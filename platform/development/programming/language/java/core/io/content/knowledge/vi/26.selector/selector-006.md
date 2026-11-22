# Lặp `selectedKeys` và loại bỏ key đã xử lý trong Java NIO Selector

## 1. Vì sao phải xử lý và loại bỏ từng SelectionKey?

Khi lập trình mạng non-blocking bằng Java NIO, ứng dụng thường dùng **một vòng lặp sự kiện** (*event loop*) để quản lý nhiều socket qua `Selector`. Mỗi lần gọi `selector.select()`, hệ thống xác định các channel đã đăng ký có thao tác I/O nào đang **sẵn sàng** (*ready*). Những đăng ký đó được biểu diễn bằng `SelectionKey`.

Sau một lần chọn, chương trình lấy tập:

```java
Set<SelectionKey> selected = selector.selectedKeys();
```

**Đây không phải một hàng đợi tự tiêu thụ.** Tập `selectedKeys()` giữ những key đã được chọn cho đến khi ứng dụng chủ động loại chúng khỏi tập (hoặc khi key bị hủy, theo quy trình xử lý hủy đăng ký của selector). Nếu bạn lặp xử lý nhưng **không loại bỏ key**, nó có thể vẫn xuất hiện trong tập đã chọn ở các vòng sau. Kết quả dễ gặp là xử lý trùng trạng thái sẵn sàng cũ, log lặp, truy cập lại buffer sai pha và event loop khó kiểm soát.

Mẫu chuẩn:

```java
Iterator<SelectionKey> iterator =
        selector.selectedKeys().iterator();

while (iterator.hasNext()) {
    SelectionKey key = iterator.next();
    iterator.remove(); // Loại khỏi selected-key set.

    if (!key.isValid()) {
        continue;
    }

    // Xử lý sự kiện readiness được báo cho key này.
}
```

Điều quan trọng nhất: **`iterator.remove()` chỉ loại key ra khỏi tập đang được chọn**, chứ không mặc định đóng socket hay hủy đăng ký `SelectionKey`. Key có thể xuất hiện trở lại ở những lần `select()` tiếp theo nếu channel vẫn đăng ký, quan tâm đến sự kiện phù hợp và sẵn sàng.

## 2. Ba tập và ba trạng thái cần phân biệt

Trong một `Selector`, việc hiểu đúng ba khái niệm sau giúp tránh bug vòng lặp:

| Khái niệm | API | Ý nghĩa |
| --- | --- | --- |
| **Registered-key set** | `selector.keys()` | Các key hiện đang đăng ký với selector; không phải tập do ứng dụng tự xóa trực tiếp |
| **Selected-key set** | `selector.selectedKeys()` | Các key mà một lượt chọn đã xác định là sẵn sàng theo những interest phù hợp |
| **Canceled-key set** | Nội bộ của `Selector` | Các key đã được hủy và chờ selector xử lý dọn đăng ký |

Hai thao tác rất khác nhau:

- **`iterator.remove()`** trên iterator của `selectedKeys()`: lấy một key ra khỏi **selected-key set** sau khi đã nhận công việc từ lượt chọn. Đăng ký vẫn sống nếu key chưa bị hủy.
- **`key.cancel()`**: đánh dấu key **không còn hợp lệ**, yêu cầu hủy đăng ký với selector. Việc loại nó khỏi tập đăng ký được selector xử lý tại thời điểm thích hợp, thường trong một thao tác lựa chọn tiếp theo.

`key.cancel()` **không đóng channel**. Muốn kết thúc kết nối, ứng dụng thường phải gọi `channel.close()` và thu dọn state của kết nối. Đóng channel cũng khiến những key liên quan bị hủy, nhưng vẫn không đồng nghĩa bạn có thể bỏ qua quy tắc dọn vòng lặp và quản lý tài nguyên.

### Ví dụ tình huống

Một socket đang đăng ký `OP_READ` và có byte chờ đọc:

1. `selector.select()` nhận biết socket có thể đọc.
2. Key của socket nằm trong `selectedKeys()`.
3. Vòng lặp lấy key và gọi `iterator.remove()`.
4. Chương trình gọi `channel.read(buffer)`.
5. Nếu kết nối vẫn mở, key vẫn thuộc các đăng ký hợp lệ; khi điều kiện đọc xuất hiện ở một lượt chọn mới, key có thể được chọn **một lần nữa**.

**Không nên `cancel()` mọi key sau mỗi lần đọc**, bởi như vậy ứng dụng sẽ mất đăng ký và phải xây lại cơ chế theo dõi nếu muốn tiếp tục nhận dữ liệu.

## 3. Quy trình chuẩn: select → iterate → remove → dispatch

Luồng điều khiển thường dùng:

```text
                    +---------------------+
                    | selector.select()   |
                    +----------+----------+
                               |
                               v
                    +---------------------+
                    | selectedKeys()      |
                    +----------+----------+
                               |
                               v
                    +---------------------+
                    | iterator.hasNext()? |
                    +----------+----------+
                               |
                       yes     |     no
                        +------+------> Quay lại select()
                        |
                        v
               key = iterator.next()
                        |
                        v
                iterator.remove()
                        |
                        v
                 key.isValid()?
                  /           \
                no            yes
                |              |
         bỏ qua key      xử lý readyOps
                |              |
                +-------+------+
                        |
                        v
                  key tiếp theo
```

Các bước đáng ghi nhớ:

1. `select()` có thể trả về 0 (ví dụ do wakeup hoặc timeout). Không phải mỗi lần thức dậy đều có I/O để xử lý.
2. `selectedKeys()` chứa **tập** kết quả; không bảo đảm thứ tự các key.
3. `iterator.next()` chỉ lấy phần tử hiện tại trong tập.
4. `iterator.remove()` xóa **đúng phần tử vừa trả về bởi iterator**, an toàn khi chỉnh sửa tập trong lúc đang duyệt bằng iterator.
5. `key.isValid()` kiểm tra key có còn hợp lệ trước khi truy cập readiness hoặc cập nhật interest.
6. Xử lý các cờ phù hợp `isAcceptable()`, `isConnectable()`, `isReadable()`, `isWritable()`.
7. Thoát vòng iterator và quay lại `select()` khi ứng dụng chưa dừng.

Trong event loop thực, cần thêm xử lý ngoại lệ, đóng kết nối, giới hạn công việc mỗi lượt, hàng đợi ghi còn dở, timeout và cách thức dừng selector.

## 4. Vì sao dùng `Iterator.remove()` thay vì xóa tùy tiện?

Đoạn code sau **không nên dùng**:

```java
for (SelectionKey key : selector.selectedKeys()) {
    selector.selectedKeys().remove(key); // Sai cách trong khi for-each.
    // Xử lý key...
}
```

Vòng `for-each` thực chất duyệt bằng iterator. Thay đổi cấu trúc tập từ một đường khác khi iterator còn hoạt động có thể gây `ConcurrentModificationException` hoặc phụ thuộc cách triển khai. Hãy dùng iterator của **chính tập đó** và gọi `iterator.remove()`.

Cách đúng:

```java
Iterator<SelectionKey> it =
        selector.selectedKeys().iterator();

while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();

    if (!key.isValid()) {
        continue;
    }

    // Dispatch theo trạng thái ready của key.
}
```

**`iterator.remove()` phải theo sau một lần `next()` hợp lệ** và không gọi hai lần liên tiếp trên cùng phần tử. Gọi `remove()` trước `next()` hoặc lần thứ hai mà chưa có `next()` mới sẽ ném `IllegalStateException` theo hợp đồng Iterator.

Đặt `remove()` **ngay sau `next()`** giúp bảo đảm key được lấy ra khỏi tập đã chọn kể cả khi handler phía sau cần bỏ qua hoặc báo lỗi. Đây là một lựa chọn quản lý vòng đời event rõ ràng, không có nghĩa bản thân `remove()` đã xử lý xong byte ở socket.

### Có thể dùng `selectedKeys().clear()` không?

`selector.selectedKeys().clear()` là thao tác loại **toàn bộ** key khỏi selected set. Về mặt API, tập này cho phép remove/clear; nhưng xóa toàn bộ quá sớm sẽ bỏ các key **chưa được xử lý** trong lượt đang có. Do đó `clear()` chỉ phù hợp khi ứng dụng **cố ý bỏ qua toàn bộ selected events** hoặc đã có cơ chế snapshot/dispatch bảo đảm không mất công việc cần làm.

Không dùng `clear()` trước khi duyệt một lượt thông báo readiness với kỳ vọng vẫn xử lý đầy đủ các sự kiện vừa nhận. Mẫu `iterator.remove()` từng key rõ ràng và dễ kiểm soát hơn.

## 5. `remove()`, `cancel()`, `close()` và `interestOps(0)`

| Thao tác | Loại key khỏi selected set? | Đăng ký key còn hợp lệ? | Channel còn mở? |
| --- | --- | --- | --- |
| `iterator.remove()` | Có, với key vừa lấy | **Thường vẫn hợp lệ** nếu chưa bị hủy | Không đổi |
| `key.cancel()` | Không phải cơ chế “tiêu thụ selected event”; selector sẽ xử lý việc hủy | **Không**, key trở nên invalid | Không tự đóng |
| `key.channel().close()` | Gây hủy những đăng ký liên quan, selector dọn theo vòng đời | Không còn hợp lệ | **Không** |
| `key.interestOps(0)` | Không tự xóa key đang nằm trong selected set | Vẫn có thể hợp lệ | Không đổi |

**Hai phạm vi khác nhau:**

- **Consumed readiness**: đã lấy thông tin key ra để xử lý cho lượt select hiện tại; dùng `iterator.remove()`.
- **Lifecycle/cancellation**: không muốn selector theo dõi channel nữa; dùng `key.cancel()` và quyết định có cần `channel.close()` hay không.

Khi peer đóng chiều gửi và `read()` trả về `-1`, server thường hủy key và đóng socket (nếu protocol không cần giữ nửa kết nối). Khi chỉ đọc được vài byte của một thông điệp, **không** hủy key; giữ state để đợi các byte tiếp theo.

`interestOps(0)` có thể tạm dừng theo dõi readiness mà không hủy đăng ký. Nhưng nếu key đã được đưa vào selected-key set, bạn vẫn cần tiêu thụ/xóa entry của lượt chọn cũ; đổi interest không phải là một phép dọn selected-key set.

## 6. `interestOps` và `readyOps` không phải một

`SelectionKey` có hai tập bit quan trọng:

- **`interestOps()`**: những loại I/O mà ứng dụng muốn theo dõi, ví dụ `OP_READ` hoặc `OP_READ | OP_WRITE`.
- **`readyOps()`**: những loại I/O mà lượt chọn đã ghi nhận là đang sẵn sàng cho key.

Các phương thức tiện ích `isReadable()`, `isWritable()`, `isAcceptable()`, `isConnectable()` phản ánh những bit ready tương ứng; chúng **không kiểm tra interestOps**.

| Bit | Kênh điển hình | Cách xử lý |
| --- | --- | --- |
| `SelectionKey.OP_ACCEPT` | `ServerSocketChannel` | Gọi `accept()` và kiểm tra kết quả có thể là `null` |
| `SelectionKey.OP_CONNECT` | `SocketChannel` đang connect | Gọi `finishConnect()`, xử lý lỗi/kết nối còn dở |
| `SelectionKey.OP_READ` | `SocketChannel` đã kết nối | Gọi `read()`, kiểm tra `>0`, `0`, `-1` |
| `SelectionKey.OP_WRITE` | `SocketChannel` có dữ liệu chờ gửi | Thử `write()` phần pending, điều chỉnh interest khi gửi hết |

**Một key có thể có nhiều bit ready cùng lúc.** Vì vậy dùng chuỗi `if` độc lập khi các hoạt động phù hợp cùng một channel cần được xử lý trong một lượt, thay vì mặc định `else if` sẽ bao quát mọi trường hợp:

```java
if (key.isConnectable()) {
    // finishConnect() nếu kết nối đang chờ.
}
if (key.isValid() && key.isReadable()) {
    // read, giữ parser state.
}
if (key.isValid() && key.isWritable()) {
    // write phần pending.
}
```

Đây là đoạn minh họa; trong ứng dụng thực phải kiểm tra state kết nối, buffer pending và loại channel cụ thể. Với `ServerSocketChannel`, chỉ `OP_ACCEPT` là lựa chọn hợp lệ; không gọi `isReadable()` để kỳ vọng chấp nhận kết nối.

**Điểm tinh tế:** Theo hợp đồng `Selector`, key đã nằm trong selected set có thể được cập nhật tập ready operations ở các lần selection tiếp theo, thay vì được tự loại bỏ. Do đó **không xóa key** làm bạn tiếp tục quan sát key cũ và có thể pha trộn trạng thái sẵn sàng giữa các lượt. `iterator.remove()` giúp phân định rõ từng lượt xử lý.

## 7. Ví dụ Java 17+ số 1: Pipe, selected key và registered key

Để quan sát trực tiếp `selectedKeys()` mà không cần mạng bên ngoài, ta dùng `java.nio.channels.Pipe`. `Pipe.SourceChannel` có thể đăng ký `Selector` với `OP_READ`. `Pipe.SinkChannel` ghi dữ liệu vào pipe, làm source sẵn sàng đọc.

Ví dụ này ghi đúng hai byte ASCII `OK`, nhận qua selector, loại bỏ key đã chọn, rồi kiểm tra:

- selected set đã rỗng hay chưa;
- key có còn đăng ký với selector hay không.

**Tệp `SelectedKeysPipeDemo.java`:**

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public class SelectedKeysPipeDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);
            SelectionKey registered =
                    source.register(selector, SelectionKey.OP_READ);

            ByteBuffer outgoing = ByteBuffer.wrap(
                    "OK".getBytes(StandardCharsets.US_ASCII));
            while (outgoing.hasRemaining()) {
                sink.write(outgoing);
            }

            ByteBuffer received = ByteBuffer.allocate(2);
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(5);

            while (received.hasRemaining()) {
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) {
                    throw new IOException("Selection timeout");
                }

                long timeoutMs = Math.max(1L,
                        TimeUnit.NANOSECONDS.toMillis(remaining));
                selector.select(timeoutMs);

                Iterator<SelectionKey> iterator =
                        selector.selectedKeys().iterator();

                while (iterator.hasNext()) {
                    SelectionKey key = iterator.next();
                    iterator.remove();

                    if (!key.isValid()) {
                        continue;
                    }
                    if (key.isReadable()) {
                        int n = source.read(received);
                        if (n == -1) {
                            throw new EOFException("Pipe closed early");
                        }
                    }
                }
            }

            received.flip();
            String message = StandardCharsets.US_ASCII
                    .decode(received).toString();

            System.out.println("Nhan duoc: " + message);
            System.out.println("Selected set rong: "
                    + selector.selectedKeys().isEmpty());
            System.out.println("Key van dang ky: "
                    + selector.keys().contains(registered));
            System.out.println("Key con hop le: "
                    + registered.isValid());
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac SelectedKeysPipeDemo.java
java SelectedKeysPipeDemo
```

**Stdout khi các thao tác I/O và lựa chọn hoàn tất:**

```text
Nhan duoc: OK
Selected set rong: true
Key van dang ky: true
Key con hop le: true
```

### Giải thích kết quả

1. `source.configureBlocking(false)` là điều kiện để đăng ký vào selector.
2. `sink` ghi hai byte, nhờ đó `source` trở nên sẵn sàng đọc.
3. `select(timeoutMs)` chọn key của source khi có readiness.
4. `iterator.remove()` chỉ xóa phần tử đang duyệt khỏi **selected-key set**, không hủy key.
5. `source.read(received)` nhận số byte có sẵn. Vòng ngoài tiếp tục nếu chưa đủ hai byte; vì vậy stdout không phụ thuộc dữ liệu về trong một hay nhiều lần chọn.
6. `selector.selectedKeys().isEmpty() == true` sau khi mọi key đã được lấy ra.
7. `selector.keys().contains(registered) == true` và `registered.isValid() == true` cho thấy đăng ký vẫn còn sống.

Các dòng stdout không in số lượt `select()`, vì số lần event loop thức dậy có thể khác nhau theo lịch của hệ điều hành. Chương trình chỉ in trạng thái cuối trong điều kiện thành công.

**Lưu ý:** khi source/sink/selector rời `try-with-resources`, tài nguyên được đóng. Việc key còn hợp lệ ở thời điểm in **không có nghĩa nó sẽ tiếp tục hợp lệ sau khi channel hoặc selector đóng**.

## 8. Ví dụ Java 17+ số 2: TCP server chọn `OP_ACCEPT` và `OP_READ`

Ví dụ thứ hai thể hiện vòng lặp gần với ứng dụng server:

- Mở `ServerSocketChannel` trên loopback và cổng hệ điều hành tự cấp.
- Đặt server ở non-blocking mode và đăng ký `OP_ACCEPT`.
- Dùng client kết nối gửi bốn byte ASCII `PING`.
- Khi selector báo sẵn sàng chấp nhận, server tạo `SocketChannel` non-blocking và đăng ký `OP_READ`.
- Event loop đọc đến khi nhận đủ bốn byte, luôn dùng `iterator.remove()` cho từng key đã lấy.
- Sau khi hoàn tất thông điệp, server **hủy key và đóng client được chấp nhận** vì phiên làm việc đã hoàn thành.

**Tệp `SelectedKeysTcpDemo.java`:**

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public class SelectedKeysTcpDemo {
    public static void main(String[] args) throws IOException {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {

            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);

            try (SocketChannel sender = SocketChannel.open()) {
                sender.connect(server.getLocalAddress());
                ByteBuffer outgoing = ByteBuffer.wrap(
                        "PING".getBytes(StandardCharsets.US_ASCII));
                while (outgoing.hasRemaining()) {
                    sender.write(outgoing);
                }

                String result = null;
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(5);

                while (result == null) {
                    long nanos = deadline - System.nanoTime();
                    if (nanos <= 0) {
                        throw new IOException("TCP selection timeout");
                    }

                    long timeoutMs = Math.max(1L,
                            TimeUnit.NANOSECONDS.toMillis(nanos));
                    selector.select(timeoutMs);

                    Iterator<SelectionKey> iterator =
                            selector.selectedKeys().iterator();

                    while (iterator.hasNext()) {
                        SelectionKey key = iterator.next();
                        iterator.remove();

                        if (!key.isValid()) {
                            continue;
                        }

                        if (key.isAcceptable()) {
                            SocketChannel peer = server.accept();
                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(
                                        selector,
                                        SelectionKey.OP_READ,
                                        ByteBuffer.allocate(4));
                            }
                        } else if (key.isReadable()) {
                            SocketChannel peer =
                                    (SocketChannel) key.channel();
                            ByteBuffer buffer =
                                    (ByteBuffer) key.attachment();

                            int n = peer.read(buffer);
                            if (n == -1 && buffer.hasRemaining()) {
                                throw new EOFException(
                                        "Client closed before PING");
                            }

                            if (!buffer.hasRemaining()) {
                                buffer.flip();
                                result = StandardCharsets.US_ASCII
                                        .decode(buffer).toString();

                                key.cancel();
                                peer.close();
                            }
                        }
                    }
                }

                System.out.println("Nhan duoc: " + result);
                System.out.println("Selected set rong: "
                        + selector.selectedKeys().isEmpty());
                System.out.println("Server con mo: " + server.isOpen());
            }
        }
    }
}
```

Chạy:

```bash
javac SelectedKeysTcpDemo.java
java SelectedKeysTcpDemo
```

**Stdout khi kết nối loopback và I/O thành công:**

```text
Nhan duoc: PING
Selected set rong: true
Server con mo: true
```

### Điều gì được chứng minh?

- Trong cùng một vòng đời selector, key của server có thể sẵn sàng **accept**, còn key của peer có thể sẵn sàng **read**.
- Mỗi key đã lấy được **loại khỏi selected set ngay**; điều này độc lập với việc có hủy key hay không.
- Key của server tiếp tục sống để có thể chấp nhận các kết nối sau; key của peer đã xử lý đủ một thông điệp được `cancel()` và socket được đóng.
- `ByteBuffer` được gắn bằng `register(selector, OP_READ, attachment)` và đọc dần đến khi đủ bốn byte. Không mặc định một lần `read()` trả đủ bốn byte.

Trong ví dụ này, `else if` phù hợp vì `OP_ACCEPT` và `OP_READ` được đăng ký cho **hai loại channel khác nhau** và mỗi key chỉ phục vụ một nhánh. Với `SocketChannel` có cả `OP_READ` và `OP_WRITE`, cần kiểm tra độc lập những bit ready cần xử lý, kèm kiểm tra lại `key.isValid()` nếu handler trước có thể đóng socket.

**Phạm vi ví dụ:** server chỉ nhận một thông điệp cố định bốn byte từ một client loopback. Ứng dụng thật cần framing cho TCP stream, giới hạn buffer, hàng đợi gửi, timeout riêng cho từng kết nối, cleanup khi lỗi và cơ chế shutdown event loop.

## 9. Readiness không đồng nghĩa đã xử lý xong dữ liệu

Giả sử `selector.select()` báo một `SocketChannel` sẵn sàng đọc:

```java
int count = socket.read(inputBuffer);
```

Có thể gặp:

| Kết quả | Diễn giải | Cách xử lý |
| --- | --- | --- |
| `count > 0` | Đã nhận đúng `count` byte | Cập nhật parser/buffer state; giữ đăng ký nếu cần thêm |
| `count == 0` | Lần đọc này chưa có tiến độ | Không spin; quay lại selector hoặc điều chỉnh interest |
| `count == -1` | EOF phía nhận | Kết thúc hoặc xử lý half-close theo giao thức |
| Ném `IOException` | Lỗi I/O | Cleanup key/channel/buffer theo chính sách |

Ngay cả khi key được chọn là readable, `read` không cam kết lấp đầy buffer hoặc trả dữ liệu nguyên thông điệp. Ready là trạng thái *có thể thực hiện I/O*, không phải một bản sao dữ liệu đợi sẵn để ứng dụng tiêu thụ tùy thích.

Vì vậy:

- **`iterator.remove()`** nghĩa là “tôi đã lấy thông tin readiness của lượt này ra khỏi tập”, **không có nghĩa** “tôi đã nhận hết dữ liệu của socket”.
- **`key.cancel()`** nghĩa là “tôi không cần đăng ký này nữa”, không dùng thay cho xử lý phần còn dở.
- **`inputBuffer.compact()`** giữ byte chưa được parser xử lý để nhận thêm, khác hoàn toàn với thao tác loại key khỏi selected set.

Tách bạch ba cấp — *event*, *đăng ký*, *nội dung byte* — là nguyên tắc quan trọng khi viết event loop.

## 10. Đặt `remove()` trước hay sau phần xử lý?

Có hai cách có thể thấy trong mã nguồn:

```java
SelectionKey key = iterator.next();
iterator.remove();
process(key);
```

và

```java
SelectionKey key = iterator.next();
process(key);
iterator.remove();
```

Chúng đều dựa trên cùng API iterator nếu `process` không làm thay đổi chính tập đang duyệt. Tuy nhiên **đặt `remove()` ngay sau `next()` là lựa chọn bền vững hơn** khi handler có thể ném lỗi, đóng channel hoặc cần `continue` sang key khác.

Nếu mã đặt `remove` sau handler mà handler ném ngoại lệ trước khi đến lệnh này, key vẫn nằm trong selected-key set. Tùy cách vòng lặp phục hồi, key ấy có thể bị xử lý lại một cách không có chủ ý.

Nếu vì yêu cầu đặc biệt cần hoãn remove, có thể dùng cấu trúc `try/finally` cẩn thận, nhưng phải tránh gọi `remove()` sai trạng thái và phải hiểu hành vi khi iterator bị thay đổi. Với phần lớn event loop một luồng, cách đơn giản nhất vẫn là **lấy key, remove ngay, rồi dispatch**.

## 11. Xử lý ngoại lệ theo từng key để tránh làm hỏng cả vòng lặp

Trong ứng dụng production, một client hỏng không nên mặc định làm toàn bộ selector dừng phục vụ các client còn lại. Một mẫu xử lý:

```java
Iterator<SelectionKey> it =
        selector.selectedKeys().iterator();

while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();

    if (!key.isValid()) {
        continue;
    }

    try {
        handleReadyKey(key);
    } catch (IOException ex) {
        key.cancel();

        try {
            key.channel().close();
        } catch (IOException closeError) {
            ex.addSuppressed(closeError);
        }

        // Ghi log/metric có ngữ cảnh, tiếp tục key khác
        // nếu chính sách ứng dụng cho phép.
    }
}
```

Đây là **đoạn mã minh họa**: `selector` và `handleReadyKey` chưa được khai báo nên không phải chương trình biên dịch độc lập. Cần xét những ngoại lệ unchecked như `CancelledKeyException`, `IllegalArgumentException` hoặc lỗi lập trình có thể xuất hiện; không nên vô điều kiện nuốt tất cả `RuntimeException` và tiếp tục như không có gì xảy ra.

Chỉ gọi `key.cancel()` khi thực sự muốn ngừng theo dõi đăng ký; với lỗi I/O của peer dẫn đến đóng socket, đó thường là lựa chọn phù hợp. Bất cứ state nào đi kèm key (attachment) cũng cần được giải phóng hoặc xử lý tồn đọng khi kết thúc kết nối.

**Quy tắc tối thiểu:** tách lỗi của từng kết nối khỏi lỗi cấp selector; sau lỗi nghiêm trọng ở selector, phải có chiến lược tái tạo hoặc dừng event loop.

## 12. `selectedKeys()` khác `keys()`

Hai tập thường bị nhầm vì đều chứa `SelectionKey`:

```java
Set<SelectionKey> allRegistered = selector.keys();
Set<SelectionKey> readySelected = selector.selectedKeys();
```

- `keys()`: tập các đăng ký thuộc selector. Tập trả về không cho phép ứng dụng trực tiếp thêm/xóa key; có thể ném `UnsupportedOperationException` nếu cố sửa.
- `selectedKeys()`: tập các key được chọn và **cho phép remove/clear**; ứng dụng không thể tùy ý thêm key vào đó.

Khi `iterator.remove()` từ `selectedKeys()`, `keys()` vẫn có thể chứa key đó. Đây chính là kết quả của `SelectedKeysPipeDemo`.

Cũng cần phân biệt giữa key **được chọn** và key **còn hợp lệ**: một key đã bị `cancel()` có thể đang chờ selector xử lý dọn đăng ký. Vì thế `key.isValid()` cần được kiểm tra trước khi truy cập ready operations, và không nên tự suy ra trạng thái chỉ từ số lượng phần tử trong một tập.

## 13. Không dùng `cancel()` để “dọn sạch sự kiện đã chọn”

Đây là lỗi thiết kế dễ xảy ra:

```java
Iterator<SelectionKey> it = selector.selectedKeys().iterator();

while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();
    key.cancel(); // Sai nếu vẫn muốn tiếp tục theo dõi channel.

    // Lần chọn sau không còn đăng ký này để xử lý I/O tiếp.
}
```

Lệnh `key.cancel()` **không phải** bước bắt buộc sau mỗi `read` hay `write`. Nó dùng khi ngừng theo dõi một channel hoặc muốn đăng ký lại theo chiến lược khác.

Ví dụ một TCP client gửi message 100 byte nhưng lần đầu server chỉ nhận 20 byte:

- Lấy key từ selected set và gọi `iterator.remove()`.
- Đọc 20 byte, cập nhật số byte còn cần.
- **Giữ key hợp lệ và quan tâm `OP_READ`** để nhận 80 byte còn lại khi có readiness.
- Không `cancel()` và đóng socket chỉ vì `read` đầu tiên chưa đủ 100 byte.

Khi kết thúc kết nối hoặc có lỗi không thể phục hồi mới hủy key, đóng channel, dọn attachment/buffer. Lưu ý việc đọc 20 byte không chứng minh message đã hoàn chỉnh: TCP không duy trì ranh giới record ứng dụng; parser phải quản lý framing.

## 14. `OP_WRITE`: lý do loại key không đủ để tránh vòng quay CPU

Một socket TCP thường xuyên có thể ghi vì phía kernel vẫn còn buffer gửi. Nếu chương trình đăng ký `OP_WRITE` ngay cả lúc **không có dữ liệu cần gửi**, selector có thể liên tục báo key writable ở các lần chọn. Kể cả đã gọi `iterator.remove()` đúng cách, vòng lặp vẫn có thể thức dậy liên tục theo một readiness **đang thật sự tồn tại**.

Cách đúng là quản lý interest:

1. Chỉ bật `OP_WRITE` khi có outbound data còn chờ.
2. Khi gửi được một phần, giữ `ByteBuffer.position()` và duy trì `OP_WRITE`.
3. Khi đã gửi hết queue, **tắt `OP_WRITE`** khỏi `interestOps`.
4. Nếu có dữ liệu mới được enqueue, bật `OP_WRITE` trở lại và đánh thức selector nếu cần.

Ví dụ tắt write interest (minh họa):

```java
int interests = key.interestOps();
key.interestOps(interests & ~SelectionKey.OP_WRITE);
```

Mã cần xác thực key hợp lệ, trạng thái gửi và đồng bộ khi nhiều thread tương tác. Đừng xóa luôn `OP_READ` nếu vẫn cần nhận request. Thao tác thay `interestOps` là thay loại sự kiện quan tâm trong tương lai, **không thay thế** việc `iterator.remove()` key đã chọn hiện tại.

## 15. `select()`, `selectNow()`, timeout và vòng lặp chính

Ba kiểu lựa chọn thường gặp:

| API | Hành vi |
| --- | --- |
| `selector.select()` | Có thể chờ cho đến khi có key sẵn sàng, wakeup, ngắt hoặc điều kiện kết thúc tương ứng |
| `selector.select(timeoutMs)` với timeout dương | Chờ tối đa một khoảng thời gian tính bằng ms nếu chưa có readiness; trả số lượng key được cập nhật theo hợp đồng |
| `selector.selectNow()` | Thực hiện thao tác chọn không chặn và trả về ngay |

**Lưu ý:** `select(0)` không mang nghĩa “poll ngay” trong Java Selector; timeout 0 có ý nghĩa chờ vô hạn. Muốn không chặn, dùng `selectNow()`.

Việc `select` trả về một số dương không có nghĩa chỉ cần xử lý đúng bấy nhiêu phần tử bằng cách lấy từ vị trí chỉ số 0: `selectedKeys()` là **Set**, không phải array được sắp thứ tự. Luôn duyệt tập thực tế.

Một mẫu event loop:

```java
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

        // Phân phối cho handler phù hợp.
    }
}
```

Đây là minh họa vì `running` và `selector` chưa được khai báo. Trong ứng dụng thực, cần xử lý shutdown, `wakeup()` khi thay trạng thái từ thread khác, timeout, hủy đăng ký và đóng tài nguyên.

### Vì sao không phụ thuộc thứ tự selected keys?

`Set<SelectionKey>` không cam kết ưu tiên accept trước read, hoặc socket A trước socket B. Handler phải thiết kế độc lập với thứ tự, và một số key được xử lý trong lượt sau nếu readiness xuất hiện sau lần chọn hiện tại. Nếu ứng dụng cần công bằng (*fairness*) giữa các kết nối, cần chính sách số byte/số tác vụ tối đa mỗi lượt, chứ không dựa vào thứ tự duyệt tự nhiên của `selectedKeys()`.

## 16. Cấu hình channel và đăng ký key đúng cách

Channel cần ở **non-blocking mode** trước khi đăng ký selector:

```java
ServerSocketChannel server = ServerSocketChannel.open();
server.configureBlocking(false);
server.register(selector, SelectionKey.OP_ACCEPT);
```

Đây là đoạn minh họa chưa hoàn chỉnh vì cần mở/bind server, khai báo selector và đóng tài nguyên.

`SocketChannel` đã được chấp nhận từ server cần được cấu hình theo mô hình event loop:

```java
SocketChannel accepted = server.accept();
if (accepted != null) {
    accepted.configureBlocking(false);
    accepted.register(
        selector, SelectionKey.OP_READ, ByteBuffer.allocate(1024));
}
```

Một channel đang có đăng ký selector hợp lệ không thể bị chuyển thẳng về blocking mode: `configureBlocking(true)` có thể ném `IllegalBlockingModeException`. Nếu định chuyển mode, phải hủy đăng ký và để selector hoàn tất việc loại key phù hợp, không đơn giản chỉ `iterator.remove()`.

**`iterator.remove()` không ảnh hưởng blocking mode**. Sau khi bạn lấy key khỏi selected set, channel vẫn ở non-blocking mode và key vẫn có thể được đăng ký.

## 17. Các lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Duyệt `selectedKeys()` nhưng không xóa phần tử | Key có thể tiếp tục nằm trong selected set qua lượt sau | Dùng `Iterator.remove()` cho từng key đã lấy |
| Gọi `selectedKeys().remove(key)` trong `for-each` | Sửa cấu trúc set ngoài iterator có thể làm hỏng vòng duyệt | Duyệt với iterator và gọi `it.remove()` |
| Gọi `key.cancel()` sau mọi sự kiện đọc | Hủy cả đăng ký vẫn cần thiết | Chỉ cancel khi thực sự dừng theo dõi |
| Nhầm `iterator.remove()` với đóng socket | Registration và channel không bị đóng | Đóng channel riêng khi kết thúc kết nối |
| `selectedKeys().clear()` trước khi xử lý | Bỏ qua sự kiện đã chọn | Remove từng key sau `next()` |
| Không kiểm tra `key.isValid()` | Có thể gặp `CancelledKeyException` khi đọc trạng thái | Kiểm tra validity và xử lý lỗi đúng phạm vi |
| Chỉ dùng `else if` cho mọi bit ready | Có thể bỏ lỡ hoạt động khác cùng sẵn sàng | Kiểm tra các bit phù hợp, recheck trạng thái sau handler |
| Không tắt `OP_WRITE` khi queue đã rỗng | Selector thường xuyên báo writable, CPU cao | Chỉ bật OP_WRITE khi còn outbound pending |
| Quay vòng liên tục khi `read()==0` | Busy spin mà không có dữ liệu | Trả quyền cho event loop và đợi readiness |
| Diễn giải `read()==0` là EOF | Đóng peer quá sớm | `read()==-1` mới là EOF |
| Không xóa key nếu handler ném lỗi | Selected set có thể còn phần tử gây khó phục hồi | Remove ngay sau next; cleanup trong catch |
| Chia sẻ iterator/selected set giữa nhiều thread không đồng bộ | Race condition, xử lý trùng sự kiện | Quy định một thread sở hữu event loop hoặc đồng bộ chặt |
| Nghĩ `selector.keys()` có thể gọi `remove` trực tiếp | Registered set không cho sửa tùy tiện | Dùng `cancel` để hủy đăng ký |
| Nghĩ `select(0)` tương đương `selectNow()` | `select(0)` có thể chờ vô hạn | Dùng `selectNow()` khi muốn poll |
| Không giữ ByteBuffer qua nhiều lần read | TCP message bị cắt mảnh, parser sai | Attachment/state per connection và framing rõ ràng |

## 18. Lưu ý thread-safety và tài nguyên

`Selector` hỗ trợ các thao tác chọn và đăng ký, nhưng **selected-key set không phải hàng đợi xử lý sự kiện đa luồng tự động an toàn**. Nếu một thread duyệt và xóa trong khi thread khác cũng chỉnh selected set, bạn phải kiểm soát đồng bộ và ownership, nếu không có thể gặp race hoặc trạng thái khó dự đoán.

Thiết kế phổ biến: **một event-loop thread sở hữu `selectedKeys()` và thao tác `select`**, còn các worker thread khác chuyển thông điệp hoặc tác vụ qua queue. Khi cần cập nhật interest hoặc yêu cầu event loop xử lý việc mới, dùng cơ chế đánh thức như `selector.wakeup()` và một hàng đợi có đồng bộ phù hợp. Không mặc định chỉ gọi `wakeup()` là đủ để đồng bộ dữ liệu trong các cấu trúc ứng dụng.

Key có thể mang một `attachment` (qua `key.attach(value)` hoặc `register(selector, ops, attachment)`) để lưu parser state, inbound/outbound buffers hoặc metadata kết nối. Khi đóng kết nối, đừng quên giải phóng tham chiếu tới các buffer/tác vụ để tránh giữ bộ nhớ lâu hơn cần thiết.

Các handler cũng không nên chặn lâu trên event-loop thread: xử lý CPU nặng, truy vấn database blocking hoặc logging blocking kéo dài sẽ làm tất cả key khác bị chậm. Một lượt `selectedKeys()` thành công về mặt API chưa bảo đảm ứng dụng đáp ứng tốt dưới tải.

## 19. Bài tập kiểm tra kiến thức

### Tình huống A: key được remove nhưng không cancel

Một `SelectionKey k` đang hợp lệ, đăng ký `OP_READ`, được selector chọn. Handler thực hiện:

```java
SelectionKey k = iterator.next();
iterator.remove();
```

Hỏi `k` còn có thể được chọn ở một lượt `select()` tương lai không?

**Có.** `iterator.remove()` chỉ xóa khỏi selected set, không hủy đăng ký. Khi channel tiếp tục có readiness phù hợp với interest và key vẫn hợp lệ, selector có thể chọn lại key.

### Tình huống B: cancel nhưng không đóng channel

Handler gọi:

```java
key.cancel();
```

Channel có chắc chắn đã bị đóng không?

**Không.** `cancel()` hủy đăng ký, không tự đóng channel. Nếu muốn kết thúc socket, cần chính sách đóng tài nguyên phù hợp. Một key đã cancel không còn hợp lệ, còn việc selector loại nó khỏi registered set được xử lý theo vòng đời lựa chọn.

### Tình huống C: key vừa readable vừa writable

Một key của `SocketChannel` có `readyOps()` chứa cả `OP_READ` và `OP_WRITE`, ứng dụng có dữ liệu chờ gửi. Nếu handler chỉ có:

```java
if (key.isReadable()) {
    readFromPeer();
} else if (key.isWritable()) {
    writeToPeer();
}
```

Điều gì có thể xảy ra?

**Nhánh write bị bỏ qua** trong lượt ấy khi read đúng, dù write cũng sẵn sàng. Đây là minh họa chưa hoàn chỉnh vì cần khai báo hai hàm xử lý. Nếu thiết kế cần xử lý cả hai, dùng hai điều kiện độc lập và đảm bảo key còn hợp lệ sau nhánh thứ nhất.

### Tình huống D: selected set rỗng nhưng registered set không rỗng

Sau xử lý:

```text
selector.selectedKeys().isEmpty() = true
selector.keys().isEmpty() = false
```

Có phải đang sai không?

**Không.** Đây là trạng thái bình thường: lượt sự kiện đã chọn đã được tiêu thụ, nhưng selector vẫn theo dõi những channel còn đăng ký.

### Tình huống E: gửi chậm

Một key writable được xử lý và gọi `socket.write(buffer)` trả về 0. Handler có nên `cancel()` key và đóng socket ngay không?

**Không mặc định.** Kết quả 0 của non-blocking write có thể chỉ là chưa có tiến độ. Giữ outbound buffer và interest `OP_WRITE` phù hợp, quay về selector để đợi lúc có thể gửi tiếp. Chỉ đóng khi có lỗi, timeout hoặc chính sách nghiệp vụ yêu cầu.

## 20. Tóm tắt

**Mẫu lặp selected keys nên ghi nhớ:**

```java
Iterator<SelectionKey> it =
        selector.selectedKeys().iterator();

while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove(); // Tiêu thụ selected event, không hủy đăng ký.

    if (!key.isValid()) {
        continue;
    }

    // Dispatch sự kiện phù hợp.
}
```

Từ mẫu này, luôn nhớ bốn ranh giới trách nhiệm:

1. **`iterator.remove()`**: xóa key khỏi **selected-key set** ở lượt hiện tại.
2. **`key.cancel()`**: yêu cầu hủy **đăng ký** khi ứng dụng không còn muốn theo dõi channel.
3. **`channel.close()`**: đóng **tài nguyên I/O** khi vòng đời kết nối kết thúc.
4. **`interestOps(...)` và ByteBuffer state**: quản lý những loại readiness cần theo dõi và dữ liệu còn chờ xử lý.

Duyệt key đúng không thay thế việc xử lý partial read/write, EOF, framing, backpressure hoặc error handling. Nhưng đó là nền tảng giúp event loop rõ ràng, tránh sự kiện cũ bị giữ lại ngoài ý muốn và quản lý nhiều kết nối một cách có kiểm soát.

**Tài liệu Java SE 17 để đối chiếu:** `java.nio.channels.Selector` (`selectedKeys()`, `keys()`, `select()`, `selectNow()`), `java.nio.channels.SelectionKey` (`cancel()`, `isValid()`, `interestOps()`, `readyOps()`), `ServerSocketChannel`, `SocketChannel`, `Pipe` và `java.nio.ByteBuffer`.
