# CloudWatch Namespace, Dimension, Statistic, and Period

> **Chapter:** Observability with CloudWatch  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem through Region/AZ infrastructure, IAM, VPC, compute services, storage, databases, integration, and serverless. Learners build the ability to select services, design, and deploy secure applications with monitoring, recovery, and cost control.

## Learning Objectives

Amazon CloudWatch Metrics is the time-series data foundation for observing AWS workloads. To read a chart accurately or design a custom metric, you need to understand four interconnected concepts:

- **Namespace** defines the naming container holding metrics;
- **Dimension** identifies the variant/entity that the metric describes;
- **Statistic** specifies how data points are aggregated;
- **Period** specifies the time interval over which aggregation occurs.

This lesson progresses from metric identity to publishing/querying, choosing statistics for each data type, selecting periods by resolution and retention, and applying those decisions to dashboards and alarms.

After this lesson, you will be able to:

1. Identify a CloudWatch metric by namespace, metric name, and dimension set.
2. Design manageable custom namespaces that avoid mixing metrics across applications.
3. Choose stable, useful dimensions while controlling cardinality.
4. Distinguish standard resolution from high resolution.
5. Select Sum, SampleCount, Average, Minimum, Maximum, and percentiles based on data semantics.
6. Explain statistic sets and limitations when querying percentiles.
7. Choose periods matching metric resolution, query needs, and retention windows.
8. Publish custom metrics using AWS CLI and AWS SDK for Java 2.x.
9. Query metrics using GetMetricData, metric math, and the CloudWatch console.
10. Avoid common mistakes when building alarms, dashboards, and statistics.

## 1. CloudWatch Metrics Data Model

### 1.1. A Metric Is a Time-Ordered Data Series

A metric is a collection of data points published with timestamps. For example, a checkout application might emit order processing duration, successful order creation counts, and failed payment provider call counts.

A data point typically consists of:

- Namespace;
- Metric name;
- Zero or more dimensions;
- Timestamp;
- Value or statistic set;
- Optional unit;
- Storage resolution for custom metrics.

CloudWatch metrics are Region-scoped. A metric published in ap-southeast-1 does not automatically appear in ap-southeast-2; observing across multiple Regions requires querying each Region or using metric math/cross-account observability per an appropriate architecture.

### 1.2. Identity of a Metric

You can remember metric identity as follows:

~~~text
Metric identity
  = AWS account + Region
  + Namespace
  + MetricName
  + exact Dimension set
~~~

The account and Region define the CloudWatch storage scope. Within that scope, the namespace, metric name, and dimension combination uniquely identify the time series. Unit is not a dimension; data points with different units are handled by CloudWatch as separate statistical streams.

Example:

~~~text
Account: 111122223333
Region: ap-southeast-1
Namespace: Acme/Checkout
MetricName: RequestLatency
Dimensions:
  Environment = production
  Operation   = CreateOrder
Unit: Milliseconds
~~~

Another metric with Environment=staging or Operation=Refund is a distinct time series, even though the namespace and metric name are identical.

### 1.3. Four Non-Interchangeable Concepts

| Concept | Question Answered | Example |
|---|---|---|
| Namespace | Which system/group does the metric belong to? | Acme/Checkout |
| Dimension | Which entity/group does the metric describe? | Environment=production |
| Statistic | How are samples aggregated? | Average, Sum, p95 |
| Period | Over what duration are they aggregated? | 60 seconds |

A query configuration can select the right metric yet still return misleading results if the statistic or period is inappropriate. For example, the Sum of CPU utilization does not have the same meaning as Average; a one-minute Average latency can mask brief slow-request spikes.

### 1.4. AWS Metrics and Custom Metrics

AWS services publish metrics into service namespaces, typically following the pattern AWS/Service, such as:

- AWS/EC2;
- AWS/Lambda;
- AWS/RDS;
- AWS/SQS;
- AWS/ApplicationELB.

Custom metrics are published by your applications, agents, or telemetry pipelines. You design the namespace, metric name, dimensions, unit, and resolution. A custom metric does not appear automatically simply because an application writes logs; it must be published via PutMetricData, CloudWatch Agent, Embedded Metric Format (EMF), or an appropriate integration.

## 2. Namespace: Partitioning Metrics by System

### 2.1. What Is a Namespace?

A namespace is a logical container for metrics. Metrics in different namespaces are isolated so applications do not accidentally mix statistics into the same bucket.

CloudWatch has no default namespace. Every published data point must specify a namespace. Namespace names can be up to 255 characters long and use valid ASCII characters.

AWS typically names service namespaces as AWS/<service>. For custom metrics, use an organization or product prefix, for example:

~~~text
Acme/Checkout
Acme/Payments
Acme/Inventory
Acme/Platform/API
~~~

Do not name custom namespaces starting with AWS/, because that prefix is reserved for metrics published by AWS services.

### 2.2. Namespace Naming Rules

A good namespace should:

- Align with a bounded context or system with clear ownership;
- Follow a stable naming convention across environments;
- Never contain timestamps, request IDs, or values that change per deployment;
- Not create a new namespace per instance or container;
- Be documented in dashboards, runbooks, and a metric catalog.

You can put the environment into a dimension (Environment=production) so one namespace serves multiple environments. If environments have completely separate ownership, retention, or access permissions, an organization may split namespaces; pick one consistent convention.

### 2.3. A Namespace Is Not a Region

Namespaces do not aggregate metrics across Regions. Acme/Checkout in Singapore and Acme/Checkout in Sydney remain data in two separate Regions. When investigating an incident, verify the Region before concluding a metric is missing.

### 2.4. Metric Lifecycle

Metrics do not have a direct delete operation like deleting a file. When a metric stops receiving new data points, old data expires per retention rules; metrics with no new data points for 15 months expire automatically.

A metric with no new data points for two weeks may disappear from console listings or ListMetrics results. To query older metrics, use GetMetricData or GetMetricStatistics with the exact namespace, name, and dimensions.

## 3. Dimension: Identifying Metric Variants

### 3.1. A Dimension Is a Name/Value Pair

A dimension is a name/value pair describing a metric. Examples:

~~~text
Environment = production
Service     = checkout
Operation   = CreateOrder
AvailabilityZone = ap-southeast-1a
InstanceId  = i-0123456789abcdef0
~~~

AWS services typically attach dimensions such as InstanceId, LoadBalancer, TargetGroup, FunctionName, or QueueName. When querying, dimensions help select the exact target entity.

A single metric can have up to **30 dimensions**. However, the maximum limit is not a design target. Every dimension value combination creates a separate metric identity, so adding dimensions increases the number of time series to manage and can raise custom metric costs.

### 3.2. The Exact Dimension Set Is Part of Identity

Suppose a publisher emits two metrics:

~~~text
RequestLatency
  Environment=production

RequestLatency
  Environment=production, Operation=CreateOrder
~~~

These are two separate metric identities. For custom metrics, CloudWatch does not automatically roll up a two-dimension variant into a one-dimension metric. If you only publish the Environment + Operation combination, querying with Environment alone will not automatically produce the aggregate latency across all operations.

To get both views, you can:

- Publish an additional aggregate metric with only Environment;
- Query individual time series and combine them with metric math;
- Use metric math SEARCH to match multiple relevant metrics;
- Design dimension sets upfront around the dashboards and alarms to be supported.

Some AWS service metrics support aggregation across dimensions, but do not assume that behavior applies to custom metrics.

### 3.3. Dimension Combinations Create New Metrics

For example, the following combinations form four time series:

~~~text
Service=checkout, Environment=production
Service=checkout, Environment=staging
Service=payment,  Environment=production
Service=payment,  Environment=staging
~~~

If you add CustomerId with millions of values, the number of time series grows rapidly. This is a cardinality explosion: the metric catalog becomes hard to manage, queries and dashboards struggle to aggregate, and costs can spike sharply.

### 3.4. Choosing Operationally Useful Dimensions

Good dimensions answer operational questions:

| Dimension | Example Value | Used For |
|---|---|---|
| Environment | production | Separating prod/staging |
| Service | checkout | Comparing services |
| Operation | CreateOrder | Identifying failing endpoints/operations |
| Region | ap-southeast-1 | Use only if you want Region as a custom dimension |
| InstanceId | i-... | Analyzing individual instances |

Avoid dimensions whose values are nearly unique per event:

- Request ID;
- Trace ID;
- User ID;
- Email;
- Session ID;
- Timestamp;
- URL paths containing dynamic IDs like /orders/12345.

Those values belong in structured logs or traces. Metrics aggregate over stable groups; logs/traces investigate individual requests.

### 3.5. Dimensions Are Not Automatic Tag Filters

Resource tags do not automatically become dimensions on every metric. To filter metrics by tag, you need a metric integration that supports it (such as Metrics Explorer with resource tags) or you must publish corresponding dimensions.

Do not assume adding a Team=Payments tag to an EC2 instance automatically creates a Team dimension on all AWS/EC2 metrics. Verify the actual dimensions published by the service and the CloudWatch feature being used.

### 3.6. Account, Region, and Dimensions in Cross-Account Observability

Metrics are stored in the account/Region where they are published. With cross-account observability, a monitoring account can view metrics from source accounts via linking; the source account can be surfaced in query results/labels.

There is no need to stuff account IDs into dimensions just to distinguish metrics when CloudWatch already preserves account context. Only add an Account dimension if it is genuinely a business attribute of a custom metric that requires dimension-based querying.

## 4. Unit and Timestamp

### 4.1. Unit Describes the Meaning of a Value

Commonly used units:

- Count;
- Count/Second;
- Milliseconds;
- Seconds;
- Bytes;
- Bytes/Second;
- Percent.

CloudWatch does not automatically convert Milliseconds to Seconds, nor Bytes to Megabytes. Units help readers interpret data and separate streams that use different units.

If no unit is specified when publishing a custom metric, CloudWatch assigns None. Documenting units in the metric catalog and publisher prevents confusion across teams.

If the same metric identity receives data points with inconsistent units, queries may return multiple data streams or return no data when filtering by the wrong unit. Choose one canonical unit per metric and keep it consistent.

### 4.2. Units Do Not Replace Metric Names

Do not publish a Latency metric sometimes in milliseconds and sometimes in seconds expecting CloudWatch to normalize it. Metric names and units must have consistent meaning. Use clear names such as RequestLatency with unit Milliseconds, or RequestLatencySeconds with unit Seconds.

### 4.3. Timestamp and UTC

Every data point has a timestamp. If no timestamp is provided, CloudWatch assigns the ingestion time. AWS recommends using UTC; query and alarm times are also evaluated in UTC.

For custom metrics, timestamps can be up to two weeks in the past and two hours in the future. Timestamps skewed too far from current time can leave alarms in INSUFFICIENT_DATA or delay notifications.

Do not use arbitrary local timezones in producers. Synchronize clocks on hosts/containers and normalize event times before publishing.

## 5. Resolution: Standard and High Resolution

### 5.1. Standard Resolution

Most metrics published by AWS services are standard resolution with one-minute granularity. Standard custom metrics are also the default when publishing a metric without specifying high resolution.

Standard resolution works well for:

- CPU utilization, network throughput;
- Queue depth;
- Per-minute request counts;
- Per-minute error rates;
- Business metrics that do not require sub-minute reaction.

### 5.2. High Resolution

Custom metrics can be published with StorageResolution=1 to store data at one-second granularity. High-resolution metrics support sub-minute visibility, useful for short spikes, queue processing bursts, or latency on high-traffic services.

Example:

~~~json
{
  "MetricName": "RequestLatency",
  "Value": 245.7,
  "Unit": "Milliseconds",
  "StorageResolution": 1
}
~~~

Omitting StorageResolution or passing 60 stores the metric at standard resolution. High resolution does not improve the application itself; choose it only when lower observation latency is genuinely required.

### 5.3. Query Periods by Resolution

For standard metrics, the minimum period is 60 seconds and must be a multiple of 60.

For high-resolution metrics, you can query at sub-minute periods such as 1, 5, 10, 30 seconds, as well as multiples of 60 seconds. The MetricStat API also lists a 20-second period for high-resolution data. High-resolution alarms can use 10- or 30-second periods; standard alarms use periods that are multiples of 60 seconds.

If you select a 10-second period on a standard metric, CloudWatch cannot synthesize true 10-second data from samples recorded only at one-minute resolution.

### 5.4. High Resolution Impact on Cost

High-resolution metrics help when rapid response is needed, but denser publishing can increase API request counts and custom metric costs. High-resolution 10/30-second alarms also cost more than standard alarms.

Start with standard resolution. Upgrade to high resolution only for metrics with a clear requirement for detecting sub-minute spikes or latency; document the rationale and metric owner.

## 6. Statistic: How Does CloudWatch Aggregate Data Points?

### 6.1. Five Basic Statistics

CloudWatch provides five basic statistics:

| Statistic | Meaning |
|---|---|
| SampleCount | Number of data points/samples in the period |
| Sum | Sum of sample values |
| Average | Sum / SampleCount |
| Minimum | Smallest value in the period |
| Maximum | Largest value in the period |

For example, suppose a period has four latency samples: 100, 120, 130, and 450 milliseconds.

- SampleCount = 4;
- Sum = 800;
- Average = 200;
- Minimum = 100;
- Maximum = 450.

Average describes the mean, but does not reveal tail latency. Maximum shows the highest point, but is easily skewed by a single outlier. Choose the statistic according to the question you want to answer.

### 6.2. Choosing Statistics by Metric Type

| Metric Type | Commonly Used Statistic | Reason |
|---|---|---|
| Counter: orders created | Sum | Total events in the period |
| Request count | Sum | Total requests |
| Request latency | Average, p95, p99, Maximum | Mean and tail latency |
| CPU utilization | Average, Maximum | Mean load and peak load |
| Queue depth | Average, Maximum | Backlog level and peak backlog |
| Batch size | Average, Maximum, SampleCount | Size and frequency of batches |
| Error count | Sum | Total errors in the period |

For counters, Sum is usually more meaningful than Average. For gauges like CPU utilization, Average/Maximum is usually more useful than Sum. For latency, p95/p99 highlights the experience of slow requests.

### 6.3. Average Can Mask Tail Latency

Suppose a single minute has thousands of fast requests and a small group of very slow requests. Average can remain low even though some customers waited a long time.

- Average answers: what is the mean duration?
- p95 answers: what threshold are 95% of samples at or below per percentile calculation?
- p99 focuses on the more severe tail.
- Maximum shows the highest sample in the period.

Do not rely on a single statistic for every purpose. A dashboard can show Average and p95; an alarm can use p95 or error count depending on the SLO.

### 6.4. Percentiles and Extended Statistics

CloudWatch supports percentiles such as p50, p90, p95, p99, and other extended statistics. Percentiles reveal data distribution instead of a single mean value.

Other extended statistics include trimmed mean (tm99), interquartile mean (IQM), winsorized mean (WM), trimmed count (TC), trimmed sum (TS), and percentile rank (PR). These can be useful when analyzing latency distributions or histogram-like buckets.

Not all AWS service metrics support percentiles. For custom metrics, percentiles require raw, unsummarized samples and are not supported for metrics with negative values.

### 6.5. Statistic Sets

When sample volume is high, a publisher can send a statistic set instead of each raw data point. A statistic set contains:

- Minimum;
- Maximum;
- Sum;
- SampleCount.

For example, in one minute, an application measures 100 request latency samples. It can publish the min, max, sum, and sample count for that minute to query Average, Minimum, Maximum, and SampleCount.

**Important limitation:** CloudWatch can only compute percentiles from a statistic set in special cases:

1. SampleCount=1 and Min, Max, Sum are all equal; or
2. Min=Max and Sum=Min × SampleCount.

If you need p95/p99 latency, publish raw samples (or use a telemetry pipeline supporting appropriate distributions); do not send only pre-aggregated statistic sets.

### 6.6. Units and Statistic Aggregation

CloudWatch aggregates data points by namespace, metric name, dimension set, unit, and period. If the same metric identity receives data points with different units, they are aggregated into separate data streams.

CloudWatch does not convert units while computing Average, Sum, or percentiles. Standardize units across producers and queries.

## 7. Period: The Aggregation Interval

### 7.1. What Is a Period?

A period is the length of time CloudWatch uses to compute a statistic. Period is measured in seconds.

For example, if period is 60 seconds:

- Sum is the total of samples in each minute;
- Average is the mean of samples in each minute;
- Maximum is the highest value in each minute;
- p95 is the percentile of samples in each minute.

If period is 300 seconds, each statistic represents a five-minute interval. Longer periods smooth charts but can hide short spikes.

### 7.2. Valid Periods

For standard-resolution metrics, the period must be at least 60 seconds and a multiple of 60: 60, 120, 300, 600, 3600, etc.

For high-resolution metrics, you can use sub-minute periods supported by the API (1, 5, 10, 20, 30 seconds) as well as multiples of 60. Choose a period matching the storage resolution and the API/console/Alarm in use.

### 7.3. A Statistic's Timestamp Is the Start of the Period

CloudWatch timestamps each statistic with the start time of the period. For example, a statistic aggregated from 10:00 to 10:05 is stamped 10:00.

While a period is still open, the statistic for the current bucket can continue changing as new samples arrive. Do not treat a value in an open bucket as the final result for the full period.

### 7.4. Choosing a Period by Question

| Question | Suggested Period |
|---|---|
| Are multi-second latency spikes affecting users? | 1–10 seconds if high resolution is appropriate |
| Per-minute API error rate? | 60 seconds |
| Traffic trend over 30 minutes? | 300 seconds |
| Hourly operational reporting? | 3600 seconds |
| Long-term historical investigation? | Matching available retention and resolution |

Period is not the producer's sampling interval. A producer can publish many samples per minute; CloudWatch aggregates them according to the queried period.

### 7.5. Period and Alarm Evaluation

A CloudWatch alarm uses period to compute each evaluation data point. EvaluationPeriods specifies how many periods are in the evaluation window; DatapointsToAlarm specifies how many points within that window must breach for the alarm to transition.

For example, Period=60, EvaluationPeriods=5, DatapointsToAlarm=3 means the alarm evaluates the five most recent one-minute periods and requires three breaching points to transition to ALARM per evaluation semantics.

Choose period and evaluation window based on your SLO. Shorter periods detect issues faster but react more readily to noise; longer periods are steadier but increase detection latency.

## 8. Retention, Rollup, and Querying Historical Data

### 8.1. How CloudWatch Retains Metrics by Resolution

CloudWatch retains metric data for the following durations:

| Data Point Resolution | Retention at That Resolution |
|---|---:|
| Under 60 seconds (high resolution) | 3 hours |
| 60 seconds (1 minute) | 15 days |
| 300 seconds (5 minutes) | 63 days |
| 3600 seconds (1 hour) | 455 days (15 months) |

Older data does not vanish immediately after the first cutoff; CloudWatch rolls it up into coarser resolutions. For example, 1-minute data after 15 days remains queryable at 5-minute resolution; after 63 days, data is aggregated at 1-hour resolution.

### 8.2. Period Must Match Data Age

When querying historical metrics, the minimum allowed period depends on StartTime age:

| Age of StartTime | Required Period |
|---|---|
| Within the last 3 hours | Sub-minute allowed if the metric is high resolution |
| 3 hours to 15 days | Multiple of 60 seconds |
| 15 to 63 days | Multiple of 300 seconds |
| Over 63 days | Multiple of 3600 seconds |

For example, querying p95 over the past 30 days with a 60-second period will not return data at that resolution across the entire span. You must use a 300-second period for the 15–63-day range, or split queries into time ranges with matching periods.

### 8.3. Older Metrics Disappearing from ListMetrics

A metric with no new data points for two weeks may not appear in CloudWatch console Browse or ListMetrics results. That does not mean the metric and its data were deleted.

If you know the namespace, metric name, and dimension set, query directly using GetMetricData or GetMetricStatistics with an appropriate time range.

### 8.4. Period, Cost, and Observability Experience

Small periods produce more data points and can increase display/alarm costs or query data volume. Large periods reduce granularity and can obscure brief spikes. Choose periods based on:

- Desired reaction time;
- Actual metric resolution;
- SLO and alerting windows;
- Data retention;
- Custom metric and alarm costs;
- Post-incident investigative needs.

## 9. Publishing Custom Metrics with AWS CLI

### 9.1. Creating a Metric Data File

Suppose the checkout application publishes request latency for the production environment and CreateOrder operation. Create metric-data.json:

~~~json
[
  {
    "MetricName": "RequestLatency",
    "Dimensions": [
      {
        "Name": "Environment",
        "Value": "production"
      },
      {
        "Name": "Operation",
        "Value": "CreateOrder"
      }
    ],
    "Value": 245.7,
    "Unit": "Milliseconds",
    "StorageResolution": 1
  },
  {
    "MetricName": "OrdersCreated",
    "Dimensions": [
      {
        "Name": "Environment",
        "Value": "production"
      }
    ],
    "Value": 1,
    "Unit": "Count"
  }
]
~~~

The two metrics have different dimension sets and different meanings:

- RequestLatency is a latency sample; high resolution is enabled with StorageResolution=1;
- OrdersCreated is an event counter; it uses standard resolution and Sum when queried.

### 9.2. Sending Data to a Namespace

~~~bash
aws cloudwatch put-metric-data \
  --namespace Acme/Checkout \
  --metric-data file://metric-data.json \
  --region ap-southeast-1
~~~

This command publishes two metrics to the Acme/Checkout namespace in Region ap-southeast-1. If the application runs on AWS, grant an IAM role with the cloudwatch:PutMetricData permission and restrict the namespace with an appropriate IAM policy condition.

Do not place access keys in scripts or source code. Use workload identities/roles and the AWS SDK credential provider chain.

### 9.3. Timestamp Considerations

If Timestamp is omitted, CloudWatch uses the time the data point is received. For publishers sending delayed data or batch replays, consider the original event timestamp and allowed timestamp bounds. Use UTC to avoid confusion when dashboards/alarms evaluate over time.

## 10. Publishing Custom Metrics with AWS SDK for Java 2.x

### 10.1. Sending a Raw Data Point

Java example:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.cloudwatch.CloudWatchClient;
import software.amazon.awssdk.services.cloudwatch.model.Dimension;
import software.amazon.awssdk.services.cloudwatch.model.MetricDatum;
import software.amazon.awssdk.services.cloudwatch.model.PutMetricDataRequest;
import software.amazon.awssdk.services.cloudwatch.model.StandardUnit;

public class CheckoutMetricsPublisher {

    private final CloudWatchClient cloudWatch;

    public CheckoutMetricsPublisher() {
        this.cloudWatch = CloudWatchClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build();
    }

    public void publishRequestLatency(double latencyMillis) {
        Dimension environment = Dimension.builder()
            .name("Environment")
            .value("production")
            .build();

        Dimension operation = Dimension.builder()
            .name("Operation")
            .value("CreateOrder")
            .build();

        MetricDatum datum = MetricDatum.builder()
            .metricName("RequestLatency")
            .dimensions(environment, operation)
            .value(latencyMillis)
            .unit(StandardUnit.MILLISECONDS)
            .storageResolution(1)
            .build();

        PutMetricDataRequest request = PutMetricDataRequest.builder()
            .namespace("Acme/Checkout")
            .metricData(datum)
            .build();

        cloudWatch.putMetricData(request);
    }

    public void close() {
        cloudWatch.close();
    }
}
~~~

This example uses AWS SDK for Java 2.x. In a Spring Boot application, manage CloudWatchClient as a singleton bean and close it when the application context shuts down; do not instantiate a new client per request.

### 10.2. Choosing Stable Dimensions

The dimensions in the example are Environment and Operation. Placing OrderId or RequestId into dimensions could create a new metric identity per request, causing cardinality to surge.

Keep unique IDs in logs/traces, where they are better suited for finding a specific request.

### 10.3. Sending Statistic Sets When Pre-Aggregating

Example publishing aggregated latency data for a batch:

~~~java
import software.amazon.awssdk.services.cloudwatch.model.StatisticSet;

StatisticSet minuteStatistics = StatisticSet.builder()
    .minimum(8.0)
    .maximum(420.0)
    .sum(3100.0)
    .sampleCount(100.0)
    .build();

MetricDatum batchDatum = MetricDatum.builder()
    .metricName("RequestLatency")
    .dimensions(environment, operation)
    .unit(StandardUnit.MILLISECONDS)
    .statisticValues(minuteStatistics)
    .build();

PutMetricDataRequest batchRequest = PutMetricDataRequest.builder()
    .namespace("Acme/Checkout")
    .metricData(batchDatum)
    .build();

cloudWatch.putMetricData(batchRequest);
~~~

With the statistic set above, Average is 31 milliseconds. However, p95/p99 across the 100 samples cannot be reconstructed from min/max/sum/count alone because distribution details were lost.

If dashboards or alarms need tail latency, publish raw samples or use a telemetry pipeline that supports distributions/histograms with appropriate semantics.

## 11. Querying Metrics with GetMetricData and Metric Math

### 11.1. Querying a Metric with Exact Dimensions

Create metric-data-queries.json:

~~~json
[
  {
    "Id": "latency",
    "MetricStat": {
      "Metric": {
        "Namespace": "Acme/Checkout",
        "MetricName": "RequestLatency",
        "Dimensions": [
          {
            "Name": "Environment",
            "Value": "production"
          },
          {
            "Name": "Operation",
            "Value": "CreateOrder"
          }
        ]
      },
      "Period": 60,
      "Stat": "p95"
    },
    "ReturnData": true
  }
]
~~~

Run the query:

~~~bash
aws cloudwatch get-metric-data \
  --metric-data-queries file://metric-data-queries.json \
  --start-time 2026-11-20T03:00:00Z \
  --end-time 2026-11-20T04:00:00Z \
  --region ap-southeast-1
~~~

Times in the example are UTC; adjust start/end to the incident window under investigation. The query must match the published namespace, metric name, and dimension set. Omitting a custom dimension queries a different metric identity that may never have been created.

### 11.2. GetMetricData and GetMetricStatistics

GetMetricData is ideal when fetching multiple metrics, applying metric math, or paginating results. GetMetricStatistics is a simpler API for a single metric identity and single statistic request.

Use GetMetricData for modern dashboards/queries, especially when combining multiple series. Regardless of which API you use, specify a period consistent with resolution and retention.

### 11.3. Metric Math for Computing Rates

Suppose OrdersCreated publishes order counts as a counter per data point. Querying Sum over a 60-second period returns total orders in that minute.

You can use metric math to compute orders per second:

~~~text
m1 = OrdersCreated, Statistic=Sum, Period=60
expression = m1 / PERIOD(m1)
~~~

PERIOD(m1) returns the period in seconds. If m1 is total orders over 60 seconds, the expression returns count/second.

For error rate, you can compute:

~~~text
100 * errors / requests
~~~

In production, guard against zero denominators and missing data, and ensure both metrics share the same period, dimension scope, and timestamp alignment. If requests and errors use different dimension sets, the division may not reflect the same traffic cohort.

### 11.4. Metric Math Does Not Synthesize Missing Base Data

Metric math can combine existing time series, but cannot turn an unpublished dimension set into a base metric. Use SEARCH to match multiple relevant time series or publish a dedicated aggregate metric when a stable view is needed for alarms.

### 11.5. Viewing Metrics in the CloudWatch Console

In the CloudWatch console:

1. Open Metrics / All metrics;
2. Select the namespace;
3. Select the metric name/dimension combination;
4. Choose statistic and period;
5. Add the metric to a graph or create an alarm.

The console groups metrics by namespace and dimension combinations. If a metric is missing, verify account, Region, namespace, dimension values, and data point timestamps before concluding the publisher failed.

## 12. Choosing Statistics and Periods for Dashboards/Alarms

### 12.1. Dashboards Should Show Multiple Perspectives

Example checkout dashboard:

| Widget | Metric | Statistic | Period |
|---|---|---|---:|
| Request volume | Requests | Sum | 60 seconds |
| Order throughput | OrdersCreated | Sum | 60 seconds |
| Latency trend | RequestLatency | Average | 60 seconds |
| Tail latency | RequestLatency | p95, p99 | 60 seconds |
| Peak latency | RequestLatency | Maximum | 60 seconds |
| Error volume | RequestErrors | Sum | 60 seconds |

Name widgets to state the statistic and unit. A graph mixing metrics with different units can be hard to read; split axes or widgets when needed.

### 12.2. Alarms Require Statistic, Period, and Evaluation Window

When creating an alarm, decide:

- Metric identity;
- Statistic or extended statistic;
- Period;
- Threshold and comparison operator;
- EvaluationPeriods;
- DatapointsToAlarm;
- TreatMissingData;
- Alarm action/notification.

For example, an alarm for p95 latency exceeding 800 milliseconds for 3 out of 5 one-minute periods. This requires the metric to publish enough raw latency samples for CloudWatch to compute percentiles.

### 12.3. Missing Data Does Not Mean Zero

A metric can lack data points because there is no traffic, the publisher failed, permissions were denied, or the service did not emit the metric. TreatMissingData supports options such as breaching, notBreaching, ignore, and missing.

Examples:

- A missing heartbeat metric may indicate an outage; missing can be treated as breaching;
- A missing request count during zero traffic may be normal;
- If the publisher stops working, an alarm may need a separate heartbeat/agent health metric.

Do not automatically treat missing data as zero for every metric.

### 12.4. Alarm Periods and High-Resolution Metrics

A high-resolution metric does not force every alarm to use 10 seconds. If the SLO allows minute-level detection, a standard alarm with a period that is a multiple of 60 can still be appropriate. Use 10/30 seconds when lower detection latency is needed and the higher cost is acceptable.

### 12.5. Statistics Must Match Threshold Semantics

Do not configure a CPU utilization alarm with Sum when the threshold is designed for CPU percentage. Do not configure a request count alarm with Average when the goal is total requests. Do not use Average latency as a proxy for a p99 SLO.

Metric name, unit, statistic, period, and threshold should be reviewed together as one coherent configuration.

## 13. Designing a Metric Catalog and Controlling Cardinality/Cost

### 13.1. Metric Catalog

For each custom metric, document:

| Field | Example |
|---|---|
| Namespace | Acme/Checkout |
| Metric name | RequestLatency |
| Description | Checkout request processing duration |
| Unit | Milliseconds |
| Resolution | Standard or high |
| Dimensions | Environment, Operation |
| Owner | Checkout team |
| Publish source | Spring Boot worker |
| Dashboard/alarm | Checkout SLO dashboard |
| Retention/usage | Per CloudWatch metric retention |

A catalog prevents teams from publishing near-duplicate metrics with slightly different names, units, or dimensions.

### 13.2. Cardinality and Cost

Custom metrics are typically billed based on the number of metrics/metric identities published and related features. Dimension combinations can multiply metric identities quickly; high-resolution publishing and high-resolution alarms also affect cost.

To keep costs under control:

- Use low-cardinality, stable dimension values;
- Never use user/request/trace IDs as dimensions;
- Never create metric names or namespaces per deployment;
- Review the metric catalog periodically;
- Disable publishers that are no longer needed;
- Measure how many new metrics a new dimension will generate;
- Use logs/traces for high-granularity data.

### 13.3. Never Publish the Same Metric from Multiple Sources with Different Meanings

CloudWatch merges data points with the same namespace, metric name, and dimensions from multiple sources into a single metric. This is helpful when multiple instances emit the same service metric, but dangerous if two publishers share an identity with different units or semantics.

Establish clear ownership and naming conventions. If two systems measure different quantities, use distinct namespaces, metric names, or dimensions to avoid mixing data.

## 14. Troubleshooting Metrics

### 14.1. Metric Not Found in the Console

Check:

1. Current account and Region;
2. Exact namespace and metric name;
3. Dimension names/values and the published dimension combination;
4. Whether data point timestamps fall within the selected time range;
5. Whether the metric received new data points within the last two weeks;
6. Whether the publisher has the cloudwatch:PutMetricData permission;
7. Whether units were published inconsistently.

Older metrics may not appear in Browse/ListMetrics, yet can still be queried directly with GetMetricData/GetMetricStatistics.

### 14.2. Query Returns Null or No Data Points

Common causes:

- Wrong namespace or metric name;
- Missing or extra dimension;
- Mismatched unit filter;
- Wrong Region;
- StartTime/EndTime does not include data point timestamps;
- Period incompatible with resolution or data age;
- Metric has already rolled up to a coarser resolution;
- Timestamp outside valid publishing bounds.

Try querying without specifying a Unit to see which unit the data uses; then standardize the producer.

### 14.3. Percentiles Do Not Appear

Check:

- Whether the metric supports percentiles;
- Whether the custom metric publishes raw data points;
- Whether a statistic set is being used;
- Whether metric values are negative;
- Whether the statistic set satisfies one of the two special conditions for percentile availability.

If only Min/Max/Sum/SampleCount are published for a batch of samples, CloudWatch cannot reconstruct the original distribution to compute p95/p99.

### 14.4. Sub-Minute Periods Return No Data

Verify the metric was published with StorageResolution=1. Standard resolution only supports periods of 60 seconds and multiples of 60. Also check the age of StartTime; data older than three hours can no longer be queried at sub-minute periods.

### 14.5. Average Differs from Expectations

Verify whether samples share the same metric identity/unit, whether SampleCount is accurate, whether the period aggregates multiple data points, and whether the publisher sends statistic sets with accurate Min/Max/Sum/SampleCount.

If multiple instances publish the same identity, CloudWatch aggregates them into one metric. To view each instance individually, add a stable dimension like InstanceId or use AWS service-published metrics scoped by resource dimensions.

### 14.6. Alarm Stuck in INSUFFICIENT_DATA

Check period/evaluation window, missing data behavior, UTC timestamps, publisher health, and metric identity. A custom metric whose timestamp is far skewed from current time may not align with an alarm evaluating against current UTC time.

## 15. Case Study: CloudWatch Metrics for a Checkout Service

### 15.1. Context

A Spring Boot checkout application runs across multiple ECS tasks in ap-southeast-1. The operations team needs to:

- Measure the number of orders created;
- Track request latency;
- Detect tail latency breaching the SLO;
- Distinguish production from staging;
- Avoid creating millions of metrics per order/request;
- Investigate incidents within the last 15 minutes as well as daily trends.

### 15.2. Metric Design

| Namespace | Metric name | Dimensions | Unit | Resolution |
|---|---|---|---|---|
| Acme/Checkout | OrdersCreated | Environment | Count | Standard |
| Acme/Checkout | RequestLatency | Environment, Operation | Milliseconds | High |
| Acme/Checkout | RequestErrors | Environment, Operation, ErrorClass | Count | Standard |
| Acme/Checkout | PaymentProviderLatency | Environment, Provider | Milliseconds | High |

Do not include OrderId, CustomerId, RequestId, or TraceId in dimensions. Place those IDs in structured logs/traces and correlation context.

### 15.3. Dashboard and Alarms

Dashboard:

- OrdersCreated: Sum/60s;
- RequestErrors: Sum/60s;
- RequestLatency: Average, p95, p99/60s;
- PaymentProviderLatency: p95/60s;
- Queue backlog: AWS/SQS metric with exact queue dimensions.

Alarms:

- p95 RequestLatency exceeds SLO across multiple evaluation periods;
- RequestErrors Sum exceeds threshold;
- Publisher heartbeat is missing;
- Queue age/backlog exceeds processing threshold.

### 15.4. Incident Investigation

When customers report slow checkout:

1. Select the Region and production environment;
2. Inspect RequestLatency p95/p99 at a one-minute period;
3. Compare across Operations;
4. Check PaymentProviderLatency;
5. Cross-reference RequestErrors and OrdersCreated;
6. Use logs/traces to locate specific request IDs/trace IDs;
7. Verify data is not missing due to publisher, dimension, or timestamp issues.

Metrics show which behavioral group is abnormal; logs/traces identify the specific requests causing that anomaly.

## 16. Self-Check Questions

1. What is a namespace used for?
2. Which fields identify a CloudWatch metric?
3. Why are two metrics with the same namespace and metric name but different dimension sets separate metrics?
4. Does CloudWatch automatically aggregate custom metrics across dimension sets?
5. What is the maximum number of dimensions a metric can have?
6. Why shouldn't RequestId or UserId be put in dimensions?
7. What naming convention do AWS service metrics typically use for namespaces?
8. Should a custom namespace start with AWS/?
9. Is Unit a dimension?
10. Does CloudWatch automatically convert milliseconds to seconds?
11. What is the default granularity of standard resolution?
12. What does StorageResolution=1 mean?
13. Which periods are valid for standard-resolution metrics?
14. How do SampleCount and Sum differ?
15. When should Average be used for a gauge?
16. Why can Average latency mask tail latency?
17. What do p95 and p99 indicate?
18. What fields does a statistic set contain?
19. Why is a statistic set usually insufficient to compute p95/p99?
20. What is a period and in what unit is it measured?
21. Why is a statistic's timestamp the start of the period?
22. How long is high-resolution data under 60 seconds retained?
23. Why might an older metric not appear in ListMetrics?
24. What advantages does GetMetricData have over GetMetricStatistics?
25. Is missing data always equivalent to zero?

## 17. Suggested Answers

1. Namespaces partition and isolate metrics by application/service.
2. Account, Region, namespace, metric name, and dimension set.
3. The dimension set is part of the metric identity.
4. No; custom metrics do not automatically aggregate across dimension combinations.
5. 30 dimensions.
6. Cardinality grows rapidly, making management difficult and increasing costs.
7. AWS/<service>, for example AWS/EC2.
8. No; the AWS/ prefix is reserved for AWS service namespaces.
9. No; unit is a data point attribute and different units are aggregated separately.
10. No; CloudWatch does not convert units automatically.
11. One minute.
12. Publishes the custom metric at high resolution, storing data at one-second granularity.
13. Starting at 60 seconds and multiples of 60.
14. SampleCount is the number of samples; Sum is the total of sample values.
15. When measuring gauges such as CPU utilization or queue depth.
16. A small group of very slow requests may not noticeably raise Average.
17. Thresholds below which 95% or 99% of samples fall per percentile definition.
18. Minimum, Maximum, Sum, and SampleCount.
19. A statistic set discards the raw sample distribution.
20. The statistic aggregation interval, measured in seconds.
21. CloudWatch stamps statistics with the start time of the bucket.
22. Three hours.
23. Metrics with no new data points for two weeks can be hidden from Browse/ListMetrics.
24. Supports multiple metrics, metric math, and pagination.
25. No; missing data can result from no traffic or publisher/permission failures.

## 18. CloudWatch Metrics Design Checklist

### Metric Identity and Namespace

- [ ] Namespace has clear ownership and a stable naming convention.
- [ ] Metric name describes the measured quantity.
- [ ] Region/account context is clearly defined.
- [ ] Dimension set fits dashboards, alarms, and queries.
- [ ] High-cardinality dimensions such as request/user/trace IDs are excluded.
- [ ] Publishers sharing a metric identity share identical semantics and units.

### Statistic, Unit, and Period

- [ ] Units are chosen consistently without relying on implicit conversion.
- [ ] Counters use Sum when total event counts are needed.
- [ ] Gauges use Average/Minimum/Maximum suited to the operational question.
- [ ] Latency SLOs include percentiles when tail behavior matters.
- [ ] Statistic sets are used only when raw distributions are not needed for percentiles.
- [ ] Period matches standard/high resolution.
- [ ] Query periods match data age and retention rollups.
- [ ] Timestamps use UTC and clocks are synchronized.

### Publishing, Querying, and Operations

- [ ] Producers have least-privilege cloudwatch:PutMetricData IAM permissions.
- [ ] Custom metric publishers are controlled for cardinality and cost.
- [ ] Queries use exact namespace, metric name, and dimension combinations.
- [ ] Dashboards clearly display statistic, period, and unit.
- [ ] Alarms have intentional evaluation windows and missing-data behavior.
- [ ] Logs/traces exist to investigate specific events/requests.
- [ ] Critical metrics have a metric catalog entry, owner, and runbook.

**Expected outcome:** you can design accurate CloudWatch metric identities, choose controlled dimensions, publish and query custom metrics, select statistics and periods aligned with data semantics, and build dashboards/alarms that do not mislead.

## Official AWS Documentation

- [CloudWatch metrics concepts](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_concepts.html)
- [CloudWatch statistics definitions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Statistics-definitions.html)
- [MetricStat API reference](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_MetricStat.html)
- [PutMetricData API reference](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_PutMetricData.html)
- [GetMetricData API reference](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricData.html)
- [GetMetricStatistics API reference](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricStatistics.html)
- [View available metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/viewing_metrics_with_cloudwatch.html)
- [High-resolution metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/publishingMetrics.html)
- [Metric math](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/using-metric-math.html)
- [CloudWatch alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html)
- [AWS SDK for Java 2.x CloudWatch examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-cloudwatch.html)

> **Application note:** Namespaces, metric names, dimensions, account IDs, Regions, timestamps, and values in this lesson are training examples. Before publishing or creating production alarms, verify metric identity, unit, resolution, retention, IAM permissions, and cost/cardinality. Do not use metrics in place of logs/traces when investigating a specific request.
