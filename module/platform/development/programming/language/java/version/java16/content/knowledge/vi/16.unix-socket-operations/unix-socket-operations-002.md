# Dọn socket pathname sau khi server đóng và xử lý tệp còn sót

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Vận hành socket  
**Áp dụng:** Java 16 trở lên; ví dụ pathname và quyền filesystem tập trung vào Linux/POSIX hiện đại.

Unix-domain socket dùng pathname trong filesystem để các tiến trình tìm thấy endpoint IPC. Khi server bind một `ServerSocketChannel` vào `UnixDomainSocketAddress` có đường dẫn, hệ điều hành tạo một socket file tương ứng. **Đóng channel không tự xóa socket file này.** File vẫn tồn tại và lần bind tiếp theo vào cùng pathname sẽ thất bại cho đến khi entry cũ được xóa.

Vì vậy, vòng đời một server pathname socket có hai phần độc lập:

1. Đóng channel để ngừng lắng nghe và giải phóng socket đang mở.
2. Xóa pathname sau khi channel đã đóng để giải phóng tên trong filesystem.

Ứng dụng cần xử lý cả shutdown bình thường lẫn trường hợp JVM hoặc máy chủ dừng đột ngột khiến socket file còn sót. Việc dọn file cũ phải dựa trên quyền sở hữu và trạng thái tiến trình; không xóa mù quáng một pathname chỉ vì bind gặp lỗi.

## 1. Vì sao socket file vẫn còn sau khi đóng channel?

Với TCP, đóng socket giải phóng endpoint mạng để có thể bind lại theo các quy tắc TCP/IP. Với Unix-domain socket dùng pathname, socket file là một entry riêng trong filesystem. Nó tồn tại độc lập với vòng đời của channel.

Ví dụ:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Path;

static void startAndCloseServer() throws IOException {
    Path socketPath = Path.of("/run/myapp/service.sock");

    try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
        server.bind(UnixDomainSocketAddress.of(socketPath));
        // Phục vụ client...
    }

    // Channel đã đóng, nhưng pathname vẫn còn trong filesystem.
}
```

Sau khi khối `try-with-resources` kết thúc, channel được đóng. Tuy nhiên, pathname `/run/myapp/service.sock` vẫn cần được xóa rõ ràng. Nếu server khởi động lại và bind cùng pathname khi entry này còn tồn tại, thao tác bind có thể thất bại với lỗi I/O như “address already in use” hoặc lỗi tương đương tùy hệ điều hành.

Quy tắc này áp dụng cả khi server dùng `bind(null)` để được hệ thống cấp một pathname tạm tự động. Địa chỉ được cấp cũng có socket file và file đó vẫn tồn tại sau khi channel đóng.

## 2. Đóng channel trước, xóa pathname sau

Với pathname cố định do ứng dụng quản lý, có thể dùng cờ để chỉ dọn file nếu lần bind của chính tiến trình đã thành công:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;

static void runServer(Path socketPath) throws IOException {
    boolean bound = false;

    try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
        server.bind(UnixDomainSocketAddress.of(socketPath));
        bound = true;

        serve(server);
    } finally {
        if (bound) {
            Files.deleteIfExists(socketPath);
        }
    }
}

static void serve(ServerSocketChannel server) throws IOException {
    // Vòng lặp accept và xử lý kết nối của ứng dụng.
}
```

Thứ tự ở đây rất quan trọng:

1. `bind` thành công, server sở hữu pathname.
2. Server phục vụ client.
3. Khi thoát khỏi khối `try-with-resources`, Java đóng `ServerSocketChannel`.
4. Khối `finally` chạy sau khi resource đã đóng và gọi `Files.deleteIfExists`.

Cờ `bound` ngăn ứng dụng xóa một pathname cũ nếu `bind` thất bại. Nếu pathname đã tồn tại trước khi server chạy, lỗi bind không chứng minh file đó thuộc tiến trình hiện tại.

`Files.deleteIfExists` trả về `false` nếu file không còn tồn tại và `true` nếu xóa được. Phương thức có thể ném `IOException` hoặc `SecurityException` nếu không thể xóa. Trong code production, cần ghi nhận lỗi cleanup; nếu cả xử lý server và xóa file đều thất bại, hãy giữ lỗi chính và gắn lỗi cleanup bằng `Throwable.addSuppressed` thay vì vô tình che mất nguyên nhân ban đầu.

## 3. Xử lý lỗi trong quá trình khởi tạo và shutdown

Không phải mọi lần chạy đều đi đến trạng thái server đã bind:

| Tình huống | Có nên xóa pathname? | Lý do |
| --- | --- | --- |
| `bind` thất bại vì pathname đã tồn tại | Không tự xóa | Pathname có thể thuộc server khác hoặc một file không liên quan. |
| `bind` thành công, server dừng bình thường | Có, sau khi đóng channel | Đây là pathname do instance hiện tại tạo. |
| `bind` thành công, xử lý request ném exception | Có, trong cleanup sau khi đóng channel | Cần giải phóng pathname của instance hiện tại. |
| JVM bị kill cưỡng bức hoặc máy mất điện | Cleanup trong Java có thể không chạy | Cần quy trình khôi phục stale pathname khi khởi động lại. |
| Xóa pathname thất bại do quyền hoặc filesystem | Không giả định đã sạch | Ghi log/alert và xử lý trước lần bind tiếp theo. |

Đóng channel và xóa pathname là hai thao tác riêng. Đóng channel không xóa file; xóa file cũng không thay thế việc đóng channel. Nếu xóa pathname khi server vẫn đang chạy, client mới có thể không còn tìm được endpoint qua tên đó, dù channel vẫn mở và các kết nối đã thiết lập có thể tiếp tục tồn tại.

Khi server quản lý các channel client đã accept, cần đóng hoặc drain chúng theo chính sách shutdown riêng. Đóng server channel chỉ dừng listener; không tự động thay thế quy trình kết thúc mọi phiên client do ứng dụng quản lý.

## 4. Xóa socket file khi dùng bind(null)

`ServerSocketChannel.bind(null)` yêu cầu hệ thống tự chọn một pathname duy nhất trong thư mục tạm. Lấy địa chỉ thực tế bằng `getLocalAddress()` để biết file cần xóa:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;

static void runWithAutomaticPath() throws IOException {
    Path socketPath = null;
    boolean bound = false;

    try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
        server.bind(null);
        bound = true;

        UnixDomainSocketAddress actualAddress =
            (UnixDomainSocketAddress) server.getLocalAddress();
        socketPath = actualAddress.getPath();

        System.out.println("Listening at " + actualAddress);
        serve(server);
    } finally {
        if (bound && socketPath != null) {
            Files.deleteIfExists(socketPath);
        }
    }
}
```

Đường dẫn thư mục dùng cho socket tự động có thể được cấu hình bằng networking property `jdk.net.unixdomain.tmpdir` trong `conf/net.properties` hoặc system property cùng tên khi khởi chạy JVM. Nếu không cấu hình, JVM chọn vị trí tạm theo quy tắc của nền tảng và có thể dùng `java.io.tmpdir` làm phương án tiếp theo. Đường dẫn thực tế phải được lấy từ `getLocalAddress()`, không tự ghép tên file để đoán.

Client `SocketChannel` kết nối mà không gọi `bind` trước thường có socket cục bộ unnamed, không có pathname file để dọn. Quy trình cleanup pathname chủ yếu áp dụng cho server đã bind vào địa chỉ có tên và client nào chủ động bind vào pathname.

## 5. Vì sao không nên xóa mù quáng pathname còn sót?

Giả sử server mới gặp lỗi bind vì `service.sock` đã tồn tại. Không thể kết luận file đó chắc chắn là socket cũ:

- Một instance service khác có thể vẫn đang chạy và sử dụng pathname đó.
- Pathname có thể là regular file, directory, FIFO hoặc symbolic link do thao tác sai hoặc tiến trình khác tạo.
- Một tiến trình khác có thể thay thế entry giữa lúc ứng dụng kiểm tra và lúc xóa.
- Nhiều instance có thể cùng khởi động, cùng kiểm tra pathname và cùng cố dọn.

Nếu xóa pathname của server đang hoạt động, endpoint sẽ mất tên trong filesystem. Các client mới không thể kết nối theo pathname cũ; instance đang chạy có thể vẫn giữ socket mở nhưng không còn được tìm thấy qua tên đó.

**Nguyên tắc:** chỉ xóa pathname mà tiến trình hiện tại đã bind thành công và sở hữu trong vòng đời của nó. Với file còn sót từ lần chạy trước, phải có cơ chế xác minh và phối hợp instance trước khi xóa.

## 6. Kiểm tra file còn sót mà không đi theo symbolic link

Khi cần điều tra pathname tồn tại trước khi khởi động, hãy đọc thuộc tính mà không follow symbolic link:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

static void inspectExistingPath(Path socketPath) throws IOException {
    BasicFileAttributes attributes;
    try {
        attributes = Files.readAttributes(
            socketPath,
            BasicFileAttributes.class,
            LinkOption.NOFOLLOW_LINKS
        );
    } catch (NoSuchFileException missing) {
        return;
    }

    if (attributes.isSymbolicLink()) {
        throw new IOException("Socket path is a symbolic link");
    }

    if (attributes.isDirectory() || attributes.isRegularFile()) {
        throw new IOException("Socket path is not a socket entry");
    }

    if (attributes.isOther()) {
        // Đây là một loại file đặc biệt; cần xác minh sâu hơn
        // bằng metadata phù hợp với hệ điều hành trước khi xóa.
    }
}
```

`BasicFileAttributes.isOther()` chỉ cho biết entry không phải regular file, directory hoặc symbolic link. Nó không phải một phép kiểm tra portable để khẳng định entry đó chắc chắn là Unix-domain socket; FIFO và một số loại special file khác cũng có thể thuộc nhóm này.

Java NIO chuẩn không cung cấp một phương thức portable tên như `isSocketFile()` cho mọi filesystem. Nếu cần xác minh loại socket file stale, dùng metadata đặc thù nền tảng hoặc công cụ quản trị phù hợp. Trên Unix-like system, có thể kiểm tra file type qua công cụ hệ điều hành; không lấy kết quả `isOther()` làm lý do duy nhất để xóa.

Có thể kiểm tra owner bằng `Files.getOwner(path, NOFOLLOW_LINKS)` và so sánh với service account mong đợi. Tuy nhiên, owner đúng vẫn chưa chứng minh socket không còn được một process sống sử dụng. Cần kết hợp kiểm tra owner, thư mục cha, trạng thái instance và cơ chế khóa/điều phối.

## 7. Dùng thư mục runtime riêng và khóa instance

Một cách giảm rủi ro race khi cleanup là đặt socket trong thư mục runtime riêng:

- Thư mục do service account sở hữu.
- User không tin cậy không có quyền tạo, xóa hoặc đổi tên entry trong thư mục.
- Socket pathname cố định chỉ được một instance quản lý tại một thời điểm.
- Quy trình startup/shutdown cùng tuân thủ một cơ chế khóa.

Với nhiều tiến trình có thể khởi động cùng lúc, có thể dùng file lock trên một lock file riêng trong thư mục runtime:

```java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

static void runAsSingleInstance(Path lockPath) throws IOException {
    try (FileChannel lockChannel = FileChannel.open(
             lockPath,
             StandardOpenOption.CREATE,
             StandardOpenOption.WRITE
         );
         FileLock lock = lockChannel.tryLock()) {

        if (lock == null) {
            throw new IOException("Another service instance holds the lock");
        }

        // Chỉ instance giữ lock mới được kiểm tra/dọn stale path,
        // bind socket, phục vụ request và cleanup pathname.
    }
}
```

`FileLock` là khóa ở mức hệ điều hành và thường được dùng để phối hợp các process cùng tuân thủ quy ước khóa. Nó không phải cơ chế ngăn mọi process không hợp tác truy cập pathname. `tryLock()` cũng có thể ném `OverlappingFileLockException` nếu cùng JVM đã giữ khóa chồng lấn.

Không xóa lock file trong khi khóa còn được giữ. Việc xóa và tạo lại lock file có thể khiến các process khóa những file object khác nhau dù pathname giống nhau. Giữ lock file ổn định trong thư mục runtime; chỉ quản lý vòng đời thư mục khi chắc chắn không còn instance sử dụng.

Nếu dùng service manager có khả năng tạo và dọn runtime directory theo vòng đời service, hãy tận dụng cơ chế đó thay cho tự xây dựng một quy trình phức tạp. Dù vậy, ứng dụng vẫn cần hiểu pathname socket tồn tại độc lập với channel và không giả định close tự xóa file.

## 8. Cẩn thận với race giữa kiểm tra, bind và delete

Một chuỗi thao tác kiểu sau không an toàn trong thư mục mà user khác có quyền ghi:

1. Kiểm tra pathname tồn tại.
2. Xác định file có vẻ là socket cũ.
3. Xóa pathname.
4. Bind socket mới.

Một process khác có thể thay thế entry giữa bước kiểm tra và bước xóa. Đây là dạng time-of-check to time-of-use (*TOCTOU*). `NOFOLLOW_LINKS` giúp không đi theo symbolic link khi đọc thuộc tính, nhưng không biến cả chuỗi kiểm tra và xóa thành một thao tác nguyên tử.

Giảm rủi ro bằng cách:

- Giữ thư mục cha chỉ cho service account hoặc quản trị viên tin cậy ghi.
- Khóa single-instance trước khi kiểm tra và dọn.
- Không dùng pathname trong thư mục dùng chung có quyền ghi rộng.
- Chỉ xóa entry đã xác minh theo quy tắc của nền tảng.
- Không cho client group quyền quản lý entry trong thư mục chứa socket.

Nếu không thể chứng minh pathname là stale và thuộc service, dừng khởi động với lỗi rõ ràng để quản trị viên xử lý. Dừng an toàn tốt hơn xóa nhầm endpoint của process khác.

## 9. Shutdown hook và crash recovery

Có thể đăng ký shutdown hook để yêu cầu server đóng channel và xóa pathname khi JVM shutdown bình thường. Nhưng shutdown hook không được bảo đảm chạy trong mọi tình huống:

- Process bị kill cưỡng bức.
- JVM crash hoặc native process crash.
- Máy mất điện hoặc kernel dừng đột ngột.
- Container bị dừng theo cách không cho JVM đủ thời gian shutdown.

Vì thế, shutdown hook chỉ là lớp cleanup bổ sung. Không dựa duy nhất vào hook hoặc `deleteOnExit` để xử lý stale socket. Startup vẫn phải có quy trình nhận diện trạng thái cũ và xác minh quyền sở hữu trước khi dọn.

Nếu service chạy dưới systemd hoặc một service manager tương tự, có thể cấu hình runtime directory được quản lý theo vòng đời service. Điều này giúp dọn cả thư mục khi service dừng theo quy trình quản lý, nhưng cần cấu hình rõ quyền owner/group và bảo đảm thư mục không chứa dữ liệu khác cần giữ lại.

## 10. Giới hạn và trường hợp đặc biệt của pathname

Một số điểm cần nhớ khi quản lý socket file:

- Độ dài pathname Unix-domain socket bị giới hạn theo hệ điều hành; giới hạn thường xấp xỉ 100 byte nhưng khác nhau theo nền tảng. Thư mục tạm quá dài có thể khiến bind tự động thất bại.
- `bind(null)` tạo địa chỉ tự động cho server; lấy đường dẫn từ `getLocalAddress()` để cleanup.
- Client kết nối không bind local pathname thường là unnamed, không có socket file cục bộ cần xóa.
- File socket có thể còn sau khi process dừng đột ngột; lần bind tiếp theo vào tên đó không tự ghi đè file cũ.
- Việc xóa pathname cần quyền trên thư mục cha, không chỉ quyền trên socket file.
- Filesystem, container mount và namespace có thể ảnh hưởng đến pathname mà server nhìn thấy.

Đối với pathname cố định, nên đặt socket trong thư mục runtime chuyên dụng với đường dẫn ngắn và quyền hạn chế. Tránh đặt socket sâu trong cây thư mục dài không cần thiết.

## 11. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Đóng `ServerSocketChannel` tự xóa socket file. | **Sai** | Pathname vẫn tồn tại sau khi channel đóng. |
| Chỉ cần gọi `Files.deleteIfExists` trước khi đóng channel. | **Sai** | Phải đóng channel trước rồi mới xóa pathname. |
| Bind thất bại nghĩa là pathname cũ chắc chắn là socket stale. | **Sai** | Có thể là server đang hoạt động hoặc file khác loại. |
| `bind(null)` không tạo file cần cleanup. | **Sai** | Server được tự động bind vào pathname tạm và file vẫn tồn tại sau close. |
| `BasicFileAttributes.isOther()` chứng minh file là Unix socket. | **Sai** | Nó chỉ phân loại chung các special file. |
| Shutdown hook luôn chạy khi process kết thúc. | **Sai** | Crash hoặc kill cưỡng bức có thể bỏ qua cleanup. |
| Thư mục runtime riêng và single-instance lock giảm race khi cleanup. | **Đúng** | Chúng giới hạn quyền thay thế pathname và phối hợp các instance hợp tác. |
| Xóa socket pathname khi listener vẫn chạy là vô hại. | **Sai** | Client mới có thể mất khả năng tìm endpoint theo tên. |

## 12. Checklist dọn socket pathname

1. Server đã bind pathname cố định hay dùng `bind(null)`?
2. Đã lưu chính xác pathname sau khi bind, kể cả địa chỉ tự động chưa?
3. Channel có được đóng trước khi gọi `Files.deleteIfExists` không?
4. Chỉ cleanup khi bind của instance hiện tại đã thành công không?
5. Nếu bind thất bại, có tránh xóa pathname chưa xác minh không?
6. Startup có kiểm tra file hiện có mà không follow symbolic link không?
7. Có phân biệt `isOther()` với xác nhận socket file thật không?
8. Owner và quyền của thư mục cha có giới hạn process có thể thay pathname không?
9. Nhiều instance có được phối hợp bằng lock hoặc service manager không?
10. Cleanup có xử lý lỗi mà không che mất exception ban đầu không?
11. Có quy trình recovery khi JVM crash hoặc máy dừng đột ngột không?
12. Có tránh dựa duy nhất vào shutdown hook hoặc `deleteOnExit` không?

**Ghi nhớ:** Socket pathname tồn tại sau khi `ServerSocketChannel` đóng và phải được xóa riêng trước lần bind tiếp theo. Khi shutdown bình thường, đóng channel rồi mới xóa pathname do instance đã bind thành công. Khi khởi động và gặp file cũ, xác minh loại file, owner, thư mục cha và trạng thái instance; dùng thư mục runtime riêng cùng cơ chế single-instance để tránh race. Không xóa mù quáng một pathname có thể thuộc server đang chạy.

## Tài liệu chính thức

- [Java SE 26 API — `ServerSocketChannel.bind`, pathname socket tồn tại sau khi channel đóng](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html).
- [Java SE 26 API — `SocketChannel`, Unix-domain socket file lifecycle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html).
- [Java SE 26 API — `Files.deleteIfExists`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#deleteIfExists(java.nio.file.Path)).
- [Java SE 26 API — `BasicFileAttributes`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html).
- [Java SE 26 API — `FileLock`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/FileLock.html).
- [Java SE 26 Networking Properties — `jdk.net.unixdomain.tmpdir` và tự động bind server socket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/doc-files/net-properties.html).
- [JEP 380 — Unix-Domain Socket Channels, Java 16](https://openjdk.org/jeps/380).
- [Inside.java — JEP 380: Unix domain socket channels, lifecycle and pathname cleanup](https://inside.java/2021/02/03/jep380-unix-domain-sockets-channels/).
