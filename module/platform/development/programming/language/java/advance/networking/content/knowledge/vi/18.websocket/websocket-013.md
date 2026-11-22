# Ranh giới WebSocket client API của JDK và cách xây dựng WebSocket server trong Java

## 1. Kết luận kiến trúc trước khi viết code

**JDK 17+ có WebSocket _client_ API chuẩn trong module `java.net.http`; nó không cung cấp WebSocket _server_ API cấp cao tương ứng trong module này.** Do đó, việc tạo một client kết nối tới `wss://...` có thể dùng các lớp sẵn có của JDK, còn muốn **lắng nghe và phục vụ nhiều WebSocket clients** thì thường cần **server framework hoặc implementation WebSocket** như Jakarta WebSocket trong một container, Spring WebSocket, Jetty, Netty hoặc một thư viện hỗ trợ RFC 6455 phù hợp.

Phân biệt hai trách nhiệm:

~~~text
                Ứng dụng client Java 17+
                       |
       HttpClient.newWebSocketBuilder()
                       |
       WebSocket.Builder.buildAsync(...)
                       |
          java.net.http.WebSocket
                       |
          ws:// hoặc wss://
                       |
           proxy/load balancer
                       |
         WebSocket server endpoint
          (Jakarta / Spring / Jetty /
           Netty / thư viện phù hợp)
                       |
        validation, authorization,
        message handlers, state,
        pub/sub, backpressure, storage
~~~

**Không có chuyện `HttpClient.newWebSocketBuilder()` biến một `HttpClient` thành server.** `HttpClient` chủ động **gọi ra ngoài**, không có `accept()` để nhận incoming WebSocket connections. Ngược lại `java.net.ServerSocket` biết nhận TCP connections nhưng **không tự triển khai WebSocket protocol**. `com.sun.net.httpserver.HttpServer` giúp viết HTTP server đơn giản, nhưng không cung cấp một high-level RFC 6455 WebSocket server endpoint tương đương `java.net.http.WebSocket`.

Mục tiêu bài học:

1. Nhận diện chính xác những lớp Java chuẩn **chỉ dành cho client** và trách nhiệm nào thuộc **server**.
2. Nắm các mốc handshake, masking, frames, fragmentation, Ping/Pong, Close và authentication mà server phải xử lý.
3. Chọn server stack hợp lý: **Jakarta WebSocket**, Spring, Jetty/Undertow, Netty hoặc một implementation được kiểm thử.
4. Đọc và chạy ví dụ **JDK 17+ độc lập**: client chuẩn gọi tới server vòng lặp nhỏ được viết bằng `ServerSocket` chỉ để **minh họa ranh giới**.
5. Hiểu giới hạn của server demo, không sao chép nó làm production server.
6. Thiết kế bảo mật, resource quotas, session state, backpressure, reconnect và scaling đúng.

## 2. Những thứ JDK 17 cung cấp — và những thứ KHÔNG cung cấp

| Nhu cầu | API có sẵn trong JDK 17? | Ghi chú |
| --- | --- | --- |
| HTTP client đồng bộ/bất đồng bộ | **Có**: `HttpClient` | `send`, `sendAsync` |
| WebSocket **client** | **Có**: `java.net.http.WebSocket` | Handshake, gửi text/binary/Ping/Close, callbacks |
| WebSocket client builder | **Có**: `HttpClient.newWebSocketBuilder()` | Cấu hình URI, timeout, subprotocol/header theo API |
| WebSocket client event callbacks | **Có**: `WebSocket.Listener` | `onOpen`, `onText`, `onBinary`, `onPing`, `onPong`, `onClose`, `onError` |
| TCP listening socket | **Có**: `ServerSocket`/`ServerSocketChannel` | Chỉ có TCP, **không** tự hiểu WebSocket handshake/frames |
| HTTP server nhỏ để demo | **Có**: `com.sun.net.httpserver.HttpServer` | Không có API server WebSocket high-level tích hợp sẵn |
| `@ServerEndpoint` của Jakarta | **Không thuộc JDK `java.net.http`** | Cần Jakarta WebSocket API + server implementation/container |
| Spring WebSocket/Netty/Jetty server | **Không nằm trong JDK** | Thư viện/framework bên ngoài cần dependencies và runtime |
| Multi-node messaging, rooms, event persistence | **Không tự có từ WebSocket API** | Thuộc kiến trúc ứng dụng/broker/database |
| Automatic message ACK, exactly-once across reconnect | **Không** | Ứng dụng phải tự định nghĩa request IDs/cursors/transactions |

**Ranh giới quan trọng:** client WebSocket của JDK làm được **kết nối và truyền thông điệp tới một server chuẩn**, chứ không biến Java SE thành một WebSocket hosting framework. Bản thân JDK có đủ primitive TCP, I/O và crypto để **tự viết** một implementation, nhưng việc đó đòi tuân thủ RFC 6455 và một loạt nhiệm vụ bảo mật/vận hành.

### 2.1. Không nhầm ba nhóm package

- `java.net.http.HttpClient` và `java.net.http.WebSocket`: HTTP/WebSocket **client** chuẩn trong module `java.net.http`.
- `java.net.ServerSocket`, `java.nio.channels.ServerSocketChannel`: primitive **TCP listener**, không có WebSocket semantics.
- `jakarta.websocket.*` và `jakarta.websocket.server.*`: API WebSocket dùng cùng một implementation/runtime tương thích Jakarta, có khái niệm **server endpoints**. Các package này **không tự xuất hiện khi chỉ cài JDK**.

Một vài dự án cũ dùng `javax.websocket.*` theo Java EE/Jakarta đời trước; dự án dùng Jakarta EE hiện đại thường dùng `jakarta.websocket.*`. **Đừng trộn hai namespace** trong mã/dependencies mà không biết container bạn dùng hỗ trợ phiên bản nào.

## 3. Vai trò WebSocket client và WebSocket server khác nhau thế nào?

### 3.1. Client: chủ động kết nối ra ngoài

Client biết URI như `wss://chat.example.test/live`, tạo một **opening handshake**, kiểm tra response nâng cấp rồi trao đổi WebSocket messages. Với JDK 17:

~~~java
HttpClient client = HttpClient.newHttpClient();

WebSocket socket = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .buildAsync(URI.create("wss://chat.example.test/live"),
                    listener)
        .join();
~~~

Đây là **đoạn minh họa không độc lập**; `listener` là một `WebSocket.Listener` đã khai báo, cần imports `java.net.URI`, `java.net.http.*` và `java.time.Duration`. Ở app bất đồng bộ, không dùng `join()` để block UI/event loop; tiếp tục bằng `thenAccept`/`thenCompose` khi thích hợp.

Client API chịu trách nhiệm các chi tiết WebSocket **phía client**, chẳng hạn tạo key handshake, kiểm tra `Sec-WebSocket-Accept`, frame encode/decode, **mask outbound client frames**, xử lý control frames theo API và chuyển sự kiện tới `Listener`. Client vẫn phải tự lo **nội dung message, schema, quyền, retry và state ứng dụng**.

### 3.2. Server: bị động nhận và duy trì nhiều phiên

Server phải:

1. **Listen** trên một cổng/route và nhận các HTTP Upgrade requests (hoặc handshake khác được chuẩn/hạ tầng hỗ trợ).
2. **Validate** method, headers, phiên bản WebSocket, key, origin/auth và giới hạn số phiên.
3. **Chấp nhận/từ chối handshake**, nếu chấp nhận thì trả response hợp lệ rồi chuyển socket sang WebSocket framing.
4. **Xử lý nhiều kết nối đồng thời**, state riêng từng connection, listener lifecycle, message size/rate limits.
5. **Đọc/ghi frames**, xử lý fragmentation, masking, control frames, UTF-8 và đúng close handshake.
6. **Định tuyến messages** tới nghiệp vụ, kiểm tra authorization mỗi thao tác, gửi response/event/fan-out.
7. **Quản lý slow clients**, outbound queue, timers, idle timeout, errors và graceful shutdown.
8. **Tích hợp hạ tầng**, TLS/WSS, reverse proxy, load balancer, broker, observability.

Các trách nhiệm này **không được tự động giải quyết** bởi một `ServerSocket.accept()`. Vì vậy hãy chọn một server implementation đã được kiểm thử, thay vì tự dựng handler từ TCP primitives cho ứng dụng Internet.

### 3.3. WebSocket không phải HTTP CRUD được gửi lại vô hạn

Sau handshake HTTP/1.1 `101 Switching Protocols`, các messages là **WebSocket frames**, không phải `GET/POST` mới trên cùng kết nối. Nghiệp vụ muốn “create/update/subscribe” phải có protocol ứng dụng, ví dụ:

~~~json
{"type":"subscribe","channel":"orders/123","requestId":"req-41"}
{"type":"subscribed","channel":"orders/123","requestId":"req-41"}
{"type":"order.updated","channel":"orders/123","sequence":782,"status":"packed"}
~~~

Đây là **JSON envelope do ứng dụng thiết kế**, không phải định dạng RFC 6455 yêu cầu. WebSocket tự cung cấp **message boundary và transport framing**, không tự cung cấp database transaction, API authorization, JSON schema hoặc durable subscriptions.

## 4. JDK client API: cách xây dựng connection đúng

### 4.1. `WebSocket.Builder` và `buildAsync`

~~~java
CompletableFuture<WebSocket> opened =
        HttpClient.newHttpClient()
                .newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .subprotocols("chat.v1")
                .buildAsync(URI.create("wss://example.test/room"),
                            listener);
~~~

Đây là **mã minh họa** có listener đã khai báo; imports `java.net.http.*`, `java.net.URI`, `java.time.Duration` và `CompletableFuture`. `buildAsync` trả future hoàn thành với `WebSocket` sau khi handshake thành công, hoặc thất bại khi handshake/network/TLS không hợp lệ.

`subprotocols("chat.v1")` **đề nghị** một application subprotocol; server phải đồng ý và phản hồi hợp lệ. Đừng nhầm subprotocol với HTTP header `Content-Type`, và đừng coi tên subprotocol là bằng chứng client có quyền truy cập.

Với một số custom HTTP headers hợp lệ, builder cung cấp `header(name, value)`. Không tự đặt thủ công **các header bắt tay được JDK điều khiển** như `Sec-WebSocket-Key`/`Upgrade` tùy tiện; có headers bị API từ chối hoặc phải được handshake engine quản lý. Khả năng tùy biến headers của **Java client** cũng khác browser `WebSocket` API.

### 4.2. `WebSocket.Listener`: callback và receive demand

~~~java
WebSocket.Listener listener = new WebSocket.Listener() {
    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket ws, CharSequence data, boolean last) {
        System.out.println("chunk=" + data + ", last=" + last);
        ws.request(1);
        return null;
    }

    @Override
    public void onError(WebSocket ws, Throwable error) {
        error.printStackTrace();
    }
};
~~~

Đây là **fragment minh họa**, cần import `java.net.http.WebSocket` và `java.util.concurrent.CompletionStage`. Listener nhận events **bất đồng bộ**. Phương thức `request(n)` điều tiết số callbacks được yêu cầu để xử lý dữ liệu nhận; nếu ứng dụng không phát demand phù hợp, các callbacks tiếp theo có thể không được phát như mong đợi.

**Không hiểu sai `request(1)`**: nó không tự gửi một WebSocket application request tới server, không có nghĩa “xin một message chat” theo giao thức nghiệp vụ; đây là **receive demand** của Java client Listener. Nếu workload cần xử lý chậm, điều tiết request thêm bằng một queue/executor có giới hạn thay vì gọi `request(Long.MAX_VALUE)` và giữ messages vô hạn.

### 4.3. Text messages có thể được chia nhiều callbacks

Tham số `boolean last` của `onText` chỉ báo **phần cuối của một text message**, không phải kết thúc connection. Một message có thể đến theo nhiều chunks:

~~~text
onText(ws, "order.", false)
onText(ws, "updated", true)
=> một message ứng dụng: "order.updated"
~~~

Một parser JSON nên **tích lũy theo session tới `last=true`**, sau đó validate cả message. Đừng coi mỗi lần callback là một JSON hoàn chỉnh và đừng dùng `StringBuilder` không giới hạn với một người gửi độc hại.

### 4.4. Các phương thức gửi

~~~java
// Với biến ws là WebSocket đã kết nối:
ws.sendText("hello", true);
ws.sendBinary(ByteBuffer.wrap(new byte[]{1, 2, 3}), true);
ws.sendPing(ByteBuffer.wrap(new byte[]{7}));
ws.sendClose(WebSocket.NORMAL_CLOSURE, "done");
~~~

Đây là **đoạn minh họa các API riêng**, không phải lời khuyên gọi cả bốn liên tiếp trong một chương trình production. `sendText` và `sendBinary` trả future; dữ liệu có thể được gửi theo nhiều fragments, tham số `last` cho biết cuối **message**, không phải cuối socket. `sendPing` dành cho control frame có payload tối đa theo RFC là **125 bytes**. `sendClose` khởi tạo close handshake.

**Hoàn thành `sendText` không chứng minh server đã commit nghiệp vụ.** Nếu gửi `{"type":"payment.capture"}`, muốn biết xử lý thành công phải đợi **application ACK/status** có request ID. TCP/WebSocket delivery cũng không cung cấp exactly-once qua reconnect.

### 4.5. Gửi nhiều fragments theo thứ tự

~~~java
CompletableFuture<WebSocket> sent =
        ws.sendText("hel", false)
          .thenCompose(ready -> ready.sendText("lo", true));
~~~

Đoạn minh họa với `ws` đã kết nối. Chuỗi trên tạo **một text message “hello”** từ hai phần và tuần tự hóa send. Không phát hai sends cùng lúc rồi giả định mọi implementation sẽ sắp xếp theo ý bạn; quản lý một writer/queue cho connection khi có nhiều producers.

### 4.6. `onClose` và `onError` không thay cho application state

`onClose(ws, statusCode, reason)` quan sát close handshake, `onError(ws, error)` xử lý sự cố. Một peer rớt mạng có thể không gửi frame Close hợp lệ. Ứng dụng cần timeout, reconnect và state recovery; mã đóng **1000** nghĩa là normal closure ở protocol level, không chứng minh các commands trước đó đã được lưu thành công.

## 5. Handshake WebSocket phía server: một số điều framework phải làm

### 5.1. Bắt đầu từ HTTP/1.1 Upgrade

Một opening handshake minh họa:

~~~http
GET /ws HTTP/1.1
Host: chat.example.test
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Origin: https://chat.example.test
~~~

Nếu chấp nhận, server trả:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
~~~

`Sec-WebSocket-Accept` là:

~~~text
Base64(SHA-1(
    Sec-WebSocket-Key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
))
~~~

Key và accept ở trên là ví dụ nổi tiếng từ **RFC 6455**. **SHA-1 ở đây chỉ phục vụ kiểm tra handshake/protocol**, không phải mật mã bảo vệ message, hash mật khẩu hay chứng minh danh tính. Với dữ liệu nhạy cảm, sử dụng **`wss://` qua TLS** và xác thực/ủy quyền ở tầng ứng dụng.

### 5.2. Các kiểm tra mà server phải coi là trách nhiệm thật

Trước khi chấp nhận:

- Phương thức và phiên bản HTTP hợp lệ cho handshake, request target/route đúng.
- `Upgrade: websocket` và `Connection` chứa các token tương ứng theo cú pháp header.
- `Sec-WebSocket-Version: 13` và `Sec-WebSocket-Key` có định dạng/cấu trúc hợp lệ; không chấp nhận thiếu key/giá trị sai.
- Origin phù hợp chính sách browser applications; cookie/session/token/credentials hợp lệ.
- Route/subprotocol được phép; nếu thương lượng `Sec-WebSocket-Protocol`, server chỉ chọn giá trị client đã đề nghị và được server hỗ trợ.
- Giới hạn tốc độ/số lượng connections/handshakes và kích thước headers; chống amplification/DoS theo hạ tầng.
- TLS/proxy forwarding context đáng tin; không dựa vào header giả mạo từ một client public.

Đây **chưa phải danh sách đầy đủ mọi quy tắc của RFC 6455**; hãy để server framework xử lý framing/handshake đã kiểm thử và dùng application hooks cho authentication/authorization.

### 5.3. HTTP/2 không chỉ cần copy header Upgrade

WebSocket RFC 6455 qua HTTP/1.1 dùng `101 Switching Protocols`. RFC 8441 định nghĩa một cách bootstrapping WebSockets over **HTTP/2 extended CONNECT** trong môi trường hỗ trợ; **không** thể bê nguyên `Upgrade: websocket` của HTTP/1.1 sang HTTP/2 và coi như tương đương. Không giả định Java 17 client, proxy và server đều hỗ trợ lựa chọn HTTP/2 này. Khi vận hành, xác định rõ giao thức/stack đang thực tế được dùng.

## 6. Server sau khi handshake: không chỉ nhận String

Sau khi handshake, WebSocket không còn trao đổi từng HTTP request/response thông thường trên connection đó. Server phải xử lý **frames**, phân mảnh, control messages và lifecycle.

| Nội dung | Server phải làm đúng |
| --- | --- |
| Text frame `0x1` | Đọc payload, kiểm tra UTF-8 của text message, ghép continuation |
| Binary frame `0x2` | Nhận bytes và chuyển cho parser theo application schema |
| Continuation `0x0` | Ghép fragmented message theo thứ tự và giới hạn kích thước |
| Close `0x8` | Kiểm tra code/reason, phản hồi close handshake, cleanup |
| Ping `0x9` / Pong `0xA` | Tuân theo giới hạn control frame, phát hiện liveness |
| Client frame masking | **Bắt buộc client → server có mask** theo RFC 6455 |
| Server frames | **Server → client không mask** theo RFC 6455 |
| Extended payload lengths | Xử lý đúng các dạng 7-bit, 16-bit, 64-bit và giới hạn thực tế |
| Message boundaries | Không nhầm một TCP read là một full WebSocket message |
| Compression/extensions | Thương lượng đúng, giới hạn inflate/decompression |
| Backpressure | Không xếp vô hạn response/events cho client chậm |
| Closing on errors | Trả close/error hợp lệ khi có thể; release resources đúng một lần |

### 6.1. Tại sao một `Socket.read()` không tương đương `onMessage(String)`?

TCP là **byte stream**, còn WebSocket định nghĩa **message/frame structure**. Một `InputStream.read(buffer)` có thể nhận nửa frame header, nhiều frames chung một lần, hoặc phần nhỏ của payload. Server phải parse **theo bytes đã nhận thực tế**, chứ không giả định mỗi read ra đúng một message.

Trong sản phẩm, dùng implementation hỗ trợ partial network reads, fragmentation, extended lengths, UTF-8 validation và max sizes. Một parser “đọc byte đầu, byte thứ hai, rồi nhận đúng N” chỉ hoạt động cho **một tập hợp frame rất hẹp** trong demo.

### 6.2. Masking không phải mã hóa

Một client frame mang 4-byte masking key, payload trên wire được XOR với key theo RFC. Server unmask để lấy bytes. Nó **không tạo confidentiality** và không thay cho TLS/WSS. Mã độc hại có thể tự gửi frame có mask hợp lệ; masking cũng **không chứng minh ai đã gửi**.

### 6.3. Một WebSocket nhiều business messages

Server cần phân biệt:

~~~text
FRAME -> MESSAGE -> PARSE -> VALIDATE -> AUTHORIZE -> COMMAND/EVENT
                                 |
                                 +-> store/queue/service
                                 |
                                 +-> response/ack / fan-out
~~~

Phân biệt clear giữa **wire transport** và **ngữ nghĩa nghiệp vụ** làm việc debug dễ hơn: socket nhận đủ bytes chưa chắc request được phép; ACK ở network layer không đồng nghĩa database transaction đã commit.

## 7. Chọn WebSocket server implementation trong Java

### 7.1. Jakarta WebSocket: mô hình endpoint/event trên container

Jakarta WebSocket API định nghĩa các annotations/kiểu để triển khai WebSocket endpoints. Ví dụ server endpoint **minh họa**:

~~~java
import jakarta.websocket.OnMessage;
import jakarta.websocket.server.ServerEndpoint;

@ServerEndpoint("/echo")
public class EchoEndpoint {
    @OnMessage
    public String onMessage(String message) {
        return "echo:" + message;
    }
}
~~~

**Đoạn này KHÔNG biên dịch chỉ với JDK 17 thuần.** Nó cần Jakarta WebSocket API và **runtime/container server hỗ trợ** (cùng phiên bản namespace/dependency), ví dụ một Jakarta-compatible container hoặc thư viện tương ứng. Phần handshake/frame implementation do runtime thực hiện; `@OnMessage` chỉ xử lý text đã được framework giải mã.

Trong sản phẩm vẫn cần auth/Origin, schema, size limits, concurrency, outbound handling, metrics và cấu hình container. `@ServerEndpoint` không khiến dữ liệu user mặc nhiên an toàn.

### 7.2. Spring WebSocket

Nếu ứng dụng là Spring Boot, bạn có thể dùng Spring WebSocket handlers/`WebSocketHandler` hoặc STOMP messaging với broker relay tùy thiết kế. Spring giúp tích hợp HTTP handshake, interceptors, security, session handlers và vận hành cùng container.

**STOMP không phải một thành phần bắt buộc của WebSocket.** Đó là **application messaging protocol** có thể chạy trên WebSocket; dùng nó khi cần model topics/subscribe/ack tương ứng, không tự bật STOMP chỉ để echo hai chuỗi text.

Spring WebSocket hay Jakarta WebSocket đều yêu cầu **dependencies và runtime ngoài Java SE**, và cách cấu hình endpoint/proxy phụ thuộc phiên bản. Không dùng một đoạn code được ghi là Java SE standalone khi nó thực chất yêu cầu server container.

### 7.3. Jetty / Undertow / Netty và lựa chọn thấp tầng

- **Jetty, Undertow:** server HTTP/WebSocket implementations phù hợp nếu hệ thống dùng embedded server, servlet/HTTP integration hoặc runtime tương ứng.
- **Netty:** event-driven networking framework mạnh khi cần chủ động cấu hình pipeline I/O, frame handlers, TLS, high-throughput và protocol-specific codecs.
- **Jakarta-based servers:** phù hợp môi trường Jakarta EE và mô hình endpoint chính thức.
- **Tự triển khai bằng `ServerSocket`:** chỉ nên cân nhắc cho **bài học, nghiên cứu protocol hoặc trường hợp đã có năng lực kiểm thử an ninh rất cao**, không phải lựa chọn mặc định cho public service.

Chọn framework theo **maintenance/security updates**, version compatibility, Java runtime, WebSocket extensions, observability, TLS/proxy support, backpressure API, load profile và đội ngũ vận hành. Không có một lựa chọn luôn đúng cho mọi sản phẩm.

### 7.4. Quyết định nhanh

| Hoàn cảnh | Hướng nên bắt đầu |
| --- | --- |
| Viết client Java gọi tới dịch vụ WebSocket | `java.net.http.WebSocket` của JDK 17 |
| Viết endpoint cho ứng dụng Jakarta EE | Jakarta WebSocket + implementation/container |
| Ứng dụng đã dùng Spring Boot | Spring WebSocket hoặc Spring messaging phù hợp |
| Server networking tùy biến, traffic lớn | Đánh giá Netty/Jetty/Undertow và benchmarks |
| Dựng demo giải thích handshake/frame | `ServerSocket` thuần với **giới hạn nêu rõ** |
| Chỉ cần thông báo một chiều từ server | Cân nhắc SSE thay WebSocket |
| Chỉ có HTTP CRUD hoặc upload file | HTTP/REST/streaming, không cần session WebSocket |
| Cần durable messaging/exactly-once | Thêm broker/database/protocol nghiệp vụ; WebSocket riêng không đủ |

## 8. Ví dụ Java 17+ chạy độc lập: JDK WebSocket client và demo server thấp tầng

Ví dụ này cố ý cho thấy **rất rõ ranh giới**: **client** dùng API WebSocket chính thức của JDK; **server** phải tự thực hiện một phần handshake và frame parsing bằng `ServerSocket` vì JDK không cung cấp server endpoint high-level tương đương.

Demo mở đúng **một connection** ở `127.0.0.1`. Sau handshake thành công:

1. **Server chủ động gửi** text message `server-ready` ngay khi session mở.
2. **Client nhận server push**, sau đó gửi text `client-hello`.
3. **Server unmask client frame**, gửi phản hồi `ack:client-hello`.
4. Client gửi Close với code `1000`, server echo Close frame, các futures hoàn thành và sockets đóng.

Tại server, code **chỉ chấp nhận một khung FIN=1 có payload ≤125 byte, RSV=0, client mask**. Nó **không** xử lý extended lengths, binary, fragmented messages, ping/pong, WSS, Origin, authentication, mọi HTTP handshake edge cases hay nhiều clients. **ĐÂY KHÔNG PHẢI SERVER CHUẨN ĐẦY ĐỦ / KHÔNG ĐƯỢC TRIỂN KHAI RA INTERNET.**

Lưu toàn bộ code thành **WebSocketApiBoundaryDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
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
import java.util.concurrent.TimeUnit;

public class WebSocketApiBoundaryDemo {
    record Frame(int opcode, byte[] payload) {}

    // Đọc HTTP/1.1 request headers tới CRLFCRLF (demo giới hạn 8192 byte).
    static String readHttpHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        int tail = 0;
        for (int c; (c = in.read()) != -1;) {
            buffer.write(c);
            if (buffer.size() > 8192) {
                throw new IOException("HTTP headers too large");
            }
            tail = (tail << 8) | c;
            if (tail == 0x0d0a0d0a) {
                return buffer.toString(StandardCharsets.ISO_8859_1);
            }
        }
        throw new EOFException("HTTP upgrade incomplete");
    }

    static String requiredHeader(String request, String name)
            throws IOException {
        for (String line : request.split("\r\n")) {
            int colon = line.indexOf(':');
            if (colon > 0
                    && line.substring(0, colon).trim()
                            .equalsIgnoreCase(name)) {
                return line.substring(colon + 1).trim();
            }
        }
        throw new IOException("Missing header " + name);
    }

    // CHỈ demo: một client frame FIN=1, RSV=0, payload length <= 125.
    static Frame readClientFrame(InputStream in) throws IOException {
        int first = in.read();
        int second = in.read();
        if (first < 0 || second < 0) {
            throw new EOFException("Frame header");
        }
        if ((first & 0x80) == 0 || (first & 0x70) != 0) {
            throw new IOException("Demo needs FIN=1, RSV=0");
        }
        if ((second & 0x80) == 0) {
            throw new IOException("Client frame not masked");
        }
        int length = second & 0x7f;
        if (length >= 126) {
            throw new IOException("Demo only allows short frames");
        }

        byte[] mask = in.readNBytes(4);
        byte[] bytes = in.readNBytes(length);
        if (mask.length != 4 || bytes.length != length) {
            throw new EOFException("Short frame");
        }
        for (int i = 0; i < bytes.length; i++) {
            bytes[i] ^= mask[i & 3];
        }
        return new Frame(first & 15, bytes);
    }

    static void sendServerFrame(
            OutputStream out, int opcode, byte[] bytes)
            throws IOException {
        if (bytes.length > 125) {
            throw new IOException("Frame too large for demo");
        }
        out.write(0x80 | opcode); // FIN=1; server frame unmasked.
        out.write(bytes.length);
        out.write(bytes);
        out.flush();
    }

    static void serveOnce(
            ServerSocket listener, CompletableFuture<Void> finished) {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5000);
            InputStream input = peer.getInputStream();
            OutputStream output = peer.getOutputStream();

            String request = readHttpHeaders(input);
            if (!request.startsWith("GET /ws HTTP/1.1\r\n")) {
                throw new IOException("Unexpected request");
            }

            String key = requiredHeader(request, "Sec-WebSocket-Key");
            if (Base64.getDecoder().decode(key).length != 16) {
                throw new IOException("Bad key");
            }

            String toHash =
                    key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
            String accept = Base64.getEncoder().encodeToString(
                    MessageDigest.getInstance("SHA-1")
                            .digest(toHash.getBytes(
                                    StandardCharsets.US_ASCII)));

            String reply = "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
            output.write(reply.getBytes(StandardCharsets.US_ASCII));
            output.flush();

            // Server push mà client KHÔNG gửi message trước.
            sendServerFrame(output, 1,
                    "server-ready".getBytes(StandardCharsets.US_ASCII));

            Frame text = readClientFrame(input);
            if (text.opcode() != 1) {
                throw new IOException("Expected text frame");
            }
            String body = new String(
                    text.payload(), StandardCharsets.UTF_8);
            sendServerFrame(output, 1,
                    ("ack:" + body).getBytes(StandardCharsets.UTF_8));

            Frame close = readClientFrame(input);
            if (close.opcode() != 8) {
                throw new IOException("Expected close");
            }
            sendServerFrame(output, 8, close.payload());
            finished.complete(null);
        } catch (Throwable problem) {
            finished.completeExceptionally(problem);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(5000);

            CompletableFuture<Void> serverDone =
                    new CompletableFuture<>();
            Thread worker = new Thread(
                    () -> serveOnce(listener, serverDone));
            worker.setDaemon(true);
            worker.start();

            CompletableFuture<String> greeting =
                    new CompletableFuture<>();
            CompletableFuture<String> acknowledgement =
                    new CompletableFuture<>();
            CompletableFuture<Integer> closeCode =
                    new CompletableFuture<>();

            WebSocket.Listener listenerCallback =
                    new WebSocket.Listener() {
                final StringBuilder message = new StringBuilder();
                int completed = 0;

                @Override
                public void onOpen(WebSocket ws) {
                    ws.request(1);
                }

                @Override
                public CompletionStage<?> onText(
                        WebSocket ws,
                        CharSequence data, boolean last) {
                    message.append(data);
                    if (last) {
                        String whole = message.toString();
                        message.setLength(0);
                        if (completed++ == 0) {
                            greeting.complete(whole);
                        } else {
                            acknowledgement.complete(whole);
                        }
                    }
                    ws.request(1);
                    return null;
                }

                @Override
                public CompletionStage<?> onClose(
                        WebSocket ws, int statusCode, String reason) {
                    closeCode.complete(statusCode);
                    return null;
                }

                @Override
                public void onError(WebSocket ws, Throwable error) {
                    greeting.completeExceptionally(error);
                    acknowledgement.completeExceptionally(error);
                    closeCode.completeExceptionally(error);
                }
            };

            URI uri = URI.create("ws://127.0.0.1:"
                    + listener.getLocalPort() + "/ws");

            WebSocket ws = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .buildAsync(uri, listenerCallback)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("server push: "
                    + greeting.get(5, TimeUnit.SECONDS));

            ws.sendText("client-hello", true)
                    .get(5, TimeUnit.SECONDS);
            System.out.println("client receives: "
                    + acknowledgement.get(5, TimeUnit.SECONDS));

            ws.sendClose(WebSocket.NORMAL_CLOSURE, "done")
                    .get(5, TimeUnit.SECONDS);
            System.out.println("close code: "
                    + closeCode.get(5, TimeUnit.SECONDS));

            serverDone.get(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 WebSocketApiBoundaryDemo.java
java WebSocketApiBoundaryDemo
~~~

**Stdout đã kiểm tra bằng Java 17 JShell:**

~~~text
server push: server-ready
client receives: ack:client-hello
close code: 1000
~~~

### 8.1. Vì sao output thể hiện ranh giới client/server?

**Client** không tính `Sec-WebSocket-Accept`, không tạo masking key bằng tay, không parse raw frame headers — `java.net.http.WebSocket` thực hiện các phần đó. **Server demo** phải tự đọc HTTP request bytes, tính accept hash, viết `101`, đọc masking key, unmask payload và phát frame. Trong production, những việc server thấp tầng này cần do **implementation WebSocket thực thụ** đảm trách.

**Server push trước khi client gửi:** chuỗi `server-ready` được gửi ngay sau handshake, chứng minh server có thể chủ động đẩy message, khác mô hình request/response HTTP thông thường.

**`client-hello` và `ack:client-hello`:** đây chỉ là text ở tầng ứng dụng. Server không tự có định dạng `ack:` theo RFC; code chủ động tạo nó. ACK trong demo không liên quan database commit.

**Close `1000`:** JDK client và server demo trao Close frame, client Listener nhận mã đóng bình thường. Mã này chỉ xác nhận kết thúc theo protocol level, không thay thế logic nghiệp vụ.

### 8.2. Không được dùng server demo cho Internet

Mặc dù chương trình **chạy được**, nó cố ý thiếu nhiều yêu cầu bắt buộc hoặc cần thiết của một implementation production:

- Chỉ kiểm tra `GET /ws HTTP/1.1` và `Sec-WebSocket-Key` tối thiểu; không verify đầy đủ `Upgrade`/`Connection`/`Sec-WebSocket-Version`/subprotocol và mọi HTTP edge cases.
- Không dùng TLS/WSS, xác thực người dùng, Origin validation, CSWSH defense hay authorization.
- Không xử lý frame fragmentation/continuation, extended lengths, nhiều text messages hoặc binary.
- Không xử lý Ping/Pong/control interleaving, compression/extensions, UTF-8 validation, Close code/reason đầy đủ.
- Không có nhiều clients đồng thời, admission control, slow-client/backpressure, max total message size, rate limiting và quota.
- Bắt `Throwable` để báo future trong demo; production cần chiến lược lỗi/resource cleanup và tránh biến lỗi nghiêm trọng thành response giả.
- Không có graceful shutdown/reconnect/durable state hoặc broker/monitoring.

Giữ nó trên **loopback** để học protocol. Để xây server thật, dùng Jakarta/Spring/Jetty/Netty và test bảo mật/tương thích.

## 9. Thiết kế server endpoint production: từ handshake đến message handler

Một WebSocket endpoint thực cần nhiều lớp hơn một hàm `onMessage`:

~~~text
HTTP server / TLS listener
          |
          v
WebSocket handshake validator
  - origin, authentication, route, version, subprotocol
  - connection quotas, proxy policy
          |
          v
WebSocket protocol implementation
  - RFC frames, masking, fragmentation, control frames
  - max sizes, UTF-8, compression, close states
          |
          v
Session manager per connection
  - principal, subscriptions, heartbeat, outbound queue
          |
          v
Application message dispatcher
  - parse schema / validate / authorization / rate limit
          |
          +-> command handler / service / database
          |
          +-> event publisher / message broker
          |
          v
Send coordinator
  - per-session order, backpressure, ACK policy
~~~

### 9.1. Sở hữu state theo connection

Với một session WebSocket, các trường hợp cần lưu:

| Trạng thái | Phạm vi |
| --- | --- |
| `sessionId` và socket handle | Một TCP/WebSocket connection |
| `userId`/principal và credential expiry | Phiên đã xác thực và auth policy |
| `subscriptions`, rooms, filters | Channels user có quyền lắng nghe |
| `outboundQueue`, queued byte count | Giới hạn chờ gửi cho slow client |
| `lastPing`/`lastPong`/idle deadline | Theo dõi liveness |
| `lastDeliveredSequence`, request IDs | Khôi phục sau reconnect nếu cần |
| `closeState`/cleanup guard | Tránh đóng và release nhiều lần |

Không giữ mọi durable event chỉ trong RAM của một WebSocket connection. Khi node restart, socket mất; messages, job status và transaction results cần database/broker nếu muốn phục hồi.

### 9.2. Thread safety của send và session

Các framework có semantics cụ thể về việc gọi send đồng thời. Đừng mặc định hai business workers có thể cùng ghi frame/text fragments mà vẫn giữ thứ tự application messages bạn mong muốn. Một **outbound queue/writer coordinator** per connection giúp serialize messages và giữ backpressure.

Khi dùng Java `WebSocket` client, không giữ mutable `ByteBuffer` dùng cho `sendBinary` rồi sửa bytes trước khi send future hoàn tất. Với server, cũng không chia một request parser/`StringBuilder` cho mọi sessions nếu không đồng bộ; mỗi connection cần state riêng hoặc cơ chế actor/event loop rõ ràng.

### 9.3. Server push không có nghĩa gửi vô hạn

Nếu producer tạo 10.000 messages/s và client tiêu thụ 100 messages/s, queue không giới hạn sẽ dẫn tới memory pressure. Server phải có:

- Giới hạn **queue size theo byte**, không chỉ số lượng message.
- Chính sách coalesce/drop cho events được phép bỏ (ví dụ trạng thái nhiệt độ cũ).
- Chính sách không bỏ các events quan trọng, thay vào đó lưu/replay hoặc ngừng phục vụ slow client.
- Timeout outbound và đóng chậm có lý do/metric rõ.
- Message size max, per-principal rate limits, subscription quotas.

`WebSocket.Listener.request(n)` ở JDK là một cơ chế **receive demand phía client**, không tự giải quyết toàn bộ backpressure từ broker đến server đến network đến UI.

## 10. Bảo mật server: WSS, authentication, Origin và CSWSH

### 10.1. WSS và TLS

Server production thường nhận `wss://`, thực hiện TLS và xác minh server identity phía client. Với termination ở load balancer, cần cấu hình an toàn đường đi từ proxy đến backend theo threat model; không dựa vào `ws://` public để truyền dữ liệu nhạy cảm.

**WebSocket masking không mã hóa dữ liệu.** `Sec-WebSocket-Key` không phải secret để bảo vệ session. Đừng thay TLS bằng XOR masking hoặc handshake accept hash.

### 10.2. Origin validation khi dùng cookies

Một website lạ có thể thử mở WebSocket cross-site đến backend dùng session cookies trong những điều kiện trình duyệt/cookie policy cho phép. Nếu server **không kiểm tra `Origin`**, có nguy cơ **Cross-Site WebSocket Hijacking (CSWSH)**. Server browser-facing nên áp dụng allowlist Origin thực tế, kết hợp bảo vệ cookie/session và authentication.

Không hiểu Origin validation như xác thực người dùng: **non-browser clients có thể giả mạo `Origin`**. Quyền truy cập cần session/token/mTLS và **authorization cho từng message/subscription**, không chỉ một phép kiểm tra Origin.

Không coi CORS preflight của `fetch` là lớp bảo vệ tự động cho WebSocket handshake; phải dùng cơ chế kiểm soát phù hợp của WebSocket server.

### 10.3. Không dùng query string làm nơi chứa bí mật dài hạn

Một URL như `wss://example.test/ws?token=long-lived-secret` có thể xuất hiện trong proxy logs, browser history hoặc monitoring. Với browser client không thể tùy ý thêm mọi custom authorization headers, hãy dùng cơ chế auth được thiết kế rõ (session cookie an toàn, short-lived scoped token hoặc authenticated handshake flow), có log redaction, TTL ngắn và rotation.

Java JDK client có API cấu hình một số request headers, nhưng **không suy ra browser WebSocket API giống vậy**. Luôn phân biệt client platform.

### 10.4. Mỗi message là dữ liệu chưa đáng tin

Sau khi xác thực kết nối, server phải tiếp tục validate **mọi** command:

- Type/JSON schema/UTF-8/size limits.
- Allowed room/topic/principal permissions.
- Dữ liệu ID/path không có injection hoặc lộ object của user khác.
- Rate/message quotas và chống spam/abuse.
- Re-check quyền khi bị revoke hoặc token hết hạn.
- Safe logging, không in cookie/token/payload nhạy cảm.

Một WebSocket connection được chấp nhận không phải vé vào toàn bộ backend APIs.

## 11. Heartbeat, Close và reconnect: trách nhiệm của ứng dụng

### 11.1. Ping/Pong

WebSocket control frames `Ping`/`Pong` giúp phát hiện kết nối không phản hồi. Một Pong thành công **không chứng minh server đã xử lý một business command**. Tần suất heartbeat nên xét load balancer idle timeout, mobile battery, network variability và số connections.

Browser JavaScript API có giới hạn với Ping control frames; nhiều ứng dụng browser dùng application-level heartbeat messages. Java JDK client có `sendPing`/`sendPong`, nhưng đó không tự là một global liveness policy.

### 11.2. Close handshake khác rớt mạng

Khi chủ động đóng, hai phía có thể trao Close control frames; mã **1000** là normal closure. Nhưng khi Internet rớt hoặc process crash, không phải lúc nào có Close frames. Server cần idle deadline và cleanup; client cần phân biệt user logout/cancel với network failure để không tự reconnect vô hạn.

### 11.3. Reconnect không có nghĩa state cũ còn đó

~~~text
Connected to Node A
    |
    +-- subscribe(room-7)
    +-- receive event sequence=120
    X network loss / node restart

Reconnect to Node B
    |
    +-- authenticate again
    +-- restore subscriptions
    +-- request missed events since 120
    +-- if history missing: fetch snapshot / resync
~~~

Đây là logic **do ứng dụng thiết kế**, không phải protocol WebSocket có sẵn. Nếu yêu cầu exactly-once hoặc reliable commands, cần request IDs, idempotency keys, durable event cursor, ACK semantics và transaction handling.

### 11.4. Reconnect backoff và deployment

Sau khi một node restart, hàng chục nghìn clients có thể reconnect cùng lúc. Dùng exponential backoff có giới hạn, random jitter và server admission caps để tránh reconnect storm. Khi rolling deploy, server có thể drain sessions, gửi close code/reason phù hợp, giới hạn thời gian rồi chuyển sang node mới. Không giữ socket vĩnh viễn bằng cách không deploy.

## 12. Triển khai nhiều server nodes: socket gắn với một node, events thì không

Mỗi WebSocket connection đang mở thường gắn với một node cụ thể. Nếu user A kết nối Node 1 và user B kết nối Node 2, Node 1 không thể trực tiếp gọi send trên `WebSocketSession` ở bộ nhớ Node 2.

~~~text
User A --WS--> Node 1 --\
                        +--> broker / topic bus --> events
User B --WS--> Node 2 --/               |
                                        v
                           mỗi node fan-out tới
                           sessions đang kết nối
~~~

Vì vậy production architecture thường cần:

- Distributed broker/pub-sub cho events ở nhiều nodes.
- Shared or recoverable session/subscription state nếu ứng dụng cần resume.
- Durable storage cho messages/commands có yêu cầu truy xuất lại.
- Load balancer/WebSocket-aware proxy, idle timeout/connection limits.
- Metrics: concurrent connections, handshake failures, active sessions, outgoing queued bytes, slow clients, ping RTT, reconnect rates.
- Quy tắc order theo room/user/entity, không giả định một thứ tự toàn hệ thống tự tồn tại.

**Sticky sessions** có thể giữ một connection ổn định trên một node, nhưng không giải quyết reconnect sang node khác hoặc node crash. WebSocket server framework chỉ giải quyết phần **protocol/session hosting**, không tự tạo một hệ thống phân tán đáng tin cậy.

## 13. Hệ thống nào nên xây WebSocket server riêng?

Xây một **dịch vụ WebSocket** độc lập có ý nghĩa khi:

1. Sản phẩm cần quản lý nhiều live sessions, subscriptions hoặc có workload đặc thù.
2. Cần tích hợp brokers, per-user quotas và state reconciliation một cách có kiểm soát.
3. Có nhóm duy trì security updates, performance tests, failover và observability.
4. API client/web cần cả hai phía chủ động trao đổi thường xuyên, không chỉ lấy dữ liệu thưa.

Nhưng **xây dịch vụ WebSocket riêng** không đồng nghĩa **tự viết lại WebSocket protocol bằng TCP primitive**. Phần giao thức chuẩn nên nhờ framework, còn logic subscriptions/commands/fan-out là phần ứng dụng sở hữu.

Nếu chỉ cần trình duyệt nhận tiến độ một chiều, **SSE** có thể ít phức tạp hơn. Nếu chỉ có CRUD/REST, dùng HTTP. Nếu cần video/voice real-time có jitter buffer và NAT traversal, WebRTC có thể đúng hơn. Nếu cần file upload lớn, HTTP streaming/resumable upload thường thuận tiện hơn.

## 14. Lỗi thường gặp về ranh giới JDK client và server

| Nhầm lẫn | Tại sao sai | Cách xử lý |
| --- | --- | --- |
| `HttpClient.newWebSocketBuilder()` tạo server | Builder chỉ khởi tạo outbound client WebSocket | Dùng server framework/implementation |
| `HttpServer` của JDK có `@ServerEndpoint` sẵn | `jdk.httpserver` không cung cấp Jakarta WebSocket | Thêm Jakarta runtime hoặc server khác |
| `ServerSocket.accept()` đủ làm WebSocket server | Chỉ nhận TCP, không có RFC 6455 state machine | Chọn implementation hoặc học với demo có giới hạn |
| `javax.websocket` và `jakarta.websocket` luôn thay thế được | Namespace/version và container có thể khác | Đồng bộ dependencies/runtime |
| Tự đặt `Sec-WebSocket-Accept` để xác thực user | Đây chỉ là handshake correctness check | Thêm auth/session/authorization |
| Client frames gửi không mask | Vi phạm RFC 6455 | Dùng client library chuẩn |
| Server frames được mask giống client | Sai hướng frame masking RFC 6455 | Để server implementation xử lý |
| Mỗi TCP read = một full text message | Frames có thể chia/gộp trong stream | Parser/frame handling và size limit |
| Một `onText` callback luôn là message hoàn chỉnh | `last=false` có thể còn phần tiếp | Ghép tới `last=true` |
| Java Listener không gọi `request(n)` | Receive demand không được tiếp tục | Quản lý demand/backpressure |
| `sendText()` future complete = DB commit | Không có application ACK | RequestId + ACK/transaction |
| Ping/Pong là bằng chứng login còn hợp lệ | Liveness không thay authentication | Token/ACL policy riêng |
| CORS của fetch tự bảo vệ WebSocket | WebSocket handshake khác fetch/XHR | Origin allowlist + auth + CSWSH defense |
| Tắt TLS verification để kết nối WSS | Mở rủi ro MITM | Sửa certificate/trust đúng |
| Không giới hạn outbound queues | Client chậm làm server OOM | Backpressure/quotas |
| Dùng một per-connection buffer chung cho mọi user | Dữ liệu rò/trộn giữa sessions | Isolation theo session và concurrency control |
| Nối một WebSocket với mọi rooms không check ACL | User nhận dữ liệu không được phép | Authorize mỗi subscribe/action |
| Dùng raw server trong demo ở production | Thiếu RFC corner cases và security | Framework được bảo trì và test |
| Coi WebSocket là durable event storage | Lost events khi node crash/reconnect | Broker/database + sequence/replay |

## 15. Bài tập có đáp án

### Bài A — Chỉ cài JDK 17 có chạy server WebSocket cấp cao ngay không?

Đội cần expose `wss://company.test/updates` cho browser clients. Đã có `java.net.http.WebSocket` trên JDK 17. Chỉ dùng API này để nhận incoming connections được không?

**Đáp án:** không. Đó là **client API**. Hãy chọn Jakarta/Spring/Jetty/Netty hoặc runtime WebSocket khác. JDK cung cấp TCP primitives để tự viết protocol nhưng không có high-level server WebSocket endpoint tương đương.

### Bài B — Dự án Spring Boot muốn có /ws

Dự án đã dùng Spring Boot, authentication và controllers. Có nhất thiết tự xây `ServerSocket` để WebSocket hoạt động?

**Đáp án:** không. Đánh giá **Spring WebSocket** và server container của ứng dụng; cấu hình endpoint, authentication, Origin, limits và message handler. Tự parser frames thấp tầng thường tăng rủi ro.

### Bài C — Jakarta `@ServerEndpoint` báo không tìm thấy package

Code `import jakarta.websocket.server.ServerEndpoint` không compile khi chỉ chạy `javac EchoEndpoint.java` trên JDK17.

**Đáp án:** đây là **external API**, không thuộc Java SE/JDK. Thêm Jakarta WebSocket API tương thích và runtime implementation/container; kiểm tra không nhầm package `javax.websocket` với `jakarta.websocket`.

### Bài D — Server nhận frame từ client không mask

Một raw WebSocket server đọc text frame client có `MASK=0`, nhưng payload vẫn là JSON hợp lệ. Có chấp nhận không?

**Đáp án:** không nên chấp nhận theo RFC 6455; client-to-server frames **phải mask**. JSON payload hợp lệ không bù cho wire protocol violation.

### Bài E — Client đã gửi xong nhưng server không ghi DB

`ws.sendText("pay", true)` hoàn tất future; ứng dụng hiển thị “đã thanh toán thành công”. Có cơ sở không?

**Đáp án:** không. Future phản ánh hoạt động gửi ở client API, không phải business commit. Cần **application-level ACK**/status trên server cùng request ID và idempotency policy.

### Bài F — Server trả 101 nhưng không kiểm tra Origin

Ứng dụng dùng cookie login cho browser; server chấp nhận WebSocket từ mọi Origin. Rủi ro?

**Đáp án:** có nguy cơ **Cross-Site WebSocket Hijacking** trong những điều kiện cookie/browser cho phép. Dùng Origin allowlist khi phù hợp, authentication, SameSite/session policy và kiểm tra quyền mọi message.

### Bài G — Node B không thấy socket trên Node A

Client A ở Node 1, user B ở Node 2, ứng dụng gửi message chat từ A nhưng B không nhận. Vì sao?

**Đáp án:** socket và sessions là state trong từng process. Cần broker/pubsub để fan-out giữa nodes; durable storage/cursors nếu phải replay, không chỉ dùng static map trong mỗi JVM.

### Bài H — Java Listener chỉ nhận một message

`onOpen` gọi `request(1)`, `onText` xử lý message đầu nhưng không request tiếp. Điều gì xảy ra?

**Đáp án:** client Listener chưa cung cấp demand tiếp cho các receive callbacks; không được giả định các message còn lại tự đến callback. Quản lý `request(n)` theo tiến độ tiêu thụ/queue.

### Bài I — WebSocket server sử dụng HTTP headers trên mỗi message

Sau `101`, server cố parse từng chat message thành một `POST /send` với headers mới trên cùng upgraded socket.

**Đáp án:** sai wire protocol. Sau upgrade, hai bên trao đổi WebSocket frames/messages; “type=send” thuộc JSON/binary application protocol, không phải HTTP request framing mới.

### Bài J — Dùng server demo để nhận video

Server demo chỉ hỗ trợ FIN=1, payload <=125 byte và một message. Client gửi binary video frame vài kilobytes. Kết quả?

**Đáp án:** demo sẽ thất bại theo thiết kế, vì không hỗ trợ binary/extended lengths/fragmentation. Dùng server framework đầy đủ; với real-time video, đánh giá WebRTC/media transport thay vì ép server demo.

### Bài K — Client mất kết nối sau lệnh đặt hàng

Client gửi command ID=72, server xử lý xong nhưng ACK bị mất. Reconnect và gửi lại với ID mới có an toàn?

**Đáp án:** không chắc. WebSocket không bảo đảm exactly-once xuyên reconnect. Giữ idempotency key, kiểm tra trạng thái giao dịch và retry theo policy, tránh tạo đơn hàng đôi.

### Bài L — Slow client gây tràn RAM

Một server push 5000 events/s cho client chỉ đọc 20 events/s, dùng queue không giới hạn.

**Đáp án:** phải giới hạn queued bytes, coalesce/drop nếu nghiệp vụ cho phép, giảm tốc hoặc đóng slow clients, phối hợp với broker/replay. TCP/WebSocket không tự giải quyết application memory/backpressure.

## 16. Checklist triển khai WebSocket client và server Java

- [ ] Đã xác định bên nào **kết nối ra** (client), bên nào **lắng nghe** (server)?
- [ ] Đã biết `java.net.http.WebSocket` là **client-only** trong JDK 17?
- [ ] Với server, đã chọn Jakarta/Spring/Jetty/Netty/implementation phù hợp và cập nhật security patches?
- [ ] Có phân biệt `javax.websocket` và `jakarta.websocket`/container compatibility?
- [ ] Server implementation xử lý RFC 6455 handshake, masking, fragmentation, control frames, close và size limits?
- [ ] Không sử dụng `ServerSocket` demo làm server production?
- [ ] JDK client Listener dùng `request(n)` đúng receive demand và ghép text tới `last=true`?
- [ ] Gửi messages có coordinator/queue để bảo toàn thứ tự từng phiên?
- [ ] Có application schema version, type, requestId, ACK, validation và authorization?
- [ ] Đã chọn WSS/TLS, trust verification và Origin policy/CSWSH defense?
- [ ] Không cho phép subscription/topic trái ACL dù WebSocket đã xác thực?
- [ ] Có max message size, inbound/outbound quotas, rate limit và per-user connection limits?
- [ ] Có heartbeat Ping/Pong/idle timeout, Close cleanup và reconnect backoff/jitter?
- [ ] Có snapshot/replay/resync sau reconnect nếu dữ liệu quan trọng?
- [ ] Có broker/pubsub và durable store khi chạy nhiều server nodes?
- [ ] Có metrics về handshake errors, active connections, queued bytes, ping RTT, close codes và reconnect failures?
- [ ] Đã test malformed handshake/frame, fragmented messages, extended lengths, slow clients và oversized payload?
- [ ] Đã test rolling deploy, proxy idle timeout, mạng rớt và user logout?
- [ ] Có xem HTTP/SSE là lựa chọn đơn giản hơn khi full-duplex không cần thiết?

**Kết luận:** JDK 17 cho phép tạo **WebSocket client** trực tiếp bằng `HttpClient.newWebSocketBuilder()` và `java.net.http.WebSocket`. Nhưng server Java cần **HTTP/WebSocket server implementation** có khả năng lắng nghe, handshake, framing, bảo mật và quản lý nhiều kết nối. `ServerSocket` chỉ cung cấp TCP; `HttpServer` của JDK không tự là WebSocket server framework. Viết demo protocol giúp hiểu bản chất, còn production nên dùng một stack có kiểm thử chuẩn, sau đó xây application protocol, state, authorization, backpressure và distributed messaging trên đó.

## 17. Tài liệu API và tiêu chuẩn chính thức

- **Java 17 — WebSocket client:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html
- **Java 17 — WebSocket.Builder:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html
- **Java 17 — WebSocket.Listener:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html
- **Java 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Java 17 — HttpServer:** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- **RFC 6455 — The WebSocket Protocol:** https://www.rfc-editor.org/rfc/rfc6455
- **RFC 8441 — Bootstrapping WebSockets with HTTP/2:** https://www.rfc-editor.org/rfc/rfc8441
- **Jakarta WebSocket Specification:** https://jakarta.ee/specifications/websocket/

Đối với WebSocket server, hãy đối chiếu documentation của chính runtime/container/framework và phiên bản đang triển khai. API JDK client không tự đảm bảo khả năng hỗ trợ WebSocket server, cũng không thay thế các thử nghiệm bảo mật, proxy, reconnect và tải thật.