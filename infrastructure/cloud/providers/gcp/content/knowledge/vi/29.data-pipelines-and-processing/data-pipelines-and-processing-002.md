# Apache Beam và mô hình lập trình Dataflow

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Apache Beam SDK** (định nghĩa pipeline) với **Google Cloud Dataflow** (dịch vụ thực thi bằng Dataflow Runner), và **Direct Runner** khi phát triển.
2. Sử dụng **Pipeline, PCollection, PTransform, ParDo/DoFn, KV, GroupByKey, Combine** và I/O connectors.
3. Phân biệt **bounded/unbounded data**, **batch/streaming**, **event time/processing time**, **window, watermark, trigger, pane** và **allowed lateness**.
4. Viết pipeline Java kiểm thử cục bộ rồi chạy bằng Dataflow Runner; đọc job metrics và lỗi.
5. Thiết kế Pub/Sub → transforms → BigQuery/Pub/Sub với **idempotency, error handling, IAM, autoscaling và chi phí**.
6. Giải thích dữ liệu tới muộn, duplicate events, hot keys, backlog, failover và release pipeline an toàn.

## 1. Bối cảnh và hai lớp cần phân biệt

Ứng dụng Java **orders-api** trên Cloud Run ghi giao dịch vào Cloud SQL và phát sự kiện **order.created** vào Pub/Sub. Công ty cần tổng doanh thu mỗi năm phút và tái xử lý dữ liệu lịch sử từ Cloud Storage để kiểm tra chiến dịch. Nhóm không muốn viết hai hệ thống xử lý dữ liệu hoàn toàn khác nhau cho batch và streaming.

**Apache Beam** giải quyết phần **lập trình dữ liệu**: graph đọc → biến đổi → nhóm/tổng hợp → ghi. **Cloud Dataflow** là **managed runner/service** của Google Cloud: tạo và quản lý worker, phân phối công việc, khôi phục, giám sát. Đây không phải hai tên của cùng một thư viện:

| Lớp | Người phát triển thực hiện | Ví dụ |
|---|---|---|
| **Apache Beam SDK** | Định nghĩa graph và logic bằng Java/Python/Go | PCollection, ParDo, Window, IO |
| **Runner** | Biến graph thành thực thi | DirectRunner local, DataflowRunner GCP |
| **Dataflow service** | Vận hành worker VMs, autoscaling, shuffle, UI/jobs/metrics | Batch ETL, streaming liên tục |
| **Nguồn/đích** | Cung cấp/nhận dữ liệu với IAM/chi phí riêng | Pub/Sub, GCS, BigQuery, Cloud SQL |

~~~mermaid
flowchart LR
  S["Pub/Sub / GCS / BigQuery"] --> I["Beam IO.Read"]
  I --> P["PCollection"]
  P --> T["PTransform: ParDo / Window / Combine"]
  T --> O["Beam IO.Write"]
  O --> D["BigQuery / Pub/Sub / GCS"]
  R["Runner: DirectRunner hoặc DataflowRunner"] -. "Thực thi graph Beam" .-> T
  DF["Dataflow: workers, autoscaling, monitoring"] -. "Khi dùng DataflowRunner" .-> R
~~~

Trong **CLOUD_PROVIDERS_GCP**, Beam/Dataflow liên kết IAM/VPC, Cloud Run/GKE, Pub/Sub, GCS và BigQuery với độ tin cậy/chi phí. **Dataflow không phải Dataform**: Dataform chủ yếu quản lý các phép chuyển đổi SQL trong BigQuery, Beam lập trình xử lý record/event dùng nhiều runners.

## 2. Mô hình Pipeline, PCollection và PTransform

| Thành phần | Chức năng | Lưu ý |
|---|---|---|
| **Pipeline** | Đồ thị tổng thể của transforms | Định nghĩa trước, chạy khi gọi run |
| **PipelineOptions** | Runner, project, region, staging/temp, streaming, options tự định nghĩa | Không hardcode secret |
| **PCollection<T>** | Tập elements phân tán kèm timestamps/windows | Không phải Java List trên driver |
| **PTransform** | Biến đổi tạo graph, có thể ghép nhiều bước | Có thể nhận/trả nhiều PCollections |
| **ParDo + DoFn** | Xử lý phần tử, phát 0..n kết quả | Có thể được gọi lại vì retry |
| **KV<K,V>** | Key/value để tổng hợp theo key | GroupByKey/Combine.perKey |
| **Coder<T>** | Mã hóa data giữa các workers/shuffle | Type tự định nghĩa cần coder nhất quán |
| **Side input/output** | Dữ liệu tham chiếu hoặc nhánh lỗi | Dùng cho lookup nhỏ, dead-letter |
| **Window/Trigger/Pane** | Gán miền thời gian và phát kết quả | Cốt lõi của stream aggregations |

### 2.1. Graph không phải lệnh Java chạy tuần tự tại laptop

~~~java
PCollection<String> raw = pipeline.apply("Read", source);
PCollection<KV<String, Long>> values = raw.apply("Parse", parser);
PCollection<KV<String, Long>> totals = values.apply("Sum", Sum.longsPerKey());
totals.apply("Write", sink);
pipeline.run();
~~~

**Đây là pseudocode có chủ đích**: các biến pipeline, source, parser, sink phải được khai báo trong chương trình thật. Runner có thể **fuse** các transforms, chạy song song các bundles và **chạy lại DoFn** khi worker gặp lỗi. Không dựa vào thứ tự thực thi giữa các events hay side effects ngoài pipeline chỉ xảy ra một lần.

### 2.2. Tính bất biến và tính phân tán

Mỗi transform trả về PCollection mới; không dùng vòng for trên một PCollection ở driver. **Bounded PCollection** có tập hữu hạn (file cuối ngày); **unbounded PCollection** liên tục phát sinh (Pub/Sub). Timestamp và window quyết định dữ liệu có thể được nhóm với nhau.

**Unbounded không đồng nghĩa lưu vô hạn vào RAM:** phải có cách giới hạn trạng thái/aggregation, thường qua windowing.

## 3. Biến đổi dữ liệu: những transforms thường gặp

| Transform | Dùng để | Ví dụ |
|---|---|---|
| **Create, TextIO, PubsubIO** | Đọc nguồn | Dòng CSV, thông điệp |
| **MapElements** | Biến đổi 1→1 | Chuẩn hóa region |
| **Filter** | Giữ record hợp lệ | Chỉ status=PAID |
| **FlatMapElements/ParDo** | Biến đổi 1→0..n và validation | Parse một event ra nhiều outputs |
| **WithKeys/KV** | Gắn key | region → amount |
| **GroupByKey** | Gom values theo key/window | Nhóm theo merchant |
| **Combine.perKey, Sum.longsPerKey** | Tổng hợp phân tán | Doanh thu theo region |
| **CoGroupByKey** | Join hai PCollections cùng key | Orders + metadata |
| **Window.into** | Phân theo event time | 5 phút/window |
| **TextIO, BigQueryIO, PubsubIO.Write** | Ghi kết quả | GCS, BigQuery, Pub/Sub |

**Composite PTransform** có thể gói parse → validate → key, tái sử dụng giữa batch/streaming và kiểm thử độc lập. Tránh DoFn lớn chứa cả SQL client, retry, logging và UI logic.

### 3.1. Hot key và phép gộp

Nếu 90% events dùng cùng key **unknown**, GroupByKey có thể dồn việc lên ít workers, gây **hot key**. Ưu tiên **Combine.perKey** cho tổng/đếm associative; đánh giá fanout/sharding khi thích hợp. Không thu mọi values vào một Java List trong DoFn. Chỉ tăng workers không đảm bảo sửa được data skew.

## 4. Bounded/batch so với unbounded/streaming

| Tiêu chí | Batch | Streaming |
|---|---|---|
| Input | File/snapshot có điểm kết thúc | Pub/Sub/Kafka liên tục |
| Execution | Job hoàn thành | Job chạy đến khi drain/cancel |
| Window | Có thể global khi dữ liệu hữu hạn | Thường fixed/sliding/session window |
| Xử lý trễ | Thường có tập dữ liệu đầy đủ | Late/out-of-order events, watermark |
| Giám sát | Completion, duration, failures | Backlog, system latency, data freshness |
| Chi phí | Tài nguyên khi job chạy, dịch vụ phụ trợ | Workers/Streaming Engine thường chạy liên tục |

Với nguồn Pub/Sub không kết thúc phải cấu hình **--streaming=true** khi chạy DataflowRunner; với batch file thì không. Cùng một thuật toán chuyển đổi phần tử có thể dùng trong cả hai mô hình, nhưng I/O và windowing/trigger khác nhau.

**Quy tắc chọn:** báo cáo doanh thu cuối ngày dùng batch có thể đơn giản hơn; phát hiện gian lận gần real-time chọn streaming; dashboard cập nhật 15 phút cần so **freshness SLO** với chi phí trước khi quyết định.

## 5. Event time, processing time, watermark, window và trigger

~~~text
Event A: xảy ra 10:01 → tới pipeline 10:01
Event B: xảy ra 10:02 → tới pipeline 10:06 (trễ)
Event C: xảy ra 10:04 → tới pipeline 10:04

Theo event time: A, B, C cùng thuộc [10:00,10:05).
Theo processing time: B có thể nằm trong [10:05,10:10).
~~~

| Khái niệm | Định nghĩa |
|---|---|
| **Event time** | Thời điểm sự kiện thực xảy ra, theo timestamp nguồn |
| **Processing time** | Thời điểm worker xử lý record |
| **Watermark** | Ước lượng tiến độ event time; **không bảo đảm** mọi event cũ đã tới |
| **Window** | Khoảng thời gian để nhóm elements |
| **Trigger** | Quyết định khi nào phát kết quả |
| **Pane** | Mỗi đợt output của một window |
| **Allowed lateness** | Thời gian chấp nhận late events sau mốc watermark/window |

### 5.1. Windowing theo nhu cầu

| Loại | Ví dụ | Công dụng |
|---|---|---|
| **Fixed** | [10:00–10:05), [10:05–10:10) | Doanh thu mỗi 5 phút |
| **Sliding** | Window 10 phút, trượt mỗi phút | Moving totals, một event thuộc nhiều windows |
| **Session** | Ngắt 30 phút không hoạt động | Phiên người dùng, windows có thể merge |

~~~mermaid
flowchart LR
  E1["10:01 A"] --> W["Window 10:00–10:05"]
  E2["10:02 B (tới trễ)"] --> W
  E3["10:04 C"] --> W
  W --> T["Trigger: early / on-time / late"]
  T --> P1["Pane sớm"]
  T --> P2["Pane cập nhật"]
~~~

Watermark là ước lượng nên late events vẫn có thể xuất hiện. **Allowed lateness** giới hạn thời gian giữ state để cập nhật window. Một pipeline không thể bảo đảm đầy đủ tuyệt đối các events tới muộn vô hạn.

### 5.2. Accumulating so với discarding

Giả sử ba panes của một window có các thay đổi: 100 (sớm), thêm 50 (on-time), thêm 10 (late).

| Chế độ | Kết quả từng pane |
|---|---|
| **Accumulating** | 100 → 150 → 160 (mỗi pane chứa số cộng dồn) |
| **Discarding** | 100 → 50 → 10 (mỗi pane chỉ chứa phần mới) |

**Không SUM tất cả các accumulating panes để tính tổng**: 100+150+160 sẽ đếm lặp. Với dữ liệu được phát nhiều lần, sink nên **upsert theo (window_start, key)** hoặc xử lý changelog/overwrite có chủ đích. **Một trigger dùng processing time** không biến event time thành processing time.

## 6. Stateful processing, timers và luồng lỗi

- **State API** lưu state theo **key + window**, do runner quản lý; không dùng mutable global map trong Java worker.
- **Timers** lên lịch logic theo **event time/processing time**, ví dụ chờ 5 phút xem có payment-completed event không.
- **Side inputs** đưa bảng tham chiếu nhỏ đến workers; nếu lookup rất lớn hoặc biến động thường xuyên cần thiết kế khác.
- **Side outputs (TupleTag/PCollectionTuple)** tách records sai (JSON lỗi, thiếu amount, enum lạ) sang nhánh dead-letter với mã lỗi, thay vì lặp vô hạn làm tắc job.

State/timers cho phép nghiệp vụ phức tạp nhưng tăng chi phí giữ state, độ khó xử lý late data và kiểm thử. Chỉ dùng khi transforms đơn giản + windowing chưa đủ.

## 7. Bài thực hành A — Pipeline Java batch chạy DirectRunner

**Mục tiêu:** tính tổng doanh thu theo vùng từ dữ liệu mẫu, dùng **Create → ParDo → Sum.longsPerKey → TextIO**; kết quả là file CSV. Dữ liệu chỉ có số nguyên nên dùng **long**, không có sai số của double trong ví dụ. Đơn vị tiền là đồng minh họa.

### 7.1. Chuẩn bị Maven

Cần Java JDK tương thích với **Beam SDK version đã chọn**, Maven và một dự án Java riêng. **Không chạy lệnh này trong source module giáo trình**; đây là ví dụ học viên làm ở dự án lab.

Những dependency Maven cốt lõi, đặt trong pom.xml **của dự án lab**:

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

**Lưu ý:** placeholder phiên bản **không phải POM chạy ngay**. Phải thay bằng **một Beam release cụ thể đang được Dataflow hỗ trợ**, cấu hình compiler/exec plugin và xây dựng fat/uber JAR đúng cách. Dùng Beam Google Cloud BOM để tránh lệch phiên bản SDK và các thư viện gRPC/Google Cloud. **Không tự đoán version mới nhất** rồi triển khai production chưa kiểm thử.

### 7.2. Mã Java đầy đủ: BeamSalesBatch.java

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

Ví dụ giả định input:

~~~text
north,120
south,300
north,80
south,50
~~~

**Kết quả về mặt tập hợp, không cam kết thứ tự dòng:** **north,200** và **south,350**. TextIO có thể sinh các file có hậu tố shard như **revenue-00000-of-00001.csv**; chương trình không giả định chỉ có một file hoặc file order cố định.

### 7.3. Chạy local bằng DirectRunner

Sau khi cấu hình **exec-maven-plugin** trong dự án lab và tạo thư mục đầu ra:

~~~bash
mkdir -p out
mvn -q compile exec:java \
  -Dexec.mainClass=com.example.pipeline.BeamSalesBatch \
  "-Dexec.args=--runner=DirectRunner --outputPrefix=out/revenue"

# Xem nội dung shards sau khi job kết thúc.
cat out/revenue-*.csv
~~~

**DirectRunner** rất hữu ích để kiểm thử logic, nhưng không mô phỏng đầy đủ autoscaling, latency, IAM, Dataflow regional networking và failure behavior. **Create.of** chỉ dành cho sample lab; production batch thường dùng TextIO/AvroIO/BigQueryIO hoặc Storage/warehouse connectors.

### 7.4. Kiểm thử đơn vị bằng TestPipeline/PAssert

Trích đoạn JUnit test, dùng **beam-sdks-java-core**, **beam-runners-direct-java** và Beam test dependencies đúng phiên bản:

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

Đoạn **test fragment** cần imports JUnit, TestPipeline, PAssert, Create, ParDo, Sum, PCollection, KV trong dự án test và runner thích hợp; nó minh họa **kiểm tra không dựa vào thứ tự output**. Test thêm malformed inputs, empty source và overflow; trong production không nên để một input lỗi làm worker retry mãi.

## 8. Chạy cùng pipeline với DataflowRunner

**Mã Beam giống nhau**, nhưng runner sẽ được chỉ định qua options. Dataflow biến graph thành **Dataflow job**, tạo worker VMs/containers, quản lý shuffle, autoscaling, logging và cleanup khi batch hoàn tất.

### 8.1. Preflight GCP

Giả định project **shop-dev-001**, region **asia-southeast1**, bucket riêng **gs://shop-dev-001-dataflow-lab** đã tồn tại và được phê duyệt. Đảm bảo:

1. **Dataflow, Compute Engine, Cloud Storage, Cloud Logging** và APIs khác theo connector được bật.
2. Vùng của **Dataflow job, worker network, bucket staging/temp và source/sink** đáp ứng location/residency; staging/temp có quyền đọc/ghi.
3. **Submitter/CI** có quyền tạo/chạy jobs (Dataflow Developer/Admin tùy quy trình) và **iam.serviceAccounts.actAs** với worker SA.
4. **Worker service account** do tổ chức quản lý có **roles/dataflow.worker**, quyền ghi staging/temp và đúng quyền source/sink.
5. **Dataflow service agent** do Google quản lý được cấp roles cần để vận hành worker VMs; **không gỡ service-agent roles** để siết runtime tùy tiện.

| Danh tính | Nhiệm vụ | Quyền liên quan |
|---|---|---|
| **Submitter/CI** | Submit job, quản lý lifecycle | Dataflow Developer/Admin, Service Account User, staging access |
| **Dataflow service agent** | Dataflow quản lý worker, quota, resources | Service agent của project, Google-managed |
| **Worker service account** | Thực thi DoFns và I/O trên VMs | Dataflow Worker + GCS/PubSub/BigQuery IAM vừa đủ |

**Phân biệt:** SA của **orders-api trên Cloud Run** và worker SA của Dataflow **không mặc nhiên là cùng một principal**; khi job truy cập subscription hoặc BigQuery cần cấp quyền cho **worker SA thực tế**, không phải người submit.

### 8.2. Triển khai batch qua Maven/Java

Sau khi Maven project đã có entrypoint và dependencies phù hợp:

~~~bash
# Đây là ví dụ trong project lab, không chạy nếu bucket/SA chưa tạo hoặc chưa có quyền.
mvn -q compile exec:java \
  -Dexec.mainClass=com.example.pipeline.BeamSalesBatch \
  "-Dexec.args=--runner=DataflowRunner --project=shop-dev-001 --region=asia-southeast1 --stagingLocation=gs://shop-dev-001-dataflow-lab/staging --tempLocation=gs://shop-dev-001-dataflow-lab/temp --serviceAccount=dataflow-worker@shop-dev-001.iam.gserviceaccount.com --maxNumWorkers=3 --outputPrefix=gs://shop-dev-001-dataflow-lab/output/revenue"
~~~

Dataflow Java Runner **stages artifacts** vào Cloud Storage; đường đi từ launcher tới workers phải đóng gói dependencies/SDK đúng. Với một số Maven setup, gọi **exec:java** không tự tạo **uber JAR**; production thường dùng fat JAR, SDK container hoặc **Flex Template** đã kiểm thử.

**Bảng kiểm khi chạy:** Dataflow console → Jobs → chọn job region → kiểm tra **state RUNNING/DONE**, worker logs, graph, files CSV. **DONE không đồng nghĩa SUCCESS** nếu job có error. **Dataflow Runner** không tự tạo hoặc phân quyền bucket, Pub/Sub, BigQuery nếu thiếu.

### 8.3. Flex Templates: đóng gói để tái sử dụng

**Flex Template** gồm **container image** (ở Artifact Registry) và **JSON template spec** (ở Cloud Storage); bạn chạy cùng graph với các tham số environment. Phù hợp production CI/CD và recurring jobs:

~~~text
Source Java + tests
  → Maven package / Uber JAR
  → Artifact Registry image + template spec JSON
  → gcloud dataflow flex-template run (versioned parameters)
  → Dataflow job + runtime worker service account
~~~

Khác với source build, **template spec không chứa dữ liệu ứng dụng hoặc DB passwords**. Dùng Secret Manager/ADC và cấu hình IAM. Không dùng tag **latest** không kiểm soát cho production; pin image digest/version, lưu release metadata và cho rollback có chủ đích.

## 9. Bài thực hành B — Streaming Pub/Sub, window và triggers

**Mục tiêu:** tính doanh thu theo vùng trong mỗi **fixed window năm phút**, phát kết quả tạm thời và cập nhật khi có events trễ. Đây là **demo học tập**, output sang một Pub/Sub topic để dễ xem **panes**; không phải ledger tài chính vì Pub/Sub sink không bảo đảm exactly-once delivery.

Giả sử subscription đã tồn tại với tên **projects/shop-dev-001/subscriptions/sales-stream-sub**. Mỗi message có payload:

~~~text
north,120
south,300
north,80
~~~

### 9.1. Java streaming example: BeamSalesStreaming.java

Mã dùng **ParseSaleFn** của lớp **BeamSalesBatch** ở mục 7 (hai lớp trong cùng package Maven):

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

        pipeline.run(); // Streaming job tiếp tục chạy cho đến khi bị dừng.
    }
}
~~~

### 9.2. Những gì code này thực sự làm

1. **PubsubIO.readStrings()** lấy text messages; timestamp mặc định theo publish time của Pub/Sub, **chưa phải** business event time ở payload.
2. **ParseSaleFn** chuyển thành KV(region, amount); record lỗi làm stage thất bại và có thể bị retry — demo chưa có dead-letter.
3. **FixedWindows(5 phút)** chia theo timestamp được Beam gán; **AfterWatermark** phát on-time pane.
4. **Early firing** sau một phút xử lý kể từ event đầu của pane; **late firing** sau khi nhận late element.
5. **Allowed lateness 10 phút** cho phép cập nhật window trễ trong giới hạn; **accumulating** phát tổng đã tính lại.
6. **Pub/Sub output** chứa window start, region, tổng và pane timing; **một window có thể xuất hiện nhiều message**.

**Khi cần business event time:** producer gửi một attribute **event_ts** theo RFC 3339 UTC, rồi cấu hình **PubsubIO.readStrings().withTimestampAttribute("event_ts")** để dùng timestamp thuộc sự kiện. Phải xác minh mọi publisher đều ghi timestamp hợp lệ và điều kiện thời gian của Pub/Sub/Dataflow connector, nếu không windowing có thể sai hoặc message không được xử lý như mong đợi.

### 9.3. Tạo topic/subscription trong project lab

~~~bash
# Các lệnh này tạo tài nguyên/có thể phát sinh phí; chỉ chạy khi được phép.
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

**Tạo subscription trước khi publish** nếu muốn nhận đủ các message của lab từ đầu. Subscription là nơi chứa backlog riêng; nhiều subscribers trên cùng subscription **chia sẻ công việc**, không phải mỗi subscriber nhận bản sao của từng event.

### 9.4. Khởi chạy streaming trên Dataflow

Chạy Maven entrypoint trong source lab đã build; staging bucket và Dataflow worker SA cần được chuẩn bị và grant IAM như mục 8:

~~~bash
mvn -q compile exec:java \
  -Dexec.mainClass=com.example.pipeline.BeamSalesStreaming \
  "-Dexec.args=--runner=DataflowRunner --streaming=true --project=shop-dev-001 --region=asia-southeast1 --stagingLocation=gs://shop-dev-001-dataflow-lab/staging --tempLocation=gs://shop-dev-001-dataflow-lab/temp --serviceAccount=dataflow-worker@shop-dev-001.iam.gserviceaccount.com --inputSubscription=projects/shop-dev-001/subscriptions/sales-stream-sub --outputTopic=projects/shop-dev-001/topics/sales-totals"
~~~

Worker SA phải có **roles/pubsub.subscriber** tại input subscription và **roles/pubsub.publisher** tại output topic, ngoài Dataflow Worker và quyền bucket. **Không cấp Owner** cho worker để vượt qua lỗi IAM.

Khi job đã **RUNNING**, gửi messages mẫu:

~~~bash
gcloud pubsub topics publish sales-events \
  --project=shop-dev-001 --message="north,120"
gcloud pubsub topics publish sales-events \
  --project=shop-dev-001 --message="north,80"
gcloud pubsub topics publish sales-events \
  --project=shop-dev-001 --message="south,300"

# Đọc kết quả chỉ sau khi window/trigger đã phát.
gcloud pubsub subscriptions pull sales-totals-view \
  --project=shop-dev-001 --limit=10 --auto-ack
~~~

Kết quả có thể gồm **early pane** và **on-time pane**; không cam kết ba events rơi vào cùng window nếu publish sát ranh giới 5 phút. **Không bật --auto-ack trên subscription production** chỉ để quan sát nếu có nguy cơ mất message chưa xử lý.

**Chú ý về phép cộng tiền:** streaming example dùng long cho số tiền nguyên, nhưng hệ thống tài chính thật cần idempotency, currency, overflow validation, reconciliation và một sink có semantics cập nhật bền vững. Đừng xem kết quả Pub/Sub panes là một sổ cái.

## 10. Tích hợp BigQuery: chọn sink theo semantics dữ liệu

Trong kiến trúc production, thay output Pub/Sub bằng **BigQueryIO** hoặc tạo bảng sự kiện thô rồi tổng hợp bằng BigQuery:

~~~mermaid
flowchart LR
  API["Cloud Run orders-api"] --> PUB["Pub/Sub topic"]
  PUB --> BEAM["Beam / Dataflow"]
  BEAM --> VAL{"Record hợp lệ?"}
  VAL -->|Có| BQ["BigQuery raw events / aggregates"]
  VAL -->|Không| DLQ["Dead-letter Pub/Sub / GCS"]
  BQ --> BI["Looker / BI"]
~~~

| Kiểu output | Thiết kế đề xuất | Lưu ý |
|---|---|---|
| **Raw immutable events** | Append vào BigQuery qua **BigQueryIO Storage Write API** | Chọn at-least/exactly-once write method theo nghiệp vụ; dedup bằng eventId |
| **Window totals nhiều panes** | Ghi **window_start, region, pane_version, total**, rồi chọn bản mới nhất hoặc **MERGE** idempotent | Append mọi accumulating pane rồi SUM sẽ bị đếm trùng |
| **Batch aggregate cuối ngày** | Ghi BigQuery destination partition theo ngày hoặc GCS Parquet | Kiểm tra mode ghi/overwrite partition |
| **Invalid events** | Dead-letter topic hoặc GCS với error reason và event ID đã mask | Không retry vô hạn dữ liệu sai; bảo vệ PII |

Đối với dòng có nhiều panes, lưu **timestamp/window/key và phiên bản cập nhật** để BI lấy snapshot cuối hợp lệ; có thể cần tách **raw immutable facts** khỏi bảng **materialized aggregates**. **BigQueryIO tự thân không biến external side effects trong DoFn thành exactly-once**.

## 11. Exactly-once trong pipeline khác exactly-once của nghiệp vụ

Google Cloud Dataflow hiện hỗ trợ hai **streaming modes**:

| Mode | Bảo đảm trong Dataflow | Khi chọn |
|---|---|---|
| **Exactly-once (mặc định)** | Kết quả **được commit** của record không bị phản ánh lặp trong pipeline theo phạm vi bảo đảm | Đếm/tổng hợp chính xác, nghiệp vụ nhạy cảm |
| **At-least-once** | Record không bị bỏ sót nhưng có thể phản ánh lặp | ETL/map-only, có dedup downstream, tối ưu độ trễ/chi phí |

Với Java, để chọn **at-least-once mode** trên Dataflow:

~~~text
--dataflowServiceOptions=streaming_mode_at_least_once
~~~

At-least-once mode yêu cầu **Streaming Engine với resource-based billing**; chọn write method tương thích (ví dụ **BigQueryIO STORAGE_API_AT_LEAST_ONCE** khi đẩy BigQuery). Mode này **không tương thích BigQueryIO FILE_LOADS** trong pipeline streaming. Để đổi streaming mode của một job đã chạy cần **replacement job**, không giả định sửa live bằng biến môi trường.

### 11.1. Vì sao exactly-once không bảo đảm side effect một lần?

Một **DoFn có thể chạy lại** sau worker failure dù Dataflow chỉ commit output đã checkpoint một lần. Nếu DoFn gọi trực tiếp một HTTP payment endpoint hoặc gửi email, side effect có thể chạy **hai lần**:

~~~text
ProcessElement(eventId=E1)
  → gọi Payment API: thành công
  → worker chết trước khi checkpoint output
  → retry ProcessElement(E1)
  → gọi Payment API lần nữa
~~~

**Đúng cách:** dùng **eventId/idempotency key**, ghi trạng thái có điều kiện trong database, pattern outbox hoặc connector/sink có semantics phù hợp. **Không thực hiện side effect không idempotent** trong DoFn rồi mặc định Dataflow bảo vệ bên ngoài pipeline.

### 11.2. Dedup ở lớp Pub/Sub

- Pub/Sub có thể **redeliver** cùng message; Dataflow exactly-once có dedup cho những lần redelivery theo message ID.
- Nếu producer **publish cùng business event hai lần** thành hai Pub/Sub message IDs khác nhau, Dataflow **không tự biết** đó là một giao dịch lặp.
- Với Dataflow Pub/Sub connector có thể dùng **withIdAttribute** để dedup theo business ID attribute được publisher đặt nhất quán, nhưng có giới hạn (tài liệu nêu cửa sổ **10 phút**) và cần phối hợp với các sinks/retention.
- **Không khuyến nghị bật Pub/Sub exactly-once delivery cho Dataflow** chỉ để nhân đôi bảo đảm, vì Dataflow đã có cơ chế riêng và có thể giảm throughput.
- Pub/Sub **output sink không bảo đảm exactly-once delivery**; downstream consumers vẫn phải idempotent.

### 11.3. Exactly-once không đồng nghĩa kết quả đã đầy đủ

Watermark có thể đi qua khi event thực tế chưa tới. Dataflow có thể tính đúng tổng **những records nhận trong allowed lateness**, nhưng vẫn thiếu events tới muộn hơn ngưỡng. Cần một chiến lược **late-data SLA**, reconcile batch/backfill và chỉ đánh dấu báo cáo “final” theo điều kiện nghiệp vụ. **Late panes, duplicates, idempotency và output consistency** là bốn vấn đề khác nhau.

## 12. IAM, mạng, deployment và bảo vệ dữ liệu

### 12.1. IAM theo vai trò thực tế

| Principal | Quyền hợp lý | Rủi ro nếu cấp sai |
|---|---|---|
| **CI submitter** | Dataflow Developer/Admin theo nhiệm vụ; **iam.serviceAccounts.actAs** worker SA | Không submit được job hoặc được quyền quá rộng |
| **Dataflow service agent** | Service Agent managed role để tạo/quản lý VMs | Gỡ quyền làm job không chạy |
| **Dataflow worker SA** | Dataflow Worker, đọc input GCS/PubSub, ghi sink BigQuery/PubSub và staging/temp | Runtime 403, hoặc lộ toàn project nếu cấp Owner |
| **Data analyst/BI** | Quyền xem dataset/table và truy vấn | Không cần Dataflow Worker role |
| **Security/KMS operator** | Quản lý keys và audit theo chính sách | Không tự cấp quyền đọc payload |

Một ví dụ tách phạm vi:

- **roles/pubsub.subscriber** trên input subscription, **roles/pubsub.publisher** trên output topic.
- **roles/storage.objectViewer** trên input bucket; quyền tạo/sửa object cần thiết trên **staging/temp/output buckets**, đúng phạm vi.
- **roles/bigquery.dataEditor** trên sink dataset/table theo nhu cầu ghi; quyền tạo BigQuery jobs nếu connector/mô hình ghi yêu cầu.
- **roles/dataflow.worker** cho worker service account tại project chạy job.

**Không cấp Dataflow Admin, Pub/Sub Editor và BigQuery Admin cho mọi workers** để tránh từng lỗi 403. Dataflow service agent có dạng **service-PROJECT_NUMBER@dataflow-service-producer-prod.iam.gserviceaccount.com**, khác worker SA **dataflow-worker@...** của người dùng.

### 12.2. VPC và regional locality

Dataflow Runner thực thi trên tài nguyên ở **region** đã chỉ định; cần kiểm tra:

1. **Dataflow worker region** gần Pub/Sub/BigQuery/bucket và đúng residency.
2. **Cloud Storage staging/temp buckets** được cấu hình location phù hợp; dữ liệu tạm có thể có thông tin nhạy cảm.
3. Với **private workers / --usePublicIps=false**, VPC/subnet, Private Google Access, DNS, Cloud NAT hoặc private API access theo kiến trúc phải cho phép workers gọi Google APIs và lấy dependencies.
4. Nếu truy cập Cloud SQL private IP/on-premise, cần VPC routing/VPN/Interconnect, firewall và cơ chế xác thực database riêng.
5. Nếu dùng **customer-managed encryption keys (CMEK)**, cấu hình Dataflow KMS key theo tính năng và location được hỗ trợ; cấp KMS IAM cho service agents/principals phù hợp, không dùng CMEK thay IAM nguồn/đích.

**Không có bảo đảm** Dataflow chạy trong region A thì một BigQuery dataset ở region B tự được join hoặc ghi mà không có ràng buộc location. Kiểm tra resource location của **từng sink**.

### 12.3. Không đưa secrets vào pipeline options

Arguments, job configuration, logs và template metadata có thể được nhìn thấy bởi người có quyền. Không truyền **DB password, API token, customer PII** trực tiếp qua dòng lệnh **--password=...**. Dùng **Secret Manager**, Workload Identity/ADC, IAM và mask logs. **Không log từng message payload** trong production để tránh chi phí, latency và nguy cơ dữ liệu cá nhân.

## 13. Vận hành: job lifecycle, giám sát và kiểm soát chi phí

### 13.1. Theo dõi job đúng chỉ số

| Chỉ số | Khi nào bất thường | Điều tra |
|---|---|---|
| **Job state/failed work items** | FAILED hoặc retry kéo dài | Worker logs, exception, DoFn lỗi |
| **Elements processed per stage** | Input có data nhưng output không tiến | Stage graph, filter, DLQ, sink permissions |
| **Pub/Sub backlog bytes / oldest unacked age** | Tăng liên tục | Worker capacity, IO throttling, hot keys |
| **Data freshness** | Event time tới output ngày càng trễ | Watermark, late data, source backlog |
| **System latency** | Elements xử lý hoặc chờ xử lý rất lâu | Hot key, slow side effect, sink I/O |
| **Watermark progress** | Bị giữ ở mốc cũ | Stuck elements, retries, input timestamp |
| **Worker CPU/memory/restarts** | CPU cao, OOM, repeated restarts | Machine type, parsing memory, hot keys |
| **Autoscaling worker count** | Chạm max workers nhưng backlog vẫn tăng | Quota/capacity, maxNumWorkers, stage bottleneck |
| **Sink errors/quota** | BigQuery rate limit hoặc Pub/Sub errors | IAM, Write API quotas, retry/backoff |
| **Dead-letter count** | Tăng sau một release | Input schema drift, validation và upstream data |

**Quy tắc chẩn đoán:** nếu **data freshness và backlog bytes cùng tăng**, pipeline có thể không theo kịp hoặc bị kẹt. Nếu freshness tăng nhưng backlog bình thường, có thể một vài elements bị treo ở các stages. Cần xem stage metrics và logs, không mặc định tăng worker count.

### 13.2. Thao tác với job đang chạy

| Thao tác | Tác dụng | Dùng khi |
|---|---|---|
| **Cancel** | Dừng job, có thể bỏ phần dữ liệu còn buffered | Job thử nghiệm sai, sự cố cần dừng ngay |
| **Drain** | Ngừng nhận dữ liệu mới, cố gắng xử lý dữ liệu đang buffered trước khi dừng | Kết thúc streaming job có kiểm soát |
| **Update/replacement** | Thay streaming job bằng phiên bản mới theo các giới hạn tương thích | Release code/graph mới |
| **Batch rerun** | Chạy batch job mới trên dữ liệu nguồn | Backfill, xử lý lỗi sau sửa code |

**Drain không phải rollback dữ liệu đã ghi**; **cancel** có thể tạo khoảng trống nghiệp vụ nếu không có chiến lược replay. Cập nhật streaming graph có state/timers/windows cần đánh giá **compatibility và checkpoint behavior**; không coi mọi update là zero-downtime.

### 13.3. Những khoản chi phí cần đo

| Thành phần | Mô hình phát sinh |
|---|---|
| **Worker VMs CPU/memory** | Machine type, số worker, thời gian chạy |
| **Batch/Streaming shuffle, Streaming Engine** | Tài nguyên dịch vụ managed theo pricing model và lượng xử lý |
| **Dataflow Prime** | DCUs/resource-based billing khi bật tính năng phù hợp |
| **Cloud Storage staging/temp/output** | Lưu, operations, dữ liệu tạm và retention |
| **Pub/Sub/BigQuery** | Delivery, throughput, Storage Write API, queries/storage |
| **Network** | Chuyển liên vùng/egress, kết nối tới backend |
| **Cloud Logging/Monitoring** | Log volume/retention/alerts theo tính phí hiện hành |

**Exactly-once streaming** có thêm công việc checkpoint/dedup; **at-least-once** có thể tiết kiệm tài nguyên cho map-only ETL nếu downstream chấp nhận duplicate. Dataflow **Streaming Engine** thường được khuyến nghị cho streaming; resource-based billing dùng **Streaming Engine Compute Units** khi chọn chế độ đó, trong khi Dataflow Prime có mô hình **Data Compute Units (DCUs)** riêng. Không áp một mức giá cho mọi job hoặc giả định Cloud Run/BigQuery đã bao gồm phí Dataflow.

**Giảm chi phí có cơ sở:** chọn batch nếu SLO cho phép; giới hạn maxNumWorkers theo benchmark; dùng máy phù hợp; tránh logging từng event; phân vùng/giảm dữ liệu sớm, tránh hot keys; đặt lifecycle cho GCS staging/temp. Cân nhắc **FlexRS** cho batch chịu trì hoãn và **commitments** khi workload ổn định theo chính sách, không dùng cho mọi bài lab.

**Dataflow console Cost tab cung cấp ước tính**, không phải hóa đơn cuối. Đối chiếu **Cloud Billing reports** sau job; ngân sách/alerts không tự dừng job.

## 14. Troubleshooting theo lớp của Beam và Dataflow

| Triệu chứng | Nguồn lỗi khả dĩ | Kiểm tra |
|---|---|---|
| Local DirectRunner hoạt động, DataflowRunner thất bại ngay | SDK/container dependency, service account, staging bucket | Build logs, job submission logs, permissions |
| Job tạo rồi stuck ở PENDING | Region/quota, workers không tạo được, networking | Dataflow jobs, Compute Engine quotas, service agent |
| **PERMISSION_DENIED** khi đọc subscription | Worker SA thiếu Pub/Sub Subscriber hoặc sai project | Subscription IAM, job worker identity |
| **PERMISSION_DENIED** khi ghi BigQuery | Worker SA/BigQuery sink permissions | Table/dataset IAM, BigQuery API/quota |
| **STORAGE_PERMISSION_DENIED** trên GCS | Staging/temp bucket permission sai | Bucket IAM, region, object path |
| Parse NumberFormatException lặp lại | Input lỗi nhưng transform fail toàn bundle | Side output DLQ, schema validation, retry handling |
| Streaming job không có output | Trigger chưa phát, watermark chưa qua end window | Watermark, panes, event timestamps |
| Dataflow output có nhiều records cùng window/key | Early/on-time/late accumulating panes hoặc Pub/Sub sink duplicate | Pane timing, idempotent upsert, eventId |
| “Exactly-once” nhưng payment API bị gọi hai lần | DoFn side effect được retry | Idempotency key, outbox, tránh external side effects |
| Backlog tăng khi CPU thấp | Sink throttling, blocked RPC, hot key | Stage latency, pending work, external quotas |
| CPU cao ở một stage | Key skew, quá nhiều serialization hoặc expensive UDF | Hot key metrics, Combine/fanout, coder |
| Output thiếu event tới quá trễ | Allowed lateness/window đã đóng | Timestamp policy, late-event DLQ, batch reconciliation |
| Kết quả sai dù worker không lỗi | Sai event time, trigger accumulation hoặc dữ liệu nguồn lặp | Event timestamp, pane semantics, dedup ID |
| OOM worker | DoFn giữ toàn bộ nhóm, large side input, memory leak | Heap, grouping design, worker machine type |
| Batch chạy xong nhưng không thấy file | TextIO có sharded output, path prefix sai | GCS bucket/path, job state, output shards |
| Cancel xong vẫn có event chưa xử lý | Buffered data chưa drained, sink in-flight | Pub/Sub backlog, source offset/replay, sink checks |

### 14.1. Quy trình điều tra nhanh

1. **Xác nhận project/region/job ID** và trạng thái, đừng xem nhầm local/DirectRunner job.
2. **Theo stage:** xem input elements, failed elements, watermark, system latency, backlog bytes.
3. **Theo principal:** xác minh **Dataflow worker SA**, Pub/Sub/BigQuery/GCS IAM và VPC path.
4. **Theo data semantics:** timestamp, window, trigger, pane, DLQ, duplicate eventId và sink mode.
5. **Theo capacity:** autoscaling, CPU/memory, hot keys và external rate limits.
6. **Sau sửa:** chạy replay/backfill trên tập dữ liệu đã biết; so output với oracle, không chỉ xem job chuyển RUNNING.

Không “sửa” mọi lỗi bằng cách cấp Owner, tăng max workers hoặc chuyển sang at-least-once. Có thể tăng phí, làm mất tính đúng đắn hoặc che khuất lỗi dữ liệu gốc.

## 15. Tình huống tổng hợp: doanh thu đơn hàng theo sự kiện

Doanh nghiệp **Sông Xanh** cần dashboard doanh thu cập nhật gần real-time, dữ liệu lịch sử có thể nạp lại khi có lỗi. Đội đang vận hành:

- **Cloud Run Java orders-api** ghi giao dịch vào Cloud SQL, phát event đã xác nhận.
- **Pub/Sub topic orders-events** chứa các events bất đồng bộ.
- **Dataflow streaming** chuẩn hóa events và tính doanh thu 5 phút.
- **BigQuery** lưu raw events và bảng tổng hợp cho Looker.
- **Cloud Storage** chứa exports để backfill, có kiểm soát IAM/retention.

### 15.1. Kiến trúc được đề xuất

~~~mermaid
flowchart LR
  API["Cloud Run Java"] --> SQL["Cloud SQL orders"]
  API --> PUB["Pub/Sub orders-events"]
  PUB --> DF["Beam → Dataflow"]
  DF --> VAL{"Validate schema / eventId"}
  VAL -->|"Hợp lệ"| RAW["BigQuery raw_events"]
  VAL -->|"Không hợp lệ"| DLQ["Pub/Sub dead-letter + alert"]
  RAW --> AGG["Beam windows hoặc BigQuery SQL"]
  AGG --> BQ["BigQuery 5-min aggregates"]
  BQ --> BI["Looker dashboard"]
  GCS["Cloud Storage exports"] --> BACK["Batch Beam backfill"]
  BACK --> RAW
~~~

**Lưu ý thiết kế:** nếu Java orders-api cập nhật Cloud SQL rồi publish Pub/Sub bằng hai lệnh riêng, có thể gặp **dual-write failure**: DB commit thành công nhưng publish thất bại. Cân nhắc **transactional outbox**/CDC theo hệ quản trị để tránh bỏ sót sự kiện; Dataflow exactly-once không sửa được dữ liệu chưa bao giờ được publish.

### 15.2. Quyết định nghiệp vụ và thiết kế Beam

| Vấn đề | Quyết định đề xuất |
|---|---|
| **Sự kiện nguồn** | Có eventId duy nhất, orderId, UTC event time, schema version, amount theo đơn vị nguyên |
| **Tính đúng đắn** | Dataflow exactly-once khi cần aggregation chính xác; sink hỗ trợ idempotency |
| **Duplicate publish** | Dựa eventId, không chỉ Pub/Sub message ID; có reconciliation |
| **Event tới muộn** | Fixed window 5 phút, early preview và late update trong SLA, backfill ngoài ngưỡng |
| **Invalid event** | Side output DLQ và alert, không log PII/full payload |
| **BI kết quả** | BigQuery keyed by window_start + region, đọc latest snapshot/changelog đúng semantics |
| **Scale** | Combine.perKey, xem hot keys, cấu hình autoscaling theo backlog/freshness |
| **Vận hành** | Worker SA tối thiểu, staging/temp cùng region theo policy, dashboards + Cloud Billing |

### 15.3. Thử nghiệm dữ liệu và cửa sổ

Giả sử các event đều có **event time**:

| Event | Time | Region | Amount | Đến pipeline |
|---|---|---|---:|---|
| E1 | 10:01 | north | 120 | 10:01 |
| E2 | 10:03 | north | 80 | 10:03 |
| E3 | 10:04 | south | 300 | 10:04 |
| E4 | 10:02 | north | 50 | 10:07 (late so với cuối window) |

Các events trên thuộc **[10:00,10:05)** theo event time. Khi E4 còn nằm trong allowed lateness và trigger phù hợp, tổng đúng của north là **250**, south là **300**. Nếu dashboard từng nhận pane north=200 rồi nhận pane tích lũy north=250, nó phải **thay 200 bằng 250**, không cộng thành 450.

**Phải kiểm tra watermark thực tế**: E4 tới lúc 10:07 không nhất thiết là late theo Beam nếu watermark chưa vượt 10:05. Không suy late dựa duy nhất vào đồng hồ hệ thống.

### 15.4. Kịch bản kiểm thử trước release

| Test | Kỳ vọng |
|---|---|
| Batch cùng 4 records, không lỗi | north=250, south=300 |
| Streaming với late record nằm trong hạn | Window output được cập nhật đúng |
| Record đến quá allowed lateness | Có chính sách drop/DLQ/reconcile rõ |
| Gửi E2 hai lần cùng eventId | Số tiền không tăng gấp đôi sau dedup |
| Dataflow worker bị restart | Pipeline phục hồi, external side effects không lặp do idempotency |
| Một event sai schema | Đi DLQ, job không đứng mãi |
| Pub/Sub backlog tăng | Alert data freshness/system latency phát hiện |
| BigQuery sink chặn IAM | Job logs báo lỗi, worker SA được sửa quyền đúng phạm vi |
| Thay code window/trigger | Update/backfill plan bảo vệ state và downstream |
| Tắt streaming theo lịch | Drain/replay plan, kiểm tra dữ liệu buffered |

## 16. Bài tập và đáp án gợi ý

### Bài tập A — Beam hay Dataflow?

**Câu hỏi:** Chương trình khai báo ParDo, Window, Combine rồi chạy bằng DirectRunner. Có đang dùng Dataflow service không?

**Đáp án:** Không. Chương trình **dùng Apache Beam**, DirectRunner thực thi local. Chỉ khi chọn **DataflowRunner** và submit job hợp lệ vào GCP mới chạy trên Dataflow.

### Bài tập B — Phân biệt bounded/unbounded

**Dữ liệu:** một file CSV đóng băng cuối ngày và một Pub/Sub subscription có events liên tục.

**Đáp án:** File CSV là **bounded**, có thể xử lý batch; Pub/Sub subscription là **unbounded**, cần streaming hoặc cách đặt giới hạn đọc rõ. Windowing và triggering cần được thiết kế nếu grouping unbounded.

### Bài tập C — Tính tổng từ graph

Input: north,120; south,300; north,80; south,50. Sử dụng Parse → KV(region, amount) → Sum.longsPerKey.

**Đáp án:** **north=200, south=350**. Thứ tự output không được bảo đảm bởi Beam.

### Bài tập D — Event time và processing time

Event có event time **10:02** nhưng đến pipeline lúc **10:07**, window cố định 5 phút.

**Đáp án:** Theo event time, thuộc **[10:00,10:05)**. Theo processing time thuộc **[10:05,10:10)**. Việc có được tính vào event-time window hay không còn tùy **watermark, allowed lateness và trigger**.

### Bài tập E — Accumulating panes

Window của north phát tổng **100**, rồi **150**, rồi **160** ở ba panes accumulating. BI cộng cả ba thành 410.

**Đáp án:** Sai. Đây là **ba snapshots cùng một window**; tổng mới nhất là **160**. Sink cần upsert/latest-pane selection, không cộng ba snapshots.

### Bài tập F — DoFn và exactly-once

Một DoFn gọi API thanh toán, worker restart sau khi API trả 200 nhưng trước khi checkpoint, callback chạy lại.

**Đáp án:** Dataflow exactly-once **không đảm bảo external side effect chỉ xảy ra một lần**. Dùng idempotency key/transactional outbox/đưa side effect ra ngoài retry callback theo thiết kế.

### Bài tập G — At-least-once mode

Pipeline chỉ làm parse/rename fields, sink BigQuery có cơ chế dedup theo eventId. Có nên cân nhắc at-least-once?

**Đáp án:** Có thể **thử nghiệm** vì map-only và downstream chịu duplicate, có thể giảm latency/cost. Cần kiểm tra Write API method tương thích, metric duplicates và accuracy; không bật khi phép tổng hợp yêu cầu exactly-once mà chưa có cơ chế chống lặp.

### Bài tập H — Hot key và tăng workers

80% events có region=unknown, một stage chậm dù maxNumWorkers đã tăng gấp đôi.

**Đáp án:** Có **data skew/hot key**; chỉ tăng workers có thể không giúp. Xem stage metrics, key distribution, Combine/fanout, data validation và thiết kế key/window.

### Bài tập I — IAM trên worker

Người submit có BigQuery Editor nhưng Dataflow báo 403 khi worker ghi sink.

**Đáp án:** Worker dùng **worker service account riêng**, không thừa hưởng IAM của submitter. Cấp quyền ghi BigQuery tại đúng dataset/table cho worker SA; xác minh Dataflow Worker role và staging access.

### Bài tập J — Drain và cancel

Job streaming còn 50.000 events buffered, đội muốn thay revision mà không bỏ dữ liệu.

**Đáp án:** Lập kế hoạch **drain** để ngừng ingest và xử lý buffered work khi phù hợp, hoặc dùng **replacement update** nếu graph/state tương thích. **Cancel** có thể làm mất phần việc chưa xử lý trong pipeline; cần replay/backfill từ source, kiểm tra sink. Không có phép “undo” những writes đã xảy ra.

### Bài tập K — Tính freshness

Event time 10:00, dashboard có kết quả lúc 10:04. Giả sử thời gian gán timestamp và clocks đều chính xác.

**Đáp án:** Data freshness/độ trễ end-to-end của event này là **4 phút**. Trong thực tế phải xem **watermark, source backlog và stage system latency** chứ không đo duy nhất một event để đánh giá SLO toàn pipeline.

### Bài tập L — Chọn batch hay streaming

Kho dữ liệu cần báo cáo mỗi sáng, tối đa trễ 6 giờ; doanh nghiệp muốn giảm chi phí và không có alert real-time.

**Đáp án:** Ưu tiên **batch job định kỳ** từ GCS/BigQuery nếu đảm bảo deadline và tính đúng đắn. Chạy streaming 24/7 chỉ vì có Pub/Sub nguồn không nhất thiết là phương án tối ưu.

## 17. Tổng kết và tài liệu tham khảo

**Sáu nguyên tắc cần nhớ:**

1. **Apache Beam định nghĩa graph; runner thực thi graph.** DataflowRunner dùng managed Dataflow workers; DirectRunner phục vụ local/test.
2. **PCollection là dữ liệu phân tán**, PTransform là phép biến đổi; dùng ParDo/DoFn, KV, Combine, I/O connectors và coders theo mục tiêu.
3. **Batch là bounded, streaming là unbounded.** Với unbounded aggregation, event time, windows, watermarks, triggers và allowed lateness quyết định độ trễ và độ đầy đủ.
4. **Dataflow exactly-once là bảo đảm commit trong pipeline**, không bao phủ mọi side effect ngoài hệ thống; input duplicate và sink delivery cần idempotency riêng.
5. **Worker identity khác submitter và service agent.** IAM, staging/temp, VPC và location phải kiểm soát cả nguồn lẫn đích.
6. **Tính đúng đắn trước, tối ưu sau:** test với data tới trễ/duplicate/hot key; theo dõi backlog/freshness/latency/cost rồi chọn autoscaling và streaming mode phù hợp.

**Tài liệu chính thức:**

1. [Apache Beam Programming Guide](https://beam.apache.org/documentation/programming-guide/) — PCollections, transforms, windowing, triggers và state.
2. [Apache Beam Java SDK dependencies](https://beam.apache.org/documentation/sdks/java-dependencies/) — BOM, dependencies, dependency pinning.
3. [Dataflow Beam programming model](https://docs.cloud.google.com/dataflow/docs/concepts/beam-programming-model) — Beam abstractions và runner.
4. [Dataflow Runner options](https://beam.apache.org/documentation/runners/dataflow/) — project, region, streaming, staging/temp.
5. [Deploy Dataflow pipelines](https://docs.cloud.google.com/dataflow/docs/guides/deploying-a-pipeline) — Dataflow jobs lifecycle.
6. [Beam windowing/watermarks trên Dataflow](https://docs.cloud.google.com/dataflow/docs/concepts/streaming-pipelines) — time, trigger, lateness.
7. [Read Pub/Sub with Dataflow](https://docs.cloud.google.com/dataflow/docs/concepts/streaming-with-cloud-pubsub) — timestamp, dedup và ack.
8. [Exactly-once in Dataflow](https://docs.cloud.google.com/dataflow/docs/concepts/exactly-once) — hạn chế external side effects.
9. [Set streaming mode](https://docs.cloud.google.com/dataflow/docs/guides/streaming-modes) — exactly-once/at-least-once.
10. [Write to Pub/Sub](https://docs.cloud.google.com/dataflow/docs/guides/write-to-pubsub) — delivery guarantees của sink.
11. [Dataflow security and permissions](https://docs.cloud.google.com/dataflow/docs/concepts/security-and-permissions) — service agents/worker IAM.
12. [Build Flex Templates](https://docs.cloud.google.com/dataflow/docs/guides/templates/configuring-flex-templates) — container, template spec.
13. [Dataflow job metrics](https://docs.cloud.google.com/dataflow/docs/guides/using-monitoring-intf) — freshness, system latency, backlog.
14. [Troubleshoot slow streaming jobs](https://docs.cloud.google.com/dataflow/docs/guides/troubleshoot-slow-streaming-jobs) — stage bottlenecks.
15. [Stop Dataflow jobs](https://docs.cloud.google.com/dataflow/docs/guides/stopping-a-pipeline) — cancel, drain, force-cancel.
16. [Optimize Dataflow costs](https://docs.cloud.google.com/dataflow/docs/optimize-costs) — workers, Streaming Engine, pricing model.
17. [Streaming Engine](https://docs.cloud.google.com/dataflow/docs/streaming-engine) — compute/storage split, resource-based billing.
