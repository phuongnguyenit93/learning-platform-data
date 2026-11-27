# Log Ingestion, Security, and Observability for OpenSearch Domains

## Learning Objectives

Amazon OpenSearch Service provides managed domains for storing, searching, and analyzing data. In production systems, creating a domain and indexing documents is only the first step. Operations teams must also route logs to the right destinations, normalize data, govern access permissions, encrypt data in transit and at rest, and observe cluster health to detect issues before users are impacted.

This lesson belongs to the **Analytics and Search** chapter of the CLOUD_PROVIDERS_AWS module. It covers the operational lifecycle of an OpenSearch domain: collecting application and system logs, enabling log publishing, configuring audit and slow logs, designing multi-layered security, tracking CloudWatch metrics, and handling common operational scenarios.

After this lesson, learners will be able to:

- Distinguish logs belonging to the OpenSearch domain itself from application logs ingested into the domain.
- Choose among CloudWatch Logs subscriptions, Amazon Data Firehose, OpenSearch Ingestion, or OpenTelemetry Collector for each data flow.
- Standardize timestamps, fields, indexes, and retention prior to ingestion.
- Enable application/error logs, search slow logs, index slow logs, and audit logs.
- Configure CloudWatch Logs resource policies so OpenSearch Service can deliver logs.
- Explain domain access policies, IAM identity policies, and fine-grained access control.
- Design VPC access, security groups, HTTPS, node-to-node encryption, and encryption at rest.
- Build dashboards, CloudWatch alarms, and CloudWatch Logs Insights queries.
- Use CloudTrail and EventBridge to track configuration changes.
- Diagnose ingestion failures, authorization denials, shard issues, storage pressure, JVM pressure, and query latency.

## 1. The Big Picture: Ingest, Secure, and Observe

An OpenSearch domain typically sits at or near the end of a data pipeline. Logs can originate from applications, containers, servers, load balancers, operating systems, AWS services, or OpenSearch itself. Before indexing, data should be filtered, normalized, enriched with metadata, and stripped of unnecessary sensitive fields.

Two log streams must be kept distinct:

- **Logs ingested into the domain:** application events, access logs, audit logs from external systems, container logs, network logs, or telemetry. This is the data operations teams want to search and analyze.
- **Logs emitted by the domain:** internal OpenSearch errors, slow logs, and audit logs of the domain itself. OpenSearch Service can publish these logs to Amazon CloudWatch Logs.

Avoid piping all domain logs back into that same domain unchecked. If the domain is suffering from disk or heap pressure, ingesting extra logs at high volume worsens the outage. Maintain CloudWatch Logs or S3 as an independent observability and storage channel.

~~~mermaid
flowchart LR
    A[Applications / ECS / EKS / EC2] --> B[CloudWatch Logs / OTel]
    C[ALB / VPC / AWS services] --> B
    B --> D[Subscription / Firehose / OpenSearch Ingestion]
    D --> E[Parse, filter, enrich, normalize]
    E --> F[OpenSearch domain]
    F --> G[OpenSearch Dashboards / Search]
    F --> H[CloudWatch metrics]
    F --> I[Domain error, slow, audit logs]
    I --> J[CloudWatch Logs]
    H --> K[CloudWatch alarms / dashboards]
    J --> K
    L[CloudTrail / EventBridge] --> K
~~~

A well-designed architecture preserves three traits: data flows through an observable pipeline, access permissions are explainable, and an independent log channel remains available for diagnostics when the domain runs into trouble.

## 2. Classifying Logs and Telemetry

Logs are timestamped event records. Metrics are numeric time series. Traces capture a request's journey across multiple services. These three signals complement each other:

| Signal | Question Answered | Example |
|---|---|---|
| Logs | What happened? | HTTP 500, JSON parse error, user login failure |
| Metrics | How severe is it and how is it trending? | Request rate, p95 latency, JVM memory pressure |
| Traces | Which components did the request traverse and where did it spend time? | Checkout calling inventory, payment, and fulfillment |

Application logs typically need fields such as timestamp, severity, service, environment, request ID, trace ID, host/container, message, and error stack. Avoid logging unstructured free-form strings alone, which makes filtering by service, status code, or trace ID harder.

For security logs, explicitly define which data may be recorded. Passwords, access tokens, session cookies, private keys, payment card details, and personal data must never appear verbatim in messages or request bodies. Redact at the source or in a processor before data enters OpenSearch.

## 3. Choosing the Right Log Ingestion Path

No single pipeline fits every log source.

| Data Source | Common Ingestion Path | When Appropriate |
|---|---|---|
| CloudWatch Logs | Subscription filter to Lambda, Kinesis Data Streams, or Data Firehose | Logs are already centralized in CloudWatch |
| Apps on EC2/ECS/EKS | Fluent Bit, OpenTelemetry Collector, or suitable agent | Need to collect logs from files, stdout, or telemetry |
| OpenTelemetry logs and traces | OTel Collector → OpenSearch Ingestion | Standardizing telemetry on OTLP |
| Streaming events | Amazon Data Firehose or Kinesis Data Streams with consumers | Continuous traffic needing buffering and retries |
| Batch files | S3, Lambda, or scheduled ingestion pipelines | Historical datasets, archives, or backfills |
| AWS services with native integrations | Direct service integration or Data Firehose | Minimizing self-managed components |

Amazon OpenSearch Ingestion is a managed serverless data collector built on Data Prepper. Pipelines ingest logs, metrics, and traces, then filter, enrich, transform, normalize, and deliver them to OpenSearch domains or OpenSearch Serverless collections. The service manages pipeline infrastructure and scales within configured capacity bounds.

Data Firehose fits streaming flows needing buffering, retries, and supported delivery destinations. CloudWatch Logs subscriptions fit logs already in CloudWatch Logs needing near-real-time forwarding. OTel Collector fits applications emitting OpenTelemetry-standard telemetry.

### 3.1. When to Use CloudWatch Logs Subscriptions?

If applications already write logs to CloudWatch Logs, a subscription filter can forward events in near real time to a supported destination—such as Lambda, Kinesis Data Streams, or Amazon Data Firehose depending on architecture.

Subscription filters support pattern matching to trim volume—for instance, forwarding only `ERROR` logs or logs from one service. Subscription delivery provides at-least-once semantics, so duplicates can occur. Downstream pipelines should track event IDs, request IDs, or idempotency keys to deduplicate when needed.

Subscription filters support log groups in the Standard log class. If a log group uses Infrequent Access, check current service limits before designing a subscription.

### 3.2. When to Use OpenSearch Ingestion?

Use OpenSearch Ingestion when you need a managed pipeline to transform data prior to indexing. Data Prepper can:

- Parse JSON, Grok, or other log formats.
- Rename fields and normalize timestamps.
- Enrich metadata from sources or enrichment processors.
- Drop unwanted events.
- Route events by data type.
- Deliver logs and traces to OpenSearch.
- Emit pipeline observability metrics.

Pipelines can attach to a VPC for tighter network control. IAM principals sending data need ingest permission on the pipeline ARN, typically `osis:Ingest`. If the pipeline exports metrics to Amazon Managed Service for Prometheus, the principal also needs `aps:RemoteWrite` on the target workspace.

Example Data Prepper pipeline receiving OTLP logs, normalizing timestamps, and writing to a domain:

~~~yaml
version: "2"
checkout-logs:
  source:
    otlp:
      logs_path: "/checkout/v1/logs"
  processor:
    - copy_values:
        entries:
          - from_key: "time"
            to_key: "@timestamp"
  sink:
    - opensearch:
        hosts:
          - "https://orders-search.example.ap-southeast-1.es.amazonaws.com"
        index_type: log-analytics-plain
        aws:
          serverless: false
          region: ap-southeast-1
          sts_role_arn: "arn:aws:iam::123456789012:role/osis-to-orders-search"
~~~

This is an illustrative configuration. Replace endpoints and role ARNs with environment values. The pipeline role must be assumable and authorized to write to the domain; if the domain uses FGAC, map that role to an OpenSearch role granted write permissions on pipeline-created index patterns.

OTel Collector can export logs to the pipeline using SigV4:

~~~yaml
extensions:
  sigv4auth:
    region: ap-southeast-1
    service: osis

exporters:
  otlphttp/osis-logs:
    logs_endpoint: "https://pipeline-endpoint/v1/logs"
    auth:
      authenticator: sigv4auth

service:
  extensions: [sigv4auth]
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/osis-logs]
~~~

Avoid using a pipeline just to forward unstandardized payloads when formatting can be fixed at the source. Early standardization keeps index mappings clean and lowers storage costs.

## 4. Normalizing Logs Before Indexing

A log event can follow a JSON structure like this:

~~~json
{
  "@timestamp": "2026-11-20T06:30:12.456Z",
  "severity": "ERROR",
  "service": "checkout",
  "environment": "production",
  "host": "checkout-7d9c8",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "req-7f9a21",
  "http": {
    "method": "POST",
    "route": "/orders",
    "status_code": 500
  },
  "message": "Unable to reserve inventory",
  "error": {
    "type": "InventoryTimeout",
    "message": "Inventory service did not respond before deadline"
  }
}
~~~

Key principles:

- Use UTC and a consistent timestamp format.
- Separate severity, service, environment, status code, and trace ID into dedicated fields.
- Use `keyword` for fields used in filtering/grouping and numeric/date types for range queries.
- Avoid creating dynamic fields per request or per user unnecessarily.
- Keep mappings stable with index templates.
- Standardize index naming conventions by service and time.
- Set retention based on diagnostic value, compliance rules, and cost.
- Handle large payloads or long stack traces deliberately so single documents do not bloat.

If timestamps fail to parse properly, OpenSearch may index events by ingest time or treat timestamps as text, causing time-range dashboards to show wrong results or omit records.

## 5. Index Templates, Rollover, and Retention

For continuously ingested logs, never write everything into one permanent index. Use daily indexes or data streams/rollover suited to your OpenSearch version and workload.

Example index template for checkout logs:

~~~json
{
  "index_patterns": ["logs-checkout-*"],
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1
    },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "severity": { "type": "keyword" },
        "service": { "type": "keyword" },
        "environment": { "type": "keyword" },
        "trace_id": { "type": "keyword" },
        "request_id": { "type": "keyword" },
        "message": { "type": "text" },
        "http": {
          "properties": {
            "status_code": { "type": "integer" },
            "method": { "type": "keyword" }
          }
        }
      }
    }
  }
}
~~~

The primary shard count above is illustrative only. Choose shard counts based on index size, ingest rate, query patterns, and data node count. AWS suggests 10–30 GiB per shard for search workloads and 30–50 GiB per shard for log workloads; 50 GiB should be treated as a ceiling for growth planning. Typically keep at least one replica for redundancy and read capacity. Too many shards raise heap and cluster state overhead; too few shards create oversized shards or limit parallelism.

Index State Management (ISM) can automate rollovers, transitions to warm/cold tiers where supported, read-only states, or deletion after expiration. Align retention policies with data owners and audit requirements. Never retain every log indefinitely simply because free storage remains.

## 6. Three Security Layers of an OpenSearch Domain

OpenSearch Service security comprises three primary layers:

1. **Network:** determines whether requests can reach the endpoint.
2. **Domain access policy:** determines which principals can invoke which URIs or APIs on the domain.
3. **Fine-grained access control (FGAC):** authenticates users and enforces cluster-, index-, document-, and field-level permissions.

Around these three layers, IAM identity policies govern domain management and AWS APIs; encryption protects data in transit and at rest; CloudTrail and audit logs provide operational evidence.

A request must pass every applicable control layer. If a security group blocks traffic, the request never reaches the domain. If the domain access policy denies it, the request is rejected at the domain edge. Once traffic reaches OpenSearch, FGAC verifies identity and role mappings.

~~~mermaid
flowchart TD
    A[Client request] --> B{Network / VPC / SG}
    B -->|Deny| X[Does not reach domain]
    B -->|Allow| C{Domain access policy}
    C -->|Deny| Y[Edge policy rejects]
    C -->|Allow| D{FGAC authentication}
    D -->|Fail| Z[Authentication denied]
    D -->|Success| E{Cluster / Index / Document / Field permission}
    E -->|Deny| F[Authorization denied]
    E -->|Allow| G[OpenSearch operation]
~~~

Never rely on a single layer as your entire security posture. For example, a VPC security group only restricts network sources; it does not distinguish which indexes an analyst may read or which indexes an ingest role may write.

## 7. VPC Domain vs. Public Domain?

When creating a domain, choose VPC access or a public endpoint. Both models differ significantly:

| Criterion | VPC Domain | Public Domain |
|---|---|---|
| Connectivity | Clients must have network routing into the VPC | Clients route over the internet to the endpoint |
| Network controls | Security groups, routes, NACLs, VPN/TGW/proxies | Public networking and access policies |
| IP-based domain policy | Not usable; security groups enforce IP/network rules | Supported |
| Changing endpoint type | Cannot switch directly to public | Cannot switch directly to VPC |
| Best suited for | Internal production, private workloads | Controlled use cases requiring public endpoints |

VPC domains cannot be reached directly from hosts outside the VPC. Admin machines need VPN, Transit Gateway, managed networks, or properly routed proxies.

A domain created with VPC access cannot be converted to a public endpoint via configuration updates, and vice versa. Switching models requires creating a new domain, migrating data, and pointing clients to the new endpoint.

Domain security groups should allow HTTPS solely from authorized workload security groups or CIDRs. Never open inbound traffic to the entire internet merely for convenient OpenSearch Dashboards testing.

## 8. Domain Access Policies and IAM Identity Policies

A domain access policy is a resource-based policy attached to the domain. It governs calls to OpenSearch subresources such as indexes and HTTP APIs. Resource ARNs typically look like:

~~~text
arn:aws:es:ap-southeast-1:123456789012:domain/orders-search/*
~~~

Example allowing only an application role to invoke HTTP APIs on the domain:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCheckoutService",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/checkout-search-role"
      },
      "Action": [
        "es:ESHttpGet",
        "es:ESHttpPost",
        "es:ESHttpPut"
      ],
      "Resource": "arn:aws:es:ap-southeast-1:123456789012:domain/orders-search/*"
    }
  ]
}
~~~

This is an example domain resource policy. Scope HTTP methods to actual API usage. Never grant `es:ESHttp*` to every principal if an application only reads or indexes a subset of data.

If the domain access policy specifies an IAM user or role, clients must sign requests with AWS Signature Version 4. This can conflict with FGAC configured for an internal user database and HTTP Basic Authentication, since a client cannot sign the same request with both username/password and IAM credentials simultaneously. When using an internal user database, a common pattern is an access policy without IAM principal requirements paired with VPC/security groups for network isolation while FGAC handles authentication and authorization. When using an IAM master user, clients sign with SigV4 and rely on role mappings. Pick one consistent model across applications and Dashboards.

IAM identity policies typically control configuration APIs such as `DescribeDomain`, `UpdateDomainConfig`, `CreateDomain`, and `DeleteDomain`, and can also grant HTTP API permissions to principals. Keep domain administration rights separate from data access rights.

In domain access policies, resource ARNs end with `/*` to target subresources. Configuration API permissions target the domain ARN itself, not the `/*` subresource ARN.

If a policy specifies `"*"` as Principal, the domain can accept anonymous requests under matching conditions. Never use open access policies on public production domains. On VPC domains, security groups still gate network access, yet an open policy without principal constraints accepts unsigned HTTP requests from any host permitted by the security group. Enable FGAC and restrict roles rather than treating VPC placement as data authorization.

## 9. Fine-Grained Access Control

FGAC provides authorization at multiple tiers:

- **Cluster-level:** cluster APIs, health checks, index templates, or cluster-wide operations.
- **Index-level:** reading, writing, creating indexes, managing aliases, and mappings.
- **Document-level security (DLS):** restricts users to documents matching a query.
- **Field-level security (FLS):** includes or excludes specific fields.
- **Field masking:** obscures sensitive field values per configuration.

FGAC uses OpenSearch roles, users, and role mappings. OpenSearch roles are distinct from IAM roles: IAM roles represent AWS identities, while FGAC roles hold permissions inside the cluster. An IAM role can map to one or more FGAC roles.

Treat FGAC as an upfront architectural decision: once enabled, it cannot be disabled directly. Major security model changes require migrating to a new domain.

Examples:

- The `ingest` role can write only to `logs-checkout-*`.
- The `analyst` role can search only on `logs-*`.
- The `security-auditor` role reads only audit indexes.
- The `support` role views only documents belonging to assigned tenants.
- The `pii-restricted` role hides `email` or `phone` fields.

FGAC requires HTTPS, encryption at rest, and node-to-node encryption on the domain. Once FGAC is enabled, it cannot be turned off directly. When designing a new domain, decide the master user, authentication method, and role mappings upfront.

## 10. Master User and Identity Management

The master user holds elevated privileges on the OpenSearch cluster. You can choose:

- An IAM principal as master user.
- An internal user database with username/password.

Because the master user has broad privileges, reserve it strictly for managing roles, users, mappings, and security settings. Ingest pipelines and dashboards should never use master credentials.

You can configure SAML authentication for OpenSearch Dashboards to integrate an identity provider. With an IAM master user, browser-based Dashboards sign-in requires configuring a supported login mechanism such as SAML or Amazon Cognito. Setting an IAM master user alone without a web sign-in flow prevents Dashboards login from working as expected.

Role mapping is mandatory. Creating a role without mapping users or backend roles causes requests to be denied. With SAML, you can map group attributes from the identity provider to FGAC roles.

## 11. HTTPS, Node-to-Node Encryption, and Encryption at Rest

The three encryption controls protect distinct surfaces:

| Setting | What It Protects | Role |
|---|---|---|
| Require HTTPS | Client to domain endpoint | Encrypts requests/responses between clients and domain |
| Node-to-node encryption | Communication between OpenSearch nodes | TLS 1.2 for internal data movement |
| Encryption at rest | Data on storage | AWS KMS and AES-256 |

Node-to-node encryption protects traffic while OpenSearch shards and replicates data across nodes. When clients connect over HTTPS, data remains encrypted internally throughout processing and replication. Node-to-node encryption is a prerequisite for FGAC.

Once node-to-node encryption is enabled, it cannot be disabled directly. Changing it requires creating a new domain, snapshotting/migrating data, and cutting over applications.

Encryption at rest uses AWS KMS with either AWS owned keys or customer managed keys. With customer managed keys, ensure key policies and key state allow OpenSearch Service usage. Disabling or losing access to the key triggers KMS errors and disrupts domain operation.

Note: domain encryption at rest does not automatically encrypt CloudWatch Logs log groups. Enable KMS encryption separately on log groups when needed. Manual S3 snapshot repositories also use bucket-level encryption separately.

## 12. Enabling Log Publishing for Domains

OpenSearch Service supports four main log types published to CloudWatch Logs:

| Log Type in Config | Contents | Purpose |
|---|---|---|
| `ES_APPLICATION_LOGS` | OpenSearch error/application logs | Query, indexing, script, snapshot, and operational errors |
| `SEARCH_SLOW_LOGS` | Search request or search slow logs | Identifying slow queries |
| `INDEX_SLOW_LOGS` | Shard indexing slow logs | Identifying slow indexing operations |
| `AUDIT_LOGS` | User activity and security events | Investigating authentication, authorization, and compliance |

These logs are disabled by default. Enabling them incurs CloudWatch Logs usage charges. Create a separate log group per log type to manage retention, access, and querying cleanly.

To enable log publishing via console:

1. Open Amazon OpenSearch Service.
2. Select the domain.
3. Open the Logs tab.
4. Select the log type to publish and choose Enable.
5. Select or create a CloudWatch log group.
6. Grant a resource policy for the OpenSearch service principal.
7. Wait for the domain to return to Active state and verify log streams.

When enabling log publishing, the domain enters Processing state; update duration depends on configuration and can take time. Never assume checking the box guarantees logs are arriving—verify resource policies, log groups, and thresholds.

## 13. CloudWatch Logs Resource Policy for OpenSearch

OpenSearch Service needs permissions to create log streams and write log events. A CloudWatch Logs resource policy grants the `es.amazonaws.com` service principal access to target log groups.

Example policy scoped to account and domain:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOpenSearchDomainLogDelivery",
      "Effect": "Allow",
      "Principal": {
        "Service": "es.amazonaws.com"
      },
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/*:*",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "123456789012"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:es:ap-southeast-1:123456789012:domain/orders-search"
        }
      }
    }
  ]
}
~~~

`SourceAccount` and `SourceArn` conditions mitigate confused deputy risks. Supply exact account, Region, domain, and log group ARNs. These conditions require compatible service software; if running an older domain, verify compatibility before applying.

CloudWatch Logs limits the number of resource policies per Region. If multiple domains publish logs, manage one centralized policy covering the required log groups rather than exceeding policy quotas.

Example creating the resource policy with AWS CLI:

~~~bash
aws logs put-resource-policy \
  --policy-name opensearch-domain-logs \
  --policy-document file://opensearch-logs-policy.json
~~~

Never grant `logs:PutLogEvents` more broadly than required log groups. Configure retention per log group and restrict who can read audit logs.

## 14. Enabling Log Publishing via AWS CLI

Create the log group first:

~~~bash
aws logs create-log-group \
  --log-group-name /aws/opensearch/orders-search/application
~~~

Once the resource policy is in place, enable log types using `update-domain-config`:

~~~bash
aws opensearch update-domain-config \
  --domain-name orders-search \
  --log-publishing-options '{
    "ES_APPLICATION_LOGS": {
      "CloudWatchLogsLogGroupArn": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/application",
      "Enabled": true
    },
    "SEARCH_SLOW_LOGS": {
      "CloudWatchLogsLogGroupArn": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/search-slow",
      "Enabled": true
    },
    "INDEX_SLOW_LOGS": {
      "CloudWatchLogsLogGroupArn": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/index-slow",
      "Enabled": true
    },
    "AUDIT_LOGS": {
      "CloudWatchLogsLogGroupArn": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/audit",
      "Enabled": true
    }
  }'
~~~

The command above illustrates a shell supporting single-quoted JSON. In PowerShell or CI environments, adjust quoting or save JSON to a file and pass a file parameter.

Verify the configuration:

~~~bash
aws opensearch describe-domain-config \
  --domain-name orders-search
~~~

Check `LogPublishingOptions` to verify exact ARNs, log types, and `Enabled=true`. Then open CloudWatch Logs and confirm new log streams appear.

## 15. Error/Application Logs

`ES_APPLICATION_LOGS` captures internal OpenSearch error logs. When enabled, the service publishes `WARN`, `ERROR`, and `FATAL` lines, along with selected `DEBUG` exceptions.

Commonly useful events:

- Painless script compilation errors.
- Invalid queries or shard errors.
- Mapping/parsing exceptions during document indexing.
- Snapshot failures.
- Index State Management migration failures.
- Rejected executions or resource exhaustion errors.

Not every error surfaces in error logs. When clients receive HTTP 4xx or 5xx responses, correlate response bodies, application logs, audit logs, and metrics at the same timestamp. Never conclude no logs means no errors.

## 16. Search Slow Logs and Index Slow Logs

Slow logs pinpoint time-consuming operations. Two scopes are common:

- Search request slow logs measure total processing duration of search requests; supported on OpenSearch 2.13 and later per service docs.
- Shard slow logs record search or indexing duration at the shard/index level.

Enabling log publishing alone is insufficient. For shard slow logs, configure thresholds in index settings so OpenSearch knows what counts as slow.

Example setting thresholds on a log index:

~~~http
PUT logs-checkout-*/_settings
{
  "index.search.slowlog.threshold.query.info": "1s",
  "index.search.slowlog.threshold.query.warn": "3s",
  "index.indexing.slowlog.threshold.index.info": "1s",
  "index.indexing.slowlog.threshold.index.warn": "3s"
}
~~~

These values are starting baselines. Tailor thresholds to SLOs, query types, volume, and normal latency. Thresholds set too low flood logs and raise costs; thresholds set too high miss queries hurting users.

During testing, you can temporarily lower thresholds in non-production to verify log delivery, then restore normal values. Never leave test thresholds active in production longer than necessary.

## 17. Audit Logs and Tracking User Activity

Audit logs track cluster activity including authentication successes/failures, OpenSearch requests, index changes, and search queries. Audit logs require FGAC on the domain.

Enabling audit logs takes two steps:

1. Enable `AUDIT_LOGS` publishing in domain settings and apply the CloudWatch Logs resource policy.
2. In OpenSearch Dashboards, enable audit logging and configure desired layers/categories.

The user configuring audit settings must be mapped to the `security_manager` role to access the Security REST API.

Common categories:

| Category | Meaning |
|---|---|
| `FAILED_LOGIN` | Authentication failure |
| `AUTHENTICATED` | Authentication success |
| `MISSING_PRIVILEGES` | User lacks permission for request |
| `GRANTED_PRIVILEGES` | Request authorized |
| `INDEX_EVENT` | Index management operation |
| `COMPLIANCE_DOC_READ` | Document read under compliance audit |
| `COMPLIANCE_DOC_WRITE` | Document write under compliance audit |

Do not enable every category blindly. `GRANTED_PRIVILEGES` and `AUTHENTICATED` can fire on every valid request, surging log volume. AWS recommends excluding these two categories in typical default configurations and enabling them only during targeted investigations.

Audit settings can also log request bodies. While helpful for diagnostics, request bodies may expose sensitive data. Configure `exclude_sensitive_headers`, `ignore_users`/`ignore_requests`, and compliance logging per security standards.

Audit log messages have size limits; oversized content may be truncated. Some cross-cluster search requests rejected by the destination domain's access policy do not appear in the destination domain's audit logs. Include CloudTrail, source domain logs, and client logs when investigating cross-cluster search.

## 18. Sample Audit Log Configuration

Once publishing is enabled on the domain, configure audit logs via OpenSearch Dashboards or the Security REST API.

Minimal configuration retaining investigative categories while excluding high-noise events:

~~~json
{
  "enabled": true,
  "audit": {
    "enable_rest": true,
    "disabled_rest_categories": [
      "GRANTED_PRIVILEGES",
      "AUTHENTICATED"
    ],
    "enable_transport": true,
    "disabled_transport_categories": [
      "GRANTED_PRIVILEGES",
      "AUTHENTICATED"
    ],
    "resolve_bulk_requests": true,
    "log_request_body": false,
    "resolve_indices": true,
    "exclude_sensitive_headers": true,
    "ignore_users": [
      "kibanaserver"
    ],
    "ignore_requests": [
      "/_cluster/health"
    ]
  }
}
~~~

Example REST request:

~~~http
PUT _plugins/_security/api/audit/config
Content-Type: application/json

{
  "enabled": true,
  "audit": {
    "enable_rest": true,
    "disabled_rest_categories": [
      "GRANTED_PRIVILEGES",
      "AUTHENTICATED"
    ],
    "enable_transport": true,
    "disabled_transport_categories": [
      "GRANTED_PRIVILEGES",
      "AUTHENTICATED"
    ],
    "log_request_body": false,
    "exclude_sensitive_headers": true
  }
}
~~~

Production configurations must retain categories required by compliance policies. If you must prove who read or wrote specific documents, evaluate compliance logging and associated costs. Test on a non-production domain first since audit settings impact log volume and privacy.

## 19. Observing Domains with CloudWatch Metrics

Amazon OpenSearch Service publishes metrics under the `AWS/ES` namespace. Most metrics emit every 60 seconds; certain EBS metrics update on longer intervals. Cumulative counters such as rejected tasks can reset during node restarts, replacements, or blue/green deployments.

Metrics observe three pillars:

- **Cluster health:** shard state, node count, and write acceptance.
- **Resource pressure:** CPU, JVM heap, storage, queues, and rejected requests.
- **Workload performance:** search rate, indexing rate, latency, and request volume.

Common dimensions include `ClientId` and `DomainName` for domain-level metrics, plus `NodeId` for node-level metrics. Some shard metrics add `ShardRole`. Pick exact dimensions and statistics when creating alarms; wrong dimensions leave alarms stuck in `Insufficient Data`.

The service retains metrics for a bounded window before aging them out. CloudWatch dashboards and alarms can incur charges, even though standard OpenSearch Service metrics are published without extra custom-metric charges.

## 20. Key Metrics and Interpretation

| Metric | Meaning | Signal to Investigate |
|---|---|---|
| `ClusterStatus.red` | Primary or replica shards unassigned | Cluster risks data loss or partial index unavailability |
| `ClusterStatus.yellow` | Replica shards unassigned | Reduced redundancy |
| `FreeStorageSpace` | Available data node disk space | Disk nearing full; write block risk |
| `JVMMemoryPressure` | Percentage of Java heap used | Sustained high heap, GC pressure, write blocks |
| `CPUUtilization` | Node CPU usage | Query/index workload exceeding capacity |
| `Nodes` | Active node count | Unreachable nodes or missing nodes |
| `ClusterIndexWritesBlocked` | Whether cluster is blocking writes | Storage/heap pressure or cluster state |
| `SearchLatency` | Total search processing time per node over period | Slow queries or rising load |
| `IndexingLatency` | Indexing duration | Slow ingestion or write pressure |
| `SearchRate` | Count of search requests | Traffic changes or query patterns |
| `IndexingRate` | Count of index operations | Ingest rate and bursts |
| `ThreadpoolSearchQueue` | Queued search tasks | Search workers saturated |
| `ThreadpoolWriteQueue` | Queued write tasks | Ingestion exceeding processing rate |
| `ThreadpoolSearchRejected` | Rejected search tasks | Search queue overflow |
| `ThreadpoolWriteRejected` | Rejected write tasks | Write queue overflow |
| `AutomatedSnapshotFailure` | Automated snapshot failed | Snapshot/recovery needs investigation |

CloudWatch reports `FreeStorageSpace` in MiB. The `Minimum` statistic surfaces the node with the least free disk. The `Sum` statistic gives cluster-wide free space, but requires keeping the period at one minute for accurate readings per AWS guidance.

High `SysMemoryUtilization` does not immediately signify heap trouble because OpenSearch uses the filesystem cache; `JVMMemoryPressure` is usually the sharper indicator of Java heap pressure.

On OpenSearch versions 7.1 and later, `ThreadpoolWriteRejected` is no longer the sole write-rejection metric because default write queues changed. Also monitor `CoordinatingWriteRejected`, `PrimaryWriteRejected`, and `ReplicaWriteRejected` on matching versions.

## 21. Recommended CloudWatch Alarms

Starting thresholds from AWS guidance:

| Alarm | Reference Condition | Response |
|---|---|---|
| `ClusterStatus.red` | Maximum >= 1 for 1 minute | Check shard allocation, nodes, and disk |
| `ClusterStatus.yellow` | Maximum >= 1 for 1 minute across multiple periods | Check replica allocation and node availability |
| `FreeStorageSpace` | Minimum <= 20 GiB or 25% of node capacity | Expand EBS/storage or nodes; check retention |
| `ClusterIndexWritesBlocked` | Maximum >= 1 | Check storage, heap, and write blocks |
| `Nodes` | Minimum below expected node count | Investigate node failure |
| `AutomatedSnapshotFailure` | Maximum >= 1 | Check cluster health and snapshot status |
| `CPUUtilization` | Sustained high, e.g., 80% over 15 minutes | Scale up instance size or node count |
| `JVMMemoryPressure` | Maximum >= 95% repeatedly | Inspect heap, shards, queries, and scaling |
| `MasterJVMMemoryPressure` | Sustained high | Inspect dedicated master capacity |

Do not copy sample thresholds without factoring in your workload. For example, translate `FreeStorageSpace` based on per-node disk size, node count, and replicas. A large cluster with abundant total free disk can still fail if one node fills up due to skew.

Alarms should trigger concrete actions: SNS alerts, incident tickets, or EventBridge workflows. Avoid auto-scaling or deleting indexes off a single metric without guardrails.

## 22. Creating a CloudWatch Alarm for JVM Memory Pressure

Example AWS CLI command creating a `JVMMemoryPressure` alarm:

~~~bash
aws cloudwatch put-metric-alarm \
  --alarm-name orders-search-jvm-pressure \
  --namespace AWS/ES \
  --metric-name JVMMemoryPressure \
  --dimensions Name=ClientId,Value=123456789012 Name=DomainName,Value=orders-search \
  --statistic Maximum \
  --period 60 \
  --evaluation-periods 3 \
  --datapoints-to-alarm 3 \
  --threshold 90 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data missing \
  --alarm-actions arn:aws:sns:ap-southeast-1:123456789012:platform-alerts
~~~

The 90% threshold is an illustrative example. Cross-check recommendations by metric, workload, and runbook. For node-level alarms, add the `NodeId` dimension and decide whether per-node alarms are required.

Alarms for cluster `red` should use `Maximum` and trigger fast. Alarms for `yellow` often need multiple evaluation periods to avoid transient alerts during shard relocations. Use composite alarms when combining cluster status, storage, and node count.

## 23. Using CloudWatch Logs Insights for Investigation

Once logs are published, CloudWatch Logs Insights filters errors by time, severity, domain, or exception.

Example searching for `ERROR`/`FATAL` in the application log group:

~~~text
fields @timestamp, @message
| filter @message like /ERROR|FATAL/
| sort @timestamp desc
| limit 100
~~~

Search slow query logs exceeding thresholds when the format contains `took`:

~~~text
fields @timestamp, @message
| filter @message like /took/
| sort @timestamp desc
| limit 100
~~~

Find failed logins from audit logs:

~~~text
fields @timestamp, @message
| filter @message like /FAILED_LOGIN/
| sort @timestamp desc
| limit 100
~~~

Log formats vary by version and configuration. When logs are parsed into JSON fields, filter on structured fields instead of string regexes. Broad scans across huge log groups consume time and scan fees; always bound time ranges and log groups.

## 24. CloudTrail and EventBridge for Domain Activity

CloudTrail records configuration API calls to OpenSearch Service, such as:

- `CreateDomain` and `DeleteDomain`.
- `UpdateDomainConfig`.
- `AddTags` and `RemoveTags`.
- Changes to access policies or security configurations.
- Other OpenSearch domain management APIs tracked by CloudTrail.

CloudTrail answers who called the AWS API, from which account, source IP, and timestamp. It does not replace OpenSearch audit logs for individual search requests or document operations.

Amazon EventBridge receives near-real-time service events describing domain state changes. Create rules to detect transitions to Processing, config updates, errors, or service events, then route to SNS, incident creation, or automated response workflows.

Combine all three sources:

| Source | Scope |
|---|---|
| CloudTrail | Who modified AWS domain/API configurations |
| OpenSearch audit logs | Who signed in and acted inside the cluster |
| CloudWatch metrics/logs | How the cluster and workloads behaved |

During investigations, align UTC timestamps and preserve domain names, request IDs, principal ARNs, and trace IDs to correlate events across sources.

## 25. Application Observability with OpenTelemetry

To observe application logs, traces, and metrics together, use OpenTelemetry Collector as a unified telemetry collector. The collector receives OTLP from SDKs or auto-instrumentation, then forwards logs/traces to OpenSearch Ingestion via SigV4. Metrics can route to Amazon Managed Service for Prometheus using Prometheus Remote Write.

Sample flow:

~~~mermaid
flowchart LR
    A[Application SDK / Agent] --> B[OpenTelemetry Collector]
    B -->|OTLP logs and traces| C[OpenSearch Ingestion]
    C --> D[OpenSearch domain]
    B -->|Prometheus Remote Write| E[Amazon Managed Service for Prometheus]
    D --> F[OpenSearch UI]
    E --> F
~~~

IAM principals emitting telemetry need `osis:Ingest` on the pipeline ARN. Sending metrics to AMP requires `aps:RemoteWrite` on the workspace. OpenSearch Ingestion processes, enriches, and routes telemetry before indexing.

OpenSearch Service now offers a newer observability experience inside OpenSearch UI workspaces. Capabilities such as Application Monitoring, service maps, and logs/traces/metrics correlation are documented for OpenSearch UI; they do not map one-to-one with every plugin inside traditional OpenSearch Dashboards. Verify workspace types and feature availability before designing dashboards.

## 26. Protecting Logs and Sensitive Data

Logs frequently contain user-identifiable details or internal architecture clues. Before ingesting, determine:

- Which fields contain personal data or secrets.
- Who is allowed to read corresponding indexes.
- Who has permission to export or snapshot.
- How long logs are retained.
- Which KMS keys encrypt log groups and S3 archives.
- Whether field masking or document-level security is needed.
- Who can alter audit settings or retention.

Never log access tokens, passwords, session cookies, or private keys. Avoid enabling request-body audit logging globally if payloads may contain personal data. Apply data minimization and redaction at sources/processors.

For multi-tenant datasets, isolate indexes per tenant or use DLS to filter documents by tenant ID. Test DLS/FLS across bulk APIs, aliases, aggregations, and dashboards—a flawed policy can leak data through indirect queries even when the UI hides certain fields.

## 27. Governing Retention and Observability Costs

Operating an OpenSearch domain costs more than compute and storage alone. Log publishing, CloudWatch Logs ingestion/storage, dashboards, alarms, Data Firehose, OpenSearch Ingestion, and snapshots all add charges.

Cost-control practices:

- Separate application, search slow, index slow, and audit log groups.
- Set shorter retention for debug/slow logs when long retention is unnecessary.
- Archive long-retention audit logs to S3 per policy.
- Filter aggressively in CloudWatch Logs subscriptions to trim volume.
- Redact and drop unused fields before indexing.
- Choose sensible slow log thresholds.
- Use ISM to roll over and expire old indexes.
- Track ingest bytes, index size, shard counts, and storage growth.
- Pause or scale down non-continuous ingestion pipelines where use cases allow.
- Control field cardinality and total index counts.

Never set retention shorter than diagnostic or compliance requirements. If audit logs must be kept for 1 year, build dedicated archival storage and test retrieval rather than holding everything in hot storage.

## 28. Case Study: Observing an Order Search Domain

An e-commerce platform runs an OpenSearch domain serving order search and history lookup. Checkout runs on ECS, API gateways and load balancers emit access logs, and security teams monitor index access.

Design:

1. Domain lives in a VPC; security groups allow HTTPS only from ECS services and admin networks.
2. Require HTTPS, node-to-node encryption, and encryption at rest are enabled.
3. FGAC uses an IAM master role plus dedicated role mappings for `ingest`, `analyst`, and `security-auditor`.
4. ECS emits structured application logs to CloudWatch Logs.
5. Subscription filters forward matching logs to Data Firehose or OpenSearch Ingestion.
6. The pipeline normalizes timestamps, service names, environments, trace IDs, and status codes.
7. Index templates enforce explicit mappings; ISM rolls over and deletes logs per retention.
8. The domain publishes application logs, search slow logs, index slow logs, and audit logs to separate log groups.
9. CloudWatch alarms watch red/yellow status, storage, CPU, JVM pressure, node count, and write blocks.
10. CloudTrail and EventBridge detect domain configuration changes.
11. Analysts read only `logs-*` indexes; the ingest role writes only service-specific indexes; security auditors read audit logs and security events.
12. Runbooks correlate CloudWatch metrics, slow logs, audit logs, and application traces to pinpoint root causes.

If search latency climbs while CPU stays normal, the team inspects slow logs and shard distribution. If write blocks appear alongside low `FreeStorageSpace`, they inspect ISM retention, expand EBS, or add data node capacity. If `FAILED_LOGIN` or `MISSING_PRIVILEGES` spikes, they cross-check principals, role mappings, and network sources.

## 29. Symptom-Based Troubleshooting

| Symptom | First Check | Action Path |
|---|---|---|
| Domain timeout | VPC routes, SGs, NACLs, DNS | Verify client network reachability to the VPC domain |
| HTTP 403 | Domain access policy, IAM signature, FGAC role mapping | Identify which layer rejected the request |
| Log group has no streams | CloudWatch resource policy, log publishing options | Verify `es.amazonaws.com`, ARNs, and `Enabled` |
| Slow logs missing | Thresholds and log publishing | Configure index slowlog thresholds and retest |
| Audit logs not active | FGAC, `security_manager`, resource policy | Complete both domain publishing and Dashboards config |
| `ClusterStatus.red` | Unassigned primary shard, nodes, disk | Inspect allocation explain, node health, and storage |
| `ClusterStatus.yellow` | Unassigned replica shard | Check replicas, AZs, and node availability |
| Low `FreeStorageSpace` | Per-node disk, index growth, retention | Roll over, delete expired indexes, or add storage |
| High `JVMMemoryPressure` | Heap, shard count, queries, aggregations | Reduce shards/fielddata, tune queries, scale up |
| `ClusterIndexWritesBlocked` | Disk or heap protection | Resolve root cause of write block before retrying |
| Search queue growing | Search concurrency, slow queries | Tune queries, shards, and scale |
| Write rejections growing | Ingest bursts, indexing pressure | Buffer, backoff, adjust batch sizes, and scale |
| Audit log volume spikes | `GRANTED_PRIVILEGES`/`AUTHENTICATED` categories | Adjust enabled categories and filters |
| Duplicate ingest | At-least-once delivery/retries | Use event IDs or idempotent processing |
| Field mapping conflicts | Same field receiving conflicting types | Standardize schemas, templates, and field versioning |

### 29.1. HTTP 403 Is Not Always IAM

403 errors fall into three buckets:

- IAM request signing or identity policy denies the call.
- Domain access policy denies the principal or HTTP method.
- FGAC authenticates the user, who then lacks cluster/index/document/field privileges.

Inspect the response body, request signer, principal ARN, and role mappings. Never grant `es:*` domain-wide as a quick fix for a 403 error.

### 29.2. Storage and JVM Pressure

When `FreeStorageSpace` nears zero, OpenSearch Service can block writes and throw `ClusterBlockException`. When heap pressure stays high, protection mechanisms block writes to keep the cluster from turning red. Inspect shard counts, fielddata, aggregations, mapping explosions, queues, and node sizing.

Never delete the newest index or an actively used index merely to free disk. Check retention expiration, snapshot/recovery needs, and owners before deleting.

### 29.3. Audit Logs Missing Despite Being Enabled

Audit logging has two halves: publishing `AUDIT_LOGS` to CloudWatch and enabling/configuring audit logging inside OpenSearch. Verify both. Additionally, the configuring user needs the `security_manager` role, the log group needs a resource policy for OpenSearch Service, and the domain must have FGAC enabled.

## 30. Lab: Enabling Log Publishing and Creating Alarms

Run this on a test domain or approved sandbox—never modify a production domain just to experiment.

### Step 1: Inspect the Domain

~~~bash
aws opensearch describe-domain \
  --domain-name orders-search
~~~

Record the domain ARN, endpoint, VPC options, encryption options, and status.

### Step 2: Create Log Groups

~~~bash
aws logs create-log-group \
  --log-group-name /aws/opensearch/orders-search/application

aws logs create-log-group \
  --log-group-name /aws/opensearch/orders-search/search-slow
~~~

Create the resource policy for the OpenSearch service principal using the example above.

### Step 3: Enable Application Logs and Slow Logs

~~~bash
aws opensearch update-domain-config \
  --domain-name orders-search \
  --log-publishing-options '{
    "ES_APPLICATION_LOGS": {
      "CloudWatchLogsLogGroupArn": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/application",
      "Enabled": true
    },
    "SEARCH_SLOW_LOGS": {
      "CloudWatchLogsLogGroupArn": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/search-slow",
      "Enabled": true
    }
  }'
~~~

Wait for the domain to return to `Active`. Configure thresholds on a test index.

### Step 4: Run a Test Query and Inspect Logs

~~~http
PUT logs-lab-000001/_settings
{
  "index.search.slowlog.threshold.query.info": "1ms",
  "index.search.slowlog.threshold.query.warn": "2ms"
}
~~~

Run a search query on the test index, then check CloudWatch Logs for the log stream. Low thresholds are strictly for the lab and must be raised back after verification.

### Step 5: Create an Alarm

Use the `put-metric-alarm` command from the CloudWatch section to monitor `JVMMemoryPressure`. Optionally add alarms for `ClusterStatus.red` and `FreeStorageSpace`.

### Step 6: Verify and Clean Up

- Confirm log streams receive events.
- Confirm metrics receive data points.
- Confirm alarms transition states when test conditions trigger.
- Restore slow log thresholds to operational levels.
- Delete test alarms, log groups, and test indexes when no longer needed.
- Never delete domains or data outside lab scope.

## 31. Production Readiness Checklist

### Ingestion

- [ ] Domain logs and application logs are clearly separated.
- [ ] Ingestion pipeline matches the data source.
- [ ] Logs include UTC timestamps and consistent schemas.
- [ ] Secrets and personal data are filtered/redacted before indexing.
- [ ] Retries, duplicates, and backpressure are handled.
- [ ] Index templates and retention policies are tested.
- [ ] Shard counts reflect index size and query patterns.

### Security

- [ ] Domain resides in a VPC when workloads fit private access.
- [ ] Security groups allow only identified clients.
- [ ] Require HTTPS is enabled.
- [ ] Node-to-node encryption is enabled.
- [ ] Encryption at rest uses managed KMS keys.
- [ ] FGAC is enabled and role mappings are tested.
- [ ] Master user is reserved strictly for administration.
- [ ] Domain access policies and IAM identity policies follow least privilege.
- [ ] CloudWatch log groups have resource policies, encryption, and retention.
- [ ] Audit logs do not unintentionally capture credentials or sensitive payloads.

### Observability

- [ ] Application/error logs are published.
- [ ] Search slow and index slow logs have configured thresholds.
- [ ] Audit logs are enabled in both domain publishing and OpenSearch settings.
- [ ] CloudWatch alarms monitor cluster health, disk, JVM, CPU, and write blocks.
- [ ] Dashboards cover domain, node, and workload health.
- [ ] CloudTrail tracks configuration APIs.
- [ ] EventBridge has rules for critical domain events.
- [ ] Runbooks correlate metrics, logs, and traces by timestamp/request ID.

### Cost and Operations

- [ ] Log group retention aligns with storage policies.
- [ ] Ingest pipeline capacity and cost are tracked.
- [ ] Rollover and deletion plans exist for aged indexes.
- [ ] Owners are assigned per index/log source.
- [ ] Change procedures cover policies, role mappings, and KMS keys.
- [ ] Snapshots/restores and domain recovery are tested.
- [ ] Troubleshooting runbooks cover CloudWatch or OpenSearch log delivery gaps.

## 32. Self-Check Exercises

### Question 1

What is the difference between logs ingested into an OpenSearch domain and logs emitted by the domain?

**Answer:** Ingested logs come from applications/systems that the organization wants to search. Domain-emitted logs are OpenSearch Service's own error logs, slow logs, and audit logs.

### Question 2

What are the four common log publishing types in OpenSearch Service?

**Answer:** `ES_APPLICATION_LOGS`, `SEARCH_SLOW_LOGS`, `INDEX_SLOW_LOGS`, and `AUDIT_LOGS`.

### Question 3

Is enabling `INDEX_SLOW_LOGS` publishing enough to receive slow logs?

**Answer:** No. You must also configure thresholds in index settings so OpenSearch knows which operations qualify as slow.

### Question 4

Why do audit logs require fine-grained access control?

**Answer:** OpenSearch Service audit logs are available only when FGAC is enabled on the domain; configuring audit settings requires the `security_manager` role.

### Question 5

How do a domain access policy and an IAM identity policy differ?

**Answer:** A domain access policy is a resource-based policy gating requests to domain subresources; an IAM identity policy attaches to users/roles and typically governs AWS configuration APIs as well as granted HTTP API permissions.

### Question 6

Can a VPC domain use an IP-based domain access policy?

**Answer:** No. On VPC domains, security groups enforce IP/CIDR network controls.

### Question 7

Can a domain switch directly from a VPC endpoint to a public endpoint?

**Answer:** No. You must create a new domain and migrate data.

### Question 8

Which encryption settings does FGAC require?

**Answer:** HTTPS for all traffic, encryption at rest, and node-to-node encryption.

### Question 9

What traffic does node-to-node encryption protect?

**Answer:** Internal communication between OpenSearch nodes using TLS 1.2.

### Question 10

Can CloudTrail replace OpenSearch audit logs?

**Answer:** No. CloudTrail tracks AWS configuration APIs; audit logs track in-cluster authentication/authorization and request activity.

### Question 11

Which metric reflects Java heap pressure?

**Answer:** `JVMMemoryPressure`; distinguish it from `SysMemoryUtilization`.

### Question 12

In what unit does CloudWatch report `FreeStorageSpace`?

**Answer:** MiB. The OpenSearch console may display GiB.

### Question 13

What does `ClusterIndexWritesBlocked` equal to 1 mean?

**Answer:** The cluster is blocking incoming write requests.

### Question 14

Why shouldn't `GRANTED_PRIVILEGES` and `AUTHENTICATED` audit categories be enabled for every request?

**Answer:** They fire on every authorized request, sharply inflating log volume and cost.

### Question 15

Can CloudWatch Logs subscriptions produce duplicate events?

**Answer:** Yes. Subscriptions use at-least-once delivery semantics, so downstream consumers should handle or deduplicate duplicates.

### Question 16

What technology powers OpenSearch Ingestion?

**Answer:** Data Prepper, a data collector capable of filtering, enriching, transforming, normalizing, and aggregating data.

### Question 17

If a log group has no log streams after enabling publishing, what should you check?

**Answer:** Check the CloudWatch Logs resource policy, the `es.amazonaws.com` principal, log group ARN, domain log publishing options, and domain status.

### Question 18

Why separate log groups for application, slow, and audit logs?

**Answer:** To manage read access, retention, encryption, querying, and cost independently by log purpose.

### Question 19

Does a yellow cluster always mean primary data is lost?

**Answer:** No. Yellow typically means replica shards are unassigned while primary shards remain operational. Still, redundancy is degraded and requires investigation.

### Question 20

When `JVMMemoryPressure` stays high, which root causes should you inspect?

**Answer:** Shard counts, fielddata, mapping explosions, aggregations, wildcard queries, wide time ranges, concurrency, and instance capacity.

## 33. Official Reference Documentation

- [Monitoring OpenSearch logs with Amazon CloudWatch Logs](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/createdomain-configure-slow-logs.html)
- [Monitoring audit logs in Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/audit-logs.html)
- [Monitoring Amazon OpenSearch Service domains](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/monitoring.html)
- [Monitoring OpenSearch cluster metrics with Amazon CloudWatch](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/managedomains-cloudwatchmetrics.html)
- [Recommended CloudWatch alarms for Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/cloudwatch-alarms.html)
- [Identity and Access Management in Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ac.html)
- [Fine-grained access control in Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/fgac.html)
- [Launching OpenSearch Service domains within a VPC](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/vpc.html)
- [Node-to-node encryption for Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ntn.html)
- [Encryption of data at rest for Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/encryption-at-rest.html)
- [Operational best practices for Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/bp.html)
- [Overview of Amazon OpenSearch Ingestion](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ingestion.html)
- [Ingesting application telemetry](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/observability-ingestion.html)
- [Monitoring pipeline logs](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/monitoring-pipeline-logs.html)
- [Loading streaming data from Amazon CloudWatch](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/integrations-cloudwatch.html)
- [Loading streaming data into Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/integrations.html)
- [Real-time processing of log data with CloudWatch Logs subscriptions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Subscriptions.html)
- [Log Amazon OpenSearch Service API calls with CloudTrail](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/monitoring-cloudtrail.html)
- [AWS CloudFormation OpenSearch Service domain resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-opensearchservice-domain.html)

Metric names, features, limits, engine versions, and configuration options vary across OpenSearch versions, service software, and Regions. Before deploying, check current documentation and test on a non-production domain.
