# Kiến trúc BigQuery và tách biệt storage với compute

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích hai lớp **storage** và **compute** của BigQuery, vai trò **Colossus/Capacitor**, **Dremel**, **Jupiter** và **slot** mà không nhầm chúng với tài nguyên VM do người dùng cấp phát.
2. Mô tả đường đi một truy vấn từ SQL → lập kế hoạch → đọc cột dữ liệu → xử lý phân tán → trả kết quả; phân biệt **logical bytes**, **bytes processed**, **slot-ms** và thời gian chạy.
3. So sánh **on-demand pricing** theo dữ liệu xử lý với **capacity-based reservations** theo số slot được cấp theo thời gian và các **BigQuery editions**.
4. Tạo dataset, bảng phân vùng/cluster, chạy SQL và dry run; đọc thống kê jobs/storage để tối ưu hiệu năng và chi phí.
5. Phân biệt managed tables với external tables, chọn ingest batch/streaming, kiểm soát region, IAM, bảo vệ dữ liệu và vận hành.
6. Áp dụng mô hình vào ứng dụng Java trên Cloud Run/GKE, tình huống doanh nghiệp, câu hỏi luyện tập và bài tập có đáp án.

## 1. BigQuery là gì và giải quyết bài toán nào?

**BigQuery** là nền tảng dữ liệu và **data warehouse phân tích serverless** của Google Cloud. Bạn gửi GoogleSQL, tải dữ liệu, gọi API hoặc tạo jobs; Google Cloud quản lý phần lớn hạ tầng lưu trữ và thực thi. Trong mô-đun **CLOUD_PROVIDERS_GCP**, BigQuery bổ sung lớp phân tích cho dữ liệu phát sinh từ Cloud Run, GKE, Cloud SQL, Pub/Sub và Cloud Storage, bên cạnh IAM, giám sát độ tin cậy và tối ưu chi phí.

Ví dụ hệ thống bán hàng:

- **Cloud SQL PostgreSQL** phục vụ từng giao dịch thanh toán/đặt hàng với độ trễ thấp.
- **Pub/Sub** mang sự kiện phát sinh từ Java orders-api.
- **Cloud Storage** chứa bản xuất file CSV/Parquet.
- **BigQuery** tổng hợp hàng tỷ sự kiện theo ngày, sản phẩm, vùng và kênh bán hàng.
- **Looker/BI tool** truy vấn báo cáo; nhóm dữ liệu chạy ETL/ELT SQL.

BigQuery **không thay thế mặc định** Cloud SQL hoặc Spanner cho mỗi lần đọc/ghi bản ghi transactional nhỏ với yêu cầu OLTP latency thấp. Trọng tâm của BigQuery là đọc/tổng hợp nhiều dữ liệu và xử lý phân tích có thể phân tán.

### 1.1. Câu hỏi xuyên suốt

Doanh nghiệp lưu **20 TB dữ liệu lịch sử**, nhưng chỉ chạy báo cáo tổng kết mỗi đêm; lúc có chiến dịch, hàng chục nhà phân tích lại chạy SQL đồng thời. Nếu một database truyền thống gắn chặt disk với CPU, tăng storage thường kéo theo quyết định về compute. **BigQuery tách storage và compute**: dung lượng lưu có thể lớn trong khi compute được dùng linh hoạt theo từng job hoặc reservation.

## 2. Sơ đồ kiến trúc: storage và compute là hai lớp độc lập

~~~mermaid
flowchart TB
    CLIENT["BigQuery Studio / bq CLI / Java SDK / BI"] --> API["BigQuery API + Metadata + IAM"]
    API --> JOB["Query job: parser, optimizer, scheduler"]
    JOB --> CPU["Compute layer: Dremel execution tree<br/>distributed workers + slots + shuffle"]
    CPU <-->|"Jupiter high-bandwidth network"| STORE["Storage layer: Colossus<br/>Capacitor columnar data + metadata"]
    LOAD["Batch load / BigQuery Storage Write API / DML"] --> STORE
    GCS["Cloud Storage external data / BigLake"] -. "đọc ngoài managed storage khi truy vấn" .-> CPU
    CPU --> RESULT["Query result / cached result / destination table"]
    RESULT --> CLIENT
~~~

| Thành phần | Vai trò thực tế | Người dùng điều khiển gì? |
|---|---|---|
| **Colossus** | Hệ thống distributed storage quản lý dữ liệu BigQuery, replication/recovery | Datasets, tables, partition, retention, encryption, vị trí |
| **Capacitor** | Định dạng lưu trữ cột tối ưu đọc/nén dữ liệu phân tích | Schema, types, clustering, partition; không quản trị file Capacitor |
| **Jupiter** | Mạng thông lượng rất cao kết nối compute và storage | Location, data paths và network costs; không cấp mạng Jupiter |
| **Dremel** | Query execution engine song song với execution tree, scans/aggregations | SQL, query plan, job priority, reservations |
| **Slot** | Đơn vị compute ảo BigQuery dùng để chạy query và các jobs hỗ trợ | On-demand: BigQuery cấp tự động; capacity: cấu hình reservation |
| **Metadata, scheduler, shuffle** | Catalog, lập kế hoạch stages và trao đổi intermediate data | SQL/schema, jobs, reservation assignment, observability |

**Kiến trúc tách lớp là nguyên tắc quản lý tài nguyên, không phải hai dịch vụ khách hàng phải tự kết nối thủ công.** BigQuery quản lý sự phối hợp giữa Dremel và Colossus. Bạn không tạo một máy Dremel hoặc gắn ổ Colossus vào VM.

### 2.1. So với kiến trúc gắn storage/compute

| Đặc tính | Database/server truyền thống | BigQuery |
|---|---|---|
| Tăng dung lượng dữ liệu | Thường phải tăng disk trên server/cụm | Managed storage mở rộng độc lập với việc mua slot |
| Tăng song song truy vấn | Tăng số node/CPU hoặc cấu hình cluster | BigQuery cấp slots theo job hoặc reservations |
| Khi không có SQL jobs | Có thể vẫn trả phí máy chủ liên tục | Managed storage vẫn tồn tại/tính phí; **on-demand query compute** không chạy khi không có job |
| Khi nhiều SQL jobs cùng lúc | Cạnh tranh CPU/RAM, cần tuning cluster | Scheduler chia slots; vẫn có contention nếu capacity bị giới hạn |
| Truy vấn dữ liệu cực lớn | Phụ thuộc cách phân vùng, indexing, cluster | Columnar scans/partition pruning và parallel execution |

**Không hiểu sai:** tách lớp **không có nghĩa compute miễn phí** hoặc một truy vấn luôn nhanh bất kể SQL. Storage bytes, slots, network, concurrency, shuffle, data location và câu SQL đều ảnh hưởng hiệu năng/chi phí.

## 3. Storage layer: Colossus và Capacitor

BigQuery trình bày dữ liệu theo **project → dataset → table → rows/columns**, nhưng managed storage vật lý được tối ưu **theo cột**, dùng **Capacitor**, lưu trên **Colossus**.

### 3.1. Vì sao columnar storage phù hợp OLAP?

Giả sử bảng có 200 cột, 1 tỷ rows, nhưng câu SQL chỉ dùng **order_date, region, amount**. BigQuery có thể đọc các cột cần thiết thay vì đọc toàn bộ 200 cột rồi loại bỏ. Các giá trị của cùng cột cũng thường dễ nén hơn.

~~~sql
SELECT
  region,
  SUM(amount) AS revenue
FROM `shop-dev-001.commerce_analytics.orders`
WHERE order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-07'
GROUP BY region;
~~~

**Không có cam kết “đọc đúng ba cột và đúng bảy ngày” nếu thiết kế bảng sai:** filter chỉ giúp **partition pruning** khi table phân vùng phù hợp; scan bytes còn tùy types, clustering, storage format và query plan. Thêm **LIMIT 10** không tự giảm byte quét của một aggregation cần đọc cả tập dữ liệu.

### 3.2. Storage độc lập nhưng vẫn có vị trí và phí

- **Dataset** có location như **asia-southeast1** hoặc **US**; các tables nằm trong dataset đó. Location cần quyết định khi tạo vì không thể sửa tại chỗ.
- Managed data có cơ chế replication/durability của BigQuery phù hợp location; **không suy rằng một regional dataset tự động là multi-region DR**.
- BigQuery có **logical storage billing** (bytes không nén) và **physical storage billing** (bytes nén). Chọn mô hình tại **dataset level**; thay model tính phí **không di chuyển hoặc định dạng lại dữ liệu**.
- Storage có **active/long-term**: dữ liệu trong một table/partition không thay đổi trong **90 ngày** có thể đạt mức long-term tương ứng. Thao tác sửa phần dữ liệu bị ảnh hưởng có thể làm phần đó trở lại active.
- **Time travel** mặc định 7 ngày, tùy chỉnh 2–7 ngày; sau đó có **fail-safe 7 ngày** không tùy chỉnh. Trong mô hình physical billing, time-travel/fail-safe bytes có thể được tính phí riêng.

**Tách storage/compute không loại bỏ** retention, encryption, quy hoạch vùng và quản lý dữ liệu nhạy cảm.

### 3.3. Partitioning và clustering là tối ưu đường đọc

| Kỹ thuật | Tác dụng | Ví dụ |
|---|---|---|
| **Partition by DATE** | Đọc những partitions hợp filter ngày | orders theo order_date |
| **Clustering** | Sắp xếp/nhóm data blocks theo các cột lọc, giảm block scan | customer_id, region |
| **Column projection** | Đọc cột thực sự dùng trong SQL | SELECT region, amount thay SELECT * |
| **Materialized view** | Lưu/duy trì kết quả tổng hợp đủ điều kiện để dùng lại | Daily revenue theo ngày |
| **Query result cache** | Trả lại kết quả query y hệt nếu đủ điều kiện | Dashboard query lặp lại |

**Partition ≠ cluster:** partition pruning có thể ước lượng từ bộ lọc phân vùng trước job; clustering block pruning có thể chỉ giảm bytes sau khi thực thi, vì vậy dry run đối với clustered tables có thể **ước lượng cao hơn thực tế**.

## 4. Compute layer: Dremel và slots

Một **slot** là **đơn vị compute ảo của BigQuery**, không phải một vCPU hoặc một Pod Kubernetes cố định. Mỗi query có thể được chia thành các stages và work units song song:

~~~mermaid
flowchart TB
    Q["SELECT ... GROUP BY region"] --> PLAN["Optimizer: stages / distributed plan"]
    PLAN --> S1["Slots: scan partitions + cột cần dùng"]
    PLAN --> S2["Slots: scan partitions + cột cần dùng"]
    PLAN --> S3["Slots: scan partitions + cột cần dùng"]
    S1 --> SH["Shuffle + partial aggregation"]
    S2 --> SH
    S3 --> SH
    SH --> FIN["Final aggregation / ordering"]
    FIN --> OUT["Result"]
~~~

1. **Parser/optimizer** kiểm tra cú pháp, permissions và tạo kế hoạch đọc/transform/join/aggregate.
2. Scheduler chia query thành stages có phụ thuộc; BigQuery cấp **slots** phù hợp dựa trên công việc và capacity sẵn có.
3. **Workers** đọc cột/bản phân vùng từ Colossus qua mạng nội bộ, giải nén và thực hiện operators.
4. **Shuffle** chuyển dữ liệu trung gian theo key để thực hiện join/grouping, có thể tốn compute/network nếu dữ liệu lớn hoặc skew.
5. Kết quả được trả cho client, lưu **temporary result cache**, hoặc ghi thành **destination table**.

**Một query dùng nhiều slots không đồng nghĩa thời gian giảm tuyến tính.** Bottlenecks có thể đến từ **scan lớn, shuffle, skew, serial stages, slot contention, UDF, external source latency**; có stages không chạy song song hoàn toàn.

### 4.1. Slot-ms khác wall time

BigQuery có metric **total_slot_ms** = tổng thời gian sử dụng slots trong quá trình job. Ví dụ giả định query chạy **10 giây** và tiêu thụ **50.000 slot-ms**:

\[
\text{Average slots used} \approx \frac{50{,}000\ \text{slot-ms}}{10{,}000\ \text{ms}} = 5.
\]

Đây chỉ là **average utilization ước lượng**, không có nghĩa query luôn giữ đúng năm slots. Một job có thể dùng nhiều slots ở một stage rồi ít ở stage khác. **total_bytes_processed** và **total_slot_ms** đo hai khía cạnh khác nhau; dưới on-demand, tiền query thường dựa **bytes billed**, không trực tiếp dựa slot-ms.

## 5. Vòng đời query và các loại BigQuery jobs

Trong BigQuery, các thao tác nặng được thực thi bằng **jobs**. Một job có **project, location, job ID, type, state, labels và statistics**:

| Job type | Ví dụ | Đường xử lý |
|---|---|---|
| **QUERY** | SELECT, CREATE TABLE AS SELECT, INSERT, MERGE | Dremel query execution; đọc/ghi BigQuery storage |
| **LOAD** | Nạp CSV/Parquet từ Cloud Storage | Ingestion vào managed storage |
| **COPY** | Copy một table/snapshot theo điều kiện hỗ trợ | BigQuery managed job |
| **EXTRACT** | Export table/query result tới Cloud Storage | Đọc managed data và xuất dữ liệu |

**Một query job** có các trạng thái như **PENDING → RUNNING → DONE**. DONE có thể kèm lỗi nên phải kiểm tra **errorResult**, không chỉ state. Các job metadata khác với **table storage**: query xong, table vẫn tồn tại và có phí lưu trữ nếu không bị xóa/expire.

### 5.1. Đường đi theo thời gian

~~~mermaid
sequenceDiagram
    participant C as bq / SDK / BI
    participant B as BigQuery API & scheduler
    participant D as Dremel compute
    participant S as Colossus storage
    C->>B: Submit query job
    B->>B: Verify IAM, location, SQL, optimize
    B->>D: Schedule stages and allocate slots
    D->>S: Read referenced columns/partitions
    S-->>D: Compressed columnar blocks
    D->>D: Scan, filter, shuffle, aggregate
    D-->>B: Result + job statistics
    B-->>C: Rows / result destination / job ID
~~~

Nếu query có **result cache hit**, BigQuery có thể trả cached results và tránh chạy lại pipeline. Cached query results thường có thời hạn **khoảng 24 giờ**, không được đảm bảo cho queries nondeterministic, có recent streaming writes, hoặc dữ liệu đã thay đổi. Cached results **không bị tính phí storage**, và một cache hit hợp lệ **không bị tính phí query compute**.

**Cache không phải nguồn dữ liệu lâu dài:** nếu downstream pipeline cần bảng bền vững, ghi vào destination table/materialized view thay vì phụ thuộc bảng kết quả tạm.

### 5.2. Interactive và batch priority

Query **INTERACTIVE** ưu tiên chạy sớm theo capacity và quotas hiện có. Query **BATCH** có thể được xếp lịch trong cửa sổ chờ để tận dụng hệ thống; phù hợp ETL không yêu cầu latency tức thì. **Batch không có nghĩa query không tiêu thụ slots hoặc luôn miễn phí**; chi phí vẫn theo pricing model và tài nguyên của job.

## 6. Cấu trúc resource, location và quyền sở hữu

~~~text
Google Cloud project: shop-dev-001
├── BigQuery dataset: commerce_analytics (asia-southeast1)
│   ├── Managed table: orders
│   ├── View: daily_revenue
│   └── Other tables / materialized views / routines
├── Query jobs (location asia-southeast1)
└── Optional: Reservations + assignments (cùng location)
~~~

| Tài nguyên | Vai trò | Ví dụ |
|---|---|---|
| **Project** | IAM, API, billing, nơi submit job | shop-dev-001 |
| **Dataset** | Container tables/views, data location, retention, storage billing model | commerce_analytics |
| **Table** | Schema và managed data lưu trong BigQuery | orders |
| **View** | SQL logic được lưu; thường không sao chép data gốc | daily_revenue |
| **Job** | Thực thi một thao tác; có location, query plan, job stats | query job ID |
| **Reservation** | Pool slots/edition ở một location để xử lý workload được gán | etl-reservation |
| **Assignment** | Gán project/folder/organization hoặc job type vào reservation | analytics jobs → etl-reservation |

### 6.1. Location vừa là dữ liệu, vừa là compute

- Dataset được tạo ở **region** (như asia-southeast1) hoặc **multi-region** (US/EU) đủ điều kiện. Location của dataset **không đổi trực tiếp**; muốn chuyển phải copy/replicate/migrate theo phương pháp được hỗ trợ.
- Job phải chạy tại **location tương thích** với dataset được truy vấn; queries thông thường không trực tiếp join hai datasets ở locations khác nhau.
- Nếu dùng reservations, **slot capacity bị ràng buộc vào location của reservation**. Một job chạy ngoài location reservation có thể bị tính theo **on-demand** nếu không có assignment tương ứng.
- Dùng **bq --location** hoặc job configuration chỉ rõ vị trí, đặc biệt với jobs không tham chiếu một dataset giúp suy ra location.
- BigQuery có các tính năng cross-region dataset replication/DR với điều kiện riêng; **không đồng nghĩa mọi dataset mặc định có backup đa vùng độc lập**.

**Ví dụ:** table ở asia-southeast1 nhưng Java SDK gửi query job với location **US** có thể nhận **Not found: Dataset ... was not found in location US** dù dataset thực sự tồn tại. Đây là lỗi **location**, không nhất thiết lỗi IAM.

## 7. Tách storage/compute tạo ra hai mô hình tính phí riêng

### 7.1. Giá storage

Trong **managed BigQuery storage**, chi phí gắn với dữ liệu được lưu và hình thức **logical/physical billing**, active/long-term bytes, time travel/fail-safe, snapshots/clones và retention theo chính sách. Dữ liệu vẫn tồn tại khi không chạy SQL.

Ví dụ doanh nghiệp có **20 TiB dữ liệu lưu** trong tháng, nhưng chỉ chạy một báo cáo: **20 TiB stored không tự đồng nghĩa 20 TiB query processed hoặc 20 TiB billed cho compute**. Ngược lại, nếu một bảng 1 TiB bị scan 30 lần, tổng query processing có thể lớn hơn dung lượng lưu nhiều lần.

### 7.2. Giá compute: on-demand hay capacity?

| Tiêu chí | **On-demand** | **Capacity-based / reservations** |
|---|---|---|
| Cách tính | Theo **TiB processed/billed** bởi mỗi query | Theo **slot capacity được cấp theo thời gian**, gắn với edition |
| Slots | BigQuery cấp tự động theo nhu cầu và giới hạn hệ thống | Baseline + slots autoscaled theo max reservation |
| Cấu hình ban đầu | Không cần tạo reservation | Tạo reservation và assignment theo workload/location |
| Khi query không chạy | Không tính **query processing** nếu không có query phát sinh | Baseline có thể vẫn tính tiền dù đang idle; autoscale tùy quy tắc |
| Phù hợp | SQL khám phá, tải nhỏ/dao động, ít cấu hình | Workload đều hoặc cần quản lý capacity/SLO và dự báo compute |
| Kiểm soát chi phí | Dry run, maximum bytes billed, quotas, tối ưu bytes scan | Baseline, max autoscale, commitments, jobs/slot metrics |

**Mọi query đều dùng slots**, kể cả on-demand; khác nhau chủ yếu ở **cách trả tiền và điều khiển capacity**, không phải hai engine xử lý SQL khác nhau.

**BigQuery editions** khi dùng reservation gồm **Standard, Enterprise, Enterprise Plus** với tính năng/giá khác nhau. Có thể dùng **on-demand ở một workload** và **capacity reservations ở workload khác** trong hệ thống; không phải di chuyển bảng dữ liệu giữa chúng. **Reservation assignment** phải đúng project/folder/organization và location thì job mới dùng được slot pool.

### 7.3. Reservation, baseline và autoscaling

~~~mermaid
flowchart LR
  JOBS["ETL / BI jobs<br/>assigned đúng location"] --> RES["Reservation: Enterprise"]
  BASE["Baseline slots<br/>tính tiền khi đã cấp"] --> RES
  AS["Autoscaled slots<br/>chỉ tăng đến max và tính phí theo capacity"] --> RES
  RES --> DRE["Dremel slots chạy queries"]
  DATA["BigQuery managed tables"] -. "không phải chuyển dữ liệu khi đổi model" .-> DRE
~~~

Với autoscaling, BigQuery có thể tăng slots theo demand tới **max reservation size**; số slots autoscaled làm tròn theo bước, phụ thuộc quota/capacity. **Baseline luôn được tính phí theo capacity model**, và autoscaled capacity có quy tắc scale-down/minimum billing tùy tùy chọn (ví dụ fluid scaling). Không suy **số slots thực dùng của một query bằng số slots được tính tiền**.

**Commitments** có thể giảm chi phí cho baseline usage đều, nhưng là quyết định tài chính dài hạn. Hãy đo **job slot-ms, peak concurrency, pending time và reservation utilization** trước khi mua commitments hoặc nâng max.

### 7.4. Ví dụ tính toán không dùng giá cố định

Giả sử:

- Bảng **1 TiB** được scan đầy đủ **40 lần** trong tháng.
- Một dashboard được tối ưu chỉ đọc **10% partitions** nên giảm xuống khoảng **0,1 TiB/query** khi chọn đúng cột và filter.
- Tần suất 40 queries không đổi.

| Cách truy vấn | Tổng bytes processed minh họa |
|---|---:|
| Scan toàn bộ 1 TiB × 40 | **40 TiB** |
| Scan 0,1 TiB × 40 | **4 TiB** |

Nếu on-demand, tối ưu partition/column có thể giảm query cost đáng kể. Nếu dùng reservations, **giảm scan cũng rút ngắn slot time/giải phóng capacity**, nhưng hóa đơn baseline có thể **không giảm ngay** nếu vẫn giữ cùng baseline slots đã mua.

**Không coi 0,1 TiB là mức được đảm bảo** chỉ bằng WHERE date: phải xem partition thực, số cột dùng, job statistics và bytes billed. Cloud Billing, không phải phép nhân giả định, là nguồn xác nhận hóa đơn.

## 8. Nạp và đọc dữ liệu: managed storage không đồng nghĩa mọi nguồn dữ liệu

| Cách | Luồng dữ liệu | Vai trò storage/compute |
|---|---|---|
| **Batch load job** | Cloud Storage CSV/JSON/Parquet/Avro → BigQuery table | Chuyển thành managed storage, phù hợp dữ liệu định kỳ |
| **Storage Write API/streaming** | Ứng dụng/connector ghi gần thời gian thực | Có quota/phí/phương thức commit và visibility riêng |
| **SQL DML/CTAS/MERGE** | Query → thay đổi BigQuery managed table | Dùng query execution và ghi managed storage |
| **External table / BigLake** | Query trực tiếp data trong Cloud Storage/open table format | Data giữ ở nguồn ngoài; không tự thành Capacitor managed storage |
| **Materialized view** | Lưu và cập nhật kết quả tổng hợp được hỗ trợ | Có storage cho kết quả và compute refresh |
| **Export job** | BigQuery table → Cloud Storage | Đưa dữ liệu ra hệ thống/object storage |

**External table không giống managed BigQuery table:** dữ liệu ngoài Cloud Storage có lifecycle, storage billing và permissions riêng; tốc độ query, caching, thống kê và giới hạn tính năng có thể khác. Nếu cùng một dataset được hỏi liên tục với yêu cầu OLAP cao, đánh giá **load vào managed tables** để tận dụng tối ưu columnar hơn.

### 8.1. Không nhầm BigQuery Storage API

- **BigQuery Storage Read API** cho đọc data hiệu quả sang client/processing frameworks qua streams; **khác** một query SQL không cần máy riêng.
- **BigQuery Storage Write API** phục vụ ghi hàng loạt/streaming theo cơ chế streams/offsets; cần xem chi phí/quota và bảo đảm giao hàng.
- **Cloud Storage** là dịch vụ object storage khác BigQuery managed storage; bucket chứa Parquet không tự biến thành BigQuery table cho tới khi được load hoặc khai báo external table.

### 8.2. BigQuery là OLAP, không phải lựa chọn mặc định cho OLTP

Gửi mỗi request web vào BigQuery để lookup một row nhỏ có thể tạo latency/job overhead và chi phí không phù hợp. Với **Spring Boot orders-api**, ghi giao dịch vào **Cloud SQL/Spanner**; sau đó chuyển event vào Pub/Sub/Dataflow/BigQuery theo SLA dữ liệu. BigQuery có ACID/DML/transactions được hỗ trợ, nhưng **không nên suy rằng mô hình latency, index và lock giống PostgreSQL/MySQL OLTP**.

## 9. Thực hành A — Tạo dataset và managed table phân vùng

**Tiền đề:** project **shop-dev-001** chỉ là tên minh họa, BigQuery API đã bật, có billing/quota và người chạy có quyền tạo dataset, table, query job. Các lệnh có thể tạo tài nguyên và phát sinh phí; chỉ dùng project lab được phê duyệt. Không tạo project/dataset mới nếu đã có tài nguyên cùng tên.

### 9.1. Kiểm tra project và location

~~~bash
gcloud config get-value project
gcloud auth list
bq version
bq ls --project_id=shop-dev-001
~~~

**Location ví dụ:** **asia-southeast1** (Singapore), không phải một bảo đảm “dữ liệu ở Việt Nam”. Hãy chọn region/multi-region thực sự được BigQuery hỗ trợ và đáp ứng residency, data source/consumer locality trước khi tạo.

### 9.2. Tạo dataset

~~~bash
# Tạo dataset chỉ sau khi xác nhận IAM, billing và nơi đặt dữ liệu.
bq --location=asia-southeast1 mk \
  --dataset \
  --description="Lab commerce analytics; non-production data" \
  --label=env:lab \
  shop-dev-001:commerce_analytics

bq show --format=prettyjson shop-dev-001:commerce_analytics
~~~

Sau khi tạo, **dataset location không đổi tại chỗ**. Lệnh bq tạo dataset không tự tạo slot reservation hoặc VM. Một **dataset** là container logic và có thể chứa nhiều tables trong cùng location.

### 9.3. DDL mẫu trong BigQuery Studio (GoogleSQL)

~~~sql
CREATE TABLE IF NOT EXISTS `shop-dev-001.commerce_analytics.orders` (
  order_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  order_date DATE NOT NULL,
  amount NUMERIC NOT NULL,
  region STRING
)
PARTITION BY order_date
CLUSTER BY customer_id
OPTIONS (
  require_partition_filter = TRUE,
  description = 'Orders data for storage/compute lab'
);
~~~

**Giải thích thiết kế:**

- **PARTITION BY order_date** tạo partitions theo ngày, giúp lọc đọc phù hợp thời gian.
- **CLUSTER BY customer_id** giúp giảm block scan khi lọc theo khách hàng; **không** tự tạo một index B-tree như PostgreSQL.
- **require_partition_filter = TRUE** buộc queries đọc bảng có điều kiện filter đủ khả năng prune partition, để hạn chế full scan do quên filter.
- BigQuery quản lý dữ liệu columnar trong managed storage; không cần tạo hay attach một disk.

### 9.4. Ghi vài dòng giả định

~~~sql
INSERT INTO `shop-dev-001.commerce_analytics.orders`
  (order_id, customer_id, order_date, amount, region)
VALUES
  ('ord-001', 'cust-1', DATE '2026-11-17', 120000, 'north'),
  ('ord-002', 'cust-2', DATE '2026-11-17', 350000, 'south'),
  ('ord-003', 'cust-1', DATE '2026-11-18',  80000, 'north'),
  ('ord-004', 'cust-3', DATE '2026-11-18', 200000, 'south'),
  ('ord-005', 'cust-2', DATE '2026-11-19', 150000, 'north');
~~~

**Không chạy INSERT lặp nhiều lần** nếu muốn tổng doanh thu chính xác: BigQuery không tự tạo unique constraint cưỡng chế như Cloud SQL trên mọi bảng. Dùng bảng lab rỗng/kiểm tra row count và quản lý idempotency của ingestion; khóa nghiệp vụ cần được xử lý trong ETL.

### 9.5. Query doanh thu theo vùng

~~~sql
SELECT region, COUNT(*) AS order_count, SUM(amount) AS revenue
FROM `shop-dev-001.commerce_analytics.orders`
WHERE order_date BETWEEN DATE '2026-11-17' AND DATE '2026-11-19'
GROUP BY region
ORDER BY revenue DESC;
~~~

**Kết quả dữ liệu ví dụ:** north = **3 orders / 350.000**, south = **2 orders / 550.000** (đơn vị tiền chỉ minh họa). Tổng **900.000**, năm dòng. Ở bảng vài dòng, bytes billed có **mức tối thiểu theo pricing model**, nên không dùng lab nhỏ để kết luận tiết kiệm bao nhiêu USD bằng partition pruning.

## 10. Thực hành B — Dry run, giới hạn bytes billed và quan sát query plan

### 10.1. Dry run (không thực thi SELECT)

Từ **Cloud Shell/bash**:

~~~bash
bq --location=asia-southeast1 query \
  --use_legacy_sql=false \
  --dry_run \
  'SELECT region, SUM(amount) AS revenue
   FROM `shop-dev-001.commerce_analytics.orders`
   WHERE order_date BETWEEN DATE(2026, 11, 17) AND DATE(2026, 11, 19)
   GROUP BY region'
~~~

**Dry run** kiểm tra SQL và ước lượng **bytes processed** trước khi chạy, không tạo kết quả truy vấn thực. Nó **không cho biết chắc latency, slot-ms hoặc hóa đơn cuối cùng**; clustered tables, materialized views, metadata changes và caching có thể làm thực tế khác ước lượng.

### 10.2. Chạy query với cost guardrail

~~~bash
bq --location=asia-southeast1 query \
  --use_legacy_sql=false \
  --maximum_bytes_billed=104857600 \
  'SELECT region, SUM(amount) AS revenue
   FROM `shop-dev-001.commerce_analytics.orders`
   WHERE order_date BETWEEN DATE(2026, 11, 17) AND DATE(2026, 11, 19)
   GROUP BY region
   ORDER BY revenue DESC'
~~~

**maximum_bytes_billed** ở đây là **100 MiB** (giá trị mô phỏng). Query vượt ước lượng bytes được phép sẽ **thất bại trước khi thực thi và không bị tính phí query**. Nếu dataset thật có dữ liệu lớn, cần chọn ngưỡng theo ngân sách và kích thước thật thay vì sao chép ngưỡng này.

### 10.3. So sánh hai điều kiện

Trên một bảng thực có dữ liệu đủ lớn, so sánh **dry run** và job statistics của:

~~~sql
-- Query 1: khoảng ba ngày, đọc 2 cột có liên quan.
SELECT customer_id, SUM(amount) AS revenue
FROM `shop-dev-001.commerce_analytics.orders`
WHERE order_date BETWEEN DATE '2026-11-17' AND DATE '2026-11-19'
GROUP BY customer_id;

-- Query 2: khoảng một tháng, cùng hai cột và biểu thức.
SELECT customer_id, SUM(amount) AS revenue
FROM `shop-dev-001.commerce_analytics.orders`
WHERE order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-30'
GROUP BY customer_id;
~~~

**Kỳ vọng:** query 1 prune nhiều partitions hơn query 2 khi dữ liệu trải đều theo ngày. Nhưng bảng lab chỉ có dữ liệu ba ngày, có thể **không có chênh lệch đáng kể**. Một bảng trống/nén tốt có kết quả đo khác bảng production; không tự tạo số liệu benchmark giả.

### 10.4. Xem query execution details

Trong **BigQuery Studio → Job information / Execution graph**:

- **Bytes processed / billed:** ước lượng storage data đã quét và giá compute theo on-demand.
- **Slot time:** lượng compute tổng cộng sử dụng; giúp đánh giá workloads theo reservations.
- **Stages**: scan, shuffle, join, aggregation; đọc **shuffle bytes, spill, skew, wait time** nếu khả dụng.
- **Cache hit:** nếu TRUE và query đủ điều kiện, BigQuery trả cached results; không dùng kết quả cache để benchmark compute.

Để benchmark hai câu SQL, hãy lưu lại **dataset size, filter, slot assignment, job location, caching behavior**, đo nhiều lần trong điều kiện tương đương. **Thay query text hoặc dữ liệu có thể vô hiệu hóa cache**; query dùng CURRENT_TIMESTAMP() có thể không được cache.

## 11. Thực hành C — Java BigQuery client với ADC và giới hạn chi phí

Ứng dụng Java có thể gửi một **query job** và nhận kết quả qua **com.google.cloud:google-cloud-bigquery**, dùng Application Default Credentials. Mẫu dưới truy vấn dataset tại **asia-southeast1**; không đòi tải JSON key dài hạn.

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.BigQueryOptions;
import com.google.cloud.bigquery.FieldValueList;
import com.google.cloud.bigquery.JobId;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;
import com.google.cloud.bigquery.TableResult;
import java.util.UUID;

public final class BigQueryRevenueReport {
    private BigQueryRevenueReport() {}

    public static void main(String[] args) throws Exception {
        BigQuery client = BigQueryOptions.newBuilder()
            .setProjectId("shop-dev-001")
            .build()
            .getService(); // ADC của local/Cloud Run/GKE

        String sql = "SELECT region, SUM(amount) AS revenue "
            + "FROM `shop-dev-001.commerce_analytics.orders` "
            + "WHERE order_date BETWEEN @from_date AND @to_date "
            + "GROUP BY region ORDER BY revenue DESC";

        QueryJobConfiguration config = QueryJobConfiguration.newBuilder(sql)
            .setUseLegacySql(false)
            .addNamedParameter("from_date",
                QueryParameterValue.date("2026-11-17"))
            .addNamedParameter("to_date",
                QueryParameterValue.date("2026-11-19"))
            .setMaximumBytesBilled(104857600L)
            .build();

        JobId jobId = JobId.newBuilder()
            .setProject("shop-dev-001")
            .setLocation("asia-southeast1")
            .setJob("revenue_" + UUID.randomUUID().toString().replace("-", "_"))
            .build();

        TableResult results = client.query(config, jobId);
        for (FieldValueList row : results.iterateAll()) {
            System.out.println(row.get("region").getStringValue()
                + ": " + row.get("revenue").getNumericValue());
        }
    }
}
~~~

**Điều kiện để chạy:** Java 21, thư viện BigQuery được chọn phiên bản tương thích, ADC có **bigquery.jobs.create** tại project chạy job và quyền đọc bảng, dataset/tables đã tạo. Đoạn ví dụ dùng query ngắn; production cần **deadline, retry/cancel job, paging/large result handling và monitoring**. Hãy kiểm tra tính tương thích của thư viện khi nâng version.

### 11.1. Tại sao Java chỉ định JobId location?

Với client Java, khi dataset ở location ngoài **US/EU**, dùng overload query với **JobId có location rõ ràng** giúp tránh gửi query vào sai vị trí. **Vị trí dataset và vị trí job phải tương thích**; vị trí Cloud Run service không tự động xác định BigQuery query location.

**Không tạo BigQuery client/connection mới cho từng HTTP request.** Với báo cáo lớn, chạy batch/asynchronous jobs, lưu destination table, trả job status và xử lý quota/throttling thay vì giữ một HTTP request chờ hàng phút.

## 12. IAM, mã hóa, dữ liệu nhạy cảm và ranh giới trách nhiệm

Tách storage và compute tạo ra hai nhóm quyền không nên gộp: **người tạo query job** và **người được phép đọc/chỉnh dữ liệu**.

| Principal | Quyền cần thiết | Không tự động có |
|---|---|---|
| **Analyst** | Tạo jobs tại project chạy query; đọc dataset/table được phân quyền | Xóa dataset, cấp IAM rộng |
| **Java Cloud Run runtime SA** | Tạo query job và đọc tables phục vụ nghiệp vụ | BigQuery Admin hoặc Owner |
| **Data engineer / pipeline** | Tạo/update tables/partitions và load data | Quyền đọc dữ liệu nhạy cảm ngoài phạm vi |
| **Capacity administrator** | Quản lý reservations, assignments, commitments | Truy cập dữ liệu trong bảng nếu không được cấp |
| **Security/metadata viewer** | Xem metadata, audit logs theo nhiệm vụ | Đọc mọi dòng dữ liệu |

### 12.1. Ví dụ IAM tối thiểu tương đối

- **roles/bigquery.jobUser** tại project thực thi cho quyền **bigquery.jobs.create**.
- **roles/bigquery.dataViewer** tại dataset chứa bảng cần SELECT.
- **roles/bigquery.dataEditor** chỉ cho principal cần ghi/quản lý dữ liệu; tránh cấp cho analyst chỉ đọc.
- **roles/bigquery.resourceAdmin** (hoặc quyền cụ thể) cho người quản lý slots/reservations, **không** cho Cloud Run runtime bình thường.

Nếu project chạy job khác project lưu data, cần cấp **jobUser ở project chạy query** và **dataViewer tại dataset nguồn**. Query billing thường thuộc **project chạy job** (hoặc capacity reservation/billing arrangement tương ứng), không mặc định thuộc project sở hữu table.

**Server identity:** Cloud Run dùng runtime service account; GKE dùng Workload Identity Federation for GKE. **Không đặt JSON private key** trong Docker image, Git hoặc notebook chia sẻ. ADC không cấp tự động quyền dữ liệu; nó chỉ tìm principal để BigQuery kiểm tra IAM.

### 12.2. Bảo mật không dừng ở dataset

| Lớp | Công cụ | Cần nhớ |
|---|---|---|
| Dữ liệu cấp dataset/table | IAM/resource policies | Mỗi table/project có thể có owner khác |
| Cột nhạy cảm | Policy tags, column-level security/data masking | Cần review quyền đọc cột |
| Dòng dữ liệu | Row-level access policies | Không dùng dataset Viewer để thay row filtering |
| Storage encryption | Google-managed encryption; CMEK khi yêu cầu | CMEK key availability ảnh hưởng truy cập |
| Data egress | VPC Service Controls, locations, export permissions | IAM không kiểm soát một mình mọi đường egress |
| Audit | Cloud Audit Logs và job history | Chú ý Data Access logs/retention/PII trong query text |

**Location không tự động là “bảo mật dữ liệu”.** Một analyst có quyền query có thể export kết quả tới nơi khác nếu chính sách cho phép. Kết hợp IAM, org policies, dataset locations, CMEK, policy tags và kiểm soát export theo data classification.

### 12.3. Chi phí query có thể phát sinh dù dữ liệu không cùng project

Nếu analyst ở **analytics-project** query bảng từ **data-project**, billing, IAM và reservation assignment là những quyết định độc lập. Không cấp người dùng **Owner** chỉ để qua lỗi jobUser hoặc dataViewer. Thử nghiệm negative IAM trên staging để chắc rằng principal không thể đọc dữ liệu tài chính ngoài vai trò.

## 13. Quan sát storage và compute qua BigQuery INFORMATION_SCHEMA

BigQuery cung cấp metadata views để quan sát **jobs**, **slots** và **storage**. Những views này có permissions và location scope riêng; không mặc định miễn phí mọi truy vấn metadata.

### 13.1. Query jobs theo region

Trong BigQuery Studio, chọn **query location asia-southeast1**:

~~~sql
SELECT
  job_id,
  creation_time,
  state,
  total_bytes_processed,
  total_bytes_billed,
  total_slot_ms,
  cache_hit,
  reservation_id
FROM `shop-dev-001.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY'
  AND (statement_type IS NULL OR statement_type != 'SCRIPT')
ORDER BY creation_time DESC
LIMIT 50;
~~~

**Đọc đúng dữ liệu:**

- **total_bytes_processed**: lượng data được xử lý, không phải dung lượng table đang lưu.
- **total_bytes_billed**: lượng data được tính tiền theo logic on-demand khi áp dụng; có thể **0** do cache hoặc pricing model; không dùng một field này để tái tạo đầy đủ hóa đơn reservations.
- **total_slot_ms**: tổng mức compute được sử dụng bởi job; **không phải baseline slots** đang thanh toán.
- **cache_hit**: cho biết kết quả được lấy từ query cache.
- **reservation_id**: giúp nhận biết slot reservation tương ứng khi có assignment.

Với jobs còn PENDING/RUNNING, một số fields có thể NULL hoặc chưa đủ giá trị. **INFORMATION_SCHEMA.JOBS_BY_PROJECT** dùng region qualifier và query location tương ứng; dữ liệu truy vấn phụ thuộc quyền xem jobs của principal.

### 13.2. Thống kê dung lượng managed tables

~~~sql
SELECT
  table_schema,
  table_name,
  total_rows,
  active_logical_bytes,
  long_term_logical_bytes,
  active_physical_bytes,
  long_term_physical_bytes,
  time_travel_physical_bytes
FROM `shop-dev-001.region-asia-southeast1.INFORMATION_SCHEMA.TABLE_STORAGE_BY_PROJECT`
WHERE table_schema = 'commerce_analytics'
ORDER BY active_logical_bytes DESC;
~~~

Các fields **logical** và **physical** phục vụ so sánh mô hình storage pricing, không cộng hai giá trị rồi coi là hóa đơn. **TABLE_STORAGE views có độ trễ cập nhật**; số lượng bytes/partitions có thể khác UI billing snapshot nhất thời. Các table snapshots/clones có thể biểu diễn đầy đủ bytes về mặt thông tin trong khi billing tính delta theo cơ chế riêng.

### 13.3. Chỉ số vận hành cần theo dõi

| Chỉ số | Dùng để phát hiện |
|---|---|
| **Query latency p95/p99**, pending time | BI chậm, slot contention, queueing |
| **Bytes processed/billed** | SELECT * hoặc filter không prune partitions |
| **Total slot-ms, slot utilization** | Cơ hội tối ưu SQL hoặc điều chỉnh capacity |
| **Reservation baseline/autoscale slots** | Slot capacity tính phí và tình trạng scale |
| **Shuffle bytes/spill/skew** | Join/group lớn, data skew |
| **Table logical/physical bytes** | Storage growth, nén, long-term savings |
| **Failed jobs/permission errors** | SQL, quota, IAM, location mismatch |
| **Billing service/SKU** | Chênh lệch giữa ước lượng job và chi phí thực |

Với reservations, dùng **BigQuery Capacity Management / Slot Estimator** và reservation metadata/Monitoring để xem **allocated vs utilized slots**. **Không lấy tổng job slot-ms làm đúng hóa đơn autoscaling**, vì autoscaling được tính theo capacity được cấp và quy tắc billing riêng.

## 14. Tính sẵn sàng, giữ dữ liệu và quản lý vòng đời

**BigQuery serverless không đồng nghĩa miễn nhiễm sự cố hoặc thao tác sai.** Hãy phân biệt:

- **Durability/replication managed storage**: Google quản lý hạ tầng và chống nhiều lỗi phần cứng.
- **Availability/latency compute**: jobs vẫn có thể queue, fail hoặc chậm vì quota, region issue, slots hoặc câu SQL không hiệu quả.
- **Time travel/fail-safe**: giúp phục hồi những thay đổi/xóa gần đây trong cửa sổ đủ điều kiện; **không phải lưu trữ bất biến dài hạn**.
- **Table snapshots/copies/backups/data exports**: hỗ trợ retention/DR theo kiến trúc và tính năng được hỗ trợ.
- **Cross-region dataset replication/managed disaster recovery**: tính năng có điều kiện, cần cấu hình/chi phí và quy trình failover riêng; không bật tự động cho mọi project.

### 14.1. Runbook cho thao tác DELETE nhầm

1. Dừng job/pipeline đang xóa dữ liệu sai; giữ job ID, thời điểm UTC và SQL.
2. Xác định dataset/table, **time travel window**, quyền khôi phục và các thay đổi xảy ra sau đó.
3. Tạo bản phục hồi vào **table/dataset mới** qua cơ chế time travel/restore được hỗ trợ, không ghi đè production ngay.
4. Kiểm tra row count, checksum, business invariants và schema.
5. Chuyển downstream readers theo kế hoạch, lưu forensic evidence và báo cáo RPO/RTO.

Nếu sự cố ngoài **time travel window**, cần backup/export/DR plan khác; fail-safe 7 ngày **không phải giao diện tự restore tức thì**, có sự tham gia hỗ trợ theo điều kiện.

### 14.2. Chiến lược tránh dữ liệu quá hạn

Đặt **partition expiration/table expiration/lifecycle** theo yêu cầu pháp lý và nghiệp vụ. Dữ liệu quá hạn vẫn có thể xuất hiện trong cửa sổ time travel/fail-safe tùy chế độ lưu và tính phí. **Không dùng việc đổi storage billing model** làm biện pháp xóa dữ liệu; thay đổi billing model không chuyển dữ liệu hay reset retention.

## 15. Troubleshooting: nhận diện đúng storage hay compute

| Hiện tượng | Khả năng đầu tiên | Kiểm tra |
|---|---|---|
| **Dataset not found in location US** | Job sai location, không phải mất table | Dataset location và **bq --location** / JobId |
| **Access Denied: Table** | Principal không có quyền đọc nguồn | Dataset/table IAM, row/column policies |
| **Access Denied: Project / jobs.create** | Project chạy job thiếu role jobUser | Job project và service identity |
| **Resources exceeded during query execution** | Shuffle/aggregation lớn, skew, memory constraints | Execution graph, partition/index design |
| Query chạy rất chậm, pending dài | Thiếu slots, queue hoặc quota | Slot utilization, reservation assignment, job priority |
| Query scan quá nhiều bytes | SELECT *, thiếu partition filter hoặc WHERE không prune | Query validator/dry run, schema, partitions |
| **maximum bytes billed exceeded** | Query ước lượng vượt guardrail | Dry run và tối ưu; chỉ tăng ngưỡng sau review |
| Query cho kết quả cũ dù SQL lặp lại | Cached result, hoặc ETL chưa cập nhật | cache_hit, last modified, freshness SLO |
| Mỗi lần chạy query vẫn có phí dù bảng không đổi | Cache không đủ điều kiện hoặc khác text | Query cache rules, nondeterministic functions |
| Storage bill tăng nhưng jobs ít | Dữ liệu/index/retention/physical time travel tăng | TABLE_STORAGE views, dataset billing model |
| Reservation baseline tốn phí khi idle | Capacity đã cấp vẫn được tính tiền | Baseline/autoscale pricing và assignment |
| Query chuyển thành on-demand ngoài ý muốn | Job location/assignment khác reservation | Project/folder assignment, reservation location |
| Java Cloud Run 403 nhưng console user chạy được | Runtime ADC khác user principal | Cloud Run service account, IAM, job project |
| Join từ dataset US và asia-southeast1 thất bại | BigQuery yêu cầu query data locations tương thích | Copy/replicate/migrate trước, không join trực tiếp |
| Streaming data vừa ghi chưa hiện trong truy vấn | Ingestion/commit semantics và pipeline delay | Storage Write API stream mode, job state, source telemetry |
| Dashboard chỉ chậm một khách hàng | Filter thiếu partition prune hoặc data skew | Query plan, cluster keys, job stats |

### 15.1. Cách xử lý theo lớp

~~~mermaid
flowchart TD
    ISSUE["BigQuery query lỗi hoặc chậm"] --> CODE{"Mã lỗi / trạng thái?"}
    CODE -->|"403"| IAM["IAM: jobUser + dataViewer + runtime SA"]
    CODE -->|"Not found in location"| LOC["So dataset location, job location, reservation"]
    CODE -->|"Bytes billed exceeded"| BYTES["Dry run, partition/column pruning"]
    CODE -->|"Slow / resources exceeded"| PLAN["Execution graph, skew/shuffle/slots"]
    CODE -->|"Wrong results"| DATA["Ingestion freshness, SQL semantics, cache"]
    IAM --> VERIFY["Test lại + ghi job ID/metrics"]
    LOC --> VERIFY
    BYTES --> VERIFY
    PLAN --> VERIFY
    DATA --> VERIFY
~~~

**Không sửa tất cả bằng cách cấp BigQuery Admin, thêm slot reservations hoặc tăng maximum bytes billed.** Ba cách đó có thể tăng quyền hoặc phí mà không giải quyết sai location, filter hoặc data skew.

## 16. Case study: dữ liệu bán hàng 20 TB và hai loại workload

Doanh nghiệp **Bình Minh** có 20 TB data lịch sử, đội BI dùng Looker, còn Java orders-api phát sinh 2 triệu events/ngày. Có ba nhóm workload:

| Workload | Yêu cầu | Quyết định ban đầu |
|---|---|---|
| **OLTP orders-api** | Ghi mỗi đơn hàng nhanh, bảo đảm transaction | Cloud SQL/Spanner, **không** BigQuery làm primary OLTP DB |
| **ETL hằng đêm** | Load và aggregate theo partition order_date | Pub/Sub/Dataflow hoặc batch GCS → BigQuery managed tables |
| **BI dashboards** | Nhiều queries trong giờ hành chính | Query partitioned/clustered tables; cân nhắc reservations khi tải đều |

### 16.1. Vì sao không mua compute theo dung lượng 20 TB?

BigQuery storage có thể chứa 20 TB ngay cả khi ETL chạy 1 lần/ngày. Khi BI workload tăng, compute tăng qua slots/on-demand hoặc reservation **mà không phải copy 20 TB sang một cluster máy chủ lớn hơn**.

Trong môi trường có data residency, dataset và reservation đặt đúng location; Cloud Run Java và bucket GCS đặt gần để tránh latency/egress bất ngờ. **Thay pricing model không thay database schema hay vị trí dữ liệu**, nhưng cần kiểm tra IAM/assignments và công cụ báo cáo.

### 16.2. Quy trình phát hành

~~~mermaid
flowchart TD
    SOURCE["Cloud SQL + Pub/Sub + Cloud Storage"] --> INGEST["Load / streaming / Dataflow"]
    INGEST --> TABLE["BigQuery managed orders table<br/>partition by date"]
    TABLE --> ETL["Scheduled queries / ETL"]
    TABLE --> BI["Looker dashboard / BI"]
    ETL --> OUT["Daily revenue table"]
    BI --> WATCH["Job metrics + Billing + SLO"]
    OUT --> WATCH
    WATCH --> TUNE{"Scan/slot/latency vượt mục tiêu?"}
    TUNE -->|Có| FIX["Filter/partition/index of data layout<br/>hoặc reservation sizing"]
    TUNE -->|Không| OK["Tiếp tục giám sát"]
~~~

### 16.3. So sánh hai kịch bản chi phí

**Kịch bản A – on-demand:** tải BI dao động và analyst chạy ít queries. Ưu tiên **dry run, maximum bytes billed, giới hạn quota** và giảm bytes scan.

**Kịch bản B – reservation:** BI liên tục, nhiều người chạy queries đồng thời, có peak xác định. Đo **total_slot_ms, pending time, p95** và cân nhắc **baseline + autoscaling**; đặt max slots, SLO và dự toán tài chính. Chuyển workloads vào reservation theo assignment, không di chuyển tables.

**Quyết định dựa trên telemetry:** không có ngưỡng TB lưu trữ nào tự động buộc phải dùng reservations. Mô hình trả tiền cần dựa vào **queries, scan size, concurrency, hiệu suất và thời gian sử dụng compute**.

### 16.4. Nghiệm thu theo chiều storage và compute

| Kiểm thử | Kỳ vọng |
|---|---|
| Tạo dataset tại asia-southeast1 | Location đúng và bất biến tại chỗ |
| Load data vào table phân vùng | Dữ liệu xuất hiện theo partitions |
| SQL chỉ đọc ba ngày | Pruning phù hợp, bytes processed giảm trên dataset đủ lớn |
| Java query có JobId location | Chạy tại đúng region nếu IAM hợp lệ |
| Thay on-demand → reservation | Managed tables không phải tạo lại |
| Dùng cached query | cache_hit được xác nhận, không giả định cache luôn có |
| Tách analyst khỏi quyền ghi | User đọc được table có quyền, không xóa dataset |
| Slot baseline không có query | Có thể vẫn phát sinh phí capacity |
| Restore table xóa nhầm | Thành công trong retention window hợp lệ nếu đã chuẩn bị |
| Billing reports | Phân biệt storage bytes và compute SKUs |

## 17. Bài tập và đáp án gợi ý

### Bài tập A — Phân biệt storage và compute

Một công ty lưu 5 TB logs trên BigQuery nhưng không chạy query trong bảy ngày.

**Hỏi:** BigQuery có phải vẫn cần giữ “năm node Dremel” tương đương 5 TB?

**Đáp án:** **Không.** Managed storage độc lập với việc cấp compute theo số bytes lưu. Dữ liệu vẫn có **storage charges**; on-demand query processing không tiêu thụ khi không chạy query. Nếu đã mua **baseline slots**, capacity vẫn có thể tính phí.

### Bài tập B — Tính slot utilization

Một query chạy 12 giây, total_slot_ms = 96.000.

**Đáp án:** Average slots used ≈ 96.000 / 12.000 = **8 slots**. Đây không phải mức slots cố định trong toàn bộ 12 giây, cũng không phải số lượng node BigQuery.

### Bài tập C — Tại sao SELECT * tốn tiền?

Một table 1 TB có 100 cột. Dashboard chỉ cần ngày, vùng, doanh thu nhưng dùng SELECT *.

**Đáp án:** BigQuery là columnar; **chỉ chọn ba cột cần thiết** và thêm filter trên partition date để giảm scan bytes. **LIMIT 10** không tự bảo đảm giảm bytes processed của SELECT *.

### Bài tập D — Region mismatch

Dataset nằm ở **asia-southeast1** nhưng Java query job được tạo với location **US**.

**Đáp án:** Chọn **JobId location asia-southeast1** và bảo đảm dataset/table cùng location phù hợp. Không thêm IAM Admin để chữa lỗi region.

### Bài tập E — Mô hình phí

Một bảng lưu 2 TiB; một query scan 0,25 TiB và chạy 100 lần không được cache.

**Đáp án:** Query total processed là **25 TiB** theo giả định, **không phải 2 TiB**. Storage vẫn là 2 TiB theo mô hình billing tương ứng; phí query on-demand dựa bytes billed/mức tối thiểu/giá tại location, không đơn giản là dung lượng storage.

### Bài tập F — Reservation có miễn phí khi idle không?

Nhóm tạo reservation 300 baseline slots nhưng BI chỉ chạy một giờ/ngày.

**Đáp án:** **Baseline capacity** được tính tiền dù không có queries. Cân nhắc giảm baseline, dùng autoscaling phù hợp hoặc quay lại on-demand theo đặc tính workload và bảng giá.

### Bài tập G — Read cached result

Một query chạy lại và hiển thị total_bytes_billed = 0, cache_hit = TRUE.

**Đáp án:** Query có khả năng đã lấy từ **query result cache**, không chạy lại scan/compute. Không dùng số liệu cache hit để đo performance của SQL dưới full scan; cache còn phụ thuộc data changes và giới hạn áp dụng.

### Bài tập H — IAM cho Java

Cloud Run service account có **roles/bigquery.dataViewer** trên dataset nhưng gọi job API nhận **bigquery.jobs.create permission denied**.

**Đáp án:** Thiếu quyền **tạo job** tại project thực thi, ví dụ **roles/bigquery.jobUser**. DataViewer chỉ cấp đọc data, không tự cấp jobs.create. Không cần BigQuery Admin.

### Bài tập I — Khác biệt managed/external storage

Một bucket Cloud Storage có 20 TB Parquet; nhóm khai báo BigLake external table rồi cho rằng bytes đã chuyển vào Colossus và bucket không còn tính phí.

**Đáp án:** Sai. **External table đọc dữ liệu tại nguồn ngoài**; bucket vẫn giữ/tính phí lưu và quyền truy cập riêng. Muốn managed BigQuery storage phải **load/copy data** vào BigQuery table phù hợp, đánh giá chi phí chuyển dữ liệu.

### Bài tập J — Khôi phục dữ liệu

Một bảng bị xóa 3 ngày trước. Dataset có time travel window mặc định 7 ngày.

**Đáp án:** Có thể dùng chức năng **time travel/table restore** theo điều kiện để khôi phục ra bảng mới, kiểm tra toàn vẹn và chuyển downstream. Không coi **fail-safe** là endpoint đọc dữ liệu tức thời hoặc một bản backup độc lập ngoài project.

### Bài tập K — Chọn cách tối ưu trước

Query mỗi lần scan 8 TB nhưng p95 cao; nhóm đề xuất mua thêm 1.000 slots ngay.

**Đáp án:** Trước tiên xem **query plan, partition/cluster pruning, SELECT * và shuffle/skew**. Tối ưu SQL/data layout có thể giảm cả bytes và slot time. Chỉ điều chỉnh reservation sau khi đo mức sử dụng, queueing và SLO.

## 18. Tổng kết và tài liệu tham khảo

**Sáu điểm cần nhớ:**

1. **Colossus/Capacitor** quản lý columnar storage; **Dremel/slots** thực thi queries; mạng **Jupiter** giúp kết nối hai lớp với băng thông cao.
2. **Storage và compute mở rộng độc lập**, nhưng vẫn chịu ràng buộc **location, IAM, quota, data layout và hóa đơn**.
3. **On-demand** thường tính theo **bytes billed** của query; **capacity reservations** tính theo **slot capacity đã cấp theo thời gian**, gắn BigQuery editions.
4. **Partition pruning, column projection, clustering, query plan và caching** quyết định bytes processed và hiệu năng; **LIMIT** không phải cách tránh full scan đáng tin cậy.
5. **Managed BigQuery storage khác Cloud Storage/external tables**; ingestion, streaming, caching, backups và BI có semantics riêng.
6. **Dry run, maximum bytes billed, INFORMATION_SCHEMA, IAM least privilege và Billing** tạo nền tảng vận hành an toàn và tối ưu chi phí cho Java/cloud analytics.

**Tài liệu Google Cloud chính thức:**

1. [BigQuery overview và architecture](https://docs.cloud.google.com/bigquery/docs/introduction) — hai lớp storage/compute và khả năng serverless.
2. [Separation of storage and compute in BigQuery](https://cloud.google.com/blog/products/bigquery/separation-of-storage-and-compute-in-bigquery) — Dremel, Colossus, Jupiter.
3. [Overview of BigQuery storage](https://docs.cloud.google.com/bigquery/docs/storage_overview) — managed columnar storage, ingestion và client reads.
4. [Understand slots](https://docs.cloud.google.com/bigquery/docs/slots) — slot-ms, on-demand/capacity, baseline và autoscaling.
5. [BigQuery editions](https://docs.cloud.google.com/bigquery/docs/editions-intro) — Standard, Enterprise, Enterprise Plus.
6. [Workload management và reservations](https://docs.cloud.google.com/bigquery/docs/reservations-intro) — assignment, location và compute budgeting.
7. [BigQuery datasets](https://docs.cloud.google.com/bigquery/docs/datasets-intro) — dataset location, storage billing models và retention.
8. [BigQuery locations](https://docs.cloud.google.com/bigquery/docs/locations) — job/data locality.
9. [Partitioned tables](https://docs.cloud.google.com/bigquery/docs/creating-partitioned-tables) — DDL partition/filter options.
10. [Partition pruning](https://docs.cloud.google.com/bigquery/docs/querying-partitioned-tables) — giới hạn scan bằng partition filters.
11. [Run queries và dry run](https://docs.cloud.google.com/bigquery/docs/running-queries) — execution và estimates.
12. [Cached query results](https://docs.cloud.google.com/bigquery/docs/cached-results) — cache hit, phí và giới hạn.
13. [INFORMATION_SCHEMA.JOBS](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs) — bytes/slots và job metadata.
14. [INFORMATION_SCHEMA.TABLE_STORAGE](https://docs.cloud.google.com/bigquery/docs/information-schema-table-storage) — logical và physical bytes.
15. [Data retention và time travel](https://docs.cloud.google.com/bigquery/docs/time-travel) — phục hồi dữ liệu.
16. [bq command-line reference](https://docs.cloud.google.com/bigquery/docs/reference/bq-cli-reference) — bq mk/query/show và giới hạn bytes billed.
17. [Java query sample](https://docs.cloud.google.com/bigquery/docs/samples/bigquery-query) — ADC và QueryJobConfiguration.
18. [Java BigQuery client query API](https://docs.cloud.google.com/java/docs/reference/google-cloud-bigquery/latest/com.google.cloud.bigquery.BigQuery) — job location và client overloads.
