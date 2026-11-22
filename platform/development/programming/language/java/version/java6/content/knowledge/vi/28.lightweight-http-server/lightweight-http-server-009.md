# Đóng stream, giới hạn nội dung và dừng server với HttpServer trong Java

## 1. Tại sao quản lý vòng đời quan trọng với HTTP server gọn?

`com.sun.net.httpserver.HttpServer` là HTTP server nhỏ có sẵn trong module JDK `jdk.httpserver`. Nó hữu ích cho ứng dụng nhúng, endpoint điều khiển đơn giản, công cụ nội bộ, kiểm thử tích hợp hoặc server nhẹ có yêu cầu được kiểm soát. Tuy API ngắn, xử lý HTTP **không chỉ** là đọc `getRequestBody()` và ghi `getResponseBody()`.

Một handler có thể trả về `200 OK` nhưng vẫn gây vấn đề nếu:

- Không đóng response stream hoặc quên kết thúc `HttpExchange`: connection/worker có thể không được giải phóng.
- Dùng `InputStream.readAllBytes()` với request chưa được giới hạn: client gửi body cực lớn khiến memory bị tiêu hao.
- Tin tuyệt đối vào `Content-Length`: client có thể gửi body không biết trước độ dài hoặc dùng chunked transfer.
- Đặt `sendResponseHeaders(200, text.length())` cho UTF-8: số ký tự khác số **byte**, nên fixed-length response sai.
- Hiểu `responseLength=0` là body rỗng: trong API này **0 có nghĩa chunked transfer**, không phải empty response.
- Gọi `server.stop(0)` khi còn request đang chạy rồi mong mọi request hoàn tất.
- Chỉ gọi `server.stop(delay)` mà không đóng `ExecutorService` do ứng dụng tự tạo.
- Cố gọi `server.start()` để khởi động lại instance đã `stop`: lifecycle không cho phép.
- Bỏ qua path matching dạng prefix hoặc thiếu giới hạn method, concurrency, timeout và request size.

> Quy tắc cốt lõi: **mỗi request phải được đọc có giới hạn, mỗi response phải được kết thúc đúng framing, mỗi exchange phải được đóng, và toàn bộ server/executor phải có trình tự shutdown rõ ràng.**

Bài này dùng Java 17+ với những API **còn hiện hành**: `HttpServer`, `HttpHandler`, `HttpExchange`, `InputStream`/`OutputStream`, `ExecutorService` và `java.net.http.HttpClient` để tự kiểm thử. Các ví dụ tạo HTTP server trên `127.0.0.1`, không mở dịch vụ trên mạng công cộng.

## 2. Cấu trúc và trách nhiệm tài nguyên

~~~text
HttpServer (listening socket, contexts)
    |
    +--- Executor / worker threads
    |       |
    |       +--- HttpHandler.handle(HttpExchange)
    |                    |
    |                    +--- Request headers
    |                    +--- Request InputStream
    |                    +--- Response headers
    |                    +--- Response OutputStream
    |                    |
    |                    +--- Exchange.close()
    |
    +--- HttpServer.stop(delay)
    |
    +--- ExecutorService.shutdown()
            |
            +--- awaitTermination(...)
            +--- shutdownNow() fallback when needed
~~~

Các đối tượng có vòng đời **khác nhau**:

| Đối tượng | Tạo ở đâu | Kết thúc như thế nào |
| --- | --- | --- |
| `HttpServer` | `HttpServer.create(...)` | `server.stop(delay)` |
| `HttpContext` | `server.createContext(...)` | Bị gỡ khi server dừng hoặc chủ động `removeContext` |
| `HttpExchange` | Server chuyển vào `HttpHandler.handle` | `exchange.close()` trong `finally` |
| Request `InputStream` | `exchange.getRequestBody()` | Đóng khi exchange hoàn tất; tiêu thụ đủ khi thích hợp |
| Response `OutputStream` | `exchange.getResponseBody()` | **Đóng sau khi ghi body**; `try-with-resources` rất hữu ích |
| `ExecutorService` tự cấp | `Executors.newFixedThreadPool(...)` | `shutdown()`, `awaitTermination(...)`, có thể `shutdownNow()` |
| Client `HttpResponse` | `HttpClient.send(...)` | `BodyHandlers.ofString` nhận hết body; với streaming handler phải đóng stream client riêng |

**Phân biệt:** `server.stop(delay)` dừng HTTP server, nhưng **không thay thế** vòng đời của executor tùy biến do ứng dụng tạo và các resources khác trong handler như JDBC connection/file stream. Hãy xác định **ai sở hữu tài nguyên và ai có trách nhiệm đóng**.

## 3. Vòng đời đúng của một HttpExchange

Phương thức handler:

~~~java
@Override
public void handle(HttpExchange exchange) throws IOException {
    try {
        // Validate method, path, headers; đọc request body có giới hạn.
        // Chuẩn bị response headers.
        // sendResponseHeaders(...) trước khi ghi response body.
        // Ghi body nếu có và đóng response output stream.
    } finally {
        exchange.close();
    }
}
~~~

Đây là **khung minh họa**, không phải method hoàn chỉnh vì các bước xử lý cần triển khai. Trong JavaDoc hiện hành, `HttpExchange.close()` kết thúc exchange theo thứ tự đóng request input và response output nếu chúng chưa đóng.

### 3.1. Vì sao phải đóng response body stream?

Một HTTP response có điểm kết thúc. Với fixed-length framing, client trông đợi **đúng số byte**; với chunked transfer, stream phải được đóng để hoàn tất truyền tải. Nếu handler cứ giữ `OutputStream` mở:

- Client có thể chờ body mãi.
- Connection tiếp tục chiếm socket.
- Worker đang xử lý exchange có thể không được giải phóng đúng cách.
- Server có thể gặp khó khăn khi shutdown.
- Những request tiếp theo trên cùng keep-alive connection có thể không được xử lý đúng.

Mẫu ghi response:

~~~java
byte[] body = message.getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(status, body.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(body);
}
~~~

**Chỉ dùng khi `body.length > 0`**; đoạn trên là snippet có biến `message`, `status` và `exchange`. Khi body rỗng cần xử lý `-1` thay vì `0` nếu không muốn dùng chunked framing.

### 3.2. Request stream có cần đọc hết không?

JavaDoc `HttpExchange` khuyến nghị tiêu thụ hết request body trước khi đóng khi thực sự cần tái sử dụng connection. Đóng `getResponseBody()` cũng có thể đóng request `InputStream`. Nếu request input chưa được đọc hết:

- Việc đóng request stream có thể đọc rồi bỏ **một lượng bytes nhất định do implementation quy định**.
- Connection có thể không còn dùng lại được cho exchange tiếp theo.
- Không được suy luận rằng `close()` luôn drain toàn bộ body lớn của client.
- Đặc biệt khi phát hiện request quá lớn, **không đọc vô hạn chỉ để giữ keep-alive**. Có thể phản hồi `413` và chủ động yêu cầu đóng connection.

Điểm cân bằng: **request hợp lệ** nên được xử lý hết theo framing của HTTP; **request quá giới hạn** cần dừng có kiểm soát, không hy sinh an toàn bộ nhớ hoặc CPU chỉ để cố reuse connection.

### 3.3. Dùng `finally` để không bỏ sót exception

~~~java
public void handle(HttpExchange exchange) throws IOException {
    try {
        // Handle a request.
    } finally {
        exchange.close();
    }
}
~~~

Đây là snippet. `finally` vẫn chạy nếu code trả sớm do method không được hỗ trợ hoặc request bị từ chối. Nếu response output stream đã được đóng ở `try-with-resources` thì `exchange.close()` là cơ chế cleanup cuối cùng.

Không nên viết:

~~~java
exchange.sendResponseHeaders(200, 5);
exchange.getResponseBody().write(
        "hello".getBytes(StandardCharsets.UTF_8));
// Sai: quên đóng output/exchange.
~~~

Đây là anti-pattern. Trên một request thử nghiệm nhỏ, client có thể vẫn đọc được 5 bytes rồi trông như đúng, nhưng không vì vậy mà lifecycle hoàn chỉnh được bảo đảm.

## 4. `sendResponseHeaders` và số byte response

API trọng tâm:

~~~java
exchange.sendResponseHeaders(int statusCode, long responseLength);
~~~

Đây là chữ ký gọi minh họa. Cách hiểu của Java `HttpExchange`:

| `responseLength` | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| **> 0** | Fixed-length body; phải ghi **đúng số byte** | Response byte array/string đã encode |
| **= 0** | Sử dụng **chunked transfer encoding**; số byte tùy ý | Streaming response không biết trước chiều dài |
| **<= -1** | **Không gửi response body** | Body rỗng hoặc status/method không cho body |

Các bản JDK mới có thể khai báo các constant thuận tiện cho empty/chunked, nhưng **`0` và `-1` vẫn là giá trị tương thích Java 17** trong ví dụ.

### 4.1. Không nhầm `String.length()` với số UTF-8 bytes

Sai:

~~~java
String message = "Xin ch\u00E0o";
exchange.sendResponseHeaders(200, message.length());
// Sai nếu dùng UTF-8: chữ có dấu có thể chiếm nhiều byte.
~~~

Đây là snippet cố ý sai ở tham số độ dài, không phải phương pháp hoàn chỉnh. Đúng:

~~~java
String message = "Xin ch\u00E0o";
byte[] body = message.getBytes(StandardCharsets.UTF_8);
exchange.sendResponseHeaders(200, body.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(body);
}
~~~

Chuỗi `"Xin chào"` có **8 ký tự Java** nhưng **9 bytes UTF-8**. Tùy nội dung, còn có Unicode code points cần hai UTF-16 code units; vì vậy đếm ký tự bằng `String.length()` càng không thể dùng làm HTTP body byte length.

**Lưu ý:** Java source của ví dụ dùng escape `\u00E0` cho chữ `à`, nên ngay cả công cụ ghi file source với encoding ASCII vẫn biên dịch ra đúng chuỗi Unicode. Đây là chủ ý để kiểm thử byte length ổn định trên các môi trường.

### 4.2. Số byte cố định phải được ghi chính xác

Nếu khai báo fixed response length 5:

~~~java
exchange.sendResponseHeaders(200, 5);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(new byte[] {1, 2, 3, 4, 5});
}
~~~

Đây là snippet trong handler hợp lệ; đúng vì **5 bytes được ghi**. Nếu ghi 6 bytes, write có thể ném `IOException`. Nếu chỉ ghi 4 bytes, `OutputStream.close()` có thể ném `IOException`; exchange bị abort, TCP connection có thể bị đóng. Đừng catch lỗi đó rồi âm thầm báo request thành công.

### 4.3. Vì sao `0` không phải “empty body”?

~~~java
exchange.sendResponseHeaders(200, 0);
~~~

Theo JavaDoc, `0` yêu cầu **chunked transfer**. Nếu muốn response thật sự không có body:

~~~java
exchange.sendResponseHeaders(204, -1);
exchange.getResponseBody().close();
~~~

Đây là snippet cho `204 No Content`. Trường hợp `HEAD` cũng không gửi body:

~~~java
exchange.sendResponseHeaders(200, -1);
exchange.getResponseBody().close();
~~~

Trong production, cần tuân thủ semantics HTTP về `HEAD` và status như `1xx`, `204`, `304`; đừng gửi body khi bị cấm. Nếu làm HEAD song song với GET, headers biểu diễn metadata của tài nguyên phải phù hợp contract, còn thân response không được gửi. Chương trình chính minh họa `HEAD /status` trả `200` và body length 0.

### 4.4. Streaming response chưa biết độ dài

Nếu tạo response lớn theo từng phần:

~~~java
exchange.getResponseHeaders().set(
        "Content-Type", "application/octet-stream");
exchange.sendResponseHeaders(200, 0); // chunked
try (OutputStream out = exchange.getResponseBody()) {
    writeChunks(out); // Hàm do ứng dụng định nghĩa.
}
~~~

Đây là snippet; `writeChunks` không phải API JDK có sẵn. Vì chunked cho phép số byte tùy ý, bạn **vẫn cần đặt giới hạn tổng output**, timeout và cancellation theo nghiệp vụ để tránh stream vô hạn.

### 4.5. Headers phải thiết lập trước khi commit response

Mẫu đúng:

~~~java
exchange.getResponseHeaders().set(
        "Content-Type", "application/json; charset=utf-8");
exchange.getResponseHeaders().set("Cache-Control", "no-store");
exchange.sendResponseHeaders(200, length);
~~~

Sau `sendResponseHeaders(...)`, HTTP status/headers đã được gửi. Đừng tiếp tục sửa headers hoặc cố gọi `sendResponseHeaders(500,...)` lần thứ hai nếu đang ghi body mà gặp lỗi. Một response chỉ được commit một lần.

## 5. Giới hạn request body: phải giới hạn **bytes thực đọc**

Một sai lầm phổ biến:

~~~java
byte[] body = exchange.getRequestBody().readAllBytes();
if (body.length > MAX_BYTES) {
    // Đã quá muộn: body lớn có thể đã được cấp phát hết vào RAM!
}
~~~

Mã này không phù hợp với request chưa tin cậy. Với file/upload/binary payload lớn, attacker có thể khiến app cấp phát memory ngoài budget trước khi kiểm điều kiện.

**Cách tốt hơn:** chỉ đọc tối đa `MAX_BYTES + 1` bytes, để phân biệt:

- Kết thúc input trước hoặc đúng `MAX_BYTES`: chấp nhận.
- Đọc được byte thứ `MAX_BYTES+1`: request quá lớn, trả `413 Content Too Large` (tên cũ “Payload Too Large” vẫn thường thấy trong logs/client), đóng connection nếu không consume hết.

### 5.1. Hàm đọc giới hạn và phát hiện byte vượt ngưỡng

~~~java
record LimitedBody(byte[] data, boolean tooLarge) {}

static LimitedBody readBounded(InputStream input, int limit)
        throws IOException {
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    byte[] buffer = new byte[8];
    while (true) {
        int take = Math.min(
                buffer.length, limit + 1 - bytes.size());
        int n = input.read(buffer, 0, take);
        if (n == -1) {
            return new LimitedBody(bytes.toByteArray(), false);
        }
        bytes.write(buffer, 0, n);
        if (bytes.size() > limit) {
            return new LimitedBody(new byte[0], true);
        }
    }
}
~~~

Đây là helper từ chương trình đầy đủ. Giả định `0 <= limit < Integer.MAX_VALUE` để phép `limit+1` không overflow và `InputStream` đọc theo contract bình thường. Trong dự án thật, validate limit và dùng biến `long` nếu có thể nhận dữ liệu lớn hơn giới hạn `int`.

**Đặc tính:**

- Bộ nhớ cho dữ liệu được lưu không vượt quá **`limit+1` bytes**, ngoài overhead của buffer và `ByteArrayOutputStream`.
- Hàm không đọc đến EOF khi đã phát hiện byte vượt giới hạn.
- Một request không có `Content-Length` vẫn bị kiểm tra bằng bytes thực tế.
- Do body được dùng dưới dạng bytes, không nhầm ký tự/UTF-8 code units với bytes.
- Trả về `tooLarge` thay vì cố trả những bytes không hợp lệ để xử lý nghiệp vụ.

Nếu workload là upload file lớn hợp lệ, không nên giữ toàn bộ body trong `ByteArrayOutputStream`: streaming ra file/object store tạm với byte counter/checksum và abort nếu quá max sẽ phù hợp hơn. Khi upload thất bại, dọn file tạm và không đưa nội dung thiếu vào xử lý chính.

### 5.2. Content-Length chỉ là kiểm tra sớm

Client có thể gửi:

~~~text
Content-Length: 40
~~~

Nếu giới hạn của endpoint là 32 bytes, server có thể từ chối **trước khi đọc** body. Nhưng không nên chỉ làm:

~~~java
long size = Long.parseLong(
        exchange.getRequestHeaders().getFirst("Content-Length"));
if (size <= 32) {
    processBodyWithoutCounting(); // Sai: tin header là nguồn duy nhất.
}
~~~

Đây là anti-pattern; `processBodyWithoutCounting` là hàm minh họa, không phải API sẵn có. Bởi vì:

- HTTP/1.1 có request body **không biết trước độ dài** dùng `Transfer-Encoding: chunked`.
- `Content-Length` có thể không xuất hiện.
- Một gateway/proxy có thể xử lý/chuyển đổi framing theo đường đi.
- Không nên tự xây HTTP parser riêng để xử lý header mâu thuẫn; trách nhiệm đó thuộc HTTP implementation/gateway.
- Với server API, **luôn đếm bytes thực đọc** từ `getRequestBody()` để thực thi max body size của ứng dụng.

Chương trình demo kiểm tra `Content-Length` nếu có để có thể trả 413 sớm, nhưng **bất kể header thế nào vẫn gọi `readBounded`** cho request đã qua kiểm tra sớm.

### 5.3. Xử lý body quá lớn và keep-alive

Khi phát hiện byte thứ 33 (với max 32):

~~~java
exchange.getResponseHeaders().set("Connection", "close");
respond(exchange, 413, "request too large");
return;
~~~

Đây là snippet ở handler. Header `Connection: close` được gửi **trước** `sendResponseHeaders`. Cách này giảm kỳ vọng reuse connection khi body request còn chưa consume hết.

Tuy nhiên cần hiểu đúng:

- `Connection: close` thể hiện ý định kết thúc kết nối sau exchange; đó là lựa chọn ứng dụng/JDK implementation, không thay thế network timeouts.
- JavaDoc nói khi đóng input chưa đọc hết, implementation có thể **discard thêm một số bytes**, không cam kết drain toàn bộ.
- Nếu client gửi body rất chậm, **byte cap không tự áp timeout**, nên cần giới hạn socket/read deadline, reverse proxy hoặc server phù hợp production.
- Nếu client đang gửi request body lớn, response 413 sớm có thể dẫn tới connection close/reset phía client; test integration nên dự kiến điều này thay vì giả định client chắc chắn luôn nhận một body lỗi đầy đủ.
- Không cố drain một body không giới hạn chỉ để giữ keep-alive.

### 5.4. Các giới hạn khác ngoài body bytes

Giới hạn body chỉ là một phần phòng ngừa abuse:

| Giới hạn | Rủi ro nếu bỏ qua | Cách xử lý |
| --- | --- | --- |
| Request body bytes | Memory/IO DoS | Đếm từng byte, ngừng khi vượt max |
| Number/size of headers | Header abuse | Reverse proxy/framework/runtime limits |
| URL path/query length | Routing/log memory abuse | Gateway / URL-validation |
| Request duration | Slowloris / kết nối giữ lâu | Socket/proxy read timeout và deadline |
| Concurrent requests | Thread pool exhaustion | Giới hạn concurrency, bounded work queue, backpressure |
| Response bytes | Streaming dữ liệu vô hạn | Precompute/max output bytes hoặc bounded stream |
| Decompressed bytes | Compression bombs | Giới hạn **sau giải nén** nếu chấp nhận Content-Encoding |
| JSON/XML nesting | CPU/memory parsing | Parser depth/element count limits |
| File upload temp storage | Disk exhaustion | Quota, cleanup, file size and timeout |
| Client idle timeout | Kết nối chiếm socket | HTTP front proxy/runtime settings |

`HttpServer` là server nhỏ; với môi trường public/high traffic, thường cần reverse proxy/API gateway và HTTP stack có quotas, timeouts, TLS, header limits, observability được cấu hình rõ. Không tự quảng bá nó như một server production đầy đủ chỉ nhờ có `readBounded`.

## 6. Đóng stream đúng với từng loại phản hồi

### 6.1. Thành công với fixed-length body

~~~java
static void respond(
        HttpExchange exchange, int status, String message)
        throws IOException {
    byte[] body = message.getBytes(StandardCharsets.UTF_8);
    exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=utf-8");
    exchange.sendResponseHeaders(
            status, body.length == 0 ? -1 : body.length);
    try (OutputStream out = exchange.getResponseBody()) {
        out.write(body);
    }
}
~~~

Đây là helper đầy đủ về response stream: fixed length nếu body >0, không body nếu empty. Demo chính bổ sung max response 128 bytes, `Cache-Control: no-store`.

### 6.2. Early return vì method không hợp lệ

~~~java
if (!"POST".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "POST");
    respond(exchange, 405, "use POST");
    return;
}
~~~

Nên gửi `Allow` cho 405, thông báo method endpoint hỗ trợ. `finally { exchange.close(); }` của handler vẫn chạy sau `return`.

### 6.3. Early return vì body quá lớn

~~~java
if (request.tooLarge()) {
    exchange.getResponseHeaders().set(
            "Connection", "close");
    respond(exchange, 413, "request too large");
    return;
}
~~~

Đóng exchange để không giữ request/response streams. Không gọi tiếp parser trên body đã bị cắt dở.

### 6.4. Response không body với HEAD

~~~java
if ("HEAD".equals(exchange.getRequestMethod())) {
    exchange.sendResponseHeaders(200, -1);
    exchange.getResponseBody().close();
    return;
}
~~~

Đây là snippet dùng trong handler có `finally { exchange.close(); }`. Status phù hợp và không ghi body. Đừng dùng `sendResponseHeaders(200, 0)` nếu bạn thực sự muốn no-body: `0` là chunked mode trong API.

## 7. Xử lý exceptions: trước và sau khi gửi response headers

Trong handler, xử lý lỗi có hai pha:

1. **Chưa gọi `sendResponseHeaders`**: có thể gửi error response như 400/405/413/500 nếu còn an toàn và parser không ở trạng thái hỏng.
2. **Đã gọi `sendResponseHeaders`**: status/headers đã được commit. Nếu ghi output lỗi, **không thể chuyển thành một response 500 khác trên cùng exchange**; log kết quả lỗi, đóng exchange, để client nhận incomplete response/connection close.

Một cách quản lý:

~~~java
boolean committed = false;
try {
    validateRequest(exchange);
    byte[] body = buildResponseBytes(exchange);
    exchange.sendResponseHeaders(200, body.length);
    committed = true;
    try (OutputStream out = exchange.getResponseBody()) {
        out.write(body);
    }
} catch (IOException failure) {
    // Đã commit? Đóng exchange, log safely, không gửi headers lần hai.
    // Chưa commit? Có thể thử gửi error response nếu connection còn usable.
    throw failure;
} finally {
    exchange.close();
}
~~~

Đây là **snippet minh họa**, không phải source độc lập; `validateRequest`/`buildResponseBytes` là helpers ứng dụng, và `committed` cần được dùng trong một error policy cụ thể. Bản demo giữ logic nhỏ, sử dụng `try/finally` và trả lỗi trước commit. Trong production cần phân loại client abort, request malformed, timeout và internal error để log hợp lý; không log toàn bộ request chứa dữ liệu bí mật.

**Đặc biệt:** `OutputStream.close()` có thể ném `IOException` nếu số byte fixed-length không đúng. Không bắt exception rồi thay bằng giả định “client đã nhận thành công”.

## 8. Ví dụ Java 17+ hoàn chỉnh: POST có giới hạn, 413, HEAD và shutdown

### 8.1. Mục tiêu test

Chương trình `HttpServerLifecycleDemo.java`:

- Tạo `HttpServer` trên `127.0.0.1` với port `0` để OS chọn cổng trống; chỉ nghe loopback.
- Đăng ký `/echo` nhận `POST`, giới hạn request **32 bytes**.
- Nếu `Content-Length` có mặt và lớn hơn max, trả `413` sớm cùng `Connection: close`.
- Nếu body không biết trước độ dài/chunked, vẫn đếm bytes thực bằng `readBounded`.
- Trả thông điệp `accepted bytes=N` bằng UTF-8 với Content-Length chính xác theo bytes.
- Trả `405` và `Allow: POST` với method khác; kiểm path chính xác để `/echo/extra` nhận 404 mặc dù context matching dạng prefix.
- Thêm `/status` hỗ trợ `GET` trả `200/ready` và `HEAD` trả 200 với body rỗng.
- Dùng `ExecutorService` riêng, gọi `server.stop(1)`, `workers.shutdown()` và `awaitTermination`.
- Chứng minh cùng instance `HttpServer` **không được start lại** sau stop.
- Client kiểm thử sử dụng `java.net.http.HttpClient` theo HTTP/1.1, request có timeout, chỉ gửi tới loopback.

**Giới hạn:** Ví dụ dùng max 32 bytes và 128 bytes response chỉ để test dễ. Đây không phải mức giới hạn được khuyến nghị cho mọi API. Mã không có TLS/authentication/public endpoint và không phải HTTP application framework production.

### 8.2. Toàn bộ file `HttpServerLifecycleDemo.java`

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
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

public final class HttpServerLifecycleDemo {
    private static final int MAX_REQUEST_BYTES = 32;
    private static final int MAX_RESPONSE_BYTES = 128;

    record LimitedBody(byte[] data, boolean tooLarge) {}

    static LimitedBody readBounded(InputStream input, int limit)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        byte[] buffer = new byte[8];
        while (true) {
            int take = Math.min(
                    buffer.length, limit + 1 - bytes.size());
            int n = input.read(buffer, 0, take);
            if (n == -1) {
                return new LimitedBody(bytes.toByteArray(), false);
            }
            bytes.write(buffer, 0, n);
            if (bytes.size() > limit) {
                return new LimitedBody(new byte[0], true);
            }
        }
    }

    static void respond(
            HttpExchange exchange, int status, String message)
            throws IOException {
        byte[] body = message.getBytes(StandardCharsets.UTF_8);
        if (body.length > MAX_RESPONSE_BYTES) {
            throw new IOException("Response too large");
        }
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.getResponseHeaders().set(
                "Cache-Control", "no-store");
        exchange.sendResponseHeaders(
                status, body.length == 0 ? -1 : body.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(body);
        }
    }

    static final class EchoHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            try {
                if (!"/echo".equals(
                        exchange.getRequestURI().getPath())) {
                    respond(exchange, 404, "not found");
                    return;
                }
                if (!"POST".equals(exchange.getRequestMethod())) {
                    exchange.getResponseHeaders().set(
                            "Allow", "POST");
                    respond(exchange, 405, "use POST");
                    return;
                }

                String declared = exchange.getRequestHeaders()
                        .getFirst("Content-Length");
                if (declared != null) {
                    long length;
                    try {
                        length = Long.parseLong(declared);
                    } catch (NumberFormatException malformed) {
                        exchange.getResponseHeaders().set(
                                "Connection", "close");
                        respond(exchange, 400,
                                "invalid content length");
                        return;
                    }
                    if (length < 0) {
                        exchange.getResponseHeaders().set(
                                "Connection", "close");
                        respond(exchange, 400,
                                "invalid content length");
                        return;
                    }
                    if (length > MAX_REQUEST_BYTES) {
                        exchange.getResponseHeaders().set(
                                "Connection", "close");
                        respond(exchange, 413,
                                "request too large");
                        return;
                    }
                }

                LimitedBody request = readBounded(
                        exchange.getRequestBody(),
                        MAX_REQUEST_BYTES);
                if (request.tooLarge()) {
                    exchange.getResponseHeaders().set(
                            "Connection", "close");
                    respond(exchange, 413, "request too large");
                    return;
                }

                respond(exchange, 200,
                        "accepted bytes=" + request.data().length);
            } finally {
                exchange.close();
            }
        }
    }

    static final class StatusHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            try {
                String method = exchange.getRequestMethod();
                if ("HEAD".equals(method)) {
                    exchange.sendResponseHeaders(200, -1);
                    exchange.getResponseBody().close();
                } else if ("GET".equals(method)) {
                    respond(exchange, 200, "ready");
                } else {
                    exchange.getResponseHeaders().set(
                            "Allow", "GET, HEAD");
                    respond(exchange, 405,
                            "unsupported method");
                }
            } finally {
                exchange.close();
            }
        }
    }

    static HttpResponse<String> send(
            HttpClient client, HttpRequest request)
            throws Exception {
        return client.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 16);
        ExecutorService workers =
                Executors.newFixedThreadPool(4);
        server.setExecutor(workers);
        server.createContext("/echo", new EchoHandler());
        server.createContext("/status", new StatusHandler());
        server.start();
        boolean stopped = false;

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();

            byte[] utf8 = "Xin ch\u00E0o".getBytes(
                    StandardCharsets.UTF_8);
            HttpResponse<String> ok = send(client,
                    HttpRequest.newBuilder(
                            URI.create(base + "/echo"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofByteArray(utf8))
                    .build());
            System.out.println(
                    "UTF-8 POST status: " + ok.statusCode());
            System.out.println(
                    "UTF-8 POST body: " + ok.body());
            System.out.println("UTF-8 counted as bytes: "
                    + ok.body().equals(
                            "accepted bytes=" + utf8.length));

            HttpResponse<String> full = send(client,
                    HttpRequest.newBuilder(
                            URI.create(base + "/echo"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofByteArray(
                            new byte[MAX_REQUEST_BYTES]))
                    .build());
            System.out.println(
                    "Exactly-at-limit status: "
                    + full.statusCode());
            System.out.println(
                    "Exactly-at-limit body: " + full.body());

            HttpResponse<String> tooLarge = send(client,
                    HttpRequest.newBuilder(
                            URI.create(base + "/echo"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofByteArray(
                            new byte[MAX_REQUEST_BYTES + 8]))
                    .build());
            System.out.println(
                    "Oversize fixed POST status: "
                    + tooLarge.statusCode());

            HttpResponse<String> chunked = send(client,
                    HttpRequest.newBuilder(
                            URI.create(base + "/echo"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofInputStream(() ->
                            new ByteArrayInputStream(
                                    new byte[MAX_REQUEST_BYTES + 8])))
                    .build());
            System.out.println(
                    "Oversize unknown-length POST status: "
                    + chunked.statusCode());

            HttpResponse<String> badMethod = send(client,
                    HttpRequest.newBuilder(
                            URI.create(base + "/echo"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build());
            System.out.println(
                    "Wrong method status: " + badMethod.statusCode());
            System.out.println(
                    "Wrong method Allow: "
                    + badMethod.headers().firstValue("Allow")
                            .orElse("?"));

            HttpResponse<String> badPath = send(client,
                    HttpRequest.newBuilder(
                            URI.create(base + "/echo/extra"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build());
            System.out.println(
                    "Prefix-matched bad path status: "
                    + badPath.statusCode());

            HttpResponse<String> health = send(client,
                    HttpRequest.newBuilder(
                            URI.create(base + "/status"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build());
            System.out.println(
                    "Health GET status/body: "
                    + health.statusCode() + "/" + health.body());

            HttpResponse<String> head = send(client,
                    HttpRequest.newBuilder(
                            URI.create(base + "/status"))
                    .timeout(Duration.ofSeconds(5))
                    .method("HEAD", HttpRequest.BodyPublishers.noBody())
                    .build());
            System.out.println(
                    "Health HEAD status/body length: "
                    + head.statusCode() + "/" + head.body().length());

            server.stop(1);
            stopped = true;
            workers.shutdown();
            boolean ended = workers.awaitTermination(
                    3, TimeUnit.SECONDS);
            System.out.println(
                    "Executor terminated: " + ended);

            boolean restartRejected = false;
            try {
                server.start();
            } catch (IllegalStateException expected) {
                restartRejected = true;
            }
            System.out.println(
                    "Restart same server rejected: " + restartRejected);
        } finally {
            if (!stopped) {
                server.stop(0);
            }
            workers.shutdownNow();
        }
    }
}
~~~

### 8.3. Biên dịch và chạy

Lưu code vào file `HttpServerLifecycleDemo.java`. Module `jdk.httpserver` được export chính thức bởi JDK. Compile/run tương thích Java 17:

~~~sh
javac --release 17 --add-modules jdk.httpserver HttpServerLifecycleDemo.java
java --add-modules jdk.httpserver HttpServerLifecycleDemo
~~~

**Stdout chính xác**, đã chạy trên JDK 24 với Unicode escape dùng cho chữ `à`:

~~~text
UTF-8 POST status: 200
UTF-8 POST body: accepted bytes=9
UTF-8 counted as bytes: true
Exactly-at-limit status: 200
Exactly-at-limit body: accepted bytes=32
Oversize fixed POST status: 413
Oversize unknown-length POST status: 413
Wrong method status: 405
Wrong method Allow: POST
Prefix-matched bad path status: 404
Health GET status/body: 200/ready
Health HEAD status/body length: 200/0
Executor terminated: true
Restart same server rejected: true
~~~

### 8.4. Vì sao các tests quan trọng?

**UTF-8 POST:** `"Xin chào"` có 9 UTF-8 bytes, nên server trả `accepted bytes=9`. Điều này kiểm chứng **byte count**, không dựa vào ký tự Java hay độ dài HTTP header.

**Exactly-at-limit:** body 32 bytes được chấp nhận, còn 40 bytes được từ chối. Tùy nghiệp vụ, hãy định nghĩa rõ ràng **“tối đa 32”** có bao gồm đúng 32 không; demo dùng `<=32`.

**Oversize fixed vs unknown-length:** `BodyPublishers.ofByteArray` gửi request mà client biết size; `BodyPublishers.ofInputStream` không công bố size trước và thường dùng chunked transfer qua HTTP/1.1. Cả hai đều bị chặn bởi **actual bytes count**. Không chỉ dựa vào `Content-Length`.

**405 và Allow:** phương thức GET không được phép tại `/echo` nên trả 405 và `Allow: POST`.

**Prefix-matched bad path:** `HttpServer.createContext("/echo", handler)` dùng matching theo path prefix; `/echo/extra` cũng có thể tới cùng handler. Demo tự so exact path và trả 404 thay vì vô tình coi mọi tiền tố là endpoint hợp lệ.

**GET/HEAD health:** GET trả body `ready`; HEAD trả status 200 với body length 0, phù hợp semantics HEAD.

**Stop và executor:** `stop(1)` đóng server sau khi các request hoàn tất hoặc hết giới hạn chờ; `workers.shutdown()` và `awaitTermination` đóng worker pool riêng. Sau đó `server.start()` trên instance đã stop bị từ chối.

### 8.5. Những điều chương trình không bảo đảm

- Không có TLS, authentication, authorization, reverse proxy hoặc request logging production.
- Không thiết lập server-side read timeout/socket deadline ở lớp HTTP stack; client timeout trong test chỉ bảo vệ **client thử nghiệm**.
- Không giới hạn số lượng/concurrent work queue bằng một `ThreadPoolExecutor` có queue bounded; `newFixedThreadPool` vẫn sử dụng hàng đợi có thể phát triển khi chịu nhiều requests.
- Không validate payload theo JSON/XML/schema; chỉ đếm bytes.
- Không hỗ trợ mọi phương thức HTTP hoặc mọi Content-Encoding.
- Không xử lý request body upload rất lớn hợp lệ bằng streaming-to-disk.
- Không tuyên bố rằng mọi client luôn thấy body lỗi 413 nếu server đóng connection sớm.

Đối với môi trường public, dùng gateway/proxy hoặc server framework có giới hạn connection/header/body/timeout/concurrency rõ ràng. Demo phục vụ việc học API cơ bản, dễ kiểm chứng.

## 9. `stop(int delay)` chính xác làm gì?

JavaDoc `HttpServer.stop(int delay)` mô tả:

1. Đóng listening socket, **không nhận thêm exchange mới**.
2. Chờ các exchange handlers hiện tại hoàn tất, **hoặc** gần hết `delay` giây, tùy điều gì xảy ra trước.
3. Sau đó đóng các TCP connections đang mở, background server thread kết thúc và method trả về.
4. Instance đã dừng **không được sử dụng lại bằng `start()`**.

`delay` là **giây**, không phải milliseconds. `delay < 0` gây `IllegalArgumentException`.

| Cách gọi | Hành vi mong muốn | Rủi ro nếu hiểu sai |
| --- | --- | --- |
| `server.stop(0)` | Dừng ngay, không chờ exchange hoàn tất | Có thể cắt ngang request đang chạy |
| `server.stop(2)` | Chờ tối đa khoảng 2 giây cho các exchange đang hoạt động | Không bảo đảm mọi request chậm hoàn tất |
| `server.stop(10)` | Chờ tối đa khoảng 10 giây | Có thể chặn thread gọi stop trong tối đa thời gian này |
| `server.stop(-1)` | Không hợp lệ | Ném `IllegalArgumentException` |
| `server.start()` sau `stop` | Không được restart | Tạo instance mới nếu cần chạy lại |

**Không nên gọi stop trong mỗi handler.** Chạy `stop` ở lifecycle controller/shutdown hook/admin path đã xác thực, sau khi đã chuyển hệ thống sang trạng thái chuẩn bị ngừng và chặn admission nếu cần.

### 9.1. `stop(delay)` không phải draining hoàn chỉnh của toàn ứng dụng

Server có thể chờ handler hiện tại, nhưng handler có thể còn công việc ngoài phạm vi HTTP exchange như database async task hoặc queue job. Phải quản lý những công việc đó bằng lifecycle riêng. Khi hết delay, active TCP connections có thể bị đóng **ngay cả khi business task chưa hoàn tất**.

Nếu handler bỏ qua cancellation hoặc đang block vô hạn ở database/file I/O, việc `stop` trả về **không có nghĩa** mọi task đã kết thúc an toàn. Cần deadlines, cancellation, transaction boundaries và idempotency.

### 9.2. Tại sao dừng server trước khi tắt executor?

Trình tự thông dụng:

~~~java
server.stop(5);
workers.shutdown();
if (!workers.awaitTermination(10, TimeUnit.SECONDS)) {
    workers.shutdownNow();
}
~~~

Đây là snippet trong lifecycle method có `server`, `workers`, method `throws InterruptedException` hoặc xử lý interrupt rõ ràng. Dừng listener trước, cho handler đang chạy thời gian hoàn tất, rồi không nhận nhiệm vụ mới vào pool và dọn pool.

Không gọi `workers.shutdownNow()` trước `server.stop(delay)` rồi mong response đang ghi hoàn tất bình thường: interrupts có thể cắt request tùy handler. Nếu app muốn chủ động dừng nhận **request mới** trước khi gọi stop, có thể dùng readiness/draining flag kết hợp HTTP routing hoặc load balancer.

### 9.3. Shutdown hook minh họa

~~~java
Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    server.stop(5);
    workers.shutdown();
    try {
        if (!workers.awaitTermination(10, TimeUnit.SECONDS)) {
            workers.shutdownNow();
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        workers.shutdownNow();
    }
}, "http-shutdown"));
~~~

Đây là snippet cho app có `server`, `workers` đã được tạo; không nên đồng thời gắn nhiều hook cùng quản lý resource. Trong hệ thống thật, shutdown hook cần **idempotent**, không giữ lock đang được request handler cần, và phải tôn trọng ngân sách thời gian của orchestration platform. Nếu container dừng tiến trình ngay sau deadline, hook không được bảo đảm luôn chạy hết.

## 10. Ví dụ thứ hai: chứng minh `stop(2)` chờ handler đang chạy

Ví dụ `HttpServerStopDelayDemo.java` dùng `CountDownLatch` để điều khiển một handler đang chờ:

1. Client bắt đầu `GET /slow`.
2. Handler đánh dấu đã vào rồi **chờ** latch.
3. Main thread gọi `server.stop(2)` từ thread khác.
4. Kiểm thử xác nhận stop **chưa trả về** trong khi handler vẫn bị giữ.
5. Release latch; handler trả `200/done` và đóng response/exchange.
6. Stop hoàn tất, sau đó executor kết thúc.

Đây là **integration test có đồng bộ rõ ràng**, không dựa vào sleep tùy ý để quyết định handler có thực sự đang chạy hay không.

### 10.1. File `HttpServerStopDelayDemo.java`

~~~java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpExchange;
import java.io.IOException;
import java.io.OutputStream;
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

public final class HttpServerStopDelayDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch stopCalled = new CountDownLatch(1);
        CountDownLatch stopReturned = new CountDownLatch(1);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 8);
        ExecutorService workers =
                Executors.newFixedThreadPool(2);
        server.setExecutor(workers);
        server.createContext("/slow", exchange -> {
            try {
                entered.countDown();
                try {
                    if (!release.await(5, TimeUnit.SECONDS)) {
                        exchange.sendResponseHeaders(503, -1);
                        return;
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IOException(
                            "Handler interrupted", interrupted);
                }
                byte[] body = "done".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();

        Thread stopper = null;
        try {
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder(URI.create(
                    "http://127.0.0.1:"
                    + server.getAddress().getPort() + "/slow"))
                    .timeout(Duration.ofSeconds(4))
                    .GET()
                    .build();
            CompletableFuture<HttpResponse<String>> pending =
                    client.sendAsync(request,
                            HttpResponse.BodyHandlers.ofString());

            boolean active = entered.await(3, TimeUnit.SECONDS);
            if (!active) {
                throw new IOException("Handler did not start");
            }
            System.out.println(
                    "Handler active before stop: " + active);

            stopper = new Thread(() -> {
                stopCalled.countDown();
                try {
                    server.stop(2);
                } finally {
                    stopReturned.countDown();
                }
            }, "http-stop");
            stopper.start();
            if (!stopCalled.await(2, TimeUnit.SECONDS)) {
                throw new IOException("stop did not begin");
            }
            boolean early =
                    stopReturned.await(100, TimeUnit.MILLISECONDS);
            System.out.println(
                    "Stop returned while handler blocked: " + early);

            release.countDown();
            HttpResponse<String> reply =
                    pending.get(3, TimeUnit.SECONDS);
            System.out.println(
                    "In-flight response: "
                    + reply.statusCode() + "/" + reply.body());

            boolean ended =
                    stopReturned.await(3, TimeUnit.SECONDS);
            System.out.println("Stop completed: " + ended);
            stopper.join(3000);
            workers.shutdown();
            System.out.println(
                    "Executor terminated: "
                    + workers.awaitTermination(3, TimeUnit.SECONDS));
        } finally {
            release.countDown();
            server.stop(0);
            if (stopper != null) {
                stopper.join(3000);
            }
            workers.shutdownNow();
        }
    }
}
~~~

### 10.2. Biên dịch và kết quả

Lưu file `HttpServerStopDelayDemo.java`:

~~~sh
javac --release 17 --add-modules jdk.httpserver HttpServerStopDelayDemo.java
java --add-modules jdk.httpserver HttpServerStopDelayDemo
~~~

**Stdout chính xác** trong kiểm thử JDK 24:

~~~text
Handler active before stop: true
Stop returned while handler blocked: false
In-flight response: 200/done
Stop completed: true
Executor terminated: true
~~~

**Phân tích:** `stop` không trả ngay khi có active handler; sau khi handler giải phóng và đóng exchange, stop hoàn tất. Test dùng 100 ms để quan sát trạng thái khi blocked; trên máy bị treo lâu bất thường, lịch thread có thể khiến timing thay đổi, nên với CI production cần tăng time budget và assert lifecycle bằng synchronization/controlled scheduler nếu muốn test chống flaky tuyệt đối. Không lấy đúng 100 ms làm đặc tả `stop`.

### 10.3. Nếu handler chạy lâu hơn delay thì sao?

Theo API, sau khoảng `delay` giây, stop kết thúc các connections còn mở ngay cả khi handlers chưa tự hoàn tất. Kết quả client có thể là response incomplete hoặc I/O error, tùy thời điểm.

**Không mô phỏng điều này bằng cách treo vô hạn** trong production. Thử nghiệm nên dùng latch/timeouts và cleanup chặt chẽ. Nếu nghiệp vụ là payment/queue/job, transaction/idempotency quyết định cách khôi phục sau khi connection bị đóng, không phải kỳ vọng socket còn mở.

## 11. Thread pool, backlog và saturation

Khi gọi:

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 0), 16);
ExecutorService workers = Executors.newFixedThreadPool(4);
server.setExecutor(workers);
~~~

- Tham số `16` là socket **backlog hint**, không phải max requests/connections và không phải giới hạn hàng đợi handler.
- `setExecutor` phải được gọi **trước `start()`**.
- `newFixedThreadPool(4)` giới hạn số worker threads xử lý đồng thời, nhưng hàng đợi công việc của executor mặc định có thể **không giới hạn**; đây không phải policy bảo vệ khỏi flood requests.
- Nếu không set executor, `HttpServer` dùng default implementation, theo JavaDoc có thể xử lý công việc trên thread do `start()` tạo; không nên mặc định khả năng phục vụ song song cao.
- `stop(delay)` không tự giải phóng resources của executor custom.

Với server có nguy cơ chịu nhiều requests, hãy chọn giới hạn concurrency rõ ràng. Ví dụ có thể dùng `ThreadPoolExecutor` với bounded queue và rejection policy, nhưng cần kiểm tra cách `HttpServer` xử lý `RejectedExecutionException` và không coi từ chối task là tự động trả `503` đúng chuẩn. Sản phẩm public-facing nên đặt admission/load-shedding tại gateway/server framework có khả năng quan sát và kiểm soát.

### 11.1. Đọc body có byte limit vẫn có thể bị slow client giữ thread

Byte cap không tự tạo deadline. Một client gửi 1 byte mỗi 30 giây sẽ không vượt max nhưng có thể chiếm worker lâu. Hệ thống nên có:

- Read/idle timeout thật ở lớp network/HTTP stack hoặc reverse proxy.
- Request deadline toàn phần.
- Hạn chế concurrent sockets/handlers.
- Bounded queue, cancellation/backpressure.
- Kiểm tra client authentication và quotas khi cần.
- Chính sách đóng connection với request bị reject sớm.

Không dựa vào `HttpClient.Builder.connectTimeout` trong **test client** như thể nó bảo vệ server khỏi slow HTTP clients khác.

## 12. Các trạng thái lỗi HTTP và response stream

| Tình huống | HTTP status có thể dùng | Cách xử lý |
| --- | --- | --- |
| Request hợp lệ | `200` hoặc `201` theo nghiệp vụ | Ghi đúng số bytes, đóng output/exchange |
| Không có body trả về | `204` hoặc phù hợp với method | `sendResponseHeaders(status,-1)` |
| Sai phương thức | `405` | Set `Allow`, phản hồi, đóng |
| Path không tồn tại | `404` | Bảo đảm exact path nếu context prefix matching |
| Header body size không hợp lệ | `400` | Không tự parse framing không đáng tin |
| Request body quá lớn | `413` | Không đọc tiếp vô hạn, có thể `Connection: close` |
| Handler gặp lỗi trước khi response commit | `500` | Gửi error body bounded nếu connection còn usable |
| Server đang draining/quá tải | `503` | Admission policy, retry hint nếu phù hợp |
| Read timeout | `408` trong trường hợp server có logic phát hiện phù hợp | Socket/timeouts, tránh gửi lỗi sau connection đã hỏng |

Lưu ý `413` có tên “Content Too Large” theo HTTP Semantics hiện hành; nhiều tài liệu cũ vẫn dùng “Payload Too Large”. Status code `413` không đổi. `Connection: close` là lựa chọn hữu ích khi request body bị bỏ dở, nhưng client vẫn có thể nhận connection reset tùy timing.

## 13. Kiểm thử cần có cho handler production

| Test | Setup | Kỳ vọng |
| --- | --- | --- |
| Body rỗng | POST 0 bytes | Hợp lệ nếu contract cho phép, response không nhầm `0` |
| Body đúng giới hạn | 32/32 bytes | 200 và xử lý toàn bộ |
| Body vượt 1 byte | 33/32 bytes | 413 |
| Body lớn biết Content-Length | POST 40 bytes | 413 trước hoặc khi đọc |
| Body lớn unknown length | Chunked POST 40 bytes | 413 do byte counter |
| UTF-8 body | `"Xin chào"` | Đếm **9 bytes**, không phải 8 ký tự |
| UTF-8 response | Dữ liệu có dấu | Fixed Content-Length = encoded bytes length |
| Sai method | GET /echo | 405, `Allow: POST` |
| Bad path | /echo/extra | 404 nếu endpoint chỉ chấp nhận exact path |
| HEAD | /status | 200, body rỗng |
| Empty response | 204 | `sendResponseHeaders(204,-1)` |
| Chunked response | Không biết trước response length | `sendResponseHeaders(200,0)` và đóng stream |
| Fixed-length too few | Viết ít bytes hơn đã khai báo | IOException/abort, không giả báo thành công |
| Fixed-length too many | Viết thừa bytes | IOException/abort |
| Handler throws before commit | Lỗi xử lý | Trả 5xx nếu còn khả thi, đóng exchange |
| Handler throws after commit | I/O lỗi khi ghi body | Đóng connection; không gửi headers lần hai |
| Không đóng output | Handler cố ý quên close (test cô lập) | Phát hiện resource leak/client chờ |
| Body lớn + keep-alive | Reject sớm | Không drain vô hạn, connection close theo policy |
| Slow client | Gửi rất chậm | Timeout/concurrency budget bảo vệ server |
| Nhiều requests đồng thời | Vượt worker pool | Bounded admission/queuing, không OOM |
| Stop không có active exchange | `stop(0)` | Trả sau khi dừng |
| Stop có exchange ngắn | `stop(2)` | Exchange xong, stop kết thúc |
| Stop với exchange chậm | Quá delay | Active connections có thể bị đóng |
| Custom executor | Stop server | Phải shutdown executor riêng |
| Restart server | `start` sau stop | `IllegalStateException` |
| Double shutdown hook | Hai tín hiệu stop | Controller idempotent, không deadlock |
| Port conflict | Bind cổng đã dùng | Handle `BindException` |
| Không public bind | Bind loopback | Không truy cập từ interface khác |

Để tránh tests flaky, dùng port `0`, loopback `127.0.0.1`, latches, request timeouts, `finally` cleanup. Đừng dựa vào một cổng cố định có thể bị tiến trình khác chiếm.

## 14. Các lỗi thường gặp và hướng sửa

| Lỗi | Hậu quả | Hướng đúng |
| --- | --- | --- |
| `getRequestBody().readAllBytes()` trên input chưa tin | Memory exhaustion | `readBounded` hoặc streaming với byte counter |
| Chỉ kiểm `Content-Length` | Bỏ sót chunked/unknown-length | Đếm actual bytes đã đọc |
| Dùng `String.length()` làm response length | Sai Content-Length với UTF-8 | `getBytes(UTF_8).length` |
| `sendResponseHeaders(..., 0)` để gửi rỗng | Kích hoạt chunked | Dùng `-1` khi không body |
| Ghi số byte khác fixed length | IOException/abort, client lỗi | Viết đúng byte count |
| Không đóng response output | Client chờ, resource leak | `try-with-resources` |
| Quên `exchange.close()` trong return sớm | Connection/resource giữ lại | `try/finally` |
| Đóng request chưa đọc hết rồi kỳ vọng keep-alive | Connection có thể unusable | Consume hợp lệ; với oversize chủ động close |
| Drain toàn bộ oversized request để reuse socket | DoS/worker bị giữ | Dừng tại max+1 và đóng connection |
| Không kiểm method | Endpoint làm việc ngoài contract | 405 + Allow |
| Chỉ tạo context `/echo` rồi tin path exact | `/echo/extra` cũng được match | Kiểm `getRequestURI().getPath()` |
| Gọi `getResponseBody` rồi ghi trước sendResponseHeaders | Vi phạm API sequence | Call sendResponseHeaders trước |
| Cố gửi 500 sau khi đã commit 200 | Two responses không hợp lệ | Log, abort/close exchange |
| Gọi `server.stop(0)` khi muốn đợi request | Cắt kết nối sớm | `stop(delay > 0)` trong shutdown plan |
| Hiểu `delay` là milliseconds | Shutdown timing sai | `delay` tính bằng **giây** |
| Gọi `stop` nhưng không shutdown custom executor | Process còn worker threads | `shutdown + awaitTermination` |
| `start` server đã stop | IllegalStateException | Tạo HttpServer instance mới |
| Dùng fixed thread pool như bounded queue | Hàng đợi có thể phình | Bounded admission/queue framework |
| Nghĩ byte max chặn slowloris | Client nhỏ nhưng chậm giữ thread | Read/idle timeouts, proxy, cancellation |
| Bind `0.0.0.0` trong demo | Vô tình mở endpoint ra LAN | Bind loopback để học/test |
| Không có TLS/auth khi public-facing | Lộ dữ liệu/không có identity | HTTPS/proxy/authorization |
| Không đóng client-side streaming body | Leak client connection | Đóng stream phản hồi ở client nếu BodyHandlers.ofInputStream |
| Bỏ qua InterruptedException trong shutdown | Không tôn trọng cancel | Restore interrupt, `shutdownNow` fallback |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao response OutputStream phải được đóng?

**Trả lời:** Để kết thúc HTTP response/exchange đúng framing, giải phóng tài nguyên; với chunked, close còn báo body đã hoàn tất.

**Câu 2.** `HttpExchange.close()` có vai trò gì?

**Trả lời:** Kết thúc exchange, đóng request input và response output nếu chưa đóng. Đặt trong `finally` để xử lý cả return sớm và exception.

**Câu 3.** Vì sao request lớn không nên gọi `readAllBytes`?

**Trả lời:** Nó cấp phát/cố đọc toàn bộ request trước khi kiểm max; attacker có thể gây cạn memory.

**Câu 4.** Tại sao kiểm `Content-Length` thôi chưa đủ?

**Trả lời:** Vì request có thể không có Content-Length hoặc truyền chunked/unknown-length; phải đếm bytes thực từ request stream.

**Câu 5.** Đọc byte thứ `MAX+1` có tác dụng gì?

**Trả lời:** Phân biệt body có đúng MAX bytes (hợp lệ) và body vượt MAX, mà không đọc không giới hạn.

**Câu 6.** Khi request quá lớn, có nên drain mãi để tái sử dụng keep-alive không?

**Trả lời:** Không. Nên dừng đọc, phản hồi 413 nếu có thể, dùng `Connection: close` theo policy và đóng exchange.

**Câu 7.** `sendResponseHeaders(200,0)` nghĩa là gì?

**Trả lời:** Chunked transfer, **không phải** body rỗng.

**Câu 8.** Muốn gửi body rỗng thì truyền bao nhiêu?

**Trả lời:** `-1` (giá trị <=-1) cho no response body, rồi đóng response/exchange.

**Câu 9.** Vì sao `"Xin chào"` có thể phải ghi 9 bytes dù chỉ có 8 ký tự?

**Trả lời:** UTF-8 dùng nhiều bytes cho `à`. Fixed-length HTTP body dùng byte count sau encoding, không dùng `String.length()`.

**Câu 10.** Nếu đã `sendResponseHeaders(200,...)` rồi ghi output lỗi, có thể gửi 500 không?

**Trả lời:** Không nên. Headers/status đã commit; phải xử lý lỗi, đóng/abort exchange và log an toàn.

**Câu 11.** `stop(2)` chờ gì và trong bao lâu?

**Trả lời:** Chờ current exchanges hoàn tất hoặc khoảng 2 giây, tùy điều xảy ra trước; sau đó đóng TCP connections và server kết thúc.

**Câu 12.** `stop(0)` có bảo đảm graceful completion không?

**Trả lời:** Không. Nó dừng ngay và có thể cắt request đang chạy.

**Câu 13.** `HttpServer` có start lại sau stop không?

**Trả lời:** Không. Cần tạo instance mới.

**Câu 14.** `server.stop(5)` có shutdown `Executors.newFixedThreadPool` mà tôi tự tạo không?

**Trả lời:** Không được dựa vào điều đó. Ứng dụng phải shutdown/awaitTermination pool riêng.

**Câu 15.** Vì sao `newFixedThreadPool(4)` không đủ chống flood requests?

**Trả lời:** Nó giới hạn số threads xử lý đồng thời nhưng hàng đợi có thể tăng không giới hạn; cần bounded queue/admission và upstream rate limits.

**Câu 16.** Tại sao test `/echo/extra` nhận 404 dù context đăng ký là `/echo`?

**Trả lời:** Vì context routing mặc định dựa trên prefix; handler demo kiểm exact path rồi trả 404.

**Câu 17.** Có thể dùng `HttpServer` public-facing mà không thêm lớp bảo vệ gì không?

**Trả lời:** Không nên. Cần TLS/auth, quotas, header/body limits, timeouts, logging an toàn, concurrency management và đánh giá môi trường production.

**Câu 18.** `HttpClient.connectTimeout` trong test có hạn chế slow HTTP clients gửi tới server không?

**Trả lời:** Không. Nó chỉ là timeout của test client; server cần chính sách read/idle timeout của network stack/proxy.

**Câu 19.** Vì sao `stop(delay)` không thay thế transaction cancellation?

**Trả lời:** Vì server stop quản lý listener/exchanges/TCP sockets; business tasks, database transactions và async work có lifecycle khác.

**Câu 20.** Khi nào handler được xem là hoàn thành an toàn?

**Trả lời:** Khi request được đọc/kiểm trong budget, response ghi đúng framing và đóng, exchange được kết thúc, không còn side effect treo hoặc đã bàn giao chúng theo transaction/idempotency policy.

**Tóm tắt:** Với `com.sun.net.httpserver.HttpServer`, hãy đặt `exchange.close()` trong `finally`, đóng `getResponseBody()` (dù không gửi body), đọc request tối đa `MAX+1` bytes thay vì `readAllBytes`, và đếm bytes thật thay vì chỉ tin `Content-Length`. `sendResponseHeaders` dùng **>0** cho fixed bytes, **0** cho chunked, **-1** cho no-body; với UTF-8 dùng `getBytes(UTF_8).length`. Khi dừng, `stop(delay)` chỉ đợi current exchanges tối đa delay **giây**, không restart được server và phải shutdown executor riêng. Kết hợp byte size với concurrency, timeout và network/security limits nếu triển khai ngoài môi trường kiểm thử.

### Tài liệu tham khảo chính thức và hiện hành

- [Oracle Java SE 27 — HttpExchange](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request/response streams, framing lengths, close semantics.
- [Oracle Java SE 26 — HttpServer](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `start`, `setExecutor`, `stop(delay)`, context prefix matching.
- [Oracle Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): tính tương thích Java 17 và lifecycle.
- [Oracle Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): `sendResponseHeaders`, đóng request/response streams.
- [Oracle Java SE 17 — HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): `handle(HttpExchange)`.
- [Oracle Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown/awaitTermination/cancellation.
- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client test với timeouts.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): phương thức, `HEAD`, `413 Content Too Large`, status codes.
