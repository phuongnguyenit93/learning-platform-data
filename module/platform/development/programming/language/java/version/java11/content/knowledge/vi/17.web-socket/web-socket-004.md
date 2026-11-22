# Java 11+ — WebSocket: Nhận thông điệp text và binary

## 1. Bối cảnh: nhận dữ liệu trên một kết nối WebSocket

`java.net.http.WebSocket` là WebSocket client chuẩn của Java, được giới thiệu chính thức trong **Java 11** và vẫn được sử dụng trong các JDK hiện hành. Khác với việc gọi một HTTP request rồi nhận một response duy nhất, WebSocket sau khi bắt tay thành công duy trì một kết nối hai chiều, trên đó phía bên kia có thể gửi **nhiều thông điệp** trong cùng phiên.

Trong Java 11, ứng dụng nhận dữ liệu qua **`WebSocket.Listener`**, thường ghi đè hai callback:

- **`onText(WebSocket, CharSequence, boolean last)`** — nhận một phần dữ liệu text đã được WebSocket giải mã thành chuỗi ký tự.
- **`onBinary(WebSocket, ByteBuffer, boolean last)`** — nhận một phần dữ liệu binary ở dạng byte, chưa gắn charset hoặc cấu trúc ứng dụng.

Cả hai callback nhận cờ **`last`**. Khi `last == true`, **thông điệp hiện tại đã đủ phần**. Khi `last == false`, còn phần tiếp theo của cùng thông điệp; không được xử lý fragment đó như thông điệp hoàn chỉnh nếu giao thức ứng dụng cần toàn bộ dữ liệu.

Điểm then chốt là một *WebSocket message* và một *callback invocation* **không nhất thiết tương ứng 1:1**. Java API có thể gọi `onText` hoặc `onBinary` nhiều lần cho một message; vì thế người học cần hiểu cả **ghép fragment**, **demand/backpressure** và **vòng đời buffer**.

Bài này tập trung vào **nhận** text/binary. Các thao tác `sendText`, `sendBinary` chỉ được đề cập để tránh nhầm với chiều nhận. Ví dụ chạy được sử dụng một WebSocket test double để chủ động phát các fragment; nó **không giả vờ đã kiểm thử handshake hoặc mạng thực tế**.

## 2. Hai callback nhận message: hiểu đúng tham số

| Callback | Kiểu dữ liệu | `last` có nghĩa gì? | Cách xử lý điển hình |
| --- | --- | --- | --- |
| `onText(WebSocket ws, CharSequence data, boolean last)` | `CharSequence` chứa **dữ liệu ký tự**; JDK bảo đảm nó là một chuỗi UTF-16 hợp lệ. | `true` khi phần text này **kết thúc một message text**. | Sao chép/ghép vào `StringBuilder`, hoàn tất message khi `last` đúng, rồi parse/validate theo protocol. |
| `onBinary(WebSocket ws, ByteBuffer data, boolean last)` | Byte nằm **từ `position()` đến `limit()`**, không nhất thiết toàn bộ backing array. | `true` khi phần binary này **kết thúc một message binary**. | Đọc `remaining()` byte cần thiết, sao chép hoặc tiêu thụ đồng bộ, ghép theo message và kiểm tra định dạng. |

### Ví dụ text bị chia thành hai lần callback

Một message text `"Hello Java"` có thể được ứng dụng nhận như:

```java
onText(ws, "Hello ", false);
onText(ws, "Java", true);
```

Đây là ví dụ minh họa **hai lần callback**, không phải chương trình độc lập. Chỉ sau lần thứ hai mới có message hoàn chỉnh `"Hello Java"`. Cờ `last` **không** nói kết nối WebSocket kết thúc; sau đó vẫn có thể có message mới.

Điều này quan trọng ngay cả khi server “thường gửi message ngắn”: không được phụ thuộc vào giả định toàn bộ message luôn đến trong một callback. Việc chia fragment cũng **không** có nghĩa “mỗi frame mạng tương ứng chính xác một lời gọi listener” theo cách bạn kiểm soát được; code phải bám vào cờ `last` của API.

### ByteBuffer: không đọc ngoài vùng `remaining()`

Ví dụ:

```java
byte[] backing = {99, 1, 2, 88};
ByteBuffer buffer = ByteBuffer.wrap(backing);
buffer.position(1);
buffer.limit(3);

byte[] part = new byte[buffer.remaining()]; // 2 byte
buffer.get(part);                           // {1, 2}
```

Nội dung hợp lệ cho callback là hai byte `01 02`, không phải `63 01 02 58`. Đừng dùng `data.array()` như một cách lấy chính xác message vì buffer có thể là **direct buffer**, read-only hoặc có `position/limit` khác toàn bộ mảng. `data.remaining()` và `data.get(...)` là cách dùng chuẩn; có thể dùng `data.slice()` khi cần một view, nhưng phải quan tâm đến vòng đời dữ liệu.

## 3. Bắt đầu nhận dữ liệu: `onOpen` và `WebSocket.request(long)`

`WebSocket` có bộ đếm **demand** cho các lần gọi receive method. Khi WebSocket mới được xây dựng, bộ đếm này bằng 0. Muốn nhận callback, listener phải yêu cầu thêm:

```java
@Override
public void onOpen(WebSocket webSocket) {
    webSocket.request(1);
}
```

`request(1)` cho phép một lần gọi **receive callback** tiếp theo, **không có nghĩa “đã sẵn sàng nhận một message hoàn chỉnh”**. Một message bị chia thành ba callback có thể tiêu thụ ba đơn vị demand.

Theo Java API, các receive method bao gồm `onText`, `onBinary`, `onPing`, `onPong` và `onClose`; riêng `onOpen` và `onError` không tiêu thụ demand theo cơ chế này. WebSocket chỉ gọi receive callback khi có demand thích hợp; `onError` là trường hợp đặc biệt có thể đến mà không cần yêu cầu nhận trước.

Khi đã xử lý xong một fragment và sẵn sàng nhận phần tiếp theo:

```java
@Override
public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
    // Sao chép/tiêu thụ data trước khi hoàn thành stage.
    appendTextFragment(data, last);
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
```

Đoạn trên là minh họa và cần định nghĩa `appendTextFragment`; chương trình hoàn chỉnh ở mục 7 có xử lý cụ thể.

**Lưu ý về default methods:** trong Java 11, implementation mặc định của `WebSocket.Listener.onOpen` gọi `request(1)`; implementation mặc định của `onText` và `onBinary` gọi `request(1)` rồi trả `null`. **Nhưng khi bạn override một method, bạn tự chịu trách nhiệm cấp demand nếu muốn tiếp tục nhận.** Nếu override `onText` mà không gọi `request`, kết nối có thể ngừng đưa các callback tiếp theo do demand đã hết.

Gọi `request(n)` với `n <= 0` không hợp lệ. Đừng vô hạn `request(Long.MAX_VALUE)` như phản xạ nếu ứng dụng có thể xử lý chậm hoặc tích lũy dữ liệu lớn; demand là một cơ chế kiểm soát lượng công việc nhận.

## 4. Hai cơ chế độc lập: demand và `CompletionStage`

Chữ ký `onText`/`onBinary` trả về `CompletionStage<?>`:

```java
CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last);
CompletionStage<?> onBinary(WebSocket ws, ByteBuffer data, boolean last);
```

Stage trả về **không phải** message mới và cũng **không phải** số callback đã yêu cầu. Nó cho WebSocket biết **khi nào listener đã hoàn thành sử dụng đối tượng dữ liệu** để JDK có thể thu hồi hoặc tái sử dụng `CharSequence`/`ByteBuffer` đó.

Theo hợp đồng:

- Trả `CompletableFuture.completedFuture(null)` khi dữ liệu đã được tiêu thụ hoặc sao chép xong, không còn truy cập `data` sau đó.
- Trả `null` cũng được API chấp nhận và được coi như một stage đã hoàn thành bình thường. Dùng completed future làm ví dụ để ý nghĩa rõ ràng.
- Nếu công việc tiếp tục bất đồng bộ và vẫn cần đối tượng dữ liệu gốc, phải bảo đảm stage **chưa hoàn thành** cho đến khi xong; đơn giản hơn và an toàn hơn thường là **sao chép dữ liệu** sang đối tượng do ứng dụng sở hữu trước rồi mới hoàn thành stage.
- **Stage chưa hoàn thành không tự động giảm hoặc đóng băng demand.** Số lượng invocation phụ thuộc lời gọi `request(n)`. WebSocket có thể tiếp tục callback nếu còn demand, không cần chờ stage của fragment trước hoàn thành.
- Nếu listener ném exception hoặc stage hoàn tất ngoại lệ, WebSocket sẽ gọi `onError` theo hợp đồng lỗi (trừ những trường hợp đặc biệt được quy định).

Hậu quả: mẫu “return completed future nhưng giữ lại `ByteBuffer` do JDK cấp để dùng ở luồng khác” **không an toàn**. ByteBuffer có thể bị JDK thu hồi hoặc nội dung thay đổi sau khi stage hoàn thành. Hãy tạo snapshot ngay trong callback:

```java
int count = data.remaining();
byte[] copy = new byte[count];
data.get(copy);
return CompletableFuture.completedFuture(null);
```

Đoạn này là phần thân `onBinary` minh họa; `copy` phải được đưa vào bộ ghép message hoặc tầng xử lý thích hợp trước khi trả. Với text, `StringBuilder.append(data)` thực hiện sao chép các ký tự; `data.toString()` có thể dùng để giữ một `String` ổn định khi cần.

## 5. Ghép message text theo `last`

Trạng thái tối thiểu cho một connection:

```java
private final StringBuilder text = new StringBuilder();
```

Trong `onText`:

```java
text.append(data);
if (last) {
    String complete = text.toString();
    text.setLength(0);
    // Xử lý complete như một message text độc lập.
}
ws.request(1);
return CompletableFuture.completedFuture(null);
```

Đây là đoạn minh họa nằm trong class listener, không phải chương trình độc lập.

Quan trọng:

1. `text` là **bộ tích lũy cho message hiện tại**, không phải tổng mọi message kể từ khi mở kết nối.
2. Chỉ gọi parser nghiệp vụ khi nhận `last == true`, trừ khi protocol ứng dụng **chủ động cho phép streaming partial text**.
3. Sau khi hoàn thành message, phải reset `StringBuilder` để message sau không dính vào message trước.
4. Dữ liệu text được cung cấp dưới dạng chuỗi Unicode hợp lệ. Đừng tự giải mã lại `CharSequence` như thể nó là mảng byte UTF-8.
5. `StringBuilder.length()` đếm **đơn vị UTF-16**, không phải byte UTF-8 hoặc số ký tự hiển thị. Giới hạn kích thước text bằng `length` phải ghi rõ đơn vị đó.
6. Nếu message thực ra chứa JSON, cần parse JSON bằng thư viện JSON phù hợp rồi validate schema. `last == true` chỉ cho biết đủ **message WebSocket**, **không** có nghĩa payload JSON hợp lệ.

Một callback có thể nhận một message text rỗng hợp lệ (0 ký tự) với `last == true`. Đừng bỏ qua rỗng chỉ vì `data.length() == 0`; contract nghiệp vụ mới quyết định chấp nhận hay từ chối message rỗng.

## 6. Ghép message binary theo `last`

Dữ liệu binary nên được coi là **byte nguyên bản**. Một ví dụ đơn giản dùng `ByteArrayOutputStream`:

```java
private final ByteArrayOutputStream binary = new ByteArrayOutputStream();
```

Trong `onBinary`:

```java
int size = data.remaining();
byte[] part = new byte[size];
data.get(part);
binary.write(part, 0, part.length);

if (last) {
    byte[] complete = binary.toByteArray();
    binary.reset();
    // Xử lý complete theo định dạng binary của ứng dụng.
}
ws.request(1);
return CompletableFuture.completedFuture(null);
```

Đây là đoạn minh họa trong một class listener, không chạy độc lập. Dùng buffer theo `position/limit`, không lấy tất cả `capacity()` byte hay gọi `array()` trên giả định buffer luôn có backing array.

Nếu binary có thể là ảnh, tệp nén, Protobuf, CBOR, audio hoặc một binary format riêng, chính **protocol ứng dụng** mới quyết định cách diễn giải. `onBinary` không tự suy ra charset, MIME type hay schema. Chỉ chuyển thành `String` khi payload **được định nghĩa là văn bản** và đã biết charset:

```java
String decoded = new String(completeBytes, StandardCharsets.UTF_8);
```

Đoạn này cần `completeBytes` là mảng byte đầy đủ và import `java.nio.charset.StandardCharsets`. Đối với dữ liệu binary thực sự, việc giải mã tùy tiện có thể làm mất byte không hợp lệ.

`ByteArrayOutputStream` giữ toàn bộ message trong RAM, phù hợp minh họa và payload nhỏ có giới hạn; message lớn nên xử lý theo streaming/file/buffer có quota, không cộng dồn không giới hạn.

## 7. Chương trình Java 11 hoàn chỉnh: test nhận fragment text và binary

Ví dụ dưới đây kiểm thử **logic của `WebSocket.Listener`** một cách xác định, không cần WebSocket server. `TestSocket` là một **test double** triển khai `WebSocket` và ghi nhận các lần `request(n)`. Chương trình chủ động gọi listener với những phần dữ liệu đã dựng sẵn; nó **không mô phỏng toàn bộ bộ đếm demand, framing, handshake, ping/pong hoặc mạng** của một WebSocket thực. Đây là unit test cho việc ghép message, sao chép dữ liệu và xử lý lỗi giới hạn.

Hàm `onText` sao chép ký tự vào `StringBuilder`; `onBinary` lấy **chính xác số byte còn lại** trong buffer và tạo snapshot. Cả hai chỉ hoàn tất message khi `last == true`. Bộ giới hạn text dùng **đơn vị UTF-16**, còn binary dùng **byte**. Listener trả stage đã hoàn thành vì không giữ lại đối tượng dữ liệu do JDK sở hữu.

Lưu đúng tên tệp **`WebSocketReceiveDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public final class WebSocketReceiveDemo {
    static final class ReceivingListener implements WebSocket.Listener {
        private final int maxTextUnits;
        private final int maxBinaryBytes;
        private final StringBuilder text = new StringBuilder();
        private final ByteArrayOutputStream binary = new ByteArrayOutputStream();
        final List<String> textMessages = new ArrayList<>();
        final List<byte[]> binaryMessages = new ArrayList<>();
        String close = "";

        ReceivingListener(int maxTextUnits, int maxBinaryBytes) {
            if (maxTextUnits < 1 || maxBinaryBytes < 1) {
                throw new IllegalArgumentException("Positive limits required");
            }
            this.maxTextUnits = maxTextUnits;
            this.maxBinaryBytes = maxBinaryBytes;
        }

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onText(WebSocket socket, CharSequence part, boolean last) {
            if ((long) text.length() + part.length() > maxTextUnits) {
                throw new IllegalArgumentException("Text message too large");
            }
            text.append(part); // Copy CharSequence before completing the stage.
            if (last) {
                textMessages.add(text.toString());
                text.setLength(0);
            }
            socket.request(1); // Demand counts callbacks, not complete messages.
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onBinary(WebSocket socket, ByteBuffer part, boolean last) {
            int length = part.remaining(); // Read only [position, limit).
            if ((long) binary.size() + length > maxBinaryBytes) {
                throw new IllegalArgumentException("Binary message too large");
            }
            byte[] snapshot = new byte[length];
            part.get(snapshot); // Copy bytes before completing the stage.
            binary.write(snapshot, 0, snapshot.length);
            if (last) {
                binaryMessages.add(binary.toByteArray());
                binary.reset();
            }
            socket.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(WebSocket socket, int statusCode, String reason) {
            close = statusCode + ":" + reason;
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            System.err.println("WebSocket error: " + error.getClass().getSimpleName());
        }
    }

    static final class TestSocket implements WebSocket {
        long requested;

        @Override
        public void request(long n) {
            if (n <= 0) throw new IllegalArgumentException("n must be positive");
            requested = Math.addExact(requested, n);
        }

        @Override
        public CompletableFuture<WebSocket> sendText(CharSequence text, boolean last) {
            throw new UnsupportedOperationException("No network in this fixture");
        }

        @Override
        public CompletableFuture<WebSocket> sendBinary(ByteBuffer data, boolean last) {
            throw new UnsupportedOperationException("No network in this fixture");
        }

        @Override
        public CompletableFuture<WebSocket> sendPing(ByteBuffer data) {
            throw new UnsupportedOperationException("No network in this fixture");
        }

        @Override
        public CompletableFuture<WebSocket> sendPong(ByteBuffer data) {
            throw new UnsupportedOperationException("No network in this fixture");
        }

        @Override
        public CompletableFuture<WebSocket> sendClose(int code, String reason) {
            throw new UnsupportedOperationException("No network in this fixture");
        }

        @Override
        public String getSubprotocol() { return ""; }

        @Override
        public boolean isOutputClosed() { return false; }

        @Override
        public boolean isInputClosed() { return false; }

        @Override
        public void abort() { }
    }

    static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte b : bytes) {
            if (result.length() != 0) result.append(' ');
            result.append(String.format("%02X", b & 0xFF));
        }
        return result.toString();
    }

    public static void main(String[] args) {
        ReceivingListener listener = new ReceivingListener(64, 64);
        TestSocket socket = new TestSocket();

        listener.onOpen(socket);
        System.out.println("open-demand=" + socket.requested);

        StringBuilder mutableText = new StringBuilder("Xin ");
        listener.onText(socket, mutableText, false).toCompletableFuture().join();
        mutableText.setLength(0); // Proves that the fragment was copied.
        listener.onText(socket, "chao world", true).toCompletableFuture().join();

        byte[] underlying = {99, 1, 2, 88};
        ByteBuffer slice = ByteBuffer.wrap(underlying);
        slice.position(1);
        slice.limit(3);
        listener.onBinary(socket, slice, false).toCompletableFuture().join();
        underlying[1] = 0;
        underlying[2] = 0;

        byte[] lastPart = {(byte) 0xFF};
        listener.onBinary(socket, ByteBuffer.wrap(lastPart), true)
                .toCompletableFuture().join();
        lastPart[0] = 0;

        System.out.println("text-count=" + listener.textMessages.size());
        System.out.println("text-value=" + listener.textMessages.get(0));
        System.out.println("binary-count=" + listener.binaryMessages.size());
        System.out.println("binary-hex=" + hex(listener.binaryMessages.get(0)));
        System.out.println("receive-requests=" + socket.requested);

        listener.onClose(socket, 1000, "done").toCompletableFuture().join();
        System.out.println("close=" + listener.close);

        ReceivingListener small = new ReceivingListener(4, 3);
        TestSocket secondSocket = new TestSocket();
        small.onOpen(secondSocket);
        try {
            small.onText(secondSocket, "12345", true);
            System.out.println("oversized-text=unexpected-success");
        } catch (IllegalArgumentException ex) {
            System.out.println("oversized-text=IllegalArgumentException");
        }
    }
}
```

Biên dịch và chạy trên JDK 11 trở lên. `--release 11` xác minh tương thích cú pháp/API Java 11:

```bash
javac -encoding UTF-8 --release 11 WebSocketReceiveDemo.java
java WebSocketReceiveDemo
```

**Stdout chính xác đã kiểm thử:**

```text
open-demand=1
text-count=1
text-value=Xin chao world
binary-count=1
binary-hex=01 02 FF
receive-requests=5
close=1000:done
oversized-text=IllegalArgumentException
```

Diễn giải:

1. `open-demand=1`: `onOpen` gọi `request(1)` một lần.
2. `text-count=1` và `text-value=Xin chao world`: hai lần `onText` (fragment đầu `last=false`, fragment cuối `last=true`) được ghép thành **một message**. `mutableText.setLength(0)` sau callback đầu không thay đổi message đã tích lũy vì listener đã sao chép dữ liệu.
3. `binary-count=1`, `binary-hex=01 02 FF`: hai fragment binary thành một message ba byte. Callback chỉ đọc vùng `position=1..limit=3` của buffer đầu; các thay đổi backing array sau callback không làm thay đổi message đã lưu.
4. `receive-requests=5`: một lần `request(1)` từ `onOpen` + bốn lần `request(1)` từ hai callback text và hai callback binary. **Đây là số lời gọi demand của test double**, không phải kết quả đo bộ đếm nội bộ của một WebSocket thật.
5. `close=1000:done`: listener nhận thông tin kết thúc giả lập từ `onClose`.
6. `oversized-text=IllegalArgumentException`: test double đưa fragment dài hơn giới hạn 4 đơn vị UTF-16; listener từ chối. Trong kết nối WebSocket thật, nếu listener ném exception, runtime có thể kết thúc bằng `onError` theo hợp đồng. Test double không tự gọi `onError` vì không cài đặt cơ chế dispatch thật.

## 8. Dùng listener với WebSocket client thật

Khi nối tới một WebSocket server được phép truy cập, dùng builder của `HttpClient`:

```java
// Minh họa tích hợp, KHÔNG phải chương trình chạy độc lập.
// Cần import HttpClient, WebSocket, URI, Duration.
// Địa chỉ phải được cấu hình cho một WebSocket server thực.
WebSocket.Listener listener = new ReceivingListener(1_000_000, 2_000_000);

CompletableFuture<WebSocket> connected = HttpClient.newHttpClient()
        .newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .buildAsync(URI.create("wss://ws.example.com/events"), listener);

// Sau khi handshake thành công, WebSocket sẽ dùng listener để nhận dữ liệu.
// Xử lý connected và vòng đời kết nối theo thiết kế ứng dụng.
```

Tên `ReceivingListener` là class ở mục 7, nhưng trong dự án thật nên thiết kế một listener riêng có giao diện callback/queue/handler cho logic nghiệp vụ thay vì giữ vô hạn mọi message trong `List`. URI `wss://ws.example.com/events` chỉ là **ví dụ**, không phải endpoint được chạy thử.

Giải thích thêm:

- **`ws://`** là WebSocket không dùng TLS; **`wss://`** bảo vệ kết nối bằng TLS. Khi cần xác thực và dữ liệu nhạy cảm, ưu tiên `wss://`.
- `buildAsync(URI, listener)` thực hiện quá trình kết nối/handshake bất đồng bộ và trả `CompletableFuture<WebSocket>`. Hoàn thành handshake **không đồng nghĩa mọi message tương lai đã nhận xong**.
- `connectTimeout` giới hạn thời gian thiết lập kết nối theo API, không tự giới hạn tổng vòng đời message, idle timeout hoặc toàn bộ công việc trong listener.
- Với token/cookie/header bổ sung, dùng API `WebSocket.Builder.header(...)` khi được cho phép; không tự chỉnh các header điều khiển handshake WebSocket. Không hard-code secret hoặc đưa token vào log.
- `WebSocket` được dùng theo từng connection. `WebSocket.Listener` có thể nhận callback từ nhiều WebSocket nếu cố tình chia sẻ, khi đó phải quản lý trạng thái và thread-safety theo connection.

**Không gọi `connected.join()` hay chờ các thao tác chặn trên event loop/UI thread chỉ để “biến async thành sync”**. Trong ứng dụng giao diện hoặc dịch vụ nhiều kết nối, xử lý hoàn tất/ngoại lệ của future mà không khóa luồng điều phối.

## 9. Lỗi, đóng kết nối và control frames

### `onClose`

```java
@Override
public CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason) {
    // Ghi trạng thái, giải phóng message đang ghép dở nếu cần.
    return CompletableFuture.completedFuture(null);
}
```

`onClose` được gọi khi nhận Close message. Đây là lời gọi cuối của listener đối với kết nối đó theo hợp đồng API; sau `onClose` không còn callback nhận dữ liệu khác. Stage trả về từ `onClose` tham gia điều phối việc đóng output, không mang cùng ý nghĩa trả dữ liệu như `onText`/`onBinary`.

Nếu một message vẫn còn fragment chưa hoàn thành khi kết nối đóng, hãy **bỏ hoặc đánh dấu lỗi message dở dang theo giao thức**, không tự coi đó là message hoàn chỉnh. Với ứng dụng cần đóng chủ động, `WebSocket.sendClose(code, reason)` là thao tác **gửi** close, khác với `onClose` là callback **nhận** close.

### `onError`

```java
@Override
public void onError(WebSocket ws, Throwable error) {
    // Ghi nhận lỗi, dọn state; không ném tiếp một exception khác.
}
```

`onError` có thể đến bất kỳ lúc nào sau `onOpen` và theo Javadoc, khi bắt đầu callback này cả input/output đã đóng. Đây là callback cuối cùng cho WebSocket đó. Không ném exception mới từ `onError` vì hành vi kết quả không được xác định rõ. Phân biệt **I/O hoặc protocol error** với **lỗi validation nội dung ứng dụng** nếu muốn ứng dụng tiếp tục sử dụng kết nối khi nhận một message sai nghiệp vụ: không nên ném bừa từ listener trong trường hợp chỉ muốn từ chối một record.

### Ping/Pong

Ngoài text/binary, WebSocket có `onPing` và `onPong`. Khi không override, implementation mặc định của listener yêu cầu thêm một lần callback. JDK WebSocket tự động gửi Pong tương ứng khi nhận Ping theo hợp đồng chuẩn của nó; thông thường bạn **không** cần viết `sendPong` thủ công trong `onPing`.

Nếu override `onPing`/`onPong`, cũng phải nghĩ đến `request(1)` và vòng đời `ByteBuffer`. Ping/Pong là **control frames**, không phải phần text/binary cần ghép vào message của bạn. Một message đang bị phân mảnh có thể có control frames xen giữa.

## 10. Vòng đời, đồng thời và xử lý nặng

Javadoc quy định các callback của **cùng một WebSocket** được gọi theo thứ tự nghiêm ngặt, không reentrant: lời gọi listener tiếp theo chỉ bắt đầu sau khi lời gọi trước kết thúc. Điều này giúp giữ `StringBuilder` và `ByteArrayOutputStream` làm state của **một kết nối** mà không cần khóa quanh từng thao tác.

Tuy nhiên, khi cùng một listener được dùng cho **nhiều WebSocket**, callback từ các connection khác nhau **có thể chạy đồng thời** và các buffer đơn lẻ sẽ dễ trộn message. Vì vậy:

- Mỗi kết nối nên có **listener/state riêng**, hoặc gắn state với WebSocket và bảo vệ thread-safety đầy đủ.
- Không dùng bộ `StringBuilder` toàn cục cho tất cả client.
- Không làm truy vấn DB blocking, `Thread.sleep`, `join/get` chờ, parse khối dữ liệu cực lớn hoặc tác vụ CPU kéo dài ngay trong callback nếu có thể gây nghẽn nhận dữ liệu.
- Nếu cần xử lý nặng, **sao chép byte/text** cần thiết rồi đưa vào một executor/hàng đợi có giới hạn. Chỉ `request(1)` khi còn khả năng tiếp nhận theo chính sách backpressure.
- Hãy giám sát memory, queue depth, số connection và message-per-second; một message có thể chia thành nhiều fragment và mỗi fragment có thể tiêu tốn tài nguyên.

**Không dùng future trả về như “van lưu lượng” duy nhất:** `CompletionStage` quản lý vòng đời dữ liệu, còn `request` quản lý số lần nhận callback. Hai cơ chế liên quan nhưng **độc lập**. Khi gửi tác vụ xử lý sang thread khác, cân nhắc thiết kế queue riêng và cấp demand sau khi đã xử lý hoặc đã nhận trách nhiệm với message an toàn.

## 11. Giới hạn kích thước và dữ liệu không tin cậy

Một WebSocket nhận dữ liệu từ môi trường mạng có thể gặp payload rất lớn hoặc số lượng fragment nhiều. Để tránh lỗi:

| Vấn đề | Phòng vệ |
| --- | --- |
| Text message quá dài | Giới hạn số đơn vị UTF-16, hoặc giới hạn byte ở tầng có quyền truy cập dữ liệu byte; không nhầm `String.length()` là byte UTF-8. |
| Binary message quá dài | Kiểm tra `(long) accumulatedBytes + data.remaining() <= MAX` **trước** khi cấp phát mảng. |
| Fragment nhỏ nhưng quá nhiều | Có giới hạn tổng message, deadline/timeout và số fragment khi cần; không lặp tích lũy vô hạn. |
| Bộ nhớ tăng do giữ mọi message | Giao message cho consumer/queue có giới hạn, không giữ `ArrayList` vô hạn như ví dụ demo. |
| Nội dung binary sai schema | Parse theo codec định nghĩa (CBOR/Protobuf/ảnh/định dạng riêng), kiểm tra header, type, length và tính hợp lệ. |
| Nội dung text sai JSON/schema | Chỉ parse sau khi message text hoàn chỉnh; kiểm tra parser, schema và nghiệp vụ. |
| Dữ liệu ByteBuffer bị thay đổi ngoài ý muốn | Snapshot trong phạm vi callback hoặc giữ stage chưa hoàn thành đúng quy tắc, không giữ buffer sau completed stage. |
| Mất kết nối khi đang ghép message | Hủy/đánh dấu lỗi phần chưa đủ; báo trạng thái và không tạo một message giả. |
| Tải xử lý chậm hơn tốc độ nhận | Điều tiết qua `request(n)` và queue/backpressure; không xin vô hạn demand rồi giữ vô hạn dữ liệu. |

Trong ví dụ chạy được, phép cộng kích thước dùng `(long) text.length() + part.length()` hoặc `(long) binary.size() + length` để tránh tràn `int` khi kiểm tra trước. Chỉ sau khi đủ quota mới cấp mảng mới.

Tầng ứng dụng vẫn cần giới hạn số message, thời gian chờ, kết nối đồng thời và số lần retry/reconnect. **`wss` bảo vệ kênh truyền**, không tự bảo đảm payload phù hợp schema hoặc người gửi có quyền thực hiện tác vụ.

## 12. Kiểm thử nhận text/binary như thế nào?

Hãy phân loại test theo hành vi, không chỉ kiểm tra “callback có chạy”:

| Test | Fixture | Assertion |
| --- | --- | --- |
| Text một fragment | `onText(..., "hello", true)` | Một message `"hello"` được giao đúng một lần. |
| Text nhiều fragment | `"Xin "`/`false`, `"chao"`/`true` | Chỉ sau fragment cuối mới hoàn thành một message. |
| Text mutable/ephemeral | Truyền `StringBuilder`, sau callback sửa nguồn | Kết quả vẫn đúng nhờ đã copy trong callback. |
| Binary nhiều fragment | Một buffer có `position/limit`, sau đó fragment cuối | Byte cuối cùng đúng thứ tự, không lấy byte thừa. |
| Binary backing array bị sửa | Ghi đè mảng gốc sau completed stage | Snapshot đã lưu không đổi. |
| Demand | `onOpen` và mỗi receive callback gọi `request(1)` | Đếm **invocation demand**, không nhầm với message count. |
| Message rỗng | Text `""`/binary buffer rỗng với `last=true` | Tùy contract, hoàn tất message rỗng đúng cách. |
| Đóng giữa message | `last=false` rồi `onClose` | Không phát message nửa chừng như complete. |
| Payload vượt quota | Fragment gây vượt max | Báo lỗi rõ, không mở rộng buffer vô hạn. |
| Message sai cấu trúc | Text JSON/schema sai, binary sai codec | Chặn ở tầng parse/validate, tách biệt khỏi lỗi WebSocket transport. |
| Hành vi mạng thật | WebSocket server cục bộ có handshake, fragment, ping/close | Kiểm tra callback thực, thời gian sống kết nối, TLS/proxy/auth ở môi trường test riêng. |

Ví dụ mục 7 là **unit test listener** bằng test double, vì vậy không có bảo đảm WebSocket thực sẽ phát chính xác từng fragment giống fixture. Khi cần xác nhận event runtime, nên dùng **server WebSocket test có kiểm soát** (không gọi server production), khẳng định **message hoàn chỉnh**, không phụ thuộc số frame/callback cho một message.

Trên CI, thay các lệnh `System.out.println` bằng assertions (`assertEquals`, `assertArrayEquals`, `assertThrows`), và tạo fixture mới cho mỗi ca để tránh trộn state. Trường hợp vượt hạn mức là negative test; với socket thật, lựa chọn đóng connection hay trả lỗi application-level phải theo protocol nghiệp vụ.

## 13. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`onText` được gọi đúng một lần cho mỗi message text.” | Không bảo đảm; dựa vào `last` để ghép đủ message. |
| “`last=true` nghĩa là WebSocket đóng.” | Chỉ kết thúc **message hiện tại**, không phải connection. |
| “`request(1)` nghĩa là xin một message hoàn chỉnh.” | Nó cấp **một lần gọi receive method**; message có thể có nhiều callback. |
| “`CompletionStage` chưa hoàn thành thì callback mới sẽ không đến.” | Không bảo đảm; demand là cơ chế riêng. |
| “Override `onText` nhưng bỏ `request` vẫn luôn nhận tiếp.” | Khi demand hết, listener không còn được gọi receive method như mong muốn. |
| “Trả completed future rồi giữ `ByteBuffer` đọc sau cũng an toàn.” | Không; buffer có thể bị thu hồi/tái sử dụng sau khi stage complete. |
| “`ByteBuffer.array()` luôn chính xác message.” | Sai: direct buffer, read-only, `position`/`limit` và backing array làm giả định này không đúng. |
| “`ByteBuffer.capacity()` là số byte mới nhận.” | Sai: dùng `remaining()` trong vùng `position..limit`. |
| “Dữ liệu binary luôn là UTF-8.” | Không; byte có thể là bất kỳ định dạng nào. |
| “Text nhận được thì JSON/schema chắc chắn đúng.” | Không; parse và validate sau khi ghép complete message. |
| “Một listener có thể an toàn dùng chung bộ buffer cho nhiều WebSocket.” | Callback giữa các kết nối có thể đồng thời; cần state riêng/đồng bộ. |
| “Text limit bằng `String.length()` là giới hạn số byte trên mạng.” | Không; nó đếm **UTF-16 code units**. |
| “Có thể xin vô hạn demand để tránh backpressure.” | Dễ khiến ứng dụng nhận nhanh hơn khả năng xử lý; cần giới hạn. |
| “Ping là một phần của message binary cần ghép.” | Ping/Pong là control frames và callback riêng. |
| “Test double mục 7 chứng minh handshake/proxy/TLS hoạt động.” | Không; chỉ kiểm thử logic listener và lời gọi demand. |

## 14. Checklist triển khai Java 11+

1. Tạo `WebSocket.Listener` cho **từng connection** hoặc quản lý state riêng theo socket.
2. Trong `onOpen`, gọi `request(1)` hoặc thiết lập demand có tính toán.
3. Trong `onText`, sao chép `CharSequence`, kiểm tra quota và ghép fragments; chỉ xử lý hoàn chỉnh khi `last=true`.
4. Trong `onBinary`, dùng `data.remaining()`/`data.get(...)` trong phạm vi `position..limit`, sao chép trước khi completed stage.
5. Phân biệt demand `request(n)` và vòng đời dữ liệu `CompletionStage`; không giữ buffer sau khi báo đã hoàn tất.
6. Cấp demand tiếp theo theo năng lực xử lý và chính sách queue; không chờ tác vụ nặng trực tiếp trong listener.
7. Xác định rõ encoding/codec và parser ở tầng ứng dụng; binary không mặc định là text.
8. Xử lý `onClose`/`onError`, dọn message đang dang dở, tài nguyên và trạng thái kết nối.
9. Đặt hạn mức cho số byte/ký tự, số fragment, thời gian và số message; không giữ toàn bộ lịch sử trong RAM.
10. Unit-test fragment và data snapshot bằng test double; integration-test handshake, ping/pong, đóng và dữ liệu thật bằng server test riêng.
11. Với dịch vụ thật, dùng `wss://` cho dữ liệu cần bảo mật và kiểm soát xác thực/ủy quyền; WebSocket không tự validate schema.

### Tài liệu chính thức

- [Oracle Java SE 11 — `WebSocket.Listener`, `onText`, `onBinary`, `onOpen`, `onClose`, `onError`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
- [Oracle Java SE 11 — `WebSocket`, bộ đếm demand, `request(long)`, `sendText`, `sendBinary`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html)
- [Oracle Java SE 11 — `WebSocket.Builder`: `buildAsync` và `connectTimeout`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Builder.html)
- [Oracle Java SE 25 — `WebSocket.Listener`: hợp đồng callback tiếp tục được duy trì](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
- [Oracle Java SE 25 — `WebSocket`: hợp đồng demand và thông điệp hiện hành](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/WebSocket.html)
