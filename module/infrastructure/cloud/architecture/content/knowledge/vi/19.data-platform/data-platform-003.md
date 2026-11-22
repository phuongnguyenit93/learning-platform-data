# Data lake, data warehouse và lakehouse

> **Chương:** Nền tảng dữ liệu  
> **Module:** CLOUD_ARCHITECTURE  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học cân nhắc độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của data lake, data warehouse và lakehouse, cùng những vấn đề mỗi mô hình giải quyết.
2. Chọn mô hình lưu trữ và xử lý theo loại dữ liệu, access pattern, độ trễ, tính nhất quán, kỹ năng đội ngũ và chi phí.
3. Phác thảo nền tảng dữ liệu cloud từ ingestion, vùng lưu trữ, catalog, xử lý, phục vụ đến quản trị và quan sát.
4. Phân biệt batch, micro-batch và streaming; xác định độ trễ dữ liệu và bảo đảm giao nhận/khôi phục cần thiết.
5. Hiểu vai trò của định dạng tệp cột, table format, metadata/catalog và transaction trong hồ dữ liệu hiện đại.
6. Thiết kế phân vùng, vòng đời lưu trữ, chất lượng dữ liệu, quyền truy cập và quản lý chi phí.
7. Đánh giá lựa chọn lake/warehouse/lakehouse theo yêu cầu nghiệp vụ và các trụ cột Well-Architected.

## 1. Bài toán nền tảng dữ liệu trong kiến trúc cloud

Một ứng dụng giao dịch thường cần cơ sở dữ liệu phục vụ request với độ trễ thấp và ràng buộc cập nhật chặt chẽ. Nhưng khi doanh nghiệp muốn phân tích hành vi khách hàng, theo dõi vận hành, huấn luyện mô hình hoặc kết hợp dữ liệu từ nhiều hệ thống, chạy mọi truy vấn phân tích trên database giao dịch có thể gây tranh chấp CPU, I/O và connection với workload phục vụ người dùng.

**Nền tảng dữ liệu (data platform)** tổ chức cách thu nhận, lưu trữ, xử lý, quản trị và cung cấp dữ liệu cho các nhu cầu đó. Một nền tảng thường hỗ trợ nhiều dạng dữ liệu:

- Dữ liệu có cấu trúc từ relational database, ERP, CRM và hệ thống giao dịch.
- Dữ liệu bán cấu trúc như JSON, log, event, clickstream và tài liệu.
- Dữ liệu phi cấu trúc như ảnh, video, âm thanh và tệp.
- Dữ liệu thay đổi theo thời gian, gồm CDC (change data capture), event và telemetry.
- Dữ liệu tham chiếu, metadata, danh mục dữ liệu và thông tin quản trị.

Các nhóm người dùng cũng khác nhau: ứng dụng cần đọc/ghi giao dịch; analyst cần SQL và dữ liệu đã chuẩn hóa; data engineer cần ingest/transform; data scientist cần khám phá và thử nghiệm; hệ thống báo cáo cần mô hình ổn định; nhóm quản trị cần lineage, quyền truy cập và bằng chứng kiểm toán.

### 1.1. Câu hỏi thiết kế trước khi chọn công nghệ

| Câu hỏi | Ví dụ | Tác động tới kiến trúc |
|---|---|---|
| Dữ liệu đến từ đâu? | DB giao dịch, SaaS, file, sensor, event | Batch ingestion, CDC, streaming hoặc file transfer |
| Định dạng và tốc độ tăng? | 200 GB/ngày, tăng 30%/năm; nhiều file nhỏ hay ít file lớn | Object storage, compaction, partitioning và lifecycle |
| Độ trễ chấp nhận? | Báo cáo ngày hôm sau hay dashboard cập nhật trong vài giây | Batch, micro-batch hoặc streaming |
| Ai sử dụng? | SQL analyst, BI, ứng dụng, ML pipeline | Warehouse, query engine, API hoặc feature pipeline |
| Cần mức nhất quán nào? | Snapshot nhất quán hay chấp nhận eventual consistency | Transaction, watermark, CDC offset và table format |
| Dữ liệu nhạy cảm đến đâu? | PII, thanh toán, dữ liệu công khai | Encryption, IAM, masking, retention và audit |
| Có cần lưu nguyên bản? | Điều tra, replay, kiểm toán | Raw zone bất biến, versioning và retention |
| Khả năng chi trả/vận hành? | Đội nhỏ, tải biến động, ngân sách hạn chế | Dịch vụ quản lý, autoscaling, serverless hoặc mô hình lai |

Không phải workload nào cũng cần một nền tảng lớn. Một nhóm có vài báo cáo có thể dùng database replica hoặc warehouse nhỏ; khi nguồn dữ liệu, lịch sử và nhu cầu phân tích tăng, lake/warehouse/lakehouse trở nên hữu ích. Chọn kiến trúc theo yêu cầu hiện tại và đường tiến hóa có thể kiểm soát.

## 2. Data lake: lưu trữ linh hoạt với dữ liệu ở quy mô lớn

### 2.1. Khái niệm và mục tiêu

**Data lake** là kho dữ liệu tập trung, thường xây dựng trên object storage có khả năng mở rộng, để lưu dữ liệu ở nhiều định dạng và mức xử lý khác nhau. Dữ liệu có thể được giữ gần với định dạng nguồn ban đầu, sau đó mới làm sạch, chuẩn hóa hoặc biến đổi theo mục đích sử dụng.

Một lake thường có các đặc tính:

- **Schema-on-read:** cấu trúc/kiểu dữ liệu được áp dụng hoặc diễn giải khi đọc, tùy định dạng và engine.
- **Định dạng linh hoạt:** CSV, JSON, Parquet, Avro, ảnh, log, binary và nhiều định dạng khác.
- **Chi phí lưu trữ theo lớp:** tận dụng object storage và lifecycle chuyển dữ liệu ít truy cập sang lớp rẻ hơn.
- **Tách compute khỏi storage:** nhiều engine có thể đọc cùng vùng dữ liệu mà không cần một cụm database duy nhất.
- **Giữ dữ liệu raw:** thuận tiện tái xử lý khi logic nghiệp vụ thay đổi hoặc cần điều tra nguồn gốc.

Schema-on-read không có nghĩa dữ liệu không cần schema hoặc validation. Nếu thiếu hợp đồng, catalog và kiểm tra chất lượng, lake có thể trở thành **data swamp**: nhiều tệp khó tìm, lược đồ không rõ, dữ liệu lỗi/trùng, quyền truy cập không kiểm soát và không ai biết dữ liệu còn giá trị hay không.

### 2.2. Các vùng dữ liệu thường gặp

| Vùng | Mục đích | Đặc điểm |
|---|---|---|
| **Landing / ingest** | Nhận dữ liệu từ nguồn | Giữ dấu vết nhận, checksum, manifest, thời gian ingest |
| **Raw / bronze** | Lưu dữ liệu gần nguyên bản | Append/version, ít biến đổi, lưu metadata nguồn và thời điểm |
| **Cleaned / silver** | Làm sạch, chuẩn hóa, khử trùng | Có schema rõ, chất lượng được kiểm tra |
| **Curated / gold** | Phục vụ phân tích/BI theo nghiệp vụ | Mô hình dễ dùng, metric thống nhất, access policy cụ thể |
| **Archive** | Giữ dữ liệu lịch sử ít truy cập | Storage class rẻ hơn, truy xuất lâu hơn, retention rõ |

Tên bronze/silver/gold là quy ước tổ chức thường dùng, không phải chuẩn bắt buộc. Có thể dùng raw/standardized/serving hoặc cấu trúc khác. Điều quan trọng là mỗi vùng có ý nghĩa, owner, quyền và chất lượng đầu ra được định nghĩa.

### 2.3. Sơ đồ data lake

~~~mermaid
flowchart LR
    DB[(Operational DB)] --> CDC[CDC / Batch Ingestion]
    SaaS[SaaS / APIs] --> ING[Ingestion]
    Files[Files / Logs / Events] --> ING
    CDC --> RAW[(Object Storage: Raw)]
    ING --> RAW
    RAW --> PROC[Batch / Spark / SQL Processing]
    PROC --> CLEAN[(Cleaned / Silver)]
    CLEAN --> CURATED[(Curated / Gold)]
    CURATED --> BI[BI / Analytics]
    RAW --> DS[Data Science / ML]
    CAT[Catalog + Governance] -.-> RAW
    CAT -.-> CLEAN
    CAT -.-> CURATED
~~~

Sơ đồ chỉ thể hiện luồng logic. Triển khai thực tế cần network boundary, danh tính workload, khóa mã hóa, vùng lưu trữ, catalog, logging, checkpoint và cách truy cập riêng cho từng engine.

### 2.4. Khi nào data lake phù hợp?

- Dữ liệu đa dạng và tăng nhanh; muốn lưu bản gốc phục vụ phân tích sau này.
- Có workload khám phá, data science, machine learning hoặc tái xử lý.
- Cần tách chi phí lưu trữ khỏi compute và chọn engine theo từng tác vụ.
- Nhiều nhóm dùng chung dữ liệu nhưng có nhu cầu xử lý khác nhau.
- Muốn giữ lịch sử dài hạn với lifecycle policy rõ.

Đánh đổi là phải tổ chức schema, metadata, transaction, quyền truy cập, chất lượng, compaction và vòng đời. Query trên nhiều tệp nhỏ, CSV/JSON không tối ưu hoặc partition không hợp lý có thể chậm và tốn chi phí. Chỉ có object storage chưa tạo thành nền tảng dữ liệu đáng tin cậy.

## 3. Data warehouse: dữ liệu được tổ chức để phân tích

### 3.1. Khái niệm và mục tiêu

**Data warehouse** là hệ thống lưu trữ và truy vấn dữ liệu phân tích, thường tích hợp dữ liệu từ nhiều nguồn, làm sạch và mô hình hóa theo cấu trúc phù hợp cho SQL, BI và báo cáo.

Đặc trưng thường thấy:

- **Schema-on-write:** dữ liệu được kiểm tra/chuyển đổi theo schema trước khi nạp vào mô hình phục vụ.
- **Mô hình phân tích:** fact, dimension, star schema, snowflake hoặc data model theo nhu cầu.
- **Tối ưu truy vấn phân tích:** columnar storage, compression, parallel execution, caching và query optimizer.
- **Quản trị tập trung:** quyền theo schema/table/column/row, audit và chia sẻ dữ liệu được kiểm soát.
- **Tách workload:** truy vấn BI không chạy trực tiếp trên database giao dịch.

Nhiều warehouse cloud hiện đại là managed/serverless hoặc tách storage khỏi compute. Mỗi nhà cung cấp có cách định giá, concurrency, caching, giới hạn và semantics khác nhau; cần đọc mô hình thực tế chứ không suy ra mọi warehouse hoạt động giống nhau.

### 3.2. Fact và dimension

Ví dụ phân tích doanh thu và số booking:

- **FactBooking:** một dòng cho một booking hoặc một sự kiện nghiệp vụ được xác định grain rõ.
- **DimCustomer:** thuộc tính khách hàng dùng để phân loại.
- **DimResource:** thông tin tài nguyên/dịch vụ.
- **DimDate:** ngày, tháng, quý, ngày trong tuần.
- **DimLocation:** khu vực/địa điểm nếu có.

~~~mermaid
flowchart TB
    FC[(FactBooking)] --> DC[DimCustomer]
    FC --> DR[DimResource]
    FC --> DD[DimDate]
    FC --> DL[DimLocation]
~~~

Grain của fact cần được ghi rõ: một dòng đại diện một booking, một lần thay đổi trạng thái hay một dòng thanh toán? Nếu grain mơ hồ, việc cộng doanh thu hoặc đếm booking có thể sai do join nhân bản hoặc tính lặp nhiều trạng thái.

### 3.3. Ví dụ star schema

| Bảng | Khóa | Trường minh họa | Vai trò |
|---|---|---|---|
| FactBooking | booking_key (surrogate) | date_key, customer_key, resource_key, status_key, amount, count | Số liệu đo lường |
| DimCustomer | customer_key | customer_id, segment, created_date, valid_from/to | Phân tích theo khách |
| DimResource | resource_key | resource_id, category, location_key | Phân tích theo tài nguyên |
| DimDate | date_key | date, month, quarter, year, weekday | Phân tích theo thời gian |
| DimStatus | status_key | status_code, status_group | Nhóm trạng thái |

Nếu cần theo dõi thay đổi thuộc tính dimension theo thời gian, có thể dùng **Slowly Changing Dimension (SCD)**. Type 1 ghi đè thông tin hiện tại; Type 2 tạo bản ghi phiên bản mới với valid_from/valid_to và cờ current. Cách chọn ảnh hưởng khả năng trả lời “khách thuộc phân khúc nào lúc giao dịch xảy ra?” khác với “khách hiện thuộc phân khúc nào?”.

### 3.4. Khi nào warehouse phù hợp?

- BI/reporting với SQL và metric có định nghĩa thống nhất.
- Truy vấn tổng hợp trên nhiều nguồn và lượng dữ liệu lớn.
- Cần concurrency cho analyst, dashboard và workload phân tích.
- Muốn mô hình dữ liệu có kiểm soát, curated data và quyền truy cập chi tiết.
- Đội ngũ cần tích hợp tốt với công cụ BI/semantic layer hiện có.

Đánh đổi gồm chi phí compute khi query nặng, chi phí ingest/storage, phụ thuộc tính năng và pricing dịch vụ, cũng như nhu cầu chuyển dữ liệu và quản lý mô hình. Warehouse có thể hỗ trợ một số loại dữ liệu mở rộng, nhưng không mặc nhiên thay thế object lake cho mọi loại tệp.

## 4. Lakehouse: kết hợp hồ dữ liệu và khả năng quản lý bảng

### 4.1. Động cơ hình thành

Data lake linh hoạt và thường có economics tốt cho object storage, nhưng các tệp rời thiếu transaction, cập nhật đồng thời và metadata bảng chuẩn hóa. Warehouse cung cấp trải nghiệm SQL/transaction/management tốt nhưng có thể gắn chặt storage/compute hoặc tạo thêm bản sao khi dữ liệu thô đã nằm trong lake.

**Lakehouse** là kiến trúc hướng tới việc dùng storage mở hoặc object storage làm nền, đồng thời bổ sung lớp quản lý bảng và metadata để hỗ trợ một số đặc tính thường gắn với warehouse: schema enforcement/evolution, transaction, snapshot, update/delete, time travel và nhiều engine truy cập.

Lakehouse thường dựa trên:

- Object storage làm lớp lưu trữ bền vững.
- Định dạng dữ liệu cột như Parquet.
- Table format cung cấp metadata, snapshot và transaction semantics.
- Catalog/metadata service để đăng ký bảng, schema, location và quyền.
- Engine xử lý batch/streaming/SQL/ML để đọc và ghi.
- Governance, lineage, quality và access control xuyên engine.

Lakehouse không phải một định dạng file hoặc một dịch vụ đơn lẻ. Tính năng hỗ trợ phụ thuộc table format, catalog, engine, connector và phiên bản; một tính năng có trong một engine chưa chắc hoạt động giống nhau khi nhiều engine cùng ghi.

### 4.2. Sơ đồ lakehouse

~~~mermaid
flowchart TB
    SRC[DB / SaaS / Events / Files] --> ING[Batch / CDC / Streaming Ingestion]
    ING --> OBJ[(Object Storage)]
    subgraph Lakehouse[Lakehouse Table Layer]
        OBJ --> PARQ[Parquet / Columnar Files]
        META[Table Format Metadata / Snapshots]
        CAT[Catalog / Namespace / Schema]
        PARQ <--> META
        CAT --> META
    end
    ENG1[Spark / Batch Engine] <--> Lakehouse
    ENG2[SQL Query Engine] <--> Lakehouse
    ENG3[Streaming Engine] <--> Lakehouse
    ENG4[ML / Data Science] <--> Lakehouse
    GOV[Governance / IAM / Lineage / Quality] -.-> CAT
    BI[BI / Data Products] --> ENG2
~~~

Sơ đồ biểu diễn khái niệm; cách engine kết nối object storage/catalog và cách commit snapshot phụ thuộc hệ sinh thái đã chọn. Không phải mọi engine đều hỗ trợ đầy đủ mọi thao tác trên cùng table format.

### 4.3. So sánh ba mô hình

| Tiêu chí | Data lake | Data warehouse | Lakehouse |
|---|---|---|---|
| Mục tiêu chính | Lưu đa dạng dữ liệu quy mô lớn, linh hoạt xử lý | Phân tích SQL/BI trên dữ liệu có mô hình | Kết hợp lưu trữ mở với quản lý bảng/transaction |
| Storage | Thường object storage | Managed storage hoặc storage tích hợp dịch vụ | Thường object storage |
| Schema | Thường schema-on-read ở nhiều vùng | Thường schema-on-write trước serving | Có schema enforcement/evolution qua table layer |
| Transaction bảng | Không có mặc định cho file rời; cần cơ chế bổ sung | Thường là tính năng managed warehouse | Table format/engine phối hợp cung cấp |
| Dữ liệu phi cấu trúc | Rất phù hợp | Tùy dịch vụ, thường cần cách lưu riêng | Có thể lưu cùng storage; quản lý metadata tùy cách dùng |
| SQL/BI | Cần query engine/catalog phù hợp | SQL thường là trọng tâm | Nhiều SQL engine, tùy tương thích |
| Batch/stream/ML | Linh hoạt, governance phải xây | Hỗ trợ theo dịch vụ/công cụ | Hướng đến nhiều engine cùng dùng dữ liệu |
| Quản trị | Dễ rời rạc nếu thiếu catalog/policy | Thường tích hợp quản trị tập trung | Cần phối hợp catalog, table format và engine |
| Đánh đổi | Data swamp, small files, schema drift | Chi phí compute, dịch vụ/proprietary coupling | Độ phức tạp tích hợp/compatibility và vận hành |

Các mô hình không loại trừ nhau. Một tổ chức có thể dùng lake lưu raw, warehouse cung cấp KPI quan trọng, và lakehouse cho dữ liệu dùng chung giữa batch, SQL và ML. Việc có nhiều lớp phải có lý do: tránh sao chép vô ích và quy định nguồn sự thật rõ ràng.

### 4.4. Khi nào lakehouse đáng cân nhắc?

- Muốn nhiều engine cùng truy cập các bảng dùng chung mà giảm việc tạo nhiều bản sao.
- Cần update/delete/merge, snapshot và schema evolution trên dữ liệu trong object storage.
- Có cả batch, streaming, SQL analytics và data science.
- Muốn định dạng/bảng mở và lựa chọn engine linh hoạt hơn.
- Đội ngũ có khả năng quản lý catalog, transaction semantics, compaction, file layout và tương thích engine.

Lakehouse có thể giảm phụ thuộc vào một warehouse độc quyền, nhưng **không tự động loại bỏ vendor lock-in**. Catalog, cloud object storage, engine, IAM và công cụ quản trị vẫn tạo phụ thuộc. Chi phí vận hành có thể cao nếu tổ chức phải tự phối hợp nhiều thành phần.

## 5. Định dạng tệp và table format: hai lớp khác nhau

### 5.1. Row format và columnar format

CSV/JSON thường dễ trao đổi, dễ đọc thủ công nhưng có thể tốn dung lượng và CPU khi phân tích cột. **Parquet** và **ORC** là định dạng lưu trữ theo cột, hỗ trợ compression và đọc chọn cột/row group, thường phù hợp workload phân tích.

| Định dạng | Đặc điểm | Phù hợp |
|---|---|---|
| CSV | Văn bản hàng-cột đơn giản, ít metadata kiểu dữ liệu | Trao đổi đơn giản, ingest nguồn, dữ liệu nhỏ |
| JSON | Linh hoạt, nested/semi-structured | Event/API, raw landing |
| Avro | Row-oriented, schema được mô tả cùng dữ liệu | Event/record serialization, streaming |
| Parquet | Columnar, compression, predicate/column pruning tùy engine | Analytics, lake/lakehouse |
| ORC | Columnar, tối ưu cho một số hệ sinh thái SQL/big data | Analytics, khi engine hỗ trợ tốt |

Chọn định dạng theo producer/consumer, schema evolution, compression, scan pattern, latency và interoperability. File Parquet không tự có transaction, catalog hoặc quyền truy cập ở mức bảng.

### 5.2. File format không phải table format

**File format** mô tả cách bytes được tổ chức trong một tệp. **Table format** quản lý tập tệp như một bảng logic, gồm metadata, snapshot/transaction, schema, partition spec và thao tác cập nhật/xóa theo cơ chế của nó.

Một bảng lakehouse có thể gồm hàng trăm file Parquet và metadata log/snapshot. Khi ghi transaction mới, table format xác định phiên bản bảng nào được commit và tệp nào thuộc snapshot đó. Engine đọc bảng qua metadata thay vì tự quét mọi file trong prefix storage.

### 5.3. Một số table format phổ biến

| Table format | Ý tưởng/đặc điểm khái quát | Khi đánh giá cần chú ý |
|---|---|---|
| **Apache Iceberg** | Table format mở, metadata và snapshot; schema/partition evolution theo đặc tả và engine | Catalog, engine compatibility, commit protocol, version/tính năng từng connector |
| **Delta Lake** | Transaction log quản lý version và thao tác bảng; hệ sinh thái xử lý dữ liệu rộng | Tương thích engine, protocol version và tính năng mở rộng cụ thể |
| **Apache Hudi** | Quản lý dữ liệu lake với upsert/incremental processing và các chế độ lưu trữ | Query mode, compaction/cleaning, timeline và hỗ trợ engine |

Không nên kết luận ba định dạng tương đương hoàn toàn hoặc mọi engine đều đọc/ghi mọi tính năng như nhau. Trước khi chọn, lập compatibility matrix theo engine, catalog, cloud storage, reader/writer version, concurrency model, schema evolution, deletes, streaming và governance. Thử workload thực tế và kiểm tra giới hạn phiên bản.

### 5.4. Snapshot, time travel và compaction

Table format có thể giữ lịch sử snapshot để đọc lại phiên bản bảng ở thời điểm trước, so sánh dữ liệu qua lần cập nhật, hỗ trợ rollback/recovery trong phạm vi metadata và tệp được giữ, hoặc chạy incremental processing theo khả năng của format/engine.

Time travel **không thay thế backup độc lập**. Nếu tệp cũ đã được vacuum/expire/xóa theo lifecycle, snapshot cũ có thể không còn truy cập được. Retention cần cân bằng khả năng khôi phục, quy định lưu giữ, privacy deletion và chi phí.

Nhiều file nhỏ làm tăng overhead listing, planning, metadata và request storage. **Compaction** gom file thành kích thước phù hợp hơn, nhưng là workload ghi mới, cần kiểm soát xung đột, tài nguyên và snapshot. Chọn kích thước file dựa trên engine, storage và query; không áp một con số chung cho mọi nền tảng.

## 6. Ingestion và xử lý dữ liệu: batch, micro-batch, streaming

### 6.1. Batch ingestion

Batch gom dữ liệu theo khoảng thời gian hoặc khối công việc rồi nạp/xử lý. Ví dụ đồng bộ đơn hàng mỗi giờ hoặc xuất báo cáo lúc đêm.

Ưu điểm: đơn giản hơn về điều phối và kiểm thử; phù hợp dữ liệu không cần cập nhật tức thời; có thể tối ưu chi phí bằng lịch chạy và compute tạm thời; dễ chạy lại một khoảng thời gian nếu input được lưu và tác vụ idempotent.

Đánh đổi: độ trễ gồm thời gian chờ batch và xử lý; batch lớn tạo đỉnh compute/IO; job lỗi gần cuối có thể phải chạy lại nhiều dữ liệu nên cần checkpoint và khả năng resume.

### 6.2. Micro-batch

Micro-batch gom dữ liệu trong các cửa sổ nhỏ, ví dụ 30 giây hoặc 5 phút, rồi xử lý thành từng lô. Nó nằm giữa batch truyền thống và streaming event-by-event.

Phù hợp khi cần dashboard cập nhật gần thời gian thực nhưng không đòi hỏi latency vài mili giây. Cần xác định window, watermark, late-arriving data và cách cập nhật kết quả khi event cũ tới sau.

### 6.3. Streaming

Streaming xử lý event liên tục từ broker hoặc nguồn stream. Kiến trúc cần xác định:

- Producer, topic/partition, schema và thời gian sự kiện.
- Consumer group, offset/checkpoint và tiến độ xử lý.
- Thứ tự cần thiết, partition key và xử lý event trùng.
- Event-time hay processing-time; watermark và late events.
- Windowing, state store và recovery khi worker restart.
- Backpressure, lag, retention, DLQ và scaling.

**Exactly-once** phụ thuộc phạm vi hệ thống và semantics của engine/sink; không mặc nhiên có exactly-once end-to-end khi kết hợp broker, database và API bên ngoài. Thường phải thiết kế idempotent sink, transaction hoặc deduplication để đạt hiệu ứng nghiệp vụ đúng.

### 6.4. Chọn độ trễ theo nhu cầu

| Nhu cầu nghiệp vụ | Mẫu xử lý có thể chọn | Điều cần đo |
|---|---|---|
| Báo cáo tài chính theo ngày | Batch hằng ngày | Thời gian hoàn tất, completeness, khả năng rerun |
| Dashboard vận hành cập nhật vài phút | Micro-batch | Data freshness, window lag, chi phí job |
| Cảnh báo gian lận gần thời gian thực | Streaming | Event-to-alert latency, false positive, recovery |
| KPI marketing từ clickstream | Streaming hoặc micro-batch | Late event, dedup, session/window semantics |
| Huấn luyện mô hình hàng tuần | Batch data preparation | Dataset version, lineage, reproducibility |

Không chọn streaming chỉ vì “real-time nghe hiện đại”. Chi phí hạ tầng luôn chạy, quản lý state, vận hành, retry và debugging có thể không đáng khi nghiệp vụ chấp nhận trễ 15 phút.

## 7. Kiến trúc tham chiếu cho nền tảng dữ liệu cloud

### 7.1. Luồng từ nguồn đến sản phẩm dữ liệu

~~~mermaid
flowchart TB
    subgraph Sources[Data sources]
        OLTP[(Operational databases)]
        SAAS[SaaS / APIs]
        EVENTS[Events / Logs]
        FILES[Files / Partner feeds]
    end
    subgraph Ingestion[Ingestion layer]
        CDC[CDC connectors]
        BATCH[Batch loaders]
        STREAM[Stream broker]
    end
    OLTP --> CDC
    SAAS --> BATCH
    FILES --> BATCH
    EVENTS --> STREAM
    CDC --> RAW[(Raw object storage)]
    BATCH --> RAW
    STREAM --> RAW
    RAW --> TRANSFORM[Transform / Validate / Deduplicate]
    TRANSFORM --> SILVER[(Standardized tables)]
    SILVER --> CURATE[Business modeling]
    CURATE --> GOLD[(Curated data products)]
    GOLD --> WH[Warehouse / SQL serving]
    GOLD --> BI[BI / Semantic layer]
    SILVER --> ML[ML / Feature pipelines]
    CAT[Catalog + Lineage + Policy] -.-> RAW
    CAT -.-> SILVER
    CAT -.-> GOLD
    OBS[Logs / Metrics / Alerts] -.-> TRANSFORM
    OBS -.-> WH
~~~

Đây là mô hình logic có thể triển khai bằng nhiều dịch vụ cloud. Không nhất thiết phải có đủ mọi hộp; warehouse có thể trực tiếp phục vụ BI, lakehouse engine có thể query curated table mà không nạp vào warehouse riêng. Mỗi vùng phải có owner, SLA, schema, quyền và quy tắc xóa/retention.

### 7.2. Phân lớp trách nhiệm

| Lớp | Trách nhiệm | Câu hỏi vận hành |
|---|---|---|
| Source systems | Cung cấp dữ liệu và hợp đồng schema/change | Ai chịu trách nhiệm khi schema nguồn đổi? |
| Ingestion | Kết nối, checkpoint, retry, lưu dấu nhận dữ liệu | Làm sao tránh mất hoặc nhân đôi dữ liệu? |
| Storage | Durability, versioning, encryption, lifecycle | Dữ liệu nào giữ bao lâu và ở region nào? |
| Processing | Validation, transform, deduplicate, business logic | Job có idempotent, replay và test được không? |
| Catalog/governance | Discovery, schema, classification, lineage, policy | Ai được thấy và sử dụng dữ liệu? |
| Serving | SQL, BI, API, feature store hoặc export | SLO, concurrency và freshness là gì? |
| Observability | Job status, data freshness, quality, cost | Ai được cảnh báo và runbook ở đâu? |

### 7.3. Tách storage khỏi compute

Object storage và compute engine có thể mở rộng độc lập: dữ liệu lưu bền, compute bật theo job hoặc workload. Điều này linh hoạt nhưng không miễn phí:

- Mỗi query có thể phát sinh chi phí scan, request storage và compute.
- Nhiều engine đọc cùng dữ liệu cần quản lý concurrency, catalog và quyền thống nhất.
- Network egress giữa region/account/service có thể đáng kể.
- File format và partition quyết định lượng dữ liệu đọc; dữ liệu cột không tự tối ưu nếu query phải scan tất cả.
- Engine tạm thời cần bootstrap, cache và warm-up; job quá ngắn có thể bị overhead khởi tạo chi phối.

Thiết kế serving có thể tách workload BI, ML và data engineering để giới hạn blast radius. Không để một truy vấn phân tích không giới hạn chiếm toàn bộ tài nguyên phục vụ dashboard quan trọng.

## 8. Lược đồ dữ liệu, partitioning và chất lượng

### 8.1. Partition theo mẫu truy vấn

Partitioning giúp engine loại bỏ phần dữ liệu không cần đọc (partition pruning) nếu predicate khớp partition key. Ví dụ dữ liệu sự kiện theo ngày:

~~~text
s3://data-lake/events/
  event_date=2026-11-16/
  event_date=2026-11-17/
  event_date=2026-11-18/
~~~

Hoặc theo ngày và loại nguồn:

~~~text
.../event_date=2026-11-18/source=web/
.../event_date=2026-11-18/source=mobile/
~~~

Partition quá chi tiết tạo nhiều thư mục/file nhỏ và metadata; partition quá thô làm query quét dữ liệu không cần. Không partition theo user_id có cardinality rất cao nếu tạo hàng triệu partition. Chọn partition key từ access pattern, volume theo chu kỳ, khả năng prune và cách engine quản lý catalog.

### 8.2. File size và small files problem

Nhiều tệp nhỏ có thể khiến query phải liệt kê/đọc metadata lớn, mở nhiều file và tăng chi phí request. Compaction giảm overhead nhưng cần tài nguyên và phối hợp writer/reader.

Các biện pháp:

- Gom dữ liệu theo micro-batch hoặc buffer hợp lý trước khi ghi.
- Dùng compaction theo partition hoặc threshold, tránh chạy đồng loạt vào giờ cao điểm.
- Theo dõi số file, kích thước trung bình/p95, tỷ lệ file nhỏ và thời gian planning.
- Tránh một job ghi một file cho mỗi record hoặc mỗi partition quá nhỏ.
- Dùng table format/catalog để quản lý snapshot và metadata thay vì chỉ dựa vào prefix file.

### 8.3. Data quality và hợp đồng schema

| Chiều chất lượng | Câu hỏi | Ví dụ kiểm tra |
|---|---|---|
| Completeness | Có đủ bản ghi/field theo kỳ vọng? | Số record theo source/time window |
| Validity | Giá trị có thuộc miền hợp lệ? | Status trong enum, timestamp parse được |
| Uniqueness | Có trùng key logic không? | Deduplicate theo event_id/booking_id |
| Consistency | Các nguồn/field liên quan có mâu thuẫn? | Amount = quantity × price theo quy tắc |
| Timeliness | Dữ liệu đến đúng hạn? | Freshness lag, watermark |
| Accuracy | Có khớp nguồn chuẩn hoặc phép đối soát? | Reconciliation count/sum |

Không sửa dữ liệu lỗi âm thầm. Ghi nhận số lượng reject/quarantine, nguyên nhân, source, thời điểm và người xử lý. Dữ liệu lỗi có thể được cách ly để không chặn cả batch, nhưng không được bỏ mất mà không có metric và quy trình xử lý.

### 8.4. Schema evolution

Nguồn có thể thêm cột, đổi kiểu, đổi enum hoặc bỏ field. Nên có schema registry/catalog hoặc quy trình quản trị tương đương:

1. Gắn schema version và owner với nguồn.
2. Phân tích consumer có phụ thuộc field/semantics thay đổi không.
3. Ưu tiên thay đổi tương thích như thêm field optional có nghĩa rõ.
4. Với thay đổi phá vỡ, triển khai song song phiên bản/field, backfill và chuyển consumer theo lộ trình.
5. Kiểm tra dữ liệu cũ, dữ liệu mới, null và event đến muộn.
6. Chỉ bỏ field cũ sau khi consumer đã chuyển đổi và hết cửa sổ rollback.

Schema evolution không chỉ là parse. Thay đổi đơn vị tiền, timezone, ý nghĩa trạng thái hoặc grain của fact có thể khiến báo cáo sai dù job vẫn chạy thành công.

## 9. Catalog, governance và bảo mật dữ liệu

### 9.1. Data catalog và metadata

Catalog giúp người dùng tìm và hiểu dữ liệu. Metadata hữu ích gồm:

- Tên dataset/table, mô tả nghiệp vụ và owner.
- Schema, loại dữ liệu, partition và vị trí storage.
- Source system, thời điểm ingest, lịch cập nhật, freshness và SLA.
- Classification như public/internal/confidential/regulated.
- Lineage upstream/downstream, job tạo ra và consumer.
- Quyền truy cập, retention, quality score và trạng thái deprecated.

Catalog không thay thế enforcement. Ghi “PII” trong mô tả chưa tự ngăn analyst đọc field email; cần IAM/ACL, masking, row/column-level controls hoặc cơ chế tương ứng do nền tảng hỗ trợ.

### 9.2. Phân quyền theo danh tính và mục đích

- Workload ingestion chỉ được ghi vùng landing/raw tương ứng, không có quyền đọc toàn bộ curated data.
- Pipeline transform chỉ đọc vùng cần thiết và ghi dataset được giao.
- BI/analyst chỉ đọc data product phù hợp vai trò; PII cần quyền riêng hoặc masking.
- Service account/workload identity tách theo job và môi trường; tránh credential dùng chung lâu dài.
- Catalog, storage và query engine phải có chính sách nhất quán; không để truy cập trực tiếp object storage bypass quyền ở warehouse.
- Audit log cho hành động cấp quyền, truy vấn dữ liệu nhạy cảm, export và xóa.

### 9.3. Mã hóa, network và data residency

Thiết kế cloud cần xác định:

- TLS khi truyền từ source → ingestion → storage → engine.
- Encryption at rest và vòng đời KMS key, quyền decrypt.
- Private endpoint/VPC endpoint, egress restriction và kết nối cross-account.
- Region được phép lưu dữ liệu, nơi chạy compute và nơi tạo bản sao/backup.
- Quy trình xóa dữ liệu theo yêu cầu: raw, curated, cache, extract, backup và bản sao dẫn xuất.

Một bản sao Parquet hoặc snapshot có thể chứa PII ngay cả khi tên tệp không nói điều đó. Lineage và classification cần đi cùng lifecycle để xử lý truy cập, retention và xóa nhất quán.

### 9.4. Governance và ownership

| Vai trò | Trách nhiệm |
|---|---|
| Data owner | Định nghĩa mục đích, chất lượng, quyền và retention |
| Data steward | Metadata, glossary, classification, quy tắc chất lượng |
| Producer owner | Đảm bảo schema và nguồn dữ liệu |
| Pipeline owner | Vận hành ingest/transform, freshness, retry và khôi phục |
| Consumer owner | Sử dụng đúng ngữ nghĩa, quyền và giới hạn dataset |
| Platform/security | Dịch vụ nền, IAM, network, encryption, logging và policy |

Không để data catalog có hàng nghìn bảng nhưng không owner hoặc mô tả. Khi owner rời nhóm hoặc sản phẩm dừng, cần chuyển trách nhiệm hoặc đánh dấu dataset deprecated/retired với quy trình dữ liệu tương ứng.

## 10. Độ tin cậy, phục hồi và khả năng tái xử lý

### 10.1. Ingestion phải có thể resume

Một pipeline có thể mất kết nối giữa lúc đọc nguồn và ghi đích. Cần xác định:

- Watermark/offset/checkpoint được lưu ở đâu?
- Khi job retry, có thể ghi duplicate không?
- Dữ liệu tới muộn hoặc sai thứ tự được xử lý thế nào?
- Khi source schema đổi giữa job, job fail hay quarantine?
- Khi job chết sau khi ghi nhưng trước khi đánh dấu hoàn tất, làm sao tránh ghi trùng?

Giải pháp thường gồm idempotent write, staging + atomic commit hoặc table format transaction, event ID/dedup key, checkpoint bền và reconciliation với nguồn. Với database CDC, cần hiểu offset/log position và retention của transaction log; nếu consumer lag vượt retention, có thể phải bootstrap snapshot lại.

### 10.2. Data freshness và completeness

Freshness đo thời gian từ lúc sự kiện/dữ liệu phát sinh ở nguồn đến lúc có thể truy vấn ở lớp phục vụ:

~~~text
event_time        = thời điểm nghiệp vụ xảy ra
ingestion_time    = thời điểm nền tảng nhận dữ liệu
processed_time    = thời điểm pipeline hoàn tất
available_time    = thời điểm consumer có thể query kết quả

end-to-end freshness = available_time - event_time
~~~

Chỉ đo thời gian job chạy có thể bỏ qua thời gian dữ liệu nằm chờ ở source hoặc queue. Theo dõi thêm watermark, late events, số partition chậm, record quarantine và completeness theo cửa sổ.

### 10.3. Backup và disaster recovery

Object storage versioning, replication, table snapshot và warehouse backup có ngữ nghĩa khác nhau:

- Versioning hỗ trợ khôi phục phiên bản object theo khả năng dịch vụ nhưng không tự bảo đảm consistency giữa nhiều file thuộc một bảng.
- Replication có thể sao chép cả thao tác xóa hoặc dữ liệu đã bị hỏng logic.
- Snapshot/time travel phụ thuộc metadata và retention; vacuum/expire có thể xóa dữ liệu cũ.
- Backup warehouse có cách restore/clone/retention riêng của dịch vụ.

Xác định RTO/RPO cho raw, curated, catalog, pipeline state và serving layer. Thử khôi phục **một dataset hoàn chỉnh và metadata cần đọc nó**, không chỉ khôi phục một tệp. Phục hồi dữ liệu cần catalog, schema, encryption key, quyền và code/version pipeline tương thích.

### 10.4. Replay và reproducibility

Raw immutable hoặc source archive có thể cho phép chạy lại transform khi logic thay đổi. Để tái lập kết quả, lưu:

- Source snapshot/version hoặc offset và time window.
- Mã pipeline, tham số, dependency và phiên bản engine.
- Schema, business rule và reference data version.
- Thời gian chạy, checkpoint, output table snapshot và chất lượng đầu ra.

Không phải raw nào cũng cần lưu mãi. Replay phải tuân thủ retention và quyền xóa dữ liệu; dữ liệu nhạy cảm được xóa theo yêu cầu có thể khiến tái lập đầy đủ không còn được phép.

## 11. Hiệu năng và chi phí trên nền tảng dữ liệu cloud

### 11.1. Tối ưu theo lượng dữ liệu thực sự đọc

Chi phí query có thể phụ thuộc bytes scanned, compute time, concurrency, storage request hoặc mức tài nguyên cấp phát. Các kỹ thuật:

- Columnar format và projection pruning: chỉ đọc cột cần thiết.
- Predicate pushdown: lọc gần nguồn dữ liệu khi engine hỗ trợ.
- Partition pruning: chỉ đọc partition phù hợp.
- Compression: giảm dung lượng I/O, cân nhắc CPU giải nén.
- Statistics/catalog: giúp planner ước lượng và chọn plan.
- Materialized view/aggregate table: giảm tính toán lặp cho dashboard phổ biến.
- Cache: cải thiện truy vấn lặp nhưng cần freshness và invalidation.
- Workload isolation/resource group: tránh query lớn chiếm toàn bộ compute.

Ví dụ: dashboard chỉ cần 5 cột trong bảng 80 cột và lọc 2 ngày dữ liệu trong 1 năm. Parquet + partition theo ngày + projection/filter pushdown có thể giảm bytes đọc đáng kể so với scan toàn bộ. Hiệu quả thực tế phải đo bằng bytes scanned, plan và chi phí.

### 11.2. Ước tính chi phí

~~~text
TCO dữ liệu ≈
    storage (raw + curated + snapshots + versions)
  + ingestion (connectors, broker, API calls, egress)
  + compute (batch, streaming, SQL, ML)
  + catalog/governance/observability
  + backup/replication/DR
  + vận hành, bảo mật và nhân lực
~~~

Ví dụ giả định: lake lưu 10 TB raw, thêm 4 TB cleaned/curated và 3 TB phiên bản/snapshot; tổng logical storage khoảng 17 TB trước khi tính compression/dedup và cách tính của nhà cung cấp. Nếu giữ nhiều snapshot, compaction tạm thời và bản sao region, dung lượng tính phí thực tế có thể cao hơn. Không lấy 10 TB raw làm toàn bộ dự toán.

### 11.3. Nguồn chi phí hay bị bỏ sót

| Nguồn | Cách phát sinh | Kiểm soát |
|---|---|---|
| Small files/listing | Nhiều object nhỏ, planning và request overhead | Compaction, batching, theo dõi số file |
| Query scan | Quét partition/cột không cần | Parquet/ORC, pruning, query guardrail |
| Streaming compute | Worker luôn chạy, idle capacity | Autoscale/scale-to-zero khi phù hợp, batching |
| Data egress | Đọc giữa region, account hoặc Internet | Đặt compute gần storage, network cost review |
| Snapshot/version | Dữ liệu lịch sử, delete files, retention | Lifecycle và snapshot expiration theo policy |
| Log/trace | Job/query log dung lượng lớn | Sampling, retention, che dữ liệu nhạy cảm |
| Failed jobs/retry | Lặp scan/compute do lỗi | Idempotency, checkpoint, retry giới hạn |
| Replication/DR | Bản sao vùng và cross-region | Thiết kế theo RPO/RTO và kiểm tra chi phí |

### 11.4. Chargeback/showback và FinOps

Gắn owner, domain, environment, data product, cost center và pipeline ID vào metadata/cost tags khi nền tảng hỗ trợ. Đối chiếu chi phí theo dataset/table/storage prefix, job/pipeline/compute pool, query/workload/warehouse, region/network egress, retention/snapshot/version/lifecycle.

Không nhất thiết chargeback mọi chi phí chính xác đến từng user; showback theo domain hoặc product thường đủ để bắt đầu. Quan trọng là có owner phản hồi khi storage/query tăng bất thường.

## 12. Data products và tầng phục vụ

Curated data nên được xem như **data product** có người dùng và hợp đồng rõ:

- Tên và mô tả nghiệp vụ; grain và semantics của metric.
- Owner, steward, source lineage và consumer được phép.
- Schema/version, lịch cập nhật, freshness/SLO và quality score.
- Quyền truy cập, classification, retention và cách yêu cầu quyền.
- Cách sử dụng: BI semantic layer, SQL endpoint, API hoặc export.

Ví dụ data product booking_daily_metrics định nghĩa một dòng theo ngày, region và service category; booking_count đếm booking đã xác nhận theo thời điểm snapshot; gross_amount xác định đơn vị tiền, cách xử lý refund và timezone. Nếu không có semantics này, hai dashboard có thể dùng cùng tên KPI nhưng cho kết quả khác nhau.

Một semantic layer có thể tập trung định nghĩa metric và quyền, tránh mỗi dashboard tự viết logic riêng. Tuy nhiên nó không thay thế kiểm tra dữ liệu nguồn, lineage và chất lượng.

## 13. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi với lake/warehouse/lakehouse | Bằng chứng |
|---|---|---|
| **Operational Excellence** | Pipeline có owner, retry, replay, lineage, runbook và deployment version không? | Job SLO, runbook, lineage, CI/CD, diễn tập replay |
| **Security** | Danh tính, encryption, PII, network và quyền truy vấn có được kiểm soát xuyên các engine không? | IAM/ACL test, audit, masking, access review |
| **Reliability** | Ingestion có resume, output có transaction/atomicity, backup/restore có đạt RTO/RPO? | CDC checkpoint, failure test, restore drill |
| **Performance Efficiency** | Partition, file layout, format, query engine và workload isolation có phù hợp? | Bytes scanned, p95 query, streaming lag, file metrics |
| **Cost Optimization** | Storage, query, compute, egress, snapshot và retry có owner/budget? | Cost dashboard, showback, lifecycle, query cost |
| **Sustainability** | Có tránh scan/lưu trữ dư thừa, tắt compute nhàn rỗi, xóa dữ liệu hết hạn? | Utilization, scan efficiency, retention compliance |

Không chọn lakehouse chỉ vì có nhiều tính năng, hoặc warehouse chỉ vì SQL tiện. Hãy cân bằng tổng chi phí sở hữu, khả năng vận hành, tính di động, yêu cầu dữ liệu và năng lực đội ngũ.

## 14. Quy trình chọn mô hình phù hợp

1. **Xác định mục tiêu:** BI, ad hoc analytics, ML, dashboard gần real-time, audit hoặc chia sẻ dữ liệu.
2. **Lập inventory nguồn:** định dạng, volume, velocity, schema, quyền, vị trí và owner.
3. **Xác định SLO dữ liệu:** freshness, completeness, query latency, concurrency, RTO/RPO và retention.
4. **Liệt kê access pattern:** SQL, scan, join, upsert, streaming, replay, file access và chia sẻ.
5. **So sánh lake/warehouse/lakehouse:** storage, transaction, engine, governance và chi phí.
6. **Thử workload đại diện:** ingest thực, query thật, dữ liệu có skew, concurrency, late events và failure.
7. **Thiết kế security/governance:** catalog, IAM, data classification, lineage và xóa dữ liệu.
8. **Ước tính TCO:** storage, compute, egress, snapshots, logging, backup và effort vận hành.
9. **Ghi ADR và roadmap:** quyết định ban đầu, giới hạn, trigger đánh giá lại và cách di chuyển.

### 14.1. Ma trận chọn nhanh

| Nhu cầu nổi bật | Mô hình thường đáng xem xét đầu tiên | Lưu ý |
|---|---|---|
| Lưu dữ liệu thô đa dạng, dài hạn, ML/exploration | Data lake | Cần đầu tư catalog, schema, quality và policy |
| BI/SQL có mô hình ổn định, metric chuẩn | Data warehouse | Tính compute/concurrency và portability |
| Nhiều engine cùng dùng bảng trên object storage, cần transaction/update | Lakehouse | Xác minh table format/catalog/engine compatibility |
| Chỉ vài báo cáo từ database nhỏ | Replica/warehouse nhỏ hoặc query service đơn giản | Có thể chưa cần lake/lakehouse |
| Event real-time với stateful processing | Streaming platform kết hợp lake/warehouse/lakehouse | Đánh giá broker, checkpoint và sink semantics |

### 14.2. Ví dụ ADR chọn kiến trúc

~~~text
ADR-DP-003: Xây dựng curated analytics trên lakehouse

Bối cảnh:
- Nguồn dữ liệu gồm relational DB, event và file đối tác.
- Data engineering, BI và ML cần dùng một số bộ dữ liệu chung.
- Raw data phải lưu được để replay; curated data cần SQL và cập nhật có kiểm soát.

Lựa chọn:
A. Chỉ data lake + query engine.
B. Nạp toàn bộ dữ liệu vào warehouse.
C. Object storage + open table format + catalog + nhiều engine.

Quyết định minh họa: C cho dữ liệu curated dùng chung;
raw giữ ở vùng lưu trữ riêng; warehouse vẫn được cân nhắc
cho workload BI có SLO/concurrency đặc thù.

Lý do:
- Hỗ trợ nhiều engine và giữ dữ liệu nền trên object storage.
- Table metadata/transaction giúp quản lý cập nhật và snapshot.

Đánh đổi:
- Cần kiểm thử compatibility, catalog, commit concurrency,
  compaction, governance và vận hành.
- Không tự động loại bỏ cloud/provider coupling.

Kiểm chứng:
- So sánh query/ingest với workload đại diện.
- Thử writer concurrency, schema evolution và replay.
- Thử quyền truy cập qua từng engine.
- Đo bytes scanned, freshness, storage, compute, egress và TCO.

Xem xét lại khi:
- SLO, engine ecosystem, team skill hoặc chi phí đổi đáng kể.
~~~

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Xem data lake chỉ là bucket chứa file | Data swamp, khó tìm và khó quản trị | Catalog, owner, zones, schema, lineage, quality |
| Đưa mọi báo cáo lên database OLTP | Tranh chấp tài nguyên với request người dùng | Replica, warehouse hoặc workload tách biệt |
| Chọn warehouse/lakehouse trước khi hiểu access pattern | Chi phí và độ phức tạp không cần thiết | Làm rõ user, query, freshness, volume |
| Nghĩ Parquet tự cung cấp transaction | Ghi đồng thời hoặc đọc snapshot không nhất quán | Table format/catalog/commit semantics |
| Nghĩ lakehouse loại bỏ mọi vendor lock-in | Phụ thuộc connector, IAM, catalog, engine vẫn tồn tại | Compatibility matrix và portability test |
| Streaming cho dữ liệu không cần realtime | Chi phí và vận hành cao | Batch/micro-batch khi SLO cho phép |
| Partition theo key có cardinality quá cao | Quá nhiều partition/file nhỏ | Chọn grain từ volume và query predicate |
| Không xử lý late/duplicate events | KPI sai, record trùng | Watermark, event ID, dedup/reconciliation |
| Giữ snapshot vô thời hạn | Storage tăng, retention/privacy khó đáp ứng | Snapshot expiration và policy |
| Chỉ backup file mà quên catalog/code/key | Khôi phục dữ liệu không dùng được | Backup metadata, pipeline, IAM và encryption key |
| Không phân quyền thống nhất giữa engine/storage | Bypass governance và lộ dữ liệu | Policy xuyên catalog, object storage và query engine |
| Chỉ đo job success, không đo freshness/quality | Job xanh nhưng dữ liệu thiếu/cũ | Data SLO, reconciliation, freshness và quality checks |

## 16. Bài thực hành: thiết kế data platform cho dịch vụ đặt lịch

**Tình huống:** Một nền tảng đặt lịch có relational database phục vụ API, event booking, log web/mobile và file đối tác. Nhóm sản phẩm cần dashboard vận hành cập nhật trong vòng 5 phút; tài chính cần báo cáo chính xác theo ngày; data science cần lịch sử dữ liệu để xây mô hình dự báo nhu cầu. Dữ liệu có PII và phải giới hạn truy cập. Hiện chưa xác định volume thực tế, chi phí mục tiêu hoặc engine cụ thể.

Hãy xây dựng đề xuất gồm:

1. **Phân loại workload:** xác định dashboard 5 phút, báo cáo ngày và ML lịch sử cần freshness/consistency khác nhau thế nào.
2. **Source inventory:** ghi nguồn, schema, volume/velocity, owner, classification, retention và cách ingest.
3. **So sánh ba mô hình:** đề xuất vai trò của lake, warehouse và lakehouse; nêu phần nào nên dùng chung, phần nào không cần ép vào một mô hình.
4. **Sơ đồ kiến trúc:** thể hiện ingestion batch/CDC/stream, raw/clean/curated, catalog, governance, SQL/BI/ML và observability.
5. **Định dạng/partition:** chọn CSV/JSON/Avro/Parquet hoặc table format cho từng vùng; xác định partition và chiến lược compaction.
6. **Data quality/schema:** quy định dedup, late events, schema evolution, quarantine và reconciliation.
7. **Security:** phân quyền ingestion/analyst/ML, masking PII, encryption, private network, audit và retention.
8. **Reliability:** thiết kế checkpoint, replay, idempotency, backup/restore và RTO/RPO theo loại dữ liệu.
9. **Cost model:** tính storage raw/curated/snapshot, compute theo job/query, egress, logging và backup; nêu cách showback.
10. **ADR và kiểm thử:** chọn một kiến trúc, nêu phương án thay thế, thử query/ingestion/failure và trigger đánh giá lại.

| Data product | Consumer | Freshness mục tiêu | Storage/model | Quyền | Kiểm chứng |
|---|---|---|---|---|---|
| booking_ops_5min | Operations | ≤ 5 phút (giả định) | Curated table + SQL/BI | Operations role, PII tối thiểu | Event lag, completeness |
| booking_finance_daily | Finance | Hoàn thành trước giờ báo cáo ngày | Warehouse/lakehouse curated | Finance role, audit | Reconciliation count/sum |
| booking_history_ml | Data Science | Batch theo ngày/tuần | Lake/lakehouse lịch sử | ML role, masking | Dataset version, lineage |

**Tiêu chí hoàn thành:** Người review hiểu dữ liệu đi từ nguồn nào đến consumer nào, mỗi vùng giữ dữ liệu gì, cách xử lý event trùng/muộn, ai được truy cập, phục hồi thế nào và chi phí chính được đo ở đâu. Mục tiêu chưa có số liệu phải được ghi là giả định cần xác minh.

## 17. Khung ghi nhớ

- **Data lake** ưu tiên lưu dữ liệu đa dạng ở quy mô lớn, giữ dữ liệu gần nguyên bản và cho phép nhiều kiểu xử lý.
- **Data warehouse** ưu tiên dữ liệu đã được mô hình hóa, truy vấn SQL/BI và metric có quản trị.
- **Lakehouse** bổ sung lớp quản lý bảng, metadata và transaction trên storage mở để nhiều engine dùng chung dữ liệu; mức hỗ trợ tùy hệ sinh thái.
- **File format khác table format:** Parquet tổ chức dữ liệu trong file; Iceberg/Delta/Hudi quản lý bảng, snapshot và transaction semantics.
- **Batch, micro-batch và streaming** được chọn theo độ trễ nghiệp vụ, độ phức tạp và chi phí vận hành.
- **Governance đi cùng dữ liệu:** catalog, owner, classification, IAM, lineage, quality, retention và audit phải bao phủ mọi engine.
- **Đo toàn hệ thống:** freshness, completeness, query performance, bytes scanned, storage, compute, egress và khả năng replay/restore.

Một nền tảng dữ liệu cloud tốt không phải nơi lưu được nhiều tệp nhất hay có nhiều engine nhất. Đó là kiến trúc giúp tổ chức đưa dữ liệu đúng, đủ, an toàn và đúng thời điểm tới người cần dùng, với chi phí và độ phức tạp vận hành có thể giải thích, đo lường và cải tiến.
