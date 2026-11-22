# Unix domain socket qua StandardProtocolFamily.UNIX và UnixDomainSocketAddress

## 1. Bài toán: giao tiếp giữa các tiến trình trên cùng máy

Một ứng dụng Java có thể cần trao đổi dữ liệu với một tiến trình khác trên **cùng máy**: service nội bộ, tiến trình quản lý, daemon, worker hoặc hai chương trình chạy tách biệt nhưng dùng chung hệ điều hành. TCP loopback qua `127.0.0.1`/`::1` là một lựa chọn. **Unix domain socket** là một lựa chọn khác dành cho **local inter-process communication (IPC)**, được định danh chủ yếu bằng **đường dẫn trên hệ thống tệp**, không bằng IP và port.

Từ **Java 16** (JEP 380), Java NIO hỗ trợ Unix domain socket qua `ServerSocketChannel` và `SocketChannel`. Vì chủ đề thuộc nhóm **Buffer và channel**, trọng tâm ở đây là **`StandardProtocolFamily.UNIX`, `UnixDomainSocketAddress`, vòng đời channel và `ByteBuffer`**.

Hai đầu trao đổi có mô hình:

~~~text
Tiến trình server                       Tiến trình client
ServerSocketChannel                    SocketChannel
open(StandardProtocolFamily.UNIX)      open(StandardProtocolFamily.UNIX)
           |                                      |
bind(UnixDomainSocketAddress)          connect(UnixDomainSocketAddress)
           |______________________________________|
                          |
                  pathname cục bộ
             ví dụ /run/myapp/service.sock
                          |
                server.accept() -> SocketChannel
                          |
                đọc/ghi ByteBuffer hai chiều
~~~

Đường dẫn `/run/myapp/service.sock` chỉ là minh họa kiểu Unix/Linux, không phải đường dẫn bắt buộc hay tự có trên mọi hệ điều hành.

**Đặc tính then chốt:**

- Dùng để giao tiếp **cùng host**, không phải kết nối trực tiếp từ máy này sang máy khác qua Internet.
- Không có cặp **IP/port** như `InetSocketAddress`; đối tượng `UnixDomainSocketAddress` bao bọc một `Path`.
- Kết nối sử dụng **kênh hướng luồng (stream-oriented)**: dữ liệu vẫn là luồng byte, **không có ranh giới thông điệp tự động**.
- Không cần mở port TCP mạng cho service này, nhưng vẫn cần quản lý **quyền truy cập file/đường dẫn**, kết nối và giới hạn tài nguyên.
- Việc hỗ trợ phụ thuộc **JDK, hệ điều hành và provider**. Java 17+ có API, nhưng một môi trường cụ thể vẫn có thể không hỗ trợ `UNIX`.

## 2. Các API cần phân biệt

| API | Vai trò |
| --- | --- |
| `StandardProtocolFamily.UNIX` | Chọn họ địa chỉ Unix domain, thay vì `INET`/`INET6` |
| `UnixDomainSocketAddress.of(Path)` | Tạo địa chỉ endpoint từ đường dẫn mặc định của hệ điều hành |
| `UnixDomainSocketAddress.of(String)` | Tạo địa chỉ từ chuỗi đường dẫn |
| `ServerSocketChannel.open(UNIX)` | Tạo kênh server cho Unix domain, lúc đầu chưa bind |
| `server.bind(address)` | Gắn tên socket vào filesystem và bắt đầu lắng nghe |
| `server.accept()` | Nhận kết nối, trả về `SocketChannel` trao đổi dữ liệu |
| `SocketChannel.open(UNIX)` | Tạo kênh client Unix domain chưa kết nối |
| `client.connect(address)` | Kết nối đến đường dẫn socket mà server đang lắng nghe |
| `SocketChannel.open(address)` | Cách viết rút gọn: tự suy ra họ `UNIX` khi address là `UnixDomainSocketAddress` |
| `ByteBuffer` | Bộ đệm có `position`/`limit`/`capacity` cho `read` và `write` |
| `Files.deleteIfExists(path)` | Dọn socket filesystem node **sau khi server đóng** |

Các import đặc trưng:

~~~java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;
~~~

*Đây là danh sách import minh họa; ví dụ chạy độc lập phía dưới có đủ import cần thiết.*

Điểm dễ nhầm: `SocketChannel.open()` và `ServerSocketChannel.open()` **không tham số** thông thường tạo kênh Internet, **không** tự động tạo Unix domain socket. Muốn kiểm soát rõ giao thức, hãy gọi phiên bản `open(StandardProtocolFamily.UNIX)`. Đối với client, `SocketChannel.open(unixAddress)` cũng hợp lệ vì có overload tự suy ra family từ kiểu địa chỉ.

Một số phương thức thích ứng kiểu cũ như `SocketChannel.socket()` hoặc `ServerSocketChannel.socket()` **không hỗ trợ Unix domain socket** và có thể ném `UnsupportedOperationException`. Hãy dùng **API channel trực tiếp**, ví dụ `read(ByteBuffer)`, `write(ByteBuffer)`, `getLocalAddress()` và `getRemoteAddress()`. Đừng chuyển kênh Unix domain thành `java.net.Socket`/`ServerSocket` bằng `socket()` như với Internet channel.

## 3. UnixDomainSocketAddress: endpoint là đường dẫn, không phải cổng

Có thể tạo địa chỉ bằng:

~~~java
Path socketPath = Path.of("/run/myapp/service.sock");
UnixDomainSocketAddress address = UnixDomainSocketAddress.of(socketPath);
~~~

*Đoạn minh họa đường dẫn Unix; hãy chọn đường dẫn thực sự tồn tại thư mục cha, có quyền phù hợp với hệ điều hành đang dùng.*

Hoặc với một chuỗi:

~~~java
UnixDomainSocketAddress address =
        UnixDomainSocketAddress.of("service.sock");
~~~

*Đoạn trên minh họa địa chỉ tương đối. Server và client phải giải thích đường dẫn theo đúng thư mục làm việc/cách triển khai tương ứng.*

`UnixDomainSocketAddress` là **mô tả địa chỉ**, không tự tạo file, không mở channel và không kết nối. Chỉ khi `server.bind(address)` thành công, hệ điều hành/JDK mới tạo filesystem node cho Unix domain socket ở địa chỉ đó. Client cần một đường dẫn quy chiếu tới **cùng endpoint thực**.

Những lưu ý về đường dẫn:

- **Thư mục cha:** phải tồn tại và có quyền truy cập phù hợp. Với dịch vụ thật, đặt socket trong thư mục dành riêng có chủ sở hữu/quyền truy cập được quản lý.
- **Tên đã tồn tại:** bind thường không thể dùng lại path có sẵn. Chỉ đóng server **không tự xóa** file socket cũ; phải dọn node đúng cách sau khi đóng.
- **Giới hạn độ dài:** hệ điều hành có giới hạn đường dẫn Unix domain socket theo **byte** (thường quanh 100 byte, tùy nền tảng). Đường dẫn temp hoặc dự án quá sâu có thể làm bind thất bại.
- **Path từ default filesystem:** `UnixDomainSocketAddress.of(Path)` yêu cầu `Path` thuộc hệ thống tệp mặc định; không dùng tùy tiện một `Path` từ provider ảo/ZIP.
- **Địa chỉ tương đối:** phụ thuộc working directory và cách hai tiến trình giải quyết path. Chương trình production nên cấu hình và kiểm chứng đường dẫn nhất quán.
- **Không đồng nghĩa file dữ liệu thường:** node socket được hệ điều hành tạo là điểm đặt tên để IPC; không đọc/ghi nó bằng `Files.readString(...)` như một tệp văn bản.

Ở phía client, khi `connect` mà không `bind` một địa chỉ local tường minh, socket thường **unnamed**: địa chỉ local có path rỗng và **không có file client riêng cần xóa**. Server, ngược lại, cần một tên có thể tìm thấy để các client kết nối.

## 4. Chu trình server và client

**Phía server:**

~~~text
ServerSocketChannel.open(UNIX)
    -> bind(UnixDomainSocketAddress.of(path))
    -> accept()
    -> SocketChannel của phiên vừa chấp nhận
    -> đọc/ghi ByteBuffer trên channel được accept
    -> đóng accepted channel và server channel
    -> xóa filesystem socket node của server
~~~

**Phía client:**

~~~text
SocketChannel.open(UNIX)
    -> connect(UnixDomainSocketAddress.of(cùng path))
    -> đọc/ghi ByteBuffer
    -> close()
~~~

`ServerSocketChannel` là **kênh lắng nghe**, không phải kênh trao đổi payload của một client cụ thể. Sau `accept()`, giá trị trả về mới là `SocketChannel` đã kết nối để truyền dữ liệu. Một server có thể `accept()` nhiều lần cho nhiều client, mỗi client có kênh riêng.

Khi `accept()`, `read()` và `write()` dùng **blocking mode mặc định**: nếu chưa có sự kiện/dữ liệu cần thiết, lời gọi có thể chờ. Có thể `configureBlocking(false)` và dùng `Selector`, nhưng khi đó phải xử lý `accept() == null`, đọc/ghi trả 0, đăng ký `SelectionKey` và hoàn tất kết nối chưa xong bằng `finishConnect()`. Hai ví dụ của bài dùng blocking mode để tập trung đúng vào Unix domain socket và ByteBuffer.

Kênh Unix domain stream **không biến thành UDP datagram**. Một lần `write` không buộc tương ứng đúng một lần `read`. Với thông điệp dài biến đổi, phải có framing (ví dụ length prefix) giống các luồng byte khác.

## 5. Ví dụ Java 17+: tạo Unix domain socket và trao đổi hai chiều

Ví dụ này chạy **cả server và client trong một chương trình** để kiểm chứng API mà không cần hai terminal. Nó tạo một thư mục tạm riêng, bind đến `service.sock` trong thư mục đó, client kết nối, server nhận `"HELLO"` và trả `"OK"`. Đường dẫn được tạo duy nhất cho mỗi lượt chạy, nên không phải ghi đè một socket pathname có sẵn.

Lưu vào `UnixSocketBasicDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class UnixSocketBasicDemo {
    static void writeAll(SocketChannel channel, String value) throws IOException {
        ByteBuffer bytes = StandardCharsets.UTF_8.encode(value);
        while (bytes.hasRemaining()) {
            channel.write(bytes);
        }
    }

    static String readExactly(SocketChannel channel, int count) throws IOException {
        ByteBuffer bytes = ByteBuffer.allocate(count);
        while (bytes.hasRemaining()) {
            if (channel.read(bytes) < 0) {
                throw new EOFException("stream ended before " + count + " bytes");
            }
        }
        bytes.flip();
        return StandardCharsets.UTF_8.decode(bytes).toString();
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("java-uds-");
        Path socketPath = dir.resolve("service.sock");
        try {
            UnixDomainSocketAddress endpoint = UnixDomainSocketAddress.of(socketPath);
            try (ServerSocketChannel server =
                         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
                server.bind(endpoint);

                try (SocketChannel client =
                             SocketChannel.open(StandardProtocolFamily.UNIX)) {
                    client.connect(endpoint);
                    try (SocketChannel accepted = server.accept()) {
                        System.out.println("server unix address: "
                                + (server.getLocalAddress()
                                instanceof UnixDomainSocketAddress));
                        System.out.println("client connected: " + client.isConnected());

                        writeAll(client, "HELLO");
                        System.out.println("server received: " + readExactly(accepted, 5));

                        writeAll(accepted, "OK");
                        System.out.println("client received: " + readExactly(client, 2));
                    }
                }
            }
        } finally {
            Files.deleteIfExists(socketPath);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch/chạy với **JDK 17+ và nền tảng hỗ trợ Unix domain socket**:

~~~bash
javac UnixSocketBasicDemo.java
java UnixSocketBasicDemo
~~~

Kết quả kiểm thử khi bind/connect qua Unix domain socket thành công:

~~~text
server unix address: true
client connected: true
server received: HELLO
client received: OK
~~~

Giải thích thứ tự:

1. `Files.createTempDirectory` cho một thư mục mới duy nhất, sau đó `socketPath = dir.resolve("service.sock")` chọn tên socket chưa tồn tại. Đây là cách tránh đụng tên khi demo chạy nhiều lần; nếu tên temp quá dài so với giới hạn hệ điều hành, phải chọn thư mục ngắn hơn.
2. `UnixDomainSocketAddress.of(socketPath)` tạo endpoint. `ServerSocketChannel.open(UNIX).bind(endpoint)` tạo server Unix domain và lắng nghe.
3. `SocketChannel.open(UNIX)` tạo client; `client.connect(endpoint)` kết nối. `server.accept()` trả kênh phía server cho phiên này.
4. `getLocalAddress() instanceof UnixDomainSocketAddress` xác nhận kiểu endpoint mà server đã bind; `client.isConnected()` cho biết kết nối đã thành công.
5. `writeAll` lặp khi `ByteBuffer.hasRemaining()` vì ngay cả channel chặn cũng **không được giả định một lần write luôn xử lý toàn bộ buffer**.
6. `readExactly` lặp đến đủ số byte yêu cầu; `read` trả `-1` khi phía kia đóng đầu ra/luồng kết thúc. `flip()` chuyển buffer từ chế độ ghi dữ liệu vào sang chế độ đọc dữ liệu ra.

**Giới hạn của demo:** hai độ dài 5 và 2 byte đã biết trước. Đây **không phải framing tổng quát** cho message có độ dài bất kỳ. Ở phần kế tiếp ta thêm header độ dài để biết chính xác cần đọc bao nhiêu byte.

Trong `finally`, chương trình xóa file socket sau khi các channel đã đóng, rồi xóa thư mục tạm. Đây là trách nhiệm bổ sung so với việc chỉ dùng `try-with-resources`. Vì thư mục được tạo riêng cho demo, việc dọn này không động đến một path dịch vụ có sẵn. Với service production, phải kiểm soát quyền sở hữu và lifecycle trước khi xóa node, tuyệt đối không xóa bừa một path do người dùng/tiến trình khác quản lý.

## 6. ByteBuffer: position, limit, flip và read/write đủ byte

Trong Java NIO, `ByteBuffer` có ba khái niệm:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `capacity()` | Sức chứa cố định của buffer |
| `position()` | Vị trí thao tác kế tiếp |
| `limit()` | Ranh giới trên (exclusive) của vùng có thể thao tác |
| `remaining()` | Số phần tử từ position tới limit |
| `hasRemaining()` | Còn byte cần đọc/ghi hay không |
| `flip()` | Đặt limit = position, position = 0, chuyển buffer vừa ghi sang chế độ đọc |
| `clear()` | position = 0, limit = capacity, chuẩn bị **ghi đè**, không xóa nội dung byte |
| `compact()` | Dồn byte chưa đọc về đầu buffer, chuẩn bị nhận thêm khi dùng incremental parser |

Khi ghi dữ liệu **từ chương trình ra channel**, ta thường:

~~~java
ByteBuffer output = StandardCharsets.UTF_8.encode("HELLO");
while (output.hasRemaining()) {
    channel.write(output);
}
~~~

*Đoạn minh họa trong một phương thức đã có `SocketChannel channel`; không phải chương trình độc lập.*

`StandardCharsets.UTF_8.encode` trả một `ByteBuffer` có giới hạn tương ứng dữ liệu đã mã hóa, sẵn sàng đọc từ buffer để `channel.write` gửi đi. Nếu dùng `ByteBuffer.allocate(...)` rồi `put(...)`, phải gọi `flip()` trước khi `write()`; nếu không channel có thể gửi byte chưa phải payload mong muốn.

Khi **đọc từ channel vào buffer**, thứ tự ngược:

~~~java
ByteBuffer input = ByteBuffer.allocate(5);
while (input.hasRemaining()) {
    if (channel.read(input) < 0) {
        throw new EOFException("missing bytes");
    }
}
input.flip();
String value = StandardCharsets.UTF_8.decode(input).toString();
~~~

*Đoạn minh họa cho **blocking SocketChannel** và payload 5 byte đã biết trước; cần import `ByteBuffer`, `EOFException` và `StandardCharsets`.*

Khi channel ở non-blocking mode, `read` hoặc `write` có thể trả 0 dù buffer còn byte. Không được bận vòng `while` liên tục mà không dùng `Selector`/readiness hoặc chiến lược scheduling phù hợp. Với blocking mode, vòng lặp đọc/ghi trên là cách đơn giản để xử lý partial I/O.

**Quan trọng:** Unix domain socket là stream, nên framing không được dựa vào số lần đọc. Ví dụ server viết hai message liên tiếp; phía client có thể đọc nhận các byte theo cách gộp/tách khác. Muốn đọc message trọn vẹn cần **quy tắc ranh giới** và giới hạn kích thước hợp lệ.

## 7. Ví dụ Java 17+: hai thông điệp length-prefixed qua một kết nối

Ví dụ này nâng cấp thành giao thức:
- Header `4 byte int` ở big-endian (theo `ByteBuffer.putInt/getInt` mặc định).
- Body là số byte UTF-8 đúng bằng length header.
- Giới hạn `MAX_FRAME_BYTES = 1024` để không cấp phát theo độ dài vô hạn do peer điều khiển.
- `readFully` nhận đủ header/body hoặc ném `EOFException`.
- Hai message `"A"` và `"Xin chào"` chạy liên tiếp **trên cùng một kết nối Unix domain socket**, mỗi message được phản hồi `"ACK"`.

Lưu `UnixSocketFrameDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class UnixSocketFrameDemo {
    private static final int MAX_FRAME_BYTES = 1024;

    static void writeFrame(SocketChannel channel, String message)
            throws IOException {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_FRAME_BYTES) {
            throw new IllegalArgumentException("frame too large");
        }
        ByteBuffer frame = ByteBuffer.allocate(Integer.BYTES + bytes.length);
        frame.putInt(bytes.length);
        frame.put(bytes);
        frame.flip();
        while (frame.hasRemaining()) {
            channel.write(frame);
        }
    }

    static void readFully(SocketChannel channel, ByteBuffer buffer)
            throws IOException {
        while (buffer.hasRemaining()) {
            int n = channel.read(buffer);
            if (n < 0) {
                throw new EOFException("incomplete frame");
            }
        }
    }

    static String readFrame(SocketChannel channel) throws IOException {
        ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);
        readFully(channel, header);
        header.flip();
        int length = header.getInt();
        if (length < 0 || length > MAX_FRAME_BYTES) {
            throw new IOException("invalid frame length: " + length);
        }
        ByteBuffer body = ByteBuffer.allocate(length);
        readFully(channel, body);
        body.flip();
        return StandardCharsets.UTF_8.decode(body).toString();
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("java-uds-frame-");
        Path socketPath = dir.resolve("service.sock");
        try {
            UnixDomainSocketAddress address = UnixDomainSocketAddress.of(socketPath);
            try (ServerSocketChannel server =
                         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
                server.bind(address);
                try (SocketChannel client =
                             SocketChannel.open(StandardProtocolFamily.UNIX)) {
                    client.connect(address);
                    try (SocketChannel accepted = server.accept()) {
                        for (String text : new String[] {"A", "Xin chào"}) {
                            writeFrame(client, text);
                            String received = readFrame(accepted);
                            System.out.println("server received: " + received);
                            writeFrame(accepted, "ACK");
                            System.out.println("client received: "
                                    + readFrame(client));
                        }
                    }
                }
            }
        } finally {
            Files.deleteIfExists(socketPath);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Chạy:

~~~bash
javac UnixSocketFrameDemo.java
java UnixSocketFrameDemo
~~~

Kết quả:

~~~text
server received: A
client received: ACK
server received: Xin chào
client received: ACK
~~~

Giải thích các bước của một frame:

1. `String.getBytes(UTF_8)` chuyển message sang byte trước, nên length là **số byte**, không phải `String.length()`. `"Xin chào"` chứa ký tự nhiều byte nhưng vẫn được nhận đúng.
2. `ByteBuffer.allocate(4 + payload.length)` chứa header và body. `putInt`/`put` tăng position; `flip` đặt đúng limit để `SocketChannel.write` gửi phần dữ liệu đã chuẩn bị.
3. `readFully(header)` bảo đảm nhận đủ 4 byte, `flip` rồi `getInt()` lấy length.
4. **Kiểm tra `length < 0 || length > MAX_FRAME_BYTES` trước `ByteBuffer.allocate(length)`**. Không bao giờ cấp phát mảng/buffer dựa trên trường length chưa được kiểm tra.
5. `readFully(body)` nhận đủ body (có thể qua nhiều lần đọc). `flip` rồi `UTF_8.decode(...)` giải mã đúng vùng byte.
6. Vòng `for` gửi hai frame qua một kết nối; việc `readFrame` phân tách ranh giới là nhờ **header**, không phải nhờ Unix domain socket tự ghi nhớ ranh giới.

`readFully` trong ví dụ chỉ dùng với **blocking channel**. Nếu đổi sang non-blocking, phải có trạng thái parser và xử lý `read() == 0` bằng readiness event/Selector thay vì busy-wait. Ngoài ra, message production cần kiểm tra quyền truy cập, authentication/authorization tùy bối cảnh, timeout/deadline, giới hạn số client, hạn mức tổng bộ nhớ và quy tắc giao thức khi EOF/vi phạm length.

## 8. Phân biệt Unix domain socket với TCP loopback

| Đặc điểm | TCP loopback | Unix domain socket |
| --- | --- | --- |
| Endpoint | `InetSocketAddress` gồm IP + port | `UnixDomainSocketAddress` gồm path |
| Phạm vi kết nối thông thường | Cùng máy qua loopback, có thể cấu hình TCP trên IP khác cho remote | **Chỉ cùng host/không trực tiếp qua mạng IP** |
| Java NIO server | `ServerSocketChannel.open()` rồi bind IP/port | `ServerSocketChannel.open(UNIX)` rồi bind path |
| Java NIO client | `SocketChannel.open()` rồi connect IP/port | `SocketChannel.open(UNIX)` rồi connect path |
| Bản chất dữ liệu | Byte stream | Byte stream |
| Ranh giới message | Ứng dụng tự định nghĩa | Ứng dụng tự định nghĩa |
| Quản lý tên endpoint | Port được giải phóng theo vòng đời socket của OS | Socket path thường **còn lại sau close**, cần dọn |
| Kiểm soát truy cập | Network binding, firewall, hệ điều hành và ứng dụng | Quyền thư mục/file socket, OS và ứng dụng |
| Hỗ trợ | Phụ thuộc giao thức Internet trên nền tảng | Phụ thuộc AF_UNIX/JDK/provider, giới hạn tên path |

Unix domain socket thường hợp lý khi **cả hai tiến trình ở cùng host** và muốn giao tiếp qua một pathname nội bộ. TCP loopback vẫn hữu ích khi cần khả năng chuyển sang host khác, tích hợp hệ thống vốn đòi IP/port, hoặc môi trường không có AF_UNIX.

**Không được kết luận Unix domain socket tự mã hóa dữ liệu hoặc tự xác thực peer.** Bản chất “local only” và quyền filesystem giúp giảm bề mặt truy cập, nhưng ứng dụng vẫn phải xác định trust boundary, quyền mở socket, và khi cần dùng cơ chế nhận diện peer/thông điệp phù hợp. Socket file ở thư mục chung không kiểm soát quyền có thể gây rủi ro giả mạo endpoint hoặc truy cập trái phép.

## 9. Quản lý file socket an toàn và vòng đời tài nguyên

Với server Unix domain socket **có đường dẫn tường minh**, một chu trình triển khai cẩn thận gồm:

1. Tạo **thư mục riêng** có quyền hạn phù hợp, tránh tên do bên không tin cậy điều khiển; chọn đường dẫn ngắn, cấu hình nhất quán.
2. Trước bind, xác nhận tên socket dự kiến **không bị tiến trình khác sở hữu**. Không tự động `deleteIfExists` một path dùng chung trước khi bind: có thể xóa node của dịch vụ đang chạy.
3. Mở `ServerSocketChannel.open(StandardProtocolFamily.UNIX)` rồi `bind(address)`. Khi cần client biết path, công bố path qua cấu hình được kiểm soát.
4. `accept` và quản lý từng `SocketChannel` riêng, dùng `try-with-resources` để đóng khi xong.
5. Khi shutdown, đóng server và toàn bộ accepted channels, dọn node **mà chính server sở hữu** bằng `Files.deleteIfExists(socketPath)`; kiểm soát lỗi cleanup phù hợp.
6. Theo dõi giới hạn filesystem, hạn mức handle/file descriptor, số connection và số bytes đang đợi xử lý.

Nếu server chết đột ngột, file socket có thể còn lại dù tiến trình không còn lắng nghe. Việc một path tồn tại **không chứng minh có server đang sống**. Nhưng cũng không được mặc định mọi file socket còn lại đều “rác”: một tiến trình khác có thể đang dùng tên ấy. Production nên có cơ chế kiểm soát ownership/khởi động để tránh tự xóa endpoint hợp lệ.

Một lựa chọn API khác là `server.bind(null)`: JDK sẽ tạo **một tên socket tự động trong vị trí tạm**, có thể lấy địa chỉ thật bằng `(UnixDomainSocketAddress) server.getLocalAddress()`. File socket được tạo vẫn cần xóa sau khi đóng, không phải “tên tự động nghĩa là auto-delete”. Muốn client biết tên này, phải truyền cho nó qua kênh cấu hình/điều phối riêng. Không nên giả định đường dẫn temp sẽ luôn đủ ngắn cho giới hạn tên AF_UNIX.

Ví dụ dùng `Files.createTempDirectory` để minh họa cleanup an toàn trên một thư mục thuộc chương trình demo. Với ứng dụng nhiều tiến trình thực sự, không dùng directory tạm được tạo riêng cho server nếu client không biết path; cần giải pháp cung cấp/khám phá tên hợp lý.

## 10. Giới hạn nền tảng, ngoại lệ và các API không nên nhầm

**Điều kiện Java:** `StandardProtocolFamily.UNIX` và `UnixDomainSocketAddress` có từ Java 16. Để chạy code của bài, dùng **JDK 17 hoặc mới hơn**; source và class không thể biên dịch với JDK 11 vì thiếu các API này. Một số hệ điều hành hoặc cấu hình JDK không hỗ trợ Unix domain socket và `open(UNIX)` có thể báo `UnsupportedOperationException`. Bài kiểm thử không yêu cầu kết nối Internet.

Các lỗi có thể gặp:

- **Bind path trùng:** tên đã tồn tại hoặc service khác sở hữu; thường là lỗi I/O/bind. Không “sửa” bằng cách tùy tiện xóa path không thuộc mình.
- **Thư mục không tồn tại/không đủ quyền:** server bind hoặc client connect có thể ném `IOException`; kiểm tra đường dẫn, quyền thư mục và quyền file.
- **Đường dẫn quá dài:** ràng buộc AF_UNIX ở mức OS (thường cỡ 100 byte nhưng không có con số chung cho mọi máy); chọn tên ngắn hơn.
- **Connect khi server không lắng nghe:** `connect` thất bại, không tự biến path thành server sống.
- **Địa chỉ sai loại:** ví dụ mở Internet socket channel rồi truyền địa chỉ Unix domain cho bind/connect không tương thích; có thể gặp `UnsupportedAddressTypeException`.
- **Gọi `socket()` trên Unix domain channel:** có thể ném `UnsupportedOperationException`; dùng `SocketChannel.read/write(ByteBuffer)` và `ServerSocketChannel.accept()`.
- **`ClosedChannelException`, `EOFException`, lỗi I/O khác:** cần kiểm soát vòng đời kênh và xử lý ngắt kết nối; `read` trả `-1` khi peer kết thúc đầu ghi.
- **Non-blocking bị xử lý như blocking:** `accept` có thể trả `null`; `read`/`write` có thể trả 0; phải dùng readiness và trạng thái đúng.

Bảng socket option cũng khác TCP: ví dụ `TCP_NODELAY` là tùy chọn TCP, không phải tùy chọn cho kênh Unix domain. Với Java 21, Unix `SocketChannel` thường có các tùy chọn như `SO_SNDBUF`, `SO_RCVBUF` và `SO_LINGER`; `ServerSocketChannel` Unix hỗ trợ `SO_RCVBUF`. Khi viết code portable hãy hỏi `supportedOptions()` thay vì gán cứng rằng mọi tùy chọn Internet đều hợp lệ.

## 11. Channel và Selector: mở rộng khi có nhiều kết nối

Hai ví dụ đầu cố ý dùng blocking mode để dễ chạy. Khi server cần nhiều kết nối concurrent, Java NIO vẫn cho phép dùng `Selector` với Unix domain socket channels:

- `ServerSocketChannel` hỗ trợ `SelectionKey.OP_ACCEPT` để nhận client mới.
- `SocketChannel` hỗ trợ các interest liên quan connect/read/write (tùy trạng thái) giống channel hướng luồng khác.
- Để register với selector, phải `configureBlocking(false)`.
- Khi `accept()` trả `null` hoặc `read()/write()` trả `0`, đó có thể là kết quả hợp lệ ở non-blocking mode; đợi readiness hoặc thay đổi interest, **không busy-spin**.
- Với kết nối chưa xong, dùng `finishConnect()` trước khi đọc/ghi bình thường.
- Khi đọc nhiều message vào một ByteBuffer, parser phải quản lý trạng thái và dữ liệu chưa đủ bằng `flip/compact`; không coi mỗi readiness event là đúng một frame.

**Ví dụ ý tưởng** (không phải chương trình đầy đủ):

~~~java
server.configureBlocking(false);
server.register(selector, SelectionKey.OP_ACCEPT);
// Tại event OP_ACCEPT: accept(), đăng ký channel mới;
// Tại OP_READ: đọc vào buffer và phân tích frame khi đủ byte;
// Tại OP_WRITE: ghi phần ByteBuffer còn remaining.
~~~

Để chạy thực tế cần khởi tạo `Selector`, vòng lặp `select()`, quản lý selection key, client state, timeout và shutdown. Mục tiêu của phần này là biết Unix domain socket tương thích mô hình NIO và `Selector`, **không** thay thế logic framing hay quản lý ByteBuffer.

## 12. Những sai lầm phổ biến

1. **Dùng `ServerSocketChannel.open()` rồi cố bind Unix address.** Phiên bản không tham số mở family Internet; phải `open(StandardProtocolFamily.UNIX)`.
2. **Dùng `InetSocketAddress("localhost", port)` thay cho `UnixDomainSocketAddress`.** Hai mô hình địa chỉ khác nhau; Unix domain không có port TCP.
3. **Gọi `SocketChannel.socket().getInputStream()`.** Adapter `socket()` không dành cho Unix domain channel; hãy đọc/ghi `ByteBuffer` trực tiếp.
4. **Quên `flip()` sau `put()` hoặc `read()`.** Buffer position/limit sai dẫn đến gửi byte rác hoặc decode thiếu dữ liệu.
5. **Cho rằng một lần `write` luôn ghi đủ và một lần `read` luôn đọc đủ.** Phải dùng `remaining/hasRemaining`, framing và xử lý EOF.
6. **Nghĩ Unix domain socket có message boundary.** Nó cung cấp byte stream; dùng length-prefix hoặc delimiter/application protocol.
7. **Dùng `new ByteBuffer[length]` hoặc `allocate(length)` từ header chưa validate.** Peer có thể gửi length vô lý; chặn trước allocation.
8. **Chỉ đóng server mà không dọn file socket.** Node của đường dẫn có thể vẫn tồn tại và chặn bind lần sau.
9. **Xóa file socket bất kỳ khi khởi động để “sửa lỗi đang dùng”.** Có thể xóa endpoint của tiến trình khác; cần xác định ownership và quyền trước.
10. **Chọn đường dẫn cực dài trong thư mục nested/temp.** AF_UNIX có giới hạn tên theo byte; chọn đường dẫn phù hợp nền tảng.
11. **Cho rằng local IPC tự động an toàn.** Cần phân quyền path/parent dir, xác minh peer và bảo vệ dữ liệu theo trust model.
12. **Gửi client tới path không cùng filesystem namespace.** Hai container/tiến trình phải nhìn thấy cùng endpoint; share path/mount phù hợp mới kết nối được.
13. **Chuyển sang non-blocking mà giữ vòng `readFully` bận chạy.** Kênh có thể trả 0; phải dùng `Selector`/state machine và fairness.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao địa chỉ Unix domain socket không có `host:port` như TCP? Khi nào nên dùng Unix domain thay TCP loopback?

Đáp án: nó định danh một endpoint IPC nội bộ qua filesystem path, không qua IP/port. Dùng khi cả hai tiến trình cùng host, kiểm soát đường dẫn và có hỗ trợ hệ điều hành/JDK thích hợp; TCP loopback phù hợp hơn khi cần tích hợp qua giao diện IP/port hoặc có yêu cầu remote sau này.

**Câu 2.** Vì sao lệnh `ServerSocketChannel.open()` không đủ khi muốn dùng `UnixDomainSocketAddress`?

Đáp án: constructor không tham số mở kênh Internet; cần `ServerSocketChannel.open(StandardProtocolFamily.UNIX)`. Với client, `SocketChannel.open(unixAddress)` là overload có thể tự suy ra family.

**Câu 3.** Vì sao `ByteBuffer.flip()` cần xuất hiện sau `putInt`/`put(bytes)` hoặc sau khi `read` đầy buffer?

Đáp án: vì khi ghi dữ liệu vào buffer, `position` tăng. `flip` đặt `limit` bằng position hiện tại và đưa position về 0 để vùng byte vừa nhận/ghi trở thành vùng đọc hợp lệ. `clear` chỉ reset cursor, không xóa byte.

**Câu 4.** Server gửi hai frame `"A"` và `"Xin chào"` liên tiếp. Vì sao client không được gọi `read` đúng hai lần rồi giả định nhận đúng hai message?

Đáp án: Unix domain socket dạng stream có thể gộp hoặc chia byte giữa các lần `read`; cần length prefix hoặc framing khác và vòng đọc đủ.

**Câu 5.** Sau `server.close()`, tại sao bind vào cùng socket path có thể vẫn thất bại? Có nên luôn `Files.deleteIfExists(path)` lúc khởi động?

Đáp án: node của server Unix domain socket có thể vẫn tồn tại trên filesystem; nó thường không tự biến mất sau close. Không xóa bừa lúc khởi động: phải xác minh path thuộc dịch vụ/tiến trình mình và có cơ chế tránh race; dọn path sở hữu khi shutdown.

**Câu 6.** Vì sao `client.getLocalAddress()` đối với Unix domain socket có thể có path rỗng?

Đáp án: client không bắt buộc bind một tên local. Kết nối mặc định có thể dùng địa chỉ **unnamed** nên không có socket file phía client.

**Bài thực hành:** 
- Chạy `UnixSocketBasicDemo` hai lần. Xem vì sao chương trình tạo thư mục temp riêng và dọn `service.sock` trong `finally`.
- Trong `UnixSocketFrameDemo`, thêm message UTF-8 dài hơn 1 byte/ký tự như `"Việt Nam"`, kiểm tra rằng mã hóa `getBytes(UTF_8)` tạo length theo **byte**.
- Thử bỏ `frame.flip()` trước `write` để quan sát hành vi sai trong một môi trường kiểm thử riêng, sau đó khôi phục code đúng.
- Sửa `MAX_FRAME_BYTES` thành `4` và gửi `"HELLO"`, xác minh sender từ chối vì vượt hạn mức trước allocation frame.
- Thử `ServerSocketChannel.open(StandardProtocolFamily.UNIX).bind(null)`, lấy `server.getLocalAddress()` và lên kế hoạch cleanup path thật trước khi chạy; không ghi đè endpoint hệ thống đã có.

## Tài liệu chuẩn

- [JEP 380 — Unix-Domain Socket Channels](https://openjdk.org/jeps/380)
- [UnixDomainSocketAddress — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/UnixDomainSocketAddress.html)
- [StandardProtocolFamily — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/StandardProtocolFamily.html)
- [ServerSocketChannel — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [SocketChannel — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [ByteBuffer — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html)
