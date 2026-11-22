# WebSocket.Listener.onOpen, onClose và onError trong Java 11

**Chủ đề cha:** WebSocket  
**Mục tiêu:** Xây dựng vòng đời WebSocket client đúng API `java.net.http.WebSocket.Listener` từ Java 11: khởi tạo kết nối, cấp quyền nhận callback, xử lý Close handshake, phân biệt đóng bình thường với lỗi, hoàn tất công việc và dọn tài nguyên. Các khái niệm này vẫn áp dụng cho những bản JDK hiện đại.

Java 11 cung cấp WebSocket client trong module chuẩn `java.net.http`, bên cạnh `HttpClient`. Client mở kết nối bằng `HttpClient.newWebSocketBuilder().buildAsync(uri, listener)`, sau đó `WebSocket` gọi các callback trong `WebSocket.Listener`. Ba phương thức trọng tâm của bài là **`onOpen`** (kết nối đã được thiết lập), **`onClose`** (đã nhận Close message) và **`onError`** (lỗi của kết nối sau khi mở).

Dùng đúng ba callback này không chỉ để in log: ứng dụng cần biết lúc nào được bắt đầu luồng nhận, khi nào phải hoàn tất request đang chờ, khi nào còn quyền gửi dữ liệu, và khi nào phải đánh dấu kết nối đã thất bại. **`onClose` và `onError` là hai đường kết thúc khác nhau**, còn lỗi xảy ra ngay trong lúc mở handshake có thể được báo qua future của `buildAsync` trước khi có một `WebSocket` đã mở.

## 1. Kết quả học tập

Sau bài học này, bạn có thể:

1. Kết nối đến `ws://` (thực hành local) hoặc `wss://` (dịch vụ thực) bằng Java 11 và xử lý `CompletableFuture<WebSocket>` của `buildAsync`.
2. Hiểu chính xác `onOpen(WebSocket)` là callback đầu tiên, được gọi tối đa một lần, và vì sao nên gọi `webSocket.request(1)` để cấp quyền nhận thông điệp.
3. Phân biệt một **lượt gọi callback nhận** với một **WebSocket message**; hiểu `onText` có tham số `last` và `onClose` cũng tiêu thụ một lượt receive.
4. Hiểu `onClose(WebSocket, int, String)` là callback cuối cùng sau khi nhận frame Close; lúc đó chiều **input đã đóng**, còn chiều **output** có quy tắc đóng riêng.
5. Hiểu `CompletionStage<?>` trả từ `onClose` điều phối thời điểm Java WebSocket đáp lại Close/đóng chiều output; biết khi nào dùng `null`, stage hoàn tất hoặc tự gọi `sendClose`.
6. Hiểu `onError(WebSocket, Throwable)` là callback cuối cùng khi xảy ra lỗi sau khi mở; cả **input/output đã đóng**, không xử lý nó như một Close frame bình thường.
7. Viết callback không làm nặng hoặc chặn luồng I/O, không để exception lọt ra khỏi `onError`; quản lý pending operations và reconnect qua một WebSocket **mới** nếu cần.
8. Kiểm tra toàn bộ hợp đồng bằng ba chương trình Java 11 kết nối tới WebSocket server **loopback**, không phụ thuộc Internet và không dùng `Thread.sleep()` để phỏng đoán thứ tự sự kiện.

## 2. Các thành phần và cách mở kết nối

WebSocket là giao thức giao tiếp hai chiều sau HTTP opening handshake. Client Java 11 có thể bắt đầu với:

```java
HttpClient httpClient = HttpClient.newHttpClient();

WebSocket.Listener listener = new WebSocket.Listener() {
    @Override
    public void onOpen(WebSocket socket) {
        System.out.println("WebSocket opened");
        socket.request(1);
    }
};

CompletableFuture<WebSocket> future = httpClient
        .newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .buildAsync(URI.create("wss://example.com/events"), listener);
```

Đây là **đoạn mã minh họa cần đặt trong phương thức** và import `HttpClient`, `WebSocket`, `CompletableFuture`, `Duration`, `URI`; endpoint `example.com` không được xác nhận là WebSocket server để chạy thử. Đối với hệ thống thật, dùng URL `wss://` với TLS, xác thực/ủy quyền và cấu hình subprotocol đúng hợp đồng của máy chủ. Với test local trong bài, sử dụng `ws://127.0.0.1`, không truyền thông tin nhạy cảm qua kết nối không mã hóa.

Những mốc cần phân biệt:

| Mốc | Nguồn thông tin | Có nghĩa là |
|---|---|---|
| Bắt đầu mở WebSocket | `buildAsync(uri, listener)` | Đã khởi động opening handshake, **chưa chắc thành công** |
| Handshake hoàn tất | `CompletableFuture<WebSocket>` thành công | Có đối tượng WebSocket đã kết nối |
| `onOpen` | WebSocket gọi listener | Đây là callback **đầu tiên**, được gọi tối đa một lần |
| Bắt đầu nhận inbound | `webSocket.request(n)` | Đã cho phép tối đa `n` lượt gọi **receive method** |
| `onClose` | Nhận Close message từ peer | Input đóng, sự kiện cuối của listener, output được kết thúc theo quy tắc Close |
| `onError` | WebSocket gặp lỗi sau khi đã mở | Sự kiện cuối, cả input và output đã đóng |
| Future handshake thất bại | `buildAsync` hoàn thành ngoại lệ | Có thể **không có `onOpen` / `onError`** của một kết nối đang mở |

`HttpClient.newWebSocketBuilder()` có từ Java 11; `WebSocket.Builder` có `connectTimeout`, `header` và `subprotocols`. Future có thể thất bại với `WebSocketHandshakeException` khi server từ chối opening handshake, `HttpTimeoutException` khi mở quá lâu, hoặc các lỗi kết nối khác. Phải gắn xử lý lỗi vào **future mở kết nối**; không đợi riêng `onError` để bắt mọi lỗi.

## 3. Hợp đồng ba callback trọng tâm

| Callback | Chữ ký Java 11 | Khi nào được gọi? | Trạng thái / ý nghĩa |
|---|---|---|---|
| `onOpen` | `void onOpen(WebSocket ws)` | Kết nối được thiết lập; callback đầu tiên, tối đa một lần | Thường gọi `ws.request(1)` để bắt đầu nhận |
| `onClose` | `CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason)` | Client **nhận Close message** | Là callback cuối; **input đã đóng**; stage điều phối chiều output nếu còn mở |
| `onError` | `void onError(WebSocket ws, Throwable error)` | Lỗi sau khi `onOpen` đã được gọi | Là callback cuối; **input và output đều đã đóng**; không để onError ném exception |

Một số chi tiết từ tài liệu Java SE 11 cần nhớ:

- `onOpen` mặc định thực hiện `webSocket.request(1)`. Nếu **override** nó, bạn phải tự gọi `request(...)` khi cần nhận dữ liệu.
- `onClose` mặc định **trả `null`**, nghĩa là cho phép đóng chiều output ngay nếu vẫn còn mở. `null` ở đây là một lựa chọn hợp đồng được Java WebSocket hỗ trợ, không phải lỗi.
- `onError` mặc định không thực hiện gì. Nếu bạn override để log/chuyển trạng thái, phải đảm bảo handler **không ném exception**; Javadoc nói hành vi sẽ không xác định nếu callback này ném lỗi.
- Với mỗi **một WebSocket**, các callback listener được gọi **tuần tự và không reentrant**. Không được suy ra tất cả được gọi trên cùng thread; nếu một listener được dùng cho nhiều WebSocket, callback từ **các socket khác nhau** có thể chạy đồng thời.
- `onError` có thể xảy ra sau khi `onOpen`, không cần còn demand `request(n)`. Nếu đã gọi `onClose` hoặc `onError`, Java WebSocket không gọi callback listener nào tiếp theo cho đối tượng ấy.

**Lưu ý phạm vi:** Các quy tắc trên là hợp đồng của `java.net.http.WebSocket` trong Java 11, không phải một “vòng đời” trừu tượng áp dụng y hệt cho mọi thư viện WebSocket của bên thứ ba. Khi đổi thư viện, cần đối chiếu API của thư viện đó.

## 4. onOpen: đầu tiên, một lần, nhưng chưa tự có quyền nhận vô hạn

`onOpen(WebSocket ws)` được WebSocket gọi sau khi đã kết nối và là callback đầu tiên; API không hứa nó chạy trên thread gọi `buildAsync`. Đây là nơi phù hợp để ghi nhận connection identity, khởi tạo state và cấp **receive demand** ban đầu:

```java
@Override
public void onOpen(WebSocket socket) {
    state.set(State.OPEN);
    socket.request(1);
}
```

Đây là trích đoạn minh họa, `state` và enum `State` phải do ứng dụng định nghĩa. `request(1)` không phải lệnh gửi dữ liệu hay một lời gọi đến server: nó **tăng bộ đếm nội bộ** cho phép WebSocket gọi thêm **một receive method** trên listener. Các receive methods bao gồm `onText`, `onBinary`, `onPing`, `onPong` và **`onClose`**. `onOpen` và `onError` không tiêu thụ bộ đếm demand.

### 4.1 Vì sao request(1) không phải “một message”?

Một text message có thể bị phân chia thành nhiều callback `onText(ws, data, last)`. Tham số `last=false` cho biết còn phần tiếp theo của **cùng** message, còn `last=true` đánh dấu đoạn cuối. Mỗi lần `onText` là một receive invocation và giảm counter một đơn vị; nếu không gọi `request(1)` tiếp theo, đoạn sau có thể không được chuyển vào listener.

Tương tự, ping/pong/close tiêu thụ demand riêng. Một client đã nhận xong một text message nhưng không gọi `request` tiếp có thể không nhận callback `onClose` đang chờ, dù server đã phát frame Close.

**Lệnh `request(n)` yêu cầu `n > 0`.** Gọi `request(0)` hoặc `request(-1)` ném `IllegalArgumentException`. Không dùng số lượt gọi không giới hạn khi ứng dụng cần kiểm soát bộ nhớ; lựa chọn demand phải gắn với khả năng xử lý thực tế.

### 4.2 Mẫu xử lý onText phù hợp

```java
private final StringBuilder message = new StringBuilder();

@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence fragment, boolean last) {
    message.append(fragment);
    if (last) {
        String completeMessage = message.toString();
        message.setLength(0);
        processMessage(completeMessage);  // phải ngắn hoặc điều phối async
    }
    socket.request(1);
    return CompletableFuture.completedFuture(null);
}
```

Đây là **trích đoạn trong một lớp Listener**, cần khai báo `processMessage` và các import tương ứng. Trình bày để hiểu `last`/demand; với message dài cần **giới hạn tổng số ký tự/byte**, tránh gom vô hạn. Nếu xử lý tốn thời gian, chuyển bản sao message sang một queue/executor có giới hạn rồi cân nhắc khi nào cấp demand tiếp theo.

`CompletionStage<?>` mà `onText` trả về có mục đích riêng: báo khi dữ liệu `CharSequence` được WebSocket phép **thu hồi/tái sử dụng**. Nếu trả một stage đã hoàn tất, đừng giữ tham chiếu `CharSequence` và dùng sau đó một cách tùy tiện; copy nội dung cần thiết trước khi hoàn tất stage. Việc hoàn tất stage **không tự tăng request counter**. Đây là hai cơ chế độc lập.

## 5. onClose: nhận Close, input đã đóng, output có thể còn mở

Chữ ký:

```java
@Override
public CompletionStage<?> onClose(
        WebSocket socket, int statusCode, String reason) {
    // Ghi log, cập nhật state và đánh thức những tác vụ đang chờ.
    return CompletableFuture.completedFuture(null);
}
```

`onClose` xảy ra khi nhận một **WebSocket Close message**, mang status code và reason. Nó là callback listener cuối cùng cho WebSocket đó. Tại **thời điểm callback bắt đầu**, `socket.isInputClosed()` đã là `true`. Tuy nhiên, input và output của WebSocket có vòng đời **độc lập**: khi nhận Close, output **có thể vẫn đang mở**.

`WebSocket.NORMAL_CLOSURE` có giá trị `1000`, biểu thị kết thúc bình thường. Các mã 1001, 1002, 1008, 1011... có ý nghĩa riêng theo giao thức; ứng dụng nên phân loại code dựa vào chuẩn và hợp đồng server. Không kết luận một mã 1000 đảm bảo mọi giao dịch/tiến trình nghiệp vụ đã commit thành công.

### 5.1 CompletionStage từ onClose quyết định điều gì?

Nếu chiều output chưa đóng, Java WebSocket sử dụng stage do `onClose` trả về để biết **khi nào có thể đóng chiều output**. Nó sẽ đóng output ở thời điểm sớm nhất giữa: stage hoàn tất, ứng dụng gọi `sendClose` hoặc gọi `abort`.

| Kết quả từ `onClose` | Điều được báo cho WebSocket |
|---|---|
| `return null;` | Có thể đóng output ngay; chính là hành vi mặc định của listener |
| `return CompletableFuture.completedFuture(null);` | Stage đã hoàn tất, cho phép đóng output ngay |
| `return pendingStage;` | Chưa cho phép đóng output theo đường stage cho tới khi pendingStage hoàn tất; `sendClose` hoặc `abort` vẫn có thể kết thúc sớm hơn |
| Stage **không bao giờ** hoàn tất | Về thực chất vô hiệu hóa reciprocal close theo đường stage; có nguy cơ giữ trạng thái/tài nguyên nếu không có nhánh dọn dẹp khác |

**Không đánh đồng** stage do `onClose` trả về với future của `socket.sendClose(...)`. Stage `onClose` là tín hiệu cho phép đóng output; future của `sendClose` là kết quả một thao tác **gửi** Close message do ứng dụng chủ động tạo.

**Tùy chỉnh close frame đáp lại:** Khi cần code/reason riêng theo hợp đồng, có thể gọi `socket.sendClose(customCode, reason)` trong `onClose`. Không được nhầm rằng chỉ trả stage với một giá trị số là đã tạo close frame có code tùy chỉnh. Javadoc nêu có thể gọi `sendClose` trong `onClose` để làm việc đó.

### 5.2 sendClose không đồng nghĩa cả hai chiều đã đóng

Ứng dụng có thể chủ động bắt đầu close:

```java
socket.sendClose(WebSocket.NORMAL_CLOSURE, "");
```

Đây là trích đoạn. Lệnh `sendClose` đóng **output** sau khi gửi Close thành công; **input có thể vẫn mở** cho tới khi peer gửi Close hoặc xảy ra lỗi/`abort`. Vì vậy, future của `sendClose` hoàn tất **không luôn là tín hiệu toàn bộ connection đã đóng**, và không nên giải phóng mọi state trước khi xử lý inbound close/lỗi theo chính sách.

`socket.abort()` đóng **cả hai chiều đột ngột**; không thay thế cho close handshake bình thường khi vẫn có thể trao đổi frame Close một cách trật tự. Trong thiết kế có graceful shutdown, có thể dùng `sendClose` và thời hạn chờ, rồi `abort` khi quá hạn; không làm điều này bằng blocking sleep trong callback.

### 5.3 Mã và lý do Close

Trên Java 11, `onClose` có thể nhận status code từ frame Close và reason được giải mã. Khi **chủ động gửi** `sendClose(code, reason)`, Javadoc yêu cầu code ở miền `1000..4999` và cấm một số mã reserved như `1006`, `1015`; reason có biểu diễn UTF-8 dài tối đa **123 byte**. Quy tắc 123 **byte** không phải 123 ký tự Java, vì Unicode có thể chiếm nhiều byte UTF-8.

`1006` là một mã đặc biệt dùng để mô tả đóng bất thường ở tầng chẩn đoán, **không phải mã được gửi trong Close frame**. Nếu server chết hoặc mạng đứt mà không có Close handshake, không nên tự giả định listener sẽ nhận `onClose(...,1006,...)`; thông thường xử lý qua lỗi `onError` và các cơ chế phát hiện mất kết nối/timeout.

## 6. onError: nhánh cuối, cả hai chiều đã đóng

Chữ ký:

```java
@Override
public void onError(WebSocket socket, Throwable error) {
    recordFailure(error);
    completePendingCallsExceptionally(error);
}
```

Đây là **trích đoạn trong một lớp Listener**, cần hiện thực `recordFailure` và `completePendingCallsExceptionally`. Theo Javadoc Java 11:

- `onError` là callback cuối cùng của WebSocket ấy.
- Tại lúc callback bắt đầu, `socket.isInputClosed()` và `socket.isOutputClosed()` đều là `true`.
- Nó có thể đến **bất cứ lúc nào sau `onOpen`**, kể cả chưa có demand từ `request(n)`.
- Nếu chính `onError` ném exception, hành vi tiếp theo là **không xác định**. Handler phải bắt lỗi của chính đường logging/cleanup khi cần, không để exception thoát ra.
- Nếu một receive callback khác ném exception hoặc stage trả về của receive callback kết thúc ngoại lệ, WebSocket có thể chuyển lỗi đó đến `onError`.

**Khác biệt lớn:** `onError` không nhất thiết có close status code/reason; nó mang `Throwable`. Nên lưu loại lỗi, cause, thời điểm và connection ID để chẩn đoán, nhưng tránh log token, message body bí mật hoặc stack trace chứa dữ liệu nhạy cảm không cần thiết.

### 6.1 Không “khôi phục” cùng một WebSocket sau onError

Một WebSocket đã có `onError` thì cả input/output đã đóng. Gọi `request(1)` sau đó không biến kết nối thành mở lại; `sendText`/`sendBinary` trên socket đã đóng không phải đường khôi phục.

Nếu nghiệp vụ cần reconnect, tạo **WebSocket mới** bằng `newWebSocketBuilder().buildAsync(...)` và listener/state tương ứng; sử dụng backoff, giới hạn số lần thử, khả năng xác thực lại và cơ chế resume/replay message khi giao thức server hỗ trợ. Không retry dồn dập khi server lỗi. Những tin nhắn outbound chưa có xác nhận nghiệp vụ phải được quản lý riêng với future hoàn tất của `sendText`.

### 6.2 Không phải mọi lỗi sẽ dẫn đến onError

Nếu opening handshake thất bại (ví dụ HTTP 403, TLS failure, timeout), `buildAsync` có thể hoàn tất ngoại lệ **trước khi có WebSocket mở thành công**. Không viết code chỉ chờ `onError` mà bỏ qua `CompletableFuture` từ `buildAsync`. Cần xử lý:

```java
client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .buildAsync(uri, listener)
        .whenComplete((socket, failure) -> {
            if (failure != null) {
                // Ghi nhận handshake/connect failure.
                return;
            }
            // Connection đã được thiết lập; listener nhận onOpen.
        });
```

Đây là **trích đoạn**, cần khai báo `client`, `uri`, `listener`; không phải ví dụ biên dịch độc lập. `whenComplete` chỉ xử lý kết quả future xây dựng. Nó **không thay thế** callback `onClose`/`onError` cho vòng đời sau khi đã kết nối.

## 7. Sơ đồ vòng đời kết nối

```text
                      buildAsync(uri, listener)
                               |
                    +----------+-----------+
                    |                      |
             handshake lỗi          handshake thành công
                    |                      |
          future exceptional              onOpen
          chưa có socket OPEN               |
                                           request(n)
                                              |
                                  onText / onBinary / Ping / Pong
                                              |
                               +--------------+--------------+
                               |                             |
                          nhận Close                      lỗi I/O/callback
                               |                             |
                            onClose                       onError
                        input đã đóng                 cả input/output đóng
                               |                             |
              stage hoàn tất / sendClose / abort              |
                               |                             |
                         output đóng                   kết thúc thất bại
                               |
                        kết thúc có Close
```

**Điểm quan trọng của sơ đồ:** `onClose` không có đường đi tiếp sang `onError` trong cùng vòng listener theo hợp đồng “callback cuối”; `onError` cũng không phải một lời hứa rằng sẽ có `onClose` sau đó. Tuy nhiên thao tác outbound do ứng dụng đã khởi động có future riêng cần được xử lý; không dùng duy nhất thứ tự callback để suy ra mọi send đã commit.

### 7.1 Tách trạng thái protocol và trạng thái nghiệp vụ

Một state machine ứng dụng có thể dùng `CONNECTING`, `OPEN`, `CLOSING`, `CLOSED`, `FAILED`, nhưng cần biết đây là **trạng thái do ứng dụng định nghĩa**. `WebSocket` API chỉ cung cấp `isInputClosed()`/`isOutputClosed()`, không cung cấp enum ấy. Một lần `sendClose` hoàn tất có thể đưa output về closed nhưng input vẫn open; do đó enum quá đơn giản có thể che trạng thái half-close.

Nên có terminal completion riêng:

```java
CompletableFuture<Void> terminated = new CompletableFuture<>();

// Trong onClose:
terminated.complete(null);

// Trong onError:
terminated.completeExceptionally(error);
```

Đây là trích đoạn thiết kế, không phải chương trình đầy đủ. Nếu handshake thất bại, future `buildAsync` cũng phải được chuyển vào trạng thái kết thúc phù hợp. `CompletableFuture.complete` chỉ thành công cho lần hoàn tất đầu tiên, thuận tiện để tránh thông báo terminal trùng lặp trong tầng ứng dụng. Nếu callback có chạy trên nhiều socket khác nhau, mỗi connection nên có future/trạng thái riêng.

## 8. Ví dụ chạy được 1 — vòng đời bình thường, lỗi listener và handshake bị từ chối

Ví dụ đầu tiên hoàn toàn chạy trên loopback `127.0.0.1`. Vì JDK 11 **không cung cấp một WebSocket server public API đơn giản tương đương client**, bài test mở một `ServerSocket` nhỏ chỉ để đáp ứng handshake và một vài frame WebSocket cố định. Phần server dùng SHA-1 + magic GUID để tạo `Sec-WebSocket-Accept`, gửi text frame, Close frame và nhận Close hồi đáp. Nó **chỉ là WebSocket test fixture tối giản**, không phải server hoàn chỉnh, không được đưa vào production hoặc Internet.

Ba tình huống được thử:

1. **NORMAL:** onOpen → nhận text `"hello"` → onClose code `1000`/reason `done`. Trong onClose, `isInputClosed()` đã true.
2. **LISTENER_FAILURE:** cùng handshake thành công, nhưng `onText` cố tình ném `IllegalStateException("bad-message")`. Java WebSocket chuyển sang `onError`, và cả input/output đã closed. Đây là kỹ thuật test lỗi có chủ đích, **không phải cách xử lý message lỗi trong ứng dụng thật**.
3. **REJECT_HANDSHAKE:** server trả HTTP 403 ngay trong handshake. `buildAsync` hoàn tất ngoại lệ `WebSocketHandshakeException`; không dựa vào `onError` để nhận lỗi này.

Listener ghi lại sự kiện vào danh sách sau khi đã được callback theo thứ tự; main chỉ in sau khi latch terminal đã hoàn tất, giúp stdout dễ kiểm chứng. Vì WebSocket bảo đảm callback **tuần tự trên mỗi socket** nhưng không hứa một thread cố định, ứng dụng sản xuất nên dùng state an toàn khi nhiều socket hoặc nhiều tác vụ khác cùng truy cập.

Lưu file **`WebSocketLifecycleDemo.java`**:

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
import java.net.http.WebSocketHandshakeException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

public class WebSocketLifecycleDemo {
    enum Mode { NORMAL, LISTENER_FAILURE, REJECT_HANDSHAKE }

    static final class LocalWsServer implements AutoCloseable {
        private final ServerSocket server;
        private final Thread thread;
        private final CompletableFuture<Void> finished = new CompletableFuture<>();
        private final Mode mode;

        LocalWsServer(Mode mode) throws IOException {
            this.mode = mode;
            this.server = new ServerSocket(
                    0, 1, InetAddress.getByName("127.0.0.1"));
            this.thread = new Thread(this::serve, "local-ws-server");
            thread.setDaemon(true);
            thread.start();
        }

        URI uri() {
            return URI.create("ws://127.0.0.1:" + server.getLocalPort() + "/ws");
        }

        private void serve() {
            try (Socket client = server.accept()) {
                client.setSoTimeout(5000);
                InputStream input = client.getInputStream();
                OutputStream output = client.getOutputStream();
                String headers = readHeaders(input);
                String key = null;
                for (String line : headers.split("\r\n")) {
                    if (line.toLowerCase(Locale.ROOT).startsWith(
                            "sec-websocket-key:")) {
                        key = line.substring(line.indexOf(':') + 1).trim();
                    }
                }
                if (key == null) throw new IOException("Missing WebSocket key");
                if (mode == Mode.REJECT_HANDSHAKE) {
                    output.write(("HTTP/1.1 403 Forbidden\r\n"
                            + "Content-Length: 0\r\nConnection: close\r\n\r\n")
                            .getBytes(StandardCharsets.US_ASCII));
                    output.flush();
                    finished.complete(null);
                    return;
                }
                byte[] digest = MessageDigest.getInstance("SHA-1").digest(
                        (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                        .getBytes(StandardCharsets.US_ASCII));
                String accept = Base64.getEncoder().encodeToString(digest);
                String response = "HTTP/1.1 101 Switching Protocols\r\n"
                        + "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                        + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
                output.write(response.getBytes(StandardCharsets.US_ASCII));
                output.flush();

                if (mode == Mode.NORMAL) {
                    writeFrame(output, 0x81,
                            "hello".getBytes(StandardCharsets.UTF_8));
                    byte[] reason = "done".getBytes(StandardCharsets.UTF_8);
                    byte[] close = new byte[2 + reason.length];
                    close[0] = 0x03;
                    close[1] = (byte) 0xE8;
                    System.arraycopy(reason, 0, close, 2, reason.length);
                    writeFrame(output, 0x88, close);
                    consumeClientClose(input);
                } else {
                    writeFrame(output, 0x81,
                            "broken".getBytes(StandardCharsets.UTF_8));
                    // onText intentionally throws; Java WebSocket closes both sides.
                    while (input.read() != -1) {
                        // Drain any bytes until client closes after onError.
                    }
                }
                finished.complete(null);
            } catch (Throwable error) {
                finished.completeExceptionally(error);
            }
        }

        static String readHeaders(InputStream input) throws IOException {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            int match = 0, current;
            while ((current = input.read()) != -1) {
                bytes.write(current);
                match = current == "\r\n\r\n".charAt(match)
                        ? match + 1 : current == '\r' ? 1 : 0;
                if (match == 4) {
                    return new String(bytes.toByteArray(),
                            StandardCharsets.US_ASCII);
                }
                if (bytes.size() > 8192) throw new IOException("Header too large");
            }
            throw new IOException("Handshake ended early");
        }

        static void writeFrame(OutputStream output, int firstByte, byte[] data)
                throws IOException {
            if (data.length >= 126) throw new IllegalArgumentException();
            output.write(firstByte);
            output.write(data.length); // Server-to-client frames are unmasked.
            output.write(data);
            output.flush();
        }

        static void consumeClientClose(InputStream input) throws IOException {
            int opcode = input.read(), length = input.read();
            if (opcode != 0x88 || (length & 0x80) == 0) {
                throw new IOException("Expected masked Close frame");
            }
            int count = length & 0x7F;
            if (count >= 126) throw new IOException("Unexpected size");
            byte[] mask = new byte[4], data = new byte[count];
            readFully(input, mask);
            readFully(input, data);
            for (int i = 0; i < count; i++) data[i] ^= mask[i % 4];
            if (count < 2 || data[0] != 0x03 || data[1] != (byte) 0xE8) {
                throw new IOException("Expected normal close code");
            }
        }

        static void readFully(InputStream input, byte[] data)
                throws IOException {
            int offset = 0;
            while (offset < data.length) {
                int n = input.read(data, offset, data.length - offset);
                if (n < 0) throw new IOException("Unexpected EOF");
                offset += n;
            }
        }

        void awaitServer() throws Exception {
            finished.get(5, TimeUnit.SECONDS);
        }

        @Override
        public void close() throws Exception {
            server.close();
            thread.join(5000);
        }
    }

    static final class RecordingListener implements WebSocket.Listener {
        final Mode mode;
        final List<String> events = new ArrayList<>();
        final CountDownLatch terminal = new CountDownLatch(1);

        RecordingListener(Mode mode) {
            this.mode = mode;
        }

        @Override
        public void onOpen(WebSocket socket) {
            events.add("open");
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket socket, CharSequence data, boolean last) {
            if (mode == Mode.LISTENER_FAILURE) {
                throw new IllegalStateException("bad-message");
            }
            events.add("text=" + data + ",last=" + last);
            socket.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket socket, int statusCode, String reason) {
            events.add("close=" + statusCode + ":" + reason);
            events.add("input-closed=" + socket.isInputClosed());
            terminal.countDown();
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            events.add("error=" + error.getClass().getSimpleName()
                    + ":" + error.getMessage());
            events.add("both-closed=" + (socket.isInputClosed()
                    && socket.isOutputClosed()));
            terminal.countDown();
        }

        void awaitTerminal() throws InterruptedException {
            if (!terminal.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Listener terminal timeout");
            }
        }
    }

    static void run(Mode mode) throws Exception {
        try (LocalWsServer server = new LocalWsServer(mode)) {
            RecordingListener listener = new RecordingListener(mode);
            HttpClient client = HttpClient.newHttpClient();
            if (mode == Mode.REJECT_HANDSHAKE) {
                try {
                    client.newWebSocketBuilder()
                            .connectTimeout(Duration.ofSeconds(5))
                            .buildAsync(server.uri(), listener)
                            .get(5, TimeUnit.SECONDS);
                    throw new AssertionError("Handshake should fail");
                } catch (ExecutionException expected) {
                    System.out.println("handshake-rejected="
                            + (expected.getCause()
                            instanceof WebSocketHandshakeException));
                }
            } else {
                WebSocket socket = client.newWebSocketBuilder()
                        .connectTimeout(Duration.ofSeconds(5))
                        .buildAsync(server.uri(), listener)
                        .get(5, TimeUnit.SECONDS);
                listener.awaitTerminal();
                server.awaitServer();
                System.out.println(mode.name().toLowerCase(Locale.ROOT)
                        + "-events=" + listener.events);
                System.out.println(mode.name().toLowerCase(Locale.ROOT)
                        + "-input-closed=" + socket.isInputClosed());
            }
            if (mode == Mode.REJECT_HANDSHAKE) server.awaitServer();
        }
    }

    public static void main(String[] args) throws Exception {
        run(Mode.NORMAL);
        run(Mode.LISTENER_FAILURE);
        run(Mode.REJECT_HANDSHAKE);
    }
}
```

Biên dịch và chạy bằng JDK 11 (hoặc JDK mới hơn còn hỗ trợ target Java 11):

```bash
javac --release 11 -encoding UTF-8 WebSocketLifecycleDemo.java
java WebSocketLifecycleDemo
```

**Đầu ra chính xác đã kiểm chứng:**

```text
normal-events=[open, text=hello,last=true, close=1000:done, input-closed=true]
normal-input-closed=true
listener_failure-events=[open, error=IllegalStateException:bad-message, both-closed=true]
listener_failure-input-closed=true
handshake-rejected=true
```

### Giải thích kết quả

- `open` luôn đứng đầu cho từng WebSocket; `onOpen` gọi `request(1)` nên có thể nhận text.
- `onText` nhận nội dung `hello` và `last=true`, sau đó gọi `request(1)` để cho phép listener nhận sự kiện kế tiếp (Close).
- `onClose` nhận `1000` và `done`, ghi nhận input đã đóng. Không có `onError` trong nhánh bình thường.
- Ở nhánh lỗi, việc ném exception từ `onText` dẫn tới `onError`; không có `onClose` tiếp theo. `both-closed=true` phù hợp Javadoc.
- HTTP 403 từ server test khiến opening handshake thất bại; `buildAsync` có exception. Đó là lỗi **mở kết nối**, không phải Close frame.

**An toàn:** Chương trình giới hạn header 8 KiB, kích thước frame cố định nhỏ, socket loopback và timeout để test không treo vô hạn. Nó không kiểm tra mọi luật RFC 6455, không hỗ trợ fragmentation, masking phức tạp, extension, TLS, nhiều kết nối hoặc độ lớn payload thực tế. Server production phải dùng thư viện/network stack có triển khai đầy đủ giao thức.

## 9. Ví dụ chạy được 2 — CompletionStage của onClose điều khiển thời điểm đóng output

Để chứng minh ý nghĩa stage do `onClose` trả về, listener tiếp theo nhận Close nhưng trả **`CompletableFuture<Void>` chưa hoàn tất**. Khi callback đã xảy ra:

- Input đã đóng.
- Output vẫn mở vì stage chưa xong và ứng dụng chưa gọi `sendClose`/`abort`.
- Sau khi hoàn tất stage, Java WebSocket được phép đóng output và server test nhận Close hồi đáp.

Chương trình này **sử dụng lại class hỗ trợ `LocalWsServer` đã định nghĩa ở file WebSocketLifecycleDemo.java**; đặt hai file trong cùng thư mục/default package rồi biên dịch **cùng nhau**. Như vậy không cần sao chép một RFC 6455 test fixture dài vào mỗi ví dụ.

Lưu thành **`WebSocketCloseStageDemo.java`**:

```java
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class WebSocketCloseStageDemo {
    static final class HoldingListener implements WebSocket.Listener {
        final CompletableFuture<Void> allowClose = new CompletableFuture<>();
        final CountDownLatch closeSeen = new CountDownLatch(1);
        volatile Throwable failure;

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket socket, CharSequence text, boolean last) {
            socket.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket socket, int statusCode, String reason) {
            closeSeen.countDown();
            return allowClose;
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            closeSeen.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        try (WebSocketLifecycleDemo.LocalWsServer server =
                new WebSocketLifecycleDemo.LocalWsServer(
                        WebSocketLifecycleDemo.Mode.NORMAL)) {
            HoldingListener listener = new HoldingListener();
            WebSocket socket = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(5))
                    .buildAsync(server.uri(), listener)
                    .get(5, TimeUnit.SECONDS);

            if (!listener.closeSeen.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Close callback timeout");
            }
            if (listener.failure != null) {
                throw new IllegalStateException("Unexpected onError", listener.failure);
            }
            System.out.println("input-closed-at-onClose="
                    + socket.isInputClosed());
            System.out.println("output-closed-while-stage-pending="
                    + socket.isOutputClosed());

            listener.allowClose.complete(null);
            server.awaitServer();
            System.out.println("output-closed-after-stage="
                    + socket.isOutputClosed());
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 WebSocketLifecycleDemo.java WebSocketCloseStageDemo.java
java WebSocketCloseStageDemo
```

```text
input-closed-at-onClose=true
output-closed-while-stage-pending=false
output-closed-after-stage=true
```

**Tại sao đáng kiểm thử?** Nhiều code suy rằng “nhận Close → cả hai chiều đóng ngay”. Trên Java 11, điều đó không hoàn toàn đúng: `onClose` bắt đầu khi **input đã đóng**, còn chiều gửi có thể chờ stage. Nếu logic trì hoãn Close không có timeout/cơ chế hoàn tất, nó có thể khiến connection giữ tài nguyên. Trong code thực tế chỉ nên giữ stage pending khi thật sự có công việc ngắn, có thời hạn rõ ràng. Không tạo stage never-completing rồi hy vọng ứng dụng vẫn graceful close.

## 10. Ví dụ chạy được 3 — request(1) là một lượt callback, kể cả Close

Ví dụ thứ ba cố ý **override `onOpen` mà không gọi `request(1)`**. Server vẫn gửi text và Close, nhưng listener chưa được phép nhận receive callback. Main sau đó cấp một lượt demand: nhận `onText`. Vì `onText` không gọi `request(1)` tiếp, `onClose` vẫn chưa được chuyển tới listener. Chỉ khi main gọi `request(1)` lần hai thì Close callback mới chạy.

Chương trình dùng lại class hỗ trợ `LocalWsServer` trong file thứ nhất; biên dịch hai file cùng nhau, không cần Internet.

Lưu thành **`WebSocketDemandDemo.java`**:

```java
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class WebSocketDemandDemo {
    static final class DemandListener implements WebSocket.Listener {
        final CountDownLatch opened = new CountDownLatch(1);
        final CountDownLatch message = new CountDownLatch(1);
        final CountDownLatch closed = new CountDownLatch(1);
        volatile String text = "";
        volatile int closeCode = -1;
        volatile Throwable failure;

        @Override
        public void onOpen(WebSocket socket) {
            // Unlike the default implementation, we deliberately request nothing.
            opened.countDown();
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket socket, CharSequence data, boolean last) {
            text = data.toString();
            message.countDown();
            // Deliberately do not request the next receive invocation.
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket socket, int statusCode, String reason) {
            closeCode = statusCode;
            closed.countDown();
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            failure = error;
            opened.countDown();
            message.countDown();
            closed.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        try (WebSocketLifecycleDemo.LocalWsServer server =
                new WebSocketLifecycleDemo.LocalWsServer(
                        WebSocketLifecycleDemo.Mode.NORMAL)) {
            DemandListener listener = new DemandListener();
            WebSocket socket = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(5))
                    .buildAsync(server.uri(), listener)
                    .get(5, TimeUnit.SECONDS);

            if (!listener.opened.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("onOpen timeout");
            }
            if (listener.failure != null) throw new IllegalStateException(listener.failure);
            System.out.println("message-without-request="
                    + (listener.message.getCount() == 0));

            socket.request(1);
            if (!listener.message.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("onText timeout");
            }
            if (listener.failure != null) throw new IllegalStateException(listener.failure);
            System.out.println("message-after-request=" + listener.text);
            System.out.println("close-without-second-request="
                    + (listener.closed.getCount() == 0));

            socket.request(1);
            if (!listener.closed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("onClose timeout");
            }
            server.awaitServer();
            System.out.println("close-after-second-request="
                    + listener.closeCode);
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 WebSocketLifecycleDemo.java WebSocketDemandDemo.java
java WebSocketDemandDemo
```

```text
message-without-request=false
message-after-request=hello
close-without-second-request=false
close-after-second-request=1000
```

Điểm cốt lõi: nếu bạn override `onOpen` nhưng quên demand, chương trình có thể **kết nối thành công mà không nhận bất kỳ text/close callback nào**. Khi có text, việc gọi `request(1)` tiếp là điều kiện để tiến tới event tiếp theo. Đừng sửa lỗi bằng cách gọi `Thread.sleep` lâu hơn: đó là **flow control**, không phải vấn đề “server gửi chưa kịp”.

Ví dụ chủ động để `onError` chỉ ghi lại lỗi và đánh thức các latch, **không ném exception từ onError**. Main mới là nơi kiểm tra lỗi và ném exception nếu test không đúng. Đó là cách tổ chức quan trọng cho callback lỗi trong ứng dụng thực tế.

## 11. Lập trình bất đồng bộ và tránh lỗi lifecycle

### 11.1 Không block trong callback

Một số thao tác có vẻ tiện nhưng nguy hiểm khi chạy trong callback WebSocket:

- `future.join()`/`future.get()` trên một future phụ thuộc chính WebSocket callback hiện tại.
- `Thread.sleep` hoặc xử lý CPU nặng khi hàng đợi inbound đang phát dữ liệu.
- Gọi network API đồng bộ, truy vấn DB chậm hoặc lấy lock có thể bị giữ bởi worker đang đợi kết quả của callback.
- Đưa message vào queue không có giới hạn trong khi tự động gọi `request(Long.MAX_VALUE)` liên tục.

WebSocket.Listener bảo đảm **các invocation tuần tự trên cùng một socket**. Callback nặng có thể trì hoãn mọi inbound event tiếp theo, kể cả `onClose`. Thay vì làm công việc nặng trong `onText`, copy message cần thiết, enqueue sang worker pool có giới hạn, điều phối demand phù hợp với throughput thực tế và dùng `CompletionStage` để bảo vệ vòng đời dữ liệu khi cần.

Nếu listener được dùng cho **nhiều** socket, callback thuộc các socket khác nhau có thể chạy đồng thời. Không dùng một `StringBuilder`/`ArrayList` chung mà không đồng bộ cho tất cả kết nối. Mỗi socket nên có connection state riêng, hoặc phải dùng concurrent data structure.

### 11.2 Phân biệt request demand và CompletionStage

| Cơ chế | Nó quyết định | Nó không làm |
|---|---|---|
| `socket.request(n)` | Số lượt WebSocket được phép gọi receive methods thêm | Không đợi xử lý message, không tự tạo outbound send |
| Stage từ `onText/onBinary` | Khi WebSocket được phép thu hồi buffer/fragment đã trao | Không tự tăng demand counter |
| Stage từ `onClose` | Khi output được phép đóng sau khi nhận Close | Không có nghĩa một nghiệp vụ bên ngoài đã commit |
| Future của `sendText/sendClose` | Trạng thái thao tác outbound tương ứng | Không tự xác nhận peer đã xử lý message ở tầng ứng dụng |
| Future của `buildAsync` | Opening handshake thành công/thất bại | Không bao trùm mọi lỗi lifecycle sau khi mở |

Một mốc `sendText(...).thenAccept` chỉ chứng minh thao tác gửi theo API đã hoàn tất, **không** chứng minh phía server đã ghi DB hoặc trả business ACK. Nếu cần đảm bảo delivery theo nghiệp vụ, xây cơ chế request ID/ack, idempotency và timeout ở tầng protocol.

### 11.3 Đồng bộ terminal completion mà không tự tạo deadlock

Thực tế nên có một `CompletableFuture` riêng cho trạng thái kết thúc và một vòng đời connection object:

```java
final CompletableFuture<CloseInfo> finished = new CompletableFuture<>();

// onClose:
finished.complete(new CloseInfo(code, reason));

// onError:
finished.completeExceptionally(error);
```

Đây là trích đoạn ý tưởng; `CloseInfo` là kiểu kết quả do ứng dụng tự định nghĩa. Future cho phép một thread khác đợi kết thúc **ở ngoài callback**, kiểm tra nguyên nhân và dọn dẹp. Đừng gọi `finished.join()` ngay trong onClose/onError vì sẽ tự chờ chính mình hoặc đường xử lý liên quan.

Một người dùng có thể chủ động đóng bằng `sendClose`, nhưng đừng hoàn tất `finished` chỉ vì future outbound Close xong nếu hợp đồng của bạn đòi nhận inbound Close nữa. Cần có timeout/graceful shutdown và phương án `abort` khi peer im lặng.

### 11.4 Kiểm tra trạng thái input/output

`WebSocket` cho phép:

```java
boolean inboundEnded = socket.isInputClosed();
boolean outboundEnded = socket.isOutputClosed();
```

Đây là trích đoạn. Hai cờ độc lập và sau khi true thì vẫn true. `onClose` bắt đầu với input closed; output còn tùy stage/`sendClose`/`abort`. `onError` bắt đầu khi cả hai closed. Đừng suy ra kết nối “OPEN” chỉ vì `isOutputClosed()==false` nếu input đã đóng.

### 11.5 Logging và metric

Một mô hình quan sát dễ hiểu:

| Event | Thu thập | Ý nghĩa |
|---|---|---|
| `connect_started` | URI/host đã cho phép, request ID | Bắt đầu handshake |
| `connect_failed` | Throwable từ `buildAsync` | Chưa thiết lập WebSocket thành công |
| `open` | Timestamp của `onOpen`, connection ID | Connection đã được mở |
| `receive_demand` | Số lượt `request(n)` | Flow control thực tế |
| `message_fragment` | Độ dài, `last`, loại text/binary | Nhận dữ liệu; chưa chắc hoàn tất message |
| `close_received` | Status code, reason đã lọc dữ liệu nhạy cảm | Nhận Close, input đóng |
| `error_terminated` | Loại lỗi và cause từ `onError` | Kết thúc bất thường, hai chiều đóng |
| `close_output_sent` | Completion future của `sendClose` | Đã gửi close frame theo API |
| `connection_terminated` | Terminal future của ứng dụng | Kết thúc lifecycle; cleanup/reconnect policy |

Đừng log toàn bộ payload, credential trên header handshake hoặc token trong URI. Reason của Close có thể do phía server gửi; coi nó là **dữ liệu ngoài tin cậy**, không đưa thẳng vào UI/alert có quyền cao hoặc query/log không kiểm soát.

## 12. Xử lý Close bình thường, lỗi mạng và reconnect

### 12.1 Close bình thường

Một flow điển hình là ứng dụng chủ động gửi `sendClose(WebSocket.NORMAL_CLOSURE, "")` hoặc nhận Close từ peer. Khi nhận Close, `onClose` lưu code/reason, thông báo các phần phụ thuộc, rồi trả một stage hoàn tất hoặc `null` để đóng output theo hợp đồng. Không bắt buộc người dùng tự gửi Close hồi đáp trong mọi trường hợp, vì WebSocket API Java xử lý Close/Pong theo giao thức.

### 12.2 Lỗi bất thường

Ví dụ: kết nối đứt, decode lỗi, listener callback ném exception, stage receive hoàn tất ngoại lệ. `onError` nhận Throwable và báo kết thúc. Handler không ném thêm lỗi; chỉ ghi nhận một lần và đánh thức những pending promise. Nếu nghiệp vụ cần retry, tạo client socket mới; retry phải có backoff + jitter khi thích hợp và không tự phát lại message chưa được server xác nhận.

### 12.3 Handshake bị từ chối

Một server có thể trả HTTP 401/403, 404, hoặc không hỗ trợ WebSocket upgrade. Khi `buildAsync` trả exception, hãy xử lý handshake failure riêng. Nếu đó là auth failure, cần xác thực lại hoặc sửa quyền; đừng gọi reconnect vô hạn với cùng thông tin sai.

### 12.4 Thời gian chờ

`WebSocket.Builder.connectTimeout` là **timeout thiết lập kết nối**, không phải một keep-alive/idle timeout mặc định cho toàn bộ phiên WebSocket đã mở. Với phiên sống dài, cần cơ chế health check/heartbeat có giới hạn và deadline phù hợp giao thức sản phẩm. API `sendPing` có thể gửi Ping và Java WebSocket tự đáp Pong khi nhận Ping, nhưng không tự biến nó thành hệ thống timeout/reconnect mà ứng dụng không cấu hình.

Nếu client gửi `sendClose` rồi peer không bao giờ trả Close, xây timer ở tầng ứng dụng để `abort` sau ngưỡng hợp lý; không block callback bằng `Thread.sleep` để đợi timer.

### 12.5 Bảo mật

Sử dụng `wss://` cho sản phẩm qua Internet để bảo vệ dữ liệu in transit, xác thực endpoint/certificate và chỉ gửi credential/subprotocol theo server contract. Không cho phép URI WebSocket do bên ngoài kiểm soát tùy ý trỏ vào mạng nội bộ. Giới hạn kích thước message tích lũy, validate schema và rate limit reconnect/send. Khả năng nhận message từ WebSocket không đồng nghĩa dữ liệu đó đáng tin.

## 13. Ma trận kiểm thử hợp đồng

| Ca | Bước thiết lập | Kết quả mong đợi |
|---|---|---|
| Open thành công | Server trả handshake HTTP 101 hợp lệ | `onOpen` đầu tiên, tối đa một lần |
| Default `onOpen` | Không override | Gọi `request(1)` theo hành vi mặc định |
| Override `onOpen` không request | Server gửi text | Không có `onText` cho tới khi được cấp demand |
| Demand một lần | `request(1)` khi server đã gửi text | Một receive callback được phép chạy |
| Nhiều fragment | Text message chia nhiều phần với `last=false` | Cần request thêm theo từng invocation |
| Close bị giữ bởi demand | Nhận text nhưng không request tiếp | `onClose` chưa được gọi cho tới khi cấp lượt mới |
| Normal Close | Server gửi code 1000/reason done | `onClose` là callback cuối; input closed |
| Stage pending trong `onClose` | Trả future chưa hoàn tất | Output còn mở trong khi chờ stage (nếu chưa sendClose/abort) |
| Stage hoàn tất | Hoàn tất future từ onClose | Output có thể đóng và gửi Close hồi đáp |
| `sendClose` từ client | Chủ động gửi Close 1000 | Output đóng theo send future; input có thể còn mở |
| Listener `onText` ném lỗi | Gây lỗi có chủ đích | `onError`, cả hai chiều đóng, không có onClose sau |
| `onError` không ném | Handler chỉ log/state/future | Không gây thêm lỗi không xác định |
| Server ngắt mạng đột ngột | Cắt socket không có Close | Xử lý lỗi, không giả lập nhận frame Close 1006 |
| Handshake HTTP 403 | Server từ chối upgrade | Future `buildAsync` exceptional; không chờ onClose |
| Close code trái quy tắc | Gửi code bị cấm bằng `sendClose` | `IllegalArgumentException` theo API |
| Reconnect | Đóng hoặc lỗi rồi tạo kết nối mới | WebSocket mới, listener/state mới; không reuse socket đã đóng |
| Nhiều socket chung listener | Các callback có thể xen kẽ giữa sockets | State được tách/đồng bộ |
| Callback async giữ reference fragment | Stage hoàn tất trước khi đọc dữ liệu | Có nguy cơ dùng buffer đã được reclaim; copy trước |
| Graceful shutdown peer im lặng | Client gửi close và chờ deadline | Abort theo policy, không block callback vô hạn |

Các ví dụ trong bài dùng latch và timeout để tránh bài test flaky. Với hệ thống thật, ngoài unit/loopback test, nên dùng một WebSocket server chuẩn hỗ trợ TLS, ping/pong, fragmentation, close codes, proxy và nhiều client, nhưng vẫn giữ **cùng hợp đồng kiểm thử** cho onOpen/onClose/onError.

## 14. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Hướng đúng |
|---|---|---|
| Override `onOpen` nhưng quên `request(1)` | Kết nối mở nhưng không nhận text/close callback | Cấp demand ban đầu |
| Coi `request(1)` là một message hoàn chỉnh | Text fragmented có thể còn đoạn chưa nhận | Xét `last` và cấp demand cho từng invocation |
| Chỉ cấp demand cho text rồi quên Close | `onClose` có thể không được gọi | Cấp demand đúng vòng đời |
| Nghĩ `onOpen` chạy trên thread của `buildAsync` | Race state hoặc UI update | Không giả định callback thread cố định |
| Xem `onClose` nghĩa cả hai chiều đã đóng ngay | Output có thể chờ CompletionStage | Phân biệt input/output |
| Trả stage không bao giờ hoàn tất trong onClose | Reciprocal closure không tiến triển | Có giới hạn thời gian hoặc hoàn tất stage |
| Tự gửi Close hồi đáp hai lần | Dư thừa/thao tác sai trạng thái | Hiểu cơ chế tự động phản hồi của Java |
| Gọi `sendClose` xong rồi coi inbound đã đóng | Input có thể vẫn open | Chờ onClose/onError hoặc timeout |
| Bắt mạng đứt bằng `onClose(1006)` giả định | Không phải Close frame thông thường | Xử lý `onError`/transport errors |
| Chỉ bắt lỗi trong `onError` | Handshake fail có thể chỉ nằm trong buildAsync future | Xử lý cả future xây WebSocket |
| Ném exception trong `onError` | Hành vi WebSocket không xác định | Handler không ném; lỗi ghi log được cô lập |
| Cố gửi lại trên socket đã onError | Cả input/output đã đóng | Tạo socket mới, retry có backoff |
| Chặn trong listener callback | Chậm toàn bộ inbound, dễ deadlock | Xử lý ngắn, chuyển việc sang worker |
| Trả stage onText hoàn tất rồi giữ `CharSequence` để đọc sau | Dữ liệu có thể bị reclaim | Copy dữ liệu trước khi hoàn tất stage |
| Dùng listener chung mutable state cho nhiều socket không đồng bộ | Data race giữa sockets | Connection state riêng/thread-safe |
| Log nguyên payload/token/reason | Rò dữ liệu nhạy cảm | Lọc/ẩn thông tin, giới hạn log |
| Dùng `ws://` cho dữ liệu nhạy cảm trên Internet | Không có bảo vệ TLS | Dùng `wss://` và cấu hình TLS hợp lệ |
| Gửi Close reason theo số ký tự thay vì byte UTF-8 | Có thể vượt giới hạn 123 byte | Kiểm tra giới hạn byte và code hợp lệ |

## 15. Bài tập có đáp án

**Bài 1 — callback nào chạy trước?** Một WebSocket được xây thành công và đã mở. Callback nào được bảo đảm là đầu tiên?  
**Đáp án:** `onOpen`, được gọi tối đa một lần. Từ đó listener thường gọi `request(1)` để nhận callback dữ liệu.

**Bài 2 — override mặc định.** Bạn viết `@Override onOpen` chỉ để log rồi không gọi `request`. Server đã gửi `"hi"`. Có bắt buộc `onText` được gọi không?  
**Đáp án:** không. Counter nhận ban đầu là 0; phải gọi `request(n)` để cấp lượt nhận.

**Bài 3 — hai callback.** Server gửi một text message có hai fragment, `last=false` rồi `last=true`. `request(1)` đủ cho cả message không?  
**Đáp án:** không. Nó cấp một lượt receive invocation; cần cấp demand cho fragment tiếp theo.

**Bài 4 — onClose có thể chưa đến.** Listener đã nhận xong text rồi không request thêm. Server gửi Close. Vì sao onClose có thể chưa chạy?  
**Đáp án:** onClose là receive method và tiêu thụ demand; nếu counter 0, callback bị giữ cho đến khi có lượt nhận.

**Bài 5 — input/output.** Trong `onClose`, `socket.isInputClosed()` là gì? `isOutputClosed()` chắc chắn cùng giá trị không?  
**Đáp án:** input đã closed. Output chưa chắc: có thể chờ CompletionStage từ onClose, `sendClose` hoặc `abort`.

**Bài 6 — stage pending.** Trả `CompletableFuture` chưa hoàn tất từ `onClose` để làm gì?  
**Đáp án:** trì hoãn việc Java WebSocket đóng output theo đường reciprocal closure. Nếu không hoàn tất stage thì có thể làm đóng kết nối không tiến triển; cần deadline/cơ chế cleanup.

**Bài 7 — onError.** `onError` được gọi sau lỗi ném từ `onText`. Input và output ở trạng thái nào? Có `onClose` tiếp theo không?  
**Đáp án:** cả hai đã đóng; `onError` là callback cuối cùng cho WebSocket đó, không có onClose sau.

**Bài 8 — handshake từ chối.** Server HTTP 403 khi opening handshake. Bạn chờ `onError` mà không xử lý future `buildAsync`. Có đúng không?  
**Đáp án:** không. `buildAsync` có thể hoàn tất ngoại lệ trước khi socket được mở; phải xử lý future xây dựng.

**Bài 9 — close bình thường.** `sendClose(WebSocket.NORMAL_CLOSURE,"")` hoàn tất nghĩa là gì?  
**Đáp án:** thao tác gửi Close và đóng chiều output đã hoàn tất theo API; không tự chứng minh input đã đóng hoặc peer đã commit dữ liệu nghiệp vụ.

**Bài 10 — không throw.** Vì sao `onError` không nên ném exception dù log thất bại?  
**Đáp án:** Javadoc quy định hành vi là không xác định nếu onError ném; cô lập lỗi logging/cleanup và báo lỗi qua state/future ở tầng ứng dụng.

**Bài 11 — reconnect.** Sau onError, ứng dụng gọi `socket.request(1)` để “khôi phục” connection. Hợp lệ không?  
**Đáp án:** không. Cả input/output đã đóng; phải tạo kết nối WebSocket mới với chính sách retry.

**Bài 12 — reason.** Một reason chứa 123 ký tự Unicode có luôn phù hợp giới hạn close không?  
**Đáp án:** không. Giới hạn là 123 **byte UTF-8**; nhiều ký tự có thể chiếm 2–4 byte.

## 16. Tài liệu chuẩn còn giá trị trên JDK hiện đại

- [Java SE 11 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): `onOpen`, `onClose`, `onError`, onText/onBinary, CompletionStage và tính tuần tự callback.
- [Java SE 11 — WebSocket](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html): `request(n)`, `sendClose`, `abort`, `isInputClosed`, `isOutputClosed`, `NORMAL_CLOSURE`.
- [Java SE 11 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): `buildAsync`, `connectTimeout`, handshake exception, header/subprotocol.
- [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): `newWebSocketBuilder()`, cấu hình kết nối.
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455): opening handshake, masking, data/control frames, Close status và lý do.
- [Java SE 11 — CompletableFuture](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html): xử lý hoàn tất async, exception và terminal signal.

**Nguyên tắc thực hành:** `onOpen` báo đã mở, `request` cấp lượt nhận, `onClose` báo đã nhận Close với input đóng, `onError` báo đã lỗi và hai chiều đóng. Không gộp các mốc này làm một. Chỉ đánh dấu công việc hoàn tất khi trạng thái protocol và điều kiện nghiệp vụ tương ứng đã được xác minh; thiết kế riêng kết thúc bình thường, handshake failure và lỗi sau khi mở.