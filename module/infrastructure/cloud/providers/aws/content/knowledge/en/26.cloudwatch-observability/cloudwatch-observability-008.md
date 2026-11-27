# Dashboards by Service and Business Metrics

## Learning Objectives

After this lesson, learners can:

- Explain the role of Amazon CloudWatch dashboards in operational monitoring of AWS and applications.
- Distinguish technical service dashboards from business dashboards tracking customer journeys, transactions, and KPIs.
- Select golden signals—traffic, latency, errors, and saturation—alongside availability, queue lag, dependency health, and cost signals.
- Design metric namespaces, dimensions, units, statistics, periods, and naming conventions so dashboards scale cleanly.
- Use CloudWatch metric widgets, alarm widgets, text widgets, metric math, SEARCH, Metrics Insights, and dashboard variables.
- Build overview dashboards, service dashboards, dependency dashboards, and business-metric dashboards.
- Design KPIs from business events while avoiding misaggregation caused by retries, duplicate events, or metric cardinality.
- Combine CloudWatch metrics, logs, alarms, Application Signals, and traces to investigate incidents.
- Monitor multiple AWS accounts and Regions using cross-account observability and cross-account cross-Region dashboards.
- Manage dashboards via CloudFormation/IaC and govern access permissions, costs, and lifecycle.
- Build dashboards supporting SLO/error budgets, release monitoring, incident response, and capacity planning.
- Test dashboards and diagnose missing/stale metrics, wrong statistics, mismatched dimensions, and misleading charts.

**Module context:** This lesson belongs to the **Observability with CloudWatch** chapter in CLOUD_PROVIDERS_AWS. The module covers AWS Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless. Dashboards must reflect the health of these components while showing how they impact business operations.

> **Scope:** Examples use Amazon CloudWatch Metrics, Dashboards, Alarms, Logs Insights, Metrics Insights, and Application Signals. Namespace, metric, service, Region, and KPI names are illustrative; metric availability/statistics vary by AWS service and telemetry configuration. Check service documentation and your account/Region before deploying.

## 1. Why Do Dashboards Need Two Perspectives: Service and Business?

A dashboard showing only CPU, memory, and request counts cannot tell whether customers can successfully place orders. Conversely, a dashboard showing only daily revenue cannot help on-call engineers identify which API, database, or queue is slowing transactions down.

A strong observability setup has two layers:

- **Service dashboard:** shows whether each technical component is healthy, where requests flow, and which dependency is introducing errors or latency.
- **Business dashboard:** shows whether customer journeys and business outcomes are succeeding, such as checkout success, payment authorization, order completion, and revenue.

~~~mermaid
flowchart TD
    User[Customer journey] --> API[Orders API]
    API --> DB[(Orders database)]
    API --> Q[(SQS order events)]
    Q --> Worker[Order worker]
    Worker --> Pay[Payment provider]
    Worker --> S3[(S3 invoices)]
    API --> Tech[Service metrics / traces / logs]
    DB --> Tech
    Q --> Tech
    Worker --> Tech
    Pay --> Tech
    Tech --> ServiceDash[Service dashboard]
    User --> Events[Business events]
    Events --> BusinessDash[Business KPI dashboard]
    ServiceDash --> Ops[On-call / SRE]
    BusinessDash --> Product[Product / Operations]
~~~

For example, an API may have normal latency while the payment declined rate spikes. Technical dashboards might stay green because HTTP requests succeed, whereas the business dashboard catches conversion dropping. Alternatively, payment success might drop because SQS consumer backlog is growing; both dashboards complement each other to isolate the cause.

## 2. Start from Operational Questions, Not a List of Metrics

Before adding widgets, identify who will use the dashboard and what decisions they need to make.

| User | Question | What the Dashboard Should Include |
| --- | --- | --- |
| On-call engineer | Where is the service failing? | Traffic, latency, errors, saturation, dependencies, alarms |
| Service owner | Did the new release hurt reliability? | SLO, error budget, deploy markers, p95/p99, error rate |
| Product manager | Are customers completing checkout? | Funnel, conversion, orders, payment success, revenue |
| Operations | Are queues and batches keeping up? | Queue age/depth, processing rate, retries, DLQ |
| Platform team | Does infrastructure have enough capacity? | CPU, memory, throttles, connections, quotas |
| Finance/FinOps | Which workloads are driving cost increases? | Usage, request volume, storage, cost signals |

Each dashboard should answer a cohesive set of questions. Cramming every metric from every service onto one screen makes it hard for viewers to separate critical signals from noise.

## 3. Golden Signals for Each Service

Four golden signals commonly used to evaluate services:

1. **Traffic:** volume of requests or operations flowing through the system.
2. **Latency:** processing time; observe p50, p90, p95, or p99 depending on the use case.
3. **Errors:** rate and count of failed requests, including HTTP 5xx, exceptions, throttling, and business failures.
4. **Saturation:** resource utilization or limits preventing the service from accepting additional load.

Supplement these with availability/success rate, dependency latency/error rate, queue age/backlog, retry/throttle rate, resource capacity, connection pools, and SLO/error budget.

### Metric Mapping by AWS Service

| Component | Traffic | Latency | Errors | Saturation / Backlog |
| --- | --- | --- | --- | --- |
| API Gateway | Count | Latency, IntegrationLatency | 4XXError, 5XXError | Throttles, quota |
| Application Load Balancer | RequestCount | TargetResponseTime | HTTPCode_Target_5XX_Count, HTTPCode_ELB_5XX_Count | HealthyHostCount, TargetConnectionErrorCount |
| EC2 | NetworkIn/Out, disk I/O | EBS latency if applicable | StatusCheckFailed | CPUUtilization, CPU credit, memory via agent |
| ECS | RunningTaskCount, task restarts | App request latency | Deployment/task failures | CPUUtilization, MemoryUtilization, desired vs running |
| EKS | Pod/request metrics via Container Insights/Prometheus | API/service latency | Restarts, failed requests | CPU/memory, pending pods, node pressure |
| Lambda | Invocations | Duration | Errors, Throttles | ConcurrentExecutions, AsyncEventAge, IteratorAge by event source |
| SQS | NumberOfMessagesSent/Received/Deleted | — | DLQ messages, oldest message age | ApproximateNumberOfMessagesVisible/NotVisible |
| DynamoDB | ConsumedRead/WriteCapacityUnits | SuccessfulRequestLatency | ThrottledRequests, SystemErrors | Consumed vs provisioned capacity |
| RDS/Aurora | DatabaseConnections, transactions if applicable | Read/WriteLatency | Deadlocks, failed connections, replica lag | CPUUtilization, FreeableMemory, FreeStorageSpace |
| S3 | AllRequests, GetRequests, PutRequests | FirstByteLatency, TotalRequestLatency when request metrics enabled | 4xx/5xx errors | ReplicationLatency if replication metrics enabled |
| SNS | NumberOfMessagesPublished, NumberOfNotificationsDelivered | Delivery latency by protocol | NumberOfNotificationsFailed | Subscription backlog in downstream queues |

Not every metric is available by default. EC2 memory usually requires CloudWatch Agent; S3 request metrics must be enabled; ECS/EKS container metrics depend on Container Insights/Prometheus setup. Always verify actual namespaces, dimensions, and publishing intervals.

## 4. How Do Service Dashboards and Business Dashboards Differ?

| Criterion | Service Dashboard | Business Dashboard |
| --- | --- | --- |
| Unit of observation | Service/resource/API/dependency | Journey, transaction, order, customer action |
| Metric examples | p95 latency, 5xx, CPU, queue age | Checkout conversion, paid orders, revenue |
| Dimensions | Service, Region, AZ, environment, route | Product category, channel, market, payment method |
| Users | SRE, developer, on-call | Product, operations, business owner |
| Cadence | 1 minute or near real-time depending on metric | 1–5 minutes, hourly, or daily |
| Action | Scale, rollback, failover, mitigate | Adjust funnel, payment routing, promotions, operations |

Do not use user ID, order ID, or email as metric dimensions. Detailed transaction identifiers belong in logs/traces or event stores.

## 5. Designing Business KPIs from Business Events

KPIs must be defined with explicit events and formulas before emitting metrics.

~~~mermaid
flowchart LR
    Visit[Checkout started] --> Validate[Address validated]
    Validate --> Pay[Payment authorized]
    Pay --> Order[Order confirmed]
    Order --> Ship[Shipment created]
~~~

| KPI | Definition | Measurement |
| --- | --- | --- |
| Checkout starts | Number of checkouts started | Counter CheckoutStarted |
| Checkout completion | Successful checkouts / checkouts started | OrdersConfirmed / CheckoutStarted |
| Payment authorization success | Authorized payments / authorization attempts | PaymentsAuthorized / PaymentAttempts |
| Order completion time | From checkout start to order confirmed | Histogram/timer or event timestamps |
| Revenue | Total value of paid orders | Sum by currency, after deduplication |
| Refund rate | Refund amount / paid amount | Sum by same currency and window |
| Fulfillment lag | From order confirmed to shipment created | Histogram/percentile |

### Defining the Denominator

A ratio is meaningless without defining its denominator. Payment success rate can be measured over attempts or unique orders; checkout conversion can be measured over sessions, users, or checkout attempts; refund rate can be based on order counts or monetary value.

Explicitly document windows, timezones, currencies, inclusion/exclusion rules, cancellation/refund handling, and retry semantics. Never compare two KPIs that use different denominators.

### Event Schema

A business event should include an event ID, event type, occurred_at, entity ID, schema version, and standardized business dimensions.

~~~json
{
  "event_id": "evt-01JABC",
  "event_type": "order.confirmed",
  "occurred_at": "2026-11-20T03:15:00Z",
  "schema_version": 2,
  "market": "VN",
  "channel": "web",
  "currency": "VND",
  "amount_minor": 12500000
}
~~~

Do not emit metrics directly on every SQS delivery if messages can be delivered more than once. Deduplicate by event ID or emit metrics from an idempotent data source.

## 6. Metric Namespace, Name, and Dimensions

CloudWatch custom metrics are grouped by namespace. Each metric has a name and a set of dimensions. A metric identity consists of namespace, metric name, and the full dimension set.

~~~text
Namespace: MyCompany/Commerce
Metric: OrdersConfirmed
Dimensions:
  Environment=prod
  Region=ap-southeast-1
  Channel=web
Unit: Count
~~~

| Component | Rule |
| --- | --- |
| Namespace | Organization/domain name, e.g., MyCompany/Commerce |
| Metric name | Describes the event/measurement, e.g., OrdersConfirmed |
| Dimensions | Bounded values such as Environment, Channel, Market |
| Unit | Consistent: Count, Milliseconds, Bytes, Percent, None |
| Timestamp | When the event/measurement occurred |
| Storage resolution | Standard or high-resolution as needed |
| Period | Aggregation interval matching publishing interval |

CloudWatch does not automatically treat metrics with different dimensions as the same time series. OrdersConfirmed with Environment=prod is a different metric from the same name with Environment=dev. Every dimension combination creates a distinct metric variant and affects metric counts and costs.

Never create dimensions for OrderId, UserId, RequestId, raw URLs, or exception messages. Those values cause high cardinality, increase costs, and complicate queries.

## 7. Measuring Business Metrics with Embedded Metric Format (EMF)

Embedded Metric Format allows applications/workers to write structured JSON logs containing metric directives. CloudWatch Logs extracts metrics from the log events into custom metrics.

Example EMF log:

~~~json
{
  "_aws": {
    "Timestamp": 1795144500000,
    "CloudWatchMetrics": [
      {
        "Namespace": "MyCompany/Commerce",
        "Dimensions": [["Environment", "Channel", "Currency"]],
        "Metrics": [
          {"Name": "OrdersConfirmed", "Unit": "Count"},
          {"Name": "RevenueMinor", "Unit": "None"}
        ]
      }
    ]
  },
  "Environment": "prod",
  "Channel": "web",
  "Currency": "VND",
  "OrdersConfirmed": 1,
  "RevenueMinor": 12500000
}
~~~

This example represents one confirmed order. For revenue, ensure:
- Emit only once for a confirmed business transition;
- Deduplicate events before summing;
- Never add VND, USD, and other currencies into the same total;
- Clearly document amount_minor units and currency;
- Choose dimensions carefully to avoid excessive time series.

EMF works well for metrics from Lambda, ECS workers, and log-based applications. If using CloudWatch Agent/Fluent Bit, verify the log pipeline forwards intact JSON events and the EMF parser is enabled.

## 8. Statistic and Period: Interpreting Displayed Numbers Accurately

| Statistic | Meaning | When to Use |
| --- | --- | --- |
| Sum | Total of values in period | Request counts, events, bytes |
| Average | Mean value | CPU utilization, average duration |
| Minimum/Maximum | Lowest/highest value | Capacity floor/peak |
| SampleCount | Number of published samples | Verifying measurement volume |
| p50/p90/p95/p99 | Percentile | Latency distribution when supported by metric |

A common mistake is using Average on a counter and interpreting it as total orders. Counters usually require Sum. Latency usually requires p95/p99 rather than Average alone because tail latency impacts users.

### Period and Publishing Interval

- Period must match how often the metric is published.
- Standard-resolution metrics typically have a minimum granularity of 1 minute.
- High-resolution custom metrics can be published at 1-, 5-, 10-, or 30-second resolution; querying/display depends on widget/API limits.
- In a dashboard body, a metric widget's period property must be a multiple of 60 seconds and at least 60 seconds. Do not assume a high-resolution metric will always render on dashboard graphs at sub-minute intervals.
- Some AWS service metrics publish only on 1-minute or 5-minute intervals.
- Periods that are too short produce gaps or missing data points; periods too long obscure spikes and recovery times.

When comparing multiple metrics, ensure statistics and periods align semantically. Do not sum or average per-instance Averages to infer a fleet-wide average without weighting by request/sample counts.

Percentiles require appropriate distribution/raw samples. Standard statistic sets generally lack enough information to compute exact percentiles, except special cases like SampleCount=1 or Min=Max.

## 9. Metric Math for KPIs and Service Health

Metric math combines multiple time series to produce a graph or metric expression.

\[
ErrorRate(\%) = 100 \times \frac{5xx}{RequestCount}
\]

\[
PaymentSuccess(\%) = 100 \times \frac{Authorized}{Attempted}
\]

\[
RevenuePerOrder = \frac{RevenueSum}{OrdersConfirmedSum}
\]

Suppose a widget defines m1 as HTTP 5xx Sum and m2 as RequestCount Sum. Expression:

~~~text
IF(m2 > 0, 100 * m1 / m2, 0)
~~~

Label it 5xx rate (%), format as percentage, and display alongside request volume. When the denominator is 0, the expression returns 0 to avoid math errors, yet viewers must distinguish "no traffic" from "healthy service." Display traffic separately and configure explicit no-data behavior for alarms.

| Goal | Expression/Idea |
| --- | --- |
| Success rate | 100 * success / attempts |
| Error rate | 100 * errors / requests |
| Requests per second | requests_sum / PERIOD(requests) |
| Fleet total | SUM(METRICS()) over matching metric set |
| Queue age | MAX(queue_age) |
| Capacity ratio | 100 * consumed / provisioned |
| Revenue per order | revenue_sum / orders_sum |

Metric math must combine metrics with compatible units and aggregation semantics. Never average per-instance percentages to derive a fleet-wide percentage; sum the numerators and denominators first, then divide.

## 10. SEARCH and Metrics Insights for Dynamic Dashboards

As services and resources multiply, creating a dedicated metric widget for every resource becomes unmanageable.

### SEARCH Expressions

CloudWatch SEARCH discovers metrics by namespace, metric name, and dimensions. Example:

~~~text
SEARCH('{AWS/ApiGateway,ApiName} MetricName="Count"', 'Sum')
~~~

Search expressions can dynamically match multiple API names sharing a namespace/dimension pattern. Search expressions return multiple time series; dashboards automatically display new series as matching metrics are published.

Limits to remember:
- SEARCH only finds metrics that reported data within the past two weeks;
- Queries must match the namespace/dimension schema;
- Each graph has limits on search expressions and time series;
- Overly broad queries slow down dashboards and hurt readability;
- Not every expression is supported in all alarm contexts.

### Metrics Insights

Metrics Insights uses SQL-like queries to analyze CloudWatch metrics with dimensions, filtering, grouping, and aggregation.

Example finding the top 10 EC2 instances by CPU:

~~~sql
SELECT AVG(CPUUtilization)
FROM SCHEMA("AWS/EC2", InstanceId)
GROUP BY InstanceId
ORDER BY AVG() DESC
LIMIT 10
~~~

The schema must match the metric's dimensions. If metrics lack the InstanceId dimension specified in the query, results will be empty.

Metrics Insights fits top-N resource rankings by CPU/latency/errors, comparing workloads across environments, finding high queue age/throttles, and breaking down custom metrics by channel/market.

A Metrics Insights query can process up to 10,000 metrics and return up to 500 time series. Visualization queries cover up to two weeks of data; Metrics Insights does not support sub-minute high-resolution data. Use ORDER BY when intentionally selecting top-N series.

## 11. Dashboard Widgets: Choosing the Right Visual for the Goal

CloudWatch dashboard bodies support the following widget types:

| Widget Type | Usage |
| --- | --- |
| metric | Graph metrics, metric math, SEARCH, and Metrics Insights |
| alarm | Single alarm with graph or multi-alarm status view |
| log | CloudWatch Logs Insights query |
| text | Markdown, owner info, guidance, and runbook links |
| explorer | Metrics Explorer filtered by tags/resource properties |
| chart | Visualization/chart per supported schema |

Metric graphs can render as line, stacked area, number, gauge, bar, or pie.

Avoid pie charts with dozens of categories; avoid gauges for metrics without meaningful bounds; avoid plotting too many line series on a single chart.

### Suggested Layout

1. Top row: KPIs and alarm status;
2. Second row: traffic, p95/p99 latency, error rate;
3. Third row: saturation, dependency latency, queue backlog;
4. Bottom row: logs/traces links, deployment markers, and runbooks.

## 12. Dashboard Variables: One Dashboard for Multiple Environments

Dashboard variables let viewers switch dimension values without duplicating dashboards for dev/stage/prod or multiple services.

Two main types:

- **Property variable:** changes the value of a JSON property in the dashboard, such as region or a metric dimension.
- **Pattern variable:** uses a regular expression to replace part or all of a JSON property.

Variables can target Environment, FunctionName, InstanceId, Cluster, or Region depending on metric schemas. Variables can pull values from metric property searches or configured lists.

Guidelines:
- Set a safe default value and clearly display the active scope;
- Do not share one variable across widgets with incompatible dimension schemas;
- Test every widget when switching variable values;
- Constrain values and avoid overly broad queries;
- On incident dashboards, prevent filters from accidentally hiding critical services.

Dashboard variables promote layout reuse; they do not reduce custom metric costs or telemetry ingestion.

## 13. Dashboard Body in JSON

CloudWatch dashboards are defined as a JSON body. They can be created via console, AWS CLI, SDK, or CloudFormation.

Example dashboard with metric widgets and an alarm widget:

~~~json
{
  "widgets": [
    {
      "type": "metric",
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Orders API request count and p95 latency",
        "view": "timeSeries",
        "region": "ap-southeast-1",
        "period": 60,
        "metrics": [
          ["AWS/ApiGateway", "Count", "ApiName", "orders-api", {"stat": "Sum", "id": "requests", "yAxis": "left"}],
          [".", "Latency", ".", ".", {"stat": "p95", "id": "latency", "yAxis": "right"}]
        ],
        "yAxis": {
          "left": {"label": "Requests"},
          "right": {"label": "Milliseconds"}
        },
        "annotations": {
          "horizontal": [
            {"label": "Latency objective", "value": 500, "yAxis": "right"}
          ]
        }
      }
    },
    {
      "type": "metric",
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Orders confirmed by channel",
        "view": "timeSeries",
        "region": "ap-southeast-1",
        "period": 300,
        "metrics": [
          ["MyCompany/Commerce", "OrdersConfirmed", "Environment", "prod", "Channel", "web", {"stat": "Sum", "id": "web"}],
          [".", ".", ".", ".", ".", "mobile", {"stat": "Sum", "id": "mobile"}]
        ]
      }
    },
    {
      "type": "alarm",
      "width": 12,
      "height": 4,
      "properties": {
        "alarms": [
          "arn:aws:cloudwatch:ap-southeast-1:111122223333:alarm:OrdersApiHighErrorRate"
        ]
      }
    }
  ]
}
~~~

This structure is illustrative; metric dimensions and statistics must exist in your account. Percentile latency requires metric data that supports percentiles. Metric widgets require an explicit Region; for cross-account metrics, set accountId on the widget or individual metrics.

### Creating a Dashboard via CLI

~~~bash
aws cloudwatch put-dashboard \
  --dashboard-name Orders-Operations \
  --dashboard-body file://dashboard.json
~~~

CloudWatch dashboards are account-global rather than tied to a single Region; each metric widget specifies the Region of the metrics to display. One dashboard can combine widgets from multiple Regions.

PutDashboard replaces the entire body of a dashboard with that name. If multiple teams edit the same dashboard, one deploy can overwrite another team's changes. Manage ownership, code reviews, and deployment serialization carefully.

PutDashboard returns validation messages: warnings indicate the dashboard saved while some elements may not render; errors fail the operation. Pipelines must inspect the response body, not merely HTTP 200.

## 14. Managing Dashboards with CloudFormation/IaC

Dashboards can be managed as infrastructure resources:

~~~yaml
Resources:
  OrdersOperationsDashboard:
    Type: AWS::CloudWatch::Dashboard
    Properties:
      DashboardName: Orders-Operations
      DashboardBody: |
        {
          "widgets": [
            {
              "type": "metric",
              "width": 12,
              "height": 6,
              "properties": {
                "title": "Orders API errors",
                "region": "ap-southeast-1",
                "period": 60,
                "metrics": [
                  ["AWS/ApiGateway", "5XXError", "ApiName", "orders-api", {"stat": "Sum"}]
                ]
              }
            }
          ]
        }
~~~

Benefits:
- Dashboards are version-controlled and reviewed via pull requests;
- Dashboard updates ship alongside service releases and configs;
- Deployable within the same stack or CI pipeline;
- Easy to standardize dashboards across services and teams;
- Distributable via pipelines or StackSets.

Validate JSON after template rendering. When using Fn::Sub, watch out for pseudo-parameter placeholders inside the dashboard body so CloudFormation does not substitute them unintentionally.

## 15. Cross-Account and Cross-Region Dashboards: Distinguishing Two Mechanisms

CloudWatch provides two related but distinct mechanisms.

**Cross-account observability via OAM:**
- Centralizes metrics, logs, traces, and Application Signals from source accounts into a monitoring account;
- Supports searching/analyzing telemetry across accounts within the same Region;
- Does not turn an OAM link into a cross-Region link;
- Best for centralized observability within a single Region.

**Cross-account cross-Region dashboards/console:**
- Dashboards can display metrics from multiple accounts and Regions using accountId/region selectors;
- Can leverage cross-account cross-Region console integration;
- This console capability does not provide cross-account cross-Region Logs visibility and does not support creating alarms in a monitoring account watching metrics in another Region;
- Best when a single overview dashboard spanning multiple Regions and accounts is needed.

~~~mermaid
flowchart TD
    subgraph SameRegion[Single-Region OAM cross-account]
      S1[Source account A] --> OAM[OAM sink / links]
      S2[Source account B] --> OAM
      OAM --> M[Monitoring account]
      M --> T[Metrics / logs / traces / SLOs]
    end
    subgraph MultiRegion[Cross-account / cross-Region dashboard]
      R1[Account A / Region 1] --> D[Central dashboard]
      R2[Account B / Region 2] --> D
    end
~~~

When designing a central dashboard:
- Identify the monitoring account and source accounts;
- Choose the right sharing mechanism for single-Region vs. multi-Region needs;
- Grant IAM permissions to viewers;
- Ensure metric widgets carry accurate account/Region context;
- Display account/Region in titles or labels;
- Avoid sharing sensitive logs/traces outside authorized boundaries.

## 16. Alarms, Anomaly Detection, and SLOs on Dashboards

Dashboards should show both trends and actionable status.

### Alarm Widgets

Surface critical alarm states: API 5xx rate, p95 latency, queue oldest message age, Lambda errors/throttles, database connections/CPU/free storage, and business checkout/payment success rates.

### Anomaly Detection

CloudWatch anomaly detection builds an expected band from historical metric patterns. Bands can be overlaid on metric graphs and used as thresholds for anomaly detection alarms.

Avoid blindly applying anomaly detection to metrics with erratic seasonality, low traffic, or rare events. Inspect training windows, excluded time ranges, and threshold behavior.

### SLOs

An SLO should define its SLI, objective (for example, 99.9% successful requests over rolling 30 days), measurement window, good/bad events, error budget, and burn-rate alerting.

CloudWatch Application Signals supports service-level objectives and service operations when onboarded and configured. Dashboards can display related metrics/alarms and link to Application Signals service maps and SLO views.

## 17. Service Dashboard Example: Orders API

A service dashboard should be organized into sections:

| Section | Metrics |
| --- | --- |
| Health | Availability, 5xx rate, alarms, deployment status |
| Traffic | RequestCount, requests/sec, orders started |
| Latency | p50/p95/p99, integration latency |
| Saturation | CPU/memory, DB pool, thread pool |
| Dependencies | RDS latency, SQS send errors, payment API |
| Queue | Visible/NotVisible, oldest age, DLQ |
| Business | Checkout started, orders confirmed, payment success |

Dashboards should share a synchronized time range when comparing a service and its dependencies. Add annotations/markers for deployments, config changes, and incident windows to spot temporal correlations.

A service-wide p95 can hide a single failing Region or endpoint. Include total traffic, breakdowns by Region and route template/operation, top dependencies, and alarm states per critical component.

Never group by raw URLs containing IDs; use route templates such as /orders/{id}.

## 18. Business Dashboard Example: Checkout Funnel

Business dashboards should be driven by deduplicated business events.

| KPI | Metric | Statistic | Dimensions |
| --- | --- | --- | --- |
| Checkout started | CheckoutStarted | Sum | Environment, Channel, Market |
| Orders confirmed | OrdersConfirmed | Sum | Environment, Channel, Market |
| Payment attempts | PaymentAttempts | Sum | Environment, PaymentMethod |
| Payment authorized | PaymentsAuthorized | Sum | Environment, PaymentMethod |
| Refund amount | RefundAmountMinor | Sum | Environment, Currency |
| Fulfillment delay | FulfillmentLag | p95 | Environment, Market |

Ratio KPIs can be calculated via metric math. Keep revenue separated by currency or normalize to a base currency with an explicit exchange-rate timestamp and source.

Business dashboards should show current period vs. prior comparable period, hourly/daily trends, conversion funnels, payment success by method, revenue by currency/market, refund/cancellation rates, fulfillment backlog/lag, and data freshness/last event timestamp.

A metric equal to 0 differs from a metric with no data. Dashboards should make no-data and stale-data states explicit so product/operations teams do not mistake missing events for zero activity.

## 19. Combining Dashboards with Logs Insights and Traces

When metrics show rising errors, dashboards should provide direct paths to logs and traces.

Workflow:
1. Select the time range containing the spike;
2. Inspect metrics by Region, service, and route;
3. Open the firing alarm and review its threshold/reason;
4. Open a Logs Insights query covering the same time window;
5. Filter by controlled trace IDs or request IDs;
6. Open trace/service maps to inspect dependency latency;
7. Cross-reference deployment markers and stack events.

Example Logs Insights query for application errors:

~~~sql
fields @timestamp, @message, traceId, service, level
| filter level = "ERROR"
| sort @timestamp desc
| limit 100
~~~

Field names depend on your structured log schema and ingestion pipeline. For JSON logs, CloudWatch Logs Insights can auto-discover fields; otherwise, apply a parse matching your format.

Dashboard log widgets can run saved queries or inline queries. Keep query scopes and time ranges bounded to avoid overly expensive scans during incidents.

## 20. Dashboard Variables and Cross-Service Drill-Down

Use dashboard variables to switch environments/services/Regions and keep drill-downs consistent.

Example:
- An overview dashboard has an Environment variable;
- A link navigates to Orders-API-Detail;
- The detail dashboard preserves the same Environment, Region, and time range;
- Alarm widgets show alarms for the selected service.

Links should preserve context and point only to authorized dashboards or log groups. Never embed credentials, signed URLs, or raw customer identifiers in dashboard links.

## 21. Dashboards for Serverless and Event-Driven Workloads

Serverless workloads require visibility into both function execution and event delivery.

| Component | Important Metrics |
| --- | --- |
| Lambda | Invocations, Duration p95/p99, Errors, Throttles, ConcurrentExecutions, IteratorAge for streams |
| SQS | Visible/NotVisible, ApproximateAgeOfOldestMessage, Sent/Received/Deleted, DLQ |
| SNS | Published, Delivered, Failed notifications |
| EventBridge | Invocations, FailedInvocations, ThrottledRules, DLQ |
| Step Functions | ExecutionsStarted/Succeeded/Failed/TimedOut, ExecutionTime |
| API Gateway | Count, Latency, IntegrationLatency, 4XX/5XX, Throttles |

For SQS → Lambda event source mappings, view queue age and Lambda errors side by side. Lambda Errors alone do not reveal all retried messages; check queue age, receive counts, DLQ depth, and event source mapping behavior.

For Step Functions, distinguish Standard vs. Express workflow metric/logging semantics. Dashboards should show failed/timed-out executions and execution duration, not just executions started.

## 22. Dashboards for Databases and Storage

| Service | Metrics to Track | Business Impact |
| --- | --- | --- |
| RDS/Aurora | CPU, FreeableMemory, FreeStorageSpace, DatabaseConnections, Read/WriteLatency, replica lag | Slow checkout/API, transaction failures |
| DynamoDB | ConsumedRead/WriteCapacity, ThrottledRequests, SuccessfulRequestLatency | Request retries, slow order lookups |
| S3 | 4xx/5xx, request metrics, replication metrics, storage bytes | Upload/download failures, missing invoices |
| EBS | VolumeQueueLength, BurstBalance/IOPS, throughput | Database/application disk latency |
| EFS | PercentIOLimit, BurstCreditBalance, throughput | Slow shared file access |

Metric availability and names vary by engine, storage class, feature, and monitoring setup. RDS Enhanced Monitoring/Database Insights provide deeper detail than basic metrics; S3 request metrics require configured filters.

## 23. Dashboards for Capacity, Releases, and Reliability

### Capacity Dashboard

- ECS desired/running task count;
- EKS node/pod capacity and pending pods;
- Lambda concurrency/throttles;
- RDS connections/CPU/free storage;
- DynamoDB consumed/provisioned capacity;
- SQS oldest message age;
- EC2 CPU credits, network throughput, EBS queue.

### Release Dashboard

- Deployment events/markers;
- Pre-/post-deploy error rates;
- p95/p99 latency;
- Task/pod restarts;
- Rollback count;
- Business KPI delta;
- Alarm states and smoke test status.

### Reliability Dashboard

- SLO attainment;
- Remaining error budget;
- Burn rate;
- Availability by Region;
- Dependency health;
- Incident count/MTTR;
- Data freshness.

Dashboards need appropriate time ranges. A 30-day SLO cannot be evaluated from a 1-hour chart, whereas a release regression needs a window spanning minutes before and after deployment.

## 24. Designing Dashboards for Multi-Region Resilience

For multi-Region applications, dashboards must distinguish global experience from each individual Region.

| View | Metrics |
| --- | --- |
| Global | Request count, success rate, traffic-weighted latency aggregation |
| Region A | API 5xx, p95, database lag, queue age |
| Region B | API 5xx, p95, database lag, queue age |
| Failover | Route/health check state, traffic shift, replication lag |
| Recovery | Backlog drain rate, data replication catch-up, error budget |

Never average latencies across Regions without weighting by traffic. A low-traffic Region experiencing severe latency can be masked by a high-traffic Region. Display each Region individually alongside traffic-weighted global aggregates.

## 25. Dashboard Sharing, IAM, and Sensitive Data

CloudWatch dashboards can be shared via the AWS Console or public sharing depending on enabled features and permissions. Public dashboards can expose operational details, resource names, traffic patterns, and business KPIs.

Controls:
- cloudwatch:GetDashboard, cloudwatch:ListDashboards, cloudwatch:PutDashboard, cloudwatch:DeleteDashboards;
- Metrics/logs/traces permissions needed for displayed data;
- OAM sharing permissions for cross-account observability;
- KMS/Logs access policies when querying logs;
- Dashboard sharing policies and approved viewers;
- Never put customer PII, secrets, or private endpoint details into text widgets.

Dashboards do not grant underlying data access by themselves. Viewers must hold required permissions for the underlying metrics, logs, traces, and source accounts.

## 26. Dashboard Costs and Performance

Dashboard metric widgets consume API/query capacity and may pull metrics across multiple accounts and Regions. Certain features/queries carry dedicated pricing or quotas.

Optimizations:
- Limit unnecessary widgets and time series;
- Use targeted filters and grouping in SEARCH/Metrics Insights;
- Do not query hundreds of dimensions when only top-N is needed;
- Match periods to metric resolution;
- Reduce custom metric cardinality;
- Do not enable detailed monitoring/request metrics without a use case;
- Use dashboard variables to reuse layouts;
- Review dashboard usage and quotas at scale.

Costs extend beyond the dashboard itself. Custom metrics, high-resolution metrics, alarms, log ingestion/storage/queries, Application Signals, and traces often make up most of the bill. Designing metrics cleanly before emitting them has greater long-term impact than merely trimming widgets.

## 27. Deploying Dashboards with AWS CLI and SDK

### AWS CLI

~~~bash
aws cloudwatch put-dashboard \
  --dashboard-name Orders-Operations \
  --dashboard-body file://dashboard.json

aws cloudwatch get-dashboard \
  --dashboard-name Orders-Operations

aws cloudwatch list-dashboards \
  --dashboard-name-prefix Orders
~~~

### AWS SDK for Java 2.x

~~~java
import software.amazon.awssdk.services.cloudwatch.CloudWatchClient;
import software.amazon.awssdk.services.cloudwatch.model.PutDashboardRequest;

public class DashboardPublisher {

    private final CloudWatchClient cloudWatch;

    public DashboardPublisher(CloudWatchClient cloudWatch) {
        this.cloudWatch = cloudWatch;
    }

    public void publish(String name, String dashboardBody) {
        cloudWatch.putDashboard(PutDashboardRequest.builder()
            .dashboardName(name)
            .dashboardBody(dashboardBody)
            .build());
    }
}
~~~

The SDK/CLI identity needs cloudwatch:PutDashboard. Reading back requires cloudwatch:GetDashboard; listing requires cloudwatch:ListDashboards.

PutDashboard overwrites the entire dashboard of that name. Pipelines should generate one complete dashboard body, validate the JSON, and deploy atomically rather than letting multiple writers race with partial edits.

## 28. Testing Dashboards Before Release

Dashboards are part of operations and should be verified alongside IaC and service releases.

Checklist:
- Dashboard JSON parses cleanly;
- All metric namespaces, names, and dimensions exist;
- Statistics and periods match metric publishing intervals;
- Metric math expressions reference valid IDs;
- Variables update all widgets properly;
- Cross-account/Region selectors display intended sources;
- Alarm widgets reference valid ARNs;
- Logs Insights queries use valid field names;
- Links open the intended dashboards/runbooks;
- Dashboards expose no secrets or PII;
- Data freshness/no-data states are visible;
- Widget layout is legible on target screens.

A dashboard can be created without errors while widgets render blank due to dimension mismatches, unemitted metrics, wrong Regions, or missing permissions. Validate dashboards in an account with real telemetry and synthetic test data before production.

## 29. Troubleshooting Dashboards

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Widget shows no data | Wrong namespace/name/dimensions or metric not emitted | Open Metrics console and verify exact dimension set |
| Metric appears delayed | Publishing interval or ingestion delay | Increase period/time range, check emitter |
| Counter unusually low | Using Average instead of Sum, or lost/duplicated events | Switch to Sum and inspect event pipeline |
| p95/p99 missing | Metric publishes statistic sets not supporting percentiles | Publish raw samples or appropriate distributions |
| Error rate shows 0 with no traffic | IF expression returns 0 when denominator=0 | Display request volume and no-data state separately |
| SEARCH finds no metrics | No recent data points or wrong schema filter | Verify namespace, dimensions, and time range |
| Metrics Insights query empty | SCHEMA does not match metric dimensions | Verify metric schema and Region |
| Dashboard variable fails to filter widget | Wrong variable property or pattern | Inspect variable source and metric dimensions |
| Cross-account widget empty | Missing OAM link/sink or sharing permissions | Verify source/monitoring accounts and sharing |
| Cross-Region widget wrong | Incorrect widget region property | Set explicit Region on each widget |
| Alarm widget fails to display | Wrong ARN or viewer lacks alarm permissions | Check account, Region, ARN, and IAM |
| Logs widget empty | Wrong query field names or time range | Test query in Logs Insights first |
| Dashboard overwrote another team's changes | PutDashboard replaces full body | Enforce single owner/pipeline, reviews, and serialization |
| Business revenue incorrect | Mixed currencies, duplicate events, or wrong refund semantics | Normalize currencies, dedupe, and align KPI contract |
| KPI stale yet chart still renders | Missing freshness metric or last-event timestamp | Add a data freshness widget and alarm |
| Widget slow or too many series | Overly broad SEARCH/query or high cardinality | Filter, limit to top-N, reduce dimensions/time range |

### Investigation Workflow

~~~text
1. Confirm dashboard name, account, Region, and time range.
2. Open one metric widget and check namespace, name, and dimension set.
3. Verify the metric has recent data points in the Metrics console.
4. Check statistic, period, unit, and y-axis.
5. Verify metric math IDs and denominators.
6. For SEARCH/Metrics Insights, run the query standalone and narrow filters.
7. Check dashboard variables and account/Region context.
8. Verify IAM/OAM permissions for the data sources.
9. Check CloudWatch Logs Insights queries and field extraction.
10. Reconcile business event sources, deduplication, and freshness.
11. Inspect dashboard validation messages and API responses.
12. Fix dashboard source in Git/IaC and redeploy.
~~~

## 30. Lab: Building a Dashboard for Orders Service and Checkout KPIs

### Scenario

An e-commerce application running in ap-southeast-1 includes API Gateway, Orders API, SQS, a Lambda worker, DynamoDB, and a payment provider. The team needs one dashboard serving both on-call and product operations.

### Step 1 — Lock Down the KPI Contract

| KPI | Definition | Source |
| --- | --- | --- |
| Checkout starts | Count of deduplicated checkout_started events | EMF/business events |
| Orders confirmed | Count of order_confirmed events | EMF |
| Payment success | authorized / attempted | EMF |
| Revenue | Sum of amount_minor in VND | Paid order events |
| Queue lag | ApproximateAgeOfOldestMessage | SQS |
| API errors | 5xx / requests | API Gateway |
| API p95 | p95 Latency | API Gateway |

Document event IDs, currency, timezone, event timestamps, and deduplication rules. Never calculate revenue by summing raw message deliveries.

### Step 2 — Emit an EMF Log Event

~~~json
{
  "_aws": {
    "Timestamp": 1795144500000,
    "CloudWatchMetrics": [
      {
        "Namespace": "MyCompany/Commerce",
        "Dimensions": [["Environment", "Channel", "Market"]],
        "Metrics": [
          {"Name": "OrdersConfirmed", "Unit": "Count"}
        ]
      }
    ]
  },
  "Environment": "prod",
  "Channel": "web",
  "Market": "VN",
  "OrdersConfirmed": 1
}
~~~

Ensure the log pipeline forwards the intact JSON event to CloudWatch Logs and the EMF parser extracts it into a custom metric.

### Step 3 — Build the Dashboard JSON

Start from the JSON example in section 13, adding widgets for SQS queue age, Lambda errors, DynamoDB throttles, and business counters. Match periods to publishing intervals and use Sum for counters.

### Step 4 — Deploy

~~~bash
aws cloudwatch put-dashboard \
  --dashboard-name Orders-Operations \
  --dashboard-body file://dashboard.json
~~~

### Step 5 — Verify

- Create a test order;
- Confirm one OrdersConfirmed event is logged;
- Confirm the metric Sum increments by exactly one;
- Simulate a payment failure in sandbox;
- Verify payment success rate and SQS age;
- Locate traces/logs in the same time range;
- Confirm the dashboard exposes no PII;
- Re-check after switching Environment or Region variables.

### Step 6 — Write the Runbook

The runbook should document the dashboard owner, KPI definitions/sources, critical alarms/thresholds, links to Logs Insights/trace search, service dependencies, rollback/mitigation actions, escalation contacts, and last validated timestamp.

## 31. Exercises and Self-Check Questions

### Exercise 1 — Service Dashboard

Orders API shows normal request counts, yet p99 latency is climbing and SQS oldest message age is rising.

**Prompt:** Select widgets, dimensions, and time ranges; explain how to determine whether the bottleneck is in the API, a downstream dependency, or consumer backlog.

### Exercise 2 — Business KPIs

Checkout starts = 1,000, orders confirmed = 720, payment attempts = 800, authorized = 760.

**Prompt:** Compute checkout conversion and payment authorization success; explain why the two ratios have different denominators and which events must be deduplicated.

### Exercise 3 — Metric Math

A widget contains 5xx Sum and RequestCount Sum.

**Prompt:** Write an expression for error rate handling a zero denominator and explain why request volume should be displayed alongside the rate.

### Exercise 4 — EMF

A worker consumes an SQS Standard queue with at-least-once delivery. It emits OrdersConfirmed every time it receives a message.

**Prompt:** Explain why the metric gets double-counted; design event ID/deduplication and emit the metric only once a business state transition is durable.

### Exercise 5 — Multi-Account Dashboard

An organization has tooling, dev, staging, and production accounts across two Regions.

**Prompt:** Design the monitoring account, OAM links, cross-account cross-Region dashboard, IAM viewers, and account/Region selectors; identify data access boundaries.

### Exercise 6 — Change Management

Two teams both use PutDashboard to update the Orders-Operations dashboard.

**Prompt:** Explain why one team can overwrite the other; propose single ownership, Git/IaC, code reviews, and deployment serialization.

### Exercise 7 — SLO

Orders API has an objective of 99.9% successful requests over a rolling 30-day window.

**Prompt:** Define good/bad SLI events, error budget, burn-rate alerts, and dashboard widgets to display.

### Exercise 8 — Metrics Insights

You need to find the top 10 EC2 instances by CPU utilization in production.

**Prompt:** Write the Metrics Insights query, verify SCHEMA dimensions, and explain query limits when metrics lack InstanceId.

### Short Questions

1. **How do a service dashboard and a business dashboard differ?** One tracks service health; the other measures customer/business journey outcomes.
2. **What are the golden signals?** Traffic, latency, errors, and saturation.
3. **Which statistic should counters use?** Sum.
4. **Which statistic should latency inspect?** p95/p99 alongside average when appropriate.
5. **What defines a CloudWatch metric identity?** Namespace, metric name, and the complete dimension set.
6. **What does high dimension cardinality cause?** More metric variants, higher costs, and harder analysis.
7. **What is EMF used for?** Extracting custom metrics from structured CloudWatch Logs events.
8. **Should business counters be emitted on every SQS delivery?** No if messages can be redelivered; deduplicate first.
9. **What is metric math used for?** Combining time series to calculate KPIs, rates, and ratios.
10. **Does SEARCH find metrics never published?** No; metrics must have matching recent data.
11. **What language does Metrics Insights use?** An SQL-like query language.
12. **What do dashboard variables help with?** Reusing dashboards across multiple dimensions/environments.
13. **Does PutDashboard append widgets or replace the body?** It replaces the dashboard body for that name.
14. **Are CloudWatch dashboards account-global?** Yes; dashboards are not bound to one Region, while individual widgets select Regions.
15. **Within what scope does OAM cross-account observability operate?** Sharing supported telemetry—metrics, logs, traces—across accounts in the same Region.
16. **When are cross-account cross-Region dashboards used?** When aggregating metrics from multiple accounts and Regions is needed.
17. **Does no data equal zero?** No.
18. **Is anomaly detection suitable for every metric?** No; it requires suitable history/seasonality and threshold semantics.
19. **What components does an SLO require?** SLI, objective, window, good/bad events, and error budget.
20. **Do dashboards automatically grant permission to view logs/metrics?** No; viewers need permissions on the underlying data sources.
21. **How should multi-currency revenue KPIs be handled?** Separate by currency or normalize using an explicit FX source and timestamp.

## 32. Pre-Production Checklist

- [ ] Dashboard has an owner, audience, purpose, and runbook.
- [ ] Service dashboard shows traffic, latency, errors, saturation, and dependencies.
- [ ] Business dashboard documents KPI contracts, denominators, windows, timezones, and currencies.
- [ ] Business events are deduplicated/idempotent before emitting counters.
- [ ] Metric namespaces, names, dimensions, and units are standardized.
- [ ] No PII or high-cardinality identifiers are used as dimensions.
- [ ] Counters use Sum; latency uses percentiles where supported.
- [ ] Periods match metric publishing intervals/resolutions.
- [ ] Metric math handles zero traffic/no data explicitly.
- [ ] SEARCH/Metrics Insights queries have appropriate filters and limits.
- [ ] Dashboard variables are tested across all widgets.
- [ ] Account/Region context is explicit for cross-account/cross-Region views.
- [ ] Alarms/SLOs/anomaly bands have clear thresholds, owners, and actions.
- [ ] Logs Insights/trace links use valid fields and permissions.
- [ ] Dashboard JSON is validated and managed via Git/IaC.
- [ ] PutDashboard ownership is serialized to prevent lost updates.
- [ ] IAM/OAM/sharing policies restrict access to necessary viewers only.
- [ ] Dashboards containing sensitive operational data are never publicly shared.
- [ ] Custom metric, log, alarm, and query costs are monitored.
- [ ] Freshness/no-data signals exist for critical KPIs.
- [ ] Dashboards are tested against real telemetry in non-production.
- [ ] Deployment markers, rollback/incident links, and runbooks are present.
- [ ] Cross-Region aggregates do not mask low-traffic Regions with high error rates.

## 33. Summary

Effective CloudWatch dashboards connect two perspectives: **the health of each service** and **the business outcomes delivered to users**. Service dashboards focus on golden signals, dependencies, saturation, queue backlogs, alarms, and SLOs. Business dashboards focus on event definitions, funnels, conversion, payment success, revenue, refunds, and fulfillment.

Dashboard reliability rests on metric contract quality. Standardize namespaces/dimensions/units, pick accurate statistics/periods, handle duplicate events, separate currencies, and surface freshness/no-data states. Use metric math, SEARCH, and Metrics Insights for dynamic views; use variables to reuse layouts; use CloudFormation/IaC to version-control dashboards.

When operating across accounts and Regions, choose the right mechanism between CloudWatch OAM and cross-account cross-Region dashboards. Pair metrics with alarms, Logs Insights, traces, and Application Signals to move quickly from "something is wrong" to "where it is failing and which KPI is affected." Protect dashboard data, control cardinality/query costs, and test dashboards as part of every release.

### Official Documentation

- [CloudWatch Dashboards](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Dashboards.html)
- [Dashboard body structure and widgets](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Dashboard-Body-Structure.html)
- [Dashboard variables](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_dashboard_variables.html)
- [Metric math](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/using-metric-math.html)
- [SEARCH expression](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/search-expression-syntax.html)
- [Metrics Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch-metrics-insights.html)
- [Metrics Insights quotas](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch-metrics-insights-limits.html)
- [Embedded Metric Format](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format.html)
- [CloudWatch cross-account observability](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Unified-Cross-Account.html)
- [Monitor across accounts and Regions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Cross-Account-Methods.html)
- [Cross-account cross-Region dashboards](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Dashboards.html#CloudWatch_Dashboards_CrossAccount)
- [CloudWatch alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html)
- [CloudWatch anomaly detection](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Anomaly_Detection.html)
- [CloudWatch Application Signals](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals.html)
- [CloudWatch dashboard CloudFormation resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cloudwatch-dashboard.html)
- [CloudWatch PutDashboard API](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_PutDashboard.html)

**Operational note:** AWS service metrics, custom metric dimensions, dashboard variables, Metrics Insights, and cross-account features have specific limits and availability. Before production, verify metric schemas and permissions in the target account/Region; validate dashboards with real telemetry and keep KPI definitions in version control.
