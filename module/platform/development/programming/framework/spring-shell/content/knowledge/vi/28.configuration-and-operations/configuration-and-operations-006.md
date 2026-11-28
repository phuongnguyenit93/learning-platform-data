# Quy ước mức chi tiết thông báo và chế độ debug

Một CLI Spring Shell thường chạy trực tiếp trong terminal, trong script hoặc trong pipeline. Người dùng cần nhìn thấy kết quả command rõ ràng, còn đội vận hành cần đủ thông tin để tìm nguyên nhân khi có lỗi. Nếu mọi thông báo đều ở mức `INFO`, terminal nhanh chóng bị nhiễu; nếu bật `DEBUG` hoặc `TRACE` cho toàn bộ ứng dụng, log có thể quá lớn và vô tình chứa dữ liệu nhạy cảm.

Hãy đặt quy ước mức log ngay từ đầu, cấu hình theo profile và chỉ tăng chi tiết cho package cần điều tra. Spring Boot 3.x cung cấp `logging.level`, logging groups, profile-specific configuration, file rotation và structured logging. Cờ `--debug` của Spring Boot là chế độ chẩn đoán cho một tập logger lõi; nó không đồng nghĩa với việc đặt mọi logger của ứng dụng ở `DEBUG`.

## Phân biệt output của command và log chẩn đoán

Trong ứng dụng Spring Shell, hai loại output phục vụ mục đích khác nhau:

| Loại | Người nhận | Nội dung |
|---|---|---|
| Command output | Người dùng đang chạy command hoặc chương trình gọi CLI | Kết quả nghiệp vụ, bảng dữ liệu, thông báo thành công/thất bại và hướng dẫn tiếp theo |
| Application log | Người vận hành, đội hỗ trợ và hệ thống thu thập log | Mốc thực thi, thời lượng, logger, trạng thái kỹ thuật, exception và correlation ID |

Không dùng `System.out.println()` hoặc `System.err.println()` thay cho logging framework. Trong command, trả kết quả qua return value hoặc output writer của Spring Shell. Trong service và component, dùng SLF4J logger. Điều này cho phép cấu hình level, appender, file rotation, định dạng và đích nhận log độc lập với nội dung command.

Nếu người dùng pipe kết quả command sang file hoặc công cụ khác, log chẩn đoán không nên làm hỏng định dạng dữ liệu. Với CLI có output JSON/CSV, cấu hình appender phù hợp để log đi sang `stderr` hoặc file riêng, rồi kiểm thử cả hai luồng trên môi trường thực tế. Spring Boot mặc định ghi log ra console; cấu hình file bằng `logging.file.name` sẽ bổ sung file output, không tự động có nghĩa là console output đã bị tắt.

## Ý nghĩa của từng log level

Các level được sắp xếp từ ít nghiêm trọng/chi tiết tới nghiêm trọng hơn. Một logger đặt ở `INFO` chỉ phát ra request `INFO`, `WARN` và `ERROR`; các request `DEBUG` và `TRACE` bị bỏ qua.

| Level | Dùng khi | Ví dụ trong CLI |
|---|---|---|
| `TRACE` | Theo dõi rất chi tiết từng bước nội bộ, thường chỉ bật trong thời gian ngắn | Dấu vết parser, vòng lặp xử lý, giao tiếp protocol đã được lọc dữ liệu |
| `DEBUG` | Thông tin chẩn đoán giúp lập trình viên hiểu luồng xử lý | Đã nạp 24 bản ghi, chọn profile `staging`, retry lần 2 |
| `INFO` | Sự kiện vận hành bình thường, có ý nghĩa khi theo dõi | Bắt đầu import, hoàn tất export, kết nối dịch vụ thành công |
| `WARN` | Điều bất thường nhưng ứng dụng vẫn tiếp tục hoặc đã phục hồi | Dùng giá trị mặc định, retry do timeout, bỏ qua một dòng dữ liệu lỗi |
| `ERROR` | Một thao tác hoặc bước nghiệp vụ thất bại và cần chú ý | Không thể kết nối dịch vụ, import thất bại, transaction bị rollback |
| `OFF` | Tắt log của logger được cấu hình | Chỉ dùng có chủ đích cho logger cụ thể, không che mất audit/security event bắt buộc |

Logback và SLF4J dùng thứ tự `TRACE < DEBUG < INFO < WARN < ERROR`. Spring Boot cũng chấp nhận `FATAL` trong cấu hình level; Logback không có level `FATAL` riêng và ánh xạ nó thành `ERROR`.

Một quy ước thực tế cho Spring Shell:

- `INFO`: ghi các mốc bắt đầu/kết thúc operation, version, profile đang dùng và kết quả tổng quát.
- `WARN`: ghi dữ liệu bị bỏ qua, fallback, retry hoặc cấu hình không tối ưu nhưng vẫn xử lý được.
- `ERROR`: ghi operation thất bại cùng exception và operation ID để truy vết.
- `DEBUG`: ghi quyết định kỹ thuật, số lượng, thời lượng và trạng thái trung gian không nhạy cảm.
- `TRACE`: chỉ dùng khi cần khoanh vùng một luồng cụ thể; tắt sau khi điều tra.

Không ghi một dòng `INFO` cho mọi bản ghi trong vòng lặp lớn. Hãy ghi tổng số lượng, thời gian và số lỗi ở cuối operation; chỉ dùng `DEBUG`/`TRACE` khi thật sự cần chi tiết từng phần tử.

## Logger, root level và kế thừa level

SLF4J tạo logger theo tên, thường là tên class. Các tên logger tạo thành cây phân cấp theo package. Logger không có level riêng sẽ kế thừa level từ ancestor gần nhất có cấu hình; cuối cùng là root logger.

Ví dụ:

```text
root = INFO
└── com.example.customercli = DEBUG
    ├── command = DEBUG
    ├── service = DEBUG
    └── repository = INFO
```

Trong cấu hình này, package `com.example.customercli.command` kế thừa `DEBUG`, còn `com.example.customercli.repository` có level riêng là `INFO`. Logger con không khai báo level sẽ lấy level hiệu lực từ cha gần nhất. Đây là lý do nên đặt root level tương đối ổn định và chỉ tăng chi tiết ở package cần điều tra.

Ví dụ dùng SLF4J trong service:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
class CustomerImportService {

    private static final Logger log =
            LoggerFactory.getLogger(CustomerImportService.class);

    void importCustomers(String operationId, int rowCount) {
        log.info("Customer import started operationId={} rows={}",
                operationId, rowCount);

        log.debug("Validating import options operationId={}", operationId);

        try {
            // Thực hiện import.
            log.info("Customer import completed operationId={}", operationId);
        } catch (RuntimeException ex) {
            log.error("Customer import failed operationId={}", operationId, ex);
            throw ex;
        }
    }
}
```

Dùng message template cố định và placeholder `{}` thay vì nối chuỗi. Điều này giúp logging framework trì hoãn việc format khi level đang bị tắt và giảm nguy cơ dữ liệu đầu vào làm thay đổi cấu trúc thông điệp. Placeholder không tự ngăn log injection; dữ liệu không tin cậy vẫn phải được sanitize/encode phù hợp với encoder và định dạng log.

## Đặt level trong application.yaml

Spring Boot cấu hình level qua `logging.level.root` và `logging.level.<logger-name>`. Ví dụ `application.yaml`:

```yaml
logging:
  level:
    root: INFO
    com.example.customercli: INFO
    org.springframework.shell: WARN
    org.springframework.boot: WARN
```

Tên package ở trên là ví dụ; thay bằng package thật của ứng dụng. Giữ `root` ở `INFO` giúp có các mốc vận hành và lỗi quan trọng mà không bật quá nhiều log từ dependency.

Khi cần điều tra package riêng, có thể ghi đè bằng command-line property lúc khởi động:

```bash
java -jar customer-cli.jar \
  --logging.level.com.example.customercli.service=DEBUG
```

Hoặc dùng environment variable cho package:

```bash
LOGGING_LEVEL_COM_EXAMPLE_CUSTOMERCLI_SERVICE=DEBUG \
  java -jar customer-cli.jar
```

Quy tắc environment variable của Spring Boot thay dấu chấm bằng dấu gạch dưới, bỏ dấu gạch ngang và chuyển thành chữ hoa. Cách này phù hợp với logger package. Do relaxed binding chuyển tên biến thành chữ thường, không thể cấu hình chính xác logger theo tên class có chữ hoa bằng cách này; với logger class cụ thể, dùng config file hoặc `SPRING_APPLICATION_JSON`.

## Dùng logging groups để điều chỉnh nhiều logger

Khi cần điều chỉnh một nhóm logger liên quan, Spring Boot hỗ trợ `logging.group.<group-name>`. Boot có sẵn hai group phổ biến:

| Group | Logger thành viên chính |
|---|---|
| `web` | `org.springframework.core.codec`, `org.springframework.http`, `org.springframework.web` và một số web infrastructure logger |
| `sql` | `org.springframework.jdbc.core`, `org.hibernate.SQL` và logger SQL liên quan |

Có thể bật group `sql` ở `DEBUG` trong môi trường phát triển:

```yaml
logging:
  level:
    root: INFO
    sql: DEBUG
```

Có thể tạo group riêng cho các module của ứng dụng:

```yaml
logging:
  group:
    customer-import: com.example.customercli.importer,com.example.customercli.csv
    remote-api: com.example.customercli.remote,com.example.customercli.http
  level:
    root: INFO
    customer-import: DEBUG
    remote-api: INFO
```

Khi điều tra lỗi import, chỉ cần tăng `customer-import` thay vì bật `DEBUG` cho toàn bộ ứng dụng. Nếu group chứa logger SQL hoặc HTTP, kiểm tra trước xem log có thể in dữ liệu đầu vào, query parameter, header hoặc payload nhạy cảm hay không.

## Tách cấu hình theo profile

Một CLI thường chạy ở môi trường local, test, staging và production. Đặt cấu hình chung ở `application.yaml`, sau đó tạo file `application-{profile}.yaml` cho khác biệt về log level.

`application.yaml`:

```yaml
logging:
  level:
    root: INFO
    com.example.customercli: INFO
```

`application-dev.yaml`:

```yaml
logging:
  level:
    root: INFO
    com.example.customercli: DEBUG
    com.example.customercli.remote: TRACE
```

`application-prod.yaml`:

```yaml
logging:
  level:
    root: INFO
    com.example.customercli: INFO
    org.springframework: WARN
```

Kích hoạt profile khi chạy:

```bash
SPRING_PROFILES_ACTIVE=dev java -jar customer-cli.jar
```

PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
java -jar .\customer-cli.jar
```

Profile `dev` có thể tăng log cho package ứng dụng để chẩn đoán. Không đặt `TRACE` cho toàn bộ Spring hoặc SQL trong production. Cấu hình bên ngoài JAR, environment variables và command-line arguments có thể ghi đè file profile; command-line properties có độ ưu tiên cao hơn config data. Khi log level khác mong đợi, kiểm tra profile đang active và nguồn property override trước khi thay đổi logger.

## Phân biệt --debug, --trace và logging.level

Spring Boot có cờ chẩn đoán khi khởi động:

```bash
java -jar customer-cli.jar --debug
```

`--debug` yêu cầu một số logger lõi của Spring Boot, embedded container và Hibernate ghi nhiều thông tin hơn. Nó không đặt tất cả logger của ứng dụng ở `DEBUG`.

`--trace` tương tự nhưng tăng trace cho một tập logger lõi khác, bao gồm các phần của Spring và Hibernate schema generation:

```bash
java -jar customer-cli.jar --trace
```

Để bật logger của ứng dụng, cấu hình `logging.level` rõ ràng:

```bash
java -jar customer-cli.jar \
  --logging.level.com.example.customercli=DEBUG
```

Phân biệt các cách dùng:

| Cách | Tác dụng |
|---|---|
| `--debug` | Chế độ debug chọn lọc cho logger lõi của Spring Boot và một số thư viện |
| `--trace` | Chế độ trace chọn lọc cho logger lõi được Spring Boot chỉ định |
| `--logging.level.com.example.customercli=DEBUG` | Đặt level cụ thể cho logger/package ứng dụng |
| `logging.level.root: DEBUG` | Bật DEBUG cho root và các logger con kế thừa; có thể tạo lượng log rất lớn |

`--debug` và `--trace` là tham số lúc khởi động process, không phải command Spring Shell chạy sau khi REPL đã mở. Trong script/CI, hãy đặt đúng vị trí trước khi ứng dụng khởi động và chỉ bật trong khoảng thời gian điều tra.

## Quy ước bật debug có kiểm soát

Không bật debug toàn cục trong cấu hình production chỉ để điều tra một lỗi. Dùng thứ tự sau:

1. Xác định package/logger liên quan từ stack trace hoặc log hiện có.
2. Bật `DEBUG` cho package hoặc logging group nhỏ nhất có thể.
3. Tái hiện một lần với dữ liệu giả hoặc dữ liệu đã được che.
4. Thu thập log trong khoảng thời gian ngắn và gắn operation/correlation ID.
5. Đặt logger về level trước đó hoặc xóa override runtime.
6. Kiểm tra log đã thu thập trước khi chia sẻ ra ngoài nhóm vận hành.

Nếu cần dùng `TRACE`, ghi rõ người yêu cầu, thời điểm bắt đầu, thời điểm tắt và nơi lưu log. Đặt deadline để không quên tắt. Không để một profile debug trở thành profile mặc định của release production.

## Thay đổi log level khi ứng dụng đang chạy

Nếu ứng dụng có Spring Boot Actuator và đã bật endpoint `loggers`, người vận hành có thể xem level hiệu lực và thay đổi logger mà không cần restart. Endpoint web thường có dạng:

```text
GET  /actuator/loggers/com.example.customercli
POST /actuator/loggers/com.example.customercli
```

Đọc cấu hình hiện tại:

```bash
curl http://localhost:8080/actuator/loggers/com.example.customercli
```

Đặt logger thành `DEBUG`:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":"DEBUG"}' \
  http://localhost:8080/actuator/loggers/com.example.customercli
```

Xóa level riêng để logger kế thừa từ parent:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{}' \
  http://localhost:8080/actuator/loggers/com.example.customercli
```

Ví dụ trên chỉ hoạt động khi ứng dụng có Actuator, endpoint được expose và có web management endpoint đang chạy. Trong CLI không chạy web server, không giả định URL này tồn tại; có thể dùng cơ chế management/JMX hoặc một công cụ nội bộ đã được bảo vệ.

Nếu expose endpoint, chỉ cho phép truy cập từ mạng quản trị hoặc qua xác thực/authorization phù hợp. Không expose `loggers` công khai. Người có quyền thay đổi level có thể bật `TRACE`, làm tăng dung lượng log hoặc khiến dữ liệu nhạy cảm xuất hiện. Ghi audit người thay đổi, logger, level cũ/mới và thời gian thay đổi.

## Ghi log vào file và giới hạn dung lượng

Spring Boot mặc định ghi log ra console. Để ghi thêm vào file, cấu hình `logging.file.name` hoặc `logging.file.path`:

```yaml
logging:
  file:
    name: logs/customer-cli.log
```

Nếu chỉ đặt `logging.file.path`, Boot tạo `spring.log` trong thư mục đó. Nếu đặt cả `name` và `path`, `name` được dùng và `path` bị bỏ qua. File path tương đối được tính từ working directory.

Với Logback, có thể cấu hình rolling policy bằng các property Spring Boot:

```yaml
logging:
  file:
    name: logs/customer-cli.log
  logback:
    rollingpolicy:
      file-name-pattern: "${LOG_FILE}.%d{yyyy-MM-dd}.%i.gz"
      max-file-size: 20MB
      total-size-cap: 500MB
      max-history: 14
```

Các property quan trọng:

| Property | Ý nghĩa |
|---|---|
| `logging.logback.rollingpolicy.file-name-pattern` | Mẫu tên file archive |
| `logging.logback.rollingpolicy.max-file-size` | Dung lượng tối đa trước khi rotate |
| `logging.logback.rollingpolicy.total-size-cap` | Tổng dung lượng tối đa của các archive |
| `logging.logback.rollingpolicy.max-history` | Số archive tối đa được giữ |
| `logging.logback.rollingpolicy.clean-history-on-start` | Có dọn archive khi ứng dụng khởi động hay không |

Spring Boot mặc định rotate file khi đạt 10 MB và mặc định giữ tối đa 7 archive với cấu hình Logback tiêu chuẩn. Giá trị ở ví dụ trên thay đổi chính sách đó. Chọn dung lượng và thời gian giữ theo dung lượng ổ đĩa, tần suất chạy CLI, yêu cầu audit và chính sách lưu trữ của tổ chức.

Với CLI chạy một lần trong pipeline/container, thường phù hợp hơn khi ghi log ra console để runtime thu thập. Với CLI chạy lâu dài trên máy chủ, file log cần có rotation, quyền truy cập, backup và retention rõ ràng. Không để file log tăng vô hạn hoặc ghi vào thư mục có thể bị người dùng không tin cậy đọc.

## Structured logging và correlation ID

Log dạng text dễ đọc trong terminal. Khi gửi log tới hệ thống tập trung, JSON có cấu trúc giúp lọc theo level, operation ID, service, logger và timestamp.

Spring Boot 3.4 hỗ trợ các format JSON có sẵn như ECS, GELF và Logstash. Ví dụ bật ECS cho console và file:

```yaml
logging:
  structured:
    format:
      console: ecs
      file: ecs
    ecs:
      service:
        name: customer-cli
        version: 1.4.0
        environment: production
```

Nếu dùng custom Logback/Log4j2 configuration, cấu hình encoder/layout theo các system property mà Spring Boot cung cấp để structured logging hoạt động. Không giả định việc đổi format JSON tự động lọc secret; ứng dụng vẫn phải quyết định field nào được ghi.

Với một command xử lý nhiều bước, thêm operation ID vào MDC để các log liên quan có thể tìm cùng nhau:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

class ExportService {

    private static final Logger log = LoggerFactory.getLogger(ExportService.class);

    void export(String operationId) {
        MDC.put("operationId", operationId);
        try {
            log.info("Export started");
            // Thực hiện export.
            log.info("Export completed");
        } finally {
            MDC.remove("operationId");
        }
    }
}
```

Xóa MDC trong `finally` để tránh dữ liệu của command trước xuất hiện trong log của tác vụ tiếp theo khi thread được tái sử dụng. Không đưa access token, email, số tài khoản hoặc PII vào correlation ID. Dùng ID ngẫu nhiên/opaque và chỉ ghi metadata tối thiểu.

## Bảo vệ log khi bật DEBUG/TRACE

Debug log có thể chứa nhiều thông tin hơn dự kiến: SQL, query parameter, header, file path, nội dung request, cấu hình hoặc dữ liệu người dùng. Trước khi bật level cao, xác định logger nào có thể in dữ liệu nhạy cảm.

Không ghi trực tiếp:

- Password, API token, refresh token, cookie, session ID hoặc Authorization header.
- Private key, encryption key, database connection string có credential.
- Dữ liệu cá nhân nhạy cảm hoặc payload đầy đủ khi không cần thiết.
- Nội dung file import/export chứa thông tin khách hàng.
- Toàn bộ object có `toString()` chứa trường bí mật.

Nên ghi metadata đã chọn lọc:

```java
// Không an toàn: request.toString() có thể chứa token và dữ liệu cá nhân.
log.debug("Remote request: {}", request);

// Tốt hơn: chỉ ghi thông tin vận hành đã được allowlist.
log.debug("Calling remote API operationId={} method={} target={}",
        operationId, "POST", "/customers/import");
```

Dữ liệu do người dùng nhập có thể chứa ký tự xuống dòng hoặc delimiter. Sanitize/encode dữ liệu không tin cậy trước khi ghi log để tránh log injection. Parameterized logging giữ message template ổn định nhưng tự nó không ngăn CR/LF injection; structured encoder cần escape giá trị đúng định dạng.

Một số logger SQL hoặc HTTP có thể ghi query và bind value. Chỉ bật chúng khi đã hiểu nội dung sẽ được ghi và có dữ liệu thử không nhạy cảm. Đặc biệt, không bật trace bind parameter trong production chỉ để xem một câu query.

## Quy ước log cho command Spring Shell

Đối với mỗi command, nên thống nhất các mốc sau:

| Thời điểm | Level | Field nên ghi |
|---|---|---|
| Bắt đầu command | `INFO` | command name, operation ID, actor ID đã được phép ghi, profile |
| Đã validate input | `DEBUG` | loại operation, số lượng input, lựa chọn xử lý đã được lọc |
| Gọi dependency | `DEBUG` | service name, attempt, duration hoặc endpoint alias không nhạy cảm |
| Có retry/fallback | `WARN` | nguyên nhân an toàn, attempt, quyết định tiếp theo |
| Thành công | `INFO` | operation ID, số lượng xử lý, duration |
| Thất bại | `ERROR` | operation ID, error code, exception |

Không log cùng một exception ở mọi tầng. Nếu service đã ghi stack trace rồi command cũng ghi lại, log sẽ bị trùng. Chọn một tầng chịu trách nhiệm ghi exception đầy đủ; tầng khác có thể trả thông báo ngắn cho người dùng kèm operation ID.

Thông báo người dùng nên hữu ích nhưng không tiết lộ chi tiết nội bộ:

```text
Không thể kết nối dịch vụ khách hàng. Mã tham chiếu: op-7f3a.
Kiểm tra kết nối mạng hoặc xem log vận hành để biết chi tiết.
```

Log nội bộ có thể chứa exception và stack trace cần thiết, nhưng vẫn phải loại bỏ secret và payload không cần thiết.

## Kiểm tra cấu hình log đang có hiệu lực

Khi log không xuất hiện hoặc có quá nhiều log, kiểm tra theo thứ tự:

1. Profile nào đang active?
2. `logging.level.root` đang là gì?
3. Logger cụ thể có level riêng hay đang kế thừa từ parent?
4. Có command-line argument, environment variable hoặc external config ghi đè không?
5. Ứng dụng dùng Logback, Log4j2 hay JUL?
6. Log đang đi tới console, file hay appender khác?
7. Nếu có Actuator, xem `configuredLevel` và `effectiveLevel` của logger.

Actuator `GET /actuator/loggers/{logger-name}` trả level đã cấu hình và level hiệu lực. Nếu `configuredLevel` rỗng, logger thường kế thừa từ ancestor; `effectiveLevel` cho biết level thực tế được dùng.

Với cấu hình file, kiểm tra `logging.file.name`, `logging.file.path`, quyền ghi thư mục và working directory. Với cấu hình Logback tùy chỉnh, kiểm tra logger có appender đúng và `additivity` có làm log bị ghi trùng hay không.

## Ma trận kiểm thử logging

| Kịch bản | Điều cần xác nhận |
|---|---|
| Root `INFO` | `INFO`, `WARN`, `ERROR` xuất hiện; `DEBUG`/`TRACE` không xuất hiện |
| Package ứng dụng `DEBUG` | Chỉ package được chọn tăng chi tiết |
| Logger con có level riêng | Level con ghi đè level kế thừa |
| `--debug` lúc startup | Logger lõi tăng thông tin; logger app không tự động thành DEBUG |
| `--trace` lúc startup | Chỉ tập logger Boot chọn được trace |
| Profile `dev` | Package được chỉ định ở DEBUG/TRACE |
| Profile `prod` | Root và app giữ level vận hành đã định |
| Environment override | Package-level logger nhận đúng env var |
| File output | Log được ghi đúng đường dẫn và có rotation |
| Structured JSON | Mỗi event parse được và có field cần thiết |
| MDC | Operation ID xuất hiện đúng các dòng liên quan và được xóa sau operation |
| Secret sentinel | Password/token giả không xuất hiện trong console, file, exception hoặc JSON |
| CR/LF input | Dữ liệu không thể giả mạo thêm log record |
| Actuator logger endpoint | Chỉ principal được phép mới xem/đổi level |
| CLI output redirect | Log không làm hỏng JSON/CSV hoặc script output |

Nên dùng một chuỗi sentinel giả trong test, ví dụ `fake-token-do-not-log`, rồi tìm chuỗi đó trong log capture và output. Không dùng credential thật trong test hoặc khi chụp màn hình hỗ trợ.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Thêm `--debug` nhưng log app vẫn ở INFO | `--debug` chỉ cấu hình một tập logger lõi | Đặt `logging.level.<package>=DEBUG` |
| Bật DEBUG root làm log quá nhiều | Tất cả logger con kế thừa DEBUG | Giữ root INFO, tăng level package/group cụ thể |
| Environment variable không đổi logger theo class | Relaxed binding chuyển tên biến thành chữ thường | Dùng file config hoặc `SPRING_APPLICATION_JSON` cho class logger |
| Profile dev không có tác dụng | Profile chưa active hoặc bị nguồn ưu tiên cao hơn ghi đè | Kiểm tra active profiles và property source |
| Không thấy file log | Chưa đặt `logging.file.name/path`, sai working directory hoặc thiếu quyền ghi | Kiểm tra property và quyền thư mục |
| File log tăng vô hạn | Chưa cấu hình rotation hoặc dùng logging system khác Logback | Cấu hình rolling policy tương ứng với logging backend |
| Log bị lặp | Appender gắn ở logger con và root, additivity không phù hợp | Kiểm tra logger hierarchy và appender references |
| Bật SQL debug làm lộ dữ liệu | Logger query/bind ghi câu lệnh và parameter | Chỉ bật có kiểm soát, lọc dữ liệu và tắt sau điều tra |
| Log làm hỏng output command | Log console trộn với JSON/CSV hoặc bảng | Tách stream/appender, ghi file hoặc stderr và kiểm thử redirect |
| JSON log vẫn chứa secret | Structured format không tự redaction | Allowlist field và loại bỏ secret trước khi log |
| Log bị giả mạo nhiều dòng | Input chứa CR/LF hoặc delimiter | Sanitize/encode input và giới hạn độ dài |
| Actuator logger endpoint bị truy cập trái phép | Expose endpoint không có auth/network restriction | Giới hạn management endpoint và audit thay đổi level |

## Quy trình vận hành debug

1. Dùng `INFO` làm mức mặc định cho root và package ứng dụng.
2. Ghi `WARN` cho tình huống bất thường có thể phục hồi và `ERROR` cho thao tác thất bại.
3. Định nghĩa logging groups cho các module thường được điều tra cùng nhau.
4. Tách profile `dev` và `prod`; không đưa `DEBUG`/`TRACE` toàn cục vào cấu hình production.
5. Khi cần debug, tăng level cho package/group nhỏ nhất và đặt thời hạn tắt.
6. Chỉ dùng `--debug`/`--trace` khi cần chẩn đoán logger lõi của Spring Boot.
7. Dùng file rotation hoặc structured logging phù hợp với môi trường triển khai.
8. Gắn operation/correlation ID nhưng không đưa PII hoặc secret vào MDC.
9. Kiểm tra redaction, log injection, quyền đọc và retention trước khi chia sẻ log.
10. Khôi phục level ban đầu, ghi audit thay đổi và xác nhận log volume đã trở lại bình thường.

Quy ước level tốt giúp terminal giữ được thông tin hữu ích, còn log vận hành vẫn đủ chi tiết để điều tra. Đặt mặc định ổn định, tăng mức log đúng phạm vi và luôn kiểm tra nội dung nhạy cảm trước khi phát hành hoặc chia sẻ log.

## Tài liệu tham khảo

- [Spring Boot 3.4 — Logging](https://docs.spring.io/spring-boot/3.4/reference/features/logging.html): default console logging, `--debug`/`--trace`, levels, logging groups, file output, rolling policy và structured logging.
- [Spring Boot 3.4 — Externalized Configuration](https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html): property source precedence, command-line properties, external config và profile-specific files.
- [Spring Boot 3.4 — Profiles](https://docs.spring.io/spring-boot/3.4/reference/features/profiles.html): active profiles và profile-specific configuration.
- [Spring Boot 3.4 — Actuator Loggers Endpoint](https://docs.spring.io/spring-boot/3.4/api/rest/actuator/loggers.html): xem, đặt và xóa logger level lúc runtime.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html): logger hierarchy, level inheritance và quy tắc chọn log event.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html): cấu hình logger, appender, level và additivity.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu cần loại bỏ/che, log injection, bảo vệ, giám sát và retention của log.
