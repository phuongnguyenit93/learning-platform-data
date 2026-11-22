# Giới hạn phạm vi trước khi chọn framework cho yêu cầu phức tạp

**`com.sun.net.httpserver.HttpServer`** của module **`jdk.httpserver`** là một HTTP server nhỏ gọn có sẵn trong JDK. Nó hữu ích khi cần một endpoint kiểm thử, health check, tiện ích nhúng hoặc một dịch vụ HTTP nhỏ với yêu cầu đã biết. Tuy nhiên, **“có thể nhận HTTP request” không có nghĩa “đã có đầy đủ một nền tảng web cho sản phẩm phức tạp”**. Trước khi quyết định dùng JDK server thuần hay chuyển sang framework/server khác, hãy xác định **phạm vi**, **những trách nhiệm phải tự xây** và **tiêu chí có thể kiểm chứng**.

Tài liệu chính thức của Oracle về `jdk.httpserver` xác nhận API/SPI và default implementation được thiết kế cho **HTTP semantics tối giản**, chủ yếu phục vụ **local testing, development và debugging**; thiết kế **không nhằm trở thành full-featured, high-performance HTTP server**. Điều này **không có nghĩa `HttpServer` đã bị legacy/deprecated**: nó vẫn là API công khai, được hỗ trợ trên Java 17+ và JDK 26. Cũng không có nghĩa mọi dự án thật đều bắt buộc dùng Spring, Quarkus hoặc framework khác.

**Thông điệp của bài học:**

> Hãy lựa chọn kiến trúc từ **yêu cầu chức năng, bảo mật, vận hành và tải thực tế**. Giữ `HttpServer` khi mục tiêu nhỏ và ràng buộc có thể kiểm soát; chỉ chọn framework khi nó loại bỏ được nhiều chi phí/rủi ro hơn phần phụ thuộc và độ phức tạp mà nó đem vào.

Bài thuộc nhóm **HTTP server gọn**, tập trung vào việc **giới hạn phạm vi trước khi chọn framework cho yêu cầu phức tạp**, không phải hướng dẫn sử dụng một framework cụ thể. Mọi API Java được giới thiệu đều còn áp dụng hiện nay. Hai demo Java 17+ độc lập cuối bài đã **biên dịch bằng `javac --release 17` và chạy trên JDK 24**: một bộ phân loại nhu cầu minh bạch (4/4 tình huống PASS) và một HTTP server loopback với 10 kiểm tra HTTP thực tế PASS.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Nêu đúng những gì `HttpServer`, `HttpHandler`, `HttpExchange`, `HttpContext`, `Filter`, `Authenticator` và `HttpsServer` cung cấp.
2. Phân biệt **khả năng có sẵn**, **khả năng tự triển khai với công sức hữu hạn** và **nhu cầu nên đánh giá một server/framework khác**.
3. Nhận diện giới hạn của routing kiểu **literal longest-prefix**, method dispatch, path parameters, request parsing, body validation và response serialization.
4. Đánh giá yêu cầu bảo mật: TLS, authentication, authorization, token/certificate lifecycle, CORS, CSRF, rate limits, request size và path normalization.
5. Xây một bảng tiêu chí quyết định dựa trên **SLO, lưu lượng, số lượng endpoints, dữ liệu, phụ thuộc, giao thức và năng lực vận hành**.
6. Biết khi nào **reverse proxy/API gateway** là một phần lời giải, và khi nào nó không thay thế vấn đề ở tầng business logic.
7. Tránh giả định rằng cứ có `HttpServer` là có HTTP/2/WebSocket/REST validation/observability tích hợp.
8. Tránh ngược lại: dùng framework lớn chỉ để có một localhost health endpoint.
9. Giữ mã nghiệp vụ độc lập khỏi HTTP adapter để có thể đổi transport/framework sau này.
10. Viết phép thử “scope gate” rõ ràng, đánh giá use case mà không dùng một con số magic như “hơn 10 routes = Spring”.
11. Chạy demo HTTP có kiểm tra URI literal prefix, UTF-8 byte lengths, method 405, giới hạn request body 413 và resource cleanup.
12. Tạo một quyết định kỹ thuật có **giả định, phương án thay thế, bằng chứng đo, điều kiện dừng và kế hoạch migration**.

## 2. HttpServer thực sự cung cấp gì?

`HttpServer` nằm trong package `com.sun.net.httpserver` được module `jdk.httpserver` **export công khai**. Tên package `com.sun` ở đây không làm API trở thành internal unsupported package kiểu `sun.*`. Một chương trình Java 17+ có thể:

```java
HttpServer server = HttpServer.create(
        new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
server.createContext("/health", exchange -> {
    try (exchange) {
        byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders()
                .set("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, body.length);
        try (var output = exchange.getResponseBody()) {
            output.write(body);
        }
    }
});
server.start();
```

**Đây chỉ là mảnh code** minh họa API. Một ứng dụng hoàn chỉnh phải xử lý checked exceptions, quản lý `server.stop`, quản lý executor khi có, áp deadline và hạn chế request input. Các demo chạy độc lập được trình bày sau.

### 2.1. Những khả năng cốt lõi

| Nhóm | JDK server cung cấp | Cần hiểu thêm |
| --- | --- | --- |
| Socket HTTP | `HttpServer.create/bind/start/stop`. | Chọn bind address, port, backlog, shutdown policy. |
| Routing | `createContext(path, HttpHandler)`. | Literal prefix dài nhất, case-sensitive; không phải REST router. |
| Handler | `HttpHandler.handle(HttpExchange)`. | Ứng dụng phải xử lý method, validation, errors và response. |
| Request | `getRequestMethod`, `getRequestURI`, `getRequestHeaders`, `getRequestBody`. | Streams có thể lớn; path/raw encoding do ứng dụng kiểm tra. |
| Response | `getResponseHeaders`, `sendResponseHeaders`, `getResponseBody`. | Fixed-length, chunked/no-body và đóng exchange đúng. |
| Interception | `Filter`/`Filter.Chain`. | Không tự động có distributed tracing hay security filters hoàn chỉnh. |
| Authentication hook | `HttpContext.setAuthenticator`, `BasicAuthenticator`. | Không tương đương OIDC/OAuth2/RBAC/multi-tenant policy. |
| Concurrency | `setExecutor(Executor)`. | Thread pools, queue capacity, saturation và shutdown vẫn phải quản lý. |
| HTTPS | `HttpsServer` + `HttpsConfigurator`/`SSLContext`. | TLS policy, certificate lifecycle và reverse proxy là trách nhiệm triển khai. |
| Provider SPI | `HttpServerProvider`. | Provider mặc định là server đơn giản, không framework đầy đủ. |

### 2.2. Những thứ không nên kỳ vọng “tự có”

Không có lý do để tự cho rằng `HttpServer` sẽ cung cấp sẵn:

- Router khai báo `GET /users/{id}` với type conversion và route constraints.
- Annotation-driven controllers, dependency injection, middleware ecosystem lớn.
- JSON serialization/deserialization, schema validation, OpenAPI contract generation.
- Request/response DTO binding và xử lý lỗi có cấu trúc nhất quán.
- Session/cookie/CSRF/OIDC/RBAC policies dành cho ứng dụng người dùng.
- HTTP/2 hoặc WebSocket endpoint API trong **default minimal server**.
- Streaming multipart uploads, resumable transfers hoặc file storage pipeline bảo mật.
- Structured logs/metrics/traces, dashboard readiness/liveness, graceful lifecycle của một production stack.
- API versioning, pagination, idempotency policies, retries/circuit breakers và distributed transactions.
- Giới hạn tải, chống DDoS, abuse detection, WAF, certificate rotation và observability tự động.

**Không có sẵn ≠ không thể làm được.** Ứng dụng có thể bổ sung library, filter, gateway và custom code. Vấn đề cần quyết định là **chi phí phát triển, kiểm thử và vận hành phần bổ sung đó có còn hợp lý không?**

## 3. Phân loại yêu cầu theo ba tầng

Trước khi so sánh framework, xếp yêu cầu vào ba tầng:

| Tầng | Mô tả | Ví dụ | Quyết định thường hợp lý |
| --- | --- | --- | --- |
| **A — đơn giản/cố định** | Ít endpoint, internal/loopback, không có sensitive workflows, xử lý ngắn. | `/health`, diagnostic endpoint, webhook test in isolated environment. | `HttpServer` có thể đủ với bảo vệ tối thiểu. |
| **B — thêm guardrails nhưng còn kiểm soát được** | Có một số clients nội bộ, method/path validation, input quotas, log/metrics cơ bản. | Internal tool ít route sau gateway đáng tin. | Giữ JDK server **nếu** đã chứng minh được auth, limits, operability và ownership. |
| **C — hệ thống ứng dụng phức tạp** | Nhiều giao thức, user identity/tenant isolation, public SLA, rich API, team lớn hoặc nhiều integrations. | Public CRUD API, realtime WebSocket, multi-tenant service có RBAC và tracing. | **Đánh giá** framework/server/gateway đầy đủ thay vì tự xây toàn bộ. |

Đây là **heuristic thiết kế**, không phải tiêu chuẩn của Java hoặc quy tắc bắt buộc. Một ứng dụng rất ít routes nhưng xử lý dữ liệu tài chính/cá nhân nhạy cảm vẫn có thể thuộc tầng C. Một hệ thống có nhiều endpoints rất đơn giản nhưng được generate theo spec có thể vẫn gọn nếu dùng cách tiếp cận phù hợp.

### 3.1. Câu hỏi gốc cần trả lời trước lựa chọn công nghệ

Viết một bản scope ngắn:

1. Ai là client (localhost CLI, private service, browser, partner, Internet)?
2. Dữ liệu gì (public test data, PII, token, payment data, file uploads)?
3. API nào (GET/POST, JSON, streaming, multipart, WebSocket, SSE, HTTP/2)?
4. Số requests, p95/p99 latency, concurrent connections và payload sizes là bao nhiêu?
5. Có authN/authZ theo người dùng, role, tenant/resource không?
6. Mục tiêu uptime, recovery, backup, rolling deploy và audit là gì?
7. Ai chịu trách nhiệm cập nhật dependencies, certificates và security patches?
8. Framework có giải quyết một tập lớn yêu cầu đã được xác nhận không, hay chỉ thêm abstraction không cần thiết?

Nếu chưa trả lời được, đừng bắt đầu bằng “dùng Spring cho chắc” hoặc “JDK thuần luôn nhẹ hơn”. Hãy đo và xác định những yêu cầu **bắt buộc** trước.

## 4. Giới hạn định tuyến và HTTP semantics

`HttpServer` chọn `HttpContext` theo **longest literal prefix** của request URI path, **phân biệt chữ hoa/thường** và **không giải mã percent-encoded path** trước bước so match. Nó **không** chọn context dựa trên HTTP method hoặc query string. Ví dụ:

| Context đã đăng ký | HTTP request | Điều xảy ra |
| --- | --- | --- |
| `"/api"` | `GET /api2` | Có thể match `"/api"` vì prefix, dù không cùng segment. |
| `"/api/"` | `GET /api2` | Không match `"/api/"`. |
| `"/users/"` | `GET /users/42` | Match prefix, nhưng phải tự parse `42`. |
| `"/users/"` | `POST /users/42` | Vẫn match context; phải tự kiểm tra POST có được phép. |
| `"/hello"` | `GET /helloworld` | Có thể match `"/hello"`; exact-path check cần nằm trong handler. |
| `"/HELLO"` | `GET /hello` | Không match vì case-sensitive. |
| `"/api/"` | `GET /api/items?x=1` | Query không tác động chọn context. |
| `"/users/"` | `GET /users/%34%32` | Cần định nghĩa policy raw/decoded path, không tự coi suffix là số 42. |

### 4.1. Khi nào tự router là hợp lý?

Nếu chỉ có `GET /health` và `POST /task`, việc viết điều kiện kiểm tra method và path có thể rất ngắn và minh bạch.

Nhưng khi xuất hiện:

- Hàng chục route có path variables và constraints khác nhau.
- Nhiều versions `/v1`, `/v2` có compatibility contract.
- Content negotiation, validation DTO, pagination, error mapping đồng nhất.
- Annotations, cross-cutting auth/tracing, API documentation.
- Nhiều nhóm phát triển cùng thêm endpoints.

…thì custom router có thể trở thành framework tự chế. Ngưỡng chuyển đổi không phải một số route cố định: hãy nhìn vào **độ phức tạp thay đổi và lỗi lặp lại**, cùng số giờ test/bảo trì.

### 4.2. Path và query cần policy thống nhất

`exchange.getRequestURI().getRawPath()` giữ percent encoding; `getPath()` đã decode. Nếu reverse proxy match raw path còn application match decoded path, có thể xảy ra **route confusion** hoặc path traversal. Những lỗi dễ có:

- Decode hai lần.
- Không thống nhất canonicalization dấu `/`, `..`, encoded separators.
- Chỉ kiểm tra `startsWith("/admin")` nên nhận nhầm `/administrator`.
- Dùng query parameter làm routing security flag.
- Phân quyền theo decoded path khác với path được resource handler sử dụng.

Một framework cũng cần cấu hình và kiểm thử các điểm này; không có gì “tự an toàn tuyệt đối” chỉ vì có router declarative.

## 5. HTTP request/response lifecycle: trách nhiệm dễ bị đánh giá thấp

`HttpHandler` nhận một `HttpExchange` đại diện cho **một HTTP request và response**. Handler phải:

1. Kiểm tra method/path, authentication và authorization.
2. Kiểm tra headers, content type, size và format của request.
3. Đọc `getRequestBody()` có giới hạn hoặc stream khi payload lớn.
4. Xử lý dữ liệu nghiệp vụ qua service riêng.
5. Đặt response headers trước `sendResponseHeaders`.
6. Gửi status và response length đúng.
7. Ghi output, đóng stream và exchange ngay cả khi gặp lỗi.

Đây là chi phí “ẩn” khi tự xử lý một endpoint. Nếu ứng dụng có nhiều endpoint, một middleware abstraction sẽ rất nhanh xuất hiện — đôi khi đó chính là dấu hiệu nên xem xét framework.

### 5.1. Response length là **số byte**, không phải số ký tự

`sendResponseHeaders(int,long)` có ba chế độ:

| Giá trị responseLength | Ý nghĩa | Rủi ro nếu hiểu sai |
| --- | --- | --- |
| `>0` | Độ dài **chính xác** theo bytes. | Dùng `String.length()` với UTF-8 làm response sai hoặc connection abort. |
| `0` | Chunked response (không biết trước độ dài). | Nhầm `0` là body rỗng. |
| `-1` | Không có response body. | Ghi body dù status như 204. |

JDK 26 có các hằng `HttpExchange.RSPBODY_CHUNKED` và `RSPBODY_EMPTY` tương ứng, nhưng **demo Java 17+ sử dụng số 0/-1** để đảm bảo `--release 17` biên dịch được. Không giới thiệu hằng mới như một API Java 17.

### 5.2. Một response đã bắt đầu không được viết lại status

Sau `sendResponseHeaders(...)`, status đã được gửi. Nếu downstream operation lỗi giữa lúc stream body, bạn **không thể giả định** gửi thêm một HTTP 500 body mới thay thế response đang diễn ra. Cần dự liệu streaming error semantics, đóng stream, log/correlation ID và retry policy ở client (nếu có thể).

### 5.3. Body quotas cần được thi hành **trong khi đọc**

`Content-Length` có thể thiếu/sai theo input; đừng tin nó hoàn toàn. Ví dụ:

```java
final int maxBytes = 32;
byte[] received;
try (var in = exchange.getRequestBody()) {
    received = in.readNBytes(maxBytes + 1);
}
if (received.length > maxBytes) {
    // Gửi 413, không parse thêm.
}
```

Đây là mảnh code cần `exchange` và xử lý I/O/response phù hợp. Nó minh họa cách phát hiện quá giới hạn cho body nhỏ, **không phải** chính sách production hoàn chỉnh: bạn vẫn cần HTTP header limits, deadline, streaming body parser, proxy quotas và chống request flooding.

## 6. Yêu cầu bảo mật nào làm phạm vi tăng mạnh?

Một endpoint nhận từ Internet có attack surface khác hẳn localhost probe. Những yêu cầu sau thường đưa quyết định từ “viết vài handler” sang “đánh giá stack có tích hợp bảo mật”:

| Yêu cầu | JDK server có sẵn đến đâu? | Phần phải chủ động đảm nhận |
| --- | --- | --- |
| HTTPS | `HttpsServer`/`HttpsConfigurator`/`SSLContext`. | Chứng chỉ, rotation, TLS policy, cipher/certificate validation, termination. |
| Authentication | `HttpContext.setAuthenticator`, basic hooks. | OIDC/OAuth2/JWT session/cookies, login flows, token introspection và revocation. |
| Authorization | Không có RBAC/ABAC policy engine hoàn chỉnh mặc định. | Kiểm tra quyền theo user/role/tenant và từng resource. |
| Rate limiting | Không có application quotas tự động. | Theo client/key/tenant, overload handling, distributed state nếu cần. |
| CORS | Tự đặt/kiểm soát headers. | Origins/methods/credentials/preflight caching chính xác. |
| CSRF | Không có bảo vệ tự động. | Nếu dùng cookies/browsers, token/SameSite/origin policy. |
| Request validation | Có body InputStream. | JSON, schema, multipart, limits, validation errors. |
| Secret management | Không do HttpServer xử lý. | Keystore/KMS, rotation, least privilege, audit. |
| Access logs & tracing | Có Filter + custom code. | PII redaction, correlation IDs, trace propagation, metrics. |
| Abuse prevention | Chỉ có socket/threads và settings provider. | Bot/DoS protections, IP/device/account quotas, egress/network policy. |

**Framework cũng không tự cung cấp đầy đủ bảo mật chỉ nhờ thêm dependency.** Ví dụ Spring Security/Quarkus security hỗ trợ xây cơ chế auth, nhưng application vẫn phải cấu hình đúng provider, trust, resource-level authorization, token/audience/issuer, audit và secrets. Reverse proxy cũng không thay business authorization.

### 6.1. CORS và CSRF không phải authentication

- **CORS** chủ yếu là cơ chế browser hạn chế origin của JavaScript request/response; nó **không ngăn một HTTP client không phải browser gửi request**.
- **CSRF** liên quan request lợi dụng credentials browser tự gửi (ví dụ cookie), phải có cơ chế chống riêng.
- **Authentication** xác định ai là người dùng/client.
- **Authorization** xác định client đó được phép thao tác **resource cụ thể nào**.

Đừng bật `Access-Control-Allow-Origin: *` rồi cho rằng API đã an toàn. Ngược lại, không thêm CORS cũng không làm một public HTTP endpoint tự chặn người dùng ngoài browser.

### 6.2. TLS kết thúc ở proxy có giải quyết mọi thứ?

Reverse proxy/gateway có thể đảm nhiệm edge TLS termination, HTTP/2 phía client, rate limiting, authentication ở một tầng hoặc request-size limits. Nhưng một backend HTTP server vẫn phải:

- Kiểm tra business authorization.
- Phân biệt trusted proxy headers với header client có thể giả.
- Có connection/request timeouts riêng.
- Giữ dữ liệu nhạy cảm an toàn trên mạng nội bộ nếu threat model yêu cầu mTLS.
- Không giả định TLS termination giải quyết WebSocket/streaming protocol nếu backend API không hỗ trợ.
- Bảo vệ các endpoint bypass gateway, ví dụ không bind thêm public port.
- Có readiness, deployment/rollback và monitoring.

Nếu yêu cầu là **HTTP/2 end-to-end tới application**, edge HTTP/2 và backend HTTP/1.1 **không tương đương**. Nếu yêu cầu là WebSocket semantics phía backend, JDK minimal `HttpServer` API không có một WebSocket endpoint abstraction chỉ bằng `createContext`.

## 7. Các yêu cầu giao thức/phương tiện cần đánh giá stack

| Nhóm | Ví dụ nhu cầu | Câu hỏi ra quyết định |
| --- | --- | --- |
| JSON REST API | DTO validation, content negotiation, OpenAPI, structured errors. | Tự xây middleware/DTO + tests ít hơn dùng một framework không? |
| Multipart/file uploads | Streaming GB files, checksum, resume, antivirus scanning. | Parser/quota/timeout/streaming ownership ở đâu? |
| Long-lived streaming | SSE hoặc responses dài. | Executor, cancellation, proxy buffering, keepalive, reconnection đã test? |
| WebSocket | Bidirectional frames, ping/pong, subprotocols. | Cần WebSocket server implementation thực, không chỉ chunked HTTP body? |
| HTTP/2 | Multiplexing/server push semantics theo use case. | Chỉ cần edge HTTP/2 hay backend phải native H2? |
| gRPC | HTTP/2 framing, Protobuf, bi-directional streams. | Cần gRPC server stack thay vì một HttpHandler đơn giản? |
| API gateways | Global auth/routing/rate limits. | Gateway độc lập có phù hợp hay quá nặng cho localhost app? |
| Static files | Cache, ETag, Range, MIME, path security. | `SimpleFileServer`/`jwebserver` dùng cho dev/test; production cần giải pháp phù hợp? |

`SimpleFileServer` và `jwebserver` trong module `jdk.httpserver` là công cụ phục vụ tệp đơn giản cho development/debugging. **Không nên tự suy ra đây là CDN hoặc hardened static asset server**.

## 8. Khả năng chịu tải: đo trước khi chọn

Một dự án có 2 endpoints cũng có thể nhận rất nhiều requests; một dự án 100 endpoints có thể gần như không có lưu lượng. Vì vậy, **số route không phải proxy đáng tin của tải**.

Các thông số phải biết:

- **RPS/QPS mục tiêu**: trung bình, peak và burst.
- **p50/p95/p99 latency**: bao gồm timeouts của backend dependencies.
- **Concurrent requests/connections**: active, idle, streaming và keep-alive.
- **Payload sizes**: p50/p99/max cho cả request và response.
- **SLO/error budget**: availability, timeout ratio, error rate và recovery time.
- **Backpressure**: khi executor/queue/connection limit chạm ngưỡng, trả gì thay vì làm nghẽn JVM?
- **Heap/GC/CPU**: theo tải thực, không dựa vào “JDK server nhẹ” như một lời đảm bảo.

### 8.1. Backlog không phải giới hạn concurrency

`HttpServer.create(address, backlog)` dùng `backlog` cho **hàng đợi TCP connections chờ accept**. Nó không phải kích thước thread pool, giới hạn request body hay số HTTP requests tối đa.

`setExecutor(executor)` dispatch handler tasks. Với `Executors.newFixedThreadPool(4)`, số worker threads thường là 4 nhưng hàng đợi tasks của executor mặc định có thể **không giới hạn**. Nếu hệ thống cần overload policy nghiêm ngặt, hãy thiết kế bounded queue, rejection strategy và connection limits thay vì chỉ thay số thread.

### 8.2. Little's law chỉ là công cụ ước lượng

Trong trạng thái tương đối ổn định, số requests đang hoạt động gần đúng:

```text
concurrency ≈ throughput (requests/second)
              × average response time (seconds)
```

Ví dụ **giả định**: 200 requests/second với trung bình 0,25 giây thì có khoảng 50 requests concurrent trong hệ thống. Đây không phải phép đo thực tế của server demo; không dùng nó làm kích thước queue cuối cùng. Peak bursts, p99 latency, long-held connections và downstream blocking cần đo riêng.

### 8.3. Benchmark phải test công việc thật

Đừng chỉ benchmark `GET /health` rồi tuyên bố server đủ cho upload lớn, database transactions hay OIDC security. So sánh phương án với **cùng application logic** và có:

1. Workload profiles (read/write, sizes, auth, dependencies).
2. Ramp-up, steady state, peak and burst.
3. p95/p99 latency và timeouts.
4. CPU/heap/GC/thread/connection metrics.
5. Failure injection: downstream slow/unavailable, client disconnect, malformed bodies.
6. Recovery time, resource cleanup và graceful stop.
7. Reproducibility: JDK/provider version, host resources, server/gateway configuration.

Kết luận chỉ có giá trị cho **workload và môi trường được đo**. Không suy rộng một số benchmark trên máy tính cá nhân cho production.

## 9. Observability, lifecycle và vận hành lâu dài

Một service production cần hơn `System.out.println("request")`:

| Khía cạnh | Việc cần đảm nhận | Tín hiệu nghiêng về ecosystem/framework |
| --- | --- | --- |
| Structured logging | Request ID, outcome, status, redaction, sampling. | Nhiều teams/correlation xuyên services. |
| Metrics | RPS, error rate, latency, saturation, JVM, queue. | SLO/alerting cần exporters và dashboards. |
| Distributed tracing | Trace/span propagation, downstream timing. | Nhiều services/data stores. |
| Health/readiness | Phân biệt app sống và sẵn sàng nhận traffic. | Orchestrator rolling deploy, traffic gating. |
| Graceful shutdown | Stop accept, drain in-flight, close pools. | Zero-downtime rollout, long-lived requests. |
| Security patching | JDK, framework, libraries, TLS, certificates. | Nhiều dependencies/cert rotation. |
| Configuration | Typed config, secret injection, feature flags. | Nhiều environments/tenants. |
| Error handling | Mapping exception → safe 4xx/5xx, retry IDs. | API contract và audit. |

Spring Boot có **Actuator** cung cấp một hệ sinh thái health/metrics/management endpoints; đó là một **khả năng có điều kiện và phải cấu hình**, không phải bảo đảm tự động sau khi import Spring. Các endpoint quản trị có thể nhạy cảm nên phải hạn chế exposure/authorization. Quarkus có hệ sinh thái REST, security và observability khác; hãy đánh giá yêu cầu/skillset trước khi chọn.

### 9.1. JDK 26 thay đổi phạm vi HttpExchange attributes

Theo JDK 26 module docs, **trước JDK 26** trong default implementation, `HttpExchange` attributes được dùng chung với `HttpContext`. Từ JDK 26, **mặc định là per-exchange**. Dùng `exchange.getHttpContext().getAttributes()` nếu muốn config/state chia sẻ ở cấp context; dùng `exchange.setAttribute/getAttribute` cho metadata của từng exchange.

System property `jdk.httpserver.attributes=context` khôi phục hành vi cũ trên default provider. Đây là compatibility switch, **không phải khuyến nghị cho code mới**. Một phần trong việc giới hạn scope là kiểm thử behavior khi nâng JDK/provider, thay vì vô tình chia sẻ trạng thái giữa các requests.

## 10. Ba phương án kiến trúc đáng cân nhắc

Không nên đặt câu hỏi đơn giản “JDK hay Spring?” trước khi biết requirements. Có ít nhất ba phương án:

### 10.1. Phương án A — JDK HttpServer tối giản

```text
localhost / isolated internal client
             |
             v
     JDK HttpServer
        + contexts
        + simple handlers
        + explicit limits
             |
             v
        domain service
```

**Phù hợp khi:** ít endpoints cố định; mục đích internal/dev/test; không cần giao thức nâng cao; security surface giới hạn; nhóm sẵn sàng kiểm tra method/input/close/timeout.

**Rủi ro:** team dần tự xây router, auth, tracing, body parsing, configs thành một framework không chính thức.

### 10.2. Phương án B — JDK HttpServer sau gateway

```text
external clients
      |
      v
trusted gateway / reverse proxy
  TLS, request limits, coarse auth,
  rate limits, logging policies
      |
      v
JDK HttpServer trên mạng/private interface
  exact paths, application authZ,
  bounded work, health/metrics
      |
      v
domain service
```

**Phù hợp khi:** business logic còn đơn giản nhưng requirements của edge lớn hơn capabilities HTTP server. Cần **đánh giá thực tế** rằng gateway không để lộ backend port, chính sách header/trust nhất quán và back-end business authorization vẫn đúng.

**Rủi ro:** tưởng gateway giải quyết hết; backend còn rủi ro với uploads, memory, deadlines, error handling hoặc bypass paths.

### 10.3. Phương án C — Framework hoặc server stack đầy đủ

```text
clients / gateway
       |
       v
full web/server stack
 routing, validation, security,
 serialization, middleware,
 telemetry and lifecycle
       |
       v
domain/application services
       |
       v
DB, queue, external APIs
```

**Phù hợp khi:** API nhiều nghiệp vụ, OpenAPI/DTO validation, OIDC/RBAC, multi-tenant, message integrations, operational SLO cao, client protocol constraints, hoặc nhu cầu nhiều team cùng duy trì.

**Rủi ro:** dependency surface, framework upgrades, magic auto-configuration, startup/runtime footprint, training và security configuration complexity. **Một framework có nhiều tính năng không đồng nghĩa nó tự đạt SLO và security policy.**

## 11. Chọn framework theo loại yêu cầu, không theo tên tuổi

Các ví dụ **hiện hành** trong Java ecosystem:

| Hướng | Đặc điểm cần đánh giá | Không nên suy ra |
| --- | --- | --- |
| **Spring Boot MVC** | Web MVC, embedded server, ecosystem data/security, REST API, Actuator. | Mọi application đều cần Spring hoặc tự an toàn ngay. |
| **Spring WebFlux** | Reactive HTTP model cho use cases phù hợp; ecosystem Spring. | Cứ cần hiệu năng cao là phải reactive hoặc mọi I/O đều nonblocking. |
| **Quarkus REST** | Jakarta REST style, Vert.x-based REST layer, build-time integration. | Mọi code JDBC/blocking chạy trong event loop đều không ảnh hưởng throughput. |
| **Jakarta REST trong server hỗ trợ** | Chuẩn API cho REST resources và provider integration. | Một API specification tự bao gồm HTTP server/operations. |
| **Netty, Jetty và server libraries** | Cấu hình network/HTTP stack ở mức khác, có thể xây app tùy biến. | Có sẵn tất cả business validations, auth và metrics không cần tích hợp. |
| **JDK HttpServer** | Dependency tối thiểu, controls hiển thị rõ. | Là drop-in replacement của enterprise web framework. |

Tại thời điểm đánh giá, hãy xem **tài liệu của đúng phiên bản hiện hành** tương thích với JDK mục tiêu, hệ sinh thái bảo mật/observability, lifecycle support và khả năng nâng cấp. Không pin một phiên bản framework trong README khi không có yêu cầu phiên bản hoặc môi trường triển khai cụ thể.

### 11.1. Spring Boot MVC vs WebFlux: đừng chọn reactive theo cảm tính

Nếu service chủ yếu làm blocking JDBC/legacy SDK calls, một pipeline reactive không tự biến các operations đó thành nonblocking. Khi chọn WebFlux/Quarkus reactive cần hiểu event-loop vs worker threads, backpressure, request cancellation và blocking isolation.

Với một API CRUD có security/validation/transaction thông thường, Spring Boot MVC có thể là lựa chọn dễ quản lý hơn; với high-concurrency streaming và nonblocking dependencies, một reactive model có thể đáng benchmark. **Đây là giả thuyết kỹ thuật cần kiểm tra theo workload, không phải kết quả benchmark được công bố trong bài này.**

### 11.2. Gateway vs framework không cùng một bài toán

Gateway có thể giúp:

- TLS termination và coarse-grained edge policies.
- HTTP/2 phía client trong khi backend dùng HTTP/1.1 nếu protocol requirement cho phép.
- Routing nhiều services, basic rate limits, API keys và request budgets.
- Centralized access logs.

Framework có thể giúp:

- Request/DTO validation, handler/controller structure.
- Application authN/authZ, security policy integration.
- Transaction boundaries, structured API errors.
- Observability ở tầng business/dependencies.

Hai giải pháp có thể **bổ sung** nhau. Không chọn gateway để thay toàn bộ domain validation; không chọn framework để khỏi phải làm network security.

## 12. Quy trình quyết định trước khi viết framework dependency

Một quyết định có thể lặp lại và review được nên có bảy bước:

**Bước 1 — Định nghĩa ranh giới.** Viết danh sách endpoints, clients, dữ liệu nhạy cảm, protocol và deployment environment. Đừng mở rộng scope sang “chúng ta sẽ xây mọi thứ sau này” khi chưa có yêu cầu.

**Bước 2 — Xác định must-have.** Chọn rõ các hard requirements như HTTP/2 end-to-end, WebSocket, OIDC/RBAC, OpenAPI validation, multipart streaming, audit retention, SLO, compliance. Một hard requirement có thể khiến minimal server không phải lựa chọn tốt dù chỉ có một endpoint.

**Bước 3 — Phân tầng trách nhiệm.** Đánh dấu cái gì JDK có, cái gì gateway có thể cung cấp, cái gì application phải làm và cái gì framework tích hợp. Có một người/team làm owner cho từng phần.

**Bước 4 — Chọn một baseline tối giản.** Tạo proof-of-concept bằng `HttpServer` với input/output tests thật. Không cần framework khi baseline đã thỏa requirements đã kiểm chứng.

**Bước 5 — So sánh ít nhất một alternative.** Nếu scope vượt baseline, dựng một endpoint tương đương bằng framework/server candidate, giữ cùng domain logic. Đo complexity và failure modes, không chỉ hello-world latency.

**Bước 6 — Đặt exit criteria.** Ví dụ “p99 dưới X ms với Y RPS, 95% requests dưới Z bytes, authZ theo tenant được test, 0 unauthorized file reads, alerts có owner”; **X/Y/Z phải do sản phẩm xác định**, không dùng số giả định từ bài này.

**Bước 7 — Quyết định và lưu ADR.** Ghi scope, assumptions, options, bằng chứng, trade-offs, rollback, migration triggers và thời điểm đánh giá lại. Khi yêu cầu mới xuất hiện, update ADR thay vì vô hạn mở rộng server tự chế.

### 12.1. Không dùng một điểm số giả để hợp thức hóa quyết định

Không có một công thức `if (routes > 10) useFramework()` đáng tin cậy cho mọi dự án. Số route là một tín hiệu quản lý complexity, nhưng **dữ liệu, security, protocols và reliability** còn quan trọng hơn.

Bài demo đầu dùng **explicit needs** và đưa ra **một gợi ý đánh giá**, không phải kết luận framework bắt buộc. Đây là cách biến quyết định thành danh sách giả định kiểm thử được.

## 13. Chương trình 1: ScopeGateDemo.java — quyết định dựa trên yêu cầu rõ ràng

Chương trình này **không cần chạy HTTP server**. Nó dùng Java 17 `record` và `enum` để minh họa cách làm scope review thành dữ liệu rõ ràng. Không có external dependencies. Nó cố ý phân ra ba mức:

- `JDK_CANDIDATE`: use case local nhỏ, chưa có tín hiệu đòi hỏi stack lớn.
- `JDK_WITH_EXPLICIT_GUARDS`: use case nằm trên trusted network; vẫn cần auth, network policies, limits và monitoring cụ thể.
- `EVALUATE_STACK`: có yêu cầu mà team cần **đánh giá** framework/server/gateway tương ứng, **không có nghĩa Java minimal server không thể đáp ứng bằng custom code**.

### 13.1. Source đầy đủ

**Tệp: `ScopeGateDemo.java`**

```java
import java.util.EnumSet;
import java.util.Set;
import java.util.stream.Collectors;

public final class ScopeGateDemo {
    enum Need {
        LOCAL_ONLY, FIXED_FEW_ROUTES, TRUSTED_NETWORK, BOUNDED_PAYLOADS,
        IDENTITY_RBAC, OPENAPI_CONTRACT, DISTRIBUTED_TRACING,
        WEBSOCKET, HTTP2_END_TO_END, LARGE_UPLOAD_STREAMING, HIGH_SLA
    }
    record Profile(String name, Set<Need> needs) {}
    enum Verdict {
        JDK_CANDIDATE, JDK_WITH_EXPLICIT_GUARDS, EVALUATE_STACK
    }

    private static final EnumSet<Need> ADVANCED = EnumSet.of(
            Need.IDENTITY_RBAC, Need.OPENAPI_CONTRACT, Need.DISTRIBUTED_TRACING,
            Need.WEBSOCKET, Need.HTTP2_END_TO_END,
            Need.LARGE_UPLOAD_STREAMING, Need.HIGH_SLA);

    static Verdict assess(Profile profile) {
        if (profile.needs().stream().anyMatch(ADVANCED::contains)) {
            return Verdict.EVALUATE_STACK;
        }
        if (profile.needs().contains(Need.TRUSTED_NETWORK)) {
            return Verdict.JDK_WITH_EXPLICIT_GUARDS;
        }
        return Verdict.JDK_CANDIDATE;
    }

    static String advancedReasons(Profile profile) {
        return profile.needs().stream()
                .filter(ADVANCED::contains)
                .map(Enum::name)
                .sorted()
                .collect(Collectors.joining(","));
    }

    private static void check(
            Profile profile, Verdict expected, String reasons) {
        Verdict actual = assess(profile);
        if (actual != expected
                || !advancedReasons(profile).equals(reasons)) {
            throw new AssertionError(profile.name() + " " + actual + " "
                    + advancedReasons(profile));
        }
        System.out.println(profile.name() + "=" + actual
                + (reasons.isEmpty() ? "" : "|" + reasons));
    }

    public static void main(String[] args) {
        check(new Profile("local_probe", EnumSet.of(
                Need.LOCAL_ONLY, Need.FIXED_FEW_ROUTES)),
                Verdict.JDK_CANDIDATE, "");
        check(new Profile("internal_tool", EnumSet.of(
                Need.FIXED_FEW_ROUTES,
                Need.TRUSTED_NETWORK, Need.BOUNDED_PAYLOADS)),
                Verdict.JDK_WITH_EXPLICIT_GUARDS, "");
        check(new Profile("public_api", EnumSet.of(
                Need.IDENTITY_RBAC,
                Need.OPENAPI_CONTRACT, Need.DISTRIBUTED_TRACING)),
                Verdict.EVALUATE_STACK,
                "DISTRIBUTED_TRACING,IDENTITY_RBAC,OPENAPI_CONTRACT");
        check(new Profile("realtime_product", EnumSet.of(
                Need.WEBSOCKET, Need.HTTP2_END_TO_END, Need.HIGH_SLA)),
                Verdict.EVALUATE_STACK,
                "HIGH_SLA,HTTP2_END_TO_END,WEBSOCKET");
        System.out.println("scopeChecks=4/4");
    }
}
```

### 13.2. Biên dịch/chạy

```bash
javac --release 17 -encoding UTF-8 ScopeGateDemo.java
java ScopeGateDemo
```

**Stdout chính xác đã kiểm chứng trên JDK 24:**

```text
local_probe=JDK_CANDIDATE
internal_tool=JDK_WITH_EXPLICIT_GUARDS
public_api=EVALUATE_STACK|DISTRIBUTED_TRACING,IDENTITY_RBAC,OPENAPI_CONTRACT
realtime_product=EVALUATE_STACK|HIGH_SLA,HTTP2_END_TO_END,WEBSOCKET
scopeChecks=4/4
```

### 13.3. Giải thích và giới hạn

**`local_probe`** chỉ dùng localhost và ít routes, là ứng viên cho JDK minimal server. Kết quả không đồng nghĩa service đã sẵn sàng phơi public Internet.

**`internal_tool`** vẫn có network clients (dù thuộc môi trường tin cậy) nên cần guardrails riêng: network access control, authentication phù hợp, body quotas, timeouts, logging. “Trusted network” **không có nghĩa “mọi request đáng tin”**.

**`public_api`** yêu cầu identity/RBAC, API contract và distributed tracing nên phải đánh giá stack hỗ trợ. Có thể chọn framework hoặc combination của gateway + application, nhưng không nên tự coi một handler ngắn đã hoàn thành ba requirements đó.

**`realtime_product`** có WebSocket, HTTP/2 end-to-end và SLO cao. Default JDK `HttpServer` không phải nơi có sẵn một protocol stack như thế, nên cần một evaluation cụ thể.

**`EVALUATE_STACK` không tự chọn Spring/Quarkus/Netty hoặc kết luận benchmark.** Rule này chỉ là ví dụ về **scope-gating process**. Nếu sản phẩm thực có use case khác, thay `Need`/criteria và thêm cost/operational evidence; đừng copy classifier như một policy công ty bất biến.

## 14. Chương trình 2: HttpBoundaryProbeDemo.java — chứng minh phạm vi JDK bằng HTTP thật

Chương trình này dùng **`HttpServer` và `HttpClient` đều có sẵn trong JDK 17+**. Nó chỉ mở HTTP socket ở **loopback**, OS tự chọn port, không kết nối Internet. Nó cố ý giới hạn business scope:

- `GET /health` trả một plain-text UTF-8 status.
- `POST /api/echo` nhận tối đa **32 bytes** cho demo và echo lại.
- Các paths khác trả 404.
- HTTP method sai trả 405 và header `Allow: POST`.
- Chặn literal prefix trap như `/healthcheck` hoặc `/api/echoExtra` bằng exact raw path check.
- Có timeout ở client, executor 2 threads, shutdown trong `finally`.
- Không giả vờ có JSON mapping, auth, OpenAPI, WebSocket hoặc distributed tracing.

### 14.1. Source đầy đủ

**Tệp: `HttpBoundaryProbeDemo.java`**

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
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
import java.util.concurrent.TimeUnit;

public final class HttpBoundaryProbeDemo {
    private static final int MAX_INPUT_BYTES = 32;

    static void reply(HttpExchange e, int code, String text) throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        e.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        e.getResponseHeaders().set("X-Content-Type-Options", "nosniff");
        e.sendResponseHeaders(code, data.length == 0 ? -1 : data.length);
        try (var out = e.getResponseBody()) {
            out.write(data);
        }
    }

    static boolean method(HttpExchange e, String expected) throws IOException {
        if (expected.equals(e.getRequestMethod())) return true;
        e.getResponseHeaders().set("Allow", expected);
        reply(e, 405, "method-not-allowed");
        return false;
    }

    static void health(HttpExchange e) throws IOException {
        try (e) {
            if (!"/health".equals(e.getRequestURI().getRawPath())) {
                reply(e, 404, "path-not-found");
            } else if (method(e, "GET")) {
                reply(e, 200, "sẵn-sàng");
            }
        }
    }

    static void echo(HttpExchange e) throws IOException {
        try (e) {
            if (!"/api/echo".equals(e.getRequestURI().getRawPath())) {
                reply(e, 404, "path-not-found");
                return;
            }
            if (!method(e, "POST")) return;
            byte[] content;
            try (var input = e.getRequestBody()) {
                content = input.readNBytes(MAX_INPUT_BYTES + 1);
            }
            if (content.length > MAX_INPUT_BYTES) {
                reply(e, 413, "payload-too-large");
            } else {
                reply(e, 200, "echo:"
                        + new String(content, StandardCharsets.UTF_8));
            }
        }
    }

    static void noRoute(HttpExchange e) throws IOException {
        try (e) {
            reply(e, 404, "path-not-found");
        }
    }

    static HttpResponse<String> get(
            HttpClient client, String base, String path) throws Exception {
        return client.send(HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(5)).GET().build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    static HttpResponse<String> post(HttpClient client, String base,
                                     String path, String body)
            throws Exception {
        return client.send(HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(5))
                .POST(HttpRequest.BodyPublishers.ofString(
                        body, StandardCharsets.UTF_8)).build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    static void check(String label, int code, String text,
                      HttpResponse<String> response) {
        if (response.statusCode() != code || !text.equals(response.body())) {
            throw new AssertionError(label + " expected=" + code + "|"
                    + text + ", got=" + response.statusCode()
                    + "|" + response.body());
        }
        System.out.println(label + "=" + code + "|" + text);
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        server.setExecutor(executor);
        server.createContext("/health", HttpBoundaryProbeDemo::health);
        server.createContext("/api/echo", HttpBoundaryProbeDemo::echo);
        server.createContext("/", HttpBoundaryProbeDemo::noRoute);
        try {
            server.start();
            String base = "http://localhost:" + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(5)).build();
            check("health", 200, "sẵn-sàng",
                    get(client, base, "/health"));
            check("healthQuery", 200, "sẵn-sàng",
                    get(client, base, "/health?format=text"));
            check("literalPrefix", 404, "path-not-found",
                    get(client, base, "/healthcheck"));
            check("caseSensitive", 404, "path-not-found",
                    get(client, base, "/HEALTH"));
            check("echoUnicode", 200, "echo:Chào 😀",
                    post(client, base, "/api/echo", "Chào 😀"));
            check("inputLimit", 413, "payload-too-large",
                    post(client, base, "/api/echo", "a".repeat(33)));
            check("echoPrefix", 404, "path-not-found",
                    post(client, base, "/api/echoExtra", "x"));
            HttpResponse<String> badMethod = get(client, base, "/api/echo");
            check("wrongMethod", 405, "method-not-allowed", badMethod);
            if (!"POST".equals(
                    badMethod.headers().firstValue("Allow").orElse(""))) {
                throw new AssertionError("Missing Allow header");
            }
            System.out.println("allowHeader=PASS");
            check("unknownRoute", 404, "path-not-found",
                    get(client, base, "/api/missing"));
            System.out.println("httpChecks=10/10");
        } finally {
            server.stop(0);
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

### 14.2. Biên dịch/chạy

```bash
javac --release 17 -encoding UTF-8 HttpBoundaryProbeDemo.java
java HttpBoundaryProbeDemo
```

**Stdout chính xác đã kiểm chứng trên JDK 24:**

```text
health=200|sẵn-sàng
healthQuery=200|sẵn-sàng
literalPrefix=404|path-not-found
caseSensitive=404|path-not-found
echoUnicode=200|echo:Chào 😀
inputLimit=413|payload-too-large
echoPrefix=404|path-not-found
wrongMethod=405|method-not-allowed
allowHeader=PASS
unknownRoute=404|path-not-found
httpChecks=10/10
```

**10 kiểm tra HTTP thực tế PASS** và một dòng tổng kết, tổng cộng **11 dòng stdout**. Client gửi HTTP requests qua loopback đến server cùng process; không có Internet traffic, database hoặc framework dependency. Đã biên dịch thành công `--release 17` và chạy trên JDK 24.

### 14.3. Kết quả này chứng minh điều gì — và không chứng minh điều gì?

**Có chứng minh:**

- JDK server tạo contexts và trả response thật.
- Literal prefix trap cần exact-path validation.
- Query không thay đổi context matching.
- Path matching phân biệt hoa/thường.
- HTTP response body Unicode được encode UTF-8 đúng số bytes.
- Handler có thể chặn body quá 32 bytes và trả 413.
- Method sai nhận 405 và header Allow.
- Server/executor được dọn trong `finally`.

**Không chứng minh:**

- Đã có authentication/authorization an toàn.
- Chống được mọi path normalization/encoded slash attack.
- Hỗ trợ HTTP/2/WebSocket.
- Thỏa p95/p99/SLO cụ thể.
- Chống được DDoS, long-lived uploads, slowloris hoặc request smuggling.
- Có comprehensive tracing, metrics, dashboards và alerting.
- Đủ triển khai Internet-facing production system.

Điểm giá trị của demo là **cho thấy sự chênh lệch giữa một endpoint hoạt động và một production-ready API**. Khi scope tăng, một tập hợp controls mới sẽ phải được thiết kế hoặc nhận từ ecosystem.

## 15. Kế hoạch nâng cấp mà không khóa chặt business logic

Đừng đặt toàn bộ nghiệp vụ vào `HttpHandler.handle`:

```java
// Anti-pattern minh họa:
// Handler vừa parse JSON, validate user, query database,
// áp quy tắc giảm giá, gửi email, retry và serialize response.
server.createContext("/orders", exchange -> {
    // Hàng trăm dòng business + HTTP bị trộn lẫn.
});
```

Mảnh code trên là một anti-pattern minh họa, không phải chương trình chạy độc lập. Khi chuyển framework, bạn sẽ phải viết lại business logic hoặc giữ handler class phụ thuộc HTTP.

Thay vào đó, tổ chức:

```text
domain/
  Order.java
  PriceRule.java
application/
  OrderService.java          <- không import com.sun.net.httpserver
  OrderRepository.java       <- interface
adapters/
  http-jdk/
    OrderHttpHandler.java    <- decode/validate/request/response
  http-framework/
    OrderController.java     <- adapter thay thế được về sau
infrastructure/
  OrderRepositoryJdbc.java   <- DB implementation
```

Đây là **sơ đồ kiến trúc**, không phải danh sách tệp repo của người dùng. Hãy giữ domain/application methods nhận typed inputs và trả typed outputs hoặc results/errors độc lập khỏi `HttpExchange`. Khi chuyển sang Spring/Quarkus/Jakarta REST, phần adapter HTTP đổi nhưng quy tắc business có thể giữ lại.

### 15.1. “Strangler” migration từng endpoint

Nếu một server JDK hiện tại đã lớn hơn phạm vi:

1. Đóng băng API contract và status/error semantics ở từng route.
2. Viết integration tests bằng `HttpClient`/contract tests.
3. Tách business service, repository và transport parsing.
4. Dựng application mới cho route phức tạp trước.
5. Gateway route một phần endpoints sang stack mới, phần còn lại tạm ở JDK server.
6. Theo dõi latency/error rates, so sánh response semantics, có rollback.
7. Chuyển thêm routes theo capability/owner, không big-bang rewrite khi không cần.
8. Loại bỏ custom middleware khi framework đã thay thế, tránh hai nơi xác thực/log.

Đừng duy trì hai hệ thống auth/permission với kết quả khác nhau khi migration: contract/authorization consistency phải được test trước khi chia traffic.

## 16. Ước tính chi phí sở hữu thay vì đoán “nhẹ” hay “nặng”

So sánh **total cost of ownership (TCO)**:

```text
TCO = chi phí xây dựng
    + chi phí kiểm thử bảo mật
    + chi phí vận hành/quan sát
    + chi phí nâng cấp dependencies
    + chi phí đào tạo/team handoff
    + chi phí sự cố và migration về sau
```

Trong project nhỏ, dependency tối thiểu của JDK HttpServer có thể làm TCO thấp. Trong project nhiều API/public clients, tự viết JWT/Jackson-style binding, RBAC, OpenAPI, validation, observability, retries và middleware có thể làm TCO rất cao.

Ngược lại, chọn framework lớn cho đúng một health check có thể thêm:

- Build plugins, BOM/dependency management.
- Security/actuator/configuration defaults cần kiểm tra.
- Framework upgrade cadence và vulnerability scans.
- Memory/startup footprint (cần đo thực tế, không chỉ dự đoán).
- Team-specific operational knowledge.

**Không có đáp án phổ quát.** Dùng một ADR nhỏ với giả định kiểm chứng được sẽ có giá trị hơn một danh sách “framework X nhanh nhất”.

## 17. Ma trận ra quyết định để copy vào ADR

Đặt *mỗi hàng* thành một câu hỏi có owner và bằng chứng:

| Tiêu chí | Dữ liệu cần thu thập | Khi nào cần đánh giá framework/server? |
| --- | --- | --- |
| Scope API | Số routes, phương thức, schema, versioning, contracts. | Nhiều route constraints/DTO/error rules và phát sinh duplication. |
| Giao thức | HTTP/1.1, HTTP/2, WebSocket, SSE, gRPC. | Cần native protocol support mà JDK minimal API không cung cấp. |
| Security | AuthN/authZ, tokens, tenant isolation, CORS/CSRF. | Security logic phức tạp, có compliance/audit/identity integration. |
| Dữ liệu | JSON, multipart, large files, transaction boundaries. | Parser/validation/streaming tự viết lớn hoặc có nhiều edge cases. |
| Tải | RPS, peak, p95/p99, concurrency, max payload. | PoC cho thấy saturation/latency vượt SLO. |
| Vận hành | Metrics/tracing/probes/shutdown/deployment. | Đòi hỏi lifecycle và instrumentation chuẩn hóa. |
| Nhân sự | Team skillset, on-call, số team đóng góp. | Ownership và review custom framework không bền vững. |
| Phụ thuộc | Licenses, CVEs, support window, upgrade policy. | Chi phí tự quản lý hoặc framework candidates được đánh giá. |
| Đường quay lại | Endpoint contract, migration/rollback. | Khi cần thay transport mà không viết lại domain. |

**Không mặc định đặt deadline hoặc một ngưỡng số liệu khi chưa có product context**. Trong ADR, ghi nguồn đo, sample size, load profile, cloud/VM spec và ngày review.

### 17.1. Ví dụ ADR ngắn

```text
Decision: GIỮ JDK HttpServer cho diagnostic loopback.
Scope: GET /health và GET /info, không nhận dữ liệu người dùng.
Constraints: bind loopback; giới hạn request length; không public.
Security: no user credentials, no sensitive body; patch JDK định kỳ.
Operations: log trạng thái, stop trong shutdown hook, test endpoint CI.
Trigger evaluate: thêm public clients, user auth, uploads, WebSocket,
                  OpenAPI contract hoặc SLO cần multi-replica operation.
Alternatives: JDK + gateway; Spring Boot MVC; Quarkus REST.
Evidence: JDK17 integration tests, threat model, measured peak load.
Review: sau thay đổi scope hoặc security requirements.
```

Đây là **mẫu quyết định**, không phải một quyết định đã được thực hiện cho hệ thống cụ thể.

## 18. Những lỗi tư duy thường gặp

| Sai lầm | Tại sao sai | Phản ứng đúng |
| --- | --- | --- |
| “JDK có HttpServer nên chắc đủ production” | API tối giản, thiếu nhiều integration/default controls. | Xác định SLO/security/operability trước. |
| “HttpServer bị legacy” | API công khai còn hỗ trợ trong JDK hiện hành. | Dùng đúng nơi nó phù hợp. |
| “Ít endpoint nên an toàn” | Một endpoint upload/auth sai vẫn có thể rủi ro lớn. | Đánh giá data và trust boundaries. |
| “Nhiều endpoint bắt buộc Spring” | Số endpoint không tự quyết định. | Đo complexity/ops và use case. |
| “Đặt backlog=100 là nhận được 100 concurrent requests” | Backlog là TCP accept queue. | Thiết kế executor/backpressure riêng. |
| “Sử dụng virtual threads sẽ tự hỗ trợ HTTP/2” | Threads và protocol implementation khác nhau. | Chọn protocol stack đúng yêu cầu. |
| “Gateway có auth thì backend không cần kiểm tra quyền” | Resource/tenant authorization là business concern. | Kiểm tra ở backend đúng dữ liệu. |
| “CORS đã chặn tất cả clients lạ” | CORS là browser policy, không phải auth. | Có authentication/network controls. |
| “WebSocket chỉ là HTTP body stream” | Upgrade/framing/ping-pong/subprotocols riêng. | Server hỗ trợ WebSocket thật. |
| “HttpClient có HTTP/2 nên HttpServer cũng có” | `java.net.http.HttpClient` là **client**, không chứng minh server stack. | Đọc server API/protocol support. |
| “Router `/api` chỉ nhận `/api/...`” | Literal prefix cũng match `/api2`. | Segment boundary/exact validation. |
| “HTTP framework tự xử lý input size và rate limit cho mọi endpoint” | Defaults/config thay đổi theo stack; có thể chưa đủ. | Kiểm chứng quotas và abuse tests. |
| “Dùng Spring/Quarkus = không cần threat model” | Security misconfiguration vẫn xảy ra. | Threat model, tests, patches, audit. |
| “Thấy benchmark hello-world nhanh thì đã đủ SLO” | Workload business khác. | Benchmark dữ liệu và failure modes thực. |
| “Cần framework thì viết lại toàn bộ domain” | Transport không nên ràng buộc business logic. | Adapter boundary/migration từng route. |
| “Đổi framework sẽ tự chữa DB bottleneck” | Bottleneck có thể ở DB/network/serialization. | Profile end-to-end trước. |
| “Dùng OpenAPI nghĩa chỉ thêm file YAML” | Phải giữ contract validation/versioning thật. | Consumer-driven tests và schema ownership. |
| “Dùng HTTPS là xong auth” | TLS encryption khác user identity/RBAC. | Xây authN/authZ theo business. |
| “Health endpoint trả 200 nghĩa service ready” | Dependencies/state có thể chưa sẵn sàng. | Tách liveness/readiness theo SLO. |
| “Framework startup nhiều RAM chắc chắn tệ hơn tự viết” | Chi phí phải đo theo constraints thực. | So benchmark/ops TCO. |

## 19. Checklist cuối trước khi chốt công nghệ

- [ ] Đã viết rõ scope và out-of-scope?
- [ ] Đã xác định clients/trust boundary và data classification?
- [ ] Đã xác nhận protocol requirements: HTTP/1.1, HTTP/2, WebSocket, gRPC, SSE?
- [ ] Đã có API contract, validation và error model?
- [ ] Đã xác định authN/authZ, tenant isolation và TLS requirements?
- [ ] Đã có request/response size budgets, timeouts và rate limits?
- [ ] Đã chọn metrics/trace/logging/health/readiness cần thiết?
- [ ] Đã đo expected workload và xác định SLO/p99/failure budget?
- [ ] Đã chứng minh default JDK HttpServer phù hợp/không phù hợp cho use case đó?
- [ ] Đã phân biệt edge-gateway responsibilities với app business responsibilities?
- [ ] Đã xem khả năng của ít nhất một framework/server candidate nếu scope phức tạp?
- [ ] Đã kiểm tra version compatibility/JDK/provider/security advisories?
- [ ] Đã tránh dùng số routes làm quy tắc duy nhất?
- [ ] Đã có PoC/benchmark với cùng domain workload và representative traffic?
- [ ] Đã xử lý overload, graceful shutdown, client disconnect và IO cleanup?
- [ ] Đã giữ business logic độc lập khỏi HttpExchange/framework controller?
- [ ] Đã có owner và policy cho upgrades, certificates, CVE response?
- [ ] Đã ghi ADR với risks, assumptions, alternatives, acceptance criteria?
- [ ] Đã xác định trigger cần đánh giá lại khi scope mới xuất hiện?

## 20. Bài tập thực hành

**A — Local probe.** Chọn use case có đúng một `GET /health` trên loopback. Liệt kê ba rủi ro nếu vô tình đổi bind address sang `0.0.0.0`.

**B — Prefix trap.** Trong demo đổi `"/health"` thành một route `"/api"` rồi gửi `/api2`. Phân tích vì sao router match và tại sao handler phải kiểm tra exact path.

**C — Phân biệt đường dẫn.** Gửi request có `%2F`, `%2e` hoặc encoded segment tới thử nghiệm localhost. Xác định policy raw/decoded path trước khi gắn resource ID.

**D — Body quota.** Thay `MAX_INPUT_BYTES=32` thành 8. Test input ASCII 8/9 bytes và input tiếng Việt có bytes UTF-8 dài hơn số ký tự.

**E — Method policy.** Thêm `PUT` cho một route mới. Nếu method không hỗ trợ, trả 405 và header `Allow`.

**F — HTTPS.** Viết danh sách trách nhiệm của `HttpsServer + HttpsConfigurator` so với TLS termination ở reverse proxy, bao gồm certificate rotation và client trust.

**G — Public API.** Đặt giả định sản phẩm có OIDC login, RBAC theo tenant, OpenAPI và tracing. Điền ma trận ADR: phần nào gateway hỗ trợ, phần nào application/framework phải xử lý?

**H — WebSocket.** Nếu yêu cầu browser realtime bi-directional, so sánh SSE, WebSocket và polling; kết luận dựa trên transport semantics, không xem chunked output là WebSocket.

**I — HTTP/2 end-to-end.** Một gateway nhận HTTP/2 rồi gọi backend HTTP/1.1. Trong tình huống nào đủ, tình huống nào yêu cầu ứng dụng thật sự hỗ trợ H2?

**J — Benchmark.** Chọn target RPS và p99 giả định của team; tạo test ramp-up + burst và profile CPU/heap/thread saturation, không dùng dữ liệu demo làm benchmark.

**K — Observability.** Bổ sung correlation ID, error histogram và /readyz riêng; không log Authorization headers hay request bodies chứa secrets.

**L — Migration.** Tách method xử lý nghiệp vụ khỏi `HttpExchange`, tạo một adapter framework mới nhưng giữ domain tests, so sánh response contracts.

**M — Security tests.** Với yêu cầu multi-tenant, thiết kế tests chứng minh user của tenant A không đọc/ghi resource của tenant B, bất kể gateway hay framework được chọn.

**N — ADR.** Viết một quyết định kỹ thuật một trang cho ba phương án JDK-only, JDK+gateway, framework/server. Có assumptions, benchmarks, security ownership và rollback.

## 21. Câu hỏi tự kiểm tra

**1. `HttpServer` có phải API legacy bị bỏ không?** — Không. Nó vẫn được hỗ trợ; phạm vi thiết kế là HTTP server tối giản.

**2. Tài liệu Oracle mô tả default JDK HttpServer thích hợp nhất cho gì?** — Simple usages như local testing, development, debugging; không nhằm một full-featured high-performance HTTP server.

**3. Khi nào một server tối giản vẫn hợp lý?** — Khi use case nhỏ/cố định, có ranh giới tin cậy rõ và guardrails có thể được kiểm chứng/bảo trì.

**4. Có cần framework chỉ vì hơn 10 routes?** — Không. Số routes không phải quy tắc độc lập; phải xét security/protocol/ops/complexity.

**5. Longest literal prefix có thể gây lỗi gì?** — `"/hello"` match `"/helloworld"`; cần exact-path hoặc segment-boundary check.

**6. HTTP method có quyết định context match không?** — Không. Handler/filter cần xác minh method.

**7. ResponseLength `0` nghĩa là empty body?** — Không. Nó nghĩa chunked; `-1` cho no-body.

**8. `String.length()` có dùng làm fixed response byte count với UTF-8 không?** — Không. Phải lấy `getBytes(UTF_8).length`.

**9. Gateway TLS có thay authorization theo resource không?** — Không. Business authZ vẫn thuộc ứng dụng hoặc policy engine được tích hợp đúng.

**10. Spring/Quarkus có tự đảm bảo ứng dụng an toàn?** — Không. Framework cung cấp công cụ nhưng phải cấu hình, test và cập nhật đúng.

**11. HTTP/2 trên HttpClient có chứng minh HttpServer hỗ trợ server-side HTTP/2 không?** — Không. Đây là hai API/roles khác nhau.

**12. Có thể xử lý streaming/multipart bằng custom code?** — Có thể, nhưng size/timeouts/limits/parser correctness có thể làm TCO tăng; phải đánh giá.

**13. Khi đổi framework, phần nào nên giữ lại?** — Domain/application logic và tests độc lập khỏi HTTP adapter.

**14. Demo `ScopeGateDemo` có tự quyết định mua/dùng framework?** — Không. Nó chỉ đánh dấu cần đánh giá stack dựa trên explicit needs.

**15. Demo HTTP có chứng minh production security/performance chưa?** — Không. Nó chứng minh 10 HTTP behaviors trên loopback JDK 24, không chứng minh SLO/security đầy đủ.

**16. Điều gì thay đổi với `HttpExchange` attributes từ JDK 26?** — Mặc định per-exchange trong provider JDK; context state dùng `getHttpContext().getAttributes()`.

## 22. Nguồn tham khảo chính thức hiện hành

- [Oracle — jdk.httpserver module, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/module-summary.html): phạm vi minimal HTTP server, provider, cấu hình và thay đổi attributes.
- [Oracle — HttpServer, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `createContext`, longest literal prefix, bind/backlog, executor và stop.
- [Oracle — HttpExchange, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request-response lifecycle, byte length, chunked/no-body, close và headers.
- [Oracle — HttpContext, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): context, filters/authenticator và attributes.
- [Oracle — Filter, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html): `Filter.beforeHandler`/`afterHandler`, filter chains.
- [Oracle — HttpsServer, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): HTTPS server và HttpsConfigurator.
- [Oracle — HttpServer, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): khả năng tương thích `--release 17` của ví dụ.
- [Oracle — HttpClient, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client chuẩn JDK dùng kiểm thử loopback.
- [Spring Boot — Web Applications](https://docs.spring.io/spring-boot/reference/web/index.html): MVC/WebFlux và embedded web servers, tài liệu hiện hành.
- [Spring Boot — Production-ready Features/Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html): health, metrics, management endpoints; cần cấu hình exposure/security.
- [Quarkus — Writing REST services](https://quarkus.io/guides/rest/): Quarkus REST và execution model, tài liệu hiện hành.

**Kết luận:** Không chọn framework bằng cảm tính hoặc chỉ nhìn số dòng code. Xác định **nhu cầu thật, ranh giới bảo mật, protocol, SLO, vận hành và ownership**; dùng JDK `HttpServer` cho phạm vi đủ nhỏ và được kiểm soát, bổ sung gateway khi đúng tầng trách nhiệm, hoặc đánh giá framework/server đầy đủ khi scope thật sự phức tạp. Giữ mã nghiệp vụ tách khỏi `HttpHandler` để quyết định hôm nay không khóa chặt kiến trúc ngày mai.
