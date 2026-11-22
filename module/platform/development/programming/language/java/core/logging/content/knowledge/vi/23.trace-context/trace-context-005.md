# Propagation qua service trong Java Core Logging

## 1. Vì sao phải truyền trace context qua service?

Một yêu cầu thường đi qua nhiều thành phần: API Gateway → Service A → Service B → hàng đợi → Worker. Nếu mỗi nơi chỉ ghi timestamp và thông báo, việc ghép các dòng log của cùng một yêu cầu sẽ khó khăn, nhất là khi nhiều request được xử lý đồng thời.

**Propagation qua service** là quá trình **trích xuất ngữ cảnh truy vết từ yêu cầu nhận vào, gắn ngữ cảnh đó với xử lý hiện tại, rồi truyền các trường cần thiết sang lời gọi kế tiếp**. Nhờ vậy, log ở các service có thể được lọc theo một định danh xuyên suốt.

Ví dụ, cùng một lần gọi thanh toán có thể sinh các log sau:

~~~text
api-gateway traceId=4bf92f3577b34da6a3ce929d0e0e4736 action=route
order-service traceId=4bf92f3577b34da6a3ce929d0e0e4736 action=create-order
payment-service traceId=4bf92f3577b34da6a3ce929d0e0e4736 action=authorize
~~~

Ba dòng thuộc cùng một trace mặc dù xuất hiện ở ba service. Việc có chung trace ID **không** tự động tạo ra distributed tracing: để xem quan hệ cha–con và thời lượng từng thao tác, cần các **span** và hệ thống thu thập trace tương ứng.

Mục tiêu của bài là hiểu ngữ nghĩa các định danh, biết cách truyền context qua ranh giới mạng và luồng thực thi, đồng thời ghi log có thể đối chiếu mà không làm rò rỉ dữ liệu.

## 2. Các định danh thường gặp

| Thành phần | Ý nghĩa | Phạm vi và lưu ý |
| --- | --- | --- |
| **Correlation ID / Request ID** | Mã ứng dụng dùng để gom log của một yêu cầu hoặc quy trình nghiệp vụ | Thường được truyền bằng header tùy chỉnh như X-Correlation-ID; **không phải chuẩn span tracing** |
| **Trace ID** | Định danh chung cho toàn bộ một distributed trace | Giữ ổn định khi đi qua các service trong cùng trace |
| **Span ID** | Định danh của một đơn vị công việc trong trace | Mỗi span có ID riêng; span ở service sau thường khác span ở service trước |
| **Parent Span ID** | Liên kết span hiện tại với span tạo ra nó | Tạo cây phụ thuộc giữa các thao tác |
| **Trace flags** | Bit điều khiển, trong đó bit thấp nhất thể hiện cờ sampled | Không suy diễn rằng cờ sampled=0 đồng nghĩa không có trace ID |
| **Baggage** | Tập thuộc tính có thể lan truyền qua ranh giới service | Chỉ dùng thông tin được phép truyền; không đưa token, mật khẩu hoặc dữ liệu nhạy cảm vào đây |
| **MDC (Mapped Diagnostic Context)** | Kho trường khóa–giá trị phục vụ định dạng log của một luồng xử lý | Là dữ liệu cục bộ của logger, không tự truyền qua HTTP hay message broker |

Một hệ thống có thể vừa có traceId để liên kết spans, vừa có correlationId để gắn một quy trình nghiệp vụ. Không nên mặc định hai giá trị này phải bằng nhau: correlationId có thể sống lâu hơn một trace, ví dụ một đơn hàng qua nhiều job độc lập.

## 3. Dòng chảy tại một service

Quy trình phổ biến khi nhận một HTTP request:

1. **Extract:** đọc traceparent/tracestate (hoặc header correlation ID theo hợp đồng nội bộ), kiểm tra cú pháp và giới hạn dữ liệu.
2. **Establish:** khôi phục ngữ cảnh cha hợp lệ, tạo span mới cho công việc hiện tại nếu đang dùng tracer; nếu chưa có context hợp lệ, bắt đầu context mới.
3. **Activate:** đặt ngữ cảnh trong scope thực thi để logger lấy được traceId/spanId/correlationId.
4. **Log:** đưa các trường định danh vào log có cấu trúc hoặc pattern MDC, giúp tìm kiếm giữa nhiều service.
5. **Inject:** khi gọi HTTP/gRPC hoặc phát message, đưa context **hiện tại** vào carrier của lời gọi ra.
6. **Cleanup:** kết thúc scope, khôi phục ngữ cảnh cũ hoặc xóa MDC/ThreadLocal trong khối finally để tránh rò dữ liệu sang yêu cầu kế tiếp.

~~~text
Client
  |
  | traceparent / X-Correlation-ID
  v
Service A: EXTRACT -> ACTIVATE -> LOG
  |
  | INJECT vào HTTP headers
  v
Service B: EXTRACT -> ACTIVATE -> LOG
  |
  | INJECT vào message headers
  v
Worker:    EXTRACT -> ACTIVATE -> LOG -> CLEANUP
~~~

**Quy tắc chính:** một trace hợp lệ đi qua nhiều service vẫn giữ **trace ID**, còn các service có thể tạo **span ID mới**. Trong khi đó một correlation ID thủ công có thể được sao chép nguyên vẹn; không nên gọi cách sao chép đó là tự động tạo span.

## 4. Chuẩn W3C Trace Context

Để các framework/ngôn ngữ có thể tương tác, W3C định nghĩa hai HTTP headers quan trọng:

- **traceparent:** chứa version, trace-id, parent-id và trace-flags.
- **tracestate:** mang thông tin trạng thái theo nhà cung cấp tracing; chỉ truyền khi phù hợp với ngữ cảnh và chuẩn.

Ví dụ hợp lệ của traceparent:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Cấu trúc của phiên bản 00:

~~~text
00 - 4bf92f3577b34da6a3ce929d0e0e4736 - 00f067aa0ba902b7 - 01
|                 |                         |           |
version     trace-id (16 byte)         parent-id    flags
             32 chữ số hex             16 hex      2 hex
~~~

Trace ID và parent ID không được toàn số 0; các trường phải đúng chiều dài và định dạng của phiên bản được hỗ trợ. Giá trị 01 ở trace-flags có bit sampled bật; 00 nghĩa là bit sampled tắt. Header gửi **từ A sang B** thể hiện span đang làm cha cho thao tác tiếp theo; khi B tạo server span mới, span ID của B sẽ khác ID cha trong header.

Khi nhận traceparent hợp lệ, tracer thường **tiếp tục trace ID** và tạo span mới cho tác vụ hiện tại. Khi thiếu hoặc không hợp lệ, hệ thống bắt đầu trace mới theo chính sách. Không tự ghép chuỗi traceparent bằng cách sửa một vài ký tự nếu ứng dụng đã có OpenTelemetry/Micrometer Tracing: hãy để propagator và tracer xử lý phiên bản, cờ lấy mẫu và trạng thái.

**Baggage** là một tiêu chuẩn liên quan nhưng tách biệt; nó không phải một phần bốn trường của traceparent. Một số thuộc tính có thể đi qua nhiều hệ thống và bị bên nhận quan sát, vì vậy cần giới hạn danh sách cho phép, kích thước và ranh giới tin cậy.

## 5. Ví dụ Java 17: correlation ID xuyên hai HTTP service

Ví dụ dưới đây chỉ dùng JDK, chạy hai HTTP server trên localhost để minh họa cơ chế **nhận → lưu trong scope luồng → gắn header vào lời gọi tiếp theo → ghi log → xóa scope**. Đây là cách truyền **X-Correlation-ID tùy chỉnh**, **không** phải triển khai đầy đủ của W3C spans.

Tạo file **CorrelationAcrossServices.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

public class CorrelationAcrossServices {
    private static final String HEADER = "X-Correlation-ID";
    private static final ThreadLocal<String> CURRENT_ID = new ThreadLocal<>();
    private static final Pattern VALID_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private static String acceptOrCreate(String candidate) {
        if (candidate != null && VALID_ID.matcher(candidate).matches()) {
            return candidate;
        }
        return UUID.randomUUID().toString();
    }

    private static void log(String service, String event) {
        System.out.println(service + " correlationId=" + CURRENT_ID.get()
                + " | " + event);
    }

    private static void reply(HttpExchange exchange, int code, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(code, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        HttpClient client = HttpClient.newHttpClient();

        HttpServer serviceB = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        serviceB.setExecutor(pool);
        serviceB.createContext("/work", exchange -> {
            CURRENT_ID.set(acceptOrCreate(
                    exchange.getRequestHeaders().getFirst(HEADER)));
            try {
                log("B", "xu ly /work");
                reply(exchange, 200, "OK");
            } finally {
                CURRENT_ID.remove();
            }
        });
        serviceB.start();
        int portB = serviceB.getAddress().getPort();

        HttpServer serviceA = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        serviceA.setExecutor(pool);
        serviceA.createContext("/start", exchange -> {
            String id = acceptOrCreate(
                    exchange.getRequestHeaders().getFirst(HEADER));
            CURRENT_ID.set(id);
            try {
                log("A", "nhan /start");

                HttpRequest downstream = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + portB + "/work"))
                        .header(HEADER, id)
                        .GET()
                        .build();

                int code;
                String body;
                try {
                    HttpResponse<String> response = client.send(
                            downstream,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
                    code = response.statusCode();
                    body = response.body();
                    log("A", "B tra " + code);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    code = 503;
                    body = "interrupted";
                    log("A", "loi: interrupted");
                } catch (IOException e) {
                    code = 502;
                    body = "bad gateway";
                    log("A", "loi khi goi B");
                }
                reply(exchange, code, body);
            } finally {
                CURRENT_ID.remove();
            }
        });
        serviceA.start();

        try {
            int portA = serviceA.getAddress().getPort();
            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:" + portA + "/start"))
                    .header(HEADER, "demo-req-42")
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("CLIENT HTTP " + response.statusCode()
                    + " body=" + response.body());
        } finally {
            serviceA.stop(0);
            serviceB.stop(0);
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --add-modules jdk.httpserver CorrelationAcrossServices.java
java --add-modules jdk.httpserver CorrelationAcrossServices
~~~

Kết quả kỳ vọng khi cả hai service trả HTTP 200:

~~~text
A correlationId=demo-req-42 | nhan /start
B correlationId=demo-req-42 | xu ly /work
A correlationId=demo-req-42 | B tra 200
CLIENT HTTP 200 body=OK
~~~

Giải thích:

- **Client** đặt header X-Correlation-ID bằng demo-req-42.
- **A** nhận và kiểm tra header, đặt ID vào ThreadLocal của luồng phục vụ A, rồi gắn chính ID đó vào yêu cầu HTTP gửi B.
- **B** lấy header mới nhận được, gắn vào ThreadLocal của luồng phục vụ B; do đó hai service có cùng correlationId trong log.
- Cuối mỗi handler, finally gọi CURRENT_ID.remove(). Thread pool tái sử dụng thread nên việc dọn context là bắt buộc.
- Nếu header thiếu hoặc không phù hợp biểu thức kiểm tra, service tạo UUID. Đây là ví dụ để hiểu propagation; hệ thống thực tế còn cần chính sách xác thực/chuẩn hóa nguồn tạo ID, kích thước header, xử lý nhiều giá trị và tỷ lệ lỗi.

**Điểm dễ nhầm:** ThreadLocal ở A **không hề** chạy qua mạng tới B. Chính giá trị của **HTTP header** mới làm cầu nối. Nếu bỏ dòng .header(HEADER, id) ở yêu cầu A → B, B sẽ tạo một ID mới và chuỗi log không còn liên tục.

Ví dụ đồng bộ này dùng blocking HttpClient để dễ quan sát; với HTTP client hoặc server bất đồng bộ cần dùng cơ chế truyền context phù hợp với executor/callback/framework.

## 6. Kết hợp context với logger và MDC

Trong ứng dụng Java dùng SLF4J/Logback, nên đưa correlationId hoặc traceId vào **MDC** rồi cấu hình pattern/JSON encoder hiển thị trường đó ở mọi dòng log. Mã dưới đây **cần thư viện SLF4J** và là trích đoạn tích hợp, không phải chương trình JDK độc lập:

~~~java
import org.slf4j.MDC;

void handleRequest(String correlationId) {
    try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("correlationId", correlationId)) {
        // Log trong scope này có thể đọc MDC["correlationId"].
        processRequest();
    }
}
~~~

Ví dụ một phần pattern của Logback:

~~~text
%d{ISO8601} %-5level trace=%X{traceId} correlation=%X{correlationId} %logger - %msg%n
~~~

Tên trường trong MDC phải thống nhất với cấu hình thư viện tracing và encoder. Nếu dùng Micrometer Tracing hoặc OpenTelemetry có tích hợp log correlation, hãy kiểm tra cấu hình cụ thể để tránh tự ghi đè traceId/spanId do framework đã quản lý.

Khi xử lý lỗi, **log exception với stack trace** và giữ nguyên context đang hoạt động; không cần nhân bản toàn bộ payload request/response chỉ để tìm một trace. Với hệ thống nhiều service, log dạng JSON có các khóa nhất quán như timestamp, service, level, traceId, spanId, correlationId và message giúp truy vấn ổn định.

## 7. Khi công việc đổi luồng: Executor, CompletableFuture, reactive

MDC thường dựa trên ThreadLocal. Một task chuyển sang luồng khác bằng Executor, CompletableFuture, callback hoặc message listener **không mặc nhiên thừa hưởng** context hiện tại. Việc giữ nguyên field ở HTTP header là cần thiết nhưng chưa đủ cho các tác vụ chạy bất đồng bộ *bên trong* service.

Với ví dụ ThreadLocal ở trên, cách tối thiểu cho một task dùng Executor là **capture trước khi submit, activate trong task, restore sau khi xong**:

~~~java
String capturedId = CURRENT_ID.get();
executor.execute(() -> {
    String previousId = CURRENT_ID.get();
    try {
        if (capturedId == null) {
            CURRENT_ID.remove();
        } else {
            CURRENT_ID.set(capturedId);
        }
        doWork();
    } finally {
        if (previousId == null) {
            CURRENT_ID.remove();
        } else {
            CURRENT_ID.set(previousId);
        }
    }
});
~~~

Đoạn này minh họa việc truyền một ThreadLocal do chính ứng dụng quản lý; nó **không** sao chép toàn bộ OpenTelemetry Context hay bản đồ MDC. Trong ứng dụng thực, ưu tiên context propagation do tracing SDK/framework hoặc task decorator hỗ trợ để mang đúng các trường và quản lý scope. Không sử dụng InheritableThreadLocal như một giải pháp chung cho thread pool vì các worker tồn tại lâu và được tái sử dụng.

Với **Spring WebFlux/Reactor**, chuỗi xử lý có thể đổi thread giữa các operator: không dựa hoàn toàn vào ThreadLocal truyền tay. Dùng Reactor Context và cơ chế tích hợp context propagation phù hợp với phiên bản Reactor/Micrometer/OpenTelemetry đang triển khai.

## 8. Qua HTTP, gRPC và hàng đợi

| Ranh giới | Vị trí truyền | Bên nhận cần làm |
| --- | --- | --- |
| HTTP REST | Headers traceparent, tracestate; hoặc X-Correlation-ID nếu có hợp đồng nội bộ | Extract/validate, tạo scope/span phù hợp, log và inject sang lần gọi sau |
| gRPC | Request metadata | Dùng propagator/interceptor tương thích, truyền context theo lời gọi |
| Kafka/RabbitMQ | Message headers/properties | Producer inject khi publish; consumer extract cho **mỗi message**, xử lý rồi đóng scope |
| Job theo lịch | Metadata job hoặc định danh workflow được lưu tường minh | Tạo trace mới nếu không có parent; ghi rõ quan hệ với job/correlation ID |
| Retry hoặc chuyển sang DLQ | Metadata của lần xử lý và thông tin retry | Giữ định danh nghiệp vụ cần thiết; tạo span xử lý mới, tránh lẫn log giữa các attempt |

Ví dụ với message broker: nếu Service A phát sự kiện tạo đơn hàng, hãy inject context vào **headers** của message, không giả định nội dung JSON body tự mang trace context. Khi worker nhận nhiều message liên tiếp trên một thread, đóng context của message trước khi xử lý message kế tiếp. Đối với xử lý trì hoãn hoặc sự kiện bất đồng bộ có tuổi thọ dài, có thể dùng **span links** để thể hiện quan hệ nguyên nhân thay vì ép mọi tác vụ làm con trực tiếp; việc chọn parent/link phụ thuộc mô hình tracing và hợp đồng nghiệp vụ.

## 9. Biên tin cậy, bảo mật và vận hành

1. **Không coi inbound traceId/correlationId là bằng chứng nhận dạng.** Client có thể tự gửi header. Xác thực/ủy quyền luôn độc lập với tracing.
2. **Xác thực cấu trúc và giới hạn chiều dài** của các ID tự quản lý; không ghi header thô tùy ý vào log vì có nguy cơ log injection, chiếm dung lượng và sai lệch tìm kiếm.
3. **Không truyền dữ liệu nhạy cảm qua baggage hoặc log.** Token, mật khẩu, thông tin thẻ, dữ liệu cá nhân và nội dung request chưa lọc không thuộc trace context.
4. **Có chính sách tại trust boundary.** Gateway có thể loại bỏ/khởi tạo lại context từ nguồn không tin cậy theo chính sách, và chỉ cho phép tập baggage được duyệt đi tiếp.
5. **Giữ ranh giới lỗi.** Timeout, cancellation hoặc retry phải kết thúc scope cũ đúng cách; không để MDC từ yêu cầu trước tồn tại trên worker kế tiếp.
6. **Đừng nhầm sampling với khả năng đối chiếu log.** Cờ sampled điều khiển quyết định lấy mẫu trace; log correlation và việc lưu span thực tế còn phụ thuộc cấu hình SDK, exporter và log pipeline.
7. **Đảm bảo tên field nhất quán.** Nếu A ghi trace_id còn B ghi traceId, cần normalize ở logger/collector để một truy vấn tìm được cả hai.
8. **Theo dõi chi phí.** Tránh đưa các thuộc tính có cardinality cao hoặc payload lớn vào nhãn metric; trace ID thích hợp trong log/trace nhưng không phải nhãn metric tổng hợp.

## 10. Lỗi phổ biến và cách nhận biết

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Log ở A có ID, log ở B thiếu ID | Client A không inject header hoặc B không extract | Kiểm tra HTTP/message interceptor hai phía, đối chiếu headers mẫu |
| Mỗi service có traceId khác nhau | Tạo root trace mới ở mọi hop hoặc bỏ parent context | Khôi phục incoming context trước khi bắt đầu span mới |
| Hai request khác nhau có cùng MDC | Không clear/restore ThreadLocal ở thread pool | Đóng scope trong finally/try-with-resources |
| Log trong CompletableFuture mất ID | Task chạy ở executor khác | Capture/activate/restore bằng cơ chế propagation được hỗ trợ |
| Có traceId nhưng không có cây span | Mới sao chép một correlation ID hoặc chưa cấu hình tracer/exporter | Phân biệt log correlation với distributed tracing và kiểm tra instrumentations |
| Trace bị đứt khi qua broker | Producer không inject hoặc consumer không extract message headers | Instrument riêng producer/consumer, kiểm tra mỗi message |
| Query log trả về dữ liệu không mong muốn | Tin header tự do hoặc không chuẩn hóa field | Validate, đặt trust policy, chuẩn hóa cấu trúc log |

## 11. Cách kiểm thử propagation

Một bộ kiểm tra hiệu quả nên bao gồm:

- **Happy path:** gửi ID hợp lệ từ client, gọi A → B → worker; xác nhận mọi log thuộc yêu cầu có cùng correlationId/traceId và trace span IDs có quan hệ hợp lệ nếu dùng tracer.
- **Thiếu hoặc sai header:** xác nhận hệ thống tạo context mới và không làm hỏng request; kiểm tra chính sách biên cho nguồn không tin cậy.
- **Concurrency:** chạy nhiều request song song với ID khác nhau; tìm các log bị trộn ID giữa thread.
- **Async/retry/timeout:** đổi executor, retry và hủy yêu cầu; xác nhận context gắn đúng attempt, được dọn sau khi xử lý.
- **Messaging:** kiểm tra producer/consumer, batch nhiều message và đường đi DLQ; không giả định thread-local còn đúng sau lần xử lý trước.
- **Observability:** lấy một trace ID từ log rồi truy vấn ở service kế tiếp; nếu đã có tracing backend, kiểm tra span tree và mối liên hệ log–trace.

**Bài học cần nhớ:** context chỉ đi qua service khi được **serialize/inject vào giao thức** và được **extract/activate** ở đầu nhận. MDC hoặc ThreadLocal chỉ giúp gắn ID trong phạm vi thực thi cục bộ. Để có distributed tracing đầy đủ, cần tracer/propagator phù hợp bên cạnh log correlation.