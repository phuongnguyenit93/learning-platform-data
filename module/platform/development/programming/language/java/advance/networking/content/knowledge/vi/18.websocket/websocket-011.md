# sendClose, hai chiều input/output và abort khi không thể đóng có thứ tự

## Mục tiêu bài học

Khi làm việc với `java.net.http.WebSocket` trên Java 17+, thao tác đóng kết nối **không** đơn giản là thay một trạng thái từ OPEN sang CLOSED. Đối tượng `WebSocket` có **hai phía độc lập**: **input** để nhận và **output** để gửi. Lệnh `sendClose(...)` chỉ bắt đầu **đóng output có thứ tự** bằng một Close control frame; input có thể vẫn mở để nhận Close đối ứng. Nếu peer không phản hồi, transport lỗi hoặc ứng dụng không thể đợi thêm, `abort()` đóng **đột ngột cả input lẫn output**.

Sau bài, bạn có thể:

- Mô tả **closing handshake** theo RFC 6455, phân biệt Close frame, trạng thái WebSocket và việc đóng kết nối TCP/TLS bên dưới.
- Giải thích `isInputClosed()` và `isOutputClosed()`; nhận biết trạng thái **input=false, output=true** là hợp lệ.
- Hiểu chính xác future do `sendClose(int, String)` trả về: hoàn tất khi **Close message đã được gửi**, không phải khi peer đã phản hồi hoặc application data đã được xử lý.
- Dùng `WebSocket.Listener.onClose`, `onError` và `request(n)` để quan sát đúng quá trình nhận và lỗi.
- Chọn `sendClose` khi muốn graceful shutdown và `abort` khi hết deadline/không thể đóng có thứ tự.
- Kiểm soát Close code hợp lệ, reason UTF-8 tối đa 123 byte, pending sends và không gửi lại sau khi output đã đóng.
- Ghép `sendText` trước `sendClose` đúng thứ tự; hiểu vì sao Close không thay thế application acknowledgment.
- Chạy **chương trình Java 17+ độc lập trên loopback** chứng minh khác biệt trước/sau Close đối ứng và trước/sau abort.

**Phạm vi:** client `java.net.http.WebSocket` có từ Java 11, dùng API Java 17 để kiểm tra. Đây không phải `javax.websocket.Session` hoặc `Socket.shutdownInput/shutdownOutput`, cũng không phải các method lifecycle `HttpClient.close/shutdown` mới xuất hiện ở Java 21. Server giả lập trong bài chỉ là công cụ kiểm thử tối thiểu, **không phải WebSocket server production**.

## 1. Tại sao WebSocket cần một nghi thức đóng riêng?

Sau HTTP opening handshake (thường `101 Switching Protocols`), WebSocket truyền dữ liệu bằng **frames** trên một kết nối tồn tại lâu. Hai endpoint đều có thể gửi dữ liệu; không có khái niệm mỗi response HTTP sẽ tự kết thúc session.

~~~text
Client                                        Server
   │── GET /chat + Upgrade: websocket ──────►│
   │◄──────── HTTP/1.1 101 Switching Protocols│
   │                                         │
   ╞══════ WebSocket established ═══════════╡
   │────── Text / Binary / Ping ────────────►│
   │◄────────────── Text / Binary / Pong ────┤
   │                                         │
   │────── Close (status 1000) ─────────────►│
   │◄──────────────────── Close (status 1000)│
   │       close underlying TCP/TLS         │
~~~

**Close** trong WebSocket là **control frame**, không phải HTTP status code hay lệnh trực tiếp gửi TCP FIN. Theo RFC 6455, một bên có thể khởi xướng bằng Close frame; bên kia phản hồi Close nếu chưa gửi. Khi cả hai đã **gửi và nhận Close**, kết nối WebSocket có thể kết thúc sạch bằng cách đóng transport bên dưới.

Đừng nhầm ba mốc:
1. **Đã gửi Close frame cục bộ**: phía gửi đã thông báo muốn đóng.
2. **Đã nhận Close frame đối ứng**: peer đã phát Close; listener có thể báo sự kiện.
3. **Underlying TCP/TLS connection đóng**: kết thúc tài nguyên transport; RFC phân biệt đóng *cleanly* sau handshake với đóng bất thường do mất mạng.

Một peer có thể ngắt mạng ngay sau khi nhận message, khiến client không thấy Close frame; đó là **abnormal closure** chứ không phải orderly closing handshake.

## 2. Hai phía độc lập: input và output

Javadoc định nghĩa `WebSocket` có **input side** và **output side**. Khi một phía đã đóng thì không mở lại được.

| API | Câu hỏi mà nó trả lời |
|---|---|
| `isInputClosed()` | Chiều **nhận** WebSocket messages đã đóng chưa? |
| `isOutputClosed()` | Chiều **gửi** WebSocket messages đã đóng chưa? |
| `sendClose(code, reason)` | Bắt đầu đóng **output** bằng WebSocket Close frame |
| `abort()` | Đóng **cả input và output** đột ngột |

### Bốn tổ hợp trạng thái

| Input closed? | Output closed? | Diễn giải thường gặp |
|---|---|---|
| `false` | `false` | Hai phía mở; có thể gửi và nhận theo quy tắc WebSocket |
| `false` | `true` | Đã gửi Close; không gửi thêm data; vẫn có thể đợi Close từ peer |
| `true` | `false` | Đã nhận Close, input đóng; output có thể đang chờ completion của listener để phản hồi |
| `true` | `true` | Cả hai phía đã đóng do Close handshake, lỗi hoặc abort |

Hai getter **không cho biết ai đã đóng trước** hay mã Close. Giá trị là snapshot tại thời điểm gọi; threads nhận/send có thể khiến nó thay đổi ngay sau kiểm tra. Javadoc bảo đảm một khi getter trả `true` thì những lần gọi sau cũng trả `true`.

**Cần hiểu đúng:** đây là hai phía của **WebSocket API**, không phải lời cam kết trực tiếp về TCP half-close hay thời điểm TCP FIN. Implementation quản lý TCP/TLS bên dưới; ứng dụng dùng WebSocket protocol API.

## 3. `sendClose` đóng output có thứ tự, không đóng input

Cách gọi phổ biến:

~~~java
CompletableFuture<WebSocket> closeSent =
    socket.sendClose(WebSocket.NORMAL_CLOSURE, "");
~~~

`WebSocket.NORMAL_CLOSURE` = **1000**. Future trả về sẽ hoàn tất **khi Close message đã được gửi**; nếu gửi thất bại, future hoàn tất exceptionally. Điều này **không đồng nghĩa** peer đã nhận Close hay đã hoàn thành application work.

~~~text
Client đã kết nối
 input=false, output=false
             │
    sendClose(1000,"bye")
             ▼
    local Close sent
 input=false, output=true   ← hoàn toàn bình thường
             │
    peer gửi Close đối ứng
             ▼
     listener.onClose
 input=true, output=true
~~~

Javadoc Java 17 nêu rõ: `sendClose` **không đóng input**. Nó chỉ khởi tạo closure của output. Input vẫn mở cho tới khi nhận Close, gọi abort hoặc xảy ra lỗi. Vậy code dưới đây **không được** assert input đã đóng:

~~~java
socket.sendClose(WebSocket.NORMAL_CLOSURE, "bye").join();
System.out.println(socket.isOutputClosed()); // true khi gửi thành công
System.out.println(socket.isInputClosed());  // có thể false
~~~

Đây là snippet cần biến `socket` đã kết nối. `join()` có thể chặn thread **đến khi send hoàn tất**, không chờ remote Close. Nếu cần chờ remote Close, tạo future được listener hoàn tất khi `onClose` hoặc `onError` xảy ra và đặt deadline riêng.

### Không tiếp tục gửi data sau Close

Khi output đã đóng, các thao tác `sendText`, `sendBinary`, `sendPing` hay `sendPong` mới có thể thất bại với `IOException`. Một WebSocket đã đóng không được “reopen”; tạo một kết nối mới nếu muốn trao đổi tiếp.

Nếu cần gửi message cuối trước khi Close, **đừng** khởi tạo cả hai thao tác độc lập rồi hy vọng thứ tự đúng:

~~~java
// Không nên dùng để bảo đảm message cuối hoàn tất trước Close:
socket.sendText("last data", true);
socket.sendClose(WebSocket.NORMAL_CLOSURE, "");
~~~

Dùng dependent future:

~~~java
CompletableFuture<WebSocket> closedOutput =
    socket.sendText("last data", true)
        .thenCompose(ws -> ws.sendClose(
            WebSocket.NORMAL_CLOSURE, ""));
~~~

`thenCompose` bảo đảm **Close send chỉ được khởi tạo khi future gửi data trước hoàn tất bình thường**. Nó **không** bảo đảm server đã xử lý data ở tầng nghiệp vụ. Nếu cần server ACK/commit, thiết kế message ID/ACK và đợi xác nhận đó **trước** closing handshake.

## 4. Close status code, reason và lỗi tham số

Một Close frame có thể mang **status code** cùng **reason UTF-8**:

| Status | Ý nghĩa thường gặp |
|---|---|
| `1000` | Normal closure |
| `1001` | Going away, ví dụ endpoint chuẩn bị dừng |
| `1008` | Policy violation |
| `1011` | Server gặp lỗi nội bộ không thể xử lý tiếp |
| `1005` | Mã sentinel cho trường hợp nhận Close không có code; không được gửi trên wire |
| `1006` | Abnormal closure, chưa nhận Close frame hợp lệ; **không được gửi trên wire** |
| `1015` | Mã sentinel liên quan TLS failure; không được gửi trên wire |
| `3000–3999` | Các status do thư viện/framework/ứng dụng đăng ký theo registry |
| `4000–4999` | Vùng riêng theo thỏa thuận ứng dụng |

**Theo Javadoc `WebSocket.sendClose` của Java SE 17:** mã đưa vào method phải nằm trong khoảng **1000–4999**; các mã `1002`, `1003`, `1006`, `1007`, `1009`, `1010`, `1012`, `1013` và `1015` bị JDK đánh dấu illegal; behavior của những code khác có thể tùy implementation. Danh sách đó **không thay thế** quy tắc giao thức/IANA: không nên gửi các sentinel codes dự trữ như 1005. Với đóng bình thường, chọn `WebSocket.NORMAL_CLOSURE`.

### Reason tối đa 123 byte UTF-8

Control frame tối đa **125 byte** payload. Khi có code, **2 byte đầu** dành cho status, còn **123 byte** để mô tả lý do. `String.length()` của Java đo đơn vị UTF-16, **không** phải số byte UTF-8:

~~~java
String reason = "Kết thúc phiên";
int bytes = reason.getBytes(StandardCharsets.UTF_8).length;
if (bytes > 123) {
    throw new IllegalArgumentException("Close reason too long");
}
socket.sendClose(WebSocket.NORMAL_CLOSURE, reason);
~~~

Snippet cần import `java.nio.charset.StandardCharsets` và biến `socket` đã mở. Lỗi reason/code có thể làm future từ `sendClose` hoàn tất exceptionally với `IllegalArgumentException`; reason `null` có thể gây `NullPointerException`. I/O lỗi hoặc output đã đóng dẫn tới exceptional completion với `IOException`.

Javadoc còn chỉ rõ: trừ trường hợp không hợp lệ về đối số (ví dụ `IllegalArgumentException`/`NullPointerException` theo contract), việc gọi sendClose sẽ dẫn output tới trạng thái đóng. Đừng retry gửi Close không giới hạn khi một lần gửi bị lỗi I/O.

**Bảo mật:** reason là dữ liệu có thể được ghi log hoặc xuất hiện ở peer; không nhét access token, session cookie, đường dẫn file bí mật hay stack trace vào reason.

## 5. `Listener.onClose` và receive demand

`WebSocket.Listener` là nơi nhận sự kiện từ phía **input**:

- `onOpen` được gọi một lần khi WebSocket kết nối; thường cấp receive demand với `socket.request(1)`.
- `onText`, `onBinary`, `onPing`, `onPong`, `onClose` là các receive methods, chịu bộ đếm demand của WebSocket.
- `onClose(socket, code, reason)` được gọi khi **nhận Close frame**. **Ngay khi onClose bắt đầu, input đã đóng**. Đây là callback cuối của listener cho WebSocket đó.
- `onError(socket, error)` báo lỗi; khi nó được gọi, **cả input và output đã đóng**. Đây cũng là callback cuối, nhưng **không** giống việc nhận Close hợp lệ.
- Java WebSocket có cơ chế **tự xử lý Close đối ứng**; listener không bắt buộc gọi `sendClose` thủ công khi peer gửi Close.

Mẫu listener theo dõi kết quả:

~~~java
static final class CloseListener implements WebSocket.Listener {
    final CompletableFuture<Integer> peerClose = new CompletableFuture<>();

    @Override
    public void onOpen(WebSocket socket) {
        socket.request(1);
    }

    @Override
    public CompletionStage<?> onClose(
            WebSocket socket, int statusCode, String reason) {
        peerClose.complete(statusCode);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public void onError(WebSocket socket, Throwable error) {
        peerClose.completeExceptionally(error);
    }
}
~~~

Đây là **đoạn code của một class**, cần import `java.net.http.WebSocket` và `java.util.concurrent.*`. Chương trình chạy được hoàn chỉnh ở phần 10 dùng listener tương tự.

### Vì sao `request(1)` quan trọng?

Receive demand ban đầu là **0**, và `request(n)` cho phép thêm `n` lần gọi receive callback. Nó **không gửi HTTP request** và không có nghĩa mỗi lần gọi tương ứng một WebSocket message hoàn chỉnh. Nếu listener tiêu thụ nhiều text fragments mà không gọi thêm `request(1)`, có thể cạn demand trước Close và làm `onClose` chưa được gọi dù peer đã gửi Close.

Trong ví dụ chỉ có Close frame, `request(1)` ở `onOpen` đủ cho callback Close. Với ứng dụng chat nhận nhiều text messages, mỗi `onText` cần quản lý nội dung và cấp demand tiếp theo theo policy.

### Peer gửi Close trước

Nếu peer gửi Close khi local output còn mở, Java WebSocket **tự quản lý Close đối ứng**. Theo Javadoc, stage mà `onClose` trả về có thể điều khiển thời điểm implementation đóng output nếu output chưa đóng. Trả `null` (mặc định) báo có thể đóng ngay; trả một stage không bao giờ complete có thể **làm trì hoãn việc tự phản hồi Close**, gây liveness bug. Chỉ custom `sendClose` trong `onClose` nếu bạn thật sự cần chọn close code/reason đối ứng theo protocol và hiểu hợp đồng callback; không gửi hai Close frames vô điều kiện.

## 6. `abort()`: dừng đột ngột cả hai phía

`socket.abort()` là method `void`. Theo Javadoc Java 17, sau khi nó **trả về**:
- `socket.isInputClosed() == true`.
- `socket.isOutputClosed() == true`.
- Pending send operations sẽ thất bại với `IOException`.
- Gọi `abort()` lại không có thêm hiệu ứng.

~~~java
socket.abort();
assert socket.isInputClosed();
assert socket.isOutputClosed();
~~~

Snippet giả định `socket` đã tạo. `abort` không gửi WebSocket Close frame có thứ tự như `sendClose`, không chờ peer, và không đảm bảo peer đã xử lý data còn pending. Do vậy nó là **force stop**, không phải “đóng sạch nhưng nhanh hơn”.

### Khi nào sử dụng?

| Tình huống | Lựa chọn hợp lý |
|---|---|
| Hoàn tất phiên bình thường và peer đáp ứng | `sendClose(1000, reason)` và đợi Close đối ứng |
| `sendClose` xong nhưng peer không trả Close trước deadline | `abort()` rồi ghi nhận timeout |
| I/O lỗi hoặc protocol state không thể tiếp tục an toàn | `abort()` hoặc để implementation dừng khi lỗi, không gửi tiếp |
| Ứng dụng buộc dừng ngay | `abort()` với chấp nhận kết nối bất thường |
| Đã gửi Close nhưng muốn đợi peer thêm ít thời gian | Không abort ngay; quan sát input/onClose có thời hạn |
| Nghiệp vụ yêu cầu biết message cuối đã commit chưa | Cần **application ACK**, Close không thay thế |

**Không suy diễn rằng abort làm rollback:** server có thể đã nhận/ghi giao dịch trước khi local client force close. Khi nối lại, cần message IDs, idempotency policy, đồng bộ trạng thái server và retry có giới hạn.

## 7. Hai future phải theo dõi riêng

Một graceful close đúng thường có ít nhất **hai sự kiện độc lập**:

1. **Close đã được gửi:** future do `sendClose` trả về hoàn tất.
2. **Peer Close đã đến:** listener `onClose` hoàn tất một future do ứng dụng quản lý.

~~~text
Application stops new sends
             │
     Wait for pending sends
             │
             ▼
  sendClose(1000, reason)
             │
             ├── send failed ───────► abort / report
             ▼
    Close-send future done
             │
             ├── peer onClose ──────► graceful path
             │
             ├── listener onError ──► error path
             │
             └── deadline expired ─► abort / timeout path
~~~

Nếu bạn chỉ gọi `sendClose(...).join()` thì mới chờ **vế 1**. Nếu bạn chỉ gọi `peerClose.join()` không có timeout, một peer treo có thể giữ thread mãi.

### `CompletableFuture.orTimeout` không tự abort

~~~java
CompletableFuture<WebSocket> sending =
    socket.sendClose(WebSocket.NORMAL_CLOSURE, "");

sending.orTimeout(2, TimeUnit.SECONDS)
    .whenComplete((ws, failure) -> {
        if (failure != null) {
            socket.abort();
        }
    });
~~~

Đoạn này là snippet cần import `java.util.concurrent.*`. `orTimeout` làm **chính future** hoàn tất exceptionally nếu chưa xong trong hạn; nó **không** tự hủy network operation hay gửi Close đối ứng. Trong ví dụ application gọi `abort()` một cách tường minh khi deadline vượt. Cũng cần một deadline thứ hai để chờ **peer Close** sau khi local Close đã gửi.

### Scheduler cho graceful deadline

Một mô hình bổ sung:

~~~java
ScheduledFuture<?> deadline = scheduler.schedule(
    () -> {
        if (!socket.isInputClosed()) {
            socket.abort();
        }
    },
    3, TimeUnit.SECONDS);

peerClose.whenComplete((code, error) -> {
    deadline.cancel(false);
    if (error != null) {
        socket.abort();
    }
});
~~~

Snippet giả định `scheduler` là `ScheduledExecutorService` đang chạy và `peerClose` là `CompletableFuture<Integer>` từ listener. Chỉ đặt timer **sau khi local Close đã gửi**; nếu không, phép đo grace period có thể không như mong muốn. Quản lý scheduler ở application lifecycle, không tạo một thread mới cho mỗi WebSocket rồi quên shutdown.

**Đóng sạch không phải hard guarantee về thời gian:** deadline là policy của ứng dụng; nếu peer không hợp tác, `abort` giúp giải phóng local sides nhưng không cam kết server hoàn tất nghiệp vụ. Nếu shutdown service đang có nhiều socket, cần coordinator và giới hạn số kết nối/scheduled tasks.

## 8. Thứ tự gửi data và race giữa nhiều threads

Trong WebSocket client Java 17, `sendText`/`sendBinary` có hợp đồng pending operations. Một pending text/binary send chưa hoàn tất hoặc chuỗi fragments chưa hoàn chỉnh có thể khiến operation khác thất bại với `IllegalStateException`. `sendClose` còn làm output đóng. Vì vậy không nên coi ba thread gửi message, ping và close là các hành động hoàn toàn độc lập.

**Mẫu khuyến nghị:** có một coordinator sở hữu lifecycle OPEN → CLOSING → CLOSED, ngừng nhận outbound messages mới khi bắt đầu đóng, chain futures cho message cuối, rồi gửi Close. Cập nhật một trạng thái ứng dụng bằng atomic/lock nếu nhiều threads cùng muốn close; chỉ một thread bắt đầu closing handshake.

Ví dụ:

~~~java
CompletableFuture<WebSocket> finalSend =
    socket.sendText("BYE", true);

CompletableFuture<WebSocket> closeSend =
    finalSend.thenCompose(ws ->
        ws.sendClose(WebSocket.NORMAL_CLOSURE, "done"));
~~~

Không thêm `sendText` mới khi state ứng dụng chuyển CLOSING. `isOutputClosed()==false` không phải atomic permission token: ngay sau kiểm tra, thread khác có thể đóng output. Luôn xử lý exceptional completion ở send futures.

**Điều không nên hứa:** future của `sendText` hoàn tất không chứng minh peer đã xử lý message theo ý nghĩa nghiệp vụ. Nếu yêu cầu “server đã lưu”, phải có ACK hoặc response message riêng rồi mới đóng.

## 9. Ví dụ chạy thật: server phản hồi Close và server không phản hồi

Để kiểm tra **nửa đóng** một cách quyết định thay vì phụ thuộc `Thread.sleep`, chương trình dùng **CountDownLatch** cho phép server giả lập trì hoãn trả Close cho đến sau khi client kiểm tra trạng thái.

- **Cooperative server:** nhận Close từ client, chờ latch; client in `input=false output=true`, server gửi Close 1000, listener nhận rồi client in `true/true`.
- **Unresponsive server:** nhận Close nhưng không trả Close; client thấy `false/true`, gọi `abort()` rồi thấy `true/true`.

Cả client lẫn server bind/kết nối trên loopback `127.0.0.1`. `TestServer` **chỉ** nhận một masked Close frame ngắn và gửi một Close frame tối giản. Nó không phải HTTP/WebSocket stack hoàn chỉnh và không được tái sử dụng trong service thật.

### 9.1. File `WebSocketCloseDemo.java`

~~~java
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.*;

public class WebSocketCloseDemo {
    static final class CloseListener implements WebSocket.Listener {
        final CompletableFuture<Integer> peerClose = new CompletableFuture<>();

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onClose(WebSocket socket,
                int statusCode, String reason) {
            peerClose.complete(statusCode);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            peerClose.completeExceptionally(error);
        }
    }

    static final class TestServer implements AutoCloseable {
        final ServerSocket listener;
        final ExecutorService worker = Executors.newSingleThreadExecutor();
        final CountDownLatch mayFinish = new CountDownLatch(1);
        final CompletableFuture<Void> closeReceived = new CompletableFuture<>();
        final boolean replyToClose;
        final Future<?> task;

        TestServer(boolean replyToClose) throws IOException {
            this.replyToClose = replyToClose;
            listener = new ServerSocket(0, 1,
                InetAddress.getByName("127.0.0.1"));
            task = worker.submit(this::run);
        }

        URI uri() {
            return URI.create("ws://127.0.0.1:"
                + listener.getLocalPort() + "/close");
        }

        void release() {
            mayFinish.countDown();
        }

        void run() {
            try (Socket peer = listener.accept()) {
                peer.setSoTimeout(5_000);
                InputStream in = peer.getInputStream();
                OutputStream out = peer.getOutputStream();

                ByteArrayOutputStream headerBytes = new ByteArrayOutputStream();
                int b;
                while ((b = in.read()) != -1) {
                    headerBytes.write(b);
                    int n = headerBytes.size();
                    byte[] data = headerBytes.toByteArray();
                    if (n >= 4 && data[n-4] == '\r'
                            && data[n-3] == '\n'
                            && data[n-2] == '\r'
                            && data[n-1] == '\n') {
                        break;
                    }
                    if (n > 16_384) throw new IOException("Oversized handshake");
                }

                String headers = headerBytes.toString(StandardCharsets.US_ASCII);
                String key = null;
                for (String line : headers.split("\r\n")) {
                    if (line.regionMatches(true, 0,
                            "Sec-WebSocket-Key:", 0, 18)) {
                        key = line.substring(18).trim();
                    }
                }
                if (key == null) throw new IOException("No WebSocket key");

                byte[] digest = MessageDigest.getInstance("SHA-1").digest(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                    .getBytes(StandardCharsets.US_ASCII));
                String accept = Base64.getEncoder().encodeToString(digest);
                out.write(("HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n")
                    .getBytes(StandardCharsets.US_ASCII));
                out.flush();

                int first = in.read();
                int second = in.read();
                if (first < 0 || second < 0
                        || (first & 0x0f) != 8
                        || (second & 0x80) == 0
                        || (second & 0x7f) > 125) {
                    throw new IOException("Expected masked Close frame");
                }
                byte[] mask = in.readNBytes(4);
                int len = second & 0x7f;
                byte[] payload = in.readNBytes(len);
                if (mask.length != 4 || payload.length != len) {
                    throw new EOFException("Truncated Close frame");
                }
                for (int i = 0; i < payload.length; i++) {
                    payload[i] ^= mask[i % 4];
                }
                if (payload.length < 2
                        || (payload[0] & 0xff) != 3
                        || (payload[1] & 0xff) != 232) {
                    throw new IOException("Expected close code 1000");
                }
                closeReceived.complete(null);

                if (!mayFinish.await(5, TimeUnit.SECONDS)) {
                    throw new IOException("Test not released");
                }
                if (replyToClose) {
                    out.write(new byte[] {
                        (byte) 0x88, 0x02, 0x03, (byte) 0xe8
                    });
                    out.flush();
                }
            } catch (Exception error) {
                closeReceived.completeExceptionally(error);
                throw new CompletionException(error);
            }
        }

        @Override
        public void close() throws Exception {
            release();
            try {
                task.get(5, TimeUnit.SECONDS);
            } finally {
                listener.close();
                worker.shutdownNow();
            }
        }
    }

    static WebSocket connect(TestServer server, CloseListener listener)
            throws Exception {
        return HttpClient.newHttpClient().newWebSocketBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .buildAsync(server.uri(), listener)
            .get(3, TimeUnit.SECONDS);
    }

    static void cooperative() throws Exception {
        try (TestServer server = new TestServer(true)) {
            CloseListener listener = new CloseListener();
            WebSocket socket = connect(server, listener);
            socket.sendClose(WebSocket.NORMAL_CLOSURE, "bye")
                .get(3, TimeUnit.SECONDS);
            server.closeReceived.get(3, TimeUnit.SECONDS);

            System.out.println("graceful sent: input="
                + socket.isInputClosed()
                + " output=" + socket.isOutputClosed());

            server.release();
            int code = listener.peerClose.get(3, TimeUnit.SECONDS);
            System.out.println("graceful peer: code=" + code
                + " input=" + socket.isInputClosed()
                + " output=" + socket.isOutputClosed());
        }
    }

    static void unresponsive() throws Exception {
        try (TestServer server = new TestServer(false)) {
            CloseListener listener = new CloseListener();
            WebSocket socket = connect(server, listener);
            socket.sendClose(WebSocket.NORMAL_CLOSURE, "bye")
                .get(3, TimeUnit.SECONDS);
            server.closeReceived.get(3, TimeUnit.SECONDS);

            System.out.println("stalled before abort: input="
                + socket.isInputClosed()
                + " output=" + socket.isOutputClosed());
            socket.abort();
            System.out.println("stalled after abort: input="
                + socket.isInputClosed()
                + " output=" + socket.isOutputClosed());
            server.release();
        }
    }

    public static void main(String[] args) throws Exception {
        cooperative();
        unresponsive();
    }
}
~~~

### 9.2. Biên dịch và kết quả

Dùng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 WebSocketCloseDemo.java
java WebSocketCloseDemo
~~~

Stdout đã được kiểm chứng thực tế (biên dịch với `--release 17`, chạy trên Java và loopback):

~~~text
graceful sent: input=false output=true
graceful peer: code=1000 input=true output=true
stalled before abort: input=false output=true
stalled after abort: input=true output=true
~~~

### 9.3. Giải thích từng dòng

1. `graceful sent`: client đã gửi Close nhưng server đang đợi latch, nên output đóng còn input mở.
2. `graceful peer`: server phát Close frame mã 1000, `onClose` của client nhận; input đóng và output đã đóng từ trước.
3. `stalled before abort`: phía server không gửi Close đối ứng dù đã nhận Close của client, cho thấy `sendClose` không tự đóng input.
4. `stalled after abort`: gọi `abort()` bảo đảm đóng cả hai phía khi method trả về.

**Điểm đồng bộ:** `CountDownLatch` khiến trạng thái đo được không phụ thuộc độ trễ mạng. Server test chỉ phục vụ một kết nối mỗi lần, không xử lý text/binary frames hay mọi corner case RFC; production phải dùng WebSocket server implementation hoàn chỉnh.

**Vì sao code sử dụng masking?** RFC 6455 yêu cầu client-to-server frames có mask. Test fixture giải mã 4-byte masking key để đọc status Close 1000 trong payload. Server-to-client Close frame của fixture không mask. Điều này mô tả đúng nguyên tắc wire-format cơ bản mà không tự nhận là parser production.

**Vì sao `onOpen` gọi `request(1)`?** Vì nhận Close là một receive callback và phải có demand. Nếu không có demand, listener có thể không bao giờ báo Close đối ứng, dẫn đến timeout giả.

## 10. Peer đóng trước, hai phía đóng đồng thời và Close code khác nhau

### Peer đóng trước

Khi server gửi Close trước:
- Input client đóng khi `onClose` được gọi.
- Java WebSocket có thể tự phản hồi Close cho peer qua output nếu output còn mở.
- Theo hợp đồng `Listener.onClose`, completion stage trả về có thể quyết định khi nào output được phép đóng.
- Không bắt buộc viết `onClose(...){ socket.sendClose(...); }` chỉ để “đáp lại”; gửi Close hai lần vô ý là không cần thiết.

Nếu handler muốn custom Close reason/code ở đường peer-initiated, phải đọc contract Javadoc kỹ; trong trường hợp đơn giản, trả `null` hoặc completed stage và để implementation phản hồi.

### Hai bên cùng gửi Close

~~~text
Client                                        Server
send Close(1000) ────────────────►           send Close(1001)
                 ◄───────────────────────────
recv Close(1001)                               recv Close(1000)
~~~

Theo RFC 6455, code mà mỗi endpoint ghi nhận là code trong **Close frame đầu tiên nó nhận**. Do đó local code và remote code có thể khác trong tình huống đóng đồng thời mà **không** có lỗi giao thức. Ghi logs riêng `localCloseCode` và `remoteCloseCode` thay vì ép trùng nhau.

### Transport đứt trước Close

Khi socket TCP bị reset, firewall/proxy cắt đường hay TLS transport hỏng, listener có thể báo lỗi thay vì Close. `1006` là **ký hiệu abnormal closure**, không phải Close frame có code 1006 được peer gửi. Không coi mọi connection drop là lỗi xác thực WebSocket; phân biệt timeout, TCP/TLS, proxy idle limit và lỗi ứng dụng.

## 11. Cleanup và reconnect không đồng nghĩa hoàn tất nghiệp vụ

Một phiên WebSocket thường phục vụ các giao dịch dài:
- Client gửi message A và server có thể đã nhận nhưng chưa ghi database.
- Client gọi `sendClose` và đợi Close đối ứng.
- Server phản hồi Close nhưng không có cơ chế nào của RFC bảo đảm A đã commit vào database.
- Nếu kết nối bị abort trong lúc có request nghiệp vụ pending, phía client có thể không biết server đã thực hiện A hay chưa.

Vì vậy khi cần at-least-once/at-most-once semantics:
- Gắn **message ID**, sequence/offset, timestamp khi phù hợp.
- Xây **ACK ứng dụng** sau khi server xử lý/ghi nhận theo contract.
- Chỉ đánh dấu request hoàn tất dựa trên ACK, không dựa vào Close frame.
- Dùng idempotency/deduplication cho retry sau disconnect.
- Khi reconnect, đồng bộ trạng thái theo server-truth thay vì resend toàn bộ vô điều kiện.

### `ws://` và `wss://`

- `ws://` không có TLS; ví dụ chỉ bind loopback và không gửi secret.
- `wss://` bảo vệ kênh bằng TLS. Vẫn phải kiểm tra certificate/hostname đúng, không dùng trust-all để xử lý lỗi.
- Một reverse proxy có thể chấm dứt TLS; phần backend cần bảo vệ riêng theo threat model.
- Không đặt Bearer token, session cookie hay dữ liệu nhạy cảm trong close reason/logs; bảo vệ cả opening handshake headers.
- Proxy/load balancer có thể có idle timeout. Ping/Pong giúp kiểm tra liveness theo policy nhưng **không thay closing handshake**.

### Reconnect sau `abort`

Không tái sử dụng `WebSocket` đã đóng. Tạo kết nối mới qua `HttpClient.newWebSocketBuilder()`; áp dụng **retry/backoff có jitter**, giới hạn thử lại, xác minh authentication còn hợp lệ và phục hồi trạng thái dựa trên ACK. Đừng tự động reconnect vô hạn khi bị từ chối chính sách vì có thể tạo tải lớn.

## 12. Checklist shutdown cho WebSocket client thực tế

1. **Chuyển trạng thái ứng dụng sang CLOSING** để ngăn tạo outbound sends mới.
2. **Theo dõi pending send futures** và quyết định chờ bao lâu trước khi đóng; không dùng sendText sau khi output đóng.
3. **Giữ receive demand đủ** để xử lý Close frame; không vô tình chặn listener.
4. **Gửi `sendClose(NORMAL_CLOSURE, reason)`** với code/reason hợp lệ, không đưa secret vào reason.
5. **Đặt deadline cho Close send future**; lỗi gửi không phải “đã đóng sạch”.
6. **Đợi listener `onClose` hoặc `onError`** với deadline riêng; phân biệt peer Close và transport error.
7. **Nếu quá hạn, gọi `abort()`** và ghi nhận abnormal/forced shutdown; không khẳng định peer đã xử lý message cuối.
8. **Giải phóng tài nguyên ứng dụng** như scheduled tasks, custom executor, message queues và subscription state theo đúng owner.
9. **Lưu telemetry**: local/remote close code, thời gian gửi Close, thời gian đợi peer Close, timeout/abort/error và số pending messages.
10. **Nếu reconnect**, chỉ nối lại khi policy cho phép; tránh mất/lặp nghiệp vụ bằng application ACK và idempotency.

## 13. Lỗi thường gặp và cách sửa

| Hiểu sai | Cách hiểu đúng |
|---|---|
| “`sendClose(...).join()` xong là toàn bộ WebSocket closed.” | Future chỉ xác nhận Close **đã gửi**, input có thể còn mở |
| “sendClose đóng cả input lẫn output.” | `sendClose` đóng **output**, đợi peer Close cho input |
| “`isInputClosed` và `isOutputClosed` luôn giống nhau.” | Hai trạng thái **độc lập** |
| “`onClose` luôn cần tự gọi `sendClose` để trả lời.” | JDK tự quản lý Close đối ứng, cần đọc contract callback |
| “`onClose` có thể tiếp tục nhận text sau đó.” | Đây là callback cuối của socket |
| “Không có receive demand vẫn chắc gọi onClose.” | Cần `request(n)` để cấp số lần receive callbacks |
| “`abort` giống gửi Close 1000 nhưng nhanh.” | Abort đóng **đột ngột**, không có orderly handshake |
| “`abort` phát Close code 1006 lên wire.” | 1006 là sentinel abnormal, không được gửi |
| “Reason tối đa 123 ký tự Java.” | Giới hạn **123 byte UTF-8** |
| “`orTimeout` tự kết thúc socket.” | Nó chỉ điều chỉnh completion future; cần abort nếu muốn force close |
| “Đóng WebSocket nghĩa server đã commit bản tin cuối.” | Phải có application-level ACK/transaction confirmation |
| “Cứ kiểm tra `isOutputClosed()==false` rồi gửi là an toàn đa luồng.” | Có race; cần coordinator và xử lý future exception |
| “`sendText` và `sendClose` khởi động độc lập luôn đúng thứ tự.” | Chain futures để bảo đảm gửi trước Close |
| “`onError` bắt buộc được gọi sau mọi abort.” | Javadoc không hứa callback riêng cho mỗi lần abort |
| “Close hợp lệ luôn tương đương TCP đóng ngay tức thì.” | WebSocket API và underlying transport có lifecycle khác |
| “Có thể dùng lại một WebSocket đã đóng.” | Cần tạo kết nối mới |
| “TestServer đơn giản của bài là server sản xuất được.” | Nó chỉ hỗ trợ handshake và short Close frame của test |
| “Mất mạng luôn có Close code peer gửi.” | Có thể là abnormal TCP/TLS loss không có Close frame |

## 14. Bài tập tự kiểm tra

1. Hai phía input/output của `java.net.http.WebSocket` có vai trò gì? Khi nào chúng có giá trị khác nhau?
2. Sau `socket.sendClose(1000,"").join()`, điều gì đã được xác nhận và điều gì chưa?
3. `Listener.onClose` cho biết điều gì về input state **ngay khi callback bắt đầu**?
4. WebSocket Java có tự phản hồi Close nhận vào không? Trường hợp nào cần custom Close trong listener?
5. Tại sao `request(1)` ở `onOpen` quan trọng? Nó có gửi một message ra mạng không?
6. Một server không trả Close sau 5 giây. Để tránh đợi mãi, policy của client nên là gì?
7. Sau `abort()` trả về, hai getter `isInputClosed/isOutputClosed` phải trả giá trị gì?
8. `abort` có bảo đảm gửi Close status 1006 hay chờ peer trả lời không?
9. Vì sao `1005`, `1006`, `1015` không được phát như Close status trên wire?
10. Một close reason gồm 110 ký tự tiếng Việt có luôn hợp lệ với giới hạn 123 byte không? Kiểm tra thế nào?
11. Phân biệt timeouts của `sendClose` future và việc đợi `onClose` future.
12. Tại sao `CompletableFuture.orTimeout` không bảo đảm network operation đã dừng?
13. Viết đoạn ghép `sendText("done",true)` rồi `sendClose(...)` theo thứ tự.
14. Client gửi Close 1000, server gửi Close 1001 cùng lúc. Vì sao logs có thể khác?
15. Trong demo, tại sao `graceful sent` hiển thị `input=false output=true`?
16. Trong demo, tại sao gọi `abort` trên một kết nối không phản hồi lại cho `true/true`?
17. Khi server đã nhận message trước Close, liệu Close trả lời có chứng minh database đã ghi message không?
18. Nếu cần chống gửi lại nghiệp vụ khi reconnect, ứng dụng nên có những identifier/ACK nào?
19. `wss://` giải quyết điều gì và điều gì vẫn cần xử lý ở application/proxy?
20. `java.net.http.WebSocket` có phải cùng API với `javax.websocket.Session` không?

**Đáp án cốt lõi:** (1) input nhận/output gửi độc lập; (2) Close được gửi, chưa chắc đã nhận Close đối ứng; (3) input đã đóng; (4) JDK tự xử lý, custom chỉ khi cần contract đặc biệt; (5) receive demand, không gửi ra mạng; (6) graceful wait có deadline rồi abort; (7) true/true; (8) không; (9) reserved/sentinel; (10) không, đếm UTF-8 bytes; (11) hai sự kiện khác nhau; (12) chỉ thay trạng thái future; (13) `thenCompose`; (14) mỗi bên thấy Close frame đầu tiên nó nhận; (15) server chưa trả Close; (16) abort đóng đột ngột hai phía; (17) không; (18) IDs, ACK, dedup/idempotency; (19) TLS bảo vệ kênh, không thay app ACK/authorization; (20) hai API khác nhau.

## 15. Tổng kết

- **Hai chiều độc lập:** `WebSocket.isInputClosed` và `isOutputClosed` không cần đổi cùng lúc; trạng thái đã đóng không mở lại.
- **`sendClose` đóng output có thứ tự:** future hoàn tất khi gửi Close, **không** khi peer xác nhận; input có thể vẫn mở.
- **`onClose` là sự kiện nhận Close:** input đã đóng khi callback bắt đầu; implementation tự quản lý Close đối ứng và phải có receive demand.
- **`abort` dừng đột ngột:** khi trả về cả hai phía đóng, pending sends thất bại; dùng khi không thể/không nên chờ graceful.
- **Close code/reason:** dùng status 1000 cho bình thường; không gửi 1006; reason giới hạn 123 byte UTF-8.
- **Quản lý bằng deadline:** ngừng outbound sends, chờ pending sends, gửi Close, đợi peer Close có timeout, fallback abort và cleanup.
- **Close không phải ACK nghiệp vụ:** reconnect/retry cần message IDs, server confirmation và idempotency.
- **Ví dụ Java 17 đã kiểm thử** trên TCP loopback với trạng thái trước/sau Close đối ứng và trước/sau abort.

### Tài liệu tham khảo

- [Oracle Java SE 17 — WebSocket: sendClose, isInputClosed, isOutputClosed và abort](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html)
- [Oracle Java SE 17 — WebSocket.Listener: onClose, onError, request(n)](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
- [Oracle Java SE 17 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html)
- [Oracle Java SE 17 — HttpClient.newWebSocketBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)
- [IANA — WebSocket Close Code Number Registry](https://www.iana.org/assignments/websocket/websocket.xhtml)
