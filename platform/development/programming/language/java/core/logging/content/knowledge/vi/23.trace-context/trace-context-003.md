# Trace context trong log (Java Core Logging)

## 1. Vì sao log cần trace context?

Trong ứng dụng Java phục vụ nhiều request đồng thời, log từ nhiều thread và nhiều dịch vụ thường xen kẽ nhau. Chỉ nhìn thời điểm, mức INFO/ERROR và thông điệp sẽ khó biết dòng log nào thuộc cùng một lần xử lý. **Trace context trong log** là tập định danh được đính kèm vào từng sự kiện log để truy vết toàn bộ đường đi của một tác vụ, đặc biệt khi tác vụ đi qua nhiều service hoặc chạy bất đồng bộ.

Ví dụ, hai dòng log ở hai dịch vụ có cùng trace ID giúp tìm các sự kiện liên quan đến một chuỗi xử lý:

~~~text
INFO  service=api     trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7 - Accepted order
INFO  service=payment trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=1111111111111111 - Charged order
~~~

Giá trị của cách làm này là khả năng lọc log theo trace ID khi điều tra lỗi, liên hệ log với distributed trace, và giảm nhầm lẫn giữa các request chạy đồng thời. Context không thay thế thông điệp log rõ nghĩa, exception stack trace, hay một hệ thống tracing thực sự.

## 2. Các định danh cần phân biệt

| Trường | Ý nghĩa | Phạm vi |
| --- | --- | --- |
| trace_id | Định danh của toàn bộ trace, giữ nguyên khi cùng trace đi qua nhiều span/service | Một trace phân tán |
| span_id | Định danh span đang hoạt động tại thời điểm tạo log; các bước khác nhau có thể có span ID khác nhau | Một span |
| parent_span_id | Span cha của span hiện tại, hữu ích khi biểu diễn quan hệ cha–con; không bắt buộc có trong mỗi dòng log | Quan hệ giữa các span |
| request_id / correlation_id | Định danh do ứng dụng hoặc gateway quy ước để tra cứu request/nghiệp vụ; không mặc nhiên tuân thủ chuẩn trace ID | Tùy hệ thống |
| trace_flags | Cờ của trace context, trong đó bit sampled cho biết quyết định lấy mẫu tracing | Trace context |
| service.name | Tên dịch vụ phát sinh log, dùng để phân biệt nguồn khi tổng hợp tập trung | Dịch vụ |

**Trace ID và request ID không đồng nghĩa.** Một request HTTP thường tương ứng một trace, nhưng có thể có trace tiếp tục qua hàng đợi, hoặc một luồng nghiệp vụ gồm nhiều request. Không lấy chuỗi request ID bất kỳ và coi đó là W3C trace ID.

### Trace context truyền giữa các dịch vụ

W3C Trace Context định nghĩa HTTP header traceparent với dạng:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^^ ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^^^ ^^
             │  trace-id (32 ký tự hex)           │                trace-flags
             version                              parent-id (16 ký tự hex)
~~~

Trong phiên bản 00, trace-id dài 16 byte (32 ký tự hex chữ thường), parent-id dài 8 byte (16 ký tự hex chữ thường); hai ID không được toàn số 0. Khi dịch vụ nhận traceparent, parent-id là ID span phía gửi; khi dịch vụ tạo span mới, span_id hiện tại của dịch vụ có thể khác parent-id nhận vào. Header tracestate có thể mang thông tin riêng của vendor. Header baggage, nếu có, dùng để truyền thuộc tính bổ sung và phải kiểm soát dữ liệu nhạy cảm.

~~~text
Client
  └─ traceparent ──> API [span A]
                       ├─ log: trace=T, span=A
                       └─ traceparent ──> Payment [span B]
                                             └─ log: trace=T, span=B
~~~

Hai dịch vụ giữ cùng trace ID T nhưng có span ID A và B khác nhau. Việc truyền traceparent qua HTTP/message headers và tạo span thuộc trách nhiệm của thư viện tracing hoặc instrumentation; chỉ đưa một giá trị vào log không tự tạo ra distributed trace.

## 3. MDC: cách gắn context vào log Java

SLF4J có API **Mapped Diagnostic Context (MDC)**: một map từ khóa đến chuỗi, thường được logging provider gắn với thread đang thực thi. Logback dùng ký hiệu %X{key} trong pattern để lấy giá trị MDC tại thời điểm ghi log.

~~~java
MDC.put("trace_id", "4bf92f3577b34da6a3ce929d0e0e4736");
try {
    logger.info("Processing");
} finally {
    MDC.remove("trace_id");
}
~~~

Đây là đoạn minh họa bên trong một lớp đã có logger, không phải chương trình độc lập. Cần dọn context trong finally vì các thread của pool được tái sử dụng; nếu để sót giá trị, log của request sau có thể bị gắn nhầm trace ID của request trước. Khi scope lồng nhau hoặc cần giữ lại context cũ, nên lưu và phục hồi cả map thay vì chỉ gọi clear không điều kiện.

MDC là dữ liệu phục vụ logging; nó **không tự truyền qua mạng, không tạo span, không đảm bảo được mang sang ExecutorService, CompletableFuture hoặc các luồng xử lý reactive**. Phải chuyển context bằng cơ chế phù hợp ở ranh giới bất đồng bộ.

## 4. Ví dụ Java 17+: log theo trace và truyền MDC vào thread pool

Ví dụ dùng SLF4J 2.0.20 cùng Logback 1.6.5. Các ID đặt trong ví dụ là dữ liệu mô phỏng để học MDC; chương trình không tạo span OpenTelemetry hay gửi trace qua mạng.

Cấu trúc dự án Maven:

~~~text
trace-log-demo/
├── pom.xml
└── src/main/
    ├── java/example/TraceLogDemo.java
    └── resources/logback.xml
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>trace-log-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.20</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.6.5</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/resources/logback.xml**

~~~xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level trace_id=%X{trace_id:-none} span_id=%X{span_id:-none} request_id=%X{request_id:-none} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Trong pattern, %X{trace_id:-none} hiển thị MDC trace_id; nếu không có thì hiển thị none. Các trường được đặt tên nhất quán để hệ thống thu thập log có thể tìm kiếm.

**src/main/java/example/TraceLogDemo.java**

~~~java
package example;

import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class TraceLogDemo {
    private static final Logger LOG = LoggerFactory.getLogger(TraceLogDemo.class);

    // Cài context cho scope hiện tại, rồi phục hồi context trước đó.
    private static void withMdc(Map<String, String> context, Runnable action) {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (context == null || context.isEmpty()) {
                MDC.clear();
            } else {
                MDC.setContextMap(context);
            }
            action.run();
        } finally {
            if (previous == null || previous.isEmpty()) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            LOG.info("before request");

            Map<String, String> requestContext = Map.of(
                "trace_id", "4bf92f3577b34da6a3ce929d0e0e4736",
                "span_id", "00f067aa0ba902b7",
                "request_id", "req-42"
            );

            withMdc(requestContext, () -> {
                LOG.info("request accepted");

                // Chụp bản sao ở thread gọi, trước khi gửi sang pool.
                Map<String, String> captured = MDC.getCopyOfContextMap();
                CompletableFuture.runAsync(
                    () -> withMdc(captured, () -> {
                        // Mô phỏng một span khác; không tạo span thực.
                        MDC.put("span_id", "1111111111111111");
                        LOG.info("async work");
                    }),
                    pool
                ).join();

                LOG.info("response sent");
            });

            LOG.info("after request");
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Tại thư mục chứa pom.xml, dùng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.TraceLogDemo
~~~

Phần log do ứng dụng ghi ra (bỏ qua thông báo riêng của Maven nếu có) theo đúng thứ tự:

~~~text
INFO trace_id=none span_id=none request_id=none - before request
INFO trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7 request_id=req-42 - request accepted
INFO trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=1111111111111111 request_id=req-42 - async work
INFO trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=00f067aa0ba902b7 request_id=req-42 - response sent
INFO trace_id=none span_id=none request_id=none - after request
~~~

**Vì sao đúng?** withMdc nhận bản sao context trước đó, gắn context mới trong try và phục hồi trong finally. Thread pool nhận captured từ thread gọi và tự phục hồi MDC sau tác vụ. join() chờ log ở thread pool hoàn thành trước khi ghi response sent, vì vậy thứ tự các dòng trong ví dụ là xác định. Thay span_id trong tác vụ async chỉ ảnh hưởng scope của tác vụ đó; sau khi quay về thread gọi, span_id ban đầu vẫn còn. Hai dòng đầu/cuối ngoài scope không mang trace ID, chứng tỏ không rò rỉ MDC.

**Giới hạn của ví dụ:** cập nhật MDC span_id thủ công chỉ thay nhãn log. Nếu dùng tracing thật, span phải được tạo/kích hoạt qua tracer; không tự gán giá trị giả để báo rằng đã có một span được ghi nhận trong hệ thống tracing.

## 5. Tích hợp tracing thật với OpenTelemetry

Trong hệ thống nhiều dịch vụ, nên dùng OpenTelemetry SDK hoặc Java agent phù hợp để tự động/trực tiếp thực hiện các bước: tiếp nhận và kiểm tra traceparent, tạo span, duy trì context đang hoạt động, truyền context khi gọi dịch vụ khác, và đưa trace ID/span ID đúng của span hiện tại vào log.

Với OpenTelemetry Java agent có instrumentation MDC tương ứng, các khóa thường gặp trong logging event là:

- trace_id: ID của trace hiện tại;
- span_id: ID của span hiện tại;
- trace_flags: cờ trace hiện tại, ví dụ 01 khi sampled.

Ví dụ pattern Logback có thể dùng:

~~~xml
<pattern>%d{ISO8601} %-5level service=orders trace_id=%X{trace_id:-} span_id=%X{span_id:-} flags=%X{trace_flags:-} - %msg%n</pattern>
~~~

Đây là phần cấu hình pattern, không phải cấu hình đầy đủ để cài OpenTelemetry Java agent. Phải cấu hình agent/exporter, kích hoạt instrumentation phù hợp và kiểm tra logging provider đang dùng. Khi không có span hợp lệ đang hoạt động, không được giả định các trường trace tự xuất hiện. **Không trộn cơ chế tự gán MDC thủ công và cơ chế agent chèn MDC trên cùng khóa** nếu chưa xác định rõ cách chúng tương tác.

Mô hình sử dụng thực tế:

1. HTTP ingress nhận hoặc khởi tạo trace context; tracer xác lập span hiện tại.
2. Log trong service ghi trace_id/span_id từ span hiện tại.
3. HTTP client hoặc producer hàng đợi inject context vào metadata của lời gọi đi.
4. Service/consumer tiếp theo extract context và tạo span con; log tiếp tục cùng trace_id.
5. Tại các nhánh chạy nền, task được tạo phải mang context một cách rõ ràng (hoặc dùng instrumentation/framework hỗ trợ).
6. Khi kết thúc scope, context được đóng/phục hồi để tránh dính sang tác vụ khác.

Quy trình này giải quyết cả **truy vết giữa các dịch vụ** và **liên kết log với trace**; MDC đơn lẻ chỉ giải quyết phần ghi context vào log.

## 6. Những tình huống cần chú ý

### Thread pool, CompletableFuture, virtual thread và reactive flow

- MDC truyền thống thường gắn với thread. Không được giả định context tự kế thừa khi dùng ExecutorService, CompletableFuture hoặc chạy callback trên thread khác.
- Dùng wrapper/cơ chế context propagation của tracing hoặc framework để chụp và phục hồi context tại ranh giới tác vụ; luôn dọn context trong finally.
- Với reactive streams, một request có thể đổi thread nhiều lần; dùng context propagation của Reactor/OpenTelemetry thay vì chỉ đặt MDC một lần ở thread ban đầu.
- Với virtual threads, vẫn phải xem lại cách thư viện logging và tracing quản lý context; không suy ra context sẽ tự đi qua mọi tác vụ bất đồng bộ.

### Bảo mật và tính toàn vẹn

- Không đưa access token, mật khẩu, thông tin thanh toán hay dữ liệu cá nhân nhạy cảm vào MDC, baggage hoặc log. Trace ID chỉ là định danh tương quan, không phải bằng chứng xác thực danh tính.
- Header traceparent từ phía ngoài phải được parser của thư viện tracing kiểm tra; nếu không hợp lệ thì bỏ và áp dụng chính sách khởi tạo trace mới. Không tin mọi giá trị do client gửi vào rồi ghi nguyên xi.
- Giới hạn độ dài và chuẩn hóa các trường tùy biến như request_id, tránh ký tự xuống dòng/ký tự điều khiển gây giả mạo log.
- Dùng tên trường ổn định, ví dụ trace_id, span_id, request_id, service.name; kiểm tra cách backend log tìm kiếm/index các trường này. Với structured JSON logging, giữ chúng thành các thuộc tính riêng thay vì nhét tất cả vào message.
- Quyết định sampled ở trace_flags không có nghĩa là mọi dòng log đều được lưu, và log có trace ID không chứng minh rằng trace đã được xuất hoặc được sampling giữ lại.

### Lỗi triển khai hay gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| Log trong thread pool không có trace_id | Chỉ gắn MDC ở thread gọi | Chuyển context vào task, phục hồi trong finally |
| Request B có trace_id của request A | Không dọn MDC sau request hoặc task | Dùng scope try/finally; thử hai request trên cùng pool |
| Nhiều service có request_id giống nhau nhưng trace không nối được | Chỉ truyền ID tùy biến; thiếu traceparent và span thực | Kiểm tra inject/extract context bằng tracing SDK/agent |
| Cùng trace_id nhưng span_id không đổi ở mọi bước | Chưa tạo/activate span con, hoặc gán ID thủ công | Dùng tracer và kiểm tra span đang hoạt động |
| Trên hệ thống log không thấy trace_id dù MDC.put đã gọi | Pattern/appender không xuất MDC, provider không hỗ trợ, hoặc thiếu span khi dùng agent | Kiểm tra backend SLF4J, Logback pattern và instrumentation |
| Trace có sampled=01 nhưng không tìm thấy trên backend | Pipeline/exporter có lỗi, cấu hình sampling khác, chưa xuất xong | Kiểm tra SDK/exporter, collector và chính sách lấy mẫu |

## 7. Cách xác nhận hoạt động đúng

Khi tích hợp vào ứng dụng thực tế, kiểm tra tối thiểu các trường hợp sau:

1. Gửi hai request song song: mỗi request có trace_id riêng và mọi log trong mỗi request giữ đúng ID của nó.
2. Tạo một tác vụ trong ExecutorService/CompletableFuture: log bên trong có context kỳ vọng, log của tác vụ tiếp theo trên cùng worker không nhận context cũ.
3. Gọi API sang service khác: trace_id giống nhau giữa hai service, còn span_id phản ánh span hiện tại của từng dịch vụ.
4. Gây exception hoặc timeout: context vẫn được dọn trong finally; có đủ thông tin exception trong log.
5. Dùng traceparent sai định dạng: ứng dụng xử lý an toàn qua parser/instrumentation; không chấp nhận một ID tùy ý như một trace hợp lệ.
6. Tắt instrumentation tạo span hoặc gọi log ngoài span: hiểu chính xác vì sao không có trace_id và không gắn nhầm ID giả.

Bài tập mở rộng: chạy ba request trên một fixed thread pool nhỏ; thêm request_id khác nhau và kiểm tra bằng log rằng không có request nào nhận nhầm context. Sau đó bật distributed tracing thực tế, tìm tất cả log của một trace_id trên nhiều dịch vụ và so sánh span_id tương ứng.

## 8. Ghi nhớ

Trace context trong log giúp nối các sự kiện liên quan giữa thread và dịch vụ. **Trace ID** mô tả một trace; **span ID** mô tả span đang chạy; **MDC** là cách logging framework hiển thị các ID này trong từng dòng log. Để correlation đáng tin cậy, phải có context propagation, scope cleanup và instrumentation tracing phù hợp; tự đặt vài chuỗi vào MDC chưa phải distributed tracing.

### Tài liệu tham khảo

- W3C Trace Context (đặc tả traceparent, tracestate): https://www.w3.org/TR/trace-context/
- SLF4J MDC API: https://www.slf4j.org/apidocs/org/slf4j/MDC.html
- Logback MDC manual: https://logback.qos.ch/manual/mdc.html
- Logback PatternLayout (%X): https://logback.qos.ch/manual/layouts.html
- OpenTelemetry Java — logger MDC instrumentation: https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/docs/logger-mdc-instrumentation.md
