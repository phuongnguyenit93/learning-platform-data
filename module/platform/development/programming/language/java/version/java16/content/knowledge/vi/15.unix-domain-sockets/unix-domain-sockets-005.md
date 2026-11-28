# Đường dẫn socket, hệ tệp mặc định và giới hạn độ dài theo nền tảng

Unix-domain socket là cơ chế giao tiếp liên tiến trình (IPC) trên cùng máy, dùng địa chỉ gắn với không gian tên cục bộ thay vì địa chỉ IP và cổng TCP. Từ Java 16, NIO cung cấp `UnixDomainSocketAddress` cùng khả năng mở `SocketChannel` và `ServerSocketChannel` với `StandardProtocolFamily.UNIX`.

Địa chỉ Unix-domain socket dạng pathname gắn với một đường dẫn trong hệ tệp. Vì vậy, server và client phải thống nhất cùng một đường dẫn, quyền truy cập vào thư mục chứa socket phải được quản lý phù hợp, và đường dẫn phải nằm trong giới hạn mà hệ điều hành hỗ trợ. Java không quy định một độ dài pathname tối đa chung cho mọi nền tảng.

## 1. Địa chỉ Unix-domain socket là một Path

Java biểu diễn địa chỉ pathname bằng `UnixDomainSocketAddress`:

```java
import java.net.UnixDomainSocketAddress;
import java.nio.file.Path;

Path socketPath = Path.of("/tmp/my-service.sock");
UnixDomainSocketAddress address = UnixDomainSocketAddress.of(socketPath);
```

`UnixDomainSocketAddress` là đối tượng địa chỉ dùng khi bind hoặc connect. Việc tạo `Path` hay `UnixDomainSocketAddress` không tự tạo socket file và cũng không mở kết nối. Socket file được hệ điều hành tạo khi server bind thành công vào địa chỉ pathname.

`Path.of(...)` tạo `Path` bằng hệ tệp mặc định của JVM. Với ứng dụng Java thông thường chạy trên hệ điều hành, đây là lựa chọn phù hợp để tham chiếu pathname mà native Unix-domain socket provider sẽ sử dụng. `UnixDomainSocketAddress.of(String)` cũng chuyển chuỗi thành `Path` qua hệ tệp mặc định. Nếu ứng dụng dùng filesystem provider tùy chỉnh, không nên giả định đường dẫn ảo của provider đó tương ứng với pathname mà hệ điều hành nhìn thấy.

Không truyền URI như `file:///tmp/my-service.sock` vào API này. Hãy truyền đường dẫn hệ tệp như `/tmp/my-service.sock` hoặc một `Path` được tạo từ đường dẫn đó.

## 2. Dùng đường dẫn tuyệt đối để server và client thống nhất

Đường dẫn tương đối được diễn giải dựa trên working directory của tiến trình. Nếu server và client được khởi chạy từ hai thư mục khác nhau, cùng một chuỗi tương đối có thể trỏ tới hai vị trí khác nhau.

Hãy chuẩn hóa thành đường dẫn tuyệt đối trước khi tạo địa chỉ:

```java
import java.net.UnixDomainSocketAddress;
import java.nio.file.Path;

Path socketPath = Path.of("run", "my-service.sock")
    .toAbsolutePath()
    .normalize();

UnixDomainSocketAddress address = UnixDomainSocketAddress.of(socketPath);
```

- `toAbsolutePath()` tạo đường dẫn tuyệt đối theo working directory hiện tại nếu đường dẫn ban đầu là tương đối.
- `normalize()` loại bỏ các thành phần `.` và `..` về mặt cú pháp.
- `normalize()` không kiểm tra sự tồn tại của file và không giải quyết symbolic link.

Trong môi trường production, nên lấy thư mục socket từ cấu hình triển khai ổn định, rồi dùng cùng cấu hình cho server và client. Không dựa vào working directory tình cờ do IDE, service manager hoặc script khởi chạy cung cấp.

## 3. Tạo thư mục cha trước khi bind

Socket pathname nằm trong hệ tệp, nên thư mục cha phải tồn tại và tiến trình server phải có quyền tạo entry tại đó:

```java
import java.io.IOException;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.net.StandardProtocolFamily;
import java.nio.file.Files;
import java.nio.file.Path;

class UnixSocketServerSetup {
    static void openServer(Path socketPath) throws IOException {
        Path absolutePath = socketPath.toAbsolutePath().normalize();
        Files.createDirectories(absolutePath.getParent());

        UnixDomainSocketAddress address = UnixDomainSocketAddress.of(absolutePath);

        try (ServerSocketChannel server = ServerSocketChannel.open(
                StandardProtocolFamily.UNIX)) {
            server.bind(address);
            // Server đã bind thành công; có thể accept kết nối tại đây.
        }
    }
}
```

Đây là phần khởi tạo minh họa. Trong ứng dụng thật, server channel cần được giữ mở trong suốt thời gian phục vụ và gọi `accept()` trong vòng đời của server; đóng channel ngay sau `bind()` sẽ kết thúc listener.

`Files.createDirectories()` tạo các thư mục còn thiếu. Nó không đặt chính sách bảo mật cho thư mục. Với socket dùng nội bộ, hãy đặt socket trong thư mục do ứng dụng sở hữu và giới hạn quyền truy cập bằng permission hoặc ACL phù hợp. Tránh đặt socket trong thư mục dùng chung có quyền ghi rộng, nơi tiến trình khác có thể thay thế hoặc chiếm pathname.

## 4. Server và client phải dùng cùng pathname

Ví dụ dưới đây minh họa server bind và client connect bằng cùng một `Path`. Server chấp nhận một kết nối, đọc một ít dữ liệu rồi đóng:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

class UnixDomainSocketExample {
    private static final Path SOCKET_PATH = Path.of(
        System.getProperty("java.io.tmpdir"), "my-service", "service.sock"
    ).toAbsolutePath().normalize();

    static void runServer() throws IOException {
        Files.createDirectories(SOCKET_PATH.getParent());
        boolean bound = false;

        try (ServerSocketChannel server = ServerSocketChannel.open(
                StandardProtocolFamily.UNIX)) {
            server.bind(UnixDomainSocketAddress.of(SOCKET_PATH));
            bound = true;

            try (SocketChannel client = server.accept()) {
                ByteBuffer buffer = ByteBuffer.allocate(256);
                int bytesRead = client.read(buffer);
                if (bytesRead > 0) {
                    buffer.flip();
                    System.out.println(StandardCharsets.UTF_8.decode(buffer));
                }
            }
        } finally {
            // Chỉ xóa pathname nếu chính lần chạy này đã bind thành công.
            if (bound) {
                Files.deleteIfExists(SOCKET_PATH);
            }
        }
    }

    static void runClient() throws IOException {
        try (SocketChannel client = SocketChannel.open(StandardProtocolFamily.UNIX)) {
            client.connect(UnixDomainSocketAddress.of(SOCKET_PATH));
            ByteBuffer message = StandardCharsets.UTF_8.encode("hello from client");
            while (message.hasRemaining()) {
                client.write(message);
            }
        }
    }
}
```

Chạy `runServer()` trong một tiến trình trước, sau đó chạy `runClient()` trong tiến trình khác. Cả hai phải dùng cùng pathname tuyệt đối. Ví dụ này chỉ đọc một lần để minh họa; giao thức thực tế cần quy định framing, xử lý partial read, timeout, xác thực peer và vòng lặp phục vụ nhiều client.

## 5. Socket pathname là entry của hệ tệp và cần quản lý vòng đời

Khi bind thành công vào pathname, hệ điều hành tạo socket entry tại đường dẫn đó. Đóng `ServerSocketChannel` giải phóng listener, nhưng pathname có thể vẫn tồn tại trong hệ tệp trên các hệ Unix. Do đó, server cần có chính sách dọn dẹp socket file khi dừng.

Một trình tự an toàn thường là:

1. Chọn thư mục riêng do ứng dụng quản lý.
2. Xác định pathname ổn định và bảo đảm không xung đột với server khác.
3. Bind thành công rồi mới đánh dấu tiến trình sở hữu pathname.
4. Khi dừng, đóng `ServerSocketChannel` trước.
5. Chỉ xóa pathname mà tiến trình này thực sự sở hữu.

Không gọi `Files.deleteIfExists(socketPath)` một cách mù quáng trước khi bind. Nếu pathname thuộc một server đang chạy, xóa entry đó có thể làm hỏng khả năng kết nối mới tới server hiện tại. Java NIO không cung cấp một thao tác portable để xác minh chắc chắn một pathname bất kỳ là socket do chính ứng dụng sở hữu; hãy dựa vào thư mục riêng, quyền truy cập và cơ chế quản lý tiến trình.

Nếu bind thất bại vì pathname đã tồn tại, hãy xác định nguyên nhân: có thể server khác đang hoạt động, hoặc đó là entry còn sót lại từ lần chạy trước. Chỉ dọn entry cũ sau khi đã xác minh server sở hữu nó không còn chạy và thao tác xóa nằm trong thư mục mà ứng dụng kiểm soát.

## 6. Hệ tệp mặc định và đường dẫn do provider tùy chỉnh

`Path` là abstraction của hệ tệp trong Java NIO. Một `Path` có thể đến từ hệ tệp mặc định hoặc từ một provider khác. Tuy nhiên, Unix-domain socket là tài nguyên native của hệ điều hành; pathname mà socket address sử dụng phải có ý nghĩa đối với filesystem namespace của hệ điều hành.

Với ứng dụng thông thường, dùng `Path.of(...)` hoặc `FileSystems.getDefault().getPath(...)` để tạo đường dẫn thuộc hệ tệp mặc định:

```java
import java.nio.file.FileSystems;
import java.nio.file.Path;

Path defaultPath = FileSystems.getDefault()
    .getPath("/var/run/my-service.sock");
```

Không lấy một `Path` từ ZIP filesystem, in-memory filesystem hoặc provider tùy chỉnh rồi giả định Unix socket provider có thể bind vào đó. Các provider này mô phỏng không gian tên riêng trong JVM, không nhất thiết là pathname mà kernel sử dụng cho AF_UNIX.

`UnixDomainSocketAddress.of(Path)` nhận một `Path` và biểu diễn nó thành địa chỉ. Để tương thích rõ ràng với socket pathname của hệ điều hành, hãy tạo path từ default filesystem và xác định đường dẫn tuyệt đối.

## 7. Giới hạn độ dài pathname phụ thuộc hệ điều hành

Java không định nghĩa một giới hạn số ký tự hoặc số byte chung cho pathname Unix-domain socket. Giới hạn thực tế phụ thuộc cấu trúc địa chỉ socket native, hệ điều hành và cách nền tảng mã hóa pathname.

Ví dụ, các hệ Unix thường có trường pathname kích thước cố định trong cấu trúc `sockaddr_un`, nhưng kích thước và quy tắc kết thúc chuỗi khác nhau giữa Linux, macOS và các hệ thống khác. Tài liệu `ServerSocketChannel` của Java 16 mô tả giới hạn triển khai thường gần và nhìn chung không nhỏ hơn khoảng 100 byte; đây chỉ là thông tin định hướng, không phải bảo đảm cho mọi hệ điều hành hoặc mọi JDK. Không nên lấy một con số từ một nền tảng rồi áp dụng cho mọi môi trường.

Các điểm cần lưu ý:

- Giới hạn thường liên quan đến số byte trong pathname native, không đơn giản là `String.length()`.
- Ký tự Unicode có thể chiếm nhiều byte trong encoding của hệ điều hành.
- Đường dẫn đầy đủ bao gồm cả thư mục cha; tên socket ngắn vẫn có thể vượt giới hạn nếu thư mục quá sâu.
- Thư mục tạm của container hoặc môi trường triển khai có thể có prefix dài.
- Hệ điều hành hoặc provider có thể từ chối bind/connect với lỗi pathname quá dài.

Đừng kiểm tra độ dài bằng `path.toString().length()` rồi xem đó là bằng chứng portable rằng pathname hợp lệ. `String.length()` đếm UTF-16 code unit, trong khi native API có thể áp dụng giới hạn theo byte của encoding nền tảng. Dùng tên ASCII ngắn và thư mục cha ngắn giúp giảm rủi ro, nhưng vẫn phải kiểm tra trên các hệ điều hành mục tiêu.

## 8. Chọn vị trí socket ngắn, ổn định và có quyền phù hợp

Không nên mặc định `java.io.tmpdir` luôn tạo ra pathname đủ ngắn. Trong container hoặc môi trường CI, giá trị này có thể chứa nhiều thành phần thư mục. Hãy cấu hình thư mục socket rõ ràng và cân nhắc tổng độ dài đường dẫn.

Ví dụ lấy thư mục từ cấu hình ứng dụng:

```java
import java.nio.file.Path;

class SocketPathConfig {
    static Path socketPath(String configuredDirectory) {
        return Path.of(configuredDirectory, "svc.sock")
            .toAbsolutePath()
            .normalize();
    }
}
```

Các nguyên tắc triển khai:

- Ưu tiên thư mục chuyên dụng, có tên ngắn và ổn định.
- Bảo đảm user chạy server có quyền tạo socket entry và user chạy client có quyền truy cập theo chính sách của hệ điều hành.
- Giới hạn quyền đọc/ghi trên thư mục cha để tránh tiến trình không tin cậy thay thế socket pathname.
- Không hardcode `/tmp` nếu ứng dụng cần chạy trên nhiều hệ Unix hoặc trong môi trường có quy ước thư mục khác.
- Kiểm tra việc bind và connect trên từng nền tảng được hỗ trợ.

Nếu dùng POSIX permission APIs như `PosixFilePermissions`, hãy coi đó là tùy chọn theo nền tảng; không phải mọi filesystem hoặc hệ điều hành đều hỗ trợ POSIX attributes. Với hệ thống đa nền tảng, dùng cơ chế ACL và quyền triển khai phù hợp với môi trường thực tế.

## 9. Tự động bind và thư mục tạm do JDK chọn

`ServerSocketChannel.bind(null)` cho phép JDK tự chọn một pathname duy nhất trong thư mục tạm của hệ thống. Sau khi bind, có thể lấy địa chỉ thực tế bằng `getLocalAddress()` và ép kiểu thành `UnixDomainSocketAddress` để xem pathname được chọn:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;

class AutomaticallyBoundServer {
    static void open() throws IOException {
        Path socketPath = null;
        try {
            try (ServerSocketChannel server = ServerSocketChannel.open(
                    StandardProtocolFamily.UNIX)) {
                server.bind(null);
                UnixDomainSocketAddress actualAddress =
                    (UnixDomainSocketAddress) server.getLocalAddress();
                socketPath = actualAddress.getPath();

                System.out.println(socketPath);
                // Giữ server mở trong thời gian phục vụ thực tế.
            }
        } finally {
            if (socketPath != null) {
                Files.deleteIfExists(socketPath);
            }
        }
    }
}
```

Socket file được tự động tạo vẫn tồn tại sau khi channel đóng và cần được dọn theo vòng đời ứng dụng. Đường dẫn tự sinh cũng chịu giới hạn pathname của nền tảng; thư mục tạm quá dài có thể khiến bind thất bại.

Có thể cấu hình thư mục dùng cho automatic bind bằng networking property `jdk.net.unixdomain.tmpdir` trong `conf/net.properties`, hoặc ghi đè bằng system property cùng tên khi khởi chạy JVM, ví dụ `-Djdk.net.unixdomain.tmpdir=/run/myapp`. Nếu không xác định được thư mục theo property này, một số nền tảng dùng `java.io.tmpdir` làm fallback. Cấu hình này áp dụng cho địa chỉ tự động được chọn; nó không rút ngắn pathname tường minh mà ứng dụng truyền vào `bind(address)`. Chọn một thư mục ngắn, tồn tại và có quyền phù hợp.

Với client `SocketChannel` kết nối mà không gọi `bind()` trước, local Unix-domain socket được bind ngầm dưới dạng unnamed address; nó không tạo socket pathname. Các thuộc tính thư mục tạm ở trên không ảnh hưởng kiểu bind ngầm này.

## 10. Pathname socket khác với Linux abstract namespace

Linux có khái niệm abstract Unix-domain socket namespace, trong đó địa chỉ không được đại diện bằng một entry pathname thông thường. Đây là đặc tính riêng của Linux và không phải mô hình pathname portable mà `UnixDomainSocketAddress` hướng tới.

API Java chuẩn `UnixDomainSocketAddress` biểu diễn địa chỉ dựa trên `Path`. Không thiết kế ứng dụng đa nền tảng dựa vào giả định rằng mọi hệ điều hành đều hỗ trợ abstract namespace hoặc cách mã hóa đặc biệt để truy cập nó. Nếu ứng dụng cần một tính năng native riêng, cần đánh giá API và khả năng tương thích riêng cho nền tảng đó.

## 11. Kiểm thử đường dẫn và lỗi bind/connect

Khi kiểm thử, nên dùng thư mục tạm do test tạo và xóa sau khi server đã đóng. Không dùng một pathname cố định dùng chung giữa nhiều lần chạy test song song.

Ví dụ tạo path tạm:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class TemporarySocketPath {
    static Path createSocketPath() throws IOException {
        Path directory = Files.createTempDirectory("uds-");
        return directory.resolve("s.sock").toAbsolutePath().normalize();
    }
}
```

Thư mục tạm nên được dọn sau khi đóng server và client. Vì giới hạn pathname khác nhau theo nền tảng, test tích hợp nên chạy trên các OS mục tiêu và kiểm tra lỗi bind/connect thực tế thay vì chỉ test độ dài chuỗi trong JVM.

Các trường hợp cần kiểm tra:

- Server và client dùng cùng pathname tuyệt đối.
- Thư mục cha không tồn tại hoặc tiến trình không có quyền truy cập.
- Pathname đã được một server khác sử dụng.
- Pathname vượt giới hạn của nền tảng.
- Dọn socket file sau khi listener đóng.
- Hai test hoặc hai instance không vô tình dùng chung socket pathname.

Unix-domain socket là tính năng phụ thuộc nền tảng. Test có thể dùng assumption/condition của JUnit để bỏ qua trên môi trường không hỗ trợ, nhưng cần giữ ít nhất một job CI trên mỗi nền tảng mà sản phẩm tuyên bố hỗ trợ.

## 12. Những điểm cần nhớ

- `UnixDomainSocketAddress` biểu diễn địa chỉ pathname; tạo address không tự tạo socket file.
- `Path.of(...)` dùng hệ tệp mặc định; ưu tiên path thuộc default filesystem cho native socket pathname.
- Dùng đường dẫn tuyệt đối đã chuẩn hóa để server và client cùng diễn giải một địa chỉ.
- Tạo thư mục cha và quản lý permission/ACL trước khi bind.
- Chỉ xóa socket pathname mà tiến trình đã bind và sở hữu; không xóa mù quáng một entry đang được server khác dùng.
- Java không quy định độ dài pathname tối đa portable; giới hạn phụ thuộc OS và native encoding.
- Độ dài đường dẫn đầy đủ, số byte và thư mục tạm đều ảnh hưởng khả năng bind/connect.
- Linux abstract namespace là tính năng riêng, không nên xem là pathname portable của Java.
- `bind(null)` tự chọn pathname tạm; `jdk.net.unixdomain.tmpdir` và fallback `java.io.tmpdir` ảnh hưởng thư mục được chọn.
- Client connect không gọi `bind()` trước dùng unnamed local socket, không tạo pathname.
- Kiểm thử trên các hệ điều hành mục tiêu thay vì dựa vào một con số độ dài cố định.

Hãy coi pathname Unix-domain socket là một tài nguyên hệ điều hành có vòng đời và quyền truy cập rõ ràng. Chọn path tuyệt đối từ hệ tệp mặc định, giữ đường dẫn ngắn, quản lý việc bind và cleanup cẩn thận, rồi xác minh giới hạn trên từng nền tảng triển khai.

## Tài liệu tham khảo

- [UnixDomainSocketAddress – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/net/UnixDomainSocketAddress.html)
- [UnixDomainSocketAddress – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/UnixDomainSocketAddress.html)
- [StandardProtocolFamily – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardProtocolFamily.html)
- [ServerSocketChannel – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [SocketChannel – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [ServerSocketChannel – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Networking Properties: Unix domain sockets – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/doc-files/net-properties.html)
- [JEP 380: Unix-Domain Socket Channels](https://openjdk.org/jeps/380)
