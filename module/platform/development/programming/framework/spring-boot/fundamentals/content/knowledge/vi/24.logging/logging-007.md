# Log console, log file và giới hạn quản lý vòng đời file

Logging là một trong những khả năng quan trọng nhất khi vận hành ứng dụng Spring Boot. Log giúp trả lời các câu hỏi: ứng dụng đã khởi động chưa, request nào thất bại, lỗi xuất hiện ở service nào, tác vụ batch có hoàn thành không và tài nguyên hệ thống có đang gặp vấn đề không.

Spring Boot thường cấu hình sẵn logging cho **console**. Khi cần lưu log thành tệp, ứng dụng có thể bật **file logging** và cấu hình **rolling/retention** để tránh ghi mãi vào một tệp. Tuy nhiên, việc ghi log xuống file không đồng nghĩa framework sẽ tự giải quyết toàn bộ vòng đời của log: dung lượng đĩa, số lượng tệp, chính sách lưu trữ, log shipping, backup, xóa dữ liệu nhạy cảm và xử lý file khi deploy vẫn cần thiết kế vận hành.

Bài học tập trung vào ba vấn đề có liên hệ chặt chẽ:

1. Spring Boot ghi log ra console như thế nào và khi nào nên sử dụng.
2. Cách ghi log ra file bằng các property và cấu hình logging phù hợp.
3. Các **giới hạn của việc quản lý vòng đời file log**, bao gồm rotation, retention, disk usage, nhiều instance và môi trường container.

Các ví dụ sử dụng API SLF4J và cách cấu hình Logback phổ biến trong Spring Boot. Một số tên property, default và starter có thể thay đổi giữa các phiên bản Spring Boot; khi áp dụng production hãy đối chiếu với dependency và reference documentation của phiên bản đang sử dụng.

## 1. Logging trong Spring Boot gồm những tầng nào?

Một ứng dụng Spring Boot thường ghi log qua API chung như **SLF4J**:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
public class OrderService {

    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void placeOrder(String orderId) {
        log.info("Placing order {}", orderId);
        // Xử lý nghiệp vụ.
    }
}
```

Các tầng cần phân biệt:

| Tầng | Nhiệm vụ | Ví dụ |
|---|---|---|
| Logging API | Cung cấp method ghi log | SLF4J `Logger` |
| Logging implementation | Quyết định cách xử lý sự kiện log | Logback, Log4j2 |
| Logger configuration | Level, pattern, appender, rolling | `application.yml`, `logback-spring.xml` |
| Appender/output | Đưa log tới đích | Console, file, hệ thống thu thập |
| Hạ tầng vận hành | Thu thập, giữ, tìm kiếm và xóa log | Container runtime, agent, log platform |

Với cấu hình thông dụng, Spring Boot dùng Logback qua starter logging phù hợp. Nhưng ứng dụng có thể được cấu hình dùng Log4j2 hay một implementation khác. Không nên áp dụng property riêng của Logback rồi kỳ vọng mọi implementation đều hiểu.

Một sự kiện log có thể đi đến nhiều appender cùng lúc: console **và** file. Không có quy tắc bắt buộc “chọn file thì console phải tắt”.

## 2. Console logging là gì?

Console logging là cách ghi sự kiện log ra luồng console của tiến trình, thường là stdout hoặc stderr tùy cấu hình appender.

Ví dụ:

```java
private static final Logger log =
        LoggerFactory.getLogger(InventoryService.class);

public void reserve(String sku, int quantity) {
    log.debug("Reserving sku={} quantity={}", sku, quantity);
    log.info("Reservation requested for {}", sku);
}
```

Khi chạy:

```bash
java -jar app.jar
```

bạn có thể thấy log startup và log ứng dụng trong terminal. Ví dụ minh họa:

```text
2026-11-13T09:00:01.432+07:00  INFO ... OrdersApplication : Started OrdersApplication
2026-11-13T09:00:02.105+07:00  INFO ... InventoryService   : Reservation requested for SKU-123
```

Định dạng thực tế tùy phiên bản Boot, backend logging, logging pattern và những thông tin MDC/tracing được bật.

### Vì sao console là mặc định hữu ích?

- Không cần chỉ định file path hoặc quyền ghi thư mục.
- Phù hợp khi chạy local và theo dõi lỗi lúc phát triển.
- Container runtime và hệ thống orchestration thường có thể thu thập stdout/stderr.
- Không cần ứng dụng tự quản lý tệp log trên mỗi container.
- Tránh phụ thuộc vào filesystem có thể chỉ đọc hoặc tồn tại ngắn hạn.

Đặc biệt trong container/Kubernetes, một cách triển khai phổ biến là **ghi log ra console rồi để nền tảng thu thập và chuyển đi**. Tuy nhiên, console logging không tự bảo đảm log sẽ được lưu lâu dài: retention và khả năng truy vấn phụ thuộc vào runtime và hệ thống log aggregation.

## 3. Console logging không phải System.out.println

Hai đoạn sau không tương đương về quản trị log:

```java
System.out.println("Order " + orderId + " created");
```

```java
log.info("Order {} created", orderId);
```

Với `System.out.println`:

- Dữ liệu được ghi trực tiếp ra `System.out`.
- Không sử dụng logger level, logger name, appender chain theo cách logging API xử lý.
- Thông thường không có pattern/metadata chuẩn của backend logging.
- Không tự động được ghi vào file appender chỉ vì ứng dụng bật file logging.

Với `log.info`:

- Sự kiện đi qua logging framework.
- Có logger name, level, message và exception.
- Backend quyết định output destinations và format.
- Có thể lọc theo package hoặc logger.
- Có thể tích hợp MDC, tracing và structured logging.

Nếu công cụ ngoài tiến trình redirect toàn bộ stdout vào file, `System.out.println` cũng có thể xuất hiện trong file đó. Nhưng đây là **redirect của hệ điều hành**, không phải việc SLF4J quản lý dòng `System.out.println`.

Ưu tiên dùng logger trong code ứng dụng. Dành `System.out.println` cho ví dụ đơn giản hoặc công cụ dòng lệnh có đầu ra thực sự là dữ liệu cho người dùng.

## 4. Logging level quyết định những gì xuất hiện

Các level phổ biến trong hệ sinh thái SLF4J:

| Level | Ý nghĩa thường gặp |
|---|---|
| TRACE | Thông tin cực chi tiết, thường chỉ dùng khi điều tra chuyên sâu |
| DEBUG | Dữ liệu phục vụ debug trong quá trình phát triển |
| INFO | Sự kiện vận hành bình thường, đáng chú ý |
| WARN | Tình huống bất thường nhưng hệ thống có thể tiếp tục |
| ERROR | Lỗi cần được quan sát, điều tra hoặc xử lý |

Ví dụ:

```java
log.trace("Checking candidate {}", candidateId);
log.debug("Validated {} items", itemCount);
log.info("Import finished, count={}", itemCount);
log.warn("Retrying request after timeout");
log.error("Import failed", exception);
```

Có thể đặt level trong `application.properties`:

```properties
logging.level.root=INFO
logging.level.com.example.orders=DEBUG
logging.level.org.springframework.web=WARN
```

Hoặc YAML:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    org.springframework.web: WARN
```

Nếu logger có effective level INFO, sự kiện DEBUG và TRACE thông thường không được xuất ra các appender của logger đó. Nếu chuyển package ứng dụng sang DEBUG, lượng log tăng và có thể làm tăng chi phí I/O, network và dung lượng lưu trữ.

**Đổi output từ console sang file không thay thế việc quản lý level.** Hai việc này nên được thiết kế riêng.

## 5. Ghi log với parameterized messages

SLF4J hỗ trợ placeholder `{}`:

```java
log.info("Created orderId={} for customerId={}",
        orderId, customerId);
```

Thường nên dùng cách này thay vì luôn nối chuỗi:

```java
log.debug("Customer " + customerId + " has " + count + " orders");
```

Với parameterized logging, framework có thể tránh một số chi phí format message khi level không bật. Tuy nhiên, biểu thức Java dùng để tính argument vẫn được đánh giá trước lời gọi method; nếu việc chuẩn bị giá trị rất tốn kém, cần kiểm tra level hoặc dùng API logging phù hợp.

Khi log exception:

```java
try {
    paymentGateway.charge(payment);
} catch (PaymentException ex) {
    log.error("Payment failed for orderId={}", orderId, ex);
    throw ex;
}
```

Truyền exception vào vị trí phù hợp giúp logging framework có thể ghi stack trace. Chỉ ghi `ex.getMessage()` thường mất thông tin về call stack.

Không log bí mật như password, API key, access token hay số thẻ thanh toán. Cần chuẩn hóa/redact dữ liệu trước khi ghi log và tuân thủ quy định lưu trữ.

## 6. Console output và màu ANSI

Console của Spring Boot có thể được cấu hình để dùng ANSI colors nhằm phân biệt level và các trường trong log.

Ví dụ property:

```properties
spring.output.ansi.enabled=detect
```

Các lựa chọn thường gặp:

- `detect`: tự phát hiện khả năng hỗ trợ màu.
- `always`: cố bật ANSI output.
- `never`: tắt ANSI escape sequences.

Trong terminal hỗ trợ màu, ANSI có thể giúp con người đọc nhanh hơn. Tuy nhiên, nếu chuyển nguyên ký tự ANSI vào file hoặc log collector không xử lý escape code, log sẽ khó đọc.

Với môi trường production và log pipeline, nên kiểm tra format output và tắt ANSI nếu không phù hợp. Một số nền tảng tự chuyển đổi hoặc loại bỏ ANSI, nhưng không nên giả định mọi collector làm được điều này.

## 7. File logging là gì?

File logging ghi sự kiện log vào một tệp trên filesystem.

Ví dụ:

```text
Ứng dụng
   │
   ▼
SLF4J Logger
   │
   ▼
Logging backend (Logback)
   │
   ├── Console appender ──► stdout/stderr
   │
   └── File appender ─────► ./logs/orders.log
```

File log hữu ích khi:

- Cần xem lại log trên một máy cụ thể sau khi tiến trình thoát.
- Máy chủ hoặc hệ thống cũ có công cụ thu gom log từ file.
- Cần tệp riêng cho một ứng dụng trong môi trường không có tập trung log.
- Có quy định vận hành yêu cầu lưu log tại filesystem được quản lý.

Nhưng file logging tạo thêm trách nhiệm:

- Phải có đường dẫn và quyền ghi.
- Filesystem có thể đầy.
- File có thể mất sau redeploy/container recreation.
- Cần rotation và retention.
- Cần xác định ai thu thập/xóa các file cũ.
- Phải ngăn secret bị lưu vào tệp quá lâu hoặc truy cập trái phép.

## 8. Bật file logging bằng logging.file.name

Với các phiên bản Spring Boot hỗ trợ nhóm property này, cách đơn giản là:

```properties
logging.file.name=logs/orders.log
```

Hoặc:

```yaml
logging:
  file:
    name: logs/orders.log
```

Ứng dụng sẽ cấu hình file logging theo đường dẫn được chỉ định nếu logging backend và Boot logging configuration hỗ trợ.

Đường dẫn có thể là relative hoặc absolute, tùy môi trường:

```properties
logging.file.name=/var/log/orders/orders.log
```

Ví dụ relative:

```properties
logging.file.name=./logs/orders.log
```

Relative path được diễn giải dựa trên **working directory của tiến trình**. Khi chạy từ IDE, terminal, systemd hoặc container với thư mục làm việc khác nhau, file có thể được tạo ở những vị trí khác nhau.

Vì thế, nếu không tìm thấy file, đừng chỉ kiểm tra nội dung property. Hãy kiểm tra:

1. Working directory thực tế.
2. Đường dẫn đã resolve.
3. Quyền tạo thư mục/file.
4. Filesystem có đủ dung lượng.
5. Logging configuration thực tế có dùng property đó không.

### File logging có tự tắt console không?

Thông thường không. Cấu hình logging mặc định của Spring Boot có thể giữ console appender và thêm file appender. Khi đó một sự kiện có thể xuất hiện ở cả console và file.

Nếu yêu cầu chỉ ghi file, cần cấu hình appender tương ứng hoặc cơ chế hỗ trợ của đúng phiên bản, không nên giả định `logging.file.name` tự tắt console.

## 9. Bật file logging bằng logging.file.path

Một property khác:

```properties
logging.file.path=./logs
```

Nó chỉ định **thư mục** chứa file log. Với cấu hình Spring Boot thông thường, file được đặt tên mặc định như `spring.log` trong thư mục đó.

So sánh:

| Property | Bạn chỉ định | Kết quả theo cấu hình Boot thông dụng |
|---|---|---|
| `logging.file.name=logs/app.log` | Tên/đường dẫn file | File `logs/app.log` |
| `logging.file.path=logs` | Thư mục | File mặc định như `logs/spring.log` |
| Không có cả hai | Không yêu cầu file output | Console logging thông thường |
| Có cả `name` và `path` | Cả file và thư mục | `logging.file.name` được ưu tiên |

Ví dụ:

```properties
logging.file.name=/srv/app/logs/orders.log
logging.file.path=/tmp/ignored-directory
```

Trong cấu hình hỗ trợ hai property trên, `logging.file.name` quyết định đường dẫn file; `logging.file.path` không thay thế giá trị đó.

**Khuyến nghị:** nếu muốn tên file rõ ràng, dễ kiểm tra trong deployment và monitoring, dùng `logging.file.name`; nếu chỉ quan tâm thư mục và chấp nhận tên mặc định, dùng `logging.file.path`.

## 10. Ghi file bằng tham số dòng lệnh và profile

Có thể đặt file logging tại thời điểm deploy thay vì đóng cứng trong artifact.

Ví dụ:

```bash
java -jar app.jar --logging.file.name=/var/log/orders/orders.log
```

Hoặc trong `application-prod.yml`:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: INFO
  file:
    name: /var/log/orders/orders.log
```

Khi profile `prod` active, file cấu hình này có thể cung cấp các property tương ứng:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Đây là cách tách nhu cầu development (console là đủ) khỏi môi trường cần file. Hãy bảo đảm profile được kích hoạt từ nguồn phù hợp và file path có quyền ghi.

Nếu một property source có precedence cao hơn (ví dụ command line) đặt `logging.file.name`, nó có thể override giá trị trong YAML. Khi debug cần kiểm tra **property hiệu lực** chứ không chỉ một file.

## 11. Phân biệt logging.file.name với output redirect

Có ít nhất hai cách tạo file chứa log:

**Cách A — Logging framework ghi file:**

```properties
logging.file.name=./logs/orders.log
```

Log event được xử lý qua appender, pattern và rolling policy của backend.

**Cách B — Shell redirect stdout/stderr:**

```bash
java -jar app.jar > app-console.txt 2>&1
```

Ở cách B, shell/OS redirect output của tiến trình sang file. File `app-console.txt` do redirect quản lý, **không tự chịu rolling policy của Logback file appender**.

| Tiêu chí | Logging file appender | Shell redirect |
|---|---|---|
| Đối tượng ghi | Logging framework | Shell/OS chuyển stream |
| Có thể lọc theo logger level | Có | Chỉ thấy nội dung đã được ứng dụng in ra |
| File rolling bằng Logback | Có khi cấu hình phù hợp | Không tự áp dụng |
| Bắt `System.out.println` | Không mặc định | Có |
| Bắt stderr | Tùy appender/config | Có với `2>&1` ở ví dụ |
| Định dạng | Pattern/encoder của backend | Nội dung gốc của stdout/stderr |

Không nên nghĩ redirect console đã thay thế file appender có rotation. Nếu dùng redirect trong production, phải có cơ chế log rotation/retention bên ngoài hoặc nền tảng quản lý phù hợp.

## 12. Vì sao một file log cần rotation?

Nếu liên tục append vào một file duy nhất, kích thước có thể tăng vô hạn cho tới khi filesystem đầy.

Ví dụ một dịch vụ tạo lượng log trung bình:

```text
500 KB/phút
    │
    ▼
30 MB/giờ
    │
    ▼
720 MB/ngày
    │
    ▼
~21,6 GB/30 ngày
```

Các số chỉ minh họa mức tăng giả định khi lưu lượng ổn định, không phải chỉ số đặc trưng của Spring Boot.

Khi filesystem đầy có thể xảy ra:

- Ghi log thất bại.
- Một số thao tác khác cùng phân vùng đĩa bị lỗi.
- Database/queue/cache trên máy bị ảnh hưởng nếu chia sẻ storage.
- Monitoring bị mất dấu vết vì không ghi được log mới.
- Ứng dụng hoặc host mất ổn định tùy cách xử lý lỗi I/O.

**Rolling/rotation** chuyển sang file log mới theo thời gian hoặc kích thước, giúp mỗi file có phạm vi quản lý rõ hơn.

**Retention** xác định lượng archive được giữ lại trước khi dọn. Rotation không đồng nghĩa retention; có thể rotate liên tục nhưng vẫn giữ vô hạn file cũ nếu không có chính sách xóa.

## 13. Rolling theo kích thước, thời gian và kết hợp

Các chiến lược thường gặp:

| Chiến lược | Khi nào tạo file mới? | Điểm cần lưu ý |
|---|---|---|
| Size-based | File đạt ngưỡng kích thước | Có thể tạo nhiều file trong cùng ngày |
| Time-based | Sang chu kỳ mới như ngày/tháng | Ngày lưu lượng cao có thể tạo file rất lớn |
| Size-and-time-based | Hết chu kỳ hoặc đạt ngưỡng size | Cân bằng khả năng giới hạn kích thước từng archive |
| External rotation | Tác vụ OS/agent đổi file | Phải phối hợp với process đang giữ file handle |

Với file log có lưu lượng thay đổi, **size-and-time rolling** là lựa chọn phổ biến. Ví dụ mỗi ngày có các archive:

```text
logs/
├── orders.log
├── orders.2026-11-11.0.log.gz
├── orders.2026-11-12.0.log.gz
├── orders.2026-11-12.1.log.gz
└── orders.2026-11-12.2.log.gz
```

Trong sơ đồ:

- `orders.log` là file active.
- Các file có ngày/index là archive.
- `.gz` chỉ archive được nén để tiết kiệm dung lượng.
- Nhiều archive trong một ngày có thể được tạo khi đạt ngưỡng size.

Đường dẫn và pattern cụ thể do backend cấu hình, không có quy tắc rằng mọi phiên bản Boot đều phải dùng đúng định dạng này.

## 14. Rolling policy của Logback qua Spring Boot properties

Trong các phiên bản Spring Boot dùng Logback có hỗ trợ các property dưới đây, có thể cấu hình:

```properties
logging.file.name=./logs/orders.log

logging.logback.rollingpolicy.file-name-pattern=./logs/orders.%d{yyyy-MM-dd}.%i.log.gz
logging.logback.rollingpolicy.max-file-size=20MB
logging.logback.rollingpolicy.max-history=14
logging.logback.rollingpolicy.total-size-cap=1GB
logging.logback.rollingpolicy.clean-history-on-start=true
```

Ví dụ YAML:

```yaml
logging:
  file:
    name: ./logs/orders.log

  logback:
    rollingpolicy:
      file-name-pattern: ./logs/orders.%d{yyyy-MM-dd}.%i.log.gz
      max-file-size: 20MB
      max-history: 14
      total-size-cap: 1GB
      clean-history-on-start: true
```

Các property `logging.logback.rollingpolicy.*` là **property riêng của cấu hình Logback được Spring Boot hỗ trợ**. Không áp dụng nguyên xi cho Log4j2 hoặc các version không có cùng contract.

### Ý nghĩa từng property

| Property | Ý nghĩa |
|---|---|
| `file-name-pattern` | Tên file archive với token ngày `%d`, index `%i`, tùy chọn nén như `.gz` |
| `max-file-size` | Ngưỡng kích thước kích hoạt rollover theo size trong policy tương ứng |
| `max-history` | Số chu kỳ lịch sử được giữ lại theo pattern thời gian |
| `total-size-cap` | Giới hạn tổng dung lượng archives được policy quản lý, theo semantics của backend |
| `clean-history-on-start` | Yêu cầu dọn archive cũ lúc startup theo khả năng policy |

Với pattern `%d{yyyy-MM-dd}`, `max-history=14` được hiểu theo **chu kỳ ngày**. Nếu chuyển sang pattern tháng, `max-history` phản ánh số chu kỳ tháng, không nên diễn giải thành 14 ngày trong mọi trường hợp.

### Những điều property không bảo đảm

- Không bảo đảm toàn filesystem chỉ sử dụng tối đa đúng `1GB`.
- Không giới hạn dung lượng logs của các ứng dụng khác cùng disk.
- Không tự đưa archive lên object storage.
- Không tự backup hoặc đáp ứng một chính sách compliance.
- Không tự xóa ngay mọi file quá hạn vào đúng thời điểm trên đồng hồ khi không có hoạt động rollover/cleanup thích hợp.
- Không tự quản lý file stdout redirect hoặc file do library khác tự ghi.

Việc cleanup phụ thuộc policy, thời điểm rollover/startup và quyền filesystem. Hãy kiểm tra thực tế ở môi trường vận hành.

## 15. Phân biệt max-file-size, max-history và total-size-cap

Ba giới hạn phục vụ ba câu hỏi khác nhau.

### 15.1. max-file-size: một file archive lớn tới đâu?

```properties
logging.logback.rollingpolicy.max-file-size=20MB
```

Đối với size-and-time based rolling policy, threshold này góp phần xác định khi nào cần chuyển từ file active sang archive mới trong cùng chu kỳ.

Đừng coi `20MB` là giới hạn cứng từng byte của mọi file trong mọi tình huống: một log event lớn, write buffering hoặc implementation details có thể khiến kích thước thực tế vượt mốc trước khi rollover.

### 15.2. max-history: giữ bao nhiêu chu kỳ lịch sử?

```properties
logging.logback.rollingpolicy.max-history=14
```

Nếu file-name-pattern sử dụng ngày, đây thường là giới hạn 14 chu kỳ lịch sử ngày cho archives do rolling policy quản lý.

Nếu hôm nay có ba archive do traffic cao, chúng vẫn thuộc cùng chu kỳ ngày. Vì vậy `max-history=14` không đồng nghĩa “chỉ giữ 14 file”.

### 15.3. total-size-cap: tổng archive được giữ bao nhiêu?

```properties
logging.logback.rollingpolicy.total-size-cap=1GB
```

Giới hạn này dùng để dọn archive vượt tổng mức dung lượng policy cho phép. Nó không phải một disk quota của OS và thường không bao gồm tất cả dữ liệu ngoài phạm vi archive mà policy quản lý.

Ngay cả khi cấu hình đúng, vẫn cần **monitor disk space** vì:

- File active vẫn chiếm chỗ.
- Các file khác có thể chiếm disk.
- Dung lượng tăng trước thời điểm dọn.
- Có thể tồn tại bản sao, temp files, file không thuộc policy.
- File bị xóa nhưng process khác còn giữ file descriptor trong một số OS vẫn có thể tiếp tục chiếm storage cho tới khi handle đóng.

### 15.4. Ước tính dung lượng cần thiết

Nếu bạn chọn:

```text
max-file-size = 20MB
max-history = 14 chu kỳ ngày
total-size-cap = 1GB
```

thì kế hoạch dung lượng vẫn phải dành headroom cho active file, quá trình tạo archive, nén, burst traffic và các dữ liệu khác trên cùng filesystem.

Không lấy `total-size-cap=1GB` làm bằng chứng rằng partition 1GB là đủ. Mức cap không phải hard filesystem quota và không phải cơ chế bảo vệ cuối cùng khi disk đầy.

## 16. Dọn lịch sử file log diễn ra khi nào?

Nhiều rolling policy chỉ thực hiện một phần công việc housekeeping khi xảy ra **rollover** hoặc ở startup nếu được cấu hình.

Ví dụ:

```text
Ứng dụng nhận log event
      │
      ▼
Kiểm tra điều kiện rollover
      │
      ├── Chưa tới ngưỡng
      │       └── Ghi vào file active
      │
      └── Tới ngưỡng/chu kỳ
              │
              ▼
         Đổi/đóng file active
              │
              ▼
         Tạo archive theo pattern
              │
              ▼
         Nén và cleanup nếu policy yêu cầu
              │
              ▼
         Tiếp tục ghi file active mới
```

Đây là luồng khái niệm; chi tiết thực tế phụ thuộc Logback rolling policy.

Một ứng dụng gần như không có log activity có thể không rollover đúng vào nửa đêm, vì rollover thường được trigger khi có log event tiếp theo. Do đó, việc archive cũ vẫn còn sau khi bước sang ngày mới không nhất thiết chứng minh cấu hình `max-history` sai.

`clean-history-on-start` có thể giúp dọn một phần archive cũ khi ứng dụng khởi động, nhưng không phải hệ thống dọn file nền độc lập hoạt động liên tục.

Khi có yêu cầu xóa đúng lịch theo phút/giây hoặc tuân thủ thời hạn pháp lý, cần thiết kế cơ chế retention bên ngoài hoặc hệ thống lưu trữ log chuyên dụng.

## 17. File logging có thể tiếp tục ghi khi ứng dụng restart không?

Tùy appender và cấu hình, file active thường được mở ở chế độ append để giữ log đã ghi. Nhưng không nên coi hành vi đó là hợp đồng bất biến của mọi logging configuration.

Các tình huống cần xem xét:

- Ứng dụng restart và ghi tiếp vào cùng file.
- Ứng dụng restart ở working directory khác, tạo file tại vị trí khác.
- Rolling policy phát hiện archive cần dọn khi startup.
- Một deployment script xóa hoặc thay thế thư mục logs.
- Container bị tạo lại nên filesystem trước đó không còn.
- File path trỏ tới volume không được mount trong lần chạy mới.

Muốn bảo đảm retention qua restart/redeploy, phải kiểm tra storage thực tế, mount/volume, policy của platform và cơ chế thu thập ngoài ứng dụng.

Nếu log quan trọng cho audit, không nên chỉ phụ thuộc một file trên local disk của service đang chạy.

## 18. Vòng đời của file handle và shutdown

Khi ghi file, logging appender thường giữ một file handle/stream trong quá trình chạy. Điều này ảnh hưởng tới việc thay tên, xóa và rotate file.

Một shutdown bình thường cho phép logging system đóng appender và flush theo cấu hình. Nhưng nếu tiến trình bị kill đột ngột, máy bị mất điện hoặc container bị cưỡng bức dừng, log vẫn có thể bị mất ở các buffer chưa kịp flush.

Trong ứng dụng dùng async logging/appender, có thể còn log events trong queue. Khi shutdown, cần cấu hình phù hợp để backend có cơ hội drain queue; không có bảo đảm tuyệt đối với process crash.

**Ranh giới cần nhớ:**

- Log event được code gọi không đồng nghĩa đã được đồng bộ bền vững lên disk.
- File đã có trong filesystem không đồng nghĩa archive đã được backup.
- Process dừng không sạch có thể làm thiếu một số dòng cuối cùng.
- Hệ thống tập trung log cũng có thể có độ trễ ingestion hoặc mất message nếu queue/network gặp sự cố.

Không nên dùng log thông thường làm nguồn dữ liệu giao dịch duy nhất. Với dữ liệu không được phép mất, cần cơ chế durable storage, audit/event pipeline có contract riêng.

## 19. Logback cấu hình chuyên sâu bằng logback-spring.xml

Khi các property mặc định không đủ để diễn đạt nhiều appender hoặc chính sách phức tạp, có thể tạo `src/main/resources/logback-spring.xml`.

Ví dụ minh họa cho ứng dụng muốn vừa ghi console vừa ghi rolling file:

```xml
<configuration>
    <springProperty scope="context"
                    name="APP_NAME"
                    source="spring.application.name"
                    defaultValue="orders"/>

    <property name="LOG_DIR" value="./logs"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>${LOG_DIR}/${APP_NAME}.log</file>

        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>
                ${LOG_DIR}/${APP_NAME}.%d{yyyy-MM-dd}.%i.log.gz
            </fileNamePattern>
            <maxFileSize>20MB</maxFileSize>
            <maxHistory>14</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Để ví dụ ngắn gọn, nó chỉ dùng một root logger và hai appender. Trong hệ thống thật còn có thể cần:

- Logging level theo package.
- Pattern bao gồm traceId/spanId hoặc dữ liệu MDC đã được kiểm soát.
- Encoder structured JSON.
- Async appender có chính sách queue/flush rõ ràng.
- Nhiều file riêng theo concern, nếu cần.
- Profile-specific appender.
- Bảo vệ log path và kiểm soát quyền truy cập.

### Vì sao dùng logback-spring.xml thay vì logback.xml?

`logback-spring.xml` là convention được Spring Boot hỗ trợ để tích hợp các phần mở rộng như `<springProperty>` hoặc `<springProfile>` trong quá trình khởi tạo logging theo cách Boot quản lý.

Một file `logback.xml` do Logback tự load rất sớm có thể không có quyền truy cập vào các Spring extension theo cùng cách. Vì vậy khi cần các tag đặc thù Spring, nên dùng `logback-spring.xml` trong setup Boot tương ứng.

Đừng khai báo cùng lúc nhiều nguồn cấu hình logging cạnh tranh mà không hiểu precedence. Khi đã tự định nghĩa appender/rolling policy bằng XML, các property mặc định của Boot có thể không còn điều khiển các appender đó nếu XML không tham chiếu tới chúng.

## 20. Cấu hình Logback theo profile

Nếu chỉ muốn ghi file trong production, một cách là tách cấu hình theo profile.

Ví dụ ý tưởng:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <springProfile name="dev">
        <root level="DEBUG">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="prod">
        <appender name="PROD_FILE"
                  class="ch.qos.logback.core.FileAppender">
            <file>./logs/prod.log</file>
            <append>true</append>
            <encoder>
                <pattern>%d %-5level %logger - %msg%n</pattern>
            </encoder>
        </appender>

        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
            <appender-ref ref="PROD_FILE"/>
        </root>
    </springProfile>
</configuration>
```

**Đây là ví dụ minh họa profile selection, không phải cấu hình rolling production hoàn chỉnh**: `FileAppender` trong nhánh prod không tự rotate. Nếu muốn rotation/retention, thay nó bằng `RollingFileAppender` phù hợp như phần trước.

Ngoài ra, nếu ứng dụng chạy với một tập profile khác cả dev lẫn prod, ví dụ chỉ `staging`, file trên không khai báo một root trong các nhánh đó. Khi thiết kế cấu hình thực tế, hãy có fallback rõ ràng hoặc một nhóm profile điều kiện phù hợp.

Nếu không cần custom XML, chỉ khai báo `logging.file.name` trong `application-prod.yml` thường đơn giản hơn.

## 21. Không trộn hai cơ chế rotation thiếu kiểm soát

Một lỗi vận hành phổ biến là để **Logback rolling policy** và công cụ ngoài như **logrotate** cùng quản lý một file theo cách không phối hợp.

Tình huống:

1. Logback đang giữ file handle của `orders.log`.
2. Công cụ OS đổi tên hoặc xóa `orders.log`.
3. Process có thể tiếp tục ghi vào file handle cũ thay vì file mới theo kỳ vọng.
4. Log collector nhìn thấy file mới nhưng thiếu các dòng đang được ghi vào inode/handle cũ.
5. Disk usage vẫn có thể tăng dù tên file cũ đã bị xóa trên một số filesystem.

Một số cấu hình external rotation dùng cơ chế copy-truncate hoặc yêu cầu process reopen file, nhưng mỗi cách có trade-off và rủi ro mất/trùng log. Không nên dùng tùy tiện để “sửa nhanh” vấn đề file lớn.

Nên xác định một **nguồn chịu trách nhiệm rotation chính**:

- Nếu Logback quản lý: cấu hình rolling policy và retention của Logback, để collector đọc file tương ứng.
- Nếu hạ tầng OS quản lý: chọn cách appender/rotation tương thích và thử nghiệm reopen/rename/flush.
- Nếu container platform quản lý stdout: ưu tiên không tự rotate file trong app, để runtime/collector thực hiện theo chính sách của platform.

## 22. Nhiều instance không nên cùng ghi một file

Giả sử chạy ba replicas của ứng dụng nhưng đều mount chung một volume và ghi:

```properties
logging.file.name=/shared/orders.log
```

Những tiến trình độc lập có thể ghi cùng file và cùng thực hiện rotation. Hậu quả có thể gồm:

- Dòng log xen kẽ.
- Archive collisions.
- Tệp bị rename hoặc nén trong khi process khác còn ghi.
- Retention của instance này xóa file instance khác cần.
- Khó xác định log thuộc instance nào.

Không nên mặc định một `RollingFileAppender` thông thường sẽ xử lý an toàn mọi tình huống multi-process shared log file.

Lựa chọn hợp lý hơn:

1. Ghi stdout/stderr để container runtime/collector gắn pod/container identity.
2. Nếu buộc phải ghi file, dùng đường dẫn riêng cho mỗi instance.
3. Thêm instance identifier vào log metadata hoặc tên file theo một chính sách an toàn.
4. Thu gom về hệ thống tập trung thay vì cho mọi replica cạnh tranh một file active.

Ví dụ đường dẫn được cấp bởi deployment:

```text
/var/log/orders/instance-a/orders.log
/var/log/orders/instance-b/orders.log
/var/log/orders/instance-c/orders.log
```

Số lượng instance thay đổi động làm công việc dọn file cũ càng quan trọng. Hạ tầng phải biết khi nào một instance đã dừng và file của nó còn cần lưu lại bao lâu.

## 23. File logging trong container và Kubernetes

Trong môi trường container, filesystem của container thường không được thiết kế để giữ log lâu dài qua việc xóa/tạo lại container.

Mô hình thu thập log phổ biến:

```text
Spring Boot logger
        │
        ▼
Console appender
        │
        ▼
stdout / stderr
        │
        ▼
Container runtime logging
        │
        ▼
Log collector / agent
        │
        ▼
Central logging / observability storage
```

Ưu điểm:

- Không cần ứng dụng quản lý file path chung trên node.
- Collector có thể thêm metadata của container/pod/namespace.
- Hệ thống lưu trữ log tập trung hỗ trợ tìm kiếm và retention.
- Không phụ thuộc vào lifecycle của container filesystem.

Nhưng điều này không có nghĩa “không cần quản lý log”:

- Container runtime vẫn có cơ chế giới hạn và rotate local logs.
- Collector có thể có queue, retry, backpressure và quota.
- Logging backend tập trung vẫn cần retention policy và kiểm soát chi phí.
- Khi bị mất kết nối hoặc quá tải, tùy pipeline có thể chậm trễ hoặc mất log.
- `kubectl logs` thường xem log stream của container, không tự đọc mọi file mà ứng dụng tự tạo trong container.

Nếu ghi file trong container, phải chọn volume/path phù hợp và thiết lập collector để đọc file. Mount volume không tự giải quyết retention hoặc rotation.

## 24. Vấn đề về quyền ghi và đường dẫn

Các lỗi thường gặp khi bật file:

```text
Permission denied
No such file or directory
Read-only file system
No space left on device
```

Nguyên nhân:

- Process chạy bằng user không có quyền ghi.
- Thư mục parent không tồn tại và backend không thể tạo nó theo setup.
- Container root filesystem là read-only.
- Mount volume sai.
- Partition hoặc quota đã đầy.
- Relative path khác dự kiến.
- File do process khác sở hữu.

Khi triển khai nên:

1. Chọn log directory có chủ sở hữu rõ ràng.
2. Chỉ cấp quyền cần thiết cho service user.
3. Bảo đảm mount và đường dẫn tồn tại hoặc được tạo hợp lệ.
4. Theo dõi disk free và inode usage nếu hệ điều hành cần.
5. Không cấp quyền ghi rộng chỉ để tránh lỗi permission.
6. Kiểm tra quyền file archive sau rotation và khi log collector đọc.

Ví dụ Unix shell để xem thư mục:

```bash
ls -lah ./logs
du -sh ./logs
df -h .
```

Ví dụ PowerShell:

```powershell
Get-ChildItem -LiteralPath .\logs
Get-Item -LiteralPath .\logs\orders.log
```

Đây là lệnh hỗ trợ quan sát, không phải lệnh phải chạy trong STEP 4 của việc biên soạn tài liệu.

## 25. Logging level ảnh hưởng trực tiếp vòng đời file

Giả sử production đang đặt:

```properties
logging.level.root=DEBUG
```

Một ứng dụng có rất nhiều request có thể ghi hàng triệu dòng DEBUG mỗi ngày, khiến:

- File active chạm max-file-size nhanh hơn.
- Số archive tăng.
- Retention xóa log cũ sớm hơn nếu bị giới hạn bởi total-size-cap.
- Disk I/O và CPU cho format/compression tăng.
- Log collector phát sinh thêm traffic và chi phí lưu trữ.

Ngược lại, nếu level quá cao như ERROR cho toàn bộ hệ thống, bạn có thể mất các sự kiện INFO cần thiết để phân tích hành trình request.

Cần cân bằng:

- INFO cho sự kiện vận hành quan trọng, tương đối ít.
- DEBUG/TRACE chỉ bật cho package cụ thể khi điều tra.
- Tránh log trong vòng lặp nóng nếu không cần.
- Không lặp stack trace ở mọi tầng xử lý cùng một lỗi.
- Dùng metric/tracing cho dữ liệu tần suất cao thay vì spam text logs.

**Rotation xử lý hậu quả của log volume, không thay thế việc quản lý log volume ngay tại nguồn.**

## 26. Structured logs, correlation ID và log file

Ở hệ thống nhiều service, một log line đơn lẻ có thể thiếu ngữ cảnh. Cần gắn correlation/trace identifier để liên kết các sự kiện.

Ví dụ:

```text
time=... level=INFO service=orders traceId=abc123 orderId=O123 message="order created"
```

Các lựa chọn:

- Logging pattern có MDC fields.
- Structured JSON logging.
- Tracing/observation integration có thể đưa trace/span IDs vào logging context.
- Collector thêm metadata như instance, environment, deployment.

Ví dụ pattern Logback minh họa:

```text
%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%X{traceId:-}] %logger - %msg%n
```

`%X{traceId:-}` đọc giá trị từ MDC nếu có, với fallback theo cú pháp pattern của Logback. Cần có thành phần thực sự đưa traceId vào MDC; chỉ thêm pattern không tự tạo trace ID.

Dù ghi console hay file, structured logging giúp log collector dễ parse hơn. Tuy nhiên, format có thể ảnh hưởng kích thước file và chiến lược retention. JSON thường dài hơn text tối giản, nên cần đo log volume thực tế.

## 27. Vòng đời file log và yêu cầu bảo mật

File log có thể chứa:

- Request identifiers.
- Tên người dùng hoặc customer ID.
- Đường dẫn tài nguyên.
- Nội dung exception.
- Query parameters.
- Dữ liệu nghiệp vụ.
- Thông tin có tính nhạy cảm nếu ứng dụng log không kiểm soát.

Vì vậy, việc quản lý vòng đời không chỉ là giữ bao nhiêu ngày:

1. **Quyền truy cập:** ai được đọc log trên host và trong hệ thống tập trung?
2. **Mã hóa:** cần mã hóa at rest/in transit ở cấp filesystem, storage hoặc pipeline không?
3. **Redaction:** những trường nào không được ghi ngay từ đầu?
4. **Retention:** giữ log bao lâu theo mục đích và yêu cầu hiện hành?
5. **Deletion:** xóa archive local có đủ không nếu còn bản sao collector/backup?
6. **Audit:** sự kiện quan trọng có cần lưu trong hệ thống audit riêng có kiểm soát không?

Đừng dựa vào `max-history=14` để kết luận mọi bản sao dữ liệu sẽ bị xóa sau đúng 14 ngày. Property này chỉ điều khiển một phần lịch sử file do rolling policy quản lý; không kiểm soát mọi nơi log đã được sao chép đến.

Ngoài ra, nên xử lý log injection: các chuỗi có ký tự xuống dòng do người dùng cung cấp có thể làm log text khó parse hoặc giả mạo nhiều dòng nếu không được escape/encode phù hợp.

## 28. File log khác audit event và dữ liệu nghiệp vụ

Log là phương tiện quan sát hành vi hệ thống, không nên là nguồn duy nhất cho dữ liệu quan trọng cần tái tạo chắc chắn.

Ví dụ nghiệp vụ thanh toán:

```java
log.info("Payment {} confirmed", paymentId);
```

Dòng log không tự đảm bảo:

- Giao dịch database được commit thành công.
- Sự kiện thanh toán đã được gửi tới hệ thống downstream.
- Log đã được flush và lưu bền vững.
- Log không bị xóa bởi retention.
- Nhiều instance không ghi trùng.

Nếu hệ thống yêu cầu bằng chứng audit hoặc event processing với semantics rõ ràng, hãy thiết kế event/audit storage có transaction, định danh, retention và truy cập riêng; logging phục vụ quan sát và chẩn đoán bổ sung.

## 29. Chiến lược vận hành: chọn console hay file?

| Tình huống | Lựa chọn thường phù hợp | Cần quản lý thêm |
|---|---|---|
| Developer chạy local | Console | Level, format dễ đọc |
| Batch nhỏ trên VM | Console hoặc file | Exit status, retention |
| Spring Boot service trên VM có log agent đọc file | File rolling | Permission, rolling, retention, disk monitoring |
| Container/Kubernetes có log collector | Console | Runtime rotation, aggregation, retention |
| Legacy server không có collector stdout | File rolling | Backup/rotation/cleanup ngoài ứng dụng nếu cần |
| Hệ thống cần audit lâu dài | Logging + audit storage riêng | Security, immutability/retention theo yêu cầu |
| Nhiều replicas auto-scale | Console hoặc file riêng từng instance | Instance metadata, collector, tránh shared file |

Không có lựa chọn tuyệt đối cho mọi hệ thống. Quyết định dựa trên:

- Ứng dụng được chạy ở đâu.
- Nền tảng thu thập log bằng cách nào.
- Cần xem log trong bao lâu.
- Số lượng process/replicas.
- Khối lượng log và tài nguyên disk.
- Quy định bảo mật và vận hành.

## 30. Quy trình cấu hình một dịch vụ Spring Boot ghi file an toàn hơn

Ví dụ service chạy trên VM có một process, muốn lưu rolling files trong thư mục riêng.

### Bước 1 — Chọn thư mục và tên file

```properties
logging.file.name=/var/log/orders/orders.log
```

Đảm bảo service user có quyền ghi.

### Bước 2 — Chọn level

```properties
logging.level.root=INFO
logging.level.com.example.orders=INFO
logging.level.org.springframework=WARN
```

Không bật DEBUG toàn hệ thống như cấu hình thường trực nếu không có lý do.

### Bước 3 — Đặt rolling và retention

```properties
logging.logback.rollingpolicy.file-name-pattern=/var/log/orders/orders.%d{yyyy-MM-dd}.%i.log.gz
logging.logback.rollingpolicy.max-file-size=20MB
logging.logback.rollingpolicy.max-history=14
logging.logback.rollingpolicy.total-size-cap=1GB
logging.logback.rollingpolicy.clean-history-on-start=true
```

Các property này giả định Spring Boot/Logback version hỗ trợ chúng.

### Bước 4 — Quan sát hoạt động

- Xác nhận file active được tạo.
- Xác nhận log thực sự có nội dung.
- Xác nhận appender không báo lỗi permission/path.
- Quan sát khi file đạt ngưỡng rollover.
- Kiểm tra archive filename và compression.
- Kiểm tra retention khi có đủ dữ liệu và chu kỳ.
- Kiểm tra disk usage thực tế.

### Bước 5 — Gắn hệ thống thu gom nếu cần

Nếu đội vận hành cần truy vấn log qua nhiều máy, thiết lập collector có trạng thái đọc file phù hợp, tránh đọc trùng sau rollover.

### Bước 6 — Định nghĩa trách nhiệm

Ghi rõ:

- Ai cấu hình file appender.
- Ai chịu trách nhiệm rotation.
- Ai giám sát disk.
- Ai sở hữu retention của backend tập trung.
- Ai có quyền đọc/xóa.
- Log nào không được chứa thông tin nhạy cảm.

Nếu không xác định trách nhiệm, rất dễ rơi vào tình trạng có file log nhưng không ai kiểm soát dung lượng hay vòng đời của nó.

## 31. Kiểm tra log file khi ứng dụng hoạt động

### 31.1. Quan sát log hiện tại

Trên Unix-like system:

```bash
tail -f ./logs/orders.log
```

Lệnh này bám theo file active tại đường dẫn đang có. Sau rotation, hành vi theo dõi tên file hoặc inode có thể khác giữa công cụ và option; cần chọn chế độ phù hợp khi muốn theo dõi file mới.

### 31.2. Kiểm tra archives

```bash
ls -lh ./logs
du -sh ./logs
```

Quan sát:

- Bao nhiêu file archive đang tồn tại.
- Tên file có đúng ngày và index.
- Dung lượng file active và archives.
- Compression có được áp dụng.
- Có file nào phát triển quá mức dự kiến.

### 31.3. Kiểm tra hiệu ứng của log level

Chạy với:

```bash
java -jar app.jar --logging.level.com.example.orders=DEBUG
```

Sau đó quan sát console/file. Sự kiện DEBUG chỉ xuất hiện nếu logger và appender/filter configuration cho phép.

### 31.4. Kiểm tra restart

Khởi động lại ứng dụng trong môi trường test thích hợp. Xác nhận log có còn được ghi vào đúng nơi và rolling policy không xóa mất những file cần giữ.

Không nên kiểm tra bằng cách cố tình làm đầy đĩa production. Hãy sử dụng môi trường thử nghiệm và ngưỡng nhỏ phù hợp.

## 32. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Console có log, nhưng không có file | Chưa bật file logging hoặc custom config không có file appender | Kiểm tra `logging.file.name`/`path` và logging config |
| File xuất hiện ở thư mục lạ | Dùng relative path với working directory khác dự kiến | Xem working directory, dùng absolute path khi cần |
| Permission denied | Service user không được ghi vào log directory | Sửa quyền/owner/mount phù hợp |
| File không thể tạo | Thư mục không tồn tại, filesystem read-only hoặc thiếu disk | Kiểm tra path và storage |
| Chỉ có file rất lớn | Chưa bật/đang ghi đè rolling policy hoặc policy không hoạt động | Kiểm tra active appender, cấu hình version và rollover conditions |
| Archives không bị xóa ngay sau nửa đêm | Cleanup có thể diễn ra tại rollover/startup | Kiểm tra policy trigger và `clean-history-on-start` |
| `total-size-cap` đã đặt nhưng disk vẫn đầy | Cap chỉ quản lý archives trong scope của policy; còn active file và dữ liệu khác | Theo dõi disk/quota, giảm log volume |
| Log bị tách giữa nhiều file bất ngờ | Có size-and-time rolling, nhiều chỉ số trong một ngày | Đọc filename pattern và threshold |
| Log trùng ở console và file | Hai appender cùng nhận event | Đây có thể là behavior chủ đích; sửa cấu hình nếu không mong muốn |
| Log biến mất sau redeploy container | Container filesystem không bền vững | Thu thập stdout hoặc dùng persistent volume có kế hoạch |
| `kubectl logs` không thấy file log | Runtime log stream khác file do ứng dụng tạo | Thiết lập collector cho file hoặc ghi console |
| File bị đổi tên nhưng process vẫn ghi | External rotation không phối hợp file handle | Tránh dual rotation, kiểm thử reopen/copytruncate |
| Log nhiều instance bị lẫn | Nhiều process ghi cùng shared file | Dùng console/collector hoặc file riêng |
| Một số dòng cuối mất khi crash | Buffer hoặc async queue chưa flush | Thiết kế flush/shutdown/aggregation phù hợp |
| DEBUG không xuất hiện | Effective logger level/filter loại DEBUG | Kiểm tra level của logger và appender |
| Logback property không có tác dụng | Dùng backend khác, version khác hoặc custom XML không tham chiếu property | Đối chiếu backend/config thực tế |
| Log có thông tin mật | Ứng dụng ghi raw headers/payload/exception | Redact dữ liệu và giới hạn truy cập |
| File không được xóa dù vượt retention | Archive nằm ngoài pattern hoặc không được policy quản lý | Kiểm tra filename pattern, trigger và quyền xóa |

## 33. Những điểm dễ nhầm về vòng đời file

### 33.1. “Tôi bật logging.file.name nên đã có rotation đầy đủ”

Chưa chắc. Property này yêu cầu file logging. Rolling cụ thể phụ thuộc backend, Boot version và cấu hình đang có. Hãy xác nhận rolling policy và các giới hạn thật sự được sử dụng.

### 33.2. “Tôi đặt max-history=7 nên chỉ còn bảy file”

Sai trong trường hợp pattern theo ngày có nhiều archive mỗi ngày. `max-history` điều khiển số chu kỳ lịch sử, không nhất thiết số lượng file đơn lẻ.

### 33.3. “Tôi đặt total-size-cap=1GB nên không thể đầy đĩa”

Không đúng. Active log file, temp/compression files, logs ngoài scope và các ứng dụng khác vẫn chiếm disk. Cleanup cũng không nhất thiết tức thời.

### 33.4. “Logback đã rotation nên logrotate cũng nên rotation cùng file”

Không nên tự động kết hợp hai cơ chế quản lý cùng một file. Chúng có thể tranh chấp và gây mất/trùng log nếu không phối hợp file handles.

### 33.5. “Log nằm trong container nên redeploy vẫn còn”

Không được bảo đảm. Container filesystem có vòng đời riêng. Nếu cần lưu lâu, phải có volume hoặc log aggregation.

### 33.6. “Có file log nghĩa là đã có audit trail đáng tin cậy”

Log có thể bị xóa, ghi đè, mất lúc crash hoặc không đồng bộ với transaction. Yêu cầu audit bền vững cần kiến trúc và chính sách khác.

### 33.7. “Tắt console khi bật file luôn tốt hơn”

Không nhất thiết. Nền tảng có thể chỉ thu thập stdout/stderr; khi tắt console, hệ thống giám sát có thể không còn nhận log. Đầu ra nào cần bật phải dựa trên pipeline thu thập thực tế.

## 34. Bài tập thực hành

### Bài tập A — Console và logging level

Tạo một `OrderService` ghi DEBUG, INFO, WARN và ERROR. Chạy Spring Boot với level INFO, sau đó đổi package ứng dụng sang DEBUG. Ghi lại sự khác nhau của console output.

### Bài tập B — Ghi file theo đường dẫn

Đặt:

```properties
logging.file.name=./logs/orders.log
```

Khởi động ứng dụng và tạo vài log events. Kiểm tra file được tạo ở đâu, có phụ thuộc working directory không.

### Bài tập C — So sánh name và path

Thử lần lượt `logging.file.name=./logs/custom.log` và `logging.file.path=./logs`. Ghi nhận tên file được sinh ra. Sau đó đặt cả hai và xác định property ưu tiên.

### Bài tập D — Rolling theo size và thời gian

Cấu hình thử:

```properties
logging.logback.rollingpolicy.file-name-pattern=./logs/orders.%d{yyyy-MM-dd}.%i.log.gz
logging.logback.rollingpolicy.max-file-size=1MB
logging.logback.rollingpolicy.max-history=3
logging.logback.rollingpolicy.total-size-cap=10MB
```

Chỉ dùng trong môi trường thử nghiệm. Tạo lượng log đủ để kích hoạt rollover, quan sát filename và archive compression. Giải thích vì sao `max-history=3` không có nghĩa tối đa ba file trong mọi trường hợp.

### Bài tập E — Kiểm tra retention trigger

Quan sát file archive khi ứng dụng không ghi log trong một thời gian. So sánh với lúc một log event mới kích hoạt rollover và với behavior khi bật `clean-history-on-start`.

### Bài tập F — File vs stdout redirect

Chạy một ứng dụng với file appender và so sánh với shell redirect console ra file. Kiểm tra nơi `System.out.println` xuất hiện và liệu file do redirect có chịu rolling policy của Logback hay không.

### Bài tập G — Container

Triển khai thử ứng dụng ghi console và ứng dụng ghi file trong container. Kiểm tra log nào xem được qua runtime log command, log nào nằm trong filesystem của container và điều gì xảy ra sau khi container bị tạo lại.

### Bài tập H — Nhiều replicas

Giả lập hai process ghi cùng một log file rồi đánh giá rủi ro khi rotation. Thiết kế lại bằng file riêng hoặc console aggregation.

### Bài tập I — Disk budget

Giả sử ứng dụng tạo trung bình 300 MB log/ngày, tăng gấp bốn lần trong giờ cao điểm. Đề xuất max-file-size, max-history, total-size-cap và disk free alert có headroom phù hợp. Phân biệt size cap của archive với quota filesystem.

### Bài tập J — An toàn dữ liệu

Xem một đoạn log có email, bearer token và request body. Xác định dữ liệu nào phải redaction. Giải thích vì sao giảm max-history không thay thế việc ngăn ghi secret từ đầu.

## 35. Ghi nhớ

1. **Console logging** là điểm bắt đầu đơn giản và rất phù hợp với ứng dụng chạy trong container có log collector.
2. **File logging** yêu cầu đường dẫn, quyền ghi và cơ chế quản lý storage.
3. `logging.file.name` chỉ định file log; `logging.file.path` chỉ định thư mục dùng cho tên file mặc định. Khi cùng có cả hai, `name` thường ưu tiên.
4. Ghi file không nhất thiết tắt console. Một sự kiện có thể được gửi tới nhiều appender.
5. SLF4J logger khác `System.out.println`: logger đi qua levels, patterns và appenders.
6. **Rotation** tạo file archive mới; **retention** dọn lịch sử. Hai khái niệm khác nhau.
7. Với Logback, các property `logging.logback.rollingpolicy.*` có thể điều chỉnh pattern, max-file-size, max-history, total-size-cap và cleanup-on-start trong các phiên bản hỗ trợ.
8. `max-history` thường đếm chu kỳ theo date pattern, không phải tổng số file tuyệt đối.
9. `total-size-cap` không phải hard disk quota và không đảm bảo toàn filesystem không thể đầy.
10. Retention cleanup có thể chỉ diễn ra tại rollover/startup; không nên suy ra việc xóa tức thời chỉ từ ngày trên đồng hồ.
11. Tránh để Logback rolling và công cụ external rotation cùng thao tác một file thiếu phối hợp.
12. Nhiều process/replicas không nên cạnh tranh một shared active log file trừ khi đã có thiết kế multi-process logging an toàn.
13. File trong container có thể mất sau khi container bị thay thế; stdout aggregation hoặc volume/collector là quyết định hạ tầng.
14. Shutdown không sạch có thể làm mất log chưa flush, đặc biệt khi dùng async appender.
15. Quản lý level và log volume giúp giảm disk I/O, archive churn và chi phí thu gom.
16. Không log secrets hoặc dữ liệu nhạy cảm; kiểm soát access, retention và deletion ở cả file local lẫn hệ thống tập trung.
17. Log quan sát không thay thế audit/event storage với yêu cầu bền vững và transaction consistency.
18. Nếu custom `logback-spring.xml`, cần hiểu appender và policy do chính XML điều khiển; không giả định mọi property mặc định của Boot đều còn hiệu lực.
19. Hãy kiểm tra behavior trên đúng Spring Boot version, backend và môi trường triển khai thực tế, thay vì chỉ dựa vào tên property.
20. Cuối cùng, cần có ownership rõ ràng cho file rotation, disk monitoring, log aggregation và chính sách lưu trữ.

**Tư duy cốt lõi:** log console và log file là hai **đích xuất sự kiện**, còn vòng đời file là một **bài toán vận hành** gồm rotation, retention, storage, collector và bảo mật. Spring Boot và logging backend có thể giúp quản lý một phần vòng đời, nhưng không tự thay thế hệ thống quản trị log đầy đủ của môi trường triển khai.
