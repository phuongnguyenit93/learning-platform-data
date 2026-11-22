# Tách log audit khỏi log ứng dụng trong Java

## 1. Tách log audit là gì và tại sao cần làm?

**Log audit** (nhật ký kiểm toán) ghi nhận những hành động có ý nghĩa về trách nhiệm, truy vết và kiểm chứng: **ai** đã thực hiện **hành động gì**, trên **đối tượng nào**, **khi nào**, từ **ngữ cảnh nào** và **kết quả ra sao**. Ví dụ: cấp quyền quản trị, thay đổi trạng thái đơn hàng, phê duyệt thanh toán, truy cập dữ liệu nhạy cảm hoặc đăng nhập thất bại.

**Log ứng dụng** (application/diagnostic log) phục vụ vận hành và gỡ lỗi: exception, latency, trạng thái xử lý, lần retry, kết nối downstream, truy vấn hoặc thông điệp kỹ thuật. Hai loại có thể cùng liên quan một request nhưng khác mục đích, mức quan trọng, quyền truy cập, thời gian lưu và yêu cầu bảo toàn.

**Tách log audit** là phân loại sự kiện ngay từ nguồn và định tuyến audit đến **kênh, appender, file hoặc hệ thống lưu trữ riêng**, áp dụng chính sách tiếp nhận và bảo vệ phù hợp. Chỉ thêm chữ "AUDIT" vào message của logger chung không tạo ra một đường audit độc lập.

| Tiêu chí | Log ứng dụng | Log audit |
| --- | --- | --- |
| Câu hỏi chính | Hệ thống chạy thế nào, lỗi ở đâu? | Ai làm gì, với đối tượng nào và kết quả gì? |
| Ví dụ | Connection timeout, request slow, retry | USER_ROLE_CHANGED, ORDER_APPROVED, ACCESS_DENIED |
| Khối lượng | Có thể rất lớn, nhiều DEBUG/INFO | Thường chọn lọc theo hành động nghiệp vụ/bảo mật |
| Lọc/sampling | Có thể giảm log chẩn đoán theo chính sách | Sự kiện bắt buộc không được sampling/loại tùy tiện |
| Thời gian lưu | Theo nhu cầu quan sát, chi phí | Theo chính sách kiểm toán và nghĩa vụ áp dụng |
| Quyền truy cập | Nhóm vận hành/phát triển theo phân quyền | Giới hạn hơn; bảo vệ khỏi sửa/xóa trái phép |
| Độ bền | Có thể chấp nhận mất một phần log không quan trọng | Có thể yêu cầu chứng cứ bền vững, kiểm tra toàn vẹn |

Một sự kiện ERROR không đương nhiên là audit; một hành động cấp quyền **thành công** có thể cần audit dù không có bất kỳ ERROR nào. Vì thế không thể tạo kho audit đáng tin cậy chỉ bằng cách sao chép toàn bộ WARN/ERROR từ application.log.

## 2. Những sự kiện nào nên đi vào kênh audit?

Phạm vi do nghiệp vụ, rủi ro và quy định áp dụng quyết định. Ví dụ có giá trị truy vết:

- **Xác thực và phân quyền:** đăng nhập thành công/thất bại theo chính sách, từ chối truy cập, thay đổi vai trò/quyền, cấp hoặc thu hồi token hay khóa truy cập.
- **Thay đổi dữ liệu quan trọng:** tạo, phê duyệt, từ chối, sửa, hủy, xóa đơn hàng/giao dịch; thao tác quản trị dữ liệu.
- **Truy cập tài nguyên nhạy cảm:** xuất báo cáo, đọc hồ sơ được bảo vệ, tải hoặc chia sẻ dữ liệu quan trọng.
- **Hành động quản trị:** thay đổi cấu hình bảo mật, bật/tắt chức năng quan trọng, thay đổi chính sách hoặc quyền người dùng.
- **Hành động đáng nghi:** cố gắng vượt giới hạn, truy cập không đủ quyền, tác vụ bất thường; cần quy định tiêu chí cụ thể để tránh tạo quá nhiều nhiễu.

Không nên audit mọi dòng DEBUG, mỗi lần gọi getter, mỗi truy vấn SQL hoặc mọi healthcheck. Đó thường là log kỹ thuật, làm tăng khối lượng và che các hành động cần kiểm chứng. Ngược lại, không được bỏ qua sự kiện từ chối quyền chỉ vì giao dịch bị rollback: **một lần thử bị từ chối cũng có thể cần chứng cứ audit**.

Trước khi viết code, xác định danh sách **event code** có nghĩa ổn định, chẳng hạn ORDER_APPROVED, USER_ROLE_REVOKED, EXPORT_REQUESTED. Không dùng câu tiếng Việt tự do làm định danh duy nhất của hành động, vì wording có thể đổi hoặc được địa phương hóa.

## 3. Thiết kế schema audit có cấu trúc

Một bản ghi audit nên là dữ liệu có trường rõ ràng, thay vì một câu khó truy vấn. Ví dụ minh họa JSON:

~~~json
{
  "eventId": "evt-000042",
  "occurredAt": "2026-11-10T02:00:00Z",
  "actorType": "USER",
  "actorId": "user-7",
  "action": "ORDER_APPROVE",
  "targetType": "ORDER",
  "targetId": "order-42",
  "outcome": "SUCCESS",
  "correlationId": "req-1",
  "sourceService": "order-service",
  "reasonCode": "APPROVAL_POLICY_MET"
}
~~~

Các ID trên là dữ liệu giả lập; không dựa vào chúng để suy ra danh tính thực. Một schema thực tế nên xem xét:

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| eventId | Định danh của **một sự kiện audit** | Dùng để loại bản ghi trùng khi retry |
| occurredAt | Thời điểm sự kiện diễn ra, nên có offset/UTC | Đồng bộ đồng hồ, phân biệt thời điểm ghi và thời điểm ingest |
| actorType / actorId | Chủ thể khởi tạo hành động | Có thể là USER, SERVICE, SYSTEM; lấy từ ngữ cảnh đã xác thực |
| action | Mã hành động cố định | Có danh mục và phiên bản schema |
| targetType / targetId | Đối tượng chịu tác động | Dùng định danh cần thiết, hạn chế PII |
| outcome | SUCCESS, DENIED, FAILED, ... | Phân biệt nỗ lực và thay đổi đã commit |
| correlationId | Liên hệ với request/trace nghiệp vụ | **Không thay thế eventId** |
| sourceService | Thành phần tạo sự kiện | Giúp điều tra nhiều dịch vụ |
| reasonCode / metadata được phép | Lý do hoặc thông tin hỗ trợ | Tránh đưa dữ liệu nhạy cảm nguyên dạng |

Một request có thể tạo **nhiều** sự kiện audit; vì vậy correlationId giống nhau là bình thường. eventId phải khác nhau cho từng sự kiện logic, nhưng khi **gửi lại cùng sự kiện** sau lỗi mạng, phải giữ nguyên eventId để consumer deduplicate. Nếu một giao dịch có nhiều attempt, nên quy định rõ cách liên kết transactionId, attemptId và eventId.

Với thay đổi dữ liệu, có thể cần before/after hoặc một diff đã chọn lọc; đừng sao chép toàn bộ bản ghi chứa mật khẩu, token, thông tin tài chính hoặc dữ liệu cá nhân nhạy cảm.

## 4. Mô hình định tuyến: hai logger, hai đích

Với SLF4J + Logback hoặc Log4j 2, một cách đơn giản là tạo **logger có tên riêng cho audit** và gắn appender độc lập:

~~~text
                                  +--> Logger ứng dụng
Code nghiệp vụ -------------------|       |
                                  |       v
                                  |   APPENDER APP
                                  |       |
                                  |   application.log
                                  |
                                  +--> Logger "audit.events"
                                          |
                                          v
                                     APPENDER AUDIT
                                          |
                                       audit.log
                                          |
                                   Kho lưu/collector audit
~~~

Ở đây **định tuyến** dựa trên tên logger được chọn khi phát sự kiện. Không phụ thuộc vào level ERROR/WARN để đoán đó là audit.

Điểm đặc biệt của Logback và Log4j 2 là **additivity**: mặc định log từ logger con có thể đi tới appender của các logger cha, bao gồm ROOT. Nếu gắn audit logger với AUDIT_FILE nhưng vẫn để additivity=true, sự kiện audit có thể đồng thời xuất ở application.log, làm lẫn dữ liệu và tăng nguy cơ lộ thông tin. Để cô lập đường xuất, đặt **additivity=false** trên logger audit và gắn appender AUDIT trực tiếp.

**Chú ý:** additivity=false mà không cấu hình appender tương ứng có thể khiến sự kiện không đi tới đích nào. Cũng phải kiểm tra filter/threshold và error handler của appender. Tách kênh ở mức cấu hình framework chỉ là **bước định tuyến**, chưa phải cam kết lưu bền vững.

## 5. Ví dụ Java 17+ chạy độc lập: quan sát hai luồng log

Đoạn sau dùng java.util.logging (JUL) có sẵn trong JDK để minh họa hai logger độc lập được gắn với hai Handler riêng. Để kết quả dễ kiểm tra, hai Handler đều in ra stdout nhưng có nhãn luồng **APP** và **AUDIT**; trong ứng dụng thực, mỗi Handler/appender sẽ ghi vào đích riêng.

Tạo file **AuditRoutingDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class AuditRoutingDemo {
    private static Handler sink(String stream) {
        return new Handler() {
            { setLevel(Level.ALL); }

            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(stream + " | "
                            + record.getLevel().getName() + " | "
                            + record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };
    }

    public static void main(String[] args) {
        Logger app = Logger.getLogger("demo.app");
        Logger audit = Logger.getLogger("audit.events");

        Handler appSink = sink("APP");
        Handler auditSink = sink("AUDIT");

        // Tránh JUL gửi tiếp đến Handler của logger cha.
        app.setUseParentHandlers(false);
        audit.setUseParentHandlers(false);
        app.setLevel(Level.INFO);
        audit.setLevel(Level.INFO);

        app.addHandler(appSink);
        audit.addHandler(auditSink);

        try {
            app.info("request-complete id=req-1");
            audit.info("eventId=evt-1 actor=user-7 "
                    + "action=ORDER_APPROVE target=order-42 "
                    + "outcome=SUCCESS");

            app.warning("slow downstream");
            audit.info("eventId=evt-2 actor=user-7 "
                    + "action=ORDER_DELETE target=order-42 "
                    + "outcome=DENIED");
        } finally {
            app.removeHandler(appSink);
            audit.removeHandler(auditSink);
            appSink.close();
            auditSink.close();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AuditRoutingDemo.java
java AuditRoutingDemo
~~~

Stdout:

~~~text
APP | INFO | request-complete id=req-1
AUDIT | INFO | eventId=evt-1 actor=user-7 action=ORDER_APPROVE target=order-42 outcome=SUCCESS
APP | WARNING | slow downstream
AUDIT | INFO | eventId=evt-2 actor=user-7 action=ORDER_DELETE target=order-42 outcome=DENIED
~~~

**Giải thích:** Logger demo.app chỉ gửi tới appSink; logger audit.events chỉ gửi tới auditSink. Cả hai đều ở mức INFO, nhưng mục đích log khác nhau. Việc dùng INFO cho sự kiện audit **không có nghĩa audit là log ứng dụng INFO**: kênh audit do **logger và appender chuyên dụng** quyết định. Demo dùng Handler tùy chỉnh có gọi isLoggable(record) để tôn trọng mức và Filter của Handler.

Ví dụ này chỉ chứng minh định tuyến. Console không phải kho audit bền vững; mã minh họa cũng chưa có schema validation, xác thực actor, cơ chế lưu giao dịch, retention hay chống sửa đổi. Những yêu cầu đó cần kiến trúc ở các mục sau.

## 6. Dùng SLF4J để phát audit event có chủ đích

Trong dự án dùng SLF4J, code nghiệp vụ có thể giữ logger bình thường theo tên lớp và tạo **logger audit chuyên dụng** với một tên cố định:

~~~java
// Đoạn minh họa bên trong service dùng SLF4J.
// Yêu cầu dependency SLF4J và logging backend;
// các biến actorId, orderId, eventId, correlationId
// lấy từ các nguồn đã được xác thực/kiểm soát.
private static final org.slf4j.Logger appLog =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

private static final org.slf4j.Logger auditLog =
        org.slf4j.LoggerFactory.getLogger("audit.events");

public void recordApproval(String eventId, String actorId,
                           String orderId, String correlationId) {
    auditLog.info(
            "eventId={} actor={} action=ORDER_APPROVE "
            + "target={} outcome=SUCCESS correlationId={}",
            eventId, actorId, orderId, correlationId);
}
~~~

**Đây là fragment cần đặt vào class phù hợp**, không phải chương trình độc lập. OrderService là tên lớp ví dụ. Các giá trị audit phải được lấy từ ngữ cảnh đáng tin cậy (principal sau xác thực, dữ liệu nghiệp vụ đã xác minh), không mặc nhiên tin actorId do HTTP client tự gửi lên.

Nên tập trung logic audit trong một **AuditService hoặc AuditEventPublisher** để chuẩn hóa eventId, action, outcome, schema và chính sách lỗi. Tránh để mỗi controller tự ghép chuỗi với tên trường không nhất quán. Nếu cần độ tin cậy giao dịch cao, AuditService phải có đường ghi bền vững; gọi auditLog.info(...) đơn thuần không đủ.

Trong các hệ thống có log cấu trúc, ưu tiên chuyển các field audit dưới dạng thuộc tính có cấu trúc hoặc JSON được encode an toàn. Ví dụ chuỗi key=value ở trên giúp học cách routing nhưng khó bảo đảm escaping nếu dữ liệu có dấu cách, dấu xuống dòng hoặc ký tự điều khiển.

## 7. Logback: tách application.log và audit.log

Với SLF4J + Logback Classic, có thể định tuyến audit bằng tên logger và additivity=false. Ví dụ file **logback.xml** (trong Spring Boot có thể dùng **logback-spring.xml** khi phù hợp):

~~~xml
<configuration>
  <appender name="APP_FILE"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>
    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
      <fileNamePattern>logs/application.%d{yyyy-MM-dd}.log</fileNamePattern>
      <maxHistory>14</maxHistory>
    </rollingPolicy>
    <encoder>
      <charset>UTF-8</charset>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <appender name="AUDIT_FILE"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/audit.log</file>
    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
      <fileNamePattern>logs/audit.%d{yyyy-MM-dd}.log</fileNamePattern>
      <maxHistory>90</maxHistory>
    </rollingPolicy>
    <encoder>
      <charset>UTF-8</charset>
      <pattern>%d{ISO8601} %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <logger name="audit.events" level="INFO" additivity="false">
    <appender-ref ref="AUDIT_FILE"/>
  </logger>

  <root level="INFO">
    <appender-ref ref="APP_FILE"/>
  </root>
</configuration>
~~~

**Luồng kết quả khi không có cấu hình khác ghi đè:**

| Logger được gọi | Sự kiện | application.log | audit.log |
| --- | --- | --- | --- |
| com.example.OrderService | INFO request processed | Có | Không |
| audit.events | INFO ORDER_APPROVE | Không | Có |
| audit.events | INFO ACCESS_DENIED | Không | Có |
| com.example.OrderService | ERROR timeout | Có | Không |

Vì ROOT chỉ gắn APP_FILE, logger ứng dụng đi vào file chung. Logger **audit.events** gắn AUDIT_FILE, có additivity=false nên sự kiện của nó không lan lên ROOT. Các logger con theo phân cấp tên audit.events có thể đi theo nhánh này nếu không được override riêng.

Chú ý khi sử dụng:

- **14 và 90 là số kỳ lịch sử mẫu**, không phải thời hạn lưu bắt buộc. Việc xóa log audit cần tuân thủ chính sách thực tế; nếu cần lưu dài hạn, chuyển sang kho audit riêng có kiểm soát retention.
- Hai đường dẫn phải có thư mục và quyền ghi phù hợp. Với nhiều instance/container, không cho các tiến trình độc lập cùng ghi tùy tiện một file có đường dẫn dùng chung nếu backend không hỗ trợ an toàn.
- Không để framework hoặc cấu hình môi trường đặt logger audit thành OFF hoặc cao hơn INFO làm biến mất sự kiện cần lưu. Có thể cần giám sát cấu hình hiệu lực.
- Không đặt appender AUDIT_FILE thêm ở ROOT, trừ khi thật sự muốn mọi log ứng dụng cũng đi vào audit.log.
- **RollingFileAppender chỉ xoay file và quản lý lịch sử cục bộ**; nó không cung cấp lưu trữ bất biến, chống sửa đổi, xác nhận ghi end-to-end hoặc cam kết không mất sự kiện khi crash.

Nếu cần audit JSON có cấu trúc, thay pattern encoder bằng encoder tương thích backend và phiên bản đang dùng; kiểm tra thực tế trường, dấu xuống dòng, ký tự đặc biệt và khả năng truy vấn.

## 8. Log4j 2: cấu hình Logger và AppenderRef riêng

Nếu backend là Log4j 2 Core, mẫu tách tương đương trong file **log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <File name="APP_FILE" fileName="logs/application.log"
          append="true">
      <PatternLayout
          pattern="%d{ISO8601} %-5p %c - %m%n"/>
    </File>

    <File name="AUDIT_FILE" fileName="logs/audit.log"
          append="true">
      <PatternLayout
          pattern="%d{ISO8601} %c - %m%n"/>
    </File>
  </Appenders>

  <Loggers>
    <Logger name="audit.events" level="info" additivity="false">
      <AppenderRef ref="AUDIT_FILE"/>
    </Logger>

    <Root level="info">
      <AppenderRef ref="APP_FILE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

Logger **audit.events** chỉ tham chiếu AUDIT_FILE và dừng chuyển sự kiện tới ROOT. Các logger ứng dụng khác kế thừa ROOT và đi vào APP_FILE. Ví dụ này dùng File appender cho dễ đọc; khi vận hành phải bổ sung rolling/retention, quyền truy cập, giám sát lỗi và lưu trữ dài hạn phù hợp. Không sao chép tên class và phần tử XML giữa Logback và Log4j 2: đây là hai backend khác nhau.

Trong Log4j 2, AppenderRef có thể có level/filter riêng. Nếu một reference hoặc appender filter từ chối sự kiện audit, việc khai báo logger đúng vẫn không bảo đảm log được xuất. Các filter, chính sách async, lỗi I/O và additivity cần được kiểm tra cùng nhau.

### Khi nào dùng marker hoặc context thay cho logger name?

Marker như AUDIT có thể giúp phân loại event bằng cấu trúc thay vì tên logger. Điều đó hữu ích khi muốn giữ logger theo tên lớp, nhưng bắt buộc phải cấu hình đúng filter/routing cho **mọi đích**. Tách bằng một logger có tên cố định là cách dễ kiểm tra cho bài học này.

Với yêu cầu nghiêm ngặt, phần code phát sự kiện vào AuditService thường tốt hơn việc phụ thuộc một quy ước marker có thể bị developer quên gắn. Chọn một cơ chế chính và viết kiểm thử chứng minh mọi event audit bắt buộc thực sự đi vào kênh riêng.

## 9. Spring Boot: logging.level không tạo được kênh audit riêng

Với Spring Boot, các thuộc tính như:

~~~properties
logging.level.root=INFO
logging.level.audit.events=INFO
~~~

chỉ quyết định **level của logger**. Chúng **không tự tạo file audit.log**, không vô hiệu additivity và không gắn appender. Để định tuyến theo tên logger với Logback, hãy đặt cấu hình phù hợp trong logback-spring.xml (hoặc file do hệ thống lựa chọn), như ví dụ ở mục 7.

Tùy Spring Boot và classpath, backend mặc định có thể là Logback; nếu chuyển sang Log4j 2 phải dùng cấu hình tương ứng. Tránh để hai backend/provider xung đột.

Khi deploy, xác minh tệp cấu hình nào **được nạp thật**, môi trường nào ghi đè level, đường dẫn output nào thực sự tồn tại. Thay đổi mức log qua cơ chế quản trị runtime có thể vô tình làm tắt audit logger nếu quyền hoặc guard không được thiết kế đúng.

## 10. Tách đường xuất không đồng nghĩa với lưu audit bền vững

Đây là ranh giới kiến trúc quan trọng nhất:

~~~text
(A) Routing để tiện quan sát
Ứng dụng -> logger audit -> AUDIT_FILE -> file/collector
          Phù hợp khi chấp nhận rủi ro lỗi appender theo chính sách.

(B) Audit bắt buộc phải có chứng cứ bền vững
Giao dịch nghiệp vụ + Audit Outbox (cùng database transaction)
                         |
                         v
                Worker phát sự kiện
                         |
                         v
               Kho audit chuyên dụng
                 (dedup eventId)
                         |
                         v
                Xác nhận, giám sát
~~~

Trong (A), lời gọi auditLog.info(...) có thể trả về sau khi chuyển sự kiện đến appender hoặc queue, nhưng không có nghĩa file đã fsync, collector đã nhận hoặc bản ghi đã được lưu bất biến. Nếu queue đầy, process bị kill, disk đầy hoặc network lỗi, log vẫn có thể mất.

Nếu tính đúng đắn yêu cầu **mọi thay đổi nghiệp vụ thành công phải có bản ghi audit**, một lựa chọn là transactional outbox:

1. Trong **cùng một transaction dữ liệu**, thực hiện thay đổi nghiệp vụ và ghi bản ghi outbox chứa eventId cùng các trường audit cần thiết.
2. Nếu transaction rollback, cả thay đổi nghiệp vụ và bản ghi outbox được rollback; không tuyên bố thành công khi chưa commit.
3. Sau commit, worker đọc outbox, gửi đến kho audit chuyên dụng, retry khi lỗi và ghi nhận việc chuyển thành công.
4. Kho nhận dùng eventId để **idempotent/deduplicate**, vì retry thường có thể chuyển cùng sự kiện nhiều lần.
5. Giám sát backlog outbox, số lần retry, tuổi sự kiện chưa chuyển và trạng thái kho audit.

**Ví dụ SQL khái niệm** (tên bảng/cột và quy tắc kiểm tra ảnh hưởng dòng tùy ứng dụng; không phải script chạy độc lập):

~~~sql
BEGIN;

-- Chỉ ghi SUCCESS sau khi đã kiểm tra quyền và thay đổi hợp lệ.
UPDATE orders
SET status = 'APPROVED'
WHERE id = 42 AND status = 'PENDING';

-- Ứng dụng phải xác nhận đúng một dòng đã đổi trạng thái.
-- Trong cùng transaction, lưu sự kiện để worker phát sau commit.
INSERT INTO audit_outbox (
    event_id, action, actor_id, target_id, outcome
) VALUES (
    'evt-000042', 'ORDER_APPROVE', 'user-7',
    'order-42', 'SUCCESS'
);

COMMIT;
~~~

Không chạy ví dụ này như-is nếu không có bảo đảm kiểm tra số dòng UPDATE và ràng buộc nghiệp vụ. Nếu UPDATE không thành công hoặc không đủ quyền, transaction phải xử lý tương ứng và không phát sự kiện SUCCESS sai sự thật.

**Audit của một lần thử bị từ chối** khác với audit của thay đổi đã commit: việc truy cập trái phép cần được ghi nhận dù không có transaction thay đổi dữ liệu. Phải thiết kế đường ghi phù hợp cho các nỗ lực thất bại mà vẫn tránh tạo false SUCCESS.

Transactional outbox đảm bảo tính nguyên tử giữa thay đổi nghiệp vụ và **ghi outbox trong cùng database transaction**. Nó không tự đảm bảo kho audit bên ngoài đã nhận ngay tức thì; vì vậy cần retry, theo dõi độ trễ, idempotency và cơ chế khôi phục.

## 11. Bảo vệ kênh audit: quyền, toàn vẹn và dữ liệu nhạy cảm

Tách file chỉ có ý nghĩa thực tế khi chính sách kiểm soát của audit cũng được tách phù hợp.

### 11.1. Quyền truy cập

- Chỉ thành phần cần thiết được **ghi** audit; quyền **đọc**, xuất và truy vấn tuân theo vai trò.
- Người quản trị ứng dụng không mặc nhiên có quyền xóa/sửa kho audit đã chốt, nếu yêu cầu kiểm toán đòi hỏi tách trách nhiệm.
- Bảo vệ kết nối từ ứng dụng tới collector/kho audit, xác thực nguồn và giới hạn quyền của service account.
- Truy vấn, tải xuống, thay đổi retention hoặc thay đổi cấu hình audit có thể cũng cần được audit.

### 11.2. Toàn vẹn và chống sửa đổi

Các tùy chọn tùy mức rủi ro gồm kho **append-only/WORM**, phân quyền tách biệt, ký hoặc HMAC theo lô/bản ghi, chuỗi hash có quản lý khóa và mốc thời gian đáng tin cậy, kiểm tra toàn vẹn định kỳ và bản sao bảo vệ riêng.

Một chuỗi hash thuần túy có thể phát hiện thay đổi trong một tập dữ liệu đã chốt nhưng **không đủ chống kẻ có quyền sửa lại toàn bộ chuỗi**; cần bảo vệ neo xác minh/khóa và truy cập kho lưu. File RollingFileAppender thông thường không có những bảo đảm này.

### 11.3. Không thu thập secret

Không ghi password, access token, API key, session cookie, private key, số thẻ đầy đủ, dữ liệu nhạy cảm hoặc nguyên request body vào audit. Chỉ lưu trường tối thiểu để xác minh trách nhiệm; dùng ID/pseudonym phù hợp và redaction có cấu trúc khi cần.

Không lấy actorId từ header tùy ý do client gửi mà chưa xác thực. Dữ liệu message có xuống dòng hoặc ký tự điều khiển phải được encode/sanitize để tránh **log injection**, tức tạo các dòng giả làm sai bằng chứng. Với JSON audit, dùng serializer tin cậy thay vì nối chuỗi thủ công.

Retention phải được quyết định dựa trên nhu cầu kiểm toán, quyền riêng tư và quy định áp dụng; thời hạn lớn hơn không mặc nhiên an toàn hơn. Cần định nghĩa cả xóa theo chính sách, backup và cách khôi phục trong tình huống pháp lý/vận hành phù hợp.

## 12. Ứng xử khi kênh audit lỗi

Một chính sách rõ ràng phải trả lời điều gì xảy ra khi audit sink không sẵn sàng:

| Tình huống | Hệ quả có thể xảy ra | Cách xử lý cần thiết |
| --- | --- | --- |
| File audit hết dung lượng hoặc không có quyền ghi | Appender lỗi hoặc không lưu | Phát hiện lỗi, cảnh báo riêng, phương án khôi phục theo chính sách |
| Queue async của audit đầy | Drop, block hoặc fallback theo cấu hình | Không dùng chính sách drop cho sự kiện bắt buộc nếu không được phép |
| Collector/kho audit mất kết nối | Sự kiện trễ hoặc thất lạc nếu không có hàng đợi bền vững | Retry có giới hạn, durable queue/outbox, giám sát backlog |
| Process bị kill giữa lúc enqueue và flush | Event đã được tạo nhưng chưa bền vững | Không coi enqueue thành công là chứng cứ lưu lâu dài |
| Consumer nhận lặp do retry | Có nhiều bản ghi cùng event | Deduplicate bằng eventId, giữ metadata lần xử lý |
| Clock lệch giữa các service | Khó dựng lại chuỗi hành động | UTC, đồng bộ thời gian, sequence/version nghiệp vụ khi cần |

Hai kiểu chính sách thường được cân nhắc:

- **Fail-open với ghi bền vững đệm:** nghiệp vụ vẫn chạy nếu audit collector tạm lỗi, nhưng event cần được lưu chắc chắn trong outbox để gửi sau. Đường "bỏ qua khi không audit được" không thỏa yêu cầu audit bắt buộc.
- **Fail-closed:** từ chối một số hành động nhạy cảm nếu không thể ghi nhận chứng cứ theo chính sách. Có thể bảo vệ nghĩa vụ kiểm toán nhưng tác động availability; cần quyết định dựa trên rủi ro và quy định, không áp dụng máy móc cho mọi request.

Lỗi ghi audit không nên chỉ được báo qua **chính logger audit đang lỗi**. Cần metric/health/alert độc lập, ví dụ audit_outbox_backlog, audit_delivery_failures, oldest_pending_event_age và kiểm tra bằng chứng ở kho đích.

## 13. Kiểm thử định tuyến và tính đầy đủ

Một bộ kiểm thử tốt phải chứng minh cả **có mặt ở đúng nơi** và **vắng mặt ở nơi không được phép**.

### 13.1. Ma trận tuyến log

Giả sử APP_FILE là appender root, AUDIT_FILE thuộc logger audit.events, additivity=false:

| Event đầu vào | APP_FILE | AUDIT_FILE |
| --- | --- | --- |
| Logger ứng dụng: INFO request completed | Có | Không |
| Logger ứng dụng: ERROR downstream failure | Có | Không |
| Logger audit.events: INFO ORDER_APPROVE | Không | Có |
| Logger audit.events: INFO ACCESS_DENIED | Không | Có |
| Logger audit.events: DEBUG diagnostic | Không | Không nếu audit level=INFO |

**Lưu ý:** nếu audit bắt buộc, không để khả năng tạo sự kiện phụ thuộc việc developer nhớ chọn đúng mức DEBUG/INFO. Dùng API AuditService có quy tắc thống nhất, validation và test bao phủ event code.

### 13.2. Các kiểm thử quan trọng

1. **Routing:** ghi thử một event nghiệp vụ và một event audit, đợi sink flush rồi so sánh từng đích.
2. **Không nhân đôi:** cố tình bật additivity=true trong môi trường thử để thấy audit xuất thêm ở root; sau đó xác minh cấu hình thật không còn bản ghi không mong muốn.
3. **Không thất lạc:** kiểm tra logger audit không bị OFF/ERROR do cấu hình profile hoặc thay đổi runtime.
4. **Schema:** eventId, action, actor, target, outcome, timestamp và correlationId có định dạng/kiểu hợp lệ; trường bắt buộc không null.
5. **Nguồn dữ liệu:** actor đã xác thực, không thể giả mạo bằng header; ký tự xuống dòng trong trường nhập không thể chèn bản ghi giả.
6. **Tách quyền:** người chỉ có quyền xem application.log không mặc nhiên được đọc hoặc thay đổi audit.log.
7. **Downstream failure:** mô phỏng disk full/collector timeout trong môi trường thử; xác minh retry, backlog, alert và chính sách fail-open/fail-closed.
8. **Crash/Restart:** kiểm tra event đã commit vào outbox vẫn còn sau restart và được gửi đúng eventId.
9. **Retry/dedup:** gửi cùng một eventId nhiều lần; đảm bảo kho đích không tạo nhiều sự kiện logic, nhưng vẫn có thể ghi nhận metadata lần retry riêng khi cần.
10. **Truy vấn:** dựng lại một chuỗi hành động mẫu từ audit event và đối chiếu trạng thái nghiệp vụ cuối cùng.
11. **Retention và phục hồi:** kiểm tra xoay file/lưu kho, backup, archive, quyền xóa và thủ tục phục hồi đúng chính sách.

Nếu backend ghi bất đồng bộ hoặc collector có độ trễ index, phải chờ xử lý và flush có kiểm soát trước khi kết luận thiếu event. Không dùng COUNT(*) trên mọi dòng log ứng dụng để kiểm thử tính đầy đủ của audit; hãy đếm theo eventId hoặc theo danh sách hành động cần ghi.

## 14. Những lỗi thiết kế dễ gặp

### Chỉ gắn marker AUDIT rồi dùng chung appender

Marker chỉ là metadata; nếu không có filter/routing tương ứng hoặc sink riêng, log vẫn có thể nằm trong application.log. Với nhiều developer, người quên marker có thể làm thất lạc audit bắt buộc. Nên có API chuyên dụng và kiểm thử ràng buộc.

### Đã có file audit.log nên coi như đáp ứng yêu cầu kiểm toán

Một file có thể bị chỉnh sửa/xóa, mất khi container bị thay, chưa flush khi crash hoặc bị ghi trùng nhiều instance. Cần chính sách truy cập, lưu bền vững, bảo toàn event và tính toàn vẹn tương xứng yêu cầu.

### Đặt additivity=false nhưng quên appender

Logger audit dừng ở chính nhánh của nó. Nếu không gắn AUDIT_FILE hoặc appender bị lỗi cấu hình, audit có thể không xuất ở đâu. Phải kiểm thử từng event thực tới đích.

### Đặt additivity=true và vô tình lộ audit qua console chung

Audit có thể đi qua APP_FILE hoặc stdout của root; bản ghi chứa trường nhạy cảm bị xuất thêm vào hệ thống có quyền rộng hơn. Cần kiểm tra cả log cục bộ lẫn collector tập trung, nơi các luồng có thể được nhập trở lại một index.

### Ghi audit trước khi transaction commit

Nếu audit SUCCESS được gửi ra một hệ thống ngoài trước khi transaction nghiệp vụ commit, transaction có thể rollback nhưng chứng cứ vẫn nói thành công. Ghi outbox trong cùng transaction hoặc thiết kế rõ hai loại ATTEMPT và COMMITTED_OUTCOME.

### Dùng correlationId làm eventId

Một request có thể tạo nhiều hành động audit, vì thế dùng cùng correlationId làm khóa duy nhất sẽ ghi đè hoặc bỏ mất event. eventId định danh mỗi sự kiện; correlationId dùng để liên kết các sự kiện cùng luồng.

### Dùng log level để quyết định audit cần hay không

Một hành động quan trọng có thể là SUCCESS ở mức INFO; một stack trace ERROR kỹ thuật không phải bản ghi audit. Phân loại theo action/eventCode và yêu cầu nghiệp vụ, không theo độ nghiêm trọng của thông báo.

### Chỉ audit sự kiện thành công

Các nỗ lực truy cập bị từ chối, thay đổi quyền thất bại, truy vấn trái phép hoặc thay đổi cấu hình không được phép có thể quan trọng hơn một số thao tác thành công. Định nghĩa rõ event audit bắt buộc cho cả SUCCESS, DENIED và FAILED.

### Ghi payload quá nhiều

Dữ liệu log có thể bị nhân bản qua backup và nhiều hệ thống tìm kiếm. Không ghi nguyên request/response, token, mật khẩu hoặc dữ liệu nhạy cảm; chỉ giữ thông tin tối thiểu đã phân loại.

## 15. Checklist triển khai

- [ ] Có danh mục event code audit và phân biệt audit với application log.
- [ ] Mỗi event có eventId, timestamp, actor đáng tin cậy, action, target và outcome phù hợp.
- [ ] Ứng dụng có AuditService hoặc quy ước phát sự kiện bắt buộc dễ kiểm thử.
- [ ] Logger audit và appender/đích được khai báo riêng; additivity được cấu hình có chủ đích.
- [ ] Đã xác minh event audit không xuất nhầm vào application.log hoặc mất vì filter/level.
- [ ] Log audit có chính sách quyền đọc/ghi/xóa, mã hóa, retention và chống sửa đổi phù hợp.
- [ ] Không ghi secret hoặc dữ liệu cá nhân không cần thiết; có kiểm thử log injection.
- [ ] Khi cần bền vững giao dịch, sử dụng outbox hoặc cơ chế tương đương và dedup bằng eventId.
- [ ] Có cảnh báo độc lập cho lỗi ghi, backlog, retry và event bị trễ.
- [ ] Đã kiểm thử rollback, DENIED, retry, crash, đầy đĩa, mất collector và phục hồi.
- [ ] Có thể tái dựng chuỗi hành động kiểm toán bằng bản ghi đã lưu tại đích.

**Điểm cần nhớ:** Tách log audit đúng nghĩa gồm **phân loại sự kiện**, **định tuyến riêng** và **chính sách bảo toàn/kiểm soát khác biệt**. Logger và appender giúp tách dòng log; khi audit là chứng cứ bắt buộc, cần thêm ghi bền vững, khả năng kiểm tra toàn vẹn và quy trình phục hồi.

## Tài liệu tham khảo

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): phân biệt mục tiêu log, sự kiện bảo mật/audit, trường dữ liệu, thông tin nhạy cảm và bảo vệ log.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html): logger hierarchy và additivity.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): FileAppender, RollingFileAppender và TimeBasedRollingPolicy.
- [Apache Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html): Logger, Root, AppenderRef và additivity.
- [Apache Log4j 2 — Architecture](https://logging.apache.org/log4j/2.x/manual/architecture.html): luồng sự kiện và quy tắc appender inheritance.
- [Oracle Java SE 17 — java.util.logging](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html): logger và handler dùng trong ví dụ chạy độc lập.
