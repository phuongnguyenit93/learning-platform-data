# Microsoft Fabric trong hệ sinh thái dữ liệu Azure

Một doanh nghiệp bán lẻ đang sử dụng Azure SQL Database để lưu đơn hàng, Azure Blob Storage để lưu tệp, Azure Event Hubs để thu thập sự kiện truy cập và Power BI để lập báo cáo. Nhóm dữ liệu muốn hợp nhất các nguồn này, làm sạch, phân tích và trình bày số liệu mà không phải tự kết nối quá nhiều dịch vụ bằng những đoạn mã tích hợp riêng. **Microsoft Fabric** là một hướng tiếp cận quan trọng cho bài toán đó: cung cấp các trải nghiệm data engineering, data integration, data warehousing, real-time analytics, data science và business intelligence trên một nền tảng phân tích dạng **Software as a Service (SaaS)** có lớp lưu trữ thống nhất **OneLake**.

Trong hệ sinh thái Microsoft Azure, Fabric **không phải tên mới của Azure Storage, Azure SQL Database hoặc Azure Databricks**, cũng không tự động thay thế mọi thành phần đó. Fabric có thể **đọc, kết nối, sao chép, đồng bộ hoặc phân tích** dữ liệu từ nhiều dịch vụ Azure tùy tính năng, quyền và mô hình kết nối. Người kiến trúc sư cần biết **chỗ nào giữ dữ liệu nguồn, chỗ nào xử lý biến đổi, chỗ nào phục vụ truy vấn/báo cáo và chỗ nào kiểm soát chi phí/bảo mật**.

Bài học thuộc chương **Nền tảng dữ liệu và phân tích** trong mô-đun **CLOUD_PROVIDERS_AZURE**. Mô-đun khảo sát Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu; từ đó triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng. Bài này kết nối những khối kiến thức đó thành một pipeline dữ liệu có khả năng sử dụng Microsoft Fabric.

> **Phạm vi và lưu ý:** Microsoft Fabric phát triển nhanh; tên workload, loại item, tính năng liên kết OneLake, security, network integration, billing và licensing có thể khác theo tenant, region, capacity và thời điểm. Các ví dụ là kiến trúc/lab minh họa; không có lệnh nào trong tài liệu tự triển khai tài nguyên. Khi áp dụng production phải kiểm tra tài liệu chính thức cho đúng tenant và SKU.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Fabric là nền tảng **SaaS phân tích dữ liệu** và xác định quan hệ với dịch vụ Azure.
2. Phân biệt **tenant, Fabric capacity, workspace và Fabric item**.
3. Trình bày **OneLake**, **Lakehouse**, định dạng **Delta Lake**, **Warehouse**, **SQL analytics endpoint**, **semantic model** và **Power BI report**.
4. Phân biệt **Data Factory pipeline**, **Dataflow Gen2**, **Notebook/Spark**, **Mirroring**, **OneLake shortcut** và **Eventstream/Eventhouse**.
5. Thiết kế pipeline **Bronze → Silver → Gold**, kết nối Azure SQL, ADLS/Blob và Event Hubs.
6. Đánh giá khi nào chọn Fabric thay vì hoặc phối hợp với **Azure Data Factory, Azure Synapse Analytics, Azure Databricks, Azure Data Explorer**.
7. Hiểu các lớp identity, workspace/item permissions, dữ liệu nhạy cảm và network connectivity.
8. Đánh giá **Fabric capacity, Compute Units (CU), OneLake storage, throttling và Power BI licensing** trước khi vận hành.
9. Viết ví dụ PySpark, SQL và KQL để minh họa luồng phân tích.
10. Xây dựng checklist vận hành, giám sát, thử nghiệm và tối ưu chi phí production.

## 1. Bối cảnh: tại sao doanh nghiệp cần nền tảng phân tích thống nhất?

Một kiến trúc dữ liệu truyền thống thường có nhiều công cụ:

~~~text
                         Nguồn dữ liệu

Azure SQL       Cosmos DB       ADLS/Blob      Event Hubs
   |                |               |              |
   +----------------+---------------+--------------+
                            |
                            v
                   Ingestion / ETL / ELT
                            |
                            v
                      Data lake / DWH
                            |
                            v
                     Data engineering
                            |
                            v
                   Semantic model / BI
                            |
                            v
                       Người dùng
~~~

Khi mỗi bước chạy trong một sản phẩm riêng, nhóm vận hành phải quản lý:

- Kết nối, service principals và secrets của nhiều công cụ.
- Dữ liệu bị copy lặp lại giữa lake, warehouse và BI.
- Chuẩn schema, chất lượng dữ liệu và lineage.
- Lịch chạy batch, luồng realtime, retry và khôi phục sau lỗi.
- Chi phí compute, storage, egress và license phân tán.
- Quyền đọc của nhà phân tích, kỹ sư dữ liệu và người xem báo cáo.

Fabric nhằm giảm độ phân mảnh này bằng **trải nghiệm quản trị và cộng tác chung**, **OneLake** và các workload tích hợp. Tuy nhiên “thống nhất” **không có nghĩa không cần kiến trúc dữ liệu, phân quyền hoặc chuẩn hóa dữ liệu**.

## 2. Microsoft Fabric là gì?

Microsoft Fabric là một **nền tảng SaaS phân tích dữ liệu** cung cấp các trải nghiệm tích hợp cho:

- **Data ingestion/orchestration:** Pipelines, Dataflow Gen2, connectors.
- **Data engineering:** Lakehouse, Notebooks, Spark.
- **Data warehousing:** Fabric Warehouse và SQL.
- **Real-time intelligence:** Eventstream, Eventhouse và KQL theo tính năng.
- **Data science:** môi trường làm việc với notebook, thí nghiệm/mô hình ML theo khả năng.
- **Business intelligence:** Power BI semantic models, reports, dashboards.
- **Data governance/discovery:** catalog, lineage, sensitivity labeling và những khả năng quản trị phù hợp với Microsoft Purview/tenant policy.

### Fabric khác một máy chủ Azure thế nào?

Người dùng thường làm việc với **workspace** và **items**, không tự tạo VM để cài SQL, Spark, Airflow hay Redis. Compute của nhiều trải nghiệm được cung cấp thông qua **Fabric capacity** hoặc mô hình license/trial tương ứng.

~~~text
Microsoft Entra tenant
        |
        v
Microsoft Fabric tenant configuration
        |
        +--> Fabric capacity (compute budget)
        |         |
        |         +--> Workspace: Analytics
        |         |       +--> Lakehouse
        |         |       +--> Notebook
        |         |       +--> Warehouse
        |         |       +--> Semantic model/Report
        |         |
        |         +--> Workspace: Realtime
        |                 +--> Eventstream
        |                 +--> Eventhouse
        |
        +--> OneLake (logical unified data lake)
~~~

Sơ đồ biểu diễn quan hệ quản trị ở mức khái niệm. **OneLake không phải một VM/disk nằm bên trong capacity**, và storage/capacity có cơ chế quản lý, billing riêng.

## 3. Fabric nằm trong hệ sinh thái Azure như thế nào?

| Nhu cầu | Dịch vụ Azure thường gặp | Fabric bổ trợ như thế nào? |
|---|---|---|
| Transactional database | Azure SQL Database, Azure Cosmos DB | Đọc, sao chép/đồng bộ dữ liệu để phân tích mà không biến lakehouse thành nơi thực hiện toàn bộ OLTP |
| Object/data lake storage | Azure Blob Storage, ADLS Gen2 | Ingest hoặc truy cập qua **OneLake shortcuts** khi khả năng/nguồn được hỗ trợ |
| Event streaming | Azure Event Hubs, IoT Hub | Tiếp nhận và phân tích luồng qua những tính năng real-time ingestion |
| Data integration | Azure Data Factory | Fabric Data Factory pipelines/Dataflow Gen2, tùy yêu cầu orchestration |
| Big data processing | Azure Databricks, Azure Synapse Spark | Fabric Spark/Notebooks, Delta processing |
| SQL analytics | Azure Synapse dedicated/serverless SQL, Azure SQL | Fabric Warehouse và Lakehouse SQL analytics endpoint |
| Real-time analytics | Azure Data Explorer, Azure Stream Analytics | Fabric Eventhouse/KQL/Eventstreams |
| Reporting | Power BI | Power BI là một trải nghiệm quan trọng trong Fabric |
| Governance | Microsoft Purview, Entra ID | Tích hợp discovery/lineage/labels và identity theo chính sách |

**Không phải mọi ô trên tương đương tính năng.** Chẳng hạn Fabric Warehouse có mô hình T-SQL/transaction và giới hạn khác Azure SQL Database; Eventhouse không thay Event Hubs về retention/consumer offsets; Spark Fabric không có mọi option quản trị của Azure Databricks.

### Fabric có phải Azure resource group không?

Fabric **là dịch vụ SaaS**, dùng tenant/workspaces/items theo mô hình Fabric. Một **Fabric capacity F SKU** có thể được mua/quản lý dưới Azure subscription và resource group theo cơ chế được hỗ trợ, trong khi **workspaces và items** không được quản lý giống từng Azure VM/VNet resource nằm dưới resource group. Đây là khác biệt quản trị quan trọng.

## 4. Những khái niệm quản trị: tenant, capacity, workspace, item

| Thành phần | Ý nghĩa |
|---|---|
| **Microsoft Entra tenant** | Phạm vi danh tính, người dùng, groups và chính sách tổ chức |
| **Fabric tenant settings** | Quy tắc cho phép/từ chối tính năng, chia sẻ, tạo items, data movement... |
| **Fabric capacity** | Ngân sách compute cho các workload được gán theo mô hình cấp phép |
| **Workspace** | Không gian cộng tác, quản lý ownership, items và quyền |
| **Item** | Đơn vị như Lakehouse, Warehouse, Pipeline, Notebook, Eventhouse, Report |
| **OneLake** | Lớp data lake logic thống nhất cho dữ liệu trong Fabric và những truy cập được hỗ trợ |
| **Connection/credential** | Cấu hình cách Fabric truy cập external sources |
| **Deployment pipeline/Git** | Cách đưa nội dung Fabric qua các môi trường theo tính năng |

### Một workspace không nhất thiết dành cho một tenant khách hàng

**Workspace** trong Fabric là đơn vị tổ chức cho nhóm làm việc và quản trị; không tự đảm bảo cách ly dữ liệu SaaS multi-tenant ở tầng application. Nếu nhiều khách hàng cùng truy vấn semantic model/warehouse, cần thiết kế row/column/object security và kiểm thử phân quyền end-to-end.

### Phân quyền capacity và workspace

Quản trị viên capacity không nhất thiết là owner của mọi nguồn dữ liệu; người có quyền chỉnh workspace cũng không tự có quyền mở mọi Azure SQL source. Quyền truy cập **data plane ở nguồn** và **quyền thao tác item trong Fabric** phải được cấp đúng phạm vi.

## 5. OneLake: một lớp data lake logic thống nhất

**OneLake** là data lake logic chung cho Fabric, dựa trên công nghệ lưu trữ tương thích hệ sinh thái Azure Data Lake Storage và định dạng mở. Nó giúp nhiều workload trong Fabric truy cập dữ liệu đã được quản trị và tổ chức trong một môi trường thống nhất.

~~~text
                        OneLake
                 +---------------------+
                 | Workspace A         |
                 |  Lakehouse Sales    |
                 |   Files             |
                 |   Tables (Delta)    |
                 |                     |
                 | Workspace B         |
                 |  Lakehouse Metrics  |
                 |   Tables (Delta)    |
                 +---------------------+
                          |
          +---------------+----------------+
          |               |                |
          v               v                v
       Spark          SQL analytics      Power BI
       notebooks      endpoint           semantic model
~~~

### OneLake không có nghĩa copy mọi dữ liệu vào một thư mục

Mỗi workspace/lakehouse có tổ chức tài nguyên và đường dẫn riêng. MộtLake shortcuts có thể giúp **tham chiếu** dữ liệu từ vị trí khác mà không luôn copy vật lý, nhưng việc truy cập/phân quyền/hiệu năng phụ thuộc loại shortcut và nguồn.

### Dữ liệu trên OneLake có định dạng gì?

**Lakehouse tables** thường sử dụng **Delta Lake** (dữ liệu Parquet kết hợp transaction log). Tệp nguồn như CSV, JSON, Parquet có thể được đặt trong **Files**, sau đó Spark hoặc công cụ khác làm sạch và đưa vào **Tables**.

**OneLake không có nghĩa mọi file tự động trở thành bảng SQL có schema.** Dữ liệu thô cần được quản lý, chuẩn hóa và đăng ký phù hợp trước khi phục vụ SQL/BI.

## 6. Files, Tables và Delta Lake

Một Lakehouse có thể có cấu trúc khái niệm:

~~~text
Lakehouse: sales_lh
    |
    +-- Files/
    |    +-- landing/orders_2026_11_20.csv
    |    +-- raw/events/
    |
    +-- Tables/
         +-- bronze_orders/
         +-- silver_orders/
         +-- gold_daily_sales/
~~~

### Vì sao chọn Delta Lake?

- Hỗ trợ table format có metadata và transaction log.
- Phù hợp xử lý ETL với Spark và sử dụng lại cho SQL/BI theo mức hỗ trợ.
- Cho phép tổ chức dữ liệu dạng bảng để tiếp tục tối ưu đọc/ghi.
- Giảm sự lệ thuộc vào file CSV nguyên bản trong tầng phân tích.

Nhưng Delta không có nghĩa mọi engine đều hỗ trợ mọi mutation/transaction semantics như nhau. Cần kiểm tra giới hạn **Fabric Spark, Warehouse và Lakehouse SQL analytics endpoint** trước khi viết pipeline.

### Raw files có vai trò gì?

Giữ nguyên nguồn thô giúp:

1. Đối chiếu khi dữ liệu xử lý sai.
2. Chạy lại transformation với logic mới.
3. Tách lỗi ingest khỏi lỗi xử lý.
4. Có chứng cứ audit khi retention và quyền được thiết kế hợp lý.

Raw layer cần kiểm soát PII, retention, encryption và access; không để nhà phân tích mặc nhiên có toàn quyền truy cập dữ liệu chưa làm sạch.

## 7. Lakehouse và Warehouse khác nhau thế nào?

| Câu hỏi | Fabric Lakehouse | Fabric Warehouse |
|---|---|---|
| Định hướng | Kết hợp data lake và analytics trên dữ liệu dạng file/bảng Delta | Phân tích quan hệ với trải nghiệm SQL warehouse |
| Người dùng chính | Data engineers, Spark developers, analysts | SQL developers, BI/analytics teams |
| Tạo/chuyển dữ liệu | Spark/Notebook, pipeline và các cơ chế ingest | T-SQL và các cơ chế ingest/ETL được hỗ trợ |
| Truy vấn SQL | Qua **Lakehouse SQL analytics endpoint** (chủ yếu phục vụ đọc) | **Warehouse SQL endpoint** có khả năng ghi/biến đổi được hỗ trợ |
| Dữ liệu thô/files | Có khu vực Files | Không phải công cụ duy nhất quản lý raw lake files |
| Power BI | Có thể xây semantic model trên dữ liệu lakehouse | Có thể xây semantic model trên Warehouse |
| Khi dùng | Medallion, ML/Spark, nhiều định dạng file | Mô hình star schema, SQL analytics, quản trị bảng quan hệ |

### Điểm quan trọng: Lakehouse SQL analytics endpoint

**Lakehouse SQL analytics endpoint** chủ yếu dành cho truy vấn SQL trên các bảng Delta được bộc lộ; **không nhầm** với Warehouse cho DDL/DML tùy ý. Để ghi/chỉnh bảng Lakehouse, dùng **Spark hoặc cơ chế ghi được hỗ trợ**, không giả định lệnh UPDATE của Warehouse sẽ chạy qua endpoint Lakehouse.

### Warehouse có phải Azure SQL Database không?

**Không.** Fabric Warehouse là dịch vụ analytics/warehouse, trong khi Azure SQL Database chủ yếu hướng tới transactional workloads theo các service tiers. Dù cùng có T-SQL ở một số bề mặt, concurrency, data modeling, supported features và operational guarantees khác nhau.

## 8. SQL analytics endpoint và ví dụ truy vấn

Một người phân tích có thể truy vấn bảng đã được chuẩn hóa:

~~~sql
-- Ví dụ T-SQL chỉ đọc, giả định bảng đã tồn tại.
SELECT TOP (20)
    order_date,
    customer_segment,
    SUM(net_amount) AS total_net_sales
FROM dbo.gold_order_sales
GROUP BY order_date, customer_segment
ORDER BY order_date DESC, total_net_sales DESC;
~~~

**Lưu ý:** Tên bảng/cột hoàn toàn giả định. Với Lakehouse, endpoint bộc lộ các bảng và schema theo quy tắc đồng bộ metadata của dịch vụ; cấu trúc không nhất thiết là dbo của mọi lakehouse. Với Warehouse, cần xác nhận tên schema thực tế.

### SQL endpoint không tự giải quyết bảo mật

Người dùng cần đúng quyền Fabric item/SQL hoặc OneLake data access tùy đường truy cập. **Thấy bảng trong SQL explorer không đồng nghĩa có quyền đọc mọi rows**. Phải kiểm tra effective access và khi cần thiết dùng row/column/object-level controls được hỗ trợ trên đúng engine.

## 9. Data Factory trong Fabric

**Data Factory** là trải nghiệm tích hợp dữ liệu trong Fabric. Hai thành phần rất hay gặp:

- **Data pipeline:** điều phối activities, dependencies, lịch chạy, sao chép dữ liệu và gọi những xử lý khác.
- **Dataflow Gen2:** biến đổi dữ liệu theo hướng low-code với Power Query và các connector được hỗ trợ.

~~~text
Azure SQL / ADLS / SaaS API
           |
           v
      Fabric Pipeline
         |        |
         |        +--> Copy data
         |
         +--> Dataflow Gen2 transform
         |
         +--> Notebook Spark
         |
         v
     Lakehouse / Warehouse
~~~

### Pipeline không nhất thiết tự chuyển đổi dữ liệu

**Orchestration** quyết định bước nào chạy trước, dependency và retry; **transformation** quyết định dữ liệu được làm sạch/tính toán thế nào. Trong pipeline, hoạt động Copy có thể chuyển dữ liệu; Notebook và Dataflow có thể biến đổi; mỗi activity có giới hạn và cách tính chi phí riêng.

### Data Factory Fabric khác Azure Data Factory?

Hai môi trường có khái niệm pipeline/connectors tương đồng, nhưng **không mặc định có feature parity 1:1**. Integration runtime, network gateways, managed identity, activity types, CI/CD và billing cần được kiểm tra riêng trước khi migrate Azure Data Factory.

## 10. Notebook và Spark trong Fabric

**Fabric Data Engineering** hỗ trợ Notebook/Spark để xử lý dữ liệu lớn, biến đổi file thành Delta tables, tính toán và chuẩn hóa dữ liệu.

Một ví dụ:

~~~text
Raw CSV in OneLake Files
       |
       v
Fabric Notebook (PySpark)
  - parse fields
  - validate schema
  - drop/mark invalid records
  - deduplicate by business key
       |
       v
Delta tables in Lakehouse
       |
       v
Warehouse / Power BI semantic model
~~~

### Spark phù hợp khi nào?

- Xử lý dữ liệu file lớn, semi-structured.
- Batch transformation có nhiều bước.
- Chuẩn hóa schemas/quality checks.
- Cần sử dụng Python/Scala và các thư viện xử lý được hỗ trợ.

### Không dùng Spark cho mọi việc

Một bảng 200 dòng được cập nhật mỗi ngày có thể xử lý hiệu quả hơn bằng SQL/Dataflow Gen2 thay vì khởi chạy Spark session. Chi phí compute, startup latency, lịch chạy và yêu cầu kỹ năng phải được tính vào quyết định.

## 11. Ví dụ PySpark: CSV thành Delta table

Đoạn mã sau **minh họa một notebook gắn vào Lakehouse**. Nếu chạy, nó đọc file có sẵn rồi tạo/ghi bảng; **chỉ thực hiện trên Fabric workspace/lakehouse lab**. Không chạy khi chưa kiểm tra output table và quyền ghi.

Giả sử file:

~~~text
Files/landing/orders.csv

order_id,customer_id,amount
ORD-001,C-001,125000
ORD-002,C-002,75000
ORD-003,C-001,99000
~~~

Notebook:

~~~python
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, DecimalType
)

schema = StructType([
    StructField("order_id", StringType(), False),
    StructField("customer_id", StringType(), True),
    StructField("amount", DecimalType(18, 2), True),
])

df = (
    spark.read
    .option("header", "true")
    .schema(schema)
    .csv("Files/landing/orders.csv")
)

clean = (
    df.filter(F.col("order_id").isNotNull())
      .filter(F.col("amount") >= 0)
      .withColumn("ingested_at", F.current_timestamp())
)

# Chỉ dùng tên bảng lab; append sẽ tạo dữ liệu lặp nếu chạy lại
# mà không có idempotency/deduplication.
clean.write.format("delta").mode("append").saveAsTable(
    "bronze_orders_lab"
)
~~~

### Điểm cần giải thích

1. **Schema được khai báo** để tránh suy đoán kiểu dữ liệu từ vài dòng đầu.
2. **DecimalType** phù hợp hơn float cho một số giá trị tiền, nhưng bài toán tiền thật vẫn cần quy tắc currency/scale và validation.
3. **filter** loại một số bản ghi sai, chưa có quarantine cho dữ liệu lỗi.
4. **append** không idempotent nếu notebook chạy lại; production cần MERGE/deduplication theo key và batch/run ID.
5. Bảng được tạo trong Lakehouse mà notebook đã attach; tên/namespace phải điều chỉnh theo môi trường thực tế.
6. **Spark session/compute có chi phí**, ngay cả khi file nhỏ.

### Những bước phải thêm khi production

- Validation cho trường bắt buộc và thời gian event.
- Bảng quarantine/error records.
- Ingestion watermark/checkpoint theo nguồn.
- Ghi audit row counts và run IDs.
- Partitioning/compaction hoặc tối ưu theo workload.
- Retry có giới hạn và cơ chế kiểm soát ghi trùng.
- Schema evolution có phê duyệt.

## 12. Medallion architecture: Bronze, Silver, Gold

**Medallion** là cách tổ chức dữ liệu theo mức độ chuẩn hóa:

~~~text
Nguồn Azure SQL / Event Hubs / ADLS
                 |
                 v
         Bronze (raw/landing)
         - giữ cấu trúc nguồn
         - metadata ingestion
         - khả năng replay
                 |
                 v
         Silver (clean/validated)
         - chuẩn hóa schema
         - loại trùng, sửa lỗi có kiểm soát
         - chuẩn timezone, currency, business keys
                 |
                 v
         Gold (business-ready)
         - facts/dimensions
         - bảng tổng hợp chỉ số
         - semantic models / reports
~~~

### Bronze

Lưu dữ liệu gốc hoặc bản sao đủ để tái xử lý. Có thể giữ source timestamps, ingestion timestamps, batch identifiers, source file/version. Cần xác định retention và kiểm soát PII, không mở quyền rộng vì “chỉ là raw”.

### Silver

Chuẩn hóa định dạng và logic, xử lý null/duplicate/out-of-order, áp data quality tests. **Không xóa âm thầm mọi bản ghi sai**; quarantine giúp phân tích lỗi nguồn.

### Gold

Tổ chức business-ready data: fact/dimension, metric definitions, aggregates. Một Gold table hoặc semantic model phải có **owner và quy tắc tính metric** rõ ràng, tránh mỗi dashboard định nghĩa doanh thu khác nhau.

### Có bắt buộc ba Lakehouses?

Không. Medallion là **mô hình kiến trúc**, có thể triển khai bằng nhiều schemas, tables, lakehouses/workspaces hoặc một phần trong Warehouse theo giới hạn nền tảng. Tách vật lý tùy quy mô, trách nhiệm dữ liệu và security boundary.

## 13. Shortcut trong OneLake: tham chiếu, không nhất thiết sao chép

**OneLake shortcut** giúp bộc lộ dữ liệu từ vị trí được hỗ trợ vào namespace OneLake, có thể từ workspace/item khác hoặc nguồn ngoài như ADLS Gen2 theo connector/feature hỗ trợ.

~~~text
Azure Data Lake Storage Gen2
   container / curated/orders
              |
              | OneLake shortcut
              v
Fabric Lakehouse
   Files/linked_orders  -- tham chiếu dữ liệu nguồn
              |
              v
Spark / supported engines
~~~

### Lợi ích

- Tránh một số bản sao vật lý không cần thiết.
- Giảm công việc ingest khi dữ liệu đã ở một lake khác.
- Tận dụng tập dữ liệu hiện có từ Azure.
- Cho phép nhiều nhóm dùng chung một nguồn theo mô hình truy cập được hỗ trợ.

### Rủi ro và giới hạn

- Shortcut không tự chuẩn hóa schema, loại trùng hoặc làm sạch dữ liệu.
- Nếu dữ liệu gốc đổi, truy vấn có thể quan sát thay đổi theo semantics nguồn/cache/engine.
- **Credentials và access control** của shortcut, người tạo connection và người truy vấn phải được thiết kế đúng.
- Network access tới external source và tính năng hỗ trợ khác nhau theo connector.
- Không giả định mọi loại external shortcut đều hỗ trợ ghi hoặc mọi engine nhìn thấy shortcut như một Delta table.
- Khả năng tạo cache/copy ngầm trong các tầng công cụ cần được kiểm tra nếu hệ thống có yêu cầu residency nghiêm ngặt.

**Shortcut không phải một bản backup bất biến**. Nếu nguồn bị xóa hoặc access bị thu hồi, dữ liệu được tham chiếu có thể không còn khả dụng.

## 14. Mirroring khác Shortcut thế nào?

**Mirroring** trong Fabric là nhóm tính năng giúp phản ánh/sao chép và cập nhật dữ liệu từ **một số nguồn được hỗ trợ** vào Fabric/OneLake để phục vụ analytics, theo cơ chế của connector/nguồn. Nó khác shortcut:

| Câu hỏi | OneLake shortcut | Fabric Mirroring |
|---|---|---|
| Mục tiêu | Tham chiếu dữ liệu có sẵn từ một vị trí khác | Đưa và giữ một bản phản ánh của nguồn tương thích để phân tích |
| Có copy dữ liệu không? | Thường tránh copy dữ liệu nguồn ban đầu | Có cơ chế đưa/duy trì dữ liệu mirror trong Fabric theo connector |
| Độ mới | Phụ thuộc nguồn và access path | Phụ thuộc replication/sync lag |
| Nguồn | OneLake/ADLS và những loại supported shortcuts | Những databases/sources có mirror connector được hỗ trợ |
| Biến đổi | Không tự ETL | Mirroring không mặc định thay thế clean/semantic transformation |
| Quản trị | Credentials, quyền, lifecycle của shortcut/source | Connection, replication status, lag, source impact |

### Ví dụ Azure SQL

Một doanh nghiệp có Azure SQL Database phục vụ OLTP. Nếu Fabric Mirroring hỗ trợ cấu hình nguồn/tier của họ, có thể sử dụng một cơ chế mirror để phân tích mà không phải tự viết full batch copy thường xuyên.

Tuy nhiên:

- Không phải mọi Azure SQL deployment/bảng/tính năng đều đủ điều kiện.
- Một bản mirror có **replication lag**; không dùng như read-after-write tuyệt đối cho giao dịch.
- Phải đánh giá overhead ở nguồn, quyền, firewall/private access và initial sync.
- Mirroring không loại bỏ nhu cầu backup, PITR và DR của database gốc.

### Khi nào cần Copy/Pipeline thay vì Mirroring?

Khi nguồn không được hỗ trợ, cần điều khiển incremental load theo quy tắc riêng, có transformation phức tạp hoặc cần business validation trước khi đưa vào Gold, có thể chọn Data Factory pipeline/Dataflow/Notebook.

## 15. Power BI và semantic model trong Fabric

Power BI là phần quan trọng của trải nghiệm Fabric: xây **semantic model** và báo cáo cho người dùng nghiệp vụ.

~~~text
Gold tables (Lakehouse/Warehouse)
               |
               v
        Power BI Semantic Model
        - relationships
        - business measures
        - row-level security nếu được thiết kế
               |
               v
        Power BI Report / Dashboard
               |
               v
          Business users
~~~

### Semantic model là gì?

Nó mô tả cách tổ chức tables, relationships, measures và business logic để report creators không phải tự viết lại định nghĩa “doanh thu”, “đơn hủy” hay “khách hàng hoạt động” trong từng dashboard.

Ví dụ:

~~~text
Revenue = SUM(net_sales_amount)
OrderCount = DISTINCTCOUNT(order_id)
AverageOrderValue = Revenue / OrderCount
~~~

**Đây là công thức khái niệm**, không phải DAX hoàn chỉnh cho mọi semantic model. Chỉ tiêu cần quy định thuế/hoàn tiền/đơn hủy và thời gian ghi nhận.

### Chế độ truy cập dữ liệu

Power BI có các chế độ như **Import**, **DirectQuery** và **Direct Lake** trong những cấu hình hỗ trợ. Không nhầm:

- **Import:** dữ liệu được nạp vào semantic model, cần cập nhật theo lịch/điều kiện.
- **DirectQuery:** truy vấn nguồn khi xem/ tương tác, phụ thuộc performance nguồn và giới hạn.
- **Direct Lake:** được thiết kế để tận dụng dữ liệu trên OneLake/Delta với hiệu năng gần mô hình dữ liệu trong Fabric theo điều kiện hỗ trợ.

**Direct Lake không phải lời hứa tự động realtime tuyệt đối**, không tự bỏ quyền RLS, và có giới hạn fallback/hỗ trợ theo model/tier. Khi cần dữ liệu mới phải thiết kế quá trình cập nhật tables/model và đo freshness end-to-end.

## 16. Real-Time Intelligence: Eventstream, Eventhouse và KQL

Fabric có trải nghiệm **Real-Time Intelligence** cho việc thu thập, phân tích và trực quan hóa event/telemetry gần thời gian thực qua các thành phần được hỗ trợ.

~~~text
Ứng dụng / thiết bị
          |
          v
Azure Event Hubs / supported source
          |
          v
Fabric Eventstream
  - ingest/route/transform theo khả năng
          |
          v
Eventhouse / KQL database
          |
          v
KQL queries, dashboards, alerts/Activator
          |
          v
Người vận hành / incident workflow
~~~

### Eventstream

Dùng cho những luồng sự kiện liên tục, cho phép kết nối nguồn/đích và xử lý theo khả năng. **Eventstream không đồng nghĩa Event Hubs**: Event Hubs là dịch vụ broker/ingestion của Azure với partitions/consumer groups/retention riêng; Fabric Eventstream là thành phần trong nền tảng phân tích.

### Eventhouse và KQL Database

Hướng đến truy vấn event/log/time-series khối lượng lớn với **Kusto Query Language (KQL)** và các tính năng lưu/thu/truy vấn phù hợp.

### Ví dụ KQL chỉ đọc

Giả sử một KQL database có bảng **AppEvents** với các cột **EventTime** và **EventType**:

~~~kusto
AppEvents
| where EventTime >= ago(1h)
| summarize EventCount = count()
    by bin(EventTime, 5m), EventType
| order by EventTime asc
~~~

Truy vấn tính số sự kiện theo mỗi 5 phút và loại event. Tên bảng/cột là giả định. Cần đánh giá timezone, event time so với ingestion time, late events và filtering/retention nếu dùng để dựng alert.

## 17. Data Science trong Fabric

Fabric có trải nghiệm cho data scientists để sử dụng dữ liệu từ OneLake/Lakehouse, chạy notebooks và xây dựng mô hình hoặc phân tích.

Một quy trình:

~~~text
Silver data (cleaned, consented)
          |
          v
Feature engineering (Notebook/Spark)
          |
          v
Training / evaluation
          |
          v
Model/experiments theo khả năng hỗ trợ
          |
          v
Batch scoring / reports / downstream API
~~~

### Không đồng nghĩa Azure Machine Learning

Azure Machine Learning có hệ sinh thái phục vụ training/registry/deployment/managed endpoints/ML operations theo khả năng riêng. Fabric Data Science không tự thay thế mọi chức năng của Azure ML. Lựa chọn theo quy trình production, quản trị model, latency online inference, network/security và chi phí.

### Quyền đối với dữ liệu huấn luyện

Data scientist có thể nhìn thấy bảng phân tích nhưng **không được tự suy ra họ có quyền xem PII thô**. Cần dùng dataset đã được phân loại, quản lý consent, masking, lineage và kiểm soát nơi xuất model artifacts.

## 18. Kết nối Fabric với các nguồn Azure

| Nguồn | Cách tích hợp cần đánh giá | Điểm lưu ý |
|---|---|---|
| **Azure SQL Database** | Pipeline, connector, Mirroring nếu hỗ trợ | Network, source load, replication lag, credentials |
| **Azure Cosmos DB** | Connector/Mirroring khi hỗ trợ | API compatibility, partitioning, RU/s và change propagation |
| **ADLS Gen2 / Blob** | Copy/Pipeline hoặc OneLake shortcut | ACL/RBAC, shortcut type, path/format, cost |
| **Azure Event Hubs** | Eventstream/supported connector | Consumer position, streaming lag, throughput |
| **Azure Databricks** | Delta data exchange/OneLake connectors theo khả năng | Compatibility, Unity Catalog/governance, copy vs reference |
| **Azure Functions/Logic Apps** | Pipeline orchestration/API/service integration | Authentication, rate limits, retry/idempotency |
| **Power BI** | Semantic models/reports | Licensing, Direct Lake conditions, RLS |
| **On-premises SQL** | Data gateway/connectors theo hỗ trợ | Private connectivity, gateway capacity, security |

### Kết nối không đồng nghĩa copy dữ liệu

**Shortcut** là đường tham chiếu; **Copy activity** tạo dữ liệu đích; **Mirroring** duy trì bản phản ánh nguồn; **DirectQuery** truy vấn nguồn theo yêu cầu; **Import** nạp dữ liệu vào semantic model. Từng cách có cost, freshness và access-control khác nhau.

## 19. Fabric và Azure Data Factory: chọn công cụ điều phối

**Azure Data Factory (ADF)** là dịch vụ Azure PaaS tích hợp/orchestration riêng, có pipelines, activities và integration runtime. **Fabric Data Factory** đưa những trải nghiệm orchestration/dataflow vào Fabric.

| Điều kiện | Hướng đánh giá |
|---|---|
| Phân tích chủ yếu trong Fabric/OneLake | Fabric pipelines/Dataflow Gen2 |
| Có ADF đang vận hành nhiều kết nối phức tạp | Tiếp tục ADF hoặc migrate có đánh giá, không bắt buộc đổi |
| Kết nối on-prem/private systems | Kiểm tra gateway/network support của từng nền tảng |
| Cần orchestration qua nhiều Azure subscriptions | ADF hoặc Fabric tùy connectors/identity/requirements |
| Muốn tối giản thao tác chuẩn bị dataset cho Power BI | Fabric Dataflow Gen2 có thể phù hợp |
| Cần tái sử dụng IaC/CI/CD hiện tại | So sánh deployment APIs, Git integration và feature parity |

**Không nhập khẩu một ADF pipeline JSON rồi kỳ vọng nó hoạt động hoàn toàn tương tự trong Fabric**. Tên activity, runtime, parameters, triggers, billing và hỗ trợ có thể khác.

## 20. Fabric, Azure Synapse và Azure Databricks

| Tiêu chí | Microsoft Fabric | Azure Synapse Analytics | Azure Databricks |
|---|---|---|---|
| Định hướng | SaaS analytics thống nhất tích hợp Power BI/OneLake | Hệ dịch vụ analytics Azure với Spark/SQL/pipelines theo cấu hình | Nền tảng lakehouse/data engineering/ML do Databricks cung cấp trên Azure |
| Tầng quản trị | Fabric tenant/capacity/workspaces/items | Azure resources/workspaces/pools | Azure workspace/compute và quản trị platform |
| Spark | Fabric Spark notebooks/experiences | Synapse Spark theo pool | Databricks clusters/SQL/ML features |
| SQL | Fabric Warehouse/Lakehouse SQL endpoint | Dedicated/serverless SQL experiences | Databricks SQL/lakehouse tables |
| BI | Power BI tích hợp sâu | Kết nối BI riêng | Kết nối Power BI và công cụ BI khác |
| Data lake | OneLake/shortcuts | ADLS Gen2 và data lake kết hợp | Delta lake trong storage theo kiến trúc |
| Pricing | Fabric capacity + storage/licensing | Mỗi dịch vụ/compute pool theo billing | DBUs + compute/cloud storage theo mô hình |
| Khi chọn | Muốn hợp nhất workloads và cộng tác BI | Đang có Synapse workloads/điều kiện phù hợp | Cần Spark/ML platform và Databricks features chuyên sâu |

### Tránh câu hỏi sai: “Công cụ nào luôn tốt nhất?”

Ví dụ một công ty đã vận hành Databricks tốt, có data governance hoàn chỉnh và bảng Delta trên ADLS, có thể tiếp tục dùng Databricks để xử lý và dùng **Fabric/Power BI** để phục vụ báo cáo theo đường tích hợp phù hợp. Không nhất thiết phải chuyển toàn bộ Spark jobs vào Fabric để có lợi ích từ OneLake hoặc semantic model.

### Tránh nhầm Fabric với việc chỉ đổi tên Power BI

Power BI là một thành phần cốt lõi, nhưng Fabric còn bao gồm ingestion, Spark, Lakehouse, Warehouse và Real-Time Intelligence. Ngược lại, không phải người dùng Power BI đều cần sử dụng toàn bộ Fabric workloads.

## 21. Kiến trúc end-to-end: ứng dụng bán lẻ trên Azure và Fabric

Giả sử một doanh nghiệp có ba nguồn:

- **Azure SQL Database:** đơn hàng, chi tiết đơn, khách hàng.
- **ADLS Gen2:** tệp sản phẩm và lịch sử giao dịch dạng Parquet/CSV.
- **Azure Event Hubs:** hành vi clickstream và telemetry liên tục.

Một kiến trúc đề xuất:

~~~text
        Azure SQL Database          ADLS Gen2             Event Hubs
                 |                     |                      |
                 | Mirroring/Copy      | Shortcut/Copy        | Eventstream
                 v                     v                      v
         +-----------------------------------------------------------+
         |                     Microsoft Fabric                      |
         |                                                           |
         |  OneLake / Lakehouse               Eventhouse             |
         |    Bronze raw data                     |                   |
         |         |                              | KQL/aggregation   |
         |         v                              v                   |
         |    Notebook Spark / Dataflow Gen2   Realtime insights     |
         |         |                              |                   |
         |         v                              |                   |
         |    Silver validated                    |                   |
         |         |                              |                   |
         |         v                              |                   |
         |    Gold facts/dimensions <--------------+                   |
         |         |                                                  |
         |         v                                                  |
         |    Warehouse / Lakehouse SQL endpoint                     |
         |         |                                                  |
         |         v                                                  |
         |    Semantic model -> Power BI report                       |
         +-----------------------------------------------------------+
                                |
                                v
                   Data consumers / business users
~~~

### Các ranh giới kiến trúc

1. **Azure SQL** tiếp tục là nguồn OLTP; không bắt website phải ghi đơn hàng trực tiếp vào Warehouse analytics.
2. **Event Hubs** chịu trách nhiệm nhận sự kiện; Fabric Eventstream/Eventhouse phục vụ tiêu thụ và phân tích theo tích hợp được hỗ trợ.
3. **ADLS/OneLake** giữ dữ liệu file và các bảng Delta; shortcut/copy theo quyền và nhu cầu.
4. **Silver/Gold** tạo ngữ nghĩa dữ liệu đáng tin cậy, không chỉ đổi tên bảng.
5. **Semantic model** chuẩn hóa metrics, quan hệ và quyền người xem.
6. **Monitoring và governance** phải chạy xuyên các lớp, không dừng ở “pipeline thành công”.

## 22. Tại sao cần phân biệt OLTP và OLAP?

**OLTP (Online Transaction Processing)** phục vụ nhiều giao dịch ngắn như tạo đơn, trừ kho, cập nhật trạng thái. **OLAP (Online Analytical Processing)** phục vụ tính tổng hợp dài hạn và truy vấn nhiều chiều.

| Tiêu chí | Azure SQL Database cho OLTP | Fabric Lakehouse/Warehouse cho OLAP |
|---|---|---|
| Mục tiêu | Giao dịch nghiệp vụ độ trễ thấp | Phân tích tập dữ liệu lớn và tổng hợp |
| Kiểu truy vấn | Point lookup, writes/updates giao dịch | Scan/aggregate/join nhiều bảng |
| Tải | Nhiều giao dịch ngắn đồng thời | Batch/analytics/BI concurrency |
| Tính nhất quán | Transactional semantics của DB | Dựa trên engine/table và pipeline freshness |
| Nguồn sự thật | Thường là hệ thống ghi nghiệp vụ | Bản dữ liệu phục vụ phân tích |
| Sử dụng | REST API, checkout, inventory | Dashboard, nghiên cứu hành vi, báo cáo |

**Fabric Warehouse không phải bản thay thế trực tiếp cho backend thanh toán cần transaction nhanh.** Khi báo cáo làm chậm Azure SQL, một hướng là đưa dữ liệu sang Fabric phân tích thay vì cho hàng trăm report queries quét bảng giao dịch.

### Vấn đề dữ liệu mới nhất

Một báo cáo doanh thu chạy qua dữ liệu mirror/batch có thể **trễ** so với đơn hàng vừa commit. Người dùng phải biết:

- Khoảng trễ có thể chấp nhận (freshness SLO).
- Thời điểm dữ liệu nguồn được ghi và đích được cập nhật.
- Những bảng nào được cập nhật realtime, near-real-time hay batch.
- Khi pipeline lỗi, có hiện cảnh báo “dữ liệu đã cũ” hay không.

## 23. Ingest full load, incremental load và CDC

Nạp dữ liệu lần đầu thường khác cập nhật hàng ngày:

| Kiểu ingest | Mục tiêu | Rủi ro |
|---|---|---|
| **Full load** | Lấy toàn bộ dữ liệu nguồn | Tốn thời gian/chi phí, dễ quá tải source |
| **Incremental timestamp/watermark** | Chỉ đọc record mới hoặc thay đổi theo cột thời gian | Thiếu bản ghi đến muộn hoặc timestamp không đáng tin |
| **Change Data Capture (CDC)** | Theo dõi thay đổi theo log/connector được hỗ trợ | Lỗi permission, retention, ordering, schema changes |
| **Mirroring** | Duy trì bản sao gần nguồn theo connector | Lag, source compatibility, initial sync và quyền |
| **Eventstream** | Tiêu thụ events liên tục | Event duplication, late events, streaming pressure |

### Watermark không phải lúc nào cũng đủ

~~~text
Last watermark = 10:00
Record A được ghi source lúc 10:01 -> ingest thành công
Record B đến muộn lúc 10:05 nhưng timestamp nghiệp vụ 09:59

Nếu chỉ đọc timestamp > 10:00:
  Record B có thể bị bỏ qua.
~~~

Giải pháp có thể gồm overlap window, deduplication theo business key, change tracking/CDC hoặc cơ chế log-based ingestion được hỗ trợ.

### Full load và CDC phải nối với nhau chính xác

Nếu vừa thực hiện full copy, vừa bật stream thay đổi mà không xác định cutover point/watermark, có thể trùng hoặc thiếu sự kiện. Đây là vấn đề **data correctness**, không phải lỗi mà một Fabric capacity lớn hơn có thể tự sửa.

## 24. Tổ chức ingestion pipeline có thể chạy lại

Một pipeline tốt cần **idempotent/restartable**:

~~~text
Run ID: orders-2026-11-20-08
      |
      v
Read source data for window
      |
      v
Validate source schema/row counts
      |
      v
Write staging or Bronze partition
      |
      v
Transform/Deduplicate into Silver
      |
      v
Publish Gold data
      |
      v
Update run watermark/status after commit
~~~

### Nếu bước giữa thất bại

Giả sử Copy đã ghi 100.000 rows vào Bronze nhưng Notebook chuyển Silver thất bại. Retry từ đầu với **append không kiểm soát** sẽ có nguy cơ nhân đôi Bronze. Hãy chọn:

- Dùng **run_id** làm khóa xử lý.
- Deduplication theo source operation ID.
- Upsert/MERGE vào Delta table khi engine hỗ trợ đúng.
- Ghi staging rồi publish theo điều kiện xác minh.
- Chỉ tăng watermark khi output thực sự commit bền vững.

### Có cần exactly-once không?

Không nên hứa exactly-once toàn bộ hệ thống chỉ vì một activity có retry. Từ Azure SQL qua Copy/Mirror, Spark rồi semantic model có nhiều ranh giới commit khác nhau. **At-least-once ingest + idempotent transforms** thường là một chiến lược thực tiễn, cần chứng minh bằng test.

## 25. Data quality là một phần của pipeline

Các câu hỏi quan trọng:

- Order ID có null hoặc trùng không?
- Số tiền có âm do hoàn tiền hay do dữ liệu lỗi?
- Currency/timezone có được chuẩn hóa không?
- Khách hàng bị xóa theo yêu cầu privacy có còn ở raw files không?
- Có bản ghi phát sinh muộn sau lần tổng hợp Gold không?
- Số đơn đã xử lý có khớp tổng nguồn không?

### Ví dụ quy tắc kiểm tra

| Rule | Loại | Hành động |
|---|---|---|
| order_id không null | Completeness | Quarantine record thiếu khóa |
| amount hợp lệ theo business context | Validity | Ghi lỗi; không tự bỏ hoàn tiền âm |
| order_id + source_event_version duy nhất | Uniqueness | Deduplicate theo hợp đồng |
| currency là mã được hỗ trợ | Validity | Dùng reference lookup |
| order_date không trong tương lai bất hợp lý | Timeliness | Quarantine/đánh dấu cần xem xét |
| Gold total reconcile với nguồn | Accuracy | Chặn publish nếu vượt ngưỡng |

**Dataflow Gen2/Spark không làm dữ liệu tự động sạch chỉ vì pipeline hoàn thành.** Mỗi bước transformation cần quality assertions và metrics.

## 26. Timezone, currency và event time

Trong ứng dụng toàn cầu, thời gian đơn hàng thường được lưu UTC và hiển thị theo khu vực người dùng. Nếu bảng Gold được group theo local date mà không biết timezone, doanh thu ngày có thể lệch.

~~~text
Source event:
  2026-11-20T23:45:00Z

Business timezone UTC+7:
  2026-11-21 06:45

UTC date = 20/11
Local business date = 21/11
~~~

### Những định nghĩa cần thống nhất

- **Event time:** khi sự kiện xảy ra ở nguồn.
- **Ingestion time:** khi pipeline nhận được dữ liệu.
- **Processing time:** khi transform thực thi.
- **Business date:** ngày theo timezone/quy định kế toán của tổ chức.

Chọn time field đúng trong fact tables, semantic measures và dashboards. Với streaming, late events phải được xử lý riêng; đừng coi thứ tự ingest là thứ tự nghiệp vụ.

## 27. Bảo mật: Microsoft Entra ID và quyền truy cập Fabric

Một kiến trúc Fabric liên quan nhiều lớp:

~~~text
Microsoft Entra ID
       |
       v
Fabric tenant / workspace roles
       |
       +-- Item permissions
       |
       +-- OneLake data permissions / roles theo khả năng
       |
       +-- Warehouse / SQL security
       |
       +-- Power BI semantic model permissions/RLS
       |
       v
External Azure sources
       |
       +-- Azure SQL identity/SQL permissions
       +-- ADLS Gen2 RBAC/ACL
       +-- Event Hubs consumer rights
~~~

### Mỗi lớp trả lời một câu hỏi khác nhau

| Lớp | Ví dụ câu hỏi |
|---|---|
| **Tenant administration** | Ai được phép tạo/chia sẻ items hoặc dùng tính năng external sharing? |
| **Workspace role** | Ai có thể tạo/sửa/xem items trong workspace? |
| **Item permissions** | Ai có quyền đọc/chạy/chỉnh đúng Lakehouse, Warehouse, Pipeline? |
| **OneLake data access** | Ai được đọc dữ liệu trong một phạm vi OneLake phù hợp? |
| **SQL security** | Ai được SELECT/UPDATE bảng/cột/row trong endpoint tương ứng? |
| **Semantic model RLS/OLS** | Người xem báo cáo chỉ được thấy subset dữ liệu nào? |
| **Azure source authorization** | Fabric connection có thể đọc database/container nào? |

### Không coi mọi vai trò Fabric giống nhau

Những vai trò như **Admin, Member, Contributor, Viewer** trong workspace có quyền khác nhau. Quyền truy cập dữ liệu thực tế còn phụ thuộc item, SQL/OneLake security và các cơ chế share/build. **Viewer trong một report không mặc nhiên có quyền truy cập raw PII**; điều này phải được xác minh và giới hạn khi thiết kế.

### Nguyên tắc

1. Dùng Entra groups thay phân quyền cá nhân khi có thể.
2. Tách quyền dev/test/prod.
3. Phân loại PII trước khi cho phép tạo shortcut hoặc export.
4. Hạn chế người có quyền đổi connection credentials.
5. Không cấp rộng workspace Admin để sửa lỗi permission.
6. Kiểm thử truy cập bằng **người dùng có quyền thấp thực sự**.

## 28. OneLake và ranh giới tin cậy của Shortcut

Một shortcut tới ADLS không tự làm dữ liệu nguồn công khai. Cần xem:

- Ai được tạo shortcut?
- Connection dùng danh tính/credential nào?
- Ai có quyền đọc shortcut như một Fabric item?
- Dữ liệu external source có ACL/RBAC như thế nào?
- Tài khoản kết nối là service principal, workspace identity hay credentials người dùng?
- Khi người tạo shortcut rời công ty, connection có còn hợp lệ?
- Có thể truy cập dữ liệu qua đường OneLake khác bỏ qua các kiểm soát SQL/Power BI không?

### Ví dụ rủi ro

~~~text
Power BI Report đã có RLS tốt
       |
       v
Người dùng chỉ xem dữ liệu tenant-A

Nhưng cùng người đó có quyền đọc trực tiếp Lakehouse raw Files
       |
       v
Có thể thấy nhiều tenant nếu raw access không được hạn chế
~~~

**RLS ở semantic model không thay thế permissions ở OneLake/Files/SQL endpoint.** Khi dữ liệu nhạy cảm, mọi đường truy cập phải được đánh giá riêng.

## 29. Microsoft Purview, lineage và data governance

Governance giúp trả lời:

- Bảng Gold được tạo từ nguồn nào?
- Ai sở hữu định nghĩa doanh thu?
- Báo cáo nào phụ thuộc một cột sắp bị đổi tên?
- Dữ liệu nào chứa PII?
- Ai đã truy cập, chia sẻ hoặc xuất dữ liệu?
- Dữ liệu có được giữ đúng retention policy không?

**Fabric** có các khả năng lineage/discovery và tích hợp với hệ sinh thái **Microsoft Purview**, tùy license, cấu hình và giới hạn. Không giả định mọi bảng, shortcut, pipeline hoặc external source có **lineage hoàn chỉnh tự động**. Cần kiểm thử mức độ metadata được thu và bổ sung documentation ở nơi còn thiếu.

### Một bộ metadata tối thiểu

| Trường | Ví dụ |
|---|---|
| Dataset owner | Data Platform Team |
| Business owner | Finance |
| Source | Azure SQL orders |
| Update cadence | Every 15 minutes |
| Freshness SLO | Data age dưới 30 phút |
| Sensitivity | Confidential / contains PII? |
| Retention | Theo chính sách doanh nghiệp |
| Quality checks | Row count, duplicate rate, reconciliation |
| Downstream | Revenue semantic model/report |

Quản trị dữ liệu là công việc **liên tục**, không chỉ gắn nhãn “Gold” vào tên bảng.

## 30. Kết nối mạng riêng và dữ liệu doanh nghiệp

Fabric là SaaS, nên cách nó kết nối tới tài nguyên trong VNet không hoàn toàn giống một VM/AKS pod chạy trong subnet do bạn quản lý.

### Các đường truy cập cần đánh giá

- Public endpoint được firewall/IP policy cho phép.
- **On-premises data gateway** khi nguồn ở mạng nội bộ.
- **VNet data gateway** hoặc những tính năng kết nối mạng riêng được Fabric hỗ trợ.
- **Managed private endpoints/Private Link** hoặc service-specific network integrations theo từng workload/tier.
- Workspace identity hoặc service principal khi connector hỗ trợ.

**Không mặc định toàn bộ Fabric workspaces chạy bên trong VNet của bạn**, hoặc tạo một Azure Private Endpoint thì bất kỳ Notebook, Dataflow, Mirroring, Eventstream và SQL connector đều có thể đi qua cùng đường mạng đó.

### Quy trình kiểm tra

1. Xác định chính xác **Fabric workload/connector** truy cập nguồn.
2. Kiểm tra network options mà workload đó hỗ trợ.
3. Xác định authentication identity và source firewall/private DNS.
4. Kiểm thử từ Fabric activity/notebook thật, không chỉ từ laptop cá nhân.
5. Kiểm tra dữ liệu có đi qua region/network path nào.
6. Ghi lại yêu cầu compliance và dữ liệu được phép rời region.

### Tránh cách xử lý nguy hiểm

Nếu pipeline báo lỗi kết nối, đừng mở Azure SQL/Storage public network access cho **tất cả Internet** hoặc cấp quyền admin vô hạn. Phân loại lỗi **DNS/network/TLS** với **authentication/RBAC/SQL permissions** trước.

## 31. Data residency, regions và compliance

Fabric capacity được gắn với **vùng/địa lý** theo lựa chọn dịch vụ, trong khi external sources như Azure SQL, ADLS có region riêng. Truy cập dữ liệu xuyên vùng có thể ảnh hưởng:

- Network latency và bandwidth.
- Data transfer/egress costs.
- Data residency và sovereignty.
- Chính sách PII/export của tổ chức.
- Availability và recovery khi một vùng gặp sự cố.

### Ví dụ cần kiểm tra

Một tổ chức có ADLS tại một region Azure và Fabric capacity tại region khác. Một OneLake shortcut có thể tránh copy dữ liệu ban đầu, **nhưng không đồng nghĩa mọi truy vấn không đọc dữ liệu xuyên vùng hoặc không phát sinh egress**. Nếu mirroring/copy dữ liệu, cần xác định bản sao vật lý và nơi lưu.

Không tuyên bố một kiến trúc “tuân thủ địa phương” chỉ vì tên sản phẩm có chữ Azure. Phải xác minh **region của compute, storage, caches, logs, backups và network path** theo điều khoản hiện hành.

## 32. Fabric capacity và Compute Units (CU)

Fabric dùng capacity để cung cấp ngân sách compute cho nhiều workload. Những capacity gắn với **F SKU** được quản lý theo cơ chế Azure trong các cấu hình hỗ trợ, có mức năng lực biểu diễn qua **Compute Units (CU)**. Workspaces được gán vào capacity theo mô hình license/tenant.

~~~text
                     Fabric Capacity (F SKU)
                              |
                 Shared compute capacity budget
                              |
           +------------------+------------------+
           |                  |                  |
           v                  v                  v
       Spark notebook      Warehouse SQL    Power BI queries
           |                  |                  |
           +---------+--------+------------------+
                     |
                     v
              Capacity utilization
                     |
              Throttling nếu quá tải
              theo cơ chế dịch vụ
~~~

### CU không phải một CPU core

**CU** là đơn vị capacity/billing nội bộ cho các hoạt động Fabric theo cơ chế dịch vụ. Không thể quy đổi cứng **1 CU = 1 vCore Azure VM** hoặc một số queries/second cố định. Spark, Warehouse, Power BI và pipeline có consumption profiles khác nhau.

### Điều cần giám sát

- Capacity utilization và mức sử dụng theo workload/item.
- Thời gian background operations so với interactive queries.
- Throttling/delays/rejections theo chính sách capacity.
- Các peak trùng lịch giữa Spark batch, Warehouse ETL và báo cáo Power BI.
- Hiệu quả của việc phân capacity hoặc lịch chạy khác nhau.

**Một workspace chạy tốt lúc không có notebook job không có nghĩa capacity đủ cho giờ tất cả report refresh đồng thời**.

## 33. Throttling và capacity planning

Capacity có thể trải qua các giai đoạn áp lực khi tải vượt mức, theo cơ chế smoothing/throttling của Fabric. Không giả định một request đơn lẻ dùng quá cao CU là toàn bộ queries dừng ngay tức thì; cũng không giả định hệ thống tự mở rộng vô hạn.

### Ví dụ tải xung đột

~~~text
08:00  Warehouse loads Gold tables
08:05  40 Power BI reports refresh/interactive
08:10  Spark notebook chạy backfill hai tháng dữ liệu
08:15  Eventhouse đang ingest event liên tục

Nếu capacity quá nhỏ:
  Interactive report latency có thể tăng,
  background jobs có thể bị trì hoãn,
  một số requests có thể bị throttle.
~~~

### Cách xử lý

1. Đo utilization theo ngày và phân biệt interactive/background.
2. Dàn lịch batch/refresh để giảm overlap.
3. Tối ưu Spark jobs, SQL queries và model size.
4. Giảm copy/scan không cần thiết, dùng partitions.
5. Tách workloads quan trọng sang capacity riêng nếu nhu cầu/quyền cho phép.
6. Scale F SKU sau khi có benchmark và dự toán.
7. Dùng alerts, budget và runbook nếu capacity quá tải.

**Đừng tăng F SKU để chữa một pipeline nhân đôi dữ liệu do retry.** Trước hết phải khắc phục tính đúng đắn.

## 34. OneLake storage và chi phí tổng thể

Một nền tảng Fabric có các thành phần chi phí cần xét riêng:

| Thành phần | Điều cần tính |
|---|---|
| **Fabric capacity** | F SKU/compute được cấp phát hoặc billed theo mô hình mua |
| **OneLake storage** | Dữ liệu/bản sao/files/tables, retention và loại storage theo pricing |
| **External Azure storage** | ADLS/Blob dùng làm nguồn, transactions, egress nếu có |
| **External Azure compute** | Azure SQL, Databricks, Event Hubs, Functions vẫn tính tiền riêng |
| **Data movement** | Pipeline copy/mirroring/gateway/network operations theo tính năng |
| **Power BI licensing** | Quyền tạo/chia sẻ/xem báo cáo theo Fabric capacity và license chính sách hiện hành |
| **Monitoring/governance** | Log, retention, Purview và các dịch vụ tích hợp |
| **Operations** | Chi phí hỗ trợ, phát triển, quality checks, DevOps |

### Không nhầm capacity với storage

Có Fabric capacity không có nghĩa OneLake storage luôn miễn phí vô hạn. Ngược lại, ngừng/pause capacity theo cơ chế được hỗ trợ không đồng nghĩa tự xóa dữ liệu, cũng không bảo đảm storage bill dừng.

### Quy trình dự toán

1. Ước lượng số TB dữ liệu nguồn và growth.
2. Xác định dữ liệu copy vật lý, mirroring, shortcut và retention.
3. Ước lượng lịch batch/streaming, Spark, Warehouse và Power BI queries.
4. Chọn F SKU ứng viên dựa trên benchmark.
5. Tính external Azure charges, network/egress và licensing.
6. Dùng **Azure Pricing Calculator** và **Fabric Capacity Metrics** trong giai đoạn thử.
7. Đo bill thực, điều chỉnh workload và capacity.

**Không viết một đơn giá USD/CU cố định** vì region, SKU, hình thức mua và bảng giá thay đổi. Chi phí phải được tính với điều kiện thực tế.

## 35. Power BI licensing và người xem báo cáo

Một bẫy triển khai: đội dữ liệu đã có Fabric capacity và tưởng rằng **mọi người đều có thể xem mọi Power BI report mà không cần license hoặc quyền**.

Quyền dùng, chia sẻ và xem Power BI có thể phụ thuộc:

- Power BI Pro/Premium Per User hoặc license khác.
- Fabric capacity size/tier được hỗ trợ.
- Quyền workspace/item/semantic model.
- Cách report được chia sẻ, embedded hoặc external sharing.
- Tenant-level settings.

### Những câu hỏi trước khi phát hành

1. Ai là report author, ai là người xem?
2. Người xem có license nào?
3. Workspace nằm trên capacity phù hợp điều kiện share/view chưa?
4. External B2B viewers có thể xem không theo tenant policy?
5. Có cần RLS/OLS hoặc hạn chế export/download không?
6. Gateway, Direct Lake hoặc DirectQuery có làm người dùng truy vấn external source?

**Không áp một quy tắc licensing bất biến cho mọi F SKU** vì điều kiện có thể thay đổi theo product policy và mức capacity. Kiểm tra Microsoft Learn và hợp đồng tổ chức trước khi rollout.

## 36. Giám sát pipeline và dữ liệu bằng metrics

| Lớp | Cần theo dõi | Rủi ro nếu bỏ qua |
|---|---|---|
| Source | Data freshness, source errors, changes | Không biết nguồn đã ngừng cập nhật |
| Ingestion | Rows/files/events in, retries, duration | Thiếu/trùng dữ liệu |
| OneLake | Storage growth, file sizes, schema evolution | Chi phí/hiệu năng xấu |
| Spark | Job duration, failures, skew, data shuffle | Compute quá tải |
| Warehouse | Query latency, concurrency, failed operations | BI chậm/throttling |
| Eventhouse | Ingestion lag, query latency, retention | Realtime dashboard cũ |
| Semantic model | Refresh status, relationships, RLS | Metrics/report sai |
| Capacity | CU utilization, throttling và item consumption | Workload ảnh hưởng nhau |
| Security | Permission changes, unexpected sharing | Rò rỉ dữ liệu |
| Cost | Fabric + Azure external resource bills | Không biết tổng TCO |

### Một SLO về freshness

~~~text
Đơn hàng tại Azure SQL được ghi lúc 10:00.
Yêu cầu báo cáo xuất hiện trước 10:15.

Freshness SLO:
  95% đơn hợp lệ phải có trong Gold/semantic view
  trong vòng 15 phút sau khi commit nguồn.
~~~

Đây là **SLO minh họa**, không phải guarantee của Fabric. Muốn đo cần lưu source timestamp, ingestion timestamp, transformation completion và thời điểm báo cáo nhìn thấy.

### Thành công kỹ thuật khác thành công nghiệp vụ

Pipeline báo **Succeeded** không tự chứng minh:

- Tổng doanh thu đúng.
- Không thiếu bản ghi.
- Không lộ PII.
- Report đã refresh.
- Semantic measures đúng định nghĩa tài chính.

Cần kiểm thử **row-count reconciliation**, rule quality, sample audits và business-level metrics.

## 37. CI/CD, Git integration và triển khai môi trường

Fabric có các khả năng **Git integration, deployment pipelines và REST APIs** cho một số artifact/workload theo điều kiện hỗ trợ.

~~~text
Developer changes
       |
       v
Git repository (metadata/code được hỗ trợ)
       |
       v
DEV Fabric workspace
  - notebooks
  - pipeline definitions
  - semantic models/reports
       |
       v
Test/validation
       |
       v
TEST workspace
       |
       v
Approval + release
       |
       v
PROD workspace
~~~

### Những nội dung cần tách

- **Code/metadata** của pipeline, notebook và report.
- **Data** trong OneLake/warehouse.
- **Connections, credentials và identity** cho mỗi môi trường.
- **Capacity** và workspace assignment.
- **Permissions** và tenant policies.

Không giả định bấm Deploy Pipeline sẽ tự di chuyển mọi dữ liệu, copy tất cả secrets hoặc cấp quyền cho mọi users. Hãy kiểm tra item types được hỗ trợ và **deployment rules** của đúng workload.

### Quy tắc production

1. Không dùng production data làm fixture dev tùy tiện.
2. Mỗi môi trường dùng identity và external source riêng khi có thể.
3. Có test notebooks/pipeline output và số liệu reconciliation.
4. Có rollback artifact và kế hoạch dữ liệu khi schema thay đổi.
5. Version schema, query, semantic measures và dashboard definitions.
6. Review quyền/connection sau mỗi deployment.

## 38. Backup, recovery và data retention

OneLake, Warehouse, Lakehouse, shortcut và mirrored data **không tự động có cùng mô hình backup/restore**. Phải xác định khả năng khôi phục cho từng loại item và nguồn.

### Các câu hỏi RPO/RTO

- Nếu notebook ghi sai dữ liệu Silver, có thể quay lại version nào?
- Nếu xóa nhầm Lakehouse table, có khôi phục được không và trong bao lâu?
- Nếu external ADLS source bị xóa, shortcut còn dữ liệu không?
- Nếu mirrored table corrupt hoặc lag, có thể resync/backfill ra sao?
- Nếu semantic model bị deploy sai, có rollback version được không?
- Nếu một region hoặc capacity gặp sự cố, recovery workflow nào được hỗ trợ?

### Tách ba lớp khôi phục

1. **Nguồn gốc:** Azure SQL/Cosmos DB/ADLS có backup/PITR/DR riêng.
2. **Dữ liệu Fabric:** retention, versioning/time travel và cơ chế restore tương ứng từng item/table.
3. **Artifact/code:** Git/deployment history và tài liệu cấu hình.

**Một Lakehouse raw table là bản sao phân tích không tự thay thế backup đã được kiểm thử của Azure SQL**, và shortcut không tạo snapshot bảo toàn dữ liệu gốc.

## 39. Hiệu năng: tránh đọc quá nhiều dữ liệu

Các nguyên nhân tốn capacity thường gặp:

- Spark đọc toàn bộ bảng lớn mỗi lần thay vì incremental load.
- Tạo rất nhiều file nhỏ làm chậm metadata/scan.
- Join dữ liệu lớn không đúng partition strategy.
- Warehouse/BI query quét raw records thay vì Gold aggregates.
- Dataflow/Notebook chạy trùng lịch.
- Report tự refresh liên tục dù dữ liệu nguồn chỉ thay đổi mỗi ngày.
- Không prune partitions hoặc không áp predicates sớm.

### Các thực hành

- Chọn incremental ingest và idempotent MERGE khi phù hợp.
- Partition/cluster tables theo access patterns thực tế.
- Giảm file fragmentation và sử dụng tối ưu hóa bảng được Fabric hỗ trợ.
- Chỉ lấy cột/dòng cần thiết.
- Tách raw/clean/Gold layers để giảm lặp lại logic.
- Đo Spark/Warehouse/BI queries và CU consumption theo item.
- Kiểm tra tính đúng đắn trước và sau mỗi thay đổi hiệu năng.

Không chạy **OPTIMIZE/VACUUM/DELETE** trên dữ liệu production chỉ vì đọc được một gợi ý chung; cần kiểm tra engine support, transaction, retention và backup.

## 40. Lab A: tạo một Lakehouse và Gold table mẫu

**Mục tiêu:** hiểu luồng Files → Delta table → SQL → report trong Fabric. Bài lab sử dụng dữ liệu giả, chỉ chạy trong **Fabric workspace/capacity thử nghiệm đã được cấp phép**.

### Điều kiện

1. Đã được cấp workspace hoặc quyền tạo workspace lab.
2. Workspace có capacity/trial phù hợp cho các features cần dùng.
3. Có quyền tạo Lakehouse, Notebook và xem SQL analytics endpoint.
4. Không dùng dữ liệu khách hàng hoặc file có PII.
5. Có ngân sách và hướng dẫn cleanup.

### Các bước

1. Trong Fabric, chọn đúng workspace lab.
2. Tạo **Lakehouse** với tên ví dụ **sales_lab**.
3. Upload một tệp CSV giả vào **Files/landing/orders.csv**.
4. Tạo Notebook, attach lakehouse lab.
5. Dùng ví dụ PySpark ở mục 11 để nạp bảng **bronze_orders_lab**.
6. Tạo bước chuyển đổi Silver/Gold:
   - Validate amount/order_id.
   - Tính tổng số tiền theo ngày hoặc customer segment.
   - Chọn unique business key.
7. Kiểm tra bảng Delta đã xuất hiện trong Lakehouse.
8. Dùng SQL analytics endpoint để **SELECT** dữ liệu, không thử DML tùy ý.
9. Nếu đủ quyền/licensing, tạo semantic model/report từ Gold table.
10. Ghi lại thời gian chạy notebook, số dòng source/target và số liệu capacity.

### Ví dụ SQL read-only cho bảng Gold giả định

~~~sql
SELECT
    order_date,
    COUNT(*) AS order_count,
    SUM(amount) AS gross_amount
FROM dbo.gold_orders_lab
GROUP BY order_date
ORDER BY order_date DESC;
~~~

Nếu schema/table names thực không thuộc **dbo**, phải đổi tên theo endpoint. Không giả định Notebook ở bước 5 đã tạo sẵn Gold table; bước 6 mới tạo Gold sau khi chuẩn hóa.

### Nghiệm thu

| Kiểm tra | PASS khi |
|---|---|
| Workspace | Đúng workspace/capacity lab |
| Files | CSV fake có thể đọc |
| Notebook | Chạy thành công, có log run ID/row count |
| Delta | Bảng tồn tại trong đúng Lakehouse |
| Schema | order_id/amount đúng kiểu mong muốn |
| Quality | Không có duplicate ngoài hợp đồng |
| SQL | SELECT đọc được bảng được hỗ trợ |
| Report | Metrics khớp SQL, quyền người xem phù hợp |
| Cost | Đã quan sát compute/capacity tiêu thụ |
| Cleanup | Items lab được dọn theo quyền/phê duyệt |

## 41. Lab B: dùng shortcut thay vì copy

**Mục tiêu:** phân biệt quyền tham chiếu OneLake shortcut với sao chép vật lý.

### Chuẩn bị

- Một ADLS Gen2 container lab đã có bảng/file được tổ chức phê duyệt.
- Kết nối external source được hỗ trợ.
- Identity/connection có quyền đọc phạm vi tương ứng.
- Workspace Lakehouse lab.

### Thao tác

1. Trong Lakehouse, tạo shortcut đến thư mục ADLS lab theo UI/tính năng được hỗ trợ.
2. Kiểm tra shortcut xuất hiện ở khu vực Files hoặc Tables theo loại nguồn.
3. Thử đọc một tệp/bảng từ Notebook bằng đường dẫn được Fabric cung cấp.
4. So sánh với Copy activity: Copy tạo dữ liệu vật lý ở đích; shortcut tham chiếu đường nguồn theo connector.
5. Thu hồi quyền đọc **trong môi trường lab** rồi quan sát hành vi/notification nếu được phép.
6. Đánh giá latency, data egress, access log và ownership.

### Những điều không được suy ra

- Tạo shortcut không tự cấp quyền read cho mọi Fabric viewer.
- Shortcut không là backup.
- Không phải mọi external file sẽ xuất hiện tự động thành Delta table.
- Shortcut không chứng minh data residency compliance nếu chưa kiểm tra đường đọc/copy.

### Câu hỏi

Vì sao một tổ chức yêu cầu dữ liệu không được copy ra khỏi ADLS region vẫn cần đánh giá **network path và external processing** trước khi dùng shortcut?

## 42. Lab C: Event Hubs tới Real-Time Intelligence

**Mục tiêu:** nhận biết các ranh giới giữa Azure ingestion và Fabric analytics.

~~~text
Telemetry producer (lab)
       |
       v
Azure Event Hubs
       |
       v
Fabric Eventstream (supported connector)
       |
       v
Eventhouse / KQL Database
       |
       v
Read-only KQL / dashboard
~~~

### Quy trình

1. Chuẩn bị Event Hubs namespace/event hub lab được cấp phép.
2. Kiểm tra RBAC/credentials cho connector đọc event.
3. Tạo Fabric Eventstream với nguồn Event Hubs được hỗ trợ.
4. Chọn destination Eventhouse/KQL theo cấu hình được phép.
5. Gửi vài sự kiện giả qua producer lab có timestamp và event type.
6. Xem ingestion status và latency; đọc bằng KQL giống mục 16.
7. Thử thay đổi schema bằng một event lab lỗi, quan sát quarantine/errors.
8. Dừng ingest theo quy trình và kiểm tra cleanup/cost.

### Những điều cần trả lời

- Producer thành công có chứng minh Eventhouse đã nhận dữ liệu không?
- Fabric Eventstream có tự lưu lịch sử event giống Event Hubs consumer group retention không?
- Số lượng event nhìn thấy có thể chậm vì connection/consumer lag ở đâu?
- Nếu Eventhouse bị tạm ngưng, yêu cầu recovery/replay phụ thuộc vào retention và cách kết nối nào?

Không chạy producer tốc độ cao trên Event Hubs/Fabric capacity không có ngân sách; vài record giả đã đủ để kiểm tra đường đi dữ liệu.

## 43. Tình huống kiến trúc: doanh nghiệp thương mại điện tử

Một doanh nghiệp có:

- Azure SQL Database làm OLTP cho đơn hàng.
- Azure Cosmos DB lưu sự kiện hành vi/giỏ hàng.
- ADLS Gen2 chứa tệp lịch sử.
- Azure Event Hubs thu 20 triệu click events/ngày.
- Đội phân tích muốn báo cáo doanh thu mỗi 15 phút.
- Đội vận hành muốn cảnh báo clickstream bất thường trong vài phút.
- Nhóm ML muốn dự báo nhu cầu hàng tuần.
- Bộ phận bảo mật yêu cầu PII chỉ được đọc bởi nhóm được phê duyệt.
- Tổ chức đã có Power BI, Azure Databricks và một số ADF pipelines.

### Nhiệm vụ

1. Phân loại data sources theo OLTP, lake files và streaming.
2. Chọn thành phần Fabric có thể hỗ trợ mỗi loại phân tích.
3. Thiết kế luồng Azure SQL → Fabric với Copy/Mirroring tùy khả năng nguồn.
4. Giải thích khi nào OneLake shortcut phù hợp với ADLS và khi nào cần copy/transform.
5. Thiết kế Bronze/Silver/Gold với watermark, deduplication, timezone và currency.
6. Giải thích làm sao đáp ứng freshness SLO 15 phút và đo lỗi.
7. Dùng Eventstream/Eventhouse/KQL cho near-real-time alerts.
8. Thiết kế semantic model doanh thu và kiểm soát quyền report.
9. Đề xuất những tác vụ tiếp tục chạy trong Azure Databricks thay vì migrate ngay.
10. Thiết kế workspace/capacity cho môi trường dev/test/prod.
11. Nêu cách kết nối Azure SQL/ADLS qua network policy được phê duyệt.
12. Đánh giá CU/capacity, OneLake storage, Azure sources và Power BI licensing.
13. Thiết kế quy trình khôi phục nếu Silver pipeline tạo dữ liệu trùng.
14. Nêu bộ metrics cho ingestion, Gold freshness, report availability và chi phí.
15. Đề xuất kiểm thử với một nhóm người dùng có quyền thấp, bao gồm PII không được lộ.

### Gợi ý giải pháp

~~~text
Azure SQL + ADLS + Cosmos DB --> Fabric pipeline/mirror/shortcut
                                          |
                                          v
                                 Bronze Lakehouse
                                          |
                                          v
                             Silver validated Delta tables
                                          |
                                          v
                              Gold Warehouse / Lakehouse
                                          |
                                          v
                             Power BI semantic model/report

Event Hubs --> Fabric Eventstream --> Eventhouse --> KQL / alerts

Gold/Silver data --> Fabric Notebook hoặc Databricks/ML workflow
~~~

Đây là **hướng triển khai để đánh giá**, không phải kiến trúc duy nhất. Sự lựa chọn phụ thuộc quotas, IAM, connectors, latency, region, tính năng, workforce skills và TCO.

## 44. Checklist trước khi dùng Fabric trong production

| Nhóm | Điều cần xác minh |
|---|---|
| Mục tiêu | Fabric giải quyết nhu cầu dữ liệu nào, không chỉ chọn vì sản phẩm mới |
| Source of truth | OLTP sources giữ đúng vai trò, pipeline không phá giao dịch |
| Tenant/capacity | Tenant settings, F SKU và capacity assignment phù hợp |
| Workspace | Môi trường dev/test/prod, owner và vai trò rõ ràng |
| OneLake | Nguồn dữ liệu, storage growth, Files/Tables và quyền |
| Shortcut | Đúng connector, identity, data residency và không coi là backup |
| Mirroring | Nguồn hỗ trợ, lag, initial sync và source load |
| Data Factory | Pipeline dependencies, retries, watermark/idempotency |
| Spark/Notebook | Runtime/version, schema, quality, compute usage |
| Warehouse | SQL feature support, data model, query latency |
| Realtime | Eventstream/Eventhouse ingestion lag/retention |
| Semantic model | Metrics chuẩn, Direct Lake compatibility, RLS/OLS |
| Identity | Entra group, managed/workspace identities và least privilege |
| External sources | Azure SQL/ADLS/Event Hubs access, network và DNS |
| Data governance | Catalog, lineage, classification, owner và retention |
| Data privacy | PII masking/access, share/export restrictions |
| Region | Data residency, network egress và recovery requirements |
| CI/CD | Git/deployment support, parameters, secrets và rollback |
| Monitoring | Quality/freshness, capacity throttle, query/refresh errors |
| Cost | Capacity + OneLake + Azure external resources + licensing |
| DR | Data restoration, replay/backfill và runbooks đã thử |
| Training | Nhóm vận hành hiểu sự khác biệt giữa Fabric SaaS và Azure PaaS |

## 45. Câu hỏi tự kiểm tra

1. Microsoft Fabric là SaaS hay một Azure VM?
2. Vì sao Fabric không đồng nghĩa chỉ có Power BI?
3. OneLake là gì, có phải một subscription Azure chứa tất cả blobs không?
4. Phân biệt Fabric capacity, workspace và item.
5. CU khác vCore của Azure VM ở điểm nào?
6. Lakehouse dùng Files và Tables để giải quyết nhu cầu nào?
7. Delta Lake có điểm gì hữu ích so với raw CSV?
8. Lakehouse SQL analytics endpoint khác Warehouse SQL endpoint ở khả năng ghi thế nào?
9. Fabric Warehouse có nên là nơi API checkout trực tiếp thực hiện tất cả OLTP transaction không?
10. Data Factory pipeline khác Dataflow Gen2 ra sao?
11. Notebook Spark có nên chạy cho mọi bảng nhỏ vài chục dòng không?
12. Bronze, Silver và Gold có những nhiệm vụ gì?
13. Khi nào có thể dùng OneLake shortcut thay copy?
14. Shortcut có bảo đảm có bản backup bất biến không?
15. Mirroring khác shortcut và Copy activity thế nào?
16. Mirroring có đảm bảo report luôn thấy giao dịch mới nhất không?
17. Session/user nào được phép đọc external shortcut, và cần kiểm tra quyền ở đâu?
18. Fabric Eventstream khác Azure Event Hubs như thế nào?
19. Eventhouse/KQL Database thích hợp với dữ liệu nào?
20. KQL summarize by bin hỗ trợ bài toán gì?
21. Semantic model cung cấp lợi ích gì so với report trực tiếp trên raw tables?
22. Direct Lake, DirectQuery và Import khác nhau ở đâu?
23. Power BI RLS có tự bảo vệ raw OneLake Files không?
24. Tại sao pipeline báo succeeded chưa chắc Gold data đúng?
25. Watermark đơn giản theo timestamp có thể bỏ sót sự kiện đến muộn thế nào?
26. Vì sao retry append vào Bronze có thể nhân đôi dữ liệu?
27. Những khác biệt nào cần đánh giá khi chuyển từ ADF sang Fabric Data Factory?
28. Fabric có bắt buộc thay Azure Databricks đang chạy ổn định không?
29. Fabric capacity và OneLake storage có cùng mô hình billing không?
30. Vì sao một F SKU không tự cho phép mọi report viewer xem báo cáo miễn phí?
31. Những yếu tố nào có thể gây Fabric capacity throttling?
32. Có nên cho Spark backfill chạy đồng thời giờ report peak không?
33. Tenant Entra ID và workspace roles giải quyết những câu hỏi quyền nào?
34. Có thể mặc định Fabric kết nối được mọi private Azure SQL/ADLS resource trong VNet không?
35. Vì sao shortcut vẫn cần đánh giá data residency và network egress?
36. Tại sao Azure SQL backup không được thay bởi một Lakehouse mirror?
37. Làm sao thiết kế pipeline backfill sau khi dữ liệu bị trùng?
38. Một freshness SLO báo cáo 15 phút phải đo những timestamps nào?
39. Những metric nào giúp phân biệt Spark query chậm và capacity bị throttled?
40. Với kiến trúc bán lẻ, bạn sẽ giữ dữ liệu giao dịch ở Azure SQL hay chuyển toàn bộ vào Warehouse, và vì sao?

## Tài liệu tham khảo

- Microsoft Learn — *What is Microsoft Fabric?*: https://learn.microsoft.com/fabric/fundamentals/microsoft-fabric-overview
- Microsoft Learn — *Fabric terminology*: https://learn.microsoft.com/fabric/fundamentals/fabric-terminology
- Microsoft Learn — *OneLake overview*: https://learn.microsoft.com/fabric/onelake/onelake-overview
- Microsoft Learn — *OneLake shortcuts*: https://learn.microsoft.com/fabric/onelake/onelake-shortcuts
- Microsoft Learn — *Lakehouse overview*: https://learn.microsoft.com/fabric/data-engineering/lakehouse-overview
- Microsoft Learn — *SQL analytics endpoint*: https://learn.microsoft.com/fabric/data-engineering/lakehouse-sql-analytics-endpoint
- Microsoft Learn — *Fabric Data Warehouse overview*: https://learn.microsoft.com/fabric/data-warehouse/data-warehousing
- Microsoft Learn — *Data Factory in Fabric*: https://learn.microsoft.com/fabric/data-factory/data-factory-overview
- Microsoft Learn — *Dataflow Gen2*: https://learn.microsoft.com/fabric/data-factory/dataflows-gen2-overview
- Microsoft Learn — *Fabric notebooks*: https://learn.microsoft.com/fabric/data-engineering/how-to-use-notebook
- Microsoft Learn — *Medallion architecture in Fabric*: https://learn.microsoft.com/fabric/onelake/onelake-medallion-lakehouse-architecture
- Microsoft Learn — *Mirroring in Fabric*: https://learn.microsoft.com/fabric/database/mirrored-database/overview
- Microsoft Learn — *Real-Time Intelligence overview*: https://learn.microsoft.com/fabric/real-time-intelligence/overview
- Microsoft Learn — *Eventstream overview*: https://learn.microsoft.com/fabric/real-time-intelligence/event-streams/overview
- Microsoft Learn — *Eventhouse overview*: https://learn.microsoft.com/fabric/real-time-intelligence/eventhouse
- Microsoft Learn — *Power BI Direct Lake*: https://learn.microsoft.com/fabric/fundamentals/direct-lake-overview
- Microsoft Learn — *Fabric capacity overview*: https://learn.microsoft.com/fabric/enterprise/licenses
- Microsoft Learn — *Fabric Capacity Metrics*: https://learn.microsoft.com/fabric/enterprise/metrics-app
- Microsoft Learn — *Fabric security overview*: https://learn.microsoft.com/fabric/security/security-overview
- Microsoft Learn — *Git integration*: https://learn.microsoft.com/fabric/cicd/git-integration/intro-to-git-integration
- Microsoft Learn — *Deployment pipelines*: https://learn.microsoft.com/fabric/cicd/deployment-pipelines/intro-to-deployment-pipelines
- Microsoft Learn — *Microsoft Purview and Fabric*: https://learn.microsoft.com/fabric/governance/microsoft-purview-fabric
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
