# Building a Data Lake from Event Streams to Analytics Dashboards

## 1. Project Overview

### 1.1. Background

An online retail platform wants to monitor order activity in near real time. Every action in the order lifecycle produces an event: a customer places an order, payment is authorized or declined, the order is packed, handed to a carrier, and delivered. Operational systems must ingest events continuously; analytics teams need structured historical data to answer questions about revenue, order volume, payment performance, sales channels, and fulfillment duration.

You will design and deploy a data lake on AWS to ingest events, retain raw originals, normalize data, catalog metadata, enforce access controls, query with SQL, and surface results on dashboards. The project spans from a lightweight producer pushing events into a stream through to an operational and executive dashboard suite.

The project uses these services:

- **Amazon Kinesis Data Streams** to ingest events from producers in real time.
- **Amazon Data Firehose** to read the Kinesis stream and deliver data to Amazon S3 with dynamic partitioning based on event content.
- **Amazon S3** to store the raw, quarantine, and curated zones.
- **AWS Glue Data Catalog and AWS Glue ETL** to manage schemas, partitions, and transform JSON into normalized Parquet.
- **AWS Lake Formation** to govern database, table, and column permissions across the data lake.
- **Amazon Athena** to query S3 data using SQL.
- **AWS Quick Sight** (formerly Amazon QuickSight) connected to Athena to create datasets, analyses, and dashboards.
- **Amazon CloudWatch and AWS CloudTrail** to monitor operations and governance activity.

### 1.2. Business Objectives

The final dashboard must answer these questions:

1. How many orders are created per day, hour, channel, and sales region?
2. How do Gross Merchandise Value (GMV) and Average Order Value (AOV) trend over time?
3. What is the payment authorization rate relative to total payment-attempted orders?
4. Which products generate the highest revenue?
5. What is the average duration from order creation to delivery?
6. How many events fail schema checks or cannot be processed?
7. How fresh is dashboard data compared to when events actually occurred?

### 1.3. Scope

**In scope for the capstone**

- Build a sample retail event stream.
- Provision a Kinesis Data Stream and a producer sending JSON events.
- Provision a Firehose delivery stream with Kinesis as source and S3 as destination.
- Partition S3 data by event date and event type.
- Organize raw, error/quarantine, and curated zones.
- Use a Glue crawler/Data Catalog and Glue ETL to normalize, validate data, and write Parquet.
- Use Lake Formation and IAM for access control.
- Create an Athena workgroup, tables/views, and KPI queries.
- Build an AWS Quick Sight dataset and dashboard.
- Configure monitoring, data quality checks, cost controls, and error-handling procedures.

**Out of scope for the baseline version**

- Integrating live production payment systems, ERPs, CRMs, or storefronts.
- Storing payment card details, passwords, emails, or direct personally identifiable information.
- Standing up a separate data warehouse on Amazon Redshift.
- Guaranteeing end-to-end exactly-once semantics or sub-second latency.
- Implementing a multi-account enterprise data mesh.

You can extend this later to Apache Iceberg, Glue Streaming, Amazon Managed Service for Apache Flink, Redshift, or cross-account Lake Formation after completing the core architecture.

### 1.4. Deliverables

Upon completion, the project must include:

- Architecture diagram and data flow description.
- Data contract and at least four sample event types.
- Operational Kinesis stream and Firehose delivery stream.
- S3 bucket with Block Public Access, encryption, and data zone prefixes.
- Glue database, raw table, curated table, and ETL job.
- Data quality rules and quarantine zone.
- Lake Formation grants for data engineers and analysts.
- Athena workgroup with a dedicated query result location and cost guardrails.
- SQL views/KPIs backing the dashboard.
- AWS Quick Sight dashboard with filters and business charts.
- CloudWatch dashboards/alarms, runbooks, and acceptance checklist.
- Cleanup guide to delete lab resources.

## 2. Overall Architecture

### 2.1. Data Flow Diagram

```mermaid
flowchart LR
  P[Web / App / Order services] -->|PutRecord(s)| K[Kinesis Data Streams]
  K -->|Kinesis source| F[Amazon Data Firehose]
  F -->|Dynamic partitioning| R[(S3 raw zone)]
  F -->|Delivery/format errors| Q[(S3 error zone)]
  R --> C[AWS Glue Crawler]
  C --> CAT[(Glue Data Catalog)]
  R --> ETL[AWS Glue ETL]
  ETL -->|Validated Parquet| U[(S3 curated zone)]
  U --> CC[AWS Glue Crawler]
  CC --> CAT
  CAT --> LF[AWS Lake Formation]
  LF --> A[Amazon Athena]
  A --> D[AWS Quick Sight]
  D --> V[Operations and business users]
  K -. metrics .-> CW[CloudWatch]
  F -. delivery metrics .-> CW
  ETL -. job logs .-> CW
  A -. query history .-> CW
  IAM[IAM / KMS / CloudTrail] -. governance .-> R
  IAM -. governance .-> CAT
  IAM -. governance .-> A
```

### 2.2. Role of Each Layer

| Layer | Component | Responsibility |
|---|---|---|
| Event producer | Web/app/order services | Produce events matching the data contract with event ID and timestamp |
| Ingestion | Kinesis Data Streams | Receive, buffer, and distribute events to consumers |
| Delivery | Amazon Data Firehose | Read stream, buffer, partition, and deliver objects to S3 |
| Raw/landing | S3 raw zone | Preserve records close to raw payloads for auditing, replay, and investigation |
| Error/quarantine | S3 error zone | Store records failing delivery, partition extraction, or transformation |
| Catalog | AWS Glue Data Catalog | Store databases, tables, schemas, and partition metadata |
| Processing | AWS Glue ETL | Cast data types, enforce quality checks, deduplicate within batch, and write Parquet |
| Governance | AWS Lake Formation + IAM | Enforce permissions over catalog objects and S3 data |
| Query | Amazon Athena | Query data via SQL, define views, and aggregate KPIs |
| BI | AWS Quick Sight | Build datasets, analyses, dashboards, and share insights |
| Operations | CloudWatch / CloudTrail | Monitor metrics, logs, alarms, and administrative actions |

### 2.3. Raw, Curated, and Quarantine Zones

Use a single S3 bucket for lab manageability, separating data zones by prefix:

```text
s3://<DATA_LAKE_BUCKET>/
  raw/
    event_date=YYYY-MM-DD/
      event_type=<event-type>/
        <firehose-object>
  quarantine/
    firehose/
    glue/
  curated/
    events/
      event_date=YYYY-MM-DD/
        event_type=<event-type>/
          part-....snappy.parquet
  athena-results/
  scripts/
  manifests/
```

- **Raw zone** stores JSON events delivered by Firehose. Never mutate raw objects so source evidence remains intact.
- **Quarantine zone** stores invalid records, conversion failures, or unpartitionable records. Each record should capture the failure reason and processing timestamp when the pipeline can append metadata.
- **Curated zone** stores normalized data with stable types, proper partitions, and Snappy-compressed Parquet.
- **Athena results** isolates query outputs from input datasets.
- **Scripts/manifests** stores Glue ETL scripts, schema versions, and deployment manifests.

Never store Athena query results inside raw or curated prefixes. Query results may contain filtered or aggregated subsets with different retention and access policies.

### 2.4. Processing Flow and Latency

An event travels through these steps:

1. Producer builds an event and calls `PutRecord`/`PutRecords`.
2. Kinesis temporarily persists the record in the stream keyed by partition key.
3. Firehose reads the Kinesis source and buffers records per size/time hints.
4. Firehose extracts `event_date` and `event_type` to choose the target S3 prefix.
5. JSON objects land in the raw zone; invalid records route to the error prefix.
6. Glue crawler updates table/partition metadata; Glue ETL reads new objects, normalizes data, and writes Parquet.
7. A crawler or metadata update makes the curated table queryable in Athena.
8. Athena executes SQL queries and AWS Quick Sight updates datasets/dashboards based on its connection mode.

This is a **micro-batch near-real-time** architecture, not an instantaneous real-time dashboard. Firehose buffers data; with dynamic partitioning, end-to-end delivery latency can be roughly 1.5x the configured buffering hint. Glue ETL, crawlers, and dashboard refresh schedules add further latency before data appears. Measure each hop instead of promising numbers without benchmarking.

## 3. Retail Event Data Contract

### 3.1. Event Envelope Design

Every event must share a common envelope so crawlers and Glue ETL process records consistently:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `event_id` | string | Yes | Unique ID for duplicate detection |
| `event_type` | string | Yes | `order_created`, `payment_authorized`, `payment_declined`, `order_shipped`, `order_delivered` |
| `event_ts` | ISO-8601 UTC string | Yes | Business timestamp when the event occurred |
| `event_date` | `YYYY-MM-DD` | Yes | UTC date used for dynamic partitioning |
| `schema_version` | string | Yes | Data contract version |
| `order_id` | string | Yes | Pseudonymized order identifier |
| `customer_ref` | string | Yes | Customer reference token containing no PII |
| `channel` | string | Yes | `web`, `mobile`, `marketplace`, `store` |
| `sales_region` | string | Yes | Business sales region, e.g. `VN-SOUTH` |
| `product_id` | string | Event-dependent | SKU or product identifier |
| `quantity` | integer | Event-dependent | Item quantity |
| `unit_price` | decimal | Event-dependent | Unit price in currency |
| `amount` | decimal | Event-dependent | Monetary value associated with the event |
| `currency` | string | Event-dependent | ISO 4217 code, e.g. `VND` |

Never include names, phone numbers, email addresses, shipping addresses, payment tokens, or card data in demo events. When correlation to customer systems is required, use surrogate IDs or tokens issued by the source system under separate access controls.

### 3.2. Sample Event: Order Created

```json
{
  "event_id": "evt-20261120-000001",
  "event_type": "order_created",
  "event_ts": "2026-11-20T07:30:00Z",
  "event_date": "2026-11-20",
  "schema_version": "1.0",
  "order_id": "ord-100045",
  "customer_ref": "cust-token-0081",
  "channel": "web",
  "sales_region": "VN-SOUTH",
  "product_id": "SKU-CHAIR-01",
  "quantity": 2,
  "unit_price": 1250000,
  "amount": 2500000,
  "currency": "VND"
}
```

In the lab model, each `order_created` event represents one aggregated order where `amount` is the order total. The example includes one `product_id` to demonstrate top-product reporting. For multi-line orders in production, emit separate `order_line_created` events or embed a well-defined `items` array; in that case, top products must aggregate by line amount while AOV aggregates by total `amount` per `order_id`.

### 3.3. Sample Event: Payment

```json
{
  "event_id": "evt-20261120-000002",
  "event_type": "payment_authorized",
  "event_ts": "2026-11-20T07:31:15Z",
  "event_date": "2026-11-20",
  "schema_version": "1.0",
  "order_id": "ord-100045",
  "customer_ref": "cust-token-0081",
  "channel": "web",
  "sales_region": "VN-SOUTH",
  "amount": 2500000,
  "currency": "VND"
}
```

Declined payments share the same envelope with `event_type` set to `payment_declined`; never put sensitive banking data or detailed decline reasons into payloads exposed to analysts.

### 3.4. Sample Event: Shipment

```json
{
  "event_id": "evt-20261120-000003",
  "event_type": "order_shipped",
  "event_ts": "2026-11-20T10:45:00Z",
  "event_date": "2026-11-20",
  "schema_version": "1.0",
  "order_id": "ord-100045",
  "customer_ref": "cust-token-0081",
  "channel": "web",
  "sales_region": "VN-SOUTH",
  "amount": 2500000,
  "currency": "VND"
}
```

### 3.5. Data Quality Rules

- `event_id`, `event_type`, `event_ts`, `event_date`, `schema_version`, and `order_id` must be non-null.
- `event_type` must belong to the published enum list.
- `event_ts` must parse cleanly with a timezone; the pipeline normalizes to UTC.
- `event_date` must match the UTC date derived from `event_ts`.
- `quantity` must be greater than 0 for product events.
- `amount` must be non-negative; currency must be valid.
- `order_created` must have `channel`, `sales_region`, `amount`, `product_id`, and `quantity > 0` in the single-product-per-order lab model.
- Payment/shipment events must reference an existing `order_id` or arrive within the allowed late-arrival window.
- `event_id` must be unique at the logical event level; producer retries must preserve the original `event_id`.
- Schema changes must increment `schema_version` and undergo review before rollout.

Records failing validation must route to quarantine with `error_code`, `error_message`, `source_object`, and validation timestamp. Never drop invalid records silently, as doing so skews KPIs.

## 4. Preparing the AWS Environment

### 4.1. Prerequisites

- An AWS account with permissions to create Kinesis Data Streams, Data Firehose, S3, IAM roles, Glue, Lake Formation, Athena, and AWS Quick Sight.
- AWS CLI v2 and Python 3.10+ on the machine running the producer.
- `boto3` installed in a virtual environment.
- A Region supporting all required services; the lab uses `ap-southeast-1` as an example.
- Permissions to create IAM roles/policies or least-privilege roles provisioned by an administrator.
- Dedicated S3 bucket for the data lake and dedicated Athena workgroup for the project.

Never use root access keys. Use IAM Identity Center or an assigned IAM role. Never commit credentials, bucket policies containing secrets, or real customer data to source control.

### 4.2. Initialize Environment Variables

Example commands use Bash, WSL, or AWS CloudShell. Substitute another Region if required by your organization:

```bash
export AWS_REGION="ap-southeast-1"
export PROJECT="retail-event-lake"
export STREAM_NAME="retail-order-events"
export FIREHOSE_NAME="retail-events-to-s3"
export GLUE_DATABASE="retail_lake"
export ATHENA_WORKGROUP="retail-analytics"
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export DATA_LAKE_BUCKET="retail-event-lake-$ACCOUNT_ID-$AWS_REGION"
```

Verify caller identity and Region before creating resources:

```bash
aws sts get-caller-identity
aws configure get region
printf 'Account=%s Region=%s Bucket=%s' "$ACCOUNT_ID" "$AWS_REGION" "$DATA_LAKE_BUCKET"
```

If your CLI profile has no default Region, pass `--region "$AWS_REGION"` to each command. Bucket names must be globally unique; including account ID and Region reduces collision risk, though you should still verify availability first.

### 4.3. Create the S3 Bucket

Create the bucket in the chosen Region:

```bash
aws s3api create-bucket --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION" --create-bucket-configuration LocationConstraint="$AWS_REGION"
```

Enable Block Public Access at the bucket level:

```bash
aws s3api put-public-access-block --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION" --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

Enable versioning to protect against accidental overwrites or deletions:

```bash
aws s3api put-bucket-versioning --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION" --versioning-configuration Status=Enabled
```

S3 automatically encrypts new objects with SSE-S3 by default. For workloads requiring key control, auditing, or separated decrypt permissions, configure SSE-KMS with a customer-managed key; in that case, grant appropriate KMS permissions to Firehose, Glue, Athena, and Quick Sight roles reading the data. Never enable SSE-KMS without configuring the key policy.

Explicitly configure default SSE-S3 encryption for the lab:

```bash
aws s3api put-bucket-encryption --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION" --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Verify the bucket configuration:

```bash
aws s3api get-public-access-block --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION"
aws s3api get-bucket-versioning --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION"
aws s3api get-bucket-encryption --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION"
```

You do not need to pre-create every prefix in the console; S3 creates prefixes when the first object is written. You may create placeholder folders for visibility if desired, though placeholders are not separate resources.

## 5. Creating the Kinesis Data Stream and Producer

### 5.1. Create the Kinesis Stream

For labs with low, variable traffic, use On-demand capacity mode to avoid estimating initial shard counts:

```bash
aws kinesis create-stream --region "$AWS_REGION" --stream-name "$STREAM_NAME" --stream-mode-details StreamMode=ON_DEMAND
aws kinesis wait stream-exists --region "$AWS_REGION" --stream-name "$STREAM_NAME"
aws kinesis describe-stream-summary --region "$AWS_REGION" --stream-name "$STREAM_NAME"
```

Kinesis Data Streams buffers records temporarily for consumers to read. Default retention is 24 hours and can be extended up to 365 days at additional cost. Choose retention based on maximum consumer recovery time; do not treat the stream as long-term historical storage. The S3 raw zone is the historical archive.

If you need 72-hour retention for labs or recovery testing:

```bash
aws kinesis increase-stream-retention-period --region "$AWS_REGION" --stream-name "$STREAM_NAME" --retention-period-hours 72
```

In On-demand mode, Kinesis scales capacity automatically with traffic within service limits. For steady, predictable throughput, Provisioned mode can be more cost-effective if shards are sized accurately. Both modes require monitoring throttling and quotas.

### 5.2. Partition Keys and Event Ordering

Producers send each record with a partition key. Kinesis uses the partition key to select a shard; records sharing the same partition key land in the same shard. Sequence numbers are assigned per shard, with no global ordering across shards. The `PutRecords` API does not guarantee record order within a single batch. If strict ordering is required per client/partition key, send sequentially via `PutRecord` passing `SequenceNumberForOrdering` from the previous successful record. In this project, use `order_id` as the partition key so events for the same order stay on the same shard.

Never use a single constant partition key for all events, as that creates a hot shard. Avoid using customer ID if a single customer can generate disproportionate traffic. As traffic scales, measure partition key distribution and write throttling to evaluate whether key design or capacity needs adjustment.

### 5.3. Set Up the Python Environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip boto3
```

On Windows PowerShell, activate with `.venv/Scripts/Activate.ps1`. Configure AWS credentials via the profile or IAM role permitted in your execution environment.

### 5.4. Sample Producer in Boto3

Save the following to `producer.py`. This example emits four events for a single order to demonstrate the order lifecycle:

```python
import json
import os
import time
import uuid
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "ap-southeast-1")
STREAM_NAME = os.getenv("STREAM_NAME", "retail-order-events")
kinesis = boto3.client("kinesis", region_name=REGION)


def make_event(event_type, order_id, amount, extra=None, occurred_at=None):
    event_time = occurred_at or datetime.now(timezone.utc)
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_ts": event_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "event_date": event_time.date().isoformat(),
        "schema_version": "1.0",
        "order_id": order_id,
        "customer_ref": "cust-token-0081",
        "channel": "web",
        "sales_region": "VN-SOUTH",
        "amount": amount,
        "currency": "VND"
    }
    if extra:
        event.update(extra)
    return event


def put_event(event, sequence_number_for_ordering=None, max_attempts=5):
    payload = json.dumps(
        event,
        separators=(",", ":"),
        ensure_ascii=False
    ).encode("utf-8")

    for attempt in range(max_attempts):
        try:
            request = {
                "StreamName": STREAM_NAME,
                "Data": payload,
                "PartitionKey": event["order_id"]
            }
            if sequence_number_for_ordering:
                request["SequenceNumberForOrdering"] = sequence_number_for_ordering
            response = kinesis.put_record(**request)
            return response["SequenceNumber"]
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            retryable = {
                "ProvisionedThroughputExceededException",
                "InternalFailure",
                "KMSThrottlingException"
            }
            if code not in retryable or attempt == max_attempts - 1:
                raise
            time.sleep(min(2 ** attempt, 10))


def put_events(events):
    last_sequence_by_partition = {}
    for event in events:
        partition_key = event["order_id"]
        last_sequence_by_partition[partition_key] = put_event(
            event,
            sequence_number_for_ordering=last_sequence_by_partition.get(partition_key)
        )


if __name__ == "__main__":
    order_id = "ord-100045"
    created_at = datetime.now(timezone.utc)
    events = [
        make_event(
            "order_created",
            order_id,
            2500000,
            {
                "product_id": "SKU-CHAIR-01",
                "quantity": 2,
                "unit_price": 1250000
            },
            occurred_at=created_at
        ),
        make_event(
            "payment_authorized",
            order_id,
            2500000,
            occurred_at=created_at + timedelta(minutes=2)
        ),
        make_event(
            "order_shipped",
            order_id,
            2500000,
            occurred_at=created_at + timedelta(hours=3)
        ),
        make_event(
            "order_delivered",
            order_id,
            2500000,
            occurred_at=created_at + timedelta(days=1)
        )
    ]
    put_events(events)
    print(f"Published {len(events)} events for {order_id}")
```


The producer generates `event_id` once before sending. When retrying a failed record, preserve the same `event_id`; never generate a new event ID for the same business action. The minimal example above retries the already-serialized payload. In production, add schema validation, structured logging, failed-record metrics, and bounded retry/dead-letter strategies.

### 5.5. Send Test Events

```bash
export AWS_REGION="ap-southeast-1"
export STREAM_NAME="retail-order-events"
python producer.py
```

Check Kinesis metrics such as `IncomingRecords`, `IncomingBytes`, `WriteProvisionedThroughputExceeded` (in Provisioned mode), or corresponding throttling metrics. Before any producer sends data, the stream can be `ACTIVE` while the S3 raw zone remains empty.

## 6. Configuring Amazon Data Firehose to Deliver to S3

### 6.1. Create the Firehose Service Role

Firehose needs a role to read the Kinesis stream and write objects to the bucket. Trust policy allowing Firehose to assume the role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "firehose.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Scope permissions to the exact Kinesis stream and project bucket. Abbreviated example policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadKinesisSource",
      "Effect": "Allow",
      "Action": [
        "kinesis:DescribeStream",
        "kinesis:DescribeStreamSummary",
        "kinesis:GetRecords",
        "kinesis:GetShardIterator",
        "kinesis:ListShards"
      ],
      "Resource": "arn:aws:kinesis:ap-southeast-1:111122223333:stream/retail-order-events"
    },
    {
      "Sid": "ListLakeBucket",
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketLocation",
        "s3:ListBucket",
        "s3:ListBucketMultipartUploads"
      ],
      "Resource": "arn:aws:s3:::retail-event-lake-111122223333-ap-southeast-1"
    },
    {
      "Sid": "WriteLakeObjects",
      "Effect": "Allow",
      "Action": [
        "s3:AbortMultipartUpload",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::retail-event-lake-111122223333-ap-southeast-1/*"
    }
  ]
}
```

Replace account ID, Region, stream ARN, and bucket ARN with real values. In production, add appropriate `aws:SourceAccount` and `aws:SourceArn` conditions to the trust policy where supported to mitigate confused-deputy risks. If Firehose uses a customer-managed KMS key, grant required minimal KMS permissions and update the key policy so this role can encrypt objects. Never use wildcards across all streams or buckets in production. Firehose may also need CloudWatch Logs permissions if error logging is enabled; grant only the log actions used.

### 6.2. Create the Delivery Stream

Create a Firehose delivery stream with Kinesis Data Streams as the source and Amazon S3 as the destination:

1. Open Amazon Data Firehose in the chosen Region.
2. Choose to create a new delivery stream.
3. For Source, select **Amazon Kinesis Data Streams** and choose `retail-order-events`.
4. For Destination, select **Amazon S3** and choose the data lake bucket.
5. Select the service role created above or let the console create a new role.
6. Under processing, enable **Dynamic partitioning** when creating the delivery stream.
7. Add a **Metadata extraction** processor.
8. Select JSON parsing engine `JQ-1.6`.
9. Enter the partition extraction query shown in the next section.
10. Configure the S3 prefix, error prefix, buffer hints, and newline delimiter.
11. Create the stream and wait for `Active` status.

Dynamic partitioning can only be enabled when creating a new delivery stream. If you forget to enable it during creation, you cannot turn it on afterward for that stream; you must create a new stream with dynamic partitioning enabled.

### 6.3. Extract Partition Keys with JQ

Use the JQ expression:

```text
{
  "event_date": .event_date,
  "event_type": .event_type
}
```

Configure the S3 prefix:

```text
raw/event_date=!{partitionKeyFromQuery:event_date}/event_type=!{partitionKeyFromQuery:event_type}/
```

Configure the error output prefix:

```text
quarantine/firehose/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/
```

Use only bounded, controlled fields as partition keys. Never partition by `order_id`, `customer_ref`, `event_id`, or transaction ID, as high cardinality creates excessive prefixes and tiny buffers. For this project, date and event type suffice for Athena pruning by time and business category.

### 6.4. Buffering and Newline Delimiter

Suggested lab settings:

| Parameter | Suggested Value | Rationale |
|---|---:|---|
| Buffer size | 5 MiB | Reduces small objects when traffic is sufficient |
| Buffer interval | 60 seconds | Balances latency and object size |
| New line delimiter | Enabled | Places each JSON record on its own line for Glue/Athena |
| S3 compression | Uncompressed initially | Simplifies raw inspection; Glue writes Snappy Parquet |

These are starting values for benchmarking. At low traffic, the time buffer expires first and produces smaller objects; at high traffic, the size buffer hits first. With dynamic partitioning, Firehose maintains a separate buffer per active partition. End-to-end latency can be around 1.5x the buffering hint time due to multi-stage buffering.

### 6.5. Active Partition Limits

Firehose currently enforces a limit of 500 active partitions per delivery stream inside the delivery buffer per current documentation; quota increases may be requested up to supported limits. If exceeded, remaining records route to the S3 error prefix with error type `activePartitionExceeded`.

To avoid this error:

- Partition by `event_date` and `event_type`, not by order or customer.
- Restrict `event_type` values via the data contract.
- Monitor active partition counts and dynamic partitioning errors.
- Avoid per-minute or per-second partitions if per-partition traffic is sparse.
- Size buffer intervals and sizes to match partition count and traffic volume.

### 6.6. Notes on the Kinesis Source

When Kinesis Data Streams is configured as a Firehose source, producers must write to Kinesis via `PutRecord` or `PutRecords`; Firehose's own `PutRecord`/`PutRecordBatch` APIs are disabled for that delivery stream. Firehose begins reading Kinesis from `LATEST` when the source is configured. Therefore, create Firehose and wait until it is `Active` before running the producer for the first test. Records pushed before Firehose was created are not automatically backfilled by the new delivery stream.

A Kinesis stream can have multiple consumers, though all standard consumers share the shard's read throughput limit. When adding Glue Streaming or other consumers, monitor read throughput and `GetRecords` throttling, and evaluate Enhanced Fan-Out when independent consumer throughput is needed.

### 6.7. Verify Firehose

After the producer sends events, verify:

- The Firehose delivery stream is `Active`.
- Objects appear in S3 under `raw/event_date=.../event_type=.../`.
- The error prefix does not grow unexpectedly.
- `DeliveryToS3.Records`, `DeliveryToS3.Bytes`, and `DeliveryToS3.Success` are recorded.
- `DataFreshness` and partition-related metrics stay within thresholds.
- Objects have newline delimiters and each line parses as valid JSON.

List delivered objects with:

```bash
aws s3 ls "s3://$DATA_LAKE_BUCKET/raw/" --recursive
```

If no objects appear, verify the Firehose source ARN, service role, Kinesis stream activity, bucket/KMS policies, prefix extraction, and buffer interval. Low traffic may require waiting out the buffer interval before objects arrive.

## 7. Creating the Glue Data Catalog and Raw Table

### 7.1. Create the Glue Database

Create the metadata database for the data lake:

```bash
aws glue create-database --region "$AWS_REGION" --database-input Name="$GLUE_DATABASE"
```

Glue Data Catalog stores table metadata, schemas, and partitions; the actual data remains in S3. A Catalog database is not a record-storing database engine.

### 7.2. Create a Crawler for the Raw Zone

In the AWS Glue console:

1. Select Crawlers and create `retail-raw-crawler`.
2. Choose S3 as the data source.
3. Set the S3 path to `s3://<DATA_LAKE_BUCKET>/raw/`.
4. Attach an IAM role permitted to list/read the raw prefix and create/update tables in Glue Catalog.
5. Set the target database to `retail_lake`.
6. Configure the crawler to scan only the `raw/` prefix, never the entire bucket.
7. Run the crawler after Firehose has delivered sample objects.

The crawler infers schemas from JSON and discovers Hive-style `key=value` partitions. Inspect the generated table, confirm envelope columns have appropriate types, and confirm partition keys `event_date` and `event_type` appear in metadata.

If event types vary widely in schema, the crawler may create multiple tables or infer unexpected column types. Share a consistent envelope, keep field names stable, and place event-specific payloads inside an extension JSON field if needed. For production schemas, version schemas and manage migrations explicitly instead of relying solely on crawler inference.

### 7.3. Inspect the Raw Table

Once the crawler finishes, open Athena and select the `retail_lake` database. Inspect the table list and partitions. If the crawler generated a different table name than expected, use the actual name in subsequent steps or rename/configure intentionally.

Athena can query JSON directly, though JSON generally scans more bytes than Parquet. The raw table primarily supports inspection, auditing, and reconciliation; dashboards should read the curated table.

## 8. Building the Curated Zone with AWS Glue ETL

### 8.1. Transformation Design

Glue ETL reads the raw table from the Data Catalog and performs:

1. Parse timestamps into timestamp types.
2. Standardize `event_type`, `channel`, and `currency`.
3. Validate required fields and numeric values.
4. Route invalid records to quarantine.
5. Deduplicate `event_id` within the current batch.
6. Derive `event_date` from UTC `event_ts` to ensure accurate partitioning.
7. Write valid records as Snappy-compressed Parquet partitioned by `event_date` and `event_type`.

Columnar Parquet lets Athena read only required columns. Partitioning by date cuts bytes scanned for time-range queries. Partitioning by event type helps when dashboards filter by event category. Never partition by order or customer ID.

### 8.2. Create the Glue ETL Job

In the AWS Glue console:

- Create a Spark job with an IAM role permitted to read raw S3, write curated/quarantine S3, read Glue Catalog, and write CloudWatch Logs.
- Select a Glue version and worker type appropriate for the Region and workload.
- Store the script under the S3 `scripts/` prefix.
- Pass job parameters `--CURATED_PATH`, `--QUARANTINE_PATH`, and `--job-bookmark-option job-bookmark-enable`.
- Enable job bookmarks so Glue tracks previously processed S3 objects on supported sources.
- Configure metrics, logging, and timeouts to match actual data volume.

Update `raw_events` in the script to match the actual table name created by your crawler. Curated and quarantine paths must point to prefixes inside your project bucket.

### 8.3. Sample Glue PySpark Script

Save the script as `retail_events_etl.py`:

```python
import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.dynamicframe import DynamicFrame
from pyspark.context import SparkContext
from pyspark.sql.functions import (
    col, to_timestamp, to_date, date_format, current_timestamp, lit
)

args = getResolvedOptions(
    sys.argv,
    ["JOB_NAME", "CURATED_PATH", "QUARANTINE_PATH"]
)

sc = SparkContext.getOrCreate()
glue_context = GlueContext(sc)
spark = glue_context.spark_session

job = Job(glue_context)
job.init(args["JOB_NAME"], args)

raw_dyf = glue_context.create_dynamic_frame.from_catalog(
    database="retail_lake",
    table_name="raw_events",
    transformation_ctx="raw_events_source"
)

df = raw_dyf.toDF()

df = (
    df.withColumn("event_ts", to_timestamp(col("event_ts")))
      .withColumn("amount", col("amount").cast("decimal(18,2)"))
      .withColumn("unit_price", col("unit_price").cast("decimal(18,2)"))
      .withColumn("quantity", col("quantity").cast("int"))
)

valid_types = [
    "order_created",
    "payment_authorized",
    "payment_declined",
    "order_shipped",
    "order_delivered"
]

invalid_condition = (
    col("event_id").isNull()
    | col("order_id").isNull()
    | col("event_ts").isNull()
    | col("event_type").isNull()
    | col("schema_version").isNull()
    | col("event_date").isNull()
    | col("channel").isNull()
    | col("sales_region").isNull()
    | (col("event_date") != date_format(to_date(col("event_ts")), "yyyy-MM-dd"))
    | (~col("event_type").isin(valid_types))
    | (
        (col("event_type") == "order_created")
        & (
            col("amount").isNull()
            | (col("amount") < 0)
            | col("product_id").isNull()
            | col("quantity").isNull()
            | (col("quantity") <= 0)
            | col("currency").isNull()
        )
    )
)

invalid = (
    df.filter(invalid_condition)
      .withColumn("error_code", lit("INVALID_EVENT"))
      .withColumn("error_message", lit("Required field or event type is invalid"))
      .withColumn("processed_at", current_timestamp())
)

valid = (
    df.filter(~invalid_condition)
      .dropDuplicates(["event_id"])
      .withColumn("event_date", date_format(to_date(col("event_ts")), "yyyy-MM-dd"))
      .withColumn("processing_ts", current_timestamp())
)

if invalid.limit(1).count() > 0:
    invalid.write.mode("append").json(args["QUARANTINE_PATH"])

curated_dyf = DynamicFrame.fromDF(valid, glue_context, "curated_events")

glue_context.write_dynamic_frame.from_options(
    frame=curated_dyf,
    connection_type="s3",
    connection_options={
        "path": args["CURATED_PATH"],
        "partitionKeys": ["event_date", "event_type"]
    },
    format="glueparquet",
    format_options={"compression": "snappy"},
    transformation_ctx="curated_s3_sink"
)

job.commit()
```

This is a capstone skeleton; before production use, harden error handling, check `schema_version`, handle nullable `amount`/`quantity` per event type, and add audit fields. If the raw table's S3 prefix partition column `event_date` overlaps with the JSON field of the same name, confirm the crawler produces a single logical partition key in the Catalog. Adapt the script to match the actual cataloged schema.

### 8.4. Limitations of Batch Deduplication and Job Bookmarks

`dropDuplicates(["event_id"])` removes duplicates only within the current run's DataFrame. Job bookmarks track processed source objects, but they do not make the pipeline exactly-once and do not automatically clean up output objects if a run writes output and fails before committing the bookmark.

To improve reliability:

- Keep `event_id` stable across producer retries.
- Enable job bookmarks and avoid arbitrarily changing source paths or `transformation_ctx`.
- Log input, valid, invalid, and duplicate record counts.
- Include a run ID or processing timestamp for batch traceability.
- For cross-run upserts/deduplication, consider Apache Iceberg with `MERGE` on `event_id` or a dedicated deduplication state table.
- Write backfills to a separate output location before promoting to avoid appending duplicates into the curated table.

### 8.5. Crawler for the Curated Table

After Glue ETL writes Parquet:

1. Create crawler `retail-curated-crawler`.
2. Set the S3 target to `s3://<DATA_LAKE_BUCKET>/curated/events/`.
3. Set database to `retail_lake`.
4. Optionally set table prefix to `curated_`.
5. Run the crawler and verify the table has Parquet format, Snappy compression, and partition keys `event_date` and `event_type`.

If ETL runs frequently, consider updating partition metadata via the Glue API or Athena partition projection to reduce crawler costs. Never crawl the entire bucket, as doing so can mix raw, quarantine, curated, and Athena query results into unintended tables.

### 8.6. Validate Curated Data

After the crawler completes, verify record counts in Athena:

```sql
SELECT
    event_date,
    event_type,
    COUNT(*) AS event_count,
    COUNT(DISTINCT event_id) AS distinct_events
FROM retail_lake.curated_events
GROUP BY event_date, event_type
ORDER BY event_date DESC, event_type;
```

Reconcile valid event totals against producer counts, minus identified invalid and duplicate records. If numbers diverge, inspect Firehose error prefixes, Glue job logs, crawler partitions, and job bookmark state.

## 9. Querying the Data Lake with Amazon Athena

### 9.1. Create the Athena Workgroup

Create a dedicated workgroup to enforce query result location, encryption, CloudWatch metrics, and bytes-scanned limits:

```bash
aws athena create-work-group --region "$AWS_REGION" --name "$ATHENA_WORKGROUP" --description "Retail event lake analytics" --configuration '{"ResultConfiguration":{"OutputLocation":"s3://'"$DATA_LAKE_BUCKET"'/athena-results/","EncryptionConfiguration":{"EncryptionOption":"SSE_S3"}},"EnforceWorkGroupConfiguration":true,"PublishCloudWatchMetricsEnabled":true,"BytesScannedCutoffPerQuery":1073741824}'
```

The 1 GiB cutoff in this example is a lab guardrail; adjust it to match query scale and budget. When workgroup configuration is enforced, queries use the workgroup's output location and encryption settings. Query callers still need Athena permissions plus read/write permissions on the S3 query result prefix.

### 9.2. Verify the Curated Table

In the Athena query editor, select workgroup `retail-analytics` and database `retail_lake`. Run:

```sql
SHOW TABLES IN retail_lake;

DESCRIBE retail_lake.curated_events;

SELECT *
FROM retail_lake.curated_events
WHERE event_date = '2026-11-20'
LIMIT 20;
```

Substitute your actual table name and date. Verify partition pruning by filtering on `event_date`; avoid scanning full history when querying a single day.

### 9.3. Daily Revenue and Order Count View

Create a view for order-created events:

```sql
CREATE OR REPLACE VIEW retail_lake.v_daily_sales AS
WITH ranked_order_events AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY event_id
            ORDER BY processing_ts DESC
        ) AS row_num
    FROM retail_lake.curated_events
    WHERE event_type = 'order_created'
)
SELECT
    event_date,
    channel,
    sales_region,
    currency,
    COUNT(DISTINCT order_id) AS orders_created,
    SUM(amount) AS gross_merchandise_value,
    AVG(amount) AS average_order_value
FROM ranked_order_events
WHERE row_num = 1
GROUP BY event_date, channel, sales_region, currency;
```

Here GMV equals the sum of `amount` on `order_created` events. If the system supports refunds, cancellations, discounts, or tax events, define GMV vs. net revenue explicitly and incorporate adjustment events into the business logic.

### 9.4. Payment Outcomes View

Aggregate events by `order_id` to determine whether orders were authorized or declined:

```sql
CREATE OR REPLACE VIEW retail_lake.v_payment_outcomes AS
WITH order_payment AS (
    SELECT
        order_id,
        MIN(CASE WHEN event_type = 'order_created' THEN event_date END) AS order_date,
        MAX(CASE WHEN event_type = 'payment_authorized' THEN 1 ELSE 0 END) AS is_authorized,
        MAX(CASE WHEN event_type = 'payment_declined' THEN 1 ELSE 0 END) AS is_declined
    FROM retail_lake.curated_events
    GROUP BY order_id
)
SELECT
    order_date,
    COUNT(*) AS orders_created,
    SUM(is_authorized) AS authorized_orders,
    SUM(is_declined) AS declined_orders,
    CAST(SUM(is_authorized) AS DOUBLE) / NULLIF(COUNT(*), 0) AS authorization_rate
FROM order_payment
WHERE order_date IS NOT NULL
GROUP BY order_date;
```

If an order has multiple payment retries, the view above flags whether the order ever had an authorization or decline. To measure attempt-level rates, include a dedicated `payment_attempt` ID and define the denominator as payment attempts.

### 9.5. Delivery Duration View

Measure elapsed time from order creation to successful delivery:

```sql
CREATE OR REPLACE VIEW retail_lake.v_delivery_duration AS
WITH order_lifecycle AS (
    SELECT
        order_id,
        MIN(CASE WHEN event_type = 'order_created' THEN event_ts END) AS created_at,
        MIN(CASE WHEN event_type = 'order_delivered' THEN event_ts END) AS delivered_at
    FROM retail_lake.curated_events
    GROUP BY order_id
),
completed_orders AS (
    SELECT
        order_id,
        date_diff('second', created_at, delivered_at) AS delivery_seconds
    FROM order_lifecycle
    WHERE created_at IS NOT NULL
      AND delivered_at IS NOT NULL
      AND delivered_at >= created_at
)
SELECT
    COUNT(*) AS delivered_orders,
    AVG(delivery_seconds) / 3600.0 AS average_delivery_hours,
    approx_percentile(delivery_seconds, 0.5) / 3600.0 AS median_delivery_hours,
    approx_percentile(delivery_seconds, 0.95) / 3600.0 AS p95_delivery_hours
FROM completed_orders;
```

To slice by day or region, add `order_date` and `sales_region` to the CTE and group by those fields. Undelivered orders are excluded from delivery duration and should be tracked via a separate backlog KPI.

### 9.6. Top Products by Revenue

```sql
WITH ranked_order_events AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY event_id
            ORDER BY processing_ts DESC
        ) AS row_num
    FROM retail_lake.curated_events
    WHERE event_type = 'order_created'
      AND event_date BETWEEN '2026-11-01' AND '2026-11-30'
)
SELECT
    product_id,
    SUM(quantity) AS units_sold,
    SUM(amount) AS gross_sales
FROM ranked_order_events
WHERE row_num = 1
GROUP BY product_id
ORDER BY gross_sales DESC
LIMIT 20;
```

In the demo data contract, each `order_created` carries a single `product_id`. If an order contains multiple line items, aggregate from `order_line` events or explode items before computing top products; never treat the full order amount as revenue for each individual SKU.

### 9.7. Monitoring Data Quality and Latency

Inspect events with missing fields or unexpected types in quarantine. For curated data, monitor the delta between processing timestamp and event timestamp:

```sql
SELECT
    event_date,
    event_type,
    approx_percentile(
        date_diff('second', event_ts, processing_ts),
        0.95
    ) AS p95_processing_lag_seconds
FROM retail_lake.curated_events
WHERE event_date >= date_format(current_date - INTERVAL '7' DAY, '%Y-%m-%d')
GROUP BY event_date, event_type
ORDER BY event_date DESC, event_type;
```

Processing lag here measures elapsed time from event timestamp to Glue processing timestamp, not the entire producer-to-dashboard latency. To measure end-to-end freshness, capture ingestion timestamps recorded by the producer/consumer alongside dashboard refresh timestamps; never infer Firehose delivery duration solely from `event_ts`.

### 9.8. Athena Optimization

- Use Parquet/ORC instead of JSON/CSV for curated analytical workloads.
- Partition on fields frequently used in `WHERE` clauses such as `event_date`; keep partition cardinality reasonable.
- Select only needed columns instead of `SELECT *`.
- Use separate workgroups per team/workload and enforce bytes-scanned cutoffs.
- Place query results in a dedicated prefix with encryption and lifecycle rules.
- Inspect query execution statistics to catch oversized scans.
- At large scale, run file compaction to avoid excessive small files and tiny partitions.

Athena bills by data scanned for standard query engines; Parquet, compression, and partition pruning reduce bytes scanned. Cutoffs halt runaway queries exceeding the configured threshold but do not replace cost monitoring dashboards.

## 10. Access Governance with IAM and Lake Formation

### 10.1. Separate Roles by Responsibility

Never use one admin role for the entire pipeline. Create dedicated roles:

| Principal / Role | Required Permissions |
|---|---|
| Producer role | Write records to the designated Kinesis stream |
| Firehose service role | Read the stream and write to the designated S3 prefix |
| Glue crawler role | List/read raw or curated prefixes; update Glue Catalog |
| Glue ETL role | Read raw, write curated/quarantine, access Catalog and logs |
| Data lake administrator | Register S3 locations, manage Catalog, and grant Lake Formation permissions |
| Analyst role | Run Athena queries and read granted curated tables |
| AWS Quick Sight service role | Access Athena, Glue Catalog, query result bucket, and granted data locations |

Role separation shrinks blast radius. Analysts need no write access to raw or curated prefixes. Producers need no S3 read access. Firehose needs no bucket-deletion or Glue administration permissions.

### 10.2. Lake Formation Metadata and Data Access Governance

AWS Lake Formation uses the Glue Data Catalog as its metadata layer and provides `GRANT`/`REVOKE` controls at the database, table, and column levels. A data-read request must satisfy both IAM and Lake Formation checks:

- IAM permits calling the required Athena, Glue, and Lake Formation APIs.
- Lake Formation grants the principal access to the corresponding database, table, columns, and data location.
- S3/KMS policies permit the service/principal to access objects and decrypt data.

Setup workflow:

1. Designate a data governance role as the Lake Formation data lake administrator.
2. Register S3 locations for raw and curated prefixes using the role Lake Formation assumes.
3. Verify the location-registration role has access to the S3 bucket and KMS key if SSE-KMS is enabled.
4. Grant `DATA_LOCATION_ACCESS` to the Glue ETL role for the S3 locations the job reads/writes; grant the same to crawler roles if crawlers access registered locations.
5. Grant `DESCRIBE` on the database and `SELECT`/`DESCRIBE` on curated tables to the analyst role.
6. Grant corresponding permissions to the AWS Quick Sight service role or configured trusted identity principal.
7. Grant IAM permission `lakeformation:GetDataAccess` to principals running Athena queries.
8. Test with both the analyst role and the Quick Sight dataset connection.

Do not grant `SELECT` on raw/quarantine tables to all analysts if they only need cleaned data. For sensitive fields, use column-level filtering, data filters, or LF-tags to scope access by group.

### 10.3. IAM for Athena and S3 Query Results

Athena analysts typically need:

- Athena query execution actions on the authorized workgroup.
- Read access to required Glue Data Catalog metadata.
- `lakeformation:GetDataAccess` when tables are governed by Lake Formation.
- Read access to data locations authorized by Lake Formation/IAM.
- Read and write access on the workgroup's S3 query result prefix.
- Appropriate KMS encrypt/decrypt permissions if source data, catalog metadata, or query results use SSE-KMS.

The S3 query result bucket must have Block Public Access, encryption, lifecycle rules, and isolated access controls. SQL outputs can contain sensitive data; never treat query results as harmless temporary files.

### 10.4. Data Controls and Auditing

- Never store PII or payment secrets in the event stream.
- Use customer tokens/references instead of direct customer identities.
- Enable S3 Block Public Access at account and bucket levels.
- Enable encryption at rest; use SSE-KMS when customer-managed keys and key-usage audits are needed.
- Enforce TLS for producers and service APIs.
- Log CloudTrail management events and S3 data events for critical prefixes per audit policy.
- Use bucket versioning and lifecycle rules for retention; consider Object Lock when evidence immutability is required.
- Scope `s3:ListBucket`, `s3:GetObject`, and `s3:PutObject` permissions by prefix.
- Never share dashboards/datasets more broadly than the underlying permissions granted in Lake Formation.

## 11. Building Dashboards with AWS Quick Sight

### 11.1. Connecting to Athena

At the time of writing, the BI capability previously named Amazon QuickSight is branded AWS Quick Sight within the AWS Quick platform. Existing QuickSight dashboards, datasets, analyses, and integrations continue working, and existing APIs/SDKs remain supported.

Steps:

1. Open AWS Quick in a supported Region.
2. Have an administrator open service access management and authorize Amazon Athena connections.
3. Grant access to Athena's S3 query result bucket.
4. If the data lake uses SSE-KMS, grant decrypt permissions to the Quick Sight service role in the KMS key policy.
5. Create a new data source and choose Amazon Athena.
6. Select workgroup `retail-analytics` and Glue database `retail_lake`.
7. Select views `v_daily_sales`, `v_payment_outcomes`, `v_delivery_duration`, and any required curated tables.
8. Validate the connection and create datasets.

When Lake Formation is enabled, the Quick Sight principal must be granted `SELECT`/`DESCRIBE` on the corresponding tables and database. Enabling Athena in Quick Sight account settings alone is insufficient if IAM, Lake Formation, S3, or KMS permissions are missing.

### 11.2. Choosing Direct Query vs. SPICE

| Mode | How It Works | When It Fits |
|---|---|---|
| Direct Query | Queries Athena whenever a dataset/analysis/dashboard is opened or refreshed | Data needs higher freshness and query concurrency fits Athena limits |
| SPICE | Imports a data snapshot into the in-memory engine | Dashboards need fast interactivity and scheduled or API-driven refreshes suffice |

Direct Query does not mean a dashboard continuously auto-refreshes in real time; queries run on open/refresh actions subject to product caching behavior. SPICE holds a snapshot that must be refreshed on schedule or via ingestion API after ETL completes. Choose based on freshness SLOs, dataset size, Athena scan cost, and user experience.

For the lab dashboard to reflect the latest data immediately after Glue ETL runs, start with Direct Query. If using SPICE, trigger a refresh after successful ETL runs and monitor ingestion status.

### 11.3. Designing the Operations Dashboard

Create a dashboard named **Retail Event Lake — Operations & Sales** containing these sections:

| Visual | Dataset / View | Purpose |
|---|---|---|
| KPI: Orders created | `v_daily_sales` | Total orders created |
| KPI: GMV | `v_daily_sales` | Gross merchandise value |
| KPI: Average order value | `v_daily_sales` | Average value per order |
| Line chart: GMV by day | `v_daily_sales` | Revenue trend over time |
| Bar chart: Sales by channel | `v_daily_sales` | Compare web/mobile/marketplace/store |
| Bar chart: Top products | Top products query | Rank products by revenue |
| KPI/stacked bar: Payment outcomes | `v_payment_outcomes` | Authorized vs. declined orders |
| KPI: Median/P95 delivery time | `v_delivery_duration` | Fulfillment performance |
| Table: Data freshness | Quality/lag query | Processing timestamp and data lag |

Add shared filters:

- Date range (`event_date`).
- Sales region.
- Channel.
- Currency.
- Event type when drilling into detailed views.

Document KPI definitions in visual descriptions or dashboard notes. For example, GMV is the sum of `amount` on `order_created` events prior to refunds; payment authorization rate is orders with at least one `payment_authorized` divided by orders created in the same cohort; delivery duration includes only orders with both created and delivered timestamps.

### 11.4. Sharing the Dashboard

Share the dashboard with operations and management teams via organization-managed groups and users. Viewers need dashboard access permissions and dataset permissions per AWS Quick Sight's permission model. If row-level security is enabled, test with each persona to verify users see only their authorized sales regions or business units.

Never share raw datasets for dashboard convenience. Dashboards should read only curated views or tables with vetted schemas and permissions.

## 12. Orchestration, Monitoring, and Operations

### 12.1. Orchestrating Crawlers and ETL

In the baseline capstone, use an AWS Glue Workflow to orchestrate:

1. A scheduled trigger runs the raw crawler periodically.
2. When the raw crawler succeeds, a conditional trigger starts the Glue ETL job.
3. When the ETL job succeeds, a conditional trigger runs the curated crawler.
4. When the curated crawler succeeds, the batch is ready for Athena/Quick Sight.
5. If a job or crawler fails, send a notification and preserve run state for investigation.

A 5–15 minute cadence is a starting point for experimentation, not a default SLA. Actual cadence depends on Firehose delivery speed, object counts, crawler duration, and Glue startup overhead. At larger scale, avoid running crawlers constantly; manage partitions via the Glue API or partition projection instead.

For more complex orchestration, use Step Functions to handle retries, timeouts, backfills, quality gates, and triggering Quick Sight SPICE refreshes after ETL succeeds.

### 12.2. Monitoring Ingestion and Delivery

| Service | Metrics / Logs to Monitor | Signals to Investigate |
|---|---|---|
| Kinesis Data Streams | `IncomingRecords`, `IncomingBytes`, read/write throttling, consumer iterator age | Producer error spike, consumer lag, or hot shard |
| Data Firehose | Records/bytes delivered, delivery success/failure, data freshness, active partition errors | Missing objects, growing error prefix, or delivery lag |
| S3 | Object count/size per prefix, 4xx/5xx requests, storage growth | Raw growing without curated growth, too many small files |
| Glue Crawler | Crawler state, duration, table/partition changes | Schema drift or missed partitions |
| Glue ETL | Job run state, duration, DPU time, error logs, input/output/invalid counts | Job failures, rising invalid rate, sudden runtime spike |
| Athena | Query failures, bytes scanned, query duration, workgroup cutoffs | Large scans or analysts hitting throttling/quotas |
| AWS Quick Sight | Dataset refresh/ingestion status, dashboard access errors | Stale dashboards or failed refreshes |

Create CloudWatch alarms for Firehose delivery failures, Glue job failures, Kinesis throttling/iterator age, and quarantine error counts. Route alerts to SNS or your organization's approved incident management system.

### 12.3. CloudTrail and Audit Trails

CloudTrail identifies who created, modified, or deleted streams, Firehose delivery streams, bucket policies, Glue jobs, workgroups, and Lake Formation grants. For S3, enable data events selectively on prefixes requiring audit per security policy, since data events add cost. Never log payloads containing PII; log event IDs, request IDs, statuses, and operational metadata sufficient for traceability.

### 12.4. Data Quality Dashboard

Create a secondary dashboard or Quality section tracking:

- Daily ingested event count.
- Events successfully written to raw.
- Firehose delivery error count.
- Events processed by Glue.
- Invalid/quarantined event count.
- Duplicate `event_id` rate.
- Cataloged partition count.
- P95 processing lag.
- Timestamp of last successful Glue job run.
- Timestamp of last dataset/dashboard refresh.

Set thresholds against baselines. For instance, if the invalid event rate exceeds 1% over 15 minutes or Firehose delivery freshness breaches its SLO, fire an alert and pause publishing curated updates until investigated.

### 12.5. Runbook When Data Fails to Appear on the Dashboard

1. Check producer logs and Kinesis `IncomingRecords`.
2. Check Firehose stream state, source ARN, IAM role, and S3 destination.
3. Inspect the raw prefix and error prefix.
4. Check whether dynamic partition keys in payloads are null or malformed.
5. Verify the Glue crawler updated the raw table and partitions.
6. Inspect Glue job state, CloudWatch logs, bookmarks, and valid/invalid counts.
7. Verify Parquet objects exist in the curated prefix.
8. Run an Athena `SELECT` against the new partition to confirm metadata and access.
9. Check Lake Formation grants, IAM policies, S3 query result permissions, and KMS key policy.
10. Check Quick Sight Direct Query/SPICE mode and dataset refresh/ingestion history.

Never blindly rerun a Glue job without knowing how far output was already written. Job bookmarks do not delete partial sink outputs; rerunning an append sink can introduce duplicates. For backfills, write to a separate prefix or version and reconcile before promoting.

## 13. Handling Late Events, Duplicates, and Schema Evolution

### 13.1. Late-Arriving Events

Events may reach S3 minutes or hours late due to network issues, retries, or offline source systems. Derive `event_date` from UTC `event_ts` to partition by business event time; late records land in the partition for their historical date.

Ensure Glue crawlers or partition management detect new partitions for older dates. When using Glue job bookmarks, track newly arrived objects rather than filtering strictly by current date. If an event's timestamp falls outside the accepted lateness window, route it to quarantine or tag it as late so analysts do not confuse backfilled events with newly occurring activity.

### 13.2. Duplicate Events

Kinesis producers may retry on timeouts or missing responses, causing duplicate submissions. Kinesis, Firehose, and Glue pipelines do not automatically guarantee business-level exactly-once processing. Use stable `event_id` values and idempotent processing:

- Producers generate `event_id` before the first send and preserve it across retries.
- The raw zone preserves all received records for auditing.
- Glue deduplicates within each batch.
- For cross-batch deduplication, use Iceberg `MERGE` or a dedicated dedup store keyed by `event_id`.
- Reports must use `COUNT(DISTINCT order_id)` / `event_id` aligned with metric definitions.

### 13.3. Schema Evolution

Every event carries `schema_version`. When adding optional fields, crawlers can detect the expanded schema, though downstream consumers still need testing. When changing field types, renaming fields, or altering semantics, bump `schema_version` and roll out controlled transitions.

Never repurpose an existing field with a different meaning. Never change `amount` from order total to discount amount while keeping the old `schema_version`. For breaking changes, maintain `curated` v1 alongside `curated` v2 during transition; switch dashboards only after reconciliation.

### 13.4. Replay and Backfill

Kinesis Data Streams retains records only for the configured retention period. Beyond retention, replay/backfill from the S3 raw zone. Separate replay jobs from regular incremental jobs, and write to a dedicated output prefix/version to avoid duplicates. Record a manifest capturing input date range, source object list, code version, job run ID, and output location.

## 14. Architecture Choices and Scaling Paths

### 14.1. When to Choose Firehose, Glue Streaming, or Flink

| Technology | Choose When | Trade-Offs |
|---|---|---|
| Data Firehose → S3 | Primary goal is capturing, buffering, partitioning, and delivering data | Introduces buffering; complex transforms belong after data lands in S3 |
| Glue Streaming | Complex streaming ETL via Spark Structured Streaming, joins/enrichment, multi-target writes | Continuously running job; requires managing checkpoints, capacity, and schemas |
| Managed Service for Apache Flink | Stateful streaming, windowing, event-time aggregations, and complex real-time logic | Must design state, checkpoints, parallelism, and Flink operations |

The baseline capstone chooses Firehose because the core objective is capturing and delivering events into the data lake, followed by batch Glue ETL. If business requirements demand joining multiple streams, enriching records prior to storage, or computing rolling event-time windows, evaluate Glue Streaming or Managed Service for Apache Flink.

### 14.2. Extending to Apache Iceberg

Parquet on S3 suits append-oriented data lakes and analytical read workloads. When table-level upserts, deletes, time travel, schema evolution, and ACID transactions are required, consider Apache Iceberg:

- Use Glue Data Catalog as the catalog for Iceberg tables.
- Have ETL write in Iceberg format.
- Use Iceberg-capable Athena engines to query and mutate tables.
- Use `MERGE` on `event_id` to deduplicate across batches.
- Schedule compaction, snapshot retention, and vacuuming per policy.

Iceberg does not solve every data quality issue automatically. You still need stable event IDs, schema contracts, data validation, and Lake Formation governance.

### 14.3. Scaling with Volume

As data grows:

- Separate ingestion, data lake, analytics, and shared-services accounts following landing zone design.
- Use Lake Formation cross-account sharing instead of broad bucket policies.
- Use LF-tags to grant access by domain, classification, and persona.
- Use partition projection or Glue API partition management to reduce crawler overhead.
- Apply S3 lifecycle rules to transition older raw data to appropriate storage classes.
- Compact small files and optimize Parquet row groups.
- Separate Athena workgroups by team, workload, and budget.
- Consider Redshift if high BI concurrency or complex semantic models are required.

## 15. Testing and Acceptance Scenarios

### 15.1. Happy Path Testing

| Step | Action | Expected Result |
|---|---|---|
| Producer | Send `order_created`, `payment_authorized`, `order_shipped`, `order_delivered` | Kinesis `IncomingRecords` increases |
| Firehose | Read stream and write to S3 | Objects appear in raw prefix matching date/event type |
| Glue crawler | Crawl raw zone | Catalog has schema and partitions |
| Glue ETL | Run job | Parquet files appear in curated prefix |
| Curated crawler | Crawl curated zone | Catalog contains `curated_events` table |
| Athena | Query `v_daily_sales` | Returns order counts and GMV matching sample events |
| Athena | Query `v_payment_outcomes` | Orders with `payment_authorized` are counted accurately |
| Athena | Query `v_delivery_duration` | Delivery duration appears for delivered orders |
| AWS Quick Sight | Open dashboard | Visuals and filters display metrics |
| Security | Query as analyst role | Can read only granted database/tables |

### 15.2. Failure Testing

- Send an event missing `event_id`: Glue must route it to quarantine.
- Send an unlisted `event_type`: Glue must flag it invalid.
- Send an `event_date` mismatching `event_ts`: verify Firehose partitioning vs. Glue date normalization; record must trigger an alert or quarantine per rule.
- Send the same `event_id` twice: confirm duplicates are logged and do not inflate KPIs beyond definitions.
- Temporarily revoke S3 permissions from the Glue role in a test environment: Glue job must fail clearly, CloudWatch Logs record `AccessDenied`, and alerts fire.
- Revoke a Lake Formation grant from the analyst: Athena must deny reading the restricted table/column.
- Pause the Glue job: raw keeps receiving events while the dashboard displays the latest curated timestamp and raises a freshness alert.
- Send a record with a backdated `event_date`: verify the older partition is discovered and processed.
- Send multiple invalid `event_type` values or malformed partition keys: monitor the Firehose error prefix and active partition metrics.

Never run destructive tests against production accounts or shared roles. Use a dedicated test environment and restore permissions once complete.

### 15.3. Acceptance Criteria

The project is considered complete when:

- [ ] Producer successfully sends at least four event types.
- [ ] Firehose reads from Kinesis and delivers objects to S3.
- [ ] Raw objects are partitioned by `event_date` and `event_type`.
- [ ] Delivery/partition errors have an investigation path via the error prefix.
- [ ] Glue crawler creates the raw table and partition metadata.
- [ ] Glue ETL writes curated Parquet with a stable schema.
- [ ] Invalid events land in quarantine with error reasons.
- [ ] The curated table is queryable in Athena.
- [ ] Views exist for GMV/orders, payment outcomes, and delivery duration.
- [ ] Athena workgroup enforces result location, encryption, and bytes-scanned guardrails.
- [ ] Lake Formation grants and IAM policies match each persona.
- [ ] AWS Quick Sight dashboard includes KPI, trend, channel, product, payment, and fulfillment visuals.
- [ ] Ingestion lag, processing lag, and dashboard refresh mode are measured.
- [ ] CloudWatch alarms exist for ingestion, delivery, and ETL failures.
- [ ] Runbooks, cost estimates, and cleanup procedures are documented.
- [ ] Zero PII or payment secrets appear in the demo dataset.

## 16. Cost and FinOps

Primary cost components:

| Service | Cost Drivers | Controls |
|---|---|---|
| Kinesis Data Streams | On-demand/provisioned capacity, data retention, enhanced fan-out | Match mode to traffic; monitor throughput and retention |
| Data Firehose | Delivered volume, format conversion/processing, data transformation | Trim unnecessary fields, pick sensible buffers, prevent partition explosion |
| S3 | GB-month storage, PUT/LIST/GET requests, lifecycle/replication | Sensible partitions, Parquet compression, lifecycle and retention |
| AWS Glue | Crawler/ETL DPU hours, continuous jobs if streaming | Lower crawler frequency, optimize workers and job duration |
| Lake Formation | Does not replace S3/Glue/Athena charges; integrated features incur underlying service fees | Keep grants clean; avoid unnecessary scans |
| Athena | Bytes scanned and query executions | Parquet, compression, partition pruning, workgroup cutoffs |
| AWS Quick Sight | User/author/reader plans, SPICE capacity/ingestion per edition | Choose Direct Query or SPICE per freshness/performance needs |
| KMS/CloudWatch/CloudTrail | API requests, log/metric ingestion, and retention | Log only what is needed; set selective retention and alarms |

Do not hard-code prices in documentation, as pricing varies by Region, edition, and time. Use AWS Pricing Calculator with daily event counts, average payload size, retention, ETL run frequency, Athena TB scanned, Quick Sight user counts, and SPICE capacity. Tag all resources with `Project`, `Environment`, `Owner`, and `CostCenter`.

### 16.1. Volume Estimation

Estimate daily raw volume:

```text
Raw bytes/day ≈ events_per_day × average_event_size_bytes
Curated bytes/day ≈ raw bytes/day × parquet_compression_ratio
Athena scan ≈ selected_partitions × selected_columns_bytes
```

For example, 2 million events/day at 1 KiB average payload produces roughly 2 GiB/day raw before overhead. Parquet can reduce storage substantially, though compression ratios depend on data and schema. Measure real objects instead of locking budgets to assumed ratios.

## 17. Cleanup and Resource Protection

After acceptance, delete resources in dependency order:

1. Stop the producer so no new events arrive.
2. Disable Glue Workflows, schedules, and crawler schedules.
3. Delete Quick Sight dashboards, datasets, and data sources if this is a lab-only account.
4. Delete Glue jobs, workflows, triggers, crawlers, and databases after exporting artifacts you wish to keep.
5. Delete the Firehose delivery stream.
6. Delete the Kinesis Data Stream.
7. Revoke Lake Formation grants and deregister S3 data locations if registered.
8. Empty the S3 bucket and delete all object versions and delete markers since versioning was enabled.
9. Delete the Athena workgroup.
10. Delete IAM roles and policies created specifically for the lab.
11. If using a dedicated customer-managed KMS key, verify zero remaining dependencies before scheduling key deletion per organizational policy.

Never delete shared buckets or shared KMS keys. With bucket versioning enabled, standard object deletes only create delete markers; you must remove all versions and delete markers before deleting the bucket. Save dashboard screenshots, SQL scripts, job scripts, schemas, and runbooks before cleanup if submitting the capstone.

## 18. Sample IAM Policy for the Producer

The producer only needs to write events to the designated Kinesis stream. Example identity policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublishRetailEvents",
      "Effect": "Allow",
      "Action": [
        "kinesis:PutRecord",
        "kinesis:PutRecords"
      ],
      "Resource": "arn:aws:kinesis:ap-southeast-1:111122223333:stream/retail-order-events"
    }
  ]
}
```

Replace the ARN with your real stream ARN. Do not grant S3, Glue, Athena, or Lake Formation permissions to the producer. If the producer runs on Lambda, ECS, or EC2, attach the policy to its execution/task/instance role; never embed access keys in code.

## 19. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Producer receives `AccessDenied` | Role lacks `PutRecord`/`PutRecords` or wrong Region/account ARN | Verify caller identity and policy against the exact stream |
| Kinesis `IncomingRecords` rises but S3 stays empty | Firehose not `Active`, wrong source, buffer interval not elapsed, or missing S3 role permissions | Check stream state, source ARN, delivery metrics, buffer, and service role |
| Firehose misses records sent before delivery stream creation | Firehose source starts at `LATEST` | Resend events or replay from raw/archive into the new stream per runbook |
| Objects land in error prefix | JQ extraction failed, `event_date`/`event_type` null, or S3/KMS permission failure | Check error type, inspect payloads, and verify role/key policies |
| `activePartitionExceeded` | Partition key cardinality too high or buffer window too long | Partition only by `event_date`/`event_type`, reduce cardinality, and check quotas |
| Glue crawler creates unexpected tables | Inconsistent schemas or crawler scanning wrong prefix | Narrow S3 target, standardize envelope, and isolate tables/prefixes |
| Glue job cannot find table | Crawler has not run, wrong database/table name, or role lacks Catalog permissions | Inspect Glue Catalog and job role |
| Glue job re-reads old data | Bookmark disabled, changed source path/`transformation_ctx`, or bookmark reset | Check bookmark state and source object last-modified timestamps |
| Duplicates in curated zone | Producer retries, job append after retry, or single-batch dedup only | Reconcile by `event_id`; use Iceberg `MERGE` for cross-batch dedup |
| Athena reports `HIVE_PARTITION_SCHEMA_MISMATCH` | Partition schema differs from table or inconsistent crawler update | Standardize schema, fix partition metadata, and rerun crawler carefully |
| Athena `AccessDenied` | Missing IAM, Lake Formation `SELECT`/`GetDataAccess`, S3 result permissions, or KMS decrypt | Check each authorization layer for the actual principal |
| Athena scans too much data | Query lacks partition filter or table is still JSON | Filter on `event_date`, query curated Parquet, and select specific columns |
| Quick Sight fails to connect to Athena | Athena/S3 access not enabled, wrong workgroup, or missing KMS/Lake Formation grants | Validate data source and inspect Quick Sight service role |
| Dashboard shows no new data | Glue has not written curated data, crawler has not run, or Direct Query/SPICE refresh incomplete | Trace pipeline layer by layer and check refresh history |

## 20. Self-Check Questions

1. Why does a data lake keep a raw zone if a curated zone already exists?
2. How do Kinesis Data Streams and Data Firehose differ in responsibility?
3. From which position does Firehose begin reading a newly configured Kinesis source?
4. Why should Firehose be created before starting the producer in the initial test?
5. Which fields in the event contract are required for dynamic partitioning?
6. Why should you avoid partitioning by `order_id` or `customer_ref`?
7. How does dynamic partitioning affect delivery latency and active buffers?
8. Does Glue Data Catalog store data or metadata?
9. Why convert raw JSON into curated Parquet?
10. What do Glue job bookmarks solve, and what do they not solve?
11. Why doesn't `dropDuplicates` in a single batch guarantee cross-batch deduplication?
12. How do Lake Formation and IAM participate together in authorization?
13. How do Athena workgroups help control query costs and output locations?
14. How does Direct Query differ from SPICE in freshness and refresh behavior?
15. Which metrics help detect Firehose delivery lag?
16. How do you handle late-arriving events and historical date partitions?
17. When should you move from Firehose + batch Glue to Glue Streaming or Flink?
18. Why should PII and payment secrets never appear in event payloads?

### Suggested Answers

1. Raw acts as source evidence for auditing, replays, and reconciliation if transformations contain bugs.
2. Kinesis ingests and temporarily retains stream records for consumers; Firehose reads streams, buffers, and delivers data to destinations.
3. Firehose starts from `LATEST`.
4. Records sent before Firehose starts reading will not be picked up automatically by the new delivery stream.
5. `event_date` and `event_type` in this design; events must carry valid values for JQ extraction to succeed.
6. High cardinality creates too many active partitions and small buffers, risking quota breaches.
7. Firehose buffers per partition; end-to-end latency can approach 1.5x the buffering hint, and active partitions are capped.
8. The Catalog stores metadata, schemas, and partitions; data lives in S3 or other data sources.
9. Columnar Parquet and compression cut bytes scanned and accelerate analytical queries.
10. Bookmarks track processed source objects so only new files are read; they do not provide exactly-once guarantees or manage sink output cleanup.
11. Duplicates can arrive across separate objects or runs; `dropDuplicates` operates only on the DataFrame in the current batch.
12. IAM authorizes API/service calls; Lake Formation governs catalog and data access; S3/KMS must also permit object and key access.
13. Workgroups enforce query result locations, encryption, metrics publishing, and bytes-scanned cutoffs.
14. Direct Query reads the source when dashboards open or refresh; SPICE holds a snapshot requiring scheduled or API ingestion refreshes.
15. Delivery success/failure, `DataFreshness`, delivered records/bytes, active partition errors, and error prefix counts.
16. Derive business-date partitions from UTC `event_ts`, update metadata for historical partitions, and monitor late-arrival windows.
17. When complex streaming ETL, stream joins/enrichment, stateful windows, or lower latency than Firehose buffering is needed.
18. Reduces data exposure risk, shrinks compliance scope, and restricts what analysts can access.

## 21. Capstone Handover Package

Deliver a reproducible, structured project directory:

```text
retail-event-lake/
  architecture/
    data-flow.mmd
    adr-001-streaming-ingestion.md
  producer/
    producer.py
    requirements.txt
    sample-events.jsonl
  firehose/
    trust-policy.json
    firehose-s3-prefixes.md
  glue/
    retail_events_etl.py
    raw-crawler-config.md
    curated-crawler-config.md
  athena/
    create-views.sql
    validation-queries.sql
  governance/
    producer-policy.json
    role-matrix.md
    lake-formation-grants.md
  dashboard/
    dashboard-spec.md
    kpi-definitions.md
  operations/
    cloudwatch-alarms.md
    runbook.md
    cleanup.md
  README.md
```

The README must document the Region, account-specific ARNs to substitute, deployment commands, data contract, crawler/job execution order, sample queries, dashboard refresh mode, cost assumptions, and cleanup steps. Never commit credentials, account secrets, real customer data, or Athena query result files containing sensitive data.

## 22. Official References

- [Amazon Kinesis Data Streams — Developer Guide](https://docs.aws.amazon.com/streams/latest/dev/introduction.html)
- [Kinesis Data Streams key concepts and retention](https://docs.aws.amazon.com/streams/latest/dev/key-concepts.html)
- [Change the Kinesis Data Streams retention period](https://docs.aws.amazon.com/streams/latest/dev/kinesis-extended-retention.html)
- [Kinesis PutRecord API and sequence ordering](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_PutRecord.html)
- [Kinesis PutRecords API and ordering limitations](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_PutRecords.html)
- [Configure Kinesis Data Streams as a Data Firehose source](https://docs.aws.amazon.com/firehose/latest/dev/writing-with-kinesis-streams.html)
- [Amazon Data Firehose dynamic partitioning](https://docs.aws.amazon.com/firehose/latest/dev/dynamic-partitioning.html)
- [Enable dynamic partitioning in Data Firehose](https://docs.aws.amazon.com/firehose/latest/dev/dynamic-partitioning-enable.html)
- [Buffer data for dynamic partitioning](https://docs.aws.amazon.com/firehose/latest/dev/buffering.html)
- [Amazon S3 data protection and encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryption.html)
- [AWS Glue Data Catalog best practices](https://docs.aws.amazon.com/glue/latest/dg/best-practice-catalog.html)
- [AWS Glue streaming ETL](https://docs.aws.amazon.com/glue/latest/dg/streaming-chapter.html)
- [AWS Glue job bookmarks](https://docs.aws.amazon.com/glue/latest/dg/monitor-continuations.html)
- [AWS Glue triggers and workflow dependencies](https://docs.aws.amazon.com/glue/latest/dg/about-triggers.html)
- [AWS Lake Formation permissions overview](https://docs.aws.amazon.com/lake-formation/latest/dg/lf-permissions-overview.html)
- [Using AWS Lake Formation with Amazon Athena](https://docs.aws.amazon.com/lake-formation/latest/dg/athena-lf.html)
- [Manage Lake Formation and Athena user permissions](https://docs.aws.amazon.com/athena/latest/ug/lf-athena-user-permissions.html)
- [Amazon Athena workgroups](https://docs.aws.amazon.com/athena/latest/ug/workgroups-create-update-delete.html)
- [Specify Athena query result location using a workgroup](https://docs.aws.amazon.com/athena/latest/ug/query-results-specify-location-workgroup.html)
- [AWS Quick Sight supported data sources](https://docs.aws.amazon.com/quick/latest/userguide/supported-data-sources.html)
- [Authorize AWS Quick Sight connections to Athena](https://docs.aws.amazon.com/quick/latest/userguide/athena.html)
- [Refresh data in AWS Quick Sight](https://docs.aws.amazon.com/quick/latest/userguide/refreshing-data.html)
- [AWS Quick is now AWS Quick — November 9, 2026](https://aws.amazon.com/about-aws/whats-new/2026/11/amazon-quick-aws-quick/)
