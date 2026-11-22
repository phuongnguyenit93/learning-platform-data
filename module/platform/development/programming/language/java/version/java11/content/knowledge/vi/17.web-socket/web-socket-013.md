# Kiểm thử WebSocket hai chiều, payload lớn và đóng giữa chừng (Java 11)

## 1. Mục tiêu

WebSocket duy trì một kết nối **hai chiều (full-duplex)** sau khi opening handshake thành công. Cả client lẫn server có thể chủ động gửi thông điệp text, binary và control frame. Trong Java 11, module `java.net.http` cung cấp **WebSocket client** thông qua `HttpClient.newWebSocketBuilder()`, `WebSocket` và `WebSocket.Listener`.

Để kiểm thử thực sự tin cậy, không đủ nếu chỉ kết nối được và gửi `"hello"`. Một bộ test cần chứng minh:

1. **Hai chiều:** client→server, server→client và thông điệp do server chủ động đẩy.
2. **Ranh giới message:** dữ liệu text/binary có thể đến theo nhiều phần; `last` quyết định thời điểm một thông điệp logic kết thúc.
3. **Payload lớn:** dữ liệu vượt một chunk/buffer được bảo toàn theo thứ tự byte, không làm đầy heap hoặc treo vô thời hạn.
4. **Đóng giữa chừng:** phân biệt Close handshake bình thường, peer đóng khi truyền chưa xong, client `abort()`, và transport mất kết nối không có Close frame.
5. **Tính bất đồng bộ:** future gửi hoàn thành không có nghĩa server đã xử lý; callback có thể đến tại những thời điểm khác nhau.
6. **Vận hành:** backpressure, deadline, giới hạn kích thước, cleanup, thử tải và kiểm thử các race condition.

**Phạm vi:** kiến thức dựa trên Java SE 11 và RFC 6455, vẫn áp dụng trên JDK hiện đại. JDK 11 cung cấp **client WebSocket**, không cung cấp server WebSocket tổng quát qua `java.net.http`. Vì vậy, **unit test tự chạy** có thể kiểm tra bộ ghép fragment không cần mạng; để kiểm tra giao tiếp thật và đóng giữa chừng phải có **server kiểm thử điều khiển được**. Hai cấp độ sẽ được phân biệt rõ.

## 2. Kiến thức API Java 11 phải hiểu đúng

### 2.1. Tạo kết nối

```java
HttpClient client = HttpClient.newHttpClient();
WebSocket socket = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .buildAsync(URI.create("ws://127.0.0.1:8787/echo"), listener)
        .get(10, TimeUnit.SECONDS);
```

Đây là **trích đoạn đặt trong phương thức `throws Exception`**; cần import `java.net.URI`, `java.net.http.HttpClient`, `java.net.http.WebSocket`, `java.time.Duration` và `java.util.concurrent.TimeUnit`; `listener` phải là một `WebSocket.Listener`. Địa chỉ chỉ là **endpoint giả định cho server test do bạn kiểm soát**, không có sẵn trong JDK. Trong production, ưu tiên `wss://` và cấu hình TLS đáng tin cậy.

Một `WebSocket` có hai phía **input** và **output** độc lập. Khi output đóng, input không mặc nhiên đóng ngay. Các lời gọi `sendText`, `sendBinary`, `sendPing`, `sendPong` và `sendClose` trả `CompletableFuture<WebSocket>`. Future thành công nghĩa là **send operation hoàn thành theo API**, chứ không bảo đảm ứng dụng bên kia đã lưu thông điệp.

### 2.2. Các callback và điều kiện kết thúc

| Callback `WebSocket.Listener` | Ý nghĩa | Kiểm thử cần xác nhận |
| --- | --- | --- |
| `onOpen(socket)` | Kết nối mở; được gọi tối đa một lần | Bắt đầu cấp demand bằng `socket.request(1)` |
| `onText(socket, data, last)` | Nhận một phần text message | Ghép phần, chỉ hoàn tất message khi `last=true` |
| `onBinary(socket, data, last)` | Nhận một phần binary message | Duyệt đúng `position..limit`, đếm byte/checksum |
| `onPing(socket, data)` | Nhận Ping (≤125 byte) | API tự xử lý Pong phản hồi; không nhất thiết gửi trùng |
| `onPong(socket, data)` | Nhận Pong | Nếu có heartbeat test, đối chiếu request/payload |
| `onClose(socket, code, reason)` | Nhận Close frame; input đã đóng; callback cuối | Kiểm tra status/reason và state đóng |
| `onError(socket, error)` | Lỗi; callback cuối; hai phía đã đóng | Future test phải thất bại, không chờ `onClose` nữa |

`WebSocket.Listener` gọi callback tuần tự cho **một** socket, nhưng không cam kết tất cả callback chạy trên cùng thread. Listener dùng chung cho nhiều socket cần state và đồng bộ phù hợp.

**`onClose` và `onError` không phải hai tín hiệu bắt buộc liên tiếp.** `onError` có thể xuất hiện bất cứ lúc nào sau `onOpen`; khi nó xảy ra không kỳ vọng thêm `onClose`. Nếu server **rút TCP không có Close frame**, test không được khẳng định bắt buộc nhận `onClose(1006)`.

### 2.3. `request(n)` là số callback, không phải số byte

WebSocket Java 11 duy trì một **receive invocation counter**. `socket.request(n)` cho phép tối đa thêm `n` lời gọi trong nhóm `onText`, `onBinary`, `onPing`, `onPong` và `onClose`; `onOpen`/`onError` không tính vào nhóm này.

- `request(1)` nghĩa là cho phép **một receive callback**, không phải 1 byte, không phải 1 message.
- Một message có thể gồm nhiều lần `onText`/`onBinary` vì `last=false`.
- `request(n <= 0)` không hợp lệ: `WebSocket.request` ném `IllegalArgumentException`.
- Vì `onClose` cũng là receive callback, nếu listener **không xin thêm demand**, test có thể mắc kẹt khi chờ Close.
- Default implementation của `onOpen` và các receive data callbacks yêu cầu thêm một invocation. Khi **override** các phương thức ấy, phải tự quản lý request.

Ví dụ một listener chỉ xử lý đồng bộ:

```java
@Override
public CompletionStage<?> onBinary(
        WebSocket socket, ByteBuffer data, boolean last) {
    while (data.hasRemaining()) {
        int byteValue = data.get() & 0xff;
        processByte(byteValue);
    }
    socket.request(1);
    return null;
}
```

Đây là **trích đoạn**, cần `processByte(int)` do ứng dụng định nghĩa và import `CompletionStage`, `ByteBuffer`, `WebSocket`. Trả `null` có nghĩa dữ liệu callback đã tiêu thụ xong và JDK được phép reclaim buffer; không giữ reference để xử lý sau đó.

### 2.4. `CompletionStage` callback không thay cho demand

Với `onText`/`onBinary`/`onPing`/`onPong`, returned `CompletionStage<?>` thông báo **khi nào JDK có thể thu hồi dữ liệu**. Nó độc lập với bộ đếm `request(n)`: nếu đã có demand, callback kế tiếp có thể bắt đầu **trước** khi stage của callback trước hoàn tất.

Vì thế, với xử lý bất đồng bộ:
- Hoặc **sao chép phần dữ liệu cần dùng** trước khi trả callback, vào hàng đợi có giới hạn.
- Hoặc duy trì returned stage cho đến khi downstream xử lý xong, và cấp demand có kiểm soát.
- Không giữ `ByteBuffer`/`CharSequence` sau khi stage đã hoàn tất.
- Không coi `request(1)` là trần heap; một callback có thể có payload lớn hơn nhiều byte.

## 3. Ma trận kiểm thử theo hành vi

| Test case | Thiết lập/kích hoạt | Pass khi |
| --- | --- | --- |
| Kết nối và handshake | Server echo thật, thời hạn kết nối | `buildAsync` hoàn tất, `onOpen` nhận đúng |
| Text hai chiều | Client gửi text, server echo | Nội dung Unicode bằng nhau, `last` hoàn tất |
| Server chủ động gửi | Server gửi `SERVER_READY` trước echo | Listener nhận riêng và không nhầm thành echo |
| Binary hai chiều | Client gửi bytes gồm `0x00`/`0xff` | Tổng byte, checksum và message boundary đúng |
| Text/binary fragmented | Gửi `last=false` rồi `true` | Ghép đúng message, không phụ thuộc số callback |
| Message rỗng | Text rỗng/binary rỗng | Message vẫn hợp lệ và được hoàn tất |
| Payload lớn | 1 MiB+17 byte hoặc mức theo ngân sách | Không mất/trùng byte, không giữ toàn bộ trong heap không cần thiết |
| Ping/Pong | Client/server phát Ping trong message | Pong hợp lệ, không làm mất state ghép message |
| Slow reader/writer | Server trì hoãn nhận hoặc gửi | Không deadlock, queue và memory có giới hạn |
| Close bình thường | Client `sendClose(1000,"")` | Output đóng; nhận Close response nếu server cam kết |
| Server Close giữa payload | Server gửi Close sau ngưỡng N byte | Test kết thúc hoặc cleanup trong deadline; không commit payload thiếu |
| Transport drop giữa payload | Server đóng TCP không gửi Close | Báo lỗi hoặc trạng thái kết thúc hợp lý, không treo |
| Client abort giữa send | Gọi `socket.abort()` khi còn send pending | Input/output đóng đột ngột; pending sends fail theo hợp đồng |
| Handshake không thành công | Server trả HTTP lỗi/không upgrade | Future build thất bại; không gửi data trên socket không tồn tại |
| Race trong shutdown | Close hai phía gần đồng thời | Không assert cứng thứ tự hoặc số chunk do timing |

**Mẹo:** mô tả rõ *điều kiện đầu vào*, *server điều khiển gì*, *deadline*, *các event bắt buộc* và *sự kiện nào có thể thay đổi do race*. Với test Close giữa chừng, bắt buộc có server kiểm thử riêng có thể chọn chính xác thời điểm gửi Close hoặc drop connection.

## 4. Kiểm tra hai chiều đúng nghĩa

### 4.1. Gửi xong khác với đã nhận lại

```text
Client: sendBinary(chunk, last)    → send future complete
Server: nhận và xử lý             → log/ACK theo hợp đồng test
Client: onBinary(..., last=true)   → nhận đủ echo
```

Để kết luận **round-trip PASS**, test phải đợi cả send future và một future riêng hoàn thành tại callback `onText/onBinary` khi message đủ. Nếu nghiệp vụ có side effect, cần **application-level ACK** hoặc server-side state; chỉ thấy echo chưa chắc là transaction đã commit.

Server có thể gửi message chủ động trong khi client đang gửi. Một test đúng phải phân tuyến dựa trên loại message, correlation ID hoặc envelope, không ngầm coi mọi message đầu tiên là phản hồi của send đầu tiên.

### 4.2. Gửi fragment tuần tự

```java
socket.sendText("Xin ", false)
      .thenCompose(ws -> ws.sendText("chào Java 11", true));
```

Hai lời gọi trên tạo **một message text** khi mọi send thành công: `false` là còn fragment; `true` là phần cuối. Không chỉnh sửa `CharSequence` trước khi send future hoàn tất. Với binary:

```java
socket.sendBinary(ByteBuffer.wrap(new byte[]{1, 2}), false)
      .thenCompose(ws ->
              ws.sendBinary(ByteBuffer.wrap(new byte[]{3, 4}), true));
```

Các ví dụ là **trích đoạn** sử dụng biến `socket` kiểu `WebSocket`. Không gửi text và binary xen kẽ trong một message chưa kết thúc, không chồng các send chưa xong một cách không kiểm soát: `WebSocket` có thể báo `IllegalStateException`.

### 4.3. Không assert số lần callback

Client gửi 4 fragment nhưng server/client listener có thể nhận một số callback khác 4. Test đúng:

- Có `last=true` cuối message.
- Độ dài và checksum khớp.
- Thứ tự byte của message không đổi.
- Không xuất hiện message thừa/thiếu theo giao thức ứng dụng.

`onText` trả các `CharSequence` hợp lệ theo hợp đồng Java 11; nếu bạn xử lý text bằng byte UTF-8 thủ công thì phải giữ trạng thái decoder qua ranh giới chunk. Đừng so số ký tự UTF-16 với byte length như thể chúng luôn bằng nhau.

## 5. Payload lớn: kiểm tra đúng mà không tốn heap vô hạn

### 5.1. Sinh chunk theo yêu cầu

Một message có 1 MiB+17 byte chứa 1.048.593 byte: tổng này **không chia hết 8192**, nên giúp phát hiện lỗi phần dư cuối. Dùng một quy tắc sinh byte xác định, ví dụ `(offset+i) % 251`, và checksum `CRC32` để đối chiếu.

- **Gửi:** tạo `byte[]` ≤8192 byte, gói bằng `ByteBuffer.wrap`, gọi `sendBinary(chunk, last)`; **đợi future** trước khi sửa/tái sử dụng buffer.
- **Nhận:** đọc `ByteBuffer` trong `onBinary` từ `position` đến `limit`, cập nhật count và checksum.
- **Kết thúc:** chỉ xác nhận hoàn tất message khi `last=true`, so byte count và checksum.
- **Bộ nhớ:** không tự động gom tất cả chunk vào `ByteArrayOutputStream` hoặc `List<ByteBuffer>`.
- **Thử tải:** chạy thêm kích thước 0, 1, 8191, 8192, 8193, nhiều MiB; đo đỉnh bộ nhớ khi nhiều socket cùng chạy.

CRC32 là công cụ phát hiện sai lệch trong **test**; không phải chữ ký/HMAC bảo vệ chống sửa đổi có chủ đích.

### 5.2. `ByteBuffer` và ownership

`sendBinary(ByteBuffer, boolean)` đọc từ `position` đến `limit`. Javadoc Java 11 yêu cầu **không truy cập buffer cho tới khi future gửi hoàn tất**; khi future hoàn tất bình thường, buffer không còn byte chưa đọc.

Ở chiều nhận, `ByteBuffer` có thể là direct hoặc read-only; không dùng `data.array()` như thể mọi buffer đều có mảng backing truy cập được. Duyệt bằng `hasRemaining()/get()` hoặc `duplicate()` khi cần giữ vị trí.

```java
static long countAndHash(ByteBuffer data, CRC32 crc) {
    long n = 0;
    while (data.hasRemaining()) {
        crc.update(data.get() & 0xff);
        n++;
    }
    return n;
}
```

Đây là **phương thức minh họa** trong lớp có import `java.nio.ByteBuffer` và `java.util.zip.CRC32`.

**Không nhầm:** `capacity()` là dung lượng buffer, còn `remaining()` là số byte thực trong vùng đọc. Hãy dùng `remaining()` để giới hạn và đếm.

## 6. Chương trình Java 11 độc lập: unit test ghép fragment và kiểm tra CRC

Chương trình dưới đây **không tạo WebSocket network**. Nó kiểm tra phần xử lý **fragment text và binary** mà một listener thực sử dụng. Đây là unit test determinisitic, không thay thế integration test handshake, backpressure, Close hay transport.

Tạo tệp **`WebSocketFragmentUnitDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.util.zip.CRC32;

public class WebSocketFragmentUnitDemo {

    static final class Collector {
        private final StringBuilder text = new StringBuilder();
        private String completeText;
        private int textParts;

        private final CRC32 crc = new CRC32();
        private long bytes;
        private long checksum;
        private boolean binaryComplete;

        void onTextPart(CharSequence fragment, boolean last) {
            text.append(fragment);
            textParts++;
            if (last) {
                completeText = text.toString();
                text.setLength(0);
            }
        }

        void onBinaryPart(ByteBuffer fragment, boolean last) {
            while (fragment.hasRemaining()) {
                crc.update(fragment.get() & 0xff);
                bytes++;
            }
            if (last) {
                checksum = crc.getValue();
                binaryComplete = true;
            }
        }
    }

    public static void main(String[] args) {
        Collector collector = new Collector();
        collector.onTextPart("Xin ", false);
        collector.onTextPart("chào Java 11", true);

        int total = 1024 * 1024 + 17;
        int blockSize = 8192;
        CRC32 expected = new CRC32();

        for (int offset = 0; offset < total; ) {
            int length = Math.min(blockSize, total - offset);
            byte[] chunk = new byte[length];

            for (int i = 0; i < length; i++) {
                chunk[i] = (byte) ((offset + i) % 251);
            }

            expected.update(chunk, 0, chunk.length);
            boolean last = offset + length == total;
            collector.onBinaryPart(
                    ByteBuffer.wrap(chunk), last);
            offset += length;
        }

        System.out.println("text=" + collector.completeText);
        System.out.println("text_parts=" + collector.textParts);
        System.out.println("binary_bytes=" + collector.bytes);
        System.out.println("checksum_match="
                + (expected.getValue() == collector.checksum));
        System.out.println("binary_completed="
                + collector.binaryComplete);
    }
}
```

Biên dịch/chạy bằng **Java 11**:

```bash
javac --release 11 -encoding UTF-8 WebSocketFragmentUnitDemo.java
java WebSocketFragmentUnitDemo
```

Đầu ra xác định:

```text
text=Xin chào Java 11
text_parts=2
binary_bytes=1048593
checksum_match=true
binary_completed=true
```

Giải thích: text message có hai fragment; binary message có 1.048.593 byte gồm những chunk ≤8192, chỉ chunk cuối có `last=true`. Hai CRC khớp vì cùng thuật toán byte và thứ tự dữ liệu. Unit test này không chứng minh server WebSocket hoạt động vì nó hoàn toàn không gửi qua mạng.

## 7. Integration test Java 11: echo text và binary thật

Chuẩn bị một **server echo WebSocket kiểm thử** với hợp đồng:

1. URL, ví dụ `ws://127.0.0.1:8787/echo`, đang chạy trong mạng test.
2. Echo một message text hoặc binary **nguyên vẹn**, không thêm prefix/suffix và không đổi byte.
3. Không gửi message chủ động trên endpoint `/echo`.
4. Chấp nhận tối thiểu **1 MiB + 17 byte** cho một binary message.
5. Khi client gửi Close code 1000, server trả Close 1000 trong thời gian hữu hạn.

**Không có WebSocket server tương ứng trong `java.net.http` Java 11**: bạn cần khởi động server riêng (thư viện hoặc dịch vụ test). Mã sau là **client integration test hợp lệ**, nhưng không thể chạy thành công nếu chưa có echo server đáp ứng hợp đồng.

Tạo tệp **`WebSocketEchoIntegration.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;
import java.util.zip.CRC32;

public class WebSocketEchoIntegration {

    static final class EchoListener implements WebSocket.Listener {
        final CompletableFuture<String> textDone =
                new CompletableFuture<>();
        final CompletableFuture<long[]> binaryDone =
                new CompletableFuture<>();
        final CompletableFuture<Integer> closeDone =
                new CompletableFuture<>();

        private final StringBuilder text = new StringBuilder();
        private final CRC32 receivedCrc = new CRC32();
        private long receivedBytes;

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket socket, CharSequence part, boolean last) {
            text.append(part);
            if (last) {
                textDone.complete(text.toString());
            }
            socket.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onBinary(
                WebSocket socket, ByteBuffer part, boolean last) {
            while (part.hasRemaining()) {
                receivedCrc.update(part.get() & 0xff);
                receivedBytes++;
            }
            if (last) {
                binaryDone.complete(new long[]{
                        receivedBytes, receivedCrc.getValue()
                });
            }
            socket.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket socket, int code, String reason) {
            if (!textDone.isDone()) {
                textDone.completeExceptionally(
                        new IllegalStateException("closed before text"));
            }
            if (!binaryDone.isDone()) {
                binaryDone.completeExceptionally(
                        new IllegalStateException("closed before binary"));
            }
            closeDone.complete(code);
            return null;
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            textDone.completeExceptionally(error);
            binaryDone.completeExceptionally(error);
            closeDone.completeExceptionally(error);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java WebSocketEchoIntegration <ws-echo-uri>");
        }

        HttpClient client = HttpClient.newHttpClient();
        EchoListener listener = new EchoListener();
        WebSocket socket = client.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .buildAsync(URI.create(args[0]), listener)
                .get(10, TimeUnit.SECONDS);

        try {
            socket.sendText("Xin ", false)
                  .get(10, TimeUnit.SECONDS);
            socket.sendText("chào Java 11", true)
                  .get(10, TimeUnit.SECONDS);

            String text = listener.textDone
                    .get(10, TimeUnit.SECONDS);
            if (!"Xin chào Java 11".equals(text)) {
                throw new AssertionError("Text mismatch");
            }
            System.out.println("text_roundtrip=true");

            int total = 1024 * 1024 + 17;
            int blockSize = 8192;
            CRC32 expected = new CRC32();

            for (int offset = 0; offset < total; ) {
                int len = Math.min(blockSize, total - offset);
                byte[] chunk = new byte[len];
                for (int i = 0; i < len; i++) {
                    chunk[i] = (byte) ((offset + i) % 251);
                }
                expected.update(chunk, 0, len);
                boolean last = offset + len == total;
                socket.sendBinary(ByteBuffer.wrap(chunk), last)
                      .get(10, TimeUnit.SECONDS);
                offset += len;
            }

            long[] received = listener.binaryDone
                    .get(20, TimeUnit.SECONDS);
            if (received[0] != total ||
                    received[1] != expected.getValue()) {
                throw new AssertionError("Binary mismatch");
            }
            System.out.println("binary_roundtrip=true");
            System.out.println("binary_bytes=" + received[0]);

            socket.sendClose(WebSocket.NORMAL_CLOSURE, "")
                  .get(10, TimeUnit.SECONDS);
            int closeCode = listener.closeDone
                    .get(10, TimeUnit.SECONDS);
            if (closeCode != WebSocket.NORMAL_CLOSURE) {
                throw new AssertionError("Close status=" + closeCode);
            }
            System.out.println("normal_close=" + closeCode);
        } finally {
            if (!socket.isInputClosed() ||
                    !socket.isOutputClosed()) {
                socket.abort();
            }
        }
    }
}
```

Biên dịch/chạy sau khi **server kiểm thử đã khởi động**:

```bash
javac --release 11 -encoding UTF-8 WebSocketEchoIntegration.java
java WebSocketEchoIntegration ws://127.0.0.1:8787/echo
```

Nếu server đúng hợp đồng và không có timeout, output sẽ là:

```text
text_roundtrip=true
binary_roundtrip=true
binary_bytes=1048593
normal_close=1000
```

**Lưu ý:** đây là output **có điều kiện**, không phải tuyên bố đã chạy kết nối thật. Nếu server không tồn tại, gửi dữ liệu khác, đóng sớm hoặc vượt deadline, test phải fail. Code không coi `sendBinary` future thành công là đã nhận echo; nó đợi `onBinary(last=true)`, sau đó kiểm tra cả byte count và CRC.

**Giới hạn của ví dụ:** `EchoListener` chỉ dự kiến một message text và một message binary theo thứ tự trên một socket. Khi server còn gửi các message chủ động hoặc các loại message khác, cần thêm protocol envelope/correlation ID và state machine để phân tuyến. Không tái dùng listener một-message này cho nhiều session độc lập.

## 8. Đóng bình thường: `sendClose`, `onClose` và hai nửa kết nối

`socket.sendClose(WebSocket.NORMAL_CLOSURE, "")` phát Close frame code **1000**, yêu cầu đóng **output** có trật tự. Theo Javadoc Java 11, input **có thể vẫn mở** cho đến khi nhận peer Close, `abort` hoặc lỗi.

```text
Client                                  Server
  |----------- data message ------------>|
  |<---------- echo/ack ------------------|
  |----------- Close(1000) ------------->|
  |<---------- Close(1000) --------------|
  | onClose(...,1000,...)                |
  | input/output đã khép                |
```

Không assert tại thời điểm future của `sendClose` hoàn thành thì `isInputClosed()` nhất thiết đã true. Future gửi Close và callback nhận Close là **hai mốc độc lập**. Nếu server không phản hồi trong deadline, test cần `abort()` dọn tài nguyên.

### 8.1. Mã Close và reason

- `1000`: đóng bình thường.
- `1001`: endpoint rời đi/shutdown.
- `1009`: message quá lớn với khả năng xử lý của peer.
- `1006`: chỉ để diễn giải đóng bất thường khi không có Close frame, **không được gửi** bằng `sendClose(1006, ...)`.
- `sendClose` Java 11 chỉ chấp nhận mã hợp lệ theo API (không phải mọi mã 1000–4999 đều dùng được). `reason` UTF-8 **không quá 123 byte**, không chỉ là 123 ký tự Java.
- Ping/Pong/Close là control frame; RFC 6455 giới hạn payload **≤125 byte** và không cho fragment.

Nếu test mất TCP đột ngột, không tự tạo Close frame code 1006 để “giả lập”. Hãy đóng transport server test và quan sát lỗi thực.

## 9. Đóng giữa chừng: ba đường cần kiểm riêng

### 9.1. Server chủ động Close giữa payload

Thiết kế endpoint riêng `ws://127.0.0.1:8787/close-mid`. Server test cần:

1. Hoàn tất opening handshake.
2. Nhận binary message từ client được chia thành nhiều fragment.
3. Khi đã nhận một ngưỡng, ví dụ **64 KiB**, **chủ động gửi Close frame hợp lệ**, chưa đợi client gửi hết message.
4. Ghi log số byte, thời điểm gửi Close và state của socket để test quan sát được.
5. Đóng theo đúng quy trình protocol, hoặc sau deadline thì cắt transport và ghi rõ trong kết quả test.

**Điểm quan trọng về race:** không assert “chunk thứ 9 nhất định thất bại” hay “client chỉ gửi đúng 65.536 byte”. Scheduler, buffer mạng và JDK có thể khiến một số send future hoàn tất trước hoặc sau Close. Test nên xác nhận:

- Client có sự kiện **Close hoặc error** trong deadline, hoặc test tự abort khi hết deadline và fail rõ nguyên nhân.
- Message chưa nhận `last=true` thì **không** được đánh dấu là message hoàn chỉnh.
- Không commit dữ liệu nghiệp vụ thiếu, trừ khi protocol ứng dụng cho phép nhận từng phần và xác minh riêng.
- Các future bị treo được xử lý; có cleanup phía client/server.
- Server-side log xác thực nó thực sự đã cố chủ động Close tại ngưỡng.

```text
T0 client bắt đầu send các fragment 8192 byte
T1 server xác nhận >= 64 KiB
T2 server phát Close
T3 client thấy send thành công hoặc thất bại, tùy race
T4 listener nhận onClose hoặc onError
T5 test cleanup, đối chiếu server log và trạng thái nghiệp vụ
```

Đây là **kịch bản kiểm thử**, không phải thứ tự bất biến. Có thể dùng một barrier/kênh điều khiển server test riêng để kích hoạt Close đúng khi đạt ngưỡng, nhưng số byte đã bay trên mạng vẫn có thể khác nhau.

### 9.2. Client chủ động dừng khi đang nhận

Nếu client không muốn tiếp tục nhận payload quá lớn, có thể **gửi Close** theo chính sách hoặc gọi `abort()` khi cần dừng ngay. `sendClose` là đường có giao thức, còn `abort` đóng cả input/output **đột ngột**.

Một cách kiểm soát kích thước minh họa:

```java
long incoming = data.remaining();
if (incoming > limitBytes - acceptedBytes) {
    socket.sendClose(1009, "message too big");
    // Đánh dấu message bị từ chối; đợi Close có deadline.
    // Nếu handshake không kết thúc thì abort để cleanup.
    return null;
}
acceptedBytes += incoming;
```

Đây là **trích đoạn** trong callback `onBinary`, cần `limitBytes`, `acceptedBytes`, `data` và `socket` có giá trị hợp lệ. Kiểm tra `acceptedBytes <= limitBytes` trước phép trừ, giới hạn theo **mỗi message** hoặc toàn connection theo chính sách. Đừng coi `request(1)` là giới hạn byte. Nếu muốn từ chối **ngay lập tức** mà không chờ handshake, có thể chọn `abort()` nhưng phải chấp nhận mất khả năng graceful close.

### 9.3. Peer rút TCP hoặc mạng bị ngắt bất ngờ

Đây không phải Close handshake. Server test đóng socket/tiến trình khi client đang gửi hoặc nhận.

- `onError` hoặc send future thất bại có thể xuất hiện; **không** đợi `onClose` bắt buộc.
- Một phần dữ liệu có thể đã đến server; không suy ra “chưa xử lý gì” chỉ vì future lỗi.
- Không khẳng định chính xác class/message exception của mọi OS/JDK.
- Không đợi vô hạn; dùng deadline và `finally`/`abort`.
- Nếu nghiệp vụ có side effect, cần idempotency/correlation hoặc tra cứu trạng thái phía server thay vì retry vô điều kiện.

Theo `WebSocket.abort()` Java 11, khi nó trả về, cả input và output đều đã đóng; các send pending thất bại với `IOException`. Đừng hiểu `abort()` là có gửi Close frame 1000 hay peer nhận biết ngay lập tức.

## 10. Đồng bộ test đúng cách: không phụ thuộc `sleep`

Một test dễ flaky nếu dùng:

```java
socket.sendText("hello", true);
Thread.sleep(100);
```

Đây là **trích đoạn anti-pattern**: nó không đợi send future cũng không đợi nhận message; 100 ms không có ý nghĩa bảo đảm callback dưới tải CI.

Thay bằng:

- Future của **send**; đợi có timeout.
- Future của **receive đủ message**, hoàn thành tại callback khi `last=true`.
- Future cho **onClose** và riêng cho **onError** hoặc một completion outcome được mã hóa rõ.
- Kênh server-side audit để chứng minh byte đến server và Close đã được phát.
- Timeout **mỗi bước** và deadline **toàn kịch bản**; quá hạn phải fail và cleanup.
- Sử dụng `CompletableFuture.anyOf` khi chờ close *hoặc* lỗi, nhưng xử lý future còn lại, không để task orphan.

### 10.1. State machine nên quan sát

```text
CONNECTING
   ├── HANDSHAKE_FAILED
   └── OPEN
        ├── DATA_SENDING / DATA_RECEIVING
        │    ├── MESSAGE_COMPLETE (last=true)
        │    ├── CLOSE_SENT
        │    └── ERROR
        ├── CLOSE_RECEIVED
        ├── CLOSED
        └── ABORTED
```

Đây là **mô hình nghiệp vụ để kiểm thử**, không phải enum công khai của JDK. Đảm bảo không chuyển sang `MESSAGE_COMPLETE` khi mới có fragment `last=false`, không xử lý send mới sau output đã đóng, không chờ `onClose` sau `onError`.

### 10.2. Cleanup khi deadline vượt

```java
try {
    // Kiểm thử với get(timeout, TimeUnit.SECONDS)
    // cho các future quan trọng.
} finally {
    if (!socket.isInputClosed() ||
            !socket.isOutputClosed()) {
        socket.abort();
    }
}
```

Đây là **trích đoạn**, biến `socket` được tạo thành công từ builder. Java 11 `HttpClient` không có `close()`/`shutdown()` như JDK 21+; quản lý client theo vòng đời ứng dụng, và trong test dọn những socket đã mở cùng executor do test sở hữu.

## 11. Stress test, backpressure và ngân sách bộ nhớ

Sau kịch bản 1 connection, kiểm thử nhiều kết nối và thông điệp:

| Thử nghiệm | Quan sát |
| --- | --- |
| 1, 10, 100 socket đồng thời (tùy CI) | Active connections, CPU, heap peak, độ trễ |
| Payload 0/1 byte, 8191/8192/8193 byte | Biên buffer, rỗng và byte dư |
| Payload nhiều MiB | Heap peak, số callback, thời gian send/receive |
| Server đọc rất chậm | Send future/queue có bị kẹt, timeout hoạt động không |
| Client request rất ít | Callback có dừng đúng demand, Close có được nhận không |
| Server push trong lúc client upload | Không deadlock và không trộn message |
| Ping/Pong trong message fragment | Không làm mất trạng thái ghép message |
| Close từ hai phía gần đồng thời | Không giả định thứ tự callback, cleanup đúng |
| Server abort giữa binary | Không commit message thiếu, callback lỗi được quản lý |

Mỗi test cần giới hạn **tổng số byte**, **số connection**, **thời gian**, **số future đang chờ** và **queue downstream**. Với test stress, đừng lưu hàng trăm payload nguyên vẹn trong heap chỉ để đối chiếu; có thể xác minh bằng checksum/số byte hoặc streaming ra file test. CRC32 phù hợp kiểm thử mất/sai byte, không thay thế bảo mật.

Đặc biệt khi nhận text Unicode, ký tự có thể dài hơn một byte UTF-8; nếu phải xử lý theo byte, dùng decoder có trạng thái. Listener `onText` nhận các `CharSequence` hợp lệ; không so “độ dài String” với “byte đã gửi” như thể là một đơn vị.

## 12. Bảo mật giao thức khi kiểm thử

- **`wss://`:** sử dụng chứng chỉ hợp lệ hoặc truststore kiểm thử có phạm vi, không vô hiệu xác minh TLS để làm test xanh.
- **Handshake:** server trả lỗi hoặc không upgrade phải dẫn đến lỗi kết nối, không tự coi WebSocket đã mở.
- **Authorization:** nếu handshake mang token/cookie, không log raw header hoặc URL query; dùng dữ liệu tổng hợp trong test.
- **Masking:** RFC 6455 yêu cầu client→server frame được mask; dùng server test tuân thủ chuẩn, không chỉnh sửa giao thức để vượt test.
- **Payload limit:** server và client cần chính sách tối đa theo nghiệp vụ; `1009` biểu thị message quá lớn khi đóng theo giao thức.
- **Ping/Pong:** payload control tối đa 125 byte và không fragment, khác với text/binary dài.
- **Close code reserved:** không gửi 1006/1005 như Close frame, không giả lập đứt mạng bằng mã đóng không hợp lệ.
- **Tác vụ có side effect:** future send thành công không chứng minh server commit; cần ACK/deduplication/trạng thái nghiệp vụ trước retry.
- **Log:** chỉ log event code, correlation an toàn, byte count và trạng thái; không log raw secret/payload lớn.
- **Server kiểm thử:** dùng port riêng, tắt khi kết thúc CI, không dùng endpoint production để gây Close/abort stress.

## 13. Các lỗi phổ biến cần tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Chỉ assert future của `sendBinary` | Không chứng minh round-trip | Chờ listener đủ message và đối chiếu checksum |
| Assert số `onBinary` bằng số `sendBinary` | Callback không tương đương frame | Dựa vào `last`, byte count và thứ tự |
| Quên `request(1)` | Có thể không nhận thêm callback/Close | Cấp demand đúng nhóm receive methods |
| Coi `request(1)` là 1 byte | Sai đơn vị, có thể vượt heap limit | Giới hạn tổng byte riêng |
| Trả `null` rồi giữ `ByteBuffer` callback | Dữ liệu có thể bị reclaim | Copy hoặc stage chưa hoàn thành theo ownership |
| Lấy `capacity()` thay `remaining()` | Sai số byte | Đếm vùng `position..limit` |
| Tái dùng/sửa buffer trước send future kết thúc | Payload có thể bị thay đổi | Chờ future trước khi tái dùng |
| Dùng `StringBuilder` cho payload không giới hạn | Nguy cơ OOME | Stream/chunk/checksum và hạn mức |
| Gửi text/binary đồng thời trong fragment unfinished | Sai trạng thái, exception | Chain send futures, kết thúc message đúng |
| Cho rằng `sendClose` đóng cả input | Sai half-close semantics | Đợi peer Close hoặc abort nếu timeout |
| Mong `onClose(1006)` khi TCP reset | Không phải Close frame hợp lệ | Quan sát `onError` và cleanup |
| Gửi `sendClose(1006, ...)` | Mã không hợp lệ | Test drop transport thật |
| Assert chính xác chunk gửi thành công khi server đóng sớm | Race/timing | Assert terminal/cleanup/server-side audit |
| Dùng `Thread.sleep(100)` chờ callback | Test flaky dưới CI | Future có timeout, barrier server |
| Không cleanup khi test fail | Rò socket/thread | `finally`, abort và dọn server |
| Không giới hạn tải lớn | Làm đầy heap/CI | Ngưỡng byte/concurrency/deadline |
| Test echo công khai để kiểm tra Close giữa chừng | Không điều khiển timing và server log | Server test riêng có kịch bản chủ động |

## 14. Bài luyện tập

**Bài 1.** Client gọi `sendBinary(data, true)` và future hoàn thành. Đủ để khẳng định server đã nhận đủ và lưu dữ liệu?

**Đáp án:** Không. Future đại diện send operation; cần server ACK/log hoặc nhận echo đã đủ `last=true`, và với nghiệp vụ phải kiểm tra trạng thái riêng.

**Bài 2.** Client gửi 4 fragment, listener nhận 6 callback `onBinary`. Có tự động sai?

**Đáp án:** Không. Ranh giới callback không buộc giống ranh giới send. Test dùng byte count, checksum, thứ tự và `last`.

**Bài 3.** `request(1)` cho nhận bao nhiêu byte?

**Đáp án:** Không xác định. Nó cho phép thêm **một receive callback**, có thể chứa lượng byte khác nhau; cần giới hạn byte riêng.

**Bài 4.** `sendClose(1000,"")` hoàn tất, `isOutputClosed()==true` nhưng `isInputClosed()==false`. Có lỗi?

**Đáp án:** Không. Output và input là hai phía độc lập. Chờ Close từ peer hoặc áp timeout/abort.

**Bài 5.** Server drop TCP giữa payload. Có bắt buộc `onClose(1006)`?

**Đáp án:** Không. Không có Close frame; có thể nhận `onError` hoặc send future lỗi. `1006` không được gửi trong Close frame.

**Bài 6.** Vì sao `CRC32` cùng byte count tốt hơn chỉ so byte count?

**Đáp án:** Hai payload có thể cùng kích thước nhưng khác byte. CRC32 giúp phát hiện khác biệt trong test, không bảo đảm bảo mật trước attacker.

**Bài 7.** Vì sao không được giữ `ByteBuffer` đến sau khi returned `CompletionStage` của `onBinary` hoàn tất?

**Đáp án:** JDK được phép reclaim dữ liệu. Nếu cần xử lý trễ, copy đúng phần hoặc trì hoãn completion stage và quản lý demand.

**Bài 8.** Server đóng sau ngưỡng 64 KiB, client có lần gửi thành công thêm một chunk. Có nên assert test fail ngay?

**Đáp án:** Không nhất thiết. Các send operation và network có race; kiểm tra terminal state, deadline, cleanup và không commit message incomplete, không hardcode số chunk.

## 15. Checklist và tài liệu hiện hành

Trước khi chấp nhận một test suite WebSocket:

1. Có test **hai chiều** và server push riêng, không chỉ test send future?
2. Có xử lý text/binary fragmentation theo `last`, không phụ thuộc số callback?
3. Có case payload rỗng, buffer biên, 1 MiB+17 và dữ liệu Unicode?
4. Có checksum/byte count, không giữ cả payload lớn trong heap?
5. Listener có `request(n>0)` đúng đơn vị và xử lý `CompletionStage` đúng ownership?
6. Có test `sendClose` khác `abort()` và khác mất TCP?
7. Có test server Close giữa payload, kiểm soát bằng barrier và ghi server-side audit?
8. Có thời hạn connect/send/receive/close, cleanup kể cả khi assertion fail?
9. Có đánh giá các race, không assert thứ tự/số byte không được API bảo đảm?
10. Có giới hạn concurrency, log an toàn, TLS và chính sách nghiệp vụ?

**Ghi nhớ:** Java 11 WebSocket hỗ trợ full-duplex nhưng **send hoàn tất ≠ receive hoàn tất ≠ server commit**; payload lớn cần streaming và checksum; `request(n)` đếm callback; `sendClose` đóng output còn `abort` cắt hai phía; test đóng giữa chừng cần server điều khiển và không kết luận cứng từ race.

**Tài liệu chính thức, vẫn phù hợp với JDK hiện đại:**

- [Oracle Java SE 11 — `WebSocket`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html): gửi message/Close, `request`, `abort`, trạng thái input/output.
- [Oracle Java SE 11 — `WebSocket.Listener`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): callback, `last`, returned stage và lifecycle.
- [Oracle Java SE 11 — `WebSocket.Builder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): `connectTimeout`, `buildAsync`.
- [Oracle Java SE 11 — `HttpClient`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): WebSocket builder.
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455): full-duplex, control frames, masking và closing handshake.
- [Oracle Java SE 25 — `WebSocket`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/WebSocket.html): xác nhận API tiếp tục hiện diện trên JDK hiện đại.
