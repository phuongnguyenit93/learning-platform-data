# Mở rộng kết nối và sử dụng connection pool hoặc proxy

## Mục tiêu học tập

Trong kiến trúc ứng dụng cloud, tăng số instance ứng dụng không tự động làm database xử lý nhanh hơn. Mỗi instance có thể mở nhiều kết nối đồng thời; khi autoscaling, rolling deployment hoặc traffic burst xảy ra, tổng connection có thể tăng đột biến và vượt khả năng của database. Ngay cả khi database còn CPU, chi phí tạo kết nối, xác thực, TLS, memory cho session và tranh chấp tài nguyên vẫn có thể làm hệ thống chậm hoặc từ chối request.

**Connection pooling** tái sử dụng các kết nối đã mở để giảm chi phí thiết lập và giới hạn số kết nối đồng thời. **Database proxy** tạo một lớp trung gian quản lý hoặc phân phối kết nối giữa ứng dụng và database, có thể hỗ trợ pooling tập trung, failover, routing hoặc xác thực tùy sản phẩm. Hai kỹ thuật có liên quan nhưng không đồng nghĩa: pool thường nằm trong process ứng dụng, proxy nằm trên đường mạng và có thể quản lý kết nối cho nhiều client.

Bài học thuộc chương **Kiến trúc cơ sở dữ liệu**, tập trung vào mở rộng kết nối và sử dụng connection pool hoặc proxy. Nội dung kết hợp yêu cầu thiết kế ứng dụng cloud từ nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai; trọng tâm là đánh đổi giữa độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo Well-Architected.

Sau bài học, bạn có thể:

- Giải thích vì sao số lượng connection là tài nguyên hữu hạn của database.
- Ước lượng nhu cầu kết nối từ số instance, pool size, concurrency và workload.
- Phân biệt application-side pool, server-side pool và database proxy.
- Chọn pool size, timeout, lifetime, validation và leak detection có căn cứ.
- Thiết kế cho autoscaling, rolling deployment, failover và connection storm.
- Nhận diện ảnh hưởng của transaction, session state, prepared statement và pooling mode.
- Bảo vệ kết nối bằng TLS, IAM, secret rotation, network segmentation và least privilege.
- Quan sát pool saturation, wait time, database session, query latency và lỗi kết nối.
- So sánh TCO giữa kết nối trực tiếp, pool trong ứng dụng và proxy managed.
- Xây dựng kịch bản kiểm thử và quyết định kiến trúc phù hợp quy mô hệ thống.

## 1. Vì sao database connection cần được quản lý?

Một connection database không chỉ là socket TCP. Tùy database và giao thức, mỗi session có thể cần bộ nhớ, cấu trúc quản lý transaction, trạng thái xác thực, buffer, backend process hoặc worker, metadata và tài nguyên theo dõi. Mở connection mới cũng có chi phí DNS, TCP handshake, TLS handshake, xác thực và khởi tạo session.

Giả sử nền tảng đặt phòng chạy 20 instance ứng dụng. Mỗi instance có pool tối đa 30 connection. Nếu mọi pool cùng đạt cực đại, ứng dụng có thể giữ tới:

~~~text
20 instances × 30 connections = 600 connections
~~~

Nếu database chỉ dành 400 connection cho workload ứng dụng, cấu hình này đã vượt ngân sách trước khi tính scheduler, worker, công cụ quản trị, migration hoặc service khác. Nếu autoscaling tăng lên 40 instance, tổng pool tối đa có thể thành 1.200.

Database có thể từ chối kết nối mới, khiến request chờ pool, timeout hoặc lỗi ngay tại bước lấy connection. Tăng số instance trong tình huống này có thể làm sự cố nặng hơn vì mỗi instance mới lại tạo thêm pool.

### 1.1. Connection count không phải throughput

Có nhiều connection hơn không luôn giúp xử lý nhiều query hơn. Khi số session quá lớn:

- Database dành thêm memory và CPU cho quản lý session.
- Context switching, lock contention và transaction chờ nhau tăng.
- Cache locality có thể giảm; working set bị phân tán.
- CPU hoặc disk đã bão hòa thì thêm connection chỉ tăng hàng đợi.
- Nhiều transaction mở lâu giữ lock hoặc phiên bản dữ liệu, làm cleanup khó hơn tùy engine.

Mục tiêu là giữ số connection ở mức database xử lý hiệu quả, đồng thời cho phép ứng dụng có đủ concurrency và thời gian chờ nằm trong SLO.

### 1.2. Phân biệt các loại kết nối

| Loại kết nối | Ai sử dụng | Mục đích |
| --- | --- | --- |
| Client-to-application | Web/mobile tới API | Tiếp nhận request người dùng |
| Application-to-database | API/worker tới DB hoặc proxy | Đọc và ghi dữ liệu |
| Proxy-to-database | Proxy tới DB | Duy trì backend session phục vụ client |
| Admin connection | DBA, migration, monitoring | Quản trị, thay đổi schema, điều tra |
| Replication connection | DB primary tới replica/standby | Đồng bộ dữ liệu và failover |

Khi tính connection budget, không chỉ nhìn pool API chính. Worker nền, consumer queue, cron job, reporting service và deployment cũ có thể cùng kết nối database.

## 2. Connection pooling là gì?

Connection pool là tập kết nối database được tạo trước hoặc tạo theo nhu cầu, rồi tái sử dụng cho nhiều thao tác. Thay vì mỗi HTTP request mở rồi đóng TCP/TLS/database session, ứng dụng mượn connection từ pool, thực hiện transaction/query và trả connection về pool.

~~~mermaid
flowchart TB
    R1["HTTP request 1"] --> A["Application"]
    R2["HTTP request 2"] --> A
    R3["Worker job"] --> A
    A --> POOL["Connection pool"]
    POOL --> C1["DB connection 1"]
    POOL --> C2["DB connection 2"]
    POOL --> C3["DB connection 3"]
    C1 --> DB[("Database")]
    C2 --> DB
    C3 --> DB
~~~

Pool thường có các khái niệm:

- **Maximum pool size:** số connection tối đa pool giữ.
- **Minimum idle:** số connection rảnh tối thiểu muốn duy trì.
- **Idle connection:** connection đang rảnh và sẵn sàng được mượn.
- **Active/borrowed connection:** connection đang được một thao tác sử dụng.
- **Connection acquisition timeout:** thời gian tối đa chờ mượn connection.
- **Idle timeout:** thời gian connection rảnh trước khi bị đóng.
- **Max lifetime:** tuổi thọ tối đa trước khi pool thay thế connection.
- **Validation/keepalive:** cơ chế kiểm tra hoặc duy trì connection sống.
- **Leak detection:** cảnh báo khi connection bị giữ lâu bất thường.

Tên cấu hình và semantics cụ thể tùy thư viện. Phải đọc tài liệu của pool và driver đang sử dụng.

### 2.1. Vòng đời một connection trong pool

1. Pool khởi tạo hoặc tạo connection khi cần.
2. Ứng dụng yêu cầu connection.
3. Nếu có connection idle, pool cấp phát.
4. Nếu chưa có và chưa đạt giới hạn, pool có thể tạo thêm.
5. Nếu đã đạt giới hạn, caller chờ tới khi connection được trả lại hoặc timeout.
6. Khi ứng dụng đóng logical connection, pool thường trả connection về pool thay vì đóng socket vật lý.
7. Pool có thể kiểm tra, làm sạch session state hoặc loại connection lỗi trước lần mượn tiếp theo.

Với Java JDBC, gọi close trên proxy connection thường có nghĩa trả connection về pool. Vì vậy phải luôn đóng resource bằng try-with-resources; không giữ connection trong field hoặc qua nhiều request.

### 2.2. Pool không tự làm query nhanh hơn

Pool giảm chi phí tạo kết nối và kiểm soát concurrency. Nó không sửa query thiếu index, transaction dài, lock contention hoặc database thiếu CPU/IO. Nếu pool quá nhỏ, request chờ lâu. Nếu quá lớn, database chịu quá nhiều session. Pool size cần dựa trên benchmark và connection budget toàn hệ thống.

## 3. Các mô hình pooling phổ biến

### 3.1. Pool nằm trong ứng dụng

Mỗi ứng dụng hoặc process có pool riêng. Ví dụ mỗi Spring Boot instance chạy HikariCP. Đây là mô hình phổ biến vì đơn giản, ít thêm hop mạng và pool phối hợp trực tiếp với thread/application lifecycle.

Ưu điểm: ít thành phần hạ tầng; ứng dụng kiểm soát pool size và timeout; tận dụng transaction/session semantics của driver; không cần proxy riêng.

Giới hạn: mỗi instance có pool riêng, tổng connection tăng theo số replica; autoscaling làm connection count thay đổi mạnh; nhiều ứng dụng phải tự phối hợp DB budget; function/serverless scale theo invocation có thể tạo lượng client connection lớn.

### 3.2. Pool ở proxy hoặc middleware

Proxy đứng giữa ứng dụng và database. Ứng dụng kết nối đến proxy; proxy duy trì backend connection tới database và có thể multiplex các client tùy cơ chế.

~~~mermaid
flowchart LR
    APP1["API instances"] --> P["Database proxy"]
    APP2["Worker instances"] --> P
    APP3["Serverless functions"] --> P
    P --> B1["Backend connection 1"]
    P --> B2["Backend connection 2"]
    P --> B3["Backend connection 3"]
    B1 --> DB[("Database")]
    B2 --> DB
    B3 --> DB
~~~

Proxy có thể tập trung quản lý kết nối, giảm backend session, hỗ trợ xác thực hoặc failover và cung cấp endpoint ổn định. Tuy nhiên, không phải proxy nào cũng multiplex được mọi session; có thể có giới hạn về transaction, prepared statement, temporary table, session variable hoặc protocol feature.

### 3.3. Pool ứng dụng kết hợp proxy

Một kiến trúc thường gặp có HikariCP trong mỗi application instance và managed proxy ở phía database:

~~~mermaid
flowchart TB
    subgraph COMPUTE["Compute layer"]
      A1["API instance 1"] --> H1["Hikari pool 1"]
      A2["API instance 2"] --> H2["Hikari pool 2"]
      W["Worker"] --> HW["Worker pool"]
    end
    H1 --> PROXY["DB proxy / connection manager"]
    H2 --> PROXY
    HW --> PROXY
    PROXY --> DB[("Database cluster")]
~~~

Có hai lớp pool. Pool ứng dụng giới hạn connection từ mỗi process; proxy quản lý backend session tới database. Cần tránh đặt hai lớp timeout và capacity mà không hiểu quan hệ, vì caller có thể chờ ở pool ứng dụng rồi tiếp tục chờ proxy.

### 3.4. So sánh

| Tiêu chí | Pool trong ứng dụng | Pool/proxy tập trung |
| --- | --- | --- |
| Phạm vi | Một process/instance | Nhiều client/application |
| Quản lý connection | Mỗi ứng dụng tự cấu hình | Proxy có thể gom và phân phối |
| Scale ngang | Tổng pool tăng theo instance | Proxy có thể giảm backend sessions |
| Network hop | Trực tiếp tới DB | Thêm một hop |
| Session semantics | Gần database/driver hơn | Có thể bị giới hạn bởi multiplexing |
| Vận hành | Tương đối đơn giản | Thêm service, HA, quota và chi phí |
| Hữu ích khi | Ứng dụng ổn định, số instance kiểm soát được | Nhiều client, serverless, burst, cần failover endpoint |

Không có lựa chọn tốt nhất cho mọi workload. Một ứng dụng ít instance có thể chỉ cần pool local; platform có hàng trăm function ngắn hạn có thể cần proxy hoặc mô hình dữ liệu khác.

## 4. Ước lượng connection budget

### 4.1. Tính giới hạn tổng của ứng dụng

~~~text
Application connection ceiling
  = Number of instances × Maximum pool size per instance
~~~

Với nhiều thành phần:

~~~text
Total possible client connections
  = Σ(instances_i × maxPoolSize_i)
~~~

Ví dụ:

| Thành phần | Instance tối đa | Pool tối đa mỗi instance | Connection tối đa |
| --- | ---: | ---: | ---: |
| Booking API | 12 | 18 | 216 |
| Admin API | 3 | 8 | 24 |
| Background workers | 8 | 5 | 40 |
| Reporting service | 2 | 6 | 12 |
| **Tổng** | | | **292** |

Nếu database cho phép 350 connection, không nên dành toàn bộ 350 cho ứng dụng. Phải để chỗ cho DBA, migration, monitoring, replication, maintenance và các dịch vụ khác.

### 4.2. Connection budget toàn hệ thống

Ví dụ budget:

| Nhóm | Ngân sách connection |
| --- | ---: |
| Application workloads | 250 |
| Reporting/analytics jobs | 25 |
| Admin/migration/monitoring | 20 |
| Replication và dịch vụ nội bộ | 15 |
| Headroom cho failover/scale | 40 |
| **Tổng** | **350** |

Ngân sách nên có owner và được cập nhật khi thêm workload. Nếu database giới hạn connection theo user, database, role hoặc tenant, cần tính theo từng scope thay vì chỉ cộng tổng.

### 4.3. Autoscaling và deployment overlap

Giả sử API có tối đa 10 instance và pool max 20. Trong rolling deployment, 10 instance cũ và 10 instance mới có thể cùng tồn tại. Nếu tất cả pool mở đủ, số connection tạm thời có thể lên 400 thay vì 200.

Cần xét max replica khi autoscaling, surge/unavailable setting, graceful shutdown, pool minimum idle, worker/cron chạy song song, failover và connection bổ sung cho migration. Connection budget phải tính theo **đỉnh triển khai và phục hồi**, không chỉ steady state.

## 5. Pool size không nên chọn tùy tiện

Một cách khởi đầu là đặt pool nhỏ, đo throughput/latency và tăng dần tới khi không cải thiện. Kết nối không hoạt động cũng có chi phí, vì vậy pool tối đa không nên bằng số thread xử lý request.

Nguyên tắc:

- Tính tổng pool của mọi replica trước khi đặt max size.
- Bắt đầu ở mức khiêm tốn và benchmark theo query mix thực tế.
- Giới hạn tổng concurrency tới database, không chỉ riêng endpoint.
- Pool size cho worker nền có thể thấp hơn API nếu job nặng.
- Dành connection riêng cho admin/maintenance theo policy.
- Không tăng pool để che query chậm hoặc transaction giữ connection lâu.
- Xem CPU, IOPS, lock, buffer/cache hit và throughput cùng connection count.

### 5.1. Little's Law và ước lượng connection đang dùng

Trong điều kiện tải ổn định, Little's Law giúp ước lượng concurrency trung bình:

~~~text
Average concurrent operations
  ≈ Arrival rate × Average time in system
~~~

Ví dụ database nhận 120 query/giây, thời gian connection bị giữ trung bình là 80 ms:

~~~text
120 queries/s × 0.08 s = 9.6 concurrent connections
~~~

Đây là concurrency trung bình trong mô hình đơn giản. Transaction dài, query tail latency, burst hoặc nhiều query trong một transaction đòi hỏi benchmark và percentile. Không thể lấy 9,6 rồi kết luận pool max 10 chắc chắn đủ.

### 5.2. Pool utilization và queueing

Nếu pool max 20 và cả 20 connection thường xuyên active, caller mới phải chờ. Utilization cao kéo dài có thể làm acquisition latency tăng mạnh khi duration biến động.

Theo dõi active, idle, total connections, pending/waiting borrowers, acquisition time, usage duration, creation/close rate và timeout count.

Pool thường xuyên đầy có thể chỉ ra pool quá nhỏ, query chậm, transaction dài, thread bị block hoặc database không đủ năng lực. Cần xem đồng thời số liệu DB.

## 6. Cấu hình connection pool trong Java/Spring Boot

### 6.1. HikariCP và JDBC

Spring Boot thường dùng HikariCP làm JDBC connection pool mặc định khi dependency phù hợp được thêm vào. Cấu hình phải phù hợp với số instance và DB budget.

Ví dụ YAML minh họa:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-proxy.internal:5432/booking
    username: booking_app
    password: $DB_PASSWORD
    hikari:
      pool-name: booking-api
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 2000
      idle-timeout: 300000
      max-lifetime: 1500000
      validation-timeout: 1000
      keepalive-time: 120000
      leak-detection-threshold: 0
~~~

Các giá trị là ví dụ, không phải khuyến nghị dùng nguyên trạng. Kiểm tra phiên bản HikariCP, driver, proxy và database. Với production, secret nên lấy từ secret manager hoặc identity được phê duyệt, không lưu plain text trong file cấu hình.

### 6.2. Ý nghĩa các thông số

| Tham số | Ý nghĩa | Rủi ro khi cấu hình sai |
| --- | --- | --- |
| maximumPoolSize | Giới hạn connection tối đa trong pool | Quá lớn gây quá tải DB; quá nhỏ gây chờ |
| minimumIdle | Connection idle tối thiểu pool duy trì | Quá lớn tạo session nhàn rỗi; quá nhỏ tăng thời gian mở connection |
| connectionTimeout | Thời gian chờ lấy connection | Quá dài gây request treo; quá ngắn tạo lỗi sớm |
| idleTimeout | Đóng connection rảnh vượt thời gian | Có thể tạo churn nếu traffic dao động |
| maxLifetime | Tuổi thọ tối đa connection | Quá dài gặp connection bị server/proxy đóng; quá ngắn tạo handshake liên tục |
| validationTimeout | Thời gian kiểm tra connection | Quá dài làm chậm borrow; quá ngắn tạo false failure |
| keepaliveTime | Kiểm tra/duy trì connection idle khi được hỗ trợ | Tạo traffic định kỳ, không thay thế health check |
| leakDetectionThreshold | Cảnh báo connection bị giữ quá lâu | Ngưỡng thấp có thể tạo cảnh báo nhiễu |

Không bật leak detection với ngưỡng quá thấp trong production nếu chưa hiểu workload. Transaction hợp lệ dài hơn ngưỡng có thể bị cảnh báo như leak.

### 6.3. Luôn đóng connection

Dùng try-with-resources để trả connection, statement và result set về pool:

~~~java
public Optional<Booking> findBooking(UUID bookingId) throws SQLException {
    String sql = """
        SELECT id, status, check_in, check_out
        FROM bookings
        WHERE id = ?
        """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setObject(1, bookingId);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                return Optional.empty();
            }

            return Optional.of(new Booking(
                result.getObject("id", UUID.class),
                result.getString("status"),
                result.getDate("check_in").toLocalDate(),
                result.getDate("check_out").toLocalDate()
            ));
        }
    }
}
~~~

Khi kết thúc try block, close trả logical connection về pool. Không giữ connection qua tác vụ gửi email, gọi HTTP hoặc chờ người dùng. Đọc/ghi transaction DB trong khoảng ngắn rồi giải phóng connection trước khi làm I/O ngoài.

### 6.4. Transaction boundary

Transaction mở lâu giữ connection lâu. Ví dụ một transaction vừa cập nhật booking vừa gọi payment provider trong 5 giây có thể giữ session trong suốt thời gian chờ mạng. Với traffic lớn, pool nhanh chóng cạn.

Thiết kế thường tốt hơn:

1. Transaction ngắn tạo trạng thái payment pending và operation ID.
2. Commit, trả connection về pool.
3. Gọi payment provider ngoài transaction DB.
4. Transaction khác cập nhật kết quả theo idempotency key.
5. Đối soát nếu timeout không rõ kết quả.

Không mở connection trước khi thực hiện công việc ngoài DB nếu chưa cần truy vấn/ghi dữ liệu.

## 7. Pooling và session state: những giới hạn cần hiểu

Connection được trả về pool và dùng lại bởi request khác. Vì vậy session state phải được xử lý cẩn thận:

- Transaction phải commit hoặc rollback trước khi trả connection.
- Không để session variable, role hoặc search_path thay đổi mà không reset.
- Temporary table/session-level object có thể tồn tại sang lần mượn kế tiếp tùy database và pool.
- Prepared statement có lifecycle gắn với driver/session; pooling ở proxy có thể ảnh hưởng.
- Advisory lock/session lock có thể tồn tại lâu hơn logical request nếu không giải phóng.
- Transaction isolation hoặc timezone thay đổi phải được reset đúng cách.
- LISTEN/NOTIFY, cursor dài hoặc streaming result có thể cần session affinity.

Ứng dụng không được giả định mỗi lần lấy connection là một session mới. Pool có thể trả một session đã từng được sử dụng.

### 7.1. Transaction pooling và session pooling

Một số proxy hỗ trợ các pooling mode:

- **Session pooling:** client giữ backend connection trong suốt session. Tương thích rộng hơn với session state nhưng multiplexing thấp.
- **Transaction pooling:** backend connection được gán cho client trong một transaction; sau commit/rollback có thể trả về pool cho client khác. Tăng chia sẻ backend nhưng hạn chế tính năng phụ thuộc session.
- **Statement pooling:** backend được gán theo từng statement trong hệ thống hỗ trợ; hạn chế hơn với transaction nhiều câu lệnh và session state.

Không phải proxy nào cũng có tất cả chế độ. Transaction pooling có thể không tương thích với session-level feature, temporary table, prepared statement, advisory lock hoặc multi-statement transaction pattern. Kiểm tra danh sách hỗ trợ của proxy cụ thể và chạy integration test.

### 7.2. Prepared statements và driver behavior

Prepared statement có thể được quản lý ở driver, server hoặc proxy. Một số proxy phải theo dõi/định tuyến trạng thái prepared statement; một số cấu hình transaction pooling không hỗ trợ đầy đủ. Khi bật proxy, hãy kiểm tra driver có cache prepared statement không, statement có tên ở server hay không, proxy hỗ trợ protocol feature trong mode đang dùng ra sao và statement còn hợp lệ sau backend switch/failover không.

Không tắt prepared statement máy móc. Đo hiệu năng và tương thích dựa trên driver, server và proxy thực tế.

## 8. Database proxy: chức năng và lựa chọn

### 8.1. Proxy đứng ở đâu?

Proxy cung cấp endpoint mà ứng dụng kết nối tới. Nó nhận kết nối client rồi sử dụng backend connection tới database. Tùy thiết kế, proxy có thể gom nhiều client connection thành ít backend connection hơn, quản lý connection lifecycle/health, chuyển hướng tới writer/reader endpoint, hỗ trợ failover, tích hợp IAM/database authentication, giới hạn/quan sát connection.

Các khả năng này phụ thuộc sản phẩm. Không giả định proxy tự động load balance query, retry transaction an toàn hoặc failover không gián đoạn.

### 8.2. Managed proxy và self-managed proxy

| Tiêu chí | Managed database proxy | Self-managed proxy |
| --- | --- | --- |
| Cài đặt và patch | Nhà cung cấp quản lý phần lớn hạ tầng | Đội ngũ tự triển khai, patch và nâng cấp |
| HA | Có thể tích hợp HA theo dịch vụ | Tự thiết kế replica, health check và failover |
| Cấu hình chuyên sâu | Có thể bị giới hạn | Kiểm soát nhiều hơn |
| Tích hợp IAM/DB | Thường tích hợp theo cloud | Tự cấu hình và quản lý |
| Quan sát | Metric/log do dịch vụ cung cấp | Tùy instrumentation |
| Chi phí | Phí dịch vụ/compute/connection | Compute, network, license và nhân lực |
| Lock-in | Có thể gắn với cloud service | Có thể portable hơn, vẫn có khác biệt config |

Ví dụ sản phẩm có thể gồm Amazon RDS Proxy, Cloud SQL connectors/proxy hoặc PgBouncer cho PostgreSQL. Chúng không có chức năng và semantics giống nhau; cần đánh giá tài liệu hiện hành, engine/version, networking, authentication, pooling mode và giá dịch vụ cụ thể.

### 8.3. Proxy không thay thế application pool

Ứng dụng vẫn có thể mở hàng trăm logical client connection tới proxy. Proxy có thể giảm backend session nhưng không loại bỏ việc app giữ connection, thread chờ hoặc memory cho client session. Cần đặt giới hạn ở cả hai lớp và quan sát wait time tại từng lớp.

## 9. Serverless và connection scaling

Serverless function có thể scale concurrency nhanh theo số event/request. Nếu mỗi execution mở database connection mới, database bị connection storm.

~~~mermaid
flowchart TB
    E["Traffic burst"] --> S["Serverless platform"]
    S --> F1["Function invocation 1"]
    S --> F2["Function invocation 2"]
    S --> F3["Function invocation N"]
    F1 --> PROXY["Database proxy"]
    F2 --> PROXY
    F3 --> PROXY
    PROXY --> POOL["Bounded backend pool"]
    POOL --> DB[("Database")]
~~~

Proxy hoặc connection manager có thể giảm số backend session, nhưng vẫn cần:

- Giới hạn function concurrency/reserved concurrency.
- Đặt timeout và giới hạn client connection tới proxy.
- Tái sử dụng client nếu execution environment được giữ lại và nền tảng cho phép.
- Không giữ connection trong thời gian function idle.
- Dùng queue để hấp thụ burst nếu nghiệp vụ có thể chờ.
- Chọn database/proxy tương thích với semantics transaction.
- Benchmark tốc độ tạo connection khi cold start hoặc scale-out.
- Theo dõi quota của proxy, DB và network.

Với function ngắn, transaction pooling có thể hiệu quả nhưng phải bảo đảm ứng dụng không phụ thuộc session state giữa các transaction.

## 10. Timeout: phối hợp nhiều tầng

Một request có thể đi qua client, API gateway, application thread, application pool, proxy, database connection, query và response. Mỗi tầng có timeout riêng.

~~~mermaid
flowchart LR
    C["Client timeout"] --> G["Gateway timeout"]
    G --> A["App request timeout"]
    A --> P["Pool acquisition timeout"]
    P --> X["Proxy/backend timeout"]
    X --> D["DB statement/lock timeout"]
~~~

Nếu pool acquisition timeout là 30 giây nhưng gateway timeout là 10 giây, client đã bỏ request trước khi pool báo lỗi. Nếu query timeout dài hơn HTTP deadline, backend có thể tiếp tục chạy sau khi client ngừng chờ.

Thiết kế cần timeout budget rõ:

- Request deadline là giới hạn tổng.
- Pool acquisition timeout chỉ chiếm một phần nhỏ của budget.
- Proxy connect/borrow timeout phù hợp với pool application.
- Database statement timeout ngăn query chạy vô hạn.
- Lock timeout kiểm soát chờ lock.
- Network/socket timeout phù hợp retry policy.

Không đặt mọi timeout bằng nhau. Khi request hết deadline, cần hủy statement hoặc ngắt tác vụ theo cách driver/database hỗ trợ; kiểm tra query có thực sự dừng hay tiếp tục tiêu thụ tài nguyên.

## 11. Failover, DNS và connection lifecycle

Khi database failover sang node khác, connection TCP hiện hữu có thể bị reset hoặc trở thành stale. Pool và proxy cần nhận diện connection lỗi, loại bỏ và tạo mới. Ứng dụng cần xử lý exception và retry có kiểm soát.

Cần kiểm tra DNS TTL và cách driver/proxy resolve endpoint; connection max lifetime so với giới hạn server/proxy; validation/keepalive; retry sau khi transaction có thể đã commit nhưng response bị mất; proxy HA; và khả năng tạo connection storm tới endpoint mới.

### 11.1. Retry transaction không phải lúc nào cũng an toàn

Nếu client gửi UPDATE, database commit, nhưng network mất trước response, ứng dụng không biết transaction đã commit chưa. Retry mù có thể áp dụng side effect lần hai.

Dùng idempotency key, unique business key, optimistic version hoặc read-after-uncertain-outcome reconciliation. Pool/proxy cải thiện kết nối nhưng không giải quyết tính đúng đắn nghiệp vụ của retry.

### 11.2. Connection storm sau outage

Sau khi database phục hồi, mọi instance có thể cùng reconnect. Để giảm đỉnh:

- Giới hạn pool growth và startup connection.
- Dùng exponential backoff với jitter cho reconnect.
- Giới hạn app concurrency khi DB chưa ổn định.
- Có circuit breaker hoặc retry budget phù hợp.
- Giữ connection admin/monitoring để quan sát.
- Tránh restart đồng loạt toàn fleet nếu không cần.
- Theo dõi connection creation rate và authentication latency.

## 12. Bảo mật connection pool và proxy

Connection pooling thay đổi cách kết nối được chia sẻ, không làm giảm yêu cầu bảo mật.

### 12.1. TLS và network path

Dùng TLS cho app-to-proxy và proxy-to-database nếu mô hình hỗ trợ; xác thực certificate và hostname đúng; đặt proxy trong private network/subnet phù hợp; dùng firewall chỉ cho phép nguồn, đích và port cần thiết; kiểm tra DNS/private endpoint và route hai chiều. Không expose database/proxy endpoint công khai nếu không có yêu cầu và kiểm soát đặc biệt.

### 12.2. Identity và secret rotation

- Dùng database user/service identity theo workload.
- Cấp quyền tối thiểu theo schema/table/operation.
- Tách credential của API, worker, reporting và migration.
- Lưu secret trong secret manager hoặc identity provider phù hợp.
- Thiết kế rotation sao cho pool tạo kết nối mới bằng credential mới.
- Thu hồi credential cũ sau thời gian overlap đã kiểm thử.
- Không ghi password, token hoặc connection string đầy đủ vào log.

Nếu proxy hỗ trợ IAM authentication hoặc token ngắn hạn, cần hiểu token được lấy/refresh ở đâu, token lifetime so với connection lifetime thế nào và hành vi khi identity provider tạm thời lỗi.

### 12.3. Session reuse và tenant isolation

Nếu nhiều tenant dùng chung pool hoặc proxy, không dựa vào session variable chưa được reset để phân biệt tenant. Tenant authorization phải được thực hiện ở application/query boundary; nếu có RLS, bảo đảm context được thiết lập an toàn trong transaction rồi reset trước khi connection quay lại pool.

Không để session state của tenant trước rò sang tenant sau. Kiểm thử reuse connection tuần tự qua nhiều tenant và cả lỗi rollback.

## 13. Observability: theo dõi pool, proxy và database cùng lúc

Chỉ nhìn số connection ở DB không đủ để chẩn đoán. DB còn session nhưng app có thể hết pool; app pool rảnh nhưng proxy không cấp được backend connection.

### 13.1. Metrics ở application pool

| Metric | Ý nghĩa |
| --- | --- |
| Active connections | Số connection đang được mượn |
| Idle connections | Số connection sẵn sàng |
| Total connections | Tổng connection do pool quản lý |
| Pending threads/waiters | Số caller đang chờ |
| Acquisition latency | Thời gian lấy connection |
| Usage duration | Thời gian connection được giữ |
| Creation/close rate | Tốc độ tạo và hủy connection |
| Timeout count | Số lần không lấy được connection đúng hạn |
| Leak warnings | Kết nối bị giữ lâu bất thường |

### 13.2. Metrics ở proxy và database

Tùy sản phẩm, proxy cần theo dõi client connections, backend connections, pool utilization, borrow wait, rejected connections, authentication failure, backend health và failover events.

Database cần theo dõi session count theo user/application, active/idle sessions, transaction age, lock wait, deadlock, query latency, CPU, memory, IOPS, cache hit, replication lag và connection rejection.

### 13.3. Kết nối metrics thành một chuỗi

Ví dụ app pool pending tăng và acquisition latency tăng:

- Nếu app active = max, idle = 0, proxy/backend còn capacity: có thể query/transaction giữ connection lâu hoặc pool app quá nhỏ.
- Nếu app còn client connection nhưng proxy borrow wait tăng: proxy backend pool có thể bão hòa hoặc database không nhận thêm session.
- Nếu DB CPU/IO/lock wait cao: tăng pool/proxy capacity có thể làm sự cố nặng hơn.
- Nếu connection creation rate tăng sau deploy: xem min idle, max lifetime, rollout surge và startup behavior.

Dashboard nên có dimensions theo service, environment, deployment version và database role; tránh label cardinality quá cao theo từng connection/request.

## 14. SLO và kịch bản chất lượng

Các ngưỡng sau chỉ là ví dụ học tập. Khi áp dụng phải xác định workload, cửa sổ đo, deadline và điều kiện tải.

| Mã | Tình huống | Phản hồi kỳ vọng | Thước đo minh họa |
| --- | --- | --- | --- |
| QA-POOL-01 | Peak traffic tăng gấp 3 | Pool giữ số connection trong budget, request chờ trong giới hạn | Pool acquisition p95 dưới 100 ms; không vượt DB budget |
| QA-POOL-02 | Autoscale và rolling deployment overlap | Tổng connection không vượt capacity dành cho ứng dụng | Peak connection dưới ngưỡng được phê duyệt |
| QA-POOL-03 | Worker giữ connection quá lâu | Leak/long transaction được phát hiện | Cảnh báo trong 2 phút; không cạn pool toàn service |
| QA-PROXY-01 | Proxy backend pool bão hòa | Request bị giới hạn hoặc chờ có deadline | Rejected/timeout có cảnh báo; DB không vượt max session |
| QA-FAIL-01 | Database failover | Pool loại stale connection và phục hồi có backoff | Kết nối phục hồi trong RTO; không reconnect storm |
| QA-SEC-01 | Credential cũ bị rotation | Kết nối mới dùng credential mới, credential cũ bị thu hồi | Không có secret trong log; kết nối hoạt động sau rotation |
| QA-SESSION-01 | Hai tenant dùng lại cùng backend session | Không rò session state/authorization context | 100% ca isolation trong bộ test pass |
| QA-COST-01 | So sánh direct pool và proxy | Chi phí toàn tuyến trong budget với cùng SLO | Cost per successful transaction được đo theo từng mô hình |

SLO connection không thể chỉ dựa trên connection count. Cần kết hợp acquisition latency, query latency, transaction success và tác động người dùng.

## 15. TCO: direct connection, pool và proxy

### 15.1. Thành phần chi phí

**Kết nối trực tiếp với pool ứng dụng:** compute của ứng dụng và connection management; database capacity/session overhead; monitoring, troubleshooting và vận hành pool; reconnect/failover và headroom; network/TLS/authentication.

**Có proxy:** phí proxy instance/compute/connection tùy dịch vụ; network hop và data processing; database backend capacity có thể giảm nếu multiplexing hiệu quả; HA, scaling, monitoring và support; thời gian cấu hình, migration, kiểm thử session compatibility; lock-in và chi phí vận hành service mới.

Proxy có thể làm tổng chi phí thấp hơn nếu giảm backend session đáng kể hoặc đơn giản hóa vận hành; cũng có thể làm chi phí cao hơn nếu workload nhỏ hoặc mỗi client vẫn giữ backend session lâu.

### 15.2. Ví dụ chi phí giả định

Đơn vị: triệu VND/tháng. Các số dưới đây chỉ minh họa cách so sánh, không phải báo giá.

| Hạng mục | A: App pool trực tiếp | B: App pool + proxy |
| --- | ---: | ---: |
| Application compute phân bổ | 35 | 35 |
| Database capacity phân bổ | 80 | 68 |
| Proxy service | 0 | 22 |
| Network/processing | 5 | 8 |
| Observability/security | 8 | 10 |
| Vận hành phân bổ | 14 | 12 |
| **Tổng** | **142** | **155** |

Trong ví dụ, proxy giảm phần database capacity giả định nhưng tổng chi phí vẫn cao hơn vì phí proxy và network. Nếu workload serverless tạo nhiều kết nối ngắn và proxy giúp giảm DB capacity hoặc giảm incident, kết quả TCO có thể khác. Cần thay bằng benchmark và giá hiện hành.

### 15.3. Cost per successful transaction

~~~text
Cost per successful transaction
  = Total monthly cost of the database access path
    / Number of successful business transactions
~~~

Mẫu số là giao dịch nghiệp vụ thành công, không phải số query hoặc số connection. Nếu pool timeout làm request thất bại, chi phí compute/log/DB của lần thất bại vẫn nằm trong tử số.

## 16. Quy trình thiết kế và triển khai

1. **Thu thập tải:** request rate, query mix, transaction duration, peak/burst, số service và autoscaling range.
2. **Khảo sát DB:** max connection, session memory, CPU/IO, lock, role/user limit, replica topology và reserved capacity.
3. **Lập budget:** cộng pool tối đa của API, worker, reporting, migration và deployment overlap; để headroom.
4. **Chọn kiến trúc:** direct pool, proxy hoặc pool kết hợp proxy; xác định backend connection semantics.
5. **Cấu hình pool:** max/min, acquisition timeout, idle timeout, max lifetime, keepalive và validation.
6. **Thiết kế transaction:** giữ transaction ngắn, không giữ connection qua network call ngoài DB.
7. **Thiết kế failure handling:** timeout budget, retry, idempotency, circuit breaker, reconnect backoff và failover.
8. **Thiết kế bảo mật:** private network, TLS, identity, secret rotation và least privilege.
9. **Quan sát:** app pool, proxy, database, query latency và business SLO.
10. **Kiểm thử:** peak, autoscaling, rolling deploy, connection storm, failover, credential rotation và session reuse.
11. **Tối ưu:** benchmark pool size theo query mix; tăng capacity đúng bottleneck.
12. **Bàn giao:** connection budget owner, dashboard, alert, runbook, quota và ADR.

### 16.1. Mẫu connection budget

~~~yaml
database: booking-primary
max_database_connections: 500
reserved:
  admin_and_migration: 25
  replication_and_monitoring: 25
  operational_headroom: 50
application_budget: 400
workloads:
  booking_api:
    max_instances: 15
    pool_max_per_instance: 16
    calculated_max: 240
  admin_api:
    max_instances: 3
    pool_max_per_instance: 8
    calculated_max: 24
  background_worker:
    max_instances: 10
    pool_max_per_instance: 6
    calculated_max: 60
  reporting:
    max_instances: 2
    pool_max_per_instance: 10
    calculated_max: 20
calculated_application_total: 344
unallocated_application_headroom: 56
status: proposed
~~~

Đây là mẫu hoạch định. Tổng connection thực tế còn phụ thuộc min idle, startup behavior, deployment surge, proxy multiplexing, health checks và cách database tính session. Mẫu không thay thế load test.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Mỗi instance đặt pool lớn mà không cộng tổng | Database hết connection khi scale | Connection budget toàn fleet |
| Tăng pool khi query chậm | Session và contention tăng | Đo DB bottleneck, query/transaction duration |
| Giữ connection khi gọi API ngoài | Pool cạn dù DB query nhanh | Kết thúc transaction trước external I/O |
| Không đóng connection | Leak và timeout pool | try-with-resources, kiểm tra code path |
| Pool max lớn hơn concurrency DB chịu được | DB overload | Benchmark và giới hạn app concurrency |
| Rolling deploy mở hai thế hệ pool cùng lúc | Connection spike | Tính surge, min idle và graceful shutdown |
| Retry mù sau failover | Ghi trùng nghiệp vụ | Idempotency key và reconciliation |
| Chỉ đo DB sessions | Không thấy app pool wait hoặc proxy saturation | Dashboard ba lớp |
| Dùng transaction pooling nhưng phụ thuộc session state | Lỗi ngữ nghĩa hoặc dữ liệu chéo | Kiểm tra compatibility, reset state |
| Timeout ở các tầng không nhất quán | Request chờ quá deadline | Timeout budget xuyên tuyến |
| Reconnect đồng loạt sau outage | Connection storm | Backoff/jitter và startup ramp |
| Proxy được coi là HA tuyệt đối | Proxy/backend pool thành SPOF | Multi-AZ/HA và failure drill |
| Không rotation test | Kết nối mới không dùng credential mới | Thử rotation khi connection cũ còn sống |

## 18. Case study: Spring Boot trên cloud với database dùng chung

### 18.1. Bối cảnh

Một nền tảng đặt chỗ có 15 instance Booking API giờ cao điểm, 3 instance Admin API, 10 worker xử lý email/inventory/đối soát và 2 reporting instance. PostgreSQL managed database có giới hạn 500 connection cho workload và quản trị theo cấu hình dịch vụ.

Pool max ban đầu của mỗi Booking API là 40. Chỉ riêng API có thể tạo:

~~~text
15 × 40 = 600 connections
~~~

Chưa tính service còn lại. Trong giờ cao điểm, deploy mới khiến hệ thống xuất hiện nhiều timeout lấy connection và database từ chối session mới.

### 18.2. Đánh giá và thay đổi

Đội ngũ lập connection budget, phân bổ pool nhỏ hơn theo workload, giảm transaction duration và chuyển báo cáo nặng sang read replica/warehouse phù hợp. Sau benchmark, API dùng pool max 16, Admin 8, Worker 6 và Reporting 10:

~~~text
Booking API: 15 × 16 = 240
Admin:        3 × 8  =  24
Worker:      10 × 6  =  60
Reporting:    2 × 10 =  20
--------------------------------
Total application ceiling = 344
~~~

Database dành 400 connection cho application budget và phần còn lại cho migration, admin, monitoring và headroom. Số liệu vẫn cần kiểm thử với rollout surge và failover.

Đội đánh giá proxy vì nhiều workload ngắn hạn và serverless function có thể tạo kết nối mới nhanh. Proxy được đưa vào staging, kiểm tra session state, prepared statement, transaction, IAM/TLS, failover và metrics trước khi cân nhắc production.

### 18.3. Kiểm thử chấp nhận

- Load test ở peak traffic, đo active/idle/pending và acquisition p95/p99.
- Scale từ số instance bình thường tới max replica; xác minh DB sessions nằm trong budget.
- Rolling deployment có surge để đo peak connection thực tế.
- Dừng database primary và quan sát stale connection, reconnect rate, transaction outcome.
- Làm chậm một query để xem pool saturation và alert.
- Giữ connection cố ý quá lâu trong test để xác minh leak detection.
- Rotation credential khi pool còn connection cũ.
- Dùng lại session giữa hai tenant để kiểm tra reset và isolation.
- Nếu dùng proxy, so backend connection count, borrow latency, error rate và chi phí.

### 18.4. Kết quả kiến trúc mong đợi

Hệ thống có connection budget được quản lý, pool size được benchmark, timeout phù hợp request deadline và transaction không giữ connection trong lúc chờ network call ngoài. Proxy chỉ được triển khai nếu cải thiện được chỉ số cụ thể như backend session count, failover behavior hoặc vận hành với serverless. Mọi thay đổi phải có dashboard và runbook.

## 19. Bài tập thực hành

Một ứng dụng thương mại điện tử chạy Spring Boot trên Kubernetes và serverless. Ứng dụng có 25 API pod, mỗi pod hiện cấu hình pool max 30; 40 function có thể đồng thời chạy khi flash sale; 5 worker xử lý đơn hàng. Database có giới hạn 600 session cho workload ứng dụng và 100 session cần giữ cho quản trị, replication, monitoring và vận hành.

Hãy thực hiện:

1. Tính connection ceiling của 25 pod nếu chưa tính function và worker; nêu vì sao cấu hình hiện tại rủi ro.
2. Đề xuất connection budget cho API, function/proxy và worker; giữ headroom khi autoscale/rolling deploy.
3. Phân biệt application pool và database proxy; nêu trường hợp proxy có thể giảm backend connections.
4. Ước lượng concurrency trung bình nếu workload tạo 200 query/giây và connection usage duration trung bình 50 ms.
5. Đề xuất pool max, min idle, acquisition timeout, max lifetime và cách benchmark; giải thích các giá trị chỉ là giả định ban đầu.
6. Phân tích vì sao giữ JDBC connection trong lúc gọi payment API làm cạn pool.
7. Mô tả các giới hạn session khi proxy dùng transaction pooling.
8. Thiết kế timeout budget cho client, gateway, app pool, proxy và database statement.
9. Lập kế hoạch failover và tránh connection storm sau khi database phục hồi.
10. Thiết kế dashboard cho application pool, proxy và database; nêu ít nhất năm cảnh báo có hành động cụ thể.
11. So sánh TCO direct connection và pool + proxy theo cùng workload, cùng SLO.
12. Viết ADR về lựa chọn cuối cùng và điều kiện xem xét lại.

**Gợi ý tự đánh giá:** Bài làm đạt khi tính connection trên toàn fleet, kể cả autoscaling và deployment overlap; phân biệt logical client connection với backend database session; và có bằng chứng đo acquisition wait, DB capacity, failover và business success.

## 20. Checklist trước production

- [ ] Đã biết giới hạn connection thực tế của database, role, user và proxy.
- [ ] Đã cộng pool max của mọi API, worker, reporting và function.
- [ ] Đã tính autoscaling maximum, deployment surge và startup behavior.
- [ ] Có ngân sách riêng cho admin, migration, monitoring, replication và headroom.
- [ ] Pool size dựa trên benchmark/query mix, không chọn theo số thread tùy tiện.
- [ ] Có acquisition timeout, idle timeout, max lifetime và validation phù hợp.
- [ ] Connection được trả về pool bằng try-with-resources; không giữ qua external I/O.
- [ ] Transaction ngắn và session state được reset.
- [ ] Đã xác minh tương thích prepared statement, cursor, temp table và session feature với proxy mode.
- [ ] Timeout được phối hợp xuyên client, gateway, pool, proxy và database.
- [ ] Có idempotency/reconciliation cho retry sau timeout hoặc failover.
- [ ] Có TLS, private networking, least privilege và secret rotation.
- [ ] Dashboard theo dõi pool, proxy và database cùng lúc.
- [ ] Đã kiểm thử autoscaling, rolling deploy, failover, connection storm và credential rotation.
- [ ] Có runbook, connection budget owner và cost model.

## 21. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi review connection pooling/proxy |
| --- | --- |
| **Operational Excellence** | Connection budget, dashboard, alert, runbook, rotation và failover drill có owner rõ không? |
| **Security** | TLS, identity, least privilege, private endpoint, secret rotation và session isolation có được kiểm tra không? |
| **Reliability** | Pool/proxy có phục hồi sau stale connection, database failover, deploy overlap và connection storm không? |
| **Performance Efficiency** | Pool size, acquisition latency, query latency, concurrency và DB saturation có đáp ứng workload không? |
| **Cost Optimization** | Chi phí proxy có được bù bởi giảm backend sessions, incident và vận hành; cost per transaction là bao nhiêu? |
| **Sustainability** | Có tránh mở connection nhàn rỗi quá mức, reconnect lặp và overprovision database/proxy không? |

**Kết luận:** Connection pool và database proxy giúp điều tiết kết nối, tái sử dụng session và bảo vệ database khỏi số lượng client không kiểm soát. Hiệu quả phụ thuộc vào connection budget toàn fleet, pool size được benchmark, transaction ngắn, session semantics tương thích, timeout và hành vi failover được kiểm thử. Đừng xem việc tăng connection là cách tăng throughput mặc định; hãy tìm bottleneck thực, đo từ ứng dụng qua proxy tới database và cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo Well-Architected.
