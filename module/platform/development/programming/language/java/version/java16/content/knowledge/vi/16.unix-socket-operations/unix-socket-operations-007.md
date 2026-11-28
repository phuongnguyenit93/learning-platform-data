# Ứng phó UnsupportedOperationException trên runtime hoặc nền tảng thiếu hỗ trợ

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Vận hành socket  
**Áp dụng:** Java 16 trở lên; ví dụ dùng Unix-domain socket API chuẩn và phương án TCP loopback khi cần tương thích nền tảng.

Java 16 chuẩn hóa Unix-domain socket channels trong Java NIO qua `StandardProtocolFamily.UNIX`, `UnixDomainSocketAddress`, `SocketChannel` và `ServerSocketChannel`. API chuẩn giúp ứng dụng dùng cùng mô hình channel trên các hệ điều hành có hỗ trợ, nhưng không bảo đảm mọi runtime, provider hoặc nền tảng đều triển khai family này.

Khi provider không hỗ trợ protocol family được yêu cầu, thao tác mở channel có thể ném `UnsupportedOperationException`. Đây là tín hiệu về khả năng của provider/runtime. Nó khác với lỗi pathname, quyền filesystem hoặc endpoint đang được sử dụng.

Ứng dụng cần phân biệt ba câu hỏi:

1. **Runtime có API Java 16 không?** Các lớp và hằng số Unix-domain socket được đưa vào Java SE từ Java 16.
2. **Channel provider có hỗ trợ `StandardProtocolFamily.UNIX` không?** Có thể kiểm tra bằng cách mở channel với family này.
3. **Pathname và môi trường triển khai có cho phép bind/connect không?** Việc này còn phụ thuộc filesystem, quyền, namespace và trạng thái endpoint.

Không dùng `os.name` để đoán khả năng. Hãy kiểm tra capability thực tế và chỉ fallback khi đúng là transport không được hỗ trợ.

## 1. API Unix-domain socket có từ Java 16

Các API chuẩn liên quan:

| API | Vai trò |
| --- | --- |
| `StandardProtocolFamily.UNIX` | Chọn protocol family Unix-domain |
| `UnixDomainSocketAddress` | Biểu diễn địa chỉ socket theo pathname |
| `ServerSocketChannel.open(UNIX)` | Mở server channel cho Unix-domain socket |
| `SocketChannel.open(UNIX)` | Mở client channel cho Unix-domain socket |
| `Selector` và `SelectionKey` | Theo dõi readiness của channel non-blocking |

Ví dụ mở server channel:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.nio.channels.ServerSocketChannel;

static ServerSocketChannel openUnixServer() throws IOException {
    return ServerSocketChannel.open(StandardProtocolFamily.UNIX);
}
```

Nếu ứng dụng được biên dịch và chạy trên Java 16 trở lên, các kiểu API này có sẵn trong Java SE. Tuy nhiên, channel provider vẫn có thể không hỗ trợ Unix-domain socket trên runtime hoặc nền tảng cụ thể.

## 2. Hiểu đúng UnsupportedOperationException

`ServerSocketChannel.open(StandardProtocolFamily.UNIX)` và `SocketChannel.open(StandardProtocolFamily.UNIX)` có thể ném `UnsupportedOperationException` nếu provider không hỗ trợ protocol family được yêu cầu.

Ví dụ:

```java
try (ServerSocketChannel server =
         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
    // Provider đã mở được Unix-domain server channel.
} catch (UnsupportedOperationException unsupported) {
    // Provider không hỗ trợ protocol family này.
}
```

Không nên suy luận mọi `UnsupportedOperationException` đều có cùng nguyên nhân. Ví dụ, `Files.setPosixFilePermissions()` có thể ném exception này khi filesystem không hỗ trợ POSIX permissions. Đây là hạn chế của thao tác permission, không chứng minh Unix-domain socket channel không được hỗ trợ.

Phân biệt các nhóm lỗi:

| Lỗi | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| `UnsupportedOperationException` khi mở channel với `UNIX` | Provider không hỗ trợ protocol family | Chọn transport fallback hoặc từ chối khởi động theo yêu cầu sản phẩm |
| `UnsupportedOperationException` khi bind | Provider không hỗ trợ thao tác/family trên môi trường đó | Đóng channel rồi chọn fallback nếu đúng thao tác bind UDS bị unsupported |
| `BindException` | Pathname đang được dùng hoặc bind bị từ chối do xung đột địa chỉ | Kiểm tra listener và ownership; không tự động fallback |
| `ConnectException` | Không kết nối được tới listener | Kiểm tra readiness, pathname và trạng thái server |
| `AccessDeniedException` hoặc `SocketException` | Quyền filesystem/socket bị từ chối tùy thao tác và OS | Sửa owner/group/ACL/policy |
| `NoSuchFileException` | Pathname hoặc thư mục cha không tồn tại khi thao tác filesystem | Tạo runtime directory hoặc sửa cấu hình path |
| `UnsupportedClassVersionError` | Runtime cũ không chạy được bytecode đã biên dịch cho Java mới hơn | Nâng runtime hoặc cung cấp artifact tương thích |

Chỉ dùng `UnsupportedOperationException` để quyết định fallback khi exception phát sinh trực tiếp từ thao tác chọn/mở/bind Unix-domain channel. Không bắt `RuntimeException` chung quanh toàn bộ server lifecycle.

## 3. Kiểm tra capability thay vì đoán hệ điều hành

Có thể kiểm tra provider có mở được server channel Unix-domain hay không mà chưa cần tạo socket file:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.nio.channels.ServerSocketChannel;

static boolean supportsUnixDomainServerChannel() throws IOException {
    try (ServerSocketChannel ignored =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
        return true;
    } catch (UnsupportedOperationException unsupported) {
        return false;
    }
}
```

Lưu ý:

- Probe này kiểm tra khả năng mở channel của provider hiện tại.
- Nó không chứng minh thư mục runtime tồn tại hoặc có quyền bind.
- Nó không kiểm tra quyền client kết nối vào socket file.
- Một lỗi `IOException` khi mở channel không nên tự động bị coi là “không hỗ trợ”; hãy giữ nguyên lỗi để chẩn đoán.
- Nếu provider mở được channel nhưng bind không hỗ trợ, cần xử lý `UnsupportedOperationException` riêng quanh thao tác bind.

Đừng dùng `System.getProperty("os.name")` làm phép kiểm tra duy nhất. Cùng tên hệ điều hành có thể có phiên bản, cấu hình runtime, container và provider khác nhau. Capability probe phản ánh môi trường thực tế của tiến trình hơn.

## 4. Chỉ fallback khi Unix-domain socket thật sự không được hỗ trợ

Một quy tắc quyết định thực tế:

| Kết quả | Fallback sang TCP loopback? | Lý do |
| --- | --- | --- |
| Mở Unix-domain channel ném `UnsupportedOperationException` | Có, nếu sản phẩm cho phép fallback | Provider không hỗ trợ family |
| Bind Unix-domain channel ném `UnsupportedOperationException` | Có, sau khi channel được đóng | Thao tác UDS bị provider báo unsupported |
| Bind ném `BindException` | Không tự động | Có thể server khác đang sở hữu pathname |
| Bind/connect ném lỗi quyền | Không tự động | Fallback sẽ che giấu lỗi cấu hình bảo mật |
| Pathname không tồn tại hoặc sai | Không tự động | Sửa runtime directory/path |
| UDS hoạt động bình thường | Không | Tiếp tục dùng transport đã cấu hình |

Fallback không được biến lỗi cấu hình thành trạng thái “thành công” âm thầm. Ghi log transport được chọn và lý do chuyển đổi, không ghi secret hoặc dữ liệu request.

## 5. Mở Unix-domain server và fallback có kiểm soát

Ví dụ sau chỉ fallback khi provider báo unsupported lúc mở hoặc bind. Các lỗi `IOException` như permission, pathname đã tồn tại hoặc lỗi filesystem sẽ được truyền lên để xử lý đúng nguyên nhân:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Path;

static void startService(Path socketPath) throws IOException {
    ServerSocketChannel server;
    try {
        server = ServerSocketChannel.open(StandardProtocolFamily.UNIX);
    } catch (UnsupportedOperationException unsupported) {
        startLoopbackTcpService();
        return;
    }

    boolean bound = false;
    try (server) {
        try {
            server.bind(UnixDomainSocketAddress.of(socketPath));
            bound = true;
        } catch (UnsupportedOperationException unsupported) {
            // Ra khỏi try-with-resources để đóng channel trước khi fallback.
        }

        if (bound) {
            serveUnixClients(server);
            return;
        }
    }

    startLoopbackTcpService();
}

static void serveUnixClients(ServerSocketChannel server)
        throws IOException {
    // Vòng lặp accept và xử lý client.
}

static void startLoopbackTcpService() throws IOException {
    // Ví dụ TCP loopback ở phần tiếp theo.
}
```

`try-with-resources` bảo đảm channel được đóng trước khi fallback được gọi sau khối resource. `BindException`, `AccessDeniedException` hoặc lỗi I/O khác không bị bắt ở đây nên không bị che giấu.

Trong ứng dụng thực tế, `serveUnixClients()` thường chạy đến khi service shutdown. Nếu server UDS đã bind và phục vụ, không khởi động thêm TCP listener song song trừ khi kiến trúc chủ động yêu cầu hai endpoint.

## 6. TCP loopback là phương án tương thích phổ biến

Nếu UDS không có sẵn, TCP loopback là transport chuẩn Java có thể dùng trên nhiều nền tảng:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.ServerSocketChannel;

static void startLoopbackTcpService() throws IOException {
    try (ServerSocketChannel server = ServerSocketChannel.open()) {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        server.bind(new InetSocketAddress(loopback, 0));

        InetSocketAddress endpoint =
            (InetSocketAddress) server.getLocalAddress();

        publishEndpointSecurely(endpoint);
        serveTcpClients(server);
    }
}

static void publishEndpointSecurely(InetSocketAddress endpoint) {
    // Công bố địa chỉ/port qua service discovery hoặc kênh cấu hình tin cậy.
}

static void serveTcpClients(ServerSocketChannel server)
        throws IOException {
    // Vòng lặp accept và xử lý client.
}
```

Các điểm quan trọng:

- Bind vào `InetAddress.getLoopbackAddress()`, không bind wildcard `0.0.0.0` hoặc `::`.
- Dùng port `0` để hệ điều hành cấp một cổng trống; lấy cổng thực tế qua `getLocalAddress()`.
- Công bố endpoint cho client qua service manager, file cấu hình được bảo vệ hoặc cơ chế discovery tin cậy.
- Client cần biết port và phải xác thực server/client theo protocol.
- Đóng listener khi service shutdown và thu hồi endpoint discovery theo vòng đời tương ứng.

TCP loopback không có cơ chế quyền pathname như Unix socket. Tiến trình cục bộ khác có thể thử kết nối tới cổng loopback; nếu threat model cần phân biệt user, hãy dùng token ngẫu nhiên, xác thực hai chiều hoặc cơ chế authorization ở tầng ứng dụng. Không coi việc bind loopback là xác thực client.

## 7. Không fallback khi lỗi thực chất là permission hoặc cấu hình

Giả sử server bind `/run/myapp/service.sock` nhưng service account không có quyền ghi thư mục. Nếu ứng dụng bắt mọi `IOException` rồi chuyển sang TCP, lỗi triển khai sẽ bị che đi:

- Service có thể chạy trên TCP ngoài ý muốn.
- Client vẫn tìm endpoint cũ và liên tục nhận lỗi kết nối.
- Chính sách bảo mật dự kiến dựa trên owner/group của socket không còn được áp dụng.
- Vận hành khó xác định vì log chỉ cho thấy service “đã start”.

Tương tự, nếu pathname đã thuộc một instance khác, chuyển sang TCP có thể tạo hai instance cùng xử lý một service mà không có điều phối singleton.

Hãy phân biệt rõ:

- **Unsupported capability:** có thể fallback theo chính sách.
- **Permission/configuration error:** sửa cấu hình hoặc dừng startup.
- **Address already in use:** xác minh ownership và trạng thái instance.
- **Transient startup race ở client:** retry connect có giới hạn và deadline.

## 8. Runtime cũ hơn Java 16 là vấn đề tương thích API

Unix-domain socket API chuẩn có từ Java 16. Nếu ứng dụng trực tiếp tham chiếu `UnixDomainSocketAddress` hoặc `StandardProtocolFamily.UNIX`, runtime cũ hơn Java 16 không đáp ứng baseline API.

Phân biệt hai tình huống:

1. **Ứng dụng biên dịch cho Java 16 chạy trên JDK cũ:** runtime có thể từ chối class file trước khi code fallback chạy, thường bằng `UnsupportedClassVersionError`.
2. **Một phần code được biên dịch với bytecode cũ nhưng tham chiếu API Java 16:** khi class đó được nạp hoặc liên kết trên runtime thiếu API, có thể gặp lỗi linkage như `NoClassDefFoundError` hoặc `NoSuchMethodError`.

Đây không phải trường hợp `UnsupportedOperationException` từ provider. `catch (UnsupportedOperationException)` không thể xử lý API không tồn tại trong runtime.

Nếu sản phẩm chỉ hỗ trợ Java 16 trở lên, đặt rõ minimum runtime và build với `--release 16` hoặc baseline mới hơn phù hợp. Nếu cần chạy trên runtime cũ hơn, tách implementation Unix-domain socket khỏi phần code chung và cung cấp implementation TCP tương thích; có thể dùng multi-release JAR nếu quy trình build/release đã quản lý đúng các phiên bản class. Đừng để class chung buộc runtime cũ liên kết trực tiếp tới API Java 16.

## 9. Phân biệt thiếu UDS với thiếu POSIX permissions

Hai capability độc lập:

| Capability | API kiểm tra/thao tác | Nếu không hỗ trợ |
| --- | --- | --- |
| Unix-domain socket channel | `ServerSocketChannel.open(UNIX)` hoặc `SocketChannel.open(UNIX)` | Chọn transport fallback hoặc dừng theo chính sách |
| POSIX file permissions | `Files.setPosixFilePermissions()` / `PosixFileAttributeView` | Dùng cơ chế ACL/permission của OS hoặc service manager; không suy ra UDS cũng thiếu |

Ví dụ filesystem không hỗ trợ POSIX permission API có thể ném `UnsupportedOperationException` khi đặt mode. Nếu UDS channel vẫn hoạt động, ứng dụng có thể tiếp tục dùng socket nhưng phải cấu hình quyền thư mục/socket qua cơ chế triển khai phù hợp.

Không bỏ qua lỗi đặt permission nếu quyền socket là yêu cầu bảo mật bắt buộc. Khi không thể áp dụng chính sách truy cập, dừng startup hoặc dùng một runtime directory được service manager cấu hình sẵn.

## 10. Kiểm tra trong môi trường triển khai thật

Capability probe trong unit test không thay thế việc kiểm tra deployment. Xác minh các điểm sau trong đúng runtime, user và namespace:

1. Phiên bản Java thực tế của process có đáp ứng baseline Java 16 trở lên không?
2. `ServerSocketChannel.open(UNIX)` và `SocketChannel.open(UNIX)` có được provider hỗ trợ không?
3. Bind được vào runtime directory thật không?
4. Client service account có thể connect với owner/group/mode/ACL dự kiến không?
5. Container có nhìn thấy cùng pathname và mount namespace không?
6. Service manager có tạo runtime directory trước khi app bind không?
7. Nếu UDS unsupported, TCP fallback có bind đúng loopback và công bố endpoint an toàn không?
8. Nếu bind thất bại do permission hoặc pathname đang được dùng, ứng dụng có báo lỗi thay vì âm thầm fallback không?

Không chỉ kiểm tra `os.name` hoặc phiên bản JDK. Runtime image, provider, container và filesystem thực tế mới quyết định ứng dụng có thể hoàn tất thao tác hay không.

## 11. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Java 16 chuẩn hóa UDS nghĩa là mọi hệ điều hành/provider đều hỗ trợ. | **Sai** | API chuẩn không bảo đảm mọi provider/platform triển khai protocol family. |
| `UnsupportedOperationException` khi mở `UNIX` là dấu hiệu có thể chọn fallback. | **Đúng** | Đây là tín hiệu provider không hỗ trợ family được yêu cầu. |
| `BindException` cũng có thể coi là UDS không được hỗ trợ. | **Sai** | Thường cần kiểm tra pathname hoặc listener đang sử dụng. |
| Có thể bắt mọi `IOException` rồi fallback sang TCP. | **Sai** | Permission, path và address conflict cần được xử lý đúng nguyên nhân. |
| `os.name` đủ để quyết định có dùng UDS hay không. | **Sai** | Không phản ánh chính xác provider, runtime image, container và filesystem. |
| `UnsupportedOperationException` từ POSIX permission đồng nghĩa UDS không hoạt động. | **Sai** | Hai capability độc lập. |
| Runtime trước Java 16 có thể chạy code API Java 16 chỉ bằng catch UOE. | **Sai** | Có thể lỗi class version hoặc linkage trước khi fallback được gọi. |
| TCP loopback tương đương hoàn toàn quyền filesystem của UDS. | **Sai** | TCP cần endpoint discovery và xác thực/authorization ở tầng ứng dụng. |

## 12. Checklist triển khai fallback

1. Minimum runtime Java 16 trở lên đã được công bố rõ chưa?
2. Có kiểm tra provider bằng cách mở channel với `StandardProtocolFamily.UNIX` không?
3. Có phân biệt lỗi unsupported với `BindException`, permission và pathname error không?
4. `UnsupportedOperationException` chỉ được bắt quanh thao tác UDS có thể unsupported không?
5. Channel đã được đóng trước khi khởi động transport fallback chưa?
6. TCP fallback có bind loopback thay vì wildcard không?
7. Port được công bố qua kênh discovery tin cậy không?
8. TCP fallback có xác thực client và server theo threat model không?
9. Nếu thiếu POSIX permissions, có xử lý riêng capability này không?
10. Runtime cũ hơn Java 16 có implementation tương thích tách biệt không?
11. Log có nêu transport được chọn và lý do fallback không?
12. Deployment test đã chạy trong đúng container/user/filesystem chưa?

**Ghi nhớ:** `UnsupportedOperationException` khi mở Unix-domain channel cho biết provider không hỗ trợ protocol family; hãy kiểm tra capability thay vì đoán theo tên OS. Chỉ fallback khi thao tác UDS thực sự unsupported. Giữ nguyên các lỗi permission, pathname và address conflict để sửa đúng nguyên nhân. Nếu cần transport phổ biến hơn, TCP loopback là phương án chuẩn Java nhưng phải có endpoint discovery và xác thực ở tầng ứng dụng. API UDS có từ Java 16, vì vậy runtime cũ hơn cần một implementation tương thích riêng, không thể giải quyết bằng catch UOE.

## Tài liệu chính thức

- [JEP 380 — Unix-Domain Socket Channels, Java 16](https://openjdk.org/jeps/380).
- [Java SE 26 API — `StandardProtocolFamily.UNIX`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardProtocolFamily.html).
- [Java SE 26 API — `ServerSocketChannel.open(ProtocolFamily)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html#open(java.net.ProtocolFamily)).
- [Java SE 26 API — `SocketChannel.open(ProtocolFamily)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html#open(java.net.ProtocolFamily)).
- [Java SE 26 API — `UnixDomainSocketAddress`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/UnixDomainSocketAddress.html).
- [Java SE 26 API — `UnsupportedOperationException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/UnsupportedOperationException.html).
- [Java SE 26 API — `Files.setPosixFilePermissions`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#setPosixFilePermissions(java.nio.file.Path,java.util.Set)).
- [Java SE 26 API — `InetAddress.getLoopbackAddress`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetAddress.html#getLoopbackAddress()).
