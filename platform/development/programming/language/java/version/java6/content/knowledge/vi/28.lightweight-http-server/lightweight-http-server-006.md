# HTTP server gọn: Filter và tách logic dùng chung

## Mục tiêu học tập

Trong Java, module chuẩn **`jdk.httpserver`** cung cấp `com.sun.net.httpserver.HttpServer`, một HTTP server tối giản thích hợp cho ví dụ học tập, công cụ nội bộ, test fixture và các dịch vụ có nhu cầu cụ thể. Với nhiều endpoints, các đoạn logic như **request ID, xác thực, kiểm tra method, response headers, logging, metrics và giới hạn request** rất dễ bị sao chép vào nhiều `HttpHandler`. Kết quả là code lặp, ranh giới bảo mật không thống nhất và thay đổi policy phải sửa hàng loạt file.

**`Filter`** giúp tách **cross-cutting concerns** ra khỏi handler, cho phép xử lý request **trước** và quan sát response **sau** logic nghiệp vụ. Các filters được sắp xếp thành một **chain gắn với `HttpContext`**.

~~~text
Incoming HTTP request
          │
          ▼
HttpServer chọn HttpContext theo request path
          │
          ▼
Filter A: metadata/observability (before)
          │
          ▼
Filter B: requestId/tracing (before)
          │
          ▼
Filter C: authentication → 401 nếu fail
          │
          ▼
Filter D: HTTP method   → 405 nếu fail
          │
          ▼
HttpHandler: endpoint business logic → response
          │
          ▼
Dòng control quay ngược: D → C → B → A (after)
          │
          ▼
HTTP response tới client
~~~

Sau bài học, bạn sẽ:

1. Phân biệt **`HttpServer`**, **`HttpContext`**, **`HttpHandler`**, **`HttpExchange`**, **`Filter`** và **`Filter.Chain`**.
2. Hiểu **chain-of-responsibility** trong `Filter.doFilter(exchange, chain)` và tác dụng của việc gọi hoặc không gọi `chain.doFilter(exchange)`.
3. Thêm filters theo thứ tự vào `HttpContext.getFilters()`, biết thứ tự **before** và **after** là hai chiều khác nhau.
4. Sử dụng **`Filter.beforeHandler(...)`**, **`Filter.afterHandler(...)`** và hiểu trường hợp phù hợp với **`Filter.adaptRequest(...)`** (API còn được hỗ trợ trong Java 17+).
5. Viết **custom Filter** khi cần trả 401/403/405, ngắt chain hoặc dùng `try/finally` cho metrics/cleanup.
6. Chia sẻ metadata của một request bằng **`HttpExchange.setAttribute/getAttribute`** thay vì biến global hoặc instance fields thiếu thread-safety.
7. Tách shared HTTP infrastructure logic khỏi domain/service, gắn filter đúng **HttpContext**, không nhầm context filter với global middleware.
8. Quản lý **response headers/body, content-length tính theo bytes, exchange.close, request body, executor và shutdown** đúng cách.
9. Hiểu giới hạn của **longest-prefix matching**, 401 vs 403 vs 405, response đã gửi, auth, CORS, TLS và input limits.
10. Chạy ví dụ **Java 17+ độc lập** trên loopback bằng `HttpServer` và `java.net.http.HttpClient`, so khớp 9 dòng output kiểm thử: 200, 401, 405, 404, health 200 và audit chain.
11. Xây unit/integration tests cho short-circuit, ordering, concurrency, exception paths và tài nguyên I/O.
12. Nhận biết anti-pattern: duplicate handlers, log credentials, gửi response hai lần, catch IOException rồi bỏ, giữ `HttpExchange` vượt khỏi request lifecycle.

**Phiên bản hiện hành:** `Filter`, `HttpServer` và `HttpExchange` là API chuẩn của module **`jdk.httpserver`** còn có trong Java SE/JDK 17 và 26. `Filter.beforeHandler`, `Filter.afterHandler` và `Filter.adaptRequest` được giới thiệu từ Java 17. Ví dụ được biên dịch trên **OpenJDK 24.0.2** với `javac --release 17`. Không dùng Servlet Filter hoặc API cũ đã lỗi thời.

---

## 1. Tại sao cần Filter thay vì viết hết trong HttpHandler?

### 1.1. Vấn đề handler ôm nhiều trách nhiệm

Giả sử ba endpoints đều yêu cầu một API key và request ID:

~~~text
GET /api/orders
GET /api/customers
GET /api/products
~~~

Một cách làm dễ mắc lỗi:

~~~java
// MẢNH MINH HỌA — không phải source runnable độc lập.
void handleOrders(HttpExchange exchange) throws IOException {
    // validate API key
    // validate request method
    // tạo request ID
    // set response headers
    // ghi access log và duration
    // truy vấn orders rồi gửi response
}
~~~

Nếu mỗi handler lặp sáu bước đầu, chỉ cần một handler mới quên auth đã tạo ra lỗ hổng. Nếu policy đổi từ GET-only sang GET+HEAD, phải sửa nhiều nơi. Nếu logging vô tình ghi cả `Authorization` header, rủi ro tăng trên mọi endpoint.

Một cách tách trách nhiệm hợp lý:

| Thành phần | Nên đảm nhận | Tránh đảm nhận |
| --- | --- | --- |
| `HttpServer` | Bind address/port, dispatch, server lifecycle | Domain validation, authorization rules riêng resource |
| `HttpContext` | Mapping path + handler + filter list | Tự triển khai route params/framework |
| `HttpHandler` | Đọc input cụ thể, gọi service, tạo endpoint response | Copy/paste tracing/auth/log chung |
| `Filter` | Cross-cutting request/response policy | Toàn bộ xử lý đơn hàng/thanh toán |
| `Filter.Chain` | Gọi filter/handler tiếp theo | Tự ý gọi handler nhiều lần |
| `HttpExchange` | Request method, URI, headers/body, attributes, response | Lưu giữ sang request kế tiếp |
| Service/domain | Quy tắc nghiệp vụ và business authorization | Phụ thuộc trực tiếp vào HTTP implementation nếu không cần |

**Nguyên tắc:** đặt một concern vào Filter nếu nó thực sự áp dụng cho nhiều handlers và không phụ thuộc sâu vào một use case. Đặt các business invariants trong service/domain. Đặt việc chuyển request/response của endpoint trong handler.

### 1.2. Filter là một chuỗi, không phải decorator tĩnh

`Filter` có cả **pre-processing** và **post-processing**. Nó khác việc chỉ gọi một utility method trước khi handler bắt đầu.

~~~text
Filter A: pre
  Filter B: pre
    Filter C: pre
      HttpHandler.handle()
    Filter C: post
  Filter B: post
Filter A: post
~~~

Nếu Filter B từ chối và **không gọi chain**, Filter C và handler **không chạy**. Tuy vậy, Filter A vẫn có thể chạy phần sau khi lời gọi chain của nó trả về, vì A đã bắt đầu bao quanh B. Điều này rất hữu ích cho logging status của requests bị từ chối.

---

## 2. API `Filter` và `Filter.Chain`

### 2.1. Import và khai báo

~~~java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
~~~

`Filter` là **abstract class**. Custom class phải override **`description()`** và **`doFilter(HttpExchange, Filter.Chain)`**.

~~~java
// MẢNH MINH HỌA — lớp tối giản.
public final class SampleFilter extends Filter {
    @Override
    public String description() {
        return "An example filter";
    }

    @Override
    public void doFilter(HttpExchange exchange, Filter.Chain chain)
            throws IOException {
        // Tiền xử lý trước:
        chain.doFilter(exchange);
        // Hậu xử lý sau:
    }
}
~~~

Một filter có thể:

- Đọc request headers/method/path.
- Thêm/sửa response headers **trước khi response bắt đầu**.
- Lưu metadata bằng `exchange.setAttribute`.
- Bọc request/response streams qua `exchange.setStreams` khi thật sự cần.
- Gọi `chain.doFilter(exchange)` để xử lý tiếp.
- Không gọi chain và **tự hoàn tất response** khi request bị từ chối.

**`Filter.Chain.doFilter(exchange)`** sẽ gọi Filter tiếp theo hoặc handler cuối cùng. Nó có thể ném **`IOException`**. Theo Javadoc, một `IOException` phát sinh từ chuỗi cần được rethrow nếu filter bắt nó; không nên im lặng bỏ lỗi I/O.

### 2.2. Thứ tự filters

~~~java
// MẢNH MINH HỌA: ctx là một HttpContext đã tạo.
ctx.getFilters().add(new FilterA());
ctx.getFilters().add(new FilterB());
ctx.getFilters().add(new FilterC());
~~~

Giả sử mọi filter có một đoạn trước và một đoạn sau:

~~~text
A.before
B.before
C.before
handler
C.after
B.after
A.after
~~~

Do đó **thứ tự đăng ký** là một phần của security/observability behavior. Nếu đặt auth trước trace, những requests bị auth chặn trước trace sẽ không có request ID do tracing tạo. Nếu đặt status observer ngoài cùng, nó thấy normal returns của cả những requests bị filters bên trong short-circuit.

### 2.3. Khi nào được short-circuit?

~~~java
// MẢNH MINH HỌA trong doFilter — respond là helper có gửi response.
if (!isAllowed(exchange)) {
    respond(exchange, 403, "forbidden");
    return; // Không gọi chain.doFilter nữa.
}
chain.doFilter(exchange);
~~~

Nếu Filter không gọi chain, nó **phải trả response thích hợp** hoặc kết thúc exchange theo error policy. Chỉ `return` không gửi gì có thể khiến client chờ đến timeout.

**Không gọi chain hai lần** với cùng một `HttpExchange` để “kiểm tra lại”: handler có thể đã đọc request body, gửi response, ghi database hoặc phát event. Thực thi lần hai có thể gây side effects lặp và lỗi double send.

### 2.4. IOException và cleanup

~~~java
// MẢNH MINH HỌA bên trong doFilter.
long start = System.nanoTime();
try {
    chain.doFilter(exchange);
} finally {
    long elapsedNanos = System.nanoTime() - start;
    // Ghi metrics an toàn; không thay đổi response đã gửi.
}
~~~

`finally` chạy khi `chain.doFilter` trở về hoặc ném exception. Nhưng nếu mã trong finally ném lỗi khác thì có thể che exception gốc. Hệ thống logging/metrics nên chịu lỗi, giới hạn tài nguyên và không tự phá response.

---

## 3. Ba factory methods hữu ích của Filter trong Java 17+

### 3.1. `Filter.beforeHandler(...)`

~~~java
Filter headerFilter = Filter.beforeHandler(
        "Set response metadata",
        exchange -> exchange.getResponseHeaders().set(
                "X-App-Version", "1"));

ctx.getFilters().add(headerFilter);
~~~

`beforeHandler` chạy `Consumer<HttpExchange>` **trước khi gọi filter/handler tiếp theo**. Phù hợp để gắn headers, đặt attributes hoặc xử lý metadata không cần trả response riêng.

**Không nên gửi response hay làm authentication short-circuit trong `beforeHandler`** vì loại filter này được thiết kế để **tiếp tục gọi chain**. Consumer cũng không khai báo checked `IOException`, nên custom Filter phù hợp hơn nếu logic cần I/O và ngắt chain.

### 3.2. `Filter.afterHandler(...)`

~~~java
Filter statusObserver = Filter.afterHandler(
        "Observe response status",
        exchange -> System.out.println(
                "status=" + exchange.getResponseCode()));

ctx.getFilters().add(statusObserver);
~~~

Operation chạy **sau filter tiếp theo hoặc handler đã trở về**. Lúc này response headers/body thường đã gửi; dùng nó để **quan sát status hoặc exchange attributes**, không cố thêm response header hoặc thay HTTP status.

Nếu có hai filters dạng after:

~~~text
Đăng ký: afterA, afterB
Thực thi: handler → afterB → afterA
~~~

**Đừng nhầm `afterHandler` với một `finally` chắc chắn chạy khi inner chain ném exception**. API mô tả operation sau khi chain thực hiện xong. Muốn ghi metrics kể cả exception paths, dùng custom Filter `try/finally`.

### 3.3. `Filter.adaptRequest(...)`

~~~java
Filter addFoo = Filter.adaptRequest(
        "Add a harmless internal header",
        request -> request.with("Foo", java.util.List.of("Bar")));

ctx.getFilters().add(addFoo);
~~~

`adaptRequest` tạo một filter tiền xử lý, có thể inspect/adapt request state được truyền cho downstream. Nó **không tự xác thực danh tính**. Không dùng nó để giả mạo một `X-User` rồi tin rằng client đã được authenticated.

Nếu chỉ cần request-local metadata, **`exchange.setAttribute`** thường thích hợp hơn việc đổi request header view. Chỉ adapt request khi yêu cầu protocol/architecture rõ ràng và không tạo nhầm lẫn về dữ liệu client thực gửi.

### 3.4. Nên dùng helper nào?

| Bài toán | Giải pháp |
| --- | --- |
| Set header `X-Application` trước handler | `beforeHandler` |
| Ghi status sau handler | `afterHandler` |
| Adapt view của request | `adaptRequest` |
| Trả 401/403 khi chưa có quyền | **Custom Filter** |
| Trả 405 và `Allow` cho method sai | **Custom Filter** |
| Ghi thời gian thành công/lỗi bằng finally | **Custom Filter** |
| Bọc body stream/đếm bytes | **Custom Filter** |
| Gắn `requestId` vào exchange | beforeHandler hoặc custom Filter |
| Validate giá trị nghiệp vụ | **Domain/service**, không nhét vào filter |

---

## 4. Tách concern: tracing, auth, method, response helper

### 4.1. Tracing và attributes

~~~java
// MẢNH MINH HỌA trong custom Filter:
String traceId = "req-" + idGenerator.incrementAndGet();
exchange.setAttribute("app.requestId", traceId);
exchange.getResponseHeaders().set("X-Request-Id", traceId);
chain.doFilter(exchange);

// MẢNH MINH HỌA trong handler:
String requestId = (String) exchange.getAttribute("app.requestId");
~~~

`exchange.setAttribute` lưu dữ liệu gắn với **một exchange**, tránh race condition giữa requests. Nếu filter dùng chung giữa contexts/threads, **không đặt requestId vào một mutable instance field của Filter**.

Trên production, `req-1` không đủ vì trùng khi server restart hoặc có nhiều instances. Dùng một format correlation ID/trace context thích hợp, có policy chống injection/guessing, không tin mù quáng raw ID do client tự gửi.

### 4.2. Auth filter

Custom Filter có thể kiểm tra một header/identity rồi:

~~~text
Nếu credential không hợp lệ:
    sendResponseHeaders(401, ...)
    write/close body
    return (không gọi chain)
Nếu hợp lệ:
    setAttribute(verified identity, ...)
    chain.doFilter(exchange)
~~~

Đây là **authentication**, chưa chắc là **authorization**. Một token hợp lệ thuộc customer A không tự có quyền xem order của customer B; service/handler còn phải kiểm tra resource ownership, tenant, role và business policy.

### 4.3. Method policy filter

Nếu context chỉ chấp nhận GET:

~~~java
// MẢNH MINH HỌA trong doFilter.
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");
    respond(exchange, 405, "method-not-allowed");
    return;
}
chain.doFilter(exchange);
~~~

HTTP method có phân biệt chữ hoa/thường theo protocol. Nếu cần HEAD/OPTIONS/CORS preflight, thiết kế policy cụ thể, không trả body tùy ý cho HEAD hoặc chặn OPTIONS một cách vô ý.

### 4.4. Response helper chung

~~~java
// MẢNH MINH HỌA có các imports HttpExchange, IOException,
// OutputStream và StandardCharsets.
static void respond(HttpExchange exchange, int status, String text)
        throws IOException {
    byte[] payload = text.getBytes(StandardCharsets.UTF_8);
    try (exchange) {
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(status, payload.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(payload);
        }
    }
}
~~~

Trong `sendResponseHeaders`, `responseLength > 0` nghĩa là số **bytes** body cố định và phải ghi **đúng** số bytes đó. `responseLength == 0` là chunked response; `-1` là không có body. **Đừng truyền `String.length()` cho UTF-8 có dấu hoặc emoji**.

Khi closing OutputStream, InputStream của request cũng được đóng nếu chưa đóng. Tuy nhiên nếu body chưa được consume đủ, TCP connection có thể không được reuse. Application phải có body-size/time limits và chính sách drain/abort hợp lý.

### 4.5. Status codes chuẩn

| Status | Tình huống | Ghi chú |
| --- | --- | --- |
| 200 | Thành công, trả nội dung | Method/body/encoding phù hợp |
| 401 | Chưa được xác thực | Với auth scheme chuẩn cần header/challenge thích hợp |
| 403 | Có identity nhưng thiếu quyền | Không tiết lộ chi tiết nhạy cảm |
| 404 | Không tìm thấy route/resource | Có thể áp dụng visibility policy |
| 405 | HTTP method không được phép | Gắn `Allow` đúng các methods cho resource |
| 413 | Request body quá lớn | Size enforcement trước/khi streaming |
| 429 | Rate limiting | Cần quota đúng và retry policy |
| 500 | Internal failure | Chỉ có thể gửi khi response chưa bắt đầu |
| 503 | Service unavailable | Không mặc định dùng cho mọi exception |

Trong demo, 401/405/404 là short-circuit và exact route guard, không phải một auth framework hoàn chỉnh. Không tự lấy một message từ exception rồi gửi ra client khi nó có thể chứa token/PII.

---

## 5. Filter chỉ gắn với HttpContext và context path không phải exact route

### 5.1. Mỗi context có filter list riêng

~~~java
// MẢNH MINH HỌA.
HttpContext orders = server.createContext("/api/orders", ordersHandler);
orders.getFilters().addAll(apiFilters);

HttpContext health = server.createContext("/health", healthHandler);
// Không có apiFilters; health không đi qua auth/tracing API.
~~~

Đây là behavior quan trọng: **Filter không tự chạy cho toàn bộ HttpServer**. Một endpoint mới nếu quên gắn auth filter vẫn có thể hoạt động không bảo vệ. Nên có helper dùng chung để cấu hình contexts hoặc audit danh sách contexts/filters trong tests.

Có thể gắn cùng filter instance vào nhiều contexts nếu filter **thread-safe**, nhưng tốt hơn dùng immutable configuration và không lưu per-request state vào instance fields.

### 5.2. Longest matching literal prefix

Theo tài liệu `HttpServer`, path được chọn dựa trên **longest matching literal prefix**, case-sensitive, không có một route matcher linh hoạt như nhiều web frameworks.

~~~text
Context = /api/hello

GET /api/hello          → match
GET /api/hello/extra    → prefix match
GET /api/helloXYZ       → prefix match
GET /API/hello          → không match do case
~~~

Nếu handler chỉ cho đúng `/api/hello`:

~~~java
// MẢNH MINH HỌA.
if (!"/api/hello".equals(exchange.getRequestURI().getPath())) {
    respond(exchange, 404, "not-found");
    return;
}
~~~

**Đây là kiểm tra path đơn giản cho demo**, không thay thế route/path canonicalization có tính bảo mật. Với reverse proxy, percent encoding, decoded path, `getRawPath()` và normalize, cần một policy nhất quán để tránh bypass hoặc route confusion.

### 5.3. Reuse filters và concurrency

~~~java
// MẢNH MINH HỌA.
Filter commonTrace = new TraceFilter();
orders.getFilters().add(commonTrace);
customers.getFilters().add(commonTrace);
~~~

Nếu filter dùng `AtomicLong`, thread-safe metrics hoặc immutable settings, có thể chia sẻ an toàn. Nếu dùng một `StringBuilder` field rồi append request IDs của các threads, sẽ race và trộn dữ liệu.

**Khuyến nghị:** tất cả request-local data nằm trong local variables/attributes, không ghi thẳng vào static fields, shared mutable lists không đồng bộ hay ThreadLocal không có cleanup rõ. Test nhiều requests đồng thời.

### 5.4. Đăng ký trước `server.start()`

~~~java
HttpServer server = HttpServer.create(address, backlog);
HttpContext api = server.createContext("/api/hello", handler);
api.getFilters().addAll(filters);
server.setExecutor(executor);
server.start();
~~~

Đăng ký filter/config **trước start** giúp giữ một cấu hình xác định. Không chỉnh sửa danh sách filters tùy tiện trong lúc nhiều threads đang xử lý requests. Nếu cần cập nhật policy động, thiết kế immutable snapshot/hot reload một cách thread-safe.

---

## 6. Chương trình Java 17+ hoàn chỉnh: 5 requests và chain có thứ tự

File **`HttpFilterSharedLogicDemo.java`** chứa toàn bộ chương trình. Nó:

1. Tạo `HttpServer` trên **`127.0.0.1:0`** (chỉ loopback; OS cấp port ngẫu nhiên).
2. Dùng `Executors.newFixedThreadPool(2)` để server có executor xác định.
3. Đăng ký context `/api/hello` và **5 filters**: `Filter.afterHandler`, `Filter.beforeHandler`, `TraceFilter`, `DemoAuthFilter`, `GetOnlyFilter`.
4. Đăng ký `/health` không có API filters.
5. Gửi tuần tự 5 HTTP requests bằng `HttpClient`.
6. In mã phản hồi, body, trace IDs, header `Allow`, header từ beforeHandler và audit sequence.
7. Gọi `server.stop(0)` và shutdown executor trong `finally`.
8. Không cần dependency nào ngoài JDK; không mở public listener.

**Cảnh báo:** `DEMO_KEY` là chuỗi giả chỉ dùng trong unit/integration demo trên loopback. Đây **không phải hệ thống xác thực production**, vì hardcoded key và plain HTTP không an toàn khi đưa ra mạng. Hệ thống thực cần TLS/trusted proxy, authentication provider, key rotation, quota và security review.

### 6.1. Source duy nhất: HttpFilterSharedLogicDemo.java

~~~java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
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
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class HttpFilterSharedLogicDemo {
    private static final String DEMO_KEY = "local-demo-only";
    private static final AtomicInteger IDS = new AtomicInteger();
    private static final List<String> EVENTS = new CopyOnWriteArrayList<>();

    private static void respond(HttpExchange exchange, int status, String message)
            throws IOException {
        byte[] data = message.getBytes(StandardCharsets.UTF_8);
        try (exchange) {
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, data.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(data);
            }
        }
    }

    static final class TraceFilter extends Filter {
        @Override
        public String description() {
            return "Per-request trace ID and around-chain observation";
        }

        @Override
        public void doFilter(HttpExchange exchange, Chain chain)
                throws IOException {
            String requestId = "req-" + IDS.incrementAndGet();
            exchange.setAttribute("requestId", requestId);
            exchange.getResponseHeaders().set("X-Request-Id", requestId);
            EVENTS.add("trace-enter");
            try {
                chain.doFilter(exchange);
            } finally {
                EVENTS.add("trace-exit");
            }
        }
    }

    static final class DemoAuthFilter extends Filter {
        @Override
        public String description() {
            return "Example local-only API key check";
        }

        @Override
        public void doFilter(HttpExchange exchange, Chain chain)
                throws IOException {
            if (!DEMO_KEY.equals(
                    exchange.getRequestHeaders().getFirst("X-Demo-Key"))) {
                EVENTS.add("auth-denied");
                respond(exchange, 401, "unauthorized");
                return; // No chain.doFilter: handler never runs.
            }
            EVENTS.add("auth-allowed");
            chain.doFilter(exchange);
        }
    }

    static final class GetOnlyFilter extends Filter {
        @Override
        public String description() {
            return "Shared GET-only request policy";
        }

        @Override
        public void doFilter(HttpExchange exchange, Chain chain)
                throws IOException {
            if (!"GET".equals(exchange.getRequestMethod())) {
                EVENTS.add("method-denied");
                exchange.getResponseHeaders().set("Allow", "GET");
                respond(exchange, 405, "method-not-allowed");
                return;
            }
            EVENTS.add("method-allowed");
            chain.doFilter(exchange);
        }
    }

    private static HttpResponse<String> call(
            HttpClient client, String url, String method, boolean authorized)
            throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(URI.create(url))
                .timeout(java.time.Duration.ofSeconds(3));
        if (authorized) {
            request.header("X-Demo-Key", DEMO_KEY);
        }
        if ("POST".equals(method)) {
            request.POST(HttpRequest.BodyPublishers.noBody());
        } else {
            request.GET();
        }
        return client.send(request.build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    private static String requestId(HttpResponse<String> response) {
        return response.headers().firstValue("X-Request-Id").orElse("none");
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        server.setExecutor(executor);
        try {
            HttpContext api = server.createContext("/api/hello", exchange -> {
                if (!"/api/hello".equals(exchange.getRequestURI().getPath())) {
                    EVENTS.add("path-denied");
                    respond(exchange, 404, "not-found");
                    return;
                }
                EVENTS.add("handler");
                respond(exchange, 200,
                        "hello:" + exchange.getAttribute("requestId"));
            });

            // Filters run in list order; after-handler callbacks run
            // on the way back through the nested chain.
            api.getFilters().add(Filter.afterHandler(
                    "Observe final status after handler",
                    ex -> EVENTS.add("after:" + ex.getResponseCode())));
            api.getFilters().add(Filter.beforeHandler(
                    "Set shared response header before handling",
                    ex -> {
                        ex.getResponseHeaders().set("X-Mode", "filtered");
                        EVENTS.add("before");
                    }));
            api.getFilters().addAll(List.of(
                    new TraceFilter(),
                    new DemoAuthFilter(),
                    new GetOnlyFilter()));

            // A distinct context with no API filters.
            server.createContext("/health",
                    exchange -> respond(exchange, 200, "ok"));
            server.start();

            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            HttpClient client = HttpClient.newHttpClient();
            HttpResponse<String> ok = call(
                    client, base + "/api/hello", "GET", true);
            HttpResponse<String> denied = call(
                    client, base + "/api/hello", "GET", false);
            HttpResponse<String> wrongMethod = call(
                    client, base + "/api/hello", "POST", true);
            HttpResponse<String> extraPath = call(
                    client, base + "/api/hello/extra", "GET", true);
            HttpResponse<String> health = call(
                    client, base + "/health", "GET", false);

            System.out.println("ok=" + ok.statusCode()
                    + ":" + ok.body() + ":" + requestId(ok));
            System.out.println("unauthorized=" + denied.statusCode()
                    + ":" + denied.body() + ":" + requestId(denied));
            System.out.println("wrongMethod=" + wrongMethod.statusCode()
                    + ":" + wrongMethod.body() + ":" + requestId(wrongMethod));
            System.out.println("allow=" + wrongMethod.headers()
                    .firstValue("Allow").orElse("missing"));
            System.out.println("prefixMismatch=" + extraPath.statusCode()
                    + ":" + extraPath.body() + ":" + requestId(extraPath));
            System.out.println("health=" + health.statusCode()
                    + ":" + health.body() + ":" + requestId(health));
            System.out.println("filteredHeader=" + ok.headers()
                    .firstValue("X-Mode").orElse("missing"));
            System.out.println("requestsWithTrace=" + IDS.get());
            System.out.println("events=" + String.join("|", EVENTS));
        } finally {
            server.stop(0);
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

### 6.2. Biên dịch và chạy

Lưu source đúng tên **`HttpFilterSharedLogicDemo.java`**, dùng JDK 17+:

~~~bash
javac -encoding UTF-8 --release 17 --add-modules jdk.httpserver HttpFilterSharedLogicDemo.java
java --add-modules jdk.httpserver HttpFilterSharedLogicDemo
~~~

`jdk.httpserver` là JDK module còn được hỗ trợ. `--add-modules jdk.httpserver` nêu rõ requirement, tránh phụ thuộc module resolution mặc định. Trong dự án có `module-info.java`, khai báo `requires jdk.httpserver;` và `requires java.net.http;` khi sử dụng HttpClient.

Chương trình chỉ bind loopback và tự gửi requests nội bộ; port ngẫu nhiên được dùng nên có thể chạy khi port 8000/8080 đã có dịch vụ khác. Trong sandbox cấm mở loopback socket, ứng dụng có thể thất bại do network policy; đó không phản ánh sai logic Filter.

### 6.3. Stdout chính xác đã kiểm chứng

~~~text
ok=200:hello:req-1:req-1
unauthorized=401:unauthorized:req-2
wrongMethod=405:method-not-allowed:req-3
allow=GET
prefixMismatch=404:not-found:req-4
health=200:ok:none
filteredHeader=filtered
requestsWithTrace=4
events=before|trace-enter|auth-allowed|method-allowed|handler|trace-exit|after:200|before|trace-enter|auth-denied|trace-exit|after:401|before|trace-enter|auth-allowed|method-denied|trace-exit|after:405|before|trace-enter|auth-allowed|method-allowed|path-denied|trace-exit|after:404
~~~

**Đã biên dịch và chạy trên OpenJDK 24.0.2 với `--release 17`, khớp chính xác cả 9 dòng.** Requests được gửi tuần tự để audit sequence xác định; thread-safe list/counter chỉ phục vụ demo, không phải một observability backend sản xuất.

### 6.4. Đọc từng request

**GET có key:** `ok=200:hello:req-1:req-1` nghĩa là handler nhận `requestId=req-1` từ attribute, response có `X-Request-Id:req-1`, xác thực/method pass.

**GET thiếu key:** `unauthorized=401:unauthorized:req-2` nghĩa là auth filter đã gửi response và **không gọi chain**. Sau đó method filter/handler không chạy, dù outer tracing filter vẫn ghi exit và afterHandler observer vẫn ghi status.

**POST có key:** `wrongMethod=405:method-not-allowed:req-3` kèm `allow=GET`, nghĩa là method filter từ chối trước handler.

**GET `/api/hello/extra`:** `prefixMismatch=404:not-found:req-4` cho thấy HttpServer prefix dispatch đã đến handler; exact path guard mới phát hiện path không hợp lệ.

**GET `/health`:** `health=200:ok:none`, nghĩa là không có X-Request-Id do API filter tạo vì đây là context khác.

**Audit:** mỗi request qua API có `before → trace-enter` rồi `trace-exit → after:status`. Handler chỉ xuất hiện khi cả auth và method pass, đúng short-circuit semantics.

### 6.5. Vì sao không dùng afterHandler để đặt X-Mode?

`Filter.afterHandler` chạy khi handler đã gửi xong response. Nếu lúc đó mới đặt header, nó có thể không được gửi hoặc API có thể ném lỗi tùy state. Vì vậy **`Filter.beforeHandler` mới là vị trí đúng để thiết lập response headers**. `afterHandler` chỉ đọc status và thu metrics.

### 6.6. Vì sao không giữ requestId trong Filter field?

Một `Filter` được dùng cho nhiều requests và có thể chạy trên nhiều threads. Instance field kiểu `String currentRequestId` sẽ bị requests khác ghi đè; handler có thể nhận sai ID. `exchange.setAttribute` là nơi lưu metadata riêng cho request, còn `AtomicInteger` chỉ minh họa ID generation có đồng bộ. Ở production, cần định danh phù hợp trace/correlation policy.

---

## 7. HTTP response lifecycle và xử lý lỗi

### 7.1. Response headers phải có trước `sendResponseHeaders`

~~~text
Filter pre-processing
    │
    ├── exchange.getResponseHeaders().set(...)
    │
    ▼
Handler (hoặc Filter short-circuit)
    │
    ├── exchange.sendResponseHeaders(status, length)
    │
    ├── exchange.getResponseBody().write(...)
    │
    └── close response body/exchange
    │
    ▼
Post-processing chỉ quan sát outcome
~~~

`sendResponseHeaders(int,long)` phải gọi **trước** khi lấy `getResponseBody()`. Khi dùng fixed-length body, phải ghi đúng số bytes hoặc stream có thể báo IOException và connection bị abort. Không thể gửi response thứ hai sau khi đã gửi status headers của response thứ nhất.

### 7.2. Đóng request body

`HttpExchange.close()` kết thúc exchange bằng cách đóng request InputStream và response OutputStream. Nếu response stream đóng trước, request InputStream cũng được đóng nếu chưa đóng. Tuy nhiên, **khuyến nghị consume request body nếu muốn reuse keep-alive connection**; nếu filter từ chối một request có upload lớn thì không nên đọc vô hạn chỉ để reuse connection, hãy áp quota/timeouts và policy abort phù hợp.

### 7.3. Error boundary và `getResponseCode()`

`exchange.getResponseCode()` trả status nếu đã có, hoặc **-1** khi chưa set. Nếu handler throw trước khi send headers, một error-handling filter có thể cân nhắc trả 500 khi an toàn. Nếu headers/body đã gửi một phần, **không cố gửi status 500 lần hai**; đóng exchange, log đã redacted và để client xử lý network/partial-response failure.

### 7.4. `Filter.afterHandler` không phải exception resolver

Một status observer **không tự động biến exception thành HTTP response**. Khi cần xử lý lỗi tập trung, custom filter/error boundary phải định nghĩa:

- Những exception nào được map thành 4xx/5xx.
- Có response headers đã gửi chưa.
- Có được đọc/ghi body không.
- Có giữ/cung cấp error ID không.
- Có bảo toàn IOException và cleanup failures không.
- Tránh logging trùng ở nhiều tầng.

`try/finally` cho metrics là lựa chọn thích hợp trên cả success/error paths, nhưng code trong finally cũng phải không gây lỗi mới.

---

## 8. Vòng đời server và executor

### 8.1. Tại sao cần executor?

`HttpServer.setExecutor(Executor)` quyết định task runner xử lý requests. Nếu không cấu hình, JDK dùng default executor, không tự phù hợp mọi workload. Demo dùng:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);
server.setExecutor(executor);
~~~

Hãy giới hạn concurrency theo CPU/I/O workload, xác định queue capacity/backpressure, timeouts và resource limits. Một `newFixedThreadPool` có queue **không giới hạn theo constructor chuẩn**, nên chỉ giới hạn số threads **chưa đủ để chặn mọi overload**; trong sản phẩm, cân nhắc bounded executor hoặc admission control.

### 8.2. Shutdown đúng

~~~java
try {
    server.start();
    // xử lý hoặc test requests.
} finally {
    server.stop(0);
    executor.shutdown();
}
~~~

`stop(0)` là dừng ngay theo cơ chế server; nếu muốn graceful drain, cần chọn delay/operational protocol phù hợp. Demo có `awaitTermination` và `shutdownNow` fallback. Không dùng một code sample dừng ngay như một bằng chứng đã xử lý graceful shutdown toàn hệ thống.

### 8.3. Auth state và shared instances

Không giữ `HttpExchange`, request body stream, mutable response state hoặc client secrets trong long-lived singleton services. Khi request kết thúc, resources phải được giải phóng. Các filters có thể được share giữa contexts nếu không có per-request mutable fields và dependencies thread-safe.

---

## 9. Bảo mật request/response theo bối cảnh hiện hành

### 9.1. Localhost demonstration không phải production auth

`X-Demo-Key` chứa key hardcoded trong source và được gửi qua HTTP không mã hóa, nhưng server chỉ bind loopback và dùng input giả cho mục đích học tập. **Không triển khai nguyên mã đó ra public interface.**

Với production:

- Dùng **TLS** trực tiếp bằng HttpsServer hoặc trusted reverse proxy/TLS termination có network restrictions.
- Chọn auth scheme được quản lý và reviewed; không so sánh plaintext key hardcoded trong code.
- Secrets cần storage, access controls, rotation, lifecycle và không bị log.
- Authentication không tự thay authorization theo tenant/resource/role.
- Khi dùng shared-secret comparison, cân nhắc timing-safe verification và validation behavior phù hợp threat model.
- Rate limit và request body/headers limits để chống DoS.
- Sử dụng request IDs/trace context an toàn, không tin unvalidated client headers.
- Trả response errors an toàn, không dump stack traces/PII.

### 9.2. CORS và OPTIONS

Nếu browser gọi API cross-origin, cần policy cho **Origin, Access-Control-Allow-Methods, Access-Control-Allow-Headers, credentials và OPTIONS preflight**. Đừng chỉ thêm `Access-Control-Allow-Origin: *` rồi xem đó là authentication. Với requests có credentials, wildcard không phải một lựa chọn thay cho origin allowlist. CORS là kiểm soát browser sharing, **không thay auth**.

### 9.3. Request body limit qua Filter

`HttpExchange.setStreams(InputStream,OutputStream)` cho phép bọc streams để đếm bytes hoặc áp input limit. Nhưng khi triển khai:

- Không đọc toàn bộ body trong filter rồi mong handler đọc lại.
- Chặn bytes thực sự đọc, không chỉ tin `Content-Length` (có chunked encoding).
- Đặt limit cho decompressed data nếu chấp nhận Content-Encoding.
- Dùng timeout/cancellation.
- Đóng streams đúng ownership.
- Không log raw request body chứa secrets.
- Không tự sửa Content-Length/chunked framing bừa bãi.

Đoạn minh họa này không dùng setStreams vì GET requests không có request body; bài tập mở rộng mới cần cài một bounded stream wrapper và kiểm thử riêng.

### 9.4. Không tin route exact match từ prefix

Context `/api/hello` có thể bắt `/api/helloXYZ`; đường dẫn còn có percent encoding, Unicode, proxy rewrites và path normalization. Ứng dụng thật cần quy ước canonical routing thống nhất, hoặc dùng một router/framework phù hợp. Nếu security policy phụ thuộc path, test cả raw path/decoded path dưới các kiểu input không chuẩn.

### 9.5. Health endpoint

`/health` không có API filters trong demo nhằm chứng minh context isolation. Ở production, liveness/readiness có thể được expose cho orchestrator/trusted network; chỉ trả trạng thái tối thiểu, không chứa secrets, backend config hoặc stack traces.

---

## 10. Kiểm thử Filter đúng đắn

### 10.1. Test ma trận hành vi

| Tình huống | Kỳ vọng | Kiểm tra thêm |
| --- | --- | --- |
| GET đúng path có auth | 200 | handler chạy một lần, requestId có |
| GET đúng path thiếu auth | 401 | handler không chạy |
| POST đúng path có auth | 405 | Allow: GET, handler không chạy |
| POST đúng path không auth | 401 theo thứ tự demo | method filter không được gọi |
| GET `/api/hello/extra` có auth | 404 | Context prefix match nhưng exact guard từ chối |
| GET `/health` không auth | 200 | Không có API trace header |
| GET `/API/hello` | Không match context | Case-sensitive match |
| GET `/api/helloXYZ` | Prefix match rồi 404 | Exact path guard |
| GET với Unicode response | 200 | Content-Length đúng bytes |
| Nhiều requests đồng thời | Tách requestId | Không chia sẻ request-local state |
| Inner handler throw IOException | Propagate | Cleanup/metrics policy đúng |
| Client disconnect khi ghi body | I/O error | Không gửi response lần hai |
| Request body quá lớn | Từ chối theo policy | Không OOM |
| Request có header token sai | 401 | Không log token |
| Response đang gửi dở rồi lỗi | Connection/partial outcome | Không thay status đã gửi |

Năm requests đầu tương ứng các tình huống chạy trong demo, các trường hợp còn lại là **đề xuất mở rộng QA**, không phải kết quả đã chạy.

### 10.2. Unit test chain và integration test socket

**Unit test** có thể dùng `Filter.Chain` với handler giả và `HttpExchange` test double để assert số lần gọi chain, short-circuit, attributes và exceptions. Nhưng mock dễ bỏ sót HTTP socket/body lifecycle. **Integration test** dùng loopback `HttpServer` + `HttpClient` như demo xác minh status/headers/response trên JDK implementation thật.

### 10.3. Kiểm tra audit sequence

Request thành công:

~~~text
before → trace-enter → auth-allowed → method-allowed
       → handler → trace-exit → after:200
~~~

Thiếu key:

~~~text
before → trace-enter → auth-denied
       → trace-exit → after:401
~~~

Sai method:

~~~text
before → trace-enter → auth-allowed → method-denied
       → trace-exit → after:405
~~~

Các sequences cho thấy **handler không được gọi** khi filter chặn. Chỉ test status 401 là chưa đủ nếu một handler vẫn âm thầm thực hiện side effect do code lọt qua.

### 10.4. Kiểm thử lỗi và leak

Thử tạo các tình huống:

- Handler ném IOException trước headers, kiểm tra trace cleanup.
- Handler throw sau headers, không thể gửi response mới.
- OutputStream fail giữa chừng.
- Client hủy kết nối hoặc timeout.
- API key bị lặp headers/độ dài quá lớn.
- Concurrent requests, long-running handler.
- Server stop khi requests đang active.
- POST với body rất lớn nhưng auth chặn.
- Provider/OS không thể bind port.
- Filter lỡ nuốt IOException.
- Context mới quên gắn auth filter.

**Không dùng các bài test gây disk-full hoặc tấn công DoS trên production**; dùng môi trường test cô lập.

---

## 11. Lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| Copy auth/tracing vào mọi handler | Không nhất quán, dễ quên | Shared Filter |
| Custom filter chặn nhưng gọi chain | Handler vẫn chạy, side effects | `respond` + `return` |
| Custom filter không gọi chain và không trả response | Client treo/timeout | Short-circuit phải hoàn tất exchange |
| Gọi chain hai lần | Duplicate execution/response | Gọi một lần khi cho phép |
| Đổi header trong afterHandler | Headers có thể đã gửi | Set trong beforeHandler/pre-processing |
| Coi afterHandler là finally toàn năng | Bỏ sót exceptional path | Custom Filter `try/finally` |
| Catch IOException rồi bỏ qua | Che I/O error | Propagate theo contract |
| Lưu requestId trong field dùng chung | Data race | Exchange attribute/local |
| Tưởng context filters là global | Route khác bỏ qua auth | Audit per-context |
| Thay danh sách filters sau start | Rủi ro concurrency | Config trước start |
| Nhầm context prefix với exact route | URI ngoài dự kiến vẫn vào handler | Exact/canonical path validation |
| Truyền String.length làm Content-Length | Unicode bytes bị tính sai | `payload.getBytes(UTF_8).length` |
| Không đóng response body/exchange | Resource leak | Close ở success/failure |
| Gửi response status lần hai | IOException/connection abort | Xem response started state |
| Gửi plaintext demo API key qua public network | Lộ credential | TLS và auth scheme thực |
| Tin request header `X-User` là identity | Authentication bypass | Verify trước khi đặt principal |
| Log Authorization/cookie/token/body | Lộ secrets/PII | Redact, logging policy |
| Không giới hạn body/thread queue | DoS/heap pressure | Quotas + bounded concurrency |
| Xử lý business validation hoàn toàn trong Filter | Rối trách nhiệm, khó test | Domain service |
| Health công khai thông tin hệ thống | Information disclosure | Minimal liveness/readiness |
| Test chỉ status codes | Handler có thể vẫn chạy | Kiểm tra chain invocation/audit |
| Chỉ dùng demo loopback để khẳng định production security | Thiếu TLS/limits/edge cases | Security reviews + integration tests |

---

## 12. Bài tập tự luyện

1. Chạy chương trình, giải thích vì sao `requestsWithTrace=4` dù có 5 requests.
2. Giải thích vì sao `unauthorized` vẫn có `X-Request-Id`.
3. Đổi thứ tự `DemoAuthFilter` và `GetOnlyFilter`, dự đoán POST không có key trả status nào.
4. Chuyển `beforeHandler` sau auth filter, xem response 401 có `X-Mode` không.
5. Đăng ký hai `afterHandler` rồi kiểm tra thứ tự post operations ngược nhau.
6. Thêm custom `TimingFilter` dùng System.nanoTime, ghi cả khi inner chain ném IOException.
7. Thêm một filter gắn `Cache-Control: no-store` cho endpoint nhạy cảm.
8. Thêm `/api/orders` và sử dụng lại tracing/auth/method policy không copy code handler.
9. Tạo test để phát hiện `/api/orders` quên gắn auth filter.
10. Test GET `/api/helloXYZ` để hiểu longest-prefix matching.
11. Thêm một response tiếng Việt/emoji và xác minh `bytes.length` khác String.length.
12. Thay `CopyOnWriteArrayList` bằng metrics aggregator phù hợp throughput cao.
13. Thay `AtomicInteger` bằng UUID hoặc trace ID policy có uniqueness giữa nhiều instances.
14. Tách authentication và resource-level authorization bằng principal trong exchange attribute.
15. Viết một `Filter` chặn thiếu `Content-Type` theo API contract.
16. Thử `Filter.adaptRequest` với một header vô hại, giải thích sự khác nhau với attributes.
17. Thử `Filter.setStreams` để đếm input bytes và reject khi vượt quota.
18. Viết một bounded concurrency executor policy và mô tả behavior khi overload.
19. Thêm một OPTIONS preflight test với origin allowlist.
20. Test malformed headers và duplicate credentials.
21. Mô phỏng client disconnect và kiểm tra IOException propagation.
22. Mô phỏng handler throw sau khi đã send headers; không gửi 500 lần hai.
23. Kiểm tra response body/HttpExchange được đóng khi filter short-circuit.
24. Thêm audit correlation ID nhưng không log secrets/PII.
25. Thêm graceful shutdown và test khi nhiều active exchanges.
26. Xây ma trận acceptance gồm 200/401/403/404/405, route, method và authorization.
27. So sánh `HttpServer` với một framework chuyên dụng khi cần HTTP/2, TLS, routing và operational controls.

---

## 13. Checklist trước production

- [ ] `jdk.httpserver` là module hiện hành, không nhầm với Servlet Filter.
- [ ] Filter dành cho cross-cutting concerns, handler/service dành cho nghiệp vụ.
- [ ] Mỗi context phải có danh sách filters đúng policy.
- [ ] Thứ tự filters được kiểm thử: pre → handler → post.
- [ ] Khi cho phép, custom filter gọi chain đúng một lần.
- [ ] Khi từ chối, filter không gọi chain và tự gửi response/close.
- [ ] beforeHandler dùng trước response; afterHandler chủ yếu quan sát.
- [ ] Dùng try/finally để quan sát exception paths, không nuốt IOException.
- [ ] Không tạo request-local state trong mutable instance fields.
- [ ] Nếu tái dùng Filter giữa contexts, xác nhận thread safety.
- [ ] Đăng ký filters trước `server.start()`.
- [ ] Context longest-prefix matching được hiểu đúng.
- [ ] Exact path, normalization/encoding policy rõ ràng.
- [ ] Request method validation, `Allow` header và OPTIONS/HEAD đúng contract.
- [ ] Response headers được thiết lập trước sendResponseHeaders.
- [ ] Fixed response length dùng **UTF-8 bytes**, không dùng String.length.
- [ ] Đóng OutputStream/InputStream/HttpExchange theo lifecycle.
- [ ] Không gửi response headers lần thứ hai sau khi đã bắt đầu.
- [ ] Authn/authz độc lập và không tin raw client identity headers.
- [ ] API internet-facing có TLS/trusted proxy, credential storage/rotation.
- [ ] Không log secrets/raw credentials/PII.
- [ ] CORS/preflight đúng origin/credential policy.
- [ ] Giới hạn body/header sizes, concurrency, executor queues và timeouts.
- [ ] Audit/metrics không high-cardinality theo raw URI hoặc user IDs.
- [ ] Health endpoints không công bố sensitive diagnostics.
- [ ] Test short-circuit bảo đảm handler không chạy.
- [ ] Test IOException, client disconnect, response-started và cleanup.
- [ ] Shutdown có drain/timeout theo operational requirements.
- [ ] Không suy demo local-only là production-ready.

## Kết luận

**Filter trong `com.sun.net.httpserver`** cho phép tách logic dùng chung khỏi handlers bằng một **chain có thứ tự** được cấu hình trên từng `HttpContext`. `chain.doFilter(exchange)` điều khiển việc đi tiếp: gọi khi request hợp lệ; bỏ qua và **trả response ngay** khi filter phải chặn. `Filter.beforeHandler` thích hợp cho pre-processing đơn giản; `Filter.afterHandler` phù hợp để đọc status sau khi xử lý; custom Filter cần thiết cho short-circuit, streams và try/finally.

Hãy lưu request-specific metadata trong `HttpExchange` attributes, không trong mutable shared fields. Khi ghi HTTP response, hãy đếm bytes đúng và đóng exchange. Context matching là prefix, vì vậy cần route validation bổ sung nếu nghiệp vụ yêu cầu exact path. Ví dụ Java 17+ trong bài đã chạy thực tế với các kết quả 200/401/405/404 và audit xác nhận thứ tự chain; khi dùng production cần **TLS/auth, authorization, input limits, observability, exception handling và resource lifecycle** chặt chẽ.

**Tài liệu chính thức còn áp dụng:**

- [Filter — Java SE 26 (Chain, beforeHandler, afterHandler, adaptRequest)](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html)
- [Filter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html)
- [Filter.Chain — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.Chain.html)
- [HttpServer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [HttpContext — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html)
- [HttpExchange — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html)
- [HttpExchange — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html)
- [HttpHandler — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html)
- [jdk.httpserver module — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/module-summary.html)
- [HttpClient — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)