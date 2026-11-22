# sendClose, abort và đóng kết nối đúng trạng thái (WebSocket, Java 11+)

**Chủ đề cha: WebSocket.** Khi dùng `java.net.http.WebSocket` (API chuẩn từ Java 11), đóng kết nối không đơn giản là gọi một hàm `close()`. WebSocket là giao thức hai chiều; Java theo dõi **chiều gửi (output)** và **chiều nhận (input)** riêng biệt. Phương thức `sendClose(...)` bắt đầu đóng **có trật tự** bằng Close control frame; `abort()` thì **đóng đột ngột cả hai chiều**. Muốn kết thúc đúng, ứng dụng còn phải xử lý `WebSocket.Listener.onClose(...)`, tương tác bất đồng bộ và tình huống phía bên kia không bao giờ phản hồi Close.

Bài học giải thích chính xác hợp đồng Java 11, giới hạn close code/reason, sơ đồ trạng thái, cách quản lý futures, quy trình graceful shutdown có hạn chót, và bài kiểm thử với WebSocket server nhỏ chạy trên loopback. Những API được sử dụng vẫn được hỗ trợ trên Java hiện đại.

## 1. Một WebSocket có hai chiều đóng độc lập

Java định nghĩa mỗi WebSocket có **input side** và **output side**. Từng chiều có thể ở trạng thái mở hoặc đóng. Khi một chiều đã đóng, nó **không mở lại** trên chính WebSocket đó.

- **Input mở:** client còn có thể nhận các sự kiện từ server thông qua `WebSocket.Listener`.
- **Output mở:** client còn có thể gửi text, binary, ping, pong hoặc Close frame phù hợp.
- **Output đóng:** không thể tiếp tục gửi data frame bình thường; các lời gọi gửi mới sẽ không được xử lý như khi còn mở.
- **Input đóng:** không còn nhận thông điệp từ bên kia trên WebSocket đó.
- **Hai chiều đóng:** WebSocket đó kết thúc; muốn kết nối lại phải tạo WebSocket mới bằng builder.

Kiểm tra bằng hai phương thức:

```java
boolean inputClosed = webSocket.isInputClosed();
boolean outputClosed = webSocket.isOutputClosed();
```

Đây là đoạn minh họa với biến `webSocket` kiểu `java.net.http.WebSocket`. Không có phương thức `webSocket.isClosed()` bao quát cả hai chiều trong API này.

| `isInputClosed()` | `isOutputClosed()` | Diễn giải |
| :---: | :---: | --- |
| `false` | `false` | Còn nhận và còn gửi |
| `false` | `true` | Đã đóng chiều gửi, **vẫn có thể chờ Close từ peer** |
| `true` | `false` | Peer đã gửi Close; chiều gửi có thể còn đang xử lý phản hồi theo `onClose` |
| `true` | `true` | Đã đóng cả hai chiều |

Hai phép kiểm tra là **ảnh chụp trạng thái tại thời điểm gọi**, không phải khóa đồng bộ. Trong ứng dụng nhiều thread, trạng thái có thể đổi ngay sau `if (!webSocket.isOutputClosed())`; mã vẫn cần xử lý lỗi hoặc future thất bại khi thao tác gửi.

### Sơ đồ close handshake

```text
Client                                      Server
  |                                            |
  |               (đang trao đổi)              |
  |                                            |
  |------ Close(code=1000, reason="") -------->|
  |       client output: closed                 |
  |       client input:  open                   |
  |                                            |
  |<----- Close(code=1000, reason="") ---------|
  |       client input: closed                  |
  |                                            |
  +-- cả input và output đều đóng ------------>+
```

Đây là tiến trình **lý tưởng khi client chủ động đóng và server phản hồi**. WebSocket peer có thể chủ động gửi Close trước hoặc hai đầu gửi Close gần đồng thời. Không được suy ra “Close được gửi thành công” đồng nghĩa “Close đáp lại đã nhận”.

## 2. sendClose(int statusCode, String reason): đóng chiều gửi có trật tự

Chữ ký Java 11:

```java
CompletableFuture<WebSocket> sendClose(int statusCode, String reason);
```

Phương thức khởi tạo gửi WebSocket **Close control frame**, mang code và reason. Nó trả `CompletableFuture<WebSocket>`:

- Future **hoàn tất bình thường** khi thao tác gửi Close frame hoàn tất.
- Future **hoàn tất exceptionally** nếu thao tác gửi thất bại (ví dụ I/O, output đã đóng, status/reason không hợp lệ).
- Theo Javadoc, trừ tình huống tham số không hợp lệ khiến future hoàn tất với `IllegalArgumentException` hoặc có `NullPointerException`, chiều **output** sẽ bị đóng theo hợp đồng `sendClose`, kể cả khi một lỗi gửi khác xảy ra.
- **Chiều input vẫn có thể mở**, chờ peer gửi Close, hoặc cho đến khi `abort()` hay lỗi làm nó đóng.

Cách dùng thường gặp:

```java
webSocket.sendClose(WebSocket.NORMAL_CLOSURE, "")
        .orTimeout(5, TimeUnit.SECONDS)
        .join();
```

Đoạn minh họa cần import `java.net.http.WebSocket` và `java.util.concurrent.TimeUnit`. `WebSocket.NORMAL_CLOSURE` có giá trị **1000**. `CompletableFuture.orTimeout` có từ Java 9 nên tương thích Java 11.

**Giới hạn quan trọng:** Future này báo rằng **Close đã được gửi**, **không phải** đã nhận Close phản hồi hoặc đóng cả hai chiều. Một thao tác `join()` với future đó không đủ để bảo đảm kết nối đã kết thúc toàn bộ.

## 3. abort(): đóng đột ngột input và output

Chữ ký:

```java
void abort();
```

`abort()` đóng cả hai phía của WebSocket **ngay theo hợp đồng**. Khi `abort()` trả về, `isInputClosed()` và `isOutputClosed()` đều là `true`. Các lệnh gửi đang chờ có thể thất bại với `IOException`; gọi `abort()` thêm lần nữa không có tác dụng.

**Khác biệt cốt lõi:**

| Tiêu chí | `sendClose(...)` | `abort()` |
| --- | --- | --- |
| Bản chất | Gửi WebSocket Close frame, đóng chiều output theo trình tự | Đóng cả hai chiều đột ngột |
| Có trao đổi Close theo giao thức? | Có, nếu gửi được | Không cam kết hoàn tất close handshake |
| Kết quả trả về | `CompletableFuture<WebSocket>` | `void` |
| Input còn mở sau lời gọi? | **Có thể còn mở** để đợi phản hồi | Không; input đóng khi `abort()` trả về |
| Lệnh gửi đang chờ | Có thể hoàn tất hoặc lỗi theo thứ tự trạng thái/I/O | Thất bại với `IOException` |
| Thích hợp khi | Kết thúc phiên thông thường | Timeout, lỗi nghiêm trọng, peer không phản hồi, dọn tài nguyên khẩn cấp |

Đừng gọi `abort()` ngay lập tức sau mỗi `sendClose()` rồi gọi đó là graceful closure: bạn có thể hủy khả năng nhận Close phản hồi. Hướng tốt hơn là **sendClose → chờ peer Close có hạn chót → abort nếu không thể hoàn tất**.

Cũng đừng tưởng `abort()` bảo đảm `Listener.onClose(...)` được gọi. `onClose` tương ứng với **Close message được nhận**, còn abort là kết thúc đột ngột. Trong trường hợp lỗi, listener có thể nhận `onError`; không dựa vào một callback cụ thể sau khi chính chương trình gọi abort để hoàn tất mọi promise.

## 4. Close code và reason có quy tắc riêng

WebSocket Close frame không dùng **HTTP status code** 200/404/500. Nó dùng WebSocket closure code.

`WebSocket.NORMAL_CLOSURE` là **1000**, biểu thị đóng bình thường. Trong Java 11:

- `statusCode` gửi bằng `sendClose` phải nằm trong khoảng **1000–4999**.
- Javadoc chỉ rõ các mã **1002, 1003, 1006, 1007, 1009, 1010, 1012, 1013, 1015** không hợp lệ khi truyền vào phương thức này.
- Hành vi với một số mã khác phụ thuộc implementation; đừng xem mọi con số trong khoảng là mã ứng dụng tùy ý, hay trộn lẫn code theo RFC với việc API Java 11 chấp nhận.
- Theo RFC 6455, **1005, 1006, 1015 là các mã dành riêng để mô tả trạng thái, không được gửi nguyên dạng trên wire**. Dù cách xử lý từng mã khác nhau theo API/implementation, hãy tránh sử dụng các mã này cho lời gọi sendClose.
- Với đóng thông thường, nên dùng **`WebSocket.NORMAL_CLOSURE` và `""`**. Dùng mã khác chỉ khi hợp đồng ứng dụng và JDK thực sự cho phép.

**Giới hạn `reason` là 123 byte UTF-8, KHÔNG phải 123 ký tự Java.** Close control frame tối đa 125 byte: 2 byte status code và tối đa 123 byte reason.

| Reason | Số ký tự UTF-16 (`length()`) | Độ dài UTF-8 |
| --- | :---: | :---: |
| `"ok"` | 2 | 2 byte |
| `"đóng"` | 4 | 6 byte |
| 30 lần emoji `😀` | 60 | 120 byte |
| 31 lần emoji `😀` | 62 | 124 byte — **quá giới hạn** |

### Ví dụ chạy độc lập: `CloseReasonBytes.java`

```java
import java.nio.charset.StandardCharsets;

public class CloseReasonBytes {
    private static int bytes(String text) {
        return text.getBytes(StandardCharsets.UTF_8).length;
    }

    public static void main(String[] args) {
        String shortText = "đóng";
        String within = "😀".repeat(30);
        String tooLong = "😀".repeat(31);

        System.out.println("Vietnamese chars: " + shortText.length());
        System.out.println("Vietnamese bytes: " + bytes(shortText));
        System.out.println("30 emoji bytes: " + bytes(within));
        System.out.println("31 emoji bytes: " + bytes(tooLong));
        System.out.println("30 eligible: " + (bytes(within) <= 123));
        System.out.println("31 eligible: " + (bytes(tooLong) <= 123));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 CloseReasonBytes.java
java CloseReasonBytes
```

```text
Vietnamese chars: 4
Vietnamese bytes: 6
30 emoji bytes: 120
31 emoji bytes: 124
30 eligible: true
31 eligible: false
```

Đây là bài kiểm thử **độ dài byte của reason**, không thay thế validation thực tế của `sendClose`. Nếu truyền reason không hợp lệ, Java 11 có thể hoàn tất future gửi một cách exceptionally với `IllegalArgumentException`. Không để người dùng không tin cậy tự quyết định code/reason vượt hạn mức; cũng không đưa token, credential hoặc chi tiết nội bộ nhạy cảm vào reason gửi qua mạng.

## 5. onClose: ghi nhận Close từ phía bên kia

`WebSocket.Listener` có callback:

```java
CompletionStage<?> onClose(
        WebSocket webSocket, int statusCode, String reason);
```

Đây là callback **khi nhận Close message từ peer**. Theo Javadoc:

1. Khi `onClose` bắt đầu, **input đã đóng**.
2. Đây là **lần gọi cuối** từ WebSocket đó đến listener.
3. Nếu **output chưa đóng**, `CompletionStage` mà listener trả về được dùng để xác định khi nào WebSocket được phép đóng output. Nếu trả `null`, coi như đã hoàn tất ngay.
4. Nếu chương trình muốn tự phản hồi bằng một mã/reason khác, có thể gọi `sendClose(...)` trong `onClose` theo đúng hợp đồng. Không để stage trả về không hoàn tất vô hạn: điều đó có thể ngăn output đóng.
5. Nếu output **đã** đóng vì client từng gọi `sendClose`, việc nhận `onClose` hoàn tất quá trình đóng hai chiều.

Ví dụ một listener chỉ ghi nhận mã đóng:

```java
static final class CloseListener implements WebSocket.Listener {
    final CompletableFuture<Integer> peerClose = new CompletableFuture<>();

    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket ws, CharSequence data, boolean last) {
        ws.request(1);
        return null;
    }

    @Override
    public CompletionStage<?> onClose(
            WebSocket ws, int code, String reason) {
        peerClose.complete(code);
        return null;
    }

    @Override
    public void onError(WebSocket ws, Throwable error) {
        peerClose.completeExceptionally(error);
    }
}
```

Đây là **đoạn khai báo lớp lồng minh họa**, cần import `WebSocket`, `CompletableFuture` và `CompletionStage` trong một lớp Java. `ws.request(1)` rất quan trọng: Java WebSocket dùng **bộ đếm nhu cầu nhận callback** cho các receive methods, bao gồm `onClose`. Listener phải tiếp tục yêu cầu callback khi xử lý dữ liệu và chờ Close.

Không nhầm `request(1)` với “đọc một byte”: nó cho phép **một callback nhận** (text có thể phân mảnh, Close chỉ một callback). `onOpen` và `onError` không tiêu thụ bộ đếm nhận. Khi `onClose` hoặc `onError` đã xảy ra, không có thêm callback nào từ chính WebSocket đó.

## 6. onError khác onClose

`onClose` và `onError` đều kết thúc luồng callbacks trên một WebSocket nhưng không giống nhau:

- **`onClose(ws, code, reason)`:** có Close control frame từ peer; input đã đóng, và code/reason phản ánh message nhận được.
- **`onError(ws, Throwable)`:** báo lỗi trong quá trình vận hành hoặc callback. Khi callback này bắt đầu, cả input và output đã đóng theo hợp đồng; không có Close code từ peer bắt buộc phải tồn tại.
- `onError` không phải tín hiệu rằng một `abort()` do ứng dụng gọi **luôn** sinh callback này. Khi cleanup, hãy bảo đảm tương lai chờ đóng của ứng dụng được kết thúc ngay cả nếu listener không có callback nữa.
- Không ném exception từ `onError`. Javadoc lưu ý hành vi khi `onError` tự ném lỗi là không xác định; hãy ghi nhận, hoàn tất promises và giải phóng tài nguyên riêng.

Đừng chỉ chờ `onClose` vô thời hạn trong khi peer đã mất mạng hoặc bị abort. Nên thiết kế một deadline và một đường lỗi rõ ràng cho mọi futures ở tầng ứng dụng.

## 7. Ngữ nghĩa các futures: “đã gửi” khác “đã nhận”

Khi gọi:

```java
CompletableFuture<WebSocket> sent =
        ws.sendClose(WebSocket.NORMAL_CLOSURE, "");

sent.thenRun(() -> System.out.println("Close frame was sent"));
```

Future `sent` **không phải** tương lai cho sự kiện peer đã gửi Close phản hồi. Nó chỉ theo dõi **thao tác gửi Close ở client**. Muốn biết peer đã phản hồi, tạo một `CompletableFuture` riêng và hoàn tất nó trong `Listener.onClose` như ở mục trước.

Nên phân biệt ba cột mốc:

| Mốc | Nguồn tín hiệu | Có thể kết luận |
| --- | --- | --- |
| Close send future hoàn tất bình thường | `sendClose(...)` | Close frame phía client đã gửi xong |
| Listener nhận `onClose` | Peer gửi Close | Input phía client đã đóng |
| `isInputClosed() && isOutputClosed()` | Trạng thái hai chiều | WebSocket đó không còn gửi/nhận |

Dùng `CompletableFuture.orTimeout(...)` hoặc công cụ deadline tương ứng để tránh chờ vô hạn. **Lưu ý:** `orTimeout` chỉ khiến future chờ hoàn tất exceptionally khi hết hạn; nó **không tự gọi `ws.abort()`**. Nếu hệ thống phải giải phóng tài nguyên thật sự khi timeout, cần chủ động abort hoặc đóng theo chính sách.

## 8. Ví dụ client hoàn chỉnh: sendClose rồi đợi phản hồi có giới hạn

Ví dụ yêu cầu có WebSocket server đang chạy tại URI được cung cấp, như `ws://127.0.0.1:8080/ws`. Server cần chấp nhận một text message và đáp ứng Close handshake. Vì phụ thuộc server, **không có stdout cố định**; bài kiểm thử local có đầu ra xác định nằm ở mục tiếp theo.

### Tệp `WebSocketGracefulClient.java`

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public class WebSocketGracefulClient {
    static final class Listener implements WebSocket.Listener {
        final CompletableFuture<Integer> peerClose =
                new CompletableFuture<>();

        @Override
        public void onOpen(WebSocket ws) {
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket ws, CharSequence data, boolean last) {
            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket ws, int code, String reason) {
            peerClose.complete(code);
            return null;
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            peerClose.completeExceptionally(error);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java WebSocketGracefulClient ws://host/path");
        }

        Listener listener = new Listener();
        WebSocket ws = HttpClient.newHttpClient()
                .newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .buildAsync(URI.create(args[0]), listener)
                .orTimeout(5, TimeUnit.SECONDS)
                .join();

        try {
            ws.sendText("hello", true)
                    .orTimeout(5, TimeUnit.SECONDS).join();

            ws.sendClose(WebSocket.NORMAL_CLOSURE, "")
                    .orTimeout(5, TimeUnit.SECONDS).join();

            int code = listener.peerClose
                    .orTimeout(5, TimeUnit.SECONDS).join();

            System.out.println("peer close code: " + code);
            System.out.println("both directions closed: "
                    + (ws.isInputClosed() && ws.isOutputClosed()));
        } finally {
            if (!ws.isInputClosed() || !ws.isOutputClosed()) {
                ws.abort();
            }
        }
    }
}
```

Biên dịch:

```bash
javac --release 11 -encoding UTF-8 WebSocketGracefulClient.java
```

Chạy khi có một server WebSocket thực sự:

```bash
java WebSocketGracefulClient ws://127.0.0.1:8080/ws
```

**Cơ chế:** `sendText("hello", true)` kết thúc một text message; tiếp đó gửi Close. Future riêng trong listener đợi Close phản hồi. `finally` dùng `abort()` làm đường cleanup nếu chưa đóng đủ hai chiều, ví dụ server không trả Close hoặc một thao tác bị lỗi.

**Giới hạn của ví dụ:** Lời gọi `buildAsync(...).join()` xảy ra **trước** khối `try` vì chưa có WebSocket để abort nếu connect thất bại. Deadline này áp dụng khi thiết lập kết nối, không thay thế toàn bộ heartbeat/idle timeout của ứng dụng. Nếu server tự gửi Close trước khi client gọi `sendClose`, futures gửi có thể lỗi; caller phải quyết định chính sách xử lý thay vì cố gửi tiếp.

## 9. Integration test local: quan sát cả graceful close lẫn abort

Để kiểm chứng **trạng thái thực tế của WebSocket Java 11** mà không phụ thuộc Internet, ta sử dụng một server WebSocket tối thiểu trên loopback. Server này chỉ phục vụ fixture: đọc HTTP opening handshake, gửi `101 Switching Protocols`, nhận một **Close frame đã mask** từ Java client, rồi:

- Ở lượt **graceful**, gửi lại Close frame code 1000.
- Ở lượt **không phản hồi**, giữ kết nối mở để phía client phát hiện rằng `sendClose` **chỉ đóng output** rồi chủ động gọi `abort()`.

Server test cố tình không triển khai toàn bộ RFC 6455 (không xử lý nhiều message, phân mảnh, extension, compression...). **Không sử dụng làm WebSocket server production.** Lợi ích là nó đủ để kiểm tra close handshake mà không cần dependency bên ngoài.

### Tệp `LocalWebSocketCloseTest.java`

```java
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
import java.util.Base64;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public class LocalWebSocketCloseTest {
    private static final String MAGIC =
            "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

    static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        while (true) {
            int ch = in.read();
            if (ch < 0) {
                throw new EOFException("HTTP handshake ended");
            }
            if (ch == '\n') {
                byte[] data = bytes.toByteArray();
                int len = data.length;
                if (len > 0 && data[len - 1] == '\r') {
                    len--;
                }
                return new String(data, 0, len,
                        StandardCharsets.US_ASCII);
            }
            if (bytes.size() >= 8192) {
                throw new IOException("Header line too long");
            }
            bytes.write(ch);
        }
    }

    static void handshake(InputStream in, OutputStream out)
            throws Exception {
        String start = readLine(in);
        if (!start.startsWith("GET ")) {
            throw new IOException("Not a WebSocket opening GET");
        }

        String key = null;
        while (true) {
            String line = readLine(in);
            if (line.isEmpty()) {
                break;
            }
            if (line.toLowerCase(Locale.ROOT)
                    .startsWith("sec-websocket-key:")) {
                key = line.substring(line.indexOf(':') + 1).trim();
            }
        }

        if (key == null) {
            throw new IOException("Missing Sec-WebSocket-Key");
        }

        byte[] digest = MessageDigest.getInstance("SHA-1").digest(
                (key + MAGIC).getBytes(StandardCharsets.US_ASCII));
        String accept = Base64.getEncoder().encodeToString(digest);

        String reply = "HTTP/1.1 101 Switching Protocols\r\n"
                + "Upgrade: websocket\r\n"
                + "Connection: Upgrade\r\n"
                + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";

        out.write(reply.getBytes(StandardCharsets.US_ASCII));
        out.flush();
    }

    static int readClientCloseCode(InputStream in) throws IOException {
        int first = in.read();
        int second = in.read();

        if (first != 0x88 || second < 0 || (second & 0x80) == 0) {
            throw new IOException("Expected masked final Close frame");
        }

        int length = second & 0x7F;
        if (length < 2 || length > 125) {
            throw new IOException("Invalid Close frame length");
        }

        byte[] mask = in.readNBytes(4);
        byte[] payload = in.readNBytes(length);
        if (mask.length != 4 || payload.length != length) {
            throw new EOFException("Truncated Close frame");
        }

        int hi = (payload[0] ^ mask[0]) & 0xFF;
        int lo = (payload[1] ^ mask[1]) & 0xFF;
        return (hi << 8) | lo;
    }

    static final class MiniServer implements AutoCloseable {
        final ServerSocket listener;
        final boolean replyWithClose;
        final CompletableFuture<Integer> received =
                new CompletableFuture<>();

        MiniServer(boolean replyWithClose) throws IOException {
            this.replyWithClose = replyWithClose;
            listener = new ServerSocket(0, 1,
                    InetAddress.getByName("127.0.0.1"));

            Thread serverThread = new Thread(
                    this::serve, "mini-websocket-server");
            serverThread.setDaemon(true);
            serverThread.start();
        }

        void serve() {
            try (Socket socket = listener.accept()) {
                socket.setSoTimeout(5000);
                InputStream in = socket.getInputStream();
                OutputStream out = socket.getOutputStream();
                handshake(in, out);

                int code = readClientCloseCode(in);
                received.complete(code);

                if (replyWithClose) {
                    // FIN + opcode Close, 2-byte code 1000.
                    out.write(new byte[] {
                            (byte) 0x88, 0x02, 0x03, (byte) 0xE8
                    });
                    out.flush();
                } else {
                    // Đợi client abort/đóng socket; không phản hồi Close.
                    while (in.read() != -1) {
                        // Không có thêm data frame trong fixture này.
                    }
                }
            } catch (Throwable error) {
                received.completeExceptionally(error);
            }
        }

        URI uri() {
            return URI.create("ws://127.0.0.1:"
                    + listener.getLocalPort() + "/test");
        }

        @Override
        public void close() throws IOException {
            listener.close();
        }
    }

    static final class CloseListener implements WebSocket.Listener {
        final CompletableFuture<Integer> peerClose =
                new CompletableFuture<>();

        @Override
        public void onOpen(WebSocket ws) {
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket ws, int code, String reason) {
            peerClose.complete(code);
            return null;
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            peerClose.completeExceptionally(error);
        }
    }

    static WebSocket connect(
            HttpClient client, MiniServer server, CloseListener observer) {
        return client.newWebSocketBuilder()
                .buildAsync(server.uri(), observer)
                .orTimeout(5, TimeUnit.SECONDS)
                .join();
    }

    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        try (MiniServer server = new MiniServer(true)) {
            CloseListener observer = new CloseListener();
            WebSocket ws = connect(client, server, observer);

            ws.sendClose(WebSocket.NORMAL_CLOSURE, "demo")
                    .orTimeout(5, TimeUnit.SECONDS).join();

            int peerCode = observer.peerClose
                    .orTimeout(5, TimeUnit.SECONDS).join();
            int sentCode = server.received
                    .orTimeout(5, TimeUnit.SECONDS).join();

            System.out.println("graceful peer code: " + peerCode);
            System.out.println("graceful sent code: " + sentCode);
            System.out.println("graceful both closed: "
                    + (ws.isInputClosed() && ws.isOutputClosed()));
        }

        try (MiniServer server = new MiniServer(false)) {
            CloseListener observer = new CloseListener();
            WebSocket ws = connect(client, server, observer);

            ws.sendClose(WebSocket.NORMAL_CLOSURE, "")
                    .orTimeout(5, TimeUnit.SECONDS).join();
            server.received.orTimeout(5, TimeUnit.SECONDS).join();

            System.out.println("output closed: "
                    + ws.isOutputClosed());
            System.out.println("input still open: "
                    + !ws.isInputClosed());

            ws.abort();
            ws.abort(); // Lần thứ hai không làm gì.
            System.out.println("abort both closed: "
                    + (ws.isInputClosed() && ws.isOutputClosed()));
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 LocalWebSocketCloseTest.java
java LocalWebSocketCloseTest
```

Stdout kỳ vọng khi loopback socket được phép mở và hai lượt thử thành công:

```text
graceful peer code: 1000
graceful sent code: 1000
graceful both closed: true
output closed: true
input still open: true
abort both closed: true
```

**Giải thích:**

1. Ở lượt đầu, `sendClose` gửi code 1000, fixture server đọc Close frame đã mask và gửi lại Close 1000. Listener nhận `onClose`, vì thế client có cả hai chiều đóng.
2. Ở lượt hai, server nhận Close nhưng **không gửi Close trả lời**; Java client đã đóng output nhưng còn input. `abort()` kết thúc cả hai chiều và lần gọi lặp là no-op.
3. `MiniServer` chỉ dành cho test; không có xác thực origin, xử lý dữ liệu tổng quát hoặc kiểm soát resource của server production.
4. Server dùng một thread daemon cho mỗi fixture; môi trường không cho kết nối loopback có thể khiến ví dụ lỗi, không phải bằng chứng `sendClose` sai.
5. Trong production, luôn dùng `wss://` khi có thể và xác minh TLS/certificate phù hợp. `ws://127.0.0.1` ở đây chỉ phục vụ test loopback.

## 10. Đóng có hạn chót: bắt buộc có lối thoát

Một ứng dụng dài hạn cần quy trình có deadline vì peer có thể chết, mất kết nối mạng hoặc không trả Close. Quy trình thường dùng:

1. **Ngừng tạo data messages mới** cho session đang đóng. Với nhiều producers, khóa trạng thái ứng dụng để tránh race.
2. **Đợi những message quan trọng đã gửi xong**, theo một thời hạn hợp lý. Tránh gọi `sendClose` trước khi gửi xong một chuỗi frame text/binary phân mảnh.
3. **Gọi `sendClose(WebSocket.NORMAL_CLOSURE, "")`** và theo dõi future gửi Close.
4. **Chờ `Listener.onClose`** hoặc tín hiệu `onError`, với hạn chót riêng/hạn chót chung.
5. Nếu quá thời hạn, operation lỗi hoặc không còn khả năng hoàn tất, **`abort()`** để dọn tài nguyên.
6. **Đóng promises/trạng thái của ứng dụng** để waiter không tiếp tục treo; ghi log tình trạng kết thúc và không hứa đã nhận Close nếu chỉ gửi Close.

### Lớp tái sử dụng: `GracefulCloseWithDeadline.java`

Đây là lớp tiện ích **biên dịch được** với Java 11, không có `main`. Nó giả định một `CompletionStage<?> peerClose` do listener quản lý: stage hoàn tất bình thường khi nhận `onClose` và hoàn tất exceptionally nếu `onError` xảy ra.

```java
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public final class GracefulCloseWithDeadline {
    private GracefulCloseWithDeadline() {
    }

    public static CompletableFuture<Void> close(
            WebSocket ws, CompletionStage<?> peerClose, Duration timeout) {
        Objects.requireNonNull(ws);
        Objects.requireNonNull(peerClose);
        Objects.requireNonNull(timeout);
        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }

        CompletableFuture<WebSocket> sent = ws.isOutputClosed()
                ? CompletableFuture.completedFuture(ws)
                : ws.sendClose(WebSocket.NORMAL_CLOSURE, "");

        CompletableFuture<Void> peer = peerClose
                .toCompletableFuture()
                .thenApply(ignored -> (Void) null);

        CompletableFuture<Void> finished = sent.thenCombine(
                peer, (socket, ignored) -> (Void) null);

        return finished
                .orTimeout(timeout.toMillis(), TimeUnit.MILLISECONDS)
                .whenComplete((ignored, failure) -> {
                    if (failure != null) {
                        ws.abort();
                    }
                });
    }
}
```

```bash
javac --release 11 -encoding UTF-8 GracefulCloseWithDeadline.java
```

Ví dụ tích hợp khi đã có `WebSocket ws`, `CloseListener listener` và import `Duration`:

```java
GracefulCloseWithDeadline.close(
        ws, listener.peerClose, Duration.ofSeconds(5)).join();
```

**Các điều cần hiểu khi áp dụng:**

- `thenCombine` đợi **hai điều kiện**: future gửi Close hoàn tất bình thường và stage nhận Close hoàn tất bình thường.
- `orTimeout` đặt thời hạn cho future kết hợp, **không tự đóng socket**; `whenComplete` gọi `abort()` khi thất bại.
- Nếu `onError` làm stage thất bại, hoặc `sendClose` thất bại, cũng dọn WebSocket bằng `abort`.
- `isOutputClosed` là snapshot; nếu output chuyển trạng thái ngay lúc gọi, send future có thể lỗi và nhánh cleanup sẽ xử lý.
- `timeout.toMillis()` có thể thành 0 với thời lượng nhỏ hơn 1 ms hoặc vượt miền biểu diễn ở giá trị quá lớn; trong ứng dụng thực, hãy ràng buộc thời hạn vào miền hợp lệ (ví dụ 1–60 giây).
- Đoạn này thể hiện **chính sách một lần đóng trên một session**. Nếu nhiều thread cùng gọi close, cần điều phối idempotency ở tầng ứng dụng, ví dụ lưu một future đóng duy nhất trên session.
- Với peer chủ động Close, listener có thể tự động đóng output trước khi bạn gọi tiện ích; cần xét state và không đợi một sendClose vô nghĩa.

## 11. onClose phản hồi custom code và nguy cơ CompletionStage không hoàn tất

Mặc định `WebSocket.Listener.onClose` trả `null`, báo rằng có thể đóng output ngay. Nếu ứng dụng muốn tự gửi một Close với mã/reason được phép, Javadoc cho phép gọi `sendClose` ngay **trong callback**:

```java
@Override
public CompletionStage<?> onClose(
        WebSocket ws, int code, String reason) {

    if (ws.isOutputClosed()) {
        return null;
    }
    return ws.sendClose(WebSocket.NORMAL_CLOSURE, "");
}
```

Đây là đoạn minh họa bên trong `WebSocket.Listener`. Nó giả định `CompletionStage` đã import. Future `sendClose` hoàn tất khi Close frame được gửi; trả nó như stage của callback giúp diễn đạt rằng listener xử lý hành động trả lời trước khi công việc kết thúc. Không ném lỗi vô kiểm soát từ listener.

**Cảnh báo:** Đừng trả về một `CompletableFuture` không bao giờ được hoàn tất từ `onClose` mà không có chủ đích và cơ chế dọn dẹp; theo Javadoc, điều đó có thể **ngăn chiều output đóng**. Ứng dụng phải quản lý completion hoặc tự gửi Close/abort theo hợp đồng.

**Peer đóng trước:** Khi nhận Close, input đã đóng. Nếu output chưa đóng, ứng dụng nên để cơ chế của listener hoặc `sendClose` phản hồi phù hợp; không gửi thêm message data rồi mới phản hồi Close. Khi output đã đóng trước đó, không gửi Close lần hai.

## 12. Trạng thái gửi và thứ tự message đang chờ

Một số điều dễ gây lỗi:

- `sendText(data, false)` biểu thị **chưa hoàn tất text message**. Nếu chuỗi message bị phân mảnh, cần kết thúc đúng bằng `sendText(..., true)` trước lúc đóng theo luồng nghiệp vụ phù hợp.
- `sendText`/`sendBinary`/`sendPing`/`sendPong` đều trả futures. Không gửi ồ ạt rồi giả định thứ tự xử lý nghiệp vụ khi nhiều producers đua nhau.
- `sendClose` đóng output theo hợp đồng. Các thao tác gửi data **sau khi output đóng** không thành công; xử lý future exceptional thay vì coi dữ liệu đã gửi.
- `abort` có thể làm những lệnh gửi đang chờ thất bại. Đừng bỏ qua lỗi futures hoặc coi chúng là đã được peer nhận.
- Một request close đang được gửi **không bảo đảm dữ liệu gửi trước đó đã được ứng dụng peer xử lý**. Nếu nghiệp vụ cần xác nhận nhận hàng/commit, phải có **ACK ở tầng ứng dụng trước khi đóng**.
- Listener callbacks trên **một WebSocket** được thực thi theo thứ tự không chồng lặp, nhưng callbacks từ **các WebSocket khác nhau** có thể chạy đồng thời. Trạng thái chia sẻ giữa các session phải được đồng bộ phù hợp.
- Đóng session WebSocket rồi **kết nối lại** cần xây một WebSocket mới; không có `reopen()` cho session đã đóng.

### Bảng chọn hành động theo tình huống

| Tình huống | Cách xử lý |
| --- | --- |
| Người dùng bấm Disconnect bình thường | Ngừng gửi mới → `sendClose(1000,"")` → đợi `onClose` có hạn chót |
| Server gửi Close trước | Nhận `onClose`; nếu cần phản hồi, dùng cơ chế callback/`sendClose` đúng hợp đồng |
| Client đã gửi Close, peer không phản hồi | Timeout → `abort()` và ghi nhận đóng không hoàn tất handshake |
| Lỗi I/O nghiêm trọng | Ghi nhận `onError`/future exceptional, dọn tài nguyên; `abort` khi cần |
| Nhiều luồng cùng yêu cầu đóng | Điều phối một future/trạng thái đóng duy nhất |
| App shutdown nhưng còn data chưa gửi | Quyết định drain hay bỏ có kiểm soát, sau đó đóng với deadline |
| Close code hoặc reason không hợp lệ | Sửa tham số, không tắt kiểm tra API |
| Có yêu cầu kết nối lại | Tạo WebSocket mới và state machine mới |

## 13. Kịch bản kiểm thử và những sai lầm thường gặp

### Các trường hợp nên kiểm tra

| Test case | Cách tạo | Kỳ vọng |
| --- | --- | --- |
| Graceful close hai chiều | Server gửi Close phản hồi | `onClose` được ghi nhận, hai cờ đóng là `true` |
| Peer im lặng sau Close | Server giữ socket mở | `isOutputClosed()==true`, input có thể vẫn mở; timeout/abort đóng cả hai |
| `abort()` lặp lại | Gọi hai lần | Không lỗi hoặc thay đổi sau lần đầu |
| Close status sai | Truyền mã ngoài phạm vi/thuộc tập cấm | Lỗi `IllegalArgumentException` theo API |
| Reason quá 123 byte UTF-8 | Chuỗi nhiều emoji | Lỗi tham số; không tính theo `String.length()` |
| Output đã đóng | Gọi gửi data/Close mới | Future có thể hoàn tất exceptionally với `IOException` |
| Peer Close trước | Server gửi Close bất ngờ | Input đóng và listener không tiếp tục nhận messages |
| `onError` | Cắt mạng/đóng kết nối sai quy trình | Error path giải phóng waiter; không báo nhầm graceful |
| Timeout khi chờ peer | Không có Close trả lời | Tác vụ không treo vô hạn, gọi abort theo chính sách |
| Multiple producers | Gửi trong lúc đang đóng | Không mất ACK nghiệp vụ do race; trạng thái được điều phối |

### Những sai lầm phổ biến

1. **Dùng `sendClose` và cho rằng cả hai chiều đã đóng.** Thực tế input có thể còn mở; cần listener hoặc timeout/abort.
2. **Gọi `abort` ngay sau `sendClose` mọi lúc.** Làm mất ý nghĩa graceful handshake; dùng abort như fallback.
3. **Chờ `sendClose(...).join()` không timeout.** Peer/network có thể treo; quản lý deadline và dọn tài nguyên.
4. **Dùng `String.length()` kiểm tra close reason.** Giới hạn tính bằng UTF-8 bytes.
5. **Gửi code 1006 vì nghĩ đó là “abnormal closure” hợp lệ để gửi.** Đây là mã dự trữ và Java 11 từ chối.
6. **Nhầm WebSocket code 1000 với HTTP 200.** Hai miền mã khác nhau.
7. **Không gọi `request(n)` trong listener.** Các receive callbacks, gồm `onClose`, có thể không được phân phối khi demand bằng 0.
8. **Tin rằng `onError` sẽ luôn xảy ra do chính mình gọi `abort`.** Đừng lấy một callback không được hứa làm cơ chế cleanup duy nhất.
9. **Trả một stage không bao giờ hoàn tất từ `onClose`.** Có thể trì hoãn đóng output vô thời hạn.
10. **Không quản lý lệnh gửi đang chờ.** `abort()` có thể làm futures gửi lỗi; phải có chiến lược quan sát/hoàn tất chúng.
11. **Giả định kiểm tra `isOutputClosed` trước gửi loại bỏ mọi race.** Đây chỉ là snapshot, xử lý lỗi asynchronous vẫn cần.
12. **Dùng lại WebSocket đã đóng.** Hãy tạo kết nối mới nếu cần reconnect.

## 14. Câu hỏi tự luyện

**A.** Future của `sendClose(1000,"")` hoàn tất bình thường. Client có thể kết luận đã nhận Close từ peer chưa?

**B.** Sau `sendClose`, nếu `isOutputClosed()==true` nhưng `isInputClosed()==false` thì điều gì đang xảy ra?

**C.** Gọi `abort()` có giống trao đổi Close bình thường không?

**D.** `sendClose(1006,"")` có phải cách hợp lệ để thông báo “abnormal close” không?

**E.** Chuỗi reason gồm 31 emoji `😀` có hợp lệ chỉ vì `String.length()==62` không?

**F.** `onClose` có nhất thiết được gọi sau khi chương trình tự gọi `abort` không?

**G.** Để nhận Close message qua `Listener`, có cần duy trì receive demand bằng `request(n)` không?

**H.** Nếu `onClose` trả stage không bao giờ hoàn tất trong khi output chưa đóng, điều gì có thể xảy ra?

**I.** Nếu chưa nhận được ACK nghiệp vụ cho một lệnh gửi, `sendClose` thành công có chứng minh server đã xử lý lệnh không?

**Đáp án:** A. Chưa, chỉ biết Close phía client đã gửi. B. Đã đóng chiều gửi nhưng vẫn chờ chiều nhận kết thúc, thường là Close từ peer. C. Không, abort đóng đột ngột cả hai chiều. D. Không, code 1006 bị cấm theo Java 11. E. Không, 31 emoji UTF-8 dùng 124 byte, vượt 123. F. Không; callback onClose dành cho Close nhận được. G. Có, request counter điều khiển receive callbacks. H. Có thể trì hoãn đóng output vô thời hạn. I. Không, ACK nghiệp vụ là cơ chế riêng.

## 15. Checklist triển khai

- **State model:** Có cờ/trạng thái đóng ở tầng ứng dụng và một future đóng để các callers chia sẻ, tránh gửi mới khi bắt đầu shutdown.
- **Close reason:** Mã theo hợp đồng; thường là `WebSocket.NORMAL_CLOSURE` và chuỗi rỗng; giới hạn 123 UTF-8 bytes.
- **Tương lai thao tác:** Theo dõi futures của data sends, `sendClose` và promise cho peer `onClose` như **những sự kiện khác nhau**.
- **Inbound demand:** Listener gọi `request(n)` hợp lý; không làm mất `onClose` do không xin receive callbacks.
- **Deadline:** Chờ peer có hạn chót; `orTimeout` không tự abort WebSocket.
- **Error path:** Hoàn tất các futures/promise lỗi và dọn tài nguyên; không nuốt `onError`, không giả lập Close thành công.
- **Fallback:** Gọi `abort()` sau deadline hoặc lỗi nghiêm trọng, không dùng để thay graceful close thường xuyên.
- **Security:** Với hệ thống thật, ưu tiên `wss://`, xác thực TLS đúng và hạn chế nơi kết nối; không log close reason chứa thông tin mật.
- **Tests:** Có ít nhất test graceful, peer im lặng, abort, close code/reason sai, ranh giới nhiều luồng và application-level ACK.
- **Compatibility:** Dùng `java.net.http.WebSocket` chuẩn từ Java 11, không sử dụng những API incubator cũ.

## Tài liệu chính thức

- [Java SE 11 — WebSocket: sendClose, abort, input/output states, request](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html).
- [Java SE 11 — WebSocket.Listener: onClose, onError, CompletionStage](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html).
- [Java SE 11 — WebSocket.Builder: buildAsync, connectTimeout](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Builder.html).
- [Java SE 25 — WebSocket API tiếp tục được duy trì](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/WebSocket.html).
- [RFC 6455 — The WebSocket Protocol: Closing Handshake và status codes](https://www.rfc-editor.org/rfc/rfc6455).
