# Serverless for Apache Spark và chạy Spark theo nhu cầu

Một nền tảng đào tạo thu thập sự kiện ghi danh qua Pub/Sub, lưu dữ liệu thô vào Cloud Storage, rồi mỗi đêm tổng hợp số học viên theo khóa học để phân tích trong BigQuery. Đội dữ liệu đã có mã PySpark nhưng không muốn duy trì một cụm máy 24/7 chỉ để chạy vài giờ mỗi ngày. **Serverless for Apache Spark** giải quyết phần vận hành hạ tầng cho workload Spark theo nhu cầu: gửi job, dịch vụ cấp phát driver/executors, tự mở rộng theo tải và kết thúc tài nguyên tính toán khi batch hoàn tất.

Trên tài liệu Google Cloud hiện hành, sản phẩm này có tên **Managed Service for Apache Spark serverless** (trước đây thường gọi **Dataproc Serverless for Apache Spark**). Các API và lệnh `gcloud dataproc batches ...` vẫn được sử dụng. Bài nằm trong chương **Pipeline và xử lý dữ liệu** thuộc module **CLOUD_PROVIDERS_GCP**: kết nối IAM, VPC, Cloud Storage, BigQuery, Cloud Run/GKE và Cloud Monitoring để triển khai xử lý dữ liệu theo nhu cầu, bảo mật và có kiểm soát chi phí.

**Sau bài học, bạn có thể:**

1. Phân biệt serverless **batch**, **interactive session**, Spark cluster và những trường hợp không cần Spark.
2. Đọc kiến trúc driver/executors, submit một PySpark batch qua gcloud và theo dõi trạng thái.
3. Chọn runtime version, danh tính thực thi, network và quyền trên dữ liệu theo mô hình quyền tối thiểu.
4. Điều chỉnh dynamic allocation, memory, shuffle, partitioning và số batch chạy đồng thời dựa trên số liệu.
5. Thiết kế pipeline idempotent, lịch chạy, retry, kiểm tra dữ liệu và giám sát chi phí/độ tin cậy.
6. Hoàn thành lab giới hạn dữ liệu và bài tập thiết kế production.

## 1. Chọn đúng hình thức chạy Spark

Apache Spark là engine xử lý dữ liệu phân tán: chương trình có **driver** điều phối công việc thành stages/tasks, còn **executors** xử lý dữ liệu song song. Spark không phải một database; input/output thường nằm ở Cloud Storage, BigQuery hoặc hệ thống khác.

~~~mermaid
flowchart LR
    O["Cloud Scheduler / Airflow<br/>hoặc người vận hành"] --> API["Dataproc Batches API"]
    API --> DRIVER["Spark driver<br/>managed compute"]
    DRIVER --> E1["Executor 1"]
    DRIVER --> E2["Executor 2 ... N"]
    GCS["Cloud Storage<br/>raw input"] --> E1
    GCS --> E2
    E1 --> OUT["Cloud Storage Parquet<br/>hoặc BigQuery"]
    E2 --> OUT
    DRIVER -. "Logs, Spark UI, metrics" .-> OBS["Cloud Logging / Monitoring"]
~~~

Serverless **không yêu cầu tự tạo một cụm Dataproc**; hạ tầng tính toán phục vụ batch do Google Cloud quản lý. Tuy nhiên mã Spark, schema, dependency, quyền dữ liệu, networking, chất lượng kết quả và lịch chạy **vẫn do đội ứng dụng chịu trách nhiệm**.

### 1.1. Các phương án

| Phương án | Phù hợp khi | Cần cân nhắc |
| --- | --- | --- |
| **Serverless batch** | ETL theo giờ/ngày, backfill định kỳ, xử lý PySpark/Spark SQL/Java-Scala/R rồi kết thúc | Thời gian khởi tạo, quota/concurrency, chi phí lúc job chạy |
| **Serverless interactive session** | Notebook/Jupyter khám phá dữ liệu, thử Spark code và feature engineering | Session còn sống tiêu thụ tài nguyên; kiểm soát thời gian chờ và thông tin nhạy cảm |
| **Spark cluster do quản lý** | Cần cấu hình component/daemon đặc thù, môi trường lâu dài hoặc khối lượng chạy liên tục | Phải vận hành cluster, autoscaling, patching và công cụ đi kèm |
| **BigQuery SQL** | Tổng hợp/biến đổi dữ liệu quan hệ có thể diễn tả bằng SQL thuần | Không nên dùng Spark cho mỗi phép `GROUP BY` nhỏ nếu BigQuery đáp ứng đơn giản hơn |
| **Dataflow (Apache Beam)** | Pipeline batch/streaming cần semantics xử lý sự kiện, window và event-time | Mô hình lập trình khác Spark; đánh giá nhu cầu thật |
| **Cloud Run Jobs** | Xử lý batch nhẹ, độc lập, ít cần distributed shuffle | Không cung cấp engine Spark phân tán mặc định |

**Không phải cứ có dữ liệu lớn là bắt buộc cần Spark.** Nếu logic chỉ là một vài câu SQL và dữ liệu đã ở BigQuery, hãy benchmark BigQuery trước. Nếu cần chạy mã Spark/PySpark sẵn có, join dữ liệu lớn từ file, feature engineering hay Spark MLlib, serverless Spark là ứng viên tự nhiên.

### 1.2. Batch khác streaming

Một **batch** có đầu vào hữu hạn và kết thúc sau khi xử lý xong. Managed Service for Apache Spark cũng có thể chạy **Spark Structured Streaming**, nhưng **không quản lý tự động việc restart/checkpoint của ứng dụng streaming** như một managed streaming service hoàn chỉnh. Muốn chạy liên tục phải thiết kế checkpoint storage, recovery, retry, supervision và xử lý sự cố; không giả định batch tự chạy lại vô hạn sau crash.

## 2. Vòng đời batch và những điều cần hiểu

~~~mermaid
flowchart LR
    A["SUBMIT"] --> B["PENDING / SETUP"]
    B --> C["RUNNING"]
    C --> D{"Kết quả?"}
    D -->|Thành công| E["SUCCEEDED"]
    D -->|Lỗi| F["FAILED"]
    C -->|Hủy/timeout| G["CANCELLED"]
    E --> H["Kiểm tra output<br/>và kích hoạt bước tiếp"]
~~~

Đây là **sơ đồ trạng thái khái niệm**; API có thể trả các trạng thái trung gian chi tiết như `PENDING`, `SETUP_DONE`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLING` và `CANCELLED`. Khi xây automation, dùng **trạng thái terminal của API** thay vì so sánh một log text đơn lẻ.

| Thành phần | Trách nhiệm |
| --- | --- |
| **Submitter** | Gửi batch, chọn runtime, tài nguyên, source, network và nhận batch ID |
| **Control plane** | Điều phối tài nguyên thực thi theo batch và quota |
| **Driver** | Lên kế hoạch Spark jobs/stages, tạo task, quản lý DAG và kết quả |
| **Executors** | Đọc/ghi dữ liệu, thực thi transformations và shuffle |
| **Object storage / warehouse** | Lưu input/output, artifacts, dependencies, checkpoints nếu cần |
| **Observability** | Hiển thị batch state, Spark UI, logs, metrics, lỗi và chi phí |

Không suy rằng lệnh `gcloud ... submit` trả về ngay có nghĩa pipeline đã hoàn thành. Nếu dùng `--async`, CLI **chỉ gửi yêu cầu rồi trở về**, bước tiếp theo phải **poll/watch batch đến khi SUCCEEDED**, kiểm tra output và xử lý FAILED/CANCELLED.

### 2.1. Batch khác job trên một cluster có sẵn

| Cách gửi | Đối tượng quản lý | Dùng lệnh |
| --- | --- | --- |
| **Serverless batch** | Batch resource theo region, hạ tầng tự cấp phát | `gcloud dataproc batches submit pyspark ...` |
| **Cluster job** | Job chạy trên Dataproc cluster đã có | `gcloud dataproc jobs submit pyspark ... --cluster=...` |

Hai lệnh **không thay thế trực tiếp**: `batches submit` không cần `--cluster`, còn `jobs submit` cần cluster được chọn. Quản trị cluster và serverless batch có mô hình tính chi phí/quota khác nhau.

## 3. Runtime, IAM và VPC: ba điều kiện trước khi chạy

### 3.1. Runtime version và danh tính thực thi

Runtime version quyết định phiên bản Spark, Python/Java, connectors, tính năng và **cách ủy quyền danh tính**. Tài liệu 2026 phân biệt:

- **Runtime trước 3.0:** với service account credentials, workload dùng **Compute Engine default service account** hoặc custom service account đã gắn. Người submit cần quyền Dataproc thích hợp cùng `iam.serviceAccounts.actAs` trên service account; runtime identity cần `Dataproc Worker` và quyền dữ liệu.
- **Runtime 3.0 trở lên:** mặc định dùng **end-user credentials (EUC)** của người submit, nếu không chọn service account credentials. Có thể cấu hình **custom service account** theo yêu cầu tổ chức; khi đó cần roles/permissions chuyên biệt cho serverless node và service agents theo tài liệu phiên bản.
- **Runtime 4.0 trở lên:** có những thay đổi về resource tiers/Spark version; không mang nguyên tất cả Spark properties hoặc jar của runtime 2.x sang 4.x mà không test.

**Không phụ thuộc runtime mặc định khi production cần tái lập.** Chọn một phiên bản `major.minor` đang được hỗ trợ, kiểm thử tương thích thư viện và theo dõi EOL; các bản cập nhật phụ có thể được dịch vụ phát hành trong một dòng runtime.

### 3.2. Quyền phân tách theo vai trò

| Principal | Quyền cần có | Tránh |
| --- | --- | --- |
| **Người/CI submit batch** | `dataproc.batches.create`, get/list/operations tương ứng; role **Dataproc Serverless Editor** cho runtime mới nếu phù hợp | Project Owner chỉ để submit batch |
| **Submitter chọn custom SA** | `iam.serviceAccounts.actAs` trên **đúng** SA được gắn | Service Account Token Creator rộng nếu không cần |
| **Execution identity (EUC hoặc SA)** | Quyền đọc bucket input, ghi output, ghi logs và BigQuery access đúng dataset | Editor trên mọi buckets và mọi BigQuery datasets |
| **Service agents do Google quản lý** | Role cần thiết theo runtime/quy trình kích hoạt dịch vụ | Xóa role/SA hệ thống khi chưa hiểu tác động |
| **Người chỉ xem job** | Viewer với quyền get/list batch và logs được duyệt | Dataproc Admin/Editor |

Ví dụ, job đọc `gs://learning-lab-raw/events/` và ghi `gs://learning-lab-curated/` cần quyền **Storage Object Viewer** trên nguồn và quyền tạo object ở đích, cùng quy tắc ghi đè/xóa nếu pipeline thực sự cần. Nếu ghi BigQuery, cần quyền **tạo job** tại project job và quyền **ghi dữ liệu** vào dataset/table đích theo connector, không chỉ `roles/bigquery.dataViewer`.

**Không để nhầm danh tính:** user chạy CLI có quyền đọc bucket không chứng minh custom workload SA có quyền đó; ngược lại, với **EUC runtime 3.x** các yêu cầu quyền dữ liệu dựa trên user identity được sử dụng. Khi điều tra 403, xác định **runtime version + execution identity thực tế** trước.

### 3.3. VPC và location

Serverless Spark sử dụng compute có **internal IP**, chạy trên subnet **trong region của batch**. Nếu không chỉ rõ, dịch vụ có thể tìm subnet mặc định theo region; dự án dùng custom VPC thường phải đặt `--subnet`.

- Cần **đường nội bộ giữa driver/executors**, firewall và IP addresses phù hợp trong subnet.
- **Private Google Access** được bật cho subnet liên quan theo cơ chế sản phẩm để truy cập các Google APIs cần thiết.
- Nếu job cần tải package/model từ **Internet bên ngoài**, kiểm tra **Cloud NAT/egress** và DNS phù hợp; Private Google Access **không tương đương Internet public access**.
- Với VPC Service Controls/Shared VPC/PSC, phải kiểm tra egress, service perimeter, role service agent và networking tương ứng.
- Chọn region gần dữ liệu và phù hợp **residency**; cross-region data transfer có thể tăng độ trễ và chi phí.

Thao tác thay firewall/VPC của project **không thuộc lab học bài này**. Nếu không có subnet/identity đã được chuẩn bị, chỉ làm lab trên giấy hoặc nhờ quản trị viên phê duyệt cấu hình trước khi submit.

## 4. Ví dụ PySpark: tổng hợp sự kiện ghi danh theo khóa học

Tình huống: dữ liệu `CSV` có các cột `event_id`, `course_id`, `status` và `event_time`. Ta muốn đếm **số sự kiện ACTIVE không trùng `event_id`** theo khóa học và ghi Parquet để các bước phân tích có thể đọc tiếp.

### 4.1. Mã `aggregate_enrollments.py`

~~~python
import argparse
from pyspark.sql import SparkSession, functions as F, types as T


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    spark = SparkSession.builder.appName("enrollment-counts-lab").getOrCreate()

    schema = T.StructType([
        T.StructField("event_id", T.StringType(), True),
        T.StructField("course_id", T.StringType(), True),
        T.StructField("status", T.StringType(), True),
        T.StructField("event_time", T.StringType(), True),
    ])

    try:
        events = (
            spark.read.option("header", "true")
            .schema(schema)
            .csv(args.input)
        )
        valid = (
            events.filter(
                F.col("event_id").isNotNull()
                & F.col("course_id").isNotNull()
                & (F.col("status") == "ACTIVE")
            )
            .dropDuplicates(["event_id"])
        )
        counts = valid.groupBy("course_id").agg(
            F.count("*").alias("active_enrollments")
        )
        # Mỗi lần chạy nên có output prefix duy nhất.
        counts.write.mode("errorifexists").parquet(args.output)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
~~~

**Đặc điểm quan trọng:**

- Schema đặt tường minh, không dùng `inferSchema` toàn bộ file ở mỗi lượt chạy.
- `dropDuplicates(["event_id"])` giả định một `event_id` đại diện cho **một sự kiện duy nhất**, không bao giờ có nhiều bản ghi mang cùng ID nhưng giá trị khác nhau. Nếu dữ liệu nguồn có nhiều phiên bản cập nhật cho một event, cần quy tắc sắp xếp/version và đối soát khác; `dropDuplicates` không chọn bản mới nhất một cách bảo đảm.
- Đây là **batch bounded**; với streaming/dedupe theo thời gian phải dùng thiết kế event-time/watermark/checkpoint thích hợp.
- `mode("errorifexists")` giúp không vô tình ghi đè kết quả cũ; khi retry production, dùng prefix cố định theo batch ID rồi kiểm tra output manifest, hoặc cơ chế staging/atomic publish đáng tin cậy.
- Spark ghi **một thư mục chứa nhiều part files**, không phải một file Parquet tên bằng `--output`. Đừng đưa một tên `.parquet` rồi giả định file đơn.

### 4.2. Dữ liệu giả tối thiểu

Tạo file `enrollments.csv` **tại máy lab**, không chứa PII:

~~~csv
event_id,course_id,status,event_time
e001,java-basic,ACTIVE,2026-11-18T10:00:00Z
e002,java-basic,ACTIVE,2026-11-18T10:03:00Z
e003,python-basic,ACTIVE,2026-11-18T10:04:00Z
e003,python-basic,ACTIVE,2026-11-18T10:04:00Z
e004,java-basic,CANCELLED,2026-11-18T10:05:00Z
e005,python-basic,ACTIVE,2026-11-18T10:06:00Z
~~~

Kỳ vọng: `java-basic = 2` và `python-basic = 2`, bởi event `e003` bị lặp và `e004` đã hủy. Trong production, phải kiểm tra số lượng input rows, lỗi parse, số event bị trùng, late-arriving events và reconciliation với nguồn nghiệp vụ.

### 4.3. Quy tắc output hữu ích

| Quy tắc | Vì sao |
| --- | --- |
| Chọn `gs://.../output/run_id=.../` riêng cho mỗi lần chạy | Không ghi đè job trước, dễ đối chiếu và rollback |
| Chỉ cho bước tiếp đọc sau khi batch **SUCCEEDED** và validate đủ file | Tránh downstream đọc kết quả chưa hoàn tất |
| Dùng Parquet/columnar format cho pipeline phân tích | Giảm bytes quét so với CSV trong nhiều truy vấn |
| Partition/bucket theo query thật và dataset size | Tránh hàng nghìn file quá nhỏ hoặc một partition cực lớn |
| Ghi metadata: `run_id`, input prefix, code version, row counts | Hỗ trợ idempotency, lineage và điều tra |

**Cảnh báo:** nếu sink là BigQuery, phải dùng Spark BigQuery connector được runtime hỗ trợ, quyền dataset/job phù hợp và chọn chế độ ghi (`append`/`overwrite`) có kiểm soát; **không** suy output Parquet ở Cloud Storage đã được import vào BigQuery.

## 5. Submit Spark batch bằng CLI

### 5.1. Chuẩn bị môi trường có kiểm soát

Các lệnh dưới đây dành cho **project lab đã được chủ sở hữu phê duyệt**. Cần có billing, Dataproc/Managed Service for Apache Spark API, Cloud Storage API, quyền submit batch, và bucket input/output/staging được cấu hình **cùng chính sách location**. Người học không tự bật API, tạo VPC/firewall, hoặc cấp IAM trong production nếu chưa được giao.

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export REGION="asia-southeast1"
export STAGING_BUCKET="YOUR_EXISTING_LAB_STAGING_BUCKET"
export DATA_BUCKET="YOUR_EXISTING_LAB_DATA_BUCKET"
export SUBNET="projects/YOUR_APPROVED_LAB_PROJECT/regions/asia-southeast1/subnetworks/YOUR_LAB_SUBNET"
export RUN_ID="batch-lab-001"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project

# Chỉ đọc: kiểm tra API và tài nguyên đã được cấp
gcloud services list --enabled --filter="name:dataproc.googleapis.com"
gcloud storage buckets describe "gs://$STAGING_BUCKET"
gcloud storage buckets describe "gs://$DATA_BUCKET"
gcloud dataproc batches list --region="$REGION" --project="$PROJECT_ID"
~~~

Nếu không có subnet hoặc buckets đã được quản lý, **dừng phần chạy thật** và hoàn thành lab giấy ở mục 9. Không dùng default VPC nếu tổ chức yêu cầu custom VPC; cũng không tự chạy `gcloud services enable` khi chưa được phê duyệt.

### 5.2. Đưa code và dữ liệu giả lên Cloud Storage

Chỉ copy **file lab**. Đảm bảo `RUN_ID` chưa được dùng và đường đích không chứa dữ liệu của người khác:

~~~bash
gcloud storage cp ./aggregate_enrollments.py \
  "gs://$STAGING_BUCKET/scripts/$RUN_ID/aggregate_enrollments.py"
gcloud storage cp ./enrollments.csv \
  "gs://$DATA_BUCKET/input/$RUN_ID/enrollments.csv"
~~~

**Không coi Cloud Storage bucket là nơi public tạm thời**: cấp Storage Object Viewer/Creator theo danh tính workload, không dùng `allUsers`. Sau upload, kiểm tra URI/bytes và chỉ định output prefix mới.

### 5.3. Chạy batch với runtime được hỗ trợ

Ví dụ chọn **runtime 3.0**, nếu đang được cấp cho project/region, nhằm minh họa mặc định **end-user credentials**. Người submit phải có quyền dữ liệu tương ứng, đồng thời subnet và IAM cần sẵn sàng:

~~~bash
# THAO TÁC CÓ TÍNH PHÍ: chạy tài nguyên Spark thật.
gcloud dataproc batches submit pyspark \
  "gs://$STAGING_BUCKET/scripts/$RUN_ID/aggregate_enrollments.py" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --batch="$RUN_ID" \
  --version="3.0" \
  --subnet="$SUBNET" \
  --properties="spark.dynamicAllocation.maxExecutors=5" \
  -- \
  --input="gs://$DATA_BUCKET/input/$RUN_ID/enrollments.csv" \
  --output="gs://$DATA_BUCKET/output/$RUN_ID"
~~~

Đây là **lệnh tạo batch thực tế**, không chạy trong production chỉ để đọc bài. Version `3.0` được chọn để giải thích luồng auth mới; nếu runtime này không còn sẵn ở thời điểm thực hành, người học phải kiểm tra [runtime versions](https://cloud.google.com/dataproc-serverless/docs/concepts/versions/dataproc-serverless-versions) và dùng phiên bản được hỗ trợ cùng quyền tương ứng. `--subnet` chỉ dùng subnet trong đúng region, đã có firewall/internal connectivity cần thiết.

Một phương án production dùng **custom workload service account** thay EUC:

~~~bash
# THAM SỐ THAY THẾ, không phải chạy thêm một batch cùng RUN_ID.
# Chỉ dùng sau khi Admin cấp SA, actAs, runtime node/service agent roles,
# Cloud Storage/BigQuery quyền tối thiểu và đã kiểm tra tương thích runtime.
--service-account="spark-batch-runtime@YOUR_PROJECT.iam.gserviceaccount.com"
~~~

Không tự ghép tham số ở trên vào lệnh production nếu chưa kiểm tra yêu cầu IAM **runtime 3.x**. Với runtime trước 3.0, cách cấp Dataproc Worker/Compute Engine SA khác đáng kể; không suy một cấu hình roles dùng được cho tất cả versions.

### 5.4. Đọc kết quả và log

~~~bash
# Chỉ đọc; những lệnh này không tạo thêm batch.
gcloud dataproc batches describe "$RUN_ID" \
  --region="$REGION" --project="$PROJECT_ID"
gcloud dataproc batches list \
  --region="$REGION" --project="$PROJECT_ID"
gcloud storage ls "gs://$DATA_BUCKET/output/$RUN_ID/"
~~~

Nếu batch không `SUCCEEDED`, đừng cho downstream đọc output. Mở **Managed Service for Apache Spark → Batches → chọn batch** trong Console để xem trạng thái, driver logs, Spark UI và thông tin metrics. Kiểm tra số rows đầu vào/đầu ra (ở đây expected counts 2 và 2) bằng Spark/BigQuery query được phê duyệt, không dựa riêng vào việc output folder tồn tại.

**Không xóa batch khi đang cần logs để điều tra.** Khi lab xong, chỉ dọn đúng output/input/scripts của `RUN_ID` do bạn tạo, sau khi chắc chắn không pipeline nào đang tham chiếu chúng. Metadata batch có thời hạn/retention theo dịch vụ; việc không còn VM không có nghĩa bucket/output đã được tự dọn.

## 6. Autoscaling, shuffle và chọn tài nguyên

### 6.1. Dynamic allocation không phải quota tự động vô hạn

Serverless Spark bật **dynamic resource allocation** theo khả năng runtime: số executors có thể tăng/giảm dựa trên workload Spark. Các thuộc tính quan trọng:

| Thuộc tính Spark | Ý nghĩa | Cảnh báo |
| --- | --- | --- |
| `spark.dynamicAllocation.enabled` | Bật/tắt cấp phát executor linh hoạt | Không tắt chỉ vì muốn “ổn định”; có thể làm phí tăng hoặc thiếu capacity |
| `spark.dynamicAllocation.initialExecutors` | Số executor ban đầu | Không đồng nghĩa số executor cố định |
| `spark.dynamicAllocation.minExecutors` | Số executor thấp nhất | Giữ minimum cao có thể khiến batch nhỏ tốn tài nguyên hơn |
| `spark.dynamicAllocation.maxExecutors` | Cận trên executor cho batch | Không bảo đảm luôn có đủ quota hay IP để cấp đến mức này |
| `spark.dynamicAllocation.executorAllocationRatio` | Điều chỉnh mức độ scale-up so với lượng parallelism cần | Tăng quá nhanh có thể lãng phí resources |
| `spark.dataproc.scaling.version` | Chọn autoscaling V1 hoặc V2 theo hỗ trợ | V2 hỗ trợ downscale bất đồng bộ và quản lý shuffle tốt hơn |
| `spark.dynamicAllocation.profile` | Profile `cost` hoặc `performance` nếu runtime hỗ trợ | Profile có thể bị property được đặt tường minh ghi đè |

Trong tài liệu hiện hành, mức **min/initial executors** có giới hạn thấp nhất theo sản phẩm (thường **2**). Tránh đặt `minExecutors=0` chỉ vì nghĩ serverless đồng nghĩa scale to zero **trong lúc batch vẫn chạy**. Batch kết thúc mới giải phóng tài nguyên; không tự coi đang RUNNING có thể không tốn compute.

Ví dụ các thuộc tính có thể điều chỉnh theo nhu cầu:

~~~bash
--properties="spark.dataproc.scaling.version=2,spark.dynamicAllocation.initialExecutors=2,spark.dynamicAllocation.maxExecutors=20,spark.dynamicAllocation.executorAllocationRatio=0.5"
~~~

Đây là **đoạn flag thay thế** cho dòng `--properties` của lệnh submit, không phải lệnh shell độc lập. `maxExecutors=20` chỉ là ngưỡng trần cho lab tải lớn đã được phê duyệt; với lab 6 hàng, 20 executors là **dư thừa**. Không thay đổi nhiều properties cùng lúc khi benchmark.

### 6.2. Autoscaling V1 và V2

| Tính năng | V1 | V2 |
| --- | --- | --- |
| Scale-down | Chủ yếu đồng bộ với tiến trình shuffle migration | Có cơ chế **asynchronous downscaling** |
| Chọn nodes để scale-down | Ít tối ưu theo trạng thái shuffle | Chọn nodes có xét dữ liệu shuffle/idle |
| Tinh chỉnh graceful decommission/shuffle | Hạn chế hơn | Có thêm thuộc tính điều khiển |

Để bật V2, dùng `spark.dataproc.scaling.version=2` nếu **runtime/tier** đã chọn hỗ trợ. Không suy version 2 luôn nhanh hơn với mọi job: so **total DCU-time**, shuffle read/write, retries, p99 stage time và duration. Một job rất ngắn có thể bị chi phối bởi thời gian setup, nên thay scale algorithm ít có tác dụng.

### 6.3. Memory, partitions và skew

| Triệu chứng | Nguồn gốc cần xem | Hướng thử nghiệm |
| --- | --- | --- |
| Executor OOM | Join/shuffle lớn, skew, object overhead hoặc partition quá lớn | Profile, tăng phân vùng hợp lý, xử lý skew trước khi tăng RAM |
| Một stage có rất ít tasks dù nhiều executors | Input files/partitions ít, code `coalesce(1)` quá sớm | Kiểm tra physical plan, input splits và parallelism |
| Nhiều tasks cực nhỏ, scheduler overhead cao | Quá nhiều small files hoặc shuffle partitions | Gom file hợp lý, chọn partitions dựa dataset size |
| Một task mất lâu hơn mọi task khác | Data skew theo key rất phổ biến | Salt/hot-key split, adaptive query execution, broadcast join nếu phù hợp |
| Shuffle spill nhiều | Memory/partitions/joins chưa tối ưu, disk pressure | Đọc Spark UI shuffle spill, partition sizes, memory và skew |
| Driver OOM | Dùng `collect()` hoặc `toPandas()` trên dataset lớn | Trả dữ liệu phân tán, dùng `limit` cho preview, không kéo toàn bộ về driver |

**Nguyên tắc:** Spark parallelism thực sự bị giới hạn bởi số partitions/tasks có ích và I/O của nguồn/đích; có 100 executors nhưng chỉ 10 tasks độc lập không làm một phép đọc chạy nhanh gấp 100.

### 6.4. Partitioning và định dạng lưu trữ

- Chuyển CSV sang **Parquet** với schema thống nhất thường giảm dữ liệu đọc cho phân tích cột.
- Chỉ **partition output theo trường có ý nghĩa truy vấn** (ví dụ `event_date`), không tùy tiện partition theo `event_id` cardinality rất cao.
- Tránh tạo hàng nghìn files vài KB: file listing/metadata và downstream scan có overhead.
- Với `repartition(n)`, chọn `n` theo dữ liệu, không đặt 1 để “dễ xem file”; ép `coalesce(1)` trên dữ liệu lớn tạo task nghẽn.
- Khi ghi BigQuery, cân nhắc loại connector, partition/clustering, quyền BigQuery jobs và cách commit output để không nhân bản dữ liệu khi retry.

**Lưu ý nguồn dữ liệu:** Cloud Storage có thể truyền dữ liệu nhanh nhưng Spark vẫn phải đọc bytes, giải mã và xử lý; network/cross-region, codec và connector quyết định tốc độ. Không nhầm CPU thấp với “Spark không dùng hết tài nguyên” khi I/O đang nghẽn.

## 7. Orchestration, lịch chạy và tính đúng khi retry

### 7.1. Tách scheduler khỏi batch

Serverless Spark **nhận và chạy** workload; còn lịch chạy, phụ thuộc giữa các bước và SLA pipeline cần orchestration riêng.

~~~mermaid
flowchart TB
    SCH["Lịch hằng đêm<br/>Managed Airflow / Workflows"] --> CHECK["Kiểm tra input + định danh run"]
    CHECK --> BATCH["Submit Spark batch"]
    BATCH --> WATCH{"Chờ trạng thái terminal"}
    WATCH -->|SUCCEEDED| VAL["Validate output + row counts"]
    WATCH -->|FAILED/CANCELLED| ERR["Alert, retry có giới hạn"]
    VAL --> PUBLISH["Công bố partition / BigQuery table"]
    PUBLISH --> DOWN["Dashboard / downstream API"]
    ERR --> CHECK
~~~

**Managed Service for Apache Airflow** (được quản lý bằng Google Cloud) có operators để chạy và theo dõi Dataproc serverless batches. Với nhu cầu đơn giản, có thể dùng Cloud Scheduler kích hoạt Workflows/Cloud Run điều phối **Batches API**. Không dùng Cloud Scheduler tự submit trùng job nếu không có job ID, lock/idempotency và cơ chế xử lý timeout.

### 7.2. Retry nào an toàn?

| Trường hợp | Hành động |
| --- | --- |
| Submit request timeout nhưng batch có thể đã được tạo | **Get batch theo ID** trước khi submit lại; dùng request ID/idempotency nếu API hỗ trợ |
| Batch FAILED sau khi đã ghi một phần output | Không tự append lại; ghi vào staging prefix riêng và cleanup/reconcile trước retry |
| BigQuery sink có thể nhận duplicates | Dùng MERGE theo business key hoặc bảng staging + publish transaction phù hợp |
| Input tới muộn | Xác định watermark/cửa sổ chấp nhận late data và backfill có ID riêng |
| Downstream report query thất bại | Không chạy lại toàn bộ Spark nếu output của batch đã được xác minh tốt |
| Thay code/schema giữa hai lần retry | Ghi code version và input snapshot; yêu cầu review thay vì gọi đây là một retry tương đương |

**Batch ID** nên xác định một lượt chạy có chủ đích, ví dụ `enrollment-20261118-r01`. Không tái sử dụng ID của batch đã có mà chưa tra cứu trạng thái. Với **backfill** ngày cũ, lưu input/output manifest và làm rõ cơ chế ghi thay thế; nếu ngày mới được xử lý lại, tránh cộng dồn kết quả cũ do `append`.

### 7.3. Lưu thông tin lineage tối thiểu

Một bản ghi metadata run nên có:

~~~json
{
  "run_id": "enrollment-20261118-r01",
  "source": "gs://lab-raw/events/date=2026-11-18/",
  "output": "gs://lab-curated/enrollment_counts/run_id=enrollment-20261118-r01/",
  "code_version": "git-commit-or-image-digest",
  "runtime_version": "3.0",
  "batch_state": "SUCCEEDED",
  "validation": "PASS",
  "published_at": "2026-11-19T03:00:00Z"
}
~~~

Đây là **metadata minh họa**; không lưu service account token, credential hoặc PII trong manifest. `SUCCEEDED` phải đến từ batch API, còn `validation=PASS` là kiểm tra **riêng** của pipeline (schema/row count/uniqueness/output location). Chỉ sau cả hai đạt mới công bố dữ liệu.

## 8. Giám sát, chi phí và lựa chọn môi trường

### 8.1. Những tín hiệu cần theo dõi

| Nhóm | Metric/bằng chứng | Câu hỏi |
| --- | --- | --- |
| **Batch lifecycle** | Thời gian PENDING/SETUP/RUNNING, SUCCEEDED/FAILED, retry count | Batch có kịp deadline báo cáo? |
| **Spark UI** | DAG, stages, tasks, shuffle read/write/spill, executor utilization | Nghẽn ở driver, skew hay network? |
| **Logs** | Driver exception, executor lost, IAM error, OutOfMemory | Lỗi cấu hình hay lỗi dữ liệu? |
| **Input/output** | Rows/bytes, late data, duplicates, null rate, số files | Kết quả có đầy đủ và đúng schema không? |
| **Compute/cost** | DCU-time, driver/executor resources, shuffle storage, duration | Chi phí trên một triệu events có tăng? |
| **Data services** | Cloud Storage requests/bytes, BigQuery query/storage costs | Tiền hạ tầng Spark có phải toàn bộ chi phí? |
| **Network** | Subnet IPs, egress, VPC/perimeter violations | Job lỗi vì không tới được nguồn/đích? |

Spark UI của batch có thể xem **trực tiếp trong Console** mà không cần Persistent History Server cho trường hợp được hỗ trợ. Trước khi dùng cho audit dài hạn, kiểm tra thời gian giữ dữ liệu của Spark UI/logs, quyền truy cập và chính sách retention; không coi UI mặc định lưu mãi.

### 8.2. Serverless tính giá thế nào?

Managed serverless Spark sử dụng đơn vị **Data Compute Unit (DCU)** và tính theo tài nguyên/thời gian chạy, với phân biệt **standard/premium tiers**, shuffle storage và thành phần dùng kèm. **Không phải chỉ trả theo số hàng đầu ra**, và “serverless” không đồng nghĩa một batch nhỏ miễn phí.

Một mô hình chi phí:

\[
\text{Tổng}\approx
\text{DCU-seconds của driver/executors}\times\text{đơn giá}
+\text{shuffle storage}
+\text{Cloud Storage / BigQuery / network / logging}
\]

Kiểm tra **đơn vị giá** (DCU-hour hoặc DCU-second khi quy đổi) để không nhân sai 3.600 lần. Thời gian setup và resource minimums của workload cũng ảnh hưởng tổng phí. Interactive session giữ sống lâu có thể tiêu thụ tài nguyên trong khi người dùng không làm gì; phải đặt TTL/auto-stop theo chính sách.

**Một thay đổi runtime cần được xem xét về giá:** từ 4.0 trở lên, mô hình chọn resource tier có thay đổi; batch có thể dùng **premium mặc định** trừ khi chọn `dataproc.tier=standard` theo hỗ trợ. Không bê nguyên thiết lập `spark.dataproc.driver.compute.tier` của runtime cũ sang 4.0. Xem [bảng giá](https://cloud.google.com/products/managed-service-for-apache-spark/pricing) hiện hành theo region/tier trước khi cam kết ngân sách.

### 8.3. Tối ưu chi phí có đánh đổi

| Điều chỉnh | Có thể cải thiện | Rủi ro |
| --- | --- | --- |
| Giảm initial/min executors | Ít compute lúc ít việc | Batch chạy lâu hơn nếu scale-up chậm |
| Tăng max executors có kiểm soát | Giảm wall-clock time khi có nhiều tasks | Peak DCU, quota/IP tăng, chi phí có thể cao hơn |
| Chọn autoscaling profile `cost` | Có thể giảm tài nguyên nhàn rỗi | Một số stage sẽ chạy chậm hơn |
| Tối ưu file sizes/partition pruning | Ít I/O/shuffle và job nhanh hơn | Cần thay schema/layout, kiểm thử downstream |
| Chuyển job SQL đơn giản sang BigQuery | Bớt vận hành Spark và overhead startup | Chi phí BigQuery cần so bằng benchmark thật |
| Gom các batch nhỏ có cùng dependency | Ít startup/setup overhead | Tăng coupling, retry một bước có thể ảnh hưởng nhiều đầu ra |

**So tổng chi phí với deadline**, không chỉ so phút chạy. Một batch 10 phút dùng 5 DCU trung bình và batch 4 phút dùng 30 DCU trung bình có mức tiêu thụ khác; muốn quyết định phải dùng số DCU-time đo thực tế và chi phí dịch vụ phụ.

## 9. Chẩn đoán khi batch không chạy hoặc kết quả sai

### 9.1. Bảng lỗi theo lớp

| Triệu chứng | Nguồn gốc thường gặp | Kiểm tra an toàn |
| --- | --- | --- |
| Không submit được, thiếu `dataproc.batches.create` | Submitter thiếu quyền Dataproc Serverless tương ứng | Xác định principal và role theo runtime; không cấp Owner |
| `iam.serviceAccounts.actAs` bị từ chối | Người submit muốn gắn custom SA chưa được ủy quyền | Kiểm tra quyền **trên SA cụ thể**, không ở tài khoản khác |
| Driver không khởi tạo, chờ lâu rồi timeout | Thiếu role execution identity/service agent, subnet/firewall/DNS, không đủ IP/quota | Xem batch details, runtime version, IAM và network logs |
| `403` khi đọc Cloud Storage | Danh tính thực thi không có quyền object input | Kiểm tra EUC hay custom SA, bucket policy và object path |
| `403` khi ghi BigQuery | Thiếu `jobs.create` hoặc `tables.updateData`/role dữ liệu phù hợp | Kiểm tra job project/dataset, connector và execution SA |
| `ClassNotFound`/`ModuleNotFoundError` | Thiếu package/JAR hoặc sai version Spark/Python/Scala | Ghi rõ runtime, dependencies, image và connector versions |
| `OutOfMemoryError` trên driver | `collect()`/`toPandas()` hoặc metadata/plan lớn | Kiểm tra Spark UI, bỏ thu hết dữ liệu vào driver |
| Executor OOM, stage retry | Skew, partitions lớn, shuffle spill, tài nguyên thiếu | Xem task skew, physical plan, partition sizes và resources |
| Batch SUCCEEDED nhưng output rỗng | Sai path/filter, schema parse, missing input, ghi vào prefix khác | So input counts, schema, output manifest và dữ liệu mẫu |
| Retry khiến duplicate rows ở sink | Ghi append không idempotent, retry sau partial write | Stage/merge theo business key, kiểm soát run ID và commit |
| Job chậm dù CPU thấp | I/O, remote bucket, network, hot partition, small files | Đọc Spark UI I/O/shuffle, region và connector metrics |
| Batch chưa xong trước lịch sáng | Setup overhead, quota đợi, join/shuffle nặng | Tách PENDING vs RUNNING, thiết kế headroom và trigger sớm |

### 9.2. Runbook khi batch FAILED

1. **Khoanh vùng** đúng `project`, `region`, `batch_id`, thời gian bắt đầu, runtime và submitter.
2. Đọc `gcloud dataproc batches describe`, driver logs, Spark UI; phân biệt **lỗi cấp tài nguyên** với lỗi **mã xử lý**.
3. Xác định execution identity: EUC/runtime 3.x hay service account; đối chiếu quyền data source/sink.
4. Kiểm tra VPC subnet, firewall, DNS, Private Google Access, egress, VPC Service Controls và quota nếu driver chưa chạy.
5. Nếu driver chạy và lỗi, xem exception root cause, stage/task retries, OOM, shuffle skew và SQL schema.
6. Kiểm tra output prefix bị ghi một phần, quyết định **cleanup/retry/merge** theo runbook; không tự append lại.
7. Sau khi khắc phục, chạy lại **một batch ID mới** hoặc theo cơ chế idempotency được thiết kế; xác minh số hàng và SLO.

**Quy tắc phản ứng:** không tăng executor memory, cấp BigQuery Admin và mở firewall toàn mạng cùng lúc. Làm vậy vừa tăng blast radius vừa mất khả năng biết nguyên nhân thật.

### 9.3. Cách đọc `SUCCEEDED`

`SUCCEEDED` nghĩa là Spark workload kết thúc theo tiêu chí của dịch vụ. Nó **không chứng minh**:

- Đã đọc đúng input partition hoặc schema.
- Đã loại hết duplicate/late-arriving events theo định nghĩa nghiệp vụ.
- Đã ghi kết quả đến vị trí mà downstream đang đọc.
- Một bảng BigQuery hoặc dashboard đã được cập nhật.
- Không phát sinh rò rỉ PII hay sai phân quyền nguồn/đích.

Vì vậy cần thêm **data-quality gate**, ví dụ: `input_events >= expected_min`, `duplicate_event_ids = 0` trong output, kiểm tra số courses, output manifest hợp lệ và reconciliation với dữ liệu nguồn. Khi không đạt, đánh dấu pipeline **validation failed** dù batch state là `SUCCEEDED`.

## 10. Bài tập và tình huống thực tế

### Tình huống A — Có nên dùng serverless Spark cho 3 câu SQL?

Đội dữ liệu mỗi ngày muốn chạy ba phép `GROUP BY` trên bảng BigQuery 20 GiB. Không có thư viện Spark đặc biệt, không cần đọc file ngoài kho dữ liệu.

**Yêu cầu:** chọn BigQuery SQL, serverless Spark hay cụm Spark tự quản lý.

**Hướng giải:** BigQuery SQL thường là điểm xuất phát đơn giản. So chi phí query, latency, quản trị và tính năng. Serverless Spark chỉ có ưu thế nếu có chuyển đổi/ML/dependency trong Spark đáng giá; tự quản lý cluster cho ba câu SQL nhỏ có overhead vận hành không cần thiết.

### Tình huống B — Job 2 lần/ngày, đầu vào 1 TiB Parquet

Mỗi đêm xử lý 1 TiB dữ liệu, áp business rules PySpark, join với dimension table và ghi Parquet curated. Các job còn lại cách nhau nhiều giờ.

**Yêu cầu:** đề xuất hình thức chạy, IAM, scheduling, output layout và metric cần kiểm soát.

**Hướng giải:** dùng **serverless batch** là ứng viên hợp lý, với runtime đã pin, identity quyền tối thiểu trên buckets, subnet/region phù hợp, lịch chạy qua Managed Airflow/Workflows. Đầu ra theo `run_id` hoặc partition ngày, publish sau validation; đo wall-clock, DCU-time, shuffle spill, input/output bytes, failed retries và data-quality checks.

### Tình huống C — Submitter có quyền nhưng job vẫn `403`

Người dùng `alice@example.com` có `Dataproc Serverless Editor` và Storage Object Viewer trên input bucket. Batch chạy runtime 3.x với **custom service account** `spark-runtime@...`; driver báo thiếu quyền đọc `gs://input-bucket`.

**Yêu cầu:** principal nào thiếu quyền? Có nên cấp Editor toàn project?

**Hướng giải:** kiểm tra **execution service account** được gắn và cấp quyền Storage Object Viewer **trên input bucket** cho SA đó, cùng các quyền runtime node cần thiết theo phiên bản. Quyền đọc của Alice không tự truyền sang custom SA. Không cấp Editor toàn project; kiểm tra cả quyền `actAs` của submitter.

### Tình huống D — Tăng executors nhưng không nhanh hơn

Một job có 6 partitions xử lý độc lập, hiện dùng 8 executors. Đội tăng maxExecutors lên 100 nhưng thời gian gần như không giảm.

**Yêu cầu:** nguyên nhân và thay đổi nào đáng benchmark?

**Hướng giải:** số tasks thực đang hạn chế parallelism; 100 executors không làm xuất hiện 100 tasks có ích. Xem Spark UI số partitions và data skew, tăng phân vùng đầu vào/join hợp lý nếu I/O và dataset đủ lớn; không tăng executors chỉ để nhìn CPU tổng cao hơn.

### Tình huống E — Job chạy lại sau timeout làm tổng tăng gấp đôi

Job ghi kết quả bằng `append` vào bảng BigQuery. Orchestrator timeout và submit batch mới dù batch đầu đã ghi dữ liệu xong; dashboard báo tổng ghi danh tăng gấp đôi.

**Yêu cầu:** thiết kế chống lặp ở ba lớp.

**Hướng giải:** (1) job submission dùng `batch_id/request_id` và kiểm tra trạng thái trước retry; (2) output vào staging prefix/table theo `run_id` và validate; (3) publish bằng `MERGE`/dedupe theo business key hoặc thay partition theo quy trình. Orchestrator chỉ đánh dấu thành công khi API state và validation đều đạt.

### Tình huống F — Streaming chạy trong batch 24/7 rồi bị restart

Đội dùng Structured Streaming từ Pub/Sub, nhưng không cấu hình checkpoint bền vững và không có supervisor/restart policy, cho rằng serverless Spark sẽ tự duy trì stream liên tục.

**Yêu cầu:** giải thích sai lầm và lựa chọn khác.

**Hướng giải:** serverless hạ tầng Spark **không tự quản lý mọi yêu cầu khôi phục streaming job**. Cần checkpoint, state/replay semantics, giám sát, restart orchestration và giới hạn chi phí; nếu nhu cầu là streaming event-time liên tục, đánh giá **Dataflow/Beam** phù hợp hơn.

### Bài tập định lượng — lựa chọn theo DCU-time

Hai cấu hình xử lý cùng một batch và đều đạt chất lượng đầu ra:

| Cấu hình | DCU sử dụng trung bình khi chạy | Thời gian chạy | DCU-hours ước tính |
| --- | ---: | ---: | ---: |
| A — tiết kiệm executors | 12 DCU | 30 phút | 6 |
| B — nhiều executors | 30 DCU | 15 phút | 7,5 |

**Câu hỏi:**

1. Cách tính DCU-hours? — `DCU trung bình × thời gian (giờ)`.
2. Nếu cùng tier/đơn giá, cấu hình nào có phần compute charge thấp hơn? — **A** (6 so với 7,5 DCU-hours).
3. Cấu hình nào nhanh hơn? — **B**, 15 phút so với 30 phút.
4. Có thể khẳng định A rẻ hơn **tổng** bao nhiêu tiền chưa? — **Chưa**: cần giá theo tier/region, shuffle storage, dữ liệu I/O và các phí liên quan.
5. Nếu báo cáo bắt buộc hoàn tất trước 20 phút thì chọn cách nào? — **B** là ứng viên đạt deadline, nếu các điều kiện khác (data quality, quota, cost) đều được kiểm tra.

### Câu hỏi tự kiểm tra

1. **Serverless Spark có cần tạo cluster trước không?** — Không đối với serverless batch.
2. **Đường CLI hiện hành cho batch là gì?** — `gcloud dataproc batches submit ...`.
3. **Khác nhau giữa batch và interactive session?** — Batch kết thúc khi xử lý xong; session phục vụ tác vụ khám phá tương tác và có vòng đời riêng.
4. **Runtime 3.x mặc định chạy dưới identity nào?** — Thường là **end-user credentials**, nếu không chọn service account credentials.
5. **Quyền submitter và execution SA có giống nhau?** — Không; submit permission khác data access của runtime.
6. **Auto scaling có bảo đảm chi phí luôn thấp nhất không?** — Không; còn min executors, partitions, skew và runtime/tier.
7. **Vì sao `collect()` rủi ro với dataset lớn?** — Kéo dữ liệu về RAM driver, có thể OOM.
8. **Batches API `SUCCEEDED` có chứng minh dữ liệu đúng không?** — Không; cần validation riêng.
9. **Lệnh submit trả về khi dùng `--async` có nghĩa batch xong chưa?** — Chưa; phải poll trạng thái.
10. **Có nên retry job ghi append sau timeout mà không kiểm tra batch đầu?** — Không; có thể tạo dữ liệu trùng.

## 11. Checklist triển khai production

| Hạng mục | Tiêu chí chấp nhận |
| --- | --- |
| **Workload fit** | Có lý do dùng Spark thay BigQuery SQL/Dataflow/Cloud Run Jobs, đã benchmark trên dataset thực tế. |
| **Runtime** | Dòng Spark/Python/connector hỗ trợ, pin major.minor, kế hoạch upgrade/EOL. |
| **IAM** | Submitter có quyền batches; execution identity/EUC/custom SA rõ ràng, chỉ đọc/ghi đúng buckets/datasets. |
| **Network** | Đúng region/subnet, firewall nội bộ, Private Google Access, DNS, NAT/PSC/perimeter nếu cần. |
| **Input** | Input snapshot/partition và schema rõ, có kiểm tra số hàng, corruption, duplicates và late events. |
| **Output** | Run-specific staging prefix, deterministic publish, validation, không append lặp ngoài ý muốn. |
| **Tài nguyên** | Min/max executors, shuffle, memory, partitions đã được đo; quota/IP/cost headroom hợp lý. |
| **Orchestration** | Lịch chạy có dependency, timeout, retry/backoff, idempotency, alert và người chịu trách nhiệm. |
| **Observability** | Batches API state, Spark UI, logs, data-quality signals, DCU-time và cost dashboard. |
| **Bảo mật** | Không có JSON keys trong code; dữ liệu/credentials được ẩn khỏi logs; kiểm tra VPC SC/CMEK nếu áp dụng. |
| **Khả năng phục hồi** | Có bài test FAILED, duplicate submit, partial output, driver crash và recovery/backfill. |
| **Chi phí/SLO** | So thời gian hoàn thành, compute DCU, shuffle và phí dịch vụ đích theo ngân sách được duyệt. |

### Hướng phát triển sau bài

Khi đã chạy được một batch an toàn, hãy nâng dần chất lượng pipeline thay vì chỉ tối đa throughput: triển khai **CI/CD cho mã và cấu hình**, schema compatibility, **data contracts**, lineage, CI tests với dữ liệu giả, theo dõi freshness, kiểm toán từng run và diễn tập failure/retry. Đối với streaming, thiết kế riêng checkpoint/state/late-data hoặc chọn Dataflow nếu đó là yêu cầu cốt lõi.

## 12. Tài liệu Google Cloud chính thức

- [Managed Service for Apache Spark serverless overview](https://docs.cloud.google.com/managed-spark/docs/serverless-overview): batch workloads, interactive sessions, mô hình vận hành và lịch chạy.
- [Submit an Apache Spark batch workload](https://docs.cloud.google.com/managed-spark/docs/quickstarts/spark-batch): làm quen với Console/CLI, SparkPi và vòng đời batch.
- [gcloud dataproc batches submit pyspark](https://cloud.google.com/sdk/gcloud/reference/dataproc/batches/submit/pyspark): cú pháp `--batch`, `--region`, `--version`, `--subnet`, `--service-account`, `--properties` và `--async`.
- [Serverless runtime versions](https://docs.cloud.google.com/managed-spark/docs/concepts/versions/serverless-versions): Spark/Java/Python/connector versions, ngày hỗ trợ và khác biệt giữa các runtime.
- [Serverless IAM roles and permissions](https://docs.cloud.google.com/managed-spark/docs/concepts/iam-serverless): quyền batch, session, Viewer/Editor và execution roles.
- [Serverless service accounts](https://docs.cloud.google.com/managed-spark/docs/concepts/service-accounts-serverless): runtime trước 3.0 và 3.0+, end-user credentials và custom SA.
- [Serverless network configuration](https://docs.cloud.google.com/managed-spark/docs/concepts/network-serverless): subnet, internal IP, Private Google Access, NAT và VPC.
- [Autoscale workload resources](https://docs.cloud.google.com/managed-spark/docs/concepts/autoscaling-serverless): dynamic allocation, V1/V2, profiles và Spark properties.
- [Spark workload properties](https://docs.cloud.google.com/managed-spark/docs/concepts/spark-properties-serverless): CPU/RAM, tier, executor và shuffle controls theo runtime.
- [Monitor and troubleshoot batch workloads](https://docs.cloud.google.com/managed-spark/docs/guides/monitor-troubleshoot-batches): Spark UI, log, metrics và gỡ lỗi batch.
- [Troubleshoot batch creation failures](https://docs.cloud.google.com/managed-spark/docs/support/batch-session-creation-failures): IAM, subnet, quotas và driver setup.
- [Serverless Spark FAQ](https://docs.cloud.google.com/managed-spark/docs/faq-serverless): so sánh cluster/serverless, streaming và concurrency limits.
- [Managed Service for Apache Spark pricing](https://cloud.google.com/products/managed-service-for-apache-spark/pricing): DCUs, resource tiers, shuffle storage và thành phần giá.

**Kết luận:** chạy Spark theo nhu cầu trên Google Cloud nghĩa là **không cần quản lý cụm máy Spark thường trực**, nhưng vẫn phải quản lý đúng **runtime, execution identity, mạng, dữ liệu và workflow**. Một pipeline tốt không dừng ở trạng thái `SUCCEEDED`; nó phải đáp ứng **độ đúng dữ liệu, khả năng retry không nhân bản, deadline, quyền tối thiểu và tổng chi phí đo được**. Hãy bắt đầu từ batch nhỏ có input/output riêng, xác minh đầy đủ rồi mới tăng thông lượng bằng điều chỉnh executor, partitions và lịch chạy.
