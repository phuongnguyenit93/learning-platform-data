# Tách log lỗi trong Java: routing, phân loại và vận hành

## 1. Tách log lỗi là gì?

Trong hệ thống Java, ứng dụng có thể phát hàng triệu bản ghi **INFO** về hoạt động bình thường, một lượng nhỏ **WARN** về rủi ro có thể phục hồi và các bản ghi **ERROR** hoặc **SEVERE** cho sự cố cần điều tra. Nếu mọi sự kiện được xử lý giống nhau, nhóm vận hành dễ bỏ sót lỗi quan trọng, còn các bản ghi chi tiết sẽ làm tăng chi phí lưu trữ và truy vấn.

**Tách log lỗi (error log separation)** là việc **phân loại và định tuyến những sự kiện lỗi** theo quy tắc có chủ đích, ví dụ ghi lỗi vào một sink riêng, chuyển tới index/stream riêng trong hệ thống quan sát, hoặc tạo luồng cảnh báo. Dữ liệu lỗi vẫn có thể đồng thời tồn tại trong log tổng hợp nếu chính sách cần toàn bộ dòng thời gian xử lý.

Ví dụ:

~~~text
Ứng dụng Java
    |
    +-- INFO, WARN, ERROR --> general log --> collector --> logs-all
    |
    +-- ERROR -----------> error log ----------> logs-error / alert candidate
~~~

Trong sơ đồ, một **ERROR có thể xuất hiện ở cả luồng tổng hợp và luồng lỗi**. Đây là cách phân luồng có chủ đích, không nhất thiết là lỗi ghi trùng. Cần biết rõ mỗi tuyến đích và quy tắc truy vấn/đếm để không đếm một sự cố hai lần.

Tách log lỗi không đồng nghĩa với **bắt tất cả exception rồi ghi ERROR**, cũng không tự bảo đảm phát hiện sự cố. Chất lượng kết quả phụ thuộc vào việc phân loại đúng, giữ đủ ngữ cảnh, quản lý exception, collector và chính sách cảnh báo.

## 2. Phân biệt ERROR, WARN và sự kiện nghiệp vụ

Trước khi viết filter, phải trả lời câu hỏi: **sự kiện nào thực sự thuộc luồng lỗi?**

| Sự kiện | Cách đánh giá điển hình | Điều cần chú ý |
| --- | --- | --- |
| Request xử lý thành công | INFO hoặc không ghi từng request | Có thể tổng hợp bằng access log/metrics |
| Người dùng gửi dữ liệu không hợp lệ | INFO/WARN tùy policy, không mặc định ERROR | HTTP 400/422 có thể là kết quả dự kiến |
| Timeout ở dependency và sẽ retry | WARN nếu ứng dụng còn phục hồi | Chỉ ERROR khi thao tác thực sự thất bại theo hợp đồng |
| Một attempt thất bại, nhưng job retry thành công | WARN cho attempt thất bại; INFO cho kết quả cuối | Giữ attemptId để phân biệt |
| Job thất bại sau khi hết retry | ERROR | Kèm jobId, loại lỗi, stack trace cần thiết |
| Lỗi cấu hình khiến service không khởi động | ERROR/SEVERE | Cần rõ tên cấu hình, tránh in secret |
| Đăng nhập sai mật khẩu | Event bảo mật theo chính sách | Không đưa mật khẩu/token vào log |
| Sự kiện audit bắt buộc | Luồng audit riêng, không chỉ dựa level ERROR | Có yêu cầu lưu giữ/toàn vẹn riêng |

**HTTP status không quyết định trực tiếp log level.** Một lỗi 404 thông thường có thể là sự kiện dự kiến; một HTTP 200 nhưng ghi sai dữ liệu có thể là sự cố nghiêm trọng. Hãy đánh giá theo **tác động, khả năng phục hồi và nhu cầu hành động của người vận hành**.

Cũng cần phân biệt **lỗi nghiệp vụ** (ví dụ đơn hàng không đủ hàng tồn kho theo quy tắc hợp lệ) với **lỗi kỹ thuật** (mất kết nối database, không thể commit transaction). Hai loại sự kiện thường có mức độ, cách xử lý và chính sách cảnh báo khác nhau.

## 3. Các chiến lược tách lỗi

Có ba chiều phân loại thường gặp:

1. **Theo mức độ nghiêm trọng:** WARN trở lên, ERROR trở lên, hoặc chỉ đúng mức ERROR/SEVERE.
2. **Theo nguồn sự kiện:** package/logger, module, service, worker hoặc loại nghiệp vụ như payment, ingestion, scheduled jobs.
3. **Theo trường ngữ nghĩa:** errorCode, exceptionType, eventName, outcome, retryable, tenant hoặc hệ thống phụ thuộc.

Các nơi nhận có thể là console stdout/stderr, file riêng, queue/broker, collector route, index riêng hoặc alert pipeline. Một quy tắc tách log tốt thường giữ một **general stream** để xem toàn bộ câu chuyện, rồi có một **error stream** để tìm nhanh sự cố và phục vụ vận hành.

So sánh:

| Kiểu routing | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Chỉ lưu ERROR trong file riêng | Dễ tìm lỗi, ít volume | Mất ngữ cảnh trước/sau nếu không có general log |
| Lưu tất cả trong general và nhân ERROR sang error sink | Điều tra được toàn tuyến và lọc lỗi nhanh | Có hai bản sao; cần hiểu cách tính ingestion/retention |
| Chỉ một JSON stream, collector tách theo level/event | Quy tắc tập trung, dễ áp dụng trong container | Phụ thuộc parser, schema và tuyến collector |
| Tách theo logger/package | Khoanh vùng một thư viện hoặc nhóm chức năng | Có thể bỏ sót lỗi phát từ logger khác |
| Tách theo errorCode/exceptionType | Truy vấn đúng nhóm sự cố nghiệp vụ | Cần chuẩn hóa field và kiểm tra ngoại lệ chưa phân loại |

Không nên bật một filter quá rộng chỉ vì muốn “thấy mọi lỗi”. **WARN không đồng nghĩa ERROR** và **lỗi cần audit không đồng nghĩa lỗi chẩn đoán**.

## 4. Hiểu các thành phần routing trong Java

### 4.1. Java Util Logging (JUL)

JDK cung cấp **java.util.logging**, gồm Logger, Level, Handler, Formatter và Filter. Trong JUL, sự kiện đi qua ngưỡng của logger rồi đến các handler được gắn. Từng handler có **level** và có thể có **Filter** riêng.

Ví dụ: logger ở INFO, console handler ở INFO và file handler ở SEVERE thì bản ghi INFO/WARNING/SEVERE có thể ra console, nhưng chỉ SEVERE trở lên vào file. Đây là tách theo ngưỡng; tùy nhu cầu có thể dùng Filter để áp thêm tiêu chí cho các event cụ thể.

### 4.2. SLF4J + Logback

SLF4J là logging API; Logback là một provider/implementation thường gặp. Trong Logback, **Logger** quyết định mức sự kiện được tạo, **Appender** quyết định nơi ghi, và **Filter** quyết định sự kiện được một appender chấp nhận, từ chối hoặc tiếp tục đánh giá.

Hai filter rất dễ nhầm:

- **ThresholdFilter:** nhận các sự kiện đạt ngưỡng trở lên, ví dụ WARN + ERROR khi threshold là WARN.
- **LevelFilter:** kiểm tra **đúng một level**, ví dụ chỉ ERROR; cấu hình onMatch/onMismatch điều khiển ACCEPT/DENY/NEUTRAL.

**Root logger ở WARN sẽ chặn INFO trước khi INFO đến appender.** Việc thêm INFO appender không thể hồi phục một event đã bị logger loại bỏ. Vì thế cần suy nghĩ về cả **logger level** lẫn **appender filter**.

### 4.3. Log4j 2 hoặc framework khác

Log4j 2 có cấu trúc appender/filter và routing riêng; Spring Boot có thể điều phối provider và cấu hình level từ properties. Các ý tưởng phân tách vẫn giống nhau, nhưng **không sao chép XML của Logback sang Log4j 2 hoặc JUL**. Luôn xác định runtime đang dùng implementation nào.

## 5. Ví dụ Java 17 chạy độc lập: JUL ghi riêng SEVERE

Ví dụ sau chỉ dùng JDK 17. Ta tạo một Logger, một ConsoleHandler nhận từ INFO trở lên và một FileHandler chỉ nhận **SEVERE**. Để kết quả dễ kiểm tra, formatter chỉ ghi level và message, còn file được tạo trong thư mục tạm của hệ điều hành.

Tạo file **ErrorRoutingDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ErrorRoutingDemo {
    private static final Formatter FORMAT = new Formatter() {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName()
                    + " " + formatMessage(record)
                    + System.lineSeparator();
        }
    };

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("error-routing-");
        Path errorPath = dir.resolve("error.log");

        Logger logger = Logger.getLogger("example.error.routing");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        ConsoleHandler general = new ConsoleHandler();
        general.setLevel(Level.INFO);
        general.setFormatter(FORMAT);

        FileHandler errors = new FileHandler(errorPath.toString(), false);
        errors.setLevel(Level.SEVERE);
        errors.setFormatter(FORMAT);
        errors.setEncoding(StandardCharsets.UTF_8.name());

        logger.addHandler(general);
        logger.addHandler(errors);

        try {
            logger.info("application_started");
            logger.warning("retry_scheduled");
            logger.severe("payment_failed");
        } finally {
            logger.removeHandler(general);
            logger.removeHandler(errors);
            general.close();
            errors.close();
        }

        List<String> lines =
                Files.readAllLines(errorPath, StandardCharsets.UTF_8);
        System.out.println("error-file-records=" + lines.size());
        System.out.println("error-file-first=" + lines.get(0));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ErrorRoutingDemo.java
java ErrorRoutingDemo
~~~

**stderr** do ConsoleHandler tạo ra:

~~~text
INFO application_started
WARNING retry_scheduled
SEVERE payment_failed
~~~

**stdout** do hai lệnh System.out.println ở cuối chương trình:

~~~text
error-file-records=1
error-file-first=SEVERE payment_failed
~~~

File **error.log** chỉ có dòng:

~~~text
SEVERE payment_failed
~~~

Cách hoạt động:

1. Logger có level INFO nên cả INFO, WARNING và SEVERE được tạo.
2. ConsoleHandler nhận cả ba sự kiện và mặc định ghi ra **stderr**.
3. FileHandler có level SEVERE nên loại INFO và WARNING; chỉ ghi payment_failed. **SEVERE là mức của JUL, tương ứng về ý nghĩa với lỗi nghiêm trọng, không phải tên ERROR trong SLF4J.**
4. **setUseParentHandlers(false)** ngăn log tiếp tục đi lên parent logger, tránh log console bị ghi thêm qua root handler.
5. Việc remove và close handler trong finally giúp flush/đóng file trước khi đọc. Thư mục tạm được giữ để có thể kiểm tra file sau khi chạy; trong ứng dụng thật cần lifecycle/retention riêng.
6. Đầu ra stdout và stderr là **hai luồng riêng**; nếu terminal hoặc môi trường thu thập trộn hai luồng, thứ tự hiển thị tương đối của chúng không phải hợp đồng của chương trình.

Đây là ví dụ về routing của JUL. Trong production, không tạo FileHandler mới cho mỗi request: khởi tạo handler trong cấu hình ứng dụng, sử dụng lại xuyên suốt vòng đời và quản lý shutdown, rotation, permission.

## 6. Logback: giữ general log và ghi thêm ERROR vào file

Với ứng dụng thực sự dùng SLF4J + Logback, ta có thể ghi INFO/WARN/ERROR ra console và **chỉ ERROR** sang file riêng. Ví dụ file **logback.xml**:

~~~xml
<configuration>
    <appender name="GENERAL" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger{36} trace=%X{traceId} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ERROR_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/error.log</file>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/error.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>14</maxHistory>
            <totalSizeCap>2GB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger{36} trace=%X{traceId} - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="GENERAL"/>
        <appender-ref ref="ERROR_FILE"/>
    </root>
</configuration>
~~~

Điều kiện: Logback phải có trong runtime, thư mục logs/ phải có thể tạo/ghi, và ứng dụng cần đường lưu file bền vững hoặc cơ chế chuyển file. Cú pháp appender/rolling policy phải phù hợp phiên bản Logback đang dùng.

**Kết quả routing:**

| Level | GENERAL (console) | ERROR_FILE |
| --- | --- | --- |
| DEBUG | Không | Không |
| INFO | Có | Không |
| WARN | Có | Không |
| ERROR | Có | Có |

Giải thích:

- **root=INFO** phát sinh INFO trở lên.
- **GENERAL** không có filter nên nhận mọi sự kiện đã đi qua root.
- **LevelFilter(ERROR)** trên ERROR_FILE chỉ nhận chính xác ERROR. Nếu thay bằng **ThresholdFilter** với threshold WARN, file sẽ nhận WARN **và** ERROR.
- ERROR có hai bản sao ở **hai sink có chủ đích**. Nếu collector lấy cả console và file, cần đánh dấu tuyến hoặc chọn một nguồn ingestion để tránh đếm đôi.
- **%ex** in stack trace exception nếu có. Khi pattern vừa có %msg%n vừa có %ex, ứng dụng phải kiểm thử format thực tế để bảo đảm stack trace hiển thị rõ và không bị nhân đôi. Chỉ ghi stack trace khi log event thực sự có Throwable.
- Pattern này là **text**, chưa phải JSON; MDC **traceId** sẽ trống nếu tracing context chưa được cấu hình.
- **maxHistory=14** và **totalSizeCap=2GB** chỉ là giá trị minh họa về lưu trữ file cục bộ. Chi phí và thời hạn lưu ở backend tập trung được quản lý độc lập.

Nếu chỉ muốn ERROR trong file, không cần INFO/WARN trong file, **LevelFilter** là lựa chọn rõ ràng. Nếu muốn **WARN trở lên**, dùng filter phù hợp và mô tả lại contract lưu giữ/alert.

### Cách gọi logger đúng cách

Ví dụ với SLF4J, ở boundary xử lý lỗi:

~~~java
try {
    processPayment(jobId);
} catch (PaymentGatewayException e) {
    logger.error("event=payment_processing_failed jobId={}", jobId, e);
    throw e;
}
~~~

Đây là **đoạn tích hợp**, yêu cầu logger, exception và phương thức nghiệp vụ do ứng dụng định nghĩa. SLF4J nhận Throwable ở đối số cuối và đưa stack trace cho provider. Khi tầng trên đã ghi lỗi đầy đủ, tầng dưới hoặc tầng trên khác nên tránh ghi lại cùng exception mà không có ngữ cảnh mới. **Không log rồi bỏ qua exception** nếu hành vi nghiệp vụ đòi hỏi rollback/retry.

## 7. Chỉ muốn tách WARN và ERROR thì sao?

Các chính sách có thể khác nhau theo yêu cầu vận hành:

- **ERROR-only:** dùng **LevelFilter(ERROR)**; tập trung các thất bại thật sự, volume nhỏ.
- **WARN+ERROR:** dùng **ThresholdFilter(WARN)**; chứa cả cảnh báo retry/degradation nhưng cần lọc cảnh báo trùng.
- **Security/authentication events:** tách theo eventCode/logger hoặc kênh sự kiện chuyên biệt; nhiều sự kiện đáng theo dõi có thể được ghi INFO/WARN chứ không phải ERROR.
- **Audit events:** định tuyến vào cơ chế audit có yêu cầu toàn vẹn và retention phù hợp, không phụ thuộc vào việc ai đó đổi root logger sang WARN.

Nếu một package tạo quá nhiều WARN nhưng các lỗi nghiệp vụ quan trọng lại đến từ package khác, filter theo level vẫn quá rộng. Khi đó có thể chuẩn hóa **event code**, **marker** hoặc field JSON và cấu hình routing tại collector. Không dựa vào việc message có chứa chuỗi "error" vì message từ nhiều thành phần có thể viết khác nhau.

## 8. Tách tại console hay collector trong container?

Với container/Kubernetes, thường thuận tiện hơn khi ứng dụng xuất **một structured log stream** rồi collector tách dựa trên field **level** và **event**. Ví dụ ý tưởng routing:

~~~text
stdout/stderr của Java service
    |
    v
Log collector
    |
    +-- mọi event có schema hợp lệ ---------> general index
    |
    +-- level = ERROR ----------------------> error index/route
    |
    +-- event thuộc security/audit policy --> kênh riêng theo hợp đồng
~~~

Chỉ một dòng JSON từ ứng dụng có thể được collector đưa vào nhiều đích. Chính sách routing nên được version hóa và kiểm thử; nếu collector parse level sai, lỗi có thể không đến index dành cho error.

**stdout/stderr không phải bộ phân loại severity tự động.** JUL ConsoleHandler mặc định ghi stderr cả INFO. Trong Logback, ConsoleAppender có thể được chọn target System.out hoặc System.err và filter theo level, nhưng muốn INFO/WARN ra stdout và ERROR ra stderr phải cấu hình rõ **cả hai tuyến và filter loại trừ**, không chỉ tạo hai ConsoleAppender rồi gắn tất cả vào root.

Nếu Kubernetes platform đã thu thập cả stdout lẫn stderr và thêm metadata service/pod, nên cân nhắc phân loại ở collector để tránh tạo file cục bộ trong container. Nếu yêu cầu file error riêng vì quy định hoặc vận hành, phải thiết kế persistent storage, rotation và vận chuyển, không giả định file trong container tồn tại lâu.

## 9. Hiểu additivity và tránh log bị nhân đôi ngoài ý muốn

Trong Logback, logger con thường có **additivity=true**: event đã được xử lý bởi appender gắn trực tiếp vào logger con sẽ còn đi lên ancestor/root. Ví dụ cùng một ConsoleAppender được gắn ở package và root có thể dẫn đến một event bị ghi hai lần vào cùng console.

Dấu hiệu lỗi: hai dòng giống hệt nhau, cùng timestamp/logger/message, xuất hiện ngay cạnh nhau trong **cùng sink**. Đây khác với chính sách cố ý ghi ERROR ở **GENERAL và ERROR_FILE**.

Để sửa:

1. Kiểm tra **logger hierarchy** và appender-ref ở từng tầng.
2. Ưu tiên gắn các appender dùng chung một lần ở root nếu phù hợp.
3. Nếu cần **additivity=false** cho logger riêng, phải gắn đủ appender cần thiết vào logger đó. Bật false mà quên general appender có thể khiến log biến mất khỏi luồng tổng hợp.
4. Kiểm tra collector có đọc đồng thời stdout và file ghi cùng một sự kiện hay không.
5. Với JUL, cần hiểu **setUseParentHandlers(false)** cũng ảnh hưởng propagation lên handler của parent.

Bài kiểm tra có giá trị: phát đúng một ERROR rồi xác minh **một** bản ghi ở general sink và **một** bản ghi ở error sink; không có bản sao ngoài dự kiến trong cùng sink.

## 10. Thiết kế schema để truy vấn lỗi

Một bản ghi ERROR nên có thông tin đủ để người xử lý tìm nguyên nhân mà không phải dump toàn bộ request:

| Field | Mục đích |
| --- | --- |
| timestamp | Thời điểm xảy ra sự kiện, có timezone rõ ràng |
| level | ERROR hoặc severity chuẩn hóa |
| service, environment, version, instanceId | Khoanh vùng deployment và JVM/container |
| logger | Nơi tạo sự kiện |
| event, errorCode, outcome | Định danh loại lỗi ổn định |
| message | Tóm tắt có ý nghĩa, tránh dữ liệu nhạy cảm |
| exception.type, exception.stacktrace | Nguyên nhân kỹ thuật khi có Throwable |
| traceId, spanId, requestId | Liên kết sang request và distributed trace |
| jobId, attemptNo | Liên kết job và lần thử |
| dependency | Hệ thống phụ thuộc bị ảnh hưởng khi liên quan |

Ví dụ JSON minh họa:

~~~json
{
  "timestamp": "2026-11-10T02:40:00Z",
  "level": "ERROR",
  "service": "order-service",
  "environment": "production",
  "instanceId": "order-pod-4",
  "event": "order_persist_failed",
  "errorCode": "DB_WRITE_FAILED",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "jobId": "order-582",
  "attemptNo": 3,
  "exception": {
    "type": "java.sql.SQLTransientConnectionException",
    "message": "Connection unavailable"
  }
}
~~~

JSON này là **dữ liệu minh họa**, không phải output tự sinh từ cấu hình text Logback ở mục 6. Nếu cần lưu stack trace như một field JSON, hãy dùng JSON encoder/formatter thực sự, kiểm tra escaping và giới hạn kích thước trên collector.

**errorCode nên ổn định**, tránh đặt nguyên exception message (chứa ID ngẫu nhiên hoặc hostname) làm tên loại lỗi. Nhờ thế có thể tổng hợp theo lỗi gốc và giảm alert cardinality.

Nếu log text có stack trace nhiều dòng, collector phải hỗ trợ multiline hoặc framing phù hợp. Nếu không, mỗi dòng stack có thể bị biến thành một event riêng, khiến bộ đếm lỗi sai và truy vấn mất ngữ cảnh.

## 11. Giữ context khi xử lý đa luồng

Trong Java, thread pool tái sử dụng thread, còn CompletableFuture hoặc callback có thể chuyển giữa các thread. Các trường từ **MDC** hoặc ThreadLocal ở caller không tự động được mang sang task khác hoặc service khác.

Đoạn mã dưới đây minh họa scope MDC với SLF4J, **không phải chương trình JDK độc lập**:

~~~java
import org.slf4j.MDC;

void handleJob(String jobId) {
    try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("jobId", jobId)) {
        processJob();
    }
}
~~~

MDC cung cấp các field cho logger trong scope. Khi kết thúc phải khôi phục/xóa đúng key để job kế tiếp trên cùng thread không thừa hưởng jobId cũ. Nếu chuyển executor, dùng cơ chế **capture → activate → restore** phù hợp với framework và tracing SDK; tránh phụ thuộc InheritableThreadLocal trong thread pool.

**TraceId không tự xuất hiện vì pattern có %X{traceId}.** Cần tracing integration hoặc code thiết lập MDC, và khi đi qua HTTP/message broker cần inject/extract context. Copy một chuỗi traceId chỉ hỗ trợ log correlation; tạo cây span còn cần tracer và propagator.

Việc tách log lỗi không thay thế context propagation. Nếu ERROR_FILE có lỗi nhưng không có requestId/jobId, điều tra lỗi trong tải cao vẫn rất khó.

## 12. Xử lý exception và chính sách log một lần

Một chuỗi gọi service thường có nhiều tầng:

~~~text
HTTP Controller -> Service -> Repository -> Database
~~~

Khi Repository ném exception, không phải tầng nào cũng nên ghi nguyên stack trace. Nếu Repository ghi ERROR rồi Service ghi ERROR rồi Controller lại ghi ERROR với cùng nguyên nhân, collector có thể đếm thành ba lỗi dù một request chỉ thất bại một lần.

Một chính sách hợp lý là:

- Ở tầng thấp, **thêm ngữ cảnh bằng exception có cause** khi cần rồi ném tiếp; chỉ log tại đó nếu sự kiện thực sự cần được quan sát độc lập.
- Ở **boundary xử lý** (HTTP error handler, consumer job boundary, scheduler job handler), ghi lỗi cuối cùng một lần, kèm requestId/jobId, errorCode và throwable.
- Nếu lỗi được xử lý để retry, ghi WARN với attemptNo khi appropriate; chỉ ghi ERROR nếu thao tác cuối cùng thất bại theo hợp đồng.
- Nếu một exception được xử lý hoàn toàn và không ảnh hưởng hành vi ngoài dự kiến, cân nhắc INFO/WARN thay vì tự động ERROR.
- Không nuốt exception chỉ để tránh log. Phải giữ luồng rollback, retry, response hoặc dead-letter đúng theo semantics.

**Không đồng nhất số dòng ERROR với số incident.** Một sự cố có thể làm hàng nghìn request thất bại; cùng một lỗi có thể bị ghi ở nhiều worker/retry. Hệ cảnh báo cần nhóm theo event/errorCode, service, dependency và cửa sổ thời gian, không tạo một cảnh báo cho mỗi dòng.

## 13. Async logging, backpressure và bảo toàn lỗi

Một số triển khai dùng **AsyncAppender** hoặc queue để giảm I/O trên request thread. Khi queue đầy, log có thể bị trì hoãn, block thread ứng dụng hoặc bị drop tùy provider và cấu hình.

| Trạng thái | Điều có thể xảy ra | Điều cần kiểm tra |
| --- | --- | --- |
| Queue rỗng/còn chỗ | Event được enqueue và ghi sau | Latency, thứ tự tương đối, collector |
| Queue gần đầy | Đệm tăng, pressure lên heap | Queue metrics, logging rate |
| Queue đầy | Producer bị chặn hoặc event bị bỏ | Drop policy và mức đảm bảo với ERROR |
| Process bị kill đột ngột | Event chưa flush có thể mất | Graceful shutdown, crash scenarios |
| Remote sink mất kết nối | Retry/buffering có thể tăng | Timeout, giới hạn memory, mất log |

Một tuyến ERROR riêng chưa đủ để đảm bảo độ bền nếu cũng nằm sau async queue có thể drop. Với error event quan trọng, phải xác định chính sách queue và thiết kế nguồn ghi phù hợp. **Audit hoặc dữ liệu giao dịch bắt buộc** không nên dựa duy nhất vào diagnostic logging “best effort”; sử dụng cơ chế lưu trữ/xác nhận riêng khi yêu cầu tính toàn vẹn.

Không gửi đồng bộ từng ERROR qua network một cách thiếu kiểm soát: một backend log bị lỗi có thể khiến nhiều request thất bại dây chuyền. Phải cô lập failure domain của logging pipeline.

## 14. Bảo mật, riêng tư và retention

**Tách ERROR vào file riêng không làm nó tự an toàn hơn.** Exception message có thể chứa JDBC URL, tên bảng, tham số truy vấn, token, địa chỉ nội bộ, thông tin khách hàng hoặc dữ liệu người dùng.

Các nguyên tắc cần áp dụng:

1. **Không log password, API key, access token, Authorization header, cookie và dữ liệu thanh toán chưa lọc.**
2. **Không dump toàn bộ request/response** chỉ vì xảy ra exception; ghi errorCode và thông tin tối thiểu.
3. **Xác thực/escape dữ liệu đầu vào** trước khi đưa vào message, nhất là ký tự xuống dòng gây log injection.
4. **Giới hạn quyền đọc** file error/index và việc export dashboard.
5. **Quy định retention** theo mục đích, pháp lý, loại dữ liệu và giới hạn storage; có chính sách xóa bản sao/archive.
6. **Không sử dụng traceId, requestId hoặc jobId làm metric label** có cardinality cao; những ID này phù hợp trong log và trace.

Nếu sử dụng **RollingFileAppender**, phải đặt giới hạn thời gian/dung lượng cho file và kiểm tra khi disk đầy. Nếu chuyển lỗi sang error index, phải xác định retention và quota riêng; có thể lỗi bùng phát khiến chính tuyến error tăng mạnh bất thường.

## 15. Cách kiểm thử routing trước khi lên production

Định nghĩa ma trận sự kiện thử nghiệm:

| Event phát ra | General sink | Error sink | Kỳ vọng |
| --- | --- | --- | --- |
| DEBUG trace nội bộ | Không (root INFO) | Không | Đúng threshold |
| INFO application_started | 1 | 0 | Không đẩy sự kiện bình thường vào error |
| WARN dependency_retry | 1 | 0 | Với chính sách ERROR-only |
| ERROR order_persist_failed | 1 | 1 | Một bản sao tại mỗi sink được phép |
| ERROR với Throwable | 1 | 1 | Có stack trace/ngữ cảnh, không bị cắt hoặc đếm thừa |

Sau đó kiểm tra các tình huống:

- **Provider/config:** xác minh đúng JUL/Logback/Log4j 2, file cấu hình được nạp và level hiệu lực.
- **Additivity:** cùng một event không xuất hiện nhiều lần trong **cùng sink** do gắn appender trùng.
- **Structured output:** nếu dùng JSON, xác minh parser đọc được Unicode, dấu ngoặc kép, xuống dòng và exception.
- **Concurrency:** nhiều thread/worker gây lỗi đồng thời nhưng các traceId/jobId không bị trộn.
- **Collector failure:** khi collector/remote endpoint ngừng, ứng dụng phản ứng theo chính sách queue/backpressure; đo dropped events.
- **Disk pressure:** nếu ghi file, thử rotation, cleanup, permission và quota ở staging.
- **Security:** đưa token giả và ký tự điều khiển vào dữ liệu thử để xác nhận không lộ credential.
- **Alert:** nhiều lần retry thuộc cùng incident không tạo bão cảnh báo ngoài mong muốn; INFO/WARN thông thường không tạo alert ERROR-only.
- **Shutdown:** xác minh flush/close handler/appender và lượng log có thể mất khi hard kill.

### Quy trình khi không thấy ERROR trong error sink

1. Kiểm tra ứng dụng **có tạo ERROR/SEVERE** ở runtime hay không.
2. Xác nhận **logger effective level** không chặn event trước appender/handler.
3. Kiểm tra **filter**: LevelFilter có match đúng ERROR không; ThresholdFilter có đang loại event mong muốn không.
4. Xác minh appender đã được tham chiếu, file path/quyền ghi/dung lượng hợp lệ và handler không bị đóng sớm.
5. Nếu console/file đã có sự kiện nhưng dashboard không thấy, điều tra **collector → parser → transport → index**.
6. Kiểm tra data schema và tên level được normalized; ERROR của SLF4J và SEVERE của JUL có thể cần ánh xạ khi đi qua backend chung.

Không vội tăng DEBUG toàn bộ ứng dụng để sửa lỗi routing; đó là hai vấn đề khác nhau.

## 16. Checklist thiết kế và vận hành

| Hạng mục | Tiêu chí xác nhận |
| --- | --- |
| Định nghĩa lỗi | Phân biệt ERROR, WARN, retryable failure, business rejection và audit |
| Logger level | Mức logger cho phép sự kiện cần route đi tới handler/appender |
| Filter | Quy tắc ERROR-only hay WARN+ được viết và kiểm thử rõ |
| General sink | Giữ đủ timeline để điều tra |
| Error sink | Chứa đúng bản ghi mong muốn, không thừa INFO/WARN |
| Additivity | Không phát sinh duplicate ngoài ý muốn |
| Context | Có service, instance, errorCode, traceId/jobId và Throwable khi thích hợp |
| Production format | JSON hoặc text được chọn có lý do; parser/collector tương thích |
| Reliability | Biết queue/drop/block/flush policy |
| Security | Không lộ bí mật; phân quyền và retention đúng |
| Capacity | Rotation, size cap, quota, collector rate và alert cardinality được quản lý |
| Verification | Đã kiểm tra dữ liệu thực trên cả sink tổng hợp và sink lỗi |

**Điểm cần nhớ:** tách log lỗi là một bài toán **phân loại và định tuyến sự kiện**. Trong Java có thể thực hiện tại logger/handler/appender hoặc ở collector, nhưng luôn phải đảm bảo level đúng, event không bị đếm thừa, exception và context còn nguyên, dữ liệu nhạy cảm được bảo vệ, và tuyến lỗi vẫn hoạt động khi production có tải hoặc gặp sự cố.