# Cấu hình logger cho SDN, driver và truy vấn Cypher

Khi vận hành ứng dụng Spring Data Neo4j (SDN), log cần giúp trả lời ba câu hỏi: ứng dụng đã gửi câu Cypher nào, Neo4j Java Driver gặp vấn đề gì khi kết nối hoặc trao đổi Bolt, và server đã thực thi truy vấn ra sao. Ba loại thông tin này đến từ các lớp khác nhau nên không thể bật một logger duy nhất rồi kỳ vọng nhìn thấy toàn bộ luồng.

Spring Boot quản lý logging của ứng dụng; SDN có logger riêng cho câu lệnh và Cypher notification; Neo4j Java Driver dùng `System.Logger`; còn query log của Neo4j được cấu hình ở phía database server. Cần bật đúng phạm vi khi chẩn đoán, giữ mức log thấp trong môi trường production và tránh ghi parameter chứa dữ liệu nhạy cảm.

## 1. Phân biệt các lớp logging

| Lớp | Nguồn log | Dùng để tìm hiểu |
|---|---|---|
| Spring Boot / ứng dụng | Logger của service, repository, controller và framework | Luồng nghiệp vụ, request, correlation ID, exception và thời gian xử lý |
| Spring Data Neo4j | `org.springframework.data.neo4j` và `org.springframework.data.neo4j.cypher` | Hoạt động mapping, statement do SDN gọi và Cypher notification từ server |
| Neo4j Java Driver | `org.neo4j.driver`, `org.neo4j.bolt.connection` | Tạo driver, pool, kết nối, routing, handshake và trao đổi Bolt |
| Neo4j server | `neo4j.log`, `debug.log`, `query.log`, `security.log` và `gc.log` | Truy vấn thực thi, thời gian chạy, sự kiện bảo mật, lỗi server và GC |

Log của SDN cho biết ứng dụng gửi statement nào và server trả notification gì. Log của Driver hữu ích khi truy vấn không đến được server, connection pool cạn, routing table lỗi hoặc Bolt connection bị ngắt. Query log ở server giúp phân tích thời gian planning, waiting, page hit và thông tin thực thi. Hãy dùng đúng lớp để tránh tăng log toàn hệ thống mà vẫn không nhìn thấy nguyên nhân.

## 2. Cấu hình mức log Spring Boot

Spring Boot dùng Logback mặc định khi ứng dụng sử dụng các starter phổ biến. Có thể đặt logger level trong `application.yml` mà không cần viết cấu hình Logback riêng:

```yaml
logging:
  level:
    root: INFO
    org.springframework.data.neo4j: INFO
    org.springframework.data.neo4j.cypher: DEBUG
```

`root: INFO` giữ log chung ở mức vừa phải. `org.springframework.data.neo4j: INFO` cho phép quan sát thông tin SDN thông thường; logger Cypher được nâng riêng lên `DEBUG` để theo dõi statement và notification.

Nếu muốn cấu hình trong `application.properties`:

```properties
logging.level.root=INFO
logging.level.org.springframework.data.neo4j=INFO
logging.level.org.springframework.data.neo4j.cypher=DEBUG
```

Spring Boot hỗ trợ các mức `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` và `OFF`. Có thể dùng biến môi trường cho package logger:

```text
LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_DATA_NEO4J_CYPHER=DEBUG
```

Biến môi trường phù hợp với cấu hình theo môi trường triển khai. Với logger class cụ thể có chữ hoa trong tên, relaxed binding có thể chuyển tên thành chữ thường; dùng `SPRING_APPLICATION_JSON` hoặc file logging config nếu cần chỉ định logger class chính xác.

## 3. Bật logger Cypher của Spring Data Neo4j

Từ Spring Data Neo4j 7.1.5, logger `org.springframework.data.neo4j.cypher` bao gồm các statement do SDN gọi và notification nhận từ server. Các notification có những category riêng:

| Logger category | Ý nghĩa |
|---|---|
| `org.springframework.data.neo4j.cypher.performance` | Notification liên quan đến hiệu năng |
| `org.springframework.data.neo4j.cypher.hint` | Hint hoặc gợi ý cho query planner |
| `org.springframework.data.neo4j.cypher.unrecognized` | Notification chưa được nhận diện |
| `org.springframework.data.neo4j.cypher.unsupported` | Tính năng hoặc hành vi chưa được hỗ trợ |
| `org.springframework.data.neo4j.cypher.deprecation` | Cảnh báo API hoặc cú pháp đã deprecated |
| `org.springframework.data.neo4j.cypher.generic` | Notification chung |
| `org.springframework.data.neo4j.cypher.security` | Notification liên quan bảo mật |
| `org.springframework.data.neo4j.cypher.topology` | Notification liên quan topology |

Có thể điều chỉnh từng category riêng mà không phải nâng toàn bộ logger Cypher:

```yaml
logging:
  level:
    org.springframework.data.neo4j.cypher: DEBUG
    org.springframework.data.neo4j.cypher.deprecation: INFO
    org.springframework.data.neo4j.cypher.performance: WARN
```

Khi nâng logger parent lên `DEBUG`, các statement do SDN gọi sẽ dễ quan sát hơn. Nếu cần thêm chi tiết, chỉ bật `TRACE` trong thời gian ngắn ở môi trường phát triển hoặc staging đã kiểm soát dữ liệu. Tùy phiên bản và đường đi thực thi, mức chi tiết cao có thể làm lộ parameter hoặc thông tin graph; hãy kiểm tra nội dung log thực tế trước khi chia sẻ.

Logger SDN không thay thế log của những lệnh được gọi trực tiếp qua một Driver độc lập bên ngoài SDN. Với các lệnh đó, dùng Driver logger hoặc query log phía server.

## 4. Cấu hình Neo4j Java Driver

Neo4j Java Driver 6 sử dụng Java `System.Logger` mặc định. Tài liệu Driver hướng dẫn điều chỉnh hai logger chính qua file `$JAVA_HOME/conf/logging.properties`:

```properties
# Driver lifecycle, pool and routing
org.neo4j.driver.level = FINE

# Bolt connection and protocol diagnostics
org.neo4j.bolt.connection.level = FINE

# ConsoleHandler must also accept FINE records
java.util.logging.ConsoleHandler.level = FINE
```

Đây là cấu hình Java Util Logging (JUL) cho JDK đang chạy ứng dụng. Hãy sửa file logging.properties đang được JVM sử dụng, giữ lại các handler hiện có và chỉ thêm hoặc điều chỉnh các dòng cần thiết. Nếu muốn trỏ đến một file khác, truyền system property khi khởi động JVM:

```bash
java -Djava.util.logging.config.file=/etc/myapp/driver-logging.properties -jar app.jar
```

Mức `FINE` giúp chẩn đoán các sự kiện như driver được tạo, connection pool, routing và trao đổi Bolt. Nếu Spring Boot hoặc ứng dụng đã cấu hình bridge cho `System.Logger`/JUL sang logging backend khác, cần xác nhận đường đi của log để tránh không thấy log hoặc ghi trùng hai lần.

Không nên dùng API `Config.builder().withLogging(Logging.slf4j())` trong ví dụ cũ để cấu hình Driver 6: abstraction `org.neo4j.driver.Logging` đã deprecated và Driver dùng `System.Logger` mặc định. Hãy ưu tiên cấu hình logger theo tài liệu của đúng phiên bản Driver đang chạy.

### Phân biệt FINE, FINER và TRACE

Driver dùng mức log của `System.Logger`/JUL, không dùng tên mức giống hệt SLF4J:

| JUL level | Mức tương đương thường dùng | Mục đích |
|---|---|---|
| `INFO` | INFO | Driver lifecycle và thông tin tổng quát |
| `WARNING` | WARN | Cảnh báo kết nối hoặc hoạt động |
| `FINE` | DEBUG | Pool, routing và thông điệp Bolt ở mức debug |
| `FINER` | Chi tiết hơn DEBUG | Thông tin nhạy cảm có thể xuất hiện |
| `FINEST` | TRACE | Dữ liệu giao thức rất chi tiết, lượng log lớn |

Neo4j cảnh báo log `FINER` có thể chứa thông tin nhạy cảm như database credentials. Không bật `FINER` hoặc `FINEST` trên production. Nếu cần chẩn đoán trong môi trường cô lập, giới hạn thời gian, người truy cập và nơi lưu log; sau khi thu thập đủ bằng chứng, đưa level về trạng thái ban đầu.

## 5. Phân biệt log của ứng dụng và query log phía Neo4j server

Log của ứng dụng cho biết câu lệnh được gửi từ client; query log ghi nhận câu lệnh được server thực thi. Query log được cấu hình trong `neo4j.conf` và được ghi vào `query.log`. Đây là thành phần server-side, độc lập với `application.yml` của Spring Boot.

Neo4j có các file log chính:

| File | Nội dung |
|---|---|
| `neo4j.log` | Thông tin tổng quát của database server |
| `debug.log` | Thông tin phục vụ điều tra lỗi server; nên giữ định dạng mặc định |
| `query.log` | Truy vấn được thực thi và số liệu thực thi |
| `security.log` | Sự kiện xác thực và bảo mật |
| `gc.log` | Thông tin garbage collection của JVM |

Query log là tính năng Enterprise Edition. Trên các phiên bản Neo4j hiện hành, `db.logs.query.enabled` có các lựa chọn:

- `OFF`: tắt query log.
- `INFO`: ghi khi truy vấn hoàn tất và vượt ngưỡng `db.logs.query.threshold`.
- `VERBOSE`: ghi thời điểm bắt đầu và kết thúc của mọi truy vấn, không phụ thuộc threshold.

Tài liệu Neo4j hiện hành ghi nhận `VERBOSE` là giá trị mặc định của query logging. Vì vậy, nếu không muốn ghi mọi query, hãy đặt `INFO` hoặc `OFF` một cách tường minh trong cấu hình server thay vì dựa vào mặc định.

Ví dụ cấu hình theo dõi truy vấn chậm trong `neo4j.conf`:

```properties
db.logs.query.enabled=INFO
db.logs.query.threshold=250ms
```

Ngưỡng `250ms` chỉ là ví dụ ban đầu. Hãy chọn ngưỡng dựa trên latency SLO và đặc điểm workload. Với `INFO`, truy vấn chỉ được ghi sau khi hoàn tất và vượt ngưỡng; nếu cần quan sát tất cả query trong môi trường test, có thể tạm dùng `VERBOSE`.

Query log có thể cung cấp thời gian planning, waiting, CPU, allocated bytes, page hits, page faults, database, user, transaction ID và query plan nếu được bật. Những số liệu này giúp phân biệt query chậm do planning, chờ lock hay đọc nhiều page.

## 6. Bảo vệ parameter và literal trong query log

Một query thường truyền dữ liệu qua parameter như `$email`, `$customerId` hoặc `$token`. Parameterization giúp tái sử dụng query plan và tránh ghép giá trị trực tiếp vào chuỗi Cypher, nhưng không tự động bảo đảm giá trị parameter sẽ không xuất hiện trong log.

Ở Neo4j, query logging có cấu hình `db.logs.query.parameter_logging_enabled`. Trên các phiên bản hiện hành, mặc định của setting này là `true`. Vì vậy, khi bật query log, cần chủ động quyết định có cần lưu parameter hay không.

Ví dụ cấu hình ưu tiên bảo vệ dữ liệu:

```properties
db.logs.query.enabled=INFO
db.logs.query.threshold=250ms
db.logs.query.parameter_logging_enabled=false
db.logs.query.obfuscate_literals=true
db.logs.query.plan_description_enabled=false
```

Hai cài đặt bảo vệ cần hiểu riêng:

- `db.logs.query.obfuscate_literals=true` che các literal trong query text. Nó không che parameter values.
- `db.logs.query.parameter_logging_enabled=false` ngăn query log ghi parameter values.

Với Neo4j từ 2026.01 trở lên, có thêm `db.logs.query.obfuscate_errors=true` để che thông tin nhạy cảm có thể xuất hiện trong nội dung lỗi. Kiểm tra phiên bản trước khi thêm setting này vào cấu hình cũ:

```properties
db.logs.query.obfuscate_errors=true
```

Không bật `db.logs.query.early_raw_logging_enabled` trong môi trường chứa dữ liệu thật nếu chưa đánh giá rủi ro: setting này ghi query text và parameters sớm, trước khi obfuscation password được áp dụng. Ngoài ra, nếu query sai cú pháp và không parse được, server không thể obfuscate literal theo cấu trúc query.

### Không ghi parameter map bằng logger ứng dụng

Tránh cách ghi sau:

```java
log.debug("Executing Cypher: {} with params {}", cypher, parameters);
```

`parameters` có thể chứa email, số điện thoại, thông tin thanh toán, access token hoặc dữ liệu cá nhân. Nếu cần log ở tầng ứng dụng, chỉ ghi metadata không nhạy cảm:

```java
log.info(
        "neo4j operation={} database={} correlationId={} durationMs={} records={}",
        "findCustomerSummary",
        databaseAlias,
        correlationId,
        durationMs,
        recordCount);
```

Nếu database alias hoặc correlation ID cũng có thể nhận diện tenant/người dùng, dùng mã nội bộ đã được kiểm soát hoặc rút gọn trước khi ghi. Không log credentials, bearer token, nội dung request body hay toàn bộ node properties.

## 7. Cấu hình query plan logging có kiểm soát

Neo4j có setting `db.logs.query.plan_description_enabled` để thêm query plan vào query log. Plan có thể hữu ích khi cần biết query dùng index seek, label scan hay expand nhiều relationship. Tuy nhiên, việc thu thập và ghi plan có chi phí; không nên bật thường trực cho toàn bộ workload production.

Chỉ bật trong một khoảng điều tra có mục tiêu:

```properties
db.logs.query.enabled=INFO
db.logs.query.threshold=500ms
db.logs.query.plan_description_enabled=true
```

Sau khi thu thập đủ dữ liệu, tắt lại:

```properties
db.logs.query.plan_description_enabled=false
```

Nếu cần phân tích một query cụ thể, chạy `EXPLAIN` để xem kế hoạch mà không thực thi query; dùng `PROFILE` trong môi trường kiểm thử hoặc với query đã hiểu rõ tác động vì `PROFILE` thực sự thực thi query. Query log plan là công cụ quan sát vận hành, không thay thế việc kiểm tra query plan có chủ đích.

## 8. Dùng category để khoanh vùng vấn đề

Khi một query chậm hoặc có notification, không cần bật `TRACE` cho toàn bộ ứng dụng. Có thể chọn category phù hợp:

| Triệu chứng | Nơi bắt đầu điều tra |
|---|---|
| SDN phát sinh query không như mong đợi | `org.springframework.data.neo4j.cypher` ở `DEBUG` |
| Query có cảnh báo hiệu năng | `org.springframework.data.neo4j.cypher.performance` |
| Planner bỏ qua hoặc cảnh báo hint | `org.springframework.data.neo4j.cypher.hint` |
| Cú pháp hoặc tính năng bị cảnh báo không hỗ trợ | `org.springframework.data.neo4j.cypher.unsupported` và `.unrecognized` |
| Dùng cú pháp/API deprecated | `org.springframework.data.neo4j.cypher.deprecation` |
| Lỗi kết nối, routing hoặc pool | Driver `org.neo4j.driver` ở `FINE` |
| Lỗi trao đổi Bolt | `org.neo4j.bolt.connection` ở `FINE` |
| Query chạy lâu trên server | `query.log` với `INFO` và threshold phù hợp |
| Lỗi đăng nhập hoặc phân quyền | `security.log` phía server và exception phía ứng dụng |

Ví dụ, nếu SDN gửi query nhưng request vẫn timeout, trước tiên xác nhận statement ở logger SDN. Nếu log cho thấy statement đã gửi nhưng Driver liên tục acquire connection hoặc reconnect, chuyển sang Driver logger. Nếu query đến server nhưng mất nhiều thời gian, dùng query log và query plan để xem planning, lock wait và page hits.

## 9. Tách cấu hình theo profile

Không nên bật cùng một mức log cho mọi môi trường. Có thể giữ cấu hình mặc định trong `application.yml` và bật logger chi tiết trong `application-local.yml`:

```yaml
# application.yml
logging:
  level:
    root: INFO
    org.springframework.data.neo4j: INFO
```

```yaml
# application-local.yml
logging:
  level:
    org.springframework.data.neo4j.cypher: DEBUG
```

Khi chạy local:

```bash
java -jar app.jar --spring.profiles.active=local
```

Với staging, chỉ bật logger cần cho một đợt kiểm thử hoặc tái hiện lỗi. Production nên giữ log nghiệp vụ có cấu trúc ở `INFO`, exception ở `WARN`/`ERROR`, và chỉ nâng một category cụ thể khi có ticket điều tra.

Spring Boot khởi tạo logging trước khi `ApplicationContext` được tạo. Vì vậy, không dùng `@PropertySource` trong class `@Configuration` để thay đổi logging system hoặc cấu hình logger sớm. Nếu cần custom appender, rolling policy hoặc JSON layout, dùng `logback-spring.xml`/`log4j2-spring.xml` hoặc chỉ định `logging.config`.

## 10. Gắn correlation ID và metadata vào log ứng dụng

Khi request đi qua controller, service và repository, correlation ID giúp ghép các log thuộc cùng một request. Dùng tracing/MDC đã được ứng dụng cấu hình để gắn ID vào log pattern hoặc structured log. Không tạo một ID mới ở từng tầng vì sẽ mất khả năng đối chiếu.

Một dòng log nghiệp vụ có thể chứa:

- `correlationId` hoặc `traceId`.
- Tên operation, ví dụ `loadCustomerGraph`.
- Database alias đã được kiểm soát.
- Thời gian xử lý và số record trả về.
- Kết quả thành công/thất bại và error code.

Không đưa raw query parameters vào MDC hoặc structured key-values. MDC được sao chép vào log output và có thể được chuyển đến hệ thống tập trung; chỉ đưa các giá trị được phép lưu trữ.

Nếu dùng Spring Boot structured logging, có thể chọn định dạng JSON cho console hoặc file:

```yaml
logging:
  structured:
    format:
      console: ecs
      file: ecs
  file:
    name: logs/spring-data-neo4j.json
```

Structured logging giúp hệ thống log tìm kiếm theo `traceId`, logger, level hoặc operation. Nếu đã có custom Logback configuration, cần cấu hình encoder/layout tương ứng để sử dụng các property structured format của Spring Boot.

## 11. Kiểm tra logging có hoạt động

Sau khi thay đổi logger level, chạy một use case nhỏ có query đã biết và xác nhận:

1. Log ứng dụng có correlation ID và tên operation.
2. Logger SDN hiển thị statement do SDN gọi nếu phiên bản hỗ trợ logger Cypher.
3. Cypher notification xuất hiện dưới category tương ứng nếu server gửi notification.
4. Driver logger hiển thị driver lifecycle hoặc connection event khi cần.
5. Query log phía server có entry phù hợp với threshold và cấu hình đã chọn.
6. Parameter nhạy cảm không xuất hiện trong log.
7. Sau khi điều tra, tất cả logger được đưa về level vận hành bình thường.

Nếu không thấy log:

- Kiểm tra tên logger và level thực tế.
- Kiểm tra backend đang dùng là Logback, Log4j2 hay JUL.
- Với Driver 6, xác nhận `System.Logger`/JUL đang được route đến nơi thu log.
- Kiểm tra console handler/file appender có ngưỡng thấp hơn hoặc bằng level cần thu.
- Xác nhận server query logging có hỗ trợ edition và setting đã được áp dụng.
- Kiểm tra query có vượt threshold nếu `db.logs.query.enabled=INFO`.

## 12. Quản lý log file, retention và quyền truy cập

Spring Boot mặc định ghi log ra console. Có thể đặt `logging.file.name` để ghi thêm ra file và cấu hình rotation của Logback:

```yaml
logging:
  file:
    name: logs/application.log
  logback:
    rollingpolicy:
      max-file-size: 50MB
      max-history: 14
      total-size-cap: 2GB
```

Server Neo4j dùng Log4j 2 và cấu hình riêng trong thư mục `conf`, thường qua `user-logs.xml` và `server-logs.xml`. Không chỉnh cấu hình Log4j của Neo4j để mong thay đổi logger Logback của ứng dụng Spring Boot.

Vận hành log cần xác định:

- Ai có quyền đọc application log và database log.
- Log được giữ trong bao lâu và khi nào bị xóa.
- Có mã hóa khi truyền và khi lưu hay không.
- Rotation và dung lượng tối đa.
- Quy trình redaction khi log vô tình chứa dữ liệu nhạy cảm.
- Cách cấp quyền truy cập tạm thời cho người điều tra và thu hồi sau đó.

Giữ `debug.log` của Neo4j theo khuyến nghị mặc định và không thay đổi format của file này nếu không có lý do vận hành cụ thể. Nếu cần format khác, tạo appender bổ sung thay vì làm thay đổi format phục vụ công cụ hỗ trợ.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ bật `root=DEBUG` | Log toàn ứng dụng tăng mạnh và khó đọc | Nâng riêng logger SDN hoặc Driver cần điều tra |
| Nhầm SDN logger với Driver logger | Không thấy lỗi pool/routing hoặc statement do SDN gọi | Tách `org.springframework.data.neo4j.cypher` và Driver logger |
| Dùng cấu hình `withLogging(Logging.slf4j())` cũ với Driver 6 | Dựa vào API đã deprecated | Dùng `System.Logger` và cấu hình JUL theo tài liệu Driver |
| Chỉ đặt `org.neo4j.driver.level=FINE` nhưng console handler vẫn INFO | Driver FINE không xuất hiện | Hạ level của `ConsoleHandler` hoặc cấu hình appender phù hợp |
| Bật `FINER`/`FINEST` trên production | Có thể lộ credential và dữ liệu giao thức, log tăng nhanh | Dùng FINE có thời hạn; không bật trace sâu thường trực |
| Bật query log VERBOSE cho workload lớn | Ghi mọi query ở cả đầu và cuối, tạo lượng log lớn | Dùng INFO và threshold phù hợp |
| Để parameter logging bật với dữ liệu thật | Email, token hoặc PII có thể vào query.log | Tắt `db.logs.query.parameter_logging_enabled` |
| Chỉ bật obfuscate literals | Parameter values vẫn có thể xuất hiện | Tắt parameter logging riêng |
| Log toàn bộ parameter map trong service | Rò rỉ dữ liệu nghiệp vụ | Chỉ log operation, duration, count và correlation ID |
| Bật query plan logging liên tục | Tăng chi phí thu thập và ghi log | Chỉ bật trong đợt điều tra ngắn |
| Dùng `@PropertySource` để đổi logging sớm | Logging đã khởi tạo trước ApplicationContext | Dùng application config hoặc native logging config |
| Quên hạ level sau khi debug | Tăng dung lượng log và rủi ro lộ dữ liệu | Có thời hạn điều tra và checklist khôi phục level |

## 14. Bài tập thực hành

Xây dựng cấu hình logging cho một ứng dụng Spring Data Neo4j:

1. Đặt root logger ở `INFO` và `org.springframework.data.neo4j` ở `INFO`.
2. Bật `org.springframework.data.neo4j.cypher` ở `DEBUG` trong profile local.
3. Chạy một repository query và xác nhận statement xuất hiện trong log SDN.
4. Tạo một query có notification hoặc cú pháp deprecated trong môi trường test và xác nhận category phù hợp.
5. Cấu hình Driver `org.neo4j.driver` và `org.neo4j.bolt.connection` ở JUL `FINE`; xác nhận log pool/routing xuất hiện.
6. Tạo file query log phía Neo4j Enterprise với `INFO` và threshold phù hợp.
7. Tắt parameter logging, bật obfuscate literals và xác nhận giá trị email/token không xuất hiện trong log.
8. Bật query plan logging trong thời gian ngắn, kiểm tra plan, sau đó tắt lại.
9. Thêm correlation ID và operation metadata vào application log.
10. Chạy một request, đối chiếu log ứng dụng, SDN, Driver và server theo cùng thời điểm/correlation ID.
11. Khôi phục mọi logger về mức production và xác nhận không còn parameter nhạy cảm trong log mới.

Sau bài tập, hãy giải thích được sự khác nhau giữa logger SDN, logger Driver và query log server; cách chọn level; vì sao `FINE` khác `FINER`; và vì sao obfuscate literal không thay thế việc tắt parameter logging.

## Kết luận

Cấu hình logging hiệu quả cần tách bốn lớp: Spring Boot/application, Spring Data Neo4j, Neo4j Java Driver và Neo4j server. Dùng `org.springframework.data.neo4j.cypher` để theo dõi statement và notification, cấu hình Driver 6 qua `System.Logger`/JUL, và dùng query log server để phân tích truy vấn thực thi. Trong production, ưu tiên mức log có mục tiêu, đặt query threshold, tắt parameter logging và obfuscate dữ liệu nhạy cảm. Chỉ bật log chi tiết hoặc query plan trong thời gian điều tra, giới hạn quyền truy cập và đưa cấu hình về mức bình thường sau khi hoàn tất.

## Tài liệu tham khảo

- [Spring Data Neo4j – Logging](https://docs.spring.io/spring-data/neo4j/reference/appendix/logging.html)
- [Spring Boot – Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Neo4j Java Driver – Advanced connection information and Logging](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Operations Manual – Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Operations Manual – Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/)
- [Neo4j Operations Manual – Update dynamic settings](https://neo4j.com/docs/operations-manual/current/configuration/dynamic-settings/)
