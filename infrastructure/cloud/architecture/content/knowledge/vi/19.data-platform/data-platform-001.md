# Tách xử lý giao dịch khỏi phân tích dữ liệu

Một ứng dụng cloud thường phải đáp ứng hai nhu cầu dữ liệu khác nhau. Nghiệp vụ trực tuyến cần tạo đơn, cập nhật thanh toán, giữ tồn kho hoặc tra cứu trạng thái với độ trễ thấp và tính đúng đắn cao. Trong khi đó, bộ phận phân tích cần tổng hợp hàng triệu giao dịch, tính xu hướng theo tháng, xây dashboard, dự báo nhu cầu và kết hợp dữ liệu từ nhiều hệ thống. Nếu cả hai nhóm workload dùng chung database và tài nguyên mà không có ranh giới, truy vấn phân tích nặng có thể làm chậm giao dịch, còn những thay đổi tối ưu cho giao dịch có thể khiến việc phân tích khó khăn.

**Tách xử lý giao dịch khỏi phân tích dữ liệu** là quyết định kiến trúc nhằm cô lập workload, lưu dữ liệu theo cách phù hợp với từng mục đích và đồng bộ dữ liệu giữa các hệ thống theo hợp đồng rõ ràng. Mô hình thường kết hợp database giao dịch (OLTP), cơ chế thu thập thay đổi dữ liệu (CDC), pipeline ETL/ELT, data lake hoặc data warehouse, lớp mô hình hóa và nền tảng phục vụ phân tích.

Bài học thuộc chương **Nền tảng dữ liệu** trong lộ trình **Cloud Architecture**: học cách thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ tới mạng, compute, dữ liệu và mô hình triển khai, đồng thời cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Tách workload không có nghĩa dữ liệu tự đồng bộ tức thời hoặc bản sao phân tích luôn đúng; kiến trúc phải xác định freshness, lineage, chất lượng, quyền truy cập và phục hồi.

Sau bài học, bạn có thể:

- Phân biệt OLTP và OLAP theo workload, data model, latency và transaction semantics.
- Giải thích vì sao truy vấn phân tích có thể ảnh hưởng database giao dịch.
- Thiết kế luồng dữ liệu từ nguồn OLTP qua CDC/ETL/ELT tới lake, warehouse và serving layer.
- Chọn batch, micro-batch hoặc streaming theo freshness và chi phí.
- Xác định schema, partitioning, data quality, lineage và data governance.
- Bảo vệ dữ liệu nhạy cảm khi sao chép và cung cấp cho phân tích.
- Đặt SLO cho pipeline, freshness, completeness và phục hồi dữ liệu.
- Đánh giá trade-off giữa isolation, độ phức tạp, chi phí và khả năng vận hành.

## 1. Hai nhóm workload: OLTP và OLAP

**OLTP (Online Transaction Processing)** phục vụ giao dịch nghiệp vụ đang diễn ra. Mỗi thao tác thường đọc hoặc cập nhật một số bản ghi có chọn lọc, cần phản hồi nhanh và phải duy trì invariant dữ liệu.

Ví dụ: tạo booking và kiểm tra khả dụng tài sản; ghi nhận thanh toán hoặc hoàn tiền; cập nhật trạng thái giao nhận; kiểm tra quyền và thông tin tài khoản; giảm tồn kho trong một transaction.

**OLAP (Online Analytical Processing)** phục vụ phân tích trên tập dữ liệu lớn, thường đọc nhiều bản ghi, join, group, aggregate và tính toán theo thời gian. Ví dụ: tổng doanh thu theo khu vực/tháng/loại thiết bị; tỷ lệ hủy đơn; phân tích vòng đời khách hàng; so sánh nhu cầu theo mùa; xây tập dữ liệu dự báo và machine learning.

| Tiêu chí | OLTP | OLAP |
| --- | --- | --- |
| Mục tiêu | Xử lý nghiệp vụ trực tuyến | Phân tích và hỗ trợ quyết định |
| Mẫu truy cập | Nhiều request nhỏ, point lookup và update | Scan, join, aggregate nhiều dữ liệu |
| Đơn vị công việc | Transaction ngắn | Query/job có thể chạy lâu |
| Độ trễ | Thường từ mili giây đến vài trăm mili giây tùy use case | Từ giây tới phút hoặc lâu hơn |
| Ghi dữ liệu | Nhiều thao tác nhỏ, liên tục | Nạp batch, stream hoặc micro-batch |
| Mô hình | Thường chuẩn hóa, bảo vệ tính toàn vẹn | Dimension, fact, denormalized hoặc dạng phù hợp query |
| Đồng thời | Nhiều transaction cạnh tranh row/lock/connection | Ít query hơn nhưng mỗi query có thể tiêu thụ nhiều CPU/I/O |
| Nhất quán | Transaction và invariant nghiệp vụ | Có thể eventual consistent theo freshness SLO |
| Người dùng | Ứng dụng, khách hàng, nhân viên vận hành | Analyst, BI, data scientist, lãnh đạo |
| Tối ưu | Transaction latency, throughput, availability | Scan throughput, query latency và cost |

Các mốc thời gian chỉ mang tính định hướng. Dashboard có thể cần response dưới vài giây, còn job huấn luyện có thể chạy hàng giờ. OLTP cũng không có một latency target chung cho mọi transaction.

### 1.1. Vì sao không nên mặc định dùng một database cho tất cả?

Một query phân tích có thể đọc hàng trăm triệu dòng, giữ tài nguyên lâu, tạo sort/hash lớn hoặc dùng I/O đáng kể. Trong lúc đó, transaction OLTP vẫn cần connection, cache page, CPU và disk latency ổn định.

Nếu báo cáo chạy vào giờ cao điểm, CPU database tăng, transaction chờ lâu hơn, buffer/cache bị thay thế bởi page của scan, connection pool bị chiếm bởi query lâu, lock hoặc contention tăng. Một dashboard lỗi hoặc truy vấn không giới hạn có thể tạo hiệu ứng ảnh hưởng toàn ứng dụng.

Tách workload giúp database giao dịch tập trung bảo đảm nghiệp vụ, còn hệ thống phân tích dùng storage và compute phù hợp cho scan và aggregate.

## 2. Ranh giới kiến trúc dữ liệu

Một data platform không nhất thiết là một sản phẩm đơn lẻ. Nó gồm những vùng có trách nhiệm riêng: hệ thống nguồn, ingestion, lưu trữ, chuyển đổi, quản trị và serving.

~~~mermaid
flowchart LR
    subgraph SOURCES["Nguồn dữ liệu nghiệp vụ"]
        OLTP[("OLTP databases")]
        APP["Application events"]
        EXT["External systems / files"]
    end
    SOURCES --> ING["Ingestion: CDC / batch / stream"]
    ING --> RAW[("Raw data lake / landing zone")]
    RAW --> TRANS["Transform / quality / governance"]
    TRANS --> WH[("Warehouse / curated lakehouse")]
    WH --> BI["BI / dashboards"]
    WH --> DS["Data science / ML"]
    WH --> API["Analytical APIs / extracts"]
~~~

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| OLTP source | Nguồn có thẩm quyền cho trạng thái giao dịch | Booking DB, Payment DB |
| Ingestion | Thu nhận snapshot hoặc thay đổi | CDC connector, event consumer, file ingestion |
| Landing/raw zone | Giữ dữ liệu gần nguồn và metadata nạp | Object storage raw bucket |
| Processing | Parse, validate, deduplicate, transform | Stream processor, SQL ELT, Spark job |
| Curated layer | Dữ liệu đã chuẩn hóa và kiểm tra | Warehouse tables, lakehouse tables |
| Semantic/serving | Định nghĩa metric và phục vụ query | BI semantic model, analytical API |
| Governance | Quyền, lineage, catalog, retention và quality | Data catalog, policy engine |

Không nên để công cụ BI truy cập trực tiếp database production với quyền query tự do. Nếu có trường hợp cần tra cứu đặc biệt, phải giới hạn query, quyền, concurrency và ảnh hưởng tải.

## 3. Hợp đồng dữ liệu giữa OLTP và nền tảng phân tích

Tách workload không tự giải quyết việc dữ liệu có đúng, đầy đủ và dễ hiểu hay không. Trước khi xây pipeline, cần thống nhất hợp đồng dữ liệu.

Một data contract nên xác định:

- **Owner:** đội hoặc domain chịu trách nhiệm về ý nghĩa dữ liệu.
- **Schema:** tên trường, kiểu, nullability, enum và cấu trúc.
- **Semantics:** trường thể hiện sự kiện hay trạng thái hiện tại; đơn vị tiền, timezone và business definition.
- **Primary/business key:** cách nhận diện bản ghi hoặc đối tượng.
- **Change behavior:** insert, update, delete, tombstone, correction và late arrival.
- **Versioning:** cách thêm/bỏ field và khả năng tương thích.
- **Freshness:** dữ liệu phải tới lớp phân tích trong bao lâu.
- **Quality rules:** uniqueness, completeness, referential integrity và valid range.
- **Security classification:** PII, confidential, public hoặc dữ liệu hạn chế.
- **Retention:** thời gian giữ raw, curated và derived data.

Ví dụ, trường amount không đủ rõ nếu thiếu currency, dấu âm/dương, trạng thái giao dịch và quy tắc gross/net. Analyst có thể tạo metric doanh thu sai dù pipeline chạy thành công.

### 3.1. Trạng thái hiện tại và lịch sử sự kiện

Có hai cách phổ biến đưa dữ liệu OLTP sang phân tích:

1. **Snapshot/current-state:** mỗi lần trích xuất lấy trạng thái hiện tại của bảng. Phù hợp khi chỉ cần dữ liệu mới nhất và chấp nhận chu kỳ cập nhật.
2. **Change/event history:** truyền các thay đổi theo thời gian. Phù hợp khi cần lịch sử, incremental processing hoặc dựng lại thời điểm quá khứ.

Snapshot hiện tại không cho biết mọi transition đã xảy ra. Nếu cần phân tích vòng đời đơn hoặc lịch sử trạng thái, cần CDC đủ chi tiết, business events hoặc một nguồn lịch sử khác.

## 4. Ingestion: batch, micro-batch, streaming và CDC

### 4.1. Batch ingestion

Batch trích xuất dữ liệu theo lịch: mỗi giờ, mỗi ngày hoặc theo cửa sổ nghiệp vụ. Ưu điểm là triển khai thường đơn giản, có thể tối ưu scan và bulk load, dễ lập lịch và chạy lại theo partition. Đánh đổi là dữ liệu cũ cho tới batch tiếp theo; snapshot lớn có thể gây tải nguồn; batch thất bại làm chậm cả cửa sổ; incremental extraction cần watermark đáng tin cậy.

### 4.2. Micro-batch

Micro-batch xử lý nhóm dữ liệu nhỏ theo chu kỳ ngắn hơn, ví dụ mỗi 1–5 phút. Đây có thể là thỏa hiệp giữa độ tươi và độ phức tạp vận hành. Cần xác định cách đóng batch, retry, chống nạp trùng và xử lý khoảng thời gian batch bị bỏ lỡ. Scheduler chạy xong không chứng minh mọi record trong khoảng đó đã tới.

### 4.3. Streaming ingestion

Streaming xử lý dữ liệu liên tục hoặc theo cửa sổ rất ngắn, phù hợp khi sự kiện cần xuất hiện nhanh trong dashboard/cảnh báo. Đổi lại, cần quản lý partition, offset/checkpoint, late event, ordering, backpressure, replay và vận hành consumer.

### 4.4. Change Data Capture (CDC)

CDC ghi nhận thay đổi từ nguồn dữ liệu, thường dựa vào transaction log hoặc cơ chế tương đương. Thay vì quét toàn bảng thường xuyên, connector đọc insert/update/delete để đưa tới downstream.

~~~mermaid
sequenceDiagram
    participant A as OLTP application
    participant DB as Transactional database
    participant C as CDC connector
    participant B as Broker
    participant L as Data lake / warehouse
    A->>DB: Commit transaction
    DB->>DB: Append database log
    C->>DB: Read log position
    DB-->>C: Change records
    C->>B: Publish changes
    B-->>L: Consume and apply
    L->>L: Update curated tables
~~~

CDC có thể giảm query overhead so với polling bảng, nhưng không miễn phí. Connector cần quyền đọc log, replication slot hoặc retention phù hợp, theo dõi lag và xử lý schema change. Nếu connector dừng lâu, log cần thiết có thể bị dọn hoặc vùng lưu log tăng nhanh tùy engine.

### 4.5. So sánh ingestion

| Phương pháp | Freshness thường gặp | Độ phức tạp | Trường hợp phù hợp |
| --- | --- | --- | --- |
| Batch | Phút đến ngày | Thấp đến vừa | Báo cáo định kỳ, dữ liệu ít thay đổi |
| Micro-batch | Vài phút | Vừa | Dashboard thường xuyên nhưng không cần event tức thời |
| Streaming | Giây hoặc gần realtime | Cao | Cảnh báo, telemetry, event analytics |
| CDC | Có thể gần realtime, phụ thuộc connector/downstream | Vừa đến cao | Đồng bộ thay đổi từ database |
| Full snapshot | Theo chu kỳ trích xuất | Thấp lúc đầu, có thể tốn nguồn | Dataset nhỏ hoặc tải đầu ban đầu |

Đây là phạm vi minh họa, không phải bảo đảm của nhà cung cấp. Chọn theo freshness SLO, khả năng nguồn, chi phí và năng lực vận hành.

## 5. CDC không đồng nghĩa với business event

CDC thường phản ánh thay đổi ở mức database record: bảng nào đổi, cột nào đổi, before/after image và log position tùy hệ thống. Business event mô tả ý nghĩa nghiệp vụ: BookingConfirmed, RefundCompleted, AssetReturned.

Ví dụ một lần xác nhận booking có thể cập nhật ba bảng và CDC phát ra ba change records. Một business event có thể gói ý nghĩa rằng đơn đã được xác nhận sau khi invariant liên quan hoàn tất.

| Đặc điểm | CDC record | Business event |
| --- | --- | --- |
| Nguồn | Database log/table mutation | Domain/application logic |
| Ngữ nghĩa | Kỹ thuật, phản ánh thay đổi lưu trữ | Nghiệp vụ, phản ánh điều đã xảy ra |
| Độ gắn kết schema | Gắn với schema database | Gắn với contract nghiệp vụ |
| Phù hợp | Replication, ingestion, downstream sync | Integration, workflow, business analytics |
| Rủi ro | Schema nội bộ đổi làm consumer bị ảnh hưởng | Producer cần định nghĩa event đúng |

Có thể dùng CDC cho ingestion phân tích, nhưng nếu cần hiểu vì sao một quyết định nghiệp vụ xảy ra, business event có thể mang ngữ nghĩa tốt hơn. Không suy luận transition nghiệp vụ chỉ từ một record update nếu không có logic tương quan đủ tin cậy.

## 6. ETL và ELT

- **ETL (Extract, Transform, Load):** trích xuất dữ liệu, chuyển đổi ở processing engine rồi nạp kết quả vào destination.
- **ELT (Extract, Load, Transform):** nạp dữ liệu vào nền tảng đích trước, sau đó dùng compute của warehouse/lakehouse để chuyển đổi.

| Tiêu chí | ETL | ELT |
| --- | --- | --- |
| Biến đổi | Trước khi nạp | Sau khi nạp raw/landing |
| Nền tảng tính toán | ETL engine riêng hoặc managed service | Warehouse/lakehouse compute |
| Raw data | Có thể chỉ giữ một phần tùy pipeline | Thường giữ raw để transform lại |
| Linh hoạt | Phụ thuộc logic trước nạp | Dễ tạo model mới từ raw nếu còn dữ liệu |
| Chi phí | Compute processing và data movement | Storage raw plus compute đích |
| Phù hợp | Mask/tokenize trước khi landing, tích hợp nhiều nguồn | Analytics SQL, ELT trong warehouse/lakehouse |

Hai mô hình có thể kết hợp. Ví dụ phải loại bỏ hoặc token hóa PII trước khi đưa dữ liệu sang vùng phân tích dùng chung, rồi thực hiện transform nghiệp vụ sau khi load.

## 7. Data lake, warehouse và lakehouse

### 7.1. Data lake

Data lake thường lưu dữ liệu trên object storage với nhiều định dạng và mức xử lý: raw, cleaned, curated, logs, events, semi-structured và unstructured.

Ưu điểm là lưu được nhiều dạng dữ liệu và quy mô lớn, giữ raw để xử lý lại, tách storage khỏi compute và linh hoạt cho data science/ML. Đánh đổi là thiếu catalog/schema/ownership/quality có thể biến lake thành data swamp; query performance phụ thuộc format, partition, file sizing và metadata; quyền object-level/column-level cần thiết kế rõ.

### 7.2. Data warehouse

Data warehouse tối ưu cho query phân tích có cấu trúc, thường cung cấp SQL engine, quản lý compute và concurrency. Ưu điểm là tổ chức BI, join và aggregate dễ, schema/semantic model rõ, quản lý workload nhiều người dùng. Đánh đổi là compute cost có thể tăng theo query/concurrency; dữ liệu phi cấu trúc có thể cần chuyển đổi; cách tính giá và mức lock-in khác nhau theo nhà cung cấp.

### 7.3. Lakehouse

Lakehouse kết hợp object storage/lake với transaction table format, catalog và query engine để có đặc tính quản lý bảng gần warehouse hơn. Một số ecosystem hỗ trợ schema evolution, table transactions, time travel hoặc metadata management, nhưng tính năng cụ thể phụ thuộc table format và engine.

Không xem lakehouse tự động giải quyết mọi vấn đề của lake và warehouse. Cần xác minh compatibility giữa writer/reader engines, transaction isolation, concurrency, compaction và catalog.

| Tiêu chí | Data lake | Data warehouse | Lakehouse |
| --- | --- | --- | --- |
| Dữ liệu | Structured, semi/unstructured | Chủ yếu structured/curated | Structured và nhiều dạng qua table/lake |
| Storage | Object storage | Managed storage | Object storage + table metadata |
| Query | Nhiều engine | SQL analytics tích hợp | SQL/compute engine tương thích |
| Schema | Có thể schema-on-read | Schema quản lý chặt | Schema/table metadata |
| Use case | Raw archive, data science, files | BI, metric, analytics | Unified analytics khi ecosystem hỗ trợ |
| Vận hành | Catalog, format, partition, lifecycle | Warehouse workload/cost management | Compatibility, catalog, compaction, concurrency |

## 8. Tầng dữ liệu: raw, cleaned và curated

Một cấu trúc phân lớp giúp phân biệt dữ liệu gần nguồn, dữ liệu đã chuẩn hóa và dữ liệu sẵn sàng phục vụ quyết định.

- **Raw/landing:** lưu dữ liệu gần dạng nguồn nhất có thể, cùng source, ingestion time, batch ID, schema version và checksum. Raw cần được bảo vệ, phân quyền và retention rõ; không nhất thiết phải giữ nguyên PII đầy đủ.
- **Cleaned/standardized:** chuẩn hóa kiểu dữ liệu, timezone, đơn vị đo, mã quốc gia, currency và schema; xử lý duplicate, record không hợp lệ và late arrival; giữ lineage về raw để điều tra.
- **Curated/serving:** mô hình hóa theo use case: fact/dimension, aggregate, data mart hoặc bảng dashboard. Metric phải có định nghĩa chung như gross revenue, net revenue, cancelled booking và active customer.

~~~mermaid
flowchart TB
    S["Source systems"] --> R["Raw / landing"]
    R --> C["Cleaned / standardized"]
    C --> D["Curated / data marts"]
    D --> M["Semantic metrics"]
    M --> B["BI / analytics / ML"]
    R -. "Lineage and replay" .-> C
~~~

Tên lớp có thể khác giữa tổ chức. Quan trọng là biết dữ liệu đang ở trạng thái nào, ai sở hữu, đã qua rule nào và có được dùng cho mục tiêu nào.

## 9. Mô hình hóa dữ liệu phân tích

OLTP thường chuẩn hóa để giảm duplicate và bảo vệ update. OLAP có thể dùng mô hình chiều để query dễ và hiệu quả.

### 9.1. Star schema

Star schema thường gồm fact table ở trung tâm và các dimension xung quanh. Ví dụ nền tảng thuê thiết bị:

- **FactRental:** một dòng cho một giao dịch hoặc line item thuê.
- **DimCustomer:** thông tin khách theo dimension key.
- **DimAsset:** loại tài sản, thương hiệu và phân loại.
- **DimDate:** ngày, tuần, tháng, quý, năm tài chính.
- **DimRegion:** vùng kinh doanh hoặc điểm giao nhận.

~~~mermaid
flowchart TB
    F[("FactRental")]
    C[("DimCustomer")] --> F
    A[("DimAsset")] --> F
    D[("DimDate")] --> F
    R[("DimRegion")] --> F
~~~

### 9.2. Grain của fact table

**Grain** xác định một dòng trong fact table đại diện cho điều gì. Một dòng có thể là booking, booking item, payment transaction hoặc ngày hoạt động của thiết bị.

Nếu không định nghĩa grain, join có thể nhân bản bản ghi và làm tổng tiền bị đếm nhiều lần. Trước khi tạo fact, hãy trả lời: mỗi row là entity hay event; business key là gì; dimension có thay đổi theo thời gian không; có trạng thái hủy/điều chỉnh; metric được tính ở grain nào?

### 9.3. Slowly Changing Dimensions

Một dimension như địa chỉ vùng hoặc phân khúc khách có thể thay đổi. Cần quyết định báo cáo lịch sử dùng giá trị tại thời điểm giao dịch hay giá trị hiện tại.

- **Type 1:** ghi đè giá trị cũ; phù hợp correction hoặc thuộc tính không cần lịch sử.
- **Type 2:** tạo version mới với effective start/end; giữ lịch sử.
- **Type 3:** lưu giới hạn một số giá trị trước/current; phù hợp nhu cầu cụ thể.

Nếu doanh thu lịch sử phải gắn với vùng tại thời điểm phát sinh, Type 2 thường phù hợp hơn ghi đè Type 1.

## 10. Partitioning và file format

Data platform có thể lưu rất nhiều file và partition. Tổ chức dữ liệu kém làm query scan quá nhiều file nhỏ hoặc tạo skew.

- Partition theo trường thường dùng để lọc và cardinality hợp lý, ví dụ ngày/tháng.
- Tránh partition theo ID gần như duy nhất, vì số partition/file tăng quá lớn.
- Không partition quá sâu khi dữ liệu mỗi partition rất nhỏ.
- Dùng columnar format như Parquet/ORC cho workload phân tích dạng bảng nếu engine hỗ trợ.
- Nén theo codec và mức compression phù hợp CPU/query.
- Compaction để tránh small-file problem.
- Dùng metadata/catalog để query engine prune partition và file.
- Kiểm tra schema evolution và compatibility giữa writer/reader.

Ví dụ cấu trúc object:

~~~text
object-storage://analytics-data/curated/rentals/
    event_date=2026-11-18/
        region=south/
            part-0001.parquet
~~~

Đường dẫn chỉ minh họa. Partition theo region chỉ phù hợp nếu số vùng giới hạn và query thường lọc theo vùng; với cardinality cao hoặc dữ liệu nhỏ, có thể tạo quá nhiều thư mục.

## 11. Data quality và kiểm tra pipeline

Pipeline thành công kỹ thuật không đồng nghĩa dữ liệu đúng nghiệp vụ. Job có thể chạy exit code 0 nhưng thiếu payment events do connector mất checkpoint.

| Nhóm | Ví dụ rule |
| --- | --- |
| Completeness | Số record nhận được so với source count hoặc expected window |
| Uniqueness | event_id/business key không trùng theo semantics |
| Validity | amount không âm ngoài refund/adjustment được cho phép |
| Referential integrity | fact key tham chiếu dimension hợp lệ |
| Freshness | Event cuối cùng tới curated layer trong thời hạn |
| Consistency | Tổng tiền/record đối chiếu nguồn theo cùng định nghĩa |
| Schema | Field bắt buộc, kiểu, nullability và enum hợp lệ |
| Distribution | Giá trị không biến động bất thường so với baseline |

### 11.1. Reconciliation

Đối chiếu nguồn và đích cần có phạm vi và thời điểm rõ. Ví dụ đếm booking được commit trong một khoảng theo source watermark rồi so với số booking đã xuất hiện ở curated table sau khi pipeline catch up.

Không so sánh hai hệ thống tại hai thời điểm không tương ứng rồi kết luận dữ liệu mất. Với streaming, cần watermark/window closure để biết khoảng thời gian đã đủ dữ liệu tới hay chưa.

### 11.2. Xử lý record lỗi

Record không hợp lệ có thể đưa vào quarantine/dead-letter dataset với reason code, source ID và metadata. Cần owner sửa nguyên nhân, chính sách replay và retention. Không âm thầm drop dữ liệu lỗi mà không ghi counter hoặc cảnh báo.

## 12. Freshness, watermark và late-arriving data

Event time và processing time có thể khác nhau. Một thiết bị mất kết nối có thể gửi dữ liệu xảy ra hôm qua vào hôm nay. Nếu pipeline chỉ dùng ingestion time, báo cáo theo ngày nghiệp vụ có thể sai.

- **Event time:** thời điểm sự kiện thực sự xảy ra theo nguồn.
- **Ingestion time:** lúc platform tiếp nhận dữ liệu.
- **Processing time:** lúc pipeline xử lý.
- **Watermark:** mốc engine dùng để ước lượng dữ liệu cũ hơn đã tới đủ ở mức chấp nhận.

Cần xác định late-arrival policy: cho phép tới muộn bao lâu, có cập nhật partition lịch sử không, dashboard có provisional data không và khi nào period được đóng.

Freshness nên đo end-to-end từ source commit/event time tới curated/serving availability; chỉ đo thời gian job chạy là chưa đủ.

## 13. Data governance, catalog và lineage

Khi dataset tăng, người dùng cần biết dữ liệu nào tồn tại, ai sở hữu, định nghĩa metric là gì và có được sử dụng cho mục đích cụ thể không.

Catalog nên mô tả tên dataset/table/field và business definition, owner/steward, schema/format/partition/location, freshness/quality/SLA, classification/sensitivity/retention, lineage upstream/downstream và use case được duyệt.

Lineage nối nguồn với các bước transform và dataset đích. Khi metric doanh thu thay đổi, analyst có thể truy ngược source tables/event types, pipeline/job version, transformation logic/code commit, quality checks và semantic model sử dụng trong dashboard. Lineage hữu ích cho impact analysis, audit và điều tra sai số.

## 14. Bảo mật dữ liệu khi tách OLTP và analytics

Việc sao chép dữ liệu sang lake/warehouse mở rộng bề mặt truy cập. User không có quyền đọc database production nhưng có thể có quyền tải export hoặc query bảng raw, dẫn tới rò rỉ.

Các nguyên tắc:

- **Least privilege:** phân quyền theo dataset, table, column, row và use case khi nền tảng hỗ trợ.
- **Data minimization:** chỉ sao chép trường cần cho phân tích.
- **Masking/tokenization:** che hoặc thay thế thông tin định danh trước khi chia sẻ rộng.
- **Encryption:** mã hóa in transit và at rest, quản lý key lifecycle.
- **Network isolation:** tách data plane, private endpoints và egress policy theo nhu cầu.
- **Audit:** ghi truy vấn nhạy cảm, export, thay đổi policy và truy cập catalog.
- **Retention/deletion:** áp dụng lên raw, curated, cache, backup và derived dataset.
- **Environment separation:** test/sandbox không tự động nhận dữ liệu production đầy đủ.
- **Purpose limitation:** dữ liệu chỉ dùng đúng mục đích được duyệt.

### 14.1. Pseudonymization không phải anonymization

Thay customer ID bằng token có thể giảm nhận dạng trực tiếp nhưng nếu có bảng mapping hoặc kết hợp thuộc tính để nhận diện, dữ liệu vẫn có thể nhạy cảm. Phải phân loại theo khả năng liên kết thực tế.

### 14.2. Xóa dữ liệu và bản sao phân tích

Yêu cầu xóa/cập nhật có thể phải lan qua source, CDC, raw, curated, data marts, cache, export và backup theo thời hạn/chính sách. Cần thiết kế deletion propagation và tombstone phù hợp. Không giả định xóa ở OLTP tự động xóa mọi bản sao downstream.

## 15. Cô lập workload và bảo vệ database giao dịch

Mục tiêu là ngăn query phân tích tranh chấp tài nguyên với transaction. Các cách có thể áp dụng:

1. Dùng read replica chuyên dụng cho query read-only nếu stale tolerance và tải cho phép.
2. CDC sang lake/warehouse để tránh query trực tiếp production.
3. Dùng replica/export riêng cho ingestion ban đầu và batch extraction.
4. Giới hạn query, connection, concurrency và execution time trên mọi nguồn đọc chung.
5. Chạy export theo cửa sổ tải thấp hoặc incremental theo watermark.
6. Dùng query monitoring để phát hiện report gây tải.
7. Tách backup, maintenance và batch jobs khỏi peak transaction khi có thể.

Read replica vẫn chia sẻ replication overhead và có thể lag khi report nặng. Nếu analytics workload lớn, warehouse/lakehouse độc lập thường tạo isolation tốt hơn.

## 16. Batch load, incremental load và backfill

**Full load** lấy toàn bộ dataset, phù hợp lần khởi tạo hoặc dataset nhỏ. Với bảng lớn, full scan thường xuyên có thể gây tải nguồn và chi phí truyền/lưu trữ cao.

**Incremental load** chỉ lấy phần thay đổi kể từ watermark/checkpoint. Cần xác định watermark dựa trên updated time, transaction log position hay sequence; update đến muộn hoặc timestamp trùng; cách biểu diễn delete/tombstone; khả năng idempotent khi re-run; và checkpoint chỉ cập nhật sau khi dữ liệu đích commit.

Dựa vào updated time đơn thuần có thể bỏ sót update nếu timestamp độ phân giải thấp, đồng hồ sai hoặc transaction commit trễ. CDC dựa trên log có thể giải quyết một số trường hợp nhưng vẫn cần hiểu connector semantics.

**Backfill** nạp lại một khoảng lịch sử hoặc dataset cũ. Nó có thể cạnh tranh tài nguyên với pipeline live. Nên đặt quota, priority thấp hơn, partition theo thời gian, theo dõi progress và bảo đảm backfill không ghi đè dữ liệu mới hơn.

## 17. Orchestration và phụ thuộc pipeline

Pipeline có thể gồm ingestion, validation, transform, enrichment, aggregate và publish. Orchestrator theo dõi phụ thuộc, retry, timeout, trạng thái và lịch chạy.

~~~mermaid
flowchart TD
    A["Ingest source changes"] --> B["Validate schema and completeness"]
    B --> C{"Quality passed?"}
    C -- "No" --> Q["Quarantine + alert"]
    C -- "Yes" --> D["Transform / normalize"]
    D --> E["Build curated tables"]
    E --> F["Reconcile source and target"]
    F --> G{"Reconciliation passed?"}
    G -- "No" --> Q
    G -- "Yes" --> H["Publish semantic dataset"]
~~~

Một pipeline cần phân biệt lỗi tạm thời có thể retry; lỗi schema cần producer/data owner xử lý; lỗi quality cần quarantine hoặc chặn publish; lỗi downstream cần giữ trạng thái và chạy lại an toàn. Partial completion phải có metadata để tránh publish dữ liệu chưa đầy đủ.

Không đánh dấu dataset fresh chỉ vì scheduler job chạy xong nếu nguồn CDC còn lag hoặc quality gate chưa đạt.

## 18. Data product và ownership

Một data platform không nên chỉ là tập hợp bảng không ai chịu trách nhiệm. Với cách tiếp cận domain-oriented hoặc data mesh, domain có thể sở hữu data product, nhưng cần nền tảng chung và quy tắc liên domain.

Một data product nên có owner, đối tượng tiêu thụ, business definition, schema contract, freshness/completeness/availability SLO, quality checks, lineage, classification, permission, retention, version/deprecation policy và cách truy cập được hỗ trợ.

Không phải tổ chức nào cũng cần triển khai đầy đủ data mesh. Ý tưởng ownership theo domain có thể áp dụng mà không tạo thêm platform phân tán vượt năng lực vận hành.

## 19. Hiệu năng và tối ưu chi phí

Tách OLTP khỏi analytics tạo thêm hệ thống, storage, pipeline và bản sao dữ liệu. Lợi ích isolation cần so sánh với tổng chi phí sở hữu.

Nguồn chi phí bao gồm database OLTP/replica/log retention; CDC connector/broker/partition/data transfer; object storage theo tier và request; warehouse/lakehouse compute; ETL/ELT/stream processing; catalog/governance/quality/lineage; BI concurrency; logging/metrics/audit và on-call.

Các cách tối ưu:

- Chỉ replicate trường và bảng cần thiết.
- Dùng incremental load/CDC thay full scan lặp lại.
- Partition theo query access pattern, tránh cardinality quá cao.
- Compact file nhỏ và chọn columnar format phù hợp.
- Tự động scale/stop compute không cần chạy liên tục nếu hỗ trợ.
- Dùng workload management và giới hạn concurrency cho query đắt.
- Chọn retention/storage tier theo tần suất truy cập.
- Theo dõi cost per query, cost per dataset và cost per successful pipeline run.
- Xác định owner cho dataset không còn sử dụng.

Đừng xóa raw quá sớm nếu cần replay, audit hoặc sửa transform. Ngược lại, giữ mọi dữ liệu vô hạn tạo privacy risk và chi phí không kiểm soát.

## 20. Độ tin cậy và phục hồi data platform

Nền tảng phân tích có thể chấp nhận dữ liệu trễ trong một khoảng, nhưng không nên âm thầm mất dữ liệu.

Cần thiết kế checkpoint/offset bền vững cho CDC và stream consumers; retry với backoff, idempotent sink và quarantine; reconciliation giữa source/target; replay/backfill từ log/archive; backup metadata/catalog/configuration; rebuild curated layer từ raw nếu được; cross-region replication/backup theo RPO/RTO; runbook khi connector lag, broker full, schema change hoặc warehouse outage.

### 20.1. RPO/RTO khác freshness SLO

- **Freshness SLO:** dữ liệu mới phải xuất hiện trong lớp phân tích trong bao lâu.
- **RPO:** lượng dữ liệu có thể mất khi phục hồi sau sự cố.
- **RTO:** thời gian để khôi phục pipeline/dataset.
- **Completeness SLO:** tỷ lệ hoặc số lượng bản ghi cần được xử lý đầy đủ.

Dashboard trễ 10 phút có thể vi phạm freshness nhưng không mất dữ liệu. Pipeline mất checkpoint có thể khiến dữ liệu thiếu vĩnh viễn dù dashboard vẫn mới tới vài phút trước. Cần theo dõi từng chiều riêng.

## 21. Ví dụ kiến trúc: nền tảng đặt thuê thiết bị

Giả sử hệ thống có Booking DB, Payment DB, Asset DB và ứng dụng giao dịch. Các nhóm cần báo cáo doanh thu, hiệu suất sử dụng tài sản và hành vi khách hàng.

| Nguồn | OLTP responsibility | Dữ liệu phân tích |
| --- | --- | --- |
| Booking DB | Trạng thái booking và lịch thuê có thẩm quyền | Booking fact, thời lượng thuê, cancellation |
| Payment DB | Transaction, authorization, capture, refund | Payment fact, net/gross revenue |
| Asset DB | Tình trạng và khả dụng tài sản | Utilization, maintenance history |
| Customer service | Hồ sơ và quyền truy cập PII | Segment/tokenized dimensions theo policy |

~~~mermaid
flowchart TB
    subgraph OLTP["Operational systems"]
        B[("Booking DB")]
        P[("Payment DB")]
        A[("Asset DB")]
        C[("Customer service")]
    end
    B --> CDC["CDC / event ingestion"]
    P --> CDC
    A --> CDC
    C --> MASK["PII filter / tokenization"]
    CDC --> RAW[("Raw object storage")]
    MASK --> RAW
    RAW --> TRANS["ELT + quality + reconciliation"]
    TRANS --> CUR[("Curated lakehouse / warehouse")]
    CUR --> MART["Rental / Revenue data marts"]
    MART --> BI["BI dashboards"]
    MART --> ML["Forecasting / ML"]
~~~

BFF hoặc API giao dịch không query warehouse để xác nhận booking. Warehouse phục vụ câu hỏi phân tích; OLTP giữ quyền quyết định và commit transaction.

### 21.1. Chọn freshness

| Use case | Freshness mục tiêu giả định | Phương án |
| --- | --- | --- |
| Phát hiện gian lận nhanh | Giây đến dưới một phút | Event/stream pipeline riêng |
| Dashboard vận hành | 1–5 phút | CDC + micro-batch/stream processing |
| Báo cáo doanh thu ngày | Hàng giờ hoặc cuối ngày | Batch/ELT với reconciliation |
| Huấn luyện dự báo | Theo ngày/tuần | Curated historical dataset |
| Đối soát kế toán | Theo cửa sổ đóng sổ | Batch có completeness gate và audit |

Đây là mục tiêu minh họa, phải xác nhận bằng yêu cầu nghiệp vụ. Use case fraud detection có thể cần online feature store và serving riêng thay vì dashboard streaming.

### 21.2. Kiểm soát sự cố

- CDC connector ngừng đọc: cảnh báo log lag và bảo vệ transaction log khỏi tăng vô hạn.
- Schema Payment đổi: phát hiện contract incompatibility, quarantine và thông báo owner.
- Warehouse quá tải: giữ ingestion/raw bền vững, giảm publish/query concurrency.
- PII lọt vào raw: chặn quality/security gate và xử lý theo incident policy.
- Reconciliation lệch: giữ dataset ở trạng thái chưa verified, không publish metric như dữ liệu đầy đủ.

## 22. Kiểm thử data platform

Kiểm thử không chỉ xác nhận job chạy thành công.

- **Contract test:** schema, field semantics, version và compatibility.
- **Data quality test:** uniqueness, null, range, relationship và domain rules.
- **Volume test:** peak ingestion rate, batch size, file count và query concurrency.
- **Freshness test:** source event tới curated/serving trong SLO.
- **Failure test:** connector restart, broker outage, job crash, partial write và retry.
- **Replay/backfill test:** chạy lại cửa sổ không tạo duplicate hoặc ghi đè dữ liệu mới.
- **Security test:** quyền dataset/table/column, masking, export và audit.
- **Reconciliation test:** so sánh source/target với watermark tương ứng.
- **Recovery test:** restore metadata, checkpoint, raw/curated và rebuild.
- **Cost test:** đo ingestion, transform, storage, query và idle compute.

Pipeline nên có test fixture đại diện cho duplicate, late events, delete, timezone, currency conversion, empty batch và schema evolution.

## 23. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Cho BI query trực tiếp production OLTP | Query phân tích làm chậm giao dịch | Tách warehouse/lake hoặc replica chuyên dụng có giới hạn |
| Dùng read replica như nền tảng analytics tổng thể | Lag, scan nặng và tranh chấp tài nguyên | CDC sang nền tảng phân tích riêng khi tải lớn |
| Full extract lặp lại mọi bảng | Tải nguồn và transfer cost tăng | Incremental/CDC, watermark và partition |
| Không có business definition | Metric cùng tên nhưng kết quả khác | Semantic layer, owner và data contract |
| Coi CDC record là business event | Hiểu sai ý nghĩa transition nghiệp vụ | Phân biệt row changes và domain events |
| Bỏ qua delete/update semantics | Dữ liệu downstream sai hoặc tồn tại mãi | Tombstone, merge và retention policy |
| Không kiểm tra late-arriving data | Báo cáo theo ngày sai | Event time, watermark và correction window |
| Không có quality gate | Dashboard publish dữ liệu thiếu/sai | Completeness, reconciliation và quarantine |
| Chỉ lưu curated, bỏ raw quá sớm | Không thể replay khi transform sai | Retention raw theo mục đích và policy |
| Giữ raw vô hạn | Cost và privacy risk tăng | Lifecycle, minimization và deletion propagation |
| Không kiểm soát partition/small files | Query chậm và metadata overhead lớn | Partition design, compaction, format |
| Copy PII không lọc sang analytics | Mở rộng phạm vi lộ dữ liệu | Masking, tokenization và least privilege |
| Không version pipeline/schema | Không tái lập được metric cũ | Version code, schema, config và lineage |
| Backfill không giới hạn | Ảnh hưởng ingestion live | Priority, quota, window và resource isolation |
| Chỉ đo job success | Không phát hiện data loss hoặc stale data | Freshness/completeness/quality SLO |

## 24. Quy trình thiết kế và triển khai

1. **Xác định use case:** ai phân tích điều gì, ở mức chi tiết nào và cần freshness bao lâu?
2. **Phân loại workload:** transaction, operational reporting, analytics, ML hay archival.
3. **Chọn source of truth:** domain/database nào sở hữu từng trường và business transition?
4. **Định nghĩa data contract:** schema, key, semantics, event time, delete, version và owner.
5. **Chọn ingestion:** full snapshot ban đầu, batch, micro-batch, streaming hoặc CDC.
6. **Chọn storage:** raw landing, data lake, warehouse, lakehouse hoặc kết hợp.
7. **Thiết kế transform:** ETL/ELT, standardization, model, grain, quality và reconciliation.
8. **Đặt freshness/completeness SLO:** end-to-end và theo dataset.
9. **Thiết kế security/governance:** classification, masking, IAM, catalog, lineage, retention và deletion.
10. **Cô lập workload:** nguồn OLTP, ingestion, transform và query compute.
11. **Thiết lập CI/CD/orchestration:** version, test, retry, backfill và promotion.
12. **Đo và tối ưu:** cost, query performance, freshness, lag, quality và recovery.
13. **Diễn tập lỗi:** connector lag, schema break, broker full, restore và replay.

## 25. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | CDC/checkpoint có thể phục hồi? Backfill/replay idempotent? Có reconciliation và backup/restore? |
| **Bảo mật** | PII có được giảm thiểu/masking? Quyền raw/curated/serving phân tách? Deletion và retention lan qua mọi bản sao? |
| **Hiệu quả hiệu năng** | OLTP có được bảo vệ? Ingestion lag, query latency và concurrency đạt mục tiêu? Partition/file format hợp lý? |
| **Tối ưu chi phí** | Có full scan, small files, storage vô hạn, compute idle hoặc query không giới hạn? Cost theo dataset/use case là bao nhiêu? |
| **Khả năng vận hành** | Có catalog, lineage, owner, quality gate, freshness alert, replay/backfill runbook và pipeline version? |

### Checklist nghiệm thu

- [ ] OLTP và OLAP có workload boundary, owner và SLO rõ.
- [ ] Query phân tích không truy cập tự do database production.
- [ ] Mỗi dataset có source of truth, contract và business definition.
- [ ] Batch/CDC/streaming được chọn theo freshness, capacity và khả năng vận hành.
- [ ] CDC theo dõi log position/lag và có cách xử lý schema change.
- [ ] Raw, cleaned và curated có mục đích, quyền và retention riêng.
- [ ] Model phân tích có grain, key và metric definition rõ.
- [ ] Partition/file format và compaction được kiểm thử với query thực tế.
- [ ] Quality, completeness, freshness và reconciliation có rule/owner.
- [ ] PII được giảm thiểu, masking, mã hóa và kiểm soát quyền.
- [ ] Delete, correction và late-arriving data lan truyền đúng.
- [ ] Pipeline có checkpoint, retry, idempotency, quarantine và replay.
- [ ] Backfill không ảnh hưởng ingestion live hoặc OLTP.
- [ ] Có catalog, lineage, cost dashboard và data product owner.
- [ ] Restore/rebuild và incident runbook đã được diễn tập.

## 26. Bài tập áp dụng

Một nền tảng thương mại điện tử có database giao dịch quản lý khách hàng, đơn hàng, thanh toán và tồn kho. Trong giờ cao điểm, dashboard doanh thu và phân tích sản phẩm làm database chậm đáng kể. Ban điều hành muốn dashboard cập nhật trong 2 phút; nhóm tài chính cần báo cáo đóng sổ cuối ngày có thể đối chiếu; nhóm data science cần dữ liệu lịch sử để dự báo nhu cầu.

Hãy thiết kế:

1. Những workload nào là OLTP, operational analytics, OLAP và ML?
2. Có nên dùng read replica, CDC, batch hay streaming cho từng use case?
3. Thiết kế luồng từ source database tới raw, cleaned, curated và serving layer.
4. Cách xác định freshness, completeness và reconciliation cho dashboard 2 phút.
5. Dữ liệu nào được token hóa/masking trước khi analyst truy cập?
6. Xử lý update, delete, late event và schema evolution thế nào?
7. Định nghĩa grain cho fact sales và dimension product/customer/date.
8. Làm sao backfill lịch sử mà không gây áp lực lên production hoặc làm trùng dữ liệu?
9. Metric nào giúp phát hiện pipeline lag, data quality issue và chi phí tăng?
10. Làm sao chứng minh query dashboard không còn ảnh hưởng transaction database?

Một phương án có cơ sở có thể dùng CDC cho thay đổi giao dịch, raw object storage làm vùng lưu đầu vào, ELT xây curated tables/warehouse, micro-batch hoặc stream cho dashboard 2 phút, và batch có reconciliation cho đóng sổ. Data science sử dụng dataset lịch sử đã được quản trị, với quyền và mục đích sử dụng riêng. Cần chứng minh freshness và completeness bằng số liệu thay vì chỉ dựa vào lịch chạy pipeline.

**Điểm cốt lõi:** OLTP tối ưu cho transaction có tính đúng đắn và phản hồi nhanh; OLAP tối ưu cho scan, tổng hợp và phân tích. Tách hai workload bằng ingestion, storage và compute phù hợp giúp bảo vệ hệ thống giao dịch, nhưng tạo thêm yêu cầu về đồng bộ, freshness, quality, governance, security và chi phí. Data platform tốt phải biết dữ liệu đến từ đâu, biến đổi thế nào, ai được dùng, mới tới đâu và có thể phục hồi ra sao.
