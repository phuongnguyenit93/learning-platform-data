# UnixDomainSocketAddress.of với Path hoặc String

**UnixDomainSocketAddress** là kiểu địa chỉ dùng cho Unix-domain socket, được bổ sung trong Java 16 cùng hỗ trợ Unix-domain socket channels. Địa chỉ này đóng gói một đường dẫn file-system mà server dùng để bind và client dùng để connect. Hai factory method **of(Path)** và **of(String)** tạo cùng loại địa chỉ, nhưng khác nhau ở cách biểu diễn đầu vào và những lỗi có thể phát sinh.

Nên dùng **of(Path)** khi chương trình đã làm việc với **Path**, cần ghép thư mục và tên socket hoặc muốn chuẩn hóa đường dẫn trước khi tạo địa chỉ. Dùng **of(String)** khi đường dẫn đến từ cấu hình dạng chuỗi. Cả hai đều chỉ tạo đối tượng địa chỉ; chúng không tự tạo socket file, không mở channel và không xác nhận server đang tồn tại.

## 1. UnixDomainSocketAddress biểu diễn điều gì?

Unix-domain socket hỗ trợ giao tiếp giữa các tiến trình trên cùng host. Khác với TCP socket thường được định danh bằng địa chỉ IP và port, Unix-domain socket được định danh bằng một filesystem pathname.

Ví dụ một ứng dụng có thể dùng socket path:

~~~text
/run/order-service/orders.sock
~~~

Server bind socket vào path này. Client dùng cùng path để kết nối tới server. Path phải được hiểu trong filesystem của máy đang chạy hai tiến trình.

Trong Java, kiểu địa chỉ là:

~~~java
java.net.UnixDomainSocketAddress
~~~

Đây là subclass của **SocketAddress**, được giới thiệu từ Java 16. Nó cung cấp:

- **of(String pathname):** tạo địa chỉ từ chuỗi đường dẫn.
- **of(Path path):** tạo địa chỉ từ Path.
- **getPath():** lấy lại Path được địa chỉ đóng gói.
- **equals()** và **hashCode():** so sánh địa chỉ dựa trên path.
- **toString():** trả về biểu diễn chuỗi của path.

**UnixDomainSocketAddress** chỉ mô tả địa chỉ. Để thực sự giao tiếp, vẫn cần **ServerSocketChannel** hoặc **SocketChannel** được mở với protocol family **UNIX**.

## 2. Tạo địa chỉ bằng of(String)

Cách đơn giản nhất là truyền trực tiếp path dưới dạng chuỗi:

~~~java
import java.net.UnixDomainSocketAddress;

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of("/run/order-service/orders.sock");
~~~

Chuỗi được chuyển thành **Path** bằng filesystem mặc định của JVM. API ném:

- **NullPointerException** nếu pathname là null.
- **InvalidPathException** nếu chuỗi không thể chuyển thành một Path hợp lệ theo filesystem mặc định.

**of(String)** phù hợp khi path được đọc từ file cấu hình hoặc biến môi trường:

~~~java
String configuredPath = System.getenv("ORDER_SOCKET_PATH");

if (configuredPath == null || configuredPath.isBlank()) {
    throw new IllegalStateException("ORDER_SOCKET_PATH is required");
}

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(configuredPath);
~~~

Việc kiểm tra cấu hình rỗng ở ví dụ này là chính sách của ứng dụng. Bản thân API cho phép pathname rỗng, nên không nên nhầm quy tắc cấu hình của ứng dụng với điều kiện bắt buộc của factory method.

Không nên ghép chuỗi đường dẫn bằng cách nối dấu slash hoặc backslash thủ công. Nếu cần ghép các thành phần, hãy dùng **Path** để filesystem mặc định xử lý dấu phân cách và quy tắc đường dẫn.

## 3. Tạo địa chỉ bằng of(Path)

Khi đã có **Path**, truyền trực tiếp đối tượng đó:

~~~java
import java.net.UnixDomainSocketAddress;
import java.nio.file.Path;

Path socketPath =
    Path.of("/run/order-service", "orders.sock");

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(socketPath);
~~~

**Path.of(...)** là cách tạo Path hiện đại từ Java 11. Dạng nhiều thành phần giúp ghép thư mục và tên file mà không phải tự xử lý separator.

Dùng **of(Path)** hữu ích khi ứng dụng cần xử lý path trước:

~~~java
Path socketPath = Path.of(
    System.getProperty("user.dir"),
    "run",
    "orders.sock"
);

Path normalizedPath = socketPath.toAbsolutePath().normalize();

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(normalizedPath);
~~~

Trong ví dụ:

- **toAbsolutePath()** chuyển path tương đối thành path tuyệt đối dựa trên working directory hiện tại.
- **normalize()** loại bỏ các thành phần dư thừa theo quy tắc của filesystem, chẳng hạn dấu chấm và một số cặp tên với dấu chấm kép.
- **of(Path)** đóng gói path đã chuẩn bị thành địa chỉ socket.

**normalize()** là xử lý cú pháp path, không truy cập filesystem và không xác nhận file hoặc thư mục tồn tại. **toAbsolutePath()** cũng không tạo thư mục. Nếu ứng dụng cần thư mục cha, hãy tạo và kiểm tra thư mục riêng trước khi bind.

### Yêu cầu về filesystem của Path

**Path** truyền vào **of(Path)** phải thuộc **system-default file system**. Nếu path đến từ một filesystem provider khác, chẳng hạn một filesystem trong ZIP, factory method ném **IllegalArgumentException**.

Ví dụ, không thể lấy path từ ZIP filesystem rồi truyền thẳng vào địa chỉ Unix socket:

~~~java
// Path từ một filesystem provider khác không phù hợp
// UnixDomainSocketAddress.of(pathInsideZip);
~~~

Lý do là Unix-domain socket gắn với filesystem của hệ điều hành, không phải một đường dẫn ảo trong provider tùy chỉnh.

Nếu path được tạo bằng **Path.of(...)** hoặc **FileSystems.getDefault().getPath(...)**, nó thuộc filesystem mặc định và đáp ứng yêu cầu này.

## 4. So sánh hai overload

| Tiêu chí | of(String) | of(Path) |
| --- | --- | --- |
| Đầu vào | Chuỗi pathname | Đối tượng Path |
| Chuyển đổi path | Factory chuyển chuỗi thành Path | Dùng path đã có |
| Kiểm tra null | NullPointerException | NullPointerException |
| Lỗi riêng | InvalidPathException nếu chuỗi không hợp lệ | IllegalArgumentException nếu Path không thuộc filesystem mặc định |
| Phù hợp khi | Đọc path từ config hoặc input chuỗi | Ghép, chuẩn hóa và quản lý path bằng NIO |
| Tạo socket file | Không | Không |
| Kết nối hoặc bind | Không | Không |

Hai overload tạo cùng loại **UnixDomainSocketAddress**. Chọn overload theo dạng dữ liệu mà chương trình đang có, không phải vì một overload tạo ra loại socket khác hoặc có hiệu năng giao tiếp khác.

Ví dụ cùng một path:

~~~java
Path path = Path.of("/run/order-service/orders.sock");

UnixDomainSocketAddress fromPath =
    UnixDomainSocketAddress.of(path);

UnixDomainSocketAddress fromString =
    UnixDomainSocketAddress.of(path.toString());

System.out.println(fromPath.equals(fromString)); // true
~~~

Hai địa chỉ bằng nhau khi path mà chúng đóng gói bằng nhau theo quy tắc **Path.equals()**. Đây là so sánh path, không phải kiểm tra hai tên có chắc chắn trỏ tới cùng một filesystem object sau khi xét symbolic link hay không.

## 5. Path tương đối và tuyệt đối

Cả hai overload đều có thể tạo địa chỉ từ path tương đối. Tuy nhiên, với service chạy lâu dài, path tương đối dễ gây nhầm lẫn vì nó phụ thuộc working directory của process.

Ví dụ:

~~~java
UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of("run/orders.sock");
~~~

Nếu server và client được khởi chạy từ hai working directory khác nhau, chuỗi giống nhau có thể được diễn giải thành hai vị trí khác nhau. Kết nối sẽ không đi tới socket file mà server đã bind.

Đối với cấu hình service, thường nên dùng path tuyệt đối hoặc tạo path tuyệt đối từ một thư mục cấu hình đã xác định:

~~~java
Path socketPath = Path.of(
    System.getProperty("user.dir"),
    "run",
    "orders.sock"
).toAbsolutePath().normalize();

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(socketPath);
~~~

Cần nhớ **user.dir** phản ánh working directory của process. Nếu môi trường chạy thay đổi thư mục làm việc, kết quả cũng có thể thay đổi. Trong production, nên cấu hình rõ thư mục socket thay vì dựa vào vị trí khởi chạy ngẫu nhiên.

Không gọi **toRealPath()** chỉ để tạo địa chỉ cho socket chưa được bind: phương thức đó yêu cầu path tồn tại. Với socket file sẽ được tạo khi bind, hãy chuẩn bị thư mục cha và dùng **toAbsolutePath().normalize()** nếu cần.

## 6. Đường dẫn rỗng và unnamed address

API cho phép pathname rỗng:

~~~java
UnixDomainSocketAddress unnamed =
    UnixDomainSocketAddress.of("");
~~~

Một **UnixDomainSocketAddress** có path rỗng biểu diễn địa chỉ unnamed. Đây không phải tên socket file thông thường để server và client cùng cấu hình kết nối.

Trong channel API, socket client được bind ngầm khi connect có thể có local address unnamed. Với server, gọi **bind(null)** yêu cầu hệ thống tự gán một địa chỉ socket; có thể lấy địa chỉ đã gán qua **getLocalAddress()**.

Ví dụ:

~~~java
try (var server =
         java.nio.channels.ServerSocketChannel.open(
             java.net.StandardProtocolFamily.UNIX)) {

    server.bind(null);

    UnixDomainSocketAddress assigned =
        (UnixDomainSocketAddress) server.getLocalAddress();

    System.out.println(assigned.getPath());
}
~~~

Trường hợp tự động gán địa chỉ hữu ích khi ứng dụng không cần công bố một pathname cố định. Nếu client khác cần kết nối, ứng dụng phải cung cấp path được gán cho client theo một cơ chế phù hợp.

Không thay **bind(null)** bằng cách mặc định truyền **UnixDomainSocketAddress.of("")** cho server. Hãy dùng đúng cơ chế bind tự động được mô tả trong **ServerSocketChannel**.

## 7. Dùng địa chỉ tạo từ Path để bind server

Ví dụ sau tạo địa chỉ bằng **Path** và bind server channel:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Path;

public class UnixServer {
    public static void main(String[] args) throws IOException {
        Path socketPath =
            Path.of("/run/order-service/orders.sock");

        UnixDomainSocketAddress address =
            UnixDomainSocketAddress.of(socketPath);

        try (ServerSocketChannel server =
                 ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

            server.bind(address);
            System.out.println("Listening at " + address);

            try (var client = server.accept()) {
                // Đọc và ghi dữ liệu qua client channel.
            }
        }
    }
}
~~~

Các bước chính:

1. Chọn filesystem path dành cho socket.
2. Tạo **UnixDomainSocketAddress** từ path.
3. Mở **ServerSocketChannel** với **StandardProtocolFamily.UNIX**.
4. Gọi **bind(address)** để gắn socket với pathname.
5. Gọi **accept()** để nhận kết nối.

Thư mục cha phải tồn tại và process phải có quyền phù hợp để tạo socket file. Nếu path đã được một socket khác sử dụng hoặc hệ điều hành từ chối thao tác, **bind** có thể thất bại với **IOException**.

Việc tạo **UnixDomainSocketAddress** thành công không bảo đảm bước bind sẽ thành công. Factory method không kiểm tra quyền filesystem, path đã được dùng hay khả năng hỗ trợ của nền tảng.

## 8. Dùng địa chỉ tạo từ String để connect client

Client có thể nhận pathname từ cấu hình và tạo địa chỉ bằng **of(String)**:

~~~java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;

public class UnixClient {
    public static void main(String[] args) throws IOException {
        String socketName = "/run/order-service/orders.sock";

        UnixDomainSocketAddress address =
            UnixDomainSocketAddress.of(socketName);

        try (SocketChannel client =
                 SocketChannel.open(StandardProtocolFamily.UNIX)) {

            client.connect(address);

            // Gửi và nhận dữ liệu qua client channel.
        }
    }
}
~~~

**SocketChannel** phải được mở với protocol family **UNIX** để làm việc với Unix-domain socket. **connect(address)** thực hiện kết nối tới socket server đang lắng nghe tại path đó.

Nếu pathname không có socket server tương ứng, path sai hoặc quyền truy cập không phù hợp, thao tác connect có thể ném **IOException**. Factory method chỉ kiểm tra việc chuyển đổi chuỗi thành path, không kiểm tra server có đang lắng nghe hay không.

Có thể dùng **SocketChannel.open(address)** để mở channel và kết nối trực tiếp tới địa chỉ. Khi truyền **UnixDomainSocketAddress**, API thực hiện theo protocol family **UNIX**. Dạng mở channel tường minh như ví dụ trên giúp người đọc thấy rõ loại socket đang sử dụng.

## 9. Lấy lại Path và so sánh địa chỉ

Sau khi tạo địa chỉ, dùng **getPath()** để lấy path đã đóng gói:

~~~java
Path path = Path.of("/run/order-service/orders.sock");

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(path);

Path storedPath = address.getPath();

System.out.println(storedPath);
System.out.println(address);
~~~

**getPath()** trả về path của địa chỉ. **toString()** trả về biểu diễn chuỗi của path; nếu địa chỉ unnamed, chuỗi có thể rỗng.

Có thể so sánh hai địa chỉ:

~~~java
UnixDomainSocketAddress first =
    UnixDomainSocketAddress.of("/run/order-service/orders.sock");

UnixDomainSocketAddress second =
    UnixDomainSocketAddress.of(
        Path.of("/run/order-service", "orders.sock")
    );

if (first.equals(second)) {
    System.out.println("Same path representation");
}
~~~

**equals()** so sánh trường path. Không nên dùng phép so sánh này để kiểm tra socket server có tồn tại, đã bind hay có thể connect hay không. Muốn kiểm tra trạng thái kết nối, phải thực hiện thao tác channel tương ứng.

## 10. Giới hạn độ dài và vòng đời socket file

Độ dài pathname Unix-domain socket bị giới hạn bởi hệ điều hành và implementation. Giới hạn thường xấp xỉ 100 byte nhưng thay đổi theo nền tảng. Giới hạn này được kiểm tra khi channel bind, không phải khi gọi **UnixDomainSocketAddress.of(...)**.

Vì giới hạn tính theo byte và phụ thuộc hệ thống, không nên coi một số lượng ký tự cố định là hợp lệ trên mọi nền tảng. Path càng ngắn càng dễ triển khai giữa các môi trường khác nhau.

Khi server bind vào một Unix-domain socket pathname, hệ điều hành tạo socket file tương ứng. File này vẫn tồn tại sau khi channel đóng; trước khi bind lại cùng tên, cần xóa socket file cũ.

Ví dụ cleanup sau khi server đã dừng:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

Path socketPath = Path.of("/run/order-service/orders.sock");

// Chỉ xóa sau khi xác nhận socket thuộc instance đã dừng.
Files.deleteIfExists(socketPath);
~~~

Không xóa một pathname đang được server khác sử dụng. Trong ứng dụng thật, cleanup cần gắn với quyền sở hữu socket file và quy trình shutdown. Tránh xóa mù một path cấu hình có thể thuộc process khác.

## 11. Lỗi thường gặp khi tạo và sử dụng địa chỉ

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| NullPointerException | Truyền null cho of(String) hoặc of(Path) | Kiểm tra cấu hình trước khi tạo địa chỉ |
| InvalidPathException | Chuỗi không hợp lệ theo filesystem mặc định | Kiểm tra path đầu vào và separator |
| IllegalArgumentException | Path thuộc filesystem provider không phải mặc định | Tạo Path bằng filesystem mặc định |
| Tạo address thành công nhưng bind thất bại | Thư mục cha không tồn tại, quyền không đủ, path đã được dùng hoặc path quá dài | Kiểm tra filesystem, quyền, socket cũ và giới hạn nền tảng |
| Client không connect được | Sai path, server chưa bind hoặc quyền truy cập không phù hợp | Xác minh server, path tuyệt đối và quyền filesystem |
| Bind lại cùng path thất bại sau khi server đóng | Socket file cũ còn tồn tại | Xóa socket file cũ khi chắc chắn instance sở hữu đã dừng |
| Server và client dùng cùng chuỗi nhưng không gặp nhau | Working directory khác nhau khiến path tương đối được diễn giải khác | Dùng path tuyệt đối đã cấu hình thống nhất |
| Nền tảng không hỗ trợ UNIX protocol family | Provider hoặc hệ điều hành không hỗ trợ Unix-domain channel | Kiểm tra hỗ trợ runtime và xử lý UnsupportedOperationException |

## 12. Nên chọn overload nào?

Dùng **of(String)** khi giá trị đầu vào vốn là chuỗi, ví dụ cấu hình môi trường:

~~~java
UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(configuredSocketPath);
~~~

Dùng **of(Path)** khi chương trình cần ghép, kiểm tra hoặc chuẩn hóa path bằng NIO:

~~~java
Path socketPath = socketDirectory.resolve("orders.sock")
    .toAbsolutePath()
    .normalize();

UnixDomainSocketAddress address =
    UnixDomainSocketAddress.of(socketPath);
~~~

Trong ứng dụng có nhiều thành phần cùng dùng một socket, nên tạo **Path** một lần ở tầng cấu hình, xác định path tuyệt đối rồi truyền **UnixDomainSocketAddress** hoặc **Path** tới các thành phần cần dùng. Điều này giúp tránh việc server và client tự diễn giải chuỗi khác nhau.

Không có khác biệt về loại địa chỉ hay giao thức giữa hai overload. Sự khác biệt chỉ nằm ở kiểu dữ liệu đầu vào và các điều kiện kiểm tra tương ứng.

## 13. Kết luận

**UnixDomainSocketAddress.of(String)** tạo địa chỉ từ chuỗi pathname, phù hợp với path đến từ cấu hình. **UnixDomainSocketAddress.of(Path)** dùng khi chương trình đã quản lý đường dẫn bằng NIO và cần ghép hoặc chuẩn hóa path. Cả hai đều có từ Java 16 và tạo đối tượng địa chỉ cho Unix-domain socket.

Hãy nhớ **of(Path)** chỉ nhận path thuộc filesystem mặc định; **of(String)** có thể ném **InvalidPathException** nếu chuỗi không hợp lệ. Path rỗng biểu diễn địa chỉ unnamed, path tương đối phụ thuộc working directory và giới hạn độ dài chỉ được xác minh khi bind. Tạo địa chỉ không tạo socket file hay kết nối tới server. Sau khi tạo, cần dùng channel với protocol family **UNIX** để bind hoặc connect, đồng thời quản lý quyền truy cập và vòng đời socket file.

## Tài liệu tham khảo

- [UnixDomainSocketAddress — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/net/UnixDomainSocketAddress.html)
- [UnixDomainSocketAddress — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/UnixDomainSocketAddress.html)
- [JEP 380: Unix-Domain Socket Channels](https://openjdk.org/jeps/380)
- [ServerSocketChannel — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [SocketChannel — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [java.nio.channels — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/package-summary.html)
- [Path — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/file/Path.html)

