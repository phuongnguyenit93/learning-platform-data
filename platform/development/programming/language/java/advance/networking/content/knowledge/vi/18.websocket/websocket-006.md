# Cờ last và việc một thông điệp WebSocket được giao qua nhiều lần gọi

Trong Java 17+, WebSocket client của `java.net.http` cung cấp các callback `WebSocket.Listener.onText(WebSocket, CharSequence, boolean last)` và `onBinary(WebSocket, ByteBuffer, boolean last)`. Một **thông điệp WebSocket logic** có thể được nhận trong **một hoặc nhiều lần gọi** của các callback này. Tham số `last` cho biết **lần gọi hiện tại có mang phần cuối của thông điệp hay không**.

- **`last=false`:** dữ liệu vừa nhận chỉ là một phần của thông điệp. Còn phần tiếp theo, không được mặc nhiên parse/commit/ACK như một thông điệp hoàn chỉnh.
- **`last=true`:** phần nhận trong lần gọi này hoàn tất thông điệp logic. Sau khi thêm chính phần đó vào bộ đệm, ứng dụng có thể xử lý thông điệp hoàn chỉnh, rồi reset bộ ghép cho thông điệp sau.
- **Một thông điệp không đồng nghĩa một callback, một TCP read, hay một WebSocket frame.** Đừng viết chương trình dựa vào số callback giả định.
- **Cờ `last` ở phía gửi** cũng có trong `sendText(data,last)` và `sendBinary(data,last)`: false nghĩa còn phần sau của **cùng thông điệp**, true kết thúc thông điệp đó.
- **`webSocket.request(n)` đếm số lần gọi receive callback**, không đếm byte, frame hay thông điệp. Nếu chỉ gọi `request(1)` mà phần nhận đầu có `last=false`, phải tiếp tục cấp quyền nhận theo chính sách để lấy phần còn lại.

Bài học phân tích chính xác ranh giới thông điệp, cơ chế luồng callback và CompletionStage, cách ghép text/binary đúng ownership, giới hạn bộ nhớ, đóng kết nối, gửi phần tiếp theo đúng thứ tự, và có **một chương trình Java 17+ chạy được** qua WebSocket loopback để chứng minh cả text lẫn binary bị phân mảnh. Nội dung không phụ thuộc vào một server Internet cụ thể.

## 1. Tách biệt TCP, WebSocket frame và WebSocket message

WebSocket (RFC 6455) được đặt trên một kết nối TCP sau HTTP Upgrade hoặc cơ chế mở WebSocket phù hợp. TCP là **luồng byte**, không giữ ranh giới một lần viết của peer. WebSocket có **frame** với opcode, bit FIN và payload. Một thông điệp text hoặc binary có thể gồm nhiều frame; phía Java Listener nhận dữ liệu theo một chuỗi **callback** không được hứa tương ứng một-một với các frame.

~~~text
Thông điệp logic: "Hello Java"
           |
           v
WebSocket frame A: TEXT, FIN=0, payload="Hello "
WebSocket frame B: CONTINUATION, FIN=1, payload="Java"
           |
           v
      TCP byte stream
      (có thể chia/gộp trong các lần read)
           |
           v
WebSocket client trong JDK
           |
           v
Listener.onText(socket, data, last)
   - một hoặc nhiều callback tùy implementation
   - last=false: message chưa kết thúc
   - last=true : vừa nhận phần cuối
           |
           v
Thông điệp hoàn chỉnh: "Hello Java"
~~~

Sơ đồ minh họa một cặp frame cụ thể. **Không được khẳng định hai frame luôn tạo đúng hai lần `onText`.** Dù callback được chia như thế nào, đoạn nào có `last=true` là ranh giới kết thúc thông điệp.

| Ranh giới | Ai xử lý | Có phải ranh giới message ứng dụng? |
| --- | --- | --- |
| TCP packet / `SocketChannel.read()` | TCP/transport | Không, chỉ là bytes |
| WebSocket frame FIN và continuation | WebSocket protocol implementation | Cho biết kết thúc fragment/chuỗi frame, nhưng không phải callback count |
| `onText/onBinary(data,last)` | Java WebSocket.Listener | `last=true` là phần cuối của **một WebSocket message** |
| JSON/object/business event | Giao thức ứng dụng tự định nghĩa | Có thể là một WebSocket message nếu đã quy ước như vậy |

Không biến một lần callback thành một HTTP request hoặc một JSON object nếu chưa có ranh giới hợp lệ. Một WebSocket message có thể là lệnh nghiệp vụ, payload binary, hoặc một phần của protocol cấp cao hơn do ứng dụng quy định.

## 2. Đọc cờ last ở phía nhận

Các chữ ký của Java 17:

~~~java
// Fragment của một class implements WebSocket.Listener.
@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {
    socket.request(1);
    return null;
}

@Override
public CompletionStage<?> onBinary(
        WebSocket socket, ByteBuffer data, boolean last) {
    socket.request(1);
    return null;
}
~~~

Hai phương thức được gọi khi nhận dữ liệu text hoặc binary. Phần đầu vào của `onText` là `CharSequence` đã giải mã; phần đầu vào của `onBinary` là `ByteBuffer` có dữ liệu ở vùng `[position,limit)`. Boolean `last` được hiểu như nhau cho cả hai:

| Callback nhận | Ý nghĩa | Hành động hợp lý |
| --- | --- | --- |
| `onText(ws,"A",true)` | Trọn một text message chỉ trong callback này | Emit message "A", reset |
| `onText(ws,"Hel",false)` | Một đoạn đầu của text message | Copy/append; đợi tiếp |
| `onText(ws,"lo",true)` | Đoạn cuối của message hiện tại | Append, emit "Hello", reset |
| `onBinary(ws,part,false)` | Binary message còn dang dở | Copy/consume theo policy, giữ state |
| `onBinary(ws,part,true)` | Binary message vừa kết thúc | Hoàn tất message binary, reset |
| `onPing/onPong` | Control message riêng | Không reset text/binary accumulator |
| `onClose` | WebSocket input đóng | Đánh dấu incomplete message failed nếu chưa thấy last=true |

### Một lần gọi không bắt buộc là trọn thông điệp

~~~text
onText(ws, "Hel", false) -> giữ "Hel"
onText(ws, "lo",  true) -> hoàn thành "Hello"

onText(ws, "OK", true)  -> hoàn thành "OK"

onText(ws, "A", false)  -> giữ "A"
onText(ws, "B", false)  -> giữ "AB"
onText(ws, "C", true)   -> hoàn thành "ABC"
~~~

Ví dụ trên có **ba thông điệp** (Hello, OK, ABC) nhưng **sáu callback**. Nếu ứng dụng xử lý từng callback như một message, nó sẽ tạo ra các sự kiện thừa, parse JSON lỗi hoặc xử lý thiếu payload. Nếu ngược lại ứng dụng luôn chờ ít nhất hai callback, message `"OK"` nhận trong một lần lại bị treo dù `last=true`.

### Reset đúng thời điểm

Khi nhận `last=true`, hãy **thêm đoạn cuối trước**, rồi emit một message, rồi reset cho message kế. Reset buffer ở **mỗi callback** là sai vì làm mất phần đầu. Không reset sau `last=true` cũng sai vì sẽ dính nội dung hai thông điệp khác nhau.

## 3. Ghép text bằng StringBuilder trong Listener

Mẫu cho một WebSocket có state riêng:

~~~java
// Fragment Java 17+, trong class implements WebSocket.Listener.
private final StringBuilder partialText = new StringBuilder();

@Override
public void onOpen(WebSocket socket) {
    socket.request(1);
}

@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {
    partialText.append(data); // Copy ngay trong thời gian callback.

    if (last) {
        String whole = partialText.toString();
        partialText.setLength(0);
        handleWholeMessage(whole); // Helper do ứng dụng định nghĩa.
    }

    socket.request(1); // Xin lượt callback tiếp theo.
    return null;
}
~~~

Đây là **fragment**, không phải tệp Java độc lập; phải định nghĩa `handleWholeMessage()`. Mẫu này phù hợp khi message nhỏ, xử lý nội bộ nhanh và một Listener sở hữu state của một WebSocket. Cần bổ sung giới hạn kích thước và lỗi parser khi đưa vào production.

### Ví dụ JSON

Giả sử giao thức quy định **mỗi WebSocket text message = một JSON document**:

~~~text
Callback 1: data="{\\"name\\":"    last=false
Callback 2: data="\\"An\\"}"      last=true
Thông điệp hoàn chỉnh: {"name":"An"}
~~~

Chỉ khi đã ghép đầy đủ và `last=true` mới parse như một JSON document độc lập. Nếu muốn parse từng phần, phải dùng **streaming parser có trạng thái** và chỉ commit khi cấu trúc/validation đủ; không gọi một JSON parser thông thường trên fragment riêng lẻ.

### CharSequence là UTF-16, không phải byte TCP

Theo Javadoc, `onText` nhận một chuỗi UTF-16 hợp lệ. JVM/WebSocket implementation đã xử lý việc giải mã text WebSocket ở tầng protocol. `data.length()` là số **UTF-16 code units**, không phải số byte UTF-8 hay số grapheme Unicode. Một emoji có thể tốn hai code units, ký tự kết hợp có thể có nhiều code point. Ranh giới callback không phải ranh giới đối tượng JSON hay dòng text.

**Ownership:** Java có quyền thu hồi `CharSequence` được trao cho callback khi `CompletionStage` trả về đã hoàn tất. Nếu callback trả `null`, tương đương báo có thể thu hồi ngay. Đừng lưu chính tham chiếu `data` vào list rồi xử lý vài phút sau; dùng `data.toString()` hoặc `StringBuilder.append(data)` ngay trong callback.

## 4. Ghép binary từ ByteBuffer

Với `onBinary`, byte hữu ích nằm từ `data.position()` đến `data.limit()`. Dùng `remaining()` để lấy đúng số byte, không lấy `capacity()`, không mặc định `array()` tồn tại (direct/read-only buffers có thể không có backing array truy cập được).

~~~java
// Fragment: trong Listener, cần import ByteArrayOutputStream.
private final ByteArrayOutputStream pendingBinary =
        new ByteArrayOutputStream();

@Override
public CompletionStage<?> onBinary(
        WebSocket socket, ByteBuffer data, boolean last) {

    byte[] chunk = new byte[data.remaining()];
    data.get(chunk); // Đọc phần hiện tại, không đọc ngoài limit.
    pendingBinary.write(chunk, 0, chunk.length);

    if (last) {
        byte[] whole = pendingBinary.toByteArray();
        pendingBinary.reset();
        handleWholeBinary(whole);
    }

    socket.request(1);
    return null;
}
~~~

Mẫu trên chỉ hợp lệ cho message nhỏ **có giới hạn size**. Với binary file lớn, nên xử lý streaming sang sink/tệp có quota và chỉ đánh dấu hoàn thành file khi `last=true`, kiểm tra checksum/metadata theo protocol ứng dụng. Nếu tiếp tục tích lũy bằng `ByteArrayOutputStream` vô hạn, `request(1)` cũng không tránh được hết bộ nhớ.

Theo Javadoc, **không truy cập ByteBuffer do Listener cung cấp sau khi CompletionStage của callback hoàn tất**. Nếu chuyển nguyên buffer sang executor rồi lập tức trả null, worker có thể đọc dữ liệu đã bị implementation reclaim/reuse. Sửa bằng cách copy bytes trong callback hoặc giữ đúng CompletionStage còn pending tới khi downstream ngừng dùng buffer; vẫn phải quản lý thread-safety, thứ tự và backpressure.

## 5. request(n) đếm lần gọi receive, không đếm message

`WebSocket.request(long n)` tăng một counter cho **số lần WebSocket được phép gọi receive methods**. Counter ban đầu bằng 0. Các receive methods bao gồm `onText`, `onBinary`, `onPing`, `onPong`, `onClose`. `onOpen` và `onError` không được tính. `request(0)` hoặc `request(n<0)` ném `IllegalArgumentException`; không dùng 0 như một thao tác pause.

~~~text
socket.request(1)
       |
       v
onText("Hel", false)
       |
       +-- Dùng hết allowance của lần gọi này.
       +-- Text message chưa xong.
       |
Nếu không request tiếp: chưa có allowance cho onText tiếp.
       |
socket.request(1)
       |
       v
onText("lo", true)
       |
       +-- Emit trọn message "Hello"
~~~

Default `Listener.onOpen` gọi `request(1)`; nếu override `onOpen` như các ví dụ ở đây, phải chủ động gọi. Default `onText/onBinary/onPing/onPong` cũng request thêm một lần, nhưng khi bạn override, chính code của bạn chịu trách nhiệm cấp demand. Một Listener muốn nhận đủ message có thể gọi `request(1)` sau mỗi callback, hoặc dùng cửa sổ n lớn hơn với bounded processing.

### Ping có thể chen giữa các phần

RFC 6455 cho phép control frame chen giữa những frame của message đang phân mảnh:

~~~text
onText("Hel", false)
onPing(ByteBuffer(...))   # một control message riêng
onText("lo", true)        # text message "Hello" vừa hoàn tất
~~~

`onPing` là một lượt receive và có thể tiêu tốn allowance. Đừng reset accumulator text chỉ vì có Ping hoặc Pong. `onPing/onPong` không có cờ last vì control messages không bị phân mảnh như text/binary data messages. JDK WebSocket thường tự đáp Pong khi nhận Ping theo hợp đồng API, nên không tùy tiện gửi thêm Pong nếu không có yêu cầu protocol.

### Số byte không được giới hạn bởi request(1)

Một callback có thể chứa số byte/character đáng kể. `request(1)` chỉ giới hạn một **lần gọi**, không đặt hạn mức kích thước trong callback hoặc dung lượng JDK/OS buffers. Cần max-size per message, max concurrent sockets, queue byte budget và deadline cho partial message.

### CompletionStage không thay cho demand

`WebSocket.Listener.onText/onBinary/onPing/onPong` trả `CompletionStage<?>`. Stage này báo cho WebSocket **khi nào có thể reclaim data được giao**, không báo message hoàn chỉnh hay bao nhiêu lượt callback mới được phép gọi. Javadoc nêu một Stage chưa complete **không tự động ngăn callback mới** nếu ứng dụng đã cấp demand.

| Tín hiệu | Cho biết | Không cho biết |
| --- | --- | --- |
| `last=true` | Callback kết thúc message hiện tại | Socket đóng / server ACK nghiệp vụ |
| `request(1)` | Cho phép thêm tối đa một lần receive method | Một message hay một byte |
| `CompletionStage.complete` | Callback đã xong quyền sử dụng data | Toàn bộ message đã tới |
| `sendText(...).join()` | Lần gửi hoàn tất ở phía client | Server đã xử lý/commit nghiệp vụ |
| `onClose` | WebSocket input đang đóng | Message trước đó thiếu last có thể được chấp nhận |

Một cách thực hiện backpressure đúng khi xử lý fragment trên worker: **copy data**, gửi vào queue hữu hạn, chỉ `request(1)` khi worker xử lý xong/queue có chỗ. Không request hàng nghìn lượt rồi hy vọng việc trả Stage chậm sẽ thay thế queue control. Nếu offload nhiều fragment, cần giữ đúng thứ tự để không ghép message sai.

## 6. Gửi nhiều phần bằng sendText và sendBinary

Phía gửi, JDK có:

~~~java
CompletableFuture<WebSocket> sendText(
        CharSequence data, boolean last);

CompletableFuture<WebSocket> sendBinary(
        ByteBuffer data, boolean last);
~~~

Trong hai API, `last=false` biểu thị thông điệp outbound hiện tại còn phần tiếp theo; `last=true` biểu thị phần vừa gửi hoàn tất message. **Không dùng `last=true` như lệnh đóng WebSocket.**

### Gửi một text message bằng hai thao tác

~~~java
// Fragment Java 17+, socket là WebSocket đã kết nối.
socket.sendText("Hello ", false)
      .thenCompose(ws -> ws.sendText("Java", true))
      .join();
~~~

Chuỗi này gửi **một** text message “Hello Java”. `thenCompose` chờ thao tác trước hoàn tất trước khi gửi phần tiếp. Nếu cứ gọi hai `sendText` data operations đồng thời, thao tác có thể hoàn tất exceptionally vì còn send pending. Javadoc nêu `IllegalStateException` với sendText/sendBinary đang pending hoặc loại message trước đó còn dở.

### Gửi một binary message nhiều phần

~~~java
// Fragment Java 17+.
ByteBuffer first = ByteBuffer.wrap(new byte[] {1, 2});
ByteBuffer lastPart = ByteBuffer.wrap(new byte[] {3, 4});

socket.sendBinary(first, false)
      .thenCompose(ws -> ws.sendBinary(lastPart, true))
      .join();
~~~

Theo Javadoc, không được đọc/ghi/sửa buffer gửi trong lúc Future chưa hoàn tất; khi hoàn tất bình thường, buffer không còn remaining bytes. Buffer có trạng thái `position/limit`, không nhất thiết toàn bộ capacity đều được gửi.

### Không trộn loại khi message chưa kết thúc

~~~java
// Anti-pattern: text message chưa hoàn thành.
socket.sendText("partial", false)
      .thenCompose(ws ->
              ws.sendBinary(ByteBuffer.wrap(new byte[]{1}), true));
~~~

`sendBinary` có thể fail với `IllegalStateException` vì phần text trước chưa kết thúc message. Phải kết thúc text bằng `sendText(...,true)` rồi mới bắt đầu một binary message độc lập.

### last và close là hai việc khác nhau

- `sendText("A",true)`: đóng **message text** này, socket vẫn có thể nhận/gửi những message khác.
- `sendBinary(buffer,true)`: đóng **message binary** này.
- `sendClose(WebSocket.NORMAL_CLOSURE, "")`: khởi động đóng **WebSocket output** bằng Close control message; không phải data fragment.
- `abort()`: đóng input/output đột ngột.

Ví dụ hai message text rồi đóng:

~~~java
socket.sendText("one", true)
      .thenCompose(ws -> ws.sendText("two", true))
      .thenCompose(ws ->
              ws.sendClose(WebSocket.NORMAL_CLOSURE, ""))
      .join();
~~~

`sendText/sendBinary` Future thành công **không xác nhận người nhận đã xử lý nghiệp vụ**. Nếu cần chắc server đã lưu giao dịch, phải thiết kế ACK/message ID/timeout riêng.

## 7. Chương trình kiểm chứng WebSocket Java 17+ trên loopback

Ví dụ dùng **WebSocket client chuẩn của JDK** và một mini WebSocket server dựa trên `ServerSocket`, chỉ phục vụ bài học và chỉ bind `127.0.0.1`. Server thực hiện HTTP Upgrade RFC 6455, nhận các frame masked từ client, sau đó gửi một text message và một binary message **mỗi cái bị chia thành hai WebSocket frames**. Client ghép các callback theo cờ last, rồi orderly close.

**Không dùng mini server này trên Internet:** nó chỉ xử lý frame ngắn, một client, thiếu nhiều validations (extension, frame size dài, authentication, các lỗi giao thức khác) và không có TLS. Nó chỉ chứng minh những phần API cốt lõi, không phải server production.

Lưu toàn bộ dưới đây thành **`WebSocketLastDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
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
import java.time.Duration;
import java.util.Base64;
import java.util.HexFormat;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public class WebSocketLastDemo {
    private static final java.nio.charset.Charset ASCII =
            StandardCharsets.US_ASCII;
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;
    private static final String MAGIC =
            "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

    private static String readHeaders(InputStream in)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        int match = 0;

        while (bytes.size() < 16_384) {
            int c = in.read();
            if (c == -1) {
                throw new EOFException("EOF in handshake");
            }
            bytes.write(c);
            if (c == "\r\n\r\n".charAt(match)) {
                match++;
                if (match == 4) {
                    return bytes.toString(ASCII);
                }
            } else {
                match = c == '\r' ? 1 : 0;
            }
        }
        throw new IOException("Oversized HTTP headers");
    }

    // Server-to-client frames KHONG masked theo RFC 6455.
    private static void frame(
            OutputStream out, int opcode, boolean last,
            byte[] data) throws IOException {
        if (data.length > 125) {
            throw new IllegalArgumentException(
                    "Demo handles only short frames");
        }
        out.write((last ? 0x80 : 0x00) | opcode);
        out.write(data.length);
        out.write(data);
        out.flush();
    }

    private record Frame(
            int opcode, boolean last, byte[] payload) { }

    // Client-to-server frames PHAI masked theo RFC 6455.
    private static Frame readClientFrame(DataInputStream in)
            throws IOException {
        int first = in.readUnsignedByte();
        int second = in.readUnsignedByte();
        int len = second & 0x7f;

        if ((second & 0x80) == 0) {
            throw new IOException("Client frame must be masked");
        }
        if (len > 125) {
            throw new IOException("Demo only handles short frames");
        }

        byte[] key = in.readNBytes(4);
        byte[] data = in.readNBytes(len);
        if (key.length != 4 || data.length != len) {
            throw new EOFException();
        }
        for (int i = 0; i < data.length; i++) {
            data[i] ^= key[i % 4];
        }

        return new Frame(
                first & 0x0f,
                (first & 0x80) != 0,
                data);
    }

    private static String serve(ServerSocket listener)
            throws Exception {
        try (Socket socket = listener.accept()) {
            socket.setSoTimeout(5_000);
            InputStream input = socket.getInputStream();
            OutputStream output = socket.getOutputStream();

            // RFC 6455 HTTP opening handshake.
            String headers = readHeaders(input);
            String key = null;
            for (String line : headers.split("\r\n")) {
                if (line.regionMatches(
                        true, 0, "Sec-WebSocket-Key:", 0, 18)) {
                    key = line.substring(18).trim();
                }
            }
            if (key == null) {
                throw new IOException("Missing WebSocket key");
            }

            byte[] hash = MessageDigest.getInstance("SHA-1")
                    .digest((key + MAGIC).getBytes(ASCII));
            String accept =
                    Base64.getEncoder().encodeToString(hash);

            output.write(
                    ("HTTP/1.1 101 Switching Protocols\r\n"
                     + "Upgrade: websocket\r\n"
                     + "Connection: Upgrade\r\n"
                     + "Sec-WebSocket-Accept: " + accept
                     + "\r\n\r\n").getBytes(ASCII));
            output.flush();

            DataInputStream frames = new DataInputStream(input);
            ByteArrayOutputStream fromClient =
                    new ByteArrayOutputStream();

            // Doc mot text message fragmented tu client.
            while (true) {
                Frame f = readClientFrame(frames);
                if (f.opcode() != 1 && f.opcode() != 0) {
                    throw new IOException(
                            "Unexpected opcode " + f.opcode());
                }
                fromClient.write(f.payload());
                if (f.last()) {
                    break;
                }
            }

            // TEXT FIN=0 roi CONTINUATION FIN=1.
            frame(output, 1, false,
                    "Hello ".getBytes(UTF8));
            frame(output, 0, true,
                    "Java".getBytes(UTF8));

            // BINARY FIN=0 roi CONTINUATION FIN=1.
            frame(output, 2, false,
                    new byte[]{1, 2});
            frame(output, 0, true,
                    new byte[]{3, 4});

            // Doc Close tu client, phan hoi Close code 1000.
            Frame close = readClientFrame(frames);
            if (close.opcode() != 8) {
                throw new IOException("Expected close handshake");
            }
            frame(output, 8, true,
                    new byte[]{3, (byte) 232});

            return fromClient.toString(UTF8);
        }
    }

    public static void main(String[] args)
            throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        ExecutorService worker =
                Executors.newSingleThreadExecutor();

        try (ServerSocket listener =
                     new ServerSocket(0, 1, loopback)) {
            Future<String> receivedByServer =
                    worker.submit(() -> serve(listener));

            CountDownLatch wholeMessages =
                    new CountDownLatch(2);
            AtomicReference<Throwable> error =
                    new AtomicReference<>();
            AtomicReference<String> text =
                    new AtomicReference<>();
            AtomicReference<byte[]> binary =
                    new AtomicReference<>();

            WebSocket.Listener callbacks =
                    new WebSocket.Listener() {
                private final StringBuilder parts =
                        new StringBuilder();
                private final ByteArrayOutputStream binaryParts =
                        new ByteArrayOutputStream();

                @Override
                public void onOpen(WebSocket socket) {
                    socket.request(1);
                }

                @Override
                public CompletionStage<?> onText(
                        WebSocket socket,
                        CharSequence part, boolean last) {
                    parts.append(part);

                    if (last) {
                        text.set(parts.toString());
                        parts.setLength(0);
                        wholeMessages.countDown();
                    }
                    socket.request(1);
                    return null;
                }

                @Override
                public CompletionStage<?> onBinary(
                        WebSocket socket,
                        ByteBuffer part, boolean last) {
                    byte[] chunk =
                            new byte[part.remaining()];
                    part.get(chunk);
                    binaryParts.write(
                            chunk, 0, chunk.length);

                    if (last) {
                        binary.set(binaryParts.toByteArray());
                        binaryParts.reset();
                        wholeMessages.countDown();
                    }
                    socket.request(1);
                    return null;
                }

                @Override
                public void onError(
                        WebSocket socket, Throwable cause) {
                    error.compareAndSet(null, cause);
                    wholeMessages.countDown();
                    wholeMessages.countDown();
                }
            };

            HttpClient client = HttpClient.newHttpClient();
            WebSocket socket = client.newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(5))
                    .buildAsync(
                            URI.create(
                                    "ws://127.0.0.1:"
                                    + listener.getLocalPort()
                                    + "/demo"),
                            callbacks)
                    .get(5, TimeUnit.SECONDS);

            // Gui mot message text bang hai lan sendText.
            socket.sendText("Hi ", false)
                    .thenCompose(s ->
                            s.sendText("server", true))
                    .get(5, TimeUnit.SECONDS);

            // Cho hai message day du: mot text, mot binary.
            if (!wholeMessages.await(
                    5, TimeUnit.SECONDS)) {
                throw new TimeoutException(
                        "Inbound messages not complete");
            }
            if (error.get() != null) {
                throw new IOException(
                        "WebSocket listener failed", error.get());
            }

            System.out.println(
                    "inboundText=" + text.get());
            System.out.println(
                    "inboundBinary="
                            + HexFormat.of().formatHex(
                                    binary.get()));

            socket.sendClose(WebSocket.NORMAL_CLOSURE, "")
                    .get(5, TimeUnit.SECONDS);
            System.out.println(
                    "serverReceived="
                            + receivedByServer.get(
                                    5, TimeUnit.SECONDS));
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

### Lệnh biên dịch và đầu ra

~~~bash
javac WebSocketLastDemo.java
java WebSocketLastDemo
~~~

**Kết quả thực tế đã kiểm chứng với JDK 24, dùng các API Java 17+:**

~~~text
inboundText=Hello Java
inboundBinary=01020304
serverReceived=Hi server
~~~

Giải thích chính xác:

1. Mini server bind loopback `127.0.0.1` và port 0 do OS cấp, trả HTTP 101 với `Sec-WebSocket-Accept`.
2. Client gửi `Hi ` bằng `sendText(...false)` rồi `server` bằng `sendText(...true)`. Server nhận client frames đã mask, giải mask và tái lập text **Hi server**.
3. Server gửi text “Hello Java” qua hai **WebSocket frames** rồi gửi binary `01 02 03 04` qua hai frames nữa. Client callback append data và chỉ hoàn thành message khi callback báo `last=true`.
4. `CountDownLatch(2)` ở client giảm **một lần cho mỗi message hoàn chỉnh**, không phải mỗi fragment. Nếu JDK giao 1 hay nhiều callback cho mỗi message, kết quả cuối vẫn đúng.
5. `HexFormat.of().formatHex(...)` có mặt từ Java 17, nên chương trình phù hợp phiên bản 17+.
6. Sau khi nhận đủ hai message, client gửi Close; server đọc Close và phản hồi code 1000. Đây là close WebSocket, khác với cờ last kết thúc text/binary message.

**Không in số callback trong stdout**, vì không có hợp đồng ràng buộc số callback bằng số WebSocket frames. Cái cần kiểm chứng là **thông điệp hoàn chỉnh**. Mini server không phải server Internet có xác thực, không dùng cho production. Nếu môi trường chặn socket loopback, có thể phát sinh IOException/timeout.

## 8. Khi nào xử lý từng phần và khi nào đợi last?

| Nội dung | Có thể xử lý khi `last=false` không? | Khi `last=true` |
| --- | --- | --- |
| JSON document theo quy ước 1 message = 1 JSON | Chỉ parse incremental nếu parser giữ state, không commit document | Validate toàn bộ JSON và phát sự kiện hoàn chỉnh |
| Chat text ngắn | Có thể hiển thị preview nếu thiết kế có trạng thái partial | Đánh dấu message đã nhận đủ |
| File/binary lớn | Có thể ghi từng chunk vào tệp tạm | Finalize file, kiểm checksum/metadata rồi công bố |
| Protobuf hoặc frame nghiệp vụ | Tùy parser/framing riêng | Hoàn tất WebSocket message, kiểm protocol-level framing |
| Nén dữ liệu | Có thể feed streaming decompressor có giới hạn | Kết thúc luồng/kiểm tính toàn vẹn theo format |
| Giao dịch có side effect | Không commit chỉ vì một fragment đã tới | Chỉ sau khi toàn payload hợp lệ và nghiệp vụ cho phép |

**Không coi last=true là ACK của phía đối tác** khi bạn là người gửi. Ở phía nhận, last=true chỉ chứng minh client WebSocket đã nhận trọn message theo API, không tự chứng minh data schema hay chữ ký đã hợp lệ. Một message hoàn chỉnh vẫn có thể là JSON sai định dạng hoặc lệnh không có quyền.

## 9. Giới hạn bộ nhớ: đừng append vô hạn

Nhận nhiều lần callback dễ dẫn tới một lỗi: ứng dụng cứ append text/binary tới khi last=true, nhưng peer gửi một message dài hàng trăm MB hoặc không hoàn tất message. Khi đó có thể gây OOM dù bạn chỉ request(1) từng lượt.

### Text: giới hạn UTF-16 code units

~~~java
// Fragment trong onText; MAX_CHARS là giới hạn > 0.
if (data.length() > MAX_CHARS - partialText.length()) {
    handleOversize(); // Helper báo lỗi và dừng theo policy.
    return null;
}
partialText.append(data);
if (last) {
    String whole = partialText.toString();
    partialText.setLength(0);
    processWholeText(whole);
}
socket.request(1);
return null;
~~~

Đây là giới hạn theo **UTF-16 code units**, không phải byte UTF-8 trên network. Nếu policy giới hạn 1 MB, phải đo byte theo encoding/decoder hoặc có quota riêng. Phép `MAX_CHARS - partialText.length()` giúp tránh lỗi cộng số nguyên tràn trong check.

### Binary: giới hạn byte

~~~java
// Fragment trong onBinary; MAX_BYTES và binaryParts là state riêng.
int amount = data.remaining();
if (amount > MAX_BYTES - binaryParts.size()) {
    handleOversize();
    return null;
}
byte[] copy = new byte[amount];
data.get(copy);
binaryParts.write(copy, 0, copy.length);

if (last) {
    byte[] complete = binaryParts.toByteArray();
    binaryParts.reset();
    processWholeBinary(complete);
}
socket.request(1);
return null;
~~~

Ngoài giới hạn một message, đặt **deadline** cho message dở, max connections, max in-flight bytes, bounded work queue và chính sách backpressure. Với file rất lớn, ưu tiên streaming sang file hoặc parser có state, không gom toàn bộ vào một mảng.

**Khi vượt giới hạn:** không request tiếp bừa bãi; báo fail/cancel/abort theo chính sách. Javadoc Java 17 `sendClose` cấm một số status code, trong đó có **1009**, nên không hướng dẫn gọi `sendClose(1009, ...)` một cách máy móc. Có thể chọn mã close hợp lệ phù hợp hoặc `abort()`, và ghi nhận failure của business request.

## 10. Khi message chưa hoàn tất mà WebSocket đóng hoặc lỗi

`last=false` rồi xuất hiện Close/Error thì đoạn đang tích lũy **không trở thành message hoàn chỉnh**. Đừng cố parse body dở như thể `last=true` đã đến.

~~~java
// Fragment trong WebSocket.Listener.
@Override
public CompletionStage<?> onClose(
        WebSocket socket, int code, String reason) {
    discardPartialMessages(); // Helper: reset, báo incomplete.
    notifyConnectionClosed(code, reason);
    return null;
}

@Override
public void onError(WebSocket socket, Throwable error) {
    discardPartialMessages();
    notifyConnectionFailed(error);
}
~~~

Javadoc WebSocket quy định sau `onClose` hoặc `onError`, không có Listener method nào tiếp theo cho kết nối đó. `onClose` là input side closure; `sendClose` đóng output side, còn `abort()` đóng cả hai bên đột ngột. Khi abort hoặc lỗi mạng, không được giả định chắc sẽ có đủ quy trình close handshake.

Trong ứng dụng thực, cleanup phải idempotent vì timeout, producer, worker và callback có thể đồng thời cố hoàn tất cùng một request. Nếu ứng dụng chờ response tương ứng một request ID, hãy hoàn tất future đó thành lỗi/timeout khi connection bị đóng giữa message.

## 11. Concurrency và CompletionStage của callback

Javadoc nói Listener callbacks cho **một WebSocket** được gọi có thứ tự và **không reentrant**: một lời gọi mới chỉ có thể bắt đầu sau khi lời gọi trước đã trả về. Điều này giúp một Listener chuyên biệt giữ `StringBuilder` riêng và append trong callback mà không cần chia state cho callback thứ hai trên cùng socket.

Nhưng phải phân biệt:

- Callback không nhất thiết luôn chạy cùng một thread.
- `onError` có thể được gọi trong những tình huống bất đồng bộ; state chia sẻ với executor khác phải an toàn.
- Nếu dùng **cùng một Listener cho nhiều WebSockets**, callback từ các socket khác nhau có thể chạy đồng thời.
- Nếu `onText` offload xử lý sang worker rồi return ngay, worker xử lý các đoạn có thể hoàn tất ngược thứ tự, dù callback ban đầu có trình tự.
- Stage trả về từ callback không thay `request(n)`; nếu còn demand, WebSocket có thể tiếp tục gọi callbacks khi stage của callback trước chưa complete.

Ví dụ fragment cho xử lý nền và copy data:

~~~java
// Fragment Java 17+; executor/processChunk/reportFailure do app cung cấp.
@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {
    String copy = data.toString();

    CompletableFuture<Void> done =
            CompletableFuture.runAsync(
                    () -> processChunk(copy, last), executor);

    done.whenComplete((ignored, failure) -> {
        if (failure == null) {
            socket.request(1);
        } else {
            reportFailure(failure);
            socket.abort();
        }
    });
    return done;
}
~~~

Nếu dùng worker pool nhiều thread, phải giữ **thứ tự các fragment** trước khi ghép. Không cấp nhiều request trong lúc queue đã quá tải; có thể dùng serial executor per connection hoặc state machine actor. Bất kỳ exception từ worker phải được xử lý theo deadline/cancel/lifecycle, không để session chờ vô hạn.

## 12. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Sửa |
| --- | --- | --- |
| Parse JSON lỗi ngẫu nhiên | Parse từng `onText` dù `last=false` | Append tới `last=true` hoặc streaming parser |
| Chỉ nhận phần đầu rồi đứng | Chỉ gọi `request(1)` trong onOpen | Request tiếp sau callback khi sẵn sàng |
| Hai message bị nối | Quên reset accumulator ở `last=true` | Emit rồi reset |
| Mất fragment đầu | Reset accumulator ở **mỗi** callback | Chỉ reset sau message hoàn chỉnh |
| Nhận Ping nhưng mất text đang dở | Reset text khi nhận control frame | Xử lý Ping/Pong riêng |
| Kết quả khác giữa JDKs | Giả định 1 frame = 1 callback | Chỉ dựa vào `last` |
| ByteBuffer chứa “rác” | Dùng capacity hoặc toàn backing array | Copy đúng `remaining()` |
| Worker đọc sai CharSequence | Giữ ref sau Stage hoàn tất | Copy toString trong callback |
| Binary data bị thay đổi | Tái dùng buffer gửi trước send Future complete | Chờ Future rồi reuse |
| `sendBinary` báo IllegalStateException | Message text trước chưa hoàn tất | Hoàn tất text bằng last=true trước |
| Hai sendText song song lỗi | Một data-send còn pending | Chain thenCompose hoặc serial send queue |
| OOM vì message lớn | Append vô hạn trước last | Max-size, deadlines, streaming |
| Callback không có onNext tiếp | Demand hết, hoặc socket đóng | Theo dõi receive allowance/onError/onClose |
| Error/Close khi còn partial | Transport hoặc protocol bị ngắt | Không emit partial như complete |
| Callback Stage chưa complete nhưng có callback mới | Nhầm Stage với demand | Quản lý request(n) và queue riêng |
| Không thấy server ACK | Nhầm send Future với kết quả nghiệp vụ | Thiết kế response/ACK và request ID |
| WebSocket không đóng khi message last=true | Last không phải Close | Sử dụng sendClose cho orderly shutdown |
| sendClose(1009) bị từ chối | Javadoc Java17 cấm mã này | Dùng status hợp lệ/abort theo policy |

### Checklist debug một callback

Ghi nhận tối thiểu mà không log payload nhạy cảm:

~~~text
connectionId
callbackKind = onText | onBinary | onPing | onPong | onClose | onError
last = true | false | N/A
fragmentSize = data.length() hoặc data.remaining()
accumulatedSize
messageCountCompleted
receiveRequestsGranted
error / close code / latency
~~~

Nếu số callback thay đổi giữa hai môi trường nhưng nội dung message cuối khớp, đó có thể là sự khác nhau bình thường của cách JDK chia giao dữ liệu. Không tự sửa bằng cách chờ đủ số callback cố định.

## 13. Bộ ca thử nghiệm nên có

| Tình huống | Dữ liệu giả lập | Kết quả đúng |
| --- | --- | --- |
| Một callback | `"OK", true` | Một message "OK" |
| Hai callback | `"Hel",false`; `"lo",true` | Một message "Hello" |
| Nhiều callback | `"A",false`; `"B",false`; `"C",true` | Một message "ABC" |
| Hai message liên tiếp | `"A",true`; `"B",true` | Hai message độc lập |
| Binary hai phần | `[01,02],false`; `[03],true` | Một payload 010203 |
| Ping xen giữa | Text false; Ping; Text true | Một text message + một Ping |
| Close khi dở | Text false; onClose | Không publish incomplete |
| Zero demand | Chỉ request1 rồi callback false | Không hứa callback tiếp nếu không request |
| Không hợp lệ | request(0) | IllegalArgumentException |
| Quá size | Nhiều fragment vượt quota | Báo lỗi/abort, không OOM |
| Worker chậm | Offload nhưng queue bounded | Backpressure thực, không bỏ thứ tự |
| Gửi hai phần | sendText false rồi true | Một message phía server |
| Gửi khác loại giữa chừng | sendText false rồi sendBinary true | Lỗi trạng thái |
| Frame vs callback | Thay đổi network/frame segmentation | Message cuối không thay đổi |

Ưu tiên **unit test assembler** và **integration test thật** như chương trình mục 7. Ở unit test, có thể gọi một hàm thuần `accept(part,last)` để kiểm tra reset/boundary; ở integration test, dùng WebSocket thật và không phụ thuộc số TCP packets.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `onText(ws,"Hel",false)` xảy ra. Đây đã là thông điệp hoàn chỉnh chưa?  
**Đáp án:** Chưa; cần phần sau, chỉ xử lý message-level khi last=true.

**Câu 2.** `onText(ws,"OK",true)` là callback đầu tiên. Có phải chờ phần tiếp không?  
**Đáp án:** Không. Một callback có thể chứa trọn thông điệp.

**Câu 3.** `request(1)` cấp quyền cho một message, frame hay callback?  
**Đáp án:** Một lần receive callback, không nhất thiết là một message.

**Câu 4.** Vì sao `request(1)` có thể khiến message chưa hoàn thành đứng lại?  
**Đáp án:** Callback đầu có last=false tiêu thụ allowance. Phải request tiếp để WebSocket giao callback còn lại.

**Câu 5.** Có `onPing` giữa hai onText fragments thì có reset text không?  
**Đáp án:** Không. Ping là control message riêng, có thể chen giữa fragments.

**Câu 6.** `data.length()` trong onText có đo bytes UTF-8 không?  
**Đáp án:** Không, đó là UTF-16 code units của CharSequence.

**Câu 7.** `onBinary` có position=10, limit=14, capacity=100. Có mấy byte cần nhận?  
**Đáp án:** 4 bytes (remaining), không phải 100.

**Câu 8.** Có thể giữ CharSequence gốc sau khi callback trả null không?  
**Đáp án:** Không an toàn; implementation có quyền reclaim. Copy ngay hoặc quản lý lifetime Stage.

**Câu 9.** `sendText("A",false)` rồi `sendText("B",true)` là mấy messages?  
**Đáp án:** Một text message “AB” nếu gửi hợp lệ theo thứ tự.

**Câu 10.** `sendText("A",true)` có đóng WebSocket không?  
**Đáp án:** Không. Nó chỉ hoàn tất message, socket tiếp tục hoạt động.

**Câu 11.** Text message còn dang dở có thể gọi sendBinary ngay không?  
**Đáp án:** Không; phải hoàn tất text trước, nếu không có thể IllegalStateException.

**Câu 12.** Future của sendText hoàn tất có chứng minh server đã ghi DB không?  
**Đáp án:** Không; đó là kết quả send của client, cần ACK nghiệp vụ.

**Câu 13.** Nếu nhận partial text rồi connection lỗi trước last=true, có được emit message đó không?  
**Đáp án:** Không. Đó là incomplete message; báo lỗi và cleanup state.

**Câu 14.** Có thể dựa vào mỗi WebSocket frame có đúng một onText callback không?  
**Đáp án:** Không. API không có cam kết đó, dùng last để ghép.

**Câu 15.** Tại sao request(1) chưa đủ bảo đảm RAM bounded?  
**Đáp án:** Một fragment có thể lớn, message có thể có rất nhiều fragment, state có thể giữ lâu; cần max-size, deadline, max concurrency và bounded queue.

**Câu 16.** CompletionStage trả về từ onText dùng để làm gì?  
**Đáp án:** Báo quyền thu hồi dữ liệu callback; không tự quyết định end-of-message hay số lượt callback.

**Câu 17.** Một Listener dùng cho nhiều WebSocket có thể chia chung StringBuilder không khóa không?  
**Đáp án:** Không an toàn: callbacks của các WebSocket khác nhau có thể chạy đồng thời; dùng state riêng hoặc đồng bộ đúng.

**Câu 18.** Vì sao ví dụ loopback không log số callback?  
**Đáp án:** Vì số callback không được API cố định bằng số frames. Nội dung được ghép chính xác là kết quả cần test.

## 15. Tài liệu chính thức

- Oracle Java SE 17 — `WebSocket`: `request(long)` đếm callback; `sendText/sendBinary(last)`, IllegalStateException, sendClose và abort: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html
- Oracle Java SE 17 — `WebSocket.Listener`: `onText/onBinary(data,last)`, trình tự callback, `CompletionStage` và thời hạn sở hữu buffer: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html
- Oracle Java SE 17 — `WebSocket.Builder.buildAsync`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html
- Oracle Java SE 17 — `HttpClient.newWebSocketBuilder()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 17 — `ByteBuffer.remaining/position/limit`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Oracle Java SE 17 — `CompletionStage`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html
- IETF RFC 6455 — The WebSocket Protocol, fragmentation/continuation, masking, control frames: https://www.rfc-editor.org/rfc/rfc6455
