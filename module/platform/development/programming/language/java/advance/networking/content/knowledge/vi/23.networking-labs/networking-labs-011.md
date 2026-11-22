# Kiểm chứng phân mảnh WebSocket message và điều tiết nhận trong Java 17 client

## 1. Thí nghiệm cần chứng minh điều gì?

Khi một server WebSocket gửi một **thông điệp text bị chia thành nhiều frames**, client Java có thể nhận các phần dữ liệu bằng `WebSocket.Listener.onText(...)`. Nhưng **frame**, **message**, **callback** và **TCP packet** không phải cùng một khái niệm. Bên cạnh việc ghép đúng message, client phải điều khiển việc nhận bằng `WebSocket.request(n)` để không cho callback chạy vượt khả năng xử lý.

Trong bài này, ta tạo một server **chỉ dùng để kiểm chứng** chạy trên `127.0.0.1`, gửi một message `Hello Java` trong **ba frames**, sau đó gửi message thứ hai `next` và Close code `1000`. Client sử dụng `java.net.http.WebSocket` chuẩn của **JDK 17+**; Listener cố ý **không** gọi `request` trong `onOpen`. Sau khi server gửi xong, ta kiểm tra:

1. Chưa cấp receive demand: **0 lần `onText`**.
2. Cấp `request(1)`: đúng **một receive callback** được phép phát.
3. Cấp tiếp demand: callback parts ghép thành **`Hello Java`**, không bị trộn với message mới **`next`**.
4. Client nhận `onClose` code **1000** và server quan sát Close reply của client.
5. **Không khẳng định “ba frames tạo ba callbacks”**: JDK WebSocket API không có cam kết 1:1 giữa frame và callback.

Kết quả kiểm thử của chương trình hoàn chỉnh:

~~~text
without_request=0
after_request_one=1
fragmented_message=Hello Java
next_message=next
close=1000
~~~

Đây là một **thực nghiệm kiểm chứng hợp đồng API**, không phải chương trình benchmark throughput. Phần server raw socket chỉ dùng loopback để kiểm soát chính xác các bytes wire-level và không đủ an toàn để đưa ra mạng công cộng.

## 2. Bốn lớp dữ liệu phải phân biệt

~~~text
Ứng dụng muốn gửi một logical text MESSAGE:
                     "Hello Java"
                           |
                  WebSocket framing
                           |
            +--------------+-------------+
            |              |             |
     TEXT FIN=0       CONT FIN=0    CONT FIN=1
         "Hel"             "lo "        "Java"
            |              |             |
            +--------------+-------------+
                           |
                       TCP bytes
             (không giữ ranh giới write/read)
                           |
                    JDK WebSocket client
                           |
      onText(ws, part, last=false hoặc true)
                           |
         ghép các part tới lần last=true
                           |
                  Một message "Hello Java"
~~~

**TCP:** là byte stream có thứ tự, không biết khái niệm WebSocket message. Một lần `Socket.read(buffer)` có thể lấy một phần frame, nhiều frames hoặc chỉ vài bytes. Không thể coi một read là một frame.

**WebSocket frame:** chứa bit FIN, opcode, payload length, masking metadata và payload bytes. Một message có thể là một frame hoặc nhiều frames. Frame boundaries là chi tiết của RFC 6455.

**WebSocket message:** đơn vị text/binary logic. `Hello Java` là một message dù server cố tình dùng ba frames. Message tiếp theo `next` phải được tách riêng.

**Listener callback:** mỗi lần JDK gọi `onText` hoặc `onBinary` có thể đưa một **phần hoặc toàn bộ logical message**. Ranh giới các lần callback không được hứa giống frame boundaries. Dựa vào `boolean last` để biết message hoàn tất.

### 2.1. Mã byte đầu của thí nghiệm

| Frame | Byte đầu | Opcode | FIN | Payload | Ý nghĩa |
| --- | --- | --- | --- | --- | --- |
| 1 | `0x01` | Text `0x1` | 0 | `Hel` | Mở message đầu |
| 2 | `0x00` | Continuation `0x0` | 0 | `lo ` | Cùng message |
| 3 | `0x80` | Continuation `0x0` | 1 | `Java` | Kết thúc message đầu |
| 4 | `0x81` | Text `0x1` | 1 | `next` | Một message mới |
| 5 | `0x88` | Close `0x8` | 1 | `0x03, 0xE8` | Đóng bình thường, code 1000 |

Thí nghiệm viết các payload nhỏ **ASCII** để dễ xem byte. Nếu dữ liệu UTF-8 đa byte nằm vắt qua ranh giới frames, WebSocket implementation chuẩn phải xử lý đúng logical text. Không tự giải mã riêng từng phần raw UTF-8 bằng `new String(payloadPart, UTF_8)` rồi nối: có thể phá ký tự chia đôi.

### 2.2. Quy tắc RFC 6455 khi phân mảnh

- Một fragmented message bắt đầu bằng Text hoặc Binary frame có `FIN=0`.
- Những phần kế tiếp dùng **Continuation opcode 0x0**; frame cuối có `FIN=1`.
- Không xen một data message khác vào giữa fragments của message đang mở, trừ trường hợp extension đã thương lượng quy định khác.
- **Control frames** như Ping, Pong và Close có thể xen giữa fragments, nhưng bản thân control frame **không phân mảnh**, payload không quá **125 bytes**.
- Client-to-server frames **phải mask**, server-to-client frames **không được mask**. Masking không phải encryption và không thay `wss://`/TLS.
- Một frame có thể đến qua nhiều TCP reads. Người nhận RFC-compliant cần parser theo độ dài/flags và giới hạn tài nguyên.
- Các extensions có thể thay cách diễn giải framing; tránh giả định không có compression nếu đã đàm phán extension.

**Không phân tích JSON trên từng wire frame**: JSON message cần được ghép hoàn chỉnh trước khi parse, trừ khi ứng dụng thiết kế một streaming format riêng có parser phù hợp.

## 3. Hợp đồng nhận dữ liệu của `java.net.http.WebSocket`

JDK 17 cung cấp **WebSocket client API**, không cung cấp một `java.net.http.WebSocketServer` cấp cao tương ứng. Client được tạo bằng:

~~~java
WebSocket ws = HttpClient.newHttpClient()
        .newWebSocketBuilder()
        .buildAsync(URI.create("wss://example.test/events"), listener)
        .join();
~~~

Đây là **fragment minh họa** với `listener` đã khởi tạo và imports `java.net.URI`, `java.net.http.*`, không phải chương trình standalone. Với ứng dụng thực, ưu tiên futures/callbacks bất đồng bộ hơn việc block thread UI/event loop bằng `join()`.

`WebSocket.Listener` nhận `onOpen`, `onText`, `onBinary`, `onPing`, `onPong`, `onClose` và `onError`. Trong đó, **`onText` và `onBinary` đều có tham số `last`** — cho biết callback hiện tại có kết thúc **logical message** hay không.

### 3.1. Receive counter ban đầu bằng 0

Theo Java 17 WebSocket API, mỗi WebSocket có một **receive invocation counter**:

- Khi mới tạo: counter = **0**.
- `request(n)` với `n > 0`: tăng counter tối đa n lượt receive callback.
- Mỗi lần JDK gọi một receive method: counter giảm đi 1.
- Counter bằng 0: JDK **không** gọi thêm các receive methods được điều tiết.
- `request(0)` hoặc số âm ném `IllegalArgumentException`.

Các receive methods được tính demand là `onText`, `onBinary`, `onPing`, `onPong`, **`onClose`**. `onOpen` và `onError` **không phải** receive methods; `onError` có thể xảy ra ngay cả khi demand = 0.

~~~text
request(1) -> tối đa một callback receive, KHÔNG phải một message.
request(2) -> tối đa hai callbacks receive, có thể gồm onPing + onText.
request(1) -> nếu onText(..., last=false), phần sau cần demand tiếp.
~~~

Nếu server gửi một message bị phân mảnh và client chỉ cấp 1 demand, callback đầu có thể có `last=false`; client chưa nhận message hoàn chỉnh, **dù server có thể đã gửi toàn bộ bytes**.

### 3.2. Default `onOpen` tự cấp một demand

Điểm dễ làm hỏng thí nghiệm: `WebSocket.Listener.onOpen` mặc định **gọi `ws.request(1)`**. Nếu bạn không override `onOpen`, client đã cho phép một receive callback ngay khi kết nối. Vì vậy chương trình chủ đích:

~~~java
@Override
public void onOpen(WebSocket ws) {
    // Không request() để đo trạng thái demand ban đầu = 0.
}
~~~

Ứng dụng bình thường nên cấp demand để bắt đầu nhận; ở đây ta tạm chưa cấp **chỉ nhằm kiểm thử**.

### 3.3. Default `onText` cũng tự cấp thêm một demand

Nếu không override `onText`, implementation mặc định của Listener sẽ gọi `ws.request(1)` và trả `null`. Muốn chứng minh `request(1)` chỉ cho phép **một** callback, phải override `onText` và **không tự request tiếp** trước khi main bật `autoDemand`.

### 3.4. `CompletionStage` không phải nhận thêm credit

`onText(...)` trả `CompletionStage<?>` hoặc `null`. Stage cho WebSocket biết **khi nào dữ liệu callback không còn được listener sử dụng** và có thể được reclaim; **không thay thế receive counter**. Theo JDK docs, Stage completion và số receive callbacks là **hai cơ chế độc lập**: trả future chưa completed không có nghĩa JDK chắc chắn sẽ không gọi callback tiếp khi demand còn.

Với `return null`, callback báo dữ liệu có thể reclaim ngay; vì vậy phải **copy** `CharSequence` hoặc dữ liệu `ByteBuffer` cần dùng lâu trước khi return. Không lưu reference `part` vào queue rồi xử lý sau khi Stage đã hoàn thành.

### 3.5. Listener invocation được tuần tự hóa theo một WebSocket

JDK gọi Listener methods cho **một WebSocket** theo thứ tự, không re-entrant. Một bộ `StringBuilder` per connection có thể ghép parts theo thứ tự callback, nhưng:

- Không chia sẻ một `StringBuilder` static giữa **nhiều WebSockets**.
- Đừng đọc/ghi biến plain mutable từ main trong khi Listener cập nhật ở callback thread mà thiếu visibility; dùng `CompletableFuture`, `AtomicInteger` hoặc đồng bộ.
- Đừng block callback nhiều giây để query database; chuyển message đã copy sang một bounded executor/queue và chỉ cấp thêm demand theo capacity.

## 4. Kế hoạch kiểm chứng để kết quả không phụ thuộc sleep

Thí nghiệm có hai thành phần: **server phát raw frames kiểm soát được**, và **JDK WebSocket client nhận callbacks**.

Server chạy trong thread riêng, bind `127.0.0.1` với port 0 (OS cấp port rảnh), nhận một WebSocket handshake tối giản. Sau khi trả `101 Switching Protocols` hợp lệ, server viết từng frame và `flush()`. Khi hoàn tất cả hai messages và Close, server gọi `framesSent.complete(null)`.

Client `buildAsync()` hoàn tất, chờ `framesSent` với deadline để chắc rằng server đã thực thi **lệnh write/flush frames** trước khi đọc counter. Không cần `Thread.sleep(200)` rồi đoán.

Khi `ws.request(1)`, Listener gọi `firstCallback.complete(null)` ở callback đầu. Main đợi future với deadline, rồi in count. Sau đó main bật `autoDemand` để `onText` cấp tiếp demand khi xử lý từng part, và đợi `message1`, `message2`, `closeCode`, `serverDone` với timeout.

| Thời điểm | Điều cần khẳng định | Không nên suy diễn |
| --- | --- | --- |
| Server đã flush, client chưa request | `textInvocations=0` | OS không hề nhận bytes |
| Main vừa request 1 và đợi callback | `textInvocations=1` | Client đã nhận một message hoàn chỉnh |
| Đã cấp tiếp receive demand | `Hello Java` đúng một message | JDK phải gọi `onText` đúng 3 lần |
| Message thứ hai hoàn tất | `next` riêng biệt | TCP packet thứ hai độc lập |
| Close nhận code 1000 | Close handshake thành công | DB transaction/app command đã commit |

`framesSent.complete` là tín hiệu **server-side Java code đã flush**, không phải ACK nghiệp vụ của client. Cách tách mốc này đặc biệt hữu ích khi điều tra “server bảo đã gửi nhưng listener chưa có callback”.

## 5. Chương trình Java 17+ chạy độc lập: `FragmentDemandExperiment.java`

**Lưu ý bảo mật:** code dưới đây chứa một **WebSocket server raw TCP tối giản chỉ để học RFC framing**. Nó không kiểm tra đầy đủ Upgrade headers/version/extensions/origin/auth, không có TLS/WSS, không có limits production, không xử lý fragmentation inbound tổng quát và không phục vụ nhiều clients. **Không triển khai raw server này lên Internet.** Trong hệ thống thật, dùng Jakarta WebSocket, Spring WebSocket, Jetty, Netty hoặc runtime tương thích.

**Phần client** trong chương trình là API `java.net.http.WebSocket` của JDK 17. Không phụ thuộc thư viện ngoài, không phụ thuộc Internet hoặc echo site công cộng.

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
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class FragmentDemandExperiment {
    record Frame(int opcode, byte[] bytes) {}

    static String readHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        int last4 = 0;

        for (int b; (b = in.read()) != -1;) {
            bytes.write(b);
            last4 = (last4 << 8) | b;
            if (bytes.size() > 8192) {
                throw new IOException("Header too large");
            }
            if (last4 == 0x0d0a0d0a) {
                return bytes.toString(
                        StandardCharsets.ISO_8859_1);
            }
        }
        throw new EOFException("Missing handshake");
    }

    static String header(String all, String name)
            throws IOException {
        for (String line : all.split("\r\n")) {
            int sep = line.indexOf(':');
            if (sep > 0 &&
                    line.substring(0, sep).trim()
                            .equalsIgnoreCase(name)) {
                return line.substring(sep + 1).trim();
            }
        }
        throw new IOException("Missing header: " + name);
    }

    static void sendServerFrame(
            OutputStream out, int byte1, byte[] payload)
            throws IOException {
        if (payload.length > 125) {
            throw new IOException(
                    "Experiment only supports short frames");
        }
        out.write(byte1);
        out.write(payload.length);
        out.write(payload);
        out.flush();
    }

    static Frame readClientFrame(InputStream in)
            throws IOException {
        int first = in.read();
        int second = in.read();
        if (first < 0 || second < 0) {
            throw new EOFException("Missing frame");
        }
        if ((second & 0x80) == 0) {
            throw new IOException("Client frame unmasked");
        }

        int n = second & 0x7f;
        if (n >= 126) {
            throw new IOException("Oversized frame");
        }
        byte[] mask = in.readNBytes(4);
        byte[] data = in.readNBytes(n);
        if (mask.length != 4 || data.length != n) {
            throw new EOFException("Truncated frame");
        }
        for (int i = 0; i < n; i++) {
            data[i] ^= mask[i & 3];
        }
        return new Frame(first & 15, data);
    }

    static void serve(
            ServerSocket listener,
            CompletableFuture<Void> framesSent,
            CompletableFuture<Void> finished) {

        try (Socket socket = listener.accept()) {
            socket.setSoTimeout(5000);
            InputStream in = socket.getInputStream();
            OutputStream out = socket.getOutputStream();

            String request = readHeaders(in);
            if (!request.startsWith("GET /lab HTTP/1.1\r\n")) {
                throw new IOException("Unexpected path");
            }

            String key = header(request, "Sec-WebSocket-Key");
            String input = key
                    + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
            String accept = Base64.getEncoder().encodeToString(
                    MessageDigest.getInstance("SHA-1")
                            .digest(input.getBytes(
                                    StandardCharsets.US_ASCII)));

            String response =
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept
                    + "\r\n\r\n";
            out.write(response.getBytes(
                    StandardCharsets.US_ASCII));
            out.flush();

            // Message đầu bị chia 3 frames.
            sendServerFrame(out, 0x01, "Hel".getBytes(
                    StandardCharsets.US_ASCII));  // TEXT FIN=0
            sendServerFrame(out, 0x00, "lo ".getBytes(
                    StandardCharsets.US_ASCII));  // CONT FIN=0
            sendServerFrame(out, 0x80, "Java".getBytes(
                    StandardCharsets.US_ASCII));  // CONT FIN=1

            // Message thứ hai là một frame text hoàn chỉnh.
            sendServerFrame(out, 0x81, "next".getBytes(
                    StandardCharsets.US_ASCII));  // TEXT FIN=1

            // WebSocket Close frame, status=1000.
            sendServerFrame(out, 0x88,
                    new byte[]{3, (byte) 232});

            framesSent.complete(null);

            // JDK client tự gửi masked Close reply khi xử lý onClose.
            Frame reply = readClientFrame(in);
            if (reply.opcode() != 8) {
                throw new IOException(
                        "Expected client's Close");
            }
            finished.complete(null);
        } catch (Throwable t) {
            framesSent.completeExceptionally(t);
            finished.completeExceptionally(t);
        }
    }

    static class ListenerImpl implements WebSocket.Listener {
        final AtomicInteger textInvocations =
                new AtomicInteger();
        final AtomicBoolean autoDemand =
                new AtomicBoolean(false);

        final CompletableFuture<Void> firstCallback =
                new CompletableFuture<>();
        final CompletableFuture<String> message1 =
                new CompletableFuture<>();
        final CompletableFuture<String> message2 =
                new CompletableFuture<>();
        final CompletableFuture<Integer> closeCode =
                new CompletableFuture<>();

        final StringBuilder text = new StringBuilder();
        int messagesDone;

        @Override
        public void onOpen(WebSocket ws) {
            // Không request: default onOpen sẽ tự request(1).
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket ws, CharSequence part, boolean last) {
            int current = textInvocations.incrementAndGet();

            text.append(part); // Copy trước khi callback hoàn tất.
            if (last) {
                String message = text.toString();
                text.setLength(0); // Reset giữa hai messages.

                if (messagesDone++ == 0) {
                    message1.complete(message);
                } else {
                    message2.complete(message);
                }
            }

            if (current == 1) {
                firstCallback.complete(null);
            }
            if (autoDemand.get()) {
                ws.request(1);
            }
            return null;
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket ws, int code, String reason) {
            closeCode.complete(code);
            return null;
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            firstCallback.completeExceptionally(error);
            message1.completeExceptionally(error);
            message2.completeExceptionally(error);
            closeCode.completeExceptionally(error);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1,
                InetAddress.getByName("127.0.0.1"))) {

            CompletableFuture<Void> framesSent =
                    new CompletableFuture<>();
            CompletableFuture<Void> serverDone =
                    new CompletableFuture<>();

            Thread server = new Thread(
                    () -> serve(listener, framesSent, serverDone),
                    "one-shot-websocket");
            server.setDaemon(true);
            server.start();

            ListenerImpl callbacks = new ListenerImpl();
            String target = "ws://127.0.0.1:"
                    + listener.getLocalPort() + "/lab";

            WebSocket ws = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .buildAsync(URI.create(target), callbacks)
                    .get(5, TimeUnit.SECONDS);

            // Server đã gửi/flush, nhưng Listener chưa có demand.
            framesSent.get(5, TimeUnit.SECONDS);
            System.out.println("without_request="
                    + callbacks.textInvocations.get());

            ws.request(1);
            callbacks.firstCallback.get(5, TimeUnit.SECONDS);
            System.out.println("after_request_one="
                    + callbacks.textInvocations.get());

            // Sau phép đo, cho Listener nhận tiếp.
            callbacks.autoDemand.set(true);
            ws.request(1);

            System.out.println("fragmented_message="
                    + callbacks.message1.get(
                            5, TimeUnit.SECONDS));
            System.out.println("next_message="
                    + callbacks.message2.get(
                            5, TimeUnit.SECONDS));
            System.out.println("close="
                    + callbacks.closeCode.get(
                            5, TimeUnit.SECONDS));

            serverDone.get(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Lưu file đúng tên class, biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 FragmentDemandExperiment.java
java FragmentDemandExperiment
~~~

**Stdout đã kiểm tra trực tiếp với Java 17 JShell:**

~~~text
without_request=0
after_request_one=1
fragmented_message=Hello Java
next_message=next
close=1000
~~~

### 5.1. Ý nghĩa từng dòng

**`without_request=0`:** server đã thực hiện toàn bộ send/flush các frames và Close; Listener của client chưa cấp receive demand. Không có `onText` callback nào được phát. **Không thể suy diễn** rằng network chưa nhận bytes; có thể dữ liệu đã nằm trong TCP buffers/JDK internal buffers.

**`after_request_one=1`:** main gọi đúng `ws.request(1)`, Listener ghi nhận callback đầu và không request thêm khi `autoDemand=false`. Điều này đo **một receive invocation**, chứ không đo “một text message” hoặc “một frame”.

**`fragmented_message=Hello Java`:** các callback parts được ghép cho đến `last=true`. Vì server gửi `Hel` + `lo ` + `Java` như **một logical text message**, client phải tái lập đúng nội dung.

**`next_message=next`:** sau khi message đầu hoàn tất, Listener reset `StringBuilder`. Text message sau không bị nối nhầm vào trước.

**`close=1000`:** Listener nhận Close code 1000 khi receive demand tiếp tục. Server cũng kiểm tra có masked Close reply từ client, rồi hoàn thành `serverDone`.

### 5.2. Tính xác định và giới hạn

Code không dựa vào `Thread.sleep` để đoán thời điểm server gửi. `framesSent` hoàn thành khi server đã flush; `firstCallback` là mốc callback đầu; futures đều dùng `get(..., TimeUnit.SECONDS)` để fail fast. Điều đó không biến network/OS trở thành một hệ thời gian thực, nhưng loại được các assertion phụ thuộc sleep và lịch scheduler đơn giản.

Demo **không in số callbacks của message1** vì số lượng đó không được RFC/JDK API cố định thành số frames. Nếu muốn đo để học, thêm log trong `onText` cho `last` và `part.length()` — coi output là **diagnostic không cố định**, tuyệt đối không viết test assert số lần `onText` = 3.

### 5.3. Vì sao server chỉ dùng loopback?

Server raw `ServerSocket` không phải một WebSocket server framework chuẩn. Nó chỉ đọc HTTP Upgrade header tối thiểu, tính `Sec-WebSocket-Accept` bằng SHA-1 theo công thức RFC 6455, phát frames nhỏ không mask (đúng chiều server → client), nhận một Close frame đã mask (đúng chiều client → server). Nó **không** xử lý đầy đủ HTTP headers/Origin/session/TLS, extended length/fragmentation inbound, UTF-8 validation, Ping/Pong, compression, max message size, nhiều clients hay chống abuse. Không dùng demo làm endpoint Internet.

## 6. Thí nghiệm biến thể: quan sát `last`

Thay dòng tăng đếm trong `onText`:

~~~java
int current = textInvocations.incrementAndGet();
System.err.println(
        "callback=" + current +
        " chars=" + part.length() +
        " last=" + last);
~~~

Đây là **patch minh họa**; không thêm lần increment thứ hai. Kết quả có thể cho thấy `last=false` ở một số parts và `last=true` tại message boundary. Nhưng không có bảo đảm số callbacks/char lengths tương ứng từng frame do server phát, ngay cả khi input wire giống nhau.

Khi kiểm chứng message đúng, luôn hỏi:

- Có callback cuối cho mỗi logical message không (`last=true`)?
- Buffer có bị reset sau message hoàn chỉnh không?
- Có trộn message của hai sessions không?
- Có xử lý text message bị chia thành nhiều callbacks không?
- Có max message length và timeout khi peer không kết thúc fragments không?

Một parser không nên gọi `JSON.parse` hay decode nghiệp vụ ngay trong `onText(last=false)` nếu input chưa tạo thành một JSON document trọn vẹn. Có thể dùng streaming parser theo thiết kế riêng, nhưng phải phân biệt rõ ranh giới JSON/message.

## 7. Binary messages: dùng `onBinary` và ByteBuffer đúng ownership

Khái niệm tương tự áp dụng cho binary. Nếu server phát:

~~~text
BINARY FIN=0 bytes [01 02]
CONT   FIN=1 bytes [03 04]
=> một logical binary message [01 02 03 04]
~~~

JDK client gọi `onBinary(WebSocket, ByteBuffer data, boolean last)` để nhận parts. Dữ liệu nằm từ `data.position()` đến `data.limit()`, không phải luôn toàn bộ backing array. Không dùng `data.array()` tùy tiện vì direct/read-only ByteBuffer có thể không có array truy cập được.

Một handler minh họa (không độc lập):

~~~java
final ByteArrayOutputStream assembled = new ByteArrayOutputStream();

@Override
public CompletionStage<?> onBinary(
        WebSocket ws, ByteBuffer part, boolean last) {

    byte[] copy = new byte[part.remaining()];
    part.get(copy); // Copy trước khi hoàn tất callback.
    assembled.writeBytes(copy);

    if (assembled.size() > MAX_BINARY_BYTES) {
        ws.abort(); // Chỉ minh họa policy khi quá giới hạn.
        return null;
    }
    if (last) {
        byte[] whole = assembled.toByteArray();
        assembled.reset();
        handleCompleteBinary(whole);
    }

    ws.request(1);
    return null;
}
~~~

Đoạn trên yêu cầu `MAX_BINARY_BYTES`, `handleCompleteBinary` và imports thích hợp do ứng dụng định nghĩa. `abort` là cách đóng mạnh của client, không phải response nghiệp vụ. Trong production, chọn Close/error policy phù hợp, copy an toàn và kiểm soát queued bytes.

### 7.1. Unicode UTF-8 bị chia giữa các frames

Một text frame có thể kết thúc ở giữa mã UTF-8 nhiều byte. Nếu bạn viết raw server parser và decode từng frame thành `String` riêng, rất dễ tạo ký tự `�` rồi ghép sai. `java.net.http.WebSocket` giải mã text hợp lệ và giao `CharSequence` có UTF-16 hợp lệ theo API. Bài thực nghiệm đang test ASCII cho stdout dễ đọc; mở rộng kiểm thử bằng message chứa `Tiếng Việt 😊` bị split raw bytes tại bất kỳ vị trí nào, so sánh logical message hoàn chỉnh. Đừng hứa mỗi Unicode code point sẽ nằm gọn trong một onText callback.

## 8. Control frames: Ping/Pong cũng tiêu thụ receive demand

Một fragmented message có thể có **Ping** ở giữa:

~~~text
TEXT FIN=0 "Hel"
PING FIN=1 "x"
CONT FIN=0 "lo "
CONT FIN=1 "Java"
~~~

`onPing` cũng thuộc receive methods tính demand. Nếu bạn cấp `request(2)`, có thể nhận một `onText` và một `onPing`, chứ **không chắc** có hai `onText`. Server demo chính cố ý không gửi Ping để phép đo một demand đơn giản.

Ví dụ thêm onPing cho listener (fragment):

~~~java
@Override
public CompletionStage<?> onPing(WebSocket ws, ByteBuffer data) {
    // Java WebSocket implementation tự trả Pong theo hợp đồng API.
    ws.request(1);
    return null;
}
~~~

Theo Java 17 Listener API, WebSocket implementation tự phát Pong đáp lại Ping theo quy tắc; thường không cần tự gọi `sendPong` để phản hồi Ping. Phải copy ByteBuffer nếu sử dụng sau khi Stage hoàn thành.

**onClose cũng tiêu thụ demand**. Khi tạm pause nhận, nếu peer gửi Close, callback `onClose` có thể chưa được gọi cho tới khi có demand. Ngược lại `onError` có thể được gọi mà không cần demand, vì đó là callback báo lỗi/lifecycle chứ không phải receive callback.

### 8.1. Khi `request(1)` “không thấy” onText

Không kết luận server không gửi khi chưa quan sát:

- `onOpen` đã chạy chưa?
- Listener có cấp receive demand hoặc vô tình dùng default `onOpen` không?
- Có Ping/Pong/Close tiêu thụ demand trước text không?
- Có `onError` xảy ra? Kết nối có bị đóng/abort không?
- Server đã gửi/flush data? Proxy có chuyển Upgrade/frames đúng?
- Text message có đang dở với `last=false` và client chưa request tiếp?

Đo nhiều tín hiệu trước khi chỉnh timeout hoặc viết vòng lặp `request(Long.MAX_VALUE)`.

## 9. Receive demand khác backpressure end-to-end

**`request(n)` điều tiết số lượt listener receive callback**, không trực tiếp là “server chỉ được phép gửi n frames”. Server có thể đã gửi hàng nghìn bytes, JDK có thể buffer, TCP window có thể thay đổi; consumer còn có thể chậm ở downstream worker queue.

~~~text
Producer server
      |
   TCP / kernel buffers
      |
   JDK WebSocket internal state
      |
   request(n) -> callbacks (onText/onBinary/...)
      |
   assembler giới hạn message length
      |
   bounded processing queue
      |
   DB, UI, parser hoặc business worker
~~~

Nếu callback đưa vô hạn messages vào một `ArrayList`, việc trước đó có `request(1)` cũng không giúp khi callback **luôn** gọi `request(1)` mới mà không đợi consumer tiêu thụ.

Một chính sách receive tốt:

1. **Chỉ nhận khi downstream có capacity** (queue chưa đầy, worker có slots).
2. **Copy message part** vào buffer có ownership rõ trước khi return/Stage complete.
3. Có **max assembled bytes/characters** và deadline nếu message bị fragment mãi.
4. Khi complete message, dispatch sang **bounded queue** theo schema; chỉ cấp demand tiếp khi có đủ capacity.
5. Nếu queue đầy, **tạm dừng cấp thêm `request`**, coalesce updates không thiết yếu, hoặc đóng connection theo policy. Không để chờ vô hạn và không bỏ data quan trọng âm thầm.
6. Nếu cần sender giảm tốc theo **business semantics**, thiết kế application-level credit/ACK window; WebSocket RFC không tự định nghĩa.

Ví dụ protocol ứng dụng có credit:

~~~json
{"type":"subscribe","channel":"prices","credit":10}
{"type":"ack","lastSeenSequence":101,"moreCredit":5}
~~~

Đây là **schema minh họa do ứng dụng tự đặt**, không phải format bắt buộc của WebSocket. Server phải tôn trọng credit, còn client phải có recovery/resubscribe logic nếu đứt mạng.

### 9.1. Stage, request và producer credit là ba thứ khác nhau

| Cơ chế | Ý nghĩa | Không bảo đảm |
| --- | --- | --- |
| `CompletionStage` từ `onText` | Dữ liệu callback được dùng xong, có thể reclaim | Thêm receive invocations |
| `ws.request(n)` | Cho phép n receive method invocations | Peer/server ngừng gửi ngay |
| Application `credit/ack` | Quy tắc do hai bên thiết kế để điều tiết nghiệp vụ | TCP packet reliability/transaction exactly-once tự động |
| TCP receive window | Flow control tầng transport | Parser/DB worker đủ capacity |

Đừng trả một never-completing `CompletableFuture` và nghĩ là đã có backpressure end-to-end. Nếu demand vẫn còn, callbacks có thể tiếp tục theo hợp đồng JDK; đồng thời bạn có thể làm implementation giữ lại buffers không cần thiết.

### 9.2. Timeout và cleanup

Nếu thiếu demand, `message1.get()` có thể chờ mãi ngay cả khi server đã hoàn thành sends. Dùng `get(5, TimeUnit.SECONDS)` trong test, theo dõi `onError`, hoàn thành futures exceptionally và có đường cleanup/`abort` khi buộc hủy.

Với production, xác định idle timeout, deadline cho message fragment chưa hoàn tất và max processing lag. Không giữ một WebSocket listener mở vô hạn trong trạng thái “tạm pause” mà không có cơ chế resume hoặc close.

## 10. Send fragmentation trong Java là câu chuyện khác

Để **client gửi** một text message thành hai phần:

~~~java
ws.sendText("Hel", false)
  .thenCompose(ready -> ready.sendText("lo Java", true));
~~~

Đây là fragment, `ws` đã là WebSocket đang kết nối. Tham số `last=false` đánh dấu một phần message, `last=true` kết thúc message. Gọi `thenCompose` để tuần tự hóa send, không phát chồng hai text send operations rồi hy vọng ordering tự nhiên.

`CompletableFuture` từ `sendText` hoàn thành theo **send operation** của client API; không có nghĩa peer đã lưu database hoặc ứng dụng server đã business ACK. Với side effects, thiết kế requestId/ACK/idempotency riêng.

Khi receive, JDK đã xử lý WebSocket frame parsing; bạn **không cần tự đọc raw opcode** bên trong `onText`. Chỉ cần ghép callback data tới `last=true` và parse business message.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Biện pháp |
| --- | --- | --- |
| Chỉ nhận callback đầu tiên | `onText` không request thêm, counter về 0 | `request(1)` theo capacity |
| Không nhận callback dù server đã gửi | Override `onOpen` mà không request | Kiểm tra demand và chủ đích pause |
| Test báo “3 frames phải 3 callbacks” thất bại | Nhầm ranh giới frame/callback | Assert logical message và cờ last |
| Parser JSON lỗi với `last=false` | Parse dữ liệu chưa hoàn tất | Ghép parts, giới hạn size, parse khi last=true |
| Message2 chứa dữ liệu message1 | Không reset assembler | `setLength(0)`/reset sau last |
| Gửi Unicode bị méo | Decode UTF-8 theo từng frame raw | Decode message đúng, dùng WebSocket API |
| `ByteBuffer.array()` ném exception | Buffer không có accessible backing array | Copy bằng `remaining` và `get` |
| Ứng dụng ngừng nhận Close | Không còn receive demand | Có liveness/deadline/cấp demand/abort |
| `onError` xảy ra khi counter 0 | onError không bị demand kiểm soát | Phân biệt lifecycle với receive |
| `request(1)` nhận Ping thay vì text | Control callbacks cũng trừ counter | Có onPing policy và request tiếp |
| Hàng đợi handler tăng mãi | Request tiếp ngay dù downstream quá tải | Bounded queue + credit/admission |
| OOM khi nhận message quá lớn | `StringBuilder`/ByteArrayOutputStream không giới hạn | Max message bytes và timeout |
| Async task đọc `CharSequence` sau callback | Dữ liệu đã reclaim | Copy trước khi Stage hoàn thành |
| Test sleep 100ms thỉnh thoảng fail | Đồng bộ dựa vào thời gian | Futures/latches + timeout |
| Client mất response dù send future thành công | Không có application ACK | RequestId/ACK/transaction status |
| Dùng server demo public | Thiếu RFC/TLS/auth/limits | Server framework tiêu chuẩn |

## 12. Mở rộng bộ test theo từng bất biến

**Case A — Một text message không phân mảnh.** Server gửi TEXT FIN=1 "hi"; client cần hoàn tất một message "hi". Không assert một TCP read.

**Case B — Text ba fragments.** Server gửi TEXT FIN=0 "Hel", CONT FIN=0 "lo ", CONT FIN=1 "Java"; client cần ghép ra "Hello Java", không dispatch trước `last=true`.

**Case C — Hai messages nối tiếp.** Sau message1, server gửi TEXT FIN=1 "next"; client cần tạo message2 riêng, không "Hello Javanext".

**Case D — Demand bằng không.** Override `onOpen` và `onText`; server đã flush, client chưa request; counter callback không được tăng. Khi `onError` xảy ra, quy tắc khác.

**Case E — Một receive credit.** Gọi `request(1)` và chờ callback đầu; không có receive callback thứ hai nếu listener không tự request.

**Case F — Resume.** Sau một callback đầu và pause, tiếp tục request; toàn bộ message và các events sau vẫn được xử lý theo contract.

**Case G — Ping giữa fragments.** Gửi Ping ở giữa Text/Continuation; xét rằng `onPing` cũng tiêu thụ demand và frame không làm hỏng message.

**Case H — Binary fragmented.** Server gửi binary FIN0 + continuation FIN1; client ghép bytes theo `position/limit`, không xử lý như UTF-8.

**Case I — UTF-8 tách đôi.** Gửi một ký tự Unicode đa byte qua hai frames và kiểm tra logical text nguyên vẹn. Với server demo hiện tại cần bổ sung raw payload assembly và validation theo RFC.

**Case J — Kích thước vượt giới hạn.** Peer gửi message phân mảnh rất lớn hoặc không đặt `last=true`. Client không được tích lũy không giới hạn, phải abort/close theo policy.

**Case K — Hủy khi receive đang pause.** Có deadline để thoát; `abort` cleanup khi không thể đóng mềm, futures hoàn tất exceptionally thay vì đợi mãi.

**Case L — Hai WebSockets đồng thời.** Mỗi session cần message assembler riêng, không trộn parts; dùng atomic/concurrency-aware metrics.

**Case M — Frame sai protocol.** Continuation không có initial Text/Binary, client frame không mask, control frame bị fragment: kiểm tra protocol error qua một test harness đúng chuẩn, không dùng server demo để đánh giá mọi RFC edge case.

**Case N — Hành vi chậm phía business.** Khi queue đầy, consumer phải giảm receive demand, giới hạn memory và có policy khi chậm kéo dài.

**Case O — Close code và business success.** Nhận Close 1000 không chứng minh command trước đó đã commit. Test ACK nghiệp vụ riêng.

**Case P — Test nhiều phiên bản JDK.** Giữ assert về messages, last và demand, không hard-code callback count per frame trên mọi build.

## 13. Bài tập có lời giải

### Bài 1 — Một callback cho ba frames có sai?

Server gửi một text message phân mảnh ba frames. Client chỉ nhận `onText(data="Hello Java", last=true)` một lần.

**Đáp án:** không thể gọi đó là sai. API không bảo đảm số callbacks đúng bằng frame count; logical message và `last` mới là điều ứng dụng dựa vào.

### Bài 2 — Client tự nhận dù chưa gọi `request` trong code

Bạn không override `onOpen` của Listener. Khi server gửi, client gọi `onText` một lần.

**Đáp án:** default `onOpen` đã gọi `webSocket.request(1)`. Muốn test demand 0 phải override.

### Bài 3 — Chỉ nhận `onText("Hel", false)`

Sau callback đầu, future message hoàn chỉnh không bao giờ hoàn thành dù server đã gửi các continuation frames.

**Đáp án:** có thể receiver đã hết demand. Gọi `request(1)` tiếp, quan sát các callbacks/last; không vội kết luận server không gửi.

### Bài 4 — Request hai callbacks nhưng nhận Ping rồi một text part

Có vi phạm vì không nhận đủ message?

**Đáp án:** không. Ping tiêu thụ receive demand như onText, và một onText part có thể chưa là message hoàn chỉnh; phải request thêm theo policy.

### Bài 5 — Trả future chậm để dừng nhận

Bạn `request(100)` và trả `CompletableFuture` chưa complete cho mọi onText. JDK có chắc không gọi thêm onText?

**Đáp án:** không. CompletionStage điều khiển lifetime data, không phải receive callback counter. Cần giới hạn demand và queue.

### Bài 6 — Parse JSON từng part

Server gửi `{"type":"ping"}` trong nhiều frames, client parse khi `last=false`.

**Đáp án:** sai ranh giới message. Ghép parts và parse khi complete, với size/time limit.

### Bài 7 — Giữ một `CharSequence` trong queue

Callback trả `null` nhưng lưu `data` tham chiếu để worker dùng sau.

**Đáp án:** không an toàn theo ownership contract. Copy immutable String/bytes trước khi trả Stage hoàn tất.

### Bài 8 — Close có thể chờ demand?

Server đã gửi Close, client pause receive và đợi onClose mãi.

**Đáp án:** `onClose` là receive callback được điều tiết, nên có thể chưa được gọi khi demand 0. Cần policy resume/timeout/abort.

### Bài 9 — 0 nghĩa là request dừng?

Client gọi `ws.request(0)` để pause.

**Đáp án:** sai: `request(n)` yêu cầu n dương, 0 ném `IllegalArgumentException`. Muốn tạm dừng thì **đừng cấp thêm demand** sau khi các credit đã cấp được tiêu thụ.

### Bài 10 — Hai threads dùng chung StringBuilder

Hai WebSocket sessions cùng gắn một listener instance có buffer chung.

**Đáp án:** có thể trộn message và race; JDK tuần tự hóa callback **trong cùng một WebSocket**, không hứa tuần tự xuyên hai WebSockets. Dùng per-session state hoặc concurrency-safe map.

### Bài 11 — Client dừng request nên server chắc chắn dừng gửi

Server vẫn ghi bytes sau khi client chưa có demand.

**Đáp án:** có thể bình thường. `request` điều khiển callbacks, không phải ứng dụng credit truyền tới server. TCP flow control chỉ tác động sau khi buffers/receive window cho phép; cần end-to-end protocol nếu muốn server dừng theo capacity.

### Bài 12 — Binary bị đọc nhầm

`onBinary` nhận ByteBuffer direct, code gọi `array()` rồi parse text.

**Đáp án:** `array()` có thể không được hỗ trợ; binary không có bảo đảm UTF-8. Copy `remaining` bytes và xử lý theo binary message schema.

## 14. Checklist hoàn thành thí nghiệm

- [ ] Đã đọc và phân biệt TCP byte stream, WebSocket frame, logical message và Listener callback?
- [ ] Đã biết ý nghĩa FIN/opcode của Text và Continuation frames?
- [ ] Đã biết Ping/Pong/Close có thể xen giữa data fragments?
- [ ] Đã biết masking khác nhau theo chiều client → server và server → client?
- [ ] Đã override `onOpen` nếu cần kiểm chứng **zero demand**?
- [ ] Đã override `onText` nếu cần điều khiển **có/không request tiếp**?
- [ ] Đã chứng minh `request(1)` cho phép một receive invocation, không phải một message?
- [ ] Đã ghép text parts tới `last=true` thay vì parse từng callback?
- [ ] Đã reset buffer sau message complete?
- [ ] Đã xác minh message1 `Hello Java` và message2 `next` không trộn lẫn?
- [ ] Đã quan sát Close code 1000 và biết nó khác business ACK?
- [ ] Đã phân biệt `onError` (không cần demand) và `onClose` (cần demand)?
- [ ] Đã dùng `CompletableFuture` với deadline thay vì sleep để xác định thời điểm?
- [ ] Đã biết `CompletionStage` returned không thay `request(n)`?
- [ ] Đã xử lý data ownership của CharSequence/ByteBuffer khi return Stage?
- [ ] Đã đặt message size/time limit và bounded consumer queue trong thiết kế production?
- [ ] Đã biết request demand không trực tiếp dừng remote server gửi bytes?
- [ ] Đã hiểu default `onOpen` và default `onText` tự request một callback?
- [ ] Đã ghi nhận test chưa hứa callback count = wire frame count?
- [ ] Đã biết raw server demo chỉ được chạy loopback, không dùng production?

**Kết luận:** Bài thực nghiệm chứng minh WebSocket text message có thể bị chia thành nhiều **wire frames** nhưng ứng dụng nên xử lý theo **message boundary `last=true`**. Trên JDK 17, `request(n)` cấp số **receive callback invocations**; ban đầu counter là 0, default `onOpen` lại tự request(1) nếu không override. Kết quả `without_request=0`, `after_request_one=1`, `fragmented_message=Hello Java` và `next_message=next` cho thấy vừa kiểm soát callback delivery vừa ghép message đúng. Với sản phẩm thực, kết hợp demand, bounded buffers, timeouts và application protocol; không suy diễn một callback bằng một frame hay dùng `request` thay toàn bộ backpressure.

## 15. Tài liệu tham khảo

- **RFC 6455 — The WebSocket Protocol, Section 5.4:** https://www.rfc-editor.org/rfc/rfc6455
- **Oracle Java 17 — WebSocket, request(long n):** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html
- **Oracle Java 17 — WebSocket.Listener:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html
- **Oracle Java 17 — WebSocket.Builder:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html
- **Oracle Java 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Oracle Java 17 — CompletableFuture:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html

Tài liệu RFC xác định wire framing, còn API Oracle xác định receive demand/callback/ownership. Bài test cố ý kiểm chứng phần **được bảo đảm bởi API**, không áp đặt số lần callback của một JDK implementation cho mọi phiên bản khác.