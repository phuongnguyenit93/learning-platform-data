# Java 11 — Timeout, subprotocol và xử lý lỗi bắt tay

**Chủ đề:** Java 11 → WebSocket. Bài học tập trung vào **timeout khi thiết lập WebSocket**, **thương lượng subprotocol** và **chẩn đoán lỗi opening handshake** bằng API `java.net.http` chuẩn từ Java 11. Nội dung dùng kiến thức hiện vẫn áp dụng trong hệ thống Java và WebSocket; tránh API `jdk.incubator.httpclient` cũ, tránh giả định API WebSocket client của JDK là một WebSocket server, và không dựa vào tính năng xuất hiện sau JDK 11.

**Mục tiêu:** Sau bài này, bạn có thể viết `HttpClient.newWebSocketBuilder()` với `connectTimeout`, đưa các subprotocol theo thứ tự ưu tiên, kiểm tra `WebSocket.getSubprotocol()` sau khi kết nối, phân biệt lỗi HTTP handshake với TLS/DNS/connect/timeout, lấy HTTP status từ `WebSocketHandshakeException.getResponse()`, kiểm soát `CompletableFuture`, và xử lý vòng đời `Listener`/close/cancel/reconnect mà không bỏ sót tài nguyên.

## 1. WebSocket handshake nằm giữa HTTP và WebSocket

WebSocket bắt đầu bằng một **opening handshake**. Với cách thiết lập WebSocket qua HTTP/1.1 theo RFC 6455, client gửi HTTP request có yêu cầu nâng cấp giao thức; server xác nhận bằng response **`101 Switching Protocols`** hợp lệ. Chỉ **sau khi handshake thành công** hai phía mới trao đổi **WebSocket frames/messages**. HTTP status của opening handshake không phải WebSocket close code.

~~~text
Java 11 WebSocket.Builder.buildAsync(ws/wss URI)
        |
        +-- DNS / proxy / TCP connect / TLS (nếu wss)
        |
        v
  HTTP WebSocket opening handshake
        |
        +-- 101 + Upgrade/Connection/Sec-WebSocket-Accept hợp lệ
        |            |
        |            v
        |     buildAsync hoàn thành với WebSocket
        |     getSubprotocol() phản ánh lựa chọn thực tế
        |     Listener.onOpen → nhận/gửi WebSocket messages
        |
        +-- 401/403/404/426 hoặc 101 sai/missing headers
        |            |
        |            v
        |     buildAsync hoàn thành lỗi
        |     có thể là WebSocketHandshakeException
        |
        +-- connect/TLS/timeout/I/O thất bại
                     |
                     v
              Không có WebSocket đã kết nối
~~~

Sơ đồ trên chỉ mô tả các nhánh thường gặp. `101` **một mình không đủ**: server còn phải trả header `Upgrade: websocket`, `Connection: Upgrade`, `Sec-WebSocket-Accept` tính đúng từ `Sec-WebSocket-Key`, cùng các điều kiện protocol khác. Response `200 OK` là HTTP response bình thường, **không phải** WebSocket handshake thành công.

**Phân biệt ba giai đoạn lỗi:**

1. **Trước handshake:** DNS, TCP connect, proxy, TLS/certificate hay chính sách truy cập không cho tiến tới HTTP response.
2. **Trong handshake:** có phản hồi HTTP nhưng nâng cấp không hợp lệ/bị từ chối, chẳng hạn `403`, `404`, `401` hoặc server không trả `101`.
3. **Sau handshake:** WebSocket đã mở nhưng message, network, idle, close frame hoặc xử lý listener phát sinh lỗi. Những lỗi này **không nên** được báo nhầm thành “handshake failed”.

## 2. API WebSocket client chuẩn trong Java 11

JDK 11 có API `java.net.http` (JEP 321):

| Kiểu/phương thức | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `HttpClient.newWebSocketBuilder()` | Tạo builder WebSocket từ client đã cấu hình. | Chỉ tạo builder; chưa mở kết nối. |
| `WebSocket.Builder.connectTimeout(Duration)` | Giới hạn thời gian thiết lập WebSocket. | Đây là **connection/handshake timeout**, không phải idle timeout suốt vòng đời. |
| `WebSocket.Builder.subprotocols(String, String...)` | Gửi danh sách subprotocol theo thứ tự ưu tiên. | Không buộc server chọn phần tử đầu tiên. |
| `WebSocket.Builder.header(name, value)` | Thêm HTTP header ứng dụng cho handshake. | Không được tự ghi các header thuộc WebSocket Protocol. |
| `WebSocket.Builder.buildAsync(uri, listener)` | Khởi tạo handshake và kết nối bất đồng bộ. | Trả `CompletableFuture<WebSocket>`; thành công hoặc lỗi. |
| `WebSocket.getSubprotocol()` | Lấy subprotocol đã thương lượng. | Trả **chuỗi rỗng** khi không có subprotocol. |
| `WebSocket.Listener` | Nhận `onOpen`, text/binary/ping/pong/close/error. | `onError` sau kết nối khác với failure của `buildAsync`. |
| `WebSocket.sendText/sendBinary/sendPing/sendClose` | Gửi frame/message hoặc bắt đầu đóng. | Mỗi send trả future riêng; cần quản lý lỗi và hoàn tất. |
| `WebSocket.abort()` | Đóng input/output **đột ngột**. | Chỉ dùng khi muốn hủy ngay; không phải đóng êm. |

Các import cơ bản:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpResponse;
import java.net.http.WebSocket;
import java.net.http.WebSocketHandshakeException;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
~~~

Đây chỉ là phần **import minh họa**; một chương trình đầy đủ có ở mục 9. Java SE 11 chuẩn chỉ cung cấp **WebSocket client** thông qua những API này; `com.sun.net.httpserver.HttpServer` của JDK không biến thành WebSocket server đầy đủ chỉ bằng `createContext`.

### 2.1. WebSocket URI khác HTTP URI

- `ws://host/path`: WebSocket qua kết nối không mã hóa TLS; chủ yếu phù hợp với localhost, mạng test được kiểm soát hoặc môi trường cụ thể được phép.
- `wss://host/path`: WebSocket qua TLS, thường là lựa chọn cho môi trường production có dữ liệu/credential cần bảo vệ.
- `https://...` là HTTP URI, **không phải** URI WebSocket truyền vào `buildAsync`. Dùng `wss://` khi server mong WebSocket over TLS.
- HTTP/1.1 upgrade của RFC 6455 khác thương lượng HTTP/2 ALPN. Đừng nhầm `wss` với một lời hứa ứng dụng chạy HTTP/2, và đừng tự thêm các header H2 để ép WebSocket handshake.

Lấy endpoint từ cấu hình đáng tin cậy, không từ chuỗi người dùng tùy ý. Với endpoint có authentication, tránh đưa token vào query string vì dễ rò rỉ trong log, browser history và observability.

## 3. Timeout khi bắt tay: `connectTimeout(Duration)`

Ví dụ đặt thời gian tối đa để **thiết lập** WebSocket:

~~~java
HttpClient client = HttpClient.newHttpClient();

CompletableFuture<WebSocket> opening =
    client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .buildAsync(
            URI.create("wss://ws.example.test/events"),
            new WebSocket.Listener() {});
~~~

Đây là **đoạn minh họa**: `ws.example.test` chỉ là tên dành cho tài liệu, không phải endpoint được xác nhận. Java 11 `WebSocket.Builder.connectTimeout` nhận một `Duration` **lớn hơn 0**; không đặt giá trị thì builder giả định **timeout vô hạn** cho giai đoạn thiết lập. Khi không thiết lập kết nối trước hạn, future có thể hoàn thành lỗi với `HttpTimeoutException`.

**Phạm vi timeout này rất quan trọng:** implementation WebSocket của JDK 11 tính timeout cho toàn bộ giai đoạn connection, bao gồm cả WebSocket opening handshake và TLS handshake theo tài liệu. Điều này không có nghĩa timeout đó sẽ theo dõi mọi lần `onText`, mọi lần `sendText`, mọi giây không nhận frame hoặc thời lượng tồn tại của WebSocket sau khi đã kết nối.

### 3.1. Ba loại hạn thời gian khác nhau

| Loại thời gian | Giai đoạn | Cách áp dụng |
| --- | --- | --- |
| **Handshake/connect timeout** | Từ khi bắt đầu kết nối đến khi `buildAsync` thiết lập được WebSocket. | `WebSocket.Builder.connectTimeout(Duration)`. |
| **Thời hạn chờ của code gọi future** | Caller không muốn chờ lâu hơn N giây để quan sát kết quả. | `future.get(N, TimeUnit.SECONDS)`; có thể ném `TimeoutException` ở caller. |
| **Idle/heartbeat/message deadline** | Sau kết nối, chờ event, pong hoặc response nghiệp vụ quá lâu. | Tự quản lý bằng lịch/supervisor có giới hạn, ping/pong hay deadline ứng dụng. |

Hai mục đầu cũng **không đồng nhất**: `future.get(7, SECONDS)` chỉ giới hạn **thời gian thread caller chờ**. Khi nó ném `TimeoutException`, không tự suy rằng WebSocket handshake của JDK đã ném `HttpTimeoutException`. Future có thể vẫn đang chạy; nếu bỏ chờ, cần chính sách cancellation, kiểm trạng thái và cleanup.

~~~java
CompletableFuture<WebSocket> future = client.newWebSocketBuilder()
    .connectTimeout(Duration.ofSeconds(5))
    .buildAsync(uri, listener);

try {
    WebSocket socket = future.get(7, TimeUnit.SECONDS);
    use(socket);
} catch (TimeoutException e) {
    future.cancel(true);
    reportWaitDeadline(e);
} catch (ExecutionException e) {
    reportHandshakeCause(e.getCause());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    future.cancel(true);
    reportInterrupted(e);
}
~~~

Đây là **đoạn minh họa**, `uri` và `listener` đã được xác định, các hàm `use/report...` là hàm ứng dụng; cần import `ExecutionException`, `TimeUnit`, `TimeoutException` và các lớp trên. **Cancellation của future không bảo đảm ngay lập tức mọi socket/việc đang chạy đã ngừng**; quản lý vòng đời theo client/framework, đóng/abort kết nối nếu sau đó vẫn nhận được kết quả và không còn cần nó.

### 3.2. Không dùng sleep để “xác định chắc chắn lỗi timeout”

Một test trì hoãn response của test server có thể giúp tái hiện handshake timeout; tuy nhiên thời điểm scheduler/GC/CPU có thể làm test thiếu ổn định. Nên dùng server fixture có cờ xác nhận đã **nhận request nhưng chưa trả handshake**, đặt thời hạn đủ rộng và assert **loại kết quả nghiệp vụ** là failed/no-socket. Khi cần assert chính xác `HttpTimeoutException`, chạy trong môi trường có timeout/độ trễ kiểm soát; tránh dựa vào exception message hoặc số mili-giây tuyệt đối.

## 4. Subprotocol không phải phiên bản WebSocket, không phải extension

**Subprotocol** là thỏa thuận tên giao thức **ở tầng ứng dụng** sẽ chạy bên trong WebSocket messages. Ví dụ một sản phẩm có thể định nghĩa `events.v2`, `events.v1`, hoặc giao thức phổ biến như `graphql-transport-ws` tùy server thực sự hỗ trợ. Tên subprotocol phải là token hợp lệ; Java không tự hiểu nội dung JSON, protobuf hay schema của những tên đó.

Khi builder gọi:

~~~java
WebSocket.Builder builder = client.newWebSocketBuilder()
    .subprotocols("events.v2", "events.v1");
~~~

Client gửi danh sách ưu tiên trong opening handshake, tương đương ý tưởng:

~~~http
Sec-WebSocket-Protocol: events.v2, events.v1
~~~

Server có thể chọn **tối đa một** subprotocol được phía client đề nghị, chẳng hạn `events.v1`, nếu đó là giao thức nó hỗ trợ. Không có cam kết server buộc phải chọn `events.v2` chỉ vì nó đứng đầu. Nếu server **không chọn** subprotocol, handshake vẫn có thể thành công về mặt WebSocket nhưng `getSubprotocol()` sẽ trả **`""`**.

~~~java
WebSocket socket = builder.buildAsync(uri, listener).join();
String negotiated = socket.getSubprotocol();

if (!"events.v2".equals(negotiated)
        && !"events.v1".equals(negotiated)) {
    socket.sendClose(WebSocket.NORMAL_CLOSURE,
                     "Unsupported subprotocol");
    throw new IllegalStateException(
        "No supported subprotocol negotiated");
}
~~~

Đây là **đoạn minh họa**; `uri`/`listener` đã có, và trong hệ thống thực cần quản lý future trả bởi `sendClose`, chờ đóng/cleanup với deadline. `join()` có thể bọc lỗi handshake trong `CompletionException`, cần phân loại nguyên nhân. Nếu WebSocket đã kết nối nhưng ứng dụng đòi một subprotocol cụ thể mà không có, đó là **lỗi hợp đồng ứng dụng sau handshake**, không mặc nhiên là `WebSocketHandshakeException`.

### 4.1. Những điều không nên làm với subprotocol

- **Không tự thêm header `Sec-WebSocket-Protocol` qua `builder.header(...)`**; đó là WebSocket protocol header, Java 11 cung cấp `subprotocols(...)` riêng và cấm ghi thủ công các header được định nghĩa trong protocol.
- **Không nhầm với `Sec-WebSocket-Version: 13`**: con số 13 là phiên bản giao thức WebSocket trong RFC 6455, khác `events.v1`/`events.v2` là version của hợp đồng nghiệp vụ.
- **Không nhầm với `Sec-WebSocket-Extensions`**: extension như permessage-deflate tác động đến cách vận chuyển dữ liệu, còn subprotocol quy định semantics của messages. Builder Java 11 không có lời hứa sẽ tự hỗ trợ extension theo mọi server.
- **Không dùng tên subprotocol để thay thế authentication**. Một tên “admin.v1” không chứng minh người dùng có quyền admin; cần xác thực/phân quyền độc lập.
- **Không cho server trả một tên chưa từng được offer rồi chấp nhận im lặng**. HTTP client có thể từ chối handshake không hợp lệ; ứng dụng vẫn nên kiểm tra negotiated value có phù hợp hợp đồng.
- **Không coi thứ tự do client gửi là luật bắt buộc server ưu tiên**. Khi cần phiên bản tối thiểu, thiết kế chính sách version/khả năng tương thích rõ ràng.

### 4.2. Ví dụ ma trận thương lượng

| Client gửi | Server thực tế chọn | Kết quả ở client |
| --- | --- | --- |
| `events.v2, events.v1` | `events.v2` | Handshake thành công, `getSubprotocol()=="events.v2"`. |
| `events.v2, events.v1` | `events.v1` | Handshake thành công, phải quyết định app có chấp nhận v1 không. |
| `events.v2` | Không chọn gì | Có thể mở WebSocket, `getSubprotocol().isEmpty()`. |
| `events.v2` | `chat.v1` (không được offer) | Handshake không hợp lệ, client phải từ chối. |
| Không gọi `subprotocols` | Không chọn gì | WebSocket không có subprotocol; dùng giao thức ngầm định chỉ khi hai phía đã thống nhất. |

**Khi đổi version của message schema:** server/client phải cùng hiểu version thực sự được chọn. Nếu có cả `events.v1` và `events.v2`, đừng phát JSON v2 sau khi handshake đã chọn v1; lỗi này vẫn có thể xuất hiện dù TCP và WebSocket hoàn toàn bình thường.

## 5. Lỗi opening handshake: `WebSocketHandshakeException`

JDK 11 cung cấp `java.net.http.WebSocketHandshakeException`, lớp con của `IOException`. Exception này báo **opening handshake thất bại** và có `getResponse()` trả về `HttpResponse<?>` của phía server (nếu có). Từ response đó đọc được HTTP status/headers nhằm tìm nguyên nhân.

~~~java
try {
    WebSocket ws = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .buildAsync(uri, listener)
        .get(7, TimeUnit.SECONDS);
    onConnected(ws);
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    if (cause instanceof WebSocketHandshakeException) {
        WebSocketHandshakeException handshake =
            (WebSocketHandshakeException) cause;
        HttpResponse<?> reply = handshake.getResponse();
        if (reply != null) {
            System.out.println(
                "Handshake rejected, HTTP " + reply.statusCode());
        } else {
            System.out.println("Handshake rejected, response unavailable");
        }
    } else {
        reportOtherConnectFailure(cause);
    }
}
~~~

Đây là **đoạn minh họa**, chỉ bắt `ExecutionException` để tập trung vào lỗi handshake. Code đầy đủ vẫn phải xử lý `InterruptedException` và `TimeoutException`; `client`/`uri`/`listener` và các hàm `onConnected/report...` do ứng dụng khai báo. `getResponse()` có thể là `null` theo tài liệu (đặc biệt khi exception được serialize/deserialized), vì vậy kiểm trước khi dùng.

Khi dùng `join()` thay cho `get()`, lỗi thường được bọc vào `CompletionException`. Không chỉ catch `WebSocketHandshakeException` trực tiếp quanh `join()` mà bỏ qua wrapper.

### 5.1. Mã HTTP thường gặp và hướng chẩn đoán

| Status/kết quả | Ý nghĩa có thể có | Hướng xử lý |
| --- | --- | --- |
| `101` + handshake headers hợp lệ | Nâng cấp thành WebSocket thành công. | Dùng WebSocket và kiểm `getSubprotocol()`. |
| `200` | Endpoint đang trả HTTP thông thường, không Upgrade. | Kiểm URI/path, route/load balancer và server WS. |
| `301/302/307/308` | Endpoint chuyển hướng HTTP. | Kiểm URL/gateway; không tự giả định redirect được theo hoặc có thể forward credentials an toàn. |
| `400` | Request/headers không hợp lệ theo server. | Đối chiếu schema/version/policy server. |
| `401` | Chưa xác thực/credentials không hợp lệ. | Quy trình xác thực, refresh credential có giới hạn. |
| `403` | Server từ chối theo quyền/chính sách/Origin. | Kiểm access control/allowlist, không retry liên tục. |
| `404` | Path không ánh xạ WebSocket endpoint. | Kiểm URI, reverse proxy route, deploy/config. |
| `407` | Proxy yêu cầu xác thực. | Kiểm ProxySelector/Authenticator và môi trường. |
| `426` | Server đề nghị nâng cấp/thay đổi giao thức. | Đọc headers/hợp đồng, không kết luận tự động sửa bằng một request lặp. |
| `502/503/504` | Gateway/service không sẵn sàng hoặc timeout. | Retry có hạn mức/backoff chỉ khi phù hợp. |
| Không có `HttpResponse` | DNS, TCP, TLS, timeout hoặc lỗi I/O trước HTTP response. | Phân loại cause, không tự tạo “status=500”. |

Các mã ở bảng là **gợi ý điều tra**, không khẳng định một status chỉ có đúng một nguyên nhân. Ví dụ `403` không nhất thiết do TLS; `401` không chứng minh token hết hạn nếu không có thêm dữ kiện. Server có thể trả `101` nhưng `Sec-WebSocket-Accept` sai, khi đó handshake vẫn thất bại.

### 5.2. Khi HTTP handshake lỗi, Listener có gọi onError không?

`buildAsync(...)` trả một `CompletableFuture<WebSocket>`. **Nếu opening handshake thất bại**, future hoàn thành exceptionally và **không có WebSocket đã mở** để ứng dụng dùng. Đừng đặt toàn bộ logic lỗi handshake chỉ trong `WebSocket.Listener.onError`: callback đó dành cho lỗi **sau khi WebSocket đã kết nối/đã `onOpen`**, còn lỗi handshake cần xử lý **ở future xây dựng**.

Một số lỗi sau kết nối có thể dẫn đến `onError` thay vì `onClose`; không dựa vào giả định lúc nào cả hai cũng được gọi. Mỗi giai đoạn có cách ghi nhận trạng thái khác nhau.

## 6. Timeout không đồng nghĩa server từ chối handshake

Phân biệt những exception thường được nhìn thấy qua cause của future:

| Nhóm | Dấu hiệu Java | Có HTTP status để kiểm? |
| --- | --- | --- |
| HTTP handshake bị từ chối/sai | `WebSocketHandshakeException` | Có thể đọc từ `getResponse()`. |
| Thiết lập kéo dài quá `connectTimeout` | `HttpTimeoutException` | Không nhất thiết có HTTP response. |
| DNS/connect/đường truyền lỗi | `IOException` và nguyên nhân phía dưới | Thường không có status. |
| TLS/certificate fail trên `wss://` | `SSLHandshakeException`/`SSLException`, thường trong nhánh I/O | Thường không có HTTP response. |
| Thread caller chờ quá `future.get(timeout)` | `TimeoutException` ngay ở caller | Không phải một HTTP handshake response. |
| Caller bị interrupt | `InterruptedException` từ `get` | Phải bảo toàn interrupted flag và cleanup. |
| Builder/URI/subprotocol không hợp lệ | `IllegalArgumentException` (có thể synchronous hoặc future) | Lỗi đầu vào, không phải server reject. |
| WebSocket đang mở rồi mới mất kết nối | `Listener.onError`/future send thất bại | Không phải lỗi opening handshake. |

Mẫu xử lý không phụ thuộc message string:

~~~java
static String category(Throwable error) {
    if (error instanceof WebSocketHandshakeException) {
        return "HANDSHAKE_REJECTED";
    }
    if (error instanceof java.net.http.HttpTimeoutException) {
        return "HANDSHAKE_TIMEOUT";
    }
    if (error instanceof javax.net.ssl.SSLException) {
        return "TLS_ERROR";
    }
    if (error instanceof java.io.IOException) {
        return "CONNECT_IO_ERROR";
    }
    return "OTHER_ERROR";
}
~~~

Đây là một **method Java minh họa độc lập về logic**, có thể đặt trong class có các import tương ứng. Trong thực tế các lỗi có thể được bọc bằng `ExecutionException`/`CompletionException`, nên phải **unwrap cause đúng số tầng** trước khi phân loại; không duyệt cause vô hạn nếu có chu trình, và giữ toàn bộ chain cho log nội bộ an toàn.

### 6.1. Không tắt kiểm tra chứng chỉ để “sửa WebSocket timeout”

Với `wss://`, certificate không tin cậy, hostname mismatch, SNI/trust store sai hoặc proxy TLS can thiệp có thể gây lỗi TLS. Cách sửa là kiểm certificate chain, host, trust store, thời gian hệ thống và proxy theo chính sách bảo mật. **Không** thiết lập trust-all SSLContext hay tắt hostname verification trong production để thử cho qua handshake; điều đó tạo rủi ro MITM.

## 7. Header handshake: cho phép ứng dụng nhưng không giành quyền protocol

Có thể cần thêm header xác thực ứng dụng, ví dụ:

~~~java
WebSocket.Builder b = client.newWebSocketBuilder()
    .connectTimeout(Duration.ofSeconds(5))
    .header("Authorization", "Bearer " + accessToken)
    .subprotocols("events.v2", "events.v1");
~~~

Đây là **đoạn minh họa**, `accessToken` là token đã lấy an toàn từ hệ thống quản lý credential; không hard-code token, không in vào log, không đặt URI/redirect thiếu kiểm soát. Builder cho phép **additional HTTP headers**, nhưng cấm tự thêm các header được định nghĩa trong WebSocket Protocol, chẳng hạn `Upgrade`, `Connection`, `Sec-WebSocket-Key`, `Sec-WebSocket-Version` và `Sec-WebSocket-Protocol`.

Những header WebSocket bắt buộc do implementation tạo và kiểm tra. Tự sinh `Sec-WebSocket-Key` hoặc tự tính `Sec-WebSocket-Accept` trong **production client** không cần thiết; phần server raw local ở mục demo chỉ làm việc đó để **mô phỏng handshake** có thể kiểm soát.

**Authorization vs subprotocol:** subprotocol là tên giao thức nghiệp vụ; không mang quyền truy cập. Server vẫn phải xác thực, kiểm tra Origin/chính sách và phân quyền trước khi cho phép những message nhạy cảm. Nếu server trả `401`, không tự gửi vô hạn với token cũ; dùng chính sách refresh credential có giới hạn và bảo vệ bí mật.

## 8. Vòng đời listener: onOpen, onError, onClose và demand

Sau khi `buildAsync` thành công, một `WebSocket.Listener` nhận callbacks:

~~~java
WebSocket.Listener listener = new WebSocket.Listener() {
    private final StringBuilder partial = new StringBuilder();

    @Override
    public void onOpen(WebSocket socket) {
        socket.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket socket, CharSequence part, boolean last) {
        partial.append(part);
        if (last) {
            handleCompleteMessage(partial.toString());
            partial.setLength(0);
        }
        socket.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onClose(
            WebSocket socket, int status, String reason) {
        recordClose(status, reason);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public void onError(WebSocket socket, Throwable error) {
        recordFailure(error);
    }
};
~~~

Đây là **đoạn minh họa**, `handleCompleteMessage`, `recordClose`, `recordFailure` là hàm ứng dụng; cần import `java.util.concurrent.CompletionStage`/`CompletableFuture`. Trong production, đặt giới hạn tổng ký tự khi ghép `partial`, không tích lũy thông điệp vô hạn. Nếu xử lý message bất đồng bộ, trả `CompletionStage` tương ứng để quản lý vòng đời dữ liệu an toàn.

Điểm cần nhớ từ contract Java 11:

- `onOpen` chỉ đến khi WebSocket đã kết nối; implementation mặc định của `onOpen` gọi `request(1)`, nhưng nếu **override**, phải chủ động gọi để nhận callbacks.
- `request(1)` yêu cầu **một lần gọi receive callback**, **không phải một message hoàn chỉnh**. Một text message có thể được giao nhiều lần với `last=false` rồi `last=true`.
- `onText`/`onBinary`/`onPing`/`onPong` cần dùng `request(n)` để nhận tiếp; nếu chỉ request một lần và không tiếp tục, stream có thể trông như “bị treo” dù handshake thành công.
- `onClose` là sự kiện nhận Close message; WebSocket input đã đóng. `onError` là sự kiện lỗi và kết thúc callbacks; đừng coi mọi `onError` là một HTTP status lỗi handshake.
- Implementation sẽ tự xử lý Pong trả lời cho Ping được nhận theo protocol; `sendPing` hoàn tất nghĩa là frame Ping đã gửi, **không chứng minh** một Pong tương ứng đã nhận. Theo dõi `onPong` và deadline riêng nếu cần heartbeat.
- `Listener` callbacks có trình tự bảo đảm **trên một WebSocket**, nhưng nếu dùng chung một listener cho nhiều WebSocket, callbacks của các socket khác nhau có thể xen kẽ. Cần tránh shared mutable state không đồng bộ.

### 8.1. Đóng êm và hủy gấp khác nhau

~~~java
socket.sendClose(WebSocket.NORMAL_CLOSURE, "bye")
    .whenComplete((s, error) -> {
        if (error != null) {
            reportSendCloseFailure(error);
        }
    });
~~~

Đây là **đoạn minh họa**; `reportSendCloseFailure` do ứng dụng cung cấp. `sendClose` mở quá trình đóng êm, trả future khi thao tác gửi hoàn thành, **không tự bảo đảm peer đã phản hồi và mọi tài nguyên đã được thu hồi ngay lúc future hoàn thành**. Cần chờ `onClose`/lifecycle với timeout hợp lý nếu nghiệp vụ đòi đóng handshake hoàn chỉnh.

`socket.abort()` đóng input/output đột ngột; dùng khi kết nối hỏng, quá deadline hoặc ứng dụng phải hủy ngay. Nó không mang ý nghĩa một close frame đã được phía bên kia nhận. Đừng báo “đóng bình thường” khi thực chất gọi abort.

## 9. Demo Java 11 hoàn chỉnh: subprotocol thành công và handshake HTTP 403

Demo sau cố ý dùng **ServerSocket raw tại loopback** để kiểm soát từng byte HTTP upgrade handshake. Fixture có hai nhánh:

1. Server nhận `Sec-WebSocket-Key`, tính `Sec-WebSocket-Accept` theo RFC 6455 và trả **101** cùng subprotocol đã được client đề nghị: `demo.v1`. WebSocket client kiểm `getSubprotocol()`.
2. Server trả **403 Forbidden** thay vì nâng cấp; `buildAsync` hoàn thành lỗi. Client mở `WebSocketHandshakeException` và đọc `getResponse().statusCode()`.

Server raw này **chỉ mô phỏng opening handshake**; nó không triển khai đầy đủ WebSocket frames, ping/pong hay message loop. Vì vậy demo chủ động `abort()` sau khi kiểm subprotocol, **không gửi message ứng dụng**. Không dùng fixture này làm server production.

Lưu thành file **`WebSocketHandshakeDemo.java`**:

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
import java.net.http.HttpResponse;
import java.net.http.WebSocket;
import java.net.http.WebSocketHandshakeException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class WebSocketHandshakeDemo {
    private static final String GUID =
        "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

    private WebSocketHandshakeDemo() {
    }

    static String readRequestHeaders(InputStream in)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        byte[] end = {13, 10, 13, 10};
        int matched = 0;

        while (bytes.size() < 16384) {
            int value = in.read();
            if (value == -1) {
                throw new EOFException("Incomplete HTTP request");
            }
            bytes.write(value);
            matched = value == end[matched]
                ? matched + 1 : (value == 13 ? 1 : 0);
            if (matched == end.length) {
                return new String(
                    bytes.toByteArray(), StandardCharsets.US_ASCII);
            }
        }
        throw new IOException("Request headers too large");
    }

    static String headerValue(String request, String name) {
        for (String line : request.split("\r\n")) {
            int colon = line.indexOf(':');
            if (colon > 0 && line.substring(0, colon)
                    .equalsIgnoreCase(name)) {
                return line.substring(colon + 1).trim();
            }
        }
        return null;
    }

    static String webSocketAccept(String key) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-1").digest(
            (key + GUID).getBytes(StandardCharsets.US_ASCII));
        return Base64.getEncoder().encodeToString(hash);
    }

    static final class Fixture implements AutoCloseable {
        private final ServerSocket server;
        private final CountDownLatch release = new CountDownLatch(1);
        private final AtomicReference<Throwable> failure =
            new AtomicReference<>();
        private final Thread thread;

        Fixture(boolean accept) throws IOException {
            server = new ServerSocket(0, 1,
                InetAddress.getByName("127.0.0.1"));
            server.setSoTimeout(5000);

            thread = new Thread(() -> {
                try (Socket peer = server.accept()) {
                    peer.setSoTimeout(5000);
                    String request =
                        readRequestHeaders(peer.getInputStream());
                    OutputStream out = peer.getOutputStream();
                    if (accept) {
                        String key = headerValue(
                            request, "Sec-WebSocket-Key");
                        String offered = headerValue(
                            request, "Sec-WebSocket-Protocol");
                        if (key == null || offered == null
                                || !offered.contains("demo.v1")) {
                            throw new IOException("Missing WS headers");
                        }

                        String response =
                            "HTTP/1.1 101 Switching Protocols\r\n" +
                            "Upgrade: websocket\r\n" +
                            "Connection: Upgrade\r\n" +
                            "Sec-WebSocket-Accept: " +
                                webSocketAccept(key) + "\r\n" +
                            "Sec-WebSocket-Protocol: demo.v1\r\n\r\n";
                        out.write(response.getBytes(
                            StandardCharsets.US_ASCII));
                        out.flush();

                        release.await(5, TimeUnit.SECONDS);
                    } else {
                        String response =
                            "HTTP/1.1 403 Forbidden\r\n" +
                            "Content-Length: 0\r\n" +
                            "Connection: close\r\n\r\n";
                        out.write(response.getBytes(
                            StandardCharsets.US_ASCII));
                        out.flush();
                    }
                } catch (Throwable e) {
                    failure.set(e);
                }
            }, "local-ws-handshake-fixture");

            thread.setDaemon(true);
            thread.start();
        }

        URI uri() {
            return URI.create("ws://127.0.0.1:" +
                server.getLocalPort() + "/socket");
        }

        @Override
        public void close() throws Exception {
            release.countDown();
            server.close();
            thread.join(3000);
            if (thread.isAlive()) {
                throw new IllegalStateException(
                    "Fixture thread did not stop");
            }
            if (failure.get() != null) {
                throw new IOException(
                    "Fixture failed", failure.get());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .build();

        try (Fixture good = new Fixture(true)) {
            WebSocket socket = client.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .subprotocols("demo.v1", "demo.v2")
                .buildAsync(good.uri(), new WebSocket.Listener() {})
                .get(5, TimeUnit.SECONDS);

            try {
                if (!"demo.v1".equals(socket.getSubprotocol())) {
                    throw new AssertionError(
                        "Wrong subprotocol");
                }
                System.out.println(
                    "selected=" + socket.getSubprotocol());
            } finally {
                socket.abort(); // Chỉ dành cho fixture raw.
            }
        }

        try (Fixture forbidden = new Fixture(false)) {
            try {
                WebSocket socket = client.newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .buildAsync(forbidden.uri(),
                                new WebSocket.Listener() {})
                    .get(5, TimeUnit.SECONDS);
                socket.abort();
                throw new AssertionError(
                    "Handshake should have failed");
            } catch (ExecutionException e) {
                Throwable cause = e.getCause();
                if (!(cause instanceof
                        WebSocketHandshakeException)) {
                    throw e;
                }
                HttpResponse<?> response =
                    ((WebSocketHandshakeException) cause)
                        .getResponse();
                if (response == null
                        || response.statusCode() != 403) {
                    throw new AssertionError(
                        "Expected HTTP 403");
                }
                System.out.println(
                    "rejected.status=" + response.statusCode());
            }
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 11**, không cần dependency và không cần Internet:

~~~bash
javac --release 11 -encoding UTF-8 WebSocketHandshakeDemo.java
java WebSocketHandshakeDemo
~~~

**Stdout chính xác trong điều kiện loopback được phép và fixture hoạt động bình thường:**

~~~text
selected=demo.v1
rejected.status=403
~~~

**Giải thích:**

1. Fixture mở một `ServerSocket` tại `127.0.0.1` với port 0; OS cấp cổng trống. Client gửi `ws://` trên loopback, không dùng HTTPS hay Internet.
2. `readRequestHeaders` đọc đến `\r\n\r\n` và chặn input quá 16 KiB để tránh chờ vô hạn hoặc đọc request lỗi quá lớn trong test.
3. Khi accept, server lấy `Sec-WebSocket-Key` do Java client tạo, nối với GUID cố định của RFC 6455, áp dụng SHA-1 và Base64 để tạo `Sec-WebSocket-Accept`. SHA-1 ở đây **là phép tính bắt buộc của WebSocket handshake**, không phải khuyến nghị dùng SHA-1 để băm password hay ký dữ liệu bảo mật.
4. Server chọn đúng `demo.v1` có trong danh sách client đề nghị, nên `getSubprotocol()` bằng `demo.v1`. Danh sách được xếp theo ưu tiên nhưng server vẫn là bên chọn.
5. Nhánh 403 trả HTTP response mà **không hoàn thành upgrade**. Future `buildAsync` thất bại; `get(...)` bọc nguyên nhân trong `ExecutionException`; chương trình kiểm kiểu `WebSocketHandshakeException` và đọc status thật.
6. `Fixture.close()` giải phóng server, thread và socket; có cờ `failure` để không che lỗi phía fixture. `socket.abort()` kết thúc kết nối thử nghiệm vì fixture không xử lý các frame WS thật; sản phẩm thực nên dùng close handshake êm khi có thể.
7. Chương trình không test TLS, proxy, timeout khi server im lặng hoặc subprotocol mismatch; các trường hợp đó cần fixture riêng ở cấp integration test.
8. Nếu OS cấm tạo socket loopback, thread fixture timeout hoặc network bị can thiệp, chương trình có thể fail trước khi in đủ stdout. Không gán output cố định cho trường hợp không đạt điều kiện chạy bình thường.

**Lưu ý bảo mật:** Raw fixture trên chỉ chứng minh handshake ở mức giáo dục; nó không validate mọi header, kiểm Origin, authentication, WebSocket frames, frame masking, kích thước message hoặc close handshake. Không copy nó thành WebSocket server production.

## 10. Kiểm thử với JUnit Jupiter 5.x

Có thể tái sử dụng fixture ở mục 9 để tạo integration tests **không phụ thuộc Internet**. Đặt class dưới đây trong file **`WebSocketHandshakeDemoTest.java`** cùng package với demo, đã cấu hình JUnit Jupiter 5.x tương thích Java 11 và test runner của Maven/Gradle. JUnit không nằm sẵn trong Java SE.

~~~java
import java.net.http.HttpClient;
import java.net.http.HttpResponse;
import java.net.http.WebSocket;
import java.net.http.WebSocketHandshakeException;
import java.time.Duration;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class WebSocketHandshakeDemoTest {
    @Test
    void selectedSubprotocolIsVisible() throws Exception {
        try (WebSocketHandshakeDemo.Fixture fixture =
                 new WebSocketHandshakeDemo.Fixture(true)) {
            HttpClient client = HttpClient.newHttpClient();
            WebSocket socket = client.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .subprotocols("demo.v1", "demo.v2")
                .buildAsync(fixture.uri(),
                    new WebSocket.Listener() {})
                .get(5, TimeUnit.SECONDS);
            try {
                assertEquals("demo.v1", socket.getSubprotocol());
            } finally {
                socket.abort();
            }
        }
    }

    @Test
    void refusedUpgradeExposesHttpStatus() throws Exception {
        try (WebSocketHandshakeDemo.Fixture fixture =
                 new WebSocketHandshakeDemo.Fixture(false)) {
            HttpClient client = HttpClient.newHttpClient();
            ExecutionException error = assertThrows(
                ExecutionException.class,
                () -> client.newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .buildAsync(fixture.uri(),
                        new WebSocket.Listener() {})
                    .get(5, TimeUnit.SECONDS));

            assertTrue(error.getCause() instanceof
                WebSocketHandshakeException);
            HttpResponse<?> response =
                ((WebSocketHandshakeException) error.getCause())
                    .getResponse();
            assertNotNull(response);
            assertEquals(403, response.statusCode());
        }
    }
}
~~~

Hai test chứng minh **bên nào chọn subprotocol** và **cách lấy status lỗi handshake từ WebSocketHandshakeException**, không dựa vào mạng công cộng. Khi chạy với build tool, bảo đảm module `java.net.http` được phép dùng, test runner JUnit đúng target Java 11 và tài nguyên loopback được mở.

### 10.1. Ma trận test mở rộng

| Case | Fixture | Điều phải kiểm tra |
| --- | --- | --- |
| Valid 101 + chosen offered protocol | Server chọn `demo.v1` | Future thành công, `getSubprotocol()=="demo.v1"`. |
| Valid 101 nhưng không chọn protocol | Server không trả `Sec-WebSocket-Protocol` | `getSubprotocol().isEmpty()`; app quyết định có chấp nhận. |
| 403 Forbidden | HTTP 403, không upgrade | Future thất bại với `WebSocketHandshakeException` và status 403. |
| 404 path lỗi | HTTP 404 | Báo đúng HTTP status, không giả định lỗi DNS. |
| 101 nhưng accept value sai | HTTP 101 + `Sec-WebSocket-Accept` sai | Handshake bị từ chối vì không hợp lệ, không tạo WebSocket thành công. |
| Server chọn protocol không được offer | `Sec-WebSocket-Protocol: unknown.v1` | Handshake không hợp lệ; app không dùng WebSocket. |
| Server im lặng sau request | Server nhận request nhưng không trả HTTP response | `connectTimeout`/deadline khiến attempt thất bại, fixture cleanup. |
| Kết nối TCP bị từ chối | Port không có listener | Lỗi connect/I/O, không tự bịa HTTP 403. |
| TLS certificate không tin | WSS fixture với chain không được trust | Lỗi TLS; không disable kiểm chứng chỉ. |
| Bắt tay thành công nhưng server đóng ngay | Server gửi WebSocket close/error sau 101 | Listener lifecycle, không phân loại là HTTP 403. |
| Client cancel trong lúc bắt tay | Future bị hủy trước 101 | Không giữ tài nguyên/không báo socket connected giả. |
| Idle timeout sau kết nối | Server kết nối hợp lệ nhưng không phát event | App heartbeat/deadline, không dùng `connectTimeout` làm đồng hồ idle. |

### 10.2. Tránh test timeout bị flaky

Đối với test server im lặng, dùng `CountDownLatch` xác nhận server đã **nhận HTTP headers**, sau đó giữ kết nối mở quá handshake deadline. Đặt test timeout rộng đủ cho CI; nếu timeout có thể do fixture chưa khởi tạo, báo lỗi fixture thay vì kết luận client bị handshake timeout. Khi cần giữ test nhanh và ổn định, test handshake status/subprotocol bằng local server ở mỗi commit; test network stall/packet loss trong integration suite có tài nguyên kiểm soát được.

## 11. Quản lý idle timeout và heartbeat sau khi WebSocket đã mở

`connectTimeout` chỉ thiết lập kết nối. Một WebSocket thành công có thể **im lặng** vì server không gửi dữ liệu, proxy idle timeout, client không gọi `request(1)` để nhận tiếp, ứng dụng đang chờ message hoặc network không phát hiện mất kết nối ngay. Do đó:

- Thiết lập **business deadline**: sau N giây không có thông điệp được mong đợi, báo timeout nghiệp vụ hoặc chủ động reconnect.
- Nếu dùng Ping/Pong làm heartbeat, gửi Ping theo cadence phù hợp, ghi thời điểm gửi, theo dõi `onPong`; không suy từ `sendPing(...)` hoàn thành rằng server đã trả Pong.
- Đặt giới hạn số connection attempts/reconnect; dùng backoff có jitter để tránh hàng nghìn client kết nối lại đồng thời.
- Với authentication hết hạn, refresh credential theo policy; không reconnect vô hạn bằng token cũ.
- Nếu không có message vì listener quên `request(n)`, sửa demand handling, đừng chỉ tăng timeout.
- Tôn trọng server/proxy idle timeout, rate limit và chính sách Ping; heartbeat quá dày có thể tăng tải không cần thiết.
- Ứng dụng phải phân biệt trạng thái `CONNECTING`, `OPEN`, `CLOSING`, `CLOSED`, `FAILED` thay vì chỉ giữ boolean “đang kết nối”.

### 11.1. Ping hoàn thành gửi không có nghĩa Pong đã nhận

~~~java
socket.sendPing(
    java.nio.ByteBuffer.wrap(new byte[]{1, 2, 3}))
    .whenComplete((s, failure) -> {
        if (failure != null) {
            recordSendFailure(failure);
        } else {
            recordPingSent();
        }
    });
~~~

Đây là **đoạn minh họa**, các hàm `record...` do ứng dụng định nghĩa. Để có heartbeat đáng tin, `Listener.onPong` cần ghi nhận Pong tương ứng (kết hợp nonce/payload hoặc trạng thái ping đang chờ), timer giám sát thời hạn, và nếu quá hạn thì đóng/cancel/reconnect theo policy. Nếu ping gửi trước khi session sẵn sàng, đã close hoặc socket lỗi, future gửi có thể thất bại.

## 12. Xử lý lỗi bất đồng bộ và bảo vệ vòng đời

`buildAsync` là một **future**, không phải một method đồng bộ ném tất cả exception ngay tại dòng gọi. Những lỗi có thể xuất hiện khi:

- Bạn gọi builder/URI sai và nhận exception đồng bộ.
- Connection, TLS hoặc opening handshake thất bại sau đó và future complete exceptionally.
- Future thành công nhưng một `sendText` sau này thất bại.
- Listener phát hiện lỗi và gọi `onError` sau `onOpen`.
- Business layer chờ deadline riêng hết hạn và hủy attempt.

Mẫu phân loại ở tầng ứng dụng nên giữ riêng:

~~~text
CONNECTING
  |-- invalid args --------------------> CONFIG_ERROR
  |-- no HTTP response, TLS/I/O -------> CONNECT_ERROR
  |-- HttpTimeoutException -----------> HANDSHAKE_TIMEOUT
  |-- WebSocketHandshakeException ----> HTTP_HANDSHAKE_REJECTED
  |-- successful opening handshake ---> OPEN
                                         |-- no agreed subprotocol -> APP_PROTOCOL_UNSUPPORTED
                                         |-- Listener.onError ------> CONNECTION_FAILED
                                         |-- normal close ----------> CLOSED
                                         |-- idle deadline ---------> IDLE_TIMEOUT / reconnect policy
~~~

Khi một future trả lỗi, để log chính xác cần unwrap `ExecutionException`/`CompletionException` mà **không bỏ chain nguyên nhân**. Không ghi raw `Authorization`, token hay query chứa bí mật trong exception handling; dùng route template, hostname được phép, HTTP status, negotiated protocol và error category.

**Cẩn thận với retry:** Handshake GET theo RFC 6455 thường không thực hiện business action như POST, nhưng việc mở rồi đóng nhiều kết nối vẫn có thể tạo session/charge/rate-limit phía server. Nếu lỗi do 401/403 hoặc subprotocol không tương thích, retry liên tục sẽ không giải quyết vấn đề. Với lỗi tạm thời 503/timeout, backoff có giới hạn, jitter và tổng deadline là cần thiết.

## 13. Security cho WebSocket handshake

1. **Ưu tiên `wss://`** ngoài môi trường test có kiểm soát; kiểm chứng certificate, hostname, trust store và chính sách TLS.
2. **Không tin URI do người dùng cung cấp tùy ý.** Nếu một service backend được phép chủ động tạo WebSocket tới URL bên ngoài, kiểm soát scheme/host/IP/DNS/redirect/proxy để tránh SSRF và truy cập metadata nội bộ.
3. **Phân quyền không nằm trong subprotocol name.** `Sec-WebSocket-Protocol: admin.v1` chỉ là thỏa thuận ngữ nghĩa message, không trao quyền admin.
4. **Không log credentials.** Tránh token trong URL, raw handshake headers, cookie và query; log status và mã lỗi đã giới hạn.
5. **Kiểm tra Origin và authentication ở server.** Client-side Java builder không tự thay thế các quy tắc bảo vệ endpoint.
6. **Không tin mỗi HTTP 101.** Cần validate `Sec-WebSocket-Accept` và protocol/extension; JDK quản lý chuẩn handshake.
7. **Giới hạn kích thước message** và số sessions/concurrency ở app/server; 101 thành công không chứng minh data sau đó an toàn.
8. **Không tự chèn WebSocket protocol headers** qua `header` hoặc tắt kiểm tra TLS để chữa lỗi handshake.
9. **Không dùng SHA-1 của handshake để xác thực danh tính.** Sec-WebSocket-Accept chỉ chứng minh server đã xử lý key theo RFC; TLS và application authentication phục vụ bảo mật.
10. **Không vô hạn reconnect** khi server từ chối handshake; tôn trọng `Retry-After` khi có và policy rate limit.

## 14. Chẩn đoán theo triệu chứng

| Triệu chứng | Kiểm tra trước | Không nên kết luận |
| --- | --- | --- |
| `buildAsync` timeout | Connect/handshake deadline, DNS, proxy, TLS, server có trả 101 không. | “Server chắc chắn trả 403”. |
| Future lỗi với 403 | `getResponse().statusCode()`, auth, quyền, Origin, reverse proxy. | “Java WebSocket bị lỗi framing”. |
| Future lỗi với 200 | Endpoint đang trả HTTP thay vì upgrade, path/router, server WS có bật không. | “WebSocket đã kết nối vì HTTP thành công”. |
| Future lỗi sau 101 | `Sec-WebSocket-Accept`, Upgrade/Connection headers, protocol selected, proxy rewrite. | “101 đồng nghĩa hợp lệ”. |
| `getSubprotocol()==""` | Server có chọn protocol không, client có offer không. | “Handshake luôn thất bại”. |
| Server chọn `events.v1` dù offer v2 trước | Danh sách server hỗ trợ và chính sách chọn của server. | “Java luôn chọn phần tử đầu”. |
| Gửi được nhưng không nhận onText | `onOpen` có gọi `request(1)`, mỗi callback có request thêm không, có fragment chưa kết thúc không. | “connectTimeout quá ngắn”. |
| `onError` sau nhiều phút | Network close/reset, message/lifecycle, idle policy. | “Lỗi opening handshake”. |
| `sendPing` thành công nhưng app timeout | Đã nhận `onPong` chưa, ping payload/deadline, session state. | “Pong đã đến vì send future complete”. |
| `wss` báo `SSLHandshakeException` | Trust store, chain, hostname, TLS/proxy. | “Chỉ cần vô hiệu hóa certificate validation”. |
| 401/407 lặp nhiều lần | Authentication process/proxy identity/credential expiry. | “Retry thêm vô hạn sẽ sửa được”. |
| Đóng bằng `abort` rồi không có Close frame | Phân biệt abort và graceful close, lifecycle. | “Peer đã nhận mã close 1000”. |

## 15. Checklist trước khi triển khai

1. URI đúng `ws`/`wss`, path endpoint, quyền mạng và proxy đã rõ chưa?
2. Handshake có timeout **hữu hạn** qua `WebSocket.Builder.connectTimeout` không?
3. Có phân biệt timeout của `buildAsync` với deadline của caller, idle timeout và send/receive timeout không?
4. Danh sách subprotocol có đúng token/ưu tiên và được server hỗ trợ không?
5. Sau kết nối đã kiểm `getSubprotocol()`; nếu là chuỗi rỗng thì hợp đồng nghiệp vụ xử lý thế nào?
6. HTTP handshake exception có được phân loại qua `getResponse().statusCode()` (khi có response), tách khỏi TLS/IO/timeout không?
7. Có xử lý cả lỗi future trước `onOpen` và lỗi `Listener.onError` sau khi kết nối không?
8. Listener có gọi `request(n)` phù hợp, ghép fragmented messages và đặt byte/message budget không?
9. Có dùng `sendClose` cho graceful close và `abort` chỉ khi cần hủy đột ngột không?
10. Authentication/TLS/certificate/Origin có được kiểm tra độc lập với tên subprotocol không?
11. Có reconnect/backoff/jitter, giới hạn số connection và total deadline không?
12. Test có fixture local cho 101 hợp lệ, 403, protocol không được offer, timeout và socket ngắt giữa chừng không?
13. Có log HTTP status, error category, subprotocol được chọn và timing mà không rò raw tokens/headers không?
14. Source code và JUnit/dependencies thật sự tương thích với Java 11 không?

## 16. Bài tự luyện

**Bài 1 — ba thời hạn:** Giải thích vì sao `connectTimeout(Duration.ofSeconds(5))` không thể tự phát hiện một WebSocket im lặng sau 30 phút đã mở. Thiết kế heartbeat có `onPong` và application deadline riêng.

**Bài 2 — subprotocol:** Client đề nghị `events.v2, events.v1`; server chọn `events.v1`. `getSubprotocol()` ra gì? Điều gì xảy ra nếu ứng dụng chỉ chấp nhận schema v2? **Đáp án:** trả `events.v1`; handshake có thể thành công, nhưng app phải từ chối hoặc fallback v1 theo hợp đồng.

**Bài 3 — không chọn:** Client đề nghị một protocol nhưng server không trả `Sec-WebSocket-Protocol`. Có thể có `WebSocket` thành công không? **Có thể**; `getSubprotocol()==""`. Thiết kế kiểm tra bắt buộc nếu app cần protocol.

**Bài 4 — HTTP 403:** Chạy `WebSocketHandshakeDemo.java` và giải thích vì sao `buildAsync(...).get(...)` ném `ExecutionException` chứ không tạo WebSocket; lấy HTTP 403 ở đâu.

**Bài 5 — HTTP 101 sai:** Sửa fixture `Sec-WebSocket-Accept` thành chuỗi sai. Dự đoán handshake sẽ thất bại; đừng chỉ kiểm status 101 mà bỏ qua các header bắt buộc.

**Bài 6 — timeout:** Sửa fixture để nhận request rồi không trả HTTP response. Cấu hình connectTimeout và outer future get timeout; phân biệt `HttpTimeoutException` ở future và `TimeoutException` của thread chờ.

**Bài 7 — Listener demand:** Override `onOpen` nhưng không gọi `request(1)`; WebSocket có thể mở nhưng không đưa message tới listener. Sửa code và giải thích vì sao `request(1)` không phải “chỉ một message”.

**Bài 8 — reconnect:** Một gateway trả `503` trong 1 phút. Thiết kế retry với exponential backoff + jitter, tối đa N lần/thời hạn, không bùng nổ connection khi nhiều client cùng restart.

**Bài 9 — bảo mật:** Một service cho người dùng nhập WebSocket URL bất kỳ. Liệt kê các rủi ro SSRF, token exposure, TLS downgrade và cách tạo allowlist endpoint.

**Bài 10 — close:** So sánh `sendClose(1000, "bye")` và `abort()`. Tại sao future gửi Close hoàn tất không chứng minh phía bên kia đã đóng êm?

**Bài 11 — proxy:** WebSocket hoạt động tại localhost nhưng trả 200 hoặc 403 khi qua reverse proxy. Xác định các hop và những header/route cần kiểm tra. Không tự ép Upgrade header từ Java client khi builder đã quản lý handshake.

**Bài 12 — test:** Bổ sung JUnit case server trả 404 và server chọn subprotocol chưa được offer. Tách assertion về HTTP status khỏi assertion về hợp đồng subprotocol.

## 17. Tài liệu chuẩn và tổng kết

- [Java SE 11 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): `connectTimeout`, `subprotocols`, `header` và `buildAsync`.
- [Java SE 11 — WebSocket](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html): `getSubprotocol()`, `request(n)`, `sendPing`, `sendClose` và `abort`.
- [Java SE 11 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): callbacks, onOpen, onText fragment/last, onError và onClose.
- [Java SE 11 — WebSocketHandshakeException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocketHandshakeException.html): lỗi opening handshake và `getResponse()`.
- [Java SE 11 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpTimeoutException.html): lỗi timeout giai đoạn HTTP connection/request.
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455): `101 Switching Protocols`, `Sec-WebSocket-Key/Accept`, `Sec-WebSocket-Protocol`, frames và close handshake.
- [JEP 321 — HTTP Client API](https://openjdk.org/jeps/321): WebSocket client trong API chuẩn của JDK 11.

**Ghi nhớ:** `connectTimeout` giới hạn **thiết lập kết nối và opening handshake**, không phải idle lifetime. `subprotocols(...)` chỉ đề nghị các tên theo thứ tự ưu tiên; **`getSubprotocol()`** mới cho biết giao thức ứng dụng được server chọn, và có thể rỗng. Lỗi HTTP handshake phải kiểm ở **future của `buildAsync`**, đọc status từ `WebSocketHandshakeException.getResponse()` nếu có; lỗi sau kết nối đi qua **Listener/send futures**. Hãy quản lý TLS, deadline, request demand, graceful close và retry như những trách nhiệm riêng biệt để WebSocket Java 11 hoạt động đúng và an toàn.