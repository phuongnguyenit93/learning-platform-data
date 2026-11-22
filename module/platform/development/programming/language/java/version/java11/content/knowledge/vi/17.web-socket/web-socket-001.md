# WebSocket client trong java.net.http (Java 11+)

## 1. Khái niệm và vị trí của WebSocket trong Java 11

**WebSocket** là giao thức duy trì một kết nối hai chiều giữa client và server. Sau khi thực hiện **opening handshake** trên nền HTTP, hai phía trao đổi các **WebSocket frame/message** mà không cần tạo một HTTP request/response mới cho từng thông điệp. Nó phù hợp cho chat, trạng thái thời gian thực, dashboard cập nhật liên tục hoặc các ứng dụng cần nhận dữ liệu do server chủ động gửi.

Từ **Java 11**, mô-đun tiêu chuẩn `java.net.http` có sẵn API **WebSocket client**:

- `java.net.http.HttpClient`: tạo một client HTTP và cấu hình chung.
- `java.net.http.WebSocket.Builder`: thiết lập kết nối WebSocket.
- `java.net.http.WebSocket`: gửi thông điệp, điều khiển nhận và đóng kết nối.
- `java.net.http.WebSocket.Listener`: nhận thông báo kết nối, text, binary, ping/pong, close và lỗi.

Đây là API vẫn được hỗ trợ trên các JDK hiện đại. **JDK cung cấp WebSocket client, không cung cấp một WebSocket server đầy đủ trong `java.net.http`**. Server loopback trong chương trình kiểm thử ở mục 7 là mô hình tối giản để xác nhận giao thức, không phải thư viện để triển khai server sản xuất.

**Phân biệt:** `HttpClient.send(HttpRequest, BodyHandler)` phục vụ một HTTP request/response; WebSocket dùng `HttpClient.newWebSocketBuilder().buildAsync(uri, listener)` để tạo một kết nối được duy trì, rồi giao tiếp bằng `sendText`, `sendBinary` và callbacks. Sau handshake, các message không được biểu diễn như các đối tượng `HttpResponse<String>` lặp lại.

## 2. URI, handshake và quy trình kết nối

### 2.1. Sử dụng đúng URI

Địa chỉ WebSocket thông thường bắt đầu bằng:

- `ws://host/path`: kết nối WebSocket **không có TLS**, thích hợp cho loopback hoặc môi trường kiểm thử riêng.
- `wss://host/path`: WebSocket **qua TLS**; nên dùng khi truyền dữ liệu qua mạng không đáng tin cậy hoặc có thông tin nhạy cảm.

`wss` khác với `https` theo ý nghĩa sử dụng API: `buildAsync` nhận URI WebSocket chứ không phải dùng `HttpRequest` như HTTP thông thường. Trong sản phẩm thực, kiểm tra host, scheme, certificate và các quy tắc proxy/SSL liên quan.

### 2.2. Opening handshake diễn ra như thế nào?

Với WebSocket truyền thống trên HTTP/1.1, client thực hiện yêu cầu Upgrade, ví dụ rút gọn:

```http
GET /echo HTTP/1.1
Host: example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <giá trị do client tạo>
Sec-WebSocket-Version: 13
```

Server chấp nhận bằng `101 Switching Protocols` và `Sec-WebSocket-Accept` hợp lệ:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <giá trị xác minh handshake>
```

**Không tự ghép hoặc tự đặt các header bắt buộc của WebSocket handshake** khi dùng `WebSocket.Builder`: Java client thực hiện việc này. `Builder.header(name,value)` chỉ dành cho các **header bổ sung được phép**, và header do WebSocket Protocol quy định là không hợp lệ khi tự thêm.

Trên kết nối WebSocket thực, dữ liệu là **frame**, không đơn giản là các dòng text kết thúc bằng ký tự xuống dòng. Các frame client→server được mask theo giao thức; Java WebSocket client tự xử lý việc đóng khung và masking.

Quy trình cơ bản:

```text
HttpClient.newHttpClient()
          │
          ▼
newWebSocketBuilder()
    ├─ connectTimeout(...)
    ├─ header(...)         (nếu cần)
    └─ subprotocols(...)   (nếu server hỗ trợ)
          │
          ▼
buildAsync(wsUri, listener)
          │
          ├─ thất bại: CompletableFuture hoàn thành exceptional
          └─ thành công: WebSocket + onOpen
                          │
                          ├─ sendText/sendBinary/sendPing
                          ├─ onText/onBinary/onPing/onPong
                          │   + request(n) để nhận tiếp
                          └─ sendClose / onClose hoặc abort khi lỗi
```

## 3. Tạo WebSocket client bằng HttpClient.newWebSocketBuilder()

Mảnh mã thông dụng trên Java 11:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

HttpClient httpClient = HttpClient.newHttpClient();
WebSocket.Listener listener = new WebSocket.Listener() { };

CompletableFuture<WebSocket> future = httpClient.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .buildAsync(URI.create("wss://example.com/socket"), listener);
```

Đoạn trên là **minh họa cú pháp**, `example.com` không được khẳng định có WebSocket endpoint và **không phải ví dụ chạy độc lập**. Chương trình đầy đủ ở mục 7 kết nối tới **server loopback tự tạo**, không cần Internet.

### 3.1. Vì sao buildAsync trả CompletableFuture?

`buildAsync(uri, listener)` bắt đầu quá trình kết nối và trả:

```java
CompletableFuture<WebSocket>
```

Lúc mới nhận future, **chưa chắc handshake đã thành công**. Chỉ khi future hoàn thành bình thường mới có `WebSocket` đã kết nối. Với mã đồng bộ tại tầng gọi, có thể đợi giới hạn thời gian:

```java
WebSocket socket = future.get(5, TimeUnit.SECONDS);
```

Mảnh này cần import `TimeUnit` và xử lý `InterruptedException`, `ExecutionException`, `TimeoutException`. Với ứng dụng bất đồng bộ, ưu tiên `thenCompose`/`whenComplete` thay vì chặn thread bằng `get()`.

`WebSocket.Builder.connectTimeout(Duration)` giới hạn thời gian **thiết lập kết nối/handshake**. Nó **không phải idle timeout cho toàn bộ kết nối WebSocket sau khi mở**. Trong sản phẩm, cần thiết kế heartbeat/timeout nhận dữ liệu hoặc watchdog riêng nếu muốn phát hiện kết nối im lặng.

### 3.2. Header và subprotocol

```java
WebSocket.Builder builder = httpClient.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .header("X-Request-Id", "req-42")
        .subprotocols("chat.v2", "chat.v1");
```

`header(...)` thêm header cho HTTP opening handshake, nhưng **không được tự khai báo `Sec-WebSocket-Key`, `Sec-WebSocket-Version`, `Upgrade`...** như một header tùy ý. Không đưa token/bí mật vào log. Với `wss` và xác thực, cân nhắc chính sách token, TLS và nơi server nhận credentials.

`subprotocols(...)` gửi các định danh giao thức ứng dụng theo thứ tự ưu tiên. Chỉ sử dụng khi server đã hỗ trợ đúng một hoặc nhiều subprotocol như vậy. Sau khi kết nối:

```java
String selectedProtocol = socket.getSubprotocol();
```

Nếu không có subprotocol được chọn thì kết quả là chuỗi rỗng `""`. Việc chọn subprotocol chỉ có ý nghĩa nếu các bên thỏa thuận về cấu trúc message; nó không tự nén, tự mã hóa dữ liệu nghiệp vụ hay xác thực người dùng.

**Builder không an toàn để nhiều thread cùng chỉnh sửa mà thiếu đồng bộ.** Có thể tái sử dụng một `HttpClient`, nhưng nên tạo builder mới cho mỗi lượt kết nối và lưu cấu hình thích hợp.

## 4. Nhận sự kiện bằng WebSocket.Listener

`WebSocket.Listener` định nghĩa các callback:

| Callback | Khi nào xảy ra | Điều cần nhớ |
| --- | --- | --- |
| `onOpen(WebSocket)` | Kết nối được mở | Gọi `webSocket.request(1)` hoặc số dương để cho phép nhận |
| `onText(WebSocket, CharSequence, boolean last)` | Nhận một đoạn văn bản | Gộp các đoạn cho đến `last == true`; request tiếp |
| `onBinary(WebSocket, ByteBuffer, boolean last)` | Nhận một đoạn byte | Đọc vùng `position..limit`; gộp đến `last`; request tiếp |
| `onPing(WebSocket, ByteBuffer)` | Nhận Ping | Client tự gửi Pong; không cần tự gửi thêm Pong theo mặc định |
| `onPong(WebSocket, ByteBuffer)` | Nhận Pong | Có thể kết hợp heartbeat để theo dõi phản hồi |
| `onClose(WebSocket, int code, String reason)` | Nhận Close frame | Sự kiện cuối, đầu nhận đã đóng |
| `onError(WebSocket, Throwable)` | Có lỗi kết nối/callback | Sự kiện cuối, phải ghi nhận lỗi và dừng dùng kết nối |

### 4.1. request(n) là quyền nhận callback, không phải số message

**Điểm dễ sai nhất:** kết nối WebSocket mới có counter nhận bằng **0**. Java chỉ gọi các callback nhận dữ liệu nếu đã có demand. `webSocket.request(n)` cấp quyền nhận tối đa **n lần gọi callback nhận** (`onText`, `onBinary`, `onPing`, `onPong`, `onClose`), **không phải n message đầy đủ**.

`onOpen` và `onError` không tiêu thụ demand. Với text/binary, một message có thể được chia thành **nhiều callback**. Nếu chỉ gọi `request(1)` khi mở rồi quên cấp tiếp, việc nhận có thể đứng sau đoạn đầu tiên.

Mẫu đơn giản:

```java
@Override
public void onOpen(WebSocket ws) {
    ws.request(1);
}

@Override
public CompletionStage<?> onText(WebSocket ws,
                                 CharSequence data, boolean last) {
    // Xử lý data và last ở đây.
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
```

Đây là **mảnh mã bên trong class implements WebSocket.Listener**; cần import `CompletionStage` và `CompletableFuture`. `request(0)` hoặc số âm gây `IllegalArgumentException`. Không nên gọi `request(Long.MAX_VALUE)` chỉ để trốn thiết kế backpressure nếu ứng dụng không chịu được lượng dữ liệu nhận.

### 4.2. Nối fragment đúng cách

`last == false` có nghĩa **message chưa kết thúc**; `last == true` có nghĩa đây là **đoạn cuối của message**.

Ví dụ (mảnh mã trong listener):

```java
private final StringBuilder partialText = new StringBuilder();

@Override
public CompletionStage<?> onText(WebSocket ws,
                                 CharSequence piece, boolean last) {
    partialText.append(piece);
    if (last) {
        String complete = partialText.toString();
        partialText.setLength(0);
        processMessage(complete); // Hàm nghiệp vụ do ứng dụng định nghĩa.
    }
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
```

Không giả định mỗi lần `onText` tương ứng **một message hoàn chỉnh**. Tương tự với `onBinary`: gộp byte từ `ByteBuffer` cho đến `last == true` rồi mới giải mã/giao cho parser của message-level protocol nếu cần.

`CharSequence` và `ByteBuffer` được Listener nhận **chỉ bảo đảm có thể sử dụng trước khi `CompletionStage` trả về hoàn thành**. Nếu cần xử lý bất đồng bộ sau đó, hãy **copy dữ liệu** phù hợp. Không giữ tham chiếu mutable buffer rồi sử dụng sau khi client có quyền thu hồi/tái sử dụng nó.

### 4.3. CompletionStage của callback khác với request(n)

`onText`, `onBinary`, `onPing`, `onPong`, `onClose` trả về `CompletionStage<?>`. Nó thông báo **khi nào listener đã xử lý xong phần dữ liệu được trao** và phía WebSocket có thể thu hồi dữ liệu. `request(n)` điều khiển **số callback được phép giao tiếp theo**. Hai cơ chế **không đồng nghĩa**.

Có thể trả `null` nếu muốn biểu thị đã hoàn thành ngay theo Javadoc, nhưng trả `CompletableFuture.completedFuture(null)` giúp làm rõ ý định. Trong callback thực tế, đừng block không giới hạn, vì xử lý chậm có thể khiến luồng nhận bị nghẽn.

Javadoc bảo đảm những callback gắn với **cùng một WebSocket** được gọi theo thứ tự không reentrant. Nhưng nếu cùng Listener object được gán cho **nhiều kết nối**, các callback của những kết nối khác nhau có thể chạy đồng thời: trạng thái cần được tách theo kết nối hoặc đồng bộ hóa đúng cách.

## 5. Gửi text, binary, Ping/Pong và đóng kết nối

### 5.1. sendText(data, last)

```java
webSocket.sendText("Hello, ", false)
        .thenCompose(ws -> ws.sendText("world!", true))
        .join();
```

Đoạn trên là mảnh mã với biến `webSocket` đã được kết nối. Hai lời gọi gửi **một text message phân mảnh**: `false` báo chưa hết message, `true` báo phần cuối. Sử dụng `thenCompose` để chờ lần trước xong trước khi bắt đầu lần sau; không đua nhau gửi hai frame text hoặc binary đang pending.

Mỗi phương thức gửi trả `CompletableFuture<WebSocket>`. **Future hoàn thành bình thường nghĩa là thao tác gửi đã hoàn tất ở phía client**, **không có nghĩa server đã xử lý nghiệp vụ hoặc xác nhận message đó**. Muốn xác nhận, phải có ACK ở cấp ứng dụng.

`sendText` nhận `CharSequence`. Không sửa chuỗi/đối tượng ký tự mutable trong khi future gửi còn pending. Java sẽ encode text thành UTF-8 theo giao thức WebSocket.

### 5.2. sendBinary(ByteBuffer, last)

```java
ByteBuffer payload = ByteBuffer.wrap(new byte[] {1, 2, 3});
webSocket.sendBinary(payload, true).join();
```

Chỉ các byte thuộc `payload.position()` đến trước `payload.limit()` được gửi. Sau khi future hoàn thành bình thường, `ByteBuffer` đầu vào đã được tiêu thụ đến hết phần remaining. **Không đọc/sửa buffer trong khi thao tác gửi chưa hoàn thành.**

Có thể gửi nhiều fragment binary với `last == false` rồi kết thúc bằng `true`, nhưng không xen các lệnh text/binary không hợp lệ làm hỏng trạng thái message đang mở.

### 5.3. Ping, Pong và heartbeat

```java
webSocket.sendPing(ByteBuffer.wrap(new byte[] {42})).join();
```

Payload của Ping/Pong tối đa **125 byte** theo WebSocket Protocol. `sendPing` future hoàn thành có nghĩa **Ping đã được gửi**, không tự bảo đảm một Pong đã được nhận. Muốn đo liveness, dùng `onPong` để theo dõi phản hồi và timeout riêng.

Java WebSocket client **tự động gửi Pong tương ứng khi nhận Ping**, vì vậy thường **không cần tự gọi `sendPong` trong `onPing`**. Listener vẫn có thể quan sát Ping (và nhớ `request(1)` để nhận tiếp).

### 5.4. Đóng êm với sendClose và đóng cưỡng bức bằng abort

```java
webSocket.sendClose(WebSocket.NORMAL_CLOSURE, "").join();
```

`WebSocket.NORMAL_CLOSURE == 1000`. `sendClose` gửi Close frame và **đóng chiều gửi (output)** của WebSocket; chiều nhận **vẫn có thể đang mở** cho đến khi nhận được Close phản hồi, xảy ra lỗi hoặc gọi `abort()`.

Trong `Listener.onClose`, nhận status code và reason của peer; đây là callback cuối về phía input. Java client xử lý reciprocating Close theo giao thức khi thích hợp. **Không tự gọi `sendClose` thêm lần nữa một cách vô điều kiện từ mọi onClose**.

`sendClose` không phù hợp để hủy ngay lập tức mọi I/O còn chờ. Khi connection bị kẹt/hỏng, dùng `webSocket.abort()` để đóng cả chiều input/output đột ngột. Nó hữu ích trong cleanup khi có lỗi, **không phải cách đóng bình thường mỗi lần**.

Các mã close hợp lệ bị giới hạn; ví dụ `1006` là mã dùng để mô tả bất thường và **không được gửi** qua `sendClose`. Chuỗi reason khi gửi có biểu diễn UTF-8 tối đa **123 byte**. Khi muốn đóng bình thường, dùng hằng số `NORMAL_CLOSURE` và reason rỗng.

`isInputClosed()` và `isOutputClosed()` cho biết trạng thái hai chiều **riêng biệt**, không phải một flag “đã đóng toàn bộ” duy nhất.

## 6. Quy tắc về lỗi và trạng thái kết nối

### 6.1. Lỗi ở opening handshake

`buildAsync(...)` trả future có thể hoàn thành exceptional vì:

- Server từ chối upgrade hoặc trả response handshake không hợp lệ, có thể gây `WebSocketHandshakeException`.
- DNS, kết nối, TLS, proxy hoặc I/O thất bại (`IOException` hoặc nguyên nhân liên quan).
- Kết nối quá hạn `connectTimeout` (`HttpTimeoutException`).
- URI, header, subprotocol hay tham số builder không hợp lệ.

Khi dùng `future.get()`, lỗi kết nối thường xuất hiện qua `ExecutionException.getCause()`; với `join()` thường được bọc trong `CompletionException`. Ví dụ tách nguyên nhân:

```java
try {
    WebSocket ws = httpClient.newWebSocketBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .buildAsync(uri, listener)
            .get(8, TimeUnit.SECONDS);
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    if (cause instanceof WebSocketHandshakeException) {
        HttpResponse<?> rejected =
                ((WebSocketHandshakeException) cause).getResponse();
        // Kiểm tra status/headers nếu response khả dụng.
    }
    throw ex;
}
```

Đây là **mảnh mã**, không phải chương trình độc lập; cần import `ExecutionException`, `WebSocketHandshakeException`, `HttpResponse` và các biến phù hợp. Không log nguyên các header chứa token/credentials. `getResponse()` chủ yếu giúp chẩn đoán server từ chối handshake.

### 6.2. Lỗi sau khi kết nối

Nếu WebSocket gặp lỗi, `onError(WebSocket, Throwable)` được gọi. Nó là một tín hiệu kết thúc vòng đời theo Java API; đến khi bắt đầu callback, hai chiều input/output đã đóng. Cần báo lỗi cho logic ứng dụng, hủy tác vụ chờ và giải phóng trạng thái.

Ngoài `onError`, từng `sendText`/`sendBinary`/`sendClose` cũng có future **hoàn thành exceptional**. Không bỏ mặc future lỗi hoặc chặn vô hạn trên `join()`. Một request gửi message thất bại không luôn chứng minh server chưa nhìn thấy byte; với nghiệp vụ quan trọng, cần ACK/deduplication ở cấp ứng dụng.

### 6.3. Không tự động reconnect

API WebSocket client **không tự hứa khôi phục session, nối lại subscription hay gửi lại những message bị mất** sau khi đường truyền đứt. Nếu cần reconnect:

- Tạo kết nối mới bằng `newWebSocketBuilder().buildAsync(...)`.
- Giới hạn số lượt retry, dùng backoff/jitter, deadline và hỗ trợ hủy.
- Xác thực lại và thiết lập lại subprotocol hoặc subscription nghiệp vụ.
- Có cơ chế sequence ID/ACK/replay riêng để xử lý mất message hoặc trùng message.
- Bảo vệ trạng thái khi nhiều kết nối thay thế nhau; tránh hai socket cùng xử lý một tác vụ.

Không “retry vô hạn” một kết nối bị từ chối handshake hoặc bị chặn xác thực mà không phân biệt nguyên nhân.

## 7. Chương trình Java 11 chạy thật: WebSocket client và loopback server thử nghiệm

Để kiểm thử đầy đủ **không cần Internet**, ví dụ này dùng `ServerSocket` tại `127.0.0.1` làm **server WebSocket thử nghiệm tối giản** chỉ hỗ trợ handshake và các frame nhỏ cần cho bài. Client vẫn sử dụng **đúng API Java 11 `java.net.http.WebSocket`**. Server tự gửi đúng `101 Switching Protocols` và `Sec-WebSocket-Accept` của RFC 6455, nhận frame có mask từ client và gửi frame **không mask** theo quy tắc server.

**Những gì bài test xác minh:**

1. `HttpClient.newWebSocketBuilder().buildAsync` hoàn tất handshake.
2. Client gửi **một text message phân mảnh** bằng `sendText("hello ", false)` rồi `sendText("server", true)`.
3. Server nhận nguyên `hello server` và gửi về **text fragment** `Xin ` + `chào Java 11`.
4. Client ghép text đúng đến `last == true`.
5. Server gửi Ping; client nhận callback `onPing` và **tự động gửi Pong**.
6. Server gửi binary `{1,2,3}`; client nhận `onBinary`.
7. Client gọi `sendClose(1000, "")`; server phản hồi Close, client nhận `onClose(1000, ...)` và hai chiều đều đóng.

**Lưu ý:** server được viết chỉ để test các frame nhỏ có payload `≤125` byte; nó không xử lý mọi kích thước/frame/extension/timeout như server production. **Không dùng lớp server này làm WebSocket server dịch vụ thật.**

Tạo file **`WebSocketClientDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Arrays;
import java.util.Base64;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class WebSocketClientDemo {
    static class ClientListener implements WebSocket.Listener {
        final CompletableFuture<String> text = new CompletableFuture<>();
        final CompletableFuture<String> binary = new CompletableFuture<>();
        final CompletableFuture<Integer> closed = new CompletableFuture<>();
        final AtomicInteger pings = new AtomicInteger();
        final StringBuilder textParts = new StringBuilder();
        final ByteArrayOutputStream binaryParts = new ByteArrayOutputStream();

        @Override public void onOpen(WebSocket ws) {
            ws.request(1);
        }
        @Override public CompletionStage<?> onText(WebSocket ws,
                CharSequence fragment, boolean last) {
            textParts.append(fragment);
            if (last) {
                text.complete(textParts.toString());
                textParts.setLength(0);
            }
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }
        @Override public CompletionStage<?> onBinary(WebSocket ws,
                ByteBuffer part, boolean last) {
            byte[] bytes = new byte[part.remaining()];
            part.get(bytes);
            binaryParts.write(bytes, 0, bytes.length);
            if (last) {
                binary.complete(Arrays.toString(binaryParts.toByteArray()));
                binaryParts.reset();
            }
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }
        @Override public CompletionStage<?> onPing(
                WebSocket ws, ByteBuffer message) {
            pings.incrementAndGet();
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }
        @Override public CompletionStage<?> onClose(WebSocket ws,
                int statusCode, String reason) {
            closed.complete(statusCode);
            return CompletableFuture.completedFuture(null);
        }
        @Override public void onError(WebSocket ws, Throwable error) {
            text.completeExceptionally(error);
            binary.completeExceptionally(error);
            closed.completeExceptionally(error);
        }
    }

    static class Frame {
        final int opcode;
        final boolean fin;
        final byte[] data;
        Frame(int opcode, boolean fin, byte[] data) {
            this.opcode = opcode;
            this.fin = fin;
            this.data = data;
        }
    }
    static class ServerResult {
        final String received;
        final boolean gotPong;
        final int closeCode;
        ServerResult(String r, boolean p, int c) {
            received = r;
            gotPong = p;
            closeCode = c;
        }
    }

    private static byte[] exact(InputStream in, int count) throws Exception {
        byte[] bytes = in.readNBytes(count);
        if (bytes.length != count) {
            throw new EOFException("Incomplete WebSocket frame");
        }
        return bytes;
    }

    private static Frame readMasked(InputStream in) throws Exception {
        int b1 = in.read(), b2 = in.read();
        if (b1 < 0 || b2 < 0) throw new EOFException("No frame");
        int size = b2 & 0x7f;
        if ((b2 & 0x80) == 0 || size > 125) {
            throw new IllegalStateException(
                    "This demo expects masked small frames");
        }
        byte[] mask = exact(in, 4);
        byte[] data = exact(in, size);
        for (int i = 0; i < data.length; i++) {
            data[i] ^= mask[i & 3];
        }
        return new Frame(b1 & 15, (b1 & 0x80) != 0, data);
    }

    private static void send(OutputStream out, int opcode,
            boolean fin, byte[] data) throws Exception {
        if (data.length > 125) {
            throw new IllegalArgumentException("small demo frame");
        }
        out.write((fin ? 0x80 : 0) | opcode);
        out.write(data.length);
        out.write(data);
        out.flush();
    }

    private static ServerResult runServer(
            ServerSocket server) throws Exception {
        try (Socket socket = server.accept()) {
            socket.setSoTimeout(5000);
            InputStream in = socket.getInputStream();
            OutputStream out = socket.getOutputStream();

            ByteArrayOutputStream headers = new ByteArrayOutputStream();
            int end = 0;
            while (end != 0x0D0A0D0A) {
                int next = in.read();
                if (next == -1 || headers.size() >= 8192) {
                    throw new EOFException("Handshake incomplete");
                }
                headers.write(next);
                end = (end << 8) | next;
            }
            String opening = new String(
                    headers.toByteArray(), StandardCharsets.US_ASCII);
            String key = null;
            for (String line : opening.split("\r\n")) {
                if (line.toLowerCase(java.util.Locale.ROOT)
                        .startsWith("sec-websocket-key:")) {
                    key = line.substring(line.indexOf(':') + 1).trim();
                }
            }
            if (key == null || !opening.startsWith("GET /echo ")) {
                throw new IllegalStateException("Invalid opening handshake");
            }

            byte[] digest = MessageDigest.getInstance("SHA-1")
                    .digest((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                            .getBytes(StandardCharsets.US_ASCII));
            String accept = Base64.getEncoder().encodeToString(digest);
            String response = "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
            out.write(response.getBytes(StandardCharsets.US_ASCII));
            out.flush();

            Frame first = readMasked(in);
            Frame second = readMasked(in);
            if (first.opcode != 1 || first.fin || second.opcode != 0
                    || !second.fin) {
                throw new IllegalStateException("Expected fragmented text");
            }
            ByteArrayOutputStream received = new ByteArrayOutputStream();
            received.write(first.data);
            received.write(second.data);
            String clientText = received.toString(
                    StandardCharsets.UTF_8.name());
            if (!clientText.equals("hello server")) {
                throw new IllegalStateException("Unexpected client message");
            }

            send(out, 1, false, "Xin ".getBytes(StandardCharsets.UTF_8));
            send(out, 0, true, "chào Java 11"
                    .getBytes(StandardCharsets.UTF_8));
            send(out, 9, true, new byte[] {42});
            Frame pong = readMasked(in);
            if (pong.opcode != 10
                    || !Arrays.equals(pong.data, new byte[] {42})) {
                throw new IllegalStateException("Automatic Pong not received");
            }
            send(out, 2, true, new byte[] {1, 2, 3});

            Frame close = readMasked(in);
            if (close.opcode != 8 || close.data.length < 2) {
                throw new IllegalStateException("Close frame missing");
            }
            int code = ((close.data[0] & 0xff) << 8)
                    | (close.data[1] & 0xff);
            send(out, 8, true, new byte[] {(byte) 3, (byte) 232});
            return new ServerResult(clientText, true, code);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket(0, 1,
                InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(5000);
            ExecutorService pool = Executors.newSingleThreadExecutor();
            WebSocket ws = null;
            try {
                Future<ServerResult> serverRun =
                        pool.submit(() -> runServer(server));
                ClientListener listener = new ClientListener();
                URI uri = URI.create("ws://127.0.0.1:"
                        + server.getLocalPort() + "/echo");
                ws = HttpClient.newHttpClient()
                        .newWebSocketBuilder()
                        .connectTimeout(Duration.ofSeconds(5))
                        .buildAsync(uri, listener)
                        .get(5, TimeUnit.SECONDS);

                ws.sendText("hello ", false).get(5, TimeUnit.SECONDS);
                ws.sendText("server", true).get(5, TimeUnit.SECONDS);
                String received =
                        listener.text.get(5, TimeUnit.SECONDS);
                String receivedBinary =
                        listener.binary.get(5, TimeUnit.SECONDS);
                ws.sendClose(WebSocket.NORMAL_CLOSURE, "")
                        .get(5, TimeUnit.SECONDS);
                int code = listener.closed.get(5, TimeUnit.SECONDS);
                ServerResult sr = serverRun.get(5, TimeUnit.SECONDS);

                if (!received.equals("Xin chào Java 11")
                        || !receivedBinary.equals("[1, 2, 3]")
                        || !sr.received.equals("hello server")
                        || !sr.gotPong || listener.pings.get() != 1
                        || code != 1000 || sr.closeCode != 1000
                        || !ws.isInputClosed() || !ws.isOutputClosed()) {
                    throw new AssertionError("WebSocket test failed");
                }
                System.out.println("client connected = true");
                System.out.println("server received = " + sr.received);
                System.out.println("client text = " + received);
                System.out.println("client binary = " + receivedBinary);
                System.out.println("ping callbacks = " + listener.pings.get());
                System.out.println("automatic pong = " + sr.gotPong);
                System.out.println("close code = " + code);
                System.out.println("input/output closed = "
                        + ws.isInputClosed() + "/" + ws.isOutputClosed());
                System.out.println("ALL CHECKS PASSED");
            } finally {
                if (ws != null
                        && (!ws.isInputClosed() || !ws.isOutputClosed())) {
                    ws.abort();
                }
                server.close();
                pool.shutdownNow();
                pool.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }
}
```

**Biên dịch và chạy:** lưu file ở thư mục bất kỳ với JDK 11 trở lên; không cần thư viện ngoài, proxy hay server trên Internet.

```bash
javac --release 11 WebSocketClientDemo.java
java WebSocketClientDemo
```

**Đầu ra đã kiểm chứng bằng biên dịch/chạy thực tế:**

```text
client connected = true
server received = hello server
client text = Xin chào Java 11
client binary = [1, 2, 3]
ping callbacks = 1
automatic pong = true
close code = 1000
input/output closed = true/true
ALL CHECKS PASSED
```

### Giải thích kiểm thử

- `client connected = true`: future từ `buildAsync` hoàn thành bình thường, nghĩa là handshake đã được client chấp nhận.
- `server received = hello server`: hai lời gọi `sendText` với `last=false/true` tạo đúng một message text. Server kiểm tra opcode text đầu tiên và opcode continuation ở frame tiếp theo.
- `client text = Xin chào Java 11`: server phát hai frame text, Listener ghép đoạn và hoàn tất khi `last == true`. Số lần `onText` có thể thay đổi theo cách nhận/ghép dữ liệu của implementation; test chỉ kiểm tra message cuối.
- `client binary = [1, 2, 3]`: `onBinary` chỉ đọc phần remaining của `ByteBuffer` và hoàn tất message khi `last == true`.
- `ping callbacks = 1` và `automatic pong = true`: server gửi Ping một byte, client nhận callback rồi Java client trả Pong tương ứng **mà không cần gọi `sendPong` thủ công**.
- `close code = 1000` và `input/output closed = true/true`: client gửi Close 1000, server trả Close 1000, Listener nhận sự kiện kết thúc và hai chiều của client đã đóng.
- `ALL CHECKS PASSED`: các assertion và future có timeout đều thành công.

**Giới hạn của server test:** bộ đọc frame chỉ hỗ trợ payload nhỏ, frame từ client có mask, và đúng luồng thao tác của bài. WebSocket thực còn có trường độ dài mở rộng, nhiều loại extension, nhiều client đồng thời và các ràng buộc RFC 6455 khác. Hãy dùng server framework được duy trì nếu xây sản phẩm, không dùng trực tiếp server test này.

## 8. Xử lý dữ liệu thực tế và vấn đề hiệu năng

### 8.1. Giới hạn kích thước, không gom vô hạn

Ví dụ dùng `StringBuilder` và `ByteArrayOutputStream` để minh họa fragment. Trong ứng dụng thực, server có thể gửi message lớn hoặc vô hạn. Trước khi append, kiểm tra tổng số byte/ký tự theo chính sách; nếu vượt giới hạn thì báo lỗi và đóng/hủy kết nối phù hợp.

`request(n)` giúp kiểm soát số callback được giao, nhưng **không thay thế giới hạn kích thước message**, giới hạn hàng đợi xử lý và timeout.

### 8.2. Không block trong Listener

Nếu `onText` làm truy vấn database chậm, gọi mạng đồng bộ hoặc xử lý CPU lâu, thông lượng nhận sẽ bị ảnh hưởng. Có thể copy payload rồi đưa sang executor/queue có giới hạn và kiểm soát demand phù hợp. Không gọi `webSocket.request(1)` vô hạn khi hàng đợi đang quá tải, vì nó có thể làm mất ý nghĩa backpressure.

Giữ trạng thái `StringBuilder` theo từng WebSocket. Nếu ứng dụng dùng một Listener cho nhiều kết nối, cần quản lý map trạng thái riêng hoặc tạo listener mới cho mỗi kết nối.

### 8.3. Xác thực, TLS và thông tin nhạy cảm

- Ưu tiên `wss://` khi có token, dữ liệu cá nhân hoặc mạng không đáng tin cậy.
- Không vô hiệu hóa kiểm tra certificate chỉ để kết nối thành công.
- Không tự thêm WebSocket protocol header bị cấm qua `Builder.header`.
- Kiểm tra URI được lấy từ cấu hình/người dùng theo allowlist, host và scheme để tránh kết nối tới đích không được phép.
- Chỉ gửi token đến endpoint đáng tin; không in token và nội dung bí mật trong log/exception.
- Đánh giá proxy, certificate và cơ chế authentication từ `HttpClient` cùng yêu cầu server.
- Chọn subprotocol duy nhất theo hợp đồng hai phía; việc handshake thành công không chứng minh người dùng đã được xác thực hay dữ liệu hợp lệ.

### 8.4. Mất kết nối, reconnect và idempotency thông điệp

Gửi message qua WebSocket là bất đồng bộ. Nếu tương lai gửi hoàn thành rồi kết nối mất trước khi nhận ACK của server, không thể kết luận nghiệp vụ đã hoặc chưa xử lý. Với tác vụ thanh toán, ghi dữ liệu hoặc yêu cầu phải đúng một lần, cần protocol ứng dụng có message ID, ACK, deduplication hoặc cơ chế truy vấn trạng thái.

Không gửi lại toàn bộ message pending một cách mù quáng sau reconnect; nếu server đã nhận, có thể tạo tác dụng phụ trùng.

## 9. Bảng lỗi thường gặp

| Vấn đề | Nguyên nhân thường gặp | Cách giải quyết |
| --- | --- | --- |
| `buildAsync` thất bại khi dùng URL | Dùng `http://`/`https://` sai vị trí, server không WebSocket, TLS/handshake lỗi | Dùng URI `ws://` hoặc `wss://`, kiểm tra endpoint và nguyên nhân exception |
| Server trả 404/400 khi handshake | Đường dẫn, header hoặc xác thực không đúng | Xem `WebSocketHandshakeException.getResponse()` khi có |
| Kết nối mở nhưng callback text không chạy | Quên `request(1)` sau `onOpen` hoặc sau callback đầu | Cấp demand đúng cho mỗi lần nhận |
| Nhận text bị thiếu/đứt đoạn | Coi mỗi `onText` là message hoàn chỉnh | Gộp fragment tới `last == true` |
| `sendText` tương lai lỗi `IllegalStateException` | Có send text/binary pending hoặc trộn fragment chưa kết thúc | Chờ future trước; nối `thenCompose` |
| Không nhận được Pong như kỳ vọng | Chỉ đợi future `sendPing`, chưa theo dõi `onPong` | Ghi nhận Pong, áp dụng timeout riêng |
| Ping lặp thêm Pong | Tự `sendPong` trong `onPing` khi client đã auto-reply | Thường không cần `sendPong` thủ công |
| Đóng xong sendClose nhưng input vẫn mở | `sendClose` chỉ đóng chiều gửi | Chờ `onClose` hoặc abort khi quá hạn |
| Thử gọi `sendClose(1006, ...)` | Mã 1006 không được gửi theo giao thức | Dùng `NORMAL_CLOSURE` hoặc close code hợp lệ |
| Sau exception app vẫn chờ kết quả | Không hoàn thành future của nghiệp vụ trong `onError` | Ghi nhận lỗi, đóng kết nối, thông báo waiter |
| Nối tiếp khi source stream đã mất | Không có reconnect/session resume tự động | Xây chính sách reconnect và ứng dụng đồng bộ trạng thái |
| Buffer nhận bị dùng sau callback | WebSocket có thể tái sử dụng backing memory sau `CompletionStage` | Copy byte nếu xử lý bất đồng bộ |
| OOM khi nhận message lớn | Append payload vô hạn | Giới hạn kích thước, flow demand, queue và timeouts |
| Dùng cùng builder ở nhiều thread | `WebSocket.Builder` không thread-safe | Tạo builder riêng hoặc đồng bộ hóa |
| Nhầm WebSocket client là WebSocket server | `java.net.http` không cung cấp server WebSocket tổng quát | Dùng server framework phù hợp |

## 10. Câu hỏi và bài tập

**1.** Tại sao `HttpClient.newHttpClient().newWebSocketBuilder().buildAsync(...)` trả `CompletableFuture<WebSocket>` chứ không trả `WebSocket` ngay?  
**Đáp án:** Vì kết nối và opening handshake diễn ra bất đồng bộ; future có thể thất bại hoặc thành công sau đó.

**2.** Nếu `Listener.onOpen` không gọi `request(1)`, điều gì xảy ra?  
**Đáp án:** Lượng demand ban đầu là `0`; nếu không có lượt cấp demand, client sẽ không gọi các callback nhận. Lưu ý *default implementation* của `onOpen` tự request(1); nhưng khi **override** mà không gọi `super`/`request`, phải chủ động yêu cầu.

**3.** `request(1)` có nghĩa “nhận đúng một text message” không?  
**Đáp án:** Không. Nó cấp một lượt callback nhận. Một message có thể được chia thành nhiều callback với `last=false` rồi `last=true`.

**4.** Muốn gửi một message `"Hello world"` bằng hai đoạn thì gọi thế nào?  
**Đáp án:** `sendText("Hello ", false)` rồi khi tương lai hoàn thành, `sendText("world", true)`. Không bắt đầu send mới khi send cũ còn pending.

**5.** Khi server gửi Ping, có cần tự gửi Pong trong `onPing` không?  
**Đáp án:** Thường không. Java WebSocket tự gửi Pong tương ứng; callback có thể dùng để quan sát và request tiếp.

**6.** `sendClose(1000,"")` hoàn thành có chắc kết nối đã đóng cả chiều nhận lẫn gửi không?  
**Đáp án:** Không. Nó đóng chiều gửi; cần nhận Close phản hồi hoặc xử lý timeout/`abort`.

**7.** WebSocket qua mạng Internet có token nên dùng `ws://` hay `wss://`?  
**Đáp án:** Dùng `wss://` để bảo vệ kênh bằng TLS; kết hợp xác thực, kiểm tra server certificate và chính sách endpoint.

**8.** `WebSocketHandshakeException` được dùng khi nào, chẩn đoán bằng gì?  
**Đáp án:** Khi opening handshake thất bại. Có thể lấy HTTP response tương ứng qua `getResponse()` để xem status/headers và chẩn đoán (ẩn thông tin nhạy cảm).

**9.** Khi kết nối đứt, client Java 11 có tự phát lại tất cả message đã gửi không?  
**Đáp án:** Không có bảo đảm như vậy. Ứng dụng cần thiết kế reconnect, xác thực lại, protocol ACK/sequence và deduplication.

## 11. Ghi nhớ

- WebSocket client tiêu chuẩn Java 11 nằm trong **`java.net.http`**. Tạo kết nối bằng `HttpClient.newWebSocketBuilder().buildAsync(wsUri, listener)`.
- Dùng `ws://` cho kết nối không TLS; **ưu tiên `wss://`** khi truyền dữ liệu qua mạng và có thông tin nhạy cảm.
- **`WebSocket.Listener` nhận sự kiện**, còn `webSocket.request(n)` cấp quyền nhận theo **số callback**. Ráp text/binary đến `last=true` mới có một message hoàn chỉnh.
- Gửi bằng `sendText`/`sendBinary`; các `CompletableFuture` báo trạng thái **send phía client**, không phải xác nhận nghiệp vụ từ server.
- Ping/Pong hỗ trợ theo dõi kết nối; Java **tự Pong khi nhận Ping**.
- `sendClose` đóng êm chiều gửi, `onClose` báo peer Close; `abort()` đóng ngay khi cần. Quản lý timeout và cleanup.
- Java không tự hứa reconnect, replay message hay đúng một lần cho nghiệp vụ. Phải tự triển khai policy cấp ứng dụng khi cần.

### Nguồn tài liệu đang được hỗ trợ

- [Java SE 11 — WebSocket API, sendText/sendBinary/sendPing/sendClose/request](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html)
- [Java SE 11 — WebSocket.Builder và buildAsync](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Builder.html)
- [Java SE 11 — WebSocket.Listener, onOpen/onText/onBinary/onClose/onError](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
- [Java SE 11 — HttpClient.newWebSocketBuilder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 11 — WebSocketHandshakeException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocketHandshakeException.html)
- [Java SE 25 — WebSocket API còn áp dụng](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/WebSocket.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)
