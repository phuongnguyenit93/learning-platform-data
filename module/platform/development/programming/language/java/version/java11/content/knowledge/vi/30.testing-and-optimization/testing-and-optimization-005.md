# WebSocket phân mảnh, backpressure và đóng kết nối (Java 11+)

**Chủ đề cha: Kiểm thử và tối ưu.** Client WebSocket của Java 11 (`java.net.http.WebSocket`) cho phép trao đổi dữ liệu hai chiều, lâu dài và bất đồng bộ. Các lỗi khó tái hiện thường xuất hiện khi message bị **phân mảnh**, ứng dụng nhận quá nhanh hoặc quên cấp **demand**, và kết nối không được **đóng đúng cách**. Một chương trình chạy tốt với echo server nhỏ vẫn có thể mất dữ liệu, tăng heap hoặc treo khi gặp message lớn, Ping xen giữa fragments, slow consumer hay peer ngắt mạng.

Bài này tập trung vào ba kỹ thuật **còn áp dụng trên các JDK hiện đại**: xử lý text/binary message phân mảnh bằng `last`; backpressure đầu vào qua `request(n)` và hàng đợi đầu ra có giới hạn; thực hiện close handshake với `sendClose/onClose`, timeout và `abort`. Mã dùng **Java 11+**, không yêu cầu thư viện WebSocket cũ/legacy. Có ví dụ tích hợp chạy trên localhost bằng JDK 11, kiểm tra fragmentation, Unicode, Ping, binary, close và một bộ test cases cho production.

## 1. Ba khái niệm: TCP bytes, WebSocket frame và message

| Tầng | Ý nghĩa | Có tương ứng 1-1 với callback Java không? |
| --- | --- | --- |
| TCP | Dòng bytes trên socket | Không |
| WebSocket frame | Frame RFC 6455 chứa opcode, FIN, payload | Không bảo đảm |
| WebSocket message | Logical text/binary message; có thể gồm nhiều frames | Có thể giao qua nhiều callbacks |

Một **text message** có thể có nhiều wire frames:

```text
Logical text message: "Xin chào"
    |
    +-- Text frame       opcode=0x1  FIN=0, payload="Xin ch" + byte 0xC3
    +-- Ping control     opcode=0x9  FIN=1
    +-- Continuation     opcode=0x0  FIN=1, payload=byte 0xA0 + "o"
    |
    v
WebSocket.Listener
    onText(ws, ..., last=false)
    onPing(ws, ...)
    onText(ws, ..., last=true)
    |
    v
Application xử lý MỘT text message: "Xin chào"
```

**Sơ đồ minh họa semantics**, không cam kết số lần callback trùng đúng số wire frames. JDK có thể phân phối khác nhau; ứng dụng phải tôn trọng **`last=true` là cuối logical message**, không tự suy frame boundaries từ callback. Theo **RFC 6455 §5.4**, control frames (Ping, Pong, Close) **có thể chen giữa** data fragments; control frames **không phân mảnh** và payload tối đa 125 byte.

Một text message dài là **một** message dù nhận qua năm `onText` calls. Một Ping ở giữa **không** kết thúc text message. Khi ứng dụng cần parse JSON, không được đưa một fragment chưa hoàn chỉnh cho JSON parser rồi coi nó là message hoàn chỉnh, trừ khi parser thực sự hỗ trợ incremental parsing.

## 2. API của Java 11

Các API nằm trong module `java.net.http`:

| API | Vai trò |
| --- | --- |
| `HttpClient.newWebSocketBuilder()` | Tạo WebSocket client builder |
| `WebSocket.Builder.buildAsync(URI, Listener)` | Handshake và kết nối bất đồng bộ |
| `WebSocket.sendText(data, last)` | Gửi text data và quyết định message đã kết thúc chưa |
| `WebSocket.sendBinary(buffer, last)` | Gửi binary data với ByteBuffer |
| `WebSocket.sendPing/sendPong` | Gửi control frames, tối đa 125 bytes |
| `WebSocket.request(n)` | Cấp quyền cho n lần gọi receive callback |
| `WebSocket.sendClose(status, reason)` | Bắt đầu graceful closing chiều gửi |
| `WebSocket.abort()` | Đóng ngay cả chiều gửi/nhận |
| `WebSocket.isInputClosed/isOutputClosed` | Đọc trạng thái hai chiều |
| `WebSocket.Listener.onOpen` | Thông báo đã kết nối, nên cấp demand ban đầu |
| `Listener.onText/onBinary` | Nhận text/binary, có thể phân mảnh |
| `Listener.onPing/onPong` | Nhận control frames |
| `Listener.onClose/onError` | Callback kết thúc nhận |

**Java 11 cung cấp WebSocket client chứ không cung cấp một WebSocket server hoàn chỉnh trong package này.** Test server ở mục 11 chỉ là server tối giản bằng socket để tạo wire frames có kiểm soát.

### Gửi message phân mảnh

Giả sử `WebSocket ws` đã được kết nối:

```java
ws.sendText("Xin ", false)
  .thenCompose(socket -> socket.sendText("chào", true));
```

- `false`: text message **chưa hoàn tất**.
- `true`: hoàn tất message.
- `thenCompose` đợi future gửi phần đầu hoàn tất **trước khi** gửi phần sau.

Gửi binary:

```java
ByteBuffer a = ByteBuffer.wrap(new byte[] {1, 2});
ByteBuffer b = ByteBuffer.wrap(new byte[] {3, 4});

ws.sendBinary(a, false)
  .thenCompose(socket -> socket.sendBinary(b, true));
```

Đây là hai đoạn **minh họa**, cần khai báo/import `WebSocket`/`ByteBuffer` và xử lý failed futures trong mã thực tế.

**Không chen một binary message khi text message trước vẫn `last=false`.** Javadoc `WebSocket` mô tả một send data đang pending hoặc gửi loại data khác khi message trước chưa hoàn tất có thể khiến `CompletableFuture` hoàn tất exceptionally với `IllegalStateException`.

### Send future không phải xác nhận của remote

`sendText`/`sendBinary` trả `CompletableFuture<WebSocket>`. Future hoàn tất **bình thường** nghĩa thao tác gửi đã hoàn tất theo API; **không chứng minh** peer đã đọc, xử lý nghiệp vụ hoặc commit transaction. Nếu yêu cầu delivery/processing guarantee, thiết kế **application-level ACK** có sequence ID, timeout, retry và idempotency.

### Vòng đời dữ liệu gửi

- **Text:** không thay đổi đối tượng `CharSequence` khi send future chưa hoàn tất. Nếu dùng `StringBuilder` khả biến, snapshot thành `String` trước khi gửi.
- **Binary:** ByteBuffer gửi bytes từ `position` tới `limit`. Khi hoàn tất bình thường, buffer thường đã được tiêu thụ; **không sửa/access buffer khi send chưa xong**.
- Dù gửi nhiều fragments, đừng giữ một collection vô hạn của payloads/futures trong heap.

## 3. Nhận fragments: chú ý last và vòng đời buffer

Hai callback quan trọng:

```java
CompletionStage<?> onText(WebSocket ws,
                          CharSequence data,
                          boolean last);

CompletionStage<?> onBinary(WebSocket ws,
                            ByteBuffer data,
                            boolean last);
```

**Đoạn này mô tả signatures**, không phải chương trình main.

Ví dụ:

```text
onText("ab", false)
onText("cd", true)
=> một message "abcd"

onBinary([1,2], false)
onBinary([3,4], true)
=> một message [1,2,3,4]
```

Cần giữ trạng thái assembling **riêng theo WebSocket connection** và reset khi `last=true`. Nếu một listener object được dùng cho nhiều WebSockets, callbacks từ **những WebSockets khác nhau** có thể xen kẽ/chạy đồng thời; không dùng chung một StringBuilder không đồng bộ để trộn messages.

### Text và Unicode

RFC 6455 cho phép một ký tự UTF-8 nhiều byte bị cắt giữa các wire frames. Client JDK đưa vào `onText` một `CharSequence` chứa dữ liệu UTF-16 hợp lệ. Không lấy một frame rồi tự decode như thể nó là một chuỗi UTF-8 hoàn chỉnh. Ứng dụng có thể copy fragment bằng `String part = data.toString();` rồi nối tới `last=true`.

**`String.length()` đếm UTF-16 code units**, không phải byte UTF-8, code points hay số grapheme. Nếu protocol đặt giới hạn 1 MiB bytes, phải dùng byte budget tương ứng và tốt hơn là giới hạn ở tầng server/gateway trước khi dữ liệu bị copy vào heap.

### Binary với position/limit

Một ByteBuffer không nhất thiết có backing array. Đây là cách copy hợp lệ:

```java
byte[] bytes = new byte[data.remaining()];
data.get(bytes);
```

Đoạn trên giả sử biến `ByteBuffer data` trong `onBinary`. Không gọi `data.array()` rồi tự cho rằng mảng bắt đầu ở offset 0; direct/read-only buffers có thể không có array.

**Quan trọng về vòng đời:** khi `onText/onBinary` trả `CompletionStage` đã hoàn tất, WebSocket được phép reclaim dữ liệu callback. Không giữ `CharSequence`/`ByteBuffer` do JDK cấp để đọc sau khi stage completed; copy hoặc hoàn tất xử lý **trước** khi stage kết thúc.

## 4. request(n): demand tính theo callbacks, không phải messages

Theo Javadoc Java 11:

- Một WebSocket vừa tạo có **receive counter = 0**.
- `request(n)` với `n > 0` cộng thêm credit.
- Mỗi lần gọi **một** trong `onText`, `onBinary`, `onPing`, `onPong` hoặc `onClose` thì trừ một credit.
- Khi counter = 0, WebSocket **không gọi receive callbacks tiếp**.
- `onOpen` và `onError` **không** tiêu thụ credit.
- `onClose` hoặc `onError` là terminal callback: về sau không có các callbacks khác của cùng WebSocket.

Listener an toàn bắt đầu:

```java
@Override
public void onOpen(WebSocket ws) {
    ws.request(1);
}
```

**Nếu không override `onOpen`**, default implementation đã gọi `request(1)`. Nhưng nếu **override mà quên gọi request**, bạn thay thế hành vi mặc định và có thể không nhận được payload nào.

**`request(1)` cho phép một callback, không phải một message.** Một message nhiều fragments cần nhiều credits; Ping/Pong xen vào cũng tiêu thụ credit. `request(0)` hoặc giá trị âm ném `IllegalArgumentException`.

| Cấu hình | Hậu quả |
| --- | --- |
| `request(1)` sau xử lý fragment | Dễ điều tiết một callback mỗi lần |
| `request(100)` | Tối đa thêm 100 receive callbacks |
| `request(Long.MAX_VALUE)` | Gần như vô hạn credit, không tạo backpressure hữu ích |
| Không request sau fragment `last=false` | Có thể đứng yên vì chưa đủ credit để nhận phần tiếp |
| Không request sau `onPing` | Có thể không nhận fragments tiếp theo |
| Request ngay cả khi queue đã quá tải | Ứng dụng tự tạo backlog/memory pressure |

### Hai cơ chế độc lập: request và CompletionStage

`CompletionStage<?>` mà receive callback trả về **không tự tăng request counter**. Javadoc thậm chí nêu rõ có thể nhận thêm callbacks khi stage trước **chưa** completed, nếu counter vẫn còn dương. Stage được dùng để báo **khi nào buffer/data có thể reclaim**, không làm nhiệm vụ cấp demand.

```text
request(1)          => permit cho 1 callback nhận
returned stage      => báo lúc data/buffer callback được release

Thực hiện backpressure:
    Nhận callback -> copy/process -> khi xử lý xong
                    -> request(1) cho callback tiếp theo
```

Nếu muốn **một** callback xử lý tại một thời điểm, đừng cấp nhiều credits từ trước. Với async processing, cấp demand mới ở completion của công việc, không chỉ ở lúc enqueue vào hàng đợi vô hạn.

## 5. Listener giới hạn số bytes/message

Ví dụ sau là **class độc lập có thể biên dịch**, nhưng không phải ứng dụng main tự kết nối. Nó ghép text/binary với giới hạn, xử lý đồng bộ nhỏ và cấp demand tuần tự.

### Tệp `BoundedListener.java`

```java
import java.io.ByteArrayOutputStream;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public final class BoundedListener
        implements WebSocket.Listener {
    private static final int MAX_TEXT_UNITS = 4096;
    private static final int MAX_BINARY_BYTES = 4096;

    private final StringBuilder text = new StringBuilder();
    private final ByteArrayOutputStream binary =
            new ByteArrayOutputStream();

    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket ws, CharSequence data, boolean last) {
        String part = data.toString();
        if (part.length() > MAX_TEXT_UNITS - text.length()) {
            ws.abort();
            return CompletableFuture.completedFuture(null);
        }

        text.append(part);
        if (last) {
            System.out.println("text units: " + text.length());
            text.setLength(0);
        }
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onBinary(
            WebSocket ws, ByteBuffer data, boolean last) {
        if (data.remaining() >
                MAX_BINARY_BYTES - binary.size()) {
            ws.abort();
            return CompletableFuture.completedFuture(null);
        }
        byte[] chunk = new byte[data.remaining()];
        data.get(chunk);
        binary.write(chunk, 0, chunk.length);

        if (last) {
            System.out.println(
                    "binary bytes: " + binary.size());
            binary.reset();
        }
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onPing(
            WebSocket ws, ByteBuffer ping) {
        // JDK tự đáp Pong nhưng callback vẫn tiêu thụ credit.
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onPong(
            WebSocket ws, ByteBuffer pong) {
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }
}
```

Biên dịch bằng:

```bash
javac --release 11 -encoding UTF-8 BoundedListener.java
```

**Giới hạn:** ví dụ tính text theo **UTF-16 units**, không phải UTF-8 bytes. Phần đầu tiên do JDK giao vẫn có thể rất lớn; ứng dụng cũng phải giới hạn inbound size ở server/proxy và trên transport. Khi message bị chia vô hạn fragments nhưng không bao giờ `last=true`, code không tăng buffer vượt giới hạn, nhưng cần thêm **timeout và connection quota** để không giữ partial state mãi.

### Khi cần xử lý bất đồng bộ

Một pattern minh họa (giả sử `processChunkAsync(copy, last)` xử lý có hạn mức và trả `CompletionStage<Void>`):

```java
@Override
public CompletionStage<?> onBinary(
        WebSocket ws, ByteBuffer data, boolean last) {
    byte[] copy = new byte[data.remaining()];
    data.get(copy);

    CompletionStage<Void> processing =
            processChunkAsync(copy, last);

    processing.whenComplete((result, error) -> {
        if (error == null) {
            ws.request(1);
        } else {
            ws.abort();
        }
    });
    return processing;
}
```

Đây là đoạn **minh họa**, không phải chương trình đầy đủ. Khi chỉ có một credit, JVM sẽ không gọi receive callback tiếp cho đến khi công việc hoàn thành và `request(1)` được phát. Vẫn cần **bounded executor/queue**, timeout và error cleanup; hoàn tất stage mà không cấp credit mới có thể làm hệ thống ngừng nhận.

## 6. Backpressure chiều gửi: không để producer làm phình queue

Các send methods như `sendText` và `sendBinary` trả `CompletableFuture<WebSocket>`. Nếu gửi thêm data trong lúc data send trước còn pending, hoặc đổi loại message khi fragment chưa hoàn tất, API có thể trả future hoàn tất **exceptionally** với `IllegalStateException`. Phải **tuần tự hóa các thao tác gửi data** cho một WebSocket.

```java
CompletableFuture<WebSocket> chain =
        CompletableFuture.completedFuture(ws);
chain = chain.thenCompose(
        socket -> socket.sendText("one", true));
chain = chain.thenCompose(
        socket -> socket.sendText("two", true));
```

Đoạn trên minh họa cho biến `WebSocket ws` đã kết nối. **Không** tiếp tục tạo hàng triệu mắt xích future bằng cách append vô hạn, vì queue/closures/payload có thể tăng memory dù send operations được serialize.

Một thiết kế production gồm:

1. **Bounded outbound queue** theo số messages **và số bytes**.
2. **Một sender consumer** cho mỗi kết nối (hoặc scheduler đảm bảo serial gửi), chỉ gửi tiếp khi future trước hoàn tất.
3. **Deadline** cho send future và ACK nghiệp vụ nếu cần.
4. Chính sách khi queue đầy: phản hồi overload cho producer, loại dữ liệu có thể thay thế, drop có thống kê, hoặc close kết nối theo protocol.
5. Dừng sender, fail pending promises, giải phóng buffers khi socket terminal.

Ví dụ kiểm soát số messages:

```java
ArrayBlockingQueue<String> queue =
        new ArrayBlockingQueue<>(64);

if (!queue.offer("event-42")) {
    throw new IllegalStateException(
            "Outbound backlog limit reached");
}
```

Đây chỉ là **đoạn minh họa queue**, chưa phải sender loop; cần import `java.util.concurrent.ArrayBlockingQueue`. Một thread dành cho send có thể `take()` rồi `ws.sendText(item, true).join()` tuần tự (có xử lý lỗi/stop), nhưng **không chặn callback của WebSocket** bằng `join()`.

## 7. Ping/Pong giữa fragments

Theo RFC 6455, Ping (opcode 9), Pong (10) và Close (8) là **control frames**, có thể xen giữa data fragments. Ping/Pong payload tối đa **125 bytes**. JDK WebSocket tự đáp **Pong** khi nhận Ping.

```java
ws.sendPing(ByteBuffer.wrap(new byte[] {1, 2, 3}));
```

Đây là đoạn minh họa, cần biến `WebSocket ws` và import `ByteBuffer`.

- `onPing/onPong` tiêu thụ demand nếu được gọi. Khi override, đừng quên request tiếp.
- Gặp Ping **không** reset message assembler.
- `sendPing` future hoàn tất khi thao tác **gửi** thành công, **không** có nghĩa Pong đã về.
- Ping/Pong giúp giám sát link nhưng **không thay thế application ACK**.
- Khi đo RTT, dùng nonce hoặc correlation thích hợp, timeout và metric phân phối; tránh nhầm các Pong không chủ động.

## 8. Đóng kết nối: gửi Close không đồng nghĩa đóng cả hai chiều

`WebSocket` có input/output độc lập:

```text
OPEN (input + output)
     |
     | sendClose(1000, "")
     v
OUTPUT CLOSED, INPUT MAY STILL BE OPEN
     |
     | nhận Close từ peer
     v
onClose(ws, status, reason)
     |
     v
INPUT CLOSED, connection shutdown completes

Bất kỳ lúc nào cần fail-fast:
     abort() -> đóng ngay input + output
```

`sendClose(code, reason)` bắt đầu gửi Close để đóng **output**. Khi future gửi Close hoàn tất, **không giả định input đã đóng**: Javadoc nêu input còn mở cho tới khi nhận Close từ peer, `abort` hoặc lỗi.

`onClose` xảy ra khi nhận Close; đây là callback **cuối cùng** trên nhánh nhận. WebSocket JDK xử lý reciprocal Close tự động theo protocol. Callback `onClose` trả `CompletionStage<?>` để quyết định khi output còn mở có thể đóng; **đừng trả stage không bao giờ complete** vì sẽ ngăn phản hồi close.

`onError` là terminal error callback; khi nó bắt đầu, input và output đã đóng. Không coi một lỗi network là một graceful close 1000.

### Graceful close có timeout

Giả sử `ws` đã kết nối và listener có future `peerClosed` được complete trong `onClose`:

```java
try {
    ws.sendClose(WebSocket.NORMAL_CLOSURE, "")
      .get(3, TimeUnit.SECONDS);

    peerClosed.get(3, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    ws.abort();
}
```

Đây là đoạn **minh họa**, cần xử lý `InterruptedException`/`ExecutionException`, import `TimeUnit/TimeoutException` và định nghĩa future `peerClosed`. Nếu peer không hợp tác thì deadline phải dẫn đến cleanup, không giữ socket mãi. `abort()` là **abrupt close**, không giống close handshake.

### Các close codes và giới hạn Java 11

| Mã | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| **1000** | Normal closure | `WebSocket.NORMAL_CLOSURE`, dùng phổ biến |
| **1001** | Going away | Có thể dùng tùy ngữ cảnh |
| **1002** | Protocol error | RFC định nghĩa, nhưng Java 11 `sendClose` **không cho gửi** |
| **1005** | Không có status được gửi | Sentinel, **không** gửi trên wire |
| **1006** | Abnormal closure | Sentinel, **không** gửi trên wire |
| **1008** | Policy violation | Java 11 cho gửi; chỉ dùng đúng ngữ nghĩa |
| **1009** | Message too big | RFC định nghĩa, nhưng Java 11 `sendClose` **không cho gửi** |
| **1015** | TLS failure | Sentinel, không gửi |
| **4000–4999** | Private application codes | Có thể dùng theo protocol riêng |

**Điểm rất dễ sai:** Javadoc Java 11 quy định `sendClose` nhận code từ 1000 đến 4999 nhưng **cấm** các mã **1002, 1003, 1006, 1007, 1009, 1010, 1012, 1013 và 1015**. Vì thế không truyền 1009 từ client Java11 dù RFC khuyến nghị 1009 cho quá tải message. Có thể chọn `abort()` hoặc một close code ứng dụng **được API cho phép và có ý nghĩa đúng**; không gán sai status cho lỗi chỉ để tránh exception.

**Close reason** là chuỗi có biểu diễn **UTF-8 tối đa 123 bytes**, không phải 123 ký tự Java. Kiểm tra:

```java
if (reason.getBytes(StandardCharsets.UTF_8).length > 123) {
    throw new IllegalArgumentException("Close reason too long");
}
```

Đây là đoạn minh họa với biến `String reason` và import `StandardCharsets`. Nếu code/reason không hợp lệ, `sendClose` có thể trả future hoàn tất exceptionally với `IllegalArgumentException`.

## 9. Test tích hợp cục bộ: client Java 11, fragmented server

Để kiểm tra **thực tế** mà không phụ thuộc echo WebSocket public, dùng một test có server TCP loopback chỉ phục vụ mục đích thử nghiệm.

Test xác minh:

- Handshake HTTP Upgrade tới WebSocket.
- Client dùng `sendText("CLI", false)` và `sendText("ENT", true)` để phát **một** logical message `CLIENT`.
- Server trả một message text `Xin chào` trong **hai wire fragments**, tách ngay giữa hai bytes của Unicode `à`.
- Server chèn một **Ping** giữa hai fragments.
- Server gửi một binary message qua hai fragments.
- Server gửi Close 1000; client nhận `onClose` và gửi reciprocal Close.
- Listener quản lý receive demand một callback mỗi lượt, không phụ thuộc số lượng `onText`/`onBinary` do JDK phân phối.

**Cảnh báo:** server này chỉ thực hiện một phần nhỏ RFC 6455, giới hạn frame size và không có auth/TLS/extensions/cơ chế chống abuse đầy đủ. Chỉ bind **127.0.0.1** trong bài học, **không** dùng làm server production.

### Tệp hoàn chỉnh: `WebSocketFragmentLab.java`

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

public final class WebSocketFragmentLab {
    static final String GUID =
            "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

    static final class ClientListener
            implements WebSocket.Listener {
        final StringBuilder textParts = new StringBuilder();
        final ByteArrayOutputStream binaryParts =
                new ByteArrayOutputStream();

        final CompletableFuture<String> text =
                new CompletableFuture<>();
        final CompletableFuture<byte[]> binary =
                new CompletableFuture<>();
        final CompletableFuture<Integer> closed =
                new CompletableFuture<>();
        int pingCount;

        @Override
        public void onOpen(WebSocket ws) {
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket ws, CharSequence data, boolean last) {
            String piece = data.toString();
            if (piece.length() > 1024 - textParts.length()) {
                text.completeExceptionally(
                        new IOException("Text limit"));
                ws.abort();
                return CompletableFuture.completedFuture(null);
            }
            textParts.append(piece);
            if (last) {
                text.complete(textParts.toString());
                textParts.setLength(0);
            }
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onBinary(
                WebSocket ws, ByteBuffer data, boolean last) {
            if (data.remaining() > 1024 - binaryParts.size()) {
                binary.completeExceptionally(
                        new IOException("Binary limit"));
                ws.abort();
                return CompletableFuture.completedFuture(null);
            }
            byte[] part = new byte[data.remaining()];
            data.get(part);
            binaryParts.write(part, 0, part.length);
            if (last) {
                binary.complete(binaryParts.toByteArray());
                binaryParts.reset();
            }
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onPing(
                WebSocket ws, ByteBuffer payload) {
            pingCount++;
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onPong(
                WebSocket ws, ByteBuffer payload) {
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket ws, int code, String reason) {
            closed.complete(code);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            text.completeExceptionally(error);
            binary.completeExceptionally(error);
            closed.completeExceptionally(error);
        }
    }

    static final class Frame {
        final int opcode;
        final boolean fin;
        final byte[] data;

        Frame(int opcode, boolean fin, byte[] data) {
            this.opcode = opcode;
            this.fin = fin;
            this.data = data;
        }
    }

    static byte[] readExactly(InputStream in, int n)
            throws IOException {
        byte[] result = in.readNBytes(n);
        if (result.length != n) {
            throw new EOFException("Truncated frame");
        }
        return result;
    }

    static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        int ch;
        while ((ch = in.read()) >= 0) {
            if (ch == '\n') {
                return new String(
                        out.toByteArray(),
                        StandardCharsets.US_ASCII);
            }
            if (ch != '\r') {
                if (out.size() >= 8192) {
                    throw new IOException("Header too long");
                }
                out.write(ch);
            }
        }
        throw new EOFException("Incomplete HTTP header");
    }

    static Frame readClientFrame(InputStream in)
            throws IOException {
        int a = in.read();
        int b = in.read();
        if ((a | b) < 0) {
            throw new EOFException("Frame missing");
        }

        boolean fin = (a & 0x80) != 0;
        int opcode = a & 0x0f;
        boolean masked = (b & 0x80) != 0;
        int length = b & 0x7f;

        if (length == 126) {
            int hi = in.read();
            int lo = in.read();
            if ((hi | lo) < 0) {
                throw new EOFException("Bad extended length");
            }
            length = (hi << 8) | lo;
        } else if (length == 127) {
            throw new IOException(
                    "Lab server supports small frames only");
        }

        if (!masked || length > 1024) {
            throw new IOException(
                    "Client mask or frame size invalid");
        }

        byte[] mask = readExactly(in, 4);
        byte[] payload = readExactly(in, length);
        for (int i = 0; i < payload.length; i++) {
            payload[i] ^= mask[i & 3];
        }
        return new Frame(opcode, fin, payload);
    }

    static void sendFrame(
            OutputStream out, int opcode,
            boolean fin, byte[] payload) throws IOException {
        if (payload.length > 125) {
            throw new IllegalArgumentException(
                    "This lab sends small frames only");
        }
        out.write((fin ? 0x80 : 0) | opcode);
        out.write(payload.length);
        out.write(payload);
    }

    static byte[] concat(byte[] x, byte[] y)
            throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(x);
        out.write(y);
        return out.toByteArray();
    }

    static void serve(ServerSocket listener) {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5000);
            InputStream in = peer.getInputStream();
            OutputStream out = peer.getOutputStream();

            if (!readLine(in).startsWith("GET /echo HTTP/1.1")) {
                throw new IOException("Unexpected request line");
            }

            String key = null;
            for (int i = 0; i < 64; i++) {
                String header = readLine(in);
                if (header.isEmpty()) {
                    break;
                }
                if (header.regionMatches(true, 0,
                        "Sec-WebSocket-Key:", 0, 18)) {
                    key = header.substring(18).trim();
                }
            }
            if (key == null) {
                throw new IOException("Missing WebSocket key");
            }

            byte[] sha1 = MessageDigest.getInstance("SHA-1")
                    .digest((key + GUID)
                            .getBytes(StandardCharsets.US_ASCII));
            String accept = Base64.getEncoder().encodeToString(sha1);

            String headers =
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept
                    + "\r\n\r\n";
            out.write(headers.getBytes(StandardCharsets.US_ASCII));
            out.flush();

            ByteArrayOutputStream message =
                    new ByteArrayOutputStream();
            boolean first = true;
            for (;;) {
                Frame frame = readClientFrame(in);
                if ((first && frame.opcode != 1)
                        || (!first && frame.opcode != 0)) {
                    throw new IOException(
                            "Expected text/continuation frame");
                }
                message.write(frame.data);
                first = false;
                if (frame.fin) {
                    break;
                }
            }
            if (!"CLIENT".equals(new String(
                    message.toByteArray(), StandardCharsets.UTF_8))) {
                throw new IOException("Client payload mismatch");
            }

            byte[] firstPart = concat(
                    "Xin ch".getBytes(StandardCharsets.UTF_8),
                    new byte[] {(byte) 0xC3});
            byte[] finalPart = concat(
                    new byte[] {(byte) 0xA0},
                    "o".getBytes(StandardCharsets.UTF_8));

            sendFrame(out, 1, false, firstPart);
            sendFrame(out, 9, true, new byte[] {7});
            sendFrame(out, 0, true, finalPart);

            sendFrame(out, 2, false,
                    new byte[] {1, 2});
            sendFrame(out, 0, true,
                    new byte[] {3, 4});

            // Close 1000 (0x03E8).
            sendFrame(out, 8, true,
                    new byte[] {3, (byte) 232});
            out.flush();

            boolean gotClose = false;
            for (int i = 0; i < 5; i++) {
                Frame frame = readClientFrame(in);
                if (frame.opcode == 8) {
                    gotClose = true;
                    break;
                }
            }
            if (!gotClose) {
                throw new IOException("Client Close not received");
            }
        } catch (Exception ex) {
            throw new RuntimeException(ex);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(5000);
            ExecutorService pool =
                    Executors.newSingleThreadExecutor();
            try {
                Future<?> task = pool.submit(() -> serve(server));

                ClientListener listener = new ClientListener();
                URI uri = URI.create("ws://127.0.0.1:"
                        + server.getLocalPort() + "/echo");

                WebSocket ws = HttpClient.newHttpClient()
                        .newWebSocketBuilder()
                        .connectTimeout(Duration.ofSeconds(5))
                        .buildAsync(uri, listener)
                        .get(5, TimeUnit.SECONDS);
                try {
                    ws.sendText("CLI", false)
                      .thenCompose(socket ->
                              socket.sendText("ENT", true))
                      .get(5, TimeUnit.SECONDS);

                    String value =
                            listener.text.get(5, TimeUnit.SECONDS);
                    byte[] binary =
                            listener.binary.get(5, TimeUnit.SECONDS);
                    int code =
                            listener.closed.get(5, TimeUnit.SECONDS);
                    task.get(5, TimeUnit.SECONDS);

                    if (!"Xin chào".equals(value)
                            || !Arrays.equals(binary,
                                    new byte[] {1, 2, 3, 4})
                            || code != 1000
                            || listener.pingCount != 1) {
                        throw new AssertionError("Test mismatch");
                    }

                    System.out.println("text: " + value);
                    System.out.println("binary: "
                            + Arrays.toString(binary));
                    System.out.println(
                            "ping callbacks: " + listener.pingCount);
                    System.out.println("close code: " + code);
                    System.out.println(
                            "PASS: fragmentation, demand, close");
                } finally {
                    if (!ws.isInputClosed()
                            || !ws.isOutputClosed()) {
                        ws.abort();
                    }
                }
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
```

### Lệnh chạy

```bash
javac --release 11 -encoding UTF-8 WebSocketFragmentLab.java
java WebSocketFragmentLab
```

Stdout mong đợi trên JDK 11+ có quyền loopback networking:

```text
text: Xin chào
binary: [1, 2, 3, 4]
ping callbacks: 1
close code: 1000
PASS: fragmentation, demand, close
```

**Lý do test có giá trị:**

1. Server bind **127.0.0.1 và ephemeral port**, tránh phụ thuộc Internet/port cố định.
2. Handshake tính `Sec-WebSocket-Accept` theo RFC 6455 và upgrade HTTP 101.
3. Server kiểm tra **client frames được mask** theo RFC, ghép data thành `CLIENT` dù client gửi nhiều parts.
4. Server cố tình chia bytes Unicode `à` và gửi Ping giữa fragments. Listener vẫn ghép text thành `Xin chào`.
5. Binary message chia hai phần và được ghép chính xác.
6. Server gửi Close 1000, xác nhận client trả Close.
7. Mọi callback đã dùng `request(1)` để tránh đứng yên vì hết demand.
8. Test assert **toàn message** chứ không khẳng định số lần `onText` hoặc `onBinary` cố định.

Nếu môi trường sandbox không cho mở loopback socket hoặc không có module `java.net.http`, test có thể không chạy vì cấu hình runtime; không tự diễn giải là API không tồn tại. Server giả lập này **không phải** server WebSocket production; nó cố tình hỗ trợ small frames và một quy trình test duy nhất.

## 10. Negative tests: kiểm thử sai lệch và lỗi

| Kịch bản | Cách gây lỗi | Kết quả mong đợi |
| --- | --- | --- |
| Nhận message nhiều fragments | Server gửi `FIN=false,false,true` | Ứng dụng xử lý đúng **một** logical message |
| Unicode bị cắt giữa frames | UTF-8 split như trong lab | Ghép và decode đúng, không mất ký tự |
| Ping xen giữa data | Ping trước continuation | Không reset assembler; demand vẫn tiến |
| Binary buffer có offset | Dùng `position/limit` khác 0 | Không đọc nhầm bytes bên ngoài |
| Listener override onOpen không request | Bỏ `request(1)` | Không nhận receive callback như kỳ vọng |
| Fragment nhận xong không request | Demand về 0 | Receiver không nhận phần kế |
| `request(0)` | Gọi trực tiếp | `IllegalArgumentException` |
| Async handler xử lý chậm | Delay processor | Không cấp thêm demand khi đang overload |
| Message vô hạn fragments | Peer không bao giờ gửi `last=true` | Giới hạn bytes/thời gian, kết thúc an toàn |
| Outbound queue đầy | Producer > network rate | Thực thi overload policy, không OOM |
| Data sends chồng nhau | Gửi khi data send còn pending | Handle failed future/serialize |
| Chèn binary vào text chưa last | Vi phạm loại message | Send lỗi theo API |
| Ping >125 bytes | Payload quá lớn | `IllegalArgumentException` |
| Reason >123 UTF-8 bytes | Reason Unicode dài | `IllegalArgumentException` |
| Gửi close code 1006 hoặc 1009 | Code không được Java11 phép | `IllegalArgumentException` |
| Server Close 1000 | Peer gửi Close hợp lệ | `onClose(1000,...)`, cleanup |
| Peer đóng TCP không gửi Close | RST/EOF/network break | Error/abnormal close, không giả normal |
| Client sendClose nhưng peer im lặng | Không nhận Close reply | Timeout, `abort()` |
| Listener dùng chung nhiều sockets | Fragments của 2 connections | State phải theo connection |
| Handshake thất bại | Server trả HTTP 403/không upgrade | `buildAsync` hoàn tất exceptionally |
| Connection idle lâu | Proxy idle timeout | Heartbeat/timeout có kiểm soát |

Những test này cần cả **unit tests** cho assembler/budget và **integration tests** với server mock có điều khiển frames, ngoài ra cần thử với TLS/proxy/server production ở môi trường staging.

## 11. Đo hiệu năng và tối ưu

Với ứng dụng chat, push notifications hoặc telemetry, các metrics hữu ích:

- **Connections:** active, openings/s, close handshakes/s, abnormal closes, time to close.
- **Inbound/outbound:** messages/s, bytes/s, message-size p50/p95/p99/max, fragmentation count.
- **Flow control:** outstanding receive demand, số lần thiếu credit, callback processing latency.
- **Queues:** messages/bytes queued, high-water mark, rejected/expired, số send futures pending.
- **Health:** Ping/Pong correlation RTT, idle timeout, reconnect rate và backoff.
- **Runtime:** CPU usage, heap/direct memory, GC pauses, thread count và open file descriptors.
- **Error budget:** handshake failure, protocol rejection, timeout, close code, TLS/network errors.

### Sự khác nhau giữa chậm do GC và chậm do backpressure

Nếu response/stream chậm:

```text
Receive callback không chạy?
    +-- counter = 0? quên request?
    +-- handler async bị treo?
    +-- remote không gửi hoặc mạng có vấn đề?

Memory tăng?
    +-- partial message không có last?
    +-- queue output không có giới hạn?
    +-- giữ lại ByteBuffer/CharSequence sau stage?
    +-- sockets/pending promises không cleanup?

Send future chậm?
    +-- peer chậm đọc, TCP buffers đầy?
    +-- outbound queue quá lớn?
    +-- CPU quota/GC/scheduling?
```

**Đừng chỉ tăng `request(Long.MAX_VALUE)` để “sửa” throughput.** Nó có thể đẩy backlog từ TCP/library sang application heap. Cần giới hạn byte budgets, giảm allocations, gộp các application messages nhỏ khi protocol cho phép, và cân bằng throughput với p99 latency.

### Quy trình benchmark

1. Warm up, dùng workload đại diện: nhiều connections, cả message nhỏ/lớn và binary/text.
2. Kiểm thử slow consumers và producers, áp cả byte cap và queue cap.
3. Tiêm Ping/Close xen giữa frames, TCP reset, handshake failure và timeout.
4. Giữ nguyên JDK/vendor, server, proxy, CPU quota, memory limit giữa các lần.
5. Đo throughput, p95/p99, heap, CPU, GC, FDs và queue high-water marks.
6. Chạy dài để phát hiện partial-message retention và socket leak.
7. Không lấy một vòng echo localhost làm kết luận production throughput.
8. Roll out có canary, metrics và rollback plan khi thay fragment sizing hoặc concurrency.

## 12. Những lỗi thường gặp

| Sai lầm | Tác hại | Cách đúng |
| --- | --- | --- |
| Xem từng onText là một message | JSON/message bị cắt | Ghép đến `last=true` |
| Ghép dữ liệu không có byte cap | Peer gửi lâu gây tăng heap | Giới hạn message/connection |
| Quên request khi override onOpen | Receiver đứng | Cấp demand khởi tạo |
| Quên request sau onPing | Dừng nhận phần message tiếp | Cấp credit sau control frame |
| Hiểu CompletionStage là request | Receiver không hoạt động như dự đoán | Phân biệt lifetime với demand |
| Lưu ByteBuffer sau khi stage completed | Dữ liệu bị reuse/không an toàn | Copy trước khi stage hoàn tất |
| Dùng buffer.array() bất kể position | Sai payload | Copy `remaining()` |
| Gửi text/binary đồng thời | Pending send lỗi | Single writer hoặc future chain |
| Hàng đợi output vô hạn | OOM/p99 tăng | Bounded queue |
| Send future = ACK bên nhận | Mất/nhân đôi nghiệp vụ khi retry | Application ACK + idempotency |
| Dùng 1009 với Java11 sendClose | API từ chối | Tôn trọng danh sách code Java11 |
| Đo reason bằng Java char count | Vượt 123 UTF-8 bytes | Kiểm tra UTF-8 byte count |
| sendClose xong coi socket đã chết | Input còn mở | Đợi onClose + timeout |
| onClose trả stage không hoàn tất | Reciprocal close bị trì hoãn | Hoàn tất stage/timeout |
| abort thay thế graceful close | Mất cơ hội close handshake | Chọn theo tình huống |
| Ping gửi xong cho rằng peer khỏe | Future chỉ hoàn tất send | Quan sát Pong và timeout |
| Một listener nhiều connection dùng state chung | Trộn fragments | State tách theo WebSocket |
| Test chỉ một echo endpoint | Bỏ sót lỗi phân mảnh/overload | Inject protocol fault cases |

## 13. Checklist và câu hỏi tự luyện

**Checklist:**

- [ ] Đúng Java 11 `java.net.http.WebSocket`, không dựa API legacy.
- [ ] Phân biệt frame, message, callback; dùng `last`.
- [ ] Ghép text/binary có cap; Unicode/UTF-8 chính xác.
- [ ] `onOpen` cấp receive demand; mọi receive callback cần chính sách request tiếp.
- [ ] `CompletionStage` chỉ liên quan lifetime data, không cộng credit.
- [ ] Không chặn listener bằng I/O/CPU nặng, dùng bounded worker.
- [ ] Outbound send serial, có queue byte/message budget.
- [ ] Send future không phải application ACK.
- [ ] Ping/Pong và Close có thể xen fragments; heartbeat có timeout.
- [ ] SendClose chỉ đóng output, chờ onClose; abort khi phải fail-fast.
- [ ] Close reason <=123 **UTF-8 bytes**; không gửi các status bị cấm.
- [ ] onClose/onError terminal, cleanup promises và connection state.
- [ ] Test Unicode split, slow peer, overload, close timeout, network reset.
- [ ] Benchmark cả CPU, p99, heap/direct memory, queues, FD count.

**Câu hỏi:**

1. `onText("ab", false)` rồi `onText("cd", true)` là mấy message?
2. `request(1)` cấp quyền một message hay một callback?
3. Khi override `onPing` có cần cấp demand tiếp không?
4. Stage chưa completed nhưng receive credit còn, WebSocket có thể tiếp tục callback không?
5. Java11 có cho `sendClose(1009, "")` không?
6. `sendClose(1000, "")` có đóng ngay input không?
7. Ping future thành công có chứng minh remote đã xử lý Ping không?
8. Có nên giữ ByteBuffer của callback sau khi stage hoàn tất không?
9. Vì sao message-size limit phải tính tới fragment không bao giờ last=true?
10. Vì sao 10.000 sends chained không đồng nghĩa outbound queue đã an toàn?

**Đáp án:** 1) Một. 2) Một callback. 3) Có nếu muốn nhận tiếp. 4) Có, demand và stage độc lập. 5) Không, Java11 cấm mã đó. 6) Không, output đóng trước và input chờ peer Close. 7) Không, chỉ xác nhận thao tác gửi. 8) Không. 9) Vì peer có thể khiến partial state tồn tại vô hạn và gây OOM. 10) Chaining chỉ đảm bảo thứ tự, không giới hạn backlog.

## Tóm tắt

**Fragmentation** cần ghép đến `last=true`, không đồng nhất callback với wire frame. **Backpressure** trong Java 11 dùng `request(n)` theo **số callbacks**, kết hợp CompletionStage để quản lý lifetime của buffer và queue/budget ở tầng ứng dụng. **Graceful close** sử dụng `sendClose` và chờ `onClose`, nhưng phải có deadline và `abort()` khi peer không hợp tác. Các quy tắc này vẫn áp dụng cho WebSocket API hiện đại; kiểm thử trên localhost và staging phải bao phủ Unicode split, control frames, slow consumers, oversize messages và network errors.

## Tài liệu chính thức và còn áp dụng

- [Java SE 11 — WebSocket interface: request, sendText, sendBinary, sendPing, sendClose, abort](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html).
- [Java SE 11 — WebSocket.Listener: onOpen/onText/onBinary/onPing/onClose/onError](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html).
- [Java SE 11 — WebSocket.Builder: buildAsync và connectTimeout](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Builder.html).
- [Java SE 11 — HttpClient API và newWebSocketBuilder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Java SE 26 — WebSocket.Listener hiện hành](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/WebSocket.Listener.html).
- [IETF RFC 6455 — WebSocket Protocol, fragmentation, control, close handshake](https://www.rfc-editor.org/rfc/rfc6455).
