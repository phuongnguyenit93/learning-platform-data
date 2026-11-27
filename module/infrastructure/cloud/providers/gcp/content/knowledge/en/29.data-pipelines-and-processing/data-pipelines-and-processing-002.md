# Apache Beam and the Dataflow Programming Model

## Learning Objectives

After this lesson, learners will be able to:

1. Distinguish the **Apache Beam SDK** (which defines the pipeline) from **Google Cloud Dataflow** (the execution service via the Dataflow Runner) and the **Direct Runner** used during development.
2. Use **Pipeline, PCollection, PTransform, ParDo/DoFn, KV, GroupByKey, Combine**, and I/O connectors.
3. Distinguish **bounded/unbounded data**, **batch/streaming**, **event time/processing time**, **window, watermark, trigger, pane**, and **allowed lateness**.
4. Write a Java pipeline tested locally and then executed with the Dataflow Runner; read job metrics and errors.
5. Design Pub/Sub → transforms → BigQuery/Pub/Sub with **idempotency, error handling, IAM, autoscaling, and cost control**.
6. Explain late-arriving data, duplicate events, hot keys, backlog, failover, and safe pipeline releases.

## 1. Context and Two Layers to Distinguish

A Java application **orders-api** on Cloud Run writes transactions to Cloud SQL and publishes **order.created** events to Pub/Sub. The company needs total revenue every five minutes and historical reprocessing from Cloud Storage to audit a campaign. The team does not want to write two completely separate data processing systems for batch and streaming.

**Apache Beam** solves the **data programming** layer: the read → transform → group/aggregate → write graph. **Cloud Dataflow** is Google Cloud's **managed runner/service**: it provisions and manages workers, distributes work, recovers from failures, and monitors execution. These are not two names for the same library:

| Layer | What the developer / system does | Examples |
|---|---|---|
| **Apache Beam SDK** | Defines the graph and logic in Java/Python/Go | PCollection, ParDo, Window, IO |
| **Runner** | Translates the graph into execution | Local DirectRunner, GCP DataflowRunner |
| **Dataflow service** | Operates worker VMs, autoscaling, shuffle, UI/jobs/metrics | Batch ETL, continuous streaming |
| **Sources/sinks** | Provide/receive data with their own IAM and billing | Pub/Sub, GCS, BigQuery, Cloud SQL |

~~~mermaid
flowchart LR
  S["Pub/Sub / GCS / BigQuery"] --> I["Beam IO.Read"]
  I --> P["PCollection"]
  P --> T["PTransform: ParDo / Window / Combine"]
  T --> O["Beam IO.Write"]
  O --> D["BigQuery / Pub/Sub / GCS"]
  R["Runner: DirectRunner or DataflowRunner"] -. "Executes Beam graph" .-> T
  DF["Dataflow: workers, autoscaling, monitoring"] -. "When using DataflowRunner" .-> R
~~~

In **CLOUD_PROVIDERS_GCP**, Beam/Dataflow connects IAM/VPC, Cloud Run/GKE, Pub/Sub, GCS, and BigQuery with reliability and cost trade-offs. **Dataflow is not Dataform**: Dataform primarily manages SQL transformations inside BigQuery, whereas Beam programs record/event processing across multiple runners.

## 2. The Pipeline, PCollection, and PTransform Model

| Component | Function | Notes |
|---|---|---|
| **Pipeline** | Overall graph of transforms | Defined first, executed when `run` is called |
| **PipelineOptions** | Runner, project, region, staging/temp, streaming, custom options | Never hardcode secrets |
| **PCollection<T>** | Distributed set of elements with timestamps/windows | Not a Java List on the driver |
| **PTransform** | Graph-building transformation; can compose multiple steps | Can accept/return multiple PCollections |
| **ParDo + DoFn** | Processes elements, emits 0..n outputs | May be re-invoked on retries |
| **KV<K,V>** | Key/value pair for per-key aggregation | GroupByKey/Combine.perKey |
| **Coder<T>** | Encodes data across workers/shuffle | Custom types require a consistent coder |
| **Side input/output** | Reference data or error branch | Used for small lookups, dead-letter routing |
| **Window/Trigger/Pane** | Assigns time domains and emits results | Core of stream aggregations |

### 2.1. A Graph Is Not Sequential Java Code on a Laptop

~~~java
PCollection<String> raw = pipeline.apply("Read", source);
PCollection<KV<String, Long>> values = raw.apply("Parse", parser);
PCollection<KV<String, Long>> totals = values.apply("Sum", Sum.longsPerKey());
totals.apply("Write", sink);
pipeline.run();
~~~

**This is intentionally pseudocode**: the variables `pipeline`, `source`, `parser`, and `sink` must be declared in a real program. The runner can **fuse** transforms, process bundles in parallel, and **re-run a DoFn** when a worker fails. Do not rely on execution order between events or assume external side effects happen only once.

### 2.2. Immutability and Distribution

Each transform returns a new PCollection; never iterate over a PCollection with a `for` loop on the driver. A **bounded PCollection** has a finite set (an end-of-day file); an **unbounded PCollection** continuously produces elements (Pub/Sub). Timestamps and windows determine which data can be grouped together.

**Unbounded does not mean storing infinite data in RAM:** there must be a mechanism to bound state and aggregations, typically via windowing.

## 3. Data Transformations: Common Transforms

| Transform | Purpose | Example |
|---|---|---|
| **Create, TextIO, PubsubIO** | Read sources | CSV lines, messages |
| **MapElements** | 1→1 transformation | Normalize region |
| **Filter** | Keep valid records | Only `status=PAID` |
| **FlatMapElements/ParDo** | 1→0..n transformation and validation | Parse one event into multiple outputs |
| **WithKeys/KV** | Attach a key | `region → amount` |
| **GroupByKey** | Group values by key/window | Group by merchant |
| **Combine.perKey, Sum.longsPerKey** | Distributed aggregation | Revenue by region |
| **CoGroupByKey** | Join two PCollections with the same key | Orders + metadata |
| **Window.into** | Partition by event time | 5 minutes/window |
| **TextIO, BigQueryIO, PubsubIO.Write** | Write outputs | GCS, BigQuery, Pub/Sub |

A **Composite PTransform** can encapsulate parse → validate → key so it can be reused across batch/streaming and tested independently. Avoid giant DoFns that mix SQL clients, retry loops, logging, and UI logic.

### 3.1. Hot Keys and Aggregation

If 90% of events share the key **unknown**, `GroupByKey` can concentrate work onto a few workers, creating a **hot key**. Prefer **Combine.perKey** for associative sums/counts, and consider fanout/sharding where appropriate. Never collect all values into a Java `List` inside a DoFn. Adding more workers alone is not guaranteed to fix data skew.

## 4. Bounded/Batch vs. Unbounded/Streaming

| Criterion | Batch | Streaming |
|---|---|---|
| Input | Finite files/snapshots | Continuous Pub/Sub/Kafka |
| Execution | Job finishes upon completion | Job runs until drained/canceled |
| Window | Can be global when data is finite | Usually fixed/sliding/session windows |
| Late handling | Usually processes a complete dataset | Late/out-of-order events, watermarks |
| Monitoring | Completion, duration, failures | Backlog, system latency, data freshness |
| Cost | Resources during job run plus supporting services | Workers/Streaming Engine typically run continuously |

For an unbounded Pub/Sub source, you must set **--streaming=true** when running on `DataflowRunner`; for batch files, you do not. The same element-transformation algorithm can be shared across both models, but I/O and windowing/triggers differ.

**Selection rule:** end-of-day revenue reports are often simpler in batch; near-real-time fraud detection requires streaming; a dashboard updating every 15 minutes should weigh the **freshness SLO** against cost before deciding.

## 5. Event Time, Processing Time, Watermarks, Windows, and Triggers

~~~text
Event A: occurred 10:01 → arrived at pipeline 10:01
Event B: occurred 10:02 → arrived at pipeline 10:06 (late)
Event C: occurred 10:04 → arrived at pipeline 10:04

By event time: A, B, C all belong to [10:00,10:05).
By processing time: B may fall into [10:05,10:10).
~~~

| Concept | Definition |
|---|---|
| **Event time** | When the event actually occurred, per the source timestamp |
| **Processing time** | When the worker processes the record |
| **Watermark** | Estimated progress of event time; **does not guarantee** all older events have arrived |
| **Window** | Time interval used to group elements |
| **Trigger** | Determines when results are emitted |
| **Pane** | Each emission of a window's results |
| **Allowed lateness** | Duration for accepting late events after the watermark/window end |

### 5.1. Choosing Windows by Use Case

| Type | Example | Use case |
|---|---|---|
| **Fixed** | `[10:00–10:05)`, `[10:05–10:10)` | Revenue every 5 minutes |
| **Sliding** | 10-minute window, sliding every minute | Moving totals; one event belongs to multiple windows |
| **Session** | 30-minute inactivity gap | User sessions; windows can merge |

~~~mermaid
flowchart LR
  E1["10:01 A"] --> W["Window 10:00–10:05"]
  E2["10:02 B (arrives late)"] --> W
  E3["10:04 C"] --> W
  W --> T["Trigger: early / on-time / late"]
  T --> P1["Early pane"]
  T --> P2["Updated pane"]
~~~

Because the watermark is an estimate, late events can still arrive. **Allowed lateness** bounds how long state is retained to update a window. No pipeline can guarantee absolute completeness for events arriving arbitrarily late.

### 5.2. Accumulating vs. Discarding

Suppose three panes of a window represent the updates: 100 (early), +50 (on-time), +10 (late).

| Mode | Output of each pane |
|---|---|
| **Accumulating** | `100 → 150 → 160` (each pane contains the cumulative total) |
| **Discarding** | `100 → 50 → 10` (each pane contains only the new delta) |

**Do not `SUM` all accumulating panes to compute a total**: `100+150+160` will double-count. When results are emitted multiple times, the sink should **upsert by `(window_start, key)`** or intentionally handle changelogs/overwrites. **A processing-time trigger** does not turn event time into processing time.

## 6. Stateful Processing, Timers, and Error Flows

- **State API** stores state per **key + window**, managed by the runner; never use a mutable global map inside a Java worker.
- **Timers** schedule logic in **event time or processing time**, such as waiting 5 minutes for a `payment-completed` event.
- **Side inputs** distribute small reference tables to workers; if the lookup is huge or changes frequently, use a different design.
- **Side outputs (`TupleTag`/`PCollectionTuple`)** route malformed records (invalid JSON, missing amount, unknown enum) to a dead-letter branch with an error code instead of retrying forever and stalling the job.

State and timers enable complex business logic, but they increase state storage costs, late-data complexity, and testing effort. Use them only when simple transforms and windowing are insufficient.

## 7. Lab A — Local Java Batch Pipeline with DirectRunner

**Goal:** compute total revenue by region from sample data using **Create → ParDo → Sum.longsPerKey → TextIO**, writing CSV output. The data uses only integers, so **long** is used without `double` rounding issues. Currency values are illustrative amounts.

### 7.1. Maven Setup

You need a Java JDK compatible with the **chosen Beam SDK version**, Maven, and a separate Java project. **Do not run these commands inside the curriculum source repository**; this is a separate lab project for learners.

Core Maven dependencies to place in your **lab project's `pom.xml`**:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.apache.beam</groupId>
      <artifactId>beam-sdks-java-google-cloud-platform-bom</artifactId>
      <version>REPLACE_WITH_SUPPORTED_BEAM_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
<dependencies>
  <dependency>
    <groupId>org.apache.beam</groupId>
    <artifactId>beam-sdks-java-core</artifactId>
  </dependency>
  <dependency>
    <groupId>org.apache.beam</groupId>
    <artifactId>beam-runners-direct-java</artifactId>
  </dependency>
  <dependency>
    <groupId>org.apache.beam</groupId>
    <artifactId>beam-runners-google-cloud-dataflow-java</artifactId>
  </dependency>
  <dependency>
    <groupId>org.apache.beam</groupId>
    <artifactId>beam-sdks-java-io-google-cloud-platform</artifactId>
  </dependency>
</dependencies>
~~~

**Note:** the version placeholder **is not a ready-to-run POM**. You must replace it with **a specific Beam release supported by Dataflow**, configure compiler/exec plugins, and build a fat/uber JAR properly. Use the Beam Google Cloud BOM to prevent version mismatches across the SDK and gRPC/Google Cloud libraries. **Never guess the latest version** and deploy it to production untested.

### 7.2. Complete Java Code: `BeamSalesBatch.java`

~~~java
package com.example.pipeline;

import org.apache.beam.sdk.Pipeline;
import org.apache.beam.sdk.options.Description;
import org.apache.beam.sdk.options.PipelineOptions;
import org.apache.beam.sdk.options.PipelineOptionsFactory;
import org.apache.beam.sdk.options.Validation;
import org.apache.beam.sdk.transforms.Create;
import org.apache.beam.sdk.transforms.DoFn;
import org.apache.beam.sdk.transforms.MapElements;
import org.apache.beam.sdk.transforms.ParDo;
import org.apache.beam.sdk.transforms.Sum;
import org.apache.beam.sdk.io.TextIO;
import org.apache.beam.sdk.values.KV;
import org.apache.beam.sdk.values.TypeDescriptors;

public final class BeamSalesBatch {
    private BeamSalesBatch() {}

    public interface SalesOptions extends PipelineOptions {
        @Description("Output path prefix, e.g. out/revenue or gs://.../revenue")
        @Validation.Required
        String getOutputPrefix();
        void setOutputPrefix(String value);
    }

    public static final class ParseSaleFn extends DoFn<String, KV<String, Long>> {
        @ProcessElement
        public void process(@Element String line,
                            OutputReceiver<KV<String, Long>> out) {
            String[] fields = line.split(",", -1);
            if (fields.length != 2 || fields[0].trim().isEmpty()) {
                throw new IllegalArgumentException("Invalid sale record");
            }
            String region = fields[0].trim();
            long amount = Long.parseLong(fields[1].trim());
            out.output(KV.of(region, amount));
        }
    }

    public static void main(String[] args) {
        SalesOptions options = PipelineOptionsFactory.fromArgs(args)
            .withValidation()
            .as(SalesOptions.class);

        Pipeline pipeline = Pipeline.create(options);
        pipeline
            .apply("SampleSales", Create.of(
                "north,120", "south,300", "north,80", "south,50"))
            .apply("Parse", ParDo.of(new ParseSaleFn()))
            .apply("RevenuePerRegion", Sum.longsPerKey())
            .apply("AsCSV", MapElements.into(TypeDescriptors.strings())
                .via((KV<String, Long> kv) ->
                    kv.getKey() + "," + kv.getValue()))
            .apply("WriteCSV", TextIO.write()
                .to(options.getOutputPrefix()).withSuffix(".csv"));

        pipeline.run().waitUntilFinish();
    }
}
~~~

Sample input:

~~~text
north,120
south,300
north,80
south,50
~~~

**Set-level result (line order is not guaranteed):** **`north,200`** and **`south,350`**. `TextIO` may generate sharded files such as **`revenue-00000-of-00001.csv`**; the program does not guarantee a single output file or fixed line order.

### 7.3. Running Locally with DirectRunner

After configuring **exec-maven-plugin** in the lab project and creating the output directory:

~~~bash
mkdir -p out
mvn -q compile exec:java \
  -Dexec.mainClass=com.example.pipeline.BeamSalesBatch \
  "-Dexec.args=--runner=DirectRunner --outputPrefix=out/revenue"

# Inspect shard contents after the job finishes.
cat out/revenue-*.csv
~~~

**DirectRunner** is great for testing logic, but it does not fully simulate autoscaling, latency, IAM, Dataflow regional networking, or failure behavior. **Create.of** is only for lab samples; production batch jobs typically use `TextIO`/`AvroIO`/`BigQueryIO` or Storage/warehouse connectors.

### 7.4. Unit Testing with `TestPipeline`/`PAssert`

JUnit test excerpt using **beam-sdks-java-core**, **beam-runners-direct-java**, and matching Beam test dependencies:

~~~java
@Test
public void totalsAreCorrect() {
    TestPipeline p = TestPipeline.create();
    PCollection<KV<String, Long>> results = p
        .apply(Create.of("north,120", "south,300", "north,80"))
        .apply(ParDo.of(new BeamSalesBatch.ParseSaleFn()))
        .apply(Sum.longsPerKey());
    PAssert.that(results).containsInAnyOrder(
        KV.of("north", 200L), KV.of("south", 300L));
    p.run().waitUntilFinish();
}
~~~

This **test fragment** requires JUnit, `TestPipeline`, `PAssert`, `Create`, `ParDo`, `Sum`, `PCollection`, and `KV` imports in the test project along with an appropriate runner; it demonstrates **order-independent output assertions**. Also test malformed inputs, empty sources, and overflow; in production, a single bad input should not cause workers to retry indefinitely.

## 8. Running the Same Pipeline with DataflowRunner

**The Beam code stays the same**, while the runner is specified via options. Dataflow converts the graph into a **Dataflow job**, provisions worker VMs/containers, and manages shuffling, autoscaling, logging, and cleanup upon batch completion.

### 8.1. GCP Preflight

Assume project **shop-dev-001**, region **asia-southeast1**, and dedicated bucket **gs://shop-dev-001-dataflow-lab** already exist and are approved. Verify:

1. **Dataflow, Compute Engine, Cloud Storage, Cloud Logging**, and any connector-specific APIs are enabled.
2. The region/location of the **Dataflow job, worker network, staging/temp buckets, and sources/sinks** satisfies residency requirements; staging/temp buckets have read/write permissions.
3. **Submitter/CI** has permission to create/run jobs (Dataflow Developer/Admin per workflow) and **iam.serviceAccounts.actAs** on the worker SA.
4. The organization-managed **Worker service account** has **roles/dataflow.worker**, write access to staging/temp, and least-privilege access to sources/sinks.
5. The Google-managed **Dataflow service agent** retains the roles needed to operate worker VMs; **do not strip service-agent roles** while arbitrarily tightening runtime permissions.

| Identity | Responsibility | Related permissions |
|---|---|---|
| **Submitter/CI** | Submit jobs, manage lifecycle | Dataflow Developer/Admin, Service Account User, staging access |
| **Dataflow service agent** | Dataflow manages workers, quotas, resources | Project service agent, Google-managed |
| **Worker service account** | Executes DoFns and I/O on VMs | Dataflow Worker + scoped GCS/PubSub/BigQuery IAM |

**Distinction:** the SA of **orders-api on Cloud Run** and the Dataflow worker SA **are not the same principal by default**; when the job reads a subscription or writes to BigQuery, grant permissions to the **actual worker SA**, not the submitter.

### 8.2. Launching Batch via Maven/Java

Once the Maven project has the proper entrypoint and dependencies:

~~~bash
# Lab project example; do not run if buckets/SA are not created or lack permissions.
mvn -q compile exec:java \
  -Dexec.mainClass=com.example.pipeline.BeamSalesBatch \
  "-Dexec.args=--runner=DataflowRunner --project=shop-dev-001 --region=asia-southeast1 --stagingLocation=gs://shop-dev-001-dataflow-lab/staging --tempLocation=gs://shop-dev-001-dataflow-lab/temp --serviceAccount=dataflow-worker@shop-dev-001.iam.gserviceaccount.com --maxNumWorkers=3 --outputPrefix=gs://shop-dev-001-dataflow-lab/output/revenue"
~~~

The Dataflow Java Runner **stages artifacts** to Cloud Storage; the path from launcher to workers must package dependencies and the SDK properly. In some Maven setups, invoking **exec:java** does not automatically build an **uber JAR**; production workflows usually use a fat JAR, custom SDK container, or a tested **Flex Template**.

**Runtime checklist:** Dataflow console → Jobs → select job region → check **RUNNING/DONE state**, worker logs, execution graph, and CSV files. **DONE does not mean SUCCESS** if errors occurred. **Dataflow Runner** will not create or grant permissions on missing buckets, Pub/Sub resources, or BigQuery tables.

### 8.3. Flex Templates: Packaging for Reuse

A **Flex Template** consists of a **container image** (in Artifact Registry) and a **JSON template spec** (in Cloud Storage), allowing you to run the same graph with environment parameters. Ideal for production CI/CD and recurring jobs:

~~~text
Java source + tests
  → Maven package / Uber JAR
  → Artifact Registry image + template spec JSON
  → gcloud dataflow flex-template run (versioned parameters)
  → Dataflow job + runtime worker service account
~~~

Unlike source builds, **template specs must not contain application data or DB passwords**. Use Secret Manager/ADC and IAM configuration. Never use an unpinned **latest** tag in production; pin the image digest/version, store release metadata, and maintain an intentional rollback path.

## 9. Lab B — Streaming Pub/Sub, Windows, and Triggers

**Goal:** compute revenue by region in **five-minute fixed windows**, emitting provisional results and updating when late events arrive. This is a **learning demo** outputting to a Pub/Sub topic so **panes** are easy to inspect; it is not a financial ledger because the Pub/Sub sink does not guarantee exactly-once delivery.

Assume an existing subscription named **projects/shop-dev-001/subscriptions/sales-stream-sub**. Each message has a payload like:

~~~text
north,120
south,300
north,80
~~~

### 9.1. Java Streaming Example: `BeamSalesStreaming.java`

This code reuses **ParseSaleFn** from **BeamSalesBatch** in Section 7 (both classes live in the same Maven package):

~~~java
package com.example.pipeline;

import org.apache.beam.sdk.Pipeline;
import org.apache.beam.sdk.io.gcp.pubsub.PubsubIO;
import org.apache.beam.sdk.options.PipelineOptionsFactory;
import org.apache.beam.sdk.options.StreamingOptions;
import org.apache.beam.sdk.options.Validation;
import org.apache.beam.sdk.transforms.DoFn;
import org.apache.beam.sdk.transforms.ParDo;
import org.apache.beam.sdk.transforms.Sum;
import org.apache.beam.sdk.transforms.windowing.AfterPane;
import org.apache.beam.sdk.transforms.windowing.AfterProcessingTime;
import org.apache.beam.sdk.transforms.windowing.AfterWatermark;
import org.apache.beam.sdk.transforms.windowing.BoundedWindow;
import org.apache.beam.sdk.transforms.windowing.FixedWindows;
import org.apache.beam.sdk.transforms.windowing.IntervalWindow;
import org.apache.beam.sdk.transforms.windowing.PaneInfo;
import org.apache.beam.sdk.transforms.windowing.Window;
import org.apache.beam.sdk.values.KV;
import org.joda.time.Duration;

public final class BeamSalesStreaming {
    private BeamSalesStreaming() {}

    public interface StreamOptions extends StreamingOptions {
        @Validation.Required
        String getInputSubscription();
        void setInputSubscription(String value);

        @Validation.Required
        String getOutputTopic();
        void setOutputTopic(String value);
    }

    public static final class FormatPaneFn extends DoFn<KV<String, Long>, String> {
        @ProcessElement
        public void process(@Element KV<String, Long> result,
                            BoundedWindow window,
                            PaneInfo pane,
                            OutputReceiver<String> out) {
            IntervalWindow w = (IntervalWindow) window;
            out.output(w.start().toString() + "," + result.getKey()
                + "," + result.getValue() + "," + pane.getTiming());
        }
    }

    public static void main(String[] args) {
        StreamOptions opts = PipelineOptionsFactory.fromArgs(args)
            .withValidation()
            .as(StreamOptions.class);
        opts.setStreaming(true);

        Pipeline pipeline = Pipeline.create(opts);
        pipeline
            .apply("ReadPubSub", PubsubIO.readStrings()
                .fromSubscription(opts.getInputSubscription()))
            .apply("Parse", ParDo.of(new BeamSalesBatch.ParseSaleFn()))
            .apply("FixedWindow", Window.<KV<String, Long>>into(
                    FixedWindows.of(Duration.standardMinutes(5)))
                .triggering(AfterWatermark.pastEndOfWindow()
                    .withEarlyFirings(
                        AfterProcessingTime.pastFirstElementInPane()
                            .plusDelayOf(Duration.standardMinutes(1)))
                    .withLateFirings(AfterPane.elementCountAtLeast(1)))
                .withAllowedLateness(Duration.standardMinutes(10))
                .accumulatingFiredPanes())
            .apply("SumByRegion", Sum.longsPerKey())
            .apply("FormatPanes", ParDo.of(new FormatPaneFn()))
            .apply("PublishResults", PubsubIO.writeStrings()
                .to(opts.getOutputTopic()));

        pipeline.run(); // Streaming job keeps running until stopped.
    }
}
~~~

### 9.2. What This Code Actually Does

1. **PubsubIO.readStrings()** consumes text messages; timestamps default to Pub/Sub publish time, **not** the business event time inside the payload.
2. **ParseSaleFn** produces `KV(region, amount)`; malformed records fail the stage and can trigger retries — this demo has no dead-letter branch.
3. **FixedWindows(5 minutes)** partitions by the Beam-assigned timestamp; **AfterWatermark** emits the on-time pane.
4. **Early firing** occurs one minute of processing time after the first element in the pane; **late firing** emits whenever a late element arrives.
5. **10-minute allowed lateness** permits late window updates within bounds; **accumulating** emits the recomputed total.
6. **Pub/Sub output** contains window start, region, total, and pane timing; **one window can emit multiple messages**.

**When business event time is needed:** producers send an **event_ts** attribute in RFC 3339 UTC format, and you configure **PubsubIO.readStrings().withTimestampAttribute("event_ts")** to use the event's timestamp. You must verify that every publisher writes valid timestamps and satisfies the Pub/Sub/Dataflow connector's timing requirements; otherwise, windowing can be wrong or messages may not be handled as expected.

### 9.3. Creating Topics/Subscriptions in the Lab Project

~~~bash
# These commands create resources and may incur charges; run only when authorized.
gcloud services enable pubsub.googleapis.com dataflow.googleapis.com \
  --project=shop-dev-001

gcloud pubsub topics create sales-events --project=shop-dev-001
gcloud pubsub topics create sales-totals --project=shop-dev-001

gcloud pubsub subscriptions create sales-stream-sub \
  --project=shop-dev-001 \
  --topic=sales-events

gcloud pubsub subscriptions create sales-totals-view \
  --project=shop-dev-001 \
  --topic=sales-totals
~~~

**Create the subscription before publishing** if you want to receive all lab messages from the start. A subscription holds its own backlog; multiple subscribers on the same subscription **load-balance work**, rather than each subscriber receiving a copy of every event.

### 9.4. Launching Streaming on Dataflow

Run the Maven entrypoint in your built lab project; the staging bucket and Dataflow worker SA must be provisioned and granted IAM as in Section 8:

~~~bash
mvn -q compile exec:java \
  -Dexec.mainClass=com.example.pipeline.BeamSalesStreaming \
  "-Dexec.args=--runner=DataflowRunner --streaming=true --project=shop-dev-001 --region=asia-southeast1 --stagingLocation=gs://shop-dev-001-dataflow-lab/staging --tempLocation=gs://shop-dev-001-dataflow-lab/temp --serviceAccount=dataflow-worker@shop-dev-001.iam.gserviceaccount.com --inputSubscription=projects/shop-dev-001/subscriptions/sales-stream-sub --outputTopic=projects/shop-dev-001/topics/sales-totals"
~~~

The worker SA must have **roles/pubsub.subscriber** on the input subscription and **roles/pubsub.publisher** on the output topic, in addition to Dataflow Worker and bucket permissions. **Never grant Owner** to the worker just to bypass IAM errors.

Once the job is **RUNNING**, publish sample messages:

~~~bash
gcloud pubsub topics publish sales-events \
  --project=shop-dev-001 --message="north,120"
gcloud pubsub topics publish sales-events \
  --project=shop-dev-001 --message="north,80"
gcloud pubsub topics publish sales-events \
  --project=shop-dev-001 --message="south,300"

# Pull results only after the window/trigger has fired.
gcloud pubsub subscriptions pull sales-totals-view \
  --project=shop-dev-001 --limit=10 --auto-ack
~~~

Results may include **early panes** and **on-time panes**; three events published near a 5-minute boundary are not guaranteed to fall into the same window. **Never enable `--auto-ack` on a production subscription** just to inspect messages if losing unprocessed messages poses a risk.

**Note on monetary arithmetic:** the streaming example uses `long` for integer amounts, but real financial systems require idempotency, currency handling, overflow validation, reconciliation, and a sink with durable update semantics. Do not treat Pub/Sub pane outputs as a ledger.

## 10. BigQuery Integration: Choosing a Sink by Data Semantics

In production architectures, replace the Pub/Sub output with **BigQueryIO** or write a raw events table and aggregate in BigQuery:

~~~mermaid
flowchart LR
  API["Cloud Run orders-api"] --> PUB["Pub/Sub topic"]
  PUB --> BEAM["Beam / Dataflow"]
  BEAM --> VAL{"Valid record?"}
  VAL -->|Yes| BQ["BigQuery raw events / aggregates"]
  VAL -->|No| DLQ["Dead-letter Pub/Sub / GCS"]
  BQ --> BI["Looker / BI"]
~~~

| Output type | Recommended design | Notes |
|---|---|---|
| **Raw immutable events** | Append to BigQuery via **BigQueryIO Storage Write API** | Choose at-least-once/exactly-once write method per requirements; deduplicate by `eventId` |
| **Multi-pane window totals** | Write **window_start, region, pane_version, total**, then select latest or run idempotent **MERGE** | Appending every accumulating pane and running `SUM` will double-count |
| **End-of-day batch aggregates** | Write to a daily-partitioned BigQuery destination or GCS Parquet | Verify partition write/overwrite disposition |
| **Invalid events** | Dead-letter topic or GCS with error reason and masked event ID | Never retry bad data infinitely; protect PII |

For multi-pane rows, store **timestamp/window/key and update version** so BI reads the latest valid snapshot; consider separating **raw immutable facts** from **materialized aggregate** tables. **BigQueryIO alone does not turn external side effects inside a DoFn into exactly-once operations**.

## 11. Pipeline Exactly-Once vs. Business Exactly-Once

Google Cloud Dataflow currently supports two **streaming modes**:

| Mode | Guarantee inside Dataflow | When to choose |
|---|---|---|
| **Exactly-once (default)** | **Committed** record results are not reflected more than once within the pipeline's guarantee scope | Accurate counts/aggregations, sensitive business logic |
| **At-least-once** | Records are not lost, though they may be reflected more than once | Map-only ETL, downstream deduplication exists, optimizing latency/cost |

In Java, to select **at-least-once mode** on Dataflow:

~~~text
--dataflowServiceOptions=streaming_mode_at_least_once
~~~

At-least-once mode requires **Streaming Engine with resource-based billing**; choose a compatible write method (for example, **BigQueryIO STORAGE_API_AT_LEAST_ONCE** when writing to BigQuery). This mode **is incompatible with BigQueryIO FILE_LOADS** in streaming pipelines. Changing the streaming mode of a running job requires a **replacement job**; do not assume a live environment-variable change will switch it.

### 11.1. Why Exactly-Once Does Not Guarantee Single Side-Effect Execution

A **DoFn can re-execute** after a worker failure even though Dataflow commits checkpointed output only once. If a DoFn directly calls an HTTP payment endpoint or sends an email, that side effect can run **twice**:

~~~text
ProcessElement(eventId=E1)
  → calls Payment API: succeeds
  → worker crashes before checkpointing output
  → retries ProcessElement(E1)
  → calls Payment API again
~~~

**Proper approach:** use an **eventId/idempotency key**, conditional state writes in a database, the transactional outbox pattern, or connectors/sinks with appropriate semantics. **Never execute non-idempotent side effects** inside a DoFn and assume Dataflow protects external systems.

### 11.2. Deduplication at the Pub/Sub Layer

- Pub/Sub can **redeliver** the same message; Dataflow exactly-once deduplicates redeliveries by Pub/Sub message ID.
- If a producer **publishes the same business event twice** as two distinct Pub/Sub message IDs, Dataflow **cannot automatically know** they represent the same transaction.
- With the Dataflow Pub/Sub connector, you can use **withIdAttribute** to deduplicate by a business ID attribute consistently set by the publisher, subject to limitations (documentation specifies a **10-minute** window) and coordination with sinks/retention.
- **Enabling Pub/Sub exactly-once delivery for Dataflow is not recommended** just to double up guarantees, as Dataflow already handles message-ID deduplication and doing so can reduce throughput.
- The Pub/Sub **output sink does not guarantee exactly-once delivery**; downstream consumers must still be idempotent.

### 11.3. Exactly-Once Does Not Mean Complete Results

The watermark may advance before an actual event arrives. Dataflow can accurately sum **records received within allowed lateness**, while still missing events that arrive beyond that threshold. You need a **late-data SLA**, batch reconciliation/backfill, and business rules for marking reports as "final". **Late panes, duplicates, idempotency, and output consistency** are four distinct concerns.

## 12. IAM, Networking, Deployment, and Data Protection

### 12.1. Role-Based IAM

| Principal | Appropriate permissions | Risk if misconfigured |
|---|---|---|
| **CI submitter** | Dataflow Developer/Admin per task; **iam.serviceAccounts.actAs** on worker SA | Cannot submit jobs or gains overly broad privileges |
| **Dataflow service agent** | Service Agent managed role to create/manage VMs | Revoking roles prevents jobs from starting |
| **Dataflow worker SA** | Dataflow Worker, read GCS/PubSub inputs, write BigQuery/PubSub sinks and staging/temp | Runtime `403`, or full project exposure if granted Owner |
| **Data analyst/BI** | Dataset/table viewer and query permissions | Does not need the Dataflow Worker role |
| **Security/KMS operator** | Manages keys and audits per policy | Should not grant themselves payload read access |

Example of scoped separation:

- **roles/pubsub.subscriber** on the input subscription, **roles/pubsub.publisher** on the output topic.
- **roles/storage.objectViewer** on the input bucket; required object create/modify permissions scoped strictly to **staging/temp/output buckets**.
- **roles/bigquery.dataEditor** on the sink dataset/table as needed for writes; BigQuery job creation permissions if required by the connector/write mode.
- **roles/dataflow.worker** on the worker service account in the project running the job.

**Never grant Dataflow Admin, Pub/Sub Editor, and BigQuery Admin to all workers** just to silence a `403`. The Dataflow service agent follows the format **service-PROJECT_NUMBER@dataflow-service-producer-prod.iam.gserviceaccount.com**, distinct from the user-managed worker SA **dataflow-worker@...**.

### 12.2. VPC and Regional Locality

Dataflow Runner provisions compute in the specified **region**; verify:

1. **Dataflow worker region** is close to Pub/Sub/BigQuery/buckets and complies with residency rules.
2. **Cloud Storage staging/temp buckets** use an appropriate location; temporary data may contain sensitive information.
3. With **private workers / `--usePublicIps=false`**, the VPC/subnet, Private Google Access, DNS, Cloud NAT, or private API access must allow workers to reach Google APIs and fetch dependencies.
4. When accessing private-IP Cloud SQL or on-premises systems, configure VPC routing/VPN/Interconnect, firewall rules, and dedicated database authentication.
5. If using **customer-managed encryption keys (CMEK)**, configure the Dataflow KMS key in a supported feature/location and grant KMS IAM to the appropriate service agents/principals; never substitute CMEK for source/sink IAM.

**There is no guarantee** that Dataflow running in region A can automatically join or write to a BigQuery dataset in region B without location constraints. Check the resource location of **every sink**.

### 12.3. Never Put Secrets in Pipeline Options

Arguments, job configuration, logs, and template metadata are visible to authorized users. Never pass **DB passwords, API tokens, or customer PII** directly on the command line via **--password=...**. Use **Secret Manager**, Workload Identity/ADC, IAM, and log masking. **Do not log every message payload** in production to avoid unnecessary cost, latency, and personal data exposure.

## 13. Operations: Job Lifecycle, Monitoring, and Cost Control

### 13.1. Monitoring the Right Metrics

| Metric | When abnormal | What to check |
|---|---|---|
| **Job state/failed work items** | `FAILED` or prolonged retries | Worker logs, exceptions, failing DoFn |
| **Elements processed per stage** | Input has data but output stalls | Stage graph, filters, DLQ, sink permissions |
| **Pub/Sub backlog bytes / oldest unacked age** | Growing continuously | Worker capacity, I/O throttling, hot keys |
| **Data freshness** | Event time reaching output falls further behind | Watermark, late data, source backlog |
| **System latency** | Elements take or wait too long to process | Hot keys, slow side effects, sink I/O |
| **Watermark progress** | Stuck at an old timestamp | Stuck elements, retries, input timestamps |
| **Worker CPU/memory/restarts** | High CPU, OOM, repeated restarts | Machine type, parsing memory, hot keys |
| **Autoscaling worker count** | Hits `maxWorkers` while backlog grows | Quota/capacity, `maxNumWorkers`, stage bottleneck |
| **Sink errors/quota** | BigQuery rate limits or Pub/Sub errors | IAM, Write API quotas, retry/backoff |
| **Dead-letter count** | Spikes after a release | Input schema drift, validation, upstream data |

**Diagnostic rule:** if **both data freshness delay and backlog bytes increase**, the pipeline cannot keep up or is stalled. If freshness degrades while backlog stays normal, a few elements may be stuck inside stages. Always inspect stage metrics and logs rather than blindly raising worker count.

### 13.2. Actions on a Running Job

| Action | Effect | When to use |
|---|---|---|
| **Cancel** | Stops the job immediately; may drop buffered data | Broken test job or incident requiring immediate halt |
| **Drain** | Stops ingesting new data and attempts to process buffered data before stopping | Controlled shutdown of a streaming job |
| **Update/replacement** | Replaces a streaming job with a new version within compatibility constraints | Releasing new code/graph |
| **Batch rerun** | Runs a new batch job over source data | Backfill or reprocessing after a bug fix |

**Drain does not roll back already-written data**; **cancel** can leave business gaps without a replay strategy. Updating a streaming graph that uses state/timers/windows requires evaluating **compatibility and checkpoint behavior**; do not assume every update is zero-downtime.

### 13.3. Cost Components to Measure

| Component | How charges accrue |
|---|---|
| **Worker VMs CPU/memory** | Machine type, worker count, runtime duration |
| **Batch/Streaming shuffle, Streaming Engine** | Managed service resources based on pricing model and volume processed |
| **Dataflow Prime** | DCUs/resource-based billing when enabled |
| **Cloud Storage staging/temp/output** | Storage, operations, temporary data, and retention |
| **Pub/Sub/BigQuery** | Delivery, throughput, Storage Write API, queries/storage |
| **Network** | Cross-region transfers/egress, backend connectivity |
| **Cloud Logging/Monitoring** | Log volume/retention/alerts per active pricing |

**Exactly-once streaming** adds checkpointing and deduplication work; **at-least-once** can save resources for map-only ETL when downstream tolerates duplicates. Dataflow **Streaming Engine** is generally recommended for streaming; resource-based billing uses **Streaming Engine Compute Units** when selected, whereas Dataflow Prime has its own **Data Compute Units (DCUs)** model. Never apply a single flat rate to every job or assume Cloud Run/BigQuery pricing includes Dataflow charges.

**Principled cost reduction:** choose batch if the SLO permits; cap `maxNumWorkers` based on benchmarks; right-size machine types; avoid per-event logging; partition/filter data early and eliminate hot keys; set lifecycle policies on GCS staging/temp buckets. Consider **FlexRS** for delay-tolerant batch jobs and **commitments** for steady workloads per policy, not for every lab exercise.

**The Dataflow console Cost tab shows estimates**, not the final invoice. Reconcile against **Cloud Billing reports** after jobs run; budgets/alerts do not automatically stop jobs.

## 14. Layer-by-Layer Beam and Dataflow Troubleshooting

| Symptom | Likely root cause | Check |
|---|---|---|
| Local DirectRunner works, DataflowRunner fails immediately | SDK/container dependency, service account, staging bucket | Build logs, job submission logs, permissions |
| Job created and stuck in `PENDING` | Region/quota, workers cannot start, networking | Dataflow jobs, Compute Engine quotas, service agent |
| **`PERMISSION_DENIED`** reading subscription | Worker SA lacks Pub/Sub Subscriber or wrong project | Subscription IAM, job worker identity |
| **`PERMISSION_DENIED`** writing BigQuery | Worker SA / BigQuery sink permissions | Table/dataset IAM, BigQuery API/quota |
| **`STORAGE_PERMISSION_DENIED`** on GCS | Incorrect staging/temp bucket permissions | Bucket IAM, region, object path |
| Repeated `NumberFormatException` on parse | Malformed input fails the entire bundle | Side output DLQ, schema validation, retry handling |
| Streaming job produces no output | Trigger hasn't fired, watermark hasn't passed window end | Watermark, panes, event timestamps |
| Dataflow outputs multiple records per window/key | Early/on-time/late accumulating panes or Pub/Sub sink duplicates | Pane timing, idempotent upsert, `eventId` |
| "Exactly-once" yet payment API called twice | DoFn side effect retried | Idempotency key, outbox, avoid external side effects |
| Backlog grows while CPU is low | Sink throttling, blocked RPCs, hot key | Stage latency, pending work, external quotas |
| High CPU in one stage | Key skew, excessive serialization, or expensive UDF | Hot-key metrics, Combine/fanout, coder |
| Output misses very late events | Allowed lateness/window already closed | Timestamp policy, late-event DLQ, batch reconciliation |
| Wrong results with no worker errors | Incorrect event time, trigger accumulation, or duplicate source data | Event timestamps, pane semantics, dedup ID |
| Worker OOM | DoFn buffers entire group in memory, huge side input, memory leak | Heap, grouping design, worker machine type |
| Batch finishes but file is missing | `TextIO` sharded output, wrong path prefix | GCS bucket/path, job state, output shards |
| Unprocessed events remain after cancel | Buffered data not drained, in-flight sink writes | Pub/Sub backlog, source offset/replay, sink checks |

### 14.1. Rapid Investigation Procedure

1. **Confirm project/region/job ID** and state; do not confuse a local/DirectRunner run with Cloud Dataflow.
2. **By stage:** inspect input elements, failed elements, watermark, system latency, and backlog bytes.
3. **By principal:** verify the **Dataflow worker SA**, Pub/Sub/BigQuery/GCS IAM, and VPC path.
4. **By data semantics:** inspect timestamps, windows, triggers, panes, DLQ, duplicate `eventId`s, and sink mode.
5. **By capacity:** inspect autoscaling, CPU/memory, hot keys, and external rate limits.
6. **After fixing:** run replay/backfill on a known dataset and compare outputs against an oracle—do not stop at seeing the job reach `RUNNING`.

Never try to "fix" every issue by granting Owner, raising `maxWorkers`, or switching to at-least-once. That can inflate cost, break correctness, or mask underlying data bugs.

## 15. End-to-End Scenario: Event-Driven Order Revenue

Company **Blue River** needs a near-real-time revenue dashboard with the ability to reload historical data after bugs. The team operates:

- **Cloud Run Java orders-api** writing transactions to Cloud SQL and publishing confirmed events.
- **Pub/Sub topic `orders-events`** carrying asynchronous events.
- **Dataflow streaming** normalizing events and computing 5-minute revenue.
- **BigQuery** storing raw events and aggregate tables for Looker.
- **Cloud Storage** holding exports for backfill with IAM and retention controls.

### 15.1. Recommended Architecture

~~~mermaid
flowchart LR
  API["Cloud Run Java"] --> SQL["Cloud SQL orders"]
  API --> PUB["Pub/Sub orders-events"]
  PUB --> DF["Beam → Dataflow"]
  DF --> VAL{"Validate schema / eventId"}
  VAL -->|"Valid"| RAW["BigQuery raw_events"]
  VAL -->|"Invalid"| DLQ["Pub/Sub dead-letter + alert"]
  RAW --> AGG["Beam windows or BigQuery SQL"]
  AGG --> BQ["BigQuery 5-min aggregates"]
  BQ --> BI["Looker dashboard"]
  GCS["Cloud Storage exports"] --> BACK["Batch Beam backfill"]
  BACK --> RAW
~~~

**Design note:** if Java `orders-api` updates Cloud SQL and then publishes to Pub/Sub in two separate calls, a **dual-write failure** can occur: the DB commits, but the publish fails. Consider the **transactional outbox** pattern or CDC for your database engine to avoid dropped events; Dataflow exactly-once cannot fix events that were never published.

### 15.2. Business Decisions and Beam Design

| Concern | Recommended decision |
|---|---|
| **Source event** | Unique `eventId`, `orderId`, UTC event time, schema version, integer-unit amount |
| **Correctness** | Dataflow exactly-once for accurate aggregations; sink supports idempotency |
| **Duplicate publishes** | Deduplicate by `eventId`, not just Pub/Sub message ID; add reconciliation |
| **Late events** | 5-minute fixed windows, early previews and late updates within SLA, backfill past threshold |
| **Invalid events** | Side output DLQ + alert; never log PII or full payloads |
| **BI consumption** | BigQuery keyed by `window_start + region`, reading latest snapshot/changelog with proper semantics |
| **Scaling** | `Combine.perKey`, monitor hot keys, configure autoscaling by backlog/freshness |
| **Operations** | Least-privilege worker SA, staging/temp in compliant region, dashboards + Cloud Billing |

### 15.3. Data and Window Walkthrough

Assume all events carry **event time**:

| Event | Time | Region | Amount | Pipeline arrival |
|---|---|---|---:|---|
| E1 | 10:01 | north | 120 | 10:01 |
| E2 | 10:03 | north | 80 | 10:03 |
| E3 | 10:04 | south | 300 | 10:04 |
| E4 | 10:02 | north | 50 | 10:07 (late relative to window end) |

All events above belong to **[10:00,10:05)** by event time. While E4 is within allowed lateness with an active late trigger, the true total for `north` is **250** and `south` is **300**. If the dashboard first received pane `north=200` and later received accumulating pane `north=250`, it must **replace 200 with 250**, not sum them to 450.

**Always check the actual watermark**: E4 arriving at 10:07 is not necessarily late in Beam if the watermark has not yet passed 10:05. Never infer lateness solely from wall-clock time.

### 15.4. Pre-Release Test Scenarios

| Test | Expected outcome |
|---|---|
| Batch with the same 4 records, no errors | `north=250`, `south=300` |
| Streaming with a late record within limit | Window output updates accurately |
| Record arriving past allowed lateness | Clear drop/DLQ/reconciliation policy executed |
| Sending E2 twice with the same `eventId` | Revenue does not double after deduplication |
| Dataflow worker restart | Pipeline recovers; external side effects do not repeat due to idempotency |
| Malformed-schema event | Routed to DLQ; job does not stall indefinitely |
| Pub/Sub backlog spike | Data freshness / system latency alerts trigger |
| BigQuery sink IAM blocked | Job logs surface error; worker SA receives scoped fix |
| Window/trigger code change | Update/backfill plan protects state and downstream consumers |
| Scheduled streaming shutdown | Drain/replay plan executed; buffered data verified |

## 16. Exercises and Suggested Answers

### Exercise A — Beam or Dataflow?

**Question:** A program declares `ParDo`, `Window`, and `Combine`, and runs using `DirectRunner`. Is it using the Dataflow service?

**Answer:** No. The program **uses Apache Beam**, and `DirectRunner` executes it locally. It only runs on Dataflow when you select **`DataflowRunner`** and submit a valid job to GCP.

### Exercise B — Bounded vs. Unbounded

**Data:** an immutable end-of-day CSV file and a Pub/Sub subscription receiving continuous events.

**Answer:** The CSV file is **bounded** and can be processed in batch; the Pub/Sub subscription is **unbounded** and requires streaming or an explicit read boundary. Windowing and triggering must be designed when grouping unbounded data.

### Exercise C — Graph Summation

Input: `north,120`; `south,300`; `north,80`; `south,50`. Pipeline uses `Parse → KV(region, amount) → Sum.longsPerKey`.

**Answer:** **`north=200, south=350`**. Output line order is not guaranteed by Beam.

### Exercise D — Event Time and Processing Time

An event has event time **10:02** but reaches the pipeline at **10:07**, with 5-minute fixed windows.

**Answer:** By event time, it belongs to **[10:00,10:05)**. By processing time, it falls in **[10:05,10:10)**. Whether it is included in the event-time window depends on the **watermark, allowed lateness, and trigger**.

### Exercise E — Accumulating Panes

The `north` window emits totals **100**, then **150**, then **160** across three accumulating panes. BI sums all three to get 410.

**Answer:** Incorrect. These are **three snapshots of the same window**; the latest total is **160**. The sink must use upsert/latest-pane selection rather than summing all snapshots.

### Exercise F — DoFn and Exactly-Once

A `DoFn` calls a payment API; the worker restarts after the API returns `200` but before checkpointing, and the callback runs again.

**Answer:** Dataflow exactly-once **does not guarantee an external side effect runs only once**. Use an idempotency key, transactional outbox, or move side effects outside retryable callbacks by design.

### Exercise G — At-Least-Once Mode

A pipeline only parses and renames fields, and the BigQuery sink deduplicates by `eventId`. Should at-least-once be considered?

**Answer:** It can be **evaluated** because the pipeline is map-only and downstream tolerates duplicates, potentially lowering latency/cost. Verify compatible Write API methods, duplicate metrics, and accuracy; never enable it when aggregations require exactly-once without duplicate protection.

### Exercise H — Hot Keys and Scaling Workers

80% of events have `region=unknown`, and a stage stays slow even after doubling `maxNumWorkers`.

**Answer:** There is **data skew / a hot key**; adding workers alone may not help. Inspect stage metrics, key distribution, `Combine`/fanout, data validation, and key/window design.

### Exercise I — Worker IAM

The job submitter has BigQuery Editor, yet Dataflow throws `403` when workers write to the sink.

**Answer:** Workers run under a **separate worker service account** and do not inherit the submitter's IAM roles. Grant BigQuery write permissions on the target dataset/table to the worker SA, and verify the Dataflow Worker role and staging access.

### Exercise J — Drain and Cancel

A streaming job has 50,000 buffered events, and the team wants to deploy a new revision without losing data.

**Answer:** Plan a **drain** to stop ingesting new data and finish processing buffered work as appropriate, or use a **replacement update** if the graph/state is compatible. **Cancel** can discard in-flight work in the pipeline, requiring replay/backfill from the source and sink verification. There is no "undo" for writes already committed.

### Exercise K — Calculating Freshness

Event time is 10:00, and the dashboard displays the result at 10:04. Assume timestamps and clocks are accurate.

**Answer:** The data freshness / end-to-end latency for this event is **4 minutes**. In practice, inspect the **watermark, source backlog, and stage system latency** rather than evaluating the whole pipeline's SLO from a single event.

### Exercise L — Choosing Batch vs. Streaming

A data warehouse needs a report every morning with up to 6 hours of acceptable delay; the business wants lower cost and needs no real-time alerts.

**Answer:** Prefer a **scheduled batch job** from GCS/BigQuery if it meets the deadline and correctness requirements. Running 24/7 streaming just because events originate in Pub/Sub is not necessarily optimal.

## 17. Summary and References

**Six principles to remember:**

1. **Apache Beam defines the graph; the runner executes it.** `DataflowRunner` uses managed Dataflow workers; `DirectRunner` is for local execution and testing.
2. **`PCollection` is distributed data**, and `PTransform` is a transformation; choose `ParDo`/`DoFn`, `KV`, `Combine`, I/O connectors, and coders to match your goal.
3. **Batch is bounded; streaming is unbounded.** For unbounded aggregations, event time, windows, watermarks, triggers, and allowed lateness govern latency and completeness.
4. **Dataflow exactly-once is an intra-pipeline commit guarantee**, not coverage for external side effects; duplicate inputs and sink delivery require dedicated idempotency.
5. **Worker identity differs from submitter and service agent.** IAM, staging/temp, VPC, and location must be verified across both sources and sinks.
6. **Correctness first, optimization second:** test with late, duplicate, and skewed data; monitor backlog/freshness/latency/cost before tuning autoscaling and streaming modes.

**Official Documentation:**

1. [Apache Beam Programming Guide](https://beam.apache.org/documentation/programming-guide/) — PCollections, transforms, windowing, triggers, and state.
2. [Apache Beam Java SDK dependencies](https://beam.apache.org/documentation/sdks/java-dependencies/) — BOM, dependencies, dependency pinning.
3. [Dataflow Beam programming model](https://docs.cloud.google.com/dataflow/docs/concepts/beam-programming-model) — Beam abstractions and runners.
4. [Dataflow Runner options](https://beam.apache.org/documentation/runners/dataflow/) — project, region, streaming, staging/temp.
5. [Deploy Dataflow pipelines](https://docs.cloud.google.com/dataflow/docs/guides/deploying-a-pipeline) — Dataflow job lifecycle.
6. [Beam windowing/watermarks on Dataflow](https://docs.cloud.google.com/dataflow/docs/concepts/streaming-pipelines) — time, triggers, lateness.
7. [Read Pub/Sub with Dataflow](https://docs.cloud.google.com/dataflow/docs/concepts/streaming-with-cloud-pubsub) — timestamps, deduplication, and ACKs.
8. [Exactly-once in Dataflow](https://docs.cloud.google.com/dataflow/docs/concepts/exactly-once) — limitations on external side effects.
9. [Set streaming mode](https://docs.cloud.google.com/dataflow/docs/guides/streaming-modes) — exactly-once/at-least-once.
10. [Write to Pub/Sub](https://docs.cloud.google.com/dataflow/docs/guides/write-to-pubsub) — sink delivery guarantees.
11. [Dataflow security and permissions](https://docs.cloud.google.com/dataflow/docs/concepts/security-and-permissions) — service agents/worker IAM.
12. [Build Flex Templates](https://docs.cloud.google.com/dataflow/docs/guides/templates/configuring-flex-templates) — container, template spec.
13. [Dataflow job metrics](https://docs.cloud.google.com/dataflow/docs/guides/using-monitoring-intf) — freshness, system latency, backlog.
14. [Troubleshoot slow streaming jobs](https://docs.cloud.google.com/dataflow/docs/guides/troubleshoot-slow-streaming-jobs) — stage bottlenecks.
15. [Stop Dataflow jobs](https://docs.cloud.google.com/dataflow/docs/guides/stopping-a-pipeline) — cancel, drain, force-cancel.
16. [Optimize Dataflow costs](https://docs.cloud.google.com/dataflow/docs/optimize-costs) — workers, Streaming Engine, pricing models.
17. [Streaming Engine](https://docs.cloud.google.com/dataflow/docs/streaming-engine) — compute/storage split, resource-based billing.
