# WebSocket.Builder, buildAsync và bước mở kết nối (Java 11+)

## 1. Mục tiêu: mở một kết nối WebSocket đúng cách

WebSocket là giao thức cho phép **trao đổi thông điệp hai chiều** trên một kết nối duy trì lâu hơn một HTTP request thông thường. Ứng dụng dùng WebSocket khi cần nhận cập nhật thời gian thực, trao đổi thông điệp liên tục, theo dõi trạng thái hoặc làm việc với một giao thức ứng dụng đã định nghĩa trên WebSocket.

Từ **Java 11**, module `java.net.http` cung cấp **WebSocket client chuẩn** qua các API:

```java
HttpClient.newHttpClient()
HttpClient.newWebSocketBuilder()
WebSocket.Builder.buildAsync(URI, WebSocket.Listener)
```

Khác với `HttpClient.send(...)` trả `HttpResponse<T>` của một yêu cầu HTTP, `WebSocket.Builder.buildAsync(...)` trả **`CompletableFuture<WebSocket>`**. Nếu bắt tay mở kết nối thành công, kết quả là một đối tượng `WebSocket` để gửi/nhận thông điệp; nếu thất bại, future có thể hoàn thành bất thường.

**Bài học tập trung vào ba việc chính:**
1. Cấu hình **`WebSocket.Builder`**: URI đích, timeout, header bổ sung và subprotocol.
2. Gọi **`buildAsync`** và phân biệt “đã tạo builder”, “đang mở kết nối” và “kết nối đã mở”.
3. Hiểu **opening handshake**, listener `onOpen`, nhận dữ liệu qua `request(n)`, xử lý lỗi bắt tay, đóng kết nối an toàn.

Các API trong bài vẫn đang được sử dụng trong Java hiện đại; ví dụ hoàn chỉnh biên dịch bằng **`javac --release 11`** để tránh dựa vào chức năng chỉ có ở JDK mới hơn.

## 2. WebSocket khác HTTP request-response ở đâu?

Trong HTTP request-response, client gửi một request và nhận phản hồi; việc nhận xong body thường kết thúc một giao dịch. Với WebSocket, client **bắt đầu bằng một HTTP opening handshake**. Sau khi server chấp thuận, cùng kết nối chuyển sang trao đổi **WebSocket frames**.

```text
Java WebSocket client                       WebSocket server
        |                                         |
        |  HTTP/1.1 GET + Upgrade: websocket     |
        |  Sec-WebSocket-Key, Version,...        |
        |---------------------------------------->|
        |                                         |
        | HTTP/1.1 101 Switching Protocols       |
        | Upgrade: websocket                     |
        | Sec-WebSocket-Accept: ...               |
        |<----------------------------------------|
        |                                         |
        |           Kết nối WebSocket mở          |
        |                                         |
        |---------- text/binary frame ---------->|
        |<--------- text/binary frame ------------|
        |<---------------- ping ------------------|
        |----------------- pong ----------------->|
        |---------- close (status 1000) --------->|
        |<---------------- close -----------------|
```

Những chi tiết cần hiểu:

- URI **`ws://`** dùng WebSocket không được bảo vệ bằng TLS; URI **`wss://`** dùng WebSocket **qua TLS**, thích hợp khi truyền dữ liệu ngoài môi trường thử nghiệm cục bộ.
- Opening handshake của WebSocket theo RFC 6455 sử dụng **HTTP/1.1 Upgrade**, với một số header dành riêng cho giao thức WebSocket.
- Khi server chấp nhận, status cho bước chuyển giao thức là **`101 Switching Protocols`**, cùng các header tương ứng.
- Sau khi mở xong, WebSocket **không** gửi một `HttpRequest`/`HttpResponse` mới cho mỗi message; dữ liệu đi qua WebSocket frames và listener.
- Nếu server trả `403`, `404` hoặc phản hồi không thỏa handshake, đó **không phải một WebSocket mở thành công**. `buildAsync` có thể thất bại với `WebSocketHandshakeException`.

**Không coi WebSocket là REST API có response body theo từng message.** Thứ tự nhận/gửi, đóng kết nối và cơ chế thông điệp được quản lý riêng.

## 3. Các đối tượng Java 11 và trách nhiệm của từng đối tượng

| API | Nhiệm vụ | Lưu ý |
| --- | --- | --- |
| `HttpClient` | Cung cấp cấu hình nền tảng như TLS, proxy, authenticator, executor; tạo WebSocket builder. | Chia sẻ một client khi phù hợp; không tự gửi WebSocket frame. |
| `HttpClient.newWebSocketBuilder()` | Tạo `WebSocket.Builder`. | Chưa kết nối mạng. |
| `WebSocket.Builder` | Chọn header tùy chỉnh, connect timeout và subprotocol trước handshake. | Builder **không an toàn** để nhiều thread sửa đồng thời. |
| `buildAsync(uri, listener)` | Bắt đầu mở kết nối và trả `CompletableFuture<WebSocket>`. | Không tự chặn thread gọi để đợi kết nối. |
| `WebSocket.Listener` | Nhận sự kiện `onOpen`, `onText`, `onBinary`, `onClose`, `onError`. | Phải quản lý demand nhận dữ liệu. |
| `WebSocket` | Đại diện kết nối đã mở; `sendText`, `sendBinary`, `sendClose`, `request`. | Có hướng input/output với vòng đời riêng. |
| `WebSocketHandshakeException` | Lỗi trong bước HTTP opening handshake. | Có thể lấy `getResponse().statusCode()` để chẩn đoán. |

**Không nhầm hai builder:**

```java
HttpClient.Builder httpClientBuilder = HttpClient.newBuilder();
HttpClient client = httpClientBuilder.build();
WebSocket.Builder webSocketBuilder = client.newWebSocketBuilder();
```

Đây là **mảnh mã minh họa trong phương thức** và cần import `HttpClient`/`WebSocket`. `HttpClient.Builder` cấu hình HTTP client dùng làm nền; `WebSocket.Builder` cấu hình **một lần mở kết nối WebSocket**. Cả hai có phương thức `connectTimeout(...)` nhưng phạm vi áp dụng không giống nhau.

## 4. Tạo WebSocket.Builder và cấu hình opening handshake

### 4.1. Ví dụ ngắn gọn

```java
HttpClient client = HttpClient.newHttpClient();

WebSocket.Listener listener = new WebSocket.Listener() {
    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }
};

CompletableFuture<WebSocket> opening = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .header("X-Client", "lesson-java11")
        .subprotocols("chat.v1", "chat.v0")
        .buildAsync(URI.create("wss://socket.example.com/chat"), listener);
```

Đây là **mã minh họa**, cần import `java.net.URI`, `java.time.Duration`, `java.net.http.HttpClient`, `WebSocket` và `java.util.concurrent.CompletableFuture`. URI `socket.example.com` chỉ là ví dụ về cú pháp; không khẳng định có endpoint đang hoạt động ở đó. Chương trình độc lập có server localhost và đầu ra kiểm chứng nằm ở mục 9.

Ý nghĩa:
- `newWebSocketBuilder()`: bắt đầu cấu hình kết nối.
- `connectTimeout(...)`: giới hạn thời gian **thiết lập WebSocket**.
- `header(...)`: thêm **HTTP header bổ sung** cho opening handshake.
- `subprotocols(...)`: khai báo các giao thức ứng dụng mà client mong muốn, theo **thứ tự ưu tiên**.
- `buildAsync(uri, listener)`: khởi động thiết lập kết nối, trả future chưa chắc đã hoàn thành ngay.

### 4.2. Builder là đối tượng cấu hình, không phải WebSocket

`newWebSocketBuilder()` không gửi gói handshake và không tạo một kết nối đang mở. Các phương thức `header`, `subprotocols`, `connectTimeout` chỉ thay đổi cấu hình builder rồi trả chính builder đó.

Sau khi gọi `buildAsync(...)`, phải đợi **future kết nối** hoàn thành bình thường hoặc xử lý lỗi. Không dùng biến `WebSocket` chưa tồn tại để gửi message.

`WebSocket.Builder` được tài liệu Java 11 xác định là **không thread-safe**. Vì thế không để nhiều thread cùng lúc gọi các phương thức setter trên **một builder** mà không đồng bộ; thông thường tạo mỗi builder trong một luồng điều phối và kết thúc cấu hình trước khi gọi `buildAsync`.

### 4.3. header(String name, String value)

`header(...)` thêm một cặp name/value vào các HTTP header bổ sung **khi mở kết nối**, ví dụ:

```java
WebSocket.Builder builder = client.newWebSocketBuilder()
        .header("X-Client-Version", "1")
        .header("X-Trace-Id", "demo-001");
```

Mảnh mã này giả định đã có `HttpClient client`. Tên header giao thức WebSocket **không được tự đặt qua API này**. Các header như `Sec-WebSocket-Key`, `Sec-WebSocket-Version`, `Sec-WebSocket-Accept`, `Upgrade` hoặc `Connection` do quá trình WebSocket handshake kiểm soát. Cố ghi đè những header thuộc giao thức là sai hợp đồng builder và có thể bị từ chối.

Không tự sinh khóa `Sec-WebSocket-Key` rồi gắn thủ công; để implementation Java tuân theo RFC 6455.

Nếu API server dùng header cho xác thực, không ghi token cố định trong source, không log header bí mật, và chỉ gửi token tới server/URI tin cậy trên `wss://`. Không đưa thông tin đăng nhập vào URL query khi có phương án an toàn hơn.

### 4.4. connectTimeout(Duration)

```java
WebSocket.Builder builder = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5));
```

`WebSocket.Builder.connectTimeout` giới hạn **việc thiết lập kết nối WebSocket**, bao gồm bước mở kết nối theo hợp đồng API. Nếu vượt hạn, `buildAsync` có thể hoàn thành bất thường với **`HttpTimeoutException`**.

- `Duration` phải **dương**; giá trị `Duration.ZERO` hoặc âm không hợp lệ.
- Nếu không gọi setter này, mặc định API không đặt một giới hạn timeout hữu hạn ở mức builder.
- Đây **không phải** timeout để “mọi tin nhắn WebSocket luôn đến trong 5 giây”. Khi đã mở, ứng dụng cần chính sách heartbeat, thời hạn nghiệp vụ hoặc đóng/hủy riêng.
- `HttpClient.Builder.connectTimeout` là cấu hình kết nối ở tầng HTTP client. Khi cần **giới hạn cụ thể cho việc WebSocket mở**, hãy dùng trực tiếp `WebSocket.Builder.connectTimeout` theo yêu cầu API.

Trong ứng dụng thật nên đặt deadline hợp lý cho cả quá trình mở và cơ chế xử lý lỗi, tránh giữ các tác vụ chờ không xác định.

### 4.5. subprotocols(String mostPreferred, String... lesserPreferred)

```java
WebSocket.Builder builder = client.newWebSocketBuilder()
        .subprotocols("chat.v2", "chat.v1");
```

Tham số đầu tiên là subprotocol ưu tiên cao nhất. Client gửi danh sách trong bước handshake và server **có thể chọn một giao thức mà hai bên hỗ trợ**. Sau khi kết nối mở:

```java
String selected = webSocket.getSubprotocol();
```

Đoạn này giả định có `WebSocket webSocket` đã kết nối. Nếu không thương lượng subprotocol nào, `getSubprotocol()` trả **chuỗi rỗng**, không phải `null`. Nếu ứng dụng **bắt buộc** phải dùng `chat.v2`, phải kiểm tra kết quả và đóng kết nối nếu server không chọn giao thức chấp nhận được.

Subprotocol là **quy ước về thông điệp ứng dụng**, không phải HTTP/1.1/HTTP/2. Không dùng `HttpClient.Version.HTTP_2` để yêu cầu một `Sec-WebSocket-Protocol`. Tên subprotocol phải có cú pháp hợp lệ theo giao thức; builder có thể từ chối giá trị không hợp lệ.

## 5. buildAsync: từ future đến WebSocket đang mở

Chữ ký:

```java
CompletableFuture<WebSocket> buildAsync(
        URI uri, WebSocket.Listener listener)
```

Một cách dùng có kiểm soát:

```java
CompletableFuture<WebSocket> connection =
        client.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .buildAsync(uri, listener);

connection.thenAccept(ws -> {
    System.out.println("Connected, subprotocol=" + ws.getSubprotocol());
}).exceptionally(error -> {
    System.err.println("Failed to open: " + error);
    return null;
});
```

Đây là **mảnh mã minh họa trong phương thức**, không phải chương trình độc lập. `thenAccept` chỉ chạy nếu `buildAsync` hoàn thành **bình thường**. `exceptionally` trong mẫu dùng để minh họa một nhánh xử lý và phải được thiết kế theo nghiệp vụ: nếu kết nối bắt buộc phải thành công, không nên nuốt lỗi bằng một fallback vô nghĩa.

**Phân biệt vòng đời:**

1. **Chưa gọi `buildAsync`:** chỉ có cấu hình builder; chưa có WebSocket.
2. **Đã gọi `buildAsync`, future đang pending:** quá trình kết nối/handshake có thể chưa xong.
3. **Future hoàn thành bình thường:** có đối tượng `WebSocket` đã thiết lập; có thể gửi `sendText`, `sendBinary`, `sendPing`, `sendClose`.
4. **Future hoàn thành bất thường:** không có kết nối WebSocket thành công từ lần mở ấy; cần chẩn đoán nguyên nhân.
5. **Kết nối đã mở nhưng lỗi về sau:** listener có thể nhận `onError` hoặc các `send...` future có thể thất bại. Đây là **lỗi trong phiên WebSocket đang hoạt động**, không phải lỗi của opening handshake ban đầu.

### 5.1. buildAsync không đồng nghĩa bắt thread chờ

`buildAsync` trả `CompletableFuture<WebSocket>` nhanh, để caller ghép callback. Một chương trình CLI/test có thể dùng `join()` hoặc `get(timeout, unit)` để **chủ động chờ** kết quả:

```java
WebSocket ws = connection.join();
```

Nhưng `join()` **chặn thread gọi** và có thể ném `CompletionException` nếu future thất bại. Trong UI/server event loop, không nên dùng `join()` vô điều kiện; hãy phối hợp với `CompletableFuture` và executor phù hợp.

`get(5, TimeUnit.SECONDS)` chỉ giới hạn **thời gian caller chờ future**; nếu timeout, không tự chứng minh request đã bị hủy hoặc server chưa thấy handshake. `connectTimeout` trên builder mô tả **giới hạn của việc kết nối**; hai loại thời hạn khác nhau.

### 5.2. URI ws:// và wss://

Ví dụ cú pháp:

```text
ws://127.0.0.1:9000/chat
wss://stream.example.com/events
```

- `ws://` phù hợp với fixture **localhost** trong bài. Không dùng nó để gửi token/tin nhắn nhạy cảm qua mạng không tin cậy.
- `wss://` sử dụng TLS và là lựa chọn phù hợp cho phần lớn trao đổi qua Internet.
- `URI` phải hợp lệ và đúng endpoint WebSocket thực tế. Không dùng `https://...` hoặc `file://...` thay cho URI WebSocket rồi giả định chúng sẽ luôn hoạt động.
- URI chứa query cần được encode đúng. Không nối input chưa tin cậy vào URL rồi gửi đến host bất kỳ.

Trong ứng dụng server-side nhận URI do người dùng cung cấp, cần kiểm soát scheme, host, port, DNS/IP, proxy và những đường đi có thể dẫn đến **SSRF**. WebSocket không miễn trừ các rủi ro của việc kết nối mạng đến đích không đáng tin cậy.

## 6. Opening handshake: server chấp nhận dựa trên điều gì?

RFC 6455 định nghĩa quá trình mở WebSocket qua một HTTP/1.1 Upgrade handshake. Client gửi request kiểu:

```http
GET /chat HTTP/1.1
Host: example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <base64 nonce>
Sec-WebSocket-Version: 13
Sec-WebSocket-Protocol: chat.v1
```

Đây là **ví dụ minh họa cấu trúc giao thức**, không phải header cần lập trình viên tự gắn bằng `WebSocket.Builder.header`. Chữ `<base64 nonce>` là chỗ mô tả một giá trị được tạo cho handshake, không phải chuỗi gửi nguyên văn.

Server chấp nhận bằng một phản hồi dạng:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <computed accept>
Sec-WebSocket-Protocol: chat.v1
```

Server tính `Sec-WebSocket-Accept` từ khóa client gửi cộng với một GUID cố định rồi SHA-1/Base64, như quy định trong RFC 6455. **Giá trị này giúp xác nhận thủ tục Upgrade hợp lệ, không phải một phương pháp xác thực người dùng hoặc chứng chỉ server**. Nếu cần xác thực, thực hiện bằng TLS, thông tin xác thực/phiên và chính sách server thích hợp.

**Các bước logic của phía client Java:**

1. Tạo `HttpClient`; nếu cần, cấu hình TLS/proxy/authenticator/executor.
2. Tạo `WebSocket.Builder` từ `client.newWebSocketBuilder()`.
3. Đặt timeout, header bổ sung và subprotocol (nếu có).
4. Cung cấp `URI ws/wss` và `WebSocket.Listener` cho `buildAsync`.
5. Java mở kết nối, thực hiện TLS đối với `wss`, gửi handshake và kiểm tra phản hồi.
6. Server chấp nhận bằng `101` và header hợp lệ → `buildAsync` hoàn thành bình thường, listener được thông báo `onOpen`.
7. Sau đó ứng dụng dùng `WebSocket` và listener để trao đổi WebSocket messages.

Nếu server trả một status khác `101` hoặc handshake thiếu/sai header bắt buộc, client không được coi đó là kết nối WebSocket thành công. Đó là **lỗi opening handshake**, không giống việc server gửi một WebSocket text message có nội dung “error”.

### 6.1. Không dùng HttpResponse của REST làm kết quả buildAsync

`HttpClient.send(request, BodyHandlers.ofString())` trả `HttpResponse<String>`. Nhưng:

```java
CompletableFuture<WebSocket> connected =
        client.newWebSocketBuilder().buildAsync(uri, listener);
```

không trả `HttpResponse<String>` nếu thành công. Bạn kiểm tra **`WebSocket.getSubprotocol()`**, trạng thái input/output và sự kiện listener để theo dõi phiên. Chỉ khi handshake **thất bại** và có `WebSocketHandshakeException`, bạn có thể khai thác metadata phản hồi HTTP qua `getResponse()`.

## 7. WebSocket.Listener: onOpen, request(1) và nhận thông điệp

Một listener tối thiểu:

```java
WebSocket.Listener listener = new WebSocket.Listener() {
    @Override
    public void onOpen(WebSocket ws) {
        System.out.println("WebSocket opened");
        ws.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket ws, CharSequence part, boolean last) {
        System.out.println(part);
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public void onError(WebSocket ws, Throwable error) {
        System.err.println("WebSocket error: " + error);
    }
};
```

Đây là **đoạn minh họa trong phương thức**; cần import `WebSocket`, `CompletionStage` và `CompletableFuture`. Với một thông điệp lớn bị phân mảnh, `onText` có thể được gọi nhiều lần; không phải mỗi lần gọi tương ứng một **thông điệp hoàn chỉnh**.

### 7.1. Vì sao cần request(1)?

`WebSocket` Java 11 có **bộ đếm demand** dành cho callback nhận message. Sau khi tạo WebSocket, bộ đếm ban đầu là **0**. Gọi `ws.request(n)` để cho phép thêm `n` lần gọi phương thức receive của listener.

- `onOpen` **không** phải một receive event; nó xảy ra khi kết nối đã mở.
- `onText`, `onBinary`, `onPing`, `onPong`, `onClose` tham gia quy trình nhận.
- Nếu override `onOpen` mà **không gọi `ws.request(1)`**, ứng dụng có thể không nhận được callback dữ liệu như kỳ vọng.
- Mỗi lần xử lý `onText`, có thể gọi `ws.request(1)` để cho phép lần nhận tiếp theo.
- `request(n)` không có nghĩa server bị ép tạo `n` tin nhắn; nó là cơ chế **điều phối nhận** của client.

Nếu không override `onOpen`, implementation mặc định của `WebSocket.Listener.onOpen` gọi `webSocket.request(1)`. Nhưng khi bạn override để log/khởi tạo trạng thái, nên chủ động gọi `request(1)` hoặc gọi `WebSocket.Listener.super.onOpen(ws)`.

### 7.2. last và phân mảnh thông điệp

`onText(WebSocket ws, CharSequence data, boolean last)` cung cấp **một phần dữ liệu text** và cờ `last`.

- `last == false`: còn phần dữ liệu thuộc cùng message.
- `last == true`: phần này kết thúc message.
- Nếu muốn ghi nhận **một message hoàn chỉnh**, cộng dồn các phần đến khi `last` đúng rồi xử lý.
- Không giữ hoặc dùng `CharSequence data` sau khi `CompletionStage` trả từ `onText` hoàn tất; nếu cần lưu, **sao chép nội dung ngay** vào cấu trúc riêng.
- Đặt giới hạn kích thước message khi nhận dữ liệu từ nguồn không tin cậy; tích lũy vô hạn vào `StringBuilder` có thể làm hết bộ nhớ.

### 7.3. onError không phải callback của buildAsync failure

`WebSocket.Listener.onError` mô tả **lỗi của kết nối WebSocket đã được tạo**, ví dụ lỗi I/O trong quá trình trao đổi hoặc exception của listener. Nếu **opening handshake thất bại ngay từ đầu**, phải xử lý **future từ `buildAsync`**; đừng trông chờ mọi lỗi mở kết nối đều xuất hiện qua `listener.onError`.

Listener có thể nhận `onOpen` trước khi một callback gắn với `buildAsync` kịp chạy. Không dựa vào thứ tự lệnh `System.out.println` ở nhiều thread để suy đoán hợp đồng; nếu test cần quan sát, dùng `CompletableFuture` hoặc cơ chế đồng bộ phù hợp.

## 8. Kiểm tra lỗi buildAsync và thông tin bắt tay

### 8.1. Thất bại khi server không chấp nhận

`buildAsync` có thể hoàn thành bất thường với `WebSocketHandshakeException` khi HTTP opening handshake thất bại. Exception này **extends `IOException`** và có:

```java
HttpResponse<?> response = handshakeError.getResponse();
int status = response.statusCode();
```

Đây là **mảnh mã minh họa** với biến `handshakeError` kiểu `WebSocketHandshakeException`. Nó không phải response của một WebSocket message; đó là **phản hồi HTTP cho bước bắt tay thất bại**. Trong tình huống bình thường nó có metadata về status/headers để chẩn đoán. API cũng lưu ý `getResponse()` có thể không còn sẵn (`null`) trong trường hợp exception đã serialize rồi deserialize.

Ví dụ xử lý future:

```java
try {
    WebSocket ws = client.newWebSocketBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .buildAsync(uri, listener)
            .join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    if (cause instanceof WebSocketHandshakeException) {
        WebSocketHandshakeException h =
                (WebSocketHandshakeException) cause;
        HttpResponse<?> rejected = h.getResponse();
        System.err.println("Handshake rejected: " +
                (rejected == null ? "unknown" : rejected.statusCode()));
    } else {
        System.err.println("Failed to open WebSocket: " + cause);
    }
}
```

Đây là **mã minh họa** với `client`, `uri`, `listener` và các import cần thiết. Không log nguyên response headers/body khi có thông tin nhạy cảm.

### 8.2. Những lỗi khác

| Tình huống | Biểu hiện có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Sai URI, sai header/subprotocol | `IllegalArgumentException` hoặc lỗi validation của builder. | Sửa tham số, không tự động retry. |
| Không thể mở socket/kết nối | `IOException` hoặc subclass. | Kiểm tra mạng, proxy, server/port, có thể retry có giới hạn. |
| Không hoàn tất handshake trước thời hạn | `HttpTimeoutException`. | Kiểm tra `connectTimeout`, tải hệ thống, giới hạn retry. |
| Server trả 401/403/404 hoặc handshake không hợp lệ | `WebSocketHandshakeException`. | Xem `getResponse()` và hợp đồng endpoint; không coi đã mở WS. |
| Chứng chỉ TLS không hợp lệ khi dùng wss | `SSLException` hoặc lỗi TLS liên quan. | Sửa trust/hostname; không tắt TLS verification. |
| Future bị hủy hoặc caller ngừng đợi | `CancellationException`/`TimeoutException` ở tầng future tùy cách dùng. | Không suy ra server đã rollback hoặc kết nối bị đóng hoàn toàn. |
| Kết nối đã mở, sau đó đứt | `onError` hoặc future `sendText` bất thường. | Quản lý reconnect, đóng, giữ trạng thái application. |

`buildAsync` là bất đồng bộ, nên `join()`/`get()` có thể bọc exception. Muốn phân loại chính xác, xem `getCause()` và các tầng wrapper như `CompletionException`/`ExecutionException`, không so sánh nguyên văn thông báo lỗi.

### 8.3. Timeout mở kết nối khác timeout message

`WebSocket.Builder.connectTimeout` nói về **thiết lập kết nối**, không có nghĩa connection luôn sống hoặc server bắt buộc trả message sau 5 giây. Một phiên có thể mở thành công nhưng không bao giờ nhận tin nhắn mới. Muốn phát hiện connection “chết” cần chiến lược heartbeat/ping, deadline nghiệp vụ, đóng/reconnect và giới hạn tải theo hệ thống.

## 9. Ví dụ Java 11+ hoàn chỉnh: mở WS, echo, đóng và handshake bị từ chối

Ví dụ không dựa vào dịch vụ ngoài. Nó tạo một **server WebSocket tối giản trên localhost** bằng `ServerSocket` để chủ động kiểm thử hai kết quả:

1. Kết nối `ws://127.0.0.1:<port>/echo` mở thành công với `101 Switching Protocols`; server phản hồi subprotocol `chat.v1`.
2. Server echo một text frame nhỏ, sau đó hoàn thành close handshake.
3. Kết nối đến `/reject` bị từ chối bằng **HTTP 403**, giúp kiểm tra `WebSocketHandshakeException.getResponse()`.

**Giới hạn quan trọng:** Phần server ở đây là **fixture minh họa handshake RFC 6455 cho trường hợp nhỏ, đơn giản**, không phải một WebSocket server production đầy đủ. Nó chỉ đọc **frame masked có payload ≤125 byte**, không hỗ trợ payload mở rộng, fragmentation, nhiều loại frame, bảo vệ đầy đủ hoặc nhiều kết nối đồng thời như một server thực sự cần. Trong ứng dụng thực tế, hãy dùng WebSocket server/framework đã triển khai đầy đủ giao thức. **Phía client dùng đúng `java.net.http.WebSocket` của Java 11.**

Lưu mã trong **`WebSocketOpenDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.net.http.WebSocketHandshakeException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class WebSocketOpenDemo {
    private static final String MAGIC =
            "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

    static class Listener implements WebSocket.Listener {
        final CompletableFuture<Boolean> opened = new CompletableFuture<>();
        final CompletableFuture<String> message = new CompletableFuture<>();
        final CompletableFuture<Integer> closed = new CompletableFuture<>();
        private final StringBuilder text = new StringBuilder();

        @Override
        public void onOpen(WebSocket ws) {
            opened.complete(true);
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket ws, CharSequence part, boolean last) {
            text.append(part);
            if (last) {
                message.complete(text.toString());
            }
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket ws, int code, String reason) {
            closed.complete(code);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            opened.completeExceptionally(error);
            message.completeExceptionally(error);
            closed.completeExceptionally(error);
        }
    }

    static String line(InputStream input) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        int c;
        while ((c = input.read()) != -1 && c != '\n') {
            if (c != '\r') {
                buffer.write(c);
            }
            if (buffer.size() > 8192) {
                throw new IOException("Header too large");
            }
        }
        if (c == -1) {
            throw new EOFException("Header ended unexpectedly");
        }
        return new String(buffer.toByteArray(), StandardCharsets.US_ASCII);
    }

    static byte[] readClientFrame(InputStream input, int expectedOpcode)
            throws IOException {
        int first = input.read(), second = input.read();
        if (first < 0 || second < 0) {
            throw new EOFException("Frame header");
        }
        int opcode = first & 0x0F;
        int len = second & 0x7F;
        if (opcode != expectedOpcode || (second & 0x80) == 0 || len > 125) {
            throw new IOException("Unexpected demo frame");
        }
        byte[] mask = input.readNBytes(4);
        byte[] payload = input.readNBytes(len);
        if (mask.length != 4 || payload.length != len) {
            throw new EOFException("Frame data");
        }
        for (int i = 0; i < payload.length; i++) {
            payload[i] ^= mask[i % 4];
        }
        return payload;
    }

    static void writeServerFrame(
            OutputStream output, int opcode, byte[] payload)
            throws IOException {
        if (payload.length > 125) {
            throw new IOException("Demo payload too large");
        }
        output.write(0x80 | opcode);
        output.write(payload.length);
        output.write(payload);
        output.flush();
    }

    static void serveOne(
            Socket socket, AtomicReference<String> custom) throws Exception {
        socket.setSoTimeout(5000);
        try (Socket connection = socket) {
            InputStream input = connection.getInputStream();
            OutputStream output = connection.getOutputStream();
            String requestLine = line(input);
            String key = null, offered = "";
            String lesson = "";

            while (true) {
                String header = line(input);
                if (header.isEmpty()) {
                    break;
                }
                int colon = header.indexOf(':');
                if (colon <= 0) {
                    continue;
                }
                String name = header.substring(0, colon)
                        .trim().toLowerCase(Locale.ROOT);
                String value = header.substring(colon + 1).trim();
                if (name.equals("sec-websocket-key")) {
                    key = value;
                }
                if (name.equals("sec-websocket-protocol")) {
                    offered = value;
                }
                if (name.equals("x-lesson")) {
                    lesson = value;
                }
            }

            if (requestLine.startsWith("GET /reject ")) {
                output.write(("HTTP/1.1 403 Forbidden\r\n"
                        + "Content-Length: 0\r\n"
                        + "Connection: close\r\n\r\n")
                        .getBytes(StandardCharsets.US_ASCII));
                output.flush();
                return;
            }

            if (!requestLine.startsWith("GET /echo ")
                    || key == null || !offered.contains("chat.v1")) {
                throw new IOException("Unexpected opening request");
            }
            custom.set(lesson);
            byte[] digest = MessageDigest.getInstance("SHA-1").digest(
                    (key + MAGIC).getBytes(StandardCharsets.US_ASCII));
            String accept = Base64.getEncoder().encodeToString(digest);
            String response = "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept + "\r\n"
                    + "Sec-WebSocket-Protocol: chat.v1\r\n\r\n";
            output.write(response.getBytes(StandardCharsets.US_ASCII));
            output.flush();

            byte[] text = readClientFrame(input, 1);
            writeServerFrame(output, 1, text);
            byte[] close = readClientFrame(input, 8);
            writeServerFrame(output, 8, close);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket(0, 10,
                java.net.InetAddress.getByName("127.0.0.1"))) {
            AtomicReference<String> custom = new AtomicReference<>();
            AtomicReference<Throwable> serverError = new AtomicReference<>();
            Thread serverThread = new Thread(() -> {
                try {
                    for (int i = 0; i < 2; i++) {
                        serveOne(server.accept(), custom);
                    }
                } catch (Throwable ex) {
                    serverError.set(ex);
                }
            });
            serverThread.setDaemon(true);
            serverThread.start();

            String root = "ws://127.0.0.1:" + server.getLocalPort();
            HttpClient client = HttpClient.newHttpClient();
            Listener listener = new Listener();
            WebSocket ws = client.newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .header("X-Lesson", "java11")
                    .subprotocols("chat.v1", "chat.v0")
                    .buildAsync(URI.create(root + "/echo"), listener)
                    .orTimeout(5, TimeUnit.SECONDS)
                    .join();

            System.out.println("connected=true");
            System.out.println("onOpen=" +
                    listener.opened.get(5, TimeUnit.SECONDS));
            System.out.println("subprotocol=" + ws.getSubprotocol());
            System.out.println("customHeader=" + custom.get());

            ws.sendText("Chào WebSocket", true).join();
            System.out.println("echo=" +
                    listener.message.get(5, TimeUnit.SECONDS));
            ws.sendClose(WebSocket.NORMAL_CLOSURE, "bye").join();
            System.out.println("closeCode=" +
                    listener.closed.get(5, TimeUnit.SECONDS));

            try {
                client.newWebSocketBuilder()
                        .connectTimeout(Duration.ofSeconds(3))
                        .buildAsync(
                                URI.create(root + "/reject"),
                                new WebSocket.Listener() {})
                        .orTimeout(5, TimeUnit.SECONDS)
                        .join();
                throw new AssertionError("Expected handshake rejection");
            } catch (CompletionException ex) {
                Throwable cause = ex.getCause();
                if (!(cause instanceof WebSocketHandshakeException)) {
                    throw ex;
                }
                int code = ((WebSocketHandshakeException) cause)
                        .getResponse().statusCode();
                System.out.println("handshakeRejected=" + code);
            }

            serverThread.join(3000);
            if (serverThread.isAlive()) {
                throw new AssertionError("Fixture not stopped");
            }
            if (serverError.get() != null) {
                throw new AssertionError(serverError.get());
            }
        }
    }
}
```

Biên dịch và chạy với JDK có hỗ trợ mức Java 11:

```bash
javac -encoding UTF-8 --release 11 WebSocketOpenDemo.java
java WebSocketOpenDemo
```

**Đầu ra đã kiểm chứng trên JDK 24 khi biên dịch với `--release 11`:**

```text
connected=true
onOpen=true
subprotocol=chat.v1
customHeader=java11
echo=Chào WebSocket
closeCode=1000
handshakeRejected=403
```

### 9.1. Giải thích kết quả và cơ chế

- `connected=true`: `buildAsync` đã hoàn thành bình thường và trả `WebSocket`. Việc ghi dòng này không tự tạo kết nối.
- `onOpen=true`: listener đã nhận sự kiện mở kết nối; ví dụ dùng một `CompletableFuture<Boolean>` riêng để chờ sự kiện thay vì dựa vào thứ tự in đa luồng.
- `subprotocol=chat.v1`: client đề xuất `chat.v1` và `chat.v0`; server trả `Sec-WebSocket-Protocol: chat.v1` nên `getSubprotocol()` phản ánh kết quả thương lượng.
- `customHeader=java11`: server fixture đã thấy `X-Lesson` trong request mở. Header bổ sung này **không phải** một WebSocket message.
- `echo=Chào WebSocket`: sau khi mở kết nối, `sendText(..., true)` gửi một text message hoàn chỉnh; server gửi trả frame và listener ghép text để hoàn tất future riêng.
- `closeCode=1000`: client dùng `WebSocket.NORMAL_CLOSURE`, server trả close frame tương ứng; listener nhận mã đóng bình thường.
- `handshakeRejected=403`: endpoint `/reject` trả **HTTP 403**, không mở WebSocket; future `buildAsync` hoàn thành bất thường và cause là `WebSocketHandshakeException`. Chương trình lấy status từ `getResponse()`.

Server dùng vòng lặp socket nhỏ và kiểm tra payload chỉ đủ cho **fixture đã biết**. Nó không phải server production. Chương trình dùng cổng do hệ điều hành tự chọn bằng `new ServerSocket(0, ...)`, bind tại `127.0.0.1` nên không yêu cầu dịch vụ Internet bên ngoài.

## 10. Gửi thông điệp và đóng kết nối sau khi buildAsync thành công

Khi đã có `WebSocket ws`:

```java
CompletableFuture<WebSocket> sent =
        ws.sendText("Hello", true);

CompletableFuture<WebSocket> closed =
        ws.sendClose(WebSocket.NORMAL_CLOSURE, "done");
```

Đây là **mảnh mã minh họa** trong phương thức. `sendText(CharSequence, boolean)` trả future hoàn thành khi **tác vụ gửi** hoàn tất. `last=true` cho biết phần này là **phần cuối của một text message**, không có nghĩa listener bên kia đã xử lý thành công thông điệp.

`sendClose(...)` khởi xướng **đóng có trật tự** phía output của WebSocket; nó khác với `abort()` đóng đột ngột. WebSocket có **input side** và **output side** riêng; một phía đã đóng không nhất thiết cả hai phía đều đóng ngay. `onClose` thông báo khi nhận close message từ peer. Nếu cần chờ đóng hoàn toàn, phải điều phối cả việc gửi close và callback nhận close, kèm timeout phù hợp.

Với lỗi không thể phục hồi, `WebSocket.abort()` có thể dùng để đóng cả hai phía đột ngột. Không mặc định `sendClose(...).join()` có nghĩa server đã nhận và đóng xong ở mọi môi trường.

### 10.1. Tránh dùng một WebSocket chưa mở

**Sai:**

```java
CompletableFuture<WebSocket> opening =
        builder.buildAsync(uri, listener);

// Không có biến WebSocket nào được bảo đảm sẵn sàng ở đây.
```

Đừng gửi message bằng một tham chiếu `WebSocket` chưa được nhận từ future. Dùng `thenCompose` để nối các thao tác theo thứ tự:

```java
CompletableFuture<WebSocket> openedAndSent =
        builder.buildAsync(uri, listener)
               .thenCompose(ws -> ws.sendText("Hi", true));
```

Mảnh mã này giả định builder, URI và listener đã được tạo hợp lệ. `thenCompose` chỉ chạy sau khi kết nối mở thành công; nếu handshake lỗi, phần gửi không được thực hiện.

## 11. Bảo mật và giới hạn vận hành khi mở WebSocket

### 11.1. Dùng wss:// cho môi trường ngoài localhost

Với dữ liệu thực, dùng `wss://` để bảo vệ kênh truyền bằng TLS. Giữ xác minh hostname/chứng chỉ đúng chuẩn. Không chấp nhận mọi chứng chỉ hoặc tắt TLS verification để “chữa” `SSLHandshakeException`.

**`Sec-WebSocket-Key`/`Sec-WebSocket-Accept` không xác thực danh tính người dùng**, cũng không thay thế TLS. Đây là một phần của opening handshake nhằm xác minh thủ tục nâng cấp giao thức. Xác thực người dùng phải dựa trên cơ chế phía server quy định và chính sách lưu giữ bí mật.

### 11.2. Kiểm tra đích trước khi gửi

Nếu URI do người dùng cung cấp cho một dịch vụ backend, chỉ kiểm tra `startsWith("wss://")` là chưa đủ. Cần kiểm soát host, port, địa chỉ IP sau DNS, proxy/egress và đường đi nội bộ để hạn chế **SSRF**. Đừng để WebSocket client tùy ý kết nối đến tài nguyên nội bộ hoặc endpoint quản trị.

Với WebSocket trong **browser**, server còn thường cần kiểm tra `Origin` để ngăn nguồn web không mong muốn; `Origin` không phải thay thế xác thực. Với Java HTTP Client, môi trường không phải browser có thể gửi header khác trình duyệt, nên server không được chỉ dựa vào `Origin` để xác thực.

### 11.3. Header, subprotocol và trạng thái

- Không tự đặt header giao thức WebSocket qua `header(...)`. Các trường đó do implementation tạo và kiểm tra.
- Chỉ gửi header xác thực cho endpoint tin cậy; không ghi log nguyên token, cookie hoặc secret.
- Kiểm tra `ws.getSubprotocol()` sau khi mở, nhất là khi protocol ứng dụng **bắt buộc** một định dạng nhất định.
- Đặt **giới hạn kích thước message** và số kết nối đồng thời; ví dụ tích lũy `StringBuilder` vô hạn trong `onText` có thể gây hết RAM.
- Có cơ chế heartbeat/ping, đóng connection không dùng, reconnect có backoff và giới hạn số lần; **`connectTimeout` chỉ áp dụng lúc mở**.
- Khi reconnect, phân biệt lỗi mạng tạm thời với lỗi xác thực 401/403 hoặc subprotocol không tương thích. Không retry vô hạn vào endpoint từ chối.

### 11.4. Không dùng mã server fixture như WebSocket server thật

RFC 6455 có nhiều yêu cầu: xử lý masked/unmasked frames, phân mảnh, payload lớn dùng extended length, control frames, close semantics, kiểm tra UTF-8, giới hạn tài nguyên, TLS và nhiều luồng kết nối. Server cục bộ ở mục 9 chỉ triển khai **đủ để tạo handshake và một lượt echo nhỏ đã biết**. Khi triển khai sản phẩm, phải dùng thư viện/server WebSocket hỗ trợ RFC đầy đủ và có kiểm thử bảo mật thích hợp.

## 12. Lỗi phổ biến và hướng khắc phục

| Lỗi/hiểu nhầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Gọi `newWebSocketBuilder()` rồi nghĩ đã kết nối. | Nó chỉ tạo builder. | Gọi `buildAsync` và theo dõi future. |
| Nghĩ `buildAsync` trả `HttpResponse<String>`. | Thành công trả `WebSocket`. | Kiểu đúng: `CompletableFuture<WebSocket>`. |
| Dùng `https://...` thay vì URI `ws://`/`wss://` khi mở WebSocket. | Khác scheme và hợp đồng API. | Dùng WebSocket URI hợp lệ của endpoint. |
| Tự thêm `Sec-WebSocket-Key`/`Upgrade` bằng `header`. | Đó là header dành riêng cho giao thức, không được tự ghi đè. | Để JDK làm handshake. |
| Chọn `subprotocols(...)` nhưng không kiểm tra kết quả. | Server có thể chọn khác hoặc không chọn. | Kiểm tra `ws.getSubprotocol()` sau khi mở. |
| Nghĩ `connectTimeout` giới hạn mọi message. | Nó chỉ giới hạn mở kết nối. | Áp dụng heartbeat/deadline nghiệp vụ riêng. |
| Override `onOpen` mà không gọi `request(1)`. | Demand nhận ban đầu bằng 0. | Yêu cầu thêm receive events bằng `request(n)`. |
| Nghĩ mỗi `onText` là một message hoàn chỉnh. | Text message có thể phân mảnh. | Dùng cờ `last` và ghép các phần có giới hạn. |
| Dùng `CharSequence` của callback lâu dài sau khi stage hoàn tất. | WebSocket có thể thu hồi/đổi dữ liệu sau thời điểm đó. | Sao chép nội dung cần giữ trong callback. |
| Handshake HTTP 403 nhưng đợi `onText` để nhận lỗi. | Chưa có WebSocket thành công. | Bắt exceptional completion của `buildAsync`. |
| Bắt mọi lỗi mở kết nối như `WebSocketHandshakeException`. | Có thể là DNS, TLS, timeout hoặc tham số. | Phân loại cause; xem status chỉ khi có handshake response. |
| Gọi `join()` trực tiếp trong UI/event loop. | `join` chặn thread gọi. | Dùng callback/async composition hoặc điều phối thread phù hợp. |
| `sendClose().join()` được coi là cả hai phía đóng. | Hướng input/output có vòng đời riêng. | Theo dõi cả `onClose` khi cần. |
| Dùng `ws://` cho token ngoài Internet. | Không có TLS. | Dùng `wss://` và chính sách xác thực an toàn. |
| Retry handshake vô hạn sau lỗi 403. | Có thể sai quyền hoặc endpoint. | Sửa thông tin xác thực/đích, retry có điều kiện. |
| Xem `Sec-WebSocket-Accept` là chữ ký bảo mật. | Nó chỉ xác nhận thủ tục handshake. | TLS và xác thực độc lập. |

## 13. Bài tập thực hành và đáp án

**Câu 1.** Khác biệt giữa `HttpClient.newWebSocketBuilder()` và `buildAsync(...)`?

**Đáp án:** `newWebSocketBuilder()` chỉ tạo đối tượng cấu hình. `buildAsync` mới bắt đầu thiết lập kết nối và trả `CompletableFuture<WebSocket>`.

**Câu 2.** Server trả `HTTP 403` khi opening handshake. Có thể dùng `ws.sendText(...)` chưa?

**Đáp án:** Không. Handshake thất bại, không có WebSocket mở thành công. Xử lý `WebSocketHandshakeException` và nếu có, đọc `getResponse().statusCode()` để chẩn đoán.

**Câu 3.** Dùng `ws://` và `wss://` khác nhau thế nào?

**Đáp án:** `wss://` sử dụng TLS; `ws://` không cung cấp bảo vệ TLS. Với dữ liệu nhạy cảm qua mạng, nên dùng `wss://` và kiểm tra chứng chỉ.

**Câu 4.** `connectTimeout(Duration.ofSeconds(3))` có bảo đảm server gửi mỗi text message trong 3 giây không?

**Đáp án:** Không. Nó giới hạn bước **thiết lập WebSocket**, không phải deadline mọi message sau khi mở.

**Câu 5.** Client yêu cầu `subprotocols("chat.v2", "chat.v1")`, server chọn `chat.v1`. Có thể biết bằng cách nào?

**Đáp án:** Gọi `webSocket.getSubprotocol()` sau khi `buildAsync` hoàn tất bình thường; kết quả `chat.v1`. Nếu không thương lượng subprotocol nào, kết quả là chuỗi rỗng.

**Câu 6.** Vì sao không được tự đặt `Sec-WebSocket-Key` bằng `WebSocket.Builder.header`?

**Đáp án:** Đây là header **do giao thức WebSocket kiểm soát**. Java implementation sẽ tạo và kiểm tra nó; builder chỉ cho phép header bổ sung hợp lệ.

**Câu 7.** Khi override `onOpen` nhưng quên `ws.request(1)`, lỗi thường là gì?

**Đáp án:** Bộ đếm demand nhận ban đầu bằng 0, nên có thể không được gọi `onText` dù server gửi dữ liệu. Cần gọi `request(1)` trong `onOpen`.

**Câu 8.** `onText(ws, part, false)` có đồng nghĩa đã nhận trọn message?

**Đáp án:** Không. `last=false` báo còn phần tiếp theo; gom dữ liệu đến khi `last=true`, đồng thời giới hạn dung lượng.

**Câu 9.** `sendText("Hi", true).join()` chứng minh server đã xử lý nghiệp vụ chưa?

**Đáp án:** Chưa. Future gửi hoàn tất **tác vụ gửi**, không phải acknowledgement ứng dụng của peer. Nếu cần xác nhận, giao thức ứng dụng phải định nghĩa thông điệp phản hồi phù hợp.

**Câu 10.** Khi lỗi opening handshake, ngoài `IOException` có thể gặp nhóm lỗi nào?

**Đáp án:** `WebSocketHandshakeException`, `HttpTimeoutException`, lỗi TLS/connection, hoặc lỗi tham số. `WebSocketHandshakeException` cũng là một `IOException`; phân loại subtype trước.

**Câu 11.** Đối tượng `WebSocket.Builder` có thể dùng chung cho nhiều thread đang thay đổi header/timeout không?

**Đáp án:** Không có bảo đảm thread-safe. Tạo/cấu hình builder trong một luồng hoặc đồng bộ hóa bên ngoài.

**Câu 12.** `Sec-WebSocket-Accept` có thay thế xác thực người dùng và TLS không?

**Đáp án:** Không. Nó thuộc thủ tục Upgrade. Cần xác thực và bảo vệ kênh truyền theo chính sách độc lập.

## 14. Kết luận và tài liệu chính thức

- `HttpClient.newWebSocketBuilder()`, `WebSocket.Builder` và `buildAsync` là API client **Java 11+** vẫn còn được dùng.
- Builder cấu hình **opening handshake**; `buildAsync` khởi động kết nối và trả **`CompletableFuture<WebSocket>`**, không phải `HttpResponse`.
- URI `ws://`/`wss://` xác định WebSocket endpoint; `wss://` dùng TLS. Một handshake thành công trao đổi HTTP/1.1 Upgrade và phản hồi `101 Switching Protocols`.
- `header(...)` chỉ dành cho **header bổ sung**, không được tự ghi đè các header WebSocket bắt buộc; `subprotocols(...)` yêu cầu thương lượng, sau khi mở kiểm tra `getSubprotocol()`.
- `connectTimeout(...)` giới hạn **thời gian mở kết nối**; các deadline cho message, heartbeat và reconnect là trách nhiệm khác.
- `Listener.onOpen` xác nhận kết nối đã mở và thường phải gọi `request(1)` để nhận dữ liệu. `onText` có thể cung cấp **các phần** của một message; chú ý `last`.
- Handshake lỗi được báo qua exceptional completion, trong đó `WebSocketHandshakeException.getResponse()` giúp đọc status/metadata HTTP khi có. Lỗi trong phiên đã mở được xử lý riêng qua listener hoặc future gửi.
- Khi đóng, theo dõi `sendClose` và `onClose`; không coi `abort` hay hủy future là một close handshake bình thường.
- Dùng TLS, xác thực, giới hạn kích thước message và kiểm tra đích đáng tin cậy. Không dùng server fixture tối giản làm server thực tế.

Nguồn tham khảo chính thức:
- [Java SE 11 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Builder.html).
- [Java SE 11 — HttpClient.newWebSocketBuilder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Java SE 11 — WebSocket](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html).
- [Java SE 11 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html).
- [Java SE 11 — WebSocketHandshakeException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocketHandshakeException.html).
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455).