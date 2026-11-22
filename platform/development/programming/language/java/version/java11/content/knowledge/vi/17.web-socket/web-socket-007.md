# Ping, pong và theo dõi kết nối WebSocket (Java 11)

Trong một ứng dụng dùng WebSocket, việc tạo kết nối thành công chưa bảo đảm kết nối đó còn hoạt động mãi. Máy chủ có thể khởi động lại, mạng di động có thể đổi tuyến, bộ định tuyến/NAT có thể loại một kết nối nhàn rỗi, hoặc đường truyền có thể bị đứt mà client chưa nhận được sự kiện đóng. Để **kiểm tra đầu bên kia còn phản hồi**, giao thức WebSocket cung cấp hai **control frame**: **Ping** và **Pong**.

Từ **Java 11**, `java.net.http.WebSocket` là API client WebSocket chuẩn trong Java SE, có:

```java
CompletableFuture<WebSocket> sendPing(ByteBuffer message);
CompletableFuture<WebSocket> sendPong(ByteBuffer message);
```

và listener:

```java
CompletionStage<?> onPing(WebSocket webSocket, ByteBuffer message);
CompletionStage<?> onPong(WebSocket webSocket, ByteBuffer message);
```

**Phân biệt quan trọng:** `sendPing(...).get()` chỉ chứng minh thao tác **gửi Ping** đã hoàn thành; nó **không chứng minh** đầu bên kia đã nhận và trả lời. Muốn theo dõi kết nối bằng heartbeat, cần quan sát **`onPong`**, đối chiếu payload/nonce và áp thời hạn phản hồi riêng.

Bài thuộc nhóm **WebSocket** của Java 11, tập trung vào kiến thức còn dùng được với các JDK đang được bảo trì. Các ví dụ dùng API có từ Java 11, chạy trên JDK hiện hành hỗ trợ biên dịch `javac --release 11`. Không cần sử dụng các API HTTP/WebSocket incubator cũ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Ping/Pong ở cấp WebSocket protocol** với heartbeat JSON/text của ứng dụng.
2. Gọi `WebSocket.sendPing(ByteBuffer)`, hiểu kiểu trả về `CompletableFuture<WebSocket>`.
3. Viết `WebSocket.Listener.onPing`/`onPong` và quản lý `WebSocket.request(long n)` đúng.
4. Biết Java HTTP Client **tự phản hồi bằng Pong** khi nhận Ping; không gửi Pong thủ công lần nữa nếu không có lý do đặc biệt.
5. Hiểu giới hạn **125 byte** cho payload Ping/Pong, giới hạn từ `position` đến `limit` và vòng đời `ByteBuffer`.
6. Thiết kế heartbeat có nonce, thời điểm gửi, deadline, phát hiện Pong không khớp, RTT và một probe đang chờ.
7. Phân biệt send completion, receipt of Pong, timeout, `onError`, `onClose` và trạng thái hai chiều `isInputClosed`/`isOutputClosed`.
8. Biết cách đóng kết nối, hủy, kết nối lại với backoff và tránh false-positive khi mạng chậm.
9. Chạy ví dụ loopback xác minh cả **Pong tự động từ Java** và **Pong do server gửi**, không cần Internet.
10. Kiểm thử logic heartbeat bằng đồng hồ mô phỏng, không phụ thuộc thời gian thực.

## 2. Ping và Pong là control frame, không phải text message

Theo **RFC 6455**, WebSocket dùng những opcode:

| Control frame | Opcode | Ý nghĩa |
| --- | ---: | --- |
| `Close` | `0x8` | Bắt đầu/kết thúc quá trình đóng kết nối |
| **Ping** | **`0x9`** | Hỏi xem peer còn phản hồi; có thể mang dữ liệu nhận diện |
| **Pong** | **`0xA`** | Trả lời Ping hoặc gửi một heartbeat một chiều không được yêu cầu |

Các control frame:

- **Không được phân mảnh** thành nhiều frame.
- Có **payload tối đa 125 byte**, kể cả Ping và Pong.
- Có thể xuất hiện xen giữa các frame của một message dữ liệu đang phân mảnh.
- Không được nhầm với application-level message như chuỗi `"ping"` trong `sendText`.

Một Ping có thể mang payload, chẳng hạn 8 byte ID hoặc nonce. Khi phản hồi Ping, **Pong tương ứng phải chứa cùng payload bytes**. Theo chuẩn, cũng có thể có **Pong không được yêu cầu (unsolicited Pong)**; không tự động coi mọi Pong nhận được là phản hồi của probe hiện tại.

### Ví dụ thứ tự trao đổi

```text
Client                                 Server
   | -------- Ping(nonce = 41) --------> |
   |                                      |
   | <------- Pong(nonce = 41) --------- |
   |                                      |
   |  onPong kiểm tra nonce == 41         |
   |  cập nhật liveness và RTT            |
   |                                      |
   | <-- Ping("server-check") ----------- |
   |                                      |
   | -- Pong("server-check") [auto] ----> |
```

Đây là **sơ đồ giao thức**, không phải các lời gọi trực tiếp giữa hai đối tượng Java. `sendPing` tạo Ping phía client. Một server tuân thủ RFC sẽ gửi Pong tương ứng. Ngược lại, khi server gửi Ping tới client Java, implementation `java.net.http.WebSocket` **tự gửi Pong**, đồng thời listener có thể nhận `onPing` để quan sát sự kiện.

**Không tự dùng `sendPong` để trả lời lần hai** trong `onPing` theo mặc định. Tài liệu Java SE 11 nêu rõ WebSocket tự phản hồi Ping bằng Pong, nên việc gửi Pong thủ công cho cùng Ping là không cần thiết và có thể gây thêm traffic.

## 3. Tạo WebSocket client trong Java 11

API chuẩn:

```java
HttpClient client = HttpClient.newHttpClient();

WebSocket socket = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .buildAsync(
                URI.create("wss://ws.example.invalid/events"),
                listener)
        .join();
```

Đây là **đoạn mã bên trong một phương thức**, cần `HttpClient`, `WebSocket`, `Duration`, `URI` và đối tượng `WebSocket.Listener listener` đã được khởi tạo. URI là tên miền minh họa, **không phải endpoint có thể kết nối thực tế**. `buildAsync` trả một `CompletableFuture<WebSocket>`; `join()` có thể ném `CompletionException` nếu handshake không thành công.

Một số ý chính:

- Dùng **`wss://`** (TLS) cho kết nối có dữ liệu thực/nhạy cảm trong production; `ws://` có thể phù hợp cho test loopback.
- `connectTimeout` giới hạn quá trình thiết lập WebSocket, **không phải heartbeat interval** hay Pong timeout.
- Khi handshake thành công, listener được gọi `onOpen` trước các callback nhận dữ liệu khác.
- Có thể gửi frame với `sendText`, `sendBinary`, `sendPing`, `sendPong`, `sendClose`.
- WebSocket có **hai phía input/output độc lập**; việc phía output đóng không phải lúc nào cũng đồng nghĩa input đã đóng.
- `isInputClosed()` và `isOutputClosed()` cho biết trạng thái từng phía; chúng **không phải phép đo liveness tức thời**.

Đây là WebSocket client chuẩn Java SE 11. Không nhầm với API `javax.websocket`/`jakarta.websocket` của các framework WebSocket server hoặc client khác: các thư viện đó có cách cấu hình Ping/Pong khác nhau.

## 4. Gửi Ping: payload, Future và trạng thái pending

Đoạn mã trong một phương thức có `WebSocket socket`:

```java
byte[] nonce = "probe-42".getBytes(StandardCharsets.US_ASCII);
ByteBuffer payload = ByteBuffer.wrap(nonce);

CompletableFuture<WebSocket> sendFuture =
        socket.sendPing(payload);

sendFuture.whenComplete((webSocket, failure) -> {
    if (failure != null) {
        // Không gửi Ping thành công; phân loại lỗi và dừng probe.
    } else {
        // Ping ĐÃ ĐƯỢC GỬI, nhưng CHƯA bảo đảm nhận Pong.
    }
});
```

Cần imports `ByteBuffer`, `StandardCharsets`, `CompletableFuture`. Đây là snippet; không tự tạo kết nối, không có `main`.

### Các điều kiện quan trọng

1. **Giới hạn `message.remaining() <= 125`**. Tính từ `position` đến `limit`, không phải bằng `capacity()`. Payload hơn 125 byte sẽ khiến `CompletableFuture` hoàn tất lỗi với `IllegalArgumentException`.
2. **Không sửa hoặc đọc `ByteBuffer` đang gửi** cho tới khi future hoàn tất. Sau khi gửi thành công, buffer không còn bytes trong phạm vi `remaining()`; tạo một buffer mới hoặc view mới nếu cần gửi lần khác.
3. **Không có đồng thời một thao tác gửi Ping/Pong đang pending** trên cùng WebSocket. Nếu có pending Ping/Pong send operation, `sendPing`/`sendPong` có thể hoàn tất exceptional với `IllegalStateException`. Đây là **giới hạn pending send**, không phải chính sách “một probe chưa được Pong” của ứng dụng — hai việc khác nhau.
4. Nếu I/O thất bại hoặc output đã đóng, future có thể thất bại với `IOException`.
5. `sendPing(...)` trả `CompletableFuture<WebSocket>` của **send operation**, không phải `CompletableFuture<Pong>`. Java không tự gắn một `onPong` cụ thể vào future này để ứng dụng tính RTT.
6. Không phát Ping sau khi ứng dụng đã bắt đầu đóng hoặc hủy kết nối; kiểm tra vòng đời qua trạng thái riêng của session và xử lý race.

### Vì sao `ByteBuffer` cần được xử lý cẩn thận?

Giả sử:

```java
ByteBuffer payload = ByteBuffer.allocate(130);
payload.position(10);
payload.limit(120);
```

Đây là snippet tạo buffer: `remaining() == 110`, nên **không** vượt 125 byte mặc dù `capacity() == 130`. Ngược lại, buffer có `capacity() == 200` và `remaining() == 126` là quá dài cho một Ping.

Với payload do `onPing` hoặc `onPong` cung cấp, hãy đọc bytes từ **`position` tới `limit`**, tránh gọi `array()` vì buffer có thể là read-only/direct. Dùng `duplicate()` nếu muốn đọc mà không đổi con trỏ của buffer gốc. Đặc biệt, listener phải **không truy cập buffer nhận sau khi CompletionStage callback trả về đã hoàn tất**, bởi Java WebSocket được phép thu hồi nó.

## 5. Nhận Ping và Pong qua `WebSocket.Listener`

Java 11 có hai callback:

```java
@Override
public CompletionStage<?> onPing(
        WebSocket socket, ByteBuffer payload) {
    // HTTP Client tự gửi Pong tương ứng.
    // Có thể đọc payload để thống kê, nhưng không cần sendPong().
    socket.request(1);
    return CompletableFuture.completedFuture(null);
}

@Override
public CompletionStage<?> onPong(
        WebSocket socket, ByteBuffer payload) {
    // Đọc nonce và đối chiếu với probe đang đợi.
    socket.request(1);
    return CompletableFuture.completedFuture(null);
}
```

Đây là các **phương thức minh họa đặt bên trong một class `implements WebSocket.Listener`**, với imports `CompletionStage`, `CompletableFuture`, `ByteBuffer`, `WebSocket`; không phải chương trình độc lập.

### Vì sao phải `request(1)`?

`WebSocket` của Java 11 dùng cơ chế **receive demand**. Mỗi lời gọi `request(n)` tăng số lần Java được phép gọi các receive callbacks (`onText`, `onBinary`, `onPing`, `onPong`, `onClose`). Khi nhu cầu bằng 0, Java sẽ không gọi các receive callbacks thêm.

- `request(1)` cho phép **một lời gọi callback nhận tiếp theo**, **không** phải một byte hoặc một Ping.
- `onOpen` và `onError` **không** tính vào số lần nhận.
- Listener mặc định của Java 11 có `onOpen` tương đương `socket.request(1)`, và `onPing`/`onPong` mặc định cũng `request(1)`.
- Khi **override `onOpen` hoặc `onPong`**, bạn phải quản lý demand theo thiết kế của mình. Nếu quên `request(1)`, ứng dụng có thể không thấy callback tiếp theo dù mạng đang có dữ liệu.
- Không gọi `request(n)` với `n <= 0`; đó là đầu vào không hợp lệ.
- Một `CompletionStage` được trả về từ callback là tín hiệu về **vòng đời dữ liệu của callback**, không thay thế việc `request` thêm demand.

### `CompletionStage` và quyền sở hữu dữ liệu

Listener nhận `ByteBuffer` và có thể trả một `CompletionStage<?>`. Java WebSocket dùng thời điểm stage hoàn tất để biết khi nào được phép **thu hồi buffer**. Vì vậy:

```java
ByteBuffer view = message.duplicate();
byte[] owned = new byte[view.remaining()];
view.get(owned);
// Lưu owned vào state/future nếu cần dùng sau callback.
```

Đây là snippet trong callback, với `message` là `ByteBuffer` được nhận. `owned` là bản sao bytes độc lập; `duplicate()` chỉ sao chép **con trỏ/view**, không sao chép bytes. Không giữ `message` rồi giải mã nó tùy ý sau khi callback đã hoàn tất.

### `onError` và `onClose`

- `onError(WebSocket socket, Throwable error)` được gọi khi WebSocket gặp lỗi. Hãy ghi trạng thái session lỗi, ngừng heartbeat, hoàn tất/cancel các pending probe và lập kế hoạch reconnect nếu chính sách cho phép.
- `onClose(WebSocket socket, int code, String reason)` nhận Close frame; đây là callback cuối theo hợp đồng listener. Ngừng timer và giải phóng state. Không tiếp tục `request`/gửi Ping trong trạng thái đóng.
- Khi chủ động đóng, có thể gọi `socket.sendClose(WebSocket.NORMAL_CLOSURE, "done")` và đợi quá trình close handshake theo chính sách; `socket.abort()` là đóng đột ngột khi cần kết thúc ngay.

**Không nhầm close frame với sự cố mạng âm thầm.** Nếu TCP bị cắt mà không có Close frame, có thể chỉ xuất hiện `onError` hoặc heartbeat timeout, không có `onClose` bình thường.

## 6. Pong tự động và `sendPong` thủ công

Theo đặc tả Java 11:

- Khi nhận một Ping, `java.net.http.WebSocket` **tự gửi Pong** đúng payload, trừ trường hợp giao thức đã trong quá trình đóng mà việc phản hồi không còn phù hợp.
- `onPing` là nơi để quan sát, thống kê hoặc chuyển thông tin lên application; **không phải bắt buộc gọi `sendPong`**.
- `WebSocket.sendPong(ByteBuffer)` vẫn tồn tại để gửi **Pong theo chủ đích riêng** (chẳng hạn unsolicited Pong nếu giao thức ứng dụng yêu cầu).
- **Unsolicited Pong không yêu cầu bên nhận phản hồi bằng một Pong khác.** Không tạo vòng lặp Pong ↔ Pong.

So sánh:

| Hành động | Ai chịu trách nhiệm? | Có cần do application viết? |
| --- | --- | --- |
| Client gửi một Ping kiểm tra peer | `WebSocket.sendPing(payload)` | Có, khi chính sách heartbeat quyết định |
| Server gửi Ping tới client | Server | Không cần client khởi phát |
| Client trả Pong cho Ping của server | Java WebSocket implementation | **Không cần `sendPong` thủ công** |
| Client nhận Pong trả lời Ping của mình | `Listener.onPong` | Có, nếu muốn theo dõi heartbeat/RTT |
| Client gửi unsolicited Pong | `WebSocket.sendPong(payload)` | Chỉ khi có hợp đồng yêu cầu |
| Client phát hiện không có Pong đúng hạn | Heartbeat state/timer của ứng dụng | **Có** |

**Đừng nhầm hai loại “auto”:** Java tự **trả lời Ping đến**, nhưng không có nghĩa ứng dụng được tự động thiết lập **chu kỳ gửi Ping** và **Pong timeout** theo các con số mong muốn. Heartbeat policy là trách nhiệm của ứng dụng hoặc framework bạn dùng.

## 7. Ví dụ 1 — WebSocket loopback kiểm chứng cả hai chiều

Ví dụ hoàn chỉnh sau mở một WebSocket server **tối giản** ngay trên `127.0.0.1`, để không phụ thuộc dịch vụ hoặc tài khoản bên ngoài. Server thực hiện HTTP Upgrade handshake rồi gửi Ping có payload `"server-probe"`. Java WebSocket client tự trả Pong; server kiểm tra **payload giống nhau**. Sau đó client gửi Ping `"client-probe"`, server trả Pong với payload tương ứng; listener nhận `onPong`.

**Lưu ý phạm vi:** server trong bài chỉ nhận một kết nối và xử lý các control frame nhỏ. Nó không phải WebSocket server production, không triển khai toàn bộ validation, TLS, data frames, extension, fragmentation, concurrency hoặc security.

Tạo tệp **`WebSocketPingLoopbackDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
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

public class WebSocketPingLoopbackDemo {
    static final class Seen implements WebSocket.Listener {
        final CompletableFuture<String> ping = new CompletableFuture<>();
        final CompletableFuture<String> pong = new CompletableFuture<>();

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onPing(
                WebSocket socket, ByteBuffer payload) {
            ping.complete(readAscii(payload));
            socket.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onPong(
                WebSocket socket, ByteBuffer payload) {
            pong.complete(readAscii(payload));
            socket.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            ping.completeExceptionally(error);
            pong.completeExceptionally(error);
        }
    }

    static String readAscii(ByteBuffer original) {
        ByteBuffer view = original.duplicate();
        byte[] bytes = new byte[view.remaining()];
        view.get(bytes);
        return new String(bytes, StandardCharsets.US_ASCII);
    }

    static final class Frame {
        final int opcode;
        final byte[] payload;
        Frame(int opcode, byte[] payload) {
            this.opcode = opcode;
            this.payload = payload;
        }
    }

    static Frame readClientControlFrame(DataInputStream in)
            throws IOException {
        int first = in.readUnsignedByte();
        int second = in.readUnsignedByte();
        int opcode = first & 0x0F;
        int length = second & 0x7F;
        if ((first & 0x80) == 0 || (second & 0x80) == 0
                || length > 125 || length == 126 || length == 127) {
            throw new IOException("Invalid client control frame");
        }
        byte[] mask = new byte[4];
        in.readFully(mask);
        byte[] bytes = new byte[length];
        in.readFully(bytes);
        for (int i = 0; i < length; i++) {
            bytes[i] ^= mask[i % mask.length];
        }
        return new Frame(opcode, bytes);
    }

    static void sendControl(OutputStream out,
                            int opcode, byte[] body) throws IOException {
        if (body.length > 125) {
            throw new IllegalArgumentException("Control payload too large");
        }
        out.write(0x80 | opcode);
        out.write(body.length);
        out.write(body);
        out.flush();
    }

    static void handleOneClient(
            ServerSocket server, CompletableFuture<Boolean> gotAutoPong)
            throws Exception {
        try (Socket socket = server.accept()) {
            socket.setSoTimeout(5000);
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(socket.getInputStream(),
                            StandardCharsets.US_ASCII));
            String firstLine = reader.readLine();
            if (firstLine == null
                    || !firstLine.startsWith("GET ")) {
                throw new IOException("Bad handshake request");
            }
            String webSocketKey = null;
            String line;
            while ((line = reader.readLine()) != null
                    && !line.isEmpty()) {
                int colon = line.indexOf(':');
                if (colon > 0 && line.substring(0, colon)
                        .equalsIgnoreCase("Sec-WebSocket-Key")) {
                    webSocketKey = line.substring(colon + 1).trim();
                }
            }
            if (webSocketKey == null) {
                throw new IOException("Missing WebSocket key");
            }

            String magic =
                    "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
            byte[] digest = MessageDigest.getInstance("SHA-1")
                    .digest((webSocketKey + magic).getBytes(
                            StandardCharsets.US_ASCII));
            String accept = Base64.getEncoder().encodeToString(digest);
            String reply = "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
            OutputStream out = socket.getOutputStream();
            out.write(reply.getBytes(StandardCharsets.US_ASCII));
            out.flush();

            byte[] peerPayload =
                    "server-probe".getBytes(StandardCharsets.US_ASCII);
            sendControl(out, 0x9, peerPayload);

            DataInputStream in =
                    new DataInputStream(socket.getInputStream());
            Frame autoPong = readClientControlFrame(in);
            boolean matched = autoPong.opcode == 0xA
                    && Arrays.equals(autoPong.payload, peerPayload);
            gotAutoPong.complete(matched);
            if (!matched) {
                throw new IOException("Automatic pong mismatch");
            }

            Frame clientPing = readClientControlFrame(in);
            if (clientPing.opcode != 0x9) {
                throw new IOException("Expected client ping");
            }
            sendControl(out, 0xA, clientPing.payload);

            Frame close = readClientControlFrame(in);
            if (close.opcode == 0x8) {
                sendControl(out, 0x8,
                        new byte[] {3, (byte) 232});
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByName("127.0.0.1");
        try (ServerSocket server = new ServerSocket(0, 1, loopback)) {
            ExecutorService worker = Executors.newSingleThreadExecutor();
            CompletableFuture<Boolean> autoPong =
                    new CompletableFuture<>();
            try {
                Future<?> serverTask = worker.submit(() -> {
                    try {
                        handleOneClient(server, autoPong);
                    } catch (Exception ex) {
                        autoPong.completeExceptionally(ex);
                        throw new RuntimeException(ex);
                    }
                });

                HttpClient http = HttpClient.newBuilder()
                        .connectTimeout(Duration.ofSeconds(2))
                        .build();
                URI uri = URI.create("ws://127.0.0.1:"
                        + server.getLocalPort() + "/echo");
                Seen listener = new Seen();
                WebSocket socket = http.newWebSocketBuilder()
                        .connectTimeout(Duration.ofSeconds(3))
                        .buildAsync(uri, listener)
                        .get(5, TimeUnit.SECONDS);

                boolean repliedAutomatically =
                        autoPong.get(5, TimeUnit.SECONDS);
                String serverPing =
                        listener.ping.get(5, TimeUnit.SECONDS);

                ByteBuffer clientProbe = ByteBuffer.wrap(
                        "client-probe".getBytes(
                                StandardCharsets.US_ASCII));
                socket.sendPing(clientProbe)
                        .get(5, TimeUnit.SECONDS);
                String echoedPong =
                        listener.pong.get(5, TimeUnit.SECONDS);

                socket.sendClose(WebSocket.NORMAL_CLOSURE, "done")
                        .get(5, TimeUnit.SECONDS);
                serverTask.get(5, TimeUnit.SECONDS);

                System.out.println("Automatic pong matched: " +
                        repliedAutomatically);
                System.out.println("Client saw ping: " + serverPing);
                System.out.println("Client saw pong: " + echoedPong);
                System.out.println("Pong payload matched: " +
                        "client-probe".equals(echoedPong));
            } finally {
                worker.shutdownNow();
            }
        }
    }
}
```

### Biên dịch, chạy và stdout

Dùng compiler hỗ trợ Java 11:

```sh
javac --release 11 -encoding UTF-8 WebSocketPingLoopbackDemo.java
java WebSocketPingLoopbackDemo
```

**Stdout chính xác trong môi trường cho phép loopback:**

```text
Automatic pong matched: true
Client saw ping: server-probe
Client saw pong: client-probe
Pong payload matched: true
```

### Phân tích điều gì đã được kiểm chứng

1. Server nội bộ thực hiện `101 Switching Protocols` với `Sec-WebSocket-Accept` đúng handshake WebSocket; không kết nối ra Internet.
2. Server gửi Ping có opcode `0x9` với payload `server-probe`.
3. Java HTTP Client **tự** gửi Pong có opcode `0xA` và payload trùng nhau. Server đọc frame client (được mask theo giao thức) và so sánh; kết quả đầu tiên là `true`.
4. Listener `onPing` nhận payload `server-probe`. Nó **không gọi `sendPong`**, nhưng vẫn thấy Pong tự động đi ra; đây chính là hành vi cần học.
5. Client gửi `sendPing` với payload `client-probe`. Server nhận Ping và gửi lại Pong với đúng payload. Listener `onPong` nhận `client-probe`; dòng cuối so khớp `true`.
6. `onOpen`, `onPing` và `onPong` có `request(1)` để không làm cạn receive demand.
7. Tệp dùng `try-with-resources` và `ExecutorService.shutdownNow` để kết thúc socket/server; client gửi `sendClose` rồi server phản hồi Close frame.

**Không có khẳng định về độ trễ cố định.** Các timeout 2–5 giây chỉ là hạn chờ trong bài thực hành. Nếu môi trường chặn socket loopback hoặc máy quá tải, ví dụ có thể ném ngoại lệ thay vì in bốn dòng thành công; đó không phải bằng chứng API Ping/Pong sai.

**Không triển khai server production theo đoạn code này.** Parser chỉ đủ cho handshake/control frame của demo. Server thật cần thư viện WebSocket được bảo trì, kiểm tra protocol extensions, limits, masking, origins, TLS, authentication, fragmentation, control frame invariants, bảo mật và quản lý nhiều client.

## 8. Heartbeat khác với chỉ gọi `sendPing` theo lịch

Một **heartbeat đúng nghĩa** cần tối thiểu state:

```text
CONNECTED (không có probe đang chờ)
      |
      | đủ khoảng idle/heartbeat interval
      v
SENDING_PING(nonce, sentAt)
      |
      | sendPing future hoàn tất thành công
      v
AWAITING_PONG(nonce, deadline)
      |
      +--> onPong có cùng nonce
      |        -> tính RTT, ghi nhận alive, clear pending
      |
      +--> onPong không khớp/unsolicited
      |        -> không clear pending, có thể ghi metric
      |
      +--> lỗi sendPing/onError/onClose
      |        -> fail/closed, dừng timer
      |
      +--> quá deadline
               -> đánh dấu suspect/unhealthy,
                  đóng/hủy kết nối theo chính sách,
                  reconnect có backoff nếu cần
```

**Chính sách một probe đang chờ** là lựa chọn đơn giản, tránh nhầm Pong của lần cũ với lần mới. Đừng tự đánh đồng nó với giới hạn Java về **pending send Ping/Pong operations**: một send có thể hoàn tất trong khi vẫn chưa có Pong; ứng dụng vẫn chờ response.

### Những trường cần theo dõi

| Trường heartbeat | Vai trò |
| --- | --- |
| `connectionId` / generation | Phân biệt WebSocket cũ với kết nối mới sau reconnect |
| `nonce` hoặc sequence ID | Đối chiếu Pong với Ping đã gửi; nên duy nhất trong phiên |
| `sentAtNanos` | Đo RTT và xác định timeout bằng đồng hồ đơn điệu |
| `deadlineNanos` | Hạn nhận Pong |
| `awaitingPong` | Không phát thêm probe trùng khi một probe chưa hoàn tất |
| `lastPongAtNanos` | Mốc heartbeat thành công gần nhất |
| `lastActivityAtNanos` | Có thể dùng để tránh ping khi đã có dữ liệu đáng tin cậy |
| `closed` hoặc `stopping` | Không schedule Ping/reconnect sau khi người dùng chủ động đóng |

**Không dùng `System.currentTimeMillis()` để đo RTT** khi cần độ bền trước thay đổi đồng hồ máy. Dùng `System.nanoTime()` cho **khoảng thời gian tương đối**, với thời điểm bắt đầu/kết thúc của cùng tiến trình. Đây không phải Unix timestamp để lưu trữ hoặc đồng bộ giữa máy.

### RTT không phải độ trễ mạng thuần

`RTT = pongReceivedAt - pingSentAt` bao gồm thời gian chờ thread, queue, proxy, server scheduling và đường truyền. Đây là một tín hiệu vận hành, **không phải cam kết về ping IP/ICMP** hay hiệu năng end-to-end của toàn bộ nghiệp vụ.

## 9. Ví dụ 2 — tracker có nonce và timeout, kiểm thử bằng đồng hồ mô phỏng

Để test liveness mà không chờ vài giây thật hoặc mở socket, chúng ta tách logic quản lý probe thành lớp thuần Java. Phần này mô phỏng việc **gửi Ping thành công và nhận Pong tương ứng**; nó **không gửi WebSocket thật**, nên cần kết hợp với listener và scheduler ở production.

Tạo tệp **`HeartbeatLogicDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.util.concurrent.TimeUnit;

public class HeartbeatLogicDemo {
    static final class Tracker {
        private long lastIssued;
        private long pendingNonce;
        private long sentAtNanos;
        private long lastRttNanos = -1;
        private boolean awaiting;

        ByteBuffer issueProbe(long nowNanos) {
            if (awaiting) {
                throw new IllegalStateException("Pong still pending");
            }
            pendingNonce = ++lastIssued;
            sentAtNanos = nowNanos;
            awaiting = true;
            ByteBuffer payload = ByteBuffer.allocate(Long.BYTES);
            payload.putLong(pendingNonce);
            payload.flip();
            return payload;
        }

        boolean onPong(ByteBuffer payload, long nowNanos) {
            if (!awaiting || payload.remaining() != Long.BYTES) {
                return false;
            }
            if (payload.duplicate().getLong() != pendingNonce) {
                return false;
            }
            awaiting = false;
            lastRttNanos = nowNanos - sentAtNanos;
            return true;
        }

        boolean expired(long nowNanos, long timeoutNanos) {
            return awaiting
                    && nowNanos - sentAtNanos >= timeoutNanos;
        }

        long lastRttMillis() {
            return TimeUnit.NANOSECONDS.toMillis(lastRttNanos);
        }
    }

    public static void main(String[] args) {
        Tracker tracker = new Tracker();
        long second = TimeUnit.SECONDS.toNanos(1);

        ByteBuffer probe1 = tracker.issueProbe(0);
        System.out.println("Probe #1 bytes: " + probe1.remaining());

        ByteBuffer wrong = ByteBuffer.allocate(Long.BYTES);
        wrong.putLong(999L);
        wrong.flip();
        System.out.println("Wrong pong accepted: " +
                tracker.onPong(wrong, second / 100));

        System.out.println("Correct pong accepted: " +
                tracker.onPong(probe1.asReadOnlyBuffer(), second / 40));
        System.out.println("RTT ms: " + tracker.lastRttMillis());

        tracker.issueProbe(5 * second);
        System.out.println("Probe #2 expired at 2s: " +
                tracker.expired(7 * second, 3 * second));
        System.out.println("Probe #2 expired at 4s: " +
                tracker.expired(9 * second, 3 * second));
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 HeartbeatLogicDemo.java
java HeartbeatLogicDemo
```

**Stdout chính xác:**

```text
Probe #1 bytes: 8
Wrong pong accepted: false
Correct pong accepted: true
RTT ms: 25
Probe #2 expired at 2s: false
Probe #2 expired at 4s: true
```

### Giải thích

1. `issueProbe(0)` tạo một nonce kiểu `long` dài **8 byte**, đúng dưới mức 125 byte.
2. Pong giả có nonce `999` không khớp probe hiện hành, nên `false` và **không** xóa `awaiting`.
3. Pong đúng được gửi lại ở mốc thời gian giả lập `25 ms`, nên `true`, clear pending và lưu RTT `25 ms`.
4. `issueProbe(5 * second)` mở probe thứ hai. Khi chỉ trôi qua 2 giây với timeout 3 giây, `expired == false`; sau 4 giây, `true`.
5. `ByteBuffer.duplicate()` giúp đọc nonce mà không thay đổi position của buffer gốc; với callback thật, phải đọc/copy trước khi callback stage hoàn tất.
6. `TimeUnit.NANOSECONDS.toMillis` dùng để hiển thị RTT dạng mili giây; giá trị nội bộ vẫn dùng nano giây cho so sánh.

**Giới hạn có chủ đích của tracker:** code mô phỏng thời gian được truyền từ ngoài nên dễ unit test; chưa tích hợp thread scheduling, lỗi `sendPing`, connection generation, close/reconnect hay nguồn nonce ngẫu nhiên. Với hệ thống có callback và timer ở các thread khác nhau, phải **đồng bộ truy cập state** hoặc tập trung các chuyển trạng thái vào một event loop. Không dùng nguyên bản lớp không đồng bộ hóa này cho nhiều thread tùy tiện.

## 10. Ghép tracker với `WebSocket.Listener` và scheduler

Sau khi hiểu hai ví dụ, một thiết kế production thường gồm:

1. **Listener** nhận `onPong`, copy payload, chuyển sự kiện tới heartbeat controller.
2. **Heartbeat controller** giữ `pendingNonce`, `sentAt`, `deadline`, `connectionGeneration` và trạng thái.
3. **Scheduler** định kỳ đánh giá connection idle và quyết định có gửi Ping hoặc đánh dấu timeout.
4. **WebSocket transport** thực hiện `sendPing`, nhận completion, `sendClose`/`abort`.
5. **Reconnect manager** chỉ hoạt động nếu use case còn cần kết nối; áp backoff, giới hạn attempts và xác thực lại khi cần.

Minh họa việc gửi một probe trong một service đã có `WebSocket socket` và `HeartbeatTracker tracker`:

```java
ByteBuffer pingPayload = tracker.createProbe(System.nanoTime());

socket.sendPing(pingPayload).whenComplete((ws, failure) -> {
    if (failure != null) {
        // Hủy probe hiện tại và đánh dấu lỗi gửi;
        // không coi đó là một Pong timeout thông thường.
        tracker.onSendFailure(failure);
    }
});
```

**Đây chỉ là pseudocode định hướng tích hợp**, vì `HeartbeatTracker`, `createProbe` và `onSendFailure` là các phương thức **do ứng dụng tự định nghĩa**, không phải API có sẵn của Java SE. Tên lớp này khác với `Tracker` trong demo để tránh nhầm rằng có thể copy snippet mà không viết controller. Production cần đồng bộ state và xử lý callback lỗi.

Listener tương ứng nhận Pong:

```java
@Override
public CompletionStage<?> onPong(
        WebSocket socket, ByteBuffer message) {
    ByteBuffer view = message.duplicate();
    byte[] payload = new byte[view.remaining()];
    view.get(payload);

    // Chuyển payload độc lập tới controller có thread-safety;
    // controller đối chiếu nonce và cập nhật thời gian nhận.
    heartbeatEvents.offer(payload);

    socket.request(1);
    return CompletableFuture.completedFuture(null);
}
```

**Đây là các phương thức trong class listener có `heartbeatEvents` do ứng dụng khai báo**, không phải chương trình độc lập; khi dùng queue, nó phải **hữu hạn và có chính sách khi đầy**. Với callback thực tế, nếu `offer` thất bại, không được âm thầm bỏ mất Pong liên tục mà vẫn coi kết nối khỏe. Có thể xử lý trực tiếp rất nhanh trong callback nếu state được đồng bộ phù hợp.

### Một lịch Ping hợp lý phải cân nhắc môi trường

Không có chu kỳ **30 giây** hay **5 giây** nào “đúng” cho mọi WebSocket. Lựa chọn dựa trên:

- Idle timeout của server, reverse proxy, load balancer, NAT và mạng di động.
- Độ trễ RTT bình thường, jitter và hiện tượng tạm dừng hệ thống/GC.
- Tần suất message ứng dụng: nếu đã trao đổi dữ liệu thường xuyên, có thể không cần Ping quá dày.
- Năng lượng/băng thông trên mobile hoặc thiết bị IoT.
- Số lượng kết nối đồng thời: mỗi client Ping một lần mỗi giây có thể tạo tải lớn.
- Hạn mức reconnect, hậu quả khi một liveness check báo sai và SLA nghiệp vụ.

Ví dụ **policy minh họa**, không phải mặc định Java:

```text
heartbeatInterval = 30s
pongTimeout       = 10s
maxOutstanding    = 1 probe
onTimeout         = mark suspect, close/abort, reconnect with jitter
reconnectDelay    = exponential backoff, bounded attempts
```

Nếu timer thức dậy muộn do OS suspend hoặc GC pause, hãy dùng **đồng hồ đơn điệu** và cân nhắc một khoảng đệm/grace period để giảm false-positive. Đừng liên tục đóng và kết nối lại chỉ vì một lần lịch chạy chậm.

## 11. Liveness, trạng thái socket và trạng thái nghiệp vụ khác nhau

| Tín hiệu | Có thể kết luận gì? | Không thể kết luận gì? |
| --- | --- | --- |
| `buildAsync` hoàn thành | WebSocket handshake đã thành công lúc đó | Kết nối sẽ còn sống sau nhiều phút |
| `socket.isInputClosed() == false` | Phía input chưa được đánh dấu đã đóng | Peer vẫn đang online ngay lúc này |
| `socket.isOutputClosed() == false` | Phía output chưa được đánh dấu đã đóng | Mạng chắc chắn gửi được bytes |
| `sendPing` future hoàn tất bình thường | Thao tác gửi Ping đã hoàn thành theo API | Pong đã được nhận |
| `onPong` có nonce khớp | Đã thấy phản hồi của peer cho probe đó | Peer sẽ tiếp tục sống, business service khỏe |
| `onPong` payload không khớp | Có một Pong khác/không tương ứng | Probe hiện tại đã hoàn thành |
| `onClose` | Đã nhận Close frame | Mọi tiến trình nghiệp vụ đã được hoàn tất |
| `onError` | Có lỗi trong WebSocket | Lỗi đó có thể được khôi phục mà không reconnect |
| Heartbeat timeout | Không nhận được Pong đúng deadline | Peer chắc chắn đã tắt; có thể mạng chậm hoặc lịch xử lý trễ |
| Một message ứng dụng mới | Luồng dữ liệu gần đây hoạt động | Mọi phụ thuộc backend đều khỏe |

**Tách ba lớp sức khỏe:**

1. **TCP/network connectivity:** đường kết nối vẫn chuyển được byte.
2. **WebSocket liveness:** đầu bên kia trả lời control frame.
3. **Application/business readiness:** service phía sau có thể nhận/xử lý command, đồng bộ dữ liệu và thực hiện hợp đồng.

Một Pong thành công **không đủ** để khẳng định database, message queue hay permission của một operation nghiệp vụ đang tốt. Nếu cần readiness theo domain, thiết kế application-level heartbeat/health message riêng, có xác thực và schema phù hợp.

## 12. Ping/Pong ở server, browser và client Java khác nhau

- **Java 11 WebSocket client:** có `sendPing`, `sendPong` và listener `onPing`/`onPong`.
- **Server framework:** tùy thư viện, có thể tự phản hồi Ping hoặc yêu cầu callback để giám sát; đọc tài liệu implementation thực tế.
- **WebSocket JavaScript trong trình duyệt:** API trình duyệt tiêu chuẩn **không cung cấp trực tiếp `sendPing` hoặc `onPong` ở tầng WebSocket protocol** cho JavaScript ứng dụng. Browser thường tự xử lý control frames ở nền. Nếu ứng dụng browser cần chủ động đo heartbeat, thường thiết kế message cấp ứng dụng như JSON `{"type":"ping","id":"..."}` và response `{"type":"pong","id":"..."}`; server phải hiểu schema đó.

**Không nhầm application ping với control Ping.** Một chuỗi JSON `{"type":"ping"}` gửi qua `sendText` là **data frame**, không phải opcode `0x9`. Java `Listener.onPing` sẽ **không tự nhận** loại message ứng dụng này; nó được xử lý qua `onText` nếu server gửi dạng text.

Cả hai tầng heartbeat có thể cùng tồn tại nếu cần theo dõi khác nhau, nhưng phải tránh chi phí/hành vi trùng lặp.

## 13. Xử lý Ping/Pong khi đóng và khi có lỗi

### Đóng bình thường

Khi user rời màn hình hoặc ứng dụng không cần kết nối nữa:

1. Đánh dấu state `stopping` để scheduler không tạo Ping mới.
2. Hủy những timeout task còn chờ và dọn pending nonce.
3. Gọi `socket.sendClose(WebSocket.NORMAL_CLOSURE, "done")` để bắt đầu orderly close nếu đường truyền còn khả dụng.
4. Quan sát future gửi Close và `onClose` theo thời hạn phù hợp; không chờ vô hạn.
5. Dọn tài nguyên ứng dụng và không tự reconnect nếu đó là hành động đóng có chủ đích.

### Hủy đột ngột sau heartbeat timeout

`WebSocket.abort()` đóng input/output đột ngột. Nó có thể cần thiết khi kết nối không phản hồi, nhưng **không bảo đảm server biết chính xác vì sao** hoặc đã rollback tác vụ đang làm. Sau abort, mọi request nghiệp vụ “đã gửi nhưng chưa nhận kết quả” có thể ở trạng thái **không xác định**.

### Tránh lỗi xử lý close liên tục

Một connection controller nên có **state machine** hoặc atomic transition:

```text
NEW -> CONNECTING -> OPEN -> SUSPECT -> CLOSING -> CLOSED
                        |          |
                        +-> FAILED +-> CLOSED
                                 |
                              reconnect?
```

Điều này ngăn race giữa `onPong` đến đúng lúc timeout, `onError` và người dùng chủ động close. Nếu đã đóng một generation cũ, event `onPong` muộn của generation đó **không** được cập nhật trạng thái của WebSocket mới vừa reconnect.

## 14. Thiết kế xử lý đồng thời và callback an toàn

WebSocket.Listener Java 11 bảo đảm callback cho **cùng một WebSocket** được gọi tuần tự theo thiết kế, nhưng điều đó **không bảo đảm timer thread, UI thread hoặc controller thread của bạn** truy cập state một cách tuần tự. Một listener dùng cho nhiều WebSocket cũng có thể nhận callback từ các WebSocket khác nhau theo những thread khác nhau.

Có hai chiến lược hợp lệ:

- **Một event loop/thread sở hữu state:** listener và scheduler gửi event vào queue hữu hạn; state machine xử lý tuần tự, không cần nhiều lock trong logic cốt lõi.
- **State được đồng bộ hóa rõ ràng:** dùng `synchronized`, `AtomicReference`, concurrent collections hoặc các kỹ thuật phù hợp để bảo vệ `awaitingPong`, nonce và close state. Mọi transition cần được thiết kế để không có lost update.

**Không giữ lock ứng dụng trong khi block đợi future WebSocket hoàn tất.** Điều đó có thể gây deadlock hoặc starvation khi callback cần cập nhật state dưới cùng lock. Dùng completion callbacks và dispatch ngắn gọn, hoặc xử lý asynchronously trên executor đã quản lý.

**Không tạo scheduler mới cho mỗi Ping.** Thay vì mỗi connection tự tạo quá nhiều thread, có thể dùng một `ScheduledExecutorService` chia sẻ và giới hạn số tác vụ, với lịch hủy rõ ràng. Khi ứng dụng dừng, shutdown executor theo vòng đời.

### Timeout không phải “cứ chưa có Pong sau X giây thì lỗi Java”

Java `sendPing` không tự cung cấp một `Pong timeout` cho nghiệp vụ. `CompletableFuture.orTimeout(...)` trên future của `sendPing` chỉ giới hạn **send operation**, không kiểm soát tương ứng `onPong`. Pong deadline phải được đo ở **heartbeat tracker** và đối chiếu đúng nonce.

## 15. Giám sát và metric có ích

Một hệ thống WebSocket có thể ghi các chỉ số sau:

| Metric | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| `websocket_connections_open` | count | Số kết nối hiện được coi là đang mở |
| `websocket_ping_sent_total` | count | Tổng Ping đã được khởi phát |
| `websocket_pong_matched_total` | count | Pong có nonce khớp probe |
| `websocket_pong_unmatched_total` | count | Pong không khớp hoặc unsolicited |
| `websocket_heartbeat_timeout_total` | count | Số probe quá deadline |
| `websocket_rtt_ms` | histogram | Phân phối RTT đã đo |
| `websocket_close_total{reason}` | count | Số lần đóng theo nhóm nguyên nhân |
| `websocket_reconnect_attempt_total` | count | Số lần thử kết nối lại |
| `websocket_send_failure_total` | count | Các future gửi Ping/text/binary hoàn tất lỗi |

Đây là **tên metric minh họa**, không phải tên bắt buộc của Java API. Nếu có nhãn `reason` hoặc `endpoint`, dùng tập giá trị hữu hạn để tránh quá nhiều time series. Không ghi nguyên ping payload nếu nó mang định danh nhạy cảm; tốt nhất nonce là số vô nghĩa về nghiệp vụ.

Để vận hành tốt, cần quan sát cùng lúc **RTT, timeout ratio, reconnect rate và business error rate**. Ping vẫn thành công nhưng tỉ lệ lỗi business tăng có thể do backend phía sau, không phải kết nối WebSocket.

## 16. Bảng tình huống lỗi phổ biến

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi `sendPing` và coi kết nối khỏe ngay | Send future không chờ Pong | Chờ `onPong` có nonce đúng |
| Gọi `sendPong` trong mọi `onPing` | Không biết Java WebSocket tự Pong | Để implementation tự phản hồi; tránh gửi dư |
| Listener chỉ nhận Pong đầu tiên rồi im lặng | Quên `request(1)` sau khi override callback | Quản lý receive demand đúng |
| Pong có nonce khác vẫn xóa timeout | Không đối chiếu payload | Chỉ clear pending khi nonce khớp |
| Gửi Ping liên tục dù một probe chưa được trả lời | Không có state awaiting | Cho tối đa một probe outstanding theo policy |
| `sendPing` thất bại `IllegalStateException` | Một Ping/Pong send operation còn pending | Chờ future gửi trước kết thúc; không gửi trùng |
| Payload 126+ byte | Control frame giới hạn 125 byte | Dùng 8–16 byte nonce hoặc payload nhỏ |
| Đếm `capacity()` thay `remaining()` | Buffer có position/limit khác | Kiểm tra `remaining()` |
| Sửa ByteBuffer ngay sau `sendPing` | Send chưa hoàn tất | Không truy cập/sửa buffer trước khi future hoàn tất |
| Giữ buffer `onPong` sau khi callback complete | Java có thể reclaim buffer | Copy bytes trong callback |
| Dùng wall clock cho RTT | Đồng hồ hệ thống có thể đổi | Dùng `System.nanoTime()` |
| Kiểm tra `isInputClosed()==false` rồi khẳng định peer sống | Trạng thái local không phát hiện mọi silent disconnect | Dùng heartbeat hoặc application traffic |
| Timeout quá thấp | Mạng chậm, GC pause, scheduler trễ | Chọn interval/grace từ dữ liệu thực tế |
| Cancel WebSocket nhưng tự reconnect vô hạn | Không có cờ user-requested close | Phân biệt stop có chủ đích và lỗi kết nối |
| Heartbeat của kết nối cũ cập nhật kết nối mới | Không có generation ID | Gắn state theo connection instance/generation |
| Ping khi output đóng | WebSocket không thể gửi | Kiểm tra lifecycle, xử lý future lỗi |
| Chỉ có Pong thì coi backend sẵn sàng | Pong đo protocol liveness | Nếu cần, thêm health signal cấp ứng dụng |
| Browser JS gọi `sendPing` rồi lỗi | Browser WebSocket API không có method đó | Dùng heartbeat text/application-level |
| Unit test dựa vào số ms thực tế | Scheduler và OS không quyết định | Dùng fake clock; test loopback cho protocol |

## 17. Bài tập thực hành

### Bài 1 — Hiểu hai hướng Ping/Pong

Chạy `WebSocketPingLoopbackDemo.java`. Nêu rõ:
- Server gửi Ping nào, client tự gửi Pong nào?
- Client gửi Ping nào, server trả Pong nào?
- Vì sao trong `Seen.onPing` không có `socket.sendPong` mà server vẫn nhận `Pong`?

### Bài 2 — Kiểm tra payload giới hạn

Tạo `ByteBuffer` chứa 125 byte và 126 byte; thử `sendPing` trong một kết nối loopback. Quan sát future thành công/thất bại. Giải thích vì sao phải tính từ `position` tới `limit` và vì sao `sendPing` có thể thất bại với `IllegalArgumentException`.

### Bài 3 — Quên `request(1)`

Trong listener của ví dụ loopback, thử bỏ `socket.request(1)` tại `onPong`. Dự đoán vấn đề nếu server tiếp tục gửi nhiều Pong/Ping; vì sao kết quả callback không nhất thiết được gọi dù dữ liệu mạng đã đến? Khôi phục demand để code hoạt động liên tục.

### Bài 4 — Heartbeat có nonce

Chạy `HeartbeatLogicDemo.java`. Đổi nonce Pong sai thành nonce đúng, kiểm tra `onPong`. Thử issue hai probe liên tiếp trước khi Pong về: tracker phải ném `IllegalStateException` vì policy chỉ một probe đang chờ.

### Bài 5 — Đồng hồ và timeout

Cho heartbeat interval 30 giây, Pong timeout 10 giây. Viết unit test với fake clock cho ba kịch bản: Pong đúng sau 5 giây, Pong sai sau 5 giây, không có Pong tới 11 giây. Không dùng `Thread.sleep` trong unit test.

### Bài 6 — User đóng lúc scheduler đang chuẩn bị Ping

Thiết kế một transition atomic từ `OPEN` sang `CLOSING`; scheduler đang chờ phải bỏ qua lần gửi mới. Giải thích cách bạn ngăn `onPong` muộn của connection cũ cập nhật connection vừa tạo lại.

### Bài 7 — Khi nào cần application heartbeat?

Một WebSocket nhận Pong đúng nhưng backend của ứng dụng không xử lý được lệnh. Đề xuất một message cấp ứng dụng có request ID và status, thời hạn riêng, tránh nhầm nó với frame Ping `0x9`. Giải thích browser JavaScript theo dõi liveness ở cấp ứng dụng ra sao.

### Checklist hoàn thành

- [ ] Phân biệt WebSocket control Ping (`0x9`), Pong (`0xA`), Close (`0x8`).
- [ ] Biết payload control tối đa 125 byte và Pong phản hồi phải mang cùng bytes.
- [ ] Biết Java 11 tự trả Pong khi nhận Ping; `sendPong` thủ công thường không cần.
- [ ] Phân biệt future `sendPing` hoàn tất với `onPong` nhận phản hồi.
- [ ] Hiểu `request(1)` duy trì receive demand.
- [ ] Biết xử lý `ByteBuffer` đúng `remaining()` và vòng đời callback.
- [ ] Thiết kế heartbeat với nonce, một probe chờ, RTT và deadline dùng `System.nanoTime()`.
- [ ] Phân loại `onError`, `onClose`, timeout và hành động đóng/hủy có chủ đích.
- [ ] Không suy ra nghiệp vụ khỏe chỉ từ Pong hoặc `isInputClosed() == false`.
- [ ] Đã chạy hai chương trình Java 11 và đối chiếu stdout.

## 18. Tài liệu chính thức còn áp dụng

1. [Java SE 11 — WebSocket](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html): `sendPing`, `sendPong`, `sendClose`, `abort`, `request`, trạng thái input/output và phản hồi Ping tự động.
2. [Java SE 11 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): `onOpen`, `onPing`, `onPong`, `onError`, `onClose` và quyền sử dụng `ByteBuffer`.
3. [Java SE 11 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): kết nối qua `buildAsync`, `connectTimeout` và cấu hình handshake.
4. [Java SE 11 — ByteBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html): `remaining`, `position`, `limit`, `duplicate`.
5. [Java SE 11 — CompletableFuture](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html): theo dõi send completion, timeout, lỗi bất đồng bộ.
6. [Java SE 11 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): chạy heartbeat theo chu kỳ, hủy timer và quản lý executor.
7. [RFC 6455 — WebSocket Protocol, Section 5.5](https://www.rfc-editor.org/rfc/rfc6455#section-5.5): Ping/Pong/Close control frame, độ dài 125 byte, payload phản hồi, unsolicited Pong.
8. [Java SE 25 — WebSocket](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/WebSocket.html): xác nhận Java WebSocket client chuẩn vẫn có trên JDK LTS hiện đại.

**Nguyên tắc áp dụng:** dùng `sendPing` để **gửi một probe**, nhưng chỉ xác nhận probe thành công khi **`onPong` trả đúng nonce trong thời hạn**. Java 11 tự gửi Pong khi nhận Ping; ứng dụng cần quản lý receive demand, buffer, timer, lỗi và vòng đời kết nối. Một Pong thành công là tín hiệu WebSocket liveness tại thời điểm kiểm tra — **không** phải bảo đảm ứng dụng phía sau hoạt động đúng hoặc kết nối sẽ sống mãi.