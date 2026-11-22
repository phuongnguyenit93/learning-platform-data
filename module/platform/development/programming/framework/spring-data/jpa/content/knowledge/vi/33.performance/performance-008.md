# Cấu hình connection pool theo tải và thời gian giữ kết nối

Connection pool quản lý một tập hợp kết nối JDBC để ứng dụng có thể mượn và trả kết nối thay vì mở kết nối vật lý mới cho mỗi thao tác database. Trong Spring Boot, HikariCP thường là connection pool được sử dụng khi có mặt trên classpath. Cấu hình pool ảnh hưởng trực tiếp đến thời gian chờ lấy connection, số phiên làm việc đồng thời trên database và khả năng chịu tải của ứng dụng.

Cấu hình tốt cần cân bằng ba yếu tố: lượng công việc đồng thời, thời gian mỗi transaction giữ connection và số connection database có thể phục vụ an toàn. Tăng kích thước pool không tự động làm ứng dụng nhanh hơn; pool quá lớn có thể khiến database chịu thêm cạnh tranh, chuyển ngữ cảnh và áp lực bộ nhớ.

## 1. Connection pool hoạt động như thế nào?

Khi code cần truy cập database, JDBC lấy một connection từ pool. Connection được giữ trong lúc thao tác hoặc transaction cần nó, rồi được trả về pool để request khác dùng lại.

Luồng tổng quát:

1. Ứng dụng yêu cầu connection.
2. Nếu pool có connection rảnh, pool cấp connection đó ngay.
3. Nếu mọi connection đang được sử dụng và pool chưa đạt giới hạn, pool có thể tạo thêm connection.
4. Nếu pool đã đạt giới hạn, request phải chờ connection được trả lại hoặc hết thời gian chờ.
5. Khi công việc hoàn tất, connection được trả về pool thay vì đóng kết nối vật lý.

Trong HikariCP, `maximumPoolSize` là số connection tối đa mà pool được phép duy trì, bao gồm cả connection đang rảnh và đang được sử dụng. Khi pool cạn connection, `getConnection()` chờ tối đa theo `connectionTimeout`; nếu hết thời gian mà vẫn không có connection, ứng dụng nhận lỗi lấy connection.

Một request HTTP không nhất thiết giữ một connection trong toàn bộ thời gian xử lý. Connection thường được lấy khi persistence context cần truy cập database và được giữ theo chính sách quản lý connection của JPA provider, transaction manager và driver. Khi thiết kế tải, hãy đo thời gian connection thực sự bị chiếm dụng, đặc biệt trong các transaction.

## 2. Chọn kích thước pool dựa trên tải

Không nên chọn `maximumPoolSize` chỉ dựa trên số thread của web server hoặc số CPU. Cần xem xét:

- Tốc độ transaction ở giờ cao điểm.
- Thời gian trung bình một transaction giữ connection.
- Tỷ lệ transaction thực sự truy cập database.
- Thời gian query và thời gian chờ khóa.
- Khả năng xử lý đồng thời của database.
- Số instance ứng dụng cùng kết nối tới database.
- Connection dành cho service khác, tác vụ nền, migration và công cụ quản trị.

Có thể dùng định luật Little như một ước lượng ban đầu:

```text
Số connection đồng thời trung bình
    ≈ Tốc độ transaction (transaction/giây)
      × Thời gian giữ connection trung bình (giây)
```

Ví dụ, ứng dụng xử lý trung bình 80 transaction mỗi giây và mỗi transaction giữ connection khoảng 0,12 giây:

```text
80 × 0,12 = 9,6 connection
```

Nhu cầu trung bình xấp xỉ 10 connection đang bận. Đây không phải giá trị cấu hình cuối cùng: giờ cao điểm, phân bố thời gian giữ connection, burst traffic và mức chờ cho phép có thể làm nhu cầu thực tế khác đáng kể. Hãy dùng số liệu production hoặc load test để chọn pool size và quan sát hàng đợi khi tải tăng.

### Tính tổng connection của nhiều instance

`maximumPoolSize` áp dụng cho từng pool trong từng instance. Nếu ứng dụng chạy nhiều pod hoặc VM, tổng connection có thể lớn hơn nhiều so với giá trị cấu hình trên một instance.

Ví dụ database dành ngân sách tối đa 60 connection cho ứng dụng này sau khi đã trừ phần dành cho các client khác. Nếu có 3 instance và mỗi instance đặt pool tối đa 12:

```text
3 instance × 12 connection = 36 connection tối đa
```

Còn 24 connection trong ngân sách đó cho biến động tải hoặc các thành phần liên quan. Khi triển khai autoscaling, phải tính cả số replica tối đa có thể xuất hiện, không chỉ số replica thông thường.

Database có giới hạn connection không đồng nghĩa database xử lý hiệu quả khi tất cả connection đều hoạt động. Nếu pool quá lớn, nhiều query cùng tranh CPU, I/O, buffer, row lock và tài nguyên nội bộ. Khi đó throughput có thể giảm và p95/p99 latency tăng. Hãy tăng pool từng bước và so sánh throughput, latency, lock wait cùng mức sử dụng tài nguyên database.

## 3. Cấu hình HikariCP trong Spring Boot

Spring Boot cho phép cấu hình HikariCP bằng các thuộc tính dưới tiền tố `spring.datasource.hikari`. Ví dụ YAML sau minh họa một cấu hình có pool tối đa 12 connection:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: app
    password: change-me
    hikari:
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 300000
      max-lifetime: 1500000
      keepalive-time: 120000
      leak-detection-threshold: 20000
```

Các con số trên là ví dụ để minh họa đơn vị millisecond và quan hệ giữa các tham số, không phải bộ giá trị phù hợp cho mọi hệ thống. Cần điều chỉnh theo database, hạ tầng mạng, số replica và kết quả đo tải.

Ý nghĩa các thuộc tính:

| Thuộc tính | Tác dụng |
|---|---|
| `maximum-pool-size` | Giới hạn tổng connection của một pool |
| `minimum-idle` | Số connection rảnh tối thiểu mà pool cố duy trì |
| `connection-timeout` | Thời gian tối đa chờ lấy connection từ pool |
| `validation-timeout` | Thời gian tối đa kiểm tra connection còn hợp lệ |
| `idle-timeout` | Thời gian connection rảnh vượt quá mức `minimum-idle` trước khi pool có thể loại bỏ |
| `max-lifetime` | Tuổi thọ tối đa của connection trong pool |
| `keepalive-time` | Chu kỳ kiểm tra/giữ sống connection đang rảnh |
| `leak-detection-threshold` | Ngưỡng ghi log khi connection bị giữ quá lâu |

Nếu chỉ có một datasource, có thể đặt các thuộc tính trên trong file `application.yml` hoặc `application.properties`. Với nhiều datasource, mỗi bean `DataSource` cần được cấu hình đúng pool và đúng nhóm property tương ứng; không giả định một bộ cấu hình tự áp dụng giống nhau cho mọi datasource.

## 4. Hiểu đúng các mốc thời gian

Các tham số thời gian giải quyết những vấn đề khác nhau. Cần phân biệt thời gian chờ connection, thời gian sống của connection và thời gian connection rảnh.

### connectionTimeout

Đây là thời gian tối đa một thread chờ lấy connection khi pool không còn connection rảnh và đã đạt `maximumPoolSize`. Nó không phải query timeout và cũng không giới hạn thời gian SQL chạy.

Đặt quá dài có thể khiến request xếp hàng lâu, chiếm thread ứng dụng rồi mới thất bại. Đặt quá ngắn có thể gây lỗi tạm thời khi tải tăng đột biến dù database vẫn có khả năng phục vụ. Hãy chọn theo deadline của request và mức chờ mà nghiệp vụ chấp nhận.

### maxLifetime

Đây là tuổi thọ tối đa của connection trong pool. HikariCP chủ động loại bỏ connection đã tới tuổi thọ này; connection đang được sử dụng không bị cắt giữa chừng chỉ vì chạm mốc, mà được xử lý khi trả về pool.

Đặt `maxLifetime` thấp hơn giới hạn tuổi thọ connection do database, proxy hoặc hạ tầng mạng áp đặt một khoảng đệm hợp lý. Nếu hạ tầng đóng connection sau một thời gian nhất định nhưng pool giữ connection lâu hơn, ứng dụng có thể nhận connection đã bị phía bên kia đóng.

### idleTimeout và minimumIdle

`idleTimeout` kiểm soát việc loại bỏ connection rảnh vượt quá `minimumIdle` khi pool có nhiều connection hơn mức tối thiểu. Nó chỉ có tác dụng thu hẹp pool khi `minimumIdle < maximumPoolSize`.

Nếu không chỉ định `minimumIdle`, HikariCP mặc định dùng giá trị `maximumPoolSize`, tạo hành vi pool kích thước cố định. Khi muốn pool co giãn theo tải, có thể đặt `minimumIdle` thấp hơn `maximumPoolSize` và cấu hình `idleTimeout` phù hợp. Việc thu hẹp pool không diễn ra chính xác ngay tại từng mili giây; HikariCP kiểm tra theo chu kỳ nội bộ.

### keepaliveTime

`keepaliveTime` giúp kiểm tra và giữ sống connection đang rảnh để giảm khả năng connection bị firewall, proxy hoặc database loại bỏ do idle. HikariCP chỉ thực hiện keepalive trên connection đang rảnh; nó không thể cứu một connection đang bị query treo hoặc đã bị ngắt trong lúc sử dụng.

Giá trị này phải nhỏ hơn `maxLifetime`. Nếu hạ tầng có idle timeout, chọn chu kỳ thấp hơn ngưỡng đó với khoảng đệm phù hợp. Không bật keepalive quá dày vì mỗi lần kiểm tra cũng tạo thêm hoạt động trên database và mạng.

### validationTimeout

Đây là giới hạn thời gian kiểm tra connection còn hợp lệ. Giá trị này phải nhỏ hơn `connectionTimeout`. Với JDBC driver hỗ trợ JDBC4, HikariCP thường sử dụng `Connection.isValid()`; tránh tự đặt `connectionTestQuery` nếu driver đã hỗ trợ cách kiểm tra chuẩn.

## 5. Phân biệt pool timeout với query timeout và transaction timeout

Một lỗi phổ biến là thấy request chờ lâu rồi chỉ tăng `connectionTimeout`. Nhưng pool timeout và query timeout là hai vấn đề riêng:

- **Connection acquisition timeout:** chờ lấy một connection từ pool.
- **Query timeout:** giới hạn thời gian một câu SQL được phép chạy.
- **Transaction timeout:** giới hạn thời gian transaction được phép tồn tại theo transaction manager.
- **Network/socket timeout:** giới hạn thời gian chờ dữ liệu qua kết nối mạng, tùy driver và cấu hình.

Ví dụ, pool có thể cấp connection ngay nhưng query chạy 40 giây do thiếu index hoặc bị chờ lock. Tăng `connectionTimeout` không giải quyết query chậm. Ngược lại, database có thể khỏe nhưng mọi connection bị giữ bởi transaction dài; khi đó query timeout của một câu SQL riêng lẻ cũng không giải quyết việc pool hết connection.

Hãy thiết kế timeout theo thứ tự deadline của hệ thống. Thời gian chờ lấy connection nên đủ ngắn để request có thể thất bại có kiểm soát trước khi vượt deadline tổng. Query và transaction cần timeout riêng phù hợp với loại công việc.

## 6. Giữ transaction ngắn để trả connection sớm

Thời gian một transaction giữ connection có ảnh hưởng lớn đến số connection cần thiết. Một transaction không chỉ gồm thời gian SQL chạy; nếu connection được giữ trong suốt transaction, mọi công việc Java nằm giữa các câu query cũng có thể làm connection bị chiếm lâu.

Ví dụ không nên làm:

```java
@Transactional
public void checkout(Long orderId) {
    PurchaseOrder order = repository.findById(orderId)
            .orElseThrow();

    paymentGateway.charge(order); // Gọi mạng bên ngoài
    shippingClient.createShipment(order); // Gọi mạng bên ngoài

    order.markPaid();
}
```

Hai lời gọi mạng có thể mất nhiều giây hoặc timeout, khiến transaction và connection bị giữ trong thời gian dài. Nếu phù hợp với nghiệp vụ, hãy tách phần gọi dịch vụ bên ngoài khỏi transaction database, dùng state machine, saga hoặc outbox để phối hợp các bước. Mỗi transaction nên bao quanh một thay đổi dữ liệu có phạm vi rõ ràng và hoàn tất sớm.

Cũng cần chú ý tới:

- Không chờ người dùng nhập liệu trong transaction.
- Không sleep, retry dài hoặc gọi API bên ngoài khi đang giữ connection.
- Tránh truy vấn N+1 làm transaction kéo dài.
- Với streaming query hoặc cursor, đóng stream đúng cách vì tài nguyên có thể được giữ đến khi stream đóng.
- Không giữ connection thủ công qua nhiều request.

## 7. Theo dõi pool bằng metrics

Không thể chọn pool size chính xác chỉ bằng phỏng đoán. Hãy quan sát pool khi chạy tải thực tế hoặc load test.

Các chỉ số HikariCP thường cần theo dõi:

| Metric | Ý nghĩa |
|---|---|
| Active connections | Số connection đang được mượn |
| Idle connections | Số connection đang rảnh |
| Pending threads | Số thread đang chờ connection |
| Maximum connections | Giới hạn pool hiện tại |
| Connection acquisition time | Thời gian chờ lấy connection |
| Connection usage time | Thời gian connection được giữ trước khi trả về |
| Connection timeout count | Số lần lấy connection thất bại do timeout |

Khi dùng Spring Boot Actuator và Micrometer, các metrics datasource/pool có thể được xuất tới hệ thống giám sát tùy cấu hình. Tên metric cụ thể và tag phụ thuộc phiên bản cùng registry; hãy kiểm tra endpoint metrics hoặc dashboard thực tế của ứng dụng.

Một số dấu hiệu cần điều tra:

- Active luôn bằng maximum và pending tăng: pool thường xuyên cạn connection.
- Acquisition latency tăng nhưng database CPU thấp: xem transaction có giữ connection quá lâu, connection leak hoặc pool chưa được cấu hình phù hợp.
- Active cao, database CPU/lock wait cũng cao: database có thể là nút thắt; tăng pool có thể làm tình trạng xấu hơn.
- Idle cao và active thấp: pool có thể lớn hơn nhu cầu hiện tại, nhưng cần xem cả peak load trước khi giảm.
- Usage time tăng: kiểm tra query chậm, lock, transaction dài và lời gọi bên ngoài trong transaction.

Đối chiếu metrics pool với CPU, I/O, active sessions, lock wait, query latency p95/p99 và throughput ở database. Metrics pool đơn lẻ không cho biết nguyên nhân gốc.

## 8. Phát hiện connection leak

Connection leak xảy ra khi ứng dụng mượn connection nhưng không trả lại đúng lúc. Pool dần cạn và các thread khác phải chờ.

Khi dùng Spring Data JPA và transaction manager chuẩn, việc lấy/trả connection thường do framework quản lý. Tuy nhiên, leak vẫn có thể xuất hiện khi code JDBC thủ công, stream không đóng, transaction bị kéo dài hoặc tài nguyên được giữ sai cách.

Với JDBC thuần, dùng try-with-resources:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                     "select id from customer where id = ?")) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            long id = resultSet.getLong("id");
            // Xử lý kết quả
        }
    }
}
```

Khi dùng `DataSourceUtils` hoặc Spring JDBC, tuân theo cách quản lý tài nguyên của Spring; không tự đóng connection đang được transaction hiện tại quản lý. Không tự đóng `EntityManager` được inject bởi Spring.

Có thể bật `leak-detection-threshold` trong HikariCP để ghi log khi connection bị giữ lâu hơn ngưỡng. Đây là công cụ chẩn đoán: nó không tự giải phóng connection và một transaction hợp lệ nhưng dài cũng có thể tạo cảnh báo. Hãy dùng stack trace trong log để tìm nơi mượn connection, rồi kiểm tra transaction boundary và đường trả tài nguyên.

## 9. Quy trình tinh chỉnh có kiểm soát

Một quy trình thực tế có thể thực hiện theo các bước:

1. **Đo tải nền:** thu thập transaction/giây, số replica, thời gian giữ connection, query latency và giới hạn connection database.
2. **Ước lượng nhu cầu:** dùng throughput nhân với thời gian giữ connection để tính số connection bận trung bình; cộng biên độ phù hợp với burst và biến động.
3. **Đặt ngân sách toàn hệ thống:** nhân pool size mỗi instance với số replica tối đa; trừ phần connection dành cho các ứng dụng và tác vụ khác.
4. **Chọn timeout:** đặt connection acquisition timeout theo request deadline; đặt max lifetime và keepalive theo giới hạn của database, proxy và mạng.
5. **Chạy load test:** tăng tải theo từng mức, theo dõi pending, active, acquisition latency, throughput, query latency và database resource.
6. **Điều chỉnh từng tham số:** thay một nhóm nhỏ thông số mỗi lần để xác định tác động, tránh tăng pool size đồng thời với nhiều thay đổi khác.
7. **Kiểm tra khi lỗi:** mô phỏng database restart, network interruption, traffic burst và transaction dài để xem ứng dụng phục hồi ra sao.

Không có một con số pool size chung cho mọi ứng dụng. Giá trị phù hợp là giá trị đáp ứng throughput và latency mục tiêu trong giới hạn tài nguyên database, kể cả khi hệ thống chạy đủ số replica dự kiến.

## 10. Ghi nhớ

Connection pool giúp tái sử dụng JDBC connection và giới hạn số kết nối đồng thời từ ứng dụng tới database. Hãy cấu hình `maximumPoolSize` theo throughput, thời gian giữ connection và ngân sách tổng của mọi instance. Phân biệt `connectionTimeout`, `maxLifetime`, `idleTimeout`, `keepaliveTime` với query/transaction timeout; giữ transaction ngắn, theo dõi active/idle/pending và usage time, đồng thời điều tra leak trước khi tăng pool.