# Dataform và quản lý biến đổi SQL trong BigQuery

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Dataform** (quản lý mã SQL, phụ thuộc, kiểm thử và lịch chạy) với **BigQuery** (lưu trữ và thực thi SQL), cũng như với Dataflow/Beam.
2. Tổ chức **repository, development workspace, `workflow_settings.yaml`, SQLX, release configuration, workflow configuration** và các môi trường dev/prod.
3. Viết **declaration, table/view, incremental table và assertion**; dùng `${ref(...)}` tạo DAG, phát hiện lỗi dữ liệu và tránh tham chiếu bảng cứng.
4. Biên dịch, dry-run, chạy thử, phát hành có Git review và đặt lịch an toàn bằng **custom service account** cùng IAM tối thiểu.
5. Kiểm soát **độ đúng dữ liệu, lineage, location, chi phí BigQuery, quyền truy cập và rollback** theo một tình huống Java/Cloud Run/BigQuery.

## 1. Bối cảnh: SQL biến đổi dữ liệu cũng cần vòng đời phần mềm

Trong lộ trình **CLOUD_PROVIDERS_GCP**, Java/Spring Boot trên Cloud Run tạo đơn hàng; Cloud SQL lưu giao dịch; Pub/Sub/Dataflow chuyển sự kiện sang BigQuery. Nhóm dữ liệu cần tạo:

- Bảng **staging** chuẩn hóa sự kiện từ nguồn thô.
- Bảng **mart** tổng hợp doanh thu theo ngày và vùng.
- Kiểm thử ID không rỗng, không trùng và tiền không âm.
- Lịch chạy production, theo dõi thất bại và review thay đổi SQL.

Nếu mỗi nhà phân tích lưu một đoạn SQL riêng trong console rồi tự chạy theo lịch, ta dễ gặp **tham chiếu bảng sai, chạy sai thứ tự, lệch môi trường và không biết ai thay logic doanh thu**.

**Dataform** đưa các phép biến đổi BigQuery vào **mã có version**, tự dựng **dependency graph (DAG)**, sinh/điều phối SQL và quản lý assertions. **BigQuery vẫn là nơi thực thi SQL và lưu bảng**, nên Dataform không phải một database mới hay lớp compute tương đương Dremel/Dataflow workers.

~~~mermaid
flowchart LR
  APP["Cloud Run Java"] --> SRC["Pub/Sub / Dataflow / GCS"]
  SRC --> RAW["BigQuery raw_orders"]
  RAW --> STG["Dataform: staging SQLX"]
  STG --> MART["Dataform: revenue mart SQLX"]
  MART --> BI["Looker / BI / reporting"]
  TEST["Dataform assertions"] -. "Kiểm tra chất lượng" .-> STG
  TEST -. "Kiểm tra chất lượng" .-> MART
  GIT["Git + code review"] --> DF["Dataform repository / compilation / workflow"]
  DF -. "Lập kế hoạch và chạy SQL trong BigQuery" .-> STG
  DF -. "Lập kế hoạch và chạy SQL trong BigQuery" .-> MART
~~~

| Công cụ | Trách nhiệm chính | Không nên nhầm với |
|---|---|---|
| **BigQuery** | Storage, SQL execution, query jobs, IAM dữ liệu | Hệ thống review mã SQL và phát hành DAG |
| **Dataform Core/SQLX** | Định nghĩa các actions, references, assertions, cấu hình SQL | Engine lưu trữ/compute riêng |
| **Managed Dataform** | Repository/workspace, biên dịch, chạy, lịch, logs, Git integration | Nguồn dữ liệu streaming |
| **Dataflow/Apache Beam** | Xử lý batch/stream bằng pipelines phân tán và SDK | Bộ định nghĩa SQL marts Dataform |
| **Cloud Composer/Workflows** | Điều phối nhiều dịch vụ ngoài BigQuery khi cần | Bắt buộc phải có cho Dataform schedule |

**Khi chọn Dataform:** xử lý SQL trong BigQuery, cần quản lý dependency, test, Git và lịch chạy. **Khi chọn Beam/Dataflow:** cần đọc/biến đổi event hoặc file bằng code, xử lý streaming/windowing/state hay connectors ngoài BigQuery. Nhiều hệ thống dùng **cả hai**, nhưng không bắt buộc.

## 2. Kiến trúc và vòng đời của một Dataform workflow

### 2.1. Các đối tượng

| Đối tượng | Tác dụng | Ví dụ |
|---|---|---|
| **Repository** | Chứa mã Dataform, kết nối Git và cấu hình runtime | `commerce-transform` |
| **Development workspace** | Nhánh làm việc và biên dịch thử của developer | `dev-analyst-a` |
| **`workflow_settings.yaml`** | Project/dataset/location/assertions defaults, phiên bản Core | Dataset `analytics_mart` |
| **`definitions/*.sqlx`** | Định nghĩa bảng, view, nguồn, kiểm thử, operations | `stg_orders.sqlx` |
| **Compilation result** | Graph và SQL được biên dịch từ revision + overrides | Mã đã compile; chưa ghi dữ liệu |
| **Release configuration** | Chọn Git commitish, overrides và tần suất compile | `production` |
| **Workflow configuration** | Chọn release, actions/tags, lịch, danh tính chạy | `daily-revenue` |
| **Workflow invocation** | Một lượt chạy thực tế với trạng thái từng action | Job vào 02:00 UTC |

### 2.2. Luồng từ mã tới dữ liệu

~~~mermaid
flowchart TD
  CODE["SQLX + workflow_settings.yaml"] --> COMP["Compile: resolve refs và DAG"]
  COMP --> CHECK{"Compilation hợp lệ?"}
  CHECK -->|Không| FIX["Sửa SQLX / dependency / config"]
  CHECK -->|Có| DRY["BigQuery dry-run / kiểm tra quyền và schema"]
  DRY --> REVIEW["Git review + release configuration"]
  REVIEW --> RUN["Workflow configuration / manual invocation"]
  RUN --> JOBS["BigQuery SQL jobs theo DAG"]
  JOBS --> ASSERT["Assertions / logs / quality status"]
  ASSERT --> MART["Tables/views cho BI"]
~~~

**Biên dịch ≠ thực thi ≠ nghiệm thu dữ liệu.** Dataform compile chủ yếu kiểm tra SQLX/JavaScript, refs, target names và vòng lặp dependency; không chứng minh tất cả bảng BigQuery, cột, quyền IAM hoặc câu GoogleSQL đều hợp lệ. Sau compile cần **BigQuery dry run và một workflow execution trên staging**. Assertions kiểm tra dữ liệu sau khi có bảng, không thay thế kiểm thử nghiệp vụ.

### 2.3. Cách DAG quy định thứ tự

Nếu định nghĩa `raw_orders → stg_orders → daily_revenue`:

- **Declaration** nhận diện bảng nguồn đã tồn tại, không tạo dữ liệu mới.
- **`stg_orders`** dùng `${ref("raw_orders")}` để vừa định danh nguồn, vừa khai báo dependency.
- **`daily_revenue`** dùng `${ref("stg_orders")}`; Dataform chạy phụ thuộc trước khi chạy action tương ứng.
- Các actions không có dependency có thể chạy **song song**; không dựa vào thứ tự tên file.

`resolve()` chỉ tham chiếu đối tượng **không thêm cạnh dependency**. Nếu cần đảm bảo chạy theo thứ tự, dùng `ref()` hoặc `dependencies` tường minh. Dependency cycle làm compile lỗi.

## 3. SQLX: bảng, view, declaration, assertion và operations

`.sqlx` là SQL kèm **Dataform config/templating**. Sau compile, BigQuery nhận **GoogleSQL** tương ứng. Không chạy nguyên văn `config { ... }` hay `${ref(...)}` trong BigQuery SQL editor.

| Action `type` | Tác dụng | Lưu ý |
|---|---|---|
| `declaration` | Khai báo table/view nguồn ngoài Dataform để dùng `ref` | **Không nạp hay tạo** bảng nguồn |
| `view` | Tạo BigQuery view; có thể materialized theo cấu hình hỗ trợ | View thường không giữ bản sao data |
| `table` | Vật chất hóa kết quả SELECT thành BigQuery table | Chạy lại có thể tạo/thay bảng, tốn query/storage |
| `incremental` | Chỉ xử lý phần dữ liệu mới/thay đổi theo logic | Cần watermark/key/late-data plan |
| `assertion` | SQL trả về **0 rows để pass**; nếu có rows → fail | Không tự xóa rows lỗi |
| `operations` | Chạy GoogleSQL thủ công (DDL/DML/procedures) | Cần khai báo dependencies rõ, review tác động |

Ví dụ chỉ cần xem cú pháp:

~~~sqlx
config {
  type: "view",
  name: "orders_recent",
  tags: ["daily"]
}
SELECT order_id, region
FROM ${ref("stg_orders")}
WHERE order_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
~~~

**`tags`** dùng để chọn tập actions khi chạy workflow; nó **không** tạo IAM boundary. `description`/`columns` giúp ghi metadata; governance nâng cao có thể đồng bộ sang **Knowledge Catalog** với IAM và cấu hình tương ứng.

## 4. Cấu hình repository và môi trường

Dataform Core từ **3.0** khuyến nghị dùng `workflow_settings.yaml` ở root thay cho `dataform.json` kiểu cũ. Trong dự án thật hãy **giữ phiên bản Dataform Core được chốt bởi repository**, kiểm thử trước khi nâng.

**Ví dụ nội dung file `workflow_settings.yaml` trong một Dataform repository giả định**:

~~~yaml
defaultProject: shop-dev-001
defaultDataset: analytics_mart
defaultAssertionDataset: dataform_assertions
defaultLocation: asia-southeast1
# dataformCoreVersion: dùng phiên bản stable được repository khóa.
~~~

Không sao chép placeholder ở dạng thiếu version vào repository rồi cho rằng không cần cài Core. Nếu repository hiện có **`dataformCoreVersion`**, giữ version hiện tại; xem tính tương thích khi chuyển từ `dataform.json`. Một repository còn có thể đặt `projectSuffix, datasetSuffix, namePrefix` và compilation variables để tách môi trường.

| Khóa | Ý nghĩa |
|---|---|
| `defaultProject` | BigQuery project mặc định; có thể khác Dataform repository project |
| `defaultDataset` | Dataset đích mặc định |
| `defaultAssertionDataset` | Dataset giữ các assertion result views |
| `defaultLocation` | Vị trí **xử lý BigQuery SQL**; phải tương thích dataset nguồn/đích |
| `dataformCoreVersion` | Phiên bản Dataform Core được pin |

**Location quan trọng:** Dataform repository có thể ở một region khác **BigQuery dataset location**. Ví dụ repository ở `us-central1`, nhưng SQL xử lý bảng ở `asia-southeast1` nếu `defaultLocation` và resources phù hợp. Nếu để trống location, truy vấn không tham chiếu dataset có thể mặc định **US**; truy vấn chung nhiều locations không tương thích có thể lỗi.

### 4.1. Tách dev/staging/prod bằng compilation overrides

- Workspace cá nhân dùng **schema suffix** theo tên workspace, hoặc chạy trong project dev riêng.
- **Release configuration** production chọn nhánh/tag/commit SHA được review, đặt overrides theo môi trường.
- **Workflow configuration** tham chiếu compilation release tương ứng, chỉ chạy actions/tags được chọn.
- Dữ liệu khách hàng thật và quyền IAM nên được tách bằng **project/dataset**, không chỉ đặt tên bảng với hậu tố `_dev`.

**Không chạy thử `type: "table"` từ workspace vào dataset production trước khi xem compiled targets**: một bảng có thể bị thay thế khi execute. Workspace không tự cách ly BigQuery data nếu chưa cấu hình overrides.

## 5. Bài lab: từ dữ liệu đơn hàng thô đến bảng doanh thu

Các bước dưới đây là **ví dụ cho môi trường lab**, không phải thao tác đã chạy. Giả sử có project `shop-dev-001`, quyền tạo BigQuery tables/jobs, Dataform repository và service account phù hợp. Tên chỉ minh họa, không dùng production không được phép.

### 5.1. Bước 0 — Chuẩn bị bảng nguồn trong BigQuery

Trong **BigQuery Studio** với query location **asia-southeast1**, tạo dataset `raw_orders` trước bằng console hoặc lệnh `bq`:

~~~bash
bq --location=asia-southeast1 mk \
  --dataset shop-dev-001:raw_orders
~~~

Sau đó chạy **GoogleSQL** (không phải SQLX) để tạo bảng test:

~~~sql
CREATE TABLE IF NOT EXISTS `shop-dev-001.raw_orders.order_events` (
  event_id STRING,
  order_id STRING,
  event_ts TIMESTAMP,
  region STRING,
  amount NUMERIC,
  status STRING
)
PARTITION BY DATE(event_ts);
~~~

Nạp dữ liệu mẫu **một lần vào bảng đang rỗng**:

~~~sql
INSERT INTO `shop-dev-001.raw_orders.order_events`
  (event_id, order_id, event_ts, region, amount, status)
VALUES
  ('e1','o1', TIMESTAMP '2026-11-17 09:00:00+00','north',120,'PAID'),
  ('e2','o2', TIMESTAMP '2026-11-17 10:00:00+00','south',200,'PAID'),
  ('e3','o3', TIMESTAMP '2026-11-18 09:00:00+00','north', 50,'PENDING'),
  ('e4','o4', TIMESTAMP '2026-11-18 11:00:00+00','north', 80,'PAID');
~~~

**Cẩn thận:** chạy lại INSERT sẽ nhân đôi records vì BigQuery không cưỡng chế uniqueness như PostgreSQL primary key truyền thống. Với nguồn thật, ingestion từ Pub/Sub/Dataflow phải có **event ID, dedup và freshness SLA**; Dataform không tự sửa nguồn thiếu sự kiện hay duplicate.

### 5.2. Cấu trúc Dataform giả định

~~~text
commerce-transform/
  workflow_settings.yaml
  definitions/
    order_events.sqlx
    stg_orders.sqlx
    daily_revenue.sqlx
    assert_positive_amount.sqlx
~~~

Đây là **các file ví dụ bên trong Dataform repository riêng** để học viên tạo. Tài liệu này không yêu cầu sửa các file trên trong repository khóa học.

### 5.3. Bước 1 — `definitions/order_events.sqlx`: khai báo bảng thô

~~~sqlx
config {
  type: "declaration",
  database: "shop-dev-001",
  schema: "raw_orders",
  name: "order_events"
}
~~~

Dataform sẽ hiểu `order_events` là nguồn được quản lý **bên ngoài** workflow. **Declaration không tạo bảng và không nạp record**. Bảng BigQuery phải tồn tại, với location và IAM truy cập đúng; nếu nguồn chưa tồn tại, compilation có thể vẫn qua nhưng execution/dry run sẽ lỗi.

### 5.4. Bước 2 — `definitions/stg_orders.sqlx`: chuẩn hóa và kiểm thử

~~~sqlx
config {
  type: "table",
  schema: "analytics_mart",
  description: "Don hang da chuan hoa, giu ban ghi moi nhat moi order",
  tags: ["daily"],
  assertions: {
    uniqueKey: ["order_id"],
    nonNull: ["order_id", "order_date", "amount"],
    rowConditions: ["amount >= 0"]
  },
  columns: {
    order_id: "Ma don hang nghiep vu",
    order_date: "Ngay su kien theo UTC",
    region: "Vung kinh doanh da chuan hoa",
    amount: "Gia tri thanh toan",
    event_ts: "Thoi diem su kien"
  }
}

WITH latest AS (
  SELECT
    order_id,
    DATE(event_ts) AS order_date,
    LOWER(TRIM(region)) AS region,
    amount,
    event_ts,
    status
  FROM ${ref("order_events")}
  WHERE order_id IS NOT NULL
    AND event_ts IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY order_id ORDER BY event_ts DESC, event_id DESC
  ) = 1
)
SELECT order_id, order_date, region, amount, event_ts
FROM latest
WHERE status = 'PAID'
~~~

**Các điểm cần hiểu:**

1. `${ref("order_events")}` tạo dependency tới declaration, **không** cần ghi cứng đường dẫn table ở mỗi SELECT.
2. `QUALIFY ROW_NUMBER()` lấy record mới nhất theo `event_ts, event_id` cho từng `order_id`. Đây là **quy ước lab**, không tự biết phiên bản nghiệp vụ khi event đến sai thứ tự hoặc event_ts bị sửa; production nên có version/CDC sequence đáng tin cậy.
3. Chỉ sau khi chọn trạng thái mới nhất mới lọc `status = 'PAID'`; tránh tính đơn hàng đã chuyển sang CANCELLED.
4. `type: "table"` materialize kết quả khi chạy; không phải bảng incremental. Các assertions tạo kiểm tra riêng sau khi bảng được cập nhật.
5. Dataform mô tả cột qua `columns`, nhưng `nonNull` assertion **không tự làm cột BigQuery thành REQUIRED/NOT NULL**. Nếu cần BigQuery DDL ràng buộc kiểu dữ liệu, phải dùng phương án khác được hỗ trợ.

### 5.5. Bước 3 — `definitions/daily_revenue.sqlx`: mart tổng hợp

~~~sqlx
config {
  type: "table",
  schema: "analytics_mart",
  description: "Doanh thu hang ngay theo vung",
  tags: ["daily", "bi"],
  bigquery: {
    partitionBy: "order_date",
    clusterBy: ["region"]
  },
  assertions: {
    uniqueKeys: [["order_date", "region"]],
    nonNull: ["order_date", "region"],
    rowConditions: ["revenue >= 0", "order_count >= 0"]
  }
}

SELECT
  order_date,
  region,
  COUNT(*) AS order_count,
  SUM(amount) AS revenue
FROM ${ref("stg_orders")}
GROUP BY order_date, region
~~~

`bigquery.partitionBy` chỉ định phân vùng theo `order_date` và `clusterBy` nhóm dữ liệu theo vùng. Trên tập lớn, BI nên dùng `WHERE order_date ...` để giảm quét dữ liệu. **Partitioning và clustering không làm query miễn phí**; BigQuery vẫn tính phí lưu bảng và query jobs.

**Kết quả kỳ vọng của lab:**

| order_date | region | order_count | revenue |
|---|---|---:|---:|
| 2026-11-17 | north | 1 | 120 |
| 2026-11-17 | south | 1 | 200 |
| 2026-11-18 | north | 1 | 80 |

Tổng doanh thu **400** từ ba đơn PAID; đơn `o3` PENDING không được cộng. Nếu kết quả là 450, 520 hoặc 600, kiểm tra trùng dữ liệu nguồn, cách lọc trạng thái và lần chạy INSERT lab trước đó.

### 5.6. Bước 4 — `definitions/assert_positive_amount.sqlx`: assertion riêng

~~~sqlx
config {
  type: "assertion",
  schema: "dataform_assertions",
  tags: ["quality", "daily"]
}

SELECT order_id, amount, region
FROM ${ref("stg_orders")}
WHERE amount < 0
   OR region IS NULL
   OR TRIM(region) = ''
~~~

**Assertion phải trả về 0 dòng để pass**. Nếu trả bất kỳ dòng nào thì fail và workflow logs ghi nhận lỗi; những dòng sai **không tự bị xóa hay sửa**. Dataform cũng tạo assertion views ở BigQuery để người có quyền kiểm tra chi tiết. Dùng QA alerts/incident runbook; không chỉ xem table được tạo thành công.

### 5.7. DAG thu được sau compile

~~~mermaid
flowchart TD
  R["order_events<br/>declaration"] --> S["stg_orders<br/>table + built-in assertions"]
  S --> M["daily_revenue<br/>partitioned table + assertions"]
  S --> A["assert_positive_amount<br/>manual assertion"]
~~~

Chạy workflow theo DAG giúp **stg_orders** được vật chất hóa trước **daily_revenue** và assertion tương ứng. Nhưng một assertion không tự trở thành **cổng chặn** mọi action downstream trừ khi cấu hình dependency/run selection phù hợp; nếu cần chính sách **fail-fast trước publish mart**, phải thiết kế rõ kiểm tra và dependency mà orchestrator hỗ trợ.

## 6. Bảng incremental: xử lý dữ liệu mới nhưng không làm sai dữ liệu cũ

`type: "table"` thường tính lại toàn bộ SELECT khi chạy. Với lịch sử nhiều TB, có thể dùng `type: "incremental"` để giới hạn lượng cần xử lý. Tuy nhiên logic **incremental không tự chính xác** nếu nguồn gửi sự kiện muộn, sửa record cũ hoặc phát duplicate.

### 6.1. Ví dụ `definitions/fact_orders_incremental.sqlx` (thay thế, không bắt buộc cho lab cơ bản)

~~~sqlx
config {
  type: "incremental",
  schema: "analytics_mart",
  uniqueKey: ["order_id"],
  bigquery: {
    partitionBy: "order_date",
    clusterBy: ["region"]
  },
  assertions: {
    nonNull: ["order_id", "order_date"],
    uniqueKey: ["order_id"]
  }
}

SELECT order_id, order_date, region, amount, event_ts
FROM ${ref("stg_orders")}
${when(incremental(), `
  WHERE event_ts >= TIMESTAMP_SUB(
    (SELECT IFNULL(MAX(event_ts), TIMESTAMP('1970-01-01'))
     FROM ${self()}),
    INTERVAL 3 DAY
  )
`)}
~~~

Ý nghĩa:

- Lần đầu, `incremental()` là false: tạo bảng với toàn bộ dữ liệu từ staging.
- Các lần sau, filter chỉ xét events gần **max event_ts** của bảng đích trong khoảng **3 ngày lookback**.
- `uniqueKey: ["order_id"]` hướng Dataform sinh **MERGE/update-or-insert** theo khóa, thay vì chỉ append; **khác** `assertions.uniqueKey` vốn chỉ kiểm tra dữ liệu.
- `${self()}` tham chiếu **chính bảng đích** trong workflow; BigQuery phải có quyền đọc nó.

**Không dùng mẫu này như giải pháp cập nhật muộn hoàn chỉnh:** event đến trễ hơn lookback, event_ts sai hoặc chỉnh sửa một đơn hàng quá cũ có thể **không được nhập**. Một đơn hàng cập nhật `order_date` có thể đòi kiểm tra **MERGE scan/partition pruning**. Production cần watermark dựa vào **ingestion/update time đáng tin cậy**, khóa nghiệp vụ, khoảng reprocess phù hợp, xử lý deletes và **backfill/full refresh** có kiểm soát.

### 6.2. `updatePartitionFilter` và giới hạn ghi

Với bảng lớn, `bigquery.updatePartitionFilter` có thể giảm số partitions **bảng đích** được quét khi MERGE. Nhưng nếu điều kiện chỉ quét 7 ngày cuối mà có chỉnh sửa đơn hàng thuộc partition cũ, có thể **không match record cũ rồi insert duplicate**. Không đặt filter dựa vào “tiết kiệm phí” khi không đáp ứng phạm vi cập nhật nghiệp vụ.

### 6.3. Full refresh và backfill

Khi thay SQL logic hoặc phát hiện dữ liệu quá cũ bị bỏ sót:

1. Lập danh sách bảng phụ thuộc, lượng data cần backfill và chi phí quét.
2. Thử full refresh/backfill trên dataset staging với snapshot/dataset copy khi cần.
3. Chạy assertions và đối chiếu row counts, sums, reconciliation với hệ thống nguồn.
4. Chọn cửa sổ deploy ít tác động, xử lý downstream readers và rollback.
5. Chỉ thay production khi đã phê duyệt; **full refresh có thể dựng lại bảng và ảnh hưởng grants/policy tags** nếu không cấu hình/kiểm thử governance.

**Phân biệt:** một bài cần SQL aggregate hằng ngày cố định có thể dùng `type: "table"` đơn giản hơn incremental. Đừng dùng incremental chỉ vì tên nghe tối ưu; hãy đo số bytes processed, late-data rate và độ phức tạp sửa dữ liệu.

## 7. Assertions, kiểm thử và chất lượng dữ liệu

| Công cụ | Kiểm tra điều gì? | Hạn chế |
|---|---|---|
| **Compilation** | SQLX/JS syntax, refs, DAG, duplicate/cyclic targets | Không chứng minh BigQuery SQL hợp lệ |
| **BigQuery dry run** | Cú pháp/kiểu SQL và bảng/cột/quyền khi nguồn đã tồn tại | Không chứng minh dữ liệu đúng hoặc query không chậm |
| **Built-in assertions** | `nonNull`, `uniqueKey/uniqueKeys`, `rowConditions` | Là truy vấn kiểm tra, không cưỡng chế schema |
| **Manual assertion** | SQL phải trả 0 dòng, kiểm tra business invariant | Phải tự viết/duy trì logic |
| **Unit test Dataform** | Mock dependencies và expected outputs cho một action | Không mô phỏng mọi quota/latency/production data |
| **Staging execution** | Chạy DAG thật và assertions với data gần thực tế | Có phí BigQuery và cần IAM/isolated targets |

**Ví dụ nên có trong CI:** một order thanh toán có amount âm phải làm assertion fail; hai records trùng order_id bị phát hiện; ngày doanh thu âm hoặc vượt giới hạn nghiệp vụ phải được cảnh báo. Dataform đưa lỗi ra workflow logs; **quyết định chặn publish BI, rollback hoặc backfill do hệ thống vận hành quy định**.

### 7.1. Bảo vệ thay đổi schema và metadata

Trong SQLX, `description` và `columns` giúp tài liệu hóa dữ liệu; policy tags, row access policies và masking trong BigQuery vẫn là **cơ chế bảo mật thật**. Khi Dataform thay/recreate table, hãy xác minh **column policies/grants** có được giữ như yêu cầu. Tính năng `preserveGovernanceControls` là tùy chọn có trạng thái phát hành/giới hạn tương ứng; **không giả định mặc định giữ mọi governance metadata**.

**Data lineage** có thể được gửi tới **Knowledge Catalog** khi kích hoạt cấu hình và cấp quyền thích hợp. Lineage biểu thị quan hệ dữ liệu, **không phải bằng chứng rằng dữ liệu đã được ẩn danh hoặc được người dùng cho phép truy cập**.

## 8. Bài thực hành chạy Dataform trên Google Cloud

### 8.1. Chuẩn bị

Trong project **shop-dev-001** (giả định):

1. Bật **Dataform API** và **BigQuery API**; kiểm tra billing, organization policies và quotas.
2. Tạo **Dataform repository** ở region được hỗ trợ, ví dụ `asia-southeast1` nếu có trong danh sách location hiện hành.
3. Chọn **custom service account** cho repository và cấp quyền Dataform/BigQuery đúng phạm vi theo mục 10.
4. Tạo development workspace, bảo đảm `workflow_settings.yaml` đặt `defaultProject, defaultDataset, defaultLocation` đúng.
5. Tạo bốn SQLX files ở mục 5 trong thư mục `definitions/`.
6. Xem **Compiled graph** trước khi kích hoạt workflow; xác nhận targets không nằm ở production.

**Không dùng repository phục vụ dữ liệu thật để chạy thử** các lệnh tạo/ghi/xóa bảng. BigQuery jobs và storage có thể phát sinh phí ngay cả khi Dataform không có phí dịch vụ riêng.

### 8.2. Compile và xem kết quả

Trong **Dataform → Repository → Development Workspaces → workspace**:

- Mở từng SQLX, xem **Compiled queries** và thông báo lỗi.
- Mở **Compiled graph**, xác nhận `order_events → stg_orders → daily_revenue`.
- Kiểm tra **Dataform Core version** mà repository sử dụng và tên project/dataset được biên dịch.
- Nếu có BigQuery dry-run validation, xem cả quyền, schema và location; compile thành công không bảo đảm dry run thành công.

### 8.3. Chạy một workflow trên workspace

Chọn **Start execution** (tên nút có thể thay đổi theo giao diện), chọn các actions muốn chạy và **Include dependencies** khi cần. Quan sát:

1. `order_events` là declaration, nên không có SQL tạo bảng mới.
2. `stg_orders` tạo table có dữ liệu đã chuẩn hóa.
3. `daily_revenue` tổng hợp đúng **400** trên dữ liệu mẫu.
4. Các assertions tạo và kiểm tra kết quả; zero rows = pass.
5. Workflow execution logs cho từng action và BigQuery query jobs (lỗi BigQuery, bytes/slot-time khi có).

Nếu chỉ chọn `daily_revenue` mà bỏ dependency, trong project mới có thể bị lỗi **missing upstream table**. Cần chạy cả upstream hoặc chọn Include dependencies, thay vì thêm đường dẫn bảng cứng để né Dataform DAG.

### 8.4. Phát hiện lỗi có chủ đích

Trong **bảng raw lab** (không dùng production), thêm một đơn PAID có amount âm, chẳng hạn `event_id=e_bad, order_id=o_bad, amount=-10`. Chạy lại workflow:

- `stg_orders` có thể materialize dữ liệu chứa lỗi, nhưng **rowConditions** fail.
- `assert_positive_amount` trả ít nhất một dòng; status **FAILED**.
- Ghi lại affected action và BigQuery job ID; không tự sửa nguồn production, không để QA report coi số liệu không hợp lệ là đã publish.

Sau khi hoàn thành lab, xóa dữ liệu thử và bảng/dataset tạo riêng theo quy trình đã phê duyệt; đừng xóa dataset dùng chung, source tables hoặc các outputs đang phục vụ BI.

### 8.5. Tùy chọn: compile tại máy phát triển

Dataform có **open-source CLI**. Với một Dataform project hợp lệ và Node.js/npm được quản lý:

~~~bash
# Tại dự án Dataform lab riêng, KHÔNG phải repository giáo trình.
npm install --global @dataform/cli
dataform --version
dataform compile .
~~~

**`dataform compile` không gửi SQL tới BigQuery**, chủ yếu kiểm tra graph và build code; `dataform test`/`dataform run` là các thao tác khác, có thể gọi BigQuery và tính phí. CLI dùng ADC khi truy cập Google Cloud. Kiểm soát Node/Core versions trong CI, không dùng global latest chưa kiểm thử cho release.

## 9. Quản lý Git, release và lịch chạy

**Không biến workspace đang sửa dở thành production schedule.** Một quy trình đơn giản:

~~~mermaid
flowchart TD
  DEV["Developer workspace / feature branch"] --> CI["Compile + BigQuery dry run + tests"]
  CI --> PR["Git pull request / review"]
  PR --> MAIN["Merged main / pinned release commit"]
  MAIN --> RC["Release configuration: compile result"]
  RC --> WC["Workflow configuration: schedule + actions"]
  WC --> RUN["Workflow invocation trên BigQuery"]
  RUN --> OBS["Assertions + execution logs + cost alert"]
  OBS --> BI["Downstream analytics / BI"]
~~~

### 9.1. Release configuration khác workflow configuration

| Thành phần | Cấu hình chính | Kết quả |
|---|---|---|
| **Release configuration** | Git branch/tag/commitish, compilation overrides, lịch tạo compilation results | Phiên bản graph/SQL đã biên dịch |
| **Workflow configuration** | Release reference, danh sách actions/tags, cron/timezone, execution identity | Lịch chạy kết quả đã compile |
| **Workflow invocation** | Một lần chạy cụ thể | BigQuery jobs, action statuses, logs |

**Lưu ý lịch:** để đảm bảo workflow sử dụng compilation result mới nhất, tài liệu khuyến nghị cách thời điểm tạo release compilation và lịch chạy tối thiểu **một giờ**. Nếu scheduled run trước **chưa xong** khi tới lịch chạy mới, lần chạy tiếp theo có thể bị **skip và báo lỗi**; lập lịch dựa trên runtime thực và xử lý backlog.

### 9.2. Các cách orchestration

| Cách | Phù hợp |
|---|---|
| **Dataform workflow configurations** | SQL jobs theo DAG và cron trong Dataform, ít phụ thuộc ngoài |
| **Cloud Workflows + Cloud Scheduler** | Điều phối Dataform cùng các Google Cloud APIs khác |
| **Managed Service for Apache Airflow/Cloud Composer** | Pipeline phức tạp với dependencies giữa nhiều systems |
| **Cloud Build triggers** | Cần kích hoạt compilation/execution theo Git push |

**Không cần Composer chỉ để chạy ba bảng SQLX mỗi đêm.** Chọn orchestration dựa trên cross-service dependencies, quan sát, lỗi, lịch chạy và chi phí. Với production, ưu tiên **release configurations** thay vì clone Git remote cho mỗi invocation: đọc repository từ Git mỗi lần có thể phụ thuộc mạng và gặp lỗi credentials/SSH.

### 9.3. Triển khai và rollback

Quy trình đề xuất:

1. **PR** thay SQLX/metadata, review query plan, partitioning, columns/rules và tác động bảng downstream.
2. **Compile + dry run** trên dev; chạy assertions/integration tests ở staging.
3. **Merge** revision được duyệt; cập nhật release compilation của branch/tag/commit đã chốt.
4. **Chạy manual staging invocation**, xác minh row counts/revenue/BI contract.
5. **Bật production workflow configuration**, theo dõi một vài chu kỳ.
6. Khi lỗi, **quay lại Git revision/release configuration cũ** để khôi phục code; nếu dữ liệu đã bị ghi sai, còn cần **BigQuery restore/backfill** riêng.

**Rollback code không tự rollback dữ liệu**. Một job `type: "table"` có thể đã thay bảng; BigQuery time travel/snapshots/backup, schema compatibility và data reconciliation mới là kế hoạch khôi phục thực tế.

## 10. IAM: developer, execution identity và Dataform service agent

**Dataform quản trị workflow, BigQuery quản trị dữ liệu/query.** Hai lớp IAM cần được cấu hình độc lập:

| Danh tính | Nhiệm vụ | Quyền minh họa |
|---|---|---|
| **Dataform developer** | Sửa SQLX, compile/workspace | `roles/dataform.editor` ở phạm vi repository/workspace phù hợp |
| **Release operator** | Sửa release, lịch chạy và workflow | Dataform Admin/role phù hợp, phê duyệt môi trường |
| **Execution service account** | Thực thi BigQuery SQL jobs | `roles/bigquery.jobUser` trên job project; Viewer nguồn, Editor đích theo dataset |
| **Dataform service agent** | Hạ tầng Dataform impersonate danh tính chạy | Service-agent role + `iam.serviceAccountUser` và `iam.serviceAccountTokenCreator` trên effective SA |
| **Security/BI analyst** | Kiểm tra lineage, policies, reports | Metadata/log/BigQuery reader phù hợp |

### 10.1. Không nhầm service agent với service account thực thi

Dataform service agent thường có dạng:

~~~text
service-PROJECT_NUMBER@gcp-sa-dataform.iam.gserviceaccount.com
~~~

**Strict act-as mode hiện được áp dụng cho các repositories.** Workflow phải chạy bằng **custom service account** hoặc cơ chế Google Account credentials được hỗ trợ, **không dùng mặc định Dataform service agent làm execution identity**. Khi dùng custom SA:

- Người tạo/chỉnh execution workflow cần **`iam.serviceAccounts.actAs`** với SA được chọn.
- Dataform service agent cần **`roles/iam.serviceAccountTokenCreator`** để tạo token mạo danh service account, và **`roles/iam.serviceAccountUser`** để hỗ trợ tự động scheduled execution.
- Execution SA phải có **BigQuery Job User** ở project chạy jobs, **Data Viewer** trên nguồn và **Data Editor** trên đích. Cấp tối thiểu ở dataset khi hỗ trợ; một số hoạt động quản trị dataset hoặc policy cần quyền bổ sung.
- Nếu service account nằm **khác project**, xem ràng buộc **cross-project service account attachment** và organization policy riêng.

**Đừng cấp Owner cho service agent hoặc execution SA** chỉ để bỏ qua lỗi 403. Mỗi principal cần được audit; hạn chế phạm vi và rà soát quyền kế thừa từ project/folder/organization.

### 10.2. Ví dụ cấp quyền BigQuery ở project/dataset lab

~~~bash
# Chỉ để kiểm tra principal trước khi thao tác:
gcloud projects describe shop-dev-001 \
  --format="value(projectNumber)"

# Cấp quyền tạo query jobs cho execution SA ở project lab.
# Cần quyền setIamPolicy; chạy theo phê duyệt tổ chức.
gcloud projects add-iam-policy-binding shop-dev-001 \
  --member="serviceAccount:dataform-exec@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
~~~

**Đây không phải toàn bộ grants:** đọc `raw_orders` và ghi `analytics_mart` vẫn cần **dataset-level IAM**. Với Dataform service agent, cấp Token Creator/Service Account User **trên custom service account cụ thể**, không mở rộng toàn project nếu không cần. Không đặt mật khẩu/API key trong SQLX, workflow config hoặc Git; dùng Secret Manager/ADC đúng workload.

## 11. Quản trị dữ liệu, bảo mật và lineage

Dataform quản trị **mã biến đổi và siêu dữ liệu**, nhưng **không thay** các lớp bảo vệ dữ liệu:

| Mục tiêu | Cơ chế chính |
|---|---|
| Xem/sửa dữ liệu BigQuery | BigQuery IAM, row-level policies, column policy tags/masking |
| Phân vùng dữ liệu theo vùng địa lý | BigQuery dataset location, org policies, export restrictions |
| Kiểm thử dữ liệu | Dataform assertions/unit tests, reconciliation với nguồn |
| Định nghĩa nguồn và quan hệ | Dataform declarations/ref/DAG; Knowledge Catalog lineage khi cấu hình |
| Kiểm soát Git/secrets | Repository roles, branch protection, Secret Manager, access review |
| Bảo mật logs | Cloud Logging IAM/retention, mask query parameters/dữ liệu khách hàng |
| Phục hồi khi schema/data sai | BigQuery time travel/snapshots/backup/backfill + release rollback |

**Một assertion pass không chứng minh dữ liệu tuân thủ GDPR/PCI hoặc mọi logic kinh doanh đều đúng.** Ví dụ order_count và revenue đều dương nhưng doanh thu đã tính hai lần do ingestion duplicate; phải có reconciliation/idempotency và data contracts riêng.

### 11.1. Metadata, data catalog và lineage

Dataform có thể gắn **table/column descriptions**, BigQuery labels/tags và lineage sang **Knowledge Catalog** theo cấu hình hiện hành. Những hoạt động đồng bộ metadata có thể **bất đồng bộ sau action thành công**; lỗi đồng bộ tạm thời không nhất thiết làm thất bại BigQuery SQL job. Quyền **Dataplex Catalog Editor/Data Lineage Events Producer** chỉ cấp nếu sử dụng chức năng tương ứng.

### 11.2. Dataset location và dữ liệu nhạy cảm

Một Dataform repository không tự buộc bảng nằm tại region của repository. `defaultLocation` phải trùng location cần xử lý SQL của BigQuery; **không truy vấn trực tiếp datasets không tương thích giữa các regions**. Review cross-region data copy/export, CMEK permissions, time travel và retention theo bộ dữ liệu, không theo tên repository.

## 12. Giám sát workflow và chi phí

### 12.1. Dataform có phí riêng không?

Theo bảng giá chính thức, **Dataform là dịch vụ miễn phí**, nhưng các tài nguyên liên quan **vẫn tính phí**:

| Thành phần | Nguồn phí |
|---|---|
| **BigQuery query jobs** | Bytes billed theo on-demand hoặc slots capacity/reservations |
| **BigQuery managed tables** | Storage, partition/snapshot/retention theo mô hình |
| **Dataform assertions** | Các truy vấn kiểm tra chất lượng cũng dùng BigQuery compute |
| **Cloud Logging** | Logging/retention theo giá và lượng log thực tế |
| **Cloud Scheduler/Workflows/Airflow/Cloud Build** | Phí riêng khi dùng orchestration ngoài Dataform |
| **Cross-region/network/data export** | Phí phát sinh tùy nguồn/đích/đường truyền |

Nếu mart được tạo lại từ 5 TB raw mỗi giờ, **Dataform không tốn phí riêng** không có nghĩa 120 lần BigQuery scan là miễn phí. Tối ưu **partition filters, column projection, incremental windows, tags/chọn actions, tần suất chạy** và dữ liệu trung gian.

### 12.2. Chỉ số cần theo dõi

| Quan sát | Câu hỏi |
|---|---|
| **Compilation error rate** | Có lỗi SQLX/refs/dependency/cấu hình phiên bản? |
| **Workflow invocation status** | Lịch chạy có success/failed/skipped? |
| **Action runtime và BigQuery job ID** | Bảng nào chậm, assertion nào fail? |
| **BigQuery total_bytes_billed, total_slot_ms** | SQL nào đắt và tốn slots? |
| **Data freshness/last successful run** | Mart cập nhật chậm hơn SLA bao lâu? |
| **Assertion failure count** | Dữ liệu có sai nghiệp vụ hoặc schema drift? |
| **Storage bytes/partition growth** | Incremental có tạo duplicate/càng ngày càng lớn? |
| **IAM/metadata changes** | Có quyền rộng, thay policy tag hay xóa dataset không? |

Ví dụ đọc BigQuery jobs trong region (GoogleSQL):

~~~sql
SELECT
  job_id,
  creation_time,
  state,
  total_bytes_billed,
  total_slot_ms,
  error_result.message AS error_message
FROM `shop-dev-001.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY'
ORDER BY creation_time DESC
LIMIT 50;
~~~

**`JOBS_BY_PROJECT`** chỉ liệt kê jobs phù hợp quyền IAM và region qualifier. Một số fields có thể NULL ở job chưa kết thúc. Job bytes billed dưới **capacity-based pricing** không tự phản ánh chi phí reservation baseline; **Cloud Billing** vẫn là nguồn đối chiếu hóa đơn.

### 12.3. Alert và kiểm soát chi phí

- Alert **không có successful invocation** trước giờ BI cần dữ liệu, thay vì chỉ alert khi một job thất bại.
- Alert **assertions fail** trên dữ liệu quan trọng và ghi rõ data owner.
- Giới hạn mức truy vấn đắt qua **BigQuery quotas, maximum bytes billed/dry run** ở pipeline phù hợp; đo trước khi mở rộng.
- Kiểm tra **query cache, partition pruning và incremental scan** thực tế; không giả định WHERE date luôn prune partitions.
- **Budget alert không tự dừng workflow hoặc chặn chi phí**. Nếu cần hard guardrail, tổ chức phải tự cấu hình quyền/quota/automation được kiểm soát.

## 13. Troubleshooting theo lớp

| Triệu chứng | Khả năng đầu tiên | Cách kiểm tra |
|---|---|---|
| **Compilation error: ref not found** | Sai tên action, declaration thiếu, override tên không khớp | Files `definitions/`, compiled graph, `ref` |
| **Circular dependency** | A ref B, B ref A hoặc dependencies sai | Dựng lại DAG, bỏ vòng lặp |
| **Compile pass nhưng BigQuery syntax error** | Compile không kiểm tra toàn bộ GoogleSQL | Compiled SQL, BigQuery dry run, log job |
| **Not found: table/dataset** | Nguồn declaration chưa có hoặc upstream chưa chạy | Dataset resource, Include dependencies, IAM |
| **Not found in location US** | `defaultLocation` lệch dataset | Dataset location, compile/runtime settings |
| **PERMISSION_DENIED khi chạy** | Execution SA thiếu Job User/Viewer/Editor | Effective IAM của execution identity, job project, dataset |
| **Không thể schedule bằng custom SA** | Strict act-as/Token Creator/SA User thiếu | Dataform service agent và quyền trên effective SA |
| **Workspace ghi đè production table** | Không có compilation overrides hoặc targets sai | Compiled target project/schema trước execute |
| **Workflow chạy nhưng assertion fail** | Rows vi phạm điều kiện chất lượng | Assertion view, nguồn, event dedup |
| **Incremental bảng phình to** | Thiếu uniqueKey/merge, late-data logic, load trùng | MERGE SQL, business keys, row counts, update partitions |
| **Incremental bỏ sót cập nhật** | Lookback quá ngắn hoặc watermark sai | Event/update timestamps, reprocess policy |
| **Workflow bị skipped** | Lần chạy trước chưa hoàn tất khi đến lịch kế | Workflow logs và cron, duration |
| **Compile production Git không ổn định** | Remote Git credentials/network/compilation quá thường xuyên | Logs, release configs, Git provider connection |
| **Columns/policy tags bị mất sau refresh** | Recreate table không giữ governance metadata | BigQuery policy metadata, Dataform code và options |
| **Jobs đắt bất ngờ** | Full rebuild, SELECT *, thiếu partition pruning | INFORMATION_SCHEMA, bytes billed, partitions |
| **Không thấy lineage mới** | Metadata sync bất đồng bộ hoặc thiếu Catalog IAM | Workflow log, Catalog permissions, sync status |

**Runbook 5 bước:** xác định **repo/workspace/release + compilation result** → kiểm tra **compiled targets/DAG** → xem **effective execution identity/IAM/location** → đối chiếu **BigQuery job và assertion logs** → sửa tại **staging** và chạy replay/backfill có kiểm soát. Không giải quyết mọi lỗi bằng cách cấp `roles/owner` hoặc full refresh production.

## 14. Case study: quản lý dữ liệu bán hàng có thể kiểm toán

Doanh nghiệp **Hải Nam** có data team 5 người và Java backend trên Cloud Run. Mỗi đêm cần tổng doanh thu theo vùng, nhưng dữ liệu có thể đến muộn 48 giờ và sau phát hành phải xác định được SQL revision nào tạo ra báo cáo.

| Yêu cầu | Giải pháp |
|---|---|
| Nguồn dữ liệu có người quản lý khác | BigQuery source table + Dataform `declaration` |
| Logic thống nhất và kiểm thử được | `stg_orders`, `daily_revenue`, assertions |
| Sửa SQL không đụng production ngay | Workspace dev, schema suffix hoặc project riêng, Git PR |
| Phát hành có phiên bản | Release configuration từ commit/tag đã review |
| Tự động chạy lúc 02:00 UTC | Workflow configuration với schedule và custom SA |
| Dữ liệu đến muộn 48 giờ | Reprocess window dài hơn SLA, logic event version và backfill |
| Quyền tối thiểu | JobUser ở job project, nguồn Viewer, đích Editor, strict act-as |
| Chi phí kiểm soát | Partition by date, bytes/slot monitoring, budget, rate phù hợp |
| Khôi phục lỗi doanh thu | Revert SQL release **và** restore/recompute data |

### 14.1. Thử nghiệm chấp nhận

| Test | Kỳ vọng |
|---|---|
| Chạy bốn SQLX files trên lab đã có nguồn | Graph compile, mart có tổng doanh thu **400** |
| Một order âm | Assertion fail và workflow log ghi rõ |
| Một order trùng trong raw | Staging chọn đúng version; assertion phát hiện nếu kết quả cuối vẫn trùng |
| Bảng nguồn đổi cột | Dry run/execution chỉ ra mismatch; CI chặn release |
| Developer thiếu quyền prod | Không chạy được workflow prod |
| Job chạy sai location | Lỗi được nhận diện bằng dataset/job location |
| Incremental nhận update trễ 2 ngày | Reprocess/merge nếu nằm trong lookback và key hợp lệ |
| Incremental nhận update trễ 10 ngày | Có backfill/reconciliation; không nói “tự hỗ trợ” |
| Deploy SQL sai | Rollback release và khôi phục/recompute bảng bị tác động |

### 14.2. Điều kiện hoàn thành báo cáo

Không chỉ hỏi “Dataform job đã xanh chưa?”. Cần thêm **last successful data timestamp**, assertion results, số records nguồn/đích, doanh thu reconciliation, report consumers và hóa đơn BigQuery. Một workflow chạy thành công nhưng bỏ qua 10% sự kiện vẫn có thể tạo báo cáo sai.

## 15. Bài tập và đáp án gợi ý

### Bài tập A — Dataform hay Dataflow?

**Câu hỏi:** Java backend phát events qua Pub/Sub, nhóm cần lọc stream theo event time và tính window 5 phút; công cụ nào phù hợp? Sau đó nhóm cần tạo marts BigQuery mỗi đêm và quản lý Git SQL.

**Đáp án:** **Beam/Dataflow** xử lý stream/window; **Dataform** quản lý SQL transforms/DAG/quality trên BigQuery. Có thể dùng cả hai.

### Bài tập B — `ref` khác `resolve`?

Một bảng A tham chiếu B nhưng không được đảm bảo B chạy trước.

**Đáp án:** `resolve("B")` chỉ trả định danh, không tạo dependency. Dùng `ref("B")` hoặc `dependencies` để Dataform biết thứ tự.

### Bài tập C — Declaration có tạo bảng không?

Dataform compile thành công nhưng BigQuery báo `raw_orders.order_events` không tồn tại.

**Đáp án:** `declaration` chỉ **khai báo nguồn**, không tự tạo table. Tạo/nạp nguồn trước, kiểm tra project/dataset/IAM/location.

### Bài tập D — Tính kết quả lab

Có bốn records mẫu, trong đó ba đơn PAID amounts 120, 200, 80 và một đơn PENDING amount 50.

**Đáp án:** Doanh thu báo cáo là **400**, số đơn PAID là **3**. Chia theo ngày/vùng như bảng kết quả mục 5.

### Bài tập E — Assertion âm

Một đơn PAID có `amount=-10`; built-in rowCondition `amount >= 0`.

**Đáp án:** Assertion fail, dù bảng có thể đã được materialize. Cần xử lý lỗi nguồn, không che lỗi bằng cách tắt assertion.

### Bài tập F — Incremental và hai `uniqueKey`

Sự khác nhau giữa `uniqueKey: ["order_id"]` và `assertions: { uniqueKey: ["order_id"] }`?

**Đáp án:** Cái thứ nhất điều khiển **incremental MERGE theo khóa**; cái thứ hai **kiểm tra không có duplicate**. Chỉ assertion không biến append thành upsert.

### Bài tập G — Late update

Một order cập nhật sau 10 ngày nhưng incremental filter chỉ đọc ba ngày cuối.

**Đáp án:** Có thể bị bỏ sót. Cần event ingestion/update timestamp đáng tin cậy, lookback phù hợp hoặc backfill; không dùng filter ngắn khi SLA không cho phép.

### Bài tập H — IAM service account

Dataform developer có quyền chỉnh SQLX nhưng scheduled run báo lỗi impersonation service account.

**Đáp án:** Kiểm tra **strict act-as**: IAM actAs của người cấu hình, Dataform service agent có **Service Account User + Token Creator** trên effective SA; execution SA có BigQuery job/data permissions.

### Bài tập I — Compilation pass có chạy được không?

File SQLX dùng cột `amount_usd` không tồn tại, nhưng compiled graph không báo lỗi.

**Đáp án:** Có thể xảy ra, vì compile không kiểm tra đầy đủ BigQuery schema. Chạy BigQuery dry run và staging execution trước release.

### Bài tập J — Rollback

Sau deploy code Dataform sai, bảng `daily_revenue` đã được tạo lại với doanh thu thiếu.

**Đáp án:** Revert commit/release chưa khôi phục bảng; cần restore snapshot/time travel hoặc re-run logic đúng/backfill, sau đó kiểm tra downstream dashboards và reconciliation.

### Bài tập K — Tài chính

Một nhóm bảo Dataform miễn phí nên cho chạy full scan bảng 5 TB mỗi 15 phút.

**Đáp án:** Dataform service miễn phí nhưng **BigQuery queries/storage và Cloud Logging/orchestration vẫn tính phí**. Cần tính workload, partition/incremental, schedules và theo dõi Cloud Billing.

## 16. Tổng kết và tài liệu chính thức

**Sáu điều cần nhớ:**

1. **Dataform quản lý mã SQL/quality/dependencies**, BigQuery thực thi và lưu dữ liệu; không coi Dataform là streaming engine.
2. **`ref()` tạo cạnh DAG**, declarations đại diện nguồn, tables/views/incrementals materialize dữ liệu, assertions kiểm tra kết quả.
3. **Biên dịch không đồng nghĩa SQL BigQuery hợp lệ**; cần dry run, staging execution, unit/data assertions và review kết quả.
4. **Version control + workspace/release/workflow configurations** tạo đường phát hành có kiểm soát, không chạy dev trực tiếp trên prod.
5. **Strict act-as/IAM, dataset location, policy tags và lineage** phải được quản trị theo đúng identity và resource.
6. **Dataform miễn phí nhưng BigQuery không miễn phí**; incremental, partition, quality checks, backfill, query jobs và budgets ảnh hưởng cả độ đúng lẫn chi phí.

**Tài liệu Google Cloud chính thức:**

1. [Dataform overview](https://docs.cloud.google.com/dataform/docs/overview) — vòng đời repository/compilation/workflow.
2. [SQL workflows](https://docs.cloud.google.com/dataform/docs/sql-workflows) — graph và các loại actions.
3. [Repository/workflow settings](https://docs.cloud.google.com/dataform/docs/manage-repository) — `workflow_settings.yaml`, location, Core versions.
4. [Declare data sources](https://docs.cloud.google.com/dataform/docs/declare-source) — `declaration`.
5. [Create tables and incremental tables](https://docs.cloud.google.com/dataform/docs/create-tables) — `type, uniqueKey, ref`.
6. [Set dependencies](https://docs.cloud.google.com/dataform/docs/dependencies) — `ref` và DAG.
7. [Test data quality](https://docs.cloud.google.com/dataform/docs/test-data) — built-in/manual assertions và unit tests.
8. [Configure compilation and releases](https://docs.cloud.google.com/dataform/docs/configure-compilation) — compilation overrides.
9. [Schedule SQL workflows](https://docs.cloud.google.com/dataform/docs/schedule-runs) — workflow configs, Workflows/Scheduler/Airflow.
10. [Dataform IAM](https://docs.cloud.google.com/dataform/docs/access-control) — service agent, strict act-as và BigQuery roles.
11. [Dataform troubleshooting](https://docs.cloud.google.com/dataform/docs/troubleshooting) — compile, execution, Git errors.
12. [Dataform CLI](https://docs.cloud.google.com/dataform/docs/use-dataform-cli) — compile/test/run local.
13. [Dataform pricing](https://cloud.google.com/dataform/pricing) — Dataform free, các dịch vụ liên quan có phí.
