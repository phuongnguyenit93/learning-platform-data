# Cloud Data Fusion và xây dựng luồng tích hợp dữ liệu

Một nền tảng thương mại điện tử ghi đơn hàng qua ứng dụng Java trên Cloud Run, lưu giao dịch vào Cloud SQL và xuất các tệp CSV hằng ngày sang Cloud Storage. Bộ phận phân tích muốn chuẩn hóa ngày, loại các bản ghi lỗi rồi nạp vào BigQuery lúc 02:00. Nếu tự viết nhiều cron jobs, nhóm phải tự duy trì kết nối, chuyển đổi schema, xử lý lỗi, lịch chạy và thông tin nguồn gốc dữ liệu.

**Cloud Data Fusion** là dịch vụ **tích hợp dữ liệu được quản lý**, xây dựng pipeline ETL/ELT bằng giao diện trực quan và các plugin nguồn, biến đổi, đích. Nó dùng nền tảng mở **CDAP** và thường thực thi batch pipelines trên các cụm **Managed Service for Apache Spark** (tài liệu cũ gọi Dataproc). Cloud Data Fusion giúp quản lý luồng tích hợp nhưng **không tự bảo đảm dữ liệu đúng, nạp đúng một lần hoặc không có chi phí lúc không chạy pipeline**.

Bài thuộc chương **Pipeline và xử lý dữ liệu** của mô-đun `CLOUD_PROVIDERS_GCP`. Kiến thức áp dụng cho các hệ thống Java/GCP đã học — project, IAM, VPC, Cloud Run, GKE, Cloud Storage, Pub/Sub, cơ sở dữ liệu — nhằm chọn giải pháp, bảo vệ nguồn dữ liệu, tự động hóa và theo dõi độ tin cậy/chi phí. Ví dụ dùng project lab và các dữ liệu đơn hàng **giả lập**, không xử lý PII thật.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **instance → namespace → pipeline → run** và phân biệt tầng thiết kế với tầng thực thi Spark.
2. Chọn **batch ETL, streaming pipeline, replication/CDC** theo mức độ trễ và nguồn dữ liệu.
3. Xây pipeline **Cloud Storage → kiểm tra/chuyển đổi → BigQuery** bằng Pipeline Studio và Wrangler.
4. Dùng **Preview, schema, error handling** để phát hiện lỗi trước khi deploy.
5. Dùng macros/runtime arguments để tái sử dụng pipeline và cấu hình lịch/chaining.
6. Thiết kế **idempotency**, kiểm tra số lượng bản ghi và xử lý rerun an toàn.
7. Cấp quyền service accounts, cấu hình VPC/Private Service Connect và không làm lộ secrets.
8. Theo dõi run logs/metrics/lineage và tính đầy đủ **hai loại chi phí: instance + execution**.

## 1. Cloud Data Fusion giải quyết bài toán nào?

Hãy phân biệt **luồng tích hợp** với ứng dụng xử lý giao dịch:

| Nhu cầu | Cloud Data Fusion có phù hợp? | Lý do |
| --- | --- | --- |
| Đọc GCS, làm sạch CSV, ghi BigQuery hằng ngày | **Có** | Plugins, Wrangler, lịch chạy, giám sát tập trung |
| Lấy dữ liệu từ JDBC/SaaS rồi nạp data warehouse | **Có**, nếu có plugin/driver tương thích | Hỗ trợ nguồn và đích đa dạng, có thể cần kết nối riêng |
| Replication một số database sang BigQuery | **Có thể**, qua Replication/CDC theo ma trận hỗ trợ | Khác batch snapshot/polling; phải kiểm tra nguồn, phiên bản và semantics |
| Xử lý sự kiện Pub/Sub liên tục | Có streaming plugins, nhưng cần cân nhắc **Dataflow** | SLA trễ, checkpoint, state, watermark và vận hành |
| Một lệnh SQL transform toàn bộ trong BigQuery | **Có thể không cần** Data Fusion | BigQuery scheduled query/Dataform thường đơn giản hơn |
| Chạy thuật toán Spark phức tạp tùy biến | Cân nhắc **Managed Service for Apache Spark** trực tiếp | Toàn quyền ứng dụng Spark và tuning |
| Orchestrate hàng chục tác vụ đa dịch vụ với dependencies | Cân nhắc **Cloud Composer/Workflows** | Data Fusion thiết kế transform, không thay mọi bộ điều phối |

**Không chọn công cụ chỉ vì có giao diện kéo-thả.** Đối chiếu schema/connector support, latency, data governance, kỹ năng đội ngũ và chi phí vận hành.

## 2. Kiến trúc: Studio khác engine thực thi

~~~mermaid
flowchart LR
    USER["Data engineer"] --> UI["Cloud Data Fusion Studio<br/>design, preview, deploy"]
    UI --> META["Instance / namespaces<br/>pipelines, configs, metadata"]
    META --> RUN["Pipeline run"]
    RUN --> SPARK["Managed Spark cluster<br/>customer project"]
    GCS[("Cloud Storage<br/>raw files")] --> SPARK
    DB[("Cloud SQL / SaaS<br/>nguồn tùy chọn")] --> SPARK
    SPARK --> BQ[("BigQuery<br/>staging / curated")]
    RUN --> OBS["Run logs / metrics / lineage"]
    SPARK --> OBS
~~~

- **Control/design plane:** Cloud Data Fusion instance với Studio, plugin catalog, namespaces, pipeline definitions, runtime preferences; các thành phần dịch vụ chạy trong **tenant project** do Google quản lý.
- **Execution plane:** batch pipeline được biên dịch thành jobs trên **Managed Service for Apache Spark**. Mặc định Cloud Data Fusion cấp cụm tạm trong **customer project** rồi xóa sau khi hoàn tất. Có thể chọn compute profile khác hoặc cụm định cấu hình trước theo tính năng.
- **Sources/sinks:** GCS, BigQuery, JDBC, Pub/Sub và các plugin khác. Một số sink BigQuery sử dụng **Cloud Storage làm khu vực trung gian**, nên execution identity phải có quyền phù hợp.
- **Metadata/lineage:** theo dõi cấu trúc và luồng dữ liệu khi plugin, region và cấu hình hỗ trợ; lineage không tự xác minh mọi giá trị nghiệp vụ.

### 2.1. Đừng nhầm các cấp cấu hình

| Thành phần | Phạm vi |
| --- | --- |
| **Instance** | Một triển khai Data Fusion, có **edition, region, public/private networking** |
| **Namespace** | Nhóm logic chứa pipelines, artifacts, preferences và cấu hình người dùng |
| **Pipeline** | Đồ thị sources → transformations → sinks, được lưu và deploy |
| **Plugin** | Khối chức năng tái sử dụng: source/transform/sink/action/error handler |
| **Compute profile** | Cách chọn hạ tầng Spark để thực thi |
| **Run** | Một lần chạy cụ thể, có thời gian, runtime arguments, logs/metrics và **RunID** |

**Một pipeline được deploy chưa có nghĩa dữ liệu đã nạp**. Kết quả phải được xác minh qua run status **và dữ liệu thật ở sink**.

## 3. Batch, streaming và replication: ba cách xử lý khác nhau

| Loại | Dữ liệu vào | Độ trễ | Điểm chú ý |
| --- | --- | --- | --- |
| **Batch** | Tệp theo ngày, JDBC snapshot, dữ liệu định kỳ | Phút/giờ | Rerun, backfill, partition, idempotent sink |
| **Streaming** | Pub/Sub/Kafka, event liên tục | Giây/phút tùy kiến trúc | Ordering, checkpoint, retry, late data, state, chi phí chạy liên tục |
| **Replication/CDC** | Log thay đổi nguồn DB (nguồn được hỗ trợ) | Gần thời gian thực theo cấu hình | Initial snapshot, log retention, schema evolution, update/delete semantics |

**CDC không đồng nghĩa chạy truy vấn `SELECT *` mỗi phút.** Replication cần hiểu khóa chính, cơ chế capture và đánh dấu offset. Tính năng/connector hỗ trợ phụ thuộc loại DB và phiên bản Cloud Data Fusion; đừng hứa mọi JDBC database đều có CDC.

Trong bài lab, dùng **batch** vì đơn giản và dễ kiểm chứng. Streaming có thể dùng Data Fusion khi phù hợp nhưng **không tự đạt exactly-once business effect** khi sink hoặc hệ thống ngoài có lỗi; luôn phân tích delivery/commit/retry semantics.

## 4. Thiết kế hợp đồng dữ liệu trước khi kéo thả

Nguồn giả lập: tệp CSV đơn hàng ngày `2026-11-19`.

~~~csv
order_id,sales_region,amount_vnd,order_date
o-1001,APAC,120000,2026-11-18
o-1002,EMEA,95000,2026-11-18
o-1003,APAC,-5000,2026-11-18
o-1004,APAC,50000,2026-11-18
~~~

**Hợp đồng đầu ra** của bảng `etl_lab.orders_stage`:

| Cột | Kiểu BigQuery | Quy tắc |
| --- | --- | --- |
| `order_id` | STRING | Không rỗng; khóa nghiệp vụ |
| `sales_region` | STRING | Giá trị được chuẩn hóa, ví dụ APAC/EMEA |
| `amount_vnd` | INT64 | Chuyển từ chuỗi/CSV; **phải lớn hơn 0** |
| `order_date` | DATE | Ngày ISO `YYYY-MM-DD` |

Kỳ vọng: **3 bản ghi hợp lệ**, một bản ghi `o-1003` không hợp lệ do tiền âm. Trong hệ thống thật, cần quy trình **quarantine/DLQ** cho bản ghi lỗi, không bỏ âm thầm. Nếu là doanh thu hoàn tiền, số tiền âm có thể là **hợp lệ**; quy tắc ở đây chỉ đúng cho loại sự kiện `OrderCreated` được giả định.

**Bảo mật:** chỉ dùng mã đơn giả, không đưa tên/email/địa chỉ khách thật vào sample hoặc log.

## 5. Preflight: API, region, edition, tài khoản

Điều kiện: project lab đã bật billing, người thực hiện có quyền quản trị tài nguyên được duyệt, Cloud Storage/BigQuery/Managed Service for Apache Spark APIs và mạng đã được cấu hình khi cần. Mọi lệnh `create` dưới đây là **thay đổi thật, có thể phát sinh phí**.

Trước tiên dùng lệnh **chỉ đọc**:

~~~bash
gcloud auth list
gcloud config get-value project

gcloud beta data-fusion instances list \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud beta data-fusion operations list \
  --project=PROJECT_ID \
  --location=asia-southeast1

bq ls --project_id=PROJECT_ID
~~~

`gcloud beta data-fusion` là nhóm lệnh **beta** đang được tài liệu Cloud SDK mô tả; nên kiểm tra `--help` với phiên bản CLI đã cài. Console có thể được dùng thay CLI.

### 5.1. Chọn edition

| Edition | Tình huống điển hình | Cần cân nhắc |
| --- | --- | --- |
| **Developer** | Thử nghiệm, học tập, prototype nhỏ | Khả năng chịu tải/đồng thời hạn chế |
| **Basic** | Sandbox, PoC, khối lượng vừa phải | Không có RBAC granular như Enterprise |
| **Enterprise** | Nhiều nhóm, pipeline quan trọng, phân quyền chi tiết | **RBAC**, phí quản trị cao hơn |

**Edition được chọn khi tạo instance và không thể đổi trực tiếp**. Muốn chuyển edition cần quy trình tạo instance/migrate khác theo tài liệu. Cấu hình **private instance** dùng private connectivity; Google Cloud khuyến nghị Private Service Connect (PSC) cho kiến trúc cần ranh giới mạng mạnh.

### 5.2. Tạo instance lab — chỉ khi chưa có

~~~bash
# Gây chi phí; kiểm tra project và quyền trước khi chạy.
gcloud services enable \
  datafusion.googleapis.com \
  dataproc.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com \
  --project=PROJECT_ID

gcloud beta data-fusion instances create df-orders-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --edition=basic \
  --enable_stackdriver_logging
~~~

Ví dụ dùng **public/basic lab** để đơn giản hóa; **production nên đánh giá private instance/PSC, RBAC và network controls** thay vì sao chép mặc định. Tạo instance cần thời gian, quota và service account permissions; khi xong dùng **Cloud Data Fusion → Instances → View Instance** để mở Studio.

**Không xóa và tạo lại instance chỉ để thử pipeline**: xóa instance làm mất pipeline definitions/config/metadata của instance và không thể khôi phục trực tiếp.

## 6. IAM: người thiết kế khác tài khoản chạy Spark

Cloud Data Fusion thường liên quan hai danh tính:

- **Cloud Data Fusion API service agent** (Google-managed, design/control plane), cần role service agent dành riêng, ví dụ `roles/datafusion.serviceAgent`. **Không cấp role service agent cho người dùng hay app thường.**
- **Execution-time service account** của cụm Spark, theo mặc định có thể là Compute Engine default SA. Khuyến nghị dùng **user-managed service account** và cấp quyền nhỏ nhất theo nguồn/đích.

Ví dụ ma trận quyền theo phạm vi:

| Thành phần | Quyền cần xem xét |
| --- | --- |
| Data Fusion instance admin | `roles/datafusion.admin` hoặc quyền tương đương trên phạm vi instance/project |
| Execution identity chạy Data Fusion/Spark | `roles/datafusion.runner`, quyền Spark cluster tương ứng theo cấu hình |
| GCS raw bucket | `storage.objects.get/list` cho file nguồn |
| GCS temporary/staging bucket | Quyền đọc/ghi/xóa objects mà plugin Spark/BigQuery sink cần |
| BigQuery job project | `bigquery.jobs.create` |
| BigQuery target dataset | Quyền tạo bảng/ghi dữ liệu (`bigquery.tables.create/updateData`) theo yêu cầu |
| Cloud SQL/JDBC nguồn | Network route + DB user read-only, driver/credential phù hợp |
| Pipeline developer | Chỉ quyền thiết kế/deploy theo instance/namespace; không cần mặc định Viewer toàn bộ PII |

`roles/datafusion.runner` **không tự cấp** quyền đọc file GCS hay ghi BigQuery. Quyền Spark cluster/dataproc worker và role cụ thể còn tùy **compute profile, project và phiên bản dịch vụ**; xác minh theo lỗi permission từ runtime.

Trong **Enterprise RBAC**, phân quyền namespace/application/plugin theo vai trò; namespace chỉ là **phân nhóm logic**, không phải boundary bảo mật mạnh thay cho project/VPC/IAM.

## 7. Lab: chuẩn bị input GCS và BigQuery

**Chỉ sử dụng project lab.** Tên bucket phải **duy nhất toàn cầu**, thay hậu tố `UNIQUE` bằng chuỗi thật. Tất cả tài nguyên nên cùng vùng `asia-southeast1` để tránh lỗi location/egress không mong muốn.

Tạo `orders.csv` trên máy lab:

~~~bash
cat > orders.csv <<'CSV'
order_id,sales_region,amount_vnd,order_date
o-1001,APAC,120000,2026-11-18
o-1002,EMEA,95000,2026-11-18
o-1003,APAC,-5000,2026-11-18
o-1004,APAC,50000,2026-11-18
CSV
~~~

Tạo hai bucket (raw và temporary staging) cùng dataset:

~~~bash
gcloud storage buckets create gs://PROJECT_ID-df-raw-UNIQUE \
  --project=PROJECT_ID --location=asia-southeast1

gcloud storage buckets create gs://PROJECT_ID-df-temp-UNIQUE \
  --project=PROJECT_ID --location=asia-southeast1

gcloud storage cp orders.csv \
  gs://PROJECT_ID-df-raw-UNIQUE/input/orders.csv

bq --location=asia-southeast1 mk --dataset \
  PROJECT_ID:etl_lab
~~~

Nếu resources đã tồn tại, **kiểm tra owner, location, permission và không ghi đè**. Phân quyền raw bucket đọc và temp bucket đọc/ghi cho execution identity; người thiết kế Studio không nhất thiết là principal đọc/ghi data trong Spark job.

Tạo **bảng stage** trống bằng BigQuery Studio (đổi `PROJECT_ID`; xử lý tại `asia-southeast1`):

~~~sql
CREATE TABLE IF NOT EXISTS `PROJECT_ID.etl_lab.orders_stage` (
  order_id STRING,
  sales_region STRING,
  amount_vnd INT64,
  order_date DATE
);
~~~

Tên bảng trong câu SQL cần dấu backtick như ví dụ; chọn **một dataset lab riêng** vì sink có thể ghi thêm hoặc thay đổi schema theo cấu hình. Không dùng `CREATE OR REPLACE` trên dữ liệu thật.

## 8. Thiết kế pipeline trên Pipeline Studio

Trong Console: **Cloud Data Fusion → Instances → View Instance → Studio → Pipeline Design**. Tạo **Batch pipeline** tên `orders_gcs_to_bq_lab` trong namespace lab thích hợp.

~~~mermaid
flowchart LR
    SRC["Cloud Storage Source<br/>orders.csv"] --> PARSE["CSV parse / schema"]
    PARSE --> VALID["Wrangler + Filter<br/>amount_vnd > 0"]
    VALID --> SINK["BigQuery Table Sink<br/>orders_stage"]
    VALID -. "invalid" .-> BAD["Quarantine / error sink<br/>khi cấu hình"]
~~~

Các bước:

1. **Source: Cloud Storage** — chọn path `gs://PROJECT_ID-df-raw-UNIQUE/input/orders.csv`, format **CSV**, encoding UTF-8 và **Use first row as header = true**. Plugin có thể cần schema rõ nếu suy diễn kiểu chưa đúng.
2. **Parse / Schema** — xác nhận bốn cột. `amount_vnd` phải là **long/int** và `order_date` là **date** ở đầu ra; nếu source đang đọc tất cả thành STRING, chuyển kiểu trong Wrangler/Projection trước sink.
3. **Wrangler** — chuẩn hóa whitespace, parse/convert kiểu, kiểm tra giá trị, tạo recipe. Với ví dụ, lọc những dòng có `amount_vnd <= 0` hoặc ghi chúng sang một **error path** có quyền truy cập hạn chế.
4. **BigQuery Table sink** — chọn đúng project, dataset `etl_lab`, table `orders_stage`, schema khớp bốn trường, staging Cloud Storage bucket. Kiểm tra **write mode** (append/overwrite hoặc hành vi plugin đang dùng) trước khi chạy.
5. **Validate** từng plugin và kết nối giữa stages; kiểm tra field name, type, plugin configuration và execution identity.
6. **Preview** để thử dữ liệu/sample, đọc lỗi, sửa khi còn Draft.
7. **Deploy → Run** trong project lab; theo dõi `Provisioning → Starting → Running → Succeeded` rồi xác minh bảng BigQuery.

**Không có một cấu hình plugin duy nhất cho mọi version:** tên trường, lựa chọn CSV parser, BigQuery sink và UI có thể thay đổi. Nếu output schema không tương thích, **không chạy job bằng cách bỏ validation**, hãy xem docs plugin và sửa recipe/sink.

## 9. Wrangler, Preview và chất lượng dữ liệu

**Wrangler** giúp xây chuỗi **directives** qua UI để parse, đổi tên, chuyển kiểu, filter hoặc chuyển đổi một tập dữ liệu mẫu. Một **recipe** là tập directives; khi đưa vào pipeline, logic được áp cho luồng dữ liệu thực.

Lưu ý:

- **Preview thường chỉ lấy 100 bản ghi đầu** từ source theo thiết kế Studio; sample sạch **không chứng minh toàn bộ file không lỗi**.
- Sau khi deploy, batch pipeline xử lý **toàn bộ phần dữ liệu được source chọn**, không chỉ preview.
- Chuyển `"abc"` thành INT64, ngày sai định dạng hoặc thay đổi tên cột có thể gây **parse error / pipeline failure**; cấu hình error handlers/quarantine thay vì âm thầm bỏ dòng.
- **Error sink** phải lưu `source_file`, `record_id`, `reason` và thời điểm xử lý nếu plugin hỗ trợ; không lưu payload PII hoặc credentials nguyên văn.
- Đặt **data quality gates**: số hàng vào = số hàng hợp lệ + số hàng lỗi (nếu không có intentional drops); kiểm tra uniqueness, non-null, currency/range.

### 9.1. Dữ liệu mong đợi của lab

| order_id | sales_region | amount_vnd | order_date | Kết quả |
| --- | --- | ---: | --- | --- |
| o-1001 | APAC | 120000 | 2026-11-18 | Hợp lệ |
| o-1002 | EMEA | 95000 | 2026-11-18 | Hợp lệ |
| o-1003 | APAC | -5000 | 2026-11-18 | Loại/quarantine theo quy tắc lab |
| o-1004 | APAC | 50000 | 2026-11-18 | Hợp lệ |

**Kỳ vọng một lần chạy:** ba rows trong `orders_stage` nếu dùng bảng trống và không ghi trùng. Nếu thấy bốn rows, filter chưa áp. Nếu thấy không có rows, kiểm tra run logs, schema, source path và sink errors.

## 10. Xác minh sink bằng BigQuery SQL

Sau khi run báo `Succeeded`, thực thi query **chỉ đọc**:

~~~sql
SELECT
  order_id, sales_region, amount_vnd, order_date
FROM `PROJECT_ID.etl_lab.orders_stage`
ORDER BY order_id;

SELECT
  COUNT(*) AS rows_loaded,
  COUNTIF(amount_vnd <= 0 OR amount_vnd IS NULL) AS invalid_amount,
  COUNT(DISTINCT order_id) AS distinct_orders,
  SUM(amount_vnd) AS total_vnd
FROM `PROJECT_ID.etl_lab.orders_stage`;
~~~

Kết quả sau **một lần chạy đúng**:

~~~text
rows_loaded = 3
invalid_amount = 0
distinct_orders = 3
total_vnd = 265000
~~~

Nếu bảng đã có dữ liệu từ run trước, những con số này sẽ khác. **Không kết luận job sai** trước khi xác nhận bảng stage đang trống hoặc được tạo riêng cho lượt kiểm thử.

Nếu cần bảo đảm một nhóm dữ liệu có **schema chính xác**, quản lý schema trong source control (DDL) và dùng môi trường staging để kiểm tra thay đổi trước khi chạy production.

## 11. Retry và nạp lại: “pipeline Succeeded” không có nghĩa exactly-once

Có thể có lỗi sau khi một sink đã ghi thành công nhưng run chưa kịp cập nhật trạng thái, hoặc người vận hành chủ động **rerun** cùng input. Nếu sink ở chế độ **append**, các hàng có thể xuất hiện **hai lần**.

~~~text
Run 1: 3 rows ghi vào orders_stage → thành công
Run 2: đọc cùng file → append thêm 3 rows

orders_stage: 6 rows, nhưng chỉ 3 order_id nghiệp vụ.
~~~

**Nguyên tắc:** phân biệt **at-least-once execution/retry** với **exactly-once business effect**. Dùng một trong các chiến lược:

- **Overwrite partition / replace snapshot** khi toàn bộ tập dữ liệu có thể dựng lại, vùng ghi được kiểm soát.
- **Landing/staging + BigQuery MERGE** theo khóa nghiệp vụ.
- **Run ID / source object generation / watermark** để nhận diện input đã xử lý.
- **Deduplicate** theo primary key + event version/timestamp có thứ tự rõ.
- **Checkpoint/offset** cho streaming/CDC khi plugin hỗ trợ, kết hợp sink idempotent.

Ví dụ đơn giản để **chống duplicates khi đưa từ stage vào curated table**, không dùng trực tiếp làm thuật toán CDC:

~~~sql
CREATE TABLE IF NOT EXISTS `PROJECT_ID.etl_lab.orders_curated` (
  order_id STRING,
  sales_region STRING,
  amount_vnd INT64,
  order_date DATE
);

MERGE `PROJECT_ID.etl_lab.orders_curated` AS T
USING (
  SELECT order_id, sales_region, amount_vnd, order_date
  FROM `PROJECT_ID.etl_lab.orders_stage`
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY order_id
    ORDER BY order_date DESC, amount_vnd DESC
  ) = 1
) AS S
ON T.order_id = S.order_id
WHEN MATCHED THEN UPDATE SET
  sales_region = S.sales_region,
  amount_vnd = S.amount_vnd,
  order_date = S.order_date
WHEN NOT MATCHED THEN
  INSERT (order_id, sales_region, amount_vnd, order_date)
  VALUES (S.order_id, S.sales_region, S.amount_vnd, S.order_date);
~~~

Với lab, dù stage có 6 rows sau rerun, curated vẫn có **3 order IDs**. Trong production, lựa chọn bản “mới nhất” phải dựa vào **event_version/updated_at đáng tin cậy**; dùng `amount_vnd DESC` ở đây chỉ để xử lý hòa khi dữ liệu demo giống nhau, **không phù hợp để phân định cập nhật nghiệp vụ thật**.

**Không chạy hai MERGE jobs lên cùng target một cách mù quáng**: cần orchestration, idempotency và xử lý job concurrency. Bảng stage tăng mãi cũng cần retention/partition và cleanup policy.

## 12. Macros và runtime arguments giúp tái sử dụng

Thay vì tạo một pipeline cho từng file/ngày, dùng **macro** trong thuộc tính plugin có ký hiệu hỗ trợ macro (`M`), ví dụ:

~~~text
Cloud Storage Source Path:
  ${input_path}

BigQuery Sink Table:
  ${target_table}

Một run với:
  input_path=gs://PROJECT_ID-df-raw-UNIQUE/input/orders.csv
  target_table=orders_stage
~~~

Macro là **placeholder thay thế khi chạy**; syntax thực tế là `${input_path}` (không có ký tự khoảng trắng giữa `$` và `{`). Có thể dùng **preferences** để lấy cấu hình dùng chung, **runtime arguments** cho file/table theo ngày.

Đối với secrets, dùng **secure macro** / secure store theo plugin:

~~~text
${secure(db_password)}
~~~

Không đưa **password thật** vào runtime arguments thường, Git repository, pipeline JSON hoặc Logs Explorer. Khi dùng JDBC, đặt connection/credential trong **secure keys/Secret Manager integration** theo khả năng phiên bản, cấp quyền chính xác cho execution identity.

### 12.1. Định danh run để dễ truy vết

Một batch run nên có:

- `run_id` để liên kết logs, output và incident.
- `input_path`, nếu GCS thì cân nhắc **object generation** để phân biệt file bị ghi đè.
- `source_system`, `source_extract_time` và `schema_version`.
- `rows_read, rows_valid, rows_quarantined, rows_written`.
- `start_time, end_time, compute_profile, pipeline_version`.

**Không tự đặt `run_id` bằng timestamp bên trong mỗi stage** khiến các thành phần trong cùng run không đối chiếu được. Truyền một ID ổn định cho toàn bộ pipeline invocation.

## 13. Lập lịch và điều phối nhiều pipelines

Sau khi **Deploy**, Data Fusion Studio hỗ trợ:

- **Run:** chạy thủ công.
- **Schedule:** chạy batch định kỳ theo lịch.
- **Incoming triggers:** kích hoạt pipeline downstream dựa vào trạng thái hoàn tất của upstream.
- **REST API/Git-backed lifecycle:** phục vụ CI/CD và orchestration ngoài Studio.
- **Cloud Composer**: phù hợp khi phải điều phối nhiều Data Fusion pipelines, BigQuery jobs, Cloud Run tasks hoặc hệ thống ngoài.

Ví dụ luồng xử lý:

~~~mermaid
flowchart TD
    A["02:00 - Data Fusion raw → staging"] --> B{"Pipeline succeeded + quality gate?"}
    B -->|Yes| C["BigQuery MERGE → curated"]
    B -->|No| D["Alert + quarantine + stop downstream"]
    C --> E["BI / report"]
~~~

**Cảnh báo:** schedule không tự chứng minh file nguồn đã tới. Nếu nguồn ngày mới chưa có, pipeline có thể thất bại hoặc xử lý file cũ. Dùng upstream dependency/file sensor theo orchestration được duyệt và kiểm tra ngày/generation của object.

### 13.1. CI/CD cho pipeline

Quản lý **pipeline definition/plugin versions/schema/macros** trong source control. Quy trình đề xuất:

1. Dùng namespace/project **dev** để thiết kế và Preview.
2. Kiểm thử dữ liệu sạch, lỗi, schema đổi, thiếu credentials, rerun, duplicate source.
3. Review plugin packages và cấu hình network/IAM.
4. Deploy phiên bản đã duyệt sang staging, sau đó production.
5. Dùng **runtime arguments/secrets**, không hard-code môi trường trong pipeline JSON.
6. Lưu version, RunID, kết quả chất lượng; có rollback pipeline definition và target tables.

Việc sửa pipeline đã deploy có thể tạo **runtime version mới**; không nên kết luận người dùng đang chạy đúng phiên bản chỉ từ tên pipeline.

## 14. Kết nối an toàn: VPC, PSC, Cloud SQL và nguồn bên ngoài

~~~mermaid
flowchart LR
    UI["Studio instance<br/>private networking"] --> PSC["PSC / VPC connectivity"]
    PSC --> EXEC["Spark execution<br/>customer project/VPC"]
    EXEC --> SQL[("Private Cloud SQL")]
    EXEC --> GCS[("Cloud Storage")]
    EXEC --> BQ[("BigQuery")]
    EXEC -. "khi được phép" .-> ONPREM["On-prem qua VPN / Interconnect"]
~~~

Nếu xử lý dữ liệu nhạy cảm:

- Đánh giá **private Data Fusion instance**, Google Cloud khuyến nghị **Private Service Connect**; có thể có VPC peering tùy kiến trúc/phiên bản.
- Cụm Spark thực thi cũng cần **đường mạng riêng** tới nguồn: VPC, subnet, firewall, DNS, private IP/PSC và **Cloud NAT/Google APIs access** khi cần.
- JDBC tới Cloud SQL cần **DB authentication** riêng (username/secret hoặc IAM DB auth theo engine) ngoài quyền Google Cloud IAM và routing.
- Giữ nguồn/đích ở region phù hợp để tránh rủi ro **data residency** và phí egress.
- Không đặt public IP vào allowlist rộng chỉ để vượt lỗi permission; bảo vệ secrets và log.
- Nếu tổ chức dùng **VPC Service Controls**, kiểm tra perimeter cho Data Fusion, Spark, GCS, BigQuery và dịch vụ phụ trợ theo hỗ trợ.

**IAM điều khiển quyền dùng API; VPC/PSC điều khiển đường mạng; DB credentials điều khiển truy cập dữ liệu trong database.** Ba lớp cần kiểm chứng riêng.

## 15. Compute profiles, Spark tuning và pushdown

Default **Spark execution** giúp mở rộng xử lý nhưng có thời gian khởi tạo cluster và phí máy.

| Vấn đề | Hướng kiểm tra |
| --- | --- |
| Pipeline nhỏ nhưng mất nhiều phút chờ | Thời gian provision/start Spark cluster; cân nhắc xử lý ngay bằng BigQuery SQL |
| Spark executor OOM | Schema, skew, memory/executor configs, số partitions |
| Một source/file quá lớn | Partitioning/splits, định dạng Parquet/Avro, parallel reads |
| Join/GroupBy chậm | Shuffle, skew keys, số workers, pushdown khi được hỗ trợ |
| BigQuery sink chậm | GCS staging, BigQuery load jobs, quota, region, schema |
| Cụm cluster tạo trong project sai | Compute profile/project, runtime identity, network |
| Streaming không đạt latency | Checkpoint/state/backpressure hoặc cân nhắc Dataflow |

Một số transformations có thể **pushdown sang BigQuery** nếu nguồn/đích/transform plugins và cấu hình tương thích. Pushdown giảm tính toán Spark nhưng chuyển một phần chi phí sang **BigQuery slots/bytes processed**; phải **benchmark** trước/sau, không mặc định bật là rẻ hơn.

**Không tăng worker nodes mù quáng:** lỗi thực sự có thể là driver JVM, một key nóng, bad input, quota BigQuery hoặc permission. Theo dõi CPU, executor memory, stage duration và thời gian provisioning riêng.

## 16. Logs, metrics, lineage và cảnh báo

Trong **Data Fusion Studio → deployed pipeline → Summary / Run history**, lấy **RunID**, trạng thái, số rows và thời gian từng stage. Mở **Logs**, chọn mức `Error/Warning/Info/Debug`; khi cần xem **advanced logs** để chẩn đoán cluster/Spark.

Với **Cloud Data Fusion 6.11+**, pipeline/service logs có thể xem qua **Cloud Logging** theo tính năng và cấu hình instance; cluster logs còn có đường xem theo resource tương ứng. Một số version cũ cần bật **Dataproc/Managed Spark Cloud Logging** rõ ràng. Không giả định mọi log tự xuất hiện nếu logging chưa được cấu hình.

| Tín hiệu | Kiểm soát |
| --- | --- |
| Pipeline run `Failed` / `Succeeded` | Alert theo run status và sự kiện lịch |
| Run duration & provisioning time | Phân biệt khởi tạo Spark với xử lý data |
| `rows_read`, `rows_written` | Đối chiếu tính đầy đủ và duplicate |
| `rows_quarantined` / error ratio | Data quality gate, không che lỗi schema |
| Stage latency/records per second | Xác định bottleneck plugin/source/sink |
| Spark CPU/memory, cluster/job logs | OOM, driver/executor failures, quota |
| BigQuery load/query jobs, GCS bytes | Sink behavior và billing |
| Metadata/lineage | Tác động của đổi schema/nguồn, hỗ trợ tìm nguồn lỗi |
| Cost by SKU, RunID/time window | Đánh giá TCO của từng pipeline |

**Khi một run báo Succeeded nhưng BigQuery không đủ hàng**, đừng chỉ xem status: có thể filter sai, source path chọn nhầm hoặc thiếu data quality gate. Truy vấn SQL ở mục 10 là bước xác minh bắt buộc.

### 16.1. Quy trình xử lý lỗi thực tế

1. Chốt **instance, namespace, pipeline name/version, RunID, project và giờ UTC**.
2. Xem **stage lỗi** trong Studio. Từ phiên bản 6.11, có thể xem phân loại lỗi theo category/reason/message.
3. Đọc pipeline logs và advanced/Spark logs khi cần.
4. Xác định lỗi thuộc **source/credentials/network/schema/transform/sink/quota**.
5. Sửa nguyên nhân ở dev/staging, chạy lại **idempotently** với input ổn định.
6. So input/output/error counts, độ trễ, chi phí và thông báo incident/owner.

Không log mật khẩu JDBC hoặc payload PII để debug. Thông tin lỗi cần đủ correlation ID nhưng không làm lộ bí mật.

## 17. Chi phí Cloud Data Fusion: không chỉ là lúc pipeline Run

Theo bảng giá công bố, giá Data Fusion chia làm **phát triển/quản lý instance** và **thực thi pipelines**:

| Thành phần | Cách phát sinh |
| --- | --- |
| **Data Fusion instance** | Tính theo thời gian từ khi **tạo** đến khi **xóa**, kể cả không chạy pipeline |
| **Execution Spark** | Managed Service for Apache Spark/Compute Engine VMs, disks theo cấu hình, thời gian chạy |
| **Cloud Storage** | Raw/staging files, reads/writes, lưu trữ |
| **BigQuery** | Storage, load/queries và quota/slots theo mô hình thanh toán |
| **Network** | Egress, VPC/PSC/Cloud NAT/Interconnect khi có |
| **Logging/Monitoring** | Log ingestion/storage, monitoring theo dịch vụ |
| **Nguồn/đích khác** | Cloud SQL, API SaaS, Pub/Sub, connector resources |

Tại thời điểm kiểm tra bảng giá (2026), edition có mức tham khảo **Developer $0.35/giờ, Basic $1.80/giờ, Enterprise $4.20/giờ** theo USD; **Basic có 120 giờ đầu/tháng/tài khoản miễn phí** theo điều kiện bảng giá. **Đừng coi 120 giờ này bao gồm Spark/VM/BigQuery hoặc là miễn phí toàn bộ account**. Giá, chính sách và tiền tệ hóa đơn có thể đổi; dùng [bảng giá Data Fusion](https://cloud.google.com/data-fusion/pricing) và Billing SKU hiện hành trước quyết định.

Ví dụ tính chi phí development sau khi đã hết giờ miễn phí Basic:

~~~text
Một Basic instance chạy 24 giờ
  Development = 24 × $1.80 = $43.20 (tham khảo)

Pipeline chạy mỗi giờ, 15 phút/run:
  24 runs × 0.25 giờ = 6 giờ chạy Spark cluster

Tổng = Data Fusion instance charge
     + Managed Spark/Compute Engine/disks
     + GCS/BigQuery/network/logging...
~~~

Không dùng $43.20 làm **tổng chi phí ETL**. Instance vẫn bị tính phí khi idle; Spark cluster tạm không làm instance ngừng tính tiền. Cloud Billing budget alerts **không tự dừng nguồn lực hay khóa chi tiêu**.

## 18. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không tạo được Data Fusion instance | API, quota, service agent, region/edition | Kiểm tra IAM/operations và quota |
| Studio mở được nhưng Spark cluster không tạo | Runtime SA/`datafusion.runner`, Spark permission, compute quota | Kiểm tra Cloud Logging, IAM, quotas |
| Không đọc được GCS | Path, bucket, object quyền, region/connector | Kiểm tra source path và execution identity |
| JDBC source timeout | VPC/PSC/DNS, firewall, DB auth/driver | Phân biệt mạng với DB credentials |
| Wrangler Preview đúng, Run thất bại | Preview chỉ sample, schema lỗi ở hàng khác | Dùng error handler/quarantine, kiểm toàn file |
| BigQuery sink báo access denied | Thiếu jobUser/dataset data permissions, staging bucket | Kiểm tra quyền Spark execution identity |
| Load BQ sai schema | Type/date parsing, null, field mapping | Validate schema giữa source/transform/sink |
| Rerun tạo duplicates | Append sink, không có dedupe/idempotency | MERGE theo event key, run ID và backfill plan |
| Pipeline quá chậm khi ít dữ liệu | Spark startup chiếm thời gian | Cân nhắc BigQuery SQL/simpler service |
| Spark OOM/shuffle | Skew/partition size, memory | Tối ưu keys, memory, executor và dataset |
| Succeeded nhưng thiếu hàng | Filter loại nhầm hoặc source glob sai | So record counts, quality gate và query BQ |
| Hóa đơn cao khi không có job | Data Fusion instance vẫn chạy | Xem instance hours, xóa lab có phê duyệt |

**Không chữa lỗi bằng cách cấp Owner/Editor toàn project hoặc mở public DB.** Tìm chính xác principal, quyền, route và stage lỗi.

## 19. Tình huống tổng hợp: dữ liệu đơn hàng đa nguồn

Nhóm Commerce có: Java Order API trên Cloud Run, Cloud SQL PostgreSQL, file CSV của đối tác ở GCS, và dashboard trên BigQuery. Mong muốn:

- Nạp file mới mỗi đêm, làm sạch và đối soát số hàng.
- Đồng bộ thêm cập nhật đơn từ Cloud SQL gần thời gian thực khi cần.
- Tách PII khỏi dataset analyst và giữ lineage.
- Không sinh đơn trùng khi retry/backfill.

**Đề xuất:**

~~~mermaid
flowchart LR
    GCS["Partner CSV in GCS"] --> DF["Data Fusion batch<br/>parse + quality"]
    SQL[("Cloud SQL")] -. "CDC nếu tương thích" .-> CDC["Replication / Datastream"]
    DF --> STAGE[("BigQuery staging")]
    CDC --> STAGE
    STAGE --> MERGE["MERGE / dedupe / audit"]
    MERGE --> CURATED[("BigQuery curated")]
    CURATED --> BI["BI dashboards"]
~~~

Quyết định theo bước:

1. Thiết kế schema, business keys, quyền đọc/ghi và chất lượng data.
2. Thử **một batch pipeline lab** với ba valid rows, một quarantined row.
3. Thêm runtime arguments, partition theo ngày và khóa `order_id`/`event_version`.
4. Đặt staging + MERGE idempotent, tránh cập nhật trực tiếp curated từ hai nguồn không có thứ tự.
5. Với CDC, so sánh **Cloud Data Fusion replication** với **Datastream + Dataflow/BigQuery** theo nguồn được hỗ trợ, độ trễ, DDL và chi phí.
6. Đặt monitoring run-level/record-level, audit IAM và lineage.
7. Đánh giá TCO trước khi tăng edition/cluster size.

**Không để CSV partner có thể ghi đè đơn giao dịch chuẩn** nếu chưa có quy tắc ưu tiên nguồn/version và đối soát nghiệp vụ.

## 20. Bài tập thực hành và tự kiểm tra

**Bài 1 — Pipeline GCS → BigQuery.** Xây pipeline theo mục 7–10.

*Đạt:* một run từ file lab tạo **3 rows hợp lệ**, tổng `265000`, lỗi âm được giải thích/quarantine.

**Bài 2 — Rerun.** Chạy lại input khi sink `append`, so `orders_stage` và `orders_curated` sau MERGE.

*Đạt:* stage có thể tăng 6 rows; curated **chỉ 3 order IDs**. Giải thích vì sao không nên đặt `MERGE` theo giá trị tiền lớn nhất trong production.

**Bài 3 — Runtime macro.** Đổi `input_path` sang file khác trong cùng pipeline mà không tạo pipeline mới.

*Đạt:* mỗi run ghi đúng nguồn, log có `run_id`/`input_path`; không đưa secrets vào argument thường.

**Bài 4 — IAM.** Runtime SA đọc được GCS nhưng không ghi được BigQuery. Nêu kiểm tra.

*Đáp án:* `bigquery.jobs.create` tại job project, quyền tạo/ghi table tại dataset, staging bucket và đúng execution identity.

**Câu 5.** Pipeline được deploy đã chạy và nạp dữ liệu chưa?

*Đáp án:* Chưa. Cần trigger/run, quan sát run status và xác minh sink.

**Câu 6.** Cloud Data Fusion dùng Spark làm engine batch mặc định; có nghĩa compute miễn phí không?

*Đáp án:* Không. Cụm Spark/VM/disk phát sinh phí riêng với Data Fusion instance.

**Câu 7.** Preview thấy đủ 100 hàng mẫu, có bảo đảm cả dataset sạch không?

*Đáp án:* Không. Preview chỉ mẫu; kiểm tra quality gates trên toàn dữ liệu.

**Câu 8.** Batch và CDC giống nhau không?

*Đáp án:* Không. Batch chạy snapshot/tệp định kỳ; CDC dựa trên thay đổi nguồn DB với điều kiện nguồn/connector.

**Câu 9.** Một pipeline được chạy lại sau lỗi ACK/timeout có bảo đảm không nạp trùng không?

*Đáp án:* Không. Cần sink idempotency/MERGE, checkpoint/keys.

**Câu 10.** Namespace có thay thế IAM và tách project cho dữ liệu mật không?

*Đáp án:* Không. Namespace là nhóm logic; security boundary cần IAM/network/project controls.

**Câu 11.** Đặt Cloud SQL private IP nhưng execution Spark không có route tới VPC. Chỉ cấp DB Reader đủ chưa?

*Đáp án:* Chưa. Cần mạng và DB auth bên cạnh IAM.

**Câu 12.** Cloud Data Fusion Basic instance để idle 24 giờ có thể vẫn bị tính phí không?

*Đáp án:* Có, theo instance hours (trừ free hours đủ điều kiện). Không phụ thuộc việc pipeline có chạy.

**Câu 13.** Khi pipeline Succeeded nhưng rows thiếu, nên kiểm tra gì?

*Đáp án:* Source selection, Filter/Wrangler, error handling, row counts và query sink.

**Câu 14.** Một nhu cầu chỉ thực thi SQL hằng ngày trong BigQuery nên chọn Data Fusion mặc định?

*Đáp án:* Không. So sánh BigQuery scheduled query/Dataform vì có thể đơn giản/rẻ hơn.

## 21. Checklist trước production

- [ ] Xác định batch/streaming/CDC, SLA freshness và owner dữ liệu.
- [ ] Chọn Data Fusion thay vì Dataflow/BigQuery SQL/Composer dựa trên workload thực.
- [ ] Chọn edition/region, private VPC/PSC và compute profile đúng yêu cầu.
- [ ] IAM tách design-time service agent, execution SA, datasets/buckets/DB users.
- [ ] JDBC/credentials dùng secure storage; không hard-code secrets trong pipeline.
- [ ] Input schema, data quality rules, error quarantine và row reconciliation rõ ràng.
- [ ] Có idempotency/backfill/rerun plan; staging + curated được bảo vệ.
- [ ] Preview chỉ để phát hiện sớm; test toàn file và edge cases ở staging.
- [ ] Pipeline definitions, plugins, schema và runtime arguments được version hóa.
- [ ] Schedule/triggers có dependency/file readiness và quality gate.
- [ ] Theo dõi RunID, records in/out/error, latency, Spark errors và lineage.
- [ ] Đo CPU/memory/Spark startup/BigQuery bytes; tối ưu trước khi tăng cluster size.
- [ ] Billing tính đủ instance + Spark/VM/disk + GCS/BQ/network/logging.
- [ ] Có cleanup/retention cho staging files, run records và instances lab.
- [ ] Đã diễn tập input hỏng, mất IAM, source DB timeout, duplicate rerun và rollback.

## 22. Kết luận

**Cloud Data Fusion** giúp thiết kế và vận hành ETL/ELT bằng plugins và Studio, nhưng chất lượng pipeline chỉ được chứng minh khi **schema đúng, nguồn/đích có quyền hợp lệ, rerun an toàn, số liệu đối soát được và chi phí trong ngân sách**. Hãy bắt đầu với luồng **GCS → Wrangler/Filter → BigQuery**, rồi mới mở rộng macros, orchestration, CDC hoặc streaming khi có yêu cầu đo được.

Trong production, tách rõ **Data Fusion instance quản lý pipeline** với **Spark thực thi có tính phí riêng**, bảo vệ VPC/IAM/secrets, theo dõi RunID và sử dụng **staging + MERGE/idempotency** để không biến một sự cố retry thành báo cáo kinh doanh sai.

## Tài liệu tham khảo chính thức

- [Cloud Data Fusion: overview](https://cloud.google.com/data-fusion/docs)
- [Cloud Data Fusion: Studio overview](https://cloud.google.com/data-fusion/docs/concepts/studio-overview)
- [Cloud Data Fusion: Console, instance/edition/network](https://cloud.google.com/data-fusion/docs/concepts/console-overview)
- [Create a data pipeline quickstart](https://cloud.google.com/data-fusion/docs/create-data-pipeline)
- [Cloud Data Fusion plugin reference](https://cloud.google.com/data-fusion/plugins)
- [Parse files in Wrangler](https://cloud.google.com/data-fusion/docs/how-to/wrangler-parse-files)
- [Wrangler overview](https://cloud.google.com/data-fusion/docs/concepts/wrangler-overview)
- [Design reusable pipelines](https://cloud.google.com/data-fusion/docs/tutorials/reusable-pipeline)
- [Cloud Storage batch source](https://cloud.google.com/data-fusion/docs/how-to/configure-cloud-storage-batch-source)
- [Deploy and run pipelines](https://cloud.google.com/data-fusion/docs/concepts/deploy-and-run-pipelines)
- [Cloud Data Fusion service accounts and IAM](https://cloud.google.com/data-fusion/docs/access-control)
- [Security overview and private instances](https://cloud.google.com/data-fusion/docs/concepts/security)
- [Cloud Data Fusion networking](https://cloud.google.com/data-fusion/docs/concepts/networking)
- [View pipeline logs](https://cloud.google.com/data-fusion/docs/how-to/view-and-download-pipeline-logs)
- [View Cloud Data Fusion Cloud Logging logs](https://cloud.google.com/data-fusion/docs/how-to/view-datafusion-logs)
- [Troubleshoot Cloud Data Fusion](https://cloud.google.com/data-fusion/docs/troubleshoot)
- [Cloud Data Fusion pricing](https://cloud.google.com/data-fusion/pricing)
- [gcloud beta data-fusion instances](https://cloud.google.com/sdk/gcloud/reference/beta/data-fusion/instances)

