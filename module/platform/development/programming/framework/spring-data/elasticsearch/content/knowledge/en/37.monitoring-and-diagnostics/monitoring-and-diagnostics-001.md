# Classifying Connection, Authentication, Mapping, and Query Errors

When Spring Data Elasticsearch fails to perform an operation, the error message often travels through multiple layers: the Spring application, the Elasticsearch Java API Client, HTTP transport, the network, and the Elasticsearch cluster itself. An error surfaced at the repository layer may originate from DNS, TLS, credentials, index privileges, mapping, Query DSL, or an overloaded shard.

An effective approach is to classify errors by **originating layer and observable symptom**, then inspect the right place. You should not retry every exception the same way: transient connection errors may recover, whereas invalid mappings or invalid queries will continue to fail until code or data is fixed.

This lesson focuses on four main groups:

- **Connection and TLS**: host not found, socket cannot be opened, timeout, or untrusted certificate.
- **Authentication and authorization**: invalid credentials or identity lacks privileges on the cluster/index.
- **Mapping and document writes**: data incompatible with field types, strict mapping rejecting new fields, or writing to the wrong index.
- **Queries and search execution**: invalid Query DSL, field does not support the requested operation, timeout, shard failure, or a query not returning expected results.

## 1. Identify which layer the error comes from first

A request from the application to Elasticsearch passes through multiple steps:

~~~text
Spring service / repository
          |
          v
Spring Data Elasticsearch operations
          |
          v
Elasticsearch Java API Client
          |
          v
HTTP transport + TLS
          |
          v
Network / DNS / load balancer
          |
          v
Elasticsearch node
          |
          +--> authentication / authorization
          |
          +--> index / mapping / document
          |
          +--> query / shard execution
          |
          v
HTTP response
          |
          v
Exception translation / application handler
~~~

Some errors occur before an HTTP request reaches the cluster, such as DNS or TLS handshake failures. Some errors have clear HTTP responses such as 401, 403, 400, or 404. Some search requests return a successful HTTP status, yet the response contains shard failures or timeouts.

Therefore, when investigating, collect at a minimum:

- Operation being executed: save, bulk, update, delete, get, or search.
- Target index or alias.
- HTTP status if available.
- Elasticsearch error type and reason if the server returned an error.
- Root cause in the exception chain.
- Timestamp, duration, and correlation/request ID.
- Whether the request timed out, was retried, or ran across multiple shards.

Do not start by changing mappings or increasing timeouts before knowing which layer the error belongs to.

## 2. Quick classification by symptom

The table below helps choose the initial direction of investigation:

| Symptom | Likely error group | Check first |
|---|---|---|
| `UnknownHostException` | DNS/hostname | Hostname, DNS, container network |
| `ConnectException` / connection refused | TCP endpoint | Host, port, service state, firewall |
| `SocketTimeoutException` | Network or slow processing | Connect/read timeout, cluster load, query |
| `SSLHandshakeException` / `PKIX path building failed` | TLS trust | CA chain, truststore, certificate validity |
| HTTP 401 | Authentication | Username/password, API key, expiry |
| HTTP 403 | Authorization | Role, index pattern, API privilege |
| HTTP 400 + `mapper_parsing_exception` | Mapping/document | Field type, source value, strict mapping |
| HTTP 400 + `parsing_exception` | Query/request syntax | Query DSL, field/operator, JSON shape |
| HTTP 404 | Index/document/resource | Index alias, document ID, update semantics |
| HTTP 409 | Version conflict/create conflict | Concurrent update, duplicate ID, OCC |
| HTTP 429 | Rejection/overload | Thread pool, bulk size, concurrency, backoff |
| `timed_out: true` | Search timeout | Query cost, shard load, timeout budget |
| `_shards.failed > 0` | Partial shard failure | `failures[]`, mapping/shard/node issue |
| 0 hits, no exception | Valid query with no matches | Query semantics, analyzer, filter, data |

This is a classification guide, not an absolute conclusion. For example, a timeout may be caused by DNS, a load balancer, socket, cluster, or downstream; you must read the root cause and observe the cluster to determine it.

## 3. Connection: DNS, host, and port

If the application cannot resolve the hostname, the error usually appears before any HTTP response.

Common symptom:

~~~text
java.net.UnknownHostException: elasticsearch
~~~

Possible causes include:

- The hostname in configuration is wrong.
- The application container and Elasticsearch are not on the same Docker network.
- Kubernetes Service/DNS name uses the wrong namespace.
- Internal DNS is not ready yet.
- Testcontainers mapped host/port changed, but the Spring context still holds old values.
- An environment variable is missing or contains an incorrect hostname.

Check in order:

1. Read the final URI that the Spring client is using, without logging credentials.
2. Verify that the hostname resolves from the application's actual runtime environment.
3. Check the Elasticsearch HTTP endpoint port.
4. Check whether the container/service is running and listening on the port.
5. Check network policies, firewalls, proxies, or service meshes.
6. With Testcontainers, obtain the host and mapped port from the container fixture instead of hard-coding `localhost:9200`.

Example endpoint configuration:

~~~yaml
spring:
  elasticsearch:
    uris: http://elasticsearch:9200
~~~

The name `elasticsearch` is only valid if DNS/service discovery in the current environment resolves that name. Do not copy a Docker Compose hostname verbatim to Kubernetes if the service name differs.

### Connection refused

Symptom:

~~~text
java.net.ConnectException: Connection refused
~~~

Unlike a DNS failure, the hostname may have resolved successfully, but no process is accepting connections at that address/port. Check whether Elasticsearch has finished starting up, port mapping, bind address, and health/readiness.

In container orchestration, a process may still be starting up while the application begins sending requests too early. Use readiness checks and bounded startup retries instead of an infinite loop.

## 4. Timeouts: connect timeout and socket/read timeout

Not all timeouts have the same cause.

| Timeout type | Phase | Investigation direction |
|---|---|---|
| Connect timeout | Opening TCP connection | Network, DNS, firewall, unresponsive endpoint |
| TLS handshake timeout | Negotiating TLS | Certificate chain, proxy, handshake, server load |
| Socket/read timeout | Waiting for response after sending request | Heavy query/aggregation, slow shard, overloaded cluster |
| Application deadline | Total request exceeds service time budget | Sum of step durations, retries, downstream |

Increasing timeouts can help when a legitimate workload simply needs more time. However, increasing timeouts will not fix an inefficient query or an overloaded cluster.

For example, a search request running for 20 seconds may be caused by:

- A query scanning too many documents.
- Wildcard/prefix queries on an unsuitable field.
- Sorting on an expensive field.
- An aggregation with many buckets.
- An unbalanced or overloaded shard.
- Elasticsearch merging segments or running GC.
- Network/proxy holding connections slowly.

Record application-side duration and the `took` field in the Elasticsearch response to distinguish server processing time from total latency across the network and client.

## 5. TLS: certificate, CA, and hostname

When an endpoint uses HTTPS, the client must verify the server's certificate. Common errors:

~~~text
javax.net.ssl.SSLHandshakeException
sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
~~~

This symptom usually indicates the JVM cannot build a certificate chain to a trusted CA.

Check:

- Does the application trust the CA that signed the Elasticsearch HTTP certificate?
- Is the certificate still valid (not expired)?
- Does the server send the full intermediate certificate chain?
- Does the hostname/IP used in the URI match a Subject Alternative Name (SAN)?
- Is the client mistakenly trusting the internal transport certificate instead of the HTTP endpoint certificate?
- Did the test container generate a new certificate while the client still uses an old truststore?

Example hostname mismatch:

~~~text
No subject alternative names matching IP address 127.0.0.1 found
~~~

Having the right CA is still not enough if the certificate does not include the hostname/IP the client calls. Fix the SAN or use the matching hostname. Do not disable hostname verification or use a trust-all manager just to make tests pass.

### Distinguishing TLS from authentication

- TLS handshake failure: usually has not reached the step where Elasticsearch authenticates HTTP credentials.
- HTTP 401: TLS was established and the server rejected the credentials.
- HTTP 403: credentials were recognized, but lack sufficient privileges for the action.

Do not change passwords to fix a PKIX error; do not change the truststore to fix HTTP 403.

## 6. Authentication: HTTP 401

HTTP 401 usually indicates the client did not provide valid credentials or the credentials are no longer valid.

Causes:

- Wrong username/password.
- API key was revoked, expired, or sent in the wrong format.
- The application is using secrets from another environment.
- The Authorization header was stripped by a proxy/gateway.
- Client configuration did not attach authentication to the right transport.
- Credentials were rotated, but old application instances have not reloaded.

Example error:

~~~json
{
  "error": {
    "type": "security_exception",
    "reason": "unable to authenticate user [products-search-service]"
  },
  "status": 401
}
~~~

How to resolve:

1. Identify the identity of the credentials being used without printing secrets to logs.
2. Check the secret source, version, and rotation timestamp.
3. Verify whether Basic Auth or API key is configured with the right mechanism.
4. Check whether headers reach Elasticsearch through proxies.
5. Test the authenticate endpoint with the exact credentials in a test environment.
6. Confirm all replicas/pods have received the new secret.

For API keys, the Elasticsearch REST API uses a header of the form:

~~~http
Authorization: ApiKey BASE64_ENCODED_ID_AND_KEY
~~~

If the key creation API already returned an `encoded` field, use that exact value. Do not re-encode an already encoded value or log this header.

401 is usually not a retryable error. Retrying with the same username/password/API key will continue to fail until the credentials are fixed or rotated.

## 7. Authorization: HTTP 403

HTTP 403 usually means the identity was authenticated, but its role does not permit the action.

Example:

~~~json
{
  "error": {
    "type": "security_exception",
    "reason": "action [indices:data/read/search] is unauthorized for user [products-writer]"
  },
  "status": 403
}
~~~

Check:

- Does the role have the privilege matching the API?
- Does the index pattern match the actual index after resolving aliases?
- Does the request access multiple indices?
- Does a bulk request contain mixed actions such as create, index, update, or delete?
- Does the client need `view_index_metadata` for a specific metadata operation?
- Does the alias point to a new index version not yet permitted by the role?
- Does the API require cluster privileges or index privileges?

For example, the search API needs `read`; a writer needs the corresponding write privileges; a migration job may need `manage` or specific alias/index privileges. `write` does not automatically imply index or cluster administration privileges.

Do not solve 403 by granting `all` to the service. Identify the denied action and add the exact privilege on the exact index pattern. Use the privilege check API or test with the service's own API key.

## 8. Checking effective identity and privileges

You can use Elasticsearch Security APIs in test/staging environments:

~~~http
GET /_security/_authenticate
~~~

This API shows the identity and roles recognized by Elasticsearch for the current request.

Check privileges:

~~~http
POST /_security/user/_has_privileges
Content-Type: application/json

{
  "cluster": [],
  "index": [
    {
      "names": ["products-v2"],
      "privileges": ["read", "write"]
    }
  ]
}
~~~

Use the credentials of the actual service being diagnosed. If you check with an admin user, the result will not reflect the effective privileges of the Search API or Writer.

Also confirm that the index pattern matches the backing index. A role with `read` on `products-v1` while the alias has switched to `products-v2` can produce 403 errors after deployment.

## 9. Mapping: mapper_parsing_exception

Mapping describes field types and how fields are indexed. When the source sends a value incompatible with the mapping, Elasticsearch may return HTTP 400 with an error such as `mapper_parsing_exception`.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "price": {
        "type": "double"
      },
      "createdAt": {
        "type": "date"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

Submitted document:

~~~json
{
  "productId": "P-1001",
  "price": "one million",
  "createdAt": "yesterday",
  "status": "PUBLISHED"
}
~~~

The values for `price` and `createdAt` do not fit the declared field types. Elasticsearch can reject the document.

Example response:

~~~json
{
  "error": {
    "type": "mapper_parsing_exception",
    "reason": "failed to parse field [price] of type [double]",
    "caused_by": {
      "type": "number_format_exception",
      "reason": "For input string: \"one million\""
    }
  },
  "status": 400
}
~~~

Read both `reason` and `caused_by`; the specific root cause is often in the cause chain. Do not only log the first line `mapper_parsing_exception` and ignore the offending field/value.

### Common mapping causes

- Numeric value sent as a string that cannot be converted.
- Date does not match the declared format.
- An object sent into a scalar field or vice versa.
- The field was previously indexed with a different type.
- Mapping `dynamic: strict` rejects a new field.
- Nested/object path has an invalid structure.
- Value exceeds limits or has an invalid format.

## 10. Strict mapping and undeclared fields

If the mapping uses:

~~~json
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      }
    }
  }
}
~~~

The following document has an undeclared field `supplierCode`:

~~~json
{
  "productId": "P-1001",
  "name": "Keyboard",
  "supplierCode": "SUP-01"
}
~~~

Elasticsearch may return `strict_dynamic_mapping_exception`. How to handle it:

1. Determine whether the field genuinely belongs to the document schema.
2. If valid, update the mapping/index template before writing data.
3. If the field should not exist, fix the mapper/DTO so it does not send that field.
4. If the old mapping is incompatible with the new type, create a new index version and reindex according to plan.

Do not enable unbounded dynamic mapping just to eliminate errors. That can create thousands of fields, causing mapping explosion and making the cluster hard to manage.

## 11. Mapping types cannot be changed directly at will

A common mistake is having an index where the `price` field is already `text`, and then wanting the application to change it to `double`.

The mapping of an existing field usually cannot have its type safely changed in place. Mapping updates only add fields or change certain supported attributes; changing a data type requires creating a new index with the right mapping and reindexing/transforming the data.

General workflow:

~~~text
products-v1 (price: text)
        |
        v
Create products-v2 (price: double)
        |
        v
Reindex / transform source data
        |
        v
Validate documents and queries
        |
        v
Switch products alias to products-v2
~~~

If old data contains values that cannot be parsed as numbers, clean them up or define handling rules before reindexing. Do not let a migration fail midway without reporting failed documents.

## 12. Mapping errors in Spring Data converters

Spring Data Elasticsearch converts Java entities into Elasticsearch documents via mapping metadata and converters. Errors can happen on either side:

- Before sending the request: the converter cannot convert the Java type.
- After sending the request: Elasticsearch rejects the source due to invalid mapping or data.

Example Java field:

~~~java
@Field(type = FieldType.Double)
private BigDecimal price;
~~~

If the application has custom converters or custom field formats, confirm that the actual JSON value sent is compatible with the Elasticsearch mapping.

Do not assume entity annotations automatically fix an existing mapping on the cluster. The real mapping must be checked on the target index/alias:

~~~http
GET /products/_mapping
~~~

For versioned indices, check the backing index that the alias points to as well. Entity annotations and cluster mappings can drift if the index was created before code changes.

## 13. Classifying Query DSL errors: parsing_exception

If the JSON Query DSL is malformed or uses an operator unsupported for a field, Elasticsearch usually returns HTTP 400 with `parsing_exception` or a related error.

Example invalid query:

~~~json
{
  "query": {
    "term": {
      "status": {
        "valuee": "PUBLISHED"
      }
    }
  }
}
~~~

The property name `valuee` is invalid in that position. Elasticsearch may return a parse error instead of 0 hits.

Example response:

~~~json
{
  "error": {
    "type": "parsing_exception",
    "reason": "[term] query does not support [valuee]"
  },
  "status": 400
}
~~~

How to resolve:

- Check the JSON structure and property names.
- Determine whether the query builder generates valid DSL.
- Log the sanitized request body (with sensitive data removed) in a test environment if needed.
- Use integration tests against the actual mapping.
- Do not modify index data if the error is in query syntax.

With Spring Data `NativeQuery`, inspect the built query and the type of query builder being used. Do not mix builders from Spring Data, the Elasticsearch Java API Client, and incompatible legacy APIs.

## 14. Field unsuitable for the query type

A query can be syntactically valid yet wrong for the mapping or field semantics.

Examples:

- `term` on a `text` field when full-text search is needed.
- `match` on a `keyword` field when linguistic analysis is expected.
- Sorting on a `text` field without fielddata.
- Aggregating on a `text` field without a keyword subfield.
- Range query with an incompatible date format.
- Querying a nested field without using a `nested` query.
- Using an old field name after the mapping changed.

Example field:

~~~json
{
  "name": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword"
      }
    }
  }
}
~~~

Full-text query:

~~~json
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Exact match or sort/aggregation usually uses `name.keyword`:

~~~json
{
  "query": {
    "term": {
      "name.keyword": "Wireless Keyboard"
    }
  }
}
~~~

If you sort on `name` of type text, Elasticsearch may report fielddata disabled. Use the keyword subfield for exact sort/aggregation, or design an appropriate mapping. Do not enable fielddata on text arbitrarily because it can consume large amounts of heap.

## 15. Valid query returning 0 hits is not an exception

A 0-hit response usually means the query is valid, but no matching documents were found. This is a completely different situation from a parsing error or connection failure.

Causes:

- Term does not match exactly.
- Analyzer produces different tokens than expected.
- Field path is wrong, though the query does not throw an error in that case.
- Tenant/status filter excludes all documents.
- Searching the wrong alias/index.
- Document has not been refreshed yet so it does not appear in search.
- Stored value differs in type/case/format from the query.

Check:

1. Verify the target index/alias.
2. Fetch the document by ID if the ID is known.
3. Check the field mapping.
4. Test the query using Dev Tools or an integration test.
5. Use `_explain` for a specific document if you need to understand scoring/matching.
6. Check refresh visibility if the document was just written.

Do not handle 0 hits by retrying repeatedly or increasing timeouts. First determine whether the query actually matches the data.

## 16. Missing index or document errors

HTTP 404 can appear in several situations:

- Index/alias does not exist.
- Update by ID when the document does not exist yet.
- Document was deleted between the application's read and update.
- Alias points to an index that was deleted or not yet created.
- Request uses the wrong index name.

Distinguish index missing from document missing. The handling differs:

- Index does not exist yet: check migration/index provisioning and aliases.
- Document does not exist yet: check whether business logic requires create, upsert, or returning not found.
- Document deleted concurrently: apply appropriate concurrency policies and retries.
- Wrong alias: fix deployment/lifecycle instead of arbitrarily creating indices from a runtime service.

Do not enable index auto-creation to hide deployment bugs if indices require explicitly managed mappings/settings/aliases.

## 17. Conflict: HTTP 409

409 commonly occurs when:

- Using a create operation with an ID that already exists.
- An update encounters a version conflict.
- OCC with `_seq_no` and `_primary_term` no longer matches.

Distinguish:

| Case | Meaning | Handling direction |
|---|---|---|
| CREATE duplicate ID | Document was already created | Verify whether the duplicate has the same event/payload |
| Update conflict | Document changed concurrently | Reload, merge, or bounded retry |
| Stale OCC token | Client is writing based on an old version | Do not retry with the same token; reload and decide |
| Duplicate event | Consumer received a redelivered message | Idempotency key/version guard |

Do not treat every 409 as success. If the same ID has a different payload, it may be a collision or producer bug that needs investigation.

## 18. Overload errors: HTTP 429 and rejections

When Elasticsearch cannot accept more work in a thread pool, requests may be rejected with `es_rejected_execution_exception` or HTTP 429.

Common causes:

- Bulk batch is too large.
- Too many concurrent requests.
- Heavy searches/aggregations.
- Hot shard or hot index.
- Cluster lacks CPU/heap or thread pool queue is full.
- Consumer increased concurrency beyond cluster capacity.

How to handle:

1. Reduce the number of concurrent requests.
2. Reduce bulk batch size if items/bytes are too large.
3. Retry with exponential backoff and jitter.
4. Set retry limits and deadlines.
5. Monitor thread pool rejections, CPU, heap, GC, and shard distribution.
6. Investigate queries or mappings causing high load.

Do not retry immediately in a tight loop; a retry storm can overload the cluster even further.

## 19. Search timeout and partial shard failure

A search response can have a successful HTTP status while indicating incomplete results:

~~~json
{
  "took": 12000,
  "timed_out": true,
  "_shards": {
    "total": 8,
    "successful": 7,
    "skipped": 0,
    "failed": 1,
    "failures": [
      {
        "shard": 3,
        "index": "products-v2",
        "reason": {
          "type": "query_shard_exception",
          "reason": "..."
        }
      }
    ]
  },
  "hits": {
    "total": {
      "value": 1000,
      "relation": "eq"
    },
    "hits": []
  }
}
~~~

Fields to inspect:

- `timed_out`: whether the search exceeded the timeout.
- `_shards.total`: number of targeted shards.
- `_shards.successful`: number of shards that returned results.
- `_shards.failed`: number of failed shards.
- `_shards.failures`: details of each shard failure.
- `took`: time Elasticsearch spent processing the request.

Do not only check HTTP 200. A search with shard failures can return partial results. For APIs requiring complete data, the application should treat partial results as an error or incomplete state according to the API contract.

## 20. Reading the Elasticsearch error response structure

Server errors typically have the structure:

~~~json
{
  "error": {
    "root_cause": [
      {
        "type": "mapper_parsing_exception",
        "reason": "failed to parse field [price]"
      }
    ],
    "type": "mapper_parsing_exception",
    "reason": "failed to parse field [price]",
    "caused_by": {
      "type": "number_format_exception",
      "reason": "..."
    }
  },
  "status": 400
}
~~~

Key fields:

| Field | Meaning |
|---|---|
| `error.type` | Outer Elasticsearch error type |
| `error.reason` | Primary description of the error |
| `error.root_cause` | Root causes reported by the server |
| `error.caused_by` | Nested underlying error |
| `error.failed_shards` or `failures` | Shard failure information in relevant responses |
| `status` | HTTP status |

In the Java exception chain, there may be additional wrappers from Spring Data or the transport layer. Preserve the original exception when logging and handling; do not only log `getMessage()` of the outermost exception if it does not contain enough information.

Do not parse message text with a fixed string if you can extract status/error type from the structured response. Messages can change between Elasticsearch versions.

## 21. Exception translation in Spring Data Elasticsearch

When using repositories or `ElasticsearchOperations`, errors may be translated into Spring DAO ecosystem exceptions or Elasticsearch client exceptions, depending on the API, version, and timing of the error.

Distinguish:

- Errors occurring before the HTTP request is sent: usually network/TLS exceptions from the client.
- Server returns an HTTP error: the client may build an exception carrying status and response body.
- Spring Data repositories/operations: may translate or wrap exceptions via exception translation mechanisms.
- Application code errors: validation, DTO mapping, or business rules may fail before calling Elasticsearch.

Do not rely on a single exception class name across all versions. Preserve the cause chain and classify by stable characteristics: root cause type, HTTP status, Elasticsearch error type, index, and operation.

Example logging while preserving the stack trace:

~~~java
try {
    operations.save(document, IndexCoordinates.of("products"));
} catch (RuntimeException ex) {
    log.error(
            "Elasticsearch write failed: operation={}, index={}, documentId={}",
            "save",
            "products",
            document.getId(),
            ex
    );
    throw ex;
}
~~~

This is an error observation pattern, not complete business handling. Do not log the entire document if the source contains emails, phone numbers, tokens, or sensitive data. Pass the exception as the final throwable so the logger records the stack trace and cause chain.

## 22. Classifying errors at the service layer

You can create an adapter layer to translate technical exceptions into semantic application errors:

~~~java
public enum ElasticsearchFailureCategory {
    CONNECTION,
    TLS,
    AUTHENTICATION,
    AUTHORIZATION,
    MAPPING,
    QUERY,
    NOT_FOUND,
    CONFLICT,
    OVERLOADED,
    TIMEOUT,
    PARTIAL_RESULT,
    UNKNOWN
}
~~~

The service adapter can receive the operation context and extracted error details:

~~~java
public record ElasticsearchFailure(
        ElasticsearchFailureCategory category,
        String operation,
        String index,
        Integer httpStatus,
        String errorType,
        String message
) {
}
~~~

Extracting status/error type should be implemented according to the client version in use. Avoid building a parser that depends on English phrasing in messages.

Benefits of a classification layer:

- Controllers do not need to know Elasticsearch transport details.
- Retry policies can be driven by category.
- Metrics can count errors by type.
- API responses can return stable error codes to clients.
- Client/version upgrades have minimal impact on business services.

Do not return stack traces, internal cluster node addresses, sensitive request bodies, or credentials in public API HTTP responses.

## 23. Retry policy by error group

Not every error is retryable.

| Error group | Retry? | Reason / action |
|---|---|---|
| Transient DNS, connection reset | Bounded | May recover once network/service stabilizes |
| Connect timeout | Bounded | Verify endpoint and readiness first |
| TLS trust/hostname error | No | Fix CA, certificate, or hostname |
| HTTP 401 | No | Fix/rotate credentials |
| HTTP 403 | No | Fix role/privileges |
| HTTP 400 mapping/query | No | Fix data, mapping, or request |
| HTTP 404 | Per business rules | Check index/document and upsert semantics |
| HTTP 409 | Conditional | Reload/reconcile; do not retry blindly |
| HTTP 429 | Bounded | Backoff, reduce concurrency/batch |
| HTTP 502/503/504 | Bounded | Transient error that may recover |
| Search timeout | Conditional | Optimize query or adjust timeout |
| Partial shard failure | Conditional | Check shard failures and completeness requirements |

For timed-out write requests, the outcome may be unknown: Elasticsearch may have committed the write while the response was lost. Retries are only safe if the operation is idempotent or protected by an ID/version/idempotency key.

Example exponential backoff with jitter:

~~~java
Duration baseDelay = Duration.ofMillis(100);
Duration maxDelay = Duration.ofSeconds(5);

// Pseudocode:
// delay = min(maxDelay, baseDelay * 2^attempt) + random jitter
// Retry only when FailureCategory is in a retryable group.
~~~

Use a retry library with attempt limits, deadlines, and cancellation if the application needs automatic retries. Do not write an infinite retry loop around a repository call.

## 24. Avoiding duplicate retries with bulk

A bulk request can partially succeed. If one item has a mapping error while others were written successfully, resending the entire batch can cause conflicts or re-apply update scripts.

Correct workflow:

1. Check the `errors` field.
2. Iterate through each item in the response.
3. Record successful items.
4. Classify the errors of failed items.
5. Retry only retryable items.
6. Preserve the document ID/event ID and version.
7. Send permanent errors to a DLQ or report data errors.

For bulk updates using incrementing scripts, retrying an item after a timeout requires deduplication. A request may have already updated the document even though the client never received the response.

## 25. Distinguishing mapping errors from query errors

These two errors are often confused because both can involve field names/types.

| Mapping/write failure | Query failure |
|---|---|
| Usually occurs when indexing/creating/updating a document | Occurs when a search request is parsed or executed |
| Source value does not match mapping | Query operator/field is unsuitable |
| `mapper_parsing_exception` | `parsing_exception`, `query_shard_exception`, or other execution errors |
| Check JSON source, Java converter, mapping | Check Query DSL, mapping, analyzer, sort/aggregation |
| May require fixing document or reindexing | May require fixing query or mapping to support the use case |

Example on the same `price` field:

- On write: sending the string `"free"` to a `double` field causes a mapping error.
- On search: using a range query on a `price` field not mapped as numeric may cause a query error or unexpected semantics.
- On aggregation: using a field without doc values or a `text` field may report a fielddata error.

Always determine whether the failing request is a write or read request before changing mappings.

## 26. Useful Elasticsearch diagnostic APIs

Once you have the error type/index/shard, use the appropriate API instead of running every admin command.

### Check cluster health

~~~http
GET /_cluster/health
~~~

Shows cluster status and counts of active/relocating/unassigned shards.

### Check nodes

~~~http
GET /_cat/nodes?v
~~~

Shows nodes, heap, CPU, and roles in tabular form. Requires appropriate monitor privileges.

### Check indices

~~~http
GET /_cat/indices/products-*?v
~~~

View health, document count, size, and index status.

### Check mapping

~~~http
GET /products/_mapping
~~~

Verify field types, nested/object structures, analyzers, and dynamic settings.

### Explain shard allocation

~~~http
GET /_cluster/allocation/explain
Content-Type: application/json

{
  "index": "products-v2",
  "shard": 0,
  "primary": true
}
~~~

Use when a shard is unassigned or cannot be allocated.

### Check tasks

~~~http
GET /_tasks?detailed=true&actions=*search
~~~

Useful when identifying long-running search tasks. Some APIs require appropriate monitor/cluster privileges.

Do not grant cluster admin privileges to a runtime service just so it can run all diagnostic APIs itself. Perform operational checks with a separate monitoring identity.

## 27. Structured logging and correlation IDs

Each error should be tied to an operation context to correlate application logs and Elasticsearch logs.

Useful fields:

- `traceId` or `correlationId`.
- Operation: search, index, update, bulk, delete.
- Index/alias.
- Document ID if non-sensitive.
- HTTP status.
- Elasticsearch error type.
- Duration.
- Retry attempt.
- Result category.
- Shard failure count if applicable.

Example JSON log:

~~~json
{
  "level": "ERROR",
  "message": "Elasticsearch operation failed",
  "traceId": "trace-7f31",
  "operation": "bulk",
  "index": "products-v2",
  "status": 400,
  "errorType": "mapper_parsing_exception",
  "failureCategory": "MAPPING",
  "retryAttempt": 0,
  "durationMs": 84
}
~~~

Do not log:

- Passwords, API keys, or Authorization headers.
- Private keys, keystore passwords.
- Full document source when it contains personal data.
- Query bodies containing sensitive information.
- URLs containing credentials or secret query parameters.

If you need to capture sample requests for investigation, redact sensitive fields and restrict access to logs.

## 28. Metrics and alerts

Metrics should use low-cardinality labels. Do not use document ID, user ID, or query strings as metric labels because the number of distinct values can grow without bound.

Example metrics:

| Metric | Purpose |
|---|---|
| Request count by operation | Understand search/write/bulk workload |
| Error count by category/status | Detect connection, auth, mapping, and query errors |
| Request latency p50/p95/p99 | Track latency |
| Timeout count | Detect network issues or slow queries |
| Retry count | Detect flaky dependencies or overload |
| Bulk item failure count | Detect partial failures |
| Shard failure count | Detect incomplete search results |
| 401/403 count | Detect credential/role regressions |
| 429/rejection count | Detect overload |

Alert on meaningful trends and thresholds. A single 401 after credential rotation may be a configuration mistake; a sudden spike in 401s across all replicas requires investigating secret deployment or the identity provider.

Do not monitor only HTTP 5xx. Mapping/query 400s can spike after a deployment and break ingestion/search even while the cluster remains healthy.

## 29. Returning appropriate errors from the application REST API

Do not return raw Elasticsearch exceptions to end users. Controller advice can map failure categories to application error codes:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    ResponseEntity<ApiError> notFound(ProductNotFoundException ex) {
        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(new ApiError("PRODUCT_NOT_FOUND"));
    }

    @ExceptionHandler(SearchUnavailableException.class)
    ResponseEntity<ApiError> unavailable(SearchUnavailableException ex) {
        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError("SEARCH_UNAVAILABLE"));
    }
}
~~~

The exception types here are application domain exceptions, not hardcoded Elasticsearch exception names. The service adapter is responsible for translating technical errors into appropriate business error types.

Examples:

- Search dependency unavailable: may return 503.
- Client request violates API contract filter/query: return 400.
- User lacks permission: return 403 at the API layer.
- Business document does not exist: return 404.
- Mapping error caused by an internal data bug: return a server error, log, and alert; do not expose cluster details to the client.

If a search returns partial results, the API must clearly define whether partial data is allowed or treated as unavailable. Never silently turn shard failures into an empty list.

## 30. Step-by-step diagnostic procedure

When receiving an error report from test or production:

1. Record the operation, index/alias, timestamp, and trace ID.
2. Determine whether there is an HTTP response or a pre-HTTP error.
3. If there is no response, check DNS, host/port, TCP, TLS, and timeouts.
4. If 401, verify credentials and identity.
5. If 403, verify privileges and index patterns.
6. If 400 on write, read `mapper_parsing_exception`, `caused_by`, and the mapping.
7. If 400 on search, read `parsing_exception`/`query_shard_exception` and the Query DSL.
8. If 404, distinguish index missing from document missing.
9. If 409, determine whether it is a create duplicate or optimistic conflict.
10. If 429/5xx, check load, thread pools, shards, and retry policy.
11. For search 200, still check `timed_out` and `_shards.failed`.
12. Collect cluster health, index mapping, or task details when needed.
13. Determine whether the error is retryable and the operation is idempotent.
14. Fix the right root-cause layer and run a reproducing integration test.
15. Monitor metrics/logs after deployment to confirm the error does not recur.

## 31. Error test matrix to maintain

Integration tests should verify both success cases and intentional failure cases.

| Group | Scenario | Expected outcome |
|---|---|---|
| Connection | Invalid hostname | DNS error classified as CONNECTION |
| Connection | Port not listening | Connection refused |
| Connection | Slow server | Timeout recorded |
| TLS | Untrusted CA | TLS handshake fails |
| TLS | Hostname does not match SAN | Hostname verification fails |
| Authentication | Wrong password | 401 |
| Authentication | Revoked API key | 401 |
| Authorization | Search user calls write | 403 |
| Authorization | Writer calls delete index | 403 |
| Mapping | String sent to numeric field | 400 mapping error |
| Mapping | New field with dynamic strict | Strict mapping error |
| Mapping | Incompatible old field type | Reindex/migration required |
| Query | Invalid Query DSL | 400 parsing error |
| Query | Term does not match | 0 hits, not an exception |
| Query | Sort on unsupported text | Query execution error |
| Index | Alias does not exist | 404/resource error |
| Update | Document missing | 404 or upsert per policy |
| Concurrency | Stale version | 409 conflict |
| Capacity | Too many requests | 429/rejection |
| Search | One shard fails | Check partial result |
| Search | Request timeout | `timed_out` or timeout exception |

You do not need to put every scenario in every test class. Separate unit tests for exception classification, integration tests with an Elasticsearch container, and a secured test environment for TLS/authentication/authorization.

## 32. Common diagnostic mistakes

### Only logging the outermost exception

The outer exception may only be a wrapper. Record the stack trace and preserve the cause chain to find the root cause.

### Retrying all RuntimeExceptions

Invalid mappings, invalid queries, 401, and 403 will not self-heal. Pointless retries add load and mask errors.

### Confusing 401 with 403

401 is authentication; 403 is authorization. Check identity first, then check roles.

### Confusing TLS with passwords

TLS handshake happens before HTTP authentication. PKIX/hostname errors require fixing certificates/CA/SAN.

### Confusing mapping errors with query errors

Mapping errors usually happen on write; query errors happen during search parsing or execution. Identify the operation before making fixes.

### Looking only at HTTP 200

Search can return `timed_out: true` or `_shards.failed > 0`. Inspect the response metadata.

### Treating 0 hits as a system error

0 hits can be a valid outcome. Check the query, analyzer, tenant filter, and alias.

### Granting `all` privileges to fix 403

Find the missing privilege and grant it on the right index pattern. Do not widen admin privileges just to fix a search/write error.

### Increasing timeouts instead of optimizing queries

Timeouts can be a symptom of heavy queries or an overloaded cluster. Measure `took`, shards, and query cost first.

### Logging full requests/responses

Payloads may contain personal data or secrets. Redact and log only necessary metadata.

### Ignoring partial bulk failures

A bulk request can partially succeed. Inspect each item and retry selectively.

## References

- [Elasticsearch — Troubleshooting](https://www.elastic.co/guide/en/elasticsearch/reference/current/troubleshooting.html)
- [Elasticsearch — Error response](https://www.elastic.co/guide/en/elasticsearch/reference/current/rest-api-errors.html)
- [Elasticsearch — Security privileges](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-privileges.html)
- [Elasticsearch — Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html)
- [Elasticsearch — Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Elasticsearch — Cluster health API](https://www.elastic.co/guide/en/elasticsearch/reference/current/cluster-health.html)
- [Elasticsearch — Cat nodes API](https://www.elastic.co/guide/en/elasticsearch/reference/current/cat-nodes.html)
- [Elasticsearch — Index mapping API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-get-mapping.html)
- [Spring Data Elasticsearch — Reference documentation](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch.html)
- [Spring Framework — Data access exception translation](https://docs.spring.io/spring-framework/reference/data-access/dao.html)

## Conclusion

Classify errors by layer before fixing: DNS/TCP/TLS are connection errors; 401 is authentication; 403 is authorization; `mapper_parsing_exception` usually means data does not match the mapping; `parsing_exception` or `query_shard_exception` usually involves Query DSL or query execution. For search responses, still inspect `timed_out` and `_shards.failed` even when the HTTP status is successful. In Spring Data Elasticsearch, preserve the exception cause chain, log operation/index/status/error type with a correlation ID, and avoid logging secrets or full sources. Retry only transient errors within bounds; do not blindly retry mapping/query/auth errors or non-idempotent write timeouts.
