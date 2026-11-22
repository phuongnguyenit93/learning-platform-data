# WebSocket.Builder, subprotocol và kết nối bất đồng bộ trong Java 17+

**`WebSocket.Builder`** là API tạo WebSocket client thuộc module `java.net.http` (Java 11+, dùng ổn định trong Java 17). Bạn lấy builder từ `HttpClient.newWebSocketBuilder()`, cấu hình các header bổ sung, thứ tự ưu tiên **subprotocol** và timeout thiết lập kết nối, rồi gọi `buildAsync(URI, WebSocket.Listener)`. Kết quả là **`CompletableFuture<WebSocket>`**, chứ không phải socket đã kết nối ngay lập tức. Khi handshake thành công, bạn có thể gửi dữ liệu bằng các phương thức async trả future và nhận qua `WebSocket.Listener` với cơ chế `request(n)`.

Một sai lầm dễ gặp là hiểu `subprotocols("chat.v2", "chat.v1")` nghĩa Java **ép** server sử dụng `chat.v2`. Thực tế client chỉ **đề xuất các lựa chọn theo thứ tự ưu tiên**. Server chọn một subprotocol được chấp nhận, hoặc có thể không chọn subprotocol nào; phía client phải kiểm tra **`socket.getSubprotocol()`** và từ chối tiếp tục nếu ứng dụng bắt buộc một giao thức riêng.

Bài thuộc mục **WebSocket** của **Java Advance - networking**. Nội dung đi từ cơ chế HTTP opening handshake, builder, async completion và lỗi handshake đến lựa chọn subprotocol, listener demand, fragmentation, vòng đời close/abort, bảo mật và hai chương trình Java 17+ chạy độc lập trên loopback (một handshake thành công, một handshake bị từ chối HTTP 403).

## 1. WebSocket dùng khi nào, khác HTTP request–response ra sao?

HTTP thường được ứng dụng dùng theo từng cặp **request → response**. WebSocket thiết lập một **kênh thông điệp hai chiều lâu dài**: sau khi opening handshake hợp lệ, cả client và server có thể gửi text/binary messages mà không cần tạo một HTTP request riêng cho mỗi tin nhắn. Nó phù hợp chat, presence, bảng giá/cập nhật trạng thái theo thời gian thực, trò chơi hoặc notification.

```text
HTTP truyền thống:
client -- GET /updates --> server
client <-- JSON response -- server
client -- GET /updates --> server
client <-- JSON response -- server

WebSocket:
client -- HTTP opening handshake --> server
client <-- 101 Switching Protocols - server
             [duy trì kết nối]
client --> text/binary message --> server
client <-- event/message -------- server
client --> ping/close ----------> server
```

WebSocket **không tự biến mọi lời gọi thành giao dịch tin cậy**: còn có disconnect, mất dữ liệu khi process chết, ordering business, retry, authorization và kiểm soát queue. Protocol WebSocket truyền message trên một kết nối, nhưng **không tự cấp exactly-once delivery hoặc message persistence**; nếu hệ thống cần, ứng dụng phải tự xây sequence number/ACK/replay.

Trong Java 17, API `java.net.http.WebSocket` là **WebSocket client**, không kèm một WebSocket server production trong cùng package. Ví dụ bên dưới tự viết một server RFC 6455 tối giản **chỉ để kiểm chứng trên loopback**, không thay cho server/framework hoàn chỉnh.

## 2. HTTP opening handshake là điểm chuyển trạng thái

Với `ws://`, client mở TCP và gửi HTTP opening handshake. Một request minh họa:

```http
GET /chat HTTP/1.1
Host: example.test
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: <base64-nonce>
Sec-WebSocket-Protocol: chat.v2, chat.v1
X-Demo: present
```

Phản hồi hợp lệ có thể là:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <calculated-value>
Sec-WebSocket-Protocol: chat.v2
```

Hai ví dụ HTTP trên là **minh họa giao thức**, không phải chuỗi để copy làm Java code. Trong thực tế JDK tự tạo `Sec-WebSocket-Key` và kiểm tra `Sec-WebSocket-Accept`. **Không tự set lại các header WebSocket được protocol định nghĩa** qua `WebSocket.Builder.header`.

`Sec-WebSocket-Accept` được tạo từ `Base64(SHA-1(Sec-WebSocket-Key + GUID))` theo RFC 6455. Đây là **quy tắc xác nhận handshake của protocol**, **không** phải cách hash password hoặc chữ ký xác thực danh tính server. Với `wss://`, bảo mật kênh cần TLS/hostname verification đúng chuẩn.

**Trạng thái chính:**

- Trước `101`: vẫn là HTTP handshake; lỗi 401/403/404 hoặc invalid handshake không tạo WebSocket có thể sử dụng.
- Sau handshake hợp lệ: bên gửi/nhận trao đổi **WebSocket frames**, không xử lý mỗi tin như HTTP body mới.
- Khi close frame hoặc lỗi: hai phía tiến tới trạng thái output/input closed theo quy tắc `WebSocket`.

## 3. API căn bản: lấy builder từ HttpClient

Mẫu phổ biến:

```java
// Snippet minh họa: URI endpoint và listener được định nghĩa bên ngoài.
HttpClient client = HttpClient.newHttpClient();

WebSocket.Builder builder = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .subprotocols("chat.v2", "chat.v1")
        .header("X-Request-Id", "request-123");

CompletableFuture<WebSocket> connection =
        builder.buildAsync(endpoint, listener);
```

Đoạn trên **chưa phải chương trình độc lập**, cần imports/khai báo `endpoint`, `listener`. Những chi tiết đáng nhớ:

1. `HttpClient.newWebSocketBuilder()` thuộc `HttpClient`, không gọi `new WebSocket.Builder()` vì `Builder` là interface.
2. `WebSocket.Builder` có trạng thái **mutable**, **không an toàn cho nhiều thread sửa đồng thời**. Xây builder cho một connection trong một luồng khởi tạo; không chia sẻ cùng builder để hàng trăm task gọi `subprotocols/header/buildAsync` cùng lúc.
3. `HttpClient` đã build là immutable và có thể được chia sẻ theo policy; bạn có thể gọi `sharedClient.newWebSocketBuilder()` **riêng cho từng kết nối**.
4. `buildAsync` trả `CompletableFuture<WebSocket>`; chỉ khi future complete **bình thường** thì bạn có một WebSocket đã bắt tay thành công. Không gọi `sendText` trên một `WebSocket` chưa nhận được.
5. `HttpClient.newWebSocketBuilder()` là **optional operation** của interface. Các clients chuẩn tạo bằng `HttpClient.newHttpClient()` hoặc builder mặc định của JDK hỗ trợ; một custom `HttpClient` implementation có thể báo `UnsupportedOperationException`.

Builder cấu hình handshake **một kết nối**. Nó không phải registry quản lý room, subscription domain hay bộ đệm messages của ứng dụng.

## 4. Bốn thao tác chính của WebSocket.Builder

| Phương thức | Trách nhiệm | Cần tránh |
| --- | --- | --- |
| `header(String name, String value)` | Bổ sung HTTP headers hợp lệ trong **opening handshake** | Không tự ghi các WebSocket protocol headers bị cấm; không log bearer token |
| `connectTimeout(Duration timeout)` | Giới hạn thời gian **thiết lập WebSocket** | Không hiểu đây là timeout mọi tin nhắn sau khi đã kết nối |
| `subprotocols(String mostPreferred, String... lesserPreferred)` | Đề xuất subprotocols theo **thứ tự ưu tiên** | Không coi subprotocol là version TLS hay auth |
| `buildAsync(URI uri, WebSocket.Listener listener)` | Thực hiện async opening handshake, trả future | Không đồng nhất future tạo ra với kết nối đã sẵn sàng |

Một số giả định thực tế:

- Không gọi `subprotocols` thì **không yêu cầu** subprotocol nào, và `getSubprotocol()` sẽ là chuỗi rỗng nếu không có lựa chọn được thiết lập.
- `connectTimeout` phải là Duration dương theo hợp đồng; không dùng `Duration.ZERO` hay âm. Nếu không thiết lập, API mô tả **không có timeout hữu hạn mặc định cho việc thiết lập**.
- `header` thêm header để server xác thực/routing/trace trong handshake; không biến mọi WebSocket message sau này thành HTTP request có header riêng.
- `buildAsync` có thể hoàn tất exceptionally với `IOException`, `WebSocketHandshakeException`, `HttpTimeoutException`, `InterruptedException` hoặc lỗi cấu hình/permission tùy trường hợp.

Không bọc toàn bộ lifecycle trong một builder rồi gọi `buildAsync` lại khi reconnect mà không kiểm soát listener state/credential; với reconnect nên tạo **builder mới**, URI, policy và listener của kết nối mới.

## 5. Subprotocol không phải extension hay URI path

**Subprotocol** là **giao thức ứng dụng** diễn giải WebSocket messages, ví dụ `chat.v2` hoặc `json.rpc.v1`. Nó không phải phiên bản WebSocket transport (RFC 6455 version 13), không phải HTTP method và không phải negotiated TLS cipher suite.

```text
Client ưu tiên:
  chat.v2 (cao nhất)
  chat.v1 (thấp hơn)

Sec-WebSocket-Protocol: chat.v2, chat.v1
                    |
                 Server
                    |
                    +-- hiểu chat.v2 -> chọn chat.v2
                    +-- chỉ hiểu chat.v1 -> có thể chọn chat.v1
                    +-- không chọn -> không có negotiated subprotocol
```

Cấu hình Java:

```java
// Snippet: builder là WebSocket.Builder chưa dùng đồng thời.
builder.subprotocols("chat.v2", "chat.v1");
```

Sau kết nối:

```java
// Snippet: socket là WebSocket đã được buildAsync hoàn thành.
String selected = socket.getSubprotocol();
if (!"chat.v2".equals(selected) && !"chat.v1".equals(selected)) {
    // Nếu nghiệp vụ bắt buộc một lựa chọn: đóng/từ chối.
    socket.sendClose(WebSocket.NORMAL_CLOSURE,
            "Unsupported subprotocol");
}
```

Điều kiện lựa chọn phải do **protocol ứng dụng** quy định. Nếu client chỉ triển khai schema `chat.v2` mà server chọn `chat.v1`, đừng tiếp tục gửi messages v2. Nếu không có subprotocol và ứng dụng quy định default protocol rõ ràng, có thể cho phép; nếu bắt buộc negotiation, phải từ chối.

Server phải **chọn tối đa một subprotocol đã được client đề xuất**; không được tùy tiện trả token khác. Subprotocol IDs phải thỏa cú pháp token hợp lệ; không nhét URL, JSON, dấu cách hoặc user secret vào tên subprotocol. Thứ tự do client đưa ra là **mức ưu tiên**, server không bị ép luôn chọn phần tử đầu.

## 6. Khi nào client không nhận được subprotocol?

`socket.getSubprotocol()` trả **`""`** nếu handshake không thiết lập subprotocol. Các tình huống:

1. Client không gọi `subprotocols` và server không lựa chọn.
2. Client có đề xuất nhưng server hợp lệ quyết định không lựa chọn, nếu ứng dụng cho phép.
3. Một proxy/server không hỗ trợ negotiation riêng; tùy hành vi, handshake có thể hoàn tất không có subprotocol hoặc thất bại.

**Đừng suy ra** vì `buildAsync` thành công mà protocol nội dung đã tương thích. Nếu app truyền JSON theo schema cụ thể, kiểm tra negotiated subprotocol **trước khi gửi business messages**.

Ví dụ policy:

```java
// Snippet minh họa cho ứng dụng chỉ hỗ trợ chat.v2.
WebSocket connected = future.get(10, TimeUnit.SECONDS);
if (!"chat.v2".equals(connected.getSubprotocol())) {
    connected.sendClose(WebSocket.NORMAL_CLOSURE,
            "Protocol mismatch");
    throw new IllegalStateException("Unsupported subprotocol");
}
```

Ở production, có thể dùng một mã close phù hợp policy và hoàn tất handshake close với deadline; không mặc định gọi `abort()` chỉ vì version fallback chưa hỗ trợ. Nếu server chọn một giá trị không nằm trong offer set, đó là **lỗi opening handshake/protocol**, không phải cơ sở để lặng lẽ parse message theo một token không được quảng bá.

## 7. `ws://` và `wss://`: subprotocol không tạo bảo mật

WebSocket URIs thường là:

```text
ws://localhost:8080/chat
wss://api.example.test/realtime
```

- **`ws://`** dùng kết nối WebSocket không mã hóa TLS. Nó phù hợp demo loopback và môi trường có threat model rõ; không phù hợp truyền token/user data nhạy cảm qua mạng không đáng tin.
- **`wss://`** sử dụng TLS để bảo vệ nội dung và xác thực server theo cấu hình trust/endpoint verification. Production trên Internet thường dùng `wss://`.
- **Subprotocol** như `chat.v2` chỉ định cách hiểu messages, **không mã hóa** dữ liệu và **không xác thực** người dùng.
- **URI path/query** được gửi trong opening handshake; tránh đặt access token lâu hạn ở query vì proxy/access logs thường ghi URL.
- **CORS** của HTTP không phải một cơ chế authorization cho WebSocket server. Server phải xác thực identity/cookie/token/origin theo threat model và kiểm soát quyền trên mỗi channel/message.

Với `wss://`, có thể cấu hình `HttpClient.newBuilder().sslContext(customContext).build()` trong hệ thống cần private CA/mTLS. Nhưng truststore/custom `SSLContext` sai có thể làm TLS handshake thất bại trước cả WebSocket handshake; không chữa bằng trust-all manager.

## 8. Thêm header đúng cách trong opening handshake

`WebSocket.Builder.header(name, value)` thêm **HTTP request header bổ sung**. Các header `Sec-WebSocket-Key`, `Sec-WebSocket-Version`, `Sec-WebSocket-Protocol`, `Connection`, `Upgrade` thuộc giao thức mở WebSocket và cần được JDK quản lý; API cấm tự thêm các header đã được protocol định nghĩa.

```java
// Snippet minh họa: token do hệ thống secret quản lý.
builder.header("X-Trace-Id", traceId);
builder.header("Authorization", "Bearer " + accessToken);
```

Lưu ý:

- Header ở đây dùng **khi bắt tay**. Một message `sendText` sau đó **không có HTTP Authorization header mới**; nếu cần refresh session/credential, phải có application protocol hoặc kết nối mới.
- Server/proxy có thể đọc/kiểm tra header rồi từ chối handshake với HTTP 401/403. Không phải mọi header tùy ý đều được proxy giữ nguyên; cần test đường đi thật.
- Không chia sẻ builder mutable với Authorization header của user A rồi tái sử dụng cho user B. Tạo builder cho connection có security scope rõ.
- Không in `Authorization`, cookies, query credentials hay full handshake headers trong logs của bài test/production.
- Không dùng subprotocol làm nơi chứa token bí mật; token subprotocol có thể lộ trong handshake logs và phải theo cú pháp identifier.
- Có thể gắn correlation ID vào handshake; muốn trace từng WebSocket message, cần **message-level operation ID** trong format của subprotocol.

Ví dụ Java loopback chỉ dùng `X-Demo: present` nhằm kiểm tra builder chuyển header; không có credential thật.

## 9. Timeout của `buildAsync` không phải timeout nhận messages

`WebSocket.Builder.connectTimeout(Duration)` giới hạn **thiết lập kết nối WebSocket**. Nếu handshake không được hoàn tất trong giới hạn, future có thể hoàn tất exceptionally với `HttpTimeoutException`.

```java
// Snippet: không dùng toàn bộ API vào một class độc lập.
CompletableFuture<WebSocket> future =
        client.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .subprotocols("chat.v2")
                .buildAsync(uri, listener);

WebSocket socket = future.get(8, TimeUnit.SECONDS);
```

Hai timeout khác nhau:

- `connectTimeout(5s)` thuộc **builder/connection establishment** và JDK WebSocket client.
- `future.get(8s)` thuộc **thread đang đợi completion**. Nếu nó ném `TimeoutException`, điều đó **không tự hủy future**; application phải quyết định cancellation/cleanup theo lifecycle policy.

Sau khi đã kết nối, hai giá trị trên **không phải idle timeout hay per-message processing timeout**. Ứng dụng cần riêng heartbeat (ping/pong), deadline phản hồi nghiệp vụ, giới hạn queue, deadline close và reconnect strategy.

**Không nên dùng `join()` trong event-loop hoặc UI thread nếu nó có thể block lâu.** `buildAsync` bản thân là asynchronous nhưng người gọi có thể chủ động chờ bằng `join()/get()`; ở backend event-driven nên `thenCompose/whenComplete` để giữ tính bất đồng bộ.

## 10. Kết nối bất đồng bộ: future complete không đồng nghĩa job đã xong

Mô hình:

```text
WebSocket.Builder
   |
   | buildAsync(uri, listener)
   v
CompletableFuture<WebSocket>
   |
   +-- normal completion -> WebSocket ready
   |         |
   |         +-- getSubprotocol()
   |         +-- sendText(...), sendBinary(...)
   |         +-- Listener receives messages
   |         +-- sendClose(...) / abort()
   |
   +-- exceptional completion
             |
             +-- WebSocketHandshakeException
             +-- HttpTimeoutException
             +-- IOException / network/TLS issues
             +-- illegal arguments / policy/security failure
```

Trong Java:

```java
// Snippet minh họa: future đã có.
future.whenComplete((ws, error) -> {
    if (error != null) {
        // Phân loại lỗi handshake/TLS/timeout và cleanup.
        logFailure(error);
        return;
    }
    // Chỉ dùng ws sau khi tương thích subprotocol đã kiểm tra.
    onConnected(ws);
});
```

Đây không phải class chạy độc lập: `logFailure` và `onConnected` là functions của app. Khi dùng `get()`, exception bất đồng bộ thường được bọc trong `ExecutionException`; `join()` thường bọc trong `CompletionException`. Cần **unwrap nguyên nhân** để phân loại `WebSocketHandshakeException` và lấy status.

Nối thêm các stages:

```java
// Snippet: connectFuture đã có.
connectFuture.thenCompose(ws -> ws.sendText("hello", true))
             .thenCompose(ws -> ws.sendClose(
                     WebSocket.NORMAL_CLOSURE, ""))
             .exceptionally(error -> {
                 handleAsyncError(error);
                 return null;
             });
```

Không nên send/close ngay khi chưa xác nhận subprotocol và auth requirements của ứng dụng. Trong pipeline thật, message tới peer có thể tạo side effect; **future send completed** chứng minh send operation của client đã hoàn thành, **không** phải business ACK từ server.

## 11. Listener nhận gì và xử lý thứ tự callback ra sao?

`WebSocket.Listener` có các callbacks:

| Callback | Mục đích |
| --- | --- |
| `onOpen(WebSocket)` | Client đã connected; thường gọi `request(1)` hoặc `request(n)` |
| `onText(WebSocket, CharSequence, boolean last)` | Nhận một **phần** của text message |
| `onBinary(WebSocket, ByteBuffer, boolean last)` | Nhận một **phần** của binary message |
| `onPing(WebSocket, ByteBuffer)` | Nhận Ping control frame |
| `onPong(WebSocket, ByteBuffer)` | Nhận Pong control frame |
| `onClose(WebSocket, int code, String reason)` | Peer gửi Close, input đóng; callback cuối |
| `onError(WebSocket, Throwable)` | Lỗi trong WebSocket, callback cuối |

Với **một WebSocket**, các listener callbacks được gọi theo thứ tự và không reentrant; đối với nhiều WebSocket dùng chung một listener, callbacks **có thể xảy ra đồng thời**, vì vậy phải bảo vệ state nếu chia sẻ.

Điểm cực kỳ quan trọng: mỗi WebSocket mới bắt đầu với **receive invocation counter = 0**. Chỉ khi `webSocket.request(n)` tăng demand thì implementation mới có thể gọi receive methods như `onText/onBinary/onPing/onPong/onClose`. `onOpen` và `onError` không tiêu demand như receive methods.

**Nếu override `onOpen` mà không gọi `request`, ứng dụng có thể kết nối thành công nhưng không bao giờ thấy message callback.** Default `onOpen` của Java 17 có gọi `request(1)`; khi override phải tự giữ ý thức đó.

## 12. `webSocket.request(n)` đếm callbacks, không đếm messages hay bytes

Theo Java 17, `request(n)` tăng số lần **receive callback** được phép gọi thêm. Nó **không phải** request đọc n bytes, n WebSocket messages hay n TCP packets.

```text
onOpen -> request(1)
                |
                v
onText("Xin ", last=false)    [1 callback]
        |
        +-> request(1)
                |
                v
onText("chào", last=true)     [2nd callback]
        |
        +-> ghép thành một message: "Xin chào"
        +-> request(1) cho event tiếp theo
```

Một text message có thể được trả thành **nhiều lần `onText`**; `last` cho biết **phần cuối của message**. Một callback cũng có thể mang một message hoàn chỉnh.

`WebSocket.Listener` phải trả `CompletionStage<?>` cho `onText/onBinary/onPing/onPong/onClose`. Completion stage cho biết **khi nào implementation được phép thu hồi dữ liệu CharSequence/ByteBuffer**; nó không giống receive demand counter. Nếu callback trả `null`, implementation xem như hoàn tất ngay; khi có xử lý async, không giữ tham chiếu vào buffer mutable sau khi stage đã complete. Sao chép có giới hạn hoặc giữ stage chưa complete theo hợp đồng.

Đừng thực hiện blocking database calls không có hạn mức ngay trong `onText`; listener threads có thể trở thành nút nghẽn. Nếu chuyển sang worker, cần bounded queue, ownership của payload và chính sách khi tăng `request`.

## 13. Fragmentation: một message có thể gồm nhiều callback

WebSocket có khái niệm **message** và **frame**. Message có thể bị phân mảnh thành nhiều frames, và API Java có thể phân phối các phần tương ứng qua nhiều lần `onText` hoặc `onBinary`.

```java
// Snippet minh họa ở trong một WebSocket.Listener riêng mỗi socket.
private final StringBuilder parts = new StringBuilder();

@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {
    parts.append(data);
    if (last) {
        String wholeMessage = parts.toString();
        parts.setLength(0);
        handleMessage(wholeMessage);
    }
    socket.request(1);
    return CompletableFuture.completedFuture(null);
}
```

Đây là snippet trong listener, **chưa độc lập**: cần class bao ngoài, imports và định nghĩa `handleMessage`. Dù có thể đọc `StringBuilder` nội bộ từ callbacks được serialize theo socket, nó không phù hợp để dùng chung giữa nhiều sockets nếu không đồng bộ.

**Bảo vệ memory:** đừng append không giới hạn. Nếu peer gửi message 500 MiB mà không có `last` sớm, `StringBuilder` có thể OOM. Đặt `maxMessageChars/maxBinaryBytes`; vượt hạn thì đóng socket theo policy (ví dụ close code tương ứng khi hợp lệ) và không còn queue nhận vô hạn.

Với binary, `ByteBuffer` chỉ chứa bytes từ `position` tới `limit`; dùng `remaining()`. UTF-8 text được `onText` cung cấp dưới dạng `CharSequence` UTF-16 hợp lệ theo API, không tự cắt byte UTF-8 như raw socket. Nhưng **đừng giả định callback = một JSON object**; chỉ parse sau khi `last==true` hoặc có framing của subprotocol.

## 14. Gửi message cũng bất đồng bộ: sendText và sequencing

Sau kết nối:

```java
CompletableFuture<WebSocket> a = ws.sendText("Hello", true);
CompletableFuture<WebSocket> b = a.thenCompose(
        socket -> socket.sendText(" world", true));
```

Đoạn này là snippet minh họa. Ở ví dụ trên, `true` mỗi lần nghĩa **một text message hoàn chỉnh**, nên server sẽ nhận hai messages: `"Hello"` và `" world"`, không phải một message `"Hello world"`. Nếu muốn một message **chia thành nhiều phần**, dùng:

```java
ws.sendText("Hello ", false)
  .thenCompose(socket -> socket.sendText("world", true));
```

**Quy tắc `last`:**

- `last=false`: phần hiện tại **chưa kết thúc** text/binary message.
- `last=true`: kết thúc message.
- Nếu nhiều thread gửi đồng thời text/binary khi một send tương tự đang pending, future có thể thất bại `IllegalStateException`. **Xếp hàng gửi theo thứ tự và serialize** bằng chuỗi `thenCompose` hoặc một outgoing queue có giới hạn.
- `sendText` trả `CompletableFuture<WebSocket>` khi send operation hoàn tất ở phía client, không báo server đã parse/commit message.
- `CharSequence` không được sửa trong lúc send future còn pending. Với `sendBinary(ByteBuffer, last)`, không chạm vào buffer cho tới khi future complete theo hợp đồng Java 17.

Ví dụ thứ nhất gửi `"ping"` bằng `sendText("ping", true)` và server trả text message `ACK:ping` **tách thành hai frames**; listener ghép lại an toàn dù JDK phân phối số callbacks khác nhau.

## 15. Ví dụ Java 17+ số 1: handshake thành công, chọn subprotocol và nhận text

Tệp **`WebSocketBuilderLoopback.java`** là chương trình đầy đủ, không cần thư viện bên ngoài. Nó dùng `ServerSocket` **chỉ bind IPv4 loopback** làm một WebSocket test server rất nhỏ. Server thực hiện HTTP/1.1 Upgrade, tính `Sec-WebSocket-Accept` đúng RFC 6455, chọn `chat.v2`, đọc frame text `ping` đã được client mask, gửi lại một text message phân mảnh thành `ACK:` và `ping`, rồi phản hồi Close status 1000.

Client sử dụng đúng các API cần học:

- `HttpClient.newHttpClient().newWebSocketBuilder()`.
- `header("X-Demo", "present")`.
- `subprotocols("chat.v2", "chat.v1")`.
- `connectTimeout(Duration.ofSeconds(5))`.
- `buildAsync(uri, listener)` trả `CompletableFuture<WebSocket>`.
- `getSubprotocol()` kiểm tra server chọn `chat.v2`.
- `WebSocket.Listener.onOpen/onText/onClose/onError` và `request(1)`.
- `sendText(...).get(...)` và `sendClose(...)` với deadline.

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WebSocketBuilderLoopback {
    record ServerResult(boolean offered, boolean customHeader,
                        boolean closeSeen) {}

    static class Listener implements WebSocket.Listener {
        final StringBuilder message = new StringBuilder();
        final CompletableFuture<String> received = new CompletableFuture<>();
        final CompletableFuture<Boolean> closed = new CompletableFuture<>();

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onText(WebSocket socket,
                                         CharSequence part, boolean last) {
            message.append(part);
            socket.request(1);
            if (last) {
                received.complete(message.toString());
            }
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(WebSocket socket,
                                          int code, String reason) {
            closed.complete(code == WebSocket.NORMAL_CLOSURE);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            received.completeExceptionally(error);
            closed.completeExceptionally(error);
        }
    }

    static String headers(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] suffix = new byte[]{13, 10, 13, 10};
        while (b.size() < 8192) {
            int next = in.read();
            if (next == -1) {
                throw new IOException("EOF before HTTP headers");
            }
            b.write(next);
            byte[] data = b.toByteArray();
            if (data.length >= 4) {
                boolean end = true;
                for (int i = 0; i < 4; i++) {
                    end &= data[data.length - 4 + i] == suffix[i];
                }
                if (end) {
                    return new String(data, StandardCharsets.ISO_8859_1);
                }
            }
        }
        throw new IOException("Oversized headers");
    }

    static String headerValue(String request, String field) {
        for (String line : request.split("\r\n")) {
            int colon = line.indexOf(':');
            if (colon > 0 &&
                    line.substring(0, colon).equalsIgnoreCase(field)) {
                return line.substring(colon + 1).trim();
            }
        }
        return "";
    }

    static void sendFrame(OutputStream out, int opcode,
                          boolean last, byte[] payload) throws IOException {
        if (payload.length > 125) {
            throw new IOException("Demo only supports small frames");
        }
        out.write((last ? 128 : 0) | opcode);
        out.write(payload.length); // Server frames are not masked.
        out.write(payload);
        out.flush();
    }

    record Frame(int opcode, byte[] payload) {}
    static Frame readClientFrame(InputStream in) throws IOException {
        int first = in.read();
        int second = in.read();
        if (first < 0 || second < 0 || (second & 128) == 0) {
            throw new IOException("Missing masked client frame");
        }
        int length = second & 127;
        if (length > 125) {
            throw new IOException("Frame too large for this demo");
        }
        byte[] mask = in.readNBytes(4);
        byte[] data = in.readNBytes(length);
        if (mask.length != 4 || data.length != length) {
            throw new IOException("Incomplete frame");
        }
        for (int i = 0; i < data.length; i++) {
            data[i] ^= mask[i & 3];
        }
        return new Frame(first & 15, data);
    }

    static ServerResult serve(ServerSocket listener) throws Exception {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(8000);
            InputStream in = peer.getInputStream();
            OutputStream out = peer.getOutputStream();
            String request = headers(in);
            String key = headerValue(request, "Sec-WebSocket-Key");
            if (key.isEmpty()) {
                throw new IOException("No WebSocket key");
            }
            String offered = headerValue(request, "Sec-WebSocket-Protocol");
            boolean hasOffer = offered.contains("chat.v2")
                    && offered.contains("chat.v1");
            boolean hasHeader = "present".equals(
                    headerValue(request, "X-Demo"));
            byte[] digest = MessageDigest.getInstance("SHA-1").digest(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                            .getBytes(StandardCharsets.US_ASCII));
            String accept = Base64.getEncoder().encodeToString(digest);
            String response = "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept + "\r\n"
                    + "Sec-WebSocket-Protocol: chat.v2\r\n\r\n";
            out.write(response.getBytes(StandardCharsets.ISO_8859_1));
            out.flush();

            Frame sent = readClientFrame(in);
            if (sent.opcode() != 1 ||
                    !"ping".equals(new String(sent.payload(),
                            StandardCharsets.UTF_8))) {
                throw new IOException("Unexpected request message");
            }
            sendFrame(out, 1, false,
                    "ACK:".getBytes(StandardCharsets.UTF_8));
            sendFrame(out, 0, true,
                    "ping".getBytes(StandardCharsets.UTF_8));

            Frame close = readClientFrame(in);
            if (close.opcode() != 8) {
                throw new IOException("Expected close");
            }
            sendFrame(out, 8, true,
                    new byte[]{3, (byte) 232}); // Status 1000.
            return new ServerResult(hasOffer, hasHeader, true);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        try (ServerSocket server = new ServerSocket(0, 1, local)) {
            server.setSoTimeout(8000);
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<ServerResult> handled =
                        worker.submit(() -> serve(server));
                Listener receiving = new Listener();
                URI target = URI.create("ws://127.0.0.1:"
                        + server.getLocalPort() + "/chat");
                WebSocket socket = HttpClient.newHttpClient()
                        .newWebSocketBuilder()
                        .header("X-Demo", "present")
                        .subprotocols("chat.v2", "chat.v1")
                        .connectTimeout(Duration.ofSeconds(5))
                        .buildAsync(target, receiving)
                        .get(8, TimeUnit.SECONDS);

                socket.sendText("ping", true).get(8, TimeUnit.SECONDS);
                String text = receiving.received.get(8, TimeUnit.SECONDS);
                socket.sendClose(WebSocket.NORMAL_CLOSURE, "")
                        .get(8, TimeUnit.SECONDS);
                boolean closed = receiving.closed.get(8, TimeUnit.SECONDS);
                ServerResult result = handled.get(8, TimeUnit.SECONDS);

                System.out.println("Selected subprotocol: "
                        + socket.getSubprotocol());
                System.out.println("Received: " + text);
                System.out.println("Close status 1000: " + closed);
                System.out.println("Server saw both offers: "
                        + result.offered());
                System.out.println("Server saw custom header: "
                        + result.customHeader());
            } finally {
                worker.shutdownNow();
            }
        }
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```sh
javac -encoding UTF-8 WebSocketBuilderLoopback.java
java WebSocketBuilderLoopback
```

Stdout đã kiểm thử:

```text
Selected subprotocol: chat.v2
Received: ACK:ping
Close status 1000: true
Server saw both offers: true
Server saw custom header: true
```

**Giải thích vì sao không phải fake test:**

1. Server mở **socket TCP thực trên 127.0.0.1**, JDK client thực sự gửi HTTP handshake và thực sự chờ `101 Switching Protocols` với `Sec-WebSocket-Accept`.
2. Server đọc hai header `Sec-WebSocket-Protocol` và `X-Demo`. Hai dòng `Server saw ... true` cho thấy builder đã đưa **đề xuất subprotocol và header bổ sung** vào handshake.
3. Server quyết định `Sec-WebSocket-Protocol: chat.v2`. Chỉ **sau buildAsync thành công**, client mới đọc `socket.getSubprotocol()` và in giá trị đã được **server chấp nhận**.
4. WebSocket client **mask** frames gửi cho server. Server demo đọc bốn mask bytes và XOR payload để lấy `ping`. Server gửi frames không mask theo quy tắc RFC 6455.
5. Server trả message bằng **frame text đầu chưa FIN**, tiếp theo là **continuation FIN**. `Listener.onText` ghép mọi phần đến `last=true` để tạo `ACK:ping`. Dù JDK hợp nhất hoặc chia callbacks theo cách khác, logic vẫn đúng.
6. `request(1)` trong `onOpen` và sau mỗi `onText` bảo đảm có demand cho callback tiếp theo, kể cả Close.
7. `sendClose(WebSocket.NORMAL_CLOSURE,"")` gửi close code 1000; server đáp close, listener nhận `onClose`. Không nhầm `sendClose` với Java `AutoCloseable.close()`.

**Phạm vi demo:** server chỉ hiểu payload nhỏ (tối đa 125 bytes), một client, một text message và một Close; không kiểm tra mọi RFC frame size/fragmentation/control semantics, không có TLS, auth, concurrent clients hay production backpressure. **Không dùng class `serve` làm WebSocket server Internet**. SHA-1 ở demo chỉ phục vụ công thức handshake của RFC, không phải thuật toán khuyến nghị để lưu mật khẩu.

## 16. Ví dụ Java 17+ số 2: handshake bị server từ chối HTTP 403

`buildAsync` không luôn thành công. Nếu endpoint từ chối opening handshake, default `HttpClient` có thể hoàn tất future exceptionally với **`WebSocketHandshakeException`**, cho phép truy cập **`HttpResponse<?>`** của handshake thất bại.

Tệp **`WebSocketHandshakeRejected.java`** dựng một server TCP loopback đọc HTTP handshake rồi trả `HTTP/1.1 403 Forbidden` thay vì `101`. Client gọi `buildAsync` và dùng `Future.get`, bắt `ExecutionException`, kiểm tra root cause là `WebSocketHandshakeException` và in status:

```java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.net.http.WebSocketHandshakeException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WebSocketHandshakeRejected {
    static void reject(ServerSocket server) throws Exception {
        try (Socket peer = server.accept()) {
            peer.setSoTimeout(8000);
            InputStream in = peer.getInputStream();
            ByteArrayOutputStream headers = new ByteArrayOutputStream();
            while (headers.size() < 8192) {
                int current = in.read();
                if (current == -1) {
                    throw new IllegalStateException("No HTTP request");
                }
                headers.write(current);
                String value = headers.toString(
                        StandardCharsets.ISO_8859_1);
                if (value.endsWith("\r\n\r\n")) {
                    break;
                }
            }
            OutputStream out = peer.getOutputStream();
            out.write(("HTTP/1.1 403 Forbidden\r\n"
                    + "Content-Length: 0\r\n"
                    + "Connection: close\r\n\r\n")
                            .getBytes(StandardCharsets.US_ASCII));
            out.flush();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        try (ServerSocket server = new ServerSocket(0, 1, local)) {
            server.setSoTimeout(8000);
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<?> served = worker.submit(() -> {
                    reject(server);
                    return null;
                });
                URI endpoint = URI.create("ws://127.0.0.1:"
                        + server.getLocalPort() + "/denied");
                CompletableFuture<WebSocket> open =
                        HttpClient.newHttpClient()
                                .newWebSocketBuilder()
                                .subprotocols("chat.v1")
                                .connectTimeout(Duration.ofSeconds(5))
                                .buildAsync(endpoint,
                                        new WebSocket.Listener() {});
                boolean rejected = false;
                int status = -1;
                try {
                    open.get(8, TimeUnit.SECONDS);
                } catch (ExecutionException error) {
                    if (error.getCause()
                            instanceof WebSocketHandshakeException handshake) {
                        rejected = true;
                        status = handshake.getResponse().statusCode();
                    } else {
                        throw error;
                    }
                }
                served.get(8, TimeUnit.SECONDS);
                System.out.println("Handshake rejected: " + rejected);
                System.out.println("HTTP status: " + status);
                System.out.println("WebSocket available: "
                        + (open.isDone() && !open.isCompletedExceptionally()));
            } finally {
                worker.shutdownNow();
            }
        }
    }
}
```

Biên dịch/chạy:

```sh
javac -encoding UTF-8 WebSocketHandshakeRejected.java
java WebSocketHandshakeRejected
```

Stdout đã kiểm thử:

```text
Handshake rejected: true
HTTP status: 403
WebSocket available: false
```

`WebSocketHandshakeException.getResponse().statusCode()` giúp phân biệt server trả 403, 401, 404, redirect hay một HTTP status không chấp nhận làm upgrade. Nhưng **đừng log đầy đủ headers/body nhạy cảm** chỉ để debug lỗi auth. Một số lỗi xảy ra **trước khi HTTP response tồn tại**, như DNS/TCP/TLS failure, khi đó nguyên nhân là `IOException`/TLS exception/timeout chứ không nhất thiết `WebSocketHandshakeException`.

Không retry mù quáng mọi 401/403: cần sửa credential/permissions/Origin/middleware trước. Đừng coi 403 chỉ là network outage. Trong demo, code xác minh future không cung cấp socket sau khi handshake bị từ chối.

## 17. Tại sao Java client API không có WebSocket server dựng sẵn?

`java.net.http.WebSocket` được JDK 17 định nghĩa là **WebSocket Client**; JDK `HttpClient.newWebSocketBuilder()` chỉ tạo **client builder**. `jdk.httpserver.HttpServer` hỗ trợ HTTP server cho ví dụ HTTP, nhưng không phải một WebSocket server framework tích hợp được bảo đảm xử lý đầy đủ upgrade/framing.

Vì vậy, để có ví dụ **tự chạy không cần thư viện ngoài**, demo dùng `ServerSocket` và thực hiện tối thiểu RFC 6455 handshake, masking và vài frames. Lựa chọn này có hai giới hạn:

- Không xử lý mọi loại frame lớn/fragmentation, rate-limit, invalid UTF-8, ping/pong, compression, authentication, concurrent sessions, TLS hay graceful shutdown phức tạp.
- Demo phù hợp làm **test fixture giáo dục về builder và subprotocol**, không phải mẫu triển khai server production.

Trong ứng dụng thật, dùng WebSocket server/framework đã kiểm chứng, hỗ trợ RFC 6455, TLS, admission controls, origin validation, client authentication và quotas. Việc Java API client hỗ trợ `WebSocket.Builder` **không** có nghĩa nó được dùng để accept server-side connections.

## 18. Xử lý lỗi và trạng thái kết nối rõ ràng

Một WebSocket client cần xử lý ít nhất ba nhóm lỗi:

| Giai đoạn | Ví dụ lỗi | Cách xử lý |
| --- | --- | --- |
| **Trước upgrade** | DNS/TCP fail, TLS cert mismatch, timeout | Cấu hình endpoint/trust, retry có giới hạn nếu policy cho phép |
| **Trong handshake** | 401/403/404, 426/invalid 101, subprotocol không hợp lệ | Kiểm tra `WebSocketHandshakeException` hoặc selected protocol; sửa auth/routing |
| **Sau khi connected** | Peer close, I/O error, server restart, heartbeat timeout, payload overflow | Xử lý `onClose/onError`, cleanup, đánh dấu session state, reconnect/replay có kiểm soát |

`buildAsync` hoàn tất bình thường **chỉ xác nhận WebSocket opening handshake thành công**. Nó không bảo đảm sẽ tồn tại mãi; server có thể gửi Close ngay sau đó hoặc mạng có thể mất.

Khi `onError` được gọi, đây là callback cuối cho socket đó theo JDK API. Không tạo một vòng gọi `ws.sendText` trực tiếp trong `onError`. Ghi nhận kết nối đã lỗi, dọn các pending sends và mở kết nối mới nếu policy quyết định.

Khi `onClose` được gọi, input đã đóng; callback cuối này chứa status code và reason. Không mặc định mọi Close đều là 1000: server có thể gửi code khác, và network failure có thể xuất hiện qua `onError` mà không có close handshake hoàn chỉnh.

## 19. `sendClose` và `abort` không giống nhau

`WebSocket` trong Java 17 có hai chiều **input** và **output** độc lập:

- `sendClose(statusCode, reason)` **bắt đầu đóng output một cách có trật tự** bằng Close message. Method trả `CompletableFuture<WebSocket>`, nghĩa là công đoạn gửi Close cũng bất đồng bộ. **Nó không lập tức đóng input**; chờ peer Close hoặc error/abort.
- `abort()` đóng input và output **đột ngột**, không thực hiện close handshake thông thường. Dùng khi quá thời hạn đóng, gặp lỗi nghiêm trọng hoặc cần dừng khẩn cấp.
- `isOutputClosed()` và `isInputClosed()` cho biết trạng thái của hai chiều. Khi đã closed, chúng không tự mở lại; reconnect tạo một instance `WebSocket` mới.
- `WebSocket.NORMAL_CLOSURE` là status code **1000**. `sendClose` cũng có kiểm tra mã close hợp lệ và reason UTF-8 tối đa 123 bytes theo Java 17.
- Java 17 `WebSocket` **không phải `AutoCloseable`**; không viết `try (WebSocket ws = ...)` rồi kỳ vọng một `close()` giống TCP Socket.

Một ứng dụng production nên có **deadline cho graceful close**: gửi Close, đợi `onClose` trong khoảng hợp lý, sau đó `abort()` nếu peer không đáp. Đừng đợi future/close callback không timeout trong tác vụ shutdown quan trọng.

## 20. Ping, Pong, heartbeat và đo sức khỏe

WebSocket có control frames `Ping` và `Pong`. API Java 17:

```java
// Snippet minh họa: ws là WebSocket đang connected.
ByteBuffer probe = ByteBuffer.wrap(new byte[]{1, 2, 3});
ws.sendPing(probe).whenComplete((ignored, error) -> {
    if (error != null) {
        reportTransportFailure(error);
    }
});
```

Snippet chưa chạy độc lập: thiếu class/import và `reportTransportFailure`. Điều quan trọng:

- `sendPing` hoàn tất khi **ping send operation** thành công ở client, **không** phải khi server đã đáp Pong.
- Java WebSocket implementation **tự gửi Pong đáp lại Ping nhận được** theo protocol, vì vậy app thường không phải `sendPong` thủ công khi `onPing` được gọi.
- `sendPing/sendPong` payload tối đa **125 bytes**.
- `onPong` có thể dùng để theo dõi liveness/RTT bằng ID/timestamp do app quản lý, nhưng phải giữ policy timeout, false positives và clock monotonic phù hợp.
- `onPing/onPong` cũng là **receive callbacks** chịu `request(n)` demand; đừng để demand cạn khiến logic heartbeat không tiến triển đúng như thiết kế.
- `connectTimeout` không thay heartbeat/idle timeout của một socket đã mở hàng giờ.

Nếu server có idle policy, hãy đồng thuận tần suất heartbeat để không flood server. Tự triển khai ping mỗi vài milliseconds để “giữ sống socket” có thể gây quá tải.

## 21. Auth, Origin, validation và subprotocol trong hệ thống thật

**Subprotocol negotiation không phải authorization.** Một server trả `chat.v2` chỉ khẳng định chấp nhận **format giao thức**; không có nghĩa người gọi được phép tham gia mọi room hoặc gửi mọi command.

Cần phân tầng:

1. **Kết nối:** dùng `wss://`, TLS hợp lệ, hạn chế origin/host và kiểm tra reverse proxy upgrade.
2. **Danh tính:** xác thực session/cookie/bearer token trong handshake hoặc một application authentication step có timeouts; bảo vệ credentials và rotation.
3. **Subprotocol:** server chỉ chọn một trong các giá trị client đề xuất; client xác minh selected token tương thích message schema.
4. **Authorization message-level:** user A không được phép subscribe/publish vào room/tenant B chỉ nhờ kết nối thành công.
5. **Payload validation:** validate text/binary format, max message size, JSON schema, operation IDs, rate limits và backpressure.
6. **Lifecycle:** xử lý token hết hạn, resume/reconnect, audit và cleanup subscriptions khi socket close.

Server phải xét `Origin` khi browser clients dùng cookie-based sessions để giảm cross-site WebSocket hijacking theo threat model; nhưng **Origin một mình không phải authentication**. Non-browser clients có thể gửi header tùy ý. Tương tự, JWT/Authorization trong handshake không miễn cho việc verify resource quyền sau đó.

Không cố “chữa” lỗi TLS bằng tắt hostname validation/trust-all. Nếu client dùng `wss://` tới private CA, thiết lập truststore/`SSLContext` rõ và kiểm tra server certificate đúng hostname.

## 22. Backpressure, multi-client và reconnect thực tế

WebSocket là kết nối dài hạn; không thể dùng mỗi connection tương đương một fire-and-forget queue vô hạn.

**Outbound:**

- `sendText/sendBinary` trả futures; giới hạn số messages và tổng byte đang pending. Nếu producer nhanh hơn socket có thể gửi, queue sẽ tăng.
- Các lệnh send text/binary đồng thời có thể xung đột với một send đang pending. Xếp hàng và serialize để giữ thứ tự ứng dụng.
- Không dùng completion của `sendText` làm **ACK nghiệp vụ**. Khi cần at-least-once, mỗi message có `messageId` và server ACK; client có durable queue/retry window phù hợp.
- Không retry vô hạn khi server báo không chấp nhận subprotocol/auth; exponential backoff + jitter và circuit breaker cho network failures.

**Inbound:**

- `request(n)` là credit cho **callback invocation**, không phải memory cap tuyệt đối. Một callback có thể có fragment lớn; kiểm soát message sizes.
- Đừng request thêm khi downstream không còn capacity nếu bạn dùng bounded queue; nhưng cũng không được quên request mãi, khiến socket có data mà listener không tiến triển.
- Dữ liệu trong `CharSequence/ByteBuffer` chỉ có lifecycle do completion stage callback quản lý; copy khi chuyển sang worker chạy sau stage completion.
- Một listener được gắn vào **nhiều sockets** có thể được gọi đồng thời giữa các sockets; `StringBuilder` không thread-safe cho shared state như vậy.

**Reconnect:**

- Khi socket fail, xây **WebSocket.Builder mới** và listener/session state mới; không sửa builder cũ đồng thời nhiều threads.
- Dùng operation/sequence ID, resume token hoặc snapshot endpoint nếu server hỗ trợ; không tin rằng reconnect tự phát lại toàn bộ messages đã mất.
- Nếu message có side effect, retry dựa trên idempotency policy chứ không “sendText again” mù quáng.

## 23. Hai mươi lỗi thường gặp và cách sửa

1. **Gọi `new WebSocket.Builder()`:** `Builder` là interface; lấy từ `HttpClient.newWebSocketBuilder()`.
2. **Dùng cùng builder mutable từ nhiều threads:** Builder không thread-safe; tạo riêng cho kết nối.
3. **Nghĩ `buildAsync` lập tức trả WebSocket:** nó trả `CompletableFuture<WebSocket>`.
4. **Coi `subprotocols("v2","v1")` là ép server dùng v2:** client đề xuất thứ tự ưu tiên, server chọn.
5. **Chỉ kiểm tra buildAsync success, bỏ `getSubprotocol()`:** có thể không có/khác protocol app hỗ trợ.
6. **Đưa bearer token vào tên subprotocol:** sai phạm vi, rủi ro lộ secret và syntax.
7. **Tự thêm `Sec-WebSocket-Key` qua builder.header:** WebSocket protocol headers do JDK quản lý, API cấm.
8. **Nhầm `connectTimeout` với idle/read timeout sau kết nối:** cần heartbeat/deadline riêng.
9. **Không gọi `request(n)` trong custom `onOpen`:** listener có thể không nhận text/binary/close.
10. **Hiểu `request(1)` là một complete message:** nó cấp một callback, message có thể fragmented.
11. **Parse JSON ngay khi `onText` được gọi dù `last=false`:** có thể chỉ nhận fragment.
12. **Bỏ qua `onError`, chỉ chờ `onClose`:** network error không bảo đảm close handshake.
13. **Trả CompletionStage đã complete rồi giữ CharSequence/ByteBuffer để dùng sau:** có thể dùng dữ liệu sau lifetime hợp lệ; copy hoặc giữ stage đúng contract.
14. **Gửi nhiều text/binary không serialize khi pending:** có thể gây `IllegalStateException` và sai ordering.
15. **Coi sendText future complete là server đã xử lý message:** không có ACK nghiệp vụ.
16. **Chỉ gọi sendClose rồi cho rằng input đã đóng:** sendClose đóng output, input cần peer close/error/abort.
17. **Dùng `abort` như graceful shutdown thông thường:** abort đóng ngay, có thể làm mất messages đang gửi.
18. **Coi `ws://` là mã hóa vì WebSocket dùng handshake HTTP:** không có TLS, cần `wss://` khi có dữ liệu nhạy cảm.
19. **Tưởng Java 17 `java.net.http` có server WebSocket production:** package cung cấp client, không phải full server stack.
20. **Retry handshake 401/403 vô hạn:** cần sửa token, quyền, proxy/origin/subprotocol, không chỉ backoff.

## 24. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `buildAsync` future báo `WebSocketHandshakeException`, HTTP 403 | Token/quyền/origin/routing từ chối | Xem `getResponse().statusCode()`, kiểm tra server policy mà không log secret |
| HTTP 404 trong handshake | Sai URI path/reverse proxy upgrade route | Kiểm tra `ws(s)://host/path` và routing |
| `HttpTimeoutException` lúc connect | Handshake/transport không hoàn tất trong timeout | Kiểm tra DNS/TCP/TLS/proxy; không hiểu là idle timeout |
| TLS `SSLHandshakeException` | WSS truststore, hostname, cert chain | Sửa TLS trust/identity, không trust-all |
| Kết nối thành công nhưng không có `onText` | Override `onOpen` mà quên `request(1)` | Bổ sung receive demand, kiểm tra server có gửi không |
| `getSubprotocol()` rỗng | Server không negotiated subprotocol | Xem app có bắt buộc subprotocol hay không |
| `getSubprotocol()` là v1, app gửi payload v2 | Không kiểm tra negotiated version | Branch đúng schema hoặc đóng kết nối |
| `sendText` báo `IllegalStateException` | Pending send hoặc trạng thái message không hợp lệ | Serialize sends và xử lý `last` đúng |
| Chỉ thấy một phần text | `onText(...,last=false)` là fragment | Ghép fragments đến `last=true` có memory bound |
| `onError` sau mạng chập chờn | I/O/remote disconnect | Cleanup, reconnect có backoff và replay protocol |
| Socket không thoát khi shutdown | Chưa hoàn tất close handshake hoặc không deadline | `sendClose` + đợi onClose + `abort` fallback |
| CPU/RAM tăng khi stream realtime | Queue vô hạn, message quá lớn, listener xử lý chậm | Bounded queues/demand, payload limits, metrics |

Không dựa vào một tên exception để tự suy đoán server đã xử lý message nghiệp vụ. Có thể cần logs hai đầu, operation IDs và thông tin subprotocol/HTTP status có kiểm soát.

## 25. Câu hỏi tự kiểm tra

**1.** `WebSocket.Builder` có thread-safe không? **Không.** Intermediate methods thay mutable builder; tạo builder riêng hoặc đồng bộ bên ngoài.

**2.** `buildAsync` trả về gì? **`CompletableFuture<WebSocket>`**, complete normal khi opening handshake thành công.

**3.** Client đề xuất `chat.v2` rồi `chat.v1`, server chọn `chat.v1` có hợp lệ không? **Có**, nếu token nằm trong danh sách offered và policy/implementation cho phép; client phải chọn schema v1.

**4.** `getSubprotocol()` trả `""` có chứng minh handshake thất bại không? **Không.** Có thể handshake thành công nhưng không negotiated subprotocol.

**5.** `request(1)` cho phép đọc một WebSocket message hoàn chỉnh? **Không**, nó cấp một receive callback invocation; text message có thể fragmented.

**6.** `onText(data,false)` trả một đoạn JSON chưa đủ. Có nên parse ngay không? **Không** nếu format giả định một JSON document/message; ghép đến `last=true`.

**7.** `onOpen` override nhưng không gọi `request`, điều gì có thể xảy ra? **Kết nối có thể thành công nhưng không có receive callbacks**, vì demand ban đầu bằng 0.

**8.** Sau khi `sendText` future complete, có thể chắc server đã ghi vào database? **Không.** Cần ACK nghiệp vụ, operation ID và server semantics.

**9.** `sendClose` có đóng input ngay không? **Không.** Nó khởi động đóng output; input đợi peer close/error hoặc `abort`.

**10.** Tại sao demo dùng `ServerSocket` tự xử lý frames? **Vì JDK `java.net.http.WebSocket` cung cấp client API, không phải sẵn một WebSocket server production; server demo chỉ là test fixture RFC 6455 tối giản.**

**11.** Khi `buildAsync` thất bại do HTTP 403, có thể xem HTTP status ở đâu? **`WebSocketHandshakeException.getResponse().statusCode()`**.

**12.** `wss://` và `subprotocols("chat.v2")` có cùng trách nhiệm không? **Không.** WSS bảo vệ transport bằng TLS; subprotocol xác định message application semantics.

## 26. Checklist triển khai và kết luận

Khi review một Java 17 WebSocket client:

1. **Chọn đúng URI:** `ws://` cho loopback lab, `wss://` cho dữ liệu nhạy cảm; TLS/hostname trust đúng.
2. **Dùng HttpClient có policy phù hợp:** proxy, SSLContext, executor; không lẫn tenant authentication.
3. **Tạo WebSocket.Builder riêng cho connection:** không chia sẻ mutable builder đồng thời.
4. **Chỉ thêm headers được phép:** không tự set WebSocket protocol headers; bảo vệ token/cookies.
5. **Đề xuất subprotocols theo thứ tự ưu tiên:** chỉ đề xuất format app thực sự hỗ trợ.
6. **Đặt connectTimeout hữu hạn** và deadline chờ future phù hợp; không nhầm với liveness timeout sau connect.
7. **Xử lý cả normal/exceptional buildAsync:** phân loại handshake HTTP status, TLS, timeout và lỗi cấu hình.
8. **Kiểm tra `getSubprotocol()`:** không gửi payload theo schema sai khi server chọn khác/missing.
9. **Listener có onOpen request(n) và onError/onClose cleanup:** tránh kênh treo vì hết demand.
10. **Xử lý fragments theo last:** không nhầm một callback với một business message; giới hạn kích thước.
11. **Serialize sends và kiểm soát outbound/inbound queues:** không để pending messages tăng vô hạn.
12. **Quản lý CompletionStage lifetime của received data:** không giữ buffer sau callback completion khi chưa copy.
13. **Có heartbeat, idle deadline, close handshake và abort fallback:** không để sockets chết ngầm.
14. **Có reconnect policy và replay/idempotency nếu cần:** WebSocket transport không đảm bảo persistence/exactly-once.
15. **Có message-level validation/authorization, logs/metrics:** handshake và subprotocol không thay quyền nghiệp vụ.
16. **Test positive và negative handshake:** subprotocol selected, absent, HTTP 401/403, timeout, malformed frame, server close và reconnect.

**Kết luận:** `WebSocket.Builder` cấu hình **một lần bắt tay** và `buildAsync` trả kết quả **bất đồng bộ**. `subprotocols` chỉ đưa ra các lựa chọn theo mức ưu tiên; **`getSubprotocol()`** mới xác nhận lựa chọn cuối. Sau khi connected, mọi việc nhận/gửi/đóng vẫn tuân theo các futures, listener callbacks, `request(n)` demand và quy tắc lifecycle. Giữ ranh giới rõ giữa transport, subprotocol, authentication và nghiệp vụ là điều kiện để WebSocket client Java hoạt động đúng và an toàn.

### Tham khảo chính thức

- [Java SE 17 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html)
- [Java SE 17 — HttpClient.newWebSocketBuilder()](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 — WebSocket (sendText, request, sendClose, abort, getSubprotocol)](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html)
- [Java SE 17 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
- [Java SE 17 — WebSocketHandshakeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocketHandshakeException.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html).