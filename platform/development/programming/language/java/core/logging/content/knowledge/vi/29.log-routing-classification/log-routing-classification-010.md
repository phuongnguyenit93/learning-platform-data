# Kiểm tra routing trong Java Core Logging

## Mục tiêu

Bài học thuộc nhóm **Routing và phân loại**, với chủ đề chính **Kiểm tra routing**. Sau bài này, bạn có thể đọc một cấu hình logging để dự đoán event nào đi đến appender/sink nào, thiết kế bảng ca kiểm thử routing có cả trường hợp nên nhận và không được nhận, viết một chương trình Java 17 tự kiểm tra tuyến log, và xác minh đường đi từ ứng dụng đến log collector hoặc hệ thống tìm kiếm.

**Routing** là quyết định đưa một log event vào một hay nhiều đích xử lý dựa trên thuộc tính như logger name, level, marker, event type hoặc context. Ví dụ: log nghiệp vụ thông thường ra stdout, lỗi ứng dụng vào file lỗi, sự kiện audit vào audit sink. **Kiểm tra routing** là chứng minh các quy tắc đó hoạt động đúng, kể cả lúc thiếu context, chạy đa luồng, overload hoặc gặp lỗi sink.

Một routing test hoàn chỉnh phải có **khẳng định dương** (đúng event xuất hiện ở đúng nơi) và **khẳng định âm** (event không xuất hiện ở nơi không được phép). Chỉ thấy một dòng log trong console chưa đủ kết luận toàn bộ routing đúng.

## 1. Hiểu những tầng quyết định đường đi của log

Một hệ thống Java điển hình có nhiều điểm ảnh hưởng đến kết quả:

```text
Application / library log call
          |
          v
Logger isEnabled / effective level
          |
          v
Logger filter, event creation, context capture
          |
          v
Appender references + additivity / routing rules
          |
          +----> Console appender ----> container stdout ----> log agent ----+
          |                                                                |
          +----> File appender ------> file/rotation -----> file shipper ---+--> collector --> parser/index --> search
          |                                                                |
          +----> Audit appender -----> audit destination -------------------+
          |
          +----> Async queue/worker (nếu được cấu hình ở tuyến phù hợp)
```

Đây là sơ đồ khái niệm, không khẳng định mọi logging framework xử lý theo đúng một thứ tự vật lý. Trong một số cấu hình, filtering diễn ra trước khi tạo event; trong cấu hình khác, filter gắn với appender hoặc queue. Khi debug phải dựa trên framework và cấu hình **đang chạy thật**, không chỉ file XML/YAML trông đúng.

Các khái niệm quan trọng:

| Thành phần | Chức năng | Điều cần kiểm tra |
| --- | --- | --- |
| **Logger** | Điểm ứng dụng gọi ghi log, thường có tên theo class/package | Logger name và effective level có đúng không? |
| **Log level** | Quyết định sự kiện mức nào được xét tiếp | `DEBUG` có bị loại tại nguồn? `WARN`/`ERROR` có được giữ? |
| **Filter** | Chấp nhận, bỏ hoặc tiếp tục xét một event theo điều kiện | Rule nằm ở logger, appender hay collector? Có loại nhầm event không? |
| **Appender/Handler** | Ghi event vào console, file, network hoặc đích khác | Event có tới đúng sink và được encode thành công không? |
| **Additivity / parent handlers** | Cho phép event tiếp tục lên logger cha/root | Có gây trùng event hoặc đưa log nhạy cảm sai tuyến không? |
| **Routing key** | Level, logger, marker, MDC/ThreadContext hoặc event code được dùng để chọn đường | Key lấy từ nguồn đáng tin? Có fallback khi thiếu hoặc sai không? |
| **Async queue** | Tách producer khỏi writer | Enqueue thành công có bị hiểu nhầm là log đã tới đích không? |
| **Collector / index** | Nhận, xử lý, lưu và cho phép truy vấn log | Đã vào appender nhưng bị bỏ ở pipeline phía sau không? |

**Routing khác filtering:** routing chọn đích; filtering quyết định event có được tiếp tục trong một tuyến hay không. Một event có thể được **fan-out** đến hai sink một cách có chủ đích; một event khác chỉ nên xuất hiện ở một sink duy nhất. Mọi kiểm thử phải biết rõ trường hợp nào là độc quyền (*exclusive route*), trường hợp nào là một-nhiều (*fan-out*).

## 2. Viết quy tắc routing rõ ràng trước khi kiểm thử

Ví dụ một dịch vụ checkout có ba tuyến:

- **CONSOLE**: log ứng dụng mức `INFO` hoặc `WARN` để agent của container thu thập.
- **ERROR_FILE**: log ứng dụng mức `ERROR` để phục vụ điều tra.
- **AUDIT**: log từ logger `com.example.audit` đến đích audit chuyên biệt, không đi qua appender ứng dụng mặc định.

Ở đây chúng ta **cố ý thiết kế mỗi event chỉ đi một tuyến**. Đây là một chính sách minh họa, không phải cách bắt buộc của mọi hệ thống. Một hệ thống khác có thể muốn ghi `ERROR` ra cả console lẫn file hoặc đưa audit event tới thêm security pipeline.

Dựa trên chính sách trên, tạo ma trận kỳ vọng:

| ID | Logger nguồn | Level | Event code | CONSOLE | ERROR_FILE | AUDIT |
| --- | --- | --- | --- | :---: | :---: | :---: |
| R1 | `com.example.checkout.OrderService` | `DEBUG` | `cache.detail` | Không | Không | Không |
| R2 | `com.example.checkout.OrderService` | `INFO` | `order.created` | Có | Không | Không |
| R3 | `com.example.checkout.PaymentClient` | `WARN` | `payment.retry` | Có | Không | Không |
| R4 | `com.example.checkout.PaymentClient` | `ERROR` | `payment.failed` | Không | Có | Không |
| R5 | `com.example.audit.AccessAudit` | `INFO` | `role.changed` | Không | Không | Có |
| R6 | `com.example.audit.AccessAudit` | `ERROR` | `access.denied` | Không | Không | Có |

Cần kiểm tra đồng thời:

1. **Có mặt đúng nơi:** ví dụ R4 có đúng một bản ghi ở ERROR_FILE.
2. **Vắng mặt đúng nơi:** R4 không được lặp ở CONSOLE, R5 không lẫn vào error log ứng dụng.
3. **Số lần:** routing độc quyền kỳ vọng mỗi event được lưu một lần ở đúng tuyến, còn R1 kỳ vọng 0. Nếu chủ động fan-out, số bản sao kỳ vọng có thể lớn hơn 1.
4. **Nội dung:** mức log, event code, timestamp, service, environment, trace ID hoặc audit context không bị mất hoặc biến dạng.
5. **Thời gian:** nếu async hoặc collector/index, log có thể đến sau; test dùng thời hạn chờ rõ ràng thay vì kiểm tra ngay tức thì rồi kết luận lỗi.

Đừng xem log level là cách phân biệt audit duy nhất. Một event audit có thể ở `INFO` hoặc `ERROR` nhưng vẫn phải vào đường audit theo luật phân loại. Nếu event pháp lý cần độ bền riêng, cần đích và cơ chế lưu trữ đáp ứng yêu cầu đó; file hoặc async queue trong RAM không tự bảo đảm audit durability.

## 3. Cách định danh một event để kiểm thử

Để tránh nhầm log của các lượt chạy đồng thời, mỗi event kiểm thử nên có **mã duy nhất** do test tạo, ví dụ `test_event_id=route-test-20261110-7b2c`. Dùng cùng một mã trong event ở nguồn và trong truy vấn sink.

Cần phân biệt:

- `test_event_id`: phân biệt **một** sự kiện test cụ thể; dùng để đếm số lần xuất hiện.
- `trace_id`: gộp nhiều span/log liên quan của **cùng trace**; không phải mã duy nhất cho từng log event.
- `request_id`: có thể gom log của một request; một request có nhiều event.
- `event_code`: phân loại loại sự kiện, ví dụ `payment.failed`; hàng nghìn event có thể cùng code.

Ví dụ log JSON minh họa để so sánh sau routing:

```json
{
  "timestamp": "2026-11-10T02:00:00.000Z",
  "level": "ERROR",
  "service": "checkout",
  "environment": "staging",
  "logger": "com.example.checkout.PaymentClient",
  "event": "payment.failed",
  "test_event_id": "route-test-20261110-7b2c",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Các giá trị trong JSON là **minh họa**, không phải output mặc định của Java. Nếu production sử dụng schema `event.code` hay `service.name`, hãy dùng đúng tên trường đó trong kiểm thử. Một bài test với mã event duy nhất còn giúp tìm bản sao bất thường khi hai appender cùng đẩy về một index.

**Đừng dùng dữ liệu khách hàng hoặc secret thật làm payload thử nghiệm.** Với bài test phân tuyến nhạy cảm, dùng event giả không có PII nhưng vẫn đủ các field để chứng minh chính sách.

## 4. Bốn loại kiểm thử routing phải có

### 4.1. Unit test cho điều kiện quyết định tuyến

Đưa chính sách routing vào một lớp/hàm có đầu vào rõ: logger, level, event code, marker và context. Đầu ra có thể là tập route cho phép, ví dụ `{CONSOLE}`, `{ERROR_FILE}` hoặc `{AUDIT}`.

Các trường hợp phải bao gồm **biên** của rule: `DEBUG` ngay dưới mức nhận, `INFO` tại ngưỡng; `ERROR` thay vì `WARN`; audit logger và ứng dụng logger có tên gần giống; key routing rỗng, unknown hoặc có ký tự lạ. Một test chỉ gửi sự kiện đúng điều kiện “happy path” chưa đủ.

Không tự suy ra rằng việc route = AUDIT đồng nghĩa event chắc chắn đã được lưu bền vững. Unit test chỉ chứng minh hàm quyết định tuyến.

### 4.2. Test thực tế của logging framework

Khởi tạo cấu hình Logback/Log4j 2/JUL tương ứng trong test và gắn appender/handler có thể kiểm soát, chẳng hạn buffer trong bộ nhớ. Phát các event của ma trận R1–R6, kiểm tra **chính xác các danh sách nhận** và không có bản sao ngoài ý muốn. Với Logback, có thể dùng `ListAppender` để chụp `ILoggingEvent` trong test có dependency framework; với JUL có thể tạo `Handler` riêng như ví dụ chạy bên dưới.

Chú ý kiểm tra **logger hierarchy**, root level, appender references, filter và additivity. Một hàm phân tuyến riêng có thể đúng nhưng cấu hình framework vẫn route sai do rule bị override hoặc sự kiện đi tiếp lên root logger.

### 4.3. Integration test qua sink thật

Test qua console/file hoặc collector staging để phát hiện vấn đề mà in-memory test không thấy: quyền ghi file, đường dẫn mount, JSON encoder, rotate/rolling policy, lỗi network, timeout, buffering, sidecar/agent và config map. Với file appender, kiểm tra sự kiện tới đúng file và không xuất ở file khác; dùng tên file riêng cho test hoặc cleanup đúng phạm vi để tránh đụng log đang vận hành.

### 4.4. End-to-end test trên log backend

Sau khi phát event có `test_event_id`, tìm ở **đúng index/namespace/tên nguồn** và khoảng thời gian. Với pipeline async/indexing, truy vấn lặp có giới hạn thời gian (polling có timeout và khoảng nghỉ hợp lý). Chứng minh event có tại sink không có nghĩa nó đã tới backend; cần xác minh thêm parser, transport, routing rule ở collector, retention và quyền truy cập.

Với audit/security, còn cần kiểm tra ai **không được đọc** log đó, không chỉ nơi lưu. Một bản ghi audit xuất ở sink đúng nhưng bị sao chép sang console công khai vẫn vi phạm chính sách.

## 5. Java 17 chạy độc lập: tự kiểm tra phân tuyến log

Ví dụ này dùng **JDK 17+**, không cần SLF4J, Logback hay Spring Boot. Nó định nghĩa ba `Handler` như ba sink giả lập trong bộ nhớ:

- `console` nhận `INFO` và `WARNING` của logger ứng dụng.
- `error` nhận `SEVERE` của logger ứng dụng.
- `audit` nhận mọi mức của logger audit được cấu hình ở ví dụ.

JUL sử dụng `WARNING` và `SEVERE` thay cho tên `WARN`/`ERROR` thường thấy trong SLF4J. Các Handler ở đây chỉ **thu danh sách event** để kiểm tra và in ra sau khi đã phát xong, nên thứ tự và stdout xác định. Ví dụ kiểm tra cả event bị loại bởi level (`FINE`) và event audit không đi nhầm sang appender ứng dụng.

Tạo file **`RoutingCheckDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RoutingCheckDemo {
    private static final class RouteHandler extends Handler {
        private final String route;
        private final Predicate<LogRecord> condition;
        private final List<String> events = new ArrayList<>();

        RouteHandler(String route, Predicate<LogRecord> condition) {
            this.route = route;
            this.condition = condition;
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record) || !condition.test(record)) {
                return;
            }
            events.add("route=" + route
                    + " level=" + record.getLevel().getName()
                    + " event=" + record.getMessage());
        }

        @Override
        public void flush() {
        }

        @Override
        public void close() {
        }

        List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    private static void expect(String name,
                               List<String> actual,
                               List<String> expected) {
        if (!actual.equals(expected)) {
            throw new IllegalStateException(name
                    + " expected=" + expected + " actual=" + actual);
        }
    }

    public static void main(String[] args) {
        Logger application = Logger.getLogger("demo.routing.application");
        Logger audit = Logger.getLogger("demo.routing.audit");

        application.setUseParentHandlers(false);
        audit.setUseParentHandlers(false);
        application.setLevel(Level.INFO);
        audit.setLevel(Level.ALL);

        RouteHandler console = new RouteHandler("console",
                record -> record.getLevel().intValue()
                        >= Level.INFO.intValue()
                        && record.getLevel().intValue()
                        < Level.SEVERE.intValue());
        RouteHandler error = new RouteHandler("error",
                record -> record.getLevel().intValue()
                        >= Level.SEVERE.intValue());
        RouteHandler auditRoute = new RouteHandler("audit",
                record -> true);

        application.addHandler(console);
        application.addHandler(error);
        audit.addHandler(auditRoute);

        try {
            application.fine("query-detail");
            application.info("request-ok");
            application.warning("retry-scheduled");
            application.severe("payment-failed");
            audit.info("permission-changed");
            audit.severe("access-denied");

            expect("console", console.snapshot(), List.of(
                    "route=console level=INFO event=request-ok",
                    "route=console level=WARNING event=retry-scheduled"));
            expect("error", error.snapshot(), List.of(
                    "route=error level=SEVERE event=payment-failed"));
            expect("audit", auditRoute.snapshot(), List.of(
                    "route=audit level=INFO event=permission-changed",
                    "route=audit level=SEVERE event=access-denied"));

            if (application.isLoggable(Level.FINE)) {
                throw new IllegalStateException("FINE must be disabled");
            }

            console.snapshot().forEach(System.out::println);
            error.snapshot().forEach(System.out::println);
            auditRoute.snapshot().forEach(System.out::println);

            System.out.println("console_count=" + console.snapshot().size());
            System.out.println("error_count=" + error.snapshot().size());
            System.out.println("audit_count=" + auditRoute.snapshot().size());
            System.out.println("fine_enabled="
                    + application.isLoggable(Level.FINE));
            System.out.println("routing_test=PASS");
        } finally {
            application.removeHandler(console);
            application.removeHandler(error);
            audit.removeHandler(auditRoute);
            console.close();
            error.close();
            auditRoute.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac RoutingCheckDemo.java
java RoutingCheckDemo
```

**stdout chính xác** của chương trình:

```text
route=console level=INFO event=request-ok
route=console level=WARNING event=retry-scheduled
route=error level=SEVERE event=payment-failed
route=audit level=INFO event=permission-changed
route=audit level=SEVERE event=access-denied
console_count=2
error_count=1
audit_count=2
fine_enabled=false
routing_test=PASS
```

Vì sao kết quả có tính xác định?

1. `application.setLevel(Level.INFO)` khiến `FINE query-detail` bị loại từ logger trước khi tới Handler.
2. `console` kiểm tra level từ `INFO` đến thấp hơn `SEVERE`; `error` chỉ chấp nhận từ `SEVERE` trở lên. Hai điều kiện không chồng lấn với các event đã phát.
3. Logger audit có Handler riêng, không gắn console/error handlers. `setUseParentHandlers(false)` ngăn event đi tiếp tới handler của parent/root và gây trùng hoặc route khác ngoài dự kiến.
4. `expect` so sánh **cả nội dung và số lượng** mỗi danh sách; chỉ khi không có sai khác mới in `routing_test=PASS`.
5. Các lời gọi được thực hiện tuần tự trong một thread, và Handler chỉ ghi vào bộ nhớ. Trong một hệ thống async hoặc nhiều thread, cần cơ chế đồng bộ dữ liệu test và chờ drain; không giả định thứ tự sink luôn giống thứ tự phát.

**Thí nghiệm:** thay điều kiện của `console` thành `record -> true` và chạy lại. Event `payment-failed` sẽ xuất trong cả danh sách console và error; phép `expect("console",...)` sẽ ném `IllegalStateException`. Đây là một **regression test cho routing độc quyền**, phát hiện bản sao sai tuyến thay vì chỉ khẳng định bản ghi lỗi có tồn tại ở file lỗi.

Một thay đổi khác là bỏ `application.setUseParentHandlers(false)`: ứng dụng có thể thêm output từ parent/root handlers tùy cấu hình JUL của runtime. Vì chương trình trên kiểm tra bằng Handler nội bộ, nó không tự phát hiện mọi bản sao từ handler ngoài; muốn kiểm thử đường thực tế phải quan sát cả stdout/file và những appender/handlers khác trong môi trường test.

## 6. Kiểm tra routing với SLF4J + Logback

Một ứng dụng dùng SLF4J và Logback có thể route theo **logger name** và **level**, sử dụng appender và filter. Ví dụ bên dưới là **logback.xml** minh họa ba tuyến như ma trận R1–R6; cần thư viện SLF4J/Logback tương thích trên classpath. Các file `logs/application-error.log` và `logs/audit.log` phải nằm ở nơi process được quyền ghi.

```xml
<configuration>
    <appender name="APP_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>DENY</onMatch>
            <onMismatch>NEUTRAL</onMismatch>
        </filter>
        <encoder>
            <pattern>%d{ISO8601} %-5level logger=%logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="APP_ERROR"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/application-error.log</file>
        <append>true</append>
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>ERROR</level>
        </filter>
        <encoder>
            <pattern>%d{ISO8601} %-5level logger=%logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="AUDIT_FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/audit.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level logger=%logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.audit"
            level="INFO" additivity="false">
        <appender-ref ref="AUDIT_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="APP_CONSOLE"/>
        <appender-ref ref="APP_ERROR"/>
    </root>
</configuration>
```

Đọc cấu hình theo hai nhóm:

- Logger ứng dụng thừa kế `root=INFO`: `DEBUG` bị loại; `INFO`/`WARN` vào APP_CONSOLE vì filter console chỉ `DENY` chính xác `ERROR`; `ERROR` vào APP_ERROR qua `ThresholdFilter`, bị console từ chối.
- Logger `com.example.audit` và logger con thừa kế rule riêng, level `INFO`, `additivity=false`: event không tiếp tục lên root nên chỉ tới AUDIT_FILE trong cấu hình này. `ERROR` của audit cũng chỉ vào audit file, **không tự xuất ở application-error.log**.
- Khi muốn audit event **cũng** có mặt ở error file, cần đặt chủ đích fan-out đúng phạm vi, sửa bảng kỳ vọng và kiểm tra quyền truy cập của mỗi sink. Không bật additivity mù để thay thế thiết kế tuyến rõ ràng.

**Test cấu hình Logback thực tế:**

1. Khởi chạy test với chính backend/cấu hình dự định; xác minh file config được nạp, không bị override bởi `logging.config`, environment profile hoặc dependency backend khác.
2. Gọi logger `com.example.checkout.OrderService` với `DEBUG`, `INFO`, `WARN` và `ERROR`; gắn mỗi event với mã test riêng.
3. Gọi `com.example.audit.AccessAudit` với `INFO` và `ERROR`.
4. Đếm event trong console, `application-error.log` và `audit.log`; đối chiếu ma trận R1–R6, gồm kiểm tra **không có ở sink sai**.
5. Kiểm tra số dòng trùng khi parent/additivity và appender refs thay đổi. Nếu file đã chứa log cũ, dùng bộ lọc theo test_event_id hoặc file riêng của lượt thử.
6. Khi production dùng JSON encoder, kiểm tra field parsing và index mapping; ví dụ XML chỉ dùng text pattern để minh họa routing.

Trong test tự động có dependency Logback, `ch.qos.logback.core.read.ListAppender` có thể thu event từ appender để assertion, nhưng nó chỉ chứng minh event đã qua một tuyến của Logback. Muốn kiểm tra file, stdout hoặc collector phải có integration/end-to-end test bổ sung. Với Logback, regular appender filter trả `DENY`/`NEUTRAL`/`ACCEPT`; `ACCEPT` ở một filter không vượt qua mọi filter tại các tầng khác.

### Khi routing không phụ thuộc hoàn toàn vào level

Một service có thể route bằng marker, event type hoặc context như `MDC["log_route"]`. Ví dụ:

```text
if logger startsWith "com.example.audit":
    route = AUDIT
else if level >= ERROR:
    route = ERROR_FILE
else:
    route = CONSOLE
```

Đây là **pseudocode chính sách**, không phải cú pháp cấu hình Logback. Trật tự điều kiện quan trọng: nếu đặt nhánh `level >= ERROR` trước nhánh audit, một `ERROR` audit có thể đi sai tuyến. Nếu routing dựa vào MDC, hãy thử trường hợp context thiếu, context lỗi, chuyển thread và context cũ còn sót trong thread pool.

Logback có `SiftingAppender` để chọn appender dựa vào discriminator, chẳng hạn giá trị MDC. Cách này có thể tạo appender riêng cho từng giá trị route; phải giới hạn số route, đường dẫn file và vòng đời appender. Không lấy trực tiếp ID không tin cậy từ request làm một phần tên file/đích xuất vì có thể gây cardinality lớn, tạo quá nhiều file hoặc rò dữ liệu giữa nhóm người dùng. Với bài toán chỉ có ba tuyến cố định, logger name và appender filters thường dễ kiểm chứng hơn cấu hình dynamic route phức tạp.

## 7. Log4j 2: kiểm tra LoggerConfig, RoutingAppender và filter

Log4j 2 có các tầng như logger, `LoggerConfig`, `AppenderRef` và appender. Filter có thể trả `ACCEPT`, `DENY` hoặc `NEUTRAL` và hiệu lực phụ thuộc giai đoạn. Một event bị `DENY` ở tầng trước sẽ không tới những tuyến phía sau; `ACCEPT` ở một tầng không tự chứng minh mọi appender sẽ nhận event.

`RoutingAppender` là một lựa chọn khi phải chọn appender bằng một routing key. Một cấu trúc minh họa, trong dự án dùng đúng XML và plugin theo phiên bản Log4j 2 hiện hành:

```xml
<Routing name="Classified">
    <Routes pattern="$${ctx:log_route}">
        <Route key="audit" ref="AuditFile"/>
        <Route key="error" ref="ErrorFile"/>
        <Route ref="MainConsole"/>
    </Routes>
</Routing>
```

Đây là **đoạn cấu hình**, không phải `log4j2.xml` đầy đủ: nó cần các appender tên AuditFile, ErrorFile, MainConsole được định nghĩa, logger tham chiếu Classified, và dependency logging tương thích. Trong XML Log4j 2, `$${ctx:log_route}` là dạng tra lookup context theo event trong biểu thức Routes của ví dụ; cần xác nhận cú pháp interpolation theo phiên bản thực tế trước khi deploy.

Chính sách kiểm thử minh họa:

| `log_route` trong ThreadContext | Kỳ vọng |
| --- | --- |
| `audit` | Chỉ vào AuditFile |
| `error` | Chỉ vào ErrorFile |
| thiếu giá trị hoặc giá trị không match | Theo default route được cấu hình (ví dụ MainConsole) |
| ký tự lạ hoặc giá trị chưa duyệt | Không tạo sink tùy ý, áp dụng fallback có kiểm soát |

Cần kiểm tra cả effective logger level: nếu caller đã bị filter bởi level thì routing key đúng cũng không làm event xuất hiện. `ThreadContext` trong Log4j 2 thường gắn với execution context hiện hành; với executor/async propagation cần framework integration hoặc wrapper phù hợp. Dọn/khôi phục context trong `finally` để request sau không bị route nhầm.

Với routing động theo tenant/service, phải quan tâm đến số route tối đa, vòng đời appender, giới hạn bộ nhớ/file handles, permissions và giá trị default. Kiểm thử tải và security bên cạnh correctness; log của tenant A rơi vào sink tenant B nguy hiểm hơn việc một event thông thường bị lặp.

## 8. Routing theo MDC, marker và thông tin phân loại

MDC (Mapped Diagnostic Context) giúp gắn metadata vào event, ví dụ `trace_id`, `environment`, `tenant_group` hoặc `log_route`. **MDC không phải hệ thống phân quyền**, và giá trị của nó có thể đến từ input không đáng tin. Khi route dựa vào MDC:

1. Đặt giá trị qua lớp mapping/validation được kiểm soát, dùng tập route cho phép thay vì để client tự chọn tên sink.
2. Xác định cách xử lý khi key trống, null, sai giá trị hoặc không có trace.
3. Thử chuyển luồng `ExecutorService`/`CompletableFuture`: context không tự truyền trong mọi trường hợp.
4. Dọn và khôi phục MDC/ThreadContext khi request kết thúc, đặc biệt trong thread pool.
5. Kiểm tra async appender capture context vào event tại thời điểm đúng; log worker không được đọc nhầm MDC của thread xử lý nền.
6. Nếu routing thay đổi trên retry hoặc sau async boundary, cần test logic của từng trường hợp, không suy ra từ log ở thread chính.

**Marker** cho phép phân loại event có ý nghĩa ổn định, ví dụ `AUDIT`, `SECURITY`, `BUSINESS`. Marker hoặc event code thường tốt hơn parse substring từ message text. Tuy vậy, một marker tên AUDIT không tự biến event thành durable audit log; appender, sink và policy vẫn cần được chứng minh bằng kiểm thử.

Nếu yêu cầu routing theo `environment=staging` và `production`, hãy thử cả hai để tránh lẫn index. Một log đã được gắn `environment=staging` nhưng đưa tới production index vẫn là lỗi routing. Việc hiển thị đúng field và đường lưu đúng là hai assertion độc lập.

## 9. Additivity và nguyên nhân log trùng

Trong nhiều logging framework, logger theo tên có cấu trúc cha-con. Ví dụ `com.example.payment.Client` có ancestor `com.example.payment`, `com.example` và root. Nếu một logger con có appender riêng nhưng vẫn tiếp tục chuyển event lên cha, event có thể được ghi bởi **cả appender của con lẫn root**.

Với Logback:

```xml
<logger name="com.example.payment"
        level="INFO"
        additivity="false">
    <appender-ref ref="PAYMENT_FILE"/>
</logger>
```

Đây là một phần cấu hình; PAYMENT_FILE phải được định nghĩa trong cấu hình thật. Khi `additivity=false`, event không đi tiếp lên appenders của ancestor logger. Tuy nhiên, nếu cùng appender được tham chiếu nhiều lần ở những điểm khác, hoặc hệ thống collector nhận dữ liệu từ nhiều nguồn trùng nhau, vẫn có thể có bản sao ở pipeline. Trường hợp này cần kiểm tra theo test_event_id.

Với JUL, `Logger.setUseParentHandlers(false)` phục vụ mục đích chặn truyền event lên parent handlers. API và semantics cụ thể không giống hệt Logback, nên tránh copy tên thuộc tính giữa framework. Khi routing bị lặp, kiểm tra logger hierarchy, appender/handler refs, agent gom cả file và stdout, và collector nhận trùng luồng.

### Phân biệt trùng do chính sách và trùng ngoài ý muốn

Ví dụ `ERROR` tới cả stdout và file là **fan-out** hợp lệ nếu được chỉ định. Nếu cả stdout agent và file shipper gửi về cùng một index mà không có cách phân biệt, người vận hành có thể thấy hai bản ghi của cùng event. Test phải đếm và xác định điểm xuất hiện bản sao. Đừng xóa một bản ghi bằng dedup mù tại dashboard khi chưa rõ đường routing, vì có thể che một lỗi pipeline.

## 10. Kiểm tra bất đồng bộ và thất bại sink

Routing đúng ở điều kiện bình thường không bảo đảm đúng khi hệ thống bị quá tải:

- **Async logging:** Event có thể đã vào queue nhưng chưa tới sink khi lời gọi logger trả về. Test cần đợi worker drain hoặc chờ tối đa một thời hạn; so sánh event count khi kết thúc.
- **Queue đầy:** Tùy framework/chính sách, enqueue có thể block, drop, discard mức thấp hoặc fallback synchronous. Những event không đến sink do overflow phải được báo riêng với event bị filter chủ động.
- **File sink không ghi được:** Thiếu quyền, hết dung lượng, đường dẫn sai hoặc rotate lỗi. Xác định framework có báo error status, retry, fallback hay drop hay không.
- **Collector/network lỗi:** Event có thể tồn tại trong file hoặc stdout nhưng chưa tìm được trong backend. Test từng hop và xác nhận chính sách retry/buffer.
- **Shutdown:** Với async worker, graceful shutdown cần đủ ngân sách drain và flush. Process bị kill có thể mất event trong bộ nhớ ngay cả khi enqueue thành công.
- **Multiple instances:** Cùng test_event_id phải được gắn đúng service/instance; đồng hồ các máy có thể lệch và ingest có thể reorder log.

Nên thu các metric `route_selected_count`, `route_rejected_count`, `queue_dropped_count`, `sink_write_errors` và `collector_ingest_lag` nếu kiến trúc hỗ trợ. Định nghĩa rõ điểm đo: một số framework chỉ cung cấp số event appender nhận, không biết event bị loại ở logger từ trước. Không tự báo “100% delivery” chỉ từ event đã được xử lý thành công.

**Không dùng logger đang lỗi để lặp lại vô hạn một log báo lỗi ghi log.** Khi một sink thất bại, báo lỗi qua cơ chế status/internal diagnostics hoặc monitoring phù hợp, tránh recursive logging.

## 11. Kiểm tra routing end-to-end trong staging

Một kịch bản kiểm thử thực tế cần làm từ đầu đến cuối:

1. **Xác định topology:** service, logging backend, các appender, đường file/stdout, log agent, collector, namespace/index và quyền truy cập.
2. **Chụp cấu hình hiệu lực:** active profile, logger levels, filter chain, appender refs, additivity, routing keys và chính sách mặc định khi thiếu key.
3. **Phát test events:** dùng unique `test_run_id` và unique `test_event_id` cho từng trường hợp trong bảng. Ghi rõ expected routes và expected count.
4. **Kiểm tra tại JVM/sink:** appender test hoặc file/console có đúng event; dùng negative assertion để tìm event ở sai sink.
5. **Kiểm tra tại collector:** đối chiếu raw record, timestamp, field type, parser, labels và routing rules. Kiểm tra filter/transform nào có thể làm mất trường dùng để search.
6. **Kiểm tra index/search:** truy vấn đúng thời hạn, namespace, environment và quyền. Với eventual consistency, đợi tối đa deadline rồi mới kết luận fail; đếm trùng theo `test_event_id`.
7. **Kiểm tra sự cố:** vô hiệu tạm một sink trong môi trường test, tạo burst, restart và graceful stop; đối chiếu policy và metrics.
8. **Khôi phục:** trả cấu hình và level về trạng thái dự kiến; giữ báo cáo test gồm actual routes, timings, event count và lỗi phát hiện.

Ví dụ bảng kết quả có thể lưu cho mỗi test run:

| Event | Expected | Actual | Count | Verdict |
| --- | --- | --- | ---: | --- |
| R2 / `order.created` | CONSOLE | CONSOLE | 1 | PASS |
| R4 / `payment.failed` | ERROR_FILE | ERROR_FILE | 1 | PASS |
| R5 / `role.changed` | AUDIT | AUDIT + CONSOLE | 2 | FAIL: rò qua root |
| R1 / `cache.detail` | Không tuyến nào | Không tuyến nào | 0 | PASS |

Đây là **ví dụ báo cáo giả định**, không phải kết quả chạy từ một hệ thống thật. Một kiểm thử âm đạt yêu cầu chỉ khi các sink liên quan đã được kiểm tra; một câu lệnh search trả về 0 bản ghi vì query sai hoặc thiếu quyền không chứng minh không có event.

## 12. Các lỗi routing thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Log INFO biến mất khỏi mọi sink | Effective level quá cao hoặc filter sớm `DENY` | Kiểm tra level và filter tại logger trước khi xét appender. |
| Log ERROR vào console thay vì file lỗi | AppenderRef/filter sai, đường file không ghi được | Kiểm tra cấu hình thực thi, status/error của appender và rule level. |
| Một event xuất hiện hai lần | Additivity, nhiều appender tham chiếu cùng sink, collector ingest hai nguồn | Kiểm tra hierarchy, refs và event ID ở từng hop. |
| Audit event xuất ra app console | Logger audit vẫn đi qua root hoặc rule marker/MDC không match | Dùng route audit rõ ràng, test negative ở console và quyền truy cập. |
| Log có routing key đúng nhưng không thấy ở sink | Event bị level/filter khác chặn; sink lỗi hoặc queue drop | Kiểm tra từng tầng từ producer đến backend. |
| Log request sau rơi vào sink của request trước | MDC/ThreadContext còn giá trị trong thread pool | Dọn/khôi phục context và test đa request nối tiếp. |
| Log async không có route key | Context không được capture/propagate vào event | Kiểm tra context capture trước queue và cơ chế async của framework. |
| Sink động tạo quá nhiều file/appender | Route key lấy từ input có cardinality lớn hoặc không được validate | Dùng allowlist route hữu hạn và default route có kiểm soát. |
| Staging log nằm trong production index | Environment label/routing rule/agent config không nhất quán | Truy vết đường agent → collector → index, kiểm thử cả hai chiều. |
| Log sai timestamp hoặc mất trace ID | Encoder/transform của collector bỏ trường | So bản ghi trong JVM, sink, raw collector và index. |
| Test đếm ít hơn kỳ vọng | Async chưa drain, level/filter drop hoặc search quá sớm | Dùng chờ hữu hạn, đo drop counters và kiểm tra sink trước backend. |
| Test PASS dù log sai tuyến | Chỉ assert có mặt ở một sink; không assert các sink còn lại | Viết ma trận kỳ vọng và negative assertions cho từng trường hợp. |

## 13. Mở rộng test cho bảo mật, tải và thay đổi cấu hình

### Security và dữ liệu nhạy cảm

Một route audit hoặc security phải được kiểm tra cả **độ đúng** và **khả năng cách ly**:

- Log bảo mật không xuất vào console/index ít hạn chế hơn trừ khi policy cho phép.
- Tenant/group A không tạo file hoặc route tới tenant/group B chỉ bằng cách gửi giá trị MDC tùy ý.
- Đường dẫn sink hoặc topic name không được xây trực tiếp từ input không tin cậy.
- Secret, token, cookie và dữ liệu cá nhân cần được bỏ/redact trước khi log đi qua các đích không phù hợp.
- Quyền đọc, retention, encryption và auditability của chính sink cần được kiểm tra riêng; logger routing không thay thế kiểm soát truy cập.

### Hiệu năng và độ tin cậy

Test với ít event có thể bỏ sót lỗi race. Sau khi unit/integration test PASS, dùng một đợt tải đại diện và kiểm tra: tỉ lệ route, throughput từng sink, p95/p99 logger call, queue capacity, dropped events, log delay và mức sử dụng tài nguyên. Test tình huống route ít phổ biến, ví dụ 99% console và 1% audit, để tránh chỉ kiểm tra đường chính.

Thử thay cấu hình trên staging bằng bản release kế tiếp, chạy cùng bộ ma trận và so sánh; đặc biệt chú ý thay đổi logger name, additivity, appender ref, tên field JSON hoặc cơ chế routing dynamic. Gắn regression tests với pipeline deploy khi route ảnh hưởng đến alert, bảo mật hoặc truy vết.

### Quy tắc để kết luận PASS

Một routing rule được xem là đạt khi:

- Các event cần giữ **đều xuất hiện** đúng những sink được quy định, trong thời hạn chấp nhận.
- Những event không được phép đi một sink **thực sự vắng mặt** ở đó sau khi đã xác minh sink/test pipeline hoạt động.
- Số lần xuất hiện khớp cardinality mong đợi (độc quyền hoặc fan-out).
- Context, level, event code và nội dung thiết yếu được giữ hoặc transform theo schema đã duyệt.
- Missing/invalid routing key, async overload, sink failure và shutdown có hành vi đúng với chính sách thiết kế và được đo/giám sát.
- Không có đường rò log nhạy cảm hoặc lỗi phân loại giữa môi trường/tenant.

## 14. Câu hỏi tự kiểm tra

1. Vì sao thấy `payment.failed` ở ERROR_FILE chưa đủ để kết luận routing chính xác?
2. Trong Logback, điều gì xảy ra khi logger con có appender riêng nhưng `additivity=true`?
3. Một `ERROR` audit có nên xuất trong application-error.log không? Cần dựa vào tài liệu nào để trả lời?
4. Vì sao `trace_id` không thay thế được `test_event_id` khi kiểm tra log trùng?
5. Nếu MDC thiếu `log_route`, hệ thống cần làm gì và phải test những điều kiện nào?
6. Một log đã xuất ra stdout nhưng không thấy ở index sau 1 giây: những tầng nào cần kiểm tra trước khi kết luận lỗi routing?
7. Test chỉ đo số event ở sink có thể bỏ sót những lỗi gì khi async queue đầy hoặc producer đã filter event từ trước?
8. Làm sao chứng minh routing audit không rò sang console, đặc biệt khi có logger hierarchy và collector đa nguồn?

**Tiêu chí đạt:** Bạn lập được ma trận expected routes, chạy được test Java 17, phân biệt route/filter/additivity, tìm đúng nguyên nhân log bị mất hoặc trùng, và xác minh được cả đường đi **đúng đích** lẫn sự **vắng mặt ở đích sai** từ JVM đến log backend.

## Tài liệu tham khảo

- [Oracle Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — level, parent handlers và các API dùng trong ví dụ.
- [Oracle Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html) — xử lý và lọc `LogRecord` cho một sink.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html) — logger hierarchy, additivity và log levels.
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html) — appender filters và các kết quả `ACCEPT`, `DENY`, `NEUTRAL`.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html) — appender, routing qua cấu hình và SiftingAppender.
- [Apache Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html) — LoggerConfig, additivity, filters và AppenderRef.
- [Apache Log4j 2 — Routing Appender](https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html#RoutingAppender) — routing động theo context và routes.
