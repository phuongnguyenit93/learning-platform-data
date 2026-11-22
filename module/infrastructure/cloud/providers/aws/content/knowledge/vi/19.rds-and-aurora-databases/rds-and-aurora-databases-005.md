# Read replica và chiến lược tách đọc ghi trên Amazon RDS và Aurora

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **writer/primary**, **read replica/reader**, **replication lag**, **writer endpoint**, **reader endpoint** và lý do hệ thống nhiều lượt đọc cần tách đọc–ghi.
- Phân biệt **RDS DB instance read replica**, **RDS Multi-AZ DB instance standby**, **RDS Multi-AZ DB cluster readers** và **Amazon Aurora Replicas**, tránh nhầm high availability với read scaling.
- Xác định luồng nào cần **read-after-write/strong consistency**, luồng nào chấp nhận **eventual consistency**, từ đó chọn endpoint và fallback phù hợp.
- Hiểu replication bất đồng bộ, bán đồng bộ, độ trễ apply, ảnh hưởng của SQL/CPU/I/O và giới hạn của việc thêm replicas.
- Thiết kế định tuyến rõ ràng cho **Java/Spring Boot/JDBC**, quản lý transaction và connection pools, không nhầm annotation `@Transactional(readOnly=true)` với tự động chuyển sang reader.
- Tạo/kiểm tra RDS read replica và xem Aurora cluster endpoints bằng AWS CLI, chẩn đoán lag, query timeout và failover.
- Đánh giá **Aurora failover, promotion, Multi-AZ, cross-Region replica, Global Database, RDS Proxy** và backup/restore theo RTO/RPO.
- Sử dụng **VPC, IAM, TLS, AWS KMS, Secrets Manager, CloudWatch và AWS Budgets** để bảo vệ dữ liệu, theo dõi hiệu năng và kiểm soát chi phí.

**Ngữ cảnh:** Bài thuộc chương **Cơ sở dữ liệu RDS và Aurora**, module **CLOUD_PROVIDERS_AWS**. Sau khi học hạ tầng Region/AZ, IAM, VPC, compute, lưu trữ, database, tích hợp và serverless, người học cần biết chọn cấu trúc database vừa giải quyết bottleneck đọc, vừa **an toàn, quan sát được, có khả năng phục hồi và phù hợp ngân sách**. Read replica là một công cụ quan trọng, nhưng không tự giải quyết tính nhất quán dữ liệu hoặc tính sẵn sàng toàn hệ thống.

> **Phạm vi:** Trọng tâm là **RDS for PostgreSQL/MySQL** và **Aurora PostgreSQL/MySQL**. Hỗ trợ replica, promotion, cross-Region, metrics, engine version và instance class khác nhau theo sản phẩm/Region. Các tên, URL, account ID, ARN và lệnh trong bài đều dành cho **lab**; không thay đổi cơ sở dữ liệu production để thử ví dụ.

## 1. Vì sao phải tách đọc và ghi?

Hệ thống bán hàng có API tạo đơn, quản lý tồn kho và xem danh sách sản phẩm. Ở giờ cao điểm, giả sử trong mỗi giây có:

- 500 thao tác ghi đơn hàng/thanh toán;
- 5.000 truy vấn đọc catalog, sản phẩm và lịch sử;
- một số truy vấn dashboard tổng hợp hàng triệu dòng.

Nếu tất cả dùng cùng một RDS primary instance:

~~~mermaid
flowchart TB
    Web[Web / Mobile] --> API[Java API ECS / Lambda]
    Jobs[BI / Reporting] --> DB[(RDS Primary)]
    API --> DB
    DB --> CPU[CPU, connections, read I/O, locks]
~~~

Các SELECT tốn CPU, buffer cache, I/O và connection slots; writer phải cạnh tranh tài nguyên với các truy vấn báo cáo. Nâng cấp instance chính chỉ giải quyết một phần, có giới hạn và tăng chi phí.

Mô hình tách đọc–ghi đưa truy vấn **chấp nhận dữ liệu hơi cũ** sang các reader instances:

~~~mermaid
flowchart TB
    Client[Client] --> App[Java Application]
    App --> Rule{Operation / consistency}
    Rule -->|INSERT UPDATE DELETE| W[(Writer / Primary)]
    Rule -->|Đọc cần dữ liệu mới| W
    Rule -->|Đọc chấp nhận stale| R1[(Reader A)]
    Rule -->|Đọc chấp nhận stale| R2[(Reader B)]
    W -. Replication .-> R1
    W -. Replication .-> R2
    R2 --> Report[Reporting workload]
~~~

**Không phải mọi SELECT đều đi reader.** Kiểm tra số dư, tồn kho, phân quyền, giao dịch đang diễn ra và dữ liệu vừa ghi thường cần đọc writer hoặc cơ chế consistency mạnh đã xác minh.

## 2. Thuật ngữ và ba mục tiêu kiến trúc khác nhau

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Primary/Writer** | DB instance hoặc cluster member thực hiện những thay đổi dữ liệu chính |
| **Read replica/Reader** | Bản sao xử lý đọc, cập nhật từ writer theo cơ chế replication |
| **Replication lag** | Độ trễ để thay đổi đã commit trên writer hiển thị ở reader |
| **Read endpoint** | Địa chỉ dành cho kết nối đọc; với cluster có thể chọn một reader cho kết nối mới |
| **Writer/cluster endpoint** | Địa chỉ kết nối tới writer hiện tại, thuận tiện khi đổi writer |
| **Instance endpoint** | Endpoint của một DB instance cụ thể, không phải tên vai trò vĩnh viễn |
| **Promotion** | Chuyển một replica thành writer/DB độc lập theo cơ chế sản phẩm |
| **Failover** | Chuyển dịch vụ sang một DB instance khác để khôi phục khả dụng |
| **RTO/RPO** | Mục tiêu thời gian phục hồi / lượng dữ liệu tối đa chấp nhận mất theo thời gian |

Ba mục tiêu cần thiết kế riêng:

1. **Read scaling:** Phân tán SELECT tới nhiều instances để tăng năng lực đọc.
2. **High availability:** Tự động khôi phục dịch vụ khi writer/instance/AZ lỗi.
3. **Data recovery/disaster recovery:** Khôi phục dữ liệu đã mất/xóa nhầm/corrupt, hoặc chuyển Region khi có thảm họa.

**Read replica không đồng nghĩa high-availability standby, và cả hai đều không thay thế point-in-time recovery hoặc backup.**

## 3. RDS DB instance read replica truyền thống

Với Amazon RDS DB instance read replica, RDS tạo một **DB instance bổ sung**, thường từ snapshot nguồn ban đầu rồi duy trì **replication bất đồng bộ** bằng cơ chế của database engine.

~~~mermaid
sequenceDiagram
    participant App as Java Application
    participant W as RDS Primary
    participant R as RDS Read Replica
    App->>W: INSERT order + COMMIT
    W-->>App: COMMIT OK
    W-->>R: Replicate asynchronously
    App->>R: SELECT order ngay sau COMMIT
    R-->>App: Có thể chưa thấy order
    Note over R: Apply changes hoàn tất
    App->>R: SELECT order lần sau
    R-->>App: Nhìn thấy order
~~~

Đặc điểm:

- **Source** là RDS DB instance phù hợp; tạo replica theo engine/version/backup prerequisites.
- Replica có **compute, storage/I/O và endpoint riêng**; có thể chọn DB instance class khác tùy engine/quota.
- Thay đổi được copy **bất đồng bộ** nên có replica lag.
- Read replica thường phục vụ **read-only** SQL; một số engine hỗ trợ chế độ replica khác cần tra tài liệu chính thức.
- Ứng dụng phải **tự route các read queries** tới endpoint replica; RDS không tự động tách mọi SELECT từ primary.
- Có thể tạo nhiều read replicas theo quota và một số trường hợp cross-Region.
- RDS không mặc định **tự tăng/giảm số read replicas truyền thống** theo QPS.
- Replica có thể được **promote** thành standalone DB instance theo khả năng hỗ trợ, nhưng không tự thay primary khi source lỗi như Multi-AZ standby.

### Vì sao lag xuất hiện?

- Writer phát WAL/binlog nhanh hơn replica nhận/replay.
- Replica CPU/I/O yếu hoặc query analytics chiếm tài nguyên.
- Network bị gián đoạn, đặc biệt cross-Region.
- Transaction dài, schema change, large transaction, thiếu disk/IO capacity.
- Engine replication slots/log retention, permissions hoặc replication status lỗi.

**Replication là pipeline bất đồng bộ:** Writer báo commit thành công **không chứng minh** reader đã apply bản ghi đó.

## 4. RDS Multi-AZ DB instance standby: HA, không phải read scaling

Một hiểu lầm phổ biến: “Bật Multi-AZ là có thêm một database để chạy SELECT”.

**Sai đối với RDS Multi-AZ DB instance deployment có một standby.**

~~~text
Primary (AZ A)  --synchronous replication-->  Standby (AZ B)
  Read + write                            Không phục vụ SQL đọc
  Nhận kết nối ứng dụng                    Sẵn sàng khi cần failover
~~~

Standby do RDS quản lý để giảm downtime khi primary/AZ lỗi. **Không có reader endpoint để tận dụng standby làm reporting DB**.

| Tính chất | RDS Multi-AZ DB instance standby | RDS read replica truyền thống |
| --- | --- | --- |
| Mục tiêu chính | **High availability** | **Read scaling** và DR có kế hoạch |
| Phục vụ SELECT | **Không** | **Có** |
| Replication | Đồng bộ theo cơ chế engine | **Bất đồng bộ** |
| Automatic takeover khi primary lỗi | **Có** | **Không mặc định** |
| Ứng dụng kết nối | Primary endpoint | Replica endpoint riêng |
| Có nguy cơ stale reads | Không dùng để đọc | **Có** |
| Chi phí | Standby HA | Replica compute/storage riêng |

Có thể kết hợp **RDS Multi-AZ primary instance + RDS read replica bổ sung** nếu engine hỗ trợ, vừa có standby để HA vừa tách các reads phù hợp.

## 5. RDS Multi-AZ DB cluster: có hai readers thật

AWS còn cung cấp **RDS Multi-AZ DB cluster**, khác với mô hình Multi-AZ DB instance standby ở mục 4.

Theo tài liệu AWS hiện hành, mô hình Multi-AZ DB cluster được hỗ trợ cho **RDS MySQL/PostgreSQL** trong những engine versions/Regions phù hợp; cluster có:

- **1 writer** và **2 readable reader instances** ở ba Availability Zones khác nhau.
- **Writer endpoint** và **reader endpoint**.
- **Semisynchronous replication**: transaction có thể commit khi ít nhất một reader xác nhận theo protocol; **không đòi mọi reader đã apply đầy đủ tất cả records**.
- Automatic failover sang reader phù hợp khi writer lỗi.
- Reader vừa phục vụ SELECT vừa là failover target.

~~~mermaid
flowchart TB
    App[Java API] --> WE[Writer endpoint]
    App --> RE[Reader endpoint]
    subgraph C["RDS Multi-AZ DB cluster"]
      WE --> W[(Writer AZ A)]
      RE --> R1[(Reader AZ B)]
      RE --> R2[(Reader AZ C)]
      W -. Semisynchronous replication .-> R1
      W -. Semisynchronous replication .-> R2
    end
~~~

**Quan trọng:** Semisynchronous acknowledgment không bằng “mọi reader đã apply commit mới nhất”. Đọc từ reader C ngay sau commit ở writer A **vẫn có thể thấy dữ liệu cũ**, tùy tiến độ apply.

**Phân biệt thêm:** Một **DB instance read replica** được tạo bổ sung từ Multi-AZ DB cluster (khi hỗ trợ) **khác** các reader members nằm sẵn trong cluster: read replica bổ sung nhận thay đổi bất đồng bộ và không phải automatic failover target của cluster theo cơ chế member.

## 6. Amazon Aurora Replicas: cùng storage volume, vẫn có replication lag

**Amazon Aurora** là kiến trúc cluster với:

- Một **primary/writer DB instance** chịu trách nhiệm ghi.
- Tối đa **15 Aurora Replicas** (readers) trong cấu hình được hỗ trợ.
- Các instances dùng chung **logical Aurora cluster volume** bảo vệ qua nhiều Availability Zones.
- **Cluster writer endpoint**, **reader endpoint**, **instance endpoints** và **custom endpoints**.
- Aurora có thể **promote Aurora Replica** thành writer khi primary lỗi.

~~~mermaid
flowchart TB
    App[Java API / Lambda] --> WE[Aurora writer endpoint]
    App --> RE[Aurora reader endpoint]
    WE --> W[(Writer AZ A)]
    RE --> R1[(Reader AZ B)]
    RE --> R2[(Reader AZ C)]
    W --> Volume[(Shared Aurora cluster volume across AZs)]
    R1 --> Volume
    R2 --> Volume
    W -. Reader state / log apply .-> R1
    W -. Reader state / log apply .-> R2
~~~

**Aurora Replicas không có bản sao storage độc lập đầy đủ cho mỗi reader** như RDS read replica truyền thống. Tuy dùng chung volume, mỗi reader có compute/cache riêng và vẫn phải phản ánh thay đổi từ writer vào trạng thái query; do đó **AuroraReplicaLag không bằng 0 tuyệt đối trong mọi thời điểm**.

Aurora thường cho lag thấp, nhưng tải ghi lớn, reader quá tải, engine/version hoặc sự cố có thể làm lag tăng. Không lấy một giá trị quảng bá “vài mili giây” làm cam kết consistency cho ứng dụng thanh toán.

### Aurora Replica và failover priority

Khi writer lỗi, Aurora có thể promote một reader theo **promotion tier** và trạng thái thực tế. Tier từ 0 đến 15, **số nhỏ thường được ưu tiên hơn**. Có reader ở AZ khác làm tăng khả năng khôi phục khi một AZ ngừng hoạt động; vẫn cần app reconnect, backoff và idempotency cho writes.

## 7. Chọn đúng mô hình trước khi viết code route

| Mục tiêu | Phương án đánh giá | Điểm quyết định |
| --- | --- | --- |
| RDS primary quá tải SELECT | **RDS DB instance read replicas** | App tự route reader endpoint riêng, có lag |
| Muốn standby HA, không cần scale read | **RDS Multi-AZ DB instance** | Standby **không đọc** |
| Muốn HA và hai readable members với MySQL/Postgres | **RDS Multi-AZ DB cluster** | 1 writer + 2 readers, semisync commit |
| Muốn nhiều readers với shared cluster volume | **Aurora** | Tối đa 15 readers, cluster endpoints/failover |
| Muốn data gần người dùng khác Region | Cross-Region read replica / Aurora Global Database | Replication lag, DR routing và phí truyền dữ liệu |
| Report analytics quét dữ liệu rất lớn | Reporting replica hoặc **Redshift/S3/Athena** | Không để BI làm nghẽn OLTP |
| Muốn tăng mạnh **write** TPS | Tối ưu writer/partition/sharding/architecture | Read replicas không tự tăng writer throughput |

**Trước khi tạo replica:** Xem slow query log, index, query plan, N+1, pagination, caching, transaction length và connection pool. Một câu SQL thiếu index có thể làm quá tải cả 5 readers, không chỉ primary.

## 8. Endpoint: địa chỉ kết nối quyết định dữ liệu đi đâu

### 8.1. RDS DB instance truyền thống

Mỗi primary/read replica có **endpoint DNS riêng**:

~~~text
Writer:   orders-primary.abc123.ap-southeast-1.rds.amazonaws.com:5432
Reader A: orders-ro-a.def456.ap-southeast-1.rds.amazonaws.com:5432
Reader B: orders-ro-b.ghi789.ap-southeast-1.rds.amazonaws.com:5432
~~~

Với RDS ordinary read replicas, **không tự có một built-in “reader endpoint” tổng hợp như Aurora**. Ứng dụng/router có thể phân phối queries theo health/lag/weights hoặc chọn một replica riêng cho reporting.

### 8.2. Aurora và RDS Multi-AZ DB cluster

~~~text
Writer endpoint: orders.cluster-abc.ap-southeast-1.rds.amazonaws.com
Reader endpoint: orders.cluster-ro-abc.ap-southeast-1.rds.amazonaws.com
Instance endpoint: orders-reader-a.abc.ap-southeast-1.rds.amazonaws.com
~~~

- **Writer endpoint** trỏ writer hiện tại, thích hợp DML, transaction và critical reads.
- **Reader endpoint** thường phân phối **kết nối mới** tới readers, **không cân bằng từng SQL statement** của connection đang mở.
- **Instance endpoint** pin vào instance cụ thể, hữu ích khi debug; hardcode lâu dài có thể làm ứng dụng không đi theo role change sau failover.
- **Aurora custom endpoints** có thể group readers cho reporting/OLTP theo tính năng hỗ trợ.

### 8.3. Một ngoại lệ của Aurora reader endpoint

Nếu Aurora cluster **không có healthy Aurora Replica**, reader endpoint **có thể kết nối vào primary**. Trong tình huống đó, session có thể có write capability nếu DB user được cấp quyền. Vì vậy:

- **Không coi suffix `-ro` trên hostname là hàng rào bảo vệ write**.
- Dùng DB user **chỉ có SELECT** cho luồng read nếu phù hợp.
- Đưa DML vào writer datasource và có integration tests.
- Theo dõi số reader healthy và failover state.

### 8.4. DNS và connection reuse

Writer/reader endpoint là tên DNS. Khi failover, backend đích có thể thay đổi; **TCP connection cũ không tự đổi sang writer mới**. HikariCP/JDBC cần hủy connection lỗi, mở lại, nhận cập nhật DNS và retry có backoff.

Với reader endpoint, nếu pool tạo 30 connections khi start, những connections đó có thể phân bố không đều giữa replicas. **Không suy reader endpoint tự chia đều mọi query theo round-robin**; đo CPU, connections và query latency từng instance.

## 9. Replication lag: ví dụ ngay sau POST

~~~text
10:00:00.000  POST /orders → writer COMMIT đơn ORD-1001
10:00:00.050  GET /orders/ORD-1001 → read replica
10:00:00.050  Replica chưa apply → 404 hoặc status cũ
10:00:00.300  Replica bắt kịp
10:00:00.350  GET lần nữa → nhìn thấy ORD-1001
~~~

Đây là tình huống **read-after-write violation** trong kiến trúc eventual read, không nhất thiết là dữ liệu bị mất.

### Ba mức consistency cần phân loại

| Yêu cầu | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Cần thấy commit vừa thực hiện | Thanh toán, số dư, đơn vừa tạo | **Đọc writer** hoặc cơ chế consistency được chứng minh |
| Chịu stale tối đa vài giây | Danh sách catalog, dashboard realtime | Reader với lag threshold, fallback hoặc trạng thái chờ |
| Chịu stale lâu | Báo cáo lịch sử/BI | Reporting replica/warehouse, có lịch làm mới |

**HTTP GET không đồng nghĩa eventual read.** Một GET kiểm tra quyền, tồn kho hoặc thanh toán có thể cần đọc trạng thái mới nhất. Một SELECT trong writer transaction cũng phải dùng cùng database/connection phù hợp để nhìn thấy dữ liệu và locks cần thiết.

### Đo lag đúng

- RDS DB instance read replica: CloudWatch metric **`ReplicaLag`**, thường tính bằng giây, định nghĩa thay đổi theo engine.
- RDS Multi-AZ DB cluster: **`ReplicaLag`** thể hiện độ chậm áp dụng thay đổi trên reader member theo định nghĩa sản phẩm.
- Aurora: theo dõi **`AuroraReplicaLag`** từng reader và các metric cluster tương ứng như **`AuroraReplicaLagMaximum`** theo hỗ trợ.
- RDS `ReplicaLag=-1` có thể nghĩa **không xác định được lag**, không phải dữ liệu tốt hơn 0.
- Khi writer idle, SQL `now() - pg_last_xact_replay_timestamp()` có thể tăng hoặc trả NULL ngay cả khi dữ liệu đã bắt kịp. Không dùng công thức đó làm nguồn SLO duy nhất.

**Yêu cầu nghiệp vụ quan trọng hơn metric đơn lẻ:** “99,9% GET ngay sau thanh toán phải nhìn thấy trạng thái đã xác nhận” không được bảo đảm chỉ bởi một datapoint CloudWatch lag bằng 0.

## 10. Sáu chiến lược read-after-write và bounded staleness

### A. Đọc writer cho những request nhạy cảm

Sau một command ghi, route truy vấn cần thấy ngay kết quả đến writer:

~~~text
POST /orders → writer
GET /orders/{id} sau tạo → writer
GET /catalog → reader
GET /reports/daily → reader
~~~

Ưu điểm: rõ ràng và dễ kiểm chứng. Nhược điểm: writer vẫn phải chịu một phần đọc; đó là sự đánh đổi cần thiết cho correctness.

### B. Session affinity hoặc sticky writer reads

Trong một khoảng ngắn sau khi write, cùng user/session được route về writer. Hữu ích cho UI nhưng **không phải bảo đảm tuyệt đối**: replica lag có thể lâu hơn sticky window. Không dựa sticky TTL duy nhất cho số dư hoặc inventory.

### C. Token/position từ giao dịch

Dùng version/sequence/LSN/GTID hoặc commit position theo engine để **chờ replica đã replay tới mốc đó**. Chỉ trả kết quả từ reader khi xác nhận đạt mốc; có timeout/fallback writer.

Cách này phụ thuộc PostgreSQL/MySQL/Aurora version và API engine; **không giả định WAL LSN và GTID là một khái niệm có thể trao đổi trực tiếp**.

### D. Đọc có mức stale tối đa

Chỉ gửi query đến reader nếu health/lag thỏa ngưỡng do nghiệp vụ quy định, ví dụ stale ≤2 giây. Khi reader chậm, critical queries đi writer; noncritical queries có thể trả cache hoặc 503.

Lưu ý CloudWatch metrics được lấy mẫu, **không chứng minh từng transaction đã replay**, nên bounded staleness theo metric chỉ là heuristic trừ khi có xác nhận mức commit.

### E. Cache có TTL/invalidation rõ ràng

Sử dụng ElastiCache, CloudFront hoặc application cache cho catalog/reference data; theo dõi stale cache và bảo đảm invalidation. Cache cũng có consistency trade-off, không phải “replica không lag”.

### F. Workflow bất đồng bộ chủ động

Thay vì cam kết kết quả ghi xuất hiện ngay ở mọi read model, API trả:

~~~json
{
  "orderId": "ORD-1001",
  "status": "PROCESSING",
  "statusUrl": "/orders/ORD-1001"
}
~~~

Frontend hiển thị đang xử lý, query trạng thái qua writer/command store khi cần. Reporting/read models cập nhật qua replication hoặc events sau. Thiết kế này phù hợp **CQRS nhẹ**, nhưng vẫn cần idempotency và contract rõ ràng.

## 11. Bảng policy định tuyến đọc/ghi cho ứng dụng bán hàng

| Operation | Route | Lý do |
| --- | --- | --- |
| `POST /orders`, `PUT /orders/{id}` | Writer | DML và transaction |
| `POST /payments/confirm` | Writer | Quyết định nghiệp vụ nhạy consistency |
| `GET /orders/{id}` ngay sau POST | Writer | Read-your-writes |
| `GET /products?page=...` | Reader | Chịu eventual consistency |
| Trang lịch sử đã hoàn thành | Reader nếu SLO cho phép | Giảm tải đọc |
| Dashboard doanh thu giờ | Reader/reporting instance | Aggregate nặng |
| Kiểm tra số dư/tồn kho trước UPDATE | Writer transaction | Cần lock/version |
| Migration DDL/schema | Writer | Chỉ đổi schema qua migration có kiểm soát |
| Reconciliation/report cuối ngày | Reader + writer verification | Reporting không thay business truth |

**Không route bằng cách parse SQL đầu chuỗi là SELECT hay UPDATE**. Stored procedure, locks, session states và transactions phức tạp hơn phép phân loại cú pháp. Tốt hơn là **route theo use case/service method/transaction boundary**.

## 12. Java/Spring Boot: hai HikariCP pools rõ ràng

Để tránh router tự đoán SQL, ta tạo hai DataSources:

- `writerDataSource` cho writer/cluster endpoint.
- `readerDataSource` cho replica/reader endpoint.

Code minh họa với Java 21, Spring JDBC, HikariCP và PostgreSQL:

~~~java
package com.example.orders.config;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class DbConfiguration {

    @Bean("writerDataSource")
    public DataSource writerDataSource() {
        return pool("ORDERS_WRITER_JDBC_URL",
                    "ORDERS_WRITER_USER",
                    "ORDERS_WRITER_PASSWORD", "orders-writer-pool");
    }

    @Bean("readerDataSource")
    public DataSource readerDataSource() {
        return pool("ORDERS_READER_JDBC_URL",
                    "ORDERS_READER_USER",
                    "ORDERS_READER_PASSWORD", "orders-reader-pool");
    }

    @Bean("writerJdbc")
    public JdbcTemplate writerJdbc(
        @Qualifier("writerDataSource") DataSource source) {
        return new JdbcTemplate(source);
    }

    @Bean("readerJdbc")
    public JdbcTemplate readerJdbc(
        @Qualifier("readerDataSource") DataSource source) {
        return new JdbcTemplate(source);
    }

    @Bean("writerTxManager")
    public PlatformTransactionManager writerTxManager(
        @Qualifier("writerDataSource") DataSource source) {
        return new DataSourceTransactionManager(source);
    }

    private static DataSource pool(String url, String user,
                                   String pass, String name) {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(required(url));
        config.setUsername(required(user));
        config.setPassword(required(pass));
        config.setPoolName(name);
        config.setMaximumPoolSize(10);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(5000);
        return new HikariDataSource(config);
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing env: " + key);
        }
        return value;
    }
}
~~~

Ví dụ endpoint cấu hình (chỉ mẫu):

~~~text
ORDERS_WRITER_JDBC_URL=jdbc:postgresql://orders.cluster-abc.ap-southeast-1.rds.amazonaws.com:5432/orders?sslmode=verify-full
ORDERS_READER_JDBC_URL=jdbc:postgresql://orders.cluster-ro-abc.ap-southeast-1.rds.amazonaws.com:5432/orders?sslmode=verify-full
ORDERS_WRITER_USER=orders_rw
ORDERS_READER_USER=orders_ro
ORDERS_WRITER_PASSWORD=(inject-secret-for-lab)
ORDERS_READER_PASSWORD=(inject-secret-for-lab)
~~~

**Lưu ý cấu hình:**

- Trên PostgreSQL JDBC, `sslmode=verify-full` đòi **RDS CA bundle/trust store** phù hợp. Không tắt hostname verification để “sửa nhanh” lỗi certificate.
- Env placeholders chỉ minh họa wiring. Production nên tích hợp **Secrets Manager/secret rotation hoặc IAM DB authentication** theo engine và driver; không commit passwords vào repo/image.
- `maximumPoolSize(10)` là số minh họa. 100 ECS tasks × 2 pools × 10 có thể cần đến **2.000 DB connections**; phải so với `max_connections` và reserve cho administration/replication.
- Nếu dùng Spring Data JPA/Hibernate, cần cấu hình **EntityManagerFactory/transaction manager tương ứng từng datasource**, không suy ví dụ JDBC đã giải quyết mọi JPA mapping.

## 13. Java service: command dùng writer, query dùng reader

Tạo schema tại **writer** qua Flyway/Liquibase hoặc migration được duyệt:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(80) NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_orders_customer_created
    ON orders(customer_id, created_at DESC);
~~~

Service phân tách command/query:

~~~java
package com.example.orders.service;

import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final JdbcTemplate writerJdbc;
    private final JdbcTemplate readerJdbc;

    public OrderService(
            @Qualifier("writerJdbc") JdbcTemplate writerJdbc,
            @Qualifier("readerJdbc") JdbcTemplate readerJdbc) {
        this.writerJdbc = writerJdbc;
        this.readerJdbc = readerJdbc;
    }

    @Transactional(transactionManager = "writerTxManager")
    public void createOrder(String id, String customerId) {
        writerJdbc.update(
            "INSERT INTO orders(order_id, customer_id, status) VALUES (?, ?, ?)",
            id, customerId, "CREATED"
        );
        // Production: business validation, idempotency,
        // transactional outbox và authorization.
    }

    public OrderView getImmediatelyAfterWrite(String id) {
        // Cần read-your-writes: sử dụng writer.
        return writerJdbc.queryForObject(
            "SELECT order_id, status FROM orders WHERE order_id = ?",
            (rs, n) -> new OrderView(rs.getString(1), rs.getString(2)),
            id
        );
    }

    public List<OrderView> listRecent(String customerId) {
        // Query này chấp nhận eventual read.
        return readerJdbc.query(
            "SELECT order_id, status FROM orders "
                + "WHERE customer_id = ? ORDER BY created_at DESC LIMIT 50",
            (rs, n) -> new OrderView(rs.getString(1), rs.getString(2)),
            customerId
        );
    }

    public record OrderView(String orderId, String status) {}
}
~~~

**Điểm đúng:** DML và critical reads dùng writer, list view chấp nhận stale dùng reader. SQL dùng **prepared parameters** thay vì nối chuỗi input.

**Còn thiếu trước production:** Transactional outbox, retry safety, idempotent creates, tenant authorization, timeout/circuit breaker, secret rotation, failover behavior, schema migration và monitoring.

## 14. `@Transactional(readOnly=true)` không tự route sang replica

Spring annotation `@Transactional(readOnly = true)` cung cấp transaction hint/configuration cho ORM hoặc transaction manager; **không tự chọn AWS RDS reader endpoint**.

~~~java
@Transactional(readOnly = true)
public OrderView getOrder(String id) {
    // Vẫn đọc writer vì writerJdbc trỏ writer pool.
    return writerJdbc.queryForObject(
        "SELECT order_id, status FROM orders WHERE order_id = ?",
        (rs, n) -> new OrderView(rs.getString(1), rs.getString(2)),
        id
    );
}
~~~

Có thể triển khai `AbstractRoutingDataSource` và định tuyến theo context như `READ_EVENTUAL` / `READ_STRONG` / `WRITE`. Nhưng cần hiểu:

- Routing key cần tồn tại **trước lúc JDBC connection được lấy**.
- Nếu transaction manager lấy connection quá sớm, `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` có thể chưa phản ánh ý định route; `LazyConnectionDataSourceProxy` hoặc thiết kế interceptor có thể cần thiết.
- **Self-invocation** trong cùng class có thể không đi qua Spring AOP proxy, dẫn tới annotation không có hiệu lực như kỳ vọng.
- **Nested transaction** không được đổi physical database connection tùy tiện giữa writer và reader.
- **Open Session In View**, lazy loading hoặc JPA EntityManager có thể lấy connection ngoài thời điểm bạn dự tính.
- Cần integration tests xác nhận thật sự đang connected tới writer/reader, kể cả khi có failover.

**Cách an toàn để học:** Giữ hai JdbcTemplates/DataSources explicit cho tới khi có lý do mạnh và test đầy đủ để chuyển sang routing tự động.

## 15. Transaction consistency: không đọc replica để quyết định một write

Anti-pattern:

~~~text
BEGIN transaction trên writer
  SELECT inventory từ reader      → thấy 10 sản phẩm
  UPDATE inventory trên writer    → thực tế chỉ còn 2 sản phẩm
COMMIT
~~~

Đọc reader nằm trên một database connection khác, **không nằm trong cùng transaction snapshot/locks** của writer. Việc một method Java được đánh dấu `@Transactional` không tạo distributed transaction giữa hai DataSources.

Với nghiệp vụ thanh toán, tồn kho, chuyển tiền:

1. Đọc trạng thái hiện hành từ **writer** trong cùng transaction thích hợp.
2. Dùng **row lock**, **optimistic version**, **conditional update** hoặc isolation level theo yêu cầu.
3. Thực hiện DML và commit nguyên tử trong DB.
4. Ghi idempotency key/unique constraint để retry an toàn.
5. Không dùng reader cho phép stale để đưa ra quyết định có thể gây mất tiền hoặc vượt tồn kho.

**Transaction isolation** và **replication lag** là hai trục khác nhau: isolation điều phối các transactions trong database; replication lag mô tả reader đã bắt kịp writer đến đâu.

## 16. Reader endpoint phân phối kết nối, không chia mỗi truy vấn

Một reader endpoint có thể phân phối các TCP connections mới như sau:

~~~text
Reader endpoint:
  connection 1 → Reader A
  connection 2 → Reader B
  connection 3 → Reader B
  connection 4 → Reader C

Mọi SELECT trên connection 3 tiếp tục chạy trên Reader B
cho tới khi kết nối được đóng/chuyển.
~~~

Điều này ảnh hưởng:

- **Pool quá ít connections:** có thể không tận dụng đủ readers.
- **Pool quá nhiều connections:** có thể hết connection slots/memory; nhất là Lambda burst và nhiều ECS tasks.
- **Long-lived connections:** load distribution có thể lệch khi readers thêm/bớt.
- **Instance endpoint hardcoding:** kết nối không tự theo role mới khi failover.
- **Long-running queries:** làm một reader nghẽn dù reader khác còn rảnh.

Với Aurora, **custom endpoints** có thể nhóm instances cho BI/reporting theo tính năng hỗ trợ. Với RDS ordinary replicas, cần tự xây health-aware routing/load balancing hoặc dùng proxy/router hỗ trợ đúng engine/mô hình.

## 17. Tính toán read capacity và giới hạn scale-out

Giả sử 12.000 requests/giây, gồm:

- 20% writes/commands;
- 20% strong-consistency reads;
- 60% eventual-consistency reads.

Khi đó:

\[
Q_{\text{writer}}=12{,}000\times 40\%=4{,}800\text{ req/s}
\]

\[
Q_{\text{readers}}=12{,}000\times 60\%=7{,}200\text{ req/s}
\]

Nếu 3 readers chia tương đối đều:

\[
Q_{\text{per reader}}\approx 7{,}200/3=2{,}400\text{ req/s}
\]

**Đây là mô hình lưu lượng, không phải benchmark database.** Khả năng xử lý phụ thuộc query cost, index, CPU, memory, IOPS, buffer cache, locks và tốc độ apply replication.

### Khi nào thêm readers có ích?

- Writer bị bottleneck SELECT/ReadIOPS, trong khi write path vẫn đủ năng lực.
- Các SELECT có thể route sang eventual readers.
- Query plan và indexes tương đối tối ưu.
- App có routing, connection pools và monitoring lag thực tế.

### Khi nào thêm readers không giúp?

- Writer nghẽn **write latency/WriteIOPS/locks**.
- Phần lớn reads cần strong consistency và vẫn đi writer.
- SQL thiếu index, mỗi reader đều scan khối lượng lớn.
- Business reporting nên dùng analytics pipeline/warehouse thay vì OLTP replicas.
- Reader lag tăng vì replication apply bottleneck.

**Muốn scale writes**, cần chiến lược khác như tối ưu transaction/index, partitioning, sharding, caching thích hợp hoặc chọn database architecture khác; read replica không trở thành multi-writer chỉ nhờ tăng số instances.
## 18. RDS Proxy: quản lý connections và hỗ trợ failover

**Amazon RDS Proxy** là tầng proxy quản lý kết nối database, hữu ích khi application có số lượng connections biến động lớn, ví dụ Lambda burst hoặc ECS tasks scale theo traffic.

### RDS Proxy có thể giúp gì?

- Quản lý/reuse database connections theo điều kiện protocol và transaction.
- Giảm số kết nối mới đổ thẳng vào DB khi Lambda invocations tăng nhanh.
- Hỗ trợ ứng dụng reconnect/failover ổn định hơn trong một số tình huống.
- Tích hợp Secrets Manager/IAM authentication theo engine/feature support.
- Với **Aurora** và **RDS Multi-AZ DB cluster**, có thể cấu hình **read-only proxy endpoint** theo khả năng hỗ trợ, bên cạnh default read/write proxy endpoint.

~~~text
App writer pool → RDS Proxy default read/write endpoint → Writer
App reader pool → RDS Proxy READ_ONLY endpoint → Reader instances
~~~

**Không tự suy mọi RDS Proxy đều có read-only endpoint.** Cần kiểm tra engine, deployment type và đặc biệt phân biệt ordinary RDS single DB instance với Aurora/Multi-AZ DB cluster.

### RDS Proxy không thay thế gì?

- Không tự cập nhật mọi reader để chúng hết lag.
- Không làm read-after-write thành strongly consistent khi đọc replica.
- Không tự thêm Aurora Replicas hoặc RDS read replicas khi read QPS tăng.
- Không thay authorization/business transactions hoặc backup.
- Không bảo đảm query-level balancing khi connection/session được **pin**; temporary tables, session variables, transaction dài hoặc những đặc tính protocol có thể giảm multiplexing.

**Thiết kế đúng:** Nếu dùng proxy, vẫn có **writer/reader routing policy**, pool limits, lag alarms, idempotency và điều kiện nào được fallback tới writer.

## 19. Failover: ứng dụng phải kết nối lại và retry đúng

### 19.1. RDS ordinary read replica

Khi source primary bị lỗi, **read replica truyền thống không tự trở thành writer** như một Multi-AZ standby. Một lựa chọn DR là **promote read replica** theo quy trình, chấp nhận khả năng dữ liệu chưa replicate (RPO không bằng 0) và chuyển ứng dụng sang endpoint mới.

### 19.2. RDS Multi-AZ DB instance

Khi primary/AZ lỗi, RDS có thể **automatically fail over sang standby**. Ứng dụng kết nối lại bằng DB endpoint sau khi DNS/network cập nhật; standby trước đó không được dùng làm reader.

### 19.3. RDS Multi-AZ DB cluster

RDS có reader members là **automatic failover candidates**. Writer/reader endpoints giúp ứng dụng đi theo vai trò mới. **Semisynchronous replication không xóa mọi khả năng read lag** trên từng reader.

### 19.4. Aurora cluster

Aurora có thể promote một Aurora Replica thành writer. Cluster writer endpoint vẫn giữ tên DNS nhưng **instance đích thay đổi**. Reader endpoint cũng có thể đổi những readers có sẵn.

~~~mermaid
sequenceDiagram
    participant App as Java / HikariCP
    participant DNS as Writer endpoint DNS
    participant Old as Old Writer
    participant New as Promoted Aurora Reader
    App->>DNS: Resolve endpoint
    DNS-->>App: IP của old writer
    App->>Old: Transaction COMMIT
    Note over Old: Instance / AZ failure
    Note over New: Aurora promote reader thành writer
    App->>Old: Existing JDBC connection lỗi
    DNS-->>App: IP của new writer sau failover
    App->>DNS: Resolve và tạo connection mới
    App->>New: Retry thao tác an toàn
~~~

### Retry không được tạo duplicate writes

Một tình huống nguy hiểm:

~~~text
Client → INSERT order ORD-501 → writer COMMIT OK
Network → mất response trước khi client nhận được
Client → cho rằng INSERT chưa thực hiện, retry
~~~

Nếu retry không có **idempotency key/unique constraint**, có thể tạo thêm giao dịch hoặc gửi email/trừ tiền hai lần.

**Biện pháp:**

1. Gán `orderId` hoặc `Idempotency-Key` ổn định từ client/service.
2. Dùng DB unique constraint/conditional write hoặc transaction inbox/outbox.
3. Retry SQL theo loại lỗi và **không tự động replay non-idempotent DML** khi commit outcome không rõ.
4. Cấu hình JDBC connection timeout, socket timeout, Hikari fail-fast/connection health theo workload.
5. Xử lý DNS cache để kết nối mới nhận writer endpoint sau failover.
6. Thử failover thực trên lab và đo **RTO**, tỷ lệ 5xx, pool recovery, data reconciliation.

**Automatic failover không có nghĩa request đang chạy sẽ không lỗi.**

## 20. Cross-Region replica và Aurora Global Database

Để giảm độ trễ đọc cho users ở Region khác hoặc chuẩn bị disaster recovery:

- RDS có **cross-Region read replicas** cho một số engines/versions phù hợp.
- Aurora có **Aurora Global Database** với một primary Region và các secondary Regions theo khả năng hỗ trợ.
- Secondary Region có thể phục vụ đọc, nhưng có **cross-Region replication lag**, network latency và điều kiện failover/switchover riêng.

~~~mermaid
flowchart LR
    UserA[App Region A] --> Primary[(Writer Region A)]
    Primary -. Cross-Region replication .-> Secondary[(Reader Region B)]
    UserB[App Region B] --> Secondary
    Ops[DR Runbook] --> Fail[Switchover / Failover]
    Fail --> Secondary
~~~

**Không mặc định coi secondary là strongly consistent**. Ghi tại Region A rồi đọc ở Region B ngay có thể thấy dữ liệu cũ. Những truy vấn quan trọng nên route về primary hoặc dùng cơ chế consistency được hỗ trợ và đã kiểm thử.

### Write forwarding là tính năng riêng

Một số phiên bản Aurora MySQL/PostgreSQL có **local/global write forwarding** và các cấu hình consistency như `EVENTUAL`, `SESSION`, `GLOBAL`, theo engine và loại forwarding. Các mức này có thể yêu cầu chờ propagation và tăng latency.

**Không tự động có write forwarding chỉ vì đã dùng reader endpoint**, và không suy RDS ordinary read replica có chức năng tương đương. Kiểm tra parameter và tài liệu đúng engine/version trước khi dùng.

### DR cần hơn một replica

Một kế hoạch cross-Region tốt cần:

- Mục tiêu **RTO/RPO** định lượng.
- Route DNS/API/clients sang Region dự phòng.
- Mã hóa KMS key và secret có sẵn ở Region dự phòng theo thiết kế.
- Thử restore/failover, **fencing old writer** để tránh hai writer độc lập cùng nhận giao dịch.
- Reconcile dữ liệu chưa replicate và thông báo trạng thái cho users.
- Budget cho replication traffic, reader compute/storage, backup, logs và database networking.

**Không coi cross-Region replication là point-in-time backup**; xóa nhầm hoặc cập nhật sai có thể replicate sang Region khác.

## 21. Backup, promotion và khả năng phục hồi dữ liệu

Read replicas thường liên tục nhận **mọi thay đổi**, gồm cả thao tác nguy hiểm:

- Admin xóa nhầm đơn hàng.
- Migration cập nhật sai dữ liệu.
- User/ứng dụng bị chiếm quyền và chạy DML trái phép.
- Bug sửa trạng thái hàng triệu records.

Những thay đổi này cũng có thể đến replicas. Cần có **automated backups, PITR, AWS Backup/manual snapshots và restore tests** theo chính sách.

| Cơ chế | Giải quyết chính | Không giải quyết hoàn toàn |
| --- | --- | --- |
| Read replica | Scale đọc, một số kịch bản DR | Xóa nhầm/corruption, read-after-write |
| Multi-AZ standby | HA khi instance/AZ lỗi | Scale SELECT, PITR |
| Aurora readers | Scale đọc + failover candidates | Bất biến dữ liệu, strong reads mặc định |
| Automated backups/PITR | Khôi phục về điểm thời gian được hỗ trợ | Failover tức thì, mọi RTO |
| Manual snapshot/AWS Backup | Backup theo lịch/retention | Khả dụng tức thời |
| Cross-Region copy/Global Database | DR/đọc vùng khác | Đảm bảo zero-RPO cho mọi failure |
| Application logical backup | Khôi phục từng phần theo business | Quản trị consistency, retention và integrity |

### Khi muốn promote RDS read replica

**Chỉ thực hiện với quyền quản trị và DR runbook.**

1. Xác nhận source, Region, engine, reader endpoint và replication status.
2. Dừng/fence write traffic tới old primary hoặc xác minh nó không còn có thể nhận writes.
3. Xem `ReplicaLag` và xác định dữ liệu chưa tới replica; đặt RPO kỳ vọng.
4. Nếu nguồn còn chạy và mục tiêu cho phép, chờ replica catch up trước khi promote.
5. Kiểm tra backup retention, instance parameter group, DB subnet group, SG và authentication.
6. Promote một replica theo API hỗ trợ; theo dõi trạng thái đến khi thành standalone DB writer.
7. Chuyển writer JDBC URL/secret/pool, thử DML/SELECT và ứng dụng.
8. Reconcile giao dịch chưa replicate; không đưa old primary trở lại như một writer song song.
9. Thực hiện kế hoạch failback/migration riêng.

Promotion **không phải lệnh có thể đảo ngược tự động mà không ảnh hưởng hệ thống**. Tránh chạy trên production chỉ để thực hành.

## 22. Giám sát CloudWatch, Database Insights và ứng dụng

CloudWatch namespace **`AWS/RDS`** có nhiều metrics theo loại engine/instance.

| Metric | Tín hiệu | Khi cần điều tra |
| --- | --- | --- |
| **`ReplicaLag`** | Lag RDS read replicas và một số Multi-AZ readers | Vượt SLO, tăng không dừng, không xác định |
| **`AuroraReplicaLag`** | Lag Aurora reader instance | Reader apply chậm, stale reads |
| **`AuroraReplicaLagMaximum`** | Reader lag lớn nhất ở Aurora cluster khi hỗ trợ | Một reader lag quá cao có thể gây bất ổn |
| `CPUUtilization` | Áp lực CPU writer/reader | Reader query nặng hoặc replica apply nghẽn |
| `DatabaseConnections` | Số connections | Pool quá lớn, gần giới hạn |
| `ReadIOPS` / `ReadLatency` | I/O phục vụ SELECT | Query scan, cache miss hoặc storage bottleneck |
| `WriteIOPS` / `WriteLatency` | I/O ghi | Writer bottleneck, log pressure |
| `FreeableMemory` | Áp lực bộ nhớ | Cache/maintenance/queries |
| `FreeStorageSpace` | Storage còn lại theo loại RDS | WAL/binlog retention hoặc storage full |
| `TransactionLogsDiskUsage` | WAL logs theo engine/config | Replication slot giữ log quá lâu |
| Engine events/replication status | Replica lỗi/recovery/reconnect | Cần xử lý sớm trước mất data/availability |

**Lưu ý:** Không phải mọi metric xuất hiện cho mọi engine/version/instance class. Tên metric, dimension, units và giá trị `-1` phải được đối chiếu documentation của mô hình đang dùng.

### Database performance insights

Tùy khả năng engine/Region và sản phẩm **CloudWatch Database Insights/Performance Insights**, xem:

- Top SQL theo DB load và query latency.
- Wait events: CPU, locks, I/O.
- Query plans và missing indexes.
- Long transactions, WAL/binlog lag.
- Memory/connection pressure khi thêm nhiều tasks.

### Application observability

Đo riêng:

- p50/p95/p99 query latency **writer vs reader**.
- Tỷ lệ query route writer/reader.
- “POST thành công rồi GET không thấy” incidents.
- Số lần fallback writer vì reader unhealthy/lag.
- JDBC SQLSTATE, connection acquire timeout, pool active/idle/pending.
- Business duplicate write/transaction retry.
- Replication lag trong lúc traffic peak hoặc failover.

**Một metric `ReplicaLag=0` không tự chứng minh mọi GET ngay sau POST luôn nhất quán.** Hãy có integration tests đọc sau ghi để đo business SLO.

## 23. Cảnh báo lag và fallback không làm quá tải writer

Policy tham khảo:

~~~text
Reader healthy khi:
  DB instance available
  metrics/health probes đang được cập nhật
  lag dưới ngưỡng nghiệp vụ
  CPU và connection errors không cao kéo dài

Reader degraded khi:
  lag > 2s trong một số samples liên tiếp
  hoặc query latency/errors tăng
  hoặc reader đang maintenance/failover

Khi degraded:
  critical reads -> writer
  optional reads -> cache/stale response hoặc chờ có kiểm soát
  reports -> backoff/pause
  giám sát writer CPU/DBConnections để không gây sập writer
~~~

**Đây là policy ứng dụng, không phải một setting RDS tự cấu hình.** CloudWatch sampling có delay, nên routing thời gian thực có thể cần active health checks, circuit breaker, timeout và metrics ở ứng dụng.

### Không fallback mọi SELECT vô điều kiện

Nếu reader lỗi làm 7.000 read QPS chuyển về writer vốn đã xử lý nhiều writes, writer có thể nghẽn và gây outage lớn hơn. Phân loại theo độ quan trọng:

- Read quan trọng → writer, nhưng có rate limit.
- Catalog/analytics → serve cache hoặc 503/429 với retry hints nếu SLO cho phép.
- BI jobs → tạm ngừng.
- Kiểm soát write throughput/transaction availability trước khi quyết định mở thêm traffic.

**Graceful degradation quan trọng hơn “mọi request luôn trả 200”.**

## 24. VPC, IAM, Secrets Manager, KMS và TLS

### VPC/Network

Database production thường nằm trong **private subnets** thuộc DB subnet group trải nhiều AZ theo mô hình; application cần route, DNS và security groups phù hợp:

- PostgreSQL: **TCP 5432**.
- MySQL: **TCP 3306**.
- RDS SG inbound chỉ từ **ECS task SG, EC2 SG, Lambda VPC SG hoặc RDS Proxy SG**, không mở toàn Internet.
- NACL/route/DNS phải cho phép đường đi/return traffic hợp lệ.
- Nếu app ở on-prem, cần VPN/Direct Connect hoặc mạng kết nối riêng, cùng giải pháp DNS.

### Mã hóa và xác thực

- Bật **encryption at rest** với KMS theo yêu cầu bảo mật; xác minh KMS key policy và khả năng khôi phục từ snapshot.
- Dùng **TLS** và xác minh server certificate/hostname bằng CA bundle chính thức.
- Lưu mật khẩu trong **AWS Secrets Manager**; cấu hình rotation và kết nối tự thay credentials đúng thời điểm.
- Cân nhắc **IAM database authentication** khi engine/instance/driver hỗ trợ, với token có thời hạn ngắn; connection pool cần refresh token an toàn.
- Tách DB users `orders_rw` và `orders_ro` có SQL GRANT phù hợp. Đừng chỉ dựa reader endpoint để ngăn DML.
- Giảm quyền IAM của application: chỉ lấy đúng secret, `rds-db:connect` khi dùng IAM auth và những AWS API cần thiết.

| Principal | Quyền cần xem |
| --- | --- |
| Java ECS task role/Lambda execution role | Secrets Manager, KMS, IAM DB auth khi áp dụng |
| SQL user `orders_rw` | INSERT/UPDATE/DELETE/SELECT cần cho transaction |
| SQL user `orders_ro` | SELECT trên schema/tables được phép |
| DBA/schema migration role | DDL/maintenance theo quy trình |
| Infrastructure operator | Describe/CreateReplica/Promote/Modify theo change approval |
| KMS key administrators | Key policy/grants theo phạm vi và audit |

**AWS IAM control plane permission không đồng nghĩa database SQL GRANT**. Một task role có `rds:DescribeDBInstances` chưa được phép đọc rows; phải có database authentication và SQL privileges.

## 25. Thực hành 1 — Tạo RDS PostgreSQL read replica bằng AWS CLI

> **Chi phí và an toàn:** Tạo replica thật phát sinh phí compute/storage/I/O/backup. Chỉ thao tác trong account lab được phép. Không tạo/promote/xóa DB production và không dùng dữ liệu khách hàng. Ví dụ dùng Region `ap-southeast-1`, profile `lab`, có sẵn source DB instance `orders-primary-lab` đúng engine/version và backup prerequisites.

### 25.1. Xem source

~~~bash
aws sts get-caller-identity --profile lab

aws rds describe-db-instances \
  --db-instance-identifier orders-primary-lab \
  --region ap-southeast-1 \
  --profile lab \
  --query 'DBInstances[0].{Id:DBInstanceIdentifier,Engine:Engine,Version:EngineVersion,Status:DBInstanceStatus,MultiAZ:MultiAZ,BackupRetention:BackupRetentionPeriod,Endpoint:Endpoint.Address}'
~~~

Xác nhận source:

- Là **RDS DB instance**, không nhầm Aurora DB cluster.
- Engine/version hỗ trợ read replicas trong Region.
- Automated backup retention và prerequisites phù hợp.
- Instance class, network/SG, DB subnet group, encryption và quota đủ điều kiện.
- Workload write đủ ổn định để tạo replica mà không gây tác động không mong muốn.

### 25.2. Tạo read replica

~~~bash
aws rds create-db-instance-read-replica \
  --db-instance-identifier orders-reader-lab \
  --source-db-instance-identifier orders-primary-lab \
  --db-instance-class db.t4g.medium \
  --no-publicly-accessible \
  --region ap-southeast-1 \
  --profile lab
~~~

**`db.t4g.medium` chỉ là ví dụ.** Phải xác nhận engine/version/Region hỗ trợ class này và tài nguyên replica đủ cho load/replication apply.

### 25.3. Kiểm tra endpoint và trạng thái

~~~bash
aws rds describe-db-instances \
  --db-instance-identifier orders-reader-lab \
  --region ap-southeast-1 \
  --profile lab \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Source:ReadReplicaSourceDBInstanceIdentifier,Endpoint:Endpoint.Address,AZ:AvailabilityZone,Class:DBInstanceClass}'
~~~

Khi `DBInstanceStatus=available`, xem replication status và **ReplicaLag** qua RDS Console/CloudWatch. **Endpoint xuất hiện không đồng nghĩa replica đã catch up hoặc phù hợp nhận production traffic.**

### 25.4. Application phải tự định tuyến

Tạo read replica không tự sửa Java JDBC URL. Ứng dụng cần thêm **reader pool**, query routing và test consistency. Đo:

- Writer `CPUUtilization` và query latency trước/sau.
- Reader CPU/IO/connections.
- `ReplicaLag` qua nhiều trạng thái tải.
- Business GET-after-POST behavior.

## 26. Thực hành 2 — Xem Aurora writer và reader endpoints

Giả sử Aurora PostgreSQL cluster lab tên `orders-aurora-lab` đã có writer và một reader.

### Xem cluster endpoints

~~~bash
aws rds describe-db-clusters \
  --db-cluster-identifier orders-aurora-lab \
  --region ap-southeast-1 \
  --profile lab \
  --query 'DBClusters[0].{Status:Status,WriterEndpoint:Endpoint,ReaderEndpoint:ReaderEndpoint,Members:DBClusterMembers}'
~~~

Trường `DBClusterMembers` có thể cho biết `IsClusterWriter` để xác định writer/reader hiện tại. Nếu reader endpoint tồn tại nhưng cluster chỉ có writer healthy, đọc lại mục 8 trước khi coi endpoint đó chỉ đọc.

### Xem từng DB instance

~~~bash
aws rds describe-db-instances \
  --region ap-southeast-1 \
  --profile lab \
  --query 'DBInstances[*].{Id:DBInstanceIdentifier,Cluster:DBClusterIdentifier,Status:DBInstanceStatus,AZ:AvailabilityZone,Endpoint:Endpoint.Address,Class:DBInstanceClass}'
~~~

Lọc theo `DBClusterIdentifier=orders-aurora-lab` trong kết quả. Tránh trộn endpoints của các clusters trong một account lab có nhiều tài nguyên.

### Tạo reader mới (lab được phép, tốn phí)

~~~bash
aws rds create-db-instance \
  --db-instance-identifier orders-aurora-reader-lab \
  --db-cluster-identifier orders-aurora-lab \
  --engine aurora-postgresql \
  --db-instance-class db.r6g.large \
  --no-publicly-accessible \
  --region ap-southeast-1 \
  --profile lab
~~~

**Kiểm tra trước:** DB ID chưa tồn tại, engine/class/version tương thích, Aurora Serverless/provisioned configuration và quota cho phép. Aurora reader được thêm bằng cách tạo **DB instance thuộc Aurora cluster**; không lẫn với lệnh `create-db-instance-read-replica` dành cho RDS ordinary instances.

## 27. Thực hành 3 — Kiểm tra quyền ghi và dữ liệu qua SQL

### PostgreSQL / Aurora PostgreSQL

Kết nối riêng tới writer/reader bằng JDBC hoặc `psql` và thử:

~~~sql
-- PostgreSQL: đọc trạng thái recovery của server khi áp dụng.
SELECT pg_is_in_recovery();

-- Kiểm tra mode read-only của transaction hiện tại.
SHOW transaction_read_only;

-- Query dữ liệu nghiệp vụ:
SELECT order_id, status
FROM orders
WHERE order_id = 'ORD-1001';
~~~

Với RDS PostgreSQL physical replica, `pg_is_in_recovery()` có thể hữu ích. Nhưng với Aurora/tính năng đặc thù, **không suy toàn bộ consistency hay cluster role chỉ từ một SQL function**; đối chiếu endpoint, `IsClusterWriter` và database user permissions.

Chạy trên **writer lab**:

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES ('ORD-LAB-100', 'C-LAB', 'CREATED');
~~~

Sau COMMIT, query ngay reader:

~~~sql
SELECT order_id, status
FROM orders
WHERE order_id = 'ORD-LAB-100';
~~~

Có thể thấy row ngay hoặc chưa thấy tùy replica lag. **Nếu test một lần thấy ngay, không chứng minh luôn có strong consistency**. Cần thử dưới traffic khác nhau, đo lag và failure modes.

### MySQL/MariaDB (engine/version tương thích)

~~~sql
SELECT @@read_only, @@super_read_only;
SHOW REPLICA STATUS;
~~~

Một số phiên bản cũ dùng `SHOW SLAVE STATUS`. Lệnh này không đồng nghĩa có cùng semantics trên **Aurora shared storage**; kiểm tra engine-specific replication monitoring thay vì copy một SQL command cho mọi database.

### Cẩn trọng với công thức lag PostgreSQL

`now() - pg_last_xact_replay_timestamp()` có thể lớn khi writer không có thay đổi mới, dù reader đã bắt kịp; không dùng kết quả đơn lẻ làm lag SLO tuyệt đối. Dùng CloudWatch replication metrics, WAL positions khi cần và business read-after-write tests.

## 28. Thực hành 4 — Thử degraded mode và failover

**Chỉ thực hiện trong môi trường lab có backup, không chạy force failover trên production.**

### A. Read scaling

1. Đo baseline writer query latency, CPU/IO và connections.
2. Tạo reader, chuyển một phần `GET /products` eventual reads.
3. Load test có giới hạn, đo writer/reader query p95/p99 và ReplicaLag.
4. Nếu quá tải, tối ưu SQL/index trước khi tăng instance count.
5. Xác minh critical reads vẫn trả giá trị mới qua writer.

### B. Reader bị lag

1. Tạo một lượng ghi vừa phải ở writer lab.
2. Ghi thời điểm commit và lúc reader thấy record.
3. Tăng cảnh báo hoặc đánh dấu reader degraded khi vượt SLO.
4. Fallback **critical reads** tới writer; ngừng báo cáo nặng.
5. Không chuyển toàn bộ traffic sang writer nếu writer có nguy cơ quá tải.

### C. Aurora writer failover

1. Lưu trước endpoint/`IsClusterWriter`/application pool metrics.
2. Tạo một giao dịch nhỏ có idempotency key.
3. Dùng AWS Console/CLI **failover chỉ trên cluster lab** khi được phép.
4. Quan sát DNS refresh, JDBC stale connections, reconnect và business retry.
5. Xem cluster members sau failover, xác minh writer/reader role.
6. Đối chiếu order count/unique key để bảo đảm không tạo duplicate.
7. Đo RTO thực tế và cập nhật runbook.

### D. RDS promotion drill

1. Snapshot/backup dữ liệu giả, ghi tiến độ source/replica.
2. Dừng writes tới source hoặc fence old primary.
3. Promote read replica theo engine được hỗ trợ, xác nhận nó có write capability.
4. Chuyển app writer pool qua endpoint mới.
5. Kiểm tra RPO/dữ liệu chưa replicate và reconciliation.
6. Xử lý old primary không tạo split-brain.

## 29. Kiến trúc theo tình huống thực tế

### A. API đặt hàng, kiểm tra tồn kho

**Writes và critical reads**: writer trong transaction; dùng row locks/optimistic version/unique keys để kiểm tra stock và idempotency. **Catalog và order history**: reader nếu stale được chấp nhận. Có RDS Multi-AZ/Aurora failover + PITR, CloudWatch alerts, connection pools tối ưu.

### B. Dashboard hoạt động trong ngày

Dùng reporting reader hoặc read model riêng. Dashboard được phép chậm 2–10 giây theo SLA; không dùng nó làm nguồn quyết định thu tiền. Nếu aggregate quét dữ liệu rất lớn, chọn ETL/S3/Athena/Redshift hoặc materialized views theo engine để giảm áp lực OLTP.

### C. Lambda burst + Aurora

Lambda mở nhiều database connections. Dùng **RDS Proxy** theo support, default proxy endpoint cho commands/critical reads và read-only endpoint cho eventual queries khi hỗ trợ. Giới hạn concurrency/downstream connections, dùng secrets/IAM auth/TLS, retry an toàn.

### D. Ứng dụng nhiều Region

Chọn cross-Region replica/Aurora Global Database để cung cấp eventual reads gần người dùng; các writes và read-after-write truy vấn về primary hoặc cơ chế consistency được xác minh. Có DR/failover policy, không hứa RPO=0 chỉ vì có secondary Region.

### E. Truy vấn dữ liệu thanh toán/đối soát

Không gửi logic quyết định tài chính sang reader bất đồng bộ. Dùng writer transaction/locking/unique constraints, backup/PITR và audit. Replica chỉ phục vụ báo cáo/historical views không có yêu cầu strong consistency.

## 30. Chi phí và lựa chọn số readers

### RDS DB instance read replica

Chi phí có thể gồm:

- DB instance hours theo class/engine/license.
- Storage riêng, IOPS/throughput và backup/snapshot.
- Cross-Region replication/data transfer khi có.
- RDS Proxy, Secrets Manager, KMS, logs, Database Insights.
- Networking/VPC endpoints và hoạt động quản trị.

AWS có cơ chế không tính phí **data transfer replication giữa RDS source và read replica cùng AWS Region** theo trường hợp áp dụng; **không suy điều đó áp dụng cross-Region**.

### Aurora Replicas

Aurora readers dùng chung **cluster volume** nên không nhân toàn bộ storage riêng theo mỗi Aurora Replica như mô hình RDS ordinary replicas. Nhưng vẫn phát sinh compute instances/ACUs và storage/I/O/backup/network theo cấu hình Aurora Standard/I/O-Optimized/Serverless và pricing hiện hành.

| Phương án | Chi phí chính | Độ phức tạp | Khi chọn |
| --- | --- | --- | --- |
| Nâng instance writer | Instance class lớn hơn | Thấp | Primary CPU/IO thiếu nhưng query đã tối ưu |
| Thêm 1 RDS reader | Reader compute + storage/I/O | Vừa | Read-heavy và app route rõ |
| Nhiều RDS readers | Nhiều compute/storage instances | Cao hơn | Nhiều eventual reads, có health routing |
| RDS Multi-AZ DB cluster | Writer + 2 readers, cluster storage | Vừa | HA + đọc scale |
| Aurora + readers | Shared cluster volume + reader compute | Vừa | HA/read scaling theo Aurora |
| Redis/ElastiCache cache | Cache compute/storage | Vừa | Catalog/reads lặp lại, TTL chấp nhận |
| Analytics warehouse | ETL + compute/storage analytics | Cao | Reporting/BI nặng tách khỏi OLTP |

**Không mua reader nếu query chỉ cần thêm index.** Tính chi phí trên **mỗi 1.000 successful read requests dưới latency/consistency SLO**, dùng **AWS Pricing Calculator/Cost Explorer/Budgets** theo Region/class/engine thực.

## 31. Troubleshooting: triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| POST thành công rồi GET trả 404 | Reader chưa apply commit | Route writer cho read-after-write, ReplicaLag |
| Read replica chậm | Query scan, CPU/IO thấp, apply lag | EXPLAIN, Top SQL, CloudWatch |
| Writer vẫn quá tải reads | App không route đúng, quá nhiều strong reads | JDBC endpoints, per-pool metrics |
| Reader endpoint cho phép DML | Aurora chỉ có writer/không healthy readers; DB account quá rộng | Cluster members, read-only SQL user |
| Ghi lỗi read-only | DML bị route vào reader | Service routing, DB endpoint, transaction |
| RDS standby không đọc được | Multi-AZ DB instance standby chỉ dành HA | Xem deployment type |
| RDS Multi-AZ DB cluster reader dữ liệu cũ | Semisync ack chưa đồng nghĩa apply | ReplicaLag, transactions |
| `ReplicaLag=-1` | AWS không xác định lag | Check replica status/error, không coi -1 là tốt |
| `@Transactional(readOnly=true)` vẫn writer | Không có router hoặc connection lấy quá sớm | RoutingDataSource, TX timing, LazyConnectionDataSourceProxy |
| Aurora reader instances phân bố CPU lệch | Reader endpoint chọn connections, pool pinning | DBConnections, Hikari lifetime |
| Failover xong app vẫn lỗi | DNS caching, stale TCP/JDBC pool, retries sai | RDS events, connection validation, DNS TTL |
| Retry tạo đơn trùng | Commit outcome không rõ, thiếu idempotency | Unique key, transaction/outbox |
| Tạo replica thất bại | Engine/version/class/backup prerequisites hoặc quota | RDS API error, source config |
| Replica replication-error | Log retention/WAL/binlog/network, apply error | RDS Events, replica status |
| Cross-Region reader trả data cũ | Replication delay | Global/cross-region lag metrics |
| Lambda bão DB connections | Concurrency cao, pool/proxy không hợp | RDS Proxy, max_connections, Lambda concurrency |
| Cannot connect | SG/NACL/route/DNS/TLS, DB auth | VPC/Flow Logs, DB endpoint, KMS |
| Snapshot restore không đủ | PITR/backup chưa thử, retention sai | Backup/restore drill, RTO/RPO |
| Chi phí tăng | Reader instances ít dùng, cross-Region/proxy/logs | Cost Explorer, tags, reader utilization |

### Quy trình điều tra theo lớp

~~~text
1. Xác định account, Region, engine/version và deployment type.
2. Phân biệt RDS instance replica / Multi-AZ standby / cluster readers / Aurora.
3. Xem writer/reader endpoints thực, IsClusterWriter và JDBC URL/pools.
4. Reproduce read-after-write, ghi orderId/eventId và thời điểm commit.
5. So ReplicaLag/AuroraReplicaLag + CPU/IO/connections của từng instance.
6. Xem query plan/index, transaction length, WAL/binlog, locks.
7. Nếu lỗi kết nối: SG/VPC/DNS/TLS/RDS Proxy/Hikari/JVM caching.
8. Nếu failover: RDS events, DNS, retry/idempotency, data reconciliation.
9. Nếu DR: backup/PITR/replication lag, restore/protection và budget.
10. Sửa một nguyên nhân rồi test happy path + stale/failure paths.
~~~

**Không chữa lỗi bằng:** bỏ TLS, mở SG toàn Internet, dùng DB superuser cho app, bỏ backup hoặc route tất cả read QPS sang writer bất kể capacity.

## 32. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1 — Multi-AZ không có reader

Một hệ thống RDS PostgreSQL đang bật **Multi-AZ DB instance** với standby AZ B. Nhóm phát triển muốn chuyển 5.000 read QPS sang standby.

**Yêu cầu:** Giải thích vì sao không thể. Đề xuất thêm RDS read replica, đổi sang Multi-AZ DB cluster hoặc Aurora theo nhu cầu HA/read scale, so sánh độ trễ và thay đổi trong application.

### Bài tập 2 — Read-after-write

Frontend POST tạo ORD-9 trả 201 rồi GET ngay từ replica báo 404 khoảng 300 ms. Hãy xác định lý do và hai cách giải quyết; phân biệt sticky writer window với guarantee từ writer.

### Bài tập 3 — Pool connections

Có 80 ECS tasks, mỗi task tạo writer pool tối đa 12 connections và reader pool tối đa 20 connections.

\[
80\times(12+20)=2{,}560\text{ connections}
\]

Nếu writer capacity chỉ 400 connections và hai readers mỗi instance 500, nêu vấn đề có thể xảy ra và cách tối ưu pool sizes, task autoscaling, proxy và connection lifetime.

### Bài tập 4 — Aurora endpoint failover

Aurora có writer A, readers B/C. B hỏng, C được promote writer khi A hỏng. Hãy dự đoán hướng route writer/reader endpoints, lỗi JDBC connections cũ và nguy cơ reader endpoint trỏ writer nếu không còn healthy reader.

### Bài tập 5 — Semisynchronous commit

RDS Multi-AZ DB cluster writer A nhận acknowledgment từ reader B nhưng C chưa apply đầy đủ. Có thể đọc dữ liệu cũ ở C không? Tại sao semisynchronous replication không chứng minh read-your-writes? Đề xuất cách route tài chính vs dashboard.

### Bài tập 6 — Replica lag cao

Replica CPU 95%, p99 SELECT latency 6 giây, ReplicaLag 8 giây, writer CPU chỉ 45%.

**Yêu cầu:** Đề xuất thứ tự kiểm tra top SQL/index, reader instance class, reporting jobs, connections và replication apply. Nếu read service fallback về writer, làm gì để tránh gây writer overload?

### Bài tập 7 — Promotion DR

Source RDS PostgreSQL ở Region A bị lỗi; read replica ở Region B báo lag 30 giây. Nhóm muốn promote và nhận writes.

Hãy trình bày RPO tiềm ẩn, backup, old writer fencing/split-brain, cross-Region secrets/KMS, DNS/connection routing, dữ liệu chưa replicate và reconciliation.

### Bài tập 8 — Sai transaction

~~~java
@Transactional
public void approvePayment(long orderId) {
    Order order = readRepository.findById(orderId);
    writeRepository.markPaid(orderId);
}
~~~

Nếu `readRepository` trỏ replica đang lag, hãy mô tả race condition; thiết kế lại writer transaction với version/lock và idempotency. Tại sao Spring `@Transactional` không tạo một transaction nguyên tử giữa hai DataSources?

### Bài tập 9 — Chi phí

Có 1 RDS writer, 4 same-Region replicas, 1 cross-Region DR replica và 2 RDS Proxies. Sau khi cache catalog, read QPS giảm 70%.

Hãy lập cost model compute/storage/I/O/transfer/proxy/cache/backup/monitoring, chọn readers có thể giảm mà không phá HA/DR và đo kết quả theo latency SLO.

### Câu hỏi ngắn

1. **RDS DB instance read replica đồng bộ hay bất đồng bộ?** Chủ yếu bất đồng bộ.
2. **Standby của RDS Multi-AZ DB instance có đọc được không?** Không.
3. **RDS Multi-AZ DB cluster thông thường có bao nhiêu reader members?** Hai.
4. **Aurora Replica có full storage copy riêng không?** Không; shared logical cluster volume.
5. **Aurora hỗ trợ tối đa bao nhiêu Aurora Replicas trong mô hình thông thường?** 15 theo giới hạn được công bố.
6. **Aurora reader endpoint balance theo query hay connection?** Theo kết nối mới.
7. **Reader endpoint Aurora có thể trỏ writer không?** Có nếu không còn healthy reader.
8. **`ReplicaLag=0` bảo đảm mọi GET sau POST luôn thấy ngay không?** Không phải transaction-level guarantee.
9. **`@Transactional(readOnly=true)` tự sửa JDBC URL không?** Không.
10. **Có dùng replica quyết định tồn kho trong writer transaction không?** Không nên.
11. **Ordinary RDS read replica tự lên writer khi source lỗi không?** Không mặc định.
12. **Aurora failover tự động có cần client reconnect không?** Có.
13. **RDS Proxy có xóa replication lag không?** Không.
14. **Thêm read replicas có tăng write capacity trực tiếp không?** Không.
15. **Replica có thay backup/PITR không?** Không.
16. **Cross-Region reader luôn strongly consistent không?** Không.
17. **Read endpoint là lớp bảo mật SQL read-only tuyệt đối không?** Không.
18. **Đo gì khi failover?** RTO/RPO, error rate, connection recovery, idempotency/data integrity.

## 33. Checklist trước production

- [ ] Đã nhận diện đúng RDS DB instance, Multi-AZ DB instance, Multi-AZ DB cluster và Aurora cluster.
- [ ] Có hiểu biết rõ standby HA không phục vụ đọc, read replica có lag, cluster readers có thể failover.
- [ ] Phân loại từng use case theo strong/read-after-write/eventual consistency.
- [ ] Writes, transaction checks, authorization/inventory/balance và critical reads đi writer.
- [ ] Reporting/catalog eventual reads đi replica; app dùng reader endpoint/instance URL đúng mô hình.
- [ ] Không giả định Aurora reader endpoint phân phối query-level hoặc luôn chặn write.
- [ ] RDS ordinary replicas có health/routing riêng, không giả định có cluster reader endpoint.
- [ ] Java JDBC/Hikari/JPA transaction managers được test thật với hai connections.
- [ ] Routing theo annotation/AOP có kiểm tra connection acquisition, proxy order, LazyConnectionDataSourceProxy.
- [ ] Có idempotency và unique keys cho writes nếu failover/network timeout khiến kết quả commit không rõ.
- [ ] Có ReplicaLag/AuroraReplicaLag, CPU/I/O, DBConnections, p95/p99 SQL/application metrics.
- [ ] Có SLO cho stale reads và fallback/rate limit không làm writer quá tải.
- [ ] Query plans, indexes, pagination, cache và long transactions được tối ưu trước khi scale.
- [ ] Multi-AZ/Aurora readers trải AZ, failover promotion tiers và app DNS/reconnect đúng.
- [ ] RDS Proxy dùng theo engine/cluster hỗ trợ; reader proxy endpoints chỉ khi thích hợp.
- [ ] VPC private subnets/SG/TLS/Secrets Manager/KMS/IAM DB auth được giới hạn đúng.
- [ ] Backup/PITR/snapshot và restore drills độc lập với read replicas.
- [ ] Cross-Region/Global Database có DR/failover/fencing, RTO/RPO và reconciliation.
- [ ] Có dashboard reader health và runbook xử lý replication lag, read stale, JDBC failover.
- [ ] Có IaC/change review, schema migration test tương thích writer/replicas.
- [ ] Đã dự toán instance/storage/I/O/cross-Region/proxy/cache/logs/backup.
- [ ] Đặt AWS Budgets, tags và quy trình scale down/cleanup an toàn.
- [ ] Thực hành lỗi: reader down, writer failover, DNS cũ, lag cao, DB restore và data integrity.

## 34. Tổng kết

**Read replica** tăng năng lực đọc bằng cách chuyển những SELECT **chấp nhận dữ liệu cũ ngắn hạn** khỏi primary. Nhưng hiệu quả phụ thuộc **định tuyến ứng dụng, connection pooling, database engine và replication lag**.

Bốn mô hình cần phân biệt:

1. **RDS DB instance read replica:** replication bất đồng bộ, endpoint riêng, tăng read capacity và có thể promote có kế hoạch, **không tự là failover standby**.
2. **RDS Multi-AZ DB instance standby:** HA/failover, **không phục vụ SELECT**.
3. **RDS Multi-AZ DB cluster:** writer + hai readable readers, semisynchronous và automatic failover; reader vẫn có thể trễ apply.
4. **Amazon Aurora:** writer và tối đa 15 readers dùng shared logical cluster volume, cluster writer/reader endpoints, automatic failover; **reader endpoint cân bằng kết nối, không cân bằng từng SQL query**.

Trong Java, một điểm khởi đầu tốt là **hai connection pools tường minh**: writer cho commands/transactions/critical reads, reader cho eventual reads. Kết hợp **idempotency, transaction isolation, lag/health monitoring, IAM/KMS/VPC/TLS, backup/restore, RDS Proxy khi phù hợp và AWS Budgets** để vừa tăng năng lực đọc vừa bảo vệ dữ liệu.

### Tài liệu chính thức

- [Working with RDS DB instance read replicas](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.html)
- [Creating RDS read replicas](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.Create.html)
- [Monitoring RDS read replication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.Monitoring.html)
- [RDS Multi-AZ DB instance deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZSingleStandby.html)
- [RDS Multi-AZ DB cluster deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/multi-az-db-clusters-concepts.html)
- [RDS Multi-AZ DB cluster read replicas](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_MultiAZDBCluster_ReadRepl.html)
- [RDS Multi-AZ DB cluster endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/multi-az-db-clusters-concepts-connection-management.html)
- [Aurora DB clusters](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.html)
- [Aurora Replication](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Replication.html)
- [Aurora reader endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoints.Reader.html)
- [Aurora cluster endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.Endpoints.html)
- [Aurora failover](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-failover.html)
- [Aurora Global Database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database.html)
- [Aurora write forwarding consistency](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-mysql-write-forwarding-consistency.html)
- [RDS Proxy endpoints for Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/rds-proxy-endpoints.html)
- [Amazon RDS CloudWatch metrics](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-metrics.html)
- [RDS Pricing](https://aws.amazon.com/rds/pricing/) và [Aurora Pricing](https://aws.amazon.com/rds/aurora/pricing/)
- [AWS CLI RDS command reference](https://docs.aws.amazon.com/cli/latest/reference/rds/)

**Lưu ý vận hành:** Mô hình engine/version, số replicas, endpoint behavior, metrics, quotas và giá có thể thay đổi theo Region/account và thời điểm. Đối chiếu tài liệu AWS mới nhất, kiểm thử consistency theo nghiệp vụ và diễn tập failover/restore trong lab trước khi triển khai production.


