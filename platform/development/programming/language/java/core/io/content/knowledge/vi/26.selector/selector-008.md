# Selector: sẵn sàng I/O không bảo đảm hoàn tất toàn bộ thao tác

Trong Java NIO, `Selector` theo dõi nhiều `SelectableChannel` để phát hiện **readiness** — một thao tác đọc, ghi, nhận kết nối hoặc hoàn tất kết nối **có khả năng tiến triển** mà không cần chờ theo cơ chế blocking. Nhưng **ready không đồng nghĩa complete**: tín hiệu `OP_READ` không hứa đọc được toàn bộ thông điệp, `OP_WRITE` không hứa ghi được hết buffer, `OP_ACCEPT` không hứa chấp nhận tất cả kết nối đang chờ, và `OP_CONNECT` không hứa kết nối đã thành công.

Đó là lý do một event loop đúng phải kết hợp **ready ops + kết quả thật của API + trạng thái còn lại của buffer/protocol**, sau đó quay lại Selector khi chưa hoàn tất. Bài này tập trung phân biệt readiness với completion, xử lý partial I/O, zero progress và giới hạn của từng sự kiện trong Java 17+.

## 1. Readiness khác completion ra sao?

Hai khái niệm:

- **Readiness (sẵn sàng):** OS/provider thông báo rằng một loại thao tác trên channel có khả năng thực hiện ở thời điểm khảo sát; `Selector.select()` cung cấp các `SelectionKey` chứa bit readiness.
- **Completion (hoàn tất):** thao tác **ở cấp ứng dụng** thực sự đạt mục tiêu, ví dụ nhận đủ frame dài 100 byte, gửi hết một response 8 KiB, hoàn tất TCP connect, hoặc xử lý hết danh sách kết nối đang chờ.

```text
                 Selector.select()
                        |
                        v
                  OP_READ ready
                        |
                        v
              socket.read(buffer)
                        |
             +----------+-----------+
             |          |           |
           n > 0       n == 0      n == -1
             |          |           |
       Có byte mới   Chưa byte    EOF/half-close
             |        tiến triển    |
             v                      v
       Đủ frame chưa?        Xử lý kết thúc
          /       \
        Có        Chưa
        |          |
   Xử lý frame  Lưu buffer/state
                rồi chờ đọc tiếp
```

Một thông điệp TCP có thể được chia qua nhiều lần `read`, hoặc nhiều thông điệp nằm trong một lần `read`. Đừng đánh đồng **ranh giới I/O call**, **ranh giới gói TCP** và **ranh giới request ứng dụng**.

### Ví dụ ngắn

Giả sử protocol định nghĩa frame dài **8 byte** nhưng lúc `OP_READ` được báo, lần đọc đầu chỉ trả 3 byte. Buffer đã có `position = 3`, còn thiếu 5 byte: request **chưa hoàn tất**. Nếu handler cố giải mã ngay, có thể ném `BufferUnderflowException` hoặc tạo dữ liệu sai. Handler phải giữ 3 byte, đợi lần đọc tiếp và chỉ xử lý khi đủ 8 byte.

Ngược lại, một sự kiện `OP_READ` cũng có thể dẫn đến việc đọc đủ **hai frame** trong một lần; parser phải xử lý cả hai thay vì luôn giả định chỉ có một.

## 2. Tập interest ops và ready ops không phải kết quả I/O

Một `SelectionKey` mang hai tập bitmask:

| API | Trả lời câu hỏi | Không cam kết |
| --- | --- | --- |
| `key.interestOps()` | Ứng dụng đang **muốn theo dõi** loại thao tác nào? | Không khẳng định channel đã sẵn sàng. |
| `key.readyOps()` | Selector vừa phát hiện loại thao tác nào **có khả năng tiến triển**? | Không khẳng định bytes hay bản ghi đã hoàn tất. |
| `key.isReadable()` | Bit `OP_READ` hiện diện trong ready ops? | Không bảo đảm `read` trả đúng số byte cần. |
| `key.isWritable()` | Bit `OP_WRITE` hiện diện trong ready ops? | Không bảo đảm `write` gửi hết buffer. |
| `key.isAcceptable()` | Có readiness cho `accept`? | Không bảo đảm xử lý hết mọi client đang chờ. |
| `key.isConnectable()` | Có readiness để thử hoàn tất connect? | Không bảo đảm connect thành công. |

Cả `interestOps` và `readyOps` mô tả **loại thao tác**, không phải kích thước transfer. Để biết tiến độ, dùng giá trị `n` mà channel trả về và trạng thái `ByteBuffer`.

Trước khi đọc trạng thái key, kiểm tra `key.isValid()`. Key có thể đã bị `cancel()` hoặc channel bị đóng; nhiều thao tác trên key invalid ném `CancelledKeyException`.

## 3. Tác động của read/write lên ByteBuffer

`ByteBuffer` có ba thông số và một giá trị suy ra:

```text
0 <= position <= limit <= capacity
remaining = limit - position
```

- `position()` là offset của phần tử kế tiếp trong buffer.
- `limit()` là biên kết thúc **exclusive** của vùng đang được phép xử lý.
- `capacity()` là sức chứa của buffer.
- `remaining()` là số byte còn lại trong vùng từ `position` đến trước `limit`.

Khi gọi `socket.read(buffer)` trong **pha ghi vào buffer**, nếu `n > 0` thì channel đặt thêm `n` byte và dịch `buffer.position()` đúng `n`.

Sau khi đọc, gọi `buffer.flip()` để chuyển sang **pha tiêu thụ**: `limit = position` cũ và `position = 0`. Bộ giải mã đọc từng byte hoặc các trường dữ liệu trong vùng `[position, limit)`. Sau khi giải mã:

- Dùng `clear()` **chỉ khi đã xử lý hết** nội dung cần giữ, để tiếp tục đọc đợt mới.
- Dùng `compact()` khi vẫn còn dữ liệu chưa đủ frame; lệnh này giữ phần `remaining()`, dồn về đầu, đặt position bằng số byte giữ lại và limit về capacity.
- Dùng `rewind()` khi muốn đọc lại cùng một vùng, không phải để chuẩn bị nhận thêm dữ liệu mới.

Khi gọi `socket.write(outBuffer)` trong **pha đọc từ buffer**, nếu `n > 0` thì channel tiêu thụ `n` byte và tăng `outBuffer.position()` đúng `n`. Nếu `outBuffer.hasRemaining()` còn đúng, response **chưa gửi hết**.

**Không cộng thủ công** `position` thêm `n`: phương thức channel đã cập nhật. Và không dùng `capacity` làm số byte hợp lệ sau `flip()`; điều kiện đúng là `remaining()`.

## 4. OP_READ: đọc một phần là bình thường

Với `SocketChannel` đã `configureBlocking(false)`, gọi `read(ByteBuffer)` trả:

| Giá trị | Nghĩa | Xử lý điển hình |
| --- | --- | --- |
| `n > 0` | Đã đọc thực tế `n` byte. | Tiến parser; nếu chưa đủ frame, giữ phần dở dang và đọc tiếp khi thích hợp. |
| `n == 0` | Không chuyển byte trong lời gọi này. | Không kết luận EOF; thoát vòng đọc và chờ readiness khác. |
| `n == -1` | Đầu vào tới EOF, ví dụ peer đóng nửa ghi. | Xử lý kết thúc giao thức, frame còn dang dở và chính sách half-close/đóng kết nối. |

Khi thấy ready, có thể đọc lặp cho đến khi `read == 0` (đã lấy hết dữ liệu hiện sẵn) **hoặc đạt hạn mức công việc mỗi sự kiện**. Không nên độc chiếm event loop bằng việc xử lý mãi một kết nối đang liên tục bơm dữ liệu.

Mẫu **minh họa** (các hàm và biến state là của ứng dụng, không phải API có sẵn):

```java
// socket: SocketChannel non-blocking; state.input đang ở pha ghi.
int n = socket.read(state.input);
if (n < 0) {
    handleInputEof(state); // Xét frame dở, half-close, output chờ.
} else if (n > 0) {
    state.input.flip();
    decodeCompleteFrames(state.input, state); // Chỉ tiêu thụ frame đủ.
    state.input.compact(); // Giữ byte thiếu để lần đọc sau nối tiếp.
}
// n == 0: Không xử lý dữ liệu mới; đợi OP_READ lần sau.
```

Nếu input buffer đã đầy mà parser vẫn chưa xử lý được, phải đặt hạn mức dung lượng/khung hoặc thiết kế stream payload. **Không** chờ `OP_READ` vô hạn với `buffer.remaining() == 0`; kể cả có readiness, buffer không thể nhận thêm.

Readiness có thể được báo ngay khi có dấu hiệu EOF; không mặc định `key.isReadable()` đồng nghĩa có ít nhất một byte dữ liệu.

## 5. OP_WRITE: writable không có nghĩa đã gửi hết

Trong TCP, một socket có thể được báo writable khi hệ điều hành có khả năng nhận **ít nhất một phần** dữ liệu vào vùng đệm gửi. Nhưng:

- `socket.write(buffer)` có thể trả `n < buffer.remaining()` trước lệnh.
- Nó có thể trả `0`, kể cả sau khi trước đó key báo ready (điều kiện đã thay đổi hoặc tài nguyên hiện không sẵn sàng).
- Khi còn dữ liệu, ứng dụng phải giữ nguyên buffer (cùng `position` đã cập nhật) rồi ghi tiếp trong lượt này hoặc ở readiness sau.
- Số byte được channel chấp nhận **không bằng** số byte bên nhận đã xử lý, và không bảo đảm thông điệp đã tới ứng dụng đối tác.

Mẫu gửi đúng:

```java
// pending: ByteBuffer đã flip, chứa dữ liệu còn chờ gửi.
while (pending.hasRemaining()) {
    int n = socket.write(pending);
    if (n == 0) {
        break; // Không quay vòng bận: chờ OP_WRITE lần sau.
    }
}
if (!pending.hasRemaining()) {
    // Hoàn tất buffer hiện tại; bỏ OP_WRITE nếu queue trống.
}
```

Đây là snippet, cần `socket` là `SocketChannel` non-blocking. Trong chương trình thật, kiểm tra deadline, đóng socket khi `IOException`, xử lý các buffer tiếp theo trong hàng đợi, và áp dụng backpressure.

**Lưu ý quan trọng:** `OP_WRITE` thường xuyên ready khi socket còn khả năng ghi. Nếu bật `OP_WRITE` vĩnh viễn dù **không có dữ liệu pending**, selector có thể đánh thức rất nhiều lần và CPU tăng cao. Bật chỉ khi hàng đợi outbound không rỗng, tắt khi đã gửi hết:

```java
// Snippet: key còn valid.
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// Sau khi hoàn tất toàn bộ outbound queue:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

Thao tác bitmask `|`, `& ~` giữ nguyên những interest khác như `OP_READ`. Gọi `interestOps(OP_WRITE)` một cách mù quáng có thể vô tình tắt đọc.

## 6. Ví dụ Java 17+: Selector ready nhiều lần, dữ liệu chuyển từng phần

Ví dụ này thực sự sử dụng **một `Selector`**, một `Pipe.SinkChannel` và một `Pipe.SourceChannel`. Hai channel được đặt **non-blocking** và lần lượt đăng ký `OP_WRITE`, `OP_READ`. Để minh họa partial I/O **một cách xác định**, mỗi lần ghi được chủ động giới hạn tối đa 2 byte bằng cách tạm thu hẹp `ByteBuffer.limit()`; buffer đọc cũng chỉ có capacity 2.

Việc tạm hạ limit là **kỹ thuật kiểm thử** để làm rõ hành vi, không phải đảm bảo `SocketChannel` luôn ghi đúng 2 byte. Channel thật vẫn có thể chuyển **ít hơn**.

Lưu thành **`ReadinessNotCompletionDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

public class ReadinessNotCompletionDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();
        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);
            sink.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ);
            SelectionKey outputKey =
                    sink.register(selector, SelectionKey.OP_WRITE);

            ByteBuffer pending = ByteBuffer.wrap(
                    "ABCDE".getBytes(StandardCharsets.US_ASCII));
            ByteArrayOutputStream received = new ByteArrayOutputStream();
            int writeCalls = 0;
            int readCalls = 0;

            while (pending.hasRemaining() || received.size() < 5) {
                if (selector.select(3_000) == 0) {
                    throw new IOException("Timeout khi chờ I/O");
                }
                Iterator<SelectionKey> it =
                        selector.selectedKeys().iterator();
                while (it.hasNext()) {
                    SelectionKey key = it.next();
                    it.remove();
                    if (!key.isValid()) {
                        continue;
                    }

                    if (key.isWritable()) {
                        int oldLimit = pending.limit();
                        pending.limit(Math.min(
                                oldLimit, pending.position() + 2));
                        try {
                            int n = sink.write(pending);
                            if (n > 0) {
                                writeCalls++;
                            }
                        } finally {
                            pending.limit(oldLimit);
                        }
                        if (!pending.hasRemaining()) {
                            outputKey.interestOps(0);
                        }
                    }

                    if (key.isReadable()) {
                        ByteBuffer chunk = ByteBuffer.allocate(2);
                        int n = source.read(chunk);
                        if (n == -1) {
                            throw new IOException("EOF sớm");
                        }
                        if (n > 0) {
                            readCalls++;
                            chunk.flip();
                            while (chunk.hasRemaining()) {
                                received.write(chunk.get());
                            }
                        }
                    }
                }
            }

            System.out.println("writeCalls>=3: " + (writeCalls >= 3));
            System.out.println("readCalls>=3: " + (readCalls >= 3));
            System.out.println("payload=" +
                    received.toString(StandardCharsets.US_ASCII));
            System.out.println("pending=" + pending.remaining());
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 ReadinessNotCompletionDemo.java
java ReadinessNotCompletionDemo
```

Output đã được biên dịch và chạy kiểm chứng:

```text
writeCalls>=3: true
readCalls>=3: true
payload=ABCDE
pending=0
```

Giải thích chi tiết:

1. `Pipe.open()` tạo cặp sink/source. Source và sink đều được `configureBlocking(false)` và đăng ký vào cùng selector.
2. `ByteBuffer.wrap("ABCDE"...)` có 5 byte pending. Mỗi lần sink ready, chương trình tạm giới hạn vùng ghi tối đa 2 byte; vì thế **cần ít nhất 3 lần ghi thành công**, dù selector đã báo readiness từ trước.
3. `sink.write(pending)` dịch position theo số byte thật. `finally` trả lại limit cũ. Khi buffer được gửi hết, `outputKey.interestOps(0)` tắt `OP_WRITE` để tránh vòng quay vô ích.
4. Source ready dẫn tới `source.read(chunk)` với buffer chỉ 2 byte, nên muốn nhận đủ 5 byte cần **ít nhất 3 lượt đọc thành công**. Các byte được tích lũy vào `ByteArrayOutputStream`.
5. `selectedKeys().iterator()` được duyệt và mỗi key được `iterator.remove()`; thứ tự key được chọn không xác định, nhưng kết quả cuối cùng vẫn như nhau.
6. Event loop kết thúc dựa trên **hai điều kiện hoàn tất thực**: pending hết byte **và** số byte nhận đạt 5, không phải vì đã gặp một readiness event.
7. Dùng timeout trong ví dụ để báo lỗi nếu không có readiness thay vì đứng chờ vô hạn. Đối với hệ thống thật, timeout phải là chính sách của toàn operation, không chỉ mỗi lần select.

Dòng `writeCalls>=3` và `readCalls>=3` diễn tả **cận dưới**, không cố định số lời gọi native. Đây là lý do output được thiết kế ổn định trên những triển khai channel hợp lệ trong hoàn cảnh kiểm thử; số lần lặp thực tế có thể cao hơn.

## 7. OP_ACCEPT không đảm bảo đã nhận mọi kết nối

Với `ServerSocketChannel` non-blocking, `OP_ACCEPT` báo có khả năng có kết nối chờ. Handler cần gọi `server.accept()` và xử lý kết quả thật:

```java
// Snippet: server là ServerSocketChannel non-blocking
// đã được register OP_ACCEPT, selector đang mở.
for (int i = 0; i < 64; i++) { // Giới hạn để không đói channel khác.
    SocketChannel client = server.accept();
    if (client == null) {
        break; // Không có kết nối nào sẵn để nhận lúc này.
    }
    client.configureBlocking(false);
    client.register(selector, SelectionKey.OP_READ, new ClientState());
}
```

`ClientState` là kiểu do ứng dụng định nghĩa; đây là snippet không biên dịch độc lập. `accept()` có thể trả `null` khi không còn kết nối pending, kể cả đã nhận readiness trước đó.

**Không** dùng `while (server.accept() == null) { }`: đây là busy spin. Không mặc định một `OP_ACCEPT` chỉ ứng với một client; có thể accept nhiều kết nối có sẵn trong một lượt, với hạn mức để event loop còn phục vụ channel khác.

## 8. OP_CONNECT không đồng nghĩa TCP đã kết nối thành công

Với `SocketChannel` non-blocking:

```java
// Snippet: client non-blocking; remoteAddress và selector có sẵn.
boolean connected = client.connect(remoteAddress);
if (connected) {
    client.register(selector, SelectionKey.OP_READ);
} else {
    client.register(selector, SelectionKey.OP_CONNECT);
}
```

Khi `key.isConnectable()`:

```java
// Snippet: key hợp lệ của một SocketChannel.
SocketChannel client = (SocketChannel) key.channel();
try {
    if (client.finishConnect()) {
        key.interestOps(SelectionKey.OP_READ);
    }
} catch (IOException failure) {
    key.cancel();
    client.close();
    // Báo lỗi kết nối, áp dụng retry có kiểm soát nếu cần.
}
```

`OP_CONNECT` nghĩa là có thể **thử hoàn tất** trạng thái kết nối, không có nghĩa handshake đã thành công. `finishConnect()` có thể trả `false` nếu chưa hoàn tất hoặc ném exception khi connect thất bại. Nếu chưa kết nối xong, **không** bắt đầu đọc/ghi application protocol.

Cần phân biệt một TCP connection established với **hoàn tất giao thức ứng dụng** (TLS handshake, xác thực, nhận request...). Selector báo readiness ở tầng channel; những công đoạn cấp trên có state riêng.

## 9. Sự kiện ready là gợi ý tại thời điểm chọn, không là lời hứa lâu dài

Giữa `select()` và thao tác thực tế, tình trạng sẵn sàng có thể thay đổi. Các nguyên nhân phổ biến:

- Một thread khác hoặc một consumer khác đã tiêu thụ dữ liệu trên channel.
- Buffer đích đã đầy hoặc input reader cố đọc 0 byte.
- Buffer nguồn đã hết dữ liệu cần ghi, nên việc báo writable không mang ý nghĩa còn một response chờ gửi.
- Peer đóng kết nối, socket báo lỗi hoặc channel bị hủy/đóng.
- Readiness của cùng key được cập nhật ở vòng selection khác, trong khi ứng dụng vẫn nhìn các bit cũ nếu quản lý selected-key set sai.

Vì vậy các handler phải đọc kết quả `n` thay vì đoán từ `isReadable()`/`isWritable()`. Tín hiệu ready cũng **không bảo đảm lệnh I/O bất kỳ trên channel đó sẽ không bao giờ chặn**: dùng đúng non-blocking mode, đúng loại thao tác, và tránh code blocking khác nằm trong handler.

## 10. Vòng lặp ghi và xử lý zero progress

Trên channel non-blocking, `write` có thể trả 0 khi chưa chuyển byte. Mẫu sai:

```java
while (out.hasRemaining()) {
    socket.write(out); // Có thể luôn trả 0; CPU quay không ngừng.
}
```

Mẫu đúng cho một lần xử lý readiness:

```java
while (out.hasRemaining()) {
    int n = socket.write(out);
    if (n == 0) {
        break; // Chờ lần OP_WRITE phù hợp kế tiếp.
    }
}
if (out.hasRemaining()) {
    key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
} else {
    key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
}
```

Hai đoạn là snippet. Với một queue nhiều buffer, logic chỉ bỏ `OP_WRITE` khi **toàn bộ queue** trống, không chỉ buffer hiện tại. Để tránh starvation, event loop thường có giới hạn byte/time mỗi readiness.

Nếu buffer được tạo ra từ thread khác, giữ queue thread-safe và dùng `selector.wakeup()` để báo thread event loop cập nhật interest/state. Không tự cập nhật cùng một `ByteBuffer` từ hai thread mà không có ownership rõ.

## 11. Khi nào hoàn tất một request?

Một ứng dụng tốt định nghĩa rõ điều kiện kết thúc:

| Tác vụ | Readiness có ý nghĩa gì? | Điều kiện completion của ứng dụng |
| --- | --- | --- |
| Nhận header fixed 4 byte | `OP_READ` có thể cho một phần byte. | Tích lũy đủ 4 byte, giải mã header hợp lệ. |
| Nhận frame length-prefix | `OP_READ` có thể cho một phần hoặc nhiều frame. | Đủ header, payload đủ số byte có giới hạn, kiểm tra hợp lệ. |
| Gửi response 10 KiB | `OP_WRITE` có thể ghi một phần. | Toàn bộ outbound buffers `!hasRemaining()` hoặc queue trống. |
| Mở kết nối TCP | `OP_CONNECT` cho phép thử `finishConnect()`. | `finishConnect() == true`; nếu exception, kết nối thất bại. |
| Chấp nhận client | `OP_ACCEPT` báo có khả năng có pending connection. | Đã nhận và khởi tạo đủ tài nguyên cho từng client được accept. |
| TLS handshake | Readiness cho bước socket cần đọc/ghi. | Máy trạng thái TLS cho biết handshake hoàn tất, không chỉ vì socket writable. |

Với TCP, ngay cả khi socket `write` đã tiêu thụ hết dữ liệu ứng dụng, điều đó **chỉ** có nghĩa byte đã được channel chấp nhận để gửi theo hợp đồng; không bảo đảm peer đã nhận, xử lý hoặc commit chúng. Nếu cần xác nhận nghiệp vụ, thiết kế ACK ở tầng ứng dụng, timeout, request id và xử lý retry/duplicate.

**Không lấy `selectedKeys().isEmpty()` hay `select() > 0` làm điều kiện hoàn tất giao dịch.** Chúng chỉ là trạng thái của cơ chế selection.

## 12. Protocol framing và bộ nhớ khi đọc từng phần

Một giao thức thường cần phân tách message. Ba kiểu hay gặp:

1. **Fixed-size:** mỗi bản ghi N byte; đọc đến khi đủ N rồi xử lý.
2. **Length-prefix:** header cho biết chiều dài payload; kiểm tra độ dài hợp lệ, quota và đủ byte trước khi giải mã.
3. **Delimiter:** đọc cho đến ký tự phân cách, cần giới hạn độ dài để tránh peer không gửi delimiter.

Ví dụ parser cho bản ghi 4-byte `int`:

```java
// Snippet: input đã nhận byte vào pha ghi.
input.flip();
while (input.remaining() >= Integer.BYTES) {
    int value = input.getInt(); // Tương đối: tiêu thụ 4 byte.
    handleValue(value);
}
input.compact(); // Giữ lại 0..3 byte cho lượt read tiếp theo.
```

Cách này tránh `BufferUnderflowException` khi chỉ mới nhận một phần số nguyên. EOF với 1–3 byte dư là dấu hiệu bản ghi bị cắt (trừ khi giao thức có quy định khác).

Nếu một frame có length-prefix do bên ngoài cung cấp, kiểm tra độ dài **trước khi cấp phát** hoặc đọc theo stream với hạn mức. Dữ liệu dài bất thường, decompression bomb, client đọc rất chậm hoặc queue output tăng vô hạn đều có thể gây cạn tài nguyên dù event loop vẫn “non-blocking”.

## 13. Fairness, backpressure và không chặn event loop

Một event-loop thread quản lý nhiều channel. Việc liên tục đọc đến khi hết nguồn dữ liệu trên **một** client bận rộn có thể làm những client khác bị trì hoãn. Hạn mức thường đặt theo:

- Tổng số byte tối đa xử lý trong một readiness.
- Tổng số frame/đơn vị công việc tối đa trong một lượt.
- Deadline hoặc ngân sách thời gian cho handler.
- Dung lượng tối đa của input frame / outbound queue.
- Thời gian rảnh, thời gian hoàn thành frame và tốc độ truyền tối thiểu.

Nếu outbound queue phình to, áp dụng **backpressure**: tạm ngừng đọc/nhận message mới cho connection đó, từ chối/tạm dừng producer, hoặc đóng client theo chính sách. Không tiếp tục cấp phát buffer vô hạn vì Selector vẫn đang cho ready read.

CPU nặng, JDBC đồng bộ, file I/O blocking và xử lý lâu nên chuyển sang worker pool hoặc giải pháp bất đồng bộ phù hợp. Mô hình một thread cho nhiều channel chỉ hữu ích khi handler nhanh, không bị khóa bởi tác vụ khác.

## 14. selectedKeys: xóa đúng để tránh xử lý lặp

Mẫu event loop:

```java
// Snippet: selector và running được khai báo ngoài.
while (running) {
    selector.select();
    Iterator<SelectionKey> it =
            selector.selectedKeys().iterator();

    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove();

        if (!key.isValid()) {
            continue;
        }
        if (key.isAcceptable()) {
            onAccept(key);
        }
        if (key.isValid() && key.isConnectable()) {
            onConnect(key);
        }
        if (key.isValid() && key.isReadable()) {
            onRead(key);
        }
        if (key.isValid() && key.isWritable()) {
            onWrite(key);
        }
    }
}
```

Các handler là hàm do ứng dụng định nghĩa, không phải chương trình độc lập. `iterator.remove()` cần thực hiện sau khi lấy key ra khỏi selected-key set: tập này không tự xóa toàn bộ key chỉ vì đã gọi handler. Nếu không, key cũ có thể tiếp tục xuất hiện, tạo việc xử lý lặp và hiểu nhầm một readiness là nhiều sự kiện khác nhau.

Một key có thể được báo ready nhiều ops cùng lúc. Handler đầu có thể đóng channel hoặc cancel key, nên cần kiểm tra lại `isValid()` giữa các bước có rủi ro thay đổi vòng đời.

`selector.select()` cũng có thể trả 0 do wakeup/interrupt/đóng hoặc những lý do được API cho phép. Không biến `select() == 0` thành “peer disconnect” hoặc vòng lặp spin vô hạn; xử lý pending tasks, shutdown và timeout theo trạng thái ứng dụng.

## 15. Readiness API không phải completion API

Java cung cấp nhiều nhóm abstraction:

| Nhóm | Mô hình | Điều ứng dụng phải làm |
| --- | --- | --- |
| `Selector` + non-blocking `SocketChannel` | **Readiness**: chọn channel có khả năng thao tác. | Gọi `read/write`, kiểm tra `n`, giữ state, lặp khi cần. |
| Blocking `InputStream`/`Socket` | Lệnh có thể đợi dữ liệu. | Vẫn phải lặp nếu cần đủ N byte; read không hứa đầy buffer. |
| `AsynchronousSocketChannel` | Gửi yêu cầu I/O bất đồng bộ, nhận completion bằng `Future`/`CompletionHandler`. | Xử lý số byte thực hoàn tất và tiếp tục nếu muốn đủ frame. |
| `FileChannel` | File channel hỗ trợ positional I/O và buffer. | Không thể register như `SelectableChannel` với selector; vẫn kiểm tra partial transfer. |

Ngay cả với *completion callback* của API bất đồng bộ, một completion riêng lẻ có thể biểu thị **chỉ một phần** của message lớn hơn. Completion của lời gọi I/O và completion của request ứng dụng không nhất thiết trùng nhau.

Không nên chuyển sang `AsynchronousSocketChannel` chỉ vì muốn “mỗi event luôn gửi trọn buffer”; ứng dụng vẫn cần framing, backpressure, timeout, xử lý kết thúc và trạng thái tiến trình.

## 16. Những sai lầm phổ biến

| Nhận định hoặc lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “`OP_READ` ⇒ đọc đủ 1 request.” | TCP là byte stream; dữ liệu có thể phân mảnh hoặc gộp. | Parser theo framing, tích lũy bytes theo `remaining()`. |
| “`OP_WRITE` ⇒ gửi hết response.” | Socket có thể nhận một phần hoặc 0 byte. | Lặp theo `hasRemaining()`, giữ pending buffers. |
| “`OP_CONNECT` ⇒ TCP đã kết nối.” | Cần `finishConnect()`; có thể thất bại. | Kiểm tra return/exception rồi mới xử lý protocol. |
| “`OP_ACCEPT` ⇒ accept luôn được client.” | Non-blocking `accept()` có thể trả null. | Kiểm tra null, quay về selector; cho phép nhận nhiều client. |
| “`write() > 0` ⇒ peer đã xác nhận dữ liệu.” | Channel chỉ cho biết số byte đã tiêu thụ từ buffer gửi. | Định nghĩa ACK cấp ứng dụng nếu cần cam kết nghiệp vụ. |
| “Nếu ready thì read/write không thể trả 0.” | Readiness có thể thay đổi; không phải bảo đảm số byte. | Xử lý n==0 và chờ readiness sau. |
| “Cứ tiếp tục write khi trả 0.” | Vòng spin bận làm CPU tăng. | Break, giữ state, đợi `OP_WRITE`. |
| “`clear()` sau mỗi read.” | Có thể mất byte chưa đủ frame. | Dùng `compact()` để giữ dữ liệu dở dang. |
| “Dùng capacity để biết bao nhiêu byte còn lại.” | Sau flip, `limit` mới là ranh giới hợp lệ. | Sử dụng `remaining()` và `hasRemaining()`. |
| “Luôn bật `OP_WRITE` cho mọi client.” | Socket thường writable ngay cả khi không có dữ liệu. | Tắt khi queue output trống. |
| “Một event loop có thể xử lý task blocking lớn mà không ảnh hưởng client khác.” | Một thread bị giữ thì các channel cùng selector phải đợi. | Đặt budget và tách tác vụ blocking ra worker. |
| “FileChannel đăng ký với Selector được.” | `FileChannel` không triển khai `SelectableChannel`. | Dùng API phù hợp cho file I/O. |

## 17. Bài tập thực hành

**Bài 1 — Tích lũy frame 10 byte.** Sử dụng `ByteBuffer.allocate(16)`, mô phỏng bốn đợt đọc: 3, 1, 4, 2 byte. Sau từng đợt, in `position/limit/remaining`; chỉ giải mã frame khi đủ 10 byte. Giải thích tại sao không thể dựa vào `OP_READ` đầu tiên.

**Bài 2 — Mô phỏng partial write.** Tạo outbound buffer chứa 11 byte. Giới hạn mỗi lần write tối đa 3 byte (dùng kỹ thuật giảm `limit` trong demo). Đếm số lượt cần thiết và kiểm tra nội dung cuối. Với 11 byte cần **ít nhất 4 lượt ghi**; nếu channel còn ghi ít hơn hạn mức thì số lượt thực tế có thể cao hơn.

**Bài 3 — Thay Pipe bằng TCP.** Dùng `ServerSocketChannel` và `SocketChannel` non-blocking cho local loopback. Cài đặt OP_ACCEPT, OP_READ, OP_WRITE và state của connection. Cho client cố tình gửi một frame theo hai lần ghi; server phải trả lời chỉ khi đã thu đủ.

**Bài 4 — Không giữ OP_WRITE vô ích.** Tạo queue hai buffer. Bật `OP_WRITE` khi queue bắt đầu có dữ liệu, giữ nguyên buffer nếu write trả 0, gỡ OP_WRITE chỉ khi cả hai buffer đã hết. Kiểm tra CPU lúc server nhàn rỗi.

**Bài 5 — EOF giữa frame.** Với giao thức header 4 byte + payload, cho bên gửi đóng sau 2 byte header. Xác định lỗi truncate, không nhầm EOF với read == 0. Bổ sung giới hạn chiều dài và timeout để phòng client gửi thiếu.

**Bài 6 — Công bằng giữa các client.** Tạo hai channel, A liên tục gửi dữ liệu còn B thỉnh thoảng gửi frame ngắn. So sánh độ trễ của B khi handler A xử lý mọi byte vô hạn và khi chỉ xử lý tối đa N byte hoặc M frame mỗi vòng selection.

**Bài 7 — Completion vs business ACK.** Viết sequence diagram gồm client `write` hoàn tất, server nhận byte, server commit vào database, server gửi ACK. Chỉ rõ thời điểm nào có thể retry và cần idempotency key để tránh xử lý trùng sau mất ACK.

### Câu hỏi tự kiểm tra

1. Vì sao `isReadable() == true` vẫn có thể đi cùng `read() == 0` hoặc `read() == -1`?
2. Vì sao `isWritable()` không cho biết đã gửi bao nhiêu byte và peer đã nhận chưa?
3. Một frame có 100 byte nhưng lần read trả 60 thì phải làm gì với 40 byte còn thiếu?
4. Tại sao nên `compact()` thay `clear()` khi parser còn byte chưa xử lý?
5. Khi nào nên bật/gỡ bit `OP_WRITE` khỏi `interestOps`?
6. Điều kiện nào mới chứng minh `finishConnect()` hoàn tất?
7. Một event loop có nhiều channel có giải quyết tự động CPU-heavy handler không?
8. Completion callback của API bất đồng bộ có đồng nghĩa một request nghiệp vụ đã hoàn thành không?

## 18. Tham khảo

- [Java SE 21 — Selector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html): cơ chế chọn readiness, tập key và wakeup.
- [Java SE 21 — SelectionKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html): ready/interest ops và trạng thái đăng ký.
- [Java SE 21 — SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking connect/read/write, EOF và kết quả truyền byte.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): position, limit, remaining, flip, compact.
- [Java SE 21 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): completion handler/Future và I/O bất đồng bộ.

**Ghi nhớ:** `Selector` cho biết **có cơ hội thực hiện I/O**, không xác nhận hoàn tất thao tác. Thành công phải được quyết định bằng **giá trị trả về thật, byte còn thiếu, state của protocol và kết quả nghiệp vụ**. Giữ trạng thái qua nhiều lượt selection, tránh busy spin, giới hạn tài nguyên và chỉ gọi một request là hoàn tất khi toàn bộ điều kiện của nó đã thực sự thỏa mãn.
