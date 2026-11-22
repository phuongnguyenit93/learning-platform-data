# Đánh giá giới hạn API trước khi chọn máy chủ cho một ứng dụng — HTTP server của JDK (Java 17+)

Java 17 có sẵn module `jdk.httpserver` với `com.sun.net.httpserver.HttpServer` và `HttpsServer`. Đây là **API HTTP server nhúng, gọn, hữu ích cho thử nghiệm, ứng dụng nhỏ hoặc thành phần nội bộ có phạm vi và biện pháp bảo vệ rõ ràng**. Nó cho phép đăng ký `HttpHandler` theo đường dẫn, đọc request bằng `HttpExchange`, trả response, gắn `Filter`, `Authenticator`, cung cấp `Executor` và dùng TLS qua `HttpsServer`.

Tuy nhiên, **“JDK có HTTP server” không đồng nghĩa “JDK đã cung cấp một web application server đầy đủ tính năng”**. Trước khi chọn làm public-facing service, phải đánh giá nhu cầu thực tế về routing, HTTP version, TLS/connection handling, concurrent requests, middleware, authentication, input limits, metrics, graceful shutdown, khả năng mở rộng, vận hành và đội ngũ chịu trách nhiệm bảo trì. Một số tính năng có thể **tự triển khai bên trên API**, nhưng đó là **chi phí và rủi ro do ứng dụng sở hữu**; không phải tính năng production sẵn có mặc định.

Bài Knowledge thuộc mục **HTTP server của JDK** trong **Java Advance - networking**. Mục tiêu là xây một cách **ra quyết định có bằng chứng**: khi nào nên dùng `HttpServer`, khi nào cần thêm reverse proxy hoặc server/framework khác, cùng cách thử trực tiếp trên Java 17+ để phát hiện hai giới hạn dễ bỏ qua: **routing so khớp prefix theo chữ** và **executor là tài nguyên cần thiết kế rõ**.

## 1. Đầu tiên: phân biệt API, implementation, hệ sinh thái và trách nhiệm

Khi đánh giá máy chủ, hãy tách bốn lớp:

1. **API mà JDK hứa cung cấp:** `HttpServer`, `HttpsServer`, `HttpContext`, `HttpHandler`, `HttpExchange`, `Filter`, `Authenticator` và một số thao tác lifecycle. Đây là contract lập trình đã mô tả trong Java SE 17 Javadoc.
2. **Implementation/provider đang chạy:** `HttpServer.create(...)` lấy implementation từ `HttpServerProvider`. Default JDK implementation có hành vi cụ thể, nhưng các chi tiết chưa được API bảo đảm không nên được đưa thành giả định nghiệp vụ.
3. **Cơ sở hạ tầng triển khai:** reverse proxy, ingress, load balancer, TLS termination, WAF, rate limiting, DNS, container, service mesh, health checks và telemetry có thể bổ sung khả năng **bên ngoài Java server**.
4. **Code ứng dụng phải viết:** routing có tham số, authz, DTO/JSON validation, giới hạn body, transaction, exception mapping, structured logging, graceful draining, bảo vệ secrets, tests và nâng cấp.

Một hệ thống có reverse proxy tốt vẫn có thể gặp lỗi SQL injection hoặc thiếu authorization trong `HttpHandler`. Ngược lại, một dịch vụ nhỏ hoàn toàn nội bộ có thể không cần bộ framework nặng nếu requirements đơn giản và được kiểm soát.

**Kết luận đánh giá không nên chỉ là “server A nhanh hơn server B”**. Quyết định phải tính **chi phí sở hữu các lớp còn thiếu**, mức rủi ro của dữ liệu, số request đồng thời, kỹ năng nhóm và yêu cầu vận hành lâu dài.

## 2. Những gì Java 17 thực sự có trong module jdk.httpserver

| Thành phần | Có sẵn trong JDK 17 | Vai trò |
| --- | --- | --- |
| `HttpServer` | Có | Bind địa chỉ/port, nhận kết nối HTTP, phân phối exchange |
| `HttpsServer` | Có | HTTP server với TLS thông qua `HttpsConfigurator` và `SSLContext` |
| `HttpHandler` | Có | Callback xử lý request và response |
| `HttpContext` | Có | Ánh xạ **prefix đường dẫn** tới handler, giữ filters/authenticator |
| `HttpExchange` | Có | Request method, URI, headers, request body stream, response body/status |
| `Filter` | Có | Tiền/hậu xử lý exchange theo chain |
| `Authenticator`, `BasicAuthenticator` | Có | Framework xác thực tối giản; không phải hệ thống RBAC/OIDC đầy đủ |
| `setExecutor(Executor)` | Có | Giao xử lý request tasks cho executor do ứng dụng lựa chọn |
| `start()` / `stop(int)` | Có | Vòng đời đơn giản |
| JSON model binding, database, OAuth2/OIDC, WebSocket server, HTTP/2 application API | Không phải tính năng đóng gói như một web framework trong module này | Cần ứng dụng, thư viện hoặc server khác tùy requirements |

Trang package chính thức mô tả một **simple high-level HTTP server API**, cung cấp **partial implementation** của HTTP/1.1 và HTTPS/TLS, không phải tuyên bố tương thích mọi biến thể protocol hay sẵn toàn bộ chức năng web application.

Lưu ý tên package `com.sun.net.httpserver` **không khiến nó thành internal API bị cấm** trong phạm vi JDK module này: package được `jdk.httpserver` export công khai. Nhưng nó là **JDK-specific module**, nên cần kiểm tra runtime distribution, module graph và compatibility với môi trường deploy, không suy rằng mọi JRE tùy biến đều chứa `jdk.httpserver`.

## 3. Chọn theo yêu cầu: câu hỏi trước khi viết server

Trước khi bàn về code, viết một danh sách yêu cầu có thể đo:

- **Traffic:** requests/second kỳ vọng, burst, số kết nối đồng thời, p95/p99 latency, payload sizes và thời gian giữ request.
- **Protocol:** chỉ HTTP/1.1 JSON nhỏ, hay cần HTTP/2, WebSocket, server push/event streams, streaming upload lớn, reverse proxy upgrade?
- **Bảo mật:** public Internet hay loopback/private network, mật khẩu/token, TLS/mTLS, CORS, CSRF, identity provider, audit, rate limiting, tenant isolation?
- **Resource protection:** max headers/body, request timeout, idle timeout, hạn mức CPU/RAM/threads, queue bounds, slow clients, admission control?
- **Framework services:** routing có path variables/middleware, validation, serialization, compression, content negotiation, sessions, exception handling?
- **Observability:** access log cấu trúc, trace propagation, metrics, health/readiness, correlation ID, error budgets, incident runbooks?
- **Lifecycle:** hot deploy/config reload, graceful shutdown, draining trước khi dừng, zero-downtime release, compatibility khi nâng Java?
- **Ownership:** ai kiểm chứng TLS cấu hình, lọc request bất thường, concurrency bugs, HTTP compliance và cập nhật thư viện?

Kết quả đánh giá phải có tiêu chí **PASS / FAIL / NEEDS MITIGATION** cùng người sở hữu và cách test, không chỉ trả lời “API có class này nên đủ”.

## 4. Mô hình tối giản và ranh giới trách nhiệm

Mô hình xử lý cơ bản:

```text
Incoming TCP connection
         |
         v
HttpServer / HttpsServer
         |
         | Longest literal path prefix match
         v
HttpContext
         |
         +-- optional Authenticator
         +-- Filter chain (before/after)
         |
         v
HttpHandler.handle(HttpExchange)
         |
         +-- method / URI / request headers / request body
         +-- app validation & business logic
         +-- response status / headers / response body
         |
         v
Exchange closed / underlying connection managed by provider
```

`HttpExchange` là **một lần trao đổi request–response**, không phải Servlet request object, không phải WebSocket session và không có sẵn transaction scope. `HttpHandler.handle` có thể đọc body thành bytes hoặc xử lý stream; việc parse JSON, kiểm tra payload và ánh xạ lỗi ra HTTP status là do code handler hoặc lớp ứng dụng bên trên đảm nhiệm.

**Có thể tạo một HTTP endpoint bằng vài chục dòng**; nhưng một endpoint vận hành ngoài Internet cần số lượng concerns lớn hơn nhiều. Không nên sử dụng **độ ngắn của demo Hello World** làm bằng chứng đủ production.

## 5. Giới hạn routing: longest literal prefix, không phải REST router đầy đủ

JDK `HttpServer` tìm context có **prefix dài nhất khớp đường dẫn request**. Việc so khớp **literal, case-sensitive**, không tự biến chuỗi path thành template hay tự chuẩn hóa encoded forms để hiểu business routes.

Ví dụ:

```java
// Snippet trong setup HttpServer; hai handlers đã được khai báo.
server.createContext("/api/", apiHandler);
server.createContext("/api/admin/", adminHandler);
```

Các đường dẫn:

| Request path | Context được chọn | Điều cần hiểu |
| --- | --- | --- |
| `/api/items` | `/api/` | Prefix bình thường |
| `/api/admin/status` | `/api/admin/` | Prefix dài hơn thắng |
| `/api/Admin/status` | `/api/` | Case-sensitive: không khớp admin |
| `/unknown` | Không có context | Server có thể trả 404 |
| `/v123` khi đăng ký `"/v1"` | `/v1` | **Khớp prefix ngoài ý muốn** |

**Cảnh báo quan trọng từ Java 17 Javadoc:** context `"/foo"` có thể khớp cả `"/foobar"` và `"/foo/bar"`. Nếu định nghĩa route phân cấp, thường dùng dấu `/` cuối prefix và vẫn phải xác thực path cuối cùng trong handler.

Không có sẵn cơ chế `@GetMapping("/users/{id}")`, method-aware routing hoặc route constraint theo content type. Muốn REST router đúng nghĩa, phải tự viết, thêm thư viện, hoặc chọn framework/server có routing semantics đã kiểm chứng.

Vấn đề path encoding cần kiểm thử riêng: `getRequestURI().getPath()` và `getRawPath()` có semantics khác; tuyệt đối không dùng string prefix naïve làm boundary an ninh cho file paths/tenant IDs.

## 6. HTTP method và status: context không thay application validation

`createContext("/api/", handler)` không tự hạn chế method chỉ là GET. Handler cần xét `exchange.getRequestMethod()` và trả status đúng khi method không được hỗ trợ:

```java
// Snippet minh họa, đặt trong handler có send(...) và imports.
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");
    send(exchange, 405, "Method Not Allowed");
    return;
}
```

Nếu nhận `POST` trên một route GET-only, trả **405** và `Allow` thích hợp, không mặc định gọi code đọc database. Nếu URI không được ánh xạ thì **404** có thể xuất hiện từ server core; **403** và **401** theo auth/authz policy; **400** khi query/body không hợp lệ; **413** khi vượt body size policy; **415** khi content type không chấp nhận.

Không dựng REST API chỉ bằng `getRequestURI().toString().contains(...)` hoặc tin rằng prefix routing tự gắn identity/permissions. Phải validate method, path, percent encoding, query, headers và content type theo contract.

Việc phân biệt `HEAD`/`OPTIONS`, 304/204 không body, content negotiation và conditional requests là phần ứng dụng phải xử lý hoặc chủ động thiết kế. Nên có regression tests cho từng method và status.

## 7. Vòng đời HttpExchange: thứ tự thao tác không tùy ý

Theo Java SE 17 Javadoc, vòng đời thông thường:

1. Đọc `getRequestMethod()`, `getRequestURI()` và `getRequestHeaders()`.
2. Đọc `getRequestBody()` vào parser/stream và **đóng input**; kiểm soát tối đa bytes.
3. Thiết lập response headers bằng `getResponseHeaders()`.
4. Gọi **`sendResponseHeaders(status, responseLength)`** trước khi ghi body.
5. Gọi `getResponseBody()`, ghi **đúng định dạng/số bytes**, và **đóng output**.
6. Bảo đảm `HttpExchange` được kết thúc trong cả đường lỗi/return sớm.

`HttpExchange` thực hiện `AutoCloseable`, vì vậy có thể dùng:

```java
// Snippet: exchange là tham số HttpHandler.handle.
try (exchange) {
    byte[] body = "OK".getBytes(StandardCharsets.UTF_8);
    exchange.getResponseHeaders()
            .set("Content-Type", "text/plain; charset=UTF-8");
    exchange.sendResponseHeaders(200, body.length);
    try (OutputStream out = exchange.getResponseBody()) {
        out.write(body);
    }
}
```

Đóng response output cũng đóng request input khi chưa đóng. Nhưng **đọc hết request body trước khi đóng** được khuyến nghị để có cơ hội tái sử dụng TCP connection; đóng khi còn dữ liệu có thể khiến kết nối không thể dùng cho exchange tiếp.

Sai thứ tự hoặc quên close có thể gây rò resource, treo client hoặc khiến connection phải đóng. Đây là bài toán ownership, không phải chỉ là style code.

## 8. Response length: >0, 0 và -1 có ý nghĩa khác nhau

Một khác biệt dễ gây bug khi server trả response:

| `sendResponseHeaders(status, length)` | Ý nghĩa Java 17 | Hệ quả |
| --- | --- | --- |
| `length > 0` | Chính xác **length bytes** | Phải write **đúng** số byte, dư/thiếu đều gây IOException/abort |
| `length == 0` | Sử dụng **chunked transfer encoding** | Không có nghĩa “0 bytes” hay “body rỗng chắc chắn” |
| `length == -1` | Không gửi response body | Thích hợp `204 No Content` hoặc response không có body |

Ví dụ: nếu muốn trả text UTF-8, hãy tính độ dài sau encode:

```java
String message = "Xin chào";
byte[] body = message.getBytes(StandardCharsets.UTF_8);
exchange.sendResponseHeaders(200, body.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(body);
}
```

Không dùng `message.length()` vì Java String length là UTF-16 code units, còn HTTP response length tính **bytes**. Nếu ghi ít hơn fixed length, `OutputStream.close()` có thể ném `IOException`; nếu ghi nhiều hơn, `write` có thể ném `IOException`.

Đừng trả `sendResponseHeaders(204, 0)` để biểu diễn “không body”; theo contract `0` là chunked. Với 204, 304, HEAD, phải xét semantics chuẩn HTTP và đặc thù API. Ví dụ số 2 dùng `204, -1` và xác nhận client đọc body rỗng.

## 9. Concurrency: vì sao default executor rất dễ bị hiểu nhầm?

`HttpServer.setExecutor(Executor)` phải được gọi **trước** `start()`. Javadoc Java 17 nêu: nếu không set hoặc set `null`, default implementation sử dụng thread được tạo bởi `start()` để xử lý HTTP tasks. Vì vậy **không nên mặc định tin rằng có thread pool phục vụ concurrency tốt**.

```java
// Snippet minh họa, đã tạo server.
ExecutorService workers = Executors.newFixedThreadPool(4);
server.setExecutor(workers);   // Trước start()
server.start();                // Sau đó mới nhận request
```

Một handler chạy `Thread.sleep()`, query DB chậm hoặc đọc socket chậm có thể chiếm worker và làm ảnh hưởng request khác. Đây là **blocking server API**: chỉ tăng số threads chưa chắc đủ nếu phần mềm không có backpressure.

**Bẫy thứ hai:** `Executors.newFixedThreadPool(4)` có **queue không giới hạn theo thiết kế của factory**. Bốn worker giới hạn số task đang chạy đồng thời, nhưng hàng nghìn requests/tasks còn lại có thể chờ trong queue và gây memory/latency pressure. Ví dụ kiểm thử dùng fixed pool để dễ hiểu; production cần **giới hạn cả active tasks, queued tasks và request body size**.

## 10. Backlog không phải thread pool, queue request hay rate limiter

`HttpServer.create(address, backlog)` nhận tham số `backlog` của TCP listening socket. Nó biểu diễn **số kết nối đang đợi accept** mà hệ thống có thể queue ở lớp TCP. Nếu hết quota, TCP implementation có thể từ chối hoặc bỏ qua kết nối mới.

```text
INCOMING CLIENTS
      |
      v
TCP listening socket backlog (connections waiting accept)
      |
      v
HttpServer accepts connections
      |
      v
Executor tasks and queue (application request handling)
      |
      v
Handler / downstream DB / response
```

Chúng là những tài nguyên **khác nhau**:

- **Backlog:** giới hạn accept queue ở OS, không đo số HTTP requests hoàn thành.
- **Executor pool size:** giới hạn số tasks có thể xử lý đồng thời trong pool loại fixed.
- **Executor queue:** số tasks chờ; có thể không giới hạn nếu chọn factory không phù hợp.
- **HTTP connections:** có thể giữ keep-alive và chứa nhiều exchanges theo thời gian.
- **Downstream DB pool:** lại là quota độc lập; 100 HTTP workers không có nghĩa DB chịu 100 queries chạy song song.

`backlog <= 0` dùng giá trị mặc định của hệ thống theo Javadoc, **không** phải “không giới hạn”. Tune các giới hạn bằng load test và quan sát error rate/latency, không dựa vào một con số đơn lẻ.

## 11. Slow clients, body streaming và các hạn mức còn phải tự sở hữu

Với `HttpExchange.getRequestBody()`, request input là một `InputStream`. Nếu handler dùng `readAllBytes()` cho nội dung từ Internet mà không giới hạn, client có thể buộc server giữ memory lớn. Nếu handler chờ người gửi rất chậm, worker có thể bị giữ lâu.

Một vòng đọc có quota minh họa:

```java
// Snippet: input là InputStream; maxBytes > 0 do ứng dụng cấu hình.
long consumed = 0L;
byte[] buffer = new byte[8192];
int count;
while ((count = input.read(buffer)) != -1) {
    if (count > maxBytes - consumed) {
        throw new IOException("Request body too large");
    }
    consumed += count;
    // Parse/stream tiếp vào sink có trần, tránh giữ mọi buffer.
}
```

Đây không phải class độc lập. Thêm kiểm tra `Content-Length` chỉ là preflight tối ưu; **không thay quota thực đo** vì metadata có thể thiếu/không đáng tin, request có thể chunked hoặc connection bị cắt.

Cần yêu cầu cụ thể về **max request bytes, max header sizes, số kết nối, input rate, idle timeout, total deadline, upload duration, response output queue, rejection policy**. Một số implementation có thiết lập nội bộ hoặc network properties, nhưng **không nên xem chúng là API ứng dụng thống nhất** của `HttpServer` để áp chính sách phức tạp cho từng endpoint. Nếu thiếu knob chuẩn, cần reverse proxy có bảo vệ đầu vào hoặc chọn server/framework khác.

## 12. Filter có sẵn, nhưng middleware production không “miễn phí”

`HttpContext.getFilters()` cho phép thêm `Filter` để pre/post-process. Một filter có thể:

- Đọc header và validate một điều kiện đơn giản.
- Đặt attribute bằng `exchange.setAttribute` cho handler.
- Gọi `chain.doFilter(exchange)` để cho request đi tiếp.
- Từ chối và trực tiếp trả response mà **không gọi chain**.
- Đo thời gian, gắn correlation ID, hoặc bọc request/response streams qua `setStreams`.

Ví dụ:

```java
// Snippet: đặt trong Filter#doFilter(HttpExchange e, Chain chain).
String key = e.getRequestHeaders().getFirst("X-Demo-Key");
if (!"demo-key".equals(key)) {
    sendUnauthorizedAndClose(e);
    return;              // Không chạy handler.
}
chain.doFilter(e);        // Cho phép xử lý tiếp.
```

`sendUnauthorizedAndClose` là hàm minh họa không khai báo, **không phải chương trình standalone**. Demo số 1 có phiên bản filter đầy đủ chạy được.

**Giới hạn:** `Filter` là building block, không tự cung cấp hệ thống authentication tokens, structured audit, retry/circuit breaker, CSRF protection, per-route security policy, API versioning hay standardized error mapper. Nếu tự viết chuỗi filters phức tạp, phải kiểm thử **thứ tự thực thi, exception paths, cleanup, thread safety và propagation của attributes**.

## 13. Authentication không đồng nghĩa authorization

Trong `HttpContext` có `setAuthenticator(Authenticator)`; Java 17 cũng có `BasicAuthenticator` để kiểm tra HTTP Basic username/password bằng logic do ứng dụng cung cấp. Đây là **công cụ xác thực cơ bản**, không phải đầy đủ OAuth2/OIDC/SAML, JWT verification, sessions, CSRF policy và tenant RBAC.

Hãy phân tách:

1. **Authentication:** request thuộc principal nào? Token/session/certificate có hợp lệ không?
2. **Authorization:** principal đó có quyền đọc/sửa **resource cụ thể** không? Kiểm tra theo tenant, owner và business rule.
3. **Transport protection:** Basic credentials hoặc bearer tokens không được gửi qua HTTP công khai; dùng TLS với `HttpsServer` hoặc proxy TLS được kiểm soát.
4. **Input validation:** ngay cả authenticated client vẫn có thể gửi path traversal, JSON không hợp lệ hoặc payload quá lớn.
5. **Audit:** ai đã làm gì, operation ID và kết quả ra sao; không log password/token.

Demo dùng `X-Demo-Key: demo-key` để hiển thị filter flow. **Đó không phải cơ chế xác thực production**: key hardcoded, không chống lộ/replay, không quản lý vòng đời credential và chưa có authorization theo tài nguyên.

Nếu hệ thống cần login/session/role/tenant phức tạp, chi phí tự xây trên `HttpHandler` thường cao hơn dùng một framework có middleware/auth integration được kiểm chứng.

## 14. HTTPS có sẵn nhưng phải cấu hình TLS thật

`HttpsServer` là subclass của `HttpServer` và hỗ trợ HTTPS qua `HttpsConfigurator` dùng `SSLContext` đã khởi tạo. Điều đó có nghĩa JDK **có khả năng chạy HTTP qua TLS**, không phải “thiếu HTTPS”.

Luồng cấu hình:

```java
// Snippet minh họa, context/keyStore và imports cần chuẩn bị.
SSLContext ssl = SSLContext.getInstance("TLS");
ssl.init(keyManagerFactory.getKeyManagers(),
         trustManagers, new SecureRandom());

HttpsServer https = HttpsServer.create(
        new InetSocketAddress("127.0.0.1", 8443), 0);
https.setHttpsConfigurator(new HttpsConfigurator(ssl));
https.createContext("/health", handler);
https.setExecutor(workers);
https.start();
```

Đây **không phải chương trình độc lập**; `keyManagerFactory`, `trustManagers`, `handler`, `workers` chưa được tạo. Các yêu cầu production còn gồm:

- Private key/certificate chain hợp lệ và certificate phù hợp hostname; rotate secrets/certificates.
- TLS protocol/cipher policy, truststore, mTLS client certificates khi cần và kiểm thử endpoint identity.
- Khả năng TLS termination ở reverse proxy; nội bộ sau proxy vẫn cần threat model rõ.
- Nếu có nhiều host/domains, certificate/SNI và routing/ingress phải được thiết kế theo deployment.
- Không tắt TLS verification để “fix nhanh” chứng chỉ; không log secrets/private key.

**Có HTTPS không đồng nghĩa server đã hỗ trợ HTTP/2, ALPN policies hoặc web gateway toàn diện**. Xem documentation của đúng JDK/provider và kiểm chứng traffic qua proxy/certs.

## 15. Giao thức: HTTP/1.1 cơ bản, không tự có WebSocket server hay HTTP/2 feature stack

Tài liệu package Java 17 mô tả một triển khai **một phần HTTP/1.1** và HTTP over TLS. API này **không cung cấp các contract/application abstractions** tương đương full HTTP/2 server, WebSocket server framework, servlet container hay reactive nonblocking runtime.

| Yêu cầu | Đánh giá với Java 17 `jdk.httpserver` |
| --- | --- |
| GET/POST HTTP/1.1 cơ bản | Phù hợp sau khi thêm handler và validation |
| HTTPS | Có `HttpsServer`, cần `SSLContext`/certificate policy |
| HTTP/2 multiplexing/gRPC server | Không phải năng lực ứng dụng được API này cung cấp |
| WebSocket upgrade với sessions/frames | Không có WebSocket server abstraction trong API |
| Server-Sent Events | Có thể tự stream text/chunked trong HTTP, nhưng vẫn cần lifecycle/backpressure/timeout/proxy policies |
| Multipart upload | Không có parser/framework multipart tự động; thêm library hoặc tự xây có bounds |
| Static file hosting/cache/range/ETag | Có thể lập trình, không mặc định như full web server |
| Routing theo regex/path variable/REST annotations | Không có sẵn; context prefix literal |
| Response compression/content negotiation | Phải triển khai hoặc đưa sang proxy/framework |

Không kết luận “mọi JDK distribution tuyệt đối không thể chạy HTTP/2”: provider hoặc một tầng **khác** có thể bổ sung khả năng. Điều chắc chắn cho **API đang đánh giá** là không nên lập kế hoạch sản phẩm dựa vào các tính năng mà Java 17 `HttpServer` **không cam kết**.

Nếu sản phẩm đòi WebSocket/gRPC/HTTP2 server là core feature, thường nên **chọn server/framework chuyên dụng thay vì tự tái tạo giao thức** từ TCP/HttpExchange.

## 16. Reverse proxy giúp nhiều, nhưng không sửa được lỗi handler

Một kiến trúc có thể dùng:

```text
Internet users
      |
      v
Ingress / Reverse proxy / WAF
 - TLS termination
 - header/body limits
 - HTTP/2 where applicable
 - rate limit / traffic routing
 - access logs / health probes
      |
      v
Private network boundary
      |
      v
Java 17 HttpServer (bind internal address)
 - HttpContext routing
 - Filter authentication/authorization
 - bounded executor and request quotas
 - business logic and DB
```

Proxy có thể giảm bề mặt tấn công và bổ sung chức năng. Tuy nhiên:

- **Không tự động bảo đảm** handler không OOM/SQL-injection/path traversal.
- Header như `X-Forwarded-For`/`X-Forwarded-Proto` phải được tin **chỉ từ proxy được cấu hình**; client bên ngoài có thể tự gửi header giả.
- Proxy timeout có thể khiến client disconnect nhưng server vẫn xử lý; với POST có side effects cần idempotency/status reconciliation.
- Proxy rate limit có thể dựa trên account/IP; vẫn cần business quotas và per-tenant authorization ở ứng dụng.
- Nếu proxy terminate TLS mà kết nối tới app HTTP plaintext, chỉ nên chấp nhận theo network/security boundary đã duyệt.
- Mọi session/authn ở proxy cần đảm bảo thông tin identity truyền tới backend **không giả mạo được**.

Vì vậy, đặt proxy không khiến `HttpServer` tự trở thành một server enterprise với đầy đủ guarantees.

## 17. Ví dụ Java 17+ số 1 — routing, filter và status codes thực tế

Tệp **`JdkHttpServerRoutesDemo.java`** dựng `HttpServer` trên **loopback 127.0.0.1** và port được OS cấp, thêm hai contexts `/api/` và `/api/admin/`. Context admin có một `Filter` từ chối request thiếu `X-Demo-Key`; route public tự kiểm tra method GET. Client `java.net.http.HttpClient` gửi năm request bằng HTTP thực để xác minh hành vi.

```java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class JdkHttpServerRoutesDemo {
    private static void reply(HttpExchange exchange, int code,
                              String value) throws IOException {
        try (exchange) {
            byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(code, bytes.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(bytes);
            }
        }
    }

    private static HttpRequest get(URI uri) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5)).GET().build();
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);

        server.createContext("/api/", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())) {
                exchange.getResponseHeaders().set("Allow", "GET");
                reply(exchange, 405, "METHOD");
                return;
            }
            reply(exchange, 200, "PUBLIC");
        });

        HttpContext admin = server.createContext("/api/admin/",
                exchange -> reply(exchange, 200, "ADMIN"));
        admin.getFilters().add(new Filter() {
            @Override
            public String description() {
                return "Demonstration authorization gate";
            }

            @Override
            public void doFilter(HttpExchange exchange, Chain next)
                    throws IOException {
                if (!"demo-key".equals(exchange.getRequestHeaders()
                        .getFirst("X-Demo-Key"))) {
                    reply(exchange, 401, "DENIED");
                    return;
                }
                next.doFilter(exchange);
            }
        });

        server.setExecutor(workers);
        server.start();
        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newHttpClient();
            HttpResponse<String> publicRoute = client.send(
                    get(URI.create(base + "/api/items")),
                    HttpResponse.BodyHandlers.ofString());
            HttpResponse<String> blocked = client.send(
                    get(URI.create(base + "/api/admin/status")),
                    HttpResponse.BodyHandlers.ofString());
            HttpRequest allowed = HttpRequest.newBuilder(
                    URI.create(base + "/api/admin/status"))
                    .header("X-Demo-Key", "demo-key")
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<String> adminRoute = client.send(
                    allowed, HttpResponse.BodyHandlers.ofString());
            HttpResponse<Void> method = client.send(
                    HttpRequest.newBuilder(
                            URI.create(base + "/api/items"))
                            .timeout(Duration.ofSeconds(5))
                            .POST(HttpRequest.BodyPublishers.noBody())
                            .build(),
                    HttpResponse.BodyHandlers.discarding());
            HttpResponse<Void> missing = client.send(
                    get(URI.create(base + "/missing")),
                    HttpResponse.BodyHandlers.discarding());

            System.out.println("Public route: "
                    + publicRoute.statusCode() + "/" + publicRoute.body());
            System.out.println("Admin without key: "
                    + blocked.statusCode());
            System.out.println("Admin with key: "
                    + adminRoute.statusCode() + "/" + adminRoute.body());
            System.out.println("Method rejected: "
                    + method.statusCode());
            System.out.println("Missing route: "
                    + missing.statusCode());
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 JdkHttpServerRoutesDemo.java
java --add-modules jdk.httpserver JdkHttpServerRoutesDemo
```

Stdout đã kiểm chứng:

```text
Public route: 200/PUBLIC
Admin without key: 401
Admin with key: 200/ADMIN
Method rejected: 405
Missing route: 404
```

**Giải thích chính xác:**

1. `server.createContext("/api/", ...)` đăng ký một context prefix, còn `"/api/admin/"` dài hơn nên thắng khi yêu cầu `/api/admin/status` đến.
2. Request `GET /api/items` nhận body `PUBLIC` và HTTP 200 từ handler public.
3. Request admin thiếu `X-Demo-Key` bị filter chặn, nhận HTTP 401. Filter không gọi `chain.doFilter` trong đường từ chối.
4. Request admin có header giả định `demo-key` được phép đi qua filter, nhận `ADMIN`. **Không dùng key cứng này ngoài demo.**
5. Request POST vào route GET-only nhận **405**; handler gắn `Allow: GET`.
6. Request không khớp context nào được HTTP server trả **404**.
7. Body response tính bằng số bytes UTF-8 và được đóng đúng trong try-with-resources; `server.stop(0)` và `workers.shutdownNow()` dọn server test.
8. Toàn bộ test chỉ dùng loopback, **không gọi URL Internet**; nó kiểm chứng semantics của routing/filter/status, không chứng minh hiệu năng production.

Bạn có thể thay `Filter` demo bằng một filter thực hiện authn chuyên nghiệp, nhưng phải tự xử lý token validation, rotation, audit, authorization, timing leaks, rate limits và lỗi upstream.

## 18. Ví dụ Java 17+ số 2 — hai worker song song và bẫy prefix /v1

Tệp **`JdkHttpServerExecutorDemo.java`** dùng `CountDownLatch` để bảo đảm hai requests `/work/one` và `/work/two` **đã đồng thời vào hai handlers** trước khi cho chúng trả response. Điều này kiểm chứng việc set executor hai threads thực sự cho phép hai tasks cùng xử lý.

Chương trình còn cố tình đăng ký `createContext("/v1", ...)` (không có dấu slash cuối), rồi gọi `GET /v123` để chứng minh **literal prefix matching** có thể khớp sai về mặt REST design. `GET /V1` không khớp vì case-sensitive; `GET /empty` trả 204 không body.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class JdkHttpServerExecutorDemo {
    private static void reply(HttpExchange exchange, String text)
            throws IOException {
        try (exchange) {
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(bytes);
            }
        }
    }

    private static HttpRequest request(String base, String path) {
        return HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(7)).GET().build();
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        CountDownLatch entered = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        server.createContext("/work/", exchange -> {
            entered.countDown();
            boolean ready;
            try {
                ready = release.await(5, TimeUnit.SECONDS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                ready = false;
            }
            if (ready) {
                reply(exchange, "DONE");
            } else {
                try (exchange) {
                    exchange.sendResponseHeaders(503, -1);
                }
            }
        });
        server.createContext("/v1", exchange -> reply(exchange, "PREFIX"));
        server.createContext("/empty", exchange -> {
            try (exchange) {
                exchange.sendResponseHeaders(204, -1);
            }
        });
        server.setExecutor(workers);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();

            CompletableFuture<HttpResponse<String>> one =
                    client.sendAsync(request(base, "/work/one"),
                            HttpResponse.BodyHandlers.ofString());
            CompletableFuture<HttpResponse<String>> two =
                    client.sendAsync(request(base, "/work/two"),
                            HttpResponse.BodyHandlers.ofString());

            boolean parallel = entered.await(5, TimeUnit.SECONDS);
            release.countDown();
            HttpResponse<String> a = one.get(6, TimeUnit.SECONDS);
            HttpResponse<String> b = two.get(6, TimeUnit.SECONDS);

            HttpResponse<String> prefix = client.send(
                    request(base, "/v123"),
                    HttpResponse.BodyHandlers.ofString());
            HttpResponse<Void> caseSensitive = client.send(
                    request(base, "/V1"),
                    HttpResponse.BodyHandlers.discarding());
            HttpResponse<String> empty = client.send(
                    request(base, "/empty"),
                    HttpResponse.BodyHandlers.ofString());

            System.out.println("Parallel handlers entered: " + parallel);
            System.out.println("Work replies: "
                    + a.statusCode() + "," + b.statusCode());
            System.out.println("Literal prefix /v1 matches /v123: "
                    + "PREFIX".equals(prefix.body()));
            System.out.println("Case-sensitive route: "
                    + caseSensitive.statusCode());
            System.out.println("No-body status: "
                    + empty.statusCode() + "/" + empty.body().length());
        } finally {
            release.countDown();
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Lệnh chạy:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 JdkHttpServerExecutorDemo.java
java --add-modules jdk.httpserver JdkHttpServerExecutorDemo
```

Stdout:

```text
Parallel handlers entered: true
Work replies: 200,200
Literal prefix /v1 matches /v123: true
Case-sensitive route: 404
No-body status: 204/0
```

Ý nghĩa:

1. Hai futures client gửi hai requests trong cùng thời gian; server có `Executors.newFixedThreadPool(2)`. Latch `entered.await(5,SECONDS)` chỉ trả `true` sau khi **cả hai handlers đã bước vào**, không suy đoán concurrency từ thời gian phản hồi.
2. `release.countDown()` giải phóng handlers, hai response nhận HTTP 200. Điều này chỉ đo correctness trên loopback; không đảm bảo throughput với hàng ngàn clients.
3. Context `"/v1"` nhận cả `"/v123"` theo định nghĩa literal prefix, cho thấy tại sao REST path boundaries phải được thiết kế cẩn thận.
4. `"/V1"` nhận 404, vì so khớp context có phân biệt chữ hoa/thường.
5. `204, -1` biểu diễn no-body response; client xác nhận độ dài body bằng 0. **Đừng dùng `sendResponseHeaders(204,0)` để ngụ ý no-body**, vì 0 là chunked trong API.
6. `newFixedThreadPool(2)` có queue mặc định không giới hạn; mẫu này **chỉ phục vụ demo**, không phải production overload control.
7. Code có `finally` giải phóng latch, gọi `stop` và dọn executor để tránh treo test.

## 19. Observability và vận hành: phần còn thiếu thường lớn hơn HTTP handler

Một web service production thường cần:

| Mục vận hành | Khả năng tự có với API tối giản | Cần bổ sung |
| --- | --- | --- |
| Request/response access logging | Không có một pipeline structured access logs đầy đủ, ứng dụng phải thiết kế | Method/path/status, latency, correlation, privacy redaction |
| Metrics | Không có contract metrics cho từng route/SLA như framework instrumentation | Counters/histograms, queue depth, active handlers, saturation |
| Distributed tracing | Không tự propagate trace context theo business | Trace extraction/injection, spans cho DB/downstream |
| Health/readiness | Tự tạo context được | Check kết nối DB, dependency health, draining/readiness |
| Config/secrets | Phụ thuộc ứng dụng | Environment/secret manager, validation, rotation |
| Graceful shutdown | `stop(int delay)` có semantics cơ bản | Ngừng nhận traffic, chờ jobs, hạ readiness, flush logs/traces |
| Load shedding | Không có một policy business per route sẵn có | Bounded queues, 429/503, rate limiting, circuit breaker |
| Security review | TLS/Auth building blocks tồn tại | RBAC, CORS/CSRF, body quotas, validation, pentest |

Với ứng dụng cần audit/compliance, **chi phí tự viết/cập nhật/hardening** các phần này có thể lớn hơn việc chạy một server/framework đã tích hợp chúng trong hệ sinh thái (dù framework cũng cần cấu hình và bảo trì).

Một health endpoint luôn trả “OK” dù DB chết không phải readiness tốt; readiness phải phản ánh khả năng thật để nhận traffic theo contract. Đồng thời, tránh để health probe nặng tạo vòng truy vấn DB vô hạn.

## 20. Shutdown: stop(delay) không phải hệ thống orchestration đầy đủ

Theo Javadoc Java 17, `HttpServer.stop(int delay)`:

- Ngừng nhận exchanges mới.
- Đợi handlers đang xử lý hoàn tất hoặc khi khoảng `delay` (giây) hết, tùy mốc nào đến trước.
- Sau đó đóng open TCP connections, dừng background server thread và trả về.
- **Không thể restart cùng `HttpServer` object** sau khi đã stop.

Một trình tự shutdown có kiểm soát:

```text
1. Readiness -> false; ngừng nhận traffic mới từ ingress
2. Ngừng tạo công việc background mới
3. Chờ các requests đang chạy theo total deadline
4. Gọi server.stop(delaySeconds)
5. Đóng/đợi executor do application sở hữu
6. Flush logs/traces và đóng DB clients/other resources
7. Exit process
```

Cần phân biệt `stop(0)` trong **test loopback** (muốn kết thúc nhanh) với yêu cầu graceful drain trong production. Đừng gọi `workers.shutdownNow()` khi vẫn còn operation có side effect quan trọng chưa có policy lưu trạng thái.

`stop(delay)` không phải API hỗ trợ live reload, zero-downtime deploy, chuyển traffic, rollback DB transactions hay tự phối hợp với orchestrator. Những năng lực này phải được thiết kế ở mức hệ thống.

## 21. Bảng lựa chọn: trường hợp nào phù hợp, trường hợp nào cần khác?

| Kịch bản | Hướng lựa chọn ban đầu | Điều kiện |
| --- | --- | --- |
| Unit/integration test cần HTTP endpoint thật trên loopback | **JDK HttpServer** rất phù hợp | Tự đóng server; port tự cấp; kiểm thử status/body |
| Công cụ CLI có health/control endpoint local | **JDK HttpServer** thường phù hợp | Bind 127.0.0.1, hạn chế auth và vòng đời |
| Embedded admin API của service nội bộ, traffic nhỏ | **Có thể dùng JDK HttpServer** | Private network, HTTPS/proxy, quotas, logs, security review |
| REST API nhỏ, nhóm sẵn sàng tự quản HTTP concerns | **Cân nhắc** | Có checklist security/metrics/tests và đo tải |
| Public service nhiều tenant, high concurrency, phức tạp về auth | **Ưu tiên đánh giá framework/server chuyên dụng** | Auth integration, middleware, limit knobs, observability, ops |
| HTTP/2/gRPC/WebSocket server là yêu cầu cốt lõi | **Chọn stack có protocol support rõ** | Không tự dựng từ `HttpExchange` như giải pháp chính |
| Multipart/media upload lớn, đòi resumable/quotas | **Server/framework hoặc gateway phù hợp** | Streaming, per-tenant quotas, disk safeguards, upload sessions |
| Microservice cần deployment/health/metrics enterprise | **Xem tổng stack** | Không chỉ xem HTTP handler; tích hợp tracing, config, lifecycle |

Không tuyên bố tất cả sản phẩm phải dùng framework nặng. Một JDK server kèm gateway, threat model rõ, deployment kiểm soát và team có expertise **có thể** đủ tốt cho service có yêu cầu giới hạn. Ngược lại, nếu phải tự viết mười thứ middleware/core protocol, lựa chọn “ít dependency” có thể tạo **tổng chi phí sở hữu lớn hơn**.

## 22. So sánh theo năng lực thay vì tên framework

Khi cần tìm lựa chọn khác, không nên dựa vào quảng cáo “nhanh nhất”. Các nhóm lựa chọn:

- **Servlet containers:** phù hợp khi cần Servlet ecosystem, filters, sessions, chuẩn tích hợp của Java web.
- **Async/event-loop servers:** phù hợp high concurrency/I/O workloads, nhưng đòi thiết kế nonblocking/backpressure đúng; callback sai vẫn có thể nghẽn.
- **Application frameworks:** routing, validation, serialization, error mapping, auth integration, config/metrics, test fixtures và nhiều conventions; đổi lại thêm dependency/build/deployment complexity.
- **Reverse proxy + JDK handler:** khi cần giữ một lõi service nhỏ, đẩy TLS/rate limit/HTTP2 về edge và tự hoàn thiện security trong handler.
- **Managed platform/gateway:** chuyển một phần trách nhiệm về infrastructure, nhưng không miễn trừ nghiệp vụ/authorization/observability trong code.

Ví dụ các tên thường gặp trong Java là Tomcat, Jetty, Undertow, Netty hoặc framework ứng dụng dựa trên các server đó. Đây là **các loại ứng viên cần đánh giá**, không phải khẳng định tất cả đều có cùng tính năng/phiên bản/cấu hình mặc định.

Một bảng chấm điểm nên dùng các cột: **requirement, importance, native support, mitigation effort, operational owner, load-test evidence, security risk, decision**. Đừng đưa một benchmark duy nhất lên thay thế security/availability trade-offs.

## 23. Cách thử tải và chứng minh yêu cầu phi chức năng

Định nghĩa workload trước khi benchmark:

1. **Warmup:** JVM JIT, connection establishment, caches và DB pools không nên chi phối sai p95/p99.
2. **Request mix:** GET nhỏ, POST JSON, uploads, query DB chậm, error 4xx/5xx và malformed data theo tỷ lệ thực.
3. **Concurrency:** tăng người dùng/kết nối/tasks đến khi latency hoặc error rate vượt SLA.
4. **Slow client tests:** gửi headers/body chậm, giữ keep-alive, đọc response chậm để xem worker saturation.
5. **Payload caps:** thử body không có `Content-Length`, chunked, oversized, invalid UTF-8, JSON deeply nested.
6. **Lifecycle:** ngừng container khi còn requests, restart, readiness drain, shutdown trong lúc DB commit.
7. **Security:** direct access bypass proxy, X-Forwarded spoof, authz cross-tenant, CORS/CSRF, path normalization traversal.
8. **Resource tracking:** heap, GC pause, open FDs/sockets, thread count, executor active/queued, DB pool saturation.

**Tài liệu hóa kết quả**: tại N concurrent connections / RPS, p95 dưới X ms, p99 dưới Y ms, lỗi dưới Z%, memory dưới quota, trong điều kiện test đã mô tả. Những giá trị N/X/Y/Z là **từ SLA của ứng dụng**, không phải giá trị mặc định Java hay ngưỡng chung cho mọi service.

Nếu framework khác có overhead cao hơn trong bài “hello world” nhưng đã giảm đáng kể công tự xây auth/observability/lifecycle, quyết định tổng thể vẫn có thể nghiêng về framework. Benchmark riêng throughput không đủ.

## 24. Những sai lầm phổ biến cần tránh

1. **“Có HttpServer nên sản phẩm tự hỗ trợ HTTP/2/WebSocket.”** Không có contract như vậy trong Java 17 `jdk.httpserver`.
2. **“Tên com.sun nghĩa không dùng được trên JDK.”** Package này được export chính thức từ `jdk.httpserver`; phải phân biệt với internal API.
3. **“createContext("/v1") chỉ khớp đúng /v1.”** Sai: `/v123` cũng có thể khớp; dùng path boundaries đúng.
4. **“Context tự hiểu GET/POST.”** Không: handler phải kiểm tra method.
5. **“Default executor là pool nhiều worker.”** Không nên giả định: Javadoc mô tả default dùng thread do `start()` tạo.
6. **“newFixedThreadPool có queue bounded.”** Sai: factory tạo queue không giới hạn theo contract.
7. **“backlog=0 nghĩa không giới hạn kết nối.”** Sai: sử dụng system default.
8. **“setExecutor sau start cũng được.”** Sai: Java 17 yêu cầu set trước `start()`.
9. **“Response length=0 nghĩa body rỗng.”** Sai: chọn chunked; `-1` là no body.
10. **“Có InputStream nên upload không thể gây OOM.”** Nếu gọi `readAllBytes()` không quota vẫn có thể OOM.
11. **“Quên close HttpExchange chẳng ảnh hưởng gì.”** Có thể giữ resources và cản keep-alive.
12. **“BasicAuthenticator đủ làm OAuth2/OIDC/RBAC.”** Không; chỉ building block.
13. **“HTTPS là không có vì HttpServer chỉ HTTP.”** Có `HttpsServer` với `SSLContext`/`HttpsConfigurator`.
14. **“Bật proxy là handler không cần authz.”** Sai: proxy không thay quyền theo tài nguyên trong business logic.
15. **“RemoteAddress luôn là IP người dùng.”** Sau reverse proxy thường là proxy; forwarded headers không mặc định đáng tin.
16. **“Stop(0) là graceful drain đủ cho mọi production.”** Không: cần readiness/deadlines/owned resources.
17. **“Sau stop có thể start lại same object.”** Sai theo Javadoc.
18. **“Dùng Socket/HTTP API tối giản sẽ tự có security rate limit.”** Không: cần thiết kế admission/quotas.
19. **“Chỉ cần test GET 200.”** Thiếu auth/405/404, slow clients, malformed requests, shutdown, concurrent load.
20. **“Proxy và framework sẽ tự sửa mọi bug.”** Không: ứng dụng vẫn chịu trách nhiệm validation, business invariants và idempotency.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Tạo `HttpServer` từ Java 17 mà không thêm thư viện bên ngoài được không? **Có**, khi runtime chứa module `jdk.httpserver`.

**Câu 2.** Một context `"/users"` có thể khớp `"/users-old"` không? **Có**, do longest literal prefix matching. Không coi đó là REST route hoàn chỉnh.

**Câu 3.** Không đặt `setExecutor` thì có thể xem server đã có thread pool worker theo cấu hình app không? **Không**; Javadoc nêu default dùng thread do `start()` tạo.

**Câu 4.** `backlog=100` có nghĩa tối đa 100 HTTP requests đồng thời trong handler? **Không**, backlog là queue của TCP connections chờ accept.

**Câu 5.** `sendResponseHeaders(200,0)` nghĩa response body không được gửi? **Không**; 0 chọn chunked. Đối với no body, dùng `-1` theo contract.

**Câu 6.** Một người dùng có xác thực thành công bằng Basic, có được truy cập resource của tenant khác? **Không mặc định**; cần authorization theo resource.

**Câu 7.** JDK có HTTPS server không? **Có**, `HttpsServer` với `HttpsConfigurator` và `SSLContext`.

**Câu 8.** Có thể dùng `HttpServer` cho test loopback phục vụ một endpoint có handler thật? **Có**, và rất phù hợp khi scope/test rõ.

**Câu 9.** Vì sao `newFixedThreadPool(4)` chưa chắc an toàn khi traffic burst? **Queue mặc định không giới hạn**; cần admission/backpressure và overload policy.

**Câu 10.** Dùng reverse proxy để terminate TLS có làm SQL injection trong handler biến mất không? **Không**. Validation và parameterized SQL vẫn là trách nhiệm ứng dụng.

**Câu 11.** Muốn WebSocket server hoặc gRPC/HTTP2 chuyên dụng là yêu cầu chính, có nên mặc định chọn `jdk.httpserver`? **Không**; hãy chọn stack có capability/contract phù hợp, không tự triển khai protocol production từ vài callbacks.

**Câu 12.** Trước khi chọn server, nên chấm điểm số dòng code hay yêu cầu vận hành nào? **Yêu cầu có thể kiểm chứng** về protocol, security, throughput, p95/p99, timeout, quotas, monitoring, lifecycle, maintenance và integration.

## 26. Checklist cuối cùng và tài liệu tham khảo

Trước khi ký quyết định dùng `jdk.httpserver`:

- [ ] Xác định use case: test, loopback internal, embedded admin API hay public multi-tenant.
- [ ] Chốt HTTP version, TLS, WebSocket/gRPC/SSE requirements; không tự hứa tính năng API không có.
- [ ] Kiểm tra routing literal prefix, path decode/case-sensitivity và method checks.
- [ ] Thiết kế request body quota, header size/resource budgets, timeouts, slow-client behavior.
- [ ] Set executor trước start; chọn pool/queue/admission bounded và cách trả overload.
- [ ] Xác định authn + authz per resource, secrets, mTLS và trusted proxy boundaries.
- [ ] Nếu dùng HTTPS, có `SSLContext` chuẩn, cert rotation và TLS verification plan.
- [ ] Chuẩn hóa Content-Type, charset, length = số UTF-8 bytes và đóng `HttpExchange` đúng.
- [ ] Tạo filter/error-mapping và giới hạn log/metrics; không ghi credentials.
- [ ] Bổ sung health/readiness, tracing, structured access logs và incident runbooks.
- [ ] Kiểm tra `stop(delay)`, orchestrator draining, không dựa vào restart same server object.
- [ ] Load test cùng workload thật; đo p95/p99, error rate, memory, queue, threads và sockets.
- [ ] Có owner và chi phí bảo trì cho mọi middleware hay protocol logic phải tự xây.
- [ ] Ghi rõ quyết định: **JDK server trực tiếp**, **JDK server + gateway**, hay **framework/server chuyên dụng**.

**Kết luận:** `HttpServer` trong JDK 17 là **HTTP server nhúng hữu ích**, không phải một framework web đầy đủ. Nó cung cấp các building blocks đủ cho nhiều ứng dụng nhỏ khi rủi ro và tải được kiểm soát, nhưng **routing literal prefix, blocking handlers, default executor, giới hạn middleware/protocol, security và vận hành** là các chi phí phải xem trước khi chọn. Quyết định đúng là quyết định dựa trên yêu cầu đo được, test và trách nhiệm sở hữu, thay vì mặc định “ít dependency = production-ready”.

### Nguồn Java SE 17 chính thức

- [Module jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html)
- [Package com.sun.net.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/package-summary.html)
- [HttpServer — contexts, executor, backlog, stop](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [HttpContext — filters và authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html)
- [HttpExchange — request/response lifecycle, length và close](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html)
- [Filter — pre/post-processing](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html)
- [HttpsServer / HttpsConfigurator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html)
- [BasicAuthenticator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/BasicAuthenticator.html)
- [Executors.newFixedThreadPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html) và [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).