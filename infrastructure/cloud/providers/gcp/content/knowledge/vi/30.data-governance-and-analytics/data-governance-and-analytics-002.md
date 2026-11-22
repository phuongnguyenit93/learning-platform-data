# BigLake và truy cập dữ liệu ngoài BigQuery

Một nền tảng đào tạo lưu sự kiện học tập thô dưới dạng **Parquet/CSV trong Cloud Storage**. Nhóm phân tích muốn dùng BigQuery SQL để tổng hợp số lần học viên hoàn thành bài, nhưng không muốn tải bản sao toàn bộ dữ liệu vào BigQuery mỗi lần có file mới. Nhóm quản trị lại không muốn cấp trực tiếp quyền đọc bucket chứa dữ liệu nhạy cảm cho mọi analyst. **BigLake table** giải quyết hai nhu cầu: truy vấn dữ liệu nằm ngoài BigQuery storage và **ủy quyền truy cập nguồn qua một Cloud resource connection**.

Trong chương **Quản trị và khai thác dữ liệu** của module **CLOUD_PROVIDERS_GCP**, bài học kết nối IAM, Cloud Storage, BigQuery, VPC và dịch vụ xử lý dữ liệu (Dataflow/Spark) để lựa chọn đúng kiểu truy cập ngoài kho dữ liệu, quản lý quyền tối thiểu, độ mới của dữ liệu, hiệu năng và chi phí. Ví dụ chính dùng **GoogleSQL** với **BigLake external table trên Cloud Storage**; đây không phải tài liệu hướng dẫn sao chép dữ liệu sang BigQuery native table.

**Sau bài học, bạn có thể:**

1. Phân biệt **BigLake table**, external table thông thường, object table, federated query và Iceberg managed table.
2. Giải thích **access delegation** qua connection service account và thiết kế IAM không cho consumer đi vòng qua bảng.
3. Tạo/đọc BigLake external table trên file Cloud Storage bằng SQL và kiểm thử quyền cho data owner/analyst.
4. Chọn format, schema, file layout, Hive partitioning và metadata caching theo workload.
5. Nhận diện giới hạn consistency, DML, location, chi phí và khi nào nên **load vào BigQuery**.
6. Điều tra lỗi 403, file không xuất hiện, query chậm và thực hành với dữ liệu giả.

## 1. Bản đồ các cách BigQuery truy vấn dữ liệu ngoài

BigQuery có thể **lưu metadata/schema của bảng** nhưng dữ liệu thực nằm trong Cloud Storage hoặc hệ thống khác. Tùy nguồn và mục đích, cần chọn đúng loại tài nguyên.

| Cách truy cập | Nguồn điển hình | Cách cấp quyền | Phù hợp khi |
| --- | --- | --- | --- |
| **BigLake external table** | Cloud Storage; Amazon S3/Azure Blob qua BigQuery Omni theo hỗ trợ | **Access delegation** qua connection và IAM trên BigLake table | Data lake cần governance, SQL và chia sẻ có kiểm soát |
| **Non-BigLake external table** | Cloud Storage, Bigtable, Google Drive | Người query thường cần quyền **bảng và nguồn ngoài** | Khám phá ad hoc hoặc nguồn không hỗ trợ BigLake |
| **Object table** | File phi cấu trúc trong Cloud Storage | Connection service account; hàng phản ánh **metadata của object** | Tìm kiếm/phân loại đối tượng ảnh, tài liệu, video |
| **Federated query** | Cloud SQL, AlloyDB, Spanner hoặc database được hỗ trợ | Connection đến database; `EXTERNAL_QUERY` hoặc external dataset phù hợp | Join/đọc dữ liệu vận hành còn ở DB nguồn |
| **BigQuery native table** | Dữ liệu được load/ghi vào managed BigQuery storage | IAM theo dataset/table/view | Query lặp, tối ưu hiệu năng, quản lý theo BigQuery |
| **Apache Iceberg managed table** | Dữ liệu định dạng Iceberg trong bucket được quản lý bởi người dùng | Connection + BigQuery-managed table/catalog theo sản phẩm | Lakehouse cần open-format **và ghi/cập nhật bằng DML** |

**Phân biệt quan trọng:** một BigLake external table trên Parquet/CSV **không** giống **Iceberg managed table**. External table thông thường trong mô hình này được BigQuery **đọc**, không hỗ trợ `INSERT`/`UPDATE`/`DELETE` vào file nguồn qua DML. Iceberg managed tables có vòng đời metadata, hỗ trợ DML và tối ưu lưu trữ riêng; không dùng ví dụ `CREATE EXTERNAL TABLE` ở đây để suy rằng đã tạo Iceberg managed table.

### 1.1. BigLake không di chuyển file nguồn

~~~mermaid
flowchart LR
    ETL["Dataflow / Spark<br/>ghi Parquet"] --> GCS["Cloud Storage<br/>raw/curated objects"]
    OWNER["Data steward"] --> BQ["BigQuery BigLake table<br/>schema, metadata, IAM"]
    BQ -->|"Cloud resource connection<br/>service account"| GCS
    A["Analyst / BI"] -->|"SQL + quyền trên bảng"| BQ
    BQ --> R["Query result"]
~~~

**Dữ liệu nguồn vẫn nằm trong bucket**. Thao tác `CREATE EXTERNAL TABLE` chỉ khai báo bảng trỏ đến đối tượng; không tự tạo một pipeline ingest, không sao chép file và không sửa schema trên các file có sẵn.

### 1.2. Khi nào chọn giải pháp khác?

- **CSV nhỏ, phân tích một lần:** non-BigLake external table hoặc load trực tiếp có thể đơn giản hơn khi không cần phân tách quyền nguồn.
- **Parquet lớn, nhiều nhóm cùng đọc với quyền phân cấp:** BigLake table + connection + row/column policies là ứng viên tốt.
- **Dashboard chạy lặp liên tục với độ trễ thấp:** benchmark việc **load vào BigQuery native table** hoặc materialize một tầng curated; external table có thêm chi phí đọc nguồn.
- **Dữ liệu Google Sheets/Bigtable:** dùng external table thích hợp, **không** chọn BigLake Cloud Storage table chỉ vì tên có “BigLake”.
- **Truy vấn trực tiếp Cloud SQL/AlloyDB:** xem `EXTERNAL_QUERY` và connection của hệ thống đó; SQL ngoài có dialect/giới hạn riêng.

## 2. Access delegation: tách quyền đọc bảng khỏi quyền đọc bucket

### 2.1. Sơ đồ quyền

~~~mermaid
flowchart TB
    U["Analyst: chỉ query"] -->|"bigquery.jobs.create<br/>ở job project"| JOB["BigQuery query job"]
    U -->|"bigquery.tables.getData<br/>ở BigLake table"| T["BigLake table"]
    T -->|"Connection ID"| C["Cloud resource connection"]
    C -->|"Identity: connection service account"| S["Cloud Storage bucket/prefix"]
    OWNER["Data owner"] -->|"Tạo table, cấp quyền<br/>và audit"| T
    OWNER -->|"Grant storage.objects.get/list<br/>cho connection SA"| S
    U -. "Không có Storage Object Viewer" .-> S
~~~

Với **non-BigLake external table**, analyst cần quyền trên bảng **và** Cloud Storage objects (hoặc nguồn tương ứng). Với **BigLake table**, connection có **service account riêng** đọc file, còn analyst chỉ cần quyền query job và đọc table. Đây là nền tảng để áp các chính sách **row-level/column-level** ở BigQuery mà không phải cấp quyền đọc file thô cho người dùng.

| Principal | Quyền tối thiểu điển hình | Phạm vi |
| --- | --- | --- |
| Người tạo connection | Quyền `bigquery.connections.create` hoặc role Connection Admin thích hợp | Project/location chứa connection |
| Người tạo BigLake table | `bigquery.tables.create` và `bigquery.connections.delegate` phù hợp | Dataset và connection được phép |
| **Connection service account** | `roles/storage.objectViewer` hoặc quyền object get/list cần thiết | Bucket/managed folder được duyệt |
| Analyst | `roles/bigquery.dataViewer` trên **table** + `roles/bigquery.jobUser` tại job project | Không cấp quyền trên bucket nguồn |
| Ingestion pipeline | Quyền ghi các prefix đã được duyệt | Không cần BigQuery Admin nếu chỉ ghi dữ liệu lake |

**Job project** có thể khác project chứa table. Principal tạo query job cần `bigquery.jobs.create` trên **project chạy job**, trong khi quyền đọc dữ liệu được kiểm tra tại bảng. BigQuery IAM cấp từ project/folder/organization có thể **kế thừa** xuống nhiều bảng: phải kiểm tra tất cả bindings, không chỉ quyền trực tiếp tại table.

### 2.2. Những đường vòng cần khóa

Ngay cả khi có BigLake table an toàn, data owner cần tránh cấp analyst:

1. **Storage Object Viewer trực tiếp** trên bucket dữ liệu thô: khi đó họ có thể tải file bỏ qua filter/masking của BigQuery.
2. **Quyền tạo hoặc bind table tùy ý với connection** (ví dụ các quyền delegate/admin connection): họ có thể tự khai báo bảng mới không có chính sách che dữ liệu.
3. Quyền `bigquery.objectRefs.read` trên connection, nếu đang dùng ObjectRef functions: có thể tạo đường đọc object vượt lớp kiểm soát của BigLake table.
4. Quyền rộng từ các nhóm khác, service account impersonation hoặc bản sao dữ liệu đã được xuất.

Connection service account cần phạm vi bucket **nhỏ nhất phục vụ workload**; nếu một connection đọc được toàn bộ bucket chứa nhiều tenants, người có quyền ủy quyền connection có blast radius lớn. Dùng bucket tách theo sensitivity/owner hoặc managed folders và IAM conditions được hỗ trợ khi thích hợp; kiểm chứng quyền thực tế với IAM Policy Troubleshooter và negative tests.

**Không nhầm** connection service account với tài khoản của analyst hay service account của Cloud Run submit query: mỗi principal đảm nhiệm một lớp khác nhau. Không lưu key JSON của connection SA; dịch vụ BigQuery quản lý danh tính này.

## 3. Thiết kế nguồn dữ liệu trước khi tạo table

### 3.1. Chọn format theo nhu cầu truy vấn

| Format | Điểm mạnh | Giới hạn cần cân nhắc |
| --- | --- | --- |
| **Parquet** | Lưu cột, compression, schema và column pruning tốt | Nhiều file quá nhỏ hoặc schema không thống nhất làm chậm |
| **ORC** | Lưu cột, thích hợp dữ liệu phân tích | Phải kiểm tra kiểu dữ liệu và tương thích pipeline |
| **Avro** | Schema và dữ liệu record tương đối rõ | Với truy vấn chỉ vài cột có thể kém Parquet |
| **CSV** | Dễ đọc, thử nghiệm và trao đổi | Parse nhiều, kiểu dữ liệu không tự rõ, delimiter/quote/null dễ lỗi |
| **Newline-delimited JSON** | Dễ ghi dữ liệu bán cấu trúc | Kích thước lớn, schema thay đổi/kiểu không đồng nhất |

Cloud Storage external tables hỗ trợ các format trên theo tài liệu nguồn. Với pipeline dữ liệu lớn, **Parquet + phân vùng theo ngày/nhóm truy vấn** thường là baseline đáng đo, nhưng không đồng nghĩa mọi định dạng hay mọi query đều nhanh hơn.

**Một external table** có thể tham chiếu nhiều file phù hợp cùng schema bằng URI wildcard, ví dụ `gs://lake/curated/enrollments/*.parquet`. Tên file/schema không đúng không tự được BigLake sửa. Tránh để folder chứa file tạm, manifest, version cũ hoặc file thuộc format khác trong wildcard.

### 3.2. Vị trí dữ liệu và tính nhất quán

Chọn **BigQuery dataset location, Cloud resource connection location và bucket location** theo bảng quy tắc colocated/supported locations của Google Cloud. Với lab đơn giản, dùng **cùng một region** cho cả ba. Không giả định tên multi-region `US` tương đương bất kỳ bucket đơn region nào; chỉ dùng cặp vị trí được sản phẩm hỗ trợ và phù hợp data residency.

**External data không có cùng consistency semantics với BigQuery native tables.** Khi pipeline đang ghi, đổi tên hoặc xóa file cùng lúc query, kết quả có thể không nhất quán: query có thể thấy file mới/cũ không đồng bộ hoặc lỗi đọc. Để công bố dữ liệu, ưu tiên:

1. Ghi file vào **prefix staging** riêng theo `run_id`.
2. Kiểm tra schema, số hàng, checksum/manifest và quyền.
3. Chỉ sau khi dữ liệu hoàn chỉnh mới cập nhật **đường URI/table definition** hoặc publication pointer theo quy trình kiểm soát.
4. Không ghi đè các object đang được query; dùng file bất biến và retention/rollback có chủ đích.

Với dữ liệu đòi hỏi snapshot nhất quán và quản lý transaction phức tạp, cân nhắc **Iceberg managed table** hoặc load vào BigQuery native thay vì coi directory wildcard là một bảng transactional.

### 3.3. Folder layout và Hive partitioning

Một layout hay gặp:

~~~text
gs://LEARNING_LAKE/curated/enrollments/
  event_date=2026-11-17/part-0000.parquet
  event_date=2026-11-18/part-0000.parquet
  event_date=2026-11-19/part-0000.parquet
~~~

BigLake external table có thể khai báo **Hive partitioning** để rút gọn file discovery và đọc ít partition hơn:

~~~sql
-- GoogleSQL: ví dụ kiến trúc, không chạy khi chưa có dữ liệu/prefix lab.
CREATE EXTERNAL TABLE `PROJECT_ID.lake_curated.enrollments_partitioned` (
  event_id STRING,
  tenant_id STRING,
  course_id STRING,
  status STRING
)
WITH PARTITION COLUMNS (event_date DATE)
WITH CONNECTION `PROJECT_ID.asia-southeast1.lake_connection`
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://LEARNING_LAKE/curated/enrollments/*'],
  hive_partition_uri_prefix = 'gs://LEARNING_LAKE/curated/enrollments',
  require_hive_partition_filter = TRUE
);
~~~

Khi query, lọc `event_date` với literal/parameter giúp **partition pruning**:

~~~sql
SELECT course_id, COUNT(*) AS enrollments
FROM `PROJECT_ID.lake_curated.enrollments_partitioned`
WHERE event_date = DATE '2026-11-18'
  AND status = 'ACTIVE'
GROUP BY course_id;
~~~

**Không để `event_date` vừa là Hive partition column vừa là field vật lý lặp lại trong table schema** nếu engine/schema không hỗ trợ cách khai báo trùng. `require_hive_partition_filter` giúp tránh query quét cả lake do quên predicate. Thiết kế nhiều partition siêu nhỏ (ví dụ theo `event_id`) lại làm tăng metadata/file overhead và khó quản trị.

## 4. Lab: BigLake table trên Cloud Storage với access delegation

**Mục tiêu:** dùng một bucket/dataset **lab đã được cấp**, tạo connection và BigLake table cho sự kiện giả, xác minh analyst truy vấn được qua table nhưng **không đọc trực tiếp file**. Các lệnh tạo tài nguyên sau đây có thể phát sinh phí; chỉ chạy ở **project lab được phê duyệt**. Không cấp quyền ở production theo ví dụ.

### 4.1. Vai trò và tài nguyên

Cần có:

- Project, bucket và dataset BigQuery **riêng cho lab**, với billing và BigQuery Connection API được quản trị viên bật khi cần.
- Bucket và dataset cùng region, ví dụ `asia-southeast1` nếu được hỗ trợ.
- Principal **data steward** có quyền tạo connection, cấp IAM cho service account của connection và tạo table; có thể chia các thao tác cho admin tương ứng.
- Principal **analyst lab** chỉ có `bigquery.jobs.create` trên project chạy job và `bigquery.tables.getData` trên đúng table lab.
- Dữ liệu giả, không có email thật, số thẻ, mật khẩu hoặc thông tin học viên.

**Preflight chỉ đọc** trước khi tạo:

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export LOCATION="asia-southeast1"
export BUCKET="YOUR_EXISTING_LAB_BUCKET"
export DATASET="biglake_demo_lab"
export CONNECTION_ID="lake_lab_connection"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project
gcloud storage buckets describe "gs://$BUCKET"
bq ls --project_id="$PROJECT_ID"
bq ls --connection --project_id="$PROJECT_ID" --location="$LOCATION"
~~~

Không tiếp tục nếu tên dataset/connection trùng tài nguyên thuộc người khác hoặc bucket không đáp ứng location/security. Nếu chưa có quyền tạo connection/ban đầu chưa có API, báo owner; **không tự cấp Project Owner hoặc bật API tại production**.

### 4.2. Tạo CSV giả và tải lên prefix riêng

Ví dụ file local `events.csv`:

~~~csv
event_id,tenant_id,course_id,status,event_date
ev01,t-lab,java-basic,ACTIVE,2026-11-18
ev02,t-lab,java-basic,ACTIVE,2026-11-18
ev03,t-lab,python-basic,ACTIVE,2026-11-18
ev04,t-lab,java-basic,CANCELLED,2026-11-18
ev05,t-lab,python-basic,ACTIVE,2026-11-19
~~~

Chỉ upload nếu `gs://$BUCKET/biglake-demo/$RUN_ID/` là prefix **mới do lab sở hữu**:

~~~bash
export RUN_ID="demo-run-001"  # Đổi ID nếu đã có dữ liệu cùng tên.
gcloud storage ls "gs://$BUCKET/biglake-demo/$RUN_ID/"

# THAO TÁC GHI: file giả trong prefix lab được phê duyệt.
gcloud storage cp ./events.csv \
  "gs://$BUCKET/biglake-demo/$RUN_ID/events.csv"
~~~

Expected input có **5 dòng**: hai dòng `java-basic/ACTIVE` trong ngày 18, một `python-basic/ACTIVE` trong ngày 18, một `python-basic/ACTIVE` ngày 19 và một dòng `CANCELLED`. Không dùng `SELECT *` trên bảng chứa PII thật để thử.

### 4.3. Tạo Cloud resource connection

Tại project và region đã chốt, **data steward/connection admin** chạy:

~~~bash
# THAO TÁC GHI: tạo connection riêng cho lab.
bq mk --connection \
  --location="$LOCATION" \
  --project_id="$PROJECT_ID" \
  --connection_type=CLOUD_RESOURCE \
  "$CONNECTION_ID"

# CHỈ ĐỌC: lấy serviceAccountId do BigQuery tự tạo.
bq show --connection \
  "$PROJECT_ID.$LOCATION.$CONNECTION_ID"
~~~

Kết quả `bq show` có field `serviceAccountId`, ví dụ dạng:

~~~text
connection-12345-abcde@gcp-sa-bigquery-condel.iam.gserviceaccount.com
~~~

Admin lấy **giá trị thực** từ output, không dùng email mẫu. Sau đó cấp **Storage Object Viewer** cho connection SA trên bucket **lab** (hoặc phạm vi đối tượng nhỏ hơn theo cấu hình IAM được hỗ trợ) và kiểm tra IAM policy:

~~~bash
# Thay bằng serviceAccountId THẬT của connection do bq show trả.
export CONNECTION_SA="CONNECTION_SERVICE_ACCOUNT_FROM_BQ_SHOW"

# THAO TÁC ĐỔI QUYỀN: chỉ admin được phê duyệt thực hiện.
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$CONNECTION_SA" \
  --role="roles/storage.objectViewer"

# CHỈ ĐỌC: kiểm tra binding vừa cấp.
gcloud storage buckets get-iam-policy "gs://$BUCKET"
~~~

**Không cấp quyền bucket cho analyst**. Nếu bucket dùng chung chứa nguồn nhạy cảm, đừng cấp cả bucket chỉ để làm lab; chọn bucket riêng hoặc có policy ràng buộc prefix đã được security review. Khi connection bị xóa, quyền IAM của service account trong bucket **không nhất thiết tự được thu hồi ngay**; bước dọn phải rà soát binding.

### 4.4. Tạo BigLake external table qua GoogleSQL

Dataset `biglake_demo_lab` phải được data owner tạo **trước** trong cùng region với connection và bucket. Trong BigQuery Studio (GoogleSQL), thay **project, region, bucket, run ID** bằng giá trị lab; chạy bằng account có quyền tạo table và delegate connection:

~~~sql
-- DDL TẠO BẢNG: chỉ dùng trong dataset lab có tên riêng.
CREATE EXTERNAL TABLE `YOUR_PROJECT.biglake_demo_lab.events_external` (
  event_id STRING,
  tenant_id STRING,
  course_id STRING,
  status STRING,
  event_date DATE
)
WITH CONNECTION `YOUR_PROJECT.asia-southeast1.lake_lab_connection`
OPTIONS (
  format = 'CSV',
  uris = ['gs://YOUR_EXISTING_LAB_BUCKET/biglake-demo/demo-run-001/events.csv'],
  skip_leading_rows = 1
);
~~~

**Quan trọng:** trong lệnh mẫu, connection ID `lake_lab_connection` và các tên bucket/project **phải được thay** bằng đúng dữ liệu bước trước; nếu đã tạo `lake_lab_connection` thì giữ đúng cùng tên. `skip_leading_rows=1` bỏ header của CSV; schema được khai báo tường minh nên các cột được ánh xạ theo thứ tự file.

Khi dùng query trên một BigLake table:

~~~sql
SELECT
  event_date,
  course_id,
  COUNT(*) AS active_events
FROM `YOUR_PROJECT.biglake_demo_lab.events_external`
WHERE status = 'ACTIVE'
GROUP BY event_date, course_id
ORDER BY event_date, course_id;
~~~

**Kỳ vọng:** ba hàng kết quả: ngày `2026-11-18` khóa `java-basic` có 2, ngày `2026-11-18` khóa `python-basic` có 1 và ngày `2026-11-19` khóa `python-basic` có 1. Data vẫn nằm ở Cloud Storage; đây là phép tổng hợp khi query.

### 4.5. Positive/negative tests bằng hai danh tính

**Data owner** chỉ cấp cho analyst lab:

- `BigQuery Data Viewer` ở **bảng `events_external`** (không phải cả dataset nguồn nếu dataset có thêm bảng nhạy cảm).
- `BigQuery Job User` trên project analyst dùng để chạy query.
- **Không** cấp Storage Object Viewer trên bucket, quyền tạo/bind connection hoặc role có `bigquery.objectRefs.read` trên connection.

Kiểm thử bằng **chính analyst identity**, không dùng account owner rồi suy kết quả:

| Phép thử | Kết quả dự kiến |
| --- | --- |
| `SELECT event_date, COUNT(*) FROM events_external GROUP BY event_date` | **Cho phép**, nếu quyền job và table đúng |
| `gcloud storage cat gs://.../events.csv` với analyst identity | **Từ chối** khi analyst không có quyền đọc bucket |
| Truy vấn table nằm ngoài phạm vi được cấp | **Từ chối** nếu không có quyền kế thừa khác |
| Chỉnh URI/SQL table definition để trỏ tới một file khác | **Từ chối** nếu analyst không có quyền sửa table/delegate connection |
| Đọc file nguồn bằng connection SA thông qua BigQuery table | **Cho phép** theo table definition và policies |

Nếu analyst đọc trực tiếp bucket **thành công**, kiểm tra IAM ở bucket/project/organization, quyền từ Google Groups, impersonation và role đã cấp trước; không coi mô hình access delegation đã cách ly nguồn. Nếu query BigLake bị 403, kiểm tra **ba lớp**: job project → table permission → connection service account/bucket.

### 4.6. Dọn lab có kiểm soát

Theo thứ tự: lưu kết quả không chứa dữ liệu thật → data owner thu hồi quyền analyst → xóa **chính table lab** → thu hồi IAM bucket của connection SA → xóa **chính connection lab** nếu không còn consumer → chỉ xóa file `events.csv` và dataset lab nếu chắc chắn do bạn sở hữu.

~~~bash
# Đọc lại trước khi xóa, không chạy lệnh phá hủy trên resource dùng chung.
bq show "$PROJECT_ID:$DATASET.events_external"
bq show --connection "$PROJECT_ID.$LOCATION.$CONNECTION_ID"
gcloud storage ls "gs://$BUCKET/biglake-demo/$RUN_ID/"

# DỌN ĐÚNG TÀI NGUYÊN LAB sau khi owner phê duyệt:
# bq rm -t "$PROJECT_ID:$DATASET.events_external"
# gcloud storage buckets remove-iam-policy-binding "gs://$BUCKET" \
#   --member="serviceAccount:$CONNECTION_SA" \
#   --role="roles/storage.objectViewer"
# bq rm --connection "$PROJECT_ID.$LOCATION.$CONNECTION_ID"
# gcloud storage rm "gs://$BUCKET/biglake-demo/$RUN_ID/events.csv"
~~~

Các lệnh xóa đang **được comment** để tránh người học copy nhầm; phải xác minh chính xác resource/owner và phụ thuộc trước khi bật. Không xóa một bucket, dataset hoặc connection dùng chung chỉ để dọn bài tập.

## 5. Metadata caching: nhanh hơn nhưng phải hiểu độ mới

Với external table trỏ tới **rất nhiều files**, mỗi truy vấn có thể tốn công liệt kê/đọc metadata đối tượng. BigLake hỗ trợ **metadata caching** giúp giảm overhead này với một số format, nhưng đó là **cache metadata/file listing**, không phải cache toàn bộ dữ liệu kết quả query.

Hai tùy chọn quan trọng:

| Tùy chọn | Ý nghĩa | Đánh đổi |
| --- | --- | --- |
| `max_staleness` | Chỉ dùng metadata cache khi lần refresh vẫn còn trong ngưỡng chấp nhận | Cache quá cũ có thể quay về truy vấn metadata trực tiếp |
| `metadata_cache_mode = 'AUTOMATIC'` | Dịch vụ tự refresh theo chu kỳ, thường khoảng 30–60 phút | Độ trễ nhận biết file mới tùy chu kỳ refresh |
| `metadata_cache_mode = 'MANUAL'` | Pipeline/chủ dữ liệu chủ động chạy refresh theo lịch/cutover | Nếu quên refresh, query có thể dùng cache cũ hoặc fallback tùy staleness |

Ví dụ **một bảng khác** cho Parquet (không thay thế bảng CSV lab đang dùng):

~~~sql
CREATE EXTERNAL TABLE `PROJECT_ID.lake_curated.enrollments_cached`
WITH CONNECTION `PROJECT_ID.asia-southeast1.lake_connection`
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://LEARNING_LAKE/curated/enrollments/*.parquet'],
  max_staleness = INTERVAL 4 HOUR,
  metadata_cache_mode = 'MANUAL'
);
~~~

Khi pipeline đã ghi và xác minh các file, data owner có thể refresh:

~~~sql
-- Chạy job tại cùng BigQuery location với external table.
CALL BQ.REFRESH_EXTERNAL_METADATA_CACHE(
  'PROJECT_ID.lake_curated.enrollments_cached'
);
~~~

**Quy tắc quan trọng:**

- Chỉ dùng `max_staleness` từ **30 phút đến 7 ngày** nếu bật cache; bằng `0` là tắt.
- Cache quá thời hạn `max_staleness` thì query có thể **đọc metadata từ Cloud Storage** thay vì dùng cache; không tự coi đó là lệnh query phải fail.
- **Metadata cache sẽ hết hạn sau 7 ngày nếu không refresh.** Manual refresh cần quyền `bigquery.tables.update` và `bigquery.tables.updateData`, không cấp quyền này cho mọi analyst.
- Nếu thay **source URI**, việc cache tự động không nhất thiết cập nhật ngay: cần quy trình refresh thủ công theo tài liệu (có thể phải tạm chuyển mode sang MANUAL rồi về AUTOMATIC).
- Đọc dữ liệu qua table có thể chưa phản ánh ngay object mới/xóa khi metadata còn trong cache. Định nghĩa rõ “freshness SLA” và test cuối pipeline.
- Metadata cache refresh là job có thể tiêu thụ tài nguyên/chi phí; theo dõi cả hiệu năng và chi phí refresh.

**Không chọn staleness 7 ngày** cho dữ liệu vận hành cần cập nhật mỗi vài phút. Ngược lại, bảng Parquet bất biến theo kỳ kết toán có thể chấp nhận ngưỡng dài hơn nếu SLA cho phép.

## 6. Mở rộng: object tables, federated queries và Iceberg

BigLake là một phần của hệ sinh thái **lakehouse và quản trị dữ liệu**, nhưng không phải mọi nguồn ngoài BigQuery đều dùng cùng kiểu bảng và API.

### 6.1. Object tables: query metadata của đối tượng phi cấu trúc

Nếu bucket lưu ảnh chụp chứng chỉ, video giảng dạy hoặc PDF, một **object table** có thể biểu diễn file theo các hàng metadata, thay vì cố giải mã video/PDF thành những cột như CSV. Ví dụ:

~~~sql
-- Cần connection SA có quyền object và bucket được duyệt.
CREATE EXTERNAL TABLE `PROJECT_ID.lake_curated.course_assets`
WITH CONNECTION `PROJECT_ID.asia-southeast1.lake_connection`
OPTIONS (
  object_metadata = 'SIMPLE',
  uris = ['gs://LEARNING_LAKE/assets/*.pdf']
);
~~~

Object table giúp **lọc metadata/URI/size/type** và kết hợp các tác vụ xử lý dữ liệu không cấu trúc theo tính năng được hỗ trợ. Nó **không tự chuyển nội dung PDF thành văn bản** hay cung cấp full-text search toàn bộ file; cần pipeline/remote function/model phù hợp và quyền riêng.

### 6.2. Federated query đến cơ sở dữ liệu vận hành

Khi số lượt giao dịch mới nhất vẫn nằm trong Cloud SQL/AlloyDB/Spanner, có thể dùng connection và `EXTERNAL_QUERY` theo **database source dialect**:

~~~sql
-- MẪU TỔNG QUÁT: chỉ dùng với DB connection được admin phê duyệt.
SELECT *
FROM EXTERNAL_QUERY(
  'PROJECT_ID.asia-southeast1.approved_db_connection',
  'SELECT course_id, COUNT(*) AS cnt FROM enrollments GROUP BY course_id'
);
~~~

Đây **không phải** BigLake Cloud Storage table. `EXTERNAL_QUERY` gửi SQL tới DB ngoài rồi chuyển kết quả thành các kiểu dữ liệu tương ứng cho BigQuery; cần đánh giá connection credentials, network/database load, transaction consistency và độ trễ. Với OLTP production, một truy vấn full scan lớn qua federation có thể làm chậm hệ thống giao dịch. Cân nhắc sao chép dữ liệu sang warehouse/CDC khi workload báo cáo lớn.

### 6.3. Apache Iceberg managed tables: open format và ghi dữ liệu

**Apache Iceberg managed tables** (trước đây có tài liệu gọi BigLake tables for Apache Iceberg) cho phép BigQuery quản lý catalog/metadata và lưu dữ liệu ở **bucket người dùng sở hữu** dưới định dạng mở. Chúng hỗ trợ DML, streaming qua Storage Write API theo điều kiện sản phẩm, schema evolution và tối ưu file/metadata.

| Khả năng | BigLake external table Parquet/CSV | Apache Iceberg managed table |
| --- | --- | --- |
| Vị trí data | Files do hệ thống nguồn ghi trong bucket | Iceberg data/metadata trong bucket do người dùng sở hữu |
| BigQuery DML | **Không** sửa trực tiếp file qua `UPDATE`/`DELETE` | **Có** theo khả năng/giới hạn của managed table |
| Schema/transaction | File schema do producer kiểm soát, consistency external giới hạn | Có quản lý metadata/snapshot theo Iceberg và BigQuery |
| Truy cập từ engine khác | Có thể đọc cùng file Parquet/ORC | Đọc **Iceberg table metadata** bằng engine được hỗ trợ |
| Vận hành | Producer quản lý layout, schema, publication/cleanup | Dịch vụ tối ưu file/metadata theo cấu hình, vẫn cần IAM/giám sát |

**Đừng tự ghi/xóa file dưới đường storage URI của Iceberg managed table** mà không theo cơ chế quản lý được hỗ trợ; có thể làm hỏng metadata/snapshot. Khi yêu cầu transactional lakehouse, cần đánh giá Iceberg managed riêng, không dùng script ghi đè các file của BigLake external table.

## 7. Chính sách dữ liệu: bảo vệ hàng, cột và tenant

BigLake kết hợp **access delegation** với các chính sách phân quyền của BigQuery. Với Cloud Storage BigLake tables, có thể áp row-level access policies, column-level policy tags và data masking theo tính năng/edition được hỗ trợ.

### 7.1. Ví dụ row-level security theo tenant

Giả sử bảng `events_external` có dữ liệu nhiều tenants, analyst của tenant lab chỉ được xem `tenant_id='t-lab'`:

~~~sql
-- Chỉ data steward có quyền quản lý row access policies mới áp dụng.
CREATE ROW ACCESS POLICY only_lab_tenant
ON `YOUR_PROJECT.biglake_demo_lab.events_external`
GRANT TO ('group:approved-lab-analysts@example.com')
FILTER USING (tenant_id = 't-lab');
~~~

**Đây là ví dụ chính sách**, không yêu cầu thực hiện trong lab nếu chưa có Google Group thật/được phê duyệt. Các chính sách hàng phải được thiết kế **cho tất cả nhóm principal cần truy cập**; người không khớp policy có thể chỉ thấy các hàng được cho phép hoặc bị từ chối theo quy tắc sản phẩm. Test bằng **danh tính đại diện**, không chỉ dùng admin có nhiều quyền để kết luận chính sách đúng.

**Một bảng có row-level policy không làm cho file trong bucket được lọc**: một principal vẫn đọc được toàn bộ file nếu có `storage.objects.get` trực tiếp. Đó là lý do access delegation và không cấp đường đọc bypass là điều kiện bảo mật cốt lõi.

### 7.2. Column policy tags và masking

Ví dụ file có cột `learner_email` và `payment_amount`. Data steward có thể gắn policy tags để hạn chế quyền đọc giá trị gốc, cấp Fine-Grained Reader theo taxonomy được phê duyệt hoặc áp masking rule khi chỉ cần giá trị đã che. Cơ chế này **bổ sung** cho Data Viewer trên table, không thay thế các kiểm tra job permission và nguồn.

Quy trình an toàn:

1. Phân loại cột (public/internal/confidential), xác định mục đích sử dụng và owner.
2. Gắn policy tag và/hoặc masking policy theo khả năng BigLake table/location.
3. Cấp quyền đọc giá trị gốc cho ít principals nhất; đa số analyst chỉ đọc dữ liệu đã tổng hợp/được mask.
4. Kiểm thử `SELECT` cột được phép và cột bị hạn chế dưới các roles khác nhau.
5. Duyệt kỹ những **views, exports hoặc materialized copies** vì dữ liệu sao chép sang nơi khác cần chính sách bảo vệ tương đương.

**Không chọn `SELECT *` làm hợp đồng chia sẻ dữ liệu nhạy cảm.** Schema evolution có thể làm lộ cột mới cho người có quyền table hoặc làm query cũ thay đổi. Nên dùng **view projection có danh sách cột tường minh** đặt trên BigLake table, hoặc model curated theo nhu cầu nghiệp vụ.

### 7.3. Quyền dữ liệu nhiều tầng

~~~text
Organization policy / VPC Service Controls (nếu có)
    → IAM project / dataset / BigLake table
    → Query job permission + connection delegation
    → Row policies / column tags / masking
    → Cloud Storage bucket/object IAM của connection service account
    → Application authorization theo user/tenant và audit logs
~~~

Từng tầng bảo vệ rủi ro khác nhau. **VPC Service Controls không thay thế IAM**, IAM không tự áp row filter theo tenant và BigLake row filter không bảo vệ trực tiếp file khỏi principal có quyền bucket. Với Cloud Run/GKE chạy query, dùng workload service account riêng và không nhúng static service account key vào source/image.

## 8. Hiệu năng, khả dụng dữ liệu và chi phí

### 8.1. External table không tự nhanh như native table

| Vấn đề | Cách đánh giá | Hướng xử lý |
| --- | --- | --- |
| Nhiều files vài KB | File listing/metadata overhead lớn | Gom file thành Parquet cỡ phù hợp với workload |
| Query luôn quét nhiều ngày | Không lọc partition, URI wildcard quá rộng | Hive partition filter, phân vùng đúng query |
| CSV parse lâu | CPU/bytes scan lớn | Chuyển curated data sang Parquet/ORC |
| Metadata thay đổi thường xuyên | Cache stale hoặc refresh chưa chạy | Có publication/freshness SLA và refresh sau ETL |
| Dashboard query lặp mỗi phút | Re-scan external data, p95/chi phí cao | Load/materialize dữ liệu nóng vào BigQuery native |
| Dữ liệu vùng khác | Network/egress, residency/location mismatch | Chọn colocated locations và kiến trúc vùng phù hợp |
| Query ngoài lúc file bị xóa/ghi đè | Kết quả không nhất quán hoặc lỗi | File bất biến, staging + publish/rollback |

**BigQuery dry run** với nguồn ngoài có thể không ước lượng chính xác bytes; đôi khi trả **0 hoặc lower bound** dù query thật vẫn có chi phí. Đừng dùng dry run một mình để phê duyệt ngân sách. Đo job thực trên input lab, bytes billed/processed, Cloud Storage request/egress và connection metrics.

### 8.2. Mô hình chi phí tổng

\[
\text{TCO} \approx
C_{\text{BigQuery query/slots}}
+C_{\text{GCS storage/operations}}
+C_{\text{metadata refresh}}
+C_{\text{network/egress}}
+C_{\text{data pipeline/operations}}
\]

- **BigQuery:** phí query theo on-demand bytes processed hoặc slot/capacity editions tùy tổ chức.
- **Cloud Storage:** lưu trữ, số thao tác đọc/liệt kê, retrieval/egress theo class/location; có thể có phụ phí khi dùng lớp lưu trữ lạnh.
- **BigLake metadata cache:** refresh jobs/tài nguyên và chi phí vận hành lịch.
- **Multi-cloud:** có thể phát sinh phí BigQuery Omni, truyền dữ liệu và egress của nền tảng nguồn.
- **Quyền truy cập:** access delegation không làm dữ liệu “miễn phí”; cần budget/quota và kiểm soát query lớn.

**Budget alert không phải hard spending cap.** Có thể dùng reservation, quota và quyền query theo nhu cầu để giảm blast radius, nhưng chọn đơn giá/region phải tra trang giá chính thức tại thời điểm triển khai.

## 9. Runbook: truy vấn BigLake thất bại hoặc trả dữ liệu không như kỳ vọng

| Triệu chứng | Nguồn gốc có thể | Kiểm tra đầu tiên |
| --- | --- | --- |
| `Access Denied: bigquery.jobs.create` | Analyst không được tạo job tại execution project | Xem principal thực, IAM `roles/bigquery.jobUser` tại job project |
| `Access Denied` trên BigLake table | Thiếu `bigquery.tables.getData` hoặc chính sách hàng/cột | Kiểm tra Data Viewer trên table, policy tags, row policies |
| 403 từ Cloud Storage | Connection SA thiếu quyền đọc/list file hoặc bucket dùng deny/policy khác | `bq show --connection`, bucket IAM, đúng object path |
| Lỗi `bigquery.connections.delegate` khi tạo table | Người tạo table chưa được ủy quyền sử dụng connection | Data steward cấp quyền delegate trên đúng connection; không cấp Admin toàn project |
| Analyst đọc trực tiếp file nguồn thành công | IAM bucket/project/group quá rộng hoặc impersonation | Kiểm tra inherited roles, xóa đường bypass theo review |
| Query không thấy file mới | Metadata caching chưa refresh hoặc URI không match | Kiểm tra `max_staleness`, cache mode, URI wildcard, run manifest |
| Query không đọc được một file | File sai format/schema, bị xóa/đổi lúc query, permission lỗi | Kiểm tra file listing, schema, generation và ETL publication |
| Location mismatch | Dataset, connection, bucket không colocated | Đối chiếu supported locations; không đổi bucket production tùy tiện |
| Query chậm hoặc phí cao | Nhiều file nhỏ, CSV, thiếu filter, cross-region hoặc cache | Query plan/job stats, file layout, partition pruning, bytes |
| Chạy `UPDATE` lên external table thất bại | External table chỉ đọc bằng BigQuery DML | Dùng pipeline nguồn, native table hoặc Iceberg managed table theo nhu cầu |
| `EXTERNAL_QUERY` chậm và DB nguồn quá tải | Federation đẩy workload nặng vào OLTP | Giới hạn source query, cache/load vào warehouse và đo DB metrics |

### 9.1. Trình tự điều tra 403

1. **Xác định principal thật**: tài khoản người chạy `bq`, CI hoặc runtime service account Cloud Run/GKE.
2. **Xác định job project**: có `bigquery.jobs.create` không? Project tạo job có khác project chứa dataset không?
3. **Kiểm tra quyền BigLake table**: table ID, dataset location, row/column policies, IAM kế thừa.
4. **Kiểm tra connection**: connection ID đúng region? Được delegate để tạo table? Service account ID còn tồn tại?
5. **Kiểm tra Cloud Storage**: connection SA có quyền object trên URI hiện tại? Bucket IAM/deny policy đúng?
6. **Kiểm thử lại** bằng đúng principal và một query mới, ghi error code (ẩn tên bucket/PII khi gửi báo cáo).

Không cấp tạm `roles/editor`, `bigquery.admin` và `storage.admin` cùng lúc để chữa lỗi 403 — cách đó làm mất kiểm soát least privilege và có thể mở đường đọc dữ liệu thô.

### 9.2. Trường hợp query kết quả không nhất quán

Khi query sai số sau một lượt ETL:

1. Kiểm tra số file dự kiến so với file thực tế ở **prefix được công bố**.
2. Xác định producer có overwrite/delete file khi query đang chạy không.
3. Kiểm tra schema và bảng có refer đúng URI wildcard, partition/hive prefix không.
4. Nếu bật metadata caching, xem lần refresh cuối và staleness; chủ sở hữu chạy manual refresh khi phù hợp.
5. So kết quả query với source manifest, row counts và checksum/đối soát trên sample.
6. Khôi phục prefix/table definition phiên bản trước đã xác minh nếu cần, không xóa file ngay.

**Lỗi freshness không luôn là lỗi permissions**, và việc chạy lại query không chắc sửa được nếu cache/file publication vẫn sai.

## 10. Tình huống và bài tập

### A — Chia sẻ báo cáo nhưng không muốn mở bucket

Một doanh nghiệp có 2 TB Parquet trong Cloud Storage. Đội phân tích chỉ được xem thống kê `course_id` và `status`; cột `learner_email` nhạy cảm không được xuất. Đội muốn query qua BigQuery, không sao chép dữ liệu thô.

**Câu hỏi:** chọn non-BigLake external table hay BigLake? Quyền của analyst và connection SA là gì?

**Định hướng:** chọn **BigLake external table** với Cloud resource connection. Connection SA đọc bucket/prefix bằng object permissions; analyst có BigQuery Job User ở job project, Data Viewer ở BigLake table/view được duyệt, **không** có trực tiếp Storage Object Viewer. Dùng view chỉ chọn cột cần thiết, policy tags/masking nếu cần bảo vệ xuyên nhiều query; test query trực tiếp bucket bị từ chối.

### B — Một analyst có thể tự tạo external table mới

Data steward cấp cho nhóm analyst quyền `bigquery.connections.delegate` trên connection có thể đọc toàn bộ bucket chứa dữ liệu nhiều tenants. Một analyst dùng connection đó tạo external table vào file khác rồi đọc dữ liệu ngoài phạm vi báo cáo.

**Câu hỏi:** lỗi thiết kế nào dẫn tới điều này?

**Định hướng:** quyền **delegate/bind connection** được cấp quá rộng; bảng mới không thừa hưởng policy của bảng báo cáo đã review. Thu hẹp quyền tạo table/delegate, tách connection/bucket theo sensitivity, review IAM inherited và các đường bypass (`storage.objects.get`, ObjectRef). Không chỉ sửa view ban đầu.

### C — Metadata cache và SLA cập nhật 5 phút

Pipeline ghi Parquet mới mỗi 5 phút. BigLake table bật `metadata_cache_mode='AUTOMATIC'`, thường refresh cách nhau 30–60 phút, có `max_staleness=INTERVAL 4 HOUR`. Product owner yêu cầu báo cáo thấy file mới trong vòng 5 phút.

**Câu hỏi:** cấu hình đang đáp ứng SLA không?

**Định hướng:** **không thể cam kết** chỉ với automatic refresh. Metadata cache có thể chưa nhận file mới. Cần đánh giá tắt cache (đổi chi phí/latency), manual refresh sau mỗi publication hoặc dùng native/streaming sink phù hợp; đo end-to-end freshness và SLA thay vì chỉ cấu hình một giá trị staleness.

### D — Query ngày gần nhất rất chậm

Dữ liệu nằm trong hàng triệu file CSV dưới `gs://lake/events/*`. Dashboard luôn query **một ngày**, nhưng table không có partitioning, còn query dùng `SELECT *`.

**Câu hỏi:** đề xuất ba cải tiến ưu tiên.

**Định hướng:** (1) chuyển curated format sang **Parquet**, tránh file nhỏ; (2) tổ chức **Hive partitioning** theo ngày và dùng filter bắt buộc; (3) chỉ chọn cột cần thiết, đo metadata cache và query stats. Nếu dashboard chạy nhiều lần/phút, so với load/aggregation vào BigQuery native table.

### E — Data lake “có thể UPDATE”?

Đội muốn nhiều ứng dụng Spark và BigQuery cùng cập nhật trạng thái ghi danh, yêu cầu rollback phiên bản và quản lý snapshot. Họ tạo BigLake external table trỏ đến `events/*.parquet` rồi thử `UPDATE`.

**Câu hỏi:** giải pháp thay thế hợp lý là gì?

**Định hướng:** BigLake external table trên raw files **không hỗ trợ BigQuery DML**. Nếu phải có open lakehouse với transaction/schema evolution, đánh giá **Apache Iceberg managed tables** và phạm vi tương tác của từng engine; hoặc dùng native BigQuery table làm đích cập nhật. Không tự sửa file/manifest do managed Iceberg kiểm soát.

### F — Truy vấn BigQuery trực tiếp Cloud SQL làm OLTP chậm

Một job báo cáo BigQuery gọi `EXTERNAL_QUERY` quét toàn bảng `orders` trên Cloud SQL mỗi 5 phút. Khi chạy, CPU database tăng và request API bị chậm.

**Câu hỏi:** BigLake Cloud Storage table có tự giải quyết vấn đề không?

**Định hướng:** không. `EXTERNAL_QUERY` là federation trực tiếp tới DB vận hành, khác BigLake table. Cần query/filter có giới hạn, replica phù hợp hoặc CDC/ETL đưa dữ liệu phân tích vào Cloud Storage/BigQuery. Chọn thời gian đồng bộ, freshness và nguồn sự thật theo nghiệp vụ.

### Bài tập định lượng — metadata và lượt query

Một lake có **240.000 file** Parquet, tổng **12 TiB**. Dashboard chạy 50 lần/ngày và chỉ cần 1/24 dữ liệu (một giờ trong ngày). Giả định partition pruning loại đúng 23/24 tổng dữ liệu, kích thước phân bố đều.

1. **Lượng dữ liệu lý tưởng còn phải quét cho một query?** — `12 TiB / 24 = 0,5 TiB`, trước các tối ưu cột và overhead.
2. **Nếu không pruning, tổng dung lượng logic 50 lượt query là bao nhiêu?** — `50 × 12 = 600 TiB`.
3. **Nếu pruning hiệu quả, tổng còn bao nhiêu?** — `50 × 0,5 = 25 TiB`.
4. **Có thể đổi ngay các con số trên thành tiền billed chính xác không?** — **Không**; còn column pruning, format, metadata operations, cache, query plan, tier/capacity/giá và cơ chế đo bytes.
5. **Có nên bật metadata cache 7 ngày nếu file mới mỗi giờ?** — Chỉ khi chấp nhận độ mới tương ứng và có lịch refresh phù hợp; không lấy ngưỡng lớn làm giải pháp thay partitioning.

### Câu hỏi tự kiểm tra

1. **BigLake external table có lưu dữ liệu trong BigQuery storage không?** — Không; dữ liệu vẫn ở nguồn ngoài.
2. **BigLake và non-BigLake external table khác lớn nhất ở đâu?** — BigLake dùng connection service account để **ủy quyền truy cập nguồn**.
3. **Analyst BigLake có cần Storage Object Viewer ở bucket không?** — Không, và thường **không nên cấp**.
4. **Vì sao không cho analyst quyền delegate connection?** — Có thể tạo bảng riêng để đi vòng row/column controls của bảng được duyệt.
5. **Dữ liệu CSV/Parquet thay đổi trong lúc query có hoàn toàn nhất quán không?** — Không được bảo đảm như native table.
6. **Metadata caching có cache cả kết quả query không?** — Không; chủ yếu cache metadata của file/partition.
7. **External table có thể `UPDATE` bằng BigQuery SQL không?** — Không trong mô hình external table thông thường.
8. **Object table có tự đọc nội dung PDF thành cột không?** — Không; nó chủ yếu biểu diễn metadata đối tượng.
9. **`EXTERNAL_QUERY` có phải BigLake Cloud Storage table không?** — Không; đó là federation qua DB connection.
10. **Khi nào nên load vào BigQuery native?** — Khi query lặp cần độ trễ/hiệu năng hoặc consistency đáng tin, sau khi benchmark/TCO.

## 11. Checklist thiết kế và vận hành BigLake

| Kiểm tra | Tiêu chí chấp nhận |
| --- | --- |
| **Loại nguồn** | Chọn đúng BigLake, external table, object table, federation hoặc Iceberg theo format và read/write semantics |
| **Vị trí** | Dataset, connection, bucket colocated theo tài liệu; đáp ứng data residency |
| **Phạm vi IAM** | Query job permission, table Data Viewer và connection SA Storage Object Viewer đúng tài nguyên |
| **Chống bypass** | Analyst không có direct storage read, connection delegate/admin hoặc ObjectRef read không cần thiết |
| **Tách trách nhiệm** | Data steward duyệt table/schema/policies; ingestion pipeline chỉ ghi prefix; analyst chỉ query |
| **Schema** | Format và kiểu dữ liệu ổn định, có xử lý schema evolution/bad records/nullable values |
| **File layout** | Dùng Parquet/ORC khi phù hợp, partition theo query, hạn chế small files |
| **Freshness/consistency** | Có staging, manifest, publication, cache refresh và kiểm thử đọc ngay sau ETL |
| **Data security** | Row/column policies, masking, IAM, VPC Service Controls khi cần; kiểm thử âm tính |
| **Quan sát** | BigQuery job stats, Cloud Storage metrics, IAM audit logs, lỗi source/connection |
| **Chi phí** | Đo bytes/query, storage/requests, metadata refresh, egress, reservations/budgets |
| **Phục hồi** | Có version/prefix cũ, rollback table definition, quy trình xóa an toàn và owner |

### Quy trình review ủy quyền định kỳ

Hằng quý hoặc sau mỗi thay đổi kiến trúc, data steward cần kiểm kê **ai được đọc BigLake table**, **ai có thể delegate connection**, **connection SA đọc được những bucket nào** và **những bản sao/export nào tồn tại**. Một binding bị thu hồi ở table **không xóa** dữ liệu mà analyst đã xuất trước đó. Khi xử lý sự cố lộ dữ liệu, kiểm tra thêm audit logs, quyền kế thừa, service account impersonation và các bản sao.

## 12. Tài liệu Google Cloud chính thức

- [Introduction to external data sources](https://cloud.google.com/bigquery/docs/external-data-sources) — tổng quan BigLake, object tables, non-BigLake external tables và federation.
- [Introduction to BigLake tables](https://cloud.google.com/bigquery/docs/biglake-intro) — access delegation, định dạng/nguồn được hỗ trợ và mô hình bảo mật.
- [Create Cloud Storage BigLake tables](https://cloud.google.com/bigquery/docs/create-cloud-storage-table-biglake) — `CREATE EXTERNAL TABLE`, connection, Hive partitioning và ACL.
- [Cloud resource connections](https://cloud.google.com/bigquery/docs/create-cloud-resource-connection) — tạo connection và tìm serviceAccountId.
- [Introduction to external tables](https://cloud.google.com/bigquery/docs/external-tables) — giới hạn DML, consistency, location và hiệu năng.
- [Cloud Storage external tables](https://cloud.google.com/bigquery/docs/external-data-cloud-storage) — CSV, JSON, Parquet, Avro, ORC và schema.
- [Metadata caching for external data sources](https://cloud.google.com/bigquery/docs/metadata-caching-external-tables) — staleness, refresh mode, caching trade-offs.
- [BQ.REFRESH_EXTERNAL_METADATA_CACHE](https://cloud.google.com/bigquery/docs/reference/system-procedures#bqrefresh_external_metadata_cache) — cú pháp, quyền và refresh theo prefix.
- [Object tables](https://cloud.google.com/bigquery/docs/object-table-introduction) — metadata và đối tượng phi cấu trúc.
- [Federated queries](https://cloud.google.com/bigquery/docs/federated-queries-intro) — `EXTERNAL_QUERY` và nguồn database.
- [Apache Iceberg managed tables](https://cloud.google.com/bigquery/docs/biglake-iceberg-tables-in-bigquery) — so sánh mô hình open-format có DML.
- [BigQuery IAM](https://cloud.google.com/bigquery/docs/access-control), [row-level security](https://cloud.google.com/bigquery/docs/row-level-security-intro), [column-level security](https://cloud.google.com/bigquery/docs/column-level-security-intro) — chính sách dữ liệu.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) và [Cloud Storage pricing](https://cloud.google.com/storage/pricing) — lập dự toán chi phí.

**Kết luận:** BigLake tạo một lớp **metadata, truy vấn và quản trị quyền** trên dữ liệu đang nằm trong Cloud Storage hoặc object store được hỗ trợ. Điểm mạnh không chỉ là dùng SQL mà còn là **access delegation qua connection service account**: consumer được quyền đọc **bảng**, không cần quyền trên **file nguồn**. Một thiết kế production chỉ đáng tin khi đã chứng minh **least privilege, không có đường đọc bypass, schema/location đúng, độ mới của dữ liệu và tổng chi phí truy vấn**. Với nhu cầu DML lakehouse hoặc dashboard hiệu năng cao, phải đánh giá **Iceberg managed tables hoặc BigQuery native tables**, không mặc định mọi external table đều thay thế được chúng.
