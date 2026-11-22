# Response status trong logging ứng dụng web Java

## 1. Mục tiêu và bối cảnh

**Response status** trong ứng dụng web là **mã trạng thái HTTP của phản hồi mà server gửi hoặc dự định gửi cho client**, ví dụ **200 OK**, **201 Created**, **404 Not Found**, **429 Too Many Requests** hoặc **503 Service Unavailable**. Khi ghi log một HTTP request, response status giúp trả lời câu hỏi quan trọng: **request đó kết thúc bằng kết quả HTTP nào?**

Đây là kiến thức thuộc **logging trong ứng dụng web**, không chỉ là danh sách status code. Cần hiểu **lúc nào đọc status**, **nó khác exception và business result ra sao**, **request nào cần được log**, **ghi những field nào**, **làm sao tránh lộ dữ liệu**, và **làm sao đối chiếu log với metric/trace hay status mà client thực sự thấy**.

Sau bài học, bạn sẽ:

1. Hiểu các nhóm 1xx–5xx và ý nghĩa quan sát của response status.
2. Xác định **HTTP status cuối cùng có ý nghĩa tại tầng bạn đo**, không đoán theo exception hoặc return value của controller.
3. Biết thiết kế access log và structured event gồm method, route, status, duration, correlation ID.
4. Nhận diện status bị thay đổi bởi security filter, exception handler, reverse proxy, retry hoặc async dispatch.
5. Chạy ví dụ **Java 17 độc lập** dùng HttpServer/HttpClient, lấy status sau handler và đối chiếu với phản hồi client.
6. Biết tích hợp ở mức thiết kế với Servlet/Spring MVC, Spring Boot, WebFlux, gateway và OpenTelemetry.
7. Kiểm thử status logging cho cả thành công, lỗi client, lỗi server và request chưa có HTTP response.

## 2. Response status là gì — và không phải là gì?

HTTP response có dòng trạng thái hoặc trường pseudo-header thể hiện **mã HTTP ba chữ số**. Trong HTTP/1.1 thường thấy một status line kiểu:

~~~text
HTTP/1.1 404 Not Found
Content-Type: application/json
~~~

Response status là **404**, không phải đoạn văn bản "Not Found". HTTP/2 và HTTP/3 biểu diễn trạng thái theo giao thức tương ứng nhưng ý nghĩa mã vẫn là HTTP status.

Một event log thiết kế theo hướng dễ phân tích có thể là:

~~~text
event=http.request.completed method=GET route=/orders/{id} status=404 duration_ms=18
~~~

Đó là **một record minh họa**, không phải output mặc định bắt buộc của Java. Các field có thể mang tên khác tùy backend, tracing và logging schema. Nếu dùng quy ước OpenTelemetry HTTP, thuộc tính tiêu chuẩn là **http.response.status_code**.

Không nhầm response status với:

- **Trạng thái nghiệp vụ:** "order=PENDING", "payment=DECLINED" là kết quả của nghiệp vụ; có thể đi cùng HTTP 200, 202, 409 hoặc mã khác tùy API contract.
- **Mức log (severity):** INFO/WARN/ERROR là lựa chọn logging, không phải HTTP status. Một request 500 có thể được logger ghi INFO ở access log, còn exception tương ứng được log ERROR ở nơi khác.
- **Loại exception Java:** IOException, IllegalArgumentException hay một exception tự định nghĩa không tự động tương đương mã HTTP cố định.
- **Kết quả mạng của client:** timeout, DNS failure, TLS handshake error hoặc connection reset có thể **không có HTTP status nào**.
- **Mã gRPC:** gRPC status khác HTTP status ở lớp vận chuyển, dù một call có thể đi qua HTTP/2.
- **Mã từ upstream:** API gateway có thể nhận 500 từ service nội bộ nhưng gửi 502 cho client, hoặc trả cached 200 mà không gọi service.
- **Kết quả tìm thấy trong dashboard:** người tìm log có thể chỉ thấy status của một hop, không phải status cuối của request ngoài Internet.

Phải gắn rõ **vị trí quan sát**: application server, reverse proxy/gateway, HTTP client của service khác hay browser. Cùng một lượt giao tiếp có thể có nhiều status ở các hop.

## 3. Phân loại các nhóm mã HTTP

| Nhóm | Ý nghĩa tổng quát | Ví dụ | Cách hiểu khi logging |
| --- | --- | --- | --- |
| **1xx** | Thông tin trung gian | 100 Continue, 101 Switching Protocols | Không phải lúc nào cũng là status cuối của một HTTP exchange theo kiểu thông thường. |
| **2xx** | Request được xử lý thành công theo semantics HTTP | 200 OK, 201 Created, 202 Accepted, 204 No Content | Không suy ra mọi bước nghiệp vụ downstream đã xong; 202 là đã chấp nhận xử lý. |
| **3xx** | Chuyển hướng hoặc dùng tài nguyên/cache theo ngữ nghĩa tương ứng | 301, 302, 304, 307, 308 | Có thể là kết quả hợp lệ; client thường theo redirect rồi nhận status khác. |
| **4xx** | Vấn đề liên quan đến request/client theo semantics HTTP | 400, 401, 403, 404, 409, 422, 429 | Không tự động là bug server. Cần bối cảnh endpoint, auth và hành vi người dùng. |
| **5xx** | Server hoặc trung gian không đáp ứng request như mong đợi | 500, 502, 503, 504 | Thường là tín hiệu đáng chú ý về lỗi hệ thống, phụ thuộc tầng phát sinh. |

### Những mã thường gặp

| Mã | Tên thường gọi | Ví dụ trong ứng dụng web |
| --- | --- | --- |
| **200 OK** | Thành công | Lấy dữ liệu, cập nhật có kết quả hợp lệ. |
| **201 Created** | Đã tạo tài nguyên | Tạo đơn hàng mới. |
| **202 Accepted** | Đã chấp nhận | Nhận job vào hàng đợi, xử lý hoàn tất sau. |
| **204 No Content** | Thành công không có body | Xóa/cập nhật, không cần nội dung trả về. |
| **301 / 308** | Redirect thường mang tính lâu dài | Đổi URL chính thức; 308 giữ phương thức trong ngữ nghĩa redirect. |
| **302 / 307** | Redirect thường mang tính tạm thời | Chuyển sang nơi khác; 307 giữ nguyên method theo chuẩn. |
| **304 Not Modified** | Cache validation | Trả lời conditional request. |
| **400 Bad Request** | Request không hợp lệ | Sai cú pháp/định dạng dữ liệu. |
| **401 Unauthorized** | Thiếu hoặc không hợp lệ thông tin xác thực | Chưa đăng nhập/token không hợp lệ; tên mã có tính lịch sử. |
| **403 Forbidden** | Không được phép thực hiện | Đã biết danh tính nhưng bị từ chối theo policy, hoặc lý do khác theo contract. |
| **404 Not Found** | Không tìm thấy | ID tài nguyên không tồn tại hoặc API cố ý không tiết lộ sự tồn tại. |
| **409 Conflict** | Xung đột trạng thái | Version conflict hoặc trạng thái không phù hợp. |
| **422 Unprocessable Content** | Nội dung hợp lệ về cú pháp nhưng không xử lý được theo semantics | Vi phạm validation nghiệp vụ phù hợp contract. |
| **429 Too Many Requests** | Vượt ngưỡng yêu cầu | Rate limit. |
| **500 Internal Server Error** | Lỗi server chung | Exception chưa được xử lý hoặc không thể hoàn tất request. |
| **502 Bad Gateway** | Gateway nhận phản hồi upstream không hợp lệ | Lỗi từ upstream khi đi qua gateway. |
| **503 Service Unavailable** | Tạm thời không phục vụ | Bảo trì/quá tải/upstream không sẵn sàng tùy tầng. |
| **504 Gateway Timeout** | Gateway chờ upstream quá lâu | Timeout giữa proxy và service phụ thuộc. |

Bảng chỉ tóm tắt; mã cụ thể phải theo **hợp đồng API và HTTP semantics**. Một API có thể dùng 404 cho tài nguyên không tìm thấy bình thường; 409 cho optimistic locking; 429 để bảo vệ dịch vụ. **Không nên tự động log mọi 4xx ở ERROR** vì sẽ tạo nhiễu và có thể bị attacker cố tình gây log flooding.

## 4. Vì sao status là một field quan trọng trong access log?

Mỗi request thường tạo được **một logical access event** ở thời điểm đã xác định:

~~~text
HTTP request → routing/auth/controller → HTTP response
                              │
                              ▼
                 status + duration + route
                              │
                              ▼
                      structured log
~~~

Status kết hợp với những field khác giúp:

- **Chẩn đoán:** xác định route nào thường phát sinh 500 hoặc 404.
- **Đo SLO:** theo dõi tỷ lệ request thành công/lỗi theo định nghĩa mục tiêu vận hành.
- **Phân tích đổi phiên bản:** so sánh 5xx rate trước/sau deployment.
- **Hỗ trợ người dùng:** tìm một request theo requestId/traceId và xem status cùng latency.
- **Phát hiện lạm dụng:** 401/403/429 tăng bất thường có thể là một tín hiệu an ninh, nhưng không đủ một mình để kết luận tấn công.
- **Cô lập tầng lỗi:** phân biệt application 500 với gateway 502/504.
- **Đánh giá rate limit/cache:** 304, 429 và 503 có thể giải thích trải nghiệm client.

Không nên biến access log thành **nguồn sự thật duy nhất** về mọi request. Khi logging backend rơi event, queue đầy, collector outage hoặc retention hết hạn, log có thể thiếu. Kết hợp **metrics, traces, health và transaction data** theo yêu cầu quan sát.

### 4.1. Các field nên có

Một schema tham khảo:

| Field | Mục đích | Ghi chú bảo mật |
| --- | --- | --- |
| **timestamp** | Thời điểm event được phát hành/hoàn tất | Dùng timestamp có timezone hoặc UTC rõ ràng. |
| **service / environment** | Định vị process và môi trường | Không nhầm staging với production. |
| **http.request.method** | GET, POST, DELETE... | Chuẩn hóa để tránh giá trị kỳ lạ từ request không đáng tin. |
| **http.route** | Route template, ví dụ /orders/{id} | Thường ít cardinality và tránh ghi ID thật. |
| **http.response.status_code** | Mã HTTP thực đã được xác định | Số nguyên, không phải tự tạo "200/OK" làm string. |
| **duration_ms** | Thời gian xử lý đo bằng monotonic clock | Không tính bằng cách trừ 2 chuỗi timestamp text. |
| **request_id / trace_id** | Tương quan event trong cùng request | Validate metadata lấy từ client; không ghi token. |
| **error.type** | Loại lỗi khi có lỗi | Không đổ toàn bộ exception message nhạy cảm vào field. |
| **response_bytes** | Kích thước phản hồi theo định nghĩa thống nhất | Đừng coi body bytes là toàn bộ wire bytes nếu có framing/compression. |
| **client category / tenant** | Phân tích theo phạm vi được phép | Chỉ ghi field thật sự cần, có phân quyền đọc. |

Các field trên là **đề xuất thiết kế**, không phải mặc định mọi framework tạo. Nên dùng encoder có cấu trúc như JSON và để logger backend serialize, thay vì tự ghép dấu phân cách, tránh log forging.

Ví dụ JSON:

~~~json
{
  "event": "http.server.request.completed",
  "service": "order-service",
  "environment": "prod",
  "http.request.method": "GET",
  "http.route": "/orders/{id}",
  "http.response.status_code": 404,
  "duration_ms": 18,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
~~~

Đây là **dữ liệu minh họa**, không phải output mặc định của một backend. Route template không chứa giá trị id của người dùng; trace ID ví dụ không thuộc một request thật.

## 5. Status phải được lấy khi nào?

Một lỗi rất phổ biến là log status **quá sớm**:

~~~text
1. Request đến              → status chưa xác định
2. Security filter chạy     → có thể reject 401/403
3. Controller xử lý         → có thể trả 200/201/204
4. Exception resolver chạy  → có thể chuyển thành 400/404/500
5. Response headers gửi ra  → status bắt đầu được gửi cho client
6. Body được gửi / kết thúc → có thể có lỗi I/O sau khi headers đã gửi
7. Access log hoàn tất      → ghi giá trị tại mốc đo được thiết kế
~~~

Ở đầu request, không nên log ngay **status=200** chỉ vì một response object có default 200. Một exception, filter, redirect, authentication failure hoặc error page có thể thay đổi kết quả sau đó.

Đối với request thông thường, nên ghi access event **ở thời điểm hoàn tất xử lý hoặc đủ gần thời điểm response được commit**, lấy status từ tầng đang chịu trách nhiệm tạo phản hồi. Phải phân biệt:

- **Trước khi headers được gửi:** status còn có thể thay đổi.
- **Sau khi response được commit:** thông thường không thể đổi HTTP status đã phát cho client.
- **Sau khi body bắt đầu gửi:** lỗi I/O vẫn có thể xảy ra; status 200 có thể đã gửi dù body bị cắt. Cần thêm field lỗi vận chuyển nếu có.
- **Không có HTTP response:** không tự bịa status 500 khi connection lỗi trước khi trả được headers.

### 5.1. Không có status không có nghĩa 500

Ở Java 17 HttpServer, **HttpExchange.getResponseCode()** trả **-1** nếu chưa có mã phản hồi. Điều đó **không phải HTTP status -1**, mà là dấu hiệu API **chưa có status**.

Trong các SDK tracing, thuộc tính **http.response.status_code** chỉ được ghi **khi status thực sự được gửi/nhận**. Nếu network/TLS/DNS timeout khiến không tồn tại HTTP response, phải dùng loại lỗi/exception tương ứng; không ép status=0 hay status=500 rồi làm sai dữ liệu.

Một schema có thể tách:

~~~json
{
  "event": "http.server.request.failed",
  "http.response.status_code": null,
  "error.type": "connection_aborted",
  "outcome": "incomplete"
}
~~~

Đây là minh họa schema nội bộ cho tình huống chưa có mã, **không phải yêu cầu OpenTelemetry phải ghi null**. Khi dùng semantic conventions chuẩn, **bỏ hẳn attribute** nếu không có status là cách phù hợp hơn việc xuất null không được định nghĩa.

### 5.2. Không suy ra status chỉ từ exception

Một exception nghiệp vụ có thể được **@ExceptionHandler** chuyển thành ResponseEntity 404, 409 hoặc 422; Servlet container có thể tạo error page 500; Spring Security có thể chặn 401/403 trước controller. Cùng tên exception thậm chí có thể được xử lý khác ở các API khác nhau.

Ngược lại, controller có thể trả **ResponseEntity.status(503)** mà **không ném exception**. Vì vậy cách log kiểu:

~~~java
// Minh họa ý tưởng sai: chỉ dựa vào exception trong code nghiệp vụ.
int status = exception == null ? 200 : 500;
~~~

sẽ dễ sai. Nên lấy mã HTTP từ **response thực sự** ở đúng tầng và đúng thời điểm; exception chỉ là **một field bổ sung** khi có.

## 6. Ví dụ Java 17 độc lập: ghi actual response status

JDK 17 có module **jdk.httpserver**, cung cấp **HttpServer**, **HttpExchange**, **HttpContext** và **Filter**. Ta tạo HTTP server trên loopback với port do hệ điều hành cấp, gửi ba request bằng **HttpClient** cũng có sẵn trong JDK và dùng **Filter.afterHandler** để ghi status sau handler.

Ví dụ không cần Maven, Gradle, Spring Boot hay dependency bên ngoài.

### 6.1. Mã nguồn hoàn chỉnh

Lưu tệp **ResponseStatusDemo.java**:

~~~java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class ResponseStatusDemo {

    private static int statusFor(String path) {
        return switch (path) {
            case "/ok" -> 200;
            case "/missing" -> 404;
            case "/maintenance" -> 503;
            default -> 404;
        };
    }

    private static String routeFor(String path) {
        return switch (path) {
            case "/ok" -> "/ok";
            case "/missing" -> "/missing";
            case "/maintenance" -> "/maintenance";
            default -> "/other";
        };
    }

    private static void respond(HttpExchange exchange)
            throws java.io.IOException {
        try {
            String path = exchange.getRequestURI().getPath();
            int status = statusFor(path);
            byte[] body = ("status=" + status)
                    .getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, body.length);

            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        server.setExecutor(executor);

        List<String> accessLogs = Collections.synchronizedList(
                new ArrayList<>());
        CountDownLatch logged = new CountDownLatch(3);

        HttpContext context = server.createContext(
                "/", ResponseStatusDemo::respond);

        context.getFilters().add(Filter.afterHandler(
                "Record response status", exchange -> {
                    String route = routeFor(
                            exchange.getRequestURI().getPath());
                    int status = exchange.getResponseCode();
                    accessLogs.add(
                            "ACCESS method=" + exchange.getRequestMethod()
                            + " route=" + route
                            + " status=" + status);
                    logged.countDown();
                }));

        List<String> clientResults = new ArrayList<>();
        server.start();

        try {
            HttpClient client = HttpClient.newHttpClient();
            int port = server.getAddress().getPort();

            for (String path : List.of(
                    "/ok", "/missing", "/maintenance")) {
                URI uri = URI.create(
                        "http://127.0.0.1:" + port + path);
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .GET()
                        .build();

                HttpResponse<String> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8));

                clientResults.add(
                        "CLIENT path=" + path
                        + " status=" + response.statusCode());
            }

            if (!logged.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Access logging did not complete");
            }
        } finally {
            server.stop(0);
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }

        for (String line : accessLogs) {
            System.out.println(line);
        }
        for (String line : clientResults) {
            System.out.println(line);
        }
    }
}
~~~

### 6.2. Biên dịch và chạy

Với một bản JDK 17 có module **jdk.httpserver**:

~~~bash
javac --add-modules jdk.httpserver ResponseStatusDemo.java
java --add-modules jdk.httpserver ResponseStatusDemo
~~~

**stdout trong lần chạy thành công**, với network loopback hoạt động bình thường:

~~~text
ACCESS method=GET route=/ok status=200
ACCESS method=GET route=/missing status=404
ACCESS method=GET route=/maintenance status=503
CLIENT path=/ok status=200
CLIENT path=/missing status=404
CLIENT path=/maintenance status=503
~~~

Các request được gửi **tuần tự** và server dùng executor một thread, nên thứ tự ghi access log của ba request là xác định. Log được giữ trong list và chỉ in sau khi **CountDownLatch** xác nhận filter xử lý đủ ba exchange. Output không in port ngẫu nhiên, timestamp hoặc thời lượng nên ổn định.

### 6.3. Diễn giải

- **/ok → 200**: request đã được handler xử lý và trả OK.
- **/missing → 404**: server chủ động trả Not Found, không có exception nào được ném trong ví dụ.
- **/maintenance → 503**: handler chủ động phản hồi Service Unavailable, cũng không cần exception.
- **Filter.afterHandler** chạy sau xử lý của handler/filter tiếp theo, lấy **HttpExchange.getResponseCode()** và ghi vào accessLogs.
- **HttpClient.statusCode()** là mã mà client local thật sự nhận được ở endpoint trực tiếp này.
- **routeFor** chuyển path về một tập route đã biết, tránh lấy nguyên URL tùy ý làm nhãn log. Ở ứng dụng thực nên lấy matched route template từ routing framework.
- **CountDownLatch** và single-thread executor chỉ dùng để có output tái lập trong bài học; không phải cấu hình throughput production.
- **server.stop(0)** dừng server sau khi các request thử đã hoàn tất. Ví dụ không ghi file log, không gửi collector và không mô phỏng proxy.
- Hàm **respond** đóng exchange sau khi gửi body. Nếu một exception xảy ra trước **sendResponseHeaders**, getResponseCode có thể vẫn bằng -1. Ví dụ đơn giản không xử lý toàn bộ lỗi mạng của production.

**Điểm quan trọng:** ba dòng ACCESS ghi lại **status do server phát** sau handler; ba dòng CLIENT cho thấy **status nhận ở client**, để người học đối chiếu. Hai tập giá trị khớp vì không có reverse proxy và không có retry/redirect.

### 6.4. Tại sao không log ngay ở đầu handler?

Nếu ghi:

~~~java
// Minh họa chưa đúng: đặt trước khi gửi response.
int code = exchange.getResponseCode();
System.out.println("status=" + code);
~~~

thì lúc này có thể nhận **-1**, chứ không phải 200. Status chỉ được biết sau khi server quyết định mã và bắt đầu response bằng **sendResponseHeaders**. Trong Servlet/Spring MVC cũng có vấn đề timing tương tự, dù API khác.

### 6.5. Bài tập mở rộng từ ví dụ

Đổi route "/maintenance" thành 429 để mô phỏng rate limit; thêm route "/created" trả 201; thêm một event khi getResponseCode chưa xác định; quan sát nếu filter đo status sau handler nhưng handler có lỗi trước khi gửi headers. **Không gán -1 thành 500** nếu server chưa phát HTTP response.

Chương trình này cũng có giới hạn thiết kế: việc lưu access event trong list không được giới hạn dung lượng nếu phục vụ traffic liên tục, và demo không có structured JSON encoder, backpressure hay fail-safe audit. Production nên dùng framework observability hoặc logging backend được kiểm soát, tránh đưa mỗi event vào một list trong RAM.

## 7. Servlet API và Spring MVC: lấy status ở tầng nào?

Trong Servlet-based web application, **HttpServletResponse** có phương thức **getStatus()**, **setStatus(...)**, **sendError(...)** và **sendRedirect(...)**. Tầng filter có thể quan sát response đi qua filter chain; Spring MVC có controller, argument conversion, validation và exception resolvers tham gia quyết định status.

### 7.1. Ba cách endpoint tạo status

**Trường hợp thành công với ResponseEntity:**

~~~java
// Minh họa trong Spring MVC; cần dependency và enclosing class.
@GetMapping("/orders/{id}")
public ResponseEntity<OrderDto> getOrder(@PathVariable String id) {
    OrderDto order = service.getOrder(id);
    return ResponseEntity.ok(order);
}
~~~

**Trả 201 sau tạo tài nguyên:**

~~~java
// Minh họa trong Spring MVC, không phải class độc lập.
@PostMapping("/orders")
public ResponseEntity<OrderDto> create(@RequestBody OrderInput input) {
    OrderDto created = service.create(input);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

**Exception được chuyển thành HTTP response:**

~~~java
// Minh họa trong một @RestControllerAdvice phù hợp.
@ExceptionHandler(OrderNotFoundException.class)
public ResponseEntity<Void> notFound(
        OrderNotFoundException exception) {
    return ResponseEntity.notFound().build();
}
~~~

Các đoạn trên **không thể chạy độc lập**: cần Spring Web, DTO/service/exception và import tương ứng. Chúng minh họa rằng một exception có thể được đổi thành **404**, không nhất thiết thành **500**. Ngoài ra, validation, security, CORS và gateway có thể quyết định status **trước khi controller chạy**.

### 7.2. Filter, Interceptor, Controller Advice: vai trò khác nhau

| Vị trí | Ưu điểm | Hạn chế cần nhớ |
| --- | --- | --- |
| **Servlet Filter** | Bao quanh phần lớn request/response trong filter chain; có thể ghi duration và status. | Phải xử lý dispatcher types, async và error dispatch; chưa chắc thấy status sau khi container tự tạo error page. |
| **HandlerInterceptor** | Có ngữ cảnh handler/route Spring MVC; tiện gắn route template. | Không chắc bao phủ tất cả request bị chặn trước DispatcherServlet hay lỗi ở filter/gateway. |
| **Controller/@ExceptionHandler** | Biết ý nghĩa nghiệp vụ, status chủ động tạo. | Dễ bỏ sót lỗi trước controller; ghi nhiều nơi dẫn đến duplicate. |
| **Framework observability** | Có thể chuẩn hóa metrics/traces cho HTTP lifecycle. | Cần kiểm tra framework/version/config và policy field đang thu thập. |
| **Proxy/Gateway access log** | Phản ánh status mà gateway gửi ở biên ngoài. | Không tự biết exception và business context sâu trong Java service. |

**Không có một hook Java duy nhất quan sát chính xác mọi đường lỗi ở mọi stack.** Chọn tầng thực thi theo mục tiêu: muốn biết controller quyết định gì, gateway thực sự gửi gì hay end-to-end client thấy gì.

### 7.3. Chú ý với OncePerRequestFilter

Trong Spring MVC, **OncePerRequestFilter** giới hạn việc thực thi theo **một request dispatch**, không bảo đảm "một logical request chỉ có một lần" qua mọi loại async/error dispatch. Tài liệu Spring nêu các trường hợp **REQUEST, ASYNC, ERROR** có thể tham gia vòng đời và có phương thức để chọn lọc.

Nếu viết:

~~~java
// Đoạn minh họa ý tưởng cho request đồng bộ thông thường.
long start = System.nanoTime();
try {
    filterChain.doFilter(request, response);
} finally {
    log.info("method={} status={} duration_ms={}",
            request.getMethod(),
            response.getStatus(),
            (System.nanoTime() - start) / 1_000_000);
}
~~~

đừng coi đây là triển khai end-to-end hoàn chỉnh. Khi request chuyển sang xử lý async, **finally của dispatch đầu** có thể chạy trước khi response cuối cùng sẵn sàng. Khi exception chưa được framework/container chuyển thành error response, **getStatus() ở thời điểm finally** có thể chưa phản ánh status client nhận. Tương tự, **ERROR dispatch** có thể chạy sau đó hoặc nằm trong vòng xử lý khác; nếu log ở cả hai dispatch mà không có quy tắc, bạn có thể tạo duplicate.

Giải pháp production thường là dựa vào instrumentation của framework phù hợp, hoặc thiết kế filter/listener hỗ trợ **AsyncListener / complete/error/timeout**, error dispatch và một **once-only logical completion guard** có kiểm thử. Đừng ghép một đoạn code finally đơn giản rồi khẳng định "luôn log đúng status cuối".

### 7.4. RequestLoggingFilter và response status

Một filter chỉ log request trước/sau có thể không có field status chuẩn. Ví dụ trong Spring, **AbstractRequestLoggingFilter**/CommonsRequestLoggingFilter nhằm log thông tin request và có quy tắc riêng cho async dispatch; đừng giả định nó thay thế đầy đủ access logging có status, latency, route template và exception classification. Kiểm tra output thực sự.

## 8. Spring Boot và observability

Spring Boot có tích hợp observability dựa trên Micrometer Observation tùy dependency/cấu hình/phiên bản, còn Spring Framework hỗ trợ observation cho HTTP server và client. Ở ứng dụng servlet, instrumentation có thể tạo observation cho request/response; các hệ xuất metrics/traces có thể lấy status từ đó.

Những điểm cần kiểm tra:

- Ứng dụng đã thêm **đúng dependency** và bật cơ chế observation/metrics/tracing chưa?
- Có dùng **Servlet stack (Spring MVC)** hay **reactive stack (WebFlux)**?
- Cấu hình observability đã thu thập **status code** chưa, route nào được gắn nhãn?
- Có custom filter/controller logging đang ghi trùng với access log từ Tomcat/Jetty/Undertow hoặc gateway không?
- **Một observation/timer** có tính toàn bộ thời gian gửi response hay chỉ thời gian handler? Tùy framework và instrumentation.
- Có bật **Spring Boot Actuator** và exporter phù hợp chưa nếu mục tiêu là dashboard SLO, thay vì chỉ xuất log text?

Tên metric hoặc tag có thể khác theo hệ xuất và version. OpenTelemetry HTTP semantic conventions dùng **http.response.status_code** cho numeric status **khi có response đã gửi/nhận**; **http.route** nên là route template low-cardinality. Trong Spring Framework, một observation có thể được đặt tên **http.server.requests**; exporter có thể chuyển nó thành tên metric chuẩn khác.

**Không nên bỏ access log chỉ vì có metrics**, vì metric thường đã được aggregate. Ngược lại, đừng dùng mỗi log để tính SLO nếu log có thể drop. Kết hợp hợp lý theo chi phí và mục tiêu.

## 9. Status và mức log INFO/WARN/ERROR

Một chiến lược thực tế là ghi **mọi HTTP request đã được quan sát** thành **một event truy cập ở mức phù hợp**, rồi có log lỗi riêng khi cần stack trace/cause.

Có thể dùng chính sách mẫu sau:

| HTTP status | Access log gợi ý | Lý do |
| --- | --- | --- |
| **2xx** | INFO hoặc event access chuyên biệt | Luồng bình thường. |
| **3xx** | INFO/DEBUG tùy volume | Redirect/cache thường hợp lệ. |
| **400/404 dự kiến** | INFO hoặc WARN theo endpoint | Người dùng có thể gửi request sai; không nhất thiết là lỗi hệ thống. |
| **401/403** | INFO/WARN và security signal theo policy | Có thể là hành vi bình thường hoặc lạm dụng; tránh log thông tin xác thực. |
| **409/422** | INFO/WARN theo contract | Business/validation outcome có thể dự kiến. |
| **429** | WARN hoặc aggregate/rate-limit metric | Có thể xuất hiện ở lưu lượng lớn; tránh log flood từng request nếu không cần. |
| **5xx** | WARN/ERROR tùy trách nhiệm; error event có cause | Thường cần điều tra; có thể xảy ra ở proxy, app hoặc dependency. |

Đây là **chính sách minh họa**, không phải quy tắc bắt buộc. Một số hệ dùng access log ở một channel riêng và không đổi severity theo status; thay vào đó lưu field số và để alert dựa trên metrics. Cách đó hoàn toàn hợp lý nếu đảm bảo dễ tìm và không mất thông tin.

Không tự động log stack trace ở ERROR cho **mọi 404**. Ngược lại, một sự kiện 200 với business invariant bị vi phạm vẫn có thể đáng ghi lỗi nghiệp vụ. **HTTP status, severity và outcome là ba chiều khác nhau.**

### 9.1. Tránh log trùng

Nếu có:

- Access logging của reverse proxy.
- Tomcat access log.
- Một servlet filter tự viết.
- Spring interceptor log cuối request.
- Controller log "request completed".

Cùng một request có thể tạo **nhiều record** hợp lệ hoặc trùng nội dung. Đặt rõ mục đích của mỗi nguồn và tên event/source khác nhau, ví dụ gateway.access và app.http.server.completed; mỗi **logical request ở mỗi tầng** nên có quy tắc ghi một lần theo thiết kế, tránh nhân bản ngoài ý muốn.

## 10. Những trường hợp status gây hiểu nhầm

### 10.1. Chuyển hướng: 302 rồi 200

Browser gọi **GET /old**, server gửi **302 Location: /new**, browser tiếp tục GET /new và nhận **200**. Nếu client tự động follow redirect, kết quả cuối dễ hiện 200 trong khi server access log có **một request 302 và một request 200**.

Không kết luận một trong hai log sai. Chúng là **hai HTTP exchanges**. Nên dùng trace hoặc correlation ID phù hợp để đối chiếu; không gộp chúng thành một status duy nhất.

### 10.2. Gateway status khác status ứng dụng

~~~text
Client → Gateway → Order Service
            │            │
            │         HTTP 500
            │◄───────────┘
            │
         HTTP 502  → Client
~~~

Đây là ví dụ giả định: gateway **có thể** chuyển lỗi upstream thành một mã khác theo cấu hình, nhưng không phải mọi gateway đều chuyển 500 thành 502. Gateway có thể trả 503/504 khi chưa kết nối được upstream, trong khi app **không phát ra status nào** cho request đó.

Do vậy nên ghi **service, hop/role, route và trace ID**, để phân biệt status ghi tại gateway với status ghi tại application.

### 10.3. Lỗi sau khi đã gửi headers

Application gửi status **200** và một phần body; sau đó stream bị lỗi hoặc client disconnect. App log có thể chứa 200 vì headers đã commit, trong khi client không nhận được phản hồi hoàn chỉnh.

Tùy instrumentation, nên có field riêng như **error.type=broken_pipe/client_disconnected**, **response_completed=false** hoặc outcome tương đương **nếu đã quan sát được**. Không sửa status đã gửi thành 500 chỉ để phản ánh lỗi body.

### 10.4. Async, streaming, SSE và WebSocket

- Với **async servlet request**, controller/filter đầu tiên có thể trả quyền điều khiển trước khi response kết thúc.
- Với **streaming/SSE**, headers có thể gửi 200 rồi kết nối kéo dài; access log lúc commit và lúc đóng stream đo **hai mốc khác nhau**.
- Với **WebSocket upgrade**, status **101 Switching Protocols** mô tả handshake, không phải trạng thái từng message WebSocket.
- Với **serverless hoặc gateway**, status ở platform có thể được tạo hoặc thay đổi ngoài code Java.

Cần ghi tên event/phase hoặc các field phù hợp để dashboard không trộn "headers sent" với "full body completed".

### 10.5. Retry giữa các service

Một HTTP client có thể gọi một upstream ba lần: lần đầu 503, lần hai 503, lần ba 200. Upstream access log có **ba exchanges**; log của client có thể ghi một **logical business operation** thành công. Đừng tính tỉ lệ lỗi upstream dựa trên một event tổng hợp của client rồi suy ra không có 503.

Cần phân biệt **request attempt ID**, **logical operation ID** và **trace/span IDs**. Nếu muốn đo số thử lại, dùng field retry_attempt hoặc metric riêng khi có khả năng quan sát.

### 10.6. Cache và conditional requests

**304 Not Modified** có ý nghĩa thành công về giao tiếp cache dù không có response body như 200. Lưu lượng từ cache/CDN có thể không đi tới origin service, nên origin access logs không bao phủ toàn bộ request client.

### 10.7. Status 401 và 403

Thông thường 401 liên quan đến **thiếu hoặc không hợp lệ authentication credentials**, còn 403 liên quan đến **từ chối thực hiện**. Tuy nhiên API có thể dùng 404 thay 403 để không tiết lộ sự tồn tại của tài nguyên theo policy. Khi logging, không đưa token, cookie, password hoặc toàn bộ Authorization header vào record.

Một người dùng gửi sai credential nhiều lần có thể làm tăng 401, nhưng chỉ status không đủ kết luận tấn công; cần kết hợp rate, nguồn, hành vi, chính sách và tín hiệu bảo mật khác.

## 11. Status, metrics và SLO: đo đúng mẫu số

Một công thức đơn giản thường gặp:

~~~text
HTTP 5xx ratio = number_of_5xx_responses / number_of_eligible_requests
~~~

Nhưng cần định nghĩa chính xác:

- **Eligible requests** là gì? Có tính health check, load balancer probes, static assets, internal admin API hay không?
- **Mức quan sát**: gateway, application hay client? Nếu app và gateway cùng ghi, không được cộng thẳng mà không khử trùng/tách tầng.
- **Status 4xx**: 404 có thể là bình thường ở search resource; 429 có thể được coi là vượt SLO ở một nhóm người dùng nhưng không ở nhóm khác.
- **Timeout không có HTTP status**: nếu chỉ đếm response status, có thể bỏ qua request mất kết nối trước headers.
- **Sampling/drop**: nếu logs được sampling hoặc queue đầy, đếm log không phải số request thực.
- **Cửa sổ thời gian**: cần xác định event time/ingest time và xử lý late arrivals.
- **Route cardinality**: đừng tạo metric label bằng URL đầy đủ chứa IDs; dùng route template.

Một API có tỉ lệ 5xx thấp nhưng response 200 trả sai dữ liệu vẫn có thể có sự cố nghiệp vụ. Do đó nên theo dõi thêm **latency, success của business transaction, dependency errors, saturation và tracing**.

### 11.1. OpenTelemetry HTTP status và span status

Theo HTTP semantic conventions, thuộc tính **http.response.status_code** ghi status dạng số khi thực sự có status. Đối với **server spans**, 4xx **không tự động có span status Error** theo quy tắc mặc định; 5xx thường được đánh dấu Error. Một 404 đôi khi là expected outcome.

Đừng nhầm trường **span status** của tracing (ví dụ Error) với **http.response.status_code**; chúng có mục đích khác nhau. 500 thường là tín hiệu lỗi, nhưng các nguyên tắc về context và trường hợp request thất bại không có response vẫn cần áp dụng.

## 12. Bảo mật và quyền riêng tư khi ghi status

Status code tự thân thường không chứa PII, nhưng **các field đi kèm** có thể rất nhạy cảm.

### 12.1. Không log dữ liệu thừa

Tránh ghi:

- Toàn bộ **Authorization**, **Cookie**, session token, API key.
- Request/response body chứa mật khẩu, thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết.
- Toàn bộ query string chứa email, token hoặc dữ liệu nhập tự do.
- Địa chỉ IP, user ID, account ID nếu không có mục đích, chính sách và quyền truy cập phù hợp.
- Exception message raw khi có thể chứa URL, SQL parameters hoặc dữ liệu của người dùng.

Nếu cần hỗ trợ một request, ưu tiên **request ID/trace ID** đã validate, **method, route template, status và duration**; logger có thể giữ error class thay vì raw payload.

### 12.2. Log injection từ path hoặc headers

Raw URL, user-agent, x-request-id hoặc custom metadata có thể mang ký tự đặc biệt. Khi ghép text access log, dữ liệu không tin cậy có thể chèn dòng giả (CR/LF) hoặc phá delimiter. Dùng **structured encoder** và escape theo output format; validate các trường ID theo grammar của chúng. 

Một route template như **/orders/{id}** không lộ order ID, ít cardinality và dễ dùng cho metric. Nếu vẫn cần resource ID để điều tra, phải cân nhắc mục đích, redaction và quyền đọc.

### 12.3. Bảo vệ quyền đọc access log

Access log có thể tiết lộ rằng một người đang xem endpoint nhạy cảm, dù không có body. Cần RBAC/ABAC ở collector/dashboard, giới hạn export, retention và audit truy cập theo chính sách tổ chức. Các bản sao CSV/download/report cũng phải được kiểm soát.

## 13. Tích hợp với Logback, Log4j2 và JUL

### 13.1. Chọn cách log một event theo schema

Với SLF4J + backend phù hợp, ví dụ minh họa trong một project đã có logger:

~~~java
// Đoạn code minh họa; không phải class Java độc lập.
logger.info(
        "http.request.completed method={} route={} status={} duration_ms={}",
        method, routeTemplate, responseStatus, durationMillis);
~~~

Đừng chỉ ghép message nếu bạn cần query theo status dạng numeric. Có thể dùng **key-value pairs** của SLF4J 2.x (với provider/encoder hỗ trợ) hoặc structured JSON layout riêng để giữ field typed.

Với Logback, Log4j2 hoặc JUL, trách nhiệm của backend là serialize event và ghi vào appender/handler. **HTTP status không phải mức log của backend**, vì vậy cấu hình root INFO/WARN/ERROR không tự biến thành status 200/400/500.

### 13.2. Access log chuyên dụng

Servlet container như Tomcat có khả năng access logging, thường tạo event theo format có sẵn. Một pattern access log có thể cung cấp method, URI, status và bytes/duration tùy server. Tuy nhiên cú pháp pattern **khác** Logback PatternLayout. Không dùng converter của Logback rồi mong Tomcat access log hiểu.

Khi bật access log ở tầng container, kiểm tra:

- Status field có thật sự là **final status của tầng container** không?
- Có log request bị security filter chặn không?
- Có log async và response error cases không?
- File/stream ở đâu, retention/rotation thế nào?
- Có trùng với log của Spring Filter hoặc gateway không?
- Những field như query string/user-agent có được sanitize không?

### 13.3. Level và volume

Nếu ghi một record INFO cho mọi request trong dịch vụ hàng chục nghìn RPS, log volume có thể lớn. Tùy yêu cầu vận hành, có thể dùng access log chuyên dụng, sampling có chủ đích hoặc metric aggregate. **Không sample các event audit/security bắt buộc phải giữ** chỉ để giảm chi phí, và phải biết sampling ảnh hưởng phép đếm.

Một quyết định cần rõ: **đếm request từ metric**, **điều tra request cụ thể từ trace/log**, **quan sát lỗi từ log/alert**, không dùng một công cụ làm tất cả nếu không đáp ứng yêu cầu độ tin cậy.

## 14. Kiểm thử logging response status

Bảng kiểm tra cho một web application:

| Tình huống | Response client dự kiến | Điều cần kiểm tra trong log |
| --- | --- | --- |
| GET thành công | 200 | Một event có status=200 và route đúng. |
| Tạo tài nguyên | 201 | status=201, không mặc định về 200. |
| Xóa thành công không body | 204 | status=204, không cần body để xác minh. |
| Redirect | 301/302/307/308 | Log từng exchange, không chỉ status sau redirect. |
| Cache conditional | 304 | Hiểu status hợp lệ không có body. |
| Sai payload/syntax | 400 | status=400, không ghi body nhạy cảm. |
| Thiếu authentication | 401 | status=401, không lộ token/header. |
| Bị cấm | 403 hoặc 404 theo policy | Ghi đúng mã gửi và không tiết lộ dữ liệu riêng. |
| Tài nguyên không có | 404 | Không tự đánh ERROR cho mọi 404 nếu là expected. |
| Conflict/version | 409 | Không biến exception nghiệp vụ thành 500 khi đã map. |
| Validation semantics | 422 | Không nhầm với Java exception type. |
| Rate limit | 429 | Đúng status, có metric, chống log flood. |
| Exception chưa xử lý | Thường 500 nếu server trả được HTTP response | Log status đúng sau resolution/container; stack trace phù hợp policy. |
| Service bảo trì | 503 | Phân biệt status được chủ động trả với exception. |
| Gateway timeout | 504 ở gateway | Tìm log ở gateway; app có thể không thấy cùng status. |
| Connection reset trước headers | Không có status | Không tự bịa 500 hay 0. |
| Streaming body bị ngắt sau 200 | Headers có thể đã là 200 | Có error/outcome riêng, không sửa status đã gửi. |
| Async servlet | Tùy kết quả cuối | Không log status quá sớm hoặc nhân đôi event. |
| Request qua gateway | Có thể khác app | Có field hop/service và correlation ID. |
| Nhiều retry | Mỗi attempt có status riêng | Không gộp mọi attempt thành status cuối. |

### 14.1. Cách viết assertion

Một integration test có thể kiểm tra:

1. Client thực sự nhận status dự kiến.
2. Access event của server đúng status, route, method và request ID.
3. Có **một logical access event ở tầng đã định nghĩa** cho mỗi exchange, không duplicate do filter dispatch.
4. Không có token, password, cookie, raw body nhạy cảm trong event.
5. Các 4xx hợp lệ không tạo stack trace thừa hoặc cảnh báo spam ngoài chính sách.
6. 5xx do exception được log sau khi status đã được xác định, hoặc ghi thiếu status có chủ đích nếu chưa gửi được response.
7. Route template có cardinality thấp và không chứa path parameters nhạy cảm.
8. Khi test qua proxy, xác minh **status ở gateway** và **status ở app** bằng hai tập dữ liệu phân biệt.

Đối với Spring MVC, **MockMvc** có thể kiểm tra status của controller/DispatcherServlet path, nhưng không nhất thiết mô phỏng toàn bộ container/gateway/async/production routing. Dùng thêm integration test với server thật khi cần kiểm chứng điểm đo cuối.

## 15. Chẩn đoán khi log status không khớp client

Ví dụ: client nhận **500**, log controller ghi **200**.

### Bước 1 — Xác định đây có phải cùng request

So sánh method, route, timestamp, requestId/traceId, service, instance và deployment version. Tránh so hai request khác nhau có cùng URL.

### Bước 2 — Xác định hai tầng quan sát

Log controller ở application? Status client do gateway quyết định? Có WAF, load balancer, cache hoặc service mesh ở giữa? Nếu là hai hop, status có thể khác một cách hợp lệ.

### Bước 3 — Kiểm tra thời điểm ghi

Dòng 200 được ghi trước khi filter chain hoàn thành? Sau đó exception resolver, error dispatch hoặc response commit có thay đổi status? Nếu status đã commit 200 mà body lỗi, client có thể báo lỗi vận chuyển thay vì nhận 500 thật.

### Bước 4 — Kiểm tra cấu hình logging và exporter

Có event bị drop? Có hai access log nguồn khác nhau? Field status bị parser đổi kiểu, collector normalize hoặc dashboard hiển thị status của một hop khác?

### Bước 5 — Kiểm chứng với request độc lập

Gửi request thử có correlation ID an toàn, thu status từ client, capture access log ở application và gateway, kiểm tra trace tương ứng. Dùng **một request mỗi lần** để tránh nhầm do concurrency, sau đó thử lại dưới tải.

### Bước 6 — Sửa tại điểm phát sinh

Nếu log quá sớm, chuyển điểm ghi về completion hook phù hợp. Nếu gateway rewrite, gắn source/hop. Nếu controller ghi status dự đoán, thay bằng status thực tế. Nếu parser làm sai, sửa schema thay vì sửa mã HTTP của controller.

**Không sửa log cũ hoặc gắn nhãn 500 cho một record 200 chỉ để đồ thị đẹp**; việc quan sát sai phải được sửa ở instrumentation và có regression test.

## 16. Lỗi phổ biến cần tránh

**1. Ghi 200 tại thời điểm bắt đầu request.** Status có thể đổi thành 401, 404 hoặc 500 sau filter/controller/exception handler.

**2. Dựa vào exception để suy ra status.** Exception có thể được map thành 404/409; response 503 có thể được trả mà không có exception.

**3. Xem mọi 4xx là lỗi server nghiêm trọng.** 404, 409, 422 và cả 401 có thể được API dự kiến. Cần phân tích tần suất và ngữ cảnh.

**4. Xem response status và log severity là cùng một thứ.** Status=500 không nhất thiết có nghĩa mọi access log phải ERROR; cần schema và chính sách rõ.

**5. Tưởng root INFO ngăn được mọi ERROR event.** Level log và HTTP status không có mapping mặc định, và các filter/appender có thể có rule riêng.

**6. Chỉ log ở controller.** Security filter, static resources, error pages và gateway có thể không qua controller.

**7. Quên async và ERROR dispatch.** Access filter ghi hai event hoặc ghi status trước khi response cuối được gửi.

**8. Nhầm gateway 502/504 với service 502/504.** Một tầng khác có thể sinh status.

**9. Biến timeout/no response thành status 0 hoặc 500.** Chỉ ghi numeric status khi có giá trị; log network error riêng.

**10. Dùng URL thô làm metric label.** Path chứa order ID làm tăng cardinality và có thể rò rỉ dữ liệu.

**11. Log toàn bộ URL/query/body để tiện debug.** Có thể lộ token/PII, gây log injection hoặc tăng chi phí.

**12. Đếm SLO từ log đã sampling/drop mà không hiệu chỉnh.** Cần nguồn metric đáng tin, xác định mẫu số và tầng đo.

**13. Bỏ qua redirect và retry.** Một thao tác người dùng có thể tạo nhiều HTTP exchanges với các status khác nhau.

**14. Không gắn service/environment/trace.** Khi status không khớp, khó biết đó là record của hop nào.

**15. Chỉ test 200 và 500.** Bỏ sót 201, 204, 304, 401, 403, 409, 429 và status do framework/security tạo.

**16. Ghi raw exception trong mọi access event.** Tăng volume và có thể lộ dữ liệu; nên tách access event chuẩn với error detail theo policy.

**17. Cho rằng có HTTP status là client đã nhận đủ body.** Lỗi I/O có thể xảy ra sau khi headers đã gửi.

**18. Lấy trạng thái cuối trong HttpClient rồi gán cho từng hop redirect.** Mỗi hop có status riêng; log client và server phải định nghĩa phạm vi.

## 17. Bài tập thực hành

**Bài 1 — Tự chạy Java 17.** Biên dịch và chạy ResponseStatusDemo.java, so sánh ba cặp ACCESS/CLIENT. Vì sao status=503 được ghi dù code không ném exception?

**Bài 2 — Thêm 201.** Mở rộng statusFor với /created trả 201; thêm request client và tăng CountDownLatch tương ứng. Dự đoán output theo đúng thứ tự.

**Bài 3 — Kiểm tra status chưa có.** Trong môi trường thử nghiệm, quan sát getResponseCode trước sendResponseHeaders. Giải thích tại sao -1 không được xuất thành HTTP 500 trong field status.

**Bài 4 — Spring MVC.** Thiết kế ba endpoint: thành công 200, resource missing 404 qua @ExceptionHandler và service unavailable 503 không ném exception. Chỉ ra tại đâu nên đo status để bắt được cả ba.

**Bài 5 — Spring Security.** Request chưa xác thực nhận 401 hoặc redirect theo cấu hình authentication. Controller có được gọi không? Filter/interceptor nào có thể quan sát status?

**Bài 6 — Async.** Mô tả tại sao filter ghi trong finally của dispatch đầu có thể in status=200 dù request cuối cùng lỗi, và cách chọn completion hook.

**Bài 7 — Gateway.** Cho gateway kết thúc bằng 504 trong khi app có request xử lý lâu. Những log/metric ở hai tầng cần so sánh là gì?

**Bài 8 — Privacy.** Chuyển URL /users/1234/orders?token=secret thành log sử dụng route template /users/{id}/orders; xác định field nào được phép giữ để vẫn có correlation.

**Bài 9 — SLO.** Viết định nghĩa 5xx ratio có mẫu số rõ ràng, loại health checks nếu policy yêu cầu và xử lý request timeout không có response. Vì sao không nên tính trực tiếp bằng số dòng từ hai access log nguồn khác nhau?

## 18. Ghi nhớ

**Response status trong logging web Java là mã HTTP thực sự được xác định tại một tầng quan sát, không phải giá trị đoán trước từ exception hoặc controller.** Để ghi đúng, cần biết **điểm hoàn tất/commit**, các luồng **async/error**, status do **gateway** có thể khác application và các request **retry/redirect** có thể sinh nhiều status.

Một access event tốt thường gồm **method, route template, numeric status, duration, service/environment và correlation ID**, không chứa secret hoặc dữ liệu thừa. Ghi status giúp điều tra; metrics/tracing giúp đo sức khỏe hệ thống. Khi HTTP response chưa tồn tại, hãy **để status vắng mặt và biểu diễn lỗi vận chuyển riêng**, thay vì tạo mã giả.

### Tài liệu tham khảo chính thức

- RFC 9110 — HTTP Semantics và status codes: https://www.rfc-editor.org/rfc/rfc9110
- Oracle Java 17 — HttpExchange, sendResponseHeaders và getResponseCode: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- Oracle Java 17 — HttpServer: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Oracle Java 17 — Filter.afterHandler: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html
- Spring Framework — OncePerRequestFilter Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework — Observability Support: https://docs.spring.io/spring-framework/reference/integration/observability.html
- Spring Boot — Observability: https://docs.spring.io/spring-boot/reference/actuator/observability.html
- OpenTelemetry — HTTP semantic conventions: https://opentelemetry.io/docs/specs/semconv/http/http-spans/
- OpenTelemetry — HTTP metrics: https://opentelemetry.io/docs/specs/semconv/http/http-metrics/
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html