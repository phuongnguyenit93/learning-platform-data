# HikariCP, kích thước pool và giới hạn max_connections phía server

Spring Boot thường dùng HikariCP để quản lý các kết nối JDBC đến MySQL. Pool giúp ứng dụng tái sử dụng kết nối, tránh tạo và xác thực một kết nối mới cho từng câu lệnh. Tuy nhiên, pool không tạo thêm năng lực xử lý cho MySQL. Nếu mỗi instance ứng dụng mở quá nhiều connection, tổng số kết nối từ tất cả instance có thể vượt max_connections, làm MySQL từ chối kết nối mới hoặc tiêu tốn tài nguyên cho các phiên đang nhàn rỗi.

Định cỡ pool cần xét đồng thời workload của ứng dụng, số instance chạy song song, số datasource, các dịch vụ khác dùng chung MySQL và ngân sách kết nối dành cho quản trị. Mục tiêu là duy trì đủ connection cho lượng truy vấn đồng thời có ích, trong khi không làm database quá tải vì quá nhiều phiên.

## 1. Connection pool hoạt động như thế nào?

Khi một thành phần cần truy cập database, HikariCP cấp một connection đang rảnh từ pool. Sau khi hoàn tất công việc, ứng dụng đóng connection bằng Connection.close(). Với connection lấy từ pool, thao tác này thường trả connection về pool để tái sử dụng, thay vì đóng socket vật lý ngay lập tức.

~~~mermaid
flowchart TD
    A["Spring service / repository"] --> B["DataSource.getConnection()"]
    B --> C{"Có connection rảnh?"}
    C -->|Có| D["Cấp connection cho request"]
    C -->|Không, pool còn chỗ| E["Tạo physical connection"]
    C -->|Đã đạt maximumPoolSize| F["Chờ đến connectionTimeout"]
    E --> D
    D --> G["Thực thi SQL / transaction"]
    G --> H["Connection.close()"]
    H --> I["Trả connection về pool"]
    F -->|Có connection được trả| D
    F -->|Hết thời gian| J["SQLException: timeout lấy connection"]
~~~

Pool quản lý các connection đang được ứng dụng mượn và các connection đang chờ. Một connection đang chạy truy vấn hoặc đang ở trong transaction thường được xem là active. Connection không được mượn có thể ở trạng thái idle và sẵn sàng cấp cho request tiếp theo.

Các khái niệm cần phân biệt:

- **Active connection:** connection đang được ứng dụng giữ để thực hiện công việc.
- **Idle connection:** connection đang nằm trong pool và chưa được ứng dụng mượn.
- **Pending thread:** luồng đang chờ lấy connection vì pool chưa cấp được.
- **Physical connection:** phiên kết nối thực tế đến MySQL.
- **Pool capacity:** số connection tối đa mà một pool có thể duy trì theo cấu hình.

maximumPoolSize giới hạn tổng số connection active cộng idle của một HikariCP pool. Đây là giới hạn của từng pool trong từng tiến trình ứng dụng, không phải giới hạn tổng của toàn hệ thống.

## 2. HikariCP trong Spring Boot

Spring Boot thường tự cấu hình HikariCP khi có JDBC starter và HikariCP trên classpath. Cấu hình cơ bản nằm dưới spring.datasource.hikari.

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://mysql.internal.example:3306/shop
    username: shop_app
    password: DB_PASSWORD_FROM_SECRET_MANAGER
    hikari:
      pool-name: shop-main-pool
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1500000
~~~

Các giá trị trên chỉ là ví dụ minh họa. Cần thay bằng giá trị đã được đo trên workload thật và kiểm tra các giới hạn của phiên bản HikariCP đang dùng. Secret nên được cấp qua secret manager hoặc cơ chế cấu hình an toàn của môi trường.

Nếu không chỉ định pool implementation khác, Spring Boot thường chọn HikariCP khi dependency có mặt. Có thể kiểm tra dependency tree để xác nhận phiên bản HikariCP thực tế được đóng gói, thay vì chỉ dựa vào file cấu hình.

Trong ứng dụng có nhiều datasource, mỗi datasource có thể có pool riêng. Ví dụ, datasource đọc và datasource ghi có hai maximumPoolSize khác nhau; tổng kết nối tiềm năng phải cộng cả hai.

## 3. Các cấu hình HikariCP quan trọng

| Thuộc tính | Ý nghĩa | Cách chọn |
|---|---|---|
| maximumPoolSize | Số connection tối đa trong một pool, gồm active và idle | Định cỡ theo ngân sách server và tải đo được |
| minimumIdle | Số connection idle tối thiểu pool cố gắng duy trì | Đặt thấp hơn maximumPoolSize nếu muốn pool co giãn; nếu không đặt, HikariCP mặc định thường bằng maximumPoolSize |
| connectionTimeout | Thời gian tối đa chờ lấy connection từ pool | Chọn theo latency/SLO của ứng dụng; quá dài làm request bị treo lâu |
| validationTimeout | Thời gian tối đa cho kiểm tra connection | Phải nhỏ hơn connectionTimeout |
| idleTimeout | Thời gian idle trước khi connection dư có thể bị loại | Chỉ có tác dụng co giãn khi minimumIdle nhỏ hơn maximumPoolSize |
| maxLifetime | Tuổi thọ tối đa của physical connection trong pool | Đặt thấp hơn giới hạn tuổi thọ connection của DB/proxy/network |
| keepaliveTime | Kiểm tra/giữ connection idle khỏi bị ngắt bởi hạ tầng | Chỉ bật khi cần; phải nhỏ hơn maxLifetime |
| leakDetectionThreshold | Cảnh báo connection bị giữ lâu hơn ngưỡng | Dùng hỗ trợ điều tra; cảnh báo không tự chứng minh có leak |
| initializationFailTimeout | Cách pool xử lý khi khởi tạo không thể kết nối | Chọn theo chính sách startup và khả năng chịu lỗi của dịch vụ |

### 3.1. maximumPoolSize và minimumIdle

maximumPoolSize là trần connection của pool. Khi tất cả connection đang được sử dụng và pool đã đạt trần, request tiếp theo phải chờ. Nếu không có connection được trả về trước connectionTimeout, HikariCP ném lỗi timeout.

minimumIdle điều khiển số connection idle mà pool cố gắng duy trì. Nếu không cấu hình, HikariCP thường sử dụng maximumPoolSize làm minimumIdle, tạo pool có kích thước cố định. Đặt minimumIdle thấp hơn maximum có thể giúp pool giảm connection khi tải thấp, nhưng cũng có thể cần thời gian mở thêm connection khi tải tăng.

Không tăng maximumPoolSize chỉ vì thấy pending thread. Pending có thể là dấu hiệu truy vấn chậm, transaction giữ connection quá lâu, database quá tải hoặc ứng dụng không trả connection đúng cách. Hãy tìm nguyên nhân trước khi tăng pool.

### 3.2. Timeout và tuổi thọ connection

connectionTimeout là thời gian chờ lấy connection, không phải thời gian tối đa chạy một câu SQL. Timeout truy vấn cần được quản lý riêng ở JDBC statement, transaction, framework hoặc server.

maxLifetime nên ngắn hơn giới hạn tuổi thọ connection của MySQL, proxy, load balancer hoặc firewall. Khi đạt tuổi thọ, HikariCP loại connection khi nó không được sử dụng; connection đang được mượn không bị đóng giữa một thao tác chỉ vì đã chạm maxLifetime.

keepaliveTime chỉ tác động đến connection idle. Không đặt keepalive lớn hơn hoặc bằng maxLifetime. Nếu hạ tầng không có idle timeout gây vấn đề, không nhất thiết phải bật keepalive.

leakDetectionThreshold giúp phát hiện code có thể đã giữ connection quá lâu. Một transaction hợp lệ nhưng chạy lâu cũng có thể tạo cảnh báo. Dùng stack trace và thời gian thực thi để điều tra; không hạ ngưỡng đến mức sinh cảnh báo liên tục.

## 4. MySQL max_connections là giới hạn toàn server

max_connections là số client connection đồng thời tối đa mà MySQL server cho phép. Giá trị này áp dụng cho toàn instance, không chỉ một ứng dụng hoặc một pool. Khi đã đạt giới hạn, kết nối mới có thể bị từ chối với lỗi kiểu Too many connections.

Kiểm tra giới hạn và mức sử dụng:

~~~sql
SHOW VARIABLES LIKE 'max_connections';

SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Connection_errors_max_connections'
);
~~~

Ý nghĩa:

- max_connections: giới hạn cấu hình của server.
- Threads_connected: số client connection hiện đang kết nối.
- Threads_running: số thread đang thực thi công việc, không phải tổng connection.
- Max_used_connections: số connection đồng thời cao nhất kể từ khi server khởi động hoặc status được reset.
- Connection_errors_max_connections: số lần kết nối bị từ chối do đạt giới hạn max connections.

Threads_connected cao không đồng nghĩa tất cả connection đều đang chạy truy vấn. Pool có thể giữ nhiều connection idle. Ngược lại, Threads_running cao trong thời gian dài có thể cho thấy database đang chịu tải thực thi lớn.

Có thể xem chi tiết connection bằng:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Hoặc truy vấn Performance Schema/sys schema nếu đã bật và có quyền phù hợp. Khi điều tra, phân loại connection theo user, host, database, trạng thái và thời gian chạy. Không chia sẻ kết quả process list nếu có thông tin nhạy cảm.

## 5. Tính ngân sách connection cho toàn hệ thống

Không thể đặt maximumPoolSize bằng max_connections vì MySQL còn được dùng bởi nhiều tiến trình khác. Cần tính tổng số connection tiềm năng từ tất cả pool và dự phòng cho vận hành.

Một cách lập ngân sách:

\[
C_{app} = \sum_{i=1}^{n} R_i \times P_i
\]

Trong đó:

- R_i là số replica/instance chạy tiến trình ứng dụng loại i.
- P_i là maximumPoolSize của một pool thuộc tiến trình đó.

Sau đó:

\[
C_{planned} = C_{app} + C_{jobs} + C_{ops} + C_{other} + C_{reserve}
\]

C_jobs là kết nối từ worker/batch, C_ops là công cụ quản trị, C_other là monitoring, migration hoặc dịch vụ khác, và C_reserve là phần dự phòng cho deploy, failover và điều tra sự cố.

Ví dụ một hệ thống có:

| Nguồn | Số tiến trình | Pool tối đa mỗi tiến trình | Connection tối đa |
|---|---:|---:|---:|
| API service | 4 | 12 | 48 |
| Worker service | 3 | 5 | 15 |
| Reporting service | 2 | 4 | 8 |
| Tổng connection từ pool ứng dụng | | | 71 |
| Batch và công cụ vận hành | | | 12 |
| Monitoring, migration và dịch vụ khác | | | 7 |
| Dự phòng deploy/failover | | | 20 |
| Tổng ngân sách dự kiến | | | 110 |

Nếu MySQL có max_connections = 150, ngân sách ví dụ 110 để lại khoảng trống cho tải đột biến và các tiến trình chưa được liệt kê. Đây chỉ là minh họa phép tính; mức dự phòng phải dựa trên mô hình triển khai và SLO thực tế.

Khi có hai datasource trong cùng một ứng dụng, cộng maximum của cả hai. Khi chạy rolling deployment, old và new replicas có thể cùng tồn tại trong một khoảng thời gian; cần tính connection của cả hai nhóm. Khi failover sang một MySQL instance khác, mỗi server có ngân sách riêng, nhưng ứng dụng có thể đồng thời giữ connection cũ và tạo connection mới trong thời gian chuyển đổi.

## 6. Định cỡ pool theo workload

Pool size không nên bằng số HTTP thread, số CPU hay số user online. Một request có thể không truy cập DB, có thể chạy nhiều truy vấn tuần tự trên một connection, hoặc có thể giữ connection trong lúc gọi dịch vụ ngoài. Cần đo thời gian connection thực sự bị giữ và mức độ song song có ích đối với MySQL.

### 6.1. Bắt đầu bằng tải thực tế

Thu thập:

- Throughput yêu cầu và transaction mỗi giây.
- Tỷ lệ request có truy cập MySQL.
- Thời gian giữ connection trung bình và p95/p99.
- Số truy vấn chạy đồng thời và thời gian thực thi.
- CPU, I/O, lock wait, buffer pool và Threads_running của MySQL.
- Active, idle, pending, timeout và acquisition latency của HikariCP.

Định luật Little có thể giúp ước lượng số công việc đồng thời trung bình:

\[
L = \lambda \times W
\]

Trong đó L là số công việc trung bình đang diễn ra, lambda là tốc độ đến (request hoặc transaction mỗi giây) và W là thời gian trung bình một công việc giữ tài nguyên (giây). Ví dụ, 80 transaction DB mỗi giây, mỗi transaction giữ connection trung bình 0,05 giây, tương ứng khoảng 4 connection active trung bình. Đây là điểm xuất phát để thử tải, không phải con số pool tối ưu cuối cùng.

### 6.2. Tăng dần và quan sát điểm bão hòa

Thử các mức pool nhỏ rồi tăng dần trong môi trường gần production. Ở mỗi mức, đo throughput, latency, CPU, I/O, lock wait, active connection và pending thread.

Khi tăng pool mà throughput không tăng nhưng latency, CPU hoặc lock wait tăng, database có thể đã đạt điểm bão hòa. Tiếp tục tăng connection có thể làm hiệu năng xấu hơn do context switching, tranh chấp khóa và bộ nhớ tiêu thụ cho mỗi phiên.

Một nguyên tắc thực tế là bắt đầu với pool vừa phải, sau đó dùng benchmark để tìm điểm mà database đạt throughput tốt với latency ổn định. Định cỡ riêng cho API, worker và reporting nếu workload của chúng khác nhau.

### 6.3. Pool-locking và nested connection

HikariCP documentation có công thức tham khảo để tránh deadlock khi nhiều thread có thể đồng thời giữ nhiều connection:

\[
Pool_{min} = T_n \times (C_m - 1) + 1
\]

Trong đó T_n là số thread đồng thời có thể giữ connection và C_m là số connection tối đa một thread có thể giữ cùng lúc. Công thức này là điều kiện tối thiểu cho tình huống pool-locking do nested acquisition; nó không phải công thức chọn pool tối ưu cho throughput.

Ví dụ, nếu 8 thread có thể mỗi thread giữ tối đa 2 connection cùng lúc, giá trị theo công thức là 8 x (2 - 1) + 1 = 9. Tuy nhiên, thiết kế tốt hơn thường là tránh lấy connection lồng nhau hoặc giữ một connection trong lúc chờ một tác vụ khác. Không tăng pool theo công thức này nếu ứng dụng thực tế chỉ cần một connection cho mỗi transaction.

## 7. Quản lý vòng đời connection trong Spring và JPA

Một connection cần được trả về pool ngay khi công việc database hoàn tất. Với JDBC thuần, dùng try-with-resources:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "SELECT status FROM orders WHERE order_id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            String status = resultSet.getString("status");
        }
    }
}
~~~

Với Spring Data JPA, transaction thường được quản lý qua @Transactional:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Order findOrder(long orderId) {
        return repository.findById(orderId)
            .orElseThrow();
    }
}
~~~

Không giữ transaction mở trong lúc gọi HTTP service, chờ người dùng, xử lý file lớn hoặc thực hiện tác vụ lâu không liên quan đến database. Một transaction kéo dài sẽ giữ connection và có thể giữ lock, làm pool nhanh chóng cạn khi tải tăng.

Kiểm tra Open Session in View (OSIV). Nếu persistence context được giữ đến cuối HTTP request, truy vấn lazy loading trong lúc serialize response có thể tiếp tục dùng database sau khi service method đã kết thúc. Với ứng dụng API, cân nhắc tắt OSIV và tải dữ liệu cần thiết trong transaction/service layer, sau đó ánh xạ sang DTO.

Tránh:

- Lưu Connection, EntityManager hoặc JDBC resource vào biến static hay singleton.
- Tự gọi close() trên connection do Spring transaction manager đang quản lý nếu không đúng lifecycle.
- Giữ connection trong khi thực hiện công việc ngoài DB.
- Mở transaction lồng nhau không cần thiết hoặc dùng propagation làm giữ nhiều connection.
- Chạy truy vấn N+1 khiến connection bị giữ lâu và tạo nhiều round trip.

## 8. Quan sát HikariCP và phát hiện pool exhaustion

HikariCP có thể phát metric qua Micrometer khi ứng dụng Spring Boot đã tích hợp Actuator/Micrometer. Các metric thường hữu ích:

| Metric | Ý nghĩa |
|---|---|
| Active connections | Connection đang được mượn |
| Idle connections | Connection đang rảnh trong pool |
| Pending threads | Số thread đang chờ connection |
| Total connections | Tổng connection hiện có trong pool |
| Connection acquisition time | Thời gian chờ lấy connection |
| Usage duration | Thời gian connection được giữ |
| Timeout count | Số lần không lấy được connection trong timeout |

Các tên metric cụ thể phụ thuộc phiên bản HikariCP, Micrometer và cách đặt tên pool. Gắn pool-name riêng cho từng datasource để phân biệt dashboard.

Dấu hiệu pool exhaustion:

- Active connections thường xuyên chạm maximumPoolSize.
- Pending threads tăng và duy trì.
- Acquisition latency tăng.
- Request bắt đầu timeout khi lấy connection.
- MySQL có thể không quá tải CPU nhưng connection bị giữ lâu bởi transaction hoặc code path.

Để điều tra:

1. Xác định pool nào cạn bằng pool-name.
2. Xem active, idle, pending, acquisition time và usage duration.
3. Tìm transaction dài, truy vấn chậm, lock wait và connection leak.
4. So sánh Threads_connected, Threads_running và process list trên MySQL.
5. Kiểm tra số instance ứng dụng và pool capacity sau deploy/autoscaling.
6. Sửa truy vấn hoặc vòng đời connection trước khi cân nhắc tăng pool.

leakDetectionThreshold có thể giúp ghi stack trace nơi connection được mượn quá lâu. Một cảnh báo có thể chỉ ra transaction hợp lệ đang chậm; cần đối chiếu với usage duration và log transaction trước khi kết luận có rò rỉ.

## 9. Điều chỉnh max_connections trên MySQL

Khi đã có ngân sách kết nối và bằng chứng cho thấy giới hạn server quá thấp, DBA có thể xem xét tăng max_connections. Trước đó phải đánh giá RAM, CPU, cấu hình per-connection buffer, số thread và giới hạn tài nguyên của hệ điều hành.

Kiểm tra giá trị hiện tại:

~~~sql
SHOW VARIABLES LIKE 'max_connections';
~~~

Trong phiên bản hỗ trợ thay đổi động và tài khoản có quyền phù hợp, có thể thay đổi giá trị runtime:

~~~sql
SET GLOBAL max_connections = 180;
~~~

Thay đổi runtime có thể không tồn tại sau khi restart. Để duy trì, cấu hình trong file cấu hình MySQL hoặc dùng cơ chế persistence được phiên bản hỗ trợ và quy trình vận hành cho phép. Sau thay đổi, kiểm tra lại biến và theo dõi bộ nhớ, connection count, latency.

Không chọn một giá trị rất lớn chỉ để loại bỏ lỗi Too many connections. Mỗi connection có chi phí bộ nhớ và tài nguyên; một số buffer được cấp phát theo phiên hoặc theo truy vấn. Giới hạn cao có thể khiến máy chủ cạn RAM khi có nhiều phiên hoạt động cùng lúc.

Ngoài max_connections, có thể có giới hạn theo tài khoản như max_user_connections, giới hạn từ proxy hoặc giới hạn của dịch vụ cloud. Khi một ứng dụng bị từ chối kết nối, kiểm tra cả các lớp này.

## 10. Lập ví dụ ngân sách với autoscaling

Giả sử API service chạy tối đa 6 replica khi autoscaling, mỗi replica có một pool HikariCP tối đa 10 connection. Worker chạy tối đa 4 replica, mỗi pool tối đa 4 connection. Reporting chạy 2 replica, mỗi pool tối đa 3 connection.

\[
C_{app} = 6 \times 10 + 4 \times 4 + 2 \times 3 = 82
\]

Nếu công cụ backup, monitoring, migration và quản trị cần 15 connection, dự phòng thêm 20, tổng ngân sách là:

\[
C_{planned} = 82 + 15 + 20 = 117
\]

Với max_connections là 140, còn khoảng 23 connection ngoài ngân sách dự kiến. Cần xác nhận con số này đủ cho các tác vụ phát sinh và giới hạn thực tế của dịch vụ.

Nếu autoscaling có thể tăng API lên 10 replica, ngân sách ứng dụng thay đổi:

\[
C_{app} = 10 \times 10 + 4 \times 4 + 2 \times 3 = 122
\]

Khi cộng 35 connection cho vận hành và dự phòng, tổng là 157, vượt max_connections = 140. Vì vậy, cần định cỡ lại pool theo tải thực, đặt giới hạn autoscaling phù hợp hoặc điều chỉnh năng lực MySQL sau khi đánh giá tài nguyên. Không chỉ tính theo số replica bình thường; phải tính theo mức autoscaling tối đa và tình huống rolling deployment.

## 11. Checklist định cỡ và vận hành

### Trước khi triển khai

- [ ] Liệt kê mọi ứng dụng, worker, datasource và pool kết nối đến MySQL.
- [ ] Tính số replica tối đa, gồm autoscaling và rolling deployment.
- [ ] Cộng tổng maximumPoolSize của mọi pool.
- [ ] Dành ngân sách cho backup, monitoring, migration, DBA và các dịch vụ khác.
- [ ] Đối chiếu tổng ngân sách với max_connections và giới hạn theo user/proxy.
- [ ] Kiểm tra RAM và chi phí connection trên MySQL.
- [ ] Đo tải thực tế và thử nhiều mức pool.
- [ ] Cấu hình timeout và vòng đời connection phù hợp với hạ tầng.

### Khi vận hành

- [ ] Theo dõi active, idle, pending, total, acquisition latency và timeout.
- [ ] Theo dõi Threads_connected, Threads_running, Max_used_connections.
- [ ] Cảnh báo khi connection sử dụng gần giới hạn trong thời gian kéo dài.
- [ ] Điều tra transaction dài, slow query, lock wait và leak trước khi tăng pool.
- [ ] Tính lại ngân sách khi tăng replica, thêm datasource hoặc triển khai dịch vụ mới.
- [ ] Kiểm thử failover/restart để xác nhận pool tái tạo connection đúng cách.

## 12. Tình huống thực hành

Một ứng dụng Spring Boot chạy 5 replica. Mỗi replica có HikariCP với maximumPoolSize = 30. MySQL đặt max_connections = 160. Ngoài ứng dụng còn có worker và công cụ quản trị cần khoảng 25 connection; nhóm vận hành muốn giữ 20 connection dự phòng.

Hãy tính:

1. Tổng số connection tối đa từ API pool.
2. Tổng ngân sách khi cộng worker, công cụ và dự phòng.
3. Mức vượt hoặc còn lại so với max_connections.
4. Thay đổi nào cần xem xét nếu autoscaling có thể tăng API lên 7 replica.

API có thể mở tối đa 5 x 30 = 150 connection. Khi cộng 25 và 20, ngân sách là 195, vượt giới hạn 160. Nếu API tăng lên 7 replica, riêng API có thể cần 210 connection, chưa tính các nguồn khác. Cần định cỡ lại pool theo tải thực, đặt giới hạn autoscaling phù hợp hoặc điều chỉnh năng lực server sau khi đánh giá tài nguyên. Tăng max_connections đơn thuần không giải quyết được nguyên nhân nếu MySQL không đủ năng lực xử lý số phiên đó.

## 13. Câu hỏi tự kiểm tra

1. maximumPoolSize giới hạn connection nào trong một HikariCP pool?
2. Vì sao tổng connection cần tính theo số replica ứng dụng và số datasource?
3. Threads_connected khác Threads_running như thế nào?
4. Khi active connection chạm maximumPoolSize và pending tăng, cần kiểm tra điều gì trước khi tăng pool?
5. Vì sao connectionTimeout không phải query timeout?
6. maxLifetime cần được so sánh với timeout nào của MySQL hoặc hạ tầng?
7. Vì sao minimumIdle mặc định bằng maximumPoolSize có thể tạo pool kích thước cố định?
8. Vì sao tăng max_connections quá cao có thể làm MySQL thiếu tài nguyên?
9. Công thức pool-locking giải quyết tình huống nào và vì sao không phải công thức tối ưu throughput?
10. Sau khi autoscaling tăng số replica, cần tính lại ngân sách kết nối ra sao?

Định cỡ HikariCP là bài toán phối hợp giữa ứng dụng và database. Hãy tính tổng connection tiềm năng từ mọi tiến trình, dành ngân sách cho vận hành, đo tải để tìm pool size phù hợp và theo dõi cả metric của HikariCP lẫn trạng thái MySQL. Khi connection được trả đúng lúc và pool không vượt quá năng lực database, ứng dụng sẽ ổn định hơn trong cả tải bình thường lẫn các đợt tăng tải.
