# Wiretap HTTP client/server và bảo vệ dữ liệu nhạy cảm

## Mục tiêu bài học

Trong chương **Quan sát hệ thống** của **Spring Cloud Gateway**, bài này tập trung vào một kỹ thuật chẩn đoán rất mạnh nhưng cũng dễ tạo rủi ro: **wiretap logging của Reactor Netty `HttpServer` và `HttpClient`**. Khi một API Gateway nhận request, áp **route predicates**, thực thi **filter chain**, xác thực, rewrite path/header, retry, circuit breaker, load balancing rồi gửi HTTP tới microservice, wiretap có thể giúp nhìn thấy các sự kiện và dữ liệu tại những chặng HTTP liên quan.

Nhưng một bản ghi wiretap có thể chứa **bearer token, cookie, API key, số định danh khách hàng, query string, JSON request/response body, dữ liệu thanh toán hoặc nội dung nhạy cảm khác**. Việc bật DEBUG trên môi trường có traffic thật mà không có kiểm soát có thể tạo một kho dữ liệu bí mật mới trong log pipeline.

Sau bài học, bạn có thể:

- Phân biệt wiretap **HTTP server-side** (client ↔ Gateway) và **HTTP client-side** (Gateway ↔ upstream).
- Hiểu ý nghĩa `READ`, `WRITE`, connection ID, `HEX_DUMP`, `TEXTUAL` và `SIMPLE`; biết vì sao một connection ID không phải một HTTP request ID.
- Bật/tắt `httpserver.wiretap` và `httpclient.wiretap` đúng **namespace Spring Cloud Gateway Server WebFlux** và thiết lập logger DEBUG phù hợp.
- Phân biệt wiretap với **access log**, **application log**, **Micrometer metrics**, **distributed tracing** và **audit log**.
- Giải thích vì sao HTTPS/TLS không làm wiretap logs trở thành dữ liệu vô hại.
- Thiết kế quy trình **chẩn đoán tối thiểu, có thời hạn, trên traffic giả lập**, không ghi body/credential thật.
- Dùng metadata logging có allowlist, route ID, status, latency và trace ID thay cho full HTTP payload ở production.
- Kiểm thử lọc dữ liệu nhạy cảm, kiểm soát retention, RBAC và xóa/purge bản ghi lỡ thu thập.
- Chẩn đoán những tình huống Gateway gặp 404/502/503, Retry, response header mismatch và TLS error mà không mặc định bật log toàn bộ request.

> **Phạm vi:** ví dụ dùng **Spring Cloud Gateway Server WebFlux** dựa trên **Reactor Netty**. Không lấy `WebMvc.fn` của Gateway Server Web MVC, `ProxyExchange`, Servlet `Filter`, hoặc logging của một ingress khác làm API thay thế cho Netty wiretap. Spring Cloud Gateway có nhiều release trains; ví dụ YAML chính minh họa **prefix hiện hành** `spring.cloud.gateway.server.webflux.*`. Các dòng cũ có thể dùng `spring.cloud.gateway.*`. Phải đối chiếu version Spring Boot/Spring Cloud Gateway/Reactor Netty đang chạy.

## 1. Wiretap là gì và vì sao chỉ dùng để chẩn đoán?

**Wiretap** là cơ chế instrumentation/logging ở **tầng network I/O** của Reactor Netty. Khi được bật trên `HttpServer` hoặc `HttpClient` và logger tương ứng được đặt ở mức phù hợp, nó có thể ghi sự kiện kết nối, chiều đọc/ghi và các byte buffers của HTTP traffic.

Hãy hình dung một request:

```text
Client
  │   HTTP request (public path, headers, body)
  ▼
Gateway HttpServer    ← wiretap HTTP server
  │
  │   Spring Security, route matching, GlobalFilter,
  │   GatewayFilter, RewritePath/SetRequestHeader...
  │
Gateway HttpClient    ← wiretap HTTP client
  │
  │   HTTP request (upstream path, headers, body)
  ▼
Order Service
  │
  │   HTTP response
  ▼
Gateway HttpClient    ← wiretap response upstream → Gateway
  │
  │   response filters, fallback, headers...
  ▼
Gateway HttpServer    ← wiretap response Gateway → Client
  │
  ▼
Client
```

Sơ đồ cho thấy **bốn vị trí quan sát logic**:

1. Server `READ`: Gateway nhận request của client.
2. Client `WRITE`: Gateway gửi request đến upstream.
3. Client `READ`: Gateway nhận response từ upstream.
4. Server `WRITE`: Gateway gửi response cuối tới client.

Điều này rất hữu ích khi:

- Client gọi `/api/orders/42` nhưng backend lại nhận `/42`, nghi `StripPrefix` sai.
- Header `X-Request-Id` có ở client nhưng biến mất trước upstream.
- Gateway trả 502/503 và cần biết có thực sự mở kết nối upstream không.
- Response header từ backend không giống header Gateway gửi cho browser.
- Muốn phân biệt lỗi ở **route selection**, **filter chain**, **outbound client** hoặc **upstream**.

Tuy nhiên, với dữ liệu thực, **độ quan sát cao hơn không đồng nghĩa với an toàn hơn**. Wiretap có thể biến một request chứa dữ liệu nhạy cảm thành nhiều bản sao trong stdout, file log, logging agent và hệ thống thu thập logs tập trung.

### 1.1. Wiretap không phải packet capture thô

Wiretap của Reactor Netty quan sát **các sự kiện và buffers trong Netty pipeline**. Nó không đồng nghĩa với tcpdump/Wireshark ở network interface, cũng không phải một cam kết rằng mọi byte TLS trên mạng sẽ được hiển thị như encrypted packets.

Vị trí handler trong pipeline và loại logger quyết định nó quan sát nội dung nào. Với HTTPS, **dữ liệu HTTP sau khi TLS được xử lý vẫn có thể xuất hiện dưới dạng dễ đọc/giải mã trong application logs**. Không bao giờ coi “đã bật WSS/HTTPS” là biện pháp bảo vệ dữ liệu trong wiretap logs.

### 1.2. Mức độ cần thiết

| Triệu chứng | Công cụ nên thử trước | Khi nào mới cân nhắc wiretap? |
| --- | --- | --- |
| 5xx tăng | Gateway metrics, backend health, tracing | Khi chưa rõ Gateway có gửi/nhận HTTP đúng không |
| Route match sai | Actuator routes, route ID logs, test predicates | Khi cần chứng minh path/headers trước/sau HTTP hop |
| 429 tăng | Rate limiter metrics, auth/KeyResolver logs an toàn | Hiếm; không cần dump token để giải thích quota |
| Retry bất thường | Retry counters, idempotency logs, traces | Khi cần kiểm thử HTTP attempts trên traffic giả lập |
| TLS handshake error | TLS/Netty exception category, certificate diagnostics | Không cần log body, vì chưa có HTTP payload hợp lệ |
| Header mất/đổi | Header-name allowlist diagnostics, backend echo | Chỉ trong môi trường test được kiểm soát |
| Body rewrite lỗi | Synthetic JSON tests, content-length/encoding assertions | Chỉ với body giả và logger bị cách ly |
| Cần báo cáo KPI | Micrometer + dashboards | **Không dùng wiretap** cho dashboard thường trực |

**Nguyên tắc:** wiretap là **công cụ điều tra thời điểm cụ thể**, không phải chiến lược observability mặc định cho mọi request của Gateway.

## 2. HttpServer và HttpClient: hai kết nối, bốn chiều dữ liệu

Spring Cloud Gateway Server WebFlux thường dùng **Netty HTTP server** nhận traffic và **Netty HTTP client** gửi request tới backend.

```mermaid
sequenceDiagram
    participant C as Client
    participant HS as Gateway HttpServer
    participant F as Gateway filters
    participant HC as Gateway HttpClient
    participant B as Backend
    C->>HS: GET /api/orders/42
    Note over HS: Server READ
    HS->>F: Match route + rewrite
    F->>HC: GET /orders/42
    Note over HC: Client WRITE
    HC->>B: HTTP request
    B-->>HC: 200 + JSON
    Note over HC: Client READ
    HC-->>F: Response cho filter chain
    F-->>HS: Header/body sau xử lý
    HS-->>C: 200 + JSON
    Note over HS: Server WRITE
```

### 2.1. Bảng đọc log theo góc nhìn Gateway

| Logger/điểm quan sát | Dòng sự kiện | Ý nghĩa |
| --- | --- | --- |
| `reactor.netty.http.server.HttpServer` | `READ` | Gateway nhận bytes từ client hoặc ingress |
| `reactor.netty.http.server.HttpServer` | `WRITE` | Gateway gửi bytes ra client hoặc ingress |
| `reactor.netty.http.client.HttpClient` | `WRITE` | Gateway gửi bytes tới backend upstream |
| `reactor.netty.http.client.HttpClient` | `READ` | Gateway nhận bytes từ backend upstream |

`READ` **không** có nghĩa “client đã đọc response” và `WRITE` **không** có nghĩa “backend đã xử lý thành công”. Chúng mô tả hành vi I/O **theo phía logger**.

### 2.2. Chỉ bật server wiretap thấy gì?

Nếu chỉ bật:

```yaml
httpserver:
  wiretap: true
httpclient:
  wiretap: false
```

bạn có thể nhìn thấy traffic client/Gateway ở server side, **không** vì thế nhìn thấy chính xác HTTP request sau `RewritePath`, `SetRequestHeader` và outbound load balancing.

Ví dụ:

```text
Server READ:   GET /api/orders/42
```

Backend có thể nhận:

```text
GET /orders/42
```

nhưng muốn biết request gửi upstream phải dùng HTTP client wiretap hoặc backend stub có kiểm soát. Nếu cần đối chiếu cả hai, ưu tiên **test environment với dữ liệu giả** thay vì bật đồng thời trên production.

### 2.3. Chỉ bật client wiretap thấy gì?

Khi chỉ bật:

```yaml
httpserver:
  wiretap: false
httpclient:
  wiretap: true
```

log tập trung vào I/O Gateway–upstream. Đây có thể là nơi dữ liệu đã được:

- Rewrite path.
- Bổ sung/xóa/ghi đè header.
- Route sang `lb://` instance cụ thể.
- Retry gửi nhiều HTTP attempts.
- Áp proxy/TLS theo HTTP client configuration.

Nhưng client wiretap **không tự ghi nhận** vì sao một inbound request bị Spring Security từ chối trước khi vào Gateway route chain; request 401/403 có thể chưa từng có outbound HTTP call.

### 2.4. Hai request IDs và connection IDs không phải một

Một Netty connection ID như:

```text
[a1b2c3d4, L:/10.0.0.5:8080 - R:/10.0.0.9:53000]
```

là định danh **connection/channel** ở một thời điểm, không phải một UUID chuẩn cho **mỗi HTTP request**. HTTP keep-alive có thể dùng lại một connection cho nhiều requests; HTTP/2 có thể multiplex streams trên một connection.

Đừng nối `server connection ID == client connection ID`: Gateway thường có **hai connections khác nhau**, và client connection pool có thể tái sử dụng upstream connections cho nhiều requests.

Để tương quan requests an toàn, dùng **trace ID/span ID** do tracing infrastructure tạo và propagated hợp lệ; có thể thêm một request ID riêng theo policy, nhưng không thay trace context bằng connection ID hoặc token của user.

## 3. Bật wiretap đúng cấu hình Spring Cloud Gateway

Trong các dòng **Spring Cloud Gateway Server WebFlux mới**, configuration properties ghi:

```text
spring.cloud.gateway.server.webflux.httpserver.wiretap
spring.cloud.gateway.server.webflux.httpclient.wiretap
```

Cả hai có **giá trị mặc định `false`** trong bảng cấu hình hiện hành.

### 3.1. Ví dụ YAML chỉ dành cho môi trường chẩn đoán cô lập

```yaml
# application-wiretap-lab.yml
# Chỉ kích hoạt với traffic giả và nơi nhận log đã được cách ly.
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpserver:
            wiretap: true
          httpclient:
            wiretap: true

logging:
  level:
    reactor.netty.http.server.HttpServer: DEBUG
    reactor.netty.http.client.HttpClient: DEBUG
```

**Đây là cấu hình lab, không phải cấu hình production khuyến nghị.** Khi hai flags và DEBUG loggers được bật, lượng log có thể rất lớn và chứa HTTP headers/bodies. Việc lưu đoạn YAML này dưới một profile tên `wiretap-lab` không tự ngăn người khác vô tình kích hoạt profile trong môi trường production; cần policy deployment/RBAC riêng.

Hai điều kiện cần phân biệt:

1. `httpserver.wiretap` / `httpclient.wiretap` **gắn wiretap vào Netty HTTP pipeline**.
2. `logging.level` phù hợp **cho phép các sự kiện DEBUG được xuất ra**.

Nếu wiretap flag vẫn `false` nhưng chỉ tăng logger lên DEBUG, không phải toàn bộ I/O sẽ tự biến thành wiretap. Nếu wiretap flag `true` nhưng logger đang INFO/WARN, bạn có thể không thấy những dòng DEBUG mong đợi.

### 3.2. Khi chỉ điều tra upstream

Nếu backend đang trả lỗi nhưng Gateway ingress trông bình thường:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpserver:
            wiretap: false
          httpclient:
            wiretap: true
logging:
  level:
    reactor.netty.http.client.HttpClient: DEBUG
```

Đây vẫn là **một chế độ nguy cơ cao** vì upstream requests có thể chứa token và JSON body. Dùng **synthetic requests**, một pod/namespace được cách ly và output logs riêng. Nếu không bảo đảm chỉ có dữ liệu giả chạy qua pod ấy, **không bật** chỉ để giảm số dòng logs.

### 3.3. Namespace của phiên bản cũ

Một số dòng Spring Cloud Gateway trước khi đổi namespace sử dụng:

```yaml
spring:
  cloud:
    gateway:
      httpserver:
        wiretap: true
      httpclient:
        wiretap: true
```

Những thuộc tính:

```text
spring.cloud.gateway.httpserver.wiretap
spring.cloud.gateway.httpclient.wiretap
```

xuất hiện trong tài liệu Gateway Server WebFlux cũ. Không nên chép nguyên cấu hình cũ vào Gateway 5.x rồi nghĩ `true` chắc chắn có hiệu lực. Ngược lại, không áp namespace `server.webflux` lên một ứng dụng Gateway 3.x hoặc Gateway Server Web MVC nếu phiên bản không hỗ trợ.

**Cách xác nhận:** xem bảng configuration properties/javadoc **đúng phiên bản**, dependency tree do dự án cung cấp, log startup và test với HTTP fake payload. Không giả định Spring Boot luôn cảnh báo khi một thuộc tính lạ bị bỏ qua.

### 3.4. Không hiểu “logger DEBUG” là một toggle an toàn

Nếu ứng dụng đã khởi tạo Netty HTTP client/server **với wiretap enabled**, đổi logger sang DEBUG động có thể khiến nội dung bắt đầu xuất hiện. Nếu flag ban đầu `false`, thay logger level **không tự thêm wiretap handler** vào tất cả các kết nối đã tạo.

Vì vậy, một lệnh Actuator `/actuator/loggers` thành công không bảo đảm wiretap “đã bật/tắt đúng” ở mọi instance. Tương tự, đổi property runtime chưa chắc thay cấu hình Netty client/server hiện hành cho đến khi context/connection được xây lại theo phiên bản.

**Hãy thiết kế kế hoạch bật/tắt qua cấu hình triển khai có kiểm soát và verify thực tế;** không để một người trực tiếp bật wiretap trên toàn cluster bằng một API loggers chưa được phân quyền.

## 4. Reactor Netty có ba định dạng wire logging

Reactor Netty hỗ trợ `AdvancedByteBufFormat`:

| Định dạng | Ghi gì | Độ nhạy dữ liệu | Công dụng |
| --- | --- | --- | --- |
| `SIMPLE` | Các sự kiện, byte counts, connection/channel metadata; không dump content buffers | Thấp hơn **nhưng không tuyệt đối vô hại** | Chẩn đoán connect/read/write lifecycle |
| `HEX_DUMP` | Sự kiện **và content** dưới dạng hex/ascii dump | **Rất cao** | Phân tích HTTP bytes/framing trong lab |
| `TEXTUAL` | Sự kiện **và content** ở dạng text dễ đọc | **Rất cao** | Đọc headers/body trong lab có dữ liệu giả |

Theo Reactor Netty, **`HEX_DUMP` là formatter mặc định** khi sử dụng wire logging mặc định. Định dạng hex không bảo vệ thông tin: hex có thể được dịch ngược về bytes gốc, và ví dụ dump còn có cột ASCII giúp nhìn thẳng HTTP headers/body.

### 4.1. Ví dụ sự kiện kiểu SIMPLE

```text
[conn-id-1, L:/127.0.0.1:8080 - R:/127.0.0.1:53000] REGISTERED
[conn-id-1, L:/127.0.0.1:8080 - R:/127.0.0.1:53000] ACTIVE
[conn-id-1, L:/127.0.0.1:8080 - R:/127.0.0.1:53000] READ: 142B
[conn-id-1, L:/127.0.0.1:8080 - R:/127.0.0.1:53000] WRITE: 205B
```

Những dòng này là **minh họa**, không cam kết chính xác format hoặc số bytes ở mọi version. Không xuất body, nhưng vẫn có:

- Endpoint addresses/ports và topology mạng.
- Lượng dữ liệu/cường độ giao tiếp.
- Thông tin thời điểm hoạt động.
- Một số logger/handlers khác có thể phát URI hoặc headers ngoài formatter này.

`SIMPLE` giảm rủi ro **dump nội dung** ở chính formatter nhưng không thay các biện pháp RBAC, retention và bảo mật log infrastructure.

### 4.2. HEX_DUMP có thể lộ bí mật dù nhìn như mã máy

Một payload giả:

```http
POST /api/orders HTTP/1.1
Authorization: Bearer TEST_TOKEN_ONLY
Cookie: SESSION=TEST_COOKIE_ONLY
Content-Type: application/json

{"customerEmail":"fake@example.test"}
```

khi chuyển sang hex vẫn chứa đầy đủ bytes tương ứng với `Authorization`, `TEST_TOKEN_ONLY`, session và email. Bộ giải mã hex có thể khôi phục nội dung. **Không gọi HEX_DUMP là redaction hoặc encryption.**

### 4.3. TEXTUAL làm rủi ro rõ hơn, không nhỏ hơn

Trong lab, text formatter giúp thấy:

```text
READ: 123B POST /api/orders HTTP/1.1
Authorization: Bearer TEST_TOKEN_ONLY
Cookie: SESSION=TEST_COOKIE_ONLY
...
```

Đây là **dữ liệu giả**, không sử dụng token/session đang hoạt động. Một hệ thống log tập trung nhận các dòng tương tự ở production sẽ trở thành nơi lưu bí mật ngoài luồng quản trị credentials.

### 4.4. Tùy chỉnh formatter qua Reactor Netty API

Reactor Netty cung cấp API như:

```java
import io.netty.handler.logging.LogLevel;
import reactor.netty.http.client.HttpClient;
import reactor.netty.transport.logging.AdvancedByteBufFormat;

HttpClient diagnosticClient = HttpClient.create()
    .wiretap(
        "safe-diagnostic-wire",
        LogLevel.DEBUG,
        AdvancedByteBufFormat.SIMPLE
    );
```

Đoạn code này tạo **một HttpClient Reactor Netty độc lập để minh họa API**, không tự cấu hình `HttpClient` mà Spring Cloud Gateway đang dùng để route. Nếu muốn thay Netty client/server của Gateway, phải sử dụng **extension/customizer chính thức của đúng phiên bản**, kiểm thử TLS/pooling/proxy/LoadBalancer và tránh vô tình thay mất cấu hình mặc định.

Không khẳng định có thể chọn `AdvancedByteBufFormat.SIMPLE` bằng một thuộc tính YAML chung như `httpclient.wiretap-format` nếu bảng configuration properties của Gateway version đó **không khai báo** thuộc tính tương ứng.

### 4.5. SIMPLE vẫn có thể tạo overhead

Ngay cả khi không dump body, việc ghi sự kiện I/O cho traffic lớn có thể làm:

- Tăng số messages tới logging framework.
- Tăng CPU/allocations và contention.
- Làm log collector/agent quá tải.
- Tăng chi phí lưu trữ và tìm kiếm.

Vì vậy, khi chỉ cần số requests, kết nối, p95 latency hoặc error rate, hãy dùng **Micrometer metrics/tracing** thay vì bật wiretap liên tục.

## 5. Wiretap nhìn thấy gì ở HTTP headers và body?

Một HTTP request có thể mang dữ liệu nhạy cảm ở nhiều vị trí:

```text
Request line / URI:
  /api/accounts/123?access_token=...&email=...

Headers:
  Authorization, Cookie, X-API-Key, X-Auth-Token, X-Tenant-Id

Body:
  username/password, OTP, payment details, personal data, free text

Response:
  Set-Cookie, Location, account profile, error details, tokens
```

**Chỉ mask một header chưa đủ** nếu cùng dữ liệu xuất hiện trong query string, JSON, response hoặc một logger ở tầng khác.

### 5.1. Phân loại dữ liệu cần tránh ghi

| Loại | Ví dụ | Rủi ro |
| --- | --- | --- |
| Bearer/API credentials | `Authorization`, `X-API-Key` | Chiếm quyền API nếu token còn hiệu lực |
| Session credentials | `Cookie`, `Set-Cookie` | Session hijacking |
| Personal data | Email, phone, address, citizen ID | Vi phạm quyền riêng tư và chính sách dữ liệu |
| Payment data | Card number, payment token, billing details | Tăng phạm vi dữ liệu nhạy cảm lưu trong logs |
| Authentication factors | Password, reset token, OTP | Account compromise |
| Healthcare/financial payload | Hồ sơ bệnh án, tài khoản | Dữ liệu có yêu cầu bảo vệ cao |
| User-generated text/files | Chat message, uploaded documents | Có thể chứa secrets không lường trước |
| Internal topology | `Host`, `Forwarded`, backend URI, private IPs | Thu thập thông tin hệ thống |
| Business secrets | Partner contract fields, pricing, access policies | Tiết lộ thông tin tổ chức |

Những tên header này chỉ minh họa. Một dịch vụ có thể còn dùng header tùy biến như `X-Partner-Token`, `X-Company-Secret`, hoặc body field không có tên dễ đoán.

### 5.2. Masking sau wiretap không hoàn toàn đáng tin

Giả sử logging appender có regex:

```text
Authorization: .*  →  Authorization: [REDACTED]
```

Điều đó có thể không đủ vì:

- Wiretap mặc định có thể ghi **HEX_DUMP** thay vì text.
- JSON bodies có thể escape Unicode, xuống dòng hoặc phân mảnh nhiều chunks.
- HTTP/2 headers không nhất thiết hiển thị dưới một chuỗi HTTP/1.1 dòng đơn.
- Bí mật cũng có thể nằm ở `Cookie`, query string, `Set-Cookie`, multipart/binary.
- Một appender khác, stderr, container log driver hoặc APM agent có thể đã thu **bản raw** trước khi regex được áp.
- Log format hoặc logger name có thể thay khi nâng cấp thư viện.

**Cách phòng vệ tốt nhất là không thu thập dữ liệu bí mật ngay từ đầu.** Với traffic thật, không bật content wiretap; dùng telemetry allowlist ở mức metadata. Redaction là lớp phòng vệ bổ sung, không phải giấy phép lưu raw payload.

### 5.3. TLS không bảo vệ nội dung đã được ghi vào logs

TLS bảo vệ dữ liệu **trên kết nối giữa hai TLS endpoints**. Gateway có thể terminate TLS inbound và mở TLS outbound riêng:

```text
Browser ── TLS 1 ──▶ Gateway ── TLS 2 ──▶ Backend
```

Ứng dụng vẫn phải xử lý **HTTP plaintext representation** để match route, xác thực, rewrite headers/body hoặc proxy. Reactor Netty wire logging tùy pipeline có thể thấy nội dung HTTP trước khi nó được mã hóa cho outbound, hoặc sau khi đã giải mã inbound.

**Không suy luận:** “HTTPS đã mã hóa nên log wiretap chỉ là ciphertext, không có PII”. Cũng không cho rằng dùng `wss://` hoặc HTTP/2 khiến secret headers tự biến mất khỏi tầng quan sát.

### 5.4. Body có thể bị ghi nhiều lần qua hai hops

Một `POST /api/payments` có thể xuất hiện:

```text
Server READ:  original request
Client WRITE: outbound request
Client READ:  backend response
Server WRITE: final response
```

Nếu Retry thực hiện thêm attempts, client WRITE/READ có thể xuất hiện **nhiều lần** cho một inbound request. Chi phí lưu secret và rủi ro exposure nhân theo attempts.

Trường hợp gateway body transform cũng có thể tạo **hai representations khác nhau** chứa PII. Ngay cả khi filter ứng dụng xóa một field trước khi gửi upstream, server-side wiretap **vẫn có thể ghi field trong inbound original**.

## 6. Quy tắc ưu tiên: metrics và tracing trước, wiretap sau

Một hệ thống Gateway cần ba trụ observability:

1. **Metrics** để phát hiện tỷ lệ lỗi, latency, traffic và saturation.
2. **Traces** để theo đường đi một request qua Gateway và nhiều services.
3. **Logs có cấu trúc/metadata allowlist** để giải thích sự kiện và cung cấp context không bí mật.

Wiretap là **công cụ thứ tư**, chỉ dùng khi cần đối chiếu byte-level behavior ở các kết nối trong một môi trường kiểm soát.

### 6.1. Spring Cloud Gateway metrics

Trong Server WebFlux, Gateway có metrics integration với **Spring Boot Actuator/Micrometer** khi được bật ở release train tương ứng. Ví dụ property ở bảng cấu hình hiện hành:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          metrics:
            enabled: true
            path-tags:
              enabled: false
```

Mục tiêu là quan sát requests theo các **low-cardinality dimensions** như:

```text
routeId
httpMethod
status/outcome
```

Tài liệu Gateway mô tả timer metric `spring.cloud.gateway.requests` cùng các tags tùy phiên bản như `routeId`, `routeUri`, `outcome`, `status`, `httpStatusCode`, `httpMethod`. Kiểm tra `/actuator/metrics` của ứng dụng thực khi dùng Spring Boot/Micrometer version mới, vì tên metrics, property và labels có thể khác.

**Không bật raw path tags tùy tiện.** Nếu `path` chứa IDs, email hoặc URL do user kiểm soát, số lượng time series có thể bùng nổ và làm lộ thông tin vào hệ thống metrics. Mặc định `path-tags.enabled: false` trong bảng config mới là một lựa chọn thận trọng.

### 6.2. Access logs khác wiretap

Reactor Netty `HttpServer` có **access logging** riêng. Tài liệu Spring Cloud Gateway nêu JVM system property:

```text
-Dreactor.netty.http.server.accessLogEnabled=true
```

Đây là **Java system property**, không phải `spring.*` property thông thường. Có thể cấu hình Logback logger:

```text
reactor.netty.http.server.AccessLog
```

để gửi log vào appender riêng với retention và quyền truy cập phù hợp. Access log thường ghi request summary, **không mặc định là dump headers/body như wiretap**.

Tuy nhiên, access logs mặc định cũng có thể chứa **request URI đầy đủ, query string, IP, path ID hoặc Referer**; không được gọi “access log luôn an toàn” mà chưa kiểm tra actual format và sanitize chính sách URL.

### 6.3. Tracing: theo dõi request qua nhiều microservices

Khi đã cấu hình Micrometer Tracing/OpenTelemetry theo hệ thống:

```text
Client
  → Gateway span
  → Order Service span
  → Payment Service span
```

trace/span IDs giúp xác định request nào phát sinh lỗi/latency mà **không cần log body hoặc token**.

**Traces không có nghĩa tự an toàn.** Không thêm JWT, cookie, raw query, account ID, full request/response body làm span attributes/baggage. Trace context như `traceparent` phải được xử lý theo protocol và trust policy; một trace ID do client gửi không phải credential hoặc bằng chứng authorization.

### 6.4. Khi nào metric/tracing không đủ?

Bạn có thể thấy:

```text
routeId=orders-v1
status=502
latency=150ms
upstream=order-service
```

và vẫn chưa biết URI path sau rewrite có đúng hay không. Lúc này:

1. Kiểm tra route definitions/filters đã nạp.
2. Kiểm tra backend stub/echo hoặc structured metadata log có path template.
3. Dùng targeted diagnostic logs tại phần route/filter không nhạy cảm.
4. **Chỉ sau cùng**, dùng wiretap trên **synthetic traffic ở lab/repro pod** để đối chiếu HTTP bytes.

## 7. Một cách logging an toàn hơn: chỉ ghi metadata đã chọn

Một `GlobalFilter` có thể ghi **route ID, HTTP method, status và elapsed time** mà không đọc request/response body và không log credential. Đây là ví dụ dùng API Gateway **Server WebFlux**:

```java
package com.example.gateway.observability;

import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils
    .GATEWAY_ROUTE_ATTR;

@Component
public class SafeGatewaySummaryFilter implements GlobalFilter, Ordered {

    private static final Logger log =
        LoggerFactory.getLogger(SafeGatewaySummaryFilter.class);

    @Override
    public int getOrder() {
        return -1;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain) {

        long started = System.nanoTime();
        Route route = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
        String routeId = route == null ? "unknown" : route.getId();
        String method = exchange.getRequest().getMethod().name();

        return chain.filter(exchange)
            .doFinally(signal -> {
                HttpStatusCode status =
                    exchange.getResponse().getStatusCode();
                String statusText =
                    status == null ? "uncommitted"
                                   : Integer.toString(status.value());

                long millis = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started
                );

                log.info(
                    "gateway routeId={} method={} status={} " +
                    "elapsedMs={} signal={}",
                    routeId,
                    method,
                    statusText,
                    millis,
                    signal
                );
            });
    }
}
```

**Điểm an toàn của ví dụ:**

- Không gọi `getBody()`, không buffer JSON hoặc DataBuffer.
- Không log `Authorization`, `Cookie`, `X-API-Key`, query string, form fields.
- Không log raw path có thể chứa `/customers/{customerId}`.
- `routeId` do cấu hình route quản lý; nếu route ID có thể do external tenant tạo, vẫn phải kiểm tra độ dài/cardinality và chính sách ID.
- `doFinally` cũng thấy cancellation và error signals, nhưng **không tự phân loại chính xác nguyên nhân network**.
- Trong một số nhánh response chưa commit, status có thể null; ví dụ dùng `"uncommitted"` thay vì đoán 200.

**Giới hạn:** `GlobalFilter` của Gateway chạy cho request qua **Gateway filtering chain**, không tự bao phủ mọi request bị Spring Security/WebFilter từ chối trước route matching, hoặc Actuator endpoints. Vì vậy security 401/403 và 404 route-not-found cần metrics/observability ở đúng web layer.

### 7.1. Không tạo log injection qua giá trị chưa tin

Ngay cả structured logs cũng có thể gặp:

```text
X-Request-Id: attacker-controlled
```

nếu đem một header tự do vào log mà không kiểm tra. Header có thể dài, chứa control characters hoặc các chuỗi khiến log explorer/indexing gặp vấn đề. Với request correlation:

- Ưu tiên trace ID do instrumentation tạo.
- Nếu nhận correlation header từ client, validate grammar và length.
- Không dùng raw message content hoặc exception body làm field bắt buộc.
- Giới hạn cardinality nếu một value được đưa vào metrics.

Không ghi một **user ID** hoặc **tenant ID** vào một global metric label vô hạn chỉ để dễ tìm request; traces/logs có quyền truy cập tách biệt phù hợp hơn.

### 7.2. Nếu chỉ cần debug filter order

Thay vì wiretap full payload, có thể log:

```text
routeId=orders-v1
filter=RewritePath
phase=pre
outcome=applied
```

hoặc một event đã chuẩn hóa về selected upstream service. Nhưng tránh in raw authorization, full URL có query hay complete request headers. Nếu bắt buộc phải đo tên header đã được thêm/xóa, log **tên đã allowlist**, không log giá trị.

## 8. Quy trình bật wiretap tạm thời một cách có kiểm soát

Không nên hiểu đây là một tính năng “bật rồi quên”. Một quy trình an toàn gồm:

```mermaid
flowchart TD
    A["Sự cố / câu hỏi chẩn đoán"]
    B{"Metrics, traces, safe logs đã đủ?"}
    C["Không bật wiretap<br/>khắc phục từ metadata"]
    D["Phê duyệt mục tiêu & phạm vi"]
    E["Tạo test pod/namespace<br/>chỉ traffic giả"]
    F["Bật đúng httpserver hoặc httpclient<br/>DEBUG logger có kiểm soát"]
    G["Gửi synthetic request và thu bằng chứng"]
    H["Tắt wiretap và xác minh log stop"]
    I["Purge bản ghi không cần thiết<br/>đóng incident/audit"]
    A --> B
    B -->|"Có"| C
    B -->|"Không"| D --> E --> F --> G --> H --> I
```

### 8.1. Trước khi bật

Xác định:

1. **Giả thuyết cần kiểm chứng:** request có bị đổi từ `/api/orders/42` thành `/42` không? Hay `X-Gateway-Source` bị ghi đè?
2. **HTTP hop:** cần server-side hay client-side? Không bật cả hai nếu chỉ cần một.
3. **Đường traffic:** test pod phải thực sự **không nhận production requests chứa dữ liệu thật**.
4. **Dữ liệu giả:** fake JWT/cookie, fake user data, fake backend và cố định một số test requests.
5. **Log destination:** không tự đưa raw wiretap vào observability tập trung của production.
6. **Người được truy cập:** chỉ incident responders có thẩm quyền, có audit.
7. **Thời hạn:** cấu hình có owner, lịch tắt và quy trình xác minh tắt.
8. **Rollback:** biết cách triển khai lại profile bình thường và quản lý pod/instances.

Không dùng một query parameter `debug=true` do client tự gửi để bật raw body logging; đó là một cổng lộ dữ liệu dễ bị lạm dụng.

### 8.2. Chạy trên traffic giả

Một test an toàn ở local:

```bash
curl --http1.1 -i \
  "http://localhost:8080/api/orders/42?debugCase=lab-001" \
  -H "Authorization: Bearer FAKE_TEST_TOKEN" \
  -H "Cookie: SESSION=FAKE_TEST_COOKIE" \
  -H "X-Test-Run: lab-001"
```

Các giá trị có chữ `FAKE_` chỉ là dữ liệu thử nghiệm **không có hiệu lực**. Dùng một backend stub không xử lý giao dịch thật; không dùng account thật hoặc endpoint thanh toán thật chỉ để debug.

Nếu cần kiểm chứng request body:

```bash
curl --http1.1 -i -X POST \
  "http://localhost:8080/api/demo-echo" \
  -H "Content-Type: application/json" \
  --data '{"customer":"synthetic-user","cardToken":"FAKE_TEST_ONLY"}'
```

Chỉ bật body wiretap nếu **toàn tuyến** thuộc môi trường test. Đừng dựa vào việc body demo là giả nếu cùng Gateway pod vẫn phục vụ user khác trong lúc DEBUG được bật.

### 8.3. Sau khi thu đủ bằng chứng

- Tắt wiretap flags và DEBUG loggers bằng cấu hình/deployment đã được duyệt.
- Xác minh các HTTP connections mới không còn sinh content wiretap logs.
- Thu hồi quyền truy cập tạm và xóa test pod hoặc trả lại cấu hình bình thường.
- Đánh dấu incident/probe ID và kết quả chẩn đoán.
- Phân loại log đã thu và **xóa theo chính sách retention**, gồm local files, container stdout, sidecar/agent buffers, central index và backups theo khả năng.
- Nếu lỡ dùng **credential thật**, xử lý như **credential exposure**: thông báo security team, revoke/rotate theo tác động, không chỉ xóa một file local.

**Tắt logger không xóa những bản ghi đã được gửi tới log aggregator.** Đây là nguyên nhân phổ biến khiến một “debug 2 phút” tạo dấu vết tồn tại nhiều tuần.

## 9. Vì sao không bật wiretap trên toàn bộ production traffic?

### 9.1. Lộ dữ liệu

Khi một Gateway nhận:

```http
POST /api/login
Content-Type: application/json

{"username":"user@example.test","password":"FAKE_ONLY"}
```

wiretap có thể ghi inbound body ở **server READ** dù Gateway routing filters xóa field đó **trước HTTP client WRITE**. Nếu dùng token thật trong production, bản ghi có thể bị đọc bởi bất kỳ hệ thống/người nào có quyền logs.

### 9.2. Khối lượng logs tăng mạnh

Một ước tính minh họa:

```text
1.000 HTTP requests/giây
× 2 hops (server + client)
× 2 chiều (request + response)
= khoảng 4.000 hướng I/O cần quan sát/giây
```

Thực tế còn nhiều `READ`/`WRITE` buffer chunks, connection events, retries, HTTP/2 frames hoặc nội dung hex/ascii được in thành nhiều dòng. Số records và bytes của logs **không phải** chỉ bằng số requests nhân bốn.

Để có một request body 10 KiB, hex dump còn thêm hex digits, offset và cột ASCII, khiến lượng text log có thể lớn hơn đáng kể so với bytes HTTP ban đầu.

### 9.3. Performance và backpressure

Tăng logging làm tăng chi phí CPU, allocation, string formatting, I/O và network cho collector. Nếu appender đồng bộ/blocking, nó có thể ảnh hưởng xử lý request trên Reactor Netty event-loop; nếu appender async, queue có thể đầy, drop logs hoặc gây áp lực memory.

**Không dùng logging như một đường dữ liệu chính** để xử lý hàng nghìn requests/giây. Metrics/tracing có sampling và low-cardinality tags phù hợp hơn cho giám sát 24/7.

### 9.4. Chi phí vận hành

Khi wiretap được bật:

- Log indexing/search/storage tăng.
- Khó phân biệt 5xx từ nhiều services do log nhiễu.
- Compliance scope của log store có thể mở rộng.
- Retention policy phức tạp và các backup vẫn giữ bí mật.
- Người có quyền xem logs có thể có quyền xem **dữ liệu vốn chỉ thuộc application/backend**.

Chi phí bảo mật và quản trị có thể lớn hơn lợi ích một lần debug.

## 10. Log masking: chiến lược đúng là giảm thu thập

Một thiết kế observability an toàn có nhiều lớp:

```text
Layer 1 — Không thu body/credentials theo mặc định
Layer 2 — Allowlist metadata cần thiết
Layer 3 — Redact secrets ở nguồn phát sinh log
Layer 4 — Redact/suppress ở collector nếu hợp lý
Layer 5 — RBAC, encryption, retention, audit, deletion
Layer 6 — Verification tests với synthetic secrets
```

**Layer 1 là quan trọng nhất.** Không nên dựa toàn bộ vào một regex ở cuối pipeline.

### 10.1. Allowlist thay vì blacklist

Log summary an toàn:

```json
{
  "routeId": "orders-api",
  "httpMethod": "GET",
  "httpStatus": 502,
  "durationMs": 184,
  "upstreamService": "order-service",
  "outcome": "connect-error",
  "traceId": "synthetic-trace-id"
}
```

Không cần:

```json
{
  "authorization": "Bearer ...",
  "cookie": "...",
  "requestBody": "...",
  "responseBody": "...",
  "requestUri": "/api/orders/42?access_token=..."
}
```

**Lưu ý:** `upstreamService` là một logical service ID đã được kiểm soát, không phải URL kèm credentials/query. Trace ID nên được sinh/kiểm tra qua tracing instrumentation, không sao chép chuỗi vô hạn từ client.

### 10.2. Không log raw exception messages ở mọi tầng

Một exception có thể chứa:

```text
Failed call https://service.example/path?token=...
```

Nếu gửi nguyên `exception.getMessage()` vào alert/dashboard, URL bí mật có thể lọt ra dù ứng dụng đã không bật wiretap. Nên phân loại:

```text
errorCategory=connect-timeout
upstreamService=order-service
status=502
```

và giữ exception stack trace ở log kênh bảo vệ có redaction nếu cần điều tra kỹ.

### 10.3. Không lưu nguyên body chỉ để “ẩn một field”

Ví dụ:

```json
{
  "user": {
    "email": "person@example.test",
    "credentials": {
      "password": "FAKE",
      "otp": "FAKE"
    }
  },
  "notes": "free text có thể chứa dữ liệu bất kỳ"
}
```

Nếu chỉ xóa `password` ở top-level, vẫn có nested credentials, email, OTP, free text và dữ liệu chưa dự đoán được. Các sản phẩm có dữ liệu nhạy cảm nên **không log full JSON**. Khi bắt buộc audit nghiệp vụ, dùng **schema allowlist**, giới hạn size và tách kho audit với quyền/retention chuyên biệt.

## 11. Chẩn đoán path rewrite/header differences bằng dữ liệu giả

Giả sử Gateway route:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - SetRequestHeader=X-Gateway-Source, orders-edge
```

Client:

```http
GET /api/orders/42 HTTP/1.1
X-Gateway-Source: forged-client-value
```

Kỳ vọng upstream:

```http
GET /orders/42 HTTP/1.1
X-Gateway-Source: orders-edge
```

### 11.1. Điểm quan sát A — trước Gateway filters

Server wiretap (lab) có thể thấy:

```text
Server READ:
  GET /api/orders/42
  X-Gateway-Source: forged-client-value
```

Điều đó cho biết request inbound có path/header như trên, **chưa chứng minh** route được match hay filters chạy.

### 11.2. Điểm quan sát B — sau Gateway filters

Client wiretap (lab) có thể thấy:

```text
Client WRITE:
  GET /orders/42
  X-Gateway-Source: orders-edge
```

Điều này cho thấy request outbound có path/header sau filters, nhưng **chưa chứng minh backend đã xử lý nghiệp vụ thành công**. Backend có thể trả 404/500 sau đó.

### 11.3. Cách chẩn đoán không cần wiretap

Trong phần lớn ca, tốt hơn dùng backend echo stub:

```text
method = GET
path = /orders/42
X-Gateway-Source = orders-edge
```

Stub chỉ dùng **dữ liệu giả** và có thể assert chính xác request mà Gateway gửi. Đây là bằng chứng ít rủi ro hơn log raw traffic ở production.

### 11.4. Route không match hoặc bị security chặn

Nếu `Path` predicate không match, Gateway có thể không tạo outbound HTTP request. Nếu Spring Security từ chối trước routing, cũng có thể chỉ có **server READ/WRITE** mà **không có client WRITE**.

Không thấy client wiretap không luôn có nghĩa HTTP client bị lỗi; có thể chưa có route, request bị filter short-circuit, cache hit hoặc fallback nội bộ. Dùng response status, route matching logs và metrics để xác định nhánh xử lý.

## 12. Retry, CircuitBreaker và LoadBalancer làm thay đổi cách đọc logs

Một incoming request không luôn tương ứng đúng một outbound request.

```mermaid
flowchart TD
    IN["Client request duy nhất"]
    ROUTE["Gateway route"]
    RETRY["Retry filter"]
    A["Upstream attempt #1"]
    B["Upstream attempt #2"]
    C["Upstream attempt #3"]
    OUT["Gateway final response"]
    IN --> ROUTE --> RETRY
    RETRY --> A
    A -->|"retryable failure"| B
    B -->|"retryable failure"| C
    C --> OUT
```

### 12.1. Số lượng logs theo attempts

Ví dụ:

```text
HttpServer READ      : 1 inbound request
HttpClient WRITE     : attempt 1
HttpClient READ/ERROR: attempt 1 fails
HttpClient WRITE     : attempt 2
HttpClient READ      : attempt 2 gets 503
HttpClient WRITE     : attempt 3
HttpClient READ      : attempt 3 gets 200
HttpServer WRITE     : 1 final client response
```

Đây là sơ đồ khái niệm, không khẳng định mỗi attempt luôn có đúng một READ/WRITE log event. Network chunks, connection reuse, timeouts, handshake và client abort có thể tạo nhiều/ít events khác.

### 12.2. Không tạo kết luận “Gateway đã gửi request ba lần” từ ba log dòng WRITE

Một HTTP request body có thể bị chia thành nhiều writes, và một connection có thể được dùng lại. Ngược lại, request failed before send có thể không có complete write. Để xác nhận **attempt count** dùng:

- Retry metrics/counters theo route.
- Tracing spans cho outbound attempts nếu instrumentation hỗ trợ.
- Backend stub đếm completed requests.
- Application idempotency audit.

Không chỉ đếm `WRITE` events.

### 12.3. CircuitBreaker có thể short-circuit

Khi circuit OPEN, một request có thể **không được gửi upstream**, và client nhận fallback/status từ Gateway. Vì vậy:

```text
Server READ: có
Client WRITE: có thể không
Server WRITE: có
```

Không có client wiretap không nhất thiết là bug. Phải xem circuit state, fallback metrics và route filter chain.

### 12.4. LoadBalancer có thể chọn instance khác

`lb://order-service` là logical URI. Netty client kết nối tới instance thực được resolve, ví dụ một pod IP. Wiretap có thể để lộ **private topology**, nên log destination cũng cần được bảo vệ.

Không đưa backend instance IP:port vào các public metrics labels hoặc dashboards rộng ngoài nhu cầu; dùng logical route/service ID cho biểu đồ tổng quan.

## 13. TLS và các kiểu lỗi có thể chẩn đoán mà không dump body

TLS errors xảy ra trước khi có HTTP request/response hoàn chỉnh ở một hop hoặc trong quá trình network operation.

### 13.1. TLS inbound

```text
Client ── TLS handshake ──▶ Gateway HttpServer
```

Các lỗi:

- Chứng chỉ server hết hạn/không đúng SAN.
- TLS version/cipher mismatch.
- SNI không match certificate được chọn.
- Client mTLS cert không được tin hoặc thiếu cert khi required.

Chẩn đoán bằng certificate inspection, handshake error categories và network/TLS metrics. **Không cần bật HTTP body wiretap** để giải thích một lỗi `certificate_unknown`.

### 13.2. TLS outbound

```text
Gateway HttpClient ── TLS handshake ──▶ Upstream
```

Các lỗi:

- Gateway không trust CA của backend.
- Backend hostname không khớp SAN.
- Proxy/SNI/ALPN không tương thích.
- Backend network port không mở.

Không sửa lỗi bằng:

```yaml
use-insecure-trust-manager: true
```

trong production. Tùy dòng Gateway, property tên đầy đủ có thể là `spring.cloud.gateway.server.webflux.httpclient.ssl.use-insecure-trust-manager` với default `false`; **bật insecure trust manager không phải cách tăng observability**.

### 13.3. HTTPS không làm log an toàn

Ngay cả khi hai TLS hops đều hợp lệ, mỗi Netty HTTP stack vẫn có thể thao tác dữ liệu đã được giải mã ở application boundary. Wiretap không được coi là một hệ thống log ciphertext mặc định. **Bảo mật truyền tải và bảo mật dữ liệu lưu trữ là hai lớp riêng**.

## 14. So sánh wiretap, HTTP access log, metrics, traces và audit

| Cơ chế | Mục tiêu | Thường chứa | Rủi ro chính | Dùng lâu dài? |
| --- | --- | --- | --- | --- |
| **Wiretap** | Debug HTTP I/O ở mức buffer/channels | I/O events, headers, body (tùy format) | Rò secret/PII, log volume rất lớn | **Không nên** trên traffic thật |
| **Access log** | Ai gọi endpoint nào, status/bytes/latency | Method, URI, address, status | URI/query có PII, IP | Có thể, với format/retention an toàn |
| **Structured app log** | Sự kiện nghiệp vụ/kỹ thuật | Route ID, outcome, error category | Log thừa user input/exception data | Có, theo allowlist |
| **Metrics** | Tốc độ, lỗi, latency, saturation | Numeric series + labels | High cardinality, data leakage qua labels | Có |
| **Distributed tracing** | Phân rã latency và call graph | Trace/span IDs, attributes | Baggage/span tags có secrets | Có, với privacy policy/sampling |
| **Audit log** | Hành động cần chứng minh sau này | Actor/action/resource/outcome | Chứa định danh/decision nhạy cảm | Có, trong kho được kiểm soát |

### 14.1. Access log không phải audit log

Một dòng:

```text
GET /api/admin/routes 200
```

không chứng minh người nào được quyền thay route, ai duyệt revision và trước/sau thay đổi là gì. Nếu cần audit quản trị Gateway, dùng một audit schema và authorization context có nguồn đáng tin, không lấy toàn bộ HTTP body wiretap thay bằng chứng nghiệp vụ.

### 14.2. Metrics không thay request replay

Metrics cho biết p99 tăng và 503 cao, nhưng không giữ raw payload để replay giao dịch. Đây là **tính năng bảo vệ dữ liệu**, không phải thiếu sót bắt buộc phải “bổ sung” bằng raw body logging. Nếu muốn tái hiện lỗi, tạo **synthetic test case** trong staging.

### 14.3. Traces cũng phải có retention/RBAC

Trace ID có thể được chia sẻ giữa dịch vụ. Dù không phải secret tự thân, traces có thể tiết lộ internal service topology, endpoint names và timing. Chỉ thêm attributes cần thiết; không đưa passwords/tokens hay raw request/response vào spans để thay thế wiretap.

## 15. Môi trường test và quy trình kiểm chứng thực tế

Tạo một Gateway **lab pod** và backend echo service ở `localhost:9001` hoặc trong namespace cô lập.

### 15.1. Route mẫu

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: echo-lab
              uri: http://localhost:9001
              predicates:
                - Path=/lab/echo/**
              filters:
                - StripPrefix=2
                - SetRequestHeader=X-Gateway-Environment, lab
```

Client:

```bash
curl --http1.1 -i \
  "http://localhost:8080/lab/echo/orders/42" \
  -H "X-Gateway-Environment: forged" \
  -H "Authorization: Bearer FAKE_TEST_TOKEN"
```

Backend echo cần nhận:

```text
path = /orders/42
X-Gateway-Environment = lab
```

**Chú ý:** mục tiêu của test là xác minh path/header transform, không phải thu bearer token. Nếu đang bật wiretap để học, token phải là chuỗi **không được ứng dụng thực chấp nhận**, và test pod không được dùng chung với traffic production.

### 15.2. Cách đọc bốn nhóm logs

| Quan sát | Test mong đợi |
| --- | --- |
| Server READ | `GET /lab/echo/orders/42`, header `forged` từ client |
| Client WRITE | `GET /orders/42`, header đã thành `lab` |
| Client READ | Response echo upstream |
| Server WRITE | Response cuối cùng trả test client |

Nếu client response 200 nhưng client wiretap không có, kiểm tra profile/logger/prefix, route có sử dụng HTTP client thực không, logger name/version, và log appender bị lọc; không suy ra Gateway chưa gửi request.

### 15.3. Test không chứa secrets thật

Tạo thêm test request chứa marker giả:

```http
Authorization: Bearer SECRET_MARKER_FAKE_001
Cookie: SESSION=SECRET_MARKER_FAKE_002
X-API-Key: SECRET_MARKER_FAKE_003
```

Trong **chế độ wiretap lab có kiểm soát**, marker có thể xuất hiện ở server-side dump — đó là bằng chứng rằng content wiretap **không phù hợp để bật với credential thật**.

Sau khi tắt wiretap, chạy lại synthetic request và assert:

- Không còn raw marker trong các logs được phát sinh sau thời điểm tắt.
- Safe summary metrics/logs vẫn xuất hiện (route ID/status/latency).
- Không tồn tại một chế độ debug bị quên trên pod thứ hai.
- Các marker cũ được dọn khỏi log destination theo retention policy.

**Không kiểm thử bằng cách cố đọc secret thật hoặc chạy credential scanner trên dữ liệu khách hàng không được phép.** Dùng marker giả có thể truy vết, được phê duyệt, trong môi trường test.

## 16. Test tự động cho chính sách logging

Unit/integration tests nên kiểm tra hai mặt: **telemetry cần thiết còn hoạt động** và **log không lưu dữ liệu nhạy cảm**.

### 16.1. Test safe logger không chứa body/headers

Với `SafeGatewaySummaryFilter`:

```text
Given:
  request contains Authorization=FAKE_TEST_TOKEN
  request contains Cookie=FAKE_TEST_COOKIE
  request body contains "FAKE_PASSWORD"

When:
  GET/POST goes through Gateway route

Then:
  a summary event contains routeId, method, status, elapsedMs
  no log event from SafeGatewaySummaryFilter contains:
    FAKE_TEST_TOKEN
    FAKE_TEST_COOKIE
    FAKE_PASSWORD
```

Dùng **logging test appender** chỉ bắt đúng logger `SafeGatewaySummaryFilter`. Không tuyên bố toàn bộ hệ thống không log secrets chỉ vì một logger đã pass: Netty wiretap, WebClient logs, ingress, exception logging và APM agent còn có thể log riêng.

### 16.2. Test configuration theo profile

Test môi trường bình thường:

```text
spring.cloud.gateway.server.webflux.httpserver.wiretap = false
spring.cloud.gateway.server.webflux.httpclient.wiretap = false
```

Test profile diagnostic:

```text
wiretap may be enabled only in isolated test context
```

Ngoài unit test properties, cần test deployment policy ngăn profile diagnostic được áp trong production namespace. Một YAML `wiretap: false` ở repository không chứng minh env var/ConfigMap/Helm override không bật lại flag ở runtime.

### 16.3. Test rò secret ở log pipeline

Một test integration của staging có thể:

1. Gửi marker giả qua headers, query và JSON body.
2. Thu logs từ **tất cả sinks** trong phạm vi test.
3. Kiểm tra safe logging pipeline không giữ marker.
4. Nếu bật diagnostic wiretap lab, chứng minh marker **có thể xuất hiện**, rồi cô lập/xóa log đó.
5. Kiểm tra RBAC của collector, retention và audit truy cập.

Không chỉ kiểm tra output ở app stdout nếu sidecar/Fluent Bit/Vector/OTel Collector vẫn lưu hoặc forward bản copy.

### 16.4. Test không làm hỏng chức năng Gateway

Sau khi bật/tắt diagnostic mode, xác minh:

- Route predicates và filter chain vẫn áp đúng.
- JWT validation, RateLimiter, CircuitBreaker, Retry hoạt động như trước.
- HTTP/1.1 và HTTP/2 clients nhận response hợp lệ.
- TLS inbound/outbound certificate verification không thay.
- Không làm timeout tăng đáng kể hoặc gây memory/CPU saturation do logs.
- Log access/metrics vẫn có đúng sampling/labels.

## 17. Những lỗi thường gặp khi bật wiretap

### 17.1. Đã đặt `wiretap: true` nhưng không thấy log

Nguyên nhân có thể:

- Chưa đặt logger Reactor Netty tương ứng ở DEBUG/TRACE.
- Dùng sai prefix (`spring.cloud.gateway.*` cũ so với `server.webflux.*` mới).
- Đang chạy Gateway Server Web MVC, không dùng Netty HttpServer như WebFlux.
- Request bị security/route matching từ chối nên **không có outbound client exchange**.
- Logging appender/filter/sampling loại các dòng mong đợi.
- Flag được đổi runtime nhưng Netty client/server đã tạo trước đó.

**Cách xử lý:** kiểm tra version/configprops, logger name, route behavior và thử một request fake vào pod lab. Không tự tăng `logging.level.reactor.netty=TRACE` trên production để “xem có gì”.

### 17.2. Chỉ thấy request inbound, không thấy upstream

**Khả năng:** chỉ bật `httpserver.wiretap`, không bật `httpclient.wiretap`; hoặc không có outbound HTTP call do 401/403/404, circuit OPEN, cache hit, fallback.

**Cách xử lý:** kiểm tra cả cấu hình lẫn route/filter chain. Backend stub và traces giúp phân biệt.

### 17.3. Thấy server READ và WRITE nhưng không tìm được route ID

Netty connection logging không phải route-level tracing. HTTP server wiretap xảy ra ở pipeline mạng, trước hoặc ngoài thời điểm route được chọn; nó không tự biết `routeId`.

**Cách xử lý:** dùng Gateway metrics/trace/structured route summary. Không lấy connection ID gán làm route ID.

### 17.4. Cùng một request xuất hiện nhiều lần trong client logs

**Khả năng:** Retry attempts, HTTP chunks, redirects được HTTP client hỗ trợ theo policy, nhiều proxy hops hoặc connection reuse.

**Cách xử lý:** đo attempts bằng retry metrics/backend stub, không đếm số `WRITE` log lines làm số giao dịch.

### 17.5. Logs có chuỗi hex, không đọc được payload

Đó có thể là **`HEX_DUMP` mặc định**. Hex có thể biểu diễn nguyên bytes; không được coi là đã mask. Nếu cần phân tích bytes, làm trong lab với dữ liệu giả. Không chuyển sang `TEXTUAL` trên production để “dễ đọc hơn”.

### 17.6. Wiretap logs vẫn lộ Authorization dù đã có RemoveRequestHeader

**Khả năng:** server-side wiretap thấy **header client gốc** trước khi Gateway filter xóa nó; hoặc một logger khác ghi outbound/inbound ở tầng khác.

**Cách xử lý:** không bật content wiretap trên traffic thật. RemoveRequestHeader là chính sách **forwarding**, không phải redaction cho bytes đã đến Gateway.

### 17.7. Gateway/Log collector tăng CPU hoặc disk

**Khả năng:** ghi quá nhiều buffers, HEX_DUMP phình to, logging I/O blocking, async queue backlog hoặc nhiều retries.

**Cách xử lý:** tắt diagnostic wiretap, bảo đảm cleanup logs, theo dõi disk/memory/CPU, dùng metrics/traces cho monitoring thường trực.

### 17.8. Đã tắt DEBUG nhưng bí mật vẫn xuất hiện khi tìm logs

Logs trước khi tắt có thể đã được ghi vào:

```text
container stdout
node log files
sidecar buffers
collector queues
central index
long-term archive / backups
```

**Cách xử lý:** xác định phạm vi phát tán, áp incident response, purge theo chính sách và rotate credentials đã bị thu thập nếu có; tắt logging **không thu hồi được secret**.

### 17.9. Wiretap trên HTTPS nhưng đọc được JSON

Điều này phù hợp với nguyên tắc **TLS bảo vệ đường truyền, không bảo vệ mọi log tại endpoint**. Nếu có nguy cơ lộ dữ liệu, dừng diagnostic và xử lý bảo mật ngay; không cố “sửa” bằng cách đổi TLS cipher hoặc giả định logs đã an toàn vì HTTP client dùng HTTPS.

### 17.10. Actuator loggers được mở public

Nếu một tác nhân có thể đổi log levels và ứng dụng đã bật wiretap, họ có thể gây bùng nổ logs chứa dữ liệu nhạy cảm. Bảo vệ Actuator management APIs, giới hạn `loggers`, kiểm soát write access, TLS, network isolation và audit.

## 18. Checklist trước khi triển khai hoặc điều tra

| Hạng mục | Câu hỏi |
| --- | --- |
| **Runtime** | Đang chạy Gateway Server WebFlux/Reactor Netty đúng version? |
| **Namespace** | `server.webflux.httpserver/httpclient.wiretap` hay legacy `gateway.httpserver/httpclient.wiretap`? |
| **Mặc định** | Hai wiretap flags có tắt trên production không? |
| **Logger** | `reactor.netty.http.server.HttpServer` và `.http.client.HttpClient` có ở INFO/WARN khi không debug? |
| **Phạm vi** | Có thật sự cần server-side, client-side hay cả hai? |
| **Mục tiêu** | Đã nêu một giả thuyết cụ thể cần kiểm tra? |
| **Traffic** | Chỉ synthetic traffic, không chạy production credentials/payloads qua diagnostic pod? |
| **Formatter** | Hiểu HEX_DUMP/TEXTUAL có thể ghi content; SIMPLE vẫn có metadata? |
| **TLS** | Không giả định HTTPS che dữ liệu tại wiretap logger? |
| **Auth headers** | Không log Authorization, Cookie, API key, Set-Cookie? |
| **Body/query** | Không log JSON chứa PII, multipart, form, token trong URL? |
| **Filter chain** | Không dùng wiretap thay route-level metrics/trace? |
| **Resilience** | Retry có thể tạo nhiều outbound attempts và log copies? |
| **Log pipeline** | Đã kiểm soát file/stdout/agent/collector/index/archive? |
| **RBAC** | Chỉ nhóm được phê duyệt truy cập diagnostic logs và management controls? |
| **Retention** | Có TTL, cleanup, audit và quy trình xử lý accidental exposure? |
| **Overhead** | Theo dõi CPU, GC, memory, disk và log queue? |
| **Tắt đúng** | Có verify flags/logger levels và tất cả instances đã quay lại chế độ thường? |
| **Thay thế** | Metrics/tracing/access logs/metadata filter có đủ giải quyết vấn đề không? |
| **Tests** | Có test path/header differences, log leak markers, security reject, Retry, TLS? |

## 19. Bài luyện tập có đáp án

### Tình huống A: 404 sau rewrite

Gateway route:

```yaml
filters:
  - StripPrefix=2
```

Client gọi:

```text
GET /api/orders/42
```

Backend chỉ có:

```text
GET /orders/42
```

**Câu hỏi:** nên bật toàn bộ production wiretap để tìm lỗi không?

**Trả lời:** không. Tính trước rằng `StripPrefix=2` có thể tạo `/42`, kiểm tra route config và backend echo trong staging. Nếu cần, dùng client-side wiretap **chỉ với test request giả ở lab** để nhìn outbound path.

### Tình huống B: Missing Authorization

Client có:

```http
Authorization: Bearer FAKE_TEST_TOKEN
```

Nhưng backend trả 401.

**Câu hỏi:** có phải wiretap server/client là cách đầu tiên để biết token đã đi đâu?

**Trả lời:** không. Trước tiên xem Spring Security/TokenRelay policy, logs chỉ ghi auth outcome/scope category và test backend stub **không chứa token thật**. Khi cần so header presence, chỉ log `authorizationPresent=true/false` trong phạm vi có kiểm soát — **không log token value**.

### Tình huống C: HTTPS và hex dump

Gateway sử dụng `wss://` hoặc `https://` với upstream. Người vận hành nói “wiretap hex nên token đã mã hóa”.

**Trả lời:** sai. Hex là **representation của bytes**, có thể giải mã; Netty logging ở application pipeline có thể thấy HTTP data đã giải mã hoặc trước khi mã hóa. TLS không ngăn dữ liệu bị ghi ra logs tại Gateway.

### Tình huống D: Một GET, ba client WRITE

Có một inbound GET nhưng ba nhóm HTTP client writes.

**Trả lời:** chưa thể kết luận ba upstream attempts chỉ từ số dòng; có thể body được chia chunks, retry hoặc connection events. Dùng retry metrics, traces và backend stub để xác định số requests thực.

### Tình huống E: Không thấy log sau `logging.level...=DEBUG`

**Trả lời:** có thể `httpserver.wiretap`/`httpclient.wiretap` vẫn `false`, namespace sai hoặc request không đến path có outbound call. Debug logger và wiretap handler là hai điều kiện khác nhau.

### Tình huống F: Muốn log mọi JSON response để điều tra 503

**Trả lời:** không nên. Đo error rate/status/route ID, phân loại Netty connection errors, circuit state và service health trước. Nếu response body thực sự cần đối chiếu, tạo **JSON giả trên backend stub**; không dump dữ liệu khách hàng thật.

### Tình huống G: Token thật lỡ được lưu trong log collector

**Trả lời:** đây là **sự cố bảo mật dữ liệu**, không chỉ lỗi logging. Dừng thu thập, xác định sinks/scope, thông báo security team, rotate/revoke credentials theo mức ảnh hưởng, purge retention/index/backups theo chính sách và audit việc truy cập.

### Tình huống H: Chỉ cần tổng số 502/503 theo route

**Trả lời:** sử dụng **Gateway/Micrometer metrics** với route ID, status/outcome và latency; không cần wiretap.

## 20. Câu hỏi tự kiểm tra

1. **Server `READ` nói về chiều dữ liệu nào?**  
   Gateway nhận bytes từ client/ingress ở Netty HttpServer.

2. **Client `WRITE` nói về chiều nào?**  
   Gateway gửi bytes tới upstream qua Netty HttpClient.

3. **Client `READ` và server `WRITE` có cùng nguồn dữ liệu không?**  
   Chúng có thể nhìn hai representations response khác nhau vì Gateway response filters có thể sửa headers/body/status.

4. **Chỉ có logger DEBUG nhưng wiretap flag `false` có đủ không?**  
   Không. Cần cấu hình Netty wiretap và log level phù hợp.

5. **Mặc định trong bảng config Gateway mới là gì?**  
   `server.webflux.httpserver.wiretap=false` và `server.webflux.httpclient.wiretap=false`.

6. **Một trường HEX_DUMP đã là dữ liệu được mã hóa và an toàn để chia sẻ chưa?**  
   Chưa. Nó có thể chứa raw HTTP bytes có thể giải mã.

7. **`SIMPLE` có chắc không chứa thông tin vận hành nhạy cảm không?**  
   Không. Có thể còn remote IP/ports, byte counts, timing hoặc logs từ logger khác.

8. **TLS có bảo đảm wiretap không thấy HTTP payload không?**  
   Không. Tùy vị trí Netty handler và runtime, payload trước/sau TLS xử lý có thể được ghi.

9. **Có thể đếm HTTP requests bằng số `WRITE` lines không?**  
   Không. Có chunks, connection reuse, multiplexing và retries.

10. **Vì sao không chỉ mask `Authorization`?**  
    Secrets có thể xuất hiện ở Cookie, Set-Cookie, query string, request/response body, API-key headers và hex dumps.

11. **Tại sao retry có thể làm nhiều log hơn?**  
    Một inbound request có thể tạo nhiều outbound HTTP attempts.

12. **Khi chỉ cần route latency nên dùng gì?**  
    Micrometer metrics/tracing với low-cardinality tags.

13. **Access log có hoàn toàn an toàn không?**  
    Không; URI/query/IP có thể chứa PII, cần chính sách format/retention.

14. **Nếu wiretap đã tắt, các logs cũ tự mất không?**  
    Không. Log aggregator, files và backups vẫn có thể lưu bản copy.

15. **Bảo vệ `/actuator/loggers` để làm gì?**  
    Ngăn lạm dụng thay log levels, làm lộ dữ liệu khi diagnostics đã enabled và gây quá tải logs.

16. **Khi nào được cân nhắc content wiretap?**  
    Khi thật sự cần, có approval, test traffic giả, môi trường cô lập, TTL, rollback và kiểm soát log sinks.

## 21. Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Server WebFlux — Troubleshooting / Wiretap](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/troubleshooting.html): mức logger và mô tả HttpClient/HttpServer wiretap.
- [Spring Cloud Gateway — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html): các properties `spring.cloud.gateway.server.webflux.httpclient.wiretap`, `httpserver.wiretap`, metrics.
- [Spring Cloud Gateway Server WebFlux — Global Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html): Gateway metrics, route-level observability và filter lifecycle.
- [Spring Cloud Gateway Server WebFlux — Reactor Netty Access Logs](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/reactor-netty-access-logs.html): bật access logs bằng JVM system property, tách logger/appender.
- [Reactor Netty — HTTP Client Reference](https://projectreactor.io/docs/netty/release/reference/http-client.html) và [HTTP Server Reference](https://projectreactor.io/docs/netty/release/reference/http-server.html): wire logger, Netty client/server và các formatters.
- [Reactor Netty — AdvancedByteBufFormat API](https://projectreactor.io/docs/netty/release/api/reactor/netty/transport/logging/AdvancedByteBufFormat.html): semantics `SIMPLE`, `HEX_DUMP`, `TEXTUAL`.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): Micrometer Observation, metrics/traces, low/high-cardinality metadata.

## Tổng kết

**Wiretap của Reactor Netty `HttpServer` và `HttpClient`** là công cụ mạnh để quan sát HTTP I/O tại **hai phía của Spring Cloud Gateway Server WebFlux**. `HttpServer` thấy traffic **client ↔ Gateway**, còn `HttpClient` thấy traffic **Gateway ↔ upstream**; `READ`/`WRITE` phải được hiểu theo góc nhìn component ghi log. Trên những dòng Gateway mới, hai cờ `spring.cloud.gateway.server.webflux.httpserver.wiretap` và `.httpclient.wiretap` mặc định tắt, và DEBUG logging là điều kiện riêng để thấy output.

Điểm quan trọng hơn là **bảo vệ dữ liệu**: `HEX_DUMP` và `TEXTUAL` có thể ghi nguyên headers/bodies; `SIMPLE` giảm content logging nhưng vẫn cần kiểm soát metadata. **TLS không bảo vệ các bản ghi đã tạo ở ứng dụng**. Không bật content wiretap trên traffic thật như một giải pháp quan sát thường trực. Hãy ưu tiên **metrics, distributed tracing, access logs và structured metadata allowlist**, rồi chỉ dùng wiretap **trong lab với dữ liệu giả, có approval, scope, thời hạn, RBAC, log-sink isolation, rollback và purge** khi cần chẩn đoán sâu. Làm như vậy mới giúp Gateway phục vụ các microservices với khả năng quan sát tốt mà không biến hệ thống logs thành nơi rò rỉ credential hoặc dữ liệu nhạy cảm.
