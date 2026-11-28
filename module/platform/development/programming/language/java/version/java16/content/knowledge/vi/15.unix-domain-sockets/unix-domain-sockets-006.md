# Mở ServerSocketChannel bằng protocol family UNIX

Java 16 hoàn thiện hỗ trợ Unix-domain socket channels thông qua JEP 380. Ở phía server, API trung tâm là **ServerSocketChannel**. Để mở server channel cho Unix-domain socket, cần truyền **StandardProtocolFamily.UNIX** vào factory method **open(ProtocolFamily)**. Sau khi mở, channel chưa được bind; server phải gắn nó với một **UnixDomainSocketAddress** trước khi nhận kết nối.

Unix-domain socket phù hợp cho giao tiếp giữa các tiến trình trên cùng host. Nó dùng pathname trong filesystem thay cho IP address và port. Bài học này tập trung vào cách mở server channel, bind địa chỉ, nhận kết nối, chọn blocking hoặc non-blocking mode, cấu hình backlog và socket options, cùng các giới hạn vận hành cần hiểu khi triển khai.

## 1. ServerSocketChannel là gì?

**ServerSocketChannel** là selectable channel dành cho socket lắng nghe kết nối. API này thuộc package **java.nio.channels** và có thể làm việc với socket Internet hoặc Unix-domain socket tùy protocol family được chọn khi mở channel.

Một server channel có vòng đời cơ bản:

1. Mở channel với protocol family phù hợp.
2. Bind channel vào địa chỉ local.
3. Chấp nhận kết nối bằng **accept()**.
4. Đọc và ghi dữ liệu qua **SocketChannel** được trả về.
5. Đóng channel khi server dừng.

Với Unix-domain socket, địa chỉ local là **UnixDomainSocketAddress**. Địa chỉ chứa pathname mà hệ điều hành dùng để tạo endpoint socket trong filesystem.

Cần phân biệt hai factory method:

~~~java
ServerSocketChannel.open();
~~~

Mở server channel cho Internet protocol socket theo mặc định.

~~~java
ServerSocketChannel.open(StandardProtocolFamily.UNIX);
~~~

Mở server channel cho Unix-domain socket. Đây là dạng cần dùng khi muốn bind vào **UnixDomainSocketAddress**.

Không thể mở channel Internet mặc định rồi truyền địa chỉ Unix vào bind. Protocol family được chọn khi tạo channel.

## 2. Mở server channel với StandardProtocolFamily.UNIX

Ví dụ tối thiểu:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.nio.channels.ServerSocketChannel;

public class UnixServer {
    public static void main(String[] args) throws IOException {
        try (ServerSocketChannel server =
                 ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

            System.out.println("Unix-domain server channel opened");
        }
    }
}
~~~

**StandardProtocolFamily.UNIX** xác định loại socket mà channel sẽ sử dụng. Hằng số này và hỗ trợ Unix-domain socket channels được cung cấp trong Java 16.

Phương thức **open(ProtocolFamily)** có từ Java 15, nhưng Unix-domain socket channels được chuẩn hóa trong Java 16. Khi chạy trên một runtime hoặc nền tảng không hỗ trợ protocol family được yêu cầu, JVM có thể ném **UnsupportedOperationException**.

Các lỗi có thể gặp khi mở channel:

- **UnsupportedOperationException:** protocol family UNIX không được provider hoặc nền tảng hỗ trợ.
- **IOException:** lỗi I/O khi tạo channel.

Nên xử lý khả năng không hỗ trợ trong ứng dụng cần chạy trên nhiều nền tảng:

~~~java
ServerSocketChannel server;

try {
    server = ServerSocketChannel.open(StandardProtocolFamily.UNIX);
} catch (UnsupportedOperationException exception) {
    throw new IllegalStateException(
        "Unix-domain sockets are not supported by this runtime",
        exception
    );
}
~~~

Ví dụ này chuyển lỗi hỗ trợ nền tảng thành lỗi cấu hình rõ ràng ở tầng ứng dụng. Nếu ứng dụng có phương án giao tiếp khác, có thể chọn fallback ở tầng cấu hình.

## 3. Channel mới mở chưa được bind

Sau khi gọi **open(StandardProtocolFamily.UNIX)**, channel ở trạng thái open nhưng chưa gắn với địa chỉ local. Không thể gọi **accept()** để nhận kết nối trước khi bind.

Ví dụ bind vào một pathname:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Path;

public class UnixServer {
    public static void main(String[] args) throws IOException {
        Path socketPath = Path.of("/run/order-service/orders.sock");
        UnixDomainSocketAddress address =
            UnixDomainSocketAddress.of(socketPath);

        try (ServerSocketChannel server =
                 ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

            server.bind(address);
            System.out.println("Listening at " + address);

            // Server có thể gọi accept() sau khi bind thành công.
        }
    }
}
~~~

Thứ tự quan trọng là:

- Chọn protocol family **UNIX** khi mở channel.
- Tạo địa chỉ bằng **UnixDomainSocketAddress**.
- Gọi **bind(address)**.
- Chỉ sau khi bind thành công mới bắt đầu accept.

Nếu gọi **accept()** khi channel chưa bind, API ném **NotYetBoundException**.

## 4. Chuẩn bị pathname trước khi bind

Khi bind Unix-domain socket vào pathname, hệ điều hành tạo một socket file tương ứng. Thư mục cha phải tồn tại và process cần có quyền filesystem phù hợp.

Có thể chuẩn bị thư mục trước khi bind:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

Path socketPath = Path.of("/run/order-service/orders.sock");
Files.createDirectories(socketPath.getParent());
~~~

**Files.createDirectories()** tạo các thư mục cha còn thiếu. Nó không tạo socket file; socket file chỉ được tạo khi channel bind thành công.

Trước khi bind, cần kiểm tra pathname đã được sử dụng hay còn socket file cũ. Không nên xóa mù một file cùng tên vì nó có thể thuộc một server đang chạy. Quy trình cleanup phải xác minh instance sở hữu socket đã dừng và pathname thuộc ứng dụng hiện tại.

Pathname Unix-domain socket có giới hạn độ dài phụ thuộc nền tảng và implementation. Giới hạn được kiểm tra khi bind, không phải khi tạo **UnixDomainSocketAddress**. Hãy giữ path ngắn và tránh phụ thuộc vào một giới hạn byte cố định trên mọi hệ điều hành.

## 5. Bind với backlog

Có hai overload thường dùng:

~~~java
server.bind(address);
~~~

~~~java
server.bind(address, 100);
~~~

Overload thứ nhất tương đương với gọi **bind(address, 0)**. Overload thứ hai cho phép chỉ định **backlog**, tức số kết nối đang chờ được accept tối đa theo cách diễn giải của implementation.

Backlog không phải số client đồng thời mà server có thể xử lý. Nó liên quan tới hàng đợi kết nối chưa được ứng dụng accept. Server vẫn cần gọi **accept()** và xử lý các channel đã được chấp nhận.

Ý nghĩa chính xác của backlog phụ thuộc hệ điều hành và implementation:

- Hệ điều hành có thể giới hạn giá trị tối đa.
- Implementation có thể điều chỉnh giá trị yêu cầu.
- Giá trị 0 hoặc âm dùng backlog mặc định của implementation.
- Không nên xem backlog là bảo đảm về số lượng kết nối sẽ được xếp hàng chính xác.

Ví dụ:

~~~java
server.bind(address, 128);
~~~

Giá trị 128 là cấu hình yêu cầu cho hàng đợi pending connection. Cần đo và điều chỉnh theo mô hình tải, khả năng accept và khả năng xử lý request của ứng dụng.

## 6. Nhận kết nối bằng accept()

Sau khi bind, gọi **accept()** để nhận kết nối từ client:

~~~java
SocketChannel client = server.accept();
~~~

Giá trị trả về là **SocketChannel**, đại diện cho kết nối đã được chấp nhận. Server đọc và ghi dữ liệu qua channel này.

Trong blocking mode (chế độ mặc định):

- Nếu chưa có kết nối đang chờ, **accept()** sẽ block cho tới khi có kết nối hoặc xảy ra lỗi.
- Khi có kết nối, phương thức trả về SocketChannel mới.
- SocketChannel được trả về ở blocking mode, kể cả khi server channel đang ở non-blocking mode.

Trong non-blocking mode:

- **accept()** trả về **null** ngay nếu chưa có kết nối đang chờ.
- Vòng lặp không nên quay liên tục vô hạn để kiểm tra null; hãy dùng **Selector** để chờ sự kiện accept.

ServerSocketChannel chỉ hỗ trợ thao tác **SelectionKey.OP_ACCEPT** trong Selector.

## 7. Ví dụ server echo ở blocking mode

Ví dụ sau nhận từng client, đọc dữ liệu và gửi lại đúng các byte đã nhận. Nó minh họa vòng đời channel và cách xử lý ByteBuffer; framing của giao thức ứng dụng cần được thiết kế riêng.

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;

public class UnixEchoServer {
    public static void main(String[] args) throws IOException {
        Path socketPath = Path.of("/run/order-service/echo.sock");
        Files.createDirectories(socketPath.getParent());

        UnixDomainSocketAddress address =
            UnixDomainSocketAddress.of(socketPath);

        try (ServerSocketChannel server =
                 ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

            server.bind(address, 64);
            System.out.println("Listening at " + address);

            while (true) {
                try (SocketChannel client = server.accept()) {
                    ByteBuffer buffer = ByteBuffer.allocate(8192);

                    int bytesRead;
                    while ((bytesRead = client.read(buffer)) != -1) {
                        buffer.flip();

                        while (buffer.hasRemaining()) {
                            client.write(buffer);
                        }

                        buffer.clear();
                    }
                }
            }
        }
    }
}
~~~

Luồng xử lý:

1. Tạo thư mục cha cho socket path.
2. Tạo **UnixDomainSocketAddress**.
3. Mở **ServerSocketChannel** với protocol family **UNIX**.
4. Bind địa chỉ với backlog 64.
5. Chờ client bằng **accept()**.
6. Đọc dữ liệu vào ByteBuffer.
7. Gọi **flip()** để chuyển buffer sang chế độ đọc.
8. Gửi lại toàn bộ byte còn lại; vòng lặp write xử lý trường hợp một lần write chưa ghi hết.
9. Gọi **clear()** để tái sử dụng buffer cho lần đọc tiếp theo.
10. Đóng client channel sau khi client kết thúc kết nối.

Ví dụ xử lý một client tại một thời điểm. Trong server thực tế, có thể dispatch client channel sang worker pool hoặc dùng Selector để phục vụ nhiều kết nối. Cần giới hạn số worker và quản lý thời gian chờ để tránh client chậm giữ tài nguyên vô hạn.

Socket file có thể vẫn còn sau khi server channel đóng. Ví dụ trên không tự động xóa socket path khi shutdown; ứng dụng production cần cleanup có kiểm tra quyền sở hữu và tránh xóa file của instance khác.

## 8. Dùng Selector với non-blocking server

**ServerSocketChannel** là selectable channel, nên có thể đăng ký với **Selector**. Trong non-blocking mode, **accept()** trả về null khi chưa có kết nối. Selector giúp thread chờ sự kiện thay vì polling liên tục.

Khung thiết lập:

~~~java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

Selector selector = Selector.open();

ServerSocketChannel server =
    ServerSocketChannel.open(StandardProtocolFamily.UNIX);

server.configureBlocking(false);
server.bind(
    UnixDomainSocketAddress.of(
        Path.of("/run/order-service/selector.sock")
    )
);

server.register(selector, SelectionKey.OP_ACCEPT);
~~~

Vòng lặp event có thể nhận kết nối như sau:

~~~java
while (true) {
    selector.select();

    var iterator = selector.selectedKeys().iterator();

    while (iterator.hasNext()) {
        SelectionKey key = iterator.next();
        iterator.remove();

        if (key.isAcceptable()) {
            ServerSocketChannel listeningChannel =
                (ServerSocketChannel) key.channel();

            SocketChannel client = listeningChannel.accept();

            if (client != null) {
                client.configureBlocking(false);
                client.register(selector, SelectionKey.OP_READ);
            }
        }
    }
}
~~~

Đây là phần minh họa bước accept và đăng ký channel. Server hoàn chỉnh cần bổ sung xử lý **OP_READ**, ghi dữ liệu, đóng key khi client disconnect và xử lý lỗi I/O.

Lưu ý:

- Server channel phải được cấu hình non-blocking trước khi đăng ký với Selector.
- SocketChannel được trả về từ **accept()** ban đầu ở blocking mode; nếu muốn đăng ký nó với Selector, phải gọi **configureBlocking(false)** trước.
- Không đăng ký một channel đang ở blocking mode với Selector.
- Luôn loại bỏ key khỏi selected-key set sau khi xử lý để tránh xử lý lại cùng sự kiện ngoài ý muốn.

## 9. Socket options cho Unix-domain server

Socket options được cấu hình bằng **setOption()** và có thể kiểm tra bằng **supportedOptions()**.

Với ServerSocketChannel cho Internet protocol socket, các option chuẩn gồm **SO_RCVBUF** và **SO_REUSEADDR**. Với Unix-domain server socket trong Java 16, option chuẩn được liệt kê là:

| Option | Hỗ trợ trên Unix-domain ServerSocketChannel | Ý nghĩa |
| --- | --- | --- |
| **SO_RCVBUF** | Có | Kích thước receive buffer của socket |
| **SO_REUSEADDR** | Không được liệt kê là option chuẩn được hỗ trợ | Không nên giả định có thể bật như TCP server |

Ví dụ cấu hình receive buffer:

~~~java
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Path;

try (ServerSocketChannel server =
         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

    server.setOption(StandardSocketOptions.SO_RCVBUF, 64 * 1024);

    server.bind(
        UnixDomainSocketAddress.of(
            Path.of("/run/order-service/buffer.sock")
        )
    );

    System.out.println(
        server.getOption(StandardSocketOptions.SO_RCVBUF)
    );
}
~~~

Giá trị hệ điều hành thực sự áp dụng có thể khác giá trị yêu cầu do giới hạn nền tảng. Nếu ứng dụng cần kiểm tra khả năng hỗ trợ trước khi cấu hình, dùng:

~~~java
if (server.supportedOptions().contains(StandardSocketOptions.SO_RCVBUF)) {
    server.setOption(StandardSocketOptions.SO_RCVBUF, 64 * 1024);
}
~~~

Các option bổ sung có thể được implementation hỗ trợ. Hãy kiểm tra **supportedOptions()** trên runtime đích thay vì giả định mọi option của TCP đều dùng được với Unix-domain socket.

## 10. Không dùng ServerSocket adapter cho Unix-domain channel

**ServerSocketChannel.socket()** trả về đối tượng **ServerSocket** tương ứng với channel Internet protocol. Với Unix-domain server channel, phương thức này ném **UnsupportedOperationException** vì **java.net.ServerSocket** không phải adapter cho Unix-domain socket.

Ví dụ sau không phù hợp:

~~~java
ServerSocketChannel server =
    ServerSocketChannel.open(StandardProtocolFamily.UNIX);

// Không dùng server.socket() cho Unix-domain socket
~~~

Hãy dùng trực tiếp các API của channel:

- **bind(UnixDomainSocketAddress)** để lắng nghe.
- **accept()** để nhận kết nối.
- **SocketChannel.read(ByteBuffer)** để đọc.
- **SocketChannel.write(ByteBuffer)** để ghi.
- **close()** để giải phóng channel.

Cách này giữ đúng mô hình NIO và protocol family đã chọn.

## 11. Tự gán địa chỉ bằng bind(null)

Server có thể yêu cầu hệ điều hành tự gán pathname:

~~~java
try (ServerSocketChannel server =
         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

    server.bind(null);

    UnixDomainSocketAddress localAddress =
        (UnixDomainSocketAddress) server.getLocalAddress();

    System.out.println("Bound to " + localAddress.getPath());
}
~~~

Khi bind với null, implementation tạo một socket file duy nhất trong thư mục tạm của hệ thống. Có thể lấy địa chỉ thực tế bằng **getLocalAddress()**.

Địa chỉ tự gán hữu ích khi server không cần một pathname cố định. Nếu client khác phải kết nối, server cần công bố path đã được gán bằng một cơ chế phù hợp, chẳng hạn file cấu hình runtime hoặc service discovery nội bộ.

Socket file tự gán cũng tồn tại sau khi channel đóng và cần được dọn dẹp theo quy tắc ownership. Không giả định hệ điều hành tự xóa file khi process kết thúc.

## 12. Vòng đời socket file và cleanup

Khác với TCP port, Unix-domain socket pathname gắn với một file trong filesystem. Khi bind thành công, file socket được tạo. Sau khi channel đóng, file có thể vẫn tồn tại.

Trước khi bind lại cùng pathname, cần xóa file socket cũ. Nhưng không được xóa chỉ dựa trên việc file đang tồn tại: nó có thể thuộc một process đang chạy khác.

Quy trình an toàn:

1. Chọn thư mục socket có quyền truy cập giới hạn cho service.
2. Khi startup, xác định instance hiện tại có quyền sở hữu pathname hay không.
3. Nếu path đã tồn tại, xác minh socket cũ không còn được instance đang chạy sử dụng.
4. Chỉ xóa stale socket khi chắc chắn thuộc instance đã dừng.
5. Bind channel.
6. Khi shutdown, đóng server channel và cleanup path do instance sở hữu.

Không dùng **Files.deleteIfExists(socketPath)** một cách mù quáng trong startup. Nếu xóa nhầm socket file của server đang chạy, client mới có thể không kết nối được tới pathname dự kiến.

## 13. Lỗi thường gặp khi mở và bind server channel

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **UnsupportedOperationException** khi open UNIX | Runtime hoặc provider không hỗ trợ protocol family UNIX | Kiểm tra runtime và nền tảng; cung cấp fallback nếu cần |
| **NotYetBoundException** khi accept | Channel chưa bind thành công | Gọi bind trước accept |
| **AlreadyBoundException** | Channel đã bind rồi | Không bind lần hai trên cùng channel |
| **UnsupportedAddressTypeException** | Địa chỉ không tương thích protocol family | Dùng UnixDomainSocketAddress với channel UNIX |
| **IOException** khi bind | Thư mục cha không tồn tại, quyền không đủ, path quá dài hoặc socket path đã được sử dụng | Kiểm tra filesystem, quyền và socket file cũ |
| **accept()** block quá lâu | Server đang ở blocking mode và chưa có client | Dùng Selector/non-blocking hoặc quản lý timeout ở kiến trúc ứng dụng |
| **accept()** trả null | Server ở non-blocking mode và chưa có kết nối chờ | Chờ Selector thay vì polling liên tục |
| Không đăng ký được accepted channel vào Selector | Accepted SocketChannel vẫn ở blocking mode | Gọi configureBlocking(false) trước register |
| **setOption()** ném UnsupportedOperationException | Option không được channel hỗ trợ | Kiểm tra supportedOptions() trước |
| **socket()** ném UnsupportedOperationException | Unix-domain channel không có ServerSocket adapter | Dùng trực tiếp ServerSocketChannel API |

## 14. Quy trình triển khai thực tế

Khi xây dựng Unix-domain server trong Java 16 hoặc mới hơn, có thể đi theo các bước:

1. Xác nhận runtime và nền tảng hỗ trợ protocol family **UNIX**.
2. Chọn pathname ngắn, tuyệt đối và nằm trong thư mục có quyền truy cập phù hợp.
3. Chuẩn bị thư mục cha và kiểm tra socket file cũ theo ownership.
4. Mở channel bằng **ServerSocketChannel.open(StandardProtocolFamily.UNIX)**.
5. Cấu hình các socket option được hỗ trợ nếu có yêu cầu cụ thể.
6. Bind bằng **UnixDomainSocketAddress** và backlog phù hợp.
7. Chọn blocking accept loop hoặc non-blocking Selector theo mô hình tải.
8. Xử lý từng client bằng **SocketChannel**, quản lý ByteBuffer và giới hạn tài nguyên.
9. Đóng client channel và server channel đúng vòng đời.
10. Cleanup socket file do ứng dụng sở hữu sau khi server dừng.
11. Kiểm thử trên các nền tảng triển khai thực tế, vì giới hạn path và khả năng hỗ trợ phụ thuộc hệ điều hành.

## 15. Kết luận

Để mở Unix-domain server trong Java 16, dùng **ServerSocketChannel.open(StandardProtocolFamily.UNIX)**. Channel mới mở chưa được bind; cần gọi **bind(UnixDomainSocketAddress)** trước khi accept. **accept()** trả về SocketChannel để đọc và ghi dữ liệu, còn Selector có thể được dùng khi server hoạt động ở non-blocking mode.

Backlog chỉ là gợi ý về hàng đợi pending connection với semantics phụ thuộc implementation. Unix-domain server channel hỗ trợ **SO_RCVBUF** trong danh sách option chuẩn của Java 16; không nên giả định các TCP option như **SO_REUSEADDR** áp dụng được. Bind tạo socket file và file này có thể tồn tại sau khi channel đóng, vì vậy cleanup phải kiểm tra ownership trước khi xóa.

## Tài liệu tham khảo

- [ServerSocketChannel — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [ServerSocketChannel — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [JEP 380: Unix-Domain Socket Channels](https://openjdk.org/jeps/380)
- [java.nio.channels — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/package-summary.html)
- [SocketChannel — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [StandardProtocolFamily — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/net/StandardProtocolFamily.html)
- [StandardSocketOptions — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/net/StandardSocketOptions.html)

