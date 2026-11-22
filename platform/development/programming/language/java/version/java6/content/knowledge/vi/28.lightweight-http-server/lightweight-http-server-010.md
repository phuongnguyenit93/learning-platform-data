# Ứng dụng máy chủ kiểm thử, webhook cục bộ và công cụ nội bộ bằng HTTP server gọn (Java 17+)

## 1. Mục tiêu và phạm vi

Không phải mọi HTTP server Java đều cần một hệ framework web hoàn chỉnh. Một chương trình Java nhỏ đôi khi chỉ cần:
- Mở một **máy chủ HTTP kiểm thử** trên `127.0.0.1` để giả lập dịch vụ phụ thuộc hoặc kiểm tra client.
- Nhận một **webhook cục bộ** có chữ ký từ một tiến trình/ứng dụng thử nghiệm và kiểm chứng quy tắc bảo mật.
- Expose vài **công cụ nội bộ** như kiểm tra sức khỏe, echo có giới hạn hoặc chuyển đổi text mà không cho người dùng chạy lệnh hệ điều hành.
- Chạy các **integration tests tự chứa** với cổng tự chọn, phản hồi nhanh, tự đóng server và executor sau khi kết thúc.

Java 17+ có module **`jdk.httpserver`**, bao gồm `com.sun.net.httpserver.HttpServer`, `HttpHandler`, `HttpExchange` và `Headers`. API này đang được hỗ trợ trên JDK hiện đại. Nó phù hợp cho **test fixture, local debugging, utility endpoint và service nội bộ nhỏ** khi các yêu cầu được kiểm soát. Dùng `java.net.http.HttpClient` (module `java.net.http`) để viết HTTP client kiểm thử, không cần thêm thư viện.

**Phạm vi an toàn:** mục tiêu ở đây là **localhost/lab**. Ví dụ không biến nó thành một internet-facing webhook gateway. Một webhook thực nhận từ bên thứ ba cần endpoint HTTPS, TLS, authentication/signature verification theo **đúng chuẩn riêng của nhà cung cấp**, secrets quản lý tập trung, idempotency bền vững, queue/worker và vận hành production. Không expose internal tools ra Internet chỉ bằng cách đổi `127.0.0.1` thành `0.0.0.0`.

Sau bài, bạn có thể:
1. Tạo và dừng một `HttpServer` gọn với port ngẫu nhiên mà không bị xung đột.
2. Viết handlers cho health, echo và công cụ văn bản, dùng đúng method/path/status/header/body.
3. Nhận webhook trên loopback, xác minh HMAC-SHA256 của **raw request bytes**, ký kèm timestamp + event ID, chống phát lại cơ bản.
4. Giới hạn request body, kiểm soát Content-Type, method, token và header values.
5. Dùng `HttpClient` kiểm thử các ca hợp lệ và giả mạo ngay trong một `main`.
6. Phân biệt mô hình demo với yêu cầu production: replay cache bền vững, idempotency, secret rotation, TLS, timeouts, monitoring và quyền truy cập.

## 2. Ba kiểu ứng dụng và ranh giới tin cậy

| Use case | Mục đích | Người gọi | Yêu cầu tối thiểu |
| --- | --- | --- | --- |
| **Test server/fixture** | Fake một dịch vụ thật, kiểm thử HTTP status/body/errors. | Unit/integration test cùng máy. | Loopback, port 0, deterministic responses, cleanup, giới hạn input. |
| **Local webhook receiver** | Nhận HTTP callback từ một sender giả lập. | Test client/process trên máy. | POST-only, raw body, chữ ký HMAC, timestamp, event ID, replay check. |
| **Internal tool HTTP endpoint** | Cung cấp health/echo/formatting cho developer automation. | Người dùng/tiến trình được phép. | Bind loopback, token/OS permission, method/path allowlist, size quota. |

Cùng dùng `HttpServer` nhưng **trust model không giống nhau**:
- `/health` nên là **read-only**, trả thông tin tối thiểu, không lộ secrets.
- `/echo` hoặc `/tools/upper` có thể tiếp nhận input; phải giới hạn dung lượng, chặn requests không có token, tránh thực thi code/file path tùy ý.
- `/webhook` chấp nhận yêu cầu từ một sender được nhận diện bằng chữ ký; **đừng tin mọi POST chỉ vì đến từ localhost**.
- Nếu test server được truy cập qua **tunnel công khai**, nguồn request đã là Internet, mặc dù process cuối cùng bind localhost.

**Dữ liệu trước xác thực là không đáng tin**, kể cả khi request có `Content-Type: application/json` hoặc header `X-Webhook-Signature`. Cần xác minh chữ ký trên bytes thực tế, kiểm tra freshness và chỉ sau đó mới chạy business processing.

### 2.1. Những việc HTTP server gọn làm được và chưa tự cung cấp

`HttpServer` hỗ trợ server socket, contexts, exchange và executor; nó **không tự biến endpoints thành an toàn**. Ứng dụng phải thiết kế:
- Routing chính xác (contexts dùng longest prefix match).
- Method/Content-Type validation và HTTP status phù hợp.
- Authentication, authorization, CSRF/Origin policy trong bối cảnh browser.
- Giới hạn bytes, số connections, timeouts, concurrency và queue.
- Idempotency khi webhook sender retry.
- Secret storage/rotation, redacted logging, audit và metrics.
- HTTPS/TLS/reverse proxy nếu không còn giới hạn ở localhost.
- Graceful shutdown và xử lý lỗi sau khi HTTP response đã gửi.

Một máy chủ nhỏ thường **đơn giản hơn** Spring Boot/Quarkus cho chương trình kiểm thử vài route, nhưng không phải **mặc nhiên tốt hơn** về tính năng, compliance hay bảo mật khi ứng dụng mở rộng.

## 3. Kiến trúc một ứng dụng lab có 4 endpoint

```text
           Local test client (HttpClient Java 17)
                        |
                 127.0.0.1:port-0
                        |
                     HttpServer
                        |
    +-------------------+-------------------+
    |                   |                   |
 GET /health       POST /echo        POST /tools/upper
    |                   |                   |
 status 200          local token          local token
 body "ok"           size 2 KiB           size 2 KiB
                     echo text            uppercase text
                        |
                  POST /webhook
                        |
          method + Content-Type + size cap
                        |
          timestamp + ID + signature format
                        |
            HMAC-SHA256 trên raw bytes
                        |
               freshness +/- 5 phút
                        |
             event ID chưa từng nhận
                        |
             accepted counter (demo)
                        |
                 202 Accepted
```

Đường `/webhook` không thực sự thay đổi đơn hàng hay gửi email: nó chỉ tăng `AtomicInteger` để chứng minh **một sự kiện được chấp nhận đúng một lần trong bài test**. Do đó không nên sử dụng đầu ra `acceptedEvents=1` làm bằng chứng đã có độ bền giao dịch hoặc idempotency production.

Máy chủ chạy trên `127.0.0.1` và **cổng số 0**, nghĩa là OS chọn một cổng còn trống. Sau `server.start()`, dùng `server.getAddress().getPort()` để biết cổng thực tế và tạo URL cho client. Không hard-code cổng 8080/3000 trong integration tests nếu có thể tránh, vì tests chạy song song dễ gặp port conflicts.

## 4. Khởi tạo HttpServer và đăng ký routes

Các class chính:
- `HttpServer`: tạo server, cấu hình executor, `createContext`, `start`, `stop`.
- `HttpHandler`: callback `handle(HttpExchange)`.
- `HttpExchange`: request URI/method/headers/body, response headers/body và status.
- `Headers`: map header names không phân biệt chữ hoa/thường.
- `HttpClient`, `HttpRequest`, `HttpResponse`: tạo client integration test ngay trong JDK.

Ví dụ khai báo ngắn (chưa độc lập):

```java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 0), 0);

ExecutorService pool = Executors.newFixedThreadPool(4);
server.setExecutor(pool);
server.createContext("/health", this::health);
server.start();

int chosenPort = server.getAddress().getPort();
// Client test sẽ gửi http://127.0.0.1:chosenPort/health

// Khi kết thúc (trong finally thật của chương trình):
server.stop(0);
pool.shutdownNow();
```

**Snippet:** trong ví dụ này, `this::health` cần một instance có method `health(HttpExchange)`, đồng thời cần imports. Mã chạy hoàn chỉnh nằm ở mục 10.

**Chọn `127.0.0.1` thay vì `0.0.0.0`:** loopback giảm việc vô tình mở endpoint cho máy khác, nhưng **không phải lớp authentication**. Các tiến trình chạy cùng máy vẫn có thể kết nối. Nếu cần chỉ một user/tiến trình truy cập, cân nhắc quyền OS, token, firewall/network namespace và giao thức local IPC khác phù hợp.

**Port 0** giúp test tránh xung đột nhưng không tự đảm bảo test repeatable theo thứ tự thực thi. Để giữ kết quả ổn định, assert HTTP response values chứ không assert cổng tự chọn.

### 4.1. Context path là prefix, không phải exact route

`createContext("/webhook", handler)` có thể đưa cả `/webhook-extra` vào cùng handler do cơ chế **longest matching prefix**. Trong handler cần kiểm tra:

```java
if (!"/webhook".equals(exchange.getRequestURI().getPath())) {
    send(exchange, 404, "not found");
    return;
}
```

Đây là snippet; `send` được định nghĩa trong mã đầy đủ. Kiểm tra path và HTTP method độc lập; không giả định `HttpServer` tự xử lý exact matching hay template routes như `/items/{id}`.

Nếu ứng dụng phân quyền theo URL, cần xử lý percent-encoding, path normalization và proxy/gateway semantics nhất quán. Chỉ kiểm tra `getPath()` là phù hợp trong **demo route đơn giản**, không thay thế một routing/authz layer được kiểm chứng khi có nhiều routes nhạy cảm.

### 4.2. HTTP server và client nằm ở hai module khác nhau

| Module | Package | Mục đích |
| --- | --- | --- |
| `jdk.httpserver` | `com.sun.net.httpserver` | Tạo `HttpServer`, `HttpHandler`, `HttpExchange`, `Headers`. |
| `java.net.http` | `java.net.http` | Tạo `HttpClient`, `HttpRequest`, `HttpResponse`. |
| `java.base` | `java.io`, `java.nio.charset`, `java.security`… | Streams, encoding, crypto helper, time, collections. |
| `java.base` | `javax.crypto` | `Mac`, `SecretKeySpec` cho HMAC-SHA256. |

Với một dự án JPMS có `module-info.java`, khai báo:

```java
module demo.localwebhook {
    requires jdk.httpserver;
    requires java.net.http;
}
```

**Đây là snippet `module-info.java`**, không phải một phần thêm vào file classpath demo. Chương trình ở mục 10 được biên dịch bằng `javac --release 17` trên classpath và không cần `module-info.java`.

## 5. Quy tắc handler: request → validate → response

### 5.1. Đúng thứ tự trả response

Một handler HTTP gọn làm theo thứ tự:
1. Xác nhận URI/method.
2. Xác nhận authentication/token/signature khi có.
3. Đọc request body **với budget** và validate Content-Type.
4. Xử lý dữ liệu.
5. Chuẩn bị status, response headers và body bytes.
6. `exchange.sendResponseHeaders(status, bytes.length)`.
7. `exchange.getResponseBody()` và ghi đúng N bytes.
8. Đóng response output stream và exchange.

```java
byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
Headers headers = exchange.getResponseHeaders();
headers.set("Content-Type", "text/plain; charset=utf-8");
headers.set("Cache-Control", "no-store");

exchange.sendResponseHeaders(200, body.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(body);
}
```

**Snippet:** biến `exchange` đã có trong `HttpHandler`; cần imports. Ví dụ luôn dùng body không rỗng trong helper `send`. Với `204`/`HEAD` hoặc response không body, sử dụng `sendResponseHeaders(status,-1)`; với `responseLength=0`, `HttpExchange` chọn chunked transfer cho HTTP/1.1, **không phải Content-Length: 0**.

Không đổi status sau `sendResponseHeaders`, không thêm header sau commit rồi giả định client sẽ nhận, không phát body cố định dài hơn/nhỏ hơn `bytes.length` đã khai. Nếu streaming gửi lỗi giữa chừng, không thể gửi lại một response 500 thay thế 200 đã commit.

### 5.2. Quản lý vòng đời request và response

`HttpExchange` implements `AutoCloseable` trên Java 17, nên `try (exchange)` hợp lệ. Đóng response `OutputStream` sau khi ghi xong, rồi đóng exchange trong scope handler. Đóng exchange mà chưa đọc hết request body có thể khiến underlying TCP connection không được tái sử dụng; điều này còn phụ thuộc implementation và giới hạn số bytes khi drain.

Không dùng `InputStream.readAllBytes()` trên body từ client chưa giới hạn. Ví dụ chọn `readNBytes(MAX_BODY + 1)`, để đọc một byte vượt ngưỡng làm tín hiệu **413 Content Too Large**. `readNBytes` trả tối đa N bytes; nếu trả đúng N+1 với N là budget, reject. Một request lớn hơn nữa không được toàn bộ materialize, nhưng việc đóng sớm có thể khiến connection reuse bị ảnh hưởng, một trade-off cần chấp nhận/hỗ trợ ở reverse proxy.

### 5.3. Content-Type, text encoding và response headers

- `Content-Type: text/plain; charset=utf-8` cho echo/tool responses; `application/json` là loại webhook input của demo.
- Kiểm tra **media type thực** trước dấu `;` (ví dụ `application/json; charset=utf-8` vẫn là JSON), không dùng `startsWith("application/json")` vì sẽ vô tình chấp nhận `application/json-malicious`.
- HTTP header names case-insensitive, nhưng giá trị phải tuân định dạng riêng; `Headers.get(name)` trả list, demo chỉ chấp nhận **một giá trị** cho các security headers.
- `Cache-Control: no-store` giảm nguy cơ client/proxy cache response có dữ liệu nhạy cảm.
- `X-Content-Type-Options: nosniff` giúp browser tránh diễn giải sai MIME.
- Response body UTF-8 phải tính theo `byte[].length`, không dùng `String.length()` làm Content-Length.

**Không tự chứng minh JSON hợp lệ bằng Content-Type:** một payload có Content-Type JSON vẫn có thể là text không phải JSON. Demo chỉ xác minh chữ ký + đếm event, không parse JSON hay thực thi business logic; production phải parse JSON với thư viện hiện hành, validate schema và event types sau khi xác minh.

## 6. Webhook cục bộ: xác thực HMAC-SHA256 trên raw bytes

### 6.1. Webhook thực chất là HTTP POST có side effects

Một sender phát hiện sự kiện (order created, payment completed, deployment finished…) sẽ gửi HTTP request đến URL callback. Receiver không biết request đó có thật từ sender hay do kẻ khác tạo nếu không kiểm tra authenticity. **Đừng dựa vào User-Agent, `X-Event-Name`, localhost hay JSON field như `"event":"paid"` làm bằng chứng xác thực.**

Với protocol có HMAC, sender và receiver biết một shared secret. Sender ký **một chuỗi bytes theo quy tắc của giao thức**; receiver tính lại và so sánh. Một HMAC hợp lệ chứng minh rằng người gửi có secret, **không** tự chứng minh event ID có quyền làm mọi thay đổi nghiệp vụ; vẫn cần authorization/validation.

### 6.2. Quy tắc chữ ký của chương trình học tập

Ví dụ tạo một giao thức lab rất nhỏ:

```text
X-Webhook-Timestamp: <Unix seconds>
X-Webhook-Id:        <ASCII identifier>
X-Webhook-Signature: sha256=<64 lowercase hex characters>

signedBytes =
    UTF8(timestamp + "\n" + eventId + "\n")
    || rawRequestBodyBytes

digestBytes = HMAC-SHA256(secretKey, signedBytes)
signature   = "sha256=" + lowercaseHex(digestBytes)
```

**Đây là format riêng cho bài học, KHÔNG phải chữ ký Stripe, GitHub hoặc Standard Webhooks.** Nhà cung cấp thật thường quy định headers, canonical string, timestamp/secret rotation và signature prefix khác nhau. Phải dùng **SDK/documentation chính thức của sender**, không tự áp dụng format này cho một webhook công khai.

Trong Java 17:

```java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(keyBytes, "HmacSHA256"));
mac.update(
    (timestamp + "\n" + eventId + "\n")
        .getBytes(StandardCharsets.UTF_8));
byte[] expectedHmac = mac.doFinal(rawBodyBytes);
```

Đây là **snippet**: `keyBytes` là khóa bí mật từ secret manager/nguồn test, `rawBodyBytes` là chính bytes HTTP vừa đọc, không phải JSON đã parse rồi serialize lại. `Mac` không nên share mutable instance giữa threads; ví dụ tạo mới cho mỗi request.

### 6.3. Vì sao phải ký raw body trước khi parse JSON?

Hai JSON strings có thể mang cùng đối tượng nhưng bytes khác nhau:

```json
{"event":"paid","amount":19.75}
```

```json
{ "amount": 19.75, "event": "paid" }
```

Nếu sender ký **raw body**, receiver parse JSON rồi serialize lại có thể đổi whitespace, thứ tự properties, Unicode escaping hoặc number formatting → chữ ký khác. Luôn verify trên raw request bytes **đúng trình tự sender đã ký**. Sau khi signature hợp lệ, mới parse/validate JSON, kiểm tra event type, tenant, resource identifiers và authorization.

**Giữ nguyên bytes bao gồm newline cuối file.** Không `trim()` body, không tự normalize CRLF, không đổi charset hay convert sang Java String để tính lại signature nếu provider ký bytes gốc.

### 6.4. So sánh signature theo cách giảm rủi ro timing leak

**Không dùng** `expectedHex.equals(receivedHex)` như so sánh MAC trong một hệ bảo mật mới. Với Java, sau khi kiểm tra format signature, decode hex thành bytes và dùng:

```java
byte[] suppliedHmac = HexFormat.of()
        .parseHex(signature.substring("sha256=".length()));

boolean valid = MessageDigest.isEqual(expectedHmac, suppliedHmac);
```

**Snippet:** cần khai báo đúng `signature` và `expectedHmac`. `MessageDigest.isEqual` có hành vi so sánh phù hợp hơn cho thông tin bí mật; vẫn phải xác định kích thước/format input trước, giới hạn độ dài header, và không log raw signature/secret.

**HMAC key:** demo tạo `32` bytes ngẫu nhiên bằng `SecureRandom` ở mỗi lần chạy, chỉ nằm trong RAM. Production cần secret được cấp phát qua KMS/secret vault, có scope riêng cho từng integration, phân quyền, rotation và cơ chế chấp nhận nhiều active secrets trong giai đoạn chuyển đổi theo giao thức provider.

## 7. Freshness, replay và idempotency

### 7.1. Timestamp được ký để hạn chế replay

Một chữ ký đúng trên body không ngăn kẻ bắt được request gửi lại nguyên vẹn sau đó. Demo ký thêm timestamp và event ID, chỉ nhận timestamp nằm trong khoảng **±300 giây** so với `Instant.now().getEpochSecond()`. Nếu clock hai hệ thống lệch, webhook hợp lệ có thể bị 401; production cần NTP/clock monitoring và tolerance theo tài liệu provider.

**Timestamp phải nằm trong material được xác thực.** Nếu chỉ đọc `X-Webhook-Timestamp` nhưng HMAC không ký nó, attacker có thể sửa timestamp của request cũ và vượt qua freshness check.

### 7.2. Event ID và replay cache

Ngay cả trong cửa sổ 5 phút, cùng chữ ký vẫn có thể được replay nhiều lần. Demo:
1. Verify timestamp và HMAC.
2. Xóa các event IDs khỏi cache nếu đã quá **600 giây** tính từ lúc nhận.
3. Không cho cache vượt budget minh họa `MAX_IDS=1000`.
4. Gọi `ConcurrentHashMap.putIfAbsent(eventId, now)` để chỉ chấp nhận một lần event ID trong process.
5. Nếu đã có ID, trả **409 Duplicate** trong bài kiểm thử để dễ thấy.

**Tại sao giữ ít nhất 2 lần tolerance?** Một timestamp có thể nằm trước thời gian hiện tại tới 300 giây hoặc nằm **tương lai 300 giây**. Nếu receiver chấp nhận timestamp tương lai và chỉ lưu event ID trong 300 giây, cùng signature có thể còn nằm trong cửa sổ hợp lệ khi cache đã xóa. Dùng 600 giây để bao phủ khoảng thời gian đó trong mô hình đơn giản.

**Giới hạn:** cache trong RAM không chia sẻ giữa các server instances, mất khi restart, check `size()` không phải quota tuyệt đối dưới concurrency cao, và event ID có thể bị tái sử dụng khi TTL kết thúc. Đây là **bài tập**, không phải idempotency storage production.

### 7.3. Duplicate response và retry policy

Bài học trả `409` để assertion `webhookReplayStatus=409` rõ ràng. Với **webhook thực**, nhiều sender retry khi gặp non-2xx; việc trả 409 cho một event đã xử lý thành công có thể khiến họ retry liên tục. Thiết kế production thường:
- Nhận event đã xác minh.
- Dùng **unique key/transaction/atomic insert** vào database hoặc queue bền vững.
- Nếu ID đã xử lý hoặc đã nhận thành công, trả **2xx idempotent** (theo provider contract) và không lặp side effect.
- Lưu event ID ít nhất trong toàn bộ retry horizon của provider, không chỉ 10 phút.
- Xử lý out-of-order events, retries với backoff, và tránh giả định exactly-once delivery.

**Không tăng số dư, gửi email hay cấp quyền trước khi xác minh và lưu idempotency key bền vững.** `accepted.incrementAndGet()` trong demo chỉ tăng một counter test; không thay transaction hay durable queue.

### 7.4. Một vài chi tiết khó: headers và signature rotation

- Nếu sender gửi nhiều signatures khi rotate secrets, protocol production có thể cho phép **bất kỳ signature từ active key nào** hợp lệ; demo chỉ chấp nhận **một signature header** để có format đơn giản. Đừng sao chép quy tắc này vào provider hỗ trợ multi-signature.
- Hãy bảo đảm signed material có **định dạng phân định rõ** (demo dùng newline, ID/timestamp chỉ cho ASCII digits/identifier) để không bị ambiguous concatenation.
- Đừng phân biệt lỗi 401 quá chi tiết cho public clients; log loại lỗi ở phía server không chứa secrets.
- Không lấy event ID chưa xác thực để quyết định deduplication/trust. Cache chỉ được cập nhật **sau HMAC + freshness pass**.
- Với secret bị lộ, revoke/rotate ngay và xác minh lại những events có rủi ro.

## 8. Công cụ nội bộ: xác thực token và giới hạn thao tác

Công cụ nội bộ trên HTTP rất tiện cho developer automation, nhưng dễ biến thành một **remote-code-execution service** nếu handler nhận tham số rồi đưa thẳng vào `ProcessBuilder` hoặc shell.

**Chỉ expose những thao tác đã định nghĩa và an toàn.** Ví dụ:
- `GET /health` → `ok` (read-only).
- `POST /echo` → trả text sau khi kiểm tra token và size.
- `POST /tools/upper` → đổi text thành uppercase với `Locale.ROOT`.
- Không có endpoint chạy shell, đọc file tùy ý, xóa thư mục, mở URL tùy ý hay thao tác DB production.

Các POST local tool yêu cầu header `X-Local-Token` chứa một token 16-byte random được encode hex. Server kiểm tra token bằng `MessageDigest.isEqual` trên **hai chuỗi bytes cùng dạng ASCII hex**. Không nhầm so sánh token raw bytes với text hex: chúng khác độ dài/giá trị; test đã kiểm chứng vấn đề này và code cuối dùng cùng representation.

**Không để token trong query string** vì dễ lọt vào logs/history. Demo tạo token ngẫu nhiên trong cùng process và truyền qua `HttpClient`; không in token vào stdout. Với tool thật, dùng OS user isolation, secret storage, TLS nếu không chỉ loopback, expiry/rotation và audit. Một service cục bộ còn có thể bị các tiến trình không đáng tin trên cùng máy truy cập: loopback không thay auth.

### 8.1. Không dựa vào CORS làm authentication

Một website độc hại có thể cố gửi requests từ browser tới `localhost` hoặc nhắm một service qua DNS rebinding/CSRF trong những bối cảnh nhất định. **CORS là cơ chế browser hạn chế việc đọc response, không phải lớp xác thực API**. Không thêm `Access-Control-Allow-Origin: *` cho endpoints có side effects hay secrets, và không xem việc thiếu CORS là đủ để ngăn mọi POST.

Trong production:
- Xác thực token/Origin/CSRF theo đúng threat model.
- Với local-only tools, dùng token không đoán được và exact method/path allowlist.
- Không expose secret trong HTML/JS public.
- Đặt limits và read timeouts, đặc biệt khi dùng GUI/browser.

### 8.2. Chú ý Unicode khi biến đổi text

`String.toUpperCase(Locale.ROOT)` là API hiện đại, nhưng uppercase **không phải chuyển đổi một-một code point** trong mọi ngôn ngữ. Một số ký tự có thể nở rộng hoặc thay representation. Demo xác nhận `"Hà Nội 🌏"` thành `"HÀ NỘI 🌏"`. Công cụ thực không nên dùng uppercase làm bảo mật để chuẩn hóa user identifiers/Unicode normalization/locale-dependent account names nếu schema không định nghĩa rõ quy tắc.

## 9. Thiết kế integration test tự chứa

Một test server tốt nên:
1. **Sử dụng port 0 và 127.0.0.1**, không cần quyền administrator hay cấu hình port thủ công.
2. Đăng ký tất cả contexts trước `start()`.
3. Tạo executor có giới hạn, không giữ vô hạn threads.
4. Sử dụng `HttpClient` chuẩn với connect/request timeout.
5. Gửi requests thật qua TCP loopback, không chỉ gọi handler với mock object.
6. Assert cả **status code**, response body, headers có liên quan và side effects.
7. Kiểm thử đường thành công **và** lỗi (403, 401, 409, 413, 415, 405).
8. Đóng server và executor trong `finally` để test không treo.
9. Không in secrets/ports random/IDs dùng làm credential vào stdout.
10. Khi có concurrency, test atomicity của deduplication và idempotency.

**Không cần `Thread.sleep(...)` chờ server “warm-up”** trong trường hợp `server.start()` đã hoàn tất và client có thể gửi request. Nếu test có asynchronous processing thật, đồng bộ bằng latch/future/condition có timeout, không sleep đoán mò.

### 9.1. Ma trận endpoint và HTTP response

| Endpoint | Method | Điều kiện | Expected |
| --- | --- | --- | --- |
| `/health` | GET | Không yêu cầu token trong demo. | `200` + `ok`. |
| `/echo` | POST | Token, text/plain, body ≤2048 bytes. | `200` + echo text. |
| `/tools/upper` | POST | Token, text/plain, body ≤2048 bytes. | `200` + uppercase text. |
| `/tools/upper` | POST | Thiếu token. | `403` + `forbidden`. |
| `/webhook` | POST | Signature đúng, thời gian mới, event ID chưa thấy, JSON media type. | `202` + `accepted`. |
| `/webhook` | POST | Gửi lại event đã nhận. | `409` trong **demo** (production thường 2xx idempotent). |
| `/webhook` | POST | Body khác bytes được ký. | `401`. |
| `/webhook` | POST | Timestamp hợp lệ về cú pháp nhưng quá cũ. | `401`. |
| `/webhook` | POST | Body lớn hơn 2048 bytes. | `413`. |
| `/webhook` | POST | Content-Type không phải application/json. | `415`. |
| `/webhook` | GET | Không phải POST. | `405` + `Allow: POST`. |
| Route khác | Bất kỳ | Không có context tương ứng. | `404`. |

Một integration test cấp API nên kiểm tra thêm Content-Type response, không cache dữ liệu nhạy cảm, những headers bị lặp, request path có suffix giống context, malformed timestamp, signature không đúng định dạng, client disconnect và concurrency.

## 10. Chương trình Java 17+ đầy đủ: LocalWebhookLab.java

Đây là chương trình **runnable độc lập** (không Maven, Gradle, Spring hoặc thư viện ngoài):
- Tạo server loopback/cổng tự chọn.
- Định nghĩa health, echo, uppercase tool và webhook.
- Sinh HMAC key 32 bytes và local token 16 bytes bằng `SecureRandom` chỉ cho session test.
- Giới hạn body 2048 bytes qua `readNBytes(MAX_BODY+1)`.
- Xác minh HMAC raw body, timestamp ±5 phút, ID deduplication trong process.
- Client tự gửi positive và negative HTTP requests, assert expected statuses.
- Dừng server và pool trong `finally`.

### 10.1. Toàn bộ mã nguồn

Tạo file **`LocalWebhookLab.java`** lưu UTF-8:

```java
import com.sun.net.httpserver.Headers;
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
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class LocalWebhookLab {
    private static final int MAX_BODY = 2048;
    private static final long MAX_SKEW_SECONDS = 300;
    private static final int MAX_IDS = 1000;

    private final byte[] webhookKey = new byte[32];
    private final byte[] localToken = new byte[16];
    private final ConcurrentHashMap<String, Long> usedIds =
            new ConcurrentHashMap<>();
    private final AtomicInteger accepted = new AtomicInteger();

    private LocalWebhookLab() {
        SecureRandom random = new SecureRandom();
        random.nextBytes(webhookKey);
        random.nextBytes(localToken);
    }

    private static void send(
            HttpExchange ex, int status, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

        Headers h = ex.getResponseHeaders();
        h.set("Content-Type", "text/plain; charset=utf-8");
        h.set("Cache-Control", "no-store");
        h.set("X-Content-Type-Options", "nosniff");

        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static boolean only(
            HttpExchange ex, String method, String path)
            throws IOException {
        if (!path.equals(ex.getRequestURI().getPath())) {
            send(ex, 404, "not found");
            return false;
        }
        if (!method.equals(ex.getRequestMethod())) {
            ex.getResponseHeaders().set("Allow", method);
            send(ex, 405, "method not allowed");
            return false;
        }
        return true;
    }

    private static String oneHeader(Headers h, String name) {
        List<String> values = h.get(name);
        return values != null && values.size() == 1
                ? values.get(0) : null;
    }

    private static boolean mediaType(
            String contentType, String expected) {
        return contentType != null
                && expected.equalsIgnoreCase(
                    contentType.split(";", 2)[0].trim());
    }

    private static byte[] readBounded(HttpExchange ex)
            throws IOException {
        try (var in = ex.getRequestBody()) {
            return in.readNBytes(MAX_BODY + 1);
        }
    }

    private byte[] hmac(
            String timestamp, String id, byte[] body)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(webhookKey, "HmacSHA256"));
        mac.update((timestamp + "\n" + id + "\n")
                .getBytes(StandardCharsets.UTF_8));
        return mac.doFinal(body);
    }

    private String sign(
            String timestamp, String id, byte[] body)
            throws Exception {
        return "sha256=" + HexFormat.of().formatHex(
                hmac(timestamp, id, body));
    }

    private boolean authorized(HttpExchange ex) {
        String supplied = oneHeader(
                ex.getRequestHeaders(), "X-Local-Token");
        byte[] expected = HexFormat.of().formatHex(localToken)
                .getBytes(StandardCharsets.US_ASCII);
        return supplied != null && MessageDigest.isEqual(
                expected,
                supplied.getBytes(StandardCharsets.US_ASCII));
    }

    private void health(HttpExchange ex) throws IOException {
        try (ex) {
            if (!only(ex, "GET", "/health")) return;
            send(ex, 200, "ok");
        }
    }

    private void echo(HttpExchange ex) throws IOException {
        try (ex) {
            if (!only(ex, "POST", "/echo")) return;
            if (!authorized(ex)) {
                send(ex, 403, "forbidden");
                return;
            }
            if (!mediaType(oneHeader(
                    ex.getRequestHeaders(), "Content-Type"),
                    "text/plain")) {
                send(ex, 415, "text/plain required");
                return;
            }

            byte[] body = readBounded(ex);
            if (body.length > MAX_BODY) {
                send(ex, 413, "body too large");
                return;
            }
            String text = new String(
                    body, StandardCharsets.UTF_8);
            send(ex, 200, text.isEmpty() ? "(empty)" : text);
        }
    }

    private void upper(HttpExchange ex) throws IOException {
        try (ex) {
            if (!only(ex, "POST", "/tools/upper")) return;
            if (!authorized(ex)) {
                send(ex, 403, "forbidden");
                return;
            }
            if (!mediaType(oneHeader(
                    ex.getRequestHeaders(), "Content-Type"),
                    "text/plain")) {
                send(ex, 415, "text/plain required");
                return;
            }

            byte[] body = readBounded(ex);
            if (body.length > MAX_BODY) {
                send(ex, 413, "body too large");
                return;
            }
            String input = new String(
                    body, StandardCharsets.UTF_8);
            send(ex, 200, input.toUpperCase(Locale.ROOT));
        }
    }

    private void webhook(HttpExchange ex) throws IOException {
        try (ex) {
            if (!only(ex, "POST", "/webhook")) return;
            if (!mediaType(oneHeader(
                    ex.getRequestHeaders(), "Content-Type"),
                    "application/json")) {
                send(ex, 415, "application/json required");
                return;
            }

            byte[] body = readBounded(ex);
            if (body.length > MAX_BODY) {
                send(ex, 413, "body too large");
                return;
            }

            Headers request = ex.getRequestHeaders();
            String timestamp = oneHeader(
                    request, "X-Webhook-Timestamp");
            String id = oneHeader(request, "X-Webhook-Id");
            String signature = oneHeader(
                    request, "X-Webhook-Signature");

            if (timestamp == null
                    || !timestamp.matches("[0-9]{1,16}")
                    || id == null
                    || !id.matches("[A-Za-z0-9_-]{1,80}")
                    || signature == null
                    || !signature.matches("sha256=[0-9a-f]{64}")) {
                send(ex, 400, "invalid webhook headers");
                return;
            }

            long now = Instant.now().getEpochSecond();
            long claimed = Long.parseLong(timestamp);
            if (claimed < now - MAX_SKEW_SECONDS
                    || claimed > now + MAX_SKEW_SECONDS) {
                send(ex, 401, "stale webhook");
                return;
            }

            try {
                byte[] supplied = HexFormat.of().parseHex(
                        signature.substring("sha256=".length()));
                if (!MessageDigest.isEqual(
                        hmac(timestamp, id, body), supplied)) {
                    send(ex, 401, "bad signature");
                    return;
                }
            } catch (Exception problem) {
                send(ex, 401, "cannot verify signature");
                return;
            }

            usedIds.entrySet().removeIf(
                    entry -> entry.getValue()
                            < now - 2 * MAX_SKEW_SECONDS);
            if (usedIds.size() >= MAX_IDS) {
                send(ex, 503, "replay cache full");
                return;
            }
            if (usedIds.putIfAbsent(id, now) != null) {
                send(ex, 409, "duplicate event");
                return;
            }

            accepted.incrementAndGet(); // Only local demo.
            send(ex, 202, "accepted");
        }
    }

    private static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    private static HttpResponse<String> call(
            HttpClient client, HttpRequest req) throws Exception {
        return client.send(
                req,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    private static HttpRequest textPost(
            URI uri, String body, String token) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .header(
                    "Content-Type", "text/plain; charset=utf-8")
                .header("X-Local-Token", token)
                .POST(HttpRequest.BodyPublishers.ofString(
                    body, StandardCharsets.UTF_8))
                .build();
    }

    private HttpRequest webhookRequest(
            URI uri, String timestamp, String id,
            String json, String signature) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .header("X-Webhook-Timestamp", timestamp)
                .header("X-Webhook-Id", id)
                .header("X-Webhook-Signature", signature)
                .POST(HttpRequest.BodyPublishers.ofString(
                        json, StandardCharsets.UTF_8))
                .build();
    }

    public static void main(String[] args) throws Exception {
        LocalWebhookLab lab = new LocalWebhookLab();

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService pool =
                Executors.newFixedThreadPool(4);
        server.setExecutor(pool);
        server.createContext("/health", lab::health);
        server.createContext("/echo", lab::echo);
        server.createContext("/tools/upper", lab::upper);
        server.createContext("/webhook", lab::webhook);
        server.createContext("/", ex -> {
            try (ex) { send(ex, 404, "not found"); }
        });
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(10))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            URI base = URI.create(
                "http://127.0.0.1:"
                    + server.getAddress().getPort());

            String token = HexFormat.of().formatHex(
                    lab.localToken);

            HttpResponse<String> health = call(
                client,
                HttpRequest.newBuilder(base.resolve("/health"))
                    .timeout(Duration.ofSeconds(10))
                    .GET().build());

            check(health.statusCode() == 200
                    && health.body().equals("ok"), "health");
            System.out.println(
                    "healthStatus=" + health.statusCode());

            HttpResponse<String> echo = call(
                client,
                textPost(
                    base.resolve("/echo"), "Hà Nội 🌏", token));
            check(echo.statusCode() == 200
                    && echo.body().equals("Hà Nội 🌏"), "echo");
            System.out.println(
                    "echoStatus=" + echo.statusCode());
            System.out.println("echoBody=" + echo.body());

            HttpResponse<String> upper = call(
                client,
                textPost(
                    base.resolve("/tools/upper"),
                    "Hà Nội 🌏", token));
            check(upper.statusCode() == 200
                    && upper.body().equals("HÀ NỘI 🌏"), "upper");
            System.out.println(
                    "toolStatus=" + upper.statusCode());
            System.out.println("toolBody=" + upper.body());

            HttpResponse<String> unauthorized = call(
                client,
                HttpRequest.newBuilder(base.resolve("/tools/upper"))
                    .header("Content-Type", "text/plain")
                    .POST(HttpRequest.BodyPublishers.ofString("hello"))
                    .build());
            check(unauthorized.statusCode() == 403, "local token");
            System.out.println(
                "unauthToolStatus=" + unauthorized.statusCode());

            String now = Long.toString(
                    Instant.now().getEpochSecond());
            String json =
                    "{\"event\":\"paid\",\"city\":\"Hà Nội\"}";
            byte[] body = json.getBytes(StandardCharsets.UTF_8);

            String signed = lab.sign(
                    now, "event-1", body);
            HttpRequest first = lab.webhookRequest(
                    base.resolve("/webhook"),
                    now, "event-1", json, signed);

            HttpResponse<String> accepted = call(client, first);
            check(accepted.statusCode() == 202, "accepted webhook");
            System.out.println(
                "webhookAcceptedStatus=" + accepted.statusCode());

            HttpResponse<String> replayed = call(client, first);
            check(replayed.statusCode() == 409, "replay");
            System.out.println(
                "webhookReplayStatus=" + replayed.statusCode());

            String signedOther = lab.sign(
                    now, "event-2", body);
            HttpResponse<String> tampered = call(
                client,
                lab.webhookRequest(
                    base.resolve("/webhook"),
                    now, "event-2",
                    "{\"event\":\"replaced\"}",
                    signedOther));
            check(tampered.statusCode() == 401, "tampered body");
            System.out.println(
                "webhookTamperedStatus=" + tampered.statusCode());

            String old = Long.toString(
                Instant.now().minusSeconds(600).getEpochSecond());
            HttpResponse<String> expired = call(
                client,
                lab.webhookRequest(
                    base.resolve("/webhook"),
                    old, "event-3", json,
                    lab.sign(old, "event-3", body)));
            check(expired.statusCode() == 401, "stale");
            System.out.println(
                "webhookExpiredStatus=" + expired.statusCode());

            HttpResponse<String> oversized = call(
                client,
                lab.webhookRequest(
                    base.resolve("/webhook"),
                    now, "event-4",
                    "x".repeat(3000), signed));
            check(oversized.statusCode() == 413, "body limit");
            System.out.println(
                "webhookOversizeStatus=" + oversized.statusCode());

            HttpResponse<String> wrongType = call(
                client,
                HttpRequest.newBuilder(base.resolve("/webhook"))
                    .header("Content-Type", "text/plain")
                    .POST(HttpRequest.BodyPublishers.ofString("{}"))
                    .build());
            check(wrongType.statusCode() == 415, "media type");
            System.out.println(
                "webhookBadTypeStatus=" + wrongType.statusCode());

            HttpResponse<String> wrongMethod = call(
                client,
                HttpRequest.newBuilder(base.resolve("/webhook"))
                    .GET().build());
            check(wrongMethod.statusCode() == 405, "method");
            System.out.println(
                "webhookMethodStatus=" + wrongMethod.statusCode());

            check(lab.accepted.get() == 1, "accepted once");
            System.out.println(
                "acceptedEvents=" + lab.accepted.get());
        } finally {
            server.stop(0);
            pool.shutdownNow();
        }
    }
}
```

### 10.2. Biên dịch và chạy

Lưu file bằng UTF-8, mở terminal ở thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 LocalWebhookLab.java
java LocalWebhookLab
```

- Chạy trên JDK 17+.
- Không cần `--enable-preview`.
- `HexFormat`, `record` (không dùng trong demo), `String.repeat`, `HttpClient` và `HttpServer` đều đã có trên Java17.
- `HttpClient` trên Java17 **chưa phải AutoCloseable** theo API target, vì vậy code không đặt `HttpClient` vào try-with-resources. `HttpExchange` thì implements `AutoCloseable`.
- Test client và server cùng process, khóa HMAC/token chỉ nằm trong RAM và không in ra ngoài.
- Port được OS tự chọn; chương trình có `finally` để đóng server và pool.

### 10.3. Stdout đã thực thi

**Chương trình đã biên dịch thành công bằng `javac --release 17` và chạy trên OpenJDK 24.** Kết quả:

```text
healthStatus=200
echoStatus=200
echoBody=Hà Nội 🌏
toolStatus=200
toolBody=HÀ NỘI 🌏
unauthToolStatus=403
webhookAcceptedStatus=202
webhookReplayStatus=409
webhookTamperedStatus=401
webhookExpiredStatus=401
webhookOversizeStatus=413
webhookBadTypeStatus=415
webhookMethodStatus=405
acceptedEvents=1
```

Đây là **14 dòng stdout đã kiểm chứng** từ một lượt chạy, không chứa cổng ngẫu nhiên hoặc secret.

**Giải thích ý nghĩa:**
- `healthStatus=200`: GET health endpoint hoạt động.
- `echoStatus=200`/`echoBody=Hà Nội 🌏`: request đã có token và nội dung Unicode được echo đúng.
- `toolStatus=200`/`toolBody=HÀ NỘI 🌏`: công cụ uppercase với `Locale.ROOT` hoạt động.
- `unauthToolStatus=403`: thiếu local token, công cụ nội bộ không chạy.
- `webhookAcceptedStatus=202`: header format/timestamp/HMAC/raw body hợp lệ, event ID mới.
- `webhookReplayStatus=409`: gửi lại cùng event ID trong cửa sổ test bị từ chối **theo chính sách demo**.
- `webhookTamperedStatus=401`: thay body khi vẫn dùng HMAC của body trước đó → signature mismatch.
- `webhookExpiredStatus=401`: chữ ký đúng nhưng timestamp đã cũ 600 giây, ngoài tolerance 300 giây.
- `webhookOversizeStatus=413`: body 3000 bytes vượt `MAX_BODY=2048`.
- `webhookBadTypeStatus=415`: một POST không phải JSON media type bị chặn.
- `webhookMethodStatus=405`: GET trên route chỉ cho POST bị từ chối.
- `acceptedEvents=1`: chỉ có một sự kiện tới được nhánh `accepted.incrementAndGet()`; đây **không** phải xử lý giao dịch production.

**Lưu ý:** endpoint `/webhook` không thực sự parse JSON, không lưu vào DB, không gọi service thanh toán và không có TLS. Đây là sandbox minh họa cho **phần nhận/xác minh HTTP webhook**, không phải webhook receiver production hoàn chỉnh.

## 11. Vì sao những dòng code này quan trọng?

### 11.1. Đọc đúng bytes và ngăn request quá lớn

`readBounded()` gọi:

```java
try (var in = ex.getRequestBody()) {
    return in.readNBytes(MAX_BODY + 1);
}
```

Hàm trả nhiều nhất `2049` bytes. Nếu dài hơn `2048`, handler trả `413` và không tiếp tục parse. Đọc thêm 1 byte là để phân biệt “đúng giới hạn” và “vượt giới hạn”, không cắt âm thầm rồi nhận nội dung sai.

**Không dùng `Content-Length` làm giới hạn duy nhất:** request có thể chunked hoặc không có header, proxy có thể giải nén trước khi chuyển tới ứng dụng. Khi file upload lớn hoặc body compression, cần limit tại reverse proxy, ingress và sau giải nén. Với stream input của JDK, việc đóng sớm có thể làm connection reuse bị ảnh hưởng, không được hiểu rằng server đã đọc sạch mọi bytes còn lại.

### 11.2. Header lặp và định dạng

`oneHeader(...)` chỉ cho phép một giá trị với header có ý nghĩa bảo mật. `timestamp` chỉ gồm digits ASCII, event ID chỉ gồm chữ/số/`_`/`-`, chữ ký có prefix `sha256=` và **64 hex lowercase chars**. Điều này hạn chế chuỗi mơ hồ và kích thước signature bất thường.

**Không tự suy đây là header format của mọi provider.** Một số webhook sender có nhiều signature values trong một header trong giai đoạn secret rotation; lúc đó phải parse theo đúng format chính thức và verify tất cả active candidates theo policy.

### 11.3. Thứ tự chống giả mạo trước side effect

Webhook handler:
1. Kiểm tra method/path.
2. Kiểm tra JSON media type.
3. Đọc body có giới hạn.
4. Kiểm tra header formats.
5. Kiểm tra timestamp khoảng ±300 giây.
6. HMAC trên timestamp + ID + raw body, so sánh bytes.
7. Dọn replay cache và từ chối duplicate ID.
8. Mới tăng accepted counter và gửi 202.

**Không đổi thứ tự** theo kiểu cập nhật DB trước rồi mới verify HMAC, hoặc lưu event ID chưa xác thực vào dedup store và làm hết quota. Có thể thực hiện schema validation trước hoặc sau signature tùy threat model và cost, nhưng phải tránh processing side effects trước authentication.

### 11.4. Tạo response và đóng exchange

`send(...)` đặt `Content-Type`, `Cache-Control`, `X-Content-Type-Options` **trước** `sendResponseHeaders`, ghi **đúng UTF-8 byte count**, và đóng output stream. Mỗi handler dùng `try (ex)` để dọn request/response ngay cả khi có exception. Trên connection đứt giữa chừng, có thể không gửi được error status mới; application không được cố gửi 500 sau khi headers đã commit.

### 11.5. Đóng executor/server

`server.stop(0)` và `pool.shutdownNow()` trong `finally` hợp lý cho một integration test nội bộ đã kết thúc. Với process production, cần `stop(delaySeconds)` theo chính sách, `shutdown()` + await termination có deadline, bảo đảm các event đã được nhận/queued hoàn tất hoặc được retry idempotently. Không dừng đột ngột một webhook processor đang ghi DB.

## 12. Khi nào cần đưa webhook local ra ngoài máy?

**Webhook publisher trên Internet không thể gọi trực tiếp vào `127.0.0.1` của máy developer**, vì `127.0.0.1` trên máy sender là chính máy sender. Để nhận callbacks từ external provider trong quá trình phát triển, các lựa chọn gồm:
- Dùng staging endpoint HTTPS với xác thực và chính sách network phù hợp.
- Dùng tunnel HTTPS được tổ chức cho phép; tunnel forward tới loopback listener.
- Dùng webhook CLI/fixture hoặc chức năng test delivery chính thức của provider.
- Tạo delivery simulation trong integration tests nội bộ như `LocalWebhookLab`.

Khi dùng tunnel, URL public có thể bị dò quét. **Không mang route `/tools/upper`, `/echo` hoặc route admin lên cùng tunnel công khai** nếu không thật sự được ủy quyền và bảo vệ. Một reverse proxy có thể chỉ forward `/webhook`, giới hạn request size, IP/rate limits và đặt TLS; receiver vẫn phải xác minh signature. Không gửi secrets cho chatbot/tài liệu/logs và không cố mở port public chỉ để “test nhanh”.

Nếu **phát webhook** tới callback URL do người dùng khai, còn có nguy cơ SSRF (ví dụ localhost, private/metadata IP). Cần URL scheme allowlist, DNS/IP resolution checks trên connect, deny internal IP ranges, redirect policy, egress limits và authentication. Mã bài này là **receiver** và **không** nhận arbitrary callback URLs để tự gửi request.

## 13. Nâng từ lab lên công cụ nội bộ có thể vận hành

### 13.1. Application architecture

```text
HTTPS ingress / API gateway (if needed)
               |
       Authentication + rate limit
               |
         HttpServer handlers
               |
         Bounded request bytes
               |
    Webhook verifier / local tool auth
               |
           Schema validation
               |
       Durable idempotency store
               |
         Queue / background worker
               |
       Business action + outbox
               |
       Response 2xx when accepted
```

Đây là kiến trúc tham khảo, **không phải chức năng đã được ví dụ triển khai**. Nếu cần long-running queue/worker, phải có môi trường vận hành và persistence, không spawn thread vô hạn cho mỗi webhook.

### 13.2. Secrets và tính minh bạch của tests

- Mỗi integration nên có signing secret riêng; không commit vào Git/test fixtures.
- Khi rotate secret, có key ID/version, khoảng thời gian overlap được duyệt.
- Nếu secret bị lộ, revoke, xoay khóa và đánh giá event forging trong quá khứ.
- Không log `Authorization`, `X-Local-Token`, HMAC signature hay raw JSON có PII.
- Test không dùng production secrets hoặc callbacks tới địa chỉ bên ngoài.
- Một mock server trong integration tests nên fail/stop nếu có request bất ngờ thay vì chấp nhận mọi path.

### 13.3. Idempotency, retry và ordering

Webhook publishers thường delivery **at least once**:
- Event có thể đến nhiều lần, đến trễ hoặc đảo thứ tự.
- Response 5xx/timeout thường làm publisher retry; giao thức của từng provider quy định lịch retry khác nhau.
- Dùng event ID từ **metadata đã xác thực**, unique constraint trên database/queue và business transaction.
- Không suy “event A rồi B” từ thứ tự HTTP nhận được.
- Nếu nghiệp vụ không thể rollback, cân nhắc outbox/saga/compensating action.
- Handler nên phản hồi sớm sau khi **durably accepted** thay vì chờ xử lý quá lâu rồi timeout.

### 13.4. Monitoring

Ghi nhận (không rò secrets):
- Requests/s, 2xx/4xx/5xx, 401 signature failures, 413/415, handler latency.
- Số duplicate events, cache/database conflict rate, queue depth, retry count.
- Body bytes, connection pool saturation, thread/executor utilization.
- Clock drift/NTP health nếu dùng timestamp freshness.
- Shutdown và số inflight jobs còn lại.
- Correlation ID được sanitize/bounded.

Không gắn raw event ID, payload hay secret vào metrics labels có cardinality vô hạn. Nếu log event IDs phục vụ audit, áp dụng chính sách retention và PII phù hợp.

### 13.5. Concurrency và shared state

`HttpServer` có thể xử lý nhiều exchanges song song khi dùng executor. Mã bài dùng:
- `AtomicInteger` để đếm event trong một JVM.
- `ConcurrentHashMap.putIfAbsent` để tránh hai requests cùng event ID được nhận đồng thời trong một process.
- `Mac` mới cho mỗi lần verify, tránh share mutable cryptographic state.

Nhưng `ConcurrentHashMap.size()` rồi insert **không phải một quota atomic tuyệt đối** dưới tải song song; demo cache không thể thay thế Redis/DB với TTL/unique key, và không xử lý multiple JVM. Với production, dùng durable store có isolation/atomic uniqueness, bounded resource budgets và load tests.

## 14. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Bind `0.0.0.0` cho lab. | Vô tình expose endpoint ra LAN/Internet. | Bind `127.0.0.1`; khi cần public, qua gateway/TLS và review. |
| Coi localhost là authentication. | Local processes/browser abuse. | Token/OS isolation + method/path allowlist. |
| Sử dụng `Content-Length` làm quota duy nhất. | Chunked/mismatched headers và DoS. | Bounded stream read, proxy/app limits. |
| `readAllBytes()` trên body không giới hạn. | Heap/memory pressure. | `readNBytes(MAX+1)` hoặc bounded InputStream. |
| Dùng `GET` cho endpoint có side effects. | CSRF/caching/crawler có thể kích hoạt. | Method theo semantics, POST + authz/CSRF policy. |
| Dùng query string để truyền local token. | Tokens lộ trong logs/history. | Header và secret storage phù hợp. |
| Tin bất kỳ `X-Webhook-Signature` header. | Attacker tự điền header giả. | Tính lại HMAC bằng secret tin cậy. |
| Ký JSON re-serialized thay vì raw body. | Chữ ký sai hoặc kiểm tra không đúng provider. | Verify chính xác signed bytes. |
| Dùng `String.equals` để so sánh HMAC. | Timing side channel không cần thiết. | `MessageDigest.isEqual` trên bytes sau format validation. |
| Ký timestamp nhưng không ký event ID. | Replay/dedup binding yếu. | Ký cả ID và timestamp nếu tự thiết kế protocol. |
| Đọc timestamp nhưng không đưa vào signed bytes. | Attacker có thể sửa timestamp. | Authenticated timestamp. |
| Lưu replay ID chỉ 5 phút khi chấp nhận ±5 phút. | Timestamp tương lai vẫn hợp lệ sau cache expiry. | Giữ ≥2×tolerance và durable processing records. |
| Lưu event ID trước khi verify. | Attacker làm đầy cache hoặc chặn event thật. | Verify trước dedup insertion. |
| Trả 409 cho duplicate webhook production. | Provider có thể retry vô hạn. | Idempotent 2xx theo provider contract. |
| Dùng in-memory cache làm exactly-once guarantee. | Restart/multiple replicas làm mất dedup. | DB/queue unique constraint durable. |
| Trả 2xx trước khi đã durably accepted. | Nếu crash, mất event mà sender nghĩ đã thành công. | Queue/transaction commit rồi ack. |
| Parse/chạy business action trước signature. | Forged event kích hoạt side effects. | Verify raw body và auth trước. |
| Tái dùng format HMAC demo cho Stripe/GitHub. | Verify sai format/headers. | Provider SDK/signing spec chính thức. |
| Expose endpoint `/exec` chạy lệnh hệ điều hành. | RCE từ request input. | Allowlist các tác vụ thuần dữ liệu; không thực thi shell. |
| Cho phép CORS `*` rồi coi tool an toàn. | CORS không phải authentication. | Authn/authz + CSRF/Origin policy phù hợp. |
| Quên đóng `HttpExchange`/executor. | Leak connection/thread. | try-with-resources/finally, graceful shutdown. |
| Gọi `sendResponseHeaders` hai lần sau lỗi. | Không thể đổi status đã commit. | Lỗi sau commit chỉ log/abort/close. |
| Dùng `try(HttpClient c = ...)` khi compile Java 17. | Java17 `HttpClient` chưa AutoCloseable. | Client lifecycle theo target JDK. |
| So sánh token raw bytes với token hex ASCII. | Authentication luôn thất bại. | Cùng định dạng và dùng constant-time byte compare. |
| Xem demo nhận JSON là đã validate JSON. | Dữ liệu sai schema vẫn đến bước counter. | Sau verify dùng JSON parser/schema validation thật. |

## 15. Bộ kiểm thử mở rộng đáng thực hiện

**Test A — Local binding.** Chỉ có listener trên `127.0.0.1`, không mở unintended interface; chú ý container/network namespace.

**Test B — Port reuse.** Chạy nhiều instances song song với port 0; không conflict; shutdown giải phóng port/threads.

**Test C — Routes.** `/health-extra` hoặc `/webhook-extra` bị 404 theo exact route check; không bị prefix match chấp nhận nhầm.

**Test D — Method.** `GET /webhook` trả 405, `Allow: POST`; POST/method không phù hợp khác cũng bị reject.

**Test E — Authentication.** Thiếu/sai local token trả 403, side effect không chạy. Token không xuất hiện trong stdout/logs.

**Test F — Unicode.** Echo `Hà Nội 🌏` chính xác, uppercase theo `Locale.ROOT`; xử lý invalid UTF-8 bằng decoder `CodingErrorAction.REPORT` ở môi trường production cần strict text validation (demo `new String(byte[],UTF_8)` có thể thay bytes lỗi bằng replacement characters).

**Test G — Bytes budget.** Body đúng `MAX_BODY` được chấp nhận nếu hợp lệ; body `MAX_BODY+1` trả 413; thử Content-Length absent/chunked và compression.

**Test H — Signature positive.** HMAC đúng trên timestamp + ID + raw body trả 202, chỉ một event được đếm.

**Test I — Body tamper.** Dùng signature của JSON A nhưng gửi JSON B (khác whitespace/bytes cũng vậy) phải 401.

**Test J — Timestamp.** Timestamp quá cũ/tương lai ngoài ±300 giây bị 401; test boundary 300/301 giây có kiểm soát đồng hồ giả.

**Test K — Replay.** Gửi lại event ID đã verified, không tăng side effect. Test concurrency hai deliveries cùng ID để chỉ xử lý một lần.

**Test L — Duplicate handling production.** Với durable DB, duplicate trả 2xx idempotent sau khi state đã được commit, không làm publisher retry vô nghĩa.

**Test M — Header format.** Signature không có prefix, hex không đủ 64 chars, ký tự ngoài hex, duplicate headers, event ID quá dài, timestamp nonnumeric đều bị từ chối.

**Test N — Secret rotation.** Trong thời gian overlap, signatures từ active secrets được chấp nhận theo provider spec; revoked secret bị từ chối.

**Test O — HMAC vector.** Kiểm tra `Mac.getInstance("HmacSHA256")` bằng test vector chuẩn độc lập, không chỉ dùng cùng helper ở client và server để tránh shared-bug false positives.

**Test P — Webhook schema.** Sau verify, malformed JSON/schema sai bị 400 và không kích hoạt business action; dùng JSON parser hiện đại (ví dụ Jackson) nếu ứng dụng đã chọn dependency phù hợp.

**Test Q — Retry/failure.** Sau DB/queue failure, không trả success 2xx giả; test idempotent retry và rollback.

**Test R — Slow clients.** Đặt read/request timeouts và concurrency quotas ở tầng vận hành; không để một client gửi 1 byte/phút giữ tài nguyên mãi.

**Test S — Public exposure.** Nếu có tunnel, chỉ expose webhook receiver với HTTPS/TLS và auth, không forward internal tools.

**Test T — SSRF.** Nếu app gửi outbound webhooks tới URL do khách hàng cấu hình, test private/loopback/metadata IP ranges, redirects, DNS rebinding; không liên quan trực tiếp đến local receiver demo.

**Test U — Logs.** Trước mọi error path, bảo đảm không log secret/HMAC/raw body có PII.

**Test V — Graceful shutdown.** Đang có accepted jobs, dừng listener và drain queue theo deadline; không mất event đã ack.

**Test W — Java compatibility.** Chạy trên đúng JDK target 17/21/25, kiểm tra `jdk.httpserver` module, `HttpClient` API và provider crypto.

## 16. Bài tập thực hành

1. **Mock service:** thêm `GET /product/7` trả JSON nhỏ và `GET /product/999` trả 404, assert Content-Type và body. Cần exact route, không dùng arbitrary file paths.
2. **Timeout test:** làm client tạo request với `HttpRequest.timeout(Duration...)`, thử server handler chậm và xác nhận timeout/error cleanup. Không chạy timeouts cực dài trong CI.
3. **Webhook malformed header:** thêm test signature `sha256=abc`, timestamp chữ, event ID không hợp lệ; bảo đảm status 400/401 theo policy và counter giữ nguyên.
4. **Strict UTF-8:** thay `new String(body, UTF_8)` bằng `CharsetDecoder` có `CodingErrorAction.REPORT`, trả 400 cho bytes không hợp lệ.
5. **Replay cache test:** dùng clock được inject (thay vì gọi `Instant.now()` trực tiếp) để thử chính xác cửa sổ ±300 giây và TTL ≥600 giây.
6. **Durable dedup:** dùng in-memory DB trong test hoặc DB thật ở integration environment với unique event ID; xác minh hai workers nhận cùng event không ghi side effect hai lần.
7. **Secret rotation:** hỗ trợ hai keys có key IDs/versions, accept active signatures đúng format; không lưu secrets trong source code.
8. **Schema validation:** sau HMAC pass, parse JSON và chỉ cho phép `event` thuộc allowlist; không tin trường `"paid"` tự cấp quyền thanh toán.
9. **Metrics:** thêm counter cho 2xx/4xx/5xx, HMAC failures và request duration, tránh metric labels từ untrusted values.
10. **Shutdown:** tạo signal/control path không public để stop server gracefully, đợi inflight requests hoàn thành, không cho endpoint admin không có auth.
11. **Browser threat model:** viết test một trang cross-origin thử POST vào localhost, xác nhận token/Origin/CSRF policy chặn side effects, không cho CORS permissive.
12. **Deployment:** so sánh local loopback fixture với staging HTTPS endpoint; ghi rành mạch những layers cần bổ sung khi có public callback.

## 17. Câu hỏi ôn tập

**Câu 1. Khi nào nên dùng `HttpServer` của JDK?**

Khi cần HTTP listener gọn cho integration tests, local utilities hoặc server nội bộ nhỏ có security/operational requirements kiểm soát được. Không mặc định thay thế hạ tầng public gateway.

**Câu 2. Vì sao dùng port 0?**

OS tự chọn port trống để tránh xung đột khi nhiều tests chạy song song; lấy lại bằng `server.getAddress().getPort()`.

**Câu 3. Bind `127.0.0.1` có ngăn mọi người không được phép không?**

Không. Các tiến trình trên cùng máy vẫn có thể truy cập; tunnel/proxy có thể expose loopback. Cần auth/token và trust boundary.

**Câu 4. `HttpServer.createContext` có exact routing không?**

Không mặc định; contexts dùng longest prefix matching. Handler phải kiểm tra URI/method và 404 với đường dẫn sai.

**Câu 5. Trình tự trả status, headers và body là gì?**

Set response headers → `sendResponseHeaders(status,length)` → `getResponseBody()` → write bytes → close response stream/exchange.

**Câu 6. HMAC webhook có nên tính trên JSON đã deserialize rồi serialize lại không?**

Không nếu sender ký raw bytes. Phải dùng đúng signed material theo tài liệu provider, tránh thay đổi whitespace/order/encoding.

**Câu 7. `MessageDigest.isEqual` dùng để làm gì?**

Để so sánh bytes của expected và received MAC/token theo cách thích hợp hơn một phép so sánh String thông thường cho thông tin xác thực.

**Câu 8. Vì sao ký cả timestamp và event ID?**

Timestamp giới hạn tuổi request, ID hỗ trợ deduplication; nếu chúng không được xác thực cùng body, attacker có thể sửa metadata để replay.

**Câu 9. Chỉ kiểm tra chữ ký hợp lệ có chống replay không?**

Không. Một request cũ có chữ ký đúng vẫn có thể gửi lại. Cần freshness + dedup/idempotent processing.

**Câu 10. Vì sao replay cache 300 giây có thể thiếu với tolerance ±300 giây?**

Một timestamp tương lai được chấp nhận ở thời điểm đầu và vẫn hợp lệ trong 600 giây. Nếu ID cache mất quá sớm, replay vẫn qua freshness check.

**Câu 11. Vì sao production không nên trả 409 cho event đã xử lý?**

Một số publishers retry khi non-2xx, gây vòng lặp; thường phản hồi 2xx idempotent cho duplicate đã xử lý theo provider contract.

**Câu 12. Có thể dựa vào `Content-Length` để tránh request quá lớn không?**

Không. Header có thể thiếu hoặc không phản ánh bytes thực/decoded; bounded reading và ingress limits cần thiết.

**Câu 13. Vì sao nên dùng token trên `/tools/upper` dù chỉ bound localhost?**

Bởi local process khác và một số browser-origin threats vẫn tồn tại; token chặn callers không được phép trước khi xử lý input.

**Câu 14. Demo có thực sự xác minh JSON schema và cập nhật đơn hàng không?**

Không. Nó chỉ verify HTTP/HMAC/freshness, đếm một event và trả 202. Schema/business/DB là bước phát triển tiếp.

**Câu 15. Vì sao `AtomicInteger` và `ConcurrentHashMap` không đủ cho event delivery production?**

Chúng chỉ tồn tại trong một process, mất khi restart, không chia sẻ giữa replicas và không thay durable transaction/queue.

**Câu 16. Khác gì giữa webhook receiver và webhook publisher?**

Receiver nhận và xác thực callback. Publisher gửi callback tới URL đã đăng ký; publisher phải phòng SSRF khi URL do khách hàng cung cấp.

**Câu 17. API `HttpClient` Java 17 có thể dùng trong try-with-resources không?**

Không theo API target Java 17; `HttpClient` thời điểm đó chưa implements `AutoCloseable`. Chương trình dùng client trong phạm vi try/finally của server, không trực tiếp `try (client)`.

**Câu 18. Điều gì giúp kiểm thử không phụ thuộc thời gian/port?**

Port 0, assertions trên status/body thay vì port, timestamp tạo ngay trước request; với kiểm thử boundaries chính xác cần inject Clock/fake time.

## 18. Checklist triển khai

- [ ] Xác định rõ server đang phục vụ test fixture, webhook local hay công cụ nội bộ; ghi trust model.
- [ ] Bind `127.0.0.1` và port 0 cho test, không expose public khi chưa được phê duyệt.
- [ ] Dùng `HttpServer`/`HttpExchange` Java17+ với exact path + method checks.
- [ ] Set status/headers trước body, tính `Content-Length` theo UTF-8 bytes và đóng exchange.
- [ ] Giới hạn request body thực bằng read budget, reject bằng 413; thêm timeouts/concurrency limits.
- [ ] Đặt đúng Content-Type, 405 + Allow, 401/403/415, no-store và security headers phù hợp.
- [ ] Bảo vệ internal tools bằng token mạnh, không thực thi shell/file/URL tùy ý từ request.
- [ ] Verify webhook theo **provider signing spec**; với custom lab, ký timestamp + ID + raw body và so sánh HMAC bằng bytes.
- [ ] Giới hạn timestamp freshness, replay, retained IDs và event count; không tin in-memory cache như durable idempotency.
- [ ] Thực hiện side effects chỉ sau authentication + schema validation + idempotency transaction.
- [ ] Với duplicate đã được xử lý, dùng phản hồi idempotent theo quy định sender để không gây retry vô hạn.
- [ ] Lưu/rotate secrets ngoài source code, không log payload chứa PII hoặc signature.
- [ ] Nếu cần Internet delivery, triển khai HTTPS/tunnel được phép, chỉ expose webhook cần thiết; không public hóa local tools.
- [ ] Chống SSRF nếu hệ thống gửi outbound callback tới user-supplied URL.
- [ ] Test positive và negative cases: token thiếu, signature sai, replay, stale, oversized, bad Content-Type/method và Unicode.
- [ ] Dừng server/pool trong finally; production dùng graceful shutdown + durable queue.
- [ ] Kiểm tra JDK/provider/HTTP proxy nếu nâng cấp môi trường.
- [ ] Giữ API Java17+ và tài liệu bảo mật hiện hành; không xây dựng listener dựa vào thư viện legacy thiếu security controls.

## 19. Tham khảo chính thức và bảo mật

- [Java 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): tạo listener, context matching, port, executor, start/stop.
- [Java 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request/response streams, sendResponseHeaders, close semantics, status/body ordering.
- [Java 17 — HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): xử lý một request exchange.
- [Java 17 — Headers](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): set/add/get, case-insensitive header names.
- [Java 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client dùng trong integration tests.
- [Java 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): POST bodies, headers, per-request timeouts.
- [Java 17 — Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): HMAC-SHA256.
- [Java 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): `isEqual` cho MAC/token bytes.
- [Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): sinh secrets ngẫu nhiên trong demo.
- [Java 17 — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): hex encode/decode signatures và token.
- [Java 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `readNBytes`, close và bounded reading.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): status codes, methods, headers và resource semantics.
- [OWASP — Webhook Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Webhook_Security_Cheat_Sheet.html): HMAC verification raw body, replay, idempotency, timestamp, token/secret rotation, SSRF và payload limits.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF/Origin và hạn chế về CORS đối với tools dùng trong browser.
