# WebSocket.Listener với onOpen, onText, onBinary, onClose, onError trong Java

**Chủ đề:** Java Advance - networking  
**Nhóm:** WebSocket  
**Công nghệ:** Java 17+, module **java.net.http**, **HttpClient.newWebSocketBuilder()**, **WebSocket.Listener**.

Khi một ứng dụng Java kết nối WebSocket để nhận chat messages, telemetry, stock ticks hoặc những sự kiện thời gian thực, **WebSocket.Listener** là giao diện nhận các callback thuộc **WebSocket client** chuẩn của JDK. Những callback cốt lõi gồm:

- **onOpen(WebSocket)** — kết nối đã được thiết lập; thường bắt đầu bằng **webSocket.request(1)**.
- **onText(WebSocket, CharSequence, boolean last)** — nhận text message có thể đến nhiều phần; **last=true** mới báo đã hết message.
- **onBinary(WebSocket, ByteBuffer, boolean last)** — nhận binary message; phải đọc đúng vùng **position..limit** và quản lý buffer.
- **onClose(WebSocket, int statusCode, String reason)** — đã nhận Close message; input của WebSocket đóng và đây là callback cuối cho connection đó.
- **onError(WebSocket, Throwable error)** — xảy ra lỗi, input/output đã đóng; đây cũng là callback cuối.

Hai callback điều khiển **onPing/onPong** rất cần biết vì chúng cũng tiêu thụ **receive demand**. Theo Javadoc Java, **WebSocket.request(n)** không yêu cầu n **messages hoàn chỉnh** mà yêu cầu tối đa **n lượt receive callback**. Một message bị chia fragment có thể dùng nhiều lượt onText/onBinary. **CompletionStage** trả về từ callback lại có vai trò khác: báo khi phần dữ liệu callback có thể được implementation lấy lại/reclaim; nó **không** là demand counter.

**Mục tiêu:** hiểu signatures, thứ tự, phân mảnh, flow control, nguồn dữ liệu và vòng đời closure; xây listener an toàn; kiểm thử thật bằng Java 17 với WebSocket server thử nghiệm trên loopback; phân biệt opening handshake failure, close bình thường và connection error. Không dùng Java WebSocket client API để giả vờ nó là framework WebSocket server.

## 1. WebSocket và luồng sự kiện

Khác với mô hình HTTP request/response thông thường, WebSocket cung cấp kênh **hai chiều**, thường **lâu dài**. Client khởi đầu bằng một **opening handshake**. Với WebSocket trên HTTP/1.1 truyền thống, client gửi request có Upgrade: websocket, server hợp lệ trả **101 Switching Protocols**; sau đó hai bên trao đổi **WebSocket frames** cho tới khi đóng.

~~~text
Java client                                WebSocket server
    |                                            |
    |  HTTP GET + Upgrade: websocket ----------> |
    | <------------- HTTP/1.1 101 -------------- |
    |                                            |
    | -------- WebSocket connection OPEN ------- |
    |                 onOpen                     |
    |                                            |
    | <-------- Text fragments ----------------- |
    |    onText(part,last=false/true)            |
    | <-------- Binary fragments --------------- |
    |    onBinary(buffer,last=false/true)        |
    | <-------- Ping --------------------------- |
    |    onPing, automatic Pong from client      |
    |                                            |
    | <-------- Close(1000,"bye") -------------- |
    |    onClose; client sends Close reply       |
    |                                            |
    |  input/output CLOSED                       |
~~~

**ws://** không dùng TLS; **wss://** dùng bảo vệ TLS. Production nên dùng **wss://**, xác minh chứng chỉ/hostname đúng và quản lý authentication, authorization, origin, limits và log. Demo dùng **ws://127.0.0.1** trên loopback để không phụ thuộc Internet; đó là lựa chọn **chỉ cho học tập**.

**API Java chuẩn là client:** **java.net.http.WebSocket** giúp mở kết nối và gửi/nhận WebSocket; **HttpClient.newWebSocketBuilder()** tạo WebSocket.Builder. Java SE không cung cấp một WebSocket server production đầy đủ chỉ bằng WebSocket.Listener. Demo cuối bài tự viết một server socket tối giản để kiểm thử chứ không phải sản phẩm triển khai công khai.

## 2. Tạo WebSocket và listener bằng HttpClient

Mẫu chung:

~~~java
// Snippet: MyListener là lớp ứng dụng phải tự định nghĩa.
HttpClient httpClient = HttpClient.newHttpClient();
WebSocket.Listener listener = new MyListener();

CompletableFuture<WebSocket> opening =
        httpClient.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .buildAsync(
                        URI.create("wss://service.example/events"),
                        listener);
~~~

Cần import **java.net.URI**, **java.net.http.HttpClient**, **java.net.http.WebSocket**, **java.time.Duration** và **java.util.concurrent.CompletableFuture**. **opening** hoàn thành với **WebSocket** sau opening handshake thành công; nó cũng có thể **complete exceptionally** do DNS/connect/TLS/handshake/timeout. **Không** giả định một opening failure luôn được báo qua **onError** của một WebSocket đã mở. Hai giai đoạn phải có nhánh xử lý riêng.

Builder có thể cấu hình connectTimeout, subprotocols, headers hợp lệ và sử dụng cấu hình HttpClient như proxy/TLS/executor. Khi dùng **wss://**, không tắt certificate/hostname verification chỉ để cho kết nối thành công.

**Opening future ≠ lifecycle future:** một WebSocket mở thành công có thể nhận messages trong hàng giờ; ứng dụng nên có một **CompletableFuture<Void> closed** riêng trong listener, hoàn thành bình thường ở **onClose** hoặc exceptionally ở **onError**. Mọi send operation lại trả future riêng, còn business acknowledgements cần logic application riêng.

## 3. Bảng callback và hợp đồng mỗi method

| Callback | Chữ ký giản lược | Khi được gọi | Kết quả |
| --- | --- | --- | --- |
| **onOpen** | void onOpen(WebSocket) | WebSocket đã kết nối; callback đầu tiên, tối đa một lần | Không trả stage |
| **onText** | CompletionStage<?> onText(WebSocket, CharSequence, boolean) | Có text data | Stage điều khiển vòng đời CharSequence |
| **onBinary** | CompletionStage<?> onBinary(WebSocket, ByteBuffer, boolean) | Có binary data | Stage điều khiển vòng đời ByteBuffer |
| **onPing** | CompletionStage<?> onPing(WebSocket, ByteBuffer) | Có Ping frame | Stage cho control payload |
| **onPong** | CompletionStage<?> onPong(WebSocket, ByteBuffer) | Có Pong frame | Stage cho control payload |
| **onClose** | CompletionStage<?> onClose(WebSocket, int, String) | Nhận Close; input đã đóng | Stage cho phép đóng output |
| **onError** | void onError(WebSocket, Throwable) | Lỗi kết nối/callback | Không trả stage; không throw |

Các method đều có triển khai mặc định vì Listener là interface có **default methods**. Tuy nhiên, nếu override **onOpen** hoặc các receive callbacks mà không tự gọi **request(n)** phù hợp, app có thể dừng nhận dữ liệu. **onClose và onError là terminal** cho cùng một WebSocket: sau khi một trong hai được gọi, không có callback tiếp theo nào của connection đó.

**Trình tự callback** được Javadoc bảo vệ ở mức **phương thức**: callback kế tiếp cho cùng WebSocket chỉ bắt đầu sau khi callback trước **return**. Điều này không bảo đảm các **async tasks** do callback khởi tạo đã xong, và không bảo đảm thứ tự callback giữa **hai WebSockets khác nhau** dùng chung một listener instance.

## 4. request(long n): đếm lượt callback thay vì message

WebSocket mới tạo có **receive counter bằng 0**. Khi gọi **webSocket.request(n)** với **n > 0**, counter tăng n. Mỗi lần gọi một receive method **onText, onBinary, onPing, onPong, onClose**, counter giảm một. **onOpen** và **onError** không phải receive methods nên không tiêu thụ counter.

~~~text
New WebSocket: demand = 0
   |
   v
onOpen(ws): ws.request(1) -> demand = 1
   |
   v
onText("Hel", last=false) -> demand = 0
     append "Hel"; ws.request(1) -> demand = 1
   |
   v
onText("lo", last=true) -> demand = 0
     append "lo"; complete message "Hello"
     ws.request(1) -> demand = 1
   |
   v
onPing(ByteBuffer "p") -> demand = 0
     ws.request(1) -> demand = 1
   |
   v
onClose(...): receive callback cuối
~~~

Đây là một luồng ví dụ; Java implementation có thể phân mảnh text thành số lần onText khác với số raw frames do peer gửi. **last** là dấu hiệu của **kết thúc message**, không phải dấu hiệu của TCP packet hay ranh giới application chunk mà bạn có thể tự dự đoán.

**Nếu không request thêm:** WebSocket có thể không gọi receive callback tiếp vì counter về 0. Điều này không có nghĩa server đã ngừng gửi; hệ thống có thể bị giữ ở tầng backpressure/nhận dữ liệu.

**request(0) hoặc request(-1):** sai contract, ném **IllegalArgumentException**. Không dùng request(Long.MAX_VALUE) như mặc định khi xử lý message không có giới hạn: ứng dụng vẫn phải quản lý bộ nhớ và queue.

### Bẫy khi override onOpen

~~~java
// SAI: đã override phương thức mặc định nhưng không tạo demand.
@Override
public void onOpen(WebSocket ws) {
    System.out.println("Connected");
}
~~~

~~~java
// ĐÚNG khi listener sẵn sàng nhận callback đầu tiên.
@Override
public void onOpen(WebSocket ws) {
    System.out.println("Connected");
    ws.request(1);
}
~~~

Theo Javadoc, onOpen mặc định tự gọi request(1). Việc bạn override phương thức này làm **hành vi default không chạy**, nên phải gọi lại khi muốn nhận. onText/onBinary/onPing/onPong mặc định cũng request(1); đừng quên cấp demand nếu thay default bằng callback riêng.

**Cấp demand nên gắn với năng lực consumer:** listener nhanh có thể request một lượt mới sau khi đã copy/parse fragment; listener bận có thể đợi trước khi request thêm. Tránh vừa cấp demand ồ ạt vừa đưa dữ liệu vào executor queue vô hạn, vì đó không phải backpressure end-to-end.

## 5. onOpen: mở connection, chưa chắc ứng dụng đã authenticated

~~~java
@Override
public void onOpen(WebSocket ws) {
    // Khởi tạo per-connection state và theo dõi liveness nếu cần.
    ws.request(1);
}
~~~

**onOpen** là callback đầu, tối đa một lần, xác nhận WebSocket connected. Nhưng nó **không** cam kết user/application đã được phép subscribe mọi channel. Một service có thể đòi hỏi business authentication hoặc subscription message sau handshake; đó là tầng ứng dụng riêng.

Nếu cần gửi một message sau kết nối, dùng **sendText(...)** và xử lý future. Đừng block vô hạn ngay trong onOpen bằng chờ network/database; callback nên ngắn, giới hạn thời gian, có đường fail/cancel rõ ràng.

**Lỗi trước onOpen:** opening handshake có thể thất bại với **WebSocketHandshakeException** hoặc IOException khác; nếu opening future đã exceptional, không chờ onClose của một kết nối chưa được mở. Thiết kế cleanup riêng cho giai đoạn CONNECTING.

## 6. onText: CharSequence, fragment và boolean last

~~~java
CompletionStage<?> onText(
    WebSocket ws, CharSequence data, boolean last)
~~~

Ý nghĩa:

- **data** là phần text callback đang giao; kiểu **CharSequence** không mặc định bất biến như String. Java implementation đảm bảo data là chuỗi UTF-16 hợp lệ.
- **last=false** nghĩa là còn những phần **cùng message** chưa giao hết.
- **last=true** nghĩa là fragment hiện tại kết thúc message. Không đồng nghĩa connection closing.
- **return CompletionStage<?>** báo khi WebSocket được phép reclaim data; không truy cập **data** sau khi stage hoàn tất.
- **ws.request(1)** cho phép lần callback tiếp theo theo nhu cầu của consumer.

### Mẫu ghép message

~~~java
private final StringBuilder text = new StringBuilder();

@Override
public CompletionStage<?> onText(WebSocket ws,
                                 CharSequence fragment, boolean last) {
    text.append(fragment); // Sao chép nội dung trước stage completion.
    if (last) {
        String message = text.toString();
        text.setLength(0);
        processCompleteText(message);
    }
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

**Snippet** cần định nghĩa **processCompleteText** và import. Khi message là JSON, chỉ parse **khi đã đủ message**; đừng bắt parser nhận được JSON hoàn chỉnh ở mỗi fragment. Với server có thể gửi message cực dài, **giới hạn tổng số characters/bytes theo protocol**, ví dụ từ chối message vượt 1 MiB và khởi tạo Close 1009; không để StringBuilder tích lũy vô hạn.

Nếu cần giữ **CharSequence** sau khi returned CompletionStage complete, **copy qua toString()** trước. Không đưa raw data vào background task rồi return completedFuture nếu task còn đọc nó sau đó.

### Mối quan hệ callback và raw WebSocket frame

Một message có thể gồm một raw text frame mở đầu và nhiều continuation frames. Callback **onText** cho biết text data ở cấp Java API; không nên lập giả định cứng “mỗi raw frame tạo đúng một callback” khi thiết kế logic. Hãy dùng **last=true** để quyết định message đã đủ; số fragments không ổn định theo network/implementation.

**last=false** không phải “data bị lỗi” mà chỉ là một trạng thái hợp lệ. **last=true** có thể xuất hiện với fragment rỗng kết thúc message; parser cần xử lý cả empty text messages nếu protocol cho phép.

## 7. onBinary: ByteBuffer đúng position/limit, không đọc array tùy ý

~~~java
CompletionStage<?> onBinary(
    WebSocket ws, ByteBuffer data, boolean last)
~~~

**ByteBuffer** chứa byte hợp lệ trong **[position, limit)**. Không dùng **capacity()** làm kích thước payload; không mặc định **data.array()** tồn tại (buffer có thể direct/read-only). Không giữ tham chiếu tới ByteBuffer sau khi returned CompletionStage complete, trừ khi bạn đã copy dữ liệu ra bộ nhớ sở hữu.

### Mẫu copy đúng

~~~java
byte[] copy = new byte[data.remaining()];
data.get(copy); // Copy đúng slice từ position đến limit.
~~~

Với một ByteBuffer có position=5, limit=8, capacity=64, dữ liệu được giao chỉ có **3 bytes**, không phải 64. Nếu dùng array() rồi đọc toàn mảng có thể lấy byte ngoài phạm vi hoặc throw UnsupportedOperationException.

### Mẫu ghép fragment

~~~java
private final ByteArrayOutputStream payload = new ByteArrayOutputStream();

@Override
public CompletionStage<?> onBinary(WebSocket ws,
                                   ByteBuffer data, boolean last) {
    byte[] chunk = new byte[data.remaining()];
    data.get(chunk);
    payload.writeBytes(chunk);

    if (last) {
        byte[] message = payload.toByteArray();
        payload.reset();
        processBinary(message);
    }
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

**Snippet** yêu cầu import/định nghĩa **processBinary**. Dùng ví dụ trên chỉ khi đã có **size cap** cho dữ liệu chưa tin cậy; nếu binary payload lớn, cần xử lý theo từng phần với bounded buffers hoặc ghi file theo thiết kế, không gom vào ByteArrayOutputStream không giới hạn.

**onText và onBinary cần state riêng.** Việc có Ping xen giữa các fragments không đồng nghĩa một message đã hoàn thành. Đừng reset accumulator khi onPing xảy ra; reset khi **last=true** hoặc khi connection đóng/lỗi.

## 8. CompletionStage<?> và request(n) là hai cơ chế độc lập

Điểm khó trong tài liệu chính thức là **returned CompletionStage không thay đổi receive counter**. Stage từ **onText/onBinary/onPing/onPong** là tín hiệu khi implementation có thể reclaim CharSequence/ByteBuffer. **request(n)** mới là tín hiệu demand cho callbacks sau. Một stage chưa complete **không tự chặn** callback tiếp theo nếu listener đã request thêm.

~~~text
onText(fragment A, last=false)
    |
    +-- copy fragment A
    +-- ws.request(1)             (đã cấp demand)
    +-- return pendingStageA      (chưa hoàn thành)
              |
              |  work A còn xử lý ở background
              v
onText(fragment B, last=true)    (có thể được gọi)
    +-- xử lý fragment B
    +-- return stage B
~~~

Javadoc bảo đảm **method invocations không chồng lấn** cho cùng WebSocket, nhưng không bảo đảm **async work** do các method đó tạo sẽ hoàn thành theo đúng thứ tự. Vì vậy:

1. Nếu xử lý đồng bộ nhanh: copy data, xử lý, **request(1)** và return completedFuture.
2. Nếu xử lý async dùng raw data: trả một **stage chưa complete** tới khi task xử lý xong, **không truy cập data sau stage complete**.
3. Nếu cần giữ data ngoài lifecycle callback: copy trước stage completion.
4. Nếu cần ordering: dùng queue/serial executor theo connection và cấp demand phù hợp; không nhầm “trả stage pending” là tự có serialization.
5. Nếu stage complete exceptionally hoặc callback throw, WebSocket có thể chuyển tới **onError** theo contract. Đừng dùng exceptional stage để báo một validation warning mà application muốn bỏ qua.

### Null stage có nghĩa gì?

Javadoc cho phép onText/onBinary/onPing/onPong trả **null**; WebSocket coi đó như **một stage đã complete bình thường**. Trả null chỉ an toàn khi implementation được phép reclaim data ngay, không có công việc nào còn cần dùng buffer/CharSequence. Vì dễ đọc code và nhất quán với async style, ví dụ dùng **CompletableFuture.completedFuture(null)**.

### Ví dụ xử lý data bất đồng bộ đúng ownership

~~~java
@Override
public CompletionStage<?> onBinary(WebSocket ws,
                                   ByteBuffer bytes, boolean last) {
    byte[] safeCopy = new byte[bytes.remaining()];
    bytes.get(safeCopy);
    CompletionStage<?> task = enqueueBounded(safeCopy, last);
    task.whenComplete((ignored, failure) -> {
        if (failure == null) {
            ws.request(1);
        } else {
            ws.sendClose(1011, "Consumer failed");
        }
    });
    return task;
}
~~~

**Snippet không độc lập:** **enqueueBounded** phải có queue giới hạn, định nghĩa rõ backpressure, cancellation và trả CompletionStage. Việc dùng copy cho phép task giữ dữ liệu độc lập với ByteBuffer của implementation. Cần hiểu callback sẽ không tự động retry khi task thất bại và returned stage exceptional có thể dẫn đến onError. Nếu muốn tự đóng có chủ đích thay vì tạo exceptional stage, phải thiết kế chính sách error handling rõ ràng.

## 9. onClose: Close message, input đã đóng và phản hồi Close

~~~java
CompletionStage<?> onClose(
    WebSocket ws, int statusCode, String reason)
~~~

**onClose** được gọi khi nhận Close message; **input side đã đóng tại thời điểm vào callback**. Theo Java API, đây là **callback cuối cùng** của connection đó. Nếu output chưa đóng, returned stage xác định khi nào WebSocket có thể tự đóng output/đáp lại Close. Built-in HttpClient gửi Close reply phù hợp (cùng code, reason rỗng) khi stage hoàn thành.

~~~java
@Override
public CompletionStage<?> onClose(WebSocket ws,
                                  int statusCode, String reason) {
    System.out.println("Closed: " + statusCode + " " + reason);
    closed.complete(null);
    return CompletableFuture.completedFuture(null);
}
~~~

**closed** là CompletableFuture do ứng dụng tạo. **Hoàn tất future ứng dụng trong onClose** nghĩa là app đã nhận tin close; nếu cần bảo đảm wire reply đã được gửi, theo dõi operation và test riêng (như chương trình loopback ở phần 12).

### Mã Close thường gặp

| Code | Ngữ nghĩa | Lưu ý |
| --- | --- | --- |
| **1000** | Normal Closure | Dùng **WebSocket.NORMAL_CLOSURE** |
| **1001** | Going Away | Endpoint rời đi |
| **1002** | Protocol Error | Protocol violation |
| **1003** | Unsupported Data | Kiểu data không được chấp nhận |
| **1008** | Policy Violation | Chính sách ứng dụng không cho phép |
| **1009** | Message Too Big | Kích thước message vượt giới hạn |
| **1011** | Unexpected Condition | Server gặp lỗi bất ngờ |
| **1005**, **1006**, **1015** | Reserved / mô tả trạng thái đặc biệt | **Không gửi trong Close frame** |

**Reason** phải phù hợp giới hạn payload Close frame: reason có tối đa **123 byte UTF-8** sau 2 bytes status code, không phải 123 Java characters. Không tự gửi status code bất kỳ bằng **sendClose**; method có contract về code hợp lệ.

### sendClose khác abort

~~~java
ws.sendClose(WebSocket.NORMAL_CLOSURE, "");
~~~

**sendClose(...)** yêu cầu đóng **output side** một cách có protocol; nó **không đóng ngay input side**. **ws.abort()** đóng cả input lẫn output **đột ngột** và dùng khi không thể graceful close (chẳng hạn quá hạn chờ peer).

**Cảnh báo:** nếu onClose trả một **CompletionStage không bao giờ complete**, nó có thể ngăn automatic reciprocal Close trên output; điều này được Javadoc nêu rõ. Dùng pending stage trong onClose chỉ khi có nhu cầu thật sự, có timeout và shutdown policy.

## 10. onError: lỗi terminal, không ném ngoại lệ từ callback

~~~java
void onError(WebSocket ws, Throwable error)
~~~

**onError** có thể xảy ra bất cứ lúc nào **sau onOpen**, không yêu cầu còn receive demand. Khi callback này bắt đầu, **cả input và output đã đóng**. Đây là callback cuối cho connection; không có thêm onClose/onText sau onError của cùng WebSocket.

~~~java
@Override
public void onError(WebSocket ws, Throwable error) {
    closed.completeExceptionally(error);
    // Log connection ID, exception type, cause theo chính sách an toàn.
    // Tuyệt đối không throw từ onError.
}
~~~

**Không để onError tự ném exception.** Javadoc nói behavior là **undefined** nếu callback onError throw. Nếu logger/metrics/custom hook có khả năng throw, nên cô lập chúng bằng try/catch hoặc cơ chế không làm hỏng callback.

Một **opening failure** có thể làm **buildAsync** complete exceptionally trước khi WebSocket mở; đừng mặc định onError thay thế handler cho future đó. Một **exception trong onText/onBinary** hoặc returned stage exceptional có thể làm connection kết thúc qua onError; không gộp lỗi validation message vào lỗi network nếu application muốn tiếp tục vận hành.

### Hai con đường kết thúc hợp lệ

~~~text
Opening future:
  CONNECTING
      +-- failure --> buildAsync exceptionally (chưa chắc có onError)
      +-- success --> onOpen --> OPEN
                                  |
                                  +-- onClose --> CLOSED normal
                                  +-- onError --> CLOSED failure
~~~

Trong production, application có thể thêm các trạng thái CLOSING/RECONNECTING theo contract. Không cho phép một connection vừa onClose rồi onError nối tiếp vì Javadoc quy định terminal callback là cuối.

## 11. onPing/onPong: control frames cũng cần receive demand

Ngoài năm callback chính, onPing và onPong rất quan trọng. Chúng là **receive methods**, nên mỗi invocation cũng tiêu thụ một unit demand. Ping/Pong có payload tối đa **125 bytes** theo WebSocket protocol.

~~~java
@Override
public CompletionStage<?> onPing(WebSocket ws, ByteBuffer data) {
    byte[] copy = new byte[data.remaining()];
    data.get(copy);
    observePing(copy);
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

**observePing** là hàm ứng dụng chưa định nghĩa trong snippet. **JDK WebSocket tự gửi Pong đáp lại Ping** theo contract; không cần gửi thêm **ws.sendPong(...)** trong onPing bình thường. Nếu override mà quên **request(1)** sau Ping, receive pipeline có thể bị hết demand trước khi text/binary tiếp theo tới.

**onPong** có thể dùng làm heartbeat measurement khi client chủ động **ws.sendPing(...)**; nhưng một Pong hợp lệ không chứng minh business operation đã hoàn tất. Dùng message acknowledgements riêng cho nghiệp vụ và timeout/reconnection policy để phát hiện half-open connections.

## 12. Chương trình Java 17 hoàn chỉnh: kiểm thử WebSocket.Listener thật

Để không phụ thuộc WebSocket service bên ngoài, chương trình sau tạo một **server socket trên 127.0.0.1**, trả opening handshake **101 Switching Protocols** với **Sec-WebSocket-Accept** đúng RFC 6455, rồi phát các frames nhỏ. Phía client vẫn dùng **HttpClient.newWebSocketBuilder()** và **WebSocket.Listener thực sự**, không phải gọi callback giả.

Kịch bản server:

1. Nhận HTTP Upgrade request từ Java WebSocket client, trích **Sec-WebSocket-Key** và tính **Sec-WebSocket-Accept = Base64(SHA-1(key + RFC GUID))**.
2. Gửi text fragment **Hel** rồi continuation **lo**.
3. Gửi binary fragments **01 02** và **03 04**.
4. Gửi Ping có payload **p**; đọc Pong được client tự phát.
5. Gửi Close **1000:bye**; đọc Close reply của client.
6. Client xác nhận input/output đã đóng.

**Chú ý:** test server cố tình chỉ hỗ trợ **một kết nối, frames ngắn <=125 byte, không TLS, không extension, không production hardening**. Đó là fixture minh họa callback/flow; không đưa lên Internet làm server thật.

### WebSocketListenerDemo.java

~~~java
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
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.HexFormat;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WebSocketListenerDemo {
    static final class DemoListener implements WebSocket.Listener {
        final CompletableFuture<Void> closed = new CompletableFuture<>();
        final StringBuilder text = new StringBuilder();
        final ByteArrayOutputStream binary = new ByteArrayOutputStream();

        @Override
        public void onOpen(WebSocket ws) {
            System.out.println("onOpen");
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onText(WebSocket ws, CharSequence part,
                                          boolean last) {
            text.append(part); // copy before stage completes
            if (last) {
                System.out.println("onText=" + text);
                text.setLength(0);
            }
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onBinary(WebSocket ws, ByteBuffer part,
                                            boolean last) {
            byte[] copy = new byte[part.remaining()];
            part.get(copy); // only bytes position..limit
            binary.writeBytes(copy);
            if (last) {
                System.out.println("onBinary=" +
                        HexFormat.of().formatHex(binary.toByteArray()));
                binary.reset();
            }
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onPing(WebSocket ws, ByteBuffer data) {
            byte[] copy = new byte[data.remaining()];
            data.get(copy);
            System.out.println("onPing=" +
                    new String(copy, StandardCharsets.UTF_8));
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(WebSocket ws, int code, String reason) {
            System.out.println("onClose=" + code + ":" + reason);
            closed.complete(null);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            closed.completeExceptionally(error);
        }
    }

    record Frame(int opcode, byte[] payload) {}

    static String readHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        int matched = 0;
        int value;
        while ((value = in.read()) != -1) {
            bytes.write(value);
            if (value == "\r\n\r\n".charAt(matched)) {
                matched++;
                if (matched == 4) break;
            } else {
                matched = value == '\r' ? 1 : 0;
            }
            if (bytes.size() > 16384) throw new IOException("Headers too big");
        }
        if (matched != 4) throw new IOException("Incomplete upgrade request");
        return bytes.toString(StandardCharsets.ISO_8859_1);
    }

    static void upgrade(InputStream in, OutputStream out) throws Exception {
        String headers = readHeaders(in);
        String key = null;
        for (String line : headers.split("\r\n")) {
            if (line.regionMatches(true, 0, "Sec-WebSocket-Key:", 0, 18)) {
                key = line.substring(18).trim();
            }
        }
        if (key == null) throw new IOException("Missing WebSocket key");
        byte[] digest = MessageDigest.getInstance("SHA-1").digest(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                        .getBytes(StandardCharsets.ISO_8859_1));
        String accept = Base64.getEncoder().encodeToString(digest);
        String response = "HTTP/1.1 101 Switching Protocols\r\n"
                + "Upgrade: websocket\r\n"
                + "Connection: Upgrade\r\n"
                + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
        out.write(response.getBytes(StandardCharsets.ISO_8859_1));
        out.flush();
    }

    static void serverFrame(OutputStream out, int header, byte[] data)
            throws IOException {
        if (data.length > 125) throw new IOException("Demo frame too long");
        out.write(header);
        out.write(data.length); // server frames are not masked
        out.write(data);
        out.flush();
    }

    static Frame clientFrame(InputStream in) throws IOException {
        int b0 = in.read();
        int b1 = in.read();
        if (b0 < 0 || b1 < 0) throw new IOException("Missing client frame");
        int size = b1 & 0x7f;
        if ((b1 & 0x80) == 0 || size > 125) {
            throw new IOException("Expected masked short client frame");
        }
        byte[] mask = in.readNBytes(4);
        byte[] payload = in.readNBytes(size);
        if (mask.length != 4 || payload.length != size) {
            throw new IOException("Incomplete frame");
        }
        for (int i = 0; i < payload.length; i++) {
            payload[i] ^= mask[i % 4];
        }
        return new Frame(b0 & 0x0f, payload);
    }

    static String serveOnce(ServerSocket listener) throws Exception {
        try (Socket socket = listener.accept()) {
            socket.setSoTimeout(5000);
            InputStream in = socket.getInputStream();
            OutputStream out = socket.getOutputStream();
            upgrade(in, out);

            serverFrame(out, 0x01, "Hel".getBytes(StandardCharsets.UTF_8));
            serverFrame(out, 0x80, "lo".getBytes(StandardCharsets.UTF_8));
            serverFrame(out, 0x02, new byte[] {1, 2});
            serverFrame(out, 0x80, new byte[] {3, 4});
            serverFrame(out, 0x89, "p".getBytes(StandardCharsets.UTF_8));

            Frame pong = clientFrame(in);
            boolean gotPong = pong.opcode() == 10
                    && new String(pong.payload(), StandardCharsets.UTF_8)
                            .equals("p");

            byte[] close = {3, (byte) 232, 'b', 'y', 'e'}; // 1000 + "bye"
            serverFrame(out, 0x88, close);
            Frame reply = clientFrame(in);
            boolean gotClose = reply.opcode() == 8;
            return "serverSawPong=" + gotPong
                    + "\nserverSawClose=" + gotClose;
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> wireResult = executor.submit(() -> serveOnce(server));
                DemoListener listener = new DemoListener();
                HttpClient client = HttpClient.newHttpClient();
                URI uri = URI.create("ws://127.0.0.1:"
                        + server.getLocalPort() + "/demo");
                WebSocket ws = client.newWebSocketBuilder()
                        .connectTimeout(Duration.ofSeconds(3))
                        .buildAsync(uri, listener)
                        .get(5, TimeUnit.SECONDS);
                listener.closed.get(5, TimeUnit.SECONDS);
                System.out.println(wireResult.get(5, TimeUnit.SECONDS));
                System.out.println("inputClosed=" + ws.isInputClosed());
                System.out.println("outputClosed=" + ws.isOutputClosed());
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

### Biên dịch và chạy

Tạo file **WebSocketListenerDemo.java** trong thư mục thực hành với mã trên, dùng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 WebSocketListenerDemo.java
java WebSocketListenerDemo
~~~

**Stdout đã kiểm thử thực tế bằng javac --release 17 và chạy trên JDK 24.0.2:**

~~~text
onOpen
onText=Hello
onBinary=01020304
onPing=p
onClose=1000:bye
serverSawPong=true
serverSawClose=true
inputClosed=true
outputClosed=true
~~~

**Diễn giải:**

- **onOpen** xảy ra khi opening handshake đã thành công, rồi request(1) kích hoạt receive.
- **onText=Hello** cho thấy listener đã ghép fragments cho đến **last=true**.
- **onBinary=01020304** cho thấy copy đúng 4 bytes và ghép message nhị phân.
- **onPing=p** được gọi, đồng thời server xác nhận **serverSawPong=true** dù listener không tự gửi Pong.
- **onClose=1000:bye** thông báo peer đóng bình thường; returned completed stage cho phép close reply, server xác minh **serverSawClose=true**.
- **inputClosed=true/outputClosed=true** được in sau khi close reply đã xuất hiện.
- **onError** không xảy ra trong đường thành công này; nó đã được khai báo để hoàn tất lifecycle future exceptionally khi có lỗi.

**Giới hạn:** Output chỉ được bảo đảm với fixture/test logic trên một JDK/môi trường phù hợp; số callbacks cho một message khi chia frames có thể khác, nhưng ví dụ chỉ in khi **last=true**, nên không cần khẳng định số callbacks. Fixture **không** có TLS và **không** có đủ checks để đưa ra mạng công cộng.

## 13. Vì sao không viết WebSocket server bằng java.net.http.WebSocket?

**java.net.http.WebSocket** là API **client**. JDK không cung cấp WebSocket server production chỉ bằng interface này. Nếu xây server thực, dùng WebSocket support của server framework phù hợp hoặc một server implementation được bảo trì và kiểm thử RFC, TLS, auth, compression, limits, proxy/ingress, shutdown và denial-of-service controls.

ServerSocket fixture trên chỉ dùng SHA-1 cho **Sec-WebSocket-Accept** theo bắt tay RFC 6455; đây là **handshake validation**, không phải hash mật khẩu hay chứng minh tính bí mật. Nó chỉ hỗ trợ frames nhỏ và không xử lý tất cả errors/extensions. Không xem “SHA-1 trong opening handshake” là cơ chế bảo mật thay TLS.

## 14. Gửi dữ liệu: sendText/sendBinary khác callback nhận

**webSocket.sendText(CharSequence, boolean last)**, **sendBinary(ByteBuffer, boolean last)** và **sendClose(code, reason)** trả **CompletableFuture<WebSocket>** của send operation. Future này hoàn thành khi send operation hoàn tất theo JDK, **không** chứng minh ứng dụng peer đã xử lý message.

~~~java
// Snippet: ws là WebSocket đã connect.
ws.sendText("Hello ", false)
  .thenCompose(s -> s.sendText("WebSocket", true))
  .join();
~~~

~~~java
// Snippet: ghép hai phần binary send theo đúng thứ tự.
ws.sendBinary(ByteBuffer.wrap(new byte[] {1, 2}), false)
  .thenCompose(s -> s.sendBinary(
          ByteBuffer.wrap(new byte[] {3, 4}), true))
  .join();
~~~

**last=false** khi gửi là chưa hết message; **last=true** kết thúc message. Sử dụng **thenCompose** để tuần tự hóa hai send operations liên quan. Đừng fire-and-forget nhiều sends cùng loại khi đang có một pending send không được phép bởi API state. **Receive request(1)** không điều khiển số bytes được phép **gửi**.

Với business event quan trọng, application cần **message ID + acknowledgement/deduplication** riêng. Khi mất kết nối giữa send và server persistence, chỉ có send future chưa chắc trả lời được “server đã commit chưa?”. Không gửi lại non-idempotent operations vô điều kiện.

## 15. Production patterns: quản lý state, đóng, reconnect

Một listener dùng lâu dài nên có ít nhất:

- **Per-connection state:** text/binary accumulators, lifecycle future, request IDs, event queue, identity/subscription state.
- **Body/message limits:** max UTF-8/text length, max binary bytes, max fragments, bounded queues; reject hoặc đóng khi bị lạm dụng.
- **Receive demand strategy:** request một hoặc vài lượt chỉ khi pipeline có chỗ; không bỏ quên demand sau Ping/Pong.
- **Fragment completion:** parse schema sau **last=true**, reset accumulator đúng lúc, không để ping làm mất state.
- **Error semantics:** handshake failure từ buildAsync; onError từ established WebSocket; error stage từ sends; business validation errors.
- **Timeouts:** connect timeout, idle timeout, close-handshake timeout, application ack deadline; không đợi peer vô hạn.
- **Graceful shutdown:** gửi Close 1000 khi cần, chờ input Close, fallback **abort** nếu quá hạn.
- **Reconnect:** exponential backoff với jitter, limit attempts, refresh auth, phục hồi subscription/cursor theo protocol; Java API không tự reconnect cho bạn.
- **Security:** wss://, certificate trust/hostname verification, auth/permissions, origin/subprotocol validation, không log secrets.
- **Monitoring:** active connections, callback counts, message bytes, fragment counts, queue depth, close codes, failures, reconnect attempts, latency và idle times.

### Các future khác nhau cho các mục tiêu khác nhau

~~~text
openingFuture: CompletableFuture<WebSocket>
   - thành công khi upgrade/kết nối sẵn sàng
   - thất bại khi opening handshake lỗi

lifecycleFuture: CompletableFuture<Void>
   - thành công bình thường khi onClose
   - exceptional khi onError

sendFuture: CompletableFuture<WebSocket>
   - hoàn thành một thao tác gửi

businessAckFuture: CompletableFuture<Result>
   - theo thông điệp ack ở tầng ứng dụng
~~~

Tránh dùng **openingFuture.isDone()** để tuyên bố WebSocket đã đóng hoặc đã xử lý xong mọi message. Tránh dùng **sendFuture complete** thay cho business acknowledgement. Nếu listener dùng chung cho nhiều WebSockets, quản lý **per-socket state** vì callbacks từ các connections khác nhau có thể diễn ra đồng thời.

## 16. Lỗi triển khai thường gặp

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Override **onOpen** mà quên request(1) | Kết nối xong nhưng không có onText | Tạo demand rõ ràng |
| Chỉ request(1) duy nhất một lần | Receive ngừng sau một callback | Cấp thêm demand theo capacity |
| request(1) nghĩa một message | Bỏ mất fragments | Ghép cho đến **last=true** |
| Parse mỗi onText fragment như JSON hoàn chỉnh | Lỗi parse/thiếu data | Chỉ parse khi complete |
| Không giới hạn text/binary message | Hết RAM | Max bytes/chars + Close 1009 |
| Dùng ByteBuffer.array() | Sai slice, throw với direct buffer | Dùng remaining()/get(copy) |
| Giữ CharSequence/ByteBuffer sau stage complete | Data có thể bị reclaim | Copy trước hoặc giữ stage pending đúng |
| Nghĩ stage chưa complete chặn callbacks | Async tasks race | Cấp demand có chủ đích + serial execution |
| Override onPing nhưng không request | Dừng receive sau control frame | Cấp demand tiếp |
| Tự Pong luôn trong onPing | Thừa Pong | Java client tự đáp Pong |
| onClose trả stage không bao giờ complete | Close reply có thể không gửi | Hoàn tất stage hoặc timeout |
| Nghĩ sendClose đóng cả input | Input còn mở chờ peer | Chờ onClose hoặc abort sau deadline |
| Ném exception từ onError | Undefined behavior | onError không throw |
| Chỉ chờ onError khi buildAsync thất bại | Bỏ lỡ lỗi opening | Theo dõi opening future |
| Dùng chung mutable accumulators cho nhiều sockets | Race giữa connections | Per-connection state |
| Nhầm HTTP status từ Upgrade failure với Close code | Chẩn đoán sai tầng | Tách opening handshake và WebSocket close |
| sendText future done nghĩa server đã commit | Duplicate/retry sai | App ack và deduplication |

## 17. Kiểm thử và chẩn đoán

### Kết nối mở nhưng không có dữ liệu

Kiểm tra listener có **request(n)** ở onOpen hay không, callback onPing/onPong trước đó có tiêu thụ demand không, server đã chấp nhận subscription chưa, và có code đồng bộ đang block callback không. Không kết luận “server không gửi” chỉ từ việc onText chưa xuất hiện.

### Binary sai byte

In **data.position()**, **data.limit()**, **data.remaining()** ở môi trường test và đảm bảo chỉ copy **remaining()** bytes. Đừng giữ data sau stage completion. Kiểm tra fragments và message framing ở application protocol.

### Lỗi xảy ra sau một callback

Xem callback có throw hoặc trả exceptional stage. Tách parser/domain validation (có thể tiếp tục nếu policy cho phép) với protocol/network failure (onError/close). Đừng phát request thêm vô giới hạn trong đường error.

### onClose đã chạy nhưng output vẫn mở

Kiểm tra **CompletionStage** của onClose có complete không và ứng dụng có chủ động sendClose/abort hoặc giữ pending future vô hạn không. onClose đến lúc input đóng; output có thể chờ logic đóng riêng.

### onError không xuất hiện khi không kết nối được

Kiểm tra **CompletableFuture<WebSocket>** từ **buildAsync**: opening handshake lỗi được ghi nhận ở future này. onError không phải cách bắt mọi lỗi DNS/TLS/HTTP 101 khi chưa có WebSocket connected.

### Peer biến mất, không thấy onClose

Đây có thể là network failure báo qua onError, hoặc half-open path chưa được phát hiện. Có idle timeout, Ping/Pong liveness, retry/backoff và cleanup phù hợp. Không cho phép app đợi vô hạn mà không có deadline.

## 18. Bài tập

1. Viết listener chỉ có **onOpen/onText**. Tại sao cần **ws.request(1)** trong onOpen và mỗi lượt tiếp theo?
2. Một message text được giao qua 3 callbacks có **last=false,false,true**. Làm sao ghép JSON đúng?
3. Một binary buffer có position=3, limit=7, capacity=64. Có bao nhiêu bytes hợp lệ? Vì sao array() có thể sai?
4. So sánh **request(1)** và returned **CompletionStage**. Stage chưa complete có tự ngăn callback tiếp theo không?
5. Nếu phải xử lý một fragment trên executor khác, khi nào cần copy CharSequence/ByteBuffer? Khi nào stage được complete?
6. **onPing** tiêu thụ demand không? Java client tự gửi Pong hay bạn phải gọi sendPong?
7. Trình bày khác biệt **onClose** và **onError** về input/output, terminal callback và status/reason.
8. Vì sao **sendClose(1000,"")** không có nghĩa input đã đóng? Khi nào abort là cần thiết?
9. Nếu **onClose** trả một CompletableFuture không bao giờ complete, hành vi reciprocal close ra sao?
10. Vì sao WebSocket opening **buildAsync** có thể fail mà listener không có onError như bạn mong đợi?
11. Chạy **WebSocketListenerDemo.java** và thay binary fragments để xác minh **onBinary** ghép đúng.
12. Chặn demand sau onOpen trong fixture; mô tả expected hang/test timeout và cách tránh test chạy vô hạn.
13. Dùng cùng listener instance cho hai WebSockets. Làm sao giữ state riêng và tránh race?
14. Đề xuất policy reconnect với jitter và max attempts, kèm cách deduplicate business events.
15. Thiết kế server đột ngột đóng TCP sau onOpen để test onError; không khẳng định exception class cố định cho mọi JDK/mạng.
16. Thêm app-level acknowledgement cho sendText rồi phân biệt sendFuture completion với acknowledgement thực.

## 19. Checklist code review

- [ ] Opening future có xử lý errors riêng?
- [ ] onOpen gọi request(n) đúng?
- [ ] onText ghép message tới last=true?
- [ ] onBinary copy đúng position..limit?
- [ ] Có giới hạn message size, thời gian và memory?
- [ ] Không giữ data sau returned CompletionStage hoàn tất?
- [ ] Hiểu demand request(n) tách khỏi stage completion?
- [ ] onPing/onPong override vẫn cấp demand nếu tiếp tục?
- [ ] Không gửi duplicate Pong khi implementation đã tự đáp?
- [ ] onClose complete stage có kiểm soát, cleanup resource?
- [ ] Không nhầm sendClose với full-duplex termination?
- [ ] onError không throw và hoàn tất lifecycle future?
- [ ] Per-connection state thread-safe nếu listener share?
- [ ] Gửi dữ liệu có theo dõi future và business acknowledgement?
- [ ] Dùng wss:// cho ứng dụng thực và có reconnect/timeout policy?

**Kết luận:** WebSocket.Listener là lớp callback nhận sự kiện WebSocket của Java HTTP client. **onOpen** mở đầu và cấp demand; **onText/onBinary** nhận message fragments, cần ghép đến **last=true**; **onClose** thông báo Close frame và kết thúc input; **onError** kết thúc kết nối do lỗi. **request(n)** điều khiển số callback nhận được; **CompletionStage<?>** điều khiển vòng đời dữ liệu của callback — **không thay thế nhau**. Một listener đúng phải quản lý **fragments, ByteBuffer ownership, demand, closure, error handling, async work và tài nguyên** thay vì chỉ in log từng sự kiện.

### Tài liệu chính thức

- [WebSocket.Listener — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
- [WebSocket — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html)
- [WebSocket.Builder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html)
- [HttpClient — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
