# StandardProtocolFamily.UNIX và khả năng hỗ trợ của hệ điều hành

> **Chương:** Unix-domain socket  
> **Học phần:** `JAVA_VERSION_JAVA16` — khám phá những cải tiến từ Java 16 vẫn hữu ích trong Java hiện đại, cùng cách áp dụng API chuẩn một cách ổn định. Bài này giải thích sự khác nhau giữa việc JDK có API UNIX và việc runtime, JDK provider, hệ điều hành cùng môi trường triển khai thực sự hỗ trợ Unix-domain socket.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của `StandardProtocolFamily.UNIX` trong Java NIO.
- Phân biệt API có sẵn khi biên dịch với khả năng hỗ trợ tại runtime.
- Hiểu quan hệ giữa JDK provider, hệ điều hành, filesystem và container.
- Nhận diện `UnsupportedOperationException`, `IOException` và lỗi quyền truy cập.
- Kiểm tra khả năng bind và connect bằng một socket path thử nghiệm.
- Thiết kế kiểm thử tích hợp trên các hệ điều hành và JDK mục tiêu.
- Đưa ra quyết định fallback khi UDS không khả dụng.

## 1. StandardProtocolFamily.UNIX là gì?

`StandardProtocolFamily` là enum trong package `java.net` mô tả các protocol family chuẩn mà channel mạng có thể sử dụng. Từ Java 16, enum có thêm hằng số:

```java
StandardProtocolFamily.UNIX
```

Hằng số này yêu cầu NIO channel sử dụng Unix-domain socket. Nó đi cùng các API:

| API | Vai trò |
| --- | --- |
| `StandardProtocolFamily.UNIX` | Chọn protocol family UNIX |
| `UnixDomainSocketAddress` | Biểu diễn địa chỉ UDS bằng `Path` |
| `ServerSocketChannel.open(ProtocolFamily)` | Mở server channel theo family được chọn |
| `SocketChannel.open(ProtocolFamily)` | Mở client channel theo family được chọn |
| `bind(...)` | Gắn server channel vào socket path |
| `connect(...)` | Kết nối client đến socket path |

Ví dụ mở channel:

```java
ServerSocketChannel server =
        ServerSocketChannel.open(StandardProtocolFamily.UNIX);

SocketChannel client =
        SocketChannel.open(StandardProtocolFamily.UNIX);
```

`StandardProtocolFamily.UNIX` là API chuẩn được hoàn thiện trong Java 16 qua JEP 380. Đây không phải preview feature và không cần bật cờ preview khi biên dịch hoặc chạy.

Ứng dụng cần compile và chạy trên Java 16 trở lên để tham chiếu các API này. Nếu biên dịch với tùy chọn --release thấp hơn 16, compiler không thể tìm thấy các lớp và hằng số được bổ sung trong Java 16.

## 2. API tồn tại không có nghĩa runtime chắc chắn hỗ trợ

Cần phân biệt ba lớp điều kiện:

1. **Compile-time API:** JDK dùng để biên dịch có khai báo `StandardProtocolFamily.UNIX` và các lớp UDS.
2. **NIO provider:** provider được runtime sử dụng có triển khai mở channel cho protocol family UNIX hay không.
3. **Môi trường hệ điều hành:** OS, phiên bản OS, filesystem, quyền truy cập và namespace có cho phép tạo và sử dụng socket path hay không.

Vì vậy, một chương trình có thể biên dịch thành công nhưng vẫn thất bại khi mở hoặc bind channel ở môi trường đích.

Ví dụ:

```java
ServerSocketChannel server =
        ServerSocketChannel.open(StandardProtocolFamily.UNIX);
```

Nếu provider không hỗ trợ family này, thao tác có thể ném `UnsupportedOperationException`. Nếu channel mở được nhưng thư mục không có quyền ghi, socket path quá dài hoặc path đã được sử dụng, thao tác bind có thể thất bại bằng một ngoại lệ I/O phù hợp.

Không nên chỉ kiểm tra phiên bản Java hoặc tên hệ điều hành rồi kết luận UDS chắc chắn dùng được. Hãy kiểm tra đúng thao tác mà ứng dụng cần thực hiện trong môi trường triển khai.

## 3. Vai trò của JDK provider và SelectorProvider

Các phương thức mở channel của NIO được chuyển đến provider. Provider mặc định của JDK thường cung cấp triển khai tương ứng với hệ điều hành, nhưng khả năng hỗ trợ một protocol family vẫn phụ thuộc provider và runtime thực tế.

Các lệnh mở UDS:

```java
ServerSocketChannel.open(StandardProtocolFamily.UNIX);
SocketChannel.open(StandardProtocolFamily.UNIX);
```

có thể thất bại nếu provider không hỗ trợ family UNIX.

Một số điểm cần nhớ:

- `StandardProtocolFamily.UNIX` có mặt trong API Java 16 trở lên.
- Việc enum có hằng số UNIX không chứng minh provider đã triển khai channel tương ứng.
- Một provider thay thế có thể có mức hỗ trợ khác provider mặc định.
- Khả năng mở server channel và client channel nên được kiểm tra trên đúng JDK sẽ chạy ứng dụng.
- Nếu ứng dụng dùng `Selector`, hãy kiểm thử cả thao tác đăng ký channel và mô hình non-blocking mà ứng dụng thực sự sử dụng.

Không cần gọi API nội bộ của JDK để xác định provider. Cách kiểm tra có ý nghĩa nhất là thử mở và sử dụng channel qua API công khai.

## 4. Hệ điều hành quyết định khả năng tạo socket path

Unix-domain socket là tính năng của hệ điều hành. Linux, macOS và nhiều hệ thống Unix-like hỗ trợ UDS từ lâu. Windows hiện đại cũng có hỗ trợ AF_UNIX, nhưng khả năng cụ thể phụ thuộc phiên bản hệ điều hành và JDK đang chạy.

Khi đọc tài liệu Windows, hãy đối chiếu đúng bản phát hành JDK. Ghi chú phát hành Oracle JDK 16 nêu một giới hạn cụ thể: UDS bị tắt trên Windows Server 2019 trong bản JDK 16 ban đầu; chức năng được hỗ trợ trên Windows có build number từ 18362, gồm Windows 10 version 1903 trở lên. Ghi chú này cũng cho biết vấn đề sẽ được xử lý trong JDK 17 và một bản cập nhật JDK 16 sau đó. Đây là giới hạn của các bản phát hành cụ thể, không phải kết luận rằng Windows Server 2019 hiện nay không hỗ trợ UDS. Hãy kiểm tra release notes của đúng JDK đang triển khai.

Không nên viết logic kiểu:

```java
if (System.getProperty("os.name").contains("Linux")) {
    // Giả định UDS luôn hoạt động.
}
```

Tên OS chỉ là thông tin nhận diện tổng quát. Nó không xác nhận:

- Phiên bản OS có hỗ trợ tính năng cần thiết.
- JDK provider có triển khai protocol family UNIX.
- Thư mục runtime có tồn tại và có quyền ghi.
- Socket path có nằm trong giới hạn của hệ điều hành.
- Container có nhìn thấy đúng filesystem namespace.
- Chính sách bảo mật của máy có cho phép bind và connect.

Trên Windows, đừng nhầm Unix-domain socket với Windows named pipe. Đây là các cơ chế endpoint khác nhau. API `UnixDomainSocketAddress` của Java dùng `Path` và provider xử lý theo khả năng của nền tảng.

## 5. Giới hạn socket path và filesystem

Java biểu diễn địa chỉ UDS bằng `UnixDomainSocketAddress`, được tạo từ `Path`:

```java
Path socketPath = Path.of("/run/my-app/control.sock");

UnixDomainSocketAddress address =
        UnixDomainSocketAddress.of(socketPath);
```

Địa chỉ này là pathname socket trong filesystem namespace. Độ dài path tối đa, cách biểu diễn path và một số quy tắc đặt tên phụ thuộc OS. Java không đưa ra một giới hạn độ dài chung có thể áp dụng cho mọi hệ thống.

Một số nguyên tắc thực tế:

- Dùng path ngắn và tuyệt đối.
- Đặt socket trong thư mục runtime được tạo riêng cho ứng dụng.
- Đảm bảo thư mục cha tồn tại trước khi bind.
- Kiểm tra quyền ghi của process chạy server.
- Tránh thư mục có thể bị user không tin cậy thay thế hoặc tạo symlink.
- Dùng path riêng cho từng instance để tránh xung đột.

Không nên đặt socket path tùy ý trong thư mục làm việc hiện tại. Working directory có thể khác giữa chạy local, service manager, container và môi trường kiểm thử.

## 6. Phân biệt UnsupportedOperationException với lỗi môi trường

Khi kiểm tra hỗ trợ, cần phân biệt lỗi provider với lỗi cấu hình hoặc filesystem.

| Lỗi | Ý nghĩa thường gặp | Cách xử lý |
| --- | --- | --- |
| `UnsupportedOperationException` | Provider không hỗ trợ thao tác hoặc protocol family được yêu cầu | Xem xét UDS không khả dụng trên runtime đó |
| `IOException` | Mở, bind, connect hoặc I/O thất bại vì điều kiện môi trường | Đọc nguyên nhân cụ thể, kiểm tra path, quyền và endpoint |
| `AccessDeniedException` | Process không có quyền thực hiện thao tác filesystem hoặc socket | Sửa quyền thư mục, owner/group hoặc policy |
| `FileAlreadyExistsException` hoặc lỗi bind tương ứng | Socket path đã tồn tại hoặc endpoint bị chiếm | Xác minh stale path và ownership trước khi dọn |
| `InvalidPathException` | Chuỗi path không hợp lệ với filesystem provider | Kiểm tra cấu hình path |
| `SecurityException` | Cơ chế kiểm soát truy cập của runtime chặn thao tác | Kiểm tra policy bảo mật liên quan |

Không nên bắt mọi `IOException` rồi trả về kết luận "OS không hỗ trợ UDS". Một lỗi quyền hoặc path không tồn tại không chứng minh protocol family không được hỗ trợ.

Ngược lại, nếu bắt `UnsupportedOperationException`, hãy ghi rõ thao tác nào không hỗ trợ và giữ nguyên cause để chẩn đoán.

## 7. Kiểm tra bằng cách mở channel

Cách kiểm tra đơn giản nhất là thử mở server channel và client channel:

```java
import java.net.StandardProtocolFamily;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;

public class UdsChannelProbe {

    public static boolean canOpenUnixChannels() {
        try (ServerSocketChannel server =
                     ServerSocketChannel.open(StandardProtocolFamily.UNIX);
             SocketChannel client =
                     SocketChannel.open(StandardProtocolFamily.UNIX)) {
            return true;
        } catch (UnsupportedOperationException ex) {
            return false;
        } catch (java.io.IOException ex) {
            throw new IllegalStateException(
                    "Could not open Unix-domain socket channels",
                    ex
            );
        }
    }
}
```

Probe này kiểm tra provider có mở được hai loại channel hay không. Nó chưa kiểm tra bind, connect hoặc quyền truy cập socket path.

Không nên dùng kết quả true từ probe này như bằng chứng rằng endpoint cấu hình cụ thể chắc chắn hoạt động. Bước bind và connect còn có thể thất bại vì filesystem, path length, permission hoặc namespace.

## 8. Kiểm tra bind và connect trong thư mục runtime

Nếu ứng dụng cần dùng UDS thật, probe có giá trị hơn là tạo socket path thử nghiệm trong thư mục runtime mà service sẽ sử dụng.

Ví dụ sau kiểm tra mở server, bind socket path, mở client, connect và accept:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

public final class UnixSocketSupportCheck {

    private UnixSocketSupportCheck() {
    }

    public static void verify(Path runtimeDirectory) throws IOException {
        Path directory = runtimeDirectory.toAbsolutePath().normalize();

        if (!Files.isDirectory(directory)) {
            throw new IOException(
                    "Runtime path is not an accessible directory: " + directory
            );
        }

        Path socketPath = directory.resolve(
                "uds-probe-" + UUID.randomUUID() + ".sock"
        );

        boolean bound = false;

        try {
            UnixDomainSocketAddress address =
                    UnixDomainSocketAddress.of(socketPath);

            try (ServerSocketChannel server =
                         ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {

                server.bind(address);
                bound = true;

                try (SocketChannel client =
                             SocketChannel.open(StandardProtocolFamily.UNIX)) {

                    client.connect(address);

                    try (SocketChannel accepted = server.accept()) {
                        // Kết nối local đã được thiết lập.
                    }
                }
            }
        } catch (UnsupportedOperationException ex) {
            throw new UnsupportedOperationException(
                    "The runtime provider does not support Unix-domain sockets",
                    ex
            );
        } finally {
            if (bound) {
                Files.deleteIfExists(socketPath);
            }
        }
    }
}
```

Probe này kiểm tra nhiều điều kiện hơn việc chỉ mở channel:

- Provider mở được server và client channel.
- Server bind được vào thư mục runtime đã chọn.
- Client connect được đến địa chỉ UDS.
- Server accept được kết nối.
- Socket path do probe tạo được dọn sau khi channel đóng bình thường.

Nếu `verify` ném `IOException`, hãy đọc cause để xác định đó là quyền truy cập, path, bind hay lỗi I/O. Không tự động đổi sang TCP chỉ vì có một lỗi I/O; lỗi đó có thể sửa được trong cấu hình triển khai.

Hàm nhận thư mục runtime có sẵn và không tự xóa nội dung khác trong thư mục. Nó chỉ tạo một tên probe ngẫu nhiên và xóa path mà chính probe bind thành công.

## 9. Kiểm tra trong ứng dụng và trong môi trường triển khai

Một probe lúc khởi động có thể giúp fail fast trước khi ứng dụng nhận request. Tuy nhiên, kiểm tra lúc khởi động không thay thế integration test trên từng nền tảng mục tiêu.

Nên kiểm tra ít nhất:

1. Mở `ServerSocketChannel` với family UNIX.
2. Bind vào thư mục runtime thật hoặc thư mục test có quyền tương đương.
3. Mở `SocketChannel` và connect đến socket path.
4. Accept kết nối và trao đổi một ít dữ liệu.
5. Đóng channel và xác nhận socket path được dọn theo chính sách.
6. Restart process và kiểm tra stale path.
7. Chạy lại trong container hoặc service manager giống môi trường production.

Kiểm tra bind/connect giúp xác nhận endpoint. Kiểm tra gửi/nhận byte giúp xác nhận giao thức framing, buffer và xử lý I/O của ứng dụng.

Đừng chỉ chạy test trên máy phát triển rồi suy rộng sang mọi môi trường. Một JDK có thể chạy trên Linux developer machine nhưng deployment target dùng Windows, container tối giản hoặc filesystem với quyền khác.

## 10. Khả năng hỗ trợ trong container

Container tạo thêm ranh giới filesystem và namespace. Việc hai process cùng chạy trên một host vật lý không bảo đảm chúng nhìn thấy cùng socket path.

### Hai process trong cùng container

Nếu cùng filesystem namespace và quyền phù hợp, chúng thường có thể dùng chung socket path trong container.

### Hai container khác nhau

Để client trong container này kết nối UDS server trong container khác, socket path cần được chia sẻ qua volume hoặc mount phù hợp. Hai container cũng cần có quyền truy cập tương ứng.

Cần kiểm tra:

- Volume có được mount vào cả hai container không?
- Socket path có giống nhau trong namespace mà mỗi process nhìn thấy không?
- User/group trong hai container có quyền phù hợp không?
- Container runtime có cho phép loại socket file này trên mount đó không?
- Khi server restart, stale socket path được quản lý như thế nào?

Nếu không thể chia sẻ socket path một cách an toàn, hãy cân nhắc TCP qua network namespace/container network thay vì cố dùng cùng một path không nhìn thấy được.

## 11. Quyền truy cập khác nhau giữa các hệ điều hành

Trên hệ thống POSIX, quyền truy cập thường liên quan đến owner, group, mode của thư mục cha và socket file. Quyền thư mục cha đặc biệt quan trọng vì process có thể cần quyền truy cập đường dẫn để tìm endpoint.

Trên Windows, cơ chế quyền và bảo mật filesystem không hoàn toàn giống mô hình owner/group/mode POSIX. Không nên giả định một lệnh chmod hoặc một cấu hình permission sẽ có cùng tác dụng trên mọi OS.

Java NIO cung cấp API path và channel, nhưng việc cấu hình permission chính xác cần theo nền tảng. Hãy:

- Tạo thư mục runtime với quyền tối thiểu cần thiết.
- Kiểm tra owner và ACL trên OS đích.
- Kiểm thử connect từ user được phép và user không được phép.
- Không để user không tin cậy ghi vào thư mục chứa socket.
- Không xem socket path như một cơ chế xác thực danh tính ứng dụng hoàn chỉnh.

UDS không tự mã hóa dữ liệu. Nếu endpoint xử lý lệnh nhạy cảm, vẫn cần xác thực, phân quyền và bảo vệ payload theo threat model.

## 12. Chọn fallback khi UDS không khả dụng

Nếu UDS là yêu cầu bắt buộc, ứng dụng nên dừng khởi động với thông báo rõ khi provider hoặc OS không hỗ trợ. Không nên âm thầm mở TCP listener ngoài dự kiến vì điều đó có thể thay đổi phạm vi truy cập và ranh giới bảo mật.

Nếu ứng dụng hỗ trợ cả UDS và TCP, hãy dùng cấu hình rõ ràng:

```properties
ipc.transport=unix
ipc.unix.path=/run/my-app/control.sock
ipc.tcp.host=127.0.0.1
ipc.tcp.port=7070
```

Policy có thể quy định:

- `unix`: bắt buộc UDS; nếu không khả dụng thì fail fast.
- `tcp-loopback`: dùng TCP loopback theo host/port cấu hình.
- `auto`: chỉ fallback nếu sản phẩm chủ động cho phép, client và server đồng bộ endpoint, và phạm vi bảo mật của TCP đã được chấp thuận.

Không nên chọn `auto` chỉ bằng cách bắt mọi exception. Phải phân biệt provider không hỗ trợ với lỗi cấu hình có thể sửa, như thư mục không có quyền ghi hoặc socket path bị chiếm.

Nếu fallback sang TCP loopback, hãy bind vào loopback address cụ thể, không bind wildcard. Loopback giới hạn listener ở network interface local nhưng không ngăn process khác trên cùng máy kết nối. Nếu endpoint nhạy cảm, vẫn cần xác thực ở tầng ứng dụng.

## 13. Thiết kế capability check có thể quan sát được

Khi ứng dụng cần hỗ trợ nhiều môi trường, hãy biến capability thành thông tin vận hành rõ ràng:

- Transport được cấu hình.
- Provider có mở được channel không.
- Bind/connect có thành công không.
- Thư mục runtime nào được sử dụng.
- Lỗi thuộc nhóm unsupported, permission, path hay I/O.
- Fallback có được cấu hình và thực sự kích hoạt hay không.

Không ghi credential hoặc payload vào log. Socket path có thể được ghi nếu nó không chứa thông tin nhạy cảm và policy vận hành cho phép.

Nên phân biệt hai trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| API unavailable | Provider không triển khai protocol family UNIX |
| Endpoint unavailable | API có thể được hỗ trợ nhưng endpoint cụ thể không thể bind/connect do path, quyền, namespace hoặc xung đột |

Sự phân biệt này giúp đội vận hành sửa đúng nguyên nhân. Một lỗi permission không nên bị báo cáo như thiếu tính năng của JDK.

## 14. Kiểm thử trên nhiều nền tảng

Một ma trận kiểm thử nên phản ánh đúng JDK và OS mà sản phẩm hỗ trợ.

| Môi trường | Kiểm tra |
| --- | --- |
| Linux host | Mở channel, bind, connect, trao đổi dữ liệu và cleanup |
| macOS host | Kiểm tra cùng các thao tác UDS và giới hạn path |
| Windows có hỗ trợ AF_UNIX | Kiểm tra JDK provider, build OS, path và permission thực tế |
| Container cùng mount | Xác nhận hai process nhìn thấy cùng socket path |
| Container namespace riêng | Xác nhận path hoặc network endpoint có thể truy cập theo kiến trúc |
| JDK vendor/version mục tiêu | Kiểm tra provider thực tế, không suy ra từ máy phát triển |

Không nên bỏ qua test chỉ dựa trên tên OS. Nếu một môi trường là mục tiêu bắt buộc của sản phẩm, test tích hợp UDS trên môi trường đó cần là điều kiện phát hành.

Nếu UDS là tính năng tùy chọn, test suite có thể phân loại môi trường không hỗ trợ thành trạng thái skip có lý do; pipeline dành cho nền tảng bắt buộc vẫn phải xác nhận UDS hoạt động.

## 15. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Thấy `StandardProtocolFamily.UNIX` trong JDK rồi giả định mọi OS đều hỗ trợ | Ứng dụng lỗi khi mở channel trên provider không hỗ trợ | Kiểm tra runtime provider và OS mục tiêu |
| Chỉ kiểm tra `os.name` | Bỏ sót phiên bản OS, JDK, filesystem và container | Thử mở, bind và connect qua API công khai |
| Chỉ mở channel rồi kết luận endpoint dùng được | Bỏ sót lỗi path và permission | Probe bind/connect trong thư mục runtime |
| Bắt mọi `IOException` rồi fallback TCP | Che mất lỗi cấu hình có thể sửa và thay đổi bảo mật | Phân loại lỗi; fallback theo policy rõ ràng |
| Coi `UnsupportedOperationException` như lỗi quyền filesystem | Chẩn đoán sai nguyên nhân | Tách lỗi provider khỏi lỗi I/O/permission |
| Dùng path quá dài hoặc phụ thuộc working directory | Bind thất bại ở môi trường khác | Dùng path tuyệt đối, ngắn và có cấu hình |
| Kiểm tra trên host nhưng chạy production trong container | Bỏ qua mount và namespace | Chạy integration test trong container tương ứng |
| Dựa vào permission POSIX trên Windows | Quyền truy cập không như mong đợi | Kiểm tra ACL và hành vi OS thực tế |
| Xóa path cũ vô điều kiện khi probe | Có thể làm gián đoạn endpoint khác | Dùng path ngẫu nhiên và chỉ xóa path do probe sở hữu |
| Chỉ kiểm thử khả năng bind | Không phát hiện lỗi client connect hoặc giao thức | Test cả bind, connect, accept và trao đổi dữ liệu |

## 16. Bài tập tự luyện

### Bài 1: API hay khả năng runtime?

JDK dùng để biên dịch có `StandardProtocolFamily.UNIX`. Có thể kết luận ứng dụng chắc chắn bind được UDS trên máy production không?

**Đáp án:** Không. API có sẵn ở compile-time không chứng minh provider, OS, filesystem và quyền runtime hỗ trợ. Cần thử mở channel và bind/connect trên môi trường mục tiêu.

### Bài 2: Phân biệt lỗi

Một lệnh mở channel ném `UnsupportedOperationException`. Điều đó thường cho biết điều gì?

**Đáp án:** Provider không hỗ trợ protocol family hoặc thao tác được yêu cầu. Cần kiểm tra JDK provider và môi trường chạy. Đây khác với `IOException` do path hoặc quyền.

### Bài 3: Bind thất bại vì permission

Channel mở thành công nhưng bind vào `/run/my-app/control.sock` ném `AccessDeniedException`. Có nên kết luận OS không hỗ trợ UDS không?

**Đáp án:** Không. Đây là lỗi quyền truy cập. Hãy kiểm tra quyền thư mục cha, owner/group hoặc ACL và chạy lại probe trong thư mục runtime có quyền phù hợp.

### Bài 4: Container không nhìn thấy socket

Server bind vào `/run/my-app/control.sock` trong container A. Client container B dùng đúng chuỗi path nhưng connect thất bại. Nguyên nhân có thể là gì?

**Đáp án:** Hai container có filesystem hoặc mount namespace khác nhau. Cần chia sẻ volume/mount chứa socket path và cấp quyền truy cập cho cả hai process.

### Bài 5: Thiết kế fallback

Ứng dụng bắt buộc dùng UDS cho endpoint điều khiển nhạy cảm. Runtime không hỗ trợ UDS. Có nên tự mở TCP loopback không?

**Đáp án:** Không nên tự động thay đổi transport nếu policy chưa cho phép. Hãy fail fast với lỗi rõ ràng. Nếu sản phẩm cho phép TCP fallback, cần cấu hình tường minh, bind loopback cụ thể, đồng bộ endpoint client/server và đánh giá xác thực.

## Ghi nhớ

`StandardProtocolFamily.UNIX` là API chuẩn từ Java 16, nhưng sự hiện diện của API không bảo đảm mọi runtime đều hỗ trợ. Khả năng thực tế phụ thuộc NIO provider, OS, filesystem, quyền truy cập và namespace của container. `UnsupportedOperationException` thường chỉ ra provider không hỗ trợ; `IOException` cần được phân tích theo path, quyền và endpoint. Hãy kiểm tra bằng cách mở channel, bind và connect trong thư mục runtime thực tế, rồi xác nhận trên từng môi trường triển khai. Chỉ fallback sang TCP khi policy cho phép và client/server được đồng bộ endpoint cùng ranh giới bảo mật.

## Tài liệu tham khảo

- [JEP 380 — Unix-Domain Socket Channels](https://openjdk.org/jeps/380).
- [Java API — StandardProtocolFamily](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardProtocolFamily.html).
- [Java API — UnixDomainSocketAddress](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/UnixDomainSocketAddress.html).
- [Java API — ServerSocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html).
- [Java API — SocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html).
- [Java API — UnsupportedOperationException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/UnsupportedOperationException.html).
- [Java API — AccessDeniedException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/AccessDeniedException.html).
- [Oracle JDK 16 Release Notes — Incomplete Support for Unix Domain Sockets in Windows 2019 Server](https://www.oracle.com/java/technologies/javase/16-relnote-issues.html).
