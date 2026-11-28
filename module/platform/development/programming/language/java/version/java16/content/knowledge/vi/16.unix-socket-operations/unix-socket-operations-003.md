# Tránh xóa nhầm endpoint khi nhiều tiến trình cùng khởi động

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Vận hành socket  
**Áp dụng:** Java 16 trở lên; ví dụ pathname và metadata socket tập trung vào Linux/POSIX hiện đại.

Unix-domain socket dùng pathname trong filesystem để client tìm thấy server. Khi nhiều instance cùng khởi động, chúng có thể đồng thời thấy pathname tồn tại, cùng kết luận đó là socket cũ rồi xóa nó. Một instance có thể vô tình xóa endpoint mà instance khác vừa bind hoặc đang phục vụ.

Đây là race condition giữa các bước kiểm tra, xóa và bind (*check-then-act*). Chỉ kiểm tra PID, chỉ gọi `Files.exists()` hoặc chỉ bắt lỗi bind không đủ để xác định ai sở hữu pathname.

Một thiết kế an toàn cần có quy tắc sở hữu rõ ràng:

1. Mọi instance của cùng service phải lấy cùng một exclusive lock trước khi kiểm tra hoặc thay đổi socket pathname.
2. Instance giữ lock mới được kiểm tra stale path, bind, phục vụ và cleanup.
3. Lock được giữ suốt vòng đời listener, không chỉ trong vài dòng startup.
4. Chỉ xóa pathname mà instance đã bind thành công hoặc stale socket đã được xác minh theo chính sách nền tảng.
5. Thư mục runtime phải do service quản lý và không cho tiến trình không tin cậy thay thế entry.

## 1. Vì sao kiểm tra rồi xóa có thể phá endpoint đang chạy?

Giả sử hai instance A và B cùng dùng `/run/myapp/service.sock`:

| Thời điểm | Instance A | Instance B |
| --- | --- | --- |
| T1 | Kiểm tra pathname thấy tồn tại | |
| T2 | | Kiểm tra cùng pathname thấy tồn tại |
| T3 | Kết luận file cũ và xóa | |
| T4 | Bind pathname thành công, bắt đầu listen | |
| T5 | | Xóa pathname dựa trên kết quả kiểm tra cũ |
| T6 | Listener A vẫn mở nhưng pathname đã mất | Bind pathname mới thành công |

Sau T5, A có thể vẫn giữ channel đang mở, nhưng client mới không còn tìm thấy A bằng pathname. B lại tạo một endpoint khác cùng tên. Client sẽ kết nối tới endpoint nào phụ thuộc trạng thái filesystem tại thời điểm kết nối.

Vấn đề nằm ở chỗ thao tác kiểm tra và xóa không phải một giao dịch nguyên tử. Một instance không được quyền xóa pathname chỉ vì nó đã tồn tại khi instance đó kiểm tra.

## 2. Dùng một lock file chung cho mọi instance

Java NIO cung cấp `FileChannel` và `FileLock` để các process phối hợp quyền sở hữu một file hoặc vùng byte. Với service dùng một pathname cố định, có thể tạo lock file riêng trong thư mục runtime:

```java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

static FileLock acquireInstanceLock(FileChannel channel)
        throws IOException {
    try {
        FileLock lock = channel.tryLock();
        if (lock == null) {
            throw new IOException("Another service instance is starting or running");
        }
        return lock;
    } catch (OverlappingFileLockException alreadyLockedInThisJvm) {
        throw new IOException(
            "Another thread in this JVM already owns the service lock",
            alreadyLockedInThisJvm
        );
    }
}

static void runWithLock(Path runtimeDir) throws IOException {
    Path lockPath = runtimeDir.resolve("service.lock");

    try (FileChannel lockChannel = FileChannel.open(
             lockPath,
             StandardOpenOption.CREATE,
             StandardOpenOption.WRITE
         )) {
        FileLock lock = acquireInstanceLock(lockChannel);
        try (lock) {
            // Chỉ thực hiện startup/cleanup socket khi đang giữ lock.
            runSocketLifecycle(runtimeDir);
        }
    }
}

static void runSocketLifecycle(Path runtimeDir) throws IOException {
    // Kiểm tra stale path, bind, phục vụ và cleanup tại đây.
}
```

Mọi instance phải dùng cùng một `service.lock` và cùng quy ước khóa. Nếu một instance bỏ qua lock, lock không thể ngăn instance đó thay đổi pathname.

`tryLock()` trả về `null` khi một process khác đang giữ vùng khóa tương ứng. Nếu cùng JVM đã giữ một vùng khóa chồng lấn, lời gọi có thể ném `OverlappingFileLockException`; vì vậy cần xử lý cả hai trường hợp. Không coi `null` là tín hiệu để xóa socket cũ: đó là tín hiệu instance hiện tại không có quyền tiếp tục startup.

## 3. Giữ lock trong toàn bộ vòng đời socket

Không nhả lock ngay sau khi bind. Nếu A bind xong rồi nhả lock, B có thể lấy lock, thấy pathname tồn tại và xóa endpoint mà A vẫn đang dùng.

Lock cần bao trùm cả:

- Xác minh hoặc dọn pathname cũ.
- Bind server channel.
- Toàn bộ thời gian listener đang hoạt động.
- Đóng channel và xóa pathname của instance hiện tại.

Ví dụ cấu trúc:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

static void runSingleInstance(Path runtimeDir) throws IOException {
    Path lockPath = runtimeDir.resolve("service.lock");
    Path socketPath = runtimeDir.resolve("service.sock");

    try (FileChannel lockChannel = FileChannel.open(
             lockPath,
             StandardOpenOption.CREATE,
             StandardOpenOption.WRITE
         )) {
        FileLock lock = acquireInstanceLock(lockChannel);
        try (lock) {
            removeVerifiedStaleSocket(socketPath);

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
    }
}

static void serve(ServerSocketChannel server) throws IOException {
    // Vòng lặp accept và xử lý request.
}

static void removeVerifiedStaleSocket(Path socketPath)
        throws IOException {
    // Chỉ xóa sau khi đã xác minh theo chính sách của nền tảng.
}
```

Thứ tự đóng tài nguyên là: server channel đóng trước, pathname được cleanup trong `finally`, sau đó lock được nhả khi thoát khỏi `try (lock)`. Instance khác chỉ lấy được lock sau khi cleanup của instance hiện tại đã hoàn tất.

Nếu `bind()` thất bại, `bound` vẫn là `false`, nên `finally` không xóa pathname mà instance hiện tại không tạo. Đây là điều kiện quan trọng để tránh xóa endpoint của process khác khi startup thất bại.

Trong production, hãy bảo đảm lỗi cleanup không che mất exception chính. Nếu xử lý server đã thất bại và xóa pathname cũng lỗi, gắn lỗi cleanup vào exception chính bằng `addSuppressed()` và ghi log để vận hành xử lý.

## 4. Lock file còn lại sau crash không phải stale lock

Một file `service.lock` có thể vẫn tồn tại sau khi process kết thúc. Điều này bình thường:

- `FileLock` là trạng thái khóa do hệ điều hành quản lý, không phải nội dung đánh dấu trong file.
- Khi process hoặc channel giữ lock kết thúc, hệ điều hành giải phóng lock theo cơ chế của nền tảng.
- File pathname `service.lock` có thể vẫn tồn tại và được instance sau mở lại để lấy cùng lock.

Không xóa lock file sau khi nhả lock. Nếu A đang khóa file object cũ, một process xóa pathname rồi tạo file mới cho B khóa, A và B có thể đang khóa hai file object khác nhau dù tên pathname giống nhau. Khi đó cơ chế single-instance bị chia đôi.

Giữ lock file ổn định trong thư mục runtime. Chỉ dọn cả thư mục khi chắc chắn không còn instance hoặc process nào có thể sử dụng nó.

## 5. FileLock là cơ chế phối hợp, không phải ranh giới bảo mật tuyệt đối

File lock thường được dùng như cơ chế advisory trên các hệ điều hành phổ biến: những process tuân thủ cùng giao thức lock sẽ phối hợp với nhau. Nó không tự ngăn một process không hợp tác xóa hoặc thay pathname socket.

Các giới hạn cần hiểu:

- Mọi instance của service phải khóa đúng cùng file và cùng vùng khóa.
- Một process bỏ qua lock vẫn có thể thay đổi socket path nếu quyền filesystem cho phép.
- Filesystem hoặc môi trường triển khai có thể có giới hạn về hỗ trợ file lock; kiểm tra lỗi khi lấy lock.
- `OverlappingFileLockException` có thể xuất hiện giữa các thread trong cùng JVM.
- Không dùng file lock trên một file bị xóa và tạo lại trong lúc các instance đang phối hợp.

Nếu filesystem không hỗ trợ lock đáng tin cậy, hoặc service chạy qua nhiều host/volume có semantics không phù hợp, hãy dùng cơ chế điều phối singleton do service manager hoặc hệ thống orchestration cung cấp. Không chuyển sang xóa pathname không khóa như một phương án dự phòng.

## 6. Bảo vệ thư mục runtime để giảm race ngoài giao thức lock

Lock chỉ có tác dụng nếu các process khác không thể thay lock file hoặc socket pathname ngoài giao thức. Hãy đặt cả hai trong thư mục runtime riêng:

- Thư mục do service account sở hữu.
- Chỉ service account hoặc quản trị viên tin cậy có quyền ghi thư mục.
- Client group chỉ có quyền traverse nếu cần kết nối qua pathname đã biết.
- User không liên quan không có quyền tạo, xóa, đổi tên hoặc thay thế entry.
- Mọi instance dùng cùng runtime directory và cùng lock file.

Ví dụ Linux:

```sh
sudo install -d -o appsvc -g appclients -m 2710 /run/myapp
```

Trong ví dụ này, owner `appsvc` có toàn quyền quản lý entry. Group `appclients` chỉ có quyền traverse, không có quyền ghi thư mục. File `service.lock` nên chỉ cho service account ghi; socket file được cấp quyền kết nối theo chính sách group/ACL riêng.

Đừng cấp `w+x` trên thư mục chứa socket cho client chỉ vì họ cần kết nối. Quyền ghi thư mục cho phép thay đổi entry và có thể phá cơ chế sở hữu endpoint.

## 7. Chỉ dọn stale socket sau khi lấy được lock

Sau khi lấy exclusive lock, instance biết rằng không có instance hợp tác nào khác đang giữ lock. Nếu socket pathname vẫn còn, đó có thể là entry do lần chạy trước bị crash để lại.

Quy trình an toàn cần có các điều kiện:

1. Đã lấy lock thành công.
2. Thư mục runtime là thư mục riêng của service và không cho user không tin cậy ghi.
3. Pathname nằm đúng trong thư mục runtime đã cấu hình, không nhận tùy tiện từ request.
4. Entry hiện tại là socket file theo metadata của nền tảng.
5. Owner là service account mong đợi.
6. Chính sách triển khai bảo đảm mọi instance cùng service đều tuân thủ lock.
7. Nếu không xác minh được một điều kiện, dừng startup và yêu cầu xử lý vận hành; không xóa.

Java NIO portable cung cấp `BasicFileAttributes.isOther()`, nhưng phương thức này chỉ cho biết entry không phải regular file, directory hoặc symbolic link. Nó không xác nhận entry là Unix socket; FIFO và special file khác cũng có thể được phân loại là `other`.

Trên Linux, có thể kiểm tra loại file bằng thuộc tính Unix-specific `unix:mode`. Ví dụ dưới đây chỉ dành cho filesystem Linux/Unix hỗ trợ thuộc tính này:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

static void removeVerifiedStaleSocketLinux(
        Path socketPath,
        int expectedServiceUid
) throws IOException {
    try {
        int mode = (Integer) Files.getAttribute(
            socketPath,
            "unix:mode",
            LinkOption.NOFOLLOW_LINKS
        );
        int ownerUid = (Integer) Files.getAttribute(
            socketPath,
            "unix:uid",
            LinkOption.NOFOLLOW_LINKS
        );

        int fileType = mode & 0170000;
        int socketType = 0140000;

        if (fileType != socketType) {
            throw new IOException("Existing path is not a Unix socket");
        }
        if (ownerUid != expectedServiceUid) {
            throw new IOException("Socket owner does not match service account");
        }

        Files.delete(socketPath);
    } catch (NoSuchFileException alreadyAbsent) {
        // Không có stale entry; có thể tiếp tục bind.
    }
}
```

Các hằng số `0170000` và `0140000` là bit mask/file type của Unix mode trên Linux: mask lấy phần loại file, giá trị socket biểu thị Unix socket. Đây là kiểm tra đặc thù nền tảng, không phải API Java portable. Cần xác nhận quyền sở hữu thư mục và lock trước khi gọi; kiểm tra metadata riêng lẻ không loại bỏ TOCTOU trong thư mục mà process khác có thể ghi.

Trên hệ điều hành khác, dùng cơ chế quản trị/metadata tương ứng. Nếu không có cách xác minh đáng tin cậy loại socket và owner, không tự động xóa entry chỉ dựa trên `isOther()`.

## 8. PID file và health check không thay thế lock

PID file hữu ích cho vận hành, nhưng không phải bằng chứng đầy đủ về quyền sở hữu pathname:

- PID có thể được tái sử dụng sau khi process cũ kết thúc.
- PID trong container hoặc namespace có thể khác PID nhìn từ host.
- PID file có thể còn lại sau crash hoặc bị ghi dở.
- Kiểm tra process còn tồn tại không chứng minh process đó đang giữ socket pathname mong đợi.

Health check bằng cách kết nối tới socket có thể xác nhận có endpoint phản hồi tại thời điểm kiểm tra. Nhưng kết nối thất bại không luôn chứng minh socket stale: server có thể đang khởi động, backlog đầy, quyền truy cập bị từ chối hoặc endpoint tạm thời không sẵn sàng. Kết nối thành công cũng chưa xác định endpoint thuộc đúng instance nếu giao thức không xác thực danh tính.

Hãy dùng lock làm cơ chế điều phối các instance hợp tác; dùng PID, health check và log như dữ liệu chẩn đoán bổ sung. Không dùng chúng làm lý do duy nhất để xóa pathname.

## 9. Xử lý nhiều instance trong cùng JVM

Nếu ứng dụng khởi động nhiều server instance trong cùng JVM, `FileChannel.tryLock()` trên vùng đã bị thread khác trong JVM khóa có thể ném `OverlappingFileLockException` thay vì trả `null`.

Điều này không nên bị bỏ qua. Có hai lựa chọn thiết kế:

- Chỉ cho phép một server instance trong JVM và báo lỗi rõ khi instance thứ hai khởi động.
- Dùng một cơ chế điều phối cấp JVM, chẳng hạn `synchronized`, `ReentrantLock` hoặc singleton lifecycle manager, kết hợp với `FileLock` để phối hợp cả process khác.

Không chỉ bắt exception rồi tiếp tục bind. Nếu thread thứ hai bỏ qua lỗi lock, chính ứng dụng đã phá quy tắc single-instance của mình.

## 10. Khi nào dùng service manager hoặc orchestration?

Với service production, cơ chế quản lý instance bên ngoài có thể đơn giản và đáng tin cậy hơn:

| Môi trường | Cơ chế phù hợp |
| --- | --- |
| Linux service đơn trên một host | systemd unit đơn nhất, runtime directory và quyền owner/group rõ ràng. |
| Nhiều bản sao container trên một node | Orchestrator quản lý replica; mỗi instance có socket path/runtime directory riêng nếu cùng host namespace. |
| Nhiều host | Không chia sẻ pathname Unix socket qua mạng; dùng IPC/network abstraction phù hợp hoặc một dịch vụ điều phối. |
| Nhiều instance cùng JVM | Lifecycle manager cấp JVM cộng với lock liên process nếu cần. |

Không để hai replica cùng dùng một socket pathname trong shared volume mà không có thiết kế ownership/locking rõ ràng. Unix-domain socket là endpoint cục bộ của kernel và filesystem namespace; không nên coi file socket như một file dữ liệu bình thường có thể chia sẻ giữa host.

## 11. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Kiểm tra `Files.exists()` rồi xóa là đủ an toàn. | **Sai** | Process khác có thể bind hoặc thay pathname giữa hai thao tác. |
| Instance lấy được lock mới được dọn stale socket. | **Đúng** | Lock là điểm điều phối chung của các instance hợp tác. |
| Chỉ cần giữ lock trong lúc bind. | **Sai** | Instance khác có thể xóa endpoint trong lúc listener vẫn chạy. |
| Lock file còn sau crash chứng minh lock vẫn đang bị giữ. | **Sai** | File có thể tồn tại; trạng thái khóa do OS quản lý và được giải phóng khi process kết thúc. |
| Có thể xóa lock file sau mỗi lần shutdown. | **Sai** | Xóa/tạo lại file có thể khiến các process khóa những file object khác nhau. |
| `FileLock` ngăn cả process không hợp tác thay pathname. | **Sai** | File lock thường là advisory; cần bảo vệ thư mục filesystem. |
| PID file đủ để chứng minh server đang sở hữu socket. | **Sai** | PID có thể stale, tái sử dụng hoặc thuộc namespace khác. |
| `BasicFileAttributes.isOther()` chứng minh entry là socket. | **Sai** | Nó chỉ phân loại entry special, không xác định riêng Unix socket. |
| Không lấy được lock thì nên xóa socket cũ để thử lại. | **Sai** | Instance hiện tại chưa có quyền thay đổi endpoint. |

## 12. Checklist startup nhiều tiến trình

1. Tất cả instance có dùng cùng một lock file trong cùng runtime directory không?
2. Lock được lấy trước khi kiểm tra, xóa hoặc bind socket pathname chưa?
3. Lock có được giữ đến sau khi server channel đóng và cleanup hoàn tất không?
4. `tryLock()` đã xử lý cả `null` và `OverlappingFileLockException` chưa?
5. Lock file có được giữ ổn định, không xóa/tạo lại trong khi service chạy không?
6. Filesystem đích có hỗ trợ semantics lock mà ứng dụng cần không?
7. Runtime directory có chỉ cho service account hoặc quản trị viên tin cậy ghi không?
8. Stale path có được xác minh loại file và owner theo OS không?
9. Có tránh coi `isOther()`, PID file hoặc health check là bằng chứng duy nhất không?
10. Nếu không thể xác minh pathname, service có dừng an toàn và báo lỗi rõ ràng không?
11. Chỉ cleanup pathname nếu bind của instance hiện tại thành công chưa?
12. Service manager/orchestrator có thể quản lý singleton hoặc cấp path riêng cho từng replica không?

**Ghi nhớ:** Để tránh xóa nhầm endpoint khi nhiều tiến trình khởi động, hãy lấy exclusive lock chung trước khi đụng tới socket pathname và giữ lock đến hết cleanup. Chỉ instance giữ lock mới được xác minh stale path, bind và xóa pathname mà nó sở hữu. Kết hợp lock với runtime directory riêng, kiểm tra owner/file type theo nền tảng và quy tắc single-instance. PID, health check và `Files.exists()` chỉ là tín hiệu bổ sung; không dùng chúng để quyết định xóa endpoint.

## Tài liệu chính thức

- [Java SE 26 API — `FileChannel.tryLock`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/FileChannel.html#tryLock()).
- [Java SE 26 API — `FileLock`, phạm vi và semantics khóa file](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/FileLock.html).
- [Java SE 26 API — `OverlappingFileLockException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/OverlappingFileLockException.html).
- [Java SE 26 API — `Files.getAttribute` và `LinkOption.NOFOLLOW_LINKS`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#getAttribute(java.nio.file.Path,java.lang.String,java.nio.file.LinkOption...)).
- [Java SE 26 API — `BasicFileAttributes.isOther`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html#isOther()).
- [Java SE 26 API — `ServerSocketChannel.bind`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html#bind(java.net.SocketAddress,int)).
- [JEP 380 — Unix-Domain Socket Channels, Java 16](https://openjdk.org/jeps/380).
