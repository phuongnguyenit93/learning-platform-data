# Correlation với response trong ứng dụng web Java

## 1. Correlation với response là gì?

Trong ứng dụng web, **correlation với response** là cách gắn một định danh theo request hoặc trace vào **HTTP response** để người gọi API, trình duyệt, gateway và đội vận hành có thể tìm đúng chuỗi log đã phát sinh khi xử lý yêu cầu đó.

Ví dụ người dùng báo: “API tạo đơn hàng trả HTTP 500 lúc 10:15”. Nếu hệ thống chỉ dựa vào thời điểm và URL, việc tìm log giữa hàng nghìn request đồng thời rất khó. Nếu response có **X-Request-ID: 9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f** và log cũng chứa requestId đó, đội hỗ trợ có thể truy vấn trực tiếp một luồng xử lý.

~~~text
Client                  Web application              Log backend
  | GET /api/orders/42         |                            |
  |--------------------------->|                            |
  |                            | tạo requestId = abc-123     |
  |                            | ghi log với requestId       |
  |                            |--------------------------->|
  |  HTTP 200                  |                            |
  |  X-Request-ID: abc-123     |                            |
  |<---------------------------|                            |
  |                            |                            |
  |      Hỗ trợ tra cứu requestId=abc-123 ----------------->|
~~~

**Điểm cốt lõi:** response không cần chứa stack trace, thông tin hệ thống nội bộ hay nội dung log. Nó chỉ cần cung cấp **mã tra cứu an toàn** đã được ghi đồng nhất ở server và, nếu cần, được truyền qua những dịch vụ liên quan.

Các lợi ích chính:

- **Hỗ trợ khách hàng:** người dùng đưa mã yêu cầu thay vì gửi thông tin cá nhân hoặc screenshot chứa dữ liệu nhạy cảm.
- **Điều tra lỗi:** nối response HTTP với log ở controller, service, repository, gateway và downstream.
- **Vận hành:** tìm log theo requestId/traceId, so sánh status, thời gian xử lý, lỗi và các bước nghiệp vụ.
- **Kiểm thử và giám sát:** đối chiếu response của test case với các event log, chứng minh một lỗi thực sự đã được ghi nhận.

Correlation ID **không phải** mã xác thực, không cấp quyền truy cập và không bảo đảm log tồn tại. Nếu backend filter/drop hoặc collector chưa ingest, vẫn có thể không tìm được log dù response trả đúng ID.

## 2. Phân biệt requestId, correlationId, traceId và spanId

Các tên này liên quan nhưng **không hoàn toàn tương đương**.

| Tên | Vai trò | Phạm vi thường gặp |
| --- | --- | --- |
| **requestId** | Nhận diện một HTTP request ở biên API | Một request vào gateway hoặc một hop của service |
| **correlationId** | Liên kết các log/event thuộc cùng ngữ cảnh xử lý | Có thể cùng nhiều service hoặc message |
| **traceId** | Định danh một distributed trace | Nhiều span qua các service cùng trace |
| **spanId** | Định danh một đơn vị công việc trong trace | Một span, có parent/child |
| **businessId** | Định danh đối tượng nghiệp vụ, ví dụ orderId | Có thể xuất hiện ở nhiều request và thời điểm |

Một hệ thống nhỏ có thể dùng cùng requestId làm correlationId. Trong hệ thống đã có OpenTelemetry/Micrometer Tracing, **traceId** thường là khóa tìm log trong hệ thống trace. Không bắt buộc tạo thêm một định danh thứ hai nếu tracer đã đáp ứng yêu cầu; nhưng nhiều API vẫn muốn một **mã request thân thiện với khách hàng** độc lập với cấu trúc trace.

Ví dụ:

~~~text
response:
  X-Request-ID: 9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f

server log:
  requestId=9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f
  traceId=4bf92f3577b34da6a3ce929d0e0e4736
  spanId=00f067aa0ba902b7
  status=200
~~~

RequestId và traceId có thể khác nhau nhưng phải được **liên kết trong log** khi cần tra cứu qua nhiều hệ thống.

Theo **W3C Trace Context**, header **traceparent** có dạng version-trace-id-parent-id-trace-flags. Với phiên bản 00, trace-id dài 32 ký tự hexadecimal và parent-id dài 16 ký tự hexadecimal; các ID toàn số 0 không hợp lệ. Đây là giao thức truyền context tracing giữa các service. Nó không đồng nghĩa với một response header **X-Request-ID** tùy biến do ứng dụng quyết định.

**Không nên tự chế traceparent** bằng cách nối một UUID không đúng định dạng; hãy để instrumentation/tracer tuân thủ chuẩn. Nếu muốn thêm X-Trace-ID ở response, cần quy định rõ nguồn ID, phạm vi và chính sách tiết lộ thông tin.

## 3. Những chỗ nên xuất correlation ID

Một thiết kế thông thường sử dụng cùng ID ở các vị trí:

1. **HTTP response header:** ví dụ X-Request-ID, giúp client hoặc hỗ trợ lấy ID trên cả response thành công và lỗi.
2. **Server log:** trong trường có cấu trúc requestId hoặc trong MDC/ThreadContext, để tìm nhanh.
3. **Error response body:** khi API trả lỗi, có thể kèm requestId bên cạnh mã lỗi và thông báo an toàn.
4. **Downstream call hoặc message:** truyền correlation/trace context theo chính sách để kết nối nhiều service.
5. **Tracing/metrics:** có thể liên hệ log với trace; hạn chế dùng requestId làm metric label vì cardinality lớn.

Ví dụ HTTP response thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: 9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f

{"orderId":"order-42","status":"PAID"}
~~~

Ví dụ HTTP response lỗi với JSON dạng Problem Details:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Request-ID: 9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f

{
  "type": "about:blank",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "The request could not be completed.",
  "requestId": "9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f"
}
~~~

Ví dụ là minh họa hợp đồng API, không phải nội dung bắt buộc của mọi response. **Body chỉ cần chứa requestId khi có giá trị cho client và đã thống nhất schema**; thêm vào header thường đơn giản hơn vì không đổi body của các API thành công, file download, stream hoặc response không có body như 204.

Đối với lỗi, không trả cho client exception message nội bộ, SQL, token, địa chỉ file, endpoint downstream hay stack trace. Client cần **mã lỗi an toàn và requestId**, còn chi tiết kỹ thuật thuộc hệ thống log được phân quyền.

## 4. Vòng đời của ID qua một HTTP request

Thiết kế nên xác định một **điểm có trách nhiệm** gắn ID ở biên đáng tin cậy:

~~~text
Request tới gateway / application
               |
               v
        Nhận hoặc tạo requestId
               |
               v
       Gắn vào request context
               |
               +----> MDC / structured logging
               |
               +----> response header
               |
               v
       Controller / service
               |
               +----> HTTP client / messaging downstream
               |
               v
       Tạo response (2xx/4xx/5xx)
               |
               v
          Dọn MDC / context
~~~

**Bắt đầu sớm:** tạo/gắn ID trước khi controller, service hoặc code ghi log nghiệp vụ chạy. Nên đặt response header trước khi response bị commit để cả xử lý lỗi cũng có cơ hội mang ID.

**Một lần trong một request:** tránh mỗi tầng tạo một ID khác nhau rồi ghi đè header. Nếu gateway đã phát ID chuẩn và hệ thống có chính sách tin cậy gateway, service có thể sử dụng hoặc ghi nhận ID đó; nếu không, tự tạo ID nội bộ và có mapping khi cần.

**Kết thúc đúng lúc:** trả lại hoặc dọn thread-local context để request tiếp theo trên cùng thread pool không “thừa hưởng” ID cũ.

**Qua nhiều hop:** thống nhất điểm phát ID và policy truyền nó. RequestId có thể là ID tại edge và được giữ giữa các service, trong khi spanId sẽ khác ở từng span; không lấy spanId làm định danh duy nhất cho tất cả các hop.

## 5. ID do client gửi lên có đáng tin không?

Không nên mặc nhiên tin các header **X-Request-ID**, **X-Correlation-ID** hoặc **traceparent** đến từ Internet. Client có thể cố tình:

- Dùng một ID giả trùng với request khác để làm rối log.
- Gửi chuỗi rất dài hoặc ký tự điều khiển gây log injection, lỗi parser hoặc phí lưu trữ lớn.
- Đưa dữ liệu cá nhân hoặc secret vào ID, khiến nó bị ghi lặp ở nhiều hệ thống.
- Tạo lượng ID cực lớn làm tăng cardinality nếu dùng làm metric tag.
- Gửi trace context không hợp lệ hoặc cố tạo quan hệ trace sai.

Các lựa chọn an toàn:

1. **Luôn tự tạo requestId ở public edge** bằng UUID ngẫu nhiên hoặc một định dạng opaque phù hợp. Ghi lại upstream ID riêng nếu thật sự cần và sau khi validate.
2. **Tin ID từ reverse proxy/gateway đáng tin** nếu hạ tầng đã xác thực nguồn, **loại bỏ header do Internet cung cấp tại proxy**, giới hạn độ dài/charset và quy định rõ header có thể đi qua.
3. Nếu buộc phải chấp nhận ID do client cấp, phải **kiểm tra định dạng, kích thước, tập ký tự, số header trùng, mức entropy hoặc chính sách chống lạm dụng**; ID vẫn chỉ là metadata không đáng dùng để cấp quyền.
4. Với **traceparent**, dùng parser/propagator theo chuẩn W3C của thư viện tracing, không tự sao chép hoặc format chuỗi tùy tiện.

Không nhét email, account number, session token hoặc user input thô vào correlationId. Một UUID ngẫu nhiên là ví dụ định danh thuận tiện, không phải bằng chứng danh tính hay quyền truy cập.

## 6. Ví dụ Java 17+ chạy độc lập: ID trong response khớp log

Ví dụ dùng **JDK HttpServer** từ module jdk.httpserver, **HttpClient** và **java.util.logging**. Chương trình tạo một HTTP server trên 127.0.0.1 với cổng hệ điều hành chọn tự động, gửi một request thực tới nó, rồi chứng minh header X-Request-ID **khớp đúng ID được ghi trong log server**.

Để kết quả kiểm thử ổn định, logger được gắn một Handler lưu message trong bộ nhớ. ID mỗi lần chạy là UUID mới nên chương trình **không in giá trị UUID cố định**; thay vào đó in các kết quả so khớp đúng/sai.

Tạo file **ResponseCorrelationDemo.java**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.io.OutputStream;
import java.util.UUID;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ResponseCorrelationDemo {
    private static final Logger LOG = Logger.getLogger("demo.web");
    private static final List<String> EVENTS = new CopyOnWriteArrayList<>();

    public static void main(String[] args) throws Exception {
        Handler memory = new Handler() {
            { setLevel(Level.ALL); }

            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    EVENTS.add(record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(memory);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/orders", exchange -> {
            String requestId = UUID.randomUUID().toString();
            exchange.getResponseHeaders().set("X-Request-ID", requestId);

            LOG.info("requestId=" + requestId
                    + " path=" + exchange.getRequestURI().getPath()
                    + " status=200");

            byte[] bytes = "ok".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/orders");

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .GET().build();

            HttpResponse<String> response = HttpClient.newHttpClient()
                    .send(request, HttpResponse.BodyHandlers.ofString());

            String returnedId = response.headers()
                    .firstValue("X-Request-ID").orElseThrow();

            System.out.println("status=" + response.statusCode());
            System.out.println("body=" + response.body());
            System.out.println("validId=" +
                    UUID.fromString(returnedId).toString().equals(returnedId));
            System.out.println("sameIdInLog=" + EVENTS.stream()
                    .anyMatch(e -> e.contains("requestId=" + returnedId)));
            System.out.println("logCount=" + EVENTS.size());
        } finally {
            server.stop(0);
            LOG.removeHandler(memory);
            memory.close();
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+ có module jdk.httpserver:

~~~bash
javac --add-modules jdk.httpserver ResponseCorrelationDemo.java
java --add-modules jdk.httpserver ResponseCorrelationDemo
~~~

**Stdout xác định** khi chương trình chạy thành công:

~~~text
status=200
body=ok
validId=true
sameIdInLog=true
logCount=1
~~~

Giải thích:

- Mỗi request tới /orders được gán UUID riêng bằng UUID.randomUUID().
- Server đặt X-Request-ID **trước** sendResponseHeaders(), giúp ID có mặt trong response.
- LOG.info ghi requestId và ngữ cảnh URL/status trong cùng một message; một Handler nội bộ thu bản ghi.
- Client đọc X-Request-ID, kiểm tra dạng UUID và tìm chính giá trị đó trong message đã ghi.
- HTTP server chạy trên loopback với port tự cấp nên không cần hard-code cổng; sau khi kiểm tra, server được stop và Handler được tháo ra.

**Giới hạn ví dụ:** chỉ có một HTTP request, response thành công, logging dùng bộ nhớ và không kiểm tra concurrency, proxy, error dispatch hoặc async tracing. Handler chỉ là công cụ kiểm chứng, không phải hệ thống log production và không cho biết dữ liệu đã được index hoặc lưu bền vững. Trong ứng dụng thực, nên dùng SLF4J + backend, context propagation và structured logging.

## 7. Spring Boot: OncePerRequestFilter gắn ID cho request và response

Với ứng dụng **Spring Boot dùng Spring MVC/Servlet (Spring Boot 3+ hoặc 4+ phù hợp)**, có thể dùng OncePerRequestFilter để gắn một requestId, đưa vào MDC của SLF4J, đặt response header và dọn context sau khi request được xử lý.

Ví dụ file **RequestIdFilter.java**, cần dependency Spring Web/Servlet và SLF4J tương thích:

~~~java
import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestIdFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Request-ID";
    public static final String ATTRIBUTE = "requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        // Public edge: chủ động tạo ID, không tin header client tùy ý.
        String requestId = UUID.randomUUID().toString();

        // Dùng chung cho error handler và các thành phần servlet.
        request.setAttribute(ATTRIBUTE, requestId);

        // Đặt sớm để response thường và nhiều error path có ID.
        response.setHeader(HEADER, requestId);

        // try-with-resources dọn context sau request hiện tại.
        try (MDC.MDCCloseable ignored =
                MDC.putCloseable(ATTRIBUTE, requestId)) {
            filterChain.doFilter(request, response);
        }
    }
}
~~~

Đây là **mã class đầy đủ nhưng cần đặt trong một Spring Boot application**, không phải chương trình Java độc lập chạy bằng javac không có dependency. Việc đăng ký filter bằng @Component có thể khác theo cách tổ chức dự án; không đăng ký **cùng filter hai lần** qua @Component và FilterRegistrationBean.

**Phần quan trọng:**

- request.setAttribute giúp controller/error handler cùng request truy cập ID mà không phụ thuộc trực tiếp vào MDC.
- response.setHeader nên chạy **trước** filterChain.doFilter; nếu đặt sau, response có thể đã được commit và không thể sửa header.
- MDC.putCloseable sử dụng scope và dọn MDC khi thoát, kể cả khi filterChain ném exception. Với MDC là context theo thread, dọn đúng giúp tránh rò ID sang request khác trên thread pool.
- Cách này **cố ý không nhận X-Request-ID do client gửi**, tránh spoofing. Trong môi trường có gateway phát ID, có thể thay bằng chính sách chỉ tin header được gateway chứng thực và validate.
- Vị trí/thứ tự filter rất quan trọng. Một lỗi xảy ra ở gateway, proxy, security filter **trước filter này**, hoặc một error handler riêng, có thể không nhận được header nếu chưa chạy filter.

**Giới hạn async:** OncePerRequestFilter mặc định không lọc các async dispatch sau và không tự làm ThreadLocal MDC đi qua các thread. Khi dùng Servlet async, CompletableFuture, @Async, scheduled task hoặc Reactor, phải thiết kế propagation riêng; không tuyên bố chỉ đặt một filter là đủ cho tất cả log bất đồng bộ.

## 8. Cấu hình để requestId hiện trong log của Logback và Log4j 2

MDC chứa requestId **không có nghĩa appender sẽ tự in trường đó**. Pattern hoặc JSON encoder phải được cấu hình để lấy đúng key.

### 8.1. Logback pattern

Ví dụ cấu hình tối thiểu trong **logback-spring.xml**:

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level requestId=%X{requestId:-} %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

Khi RequestIdFilter thêm MDC key requestId, mọi lời gọi log trên cùng thread sẽ mang trường này qua %X{requestId:-}. Nếu không có context, phần đó có thể trống theo pattern; một event log chạy ngoài HTTP request không nhất thiết có requestId.

Logback có thể dùng encoder JSON có cấu trúc thay cho text pattern. Khi dùng centralized logging, nên giữ field **requestId** riêng, có index hợp lý và truy vấn chính xác theo key thay vì tìm chuỗi tự do.

### 8.2. Log4j 2 pattern

Với backend Log4j 2, ví dụ **log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <PatternLayout
          pattern="%d{ISO8601} %-5p requestId=%X{requestId} %c - %m%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

Trong Log4j 2, ThreadContext/MDC đảm nhiệm việc lưu metadata cho thread; SLF4J MDC có thể được backend Log4j 2 tích hợp theo binding/provider đúng. Không copy cú pháp XML hoặc class Logback sang Log4j 2. Kiểm tra output thực tế vì logger name, context map và pattern có thể bị ảnh hưởng cấu hình khác.

### 8.3. Nếu đã dùng Micrometer Tracing

Spring Boot với Micrometer Tracing có thể thêm **traceId** và **spanId** vào MDC và correlation trong log, theo phiên bản/cấu hình. Khi đó nên tận dụng tracing đã có thay vì xây một hệ thống correlation cạnh tranh. Xác định rõ:

- API cần trả **X-Request-ID**, **X-Trace-ID** hay cả hai?
- Cấu trúc log có lưu mapping requestId ↔ traceId không?
- ID trong response có tương ứng đúng với **active span** của request không?
- Sampling có thể khiến trace không xuất ở tracing backend; log vẫn cần chính sách riêng.

Việc logger có traceId không đồng nghĩa response tự có X-Request-ID. Chúng là hai đường tích hợp khác nhau và cần kiểm thử.

## 9. Gắn requestId vào error response một cách nhất quán

Nhiều ứng dụng có API error JSON, ví dụ dùng Spring ProblemDetail. Có thể lấy requestId đã lưu bằng request.setAttribute() trong filter rồi đưa vào body lỗi.

Mã dưới đây là **fragment Spring Boot MVC**, cần nằm trong ứng dụng có RequestIdFilter và Spring Web. Nó minh họa cách trả body an toàn với requestId mà không tiết lộ nội dung exception:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ProblemDetail> unexpected(
            Exception exception,
            HttpServletRequest request) {

        Object requestId = request.getAttribute("requestId");

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
        problem.setTitle("Internal Server Error");
        problem.setDetail("The request could not be completed.");
        if (requestId != null) {
            problem.setProperty("requestId", requestId.toString());
        }

        // Ghi lỗi ở một vị trí đã được thống nhất để tránh log trùng.
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }
}
~~~

**Đây không phải mẫu error handling hoàn chỉnh:** exception có thể thuộc loại 400, 401, 403, 404 hoặc một status khác, không phải mọi exception đều nên trả 500. Trong production, thiết kế mapping exception/status theo chính sách nghiệp vụ và Spring Security; chỉ dùng mã cho lỗi chưa dự kiến khi phù hợp.

Một số lỗi xảy ra **trước controller**, trong proxy, filter đăng nhập, gateway hoặc quá trình parse request; @RestControllerAdvice không nhất thiết xử lý các lỗi đó. Vì vậy muốn response nào cũng có ID, cần triển khai và kiểm tra **tại tầng biên phù hợp**, không chỉ ở controller advice.

Khi ghi log exception, tránh ghi lặp stack trace ở controller, interceptor và error handler. Nên có một điểm ghi lỗi chính; các lớp còn lại bổ sung context khi cần. RequestId trong body và header phải **khớp nhau**, không tạo lại ID khi bắt exception.

## 10. CORS: frontend có đọc được X-Request-ID không?

Với frontend chạy khác origin, trình duyệt có thể nhận response nhưng JavaScript **không tự đọc được mọi custom response header**. Header X-Request-ID không thuộc nhóm CORS-safelisted response headers, nên cần cấu hình **Access-Control-Expose-Headers** để client truy cập nó khi được phép.

Ví dụ response ở API đã bật CORS hợp lệ:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: X-Request-ID
X-Request-ID: 9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f
Content-Type: application/json

{"status":"ok"}
~~~

Ở frontend:

~~~javascript
// Fragment minh họa trong trình duyệt.
const response = await fetch("https://api.example.test/orders/42");
const requestId = response.headers.get("X-Request-ID");
console.log("Support request ID:", requestId);
~~~

Cấu hình Allow-Origin/credentials phải tuân theo chính sách CORS riêng. **Access-Control-Expose-Headers chỉ cho phép JavaScript đọc header đã nhận**; nó không cấp quyền gọi API và không thay thế authentication/authorization. Đối với request có credentials, tránh dựa vào wildcard * để expose header vì semantics khác theo chuẩn.

Các HTTP client không bị cơ chế JavaScript CORS của browser chi phối như frontend web, nên có thể đọc custom header trực tiếp. Tuy nhiên proxy, CDN, ingress hoặc API gateway vẫn có thể xóa/đổi header.

## 11. Correlation với downstream response và distributed tracing

Trong hệ thống nhiều service:

~~~text
Client --(requestId=edge-1)--> Gateway
                                  |
                                  v
                               Service A
                                  |
                                  v
                               Service B
                                  |
                                  v
                               Database
                                  |
                                  v
Client <--(X-Request-ID=edge-1)---+
~~~

Nếu service A gọi service B qua HTTP, có hai nhu cầu:

- **RequestId do hệ thống quản lý:** truyền X-Request-ID đến các service **nội bộ đáng tin cậy** theo chính sách và log nó tại các hop. Đừng mù quáng truyền ID này tới URL không đáng tin hoặc qua bên thứ ba nếu chính sách dữ liệu không cho phép.
- **Distributed trace context:** dùng OpenTelemetry/Micrometer hoặc thư viện tương thích để truyền **traceparent** và có thể tracestate theo chuẩn W3C. TraceId thường giữ nguyên trên toàn trace; spanId thay đổi theo span.

Không cần tạo mới UUID ở mỗi service nếu mục tiêu là giữ cùng một correlationId xuyên chuỗi. Tuy nhiên **mỗi inbound request** có thể có requestId riêng, còn một business transaction lớn có thể có một ID khác ở tầng nghiệp vụ. Hãy nêu rõ contract, tránh nhầm ID.

Khi downstream trả lỗi hoặc timeout, service upstream nên ghi log với **ID local/edge** và trace context. Nếu cần lưu requestId của downstream, dùng trường riêng (ví dụ downstreamRequestId) để tránh ghi đè ID chính mà client sẽ đọc ở response của upstream.

Với retry, một request của client có thể sinh nhiều attempt tới downstream. Correlation ID liên kết chúng, nhưng nên có **attemptId** hoặc span riêng để phân biệt từng lần thử. Không suy ra một ID tương ứng đúng một bản ghi log.

## 12. Async, thread pool và reactive: vì sao MDC dễ mất?

MDC của SLF4J thường dựa trên **context gắn với thread**; một lời gọi trong controller có requestId không bảo đảm task ở một thread khác tự có requestId đó. Điều này ảnh hưởng:

- @Async, ExecutorService, CompletableFuture;
- Servlet async dispatch hoặc streaming response;
- Reactive stack Spring WebFlux/Reactor;
- Messaging consumer hoặc scheduled/background jobs;
- Một số kiểu xử lý concurrency và virtual threads.

Ví dụ:

~~~text
HTTP thread: requestId=A
      |
      +--> asynchronous job on worker thread
               |
               +--> MDC requestId rỗng nếu không propagate
~~~

Đối với Servlet, một OncePerRequestFilter có thể không chạy trên async dispatch theo hành vi mặc định. Nếu phải hỗ trợ async, cần kiểm tra dispatcher mapping, hành vi shouldNotFilterAsyncDispatch(), cơ chế lưu request attribute và propagation context của framework. Đừng chỉ override một phương thức mà bỏ qua cấu hình dispatcher types và cleanup, vì một request có thể chạy ở nhiều thread.

Đối với Reactor/WebFlux, ưu tiên **Reactor Context** hoặc cơ chế propagation được Micrometer/Tracing hỗ trợ thay vì dựa vào ThreadLocal thủ công xuyên các operator. Với task runner, nếu copy MDC map, phải khôi phục/dọn context trên worker sau task; không để request A làm nhiễm log request B.

**Nguyên tắc:** correlation ID phải đi cùng **ngữ cảnh xử lý**, không chỉ gắn với một thread trong toàn bộ vòng đời nghiệp vụ. Kiểm thử async là bắt buộc nếu hệ thống sử dụng nó.

## 13. Những status và đường lỗi cần bao phủ

Không chỉ thử một HTTP 200:

| Tình huống | Yêu cầu correlation |
| --- | --- |
| 200/201 thành công | Header có ID; log server có cùng ID |
| 204 No Content | Không cần body; header vẫn có thể chứa ID |
| 400 do validation | Error body an toàn và header cùng ID nếu xử lý ở app |
| 401/403 do security | Kiểm tra filter order; security/gateway có thể kết thúc trước app |
| 404 do routing | Nếu request vào app, cần xem filter/router xử lý ở tầng nào |
| 500 từ controller/service | Không sinh ID mới trong error handler; header và error body khớp |
| Timeout ở gateway | Có thể do gateway trả response, app không tạo được response |
| Streaming/SSE/file download | Header phải được đặt trước khi response commit |
| Async/background completion | Context cần truyền qua thread/dispatch, log cuối vẫn có ID |
| Preflight OPTIONS/CORS | Cần quy tắc riêng để expose header và xử lý CORS |
| Repeated/retried request | Mỗi request hoặc attempt phải có định danh theo contract |

Nếu server đã trả một phần response rồi mới lỗi, có thể không thay header/status nữa. Trong trường hợp đó log và metric phải ghi nhận lỗi phía server, nhưng không hứa client luôn có body lỗi chuẩn.

Nếu gateway tự trả 502/503/504, response ID có thể do **gateway** phát và không trùng ID của service nếu service chưa nhận request. Đây không phải lúc nào cũng là bug của application filter; cần thống nhất policy correlation ở edge.

## 14. Thiết kế dữ liệu log để dễ tìm theo response ID

Một log có cấu trúc có thể có:

~~~json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "ERROR",
  "service": "order-service",
  "requestId": "9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "http": {
    "method": "POST",
    "route": "/api/orders/{id}",
    "status": 500
  },
  "errorCode": "ORDER_BACKEND_UNAVAILABLE",
  "durationMs": 241
}
~~~

Đây là dữ liệu mẫu, không phải bản ghi thật. Trường route sử dụng **route template** thay vì nguyên URL chứa query string có thể mang PII. Mỗi event có thể bổ sung component, eventCode và outcome, nhưng không nên ghi body hay thông tin xác thực.

Trong hệ thống log tập trung, ưu tiên truy vấn theo trường:

~~~text
service = "order-service"
AND requestId = "9aa67e8d-a066-4e0a-92b7-61aa95fa0c9f"
~~~

Cú pháp truy vấn phụ thuộc backend (Loki/Elastic/OpenSearch/Cloud Logging...). Đây chỉ là biểu diễn logic, **không phải câu truy vấn có thể chạy trên mọi hệ thống**.

Một request ID có thể xuất hiện trong nhiều log event, nhiều service và nhiều attempt. Không đánh giá “một response phải có đúng một log line”. Đối chiếu theo cùng requestId và thêm traceId/spanId hoặc attemptId khi cần.

**Cardinality:** requestId có tính duy nhất cao. Phù hợp để ghi vào log field và tìm kiếm có hạn chế quyền; thường **không thích hợp làm metric label/tag** trên hệ thống time series vì có thể tạo số lượng chuỗi khổng lồ.

## 15. Bảo mật và quyền riêng tư

Correlation ID được trả ra bên ngoài, nên coi nó là một **mã tham chiếu không nhạy cảm**:

- Dùng random/opaque ID; không nhúng userId, email, orderId bí mật hoặc token phiên.
- Không dùng ID làm “khóa” để truy cập log hoặc tải file. Mọi trang hỗ trợ xem log vẫn phải xác thực và phân quyền.
- Không cho phép endpoint công khai “tra cứu bất kỳ requestId” rồi trả stack trace và PII; dễ tạo lỗ hổng truy xuất chéo.
- Nếu tin header từ gateway, bảo đảm gateway loại bỏ header giả từ client và validate nguồn/trạng thái trust.
- Giới hạn kích thước/header charset và sanitize giá trị trước khi ghi log, tránh log injection.
- Tránh log nguyên query string, Authorization, Cookie hoặc HTTP body chỉ để phục vụ correlation.
- Kiểm tra retention của request ID, log và trace theo mục đích; correlation giữa nhiều dữ liệu có thể trở thành khả năng liên kết danh tính.
- Hạn chế số bản copy correlation ID được gửi tới nhà cung cấp bên ngoài khi không cần.

Nếu ID bị phơi lộ, người ngoài không được vì thế mà biết nội dung request hay truy cập dashboard log. Tính an toàn không đến từ việc giữ requestId tuyệt mật; nó đến từ phân quyền thực sự và không chứa thông tin nhạy cảm trong ID.

## 16. Thiết kế kiểm thử tích hợp

Một bộ kiểm thử nên chạy với **server thật** (Spring Boot Test, MockMvc cộng kiểm thử header hoặc một kiểm thử HTTP end-to-end) và appender/collector thử nghiệm:

1. Gửi một HTTP 200; xác nhận response có X-Request-ID đúng định dạng, log có đúng requestId.
2. Gửi nhiều request liên tục và song song; ID khác nhau, không lẫn MDC giữa các thread.
3. Gửi request với header X-Request-ID bị giả, quá dài hoặc có ký tự không hợp lệ; kiểm tra policy sinh lại/validate.
4. Với các lỗi 400/401/403/404/500, kiểm tra header và body lỗi có cùng ID **ở những đường thực tế do application xử lý**.
5. Với API 204, file download và streaming, xác nhận header được đặt trước commit.
6. Bật CORS từ một origin hợp lệ; kiểm tra JavaScript đọc được X-Request-ID sau khi expose, và không mở quyền truy cập ngoài policy.
7. Qua reverse proxy/gateway, kiểm tra header không bị đổi/xóa ngoài dự định; với gateway-generated error, xác định ID từ gateway.
8. Qua async/Executor/Reactor, kiểm tra log downstream vẫn liên kết đúng context, không nhiễm giữa request A và B.
9. Qua nhiều service, đối chiếu X-Request-ID với traceId/traceparent và các request attempt.
10. Nếu dùng sampling hoặc async logging, kiểm tra vẫn có tín hiệu điều tra tối thiểu; không coi missing log do drop là lỗi response correlation duy nhất.
11. Kiểm tra ID không được dùng làm credential và không tiết lộ PII khi tra cứu.

**Ví dụ ma trận nghiệm thu:**

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Header response xuất hiện | Có X-Request-ID theo policy |
| Định dạng ID | Opaque, hợp lệ, giới hạn độ dài |
| Log tương ứng | Cùng requestId, có service/status phù hợp |
| Error body có ID | Khớp header nếu contract yêu cầu |
| Hai request khác nhau | ID không trùng trong phép thử, context được cleanup |
| Thread khác | Propagation theo thiết kế, không mất/nhầm ID |
| Gateway | Có quy tắc ID ở trường hợp gateway tự trả lỗi |
| Tra cứu | Nhân viên được phép tìm đúng log theo requestId |
| Bảo mật | Không truy xuất log chỉ vì sở hữu requestId |
| CORS | Frontend được phép đọc custom response header |

Không hard-code một UUID cụ thể làm kết quả kỳ vọng của chương trình sinh ID ngẫu nhiên. Tốt hơn, assert **header không rỗng, đúng định dạng, khớp log và không bị dùng lại ngoài phạm vi**.

## 17. Lỗi thường gặp và cách xử lý

### Response có ID nhưng log không thấy

Kiểm tra logging pattern có %X{requestId} không, MDC đã được set trước logger.info chưa, filter chạy đúng đường request không, request có đi qua async thread và collector có đang trễ/dropped event không. Đọc trực tiếp field từ structured log nếu có.

### Log có ID nhưng response không có

Header có được đặt trước khi commit không? Một exception, security filter, gateway hoặc CDN có trả response trước khi application filter chạy không? Proxy có strip header không? Với trình duyệt, header có thể tồn tại trên network nhưng không được JavaScript đọc vì thiếu Access-Control-Expose-Headers.

### Hai request liên tiếp dùng cùng ID

Có thể ThreadLocal/MDC bị rò khi không remove trong finally; hoặc server vô tình lưu UUID static cho mọi request. Kiểm tra nơi tạo ID, lifecycle và context cleanup. Cũng cần phân biệt trường hợp gateway chủ ý giữ một correlationId cho chuỗi request khác nhau.

### RequestId trong error body khác header

Thường do error handler tạo UUID mới, filter chạy nhiều lần, hoặc gateway sửa response header. Chọn một nguồn ID, lưu trong request attribute/context và tái sử dụng.

### Có ID ở controller nhưng mất ở @Async/CompletableFuture

MDC không tự đi qua worker thread. Sử dụng công cụ context propagation của framework, đảm bảo clear/restore ở cuối task và kiểm thử dưới concurrency.

### Sử dụng traceId nhưng không tìm thấy trace

Trace có thể bị sampling, exporter lỗi, span chưa kết thúc hoặc truy vấn sai môi trường. Correlation trong log có thể vẫn hoạt động nếu chính sách logging cho phép. Không đồng nhất “có traceId” với “có trace được lưu”.

### Log trùng hoặc tìm ra quá nhiều event

Cùng ID nên xuất hiện ở nhiều dòng hợp lệ; nhưng appender additivity, logging nhiều lần cùng exception hoặc retry có thể tạo duplicate. Đoạn client support cần có service, time window, route và attempt để lọc tiếp.

### Trả lại nguyên X-Request-ID mà client gửi

Có thể tạo ID chứa PII/chuỗi nguy hiểm hoặc làm giả tương quan. Cần chính sách trust rõ ràng và validate/generate tại biên.

## 18. Checklist triển khai

- [ ] Thống nhất response header (ví dụ X-Request-ID), format và điểm sinh ID.
- [ ] Phân biệt requestId, correlationId, traceId, spanId và business ID.
- [ ] ID opaque, không chứa PII hoặc secret; header từ Internet không được tin vô điều kiện.
- [ ] Tạo/gắn ID ở tầng đủ sớm, trước khi response commit.
- [ ] Dùng cùng ID trong response header, log và error body nếu có.
- [ ] Pattern/structured encoder đã bao gồm requestId; có khả năng truy vấn theo field.
- [ ] Dọn MDC trong finally/AutoCloseable; không rò context sang request khác.
- [ ] Có propagation chuẩn cho async/thread pool/Reactor hoặc Micrometer Tracing.
- [ ] Đã thử 2xx, 4xx, 5xx, security path, 204, streaming và gateway error.
- [ ] Frontend cross-origin được cấu hình Access-Control-Expose-Headers phù hợp.
- [ ] Downstream dùng trace context chuẩn và quy tắc propagation an toàn.
- [ ] Không trả stack trace, secret hoặc log nội bộ trong response.
- [ ] Không dùng requestId làm auth token hoặc metric label có cardinality cao.
- [ ] Có kiểm thử đa luồng, nhiều service, retry, proxy và collector delay.
- [ ] Đội hỗ trợ biết cách tra cứu log bằng ID nhưng phải tuân thủ phân quyền.

**Kết luận:** Correlation với response tạo **mối liên hệ có thể kiểm chứng giữa mã trả về cho client và log ở phía server**. Hãy phát ID an toàn tại biên, đặt vào header sớm, ghi thống nhất qua MDC/structured log, dọn context đúng cách và truyền qua downstream khi cần. Response chỉ nên chứa một mã tham chiếu hữu ích, không nên tiết lộ chi tiết lỗi nội bộ.

## 19. Tài liệu tham khảo

- [W3C Trace Context Recommendation](https://www.w3.org/TR/trace-context/): traceparent, tracestate, trace-id, span-id và quy tắc truyền trace context.
- [SLF4J MDC API](https://www.slf4j.org/apidocs/org/slf4j/MDC.html): put, putCloseable, remove và thông tin diagnostic context.
- [Spring Boot — Tracing and logging correlation](https://docs.spring.io/spring-boot/4.0/reference/actuator/tracing.html): Micrometer Tracing, traceId/spanId trong log và cấu hình correlation.
- [Spring Framework — OncePerRequestFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): filter lifecycle, async/error dispatch và phương thức doFilterInternal.
- [MDN — Access-Control-Expose-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Expose-Headers): cách cho JavaScript cross-origin đọc custom response headers.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): pattern layout và xuất MDC trong log.
- [Apache Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): xuất ThreadContext/MDC với %X.
- [Oracle Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): HTTP server dùng trong ví dụ.
- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client đọc response header và kiểm chứng kết quả.
