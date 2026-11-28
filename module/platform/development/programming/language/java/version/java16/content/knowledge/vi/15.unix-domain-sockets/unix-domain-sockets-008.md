# Mở SocketChannel UNIX và kết nối tới endpoint cục bộ

Java 16 bổ sung hỗ trợ Unix-domain socket vào **SocketChannel** và **ServerSocketChannel** thông qua JEP 380. Ở phía client, **SocketChannel** mở kết nối tới một endpoint cục bộ được định danh bằng **UnixDomainSocketAddress**. Sau khi kết nối, ứng dụng dùng các thao tác NIO quen thuộc như **read(ByteBuffer)**, **write(ByteBuffer)** và **close()** để trao đổi byte.

Có hai cách mở client channel thường dùng: gọi **SocketChannel.open(address)** để mở và kết nối trong một bước, hoặc gọi **SocketChannel.open(StandardProtocolFamily.UNIX)** rồi chủ động gọi **connect(address)**. Cách thứ hai cần thiết khi muốn điều khiển non-blocking connect bằng **Selector**. Bài học này tập trung vào client-side flow, dữ liệu dạng stream, xử lý partial read/write, trạng thái kết nối và các khác biệt của Unix-domain socket so với TCP socket.

## 1. SocketChannel UNIX dùng để làm gì?

**SocketChannel** là selectable channel cho socket hướng stream. Với Unix-domain socket, channel giao tiếp với một tiến trình khác trên cùng host thông qua pathname trong filesystem.

Ví dụ server đang lắng nghe tại:

~~~text
/run/order-service/orders.sock
~~~

Client tạo **UnixDomainSocketAddress** từ pathname đó và kết nối tới server. Không có IP address hay TCP port trong địa chỉ này.

Unix-domain socket phù hợp khi hai tiến trình cần trao đổi dữ liệu cục bộ, chẳng hạn:

- Ứng dụng Java giao tiếp với một service agent trên cùng máy.
- Web server giao tiếp với application server trong cùng host.
- Các tiến trình trong những container chia sẻ một volume chứa socket file.
- Client nội bộ gọi một daemon mà không cần mở endpoint TCP ra mạng.

Unix-domain socket là IPC trên cùng host. Nếu client và server ở hai máy khác nhau, cần một transport qua mạng như TCP.

## 2. Chọn đúng cách mở SocketChannel

Có ba cách mở channel cần phân biệt:

| Cách gọi | Protocol family | Trạng thái sau khi mở |
| --- | --- | --- |
| **SocketChannel.open()** | Internet protocol socket mặc định | Open, chưa kết nối |
| **SocketChannel.open(StandardProtocolFamily.UNIX)** | Unix-domain socket | Open, chưa kết nối |
| **SocketChannel.open(SocketAddress)** với UnixDomainSocketAddress | JVM suy ra UNIX | Đã kết nối nếu lời gọi thành công |

Không dùng **SocketChannel.open()** rồi truyền Unix-domain address vào **connect()**. No-argument factory mở Internet protocol socket. Muốn mở channel UNIX, hãy chỉ rõ family hoặc dùng convenience factory nhận trực tiếp địa chỉ Unix.

### Cách ngắn: mở và kết nối trong một bước

~~~java
import java.io.IOException;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

Path socketPath = Path.of("/run/order-service/orders.sock");
UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(socketPath);

try (SocketChannel client = SocketChannel.open(address)) {
    System.out.println("Connected: " + client.isConnected());
}
~~~

Khi tham số là **UnixDomainSocketAddress**, **SocketChannel.open(address)** hoạt động như mở channel với **StandardProtocolFamily.UNIX**, sau đó gọi **connect(address)**. Nếu lời gọi trả về thành công, channel đã kết nối.

Đây là cách gọn và phù hợp với client blocking đơn giản.

### Cách tường minh: mở family rồi connect

~~~java
SocketChannel client =
    SocketChannel.open(StandardProtocolFamily.UNIX);

client.connect(address);
~~~

Cách này hữu ích khi cần:

- Bind local address trước khi connect.
- Chọn blocking hoặc non-blocking mode.
- Điều khiển connect qua Selector.
- Kiểm tra trạng thái pending bằng **isConnectionPending()**.
- Hoàn tất kết nối bằng **finishConnect()**.

Với channel mới, mặc định là blocking mode. Nếu giữ chế độ này, **connect(address)** chờ đến khi kết nối thành công hoặc thất bại.

## 3. Tạo địa chỉ và kết nối tới server

Địa chỉ remote được tạo bằng **UnixDomainSocketAddress.of(Path)** hoặc **of(String)**:

~~~java
Path socketPath = Path.of("/run/order-service/orders.sock");

UnixDomainSocketAddress remote =
    UnixDomainSocketAddress.of(socketPath);

try (SocketChannel client = SocketChannel.open(remote)) {
    System.out.println(client.getRemoteAddress());
}
~~~

**getRemoteAddress()** trả về địa chỉ Unix-domain của server khi channel đã kết nối. Nếu channel chưa kết nối, kết quả là **null**.

Có thể xác nhận trạng thái bằng:

~~~java
if (client.isConnected()) {
    System.out.println(client.getRemoteAddress());
}
~~~

Việc tạo address chỉ chuyển pathname thành đối tượng địa chỉ. Nó không kiểm tra server đang chạy, socket file có tồn tại hay quyền truy cập có phù hợp. Các điều kiện đó được kiểm tra khi thực hiện connect.

Nếu endpoint không tồn tại, server chưa bind hoặc hệ điều hành từ chối kết nối, **connect()** có thể ném **IOException**. Chi tiết exception cụ thể phụ thuộc nền tảng và tình huống hệ điều hành trả về.

## 4. Client có cần bind local address không?

Thông thường, client Unix-domain socket không cần tự bind một pathname local trước khi connect:

~~~java
try (SocketChannel client = SocketChannel.open(remote)) {
    // Client đã kết nối; local endpoint có thể là unnamed.
}
~~~

Nếu channel UNIX được connect mà chưa gọi **bind()**, socket local được bind ngầm dưới dạng **unnamed socket**. Nó không có socket file tương ứng trong filesystem, nên không cần xóa local socket pathname sau khi đóng channel.

Gọi **bind(null)** cho client cũng tạo một unnamed socket. Đây không phải cách để yêu cầu hệ điều hành tạo một pathname có thể công bố cho peer.

Chỉ bind client vào một pathname riêng khi giao thức hoặc ứng dụng thật sự cần một local endpoint có tên:

~~~java
Path localPath = Path.of("/run/order-client/client-01.sock");

try (SocketChannel client =
         SocketChannel.open(StandardProtocolFamily.UNIX)) {

    client.bind(UnixDomainSocketAddress.of(localPath));
    client.connect(remote);

    // Giao tiếp qua channel.
}
~~~

Khi client bind vào pathname cụ thể, hệ điều hành tạo socket file. File này có thể tồn tại sau khi channel đóng và phải được cleanup theo ownership. Không xóa file chỉ dựa trên việc nó đang tồn tại; xác minh instance sở hữu đã dừng trước.

Trong đa số ứng dụng client, unnamed local socket là đủ và giảm công việc quản lý file.

## 5. Đọc và ghi dữ liệu bằng ByteBuffer

Sau khi kết nối, dùng **write(ByteBuffer)** để gửi byte và **read(ByteBuffer)** để nhận byte.

Ví dụ gửi một thông điệp UTF-8:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

byte[] payload = "hello service".getBytes(StandardCharsets.UTF_8);
ByteBuffer outgoing = ByteBuffer.wrap(payload);

while (outgoing.hasRemaining()) {
    client.write(outgoing);
}
~~~

**ByteBuffer.wrap()** tạo buffer bao quanh mảng byte. Sau khi write, position của buffer tăng theo số byte đã được ghi.

Không giả định một lần **write()** luôn ghi hết toàn bộ buffer. Socket channel có thể chỉ ghi được một phần dữ liệu. Vòng lặp tiếp tục cho đến khi buffer không còn byte chưa gửi.

Đọc dữ liệu:

~~~java
ByteBuffer incoming = ByteBuffer.allocate(4096);

int bytesRead = client.read(incoming);

if (bytesRead > 0) {
    incoming.flip();

    // Xử lý các byte từ position đến limit.
}
~~~

Sau khi đọc, buffer ở chế độ ghi. Gọi **flip()** để chuyển sang chế độ đọc phần byte vừa nhận. Khi xử lý xong và muốn dùng lại buffer, gọi **clear()**.

## 6. Hiểu đúng kết quả của read() và write()

Các phương thức channel làm việc với byte stream, vì vậy kết quả có ý nghĩa cụ thể:

| Kết quả | **read(ByteBuffer)** | **write(ByteBuffer)** |
| --- | --- | --- |
| Số dương | Đã đọc số byte tương ứng | Đã ghi số byte tương ứng |
| **0** | Không đọc được byte ở lần gọi đó, hoặc buffer đích không còn chỗ | Không ghi được byte ở lần gọi đó, hoặc buffer nguồn rỗng |
| **-1** | Peer đã đóng output stream, báo end-of-stream | Không dùng -1 cho write |

Trong blocking mode, read thường chờ khi chưa có dữ liệu. Trong non-blocking mode, read có thể trả về 0 nếu hiện chưa có byte để đọc.

Một lần read không tương ứng với một message. Nếu client gửi 100 byte, server có thể đọc thành nhiều lần; ngược lại, nhiều lần write có thể được nhận trong một lần read. Ứng dụng phải tự định nghĩa framing cho giao thức.

## 7. Stream không giữ ranh giới message

Unix-domain socket channel là stream-oriented. Nó truyền chuỗi byte liên tục, không tự thêm ranh giới message.

Ví dụ client gọi:

~~~java
client.write(ByteBuffer.wrap("ABC".getBytes(StandardCharsets.UTF_8)));
client.write(ByteBuffer.wrap("DEF".getBytes(StandardCharsets.UTF_8)));
~~~

Server có thể đọc thành:

- Một lần đọc nhận **ABCDEF**.
- Hai lần đọc lần lượt nhận **ABC** và **DEF**.
- Nhiều lần đọc nhỏ hơn, tùy buffer, scheduler và implementation.

Không dựa vào số lần gọi write để xác định message boundary. Chọn một framing strategy, ví dụ:

| Cách framing | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| Fixed-length | Mỗi message có độ dài cố định | Bản tin có cấu trúc kích thước cố định |
| Delimiter | Kết thúc message bằng ký tự phân cách đã quy ước | Text protocol, line-based command |
| Length-prefix | Gửi độ dài trước payload | Binary protocol hoặc payload có kích thước thay đổi |
| EOF | Đóng output để báo hết dữ liệu | Trao đổi một chiều đơn giản, một request trên connection |

Với giao thức request/response lâu dài, length-prefix hoặc delimiter thường rõ ràng hơn việc dùng EOF làm ranh giới duy nhất.

## 8. Ví dụ client gửi request và đọc response đến EOF

Ví dụ sau tương thích Java 16 và giả định server echo ở bài học trước: server nhận byte, gửi lại byte tương ứng và đóng output khi client kết thúc output.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class UnixEchoClient {
    public static void main(String[] args) throws IOException {
        Path socketPath = Path.of("/run/order-service/echo.sock");
        UnixDomainSocketAddress address =
            UnixDomainSocketAddress.of(socketPath);

        byte[] request = "hello from client".getBytes(StandardCharsets.UTF_8);

        try (SocketChannel client = SocketChannel.open(address)) {
            ByteBuffer outgoing = ByteBuffer.wrap(request);

            while (outgoing.hasRemaining()) {
                client.write(outgoing);
            }

            // Báo server rằng client không gửi thêm byte nào.
            client.shutdownOutput();

            ByteArrayOutputStream response = new ByteArrayOutputStream();
            ByteBuffer incoming = ByteBuffer.allocate(1024);

            while (client.read(incoming) != -1) {
                incoming.flip();

                byte[] chunk = new byte[incoming.remaining()];
                incoming.get(chunk);
                response.write(chunk);

                incoming.clear();
            }

            System.out.println(
                response.toString(StandardCharsets.UTF_8)
            );
        }
    }
}
~~~

Các bước chính:

1. Tạo Unix-domain address từ socket path của server.
2. Mở channel và kết nối bằng **SocketChannel.open(address)**.
3. Chuyển request thành byte UTF-8.
4. Ghi hết buffer; không giả định một lần write ghi hết.
5. Gọi **shutdownOutput()** để báo server rằng client đã gửi xong.
6. Đọc response cho tới khi nhận **-1**.
7. Chuyển byte response về String UTF-8.
8. Đóng channel bằng try-with-resources.

Ví dụ này dùng EOF làm tín hiệu kết thúc request và response. Không dùng nguyên mẫu này cho giao thức nhiều request trên một connection nếu server không có framing riêng.

## 9. Half-close với shutdownOutput() và shutdownInput()

**SocketChannel** hỗ trợ đóng riêng một chiều của kết nối:

- **shutdownOutput()** ngừng gửi dữ liệu. Những lần write sau đó sẽ ném **ClosedChannelException**.
- **shutdownInput()** ngừng nhận dữ liệu; những lần read sau đó trả về **-1**.
- **close()** đóng toàn bộ channel và giải phóng tài nguyên.

Half-close hữu ích khi client muốn báo rằng request đã gửi xong nhưng vẫn cần đọc response. Đây là cách làm trong ví dụ echo client ở trên.

Không gọi **shutdownOutput()** trước khi gửi hết request. Khi đã shutdown output, channel không thể gửi thêm byte qua chiều đó.

Nếu giao thức có nhiều request/response trên cùng connection, thường không dùng EOF để phân định từng message; hãy dùng length-prefix, delimiter hoặc protocol framing riêng.

## 10. Kết nối non-blocking với Selector

Với client cần xử lý nhiều kết nối hoặc không muốn thread bị chặn trong lúc connect, có thể dùng non-blocking mode.

Quy trình:

1. Mở channel với **StandardProtocolFamily.UNIX**.
2. Gọi **configureBlocking(false)**.
3. Gọi **connect(remote)**.
4. Nếu connect trả về true, kết nối đã hoàn tất ngay.
5. Nếu trả về false, đăng ký **SelectionKey.OP_CONNECT**.
6. Khi Selector báo connectable, gọi **finishConnect()**.
7. Khi finishConnect trả về true, chuyển interest sang **OP_READ** hoặc xử lý dữ liệu theo giao thức.

Ví dụ khởi tạo:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

Selector selector = Selector.open();

SocketChannel client =
    SocketChannel.open(StandardProtocolFamily.UNIX);

client.configureBlocking(false);

UnixDomainSocketAddress remote =
    UnixDomainSocketAddress.of(
        Path.of("/run/order-service/orders.sock")
    );

if (client.connect(remote)) {
    client.register(selector, SelectionKey.OP_READ);
} else {
    client.register(selector, SelectionKey.OP_CONNECT);
}
~~~

Trong vòng lặp Selector:

~~~java
while (true) {
    selector.select();

    var iterator = selector.selectedKeys().iterator();

    while (iterator.hasNext()) {
        SelectionKey key = iterator.next();
        iterator.remove();

        if (key.isConnectable()) {
            SocketChannel channel = (SocketChannel) key.channel();

            if (channel.finishConnect()) {
                key.interestOps(SelectionKey.OP_READ);
            }
        }

        if (key.isReadable()) {
            // Đọc dữ liệu không blocking vào ByteBuffer.
        }
    }
}
~~~

Đây là khung minh họa connect và chuyển sang trạng thái đọc. Ứng dụng hoàn chỉnh cần xử lý lỗi connect, đóng channel và key, quản lý buffer cũng như ghi dữ liệu khi có output pending.

Không giả định non-blocking connect luôn trả về false. Với kết nối local, nó có thể hoàn tất ngay và trả về true. Nếu đã kết nối ngay, không cần chờ **OP_CONNECT**.

### Tránh đăng ký OP_WRITE liên tục

Socket thường sẵn sàng ghi trong phần lớn thời gian. Nếu đăng ký **OP_WRITE** liên tục, Selector có thể đánh thức vòng lặp thường xuyên dù ứng dụng không có dữ liệu cần gửi.

Chỉ thêm **OP_WRITE** khi còn dữ liệu pending trong outbound buffer. Khi ghi hết buffer, bỏ **OP_WRITE** khỏi interest set. Đây là nguyên tắc quan trọng để tránh busy loop trong NIO server/client.

## 11. Các trạng thái kết nối cần theo dõi

SocketChannel cung cấp các phương thức kiểm tra trạng thái:

| Method | Ý nghĩa |
| --- | --- |
| **isOpen()** | Channel còn mở hay đã đóng |
| **isConnected()** | Socket đang mở và đã kết nối |
| **isConnectionPending()** | Đã bắt đầu non-blocking connect nhưng chưa hoàn tất |
| **getLocalAddress()** | Địa chỉ local nếu channel đã bind |
| **getRemoteAddress()** | Địa chỉ remote nếu channel đã kết nối |

Ví dụ:

~~~java
if (client.isConnectionPending()) {
    // Connect đang chờ hoàn tất.
}

if (client.isConnected()) {
    System.out.println(client.getRemoteAddress());
}
~~~

Không dùng **isConnected()** như một bảo đảm rằng peer sẽ còn sống trong lần read/write tiếp theo. Peer có thể đóng kết nối ngay sau khi trạng thái được kiểm tra. Cần xử lý EOF và IOException trong thao tác I/O thật.

## 12. Socket options hỗ trợ cho UNIX SocketChannel

Socket option được cấu hình bằng **setOption()**. Danh sách chuẩn cho Unix-domain SocketChannel khác với Internet SocketChannel.

| Option | UNIX SocketChannel | Ý nghĩa |
| --- | --- | --- |
| **SO_SNDBUF** | Có | Kích thước send buffer |
| **SO_RCVBUF** | Có | Kích thước receive buffer |
| **SO_LINGER** | Có, khi channel ở blocking mode | Cách close xử lý dữ liệu chưa gửi |
| **TCP_NODELAY** | Không được liệt kê | Thuộc TCP |
| **SO_KEEPALIVE** | Không được liệt kê | Thuộc Internet socket |
| **SO_REUSEADDR** | Không được liệt kê | Không giả định có semantics như TCP |

Ví dụ:

~~~java
import java.net.StandardSocketOptions;

client.setOption(StandardSocketOptions.SO_SNDBUF, 64 * 1024);
client.setOption(StandardSocketOptions.SO_RCVBUF, 64 * 1024);
~~~

Giá trị được hệ điều hành áp dụng có thể khác giá trị yêu cầu. Một số implementation có thể hỗ trợ option riêng; hãy kiểm tra **supportedOptions()** trên channel thực tế trước khi cấu hình.

Không dùng **TCP_NODELAY** cho Unix-domain socket. UDS không chạy trên TCP nên không có thuật toán Nagle để tắt.

## 13. SocketChannel UNIX không có Socket adapter

Với Internet protocol socket, **SocketChannel.socket()** có thể trả về đối tượng **java.net.Socket** tương ứng. Với Unix-domain socket, phương thức này ném **UnsupportedOperationException** vì **Socket** gắn với mô hình địa chỉ Internet.

Ví dụ không phù hợp:

~~~java
SocketChannel client =
    SocketChannel.open(StandardProtocolFamily.UNIX);

// Không dùng client.socket() cho Unix-domain socket.
~~~

Hãy dùng trực tiếp API NIO:

- **connect(SocketAddress)**.
- **read(ByteBuffer)**.
- **write(ByteBuffer)**.
- **shutdownInput()** và **shutdownOutput()**.
- **getLocalAddress()** và **getRemoteAddress()**.
- **close()**.

Cũng không dùng **java.net.Socket** để thay thế SocketChannel UNIX. Java 16 chuẩn hóa hỗ trợ Unix-domain socket trong NIO channels; các lớp Socket/ServerSocket truyền thống không phải adapter cho loại socket này.

## 14. Thread safety và cách chia sẻ channel

SocketChannel an toàn khi được sử dụng bởi nhiều thread đồng thời. Tuy nhiên, chỉ cho phép tối đa một thread đọc tại một thời điểm và tối đa một thread ghi tại một thời điểm.

Có thể tổ chức một reader và một writer riêng trên cùng channel nếu giao thức cho phép. Không nên để nhiều thread cùng đọc một channel vì chúng sẽ cạnh tranh lấy byte từ cùng stream; ranh giới dữ liệu có thể bị chia giữa các thread ngoài ý muốn.

Các lời gọi **connect()** và **finishConnect()** được đồng bộ với nhau. Nếu thread khác bắt đầu read/write trong lúc connect hoặc finishConnect đang chạy, thao tác đó sẽ chờ cho đến khi lời gọi kết nối hoàn tất.

Trong ứng dụng nhiều request, thường nên có một owner cho trạng thái kết nối và outbound buffer. Nếu nhiều producer gửi dữ liệu, đưa message vào queue rồi để một writer tuần tự hóa và ghi ra channel.

## 15. Lỗi thường gặp khi mở và connect

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **UnsupportedOperationException** khi mở UNIX | Runtime hoặc provider không hỗ trợ protocol family | Kiểm tra runtime/nền tảng và chuẩn bị fallback |
| **UnsupportedAddressTypeException** | Channel không phải UNIX hoặc address không tương thích | Dùng open(UNIX) hoặc open(UnixDomainSocketAddress) |
| **NotYetConnectedException** khi read/write | Channel chưa kết nối | Hoàn tất connect trước I/O |
| **ConnectionPendingException** | Đã có non-blocking connect đang chờ | Chờ OP_CONNECT và gọi finishConnect |
| **NoConnectionPendingException** | Gọi finishConnect khi không có connect đang pending | Kiểm tra isConnectionPending và trình tự trạng thái |
| **AlreadyConnectedException** | Gọi connect lần nữa trên channel đã kết nối | Tạo channel mới cho kết nối mới |
| **IOException** khi connect | Server chưa chạy, pathname sai, quyền hoặc lỗi hệ điều hành | Kiểm tra endpoint và log lỗi gốc |
| **read() trả -1** | Peer đã shutdown output hoặc đóng kết nối | Xử lý EOF theo protocol |
| **write() chưa gửi hết buffer** | Socket buffer hoặc non-blocking mode chỉ chấp nhận một phần byte | Tiếp tục write phần buffer còn lại |
| **read() trả 0** | Non-blocking channel hiện chưa có byte hoặc buffer đích đầy | Chờ OP_READ hoặc xử lý buffer |
| **socket() ném UnsupportedOperationException** | Unix-domain channel không có Socket adapter | Dùng trực tiếp SocketChannel API |

## 16. Quy trình xây dựng client UNIX thực tế

1. Lấy socket pathname từ cấu hình của ứng dụng.
2. Tạo **UnixDomainSocketAddress** bằng **of(Path)** hoặc **of(String)**.
3. Dùng **SocketChannel.open(address)** nếu muốn connect blocking trong một bước.
4. Dùng **open(StandardProtocolFamily.UNIX)** nếu cần bind local hoặc non-blocking connect.
5. Kiểm tra **isConnected()** và **getRemoteAddress()** sau khi kết nối.
6. Gửi byte qua ByteBuffer và xử lý partial write.
7. Đọc byte cho tới khi nhận đủ frame theo protocol, không giả định một read là một message.
8. Dùng **shutdownOutput()** nếu protocol dùng EOF để kết thúc request.
9. Dùng Selector với **OP_CONNECT**, **OP_READ** và **OP_WRITE** khi xây dựng client non-blocking.
10. Xử lý EOF, IOException, close và trạng thái reconnect rõ ràng.
11. Chỉ bind local pathname khi có yêu cầu; nếu đã bind tên, cleanup socket file theo ownership.
12. Kiểm thử trên đúng hệ điều hành và JDK triển khai.

## 17. Kết luận

Để kết nối Unix-domain endpoint trong Java 16 trở lên, có thể dùng **SocketChannel.open(UnixDomainSocketAddress)** cho client blocking đơn giản. Nếu cần điều khiển trạng thái, hãy mở bằng **SocketChannel.open(StandardProtocolFamily.UNIX)** rồi gọi **connect()**. Non-blocking client cần theo dõi **OP_CONNECT** và gọi **finishConnect()** trước khi đọc hoặc ghi.

Sau khi kết nối, dữ liệu được trao đổi dưới dạng byte stream qua ByteBuffer. Một lần read/write không tương ứng một message; cần framing rõ ràng và phải xử lý partial write, EOF cùng trạng thái buffer. Client thường không cần bind local pathname vì kết nối ngầm dùng unnamed socket. Hãy dùng đúng socket options được hỗ trợ cho UNIX, không gọi Socket adapter và quản lý channel theo một owner rõ ràng trong ứng dụng đồng thời.

## Tài liệu tham khảo

- [SocketChannel — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [SocketChannel — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [JEP 380: Unix-Domain Socket Channels](https://openjdk.org/jeps/380)
- [java.nio.channels — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/package-summary.html)
- [ByteChannel — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/ByteChannel.html)
- [StandardSocketOptions — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/net/StandardSocketOptions.html)
- [Selector — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/Selector.html)

