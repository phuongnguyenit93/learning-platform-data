# Request method trong Java Web Logging: ghi nhận HTTP method đúng và an toàn

## 1. Request method là gì và vì sao phải đưa vào log?

Một HTTP request có **method** (phương thức) biểu diễn hành động mà client yêu cầu server thực hiện với tài nguyên đích. Các method quen thuộc gồm GET, POST, PUT, PATCH, DELETE, HEAD và OPTIONS. Trong log ứng dụng web Java, method giúp trả lời những câu hỏi quan trọng:

- Endpoint đang nhận truy vấn (GET) hay yêu cầu thay đổi trạng thái (POST/PUT/PATCH/DELETE)?
- Vì sao cùng một đường dẫn /orders nhận 200 cho GET nhưng 405 cho một phương thức khác?
- Có yêu cầu không được phép, request CORS preflight, retry hoặc probe bất thường nào không?
- Lỗi 4xx/5xx và p95/p99 latency phân bố như thế nào theo method và route?
- Một trace/request ID đã đi qua method nào tại gateway, ứng dụng và downstream?

Một access log gọn, có cấu trúc có thể trông như sau:

~~~text
http_request method=GET route=/orders/{id} status=200 duration_ms=12 request_id=req-101
http_request method=POST route=/orders status=201 duration_ms=45 request_id=req-102
http_request method=DELETE route=/orders/{id} status=403 duration_ms=3 request_id=req-103
~~~

Các dòng trên là **minh họa**, không phải output mặc định của Java. Điểm đáng chú ý: phương thức được đặt ở **field riêng**, route là template do ứng dụng xác định, status là status HTTP, còn request_id giúp liên kết những dòng liên quan.

**Đừng đánh đồng method với tên Java method.** HTTP POST không phải lời gọi một hàm có tên post(); Spring @PostMapping là ánh xạ một HTTP method tới handler Java. Khi viết log, phải xác định rõ nguồn lấy HTTP method chứ không suy từ tên controller, annotation hoặc business action.

Bài thuộc nhóm **Logging trong ứng dụng web**. Trọng tâm là lấy, chuẩn hóa, ghi và sử dụng field request method trong Java logging mà không làm sai ngữ nghĩa HTTP, gây lộ dữ liệu hay tạo metric cardinality không kiểm soát.

## 2. HTTP method theo RFC: ý nghĩa và điều dễ nhầm

HTTP method là một token trong request. Các token method **phân biệt chữ hoa/chữ thường** theo HTTP Semantics; GET là phương thức chuẩn, còn get không tự động tương đương GET. Proxy, server hoặc framework có thể từ chối hay xử lý extension method theo cấu hình riêng.

| Method | Ý nghĩa tiêu biểu | Safe theo RFC? | Idempotent theo mặc định? | Gợi ý khi logging |
| --- | --- | --- | --- | --- |
| GET | Lấy biểu diễn của tài nguyên | Có | Có | Ghi GET và route template; không ghi query chứa token |
| HEAD | Như GET về metadata, nhưng không trả response content | Có | Có | Tách HEAD khỏi GET khi đo; đừng đếm response body size như GET |
| POST | Xử lý nội dung request theo ngữ nghĩa tài nguyên | Không | Không được bảo đảm | Không suy ra đã tạo tài nguyên chỉ từ method |
| PUT | Tạo/thay thế trạng thái tài nguyên đích theo ngữ nghĩa PUT | Không | Có | Retry có thể tạo nhiều access log nhưng cùng tác động dự kiến |
| PATCH | Áp dụng một tập thay đổi cho tài nguyên | Không | Không được bảo đảm | Đừng suy PATCH luôn idempotent; tùy cách thiết kế |
| DELETE | Yêu cầu xóa các biểu diễn hiện tại của tài nguyên | Không | Có | Lần lặp có thể trả status khác mà vẫn idempotent |
| OPTIONS | Hỏi các lựa chọn giao tiếp, thường gặp trong CORS preflight | Có | Có | Phân loại preflight để tránh nhầm với business traffic |
| TRACE | Yêu cầu loop-back message cho chẩn đoán HTTP | Có theo định nghĩa RFC | Có | Thường hạn chế/tắt vì rủi ro lộ thông tin; giám sát yêu cầu bất thường |
| CONNECT | Yêu cầu thiết lập tunnel tới đích | Không | Không được bảo đảm | Chủ yếu ở proxy; không mặc định là endpoint app thông thường |

**Safe** trong RFC nghĩa là client không yêu cầu thay đổi trạng thái theo ngữ nghĩa method. Nó **không có nghĩa** request đó không tạo ra bất kỳ side effect nào: server vẫn có thể sinh access log, counter, metric và cache activity.

**Idempotent** nghĩa là tác động dự kiến của nhiều yêu cầu giống hệt một yêu cầu, không có nghĩa server chỉ ghi đúng một access log. Một DELETE được gửi ba lần có thể xuất ba access event, dù hành động xóa có ngữ nghĩa idempotent. Status trả về của từng lần vẫn có thể khác nhau.

POST có thể được ứng dụng thiết kế idempotent bằng idempotency key, nhưng tính chất đó không tự có chỉ từ tên method. PATCH có thể hoặc không idempotent tùy tài liệu và định nghĩa patch. Không nên suy luận kết quả nghiệp vụ chỉ từ cột method trong log.

### Status 405 và 501

Theo HTTP Semantics:

- **405 Method Not Allowed**: phương thức được server nhận biết/triển khai nhưng **không được phép trên target resource**. Response 405 phải chứa header Allow liệt kê các method được hỗ trợ cho tài nguyên.
- **501 Not Implemented**: phương thức không được server nhận biết hoặc không được triển khai; RFC khuyến nghị status này cho trường hợp đó.

Một framework hoặc reverse proxy có thể tự trả 405/501 trước khi request tới controller. Vì vậy, nếu chỉ log bên trong controller, bạn có thể bỏ lỡ hoàn toàn các request bị chặn ở tầng trước.

### HTTP/2 và HTTP/3

Trong HTTP/2, method được biểu diễn bằng pseudo-header :method trên giao thức. Ứng dụng Java Servlet thường vẫn nhìn thấy method qua API chuẩn (HttpServletRequest.getMethod()), không cần tự đọc pseudo-header hay cố tái tạo request line HTTP/1.1. Ghi method từ API request đã được server/container parse phù hợp hơn ghi một header tùy ý do client tự khai.

## 3. Field nào nên đi cùng request method?

Một event web request phục vụ vận hành thường có các field sau:

~~~json
{
  "timestamp": "2026-11-10T03:00:00Z",
  "event_type": "HTTP_REQUEST_COMPLETED",
  "service": "orders-api",
  "method": "GET",
  "route": "/orders/{id}",
  "status": 200,
  "duration_ms": 12,
  "request_id": "req-101",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
~~~

Đây là **schema minh họa**, không phải output tự động của JUL, Servlet hay Spring. Có thể cần thêm response size, protocol, client class, outcome hoặc error category theo mục đích.

| Field | Nguồn nên dùng | Lưu ý |
| --- | --- | --- |
| method | HTTP request method do server/container parse | Dùng giá trị quan sát tại tầng xác định; không lấy từ header tùy ý |
| route | Route template do router/framework xác định | /orders/{id}, không phải /orders/42?token=... |
| status | Kết quả HTTP cuối cùng khi request hoàn tất | Exception/async có thể làm status ban đầu chưa phải cuối cùng |
| duration_ms | Đồng hồ đơn điệu cho thời gian trôi | Dùng System.nanoTime cho elapsed; không dùng timestamp wall clock để trừ bừa |
| request_id | ID do hệ thống tin cậy cấp hoặc ID đã được validate | Không dùng trực tiếp token bất kỳ từ client |
| trace_id | Trace context hợp lệ nếu có | Không chứng minh danh tính người dùng |
| service | Cấu hình deployment/application | Tránh lấy service name trực tiếp từ user input |
| outcome | Success/failure theo định nghĩa có chủ đích | 4xx có thể là expected client error, không phải bug |
| request_bytes/response_bytes | Kích thước thực sự đo được ở tầng phù hợp | Content-Length không luôn phản ánh bytes thực chuyển |

**Chỉ method không đủ kết luận request có thành công.** POST status=201, POST status=400 và POST status=500 là ba kết quả khác nhau. Để debug, cần kết hợp method, route, status, latency, trace/request ID và error category mà không đưa payload nhạy cảm vào log.

## 4. Cách lấy HTTP request method trong Java

### 4.1. Jakarta Servlet: HttpServletRequest.getMethod()

Trong ứng dụng Servlet/Jakarta EE/Spring MVC, API thường dùng là:

~~~java
// Snippet cần Jakarta Servlet API; không chạy độc lập bằng JDK.
String httpMethod = httpServletRequest.getMethod();
~~~

Với Jakarta Servlet, interface thuộc package jakarta.servlet.http.HttpServletRequest. Ứng dụng cũ có thể dùng javax.servlet.http.HttpServletRequest; phải chọn namespace đúng phiên bản framework/server đang sử dụng.

getMethod() trả về tên phương thức của HTTP request mà Servlet container nhận biết, ví dụ GET hoặc POST. Đây là dữ liệu lấy từ request được xử lý ở tầng container, **không phải giá trị từ request.getParameter("method")**. Tuy nhiên, vì đầu vào cuối cùng vẫn đến từ client, method và các method tùy biến vẫn cần kiểm soát khi dùng làm label hoặc log text.

### 4.2. Java HTTP Server trong JDK

Module jdk.httpserver của JDK cung cấp com.sun.net.httpserver.HttpExchange.getRequestMethod(). Nó rất phù hợp cho ví dụ Java 17 không cần thư viện ngoài:

~~~java
// Snippet nằm bên trong HttpHandler của JDK HttpServer.
String method = exchange.getRequestMethod();
~~~

HttpExchange mô tả request tới một HTTP server tối giản trong JDK. Nó **khác HttpServletRequest** và không thay thế một Servlet container production hay Spring MVC. Ví dụ hoàn chỉnh ở mục 7 sử dụng API này.

### 4.3. Spring MVC/Spring Boot

Trong controller Spring MVC:

~~~java
// Snippet Spring MVC; cần Spring Web và method parameter từ framework.
@GetMapping("/orders/{id}")
public ResponseEntity<String> getOrder(
        HttpServletRequest request,
        @PathVariable String id) {
    String observedMethod = request.getMethod();
    return ResponseEntity.ok("order");
}
~~~

Đoạn này là snippet, không phải ứng dụng Spring Boot chạy độc lập. Một controller chỉ quan sát những request được route tới chính handler đó; các request bị từ chối bởi gateway, Spring Security, CORS hoặc servlet filter có thể không tới controller. Muốn có access log **nhất quán cho mọi route**, cân nhắc filter, interceptor hoặc access logging của web server/gateway.

Spring WebFlux dùng mô hình request khác (ví dụ ServerHttpRequest.getMethod()), không copy trực tiếp Servlet filter sang reactive stack. Trong reactive/async request, cần đo tại điểm hoàn tất của publisher/response, không giả định lúc handler method trả về là lúc response đã được gửi xong.

## 5. Method không phải chuỗi log tùy ý

Theo HTTP, method có dạng token. Server thường đã kiểm tra cú pháp ở tầng HTTP parser, nhưng một extension method vẫn có thể tạo giá trị hiếm hoặc không mong muốn. Nếu bạn dùng raw method làm metric label, tên file, tên logger hoặc route, nguy cơ phát sinh high-cardinality hoặc injection/cấu hình sai sẽ tăng.

Một hàm **phân loại cho mục đích log/metric** có thể là:

~~~java
// Snippet Java 17. Không dùng hàm này để quyết định authorization.
static String methodBucket(String raw) {
    if (raw == null) {
        return "OTHER";
    }
    return switch (raw) {
        case "GET", "POST", "PUT", "PATCH", "DELETE",
             "HEAD", "OPTIONS", "TRACE", "CONNECT" -> raw;
        default -> "OTHER";
    };
}
~~~

Ưu điểm:

- Chỉ các nhãn được thiết kế trước xuất hiện trong histogram hoặc dashboard.
- Không tạo một loại metric cho mỗi method lạ.
- Không tự động viết lại method “get” thành “GET”, bởi HTTP method là case-sensitive.
- Không để giá trị untrusted chọn file đích, index hay logger category tự do.

**Lưu ý quan trọng:** methodBucket chỉ dùng cho **đầu ra log/aggregation**. Việc quyết định request GET có được cho phép hay không vẫn dùng method gốc hoặc kết quả dispatch từ HTTP server. Nếu thay method gốc bằng OTHER trước lúc routing, bạn có thể mất thông tin để trả 405/501 đúng hoặc khiến cơ chế bảo mật hiểu sai.

Nếu cần phục vụ điều tra security request có method bất thường, có thể lưu một field raw_method riêng **đã được escape và giới hạn độ dài**, trong luồng có quyền phù hợp. Tránh cho giá trị đó trở thành metric label có cardinality không kiểm soát.

## 6. Lúc nào ghi access log?

Có ba thời điểm khác nhau:

1. **Khi nhận request:** ghi request_started, biết method nhưng chưa biết kết quả. Hữu ích để điều tra request bị treo.
2. **Khi ứng dụng quyết định status:** biết business routing, validation/exception dự kiến; nhưng response có thể chưa được gửi hoàn tất.
3. **Khi request/response hoàn tất tại một tầng quan sát:** có thể báo status và elapsed time thực tế của tầng đó. Đây thường là vị trí phù hợp cho access log tổng kết.

Nếu bắt đầu bằng:

~~~text
request method=POST route=/orders status=201
~~~

**trước khi commit response**, rồi có lỗi socket khi ghi response body, log đó chưa chứng minh client đã nhận response 201 hoàn chỉnh. Cần đặt tên field như status_decided, status_written hoặc status_observed cho đúng mốc.

Nên có tên event nhất quán, ví dụ:

~~~text
HTTP_REQUEST_STARTED
HTTP_RESPONSE_STATUS_DECIDED
HTTP_REQUEST_COMPLETED
HTTP_REQUEST_ABORTED
~~~

Không nhất thiết phải log cả bốn event cho mỗi request. Nhiều hệ thống chỉ cần một request completed log và tracing/metrics. Đừng tăng số log không cần để thể hiện vòng đời mà telemetry khác đã đủ.

### Duration: không dùng đồng hồ lịch để đo elapsed

Dùng:

~~~java
// Snippet Java 17.
long startNanos = System.nanoTime();
try {
    handleRequest();
} finally {
    long elapsedMs =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startNanos);
    // Ghi elapsedMs theo logger/format được thiết kế.
}
~~~

Đây là snippet, handleRequest() là một phần của ứng dụng thật. System.nanoTime là nguồn thích hợp để đo **khoảng thời gian trôi** trong cùng JVM; không dùng nó làm timestamp tuyệt đối để lưu log. Timestamp của event nên lấy từ Instant/clock tương ứng. Nếu cần p95/p99 chính xác ở độ trễ rất nhỏ, có thể dùng microseconds hoặc histogram đơn vị nhỏ hơn.

## 7. Ví dụ Java 17 chạy độc lập: ghi method bằng JUL và gửi HTTP request thử nghiệm

Ví dụ này dùng JDK 17, gồm:

- HttpServer (module jdk.httpserver) nhận GET và POST.
- HttpExchange.getRequestMethod() lấy method thực từ HTTP request.
- JUL java.util.logging.Logger ghi field method, route và status_decided.
- HttpClient gửi tuần tự hai request tới **127.0.0.1** ở port được hệ điều hành cấp tự động.
- Handler JUL hiển thị một dòng cho mỗi event; không có timestamp hay port động nên output xác định.
- Ví dụ **không ghi header, query, request body hoặc credential** vào log.

**Tệp: RequestMethodLoggingDemo.java**

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
import java.util.List;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class RequestMethodLoggingDemo {
    private static final Logger ACCESS =
            Logger.getLogger("example.web.access");

    private static final Set<String> KNOWN = Set.of(
            "GET", "POST", "PUT", "PATCH", "DELETE",
            "HEAD", "OPTIONS", "TRACE", "CONNECT");

    private static String bucket(String raw) {
        return KNOWN.contains(raw) ? raw : "OTHER";
    }

    private static void handle(HttpExchange exchange)
            throws IOException {
        try {
            String rawMethod = exchange.getRequestMethod();
            String method = bucket(rawMethod);

            int status;
            String reply;
            if ("GET".equals(rawMethod)) {
                status = 200;
                reply = "order-list";
            } else if ("POST".equals(rawMethod)) {
                status = 201;
                reply = "created";
            } else if (KNOWN.contains(rawMethod)) {
                status = 405;
                reply = "method-not-allowed";
                exchange.getResponseHeaders()
                        .set("Allow", "GET, POST");
            } else {
                status = 501;
                reply = "not-implemented";
            }

            // Nhận hết request body nhưng KHÔNG log payload.
            exchange.getRequestBody()
                    .transferTo(OutputStream.nullOutputStream());

            // Ghi quyết định trước khi gửi response:
            // status_decided KHÔNG phải chứng nhận client đã nhận.
            ACCESS.info("request method=" + method
                    + " route=/orders status_decided=" + status);

            byte[] bytes = reply.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream body = exchange.getResponseBody()) {
                body.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        // Sink JUL tối giản để có output lặp lại được.
        Handler output = new Handler() {
            {
                setLevel(Level.INFO);
            }

            @Override
            public synchronized void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush(); // Không đóng System.out.
            }
        };
        ACCESS.setUseParentHandlers(false);
        ACCESS.setLevel(Level.INFO);
        ACCESS.addHandler(output);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/orders",
                RequestMethodLoggingDemo::handle);
        server.start();

        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/orders");
            HttpClient client = HttpClient.newHttpClient();

            for (String method : List.of("GET", "POST")) {
                HttpRequest.Builder builder =
                        HttpRequest.newBuilder(uri);

                HttpRequest request = "POST".equals(method)
                        ? builder.POST(
                                HttpRequest.BodyPublishers
                                        .ofString("{}")).build()
                        : builder.GET().build();

                HttpResponse<String> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8));

                ACCESS.info("client method=" + method
                        + " status=" + response.statusCode()
                        + " body=" + response.body());
            }
        } finally {
            server.stop(0);
            ACCESS.removeHandler(output);
            output.flush();
            output.close();
        }
    }
}
~~~

**Biên dịch và chạy từ thư mục chứa file** bằng JDK 17 trở lên:

~~~bash
javac --add-modules jdk.httpserver -encoding UTF-8 RequestMethodLoggingDemo.java
java --add-modules jdk.httpserver RequestMethodLoggingDemo
~~~

**Stdout kỳ vọng, với máy cho phép mở loopback socket:**

~~~text
request method=GET route=/orders status_decided=200
client method=GET status=200 body=order-list
request method=POST route=/orders status_decided=201
client method=POST status=201 body=created
~~~

### Vì sao output có thứ tự ổn định?

Vòng for gửi GET rồi mới gửi POST bằng HttpClient.send (đồng bộ). Trong mỗi request, handler server ghi status_decided **trước khi** gửi response headers và body; client chỉ ghi dòng client sau khi HttpClient đã nhận response. Vì vậy hai event của GET xuất hiện trước hai event của POST, không phụ thuộc số port tự chọn. Handler tự in message, không thêm timestamp/thread động.

### Vì sao dùng status_decided?

Response thực có thể thất bại giữa lúc server đã chọn 200 và lúc client nhận đủ body. Trong demo, mục tiêu là quan sát method/routing và output xác định, nên tên status_decided phản ánh đúng mốc. Trong hệ thống production, access log tổng kết thường nên đo ở tầng container/gateway sau khi request hoàn thành và ghi outcome thích hợp cho request lỗi/aborted.

### Một số chi tiết về kỹ thuật

- KNOWN chỉ là tập method được dùng trong ví dụ để phân loại; hệ thống thật có thể hỗ trợ extension method hoặc những policy khác. Không dùng danh sách này làm tường lửa.
- bucket() giữ nhãn log có cardinality nhỏ; server vẫn dùng rawMethod để dispatch và phân biệt 405/501.
- Route /orders trong event là một **literal do server định nghĩa**, không phải request URI có thể chứa query hay dữ liệu cá nhân.
- Mã dùng localhost nhằm tránh request ra Internet hoặc dịch vụ khác. Port 0 cho hệ điều hành chọn cổng trống; port đó không được ghi vào stdout.
- Handler JUL ở đây là công cụ học tập; appender production cần hỗ trợ formatting, concurrent logging, lỗi I/O và shutdown theo framework.
- Chương trình đọc hết request body để xử lý connection hợp lý nhưng cố ý không ghi nội dung body. Production còn phải giới hạn kích thước đầu vào và đặt timeout để tránh client giữ connection vô hạn.
- Content-Type được chọn rõ; các response của ví dụ có body non-empty. Với HEAD/204/304 cần tuân theo quy tắc riêng về response content.

**Giới hạn:** Đây là server demo, không phải lựa chọn production thay cho Tomcat, Jetty, Undertow hoặc Spring Boot. Không dùng code ví dụ để triển khai public endpoint hoặc khẳng định nó đã có đầy đủ giới hạn request size, bảo vệ DoS, TLS, auth, tracing và graceful shutdown.

## 8. Jakarta Servlet Filter: ghi method cho nhiều route

Một Filter có thể quan sát request trước khi gọi handler và ghi sau khi FilterChain xử lý. Dưới đây là snippet đầy đủ cấu trúc cho ứng dụng Jakarta Servlet, nhưng **cần Jakarta Servlet API và container phù hợp**; không chạy độc lập bằng javac không có dependency.

**Tệp: RequestMethodLogFilter.java**

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;

public final class RequestMethodLogFilter implements Filter {
    private static final Logger LOG =
            Logger.getLogger(RequestMethodLogFilter.class.getName());

    private static String methodLabel(String raw) {
        return switch (raw) {
            case "GET", "POST", "PUT", "PATCH", "DELETE",
                 "HEAD", "OPTIONS", "TRACE", "CONNECT" -> raw;
            default -> "OTHER";
        };
    }

    @Override
    public void doFilter(ServletRequest request,
                         ServletResponse response,
                         FilterChain chain)
            throws IOException, ServletException {

        if (!(request instanceof HttpServletRequest http)
                || !(response instanceof HttpServletResponse res)) {
            chain.doFilter(request, response);
            return;
        }

        long started = System.nanoTime();
        boolean returnedNormally = false;

        try {
            chain.doFilter(request, response);
            returnedNormally = true;
        } finally {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            String statusObserved =
                    http.isAsyncStarted() ? "ASYNC_PENDING"
                    : returnedNormally
                        ? Integer.toString(res.getStatus())
                        : "UNRESOLVED";

            LOG.info(() -> "http_filter"
                    + " method=" + methodLabel(http.getMethod())
                    + " status_observed=" + statusObserved
                    + " elapsed_ms=" + elapsedMs);
        }
    }
}
~~~

**Giải thích giới hạn của filter:**

1. Filter phải được **đăng ký** theo web.xml, @WebFilter hoặc cơ chế cấu hình framework. Chỉ có file class chưa khiến filter tự chạy.
2. request.getMethod() lấy method từ Servlet request; không lấy từ request parameter.
3. System.nanoTime() dùng cho elapsed, không phải timestamp. Giá trị elapsed_ms ở đây chỉ bao phủ **đoạn chain.doFilter trong lần dispatch đó**.
4. Nếu chain ném exception, status cuối có thể được container đổi thành 500 **sau khi** finally chạy. Để tránh ghi “200 cuối cùng” sai, ví dụ gắn UNRESOLVED khi có exception.
5. Nếu request bắt đầu async, chain.doFilter có thể trở về trước khi response hoàn tất. Ví dụ đánh dấu ASYNC_PENDING, **không gọi đó là request completed**. Production cần AsyncListener/observation lifecycle phù hợp nếu muốn log kết quả cuối.
6. Với forward, include và ERROR dispatch, filter có thể chạy nhiều lần tùy mapping/dispatcher types. Cần tránh đếm trùng bằng thiết kế dispatch/once-per-request cụ thể; đừng suy rằng mỗi lần Filter.doFilter là một request mạng duy nhất.
7. Ví dụ không log raw URI vì route template có thể chưa được xác định khi filter chạy. Nếu cần route, hãy lấy sau khi router khớp ở tầng có thông tin đáng tin cậy.
8. Với ứng dụng dùng javax.servlet trước Jakarta EE 9, package import phải đổi. Không trộn javax.servlet với jakarta.servlet trong cùng code nếu server không tương thích.

Trong Spring MVC, một lựa chọn khác là HandlerInterceptor hoặc observation/metering do framework cung cấp. Một interceptor biết handler mapping nhưng request có thể bị chặn **trước khi** interceptor chạy. Do đó vị trí quan sát phải phù hợp mục đích: access log ở gateway/container để nhìn toàn bộ traffic, filter/interceptor ở ứng dụng để bổ sung route/trace và thông tin nghiệp vụ.

## 9. Spring MVC: route template và method

Nếu ứng dụng Spring Boot có controller:

~~~java
// Snippet cần Spring Web MVC.
@RestController
@RequestMapping("/orders")
class OrderController {
    @GetMapping("/{id}")
    ResponseEntity<String> find(@PathVariable String id) {
        return ResponseEntity.ok("found");
    }

    @PostMapping
    ResponseEntity<String> create() {
        return ResponseEntity.status(201).body("created");
    }
}
~~~

Cùng đường dẫn /orders có thể phục vụ POST, còn /orders/{id} phục vụ GET. Logging theo **method + route template** giúp gom nhóm đúng, thay vì chỉ dựa vào path nguyên văn.

Trong Spring MVC, route template đã khớp có thể được cung cấp qua request attribute theo HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE:

~~~java
// Snippet Spring MVC, sau khi HandlerMapping đã xác định route.
Object value = request.getAttribute(
        org.springframework.web.servlet.HandlerMapping
                .BEST_MATCHING_PATTERN_ATTRIBUTE);
String route = value instanceof String template
        ? template
        : "UNMAPPED";
~~~

Đoạn trên không chạy độc lập; biến request là HttpServletRequest trong context Spring MVC. Phải thực hiện **đúng thời điểm**: một Filter nằm trước HandlerMapping thường chưa có thuộc tính này. Interceptor hoặc lifecycle hook sau khi route được match có thể quan sát route; cũng phải quan tâm async và exception.

### Không nên log raw URL một cách mù quáng

So sánh:

~~~text
method=GET path=/customers/12345?email=user@example.com&token=secret
method=GET route=/customers/{id}
~~~

Dòng thứ nhất có định danh cá nhân và query có thể chứa secret; dòng thứ hai vẫn giúp đo endpoint mà không phơi payload. Nếu phải giữ request target để điều tra, hãy dùng allowlist/redaction, giới hạn độ dài, escape control characters, phân quyền và retention phù hợp.

**Route template không tự đủ cho truy vết một request cụ thể.** Kết hợp request_id/trace_id và error category; không biến user ID/order ID thành một metric label nếu số giá trị có thể tăng vô hạn.

### Logging sẵn có của container/gateway

Tomcat, Jetty, reverse proxy và load balancer có thể có access log riêng, được phát ra ngay cả khi Java controller không được gọi. Một ứng dụng nên quyết định nguồn **canonical access log** và đường liên kết trace để tránh một request bị tính hai hay ba lần do gateway + container + filter đều ghi như nhau.

Nếu cần log riêng ở mỗi hop, dùng field như observer=api-gateway, observer=servlet-container, observer=service để biết dòng nào quan sát ở tầng nào. Số lần log không đồng nghĩa số request nghiệp vụ duy nhất.

## 10. Request method override: client nói gì, server xử lý gì?

Một số stack hỗ trợ “method override” nhằm tương thích HTML form hoặc client cũ, ví dụ một POST có tham số _method=DELETE hoặc header X-HTTP-Method-Override được **một filter đặc biệt đã cấu hình** diễn giải.

Điều cần phân biệt:

- **Wire/original method:** method do server HTTP parser nhận ở phía ngoài, ví dụ POST.
- **Effective method:** method mà framework dùng để route sau bước override hợp lệ, ví dụ DELETE.
- **Client-declared override:** giá trị param/header chưa chắc đã được tin cậy hoặc thực thi.

Ví dụ minh họa sau:

~~~text
wire_method=POST
effective_method=DELETE
route=/orders/{id}
status=204
override_applied=true
~~~

Đây là một event giả lập trong hệ thống có override được bật; **không phải mọi server Java đều tự động làm điều này**. Đừng ghi phương thức “DELETE” chỉ vì client gửi header tùy ý nhưng server thực tế vẫn xử lý POST.

### Lựa chọn logging khi có override

- Gateway/access log ở ngoài cùng có thể ghi wire method.
- Application logging sau filter override có thể thấy effective method tùy thứ tự filter/wrapper.
- Khi điều tra hành vi bảo mật, đôi khi cần cả hai field, nhưng chúng phải được tạo bởi **các tầng quan sát đáng tin**, không phải giá trị do client tự gắn nhãn.
- Authorization/CSRF/idempotency phải dựa trên effective semantics thực sự của routing, không dựa trên field dùng để xuất log.

Một log rõ nguồn phương thức giúp giải thích sự khác nhau giữa đường request tại gateway và handler Spring. Không tự so sánh hai field từ các hop khác nhau rồi khẳng định xảy ra gian lận nếu có một filter override hợp lệ ở giữa.

## 11. Những trường hợp đặc biệt cần tách trong log

### 11.1. HEAD

HEAD về ngữ nghĩa lấy metadata tương ứng GET nhưng không gửi response content. Một số framework xử lý HEAD tự động qua route GET; có framework định nghĩa handler riêng.

- Khi client gửi HEAD, **method trong access log vẫn nên là HEAD**.
- Không cộng response body size như GET nếu body thực tế bị bỏ.
- HEAD có thể có status/headers tương tự GET theo HTTP Semantics; đừng giả định backend đã xử lý GET chỉ vì cùng handler.
- Kiểm tra body suppression ở gateway/container nếu cần tính bytes sent.

### 11.2. OPTIONS và CORS preflight

Trình duyệt có thể gửi OPTIONS preflight trước một request cross-origin thực tế. Một luồng có thể là:

~~~text
OPTIONS /orders 204  # preflight theo cấu hình server
POST    /orders 201  # actual request
~~~

Một OPTIONS preflight **không tự chứng minh** browser đã gửi POST sau đó. CORS middleware, gateway hoặc container có thể trả preflight mà không tới controller. Nếu chỉ đếm request trong app controller, dashboard có thể bỏ qua phần OPTIONS này.

Khi đo error rate/latency, có thể phân nhóm preflight và actual request; nhưng đừng tự loại OPTIONS khỏi toàn bộ security logging nếu đang phân tích tấn công/quét endpoint. Tùy mục đích, preflight có thể được quan sát riêng trong access metrics.

### 11.3. TRACE

RFC định nghĩa TRACE dùng để loop-back thông điệp HTTP. Vì phản hồi có thể làm lộ header hoặc dữ liệu nhạy cảm, nhiều triển khai vô hiệu hóa TRACE. Việc thấy TRACE trong access log có thể là dấu hiệu probe cần xem xét, nhưng không tự động là một exploit thành công.

Không đưa các request header nhạy cảm vào log chỉ vì TRACE xuất hiện. Kiểm tra cấu hình server/gateway và policy cho phép method ở từng route.

### 11.4. CONNECT

CONNECT thường gặp ở HTTP proxy để thiết lập tunnel; ứng dụng REST thông thường có thể không chấp nhận. Một proxy có thể xử lý CONNECT trước lớp Servlet. Vì vậy access log ở tầng proxy mới có thể chứa đầy đủ CONNECT, còn app backend không thấy.

Không suy từ việc backend không có CONNECT log rằng hệ thống edge chưa từng nhận method này.

### 11.5. Unknown/extension method

HTTP cho phép các method mở rộng. Một request với method lạ có thể được server chặn sớm hoặc đi vào handler mặc định. Nếu bạn chỉ dùng enum được hardcode, hãy tách:
- **Giá trị method thực** trong request processing.
- **Method bucket** dùng cho log aggregation/metrics, ví dụ OTHER.
- **Chính sách server** đối với unsupported methods, 405/501 tùy trường hợp.

Đừng viết một switch “OTHER → GET” để tiếp tục vì dễ thay đổi ngữ nghĩa request và tạo lỗ hổng authorization.

## 12. Bảo mật và quyền riêng tư khi ghi method

Chỉ một method GET/POST tự nó thường không chứa nhiều dữ liệu cá nhân. Nhưng **những field đi kèm** có thể chứa thông tin nhạy cảm hoặc gây nguy cơ log forging:

- URL có query string chứa email, token, API key, session identifier.
- Header Authorization, Cookie, Set-Cookie, request body, form data.
- User-Agent, Referer hoặc X-Forwarded-For có dữ liệu do client đưa vào.
- Exception message có thể chứa raw request/payload.
- MDC request_id hoặc user_id có thể bị tiêm từ nguồn không đáng tin.
- Path segment là account ID, email hoặc thông tin nghiệp vụ định danh.

**Nguyên tắc:** log method, route template, status, duration và ID có kiểm soát; không log toàn bộ request “để tiện debug” một cách mặc định. Sự kiện cần điều tra có thể dùng trường bổ sung trong luồng có phân quyền và thời hạn giữ phù hợp.

### Log injection

Nếu appender ghi text trực tiếp từ path/header, CR/LF hoặc ký tự điều khiển có thể làm méo ranh giới dòng log. Method raw cũng là dữ liệu từ request parser; với method lạ, luôn giới hạn/escape trước khi đưa vào field text hoặc metric. Dùng JSON encoder đã được kiểm thử nếu cần structured logging.

**Placeholder không phải sanitizer:** SLF4J log.info("method={}", rawMethod) giúp định dạng tham số nhưng không tự bảo đảm mọi value có CR/LF được escape khi layout cuối là text. Với method canonical từ allowlist, rủi ro giảm; với giá trị untrusted khác, cần neutralization theo format.

### CSRF và authorization không thể suy ra chỉ từ method

GET nên tuân thủ safe semantics, nhưng một route GET thực hiện xóa dữ liệu là bug thiết kế. POST không mặc định có nghĩa client được quyền tạo tài nguyên. Kiểm soát authorization, CSRF, CORS và rate limiting phải dựa trên chính sách server, không dựa trên access log.

Không biến log method thành “bằng chứng” rằng một thay đổi trạng thái đã được commit. Một request POST có thể thất bại sau khi server quyết định status, hoặc request retry có thể tạo các event giống nhau. Nếu cần sự kiện nghiệp vụ bền vững, phải có cơ chế transaction/outbox/audit phù hợp.

## 13. Method trong metric: cardinality và cách nhóm

Một tập metric hữu ích có thể là:

~~~text
http_server_requests_total{method="GET",route="/orders/{id}",status_class="2xx"}
http_server_requests_total{method="POST",route="/orders",status_class="2xx"}
http_server_requests_total{method="OTHER",route="UNMAPPED",status_class="4xx"}
~~~

Đây chỉ là **minh họa mô hình nhãn**; tên metric cụ thể và cách phát sinh phụ thuộc OpenTelemetry/Micrometer/Prometheus hoặc hệ thống của bạn. Giá trị label đặt trong dấu quote.

Các nhãn nên thuộc tập có giới hạn:

| Nhãn | Lý do hữu ích | Rủi ro khi không kiểm soát |
| --- | --- | --- |
| method | Phân biệt loại HTTP request | Extension method tạo nhãn lạ |
| route | Xem endpoint chịu tải/lỗi | Raw path chứa ID tạo hàng triệu time series |
| status hoặc status_class | Phân tích 2xx, 4xx, 5xx | Nên dùng numeric/status class có tập nhỏ |
| service | Tách dịch vụ | Tên động theo request khó kiểm soát |
| environment | Dev/staging/prod | Phải do deployment tin cậy cấp |
| outcome/error_type | Phân tích lỗi | Message exception ngẫu nhiên tạo cardinality lớn |

Không dùng user_id, order_id, raw URL, email hoặc trace_id làm nhãn Prometheus có cardinality cao. Những giá trị này nên được lưu trong log/tracing khi cần, với quyền và retention phù hợp, thay vì biến thành time series label.

### Tỷ lệ lỗi theo method

Ví dụ muốn tính tỷ lệ 5xx của POST /orders:

~~~text
5xx error rate =
  số request POST /orders có status 5xx
  / tổng request POST /orders trong cùng cửa sổ thời gian
~~~

Mẫu số phải là **request được quan sát ở cùng tầng**, không lấy log POST ở gateway làm mẫu số và lỗi POST ở controller làm tử số mà không điều chỉnh. Với OPTIONS preflight, HEAD, retries và method override, cần định nghĩa scope để không tạo dashboard sai.

## 14. Latency và điểm quan sát trong kiến trúc nhiều tầng

Trong hệ thống có gateway, load balancer và Java service:

~~~text
Client
  │
  ▼
API Gateway (method trên wire, toàn bộ edge requests)
  │
  ▼
Servlet Filter / Security / CORS (method quan sát tại app entry)
  │
  ▼
Spring HandlerMapping (route template, effective method)
  │
  ▼
Controller → Service → DB
  │
  ▼
Response / exception mapping / async completion
  │
  ▼
Gateway response to client
~~~

**Cùng một request** có thể có nhiều log:

~~~text
observer=gateway method=POST route=/orders status=502 duration_ms=310
observer=app method=POST route=/orders status=201 duration_ms=280
~~~

Hai dòng giả lập này không nhất thiết mâu thuẫn: application có thể đã chọn hoặc gửi response, nhưng gateway gặp lỗi kết nối/timeouts và trả 502 cho client. Không thay status gateway bằng status app rồi tuyên bố request thành công.

### Quy tắc quan sát

1. Đặt tên observer rõ: gateway, servlet, application, client.
2. Phân biệt status_decided, status_observed, status_sent/received khi cần.
3. Sử dụng trace/request ID để liên kết các hop, nhưng không coi trace ID là thông tin xác thực.
4. Dùng cùng chuẩn route template và method bucket tại mỗi nơi để so sánh, đồng thời giữ ngữ nghĩa wire/effective khi có override.
5. Nếu log đã được phát ở gateway, xác định còn cần log riêng ở app với cùng trường hay chỉ cần business exception events.
6. Không suy thứ tự nghiệp vụ chỉ từ thứ tự dòng log giữa các node; clock skew, buffering và async log có thể làm thời điểm hiển thị khác thời điểm xảy ra.

## 15. Logging method với SLF4J/Logback hoặc Log4j 2

Khi code Java web dùng SLF4J:

~~~java
// Snippet cần SLF4J và logging backend tương thích.
accessLog.info(
        "http_request method={} route={} status={} duration_ms={}",
        methodBucket, routeTemplate, status, durationMs);
~~~

Placeholder giúp tránh một số định dạng chuỗi khi level tắt, nhưng **các đối số Java vẫn được tính trước lời gọi**. Nếu route resolution hoặc serialization rất đắt, cân nhắc lấy field khi cần và tránh mọi thao tác I/O chỉ để ghi DEBUG.

Với Logback, có thể dùng ConsoleAppender có PatternLayout hoặc JSON encoder. Trong container nên cân nhắc structured JSON ra stdout; collector/backend có thể index method/route/status thành field mà không cần regex:

~~~json
{"event":"HTTP_REQUEST_COMPLETED","method":"GET","route":"/orders/{id}","status":200,"duration_ms":12}
~~~

Đây là một JSON line minh họa; Logback/Log4j 2 không tự sinh đúng cấu trúc này chỉ vì dùng ConsoleAppender. Cần cấu hình encoder/layout tương ứng, cùng schema và escaping đúng cho mọi value.

### Hạn chế log storm

- Không phát ba bản access log cho cùng request tại cùng một tầng trừ khi thiết kế yêu cầu.
- Ưu tiên một event tổng kết và metrics cho traffic thành công có tần suất cao.
- Với DEBUG body/header, chỉ bật có mục tiêu, có giới hạn thời gian và dữ liệu an toàn.
- Dùng sampling cho những event có thể sample; không bỏ mù security audit hay sự kiện nghiệp vụ cần đầy đủ.
- Async appender giúp giảm chờ I/O trong điều kiện thường nhưng có queue, overflow, drop/block và shutdown flush. Không đồng nghĩa log đã lưu bền vững.
- Giữ method và route là field ổn định; đừng serialize full HttpServletRequest hay headers mỗi request.

## 16. Status và lỗi khi servlet dispatch

Nên đặc biệt chú ý các trường hợp sau:

| Tình huống | Nếu log quá sớm | Cách xử lý |
| --- | --- | --- |
| Request thành công đồng bộ | Có thể có status trước response | Ghi ở cuối tầng quan sát có thể kiểm chứng |
| Controller ném exception | Response còn mặc định 200 | Log UNRESOLVED hoặc đo sau exception resolver/container |
| Spring Security từ chối | Controller không chạy | Đo tại gateway/filter được đặt trước security nếu cần |
| Servlet async / DeferredResult | chain.doFilter trở về trước response | Ghi ASYNC_PENDING; dùng AsyncListener/observation completion để tính final |
| ERROR dispatch | Một request có nhiều lần dispatch | Kiểm soát dispatcher types và dedup |
| Forward/include | Có thể có đường xử lý nhiều handler | Ghi source/dispatch type hoặc chỉ canonical request |
| Client disconnect | App có thể chọn 200 nhưng client không nhận | Ghi aborted/IO error theo tầng quan sát |
| Gateway trả timeout | App status và gateway status khác nhau | Phân biệt observer, không ghi đè |
| Exception sau khi commit | Không đổi status đã gửi được nữa | Ghi trạng thái response committed và outcome phù hợp |

Trong một web filter, response wrapper hoặc status tracker có thể được dùng để đo status cuối và bytes, nhưng phải kiểm thử lifecycle. Nếu ứng dụng hỗ trợ streaming/SSE, request có thể kéo dài rất lâu; một filter chỉ ghi sau chain chưa đủ để mô tả quá trình stream.

## 17. Kiểm thử tính đúng đắn khi logging request method

Một bộ test nên kiểm tra cả method, routing, status và dữ liệu riêng tư.

| Test | Hành vi cần kiểm chứng |
| --- | --- |
| GET /orders | Log method=GET, route đúng, status 200 |
| POST /orders | Log method=POST, status 201, không log body |
| PUT hoặc DELETE trên route chỉ cho GET/POST | 405 với Allow nếu server nhận biết method |
| Method không hỗ trợ | 501 nếu server không nhận biết/triển khai theo thiết kế |
| HEAD | Log HEAD, không nhầm response body size với GET |
| OPTIONS preflight | Nhìn đúng request ở tầng gateway/CORS; không tự tính thành POST |
| GET có query chứa token | Log route template, không ghi token |
| URL có ID động | Route label không có ID để tránh cardinality |
| Method viết thường hoặc method lạ | Không tự uppercase để thay semantics; nhãn OTHER trong metrics |
| Method override có bật | Phân biệt wire_method/effective_method đúng theo filter |
| Authorization từ chối | Có event ở tầng quan sát đã chọn, không lộ credential |
| Controller ném exception | Không gọi status ban đầu là status cuối |
| Async completion | Có một canonical completion event và latency đúng scope |
| ERROR/forward dispatch | Không đếm trùng request không chủ đích |
| Client disconnect | Outcome phù hợp, không tuyên bố client đã nhận thành công |
| Nhiều thread | Không trộn request_id/MDC giữa request |
| Collector parse JSON | method/route/status có kiểu đúng, message không tạo thêm record |

### Unit test

Test hàm methodBucket độc lập với HTTP server: GET → GET, POST → POST, PATCH → PATCH, "get" → OTHER, custom method → OTHER. Đây là test **phân loại nhãn**, không phải test protocol parser hay authorization.

### Integration test

Với ứng dụng dùng Servlet/Spring, gửi HTTP request thật đến test server và kiểm tra output appender/collector. Test cần chạy qua chính filter/security/CORS/exception handling chain sẽ deploy. Mock HttpServletRequest.getMethod() trong unit test không chứng minh edge proxy hoặc method override thực tế diễn ra đúng.

### Đo số request

Nếu gateway, container và ứng dụng cùng ghi log, phân biệt request theo observer để tránh tổng hợp số dòng thành số HTTP request thực. Một request có thể được retry ở client và tạo nhiều request hợp lệ; không tự deduplicate theo method+path vì hai request khác nhau có thể dùng cùng method và path.

## 18. Các lỗi phổ biến và cách sửa

**Lỗi 1 – Log method từ request.getParameter("method").**  
Giá trị đó là query/form parameter, không phải HTTP method. Dùng getMethod của request API hoặc nguồn method do gateway/server xác định.

**Lỗi 2 – Chỉ log trong controller.**  
Các request 401/403/404/405 hoặc CORS preflight có thể bị xử lý trước controller. Nếu cần access coverage, dùng gateway/container/filter/observation thích hợp.

**Lỗi 3 – Dùng raw path làm route trong metrics.**  
/clients/1 và /clients/2 thành nhiều time series. Dùng route template /clients/{id}, có trường hợp UNMAPPED khi chưa route.

**Lỗi 4 – Gọi status=200 trước khi response hoàn tất.**  
Đó có thể chỉ là status mặc định/chủ đích. Ghi rõ status_decided hoặc đo sau khi completion; xử lý exception, client disconnect và async.

**Lỗi 5 – Coi GET luôn an toàn vì RFC gọi safe.**  
Safe là yêu cầu ngữ nghĩa do application phải tuân thủ; route GET đổi trạng thái là lỗi thiết kế. Logging không sửa được lỗi đó.

**Lỗi 6 – Coi POST không thể idempotent, PUT/DELETE chỉ ghi một log.**  
POST có thể được thiết kế idempotent bằng cơ chế riêng; PUT/DELETE có thể được gửi nhiều lần và sinh nhiều access event.

**Lỗi 7 – Gộp OPTIONS vào POST.**  
Preflight là request OPTIONS độc lập, có thể do edge xử lý. Không mặc định sau preflight luôn có actual request.

**Lỗi 8 – Đọc X-HTTP-Method-Override mà không xác nhận đã áp dụng.**  
Một header tùy ý không phải effective method nếu không có filter/route policy tương ứng. Phân biệt giá trị raw và method thực được server dùng.

**Lỗi 9 – Không giới hạn method lạ ở nhãn metrics.**  
Extension methods có thể tạo cardinality cao. Bucket OTHER và theo dõi request bất thường qua kênh security có kiểm soát.

**Lỗi 10 – Ghi toàn bộ HttpServletRequest/headers/payload.**  
Có thể lộ Authorization, Cookie, URL query, dữ liệu cá nhân và tạo log injection; dùng field allowlist.

**Lỗi 11 – Ghi đồng thời ở nhiều tầng mà không gắn observer.**  
Làm tăng chi phí và gây dashboard sai số. Xác định canonical access log và purpose của các log bổ sung.

**Lỗi 12 – Dùng wall-clock để đo request duration.**  
System.currentTimeMillis có thể nhảy khi đồng hồ điều chỉnh. Dùng System.nanoTime để đo elapsed trong JVM.

## 19. Checklist áp dụng trong dự án Java Web

1. Xác định tầng cần logging: gateway, web server, Servlet filter, Spring interceptor hay business handler.
2. Xác định field method là wire hay effective method, nhất là khi có proxy/method override.
3. Dùng HTTP request API đúng: HttpServletRequest.getMethod, HttpExchange.getRequestMethod hoặc API của reactive framework.
4. Định nghĩa tập method buckets hữu hạn; giữ method gốc trong logic routing và authorization.
5. Ghi route template thay vì raw URL có ID/query.
6. Ghi status ở mốc chính xác, dùng tên field có nghĩa (decided, observed, completed).
7. Đo duration bằng đồng hồ đơn điệu và đúng scope, không so sánh hai timestamp server khác nhau để suy ra chính xác latency.
8. Hỗ trợ CORS OPTIONS, HEAD, async/error dispatch và client disconnect khi cần đầy đủ access coverage.
9. Giới hạn dữ liệu: không ghi token, cookie, raw body, query nhạy cảm; escape/encode các field untrusted.
10. Kết hợp request_id/trace_id được kiểm soát, clear MDC khi thread pool dùng lại.
11. Kiểm tra concurrency, lỗi handler, forward/dispatch, retries và multiple observer để tránh count sai.
12. Test trên runtime thực tế; đối chiếu access log từ source tới collector và dashboard.
13. Đặt retention và phân quyền cho access logs vì metadata request vẫn có thể góp phần nhận diện cá nhân.
14. Nếu bật DEBUG chi tiết khi điều tra, giới hạn thời gian, log rate và phạm vi logger rồi quay lại cấu hình bình thường.

## 20. Bài tập thực hành

### Bài 1 – Thêm method không được cho phép

Chạy RequestMethodLoggingDemo.java rồi bổ sung một HTTP request PUT tới /orders trong môi trường thử nghiệm. Dự đoán server trả 405 và header Allow: GET, POST. Xác minh log có method=PUT và status_decided=405; không có thông điệp xác nhận order được tạo.

### Bài 2 – Phân biệt method lạ

Thử unit test hàm bucket với GET, get, PATCH và một token mở rộng như PROPFIND. Giải thích vì sao metric label OTHER phù hợp nhưng **không thể dùng OTHER làm kết quả authorization** cho mọi request.

### Bài 3 – Servlet Filter và exception

Trong ứng dụng Jakarta Servlet test, dùng filter mục 8. Tạo một route ném exception rồi kiểm tra log status_observed=UNRESOLVED của lần dispatch ban đầu. Thiết kế thêm cách quan sát status cuối sau error handling thay vì tự báo 500 trong finally khi chưa có kết quả.

### Bài 4 – CORS và HEAD

Tại web app test, gửi OPTIONS preflight, HEAD và GET tới một route tương ứng. Xác định tầng nào nhìn thấy từng request, cách tính request count và vì sao HEAD không nên có response content như GET.

### Bài 5 – Privacy và metrics

Một đội dùng metrics label raw_path=/orders/123?email=... và lưu header Authorization để chẩn đoán. Thiết kế schema thay thế gồm method, route template, status_class, duration_ms, request_id và error_category. Giải thích cách giảm cardinality và tránh lưu token.

### Bài 6 – End-to-end với reverse proxy

Giả sử gateway log wire_method=POST còn ứng dụng có method-override filter nhận effective_method=DELETE. Tạo bản ghi log mô phỏng có observer, route, status và trace ID. Giải thích khi nào hai method khác nhau là hợp lệ, cách kiểm chứng override thật sự được áp dụng, và vì sao không thể tin raw header từ client làm method cuối.

## 21. Ghi nhớ

**Request method là field trung tâm của access logging**, nhưng chỉ có ý nghĩa khi đi cùng route, status, duration và nguồn quan sát. GET/HEAD/OPTIONS/TRACE được định nghĩa safe; các method safe cùng PUT và DELETE có ngữ nghĩa idempotent theo RFC. POST/PATCH không mặc định idempotent. Safe/idempotent **không có nghĩa** không sinh log, không gặp lỗi hay chỉ có một bản ghi.

Trong Java Web, lấy method từ API request đã parse thay vì request parameter; phân biệt original/wire và effective method khi có override. Ghi method ở tầng phù hợp, không gọi status chưa hoàn tất là status cuối, và xử lý đặc biệt cho Servlet async, CORS preflight, HEAD, 405/501 và gateway. Đối với metrics, dùng method bucket và route template để giảm cardinality. Đối với quyền riêng tư, không ghi raw URL query, headers hoặc body chứa dữ liệu nhạy cảm. Hãy test cả log từ ứng dụng đến collector, không chỉ một logger call.

### Tài liệu tham khảo

- RFC 9110 – HTTP Semantics, request methods, safe/idempotent, 405/501: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 5789 – PATCH Method for HTTP: https://www.rfc-editor.org/rfc/rfc5789
- Oracle Java 17 – HttpExchange.getRequestMethod: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- Oracle Java 17 – HttpServer: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Oracle Java 17 – HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Jakarta Servlet – HttpServletRequest: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/HttpServletRequest.html
- Spring Framework – Request Mapping: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework – Handler Mapping: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
