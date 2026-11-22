# Cấu hình logging cho môi trường production trong Java

## 1. Mục tiêu và phạm vi

Ở môi trường phát triển, có thể bật nhiều log để quan sát chi tiết chương trình. Trong **production**, cấu hình logging còn phải đảm bảo hiệu năng, bảo mật, lưu giữ, khả năng truy vấn và tính ổn định của dịch vụ. Một hệ thống nhiều JVM hoặc container có thể tiếp nhận lượng lớn request song song; log không được thiết kế tốt sẽ khó tìm kiếm, gây tốn dung lượng hoặc trực tiếp làm chậm ứng dụng.

**Cấu hình production** là tập hợp các quyết định về **sự kiện cần ghi, mức độ chi tiết, định dạng, đầu ra, cách thu thập và lưu giữ, xử lý quá tải, bảo vệ dữ liệu và điều chỉnh cấu hình khi vận hành**.

Một cấu hình tốt cần giúp người vận hành trả lời: sự cố bắt đầu lúc nào, xảy ra tại service/instance nào, request hoặc task nào liên quan, có exception và nguyên nhân gốc gì, log đã đến backend thu thập chưa, và có thể tăng chi tiết ở đúng thành phần khi cần hay không.

Không có một file cấu hình chung cho mọi môi trường. Dịch vụ chạy trong container với bộ thu thập stdout khác tiến trình Java trên VM ghi file cục bộ; sự kiện audit có yêu cầu khác log chẩn đoán. Các nguyên tắc dưới đây cho thấy cách đưa ra quyết định và xác minh cấu hình thực tế.

## 2. Xác định logging stack đang chạy

Trong Java cần tách ba lớp:

| Lớp | Ví dụ | Vai trò |
| --- | --- | --- |
| **Logging API** | java.util.logging (JUL), SLF4J | Ứng dụng gọi các phương thức ghi log |
| **Implementation / provider** | JUL Handler/Formatter, Logback, Log4j 2 | Lọc level, định dạng, chuyển log đến destination |
| **Collector / storage** | Agent của platform, OpenTelemetry Collector, Fluent Bit, Loki hoặc hệ thống tương đương | Nhận, vận chuyển, xử lý, lưu trữ và truy vấn log |

Ví dụ một ứng dụng gọi **org.slf4j.Logger.info(...)**. File **logback.xml** chỉ có hiệu lực khi Logback đang là provider thực tế. Nếu ứng dụng chạy với JUL hoặc Log4j 2, cấu hình và cơ chế nạp có thể khác. Một số framework như Spring Boot còn có lớp điều phối mức log và lựa chọn file cấu hình. Phải xác nhận **effective configuration** trên runtime thay vì suy đoán từ tên file trong repository.

Nên quản lý cấu hình theo môi trường bằng file được triển khai cùng ứng dụng, system property, environment variable hoặc cấu hình ngoài được kiểm soát. Các tùy chọn này không tự có cùng cú pháp trên mọi framework.

| Môi trường | Mức log gợi ý | Mục tiêu |
| --- | --- | --- |
| Local | DEBUG theo nhu cầu | Điều tra code và luồng xử lý khi phát triển |
| Staging | INFO; DEBUG tạm thời theo package | Kiểm tra logic và chuẩn bị vận hành |
| Production | INFO hoặc WARN theo loại service | Ghi sự kiện quan trọng, kiểm soát volume |
| Production incident | DEBUG trong phạm vi và thời gian giới hạn | Thu thêm dữ kiện rồi hoàn nguyên |

Đây là gợi ý chính sách, không phải mặc định do JDK quy định. Có dịch vụ cần INFO cho event nghiệp vụ; có thư viện tạo quá nhiều INFO nên cần nâng threshold của riêng namespace đó.

## 3. Thiết kế mức log theo ý nghĩa sự kiện

Các stack như SLF4J/Logback thường dùng **TRACE, DEBUG, INFO, WARN, ERROR**. JUL có **FINEST, FINER, FINE, CONFIG, INFO, WARNING, SEVERE**. Không thể giả định những bộ mức này tương đương tuyệt đối trong mọi thư viện.

| Tình huống | Level thường phù hợp | Lưu ý |
| --- | --- | --- |
| Biến nội bộ, đường đi của thuật toán, chi tiết cache | TRACE/DEBUG | Thường không bật mặc định ở production |
| Startup, shutdown, job hoàn tất, trạng thái hệ thống | INFO | Ghi theo sự kiện có giá trị, tránh lặp |
| Dependency chậm, retry, bất thường còn phục hồi được | WARN | Kèm giới hạn và ngữ cảnh để điều tra |
| Thao tác thất bại cần xử lý | ERROR | Ghi stack trace khi có lỗi thực sự |
| Sự kiện audit bắt buộc | Kênh audit theo chính sách | Không phụ thuộc duy nhất vào ngưỡng log chẩn đoán |

Một response 4xx do validation không nhất thiết phải ERROR nếu đó là hành vi dự kiến. Ngược lại, một lỗi dữ liệu bị bỏ qua có thể phải được ghi ERROR. Level nên thể hiện **mức độ hành động vận hành**, không đơn thuần là tên exception.

Tránh ghi trùng stack trace qua nhiều tầng: tầng thấp log lỗi rồi ném exception, tầng cao lại log nguyên lỗi khiến hệ thống có nhiều bản sao mà không thêm ngữ cảnh. Chọn boundary ghi lỗi phù hợp, giữ các thông tin như operation, errorCode, requestId và stack trace cần thiết.

Không ghi INFO ở mỗi vòng lặp hoặc mỗi bản ghi dữ liệu khi số lượng rất lớn. Dùng thống kê theo batch, metrics, hoặc sự kiện tổng kết để tránh tăng volume tuyến tính không cần thiết.

## 4. Đầu ra và pipeline thu thập

### 4.1. stdout/stderr trong container

Với ứng dụng chạy dưới container orchestrator, một lựa chọn thường thuận tiện là **ghi log ra stdout/stderr** rồi để runtime/agent của nền tảng thu thập và chuyển tới backend tập trung. Việc log xuất hiện trong container **không đảm bảo** nó đã được lưu dài hạn; chính sách transport, storage và retention cần cấu hình riêng.

Cần xác minh collector có đọc cả hai luồng không, parser xử lý multiline stack trace ra sao, backend giữ dữ liệu sau khi pod bị xóa thế nào, và tình huống collector quá tải dẫn tới drop hay block ứng dụng.

Lưu ý: stderr không đồng nghĩa chỉ chứa ERROR. Ví dụ **java.util.logging.ConsoleHandler** mặc định ghi vào stderr kể cả khi sự kiện ở mức INFO.

### 4.2. File cục bộ

Trên VM hoặc môi trường cần lưu file tại host, có thể dùng FileHandler/RollingFileAppender. Khi đó phải thiết kế đường dẫn và quyền ghi, rotation theo dung lượng/thời gian, nén, retention và chuyển dữ liệu sang kho log. Không để một file tăng không giới hạn.

Nếu bật đồng thời appender console và file, rồi collector đọc cả hai nguồn, có thể tạo log trùng. Nên xác định chính xác tuyến đi của mỗi event trước khi bật nhiều destination.

### 4.3. Gửi log trực tiếp tới remote endpoint

Việc gửi đồng bộ từng log event qua mạng có thể làm tăng latency và buộc ứng dụng phụ thuộc vào logging server. Thông thường nên có ranh giới collector/agent với cơ chế đệm và retry phù hợp. Nếu dùng network appender trực tiếp, cần có timeout, queue, giới hạn bộ nhớ và chính sách khi đích mất kết nối.

Một pipeline tham khảo:

~~~text
Java service
    |
    | Console / local log sink
    v
Container runtime hoặc log agent
    |
    v
Collector / parser / redaction
    |
    v
Backend tìm kiếm + lưu trữ + dashboard
~~~

Ở mỗi bước có thể phát sinh trễ, lỗi, mất log hoặc sự kiện trùng; cần có chỉ số giám sát cho pipeline, không chỉ nhìn số lượng log ứng dụng đã gọi.

## 5. Schema log có cấu trúc

Log dạng JSON hoặc bản ghi có field rõ ràng giúp truy vấn ổn định. Một schema phổ biến gồm:

| Trường | Ý nghĩa |
| --- | --- |
| timestamp | Thời điểm sự kiện, ISO 8601 có offset hoặc UTC |
| level | Mức nghiêm trọng theo policy |
| service, version, environment | Tên dịch vụ, phiên bản và môi trường |
| instanceId | JVM/container/pod phát log |
| logger | Namespace/class tạo bản ghi |
| threadName | Thread đang thực thi |
| traceId, spanId | Liên hệ với distributed trace nếu được cung cấp |
| requestId, correlationId | Liên kết yêu cầu theo hợp đồng ứng dụng |
| taskId, attemptNo | Công việc nền và lần thử |
| event, errorCode, message | Loại sự kiện, mã lỗi và mô tả |
| exception | Loại exception và stack trace đã qua kiểm soát dữ liệu |

Ví dụ JSON hợp lệ để minh họa schema:

~~~json
{
  "timestamp": "2026-11-10T02:40:00.000Z",
  "level": "WARN",
  "service": "billing-service",
  "version": "2.4.1",
  "environment": "production",
  "instanceId": "billing-pod-7",
  "threadName": "http-worker-3",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "event": "downstream_request_slow",
  "dependency": "inventory",
  "durationMs": 820,
  "message": "Dependency latency exceeded warning threshold"
}
~~~

**JSON ví dụ này không tự sinh ra từ JUL hay Logback nếu chưa có JSON formatter/encoder.** Một text pattern như level + message vẫn là text. Với JSON, cần chọn encoder/formatter tương thích phiên bản logging implementation, rồi thử parsing đầu ra thực tế với dấu ngoặc kép, xuống dòng, Unicode và exception.

Định dạng thời gian nên thống nhất giữa các service; UTC thường giúp đối chiếu. Tuy vậy, timestamp giữa các node không hoàn toàn biểu diễn quan hệ nhân quả khi có clock skew. Kết hợp trace/span hoặc task ID để truy vết thay vì chỉ sắp xếp timestamp.

Không sử dụng threadName làm requestId: thread pool có thể tái sử dụng thread, và các callback bất đồng bộ có thể chạy trên thread khác.

## 6. Java 17: cấu hình JUL bằng logging.properties

JDK có sẵn **java.util.logging (JUL)**. Ví dụ sau dùng hoàn toàn Java SE để hiểu việc cấu hình logger và handler thông qua file ngoài chương trình.

Tạo file **ProductionLoggingDemo.java**:

~~~java
import java.util.logging.Logger;

public class ProductionLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ProductionLoggingDemo.class.getName());

    public static void main(String[] args) {
        LOG.info("event=application_started");
        LOG.fine("event=cache_internal_state");
        LOG.warning("event=dependency_degraded");
    }
}
~~~

Tạo file **logging.properties** cùng thư mục:

~~~properties
handlers = java.util.logging.ConsoleHandler
.level = INFO

java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format = %4$s %5$s%6$s%n
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac ProductionLoggingDemo.java
java -Djava.util.logging.config.file=logging.properties ProductionLoggingDemo
~~~

Với JDK/locale dùng tên level tiếng Anh, terminal hiển thị:

~~~text
INFO event=application_started
WARNING event=dependency_degraded
~~~

**ConsoleHandler ghi các dòng này ra stderr, không phải stdout.** Dòng FINE bị lọc do root logger và handler đều có threshold INFO. Trong SimpleFormatter, **%4$s** biểu diễn level, **%5$s** là message, **%6$s** là throwable nếu có, và **%n** là xuống dòng.

Những điểm cần hiểu:

1. JVM đọc system property **java.util.logging.config.file** khi LogManager khởi tạo. Truyền property ngay lúc khởi động, trước khi logging được sử dụng.
2. **.level** điều khiển root logger; **ConsoleHandler.level** lọc ở handler. Một sự kiện phải vượt qua cả hai bộ lọc.
3. Ví dụ cố ý dùng formatter ngắn để kết quả dễ quan sát. Ở production nên bổ sung timestamp, service/instance context và format theo schema.
4. Nếu file không được đọc, JUL có thể dùng cấu hình mặc định. Xác nhận effective behavior bằng log thử nghiệm thay vì chỉ kiểm tra file tồn tại.
5. Cấu hình mức log không yêu cầu sửa từng lệnh **LOG.info** hay **LOG.fine** trong source. Code nên diễn đạt đúng ngữ nghĩa sự kiện; config quyết định sự kiện nào được phát ra.

JUL có các handler và formatter khác Logback; không áp dụng file **logging.properties** cho SLF4J/Logback rồi kỳ vọng kết quả giống nhau.

## 7. Logback production cho ứng dụng dùng SLF4J

Nếu runtime sử dụng **SLF4J + Logback**, file **logback.xml** có thể cấu hình console appender và ngưỡng level. Đây là file XML mẫu; cần Logback có mặt trên classpath.

~~~xml
<configuration scan="false">
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level [%thread] logger=%logger{36} trace=%X{traceId} span=%X{spanId} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.billing.internal" level="WARN" />

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Ở đây:

- **CONSOLE** ghi ra stdout cho collector/container runtime thu thập.
- **root=INFO** là mức chung. Logger **com.example.billing.internal** chỉ phát WARN trở lên.
- **PatternLayoutEncoder** tạo text. Muốn JSON, dùng JSON encoder/layout tương ứng và dependency hợp lệ.
- **%X{traceId}** và **%X{spanId}** chỉ đọc từ MDC khi context đã tồn tại. Pattern không tự tạo trace hay span.
- **scan=false** cho phép ví dụ tránh cơ chế scan cấu hình liên tục; đổi config có thể cần restart hoặc cơ chế reload đã được kiểm chứng.

Đối với Logback độc lập, có thể trỏ tới file ngoài bằng system property:

~~~bash
java -Dlogback.configurationFile=/etc/myapp/logback.xml -jar myapp.jar
~~~

Đây là lệnh minh họa; đường dẫn và JAR tùy hạ tầng. Nếu ứng dụng sử dụng Spring Boot hoặc framework điều phối logging, hãy kiểm tra cơ chế chọn file/config được framework hỗ trợ thay vì giả định system property luôn là nguồn cuối cùng.

**Đừng bật DEBUG toàn bộ production quá lâu.** Khi điều tra, chỉ tăng level cho đúng package/service trong khoảng thời gian kiểm soát được và ghi lại thời điểm hoàn nguyên.

## 8. File rotation và retention

Nếu cần file logging trên host, hãy xác định đường dẫn, quyền ghi, dung lượng tối đa, chu kỳ rotation, số ngày lưu, nén và xóa cục bộ. File trên filesystem tạm của container có thể mất khi pod bị thay thế; phải có chính sách vận chuyển/lưu giữ độc lập.

Ví dụ định nghĩa appender Logback chỉ phù hợp khi có thư mục **logs/** được cấp quyền và quản lý:

~~~xml
<appender name="ROLLING" class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>
    <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
        <maxFileSize>100MB</maxFileSize>
        <maxHistory>14</maxHistory>
        <totalSizeCap>5GB</totalSizeCap>
    </rollingPolicy>
    <encoder>
        <pattern>%d{ISO8601} %-5level [%thread] %logger{36} - %msg%n</pattern>
    </encoder>
</appender>
~~~

Đây mới là **định nghĩa appender**, cần **appender-ref** từ root/logger để thực sự nhận log. Các số 100MB, 14 kỳ và 5GB chỉ để minh họa; phải tính theo nhu cầu truy vấn, sản lượng log, disk quota và chính sách bảo mật.

Tránh dùng hai công cụ rotation không phối hợp trên cùng một file: appender còn giữ file handle trong khi tiến trình ngoài rename/truncate có thể dẫn tới log thiếu, trùng hoặc dung lượng không theo dự tính.

Phải phân biệt **retention cục bộ** và **retention trên backend tập trung**. Xóa archive cũ trên host không đồng nghĩa log đã bị xóa khỏi object storage hoặc index tìm kiếm. Khi có chính sách dữ liệu, cần quản lý đủ mọi bản sao.

## 9. Asynchronous logging và backpressure

Ghi log trực tiếp có thể gây I/O bottleneck khi số event lớn. Async logger/appender thường đưa log vào queue rồi dùng thread nền để ghi. Cơ chế này cải thiện đường xử lý nóng trong nhiều trường hợp, nhưng không tự đảm bảo không mất log.

| Tình trạng | Rủi ro | Quyết định cần có |
| --- | --- | --- |
| Queue còn chỗ | Enqueue nhanh, sink ghi sau | Bounded queue và quan sát độ trễ |
| Queue gần đầy | Tăng memory/latency | Giảm log, tăng khả năng sink, cảnh báo |
| Queue đầy | Block producer hoặc discard tùy cấu hình | Chọn chính sách latency vs mất dữ liệu |
| JVM crash/kill | Event trong bộ đệm chưa flush có thể mất | Xác định mức đảm bảo phù hợp |
| Shutdown | Chưa kịp flush hoặc close | Graceful shutdown và giám sát dữ liệu bị mất |

Trong Logback, **AsyncAppender** có các tham số queue size, discarding threshold và **neverBlock**. Mặc định cụ thể có thể phụ thuộc cấu hình và phiên bản, nên không giả định mọi INFO/DEBUG đều được lưu khi queue gần đầy. Với neverBlock=false, producer có thể bị block khi queue đầy; nếu chọn cơ chế discard/non-blocking thì phải chấp nhận và đo loss.

**Audit hay sự kiện giao dịch bắt buộc** cần một đường ghi nhận có độ bền theo hợp đồng, không thể chỉ trông cậy vào async diagnostic logging. Audit không đồng nghĩa ghi nhiều INFO hơn; cần cơ chế lưu/đối soát được thiết kế riêng.

Cần theo dõi events/sec, bytes/sec, queue fullness, drop count, transport latency và chi phí lưu trữ, cùng với CPU/heap/response latency của ứng dụng.

## 10. Thread context, MDC và correlation

Ở production, một request hoặc job thường chuyển qua nhiều thread. **MDC (Mapped Diagnostic Context)** của SLF4J/Logback giúp thêm các field như requestId, workerId, traceId vào log trong phạm vi thực thi.

Đoạn sau chỉ mang tính **tích hợp**, yêu cầu SLF4J và phương thức nghiệp vụ **processRequest()** của ứng dụng:

~~~java
import org.slf4j.MDC;

void handle(String requestId) {
    try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("requestId", requestId)) {
        processRequest();
    }
}
~~~

Scope được đóng khi rời try-with-resources; điều này đặc biệt quan trọng với thread pool vì thread có thể xử lý request khác sau đó. Với callback hoặc executor, context trong caller không tự động chuyển qua thread mới; dùng cơ chế capture/activate/restore hoặc context propagation do framework hỗ trợ.

**MDC/ThreadLocal không tự đi qua HTTP hoặc message broker.** Để liên kết log giữa service, phải inject context vào headers/metadata, extract ở bên nhận và quản lý scope. Copy một chuỗi traceId vào MDC không tạo ra distributed tracing đầy đủ: hệ thống tracing cần tracer/propagator và span lifecycle.

Một schema production nên ghi service/instance, requestId/traceId nếu có, taskId cho background jobs, exception/errorCode phù hợp. Không dùng các định danh có cardinality cao làm label metrics tổng hợp.

## 11. Bảo mật dữ liệu trong log

Log là một đường xuất dữ liệu cần kiểm soát. Không ghi trực tiếp token, password, private key, Authorization header, cookie phiên đăng nhập, số thẻ, dữ liệu cá nhân hoặc toàn bộ request/response payload chưa được lọc.

Ví dụ cần tránh:

~~~text
INFO authentication failed token=secret123 authorization=Bearer-raw-token
~~~

Cách an toàn hơn:

~~~text
WARN event=authentication_rejected reason=invalid_token requestId=req-217
~~~

Các giá trị trên là minh họa, không chứa bí mật thực. Mục tiêu là giữ thông tin vận hành cần thiết mà không lộ credential. Không tin rằng chỉ cần level INFO sẽ an toàn; exception message và INFO vẫn có thể mang dữ liệu nhạy cảm.

Áp dụng lọc/redaction tại nguồn khi có thể, kiểm soát log pipeline và quyền người xem, sử dụng retention theo mức độ nhạy cảm. Với dữ liệu người dùng đưa vào log, cần giới hạn chiều dài, xác thực hoặc escape ký tự đặc biệt và ký tự xuống dòng để giảm nguy cơ log injection.

Trong backend tập trung phải kiểm soát cả quyền export, download, dashboard share, replication và archive, bởi một dữ liệu nhạy cảm đã lọt vào log có thể được sao chép nhiều nơi.

## 12. Kiểm soát volume, sampling và chi phí

Lượng log production có thể tăng mạnh khi lưu lượng request tăng. Các biện pháp thường dùng:

1. Tắt TRACE/DEBUG mặc định hoặc giới hạn theo package.
2. Ghi tổng kết batch thay vì log INFO ở từng phần tử vòng lặp.
3. Giới hạn độ dài message/payload; đảm bảo exception vẫn đủ dữ kiện điều tra.
4. Sampling các sự kiện lặp và không bắt buộc, có quy tắc rõ ràng.
5. Phân loại retention theo nguồn dữ liệu và mức độ cần thiết.
6. Cảnh báo khi bytes/sec, ingestion delay, dropped events hoặc chi phí lưu tăng bất thường.

**Log sampling khác trace sampling.** Cờ sampled của trace không tự quyết định mọi log có được ghi hay không. Không áp dụng sampling tùy tiện cho audit, lỗi hiếm nhưng quan trọng hoặc bằng chứng giao dịch.

Tránh sử dụng requestId/traceId/taskId làm nhãn Prometheus metric vì cardinality cao tạo nhiều chuỗi thời gian. Các ID này thích hợp hơn trong log và trace; metric labels nên có tập giá trị ổn định như service, queue và outcome.

## 13. Thay đổi cấu hình trong production

Một thao tác đổi level hoặc destination cần có nguồn cấu hình, phê duyệt và cách hoàn nguyên phù hợp:

- **Xác định mục tiêu:** giảm volume, tăng dữ kiện, đổi format hay xử lý retention?
- **Khoanh vùng:** service, namespace, instance và thời gian hiệu lực.
- **Xác nhận provider:** JUL/Logback/Log4j 2 và framework điều phối.
- **Kiểm thử trước:** validate file, parser/encoder, level, timezone, permission, output và khả năng thu thập.
- **Triển khai có kiểm soát:** version, review, rollout dần, xác nhận effective configuration.
- **Quan sát sau deploy:** tỷ lệ lỗi, latency, log volume, ingestion, drop, parse errors.
- **Hoàn nguyên:** trả DEBUG tạm thời về mức chính sách, kiểm tra trên mọi instance.

Không phải mọi logger tự reload khi file đổi. JUL, Logback và framework có cơ chế riêng; cần bằng chứng runtime hoặc restart thành công. Nếu nhiều instance được chỉnh bằng tay, có thể xảy ra **configuration drift**: cùng dịch vụ nhưng mỗi pod phát log khác nhau. Nên giữ cấu hình được quản lý tập trung và có version.

## 14. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều tra |
| --- | --- | --- |
| Không thấy INFO | Root hoặc appender chỉ nhận WARN, file không được nạp | Xác minh effective level và config load |
| Log DEBUG tràn hệ thống | Bật root DEBUG, log trong vòng lặp | Giới hạn namespace/thời gian, đo volume |
| Terminal có log nhưng dashboard không thấy | Collector, parser, transport hoặc index lỗi | Kiểm tra tuần tự app → collector → backend |
| Một event xuất hiện hai lần | Nhiều handler/appender, logger additivity, collector đọc trùng nguồn | Kiểm tra logger tree và pipeline |
| Stack trace bị chia thành nhiều event | Parser multiline không phù hợp | JSON exception field hoặc cấu hình multiline |
| Thiếu traceId | Tracer/MDC chưa gắn hoặc context mất khi đổi thread | Kiểm tra propagation và scope |
| Log request bị trộn | ThreadLocal/MDC không clear/restore | Dọn context trong finally |
| Disk đầy | Không rotation hoặc retention | Giới hạn size/time, kiểm tra cleanup |
| Ứng dụng chậm khi collector lỗi | Network logging đồng bộ hoặc queue đầy chặn producer | Chọn chính sách backpressure, đo queue |
| Mất log khi shutdown | Buffer chưa flush hoặc tiến trình bị kill | Graceful shutdown, đo số event bị mất |
| JSON không parse | Chỉ có text pattern hoặc escaping sai | Kiểm tra encoder, parser và payload thật |
| Lộ bí mật | Dump raw request hoặc exception chứa token | Redact ở nguồn, kiểm soát quyền và retention |

Ví dụ sau deploy, dashboard chỉ còn WARN/ERROR. Hãy kiểm tra xem service có thực sự phát INFO ở runtime không, root và handler threshold là gì, rồi quan sát stdout/stderr trực tiếp. Nếu terminal có INFO nhưng dashboard không có, vấn đề có khả năng ở collector/filter/backend chứ không phải logger; bật DEBUG chỉ làm tăng dữ liệu mà chưa giải quyết đường thu thập.

Nếu log bị nhân đôi, cần kiểm tra cả additivity của logger con, việc gắn appender nhiều tầng và collector đọc cả file lẫn console.

## 15. Kiểm thử cấu hình logging

Một bộ kiểm thử production logging nên xác nhận các nhóm sau.

**Level và namespace:** tạo DEBUG/INFO/WARN/ERROR mẫu, xác nhận mức theo từng logger và handler; tăng DEBUG chỉ ở một package không làm thay đổi root ngoài dự kiến.

**Định dạng:** timestamp có timezone, severity, service/instance, thread, error context; nếu JSON, phải parse được qua parser thực, kể cả dấu ngoặc kép, dấu xuống dòng và Unicode tiếng Việt.

**Propagation:** nhiều request/task đồng thời không trộn requestId/traceId. Với ExecutorService, CompletableFuture, message consumer và retries, context phải gắn đúng phạm vi, được dọn sau khi tác vụ kết thúc.

**Độ bền pipeline:** kiểm tra log khi pod restart, collector unavailable và lượng log tăng; đo queue, dropped events, ingestion delay và cách shutdown flush buffer.

**File và retention:** nếu dùng file appender, xác minh rotation theo kích thước/thời gian, dung lượng archive, quyền truy cập và đồng bộ ra kho lưu trữ.

**Bảo mật:** gửi test token giả và message có ký tự điều khiển; xác nhận dữ liệu không lọt vào log, parser không bị phá và người dùng không đủ quyền không đọc được backend.

**Hoàn nguyên:** tăng level tạm thời rồi rollback; mọi instance phải áp dụng cùng chính sách sau khi rollout.

## 16. Checklist trước khi bật production

| Hạng mục | Điều kiện cần đạt |
| --- | --- |
| Logging provider | Biết implementation thực tế và đường dẫn config có hiệu lực |
| Level | Root/namespace threshold được chọn có lý do |
| Destination | stdout/stderr hoặc file phù hợp hạ tầng |
| Format | Có timestamp, level, service, instance, ngữ cảnh cần thiết |
| Collector | Đã xác minh đường đi từ ứng dụng tới backend |
| Correlation | Tra cứu được theo request/trace/job ID khi áp dụng |
| Data protection | Không ghi bí mật; masking, phân quyền và retention được kiểm thử |
| Volume | Có giới hạn và cảnh báo log bùng phát |
| Backpressure | Hiểu drop/block policy, queue và shutdown flush |
| Rotation | File và archive không tăng vô hạn nếu có file logging |
| Monitoring | Theo dõi ingestion, parse errors, dropped log events |
| Change management | Cấu hình được version hóa, rollback được, hạn chế drift |
| Verification | Đã kiểm tra các sự kiện thực tế sau deploy |

**Điểm cần nhớ:** cấu hình logging production tốt phải **đủ dữ kiện điều tra, có cấu trúc, bảo vệ thông tin, truy vấn được, giữ chi phí và tác động hiệu năng có kiểm soát**. Với Java, hãy xác nhận đúng provider, thiết kế level/formatter/appender có chủ đích, kiểm chứng collector và lưu trữ, rồi chạy các bài kiểm thử vận hành trước khi đưa hệ thống vào tải thật.