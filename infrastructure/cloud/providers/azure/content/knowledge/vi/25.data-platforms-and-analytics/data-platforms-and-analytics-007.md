# Azure Databricks và xử lý dữ liệu bằng Apache Spark

Một doanh nghiệp nhận dữ liệu từ ứng dụng giao dịch, tệp CSV/JSON, hệ thống ERP, sự kiện clickstream và cảm biến. Mỗi ngày có thể có hàng triệu bản ghi cần chuẩn hóa, kiểm tra chất lượng, kết hợp và cung cấp cho báo cáo. Khi khối lượng vượt khả năng xử lý thuận tiện của một tiến trình đơn hoặc khi dữ liệu đến liên tục, nhóm kỹ thuật cần một cách **phân tán tính toán, kiểm soát chất lượng và vận hành pipeline có thể khôi phục**.

**Apache Spark** là công cụ xử lý dữ liệu phân tán hỗ trợ DataFrame, SQL, batch processing, machine learning và Structured Streaming. **Azure Databricks** cung cấp môi trường quản lý dựa trên Spark với notebooks, compute, Delta Lake, Jobs/Workflows, SQL analytics và Unity Catalog để xây dựng nền tảng dữ liệu trên Azure.

Bài học thuộc chương **Nền tảng dữ liệu và phân tích** của mô-đun **CLOUD_PROVIDERS_AZURE**. Nó kết nối Azure Databricks với subscription và resource group, Microsoft Entra ID, mạng ảo, Azure Data Lake Storage Gen2 (ADLS Gen2), Key Vault, Azure Monitor và việc triển khai, bảo mật, giám sát, kiểm soát chi phí kiến trúc ứng dụng Azure.

**Phạm vi:** nền tảng Spark và các mẫu thiết kế Databricks thực hành được. Những tính năng như serverless, loại compute, catalog, deployment model, vùng triển khai và SKU thay đổi theo thời điểm/tier. Không mặc định mọi tính năng đều có ở mọi workspace; kiểm tra tài liệu và chính sách tổ chức trước khi chạy.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích driver, executor, task, partition, DAG, stage, lazy evaluation và shuffle trong Apache Spark.
2. Phân biệt Spark DataFrame API, Spark SQL, RDD và pandas; chọn công cụ theo quy mô/bài toán.
3. Hiểu các thành phần của Azure Databricks workspace, notebooks, compute, Databricks Runtime, Jobs/Workflows, SQL warehouses, Delta Lake và Unity Catalog.
4. Mô tả kiến trúc lakehouse sử dụng ADLS Gen2, Bronze/Silver/Gold và bảng Delta.
5. Viết PySpark để đọc, chuẩn hóa, lọc lỗi, loại bản ghi trùng và tổng hợp đơn hàng.
6. Đọc/ghi dữ liệu Delta trong schema được phép; hiểu transaction log, ACID, schema enforcement và MERGE.
7. So sánh batch ingestion, Auto Loader và Structured Streaming với checkpointing, state và event-time semantics.
8. Thiết kế quyền truy cập dữ liệu với Unity Catalog, Microsoft Entra ID, managed identity và private networking.
9. Chọn job compute, interactive compute hay SQL warehouse theo workload và ngân sách.
10. Hiểu cách tối ưu partitions, join, skew, small files, adaptive query execution và query plans.
11. Triển khai pipeline có orchestration, CI/CD, data quality checks, lineage và khả năng retry an toàn.
12. Theo dõi Spark UI, job runs, logs, chi phí Databricks Units (DBUs) và hạ tầng Azure.
13. Nhận biết tình huống nên và không nên chọn Databricks thay cho dịch vụ dữ liệu khác.

Ví dụ ở đây dùng **Python/PySpark**, SQL và cấu trúc notebook. Không tự tạo tài nguyên hoặc thực thi trên subscription sản xuất.

## 2. Bài toán: từ tệp thô tới báo cáo tin cậy

Giả sử hệ thống thương mại điện tử tạo:

- Orders và OrderItems từ backend App Service.
- Clickstream JSON của website.
- Customer data từ một database quan hệ.
- Tệp sản phẩm CSV từ đối tác.
- Sự kiện thanh toán từ Event Hubs hoặc message service.

Mục tiêu kinh doanh: mỗi sáng có báo cáo doanh thu theo tenant và ngày, đồng thời phát hiện dữ liệu hỏng, bản ghi trùng và các đơn bị hoàn tiền.

~~~mermaid
flowchart LR
    A["App / ERP / Event sources"] --> L["ADLS Gen2 landing"]
    L --> B["Bronze: ingest raw"]
    B --> S["Silver: clean, validate, deduplicate"]
    S --> G["Gold: business aggregates"]
    G --> Q["Databricks SQL / BI / Analytics"]
    S --> M["ML features / downstream apps"]
    B --> E["Quarantine / data quality alerts"]
    S --> E
~~~

Cần giải quyết đồng thời:

1. **Scale:** dữ liệu nhiều hơn RAM/một CPU.
2. **Data quality:** trường sai kiểu, null, duplicate, late arrival.
3. **Repeatability:** chạy lại một lô không tạo dữ liệu trùng.
4. **Governance:** tenant nào được đọc bảng nào?
5. **Recovery:** job lỗi giữa chừng thì chạy lại từ đâu?
6. **Cost:** không giữ compute đắt tiền khi pipeline không hoạt động.
7. **Lineage:** dữ liệu trong báo cáo xuất phát từ nguồn nào?

Spark giúp phân tán tính toán; Databricks cung cấp môi trường vận hành và quản trị. Chúng **không tự quyết định business rules**, không thay thế chất lượng thiết kế schema và không bảo đảm mọi pipeline là exactly-once nếu logic ghi dữ liệu không idempotent.

## 3. Apache Spark hoạt động như thế nào?

### 3.1. Driver và executors

~~~mermaid
flowchart TD
    D["Driver: SparkSession, planner, scheduler"] --> E1["Executor 1"]
    D --> E2["Executor 2"]
    D --> E3["Executor 3"]
    E1 --> T1["Tasks / data partitions"]
    E2 --> T2["Tasks / data partitions"]
    E3 --> T3["Tasks / data partitions"]
    E1 --> S["Read / Write distributed storage"]
    E2 --> S
    E3 --> S
~~~

- **Driver:** chạy chương trình điều phối Spark, tạo query plan, chia công việc và tổng hợp trạng thái.
- **Executors:** các tiến trình thực hiện tasks, dùng CPU/RAM, có thể cache partitions.
- **Task:** đơn vị tính toán chạy trên một partition trong một stage.
- **Partition:** phần dữ liệu logic được Spark xử lý song song; không đồng nghĩa một thư mục lưu trữ hay partition key Cosmos DB.
- **Job:** thường được kích hoạt bởi action như count, collect hoặc write.
- **Stage:** nhóm tasks có thể chạy song song trước/sau các ranh giới shuffle.

Driver **không phải nơi chứa toàn bộ dữ liệu lớn**. Nếu gọi collect/toPandas trên hàng chục triệu dòng, dữ liệu có thể tràn RAM driver dù Spark cluster có nhiều executors.

### 3.2. DAG và lazy evaluation

Spark DataFrame operations như select, filter, withColumn và join thường là **transformations**: Spark xây dựng kế hoạch tính toán nhưng chưa thực thi ngay.

Các thao tác như count, show, collect và write là **actions**, kích hoạt thực thi job.

~~~python
from pyspark.sql import functions as F

filtered = df.filter(F.col("status") == "paid")  # transformation
grouped = filtered.groupBy("tenant_id").count()   # transformation

grouped.explain()  # xem kế hoạch xử lý
grouped.show()     # action: khởi chạy Spark computation
~~~

Điều này có nghĩa một notebook có thể “chạy qua” nhiều dòng transformations rất nhanh rồi chỉ bắt đầu tiêu thụ nhiều compute khi gặp action.

### 3.3. Narrow và wide transformations

| Loại | Ví dụ | Tác động |
|---|---|---|
| Narrow | filter, select, withColumn đơn giản | Thường có thể xử lý trong partition hiện có |
| Wide | groupBy, orderBy, distinct, nhiều joins | Có thể cần shuffle dữ liệu qua executors |
| Action | count, show, write | Kích hoạt thực thi DAG |
| Cache/persist | cache hoặc persist | Dữ liệu được lưu lại khi action materialize, tốn RAM/disk |

**Shuffle** là việc phân phối lại dữ liệu giữa partitions theo keys/order, cần network và disk I/O. Một groupBy trên hàng tỷ records hoặc join không có key tốt có thể rất tốn thời gian.

### 3.4. Shuffle và data skew

Ví dụ bảng events có 80% bản ghi thuộc một tenant lớn. GroupBy tenant_id khiến một số partition xử lý nhiều dữ liệu hơn các partition khác.

~~~text
Partition 1: tenant-a 80 triệu events
Partition 2: tenant-b 2 triệu events
Partition 3: tenant-c 1 triệu events
...
~~~

Kết quả là một executor chạy rất lâu trong khi các executor khác rảnh. Đây là **data skew**, không được giải quyết chỉ bằng tăng số worker nếu key distribution vẫn lệch.

Các hướng xử lý gồm:

- Phân tích skew trước, không chọn partition key theo cảm tính.
- Dùng adaptive query execution khi được hỗ trợ.
- Phân tách hot keys hoặc salting ở tình huống phù hợp.
- Broadcast bảng nhỏ nếu đủ điều kiện.
- Chia dữ liệu theo đúng access/query pattern.
- Đo shuffle read/write, spill và task duration trong Spark UI.

### 3.5. Spark DataFrame, SQL, RDD và pandas

| Công cụ | Khi phù hợp | Lưu ý |
|---|---|---|
| DataFrame API (PySpark) | ETL, joins, cleaning, aggregations | Catalyst optimizer có thể tối ưu query plan |
| Spark SQL | Truy vấn, tạo view/table, BI transformation | Vẫn chạy phân tán qua Spark |
| RDD | Một số thuật toán mức thấp đặc thù | Ít tối ưu hóa cấu trúc hơn DataFrame |
| pandas | Dữ liệu vừa RAM của một máy, phân tích nhanh | Không tự phân tán trên Spark executors |
| pandas API on Spark | Giao diện pandas-like phân tán | Semantics/performance khác pandas cục bộ |
| Databricks SQL | SQL analytics/warehouse và BI workflows | Cần compute/SQL warehouse và quyền dữ liệu |

Với pipeline có SQL/ETL chuẩn, ưu tiên **DataFrame API hoặc Spark SQL**. Không viết Python for-loop đọc từng dòng JSON rồi gọi API/DB tuần tự từ driver khi Spark đã có các primitives xử lý theo cột.

## 4. Azure Databricks có thêm những gì?

### 4.1. Các thành phần chính

~~~mermaid
flowchart TD
    W["Azure Databricks Workspace"] --> N["Notebooks / Repos / Development"]
    W --> C["Compute: interactive / jobs / serverless nếu hỗ trợ"]
    W --> J["Lakeflow Jobs / Workflows orchestration"]
    W --> Q["Databricks SQL Warehouses"]
    W --> U["Unity Catalog governance"]
    C --> S["Apache Spark engine"]
    S --> D["Delta Lake tables trên cloud storage"]
    Q --> D
    U --> D
    J --> C
    J --> Q
~~~

- **Workspace:** giao diện và phạm vi làm việc cho notebooks, compute settings, jobs và assets.
- **Databricks Runtime:** môi trường runtime kết hợp Spark với các thư viện/tối ưu hóa/tính năng của Databricks theo phiên bản.
- **Notebooks:** viết code Python, SQL và nhiều ngôn ngữ được hỗ trợ để khám phá và xử lý dữ liệu.
- **Compute:** tài nguyên thực thi workloads, có thể là classic compute hoặc serverless theo tính năng workspace.
- **Jobs/Workflows:** đặt lịch và điều phối notebook, Python, SQL hoặc các tasks theo capability được hỗ trợ.
- **Databricks SQL:** SQL warehouses, queries, dashboards và kết nối công cụ BI.
- **Unity Catalog:** quản trị catalogs/schemas/tables/volumes, phân quyền, lineage và quản lý truy cập tài nguyên dữ liệu.
- **Delta Lake:** định dạng bảng hỗ trợ transaction log, ACID và nhiều thao tác DML đáng tin cậy trên object storage.

Tên tính năng/khả năng có thể thay đổi theo release và workspace SKU. “Có Databricks workspace” không tự có sẵn tất cả compute types hoặc quyền tạo catalogs.

### 4.2. Control plane và compute/data plane

Ở mức khái niệm, Azure Databricks gồm:

- **Control plane** quản lý workspace services, job scheduling, UI và metadata dịch vụ.
- **Compute/data plane** thực thi workloads và truy cập dữ liệu với network/identity theo kiểu compute/workspace đã chọn.
- **Cloud storage** như ADLS Gen2 để lưu landing, Delta tables, files và checkpoints.

Với classic compute, các VM/tài nguyên thường sử dụng Azure environment theo cách triển khai của workspace. Với serverless, cơ sở hạ tầng compute được Databricks quản lý theo mô hình khác. **Không giả định cùng một cấu hình VNet/Private Link/egress áp dụng hệt nhau cho mọi compute type.**

### 4.3. Khi nào nên dùng Databricks?

Phù hợp khi:

- Xử lý nhiều GB/TB+ dữ liệu batch hoặc near-real-time.
- Dùng Spark SQL/PySpark và cần tính toán phân tán.
- Xây lakehouse trên Delta Lake với nhiều pipeline.
- Có ingestion từ files/events, transformations nhiều tầng.
- Cần thống nhất data engineering và BI/ML workloads theo governance.
- Cần job orchestration, identity và lineage ở quy mô tổ chức.

Có thể là lựa chọn không tối ưu khi:

- Chỉ xử lý 200 dòng CSV mỗi ngày.
- Tất cả nghiệp vụ là truy vấn OLTP vài milliseconds; cần Azure SQL Database/PostgreSQL hơn Spark.
- Cần vận hành Kafka low-latency messaging hoặc transaction APIs thay vì analytics.
- Một SQL query nhỏ đã chạy tốt trong warehouse/serverless SQL khác.
- Không có đội vận hành pipeline, data quality và chi phí compute.

**Spark không phải database giao dịch trực tuyến thay cho Azure SQL/Cosmos DB.** Nó là engine xử lý/analytics phân tán và có thể dùng Delta tables trong kiến trúc lakehouse.

## 5. Chọn loại compute và runtime

### 5.1. Các loại compute theo mục đích

| Loại | Mục đích thường gặp | Lưu ý |
|---|---|---|
| Interactive/all-purpose compute | Khám phá dữ liệu, development, notebooks tương tác | Có thể bị quên tắt; cần auto-termination |
| Jobs compute | Chạy pipeline theo lịch/trigger | Thường phù hợp workloads tự động với thời gian sống theo job |
| SQL warehouse | SQL queries, dashboards, BI | Tách khỏi cluster PySpark tùy thiết kế |
| Serverless compute | Workloads được hỗ trợ, quản lý compute ít hơn | Availability, network, governance và giá cần xác minh |
| Single-node compute khi hỗ trợ | Lab/khối lượng nhỏ | Không chứng minh khả năng scale phân tán |

Các thuật ngữ UI và khả năng hỗ trợ thay đổi theo release. Đừng chọn interactive compute chạy 24/7 cho một job mỗi ngày 10 phút nếu jobs compute đáp ứng yêu cầu.

### 5.2. Databricks Runtime và thư viện

Trước khi bắt đầu notebook:

1. Xác định phiên bản Databricks Runtime, Spark, Python và Delta được hỗ trợ.
2. Chọn runtime được tổ chức phê duyệt, cân nhắc LTS khi muốn ổn định.
3. Kiểm tra các thư viện bổ sung, phiên bản connector/JDBC.
4. Không cài tràn lan packages trên production cluster từ nguồn không kiểm soát.
5. Chạy regression tests trước khi upgrade runtime.
6. Ghi runtime version trong job/release metadata.

Một notebook chạy trên Runtime A có thể không hoạt động trên Runtime B do thay đổi Python/PySpark APIs, permissions hoặc dependencies.

### 5.3. Autoscaling và auto-termination

- **Autoscaling** điều chỉnh số workers theo điều kiện được dịch vụ hỗ trợ.
- **Auto-termination** ngắt compute tương tác sau khoảng idle được cấu hình.
- **Jobs compute** có vòng đời theo job run, nhưng phải hiểu startup/scale overhead.
- **Serverless** thay đổi mô hình quản lý hạ tầng và tính phí.

Autoscaling **không xóa bottleneck shuffle/data skew**, cũng không cứu một job thường xuyên collect dữ liệu lớn vào driver.

### 5.4. Cluster policies và tags

Quản trị production nên có guardrails:

- Giới hạn node types và max workers.
- Chặn/runtime versions không còn được hỗ trợ.
- Ép auto-termination cho compute tương tác.
- Gắn resource tags như env, team, costCenter, workload.
- Giới hạn những lựa chọn instance/storage/cluster chưa được phê duyệt.
- Tách dev/test/prod và quyền tạo compute.

Một cluster policy hỗ trợ governance nhưng không tự bảo đảm query tối ưu hay data access đúng.

## 6. ADLS Gen2 và kiến trúc lakehouse

### 6.1. Storage tách khỏi compute

~~~mermaid
flowchart LR
    SRC["Sources"] --> LAND["ADLS Gen2 landing / raw"]
    LAND --> BR["Bronze Delta tables"]
    BR --> SI["Silver Delta tables"]
    SI --> GO["Gold Delta tables"]
    GO --> BI["Databricks SQL / BI"]
    GO --> ML["Analytics / ML"]
    UC["Unity Catalog"] -. "Access, metadata, lineage" .-> BR
    UC -. "Access, metadata, lineage" .-> SI
    UC -. "Access, metadata, lineage" .-> GO
~~~

ADLS Gen2 cung cấp object storage với hierarchical namespace và các khả năng quản trị Azure Storage. Spark compute có thể được tạo và tắt riêng, trong khi dữ liệu Delta được lưu lâu dài trên storage.

### 6.2. Bronze/Silver/Gold (Medallion)

| Lớp | Nội dung | Yêu cầu |
|---|---|---|
| Bronze | Dữ liệu gần nguồn, có metadata ingestion | Không mất thông tin nguồn, có schema/quarantine khi cần |
| Silver | Clean, typed, deduplicated, chuẩn hóa khóa và rules | Dùng lại giữa nhiều consumers, kiểm thử chất lượng |
| Gold | Aggregates/data marts theo nghiệp vụ | Metric definitions, quyền truy cập và SLA rõ |

**Bronze không có nghĩa “cứ sai cũng mặc kệ”**: cần giữ thông tin đủ để xử lý lại và biết nguồn dữ liệu. **Gold không phải tự động đúng**: team phải định nghĩa metric, thời gian, data contracts và xử lý late events.

### 6.3. Unity Catalog managed và external storage

Unity Catalog có thể quản lý **managed tables/volumes** trong managed storage hoặc truy cập **external locations** đã được cấu hình phù hợp. Không nên dựa vào những mount/credential hard-coded không thuộc governance để tạo toàn bộ pipeline mới.

Các khái niệm:

- **Catalog:** không gian tên dữ liệu cấp cao.
- **Schema:** nhóm tables/views/volumes.
- **Table:** dữ liệu có schema và quyền SELECT/MODIFY.
- **Volume:** đường quản lý tệp phi bảng trong Unity Catalog.
- **Storage credential:** cơ chế truy cập storage được quản lý.
- **External location:** đường dẫn cloud storage gắn với credential và phân quyền.
- **Lineage:** quan hệ nguồn/đích được ghi nhận ở các hoạt động được hỗ trợ.

Cấu hình storage credential, external location và access connector thường cần quyền Azure và Unity Catalog thích hợp; không mặc định notebook user có thể tự tạo.

### 6.4. Cấu trúc đường dẫn cần cẩn trọng

Ví dụ đường dẫn của một Unity Catalog volume:

~~~text
/Volumes/<catalog>/<schema>/<volume>/landing/orders/
~~~

Đây là placeholder, không phải resource thật. Trong jobs production nên ghi đường dẫn/tên table từ cấu hình môi trường có kiểm soát. Không đưa access key, SAS token hoặc client secret vào string đường dẫn.

## 7. Spark DataFrame: những API cốt lõi

### 7.1. Tạo SparkSession và đọc dữ liệu

Trong notebook Databricks gắn với Spark compute, đối tượng **spark** thường đã có.

~~~python
from pyspark.sql import functions as F

# Trong Databricks notebook đã có SparkSession spark.
rows = [
    ("o-001", "tenant-a", 2, 125.50),
    ("o-002", "tenant-a", 1, 90.00),
    ("o-003", "tenant-b", 3, 49.90),
]

df = spark.createDataFrame(
    rows,
    ["order_id", "tenant_id", "quantity", "unit_price"]
)

df.printSchema()
df.show(truncate=False)
~~~

**spark.createDataFrame** là cách tạo dữ liệu lab nhỏ. Khi đọc dữ liệu production, ưu tiên nguồn phân tán như ADLS Gen2/Delta tables thay vì chuyển một danh sách hàng triệu Python objects qua driver.

### 7.2. Select, filter, withColumn

~~~python
clean = (
    df.filter(F.col("quantity") > 0)
      .withColumn("line_total", F.col("quantity") * F.col("unit_price"))
      .select("order_id", "tenant_id", "line_total")
)

clean.show()
~~~

Trong dữ liệu tài chính, nên dùng **DecimalType** thay vì float khi cần tính toán tiền chính xác. Số 125.50 trong demo chỉ minh họa API, không phải thiết kế data type production.

### 7.3. GroupBy và aggregate

~~~python
summary = (
    clean.groupBy("tenant_id")
         .agg(
             F.count("*").alias("order_count"),
             F.sum("line_total").alias("gross_total")
         )
)

summary.show()
~~~

Spark thực thi một phép groupBy có thể cần shuffle theo tenant_id. Cần quan sát số partition và skew nếu có một tenant chiếm phần lớn dữ liệu.

### 7.4. Join

~~~python
tenants = spark.createDataFrame(
    [("tenant-a", "North"), ("tenant-b", "South")],
    ["tenant_id", "region"]
)

result = summary.join(tenants, on="tenant_id", how="left")
result.show()
~~~

Khi bảng tenant mapping thực sự nhỏ, Spark optimizer có thể chọn broadcast join. Không broadcast một bảng lớn chỉ vì nó có ít dòng nhưng mỗi dòng chứa payload khổng lồ.

### 7.5. DataFrames bất biến theo kiểu transformation

Các operations DataFrame thường trả **DataFrame mới**; câu lệnh:

~~~python
df.filter(F.col("quantity") > 0)
~~~

không tự thay thế biến df. Để giữ kết quả cần gán:

~~~python
df = df.filter(F.col("quantity") > 0)
~~~

Một pipeline rõ ràng nên dùng các biến **raw, validated, silver, gold** thay vì ghi đè df liên tục khiến khó review lineage.


## 8. Thực hành PySpark tự chứa: làm sạch đơn hàng

### 8.1. Dữ liệu và quy tắc

Ta dùng dữ liệu tạo ngay trong notebook, không cần quyền truy cập storage. Mục tiêu là xử lý sáu dòng, trong đó hai dòng lỗi và một đơn hàng có hai phiên bản. Quy tắc nghiệp vụ:

- quantity phải là số nguyên dương.
- unit_price phải là DECIMAL không âm.
- event_time là thời gian UTC hợp lệ.
- status thuộc paid, pending, canceled.
- Trong cùng tenant, mỗi order_id lấy source_version mới nhất.
- Gold tính tổng gross value cho đơn paid theo tenant/ngày.

### 8.2. Tạo dữ liệu Bronze

~~~python
from pyspark.sql import functions as F
from pyspark.sql import Window

spark.conf.set("spark.sql.session.timeZone", "UTC")

rows = [
    ("o-001", "tenant-a", "c-01", "2026-11-18T08:00:00Z",
     "2", "125.50", "paid", 1),
    ("o-002", "tenant-a", "c-02", "2026-11-18T08:05:00Z",
     "1", "90.00", "pending", 1),
    ("o-001", "tenant-a", "c-01", "2026-11-18T08:10:00Z",
     "2", "125.50", "paid", 2),
    ("o-003", "tenant-b", "c-03", "2026-11-19T11:30:00Z",
     "3", "49.90", "paid", 1),
    ("o-004", "tenant-b", "c-04", "2026-11-19T12:00:00Z",
     "-1", "24.50", "paid", 1),
    ("o-005", "tenant-b", "c-05", "2026-11-19T12:30:00Z",
     "1", "invalid", "paid", 1),
]

schema = """
order_id STRING,
tenant_id STRING,
customer_id STRING,
event_time_text STRING,
quantity_text STRING,
unit_price_text STRING,
status STRING,
source_version INT
"""

bronze = (
    spark.createDataFrame(rows, schema=schema)
         .withColumn("_ingested_at", F.current_timestamp())
)
bronze.show(truncate=False)
~~~

Bronze production nên có source file, source event ID, ingestion batch và schema version. DataFrame này chỉ là tập dữ liệu minh họa, không phải một bảng Delta đã được lưu.

### 8.3. Chuẩn hóa kiểu dữ liệu

~~~python
typed = (
    bronze
    .withColumn(
        "event_time",
        F.to_timestamp("event_time_text", "yyyy-MM-dd'T'HH:mm:ssX")
    )
    .withColumn(
        "quantity", F.expr("try_cast(quantity_text as int)")
    )
    .withColumn(
        "unit_price",
        F.expr("try_cast(unit_price_text as decimal(18,2))")
    )
)
typed.select(
    "order_id", "event_time", "quantity",
    "unit_price", "status"
).show(truncate=False)
~~~

Hàm **try_cast** trong Databricks SQL trả null nếu không cast được, nhờ đó có thể đưa dữ liệu hỏng vào quarantine. Các phiên bản Runtime/Spark có thể khác về hàm và định dạng timestamp; ví dụ cố tình dùng những chuỗi thời gian ISO hợp lệ. Với nguồn thời gian sai, cần thêm nhánh parsing có kiểm soát.

**Dữ liệu tiền cần DECIMAL với precision/scale, currency và chính sách rounding rõ ràng**, không sử dụng float tùy tiện trong báo cáo tài chính.

### 8.4. Phân loại valid/quarantine

~~~python
condition = (
    F.col("order_id").isNotNull()
    & F.col("tenant_id").isNotNull()
    & F.col("customer_id").isNotNull()
    & F.col("event_time").isNotNull()
    & (F.col("quantity") > 0)
    & (F.col("unit_price") >= 0)
    & F.col("status").isin("paid", "pending", "canceled")
)
is_valid = F.coalesce(condition, F.lit(False))

valid = typed.filter(is_valid)
quarantine = typed.filter(~is_valid)

print("Valid rows:", valid.count())
print("Rejected rows:", quarantine.count())
~~~

Kỳ vọng **4 valid**, **2 rejected**: o-004 quantity âm, o-005 unit_price không parse được. Coalesce giúp mọi điều kiện null trở thành False thay vì để toán tử NOT trên SQL null làm sót dòng lỗi.

Ở production, quarantine cần lưu source metadata, mã lỗi, thời gian, owner và lịch retry; không được bỏ dữ liệu hỏng rồi báo pipeline thành công mà không có alert.

### 8.5. Loại dữ liệu trùng theo source_version

~~~python
w = (
    Window.partitionBy("tenant_id", "order_id")
          .orderBy(
              F.col("source_version").desc(),
              F.col("event_time").desc()
          )
)

silver = (
    valid
    .withColumn("_row_num", F.row_number().over(w))
    .filter(F.col("_row_num") == 1)
    .select(
        "tenant_id", "order_id", "customer_id",
        "event_time", "quantity", "unit_price",
        "status", "source_version"
    )
)

silver.orderBy("tenant_id", "order_id").show(truncate=False)
~~~

Kỳ vọng **3 Silver rows**: bản mới o-001, o-002 và o-003.

Đây là quy tắc lab. Trong sản xuất, nếu source_version và event_time cùng trùng, cần tie-breaker ổn định như source event ID/sequence. Một phép dropDuplicates chọn dòng bất kỳ sẽ không đủ cho cập nhật có ý nghĩa nghiệp vụ.

### 8.6. Tổng hợp Gold cho đơn paid

~~~python
paid = silver.filter(F.col("status") == "paid")

gold = (
    paid
    .withColumn("order_date", F.to_date("event_time"))
    .groupBy("tenant_id", "order_date")
    .agg(
        F.countDistinct("order_id").alias("paid_orders"),
        F.sum(
            F.col("quantity") * F.col("unit_price")
        ).alias("gross_value")
    )
)

gold.orderBy("tenant_id", "order_date").show(truncate=False)
~~~

Kết quả mong đợi:

| tenant_id | order_date (UTC) | paid_orders | gross_value |
|---|---|---:|---:|
| tenant-a | 2026-11-18 | 1 | 251.00 |
| tenant-b | 2026-11-19 | 1 | 149.70 |

Đây chỉ là **gross quantity × unit_price** của những đơn paid, chưa trừ tax, refund và discount. Nếu báo cáo theo ngày tại Việt Nam, cần chuyển timezone theo yêu cầu business trước khi groupBy ngày; ví dụ đang dùng UTC.

### 8.7. Kiểm thử số dòng

~~~python
assert bronze.count() == 6
assert quarantine.count() == 2
assert silver.count() == 3
assert gold.count() == 2

assert (
    silver.filter(
        (F.col("tenant_id") == "tenant-a")
        & (F.col("order_id") == "o-001")
        & (F.col("source_version") == 2)
    ).count()
) == 1
~~~

Các lệnh count là **actions** có thể kích hoạt lại Spark jobs. Trong production tránh chạy count toàn bảng lặp lại chỉ để debug; cân nhắc metrics tích hợp pipeline, expectations hoặc sampling.

### 8.8. Giới hạn của lab

Dữ liệu nhỏ; chưa kiểm tra concurrency, skew, storage permission, checkpoint, late events hoặc MERGE. Production cần idempotent ingestion, schema validation, metadata nguồn, kiểm thử quyền và orchestration.

## 9. Delta Lake: transaction trên object storage

### 9.1. Vì sao không chỉ dùng thư mục Parquet?

Parquet là định dạng columnar hữu ích, nhưng một thư mục tệp Parquet thuần túy không tự mang lại giao dịch UPDATE/DELETE nhiều tệp và phiên bản bảng nhất quán.

**Delta Lake** sử dụng tệp dữ liệu (thường Parquet) cùng transaction log để hỗ trợ:

- ACID transactions cho các operations được hỗ trợ.
- Schema enforcement khi ghi.
- Schema evolution có kiểm soát.
- UPDATE/DELETE/MERGE.
- Time travel đọc những snapshots còn được giữ.
- Batch và Structured Streaming trên bảng Delta.
- File optimization/layout theo tính năng Databricks Runtime.

~~~mermaid
flowchart TD
    T["Delta table"] --> D["Data files"]
    T --> L["_delta_log"]
    L --> V1["Version 1"]
    L --> V2["Version 2"]
    L --> V3["Version 3"]
    V3 --> Q["Consistent snapshot for readers"]
~~~

ACID của Delta table không làm application logic tự có một unique constraint trên (tenant_id, order_id). Nếu source có duplicate không được kiểm tra, vẫn có thể ghi sai business data.

### 9.2. Ghi bảng trong lab có quyền

Giả sử Unity Catalog có **catalog và schema lab**, người chạy có quyền tạo bảng và tên đích chưa tồn tại:

~~~python
target_table = "training_catalog.sandbox.orders_silver_lab"

(
    silver.write
          .format("delta")
          .mode("errorifexists")
          .saveAsTable(target_table)
)
~~~

**errorifexists** chủ đích từ chối ghi nếu bảng đã tồn tại. Không dùng overwrite trên bảng production hay chạy lệnh trên tài nguyên không sở hữu. Tên training_catalog.sandbox chỉ minh họa; phải thay bằng catalog/schema đã được tạo và cấp quyền.

### 9.3. Đọc lại với PySpark và SQL

~~~python
saved = spark.table("training_catalog.sandbox.orders_silver_lab")
saved.printSchema()
saved.show(truncate=False)
~~~

~~~sql
SELECT tenant_id, COUNT(*) AS orders_count
FROM training_catalog.sandbox.orders_silver_lab
GROUP BY tenant_id
ORDER BY tenant_id;
~~~

### 9.4. MERGE cho incremental upsert

Giả sử bảng staging đã được **deduplicate theo (tenant_id, order_id)**:

~~~sql
MERGE INTO training_catalog.sandbox.orders_silver_lab AS t
USING training_catalog.sandbox.orders_stage_lab AS s
ON t.tenant_id = s.tenant_id
   AND t.order_id = s.order_id
WHEN MATCHED AND s.source_version > t.source_version
THEN UPDATE SET
    t.customer_id = s.customer_id,
    t.event_time = s.event_time,
    t.quantity = s.quantity,
    t.unit_price = s.unit_price,
    t.status = s.status,
    t.source_version = s.source_version
WHEN NOT MATCHED THEN INSERT (
    tenant_id, order_id, customer_id, event_time,
    quantity, unit_price, status, source_version
)
VALUES (
    s.tenant_id, s.order_id, s.customer_id, s.event_time,
    s.quantity, s.unit_price, s.status, s.source_version
);
~~~

Đây là ví dụ với bảng stage giả định đã tồn tại. Nếu có delete events, late data, source duplicates hoặc transaction conflicts, cần logic riêng. Trong production, việc ghi lại một batch phải idempotent; một source có nhiều dòng trùng key có thể khiến MERGE fail hoặc sai semantics.

### 9.5. Time travel, retention và VACUUM

~~~sql
DESCRIBE HISTORY training_catalog.sandbox.orders_silver_lab;

-- Chỉ chạy khi table thực sự còn phiên bản 2:
SELECT *
FROM training_catalog.sandbox.orders_silver_lab VERSION AS OF 2;
~~~

Để time travel, log và các data files liên quan phải còn trong retention. **VACUUM** có thể xóa những file không còn tham chiếu và khiến lịch sử cũ không còn đọc được. Không giảm retention xuống quá thấp chỉ để tiết kiệm storage nếu có streaming readers, rollback, long-running jobs hoặc compliance. Kiểm tra an toàn retention trước khi cleanup.

### 9.6. Schema evolution là quyết định governance

Khi nguồn thêm trường hoặc đổi kiểu:

1. Xác định đây là breaking hay non-breaking change.
2. Cập nhật source/target data contracts.
3. Xem có cần backfill.
4. Kiểm tra tables/views/BI downstream.
5. Giữ log version, commit và tests.
6. Chỉ bật schema auto-merge khi có policy kiểm soát.

Không bật tự động chấp nhận mọi field ở bảng Gold nhạy cảm rồi xem đó là khả năng phục hồi schema.

## 10. Medallion architecture: Bronze, Silver, Gold

### 10.1. Bronze: giữ dữ liệu nguồn có chứng cứ

Bronze nên giữ raw payload hoặc schema gần nguồn và metadata:

- Event/file ID, source name, ingestion timestamp UTC.
- Schema version, source partition/offset nếu có.
- Tenant và data classification.
- Trường lỗi hoặc rescued data theo capability hỗ trợ.
- Retention đủ để replay khi pipeline Silver lỗi.

Nếu source bị sai kiểu, vẫn cần biết nguồn nào tạo lỗi và có khả năng khắc phục; không im lặng drop ngay.

### 10.2. Silver: sạch có quy tắc

Silver thường xử lý:

- Parse/cast kiểu dữ liệu.
- Check null/amount/status/domain.
- Timezone, currency và code normalization.
- Deduplicate theo business key/source version.
- Upsert với late-arriving changes.
- Enrichment/join giữa các sources.
- Data quality metrics và quarantine.

Mỗi quy tắc phải có owner và test; tên Silver không đảm bảo dữ liệu đúng.

### 10.3. Gold: metric và grain rõ

Một Gold aggregate nên được tài liệu hóa:

~~~text
Metric: paid_gross_value
Grain: tenant_id + calendar_date (UTC)
Source: silver.orders
Filter: latest source_version, status = paid
Formula: sum(quantity * unit_price)
Excludes: tax, refund, discount in this lab
Business owner: Commerce Analytics
Freshness target: trước 07:00 UTC hằng ngày (ví dụ)
~~~

Nếu Business yêu cầu ngày theo múi giờ Việt Nam hoặc một region khác, không mặc định cắt ngày UTC cho mọi tenant.

### 10.4. Quản trị bảng

Mỗi bảng Delta nên có:
- Owner và steward.
- Catalog/schema và quyền dữ liệu.
- Schema, contract version và lineage.
- Freshness và chất lượng.
- Retention và backup/recovery.
- Storage layout/performance policy.
- Cost budget và người xử lý incident.

Bảng dữ liệu mới là một sản phẩm phục vụ người dùng; không chỉ là một folder có tệp.


## 11. Đọc dữ liệu ADLS Gen2 bằng batch

### 11.1. Ưu tiên storage path được quản trị

Trong workspace đã cấu hình **Unity Catalog volume** và permissions phù hợp:

~~~python
source_path = (
    "/Volumes/<catalog>/<schema>/<volume>/landing/orders/"
)

df_batch = (
    spark.read
         .format("json")
         .load(source_path)
)

df_batch.printSchema()
~~~

Đường dẫn trên là placeholder, không phải file lab có sẵn. Phải dùng catalog/schema/volume đã được nhóm Data Platform cấp quyền; không lưu SAS/account key vào notebook code.

### 11.2. CSV với schema tường minh

~~~python
from pyspark.sql.types import (
    StructType, StructField,
    StringType, IntegerType, DecimalType
)

product_schema = StructType([
    StructField("sku", StringType(), False),
    StructField("quantity", IntegerType(), True),
    StructField("unit_price", DecimalType(18, 2), True)
])

products = (
    spark.read
         .format("csv")
         .option("header", "true")
         .schema(product_schema)
         .load(
             "/Volumes/<catalog>/<schema>/<volume>/landing/products/"
         )
)
~~~

Không phụ thuộc **inferSchema** cho data contracts quan trọng; kiểu dữ liệu, nullability, encoding và header có thể thay đổi khi upstream tạo tệp mới.

### 11.3. Vì sao đọc lại toàn bộ folder mỗi ngày gây vấn đề?

Một thư mục tích lũy 100.000 tệp/ngày. Nếu batch job luôn đọc lại tất cả:

- Tăng storage listing và network requests.
- Tốn compute/RU ở những nguồn có định giá khác.
- Dễ tạo duplicate nếu append vào target.
- Reprocess lịch sử không được kiểm soát.
- Tăng small-file overhead.
- Khó xác định đâu là records mới sau sự cố.

Có thể dùng ingestion manifests, source metadata hoặc **Auto Loader** để tăng dần và track tiến độ.

## 12. Auto Loader: file-based incremental ingestion

### 12.1. Auto Loader là gì?

Databricks **Auto Loader** dùng nguồn **cloudFiles** để phát hiện files mới từ cloud storage và đưa vào Structured Streaming pipeline. Nó có schema location và checkpoint để theo dõi input đã nhận.

~~~mermaid
flowchart LR
    F["ADLS Gen2 files"] --> A["Auto Loader cloudFiles"]
    A --> C["Checkpoint / Schema state"]
    A --> B["Bronze Delta table"]
    B --> S["Silver cleaning"]
~~~

Auto Loader có các cơ chế file discovery như directory listing hoặc file-event/notification-based theo cấu hình được hỗ trợ. Cần kiểm tra feature prerequisites và quyền Azure Storage; không mặc định mọi workspace có tự động quản lý file events.

### 12.2. Ví dụ đọc JSON files mới

Giả sử một Unity Catalog volume cho phép đọc landing và ghi schema/checkpoint:

~~~python
landing = (
    "/Volumes/<catalog>/<schema>/<volume>/landing/orders/"
)
schema_location = (
    "/Volumes/<catalog>/<schema>/<volume>/schemas/orders/"
)
checkpoint = (
    "/Volumes/<catalog>/<schema>/<volume>/checkpoints/orders_bronze/"
)

bronze_stream = (
    spark.readStream
         .format("cloudFiles")
         .option("cloudFiles.format", "json")
         .option("cloudFiles.schemaLocation", schema_location)
         .load(landing)
)

query = (
    bronze_stream.writeStream
                 .format("delta")
                 .option("checkpointLocation", checkpoint)
                 .trigger(availableNow=True)
                 .toTable(
                     "<catalog>.<schema>.orders_bronze"
                 )
)

query.awaitTermination()
~~~

Điều kiện:
1. Compute/runtime hỗ trợ Auto Loader và Structured Streaming.
2. Đường dẫn volume và quyền đọc/ghi phù hợp.
3. Checkpoint/schemaLocation là paths bền vững.
4. Target table có quyền create/write.
5. Tên catalog/schema/volume được thay bằng tên thật.
6. Không có một query khác đang dùng chung checkpoint không tương thích.

**availableNow=True** có ý nghĩa xử lý dữ liệu đang có qua một hoặc nhiều micro-batches rồi dừng theo semantics hỗ trợ; đây không phải stream 24/7 tự chạy.

### 12.3. Checkpoint khác logging

Checkpoint được Spark dùng để khôi phục offsets, trạng thái và tiến độ sink. Nếu xóa checkpoint rồi start lại, có thể:

- Nạp lại files đã xử lý.
- Duplicate records trong append target.
- Dẫn đến behavior khác khi schema/location thay đổi.
- Mất giả định idempotency và khả năng recovery.

Không dùng một checkpoint chung cho hai pipelines hoặc tùy tiện xóa để “chữa lỗi” streaming. Khi thay source, schema, query semantics hoặc target, cần kiểm tra compatibility và migration plan.

### 12.4. Schema drift và rescued data

Khi file mới thêm cột hoặc đổi kiểu:

- Pipeline có thể cập nhật schema theo configuration.
- Có thể dừng để đợi can thiệp.
- Có thể đưa dữ liệu không khớp vào rescued data field theo tính năng hỗ trợ.
- Có thể fail nếu target Delta schema không chấp nhận.

Không cho phép mọi thay đổi schema tự chạy xuyên Bronze, Silver, Gold nếu nó ảnh hưởng metric doanh thu, quyền riêng tư hoặc backward compatibility.

## 13. Structured Streaming và xử lý event-time

### 13.1. Batch và streaming

**Batch** đọc tập dữ liệu hữu hạn rồi kết thúc. **Structured Streaming** xử lý dữ liệu mới một cách tăng dần theo triggers, source offsets, checkpoint và sink semantics.

~~~mermaid
sequenceDiagram
    participant S as Source
    participant Q as Streaming Query
    participant C as Checkpoint
    participant D as Delta table
    S->>Q: Micro-batch input
    Q->>C: Read progress and state
    Q->>D: Write output batch
    Q->>C: Advance checkpoint
    S->>Q: Next input
~~~

- **Micro-batch** là nhóm records thực thi trong một batch logic.
- **Checkpoint** lưu tiến độ/stream state.
- **Trigger** quyết định khi nào xử lý dữ liệu.
- **Watermark** giúp giới hạn state cho những phép tính dựa trên event time.
- **Sink** có thể là Delta table hoặc đích khác được hỗ trợ.

Mọi sink không có cùng transaction semantics. Ghi Delta với checkpoint phù hợp khác việc tự gửi HTTP/JDBC trong **foreachBatch**.

### 13.2. Event time khác processing time

Ví dụ:

~~~text
Event A occurred 10:00, arrived 10:01
Event B occurred 09:55, arrived 10:20
~~~

Nếu chỉ group theo lúc Spark nhận event thì Event B dễ bị xếp sang bucket sai. Cần xác định:

- Event time do nguồn cung cấp.
- Ingestion time vào lake.
- Processing time trong Spark.
- Late event policy.
- Timezone chuẩn hóa và calendar date logic.

### 13.3. Watermark và window

Giả sử một streaming DataFrame **events** có các trường event_time TIMESTAMP và tenant_id STRING:

~~~python
from pyspark.sql import functions as F

windowed = (
    events
    .withWatermark("event_time", "15 minutes")
    .groupBy(
        F.window("event_time", "5 minutes"),
        F.col("tenant_id")
    )
    .count()
)
~~~

Đây chỉ là streaming transformation; chưa có sink và checkpoint. Watermark giúp giới hạn state và xác định late-data handling theo output mode. Một event đến quá trễ có thể bị bỏ qua. Không chọn 15 phút nếu event nguồn thường đến trễ 3 ngày.

### 13.4. Exactly-once cần hiểu phạm vi

Structured Streaming và Delta có cơ chế khôi phục/transaction theo nguồn và sink được hỗ trợ. Tuy nhiên:

- Source có thể phát lại event.
- Business event ID có thể trùng.
- Một Spark job có thể retry task.
- External HTTP API/JDBC sink không mặc nhiên idempotent.
- Pipeline có thể đọc lại dữ liệu nếu checkpoint bị xóa.
- MERGE cần keys/staging dedup đúng.

Với **foreachBatch**, sử dụng batchId cùng transaction/idempotency key thích hợp để tránh side effects lặp lại. Không gọi đó là exactly-once end-to-end nếu chưa chứng minh từng bước.

### 13.5. Stateful streaming cần quan sát state size

Một window aggregation hoặc streaming join có thể giữ state theo keys/watermark. Nếu watermark quá dài, key cardinality quá cao hoặc late events không được giới hạn, state tăng mạnh và micro-batches chậm dần.

Theo dõi:
- Input rows/second.
- Processed rows/second.
- Batch duration.
- State store memory/rows.
- Watermark progress.
- Backlog/source lag.
- Shuffle/spill/errors.
- Checkpoint health.

Nếu mục tiêu chỉ xử lý tệp mỗi giờ, triggered batch/availableNow có thể đơn giản và rẻ hơn chạy stream liên tục.

## 14. Unity Catalog: governance, phân quyền và lineage

### 14.1. Cấu trúc đối tượng

~~~mermaid
flowchart TD
    M["Unity Catalog metastore / governance"] --> C["Catalog: analytics"]
    C --> S1["Schema: bronze"]
    C --> S2["Schema: silver"]
    C --> S3["Schema: gold"]
    S1 --> T1["Delta tables"]
    S2 --> T2["Delta tables"]
    S3 --> T3["Tables, views, BI"]
    C --> V["Volumes / external locations"]
~~~

Catalog, schema, table và volume có owner, privileges và lifecycle. Một workspace có thể được gắn với khả năng governance theo tổ chức; không mặc định mọi workspace đều được cấp quyền truy cập mọi catalog.

### 14.2. Unity Catalog và Azure identity

Với ADLS Gen2, một tổ chức có thể sử dụng **Azure Databricks access connector** và managed identity để tạo storage credential, external location hoặc managed storage theo khả năng Unity Catalog. Cần:

1. Azure identity có đúng RBAC/ACL trên Storage.
2. External location/volume được tạo trong Unity Catalog.
3. Quyền Unity Catalog cho user/service principal/workload.
4. Network/DNS và private endpoint path hợp lệ.
5. Không lộ account keys hoặc SAS tokens trong notebook.
6. Data owner và steward được phân công.

**Azure Storage Blob Data Contributor** trên storage không tự cấp quyền SELECT một Unity Catalog table. Ngược lại, GRANT SELECT trong UC chưa đủ nếu underlying storage credential/network bị cấu hình sai.

### 14.3. SQL privileges minh họa

Ví dụ Databricks SQL với objects đã tồn tại, không tạo mới:

~~~sql
GRANT USE CATALOG
ON CATALOG analytics
TO data_analyst_group;

GRANT USE SCHEMA
ON SCHEMA analytics.gold
TO data_analyst_group;

GRANT SELECT
ON TABLE analytics.gold.daily_orders
TO data_analyst_group;
~~~

Tên principal và tables là minh họa. Cần quyền grant phù hợp, và các quyền có thể được kế thừa theo cấu hình. Với dữ liệu nhạy cảm, nên dùng views/row filters/column masks theo khả năng được hỗ trợ để kiểm soát PII/tenant scope.

### 14.4. Least privilege

| Vai trò | Quyền gợi ý | Không nên cấp mặc định |
|---|---|---|
| Data engineer Bronze | Đọc nguồn, ghi bảng Bronze được giao | Toàn bộ catalogs production |
| Transformation job Silver | SELECT Bronze, MODIFY Silver | Account admin, all storage keys |
| BI analyst | SELECT Gold/views được phê duyệt | Read raw PII hoặc ghi Bronze |
| Security auditor | Metadata/logs theo yêu cầu | Tùy ý sửa/xóa dữ liệu |
| CI/CD service principal | Deploy jobs/tables trong scope | Owner toàn subscription |
| Platform admin | Compute/network/governance quản trị | Sử dụng danh tính admin cho pipelines |

Không đồng nhất workspace membership, compute access, SQL privileges và Azure RBAC: đó là **nhiều mặt phẳng quyền độc lập**.

### 14.5. Lineage và data discovery

Lineage hỗ trợ trả lời:
- Báo cáo Gold dựa vào bảng Silver/Bronze nào?
- Notebook/job nào tạo dữ liệu?
- Cột doanh thu có nguồn và transformation nào?
- Ai là owner khi schema thay đổi?

Tính đầy đủ lineage phụ thuộc cách hoạt động/job/query được hỗ trợ ghi nhận. Không dùng lineage như bằng chứng không có bất kỳ truy cập ngoài hệ thống nào nếu còn pipelines hoặc công cụ không được theo dõi.

## 15. Mạng, secrets và bảo mật workspace

### 15.1. Kết nối Azure an toàn

~~~mermaid
flowchart LR
    APP["Databricks workload"] --> DNS["DNS / VNet routing"]
    DNS --> ADLS["ADLS Gen2 private or approved endpoint"]
    APP --> UC["Unity Catalog authorization"]
    UC --> ID["Managed identity / storage credential"]
    ID --> ADLS
    APP --> LOG["Logs / Monitoring"]
~~~

Một hệ thống private-data architecture có thể cần:

- Workspace/compute networking được thiết kế theo deployment model.
- Private Endpoints tới ADLS, Key Vault và các tài nguyên khác nếu phù hợp.
- Private DNS Zones và resolver hoạt động.
- Network Security Groups/route/firewall bảo vệ luồng traffic.
- Egress controls, allowed libraries/package repositories.
- Kết nối Microsoft Entra token endpoints nếu identity yêu cầu.

**Classic compute và serverless có thể có network requirements khác nhau**; không áp một sơ đồ subnet duy nhất cho mọi tính năng.

### 15.2. Secrets và thông tin nhạy cảm

- Không hard-code client secret, storage account key hoặc SAS trong notebook.
- Dùng Microsoft Entra authentication, service principal federation/managed identity khi có thể.
- Với secrets thực sự bắt buộc, sử dụng cơ chế secret management được tổ chức cho phép (Key Vault integration/Databricks secrets).
- Không in token qua print/display/log.
- Không đưa PII production vào notebook demo hoặc shared tables.
- Quản lý quyền SELECT/READ VOLUME và data retention.
- Tách identities cho runtime và pipeline deployment.

**Secret scope không tự là hàng rào dữ liệu cấp tenant**. Một identity có nhiều quyền storage vẫn có thể truy cập dữ liệu ngoài dự kiến nếu policies không được cấu hình đúng.

### 15.3. Encryption, compliance và dữ liệu cá nhân

Cần kiểm tra:
- Encryption at rest và in transit.
- Customer-managed keys nếu compliance yêu cầu và tính năng hỗ trợ.
- Audit logs, access logs và retention.
- Data residency của workspace, storage, secondary/replicas và logs.
- Row/column access controls hoặc views.
- Token/credential rotation và break-glass access.
- Backup/restore và deletion policies.

**VACUUM một bảng Delta không chứng minh mọi bản dữ liệu đã bị xóa khỏi cloud backups hoặc downstream BI extracts.** Cần kế hoạch end-to-end data lifecycle và legal hold nếu áp dụng.


## 16. Tối ưu hiệu năng Spark

### 16.1. Tìm nguyên nhân trước khi tăng số workers

Một job chậm có thể do:

- Input có nhiều tệp nhỏ.
- Shuffle rất lớn trong groupBy/join/orderBy.
- Data skew: một key có nhiều records.
- Python UDF làm giảm khả năng tối ưu expression.
- Cache quá nhiều làm executor memory bị pressure.
- Driver collect quá nhiều dữ liệu.
- Executor memory spill hoặc out-of-memory.
- Query đọc quá nhiều columns/partitions.
- Thiếu data skipping/file layout thích hợp.
- Chỉ có một task lớn nên không tận dụng nhiều workers.
- Nhiều job cùng dùng compute/warehouse bị contention.

Không mặc định tăng kích thước cluster là giải pháp; Spark UI và query plan thường chỉ ra vấn đề nằm ở đâu.

### 16.2. Đọc execution plan

~~~python
gold.explain("formatted")
~~~

Xem:

- Exchange: dữ liệu bị shuffle ở đâu?
- Scan: đọc những files/columns nào?
- Filter pushdown và partition pruning có hiệu lực không?
- Broadcast join có được sử dụng đúng không?
- SortAggregate/HashAggregate và số partitions.
- Adaptive query execution adjustments.
- Các operators có tốn CPU/IO hơn dự kiến không?

Cần liên hệ execution plan với Spark UI stages, tasks, shuffle read/write, skew và spill metrics.

### 16.3. Số lượng partitions

Nhiều partitions quá nhỏ gây scheduler overhead; ít partitions quá lớn gây thiếu parallelism, memory pressure và long tail. Một số thao tác:

~~~python
# Repartition khi có lý do rõ ràng để phân phối lại dữ liệu.
balanced = source_df.repartition(32)

# Coalesce thường giảm số partitions mà không cần full shuffle
# trong những tình huống được Spark hỗ trợ.
smaller = balanced.coalesce(8)
~~~

Các số 32 và 8 chỉ là minh họa. Không chọn cố định cho mọi data size, cluster size và file layout.

**repartition(32, "tenant_id") không chữa được skew nếu 80% records cùng tenant_id**: cùng key vẫn về cùng partition theo hash. Có thể cần chia theo key bổ sung, salting, AQE hoặc thiết kế aggregation hai tầng.

### 16.4. Broadcast join

Khi một dimension table nhỏ và được phép nhân bản lên executors:

~~~python
from pyspark.sql import functions as F

joined = facts.join(
    F.broadcast(dimensions),
    on="product_id",
    how="left"
)
~~~

Broadcast có thể tránh shuffle lớn của bảng facts, nhưng phải đo memory. Không broadcast bảng “ít dòng” mà mỗi dòng chứa rất nhiều dữ liệu; nếu không vừa RAM, executors có thể thất bại.

### 16.5. Adaptive Query Execution (AQE)

**Adaptive Query Execution** cho phép Spark điều chỉnh một số quyết định query plan dựa trên runtime statistics, ví dụ coalescing shuffle partitions hoặc xử lý skew trong các operator được hỗ trợ.

Kiểm tra cấu hình và behavior runtime thực tế:

~~~python
spark.conf.get("spark.sql.adaptive.enabled")
~~~

Đừng thay hàng loạt spark.sql.* configs theo blog cũ mà không benchmark trên Databricks Runtime đang dùng; các defaults và tối ưu hóa có thể đã thay đổi.

### 16.6. Built-in functions thường tốt hơn Python UDF

Ví dụ thay:

~~~python
# Hạn chế Python UDF nếu logic có thể biểu diễn bằng
# Spark SQL functions.
normalized = df.withColumn(
    "normalized_email",
    F.lower(F.trim(F.col("email")))
)
~~~

Nếu business cần Unicode/case folding phức tạp, phải đánh giá đúng semantics và kiểm thử; nhưng về hiệu năng nên cân nhắc Spark built-ins trước Python UDF, do overhead serialization và khả năng optimizer không nhìn được logic tùy ý.

### 16.7. Cache khi có reuse thực sự

~~~python
reused = source_df.filter(F.col("status") == "paid").cache()

# Action materialize cache.
reused.count()

# Hai downstream operations cùng dùng reused.
a = reused.groupBy("tenant_id").count()
b = reused.groupBy("customer_id").count()

# Sau khi dùng xong:
reused.unpersist()
~~~

Cache không phải tối ưu mặc định. Nó tiêu tốn memory/disk và có thể gây eviction/spill nếu dataset lớn hơn capacity. Không cache dữ liệu chỉ được dùng đúng một lần.

### 16.8. Small files và Delta optimization

Khi append hàng chục nghìn micro-batches hoặc nhiều tasks, Delta table có thể có nhiều data files nhỏ:

- Listing/metadata overhead.
- Khởi tạo tasks nhiều.
- Query latency tăng.
- Storage transaction/compute cost lớn.

Có thể dùng compaction/OPTIMIZE và cơ chế automatic optimization được hỗ trợ:

~~~sql
-- Chỉ chạy trên bảng lab có quyền và nhu cầu thực.
OPTIMIZE training_catalog.sandbox.orders_silver_lab;
~~~

Không OPTIMIZE mọi bảng sau mỗi micro-batch. Nên chọn lịch/tần suất theo file sizes, query patterns và cost. Các phương pháp như **Z-ORDER** hoặc **liquid clustering** có hỗ trợ và điều kiện riêng; không trộn tùy tiện các chiến lược layout khi chưa kiểm tra feature matrix.

### 16.9. Partitioning của Delta table khác Spark partitions

- **Spark partitions:** các đơn vị dữ liệu thực thi trong job.
- **Delta table partitioning:** cách tổ chức file/table data trên storage theo một/một số partition columns nếu được chọn.
- **Unity Catalog schema:** namespace metadata.
- **Cosmos DB partition key:** cơ chế phân phối dữ liệu của một dịch vụ khác.

Chia Delta table theo customer_id có cardinality rất cao có thể tạo nhiều thư mục/tệp nhỏ. Nếu cần partitioning theo ngày, kiểm tra volume mỗi ngày, access patterns và pruning. **Không partitionBy mọi cột**.

## 17. Tính chi phí Azure Databricks

### 17.1. Các thành phần chi phí chính

Một ước lượng tổng chi phí cần xem:

~~~text
Total data platform cost =
    Azure Databricks usage (DBUs / workload billing model)
  + Azure infrastructure compute where applicable
  + ADLS Gen2 data storage and transactions
  + Network egress / private connectivity
  + SQL warehouse usage
  + Job retry/reprocessing and orchestration overhead
  + Monitoring / Log Analytics ingestion and retention
  + Other dependent services (Event Hubs, Key Vault, etc.)
~~~

**DBU (Databricks Unit)** là đơn vị dùng trong các mô hình thanh toán Databricks, nhưng giá/mô hình tính tiền tùy tier, workload, serverless/classic compute và hợp đồng. Với classic compute có thể còn phí VM/hạ tầng Azure riêng. Đừng nhân một mức giá DBU duy nhất cho mọi workload.

### 17.2. Chọn compute đúng workload

| Nhu cầu | Lựa chọn bắt đầu đánh giá | Chú ý |
|---|---|---|
| Một data engineer khám phá nhỏ | Interactive compute có auto-termination | Tránh idle cả đêm |
| ETL hằng đêm | Jobs compute | Startup overhead và runtime |
| Streaming luôn chạy | Compute phù hợp continuous streaming | SLA/backpressure, cost 24/7 |
| Dashboard SQL | SQL warehouse | Auto-stop, concurrency và price |
| File ingestion theo giờ | availableNow job | Dễ kiểm soát khi dữ liệu thưa |
| POC dữ liệu nhỏ | Compute nhỏ hoặc công cụ nhẹ hơn | Databricks có thể không cần thiết |

### 17.3. Ví dụ minh họa tiền compute

Giả sử một pipeline chạy 20 phút mỗi giờ:

~~~text
Tổng processing time/ngày:
  24 × 20 phút = 480 phút = 8 giờ.

Nếu giữ compute hoạt động 24 giờ:
  có thể trả cho idle time đáng kể theo mô hình.

Nếu dùng jobs compute tắt sau run:
  trả theo usage/capacity và startup overhead.
~~~

Đây không phải bảng giá thật. Cần so **DBU + compute/infrastructure + storage/network/logging** và xem serverless billing khác classic compute thế nào. Một job quá nhiều lần khởi động compute nhỏ có thể không rẻ hơn job dài nếu startup overhead lớn.

### 17.4. Những đòn bẩy tiết kiệm

- Auto-termination cho interactive compute.
- Dùng jobs compute cho chạy định kỳ.
- Right-size driver/workers theo Spark UI.
- Giảm đọc lại data cũ bằng incremental ingestion.
- Sử dụng Delta file optimization khi có lợi.
- Tránh collect/toPandas tập dữ liệu lớn.
- Hạn chế shuffle và Python UDF không cần thiết.
- Giới hạn retry vô hạn, concurrency và job timeout.
- Theo dõi network egress, logs và storage retention.
- Gắn tags/cost attribution theo team, environment, job.
- Dùng các options pricing/commitment nếu tổ chức đủ điều kiện.

Không tiết kiệm bằng cách tắt audit, hạ retention cần cho phục hồi hoặc giảm bảo mật mạng mà chưa được phê duyệt.

### 17.5. Monitoring cost theo workload

Mỗi pipeline nên ghi:
- Job ID và release version.
- Số input files/rows và bytes.
- Thời gian, compute type và worker count.
- Output rows/bytes và số partitions/files.
- Retries, failures và root causes.
- Cost attribution/usage tags.
- Resource budget và notification owner.

Có thể so **cost per million rows processed** giữa các phiên bản pipeline để phát hiện regression, nhưng chỉ có ý nghĩa khi cùng chất lượng dữ liệu, kết quả và SLA.

## 18. Databricks Jobs/Workflows: điều phối pipeline

### 18.1. Dependency graph

~~~mermaid
flowchart TD
    I["Ingest orders"] --> Q["Validate schema / quarantine"]
    Q --> S["Silver merge"]
    S --> G["Gold aggregate"]
    G --> T["Data quality / reconciliation"]
    T --> P["Publish / notify"]
    Q --> F["Alert data owner on failure"]
    S --> F
    G --> F
~~~

Một workflow thường có tasks, dependencies, compute configuration, parameters, schedule/trigger, retries và notifications. Databricks hỗ trợ nhiều loại task theo phiên bản sản phẩm; không mặc định mọi type có ở tất cả workspaces.

### 18.2. Job cần idempotency

Nếu task Silver merge thành công nhưng task Gold thất bại, workflow được retry. Không nên cứ append Silver lại mà tạo duplicate records.

Các chiến lược:

- Merge theo business keys/source version.
- Lưu ingestion batch ID và nguồn đã processed.
- Dùng Delta transactions/checkpoints đúng.
- Chia commit boundaries rõ.
- Quarantine invalid records và retry chọn lọc.
- Ghi runId và alert có correlation IDs.
- Kiểm thử rerun cùng input cho cùng output business.

**Retry** chỉ giúp hệ thống phục hồi khi gặp lỗi transient nếu logic side effects được thiết kế an toàn.

### 18.3. Tách notebooks development và jobs production

Trong phát triển, notebook có thể:
- Đọc một tập nhỏ để khám phá.
- Dùng display, show, explain.
- Chạy từng cell thủ công.
- Thay đổi parameters/paths tạm thời.

Trong production:
- Dùng job/task parameters kiểm soát.
- Không phụ thuộc vào thứ tự cell đã chạy thủ công.
- Dùng code modules/functions tái sử dụng khi thích hợp.
- Cấu hình timeout, retries, notifications.
- Không lưu secrets trong notebook.
- Có logs và data quality gates.
- Có CI/CD, tests và release metadata.

Không nên copy một notebook thí nghiệm đầy cell tạm vào production rồi chỉ đặt lịch mà không kiểm tra idempotency.

### 18.4. CI/CD và source control

Một pipeline chuyển từ dev tới production nên quản lý:

~~~text
Git repository
  ├─ src/              transformation code
  ├─ notebooks/        interactive workflows
  ├─ tests/            unit / contract tests
  ├─ sql/              table definitions / business views
  ├─ deployment/       bundle/IaC configuration
  └─ docs/             source contracts, runbooks, ADRs
~~~

Cấu trúc thư mục là ví dụ kiến trúc, **không yêu cầu tạo file** trong assignment này.

Có thể sử dụng những công cụ deployment Databricks được hỗ trợ (bundles/CLI/APIs/IaC) và Azure DevOps/GitHub Actions với service identity; chi tiết phụ thuộc hệ sinh thái hiện hành.

Tách:
1. CI chạy lint/unit tests.
2. Integration test ở catalog/schema staging.
3. Data contract/security validation.
4. CD deploy workflow/compute config dưới identity phù hợp.
5. Production approval gate.
6. Monitoring/canary và rollback plan.

### 18.5. Parameters và môi trường

Một job parameter set có thể gồm:

~~~json
{
  "environment": "staging",
  "input_catalog": "commerce_staging",
  "output_catalog": "analytics_staging",
  "process_date": "2026-11-20",
  "run_mode": "incremental",
  "fail_on_quality_error": true
}
~~~

Đây là schema minh họa do nhóm tự thiết kế, không phải JSON API Databricks Job bắt buộc. Không cho người dùng bất kỳ truyền tên catalog sản xuất qua parameter rồi đọc/ghi dữ liệu vượt quyền; kiểm tra allowlist và quyền UC.

### 18.6. Hệ thống orchestration ngoài Databricks

Databricks Jobs có thể kết hợp Azure Data Factory, Microsoft Fabric pipelines, Azure Functions hoặc các orchestrators khác theo nhu cầu. Tránh tạo hai scheduler độc lập cùng chạy một pipeline và ghi đè dữ liệu trùng.

Nếu ADF gọi Databricks job, cần xác định rõ:
- Ai là owner của schedule?
- Nơi lưu retries/checkpoints?
- Nơi tập trung SLA/alerts?
- Mục nào là source of truth cho job status?
- Có cách cancel/failover khi chạy trùng không?

## 19. Data quality và kiểm thử

### 19.1. Các loại test

| Loại | Ví dụ | Khi chạy |
|---|---|---|
| Schema | Không thiếu order_id, unit_price là DECIMAL | Ingest/PR |
| Domain | quantity > 0, status hợp lệ | Silver |
| Uniqueness | Một row mới nhất cho tenant_id + order_id | Silver |
| Referential | product_id có trong dimension | Silver/Gold |
| Freshness | Dữ liệu có cập nhật trong SLA | Sau job |
| Volume | Số dòng không giảm bất thường | Sau ingest |
| Reconciliation | Tổng giá trị orders khớp source trong tolerance | Gold/cutover |
| Permission | BI không đọc được PII Bronze | Release/security |
| Idempotency | Chạy hai lần input giống nhau không nhân đôi kết quả | Integration test |
| Failure recovery | Checkpoint/retry hoạt động | Staging chaos test |

### 19.2. Quyết định fail fast hay quarantine

Không phải mọi lỗi dữ liệu đều cần dừng cả pipeline:

- **Invalid quantity:** quarantine row và báo data owner nếu policy cho phép partial success.
- **Thiếu critical schema:** fail pipeline trước khi xuất bản Gold.
- **Một tenant bị lỗi:** có thể isolate tenant nếu business cho phép.
- **PII xuất hiện ở cột không được phép:** chặn release và báo security.
- **File bị duplicate:** xử lý bằng source key/idempotency.
- **Late event:** áp business watermark/backfill policy.

Cần mô tả rõ “partial success” và không báo báo cáo đạt SLA nếu 20% tenant data đã bị quarantine.

### 19.3. Constraints khi phù hợp

Ở Delta tables có hỗ trợ, có thể dùng NOT NULL hoặc CHECK constraints. Ví dụ minh họa trên bảng lab đã tồn tại và chỉ sau khi xác minh dữ liệu tương thích:

~~~sql
ALTER TABLE training_catalog.sandbox.orders_silver_lab
ADD CONSTRAINT positive_quantity CHECK (quantity > 0);
~~~

Không thêm constraint vào bảng Bronze raw chứa dòng sai rồi khiến toàn bộ ingestion bị dừng ngoài kế hoạch. CHECK cũng không thay thế uniqueness business logic/foreign key semantics mà nó không hỗ trợ.

### 19.4. Testing incremental và late data

Một bộ test nên bao gồm:

1. Source event mới.
2. Event trùng source ID.
3. Event cũ đến sau bản mới.
4. Event bị mất field bắt buộc.
5. Source thêm cột.
6. Price/null sai kiểu.
7. Job crash giữa Bronze và Silver.
8. Rerun cùng batch ID.
9. Stream restart với checkpoint.
10. Data backfill sau khi code đã đổi.

Kết quả phải được kiểm chứng bằng **đầu ra bảng và metrics**, không chỉ “job chạy trạng thái Success”.

## 20. Quan sát và xử lý sự cố

### 20.1. Spark UI giúp gì?

Spark UI có thể thể hiện:
- Jobs và stages.
- Duration theo stage/task.
- Shuffle read/write.
- Spill memory/disk.
- Executor memory/CPU.
- Failed/retried tasks.
- Query SQL plans/physical operators.
- Skew: một vài tasks lâu hơn phần còn lại.

Nếu job chậm do một task xử lý 90% dữ liệu, tăng workers có thể không cứu được. Nếu mọi executor cùng bị memory spill, cần xử lý query plan/partition size hoặc capacity.

### 20.2. Databricks job và pipeline telemetry

Các tín hiệu vận hành:

| Tín hiệu | Lý do |
|---|---|
| Job run status/duration | Pipeline SLA |
| Task retries/failures | Transient vs permanent error |
| Rows/bytes ingested | Data volume/freshness |
| Quarantine counts | Chất lượng nguồn |
| Input/output schema versions | Phát hiện drift |
| Streaming lag | Dữ liệu chậm, checkpoint backlog |
| Shuffle/spill/skew | Bottleneck Spark |
| Cluster/SQL warehouse usage | Capacity/cost |
| Delta table history | Biến động schema/data |
| Unity Catalog audit/lineage | Governance |
| Azure Storage errors | Network/storage/quota |
| Cost by job/team | Budget |

Nên lưu run metadata có timestamp UTC, commit SHA, job ID, environment, table versions và source identifiers. Tránh đưa PII hoặc credentials vào log.

### 20.3. Bảng lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều tra |
|---|---|---|
| Job stuck ở stage cuối | Skew hoặc một task lớn | Spark UI task durations, key distribution |
| Executor OutOfMemory | Partition quá lớn, cache, join | Memory/spill, partition sizes |
| Driver OutOfMemory | collect/toPandas dữ liệu lớn | Bỏ collect, dùng distributed write |
| Shuffle rất lớn | groupBy/join/orderBy | Explain plan, partitioning, AQE |
| Nhiều small files | Micro-batch writes liên tục | File metrics, optimize policy |
| FileNotFound | Source path/quyền/retention | UC volume, ADLS paths, file lifecycle |
| 403 khi đọc ADLS | Storage RBAC/ACL, credential hoặc UC privileges | Kiểm tra từng lớp quyền |
| Job SQL permission denied | Thiếu USE CATALOG/SCHEMA/SELECT/MODIFY | UC grants và principal |
| Stream xử lý lại input | Checkpoint bị reset hoặc source changed | Checkpoint/state review |
| Late events bị mất | Watermark quá ngắn | Event-time distributions |
| Schema mismatch | Upstream drift, Delta enforcement | Source contract, rescued data |
| MERGE fail | Source duplicate keys hoặc conflicts | Dedup stage, concurrent writers |
| Streaming state quá lớn | Watermark/key cardinality | State metrics và logic |
| Dashboard stale | Job failed, Gold chưa update | Job lineage và freshness |
| Compute idle tốn phí | Quên auto-terminate | Billing, cluster policy |
| Network timeout | VNet/DNS/firewall/private path | Test từ đúng compute environment |
| Python UDF chậm | Serialization/optimizer overhead | Built-in functions hoặc vectorized strategy |

### 20.4. Runbook điều tra theo thứ tự

1. Xác định **job ID, run ID, environment, UTC timestamps**.
2. Kiểm tra lỗi tới từ source, compute, transformation, sink hay quyền.
3. Xem Databricks run/task logs, không chỉ thông báo “Failed”.
4. Xem Spark UI plan/shuffle/spill/skew nếu hiệu năng.
5. Xác minh checkpoint/source offsets khi stream.
6. Kiểm tra Unity Catalog grants, storage credential và network.
7. So schema, data contract, deployment commit với phiên đã thành công.
8. Xác định job có thể retry **an toàn** không.
9. Quarantine/reconcile dữ liệu lỗi, không xóa output vô tội vạ.
10. Run lại có kiểm soát, validate output/metrics và viết postmortem.

**Không xóa checkpoint, VACUUM toàn bảng hoặc mở public Storage firewall chỉ để thử nhanh khi chưa xác định nguyên nhân.**

## 21. Ví dụ kiến trúc end-to-end: doanh thu và clickstream

### 21.1. Yêu cầu

Một nền tảng thương mại có:

- Hàng triệu order records từ Azure SQL Database.
- Clickstream từ web qua Event Hubs.
- Product CSV hàng ngày lưu ở ADLS Gen2.
- Dashboard doanh thu theo tenant/ngày.
- Fraud analytics cần dữ liệu gần real time.
- PII trong customer records phải được bảo vệ.
- Một số tenants có báo cáo riêng.

### 21.2. Thiết kế tham khảo

~~~mermaid
flowchart TD
    SQL["Azure SQL Database"] --> ING["Ingestion / CDC pipeline"]
    EH["Event Hubs clickstream"] --> ST["Streaming ingestion"]
    FILES["Product CSV ADLS"] --> AL["Auto Loader"]
    ING --> BR["Bronze Delta"]
    ST --> BR
    AL --> BR
    BR --> SI["Silver clean + dedupe + joins"]
    SI --> GO["Gold revenue + funnel"]
    GO --> WH["Databricks SQL Warehouse"]
    WH --> DASH["BI dashboards"]
    SI --> ML["Fraud analytics"]
    UC["Unity Catalog"] -. "Access / lineage" .-> BR
    UC -. "Access / lineage" .-> SI
    UC -. "Access / lineage" .-> GO
    JOB["Jobs + monitoring"] --> BR
    JOB --> SI
    JOB --> GO
~~~

Đường CDC từ Azure SQL hoặc Event Hubs chỉ là kiến trúc logic; cần chọn đúng connector/ingestion service hỗ trợ và quyền đọc nguồn. Không mặc định Databricks tự có CDC cho mọi loại Azure SQL database.

### 21.3. Vì sao chia Bronze/Silver/Gold?

- Bronze giữ sự kiện order và clickstream gần nguồn.
- Silver chuẩn hóa event ID, status, currency, timezone, deduplicate.
- Gold định nghĩa revenue và funnel theo business contract.
- Unity Catalog phân quyền: BI đọc Gold, fraud team đọc Silver được lọc, người dùng phổ thông không đọc raw PII.
- Jobs/Workflows điều phối batch và theo dõi sự cố.
- Structured Streaming theo dõi near-real-time events có checkpoint và watermark.
- ADLS Gen2 lưu Delta lâu dài theo retention policy.

### 21.4. Acceptance tests

- Không trùng order sau retry/backfill.
- Late order update không làm doanh thu bị cộng hai lần.
- Invalid currency/negative quantity vào quarantine.
- Gold chỉ tính metrics theo business definitions đã phê duyệt.
- Tenant isolation được kiểm tra trên views/permissions.
- Streaming restart dùng checkpoint không nhân đôi output business.
- Jobs cảnh báo khi freshness SLA không đạt.
- Có lineage/source IDs cho từng báo cáo.
- Có bài kiểm tra cost khi workload tăng đột biến.
- Thử recovery/rollback khi schema mới phá pipeline.


## 22. So sánh Databricks với những lựa chọn dữ liệu khác

### 22.1. Không có một dịch vụ phù hợp mọi workload

| Công cụ/dịch vụ | Mạnh ở đâu | Không nên dùng thay |
|---|---|---|
| **Azure Databricks** | Spark ETL, lakehouse, Delta, streaming/analytics, governed pipelines | Database OLTP cho từng HTTP request |
| **Azure Data Factory** | Orchestration/integration, copy activities và connectors theo thiết kế | Engine tự thực thi mọi Spark transform phức tạp |
| **Azure SQL Database** | Giao dịch quan hệ OLTP, constraints và truy vấn ứng dụng | Spark ETL trên nhiều TB tệp thô |
| **Azure Cosmos DB** | NoSQL applications, partitioned low-latency operations | Tổng hợp ad hoc xuyên data lake khổng lồ |
| **Azure Event Hubs** | Event ingestion/buffering | Lakehouse lưu lâu dài hoặc SQL analytics |
| **ADLS Gen2** | Cloud object storage/dữ liệu thô/Delta files | Tự chạy SQL/Spark compute |
| **Microsoft Fabric** | Nền tảng analytics tích hợp với lakehouse/warehouse/BI theo capability | Không mặc định tương đương từng feature Databricks |
| **Azure Synapse Analytics** | Những workloads SQL/Spark/integration theo khả năng workspace | Cần đánh giá maturity/support và hợp đồng hệ thống |
| **Azure Functions** | Event-driven logic và short-running compute | ETL phân tán hàng TB khi cần Spark |

Một kiến trúc doanh nghiệp có thể dùng nhiều sản phẩm kết hợp. Ví dụ Azure Data Factory kích hoạt Databricks job, ADLS lưu Delta, Event Hubs nhận sự kiện và BI đọc Gold.

### 22.2. Câu hỏi lựa chọn

1. Dữ liệu có lớn đến mức cần phân tán tính toán không?
2. Có cần Spark DataFrame/SQL, ML hoặc streaming không?
3. Muốn quản trị bảng Delta qua Unity Catalog không?
4. Nguồn dữ liệu đã sẵn trong ADLS/Delta hay trong database OLTP?
5. SLA latency là milliseconds, minutes hay hours?
6. Cần governance/lineage, data contracts và nhiều data teams?
7. Đội có kỹ năng Spark/SQL và khả năng quản lý jobs/cost không?
8. Tổng chi phí cần gồm network, storage, VM/DBUs và monitoring thế nào?
9. Có những nền tảng analytics khác đã được tổ chức chuẩn hóa không?
10. Có thể làm POC cho hai ứng viên trước khi khóa kiến trúc không?

**Nếu một query SQL trên 200.000 dòng chạy tốt trong database hiện hữu, không nhất thiết xây Spark pipeline chỉ để “đưa lên cloud hiện đại”.**

## 23. Những lỗi kiến trúc nên tránh

### 23.1. Collect toàn bộ dữ liệu về driver

Sai với bảng lớn:

~~~python
# Không dùng cho bảng production rất lớn.
all_rows = huge_df.collect()
~~~

Đúng về mặt hướng thiết kế:

~~~python
# Spark xử lý phân tán; ghi ra output được quản trị.
aggregated = huge_df.groupBy("tenant_id").count()
# Sau khi có quyền và mục đích rõ, dùng distributed write.
~~~

collect phù hợp để kiểm tra vài dòng/ít dữ liệu có giới hạn; nó không thể được coi là cách export hàng TB.

### 23.2. UDF cho mọi phép biến đổi

Python UDF có serialization overhead và giảm khả năng optimizer hiểu logic. Ưu tiên Spark SQL built-in functions khi phù hợp; chỉ dùng UDF nếu cần thuật toán riêng và đã benchmark.

### 23.3. Đưa secrets trực tiếp vào notebooks

Không nên:

~~~python
# Ví dụ KHÔNG AN TOÀN — không dùng credential thật.
storage_key = "PLACEHOLDER_SECRET"
~~~

Ưu tiên managed identity, storage credentials/Unity Catalog và secret management được tổ chức phê duyệt. Không đưa secrets vào commit history hoặc logs.

### 23.4. Dùng một compute cho mọi nhóm

Một interactive cluster chung cho ETL production, BI dashboard và notebook thử nghiệm có thể gây contention, tăng chi phí và làm khó phân quyền. Tách compute/workload theo SLA, security và budget là lựa chọn cần đánh giá.

### 23.5. Dùng overwrite để chạy lại production

Ví dụ:

~~~python
# Chỉ nên dùng với target đã được xác minh và thay thế có chủ đích.
df.write.mode("overwrite")
~~~

Không chạy overwrite lên Gold production trong một retry khi chưa biết downstream queries và rollback. Ưu tiên transaction/upsert/idempotent patterns, staging tables và controlled promotion.

### 23.6. Bỏ qua late data

Một click event đến trễ 20 phút có thể làm metric thay đổi. Nếu watermark chỉ 5 phút, event đó có thể bị bỏ qua. Cần xác định **late arrival distribution**, business reporting cutoffs và backfill policy.

### 23.7. Xem Delta time travel là backup vĩnh viễn

Time travel phụ thuộc file retention và lịch sử transaction còn sẵn. VACUUM/retention/restore plan cần được quản lý riêng. Đừng dùng nó như giải pháp DR duy nhất.

### 23.8. Tự động chấp nhận mọi schema drift

Tự động thêm hoặc đổi cột từ nguồn không kiểm soát có thể phá Gold metrics, data privacy và BI. Có thể cho Bronze linh hoạt hơn nhưng Silver/Gold cần contract và review.

### 23.9. Bỏ qua partition skew và kích thước tệp

Một hot key có thể làm một task chạy lâu; nhiều triệu file nhỏ làm query tốn metadata overhead. Không thể giải quyết bằng tăng workers vô hạn.

### 23.10. Chỉ giám sát trạng thái Success

Job có thể Success nhưng:
- Chỉ ingest 10% data.
- Thả toàn bộ records vào quarantine.
- Tính sai timezone/doanh thu.
- Đọc Gold version cũ.
- Không cập nhật downstream service.

Production cần **data freshness, quality, reconciliation và business metrics**, không chỉ trạng thái job.

## 24. Kế hoạch triển khai Databricks trên Azure

### 24.1. Giai đoạn 1: yêu cầu và kiến trúc

Chuẩn bị:

- Data sources và volume/velocity/variety.
- Workload batch/streaming và latency SLA.
- Data classification/PII và retention.
- Storage account/container/ADLS Gen2 region.
- Workspace isolation dev/staging/prod.
- Compute model, budget và networking.
- Identity, Unity Catalog, owner và lineage.
- Backup/DR và yêu cầu replay.
- Kịch bản job error/retry và alert.

### 24.2. Giai đoạn 2: nền tảng bảo mật

1. Tạo hoặc sử dụng workspace đã được tổ chức phê duyệt.
2. Cấu hình Microsoft Entra ID/workspace identities.
3. Thiết lập Unity Catalog, catalogs/schemas/tables/volumes.
4. Thiết lập Storage credentials/external locations qua managed identity theo khả năng.
5. Kiểm tra ADLS RBAC/ACL và UC permissions.
6. Kiểm tra private networking/DNS/egress theo compute model.
7. Cấu hình secrets, audit logs và retention.
8. Cấu hình cluster policies, auto-termination và cost tags.

### 24.3. Giai đoạn 3: pipeline và tests

1. Tạo data contracts cho nguồn.
2. Xây Bronze ingestion với source metadata.
3. Xây Silver transformations có quarantine.
4. Xây Gold metrics có chủ sở hữu.
5. Tạo jobs/dependencies, checkpoint và retries.
6. Kiểm thử dữ liệu trùng, dữ liệu trễ, schema drift.
7. Kiểm thử permissions và PII policies.
8. Benchmark với dữ liệu/traffic được ẩn danh hóa.
9. Kiểm thử failure recovery/rollback.
10. Tạo runbook vận hành.

### 24.4. Giai đoạn 4: release và tối ưu

- Triển khai với CI/CD identity có quyền tối thiểu.
- Bật monitor/alerts/tracing.
- Chạy canary hoặc so sánh outputs trước cutover.
- Theo dõi freshness, quality, time-to-completion và costs.
- Tối ưu partition, join, file sizes sau khi có measurements.
- Diễn tập backfill, rollback và data recovery.
- Ghi architecture decision record (ADR) và release metadata.

## 25. Checklist production

### Thiết kế dữ liệu

- [ ] Source owners, schemas và partition/access patterns đã được xác nhận.
- [ ] Có Bronze/Silver/Gold data contracts và metric definitions.
- [ ] Dữ liệu timestamp có timezone policy rõ.
- [ ] Có stable source event IDs/business keys.
- [ ] Late/duplicate/invalid data policy được kiểm thử.
- [ ] Không để raw PII xuất hiện ngoài quyền cho phép.
- [ ] Có lineage và data retention.
- [ ] Đã đánh giá storage layout/Delta table optimization.

### Spark và pipeline

- [ ] Driver không collect dataset lớn.
- [ ] GroupBy/join có xem shuffle/skew và explain plan.
- [ ] Có resource sizing theo dữ liệu thật.
- [ ] Có checkpoint paths bền vững và thuộc job.
- [ ] Không share checkpoint giữa incompatible queries.
- [ ] Ingestion có cơ chế idempotency và rerun.
- [ ] MERGE staged data đã được deduplicate.
- [ ] Có schema evolution policy.
- [ ] Có quarantine và data quality alerts.
- [ ] Có test streaming restart/late events.
- [ ] Các UDF/cache/repartition đều có lý do và benchmark.

### Bảo mật và governance

- [ ] Đúng subscription, resource group, region và workspace.
- [ ] Catalog/schema/table/volume privileges theo least privilege.
- [ ] Managed identity/storage credential đúng scope.
- [ ] Private networking/DNS/TLS/egress đã kiểm tra.
- [ ] Không hard-code secrets hoặc PII trong notebooks/logs.
- [ ] Có audit logs, ownership và change approvals.
- [ ] Data residency, retention và backup policy rõ.
- [ ] CI/CD identity không có quyền admin toàn tổ chức không cần thiết.

### Vận hành và chi phí

- [ ] Jobs có dependency, timeout, retry, notifications.
- [ ] Interactive compute có auto-termination.
- [ ] Có compute policy, max workers, runtime chuẩn.
- [ ] Đã theo dõi DBUs/hạ tầng/ADLS/logging và budget.
- [ ] Có Spark UI/SQL execution diagnostics cho incidents.
- [ ] Có SLA freshness, data quality, volume và output verification.
- [ ] Có runbook source/compute/network/auth/sink/schema/streaming.
- [ ] Có backfill, rollback và recovery test.
- [ ] Các bảng có owner và quy trình VACUUM/retention đúng.
- [ ] Có review sau khi workload/data tăng vượt dự báo.

## 26. Tự kiểm tra kiến thức

1. **Apache Spark giải quyết vấn đề gì?** Xử lý dữ liệu phân tán với DataFrame/SQL/batch/streaming.
2. **Driver làm gì?** Lập query plan, điều phối jobs/stages/tasks và theo dõi thực thi.
3. **Executor làm gì?** Chạy tasks, tính toán và xử lý partitions.
4. **Spark partition có giống Delta table partitioning không?** Không.
5. **Lazy evaluation là gì?** Transformations xây plan, actions kích hoạt thực thi.
6. **Ví dụ action?** count, show, collect, write.
7. **Shuffle xảy ra khi nào?** Khi cần phân phối lại dữ liệu, ví dụ groupBy/join/orderBy.
8. **Data skew gây vấn đề gì?** Một số tasks xử lý khối lượng lớn hơn hẳn tasks khác.
9. **Vì sao collect có thể làm crash driver?** Tập trung dữ liệu lớn về RAM driver.
10. **DataFrame khác pandas thế nào?** DataFrame Spark xử lý phân tán, pandas thường xử lý trên một máy.
11. **Azure Databricks bổ sung gì cho Spark?** Workspace, runtimes, compute, jobs, Delta/SQL và governance.
12. **Unity Catalog quản lý gì?** Objects dữ liệu, quyền, metadata và lineage theo khả năng.
13. **ADLS Gen2 dùng để làm gì?** Lưu file/object data/Delta trên Azure.
14. **Bronze nên lưu gì?** Source data và ingestion metadata đủ để replay.
15. **Silver nên làm gì?** Parse, validate, normalize, deduplicate, enrich và quarantine.
16. **Gold dùng cho gì?** Metrics/data marts theo business contract.
17. **Delta Lake khác Parquet folder thuần ở đâu?** Có transaction log/ACID/schema và DML/time travel theo hỗ trợ.
18. **Time travel có vĩnh viễn không?** Không; phụ thuộc log và file retention.
19. **VACUUM có thể ảnh hưởng gì?** Xóa file không còn tham chiếu, làm mất khả năng đọc lịch sử cũ.
20. **MERGE có tự chống mọi duplicate business key không?** Không; cần dedup/idempotency.
21. **Auto Loader sử dụng format gì?** cloudFiles.
22. **SchemaLocation dùng để làm gì?** Quản lý/tracking schema của Auto Loader.
23. **Checkpoint cần lưu ở đâu?** Đường dẫn bền vững có quyền, riêng cho query.
24. **Xóa checkpoint có nguy cơ gì?** Replay dữ liệu, duplicate output hoặc sai state.
25. **availableNow khác continuous stream thế nào?** Xử lý nguồn sẵn có rồi kết thúc theo trigger.
26. **Event time khác processing time thế nào?** Thời gian xảy ra sự kiện và lúc pipeline xử lý.
27. **Watermark có tác dụng gì?** Giới hạn late-data/state theo semantics streaming operator.
28. **Exactly-once có tự áp cho HTTP sink tự viết không?** Không.
29. **Broadcast join có lợi khi nào?** Dimension nhỏ, có đủ RAM và tránh shuffle lớn.
30. **AQE là gì?** Spark điều chỉnh một số kế hoạch truy vấn dựa vào thống kê runtime.
31. **Cache có luôn nhanh hơn không?** Không; có thể gây memory pressure/overhead.
32. **Small files tác động gì?** Tăng metadata/tasks và có thể làm chậm truy vấn.
33. **DBU là gì?** Đơn vị sử dụng Databricks trong các mô hình định giá thích hợp.
34. **Chọn jobs compute hay interactive cho ETL hằng đêm?** Thường cân nhắc jobs compute.
35. **Unity Catalog SELECT có đủ nếu Storage permission/network sai không?** Không.
36. **Azure RBAC có thay table-level Unity Catalog grants không?** Không.
37. **Tại sao tách BI Gold khỏi Bronze PII?** Least privilege và governance.
38. **Job Success có chứng minh dữ liệu đúng không?** Không; phải test quality/freshness/reconciliation.
39. **Khi nào Databricks không cần thiết?** Dữ liệu nhỏ hoặc OLTP API đơn giản đã có engine thích hợp.
40. **Điều gì khiến pipeline đáng tin cậy?** Data contracts, idempotency, checkpoint, governance, quality tests, monitoring, recovery và cost control.

## 27. Tài liệu tham khảo

Các liên kết chính thức để kiểm tra tính năng, khả năng hỗ trợ của Runtime và hướng dẫn triển khai:

- [Azure Databricks documentation](https://learn.microsoft.com/azure/databricks/) — workspace, compute, notebooks, Jobs, SQL và governance.
- [What is Azure Databricks?](https://learn.microsoft.com/azure/databricks/introduction/) — khái niệm và các workload.
- [Apache Spark programming guide](https://spark.apache.org/docs/latest/) — Spark SQL/DataFrames, Structured Streaming, tuning.
- [PySpark API reference](https://spark.apache.org/docs/latest/api/python/) — cú pháp DataFrame functions, Window và SparkSession.
- [Databricks compute documentation](https://learn.microsoft.com/azure/databricks/compute/) — loại compute, runtime, policies và lifecycle.
- [Databricks Workflows/Jobs](https://learn.microsoft.com/azure/databricks/jobs/) — orchestration và job monitoring.
- [Databricks SQL](https://learn.microsoft.com/azure/databricks/sql/) — warehouses và SQL analytics.
- [Databricks Delta Lake](https://learn.microsoft.com/azure/databricks/delta/) — transactions, DML, history, VACUUM và optimization.
- [Medallion lakehouse architecture](https://learn.microsoft.com/azure/databricks/lakehouse/medallion) — Bronze/Silver/Gold.
- [Auto Loader](https://learn.microsoft.com/azure/databricks/ingestion/cloud-object-storage/auto-loader/) — cloudFiles, schemaLocation và incremental ingestion.
- [Structured Streaming](https://learn.microsoft.com/azure/databricks/structured-streaming/) — watermark, triggers, checkpoints, performance.
- [Unity Catalog](https://learn.microsoft.com/azure/databricks/data-governance/unity-catalog/) — data governance, privileges, external locations.
- [Unity Catalog volumes](https://learn.microsoft.com/azure/databricks/volumes/) — quản lý file resources và đường dẫn Volumes.
- [Azure Data Lake Storage Gen2 overview](https://learn.microsoft.com/azure/storage/blobs/data-lake-storage-introduction) — storage, hierarchical namespace, data lake design.
- [Azure Databricks networking](https://learn.microsoft.com/azure/databricks/security/network/) — networking và bảo mật kết nối.
- [Azure Databricks monitoring](https://learn.microsoft.com/azure/databricks/admin/account-settings/usage/) — usage và quản trị tài khoản; xem thêm job/Spark UI diagnostics.
- [Azure Databricks pricing](https://azure.microsoft.com/pricing/details/databricks/) — pricing model và cost planning.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — budgets, tags và phân tích chi phí.

**Kết luận:** Apache Spark cung cấp engine tính toán phân tán qua driver, executors, DAG và DataFrames. Azure Databricks xây dựng môi trường phát triển, xử lý và vận hành lakehouse trên nền Spark, Delta Lake, ADLS Gen2, Unity Catalog và Jobs/Workflows. Để triển khai đúng, cần thiết kế **Bronze/Silver/Gold rõ ràng, source keys và data quality rules, incremental ingestion/checkpoints, phân quyền dữ liệu, tối ưu shuffle và storage layout, cùng monitoring/chi phí và runbook phục hồi**. Một pipeline đáng tin không chỉ kết thúc bằng trạng thái Success mà còn phải tạo ra số liệu có thể đối soát, có lineage, bảo mật đúng và chạy lại an toàn khi có lỗi.

