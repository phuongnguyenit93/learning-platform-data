# Đăng ký OP_ACCEPT, OP_READ và OP_WRITE cho kênh UNIX

> **Chương:** Unix-domain socket  
> **Phạm vi:** Sử dụng `Selector` và `SelectionKey` để theo dõi sự kiện trên `ServerSocketChannel` và `SocketChannel` thuộc họ giao thức UNIX. Bài tập trung vào ba interest operation `OP_ACCEPT`, `OP_READ`, `OP_WRITE`, cách chuyển trạng thái key và xử lý dữ liệu không chặn. Unix-domain socket được hỗ trợ chính thức trong Java 16 và vẫn là API NIO hiện hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Tạo server UNIX bằng `ServerSocketChannel` và `UnixDomainSocketAddress`.
2. Đăng ký `OP_ACCEPT` để nhận kết nối mới.
3. Đăng ký `OP_READ` cho client channel đã accept.
4. Đăng ký `OP_WRITE` khi có dữ liệu đang chờ gửi.
5. Phân biệt interest operation với ready operation.
6. Xử lý partial read, partial write, EOF và trạng thái key không còn hợp lệ.
7. Thiết kế event loop dùng `Selector` mà không gây busy loop.

## 1. Kênh UNIX và Selector trong Java NIO

Java 16 bổ sung hỗ trợ Unix-domain socket trong `java.nio.channels` theo JEP 380. Ứng dụng dùng các lớp NIO quen thuộc:

- `ServerSocketChannel`: lắng nghe kết nối đến.
- `SocketChannel`: trao đổi byte với một client đã kết nối.
- `UnixDomainSocketAddress`: địa chỉ socket gắn với đường dẫn hệ thống tệp.
- `StandardProtocolFamily.UNIX`: chọn họ giao thức UNIX khi mở channel.
- `Selector`: chờ nhiều channel sẵn sàng thực hiện I/O.
- `SelectionKey`: giữ channel, selector, interest operations, ready operations và attachment.

Không có lớp riêng tên `UnixSocketChannel`. Kênh UNIX vẫn là `ServerSocketChannel` hoặc `SocketChannel`, được mở với `StandardProtocolFamily.UNIX`.

Ví dụ tạo địa chỉ:

```java
import java.net.UnixDomainSocketAddress;
import java.nio.file.Path;

Path socketPath = Path.of(
        System.getProperty("java.io.tmpdir"),
        "my-service.sock"
);
UnixDomainSocketAddress address =
        UnixDomainSocketAddress.of(socketPath);
```

Đường dẫn phải phù hợp với giới hạn và quyền truy cập của hệ điều hành. Hãy đặt socket trong thư mục runtime do ứng dụng kiểm soát, giới hạn quyền thư mục/socket phù hợp với mô hình bảo mật và tránh dùng một đường dẫn dùng chung mà tiến trình không tin cậy có thể thay thế.

Unix-domain socket dùng để giao tiếp giữa các tiến trình trên cùng hệ thống. Nó không mở cổng TCP và không dùng địa chỉ IP.

## 2. Interest operation và ready operation

Khi đăng ký channel với selector, ứng dụng khai báo những sự kiện mình muốn theo dõi bằng `interestOps`. Khi selector phát hiện sự kiện, `readyOps` cho biết thao tác nào hiện có thể tiến hành.

| Khái niệm | API | Ý nghĩa |
| --- | --- | --- |
| Interest operations | `key.interestOps()` | Các sự kiện ứng dụng muốn selector theo dõi |
| Ready operations | `key.readyOps()` | Các sự kiện selector xác định channel hiện sẵn sàng |
| Kiểm tra readiness | `key.isReadable()` | Có thể thử đọc mà không phải chờ theo chế độ blocking |
| Kiểm tra readiness | `key.isWritable()` | Có thể thử ghi một phần dữ liệu |
| Kiểm tra readiness | `key.isAcceptable()` | Server channel có thể thử accept |

Đăng ký một interest operation không có nghĩa sự kiện đã xảy ra. Tương tự, một key được chọn không bảo đảm thao tác sẽ xử lý toàn bộ dữ liệu trong một lần.

Các bit operation chính:

| Operation | Channel hợp lệ | Ý nghĩa |
| --- | --- | --- |
| `OP_ACCEPT` | `ServerSocketChannel` | Có kết nối mới đang chờ accept |
| `OP_READ` | `SocketChannel` | Có thể thử đọc byte hoặc phát hiện EOF |
| `OP_WRITE` | `SocketChannel` | Có thể thử ghi một phần byte |
| `OP_CONNECT` | `SocketChannel` | Kết nối non-blocking có thể hoàn tất |

`OP_CONNECT` thường được dùng ở phía client khi gọi `connect()` theo chế độ non-blocking. Phần chính của bài này tập trung vào server và ba operation accept/read/write.

## 3. OP_ACCEPT: đăng ký server channel

Server channel cần được mở với protocol family UNIX, chuyển sang non-blocking rồi bind vào địa chỉ UNIX. Sau đó đăng ký `OP_ACCEPT` với selector:

```java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Path;

Path socketPath = Path.of(
        System.getProperty("java.io.tmpdir"),
        "my-service.sock"
);
UnixDomainSocketAddress address =
        UnixDomainSocketAddress.of(socketPath);

try (Selector selector = Selector.open();
     ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

    server.configureBlocking(false);
    server.bind(address);
    server.register(selector, SelectionKey.OP_ACCEPT);

    // Event loop được trình bày ở phần sau.
}
```

Các bước có ý nghĩa:

1. `Selector.open()` tạo selector để theo dõi nhiều selectable channel.
2. `ServerSocketChannel.open(StandardProtocolFamily.UNIX)` mở server channel cho Unix-domain socket.
3. `configureBlocking(false)` cho phép selector điều phối I/O không chặn.
4. `bind(address)` bắt đầu lắng nghe tại đường dẫn socket.
5. `register(selector, OP_ACCEPT)` yêu cầu selector thông báo khi có kết nối mới.

Server channel chỉ hỗ trợ operation accept. Không đăng ký `OP_READ` hoặc `OP_WRITE` trên server channel.

### Kiểm tra operation hợp lệ

`channel.validOps()` trả về bitmask các operation mà channel hỗ trợ. Đây là cách kiểm tra loại channel trước khi đăng ký:

```java
int supported = server.validOps();
boolean canAccept =
        (supported & SelectionKey.OP_ACCEPT) != 0;
```

Nếu đăng ký một operation không nằm trong `validOps()`, việc đăng ký có thể thất bại với `IllegalArgumentException`. Vì vậy, không dùng cùng một bitmask tùy tiện cho server và client channel.

## 4. Xử lý OP_ACCEPT và đăng ký OP_READ

Khi key của server trở nên acceptable, gọi `accept()` để lấy client channel. Với server non-blocking, `accept()` có thể trả về `null` nếu không còn kết nối chờ tại thời điểm gọi.

Nên accept trong vòng lặp cho đến khi không còn kết nối:

```java
import java.io.IOException;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;

static void acceptConnections(
        ServerSocketChannel server,
        Selector selector
) throws IOException {
    SocketChannel client;
    while ((client = server.accept()) != null) {
        client.configureBlocking(false);
        client.register(
                selector,
                SelectionKey.OP_READ,
                new ConnectionState()
        );
    }
}
```

`ConnectionState` là trạng thái riêng của mỗi client, thường chứa buffer nhận, hàng đợi buffer gửi và thông tin giao thức:

```java
import java.nio.ByteBuffer;
import java.util.ArrayDeque;
import java.util.Deque;

final class ConnectionState {
    final ByteBuffer inbound = ByteBuffer.allocate(8 * 1024);
    final Deque<ByteBuffer> outbound = new ArrayDeque<>();
    boolean inputClosed;
    boolean readPaused;
}
```

Trong ví dụ, client được đăng ký với `OP_READ` ngay sau khi accept. Attachment giúp event loop lấy đúng trạng thái của kết nối khi xử lý key.

### Vì sao accept có vòng lặp?

Một lần selector báo acceptable có thể tương ứng với nhiều kết nối đã chờ. Accept một lần rồi quay lại `select()` có thể làm tăng số lần đánh thức selector không cần thiết. Vòng lặp dừng khi `accept()` trả về `null`.

Không gọi `accept()` trên channel đang blocking trong event loop. Điều đó có thể chặn toàn bộ selector thread.

## 5. OP_READ: nhận dữ liệu từ client

`OP_READ` cho biết có thể thử đọc. Nó không bảo đảm đã có đủ một thông điệp hoàn chỉnh.

Với `SocketChannel` non-blocking:

- `read(buffer) > 0`: đã đọc được số byte trả về.
- `read(buffer) == 0`: hiện chưa đọc được byte nào.
- `read(buffer) == -1`: peer đã đóng đầu ra; đây là EOF.

Ví dụ đọc dữ liệu:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.SocketChannel;

static void readFromClient(SelectionKey key) throws IOException {
    SocketChannel client = (SocketChannel) key.channel();
    ConnectionState state = (ConnectionState) key.attachment();

    int count = client.read(state.inbound);

    if (count == -1) {
        // Peer đã đóng chiều gửi; vẫn có thể còn phản hồi cần gửi.
        state.inputClosed = true;
        if (state.outbound.isEmpty()) {
            closeConnection(key);
        } else {
            updateInterestOps(key, state);
        }
        return;
    }

    if (count == 0) {
        return;
    }

    state.inbound.flip();

    ByteBuffer response = ByteBuffer.allocate(state.inbound.remaining());
    response.put(state.inbound);
    response.flip();
    state.outbound.add(response);

    state.inbound.clear();
    updateInterestOps(key, state);
}
```

Đây là ví dụ echo theo từng khối byte vừa nhận. Trong giao thức thực tế, cần thêm bộ phân tích frame hoặc delimiter vì stream socket không giữ ranh giới message. Một lần `read()` có thể nhận một phần message hoặc nhiều message cùng lúc.

### Position và limit của buffer khi đọc

Sau `read()`, position của buffer là vị trí ngay sau số byte đã nhận. Gọi `flip()` để chuyển vùng vừa nhận thành vùng có thể đọc:

```java
int count = client.read(state.inbound);

if (count > 0) {
    state.inbound.flip();
    // Xử lý byte trong vùng [position, limit).
    state.inbound.compact();
}
```

`compact()` phù hợp khi parser chưa xử lý hết dữ liệu và cần giữ byte còn lại để ghép với lần đọc tiếp theo. `clear()` chỉ phù hợp khi ứng dụng đã xử lý hoặc sao chép toàn bộ byte cần giữ.

Nếu buffer đầy mà chưa có frame hoàn chỉnh, parser phải có chiến lược tăng dung lượng, giới hạn kích thước frame hoặc từ chối input quá lớn. Không tiếp tục đọc vào buffer đã hết chỗ.

## 6. OP_WRITE: gửi dữ liệu đang chờ

`OP_WRITE` báo rằng channel có thể ghi ít nhất một phần dữ liệu. Nó không bảo đảm toàn bộ buffer sẽ được ghi trong một lần.

Một `SocketChannel.write(buffer)` có thể:

- Ghi hết buffer.
- Ghi một phần và để `buffer.hasRemaining()` là `true`.
- Trả về 0 khi hiện không thể ghi thêm.

Do đó, ứng dụng cần giữ buffer chưa gửi hết trong hàng đợi và tiếp tục ở lần writable tiếp theo.

Ví dụ ghi từ hàng đợi:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.SocketChannel;

static void writeToClient(SelectionKey key) throws IOException {
    SocketChannel client = (SocketChannel) key.channel();
    ConnectionState state = (ConnectionState) key.attachment();

    while (!state.outbound.isEmpty()) {
        ByteBuffer current = state.outbound.peek();
        client.write(current);

        if (current.hasRemaining()) {
            break;
        }

        state.outbound.remove();
    }

    if (state.inputClosed && state.outbound.isEmpty()) {
        closeConnection(key);
        return;
    }

    updateInterestOps(key, state);
}
```

Khi `write()` trả về 0 hoặc chỉ ghi một phần, buffer vẫn còn dữ liệu và vòng lặp dừng. Selector sẽ thông báo writable ở một lần xử lý sau nếu key vẫn đăng ký `OP_WRITE`.

## 7. Chỉ bật OP_WRITE khi thực sự có dữ liệu

Socket channel thường có thể ghi được trong phần lớn thời gian. Nếu đăng ký `OP_WRITE` liên tục ngay cả khi hàng đợi rỗng, selector có thể trả về tức thì lặp đi lặp lại và tiêu tốn CPU.

Vì vậy:

- Giữ `OP_READ` khi ứng dụng muốn nhận dữ liệu.
- Thêm `OP_WRITE` khi hàng đợi outbound có dữ liệu.
- Bỏ `OP_WRITE` ngay khi hàng đợi đã rỗng.

Ví dụ cập nhật interest operations:

```java
import java.nio.channels.SelectionKey;

static void updateInterestOps(
        SelectionKey key,
        ConnectionState state
) {
    if (!key.isValid()) {
        return;
    }

    int ops = key.interestOps();

    if (state.inputClosed || state.readPaused) {
        ops &= ~SelectionKey.OP_READ;
    } else {
        ops |= SelectionKey.OP_READ;
    }

    if (state.outbound.isEmpty()) {
        ops &= ~SelectionKey.OP_WRITE;
    } else {
        ops |= SelectionKey.OP_WRITE;
    }

    key.interestOps(ops);
}
```

Phương thức trên giả định ứng dụng luôn muốn đọc từ client. Nếu cần backpressure, có thể tạm bỏ `OP_READ` khi hàng đợi gửi vượt ngưỡng, sau đó đăng ký lại khi hàng đợi giảm.

### Vì sao không đăng ký cả READ và WRITE từ đầu?

`OP_READ | OP_WRITE` là bitmask hợp lệ với `SocketChannel`, nhưng `OP_WRITE` thường luôn sẵn sàng. Nếu không có dữ liệu cần gửi, selector vẫn có thể đánh thức liên tục. Chỉ đăng ký write khi có công việc thực tế giúp event loop hoạt động hiệu quả hơn.

## 8. Event loop xử lý ACCEPT, READ và WRITE

Một selector thread thường chạy vòng lặp:

1. Gọi `select()` để chờ sự kiện.
2. Duyệt các key đã được chọn.
3. Xóa từng key khỏi `selectedKeys()` sau khi lấy ra.
4. Kiểm tra key còn hợp lệ không.
5. Xử lý accept, read hoặc write theo readiness.

Ví dụ khung event loop:

```java
import java.io.IOException;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.util.Iterator;

static void runEventLoop(Selector selector) throws IOException {
    while (!Thread.currentThread().isInterrupted()) {
        selector.select();

        Iterator<SelectionKey> iterator =
                selector.selectedKeys().iterator();

        while (iterator.hasNext()) {
            SelectionKey key = iterator.next();
            iterator.remove();

            if (!key.isValid()) {
                continue;
            }

            try {
                if (key.isAcceptable()) {
                    acceptConnections(
                            (java.nio.channels.ServerSocketChannel) key.channel(),
                            selector
                    );
                }

                if (key.isValid() && key.isReadable()) {
                    readFromClient(key);
                }

                if (key.isValid() && key.isWritable()) {
                    writeToClient(key);
                }
            } catch (IOException error) {
                if (key.channel() instanceof
                        java.nio.channels.ServerSocketChannel) {
                    throw error;
                }
                closeConnection(key);
            }
        }
    }
}
```

Các hàm `acceptConnections`, `readFromClient`, `writeToClient` và `closeConnection` là những hàm ở các phần trước. Trong server hoàn chỉnh, cần xử lý lỗi của server channel riêng với lỗi của từng client để một client hỏng không làm dừng listener.

### Luôn xóa key đã xử lý khỏi selectedKeys

`selectedKeys()` là tập key đã sẵn sàng. Selector không tự loại key ra khỏi tập sau khi ứng dụng xử lý. Nếu không gọi `iterator.remove()`, key cũ có thể tiếp tục xuất hiện và làm event loop xử lý lặp.

### Kiểm tra key còn hợp lệ sau mỗi thao tác

Một thao tác read có thể phát hiện EOF và đóng channel. Sau đó key có thể không còn hợp lệ. Trước khi xử lý write tiếp theo, kiểm tra `key.isValid()`.

## 9. Đóng kết nối an toàn

Khi client gửi EOF hoặc phát sinh lỗi I/O, hủy key và đóng channel:

```java
import java.io.IOException;
import java.nio.channels.SelectionKey;

static void closeConnection(SelectionKey key) {
    key.cancel();
    try {
        key.channel().close();
    } catch (IOException ignored) {
        // Ghi log nếu ứng dụng cần theo dõi lỗi đóng tài nguyên.
    }
}
```

Không giữ key đã hủy trong cấu trúc quản lý connection. Nếu attachment giữ buffer lớn hoặc trạng thái giao thức, giải phóng tham chiếu khi kết nối đóng.

Đóng selector và server channel khi dừng service. Với đường dẫn socket, quản lý vòng đời file socket trong thư mục runtime có kiểm soát; chỉ dọn đường dẫn cũ khi chắc chắn không có server đang sử dụng nó.

## 10. Client non-blocking và OP_CONNECT

Phía client có thể dùng `SocketChannel` với `StandardProtocolFamily.UNIX`. Nếu dùng non-blocking connect, cần theo dõi `OP_CONNECT` trước khi đăng ký read/write:

```java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.SocketChannel;

SocketChannel client =
        SocketChannel.open(StandardProtocolFamily.UNIX);
client.configureBlocking(false);

boolean connected = client.connect(address);

if (connected) {
    client.register(selector, SelectionKey.OP_READ);
} else {
    client.register(selector, SelectionKey.OP_CONNECT);
}
```

Khi key connectable (`key.isConnectable()`), gọi `finishConnect()`. Nếu kết nối hoàn tất, thay interest operations sang `OP_READ`; chỉ bật `OP_WRITE` khi có dữ liệu outbound:

```java
if (key.isConnectable()) {
    SocketChannel client = (SocketChannel) key.channel();

    if (client.finishConnect()) {
        key.interestOps(SelectionKey.OP_READ);
    }
}
```

Nếu `connect()` trả về `true` ngay, kết nối đã hoàn tất và không cần chờ `OP_CONNECT`.

## 11. Backpressure và giới hạn hàng đợi

Một client chậm có thể khiến hàng đợi outbound tăng liên tục. Nếu không giới hạn, ứng dụng có thể tiêu thụ quá nhiều bộ nhớ.

Các biện pháp thường dùng:

- Giới hạn tổng số byte đang chờ gửi trên mỗi connection.
- Tạm bỏ `OP_READ` khi outbound queue vượt ngưỡng.
- Đăng ký lại `OP_READ` khi queue giảm dưới ngưỡng thấp hơn.
- Giới hạn kích thước frame và buffer nhận.
- Đóng kết nối nếu peer vi phạm giới hạn giao thức.

Ví dụ ý tưởng bật/tắt đọc theo ngưỡng:

```java
static final int MAX_PENDING_BYTES = 1024 * 1024;
static final int RESUME_READ_BYTES = 256 * 1024;

static void updateBackpressure(
        SelectionKey key,
        ConnectionState state,
        int pendingBytes
) {
    if (!key.isValid()) {
        return;
    }

    if (pendingBytes >= MAX_PENDING_BYTES) {
        state.readPaused = true;
    } else if (pendingBytes <= RESUME_READ_BYTES) {
        state.readPaused = false;
    }

    updateInterestOps(key, state);
}
```

Trong triển khai thực tế, cần tính chính xác số byte trong queue và tránh để một kết nối gây ảnh hưởng tài nguyên của các kết nối khác.

## 12. Cập nhật interestOps từ thread khác

Thông thường, selector thread nên là nơi sở hữu và thay đổi `interestOps`. Nếu thread khác cần thêm dữ liệu vào outbound queue, hãy gửi yêu cầu qua concurrent queue rồi gọi `selector.wakeup()` để đánh thức event loop. Selector thread lấy yêu cầu và cập nhật key.

Mô hình:

```java
// Pseudocode: producer thread
pendingTasks.add(() -> {
    state.outbound.add(responseBuffer);
    updateInterestOps(key, state);
});
selector.wakeup();
```

Sau khi `select()` trả về, selector thread xử lý `pendingTasks` trước hoặc sau khi duyệt selected keys theo thiết kế. Tránh sửa queue hoặc interest operations đồng thời từ nhiều thread mà không có đồng bộ rõ ràng.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Selector liên tục trả về ngay | Đăng ký `OP_WRITE` khi outbound queue rỗng | Bỏ `OP_WRITE` khi không có dữ liệu gửi |
| Kết nối đến nhưng server không accept | Quên đăng ký `OP_ACCEPT` hoặc server đang blocking | Dùng non-blocking server channel và đăng ký `OP_ACCEPT` |
| Client được accept nhưng không đọc được | Chưa đăng ký `OP_READ` trên client channel | Đăng ký `OP_READ` sau khi accept |
| Mất phần dữ liệu cuối | Giả định một lần `read()` nhận trọn message | Dùng framing và buffer giữ dữ liệu chưa xử lý |
| Dữ liệu gửi bị cắt | Giả định một lần `write()` gửi hết buffer | Giữ buffer trong queue khi `hasRemaining()` |
| Event loop lặp cùng key | Không remove key khỏi `selectedKeys()` | Gọi `iterator.remove()` sau khi lấy key |
| `CancelledKeyException` | Thay đổi interestOps trên key đã bị hủy | Kiểm tra `isValid()` và quản lý lifecycle connection |
| `IllegalArgumentException` khi register | Dùng operation không thuộc `channel.validOps()` | Đăng ký OP_ACCEPT cho server; READ/WRITE cho socket |
| CPU tăng cao khi không có traffic | Vòng lặp chờ bận hoặc luôn bật OP_WRITE | Dùng `select()` và chỉ bật write khi có dữ liệu |
| Bộ nhớ tăng theo client chậm | Outbound queue không có giới hạn | Áp dụng backpressure và giới hạn byte chờ gửi |

## 14. Checklist triển khai

| Hạng mục | Câu hỏi xác nhận |
| --- | --- |
| Protocol family | Channel được mở bằng `StandardProtocolFamily.UNIX` chưa? |
| Address | Địa chỉ dùng `UnixDomainSocketAddress` và path có quyền phù hợp chưa? |
| Blocking mode | Server và client channel có được cấu hình non-blocking trước khi register không? |
| Accept | Server key có `OP_ACCEPT` không? |
| Read | Client key có `OP_READ` khi ứng dụng muốn nhận dữ liệu không? |
| Write | Chỉ bật `OP_WRITE` khi outbound queue còn byte không? |
| Valid operations | Interest ops có nằm trong `channel.validOps()` không? |
| Partial I/O | Có xử lý read/write trả về 0, EOF và partial write không? |
| Selected keys | Có remove key khỏi selected set sau khi xử lý không? |
| Lifecycle | Có đóng channel và hủy key khi connection kết thúc không? |
| Backpressure | Có giới hạn buffer và outbound queue không? |
| Threading | Selector thread có quản lý việc cập nhật key một cách nhất quán không? |
| Portability | Đã kiểm tra hỗ trợ UNIX domain socket trên hệ điều hành/JDK mục tiêu chưa? |

## 15. Bài tập thực hành

### Bài 1 — Đăng ký OP_ACCEPT

Tạo `ServerSocketChannel` với `StandardProtocolFamily.UNIX`, bind vào một `UnixDomainSocketAddress` và đăng ký `OP_ACCEPT`. Kết nối từ một client rồi xác nhận selector báo acceptable.

### Bài 2 — Đăng ký OP_READ

Sau khi accept, chuyển client channel sang non-blocking và đăng ký `OP_READ`. Gửi nhiều khối dữ liệu từ client, quan sát kết quả read và xác định EOF.

### Bài 3 — Đăng ký OP_WRITE có điều kiện

Tạo outbound queue. Chỉ thêm `OP_WRITE` khi queue có dữ liệu; sau khi gửi hết, loại operation này khỏi interest set. Quan sát mức hoạt động của event loop khi queue rỗng.

### Bài 4 — Xử lý partial write

Dùng buffer lớn hoặc client đọc chậm để quan sát trường hợp `write()` chỉ gửi một phần. Giữ buffer còn lại trong queue và tiếp tục khi channel writable.

### Bài 5 — Xây dựng echo server

Kết hợp accept/read/write thành echo server UNIX. Dùng attachment cho trạng thái từng client, xử lý EOF và đóng connection đúng cách.

### Bài 6 — Thêm backpressure

Giới hạn outbound queue. Khi vượt ngưỡng, tạm bỏ `OP_READ`; khi queue giảm, đăng ký lại. Kiểm tra một client chậm không làm tăng bộ nhớ vô hạn.

## Tài liệu chính thức

- [Java SE 16 — `SelectionKey`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/SelectionKey.html) — operation `OP_ACCEPT`, `OP_READ`, `OP_WRITE`, interestOps và readyOps.
- [Java SE 16 — `Selector`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/Selector.html) — đăng ký channel và xử lý selected keys.
- [Java SE 16 — `ServerSocketChannel`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/ServerSocketChannel.html) — mở server channel theo protocol family và accept non-blocking.
- [Java SE 16 — `SocketChannel`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/SocketChannel.html) — kết nối, đọc/ghi và non-blocking operations.
- [Java SE 16 — `UnixDomainSocketAddress`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/net/UnixDomainSocketAddress.html) — địa chỉ Unix-domain socket.
- [JEP 380 — Unix-Domain Socket Channels](https://openjdk.org/jeps/380) — hỗ trợ Unix-domain socket trong Java 16.
- [Java SE 25 — `SelectionKey`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/SelectionKey.html) — xác nhận API selector operation tiếp tục được hỗ trợ trong JDK hiện đại.

**Nguyên tắc áp dụng:** Đăng ký `OP_ACCEPT` cho server channel, `OP_READ` cho client cần nhận dữ liệu và chỉ bật `OP_WRITE` khi có byte đang chờ gửi. Luôn xử lý partial I/O, EOF, selected-key lifecycle và giới hạn hàng đợi để event loop UNIX hoạt động ổn định.
