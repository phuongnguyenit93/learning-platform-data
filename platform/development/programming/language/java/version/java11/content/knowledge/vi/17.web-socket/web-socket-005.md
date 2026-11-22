# WebSocket: Phân mảnh, cờ last và lắp ghép nội dung trong Java 11+

> **Phạm vi:** WebSocket client chuẩn `java.net.http.WebSocket` của Java 11. Một thông điệp text/binary có thể được gửi hoặc nhận qua nhiều phần; cờ `last` báo phần hiện tại có kết thúc **thông điệp** hay chưa. Bài học tập trung vào `WebSocket.Listener.onText`, `onBinary`, `WebSocket.sendText`, `sendBinary`, cách ghép thông điệp, kiểm soát kích thước và vòng đời dữ liệu. Các API này được hỗ trợ trên JDK hiện đại; không dùng thư viện WebSocket đã lỗi thời.

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Phân biệt **WebSocket message**, **phần dữ liệu** mà API Java callback chuyển đến và **frame** trong giao thức WebSocket.
2. Hiểu `last=false` nghĩa là **chưa kết thúc message** và `last=true` nghĩa là **đã đến phần cuối của message**.
3. Lắp ghép text bằng `StringBuilder` trong `onText(WebSocket, CharSequence, boolean)` mà không phát sự kiện nghiệp vụ quá sớm.
4. Lắp ghép binary bằng `ByteArrayOutputStream` hoặc stream/file; chỉ đọc từ `ByteBuffer.position()` đến `limit()`.
5. Nắm hợp đồng vòng đời `CharSequence`/`ByteBuffer`, `CompletionStage<?>` và quy tắc `request(n)` để không giữ tham chiếu dữ liệu sắp được client thu hồi.
6. Gửi từng phần bằng `sendText(data, last)`/`sendBinary(data, last)`, nối các lần gửi qua `CompletableFuture` để tránh gửi chồng chéo.
7. Xử lý ping/pong xen giữa các phần, message rỗng, nhiều message liên tiếp, `onClose`/`onError` khi còn dữ liệu dang dở.
8. Đặt giới hạn kích thước, thời gian và số kết nối để tránh tăng heap vì một message quá lớn.
9. Chạy hai chương trình Java 11+ độc lập, không cần mạng ngoài: một chương trình kiểm listener lắp ghép, một chương trình kiểm quy trình gửi. Các chương trình dùng **WebSocket mô phỏng** để kiểm logic Java; chúng **không giả lập đầy đủ handshake và framing trên dây**.

## 2. Phân biệt message, fragment và callback

Một **WebSocket message** là đơn vị nội dung mà ứng dụng muốn gửi/nhận, có loại **text** hoặc **binary**. Trong giao thức WebSocket (RFC 6455), một message có thể được truyền trong một frame dữ liệu hoặc nhiều frame liên tiếp. Khi dùng Java API, ứng dụng làm việc chủ yếu với các lần gọi:

~~~java
CompletionStage<?> onText(
        WebSocket webSocket, CharSequence data, boolean last);

CompletionStage<?> onBinary(
        WebSocket webSocket, ByteBuffer data, boolean last);
~~~

Đây là **chữ ký tóm lược** các callback của `WebSocket.Listener`, không phải tệp Java độc lập.

**`last` phản ánh kết thúc message ở API**, không phải lời hứa rằng mỗi lần `onText`/`onBinary` trùng chính xác với một frame trên mạng. Java HTTP Client có thể chia dữ liệu nhận được cho listener thành nhiều lần gọi; không nên dựa vào số lượng callback, kích thước chunk hoặc ranh giới TCP packet để xác định ranh giới nghiệp vụ.

Ví dụ ứng dụng nhận một message text có nội dung `Hello`:

~~~text
Trường hợp A — một callback:
onText("Hello", true)
                  |
                  +--> message hoàn chỉnh: Hello

Trường hợp B — nhiều callback:
onText("Hel", false)  -- chưa phát message
onText("lo",  true)   -- message hoàn chỉnh: Hello

Trường hợp C — nhiều callback hơn:
onText("H",   false)  -- chưa xong
onText("ell", false)  -- chưa xong
onText("o",   true)   -- message hoàn chỉnh: Hello
~~~

Cả ba cách giao cho listener trên đều biểu diễn **một message text hoàn chỉnh** cùng nội dung. Không được coi mỗi callback là một message riêng.

### Bảng ý nghĩa của last

| Callback / lệnh gửi | `last=false` | `last=true` |
| --- | --- | --- |
| `Listener.onText(ws, data, last)` | Có thêm một phần text cho message hiện tại; tiếp tục tích lũy | Phần text cuối của message; lắp ghép và công bố một lần |
| `Listener.onBinary(ws, data, last)` | Có thêm byte của message binary hiện tại; tiếp tục tích lũy | Phần binary cuối; kết thúc message |
| `WebSocket.sendText(data, last)` | Bắt đầu/tiếp tục gửi text chưa kết thúc | Gửi phần cuối, kết thúc text message |
| `WebSocket.sendBinary(data, last)` | Bắt đầu/tiếp tục gửi binary chưa kết thúc | Gửi phần cuối, kết thúc binary message |

Đừng dịch `last=false` là “frame lỗi” hoặc “message chưa nhận gì”. Nó chỉ báo **chưa kết thúc message**. `last=true` vẫn có thể đi cùng `data` rỗng (message rỗng hoặc phần cuối rỗng), tùy tình huống.

## 3. State machine của một message

Với thông điệp text, có thể hình dung:

~~~text
      chưa có text message đang nhận
                    |
                    v
        +---------------------+
        | StringBuilder rỗng  |
        +---------------------+
                    |
             onText(chunk, ?)
                    |
              append(chunk)
                    |
               last == ?
              /         \
            false        true
             |            |
             v            v
        chờ phần sau   tạo String hoàn chỉnh
             |            |
             |         xử lý/phát message
             |            |
             |         reset StringBuilder
             |            |
             +-----<------+
~~~

Quy tắc lõi:

1. Mỗi khi nhận phần text, **sao chép** nội dung vào bộ tích lũy hiện tại.
2. Nếu `last=false`, **không** parse/dispatch như một message hoàn chỉnh.
3. Nếu `last=true`, tạo kết quả cuối, đưa vào xử lý nghiệp vụ **một lần**, rồi **reset trạng thái** cho message tiếp theo.
4. Nếu xảy ra lỗi hoặc đóng kết nối trước `last=true`, **không tự coi phần dang dở là message hoàn chỉnh**.
5. Trước khi append, kiểm tra giới hạn kích thước và tài nguyên.
6. Bảo đảm một bộ state thuộc về **một WebSocket**, hoặc có cơ chế phân biệt socket rõ ràng nếu một listener được dùng chung.

Với binary, thay `StringBuilder` bằng bộ tích lũy byte hoặc output stream/file. Cờ `last` có cùng ý nghĩa kết thúc một **binary message**.

### Nhiều message liên tiếp

~~~text
onText("A", true)       -> message #1: "A"
onText("B", false)      -> chưa xong message #2
onText("C", true)       -> message #2: "BC"
onText("", true)        -> message #3: "" (message rỗng)
~~~

Không để ký tự của message trước lưu lại trong buffer khi bắt đầu message mới. Lỗi quên reset có thể biến `"A"` và `"BC"` thành nội dung sai `"ABC"` hoặc tạo message trùng.

## 4. Listener.onText: nối đúng, không giữ CharSequence gốc

Callback từ Java 11:

~~~java
@Override
public CompletionStage<?> onText(
        WebSocket webSocket, CharSequence data, boolean last) {
    text.append(data);

    if (last) {
        String wholeMessage = text.toString();
        text.setLength(0);
        handleWholeText(wholeMessage);
    }

    webSocket.request(1);
    return null;
}
~~~

**Đây là đoạn minh họa**, cần có `StringBuilder text`, method `handleWholeText`, imports và lớp implements `WebSocket.Listener`.

Điều quan trọng:

- `data` là **CharSequence**, không được giả định luôn là `String`. `StringBuilder.append(CharSequence)` nhận được nhiều implementation của `CharSequence`.
- Javadoc của `onText` đảm bảo dữ liệu được giao ở dạng **chuỗi UTF-16 hợp lệ**. Không tự thực hiện `new String(data.getBytes(...))` vì `CharSequence` không có phương thức `getBytes` chung và không cần giải mã lại byte đã được HTTP Client chuyển thành text.
- `StringBuilder.append(data)` **sao chép nội dung** vào accumulator. Việc này phù hợp với cảnh báo vòng đời `CharSequence`: sau khi `CompletionStage` do callback trả về hoàn thành, WebSocket được phép **thu hồi/tái sử dụng** đối tượng dữ liệu. Không lưu nguyên tham chiếu `data` vào list và đọc nó mãi về sau.
- `text.toString()` tạo `String` độc lập cho tầng xử lý. Khi callback `last=true`, reset builder **trước hoặc sau khi dispatch** tùy hợp đồng; không để một handler xử lý message sau vô tình append vào builder cũ.
- Nếu handler chạy bất đồng bộ, hãy trao cho nó **bản sao độc lập** `String`, không đưa một `StringBuilder` có thể bị thay đổi trong lúc tác vụ đang chạy.
- Vì `StringBuilder` không thread-safe, trạng thái phải thuộc listener/socket có tính tuần tự theo hợp đồng callback. **Không dùng một StringBuilder dùng chung cho nhiều WebSocket** nếu không khóa/phân vùng.
- `webSocket.request(1)` ở cuối callback cho phép gọi callback nhận tiếp theo. Nếu quên, listener có thể dừng nhận khi demand trở về 0.
- `return null` hợp lệ theo Javadoc listener: WebSocket xử lý như một `CompletionStage` đã hoàn thành bình thường. Chỉ làm vậy khi bạn **đã dùng xong dữ liệu callback** trước khi return; việc xử lý cả message trong background cần thiết kế ownership/queue/buffer riêng.

### Độ dài text cần đo đúng đơn vị

`StringBuilder.length()` đo **đơn vị UTF-16**, không phải số byte UTF-8 và không hẳn số Unicode code point. Với emoji, số code unit có thể lớn hơn số code point. Nếu hợp đồng cho phép tối đa 1 MiB **byte UTF-8**, đếm `StringBuilder.length()` không phải bảo đảm chính xác; cần chọn chiến lược giới hạn theo byte sau encoding hoặc bảo vệ ở tầng nhận byte phù hợp.

## 5. Listener.onBinary: ByteBuffer.position đến limit, không lấy toàn bộ array

Khi nhận binary:

~~~java
@Override
public CompletionStage<?> onBinary(
        WebSocket webSocket, ByteBuffer data, boolean last) {

    byte[] piece = new byte[data.remaining()];
    data.get(piece);            // Chỉ đọc [position, limit).
    pendingBinary.write(piece, 0, piece.length);

    if (last) {
        byte[] complete = pendingBinary.toByteArray();
        pendingBinary.reset();
        handleWholeBinary(complete);
    }

    webSocket.request(1);
    return null;
}
~~~

Đây là **đoạn minh họa**, cần `ByteArrayOutputStream pendingBinary`, `handleWholeBinary` và imports. Phù hợp payload nhỏ và đã có hạn mức.

Với `ByteBuffer`:

- Dữ liệu hợp lệ nằm **từ `position()` (bao gồm) đến `limit()` (không bao gồm)**.
- `remaining() == limit() - position()` là số byte của **phần đang giao**.
- Không dùng `data.capacity()` hay `data.array().length` làm kích thước nội dung. Buffer có thể là **direct/read-only/sliced** hoặc có mảng nền lớn hơn phần dữ liệu; `array()` có thể ném `UnsupportedOperationException`.
- `data.get(piece)` lấy đúng số byte đang còn và **tăng position**. Nếu cần giữ nguyên position của buffer trong thời gian callback, có thể đọc từ `data.asReadOnlyBuffer()`/`duplicate()`, nhưng bản duplicate vẫn chia sẻ vùng dữ liệu và không được giữ sau khi vòng đời callback kết thúc.
- Java WebSocket được phép **thu hồi `ByteBuffer`** khi `CompletionStage` của `onBinary` hoàn tất; nên **sao chép phần cần giữ** trước khi hoàn thành stage.
- `ByteArrayOutputStream` tích lũy byte trong heap; `toByteArray()` tạo **bản sao**. Với binary lớn, dùng stream/file/chunk processor và giới hạn kích thước thay vì tích lũy không giới hạn.

### Ví dụ buffer có offset

~~~java
ByteBuffer part = ByteBuffer.wrap(
        new byte[] {99, 1, 2, 99});
part.position(1);
part.limit(3);
~~~

Ở đây `part.remaining() == 2` và phần dữ liệu phải append là **byte 1 và byte 2**. Hai byte `99` ở đầu/cuối **không** thuộc fragment đang giao. Ví dụ chạy ở mục 8 có test chính xác tình huống này.

## 6. onOpen, request(n) và CompletionStage: hai cơ chế độc lập

`WebSocket.Listener` nhận data theo cơ chế **demand**. Khi một socket mới được xây dựng, bộ đếm demand ban đầu bằng 0; Java HTTP Client chỉ gọi các receive callback khi đã có demand.

~~~java
@Override
public void onOpen(WebSocket webSocket) {
    webSocket.request(1);
}
~~~

Đây là method có thể đặt trong `WebSocket.Listener`. Nếu không override, implementation mặc định `onOpen` cũng gọi `request(1)`. Nếu **đã override**, phải tự bảo đảm request phù hợp.

### request(1) xin một *callback*, không phải một message

`webSocket.request(1)` tăng khả năng nhận **một lần gọi receive callback**, không đảm bảo nhận được **một thông điệp hoàn chỉnh**. Callback được tính bao gồm `onText`, `onBinary`, `onPing`, `onPong` và `onClose`.

Ví dụ:

~~~text
onOpen -> request(1)             demand +1

onText("Hel", false)             dùng 1 callback
    -> request(1)               demand +1

onPing(...)                      dùng 1 callback
    -> request(1)               demand +1

onText("lo", true)               dùng 1 callback
    -> request(1)               demand +1
~~~

Nếu callback `onPing` được bạn override nhưng **quên gọi `request(1)`**, dòng nhận tiếp theo có thể không được gọi khi demand đã về 0. Ping và pong là **control messages**, không phải fragment text/binary; không append nội dung ping/pong vào message accumulator.

### CompletionStage quản lý vòng đời dữ liệu, không thay request

`onText`/`onBinary` có thể trả `CompletionStage<?>`. Khi stage hoàn tất, WebSocket được phép thu hồi đối tượng `CharSequence` hoặc `ByteBuffer` được truyền vào callback. Nếu trả `null`, nó được coi như stage **đã hoàn thành bình thường**.

Điểm rất dễ nhầm: theo Javadoc Java 11, stage completion **không phải bộ đếm demand**. Một stage chưa hoàn thành không tự ngăn WebSocket gọi receive callback khác **nếu bạn đã `request(n)` thêm**. Để giới hạn inflight processing, phải phối hợp demand và ownership của message/buffer đúng cách.

| Cơ chế | Nó điều khiển điều gì? | Không bảo đảm điều gì? |
| --- | --- | --- |
| `request(n)` | Số lần listener có thể nhận callback tiếp theo | Không tương ứng đúng n thông điệp hoàn chỉnh |
| `CompletionStage<?>` trả từ `onText`/`onBinary` | Khi nào client được phép thu hồi dữ liệu tham số | Không tự giảm/tăng demand cho callback tiếp theo |
| `last` | Khi nào message hiện tại hoàn chỉnh | Không thay demand hay báo hết kết nối |
| `sendText`/`sendBinary` Future | Kết quả của **thao tác gửi** | Không nói bên nhận đã xử lý xong nghiệp vụ |

### Ví dụ xử lý message trong background

Nếu muốn đưa whole message vào queue để xử lý khác thread, hãy:

1. Tạo `String`/`byte[]` **sao chép độc lập** trong callback.
2. Chỉ đưa **bản sao** vào queue.
3. Có giới hạn queue, kích thước message và concurrency.
4. Gọi `request(1)` theo chính sách backpressure, không request vô hạn khiến hàng đợi tăng mãi.
5. Nếu cần chờ xử lý xong mới nhận tiếp, hãy điều phối `request(1)` trong completion của tác vụ xử lý; việc kéo dài `CompletionStage` riêng nó không đủ thay thế demand control.

Không giữ `CharSequence`/`ByteBuffer` gốc qua lifetime của stage đã hoàn tất.

## 7. Ping, pong và close xen giữa các fragment

Giao thức WebSocket cho phép **control frames** như ping/pong xuất hiện giữa các frame của một message dữ liệu đang được phân mảnh. Java listener có callback riêng cho chúng:

~~~java
@Override
public CompletionStage<?> onPing(
        WebSocket webSocket, ByteBuffer message) {
    // Không append ping vào pendingText / pendingBinary.
    webSocket.request(1);
    return null;
}

@Override
public CompletionStage<?> onPong(
        WebSocket webSocket, ByteBuffer message) {
    // Cập nhật metric/heartbeat nếu cần.
    webSocket.request(1);
    return null;
}
~~~

Đây là **mã minh họa**. Default implementation của `onPing`/`onPong` đã gọi `request(1)`; nếu override để xử lý metric, nhớ duy trì demand. Java HTTP Client tự gửi pong đáp lại ping theo hợp đồng API; thường không cần gọi `sendPong` thủ công mỗi khi `onPing` nhận dữ liệu.

Ví dụ:

~~~text
onText("Hel", false)
onPing(<control>)
onText("lo", true)  --> TEXT message "Hello"
~~~

Lắp ghép đúng phải giữ `"Hel"` trong `pendingText` khi callback ping xảy ra, rồi nối `"lo"` khi quay lại text callback. **Không reset pendingText chỉ vì có ping**.

### Close và dữ liệu chưa hoàn tất

`onClose(WebSocket, statusCode, reason)` báo đầu **nhận** đã đóng; theo hợp đồng, đây là callback cuối cho socket đó. Nếu ứng dụng vẫn giữ text/binary fragment với `last=false` trước khi close, **không dispatch fragment dang dở thành message thành công**.

Có thể ghi metric/lỗi “incomplete message” và giải phóng accumulator. Nếu muốn đáp lại close một cách trật tự, tuân thủ hợp đồng `sendClose`/`onClose`; khi cần cắt kết nối nhanh vì dữ liệu bất hợp lệ hoặc vượt hạn mức, `abort()` là lựa chọn mạnh hơn nhưng đóng đột ngột và có thể khiến bên kia thấy lỗi kết nối.

`onError(WebSocket, Throwable)` có thể xảy ra khi lỗi I/O hoặc callback thất bại. Hãy dọn trạng thái chưa hoàn chỉnh, báo lỗi cho tầng quản lý, không tự “đóng message” bằng cách đặt last=true giả tạo.

## 8. Chương trình Java 11+ độc lập: thử lắp ghép text và binary

Ví dụ này kiểm **thuật toán nhận fragment** bằng cách gọi các callback listener một cách trực tiếp với một `FakeSocket`. Nó có ưu điểm không cần server, Internet, DNS hoặc handshake, và stdout được kiểm chứng. Nó **không chứng minh** một WebSocket server thực sẽ tạo số lượng callback giống fixture: Java API không hứa một frame tương ứng chính xác một callback.

Tạo tệp **`FragmentAssemblyDemo.java`**:

~~~java
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.io.ByteArrayOutputStream;

public class FragmentAssemblyDemo {

    // Fake chỉ ghi nhận request(n) và trả Future đã hoàn thành.
    // Không thực hiện kết nối mạng hoặc mô phỏng giao thức WebSocket đầy đủ.
    static final class FakeSocket implements WebSocket {
        long demand;

        @Override
        public void request(long n) {
            if (n <= 0) {
                throw new IllegalArgumentException("n");
            }
            demand += n;
        }

        @Override public String getSubprotocol() { return ""; }
        @Override public boolean isInputClosed() { return false; }
        @Override public boolean isOutputClosed() { return false; }
        @Override public void abort() {}

        @Override
        public CompletableFuture<WebSocket> sendText(
                CharSequence data, boolean last) {
            return CompletableFuture.completedFuture(this);
        }

        @Override
        public CompletableFuture<WebSocket> sendBinary(
                ByteBuffer data, boolean last) {
            return CompletableFuture.completedFuture(this);
        }

        @Override
        public CompletableFuture<WebSocket> sendPing(ByteBuffer message) {
            return CompletableFuture.completedFuture(this);
        }

        @Override
        public CompletableFuture<WebSocket> sendPong(ByteBuffer message) {
            return CompletableFuture.completedFuture(this);
        }

        @Override
        public CompletableFuture<WebSocket> sendClose(
                int statusCode, String reason) {
            return CompletableFuture.completedFuture(this);
        }
    }

    static final class Assembler implements WebSocket.Listener {
        static final int MAX_TEXT_UNITS = 256;
        static final int MAX_BINARY_BYTES = 256;

        final StringBuilder pendingText = new StringBuilder();
        final ByteArrayOutputStream pendingBinary =
                new ByteArrayOutputStream();
        final List<String> completed = new ArrayList<>();

        @Override
        public void onOpen(WebSocket ws) {
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket ws, CharSequence chars, boolean last) {

            // Không dùng pendingText.length() + chars.length():
            // phép cộng có thể tràn số ở hệ thống lớn.
            if (chars.length() > MAX_TEXT_UNITS
                    - pendingText.length()) {
                throw new IllegalArgumentException(
                        "text too large");
            }

            // Sao chép CharSequence vào accumulator.
            pendingText.append(chars);

            if (last) {
                completed.add("TEXT:" + pendingText);
                pendingText.setLength(0);
            }

            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onBinary(
                WebSocket ws, ByteBuffer buffer, boolean last) {

            int count = buffer.remaining();

            if (count > MAX_BINARY_BYTES
                    - pendingBinary.size()) {
                throw new IllegalArgumentException(
                        "binary too large");
            }

            // Chỉ giữ bytes giữa position và limit.
            byte[] part = new byte[count];
            buffer.get(part);
            pendingBinary.write(part, 0, part.length);

            if (last) {
                completed.add("BINARY:"
                        + Base64.getEncoder().encodeToString(
                                pendingBinary.toByteArray()));
                pendingBinary.reset();
            }

            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onPing(
                WebSocket ws, ByteBuffer data) {
            // Ping không làm đổi nội dung message text/binary.
            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket ws, int status, String reason) {
            completed.add("CLOSE:incomplete="
                    + (pendingText.length() > 0
                            || pendingBinary.size() > 0));

            // Không phát hành fragment còn dang dở như message thành công.
            pendingText.setLength(0);
            pendingBinary.reset();
            return null;
        }
    }

    public static void main(String[] args) {
        FakeSocket ws = new FakeSocket();
        Assembler listener = new Assembler();

        listener.onOpen(ws);
        listener.onText(ws, "Hel", false);
        System.out.println("completed.afterFirst="
                + listener.completed.size());

        // Control message xen giữa hai fragment text.
        listener.onPing(ws, ByteBuffer.wrap(new byte[] {4}));

        listener.onText(ws, "lo", true);
        listener.onText(ws, "OK", true);

        // Binary fragment: lấy byte 1 và 2,
        // bỏ hai byte 9 nằm ngoài position..limit.
        ByteBuffer first = ByteBuffer.wrap(
                new byte[] {9, 1, 2, 9});
        first.position(1);
        first.limit(3);

        listener.onBinary(ws, first, false);
        listener.onBinary(
                ws, ByteBuffer.wrap(new byte[] {3}), true);

        // Mô phỏng connection đóng giữa một text message.
        listener.onText(ws, "partial", false);
        listener.onClose(ws, 1000, "done");

        for (String event : listener.completed) {
            System.out.println(event);
        }

        System.out.println("requested.invocations=" + ws.demand);
    }
}
~~~

Biên dịch và chạy bằng JDK 11 trở lên:

~~~bash
javac FragmentAssemblyDemo.java
java FragmentAssemblyDemo
~~~

**Stdout đã kiểm chứng bằng thực thi Java:**

~~~text
completed.afterFirst=0
TEXT:Hello
TEXT:OK
BINARY:AQID
CLOSE:incomplete=true
requested.invocations=8
~~~

### Giải thích kết quả

1. Sau `onText("Hel", false)`, danh sách `completed` vẫn rỗng, nên `completed.afterFirst=0`.
2. `onPing(...)` **không** làm reset `pendingText`. Khi `onText("lo", true)` chạy, listener hoàn thành `Hello` và ghi `TEXT:Hello`.
3. `onText("OK", true)` là một message khác; vì builder đã reset, output là `TEXT:OK`, không phải `TEXT:HelloOK`.
4. Fragment binary đầu chứa byte **1, 2** (không gồm 9). Fragment cuối chứa byte **3**. Ba byte `[1, 2, 3]` được mã hóa Base64 thành **`AQID`**. Base64 chỉ dùng để **hiển thị nội dung nhị phân** dễ kiểm tra, không phải một bước bắt buộc của WebSocket.
5. `onText("partial", false)` không được hoàn tất bởi `last=true` trước `onClose`. Chương trình ghi `CLOSE:incomplete=true`, rồi dọn accumulator. Không công bố `partial` thành message thành công.
6. `requested.invocations=8` là **tổng số lần mã giả gọi `request(1)`**, gồm một lần `onOpen`, các callback text, binary và ping. **Nó không phải số message đã được xử lý** và fake không thực thi cơ chế decrement/demand thực của một WebSocket.
7. Ví dụ giới hạn **256 đơn vị UTF-16** cho text và **256 byte** cho binary. Các ngưỡng này chỉ phục vụ kiểm thử, **không phải hạn mức mặc định của Java**. Trong sản phẩm thật cần chọn cap từ yêu cầu nghiệp vụ và ngân sách tài nguyên.
8. Hai lớp `FakeSocket` và `Assembler` chỉ kiểm **quy tắc lắp ghép**. Tình huống close trong lúc đang dang dở là dữ liệu mô phỏng để kiểm cleanup; test WebSocket mạng thực cần server hỗ trợ protocol.

**Mấu chốt:** không dispatch message trước `last=true`, sao chép nội dung từ buffer trước khi hoàn tất stage, không coi ping là fragment dữ liệu.

## 9. Chương trình Java 11+ độc lập: kiểm cách gửi fragment

Phía gửi có hai API quan trọng:

~~~java
CompletableFuture<WebSocket> sendText(
        CharSequence data, boolean last);

CompletableFuture<WebSocket> sendBinary(
        ByteBuffer data, boolean last);
~~~

Đây là **chữ ký tóm lược**. Cờ `last` có ý nghĩa “đây là phần cuối của message”. Các lần gửi trả `CompletableFuture<WebSocket>` để người gọi biết thời điểm **thao tác gửi** hoàn thành; nó không chứng minh server đã xử lý xong dữ liệu nghiệp vụ.

### Trình tự gửi chuẩn

~~~java
socket.sendText("Hel", false)
        .thenCompose(ws -> ws.sendText("lo", true));
~~~

Đây là **đoạn minh họa**, trong đó `socket` đã kết nối. Hai phần hình thành **một** text message `Hello`. `thenCompose` đảm bảo thao tác gửi phần tiếp theo chỉ bắt đầu sau khi Future phần trước hoàn thành bình thường.

Với binary:

~~~java
socket.sendBinary(ByteBuffer.wrap(new byte[] {1, 2}), false)
        .thenCompose(ws -> ws.sendBinary(
                ByteBuffer.wrap(new byte[] {3}), true));
~~~

Nếu hai thao tác được gọi đồng thời mà trước đó đang có send text/binary pending, hoặc một kiểu dữ liệu khác được gửi khi message cũ chưa kết thúc, API có thể hoàn thành Future thất bại với `IllegalStateException`. Không tự gửi chồng chéo và giả định JDK sẽ xếp đúng thứ tự nghiệp vụ thay bạn.

### Demo kiểm trình tự gửi bằng RecordingSocket

Tạo tệp **`FragmentSendingDemo.java`**. Lớp `RecordingSocket` triển khai interface để **ghi lại** các lời gọi gửi, không thiết lập kết nối mạng. Nó minh họa cờ last, cách dùng `thenCompose` và loại trừ việc xen text/binary khi message chưa kết thúc:

~~~java
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class FragmentSendingDemo {

    static final class RecordingSocket implements WebSocket {
        final List<String> calls = new ArrayList<>();
        boolean textOpen;
        boolean binaryOpen;

        @Override
        public CompletableFuture<WebSocket> sendText(
                CharSequence text, boolean last) {

            if (binaryOpen) {
                return CompletableFuture.failedFuture(
                        new IllegalStateException(
                                "unfinished binary"));
            }

            calls.add("sendText=" + text + ":last=" + last);
            textOpen = !last;

            return CompletableFuture.completedFuture(this);
        }

        @Override
        public CompletableFuture<WebSocket> sendBinary(
                ByteBuffer input, boolean last) {

            if (textOpen) {
                return CompletableFuture.failedFuture(
                        new IllegalStateException(
                                "unfinished text"));
            }

            byte[] bytes = new byte[input.remaining()];
            input.get(bytes);

            calls.add("sendBinary="
                    + Base64.getEncoder().encodeToString(bytes)
                    + ":last=" + last);
            binaryOpen = !last;

            return CompletableFuture.completedFuture(this);
        }

        @Override
        public CompletableFuture<WebSocket> sendPing(
                ByteBuffer payload) {
            return CompletableFuture.completedFuture(this);
        }

        @Override
        public CompletableFuture<WebSocket> sendPong(
                ByteBuffer payload) {
            return CompletableFuture.completedFuture(this);
        }

        @Override
        public CompletableFuture<WebSocket> sendClose(
                int code, String reason) {
            return CompletableFuture.completedFuture(this);
        }

        @Override
        public void request(long n) {
            if (n <= 0) {
                throw new IllegalArgumentException();
            }
        }

        @Override public String getSubprotocol() { return ""; }
        @Override public boolean isInputClosed() { return false; }
        @Override public boolean isOutputClosed() { return false; }
        @Override public void abort() {}

    }

    public static void main(String[] args) {
        RecordingSocket ws = new RecordingSocket();

        ws.sendText("Hel", false)
                .thenCompose(it -> it.sendText("lo", true))
                .join();

        ws.sendBinary(
                ByteBuffer.wrap(new byte[] {1, 2}), false)
                .thenCompose(it -> it.sendBinary(
                        ByteBuffer.wrap(new byte[] {3}), true))
                .join();

        ws.calls.forEach(System.out::println);
    }
}
~~~

Chạy:

~~~bash
javac FragmentSendingDemo.java
java FragmentSendingDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
sendText=Hel:last=false
sendText=lo:last=true
sendBinary=AQI=:last=false
sendBinary=Aw==:last=true
~~~

**Giới hạn của fixture:** Đây là mock tự trả Future đã hoàn tất, không gửi WebSocket frame trên dây, không phản ánh timing hoặc lỗi I/O của một server thật. Nó kiểm **cấu trúc các lệnh gửi và cờ last**. Với triển khai thật, dùng `HttpClient.newWebSocketBuilder().buildAsync(...)` kết nối một WebSocket server, sau đó thực hiện cùng chuỗi `thenCompose` trên socket đã kết nối.

## 10. Tạo WebSocket client thật bằng Java 11

Phần trước cố ý dùng fake để kiểm logic fragment không phụ thuộc hạ tầng. Với một WebSocket endpoint thực tế do bạn quản lý, dạng kết nối chuẩn là:

~~~java
HttpClient client = HttpClient.newHttpClient();

WebSocket.Listener listener = new MyFragmentListener();

CompletableFuture<WebSocket> connecting =
        client.newWebSocketBuilder()
                .buildAsync(
                        URI.create("wss://ws.example.com/events"),
                        listener);

CompletableFuture<WebSocket> sent =
        connecting.thenCompose(ws ->
                ws.sendText("Hel", false)
                        .thenCompose(connected ->
                                connected.sendText("lo", true)));
~~~

**Đây là đoạn minh họa**, không phải chương trình độc lập: `MyFragmentListener` là listener do ứng dụng cần triển khai và endpoint `wss://ws.example.com/events` là địa chỉ ví dụ, không cam kết hoạt động. Cần import `HttpClient`, `WebSocket`, `URI`, `CompletableFuture` và có chính sách xử lý lỗi.

- `buildAsync` trả `CompletableFuture<WebSocket>`; khi hoàn thành bình thường, WebSocket đã được tạo/thiết lập, và `onOpen` được gọi theo hợp đồng API.
- `thenCompose` nối các lần gửi theo đúng thứ tự.
- Nếu handshake thất bại, Future kết nối hoàn thành bất thường. Đừng bắt lỗi rồi gửi tiếp trên một socket chưa có.
- Chọn `wss:` (WebSocket qua TLS) cho hệ thống thật có dữ liệu nhạy cảm; `ws:` thích hợp khi chủ đích dùng mạng không TLS như fixture loopback. Không vô hiệu hóa kiểm chứng TLS.
- `WebSocket.Listener` nhận **các callback** riêng và phải gọi `request(n)` để nhận dữ liệu.
- Listener do ứng dụng quản lý, nên thiết kế **một listener với state riêng cho mỗi connection** để tránh lẫn fragment giữa các socket.

### Đóng kết nối đúng lúc

Sau khi hoàn tất gửi message, có thể dùng:

~~~java
CompletableFuture<WebSocket> closed =
        sent.thenCompose(ws ->
                ws.sendClose(WebSocket.NORMAL_CLOSURE, ""));
~~~

Đây là đoạn minh họa. `sendClose` khởi tạo quá trình đóng **đầu gửi**. Nó không đồng nghĩa đầu nhận đã đóng ngay; thông thường cần xử lý `onClose`/`onError` và timeout cho việc đóng. `abort()` đóng đột ngột và phù hợp cleanup khi không thể tiếp tục an toàn, nhưng có thể làm mất dữ liệu còn đang truyền.

## 11. Vòng đời CharSequence và ByteBuffer ở cả hai chiều

Một lỗi khó phát hiện là **giữ hoặc thay đổi buffer khi HTTP Client vẫn còn dùng**.

### 11.1. Chiều nhận

Với `onText`/`onBinary`, Javadoc định nghĩa `CompletionStage<?>` do callback trả về là tín hiệu cho phép WebSocket thu hồi đối tượng dữ liệu. Sau khi stage hoàn thành:

- **Không truy cập `CharSequence` gốc** do callback cung cấp.
- **Không truy cập `ByteBuffer` gốc** do callback cung cấp.
- Nếu xử lý background, tạo **`String`/`byte[]` bản sao trước khi kết thúc stage**, rồi chỉ dùng bản sao ở worker khác.

Ví dụ **sai**:

~~~java
List<ByteBuffer> parts = new ArrayList<>();

@Override
public CompletionStage<?> onBinary(
        WebSocket ws, ByteBuffer data, boolean last) {
    parts.add(data);             // Giữ buffer do client sở hữu.
    ws.request(1);
    return null;                 // Cho phép thu hồi data ngay!
}
~~~

Đoạn sai minh họa lỗi ownership: các byte có thể bị đọc sai hoặc không hợp lệ nếu buffer được tái sử dụng.

**Sửa:** dùng `byte[] copy = new byte[data.remaining()]`; `data.get(copy)`; giữ bản copy có giới hạn, không giữ `data`.

### 11.2. Chiều gửi text

Javadoc `sendText(CharSequence, boolean)` yêu cầu **không thay đổi `CharSequence`** cho tới khi Future gửi hoàn thành.

~~~java
StringBuilder mutable = new StringBuilder("Hel");
CompletableFuture<WebSocket> sent =
        socket.sendText(mutable, false);

// Không gọi mutable.append(...) ngay tại đây khi sent còn pending.
// An toàn hơn là gửi một String immutable:
CompletableFuture<WebSocket> safe =
        sent.thenCompose(ws -> ws.sendText("lo", true));
~~~

**Đoạn minh họa** trong method với socket đã kết nối. Nếu cần tính nội dung từ `StringBuilder`, tạo `String` immutable trước khi gửi giúp hạn chế lỗi thay đổi nội dung đang pending.

### 11.3. Chiều gửi binary

Với `sendBinary(ByteBuffer, boolean)`, nội dung được lấy từ `position` đến `limit`. Theo Javadoc, sau khi Future gửi **hoàn thành bình thường**, buffer đã **không còn remaining byte**; trước khi thao tác kết thúc, người gọi **không được truy cập buffer**.

~~~java
ByteBuffer payload = ByteBuffer.wrap(new byte[] {1, 2, 3});

CompletableFuture<WebSocket> sent =
        socket.sendBinary(payload, true);

// Chỉ kiểm/mở lại buffer sau khi Future đã hoàn thành.
// Không modify payload hoặc đọc nó trong lúc send đang pending.
~~~

**Đoạn minh họa**; không dùng lại buffer cho nhiều lần gửi đồng thời. Để gửi nhiều fragment, tạo buffer riêng từng fragment hoặc chuẩn bị lại buffer theo đúng trạng thái sau Future trước đó.

### Sự khác nhau giữa last và hoàn tất Future

- `last=true`: **phần gửi/nhận này kết thúc message**.
- Future của `sendText`/`sendBinary` hoàn thành: **thao tác gửi phần này đã hoàn thành**.
- `CompletionStage<?>` của callback nhận hoàn thành: **listener đã cho phép thu hồi buffer của callback đó**.
- `request(n)`: **cho phép thêm n lần receive callback**.

Đây là **bốn khái niệm khác nhau**. Không dùng một khái niệm để suy luận máy chủ đã parse, lưu database hoặc xác nhận nghiệp vụ.

## 12. Giới hạn kích thước: không để fragment tích lũy vô hạn

Một WebSocket message có thể rất lớn và đến qua nhiều callback `last=false`. Nếu cứ append đến lúc `last=true` mà không có cap, kẻ gửi có thể làm heap tăng liên tục hoặc giữ kết nối mở lâu.

### 12.1. Hạn mức cho text

Với accumulator dạng `StringBuilder`:

~~~java
static final int MAX_TEXT_UNITS = 64 * 1024;

if (data.length() > MAX_TEXT_UNITS
        - text.length()) {
    throw new IllegalArgumentException(
            "Text message exceeds limit");
}
text.append(data);
~~~

**Đoạn minh họa**: cap là **64 Ki đơn vị UTF-16**, không phải cap byte UTF-8; `text` là `StringBuilder`. So sánh với phần **còn lại** giúp tránh tính `text.length() + data.length()` có thể gây tràn số.

Nếu hợp đồng yêu cầu cap tính theo **số byte mã hóa UTF-8**, phải kiểm thêm giới hạn ở tầng decode/byte hoặc tính kích thước encoding đúng cách; đừng nhầm code unit với byte. Đối với text cực lớn cần parse theo luồng, nên thiết kế parser incremental và giới hạn độ sâu/cấu trúc dữ liệu.

### 12.2. Hạn mức cho binary

~~~java
int bytes = data.remaining();

if (bytes > MAX_BINARY_BYTES - pendingBinary.size()) {
    throw new IllegalArgumentException(
            "Binary message exceeds limit");
}
~~~

**Đoạn minh họa** bên trong `onBinary`. `MAX_BINARY_BYTES` là hạn mức tin cậy do ứng dụng chọn. Nếu cần lưu file lớn, hãy xử lý từng chunk hoặc ghi xuống file **có cap**, chỉ công bố file hoàn chỉnh sau `last=true`; khi kết nối đóng hoặc có lỗi, xóa file tạm.

### 12.3. Quá giới hạn thì làm gì?

Lỗi kích thước thường là **lỗi giao thức ứng dụng hoặc policy**, không nên cố giữ phần đầu của message rồi tiếp tục coi là hợp lệ. Tùy chính sách:

1. Báo lỗi nghiệp vụ phù hợp, đánh dấu message bị từ chối.
2. Dọn accumulator/file tạm.
3. Không cấp thêm demand vô hạn cho message đang vượt hạn mức.
4. Xem xét đóng kết nối có mã thích hợp khi có thể, hoặc `abort()` nếu không còn cách tiếp tục an toàn.
5. Ghi metric và reason đã redaction, tránh log toàn bộ payload hoặc token.
6. Đặt timeout/deadline cho việc chờ `last=true`; byte cap không chặn peer gửi một fragment rất nhỏ rồi im lặng mãi mãi.

**Không dùng `OutOfMemoryError` làm bộ giới hạn kích thước**; hãy chặn trước khi cấp phát.

## 13. Khi nào nên stream thay vì ghép trong heap?

Ghép bằng `StringBuilder`/`ByteArrayOutputStream` phù hợp với message nhỏ. Với message lớn hoặc độ dài không biết trước:

| Nhu cầu | Chiến lược nên chọn |
| --- | --- |
| Text nhỏ, cần parse một lần sau đủ message | `StringBuilder` + cap + `last=true` |
| Binary nhỏ, cần checksum hoặc xử lý nguyên mảng | `ByteArrayOutputStream` + cap |
| Binary lớn cần ghi file | Ghi mỗi chunk vào `OutputStream`/file tạm có cap; publish sau `last=true` |
| Text lớn cần parse dần | Parser incremental có giới hạn; cân nhắc ranh giới encoding và cú pháp |
| Chỉ cần prefix | Thiết kế quy tắc riêng cho prefix; **không** coi prefix là message hoàn chỉnh |
| Nhiều connection đồng thời | State theo connection, cap message và cap concurrency tổng |
| Chờ message có thể treo | Deadline/idle timeout và cleanup khi close/error |

### Tệp tạm phải được xử lý theo kết quả cuối cùng

Nếu nhận binary thành nhiều phần và ghi tệp:

~~~java
// Mẫu thiết kế, không phải chương trình độc lập.
@Override
public CompletionStage<?> onBinary(
        WebSocket ws, ByteBuffer data, boolean last) {

    writeChunkWithLimit(data);  // Ghi đúng [position, limit).
    if (last) {
        finishAndPublishFile(); // Chỉ sau byte cuối.
    }

    ws.request(1);
    return null;
}
~~~

Cần tự triển khai `writeChunkWithLimit`, `finishAndPublishFile`, quản lý `OutputStream`, permission và cleanup ở `onError/onClose`. Không công bố file nếu chỉ nhận 99% rồi gặp lỗi. Những thao tác file có thể block; nếu đưa sang executor, phải tạo bản sao byte an toàn và giữ backpressure.

## 14. Trật tự callback, nhiều kết nối và concurrency

Javadoc Java 11 nói rằng các lần gọi từ một WebSocket vào listener được thực hiện **theo thứ tự an toàn**, và callback sau có thể bắt đầu **chỉ khi callback trước đã kết thúc**. Vì vậy listener thường không phải xử lý reentrancy giữa các callback nhận dữ liệu **của cùng một socket**.

Tuy nhiên:

- Một listener có thể được chia sẻ bởi **nhiều WebSocket**; callback từ các socket khác nhau có thể đồng thời và không có thứ tự chung. Nếu lưu `StringBuilder` chung, dữ liệu các socket có thể bị trộn.
- Nếu callback giao dữ liệu sang một thread khác để parse hoặc ghi tệp, phần việc ở thread khác có thể đang chạy khi callback tiếp theo đến. Hãy thiết kế queue/ownership/concurrency rõ ràng.
- `CompletionStage<?>` không tự ngăn callback sau khi đã gọi `request(n)` thêm, theo ghi chú API.
- `WebSocket.sendText`/`sendBinary` trả Future và có thể thất bại nếu một thao tác gửi đang pending; đừng sử dụng nhiều thread gọi send riêng lẻ mà không có bộ sắp thứ tự.
- Không coi TCP packet boundaries, frame boundaries và callback boundaries là như nhau.
- Với protocol cấp ứng dụng có ID message hoặc request-response correlation, hãy giữ state theo khóa/connection phù hợp, không suy ra ID từ số lần callback.

Đơn giản nhất: **tạo một instance listener cho mỗi kết nối**, mỗi listener có state riêng và báo completion lên service qua queue hoặc callback; service giới hạn tổng số kết nối và message đang xử lý.

## 15. Các tình huống lỗi dễ mắc

| Cách viết hoặc suy luận | Vấn đề | Sửa thế nào |
| --- | --- | --- |
| Mỗi `onText` là một message | Fragment `false` bị phát sớm | Chỉ dispatch khi `last=true` |
| `last=false` là message rỗng/hỏng | Hiểu sai hợp đồng | Giữ state và chờ phần cuối |
| `last=true` là cuối kết nối | Nhầm ranh giới message với connection | Message mới có thể đến tiếp sau đó |
| Quên reset StringBuilder khi nhận `last=true` | Hai message dính vào nhau | Tạo bản hoàn chỉnh rồi reset |
| `onPing` reset accumulator | Phá message text/binary đang nhận | Ping/pong không thuộc payload |
| Gọi `request(1)` một lần và nghĩ đã xin một message | Chỉ đủ một callback | Request tiếp ở mỗi callback cần thiết |
| Giữ nguyên `CharSequence` do `onText` truyền cho worker | Có thể bị client thu hồi sau stage | Copy thành `String` trước |
| Lưu `ByteBuffer` gốc vào list | Dữ liệu/buffer có thể bị client tái sử dụng | Copy byte trong [position,limit) |
| Dùng `data.array()` thay vì `remaining/get` | Sai trên sliced/direct/read-only buffers | Đọc đúng slice dữ liệu |
| Chỉ dựa vào `capacity()` | Lấy thừa byte ngoài fragment | Dùng `remaining()` |
| Không chặn tổng kích thước qua nhiều fragment | Heap tăng đến khi message kết thúc | Cap trước append/write |
| Nhầm UTF-16 code unit với byte UTF-8 | Giới hạn sai đơn vị | Đếm theo đơn vị yêu cầu |
| Gửi `sendText(false)` rồi lập tức `sendBinary` | Message text đang dở | Kết thúc text trước khi đổi loại |
| Gửi các phần đồng thời | Future có thể thất bại/đảo logic | Nối `thenCompose` |
| Mutate `StringBuilder` đang được `sendText` dùng | Dữ liệu gửi có thể thay đổi | Chuyển thành `String` immutable hoặc đợi Future |
| Truy cập `ByteBuffer` khi `sendBinary` pending | Vi phạm hợp đồng vòng đời | Đợi Future hoàn tất |
| Chờ mỗi phần bằng `join` trên event-loop | Chặn thread không cần thiết | Compose bất đồng bộ |
| Xử lý `onClose` như `last=true` | Công bố message chưa đủ | Hủy pending data và cleanup |
| Một listener shared cho nhiều socket không tách state | Trộn dữ liệu các kết nối | State per socket hoặc map đồng bộ |
| Bỏ qua Future lỗi và `onError` | Không biết message bị bỏ dở | Quan sát lỗi, dọn tài nguyên |
| Mock test mà cho là đã kiểm network framing | Bỏ qua rủi ro server/protocol thật | Có thêm integration test với endpoint WebSocket thực |

## 16. Ma trận kiểm thử cần có

Một bộ test thực tế nên bao gồm:

| Test case | Dữ liệu/chỗi callback | Kết quả |
| --- | --- | --- |
| Text một phần | `onText("OK", true)` | Một message `OK` |
| Text nhiều phần | `onText("Hel", false)`, `onText("lo", true)` | Một message `Hello` |
| Text ba phần | false/false/true | Chỉ dispatch ở lần cuối |
| Nhiều message liên tiếp | `("A",true)`, `("B",true)` | Hai message tách biệt |
| Message rỗng | `("",true)` | Một message text rỗng, không bỏ sót |
| Binary hai phần | byte `[1,2]` false, `[3]` true | Byte hoàn chỉnh `[1,2,3]` |
| ByteBuffer offset | Buffer có position/limit khác capacity | Không lấy byte ngoài giới hạn |
| ByteBuffer direct | `ByteBuffer.allocateDirect(...)` | Không phụ thuộc `array()` |
| Ping xen kẽ | text false, ping, text true | Text vẫn ghép đúng |
| Pong xen kẽ | binary false, pong, binary true | Binary vẫn ghép đúng |
| Đóng giữa message | text false rồi onClose | Không dispatch dữ liệu dở |
| Lỗi mạng giữa message | binary false rồi onError | Dọn state, phát lỗi |
| Quá hạn text | Nhiều fragment khiến tổng code units > cap | Từ chối trước append |
| Quá hạn binary | Nhiều fragment khiến tổng bytes > cap | Từ chối trước cấp phát/tích lũy |
| Gửi text nhiều phần | `sendText(false)` rồi `sendText(true)` | Một message hoàn chỉnh |
| Gửi binary nhiều phần | `sendBinary(false)` rồi `sendBinary(true)` | Một message hoàn chỉnh |
| Gửi trộn sai loại | Text đang dở rồi sendBinary | Thất bại theo hợp đồng, không cố gửi |
| Future gửi lỗi | Một thao tác send thất bại | Các bước sau không tự coi là thành công |
| Nhiều socket chung listener | Fragment khác socket xen kẽ | Không lẫn nội dung (tách state) |

**Unit test** có thể gọi trực tiếp listener với fake như demo. **Integration test** nên dùng một WebSocket server thử nghiệm thực, gửi các frame/fragment và control frame hợp lệ rồi kiểm message cuối; không assert cứng rằng mỗi frame luôn tạo một callback riêng. Với server không đáng tin, giới hạn thời gian, kích thước và connection count để test không treo vô hạn.

### Ví dụ assertion không phụ thuộc console

Với các biến `listener` và `ws` trong demo:

~~~java
if (!listener.completed.contains("TEXT:Hello")) {
    throw new AssertionError("Text was not assembled");
}
if (!listener.completed.contains("BINARY:AQID")) {
    throw new AssertionError("Binary was not assembled");
}
~~~

**Đoạn minh họa**, cần chạy sau khi hai message hoàn chỉnh được phát. Trong test suite JUnit, có thể dùng `assertEquals`/`assertArrayEquals`; JUnit là dependency riêng chứ không nằm trong Java SE 11.

## 17. Hợp đồng Java 11 vẫn đúng trên JDK mới

Những API cốt lõi sau đều có trong Java 11 và được tiếp tục duy trì:

- `java.net.http.WebSocket`, `WebSocket.Listener` và `WebSocket.Builder`.
- `HttpClient.newWebSocketBuilder().buildAsync(URI, Listener)`.
- `WebSocket.sendText(CharSequence, boolean)` và `sendBinary(ByteBuffer, boolean)`.
- `WebSocket.Listener.onText(..., boolean last)` và `onBinary(..., boolean last)`.
- `WebSocket.request(long n)`, `sendClose(...)`, `abort()`, `onClose` và `onError`.
- `java.util.concurrent.CompletableFuture`/`CompletionStage`.
- `StringBuilder`, `ByteBuffer`, `ByteArrayOutputStream` và `Base64`.

Không cần dùng `javax.websocket` hoặc thư viện WebSocket cũ chỉ để minh họa các API của Java 11. `javax.websocket`/Jakarta WebSocket là một hệ sinh thái API riêng, phù hợp trong những stack server/framework cụ thể nhưng **khác** với `java.net.http.WebSocket`; không trộn tên kiểu và hợp đồng của chúng trong cùng một đoạn code Java SE.

### Nên nhớ những giới hạn do implementation

- Không có bảo đảm mọi callback ứng với **một frame** hoặc có kích thước fragment cố định.
- Không giả định mọi server hỗ trợ extension/compression/subprotocol giống nhau; negotiated subprotocol được đọc bằng `getSubprotocol()`.
- Không suy luận thời điểm ack nghiệp vụ từ completion của Future gửi.
- Không giả định giới hạn kích thước/hạn mức queue mặc định đủ an toàn cho ứng dụng: đặt cap của chính ứng dụng.
- Không dùng các chi tiết nội bộ của JDK như internal WebSocket implementation để quyết định business logic.

## 18. Tự kiểm tra kiến thức

**Câu 1.** Listener nhận `onText("Hel", false)` rồi `onText("lo", true)`. Có mấy message hoàn chỉnh?

**Một.** `last=false` chỉ là phần đầu; `last=true` đánh dấu hoàn tất message `Hello`.

**Câu 2.** `onText("A", true)` rồi `onText("B", true)` có phải một message `AB` không?

**Không.** Đó là **hai message**. Phải reset state sau `last=true` của message trước.

**Câu 3.** `ByteBuffer.capacity() == 100` nhưng `position=10` và `limit=13`; fragment dài bao nhiêu byte?

**Ba byte** (`remaining()==3`). Không đọc 100 byte từ mảng nền.

**Câu 4.** Có thể giữ `ByteBuffer` của `onBinary` vào list rồi đọc sau khi callback trả `null` không?

**Không nên.** Trả `null` báo dữ liệu có thể được thu hồi ngay. Nếu cần giữ, sao chép byte trước khi trả.

**Câu 5.** `webSocket.request(1)` xin một message hay một callback?

**Một callback**. Nếu message bị chia nhiều phần, cần request thêm; ping/pong cũng tiêu thụ demand.

**Câu 6.** Ping đến giữa message text có được xem như fragment của text không?

**Không.** Ping là control message. Không append payload ping vào `pendingText` và cũng không xóa fragment text đang chờ phần cuối.

**Câu 7.** Tại sao gửi `sendText("Hel", false)` nên nối Future rồi mới gửi `sendText("lo", true)`?

**Vì** nó tránh chồng chéo send operation và bảo đảm thứ tự. `last=true` hoàn tất **cùng một text message**.

**Câu 8.** Nếu binary message dài 100 MiB và ứng dụng không giới hạn, `ByteArrayOutputStream` có an toàn vì mỗi fragment chỉ 8 KiB không?

**Không.** Tổng dữ liệu tích lũy vẫn có thể phình lên rất lớn. Cần cap, streaming/file và giới hạn concurrency.

**Câu 9.** `onClose` xảy ra khi `pendingText` vẫn chứa `"partial"` từ `last=false`. Có được dispatch `"partial"` như message hoàn chỉnh không?

**Không.** Không có `last=true`; phải coi đó là message chưa đầy đủ và dọn state.

**Câu 10.** Cờ `last=true` có nghĩa server đã lưu dữ liệu vào database chưa?

**Không.** Nó chỉ đánh dấu kết thúc **message WebSocket** ở API. Xác nhận nghiệp vụ phải dùng giao thức ứng dụng riêng (ví dụ message xác nhận có ID/ACK).

## 19. Checklist khi review code

- [ ] Listener phân biệt text và binary, không trộn các fragment thuộc message khác loại.
- [ ] Chỉ dispatch message khi callback có `last=true`.
- [ ] Accumulator được reset sau mỗi message hoàn chỉnh.
- [ ] Ping/pong không phá accumulator và callback vẫn cấp demand hợp lý.
- [ ] `request(n)` được hiểu là số callback, không phải số message.
- [ ] `CharSequence`/`ByteBuffer` của callback được sao chép khi cần giữ sau stage.
- [ ] Binary chỉ dùng dữ liệu từ `position()` tới `limit()`.
- [ ] Text/binary có giới hạn theo **đơn vị đo được định nghĩa rõ** và check trước append.
- [ ] Có cleanup khi `onClose`/`onError`, không publish fragment dở.
- [ ] Gửi text/binary theo chuỗi Future, tránh pending sends và đổi loại giữa message chưa xong.
- [ ] Không mutate `CharSequence` hay truy cập `ByteBuffer` gửi trước khi Future hoàn thành.
- [ ] Có timeout, giới hạn memory, concurrency và policy đóng kết nối.
- [ ] Các test bao gồm last=false/true, nhiều message, buffer offset, ping interleave, empty, limit và lỗi.
- [ ] Mã target Java 11 không vô tình dùng API mới chỉ xuất hiện sau Java 11.

## 20. Tài liệu chính thức

- [`WebSocket` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html): `sendText`, `sendBinary`, `request`, `sendClose`, semantics của Future và `last`.
- [`WebSocket.Listener` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): `onText`/`onBinary`, hợp đồng `CompletionStage`, vòng đời buffer, callback ordering và ví dụ lắp ghép message.
- [`WebSocket.Builder` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): tạo WebSocket với `buildAsync`, headers/subprotocol và thời gian chờ kết nối.
- [`HttpClient` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): `newWebSocketBuilder()`, cấu hình HTTP Client.
- [`ByteBuffer` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `remaining`, `get` và thuộc tính của buffer.
- [`CompletionStage` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletionStage.html): cách nối và hoàn tất thao tác bất đồng bộ.
- [`WebSocket.Listener` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): đối chiếu những phương thức cốt lõi vẫn được hỗ trợ trên JDK hiện đại.
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455): khái niệm message, frame, fragmentation, FIN và control frames.

**Ghi nhớ:** `last=false` nghĩa là **còn phần tiếp theo của message**, `last=true` nghĩa là **đã nhận/gửi phần cuối**. Chỉ công bố message sau khi ghép đủ phần; copy dữ liệu trước khi stage cho phép thu hồi; giữ demand thông qua `request(n)`; giới hạn kích thước và dọn state trên close/error. Đây là hợp đồng Java 11 còn nguyên giá trị trên các JDK hiện đại.