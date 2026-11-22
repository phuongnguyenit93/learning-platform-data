# `Selector.select(Consumer<SelectionKey>)` — xử lý sự kiện I/O bằng callback (Java 11+)

## 1. Bài toán: biết khi nào channel sẵn sàng đọc/ghi

Trong Java NIO, một `Selector` giám sát nhiều `SelectableChannel`. Thay vì tạo một thread chờ riêng cho từng kết nối, chương trình thường đăng ký các hoạt động muốn theo dõi, chờ hệ điều hành báo **readiness**, rồi xử lý channel phù hợp. Mỗi đăng ký được đại diện bởi một `SelectionKey`.

Từ **Java 11**, `java.nio.channels.Selector` bổ sung overload:

~~~java
int select(java.util.function.Consumer<SelectionKey> action)
        throws IOException;
~~~

Phương thức này cho phép đưa logic xử lý key vào **callback** (`Consumer<SelectionKey>`). Khi một channel sẵn sàng cho ít nhất một hoạt động thuộc `interestOps` của key, selector gọi `action.accept(key)`. Đó là cơ chế **dispatch sự kiện sẵn sàng I/O**; callback vẫn chạy trên **thread đang gọi `select`**, không tự mở thread hay biến `read`/`write` thành tác vụ nền.

Ví dụ ý tưởng:

~~~java
selector.select(key -> {
    if (key.isValid() && key.isReadable()) {
        // Đọc dữ liệu từ channel tương ứng.
    }
});
~~~

Đây là **đoạn minh họa**, chưa phải chương trình độc lập; cần tạo selector, đăng ký channel non-blocking, xử lý IOException và đóng tài nguyên.

Hàm `select(Consumer)` vẫn được hỗ trợ trên các Java hiện hành. Nó là lựa chọn API cùng tồn tại với `select()` và `selectedKeys()` truyền thống; việc dùng callback **không làm thay đổi bản chất non-blocking của channel hay yêu cầu quản lý vòng đời**.

## 2. Những thành phần trong một lần chọn và xử lý

Các lớp/khái niệm chính:

| Thành phần | Vai trò |
| --- | --- |
| `Selector` | Theo dõi các channel đã đăng ký, thực hiện chọn key sẵn sàng |
| `SelectableChannel` | Channel có thể đăng ký với selector, ví dụ `SocketChannel`, `ServerSocketChannel`, `DatagramChannel` hoặc `Pipe.SourceChannel` |
| `SelectionKey` | Liên kết một channel với selector, lưu `interestOps`, `readyOps` và dữ liệu `attachment` tùy chọn |
| `Consumer<SelectionKey>` | Callback được gọi với key được chọn |
| `interestOps` | Những hoạt động chương trình đang quan tâm, như `OP_READ`, `OP_WRITE`, `OP_CONNECT`, `OP_ACCEPT` |
| `readyOps` | Những hoạt động được ghi nhận sẵn sàng trong kết quả lựa chọn hiện tại |
| `wakeup()` | Yêu cầu một phép select đang chặn, hoặc phép select kế tiếp, trả về sớm theo hợp đồng |

Một chu trình thông dụng:

~~~text
Mở Selector và SelectableChannel
              |
              v
Channel.configureBlocking(false)
              |
              v
channel.register(selector, interestOps, attachment)
              |
              v
selector.select(key -> { ... })
              |
              v
Callback nhận SelectionKey có readyOps phù hợp
              |
              v
Kiểm tra key.isValid(), key.isReadable()/isWritable() ...
              |
              v
Đọc/ghi trên channel; quản lý buffer và interestOps
              |
              v
Quay lại select khi còn tiếp tục phục vụ
              |
              v
Đóng channel và selector ở cuối vòng đời
~~~

**Điều kiện đăng ký:** một `SelectableChannel` cần ở **non-blocking mode** để đăng ký với selector. `SocketChannel`, `ServerSocketChannel`, `DatagramChannel`, `Pipe.SourceChannel` là ví dụ; `FileChannel` thông thường **không phải** `SelectableChannel` và không thể đăng ký với selector.

## 3. Hợp đồng chính xác của `select(Consumer)`

API:

~~~java
int count = selector.select(key -> handle(key));
~~~

Những điểm quan trọng:

1. **Blocking:** `select(action)` chờ cho đến khi có ít nhất một channel được chọn, có `wakeup()`, thread bị interrupt hoặc selector bị đóng/điều kiện khác theo hợp đồng. Không có timeout mặc định; với môi trường cần giới hạn thời gian, dùng `select(action, timeout)`.
2. **Lựa chọn theo interest set:** selector kiểm tra readiness của các hoạt động đã đăng ký trong `key.interestOps()`, rồi chuyển key cho callback. Không tự xử lý dữ liệu ứng dụng.
3. **Callback có thể được gọi hơn một lần cho cùng một key trong một lần select:** nếu một channel sẵn sàng cho nhiều hoạt động, implementation được phép chia các hoạt động thành những tập `readyOps` khác nhau và gọi callback nhiều lần cho cùng key. Các tập này không lặp các bit đã được callback nhận trước đó trong cùng lần chọn.
4. **Giá trị trả về là số key phân biệt được xử lý**, có thể bằng 0, **không nhất thiết là số lần callback được gọi**. Không dùng giá trị trả về như byte count hoặc số message.
5. **Readiness là tín hiệu về khả năng I/O, không bảo đảm tiến độ cụ thể:** non-blocking `read` có thể trả 0, đọc ít byte hơn yêu cầu hoặc trả -1 khi peer đóng đầu ghi; non-blocking `write` có thể ghi một phần hoặc 0. Cần xử lý các kết quả thực tế của operation.
6. **Ngoại lệ từ callback được chuyển ra caller.** `Consumer.accept` không khai báo checked `IOException`, nên code callback phải tự bắt và quyết định xử lý, chẳng hạn bọc vào `UncheckedIOException` hoặc lưu lỗi để xử lý ngoài callback.
7. **Callback được gọi khi selector và selected-key set đang được đồng bộ.** Tránh công việc dài/blocking, tránh khóa theo thứ tự có thể gây deadlock; **không gọi lại `select` trên cùng selector bên trong callback**, vì reentrant selection không được đặc tả nhất quán.

Đối với hệ thống có nhiều thread, key có thể đã bị hủy hoặc interest set thay đổi trước khi callback được gọi. Tài liệu API cho phép một số tình huống phụ thuộc implementation, kể cả callback nhận **key không còn valid**. Vì vậy hãy kiểm tra `key.isValid()` trước khi gọi `isReadable()`, `isWritable()` hoặc `readyOps()` nếu ứng dụng có thể hủy key đồng thời.

### Callback được kích hoạt, nhưng có tự chạy song song không?

Không. `Consumer<SelectionKey>` là **hàm được gọi đồng bộ trong selection operation**, không phải một `Executor`. Tính năng này giúp viết event loop gọn hơn, nhưng không tự giải quyết concurrency, backpressure hay phân phối tải CPU. Nếu callback thực hiện xử lý CPU dài hoặc I/O blocking trên tài nguyên khác, cả luồng selector có thể bị chậm.

## 4. Ba overload callback trong Java 11+

| Phương thức | Blocking | Hành vi khi chưa có channel sẵn sàng |
| --- | --- | --- |
| `select(Consumer<SelectionKey> action)` | Có, không đặt timeout | Chờ readiness, `wakeup`, interrupt hoặc điều kiện đánh thức theo API |
| `select(Consumer<SelectionKey> action, long timeout)` | Có giới hạn nếu `timeout > 0` | Chờ xấp xỉ số millisecond đã cung cấp; `timeout == 0` nghĩa là chờ vô hạn |
| `selectNow(Consumer<SelectionKey> action)` | Không | Trả về ngay, số key có thể là 0 |

Ví dụ dùng khi xây event loop:

~~~java
// Chờ tối đa khoảng 2 giây.
int processed = selector.select(this::handleKey, 2_000L);

// Chỉ kiểm tra những channel sẵn sàng ngay lúc này.
int immediate = selector.selectNow(this::handleKey);

// Chờ vô hạn cho đến khi có sự kiện/được đánh thức.
int blocking = selector.select(this::handleKey);
~~~

Ba dòng trên là **mã minh họa** cho một lớp có phương thức `handleKey(SelectionKey)` và đối tượng `selector` hợp lệ. `this::handleKey` là **method reference** tương đương truyền một `Consumer<SelectionKey>` phù hợp.

Giới hạn cần nhớ:

- `timeout > 0` được tính bằng **milli giây**, có thể trả về trước do `wakeup`, interrupt hoặc readiness. Đây **không phải bảo đảm thời gian thực chính xác**.
- `timeout == 0` là **chờ vô hạn**, không phải polling.
- `timeout < 0` ném `IllegalArgumentException`.
- `selectNow(action)` không chặn; lời gọi này cũng làm hết hiệu lực của những `wakeup()` trước đó chưa được tiêu thụ theo hợp đồng.
- Dù chọn overload nào, nếu không có key được xử lý, kết quả có thể là **0**; đừng xem mọi `0` như lỗi.
- `select(action)` nên đặt trong vòng đời có cách dừng rõ ràng nếu dùng cho server, thường thông qua biến trạng thái và `wakeup()`/`close()` phối hợp.

## 5. Ví dụ hoàn chỉnh: nhận dữ liệu từ `Pipe` bằng callback

Ví dụ dùng **một `Pipe` nội bộ** thay vì network socket, nên không cần mở port hay phụ thuộc server bên ngoài. `Pipe.SourceChannel` hỗ trợ `OP_READ`, đủ để minh họa selector xử lý readiness và đọc byte.

Tạo file **SelectorConsumerDemo.java**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;

public class SelectorConsumerDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();
        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ, "demoPipe");

            ByteBuffer payload =
                    ByteBuffer.wrap("PING".getBytes(StandardCharsets.UTF_8));
            while (payload.hasRemaining()) {
                sink.write(payload);
            }

            int selected = selector.select(key -> {
                if (!key.isValid() || !key.isReadable()) return;
                try {
                    ByteBuffer buffer = ByteBuffer.allocate(16);
                    int bytesRead = ((Pipe.SourceChannel) key.channel())
                            .read(buffer);
                    if (bytesRead > 0) {
                        buffer.flip();
                        byte[] data = new byte[buffer.remaining()];
                        buffer.get(data);
                        System.out.println("attachment=" + key.attachment());
                        System.out.println("received=" +
                                new String(data, StandardCharsets.UTF_8));
                    }
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });

            System.out.println("selected=" + selected);
            int afterDrain = selector.selectNow(key -> {
                System.out.println("unexpectedReady=" + key.readyOps());
            });
            System.out.println("afterDrain=" + afterDrain);
        }
    }
}
~~~

Biên dịch với JDK hỗ trợ Java 11:

~~~bash
javac --release 11 SelectorConsumerDemo.java
java SelectorConsumerDemo
~~~

**Stdout của chương trình trên môi trường đã kiểm thử** (JDK 24, default NIO provider):

~~~text
attachment=demoPipe
received=PING
selected=1
afterDrain=0
~~~

Để phần ví dụ chạy ổn định: chỉ đăng ký **một** `SourceChannel` cho `OP_READ`, viết một payload nhỏ `PING` vào `SinkChannel` **trước khi** gọi `select`, rồi đọc hết payload bằng callback. `selectNow` sau đó kiểm tra lần hai và không tìm thấy thêm dữ liệu đang chờ.

**Diễn giải từng bước:**

1. `Pipe.open()` tạo hai đầu: `sink` để ghi và `source` để đọc.
2. `source.configureBlocking(false)` chuyển source sang non-blocking trước khi `register`; nếu giữ blocking mode, `register` không hợp lệ.
3. `source.register(selector, OP_READ, "demoPipe")` đăng ký theo dõi đọc, kèm `attachment` để callback biết ngữ cảnh.
4. Vòng `while (payload.hasRemaining())` ghi đủ bốn byte; không giả định một lời gọi `write` luôn ghi hết mọi byte cho mọi channel.
5. `selector.select(key -> {...})` chờ readiness rồi gọi lambda. Callback kiểm tra tính hợp lệ và `isReadable()`, đọc bytes từ channel bằng `ByteBuffer` và giải mã UTF-8.
6. `bytesRead > 0` đảm bảo không xử lý buffer như một message mới khi non-blocking read trả 0 hoặc EOF -1.
7. Kết quả `selected=1` là số **key phân biệt được xử lý** trong lần chọn này, không phải số byte. `afterDrain=0` cho thấy lần chọn không chặn ngay sau khi đọc hết payload không có key sẵn sàng nữa trong môi trường thử nghiệm.
8. `try-with-resources` đóng `source`, `sink` và `selector` ở cuối; callback không đóng selector trong khi đang chạy.

Ví dụ có một payload ngắn để minh họa cơ chế. **Trong ứng dụng mạng thực tế**, một lần `read` không bảo đảm nhận trọn một message: cần vòng đọc, bộ đệm tích lũy, giải mã đúng encoding và giao thức phân khung thông điệp. Không coi một lần callback là một message ứng dụng.

## 6. So với `select()` và `selectedKeys()`

Trước khi có overload callback, cách viết thông dụng là gọi `select()`, duyệt các key từ `selectedKeys()` và **xóa từng key đã xử lý khỏi tập** để tránh lưu lại trong selected-key set:

~~~java
int selected = selector.select();
if (selected > 0) {
    java.util.Iterator<SelectionKey> iter =
            selector.selectedKeys().iterator();
    while (iter.hasNext()) {
        SelectionKey key = iter.next();
        iter.remove(); // Loại khỏi selected-key set sau khi lấy key.
        if (key.isValid() && key.isReadable()) {
            // Xử lý channel của key.
        }
    }
}
~~~

Đây là **đoạn minh họa**, có thể đặt trong code đã tạo selector và đăng ký channel; phần I/O cụ thể cần bổ sung.

Với callback Java 11+:

~~~java
int selected = selector.select(key -> {
    if (key.isValid() && key.isReadable()) {
        // Xử lý trực tiếp key vừa được chọn.
    }
});
~~~

**Điểm khác biệt chính:** Theo hợp đồng `Selector`, các phương thức `select(action)`, `select(action, timeout)` và `selectNow(action)` **thực hiện action mà không thêm các key được chọn vào selected-key set**. Chương trình thường không phải tự duyệt rồi `iterator.remove()` cho những key do phép chọn callback cung cấp.

**Lưu ý implementation:** Java cho phép implementation mặc định của một số overload callback **dùng selected-key set như bước trung gian** và tài liệu nêu rằng tập này **có thể còn hoặc không còn phần tử lúc lời gọi kết thúc**. Hơn nữa, nếu chương trình đã dùng các phương thức `select()` truyền thống trước đó thì tập selected key có thể sẵn nội dung. Vì vậy:

- **Không dựa vào `selector.selectedKeys().isEmpty()` để suy ra callback đã hoặc chưa được gọi**.
- Không coi selected-key set là nhật ký toàn bộ callback.
- Khi dùng cả hai kiểu API trong cùng selector, cần hiểu và quản lý trạng thái selected-key set theo hợp đồng cụ thể.
- Các phương thức `select()` truyền thống vẫn được hỗ trợ và có giá trị khi ứng dụng muốn chủ động quản lý selected-key set. Đừng coi chúng là API đã bị loại bỏ.

## 7. `SelectionKey`: kiểm tra và xử lý đúng hoạt động

Tùy loại channel, key có thể quan tâm:

| Bit hoạt động | Ý nghĩa | Channel ví dụ |
| --- | --- | --- |
| `SelectionKey.OP_ACCEPT` | Server socket có kết nối đến có thể accept | `ServerSocketChannel` |
| `SelectionKey.OP_CONNECT` | Kết nối non-blocking có thể hoàn tất | `SocketChannel` |
| `SelectionKey.OP_READ` | Channel có thể đọc | `SocketChannel`, `Pipe.SourceChannel`, `DatagramChannel` |
| `SelectionKey.OP_WRITE` | Channel có thể ghi | `SocketChannel`, `Pipe.SinkChannel`, `DatagramChannel` |

**Không phải channel nào cũng hỗ trợ mọi bit.** Phải kiểm tra bằng `channel.validOps()` hoặc dùng đúng loại channel. Khi đăng ký operation không hỗ trợ, `register` có thể ném `IllegalArgumentException`. Khi channel còn ở blocking mode, đăng ký với selector ném `IllegalBlockingModeException`.

Trong callback:

~~~java
selector.select(key -> {
    if (!key.isValid()) return;
    if (key.isAcceptable()) {
        // Accept kết nối trên ServerSocketChannel.
    }
    if (key.isConnectable()) {
        // Hoàn tất kết nối trên SocketChannel khi cần.
    }
    if (key.isReadable()) {
        // Đọc từng phần và quản lý EOF.
    }
    if (key.isWritable()) {
        // Ghi từng phần, giữ lại buffer chưa viết hết.
    }
});
~~~

Đây là **mẫu dispatch**, không phải code runnable độc lập. Các thao tác thực tế phải dựa trên loại channel, có xử lý checked `IOException` và kiểm tra vòng đời của key.

`key.interestOps()` là những điều ta muốn giám sát; `key.readyOps()` và các hàm `isReadable()`, `isWritable()` biểu thị những hoạt động readiness đã được chọn. **Readiness không giống khả năng hoàn thành hết công việc.** Khi callback đọc mà không còn dữ liệu, hoặc ghi mà buffer chưa hết, cần quản lý trạng thái và chờ sự kiện tiếp theo.

### Attachment giúp callback phân biệt kết nối

`SelectionKey` có `attach(Object)` / `attachment()`. Ví dụ có thể gắn một object giữ `ByteBuffer`, ID phiên, trạng thái protocol hoặc ngữ cảnh của connection:

~~~java
SelectionKey key = channel.register(
        selector, SelectionKey.OP_READ, connectionState);

// Trong Consumer:
Object state = key.attachment();
~~~

Đoạn này là **mã minh họa**: `channel` và `connectionState` cần được tạo hợp lệ. Nếu làm server có nhiều kết nối, attachment giúp callback truy cập trạng thái mà không cần map riêng chỉ để tra cứu từng key. Nhưng object gắn vào vẫn cần được quản lý an toàn khi nhiều thread cùng truy cập.

## 8. Quản lý interest set để tránh vòng lặp bận

Với `SocketChannel`, `OP_WRITE` thường được báo ready khi buffer hệ điều hành còn chỗ, kể cả ứng dụng **không có dữ liệu muốn gửi**. Đăng ký `OP_WRITE` mọi lúc dễ khiến event loop quay liên tục và tiêu tốn CPU.

Một chính sách thường dùng:

1. Chỉ quan tâm `OP_WRITE` khi thực sự còn dữ liệu chờ ghi trong buffer/hàng đợi.
2. Khi callback `isWritable()`, ghi được bao nhiêu thì ghi, giữ nguyên phần còn lại nếu chưa xong.
3. Khi buffer đã cạn, bỏ bit `OP_WRITE` khỏi `interestOps`.
4. Khi có dữ liệu mới từ thread khác, cập nhật interest set theo thiết kế đồng bộ hóa rồi gọi `selector.wakeup()` khi cần để vòng chọn nhận thay đổi.

Ví dụ thay đổi interest set:

~~~java
if (key.isValid()) {
    key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
}
// Khi đã gửi xong:
if (key.isValid()) {
    key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
}
~~~

Đây là **đoạn minh họa**, chỉ hợp lệ khi channel hỗ trợ `OP_WRITE`; tránh chạy nó cho `Pipe.SourceChannel` ví dụ ở phần 5. `interestOps` được thay đổi trong một lần selection có thể chỉ được phản ánh ở **lần selection tiếp theo**, vì hệ điều hành được hỏi readiness theo interest set ở thời điểm thao tác bắt đầu.

Đừng thiết kế vòng:

~~~java
while (running) {
    selector.selectNow(key -> process(key));
}
~~~

mà không có cơ chế chờ/giới hạn vòng quay; gọi `selectNow` liên tục có thể tiêu tốn CPU khi không có sự kiện. Trong event loop dài hạn, thường kết hợp `select(action)` hoặc `select(action, timeout)` với trạng thái dừng và `wakeup`.

## 9. Lỗi và tình huống đặc biệt cần xử lý

### 9.1 Callback ném ngoại lệ

`Consumer.accept` không khai báo `throws IOException`. Nếu đọc channel trong callback, phải tự lựa chọn cách xử lý:

~~~java
selector.select(key -> {
    try {
        handleIO(key); // Giả sử handleIO throws IOException.
    } catch (IOException e) {
        throw new java.io.UncheckedIOException(e);
    }
});
~~~

Đây là **mã minh họa**, `handleIO` cần do ứng dụng cung cấp. Nếu callback ném exception, phép chọn chuyển exception đến caller. Đừng âm thầm bỏ lỗi I/O, bởi việc đó có thể để lại một kết nối lỗi đang liên tục báo ready.

Khi cần ứng dụng tiếp tục phục vụ các kết nối khác, thiết kế chiến lược riêng: ghi log đủ ngữ cảnh, hủy key/đóng channel bị lỗi ở thời điểm thích hợp và quản lý lỗi theo connection. **Không assume** một callback ném ngoại lệ sẽ tự dọn tất cả channel.

### 9.2 Key không valid hoặc bị cancel

`key.cancel()` hủy đăng ký; `channel.close()` cũng làm đăng ký liên quan bị hủy. Key đã cancel có thể chưa được loại khỏi mọi tập cho đến lần selection tiếp theo. Callback cần kiểm tra `isValid()` nếu có khả năng bị hủy đồng thời.

~~~java
if (!key.isValid()) return;
// Sau đó mới dùng isReadable()/readyOps(), có kiểm soát race nếu đa luồng.
~~~

Chỉ kiểm tra một lần **không xóa hoàn toàn race** khi thread khác có thể đóng channel ngay sau đó. Bảo vệ trạng thái kết nối và xử lý ngoại lệ tại điểm I/O.

### 9.3 `wakeup()`, interrupt và close

- `selector.wakeup()` cho phép làm một lời gọi `select` đang đợi trả về sớm. Lời gọi `select` có thể trả về **0** mà không hề gọi callback; đây không nhất thiết là lỗi.
- Thread đang chờ bị `interrupt()` cũng có thể khiến selector được đánh thức; cần quản lý trạng thái interrupt phù hợp.
- `selector.close()` kết thúc vòng đời selector, làm các key liên quan mất hiệu lực/hủy đăng ký, **không tự đóng mọi channel đã đăng ký**. Chủ sở hữu channel vẫn phải quản lý việc đóng riêng.
- Nếu callback tự đóng selector, sau khi action hoàn tất `select(Consumer)` có thể ném `ClosedSelectorException` theo tài liệu. Thiết kế nên để vòng điều phối bên ngoài quyết định khi nào đóng.
- Không gọi `select` lồng nhau trên cùng selector ngay trong callback; tài liệu quy định hành vi reentrant selection là **implementation-specific**, không cung cấp hợp đồng portable.

### 9.4 Đồng bộ hóa và nghẽn callback

`select(action)` thực hiện callback khi đang đồng bộ trên selector và selected-key set. Công việc chờ khóa hoặc I/O blocking lâu trong callback có thể khóa hoạt động của selector, trì hoãn các kết nối khác. Nếu muốn chuyển công việc nặng sang executor, nên sao chép/đóng gói ngữ cảnh cần thiết và quản lý đăng ký/interestOps theo thiết kế thread-safe; không giữ `SelectionKey` rồi sử dụng trạng thái readiness cũ vô thời hạn như một sự kiện bất biến.

Với `readyOps`, các giá trị có thể bị cập nhật ở lần chọn kế tiếp. Không dùng dữ liệu này như bằng chứng rằng một channel **vẫn** ready vào lúc thread xử lý khác thực thi.

## 10. Khi nào nên dùng callback và khi nào nên dùng kiểu duyệt set?

**`select(Consumer)` phù hợp khi:**

- Logic event loop đã được tổ chức thành handler nhận `SelectionKey`.
- Muốn xử lý trực tiếp key sẵn sàng và tránh quản lý thủ công iterator của `selectedKeys()` cho sự kiện trong lần chọn callback.
- Cần gắn trạng thái với key bằng attachment và dispatch `OP_ACCEPT`/`OP_READ`/`OP_WRITE` rõ ràng.
- Đang dùng Java 11+ và muốn viết code tập trung vào hành vi xử lý readiness.

**`select()` + `selectedKeys()` phù hợp khi:**

- Thiết kế hiện tại cần thu thập key theo tập và xử lý theo một pha điều phối riêng.
- Framework hoặc code hiện có đã quản lý selected-key set đúng hợp đồng.
- Cần kiểm soát thời điểm duyệt và loại key theo chiến lược của ứng dụng.

Cả hai nhóm API **đều hiện hành và được hỗ trợ**. Chọn theo kiến trúc và rõ ràng về trạng thái; không chuyển đổi máy móc giữa hai kiểu mà bỏ qua quy tắc selected-key set và lỗi I/O.

## 11. Checklist kỹ thuật và lỗi phổ biến

| Lỗi/ngộ nhận | Hệ quả | Cách sửa |
| --- | --- | --- |
| Đăng ký channel khi còn blocking | `IllegalBlockingModeException` | Gọi `configureBlocking(false)` trước `register` |
| Dùng `FileChannel` với selector | Không phải `SelectableChannel` | Dùng loại channel hỗ trợ selection hoặc API file I/O phù hợp |
| Cho rằng `select(Consumer)` chạy callback ở thread nền | Xử lý nặng gây chặn selector | Giữ handler ngắn, điều phối công việc nặng riêng |
| Gọi `selector.select(...)` trong chính callback | Hành vi reentrant không được bảo đảm | Hoàn tất callback rồi select lại từ event loop |
| Coi `selected` là số lần lambda chạy hoặc số byte | Sai số liệu xử lý | Nhớ đó là **số key phân biệt được xử lý** |
| Cho rằng mỗi key chỉ callback đúng một lần | Sai khi nhiều loại readiness | Handler phải chịu được việc cùng key nhận nhiều lượt callback |
| Không kiểm tra `key.isValid()` | Có thể gặp `CancelledKeyException`/race | Kiểm tra valid, xử lý cancellation và concurrency |
| Hiểu `isReadable()` là đã nhận trọn message | Cắt thiếu frame/network payload | Đọc/ghi theo vòng, buffer, protocol framing |
| Giữ `OP_WRITE` liên tục | CPU spin do channel thường xuyên ghi được | Chỉ bật khi còn dữ liệu chờ, tắt khi đã gửi xong |
| Coi `selectNow(action)` là lời gọi có chờ | Vòng polling bận | Chọn blocking select/timeout hoặc cơ chế chờ |
| Coi `timeout == 0` là polling | Có thể block vô hạn | Dùng `selectNow(action)` nếu cần trả về ngay |
| Dùng `selectedKeys().isEmpty()` như tín hiệu callback | Phụ thuộc lịch sử/implementation | Dựa vào kết quả action và trạng thái ứng dụng |
| Callback ném `IOException` trực tiếp | Không biên dịch vì `Consumer.accept` không khai báo checked exception | Bắt/đóng gói lỗi, ví dụ `UncheckedIOException` |
| Đóng selector rồi nghĩ mọi socket cũng đã đóng | Rò rỉ tài nguyên channel | Quản lý vòng đời selector và channel riêng |
| Không có lối dừng cho blocking select | Thread chờ không cần thiết | Trạng thái dừng phối hợp `wakeup()/close()` |

**Checklist khi review mã:**

1. Channel có thể chọn và đã chuyển non-blocking trước `register` chưa?
2. Đã đăng ký đúng `interestOps` tương ứng với `validOps()` của channel chưa?
3. Selector và channel có `try-with-resources` hoặc chiến lược đóng rõ ràng không?
4. Callback có kiểm tra valid key và dùng đúng readiness bit không?
5. Đã xử lý `read() == 0`, `read() == -1` và ghi từng phần khi cần chưa?
6. Callback có công việc chặn quá lâu hoặc gọi select lồng nhau không?
7. Có xử lý lỗi callback, `IOException`, cancel và shutdown/wakeup không?
8. Đã hiểu `select(action, 0)` block vô hạn còn `selectNow(action)` không block chưa?
9. Có nhầm selected-key set với số callback hoặc danh sách sự kiện đã xử lý không?
10. Với server thật, đã kiểm soát OP_WRITE, buffer, backpressure và thread-safety chưa?

**Ghi nhớ:** `Selector.select(Consumer<SelectionKey>)` là API **Java 11+** dùng callback để xử lý key có channel sẵn sàng ngay trong thao tác selection. Callback được gọi đồng bộ, có thể gọi nhiều lần cho một key, và kết quả trả về là **số key phân biệt**. Dù không phải tự duyệt `selectedKeys()` cho sự kiện callback, ứng dụng vẫn phải quản lý non-blocking I/O, vòng đời channel/selector, lỗi và đồng bộ hóa.

## Tài liệu tham khảo chính thức, còn áp dụng

- [Oracle Java SE 11 — `Selector`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/Selector.html): chữ ký các overload `select(Consumer)` và `selectNow(Consumer)`, `Since: 11`, selection semantics và callback constraints.
- [Oracle Java SE 25 — `Selector`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/Selector.html): tài liệu API hiện hành về callback, selected-key set, blocking và concurrency.
- [Oracle Java SE 25 — `SelectionKey`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/SelectionKey.html): `interestOps`, `readyOps`, valid key, attachment và các operation bits.
- [Oracle Java SE 25 — `SelectableChannel`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/SelectableChannel.html): `configureBlocking(false)` và đăng ký channel.
- [Oracle Java SE 25 — `Pipe`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/Pipe.html): `SourceChannel`/`SinkChannel` dùng trong ví dụ.
- [Oracle Java SE 25 — `Consumer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Consumer.html): giao diện hàm được sử dụng làm callback.

Bài học sử dụng API từ Java 11 vẫn được duy trì và phân biệt rõ hợp đồng chuẩn của `Selector` với hành vi phụ thuộc provider.