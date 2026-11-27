# Metrics, Logs, Traces, and AWS Observability Strategy

> **Chapter:** Observability with CloudWatch  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem through Region/AZ infrastructure, IAM, VPC, compute services, storage, databases, integration, and serverless. Learners build the ability to select services, design, and deploy secure applications with monitoring, recovery, and cost control.

## Learning Objectives

After this lesson, learners can:

1. Distinguish monitoring from observability and explain the roles of metrics, logs, and traces.
2. Describe CloudWatch namespaces, metrics, dimensions, timestamps, resolution, and statistics.
3. Choose among built-in AWS metrics, custom metrics, CloudWatch Agent, and OpenTelemetry metrics.
4. Create dashboards, metric math, Metrics Insights, and alarms aligned with service-level objectives (SLOs).
5. Collect structured logs, configure log groups/streams, retention, encryption, and query using Logs Insights.
6. Transform log events into metrics, distribute logs via subscription filters, and centralize multi-account data.
7. Design distributed tracing using OpenTelemetry/AWS Distro for OpenTelemetry (ADOT) and understand the role of AWS X-Ray.
8. Use CloudWatch Application Signals, Application Map, Synthetics, and RUM to observe services and user experience.
9. Correlate metrics, logs, and traces using trace ID, request ID, service name, and resource attributes.
10. Build an observability strategy based on SLI/SLO, alerting, incident response, security, and cost control.

## 1. What Problem Does Observability Solve?

An application may run on Amazon ECS, Lambda, EC2, EKS, RDS, SQS, and many other AWS services. When customers report slow requests, the operations team needs to know:

- Is the request slow at the API gateway, application code, database, or a downstream service?
- At which endpoint, Region, or version is the error rate increasing?
- Did errors start after a deployment or due to a dependency throttling?
- How many users are impacted and how long has the impact lasted?
- Should we roll back, scale out, shift traffic, or handle corrupted data?

**Monitoring** tracks predefined signals and alerts when they cross thresholds. **Observability** helps infer the internal state of a system from the telemetry it emits, even when problems were not anticipated beforehand.

In practice, monitoring is part of observability. CloudWatch provides a platform to collect, store, query, visualize, and alert on telemetry from AWS workloads.

### 1.1. Three Primary Telemetry Types

| Type | Answers the Question | Examples |
| --- | --- | --- |
| **Metrics** | What is changing? What is the magnitude and trend? | CPU 85%, p95 latency 900 ms, 30 errors/minute, queue backlog 2,000 messages. |
| **Logs** | What specific event occurred? | Request received AccessDenied, SQL timeout, validation failure, deployment started. |
| **Traces** | Which components did a request pass through and where was time spent? | API → Orders service → RDS → Payment service; database call took 700 ms. |

The three telemetry types complement each other:

- Metrics indicate the timing and scope of an incident.
- Logs provide event details and context.
- Traces show the path and duration of a single request across multiple services.

A dashboard with only CPU metrics cannot explain which query is causing slowness. An individual log might show an SQL timeout but cannot show which dependency caused the overall request to slow down. Traces help place events into the same request path.

### 1.2. CloudWatch in the AWS Ecosystem

Amazon CloudWatch is an observability and monitoring service for AWS resources, applications, and workloads. Main capability groups:

| Component | Role |
| --- | --- |
| CloudWatch Metrics | Collect AWS service metrics and custom metrics. |
| CloudWatch Alarms | Evaluate metrics/expressions and perform actions when state changes. |
| CloudWatch Dashboards | Aggregate metrics, alarms, logs, and widgets. |
| CloudWatch Logs | Collect, store, protect, and query log events. |
| Logs Insights | Query and analyze log data. |
| CloudWatch Agent | Collect guest OS metrics, logs, and certain telemetry from EC2/on-premises. |
| Container Insights | Observe containerized workloads and cluster resources. |
| Lambda Insights | Collect deep telemetry for Lambda functions. |
| Application Signals | Observe service health, dependencies, operations, and SLOs. |
| CloudWatch Application Map | Display topology and health of services/dependencies. |
| CloudWatch Synthetics | Run scheduled canaries to test endpoints/user journeys. |
| CloudWatch RUM | Collect real-user monitoring data from browser sessions. |

CloudWatch integrates with CloudTrail, X-Ray, AWS Distro for OpenTelemetry, Amazon SNS, EventBridge, Systems Manager, and many other AWS services.

## 2. Observability Architecture for an AWS Application

Consider an example Orders system with a public API, an application service running on ECS, an RDS database, and an SQS queue for asynchronous work.

~~~mermaid
flowchart TB
    USER["Web / Mobile client"] --> API["API Gateway / Load Balancer"]
    API --> ORDERS["Orders service on ECS"]
    ORDERS --> DB["Amazon RDS"]
    ORDERS --> Q["Amazon SQS"]
    Q --> WORKER["Invoice worker"]
    ORDERS -. metrics .-> CW["Amazon CloudWatch"]
    WORKER -. metrics .-> CW
    DB -. AWS service metrics .-> CW
    API -. access logs .-> LOGS["CloudWatch Logs"]
    ORDERS -. structured logs .-> LOGS
    WORKER -. structured logs .-> LOGS
    ORDERS -. OpenTelemetry traces .-> XRAY["AWS X-Ray / Application Signals"]
    WORKER -. OpenTelemetry traces .-> XRAY
    CW --> DASH["Dashboards / Alarms / SLOs"]
    LOGS --> INSIGHTS["Logs Insights / Metric filters"]
    XRAY --> MAP["Application Map / Trace details"]
    DASH --> ONCALL["On-call / Incident response"]
    INSIGHTS --> ONCALL
    MAP --> ONCALL
~~~

A single request generates multiple telemetry signals:

1. The API/load balancer records access logs and latency/status metrics.
2. The Orders service records application metrics such as request count, error count, and duration.
3. Structured logs contain request ID, trace ID, route, and outcome.
4. OpenTelemetry instrumentation creates spans for the inbound request, database call, and downstream HTTP call.
5. RDS/SQS/ECS emit AWS service metrics such as database connections, queue depth, and CPU.
6. CloudWatch alarms trigger alerts; Application Signals/trace map help pinpoint the service or dependency causing impact.

### 2.1. Data Plane and Control Plane

Distinguish two planes when designing:

- **Telemetry data plane:** applications/agents send metrics, logs, and traces; CloudWatch ingests and stores them.
- **Observability control plane:** dashboards, alarms, log retention, sampling, filters, IAM policies, and service-level objectives configured to govern how data is used.

A healthy agent does not mean dashboards and alarms are designed properly. Conversely, an alarm without input data will not reflect the true state of the workload.

### 2.2. Choosing Signals by Operational Question

| Question | Appropriate Signal |
| --- | --- |
| Is CPU/memory nearing exhaustion? | EC2/ECS/Container Insights metrics. |
| Is the queue backlog growing? | SQS ApproximateNumberOfMessagesVisible and age of oldest message. |
| Is the HTTP 5xx rate increasing? | Load balancer/API metrics and application error metrics. |
| Which endpoint is slow? | Application latency metrics, Logs Insights, and traces. |
| Which database call is slow? | Distributed traces, database logs/metrics, and Performance Insights when appropriate. |
| Which service did a deployment affect? | Deployment events, metrics, traces, application map, and version tags. |
| Are real users being affected? | CloudWatch RUM, service metrics, and SLO attainment. |

## 3. CloudWatch Metrics: Foundational Concepts

A metric is a time-ordered series of data points with a name, namespace, dimensions, timestamps, and values. CloudWatch stores datapoints over time so users can query, graph, and evaluate alarms.

### 3.1. Namespace, Metric Name, and Dimensions

- **Namespace:** a naming container for grouping metrics, such as AWS/EC2, AWS/ECS, AWS/SQS, or a custom namespace like Orders/Production.
- **Metric name:** the name of the data series, such as CPUUtilization, ApproximateNumberOfMessagesVisible, or RequestLatency.
- **Dimension:** a name/value pair used to identify a resource or categorize a metric, such as InstanceId=i-..., QueueName=orders-queue.
- **Timestamp:** the time the datapoint was recorded.
- **Value:** the measured value.
- **Unit:** units such as Percent, Count, Milliseconds, Bytes, or Seconds.

Example:

| Attribute | Value |
| --- | --- |
| Namespace | AWS/EC2 |
| Metric name | CPUUtilization |
| Dimension | InstanceId = i-0123456789abcdef0 |
| Timestamp | 2026-11-20T04:00:00Z |
| Value | 42.5 |
| Unit | Percent |

CloudWatch treats each unique combination of namespace, metric name, and dimensions as a separate metric. If you publish RequestCount with Service=orders,Environment=prod and another datapoint with Service=orders,Environment=staging, those are two distinct metric time series.

**Cardinality** increases when there are many dimension combinations. Avoid using user ID, session ID, order ID, request ID, or trace ID as metric dimensions. High-cardinality identifiers belong in logs/traces. Use dimensions with a bounded set of values such as Service, Environment, Region, Operation, or StatusClass.

### 3.2. AWS Service Metrics and Custom Metrics

AWS services automatically publish many metrics into their respective namespaces. Examples:

| Namespace | Metric | Meaning |
| --- | --- | --- |
| AWS/EC2 | CPUUtilization | CPU utilization of an EC2 instance. |
| AWS/ECS | CPUUtilization, MemoryUtilization | CPU/memory usage of an ECS cluster/service depending on dimensions. |
| AWS/ApplicationELB | RequestCount, TargetResponseTime, HTTPCode_Target_5XX_Count | Traffic, latency, and errors of an Application Load Balancer. |
| AWS/SQS | ApproximateNumberOfMessagesVisible, ApproximateAgeOfOldestMessage | Queue backlog and message age. |
| AWS/RDS | DatabaseConnections, CPUUtilization, FreeStorageSpace | Database connections, CPU, and available storage space. |
| AWS/Lambda | Invocations, Errors, Duration, Throttles | Invocation count, errors, execution duration, and throttling. |

Custom metrics are suited for things an AWS service cannot inherently know, such as:

- Number of orders successfully paid.
- Number of invoices failed due to business validation.
- Processing duration of a business step.
- Retry count against a downstream provider.
- Request completion rate by business outcome.

Do not create custom metrics just to duplicate metrics an AWS service already provides. Use a dedicated namespace to separate application metrics from AWS service-emitted metrics.

### 3.3. Statistics and Aggregation

CloudWatch can aggregate datapoints by period and statistic:

| Statistic | Meaning | When to Use |
| --- | --- | --- |
| Average | Mean value. | Average CPU, memory, or latency when a general trend is needed. |
| Sum | Sum of values. | Number of requests/errors/events in a period. |
| Minimum | Minimum value. | Lowest free capacity, lowest count. |
| Maximum | Maximum value. | Peak CPU, peak queue backlog, peak latency. |
| SampleCount | Number of datapoints/samples aggregated. | Checking observation volume. |
| p50 / p90 / p95 / p99 | Percentile. | Analyzing latency distribution and tail latency. |

Average can hide outliers. For example, 99 requests taking 100 ms and one request taking 10 seconds can still yield a low average while p99 is very high. For user-facing latency, track p95/p99 alongside average.

Not every metric supports percentiles. Percentiles require appropriate raw data; if only pre-aggregated statistic sets are sent, percentiles cannot be computed in many cases.

### 3.4. Period and Metric Resolution

Period is the length of time over which CloudWatch aggregates datapoints to return a statistic or evaluate an alarm.

- AWS service metrics typically have standard resolution, commonly at 1-minute granularity or higher depending on the service.
- Custom metrics can use standard resolution or high resolution.
- High-resolution custom metrics can be published with StorageResolution=1; datapoints have 1-second granularity.
- When reading high-resolution metrics, supported periods include 1, 5, 10, 30 seconds, or multiples of 60 seconds.
- High-resolution alarms can use periods of 10, 20, or 30 seconds per alarm limits.

High resolution reduces detection latency but increases datapoint volume, API calls/cost, and noise. Enable it only when the workload requires sub-minute reaction and has a corresponding operational action.

### 3.5. Metric Retention

CloudWatch retains datapoints by resolution and duration as follows:

| Resolution/Period | Retention Period |
| --- | --- |
| High-resolution under 60 seconds | 3 hours |
| 1 minute | 15 days |
| 5 minutes | 63 days |
| 1 hour | 455 days (15 months) |

As data ages, CloudWatch aggregates it into coarser periods. Therefore, you cannot assume 1-second data will remain queryable after several days. If long-term history at fine granularity is required, design an appropriate export/streaming pipeline or analytics system.

### 3.6. Dimensions Must Be Consistent

When querying a metric, you must specify the exact dimension combination that was published. CloudWatch does not automatically aggregate custom metrics by arbitrarily dropping a dimension. If you need rollups by service or environment, publish the corresponding time series, use appropriate metric math/Metrics Insights, or design the metric schema upfront.

Do not add arbitrary dimensions on each publish. Doing so creates new time series and causes dashboards/alarms querying the old metric to miss new datapoints.

## 4. Collecting Metrics from AWS Resources and Workloads

### 4.1. Built-in Metrics from AWS Services

Many AWS services send metrics to CloudWatch automatically without installing an agent. However, the set of metrics and publishing frequency depend on the service, resource type, and monitoring mode.

For example, EC2 has basic monitoring; detailed monitoring can increase metric frequency. Metrics such as memory usage inside the guest OS are not included in default EC2 metrics because the hypervisor cannot see memory usage inside the operating system.

Before installing an agent, inspect the namespace, dimensions, and monitoring mode of the AWS service.

### 4.2. CloudWatch Agent

The unified CloudWatch Agent collects:

- Guest OS metrics such as memory, disk, swap, processes, and network as configured.
- Logs from files on EC2 and on-premises servers.
- Custom metrics via StatsD/collectd when configured.
- Traces from OpenTelemetry or X-Ray instrumentation in supported agent configurations.

The agent runs on Linux and Windows Server. Metrics published by the agent typically go into the CWAgent namespace unless overridden. Logs are sent to CloudWatch Logs.

### 4.3. CloudWatch Agent Configuration Example

Example JSON for Linux EC2, collecting memory/disk metrics and an application log:

~~~json
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "cwagent"
  },
  "metrics": {
    "namespace": "CWAgent",
    "append_dimensions": {
      "InstanceId": "${aws:InstanceId}"
    },
    "metrics_collected": {
      "mem": {
        "measurement": [
          "mem_used_percent"
        ],
        "metrics_collection_interval": 60
      },
      "disk": {
        "measurement": [
          "used_percent"
        ],
        "resources": [
          "/"
        ],
        "metrics_collection_interval": 60
      }
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/orders/application.log",
            "log_group_name": "/orders/prod/application",
            "log_stream_name": "{instance_id}",
            "timezone": "UTC"
          }
        ]
      }
    }
  }
}
~~~

This is an illustrative configuration. Before using it, verify the OS, file paths, agent version, permissions, and CloudWatch Agent options. Grant an IAM role to the instance with the least privilege needed to publish metrics and logs. Do not place access keys inside the agent config file.

### 4.4. Installing and Controlling the Agent

CloudWatch Agent can be installed via package manager, SSM Distributor, or your organization's deployment mechanism. After installation, you can fetch the config from Parameter Store and start the agent:

~~~bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c ssm:AmazonCloudWatch-linux \
  -s
~~~

The SSM parameter name in the example must exist and contain the agent configuration. -m ec2 specifies the EC2 environment; for on-premises, configure the appropriate mode/credentials. Use Systems Manager State Manager/Distributor to manage the agent fleet consistently rather than manually SSHing into each instance.

### 4.5. Container Insights and Lambda Insights

- **Container Insights** collects and aggregates telemetry from container workloads, including cluster/service/task/pod/container metrics depending on platform and configuration.
- **Lambda Insights** adds system-level metrics and diagnostic data for Lambda execution environments.
- Verify IAM permissions, agent/extension version, cluster configuration, and ingestion/custom metric costs.

Do not enable all telemetry just because you can. Select metrics that answer questions about saturation, errors, latency, and capacity.

## 5. Custom Metrics and OpenTelemetry Metrics

### 5.1. When Is a Custom Metric Needed?

A custom metric should represent a meaningful operational signal with an owner and a clear response.

Examples:

| Metric | Recommended Dimensions | Purpose |
| --- | --- | --- |
| OrdersAccepted | Service, Environment, Region | Track business throughput. |
| PaymentFailures | Provider, Environment, FailureClass | Detect payment provider failures. |
| InvoiceProcessingDuration | Service, Environment, Operation | Track processing duration. |
| OutboxBacklog | Service, Environment | Detect stalled event publishers. |
| CacheHitRate | Service, Environment, CacheName | Evaluate cache efficiency. |

Use stable dimensions with a controlled number of combinations. If you need analysis by order ID, customer ID, or trace ID, record those values in logs/traces and query by correlation ID.

### 5.2. Publishing Custom Metrics with AWS CLI

Example publishing the number of orders accepted in one minute:

~~~bash
aws cloudwatch put-metric-data \
  --namespace Orders/Production \
  --metric-data '[{"MetricName":"OrdersAccepted","Dimensions":[{"Name":"Service","Value":"orders-api"},{"Name":"Environment","Value":"prod"}],"Timestamp":"2026-11-20T04:00:00Z","Value":42,"Unit":"Count"}]' \
  --region ap-southeast-1
~~~

Example high-resolution metric:

~~~bash
aws cloudwatch put-metric-data \
  --namespace Orders/Production \
  --metric-data '[{"MetricName":"RequestLatency","Dimensions":[{"Name":"Service","Value":"orders-api"}],"Value":125,"Unit":"Milliseconds","StorageResolution":1}]' \
  --region ap-southeast-1
~~~

Timestamps, Region, namespace, and dimensions in the examples are illustrative. The IAM principal requires the cloudwatch:PutMetricData permission; the namespace can be restricted using an appropriate condition in the IAM policy. Do not call PutMetricData on every request at high volume without accounting for batching/aggregation and cost.

### 5.3. Embedded Metric Format (EMF)

Embedded Metric Format allows an application to write a JSON log event containing metric definitions and dimensions. CloudWatch Logs ingests the event and then extracts metric datapoints from the log.

Example EMF event:

~~~json
{
  "_aws": {
    "Timestamp": 1795147200000,
    "CloudWatchMetrics": [
      {
        "Namespace": "Orders/Production",
        "Dimensions": [
          ["Service", "Environment"]
        ],
        "Metrics": [
          {
            "Name": "OrdersAccepted",
            "Unit": "Count"
          },
          {
            "Name": "ProcessingLatency",
            "Unit": "Milliseconds"
          }
        ]
      }
    ]
  },
  "Service": "orders-api",
  "Environment": "prod",
  "OrdersAccepted": 1,
  "ProcessingLatency": 84
}
~~~

EMF fits well when an application already emits structured logs and wants to generate metrics without calling the CloudWatch API directly on every business operation. CloudWatch extracts metrics from the log event according to the EMF structure. EMF does not replace log schemas, log retention, or cost controls; log events are still ingested and stored according to the log group configuration.

### 5.4. OpenTelemetry Metrics

OpenTelemetry defines a common API/SDK and data model for instrumenting applications. Metrics from OpenTelemetry typically carry attributes/labels instead of traditional CloudWatch dimensions.

CloudWatch supports OpenTelemetry metrics via OTLP endpoints and querying with PromQL in corresponding capabilities. Keep these distinctions in mind:

- Metrics published by AWS services appear under namespace/metric/dimensions.
- Custom CloudWatch metrics have namespaces and dimensions.
- OpenTelemetry metrics ingested via OTLP have labels and are queried with PromQL; they do not use the exact same traditional namespace/dimensions mental model.

Choose one telemetry pipeline with clear ownership. Avoid publishing the same metric from CloudWatch Agent, EMF, and an OpenTelemetry collector without conventions, as this can create duplicate data or confusing dashboards.

## 6. Querying and Analyzing Metrics

### 6.1. Metrics Explorer and Dashboards

Metrics Explorer helps locate metrics by namespace, dimensions, resource tags, and filters. When designing a dashboard, group widgets by operational question:

- Service golden signals: traffic, errors, latency, saturation.
- Dependency health: RDS, SQS, DynamoDB, downstream APIs.
- Capacity: CPU, memory, disk, connection pools, queue depth.
- Deployment: version, desired/running tasks, deployment events.
- Business outcomes: orders accepted, payment success, invoice completion.

Do not put every metric you can find onto one dashboard. Each widget should answer a specific question and have an intended consumer.

### 6.2. Metric Math

Metric math creates new time series by combining metrics. For example, calculating error rate:

~~~text
errorRate = IF(requestCount > 0, 100 * errorCount / requestCount, 0)
~~~

An error rate chart is more meaningful than raw error counts alone when traffic varies. Metric math can be used in graphs and to create alarms on expressions returning a single time series.

Metric math requires consistent period, dimensions, and statistics across input metrics. Handle a zero denominator explicitly to avoid unexpected results.

### 6.3. Metrics Insights

CloudWatch Metrics Insights allows querying metrics using SQL-like syntax. Example finding average CPU by EC2 instance:

~~~sql
SELECT AVG(CPUUtilization)
FROM SCHEMA("AWS/EC2", InstanceId)
GROUP BY InstanceId
ORDER BY AVG() DESC
LIMIT 20
~~~

Example finding SQS queues with large backlogs:

~~~sql
SELECT MAX(ApproximateNumberOfMessagesVisible)
FROM SCHEMA("AWS/SQS", QueueName)
GROUP BY QueueName
ORDER BY MAX() DESC
LIMIT 20
~~~

Metrics Insights is useful when you have many resources and do not want to manually build widgets/metric queries for each resource. Queries can aggregate by dimensions and filter by namespace/schema. When creating alarms from Metrics Insights, understand whether the query returns one or multiple time series and understand alarm contributor semantics.

### 6.4. Search Expressions and Alarms

CloudWatch metric search expressions can discover multiple time series for graphs, but not every expression is supported for alarms. Do not create alarms on SEARCH expressions. For alarms needing to aggregate multiple time series, consider Metrics Insights alarms or an appropriate metric math expression.

### 6.5. Dashboards for Multiple Environments/Accounts

An operational dashboard should clearly show:

- The account, Region, environment, and service being viewed.
- Time range, timezone, and period.
- Deployment markers or annotations if available.
- Links to alarms, log groups, trace maps, and runbooks.
- Sufficient metric dimensions to identify affected resources.

CloudWatch cross-account observability enables a monitoring account to view telemetry shared from source accounts through CloudWatch Observability Access Manager (OAM). Design sinks/links, organization scope, and IAM permissions according to your organization's multi-account model.

## 7. CloudWatch Alarms: Detecting Issues and Triggering Actions

An alarm evaluates a metric or expression based on period, threshold, and evaluation settings. An alarm has three primary states:

| State | Meaning |
| --- | --- |
| OK | Data is within normal thresholds. |
| ALARM | Breach condition has been confirmed per evaluation settings. |
| INSUFFICIENT_DATA | Not enough data to determine state. |

An alarm does not fix a system on its own. It can send notifications via SNS, trigger EC2 actions, Auto Scaling actions, or configured automation integrations.

### 7.1. Period, EvaluationPeriods, and DatapointsToAlarm

- **Period:** the duration producing one datapoint for each evaluation.
- **EvaluationPeriods (N):** the number of most recent datapoints evaluated.
- **DatapointsToAlarm (M):** the number of datapoints out of N that must breach the threshold for the alarm to transition to ALARM.

Example 2 out of 3: Period 60 seconds, EvaluationPeriods 3, DatapointsToAlarm 2. The alarm transitions to ALARM when at least 2 of the last 3 datapoints breach the threshold; they do not have to be consecutive.

M out of N helps avoid alerting on a single transient spike while still detecting sustained incidents. Choose M/N based on SLO, metric publishing cadence, and required reaction time.

### 7.2. CloudFormation Alarm Example for SQS Backlog

~~~yaml
Resources:
  OrdersBacklogAlarm:
    Type: AWS::CloudWatch::Alarm
    Properties:
      AlarmDescription: Orders queue backlog is above the operating threshold
      Namespace: AWS/SQS
      MetricName: ApproximateNumberOfMessagesVisible
      Dimensions:
        - Name: QueueName
          Value: !GetAtt OrdersQueue.QueueName
      Statistic: Maximum
      Period: 60
      EvaluationPeriods: 3
      DatapointsToAlarm: 2
      Threshold: 100
      ComparisonOperator: GreaterThanThreshold
      TreatMissingData: notBreaching
      AlarmActions:
        - !Ref OperationsTopic
      OKActions:
        - !Ref OperationsTopic
~~~

The queue and SNS topic in the example must be declared or passed from another stack. The threshold of 100 is illustrative; choose thresholds based on backlog capacity, consumer throughput, and business processing deadlines.

### 7.3. Missing Data

Not every metric emits datapoints continuously. CloudWatch lets you configure how missing data is treated:

| Value | Behavior |
| --- | --- |
| breaching | Treat missing datapoints as breaching the threshold. |
| notBreaching | Treat missing datapoints as not breaching. |
| ignore | Maintain the current alarm state. |
| missing | If there are not enough datapoints, the alarm can transition to INSUFFICIENT_DATA. |

Choose based on metric semantics:

- Heartbeat metrics or metrics that must always emit: missing data may indicate a dead agent/service; consider breaching.
- Metrics emitted only on error events: no datapoints usually means no errors; consider notBreaching.
- Metrics emitted intermittently by design: consider ignore/missing and understand the evaluation range.

Misconfiguring missing-data behavior can cause false alarms or hide a broken telemetry pipeline.

### 7.4. Anomaly Detection

CloudWatch anomaly detection uses a model to generate an expected band from metric history. An alarm can compare the actual metric against the band instead of a static threshold.

This works well for traffic/latency with day-of-week, time-of-day, or seasonal patterns. However, anomaly detection does not inherently understand business impact. Higher traffic during a campaign may be normal; a sudden drop in traffic may matter more than a CPU spike. Combine anomaly alarms with SLO/business signals and deployment schedules.

### 7.5. Composite Alarms and Reducing Alert Noise

A composite alarm combines the states of other alarms using AND/OR/NOT logic. For example, page only when high error rate and latency breach the SLO simultaneously, or when multiple instances are unhealthy together.

Composite alarms help reduce notification storms, but must not be used to hide independent failure signals. Keep the underlying metric alarms for investigation and build composite alarms around service impact.

### 7.6. Alarm Actions and Notification Routing

An alarm can send an SNS notification on state transitions. SNS can fan out to email, incident tooling, or Lambda handlers per approved integrations.

- Page on-call only when there is user/business impact or risk of breaching an SLO.
- Warning/capacity signals can create tickets or post to notification channels.
- Include runbook URL, service name, environment, Region, alarm name, and dashboard link in the alarm description/notification.
- Define who receives the alert, who owns it, and escalation if not acknowledged.
- Test alarm actions after changing topics, roles, or permissions.

### 7.7. A Good Alarm Must Be Actionable

Do not create an alarm merely because a metric can be measured. Each alarm should answer:

1. What condition is considered abnormal?
2. Does it reflect user impact, capacity risk, or a telemetry pipeline failure?
3. Who receives the notification?
4. Which dashboard/log/trace should the responder inspect?
5. What safe action exists, such as rollback, scale, failover, or disabling a feature?
6. When is the alarm closed or converted into a post-incident action?

## 8. CloudWatch Logs: Log Groups, Streams, and Events

CloudWatch Logs ingests, stores, and queries log events from AWS services, applications, containers, and servers.

### 8.1. Log Group, Log Stream, and Log Event

| Component | Role |
| --- | --- |
| Log group | Groups logs by application, service, environment, or source. |
| Log stream | Stream of events from a specific instance, container, function execution source, or log source. |
| Log event | A single record consisting of a timestamp and a message. |

Examples of log group naming:

- /orders/prod/application
- /orders/prod/access
- /orders/prod/worker
- /payments/prod/application
- /aws/lambda/orders-handler

Log group names can become part of the operational contract. Name them consistently so queries, retention, IAM, subscription filters, and cost allocation are easy to manage.

### 8.2. Retention and Log Class

If no retention policy is set, log events may be stored indefinitely. Set retention according to purpose, audit requirements, compliance, and budget.

CloudWatch Logs offers log classes with different feature sets and costs:

- **Standard:** suited when full interactive features are needed, such as metric filters, subscription filters, Live Tail, field indexing, and rich analysis capabilities.
- **Essentials (formerly Infrequent Access):** geared toward storing and querying logs with a more limited feature set compared to Standard.
- **Delivery:** used for certain log delivery streams to Amazon S3 or Amazon Data Firehose; log events in this class are retained in CloudWatch Logs for 2 days and this retention period is fixed.

Before choosing a log class, check the current feature matrix. Some capabilities like metric filters, subscription filters, Live Tail, or field indexing are only available in Standard. A log group's class cannot be arbitrarily switched back and forth after creation; determine requirements before deployment.

### 8.3. Encryption and Access Control

CloudWatch Logs encrypts data at rest by default. You can configure a customer managed KMS key for a log group when key policy/audit control is required.

IAM should restrict:

- Who can create log groups/streams.
- Who can call PutLogEvents.
- Who can read, filter, query, or export logs.
- Who can create subscription filters and modify retention/KMS keys.
- Who can view logs belonging to environments containing sensitive data.

Do not grant every developer read access to all production logs unless needed. Separate operational access, audit access, and retention administration permissions.

### 8.4. Structured Logging

Logs should use structured JSON for easy parsing and querying. Sample event:

~~~json
{
  "timestamp": "2026-11-20T04:10:12.341Z",
  "level": "ERROR",
  "service": "orders-api",
  "environment": "prod",
  "version": "2026.11.20.3",
  "operation": "CreateOrder",
  "request_id": "req-7c91",
  "trace_id": "1-673e0a24-7d4c9a1234567890abcdef12",
  "duration_ms": 842,
  "error_code": "PAYMENT_PROVIDER_TIMEOUT",
  "message": "Payment provider did not respond before deadline"
}
~~~

Include consistent fields:

- UTC timestamp.
- Level/severity.
- Service, environment, Region, and version.
- Operation/route or event type.
- Request ID and trace ID.
- Duration/status/error code.
- Resource identifier when needed and permitted.

Structured logs enable Logs Insights to filter by field without parsing free-form text. Never log raw authorization headers, cookies, passwords, tokens, payment data, or full request bodies containing PII.

### 8.5. Log Levels and Noise

- DEBUG: detailed diagnostics for development, typically not enabled broadly in production.
- INFO: important lifecycle events and business milestones.
- WARN: abnormal situations that may self-recover or warrant monitoring.
- ERROR: failed operation or condition needing investigation.
- FATAL/CRITICAL: error preventing the process/service from continuing normal operation.

Do not repeatedly log full stack traces for an error retried thousands of times. Use appropriate sampling/rate limiting and error count metrics to preserve problem visibility.

## 9. Collecting Logs from AWS Workloads

### 9.1. Lambda

Lambda can send execution logs to CloudWatch Logs when its execution role has the appropriate permissions. The default log group typically follows /aws/lambda/function-name. You can configure the log group, log format, application/system log levels, and retention as needed.

Do not assume a log group exists just because a function deployed successfully. Check the role, log group, Region, retention, and log format. For critical functions, create the log group/retention via IaC to control its lifecycle.

### 9.2. ECS and Container Workloads

With ECS, you can use the awslogs log driver to send container stdout/stderr to CloudWatch Logs. The task execution role needs appropriate permissions to create log streams and send log events if the log group is not pre-created.

Example task definition fragment:

~~~json
{
  "logConfiguration": {
    "logDriver": "awslogs",
    "options": {
      "awslogs-group": "/orders/prod/application",
      "awslogs-region": "ap-southeast-1",
      "awslogs-stream-prefix": "orders"
    }
  }
}
~~~

Pre-create the log group with IaC, setting retention/KMS/log class and explicit permissions. For EKS/Kubernetes, use Fluent Bit/CloudWatch agent or OpenTelemetry Collector according to your chosen pipeline.

### 9.3. EC2 and On-Premises

CloudWatch Agent can tail log files from Linux/Windows servers. Configuration must specify file path, log group, stream naming, timestamp format, and timezone. When logrotate rotates a file, verify that the agent continues tracking the new file properly.

### 9.4. AWS Service Logs

Many AWS services can send service/access logs to CloudWatch Logs, S3, or Firehose depending on the service and configuration. Examples include API Gateway, VPC Flow Logs, Route 53 Resolver query logs, and certain database/application logs.

Choose the destination based on purpose:

- CloudWatch Logs: near real-time querying and operations.
- S3: long-term storage, lifecycle rules, data lakes, and analytics.
- Firehose: delivering/transforming/routing logs to supported destinations.
- OpenSearch: deep search/analytics when the workload requires those capabilities.

Do not enable access logs with all default fields blindly. Record only necessary fields, mask/redact sensitive data, and control ingestion costs.

## 10. Logs Insights: Querying Log Events

CloudWatch Logs Insights provides a query language to filter, parse, aggregate, and visualize logs.

### 10.1. Finding Recent Errors

~~~text
fields @timestamp, level, service, message, trace_id
| filter level = "ERROR"
| sort @timestamp desc
| limit 50
~~~

### 10.2. Counting Errors in 5-Minute Buckets

~~~text
filter level = "ERROR"
| stats count(*) as errorCount by bin(5m)
~~~

### 10.3. Finding High Latency

~~~text
fields @timestamp, service, operation, duration_ms, trace_id
| filter duration_ms >= 1000
| sort duration_ms desc
| limit 100
~~~

### 10.4. Finding a Trace ID

~~~text
fields @timestamp, @logStream, service, operation, message
| filter trace_id = "1-673e0a24-7d4c9a1234567890abcdef12"
| sort @timestamp asc
| limit 200
~~~

### 10.5. Parsing Plaintext Logs Without JSON Fields

If logs are in text format:

~~~text
fields @timestamp, @message
| parse @message "requestId=* status=* durationMs=*" as requestId, status, durationMs
| filter status = "500"
| sort @timestamp desc
| limit 50
~~~

The parse pattern structure must match the actual log format. For new applications, structured JSON is usually easier to operate than regex/glob parsing.

### 10.6. Common Query Syntax

| Command | Purpose |
| --- | --- |
| fields | Select fields and create calculated fields. |
| filter | Filter log events by condition. |
| parse | Extract fields from strings. |
| stats | Aggregate using count/sum/avg/max/min/percentile. |
| sort | Sort results. |
| limit | Limit the number of rows returned. |
| dedup | Remove duplicate results by fields. |
| pattern | Group logs with recurring structures. |
| diff | Compare logs between two time ranges. |
| unnest | Expand a list into multiple records. |

### 10.7. Optimizing Query Cost

Logs Insights charges based on the amount of data scanned per current pricing. To reduce scan volume:

- Select only the needed log groups; do not query across the entire account unnecessarily.
- Use the shortest practical time range.
- Filter early on useful fields.
- Use field indexes when supported by the log class and query.
- Avoid overly frequent dashboard query refreshes.
- Cancel running queries when no longer needed.
- Choose a log class aligned with required capabilities.

Save reusable queries in runbooks. Name them by service/purpose, such as orders/errors-by-operation or payments/latency-outliers.

## 11. Metric Filters and Subscription Filters

### 11.1. Metric Filters: Turning Logs into Metrics

A metric filter counts log events matching a filter pattern and publishes a CloudWatch metric. Example counting application errors in JSON logs:

~~~yaml
Resources:
  ApplicationLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /orders/prod/application
      RetentionInDays: 30

  ApplicationErrorMetric:
    Type: AWS::Logs::MetricFilter
    Properties:
      LogGroupName: !Ref ApplicationLogGroup
      FilterPattern: '{ $.level = "ERROR" }'
      MetricTransformations:
        - MetricNamespace: Orders/Production
          MetricName: ApplicationErrors
          MetricValue: "1"
          DefaultValue: 0
~~~

Each matching event contributes a metric value per MetricValue. DefaultValue can help emit a zero datapoint when no events match in certain configurations, though you must understand the semantics when filters use dimensions as well as metric filter limits.

Metric filters suit simple log patterns such as ERROR counts, authentication failures, or validation failures. For critical business metrics, instrument directly in the application layer or use EMF for clearer schemas.

### 11.2. Filter Patterns

Filter patterns support matching on unstructured, JSON, and space-delimited logs. Examples:

~~~text
ERROR
~~~

~~~text
{ $.level = "ERROR" && $.service = "orders-api" }
~~~

~~~text
[host, ident, authuser, timestamp, request, status_code = 5*, bytes]
~~~

Test filter patterns against sample logs before deploying. An overly broad pattern can emit inaccurate metrics and increase ingestion/alert noise.

### 11.3. Subscription Filters: Forwarding Logs to Other Systems

Subscription filters route log events to supported destinations such as:

- AWS Lambda.
- Amazon Kinesis Data Streams.
- Amazon Data Firehose.
- Certain cross-account/partner integration destinations depending on configuration.

Use cases:

- Centralize security/audit logs.
- Send logs to a SIEM.
- Transform/filter and store in S3.
- Stream application events to an analytics pipeline.

Subscription filters are not the sole archiving mechanism. For long-term retention requirements, use exports/Firehose/S3 lifecycles aligned with retention and compliance policies.

### 11.4. Cross-Account Log Centralization

In a multi-account AWS Organization, you can set up a log archive account or monitoring account. CloudWatch Observability Access Manager (OAM) supports sharing telemetry between source accounts and a monitoring account via sinks/links; CloudWatch Logs also offers centralization/subscription mechanisms suited to your architecture.

Design clearly:

- Which account owns the logs.
- Which account can read/search them.
- Which log groups are shared.
- Which Regions are sources/destinations.
- KMS key policies and IAM roles.
- Retention and data residency requirements.
- How to handle an organization member account leaving scope.

Do not grant read access to all logs across the entire organization when only metrics or a specific set of log groups need to be shared.

## 12. Distributed Tracing with AWS X-Ray and OpenTelemetry

Distributed tracing follows a single request across multiple services and dependencies. A trace contains multiple spans; each span represents an operation such as an HTTP server request, database query, message publish, or downstream call.

### 12.1. Trace, Span, and Context Propagation

| Component | Meaning |
| --- | --- |
| Trace ID | Identifies the entire request path. |
| Span ID | Identifies a single operation within the trace. |
| Parent Span ID | Links a child span to its parent span. |
| Trace attributes | Metadata such as service, operation, HTTP route, database system. |
| Events | Events occurring within the span's timeframe. |
| Status | Outcome of the operation, such as OK or ERROR. |

Example trace path:

~~~mermaid
flowchart LR
    CLIENT["Client request"] --> API["API Gateway span"]
    API --> ORDER["Orders API span"]
    ORDER --> DB["RDS query span"]
    ORDER --> PAY["Payment HTTP span"]
    ORDER --> QUEUE["SQS publish span"]
~~~

Context propagation passes trace context via HTTP headers or message metadata so downstream services continue the same trace. OpenTelemetry supports W3C Trace Context; AWS X-Ray also has its own trace header in certain integrations. When integrating multiple libraries/services, configure propagators consistently to avoid fragmented traces.

### 12.2. Instrumentation

There are three primary approaches:

- **Automatic instrumentation:** agents/libraries automatically create spans for supported frameworks, HTTP clients, database drivers, and runtimes.
- **Manual instrumentation:** developers create spans for business operations that auto-instrumentation does not understand, such as CalculateShipping or AuthorizePayment.
- **Infrastructure/service instrumentation:** AWS services and gateways emit trace context/telemetry per supported integrations.

Do not instrument every tiny function. Focus on request boundaries, downstream dependencies, database calls, message processing, and business steps needed for investigation.

### 12.3. AWS Distro for OpenTelemetry (ADOT)

ADOT is AWS's supported distribution of OpenTelemetry, including SDKs/auto-instrumentation and Collector components. Use the OTel API/SDK in the application, then export traces/metrics through the configured pipeline.

A tracing pipeline typically includes:

1. Instrumenting the application with the OTel SDK/agent.
2. Propagating trace context across inbound/outbound requests.
3. Sending OTLP telemetry to the Collector/CloudWatch Agent or appropriate endpoint.
4. Collector batching, enriching attributes, filtering, and exporting.
5. Viewing traces in AWS X-Ray/CloudWatch integrations.

The Collector can run as a sidecar, daemonset, gateway, or agent depending on architecture. Choose topology based on throughput, failure isolation, network path, retry/buffering, and operational ownership.

### 12.4. AWS X-Ray and the OpenTelemetry Roadmap

AWS X-Ray stores and analyzes trace data, supporting trace details, trace maps, and CloudWatch integration. X-Ray remains a useful backend/observation surface for distributed traces.

**SDK lifecycle note:** AWS X-Ray SDKs and daemon entered maintenance mode on **25-02-2026**; from that point AWS limits releases primarily to security fixes. AWS announced discontinuation of support for X-Ray SDKs/daemon on **25-02-2027**. For new applications, prefer OpenTelemetry/ADOT; for legacy systems, plan migration before the end-of-support milestone. The X-Ray backend continues to accept traces from supported instrumentation paths.

Do not confuse the maintenance of X-Ray SDKs/daemon with the CloudWatch/X-Ray trace backend shutting down. Changes are primarily needed in the application's instrumentation/collection pipeline.

### 12.5. Sampling and Trace Volume

Tracing can generate large volumes of data. Sampling decides which requests get fully recorded traces.

- **Head sampling:** decides early at the start of the trace; simple and reduces overhead.
- **Tail sampling:** decides after the collector observes part or all of the trace; can prioritize errors/slow traces, but requires the collector to buffer/hold trace data.
- **Parent-based sampling:** respects the sampling decision propagated from upstream.
- **Consistent sampling:** keeps decisions consistent across services so traces do not break mid-path.

If each service samples independently, traces may end up with only a few disconnected spans. Design propagation/sampling at service boundaries. During low traffic or critical incidents, sampling can be temporarily increased per policy while controlling costs.

### 12.6. Keep Sensitive Data Out of Spans

Do not add passwords, access tokens, authorization headers, session cookies, payment details, or unnecessary PII to span attributes/events. Trace data is often broadly accessible to developers and on-call engineers; protect it like production logs.

## 13. CloudWatch Application Signals and Application Map

Application Signals helps observe the health of applications/services and dependencies, and build service-level indicators and SLOs. Once instrumented/configured, CloudWatch can display service operations, dependency relationships, latency/error metrics, and links to traces.

### 13.1. Application Map

Application Map displays topology including clients, canaries, services, and dependencies. Operators can drill down from an application group to individual services/dependencies and inspect health/related metrics.

Application Map now replaces the legacy Service Map view in CloudWatch Application Signals. X-Ray Trace Map is a separate trace topology view focused on trace data and request paths.

### 13.2. Service Operations and Golden Signals

Application Signals focuses on key operational signals such as:

- Latency: request/operation processing time.
- Availability: ratio of successful operations as defined.
- Errors/faults: failed requests caused by the service or a dependency.
- Dependencies: services/resources that an operation depends on.

Use these metrics to evaluate service health per operation. A service with good average latency can still have a very high p99 on one route; analyze by operation and dependency.

### 13.3. Service Level Objectives

CloudWatch supports SLOs based on CloudWatch metrics/metric math and Application Signals. An SLO defines a reliability target over an evaluation interval.

Two common evaluation modes:

- **Period-based SLO:** each period is evaluated as met/unmet against a threshold.
- **Request-based SLO:** evaluates the ratio of good requests to total requests based on good/bad events.

Example availability SLO: at least 99.9% of requests in a rolling window must succeed. Latency SLO: at least 99% of requests complete within 500 ms. Thresholds are examples; choose them based on user expectations and business requirements.

### 13.4. Synthetics and RUM

| Tool | Perspective | Example |
| --- | --- | --- |
| CloudWatch Synthetics | Synthetic monitoring: proactive scheduled canary tests. | Every minute, sign in, search for a product, and add an item to cart. |
| CloudWatch RUM | Real User Monitoring: data from actual browser sessions. | Page load time, JavaScript errors, client-side latency by browser/region. |

Synthetics tests controlled journeys even when real traffic is absent. RUM reveals actual user experience. Combine both to distinguish an endpoint passing synthetic tests from real users failing due to browser or network issues.

### 13.5. Choosing Tools by Workload Type

- ECS/EKS: Container Insights, CloudWatch Agent/ADOT, Application Signals, and traces.
- Lambda: CloudWatch Logs/metrics, Lambda Insights, Application Signals, and traces.
- EC2/on-premises: CloudWatch Agent for guest metrics/logs; OTel/ADOT for application traces.
- Web application: RUM, Synthetics, API/load balancer metrics, and backend traces.
- Serverless event flows: SQS/EventBridge/Lambda metrics, structured logs, and trace context passed via event payloads/headers per supported integrations.

Not every runtime/service offers the same level of automatic instrumentation. Verify the support matrix, agent versions, permissions, and how trace context crosses async boundaries.

## 14. Correlating Metrics, Logs, and Traces

Correlation turns multiple telemetry sources into a unified investigation tool.

### 14.1. Using Identifiers Intentionally

| Identifier | Purpose | Where Stored |
| --- | --- | --- |
| trace_id | Links spans belonging to the same request. | Traces and structured logs. |
| span_id | Identifies a specific operation. | Traces and logs when needed. |
| request_id | Identifies a request at an API/application boundary. | Access/application logs, response headers if appropriate. |
| correlation_id | Links a business workflow across async events. | Message attributes/payload, logs, and spans. |
| deployment_version | Identifies the release handling a request. | Controlled-cardinality metric dimensions, logs, trace resource attributes. |

Trace ID and request ID should not become custom metric dimensions because of high cardinality. Use them to query logs/traces.

### 14.2. Correlation in Async Processing

A request may publish an SQS message and return an HTTP response; a worker processes it later. Trace context should be injected/extracted through message metadata using a compatible propagator/instrumentation.

If a single continuous trace cannot be preserved end-to-end, use a stable business correlation ID to tie the workflow together and create span links/trace links where appropriate. Do not fabricate trace IDs or reuse a request ID as a span ID.

### 14.3. Investigating from Alarm to Trace

Practical workflow:

1. An alarm reports p95 latency or error rate breaching the SLO.
2. The dashboard identifies the service, operation, Region, and timeframe.
3. Logs Insights filters ERRORs in the same time range to retrieve trace ID and request ID.
4. Open the trace to see which span took the most time or returned an error.
5. Check downstream metrics/logs for databases, queues, or dependencies.
6. Compare deployment versions and configuration changes.
7. Document root cause, mitigation, and follow-up actions.

A helpful dashboard/notification should include links or sufficient context for on-call responders to open the exact log group, time range, and trace.

## 15. Observability Strategy: SLI, SLO, and Golden Signals

Observability creates value when telemetry is tied to user impact and operational decisions. Do not start with "what metrics can we collect?"—start with "how do users need the system to behave?".

### 15.1. SLI, SLO, and SLA

| Concept | Meaning | Example |
| --- | --- | --- |
| SLI | Service Level Indicator: a measurement of reliability/performance. | Ratio of successful requests, p95 latency. |
| SLO | Service Level Objective: a target for an SLI over a time window. | 99.9% successful requests over 30 days. |
| SLA | Service Level Agreement: a customer-facing commitment, typically with terms and consequences if breached. | Availability commitment and service credits. |

SLOs should generally have stricter internal thresholds than SLAs so the team has time to remediate before breaching customer commitments.

### 15.2. Defining SLIs with Clear Denominators

Example availability SLI:

\[
Availability = \frac{Good\ Requests}{Valid\ Requests} \times 100\%
\]

Latency SLI:

\[
Latency\ Compliance = \frac{Requests\ under\ threshold}{Valid\ Requests} \times 100\%
\]

Counting errors without knowing total requests cannot distinguish 20 errors out of 100 requests from 20 errors out of 1 million requests. Always define the numerator, denominator, excluded traffic, and evaluation window.

### 15.3. Golden Signals

Four golden signals commonly used for services:

1. **Latency:** time to serve requests, usually tracked via p50/p95/p99.
2. **Traffic:** number of requests/operations per unit of time.
3. **Errors:** rate or count of failed requests.
4. **Saturation:** resource exhaustion levels such as CPU, memory, connections, queue capacity, or thread pools.

For infrastructure, the USE model is also helpful:

- Utilization: how much of a resource is in use.
- Saturation: how much work is queued due to resource shortage.
- Errors: whether errors are occurring due to the resource/dependency.

### 15.4. Error Budget

An error budget is the allowable unreliability a service can tolerate within an evaluation window. For example, a 99.9% availability SLO permits up to 0.1% of valid requests to fail within that window.

When the error budget is being consumed rapidly:

- Prioritize reliability work and reduce deployment risk.
- Limit unnecessary changes.
- Inspect dependencies, capacity, and failure patterns.
- Review rollout/canary/rollback policies.

Error budgets turn SLOs into a decision-making tool balancing feature velocity and reliability.

### 15.5. Alerting on User Impact

Prioritize alerts in this order:

- User-facing symptoms: availability, latency, error rate, failed transactions.
- Critical dependencies: unavailable database, queue age exceeding deadlines, downstream provider failures.
- Capacity risks: disk nearly full, connection pool exhaustion, sustained memory pressure.
- Telemetry pipeline failures: stopped agents, log ingestion gaps, trace export errors.

Do not page on-call for every CPU spike or warning log. Each alert should have a severity, owner, runbook, and clear action.

### 15.6. Multi-Window Alerting and Burn Rate

SLO burn rate indicates how fast the error budget is being consumed. A short window detects severe incidents quickly; a long window avoids paging on brief spikes.

You can design fast/slow alert pairs:

- Fast burn: error budget rapidly consumed over minutes, requiring a page.
- Slow burn: sustained reliability degradation over hours, creating a ticket or lower-priority alert.

CloudWatch SLOs/alarms can support tracking attainment and burn-rate signals depending on configuration. Define exact windows, thresholds, paging policies, and response times in the runbook.

## 16. Dashboards and Runbooks for Operations

### 16.1. Service Overview Dashboard

An overview dashboard for the Orders API can be organized into rows:

| Section | Recommended Widgets |
| --- | --- |
| User impact | Availability SLI, error rate, p95/p99 latency, request rate. |
| Application | CPU/memory, task count, duration, throttles, process health. |
| Dependencies | RDS connections/latency, SQS backlog/age, downstream API errors. |
| Deployment | Current version, deployment events, desired/running tasks. |
| Observability health | Agent status, log ingestion, missing metrics, trace volume/sampling. |

Dashboards should support environment/Region variants or use resource tags/filters so operators can locate the exact workload.

### 16.2. Dependency Dashboard

A dependency dashboard helps determine whether a failure is in the service or a downstream component:

- RDS: CPU, free storage, database connections, read/write latency, replica lag if applicable.
- SQS: visible/not visible messages, oldest message age, empty receives, DLQ depth.
- Lambda: invocations, errors, duration, throttles, concurrent executions.
- Load balancer: request count, target response time, 4xx/5xx, healthy host count.
- Downstream HTTP provider: request rate, error rate, timeouts, retry count.

Do not compare metrics with different statistics, periods, or dimensions without noting it explicitly. Dashboards should display units and time ranges.

### 16.3. Runbooks Linked to Alarms

A runbook for the HighOrdersErrorRate alarm should cover:

1. Identify environment, Region, deployment version, and start time.
2. Open the service dashboard and inspect availability/latency/error rate.
3. Use Logs Insights to filter ERRORs over the time range and gather trace IDs.
4. Open traces to identify the failing span or dependency.
5. Check dependency metrics, CloudTrail/deployment events, and recent config changes.
6. Choose mitigation: rollback, scale, disable feature, failover, or rate limit per approved playbook.
7. Confirm the SLI recovers and the alarm returns to OK.
8. Record the incident timeline, root cause, and preventive actions.

Runbooks must not contain secrets or unguarded instructions for modifying production. Link to dashboards, log queries, and service ownership.

### 16.4. Incident Timeline

When an incident occurs, standardize on UTC timezone and record:

- Time of the first alert.
- Start/end time of user impact.
- Most recent deployment/config change.
- Detection, acknowledgement, and mitigation times.
- Root cause and contributing factors.
- SLI/SLO impact and error budget consumed.
- Follow-up tasks with owners/due dates.

This data helps refine alert thresholds, detection coverage, and operational readiness.

## 17. Reference Architecture: Observing Orders on ECS, RDS, and SQS

~~~mermaid
flowchart TB
    subgraph APP["Workload account"]
      ECS["ECS Orders service"]
      RDS["RDS"]
      SQS["SQS + DLQ"]
      AGENT["CloudWatch Agent / ADOT Collector"]
      ECS --> RDS
      ECS --> SQS
      ECS --> AGENT
      RDS -. service metrics .-> CW
      SQS -. service metrics .-> CW
      ECS -. structured logs .-> LOGS
      AGENT -. host/container telemetry .-> CW
      AGENT -. logs/traces .-> LOGS
      AGENT -. traces .-> XRAY
    end
    subgraph OBS["Monitoring account"]
      CW["CloudWatch Metrics / Alarms"]
      LOGS["CloudWatch Logs"]
      XRAY["X-Ray / Application Signals"]
      DASH["Dashboards / SLOs / Application Map"]
      CW --> DASH
      LOGS --> DASH
      XRAY --> DASH
      DASH --> ONCALL["On-call / Incident tools"]
    end
~~~

A multi-account deployment can use OAM links to share appropriate metrics/logs/traces from workload accounts to a monitoring account. If using log subscriptions/Firehose, ensure delivery roles, destination policies, encryption, and retry behaviors are configured properly.

### 17.1. Data Flow

- The ECS task role grants the application permissions to call AWS APIs; the task execution role grants permissions to pull images/log configurations and ship logs per ECS settings.
- CloudWatch Agent/ADOT Collector uses a separate IAM role scoped strictly to publishing required metrics/logs/traces.
- CloudWatch alarms monitor service SLOs and infrastructure saturation.
- Structured logs include trace ID and deployment version.
- Trace spans capture database queries, SQS publishes, and downstream calls.
- Application Signals/App Map display service/dependency health.
- The monitoring account aggregates dashboards, alarms, and incident integrations.

Separate the application role from the telemetry agent role so neither component holds excessive permissions.

### 17.2. Pre-Go-Live Questions to Answer

- Are there metrics measuring request rate, errors, p95/p99, and saturation?
- Do log groups have retention/KMS/log class configured per policy?
- Does trace context propagate across synchronous and asynchronous calls?
- Are SLOs and alarms defined for critical user journeys?
- Is there a dashboard and runbook for every page-level alarm?
- Can telemetry be accessed from the monitoring account without overly broad permissions?
- Have alert routing, missing data handling, and agent failure been tested?
- Have ingestion, retention, query, metrics, and trace costs been estimated?

## 18. Security, Access Control, and Telemetry Data Governance

### 18.1. Least Privilege for Telemetry

Separate permissions by role:

- Application/agent publisher: PutMetricData, PutLogEvents, and required trace write APIs.
- Operator: read metrics/logs/traces, view alarms/dashboards.
- Observability administrator: create log groups, retention, metric filters, dashboards, alarms, and OAM links.
- Security/audit: access data within approved audit scope with an audit trail.

Do not grant CloudWatchFullAccess or LogsFullAccess to every workload role when it only needs to publish to a single namespace/log group.

### 18.2. Secrets and PII in Logs/Traces

Telemetry can inadvertently capture sensitive data:

- Authorization headers, cookies, API tokens.
- Passwords, connection strings, database query parameters.
- Email addresses, phone numbers, physical addresses, customer identifiers.
- Payment details or health/personal data.

Design logging schemas with an allowlist of fields; redact before emitting; use CloudWatch Logs data protection/masking when appropriate. Inspect exception messages and third-party SDK logs as well.

### 18.3. Encryption and Key Management

- CloudWatch metrics are service-managed; log groups have encryption at rest enabled by default.
- For CloudWatch Logs, a customer managed KMS key can be configured on log groups as required.
- Review KMS key policies, rotation, grants, and consumer decrypt permissions.
- For cross-account destinations, check both the source IAM policy and destination resource policy.
- Do not delete a KMS key still needed to decrypt stored logs.

### 18.4. CloudTrail and Auditing

CloudTrail records many control-plane API calls such as creating alarms, changing retention, subscription filters, log groups, dashboards, and OAM configurations. Use CloudTrail to audit who changed observability controls and when.

CloudTrail event history does not replace application logs or distributed traces. It records AWS API/control-plane actions; logs/traces describe behavior inside the application request path.

### 18.5. Data Residency and Retention

Identify the Regions where telemetry is stored, where data is shared/replicated, and any legal/contractual requirements. Retention must align with data classification and audit policies. Do not keep debug logs indefinitely without reason, and do not delete audit logs earlier than policy allows.

## 19. Cost and Telemetry Optimization

Observability incurs costs for ingestion, storage, queries, custom metrics, alarms, dashboards, traces, canaries, and data transfer. Costs vary by Region, volume, retention, resolution, and current pricing models.

### 19.1. Cost Drivers

| Component | Cost Factors |
| --- | --- |
| Metrics | Number of custom metrics/time series, dimensions, high-resolution datapoints, API usage. |
| Alarms | Number of metric alarms, high-resolution alarms, composite alarms, and query types. |
| Dashboards | Number of dashboards, widgets, and refresh frequency. |
| Logs | Data ingestion, storage volume, retention, log class, query scan volume, and subscriptions. |
| Traces | Trace ingestion, sampling rate, storage/analysis, and downstream integrations. |
| Application Signals | Service/operation telemetry, metrics, traces, and SLO usage per pricing. |
| Synthetics | Number of canary runs, runtime, and artifacts. |
| RUM | Number of user sessions/events collected. |
| Agents/Collectors | Compute resources, network transfer, and telemetry volume. |

### 19.2. Reducing Metric Costs

- Limit dimensions and cardinality.
- Avoid creating custom metrics that duplicate AWS service metrics.
- Choose standard resolution unless sub-minute detection is required.
- Batch/aggregate metrics where appropriate rather than sending a datapoint for every event.
- Clean up unused metrics; check dashboards/alarms before removing them.
- Use metric math/Metrics Insights for aggregation where appropriate instead of creating numerous time series just for dashboards.

### 19.3. Reducing Log Costs

- Choose appropriate production log levels; limit DEBUG.
- Redact/transform and drop unnecessary fields before ingestion.
- Set retention according to data classification.
- Choose log classes based on needed features.
- Use subscriptions/Firehose/S3 for long-term archiving when appropriate.
- Restrict Logs Insights time ranges and log groups.
- Avoid continuous dashboard refreshes causing repeated query scans.
- Check for log duplication caused by both application stdout and agent file tailing sending the same content.

### 19.4. Reducing Trace Costs

- Sample based on traffic/risk; prioritize errors/slow traces if the pipeline supports tail sampling.
- Do not capture large payloads/bodies or unnecessary attributes.
- Limit span events and high-cardinality attributes.
- Instrument only critical dependencies.
- Monitor collector queues/retries and export failures to avoid wasted cost.

### 19.5. Cost Ownership

Attach tags/metadata to log groups, dashboards, canaries, and workloads where supported. Assign owners to namespaces, log groups, and alarms. Periodically review:

- Which telemetry is ingested without any dashboard/query/alert consumer?
- Are any log groups set to indefinite retention unnecessarily?
- Are any custom metrics experiencing abnormal cardinality growth?
- Is the trace sampling rate too high relative to its investigative value?
- Are any canaries running too frequently or executing expensive test flows?
- Are there duplicate or ownerless alarms?

Do not blindly reduce sampling/retention during an active incident or when evidence is needed for a security investigation.

## 20. AWS CLI and Common Operational Tasks

The following commands are examples for querying/checking state. Replace accounts, Regions, resource IDs, and time ranges with values from your actual environment.

### 20.1. Listing Metrics by Namespace

~~~bash
aws cloudwatch list-metrics \
  --namespace AWS/SQS \
  --region ap-southeast-1
~~~

ListMetrics is not guaranteed to show every metric if a metric has no recent datapoints or has not been published within the query scope. When dimensions are known, use the appropriate metric explorer/API.

### 20.2. Getting EC2 CPU Statistics

~~~bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=i-0123456789abcdef0 \
  --start-time 2026-11-20T03:00:00Z \
  --end-time 2026-11-20T04:00:00Z \
  --period 300 \
  --statistics Average Maximum \
  --region ap-southeast-1
~~~

Start/end times use UTC and the period must align with resolution/retention. Returned datapoints may not be in chronological order; sort them before analysis.

### 20.3. Checking Alarms

~~~bash
aws cloudwatch describe-alarms \
  --state-value ALARM \
  --region ap-southeast-1
~~~

~~~bash
aws cloudwatch describe-alarms \
  --alarm-names OrdersBacklogAlarm \
  --region ap-southeast-1
~~~

Inspect StateReason, metric dimensions, threshold, evaluation periods, treat missing data, and actions.

### 20.4. Listing Log Groups

~~~bash
aws logs describe-log-groups \
  --log-group-name-prefix /orders/prod \
  --region ap-southeast-1
~~~

Check retentionInDays, storedBytes, logGroupClass, and kmsKeyId in the response. If retention is not set, data may remain stored until deleted manually.

### 20.5. Running a Logs Insights Query

StartQuery accepts epoch seconds for start/end time:

~~~bash
aws logs start-query \
  --log-group-names /orders/prod/application \
  --start-time 1795143600 \
  --end-time 1795147200 \
  --query-string 'fields @timestamp, level, message, trace_id | filter level = "ERROR" | sort @timestamp desc | limit 50' \
  --region ap-southeast-1
~~~

The command returns a queryId. Retrieve results with:

~~~bash
aws logs get-query-results \
  --query-id QUERY-ID \
  --region ap-southeast-1
~~~

A query can be in Scheduled/Running/Complete/Failed/Cancelled state. Do not poll aggressively; wait reasonable intervals and narrow the time range to reduce scan volume.

### 20.6. Inspecting X-Ray Traces

Use the CloudWatch console Trace Map or X-Ray trace views to filter by service, time range, error/fault, and latency. CLI/APIs can retrieve trace summaries/details subject to permissions and retention; trace data may be sampled so not every request appears.

## 21. Testing Observability Before Production

### 21.1. Unit and Component Tests

Verify application instrumentation/logging at the code level:

- Every request has a valid correlation/request ID.
- Logs include timestamp, severity, service, environment, and trace ID per schema.
- Secrets/PII are not logged in success/error paths.
- Error handling records accurate status/error codes.
- Custom metrics have consistent namespace/name/dimensions.
- Instrumentation does not create duplicate spans or drop context on downstream calls.

### 21.2. Integration Tests

In an AWS sandbox:

1. Deploy the workload and CloudWatch Agent/ADOT Collector via IaC.
2. Send synthetic traffic with known request IDs.
3. Verify metrics appear with the expected namespace/dimensions/units.
4. Verify logs arrive in the expected log group/stream with correct retention and KMS policy.
5. Query logs with Logs Insights and locate the trace ID.
6. Verify traces contain both inbound and downstream spans.
7. Create a low-threshold test alarm in the sandbox and verify SNS routing.
8. Perform a controlled stop of the agent/collector to verify telemetry health alerts.
9. Verify dashboards and runbook links.
10. Measure ingestion/query volume and estimate cost.

### 21.3. Failure-Path Tests

- IAM role missing PutMetricData or PutLogEvents.
- CloudWatch Agent unable to fetch SSM config.
- Log group in the wrong Region or missing retention.
- Subscription destination policy denying delivery.
- Collector losing network connectivity or exporter being throttled.
- Trace context breaking across async messages.
- Metrics having no datapoints and alarms mis-handling missing data.
- Logs Insights query scanning too broadly.
- KMS key policy blocking log reads.
- RUM/Synthetics canary reporting false positives due to unstable test dependencies.

Test both application failures and telemetry pipeline failures. A system can be failing silently if the telemetry collector is also broken.

## 22. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "Monitoring and observability are the same thing." | Monitoring alerts on known signals; observability supports inferring internal state from telemetry. |
| "Metrics, logs, and traces can replace one another." | Metrics show trends, logs capture events, traces show request paths and timing. |
| "EC2 CPU shows memory usage inside the OS." | Guest memory typically requires CloudWatch Agent or other telemetry. |
| "More dimensions are always better." | High cardinality increases time series/costs and makes queries/alarms harder to manage. |
| "Average latency is enough to understand user experience." | p95/p99 reveal tail latency and outliers. |
| "High-resolution metrics should be enabled for everything." | Use only when sub-minute detection is needed and actionable. |
| "Metric retention keeps 1-second datapoints long-term." | High-resolution data under 60 seconds is retained for only 3 hours before aggregation. |
| "No datapoints means the system is healthy." | The metric may not be emitting, the agent may be dead, or telemetry may be lost; missing-data policy must match semantics. |
| "An alarm only needs a threshold." | It needs period, M/N, missing-data behavior, an owner, and a runbook. |
| "Every alarm should page on-call." | Page for real user impact/risk; other warnings can open tickets. |
| "Keeping logs forever is best." | Retention must balance audit, privacy, and cost. |
| "Grepping text logs is enough." | Structured JSON and Logs Insights filter/aggregate/correlate much more effectively. |
| "Broader Logs Insights queries make investigation easier." | Choose exact log groups and narrow time ranges to reduce scan/cost. |
| "Metric filters can replace all application metrics." | Metric filters suit simple patterns; business metrics should be instrumented explicitly or via EMF. |
| "Subscription filters are a complete archive solution." | Subscription delivery and long-term archiving are distinct requirements. |
| "Trace ID should be a metric dimension." | Trace ID has high cardinality; keep it in logs/traces. |
| "Each service sampling independently is fine." | Independent sampling can fragment traces; a shared propagation/sampling strategy is needed. |
| "X-Ray SDK is still the best choice for new apps." | X-Ray SDK/daemon entered maintenance mode and end support on 25-02-2027; prefer OpenTelemetry/ADOT. |
| "Application Map and X-Ray Trace Map are the same view." | Application Map focuses on service/dependency health; Trace Map focuses on trace topology. |
| "RUM and Synthetics are the same." | RUM observes real user sessions; Synthetics proactively runs scheduled canary tests. |
| "CloudWatch Agent replaces all instrumentation." | The agent collects telemetry; applications still need instrumentation, log schemas, and trace context. |
| "A dashboard with many widgets means good observability." | Dashboards must answer operational questions and support decisions. |
| "SLO is SLA." | An SLO is an internal/operational objective; an SLA is a customer-facing service commitment. |
| "CloudTrail replaces application logs." | CloudTrail records AWS API/control-plane activity; application logs/traces describe request execution. |
| "Telemetry never contains sensitive data." | Logs/traces can inadvertently capture tokens, PII, and payloads; redaction and access controls are essential. |

## 23. Practice Exercises with Suggested Answers

### Exercise 1 — Choosing Metrics for the Orders API

**Prompt:** The team only tracks CPUUtilization, yet customers report slow checkout.

**Answer:** Add request rate, error rate, p95/p99 latency, and dependency latency. Track RDS query time, connection count, SQS backlog/age, and traces to pinpoint the bottleneck.

### Exercise 2 — Custom Metric Dimensions

**Prompt:** A developer wants to publish PaymentLatency with OrderId and CustomerId dimensions.

**Answer:** Do not use high-cardinality IDs as dimensions. Use Service, Environment, Provider, and Operation; record OrderId/CustomerId in structured logs/traces if permitted and covered by privacy policies.

### Exercise 3 — EC2 Memory Usage

**Prompt:** The dashboard only has CPUUtilization and the team wants visibility into memory pressure on a Linux instance.

**Answer:** Install the unified CloudWatch Agent with an appropriate IAM role, configure memory measurements, and use consistent namespace/dimensions. Do not expect default EC2 metrics to provide guest memory.

### Exercise 4 — High-Resolution Metrics

**Prompt:** A workload needs saturation detection within 10 seconds.

**Answer:** Consider custom high-resolution metrics and a high-resolution alarm with an appropriate period. Evaluate datapoint volume, cost, sampling, and on-call response capability before enabling.

### Exercise 5 — Low Average Latency Despite Customer Complaints

**Prompt:** Average latency is 120 ms, yet many requests take up to 4 seconds.

**Answer:** Inspect p95/p99, break down by operation/Region/version, and use traces to find tail latency. Averages do not fully represent user experience.

### Exercise 6 — Alarm Transitioning to INSUFFICIENT_DATA

**Prompt:** A queue age alarm has no datapoints during the evaluation window.

**Answer:** Determine whether the metric emits continuously or only on events, and check the queue/Region/dimensions and agent/service telemetry. Choose appropriate missing-data treatment; do not automatically assume missing means healthy.

### Exercise 7 — Growing Queue Backlog with Low Worker CPU

**Prompt:** SQS backlog is rising while worker CPU remains low.

**Answer:** Check worker concurrency, message visibility, permissions, downstream throttling, poison messages, and consumer errors. Low CPU can occur when workers are blocked waiting on a dependency or failing to receive messages.

### Exercise 8 — Tracing Errors by Trace ID

**Prompt:** Customer support provides a request ID; the operator needs to inspect the full request path.

**Answer:** Search structured logs by request ID, retrieve the trace ID, open the trace, and inspect spans/dependencies. Do not turn request ID into a metric dimension.

### Exercise 9 — Logs Insights Query Scanning Too Much Data

**Prompt:** Querying ERROR across all log groups for 30 days is slow and expensive.

**Answer:** Select the specific service log groups, narrow the time range, filter early on level/service, use field indexes where supported, and save runbook queries.

### Exercise 10 — Log Group Stored Indefinitely

**Prompt:** An application log group has no retention configured.

**Answer:** Identify audit/data classification policies, choose retention, encryption/KMS, and export/archiving if required. Manage the log group via IaC so retention does not rely on manual console configuration.

### Exercise 11 — Turning ERROR Logs into an Alarm

**Prompt:** The team wants an alert when the application writes many JSON logs with level ERROR.

**Answer:** Create a metric filter on a Standard log group matching JSON level=ERROR, publish a metric, and create an alarm. For business errors, consider instrumenting custom metrics/EMF to distinguish error classes.

### Exercise 12 — Broken Trace at SQS Worker

**Prompt:** The API trace ends after SendMessage; the worker trace is not linked to the API request.

**Answer:** Check trace context propagation across message metadata, the OTel propagator, and consumer extraction. If an async workflow does not fit a single parent-child trace, use correlation IDs/span links per semantics.

### Exercise 13 — Legacy X-Ray SDK

**Prompt:** A Java service uses the X-Ray SDK/daemon and is scheduled for an upgrade in 2026.

**Answer:** Plan a migration to OpenTelemetry/ADOT. X-Ray SDK/daemon entered maintenance on 25-02-2026 and support ends on 25-02-2027; verify instrumentation, context propagation, collector, and trace backend.

### Exercise 14 — RUM or Synthetics?

**Prompt:** The team needs to know whether the checkout page works and whether real users are hitting JavaScript errors.

**Answer:** Use Synthetics to run scheduled scripted journeys; use RUM to observe real browser sessions. Combine with backend metrics/traces to link client impact to service failures.

### Exercise 15 — Too Many Page Alerts

**Prompt:** On-call receives hundreds of alerts for brief CPU spikes that have no user impact.

**Answer:** Switch to symptom/SLO-based alarms, using M out of N, composite alarms, or anomaly detection where appropriate. Separate warnings from page-level alerts and attach runbooks to each alarm.

### Exercise 16 — Centralizing Logs Across Multiple Accounts

**Prompt:** An organization has 20 workload accounts and one monitoring account.

**Answer:** Design OAM sinks/links or log centralization/subscriptions based on the use case. Scope source accounts, Regions, log groups, IAM/KMS policies, and retention. Do not share all logs if the monitoring team only needs a subset of telemetry.

## 24. Self-Check Questions

**Question 1.** How does observability differ from monitoring?  
**Answer:** Monitoring tracks predefined signals and alerts; observability helps infer internal system state from telemetry.

**Question 2.** What are the three primary telemetry types?  
**Answer:** Metrics, logs, and traces.

**Question 3.** What question do metrics answer?  
**Answer:** What is changing, and what are its magnitude and trend.

**Question 4.** What question do logs answer?  
**Answer:** What specific event occurred.

**Question 5.** What does a distributed trace show?  
**Answer:** A request's path across services/dependencies and the duration of each operation.

**Question 6.** What is a CloudWatch namespace used for?  
**Answer:** Grouping metrics by AWS service or custom metric domain.

**Question 7.** What is a dimension?  
**Answer:** A name/value pair identifying a resource or categorizing a metric time series.

**Question 8.** Why shouldn't OrderId be used as a metric dimension?  
**Answer:** High cardinality creates many time series and increases cost and complexity.

**Question 9.** What is the p99 percentile used for?  
**Answer:** Evaluating tail latency; 99% of datapoints/requests fall below that percentile as defined by the metric.

**Question 10.** Which StorageResolution does a high-resolution custom metric use?  
**Answer:** 1.

**Question 11.** How long are high-resolution datapoints under 60 seconds retained before aggregation?  
**Answer:** 3 hours.

**Question 12.** Do default AWS EC2 metrics include guest memory usage?  
**Answer:** No; CloudWatch Agent or another telemetry source is typically required.

**Question 13.** What does CloudWatch Agent collect?  
**Answer:** Guest OS metrics, file logs, and certain telemetry/trace sources as configured.

**Question 14.** What is EMF?  
**Answer:** Embedded Metric Format; structured JSON log events from which CloudWatch extracts metrics.

**Question 15.** How are logs organized structurally?  
**Answer:** Log groups, log streams, and log events.

**Question 16.** What can happen if log retention is not set?  
**Answer:** Log events may be stored indefinitely.

**Question 17.** What is Logs Insights used for?  
**Answer:** Querying, filtering, parsing, aggregating, and visualizing log data.

**Question 18.** How does a metric filter differ from a Logs Insights query?  
**Answer:** A metric filter turns pattern-matching events into metric datapoints; a Logs Insights query analyzes log records on demand.

**Question 19.** What is a subscription filter used for?  
**Answer:** Forwarding log events to destinations such as Lambda, Kinesis Data Streams, or Firehose.

**Question 20.** What states can a CloudWatch alarm have?  
**Answer:** OK, ALARM, and INSUFFICIENT_DATA.

**Question 21.** What do EvaluationPeriods and DatapointsToAlarm represent?  
**Answer:** N is the number of periods evaluated; M is the number of datapoints within N that must breach for the alarm to transition to ALARM.

**Question 22.** What options exist for TreatMissingData?  
**Answer:** breaching, notBreaching, ignore, and missing.

**Question 23.** What is the purpose of a composite alarm?  
**Answer:** Combining alarm states to reduce noise and alert only when composite conditions are met.

**Question 24.** What is metric math used for?  
**Answer:** Combining/transforming metric time series, such as calculating an error rate.

**Question 25.** What is Metrics Insights?  
**Answer:** An SQL-like query language for querying and aggregating CloudWatch metrics.

**Question 26.** How do a trace and a span differ?  
**Answer:** A trace is the entire request path; a span is a single operation within the trace.

**Question 27.** What does trace context propagation do?  
**Answer:** Passes trace identity/parent context across services so spans link to the same request.

**Question 28.** What is ADOT?  
**Answer:** AWS Distro for OpenTelemetry, an AWS-supported distribution of OpenTelemetry SDKs/Collector.

**Question 29.** When did X-Ray SDKs/daemon enter maintenance mode?  
**Answer:** 25-02-2026.

**Question 30.** What end-of-support date did AWS announce for X-Ray SDKs/daemon?  
**Answer:** 25-02-2027.

**Question 31.** How does Application Signals help?  
**Answer:** Observing service operations, dependencies, health metrics, and SLOs.

**Question 32.** How does Application Map differ from X-Ray Trace Map?  
**Answer:** Application Map focuses on service/dependency topology and health; Trace Map focuses on topology derived from trace data.

**Question 33.** How does RUM differ from Synthetics?  
**Answer:** RUM collects data from real user sessions; Synthetics proactively runs scheduled canary tests.

**Question 34.** How do SLI and SLO differ?  
**Answer:** An SLI is a measurement; an SLO is the target for that measurement over an evaluation window.

**Question 35.** Why should an alert link to a runbook?  
**Answer:** So responders know the impact, where to investigate, safe mitigation steps, and how to confirm recovery.

## 25. Production Checklist and References

### 25.1. Pre-Production Checklist

1. Identify service owners, critical user journeys, and business impact.
2. Define SLIs/SLOs for availability, latency, and critical workflows.
3. Include golden signals: traffic, errors, latency, and saturation.
4. Ensure metrics have stable namespaces, metric names, units, and dimensions.
5. Keep high-cardinality identifiers out of metric dimensions.
6. Give CloudWatch Agent/ADOT Collector least-privilege IAM roles and manage configs as code.
7. Ensure log groups have clear naming, class, retention, encryption/KMS, and access policies.
8. Ensure application logs follow a structured schema with UTC timestamps, request ID, and trace ID.
9. Redact secrets/PII before emitting; enable data protection/masking where appropriate.
10. Scope Logs Insights queries to limited time ranges/log groups and store them in runbooks.
11. Ensure metric filters/EMF/custom metrics do not create duplicate signals.
12. Propagate trace context across synchronous and asynchronous boundaries.
13. Prefer OpenTelemetry/ADOT for new instrumentation; maintain a migration plan for legacy X-Ray SDK/daemon.
14. Enable Application Signals/SLOs/Application Map for supported services.
15. Configure alarms with clear period, M/N, missing-data treatment, severity, owner, and action.
16. Use composite alarms/anomaly detection to reduce noise where appropriate.
17. Build dashboards showing user impact, dependencies, deployments, and observability health.
18. Choose RUM/Synthetics based on questions about real users versus proactive journey checks.
19. Review source scope, destination policies, and KMS/IAM for cross-account sharing/OAM links.
20. Audit changes to observability controls with CloudTrail/audit logs.
21. Test agent failures, missing metrics, log delivery, trace propagation, and alarm routing.
22. Estimate metrics/logs/traces/SLOs/RUM/Synthetics/query costs by Region.
23. Maintain runbooks, escalation paths, incident timelines, and post-incident reviews.
24. Periodically review retention, data residency, and privacy requirements.

### 25.2. Conclusion

CloudWatch provides a platform to observe AWS workloads through metrics, logs, traces, alarms, dashboards, and application-level signals. Metrics detect trends and scope of impact; logs explain specific events; traces connect processing steps of a single request across multiple services.

An effective observability strategy starts from user journeys and SLOs, selects telemetry with sensible cardinality and retention, correlates data via trace/request IDs, alerts on impact, and equips on-call engineers with runbooks. Combined with least-privilege IAM, redaction, KMS, multi-account governance, and cost controls, CloudWatch enables operations teams to systematically detect, investigate, and recover from incidents.

### 25.3. Official AWS Documentation

- [Amazon CloudWatch User Guide](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html) — overview of CloudWatch, metrics, alarms, and dashboards.
- [CloudWatch metrics concepts](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_concepts.html) — namespaces, dimensions, resolution, and statistics.
- [CloudWatch GetMetricData and retention](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricData.html) — metric querying and retention by resolution.
- [CloudWatch alarms evaluation](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/alarm-evaluation.html) — Period, EvaluationPeriods, DatapointsToAlarm, and high-resolution alarms.
- [Treating missing data](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/alarms-and-missing-data.html) — how alarms handle missing datapoints.
- [Metric math alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Create-alarm-on-metric-math-expression.html) — creating alarms on metric math expressions.
- [CloudWatch Agent](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Install-CloudWatch-Agent.html) — collecting metrics, logs, and traces.
- [CloudWatch Logs getting started](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_GettingStarted.html) — log groups, streams, and the agent.
- [CloudWatch Logs Insights query syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html) — query language, commands, and cost tips.
- [CloudWatch Logs log classes](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CloudWatch_Logs_Log_Classes.html) — capabilities by log class.
- [Metric filter syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/FilterAndPatternSyntaxForMetricFilters.html) — turning logs into metrics.
- [CloudWatch Application Map](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/ServiceMap.html) — service/dependency topology and health.
- [CloudWatch Application Signals SLOs](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-ServiceLevelObjectives.html) — SLO configuration and attainment.
- [CloudWatch and X-Ray integration](https://docs.aws.amazon.com/xray/latest/devguide/xray-services-cloudwatch.html) — trace correlation, RUM, and Application Signals.
- [Instrument applications with ADOT or X-Ray](https://docs.aws.amazon.com/xray/latest/devguide/xray-instrumenting-your-app.html) — instrumentation options.
- [X-Ray SDK and Daemon support timeline](https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-daemon-timeline.html) — maintenance and end-of-support timeline.
- [CloudWatch X-Ray trace map](https://docs.aws.amazon.com/xray/latest/devguide/xray-console-servicemap.html) — analyzing request paths and dependencies.
