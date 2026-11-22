# Table format Apache Iceberg và quản lý vòng đời bảng

Một data lake thường lưu dữ liệu dưới dạng các file Parquet, ORC hoặc Avro trên Amazon S3. Nhưng một thư mục chứa file chưa đủ để hoạt động như một bảng dữ liệu đáng tin cậy: hệ thống cần biết file nào thuộc bảng, schema hiện tại là gì, partition được tổ chức ra sao, thao tác ghi nào đã commit và truy vấn phải đọc phiên bản dữ liệu nào. Nếu mỗi engine tự suy luận danh sách file từ thư mục, việc cập nhật đồng thời, xóa bản ghi, thay đổi schema và đọc dữ liệu lịch sử trở nên khó kiểm soát.

Apache Iceberg là một open table format giải quyết lớp quản lý bảng này. Iceberg lưu metadata có phiên bản để mô tả tập data files, snapshot, schema và partition spec. Nhiều query engine có thể đọc cùng một bảng thông qua catalog chung, trong khi các thao tác ghi được commit theo cơ chế transaction của Iceberg.

Trên AWS, một kiến trúc phổ biến dùng Amazon S3 làm nơi lưu data và metadata files, AWS Glue Data Catalog làm catalog, AWS Lake Formation quản lý quyền truy cập, còn AWS Glue, Amazon EMR, Amazon Athena và Amazon Redshift đảm nhiệm ETL hoặc analytics. Điểm quan trọng là các engine phải tương thích với cùng table format version, catalog và cơ chế commit.

Bài học tập trung vào cấu trúc bảng Iceberg, snapshot và metadata tree, schema/partition evolution, time travel, concurrent writes và các công việc bảo trì như compaction, snapshot expiration và orphan file deletion.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vì sao Apache Iceberg là table format thay vì file format.
- Mô tả quan hệ giữa data files, metadata JSON, snapshots, manifest lists, manifests và catalog.
- Hiểu cách Iceberg commit thay đổi bảng và xử lý concurrent writers.
- Tạo và đọc bảng Iceberg trên Amazon S3 bằng AWS Glue và AWS Glue Data Catalog.
- Phân biệt Iceberg format v1, v2 và v3, đồng thời đánh giá compatibility giữa các engine.
- Áp dụng schema evolution và partition evolution mà không phải rewrite toàn bộ dữ liệu.
- Truy vấn snapshot lịch sử, time travel và metadata tables.
- Sử dụng Athena, Glue và Spark để ghi, cập nhật, xóa và tối ưu dữ liệu.
- Lập chính sách compaction, snapshot retention và orphan file cleanup an toàn.
- Thiết kế vòng đời bảng từ ingestion, query, governance, maintenance đến archive.

## 1. Apache Iceberg là gì?

Apache Iceberg là open table format dành cho analytic datasets lớn. Nó định nghĩa cách quản lý bảng trên object storage hoặc file storage bằng metadata có phiên bản, cho phép engine đọc một trạng thái bảng nhất quán và cập nhật bảng bằng các transaction.

Cần phân biệt ba lớp:

| Lớp | Ví dụ | Trách nhiệm |
|---|---|---|
| File format | Parquet, ORC, Avro | Mã hóa các hàng và cột trong một file. |
| Table format | Apache Iceberg | Quản lý tập file, schema, partition, snapshot, delete và commit. |
| Catalog | AWS Glue Data Catalog | Đăng ký tên bảng và trỏ tới metadata hiện tại của bảng. |

Parquet không tự biết rằng hàng trăm file trong một prefix S3 thuộc cùng một bảng hoặc file nào là phiên bản mới nhất. Iceberg cung cấp metadata để trả lời điều đó.

### 1.1. So sánh với Hive-style tables

Với Hive-style external table, metadata thường lưu danh sách partition trong catalog. Một partition vật lý có thể tương ứng với một thư mục như year=2026/month=11/day=20/. Khi thêm partition hoặc thay đổi cấu trúc, nhóm phải đồng bộ catalog và layout file.

Iceberg dùng hidden partitioning. Engine truy vấn theo cột nghiệp vụ; Iceberg áp dụng partition transform và metadata để xác định file cần đọc. Người dùng không phải tự quản lý partition directory như một phần của schema bảng.

| Nhu cầu | Hive-style table | Apache Iceberg |
|---|---|---|
| Theo dõi file thuộc bảng | Thường dựa vào location và partition metadata | Manifest và snapshot mô tả chính xác data files |
| Schema evolution | Phụ thuộc metastore và engine; rename có thể khó an toàn | Có field IDs và metadata schema evolution |
| Partition evolution | Thường cần tạo layout/partition mới và phối hợp metadata | Có thể thay partition spec, file cũ giữ spec cũ |
| Row-level update/delete | Không có transaction semantics thống nhất từ table format | Hỗ trợ DML qua delete files và snapshot commit |
| Time travel | Không có sẵn ở mức table format | Truy vấn snapshot lịch sử khi còn được giữ |
| Concurrent writes | Dễ phụ thuộc engine và quy ước vận hành | Có commit protocol và optimistic concurrency |

Iceberg không thay thế Amazon S3, Parquet hoặc query engine. Nó bổ sung metadata và transaction semantics để các thành phần đó làm việc với nhau như một bảng.

## 2. Kiến trúc metadata của một Iceberg table

Một Iceberg table thường có một root location trên S3. Bên trong location có data files và metadata files. Catalog lưu thông tin bảng và metadata location hiện hành.

~~~mermaid
flowchart TD
    C["AWS Glue Data Catalog"] --> M["Current metadata JSON"]
    M --> S["Current snapshot"]
    S --> ML["Manifest list"]
    ML --> MF1["Manifest A"]
    ML --> MF2["Manifest B"]
    MF1 --> D1["Parquet data files"]
    MF1 --> X1["Delete files (v2)"]
    MF2 --> D2["Parquet data files"]
    M --> SC["Schema + partition specs"]
    M --> H["Snapshot history"]
~~~

Trong Iceberg v1–v3, metadata tree thường có các thành phần:

| Thành phần | Vai trò |
|---|---|
| Data file | Chứa các hàng dữ liệu, thường là Parquet, ORC hoặc Avro. |
| Delete file | Ghi nhận các hàng bị xóa, chẳng hạn position deletes hoặc equality deletes trong Iceberg v2. |
| Manifest file | File metadata dạng Avro, liệt kê một nhóm data files hoặc delete files, partition values và column metrics. |
| Manifest list | File metadata của một snapshot, liệt kê các manifest và thông tin giúp query planning. |
| Snapshot | Trạng thái bảng tại một thời điểm, xác định tập file tạo nên dữ liệu của bảng. |
| Table metadata JSON | Lưu schema, partition specs, snapshots, properties, current snapshot và metadata references. |
| Catalog entry | Lưu tên bảng và vị trí metadata hiện hành để engine mở bảng. |

Một snapshot không phải bản sao đầy đủ của toàn bộ dữ liệu. Nó là một tập tham chiếu metadata tới các file bất biến. Nhiều snapshot có thể cùng tham chiếu những data files chưa thay đổi; một snapshot mới chỉ cần mô tả phần metadata thay đổi.

### 2.1. Tại sao metadata tree giúp query nhanh hơn?

Manifest chứa partition tuple và thống kê cột như lower/upper bounds, null counts hoặc value counts khi có. Query engine có thể loại bỏ manifest hoặc data file không thể chứa giá trị cần tìm trước khi đọc nội dung file.

Ví dụ, truy vấn:

~~~sql
SELECT order_id, amount
FROM analytics.orders
WHERE order_date = DATE '2026-11-20'
  AND customer_id = 'C-1001';
~~~

Engine dùng partition spec và manifest metrics để loại bỏ các file không liên quan. Sau đó chỉ đọc file còn khả năng chứa các hàng thỏa điều kiện.

Metadata pruning giúp giảm S3 requests, bytes scanned và thời gian query. Hiệu quả phụ thuộc chất lượng file layout, partition strategy, statistics và khả năng tận dụng metadata của query engine.

### 2.2. Metadata không đồng nghĩa với dữ liệu

Data files và metadata files là hai loại đối tượng khác nhau. Xóa một metadata file đang được catalog hoặc snapshot tham chiếu có thể làm bảng không đọc được. Xóa data file đang được snapshot hiện hành tham chiếu có thể làm query lỗi hoặc thiếu dữ liệu.

Không dùng S3 Lifecycle expiration để xóa file bên trong table location theo tuổi object một cách độc lập với Iceberg. Việc xóa file phải đi theo snapshot expiration hoặc orphan file cleanup có hiểu biết về metadata.

## 3. Snapshot và transaction commit

Snapshot biểu diễn trạng thái bảng sau một lần commit. Khi writer append, update, delete hoặc rewrite dữ liệu, Iceberg tạo data/delete files mới và metadata mới rồi commit một snapshot.

Một commit điển hình:

1. Writer đọc metadata hiện tại và current snapshot.
2. Writer tạo data files hoặc delete files mới.
3. Writer tạo manifest và manifest list cho thay đổi.
4. Writer tạo metadata JSON mới trỏ tới snapshot mới.
5. Writer yêu cầu catalog cập nhật metadata location hiện hành bằng thao tác atomic commit.
6. Nếu commit thành công, snapshot mới trở thành trạng thái bảng hiện tại.
7. Nếu một writer khác đã commit trước, writer hiện tại có thể gặp conflict và phải refresh metadata, đánh giá lại thay đổi rồi retry.

Iceberg dùng optimistic concurrency: nhiều writer có thể chuẩn bị thay đổi song song, nhưng chỉ commit thành công khi metadata hiện hành vẫn thỏa điều kiện của transaction. Cơ chế conflict validation giúp tránh ghi đè mù lên thay đổi của writer khác.

### 3.1. Snapshot isolation

Một query mở bảng tại snapshot cụ thể sẽ đọc nhất quán tập file của snapshot đó. Nếu writer commit snapshot mới trong lúc query đang chạy, query hiện tại không tự trộn một phần file cũ với file mới.

Các query bắt đầu sau commit sẽ thấy snapshot mới. Đây là nền tảng cho snapshot isolation ở cấp bảng.

Không nên hiểu điều này là mọi thao tác ứng dụng đều exactly-once. Nếu producer retry sau timeout, application vẫn cần idempotency key hoặc cơ chế deduplicate để tránh ghi cùng một business event nhiều lần.

### 3.2. Commit conflict

Conflict có thể xảy ra khi:

- Hai writer cùng cập nhật một partition hoặc cùng tập file.
- Một writer đang compaction trong khi writer khác append/update cùng vùng dữ liệu.
- Metadata bị thay đổi bởi một transaction khác trước khi commit.
- Catalog lock/permission hoặc network call bị lỗi.

Cách xử lý:

- Dùng retry có giới hạn và backoff.
- Refresh metadata mới nhất trước khi tính lại commit.
- Tránh nhiều writer không phối hợp cùng ghi một bảng nóng.
- Chia workload theo partition hoặc batch boundary khi hợp lý.
- Tách maintenance job khỏi giờ ingest cao điểm nếu có xung đột dữ liệu.
- Theo dõi commit failure và retry count thay vì chỉ quan sát job exit code.

## 4. AWS Glue Data Catalog và catalog integration

AWS Glue Data Catalog là catalog phổ biến để đăng ký Iceberg tables trên AWS. Catalog lưu database/table metadata và vị trí metadata file hiện hành. Amazon S3 lưu data và metadata files thực tế.

Các query/ETL engines có thể dùng cùng catalog để tìm một bảng:

- AWS Glue Spark đọc và ghi Iceberg qua GlueCatalog.
- Amazon EMR Spark hỗ trợ Iceberg theo phiên bản EMR.
- Amazon Athena đọc, time travel, DML và DDL trong phạm vi hỗ trợ.
- Amazon Redshift có thể query Iceberg tables được catalog trong AWS Glue.
- Lake Formation cung cấp cơ chế quản trị quyền truy cập cho các engine được tích hợp.

### 4.1. Catalog là nguồn định danh bảng

Một bảng có tên analytics.orders được phân giải qua catalog/database/table. Catalog trả metadata location; Iceberg reader đọc metadata JSON và đi theo snapshot/manifest tree.

Nếu một engine tự ghi file Parquet vào đúng S3 prefix nhưng không commit metadata Iceberg, file mới không tự động trở thành một phần của bảng. Tương tự, thay đổi Glue table location thủ công không phải cách cập nhật transaction state của Iceberg.

### 4.2. Optimistic locking và phiên bản Glue

AWS Glue 4.0 trở lên dùng optimistic locking mặc định cho Iceberg Glue Catalog. AWS Glue 3.0 với Iceberg 0.13.1 yêu cầu cấu hình DynamoDB lock manager để bảo đảm atomic transaction theo hướng dẫn của AWS.

Không cấu hình nhiều cơ chế locking không tương thích cho cùng một bảng. Nếu bảng được nhiều engine dùng chung, cần xác minh tất cả engine sử dụng catalog/commit behavior tương thích.

### 4.3. Compatibility giữa engine là điều kiện bắt buộc

Không phải engine nào cũng hỗ trợ cùng một Iceberg format version hoặc toàn bộ tính năng.

Tại thời điểm tài liệu AWS hiện hành được tham chiếu trong bài:

| Engine/runtime | Hỗ trợ cần lưu ý |
|---|---|
| AWS Glue 6.0 | Hỗ trợ Iceberg format v2 và v3; mặc định tạo bảng v2. |
| AWS Glue 5.1 | Bundled Iceberg 1.10.0. |
| AWS Glue 5.0 | Bundled Iceberg 1.7.1. |
| AWS Glue 4.0 | Bundled Iceberg 1.0.0. |
| AWS Glue 3.0 | Bundled Iceberg 0.13.1; cần cấu hình DynamoDB lock manager. |
| Amazon Athena engine version 3 | Hỗ trợ Iceberg 1.4.2 và chỉ tạo/vận hành bảng format v2. |
| Amazon EMR | Iceberg được hỗ trợ native từ EMR 6.5.0; version và feature cụ thể phụ thuộc release/framework. |
| Amazon Redshift | Có thể query Iceberg v1/v2 qua Glue Data Catalog; kiểm tra giới hạn theo Region và engine. |

Nếu một bảng được đọc bởi Athena và Glue 6.0, hãy giữ format v2 trừ khi đã xác nhận mọi engine downstream hỗ trợ v3. Iceberg v3 là thay đổi một chiều; không thể downgrade bảng v3 trở lại v2.

## 5. Tạo bảng Iceberg bằng Amazon Athena

Athena engine version 3 có thể tạo Iceberg table trong AWS Glue Data Catalog và lưu dữ liệu trên S3.

Ví dụ tạo bảng orders:

~~~sql
CREATE TABLE analytics.orders (
    order_id STRING,
    customer_id STRING,
    order_ts TIMESTAMP,
    order_date DATE,
    amount DECIMAL(12, 2),
    status STRING
)
PARTITIONED BY (order_date, bucket(32, customer_id))
LOCATION 's3://company-data-lake/warehouse/orders/'
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'PARQUET'
);
~~~

Ví dụ trên dùng ngày nghiệp vụ và bucket theo customer làm partition fields. Phần partition evolution bên dưới minh họa thêm transform ngày trực tiếp từ timestamp. Hãy chọn transform theo query pattern, cardinality và phân bố dữ liệu; không sao chép nguyên partition strategy này cho mọi bảng.

### 5.1. Tạo bảng từ dữ liệu có sẵn

Có thể dùng CTAS để tạo Iceberg table từ query:

~~~sql
CREATE TABLE analytics.orders_iceberg
WITH (
    table_type = 'ICEBERG',
    format = 'PARQUET',
    location = 's3://company-data-lake/warehouse/orders_iceberg/'
) AS
SELECT
    order_id,
    customer_id,
    order_ts,
    order_date,
    amount,
    status
FROM staging.orders;
~~~

Location của bảng Iceberg phải được dành riêng cho bảng đó. Trước khi chạy CTAS, kiểm tra prefix S3 chưa chứa dữ liệu của bảng khác hoặc object không thuộc Iceberg.

## 6. Đọc và ghi Iceberg bằng AWS Glue Spark

AWS Glue 3.0 trở lên hỗ trợ Iceberg framework. Với Glue job dùng Spark, cần bật Iceberg và cấu hình Glue Catalog.

Các tham số cấu hình điển hình:

~~~text
--datalake-formats iceberg

--conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions

--conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog

--conf spark.sql.catalog.glue_catalog.warehouse=s3://company-data-lake/warehouse/

--conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog

--conf spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO
~~~

Tên catalog glue_catalog là alias Spark session. warehouse là root location; GlueCatalog kết nối AWS Glue Data Catalog; S3FileIO đọc/ghi object trên S3.

### 6.1. Tạo bảng và append dữ liệu

Ví dụ PySpark:

~~~python
# Create a new Iceberg table in the Glue Data Catalog.
df.writeTo("glue_catalog.analytics.orders") \
    .tableProperty("format-version", "2") \
    .create()

# Append a new batch to the existing table.
next_batch.writeTo("glue_catalog.analytics.orders") \
    .append()
~~~

Có thể tạo bảng bằng SQL:

~~~sql
CREATE TABLE glue_catalog.analytics.orders (
    order_id STRING,
    customer_id STRING,
    order_ts TIMESTAMP,
    amount DECIMAL(12, 2),
    status STRING
)
USING iceberg
TBLPROPERTIES ('format-version' = '2');
~~~

Trong môi trường có nhiều engine, hãy chọn format version theo engine có tập tính năng thấp nhất cần đọc/ghi bảng. Cấu hình trên minh họa format v2 để tương thích với Athena engine 3.

### 6.2. Đọc bảng từ Glue Catalog

~~~python
orders_df = spark.read \
    .format("iceberg") \
    .load("glue_catalog.analytics.orders")

orders_df.createOrReplaceTempView("orders")
spark.sql("""
    SELECT status, COUNT(*) AS total_orders
    FROM orders
    GROUP BY status
""").show()
~~~

Nếu bảng đăng ký với Lake Formation, cần cấu hình Glue job và IAM/Lake Formation permissions theo hướng dẫn cho runtime đang dùng. Glue 5.0 trở lên có hướng dẫn fine-grained access control riêng; Glue 4.0 cần các cấu hình Lake Formation tương ứng.

## 7. Iceberg format v1, v2 và v3

Iceberg format version quyết định cấu trúc metadata và các capability mà writer/reader có thể dùng.

| Version | Điểm chính | Khi cân nhắc |
|---|---|---|
| v1 | Quản lý immutable data files và snapshot metadata cơ bản. | Hệ thống cũ hoặc engine chỉ hỗ trợ v1. |
| v2 | Bổ sung row-level delete files, sequence numbers và hỗ trợ update/delete theo mô hình Iceberg. | Lựa chọn phổ biến khi cần DML và interoperability với Athena. |
| v3 | Bổ sung capability mới như VARIANT, timestamp precision nanosecond và geospatial types theo runtime hỗ trợ. | Khi toàn bộ writer/reader đã hỗ trợ v3 và có nhu cầu rõ ràng. |

### 7.1. Chọn version theo engine thấp nhất

Một lakehouse có thể có Glue Spark ghi bảng, Athena truy vấn ad-hoc và Redshift làm warehouse analytics. Nếu một engine chỉ hỗ trợ v2, việc chuyển bảng sang v3 có thể làm engine đó không đọc được.

Trước khi nâng version, lập ma trận compatibility cho:

- Runtime và Iceberg library version.
- Catalog implementation.
- File format và compression.
- Delete file semantics.
- Schema/type support.
- Time travel và metadata table support.
- Maintenance procedures và optimizer.

### 7.2. Nâng v2 lên v3

AWS Glue 6.0 hỗ trợ tạo bảng v3 bằng table property format-version=3. Nâng bảng v2 lên v3 là metadata change, không rewrite toàn bộ data files, nhưng là thay đổi một chiều.

~~~sql
ALTER TABLE glue_catalog.analytics.orders
SET TBLPROPERTIES ('format-version' = '3');
~~~

Chỉ thực hiện sau khi kiểm tra reader/writer, query engine, backup/rollback strategy và môi trường test. Nếu Athena vẫn là consumer, giữ v2 theo compatibility hiện hành.

## 8. Schema evolution

Schema evolution cho phép thay đổi cấu trúc bảng qua metadata mà không phải rewrite toàn bộ data files.

Các thay đổi thường được hỗ trợ:

- Add: thêm cột.
- Drop: bỏ cột.
- Rename: đổi tên cột.
- Reorder: đổi thứ tự hiển thị cột.
- Type promotion: mở rộng một số kiểu dữ liệu tương thích, ví dụ integer sang bigint, float sang double hoặc tăng precision của decimal trong phạm vi được hỗ trợ.

Ví dụ:

~~~sql
ALTER TABLE analytics.orders
ADD COLUMNS (sales_channel STRING);

ALTER TABLE analytics.orders
RENAME COLUMN status TO order_status;

ALTER TABLE analytics.orders
DROP COLUMN sales_channel;
~~~

### 8.1. Field ID quan trọng hơn vị trí cột

Iceberg dùng field IDs ổn định để định danh cột. Khi đổi tên cột, field ID vẫn giữ nguyên nên reader có thể hiểu dữ liệu cũ theo schema mới.

Không nên giả định cột thứ ba trong mọi data file luôn là amount. Một số file được ghi dưới schema cũ, file khác dưới schema mới. Iceberg dùng field IDs và schema metadata để ánh xạ đúng cột.

### 8.2. Type promotion và tính tương thích

Không phải mọi phép đổi kiểu đều an toàn. Ví dụ, chuyển bigint thành int có thể làm mất dữ liệu; chuyển string thành timestamp cần parse và kiểm tra giá trị lỗi.

Trước khi đổi kiểu:

1. Kiểm tra dữ liệu thực tế và null/invalid values.
2. Xác nhận reader/writer hỗ trợ phép promotion.
3. Kiểm tra downstream schema contract.
4. Thử query dữ liệu cũ và mới.
5. Ghi lại schema change trong data contract hoặc catalog documentation.

## 9. Partition evolution và hidden partitioning

Partitioning giúp query engine loại bỏ file không liên quan. Tuy nhiên, một partition strategy có thể trở nên kém hiệu quả khi workload thay đổi.

Ví dụ ban đầu partition theo ngày, nhưng sau này bảng có nhiều dữ liệu và query chủ yếu theo customer. Iceberg cho phép thêm partition spec mới mà không bắt buộc rewrite toàn bộ file cũ.

### 9.1. Partition transforms

Các transform phổ biến:

| Transform | Ví dụ | Ý nghĩa |
|---|---|---|
| identity | category | Dùng nguyên giá trị cột. |
| year | year(order_ts) | Nhóm theo năm. |
| month | month(order_ts) | Nhóm theo tháng. |
| day | day(order_ts) | Nhóm theo ngày. |
| hour | hour(event_ts) | Nhóm theo giờ. |
| bucket | bucket(32, customer_id) | Hash vào một số bucket cố định. |
| truncate | truncate(10, postal_code) | Cắt giá trị theo độ rộng. |

Ví dụ partition spec:

~~~sql
CREATE TABLE analytics.events (
    event_id STRING,
    event_ts TIMESTAMP,
    customer_id STRING,
    event_type STRING,
    payload STRING
)
PARTITIONED BY (day(event_ts), bucket(32, customer_id))
LOCATION 's3://company-data-lake/warehouse/events/'
TBLPROPERTIES ('table_type' = 'ICEBERG');
~~~

### 9.2. Đổi partition spec không rewrite file cũ

Khi partition spec thay đổi:

- File cũ tiếp tục dùng partition spec cũ.
- File mới được ghi theo spec mới.
- Manifest ghi lại spec ID và partition tuple của file.
- Query planner hiểu từng spec và tạo predicate phù hợp để prune file.

Vì vậy, bảng có thể chứa file thuộc nhiều partition spec. Không nên tự đổi tên hoặc di chuyển folder S3 để mô phỏng partition evolution.

Athena hỗ trợ hidden partitioning khi tạo bảng, nhưng một số thao tác partition DDL kiểu Hive như SHOW PARTITIONS, ALTER TABLE ADD/DROP PARTITION không áp dụng cho Iceberg. Hãy thay đổi partition spec bằng engine và cú pháp được hỗ trợ cho phiên bản đang dùng.

### 9.3. Chọn partition strategy

Tránh partition quá chi tiết dẫn tới hàng triệu partition/file nhỏ. Tránh partition theo cột có cardinality cực cao như transaction ID. Chọn partition dựa trên:

- Predicate thường xuất hiện trong query.
- Kích thước và phân bố dữ liệu.
- Tốc độ ingest và tần suất update.
- Mức độ skew.
- Khả năng compaction.
- Số file và manifest mà query phải xử lý.

Partitioning không thay thế sort order hoặc clustering. Với query filter nhiều chiều, có thể cần sort/Z-order compaction thay vì tạo thêm partition levels.

## 10. Time travel và version travel

Mỗi snapshot đại diện cho một trạng thái bảng. Khi snapshot còn được giữ, query engine có thể đọc dữ liệu tại thời điểm hoặc snapshot ID trước đó.

Time travel hữu ích cho:

- Điều tra dữ liệu thay đổi bất thường.
- So sánh số liệu trước và sau một batch.
- Khôi phục logic sau khi pipeline ghi sai.
- Reproduce kết quả báo cáo lịch sử.
- Audit và kiểm tra lineage.

Ví dụ Athena time travel theo timestamp:

~~~sql
SELECT *
FROM analytics.orders
FOR TIMESTAMP AS OF TIMESTAMP '2026-11-20 08:00:00';
~~~

Ví dụ version travel theo snapshot ID:

~~~sql
SELECT *
FROM analytics.orders
FOR VERSION AS OF 1234567890123456789;
~~~

Snapshot ID trong ví dụ là minh họa. Hãy lấy ID thực từ metadata table $snapshots.

### 10.1. Xem snapshot history

~~~sql
SELECT
    committed_at,
    snapshot_id,
    parent_id,
    operation,
    manifest_list
FROM "analytics"."orders$snapshots";
~~~

Có thể xem history:

~~~sql
SELECT *
FROM "analytics"."orders$history"
ORDER BY made_current_at DESC;
~~~

Metadata tables như $files, $manifests, $partitions, $snapshots, $history và $refs giúp quan sát cấu trúc bảng. Quyền Lake Formation row/cell filters có thể hạn chế truy vấn một số metadata tables; hãy kiểm tra access policy khi gặp AccessDeniedException.

### 10.2. Time travel không phải backup vô thời hạn

Time travel chỉ hoạt động khi snapshot và các data files cần thiết còn được giữ. Khi snapshot bị expire và file không còn được snapshot khác tham chiếu, dữ liệu có thể bị xóa.

Nếu cần audit lâu dài, hãy xác định snapshot retention phù hợp hoặc xuất dữ liệu/bằng chứng sang kho lưu trữ riêng. Đừng hứa khả năng khôi phục một snapshot đã bị expire.

## 11. Insert, update, delete và merge

Iceberg v2 hỗ trợ row-level changes bằng delete files. Writer có thể sử dụng position deletes hoặc equality deletes tùy engine và write mode.

Một số engine có thể thực hiện:

~~~sql
INSERT INTO analytics.orders
VALUES ('O-9001', 'C-1001', TIMESTAMP '2026-11-20 09:00:00', DATE '2026-11-20', 125.50, 'NEW');

UPDATE analytics.orders
SET status = 'SHIPPED'
WHERE order_id = 'O-9001';

DELETE FROM analytics.orders
WHERE order_id = 'O-9001';
~~~

Ví dụ MERGE INTO để upsert:

~~~sql
MERGE INTO analytics.customers target
USING staging.customer_changes source
ON target.customer_id = source.customer_id
WHEN MATCHED THEN
    UPDATE SET
        email = source.email,
        updated_at = source.updated_at
WHEN NOT MATCHED THEN
    INSERT (customer_id, email, updated_at)
    VALUES (source.customer_id, source.email, source.updated_at);
~~~

Cú pháp và DML support phụ thuộc query engine/version. Athena engine 3 hỗ trợ INSERT, UPDATE, DELETE và MERGE trên Iceberg v2; các thao tác UPDATE/DELETE/MERGE của Athena dùng merge-on-read với positional deletes, không chuyển sang copy-on-write chỉ vì table properties yêu cầu.

### 11.1. Merge-on-read và copy-on-write

| Chiến lược | Cách hoạt động | Trade-off |
|---|---|---|
| Copy-on-write | Rewrite data files chứa hàng bị thay đổi. | Read đơn giản hơn nhưng write có thể tốn nhiều I/O. |
| Merge-on-read | Ghi delete files và data files mới; reader hợp nhất khi query. | Write nhanh hơn trong nhiều trường hợp, nhưng query có thêm chi phí xử lý delete files. |

Sau nhiều update/delete theo merge-on-read, cần compaction để áp dụng delete files vào data files và giảm chi phí đọc.

## 12. Compaction và tối ưu layout file

Một pipeline streaming hoặc micro-batch có thể tạo nhiều file nhỏ. Hàng triệu file nhỏ làm tăng S3 requests, metadata size, planning overhead và query latency.

Compaction đọc các file hiện có, ghi lại thành ít file lớn hơn và commit snapshot mới. Snapshot cũ vẫn tồn tại theo retention policy, nên file cũ có thể chưa được xóa ngay.

Các chiến lược:

- **Binpack:** gom file nhỏ thành file lớn hơn; là chiến lược phổ biến.
- **Sort:** sắp xếp dữ liệu theo cột query thường lọc để tăng data skipping.
- **Z-order:** cluster dữ liệu theo nhiều chiều để hỗ trợ query lọc nhiều cột.

Không đặt một target file size cố định cho mọi workload. Kích thước phù hợp phụ thuộc engine, query concurrency, object size, parallelism, file group, memory và data volume.

### 12.1. Compaction bằng Athena

Athena engine 3 hỗ trợ OPTIMIZE cho Iceberg:

~~~sql
OPTIMIZE analytics.orders
REWRITE DATA USING BIN_PACK;
~~~

Có thể giới hạn bằng predicate partition:

~~~sql
OPTIMIZE analytics.orders
REWRITE DATA USING BIN_PACK
WHERE order_date = DATE '2026-11-20';
~~~

Với Athena, predicate trong OPTIMIZE chỉ hỗ trợ partition columns. Chi phí compaction phụ thuộc lượng dữ liệu được scan/rewrite. Athena phù hợp với bin-pack compaction đơn giản; sort/Z-order nâng cao nên cân nhắc Spark trên AWS Glue hoặc EMR.

### 12.2. Compaction bằng Spark

Spark có thể gọi Iceberg system procedure:

~~~sql
CALL glue_catalog.system.rewrite_data_files(
    table => 'analytics.orders',
    strategy => 'binpack'
);
~~~

Có thể đặt target size hoặc chọn sort strategy theo query pattern. Với bảng lớn, chia file groups và giới hạn concurrency để tránh driver/executor memory pressure.

Không chạy compaction cùng lúc với nhiều writer không được phối hợp trên cùng partition. Với bảng có ingest liên tục, chọn cold partitions hoặc thiết kế partial progress để giảm phạm vi conflict.

## 13. Snapshot retention và expire snapshots

Snapshot retention kiểm soát số snapshot và thời gian lịch sử được giữ. Nếu không expire snapshot, metadata và data files cũ có thể tăng theo thời gian, làm tăng chi phí S3 và metadata operations.

Ví dụ Spark procedure:

~~~sql
CALL glue_catalog.system.expire_snapshots(
    table => 'analytics.orders',
    older_than => TIMESTAMP '2026-11-13 00:00:00',
    retain_last => 10
);
~~~

Ví dụ Athena:

~~~sql
VACUUM analytics.orders;
~~~

VACUUM của Athena thực hiện snapshot expiration và orphan file removal theo cấu hình table properties. Sau khi snapshot bị expire, không thể time travel về snapshot đó.

### 13.1. Xây retention policy theo business

Một policy nên xét:

- Yêu cầu audit và compliance.
- Khoảng thời gian phát hiện lỗi dữ liệu.
- Thời gian pipeline có thể cần backfill.
- Thời gian rollback sau release.
- Chi phí lưu trữ và query history.
- Các branch/tag hoặc snapshot reference được bảo vệ.

Ví dụ, bảng raw ingestion có thể cần giữ history lâu hơn bảng aggregate có thể tái tạo từ raw. Bảng phục vụ báo cáo tài chính có thể cần retention và archive policy theo yêu cầu pháp lý.

Không chọn retention 1–2 ngày chỉ vì tiết kiệm S3 nếu nhóm thường mất nhiều ngày mới phát hiện dữ liệu sai.

## 14. Orphan files và cleanup an toàn

Orphan files là các object nằm trong table location nhưng không còn được Iceberg metadata tham chiếu. Chúng có thể xuất hiện khi:

- Job ghi file thành công nhưng commit thất bại.
- Compaction hoặc rewrite bị dừng giữa chừng.
- Pipeline retry tạo file tạm không được commit.
- Snapshot expiration xóa metadata reference nhưng không xóa associated files.
- Người vận hành xóa hoặc thay đổi dữ liệu sai quy trình.

Orphan file cleanup giúp thu hồi storage. Tuy nhiên, nếu cleanup chạy quá sớm, nó có thể xóa file mà writer đang chuẩn bị commit hoặc file nằm trong một table khác cùng location.

### 14.1. Quy tắc an toàn

- Mỗi Iceberg table nên có S3 location riêng, không dùng chung prefix với table/data source khác.
- Retention period của orphan cleanup phải lớn hơn thời gian tối đa từ lúc tạo file tới khi commit thành công, kể cả retry và delay.
- Không áp dụng S3 Lifecycle expiration xóa data/metadata files của Iceberg theo tuổi object.
- Kiểm tra optimizer logs và scope location trước khi bật.
- Thử nghiệm trên bảng test và xác minh snapshot/query sau cleanup.
- Không tự xóa metadata JSON, manifest hoặc data file bằng script dọn prefix.

AWS Glue orphan file deletion optimizer mặc định giữ orphan file trong 3 ngày; có thể cấu hình lại và giá trị tối thiểu là 1 ngày. Optimizer chỉ xóa file đáp ứng age criteria và tạo sau ngày optimizer được tạo. Nếu table location chứa dữ liệu của bảng khác, optimizer có thể xác định nhầm file và xóa dữ liệu không thuộc bảng.

## 15. AWS Glue table optimizers

AWS Glue Data Catalog có thể quản lý ba optimizer cho Iceberg tables:

| Optimizer | Mục đích | Kết quả |
|---|---|---|
| Compaction | Gộp file nhỏ, rewrite layout, có thể sort/Z-order theo cấu hình | Giảm file count, metadata overhead và query scan |
| Snapshot retention | Expire snapshot cũ theo age/count policy | Giảm storage và metadata history |
| Orphan file deletion | Xóa file không còn được metadata tham chiếu | Thu hồi storage bị chiếm bởi file mồ côi |

Có thể bật optimizer ở cấp table bằng Glue console, CLI hoặc API; catalog-level optimization giúp áp dụng default cho các bảng mới/cập nhật. Cấu hình riêng của table có thể có precedence so với catalog defaults.

### 15.1. Quyền cho optimizer

Glue optimizer assume một IAM role được chỉ định. Role cần quyền truy cập S3, Glue Data Catalog, CloudWatch Logs/metrics và KMS khi dữ liệu được mã hóa bằng customer managed key.

Quyền cần thiết khác nhau theo optimizer. Compaction và snapshot retention có thể cần đọc/ghi data và metadata; orphan deletion cần quyền liệt kê/xóa object theo scope. Hãy dùng policy tối thiểu, chỉ giới hạn vào catalog/database/table và S3 prefix cần thiết.

Nếu bucket yêu cầu VPC endpoint hoặc network path riêng, cấu hình Glue network connection phù hợp. Đối với Lake Formation registered tables, role và Lake Formation grants cần đáp ứng yêu cầu của optimizer.

### 15.2. Theo dõi optimizer runs

Kiểm tra:

- Optimizer enabled/disabled.
- Last run status và thời điểm chạy.
- Số file được rewrite/deleted.
- Lỗi IAM, KMS, S3 hoặc Glue.
- CloudWatch logs và metrics.
- Ảnh hưởng tới query latency và storage size.

Không coi optimizer enabled là đồng nghĩa maintenance đã thành công. Cần xem run history và kết quả thực tế.

## 16. Tích hợp các engine AWS

### 16.1. AWS Glue

Glue Spark phù hợp cho ETL, streaming/micro-batch, merge, schema/partition evolution và maintenance bằng Spark procedures. Glue Data Catalog là catalog entry point.

### 16.2. Amazon EMR

EMR cung cấp Spark, Flink, Hive và các framework xử lý dữ liệu khác. Iceberg được hỗ trợ native từ EMR 6.5.0; feature/version cụ thể phụ thuộc EMR release và framework. Dùng EMR khi cần kiểm soát cluster, library version, custom Spark tuning hoặc xử lý khối lượng lớn.

### 16.3. Amazon Athena

Athena phù hợp truy vấn SQL serverless, ad-hoc analysis, DML v2, time travel, metadata tables, OPTIMIZE và VACUUM. Athena có giới hạn format/version riêng; hiện tài liệu chỉ ra Iceberg 1.4.2 và v2. Kiểm tra lại support trước khi nâng version hoặc dùng type mới.

### 16.4. Amazon Redshift

Redshift có thể query Iceberg tables được catalog trong AWS Glue thông qua external schema, join với local Redshift tables và dùng Iceberg metadata statistics để tối ưu query. Redshift hỗ trợ query Iceberg v1/v2, time travel read-only và một số transaction semantics theo hướng dẫn của dịch vụ.

Ví dụ tạo external schema:

~~~sql
CREATE EXTERNAL SCHEMA lake_analytics
FROM DATA CATALOG
DATABASE 'analytics'
IAM_ROLE 'arn:aws:iam::111122223333:role/redshift-lake-role';
~~~

Sau đó query:

~~~sql
SELECT customer_id, SUM(amount)
FROM lake_analytics.orders
GROUP BY customer_id;
~~~

Để có hiệu năng tốt, cần tạo column statistics trong Glue cho Iceberg tables theo hướng dẫn Redshift. Kiểm tra Region availability và Lake Formation permissions cho môi trường cụ thể.

## 17. Lake Formation, IAM và bảo vệ dữ liệu

Iceberg metadata chứa tên cột, partition values, snapshot history, file paths và statistics. Đây có thể là thông tin nhạy cảm về hệ thống dữ liệu.

Cần quản trị:

- IAM roles cho Glue, EMR, Athena, Redshift và application writers.
- Lake Formation grants ở cấp database/table/column/row khi phù hợp.
- S3 bucket policy và access point.
- KMS key policy và encryption.
- CloudTrail audit cho thay đổi catalog, permission và resource.
- Quyền đọc metadata tables như $files, $snapshots, $manifests.
- Quy trình cấp quyền cho optimizer roles.

Lake Formation fine-grained access control có thể áp dụng cho các engine được hỗ trợ. Tuy nhiên, không phải mọi operation Iceberg đều được Lake Formation quản lý quyền theo cùng cách. Ví dụ, Athena không hỗ trợ DDL trên Iceberg tables đã đăng ký với Lake Formation theo giới hạn hiện hành; các thao tác VACUUM, MERGE, UPDATE, OPTIMIZE cũng có hạn chế quản lý quyền riêng.

Không dùng một IAM role có quyền đọc/ghi toàn bộ data lake cho mọi job. Tách role theo table domain và operation.

## 18. Bảo vệ S3 location và data lifecycle

S3 là nơi lưu trữ file, nhưng Iceberg quản lý quan hệ giữa file và snapshot. Vì vậy, các thao tác S3 phải tôn trọng table metadata.

Best practices:

- Mỗi table có location riêng.
- Dùng encryption at rest bằng SSE-S3 hoặc SSE-KMS theo policy.
- Giữ metadata và data files trong storage class mà engine hỗ trợ truy cập.
- Tránh xóa object trực tiếp ngoài Iceberg procedures.
- Không dùng Lifecycle expiration để xóa data/metadata file theo ngày.
- Kiểm soát quyền DeleteObject và DeleteObjectVersion.
- Dùng S3 Versioning khi phù hợp với yêu cầu bảo vệ object, nhưng không coi Versioning là thay thế Iceberg snapshot/backup.
- Archive/backup theo thiết kế có hiểu biết về snapshot, metadata và khả năng restore.

Nếu dùng storage class như Glacier, kiểm tra khả năng query và restore object. Athena có giới hạn với Glacier objects trong Iceberg; không nên chuyển file đang được snapshot active tham chiếu sang storage tier khiến query không đọc được.

## 19. Monitoring và vận hành bảng

Một Iceberg table cần theo dõi cả data quality, metadata health, query behavior và maintenance.

| Chỉ số | Ý nghĩa | Dấu hiệu cần xử lý |
|---|---|---|
| Snapshot count/age | Số snapshot và tuổi snapshot cũ nhất | Metadata/storage tăng hoặc retention quá ngắn |
| Data file count | Số file đang được snapshot tham chiếu | File count tăng nhanh, query planning chậm |
| Average file size | Kích thước file trung bình | Nhiều file nhỏ hoặc file quá lớn |
| Manifest count/size | Metadata overhead | Query planning và metadata scan tăng |
| Delete file count | Số position/equality delete files | Merge-on-read query chậm |
| Orphan file bytes/count | Storage không được metadata tham chiếu | Cleanup backlog hoặc failed jobs |
| Commit conflict/retry | Writer concurrency issue | Job retry nhiều hoặc write latency tăng |
| Query bytes scanned | Data scanned theo query | Partition pruning/file stats chưa tốt |
| Optimizer run status | Kết quả compaction/retention/orphan cleanup | Maintenance fail hoặc role permission thiếu |
| Data quality metrics | Null, duplicate, freshness, schema mismatch | Ingestion lỗi hoặc producer contract thay đổi |

Có thể query metadata tables bằng Athena:

~~~sql
SELECT COUNT(*) AS data_files
FROM "analytics"."orders$files";

SELECT
    committed_at,
    snapshot_id,
    operation
FROM "analytics"."orders$snapshots"
ORDER BY committed_at DESC;
~~~

Với bảng có Lake Formation filters, metadata table query có thể bị giới hạn. Hãy điều tra permission trước khi kết luận metadata không tồn tại.

## 20. Tình huống thực hành: data lake đơn hàng

Một doanh nghiệp thương mại điện tử lưu event đơn hàng từ Kinesis vào S3. Glue streaming job chuyển event sang Iceberg table analytics.orders. Athena phục vụ analyst, Redshift phục vụ BI và Glue Spark chạy enrichment hằng ngày.

### 20.1. Thiết kế bảng

Schema gồm:

- order_id: định danh đơn hàng.
- customer_id: định danh khách hàng.
- order_ts: thời điểm tạo đơn.
- order_date: ngày nghiệp vụ.
- amount: giá trị đơn.
- status: trạng thái hiện tại.
- source_updated_at: thời điểm cập nhật từ source.

Chọn Iceberg v2 vì Athena là một reader chính. Partition theo day(order_ts) và bucket(32, customer_id) sau khi kiểm tra workload query.

### 20.2. Ingestion

Glue Spark ghi micro-batch vào Iceberg. Job dùng idempotency key để chống duplicate và ghi source_updated_at/event version để xử lý late updates.

Các lần append/merge tạo snapshot mới. Analyst query snapshot hiện hành; data engineer có thể dùng time travel để so sánh kết quả trước/sau một batch.

### 20.3. Query và governance

- Athena dùng SQL để query, time travel và DML được hỗ trợ.
- Redshift query cùng bảng qua Glue Data Catalog external schema.
- Lake Formation quản lý quyền theo database/table/column hoặc row-level filter theo use case.
- IAM role tách biệt cho writer, reader và optimizer.

### 20.4. Maintenance

- Compaction định kỳ giảm small files.
- Snapshot retention giữ lịch sử đủ dài cho audit/backfill.
- Orphan cleanup chạy sau khoảng an toàn lớn hơn thời gian commit/retry tối đa.
- Glue optimizer logs và CloudWatch metrics được review.
- S3 Lifecycle không xóa object đang thuộc Iceberg table location.

### 20.5. Khi schema thay đổi

Khi thêm sales_channel, dùng schema evolution thay vì rewrite toàn bộ table. Cập nhật data contract và downstream BI. Query cũ vẫn có thể đọc file trước khi cột mới xuất hiện; cột mới có thể trả null cho các file cũ tùy schema semantics.

## 21. Những sai lầm thường gặp

1. **Nhầm Iceberg với Parquet.** Parquet là file format; Iceberg quản lý table metadata và transaction.
2. **Ghi file trực tiếp vào S3 rồi mong Iceberg tự nhận.** File phải được đưa vào metadata qua Iceberg commit.
3. **Dùng S3 folder listing làm nguồn sự thật.** Iceberg metadata xác định file thuộc snapshot.
4. **Xóa data file bằng S3 console.** Có thể làm snapshot hiện hành bị thiếu file.
5. **Nâng v3 khi Athena vẫn là reader.** Athena hiện chỉ hỗ trợ Iceberg v2.
6. **Giả định Glue và Athena có cùng feature set.** Runtime và Iceberg library version khác nhau.
7. **Không quản lý commit conflict.** Concurrent writers có thể retry hoặc thất bại.
8. **Partition quá chi tiết.** Tạo quá nhiều file nhỏ và metadata.
9. **Không compaction sau streaming ingestion.** Small files làm query planning và scan chậm.
10. **Expire snapshot quá sớm.** Mất khả năng time travel/rollback cần thiết.
11. **Orphan cleanup chạy quá sớm.** Có thể xóa file writer chưa commit.
12. **S3 Lifecycle xóa file theo tuổi.** Có thể xóa data/metadata vẫn được snapshot active tham chiếu.
13. **Cho rằng snapshot retention và orphan cleanup là một việc.** Một thao tác expire snapshot; thao tác khác xóa file không được metadata tham chiếu.
14. **Không tính delete files.** Merge-on-read có thể làm query chậm nếu không compact.
15. **Cho rằng partition evolution tự động rewrite file cũ.** File cũ vẫn dùng spec cũ; Iceberg query planner xử lý nhiều spec.
16. **Không theo dõi engine compatibility.** Reader có thể không hiểu format version hoặc type mới.
17. **Bỏ qua Lake Formation metadata restrictions.** Có thể gặp AccessDenied khi query metadata tables.
18. **Coi S3 Versioning là backup Iceberg.** Versioning không tự khôi phục catalog pointer và table transaction state.

## 22. Câu hỏi tự kiểm tra

**1. Apache Iceberg là file format hay table format?**

Table format. Nó quản lý tập file, schema, partition, snapshot và commit; dữ liệu bên trong vẫn có thể là Parquet, ORC hoặc Avro.

**2. Data Catalog giữ dữ liệu bảng hay metadata pointer?**

Catalog đăng ký bảng và vị trí metadata hiện hành; data files và metadata files thực tế được lưu trên S3.

**3. Manifest list khác manifest file như thế nào?**

Manifest list liệt kê các manifest của snapshot; manifest liệt kê data/delete files cùng partition values và metrics.

**4. Snapshot biểu diễn điều gì?**

Trạng thái bảng tại một thời điểm, xác định tập data files tạo nên dữ liệu bảng lúc đó.

**5. Iceberg commit xử lý concurrent writers ra sao?**

Dùng optimistic concurrency và atomic metadata commit; writer gặp conflict phải refresh metadata, kiểm tra lại và retry theo logic ứng dụng.

**6. Vì sao field IDs quan trọng khi rename column?**

Field ID định danh cột ổn định qua schema evolution, tránh phụ thuộc vào vị trí cột trong file.

**7. Hidden partitioning có lợi ích gì?**

Query dùng cột nghiệp vụ; Iceberg tự áp partition transform và metadata để prune file mà không cần người dùng quản lý thư mục partition.

**8. Partition evolution có rewrite toàn bộ file cũ không?**

Không. File cũ giữ partition spec đã dùng lúc ghi; file mới có thể dùng spec mới.

**9. Time travel phụ thuộc điều gì?**

Snapshot và data files cần thiết còn được giữ; snapshot đã expire không thể truy vấn lại bằng time travel.

**10. Iceberg v2 bổ sung capability quan trọng nào?**

Row-level deletes thông qua delete files, sequence numbers và hỗ trợ update/delete trong các engine tương thích.

**11. Vì sao cần compaction?**

Để giảm small files, merge delete files và cải thiện query planning/read performance.

**12. Snapshot expiration khác orphan file deletion thế nào?**

Snapshot expiration loại snapshot cũ khỏi history và có thể xóa file chỉ còn được snapshot đó tham chiếu; orphan cleanup tìm file không được metadata hiện hành tham chiếu.

**13. Tại sao orphan cleanup cần retention dài hơn commit delay?**

File đã được tạo nhưng commit chưa hoàn tất có thể chưa được metadata tham chiếu; cleanup quá sớm có thể xóa file trước khi writer commit.

**14. Athena có hỗ trợ Iceberg v3 không?**

Theo tài liệu hiện hành trong bài, Athena engine 3 hỗ trợ Iceberg 1.4.2 và vận hành bảng v2; cần kiểm tra lại compatibility trước khi dùng v3.

**15. Lake Formation có quản lý mọi operation Iceberg trong Athena không?**

Không. Quyền đọc và fine-grained access có thể được quản lý, nhưng một số DDL/maintenance operations có giới hạn riêng.

**16. Khi nào nên chọn Glue Spark hoặc EMR cho maintenance?**

Khi cần sort/Z-order, xử lý lượng file lớn, kiểm soát Spark resources hoặc dùng Iceberg procedures linh hoạt hơn Athena OPTIMIZE.

## 23. Checklist production cho Iceberg table

- [ ] Table có owner, business purpose, data contract và S3 location riêng.
- [ ] Đã chọn catalog thống nhất, ưu tiên Glue Data Catalog khi dùng engine AWS tương thích.
- [ ] Đã xác định Iceberg format version theo reader/writer thấp nhất.
- [ ] Đã xác minh runtime/engine support trước khi dùng v3 hoặc type mới.
- [ ] Có IAM/Lake Formation permissions tách theo reader, writer và optimizer.
- [ ] S3/KMS encryption và bucket policy đáp ứng yêu cầu dữ liệu.
- [ ] Không có S3 Lifecycle expiration xóa data/metadata trong table location.
- [ ] Schema evolution được quản lý bằng field IDs và data contract.
- [ ] Partition transforms dựa trên query patterns và phân bố dữ liệu.
- [ ] Writer có idempotency, retry/backoff và xử lý commit conflict.
- [ ] Có chiến lược compaction theo file count/size và query performance.
- [ ] Có snapshot retention đáp ứng audit, rollback và backfill.
- [ ] Orphan cleanup retention dài hơn thời gian commit/retry tối đa.
- [ ] Table location không chồng lấn với table hoặc data source khác.
- [ ] Có monitoring snapshot count, file count, delete files, commit retries và query scan.
- [ ] Có kiểm thử time travel, rollback, schema change và partition evolution.
- [ ] Có kiểm thử concurrent writers và compaction conflict.
- [ ] Có runbook xử lý AccessDenied, commit failure và missing file.
- [ ] Có quy trình restore/backup và kiểm tra khả năng phục hồi.
- [ ] Có review định kỳ cho cost, storage, query performance và data quality.

## Tài liệu tham khảo

- [Apache Iceberg specification](https://iceberg.apache.org/spec/)
- [Apache Iceberg terminology](https://iceberg.apache.org/terms/)
- [Apache Iceberg documentation](https://iceberg.apache.org/docs/latest/)
- [Using the Iceberg framework in AWS Glue](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-format-iceberg.html)
- [AWS Glue table optimizers](https://docs.aws.amazon.com/glue/latest/dg/table-optimizers.html)
- [AWS Glue table optimization prerequisites](https://docs.aws.amazon.com/glue/latest/dg/optimization-prerequisites.html)
- [AWS Glue compaction optimization](https://docs.aws.amazon.com/glue/latest/dg/compaction.html)
- [AWS Glue snapshot retention optimization](https://docs.aws.amazon.com/glue/latest/dg/snapshot-retention-management.html)
- [AWS Glue orphan file deletion](https://docs.aws.amazon.com/glue/latest/dg/orphan-file-deletion.html)
- [AWS Glue optimizer considerations and limitations](https://docs.aws.amazon.com/glue/latest/dg/optimizer-notes.html)
- [Catalog-level table optimizers](https://docs.aws.amazon.com/glue/latest/dg/catalog-level-optimizers.html)
- [Query Apache Iceberg tables in Athena](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg.html)
- [Create Iceberg tables in Athena](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-creating-tables.html)
- [Athena Iceberg time travel and version travel](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-time-travel-and-version-travel-queries.html)
- [Update Iceberg table data in Athena](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-updating-iceberg-table-data.html)
- [Athena OPTIMIZE](https://docs.aws.amazon.com/athena/latest/ug/optimize-statement.html)
- [Athena VACUUM](https://docs.aws.amazon.com/athena/latest/ug/vacuum-statement.html)
- [Athena Iceberg schema evolution](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-evolving-table-schema.html)
- [Query Iceberg metadata tables in Athena](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-table-data.html)
- [Using Iceberg with Amazon EMR](https://docs.aws.amazon.com/prescriptive-guidance/latest/apache-iceberg-on-aws/iceberg-emr.html)
- [Self-managed Iceberg maintenance on AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/apache-iceberg-on-aws/self-managed-maintenance.html)
- [Query Apache Iceberg tables with Amazon Redshift](https://docs.aws.amazon.com/redshift/latest/dg/querying-iceberg.html)
- [Referencing Iceberg tables in Amazon Redshift](https://docs.aws.amazon.com/redshift/latest/dg/referencing-iceberg-tables.html)
- [AWS Lake Formation table optimization](https://docs.aws.amazon.com/lake-formation/latest/dg/data-compaction.html)

