# Đăng ký channel ở chế độ non-blocking với Java NIO `Selector`

## 1. Mục tiêu và phạm vi

Trong Java NIO, `Selector` cho phép một thread theo dõi **trạng thái sẵn sàng I/O** (*readiness*) của nhiều channel phù hợp, thay vì phải dành riêng một thread chặn ở mỗi socket. Để selector theo dõi một channel, chúng ta cần mở đúng **`SelectableChannel`**, đặt nó ở **non-blocking mode**, rồi đăng ký với `Selector` cùng tập thao tác quan tâm (*interest operations*).

Sau bài này, bạn sẽ:

- Hiểu điều kiện bắt buộc để `register(selector, ops)` thành công: channel phải thuộc `SelectableChannel`, có trạng thái mở, ở non-blocking mode và `ops` hợp lệ với channel.
- Sử dụng đúng thứ tự `configureBlocking(false)`, `Selector.open()`, `register(...)`, `select()` và duyệt `selectedKeys()`.
- Phân biệt `interestOps` (muốn theo dõi) và `readyOps` (selector đã xác định sẵn sàng); hiểu `SelectionKey` và attachment.
- Xử lý lỗi `IllegalBlockingModeException`, `IllegalArgumentException`, `ClosedChannelException`, hủy key và đóng tài nguyên.
- Tránh hai lỗi phổ biến trong vòng lặp event: quên xóa key đã xử lý khỏi tập selected keys và đăng ký `OP_WRITE` liên tục khi chưa có dữ liệu cần gửi.
- Viết ví dụ **Java 17+** chạy được với `Pipe.SourceChannel` và `Selector` trước khi chuyển sang socket thực tế.

Bài tập trung vào **đăng ký non-blocking channel** và hệ quả trực tiếp. Những phần thiết kế protocol TCP lớn, framing, backpressure và kết nối mạng phân tán được nhắc đến đúng mức cần thiết để áp dụng an toàn.

## 2. Ba vai trò: channel, selector và selection key

**`SelectableChannel`** là một lớp channel có thể đăng ký với selector. Các loại tiêu biểu:

| Channel | Thao tác quan tâm hợp lệ thường gặp | Ý nghĩa |
| --- | --- | --- |
| `ServerSocketChannel` | `SelectionKey.OP_ACCEPT` | Server socket có kết nối mới đang đợi `accept()` |
| `SocketChannel` | `OP_CONNECT`, `OP_READ`, `OP_WRITE` | Hoàn tất kết nối, có thể đọc hoặc có thể ghi |
| `DatagramChannel` | `OP_READ`, `OP_WRITE` | Datagram UDP có thể đọc/ghi |
| `Pipe.SourceChannel` | `OP_READ` | Đầu đọc của pipe có byte sẵn sàng |
| `Pipe.SinkChannel` | `OP_WRITE` | Đầu ghi của pipe có thể ghi |
| `FileChannel` | **Không có operation đăng ký selector** | File I/O, không phải `SelectableChannel` |

Các bit operation là **các hằng số của `SelectionKey`**, chẳng hạn `SelectionKey.OP_READ`, chứ không phải của `Selector`. Đừng đoán tập operation từ việc một channel có `read(ByteBuffer)` hay `write(ByteBuffer)`: dùng `channel.validOps()`.

**`Selector`** quản lý các kênh đã đăng ký và thực hiện thao tác chọn kênh có readiness phù hợp. Một selector có thể có nhiều registration.

**`SelectionKey`** biểu diễn một registration giữa **một channel và một selector**. Key nắm:

- `channel()`: channel đã đăng ký.
- `selector()`: selector sở hữu key.
- `interestOps()`: bitmask các thao tác ứng dụng hiện muốn quan sát.
- `readyOps()`: bitmask thao tác được lần chọn báo là sẵn sàng.
- `attachment()`: đối tượng trạng thái tùy chọn của ứng dụng.
- `isValid()`, `cancel()`: trạng thái vòng đời registration.

Một key thuộc về **cặp (channel, selector)**. Nếu channel đã đăng ký với selector đó, gọi `register` lần nữa thường **cập nhật interest ops và attachment của key hiện tại**, không tạo key thứ hai cho cùng cặp.

```text
                  Selector
                     |
       +-------------+-------------+
       |                           |
 SelectionKey A                SelectionKey B
 interestOps=OP_READ           interestOps=OP_ACCEPT
       |                           |
 Pipe.SourceChannel           ServerSocketChannel
       |                           |
  configureBlocking(false)    configureBlocking(false)
```

Sơ đồ minh họa ý nghĩa đăng ký, không phải mệnh đề rằng hai channel này luôn cùng một ứng dụng.

## 3. Vì sao phải gọi `configureBlocking(false)`?

Một selectable channel mới mở thường ở **blocking mode**. Ví dụ `ServerSocketChannel.accept()` có thể chờ một kết nối, còn `SocketChannel.read()` có thể chờ dữ liệu.

Đối với `Selector`, channel được đăng ký **phải ở non-blocking mode**. Quy trình chuẩn:

```java
try (Selector selector = Selector.open();
     ServerSocketChannel server = ServerSocketChannel.open()) {

    server.configureBlocking(false);
    server.bind(new InetSocketAddress("127.0.0.1", 0));
    SelectionKey key = server.register(
            selector, SelectionKey.OP_ACCEPT);

    // Bắt đầu vòng lặp select/accept...
}
```

Đoạn trên là **snippet minh họa**, cần import `java.nio.channels.Selector`, `ServerSocketChannel`, `SelectionKey`, `java.net.InetSocketAddress` và xử lý `IOException` trong phương thức bao quanh. `port=0` cho OS tự chọn cổng; ví dụ không in cổng nên không phụ thuộc giá trị được cấp.

Điều cần nhớ:

1. `configureBlocking(false)` cấu hình channel, **không** tạo selector và cũng không đăng ký ngầm.
2. `register(selector, ops)` gắn channel vào selector với tập thao tác quan tâm ban đầu; bản thân lời gọi này **không chờ** readiness.
3. `selector.select()` mới thực hiện bước đợi/chọn các key có operation đã đăng ký trở nên sẵn sàng.
4. Non-blocking không có nghĩa mọi I/O sẽ thành công đủ byte ngay. `read/write` có thể trả 0; `accept()` có thể trả `null` nếu tại thời điểm gọi không còn kết nối sẵn sàng.

Nếu đang blocking, gọi `register` sẽ ném **`IllegalBlockingModeException`**. Cách sửa là cấu hình `false` trước khi đăng ký, **không** cố bắt ngoại lệ rồi bỏ qua registration.

Sau khi đã đăng ký một channel với selector, không được tùy tiện gọi `configureBlocking(true)`: chuyển lại sang blocking mode khi còn registration hợp lệ sẽ ném `IllegalBlockingModeException`. `cancel()` của key có hiệu lực đánh dấu hủy ngay, nhưng **deregistration được xử lý trong hoạt động chọn tiếp theo của selector**. Vì vậy không nên giả định mọi đăng ký đã được xóa sạch ngay trong mọi thread chỉ vì đã gọi cancel; hãy quản lý trạng thái lifecycle rõ ràng.

## 4. Chọn `interestOps` hợp lệ với `validOps()`

Tham số `ops` của `register(selector, ops)` là một **bitmask**, có thể kết hợp bằng toán tử OR `|`:

```java
int interests = SelectionKey.OP_READ | SelectionKey.OP_WRITE;
```

Đây chỉ là cú pháp kết hợp, **không phải lựa chọn tốt mặc định** cho mọi channel. Mỗi loại channel chỉ hỗ trợ một tập bit nhất định. Kiểm tra:

```java
int requested = SelectionKey.OP_READ;
if ((requested & ~channel.validOps()) != 0) {
    throw new IllegalArgumentException("Operation not supported");
}
```

Snippet giả định `channel` là một `SelectableChannel`. Biểu thức `requested & ~channel.validOps()` tìm bit được yêu cầu nhưng không có trong `validOps`. Nếu khác 0, không nên đăng ký.

Một vài ví dụ:

- `Pipe.SourceChannel` hỗ trợ `OP_READ`. Đăng ký nó với `OP_WRITE` sẽ ném `IllegalArgumentException`.
- `Pipe.SinkChannel` hỗ trợ `OP_WRITE`, không dùng nó như channel đọc.
- `ServerSocketChannel` quan tâm `OP_ACCEPT`; đăng ký `OP_READ` trên server listener là sai kiểu operation.
- `SocketChannel` hỗ trợ `OP_CONNECT` để theo dõi quá trình kết nối chưa hoàn tất, rồi thường chuyển quan tâm sang `OP_READ` và tùy tình huống sang `OP_WRITE`.

Giá trị `ops=0` **hợp lệ**: channel vẫn đăng ký nhưng tạm thời không quan tâm operation nào. Khi cần, ứng dụng có thể cập nhật lại `interestOps`; đây là kỹ thuật hữu ích để điều tiết backpressure.

`validOps()` là thông tin khả năng của loại channel. Nó không nói rằng mọi operation đang được báo ready tại thời điểm kiểm tra.

## 5. `register` tạo/cập nhật `SelectionKey` như thế nào?

Hai overload thường dùng:

```java
SelectionKey key = channel.register(selector, ops);
SelectionKey keyWithAttachment = channel.register(
        selector, ops, attachment);
```

Đây là snippet minh họa, cần khai báo `channel`, `selector`, `ops` và `attachment`.

**Attachment** là object ứng dụng lưu cùng key. Ví dụ:

- Buffer đầu vào/đầu ra của một socket.
- Mã kết nối, trạng thái xử lý protocol.
- Một đối tượng giữ state đọc header và chờ đủ payload.

`attach(object)` của `SelectionKey` có thể thay thế attachment hiện tại. `attachment()` trả object đó hoặc `null` nếu chưa gắn. Khi register lại cùng channel/selector, dùng overload không có attachment sẽ không nhất thiết thay đổi attachment; dùng overload có attachment để đặt attachment mới một cách rõ ràng.

Cần phân biệt:

| Thao tác | Hiệu ứng |
| --- | --- |
| `register(selector, OP_READ)` | Đăng ký mới hoặc cập nhật interest ops của registration hiện có |
| `key.interestOps(OP_READ)` | Đặt lại toàn bộ tập interest operations của key |
| `key.interestOps(key.interestOps() | OP_WRITE)` | Thêm OP_WRITE vào interest ops hiện có |
| `key.interestOps(key.interestOps() & ~OP_WRITE)` | Loại OP_WRITE khỏi tập quan tâm |
| `key.attach(state)` | Gắn trạng thái riêng của ứng dụng |
| `key.cancel()` | Hủy registration; key trở thành không hợp lệ |
| `channel.close()` | Đóng channel; các registration liên quan bị hủy |

**Cập nhật `interestOps`** không đồng nghĩa điều kiện readiness vừa đổi hoặc đã được selector phản ánh ngay trong một lượt `select` đang diễn ra. Nếu một thread khác sửa interest set trong lúc thread selector đang đợi, cần thiết kế cách đánh thức selector phù hợp (`selector.wakeup()`) và đồng bộ state của ứng dụng.

## 6. Ví dụ Java 17+ chạy được: đăng ký `Pipe.SourceChannel` và xử lý `OP_READ`

`Pipe` giúp học selector mà không phụ thuộc cổng TCP hay firewall. Đầu sink ghi một số byte ngắn; đầu source được đăng ký trong non-blocking mode. Đây là chương trình độc lập.

Lưu tên file **`PipeRegistrationDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

public class PipeRegistrationDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);

            SelectionKey key = source.register(
                    selector, SelectionKey.OP_READ, "message-source");

            System.out.println("registered=" + key.isValid());
            System.out.println("attachment=" + key.attachment());
            System.out.println("interestedInRead="
                    + ((key.interestOps() & SelectionKey.OP_READ) != 0));

            byte[] payload = "HELLO".getBytes(StandardCharsets.US_ASCII);
            ByteBuffer toSend = ByteBuffer.wrap(payload);

            // Sink blocking mặc định, payload nhỏ; ghi đủ 5 byte.
            while (toSend.hasRemaining()) {
                sink.write(toSend);
            }

            ByteArrayOutputStream received = new ByteArrayOutputStream();

            while (received.size() < payload.length) {
                int selected = selector.select(2000);
                if (selected == 0) {
                    throw new IOException("Timed out waiting for readable pipe");
                }

                Iterator<SelectionKey> iterator =
                        selector.selectedKeys().iterator();

                while (iterator.hasNext()) {
                    SelectionKey selectedKey = iterator.next();
                    iterator.remove(); // Không xử lý lại key cũ ở lượt sau.

                    if (!selectedKey.isValid() || !selectedKey.isReadable()) {
                        continue;
                    }

                    ByteBuffer input = ByteBuffer.allocate(16);
                    int count = source.read(input);

                    if (count == -1) {
                        throw new IOException("Pipe ended before complete data");
                    }
                    if (count > 0) {
                        input.flip();
                        byte[] bytes = new byte[input.remaining()];
                        input.get(bytes);
                        received.write(bytes, 0, bytes.length);
                    }
                }
            }

            System.out.println("receivedBytes=" + received.size());
            System.out.println("text="
                    + received.toString(StandardCharsets.US_ASCII));
        }
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac PipeRegistrationDemo.java
java PipeRegistrationDemo
```

Stdout nếu các thao tác pipe, selector và I/O đều thành công:

```text
registered=true
attachment=message-source
interestedInRead=true
receivedBytes=5
text=HELLO
```

**Giải thích chi tiết:**

1. `Pipe.open()` tạo hai đầu liên kết. `source` nhận dữ liệu do `sink` ghi.
2. `source.configureBlocking(false)` phải chạy **trước** `source.register(...)`.
3. `register(selector, OP_READ, "message-source")` tạo key và gắn nhãn tùy chọn.
4. `sink.write(toSend)` chuyển lần lượt toàn bộ 5 byte `HELLO`. Sự kiện đọc từ source là sẵn sàng mà không cần socket mạng.
5. `selector.select(2000)` chờ tối đa 2 giây; nếu hệ thống không báo readiness trong khoảng đó, chương trình báo lỗi thay vì giả vờ thành công.
6. `selectedKeys()` là **tập key được chọn**, cần duyệt và `iterator.remove()` khi đã xử lý. Loại bỏ khỏi tập selected không đồng nghĩa hủy đăng ký.
7. `source.read(input)` trả số byte thực đọc. Vì channel non-blocking, lần đọc có thể trả `0`; chương trình chỉ đưa dữ liệu vào kết quả khi `count > 0`.
8. Khi tích đủ 5 byte, chương trình in chính xác `HELLO`. Không giả định một lần `read()` luôn nhận đủ toàn bộ payload.
9. `try-with-resources` đóng các channel và selector. Sau khi source/sink đóng, không tiếp tục dùng chúng.

**Lưu ý:** Bài toán thực tế dùng socket không thể biết trước lúc nào đủ một message chỉ dựa trên một sự kiện `OP_READ`. Thường cần buffer, framing (độ dài hoặc dấu phân cách) và logic giữ lại byte dở. Ví dụ pipe dùng payload 5 byte đã biết để tập trung vào thao tác đăng ký.

## 7. Ví dụ Java 17+ chạy được: các lỗi đăng ký

Một lỗi thường gặp là cố đăng ký channel đang blocking; lỗi khác là chọn operation không nằm trong `validOps()`.

Lưu file **`RegistrationErrorsDemo.java`**:

```java
import java.nio.channels.IllegalBlockingModeException;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;

public class RegistrationErrorsDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            try {
                // SourceChannel mặc định ở blocking mode.
                source.register(selector, SelectionKey.OP_READ);
            } catch (IllegalBlockingModeException expected) {
                System.out.println("blocking registration rejected");
            }

            source.configureBlocking(false);

            try {
                // Source chỉ đọc được, không đăng ký OP_WRITE.
                source.register(selector, SelectionKey.OP_WRITE);
            } catch (IllegalArgumentException expected) {
                System.out.println("invalid operation rejected");
            }

            SelectionKey key =
                    source.register(selector, SelectionKey.OP_READ);
            System.out.println("read registration valid=" + key.isValid());

            try {
                // Đang có registration hợp lệ: không bật blocking lại.
                source.configureBlocking(true);
            } catch (IllegalBlockingModeException expected) {
                System.out.println("switch to blocking rejected");
            }

            key.cancel();
            System.out.println("valid after cancel=" + key.isValid());
        }
    }
}
```

```bash
javac RegistrationErrorsDemo.java
java RegistrationErrorsDemo
```

Stdout khi chạy thành công:

```text
blocking registration rejected
invalid operation rejected
read registration valid=true
switch to blocking rejected
valid after cancel=false
```

Các ngoại lệ là **tình huống được tạo có chủ ý để học API**, không phải cách khuyến nghị điều khiển luồng chính. Trong sản phẩm thật, hãy kiểm tra thiết kế và cấu hình channel trước khi đăng ký, dùng `validOps()` và kiểm soát key lifecycle.

Khi `key.cancel()` được gọi, `key.isValid()` trở thành `false` ngay. Selector sẽ xử lý việc deregister bị trì hoãn trong quá trình chọn tiếp theo. **Không** suy diễn rằng key hết hợp lệ thì mọi tài nguyên của channel đã được đóng: muốn ngừng dùng channel phải đóng đúng đối tượng sở hữu.

## 8. `Selector.select()`, `selectNow()` và `wakeup()`

Nhóm phương thức chọn thường gặp:

| Phương thức | Hành vi |
| --- | --- |
| `selector.select()` | Có thể chặn cho tới khi có sự kiện chọn, wakeup, interrupt hoặc trường hợp khác theo hợp đồng |
| `selector.select(timeoutMillis)` | Chờ tối đa thời hạn đã chỉ định; số `0` có thể do timeout hoặc các nguyên nhân khác |
| `selector.selectNow()` | Thực hiện thao tác chọn không chờ |
| `selector.wakeup()` | Khiến một thao tác chọn đang đợi (hoặc lần chọn tiếp theo trong những trường hợp phù hợp) trả về |
| `selector.selectedKeys()` | Tập key đã được đưa vào selected-key set |
| `selector.keys()` | Tập key đang đăng ký với selector (khác selected-key set) |

Kết quả trả về của `select()` là **số key được cập nhật/đưa vào tập selected trong lượt chọn**, không phải số byte sẵn sàng và không đồng nghĩa số connection mới. Một `SelectionKey` có thể biểu diễn nhiều operation readiness; không cộng số bit rồi coi là số kết nối.

Lệnh `select(0)` không có nghĩa “poll ngay lập tức”; trong Java API, timeout bằng 0 có thể mang ý nghĩa chờ không giới hạn. Nếu mục đích là kiểm tra không chờ, dùng `selectNow()`.

`wakeup()` hữu ích khi thread khác đã bổ sung công việc, cần selector loop sớm cập nhật `interestOps` hoặc xử lý yêu cầu đóng. Khi dùng selector nhiều thread, quản lý an toàn của danh sách công việc, của key và việc wakeup có ý nghĩa không kém lời gọi API.

Một vòng event loop phải xử lý trường hợp không có key được chọn mà vẫn cần chạy việc khác; không cố xem mọi kết quả `0` là EOF.

## 9. `interestOps` khác `readyOps`: điều ứng dụng muốn so với điều selector thấy

Một key có thể quan tâm `OP_READ` nhưng tại thời điểm kiểm tra chưa có byte nào để đọc:

```text
interestOps = OP_READ        // mong muốn theo dõi
readyOps    = 0              // chưa báo sẵn sàng
```

Khi selector cập nhật key, nó có thể báo `readyOps` chứa `OP_READ`:

```text
interestOps = OP_READ
readyOps    = OP_READ
```

Khi đó gọi `key.isReadable()` tiện hơn so với tự kiểm tra bit:

```java
if (key.isValid() && key.isReadable()) {
    // Thử đọc từ channel nonblocking và kiểm tra số byte thực đọc.
}
```

Đây là snippet, yêu cầu `key` là `SelectionKey` do selector cung cấp. `isReadable()` chỉ nên hỏi khi key hợp lệ; một số thao tác đọc state key không hợp lệ có thể ném `CancelledKeyException`.

Không dùng `isReadable()` thay cho kết quả `read()`. Readiness mang tính tức thời, đặc biệt khi nhiều thread hoặc nhiều đường truy cập cùng dùng kênh; sau event, `read()` vẫn có thể trả 0, có thể đọc ít byte, hoặc trả `-1` nếu phía kia đã đóng và không còn dữ liệu.

`interestOps` là **bitmask muốn theo dõi**, `readyOps` là **bitmask của hoạt động báo ready**; chúng không tương đương và không được giải thích như một độ dài buffer.

## 10. Duyệt selected keys đúng cách

Skeleton event loop điển hình:

```java
while (running) {
    selector.select();

    Iterator<SelectionKey> iterator =
            selector.selectedKeys().iterator();

    while (iterator.hasNext()) {
        SelectionKey key = iterator.next();
        iterator.remove();

        if (!key.isValid()) {
            continue;
        }

        if (key.isAcceptable()) {
            // Nhận kết nối (ServerSocketChannel).
        }
        if (key.isConnectable()) {
            // Hoàn tất connect (SocketChannel.finishConnect()).
        }
        if (key.isReadable()) {
            // Đọc dữ liệu từ channel.
        }
        if (key.isWritable()) {
            // Ghi phần dữ liệu đang chờ trong output queue.
        }
    }
}
```

Đây là **skeleton minh họa**, không phải chương trình độc lập: `running`, `selector`, các handler và import cần do ứng dụng cung cấp. Nó cố ý không đóng vai trò server TCP hoàn chỉnh.

### Tại sao phải gọi `iterator.remove()`?

`selectedKeys()` giữ các key đã được chọn. Nếu không loại key sau xử lý, ứng dụng có thể xử lý lại trạng thái cũ một cách không mong muốn trong các lượt sau. `iterator.remove()` chỉ **gỡ key khỏi selected-key set**, không hủy registration và không đóng channel.

Đừng gọi `selector.selectedKeys().clear()` trước khi handler đọc dữ liệu cần xử lý, vì như vậy sẽ làm mất danh sách sự kiện của lượt hiện tại. Cũng đừng gọi `key.cancel()` chỉ vì đã xử lý một sự kiện: cancel sẽ ngừng registration cho những lượt sau.

### Handler phải kiểm tra kết quả I/O

Đối với `SocketChannel.read(buffer)`:

- `n > 0`: nhận `n` byte.
- `n == 0`: chưa có byte để đọc trong lần gọi nonblocking này.
- `n == -1`: đã đến trạng thái cuối input stream của channel (EOF); cần đóng/cập nhật connection theo protocol.

Đối với `SocketChannel.write(buffer)`, kết quả là số byte **thực ghi**, có thể bằng 0 hoặc nhỏ hơn `buffer.remaining()` trước khi gọi. Vì vậy phải giữ byte chưa ghi trong output buffer/queue, thay vì giả định đã gửi xong.

## 11. Chuyển sang TCP: `OP_ACCEPT`, `OP_CONNECT` và `OP_READ`

### 11.1. Server nhận kết nối

Luồng cơ bản:

```java
ServerSocketChannel server = ServerSocketChannel.open();
server.configureBlocking(false);
server.bind(new InetSocketAddress("127.0.0.1", 8080));

SelectionKey serverKey =
        server.register(selector, SelectionKey.OP_ACCEPT);
```

Đây là snippet cần import, một `Selector` mở sẵn, xử lý `IOException` và quản lý đóng server. Cổng 8080 chỉ để minh họa; thực tế có thể bị chiếm hoặc không có quyền bind.

Khi `serverKey.isAcceptable()`:

```java
ServerSocketChannel listener =
        (ServerSocketChannel) serverKey.channel();
SocketChannel client = listener.accept();

if (client != null) {
    client.configureBlocking(false);
    client.register(selector, SelectionKey.OP_READ);
}
```

Cũng là snippet: `accept()` của server nonblocking **có thể trả `null`** nếu không còn kết nối sẵn sàng. Mỗi client được accept là một channel **mới**; phải cấu hình nonblocking cho chính client đó rồi mới register vào selector.

Trong ứng dụng thật, nên attach state của kết nối, chuẩn bị buffer, giới hạn số client, cấu hình timeout và đảm bảo đóng client khi handler thất bại. Không để channel rò rỉ chỉ vì exception giữa `accept` và `register`.

### 11.2. Client kết nối nonblocking

`SocketChannel.connect(remote)` có thể:

- Trả `true` nếu kết nối hoàn tất ngay.
- Trả `false` nếu quá trình kết nối đang diễn ra; khi đó thường đăng ký `OP_CONNECT` để chờ thông báo.

```java
SocketChannel client = SocketChannel.open();
client.configureBlocking(false);

boolean connected = client.connect(remote);
int ops = connected
        ? SelectionKey.OP_READ
        : SelectionKey.OP_CONNECT;

client.register(selector, ops);
```

Snippet giả định `remote` là `SocketAddress` hợp lệ và `selector` đã mở. Khi key connectable, handler phải gọi `client.finishConnect()`, kiểm tra kết quả và xử lý `IOException` như `ConnectException` nếu kết nối thất bại. Khi kết nối hoàn tất, cập nhật interest ops cho những công việc tiếp theo như `OP_READ`.

Không coi sự kiện `OP_CONNECT` là bằng chứng kết nối thành công tuyệt đối mà bỏ qua `finishConnect()`. Cũng không đăng ký `OP_READ` rồi kỳ vọng đọc được data trước khi hoàn tất connect.

### 11.3. Vì sao `OP_WRITE` cần được bật có điều kiện?

Trên TCP thông thường, socket thường **sẵn sàng ghi** phần lớn thời gian. Nếu đăng ký `OP_WRITE` liên tục ngay cả khi output queue trống, vòng selector có thể thức dậy nhiều lần mà không có công việc, dẫn đến CPU cao.

Mẫu xử lý:

1. Khi ứng dụng có byte chờ gửi, ghi thử vào channel.
2. Nếu chưa gửi hết, giữ lại phần còn lại trong queue/buffer và **thêm `OP_WRITE` vào interest ops**.
3. Khi key writable, ghi tiếp; mỗi lần kiểm tra byte thực sự đã ghi.
4. Khi output queue trống, **bỏ `OP_WRITE`** nhưng thường giữ `OP_READ`.
5. Tránh vòng lặp bận khi một lần `write()` trả `0`; chờ readiness tiếp theo.

Ví dụ cập nhật key (snippet):

```java
// Còn byte cần gửi:
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// Khi đã gửi hết:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

Cần `key.isValid()` khi thao tác trong môi trường có cancellation. Trong ứng dụng đa luồng, dùng cơ chế đồng bộ thích hợp nếu thread khác cũng thay đổi `interestOps`.

## 12. Hủy key, đóng channel và chuyển blocking mode

Ba thao tác có tác dụng khác nhau:

| Thao tác | Điều xảy ra |
| --- | --- |
| `key.cancel()` | Key trở thành invalid ngay; yêu cầu deregister, channel chưa tự đóng |
| `channel.close()` | Đóng kênh; mọi registration liên quan bị hủy |
| `selector.close()` | Đóng selector và hủy các registration; **không tự động đóng mọi channel đã đăng ký** |

Sau cancel, key không còn dùng hợp lệ để điều khiển interest ops. Khi muốn thay đổi registration, phải xem xét trạng thái cancellation/deregistration thay vì gọi `register` liên tục trên key đã hủy rồi mong một key hợp lệ mới xuất hiện ngay.

Muốn đổi channel đang registered trở lại blocking mode cần bảo đảm nó **không còn đăng ký với selector nào**; việc hủy key và xử lý deregistration có thể cần một lượt selection để có hiệu lực. Điều này liên quan tới đồng bộ thread: tránh đổi mode trong lúc selector thread còn đang xử lý key đó.

Nếu bạn muốn ngừng vòng lặp, thường nên:

1. Đặt trạng thái dừng trong ứng dụng theo cách thread khác nhìn thấy được.
2. Gọi `selector.wakeup()` nếu thread selector đang chặn trong `select()`.
3. Để chính event-loop xử lý cleanup ở điểm an toàn: hủy key, đóng channel, sau đó đóng selector.
4. Thực hiện `try-with-resources` hoặc cleanup rõ ràng cho tài nguyên mới mở.

Đừng nhầm **remove khỏi selected-key set** với **cancel registration** hoặc **close channel**.

## 13. Các ngoại lệ chính khi đăng ký

| Tình huống | Ngoại lệ/kết quả |
| --- | --- |
| Channel vẫn ở blocking mode khi gọi `register` | `IllegalBlockingModeException` |
| Yêu cầu operation nằm ngoài `validOps()` | `IllegalArgumentException` |
| Channel đã đóng | `ClosedChannelException` |
| Selector đã đóng | `ClosedSelectorException` |
| Đặt blocking mode `true` khi channel còn registration hợp lệ | `IllegalBlockingModeException` |
| Đọc `interestOps` / `readyOps` từ key đã cancel | Có thể ném `CancelledKeyException` |
| `SelectionKey.cancel()` | Key invalid; cần xử lý deregistration về sau |
| `selector.select(timeout)` trả 0 | Không có key mới trong kết quả, có thể timeout/wakeup; không phải EOF của channel |
| `SocketChannel.read(buffer)` trả `-1` | EOF của dòng byte channel, không phải key bị hủy |

Lưu ý: ngoại lệ có thể xuất hiện trong luồng code khi tài nguyên bị đóng từ thread khác. Kiểm tra `isOpen()` ngay trước một thao tác chỉ là quan sát tại thời điểm đó; không thể loại bỏ hoàn toàn race condition. Vẫn phải bắt lỗi ở biên I/O.

## 14. Lỗi phổ biến và cách sửa

1. **Đăng ký trước khi chuyển nonblocking:** gọi `configureBlocking(false)` trước `register`.
2. **Dùng `FileChannel` với `Selector`:** `FileChannel` không phải `SelectableChannel`; sử dụng API file đồng bộ hoặc `AsynchronousFileChannel` tùy mục tiêu.
3. **Đăng ký sai operation:** `Pipe.SourceChannel` không hỗ trợ `OP_WRITE`, server listener không hỗ trợ `OP_READ`; tra `validOps()`.
4. **Đọc `isReadable()` trên key đã hủy:** kiểm tra `key.isValid()` và thiết kế lifecycle phù hợp.
5. **Quên `iterator.remove()`:** selected-key set giữ key cũ; xóa khỏi tập sau khi lấy ra xử lý.
6. **Hủy key sau mỗi sự kiện:** sẽ ngừng theo dõi channel; chỉ cancel khi thực sự muốn deregister.
7. **Đóng selector rồi tưởng socket/channel cũng đã đóng:** phải sở hữu và đóng các channel rõ ràng.
8. **Giữ `OP_WRITE` mãi:** khi không có dữ liệu chờ ghi, sự kiện writable thường luôn xảy ra, gây bận CPU.
9. **Giả định readable là đọc được cả frame:** `read()` có thể trả 0, đọc một phần, hoặc EOF; cần parser có trạng thái.
10. **Không xử lý kết nối TCP đang pending:** dùng `OP_CONNECT` và `finishConnect()` trước khi bắt đầu đọc/ghi ở trạng thái connected.
11. **Dùng `selector.select(0)` để poll:** xem hợp đồng timeout; khi cần không chờ hãy dùng `selectNow()`.
12. **Thay interest ops từ worker mà không wakeup:** event loop có thể tiếp tục chờ một event cũ; dùng queue công việc và `wakeup()` đúng lúc.
13. **Nhầm attachment là một bản sao trạng thái tự đồng bộ:** attachment chỉ là reference object của ứng dụng; với nhiều thread cần bảo đảm đồng bộ/visibility.
14. **Gọi `configureBlocking(true)` ngay sau `key.cancel()` và suy ra đã deregister xong:** deregistration được selector xử lý theo vòng đời, phải phối hợp an toàn.
15. **Kết luận từ số `select()` trả về là đã đọc được từng ấy byte:** đó là số key được chọn/cập nhật, còn số byte phải đọc từ kết quả I/O.

## 15. Bài tập vận dụng

### Bài A — đăng ký channel đúng thứ tự

Tạo `Pipe`, gọi `source.register(selector, OP_READ)` khi channel vẫn blocking rồi quan sát ngoại lệ. Sau đó `source.configureBlocking(false)`, đăng ký lại, ghi 3 byte vào sink và dùng `selector.select(timeout)` để chờ sự kiện. Khi đọc, giải thích sự khác nhau giữa số key chọn và số byte đọc.

### Bài B — thử `validOps`

In `source.validOps()` và kiểm tra các bit `OP_READ` / `OP_WRITE` bằng toán tử bitwise. Vì sao `source.register(selector, OP_WRITE)` thất bại dù pipe cũng có `SinkChannel` ghi được?

### Bài C — thay đổi `interestOps`

Đăng ký `OP_READ`, gọi `key.interestOps(0)` rồi kiểm tra giá trị `key.interestOps()`; sau đó đăng ký/cập nhật lại `OP_READ`. Việc đặt 0 có đóng channel hay hủy key không? Tại sao?

### Bài D — thiết kế socket ghi một phần

Một socket có output queue 64 KiB, nhưng lần `write(buffer)` đầu chỉ ghi 8 KiB. Bạn cần giữ phần 56 KiB còn lại ra sao? Khi nào bật `OP_WRITE`, khi nào bỏ nó, và tại sao không gọi write trong vòng lặp bận khi kết quả là 0?

### Bài E — cleanup đúng

Từ chương trình `PipeRegistrationDemo`, hãy bổ sung tình huống cancel key trước khi đóng pipe. Quan sát `isValid()`. Giải thích vì sao `selector.selectedKeys().remove(key)` không thay thế `cancel()`, và vì sao đóng selector không phải thao tác đóng channel.

## 16. Câu hỏi tự kiểm tra

1. Có thể gọi `register` trực tiếp trên một `FileChannel` không? Vì sao?
2. Sự khác nhau giữa `Selector` và `SelectionKey` là gì?
3. Vì sao phải `configureBlocking(false)` trước `register`?
4. `SelectionKey.OP_READ | SelectionKey.OP_WRITE` là kiểu dữ liệu gì, có luôn hợp lệ cho mọi selectable channel không?
5. `channel.validOps()` kiểm tra điều gì? Nó có đồng nghĩa `readyOps()` không?
6. Một channel đã đăng ký với selector A; gọi register cùng selector A lần hai có bắt buộc tạo thêm key không?
7. Khi nào `isReadable()` trả true? Có đảm bảo `read()` sẽ trả đầy đủ frame message không?
8. Trong event loop, vì sao nên gọi `iterator.remove()` ngay khi lấy selected key để xử lý?
9. `SelectionKey.cancel()` và `SelectableChannel.close()` khác nhau thế nào?
10. `selector.close()` có tự đóng toàn bộ socket đã đăng ký không?
11. Khi client nonblocking gọi `connect(remote)` trả false, cần theo dõi bit operation nào và phương thức nào hoàn tất kết nối?
12. Tại sao giữ `OP_WRITE` ngay cả khi không có dữ liệu cần gửi có thể gây tải CPU cao?
13. Nếu selector thread đang đợi, thread khác vừa enqueue dữ liệu, `wakeup()` có vai trò gì?
14. `select(0)` và `selectNow()` có cùng ý nghĩa không?
15. Vì sao kết quả `select()` không phải số byte có thể đọc?

## 17. Tài liệu Java 17

- [`SelectableChannel` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html): `configureBlocking`, `register`, `validOps`.
- [`Selector` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select`, `selectedKeys`, `wakeup`, đóng selector.
- [`SelectionKey` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `interestOps`, `readyOps`, `OP_READ/WRITE/ACCEPT/CONNECT`, `cancel`, attachment.
- [`Pipe` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Pipe.html): cặp `SourceChannel/SinkChannel`.
- [`SocketChannel` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): kết nối nonblocking, `connect` và `finishConnect`.

## 18. Ghi nhớ

Quy trình đăng ký chuẩn là **mở `SelectableChannel` → `configureBlocking(false)` → mở `Selector` → `channel.register(selector, validOps, attachment)` → `selector.select()` → xử lý selected keys → quản lý interest ops và cleanup**.

`SelectionKey` nắm tập operation ứng dụng **muốn quan sát** và tập operation mà selector **báo sẵn sàng**. Sự kiện readiness chỉ là tín hiệu để **thử I/O**, không phải cam kết một lần `read/write` hoàn tất toàn bộ. Hãy kiểm tra kết quả thực, loại key đã xử lý khỏi selected-key set, chỉ bật `OP_WRITE` khi có dữ liệu đang chờ, và phân biệt `cancel`, `close channel` và `close selector`. Đó là nền tảng cần có trước khi xây event loop socket nonblocking đáng tin cậy.
