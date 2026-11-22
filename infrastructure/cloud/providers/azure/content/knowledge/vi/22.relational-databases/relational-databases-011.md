# High availability, read replica và geo-replication

Một hệ thống thương mại điện tử lưu đơn hàng trong cơ sở dữ liệu quan hệ trên Azure. Khi một máy chủ gặp sự cố, người dùng vẫn phải đặt hàng được. Trong giờ cao điểm, hàng chục báo cáo đọc nhiều dữ liệu không được làm chậm giao dịch thanh toán. Nếu một vùng Azure bị gián đoạn kéo dài, công ty phải có khả năng khôi phục hệ thống ở vùng khác.

Ba yêu cầu đó nghe giống nhau nhưng thực chất cần ba cơ chế khác nhau:

- **High availability (HA)**: duy trì tính sẵn sàng và tự động hoặc có kiểm soát chuyển dịch vụ sang thành phần dự phòng khi có sự cố trong phạm vi thiết kế.
- **Read replica**: tạo bản sao phục vụ đọc và phân tán tải truy vấn, thường với độ trễ sao chép nhất định.
- **Geo-replication**: sao chép dữ liệu giữa các vùng địa lý để hỗ trợ đọc từ xa hoặc kế hoạch khôi phục thảm họa (disaster recovery, DR), với cơ chế và giới hạn khác nhau tùy dịch vụ.

Không nên gộp ba khái niệm thành một chức năng “sao lưu dữ liệu”. Một read replica **không tự là bản backup bất biến**, một HA standby **không đương nhiên phục vụ truy vấn đọc**, và geo-replication **không bảo đảm RPO bằng không** khi sao chép bất đồng bộ.

Bài này thuộc chương **Cơ sở dữ liệu quan hệ** của module `CLOUD_PROVIDERS_AZURE`. Trong hệ sinh thái Microsoft Azure, từ subscription, resource group và Microsoft Entra ID đến VNet, compute, storage, database, giám sát và chi phí, bài học tập trung vào thiết kế độ sẵn sàng cho **Azure SQL Database**, **Azure Database for PostgreSQL Flexible Server** và **Azure Database for MySQL Flexible Server**. Những tính năng cụ thể phụ thuộc dịch vụ, tier, version, region và chính sách hiện hành.

> Các tài nguyên, tên server, câu lệnh và mốc thời gian trong bài là ví dụ minh họa. Không thực hiện failover, promote replica, đổi DNS hoặc sửa topology trên Production nếu chưa có phê duyệt và runbook. Với quyết định về SLA, giới hạn, giá hoặc khả năng hỗ trợ từng vùng, kiểm tra thông tin thực tế của dịch vụ và subscription tại thời điểm triển khai.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **HA, read replica, geo-replication, backup/PITR và disaster recovery**.
2. Giải thích **synchronous** và **asynchronous replication** cùng hệ quả về latency, consistency và nguy cơ mất dữ liệu.
3. Định nghĩa **RTO, RPO, availability target**, phạm vi lỗi và chi phí downtime.
4. So sánh HA và bản sao đọc trong Azure SQL Database, PostgreSQL Flexible Server và MySQL Flexible Server.
5. Thiết kế chiến lược đọc/ghi qua primary, read endpoint và replica; xử lý **replication lag**.
6. Mô tả active geo-replication/failover groups của Azure SQL Database và những đặc điểm cần chú ý của các read replica xuyên vùng trên PostgreSQL/MySQL.
7. Phân biệt **failover** với **replica promotion**, và đánh giá rủi ro mất dữ liệu khi chuyển vùng.
8. Thiết kế mạng riêng, TLS, identity, DNS, connection pooling và quyền đọc/ghi phù hợp.
9. Quan sát replica lag, failover events, CPU, storage, connection count và error rate.
10. Lập kế hoạch thử nghiệm failover/DR drill, failback và đối soát dữ liệu.
11. Dùng Portal và Azure CLI để kiểm tra topology trước khi thao tác có rủi ro.
12. Tính toán trade-off giữa availability, consistency, hiệu năng, khoảng cách vùng và chi phí.

## 2. Câu chuyện mở đầu: ba loại sự cố, ba cơ chế

Một ứng dụng Orders API dùng cơ sở dữ liệu SQL với ba yêu cầu:

| Tình huống | Câu hỏi cần trả lời | Cơ chế chính |
|---|---|---|
| Một thành phần compute/database host hỏng trong vùng đang chạy | Làm sao ứng dụng tiếp tục kết nối và ghi? | HA/failover trong vùng theo dịch vụ/tier. |
| Báo cáo cuối ngày quét hàng triệu hàng khiến CPU của primary quá cao | Làm sao tách tải đọc khỏi giao dịch ghi? | Read scale-out/read replicas, tối ưu truy vấn và tài nguyên. |
| Cả vùng chính không đáp ứng mục tiêu phục hồi | Dữ liệu và ứng dụng chuyển sang vùng dự phòng thế nào? | Geo-replication/geo-readable secondary, backups/restore và DR runbook. |
| Lập trình viên chạy nhầm `DELETE FROM Orders` không có điều kiện | Làm sao quay lại dữ liệu trước thao tác xóa? | Backup, point-in-time restore, kiểm toán và quy trình phục hồi. |

**Lưu ý quan trọng:** nếu người dùng xóa nhầm dữ liệu, việc xóa có thể được replicate ngay sang standby và read replica. Vì vậy có HA hoặc geo-replication **không thay thế** backup/PITR và biện pháp chống thao tác phá hoại.

## 3. Ranh giới lỗi: instance, zone và region

Trước khi chọn tính năng, phải biết hệ thống đang chống loại sự cố nào.

```text
Azure geography
  ├── Region A (vùng chính)
  │    ├── Availability Zone 1
  │    │      └── Primary database/compute
  │    ├── Availability Zone 2
  │    │      └── HA standby (nếu dịch vụ/tier hỗ trợ)
  │    └── Availability Zone 3
  │
  └── Region B (vùng DR)
       └── Geo-secondary / remote replica
```

- **Instance/host failure**: một thành phần compute hoặc service process bị lỗi.
- **Availability Zone failure**: một zone có vấn đề về nguồn điện/mạng/hạ tầng trong một region, theo ranh giới zone.
- **Region outage**: gián đoạn quy mô vùng, có thể ảnh hưởng nhiều dịch vụ cùng lúc.
- **Data corruption/logical error**: một lệnh ghi/xóa sai hoặc schema migration lỗi; replication có thể lan truyền lỗi.
- **Identity/network/configuration outage**: dữ liệu còn nhưng ứng dụng không kết nối được vì DNS, NSG, token, firewall hoặc cấu hình.

Một database với secondary ở cùng region có thể chịu được một số lỗi node/zone nhưng **không tự bảo vệ khỏi mất toàn region**. Một geo-secondary ở region khác giúp giảm rủi ro vùng nhưng **không tự bảo vệ ứng dụng** nếu API, secrets, Storage hoặc DNS chưa có kế hoạch DR tương ứng.

## 4. Mô hình kiến trúc: primary, HA standby và read replicas

```text
                        Application
                       /           \
                Write traffic   Read-only traffic
                     |                |
                     v                v
             Primary database     Read endpoint
                     |                |
          +----------+-------+        |
          |                  |        v
          v                  v     Read replica R1
   HA standby         Local read replica
   (failover)          (asynchronous*)
          |
          | standby không mặc định phục vụ đọc
          |
          +------------------+
                             |
                      Geo-secondary
                      Region B (DR)

* Cơ chế đồng bộ cụ thể phụ thuộc dịch vụ/tier.
```

Trong thực tế, topology có thể khác:

- Một số **Azure SQL Database** tiers dùng nhiều replicas trong kiến trúc managed HA và có thể cung cấp read scale-out; không phải lúc nào người dùng tạo một resource “standby” riêng.
- **PostgreSQL/MySQL Flexible Server HA standby** là thành phần phục vụ failover, không nên coi như read-only replica tự do nhận truy vấn.
- **Read replica** của PostgreSQL/MySQL được tạo với endpoint riêng và sao chép bất đồng bộ theo kiến trúc hỗ trợ.
- **Geo-secondary** của Azure SQL Database có thể đọc được, nhưng vai trò đọc và cơ chế failover không giống hệt read replica của PostgreSQL/MySQL.

**Tuyệt đối không dùng “secondary” như một từ đủ chính xác** trong runbook. Ghi rõ là *HA standby*, *read replica*, *geo-secondary*, *backup copy* hay *promoted standalone server*.

## 5. Synchronous và asynchronous replication

### Sao chép đồng bộ (synchronous)

Trong cơ chế synchronous replication, commit có thể liên quan tới việc ghi nhận dữ liệu ở thành phần dự phòng theo mô hình của dịch vụ. Điều này giúp giảm rủi ro mất dữ liệu cho phạm vi lỗi được thiết kế, nhưng phải đánh đổi thêm overhead/latency và phụ thuộc đường truyền giữa các thành phần.

```text
Application
    |
    v
Primary ── replicate/ack theo cơ chế sync ──> Standby
    |
    +── commit acknowledged theo chính sách
```

Không suy diễn tất cả HA deployments bảo đảm **zero data loss trong mọi sự cố**, hoặc client không bao giờ nhận lỗi trong failover. Hợp đồng commit, durability, acknowledgment và RPO phải đọc theo dịch vụ và cấu hình cụ thể.

### Sao chép bất đồng bộ (asynchronous)

Primary có thể acknowledge một giao dịch trước khi replica nhận và áp dụng giao dịch đó.

```text
T0: Primary commit Order 1042
T1: API nhận kết quả success
T2: Replication stream gửi thay đổi
T3: Replica nhận/apply Order 1042
```

Giữa T1 và T3 tồn tại **replication lag**. Nếu primary hỏng ở T2, một số giao dịch đã xác nhận với ứng dụng có thể chưa tới replica. Khi promote/failover sang bản sao chậm, có nguy cơ mất những giao dịch đó.

### So sánh

| Thuộc tính | Synchronous | Asynchronous |
|---|---|---|
| Commit latency | Có thể cao hơn vì ràng buộc acknowledgment của replica. | Ít phụ thuộc việc replica đã apply ở thời điểm commit. |
| Đọc trên replica | Phụ thuộc loại replica; synchronous standby không mặc định đọc được. | Read replica thường đọc được, có thể chậm. |
| Rủi ro dữ liệu chưa sao chép khi primary hỏng | Thường thấp hơn trong phạm vi bảo đảm. | Có nguy cơ mất phần dữ liệu chưa replicate. |
| Phù hợp khoảng cách xa | Thường khó hơn vì latency cao. | Thường phù hợp geo-replication. |
| Hệ quả khi replica chậm | Có thể ảnh hưởng commit/availability theo thiết kế. | Lag tăng, read stale; primary vẫn có thể tiếp tục ghi. |

## 6. RPO, RTO và mục tiêu độ sẵn sàng

Hai chỉ số chính:

- **Recovery Point Objective (RPO)**: lượng dữ liệu tối đa doanh nghiệp có thể chấp nhận mất khi khôi phục, đo bằng khoảng cách thời gian hoặc số giao dịch chưa có ở điểm khôi phục.
- **Recovery Time Objective (RTO)**: thời gian tối đa doanh nghiệp chấp nhận để khôi phục khả năng phục vụ sau sự cố.

Ví dụ: RPO 5 phút, RTO 30 phút nghĩa là công ty chấp nhận mất tối đa khoảng 5 phút dữ liệu theo phép đo phù hợp và cần khôi phục dịch vụ trong 30 phút. Đây là **mục tiêu nghiệp vụ**, không phải cam kết rằng bất kỳ replica nào cũng đạt được.

### Bảng yêu cầu

| Workload | RPO mục tiêu | RTO mục tiêu | Hướng thiết kế |
|---|---:|---:|---|
| Đơn hàng đã thanh toán | Rất thấp | Ngắn | HA, DR có giám sát lag, outbox/reconciliation, backup và thử chuyển vùng. |
| Dashboard doanh số gần thực | Vài phút | Vài chục phút | Read replicas, lag budget, cache/refresh. |
| Báo cáo phân tích hằng ngày | Hàng giờ | Hàng giờ | Replicas hoặc ETL sang hệ thống phân tích; backup và khả năng chạy lại. |
| Dữ liệu thử nghiệm | Cao hơn | Cao hơn | SKU tiết kiệm, backup theo chính sách và quy trình tái tạo. |

### Availability không bằng durability

Một database có thể không truy cập được 10 phút nhưng không mất dữ liệu — **RTO bị ảnh hưởng, RPO có thể gần 0**. Ngược lại, một hệ thống chuyển sang vùng DR sau 2 phút nhưng mất 3 phút giao dịch chưa replicate — **RTO tốt hơn nhưng RPO tệ hơn**.

### Tính downtime minh họa

Với mục tiêu availability 99,9% trên 30 ngày:

```text
30 ngày × 24 giờ × 60 phút = 43.200 phút
0,1% × 43.200 = 43,2 phút không sẵn sàng
```

Đây chỉ là tính toán minh họa theo khoảng 30 ngày; **không phải SLA của Azure Database tier nào**. SLA tính theo điều kiện, phạm vi và exclusions do nhà cung cấp công bố. Cần xác định SLO end-to-end của ứng dụng, không chỉ uptime database.

## 7. High availability trong một region

HA thường dùng cơ chế failover để giữ logical database service hoạt động khi một thành phần hỏng. Các lựa chọn bao gồm:

- Replica/standby trong cùng Availability Zone hoặc các zones khác nhau.
- Dữ liệu/compute có kiến trúc dự phòng theo tier của dịch vụ.
- Health detection và điều phối failover của nền tảng.
- Endpoint ổn định hoặc cơ chế reroute theo dịch vụ.
- Client retry/reconnect khi connection cũ bị đóng.

### Những gì HA không tự làm

1. Không bảo đảm **zero downtime**: connection có thể bị reset, transaction đang mở có thể fail.
2. Không tự tạo **read scaling** nếu standby không phục vụ đọc.
3. Không thay thế **geo-DR** khi lỗi toàn vùng.
4. Không sửa được lệnh SQL sai, lỗi schema migration hoặc ứng dụng dùng sai database.
5. Không tự phục hồi API, queue, Storage hay identity đang bị lỗi.
6. Không thay thế kế hoạch backup và thực hành restore.

### HA cùng zone so với zone-redundant

**Same-zone HA** có thể bảo vệ trước một số lỗi instance/host trong cùng zone, nhưng cả primary và standby có thể cùng bị ảnh hưởng khi zone đó gián đoạn.

**Zone-redundant HA** đặt thành phần dự phòng ở zone khác khi dịch vụ và region hỗ trợ, giảm rủi ro một zone đơn lẻ. Đánh giá thêm:

- Region có các Availability Zones và sản phẩm có hỗ trợ ở SKU đó?
- Cơ chế storage/replication có đáp ứng yêu cầu durability và failover?
- Application tier cũng có nhiều replicas/zone?
- Network route, private endpoints, firewall và dependency có chống zone failure?
- Chi phí và latency phát sinh?

**Chọn zone-redundant không tự làm cả ứng dụng zone-redundant.** Một API chỉ chạy trên một VM ở zone 1 vẫn có thể outage dù database có standby ở zone 2.

## 8. Azure SQL Database: HA managed và tier ảnh hưởng gì?

**Azure SQL Database** là dịch vụ SQL managed. HA là một phần kiến trúc dịch vụ; cách triển khai replica/compute và khả năng zone redundancy phụ thuộc service tier/hardware/region.

Những nhóm lựa chọn thường gặp:

- **General Purpose**: cân bằng chi phí/hiệu năng cho workload phổ biến; kiến trúc compute/storage managed với failover theo thiết kế tier.
- **Business Critical/Premium**: phù hợp workload yêu cầu latency và throughput I/O cao hơn; kiến trúc replica có thể hỗ trợ **read scale-out**.
- **Hyperscale**: kiến trúc tách compute/storage phục vụ quy mô dữ liệu lớn; có mô hình compute replicas/read replicas theo khả năng cấu hình.
- **Serverless** trong các cấu hình hỗ trợ: thêm yếu tố auto-scaling/auto-pause và cold start, không nên đồng nhất với HA của provisioned tiers.
- **Zone redundancy**: chỉ có ở những tier/region/hardware/option hỗ trợ; cần kiểm tra trạng thái của database thật.

Không mặc định mọi Azure SQL Database có cùng số replica HA, cùng RTO hoặc mọi region đều hỗ trợ zone redundancy.

### HA có tự chuyển endpoint không?

Ứng dụng thường kết nối vào **logical server/database endpoint** thay vì địa chỉ VM cụ thể. Azure SQL Database điều phối failover ở lớp managed service. Tuy nhiên:

- Những kết nối SQL/TCP đang tồn tại có thể bị ngắt.
- Transaction chưa commit có thể bị rollback theo semantics SQL.
- Connection pool có thể giữ các connections cũ/không hợp lệ.
- Ứng dụng phải có retry cho **transient faults**.
- Thiết kế giao dịch/ghi phải có idempotency khi retry một thao tác không rõ kết quả.

**Không hard-code IP của SQL service hoặc primary replica.** Dùng FQDN và connection configuration của dịch vụ.

## 9. PostgreSQL Flexible Server: HA standby

**Azure Database for PostgreSQL Flexible Server** hỗ trợ cấu hình HA trong các điều kiện/tier/region được sản phẩm cho phép, với những mô hình cùng zone hoặc khác zone. Nền tảng có thể điều phối chuyển vai trò giữa primary và standby khi thành phần primary gặp lỗi.

```text
Application
     |
     v
PostgreSQL Flexible Server endpoint
     |
     +-- Primary (read/write) ── HA replication ──> Standby
                                                  (failover target)
```

Điểm cần nhớ:

- **HA standby phục vụ mục tiêu failover**, không phải một read replica có endpoint độc lập để offload các truy vấn đọc.
- HA sử dụng cơ chế sao chép/commit theo tính năng sản phẩm, không nên áp dụng chi tiết của Azure SQL Database sang PostgreSQL.
- Có thể có failover do maintenance, node issue hoặc điều kiện nền tảng xác định.
- Client connections có thể bị ngắt và cần reconnect/retry.
- Transaction đang mở cần được xử lý theo ứng dụng.
- Zone-redundant HA yêu cầu region/zone/SKU/capacity phù hợp.

### Khi không đủ điều kiện zone-redundant

Nếu một combination region/tier/node size không hỗ trợ zone-redundant HA hoặc thiếu capacity, không nên giả vờ môi trường có chống zone outage. Phải ghi trong tài liệu kiến trúc rằng phạm vi bảo vệ thực tế chỉ là single-zone/same-zone/standalone, và đánh giá lựa chọn khác hoặc DR.

### HA không phải cross-region DR

Primary và standby của HA là cơ chế trong cùng region theo mô hình được hỗ trợ. Muốn có hướng phục hồi khi region lỗi, đánh giá **cross-region replica** hoặc **geo-redundant backups/restore** tùy khả năng và mục tiêu RPO/RTO.

## 10. MySQL Flexible Server: HA standby

**Azure Database for MySQL Flexible Server** cũng có mô hình managed HA theo những cấu hình được hỗ trợ, gồm standby và failover để giảm downtime.

```text
Orders API → MySQL Flexible Server endpoint
                         |
                  Primary read/write
                         |
                  HA standby (same-zone /
                  zone-redundant nếu hỗ trợ)
```

Các nguyên tắc thiết kế:

1. Chọn HA mode phù hợp với khả năng chịu lỗi host hay zone.
2. Kiểm tra tier, storage, region, version và hạn mức hỗ trợ.
3. Không coi standby là một endpoint phục vụ SELECT độc lập.
4. Kiểm thử retry và transaction rollback khi failover.
5. Theo dõi failover events, query latency, CPU, IO và connections.
6. Nếu cần offload report queries, tạo **read replica** theo tính năng hỗ trợ.
7. Nếu cần bảo vệ khỏi region outage, chuẩn bị **DR strategy** riêng.

Không chuyển các tham số cấu hình PostgreSQL sang MySQL chỉ vì cả hai đều gọi là Flexible Server: cơ chế replication, log, lệnh SQL và hạn mức khác nhau.

## 11. Read replica là gì và dùng cho việc gì?

**Read replica** là bản sao nhận những thay đổi dữ liệu từ primary và phục vụ các truy vấn đọc theo khả năng của sản phẩm. Phần lớn read replicas của database services được tạo để **tách tải đọc** và dùng replication bất đồng bộ.

```text
                         +---------------------+
                         | Primary             |
                         | writes + critical   |
                         | fresh reads         |
                         +----------+----------+
                                    |
                      async replication (lag)
                           /                    \
                          v                      v
               Read replica A             Read replica B
               BI dashboards              Search/report API
```

### Khi phù hợp

- Báo cáo tổng hợp nặng ít yêu cầu dữ liệu tức thì.
- Dashboard gần real time cho phép trễ vài giây/phút.
- API tìm kiếm/lọc dữ liệu đọc nhiều, nếu truy vấn đáp ứng giới hạn read-only.
- Batch/export cần tách tài nguyên khỏi primary.
- Tải đọc tăng theo thời gian nhưng write throughput chưa là bottleneck.

### Khi không phù hợp

- Nghiệp vụ ngay sau ghi phải đọc thấy giá trị mới nhất (read-your-writes) mà không có cơ chế consistency.
- Truy vấn đọc phụ thuộc state thay đổi tức thì như kiểm tra số dư ngay sau giao dịch.
- Workload cần nhiều writes phân tán: read replica không phải multi-master.
- Báo cáo gây lock/CPU cao nhưng bản chất cần **một data warehouse/OLAP** khác thay vì scale SQL replica vô hạn.
- Dùng replica như bản backup duy nhất khi lỗi logic có thể nhân bản.

## 12. Replication lag và dữ liệu đọc bị trễ

Vì sao read replica có thể trả dữ liệu cũ?

```text
T0  Primary: UPDATE Orders SET status='Paid' WHERE id=1042
T1  Transaction COMMIT trên primary
T2  Client GET /orders/1042 → đọc từ replica
T3  Replica mới apply thay đổi Paid
```

Nếu GET xảy ra ở T2 trước khi replica apply thay đổi, client có thể vẫn thấy `Pending`. Đây là **stale read**, không nhất thiết là lỗi kết nối hay lỗi SQL.

### Nguyên nhân lag tăng

- Primary tạo WAL/binlog/transaction log với tốc độ lớn.
- Network/region latency hoặc tắc nghẽn giữa primary và replica.
- Replica CPU, I/O hoặc memory không đủ để replay thay đổi.
- Long-running queries/DDL, locks hoặc yếu tố database engine cụ thể.
- Storage/replication subsystem quá tải.
- Replay bị tạm dừng do maintenance hoặc lỗi.
- Những thay đổi như bulk update/index operation tạo nhiều dữ liệu.

Không dùng một ngưỡng lag chung cho mọi ứng dụng. Đặt **lag budget** theo nghiệp vụ.

| Loại truy vấn | Độ mới dữ liệu cần thiết | Hướng định tuyến |
|---|---|---|
| Thanh toán vừa xác nhận | Ngay sau commit theo consistency contract. | Primary. |
| Xem trạng thái đơn ngay sau khi đặt | Read-your-writes quan trọng. | Primary hoặc cơ chế consistency token/đợi replica theo thiết kế. |
| Báo cáo doanh thu theo giờ | Chấp nhận trễ ngắn. | Read replica. |
| Dashboard xu hướng ngày | Chấp nhận trễ vài phút khi phù hợp. | Read replica/analytics store. |
| Đối soát tài chính cuối kỳ | Cần snapshot/mốc nhất quán, không chỉ dữ liệu “gần nhất”. | Primary/snapshot/analytics pipeline được thiết kế. |

## 13. SQL Database read scale-out và application intent

Một số Azure SQL Database tiers như **Premium/Business Critical** và cấu hình **Hyperscale** hỗ trợ read scale-out theo kiến trúc/tính năng của tier.

Ứng dụng có thể định hướng read-only workload bằng **connection string/ApplicationIntent=ReadOnly** tới endpoint phù hợp khi sản phẩm hỗ trợ. Điều quan trọng:

- **ApplicationIntent=ReadOnly** là tín hiệu cho định tuyến/read-only trong cấu hình tương ứng, không phải quy tắc bảo mật thay thế database permissions.
- Không mặc định tùy chọn này hoạt động với mọi tier hay tạo reader replica mới.
- Các replica có thể có replication lag; xem yêu cầu consistency trước khi chuyển mọi SELECT.
- Report queries có thể tiêu thụ tài nguyên đáng kể ngay cả trên read replica.
- Với geo-secondary, endpoint đọc và failover group listener có cơ chế riêng; kiểm tra read-only listener khi dùng failover group.
- Read scale-out không đồng nghĩa dữ liệu đã được replicate sang region khác.

### Ví dụ connection string khái niệm

```text
Server=tcp:<logical-server>.database.windows.net,1433;
Database=ordersdb;
Encrypt=True;
TrustServerCertificate=False;
ApplicationIntent=ReadOnly;
...
```

Đây là **đoạn trích để giải thích tùy chọn**, không phải credential đầy đủ. Không chèn password thật. Connection vẫn phải dùng endpoint/tier hỗ trợ read routing và phương thức authentication được phê duyệt.

### Vai trò đọc/ghi của ứng dụng

Nên có hai logical database clients:

```text
OrderCommandRepository ─── primary/write endpoint
OrderQueryRepository   ─── reader endpoint (tolerates lag)
```

Đừng dùng một connection pool với mọi truy vấn SELECT và kỳ vọng tự phân loại chính xác transaction nào được phép đọc stale.

## 14. PostgreSQL Flexible Server: read replica

PostgreSQL Flexible Server hỗ trợ **read replicas** theo điều kiện của dịch vụ. Các read replicas có thể được tạo ở cùng region hoặc khác region trong những cấu hình/region được hỗ trợ; phạm vi tính năng, private networking và promotion cần xác minh trước triển khai.

Ví dụ:

```text
PostgreSQL Primary: pg-orders-prod
      |
      | asynchronous replication
      +------------------------+
      |                        |
      v                        v
pg-orders-read-a       pg-orders-read-b
reporting workload     analytics workload
```

### Khác HA standby

| Tiêu chí | HA standby | Read replica |
|---|---|---|
| Mục tiêu | Chuyển vai trò khi primary lỗi. | Scale reads, có thể hỗ trợ DR tùy topology. |
| Endpoint đọc riêng | Không mặc định. | Có endpoint riêng cho replica. |
| Nhận write từ app | Không khi đang standby. | Không; replica ở read-only mode khi là replica. |
| Cơ chế sao chép | Theo HA implementation. | Thường asynchronous. |
| Promotion | HA failover do nền tảng/operation phù hợp. | Có quy trình **promote replica** thành standalone primary/server tùy tính năng. |
| Hệ quả | Endpoint HA/primary theo cơ chế dịch vụ. | Sau promote cần điều chỉnh endpoint/topology; không giả định tự đảo vai trò. |

### Điều cần kiểm tra

- Replica có **read-only** và không chấp nhận INSERT/UPDATE/DDL ghi dữ liệu trên replica.
- Kích thước compute/storage replica và replication lag.
- Quyền/roles, extensions và cấu hình Postgres tương thích.
- Network/FQDN/dns/private access cho từng replica.
- Cách ứng dụng phát hiện replica lỗi và chuyển sang replica khác.
- Số replicas, tier/region và quota.
- Khả năng promotion/cross-region theo version/region.
- Chi phí của **mỗi replica server** và traffic sao chép.

**Không coi read replica là secondary tự động được nâng cấp cùng HA standby.** Nếu cần DR tự động hoặc RTO chặt, phải đánh giá giải pháp failover/orchestration của service và workflow ứng dụng.

## 15. MySQL Flexible Server: read replica

MySQL Flexible Server cung cấp read replica trong phạm vi tính năng được hỗ trợ. Các replicas nhận thay đổi từ primary bằng cơ chế replication của hệ MySQL/Azure và cho phép read workload, thường có **replication lag**.

```text
MySQL Primary: mysql-orders-prod
      |
      +-- Read replica: mysql-orders-read
      |
      +-- (optional remote replica when supported)
```

Lưu ý:

1. Replica có **server endpoint** riêng, không phải cùng endpoint write của primary.
2. Tính năng cross-region read replicas/region pairing có điều kiện; không giả định mọi cặp vùng hợp lệ.
3. Một read replica chậm có thể trả giá trị stale.
4. Query nặng trên replica có thể làm replica apply replication chậm hơn.
5. Chỉ chạy writes vào primary; dùng read-only connection policy và database permissions phù hợp.
6. Promotion thành server độc lập (nếu được hỗ trợ) là **thay đổi topology có tác động**.
7. Một MySQL replica đơn lẻ không tự cung cấp failback đầy đủ hoặc auto-redirect tất cả clients sau promotion.

Nếu ứng dụng đang dùng **MySQL transaction consistency** cụ thể, cần kiểm tra behavior khi đọc từ replica trong bối cảnh isolation, transaction commit và replication của phiên bản MySQL đang chạy.

## 16. Read routing, read-your-writes và transaction boundaries

Một hệ thống CQRS đơn giản:

```text
Orders API
   |
   +-- POST /orders --------> Primary
   |
   +-- POST /orders/pay ----> Primary
   |
   +-- GET /orders/{id} ----> Read replica?
                                   |
                              Có thể stale
```

Ngay sau POST, client thường chờ GET trả trạng thái vừa ghi. Nếu GET đi read replica và lag vài giây, trải nghiệm có thể bị sai.

### Những cách kiểm soát

- **Primary-only reads** cho luồng cần tính nhất quán ngay sau ghi.
- **Read-after-write stickiness**: trong một cửa sổ hoặc sau một write token, tạm route truy vấn về primary.
- **Consistency token/LSN/GTID** theo engine và khả năng hỗ trợ để biết replica đã bắt kịp mốc ghi, nếu tổ chức triển khai được cách đo an toàn.
- **Accept eventual consistency** cho dashboard/reporting và thể hiện timestamp dữ liệu.
- **Cache invalidation** có chủ đích, tránh cache trả dữ liệu cũ lâu hơn replica.
- **Clear transaction boundary**: không phân tách các thao tác trong cùng transaction nghiệp vụ sang primary/replica tùy tiện.

### Ví dụ sai

1. Ghi `Order.status = Paid` ở primary.
2. Ngay lập tức đọc replica để xác minh `Paid`.
3. Replica chưa apply, trả `Pending`.
4. App kết luận payment thất bại và charge lại.

Đây không phải lỗi HA mà là **lỗi thiết kế consistency**. Phải xác minh giao dịch từ nguồn dữ liệu có đủ consistency, kết hợp idempotency để ngăn charge trùng.

## 17. Connection pooling khi có nhiều endpoints

Khi một ứng dụng có primary và read replicas, phải quản lý connection pools độc lập, hoặc định tuyến qua proxy/router được hỗ trợ.

| Pool | Endpoint | Vai trò | Lưu ý |
|---|---|---|---|
| Write pool | Primary/write listener | Giao dịch ghi và đọc cần consistency mạnh. | Retry transient fault, timeout, không cache DNS/IP vĩnh viễn. |
| Read pool A | Local read replica A | Báo cáo và truy vấn chấp nhận lag. | Throttle và kiểm tra replica lag. |
| Read pool B | Local read replica B | Chia tải đọc khi được hỗ trợ. | Health checks và routing đúng. |
| DR pool | Geo-secondary/remote promoted endpoint | Khi chuyển vùng được phê duyệt. | Khác quyền/network, kiểm tra write readiness. |

### Những lỗi thường gặp

- Connection pool giữ kết nối cũ sau failover.
- DNS cache quá lâu hoặc hard-coded IP.
- Retry mọi transaction vô hạn khi database thực sự unavailable.
- Report workload mở quá nhiều connections gây cạn connection limits.
- App gửi INSERT tới read-only replica vì connection string bị hoán đổi.
- Đổi endpoint nhưng secrets/firewall hoặc certificate verification không tương thích.
- Trong multi-tenant app, một tenant query report quá nặng khiến read replica quá tải.

**Cần kiểm tra client/driver hỗ trợ reconnect và DNS re-resolution như thế nào**. Một DNS alias không bảo đảm app tự hồi phục nếu connection pool không bỏ các connections chết.

## 18. Geo-replication: chống sự cố quy mô vùng

**Geo-replication** sao chép dữ liệu tới cơ sở dữ liệu ở region khác để phục vụ mục tiêu DR hoặc đọc gần người dùng. Nhiều giải pháp managed database dùng **asynchronous cross-region replication** nhằm tránh latency cao do khoảng cách địa lý.

```text
                      Region A (primary)
                 +------------------------+
                 | API A                  |
                 | Primary DB (write)     |
                 +-----------+------------+
                             |
                 async geo-replication
                             |
                             v
                      Region B (secondary)
                 +------------------------+
                 | API B (standby/DR)     |
                 | Geo-secondary (read)   |
                 +------------------------+
```

Lưu ý:

- Geo-secondary có thể **behind primary** vài giây hoặc lâu hơn khi có sự cố.
- RPO thực tế phụ thuộc lag ngay trước failover, không chỉ mục tiêu công bố.
- Region B phải có compute, secrets, networking, DNS, storage, dependencies và quyền tương ứng để ứng dụng hoạt động.
- Cần phân biệt **planned switchover/failover** (có thể đồng bộ/check trước) và **forced/unplanned failover** (rủi ro mất dữ liệu khi primary không còn).
- Failback sau khi Region A phục hồi có thể yêu cầu **tái thiết lập replication và đối soát**.
- Data residency/compliance có thể không cho replicate sang một region bất kỳ.

Geo-replication giúp ứng dụng có dữ liệu ở nơi khác nhưng **không tự chuyển HTTP traffic** của mọi client đến API B. Cần điều phối routing ngoài database.

## 19. Azure SQL Database active geo-replication

**Active geo-replication** trong Azure SQL Database cho phép tạo một hoặc nhiều **readable geo-secondary databases** theo giới hạn và điều kiện sản phẩm, thường với replication bất đồng bộ.

```text
Azure SQL Database (Region A)
  logical server: sql-orders-a
  database: ordersdb (read/write)
             |
             | asynchronous geo-replication
             v
Azure SQL Database (Region B)
  logical server: sql-orders-b
  database: ordersdb (readable secondary)
```

### Khi nào dùng?

- Có secondary database tại region khác cho disaster recovery.
- Một số read workloads cần chạy gần người dùng ở region B.
- Cần chủ động failover giữa các vùng theo runbook khi primary không khả dụng.
- Muốn tách logical server/network/security tại region DR theo mô hình SQL Database.

### Điều cần nhớ

1. **Geo-secondary thường read-only** khi còn là secondary.
2. Replication bất đồng bộ nên không bảo đảm mọi commit mới nhất đã đến region B trước lỗi.
3. Tạo geo-secondary có chi phí compute/storage và có thể có data transfer.
4. Server-level settings, authentication, firewall/Entra networking, logins/roles và các đối tượng ngoài database phải được đánh giá riêng — **không giả định mọi cấu hình Azure resource được nhân bản tự động**.
5. Khi failover, application connections và routing cần được kiểm tra hoặc đổi theo thiết kế.
6. Không coi geo-secondary là bản lưu bất biến chống thao tác xóa sai.

### Active geo-replication khác read scale-out tại chỗ

- **Read scale-out** có thể dùng replicas managed trong cùng region/tier.
- **Active geo-replication** hướng đến **secondary khác vùng** và phục hồi vùng.
- Có thể dùng geo-secondary cho read workloads, nhưng phải xem ảnh hưởng lag, latency cross-region và khả năng takeover.

## 20. Azure SQL failover groups và listeners

Với Azure SQL Database và một số cấu hình **Azure SQL Managed Instance** được hỗ trợ, **failover groups** cung cấp nhóm database/instance có khả năng phục vụ kế hoạch geo-failover cùng các **listener endpoints**.

Mô hình khái niệm:

```text
                 Application
                 /         \
        Write connection   Read connection
               |               |
               v               v
        RW listener       RO listener
               |               |
               v               v
       Primary region     Geo-secondary region
       SQL database(s)    SQL database(s)
                \             /
                  Failover group
```

Tùy dịch vụ và cấu hình, failover group có thể có:

- **Read-write listener**: endpoint giúp client hướng tới vùng đang giữ vai trò primary.
- **Read-only listener**: endpoint cho read-only routing khi được hỗ trợ.
- Cấu hình failover policy/automatic or manual failover theo khả năng sản phẩm.
- Tập databases được quản lý như một nhóm failover theo semantics hỗ trợ.

### Lợi ích và giới hạn

- Ứng dụng không cần hard-code riêng logical server A/B trong một số kịch bản.
- Một listener FQDN ổn định có thể giảm thay đổi connection string khi chuyển vùng.
- DNS caching/connection pool vẫn có thể làm client tiếp tục thử endpoint cũ; **phải có reconnect/retry**.
- Failover group **không làm replication đồng bộ xuyên vùng**; vẫn có RPO risk do async.
- Failover policy, grace period và trạng thái secondary phải được kiểm tra; automatic failover không có nghĩa luôn zero data loss hoặc instant.
- Không suy luận listener sẽ tự route **mọi SELECT** sang read replica; read-only intent và endpoint thực tế cần được cấu hình đúng.

### Database vs Managed Instance

Azure SQL Database active geo-replication và SQL Managed Instance failover group **không cùng mô hình tài nguyên**. Với Managed Instance, cần xem failover group/link/network requirements/instance-level settings của sản phẩm cụ thể; không dùng nguyên command cho SQL Database khi quản trị MI.

## 21. Cross-region read replicas của PostgreSQL/MySQL: DR có điều kiện

Với **PostgreSQL Flexible Server** và **MySQL Flexible Server**, read replicas có thể giúp triển khai bản sao khác vùng **nếu version/tier/region/feature đang sử dụng hỗ trợ**.

```text
Region A                         Region B
+--------------------+           +--------------------------+
| PostgreSQL/MySQL   |  async    | Remote read replica      |
| primary (read/write)|--------->| (read-only trước promote)|
+--------------------+           +--------------------------+
                                              |
                                              | promotion khi DR được phép
                                              v
                                   Standalone primary / endpoint mới
```

### Promotion không phải automatic HA failover

Một read replica được **promote** theo cơ chế sản phẩm sẽ không còn là replica đọc theo topology cũ và có thể trở thành standalone read/write server. Khi đó phải:

1. Xác minh primary cũ thực sự không còn được phép nhận writes để tránh **split-brain**.
2. Kiểm tra replica đã nhận tới đâu, replication lag và khả năng mất dữ liệu.
3. Phê duyệt promote theo mức độ sự cố.
4. Cập nhật route/endpoint/connection strings hoặc virtual endpoints nếu sản phẩm và cấu hình hỗ trợ.
5. Xác nhận network/role/TLS/secrets ở region B.
6. Chạy smoke tests và đối soát số giao dịch.
7. Lập kế hoạch **tái đồng bộ/failback**; không giả định replication tự đảo chiều.

### MySQL và PostgreSQL khác nhau

Hạn mức, phương thức cross-region, DDL replication behavior, phiên bản engine, virtual endpoints và những bước promote có thể khác. Chỉ dùng tài liệu/CLI đúng **engine và deployment mode**. Tránh áp dụng trực tiếp lệnh `pg_ctl promote` hoặc MySQL replication commands trên một managed Flexible Server nếu dịch vụ yêu cầu API quản lý riêng.

## 22. Backup, geo-redundant backup và PITR không phải replica

Backup tồn tại để phục hồi dữ liệu về một trạng thái lưu trữ, còn replication duy trì bản sao gần với primary hơn để phục vụ HA/read/DR.

| Cơ chế | Bảo vệ chính | Ưu điểm | Hạn chế |
|---|---|---|---|
| HA standby | Lỗi node/zone trong phạm vi thiết kế. | Failover tương đối nhanh theo sản phẩm. | Không phải bản backup độc lập; thường không phục vụ đọc. |
| Local read replica | Tăng tải đọc, tách report. | Offload reads, scale consumers. | Có lag, không phải rollback dữ liệu cũ. |
| Geo-secondary/read replica | Lỗi vùng, read locality khi hỗ trợ. | Dữ liệu sẵn ở vùng DR. | Async lag, promotion/failover risk. |
| Automated backup + PITR | Xóa nhầm hoặc lỗi logic trong khoảng backup retention. | Khôi phục về thời điểm trước lỗi theo khả năng dịch vụ. | Restore có thời gian và có thể tạo server/database mới. |
| Geo-redundant backup | Phục hồi từ backup ở region khác theo lựa chọn hỗ trợ. | Hữu ích khi region chính mất lâu. | Không phải hot secondary; RTO thường khác failover sang replica. |
| Export/archive/immutable backups | Lưu trữ hoặc khôi phục các mốc dữ liệu riêng. | Có thể hỗ trợ compliance/forensics. | Cần quản trị lifecycle, security, kiểm thử restore. |

**PITR (point-in-time restore)** cần backup/logs đủ thời hạn và tính năng của database, không tự sinh một database “đã rollback” ngay trong primary mà không ảnh hưởng workload. Nhiều dịch vụ tạo **new database/server** từ restore, sau đó ứng dụng phải chuyển đổi theo quy trình.

### Ví dụ xóa nhầm

09:00: database có 10.000 đơn.  
09:05: người vận hành chạy một DELETE sai.  
09:05–09:06: lỗi được replicate tới HA standby và geo-secondary.  
09:10: ứng dụng phát hiện thiếu đơn.

**Không** promote geo-secondary một cách mù quáng: nó có thể đã nhận DELETE. Hướng đúng là xác định recovery point, PITR/backup, khôi phục có kiểm soát, đối soát phần writes từ 09:00 đến khi lỗi và thực hiện data repair.

## 23. Bảng chọn kiến trúc theo mục tiêu

| Yêu cầu | Azure SQL Database | PostgreSQL Flexible Server | MySQL Flexible Server |
|---|---|---|---|
| Chịu lỗi instance trong region | Built-in HA theo service tier. | HA primary/standby khi cấu hình hỗ trợ. | HA primary/standby khi cấu hình hỗ trợ. |
| Chịu lỗi Availability Zone | Zone-redundant option theo tier/region. | Zone-redundant HA theo hỗ trợ. | Zone-redundant HA theo hỗ trợ. |
| Offload truy vấn đọc | Read scale-out/replicas theo tier, application intent. | Tạo read replicas. | Tạo read replicas. |
| Có bản sao đọc ở region khác | Active geo-replication/secondary. | Cross-region read replica khi hỗ trợ. | Cross-region read replica khi hỗ trợ. |
| Failover cross-region | Active geo-replication/failover group theo tính năng. | Promotion/DR orchestration theo tính năng. | Promotion/DR orchestration theo tính năng. |
| Read-write listener khi đổi vùng | Failover group listener khi cấu hình hỗ trợ. | Endpoint/virtual endpoint hoặc routing theo tính năng. | Endpoint/virtual endpoint hoặc routing theo tính năng. |
| Khôi phục xóa nhầm | Automated backups/PITR. | Backup/PITR. | Backup/PITR. |

**Không đánh dấu “Có” là một cam kết chung cho mọi SKU/region**. Trong bản thiết kế cuối cùng, phải ghi chính xác deployment mode, pricing tier, zone choice, engine version, region pair và các tính năng đang được bật.

## 24. DNS, endpoints và định tuyến sau failover

Một thiết kế DR thành công phụ thuộc việc client có thể **ngừng dùng endpoint cũ** và kết nối tới primary mới.

```text
Before failover
  app write → db-write.example.internal → Region A primary
  app read  → db-read.example.internal  → read replica

After region DR failover
  app write → db-write.example.internal → Region B promoted primary
  app read  → db-read.example.internal  → suitable reader
```

Sơ đồ dùng **logical DNS aliases** để minh họa; không phải mọi Azure database service cho phép tùy ý dùng CNAME thay FQDN mặc định mà vẫn hợp lệ TLS/hostname verification. Phải kiểm tra:

- Database driver/connection string có hỗ trợ alias/redirect/listener theo sản phẩm?
- TLS certificate hostname validation có còn đúng?
- DNS TTL và cache phía client/JVM/.NET/OS/connection pool.
- Private DNS zone link và private endpoint ở vùng DR.
- Firewall/NSG/UDR/Azure Firewall route.
- Microsoft Entra authentication, database users và secrets/credential.
- TCP connection timeouts, retry budget và connection pool refresh.
- Client có thể phân giải/write tới đúng primary sau khi role thay đổi.

**Không dùng IP cứng** cho database managed endpoint. Cũng không coi TTL thấp là bảo đảm đổi kết nối tức thì: client đang giữ connection có thể không tra DNS lại cho tới khi reconnect.

## 25. Consistency và các giao dịch đang mở khi failover

Failover xảy ra đúng lúc nhiều giao dịch đang chạy:

```text
Client                 Primary              Secondary
  | BEGIN TRANSACTION    |                      |
  | UPDATE Orders        |                      |
  | COMMIT ? ------------|------ replication --->|
  |      connection lost |                      |
  | retry to new primary |                      |
```

Trong tình huống client không nhận được acknowledgment của COMMIT, có hai khả năng: transaction **đã commit** hoặc **chưa commit**. Nếu retry vô điều kiện, có thể tạo double charge/order nếu câu lệnh không idempotent.

### Chiến lược an toàn

1. Mỗi business operation có **requestId/idempotency key** ổn định.
2. Database đặt **unique constraint** cho operation ID.
3. Khi lỗi mạng/failover, kiểm tra trạng thái nghiệp vụ trước khi tạo lại.
4. Retry transient errors với backoff và timeout hữu hạn.
5. Transaction ngắn, tránh giữ lock lâu.
6. Dùng outbox/inbox nếu có message broker liên quan.
7. Chạy đối soát giao dịch nằm trong **RPO risk window** sau failover.
8. Đánh dấu dữ liệu/đơn hàng chưa xác minh thay vì giả định thành công hoặc thất bại.

**HA không thay thế transactional correctness.** Một chuyển đổi hạ tầng tốt vẫn có thể tạo lỗi nghiệp vụ nếu ứng dụng retry sai.

## 26. Planned failover, forced failover và failback

### Planned failover

Được thực hiện khi primary còn kiểm soát được và hệ thống muốn đổi vai trò có chủ đích, ví dụ bảo trì hoặc DR drill. Tùy sản phẩm, có thể kiểm tra/synchronize dữ liệu trước khi chuyển đổi và giảm nguy cơ mất dữ liệu.

Quy trình:

1. Xác định phạm vi, phê duyệt và thời gian tác động.
2. Kiểm tra secondary health/lag, network và capacity.
3. Tạm giảm/chặn writes ở tầng ứng dụng nếu runbook yêu cầu.
4. Đợi replication bắt kịp trong giới hạn quy trình hỗ trợ.
5. Kích hoạt operation failover/switchover **đúng dịch vụ**.
6. Cập nhật hoặc xác minh listeners/endpoints.
7. Smoke test reads/writes và dữ liệu cuối.
8. Mở lại traffic, theo dõi error rate và latency.

### Forced/unplanned failover

Khi region chính mất kết nối, có thể không biết secondary đã nhận tất cả committed writes. Phải chấp nhận **khả năng mất dữ liệu** và nguy cơ split-brain nếu primary cũ sống lại.

- Có owner chịu trách nhiệm ra quyết định.
- Ghi mức lag đã quan sát được và khoảng uncertainty.
- Chặn hai primary ghi đồng thời.
- Promote/failover chỉ theo cơ chế được dịch vụ hỗ trợ.
- Reroute toàn hệ thống và xác nhận dependency.
- Đối soát transactions/recover missing data từ outbox, logs hoặc nguồn gốc nếu còn.
- Không tự failback khi Region A hoạt động lại.

### Failback

Failback là **một thay đổi topology mới**, không phải chỉ đảo DNS:

1. Kiểm tra primary mới đã hoạt động ổn định.
2. Xác định hướng replication, mốc dữ liệu và khả năng rebuild secondary ở region cũ.
3. Xác minh không còn writes trên primary cũ.
4. Tái tạo/sync theo runbook sản phẩm, tránh ghép hai nhánh dữ liệu đã khác nhau.
5. Planned switchover nếu cần trở lại region ban đầu.
6. Đối soát, rollback plan và cập nhật tài liệu kiến trúc.

## 27. Azure Portal: kiểm tra HA và replicas

### Với Azure SQL Database

1. Mở Portal và xác nhận tenant/subscription/resource group.
2. Chọn **SQL database**, ghi lại database name và logical server.
3. Xem **Compute + storage / Service tier** và tùy chọn **zone redundancy** nếu có.
4. Xem khu vực **Replicas/Geo-replication** hoặc giao diện tương ứng.
5. Nếu có failover group, kiểm tra primary/secondary server, role và listeners.
6. Kiểm tra **Metrics**, Resource health và cấu hình alert.
7. Ghi lại endpoint để ứng dụng kết nối read-write và read-only.

### Với PostgreSQL Flexible Server

1. Mở server chính, xem **High availability** và mode/status.
2. Xem **Read replicas** để xác nhận số replica, source, region và trạng thái.
3. Ghi endpoint từng server, engine version, compute SKU và networking.
4. Xem metrics replication lag/CPU/storage/connection theo dịch vụ.
5. Xác nhận backup retention/geo-redundancy setting nếu có.
6. Chỉ dùng nút **Promote/Failover** trong quy trình đã được phép.

### Với MySQL Flexible Server

1. Mở server, kiểm tra **High availability** và vùng/zone.
2. Kiểm tra **Read replicas** và endpoint.
3. Xem metrics replication lag, CPU, IO, memory, connections.
4. Đánh giá networking/private access của replica.
5. Kiểm tra backup retention, restore options và các alerts.
6. Không xóa replica chậm hoặc promote tự phát chỉ để hết cảnh báo.

**Portal là giao diện quản trị**, không phải bằng chứng duy nhất về consistency. Với failover rehearsal cần thêm phép thử thực tế từ application và đối soát dữ liệu.

## 28. Azure CLI: kiểm tra topology an toàn

Các lệnh dưới đây chủ yếu **chỉ đọc**; không tạo secondary, không promote, không failover. Thay placeholder bằng tài nguyên lab/Production được phê duyệt. Kiểm tra phiên bản CLI/extension phù hợp nếu lệnh hay trường output khác.

### Xác minh subscription/tenant

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table
```

### Azure SQL Database

```bash
az sql db show \
  --resource-group "<RESOURCE_GROUP>" \
  --server "<LOGICAL_SQL_SERVER>" \
  --name "<DATABASE_NAME>" \
  --query "{Name:name,Status:status,Edition:edition,ZoneRedundant:zoneRedundant,Location:location}" \
  --output json

az sql db replica list \
  --resource-group "<RESOURCE_GROUP>" \
  --server "<LOGICAL_SQL_SERVER>" \
  --name "<DATABASE_NAME>" \
  --output table
```

### Azure SQL failover groups

```bash
az sql failover-group list \
  --resource-group "<RESOURCE_GROUP>" \
  --server "<LOGICAL_SQL_SERVER>" \
  --output table
```

Khi đọc output, xác minh primary/partner servers và replication role/status. Không thực thi failover chỉ để xác minh tên group.

### PostgreSQL Flexible Server

```bash
az postgres flexible-server show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<POSTGRES_SERVER>" \
  --output json

az postgres flexible-server replica list \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<POSTGRES_PRIMARY_SERVER>" \
  --output table
```

### MySQL Flexible Server

```bash
az mysql flexible-server show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<MYSQL_SERVER>" \
  --output json

az mysql flexible-server replica list \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<MYSQL_PRIMARY_SERVER>" \
  --output table
```

Một số thuộc tính được hỗ trợ khác nhau tùy API version. Lệnh `show` có thể trả topology/HA properties nhưng **không thay thế phép đo runtime lag**. Nếu CLI báo không hỗ trợ, kiểm tra `az ... --help` và version/extension trong môi trường làm việc thay vì tự đoán parameter.

### Vì sao không đưa lệnh failover một dòng?

Promote, failover, delete replica hoặc thay HA mode là những thao tác **có rủi ro mất dữ liệu hoặc gián đoạn**. Cú pháp, điều kiện tiền đề và thao tác rollback khác theo engine/SKU. Vì vậy bài này tập trung lệnh read-only; thao tác ghi phải theo runbook thực tế và tài liệu sản phẩm tương ứng.

## 29. Ví dụ SQL: đọc đúng nguồn sau ghi

### Transaction ghi vào primary

```sql
-- Chạy trong môi trường thử nghiệm; minh họa về business idempotency.
BEGIN TRANSACTION;

UPDATE Orders
SET Status = 'Paid'
WHERE OrderId = 1042
  AND Status = 'Pending';

-- Cần kiểm tra số dòng bị thay đổi và nghiệp vụ thực tế.
COMMIT TRANSACTION;
```

Đây là cú pháp minh họa theo phong cách T-SQL của SQL Server, không dùng nguyên cho mọi PostgreSQL/MySQL dialect. Trong nghiệp vụ thực, muốn tránh double-charge phải có **idempotency key**, unique constraint và quản lý giao dịch với payment service; chỉ thêm `WHERE Status='Pending'` chưa đủ cho toàn bộ quy trình.

### Đọc từ primary hoặc replica

```sql
SELECT OrderId, Status, UpdatedAt
FROM Orders
WHERE OrderId = 1042;
```

Cùng câu SELECT trên primary có thể trả Paid, nhưng trên async replica có thể trả Pending khi lag. **SQL query không tự biết mình đang nối primary hay replica**. Kiểm tra connection properties và routing trong ứng dụng.

### Đo độ mới dữ liệu

Ứng dụng có thể lưu `UpdatedAtUtc` hoặc version/commit marker để phát hiện dữ liệu quá cũ trong ngữ cảnh báo cáo:

```text
Report generated at 10:05 UTC
Max source UpdatedAtUtc observed = 10:01 UTC
Estimated data freshness lag >= 4 minutes (heuristic)
```

Đây chỉ là **heuristic**: nếu không có bản ghi mới, chênh lệch timestamp không bằng replication lag. Đo replication lag chính xác cần engine/service metrics hoặc replication state phù hợp.

## 30. Các chỉ số phải quan sát

Một cơ sở dữ liệu có HA/replicas mà không có monitoring vẫn có thể không đạt SLO.

| Tín hiệu | Mục tiêu | Hướng xử lý |
|---|---|---|
| **Availability/connection errors** | Phát hiện failover hoặc mất kết nối. | So app errors, database health và network. |
| **Replication lag** | Biết read replica/geo-secondary chậm bao nhiêu. | Đánh giá read freshness và RPO risk. |
| **CPU** | Phát hiện compute bottleneck. | So primary/replica, queries, tier. |
| **Memory/IO/storage latency** | Phát hiện đĩa, buffer hoặc replay nghẽn. | Kiểm tra query plans, workload và tài nguyên. |
| **Storage usage/growth** | Tránh hết quota/dung lượng. | Capacity planning, alerts. |
| **Connections** | Phát hiện pool storms hoặc connection exhaustion. | Điều chỉnh pool/retry, scale. |
| **Deadlocks/lock waits** | Phát hiện transaction contention. | Tối ưu SQL và transaction scope. |
| **Query latency/p95** | Ảnh hưởng thực lên người dùng. | Theo workload, indexes và read routing. |
| **Failover events** | Xác định thời điểm/loại chuyển vai trò. | Correlate với application retries. |
| **Backup status/retention** | Bảo đảm đường PITR còn hiệu lực. | Kiểm tra backup policy và restore drills. |
| **Geo DR readiness** | Secondary sẵn và có capacity/permissions? | Kiểm thử DNS, dependency và replication. |

### Lag chỉ có ý nghĩa nếu xác định nguồn đo

- Azure SQL geo-replication có các trạng thái/metrics độ trễ và replication theo dịch vụ.
- PostgreSQL có các khái niệm WAL replay/receiver và server metrics liên quan.
- MySQL có các metric/trạng thái replication từ engine/service, cách tính khác PostgreSQL.
- **Không dùng cùng một SQL query hoặc cùng tên metric** cho ba dịch vụ.
- Một số metrics có độ trễ cập nhật; cần biết timestamp đo và clock source.

Với RPO mục tiêu 60 giây, nếu chỉ có biểu đồ lag cập nhật mỗi 5 phút, không thể chứng minh RPO ngay tại thời điểm sự cố bằng một hình chụp dashboard.

## 31. Alerts và SLO từ góc nhìn ứng dụng

Các cảnh báo tối thiểu:

1. Database unavailable/connection failures vượt ngưỡng.
2. Replica lag vượt **read freshness budget**.
3. Geo-replica lag vượt **DR RPO risk threshold**.
4. Primary CPU/IO hoặc storage cao liên tục.
5. Replica CPU/IO cao, replication replay không bắt kịp.
6. Failover/switchover event xảy ra ngoài khung bảo trì.
7. Error rate sau failover tăng/connection pools không hồi phục.
8. Backup/restore check thất bại hoặc retention thay đổi ngoài ý muốn.
9. Read-only replica bị gửi writes hoặc read endpoint không còn đúng vai trò.
10. Budget/resource cost tăng bất thường do replica mới.

### Kết hợp metrics và synthetic checks

Một bài synthetic test quan trọng:

- Từ **ứng dụng/VNet thực**, mở connection read-write đến database.
- Chạy một thao tác đọc vô hại, không chứa secrets trong logs.
- Kiểm tra role của endpoint theo phương pháp được engine hỗ trợ.
- Đo latency và response.
- Kiểm tra reader endpoint trả được kết quả với stale tolerance đã định nghĩa.
- Khi failover drill, xác nhận cả **write path** và **read path**.

Không chạy ghi dữ liệu thử trực tiếp trên Production nếu chưa có tài khoản/bảng lab và approval; có thể dùng health checks read-only cộng business tracing.

## 32. Security, network và identity cho primary/replicas

Thêm replica đồng nghĩa thêm tài nguyên/endpoints cần được bảo vệ.

### Danh sách kiểm tra

- **Private access**: VNet integration, private endpoints/delegated subnets theo dịch vụ.
- **DNS**: resolution đúng cho từng server/replica, private DNS zones và links.
- **Firewall/NSG/UDR**: cho phép chỉ các workloads và cổng cần thiết.
- **TLS**: dùng encryption, hostname validation và chứng chỉ tin cậy.
- **Identity**: Microsoft Entra authentication/managed identity khi được database và driver hỗ trợ, hoặc credential management qua Key Vault.
- **DB permissions**: ứng dụng báo cáo chỉ được SELECT phù hợp, không nhận DDL/admin chỉ vì ở replica.
- **Secret rotation**: primary/replica/failover endpoints có cần credentials khác không?
- **Audit**: control-plane changes, login failures, DDL và activity cần thiết.
- **Data residency**: remote region có được phép chứa dữ liệu khách hàng/PII không?
- **Replication encryption**: sử dụng cơ chế bảo mật dữ liệu in transit/at rest được dịch vụ hỗ trợ.
- **Key management**: nếu dùng CMK/TDE/key vault, kiểm tra chìa khóa và quyền ở DR region.

### Rủi ro thường bị quên

Một geo-secondary có thể được tạo thành công nhưng ứng dụng ở Region B không truy cập được vì **private DNS zone chưa link đúng**, thiếu firewall rule hoặc identity không có quyền. **Data plane DR readiness phải kiểm tra từ nơi ứng dụng thực sự chạy**, không chỉ từ Azure Portal.

Không dùng firewall mở toàn Internet để “thử xem replica có hoạt động không” trên Production. Sửa nguyên nhân network đúng phạm vi và thu hồi quyền tạm.

## 33. Tính chi phí của HA, replicas và geo-DR

Chi phí có thể phát sinh từ:

| Thành phần | Tác động chi phí |
|---|---|
| HA/zone redundancy | Compute/standby hoặc tier-specific HA charges theo sản phẩm. |
| Read replica | Compute, storage và I/O của mỗi replica. |
| Geo-secondary | Database resource ở region B, replication/network charges theo trường hợp. |
| Backup/PITR/long-term retention | Dung lượng backup, retention, redundancy, export. |
| DNS/private networking | Private Endpoint, VNet peering, firewall, NAT, egress. |
| Monitoring | Azure Monitor/Log Analytics/alerting. |
| DR-ready application | App instances, load balancer, secrets, cache, queue, Storage ở region B. |
| Exercises | Thời gian failover drills, dữ liệu thử, nhân sự và công phục hồi. |

### So sánh ba lựa chọn cho báo cáo

1. **Không có read replica**: tiết kiệm compute replica nhưng report load làm primary chậm; cần tối ưu SQL/index.
2. **Một local read replica**: tăng chi phí database nhưng tách report load và cải thiện performance của giao dịch ghi.
3. **Một geo-secondary kiêm report**: có thể hỗ trợ DR và đọc từ xa, nhưng latency/lag/network/role có thể không phù hợp mọi report. **Không biến DR secondary thành bottleneck** đến mức mất khả năng failover đúng lúc.

### Công thức suy nghĩ đơn giản

```text
Tổng chi phí hệ thống =
  Database primary
+ HA surcharge/standby nếu có
+ Σ(read replicas)
+ Geo-DR resources
+ Backup/PITR
+ Network/private DNS
+ Monitoring
+ Application DR capacity
+ Vận hành và diễn tập
```

Giá cụ thể thay đổi theo region, SKU, vCore/compute size, storage, uptime và reservations/discounts. Dùng Azure Pricing Calculator và số liệu tải thực tế, không dựa vào giá giả định trong bài.

## 34. Runbook: chuyển vùng khi primary region gián đoạn

**Bối cảnh:** SQL primary ở Region A bị gián đoạn kéo dài. Vùng B có geo-secondary và API dự phòng. Mục tiêu: khôi phục đặt hàng mà không tạo hai primary đồng thời.

### Pha 1 — Xác minh sự cố

1. Ghi incident ID, UTC start time, phạm vi khách hàng bị ảnh hưởng.
2. Kiểm tra Azure Service Health, database health, app error rate, network/DNS.
3. Phân biệt database failure với chỉ một connection/identity issue.
4. Kiểm tra secondary health, lag và những dữ liệu đã đến.
5. Xác định RPO risk và so với mục tiêu đã được phê duyệt.

### Pha 2 — Quyết định DR

1. Incident commander/DB owner xác nhận tiêu chí kích hoạt.
2. Ghi lại **khả năng mất committed writes** chưa replicate nếu failover cưỡng bức.
3. Xác minh Region A không còn được phép nhận writes khi Region B làm primary.
4. Chặn/giới hạn producer workloads để tránh tạo hai nhánh dữ liệu.
5. Kiểm tra API B, Service Bus, secrets, Storage, cache và external dependencies.
6. Chọn thao tác failover/promote theo loại database cụ thể.

### Pha 3 — Kích hoạt

1. Thực hiện failover/failover group hoặc replica promotion theo runbook sản phẩm.
2. Xác minh role của database tại Region B.
3. Kiểm tra listener/FQDN/DNS routing và pool reconnect.
4. Mở write traffic theo quy trình có kiểm soát.
5. Chạy smoke tests giao dịch và đọc sau ghi từ nơi app chạy.
6. Theo dõi latency, error rate, locks và connection count.

### Pha 4 — Đối soát

1. Xác định mốc dữ liệu cuối có thể khẳng định đã replicate.
2. Đối chiếu các request/transaction IDs trong khoảng RPO risk.
3. Khôi phục những giao dịch có thể lấy lại từ outbox, message log hoặc các hệ thống nguồn khác.
4. Không tự động retry toàn bộ thanh toán khi chưa kiểm tra idempotency.
5. Ghi những trường hợp chưa thể xác nhận để xử lý thủ công.

### Pha 5 — Ổn định và failback

1. Giám sát hệ thống ở Region B ít nhất theo cửa sổ vận hành đã định.
2. Phục hồi replication/secondary topology.
3. Lập kế hoạch failback được phê duyệt; không tự trỏ traffic trở lại Region A.
4. Cập nhật DNS, certificates, automation và tài liệu.
5. Tổ chức postmortem và sửa các điểm còn thiếu.

## 35. Runbook: read replica lag cao

**Triệu chứng:** dashboard báo cáo chậm, đôi khi trả dữ liệu đơn hàng cũ 3–5 phút dù primary đã commit.

### Chẩn đoán

1. Đo lag bằng **metric/engine signal phù hợp**, ghi timestamp.
2. Kiểm tra primary write volume, bulk updates, DDL và transaction log/WAL/binlog growth.
3. Kiểm tra replica CPU, memory, IO latency, storage usage và long-running queries.
4. Kiểm tra network/region health và replication status.
5. Xem report queries nào chiếm tài nguyên hoặc tạo lock.
6. Xác định lag ảnh hưởng đến SLO nào: dashboard hay đường thanh toán?
7. Kiểm tra lỗi có bắt đầu sau scale tier, migration, index rebuild hoặc deploy không.

### Khắc phục

- Với đường cần dữ liệu mới ngay, tạm **route về primary** theo chính sách capacity.
- Giảm/tối ưu report queries và tạo index phù hợp trên primary/replica theo khả năng engine (lưu ý replicated schema).
- Tăng compute/IO của replica nếu workload cho phép và có approval.
- Throttle report concurrency hoặc chạy ngoài giờ.
- Kiểm tra replication link và sự cố nền tảng.
- Nếu replica lag nghiêm trọng kéo dài, cân nhắc rebuild theo runbook; không xóa replica trước khi bảo đảm còn đường phục vụ và DR.
- Kiểm tra lại lag, query latency và load primary sau thay đổi.

**Sai lầm cần tránh:** giảm cảnh báo lag threshold hoặc tăng TTL cache để giấu stale data nếu SLO thực vẫn bị vi phạm.

## 36. Runbook: failover làm ứng dụng không kết nối được

**Triệu chứng:** database đã chuyển role thành công nhưng ứng dụng tiếp tục báo connection timeout hoặc login failed.

### Kiểm tra theo lớp

| Lớp | Cần kiểm tra |
|---|---|
| Endpoint | Connection string đang dùng primary mới, listener hoặc alias được hỗ trợ? |
| DNS | FQDN trả IP/route đúng từ VNet nơi app chạy? |
| TCP/network | NSG, UDR, Firewall, private endpoint, ports? |
| TLS | Hostname certificate, CA, encryption settings? |
| Identity | Entra principal, DB user mapping, secret/connection password? |
| Driver | Connection pool cũ, DNS cache, retry/transient faults? |
| Database | Server đã read-write chưa, replica có còn recovery mode? |
| Transactions | Giao dịch nào chưa commit, request nào cần đối soát? |
| Capacity | Primary mới đủ CPU/IO/connection limits cho tải thật? |

### Phản ứng

1. Không tăng retry vô hạn.
2. Kiểm tra FQDN và host identity từ client thực.
3. Evict/refresh connection pool theo cơ chế ứng dụng.
4. Kiểm tra quyền và TLS, không vô hiệu hóa xác thực chứng chỉ.
5. Xác minh kết nối mới đọc được và ghi thử trên dữ liệu lab được cho phép.
6. Kiểm tra error rate, latency và business workflows.
7. Nếu cần rollback, đánh giá data divergence trước; không đảo DNS mù quáng.

## 37. Tình huống A: báo cáo làm chậm giao dịch thanh toán

**Bối cảnh:** cơ sở dữ liệu PostgreSQL Flexible Server chạy Orders API và 20 báo cáo BI vào cuối ngày. Primary CPU thường lên 95%, các requests thanh toán timeout.

**Giải pháp khả thi:**

1. Tối ưu report queries/index và xác định những queries thực sự cần Primary.
2. Tạo một read replica cùng region nếu SKU/region hỗ trợ, có capacity đủ cho BI.
3. Tách read pool dùng endpoint của replica, chỉ route các báo cáo **chấp nhận eventual consistency**.
4. Đặt lag SLO, ví dụ báo cáo chấp nhận trễ tối đa vài phút; theo dõi metric.
5. Giữ trạng thái thanh toán và đối soát tức thì trên primary.
6. Kiểm thử một báo cáo nặng không làm replica lag vượt ngưỡng.
7. Đánh giá chi phí replica và phương án chuyển BI workload sang analytics store nếu truy vấn quá nặng.

**Kết luận:** read replica giải quyết **phân tán tải đọc**, không phải tự sửa tất cả query inefficiency hoặc tạo một transactionally consistent global snapshot.

## 38. Tình huống B: vùng chính bị mất, replica remote chậm 90 giây

**Bối cảnh:** MySQL Flexible Server có read replica ở region khác trong cấu hình được hỗ trợ. Region chính mất kết nối; metric cuối ghi nhận replication lag khoảng 90 giây.

**Quyết định khó:**

- Nếu promote replica ngay, ứng dụng có thể phục hồi nhanh hơn nhưng có nguy cơ chưa có các writes trong khoảng replication lag.
- Nếu chờ Region A trở lại, có thể bảo toàn thêm dữ liệu nhưng RTO dài hơn.
- Nếu RPO mục tiêu 30 giây, promote với lag 90 giây **có nguy cơ không đáp ứng RPO**.
- Nếu đây là dữ liệu thanh toán, cần đối soát transaction IDs từ các hệ thống nguồn thay vì tự coi mọi đơn hàng đã commit ở Region A là còn trong Region B.

**Runbook:** xác nhận incident và lag, được phê duyệt lựa chọn, bảo vệ chống split-brain, promote đúng sản phẩm, định tuyến ứng dụng, xác minh role/write readiness và chạy reconciliation. Khi Region A phục hồi, không tự động cho hai servers cùng nhận writes.

## 39. Tình huống C: xóa nhầm bảng và geo-replication vẫn khỏe

**Bối cảnh:** Azure SQL Database có geo-secondary khỏe. Một migration sai chạy `DELETE FROM OrderItems` khiến dữ liệu biến mất. Monitoring replication báo secondary theo kịp primary.

**Phân tích:**

- Replication “khỏe” có thể đồng nghĩa **lệnh DELETE sai đã được replicate**.
- Failover sang secondary không tự phục hồi dữ liệu trước lỗi.
- Nếu backup/PITR còn recovery point, có thể khôi phục bản sao tại thời điểm trước thao tác xóa.
- Cần đối chiếu các writes hợp lệ sau recovery point để tránh mất giao dịch.
- Quy trình phù hợp gồm dừng/mất quyền sửa lỗi, khôi phục vào database mới trong môi trường kiểm soát, xác minh và thực hiện data repair/cutover theo quyết định.

**Bài học:** HA/geo-replication dành cho **sẵn sàng hệ thống**, còn PITR/backup là một thành phần bảo vệ khỏi **lỗi dữ liệu logic**.

## 40. Bài thực hành: thiết kế HA, read scale và DR cho Orders

**Bối cảnh:** hệ thống Orders có 20.000 giao dịch/ngày, dashboard BI chạy nhiều báo cáo nặng, cần khôi phục khi zone/region lỗi. Tổ chức có khả năng chọn Azure SQL Database hoặc PostgreSQL Flexible Server.

### Các yêu cầu

| Yêu cầu | Giá trị minh họa |
|---|---|
| Write workload | Transactional OLTP, các khoản thanh toán cần idempotency. |
| Read workload | Dashboard/reporting chấp nhận dữ liệu trễ tối đa vài phút. |
| Zone failure | Ứng dụng phải có kế hoạch duy trì availability. |
| Region failure | Có DR region, RPO/RTO được business phê duyệt. |
| Logical deletion | Phải có PITR/backup. |
| Networking | Private access, TLS, identity-based auth khi hỗ trợ. |
| Monitoring | Lag, availability, failover, CPU/IO, connections, backup. |
| Diễn tập | Không làm thay đổi Production ngoài cửa sổ đã phê duyệt. |

### Nhiệm vụ

1. Vẽ primary, HA standby, local read replica và geo-secondary/remote replica.
2. Phân biệt thành phần nào là failover target, thành phần nào được query read-only.
3. Chọn mô hình HA same-zone hay zone-redundant và giải thích vùng lỗi được bảo vệ.
4. Xác định workload nào đọc primary và workload nào được phép đọc replica.
5. Định nghĩa RPO, RTO và read freshness SLO (khác nhau).
6. Giải thích synchronous vs asynchronous replication và khi nào có nguy cơ data loss.
7. Với SQL Database, so sánh read scale-out với active geo-replication/failover group.
8. Với PostgreSQL/MySQL, giải thích HA standby khác read replica và ý nghĩa promotion.
9. Thiết kế connection strings/primary/read endpoints và quy trình reconnect sau failover.
10. Đặt 3 alerts: replica lag, primary unavailable, failed failover/connection errors.
11. Thêm một read replica vào sơ đồ và ước lượng tài nguyên/cost tăng.
12. Thiết kế cách tránh đọc stale `Order.status` ngay sau thanh toán.
13. Giả lập Primary unavailable nhưng remote replica trễ; quyết định theo RPO/RTO.
14. Giả lập DELETE nhầm; giải thích vì sao phải dùng PITR.
15. Thiết kế failback và chống split-brain.
16. Ghi checklist xác minh DNS, permissions, TLS, API service và secrets ở DR region.
17. Thiết kế DR drill không ảnh hưởng dữ liệu thật.
18. Viết một đoạn báo cáo cho incident commander gồm observed lag, data loss risk, RTO và hành động khuyến nghị.

### Sơ đồ lời giải tham khảo

```text
                       Global routing / API clients
                                 |
                   +-------------+-------------+
                   |                           |
              Region A                    Region B
              API active                  API DR ready
                   |                           |
              Write pool                 DR write pool
                   |                           |
                   v                           v
               Primary DB ─── async ───> Geo-secondary
                   |
             +-----+------+
             |            |
           HA standby   Local read replica
           (failover)   (BI reports)
             |
        Backups / PITR
         ở storage được quản lý
```

**Lời giải:**

- **Primary:** OLTP và những reads cần nhất quán ngay sau ghi.
- **HA standby:** không dùng làm BI reader; giảm rủi ro một node/zone theo HA mode.
- **Local read replica:** xử lý report/dashboard, có lag budget và read-only credential.
- **Geo-secondary:** phục vụ DR/cross-region reads theo sản phẩm; cần đối soát khi promote/failover cưỡng bức.
- **Backups/PITR:** bảo vệ khỏi DELETE sai/data corruption trong khoảng restore retention.
- **Đo lường:** lag, query latency, HTTP 5xx, connection errors, failover events, restore readiness.
- **Bảo mật:** private DNS/network, TLS, identity và Key Vault/credentials phù hợp vùng B.
- **Quy trình:** planned drill định kỳ, không xóa primary hoặc force failover trên Production chỉ để thử.
- **Cost:** database replicas, DR API resources, backups, network và monitoring.

### Tiêu chí nghiệm thu

Một thiết kế đạt yêu cầu khi:

- Mỗi resource có vai trò rõ ràng và mô tả phạm vi lỗi được bảo vệ.
- RPO/RTO có cơ sở đo và phương án khi không đạt mục tiêu.
- Read routing không phá vỡ nghiệp vụ read-your-writes.
- Không dùng read replica như bản backup cuối cùng.
- Có cách chuyển vùng và failback không gây split-brain.
- Có logs/metrics để chứng minh DR readiness và recovery.
- Chi phí được gắn với đúng SLA/SLO và yêu cầu dữ liệu.

## 41. Tự kiểm tra kiến thức

**Câu 1.** HA khác read replica ở mục đích chính nào?

**Đáp án:** HA bảo vệ tính sẵn sàng khi thành phần primary hỏng; read replica tách tải đọc và có thể hỗ trợ DR theo topology. HA standby không mặc định là read endpoint.

**Câu 2.** Geo-replication có thay thế backup/PITR không?

**Đáp án:** Không. Lỗi xóa/ghi sai có thể lan truyền qua replication; backup/PITR cần để khôi phục dữ liệu về mốc trước lỗi.

**Câu 3.** RPO và RTO khác nhau thế nào?

**Đáp án:** RPO là lượng dữ liệu tối đa chấp nhận mất khi phục hồi; RTO là thời gian tối đa chấp nhận để khôi phục dịch vụ.

**Câu 4.** Async replica có thể chậm primary dù primary commit thành công không?

**Đáp án:** Có. Primary có thể acknowledge trước khi replica nhận/apply giao dịch, tạo replication lag.

**Câu 5.** Một read replica cho PostgreSQL có cho phép ứng dụng UPDATE trực tiếp không?

**Đáp án:** Không khi nó đang đóng vai trò read-only replica; writes phải vào primary. Sau promotion theo cơ chế hỗ trợ, server được nâng vai trò nhưng topology đã thay đổi.

**Câu 6.** HA standby PostgreSQL/MySQL có được dùng như read replica phục vụ BI mặc định không?

**Đáp án:** Không. HA standby là thành phần dự phòng failover; muốn tách BI reads thường cần read replica riêng.

**Câu 7.** Zone-redundant HA có tự bảo vệ khỏi mất cả region không?

**Đáp án:** Không. Cần cross-region DR và ứng dụng/dependencies tương ứng.

**Câu 8.** Azure SQL read scale-out và active geo-replication có cùng mục đích không?

**Đáp án:** Không. Read scale-out tập trung offload đọc theo tier; active geo-replication sao chép đến secondary khác vùng phục vụ DR/đọc xa.

**Câu 9.** SQL failover group read-write listener có bảo đảm 100% client không mất kết nối khi failover không?

**Đáp án:** Không. Connections cũ có thể reset, DNS cache/pools cần reconnect và retry; listener giúp ổn định định danh endpoint.

**Câu 10.** Vì sao GET trạng thái đơn hàng ngay sau POST nên cân nhắc primary?

**Đáp án:** Read replica có replication lag, có thể trả giá trị cũ; luồng cần read-your-writes phải dùng nguồn/chiến lược consistency phù hợp.

**Câu 11.** Promote remote read replica có tự đảo chiều replication khi vùng cũ phục hồi không?

**Đáp án:** Không nên giả định. Promotion có thể biến replica thành standalone primary; failback cần xây lại/sync topology theo dịch vụ.

**Câu 12.** Có thể failover sang geo-secondary chậm 90 giây mà chắc chắn không mất commit nào không?

**Đáp án:** Không. Nếu replication bất đồng bộ, có nguy cơ mất các committed writes chưa sao chép.

**Câu 13.** Vì sao phải ngăn split-brain trong geo-DR?

**Đáp án:** Nếu cả primary cũ và primary mới cùng nhận writes, hai nhánh dữ liệu có thể khác nhau, rất khó khôi phục nhất quán.

**Câu 14.** Read replica làm primary tránh được mọi vấn đề hiệu năng không?

**Đáp án:** Không. Nó giúp tách một phần tải đọc, nhưng write bottleneck, queries tệ, locks và replication overhead vẫn cần tối ưu.

**Câu 15.** Một database có HA và geo-secondary nhưng không có PITR phù hợp thì rủi ro gì?

**Đáp án:** Không có recovery point an toàn khi schema migration hoặc DELETE sai đã được replicate.

**Câu 16.** Vì sao DNS TTL thấp không bảo đảm ứng dụng tự chuyển endpoint ngay sau failover?

**Đáp án:** Driver/OS/application có thể cache DNS hoặc giữ connections cũ; phải có reconnect, retry và pool refresh.

**Câu 17.** Managed identity có tự cấp quyền database khi đã enable trên Azure VM/AKS không?

**Đáp án:** Không. Còn cần cấu hình authentication, database users/roles, Azure RBAC theo dịch vụ và network.

**Câu 18.** Nếu read replica lag 4 phút nhưng dashboard SLO chỉ cho phép trễ 1 phút, có nên tiếp tục route dashboard tới replica không?

**Đáp án:** Không mà không có biện pháp xử lý/hiển thị rõ trạng thái. Phải cải thiện lag, route theo chính sách hoặc đánh dấu dữ liệu không còn đáp ứng freshness SLO.

**Câu 19.** Synchronous replication có luôn nghĩa zero downtime không?

**Đáp án:** Không. Dù dữ liệu có bảo đảm tốt hơn trong phạm vi thiết kế, failover/reconnect vẫn có thể gây gián đoạn.

**Câu 20.** Backup geo-redundant có giống hot geo-secondary sẵn sàng nhận writes không?

**Đáp án:** Không. Backup thường cần quy trình restore, có RTO khác và không tự hoạt động như primary được promote.

**Câu 21.** Khi application gặp connection timeout trong quá trình COMMIT, retry ngay có nguy cơ gì?

**Đáp án:** Có thể giao dịch đã commit nhưng acknowledgment thất lạc; retry không idempotent có thể tạo side effect trùng.

**Câu 22.** Mục tiêu nào quan trọng hơn khi thiết kế failover: RPO hay RTO?

**Đáp án:** Không có câu trả lời chung. Business phải xác định mức độ mất dữ liệu và thời gian gián đoạn chấp nhận được; đôi khi chúng xung đột.

**Câu 23.** Một read replica ở region B đã sẵn nhưng private DNS zone của app B sai. DR đã sẵn sàng chưa?

**Đáp án:** Chưa. Dữ liệu tồn tại nhưng ứng dụng không kết nối được; phải kiểm thử end-to-end, bao gồm DNS/network/TLS/identity.

**Câu 24.** Khi geo-secondary read-only báo CPU cao, có thể ảnh hưởng gì?

**Đáp án:** Read queries nặng có thể làm replica xử lý chậm/lag tăng, giảm hiệu năng đọc và có thể ảnh hưởng DR readiness.

**Câu 25.** Vì sao failback cần một runbook riêng?

**Đáp án:** Sau khi region B đã nhận writes, dữ liệu và replication topology có thể đổi; không thể chỉ đảo CNAME để trở lại A mà không kiểm tra sync/divergence.

**Câu 26.** Có thể dùng cùng một lệnh PostgreSQL promotion cho Azure SQL Database không?

**Đáp án:** Không. Chúng là dịch vụ/engine khác nhau, có API và semantics failover khác nhau.

**Câu 27.** Khi thay đổi số read replicas, chi phí có thể phát sinh ở đâu?

**Đáp án:** Compute/storage của mỗi replica, traffic replication, network/private endpoints, monitoring và DR operations.

**Câu 28.** Một restore drill thành công cần chứng minh gì ngoài việc resource mới có trạng thái Online?

**Đáp án:** Dữ liệu đúng mốc, schema/permissions phù hợp, app kết nối được, dữ liệu có thể đọc/ghi như kỳ vọng và recovery time/data loss đáp ứng mục tiêu.

**Tóm lại:** **High availability** giảm gián đoạn trước lỗi hạ tầng theo phạm vi host/zone được hỗ trợ; **read replicas** tách tải đọc nhưng đi kèm replication lag; **geo-replication** chuẩn bị dữ liệu ở vùng khác nhưng thường có rủi ro RPO do sao chép bất đồng bộ. Một thiết kế Azure database đáng tin cậy phải kết hợp **HA đúng tier/region, read routing theo consistency, backup/PITR, geo-DR runbook, ứng dụng reconnect/idempotent, bảo mật mạng/danh tính, monitoring và diễn tập khôi phục thực tế**. Mục tiêu cuối không chỉ là database có trạng thái Online mà là **toàn bộ nghiệp vụ vẫn chính xác và có thể khôi phục trong RTO/RPO đã cam kết**.
