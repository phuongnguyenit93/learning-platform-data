# Gửi văn bản, nhị phân, ping, pong và nhận kết quả hoàn tất gửi

## 1. Bối cảnh của WebSocket client trong Java

`java.net.http.WebSocket` là API client có sẵn từ Java 11 (dùng tốt trong Java 17+). Sau khi nâng cấp kết nối qua HTTP Upgrade, client có thể gửi **text messages**, **binary messages** và **control messages** như **Ping**, **Pong**, **Close**. Một WebSocket duy trì hai hướng **input** và **output** độc lập. Dữ liệu từ client đi qua các phương thức `send...`; dữ liệu từ peer trở về được chuyển cho `WebSocket.Listener`.

Đề bài tập trung vào bốn lệnh:

| Lệnh gửi | Dữ liệu | Kết quả API | Nhận lại từ peer ở đâu? |
| --- | --- | --- | --- |
| `sendText(CharSequence, boolean last)` | Văn bản, có thể là fragment | `CompletableFuture<WebSocket>` | `Listener.onText` nếu peer gửi text |
| `sendBinary(ByteBuffer, boolean last)` | Byte nhị phân | `CompletableFuture<WebSocket>` | `Listener.onBinary` nếu peer gửi binary |
| `sendPing(ByteBuffer)` | Ping payload tối đa 125 byte | `CompletableFuture<WebSocket>` | `Listener.onPong` khi peer trả Pong |
| `sendPong(ByteBuffer)` | Pong payload tối đa 125 byte | `CompletableFuture<WebSocket>` | Không tự có ACK; phía peer có thể nhận Pong |
| `sendClose(int,String)` | WebSocket Close control | `CompletableFuture<WebSocket>` | `Listener.onClose` khi nhận Close từ peer |

**Một future hoàn tất khi thao tác gửi đã xong, không có nghĩa peer đã xử lý nghiệp vụ.** Ví dụ `ws.sendPing(payload).join()` cho biết Ping được gửi từ phía Java client; chỉ `Listener.onPong` mới cho biết phía client **đã nhận** một Pong. Với text/binary, ứng dụng có thể cần một **ACK message riêng** để xác nhận server đã xử lý/commit.

~~~text
Ứng dụng                          java.net.http.WebSocket                 Peer
    |                                      |                                |
    |-- sendText("HELLO", true) ---------->| ------ outbound text -------> |
    |<--- CompletableFuture done ---------|       thao tác gửi đã xong      |
    |                                      |                                |
    |                          <--------------- text/ACK từ peer ---------|
    |<--- Listener.onText ----------------|       nhận message khác chiều   |
    |                                      |                                |
    |-- sendPing("id") ------------------>| -------- Ping --------------> |
    |<--- send future done ---------------|                               |
    |                          <--------------- Pong("id") ---------------|
    |<--- Listener.onPong ----------------|       phản hồi đến từ peer     |
~~~

## 2. Khởi tạo WebSocket client và phân biệt handshake future

WebSocket client có sẵn trong JDK:

~~~java
WebSocket.Listener listener = new WebSocket.Listener() {
    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }
};

WebSocket ws = HttpClient.newHttpClient()
        .newWebSocketBuilder()
        .buildAsync(URI.create("wss://example.org/ws"), listener)
        .join();
~~~

*Đây là **đoạn minh họa** (cần imports, endpoint thực, xử lý lỗi và timeout), không phải chương trình độc lập. Ví dụ hoàn chỉnh ở phần 9 chỉ dùng loopback.*

`buildAsync(...)` trả một `CompletableFuture<WebSocket>` cho **giai đoạn HTTP Upgrade/khởi tạo kết nối**. Nó khác với future do `sendText`/`sendBinary`/`sendPing`/`sendPong` trả về **sau khi kết nối đã có**. Không gửi ứng dụng nếu handshake chưa thành công. HTTP endpoint bình thường không tự trở thành WebSocket server chỉ vì client gọi `buildAsync`.

Chọn `wss://` trong hệ thống thực để bảo vệ transport bằng TLS, xác thực server/certificate theo cấu hình chuẩn. `ws://127.0.0.1` trong bài chỉ dành cho kiểm thử cùng máy, không có TLS.

## 3. sendText và ý nghĩa chính xác của last

Gửi một text message hoàn chỉnh:

~~~java
CompletableFuture<WebSocket> sent = ws.sendText("Xin chào", true);
WebSocket sameSocket = sent.join();
~~~

*Đoạn minh họa, có `ws` và imports bên ngoài.*

`last=true` có nghĩa **phần này kết thúc message**, không phải lệnh đồng bộ. Nếu chưa kết thúc message, có thể phân mảnh:

~~~java
CompletableFuture<WebSocket> sent =
        ws.sendText("Xin ", false)
          .thenCompose(socket -> socket.sendText("chào", true));
sent.join();
~~~

Một `sendText(..., false)` không phải message hoàn chỉnh. Không chuyển sang `sendBinary` khi text message trước vẫn chưa kết thúc: Javadoc cho biết future gửi text/binary có thể hoàn tất exceptionally với `IllegalStateException` nếu có thao tác gửi text/binary đang pending hoặc message khác loại chưa kết thúc hợp lệ.

`CharSequence` được truyền vào `sendText` **không được chỉnh sửa trước khi future của lệnh gửi hoàn tất**. Vì vậy sử dụng `String` bất biến thường đơn giản hơn việc truyền `StringBuilder` đang bị thread khác sửa. Chuỗi không hợp lệ UTF-16 có thể khiến operation thất bại khi mã hóa.

**Không giả định một `sendText` dẫn đến đúng một `Listener.onText` ở peer.** WebSocket listener có thể nhận nhiều đoạn với tham số `last=false` rồi `last=true`; phải tích lũy đủ message trước khi parse nội dung nghiệp vụ.

## 4. sendBinary và vòng đời ByteBuffer

Gửi ba byte nhị phân:

~~~java
ByteBuffer bytes = ByteBuffer.wrap(new byte[] {1, 2, 3});
CompletableFuture<WebSocket> sent = ws.sendBinary(bytes, true);
sent.join();
System.out.println(bytes.hasRemaining()); // false nếu hoàn tất bình thường
~~~

*Đoạn minh họa với imports và `ws` có sẵn.*

Phần dữ liệu được gửi là các byte **từ `ByteBuffer.position()` tới `limit()`**, tương đương `remaining()` byte, không phải toàn bộ `capacity()`. Nếu buffer có `capacity=8, position=2, limit=5` thì chỉ gửi 3 byte.

**Quy tắc ownership:** sau `sendBinary(buffer, ...)` **không được truy cập hoặc chỉnh sửa buffer trước khi future hoàn tất**, vì Java WebSocket có thể còn đang dùng nó. Nếu future hoàn tất **bình thường**, buffer sẽ không còn byte `remaining()`. Không gọi `clear()`/`flip()` hoặc tái dùng buffer quá sớm. Khi future exceptional, không mặc định bao nhiêu byte đã được gửi; cần kiểm tra/đóng kết nối theo chính sách trước khi phát lại.

Với nhị phân chia nhiều phần, dùng `last=false` cho những phần đầu và `last=true` cho phần cuối, đồng thời bảo đảm mỗi send được xếp thứ tự. Nếu phải gửi file hoặc dữ liệu lớn, cần giới hạn số byte đang pending; một future hoàn tất gửi không thay thế giới hạn hàng đợi/outbound backpressure.

## 5. sendPing và sendPong: control messages khác dữ liệu ứng dụng

Cả `sendPing(ByteBuffer)` và `sendPong(ByteBuffer)` dùng **payload tối đa 125 byte**, tính theo `remaining()` từ position đến limit. Payload có thể rỗng. Không được tự thêm opcode/mask/WebSocket frame header vào buffer gửi; JDK làm việc đó.

Ví dụ gửi Ping:

~~~java
CompletableFuture<WebSocket> pingSent = ws.sendPing(
        ByteBuffer.wrap("hi".getBytes(StandardCharsets.US_ASCII)));
pingSent.join(); // Ping send hoàn tất; không bảo đảm Pong đã nhận.
~~~

Ví dụ gửi Pong tường minh:

~~~java
CompletableFuture<WebSocket> pongSent = ws.sendPong(
        ByteBuffer.wrap("ok".getBytes(StandardCharsets.US_ASCII)));
pongSent.join();
~~~

*Hai đoạn minh họa; cần `ws`, imports, connection đang mở.*

### Ping và Pong có quan hệ ra sao?

- Khi peer nhận Ping, theo WebSocket protocol nó thường gửi Pong tương ứng. Java `WebSocket` implementation **tự gửi reciprocal Pong khi nhận Ping**; vì thế **hiếm khi cần** tự `sendPong` bên trong `onPing`.
- `sendPong` tường minh vẫn là API hợp lệ, ví dụ để thử control frame hoặc gửi unsolicited Pong. Không nên dùng Pong làm “ACK đã lưu đơn hàng”.
- Future của `sendPing` hoàn tất là **tín hiệu outbound**; `Listener.onPong` là **tín hiệu inbound**. Nếu cần heartbeat, phải so payload hoặc ID, quản lý timeout cho Pong, không chỉ chờ `sendPing().get()`.
- Ping/Pong không có tham số `last` và **không được phân mảnh**; vượt 125 byte có thể hoàn tất exceptionally với `IllegalArgumentException`.
- Nếu có một operation Ping/Pong đang pending, lệnh Ping/Pong mới có thể thất bại với `IllegalStateException`. Nên theo dõi future và tuần tự hóa control sends khi cần.
- Không chạm hoặc sửa `ByteBuffer` control đang được send cho tới khi future kết thúc. Không giữ dữ liệu nhạy cảm trong Ping/Pong payload.

## 6. Future hoàn tất gửi: ba trạng thái khác nhau

`sendText`, `sendBinary`, `sendPing` và `sendPong` đều trả `CompletableFuture<WebSocket>`:

1. **Normal completion:** thao tác gửi đã thành công; `future.get()`/`future.join()` trả chính WebSocket. Điều này **không xác nhận peer đã đọc, parse hoặc xử lý** dữ liệu.
2. **Exceptional completion:** gửi thất bại, ví dụ output đóng, I/O lỗi, có send cùng loại pending, trộn message types khi message trước chưa kết thúc hoặc control payload quá dài.
3. **Pending:** operation đã khởi phát nhưng chưa xong. Không thay đổi buffer/CharSequence đang được gửi; xử lý timeout và cancellation có kiểm soát.

~~~java
CompletableFuture<WebSocket> pending = ws.sendText("hello", true);
pending.whenComplete((socket, error) -> {
    if (error == null) {
        System.out.println("outbound send completed");
    } else {
        System.err.println("outbound send failed: " + error);
    }
});
~~~

*Đoạn minh họa; callback `whenComplete` chỉ quan sát kết quả gửi.*

`join()` có thể chặn thread gọi và thường ném `CompletionException` khi operation exceptional. `get(timeout, unit)` có thể chặn tối đa một khoảng và ném `TimeoutException`, `ExecutionException` hoặc `InterruptedException`. **Timeout khi chờ future không chứng minh operation đã hủy hoặc peer chưa nhận byte.** Khi lỗi, phải kiểm tra cause/connection state, không retry lệnh nghiệp vụ không idempotent một cách mù quáng.

Để tránh nhiều text/binary send pending, dùng **chuỗi nối tiếp**:

~~~java
CompletableFuture<WebSocket> sent =
        ws.sendText("start", true)
          .thenCompose(socket -> socket.sendBinary(
                  ByteBuffer.wrap(new byte[] {1, 2}), true))
          .thenCompose(socket -> socket.sendPing(
                  ByteBuffer.wrap(new byte[] {7})))
          .thenCompose(socket -> socket.sendPong(
                  ByteBuffer.wrap(new byte[] {8})));
sent.join();
~~~

*Đoạn minh họa về sequencing, không phải một chương trình độc lập.*

**Đừng khởi phát đồng thời tất cả `sendText` và `sendBinary` bằng `allOf` khi chưa có cơ chế serialize:** lời gọi sau có thể thấy một text/binary send đang pending và hoàn tất exceptionally với `IllegalStateException`. Cần outbound queue per-connection, `thenCompose`, giới hạn số byte pending và xử lý lỗi từng phần.

## 7. Listener nhận về: request(n), onText, onBinary, onPong

`WebSocket.Listener` xử lý **chiều inbound**. Các phương thức `onText(ws, chars, last)`, `onBinary(ws, bytes, last)`, `onPing(ws, payload)`, `onPong(ws, payload)` và `onClose(...)` không phải kết quả trả về của phương thức send. Đây là những callback cho thông điệp **từ peer truyền về**.

`WebSocket.request(long n)` cấp **n lượt callback nhận**, **không phải n byte hay n message hoàn chỉnh**. Vì text/binary có thể phân mảnh trên nhiều callback, ứng dụng phải tích lũy đến `last=true` và gọi `request(1)` theo chính sách để nhận tiếp. Nếu demand bằng 0, WebSocket không gọi các receive methods tiếp dù network có dữ liệu.

Ví dụ rút gọn:

~~~java
class ExampleListener implements WebSocket.Listener {
    private final StringBuilder pending = new StringBuilder();

    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket ws, CharSequence part, boolean last) {
        pending.append(part);
        if (last) {
            System.out.println("whole message: " + pending);
            pending.setLength(0);
        }
        ws.request(1);
        return null;
    }

    @Override
    public CompletionStage<?> onPong(
            WebSocket ws, ByteBuffer data) {
        byte[] copy = new byte[data.remaining()];
        data.get(copy);
        ws.request(1);
        return null;
    }
}
~~~

*Đoạn minh họa cần imports; class độc lập đầy đủ nằm ở phần 9.*

Theo JDK, các callback nhận trả `CompletionStage<?>` cho runtime biết **khi nào có thể thu hồi vùng dữ liệu đã giao vào callback**. Trả `null` là hoàn tất ngay. `CompletionStage` của callback nhận **khác** `CompletableFuture<WebSocket>` của thao tác gửi; nó **không tự tăng counter của `request(n)`**. Nếu xử lý payload ngoài callback, hãy copy dữ liệu hoặc giữ stage chưa hoàn tất cho đến khi dùng xong.

`onError` thông báo lỗi listener/receive và có thể xuất hiện không cùng lúc với `onClose`. Sau sự kiện `onError` hoặc `onClose`, không giả định còn các receive callbacks kế tiếp. Trong listener hãy giữ logic ngắn, thread-safe, tránh block lâu.

## 8. Kiến trúc ví dụ: server WebSocket loopback để thử cả bốn loại

JDK cung cấp `java.net.http.WebSocket` **client**, không cung cấp một WebSocket server production đầy đủ theo đúng cách sử dụng như `HttpServer` cho HTTP thường. Để ví dụ **tự chạy không cần Internet/thư viện thứ ba**, chương trình dưới tạo **server test rất giới hạn** trên `127.0.0.1`:

- Server xử lý phần HTTP Upgrade/`Sec-WebSocket-Accept` cần thiết bằng SHA-1 + Base64 như RFC 6455 yêu cầu. SHA-1 ở đây là **cơ chế handshake RFC 6455**, không phải lựa chọn để hash mật khẩu.
- Server đọc WebSocket client frames **có mask** (quy tắc RFC 6455), giải mask, chỉ chấp nhận payload ngắn tối đa 125 byte và **FIN=1**.
- Khi nhận opcode 1 (text) hoặc 2 (binary), server **echo** một frame cùng loại; khi nhận opcode 9 (Ping), server trả opcode 10 (Pong) với đúng payload.
- Khi nhận Pong opcode 10 do client gửi tường minh, server xác minh payload `"ok"`. Khi nhận Close opcode 8, server trả Close.
- Client dùng WebSocket API chuẩn của JDK, lần lượt gửi bốn loại; listener đợi các echo/Pong rồi đóng có thứ tự.

**Giới hạn cực kỳ quan trọng:** fixture server **không hỗ trợ** nhiều client, frame dài, extended length, fragmented messages, extensions, TLS, subprotocols, trường hợp protocol sai phức tạp hoặc bảo mật production. Không triển khai thực tế từ server test này. Bài học dùng nó chỉ để quan sát **API gửi của client** với wire-level WebSocket thật.

## 9. Mã Java 17+ chạy được: text, binary, Ping, Pong và send completion

Tạo file `WebSocketSendKindsDemo.java` chứa toàn bộ chương trình:

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
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Base64;
import java.util.Locale;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class WebSocketSendKindsDemo {
    private static final String GUID =
            "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

    record Frame(int opcode, byte[] data) {}

    static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream line = new ByteArrayOutputStream();
        for (int i = 0; i < 8192; i++) {
            int b = in.read();
            if (b < 0) throw new EOFException("HTTP header incomplete");
            if (b == '\n') {
                byte[] bytes = line.toByteArray();
                int len = bytes.length;
                if (len > 0 && bytes[len - 1] == '\r') len--;
                return new String(bytes, 0, len, StandardCharsets.US_ASCII);
            }
            line.write(b);
        }
        throw new IOException("HTTP header line too long");
    }

    static void handshake(InputStream in, OutputStream out) throws Exception {
        String first = readLine(in);
        if (!first.startsWith("GET /echo HTTP/1.1"))
            throw new IOException("unexpected upgrade path");
        String key = null;
        for (int lineCount = 0; lineCount < 80; lineCount++) {
            String line = readLine(in);
            if (line.isEmpty()) break;
            int colon = line.indexOf(':');
            if (colon > 0
                    && line.substring(0, colon).trim().toLowerCase(Locale.ROOT)
                        .equals("sec-websocket-key")) {
                key = line.substring(colon + 1).trim();
            }
        }
        if (key == null) throw new IOException("missing Sec-WebSocket-Key");
        byte[] sha1 = MessageDigest.getInstance("SHA-1").digest(
                (key + GUID).getBytes(StandardCharsets.US_ASCII));
        String accept = Base64.getEncoder().encodeToString(sha1);
        String response = "HTTP/1.1 101 Switching Protocols\r\n"
                + "Upgrade: websocket\r\n"
                + "Connection: Upgrade\r\n"
                + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
        out.write(response.getBytes(StandardCharsets.US_ASCII));
        out.flush();
    }

    static Frame readClientFrame(InputStream in) throws IOException {
        int first = in.read();
        if (first < 0) throw new EOFException("missing WebSocket frame");
        int second = in.read();
        if (second < 0) throw new EOFException("missing frame length");
        if ((first & 0x80) == 0) throw new IOException("demo requires FIN");
        if ((second & 0x80) == 0) throw new IOException("client must mask frames");
        int length = second & 0x7f;
        if (length > 125) throw new IOException("demo only supports <=125 bytes");
        byte[] mask = in.readNBytes(4);
        if (mask.length != 4) throw new EOFException("missing frame mask");
        byte[] payload = in.readNBytes(length);
        if (payload.length != length)
            throw new EOFException("truncated WebSocket payload");
        for (int i = 0; i < payload.length; i++) {
            payload[i] ^= mask[i % 4];
        }
        return new Frame(first & 0x0f, payload);
    }

    static void writeServerFrame(OutputStream out, int opcode, byte[] payload)
            throws IOException {
        if (payload.length > 125)
            throw new IOException("demo frame too large");
        out.write(0x80 | opcode);
        out.write(payload.length); // Server frames are unmasked.
        out.write(payload);
        out.flush();
    }

    static boolean serveOne(ServerSocket listener) throws Exception {
        boolean explicitPongReceived = false;
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5_000);
            InputStream in = peer.getInputStream();
            OutputStream out = peer.getOutputStream();
            handshake(in, out);
            while (true) {
                Frame frame = readClientFrame(in);
                switch (frame.opcode()) {
                    case 1, 2 -> writeServerFrame(
                            out, frame.opcode(), frame.data()); // echo
                    case 9 -> writeServerFrame(out, 10, frame.data()); // ping -> pong
                    case 10 -> explicitPongReceived =
                            Arrays.equals(frame.data(),
                                    "ok".getBytes(StandardCharsets.US_ASCII));
                    case 8 -> {
                        writeServerFrame(out, 8, frame.data());
                        return explicitPongReceived;
                    }
                    default -> throw new IOException("unexpected opcode");
                }
            }
        }
    }

    static final class Events implements WebSocket.Listener {
        private final CountDownLatch messages = new CountDownLatch(3);
        private final CountDownLatch closed = new CountDownLatch(1);
        private final StringBuilder text = new StringBuilder();
        private final ByteArrayOutputStream binary = new ByteArrayOutputStream();
        private final AtomicReference<Throwable> failure = new AtomicReference<>();
        private volatile String pong = "";

        @Override
        public void onOpen(WebSocket ws) {
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket ws, CharSequence data, boolean last) {
            text.append(data);
            if (last) messages.countDown();
            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onBinary(
                WebSocket ws, ByteBuffer data, boolean last) {
            byte[] chunk = new byte[data.remaining()];
            data.get(chunk);
            binary.write(chunk, 0, chunk.length);
            if (last) messages.countDown();
            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onPong(WebSocket ws, ByteBuffer data) {
            byte[] bytes = new byte[data.remaining()];
            data.get(bytes);
            pong = new String(bytes, StandardCharsets.US_ASCII);
            messages.countDown();
            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket ws, int statusCode, String reason) {
            closed.countDown();
            return null;
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            failure.compareAndSet(null, error);
            while (messages.getCount() > 0) messages.countDown();
            closed.countDown();
        }

        void check() throws Exception {
            if (failure.get() != null)
                throw new IOException("WebSocket listener failed", failure.get());
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 8, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(5_000);
            ExecutorService serverThread = Executors.newSingleThreadExecutor();
            Future<Boolean> serverResult =
                    serverThread.submit(() -> serveOne(listener));
            try {
                Events events = new Events();
                URI uri = URI.create("ws://127.0.0.1:"
                        + listener.getLocalPort() + "/echo");
                WebSocket ws = HttpClient.newHttpClient().newWebSocketBuilder()
                        .buildAsync(uri, events).get(5, TimeUnit.SECONDS);
                try {
                    boolean textDone = ws.sendText("Hello WS", true)
                            .get(5, TimeUnit.SECONDS) == ws;
                    ByteBuffer data = ByteBuffer.wrap(new byte[] {1, 2, 3});
                    boolean binaryDone = ws.sendBinary(data, true)
                            .get(5, TimeUnit.SECONDS) == ws;
                    boolean pingDone = ws.sendPing(ByteBuffer.wrap(
                            "hi".getBytes(StandardCharsets.US_ASCII)))
                            .get(5, TimeUnit.SECONDS) == ws;
                    boolean pongDone = ws.sendPong(ByteBuffer.wrap(
                            "ok".getBytes(StandardCharsets.US_ASCII)))
                            .get(5, TimeUnit.SECONDS) == ws;

                    if (!events.messages.await(5, TimeUnit.SECONDS))
                        throw new IOException("response events timed out");
                    events.check();

                    boolean closeDone = ws.sendClose(
                            WebSocket.NORMAL_CLOSURE, "done")
                            .get(5, TimeUnit.SECONDS) == ws;
                    if (!events.closed.await(5, TimeUnit.SECONDS))
                        throw new IOException("close callback timed out");
                    events.check();
                    boolean serverSawPong =
                            serverResult.get(5, TimeUnit.SECONDS);

                    System.out.println("sendText completed: " + textDone);
                    System.out.println("sendBinary completed: " + binaryDone);
                    System.out.println("sendPing completed: " + pingDone);
                    System.out.println("sendPong completed: " + pongDone);
                    System.out.println("client text: " + events.text);
                    System.out.println("client binary bytes: "
                            + Arrays.toString(events.binary.toByteArray()));
                    System.out.println("client pong payload: " + events.pong);
                    System.out.println("server saw explicit pong: "
                            + serverSawPong);
                    System.out.println("sendClose completed: " + closeDone);
                } finally {
                    ws.abort();
                }
            } finally {
                serverThread.shutdownNow();
            }
        }
    }
}
~~~

### Lệnh biên dịch, chạy

Trong thư mục chứa file:

~~~bash
javac WebSocketSendKindsDemo.java
java WebSocketSendKindsDemo
~~~

Khi loopback hoạt động và JDK 17+ hỗ trợ WebSocket client, stdout:

~~~text
sendText completed: true
sendBinary completed: true
sendPing completed: true
sendPong completed: true
client text: Hello WS
client binary bytes: [1, 2, 3]
client pong payload: hi
server saw explicit pong: true
sendClose completed: true
~~~

Chương trình có `ServerSocket` test và client trong **cùng JVM**, dùng `ExecutorService` cho server để handshake/đọc/ghi diễn ra đồng thời. Port `0` để hệ điều hành cấp cổng trống. Các lệnh `get(5, TimeUnit.SECONDS)` và latch có timeout phục vụ **test deterministic**, không phải API yêu cầu tất cả chương trình WebSocket phải chặn sau mỗi send.

## 10. Phân tích từng dòng kết quả: gửi xong và nhận về khác nhau

| Output | Tín hiệu được kiểm tra | Ý nghĩa chính xác |
| --- | --- | --- |
| `sendText completed: true` | `ws.sendText(...).get(...) == ws` | Future text send hoàn tất bình thường |
| `sendBinary completed: true` | `ws.sendBinary(...).get(...) == ws` | Binary send đã hoàn tất bình thường |
| `sendPing completed: true` | `ws.sendPing(...).get(...) == ws` | Ping **đã gửi**; chưa phải đã nhận Pong |
| `sendPong completed: true` | `ws.sendPong(...).get(...) == ws` | Pong tường minh **đã gửi** |
| `client text: Hello WS` | `Listener.onText` | Client nhận text **echo từ server** |
| `client binary bytes: [1, 2, 3]` | `Listener.onBinary` | Client nhận binary **echo từ server** |
| `client pong payload: hi` | `Listener.onPong` | Client thực sự nhận Pong có payload `hi` |
| `server saw explicit pong: true` | Future kết quả từ server test | Server test đã thực sự đọc Pong tường minh `ok` |
| `sendClose completed: true` | Future `sendClose` | Close **đã gửi**, demo còn đợi `Listener.onClose` riêng |

Trong `Events`, `CountDownLatch messages` bắt đầu với giá trị 3. Callback text/binary chỉ `countDown()` khi `last==true`, còn Pong đếm sau khi copy payload. Điều này giúp không tính nhầm từng fragment như một message hoàn chỉnh.

Tại sao demo chờ hai nguồn tín hiệu khác nhau? `sendPing(...).get(...)` kiểm tra **gửi Ping**, còn `events.messages.await(...)` kiểm tra **nhận Pong và hai echo**. Server future riêng cho biết **Pong do client tự gửi đã đến server**. Một ứng dụng thật cũng cần tách ba tầng: send completed, peer response received, business request committed.

## 11. Lỗi của future gửi và cách chẩn đoán

| Trường hợp | Dấu hiệu/API | Hướng xử lý |
| --- | --- | --- |
| Gửi text/binary khi đã có lệnh gửi loại này pending | Future exceptional với `IllegalStateException` | Serialize send qua queue/`thenCompose` |
| Text message trước có `last=false`, rồi chuyển sang binary | Future có thể exceptional với `IllegalStateException` | Kết thúc đúng message text trước |
| Có Ping/Pong send đang pending, khởi phát control send khác | Future có thể exceptional với `IllegalStateException` | Theo dõi/control send completion |
| Ping hoặc Pong payload vượt 125 byte | `IllegalArgumentException` ở kết quả send | Kiểm tra `ByteBuffer.remaining()` |
| Output đã đóng, I/O lỗi, connection hỏng | `IOException`/future exceptional | Kiểm tra connection và cause, cleanup |
| `get(timeout)` quá hạn | `TimeoutException` ở caller | Không mặc định send đã dừng hoặc peer không nhận |
| `join()` của future lỗi | `CompletionException` | Xem cause; không nuốt lỗi |
| `sendPing` hoàn tất nhưng không có `onPong` | Chưa chắc peer đã đáp; listener có thể thiếu demand | Kiểm tra `request(n)`, deadline, errors |
| `sendClose` hoàn tất nhưng chưa có `onClose` | Hai sự kiện khác nhau | Chờ peer Close khi cần, có deadline/cleanup |
| `ws.isOutputClosed()==true` | Output WebSocket đã đóng | Không gửi dữ liệu mới |

Đừng chỉ `try/catch` quanh lời gọi `sendText` rồi cho rằng đã kiểm tra đủ lỗi: operation có thể **trả future**, sau đó **mới hoàn tất exceptionally**. Dùng `whenComplete` hoặc đọc `get/join` để quan sát kết quả thật.

## 12. Text/binary fragmentation và bài toán ordering

Với một text message có hai phần:

~~~java
ws.sendText("Hello, ", false)
  .thenCompose(socket -> socket.sendText("world!", true))
  .join();
~~~

Với binary message hai phần:

~~~java
ws.sendBinary(ByteBuffer.wrap(new byte[] {1, 2}), false)
  .thenCompose(socket -> socket.sendBinary(
          ByteBuffer.wrap(new byte[] {3, 4}), true))
  .join();
~~~

Chỉ khi phần cuối đặt `last=true`, message mới được đánh dấu hoàn chỉnh. `last=false` không tự tạo một message đã kết thúc. Để nhận, listener phải tích lũy các callback tới `last=true` và xử lý như **một** message. Không chuyển message type giữa các phần khi chưa kết thúc.

**Không thử hai ví dụ fragmentation này trực tiếp với server fixture hạn chế ở phần 9**, vì server test cố ý chỉ chấp nhận FIN frame và sẽ từ chối fragmented frames. Hãy dùng WebSocket server hoàn chỉnh hoặc mở rộng fixture đúng RFC 6455 trước khi chạy.

Control Ping/Pong là loại message khác, không có `last`. JDK tự phản hồi Pong khi nhận Ping, nên tránh gửi thêm Pong trùng chỉ vì callback `onPing`. Control frames có thể xuất hiện trong giao tiếp khi application message đang được gửi nhiều phần; vẫn cần xử lý heartbeat và ordering đúng.

## 13. Đóng kết nối: sendClose không phải onClose

Sau khi gửi các message ứng dụng cần thiết, có thể gọi:

~~~java
CompletableFuture<WebSocket> closeSent =
        ws.sendClose(WebSocket.NORMAL_CLOSURE, "done");
closeSent.join();
~~~

*Đoạn minh họa, không tự tạo signal nhận Close từ peer.*

`WebSocket.NORMAL_CLOSURE` là code **1000**, biểu thị kết thúc bình thường. Future ở đây kiểm tra **thao tác gửi Close**. Để biết đã **nhận Close từ peer**, quan sát `Listener.onClose(WebSocket, int, String)`. Một WebSocket có thể đóng output trước khi input đóng; API `isOutputClosed()`/`isInputClosed()` giúp quan sát trạng thái, nhưng phải xử lý race và lỗi.

`ws.abort()` là đóng **đột ngột**, thường dùng cho cleanup khi lỗi hoặc hết deadline, không thay cho `sendClose` trong quy trình orderly shutdown. Một client sau Close/abort không được tái sử dụng để gửi tiếp; muốn reconnect phải tạo WebSocket mới và quyết định rõ request nào an toàn để replay.

## 14. Backpressure và queue gửi trong ứng dụng thực

Nhiều producer (UI handler, scheduler heartbeat, background worker) có thể cùng muốn gửi qua một WebSocket. Thiết kế tốt cần:

1. **Một queue outbound per-connection**, giữ kiểu message, payload, requestId và priority.
2. **Không chồng lệnh text/binary send pending**. Chỉ khởi phát message tiếp theo khi future trước đã hoàn tất phù hợp. `thenCompose` hữu ích cho một chuỗi đơn giản; queue giúp mở rộng nhiều producer.
3. **Giới hạn số messages và tổng số bytes pending**, tránh hết RAM nếu mạng chậm hoặc peer không nhận.
4. **Phân biệt send completion và ứng dụng ACK**. `sendText` thành công chưa đủ đánh dấu RPC đã hoàn tất.
5. **Heartbeat riêng**: chờ Pong có matching ID/nonce và deadline, đừng dùng sendPing future như Pong future.
6. **Timeout phân tầng**: connect/handshake, send, peer response, heartbeat và close handshake là các điều kiện khác nhau.
7. **Shutdown có kiểm soát**: dừng nhận message mới, xử lý/huỷ queue theo policy, gửi Close, chờ peer khi cần rồi cleanup.
8. **Quan sát lỗi có ngữ cảnh**: ghi type/size/requestId, cause, trạng thái socket; không log token, mật khẩu hoặc payload nhạy cảm.

Vì `whenComplete` và listener callback có thể chạy trên thread do runtime quản lý, tránh xử lý blocking/CPU-heavy ngay trong callback. Khi cần lưu dữ liệu nhận sau callback, **copy ByteBuffer/CharSequence đúng vòng đời** trước khi giao sang thread khác.

## 15. Những nhầm lẫn cần tránh

| Nhầm lẫn | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “sendText trả WebSocket ngay” | Trả `CompletableFuture<WebSocket>` | Quan sát normal/exception completion |
| “sendPing hoàn tất tức peer sống” | Chỉ mới gửi Ping | Chờ `onPong` và so payload/deadline |
| “onPong là future của sendPing” | Nó là callback chiều inbound | Hai tín hiệu khác nhau |
| “Pong là ACK đã xử lý yêu cầu” | Pong là control message | Thiết kế ACK nghiệp vụ riêng |
| “Phải tự gửi Pong trong onPing” | JDK tự gửi reciprocal Pong | Chỉ gửi thủ công khi thực sự cần |
| “Ping được gửi 1000 byte” | Control payload giới hạn 125 byte | Kiểm tra `remaining()` |
| “ByteBuffer capacity = số byte gửi” | Gửi position tới limit | Kiểm tra `remaining()` |
| “Có thể clear buffer ngay sau sendBinary” | Future có thể pending | Đợi completion trước |
| “last=false là message hoàn chỉnh” | Message chưa kết thúc | Gửi tiếp tới `last=true` |
| “Một sendText = một onText callback” | Receiver có thể nhận nhiều đoạn | Tích lũy tới `last=true` |
| “request(1) cho 1 byte” | Nó cho 1 receive callback | Duy trì demand đúng |
| “Listener CompletionStage là send future” | Quản vòng đời dữ liệu nhận | Phân biệt outbound/inbound |
| “get(timeout) hủy send” | Chỉ là timeout chờ caller | Quản cancel/close riêng |
| “sendClose hoàn tất = peer đã đóng” | Chưa có nghĩa nhận onClose | Theo dõi peer closure riêng |
| “Loopback server demo phù hợp production” | Thiếu nhiều trường hợp RFC | Dùng server library chuẩn |
| “ws:// luôn an toàn như wss://” | ws:// không có TLS | Dùng wss:// khi triển khai thực |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `ws.sendText("abc", true)` trả gì? Server chắc chắn đã lưu dữ liệu chưa?

*Đáp án:* Trả `CompletableFuture<WebSocket>`. Normal completion chỉ cho biết thao tác gửi đã xong; không chứng minh server đã xử lý hoặc lưu. Cần ACK nghiệp vụ.

**Câu 2.** `sendBinary(buffer,true)` đã gọi nhưng future chưa xong. Được `buffer.clear()` không?

*Đáp án:* Không. Buffer đang được API gửi sử dụng. Chỉ truy cập lại sau completion theo hợp đồng.

**Câu 3.** Vì sao future của `sendPing` thành công chưa đủ để ghi “heartbeat OK”?

*Đáp án:* Vì nó không xác nhận client đã **nhận Pong**. Cần listener `onPong`, so nonce và deadline.

**Câu 4.** Có cần `sendPong` ngay trong mọi `onPing` không?

*Đáp án:* Thường không; JDK WebSocket client tự phát reciprocal Pong. Gửi Pong thủ công nếu giao thức thử nghiệm cần.

**Câu 5.** `ws.sendText("A",false)` rồi lập tức `sendBinary(...)` có hợp lệ không?

*Đáp án:* Message text chưa kết thúc. Không đổi type trước khi hoàn tất, thao tác có thể exceptional `IllegalStateException`.

**Câu 6.** `onText(ws,"Xin ",false)` rồi `onText(ws,"chào",true)` là bao nhiêu messages?

*Đáp án:* Một text message hoàn chỉnh; phải ghép thành `Xin chào`.

**Câu 7.** Vì sao phải `request(1)` trong listener để nhận Pong tiếp theo?

*Đáp án:* Demand là số callback được phép chuyển tiếp. Không có demand, callback có thể không được gọi dù frame đã đến.

**Câu 8.** `sendClose` future thành công có đồng nghĩa đã thấy `onClose` không?

*Đáp án:* Không. Một cái là send completion, một cái là sự kiện nhận Close từ peer.

## 17. Bài tập thực hành

1. Chạy `WebSocketSendKindsDemo.java`, chỉ rõ bốn dòng gửi text/binary/Ping/Pong và từng `get(5, TimeUnit.SECONDS)` đang xác nhận điều gì.
2. Thay `Hello WS` bằng `Xin chào`, xác minh text listener vẫn nhận đúng Unicode; không sửa CharSequence trước completion.
3. Đổi binary `[1,2,3]` thành `[10,20,30,40]` và kiểm tra echo byte chính xác.
4. Đổi Ping payload từ `hi` sang `probe-42` và so sánh payload nhận trong `onPong`; thêm deadline heartbeat.
5. Gửi Ping payload 126 byte trên **client đã kết nối**, xử lý future failure có kiểm soát và giải thích giới hạn 125 byte.
6. Cài một hàng đợi giới hạn để nhiều producer lần lượt gửi text/binary, theo dõi futures và số byte in-flight.
7. Thử bỏ `ws.request(1)` trong listener trên môi trường test và quan sát receive callbacks không tiến triển, sau đó khôi phục.
8. Viết protocol ACK: client gửi text có `requestId=42`, server chỉ trả `ack:42` **sau khi xử lý**, client không đánh dấu nghiệp vụ thành công chỉ từ send future.
9. Thực hành fragmentation `sendText(...,false)` rồi `sendText(...,true)` **với WebSocket server đầy đủ**; server test trong bài chỉ hỗ trợ FIN frames.
10. Thêm xử lý timeout/exception từ `get` hoặc `whenComplete` và mô tả cách cleanup bằng `sendClose` hoặc `abort` khi cần.
11. Chuyển từ test `ws://127.0.0.1` sang một endpoint thử nghiệm `wss://` có chứng chỉ hợp lệ, giữ xác thực TLS.

## Tài liệu tham khảo chính thức

- [`WebSocket` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/WebSocket.html): sendText, sendBinary, sendPing, sendPong, sendClose, send futures và receive demand.
- [`WebSocket.Listener` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): onText, onBinary, onPing, onPong, onClose, onError và CompletionStage chiều nhận.
- [`WebSocket.Builder` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): `buildAsync` và handshake.
- [`CompletableFuture` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): get, join, thenCompose, whenComplete, exception và timeout.
- [`ByteBuffer` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): position, limit, remaining và buffer lifetime.
- [RFC 6455 — WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455): framing, client masking, Ping/Pong/Close và giới hạn control payload.
