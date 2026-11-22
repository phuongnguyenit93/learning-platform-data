# Aurora cluster, reader endpoint và custom endpoint

> **Chương:** Cơ sở dữ liệu RDS và Aurora  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn khả năng lựa chọn dịch vụ, thiết kế ứng dụng an toàn, giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Một nền tảng học trực tuyến có API ghi đăng ký, nhiều người tra cứu khóa học và tác vụ báo cáo dài. Nếu mọi truy vấn cùng dồn vào một database instance, truy vấn báo cáo có thể làm chậm giao dịch quan trọng. **Amazon Aurora** cung cấp mô hình **DB cluster** với một **writer** và nhiều **Aurora Replicas (readers)**, dựa trên shared distributed storage, cùng các **endpoint DNS** để ứng dụng kết nối đúng nhóm DB instances.

Bài này tập trung vào ba ý chính: kiến trúc **Aurora cluster**, **reader endpoint** để phân phối kết nối đọc, và **custom endpoint** để định tuyến một workload đến các instances được chọn. Sau khi học, bạn có thể:

1. Phân biệt Aurora DB cluster, DB instance, cluster volume, Availability Zone và failover.
2. Chọn giữa cluster/writer, reader, instance và custom endpoints.
3. Giải thích reader endpoint **cân bằng kết nối, không cân bằng từng query**, cũng như trường hợp fallback về writer khi thiếu readers.
4. Cấu hình custom endpoint kiểu **READER** hoặc **ANY**, hiểu `StaticMembers` và `ExcludedMembers`.
5. Phân tích failover, promotion tiers, reader membership, DNS cache và connection pools.
6. Áp dụng read/write splitting, đọc sau ghi, kiểm tra replica lag và SQL permissions.
7. Vận dụng RDS Proxy, VPC/SG, TLS, IAM và Secrets Manager khi cần.
8. Kiểm tra cấu hình qua AWS CLI **chỉ đọc**, không tạo hay thay đổi RDS resources.
9. Đề xuất monitoring, bài test, backup/restore và chi phí phù hợp workload.

## 1. Kiến trúc một Aurora DB cluster

### 1.1. Aurora cluster không chỉ là một DB instance

Một **DB cluster** là đơn vị logic chứa **distributed cluster volume**, writer instance, các Aurora Replicas và những endpoints dùng cho kết nối.

~~~mermaid
flowchart TD
    APP[API / Workers] --> WEP[Writer endpoint]
    APP --> REP[Reader endpoint]
    APP --> CEP[Custom endpoint: reports]
    WEP --> W[Writer instance AZ A]
    REP --> R1[Reader 1 AZ B]
    REP --> R2[Reader 2 AZ C]
    CEP --> R2
    W --> S[(Shared Aurora cluster volume)]
    R1 --> S
    R2 --> S
    ST[Storage copies across 3 AZs] -. protects .-> S
~~~

| Thành phần | Vai trò | Điều cần nhớ |
|---|---|---|
| DB cluster | Cấu trúc quản lý Aurora trong Region | Khác DB instance đơn |
| Cluster volume | Storage logic dùng chung, phân tán | Compute tách khỏi storage |
| Writer/primary instance | Xử lý ghi và đọc | Một writer trong cluster thông thường |
| Aurora Replica | Nhận truy vấn đọc và có thể được promote | Có thể nằm AZ khác, tối đa 15 replicas theo mô hình hỗ trợ |
| Cluster endpoint | DNS hướng tới writer hiện tại | App dùng cho SQL writes/DDL |
| Reader endpoint | DNS hướng tới các readers hiện có | Phân phối **new connections** |
| Instance endpoint | DNS của một instance cụ thể | Để test/admin/diagnostics |
| Custom endpoint | DNS hướng tới tập instances được chọn | Dành cho specialized workloads |

Aurora tương thích **MySQL hoặc PostgreSQL** theo engine/version. Khả năng query, SQL extensions, driver và các tính năng cụ thể vẫn phụ thuộc engine family; không coi mọi tham số PostgreSQL/MySQL là giống nhau.

### 1.2. Shared storage và Availability Zones

Aurora sử dụng cluster volume phân tán với dữ liệu nhân bản ở **ba Availability Zones**. Tài liệu Aurora mô tả cơ chế **sáu bản sao lưu trữ trên ba AZ**. Writer và các readers cùng nhìn một cluster volume logic, không cần copy một bộ EBS riêng biệt cho từng reader giống các mô hình replica khác.

**Hệ quả thiết kế:**

- Reader tăng capacity về compute để xử lý truy vấn đọc, **không** làm single-writer có thêm writer.
- Thêm reader ở AZ khác cải thiện lựa chọn failover.
- Storage replication giúp bền vững, nhưng **không tự bảo đảm ứng dụng luôn sẵn sàng** nếu chỉ có một DB instance.
- Tách compute khỏi storage giúp Aurora có thể promote reader thành writer mà không cần sao chép toàn bộ dataset lúc chuyển vai trò.
- Shared storage cũng **không phải backup độc lập**: xóa nhầm dữ liệu vẫn là thay đổi trên cluster volume.

### 1.3. Writer và reader instances

Writer thực hiện `INSERT`, `UPDATE`, `DELETE` và các thay đổi schema như `CREATE TABLE`. Reader phục vụ workloads đọc, đồng thời có thể làm failover candidates.

Giả sử:

~~~text
Cluster: course-prod

Writer: course-prod-writer-1, AZ A
Reader: course-prod-reader-1, AZ B
Reader: course-prod-reader-2, AZ C

Dữ liệu lưu trên một Aurora cluster volume.
~~~

Một ứng dụng nhỏ có thể chỉ dùng một writer và chưa có reader. Khi đó **reader endpoint DNS vẫn tồn tại** nhưng chưa có nhóm read replicas để phân phối.

### 1.4. Aurora vs RDS Multi-AZ DB instance

| Tiêu chí | Aurora cluster | RDS Multi-AZ DB instance truyền thống |
|---|---|---|
| Compute | Writer + optional readers | Primary + standby để HA |
| Đọc qua replica | Aurora Replicas có thể phục vụ queries | Standby của mô hình DB instance thường không phục vụ đọc |
| Storage | Aurora shared distributed volume | Cơ chế lưu trữ/replication khác |
| Reader endpoint | Built-in reader endpoint | Không coi standby là reader endpoint |
| Failover | Promote reader hoặc phục hồi primary | Chuyển sang standby theo RDS |
| Read scaling | Tăng reader instances | Tùy RDS engine/deployment/read replica |

AWS có thêm sản phẩm **RDS Multi-AZ DB cluster**, khác với RDS Multi-AZ DB instance và Aurora. Bảng chỉ so sánh mô hình truyền thống để làm rõ khái niệm.

## 2. Phân biệt các endpoint của Aurora

### 2.1. Bảng quyết định

| Endpoint | Hostname minh họa | Dùng khi |
|---|---|---|
| **Cluster/writer** | `course.cluster-xxxx.ap-southeast-1.rds.amazonaws.com` | DML/DDL, transaction có ghi, read-after-write nghiêm ngặt |
| **Reader** | `course.cluster-ro-xxxx.ap-southeast-1.rds.amazonaws.com` | Đọc quy mô lớn, có thể chấp nhận replica lag |
| **Instance** | `course-reader-1.xxxx.ap-southeast-1.rds.amazonaws.com` | Debug/query tuning tới instance cụ thể |
| **Custom** | `course-reports.cluster-custom-xxxx.ap-southeast-1.rds.amazonaws.com` | Cô lập nhóm readers cho báo cáo hoặc ad-hoc |

Hostnames là **giả định**, không trỏ đến tài nguyên có thật. Port mặc định thường là **3306** cho Aurora MySQL, **5432** cho Aurora PostgreSQL; kiểm tra port thực tế của cluster thay vì hard-code.

### 2.2. Cluster/writer endpoint

Mỗi Aurora cluster thông thường có một **writer endpoint**, được AWS duy trì để kết nối writer hiện tại:

~~~text
jdbc:postgresql://course.cluster-xxxx.ap-southeast-1.rds.amazonaws.com:5432/appdb
~~~

Dùng cho:

- `INSERT`, `UPDATE`, `DELETE`, DDL;
- Transaction vừa đọc vừa ghi;
- Đọc sau khi vừa commit và cần nhìn thấy thay đổi mới;
- Locking/select-for-update, migrations và tác vụ quản trị có thẩm quyền.

**Không hiểu writer endpoint là proxy tự phân tách SQL.** Nếu mở một connection tới writer rồi gửi `SELECT`, query đó chạy trên writer. Khi failover, endpoint sẽ đổi đích tới **writer mới** nhưng connection cũ có thể ngắt và app phải reconnect.

### 2.3. Built-in reader endpoint

Mỗi Aurora cluster có một reader endpoint tích hợp. Nếu có readers đủ điều kiện, reader endpoint **phân phối các connection requests** giữa Aurora Replicas để giảm read load trên writer.

~~~text
jdbc:postgresql://course.cluster-ro-xxxx.ap-southeast-1.rds.amazonaws.com:5432/appdb
~~~

**Bốn điểm đặc biệt quan trọng:**

1. Reader endpoint **không cân bằng từng SQL query**; mỗi connection đã tạo sẽ gắn một instance.
2. Aurora reader có thể có **replica lag**; không dùng cho thao tác đòi read-your-writes tuyệt đối nếu chưa thiết kế consistency.
3. Nếu cluster **không có reader khả dụng**, built-in reader endpoint **có thể kết nối tới writer**, và connection đó có thể thực hiện write nếu DB user được phép.
4. Bạn **không thể tạo/xóa/đổi membership trực tiếp** của built-in reader endpoint; muốn nhóm reader chuyên biệt, dùng custom endpoint.

**Không dùng reader endpoint làm cơ chế bảo mật cấm ghi**. Tài khoản DB chuyên đọc phải được cấp quyền **SELECT-only** ở database.

### 2.4. Instance endpoint

Instance endpoint hướng tới một **DB instance cụ thể**, thuận tiện kiểm tra slow queries, CPU/memory, connection count, replica lag hoặc query plans.

~~~text
course-reader-1.xxxx.ap-southeast-1.rds.amazonaws.com:5432
~~~

**Cẩn trọng:** instance có thể đổi vai trò sau failover. Endpoint theo **tên instance**, không theo role; một instance hôm nay là reader có thể là writer ngày mai. Không hard-code writer instance endpoint cho ứng dụng cần tự phục hồi sau failover.

### 2.5. Custom endpoint

Custom endpoint biểu diễn một **tập con các instances** do bạn xác định, dùng để cô lập nhóm xử lý báo cáo hoặc nhóm có cấu hình máy khác nhau:

~~~text
Built-in reader endpoint -> reader-small, reader-medium, reader-report

Custom interactive -> reader-small, reader-medium
Custom reporting -> reader-report
~~~

Aurora phân phối **new connections** qua những instances eligible, không lập lịch từng câu truy vấn. AWS hiện hỗ trợ tối đa **5 custom endpoints/cluster** theo tài liệu cho provisioned và Aurora serverless clusters.

### 2.6. Chọn endpoint từ workload

~~~mermaid
flowchart TD
    Q[Workload DB] --> D{Có ghi / DDL / read-your-writes?}
    D -->|Có| W[Writer endpoint]
    D -->|Không| R{Đọc cần cô lập theo nhóm capacity?}
    R -->|Không| RE[Built-in Reader endpoint]
    R -->|Có| CE[Custom READER endpoint]
    Q -->|Debug chính xác instance| IE[Instance endpoint]
    Q -->|Nhiều pooled connections / failover| PR[RDS Proxy writer / reader endpoints]
~~~

## 3. Reader endpoint là connection balancer

### 3.1. Không phải query router

~~~mermaid
flowchart LR
    POOL[Java HikariCP pool] -->|New session 1| DNS[Reader endpoint DNS]
    POOL -->|New session 2| DNS
    POOL -->|New session 3| DNS
    DNS --> R1[Reader A]
    DNS --> R2[Reader B]
    DNS --> R3[Reader C]
~~~

Một connection đã thiết lập tới reader A có thể chạy 200 câu `SELECT` trên reader A. Nó không tự chuyển từng `SELECT` sang reader B/C. Vì vậy, nếu connection pool tạo toàn bộ connections cùng lúc rồi giữ lâu, phân bố load có thể không đều.

### 3.2. Vì sao có reader CPU 80% và reader khác 10%?

Các nguyên nhân thường gặp:

- JVM/OS/JDBC client cache DNS rất lâu và kết nối đến cùng một IP;
- Connection pool giữ sessions lâu, không tạo thêm connections mới;
- Báo cáo nặng chạy trên một reader, dù số sessions không nhiều;
- Một reader không healthy hoặc vừa maintenance/failover;
- App dùng nhầm instance endpoint hoặc custom endpoint chỉ có một member;
- Auto Scaling thêm reader nhưng app không tái tạo connections.

**Không tăng số readers ngay khi thấy tải lệch**; trước hết xác định pool đang kết nối đến DB instance nào, số sessions thực tế và query profile.

### 3.3. DNS TTL và HikariCP

Theo tài liệu Aurora best practices, nếu client cache DNS, nên dùng **TTL dưới 30 giây** để nhanh chóng sử dụng IP mới sau failover. Đây là hướng dẫn vận hành, không phải SLA DNS switch ở một thời gian cố định.

Một ví dụ cấu hình Java security properties:

~~~properties
networkaddress.cache.ttl=10
networkaddress.cache.negative.ttl=1
~~~

Các properties này thường được cấu hình ở **JVM security settings** hoặc set qua `java.security.Security.setProperty(...)` khi khởi động sớm, không phải mặc định có tác dụng nếu đặt vào file `application.properties`.

Trong HikariCP, `maximumPoolSize`, `minimumIdle`, `idleTimeout`, `maxLifetime`, `connectionTimeout` và connection validation ảnh hưởng cách tạo/tái sử dụng connections. Không đặt maxLifetime vài giây để cố tạo load balancing theo query; việc này có thể gây connection churn và tăng CPU.

### 3.4. Reader endpoint không bảo đảm phân phối CPU công bằng

Một reader đang chạy một query báo cáo 15 phút có thể sử dụng rất nhiều CPU/RAM dù chỉ có một pooled connection. Reader endpoint không phân tích SQL cost để tự dời query tới reader khác. Với workload không đồng nhất, **custom endpoint** + query timeouts + DB grants + capacity planning là phương án rõ hơn.

### 3.5. Reader endpoint và RDS Proxy reader endpoint

| Tiêu chí | Aurora reader endpoint | RDS Proxy read-only endpoint |
|---|---|---|
| Dịch vụ | Aurora DB cluster | RDS Proxy kết nối cluster |
| Connection balancing | DNS khi tạo connection | Proxy quản lý target connections |
| Pooling | Do application | Có pooling/multiplexing khi phù hợp |
| DNS cache/failover | Client phải tái phân giải/reconnect | Proxy có thể giảm gián đoạn |
| Khi không có readers | **Có thể fallback writer** | **Read-only proxy endpoint có thể lỗi/đợi**, không tương đương fallback writer |
| Phí | Không có proxy service riêng | Có RDS Proxy cost |

**Custom Aurora endpoint không phải RDS Proxy endpoint.** RDS Proxy còn có networking, authentication, secrets và quota riêng. Proxy không thay thế business transaction/idempotency.

## 4. Custom endpoints: READER, ANY và membership

### 4.1. Vì sao cần phân nhóm readers?

Giả sử:

~~~text
writer:            db.r7g.large
reader-api-1:      db.r7g.large
reader-api-2:      db.r7g.large
reader-report:     db.r7g.2xlarge

API tra cứu  -> reader-api-1 và reader-api-2
BI reporting -> reader-report
~~~

Nếu cả API và BI dùng built-in reader endpoint, BI vẫn có thể được gửi vào reader nhỏ và API vẫn có thể vào reader lớn. Custom endpoints cho phép **chọn nhóm instance** phù hợp workload.

### 4.2. CustomEndpointType=READER hay ANY

| Kiểu | Eligible instances | Phù hợp | Cẩn trọng |
|---|---|---|---|
| **READER** | Chỉ reader role trong membership | BI, reporting, API chỉ đọc | Nếu không còn eligible reader thì có thể không kết nối |
| **ANY** | Writer và readers đều có thể được chọn nếu nằm trong membership | Ứng dụng hiểu rõ topology và chấp nhận cả vai trò | Write có thể đến reader gây lỗi; query nặng có thể vào writer |

**AWS Console hiện tạo custom endpoint dạng ANY**, không cho chọn type ở màn hình tạo. Nếu cần type **READER**, dùng AWS CLI/API/IaC hỗ trợ và xác minh `CustomEndpointType` sau khi tạo. Một số API schemas liệt kê enum bổ sung nhưng hướng dẫn Aurora custom endpoints tập trung vào **READER/ANY**; kiểm tra hỗ trợ thực tế theo engine/version.

**Không dùng ANY như writer endpoint thứ hai** và không tin ANY giữ vai trò chỉ đọc. Nếu workload bắt buộc chỉ đọc, dùng READER type và DB user SELECT-only.

### 4.3. StaticMembers — danh sách cố định

~~~text
Custom reporting (READER):
  StaticMembers:
    - course-reader-report-1
    - course-reader-report-2
~~~

Endpoint chỉ chứa các instances được liệt kê và **có role phù hợp**. Nếu Aurora Auto Scaling tạo reader mới, **nó không tự được thêm** vào static membership. Phù hợp khi chỉ muốn báo cáo sử dụng hai high-memory readers đã duyệt.

### 4.4. ExcludedMembers — danh sách loại trừ

~~~text
Custom interactive (READER):
  ExcludedMembers:
    - course-reader-report-1

Eligible:
  mọi reader hiện có/tương lai
  trừ course-reader-report-1
~~~

Khi thêm reader mới, endpoint dựa trên **exclusion list** có thể tự thêm reader đủ điều kiện nếu tên nó không nằm trong `ExcludedMembers`. Vì vậy phù hợp Aurora Replica Auto Scaling.

**Chỉ một trong hai kiểu list** áp dụng cho một endpoint: static inclusion **hoặc** exclusion. Không dùng hai danh sách như hai biểu thức đồng thời. Thành viên có thể thuộc nhiều custom endpoints; phải xem tổng tải từng instance.

### 4.5. Động học membership khi failover

Trước failover:

~~~text
writer: course-primary
reader: course-reader-a
reader: course-reader-b

Custom READER static=[course-reader-a, course-reader-b]
~~~

Sau khi `course-reader-a` được promote thành writer:

~~~text
writer: course-reader-a
reader: course-reader-b

Custom READER eligible -> course-reader-b
~~~

Với type **READER**, Aurora loại instance đã đổi thành writer khỏi nhóm eligible. Với type **ANY**, instance đó có thể tiếp tục thuộc endpoint khi membership list vẫn bao gồm.

**Quan trọng:** việc thay membership không tự ngắt mọi database sessions đã mở. Session trên instance bị failover có thể bị ngắt do failover; những session khác còn tồn tại. Application cần xử lý stale connections và re-resolve DNS.

### 4.6. Chọn static hay excluded

| Use case | Chọn |
|---|---|
| Dành đúng hai readers mạnh cho BI | READER + StaticMembers |
| Dành mọi reader trừ một instance ETL | READER + ExcludedMembers |
| Muốn new auto readers tự vào API read group | ExcludedMembers |
| Không cần chia readers theo workload | Built-in reader endpoint |
| Một số writers/readers đều eligible cho tác vụ đặc biệt | ANY, nhưng phải đánh giá rủi ro |
| Chỉ được cấp quyền đọc dữ liệu nhạy cảm | READER + SELECT-only DB role + authorization |

### 4.7. Không coi custom endpoint là kiểm soát bảo mật

Custom endpoint chỉ chọn nhóm DB instances ở **connection time**, không tự cấp/cấm quyền SQL. Nếu DB role có `INSERT` permission, type ANY gửi connection tới writer vẫn có thể ghi; và type READER không thể thay DB GRANT. Phải kết hợp:

- Separate DB credentials cho readers;
- DB grants, schema/table/RLS permissions;
- VPC SGs và resource isolation;
- Query timeouts/resource governor khi phù hợp;
- Audit và owner cho từng endpoint.

## 5. Failover, role change và high availability

### 5.1. Khi writer gặp sự cố

Aurora có thể promote một Aurora Replica thành writer mới:

~~~mermaid
sequenceDiagram
    participant APP as Java application
    participant EP as Cluster writer endpoint
    participant W as Old writer AZ A
    participant R as Reader AZ B
    APP->>EP: SQL write connection
    EP->>W: Current writer
    Note over W: Failure
    Note over R: Aurora promotes reader
    APP->>W: Old JDBC session fails
    APP->>EP: Reconnect and resolve DNS
    EP->>R: New writer
    APP->>R: Safe retry / reconciliation
~~~

Endpoint DNS vẫn biểu thị writer role, nhưng **đường TCP/JDBC session cũ không tự di chuyển**. App phải reconnect, invalidate broken pool connections và retry operation an toàn.

### 5.2. Promotion tiers

Aurora hỗ trợ **failover promotion tiers từ 0 đến 15**:

- Tier **0** là ưu tiên cao nhất;
- Tier **15** thấp nhất;
- Khi cùng tier, Aurora xét thêm instance capacity/khả dụng theo logic dịch vụ;
- Không suy đoán instance CPU thấp nhất luôn được promote.

Nếu cluster chỉ có writer mà không có reader, Aurora phải phục hồi primary host thay vì promote sẵn một reader, có thể tăng downtime. Để HA tốt hơn, nên bố trí readers trong **AZ khác writer**.

Với Aurora Serverless v2, promotion tier 0/1 còn có thể ảnh hưởng minimum ACU của serverless readers để sẵn sàng thay writer. Đánh giá cả chi phí, không tự cấu hình tất cả readers Tier 0.

### 5.3. Endpoint sau khi đổi vai trò

| Endpoint | Hành vi sau failover |
|---|---|
| Writer | DNS chuyển mục tiêu tới writer mới; app reconnect |
| Reader | Tập readers có thể đổi; nếu không còn reader khả dụng có thể fallback writer |
| Instance | Vẫn chỉ instance cụ thể, nhưng role instance có thể đổi |
| Custom READER | Eligible instances điều chỉnh theo reader role |
| Custom ANY | Có thể tiếp tục chứa promoted writer |
| RDS Proxy | Quản lý DB targets/connection pooling theo semantics riêng |

Kết nối hiện hữu có thể bị ngắt; queries đang chạy có thể bị rollback hoặc trả error. **Endpoint name ổn định không có nghĩa transaction luôn tiếp tục không gián đoạn**.

### 5.4. Failover-aware transaction recovery

Ví dụ giao dịch trừ số dư:

~~~sql
BEGIN;
UPDATE wallet
SET balance = balance - 100
WHERE account_id = 'account-123';
COMMIT;
~~~

Nếu kết nối đứt **ngay sau COMMIT nhưng trước khi app nhận acknowledgment**, app không biết thao tác đã thành công hay chưa. Retry mù có thể trừ 2 lần. Cần **business operation ID**, unique constraints/idempotency, đối soát kết quả, retry backoff có giới hạn và transaction audit.

Không dùng failover test thật trên production chỉ để kiểm tra bài học. Failover có thể gây interruption và chi phí.

### 5.5. Cluster chỉ có writer

Với cluster không có reader:

- Reader endpoint vẫn tồn tại, có thể trỏ về writer;
- Read traffic tranh CPU/RAM với writes;
- Custom type READER không có eligible target;
- RDS Proxy read-only endpoint không giống built-in reader fallback;
- Failover không có reader sẵn để promote.

**Luôn kiểm tra `DBClusterMembers[].IsClusterWriter` và status instances**, đừng chỉ xem hostname reader endpoint để kết luận đã scale reads.


## 6. Read consistency và read/write splitting

### 6.1. Replica lag và đọc dữ liệu cũ

Aurora Replicas nhìn cùng shared cluster volume, nhưng **thời điểm thấy thay đổi** có thể trễ writer. AWS mô tả Aurora Replica lag thường rất thấp trong điều kiện bình thường, nhưng nó **không được bảo đảm bằng 0**, nhất là khi write load/long-running queries tăng.

Ví dụ:

~~~text
T0: Writer COMMIT enrollment.status = PAID
T0 + 5 ms: App SELECT status qua reader A -> còn PENDING
T0 + 40 ms: App SELECT lại -> thấy PAID
~~~

Đây là **stale read**. Với feed khóa học public có thể chấp nhận; với xác nhận thanh toán, kiểm tra quyền tài chính, update-after-read hoặc yêu cầu **read-your-writes**, thường cần đọc lại từ writer hoặc một cơ chế consistency đã được thiết kế/kiểm thử rõ ràng.

### 6.2. Ma trận chọn đường kết nối

| Nghiệp vụ | Yêu cầu | Endpoint |
|---|---|---|
| Tạo khóa học/đăng ký | Ghi transaction | Writer |
| Đọc trạng thái ngay sau khi thanh toán | Read-your-writes | Writer |
| Tìm kiếm catalog khóa học | Cho phép staleness nhỏ | Reader |
| Báo cáo tổng hợp cuối ngày | Chấp nhận replica lag, query nặng | Custom READER dành riêng báo cáo |
| Xác minh còn tồn kho rồi trừ | Transaction/locking | Writer trong cùng transaction |
| Xem thống kê tổng quát | Eventually consistent hợp lệ | Reader hoặc custom |
| Chạy DDL/migration | Thay đổi schema | Writer, quy trình change-control |
| Đo hiệu năng một DB instance | Đúng instance cụ thể | Instance endpoint |

### 6.3. Transaction không tự tách nửa đọc nửa ghi

Một transaction gồm đọc rồi ghi, nếu yêu cầu locking/consistency, phải chạy qua writer:

~~~sql
BEGIN;
SELECT seats_remaining
FROM course_capacity
WHERE course_id = 'course-123'
FOR UPDATE;

UPDATE course_capacity
SET seats_remaining = seats_remaining - 1
WHERE course_id = 'course-123' AND seats_remaining > 0;

COMMIT;
~~~

Nếu câu `SELECT FOR UPDATE` bị gửi sang reader sẽ không phù hợp role read-only và locking semantics. **Không router SQL chỉ dựa vào chữ đầu `SELECT`**, vì stored functions, CTE hoặc transaction có thể thay đổi dữ liệu hoặc yêu cầu session state.

### 6.4. Spring `@Transactional(readOnly=true)` không tự định tuyến

Trong Spring, `@Transactional(readOnly=true)` thường là **hint/semantics cho transaction manager/JPA/driver**, không có nghĩa framework tự kết nối Aurora reader endpoint. Cần cấu hình **routing datasource** hoặc tách hai DataSources/JdbcTemplates rõ ràng.

Nếu dùng `AbstractRoutingDataSource`, routing decision phải xảy ra **trước thời điểm lấy JDBC connection**, đồng thời phải xét propagation, nested transactions và async threads. Với nhu cầu cơ bản, **hai connection pools rõ ràng** dễ kiểm soát hơn dynamic SQL routing.

### 6.5. DB role chỉ đọc bảo vệ đúng tầng

Giả sử ứng dụng dùng:

~~~text
app_writer:
  quyền INSERT/UPDATE/DELETE ở các tables cần thiết

app_reader:
  quyền SELECT ở schemas/tables được phép
  không có DML/DDL
~~~

Dù reader endpoint bất ngờ trỏ về writer vì không còn replicas, **DB user app_reader vẫn không được ghi**. Endpoint là công cụ định tuyến, **không phải security boundary**.

Ví dụ PostgreSQL minh họa trên sandbox:

~~~sql
-- Thực hiện bằng DB admin có thẩm quyền trong môi trường thử nghiệm.
-- Không lưu password plaintext trong source code/migration logs.
CREATE ROLE app_reader LOGIN;
GRANT CONNECT ON DATABASE appdb TO app_reader;
GRANT USAGE ON SCHEMA public TO app_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO app_reader;
~~~

Các SQL GRANT thực tế phụ thuộc schema owner, inheritance, RLS, extension và phiên bản engine. `ALTER DEFAULT PRIVILEGES` chỉ áp dụng cho **objects được tạo bởi role tương ứng** nếu không chỉ định role khác. Hãy xác minh qua permission tests và dùng Secrets Manager/IAM DB auth cho login theo thiết kế.

## 7. Ví dụ Java/Spring Boot: hai connection pools

### 7.1. Các biến môi trường

Ví dụ cho Aurora PostgreSQL:

~~~properties
db.writer.jdbc-url=jdbc:postgresql://${DB_WRITER_HOST}:5432/appdb?sslmode=verify-full
db.reader.jdbc-url=jdbc:postgresql://${DB_READER_HOST}:5432/appdb?sslmode=verify-full

db.writer.username=${DB_WRITER_USER}
db.writer.password=${DB_WRITER_PASSWORD}
db.reader.username=${DB_READER_USER}
db.reader.password=${DB_READER_PASSWORD}
~~~

Nếu bật `verify-full`, phải cài đúng **AWS RDS trust CA** và driver TLS configuration trong runtime. Không đặt values chứa password vào Git. Variables được lấy từ secret store/runtime theo policy; `DB_READER_HOST` là **DNS name**, không phải IP cố định.

### 7.2. Spring Boot 3.x, HikariCP và JdbcTemplate

Ví dụ wiring rút gọn nhưng có các class/imports chính:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class AuroraPoolsConfig {

    @Bean("writerDataSource")
    @Primary
    DataSource writerDataSource(
            @Value("${db.writer.jdbc-url}") String url,
            @Value("${db.writer.username}") String username,
            @Value("${db.writer.password}") String password) {
        HikariConfig config = new HikariConfig();
        config.setPoolName("aurora-writer");
        config.setJdbcUrl(url);
        config.setUsername(username);
        config.setPassword(password);
        config.setMaximumPoolSize(12);
        config.setConnectionTimeout(3000);
        return new HikariDataSource(config);
    }

    @Bean("readerDataSource")
    DataSource readerDataSource(
            @Value("${db.reader.jdbc-url}") String url,
            @Value("${db.reader.username}") String username,
            @Value("${db.reader.password}") String password) {
        HikariConfig config = new HikariConfig();
        config.setPoolName("aurora-reader");
        config.setJdbcUrl(url);
        config.setUsername(username);
        config.setPassword(password);
        config.setReadOnly(true); // JDBC hint; DB GRANT vẫn cần.
        config.setMaximumPoolSize(16);
        config.setConnectionTimeout(3000);
        return new HikariDataSource(config);
    }

    @Bean("writerJdbc")
    JdbcTemplate writerJdbc(@Qualifier("writerDataSource") DataSource ds) {
        return new JdbcTemplate(ds);
    }

    @Bean("readerJdbc")
    JdbcTemplate readerJdbc(@Qualifier("readerDataSource") DataSource ds) {
        return new JdbcTemplate(ds);
    }
}
~~~

**Phạm vi ví dụ:** có thể cần cấu hình Spring Boot auto-configuration/`TransactionManager`/JPA riêng nếu ứng dụng đang dùng JPA, Spring Data hay nhiều DataSources. Số pool sizes là placeholder. Xác minh driver, dependency, SSL, SQL timeouts, connection validation và retry trong integration tests.

### 7.3. Chọn đúng JdbcTemplate trong service

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class EnrollmentService {
    private final JdbcTemplate writer;
    private final JdbcTemplate reader;

    public EnrollmentService(
            @Qualifier("writerJdbc") JdbcTemplate writer,
            @Qualifier("readerJdbc") JdbcTemplate reader) {
        this.writer = writer;
        this.reader = reader;
    }

    public int countPublishedCourses() {
        return reader.queryForObject(
            "SELECT COUNT(*) FROM courses WHERE published = true",
            Integer.class
        );
    }

    public int confirmEnrollment(String id) {
        return writer.update(
            "UPDATE enrollment SET status = ? WHERE id = ?",
            "PAID", id
        );
    }
}
~~~

**Rủi ro:** nếu gọi `confirmEnrollment` rồi lập tức gọi một read method qua reader, dữ liệu trả về có thể chưa thấy trạng thái mới. Trong flow thanh toán, nếu cần hiển thị xác nhận chính xác, đọc lại qua writer hoặc trả dữ liệu vừa commit theo transaction.

### 7.4. Transaction management với hai pools

Khi ứng dụng dùng JPA, cần tách hoặc cấu hình rõ:

- `EntityManagerFactory` và `PlatformTransactionManager` tương ứng;
- `@Transactional(transactionManager="writerTxManager")` cho luồng có ghi;
- Cấu hình read datasource/read transaction manager nếu thật sự muốn;
- Không mặc định hai transaction managers tạo **distributed atomic transaction**;
- Không dùng một transaction có ghi trên hai instances và mong isolation/locking thống nhất;
- Nếu buộc phải router trong cùng logic nghiệp vụ, xây rõ rule và test failover.

### 7.5. Tính tổng connections

Giả sử app có 6 tasks EC2/ECS chạy đồng thời:

~~~text
writer pool tối đa: 12 connections mỗi app task
reader pool tối đa: 16 connections mỗi app task

writer connections lý thuyết từ apps: 6 × 12 = 72
reader connections lý thuyết từ apps: 6 × 16 = 96
~~~

Đây chưa gồm admin connections, workers khác, background jobs, autoscales hoặc retry spikes. Nếu reader DNS phân phối lệch, một reader có thể nhận đa số của 96 connections. Theo dõi `DatabaseConnections` theo **DBInstanceIdentifier**; không chỉ nhìn tổng cluster.

**Không tăng `maximumPoolSize` khi gặp `too many connections` mà không phân tích.** Có thể cần giảm long-running transactions, giảm connection churn, chỉnh app scaling hoặc cân nhắc RDS Proxy.

### 7.6. Startup validation không lộ secret

Ứng dụng cần fail fast khi thiếu `DB_WRITER_HOST`/`DB_READER_HOST`, nhưng không in toàn bộ JDBC URL/credentials vào logs. Báo lỗi theo **tên key** và endpoint role; redact password/URL query sensitive fields. Với health endpoint, nên phân biệt **liveness** và **readiness** để tránh probe nặng/false positive khi một reader tạm unavailable.

## 8. RDS Proxy, connection resilience và proxy reader endpoint

### 8.1. Vì sao dùng RDS Proxy?

RDS Proxy đứng giữa app và Aurora, giúp quản lý DB connections và hỗ trợ failover:

~~~mermaid
flowchart LR
    APP[Lambda/ECS/EC2 app] --> PW[RDS Proxy read-write endpoint]
    APP --> PR[RDS Proxy read-only endpoint]
    PW --> W[Aurora writer]
    PR --> R1[Aurora reader A]
    PR --> R2[Aurora reader B]
~~~

RDS Proxy default endpoint hỗ trợ read/write và gửi đến writer. Có thể tạo **read-only proxy endpoint** để định tuyến các connections vào nhóm Aurora readers. Proxy có thể làm giảm kết nối mở trực tiếp, hỗ trợ multiplexing ở các tình huống tương thích và giúp reconnect nhanh hơn khi reader unavailable.

### 8.2. Khi nào proxy không giải quyết hết vấn đề?

- Không tự tách SQL read/write nếu client vẫn dùng một endpoint;
- Không tăng năng lực CPU/RAM của reader;
- Không đảm bảo transaction commit exactly-once;
- Không thay thế DB grants, SG và Secrets Manager;
- Session pinning hoặc long-running transactions có thể giảm khả năng multiplexing;
- Proxy read-only endpoint có thể chờ rồi fail khi **không có reader khả dụng**, khác built-in Aurora reader endpoint;
- Proxy phát sinh **chi phí** và có limits/configuration riêng.

Khi app có nhiều Lambda invocations ngắn, có thể cân nhắc proxy để hạn chế connection storms. Tuy nhiên phải benchmark chi phí/throughput và kiểm tra compatibility theo Aurora engine/Serverless version.

### 8.3. Khi nào custom Aurora endpoint tốt hơn proxy?

| Yêu cầu | Công cụ phù hợp |
|---|---|
| Chỉ chọn readers có RAM lớn phục vụ BI | Aurora custom READER endpoint |
| Đưa mọi new connections tới đúng subset theo danh sách | Custom Static/ExcludedMembers |
| Giảm DB connections từ hàng nghìn clients | RDS Proxy |
| Failover-aware reconnect và connection management | RDS Proxy/AWS JDBC Driver phù hợp |
| Cần hai nhóm readers khác capacity | Custom endpoints, có thể kết hợp proxy tùy kiến trúc hỗ trợ |
| Muốn phân phối từng SQL query giữa readers | Không có endpoint Aurora thông thường nào làm điều đó tự động |

Không coi RDS Proxy và Aurora custom endpoints là cùng một loại tài nguyên. Proxy endpoint có **proxy target role**, custom endpoint có **custom endpoint type/membership**, khác API và ownership.

## 9. VPC, IAM, TLS và Secrets Manager

### 9.1. Kết nối mạng an toàn

~~~mermaid
flowchart LR
    USER[Client] --> ALB[ALB]
    ALB --> API[App SG, private subnet]
    API -->|TCP 5432 / 3306| SG[DB Security Group]
    SG --> DB[(Aurora DB cluster private)]
    API -->|AWS API| SEC[Secrets Manager / KMS]
~~~

Với production:

- DB instances thường ở **private subnets**, `PubliclyAccessible=false`.
- DB subnet group nên phủ nhiều AZ phù hợp kiến trúc Aurora.
- DB SG chỉ cho **inbound từ App SG** trên đúng port.
- App SG outbound, NACL và routing phải cho TCP traffic đến DB.
- Nếu app cross-VPC, cần DNS, route, peering/Transit Gateway/private connectivity và SG tương ứng.
- Private app cần gọi Secrets Manager/SSM/KMS có thể cần NAT hoặc VPC endpoints theo dịch vụ.
- Không mở port 3306/5432 ra `0.0.0.0/0` chỉ để xử lý timeout.

### 9.2. IAM role khác database login

**AWS IAM** điều khiển quyền đọc control-plane và lấy secrets như `rds:DescribeDBClusters`, `rds:DescribeDBClusterEndpoints`, `secretsmanager:GetSecretValue`; với IAM DB authentication có `rds-db:connect` theo DB resource/user khi được hỗ trợ.

**Database SQL roles** quyết định `SELECT`/`INSERT`/`UPDATE` trên bảng. Một app IAM role có `rds:DescribeDBClusters` **không tự trở thành** database superuser. DB app_reader chỉ có SELECT **không có** quyền AWS CLI để sửa endpoint.

### 9.3. TLS verification

- Bật TLS/SSL cho client, xác minh DB server certificate và hostname theo RDS CA bundle.
- Aurora PostgreSQL với JDBC có thể dùng `sslmode=verify-full` kèm trust CA configuration.
- Aurora MySQL cần chế độ TLS identity verification theo MySQL Connector/J/AWS JDBC Driver tương ứng.
- Kiểm thử CA rotation, DNS-based endpoints và JDBC driver updates.
- Không tắt certificate hostname verification chỉ để vượt lỗi SSL trong production.

### 9.4. Secret rotation

Nên quản lý credentials qua **Secrets Manager** hoặc secret system của tổ chức:

~~~text
Writer credential -> secret riêng cho write operations
Reader credential -> secret riêng, SQL SELECT-only
DB host -> endpoint DNS không nhạy cảm bằng secret password
~~~

Khi rotate password:

1. Chuẩn bị khả năng refresh credentials trong app/pool;
2. Rotate theo workflow được duyệt, có rollback;
3. Kiểm tra new DB connections có authenticate thành công;
4. Drain/replace stale pooled sessions khi cần;
5. Theo dõi authentication errors và latency;
6. Không log password, token hoặc secret versions vào issue/chat.

Đối với IAM DB auth, kiểm tra hạn token/driver/proxy/certificate support; không giả định mọi engine/version có cùng hành vi.

## 10. Monitoring, HA và cost optimization

### 10.1. Một số CloudWatch metrics

| Metric | Đối tượng | Lý do theo dõi |
|---|---|---|
| `CPUUtilization` | Writer và từng reader | CPU nóng, imbalance |
| `DatabaseConnections` | Từng DB instance | Pool pressure, connection leaks |
| `FreeableMemory` | Từng DB instance | Memory pressure do query/report |
| `AuroraReplicaLag` / các biến thể lag | Reader/cluster theo engine | Stale reads, read throughput pressure |
| `DBLoad` (Database Insights/PI theo hỗ trợ) | DB load | Wait events, top SQL |
| `VolumeBytesUsed` | Cluster | Dung lượng thực dùng |
| `VolumeReadIOPs`/`VolumeWriteIOPs` | Cluster | Storage I/O workload và chi phí |
| `ServerlessDatabaseCapacity`/ACU-related metrics | Serverless v2 khi hỗ trợ | Capacity scale, throttling/cost |
| `FreeLocalStorage` | Instance theo engine/class | Local/temp storage pressure |
| RDS events | Cluster/instance | Failover, maintenance, scaling, errors |

Metric names/availability có thể khác theo Aurora MySQL/PostgreSQL version, Serverless/provisioned, monitoring tier và dimension. Kiểm tra CloudWatch list-metrics trên cluster thực tế trước khi tạo alarms. **Không coi một metric rỗng là không có lỗi**.

### 10.2. Cảnh báo theo workload

- Reader A CPU 90% trong khi B 15% → kiểm tra DNS/pool/queries.
- ReplicaLag tăng sau bulk writes → giảm áp lực đọc hoặc route critical reads về writer.
- Writer DatabaseConnections tăng mạnh sau deployment → kiểm tra Hikari pools và app scale.
- Failover event xảy ra → đo thời gian app recover và số transaction uncertain.
- Custom endpoint mất eligible reader → alert ngay để tránh report pipeline im lặng thất bại.
- New reader thêm vào nhưng không có sessions → xem StaticMembers/ExcludedMembers/DNS caching.

### 10.3. Aurora Auto Scaling vs Serverless v2

| Cơ chế | Điều được thay đổi | Tác động endpoints |
|---|---|---|
| Aurora Replica Auto Scaling | **Số reader instances** | Built-in reader endpoint có thêm readers; custom static list không tự thêm |
| Aurora Serverless v2 | **ACU compute capacity** của instance | Endpoint vẫn chỉ instance đó dù capacity thay |
| Manual resize | Instance class của writer/reader | Có thể gây reboot/gián đoạn; cần maintenance plan |
| RDS Proxy | Pooling/routing giữa clients và instances | Proxy endpoints có lifecycle/quota riêng |

Aurora Auto Scaling có thời gian provisioning/conditions, **không xử lý traffic spike ngay lập tức**. Cân nhắc minimum readers/capacity và giới hạn Aurora Serverless v2 theo engine/version/Region.

### 10.4. Backup/PITR và HA là hai việc khác

Aurora Replicas và ba AZ storage replication giúp **availability/durability**, nhưng **không thay thế backup**. Khi app xóa nhầm dữ liệu, readers cũng nhìn thay đổi ấy.

Cần:

- Automated backups, retention, PITR/snapshots phù hợp;
- Restore test sang cluster riêng;
- RPO/RTO và process recovery được đo thực;
- Encryption/KMS, snapshot sharing restrictions và audit;
- Không xóa production cluster/snapshots khi dọn lab.

### 10.5. Chi phí

| Thành phần | Có thể tăng phí | Cách quản lý |
|---|---|---|
| Writer instance | Compute giờ chạy hoặc ACUs | Right-size, monitor CPU/DBLoad |
| Aurora Replicas | Thêm compute readers | Chỉ tạo đủ read/HA requirements |
| Aurora Standard / I/O-Optimized storage | Storage + I/O theo lựa chọn và pricing | Đo workload và so hai cấu hình |
| RDS Proxy | Proxy capacity/usage pricing | Benchmark lợi ích pool/failover |
| Data transfer | Cross-AZ/cross-Region và egress theo biểu giá | Chọn topology/network phù hợp |
| Backups/snapshots | Retention/storage bổ sung | Lifecycle, không xóa backup cần thiết |
| KMS/Secrets Manager | Keys, secrets và API requests | Cache/rotation phù hợp |
| CloudWatch/Insights | Logs, metrics, DB Insights | Retention, sampling, alert |
| RDS Data API hoặc tính năng bổ sung | API requests theo dịch vụ | Chỉ bật theo nhu cầu |

Tạo **thêm reader để dùng custom endpoint không miễn phí**. Aurora custom endpoint bản thân là cách routing, nhưng compute của readers và services kèm theo vẫn được tính phí. Dùng AWS Pricing Calculator theo Region và engine trước khi chốt kiến trúc.

### 10.6. Backup, global database và DR

Aurora Global Database kết nối những **Aurora clusters tại nhiều Region**, khác với một Aurora cluster có multi-AZ trong **một Region**. Secondary clusters có semantics read/write riêng và khi global failover/switchover, app phải định tuyến đến **primary Region mới**. Không tự giả định cluster writer endpoint trong secondary region sẽ chấp nhận ghi trước khi chuyển vai trò.

Nếu yêu cầu cross-Region DR, cần thiết kế DNS/routing, replica lag global, RPO/RTO và runbook chứ không chỉ tạo thêm custom endpoint.


## 11. Thực hành 1 — Khám phá Aurora cluster bằng AWS CLI (chỉ đọc)

> **Phần bắt buộc của lab không thay đổi tài nguyên AWS.** Sử dụng AWS CLI v2 trên CloudShell hoặc máy đã có IAM credentials cho tài khoản sandbox. Cần các quyền đọc như `rds:DescribeDBClusters`, `rds:DescribeDBInstances`, `rds:DescribeDBClusterEndpoints`, `rds:DescribeEvents` và `cloudwatch:GetMetricStatistics` khi thực hiện tương ứng. Không gọi `Create`/`Modify`/`Failover` trên production và không đọc database customer data.

### 11.1. Kiểm tra danh tính và Region

Ví dụ Bash:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

REGION=ap-southeast-1
aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

Nếu dùng AWS CloudShell đã có session credentials nhưng không có profile `aws-lab-dev`, bỏ biến `AWS_PROFILE` và tham số `--profile` theo trường hợp thực. Kiểm tra Account/Arn để tránh truy vấn sai tài khoản.

### 11.2. Liệt kê Aurora DB clusters

~~~bash
aws rds describe-db-clusters \
  --region "$REGION" \
  --query "DBClusters[?Engine=='aurora-mysql' || Engine=='aurora-postgresql'].{Id:DBClusterIdentifier,Engine:Engine,Version:EngineVersion,Status:Status}" \
  --output table
~~~

Kết quả có thể trống nếu chưa có cluster sandbox, Region không đúng hoặc quyền bị giới hạn. **Không tạo Aurora chỉ để vượt bài lab**, vì compute/storage có chi phí kể cả chưa phát traffic.

### 11.3. Đọc cluster topology

Chỉ định cluster **được phép xem**:

~~~bash
CLUSTER=course-aurora-sandbox

aws rds describe-db-clusters \
  --db-cluster-identifier "$CLUSTER" \
  --region "$REGION" \
  --query 'DBClusters[].{Cluster:DBClusterIdentifier,Engine:Engine,EngineVersion:EngineVersion,Status:Status,WriterEndpoint:Endpoint,ReaderEndpoint:ReaderEndpoint,Port:Port,Members:DBClusterMembers}' \
  --output json
~~~

Trong `DBClusterMembers`, kiểm tra:

- `DBInstanceIdentifier`: tên từng instance;
- `IsClusterWriter`: `true` cho writer hiện tại;
- `PromotionTier`: ưu tiên failover reader;
- Đếm số readers thực tế, không chỉ nhìn tồn tại `ReaderEndpoint`.

**Ví dụ diễn giải:** một cluster có 3 members, một phần tử `IsClusterWriter=true` và hai phần tử `false` nghĩa là có một writer và hai Aurora Replicas (khi cluster ở trạng thái thông thường). Cần kiểm tra trạng thái từng instance trước khi coi cả hai readers đang phục vụ.

### 11.4. Đọc một DB instance

Lấy `DBInstanceIdentifier` từ `DBClusterMembers`, ví dụ `course-reader-a`:

~~~bash
INSTANCE=course-reader-a

aws rds describe-db-instances \
  --db-instance-identifier "$INSTANCE" \
  --region "$REGION" \
  --query 'DBInstances[].{Id:DBInstanceIdentifier,Cluster:DBClusterIdentifier,Status:DBInstanceStatus,Class:DBInstanceClass,AZ:AvailabilityZone,Endpoint:Endpoint.Address,Port:Endpoint.Port,PromotionTier:PromotionTier,PubliclyAccessible:PubliclyAccessible}' \
  --output json
~~~

`Endpoint.Address` ở đây là **instance endpoint**. `PromotionTier` không đủ để tự xác định writer/reader role — hãy đối chiếu với `IsClusterWriter` ở cluster. `PubliclyAccessible=true` cần được rà soát với network/security architecture; không tự thay cấu hình.

### 11.5. Quan sát tất cả endpoints

~~~bash
aws rds describe-db-cluster-endpoints \
  --db-cluster-identifier "$CLUSTER" \
  --region "$REGION" \
  --query 'DBClusterEndpoints[].{Id:DBClusterEndpointIdentifier,Endpoint:Endpoint,Type:EndpointType,CustomType:CustomEndpointType,Status:Status,StaticMembers:StaticMembers,ExcludedMembers:ExcludedMembers}' \
  --output json
~~~

Đây là câu lệnh quan trọng nhất của bài.

| Trường kết quả | Cách đọc |
|---|---|
| `EndpointType=WRITER` | Built-in cluster/writer endpoint |
| `EndpointType=READER` | Built-in reader endpoint |
| `EndpointType=CUSTOM` | Endpoint do người dùng tạo |
| `CustomEndpointType=READER` | Custom chỉ chọn reader eligible |
| `CustomEndpointType=ANY` | Có thể bao gồm writer và readers |
| `StaticMembers` không rỗng | Chọn các instances được liệt kê, không auto thêm reader mới |
| `ExcludedMembers` không rỗng | Loại các instances đó, new eligible readers có thể tự vào |
| `Status=available` | Endpoint về trạng thái sẵn sàng, nhưng vẫn phải kiểm tra target instance/network |

**Cẩn trọng:** `EndpointType=READER` trên built-in endpoint **khác** `CustomEndpointType=READER` ở custom endpoint. Cần phân biệt hai trường trong JSON output.

### 11.6. Đọc RDS events liên quan tới cluster

~~~bash
aws rds describe-events \
  --source-type db-cluster \
  --source-identifier "$CLUSTER" \
  --duration 1440 \
  --region "$REGION" \
  --query 'Events[].{Time:Date,Category:EventCategories,Message:Message}' \
  --output table
~~~

RDS events có thể cho biết failover, maintenance hoặc thay đổi topology. `--duration 1440` chỉ minh họa lấy khoảng thời gian tối đa 24 giờ theo khả năng API; sự kiện cũ ngoài retention sẽ không xuất hiện. Event message có thể chứa resource metadata, không dán raw output ra kênh công khai.

### 11.7. Xem CloudWatch ReplicaLag

Nếu reader `course-reader-a` có metric tương ứng:

~~~bash
READER_ID=course-reader-a
START_UTC=$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)
END_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name AuroraReplicaLag \
  --dimensions "Name=DBInstanceIdentifier,Value=$READER_ID" \
  --start-time "$START_UTC" \
  --end-time "$END_UTC" \
  --period 300 \
  --statistics Average Maximum \
  --region "$REGION" \
  --output json
~~~

Tùy engine/version và metric dimensions, `AuroraReplicaLag` có thể khác hoặc không xuất hiện. Hãy kiểm tra `cloudwatch list-metrics --namespace AWS/RDS` trước khi kết luận. Trên PowerShell/Windows, cú pháp `date -d` không hoạt động; dùng PowerShell `Get-Date` tạo timestamps ISO UTC thay thế.

### 11.8. Bảng tổng hợp lab

| Nội dung kiểm tra | Kết quả thực tế | Ý nghĩa |
|---|---|---|
| Cluster engine/version | ... | Chọn đúng JDBC driver/SQL |
| Writer identifier/AZ | ... | Nơi giao dịch có ghi chạy |
| Số readers và AZs | ... | Read capacity/HA |
| Reader endpoint hostname | ... | Hướng new connections đọc |
| Custom endpoint type | ... | READER hay ANY? |
| StaticMembers/ExcludedMembers | ... | Autoscaling membership có động không? |
| Reader DatabaseConnections | ... | Pool có phân bổ đều? |
| ReplicaLag | ... | Có stale read risk? |
| RDS events | ... | Có maintenance/failover gần đây? |
| DB instance publicly accessible | ... | Có phù hợp security policy? |

**Kết quả mong đợi:** bạn xác định được writer hiện tại, số reader thực, endpoint nào là built-in/custom, custom nào dùng static/exclusion list và có thể chỉ ra rủi ro khi đọc báo cáo qua reader endpoint chung.

## 12. Thực hành 2 — Đọc vai trò SQL từ endpoint (tùy chọn)

> Chỉ chạy trên database sandbox của chính bạn nếu có credentials/SQL grants hợp lệ. Cần đi qua VPC/private network phù hợp, TLS được xác minh, không sử dụng tài khoản dữ liệu thật. Đây là **SQL read-only introspection**, không tạo hoặc sửa bảng.

### 12.1. Aurora PostgreSQL

Nếu dùng `psql`, sau khi thiết lập CA file đúng:

~~~bash
# Chỉ dùng database sandbox. Không đặt password trực tiếp vào command.
psql "host=$DB_READER_HOST port=5432 dbname=appdb user=app_reader sslmode=verify-full sslrootcert=/path/to/rds-ca-bundle.pem" \
  -c "SHOW transaction_read_only;"
~~~

Kết quả `on` thường gợi ý session đang ở chế độ read-only. Kiểm tra `current_user` hoặc một query nhẹ không đụng PII để xác minh database role, nhưng **không tạo DML** để “thử quyền” trên dữ liệu thật.

Nếu đang kết nối writer bằng user chỉ đọc, `SHOW transaction_read_only` có thể không phản ánh toàn bộ SQL GRANT của user. Đừng hiểu `off` là user được tự do ghi mọi bảng.

### 12.2. Aurora MySQL

Kiểm tra biến instance/read-only semantics theo engine/version:

~~~sql
SHOW VARIABLES LIKE 'innodb_read_only';
SELECT @@hostname;
~~~

Đây là **ví dụ kiểm tra không đổi dữ liệu**. Kết quả có thể khác qua engine version hoặc chức năng Aurora; không hard-code tên host/IP từ query vào app connection string.

### 12.3. Không thử failover trên production

Một số lab trên Internet khuyến nghị gọi `aws rds failover-db-cluster` để xem DNS đổi. Lệnh đó **có tác động lớn** và có thể gây gián đoạn các transactions. Bài này **không yêu cầu** chạy failover thực tế. Để kiểm thử fault recovery phải dùng sandbox có approval, backup, maintenance window phù hợp, giám sát và stakeholder ownership.

## 13. Thực hành 3 — Ví dụ custom endpoint có kiểm soát

> Các lệnh trong mục này chỉ là **tài liệu tham khảo**, không chạy mặc định. Chúng **tạo/sửa/xóa RDS resources**, có thể ảnh hưởng kết nối đang vận hành. Chỉ dùng cluster sandbox được phê duyệt và có rollback plan. Cần kiểm tra engine, Region, membership, quota tối đa 5 custom endpoints và IAM.

### 13.1. READER custom endpoint với static list

~~~bash
# CÓ TÁC ĐỘNG - CHỈ MINH HỌA SANDBOX
aws rds create-db-cluster-endpoint \
  --db-cluster-identifier course-aurora-sandbox \
  --db-cluster-endpoint-identifier course-report-readers \
  --endpoint-type READER \
  --static-members course-reader-report-1 course-reader-report-2 \
  --region ap-southeast-1
~~~

Sau khi tạo, đọc lại `describe-db-cluster-endpoints` và xác nhận:

~~~text
EndpointType = CUSTOM
CustomEndpointType = READER
StaticMembers = [course-reader-report-1, course-reader-report-2]
Status = available sau khi provision xong
~~~

**Không coi type ANY được tạo trong Console là tương đương** với READER. Phải xem `CustomEndpointType` ở API.

### 13.2. READER custom endpoint với exclusion list

Nếu muốn custom group tự đón nhận new readers nhưng loại trừ report reader:

~~~bash
# CÓ TÁC ĐỘNG - ví dụ thay thế static-list, không phải chạy đồng thời.
aws rds create-db-cluster-endpoint \
  --db-cluster-identifier course-aurora-sandbox \
  --db-cluster-endpoint-identifier course-interactive-readers \
  --endpoint-type READER \
  --excluded-members course-reader-report-1 \
  --region ap-southeast-1
~~~

Khi AWS Auto Scaling thêm reader mới, endpoint exclusion-list có thể thêm reader hợp lệ đó; custom static-list không tự làm vậy. Cần giám sát để đảm bảo instance mới có cấu hình phù hợp workload.

### 13.3. Sửa membership

~~~bash
# CÓ TÁC ĐỘNG - chỉ trên custom endpoint sandbox
aws rds modify-db-cluster-endpoint \
  --db-cluster-endpoint-identifier course-report-readers \
  --static-members course-reader-report-1 course-reader-report-3 \
  --region ap-southeast-1
~~~

Các connections đã mở đến member bị loại **không tự động bị cắt chỉ vì đổi membership**. New connections sẽ tuân theo membership mới khi thay đổi có hiệu lực; ứng dụng cần xử lý pool lifecycle và tránh kết luận chỉ từ DNS cache cũ.

### 13.4. Xóa custom endpoint

~~~bash
# CÓ TÁC ĐỘNG - chỉ khi xác nhận không client nào còn dùng
aws rds delete-db-cluster-endpoint \
  --db-cluster-endpoint-identifier course-report-readers \
  --region ap-southeast-1
~~~

**Không xóa built-in writer/reader endpoint**, và không xóa custom endpoint production khi chưa cập nhật các clients đang dùng. Xóa endpoint có thể khiến các new connections thất bại; phải chuyển connection strings trước và có thời gian drain.

### 13.5. Change review tối thiểu

~~~text
1. Check đúng account, Region, cluster và endpoint identifier.
2. Đọc role + AZ + class + metrics của mọi members.
3. Xác định READER hay ANY và static/excluded.
4. So sánh capacity nhóm mới với expected workload.
5. Review migration of application connection strings.
6. Áp dụng sandbox, test read-only credential và query latency.
7. Triển khai staged rollout và quan sát DNS/pools.
8. Có rollback plan, không xóa endpoint cũ quá sớm.
~~~

## 14. Kịch bản thiết kế: nền tảng đặt khóa học

### 14.1. Yêu cầu

Một nền tảng Java/Spring Boot phục vụ:

- 2.000 requests/giây vào giờ mở đăng ký;
- Ghi/đổi trạng thái enrollment, payments và audit;
- Catalog course được đọc rất nhiều, chấp nhận trễ 100–300 ms trong một số màn hình;
- BI chạy reports 10–20 phút mỗi giờ;
- Không cho BI ảnh hưởng write latency;
- Đòi transaction read-your-writes với thanh toán;
- Có yêu cầu HA nhiều AZ, database private và chi phí có giới hạn;
- Muốn scale read API tự động nhưng report readers chỉ được dùng instances mạnh.

### 14.2. Sơ đồ đề xuất

~~~mermaid
flowchart LR
    API[Spring Boot API] --> WR[Writer pool]
    API --> IR[Interactive reader pool]
    BI[BI/report workers] --> RP[Reporting reader pool]
    WR --> WEP[Cluster writer endpoint]
    IR --> C1[Custom READER endpoint interactive]
    RP --> C2[Custom READER endpoint reporting]
    WEP --> W[Writer - AZ A]
    C1 --> R1[Reader A - AZ B]
    C1 --> R2[Reader B - AZ C]
    C2 --> R3[High-memory reader - AZ C]
    W --> S[(Shared Aurora storage)]
    R1 --> S
    R2 --> S
    R3 --> S
~~~

| Workload | Endpoint | SQL user | Đặc điểm |
|---|---|---|---|
| Ghi enrollment/payment | Cluster writer | App writer, limited DML | Transaction và read-after-write |
| Đọc catalog | Custom interactive READER | App reader, SELECT-only | Exclusion list để nhận new autoscaling readers |
| BI reports | Custom reporting READER | Reporting reader, SELECT-only | Static list các readers mạnh |
| DB schema migration | Writer | Migration role có quyền rõ ràng | Change window/audit |
| Diagnostics reader | Instance endpoint | Admin readonly | Kiểm tra từng replica |
| Traffic burst từ nhiều functions | RDS Proxy theo nhu cầu | IAM/Secrets Manager + DB grants | Pooling và failover |

### 14.3. Vì sao không chỉ dùng reader endpoint?

Reader endpoint mặc định cân bằng new connections giữa **mọi Aurora Replicas đủ điều kiện**. Report query nặng có thể vào reader nhỏ dành cho API; còn API có thể vào reporting reader mạnh. Custom endpoints cho phép **chia các pools theo mục đích**. Tuy nhiên ngay cả custom reader nhóm API cũng không tự cân bằng CPU/query; app pooling và monitoring vẫn quan trọng.

### 14.4. Xử lý read-your-writes

Luồng thanh toán:

~~~text
1. Receive payment callback và xác minh provider signature.
2. Ghi payment status + enrollment state qua writer.
3. COMMIT transaction và ghi audit/idempotency key.
4. Trả trạng thái vừa commit hoặc đọc lại bằng writer.
5. Bất đồng bộ cập nhật cache/search/reporting qua event.
6. UI catalog khác có thể dùng reader và chấp nhận lag.
~~~

Không dùng read-only JdbcTemplate để quyết định payment có commit hay chưa ngay sau bước 3, nếu nghiệp vụ đòi đọc thấy giá trị tức thời.

### 14.5. Phương án failover

- Writer AZ A bị lỗi; Aurora promote reader AZ B hoặc AZ C theo promotion tier/availability.
- App writer pool loại stale connections và resolve lại **cluster endpoint**.
- Interactive/reporting custom **READER type** loại writer mới khỏi eligible set.
- Nếu reporting group chỉ có một reader và bị promote, report pipeline có thể thiếu target: cần **fallback rõ ràng** hoặc scale thêm reader.
- Transaction outcomes chưa xác định phải đối soát bằng idempotency key, không retry mù.
- Alert RDS events, DBConnections, Error rates, ReplicaLag và recovery time.

## 15. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| App ghi qua reader endpoint bị `read-only` error | Có reader thật và SQL writer dùng nhầm URL | Dùng cluster writer endpoint cho DML |
| Reader endpoint đôi lúc cho phép ghi | Cluster chỉ có writer hoặc không còn healthy readers | Kiểm tra DBClusterMembers, DB roles; dùng SELECT-only account |
| Dữ liệu vừa ghi chưa xuất hiện ở màn hình | Replica lag/read-after-write | Đọc qua writer cho critical path, đo lag |
| Reader A CPU cao, reader B thấp | DNS cache/pool stickiness/long queries | Connection targets, pool age, query profile |
| Tạo reader mới nhưng custom endpoint không dùng | StaticMembers không tự thêm | Chuyển sang exclusion list hoặc update static |
| Custom READER không kết nối sau failover | Reader bị promote, không còn eligible member | Endpoint membership/cluster roles, availability |
| Custom ANY đôi khi ghi lỗi | Chọn trúng read-only replica | Dùng writer endpoint hoặc custom READER cho SELECT |
| Console custom endpoint bất ngờ ANY | Console không chọn READER type | Dùng CLI/API hỗ trợ; kiểm tra CustomEndpointType |
| Connection vẫn đến removed member | Connection đã mở còn tồn tại hoặc DNS/pool cache | Drain sessions, lifecycle, TTL |
| Stale IP sau failover | DNS cache quá lâu, old pool connections | TTL dưới 30 giây theo AWS guidance, reconnect |
| Writer endpoint không thể kết nối | SG/NACL/DNS/port/engine status | SG source, network path, events |
| Error `too many connections` | Tổng các app pools quá lớn | DatabaseConnections, maxPoolSize, RDS Proxy |
| RDS Proxy reader endpoint lỗi nhưng built-in vẫn kết nối | Proxy read-only không có readers | Kiểm tra available readers và proxy target health |
| `SSL certificate verify failed` | CA bundle/hostname/driver mismatch | RDS CA, TLS mode, certificate rotation |
| DB authentication thất bại sau rotation | Pool giữ credentials cũ | Secret refresh, new connections, key policy |
| Failover nhưng transaction bị nhân đôi | Retry không idempotent | Business operation ID, reconciliation |
| Báo cáo làm chậm writer | BI đi nhầm writer hoặc ANY custom | Read pool route, role/SQL, DBLoad |
| Storage tăng phí ngoài dự kiến | Data/I/O/backup retention | Cost Explorer, metrics, I/O-Optimized comparison |
| Cluster có reader nhưng không HA tốt | Readers cùng AZ hoặc capacity quá nhỏ | AZ placement, failover tier, load test |
| Read SQL bị permission denied | DB reader user thiếu GRANT | SQL role/schema/table grants |
| CloudWatch metric trống | Sai engine/dimension/Region hoặc chưa xuất datapoints | list-metrics, RDS metrics docs |

### 15.1. Runbook 10 bước

~~~text
1. Xác nhận account, Region, cluster ID và engine/version.
2. Đọc DBClusterMembers, IsClusterWriter, AZ, status.
3. Đọc EndpointType/CustomEndpointType, StaticMembers/ExcludedMembers.
4. Kiểm tra app connection string dùng đúng writer/reader/custom.
5. Đọc events, CPU, DBLoad, DatabaseConnections và ReplicaLag.
6. Kiểm tra DNS TTL, JDBC pool, stale connections và RDS Proxy.
7. Kiểm tra SG, port, routing, TLS và Secrets Manager.
8. Với transaction lỗi, xác minh outcome và idempotency.
9. Sửa đúng lớp lỗi, thử sandbox/staging với negative cases.
10. Quan sát, có rollback và ghi audit/change record.
~~~

## 16. Câu hỏi tự kiểm tra

1. Aurora DB cluster khác DB instance ở điểm gì?
2. Shared cluster volume có vai trò nào đối với HA và reader scaling?
3. Có thể có nhiều writers trong một Aurora cluster thông thường không?
4. Reader endpoint phân phối **query** hay **connection**?
5. Nếu Aurora cluster không có healthy reader, built-in reader endpoint có thể trỏ đến đâu?
6. Vì sao không dùng reader endpoint như cách bắt buộc user chỉ được SELECT?
7. Instance endpoint có còn trỏ cùng instance sau failover không? Role có thể thay đổi không?
8. Custom endpoint giải quyết vấn đề gì so với built-in reader endpoint?
9. `CustomEndpointType=READER` khác `ANY` như thế nào?
10. Tạo custom endpoint qua AWS Console hiện thường có type nào?
11. StaticMembers khác ExcludedMembers đối với autoscaling readers ra sao?
12. Với custom READER, khi member được promote thành writer, kết nối mới có tiếp tục chọn member đó không?
13. Có nên dùng ANY custom endpoint làm writer endpoint không?
14. Tại sao một Hikari pool có thể dồn phần lớn load lên một reader?
15. AWS khuyến nghị mức DNS TTL nào nếu app có cache DNS?
16. Replica lag có thể khiến read-after-write gây lỗi nghiệp vụ nào?
17. Spring `@Transactional(readOnly=true)` có tự chuyển JDBC về Aurora reader không?
18. Tại sao phải tách DB roles writer và reader?
19. Promotion tier 0 hay 15 được ưu tiên khi failover?
20. Aurora Auto Scaling khác Aurora Serverless v2 thế nào?
21. RDS Proxy reader endpoint hoạt động thế nào nếu cluster không còn readers?
22. Vì sao có reader replicas không đồng nghĩa có backup độc lập?
23. Các API nào dùng để xem cluster topology/custom endpoints mà không thay đổi chúng?
24. Khi writer failover, vì sao cần idempotency ngoài việc reconnect?
25. Nếu BI query quá nặng dù có custom endpoint, cần thêm biện pháp gì?

### 16.1. Gợi ý đáp án

1. Cluster gồm storage logic, instances, cấu hình và endpoints; instance là một compute node.
2. Storage được tách khỏi compute, shared trong cluster; readers không cần mỗi bên copy thủ công EBS dataset.
3. Một writer trong single-writer cluster thông thường.
4. **Connection mới**, không query.
5. **Writer**.
6. Endpoint là routing; cần SQL GRANT SELECT-only.
7. Instance endpoint vẫn trỏ instance; instance có thể đổi writer/reader role.
8. Chọn subset instances cho từng workload/capacity.
9. READER loại writer; ANY có thể chứa writer và readers.
10. **ANY** theo tài liệu Console hiện hành.
11. Static không tự thêm new readers; excluded tự nhận eligible readers không bị loại.
12. Không, type READER cập nhật eligibility theo role.
13. Không; một kết nối có thể tới read-only replica.
14. DNS cache lâu, connections sticky, query cost không đều.
15. **Dưới 30 giây** theo Aurora best practices.
16. UI báo chưa thanh toán dù transaction đã commit; quyền hoặc ghi tiếp có thể sai.
17. Không; cần explicit datasource routing/config.
18. Defense-in-depth khi read endpoint fallback writer.
19. **0** cao hơn.
20. Auto Scaling điều chỉnh số readers; Serverless v2 điều chỉnh ACUs của instance.
21. Có thể đợi và fail, không giống Aurora reader fallback writer.
22. Xóa nhầm dữ liệu vẫn được phản ánh trong shared cluster; phải có snapshots/PITR.
23. `describe-db-clusters`, `describe-db-instances`, `describe-db-cluster-endpoints`.
24. Một transaction có thể commit rồi mất ack; retry mù nhân đôi side effects.
25. Giới hạn SQL, sizing, query optimization, resource isolation, monitoring và workload scheduling.

## 17. Checklist trước khi triển khai production

### Cluster và endpoints

- [ ] DB cluster, writer/reader instances, AZ distribution và engine/version đã được xác minh.
- [ ] Có ít nhất một reader khác AZ nếu HA yêu cầu; promotion tiers phù hợp capacity.
- [ ] App writes/DDL dùng **cluster writer endpoint**.
- [ ] Read workloads biết rõ replica lag và read-after-write contract.
- [ ] Không dùng reader endpoint thay cho DB SELECT-only permissions.
- [ ] Custom endpoint type **READER/ANY** được chọn đúng mục đích.
- [ ] StaticMembers/ExcludedMembers có owner và tương thích Auto Scaling.
- [ ] Không vượt custom endpoint quota và có phương án thiếu eligible member.
- [ ] Instance endpoint chỉ dùng khi chủ động cần đúng instance.

### Ứng dụng và mạng

- [ ] JDBC pools tách writer/reader, sizing theo tổng replicas/app instances.
- [ ] DNS cache TTL, reconnect/validation và failover được kiểm thử.
- [ ] Transactions có idempotency/reconciliation, không retry mù.
- [ ] App SG → DB SG đúng port, DB private subnets, không public access tùy tiện.
- [ ] TLS certificate/hostname verification hoạt động; driver và CA bundle đúng.
- [ ] DB credentials quản lý qua Secrets Manager/role phù hợp, có rotation runbook.
- [ ] IAM control-plane và SQL privileges được quản trị độc lập.
- [ ] RDS Proxy nếu dùng đã được benchmark cả connection pooling và chi phí.

### Observability, DR và cost

- [ ] Alarms CPU, DatabaseConnections, ReplicaLag, DBLoad và failover events.
- [ ] Có số liệu actual connection distribution tới từng reader.
- [ ] Có load test báo cáo nặng, writer failover và custom membership changes.
- [ ] Có backup, PITR và test restore theo RPO/RTO.
- [ ] Có kế hoạch Region/global recovery riêng nếu nghiệp vụ yêu cầu.
- [ ] Đã so chi phí reader instances, storage/I/O, RDS Proxy, Secrets Manager, KMS và logs.
- [ ] Có budget, tagging, review/change approval và dọn resources sandbox đúng ownership.

**Kết quả mong đợi:** Bạn biết chọn đúng Aurora endpoint cho từng nghiệp vụ, hiểu vì sao reader endpoint chỉ phân phối kết nối và không phải công cụ phân quyền; xây custom endpoint READER/ANY với membership phù hợp; đồng thời có kế hoạch read consistency, failover, bảo mật, giám sát và chi phí.

## Tài liệu AWS chính thức

- [Amazon Aurora overview](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/CHAP_AuroraOverview.html)
- [Amazon Aurora endpoint connections](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.Endpoints.html)
- [Aurora cluster/writer endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoints.Cluster.html)
- [Aurora reader endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoints.Reader.html)
- [Aurora instance endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoints.Instance.html)
- [Aurora custom endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoints.Custom.html)
- [Custom endpoint considerations, membership and type](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoints.Custom.Considerations.html)
- [Creating Aurora custom endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-custom-endpoint-creating.html)
- [Editing custom endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-endpoint-editing.html)
- [Viewing Aurora endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-endpoint-viewing.html)
- [CLI tutorial for custom endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoint.Tutorial.html)
- [Aurora storage](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.StorageReliability.html)
- [Aurora replication](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Replication.html)
- [High availability and failover](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.AuroraHighAvailability.html)
- [Aurora failover procedure](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-failover.html)
- [Aurora Auto Scaling replicas](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Integrating.AutoScaling.html)
- [Amazon Aurora best practices including DNS TTL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.BestPractices.html)
- [RDS Proxy endpoints for Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/rds-proxy-endpoints.html)
- [Using RDS Proxy with Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/rds-proxy.html)
- [AWS CLI describe-db-cluster-endpoints](https://docs.aws.amazon.com/cli/latest/reference/rds/describe-db-cluster-endpoints.html)
- [Aurora pricing](https://aws.amazon.com/rds/aurora/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Lưu ý áp dụng:** Tất cả DB cluster names, AWS account IDs, ARNs, hostnames, user names, SQL và IAM examples trong bài là **dữ liệu đào tạo giả định**. Tính năng, endpoint behavior, quotas, engine compatibility và giá AWS có thể thay đổi theo Region/engine version. Trước khi triển khai hoặc thay đổi production, xác minh tài liệu AWS hiện hành, kiểm thử trong sandbox, bảo vệ dữ liệu và thực hiện theo quy trình phê duyệt thay đổi.
