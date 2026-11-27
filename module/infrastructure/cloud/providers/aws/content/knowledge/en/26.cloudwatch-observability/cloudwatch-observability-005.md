# CloudWatch Logs Insights and Querying Application Logs

A Spring Boot service running on Amazon ECS, EKS, or AWS Lambda can generate thousands of log events per minute. When users report a request returning HTTP 500, the operations team needs to know which service the request passed through, which step failed, whether DynamoDB or S3 was involved, and when latency started rising. If logs are just unstructured lines of text, searching and cross-referencing typically takes far too long.

**Amazon CloudWatch Logs Insights** lets you query and analyze logs directly inside CloudWatch Logs using a query language. You can filter events by time, search for exceptions, extract fields from text, group errors by service or endpoint, compute p50/p95/p99 latency, and trace requests by correlation ID.

This lesson belongs to the **Observability with CloudWatch** chapter of the **CLOUD_PROVIDERS_AWS** module. We focus on designing logs for Java/Spring Boot applications, using CloudWatch Logs Insights Query Language (Logs Insights QL), writing incident investigation queries, and optimizing scanned data volume.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the relationship between log groups, log streams, and log events.
2. Distinguish event timestamp, ingestion time, and CloudWatch Logs system fields.
3. Design structured JSON logs for Java/Spring Boot applications.
4. Use MDC/correlation IDs to tie logs together across requests and services.
5. Select appropriate log groups and time ranges before running queries.
6. Use core Logs Insights QL commands: fields, filter, parse, stats, sort, and limit.
7. Query errors, exceptions, HTTP statuses, and AWS SDK failures.
8. Compute request counts, error counts, and latency percentiles over time.
9. Find slow endpoints, common exceptions, and requests by trace ID.
10. Use parse to extract fields from unstructured text logs.
11. Discover log patterns and spot abnormal changes.
12. Run queries from the Console, AWS CLI, and API.
13. Optimize queries to reduce scanned data and cost.
14. Protect sensitive data in logs and restrict access permissions.
15. Distinguish Logs Insights from CloudWatch Metrics, metric filters, and alarms.

## 2. CloudWatch Logs: Log Groups, Log Streams, and Log Events

CloudWatch Logs organizes data around three components:

- **Log group:** groups logs sharing an application, workload, environment, or retention policy.
- **Log stream:** a stream of events from a specific source, such as a Lambda execution environment, container instance, or host.
- **Log event:** a single log record containing a timestamp and a message.

Example log group naming:

    /application/orders-api/prod
    /application/payment-service/prod
    /aws/lambda/invoice-worker
    /ecs/cluster-a/orders-api

One log group can contain many log streams. When running Logs Insights, you typically select one or more log groups as the query scope; results can aggregate logs across multiple instances/containers.

Use a consistent naming convention so operators can easily pick the right service and environment. Avoid merging development, staging, and production into the same log group when retention, access permissions, and security requirements differ.

### 2.1. System Fields

CloudWatch Logs Insights provides commonly used system fields:

| Field | Meaning |
|---|---|
| @timestamp | Timestamp of the log event |
| @message | Raw message content |
| @log | Identifier of the log group containing the event |
| @logStream | Name of the log stream |
| @ingestionTime | Time CloudWatch Logs received the event |
| @ptr | Internal pointer to the log record |

Certain log types include additional specialized system fields. For example, Lambda logs may include request-related fields or log type fields depending on format and runtime.

Do not confuse @timestamp with @ingestionTime. If an application ships logs slowly or an agent buffers logs, these two timestamps can diverge. When investigating a delayed log pipeline, compare both.

### 2.2. Event Time and Ingestion Time

`@timestamp` is the time attached to an event when it is sent to CloudWatch Logs. `@ingestionTime` is when the service ingested the event. A large gap may indicate:

- The agent or container runtime is buffering logs.
- Network connectivity to CloudWatch Logs is unstable.
- The application is emitting events late.
- System clocks are out of sync.
- Log batches are flushed periodically after a delay.

Therefore, when aligning events with traces, metrics, and deployment timelines, verify workload timezones and clock synchronization.

## 3. Standardizing JSON Logs for Java/Spring Boot

Logs Insights can automatically discover fields from JSON logs. With structured logs, you can filter directly on `level`, `service`, `statusCode`, or `traceId` without parsing every line.

A reference JSON event:

    {
      "timestamp": "2026-11-20T04:15:23.417Z",
      "level": "ERROR",
      "service": "orders-api",
      "environment": "prod",
      "message": "Unable to load order",
      "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
      "spanId": "00f067aa0ba902b7",
      "requestId": "req-7f2a91",
      "route": "/orders/{orderId}",
      "method": "GET",
      "statusCode": 503,
      "durationMs": 245,
      "errorType": "SdkClientException",
      "awsService": "DynamoDB",
      "awsOperation": "GetItem"
    }

Fields should be designed consistently:

| Field | Purpose |
|---|---|
| timestamp | Time recorded by the application, ISO 8601 UTC |
| level | DEBUG, INFO, WARN, ERROR |
| service | Service name |
| environment | dev, staging, prod |
| message | Short, readable description |
| traceId/spanId | Links distributed traces |
| requestId | Identifies the request at the application boundary |
| route/method | Endpoint and HTTP method |
| statusCode | HTTP status |
| durationMs | Processing duration |
| errorType/errorCode | Error classification |
| awsService/awsOperation | AWS dependency invoked |

Keep field names and data types consistent. For example, `durationMs` should always be numeric rather than sometimes `"245ms"` and sometimes `245`. Numeric values allow avg, max, and percentile calculations.

Do not log passwords, access tokens, session cookies, private keys, authorization headers, or unnecessary personal data. If customer identification is required, use controlled identifiers or pseudonymous IDs per data policy.

## 4. Shipping Logs from Applications to CloudWatch Logs

CloudWatch Logs Insights can only query data that has been shipped to CloudWatch Logs. Collection methods depend on the runtime environment:

| Runtime | Common Collection Method |
|---|---|
| AWS Lambda | Lambda integrates natively with CloudWatch Logs; execution role needs log write permissions |
| Amazon ECS | awslogs log driver or FireLens/Fluent Bit |
| Amazon EKS | Fluent Bit, CloudWatch agent, or OpenTelemetry Collector |
| EC2 | CloudWatch Agent or log shipper |
| On-premises/external apps | Agent/collector with appropriate credentials and network connectivity |

For containers, write logs to stdout/stderr and let the runtime log driver/collector forward them. Avoid having applications manage large local log files inside container filesystems when the platform provides standard log collection.

A log pipeline must clearly define:

1. Event format (JSON or plaintext).
2. Timestamp and timezone.
3. Multiline handling for Java stack traces.
4. Log group/stream naming.
5. Batch size and retry behavior when shipping logs.
6. Retention, encryption, and access control.
7. Handling log delivery failures and backpressure.

### 4.1. Java Stack Traces and Multiline Logs

Java exceptions typically span multiple lines. If a collector splits each line into a separate event, stack traces become fragmented and hard to search.

Prefer a single JSON event containing exception type, message, and the stack trace serialized into one field. If using plaintext logs, configure the agent/Fluent Bit multiline parser to merge stack traces along event boundaries.

Do not put entire stack traces into metric dimensions or high-cardinality labels. Stack traces belong in logs for investigation; metrics should use bounded error types/codes.

## 5. Correlation IDs and MDC in Spring Boot

As an HTTP request flows through controller, service, and repository layers, logs should carry the same correlation ID. With distributed tracing, use trace context per W3C Trace Context or OpenTelemetry rather than inventing an ad-hoc trace ID scheme.

SLF4J MDC can hold contextual fields while processing on the same thread:

    String traceId = resolveTraceId(request);

    MDC.put("traceId", traceId);
    try {
        filterChain.doFilter(request, response);
    } finally {
        MDC.remove("traceId");
    }

This illustrates a servlet filter snippet. In production code, validate header length and format from clients, never treat a correlation ID as authentication proof, and always clear MDC in a finally block to prevent context leakage across requests.

MDC usually relies on ThreadLocal. With async execution, thread pools, Reactor/WebFlux, or CompletableFuture, context may not propagate automatically across threads. Use appropriate context propagation/instrumentation, especially when integrating OpenTelemetry.

JSON logs should include traceId/spanId so you can query by request and correlate with the trace backend when needed.

## 6. Opening Logs Insights and Selecting Query Scope

In the AWS Console:

1. Select the correct AWS Region.
2. Open CloudWatch.
3. Choose Logs Insights.
4. Select the log groups for the application under investigation.
5. Select an appropriate time range.
6. Write and run the query.
7. Inspect the log event count, results, and scanned data volume.

When querying multiple log groups, results can mix logs from multiple services. Filter on `service` or `environment` to avoid drawing wrong conclusions.

Checklist before querying:

- Correct account and Region.
- Correct log group—do not confuse staging and prod.
- Time range covers the incident window.
- Log retention has not expired the time window under investigation.
- Events have been ingested; brand-new logs may take a moment to become queryable.
- The selected query language is Logs Insights QL if using the syntax in this lesson.

## 7. Basic Structure of Logs Insights QL

A query typically chains commands using the pipe `|` character:

    fields @timestamp, level, service, message
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 100

Commands execute sequentially from top to bottom. You can use multiple filter and fields commands to narrow or shape results.

| Command | Role |
|---|---|
| fields | Select or compute display fields |
| filter | Keep events matching a condition |
| parse | Extract fields from text messages |
| stats | Aggregate, count, and calculate percentiles |
| sort | Sort results |
| limit | Cap the number of returned records |
| pattern | Group logs into similar patterns |
| display | Display only the selected fields |
| unnest | Expand list elements into separate records |

This lesson uses Logs Insights QL. CloudWatch Logs Insights also supports other query languages in certain experiences/log sources; syntax is not arbitrarily interchangeable across QL, SQL, and PPL.

## 8. First Query: Viewing the Latest Logs

Query to view the 100 newest events:

    fields @timestamp, @log, @logStream, @message
    | sort @timestamp desc
    | limit 100

This query is helpful for checking whether an application is actively logging and inspecting the latest events.

If logs are JSON, prefer auto-discovered fields:

    fields @timestamp, level, service, environment, message, traceId
    | sort @timestamp desc
    | limit 100

`limit 100` only limits the number of returned results. It does not reduce how much data is scanned within the selected time range. To reduce scanned data, choose a narrower time range and fewer log groups, and filter on relevant fields.

## 9. Finding ERROR and WARN Events

Find all ERROR events:

    fields @timestamp, service, message, traceId, errorType
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 200

Find both WARN and ERROR:

    fields @timestamp, level, service, message
    | filter level in ["WARN", "ERROR"]
    | sort @timestamp desc
    | limit 200

If the application logs level inside plaintext rather than a JSON field:

    fields @timestamp, @message
    | filter @message like /ERROR|WARN/
    | sort @timestamp desc
    | limit 200

Using structured fields is generally clearer and easier to maintain than substring matching across the whole message.

### 9.1. Filtering by Service and Environment

    fields @timestamp, level, service, environment, message
    | filter service = "orders-api"
    | filter environment = "prod"
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 100

When multiple services share a log group, filtering by service is essential to exclude unrelated workloads.

## 10. Finding AWS SDK Errors and Dependency Failures

Java applications frequently call DynamoDB, S3, SQS, Secrets Manager, or RDS. Log the AWS service name, operation, error code, request ID, and trace ID where appropriate.

Find DynamoDB-related errors:

    fields @timestamp, service, awsService, awsOperation,
           errorType, errorCode, message, traceId
    | filter awsService = "DynamoDB"
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 100

Count failures by AWS operation and error type:

    filter level = "ERROR"
    | stats count(*) as failures by awsService, awsOperation, errorType
    | sort failures desc
    | limit 30

If log events lack dedicated fields, filter on the message:

    fields @timestamp, @message
    | filter @message like /ThrottlingException|ProvisionedThroughputExceededException|AccessDeniedException/
    | sort @timestamp desc
    | limit 100

Do not log credentials, request authorization headers, or full request payloads just to make querying easier. Log enough metadata to classify and correlate.

## 11. Extracting Fields with parse

For legacy plaintext logs, fields are not pre-separated. The `parse` command lets you use globs or regular expressions to extract values.

Suppose a message looks like:

    INFO method=GET path=/orders status=200 durationMs=34 traceId=abc123

Query using glob:

    parse @message "method=*, path=*, status=*, durationMs=*, traceId=*" as method, path, status, durationMs, traceId
    | fields @timestamp, method, path, status, durationMs, traceId
    | limit 100

For more complex formats, use regex named capture groups:

    parse @message /method=(?<method>\S+) path=(?<path>\S+) status=(?<status>\d{3}) durationMs=(?<durationMs>\d+)/
    | fields @timestamp, method, path, status, durationMs
    | filter status like /5\d\d/
    | limit 100

Regex parse creates fields from named groups. When the regex does not match, those fields may not be populated for that event. Test patterns against diverse real log samples, including messages with spaces, special characters, and missing fields.

### 11.1. Choosing Glob or Regex?

| Parse Method | Best Suited When |
|---|---|
| Glob | Fixed format, clear delimiters, simple structure |
| Regex | Capture groups, optional segments, complex patterns, or variable field structures |

If you control the application, emit structured JSON instead of parsing text on every query. Use parse for legacy logs or formats that cannot be changed immediately.

## 12. Counting Requests and Errors Over Time

Count events by level within the time range:

    stats count(*) as events by level
    | sort events desc

Count errors every 5 minutes:

    filter level = "ERROR"
    | stats count(*) as errors by bin(5m)

Track total requests and HTTP 5xx responses in 5-minute windows:

    stats count(*) as totalRequests,
          sum(if(statusCode >= 500, 1, 0)) as serverErrors
      by bin(5m)

If logs contain multiple events per request, include only the access/request-completion event when calculating request rate. Do not count every application log line as an HTTP request.

You can compute error percentage in the same query:

    stats count(*) as totalRequests,
          sum(if(statusCode >= 500, 1, 0)) as serverErrors
      by bin(5m)
    | fields bin(5m), totalRequests, serverErrors,
             100.0 * serverErrors / totalRequests as errorPercent

Use a numeric field for statusCode. If status was parsed from text as a string, normalize the type or filter with an appropriate regex before computing.

## 13. Measuring p50, p95, and p99 Latency

Percentiles reveal the distribution of processing times. Average can hide a cohort of very slow requests; p95/p99 expose tail latency.

    filter ispresent(durationMs)
    | stats count(*) as requests,
            avg(durationMs) as avgMs,
            pct(durationMs, 50) as p50Ms,
            pct(durationMs, 95) as p95Ms,
            pct(durationMs, 99) as p99Ms,
            max(durationMs) as maxMs

Break down by endpoint:

    filter ispresent(durationMs)
    | stats count(*) as requests,
            pct(durationMs, 95) as p95Ms,
            pct(durationMs, 99) as p99Ms
      by route
    | sort p95Ms desc
    | limit 20

Analyze latency over time:

    filter ispresent(durationMs)
    | stats count(*) as requests,
            pct(durationMs, 50) as p50Ms,
            pct(durationMs, 95) as p95Ms,
            pct(durationMs, 99) as p99Ms
      by bin(5m)

Logs Insights percentiles are statistical calculations over the queried events. They do not replace properly instrumented latency metrics for SLOs/alarms; ensure each request emits only one representative latency event.

## 14. Finding Slow Endpoints and Threshold Breaches

Find requests over 1,000 ms:

    fields @timestamp, route, method, durationMs, statusCode, traceId
    | filter durationMs > 1000
    | sort durationMs desc
    | limit 100

Find endpoints with high p95:

    filter ispresent(durationMs)
    | stats count(*) as requests,
            pct(durationMs, 95) as p95Ms,
            max(durationMs) as maxMs
      by route
    | filter requests >= 20
    | sort p95Ms desc
    | limit 20

A minimum request count threshold avoids drawing conclusions from an endpoint with only a handful of samples. In production, choose a threshold suited to traffic volume and time range.

When latency rises, compare against dependency fields such as awsService/awsOperation, database query names, or downstream statuses. Avoid logging SQL parameters or payloads containing sensitive data.

## 15. Tracing a Request by traceId

When given a trace ID from an incident, retrieve all log events carrying that ID:

    fields @timestamp, service, level, message,
           traceId, spanId, requestId
    | filter traceId = "4bf92f3577b34da6a3ce929d0e0e4736"
    | sort @timestamp asc
    | limit 500

When querying multiple log groups, results can show the request traversing the API, order service, and worker. Combining traceId with spanId helps pinpoint which log belongs to which specific span.

When using AWS X-Ray or OpenTelemetry, traces and logs are complementary signals:

- Traces describe request paths and span durations.
- Logs provide event details, exceptions, and context.
- Metrics describe quantitative trends and power alarms.

Do not treat arbitrary client-supplied trace IDs as trusted identifiers. Enforce format/length limits and follow trace context propagation standards.

## 16. Analyzing Common Exceptions

Count errors by exception type:

    filter level = "ERROR"
    | stats count(*) as occurrences by errorType
    | sort occurrences desc
    | limit 20

Count errors by error code:

    filter ispresent(errorCode)
    | stats count(*) as occurrences by errorCode
    | sort occurrences desc
    | limit 30

Find timeout errors:

    fields @timestamp, service, message, errorType, traceId
    | filter @message like /Timeout|timed out|timeout/
    | sort @timestamp desc
    | limit 100

Find authorization errors:

    fields @timestamp, service, awsService, awsOperation,
           errorCode, message, traceId
    | filter errorCode = "AccessDenied"
    | sort @timestamp desc
    | limit 100

When an exception type spikes, check release version, deployment timestamp, AWS Region, resource policies, credential refreshes, and dependency health. Never conclude root cause from the exception name alone.

## 17. Discovering Log Patterns

The `pattern` command clusters log events with similar structures into patterns, helping surface recurring messages without writing filters for every string.

    pattern @message

Pattern analysis can be used to:

- Identify the most common message templates.
- Spot a sudden surge in a specific exception type.
- Detect new messages appearing after a deployment.
- Group text logs that vary by IDs, timestamps, or dynamic values.

Pattern clustering is useful when starting an investigation on a large log group. Once you spot a notable pattern, write targeted queries using fields, filter, and stats to quantify it.

Pattern is an exploratory tool; it does not replace an intentional errorType/errorCode taxonomy in application logs. If messages vary arbitrarily, pattern grouping becomes harder to interpret.

## 18. Working with JSON Fields and Nested Data

When events are valid JSON, CloudWatch Logs Insights automatically discovers many fields. You can query top-level fields directly:

    fields @timestamp, service, level, durationMs
    | filter service = "orders-api"
    | filter durationMs > 500
    | sort durationMs desc
    | limit 100

For nested JSON, fields can be accessed with dot notation if recognized by field discovery:

    fields @timestamp, request.method, request.path,
           response.statusCode, durationMs
    | filter response.statusCode >= 500
    | sort @timestamp desc
    | limit 100

If JSON is embedded as an escaped string inside another field, use an appropriate JSON parse function or parse command. Do not assume every nested field is auto-discovered across all log types; inspect the discovered fields list and test with a small query.

Avoid field names containing spaces or special characters. Use a consistent naming convention such as lowerCamelCase or snake_case.

## 19. Querying Multiple Log Groups and Services

Logs Insights can query multiple log groups simultaneously. This helps when requests traverse multiple services or when comparing workloads.

Example querying errors by service:

    filter level = "ERROR"
    | stats count(*) as errors by service
    | sort errors desc
    | limit 50

Querying by environment and AWS Region:

    fields @timestamp, service, environment, awsRegion, level, message
    | filter environment = "prod"
    | filter awsRegion = "ap-southeast-1"
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 200

When querying with cross-account observability, proper CloudWatch configuration and permissions are required between the monitoring account and source accounts. Do not assume specifying a log group name alone crosses account boundaries.

If log groups have differing schemas, queries can return many nulls or inconsistent fields. Standardize schemas before scaling queries across the entire system.

## 20. Running Queries with AWS CLI

AWS CLI provides commands to start a query, read results, and stop a query.

Example starting a query:

    aws logs start-query \
      --log-group-names "/application/orders-api/prod" \
      --start-time <START_EPOCH_SECONDS> \
      --end-time <END_EPOCH_SECONDS> \
      --query-string 'fields @timestamp, level, message, traceId | filter level = "ERROR" | sort @timestamp desc | limit 100'

The command returns a `queryId`. Use that ID to retrieve results:

    aws logs get-query-results --query-id <QUERY_ID>

If a query runs for a while, you can call get-query-results repeatedly to check status. Common statuses include Scheduled, Running, Complete, Failed, Cancelled, and Timeout. Stop running queries when no longer needed:

    aws logs stop-query --query-id <QUERY_ID>

`start-time` and `end-time` are Unix epoch seconds, not milliseconds. Compute the exact time range and Region before running.

The CLI sample uses placeholders; substitute actual epoch timestamps and query IDs. Quoting rules differ across Bash, PowerShell, and CI shells. In automation scripts, prefer loading the query string from a file or passing arguments according to your shell's quoting rules.

## 21. Using the Logs Insights API in Automation

Applications or incident tooling can call the CloudWatch Logs Insights API:

- StartQuery: start a query and obtain a query ID.
- GetQueryResults: check status and retrieve results.
- StopQuery: stop a query that is no longer needed.
- DescribeQueries: list recent queries by log group/time range.
- PutQueryDefinition: save a query definition for reuse.

An automation workflow should:

1. Select account/Region and log groups from controlled configuration.
2. Calculate start/end times from the incident window.
3. Submit the query with a bounded time range.
4. Record the query ID and correlation/incident ID.
5. Poll GetQueryResults with appropriate backoff if the query is not yet complete.
6. Stop the query on cancellation or deadline expiration.
7. Store results per data policy without leaking sensitive logs into tickets or chat.

The IAM role running automation needs logs:StartQuery, logs:GetQueryResults, and logs:StopQuery scoped appropriately. Add describe/query-definition permissions if the workflow uses those APIs.

## 22. Optimizing Queries and Cost

Logs Insights costs depend on data scanned per CloudWatch Logs Insights pricing and Region. Broad queries across large log groups can be slow and costly even if they return only a few rows.

Optimization principles:

1. Choose the smallest time range sufficient to cover the incident.
2. Select only the necessary log groups.
3. Filter early on service/environment/level in the query.
4. Prefer structured fields over regexes across all of @message.
5. Select only the fields needed for display.
6. Use log classes and retention suited to workload/query needs.
7. Save frequently used queries so operators do not rewrite them from scratch.
8. Stop expensive or mis-scoped queries.
9. Monitor bytes scanned and query duration.
10. Use metrics for recurring dashboards/alarms instead of continuously querying high-volume logs for monitoring.

`limit` caps the displayed results but does not guarantee lower bytes scanned. Narrowing the time range, reducing the number of log groups, and filtering data early control scan volume.

### 22.1. Field Indexes

CloudWatch Logs supports field indexes for certain log group types and query conditions. When an organization creates an index policy on frequently filtered fields, equality queries on indexed fields can reduce the volume of data scanned.

Field indexes do not automatically apply to every field or every query operator. Check log class, index policy, and current documentation before relying on indexes for optimization. Design field cardinality and query patterns deliberately; do not index every field indiscriminately.

## 23. Retention, Log Class, and Data Protection

Log groups require appropriate retention policies. Keeping logs indefinitely increases costs and may violate data policies; overly short retention can leave incident investigations or audits without evidence.

Consider:

- Retention aligned with environment and data classification.
- Encryption at rest and KMS key policies when required.
- Least-privilege IAM permissions for logs:FilterLogEvents, logs:StartQuery, logs:GetQueryResults, and logs:Unmask if specially needed.
- Data protection policies to detect/mask sensitive data per service capabilities.
- Log group class aligned with query frequency and required features.
- Exporting/archiving to S3 if long-term storage and separate analytics are required.

Do not grant logs:Unmask broadly. If your organization uses data protection, clearly define who may view unmasked content and audit unmasking activity.

Logs are not a place to store secrets. Strip secrets before logging; masking is a risk-reduction layer, not a substitute for keeping secrets out of logs.

## 24. Logs Insights vs. Metric Filters and Alarms

Logs Insights excels at ad-hoc querying, investigation, and historical analysis. It should not be the sole mechanism for detecting incidents requiring rapid response.

| Mechanism | Suited For | Example |
|---|---|---|
| Logs Insights | Flexible investigation, analysis, and querying | Finding traceId, top exceptions, p95 by route |
| Metric filter | Converting log patterns into metrics | Counting ERROR or AccessDenied lines |
| CloudWatch Metrics | Dashboards and time-series analysis | RequestCount, ErrorRate, Duration |
| CloudWatch Alarm | Detecting threshold breaches and triggering actions | Rising 5xx, high CPU, queue depth exceeding threshold |
| X-Ray/OpenTelemetry tracing | Analyzing request execution paths | Slow span on DynamoDB or a downstream service |

A production system typically combines logs, metrics, and traces. Metrics/alarms detect signals; Logs Insights helps answer what happened; traces identify which span slowed a request down.

Do not build alerting around manually run log queries. If alerts from log patterns are needed, design a metric filter or appropriate metric pipeline.

## 25. Troubleshooting When Queries Return No Results

### 25.1. No Log Events Found

Verify the correct Region/account/log group, time range, retention, and ingestion status. Confirm the workload has log-writing permissions and the log stream was created.

### 25.2. Query Returns Null Fields

Check whether events are valid JSON, whether field names/casing match, and whether the log class supports expected field discovery. Inspect raw @message to verify the schema.

### 25.3. Parse Pattern Does Not Match

Compare the regex against actual messages. Watch for whitespace, quotes, special characters, optional fields, and multiline stack traces. Test step by step with a tightly scoped query.

### 25.4. Query Too Slow or Scanning Too Much Data

Shrink the time range, drop unrelated log groups, filter by service/level, use field indexes where appropriate, and avoid running regexes over the whole message when structured fields already exist.

### 25.5. Counts Do Not Match Request Volume

The application may emit multiple events per request, retries may generate extra logs, a single request may traverse multiple services, or both access logs and application logs may be counted. Pick one canonical request-completion event and use request/trace IDs to reconcile.

### 25.6. Cannot Query a Log Group in Another Account

Check CloudWatch cross-account observability, monitoring/source account setup, Region, and IAM permissions. Do not fix this by granting logs:* across all accounts.

## 26. Scenario Exercises

### Exercise A — Find the 100 Most Recent Errors

The application emits JSON with level, message, and traceId fields.

**Answer:**

    fields @timestamp, level, message, traceId
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 100

### Exercise B — Find Requests Taking Over One Second

**Answer:**

    fields @timestamp, route, durationMs, traceId
    | filter durationMs > 1000
    | sort durationMs desc
    | limit 100

### Exercise C — Count 5xx Responses Every 5 Minutes

**Answer:**

    filter statusCode >= 500
    | stats count(*) as serverErrors by bin(5m)

### Exercise D — Find the Endpoint with the Highest p95

**Answer:**

    filter ispresent(durationMs)
    | stats pct(durationMs, 95) as p95Ms by route
    | sort p95Ms desc
    | limit 20

### Exercise E — Find All Logs for One Trace

**Answer:**

    fields @timestamp, service, level, message, traceId, spanId
    | filter traceId = "TRACE_ID"
    | sort @timestamp asc

### Exercise F — Unstructured Plaintext Logs

Messages look like `method=GET path=/orders status=503 durationMs=80`.

**Answer:** use glob or regex parse to extract method/path/status/durationMs fields, then filter on status and run stats.

### Exercise G — Errors Spiking After Deployment

**Answer:** pick a time range spanning before and after the deployment, filter by service/environment, group errorType by bin(5m), and correlate with deployment version/commit SHA in the logs.

### Exercise H — durationMs Field Returns Null

**Answer:** check that the JSON log has the exact field name and numeric type; check whether events are auto-discovered and whether the field name changed between releases.

### Exercise I — Query Uses limit 10 Yet Still Scans Large Volume

**Answer:** limit only caps returned results. Narrow the time range/log groups and use appropriate filters/indexes to reduce scanned data.

### Exercise J — Java Stack Trace Split into Multiple Events

**Answer:** configure a JSON exception event or a multiline parser in the collector so stack traces stay in a single logical event.

### Exercise K — AccessDenied Query Finds No Errors

**Answer:** check whether the application logs errorCode/awsService or only a message string; cross-reference service logs and CloudTrail. Do not assume every AccessDenied has identical message text.

### Exercise L — Logs Insights Used as a Per-Minute Alarm

**Answer:** consider metric filters or custom metrics and CloudWatch alarms for signals requiring continuous monitoring; reserve Logs Insights for root-cause investigation.

## 27. Review Questions

1. How do a log group and a log stream differ?
2. What basic components make up a log event?
3. How does @timestamp differ from @ingestionTime?
4. What does @message contain?
5. Why use JSON structured logs?
6. What data type should the durationMs field use?
7. What does MDC do in a Java application?
8. Why can MDC lose context in async/reactive flows?
9. What roles do trace ID and request ID play?
10. Which symbol does Logs Insights QL use to chain commands?
11. What does the fields command do?
12. What does the filter command do?
13. Which field-extraction methods does parse support?
14. What is stats used for?
15. How does bin(5m) group data?
16. What does pct(durationMs, 95) represent?
17. Why can p95 be more informative than average?
18. What does querying by traceId help investigate?
19. What does the pattern command do?
20. What risk arises when querying multiple log groups with inconsistent schemas?
21. In what unit does start-query accept its time range?
22. What is GetQueryResults used for?
23. What does StopQuery do?
24. Does limit guarantee fewer bytes scanned?
25. What is the primary way to reduce scanned data volume?
26. How do field indexes help queries?
27. Why shouldn't secrets be cached or logged into application logs?
28. Which factors should log retention be based on?
29. How does Logs Insights differ from CloudWatch Alarms?
30. When should you use a metric filter instead of manual queries?

**Quick answers:** (1) a group holds multiple streams; (2) timestamp and message; (3) event time vs. ingestion time; (4) raw log content; (5) direct querying by field; (6) numeric; (7) attaches context to logs; (8) MDC usually relies on ThreadLocal; (9) correlate events/requests; (10) pipe; (11) select/transform fields; (12) filter events; (13) glob and regex; (14) aggregation; (15) groups into 5-minute buckets; (16) 95th percentile; (17) exposes tail latency; (18) ties together logs from one request; (19) clusters logs into patterns; (20) missing/null fields and hard-to-interpret results; (21) Unix epoch seconds; (22) retrieve query status and results; (23) cancel a query; (24) no; (25) shrink time range/log groups and filter effectively; (26) reduce scan volume for supported conditions; (27) prevent credential/PII leaks; (28) audit, incident, compliance, and cost; (29) investigative querying vs. threshold alerting; (30) when a continuous metric from a log pattern is needed.

## 28. Production Checklist

- [ ] Log group naming is consistent across services and environments.
- [ ] JSON logs include UTC timestamp, level, service, and message.
- [ ] Request/trace IDs propagate across services.
- [ ] Logs capture route, statusCode, durationMs, and errorType as needed.
- [ ] Field names and data types remain stable across releases.
- [ ] Java stack traces are kept in one logical event or parsed properly with multiline rules.
- [ ] Passwords, tokens, cookies, private keys, or sensitive payloads are never logged.
- [ ] Workloads have least-privilege log-writing permissions.
- [ ] Operators have query permissions scoped to the proper log groups/account/Region.
- [ ] Log retention and encryption are configured.
- [ ] Data protection/masking is applied where required.
- [ ] Queries use the smallest sufficient time range and log group list.
- [ ] Queries apply fields/filter before parse/stats where appropriate.
- [ ] p95/p99 are computed on one representative event per request.
- [ ] Frequently used queries are saved and clearly named.
- [ ] Automation enforces deadlines, cancellation, and query ID tracking.
- [ ] Query cost and bytes scanned are monitored.
- [ ] Field indexes are created only for query patterns that genuinely benefit.
- [ ] Metric filters/metrics/alarms handle continuous alerting.
- [ ] Traces and logs are correlated via traceId/spanId.
- [ ] Runbooks exist for missing ingestion, slow queries, or null fields.
- [ ] Periodic reviews govern access permissions and data unmasking.

## 29. Summary

CloudWatch Logs Insights turns application logs into queryable, analyzable operational data:

- Log groups organize logs by application/environment; log streams represent emitters; log events hold timestamps and messages.
- JSON structured logs allow filtering and aggregating by level, service, status, duration, traceId, and error code.
- Logs Insights QL combines fields, filter, parse, stats, sort, limit, and pattern for investigation.
- Queries can uncover errors, analyze AWS SDK failures, compute request/error buckets over time, measure p50/p95/p99, and follow a trace.
- Parse helps with legacy logs; stable JSON schemas keep queries simple.
- Multi-log-group queries require consistent field schemas and service/environment filters.
- CLI/API support automation via StartQuery, GetQueryResults, and StopQuery.
- Costs depend on data scanned; limit does not automatically reduce bytes scanned.
- Retention, IAM, encryption, and data protection mitigate log risk.
- Logs Insights complements metrics, alarms, and distributed tracing; it does not replace continuous alerting signals.

A strong observability system captures enough context to answer operational questions, keeps sensitive data out of logs, and provides standardized queries so teams can investigate incidents rapidly.

### Official AWS Documentation

1. CloudWatch Logs Insights query syntax: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html
2. CloudWatch Logs Insights QL commands: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax-operations-functions.html
3. Discover fields in log events: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_AnalyzeLogData-discoverable-fields.html
4. Query log data with CloudWatch Logs Insights: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html
5. CloudWatch Logs Insights sample queries: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_AnalyzeLogData_Examples.html
6. StartQuery API: https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_StartQuery.html
7. GetQueryResults API: https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_GetQueryResults.html
8. StopQuery API: https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_StopQuery.html
9. CloudWatch Logs field indexes: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CloudWatchLogs-Field-Indexing.html
10. CloudWatch Logs data protection: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/mask-sensitive-log-data.html
11. CloudWatch Logs retention: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Working-with-log-groups-and-streams.html
12. CloudWatch Logs pricing: https://aws.amazon.com/cloudwatch/pricing/
13. AWS Distro for OpenTelemetry: https://aws-otel.github.io/
14. OpenTelemetry context propagation: https://opentelemetry.io/docs/concepts/context-propagation/
