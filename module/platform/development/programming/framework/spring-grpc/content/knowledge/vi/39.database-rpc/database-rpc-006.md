# Connection pool dưới tải RPC

## 1. Vai trò của connection pool trong Spring gRPC

Trong **SPRING_GRPC**, một server có thể nhận hàng trăm hoặc hàng nghìn RPC đồng thời, trong khi database chỉ phục vụ được một số lượng connection hữu hạn. Mở connection cho mọi RPC đang chạy không làm database nhanh hơn; nó có thể làm cạn connection limit, tăng context switching, tranh chấp lock và khiến độ trễ tăng mạnh.

Spring Boot thường dùng HikariCP để tái sử dụng JDBC connection. Khi transaction cần database, ứng dụng mượn connection từ pool; khi transaction kết thúc, connection được trả về pool. Pool là hàng đợi tài nguyên có giới hạn giữa concurrency của RPC và năng lực database.

Thiết kế cần cân bằng ba yếu tố:

- **RPC concurrency:** số request đang chạy cùng lúc.
- **Pool capacity:** số connection một instance được phép giữ.
- **Database capacity:** số truy vấn/transaction database xử lý hiệu quả cùng lúc.

Tăng pool size chỉ hữu ích khi database còn năng lực và connection thực sự là nút thắt. Nếu database đã bão hòa CPU, I/O hoặc lock, tăng pool thường làm hàng đợi và contention tệ hơn.

## 2. Một RPC có giữ connection suốt thời gian xử lý không?

Một RPC không nhất thiết giữ connection từ lúc gRPC nhận request tới lúc response được gửi. Với JDBC/JPA, connection thường được lấy khi transaction bắt đầu database work và được trả khi transaction kết thúc, tùy transaction manager và cấu hình connection handling.

Ví dụ unary command:

1. gRPC adapter nhận request và validate cấu trúc.
2. Adapter gọi application service.
3. Spring mở transaction; transaction manager lấy connection khi cần.
4. Repository đọc/ghi dữ liệu.
5. Transaction commit hoặc rollback.
6. Connection được trả về pool.
7. Adapter phát response.

Nếu transaction mở quá sớm rồi gọi service từ xa, chờ lock lâu hoặc tính toán nặng trước commit, connection có thể bị giữ dù không có SQL đang chạy. Với streaming RPC, giữ transaction qua thời gian chờ message hoặc backpressure càng nguy hiểm.

**Giữ transaction và connection sát với đoạn database work; không giữ chúng trong lúc chờ network hoặc callback.**

## 3. Quan hệ giữa RPC concurrency và pool size

Giả sử server có 300 RPC đang hoạt động nhưng mỗi RPC chỉ dùng database trong 20 ms. Không có nghĩa cần 300 JDBC connections. Các RPC có thể lần lượt mượn một tập connection nhỏ trong khoảng thời gian ngắn.

Một ước lượng ban đầu dùng Little’s Law:

```text
Số connection trung bình cần ≈ throughput database work × thời gian giữ connection trung bình
```

Ví dụ hệ thống xử lý 500 RPC/giây, mỗi RPC dùng connection tổng cộng 30 ms:

```text
500 × 0,030 = 15 connection trung bình
```

Đây chỉ là giá trị trung bình. Sizing thực tế cần headroom cho burst, transaction duration p95/p99, RPC có nhiều truy vấn và tác vụ nền. Không lấy số RPC concurrent làm pool size trực tiếp.

Nếu mỗi RPC mở nhiều transaction tuần tự, thời gian giữ connection cộng dồn; nếu có nhiều transaction song song trong cùng request, nhu cầu có thể cao hơn. Hãy đo thời gian connection được mượn thực tế thay vì chỉ suy ra từ RPC latency.

## 4. Tính ngân sách connection toàn hệ thống

HikariCP maximumPoolSize áp dụng cho từng pool trong từng process. Nếu chạy nhiều replica, tổng connection có thể vượt xa con số cấu hình ở một instance.

| Thành phần | Số instance | Pool tối đa mỗi instance | Tổng tối đa |
| --- | ---: | ---: | ---: |
| gRPC service A | 4 | 20 | 80 |
| gRPC service B | 3 | 10 | 30 |
| Worker nền | 2 | 8 | 16 |
| Tổng ứng dụng |  |  | 126 |

Nếu database cho phép 160 connection, không thể dành toàn bộ 160 cho ứng dụng này. Cần chừa chỗ cho migration, monitoring, DBA, console, backup tooling, failover và service khác.

Ngân sách cần tính theo tình huống scale tối đa:

```text
Tổng connection tối đa
= Σ (replica tối đa × pool maximum của từng instance)
```

Nếu autoscaling tăng replica nhưng mỗi replica vẫn giữ pool maximum cũ, tổng connection có thể vượt DB limit đột ngột. Phải phối hợp autoscaling, replica ceiling và pool maximum.

## 5. Cấu hình HikariCP trong Spring Boot

Spring Boot hỗ trợ cấu hình HikariCP qua datasource properties. Ví dụ:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    password: injected-secret
    hikari:
      pool-name: orders-db-pool
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 1500
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1800000
      leak-detection-threshold: 0
```

Giá trị username/password chỉ minh họa; production nên inject credential từ secret/configuration provider, không commit secret vào repository.

| Property | Ý nghĩa | Cách cân nhắc |
| --- | --- | --- |
| maximum-pool-size | Số connection tối đa trong pool | Giới hạn theo DB budget và throughput đo được |
| minimum-idle | Số connection idle mục tiêu | Cân bằng độ sẵn sàng với số connection giữ thường trực |
| connection-timeout | Thời gian chờ mượn connection | Nằm trong ngân sách deadline RPC |
| validation-timeout | Thời gian kiểm tra connection | Nhỏ hơn connection-timeout |
| idle-timeout | Thời gian connection idle có thể bị loại bỏ | Có ý nghĩa khi minimum-idle nhỏ hơn maximum-pool-size |
| max-lifetime | Tuổi tối đa connection trước khi pool thay mới | Thấp hơn giới hạn lifetime của hạ tầng |
| leak-detection-threshold | Ngưỡng log nghi ngờ connection bị giữ lâu | Dùng chẩn đoán; không tự sửa leak |

Không sao chép nguyên các con số ví dụ vào production. Cần đo database, workload và giới hạn hạ tầng trước khi chọn giá trị.

## 6. Chọn maximumPoolSize mà không làm database quá tải

Pool size cần đủ để các transaction độc lập tiến triển, nhưng không quá lớn đến mức database phải xử lý quá nhiều query cùng lúc.

Quy trình sizing:

1. Xác định DB max connections và trừ phần dành cho quản trị, monitoring, migration cùng service khác.
2. Xác định số replica tối đa của từng ứng dụng.
3. Chia ngân sách connection cho các pool theo mức ưu tiên và tải thực tế.
4. Bắt đầu với pool vừa phải.
5. Đo pool pending/acquisition wait, transaction duration và database CPU/I/O/lock wait.
6. Điều chỉnh pool theo kết quả load test.
7. Lặp lại ở số replica tối đa và trong tình huống failover/autoscaling.

Một pool luôn full không tự động có nghĩa phải tăng pool. Nếu active connection đều đang chạy query chậm, nút thắt có thể nằm ở query plan, index, lock hoặc database capacity. Tăng pool chỉ đưa thêm query vào database đang bận.

## 7. Connection acquisition timeout và ngân sách deadline

Khi pool hết connection, thread cần database sẽ chờ connection được trả về. Nếu thời gian chờ vượt connectionTimeout, HikariCP ném lỗi lấy connection timeout.

RPC cũng có deadline. Hai ngân sách phải phối hợp:

```text
RPC deadline
  ├─ validation / application work
  ├─ wait for pool connection
  ├─ database query + commit
  └─ response serialization / network
```

Nếu RPC chỉ còn 200 ms nhưng connectionTimeout là 2 giây, request có thể tiếp tục chờ tài nguyên sau khi client đã hết thời gian chờ. Chọn connection timeout, query timeout và transaction timeout phù hợp với deadline còn lại.

Không phải mọi JDBC driver đều tự hủy query ngay khi gRPC client cancel. Cần cấu hình statement/query timeout và cancellation behavior theo driver/database; không giả định deadline gRPC tự truyền thành JDBC timeout.

Khi pool acquisition timeout xảy ra, phân loại lỗi theo policy dịch vụ. UNAVAILABLE có thể phù hợp với quá tải tạm thời có thể phục hồi; RESOURCE_EXHAUSTED phù hợp nếu contract biểu đạt giới hạn tài nguyên/quota. Không trả ABORTED trừ khi thực sự là transaction conflict. Client retry cần backoff/jitter và deadline tổng; retry dồn dập có thể làm pool quá tải nặng hơn.

## 8. Connection leak và transaction giữ connection quá lâu

Connection leak xảy ra khi code mượn connection nhưng không trả lại, thường do quản lý resource sai hoặc transaction bị treo. Với Spring/JPA, connection thường được quản lý bởi transaction manager; nhưng transaction quá dài vẫn có thể khiến pool trông như bị leak.

Các nguyên nhân thường gặp:

- Transaction bao trùm lời gọi HTTP/gRPC tới service khác.
- Transaction mở trong lúc chờ message tiếp theo của stream.
- Callback async dùng sai transaction/thread lifecycle.
- Code JDBC thủ công không đóng Statement/ResultSet/Connection đúng cách.
- Query bị block bởi lock hoặc chạy quá lâu.
- Exception path làm resource không được cleanup đúng trong code tự quản lý.

Dùng try-with-resources cho JDBC thủ công. Với Spring transaction, giữ application service ngắn và không gọi network bên trong transaction. Leak detection chỉ log stack trace của connection bị giữ vượt ngưỡng; nó không tự đóng connection an toàn thay ứng dụng.

## 9. Pool exhaustion khác database saturation

| Dấu hiệu | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Pool active chạm max, pending tăng, DB CPU thấp | Query chờ lock, transaction giữ connection lâu, pool quá nhỏ | Kiểm tra lock wait, transaction duration, pool sizing |
| Pool active chạm max, DB CPU/I/O cao | Database đã bão hòa | Query plan, index, giảm concurrency, tối ưu workload |
| Pool active thấp nhưng RPC chậm | Chậm ở network, application hoặc dependency khác | Trace từng span, không tăng pool theo cảm tính |
| Connection timeout sau deploy scale-out | Tổng pool của nhiều replica vượt DB budget | Tính lại replica × pool maximum |
| Leak detection cảnh báo liên tục | Connection giữ lâu hoặc leak thật | Xem stack trace, transaction boundaries, cleanup |

Hãy đối chiếu metrics ứng dụng với database metrics. Chỉ nhìn Hikari active count không đủ xác định nguyên nhân.

## 10. Tách pool theo workload khi cần

Một số ứng dụng có workload rất khác nhau:

- RPC interactive cần latency thấp.
- Batch import có thể chạy query lâu và dùng nhiều row.
- Reporting/export đọc lượng dữ liệu lớn.
- Worker outbox chạy nền.

Nếu tất cả dùng chung một pool, batch/reporting có thể chiếm connection khiến RPC interactive phải chờ. Có thể cân nhắc datasource/pool riêng cho workload khác biệt, nhưng mỗi pool tiêu thụ thêm connection budget và tăng độ phức tạp transaction.

Tách pool chỉ hữu ích khi có isolation mục tiêu rõ ràng. Cần kiểm tra transaction manager, routing datasource, consistency và tổng maximum connection của tất cả pool. Không tạo pool riêng cho từng RPC method một cách tùy tiện.

## 11. Metrics cần theo dõi

HikariCP có thể xuất metrics qua Micrometer/Spring Boot Actuator khi được cấu hình và instrument phù hợp.

| Metric | Ý nghĩa |
| --- | --- |
| active connections | Connection đang được mượn |
| idle connections | Connection sẵn sàng trong pool |
| pending threads | Số thread đang chờ connection |
| max connections | Giới hạn pool |
| connection acquisition time | Thời gian chờ lấy connection |
| connection usage time | Thời gian giữ connection |
| timeout count | Số lần không lấy được connection trong thời hạn |
| transaction duration | Thời gian transaction mở |
| query duration | Thời gian truy vấn database |

Kết hợp với gRPC metrics như RPC rate, latency p95/p99, status code, concurrent calls và cancellation. Kết hợp tiếp với database metrics như CPU, I/O, active sessions, lock waits, deadlocks, slow query và replication lag.

Đặt alert theo xu hướng và mức độ ảnh hưởng, ví dụ pending thread kéo dài kèm acquisition latency tăng và RPC UNAVAILABLE tăng. Một spike ngắn ở active=max trong giờ cao điểm chưa đủ kết luận pool sai.

## 12. Load test và tuning có phương pháp

Load test cần mô phỏng phân bố RPC thực tế, không chỉ gọi một method đơn giản:

1. Tạo workload có tỷ lệ query/command/streaming giống production.
2. Mô phỏng payload size và transaction duration thực tế.
3. Tăng concurrency theo từng bước, giữ mỗi mức đủ lâu để ổn định.
4. Ghi throughput, RPC latency p50/p95/p99 và status distribution.
5. Ghi Hikari active/idle/pending, acquisition/usage time và timeout count.
6. Ghi database CPU/I/O, lock wait, slow query và connection count.
7. Lặp lại với số replica tối đa và khi một replica/database node gặp sự cố.
8. Điều chỉnh một biến mỗi lần để hiểu tác động.

Tìm điểm mà throughput không còn tăng nhưng latency, pending hoặc DB contention tăng nhanh. Đó thường là dấu hiệu đã vượt vùng tải hiệu quả. Mục tiêu không phải đạt pool lớn nhất mà đạt throughput cần thiết với latency và error rate ổn định.

## 13. Checklist vận hành

- Pool maximum được tính theo DB connection budget toàn hệ thống.
- Có tính replica tối đa, autoscaling và các pool/worker khác.
- Transaction ngắn, không giữ connection qua network hoặc chờ stream.
- Query/statement/transaction timeout phù hợp với RPC deadline.
- Pool acquisition timeout không vượt ngân sách chờ hợp lý của RPC.
- Hikari active/idle/pending/acquisition/usage/timeout metrics được thu thập.
- Database CPU, I/O, lock wait và slow query được quan sát song song.
- Leak detection chỉ dùng để chẩn đoán; không xem nó là cơ chế tự khắc phục.
- Batch/reporting workload không làm cạn pool của RPC interactive.
- Load test bao gồm concurrency, payload và transaction duration thực tế.
- Retry khi pool cạn có backoff/jitter, giới hạn attempt và deadline tổng.
- Có runbook phân biệt pool exhaustion với database saturation.

Trong **SPRING_GRPC**, connection pool là giới hạn tài nguyên chia sẻ giữa các RPC đang cần database. Hãy sizing theo năng lực database và tổng số replica, giữ transaction ngắn, phối hợp timeout với deadline, rồi dùng pool metrics cùng database metrics để xác định bottleneck. Khi pool đầy, điều quan trọng là tìm xem connection bị giữ lâu, query chậm hay database đã bão hòa trước khi quyết định tăng pool.
