# Spanner và lựa chọn cơ sở dữ liệu quan hệ phân tán

Một nền tảng thương mại điện tử có dịch vụ Java trên Cloud Run, GKE và Compute Engine. Khi chỉ có một region và lượng giao dịch vừa phải, Cloud SQL hoặc AlloyDB có thể đáp ứng tốt. Nhưng khi ứng dụng cần **cơ sở dữ liệu quan hệ nhất quán, ghi đồng thời trên nhiều máy chủ, tăng quy mô theo chiều ngang và khả dụng tại nhiều khu vực địa lý**, nhóm phải cân nhắc **Google Cloud Spanner**.

**Spanner** là dịch vụ cơ sở dữ liệu phân tán được quản lý, kết hợp **bảng/SQL, giao dịch ACID, strong consistency** với việc phân bố dữ liệu và sao chép trên nhiều máy. Nó không phải “Cloud SQL có thêm vài read replicas”: mô hình khóa chính, transaction, địa lý bản sao, khả năng tương thích SQL, độ trễ và chi phí đều khác.

Bài thuộc chương **Spanner** của mô-đun `CLOUD_PROVIDERS_GCP`, kết nối quyết định lưu trữ với quản trị project/IAM/VPC, triển khai ứng dụng, tự động hóa phát hành, giám sát độ tin cậy và kiểm soát chi phí. Ví dụ sử dụng **GoogleSQL dialect**, Java 21 và project lab; nơi nào dùng PostgreSQL dialect sẽ được ghi rõ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Spanner là **distributed relational database** và phân biệt nó với Cloud SQL/AlloyDB.
2. Mô tả instance, database, splits, replicas, leader và các cấu hình **regional/dual-region/multi-region**.
3. Hiểu **ACID, serializable/external consistency**, strong read, stale read và giao dịch bị abort.
4. Chọn khóa chính tránh hotspot, tổ chức quan hệ và secondary indexes phù hợp.
5. Phân biệt **GoogleSQL** và **PostgreSQL dialect**, kể cả giới hạn tương thích.
6. Xác định khi nào nên chọn Spanner, Cloud SQL, AlloyDB, Firestore hoặc Bigtable theo workload.
7. Tạo database lab bằng `gcloud`, chạy SQL và hiểu một ví dụ transaction Java.
8. Đánh giá IAM, capacity, performance, bảo mật, backup và chi phí trước production.

## 1. Từ cơ sở dữ liệu quan hệ truyền thống đến Spanner

Một RDBMS thông thường có tables, primary keys, indexes, joins và transactions. Với dữ liệu tăng nhanh, nhóm thường phải **nâng cấu hình máy, thêm read replicas hoặc tự sharding**. Tự sharding đẩy bài toán routing, giao dịch xuyên shard, rebalance và khôi phục lỗi về phía ứng dụng.

Spanner phân bố dữ liệu theo các **key ranges (splits)**, tự quản lý nhiều replicas và cung cấp SQL/transaction qua một dịch vụ thống nhất.

~~~mermaid
flowchart LR
    API["Java services<br/>Cloud Run / GKE / VM"] --> CLIENT["Spanner client library<br/>sessions / RPC"]
    CLIENT --> DB["Spanner database<br/>Orders, Customers, Payments"]
    DB --> S1["Split: key range A"]
    DB --> S2["Split: key range B"]
    DB --> S3["Split: key range C"]
    S1 --> R["Replicated storage + consensus"]
    S2 --> R
    S3 --> R
~~~

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Instance** | Cấu hình vùng địa lý, edition, compute capacity; chứa nhiều databases |
| **Database** | Tables, indexes, schemas và data; chọn **một SQL dialect** khi tạo |
| **Split** | Một khoảng dữ liệu theo thứ tự khóa, có thể tự chia/chuyển để phân tải |
| **Replica** | Bản sao dữ liệu ở vị trí thuộc instance configuration |
| **Leader** | Thành phần điều phối ghi và consensus của dữ liệu tương ứng |
| **Processing units (PU)** | Đơn vị cấp compute; **1 node = 1.000 PU** |
| **GoogleSQL/PostgreSQL dialect** | Hai cú pháp SQL được Spanner hỗ trợ, không phải hai engine lưu trữ độc lập |

**Điểm cốt lõi:** Spanner giải quyết nhiều vấn đề phân bố dữ liệu ở tầng dịch vụ, **nhưng schema và truy vấn tệ vẫn gây hotspot, transaction abort hoặc chi phí cao**.

## 2. Kiến trúc phân tán và tính sẵn sàng

Spanner tự sao chép đồng bộ dữ liệu theo topology instance. Với **regional configuration cơ bản**, dữ liệu được sao chép tới **ba read-write replicas ở các zone khác nhau trong cùng region**. Khi mất một zone, các replica còn lại có thể duy trì dịch vụ theo điều kiện quorum/khả dụng.

~~~mermaid
flowchart TD
    APP["Ứng dụng / Spanner API"] --> SP["Spanner instance: regional-asia-southeast1"]
    SP --> A["Replica A<br/>Zone 1"]
    SP --> B["Replica B<br/>Zone 2"]
    SP --> C["Replica C<br/>Zone 3"]
    A <-->|"Consensus/replication"| B
    B <-->|"Consensus/replication"| C
~~~

Trong cấu hình **multi-region**, Spanner phân bố bản sao theo nhiều khu vực và dùng cơ chế consensus để duy trì nhất quán. Giao dịch ghi phải phối hợp bản sao, nên **latency ghi có thể tăng** khi leader/quorum nằm xa ứng dụng; đọc mạnh từ xa cũng có chi phí mạng/độ trễ nhất định.

### 2.1. Ba phạm vi triển khai

| Cấu hình | Phạm vi địa lý | Lựa chọn/đánh đổi |
| --- | --- | --- |
| **Regional** | Nhiều zone trong **một region** | Thường có write latency thấp nhất khi ứng dụng ở gần; không bảo vệ được mọi sự cố toàn region |
| **Dual-region** | **Hai region trong cùng quốc gia**, theo cấu hình hỗ trợ | Khả dụng liên vùng với độ trễ/chi phí cao hơn; yêu cầu **Enterprise Plus** |
| **Multi-region** | Nhiều region theo topology có sẵn | Phù hợp ứng dụng địa lý rộng/HA cao; cần **Enterprise Plus**, lựa chọn leader và cân nhắc write latency |

**Không tự hiểu multi-region là mỗi dòng dữ liệu luôn có một primary độc lập ở mọi region.** Topology xác định vị trí bản sao/leader và đường đi transaction. Nếu có yêu cầu đặt **từng nhóm dữ liệu ở vùng riêng**, Spanner có **geo-partitioning** trong Enterprise Plus ở trạng thái/tính năng hỗ trợ cụ thể; nó cần thiết kế schema và tuân thủ riêng, không tự bật chỉ bằng chọn multi-region.

### 2.2. Availability không đồng nghĩa zero outage

Spanner có SLA tùy **edition và cấu hình**: Standard/Enterprise regional có mức công bố **99,99%**, Enterprise Plus multi-region có thể đạt **tới 99,999%** nếu đáp ứng điều kiện. Đây là **mức SLA có điều kiện**, không phải lời hứa mọi truy vấn không lỗi. App vẫn cần timeout, retry/backoff, theo dõi latency và recovery runbook.

## 3. Vì sao Spanner vẫn là cơ sở dữ liệu quan hệ?

Spanner có:

- **Schema có kiểu dữ liệu** và **primary keys**.
- SQL để `SELECT`, `JOIN`, aggregate, lọc và sắp xếp.
- **Indexes** và quan hệ qua **foreign keys/interleaved tables** theo dialect/tính năng.
- **ACID transactions**, kể cả thay đổi nhiều rows/tables trong một database.
- **Strong reads**, snapshot read-only transactions và **stale reads** khi ứng dụng cho phép.

Không nên gọi Spanner là NoSQL chỉ vì dữ liệu được sharding. Sự khác biệt với hệ quan hệ truyền thống nằm ở **cách data được phân bố và giao dịch được phối hợp**.

### 3.1. Một transaction có thể đi qua nhiều splits

Giả sử có hai tài khoản trong bảng `Accounts` và phải chuyển 100.000 đồng từ A sang B. Với Spanner read-write transaction, hai updates có thể commit **nguyên tử** dù các rows nằm trên các splits khác nhau. Không cần ứng dụng tự thiết kế two-phase commit giữa những shard databases.

**Giới hạn:** nếu transaction còn gọi hệ thống ngoài (Pub/Sub publish, gửi email, thanh toán API), side effect đó **không nằm trong cùng Spanner transaction**. Dùng transactional outbox, idempotency key hoặc reconciliation khi cần nhất quán xuyên hệ thống.

## 4. Strong consistency, serializability và external consistency

Spanner mặc định dùng **serializable isolation** cho read-write transactions, bảo đảm các transaction được commit như thể thực hiện theo một thứ tự phù hợp. Với **external consistency**, thứ tự commit còn phù hợp với quan hệ thời gian thực: nếu transaction A hoàn tất trước khi B bắt đầu, B không được quan sát một thứ tự đảo ngược bất hợp lý.

Spanner phối hợp **TrueTime**, commit timestamps và consensus để cung cấp tính chất này. Đây là lý do dịch vụ có thể vừa có transactions phân tán vừa duy trì tính nhất quán mạnh.

| Kiểu truy cập | Khi nên dùng |
| --- | --- |
| **Read-write transaction** | Chuyển tiền, giữ tồn kho, thay đổi trạng thái nhiều rows/tables cần atomicity |
| **Strong read** | Đọc dữ liệu mới nhất theo consistency guarantee sau khi ghi đã hoàn tất |
| **Read-only transaction** | Đọc nhiều bảng trên **cùng snapshot nhất quán**, không cần lock ghi |
| **Stale read** | Báo cáo/cached view chấp nhận dữ liệu cũ để tối ưu latency/capacity theo tình huống |
| **Repeatable read isolation** | Có hỗ trợ với semantics riêng; không tự coi tương đương mặc định serializable |

**Không dùng stale read** để quyết định số dư có đủ thanh toán hoặc lượng tồn kho hiện tại nếu nghiệp vụ yêu cầu dữ liệu mới nhất.

### 4.1. Transaction ABORTED và tự động retry

Hai transactions đồng thời sửa cùng dữ liệu có thể xung đột. Spanner có thể abort một transaction; client library thường **chạy lại callback** trong transaction runner.

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant S as Spanner
    C->>S: Transaction callback lần 1
    S-->>C: ABORTED (conflict)
    C->>S: Client library retry callback
    S-->>C: COMMIT thành công
~~~

Vì callback **có thể chạy nhiều lần**, **không gửi email, thanh toán hoặc Pub/Sub publish trực tiếp bên trong callback** nếu không có idempotency. Giữ transaction ngắn và đặt tác dụng ngoài DB sau commit qua outbox/reliable relay.

## 5. Chọn GoogleSQL hay PostgreSQL dialect?

**Dialect được chọn khi tạo database** và không thể coi việc đổi dialect là một câu lệnh `ALTER DATABASE` thông thường.

| Tiêu chí | GoogleSQL | PostgreSQL dialect |
| --- | --- | --- |
| Ngôn ngữ | SQL theo GoogleSQL của Spanner | Một tập con/ngữ nghĩa tương ứng PostgreSQL được Spanner hỗ trợ |
| Java integration | Spanner Java client, GoogleSQL DDL/SQL | Spanner Java client hoặc công cụ PGAdapter/JDBC theo hỗ trợ |
| Kiểu dữ liệu/cú pháp | `STRING`, `INT64`, DDL `PRIMARY KEY (...)` ngoài định nghĩa bảng | `varchar/text`, `bigint`, kiểu SQL quen thuộc hơn |
| Ứng dụng phù hợp | Nhóm chấp nhận Spanner-native syntax | Nhóm quen PostgreSQL và muốn giảm chi phí học cú pháp |
| Tương thích engine PostgreSQL | **Không** | **Không phải PostgreSQL server đầy đủ** |

**PostgreSQL dialect ≠ Cloud SQL for PostgreSQL**. Spanner không tự hỗ trợ mọi PostgreSQL extension, stored procedure, trigger, catalog, driver hoặc hành vi quản trị engine. **PGAdapter** giúp một số công cụ PostgreSQL kết nối qua giao thức tương thích, nhưng vẫn phải kiểm tra **compatibility matrix, DDL và query semantics** trước migration.

Cả hai dialect dùng cùng lõi Spanner về transactions, replication và scalability. **Không chọn PostgreSQL dialect chỉ vì kỳ vọng nâng chuyển PostgreSQL workload mà không sửa SQL/schema**.

## 6. Thiết kế primary key quyết định khả năng scale

Spanner sắp xếp dữ liệu theo **primary key** và phân chia thành key ranges. Nếu tất cả inserts đi vào “đuôi” một dãy khóa tăng liên tục, chúng có thể cùng dồn tới một split, tạo **hotspot** dù tổng instance còn compute trống.

### 6.1. Ví dụ chưa tốt

~~~sql
-- GoogleSQL. Không khuyến nghị cho bảng insert rất nhiều mỗi giây.
CREATE TABLE Events (
  CreatedAt TIMESTAMP NOT NULL,
  EventId STRING(36) NOT NULL,
  Payload STRING(MAX)
) PRIMARY KEY (CreatedAt, EventId);
~~~

Timestamps tăng dần ở đầu key tạo **hot range**. Tương tự, sequence tăng dần dẫn đầu `OrderId` cũng có thể gây bottleneck.

### 6.2. Ví dụ tốt hơn cho đơn hàng

~~~sql
-- GoogleSQL, giả định OrderId là UUID v4 dạng chuỗi.
CREATE TABLE Orders (
  OrderId STRING(36) NOT NULL,
  CustomerId STRING(36) NOT NULL,
  TotalCents INT64 NOT NULL,
  Status STRING(20) NOT NULL
) PRIMARY KEY (OrderId);
~~~

`OrderId` dạng **UUID v4 đủ phân tán** giúp phân bố inserts tốt hơn. Với multi-tenant workload, có thể dùng `(TenantId, OrderId)` để tăng locality, **nhưng** tenant cực lớn có thể gây hotspot; phân tích access patterns và cân nhắc thêm hash/shard prefix nếu cần.

| Chiến lược key | Lợi ích | Đổi lại |
| --- | --- | --- |
| UUID v4 / khóa ngẫu nhiên | Tránh dồn mọi insert vào một key range | Đọc theo thời gian cần index/query khác |
| Hash prefix/shard ID | Phân tán write load chủ động | Query toàn bộ shards phức tạp hơn |
| Composite key theo tenant | Locality cho query trong tenant | Tenant lớn có thể quá nóng |
| Timestamp tăng dần làm prefix | Dễ scan theo thời gian | Nguy cơ **hotspot** cao với writes liên tục |

### 6.3. Secondary indexes cũng có thể hotspot

Một index có key bắt đầu bằng timestamp tăng liên tục cũng có thể dồn writes vào cuối index, ngay cả khi **base table** dùng UUID v4. Chỉ tạo index cho truy vấn thực sự cần; đánh giá **write amplification, storage** và cách sắp xếp key.

~~~sql
-- Index phục vụ lọc đơn theo khách hàng.
CREATE INDEX OrdersByCustomer
ON Orders(CustomerId)
STORING (Status, TotalCents);
~~~

Một secondary index có **chi phí ghi và lưu trữ**; `STORING` tăng lượng dữ liệu index để giảm lookup về base table. Không tạo hàng chục indexes dựa trên cảm giác.

## 7. Quan hệ dữ liệu, foreign key và interleaving

Spanner có **foreign keys** để giữ toàn vẹn tham chiếu và **interleaved tables** để đặt các bản ghi con gần bản ghi cha trong lưu trữ, khi schema hợp lý.

Ví dụ `Customers` và `Orders`:

- **Foreign key:** bảo đảm `Orders.CustomerId` trỏ tới khách hàng hợp lệ (theo schema).
- **Interleaving:** child primary key chứa prefix parent key để đặt parent/child gần nhau, phù hợp khi thường xuyên đọc cùng nhau.

**Không nên nhầm**: foreign key **không tự đồng nghĩa colocated data**, còn interleaving là quyết định **vật lý/lokal**. Cân nhắc quan hệ một–nhiều khổng lồ, lượng writes tới một parent và kích thước row trước khi dùng interleaving.

## 8. Lựa chọn database: ma trận quyết định

| Tiêu chí | Cloud SQL | AlloyDB | Spanner | Firestore | Bigtable |
| --- | --- | --- | --- | --- | --- |
| Mô hình chính | Managed MySQL/PostgreSQL/SQL Server | PostgreSQL-compatible OLTP/analytics | Distributed relational SQL | Document | Wide-column/key-value |
| Quan hệ, joins, SQL | Có | Có, PostgreSQL ecosystem | Có, GoogleSQL/PostgreSQL dialect | Không theo mô hình relational joins | Không phải SQL OLTP tổng quát |
| Distributed ACID xuyên data splits | Không phải mục tiêu scale chính | Không phải mục tiêu toàn cầu | **Thế mạnh cốt lõi** | Transactions theo semantics tài liệu | Semantics theo row; không giống multi-row RDBMS |
| Scale writes theo chiều ngang | Giới hạn theo single-primary architecture | Write primary theo kiến trúc AlloyDB | **Có**, phụ thuộc schema/capacity | Có, theo document/query patterns | Có, workload key-range phù hợp |
| Multi-region strong consistency | DR/replicas khác semantics | DR/replicas theo sản phẩm | **Có** với topology/edition thích hợp | Theo thiết kế Firestore/region và consistency riêng | Replication semantics khác |
| PostgreSQL ecosystem | Cloud SQL PostgreSQL | **Rất gần PostgreSQL** | Dialect một phần, cần kiểm tra | Không | Không |
| Workload phù hợp | Ứng dụng vừa/nhỏ, migration RDBMS nhanh | PostgreSQL nặng và hiệu năng cao | Giao dịch quan hệ phân tán quy mô lớn | Mobile/web document app | Time-series/key-value throughput cao |
| Chi phí/độ phức tạp | Thường dễ khởi đầu | Cần sizing cluster | Cần thiết kế key/transactions và capacity | Theo operations/storage | Theo nodes/storage/throughput |

**BigQuery** là lựa chọn khác cho **data warehouse/analytics**, không phải database OLTP để commit mỗi đơn hàng. Ngược lại, Spanner có SQL aggregate và analytics capabilities, nhưng **không phải mọi truy vấn BI lớn đều nên chạy trên primary Spanner OLTP**; cân nhắc export/stream sang BigQuery.

### 8.1. Khi nào nên chọn Spanner?

Cân nhắc Spanner nếu nhiều tiêu chí sau đồng thời đúng:

1. Dữ liệu là **quan hệ**, cần joins/constraints/ACID.
2. Ghi/đọc **quy mô lớn**, shard trong RDBMS truyền thống gây gánh nặng vận hành.
3. Sẵn sàng đầu tư thiết kế key, indexes, transaction patterns phù hợp phân tán.
4. Cần **strong consistency** xuyên dữ liệu phân bố và, với edition/topology phù hợp, nhiều regions.
5. SLO availability và nhu cầu tăng trưởng đủ để biện minh cho **compute/replication costs**.

### 8.2. Khi nào chưa nên chọn?

- Một ứng dụng CRUD Java với một primary DB, yêu cầu scale vừa phải, tận dụng PostgreSQL extensions/stored procedures: **Cloud SQL PostgreSQL hoặc AlloyDB** có thể kinh tế hơn.
- Chỉ cần document storage cho mobile/web: cân nhắc **Firestore**.
- Key-value/time series throughput cực lớn, không cần joins hay multi-row relational transaction: cân nhắc **Bigtable**.
- Phần lớn workload là tổng hợp dữ liệu nhiều TB/PB: ưu tiên **BigQuery** cho phân tích.
- Chỉ cần HA một region: kiểm tra **Cloud SQL HA/AlloyDB HA** trước khi chọn Spanner multi-region.

**Không chọn Spanner chỉ vì tên “globally scalable”; phải có yêu cầu đo được.**

## 9. RTO, RPO, latency và vị trí người dùng

| Yếu tố | Câu hỏi cần hỏi |
| --- | --- |
| Vùng của ứng dụng | Cloud Run/GKE ở đâu? DB leader/replicas ở đâu? |
| Read freshness | Có chấp nhận stale reads ở dashboard không? |
| Write latency | Transaction phải phối hợp bao xa để commit? |
| Availability | Mất một zone hay mất cả region là tình huống cần bảo vệ? |
| Data residency | Có quy định lưu dữ liệu ở quốc gia/khu vực nào? |
| DR | Có yêu cầu backup, restore, PITR, failover và diễn tập RTO/RPO không? |
| Business invariants | Nếu API retry, có tạo order/payment trùng không? |

Spanner replication giảm rủi ro mất dữ liệu do sự cố hạ tầng, **không đảo ngược được lệnh DELETE sai hoặc lỗi logic đã commit**. Vẫn cần backup, PITR, safeguards, application-level idempotency và disaster-recovery testing.

**Một instance multi-region không tự làm mọi write nhanh hơn regional**: quorum/leader placement ảnh hưởng. Benchmark từ **các region ứng dụng thật**, không chỉ chạy `SELECT 1` ở môi trường local.

## 10. Editions và compute capacity

Spanner hiện có ba editions:

| Edition | Đặc trưng |
| --- | --- |
| **Standard** | Tính năng relational/key-value cốt lõi, **regional configuration** |
| **Enterprise** | Thêm multi-model/search, enhanced operations như **managed autoscaling**, regional + lựa chọn read-only replicas theo hỗ trợ |
| **Enterprise Plus** | Bổ sung **dual-region/multi-region**, khả năng HA cao hơn, geo-partitioning theo trạng thái tính năng |

Compute capacity cấp bằng **nodes** hoặc **processing units**, với **1 node = 1.000 PU**. Tăng compute giúp xử lý nhiều requests hơn, nhưng **không sửa hotspot từ thiết kế schema**. Với Enterprise/Enterprise Plus, có thể cấu hình **managed autoscaling** theo CPU/storage targets và min/max capacity phù hợp.

**Capacity là compute của instance, không phải số lượng VM bạn trực tiếp quản lý.** Instance chứa nhiều databases cùng chia sẻ capacity; sizing theo tổng workload và replication topology.

### 10.1. Tài nguyên và chi phí

Spanner có thể tính phí theo:

- **Compute capacity**: edition, instance configuration, nodes/PU, số/loại replicas và thời gian.
- **Database storage**: dữ liệu, indexes, bản sao theo pricing model.
- **Backup/PITR** và data retention.
- **Network egress / replication-related transfer** theo cấu hình.
- **Data Boost** nếu dùng compute đọc độc lập cho workloads tương thích.
- **Cloud Logging/Monitoring**, client service resources và các dịch vụ liên quan.

Chi phí phụ thuộc region, edition và khả năng sử dụng tài nguyên; **không đưa số “chi phí mỗi transaction” cứng** mà không căn cứ billing SKU. Spanner có **free trial instance 90 ngày** theo điều kiện và giới hạn riêng; nó không phải môi trường free-tier production vĩnh viễn. Billing budgets dạng cảnh báo **không tự khóa chi tiêu**.

## 11. Lab chỉ đọc: đánh giá khả năng triển khai

**Bước đầu không tạo gì**, chỉ xác minh project, region và cấu hình được hỗ trợ:

~~~bash
gcloud auth list
gcloud config get-value project

# Instance configurations được hỗ trợ trong project:
gcloud spanner instance-configs list --project=PROJECT_ID

# Những instances hiện có, không thay trạng thái:
gcloud spanner instances list --project=PROJECT_ID
~~~

Giả định bài lab dùng `regional-asia-southeast1` và một instance `spanner-choice-lab`. Trước khi chạy lệnh có tác động, cần xác nhận cấu hình này xuất hiện trong output, project có Billing/Spanner API và người thực hiện có quyền phù hợp.

### 11.1. IAM cho người học và ứng dụng

- Deployer/admin lab có quyền tạo instance/database/schema, cấp hạn chế theo môi trường.
- Ứng dụng Java chỉ cần **Spanner Database User** (`roles/spanner.databaseUser`) trên database cần truy cập, thêm quyền hẹp nếu tác vụ đặc biệt.
- Trên máy local dùng **Application Default Credentials (ADC)**; trên Cloud Run/GKE/Compute Engine dùng runtime service account/Workload Identity Federation for GKE.
- Không tạo service account JSON key và không cấp `roles/spanner.admin` cho runtime chỉ để hết lỗi permission.

## 12. Lab có tác động: tạo instance và GoogleSQL database

**Cảnh báo:** lệnh dưới tạo resources có thể tính phí liên tục. Chỉ chạy trong project **lab đã phê duyệt và có budget**, không thay tên trùng với tài nguyên của nhóm khác.

~~~bash
gcloud services enable spanner.googleapis.com \
  --project=PROJECT_ID

# Ví dụ instance Standard regional nhỏ; phải xác minh quota và giá.
gcloud spanner instances create spanner-choice-lab \
  --config=regional-asia-southeast1 \
  --description="Spanner relational lab" \
  --edition=STANDARD \
  --processing-units=100 \
  --project=PROJECT_ID

# Mặc định tạo database theo GoogleSQL dialect.
gcloud spanner databases create orders-db \
  --instance=spanner-choice-lab \
  --project=PROJECT_ID
~~~

`100 PU` là ví dụ compute nhỏ phù hợp lab theo cấu hình hỗ trợ, **không phải khuyến nghị production**. Khi có free trial instance đủ điều kiện, có thể chọn luồng trial riêng theo tài liệu; đừng áp mặc định các flags của instance provisioned vào trial.

### 12.1. Tạo bảng và index

~~~bash
gcloud spanner databases ddl update orders-db \
  --instance=spanner-choice-lab \
  --project=PROJECT_ID \
  --ddl='CREATE TABLE Orders (OrderId STRING(36) NOT NULL, CustomerId STRING(36) NOT NULL, TotalCents INT64 NOT NULL, Status STRING(20) NOT NULL) PRIMARY KEY (OrderId)'

gcloud spanner databases ddl update orders-db \
  --instance=spanner-choice-lab \
  --project=PROJECT_ID \
  --ddl='CREATE INDEX OrdersByCustomer ON Orders(CustomerId) STORING (Status, TotalCents)'
~~~

Các thao tác DDL là **long-running operations** và có thể mất thời gian; chờ operation hoàn tất trước khi insert/query. Trong project đa người dùng, không chạy sửa schema production mà không có migration plan.

### 12.2. Insert và query

~~~bash
gcloud spanner databases execute-sql orders-db \
  --instance=spanner-choice-lab \
  --project=PROJECT_ID \
  --sql="INSERT INTO Orders (OrderId, CustomerId, TotalCents, Status) VALUES ('aa9dc1b4-2ef1-4afb-931c-6c912833dd70', 'customer-01', 150000, 'NEW')"

gcloud spanner databases execute-sql orders-db \
  --instance=spanner-choice-lab \
  --project=PROJECT_ID \
  --sql="SELECT OrderId, CustomerId, TotalCents, Status FROM Orders WHERE CustomerId = 'customer-01'"
~~~

**Kỳ vọng:** query trả một row với `TotalCents=150000`. Đây là **bài tập đọc/ghi cơ bản**, chưa đo được throughput hoặc bảo đảm “scale vô hạn”. Nếu cần phân tích query plan, dùng **Spanner Studio/EXPLAIN** theo phiên bản SQL dialect.

### 12.3. Dọn tài nguyên

Sau khi xác minh **không có dữ liệu hoặc người dùng khác phụ thuộc**:

~~~bash
# XÓA THẬT: database và dữ liệu lab sẽ mất.
gcloud spanner databases delete orders-db \
  --instance=spanner-choice-lab \
  --project=PROJECT_ID

# XÓA THẬT: chỉ sau khi đã xóa/cẩn trọng với mọi databases còn lại.
gcloud spanner instances delete spanner-choice-lab \
  --project=PROJECT_ID
~~~

Xóa instance có thể xóa **toàn bộ databases** trong instance và không hoàn tác đơn giản. Nếu bật deletion protection, phải tuân thủ quy trình riêng. Kiểm tra Billing Reports sau cleanup; **không giả định tắt Spanner API sẽ dừng mọi chi phí**.

## 13. Java: ghi đơn bằng read-write transaction

Đoạn sau dùng **Spanner Java client** và **GoogleSQL database** ở mục 12. Thư viện Maven: `com.google.cloud:google-cloud-spanner`, quản lý version bằng **Google Cloud Libraries BOM** được cập nhật/kiểm duyệt; code cần Java 17+ hoặc target được phiên bản client hỗ trợ.

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.DatabaseId;
import com.google.cloud.spanner.Key;
import com.google.cloud.spanner.Mutation;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;
import com.google.cloud.spanner.Struct;
import java.util.List;

public class SpannerOrderExample {
    public static void main(String[] args) {
        String projectId = "PROJECT_ID";
        String instanceId = "spanner-choice-lab";
        String databaseId = "orders-db";
        String orderId = "aa9dc1b4-2ef1-4afb-931c-6c912833dd70";

        try (Spanner spanner = SpannerOptions.newBuilder()
                .setProjectId(projectId).build().getService()) {
            DatabaseClient db = spanner.getDatabaseClient(
                DatabaseId.of(projectId, instanceId, databaseId));

            String result = db.readWriteTransaction().run(tx -> {
                Struct existing =
                    tx.readRow("Orders", Key.of(orderId), List.of("OrderId"));
                if (existing != null) {
                    return "ALREADY_EXISTS";
                }

                tx.buffer(Mutation.newInsertBuilder("Orders")
                    .set("OrderId").to(orderId)
                    .set("CustomerId").to("customer-01")
                    .set("TotalCents").to(150000L)
                    .set("Status").to("NEW")
                    .build());
                return "CREATED";
            });

            System.out.println(result);
        }
    }
}
~~~

**Giải thích:**

- `DatabaseClient` làm việc với một database cụ thể; không tự tạo instance/database.
- `readWriteTransaction().run(...)` có thể **chạy callback lại** khi Spanner trả `ABORTED` do cạnh tranh; callback chỉ đọc và ghi qua `tx`.
- `tx.readRow` kiểm tra khóa tồn tại; mutation được buffer rồi commit khi callback hoàn tất theo client library.
- Hai requests đồng thời với cùng `orderId` có thể dẫn đến abort/retry hoặc một yêu cầu ghi bị từ chối vì unique key; app phải xử lý phản hồi và business idempotency.
- **Không gọi Pub/Sub/email/payment API bên trong callback**: callback có thể chạy nhiều lần. Khi cần publish event sau khi commit, dùng **outbox table cùng Spanner transaction** và một relay đáng tin cậy.

Ví dụ đã có row do lab `INSERT` tạo ở mục 12 nên kết quả sẽ là `ALREADY_EXISTS`. Nếu muốn quan sát `CREATED`, đổi sang một **UUID v4 mới** và chạy hai lần; lần đầu created, lần sau already exists. Không tạo IDs mới cho retry của **cùng một yêu cầu nghiệp vụ**.

## 14. Spanner trong Java services: kết nối và bảo mật

| Nguồn ứng dụng | Phương thức | Điều cần xác minh |
| --- | --- | --- |
| Cloud Run | Spanner Java client qua Google Cloud API, runtime service account | IAM Database User, deadlines, max instances và sessions |
| GKE | Workload Identity Federation for GKE, client library | Namespace/KSA identity mapping, networking |
| Compute Engine | VM service account + client library | IAM và kết nối đến Google APIs |
| Local developer | ADC `gcloud auth application-default login` | Quota project, quyền DB tối thiểu |
| PostgreSQL tools | PGAdapter nếu dialect/driver phù hợp | Hỗ trợ tính năng, cấu hình kết nối và khác biệt PostgreSQL |

**Spanner không phải một PostgreSQL instance nhận kết nối TCP tới cổng 5432 mặc định.** Java client Spanner làm việc qua API; muốn dùng một số PostgreSQL clients cần PGAdapter. Không mở VPC firewall cho port PostgreSQL rồi giả định đã thiết lập Spanner.

Cân nhắc **Private Google Access, VPC egress, Private Service Connect for Google APIs** nếu tổ chức hạn chế đường mạng; không dùng public IP của VM/database kiểu Cloud SQL làm mẫu Spanner.

## 15. Giám sát Spanner và điều tra bottleneck

Theo dõi **Cloud Monitoring** và các công cụ quan sát Spanner:

| Tín hiệu | Diễn giải |
| --- | --- |
| High-priority CPU utilization | Thiếu compute capacity hay workload đột biến? |
| Storage utilization | Dung lượng data/indexes tăng? |
| Read/write latency | Độ trễ DB và khoảng cách tới leader/region |
| Transaction abort count | Contention, transaction dài, hot keys |
| Session count, RPC errors, deadline exceeded | Client resource/pool, network/IAM |
| Query statistics/plan | Index thiếu, scan nhiều rows, join quá đắt |
| **Key Visualizer** | Hotspot theo key range, thứ tự keys/indexes |
| Locks/transaction statistics | Transaction giữ lock lâu hoặc bị cạnh tranh |
| Billing SKU | Compute, storage, backup, network, Data Boost |

Google Cloud có hướng dẫn theo dõi **high-priority CPU**: giá trị khuyến nghị tối đa **65% đối với regional** và **45% mỗi region với dual-/multi-region** để còn dư tài nguyên khi một vùng khả dụng bị ảnh hưởng. Đây là **ngưỡng hướng dẫn vận hành**, không phải giới hạn cứng mọi workload.

### 15.1. Khi CPU cao nhưng throughput thấp

Đừng chỉ tăng PU/nodes. Kiểm tra:

1. **Hotspot key range** do primary key/index theo timestamp tuần tự.
2. Transaction quá dài hoặc tranh chấp một row nóng.
3. Query scan nhiều dữ liệu, thiếu index hoặc chọn join không hiệu quả.
4. App đặt ở region xa, call RPC quá nhiều lần trên mỗi request.
5. Read-only report nặng tranh CPU với OLTP; cân nhắc stale reads/Data Boost/export BigQuery.

**Thêm capacity không làm một key range nóng tự nhiên phân tán**, phải sửa schema/query pattern khi nguyên nhân là hotspot.

## 16. Migration và trade-offs về vận hành

Chuyển từ Cloud SQL/AlloyDB sang Spanner không chỉ là thay JDBC URL:

- Đánh giá **SQL dialect**, kiểu dữ liệu, extensions/procedures/triggers không tương thích.
- Thiết kế lại **primary keys, indexes, transaction boundaries** cho splits.
- Chuyển dữ liệu qua công cụ migration/Dataflow theo tài liệu, giữ **write consistency** trong dual-write/cutover.
- Định nghĩa mã lỗi `ABORTED`, retry policy, idempotency, session/pool management.
- Kiểm thử latency khi truy vấn xuyên regions và backup/PITR/restore.
- Chạy load test với **traffic thật và key distribution thật**, không chỉ tạo một số rows nhỏ.

**Chọn PostgreSQL dialect không xóa những bước này**. Ngược lại, nếu ứng dụng phụ thuộc sâu vào PostgreSQL extensions và có SLO đáp ứng được trong một region, AlloyDB hoặc Cloud SQL có thể là lựa chọn đơn giản và kinh tế hơn.

## 17. Tình huống quyết định: Orders toàn cầu

**Bối cảnh:** nhóm Commerce hiện chạy Java trên Cloud Run tại Singapore và Tokyo, database Cloud SQL PostgreSQL ở Singapore. Đơn hàng tăng nhanh, giờ cao điểm xử lý số lượng writes lớn, có yêu cầu đọc/ghi nhất quán qua nhiều vùng địa lý.

| Câu hỏi | Nếu trả lời “có” | Hướng xem xét |
| --- | --- | --- |
| Có quan hệ chặt giữa orders, payments, inventory? | Cần ACID/foreign keys/joins | Spanner / relational DB |
| Một primary database đã thành bottleneck writes? | Scale-up/replicas không đủ | Spanner, có schema phân tán |
| Cần phục vụ ghi xuyên địa lý với strong consistency? | Độ trễ/kịch bản failover phức tạp | Enterprise Plus multi-region, chọn leader phù hợp |
| Dùng nhiều PostgreSQL-specific extensions? | Migration tốn kém | Đánh giá AlloyDB/Cloud SQL trước |
| Workload chủ yếu báo cáo BI? | Query scans lớn, batch | BigQuery hơn là OLTP DB |
| Có ngân sách cho compute nhiều replicas? | Replication/capacity costs lớn | So sánh TCO theo workload |

**Quy trình lựa chọn:**

1. Đo Cloud SQL hiện tại: QPS, write latency, CPU, storage, replica lag, downtime và chi phí.
2. Xác định **RTO/RPO**, yêu cầu data residency và tỷ lệ read/write theo region.
3. Benchmark Cloud SQL/AlloyDB cải tiến **so với** một Spanner PoC dùng đúng key distribution.
4. Thử transaction đặt hàng, đồng thời cập nhật tồn kho, idempotency và lỗi network.
5. Đo p95/p99, abort rate, capacity, cross-region latency và chi phí.
6. Chỉ quyết định migrate khi lợi ích HA/scale lớn hơn phức tạp/cost; có cutover và rollback plan.

**Kết luận tình huống:** Spanner rất đáng cân nhắc nếu bottleneck ghi và yêu cầu strong consistency đa vùng là thực. Nếu chỉ cần một region với throughput chưa bão hòa, **Cloud SQL HA/AlloyDB** thường là điểm khởi đầu hợp lý hơn.

## 18. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Chọn database.** Ứng dụng Java nội bộ có 200 requests/giây, yêu cầu PostgreSQL extensions, một region. Chọn gì?

*Đáp án gợi ý:* Cloud SQL PostgreSQL/AlloyDB trước; Spanner không mặc định tối ưu vì migration/compatibility/cost.

**Bài 2 — Chọn topology.** Hệ thống thanh toán nhiều regions có yêu cầu consistency và khả dụng liên vùng. Chọn cấu hình gì?

*Đáp án:* Đánh giá Spanner Enterprise Plus dual-/multi-region, đo write latency, residency, chi phí, SLA và DR.

**Bài 3 — Tìm hotspot.** Bảng có `PRIMARY KEY (CreatedAt, EventId)`; write rate tăng nhưng CPU tổng còn dư. Sửa thế nào?

*Đáp án:* Dùng UUID v4/hash/shard prefix hoặc key phân tán phù hợp; kiểm tra cả secondary indexes và Key Visualizer.

**Bài 4 — Thực hành lab.** Tạo instance/database GoogleSQL, insert một row, chạy `SELECT` theo `CustomerId` và xem index.

*Đạt:* Dữ liệu đúng, query có kết quả; ghi lại cấu hình/PU/chi phí, dọn instance sau lab.

**Câu 5.** Spanner có thể dùng foreign keys/joins và ACID trên nhiều splits?

*Đáp án:* Có, theo tính năng/dialect được hỗ trợ; đây là thế mạnh relational phân tán.

**Câu 6.** PostgreSQL dialect của Spanner có tương đương Cloud SQL PostgreSQL 100%?

*Đáp án:* Không. SQL subset và hệ sinh thái/extension/driver cần kiểm tra.

**Câu 7.** Strong read và stale read khác nhau thế nào?

*Đáp án:* Strong read yêu cầu dữ liệu nhất quán mới nhất theo guarantee; stale read chấp nhận snapshot cũ theo yêu cầu.

**Câu 8.** Transaction Java callback bị retry có an toàn khi gọi thanh toán API ngay trong callback không?

*Đáp án:* Không. Callback có thể chạy nhiều lần; dùng outbox/idempotency/reconcile.

**Câu 9.** Regional Spanner có vượt qua sự cố toàn region mà không cần topology khác?

*Đáp án:* Không bảo đảm; regional phân bố nhiều zones trong một region, muốn DR vùng rộng cần kế hoạch khác.

**Câu 10.** Tại sao tăng nodes có thể không giúp nếu một timestamp-index là hot range?

*Đáp án:* Hotspot vẫn dồn vào một phần key space/index; cần sửa key/index layout.

**Câu 11.** Spanner multi-region có luôn viết nhanh hơn regional?

*Đáp án:* Không. Consensus/quorum liên vùng có thể tăng write latency.

**Câu 12.** 1 node tương đương bao nhiêu processing units?

*Đáp án:* 1.000 PU, nhưng sizing còn phụ thuộc edition/topology và workload.

**Câu 13.** Spanner thay thế backup/PITR vì đã synchronous replication?

*Đáp án:* Không. Lỗi logic và xóa nhầm được replicate; vẫn cần backup/restore.

**Câu 14.** Khi nào ưu tiên Bigtable thay Spanner?

*Đáp án:* Workload key-value/wide-column throughput cao, không cần relational joins/multi-row ACID tổng quát.

## 19. Checklist production

- [ ] Có yêu cầu đo được về **scale-out writes, strong consistency, HA/DR**.
- [ ] Đã so sánh với Cloud SQL/AlloyDB/Firestore/Bigtable đúng use case.
- [ ] Chọn **region/dual-region/multi-region** và edition đúng feature/SLA.
- [ ] Bảo đảm data residency, leader placement và ứng dụng gần dữ liệu.
- [ ] Primary keys/indexes tránh hotspot; benchmark bằng phân bố khóa thật.
- [ ] SQL dialect/compatibility/driver/migration được kiểm tra.
- [ ] Transaction ngắn, retry `ABORTED`, không side effect ngoài DB trong callback.
- [ ] Business idempotency và outbox có thiết kế rõ.
- [ ] IAM databaseUser tối thiểu, ADC/WIF và network controls phù hợp.
- [ ] Compute PU/nodes, CPU utilization, storage/index growth và autoscaler được sizing.
- [ ] Cloud Monitoring, Query stats, Key Visualizer và alert SLO hoạt động.
- [ ] Backup/PITR, restore drill, deletion protection và runbook DR đã duyệt.
- [ ] Có billing budget alerts; dự toán compute, replicas, storage, backup, egress.
- [ ] Có kế hoạch cutover, rollback và audit khi thay database production.

## 20. Kết luận

**Spanner là một cơ sở dữ liệu quan hệ phân tán thực thụ**, kết hợp SQL, giao dịch ACID, strong consistency và khả năng tăng quy mô ngang nhờ chia dữ liệu, sao chép và consensus. Sức mạnh đó chỉ phát huy khi **khóa phân tán tốt, transactions phù hợp, region/edition được chọn đúng và chi phí được đo**.

Chọn **Spanner** khi yêu cầu quan hệ/nhất quán/scale/khả dụng thật sự cần kiến trúc phân tán. Chọn **Cloud SQL hoặc AlloyDB** khi ứng dụng PostgreSQL/MySQL cần sự tương thích và vận hành đơn giản hơn. Mọi quyết định phải dựa vào **PoC với tải thực, SLO, data residency, migration cost và tổng chi phí sở hữu**.

## Tài liệu tham khảo chính thức

- [Spanner documentation overview](https://cloud.google.com/spanner/docs)
- [Spanner instances](https://cloud.google.com/spanner/docs/instances)
- [Regional, dual-region, multi-region configurations](https://cloud.google.com/spanner/docs/instance-configurations)
- [Spanner editions](https://cloud.google.com/spanner/docs/editions-overview)
- [Spanner transactions](https://cloud.google.com/spanner/docs/transactions)
- [Schema and data model](https://cloud.google.com/spanner/docs/schema-and-data-model)
- [Schema design best practices](https://cloud.google.com/spanner/docs/schema-design)
- [Choose GoogleSQL or PostgreSQL dialect](https://cloud.google.com/spanner/docs/choose-googlesql-or-postgres)
- [Create and query database by gcloud](https://cloud.google.com/spanner/docs/getting-started/gcloud)
- [Getting started with Spanner in Java](https://cloud.google.com/spanner/docs/getting-started/java)
- [Spanner Java read-write transaction sample](https://cloud.google.com/spanner/docs/samples/spanner-read-write-transaction)
- [Spanner CPU utilization](https://cloud.google.com/spanner/docs/cpu-utilization)
- [Spanner pricing](https://cloud.google.com/spanner/pricing)

