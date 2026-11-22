# Đường dẫn socket cục bộ, quyền truy cập và việc dọn tệp sau khi đóng — Java NIO

**Unix-domain socket** (thường gọi là *local socket* hoặc `AF_UNIX` socket) cho phép **hai tiến trình trên cùng máy** trao đổi dòng byte mà không cần địa chỉ IP và cổng TCP. Với Java 17+, nó được biểu diễn bằng `UnixDomainSocketAddress` và các NIO channel như `ServerSocketChannel`, `SocketChannel`. Một server có thể bind tới **đường dẫn trong hệ thống tệp**, ví dụ `/run/myapp/service.sock`; client kết nối đến đường dẫn đó.

Điểm dễ mắc lỗi nhất là **file socket có vòng đời khác với channel**:

~~~text
ServerSocketChannel.open(UNIX)
       |
       | bind(UnixDomainSocketAddress.of(socketPath))
       v
Socket endpoint đang lắng nghe + node ở socketPath
       |
       | accept() -> SocketChannel cho từng client
       |
       | server.close() / hết try-with-resources
       v
Kernel socket đã đóng; file tại socketPath VẪN CÓ THỂ CÒN
       |
       | Files.deleteIfExists(socketPath) (đúng ownership/thời điểm)
       v
Tên đường dẫn được giải phóng để bind lần sau
~~~

Không nên lẫn **đóng kết nối**, **xóa tên socket trên filesystem**, và **quyền của người dùng truy cập socket**. Chúng là ba trách nhiệm khác nhau. Xóa file quá sớm có thể làm client mới không tìm được service; xóa bừa file có thể xóa socket của tiến trình khác; để file tồn tại sau khi đóng có thể khiến lần khởi động tiếp theo không bind được. Bài học tập trung vào ba vấn đề này trong module **Buffer và channel** của Java Networking.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích `StandardProtocolFamily.UNIX`, `UnixDomainSocketAddress.of(Path)`, `ServerSocketChannel.bind()` và `SocketChannel.connect()`.
- Phân biệt **đường dẫn làm tên endpoint IPC** với **file thường chứa dữ liệu**, địa chỉ IP/port và địa chỉ Unix-domain socket không có tên.
- Chọn đường dẫn **ngắn, tuyệt đối, thuộc filesystem mặc định**, được kiểm soát quyền truy cập và có vòng đời rõ ràng.
- Hiểu quyền trên **thư mục cha** và **socket node** ở Linux/POSIX, khác biệt Windows ACL và giới hạn portability.
- Giải thích vì sao `close()` hoặc `try-with-resources` **không tự unlink** file socket đã bind, kể cả khi server dùng `bind(null)`.
- Viết `try/finally` để đóng channel rồi dọn **đúng đường dẫn do tiến trình sở hữu**, không xóa bừa đường dẫn chưa kiểm chứng.
- Nhận diện stale socket file sau crash, khởi động trùng, path length, `Address already in use`, `Access denied` và các rủi ro symlink/race.
- Chạy chương trình Java 17+ độc lập minh họa kết nối local, trao đổi byte, quan sát file còn sau close, và dọn file an toàn trong thư mục tạm riêng.

## 2. So sánh Unix-domain socket với TCP loopback

| Khía cạnh | TCP loopback | Unix-domain stream socket |
| --- | --- | --- |
| Endpoint | IP/hostname + port, ví dụ `127.0.0.1:8080` | Filesystem path, ví dụ `/run/myapp/service.sock` |
| Protocol family | `INET`/`INET6` | `UNIX` |
| Dùng trong Java NIO | `ServerSocketChannel` / `SocketChannel` | Cùng hai class, nhưng mở với `UNIX` |
| Địa chỉ kết nối | `InetSocketAddress` | `UnixDomainSocketAddress` |
| Giao tiếp | TCP/IP (qua loopback) | IPC stream nội bộ host, không dùng IP routing |
| Bảo vệ | Firewall, bind address, hệ điều hành, giao thức | Parent-directory permissions, socket-node permissions/ACL, peer identity, giao thức |
| Phạm vi | Tùy địa chỉ bind; loopback chỉ host hiện tại | Chỉ máy cục bộ có hỗ trợ AF_UNIX; một path có thể dùng qua shared filesystem namespace/container nếu OS cho phép |
| Xử lý dữ liệu | Byte stream, phải tự framing | Cũng là byte stream, phải tự framing |
| Đóng endpoint server | Giải phóng listener/socket qua API | Đóng channel **không tự xóa tên filesystem** |
| Java support | Có từ lâu | NIO `UNIX` từ **Java 16** (JEP 380); dùng ổn với Java 17+ nếu OS hỗ trợ |

Unix-domain socket có thể giảm overhead cho IPC nội bộ, nhưng không phải giải pháp thay thế tự động cho mọi giao tiếp qua TCP: hai tiến trình phải có cách nhìn thấy cùng đường dẫn trong **filesystem namespace** thích hợp, cần chính sách quyền và phiên bản Java/OS hỗ trợ.

**Giới hạn API quan trọng ở Java 17:** hỗ trợ Unix-domain **stream** qua `ServerSocketChannel` và `SocketChannel`; không dùng `new ServerSocket()` hoặc `new Socket()` thông thường để yêu cầu `UNIX`, và không nhầm với `DatagramChannel` Unix-domain datagrams. Nếu cần truyền datagram AF_UNIX hoặc Linux abstract namespace, phải đọc khả năng riêng của hệ thống/thư viện; JEP 380 không cung cấp những tính năng đó qua API chuẩn này.

## 3. Tạo Unix-domain socket bằng Java 17+

### 3.1. Những API cốt lõi

~~~java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

Path socketPath = Path.of("/run/myapp/service.sock");
UnixDomainSocketAddress address = UnixDomainSocketAddress.of(socketPath);

try (ServerSocketChannel server =
        ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
    server.bind(address);
    try (SocketChannel accepted = server.accept()) {
        // Đọc/ghi trên accepted channel.
    }
} // ServerSocketChannel được đóng, nhưng path cần được dọn riêng.
~~~

Đây là **mảnh code minh họa trong method** (cần `throws IOException` hoặc `catch`); path `/run/myapp/service.sock` phải được tạo trong thư mục tồn tại và có quyền phù hợp. Không copy nguyên ví dụ này để chạy trên Windows vì dạng đường dẫn Unix không tương ứng với Windows. Chương trình hoàn chỉnh, tự tạo đường dẫn phù hợp hệ điều hành, nằm ở phần 9.

- `ServerSocketChannel.open(StandardProtocolFamily.UNIX)` tạo listener-channel cho **Unix-domain stream sockets**.
- `UnixDomainSocketAddress.of(Path)` dùng một `Path` của **default file system** làm địa chỉ. Không phải mọi `Path` từ ZIP filesystem/provider bên thứ ba đều hợp lệ; JDK có thể từ chối.
- `server.bind(address)` gắn tên filesystem với endpoint lắng nghe, **tạo một socket node ở đường dẫn đó**.
- `server.accept()` trả về một `SocketChannel` **kết nối riêng** với client đã đến; server vẫn tiếp tục lắng nghe nếu không đóng.
- `SocketChannel.open(StandardProtocolFamily.UNIX)` tạo client-channel; `client.connect(address)` kết nối đến path đã bind. `SocketChannel.open(address)` cũng có thể suy ra protocol family từ kiểu address.
- `server.close()` dừng listener; `accepted.close()` kết thúc riêng kết nối đã accept; hai loại resource không có cùng vòng đời.

Cú pháp `try-with-resources` đóng channel kể cả khi code ném exception, nhưng **nó chỉ gọi `close()` của channel**, không gọi `Files.delete(...)` cho đường dẫn.

### 3.2. Không có IP/port trên Unix-domain address

~~~java
UnixDomainSocketAddress address =
        UnixDomainSocketAddress.of("/run/myapp/service.sock");
Path path = address.getPath();
~~~

`UnixDomainSocketAddress` kế thừa `SocketAddress` nhưng **không phải** `InetSocketAddress`. Không có `getHost()` hay `getPort()` để gọi. Địa chỉ của socket được xác định bằng tên trong filesystem namespace. Một file có đuôi `.sock` **chỉ là quy ước đặt tên**; tên `service.ipc` cũng được nếu hợp lệ, còn file thường đặt đuôi `.sock` **không tự biến thành socket**.

Cần tránh cách nghĩ “đã có `/tmp/app.sock` thì cứ mở bằng `Files.newInputStream()` để đọc message”. File socket **không phải file dữ liệu được ghi/đọc bằng Files I/O**. Nó là node đặc biệt phục vụ thao tác `bind/connect` qua OS; payload giao tiếp đi qua `SocketChannel.read()/write()`.

### 3.3. Tên rỗng (unnamed) và `bind(null)`

Với client dùng `SocketChannel.open(UNIX)` rồi `connect(address)` mà không `bind` trước, endpoint **cục bộ của client thường là unnamed**, có đường dẫn rỗng và **không có socket file riêng cần dọn**. Đó là hành vi khác server đã bind tới đường dẫn công khai.

Với server:

~~~java
try (ServerSocketChannel server =
        ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
    server.bind(null); // OS/JDK chọn tên tạm riêng cho server
    UnixDomainSocketAddress bound =
        (UnixDomainSocketAddress) server.getLocalAddress();
    Path autoPath = bound.getPath();
    // Cung cấp autoPath cho client qua cơ chế IPC/discovery tin cậy.
    // Đảm bảo dọn autoPath SAU khi server ngừng hoạt động.
}
~~~

Đây là **mảnh code**. Với `ServerSocketChannel.bind(null)` và family `UNIX`, JDK chọn **một đường dẫn tạm duy nhất** trong thư mục được cấu hình. **File tự động này cũng tồn tại sau khi server channel đóng**, nên vẫn cần cleanup. Đừng nhầm **bind(null) của server** với **implicit client bind**: chúng không cho cùng một pathname artifact.

JDK có các tùy chọn `jdk.net.unixdomain.tmpdir` và `java.io.tmpdir`/môi trường OS để chọn nơi tạo đường dẫn tự động, tùy hệ điều hành. Việc tự động đặt tên làm giảm khả năng đụng tên nhưng **không tự thay thế chính sách quyền truy cập, discovery hay dọn file**.

## 4. Đường dẫn socket: những quy tắc vận hành quan trọng

### 4.1. Thư mục phải tồn tại và đúng chủ sở hữu

Giả sử sản phẩm dùng `/run/myapp/service.sock`:

~~~text
/run/
  myapp/             <-- thư mục cha (owner / mode / ACL)
    service.sock      <-- node Unix-domain socket được bind tạo ra
~~~

Một địa chỉ socket cần **đường dẫn hợp lệ trong OS**, và thư mục cha phải tồn tại. `bind` không tự tạo mọi thư mục cha còn thiếu. Khi service chạy dưới user ít quyền, không được mặc định user đó có thể tạo file ở `/run` hay `/var/run`. Cách triển khai hợp lý là để service manager hoặc bước cài đặt tạo thư mục runtime với owner/group và permission đúng.

Phân loại vị trí thường gặp:

- `/run/<service>/...` trên Linux: thích hợp cho socket runtime của daemon, nếu đã có thư mục quản lý quyền thích hợp. Có thể không tồn tại hoặc không writable khi test cá nhân.
- `/tmp/<service>.sock`: dễ thử nghiệm nhưng **nguy hiểm nếu tên cố định trong thư mục chia sẻ**; có thể bị tranh chấp/race hoặc bị xóa bởi cleanup ngoài ý muốn. Chỉ dùng khi biết rõ chính sách và có bảo vệ.
- Thư mục tạm **riêng mới tạo**: tốt cho test; mã có thể tạo folder bằng `Files.createTempDirectory("uds-")`, đặt path bên trong và xóa folder khi test xong.
- Trên Windows: sử dụng `Path` Windows và ACL tương ứng; không giả định POSIX mode, đường dẫn `/run/...` hay lệnh `chmod` hoạt động.

**Khuyến nghị:** dùng đường dẫn tuyệt đối, ngắn, có namespace rõ ràng, thuộc thư mục mà tiến trình kiểm soát. Đường dẫn được ghi trong cấu hình nên xác định owner/rủi ro collision và quy trình restart; không tự “normalize rồi xóa mọi file” khi đầu vào chưa được xác thực.

### 4.2. Giới hạn độ dài path tính bằng byte

Unix-domain pathname được lưu trong buffer của cấu trúc socket address. Tên có giới hạn phụ thuộc OS/JDK; tài liệu Java mô tả **thường khoảng 100 byte**. Linux phổ biến có `sun_path[108]` trong `sockaddr_un`, với chi tiết null termination; hệ điều hành khác có thể ngắn hơn.

Vì vậy:

- `/home/username/very/long/project/path/build/tmp/.../server.sock` dễ vượt giới hạn dù là một đường dẫn file bình thường hợp lệ.
- Ký tự Unicode có thể chiếm **nhiều byte UTF-8**, nên “100 ký tự Unicode” không đồng nghĩa “100 byte tên socket”.
- Thư mục tạm tự tạo từ `java.io.tmpdir` cũng có thể nằm ở path dài, đặc biệt trên Windows CI hoặc thư mục người dùng.
- Khi `bind` hoặc `connect` thất bại với lỗi dạng “Unix domain path too long”, chuyển tới một **đường dẫn ngắn hơn do bạn sở hữu**. Không tự xóa file hay chỉnh permission vì nghĩ lỗi độ dài là permission.
- Không giả định đường dẫn chuẩn hóa theo chuỗi là định danh tuyệt đối duy nhất khi filesystem có symlink, mount namespace hay case-folding.

Để kiểm tra gần đúng số byte trên OS dùng UTF-8, có thể dùng `socketPath.toString().getBytes(StandardCharsets.UTF_8).length`; đó **không** thay thế hợp đồng/bộ đếm native của mọi platform. Cách chắc chắn là giữ path ngắn và thử `bind` trên môi trường thực.

### 4.3. Relative path và filesystem provider

`UnixDomainSocketAddress.of(Path)` yêu cầu `Path` từ **hệ thống tệp mặc định**. Một `Path` lấy từ `FileSystems.newFileSystem(zipPath)` không dùng làm Unix-domain socket address thông thường.

Đường dẫn tương đối khiến hành vi phụ thuộc working directory và cách API/OS chuyển đổi path. Nên chuẩn hóa cấu hình về một path tuyệt đối được kiểm soát, ví dụ:

~~~java
Path socketPath = configuredDirectory
        .toAbsolutePath()
        .normalize()
        .resolve("service.sock");
~~~

Đoạn này là **mã trong phương thức**, với `configuredDirectory` là `Path` đã được cấp quyền/kiểm tra. `normalize()` chỉ xử lý cú pháp path; **không** ngăn symlink, không chứng minh path thuộc đúng thư mục và không thay permission checks. Nếu attacker kiểm soát thư mục cha, có thể xuất hiện race giữa kiểm tra path và `bind/delete`.

## 5. Quyền truy cập: thư mục cha quan trọng không kém socket node

Unix-domain path là một điểm truy cập trong filesystem, nên **OS identity/permissions** ảnh hưởng đến ai có thể tạo hoặc connect.

### 5.1. Trên Linux/POSIX

Theo Linux `unix(7)`:

- Để tạo node socket ở một thư mục, tiến trình cần quyền **write** và **search/execute** trên thư mục cha (và khả năng đi qua các thư mục tổ tiên theo quy tắc OS).
- Trên Linux, kết nối đến pathname **stream socket** cần quyền **write** trên socket node; nhưng POSIX **không bảo đảm mọi OS áp dụng permission bits socket giống Linux**. Không thể dựa duy nhất vào mode của socket node cho một thiết kế bảo mật portable.
- Mode của node có thể chịu ảnh hưởng bởi **umask** của tiến trình khi tạo. Nếu service chạy với umask quá rộng trong thư mục chung, node có thể dễ bị client không mong muốn truy cập.
- Nếu thư mục cha chỉ cho owner đi qua, người dùng khác khó truy cập node ngay cả khi socket-node mode tương đối rộng.
- Thông tin owner/group và ACL nên được kiểm tra bằng công cụ OS phù hợp, chẳng hạn `ls -ld` thư mục và `ls -l` socket trên Linux.

Ví dụ triển khai Linux theo nguyên tắc tối thiểu:

~~~text
/run/myapp/             owner=myapp, mode=0700
/run/myapp/service.sock owner=myapp, mode được tạo theo umask / policy
~~~

`0700` trên thư mục nghĩa là owner có quyền read/write/execute, user/group khác không có quyền theo mode bits; thư mục riêng ngăn việc khách lạ tạo, thay thế hoặc truy cập tên socket dễ dàng. Nếu muốn một nhóm dịch vụ khác kết nối, có thể dùng group/ACL được cấu hình rõ thay vì mở rộng thành `0777`.

**Không khẳng định `chmod 600 service.sock` luôn là giải pháp đủ.** Trên Linux, nó có giá trị với permission của pathname socket, nhưng OS khác có thể xử lý khác; ngoài ra còn ACL, group, mount namespace, SELinux/AppArmor, process identity, service policy, và authentication của ứng dụng.

### 5.2. Tạo thư mục private bằng Java NIO trên POSIX

Trong một ứng dụng Linux/POSIX, có thể tạo thư mục mới với mode ban đầu được yêu cầu:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

Path parent = Path.of("/run/myapp");
Path privateDir = Files.createTempDirectory(
        parent,
        "uds-",
        PosixFilePermissions.asFileAttribute("rwx------"));
~~~

Đây là **mảnh code phụ thuộc POSIX**: `/run/myapp` phải có sẵn, writable cho service; filesystem/provider phải hỗ trợ POSIX attributes. Khi provider không hỗ trợ, operation có thể ném `UnsupportedOperationException`. Không thay thế việc cấu hình service manager và ownership/ACL cho thư mục cha, nhất là nếu folder dùng lại qua các lần restart.

Nếu muốn thay quyền sau khi đã tạo:

~~~java
Files.setPosixFilePermissions(privateDir,
        PosixFilePermissions.fromString("rwx------"));
~~~

Đây cũng chỉ là mảnh code; trên Windows/provider không có POSIX view có thể không chạy. **Chỉnh permission sau khi file đã được tạo có thể để lộ một cửa sổ thời gian (race)**; để bảo vệ production, đặt quyền/umask phù hợp **trước khi bind**, và sử dụng parent directory riêng, không thể bị người không tin cậy thay đổi.

### 5.3. Trên Windows

Windows có hỗ trợ Unix-domain sockets ở các phiên bản phù hợp, và Java NIO `UNIX` có thể chạy nếu OS/JDK hỗ trợ, nhưng:

- Quyền được quản lý theo **Windows security model/ACL**, không phải mode `0700`/`0600` của POSIX.
- Không dùng `Files.setPosixFilePermissions(...)` làm cách cấp quyền portable.
- Không giả định path `C:\...` có cùng giới hạn/tính năng với Linux hoặc rằng socket-node permission được áp dụng y hệt.
- Chỉ làm việc với thư mục và đường dẫn do tiến trình/service sở hữu; xác minh ACL trên đúng hệ điều hành, thử kết nối bằng account không được phép trước khi tuyên bố isolation có hiệu lực.

Trên hệ thống container, còn cần nhìn vào **mount namespace**: hai container chỉ kết nối được qua path nếu path đến socket được expose/đặt trong volume chia sẻ phù hợp và chính sách cho phép. Có cùng chuỗi tên file nhưng không chung namespace chưa chắc là cùng endpoint.

### 5.4. File permission không thay authentication

Unix-domain socket chỉ cho **local communication**, loại bỏ việc phơi cổng TCP ra remote network, nhưng **không tự chứng minh danh tính client**. Tùy môi trường:

- Dùng user/group và quyền thư mục/socket theo nguyên tắc tối thiểu.
- Kiểm tra peer credentials bằng khả năng **platform-specific** khi có và khi threat model yêu cầu. Một số hệ thống/JDK có option mở rộng; không tự giả định mọi platform hỗ trợ.
- Đối với tác vụ nhạy cảm, application protocol vẫn cần kiểm soát quyền thao tác, validate input, giới hạn kích thước thông điệp, tránh DoS và logging bí mật.
- Không dùng thư mục chia sẻ không kiểm soát để đặt một endpoint có quyền thực hiện thao tác quản trị hệ thống.

## 6. `close()` và `Files.deleteIfExists()` là hai bước độc lập

### 6.1. Đóng channel không gỡ file khỏi filesystem

Khi bind một Unix-domain server socket tới `/run/myapp/service.sock`, OS tạo một **socket node** trên filesystem. Sau khi đóng channel:

~~~java
server.close();
// Không tự suy rằng Files.exists(socketPath) sẽ là false.
~~~

Tài liệu `ServerSocketChannel.bind` của JDK ghi rõ node socket **tồn tại sau khi channel bị đóng**, và cần xóa trước khi bind lại cùng pathname. Điều này cũng đúng với đường dẫn server được JDK tự cấp bằng `bind(null)`. Trên Linux, hành vi này liên quan đến việc unlink pathname; nó **khác** việc đóng file descriptor.

Hệ quả:

- Một service **đã dừng** vẫn để lại `service.sock` trên đĩa (stale socket file).
- Service khởi động lại dùng đúng path và `bind` có thể thất bại kiểu “Address already in use” hoặc tương đương.
- Chỉ gọi `try (ServerSocketChannel ... )` chưa đủ để đảm bảo startup tiếp theo sạch.
- Xóa file socket **không có nghĩa** kernel connection đã được đóng (nếu còn accepted channels); cũng không tự chờ client hoàn tất. Những bước đó thuộc phần lifecycle.

### 6.2. Vì sao không `Files.deleteIfExists(path)` trước mọi lần startup?

Giả sử instance A đang chạy và sở hữu `/run/myapp/service.sock`. Instance B khởi động và thấy file tồn tại. Nếu B xóa path **không kiểm tra**, B có thể xóa tên endpoint đang hoạt động của A. Các client mới không kết nối được theo path đó dù các kết nối đã được thiết lập của A có thể còn sống; B có thể chiếm tên và tạo split-brain.

Vì vậy **file tồn tại không đồng nghĩa file stale**. Trước khi dọn một path đã có, phải biết:

- Mình có phải **owner** của endpoint/path này hay không?
- Instance cũ còn hoạt động không? Ai đang giữ lock hoặc service manager instance ownership?
- Path có thuộc **thư mục riêng** không thể bị người khác thay thế không?
- Có race giữa kiểm tra tồn tại/kiểm tra process/kiểm tra file type và thời điểm xóa không?

Cách an toàn cho bài thực hành là tạo **một thư mục tạm độc quyền mới**, đặt socket ở trong đó, không cho tiến trình khác ghi vào folder, và chỉ dọn đường dẫn đã được chính chương trình tạo ra. Với production có path cố định, dùng service manager, singleton/lock và quy trình recovery, không gọi xóa vô điều kiện trong thư mục chia sẻ.

### 6.3. Dọn đúng thời điểm

Vòng đời ưu tiên:

~~~text
1. Chọn private directory và path socket chưa tồn tại.
2. Mở ServerSocketChannel(UNIX), bind path.
3. Chấp nhận/hoàn thành các request đang xử lý.
4. Dừng nhận kết nối mới, đóng listener và accepted channels theo ownership.
5. Sau khi chắc chắn instance này sở hữu path, xóa socket node.
6. Xóa directory tạm do chính instance tạo ra (nếu rỗng).
~~~

Đối với một server thật:

- Để ngừng nhận client mới, đóng listener và bảo đảm accept loop dừng.
- Các `SocketChannel` đã `accept()` là connection riêng; nếu cần graceful shutdown, có thể cho handler hoàn tất theo deadline hoặc đóng cưỡng bức theo chính sách.
- Khi kết thúc, dọn pathname thuộc chính service. Đừng xóa path của service khác chỉ vì cùng tên.
- Đảm bảo xử lý exception trong lúc đóng và xóa file; nếu cleanup lỗi, ghi nhận và báo vận hành thay vì im lặng.

Trong Java, `Files.deleteIfExists(socketPath)` có thể ném `IOException` (quyền, file đang được dùng, hoặc vấn đề OS khác). Nếu biết chắc file thuộc mình, **đừng nuốt exception** mà giả vờ cleanup đã thành công. `Files.deleteIfExists` không tự xác minh owner hay loại file; đó là trách nhiệm của ứng dụng trước khi gọi.

### 6.4. Xử lý symlink và TOCTOU

`Files.exists(path)` rồi `Files.deleteIfExists(path)` là **hai thao tác riêng**, không tạo ra transaction. Nếu một tiến trình khác có thể thay thế path giữa hai thao tác, ứng dụng có thể xóa nhầm. `LinkOption.NOFOLLOW_LINKS` giúp kiểm tra node thay vì theo symlink trong một lần query, **nhưng không tự loại bỏ race**.

Không nên “phòng thủ” bằng cách:

~~~java
// Nguy hiểm trên đường dẫn không thuộc quyền kiểm soát:
if (Files.exists(socketPath)) {
    Files.delete(socketPath);
}
listener.bind(UnixDomainSocketAddress.of(socketPath));
~~~

Nếu path đang là socket live của instance khác hoặc file bị thay thế, code trên gây gián đoạn/không an toàn. Giải pháp vững hơn là quyền thư mục độc quyền, quản lý tên theo instance, socket/service ownership, kiểm tra lifecycle, và nếu cần dùng cơ chế lock/atomic coordination được thiết kế cho platform.

### 6.5. Xóa file không đồng nghĩa đóng listener

Trên các OS kiểu Unix, unlink pathname trong khi socket vẫn mở **không nhất thiết đóng ngay các kết nối đã thiết lập**. Nhưng client mới có thể không tìm thấy endpoint cũ để kết nối theo tên. Vì vậy **xóa path không phải API để hủy kết nối hoặc dừng server một cách an toàn**.

Trên Windows có thể có ràng buộc khác về xóa một socket node đang mở. Cách portable ở tầng Java: đóng các channel mình sở hữu trước; sau đó xóa path trong `finally` sau khi lifecycle đã dừng.

## 7. Mối quan hệ với buffer và channel

Unix-domain socket qua `SocketChannel` vẫn là **stream-oriented**. Những kiến thức NIO buffer/channel vẫn áp dụng:

- `SocketChannel.read(ByteBuffer)` trả số byte thực đọc, **có thể ít hơn buffer còn trống**, và `-1` khi peer đã kết thúc chiều gửi; không cho rằng một `read` = một message.
- `SocketChannel.write(ByteBuffer)` cũng có thể ghi **ít hơn** `buffer.remaining()`. Vòng lặp `while (buffer.hasRemaining())` thường cần trong blocking code để gửi đủ payload.
- Khi dùng non-blocking channel, `read`/`write` có thể trả `0` vì chưa sẵn sàng; code non-blocking phải tích hợp `Selector`/readiness, không busy-spin.
- `ByteBuffer.flip()` chuyển từ trạng thái ghi vào buffer sang trạng thái đọc; `clear()` hoặc `compact()` cho các vòng nhận tiếp theo.
- Cần **framing** để biết message kết thúc: fixed-length, prefix length, delimiter hoặc protocol cụ thể. AF_UNIX **không** biến một byte stream thành datagram message boundaries.
- Khi peer đóng, EOF là trạng thái của **stream**, không phải dấu hiệu mỗi request đều đã xử lý thành công.

Đoạn minh họa hai hàm hỗ trợ gửi/nhận đúng **4 byte ASCII**:

~~~java
private static void writeText(SocketChannel ch, String text)
        throws IOException {
    ByteBuffer data = StandardCharsets.US_ASCII.encode(text);
    while (data.hasRemaining()) {
        ch.write(data);
    }
}

private static String readFour(SocketChannel ch) throws IOException {
    ByteBuffer data = ByteBuffer.allocate(4);
    while (data.hasRemaining()) {
        int n = ch.read(data);
        if (n == -1) {
            throw new EOFException("Expected 4 bytes");
        }
    }
    return new String(data.array(), StandardCharsets.US_ASCII);
}
~~~

Đây là **các method dùng trong class ví dụ hoàn chỉnh ở phần 9**, không phải chương trình standalone khi copy riêng. Mã giả định channel ở **blocking mode**; với non-blocking mode, phải xử lý `0`/readiness thay vì chỉ chạy vòng lặp không chờ.

### Accepted socket và listener có cùng path không?

Listener `ServerSocketChannel` gắn với path được bind. Mỗi `accept()` trả một `SocketChannel` riêng để trao đổi với client. Các accepted connections **không phải mỗi cái một file `service-1.sock`, `service-2.sock`...**. Path là tên **endpoint đang lắng nghe**, không phải file dữ liệu cho mỗi request. Client không bind tên riêng khi dùng implicit unnamed connection.

Vì vậy khi cleanup:

- **Không** xóa socket path sau khi *mỗi request* kết thúc nếu listener vẫn cần nhận client khác.
- **Không** gọi xóa path trong `try (SocketChannel accepted = ...)` của từng handler.
- **Có** thể dọn path sau vòng đời **listener/instance server**, khi server thật sự dừng và endpoint thuộc quyền của mình.

## 8. Ma trận API và vòng đời

| Mục đích | API Java 17+ | Hành vi và lưu ý |
| --- | --- | --- |
| Tạo listener UDS | `ServerSocketChannel.open(StandardProtocolFamily.UNIX)` | Không bind ngay |
| Tạo tên endpoint | `UnixDomainSocketAddress.of(Path)` | Path từ default file system; path length phụ thuộc platform |
| Bind server | `server.bind(address)` | Tạo socket node; cần path/permissions hợp lệ, tên chưa bị chiếm |
| Bind auto | `server.bind(null)` | Tạo tên tạm do JDK chọn; file vẫn cần dọn |
| Lấy tên server đã bind | `(UnixDomainSocketAddress) server.getLocalAddress()` | Hữu ích khi bind(null) và cần discovery/cleanup |
| Nhận client | `SocketChannel ch = server.accept()` | Mỗi lần tạo connected channel mới |
| Tạo client UDS | `SocketChannel.open(StandardProtocolFamily.UNIX)` | Chưa connected |
| Kết nối client | `client.connect(address)` | Client thường implicit unnamed, không tạo pathname riêng |
| Gửi/nhận | `ch.write(ByteBuffer)` / `ch.read(ByteBuffer)` | Stream bytes; tự xử lý partial I/O/framing |
| Đóng connected channel | `ch.close()` | Không đóng listener |
| Đóng listener | `server.close()` | Dừng accept, **không unlink socket file** |
| Kiểm tra node filesystem | `Files.exists(path, NOFOLLOW_LINKS)` | Chỉ quan sát, không khẳng định stale hay ownership |
| Dọn node sở hữu | `Files.deleteIfExists(path)` | Chỉ sau khi đóng, tránh xóa nhầm/race |
| Dọn thư mục tạm | `Files.deleteIfExists(dir)` | Chỉ folder mình tạo, phải rỗng |

## 9. Chương trình Java 17+ chạy hoàn chỉnh

Chương trình này minh họa đầy đủ:

1. Dùng `Files.createTempDirectory("uds-")` để tạo thư mục riêng mới cho lần chạy, tránh tranh chấp một socket path cố định.
2. Tạo `server.sock` trong folder đó; bind bằng `ServerSocketChannel.open(UNIX)`.
3. Tạo một server worker chấp nhận client qua `accept()`; đọc `PING`, trả `PONG`.
4. Client kết nối đến đúng `UnixDomainSocketAddress` và kiểm tra nội dung phản hồi.
5. Đóng connected channels và listener bằng `try-with-resources`.
6. **Kiểm tra file còn tồn tại sau khi listener đóng** bằng `Files.exists(..., NOFOLLOW_LINKS)`.
7. **Dọn đúng path** trong `finally`, sau đó dọn thư mục riêng mới tạo.

Tạo file **`UnixDomainPathDemo.java`**:

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
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class UnixDomainPathDemo {
    private static void writeText(SocketChannel channel, String text)
            throws IOException {
        ByteBuffer data = StandardCharsets.US_ASCII.encode(text);
        while (data.hasRemaining()) {
            channel.write(data);
        }
    }

    private static String readFour(SocketChannel channel) throws IOException {
        ByteBuffer data = ByteBuffer.allocate(4);
        while (data.hasRemaining()) {
            int n = channel.read(data);
            if (n == -1) {
                throw new EOFException("Expected 4 bytes");
            }
        }
        return new String(data.array(), StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("uds-");
        Path path = directory.resolve("server.sock");
        ExecutorService workers = Executors.newSingleThreadExecutor();
        try {
            UnixDomainSocketAddress address = UnixDomainSocketAddress.of(path);
            try (ServerSocketChannel listener =
                    ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
                listener.bind(address);
                Future<String> server = workers.submit(() -> {
                    try (SocketChannel accepted = listener.accept()) {
                        String request = readFour(accepted);
                        writeText(accepted, "PONG");
                        return request;
                    }
                });
                try (SocketChannel client =
                        SocketChannel.open(StandardProtocolFamily.UNIX)) {
                    client.connect(address);
                    writeText(client, "PING");
                    System.out.println("Client received: " + readFour(client));
                }
                System.out.println("Server received: " +
                        server.get(5, TimeUnit.SECONDS));
            }
            System.out.println("Socket path remains after close: " +
                    Files.exists(path, LinkOption.NOFOLLOW_LINKS));
        } finally {
            workers.shutdownNow();
            Files.deleteIfExists(path);
            Files.deleteIfExists(directory);
        }
        System.out.println("Socket path deleted: " +
                !Files.exists(path, LinkOption.NOFOLLOW_LINKS));
    }
}
~~~

Cách biên dịch và chạy trên JDK 17+ với OS hỗ trợ pathname-based Unix-domain sockets:

~~~bash
javac -encoding UTF-8 UnixDomainPathDemo.java
java UnixDomainPathDemo
~~~

**Stdout đã xác minh với OpenJDK 24 trên Windows có AF_UNIX:**

~~~text
Client received: PONG
Server received: PING
Socket path remains after close: true
Socket path deleted: true
~~~

Cách đọc kết quả:

1. Client và server gặp nhau thông qua **đường dẫn filesystem**, không dùng TCP/IP, DNS hoặc port.
2. `writeText` và `readFour` dùng vòng lặp để không giả định một lần I/O xử lý hết bốn byte.
3. Server worker đọc đúng `PING` rồi trả `PONG`; `Future.get(5, TimeUnit.SECONDS)` đợi task xong và chuyển lỗi worker về main.
4. `try (SocketChannel accepted...)` đóng accepted connection, `try (SocketChannel client...)` đóng client, `try (ServerSocketChannel listener...)` đóng listener.
5. Sau khi **listener đã đóng**, `Files.exists(path, NOFOLLOW_LINKS)` vẫn trả `true` vì socket node vẫn còn.
6. `Files.deleteIfExists(path)` dọn đúng node trong thư mục **vừa được chương trình tạo riêng**; sau đó `Files.deleteIfExists(directory)` dọn folder rỗng. Vì thế dòng cuối xác nhận `true`.

**Giới hạn và lưu ý về demo:**

- Mặc dù `Files.createTempDirectory` giảm rủi ro đụng tên, deployment bảo mật cần chính sách ACL/mode **trước khi bind**. Không mặc định thư mục tạm của mọi OS đều thỏa yêu cầu bảo mật của một service nhạy cảm.
- Một số OS/JDK không hỗ trợ `StandardProtocolFamily.UNIX` hoặc bị hạn chế tạo socket; khi đó có thể gặp `UnsupportedOperationException` hoặc lỗi I/O. Không nên đổi sang TCP ngầm mà không thiết kế lại mô hình quyền.
- Nếu đường dẫn temp quá dài so với giới hạn Unix-domain socket của OS, bind có thể thất bại; hãy cấu hình thư mục runtime **ngắn và đáng tin** cho môi trường đó.
- `ExecutorService.shutdownNow()` ở demo chỉ là cleanup task executor sau khi `Future.get` đã xác nhận happy path. Trong server dài hạn cần đóng listener, phối hợp worker hoàn tất/hủy, có timeout và quản lý accepted connections trước khi xóa path.
- `readFour` chỉ đọc đúng bốn byte để demo; protocol thật phải định nghĩa frame, giới hạn dữ liệu và xử lý EOF/timeout hợp lệ. Unix-domain byte stream không tự framing message.
- Nếu cleanup bị lỗi, `Files.deleteIfExists` ném exception; đây là tín hiệu cần xử lý, không tự ghi đè hay xóa cả cây thư mục ngoài phạm vi.
- Kết quả `true` của `Files.exists` khi server đóng là hành vi được tài liệu Java mô tả cho pathname socket; không được viết code production phụ thuộc “tự dọn” theo mặc định.

## 10. Biến thể: `bind(null)` vẫn cần dọn đường dẫn

Một số server không cần path cố định; muốn OS/JDK tự chọn tên duy nhất:

~~~java
Path autoPath;
try (ServerSocketChannel server =
        ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
    server.bind(null);
    autoPath = ((UnixDomainSocketAddress) server.getLocalAddress()).getPath();
    System.out.println("Has named server address: " +
            !autoPath.toString().isEmpty());
    System.out.println("Socket file while open: " +
            Files.exists(autoPath, LinkOption.NOFOLLOW_LINKS));
}
try {
    System.out.println("Socket file after close: " +
            Files.exists(autoPath, LinkOption.NOFOLLOW_LINKS));
} finally {
    Files.deleteIfExists(autoPath);
}
~~~

**Đây là mảnh mã** đặt trong method `throws Exception`, cần imports `java.net.*`, `java.nio.channels.*`, `java.nio.file.*`. Đường dẫn do server tự bind phải được gửi cho client qua cơ chế discovery đáng tin. Đừng tự tìm file đầu tiên có tiền tố `socket_` trong thư mục tạm: điều đó có thể là file của process khác.

Đoạn này đã được thử trên JDK hỗ trợ UDS với ba dòng:

~~~text
Has named server address: true
Socket file while open: true
Socket file after close: true
~~~

Dòng thứ ba chứng minh **auto-named socket file vẫn tồn tại sau close**. Nếu muốn thử như chương trình độc lập, bọc đoạn trên trong class có `public static void main(String[] args) throws Exception` và imports hợp lệ. Dù server tự cấp tên, nguyên tắc dọn file thuộc chính mình không đổi.

## 11. Triệu chứng thực tế và hướng chẩn đoán

### 11.1. `Address already in use` hoặc bind thất bại

Khả năng:

- Path đã có socket node do instance **đang hoạt động** sở hữu.
- Instance cũ chết nhưng để lại **stale socket file**.
- Path là một file khác (regular file, symlink, directory) bị đặt trùng tên.
- Một process khác vừa bind vào tên đó giữa hai bước kiểm tra.
- Path vượt giới hạn OS hoặc filesystem không hỗ trợ Unix-domain node.

Cách xử lý:

1. Quan sát path, owner, type và trạng thái process/server với công cụ OS trong phạm vi được phép.
2. Kiểm tra service manager/lock, xem có instance thật đang chạy không.
3. Nếu xác thực được path stale và thuộc đúng service, dọn dưới quyền của lifecycle manager; **không xóa bừa**.
4. Ưu tiên thiết kế private runtime directory và một owner duy nhất, tránh split-brain.
5. Thử bind lại sau khi vấn đề thực được giải quyết.

**Không đưa vào startup logic một câu lệnh `Files.deleteIfExists(socketPath)` vô điều kiện** trước khi bind. Mã có thể làm gián đoạn service cũ.

### 11.2. `Access denied` / `Permission denied`

Kiểm tra:

- Parent directory có tồn tại không? Service user có thể search/traverse và create node không?
- File socket có owner/group/ACL đúng không? Trên Linux, client connect cần quyền write trên socket node.
- Có ACL bổ sung, SELinux/AppArmor, policy container, mount namespace hoặc Windows ACL không?
- Process có quyền trên thư mục temp do JDK chọn không? `bind(null)` vẫn cần ghi được ở directory mục tiêu.
- Path có đi qua thư mục do người lạ kiểm soát hoặc symlink không?

Đừng khắc phục bằng `chmod 777` toàn bộ thư mục, nhất là service có quyền nhạy cảm. Xác định **principal cần kết nối** và cấp quyền tối thiểu cho đúng principal, từ thư mục cha đến socket.

### 11.3. `No such file or directory` / `Connection refused`

- `No such file or directory`: pathname/server file có thể không tồn tại, sai mount namespace, path bị đổi hoặc thư mục cha thiếu.
- `Connection refused` hoặc lỗi kết nối tương ứng: file/socket node có thể còn nhưng không có listener đang hoạt động, server đã close hoặc trạng thái không sẵn sàng.
- Không kết luận chắc chắn chỉ từ một thông báo lỗi; wording và cách mapping native error sang `IOException` khác nhau giữa OS.
- Một path tồn tại không chứng minh server còn sống. Cần kiểm tra service process và thực hiện connect/health protocol trong quyền cho phép.

### 11.4. Linux tools thường hữu ích

~~~bash
ls -ld /run/myapp
ls -l /run/myapp/service.sock
stat /run/myapp/service.sock
ss -xl
~~~

Các lệnh trên chỉ minh họa cho Linux và nên chạy ở hệ thống bạn sở hữu hoặc được phép chẩn đoán. `ls -l` thường hiển thị type `s` với socket node; đó không phải file lưu payload. `ss -xl` giúp quan sát một số Unix-domain listening sockets; output phụ thuộc quyền, namespace và hệ điều hành. Không lấy số liệu từ những ví dụ lệnh này làm kết quả thật của chương trình Java.

## 12. Các lỗi thiết kế cần tránh

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng `new ServerSocket()` với `UnixDomainSocketAddress` | API TCP/IP legacy không phải cách chọn family `UNIX` | `ServerSocketChannel.open(UNIX)` |
| Dùng `InetSocketAddress("localhost", port)` | Đó là TCP/IP, không phải pathname IPC | `UnixDomainSocketAddress.of(Path)` |
| Nghĩ `.sock` là file payload bình thường | File socket là node đặc biệt cho connect/bind | Đọc/ghi qua `SocketChannel` |
| Đóng channel rồi tin path tự mất | JDK không tự unlink bound pathname | Cleanup riêng sau khi đóng |
| Đặt `Files.deleteIfExists(path)` trong handler của từng client | Client mới mất tên server đang lắng nghe | Cleanup ở lifecycle server/instance |
| Khi thấy path có sẵn, xóa ngay | Có thể là endpoint của server khác đang chạy | Kiểm tra owner/instance/liveness và phối hợp shutdown |
| Đặt socket cố định trong thư mục world-writable | Dễ collision, symlink/race, truy cập trái ý muốn | Private directory + ownership + permissions |
| Chỉ kiểm tra `Files.exists` rồi xóa | Có time-of-check/time-of-use race | Bảo vệ thư mục, lock và quản trị instance |
| Cố coi permission mode socket là portable | POSIX không bảo đảm cùng cơ chế mọi OS | Thư mục riêng, ACL và peer auth khi cần |
| Dùng `setPosixFilePermissions` trên Windows | POSIX attribute view không có sẵn | Cấu hình Windows ACL phù hợp |
| Dùng đường dẫn Unicode/rất dài | Native sockaddr path tính theo byte và có giới hạn | Path ngắn, thử trên OS mục tiêu |
| Dùng Path từ ZIP filesystem | Không phải default filesystem Path | Dùng `Path.of(...)` hoặc default provider |
| Tưởng `bind(null)` không tạo file | Server auto-bind tạo tên tạm và vẫn để lại node | Lấy `getLocalAddress().getPath()` và dọn |
| Định danh client bằng port hoặc IP | Unix-domain socket không có TCP endpoint | Dùng policy local users/peers, application protocol |
| Tưởng Unix-domain socket tự đóng mọi accepted connections khi listener close | Connection channels độc lập | Quản lý handler/accepted sockets riêng |
| Đọc một lần vào buffer và coi là message hoàn chỉnh | Stream I/O có thể partial | Framing và vòng read/write đúng |
| Thao tác unlink trong khi listener còn chạy | Client mới không tìm thấy endpoint, race khó debug | Dừng listener/handler rồi cleanup |
| Xóa đệ quy cả thư mục runtime dùng chung | Có thể làm mất dữ liệu/socket khác | Chỉ delete node và directory mình tạo/sở hữu |
| Bỏ qua lỗi cleanup | Restart sau dễ bind fail | Log/báo lỗi; xử lý stale file có kiểm soát |

## 13. Test cases nên có

| Tình huống | Kiểm tra |
| --- | --- |
| Bind vào path mới thuộc private directory | Thành công và tạo socket node |
| Client nối vào đúng path | Có thể trao đổi byte qua `SocketChannel` |
| Đóng client nhưng listener vẫn mở | Server còn có thể accept client khác |
| Đóng listener khi accepted channel đã tồn tại | Accepted connection không tự bị đóng chỉ bởi listener |
| Đóng listener rồi kiểm tra path | File còn tồn tại theo hợp đồng Java |
| Cleanup sau khi listener ngừng | Node bị xóa, directory rỗng có thể dọn |
| Bind lại cùng path **khi file stale chưa xóa** | Có thể thất bại; không tự xóa trước khi xác minh ownership |
| Bind lại path sau cleanup đúng | Có thể thành công nếu OS và quyền cho phép |
| Path quá dài | Bind/connect ném lỗi đúng ngữ cảnh; giải pháp là ngắn path |
| Quyền parent directory không đủ | Server bind bị từ chối theo OS policy |
| Client không được phép connect | Bị từ chối theo policy thực tế của OS/ACL |
| Symlink hoặc file khác tại path | Không ghi đè/xóa file không thuộc mình |
| Hai instance cạnh tranh cùng tên | Chỉ một owner có quyền bind; instance thứ hai không unlink instance đầu |
| Crash giữa bind và cleanup | Lần khởi động sau nhận diện stale an toàn, không xóa live socket |
| Container có mount namespace khác | Không dựa vào tên giống nhau để kết luận là cùng endpoint |
| Lỗi trong handler và cleanup | Accepted channel, listener và file được xử lý theo ownership; exception được báo |

Không nhất thiết viết hết các test bằng một `main()`; các trường hợp quyền, race và crash cần môi trường kiểm thử có quản lý, đôi khi phải chạy nhiều process/OS accounts. Demo ở phần 9 chủ yếu chứng minh bản chất **channel close ≠ pathname delete**.

## 14. Bài tập thực hành và đáp án

### Bài 1 — Tại sao restart thất bại?

Một server dùng `/run/myapp/service.sock`. Lần chạy trước đã thoát khỏi `try (ServerSocketChannel server = ...)` nhưng lần sau `bind` báo trùng tên. Vì sao?

**Đáp án:** Unix-domain socket đã bind tạo socket node; `close()` đóng channel nhưng **không tự unlink** pathname. File stale còn khiến bind lại cùng tên không thành công. Sau khi xác minh instance cũ không chạy và sở hữu path, dọn node theo quy trình an toàn, không xóa mù.

### Bài 2 — Vai trò của chmod 0700

Tại sao thư mục `/run/myapp` có mode `0700` do chính service sở hữu hữu ích hơn so với đặt socket vào `/tmp/service.sock` và chỉ chmod socket file?

**Đáp án:** Thư mục riêng giúp người không được phép **không traverse hoặc thay thế tên** endpoint; trên Linux client cần đi qua directory và có quyền thích hợp. Socket-node mode còn phụ thuộc OS và có thể bị thay đổi trong race sau bind. Khi cần một group user khác connect, dùng quyền/ACL được thiết kế, không tự mở toàn bộ thư mục.

### Bài 3 — Bind tự động

`ServerSocketChannel.open(UNIX).bind(null)` có tự giải phóng file sau khi `close()` không? Làm sao biết path để dọn?

**Đáp án:** Không. Lấy `(UnixDomainSocketAddress) server.getLocalAddress()` rồi `getPath()` sau bind, giữ path đó trong ownership của instance và dọn khi server đã dừng.

### Bài 4 — Client có file riêng?

Client tạo `SocketChannel.open(UNIX)`, gọi `connect(address)` mà không bind local address. Có cần xóa `client.sock` không?

**Đáp án:** Không có pathname socket file riêng được tạo cho kiểu client **implicitly bound** đó; endpoint local được coi là unnamed. Chỉ dọn các path mà chương trình thực sự sở hữu/tạo ra.

### Bài 5 — Xóa path sớm

Instance A đang lắng nghe tại `/tmp/app.sock`. Instance B thấy path tồn tại và gọi `Files.deleteIfExists("/tmp/app.sock")` trước khi bind. Điều gì nguy hiểm?

**Đáp án:** B có thể unlink tên endpoint đang hoạt động của A, làm client mới không connect được theo tên cũ và gây split-brain, trong khi những connection cũ có thể vẫn còn. Phải có owner/instance coordination, private directory và xác minh an toàn trước khi xử lý stale path.

### Bài 6 — Partial read/write

Server gọi `SocketChannel.read(buffer)` một lần và coi rằng đã nhận trọn một request dài 200 byte. Vì sao có thể sai?

**Đáp án:** Unix-domain stream socket **không có message boundary**. Một lần read có thể chỉ trả một phần byte; phải định nghĩa framing, lặp tới khi nhận đủ và xử lý EOF/timeout.

### Bài 7 — Phân biệt hệ điều hành

Một nhóm lập trình thấy Linux cho phép `chmod 600 service.sock` và kết luận Windows, macOS, BSD đều áp dụng cùng cách kiểm tra quyền trên socket node. Kết luận đúng không?

**Đáp án:** Không. POSIX không bắt buộc cùng semantics cho permission của pathname socket trên mọi OS; Windows dùng ACL và những chính sách riêng. Phải kiểm thử OS mục tiêu; bắt đầu bằng private directory, proper ownership và application authorization khi cần.

### Bài 8 — Giới hạn đường dẫn

Một đường dẫn dài 160 byte vẫn tạo được file văn bản trên filesystem. Nó có chắc bind được làm `UnixDomainSocketAddress` không?

**Đáp án:** Không. Unix-domain sockaddr path có giới hạn native riêng (JDK mô tả thường ~100 byte). Chọn path ngắn hơn, không tự mặc định filesystem path hợp lệ thì socket address cũng hợp lệ.

## 15. Checklist trước khi deploy

- [ ] Dùng `StandardProtocolFamily.UNIX` và `UnixDomainSocketAddress`, không nhầm với TCP loopback.
- [ ] Path là **đường dẫn ngắn, tuyệt đối**, thuộc default filesystem, directory cha có sẵn.
- [ ] Có quy tắc **owner**: server/service manager chịu trách nhiệm path, listener, accepted channels.
- [ ] Directory cha có quyền phù hợp; trên Linux phân biệt directory execute/search và socket write; trên Windows kiểm tra ACL.
- [ ] Không đặt socket nhạy cảm trong thư mục chia sẻ dễ bị đổi tên/symlink nếu chưa bảo vệ.
- [ ] Có cơ chế ngăn hai server instance cùng chiếm một tên endpoint.
- [ ] Không coi `Files.exists(path)` là bằng chứng endpoint stale hoặc client/server còn hoạt động.
- [ ] Không xóa file đã có trước startup nếu chưa xác minh ownership và trạng thái instance cũ.
- [ ] `try-with-resources` đóng channels; `finally` riêng dọn pathname **sau khi** ngừng listener/handler.
- [ ] Với `bind(null)`, lưu path do `getLocalAddress()` trả về và dọn khi kết thúc.
- [ ] Không quên dọn accepted sockets/worker/executor trong graceful shutdown.
- [ ] Có framing và xử lý partial read/write, EOF, dữ liệu quá lớn, timeout và auth theo nhu cầu.
- [ ] Triển khai và thử trên OS/JDK cụ thể, kể cả path length, permission, crash/restart.
- [ ] Nếu cleanup thất bại, ghi lỗi vận hành; không xóa đệ quy thư mục không thuộc mình.

## 16. Tài liệu chính thức để đối chiếu

- [Java SE 17 — UnixDomainSocketAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/UnixDomainSocketAddress.html): `of(Path)`, `getPath()`, path từ default file system, unnamed address.
- [Java SE 17 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): `open(UNIX)`, `bind`, `accept`, và **quy định file socket vẫn còn sau close**.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): client `connect`, stream I/O, implicit unnamed bind, channel lifecycle.
- [Java SE 17 — NIO channel package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/package-summary.html): protocol families và Unix-domain stream socket support.
- [Java SE 17 — Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html): `jdk.net.unixdomain.tmpdir` và đường dẫn socket do `bind(null)` cấp phát.
- [Inside Java — JEP 380 Unix-domain socket channels](https://inside.java/2021/02/03/jep380-unix-domain-sockets-channels/): thiết kế API, sự khác biệt TCP vs local pathname, bảo mật và cleanup.
- [Linux man-pages — unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html): pathname sockets, độ dài `sun_path`, quyền parent directory/socket node và khác biệt portability.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `createTempDirectory`, `exists`, `deleteIfExists`, `LinkOption.NOFOLLOW_LINKS` và thao tác filesystem.
- [Java SE 17 — PosixFilePermissions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html): tạo/diễn giải permission POSIX, không phải API ACL portable.

**Điều cốt lõi:** Unix-domain socket dùng **pathname làm địa chỉ IPC**, nhưng pathname **không phải vòng đời của channel**. Hãy đặt đường dẫn trong thư mục được kiểm soát, cấp quyền đúng cho những process được phép, đóng listener/accepted channels đúng scope, và **chỉ xóa socket node sau khi chính instance sở hữu endpoint đã dừng**. Đó là chìa khóa tránh lỗi restart, rò file socket và xóa nhầm endpoint đang chạy.
