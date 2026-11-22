# Ghi log SQL và tham số theo môi trường

## 1. Mục tiêu của SQL logging

Khi một thao tác repository thất bại hoặc chạy chậm, log ở tầng service đôi khi chưa đủ để tìm nguyên nhân. Người phát triển cần biết câu SQL nào được gửi tới database, thao tác mất bao lâu, driver trả lỗi gì và request nào đã tạo ra truy vấn đó.

Trong Spring Data R2DBC, cần phân biệt các loại thông tin:

- **SQL statement:** câu lệnh được gửi tới database, thường vẫn chứa bind marker.
- **Bind parameter:** giá trị thực tế được gắn vào marker, ví dụ ID, trạng thái hoặc thời điểm.
- **Execution metadata:** thời gian thực thi, số hàng bị tác động, trạng thái hoàn tất hoặc lỗi.
- **Request context:** trace ID, correlation ID, tenant alias hoặc mã nghiệp vụ để nối log.
- **Database error:** exception type, SQL state và vendor error code nếu driver cung cấp.

Không phải logger nào cũng ghi được tất cả các loại thông tin này. Spring có thể ghi SQL statement ở mức DEBUG; việc ghi giá trị bind thường cần instrumentation riêng của driver hoặc proxy. Cấu hình logging phải phù hợp môi trường vì SQL và tham số có thể chứa dữ liệu nhạy cảm.

## 2. SQL logging và parameter logging khác nhau

Giả sử ứng dụng chạy:

```java
databaseClient.sql("""
        SELECT id, email_address
        FROM customer
        WHERE email_address = :email
        """)
        .bind("email", email)
        .fetch()
        .one();
```

Một log SQL có thể hiển thị:

```text
Executing SQL statement [
    SELECT id, email_address
    FROM customer
    WHERE email_address = ?
]
```

Log này cho biết câu SQL và marker mà driver sử dụng. Nó không nhất thiết cho biết giá trị thực tế của email.

Parameter logging có thể ghi thêm thông tin như:

```text
parameter[0]: type=String, value=lan@example.com
```

Giá trị bind có thể giúp tái hiện lỗi dữ liệu, nhưng cũng có thể chứa email, số điện thoại, địa chỉ, token hoặc thông tin tài chính. Không nên bật parameter logging rộng rãi trong production.

Log SQL có marker hữu ích để tìm lỗi cú pháp và kiểm tra query shape. Parameter log cần được quản lý như dữ liệu ứng dụng, với chính sách truy cập, retention và masking phù hợp.

## 3. Logger SQL của Spring Framework

Spring Framework DatabaseClient ghi câu SQL ở mức DEBUG qua package logging của R2DBC core. Có thể bật logger:

```yaml
logging:
  level:
    org.springframework.r2dbc.core: DEBUG
```

Khi logger được bật, log thường cho biết câu SQL đang được thực thi. Tên class logger cụ thể có thể thay đổi theo implementation/version, nhưng package org.springframework.r2dbc.core là điểm cấu hình phù hợp cho SQL log của Spring DatabaseClient.

Có thể dùng thêm logger Spring Data khi cần quan sát hoạt động repository/mapping:

```yaml
logging:
  level:
    org.springframework.data.r2dbc: DEBUG
```

Logger Spring Data giúp chẩn đoán hoạt động ở tầng Spring Data. Không mặc định rằng bật logger này sẽ ghi mọi giá trị bind hoặc toàn bộ SQL do driver thực thi.

### 3.1. Không bật TRACE một cách mặc định

Một số thư viện và driver có log chi tiết hơn ở TRACE. Mức TRACE có thể tạo lượng log rất lớn, đặc biệt khi ứng dụng có nhiều truy vấn hoặc nhiều connection.

Chỉ bật TRACE trong một khoảng thời gian ngắn khi đã xác định đúng logger cần theo dõi. Trước khi bật, hãy kiểm tra logger đó có thể ghi parameter, payload hoặc thông tin kết nối nhạy cảm hay không.

### 3.2. Spring không có một cờ chung để in mọi bind value

Không nên giả định đặt org.springframework.r2dbc.core=DEBUG sẽ in đầy đủ giá trị bind. DatabaseClient log câu SQL ở lớp Spring; giá trị bind được truyền qua API R2DBC Statement tới driver.

R2DBC SPI không định nghĩa một property logging chung để mọi driver tự in tất cả tham số theo cùng định dạng. Muốn quan sát bind value, cần kiểm tra khả năng logging của driver hoặc dùng proxy/instrumentation hỗ trợ R2DBC.

## 4. Cấu hình logging theo Spring Boot profile

Một cách rõ ràng là đặt logging level theo profile. Cấu hình chung giữ mức log vừa phải; profile dev có thể bật SQL DEBUG; profile production giữ SQL ở mức INFO hoặc cao hơn theo chính sách vận hành.

Ví dụ cấu trúc:

```text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-prod.yml
```

### 4.1. Cấu hình mặc định

application.yml:

```yaml
logging:
  level:
    root: INFO
    org.springframework.r2dbc.core: INFO
    org.springframework.data.r2dbc: INFO
```

Mức INFO là baseline. Ứng dụng vẫn ghi log nghiệp vụ, cảnh báo và lỗi theo cấu hình logger của project.

### 4.2. Development profile

application-dev.yml:

```yaml
logging:
  level:
    org.springframework.r2dbc.core: DEBUG
    org.springframework.data.r2dbc: DEBUG
```

Chạy ứng dụng với profile dev:

```bash
SPRING_PROFILES_ACTIVE=dev ./mvnw spring-boot:run
```

Trên PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
.\mvnw spring-boot:run
```

Trong local development, SQL DEBUG giúp nhìn thấy query mà repository hoặc DatabaseClient đang gửi. Ưu tiên dùng database local với dữ liệu giả lập thay vì sao chép dữ liệu production về máy cá nhân.

### 4.3. Test profile

application-test.yml:

```yaml
logging:
  level:
    root: WARN
    org.springframework.r2dbc.core: DEBUG
    org.springframework.data.r2dbc: INFO
```

Trong test, có thể bật SQL DEBUG khi cần tìm lỗi integration. Nếu suite chạy nhiều test hoặc test song song, log SQL có thể rất nhiều; nên giới hạn logger và giữ output đủ để tìm test gây lỗi.

### 4.4. Production profile

application-prod.yml:

```yaml
logging:
  level:
    root: INFO
    org.springframework.r2dbc.core: INFO
    org.springframework.data.r2dbc: INFO
```

Production thường không bật parameter logging. Khi cần chẩn đoán, ưu tiên trace ID, tên thao tác, thời gian, số hàng bị tác động, SQL state và mã lỗi. Chỉ bật SQL DEBUG hoặc instrumentation chi tiết theo quy trình có kiểm soát, trong thời gian giới hạn.

### 4.5. Ghi đè bằng biến môi trường

Spring Boot hỗ trợ ghi đè cấu hình logging bằng biến môi trường:

```text
LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_R2DBC_CORE=DEBUG
```

Cách này hữu ích khi cần bật SQL log tạm thời cho một instance mà không sửa file cấu hình. Sau khi điều tra xong, cần khôi phục mức log ban đầu.

## 5. Cấu hình logger theo driver

Mỗi R2DBC driver có thể dùng logger riêng cho protocol, query, connection hoặc lỗi. Tên package và mức log phụ thuộc driver cùng phiên bản.

Không có một tên logger driver chung bảo đảm hoạt động cho PostgreSQL, MySQL, SQL Server và H2. Trước khi bật:

1. Xác định driver đang chạy thực tế từ dependency và ConnectionFactory.
2. Đọc tài liệu logging của đúng phiên bản driver.
3. Xác định logger ghi SQL, protocol hay dữ liệu bind.
4. Bật ở môi trường local hoặc test trước.
5. Kiểm tra một truy vấn có giá trị giả lập và xem log thực tế.
6. Đánh giá lượng log, dữ liệu nhạy cảm và chi phí hiệu năng.

Tránh bật toàn bộ package io.r2dbc hoặc log protocol ở TRACE mà chưa biết nội dung được ghi. Có thể có nhiều log connection lifecycle, frame giao thức hoặc dữ liệu không cần thiết.

## 6. Ghi log câu SQL với DatabaseClient

Khi sử dụng DatabaseClient, SQL có thể được đặt trong một biến hoặc hằng số có tên:

```java
private static final String FIND_CUSTOMER_SQL = """
        SELECT id, display_name, status
        FROM customer
        WHERE id = :id
        """;

public Mono<CustomerSummary> findSummary(UUID id) {
    return databaseClient.sql(FIND_CUSTOMER_SQL)
            .bind("id", id)
            .map((row, metadata) -> new CustomerSummary(
                    row.get("id", UUID.class),
                    row.get("display_name", String.class),
                    row.get("status", String.class)))
            .one();
}
```

Nếu muốn ghi nhận một sự kiện ở tầng ứng dụng, log tên thao tác thay vì in toàn bộ object:

```java
log.debug("Starting database operation: operation={}", "customer.findSummary");
```

Logger Spring có thể ghi SQL statement. Log ứng dụng bổ sung ngữ cảnh nghiệp vụ như operation name hoặc request ID. Tránh ghi lại cùng một câu SQL ở nhiều tầng nếu không có lợi ích chẩn đoán rõ ràng.

## 7. Parameter logging bằng R2DBC proxy

R2DBC SPI không có một cơ chế parameter logging portable cho mọi driver. Một lựa chọn là dùng thư viện proxy chuyên cho R2DBC, ví dụ r2dbc-proxy.

Proxy bọc ConnectionFactory thật và quan sát các thao tác như:

- Tạo statement.
- Bind parameter.
- Thực thi query.
- Thời gian thực thi.
- Kết quả hoặc lỗi.

Tùy phiên bản thư viện, API listener và formatter có thể khác nhau. Mô hình tích hợp tổng quát:

```java
ConnectionFactory observedFactory =
        ProxyConnectionFactory.builder(realConnectionFactory)
                .onAfterQuery(queryExecutionInfo -> {
                    // Chỉ ghi metadata đã được cho phép.
                    // Không in toàn bộ bind value nếu chưa masking.
                })
                .build();
```

Đoạn code minh họa điểm tích hợp; cần kiểm tra đúng API của phiên bản r2dbc-proxy được chọn. Đăng ký proxy factory này làm ConnectionFactory mà Spring Data R2DBC sử dụng.

### 7.1. Proxy quan sát được gì?

Một query execution event thường có thể cung cấp thông tin về:

- SQL/query string.
- Các batch hoặc nhóm bind.
- Metadata của parameter và giá trị bind theo khả năng proxy/driver.
- Thời điểm bắt đầu, kết thúc và duration.
- Số hàng bị tác động hoặc kết quả thực thi.
- Exception nếu query thất bại.

Khả năng cụ thể phụ thuộc proxy version và driver. Không nên giả định proxy có thể đọc mọi kiểu parameter hoặc mọi dữ liệu batch giống nhau.

### 7.2. Đặt masking trong listener

Không log trực tiếp toàn bộ QueryExecutionInfo nếu formatter mặc định có thể in giá trị parameter. Hãy chuyển event thành một bản ghi an toàn:

```json
{
  "operation": "customer.findByEmail",
  "sql": "SELECT ... WHERE email_address = ?",
  "parameters": [
    {"index": 0, "type": "String", "value": "[REDACTED]"}
  ],
  "durationMs": 12,
  "rowsUpdated": 0
}
```

Đây là cấu trúc minh họa. Trong code thật, hãy đọc metadata mà proxy version cung cấp và chỉ giữ các field cần thiết.

### 7.3. Bọc đúng ConnectionFactory

Nếu ứng dụng có nhiều ConnectionFactory, hãy quyết định proxy nằm ở đâu:

- Bọc từng target factory nếu cần quan sát từng database riêng.
- Bọc routing factory nếu cần nhìn thao tác từ phía ứng dụng sau khi route đã được chọn, tùy cách proxy tương tác với routing implementation.
- Đặt tên nguồn log để phân biệt database hoặc pool mà không ghi connection URL/password.

Nếu proxy được bọc bên ngoài một routing factory, hãy xác nhận listener có thể nhận metadata route mong muốn. Nếu cần biết tenant, truyền một tenant identifier đã được kiểm soát vào logging context; không suy ra tenant bằng cách ghi toàn bộ connection string.

## 8. Không nhầm r2dbc-proxy với P6Spy

P6Spy thường được dùng để quan sát JDBC statement. Nó không tự động trở thành proxy cho R2DBC ConnectionFactory.

Ứng dụng dùng Spring Data R2DBC cần instrumentation tương thích R2DBC, chẳng hạn r2dbc-proxy, hoặc logger/instrumentation do driver cung cấp. Không thêm P6Spy vào ứng dụng rồi kỳ vọng nó ghi mọi query reactive.

Tương tự, log SQL của Hibernate/JPA không phản ánh câu lệnh do Spring Data R2DBC thực thi nếu ứng dụng đang dùng hai stack persistence khác nhau.

## 9. Che dữ liệu nhạy cảm trong parameter log

Parameter có thể chứa:

- Email, số điện thoại và địa chỉ.
- Tên, ngày sinh hoặc thông tin cá nhân.
- Access token, refresh token hoặc API key.
- Mật khẩu hoặc giá trị xác thực.
- Số tài khoản, dữ liệu thanh toán và thông tin tài chính.
- Nội dung message hoặc dữ liệu nghiệp vụ bí mật.

Ngay cả ID nội bộ cũng có thể là dữ liệu nhạy cảm nếu có thể liên kết tới một cá nhân hoặc tài khoản.

Trước khi ghi bind value, phân loại parameter:

| Nhóm | Ví dụ | Cách log gợi ý |
| --- | --- | --- |
| Không nhạy cảm | Limit nhỏ, trạng thái kỹ thuật | Có thể log theo chính sách |
| Định danh nội bộ | UUID customer/order | Ưu tiên correlation ID hoặc dạng rút gọn được phê duyệt |
| Dữ liệu cá nhân | Email, phone, địa chỉ | Mask hoặc không ghi |
| Bí mật xác thực | Password, token, API key | Không ghi giá trị |
| Tài chính | Số tài khoản, thông tin thanh toán | Không ghi giá trị đầy đủ |
| Nội dung tự do | Message, JSON payload, ghi chú | Không ghi toàn bộ; chọn metadata an toàn |

### 9.1. Masking theo allowlist

Một chiến lược an toàn là chỉ ghi các parameter đã được xác định không nhạy cảm. Những parameter không nằm trong allowlist mặc định bị che:

```java
String safeValue(String parameterName, Object value) {
    if (Set.of("status", "pageSize").contains(parameterName)) {
        return String.valueOf(value);
    }
    return "[REDACTED]";
}
```

Ví dụ này chỉ minh họa chính sách. Tên parameter có thể không được proxy cung cấp ổn định ở native positional binding; khi đó hãy dùng operation metadata hoặc schema mapping để xác định loại dữ liệu. Nếu không thể xác định an toàn, không ghi giá trị.

### 9.2. Không log object hoặc DTO toàn bộ

Tránh:

```java
log.debug("Saving customer: {}", customer);
```

toString() có thể in email, số điện thoại, địa chỉ hoặc field bí mật. Thay vào đó, log operation và một số metadata đã được phê duyệt:

```java
log.debug("Saving customer: operation={}, customerType={}",
        "customer.save",
        customer.getClass().getSimpleName());
```

Nếu cần định danh để điều tra, dùng mã correlation hoặc ID đã được đánh giá là an toàn theo chính sách dữ liệu của ứng dụng.

### 9.3. SQL literal cũng có thể làm lộ dữ liệu

Bind parameter không phải nguồn duy nhất chứa dữ liệu nhạy cảm. Native SQL được nối chuỗi có thể ghi thẳng giá trị vào query string:

```java
String sql = "SELECT * FROM customer WHERE email_address = '" + email + "'";
```

Khi log SQL, email đã nằm trong statement. Vì vậy, luôn dùng bind parameter cho dữ liệu đầu vào và không dựa vào masking bind value để bù cho việc nối chuỗi SQL.

## 10. Chọn mức chi tiết theo môi trường

Một chính sách mẫu:

| Môi trường | SQL statement | Bind values | Duration/error |
| --- | --- | --- | --- |
| Local dev | DEBUG khi cần | Chỉ dữ liệu giả lập hoặc đã mask | Có |
| Automated test | DEBUG có chọn lọc | Không ghi giá trị nhạy cảm | Có |
| Staging | INFO mặc định; DEBUG tạm thời khi điều tra | Mask/allowlist, thường tắt | Có |
| Production | INFO/WARN/ERROR theo logger | Tắt hoặc chỉ metadata đã mask theo phê duyệt | Có, ưu tiên structured log/metrics |

Đây là baseline, không phải mức log bắt buộc cho mọi ứng dụng. Quyết định cuối cùng phụ thuộc yêu cầu vận hành, chính sách bảo vệ dữ liệu và khả năng của log platform.

## 11. Correlation ID và trace ID

Một request thường tạo nhiều query và nhiều log ở controller, service, repository, connection pool và driver. Nếu không có correlation, việc ghép các log đó rất khó.

Nên đưa một định danh xuyên suốt vào structured log:

- Trace ID từ distributed tracing.
- Span ID cho operation hiện tại.
- Correlation ID do ứng dụng hoặc gateway tạo.
- Operation name như order.create hoặc customer.find.
- Tenant identifier đã được phép log, nếu chính sách cho phép.

Ví dụ:

```text
timestamp=2026-11-15T10:00:00Z
level=DEBUG
traceId=8f...
spanId=31...
operation=customer.find
db.system=postgresql
durationMs=18
rowsReturned=1
```

Không cần đưa email hoặc toàn bộ SQL parameter vào log để tìm một request nếu trace ID đã đủ liên kết các sự kiện.

## 12. Reactor Context và MDC

Trong ứng dụng reactive, không nên giả định một request luôn chạy trên cùng thread. MDC của nhiều logging framework dựa trên ThreadLocal, nên việc đặt MDC trực tiếp trong một callback rồi kỳ vọng giá trị luôn theo publisher có thể gây mất correlation hoặc rò giá trị giữa các request.

Reactor Context phù hợp để mang metadata theo subscription. Với Spring Boot và Micrometer Tracing/Context Propagation, hãy dùng cơ chế tích hợp được hỗ trợ để đưa trace context vào log MDC.

Nguyên tắc:

- Giữ trace/correlation metadata trong context reactive.
- Không dùng một ThreadLocal tenant mutable để định tuyến hoặc nhận diện request.
- Nếu cần MDC, bật và cấu hình context propagation đúng theo stack Spring/Reactor đang dùng.
- Không tự MDC.put() mà quên xóa trong luồng có thread reuse.
- Kiểm thử log correlation khi pipeline chuyển scheduler và khi hai request chạy đồng thời.

Route key và trace ID có thể cùng tồn tại trong Reactor Context nhưng phục vụ hai mục đích khác nhau: route key chọn database; trace ID nối các log. Không đưa secret vào cả hai.

## 13. Ghi thời gian thực thi query

SQL statement giúp biết query nào chạy; duration giúp biết query nào chậm. Có thể lấy thời gian ở proxy listener hoặc instrumentation metrics.

Một cách đo ở tầng ứng dụng bằng Reactor:

```java
public Mono<Customer> findCustomer(UUID id) {
    return Mono.defer(() -> {
        long startedAt = System.nanoTime();

        return customerRepository.findById(id)
                .doFinally(signal -> {
                    long elapsedNanos = System.nanoTime() - startedAt;
                    long durationMs = elapsedNanos / 1_000_000;

                    log.debug(
                            "Database operation completed: operation={}, durationMs={}, signal={}",
                            "customer.findById",
                            durationMs,
                            signal);
                });
    });
}
```

Mono.defer tạo mốc thời gian cho mỗi subscription. doFinally được gọi khi publisher hoàn tất, lỗi hoặc bị cancel. Đây là thời gian quan sát ở tầng publisher, có thể gồm thời gian chờ connection và các bước khác; không nhất thiết bằng thời gian database thực thi statement.

Nếu cần duration riêng cho query, dùng query execution listener/proxy hoặc instrumentation ở driver. Không gắn nhãn metric bằng raw SQL có giá trị động vì sẽ tạo cardinality rất cao.

### 13.1. Slow query threshold

Có thể ghi cảnh báo khi một operation vượt ngưỡng:

```java
if (durationMs >= slowQueryThresholdMs) {
    log.warn(
            "Slow database operation: operation={}, durationMs={}",
            "customer.findById",
            durationMs);
}
```

Ngưỡng phải dựa trên SLA, loại truy vấn và số liệu thực tế. Không áp dụng một ngưỡng giống nhau cho mọi query; một truy vấn báo cáo có thể có profile khác truy vấn lấy một bản ghi.

### 13.2. Metrics thay vì log mọi query

Đối với quan sát dài hạn, metrics thường phù hợp hơn việc ghi một log cho mọi lần query:

- Số query theo operation.
- Histogram duration.
- Số lỗi theo loại lỗi.
- Số lần timeout.
- Connection acquire latency.
- Pool pending acquire và số connection đang sử dụng.

Dùng Micrometer/Observation hoặc instrumentation phù hợp với Spring Boot và driver. Tag metric nên có cardinality thấp như operation, database system và outcome; tránh tag bằng ID, SQL đầy đủ hoặc parameter value.

## 14. Ghi log lỗi database

Khi query thất bại, cần ghi đủ thông tin để phân loại lỗi:

- Operation name.
- Trace/correlation ID.
- SQL state hoặc vendor error code nếu có.
- Exception type.
- Duration.
- Database system/target alias đã được phép ghi.
- Retry count nếu có.

Ví dụ:

```java
return customerRepository.findById(id)
        .doOnError(error -> log.error(
                "Database operation failed: operation={}, customerId={}, errorType={}",
                "customer.findById",
                safeIdentifier(id),
                error.getClass().getSimpleName(),
                error));
```

Chỉ ghi safeIdentifier sau khi đã xác định ID đó có được phép log. Không in toàn bộ request hoặc entity. Exception từ driver có thể chứa SQL hoặc chi tiết server; hãy đánh giá log output trong môi trường test trước khi gửi vào log platform tập trung.

Không ghi cùng một exception ở mọi tầng rồi tạo nhiều stack trace giống nhau. Chọn tầng chịu trách nhiệm xử lý lỗi để log một lần với đủ ngữ cảnh.

## 15. Tránh log SQL quá nhiều

Một endpoint có thể chạy nhiều truy vấn. Khi bật SQL DEBUG trên tất cả instance, log volume có thể tăng nhanh và gây:

- Chi phí CPU để format log.
- Tăng dung lượng lưu trữ và chi phí truyền log.
- Khó tìm lỗi quan trọng trong lượng log lớn.
- Rò rỉ dữ liệu do nhiều query không được phân loại.
- Ảnh hưởng latency nếu appender đồng bộ hoặc log sink chậm.

Các cách kiểm soát:

- Bật logger theo profile hoặc theo instance.
- Chỉ bật cho package/operation cần điều tra.
- Giới hạn thời gian bật debug.
- Dùng sampling cho truy vấn thành công có lưu lượng lớn.
- Luôn ghi error, timeout và slow query theo chính sách.
- Đặt retention ngắn hơn cho log chẩn đoán chi tiết.
- Không log bind values trong production theo mặc định.

## 16. Bật log level động qua Actuator

Spring Boot Actuator có endpoint quản lý loggers trong các cấu hình phù hợp. Nó có thể cho phép xem hoặc thay đổi mức log mà không cần khởi động lại ứng dụng.

Endpoint này có quyền thay đổi hành vi logging, vì vậy:

- Chỉ expose trong mạng quản trị đáng tin cậy.
- Bảo vệ bằng authentication/authorization.
- Không public endpoint logger ra Internet.
- Audit ai đã đổi log level và thời điểm đổi.
- Khôi phục mức log sau khi điều tra.
- Không dùng endpoint động để bật parameter logging không được phép.

Nếu tổ chức không cần thay đổi log level runtime, không cần expose endpoint này. Có thể thay đổi qua deployment configuration hoặc biến môi trường.

## 17. Logback theo môi trường

Ngoài application YAML, ứng dụng có thể dùng logback-spring.xml để cấu hình appender, format và rolling policy. Spring Boot hỗ trợ profile section trong file Logback Spring.

Ví dụ rút gọn:

```xml
<configuration>
    <springProfile name="dev">
        <logger name="org.springframework.r2dbc.core" level="DEBUG"/>
        <logger name="org.springframework.data.r2dbc" level="DEBUG"/>
    </springProfile>

    <springProfile name="prod">
        <logger name="org.springframework.r2dbc.core" level="INFO"/>
        <logger name="org.springframework.data.r2dbc" level="INFO"/>
    </springProfile>
</configuration>
```

Đây chỉ là phần cấu hình logger; appender, encoder, rolling và retention cần được định nghĩa theo chuẩn logging của project. Không cấu hình hai nơi mâu thuẫn mà không hiểu thứ tự ưu tiên giữa YAML và Logback.

Nếu dùng logback-spring.xml, giữ tên file đúng để Spring Boot xử lý extension như springProfile.

## 18. Log SQL trong nhiều database hoặc tenant

Ứng dụng có thể có nhiều ConnectionFactory, tenant database hoặc read replica. Log cần phân biệt đích một cách an toàn:

```text
operation=order.find
db.system=postgresql
db.target=tenant-cluster-a
db.role=primary
durationMs=24
```

db.target nên là alias cấu hình, không phải connection URL. Không ghi username/password, host nội bộ nhạy cảm hoặc query parameter chứa secret.

Với tenant routing, chỉ ghi tenant ID nếu chính sách dữ liệu cho phép. Có thể ghi route group hoặc alias đã được làm mờ để điều tra pool và database mà không để lộ định danh khách hàng.

Một query có thể chạy trên database khác do routing context. Đảm bảo route metadata được gắn với đúng subscription và không dùng ThreadLocal để suy ra tenant.

## 19. Kiểm thử logging configuration

Logging là một phần của khả năng vận hành, nên kiểm tra cấu hình profile trong automated test hoặc smoke test:

- Profile dev bật logger SQL đúng package.
- Profile prod không bật SQL DEBUG hoặc parameter logging ngoài ý muốn.
- Parameter nhạy cảm được mask hoặc bỏ qua.
- Log record có trace/correlation ID khi có request context.
- Hai request reactive chạy đồng thời không dùng nhầm context.
- Lỗi database ghi SQL state/error type nhưng không lộ credential.
- Slow query event có operation name và duration.
- Logger driver chỉ bật đúng package cần thiết.

Không nên kiểm thử bằng cách so sánh toàn bộ log string nếu format có thể thay đổi giữa phiên bản framework. Có thể dùng appender test hoặc log event capture để kiểm tra level, message template và field nhạy cảm.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Không thấy SQL trong log | Logger R2DBC core chưa ở DEBUG hoặc appender lọc mất DEBUG | Kiểm tra org.springframework.r2dbc.core và appender |
| Có SQL nhưng không thấy giá trị bind | Spring SQL logger ghi statement, không ghi toàn bộ bind values | Dùng proxy/driver instrumentation nếu thực sự cần |
| Không thấy log từ driver | Đặt sai logger package hoặc driver không phát log ở level đó | Kiểm tra tài liệu đúng driver/version |
| Log quá nhiều | Bật DEBUG/TRACE cho package rộng hoặc toàn bộ instance | Giới hạn package, profile, thời gian và sampling |
| Email/token xuất hiện trong log | Ghi parameter hoặc object không mask | Tắt parameter logging, thêm allowlist/masking và kiểm tra retention |
| Trace ID bị mất giữa các thread | MDC/ThreadLocal không được propagate theo reactive context | Dùng Reactor Context và Micrometer context propagation |
| Log query nhưng không biết request nào gọi | Thiếu trace/correlation ID và operation name | Bổ sung structured context |
| Duration log cao hơn thời gian DB | Đang đo toàn bộ publisher, gồm pool acquire và xử lý khác | Dùng query-level instrumentation nếu cần duration statement |
| P6Spy không thấy R2DBC query | P6Spy tập trung vào JDBC | Dùng R2DBC-compatible proxy/instrumentation |
| Production bật DEBUG ngoài ý muốn | Profile/biến môi trường ghi đè cấu hình | Kiểm tra active profiles và effective configuration |
| SQL log lộ literal | Dữ liệu bị nối trực tiếp vào SQL | Dùng bind parameter và review native query |

## 21. Quy trình điều tra một query lỗi hoặc chậm

Khi cần chẩn đoán một vấn đề R2DBC:

1. Xác định môi trường và active Spring profile.
2. Lấy trace ID/correlation ID của request hoặc job.
3. Xác định operation name và repository/DatabaseClient method liên quan.
4. Bật SQL DEBUG ở package hẹp trong thời gian cần thiết.
5. Kiểm tra query shape, bind marker và dialect.
6. Nếu cần parameter, dùng proxy/driver instrumentation có masking; không bật in mọi bind value.
7. Ghi duration, outcome, số hàng và SQL state nếu có.
8. Kiểm tra connection pool acquire latency để phân biệt chờ pool với query chậm.
9. Dùng database execution plan hoặc slow query log của database để phân tích phía server.
10. Tắt mức log chẩn đoán sau khi hoàn tất và xác nhận cấu hình production đã trở về baseline.

Log ứng dụng cho biết điều gì đã xảy ra từ góc nhìn service/driver. Slow query log và execution plan của database giúp xác định thời gian server thực sự dùng để lập kế hoạch và thực thi. Hai nguồn bổ sung cho nhau.

## 22. Chính sách logging gợi ý

Một chính sách dễ áp dụng:

| Dữ liệu | Dev local | Test | Production |
| --- | --- | --- | --- |
| SQL statement có marker | DEBUG khi cần | DEBUG có chọn lọc | INFO mặc định; DEBUG tạm thời có kiểm soát |
| Bind value thông thường | Chỉ với fixture giả lập | Hạn chế | Tắt mặc định |
| Bind value nhạy cảm | Không ghi | Không ghi | Không ghi |
| Parameter type/index | Có thể ghi | Có thể ghi | Có thể ghi nếu hữu ích |
| Query duration | DEBUG hoặc metrics | Có thể ghi | Metrics và slow query event |
| SQL state/error type | Có | Có | Có |
| Password/credential | Không ghi | Không ghi | Không ghi |
| Trace/correlation ID | Có | Có | Có |

Điều quan trọng là phân biệt log chẩn đoán và telemetry vận hành. SQL DEBUG có thể hữu ích trong thời gian ngắn; metrics và trace có cấu trúc thường phù hợp hơn để quan sát liên tục.

## 23. Checklist cấu hình theo môi trường

Khi triển khai logging cho Spring Data R2DBC, hãy xác định:

1. Logger Spring R2DBC core có bật đúng level ở profile cần thiết không?
2. Có cần logger Spring Data R2DBC để theo dõi repository/mapping không?
3. Driver có logger riêng và tài liệu cụ thể cho phiên bản đang dùng không?
4. Có thật sự cần parameter logging hay SQL statement đã đủ?
5. Nếu cần parameter logging, proxy có hỗ trợ driver và kiểu bind đang dùng không?
6. Có masking/allowlist trước khi ghi giá trị không?
7. Có loại bỏ password, token, PII và payload nhạy cảm không?
8. Log có trace/correlation ID và operation name không?
9. Duration được đo ở tầng publisher hay query execution?
10. Metrics có tránh raw SQL và ID làm tag cardinality cao không?
11. Production có giữ SQL DEBUG và TRACE ở trạng thái tắt theo baseline không?
12. Có cơ chế tắt mức log chẩn đoán sau khi xử lý sự cố không?

Ghi log SQL và tham số giúp quan sát hành vi persistence, nhưng hai loại log có mức rủi ro khác nhau. Spring DatabaseClient có thể ghi SQL statement ở DEBUG; bind value cần khả năng riêng của driver hoặc proxy như r2dbc-proxy. Hãy cấu hình logger theo profile, ưu tiên trace ID, operation, duration và lỗi có cấu trúc, đồng thời mask dữ liệu nhạy cảm. Trong production, giữ parameter logging tắt theo mặc định và chỉ bật instrumentation chi tiết khi có lý do, phạm vi và thời hạn rõ ràng.
