# Quản lý channel và selector bằng try-with-resources

Unix-domain socket trong Java sử dụng các channel của NIO. Những đối tượng này giữ tài nguyên hệ điều hành như socket endpoint, file descriptor và selector resource, vì vậy cần xác định rõ ai sở hữu và đóng chúng. **try-with-resources** là cách phù hợp để bảo đảm channel và selector được đóng khi xử lý hoàn tất hoặc khi có exception.

Khi dùng Selector, cần phân biệt ba trách nhiệm: Selector quản lý việc chờ readiness và các SelectionKey; ServerSocketChannel/SocketChannel quản lý kết nối; ứng dụng quản lý vòng đời các channel đã mở. Đóng Selector không tự động đóng các channel đã đăng ký. Đóng một channel sẽ hủy đăng ký tương ứng, còn SelectionKey.cancel() chỉ yêu cầu hủy đăng ký chứ không đóng channel.

Bài học tập trung vào API Unix-domain socket từ Java 16 vẫn dùng được trên JDK hiện đại: mở channel với StandardProtocolFamily.UNIX, cấu hình non-blocking, đăng ký Selector, xử lý selected keys và đóng tài nguyên đúng thứ tự.

## 1. Các đối tượng cần quản lý vòng đời

Một server Unix-domain socket thường sử dụng:

| Đối tượng | Vai trò | Cần đóng? |
|---|---|---|
| ServerSocketChannel | Bind pathname và accept kết nối | Có, để đóng listening socket |
| SocketChannel | Giao tiếp với một client | Có, mỗi client channel cần được đóng |
| Selector | Chờ channel sẵn sàng đọc, ghi hoặc accept | Có, để giải phóng tài nguyên selector |
| SelectionKey | Đại diện đăng ký channel với Selector | Không phải AutoCloseable; cancel khi cần hủy đăng ký |
| UnixDomainSocketAddress | Giá trị mô tả pathname | Không giữ tài nguyên cần đóng |
| Socket file trên filesystem | Tên endpoint do hệ điều hành tạo khi bind | Thường phải xóa sau khi server đã đóng, theo chính sách ownership |

Channel và Selector triển khai Closeable/AutoCloseable nên có thể quản lý bằng try-with-resources. SelectionKey không phải resource độc lập; vòng đời của key gắn với channel và selector đã đăng ký nó.

## 2. Quy tắc đóng tài nguyên của try-with-resources

Các resource được khởi tạo từ trái sang phải và đóng theo thứ tự ngược lại. Ví dụ:

~~~java
try (Selector selector = Selector.open();
     ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

    // Cấu hình, bind, đăng ký và xử lý sự kiện.
}
~~~

Khi rời khối try:

1. ServerSocketChannel được đóng trước.
2. Selector được đóng sau.

Thứ tự này phù hợp khi channel được đăng ký với selector: channel ngừng hoạt động trước, sau đó selector giải phóng các tài nguyên chờ sự kiện và đăng ký còn lại.

Nếu resource thứ hai hoặc các resource sau đó khởi tạo thất bại, những resource đã mở trước đó vẫn được đóng. Nếu thân try ném exception và close cũng ném exception, exception khi close được gắn dưới dạng suppressed exception theo quy tắc try-with-resources.

## 3. Server blocking đơn giản với try-with-resources

Nếu server chỉ cần xử lý một client tại một thời điểm, có thể dùng blocking channel và không cần Selector:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class BlockingUnixServer {
    public static void main(String[] args) throws IOException {
        Path socketPath = Path.of("/tmp/demo-service.sock");
        UnixDomainSocketAddress address =
                UnixDomainSocketAddress.of(socketPath);

        boolean bound = false;
        try (ServerSocketChannel server =
                     ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
            server.bind(address);
            bound = true;

            try (SocketChannel client = server.accept()) {
                ByteBuffer request = ByteBuffer.allocate(1024);
                int count = client.read(request);

                if (count > 0) {
                    request.flip();
                    while (request.hasRemaining()) {
                        client.write(request);
                    }
                }
            }
        } finally {
            // Chỉ xóa path nếu instance này bind thành công.
            if (bound) {
                java.nio.file.Files.deleteIfExists(socketPath);
            }
        }
    }
}
~~~

Ở ví dụ này:

- ServerSocketChannel được mở với protocol family UNIX.
- server.bind(address) tạo endpoint tại socket path.
- server.accept() chờ một client kết nối.
- SocketChannel của client được đóng khi kết thúc khối try bên trong.
- ServerSocketChannel được đóng khi kết thúc khối try bên ngoài.
- Socket path được xóa trong finally sau khi server đã đóng.

Đây là ví dụ blocking tối giản. Nó chỉ đọc một lần và phản hồi dữ liệu nhận được trong lần đọc đó; ứng dụng thực tế cần xử lý partial read/write, nhiều request, framing và timeout theo giao thức.

Không xóa một socket path tồn tại từ trước một cách mù quáng trước khi bind. Path đó có thể thuộc một instance server khác. Nếu bind thất bại, hãy kiểm tra ownership và trạng thái process trước khi dọn socket cũ.

## 4. Client blocking cũng cần đóng SocketChannel

Client kết nối tới server bằng UnixDomainSocketAddress:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class BlockingUnixClient {
    public static void main(String[] args) throws IOException {
        var address = UnixDomainSocketAddress.of(
                Path.of("/tmp/demo-service.sock"));

        try (SocketChannel client =
                     SocketChannel.open(StandardProtocolFamily.UNIX)) {
            client.connect(address);

            ByteBuffer request = StandardCharsets.UTF_8
                    .encode("PING");
            while (request.hasRemaining()) {
                client.write(request);
            }

            ByteBuffer response = ByteBuffer.allocate(4);
            while (response.hasRemaining()) {
                int count = client.read(response);
                if (count < 0) {
                    throw new IOException("Server closed before full response");
                }
            }

            response.flip();
            System.out.println(StandardCharsets.UTF_8.decode(response));
        }
    }
}
~~~

SocketChannel được đóng kể cả khi connect, write hoặc read phát sinh IOException. Không nên giữ channel mở lâu hơn nhu cầu giao tiếp nếu không có một component quản lý lifecycle rõ ràng.

## 5. Khi nào cần Selector?

Selector cho phép một thread theo dõi readiness của nhiều channel non-blocking. Thay vì một thread bị chặn trong read() cho từng client, server có thể chờ nhiều channel và xử lý channel nào sẵn sàng.

Các bước cơ bản:

1. Mở Selector.
2. Mở ServerSocketChannel với StandardProtocolFamily.UNIX.
3. Chuyển server channel sang non-blocking.
4. Bind socket path.
5. Đăng ký server với OP_ACCEPT.
6. Gọi select() để chờ sự kiện.
7. Duyệt selectedKeys(), xử lý key và xóa key khỏi selected set.
8. Với client mới, cấu hình non-blocking rồi đăng ký OP_READ.
9. Đóng từng client khi hoàn tất hoặc khi lỗi.
10. Đóng toàn bộ tài nguyên khi server dừng.

Channel phải ở non-blocking mode trước khi đăng ký với Selector. SocketChannel được trả về từ ServerSocketChannel.accept() ban đầu ở blocking mode, vì vậy cần gọi configureBlocking(false) trước register().

## 6. Đăng ký ServerSocketChannel với Selector

Ví dụ khởi tạo:

~~~java
Selector selector = Selector.open();
ServerSocketChannel server =
        ServerSocketChannel.open(StandardProtocolFamily.UNIX);

server.configureBlocking(false);
server.bind(address);
server.register(selector, SelectionKey.OP_ACCEPT);
~~~

OP_ACCEPT báo rằng server channel có thể accept kết nối mà không phải chờ. Một server channel đã đăng ký với Selector phải ở non-blocking mode.

Có thể gộp lifecycle vào try-with-resources:

~~~java
try (Selector selector = Selector.open();
     ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

    server.configureBlocking(false);
    server.bind(address);
    server.register(selector, SelectionKey.OP_ACCEPT);

    // Selector loop.
}
~~~

Khi khối try kết thúc, server channel và selector đều được đóng ngay cả khi vòng lặp ném exception.

## 7. Selector loop và selectedKeys

Một Selector giữ tập SelectionKey đã sẵn sàng trong selectedKeys(). Tập này không tự xóa các key sau khi ứng dụng xử lý; ứng dụng cần gọi iterator.remove() để tránh xử lý lại key cũ ở vòng sau.

Mẫu vòng lặp:

~~~java
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
            // Accept một hoặc nhiều client.
        } else if (key.isReadable()) {
            // Đọc dữ liệu client.
        } else if (key.isWritable()) {
            // Ghi dữ liệu đang chờ.
        }
    }
}
~~~

Sau select(), nên kiểm tra key.isValid() trước khi truy cập ready operation. Key có thể đã bị cancel hoặc channel đã đóng. Nếu selected key không bị remove, nó vẫn nằm trong selected set và có thể khiến vòng lặp xử lý lặp lại.

select() có thể trả về vì có key sẵn sàng, vì selector.wakeup() được gọi hoặc vì thread bị interrupt. Không giả định mỗi lần select() trả về đều có selected key; vòng lặp vẫn cần xử lý trường hợp selected set rỗng.

## 8. Quản lý accepted SocketChannel

Selector không tự sở hữu vòng đời các channel được đăng ký. Đóng Selector làm các key đăng ký bị invalid và channel được deregister, nhưng các SocketChannel không tự động đóng chỉ vì Selector đóng.

Vì thế, server cần quản lý các client channel đã accept. Nếu client tồn tại qua nhiều vòng select(), không thể đặt mỗi channel trong một try-with-resources cục bộ rồi đóng ngay sau khi đăng ký. Cần một registry hoặc connection object sở hữu channel đến khi client hoàn tất.

Ví dụ registry đơn giản:

~~~java
import java.io.IOException;
import java.nio.channels.SocketChannel;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class ClientChannels implements AutoCloseable {
    private final Set<SocketChannel> openChannels = new HashSet<>();

    void add(SocketChannel channel) {
        openChannels.add(channel);
    }

    void close(SocketChannel channel) throws IOException {
        openChannels.remove(channel);
        channel.close();
    }

    @Override
    public void close() throws IOException {
        IOException failure = null;

        for (SocketChannel channel : List.copyOf(openChannels)) {
            try {
                close(channel);
            } catch (IOException e) {
                if (failure == null) {
                    failure = e;
                } else {
                    failure.addSuppressed(e);
                }
            }
        }

        if (failure != null) {
            throw failure;
        }
    }
}
~~~

Registry này được dùng bởi một selector thread nên HashSet không cần hỗ trợ truy cập đồng thời. Nếu nhiều thread có thể thêm hoặc xóa channel, phải thiết kế đồng bộ hóa hoặc chuyển quyền sở hữu lifecycle về một event loop duy nhất.

ClientChannels triển khai AutoCloseable, do đó có thể đưa vào try-with-resources. Khi server dừng, tất cả client channel còn mở được đóng trước server channel và Selector nếu chúng được khai báo theo thứ tự phù hợp.

## 9. Ví dụ selector server echo với lifecycle rõ ràng

Ví dụ sau minh họa một server echo non-blocking. Mỗi client có một ByteBuffer làm attachment của SelectionKey. Server đọc dữ liệu vào buffer, chuyển sang OP_WRITE để gửi lại, rồi quay về OP_READ sau khi ghi hết.

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.Iterator;

public class SelectorUnixEchoServer {
    public static void serve(
            Path socketPath,
            AtomicBoolean running,
            AtomicReference<Selector> selectorReference)
            throws IOException {
        UnixDomainSocketAddress address =
                UnixDomainSocketAddress.of(socketPath);

        boolean bound = false;
        try (Selector selector = Selector.open();
             ServerSocketChannel server =
                     ServerSocketChannel.open(StandardProtocolFamily.UNIX);
             ClientChannels clients = new ClientChannels()) {

            selectorReference.set(selector);
            try {
                server.configureBlocking(false);
                server.bind(address);
                bound = true;
                server.register(selector, SelectionKey.OP_ACCEPT);

                while (running.get()) {
                    selector.select();
                    if (!running.get()) {
                        break;
                    }

                    Iterator<SelectionKey> iterator =
                            selector.selectedKeys().iterator();

                    while (iterator.hasNext()) {
                        SelectionKey key = iterator.next();
                        iterator.remove();

                        if (!key.isValid()) {
                            continue;
                        }

                        if (key.isAcceptable()) {
                            SocketChannel client;
                            while ((client = server.accept()) != null) {
                                clients.add(client);
                                client.configureBlocking(false);
                                client.register(
                                        selector,
                                        SelectionKey.OP_READ,
                                        ByteBuffer.allocate(8192));
                            }
                            continue;
                        }

                        SocketChannel client = (SocketChannel) key.channel();
                        ByteBuffer data = (ByteBuffer) key.attachment();

                        if (key.isReadable()) {
                            int count = client.read(data);
                            if (count < 0) {
                                key.cancel();
                                clients.close(client);
                                continue;
                            }
                            if (count > 0) {
                                data.flip();
                                key.interestOps(SelectionKey.OP_WRITE);
                            }
                        } else if (key.isWritable()) {
                            client.write(data);
                            if (!data.hasRemaining()) {
                                data.clear();
                                key.interestOps(SelectionKey.OP_READ);
                            }
                        }
                    }
                }
            } finally {
                selectorReference.compareAndSet(selector, null);
            }
        } finally {
            // Resource server đã đóng trước khi xóa path.
            if (bound) {
                java.nio.file.Files.deleteIfExists(socketPath);
            }
        }
    }
}
~~~

Đây là ví dụ vòng lặp phục vụ mục đích học lifecycle và readiness. Trong ứng dụng production, nên bổ sung logging, giới hạn số client, giao thức framing, xử lý lỗi riêng cho từng client và chính sách socket path. AtomicBoolean cho phép thread điều khiển yêu cầu dừng; AtomicReference cung cấp Selector đang chờ để thread đó gọi wakeup().

Ví dụ yêu cầu dừng từ thread điều khiển:

~~~java
running.set(false);
Selector current = selectorReference.get();
if (current != null) {
    current.wakeup();
}
~~~

Sau khi select() được đánh thức, event loop kiểm tra running và thoát. Thread đang sở hữu try-with-resources sẽ đóng registry client, server channel và selector.

Khi accept client:

- Channel được thêm vào registry trước khi cấu hình và đăng ký.
- Nếu configureBlocking hoặc register ném exception, try-with-resources cuối cùng vẫn đóng client thông qua registry.
- Client channel được giữ mở qua nhiều lần select.
- Khi client đóng kết nối bình thường, read() trả -1; server cancel key và đóng channel.
- Khi server dừng, registry đóng mọi client còn lại.

Ví dụ đang fail-fast khi IOException xảy ra trong selector loop: lỗi truyền ra ngoài, các resource được đóng và server dừng. Một server thực tế có thể cô lập lỗi của từng client để các client khác tiếp tục hoạt động, nhưng phải giữ quy tắc close và cleanup tương tự.

## 10. Thứ tự khai báo resource khi có nhiều client

Trong selector server, có ít nhất ba nhóm resource cần đóng:

1. Các SocketChannel của client đã accept.
2. ServerSocketChannel đang listen.
3. Selector đang theo dõi các channel.

Có thể đưa một registry client vào try-with-resources:

~~~java
try (Selector selector = Selector.open();
     ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX);
     ClientChannels clients = new ClientChannels()) {

    // Event loop sử dụng cả ba resource.
}
~~~

Thứ tự đóng là:

1. ClientChannels.close() đóng các client còn mở.
2. ServerSocketChannel.close() dừng listener.
3. Selector.close() hủy các đăng ký còn lại và giải phóng selector resource.

Đây là thứ tự dễ hiểu vì resource cấp cao được tạo sau và đóng trước. Selector không thay thế ClientChannels; registry vẫn cần đóng channel thực tế.

Nếu khai báo thêm một resource quản lý socket path trước Selector, nó sẽ được đóng cuối cùng. Có thể dùng cách này để xóa pathname sau khi server channel đã đóng, như phần tiếp theo.

## 11. Hủy SelectionKey không đồng nghĩa đóng channel

SelectionKey.cancel() yêu cầu selector hủy đăng ký key. Việc deregister thường được hoàn tất trong lần selection operation tiếp theo. Nó không gọi close() trên channel.

Ví dụ:

~~~java
key.cancel();
~~~

Sau khi cancel:

- key không còn hợp lệ cho thao tác readiness.
- key có thể vẫn còn xuất hiện tạm thời trong selectedKeys hoặc tập key cho đến khi selector xử lý cancellation.
- channel vẫn có thể đang mở.
- ứng dụng vẫn phải đóng channel nếu không dùng nó nữa.

Khi client kết thúc, có thể làm rõ cả hai hành động:

~~~java
key.cancel();
clients.close(client);
~~~

Đóng SocketChannel cũng tự hủy các key mà channel đã đăng ký. Việc gọi cancel trước khi close giúp thể hiện ý định dừng theo dõi; close mới là hành động giải phóng socket channel.

Không giữ key đã cancel rồi tiếp tục gọi interestOps hoặc truy cập readiness như thể key vẫn hoạt động. Luôn kiểm tra isValid() ở nơi có khả năng key đã bị hủy.

## 12. Selector.close() không đóng các channel đã đăng ký

Đây là điểm ownership dễ bị hiểu nhầm. Selector quản lý registration và tài nguyên chờ sự kiện; channel là đối tượng độc lập.

Khi Selector đóng:

- Các SelectionKey đã đăng ký bị invalid.
- Các channel được deregister khỏi selector.
- Tài nguyên gắn với selector được giải phóng.
- Các ServerSocketChannel/SocketChannel vẫn cần được đóng riêng bởi owner của chúng.

Vì vậy, đoạn code sau không đủ để đóng toàn bộ server và client:

~~~java
try (Selector selector = Selector.open()) {
    // Đăng ký nhiều channel.
}
// Các channel không tự động bị đóng chỉ vì selector đã đóng.
~~~

Hãy đặt các channel vào try-with-resources hoặc một registry AutoCloseable do ứng dụng sở hữu.

## 13. Đóng channel sẽ hủy registration liên quan

Khi channel được đóng, các key đăng ký channel đó với selector sẽ bị cancel. Selector xử lý việc deregistration trong selection operation tiếp theo. Nếu channel được đăng ký với nhiều selector, việc đóng channel ảnh hưởng tất cả registration liên quan.

Ví dụ:

~~~java
client.close();
~~~

Sau khi channel đóng, không được tiếp tục dùng key để đọc/ghi hoặc đăng ký lại channel đã đóng. Nếu cần kết nối mới, mở SocketChannel mới và đăng ký key mới.

Trong event loop, khi đọc EOF:

~~~java
int count = client.read(buffer);
if (count < 0) {
    key.cancel();
    clients.close(client);
}
~~~

Việc remove key khỏi selectedKeys bằng iterator.remove() vẫn cần được thực hiện cho key đang xử lý. Cancel key và remove khỏi selected set là hai thao tác khác nhau.

## 14. Shutdown Selector loop bằng wakeup()

Selector.select() có thể chặn thread cho đến khi có sự kiện. Nếu một thread điều khiển muốn yêu cầu server dừng, nó cần đánh thức selector thread.

Selector.wakeup() là cơ chế phù hợp:

~~~java
running.set(false);

Selector current = selectorReference.get();
if (current != null) {
    current.wakeup();
}
~~~

Selector thread đang ở trong select() sẽ được đánh thức, kiểm tra cờ running và rời vòng lặp. Sau đó thread sở hữu khối try-with-resources đóng client registry, server channel và selector theo thứ tự.

Nên để thread sở hữu event loop thực hiện việc đóng resource. Thread điều khiển chỉ thay đổi trạng thái và gọi wakeup(), tránh đóng một phần resource từ nhiều thread mà không có quy tắc ownership.

Nếu selector được đóng từ thread khác, lời gọi select() đang chờ sẽ được đánh thức và trả về; các thao tác tiếp theo trên selector đã đóng sẽ ném ClosedSelectorException. Đó là một cách đóng cưỡng bức, nhưng shutdown có điều phối bằng running flag và wakeup() thường dễ quản lý hơn.

## 15. Quản lý socket path cùng vòng đời ServerSocketChannel

Đóng ServerSocketChannel giải phóng channel và listener, nhưng pathname socket trên filesystem có thể vẫn tồn tại. Nếu ứng dụng bind một path cố định, cần có chính sách dọn path sau khi server đã đóng.

Không xóa path cũ trước khi xác minh ownership. Nếu path đang được server khác sử dụng, xóa nó có thể làm mất tên endpoint mà process kia đang dùng hoặc gây hành vi khó dự đoán.

Có thể gói việc dọn path thành một resource:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

final class BoundSocketPath implements AutoCloseable {
    private final Path path;
    private boolean bound;

    BoundSocketPath(Path path) {
        this.path = path;
    }

    Path path() {
        return path;
    }

    void markBound() {
        bound = true;
    }

    @Override
    public void close() throws IOException {
        if (bound) {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Khai báo resource theo thứ tự:

~~~java
try (BoundSocketPath socketPath = new BoundSocketPath(path);
     Selector selector = Selector.open();
     ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX);
     ClientChannels clients = new ClientChannels()) {

    server.configureBlocking(false);
    server.bind(UnixDomainSocketAddress.of(socketPath.path()));
    socketPath.markBound();

    server.register(selector, SelectionKey.OP_ACCEPT);
    // Event loop.
}
~~~

Khi rời khối try, ClientChannels đóng trước, sau đó server đóng, Selector đóng và cuối cùng BoundSocketPath xóa pathname. Nếu bind thất bại trước markBound(), resource path không xóa một file mà ứng dụng chưa chứng minh là mình đã tạo.

Trong ứng dụng thực tế, cần kiểm soát trường hợp process crash vì finally/try-with-resources không chạy khi process bị kill cưỡng bức hoặc máy mất điện. Startup recovery phải xác định socket stale một cách an toàn, không xóa path chỉ dựa vào việc file tồn tại.

## 16. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Quên đóng ServerSocketChannel | Listener và file descriptor còn mở | Đưa server channel vào try-with-resources |
| Quên đóng Selector | Tài nguyên selector không được giải phóng đúng lúc | Đưa Selector vào try-with-resources |
| Nghĩ đóng Selector sẽ đóng mọi channel | Client/server channel vẫn còn mở | Quản lý channel bằng resource riêng hoặc registry |
| Chỉ gọi SelectionKey.cancel() | Registration bị hủy nhưng channel vẫn mở | Đóng channel khi không còn dùng |
| Đóng client ngay sau khi register | Channel biến mất trước khi event loop xử lý | Giữ ownership trong registry/connection object |
| Đăng ký channel ở blocking mode | Registration không hợp lệ | Gọi configureBlocking(false) trước register |
| Không remove selected key | Key cũ bị xử lý lặp lại | Gọi iterator.remove() khi lấy key |
| Không kiểm tra key.isValid() | Thao tác trên key đã cancel/đóng | Kiểm tra validity trước khi xử lý |
| Dùng forEach để duyệt selectedKeys và sửa set | Có thể gặp lỗi sửa collection khi duyệt | Dùng Iterator và remove đúng cách |
| Dùng một channel mutable từ nhiều thread | Race condition và lifecycle khó xác định | Giao ownership cho event loop hoặc đồng bộ hóa rõ ràng |
| Xóa socket path trước khi bind mà không kiểm tra | Có thể ảnh hưởng server instance khác | Chỉ cleanup path do instance hiện tại sở hữu |
| Đóng channel từ thread ngoài trong lúc xử lý key | Event loop gặp key invalid hoặc ClosedChannelException | Dùng trạng thái shutdown và wakeup để điều phối |

## 17. Kiểm thử lifecycle của channel và selector

Test nên xác nhận cả trạng thái channel lẫn hành vi của selector:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.StandardProtocolFamily;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class UnixChannelLifecycleTest {
    @TempDir
    Path tempDir;

    @Test
    void closesChannelAndSelectorWithTryWithResources() throws Exception {
        Path socketPath = tempDir.resolve("service.sock");
        Selector selector = Selector.open();
        ServerSocketChannel server =
                ServerSocketChannel.open(StandardProtocolFamily.UNIX);

        try {
            try (selector; server) {
                server.configureBlocking(false);
                server.bind(java.net.UnixDomainSocketAddress.of(socketPath));
                server.register(selector, SelectionKey.OP_ACCEPT);

                assertTrue(server.isOpen());
                assertTrue(selector.isOpen());
            }
        } finally {
            Files.deleteIfExists(socketPath);
        }

        assertFalse(server.isOpen());
        assertFalse(selector.isOpen());
        assertFalse(Files.exists(socketPath));
    }
}
~~~

Test này kiểm tra server channel và selector đều đóng sau khối try. Socket path được xóa sau khi server đã đóng.

Có thể kiểm tra rằng selector close không tự đóng channel:

~~~java
@Test
void closingSelectorDoesNotCloseRegisteredChannel() throws Exception {
    try (ServerSocketChannel server =
                 ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
        server.configureBlocking(false);

        try (Selector selector = Selector.open()) {
            server.register(selector, SelectionKey.OP_ACCEPT);
            assertTrue(server.isOpen());
        }

        assertTrue(server.isOpen());
    }
}
~~~

Test thứ hai làm rõ ownership: sau khi selector đóng, server channel vẫn mở cho đến khi khối try của server kết thúc.

Trong test tích hợp, nên kiểm tra thêm:

- Client được đóng khi nhận EOF.
- Client registry đóng mọi client còn mở khi server shutdown.
- SelectionKey không còn hợp lệ sau cancel/close.
- Socket path được dọn sau khi server channel đóng.
- Lỗi khi accept/register vẫn dẫn tới cleanup client vừa accept.
- Selector được wakeup khi có yêu cầu shutdown từ thread khác.

## 18. Checklist review

- [ ] Selector và server channel có nằm trong try-with-resources không?
- [ ] Channel được cấu hình non-blocking trước khi register không?
- [ ] Mỗi accepted SocketChannel có owner rõ ràng không?
- [ ] Client registry có đóng mọi channel còn mở khi server dừng không?
- [ ] Đóng Selector có bị nhầm là đóng channel không?
- [ ] Khi cancel key, channel có được đóng nếu không còn dùng không?
- [ ] Selected key có được remove khỏi selectedKeys() không?
- [ ] Code có kiểm tra key.isValid() trước khi xử lý không?
- [ ] Client EOF và exception có dẫn tới close đúng cách không?
- [ ] Shutdown có wakeup selector và để owner thread đóng tài nguyên không?
- [ ] Socket path chỉ bị xóa sau khi server đã đóng và đã xác nhận ownership không?
- [ ] Test có bao phủ đóng bình thường và cleanup khi exception không?

## 19. Ghi nhớ

- ServerSocketChannel, SocketChannel và Selector đều cần được đóng.
- try-with-resources đóng resource theo thứ tự ngược với thứ tự khai báo.
- Channel phải ở non-blocking mode trước khi đăng ký với Selector.
- Accepted SocketChannel ban đầu ở blocking mode; hãy cấu hình lại trước register.
- Selector quản lý readiness và SelectionKey, không sở hữu vòng đời channel.
- Selector.close() invalidates keys và deregisters channel, nhưng không tự đóng các channel.
- SelectionKey.cancel() hủy đăng ký, không thay thế channel.close().
- Đóng channel sẽ hủy registration liên quan.
- selectedKeys() cần được duyệt bằng Iterator và remove key đã xử lý.
- Với nhiều client, dùng registry hoặc connection object để đóng các channel còn mở khi shutdown.
- Dùng Selector.wakeup() để đánh thức event loop; để thread sở hữu loop đóng tài nguyên.
- Socket pathname có thể còn sau khi server channel đóng; chỉ xóa path mà instance đã bind và sở hữu.

Quản lý channel và selector an toàn bắt đầu từ việc xác định ownership. Đưa Selector, server channel và registry client vào try-with-resources, đóng từng client khi kết thúc, xử lý cancellation đúng cách và dọn socket path sau khi server đóng sẽ giúp server Unix-domain socket giải phóng tài nguyên ổn định cả khi chạy bình thường lẫn khi có lỗi.

## Tài liệu tham khảo

- [Java SE 26 Selector API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/Selector.html) — vòng đời selector, selection và wakeup.
- [Java SE 26 SelectionKey API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SelectionKey.html) — cancellation, validity, interest operations và attachments.
- [Java SE 26 ServerSocketChannel API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html) — bind, accept và blocking mode.
- [Java SE 26 SocketChannel API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html) — connect, read, write và close.
- [Java SE 26 Channel API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/Channel.html) — đóng channel và trạng thái open.
- [JEP 380: Unix-Domain Socket Channels](https://openjdk.org/jeps/380) — hỗ trợ Unix-domain socket channels được chuẩn hóa trong Java 16.
