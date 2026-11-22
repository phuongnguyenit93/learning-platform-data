# Bộ định tuyến log trong kiến trúc logging của Java

## 1. Bộ định tuyến log là gì và vì sao cần?

Trong ứng dụng nhỏ, mọi thông báo log có thể cùng đi đến màn hình terminal. Khi hệ thống lớn hơn, các bản ghi có mục đích khác nhau: log vận hành cần xuất hiện ở console hoặc hệ thống theo dõi; cảnh báo cần được chú ý sớm; log kiểm toán (audit) cần được kiểm soát quyền truy cập và thời gian lưu; log gỡ lỗi có thể chỉ cần ở môi trường thử nghiệm.

**Bộ định tuyến log (log router)** là phần áp dụng các quy tắc để quyết định **bản ghi nào được chuyển đến đích nào**, có thể chuyển một bản ghi đến nhiều đích, hoặc loại bỏ bản ghi không phù hợp. Quy tắc thường dựa trên mức độ nghiêm trọng, tên logger, loại sự kiện, dịch vụ, môi trường hoặc trường ngữ cảnh trong bản ghi. Trong các thư viện Java, chức năng này thường nằm ở tổ hợp `Logger`, bộ lọc (`Filter`), `Handler`/`Appender` và cấu hình lan truyền; trong hệ thống tập trung, tác nhân thu thập log hoặc pipeline xử lý cũng có thể định tuyến lần nữa.

Hãy hình dung:

```text
Code Java
    |
    v
Logger (nguồn sự kiện và mức log)
    |
    v
Bộ lọc / quy tắc định tuyến
    |-------------------|--------------------|
    v                   v                    v
Console / stdout     File / audit         Cảnh báo / collector
    |                   |                    |
    v                   v                    v
Thu thập tập trung   Lưu trữ kiểm soát    Phân tích / cảnh báo
```

Điều quan trọng là **tạo sự kiện**, **quyết định đường đi**, **định dạng** và **ghi ra đích** là các trách nhiệm có thể tách riêng. Mã nghiệp vụ nên mô tả chuyện đã xảy ra; cấu hình logging quyết định nó cần đến đâu. Nhờ vậy, thêm một đích lưu trữ mới thường không đòi hỏi sửa các câu lệnh log nằm rải rác trong toàn bộ ứng dụng.

## 2. Đặt bộ định tuyến đúng vị trí trong kiến trúc

Một pipeline logging phổ biến gồm các bước:

1. **Nơi phát log (producer):** mã thực thi gọi API logging, ví dụ `logger.info("order.created")`, có thể đính kèm ngoại lệ và ngữ cảnh.
2. **Logger:** mang tên phân loại nguồn, áp dụng mức cho phép hoặc bộ lọc ở nguồn. Nếu bị chặn ở bước này, sự kiện sẽ không tới handler.
3. **Bộ định tuyến và bộ lọc:** chọn một hoặc nhiều nơi nhận theo chính sách. Bộ lọc trên mỗi nơi nhận có thể khác nhau.
4. **Formatter/encoder:** chuyển `LogRecord` hoặc đối tượng sự kiện thành dòng văn bản hay JSON, có định dạng timestamp, level, trường cấu trúc và stack trace.
5. **Handler/appender (đích cục bộ):** ghi ra console, tệp, hàng đợi hoặc đích được hỗ trợ.
6. **Collector/pipeline tập trung (nếu có):** đọc stdout/tệp hoặc nhận dữ liệu đã chuyển đi, có thể tiếp tục lọc, che dữ liệu, phân phối và lưu theo chính sách.

Ví dụ, ứng dụng có thể xuất JSON ra stdout, để tác nhân chạy cùng container thu thập và gửi đến hệ thống phân tích. Khi đó **ứng dụng định tuyến vào stdout; pipeline tập trung định tuyến tới nơi lưu trữ**. Không nên nhầm hai tầng điều khiển này.

### Các kiểu định tuyến

| Tiêu chí | Ví dụ quy tắc | Tình huống phù hợp |
| --- | --- | --- |
| Mức độ (`level`) | `WARNING`/`ERROR` đến kênh cảnh báo | Phát hiện bất thường cần chú ý. |
| Nguồn (`logger name`) | `com.example.payment` đến kênh thanh toán | Tách nhóm chức năng để điều tra. |
| Loại sự kiện | `event.type=audit` đến kho kiểm toán | Áp dụng lưu trữ/quyền truy cập đặc thù. |
| Dịch vụ/môi trường | `service=checkout`, `env=prod` đến chỉ mục production | Tách dữ liệu theo nguồn, môi trường. |
| Kết quả/thành phần | `outcome=failed` hoặc `component=database` đến tuyến phân tích chuyên biệt | Điều tra thất bại hay nút nghẽn cụ thể. |

Bộ định tuyến có thể thực hiện:

- **Chọn một đích (exclusive routing):** log kiểm toán chỉ tới kho được kiểm soát.
- **Phân phối nhiều đích (fan-out):** cùng một cảnh báo đi vào luồng vận hành tổng quát và luồng cảnh báo.
- **Loại bỏ có chủ đích:** log `DEBUG` không cần thiết ở production.
- **Biến đổi/che dữ liệu trước khi chuyển:** đổi cấu trúc hoặc loại bỏ trường nhạy cảm theo chính sách; phải cẩn trọng vì nhiều bản sao có thể đi qua các tuyến khác nhau.

**Định tuyến không tự làm sự kiện trở nên tin cậy.** Một dòng log đã bị chặn bởi mức nguồn, mất do hàng đợi đầy, hoặc chưa được ghi trước khi tiến trình dừng thì các bộ định tuyến phía sau không thể khôi phục chỉ bằng quy tắc chọn đích.

## 3. Phân biệt cấp log, logger, filter, handler và sự lan truyền

Trong `java.util.logging` (JUL, có sẵn trong JDK):

- **`Logger`:** tên phân loại, ví dụ `app.orders`; mỗi logger có mức riêng và có thể có logger cha.
- **`LogRecord`:** dữ liệu của một sự kiện như level, logger name, message, thời điểm, throwable.
- **`Filter`:** hàm quyết định một bản ghi có được đi qua hay không; có thể gắn vào logger hoặc handler.
- **`Handler`:** nơi nhận bản ghi. `ConsoleHandler`, `FileHandler` và các handler khác chịu trách nhiệm xuất bản bản ghi.
- **`Formatter`:** chọn cách thể hiện bản ghi trước khi ghi.
- **`useParentHandlers`:** điều khiển việc chuyển bản ghi lên handler của logger cha; rất quan trọng khi tránh ghi trùng.

Trong JUL, các mức từ nghiêm trọng đến chi tiết thường là:

```text
SEVERE > WARNING > INFO > CONFIG > FINE > FINER > FINEST
(ALL cho phép mọi mức; OFF chặn mọi mức)
```

Tại nguồn, logger có thể không tạo bản ghi nếu mức sự kiện thấp hơn ngưỡng hiệu lực của logger hoặc bị filter từ chối. Bản ghi đã qua nguồn có thể được đưa tới handler tại logger và handler của logger cha khi cho phép lan truyền. **Mỗi handler lại có mức và filter riêng**, nên cùng một bản ghi có thể được nhận ở một đích nhưng bị loại ở đích khác.

Ví dụ về chính sách:

| Sự kiện | Kênh vận hành (INFO+) | Kênh cảnh báo (WARNING+) | Kênh kiểm toán (`app.audit`, INFO+) |
| --- | --- | --- | --- |
| `app.orders` / FINE | Không | Không | Không |
| `app.orders` / INFO | Có | Không | Không |
| `app.orders` / WARNING | Có | Có | Không |
| `app.audit` / INFO | Không | Không | Có |

Một bản ghi `WARNING` xuất hiện ở cả vận hành và cảnh báo **là fan-out có chủ đích**; một bản ghi xuất hiện hai lần trong cùng kênh vì vừa gắn handler ở logger con vừa lan truyền lên cha thường là **trùng lặp do cấu hình**.

### Logger cha và tính kế thừa

Tên logger theo các thành phần ngăn cách bằng dấu chấm tạo cấu trúc phân cấp, chẳng hạn `app.orders` nằm dưới `app`. Nếu logger con không đặt mức riêng, nó thường sử dụng mức hiệu lực kế thừa từ cha. Tuy nhiên, khi đưa bản ghi đã được chấp nhận lên handler của cha, **mức của logger cha không phải một vòng lọc lại cho bản ghi ấy**; handler ở cha vẫn áp dụng mức và filter của chính nó. Vì vậy, việc kiểm soát chỉ bằng mức của logger cha có thể cho kết quả khác dự kiến.

Trong các backend khác như Logback, khái niệm tương ứng thường là `Appender` và `additivity`. `SLF4J` chủ yếu cung cấp API (facade) cho mã ứng dụng; các quy tắc xuất bản bản ghi phụ thuộc backend đang được dùng. Không được giả định cấu hình hoặc tên level của JUL và Logback hoàn toàn thay thế cho nhau.

## 4. Ví dụ Java 17: định tuyến theo nguồn và mức độ

Ví dụ dùng **JUL của JDK, không cần thư viện ngoài**. Một logger cha nhận hai logger con: `lesson.route.orders` (vận hành đơn hàng) và `lesson.route.audit` (kiểm toán). Ba handler thể hiện ba đích bằng nhãn in ra stdout:

- `OPS`: log đơn hàng mức `INFO` trở lên.
- `ALERT`: log đơn hàng mức `WARNING` trở lên.
- `AUDIT`: log kiểm toán mức `INFO` trở lên.

Trong thực tế, mỗi handler có thể ghi ra một đích khác nhau; ở đây chúng cùng in ra stdout để người học nhìn rõ quyết định định tuyến, không phụ thuộc tệp hay mạng. Lưu thành `LogRoutingDemo.java`:

```java
import java.util.logging.Filter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogRoutingDemo {

    static final class RoutedHandler extends Handler {
        private final String destination;

        RoutedHandler(String destination, Level minimum, Filter filter) {
            this.destination = destination;
            setLevel(minimum);
            setFilter(filter);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            System.out.printf("%s | %s | %s | %s%n",
                    destination,
                    record.getLevel().getName(),
                    record.getLoggerName(),
                    record.getMessage());
        }

        @Override
        public void flush() {
            // Ví dụ ghi trực tiếp ra stdout; không có bộ đệm riêng.
        }

        @Override
        public void close() {
            // Không sở hữu System.out nên không đóng luồng này.
        }
    }

    public static void main(String[] args) {
        Logger router = Logger.getLogger("lesson.route");
        router.setLevel(Level.ALL);
        router.setUseParentHandlers(false);

        String ordersName = "lesson.route.orders";
        String auditName = "lesson.route.audit";

        Handler operations = new RoutedHandler(
                "OPS", Level.INFO,
                record -> ordersName.equals(record.getLoggerName()));

        Handler alerts = new RoutedHandler(
                "ALERT", Level.WARNING,
                record -> ordersName.equals(record.getLoggerName()));

        Handler audits = new RoutedHandler(
                "AUDIT", Level.INFO,
                record -> auditName.equals(record.getLoggerName()));

        router.addHandler(operations);
        router.addHandler(alerts);
        router.addHandler(audits);

        Logger orders = Logger.getLogger(ordersName);
        Logger audit = Logger.getLogger(auditName);
        orders.setLevel(Level.ALL);
        audit.setLevel(Level.ALL);

        orders.fine("order.cache.hit");
        orders.info("order.created");
        orders.warning("order.retry");
        audit.info("permission.changed");

        router.removeHandler(operations);
        router.removeHandler(alerts);
        router.removeHandler(audits);
        operations.close();
        alerts.close();
        audits.close();
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac LogRoutingDemo.java
java LogRoutingDemo
```

Stdout:

```text
OPS | INFO | lesson.route.orders | order.created
OPS | WARNING | lesson.route.orders | order.retry
ALERT | WARNING | lesson.route.orders | order.retry
AUDIT | INFO | lesson.route.audit | permission.changed
```

Giải thích từng quyết định:

1. `orders.fine("order.cache.hit")` đi qua mức `ALL` ở nguồn nhưng không vượt ngưỡng `INFO`/`WARNING` của handler phù hợp; nó không được in.
2. `orders.info("order.created")` khớp nguồn đơn hàng và đủ mức cho `OPS`, nhưng không đủ mức cho `ALERT`.
3. `orders.warning("order.retry")` khớp cả `OPS` và `ALERT`. Hai dòng có cùng nội dung ở **hai nhãn đích khác nhau** đúng với chính sách fan-out.
4. `audit.info("permission.changed")` chỉ qua `AUDIT` nhờ filter theo logger name, mặc dù cũng có mức `INFO`.
5. `router.setUseParentHandlers(false)` ngăn các bản ghi đi tiếp tới handler của logger gốc của JUL và làm hỏng kết quả minh họa bằng các dòng ngoài ý muốn. Trong ứng dụng thực tế, chỉ tắt sự lan truyền khi đã kiểm tra chủ đích ghi log của toàn bộ cây logger.

Lưu ý về chương trình: lớp `RoutedHandler` minh họa nơi ra quyết định bằng một lần in đồng bộ ra stdout. Nó **không** cung cấp cơ chế ghi tệp bền vững, gửi lại khi lỗi, tự xóa dữ liệu nhạy cảm hay quản lý hàng đợi. Một handler production cần tính đến đồng thời nhiều luồng, định dạng bản ghi, quyền truy cập và lỗi của đích nhận; nên ưu tiên handler/appender đã được kiểm thử và cấu hình phù hợp thay vì tự viết cơ chế vận chuyển dữ liệu phức tạp.

## 5. Định tuyến bằng cấu hình thay vì viết quy tắc vào mã nghiệp vụ

Trong ứng dụng thực, các lời gọi như `logger.info(...)` nên giữ ổn định, còn mức, filter và appender được khai báo qua cấu hình triển khai. Ví dụ sau **minh họa Logback**, chỉ dùng khi ứng dụng đã có SLF4J và Logback trong classpath; đây là một cấu hình backend, không phải mã JUL và không phải chương trình Java độc lập:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="AUDIT_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/audit.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.audit" level="INFO" additivity="false">
        <appender-ref ref="AUDIT_FILE" />
    </logger>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Trong cấu hình này:

- Log dưới `com.example.audit` được gửi tới `AUDIT_FILE` và không lan tiếp tới `CONSOLE` của logger gốc vì `additivity="false"`.
- Những logger khác không có cấu hình chuyên biệt sẽ dùng ngưỡng `INFO` ở root và ghi ra console.
- `additivity="false"` có tác dụng tránh lan truyền, nhưng **cũng có thể làm mất tuyến thu thập tổng quát** nếu vận hành kỳ vọng mọi log đều có ở console. Quy tắc này phải được chọn theo sơ đồ thực tế.
- File trong container có thể bị xóa khi container thay mới; **ghi file audit không đồng nghĩa với lưu trữ kiểm toán đáng tin cậy**. Cần xác định quyền truy cập, thu thập, giữ dữ liệu và mức đảm bảo riêng.

Một kênh chỉ dành cho mức `ERROR` hoặc `WARN` thường cần ngưỡng của appender và/hoặc filter tương ứng. Một logger có mức `INFO` không tự động chia `INFO` và `ERROR` thành hai đích. Khi cần fan-out, gắn các appender và filter chính xác cho từng đích, rồi kiểm tra kết quả bằng những sự kiện mẫu.

## 6. Định tuyến tại bộ thu thập tập trung

Khi hệ thống có nhiều service hoặc container, thường cần thêm một tầng định tuyến bên ngoài JVM:

```text
Service A --stdout--> collector ----> kho tìm kiếm log vận hành
Service B --stdout--> collector ----> kho lưu dài hạn
                          |
                          +--------> kênh kiểm toán có phân quyền
                          |
                          +--------> bộ phân tích/cảnh báo
```

Tầng này có thể dựa trên `service`, `environment`, `event.type` hoặc các trường đã chuẩn hóa để đưa bản ghi tới nơi lưu. Một ứng dụng phát log đúng cấu trúc JSON và có metadata nguồn sẽ đơn giản hóa đáng kể việc định tuyến tập trung.

Ví dụ một sự kiện dạng JSON:

```json
{
  "timestamp": "2026-01-01T10:15:30Z",
  "level": "WARN",
  "service": "checkout",
  "environment": "prod",
  "logger": "com.example.checkout.PaymentService",
  "event": "payment.retry",
  "trace_id": "trace-42",
  "attempt": 2,
  "error_code": "UPSTREAM_TIMEOUT"
}
```

Bộ thu thập có thể định tuyến dựa trên `environment=prod` và `event=payment.retry`, đồng thời giữ `trace_id` để truy tìm lần xử lý. Không nên phân tuyến hoặc gắn nhãn metric theo từng `trace_id` hay URL có ID riêng vì số nhóm sẽ tăng không kiểm soát. Trường động phù hợp cho **tìm kiếm chi tiết**; trường số lượng giá trị giới hạn phù hợp cho **phân nhóm tổng hợp**.

Các điểm cần quyết định cho hệ thống thực:

- **Nơi lọc:** lọc ở JVM tiết kiệm lưu lượng và bộ nhớ nhưng loại bỏ dữ liệu vĩnh viễn; lọc sau khi thu thập giữ khả năng phân tích rộng hơn nhưng tăng chi phí.
- **Bản ghi đến muộn, mất hoặc trùng:** hàng đợi bất đồng bộ có thể đầy; collector có thể gửi lại sau lỗi mạng và làm trùng bản ghi. Nếu cần đếm chính xác, xác định định danh sự kiện và chính sách xử lý trùng/mất.
- **Thứ tự:** các bản ghi trên các luồng, JVM hoặc nhiều đích không có bảo đảm giữ nguyên thứ tự toàn cục; dùng timestamp và correlation ID/trace ID phù hợp, không dựa vào vị trí dòng để suy ra quan hệ nhân quả.
- **Bộ đệm:** định tuyến bất đồng bộ giảm thời gian chờ trên đường xử lý chính nhưng có thể mất log lúc crash hoặc nghẽn; đồng bộ có thể kéo dài latency nếu đích chậm.
- **Bảo mật và phân quyền:** loại bỏ token, mật khẩu, dữ liệu cá nhân nhạy cảm ngay khi có thể; kênh audit phải có quyền truy cập, retention và kiểm soát sửa/xóa phù hợp.
- **Chi phí lưu trữ:** tuyến DEBUG có thời gian giữ ngắn hơn tuyến sự cố; chính sách vẫn phải đủ dữ liệu để điều tra khi cần.

Đặc biệt, **log kiểm toán** dùng cho yêu cầu pháp lý hoặc bảo đảm nghiệp vụ có thể cần một luồng sự kiện giao dịch chuyên dụng và mức đảm bảo cao hơn log ứng dụng thông thường. Chỉ cấu hình router không tạo ra tính toàn vẹn hoặc bảo đảm giao nhận.

## 7. Kiểm thử và quan sát chính bộ định tuyến

Một thay đổi cấu hình nhỏ cũng có thể làm mất log quan trọng hoặc nhân đôi số lượng bản ghi. Nên kiểm thử bằng ma trận nguồn × mức × đích, giống bảng trong phần 3.

Các ca tối thiểu cho ví dụ ở phần 4:

| Đầu vào | Đích mong đợi |
| --- | --- |
| `orders / FINE` | Không đích nào. |
| `orders / INFO` | Chỉ `OPS`. |
| `orders / WARNING` | `OPS` và `ALERT`, mỗi đích một bản ghi. |
| `audit / INFO` | Chỉ `AUDIT`. |
| `orders / SEVERE` | `OPS` và `ALERT`, nếu không có filter bổ sung. |

Ngoài việc kiểm tra đường đi của log, cần biết **router có hoạt động hay không**. Theo dõi số bản ghi đi vào, đi ra mỗi đích, bị lọc, bị bỏ vì hàng đợi đầy, lỗi khi xuất bản và độ trễ của bộ đệm nếu công cụ hỗ trợ. Phân biệt “không có log mới vì dịch vụ không phát sự kiện” với “dịch vụ vẫn hoạt động nhưng pipeline đã hỏng”.

Kiểm tra thủ công hữu ích: tạo một log mẫu có `event` và `trace_id` biết trước trong môi trường thử nghiệm, xác nhận nó xuất hiện đúng kênh, đúng số lần, đúng mức và đúng cấu trúc; sau đó xác nhận bản ghi chứa thông tin cần che không xuất hiện ở bất kỳ đích nào. Không đưa thông tin nhạy cảm thật vào dữ liệu kiểm thử.

## 8. Lỗi thiết kế thường gặp

1. **Định tuyến theo chuỗi message không ổn định:** thay câu chữ hay ngôn ngữ khiến quy tắc gãy. Ưu tiên logger name, event code, marker hoặc trường cấu trúc đã chuẩn hóa.
2. **Đặt mức ở handler nhưng quên mức ở nguồn:** sự kiện bị logger loại sớm sẽ không tới mọi handler, dù handler có để `ALL`.
3. **Gắn appender ở cả con lẫn cha mà quên lan truyền:** cùng sự kiện xuất hiện trùng ở một kênh. Kiểm tra `useParentHandlers` (JUL) hoặc `additivity` (backend).
4. **Tắt lan truyền cho mọi logger:** loại bỏ luôn kênh console/collector tổng quát; chỉ áp dụng khi có sơ đồ tuyến rõ ràng.
5. **Dùng logger name động theo request/user:** làm phân loại mất ổn định và tăng độ phức tạp; dùng một logger cố định theo thành phần và lưu request ID trong trường ngữ cảnh.
6. **Xem gửi thành công là lưu bền vững:** lời gọi `publish` hoặc `logger.info` trả về không bảo đảm bản ghi đã nằm trong kho tập trung, nhất là khi có buffer và network.
7. **Đưa log chứa bí mật sang nhiều đích:** tạo thêm bản sao dữ liệu nhạy cảm và khó kiểm soát; che ở nguồn, kiểm soát quyền và thời gian giữ tại từng đích.
8. **Làm việc nặng trong filter hoặc handler đồng bộ:** có thể làm chậm đường xử lý nghiệp vụ; dùng bộ xử lý chuyên dụng và áp dụng giới hạn tải.
9. **Tin rằng logger level của cha lọc lại mọi sự kiện con:** trong JUL, sau khi logger con chấp nhận sự kiện, handler cha áp dụng quy tắc của chính handler; hiểu sai dễ làm lộ hoặc nhân đôi log.
10. **Không kiểm thử khi đổi cấu hình:** có thể làm mất kênh audit hoặc giấu cảnh báo khi nâng cấp/triển khai; luôn có bộ sự kiện mẫu để đối chiếu tuyến mong đợi.

## 9. Bài tập vận dụng

Một ứng dụng Java có ba dòng sự kiện: `checkout / INFO / order.created`, `checkout / WARNING / payment.retry`, `audit / INFO / role.changed`. Yêu cầu là kênh vận hành nhận mọi sự kiện checkout từ INFO, kênh cảnh báo chỉ nhận checkout từ WARNING, còn kênh kiểm toán chỉ nhận audit từ INFO. Hỏi:

1. Mỗi sự kiện sẽ đến những đích nào?
2. Nếu chỉ cấu hình logger `checkout` ở mức `INFO` và thêm một handler `WARNING`, có đảm bảo có bản sao INFO ở kênh vận hành không?
3. Nếu log `payment.retry` xuất hiện hai lần trong kênh cảnh báo, những vị trí cấu hình nào cần kiểm tra?
4. Nếu collector mất kết nối 20 giây, những câu hỏi nào cần trả lời trước khi nói “không mất log”?

**Gợi ý đáp án:** `order.created` → vận hành; `payment.retry` → vận hành và cảnh báo; `role.changed` → kiểm toán. Handler `WARNING` không ghi bản INFO, nên phải có handler vận hành với mức và filter phù hợp. Khi trùng, kiểm tra nhiều handler cùng đích, quan hệ logger cha–con và cơ chế gửi lại của collector. Khi mất kết nối, phải kiểm tra loại buffer, giới hạn hàng đợi, chính sách drop/retry, thời gian giữ dữ liệu, tiến trình crash và khả năng xác nhận đã nhận thực sự của đích.

**Tự kiểm tra:** Nếu có thể chỉ ra tại sao một dòng INFO bị mất dù handler để ALL, cách một WARNING được fan-out hợp lệ, ý nghĩa của `additivity`/`useParentHandlers`, và sự khác nhau giữa route trong JVM với route tại collector, bạn đã nắm được vai trò của bộ định tuyến log trong kiến trúc logging.