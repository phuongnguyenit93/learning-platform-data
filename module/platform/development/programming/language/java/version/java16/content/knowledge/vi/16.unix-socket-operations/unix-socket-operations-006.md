# Xử lý BindException, ConnectException và lỗi quyền hệ tệp

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Vận hành socket  
**Áp dụng:** Java 16 trở lên; ví dụ Unix-domain socket dùng API NIO chuẩn, phần chẩn đoán quyền tập trung vào Linux/POSIX.

Unix-domain socket cho phép các tiến trình trên cùng máy giao tiếp qua một pathname trong filesystem. Khi triển khai, lỗi thường xuất hiện ở ba giai đoạn khác nhau: server bind địa chỉ, client connect tới địa chỉ và hệ điều hành kiểm tra quyền truy cập pathname.

Ba nhóm lỗi dễ gặp là:

- `BindException`: server không thể bind pathname, thường do địa chỉ đang được dùng hoặc entry đã tồn tại.
- `ConnectException`: client không thể thiết lập kết nối tới endpoint, ví dụ server chưa listen hoặc pathname không trỏ tới listener có thể kết nối.
- Lỗi quyền hệ tệp: tiến trình không có quyền traverse thư mục cha, tạo/xóa socket entry hoặc kết nối theo quyền của socket file.

Không nên xử lý tất cả bằng cách xóa socket file rồi thử lại. Cần xác định thao tác thất bại, exception class, cause, trạng thái server và quyền thực tế của user chạy process. Một pathname tồn tại có thể thuộc server đang hoạt động; xóa nhầm sẽ làm mất endpoint của server đó.

## 1. Xác định lỗi theo thao tác và exception class

Các exception thường gặp trong Java NIO:

| Exception | Quan hệ kế thừa | Tình huống thường gặp |
| --- | --- | --- |
| `BindException` | `SocketException` → `IOException` | Bind thất bại vì pathname đã được dùng hoặc OS từ chối bind vì xung đột địa chỉ |
| `ConnectException` | `SocketException` → `IOException` | Không thiết lập được kết nối tới listener |
| `SocketException` | `IOException` | Lỗi socket ở mức hệ điều hành/provider, có thể gồm lỗi quyền hoặc trạng thái endpoint |
| `AccessDeniedException` | `FileSystemException` → `IOException` | Thao tác filesystem bị từ chối, ví dụ tạo thư mục hoặc đặt permission |
| `NoSuchFileException` | `FileSystemException` → `IOException` | Pathname hoặc thành phần thư mục không tồn tại khi thao tác filesystem |
| `FileSystemException` | `IOException` | Lỗi file có thông tin file/reason phụ thuộc filesystem |
| `UnsupportedOperationException` | Runtime exception | Nền tảng hoặc filesystem không hỗ trợ thao tác/API được yêu cầu |

`ServerSocketChannel.bind` và `SocketChannel.connect` khai báo ném `IOException`. Lớp exception cụ thể và thông điệp phụ thuộc OS, filesystem và provider. Vì vậy:

- Ghi nhận class của exception, message, cause chain, operation và pathname.
- Dùng exception class để phân loại trước; dùng message để bổ sung chẩn đoán.
- Không viết logic nghiệp vụ dựa trên việc so sánh chính xác chuỗi như `"Address already in use"` hoặc `"Permission denied"`.
- Không giả định lỗi quyền khi connect luôn là `AccessDeniedException`; thao tác socket có thể trả về `SocketException` hoặc một subclass `IOException` khác.

## 2. Xử lý BindException khi server khởi động

Server bind một pathname bằng `ServerSocketChannel`:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Path;

static void startServer(Path socketPath) throws IOException {
    try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
        try {
            server.bind(UnixDomainSocketAddress.of(socketPath));
        } catch (java.net.BindException bindFailure) {
            throw new IOException(
                "Cannot bind Unix socket at " + socketPath
                    + "; inspect listener ownership and filesystem entry",
                bindFailure
            );
        }

        serve(server);
    }
}

static void serve(ServerSocketChannel server) throws IOException {
    // Vòng lặp accept và xử lý client của service.
}
```

Nếu bind thất bại, kiểm tra các khả năng:

1. Một instance khác của service đã bind cùng pathname.
2. Một process cũ vẫn đang chạy dù lần khởi động mới được kích hoạt.
3. Socket file còn sót từ lần chạy trước sau crash.
4. Pathname hiện có là regular file, directory hoặc symbolic link, không phải socket mong đợi.
5. Thư mục cha không tồn tại hoặc service account không có quyền tạo entry.
6. Pathname quá dài hoặc nền tảng/filesystem không hỗ trợ kiểu địa chỉ đang dùng.

`BindException` không tự chứng minh socket file là stale. Trước khi dọn, xác minh service instance đang hoạt động và quyền sở hữu pathname. Nếu dùng single-instance lock, lấy lock trước khi kiểm tra hoặc xóa stale path và giữ lock xuyên suốt vòng đời listener.

## 3. Kiểm tra pathname trước khi quyết định cleanup

Có thể đọc thuộc tính mà không đi theo symbolic link:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

static void inspectSocketPath(Path socketPath) throws IOException {
    BasicFileAttributes attributes;
    try {
        attributes = Files.readAttributes(
            socketPath,
            BasicFileAttributes.class,
            LinkOption.NOFOLLOW_LINKS
        );
    } catch (NoSuchFileException missing) {
        System.out.println("Socket pathname does not exist");
        return;
    }

    if (attributes.isSymbolicLink()) {
        throw new IOException("Socket pathname is a symbolic link");
    }
    if (attributes.isDirectory() || attributes.isRegularFile()) {
        throw new IOException("Path exists but is not a socket entry");
    }
    if (attributes.isOther()) {
        // Special file: cần xác minh loại file bằng metadata của OS.
        System.out.println("Path is a special filesystem entry");
    }
}
```

`BasicFileAttributes.isOther()` không xác nhận entry đó chắc chắn là Unix socket. FIFO và loại special file khác cũng có thể được phân loại là `other`. Java NIO chuẩn không cung cấp một phép kiểm tra portable để nhận diện socket file trên mọi filesystem.

Trên Linux, có thể kiểm tra file type bằng thuộc tính Unix-specific `unix:mode` và owner bằng `unix:uid`. Ví dụ:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

static boolean isLinuxSocketOwnedBy(Path path, int expectedUid)
        throws IOException {
    int mode = (Integer) Files.getAttribute(
        path, "unix:mode", LinkOption.NOFOLLOW_LINKS
    );
    int uid = (Integer) Files.getAttribute(
        path, "unix:uid", LinkOption.NOFOLLOW_LINKS
    );

    int fileType = mode & 0170000;
    int socketType = 0140000;
    return fileType == socketType && uid == expectedUid;
}
```

Đây là kiểm tra đặc thù Linux/Unix, không phải giải pháp portable. Ngay cả khi loại file và owner khớp, vẫn phải xác định không có process sống đang sử dụng endpoint trước khi xóa. Kiểm tra thuộc tính rồi xóa cũng có thể gặp TOCTOU nếu user khác được quyền ghi thư mục cha.

Chỉ cleanup stale path khi:

- Instance hiện tại đã giành được lock single-instance.
- Thư mục runtime được bảo vệ, user không tin cậy không thể thay entry.
- Pathname đúng với socket path do service cấu hình.
- Loại file và owner được xác minh theo nền tảng.
- Không có instance đang hoạt động sở hữu endpoint.

Nếu không đủ bằng chứng, dừng startup và báo lỗi để quản trị viên kiểm tra. Không xóa chỉ để làm cho lần bind tiếp theo thành công.

## 4. Xử lý ConnectException ở client

Client kết nối tới pathname:

```java
import java.io.IOException;
import java.net.ConnectException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

static SocketChannel openConnection(Path socketPath) throws IOException {
    SocketChannel client =
        SocketChannel.open(StandardProtocolFamily.UNIX);
    try {
        client.connect(UnixDomainSocketAddress.of(socketPath));
        return client;
    } catch (IOException failure) {
        try {
            client.close();
        } catch (IOException closeFailure) {
            failure.addSuppressed(closeFailure);
        }
        throw failure;
    }
}
```

`ConnectException` thường cần kiểm tra:

- Server chưa khởi động hoặc chưa bind/listen xong.
- Client dùng sai pathname hoặc cấu hình khác với server.
- Socket file đã bị xóa trong khi server vẫn đang giữ channel.
- Socket file còn sót nhưng không có listener hoạt động phía sau.
- Client không có quyền traverse một thư mục cha hoặc quyền connect theo socket file.
- Server đã đóng listener hoặc đang restart.

Thông điệp hệ điều hành có thể khác nhau. Pathname không tồn tại có thể được báo qua `ConnectException` hoặc lỗi `IOException` khác tùy nền tảng/provider. Hãy kiểm tra exception class và cause chain, sau đó xác minh path và trạng thái server.

## 5. Phân biệt server chưa sẵn sàng với socket stale

Một client được khởi động cùng lúc với server có thể connect quá sớm. Nếu kiến trúc cho phép startup song song, dùng readiness signal của service manager hoặc một cơ chế health/readiness ở tầng ứng dụng.

Nếu cần retry:

- Chỉ retry lỗi có thể tạm thời, chẳng hạn server đang khởi động hoặc restart.
- Giới hạn số lần thử; dùng exponential backoff có jitter để tránh nhiều client thử lại đồng thời.
- Giữ nguyên pathname cấu hình; không dò hoặc thử xóa các pathname khác.
- Không retry vô hạn với lỗi permission, sai path, protocol hoặc cấu hình.
- Không xem một lần connect thất bại là bằng chứng socket file stale.

Ví dụ retry với số lần thử giới hạn:

```java
import java.io.IOException;
import java.net.ConnectException;
import java.nio.channels.SocketChannel;
import java.nio.file.Path;

static SocketChannel connectWithRetry(Path socketPath, int maxAttempts)
        throws IOException, InterruptedException {
    if (maxAttempts < 1) {
        throw new IllegalArgumentException("maxAttempts must be positive");
    }

    long delayMillis = 25;
    IOException lastFailure = null;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return openConnection(socketPath);
        } catch (IOException failure) {
            if (!hasConnectFailure(failure)) {
                throw failure;
            }
            lastFailure = failure;
            if (attempt == maxAttempts) {
                break;
            }

            Thread.sleep(delayMillis);
            delayMillis = Math.min(delayMillis * 2, 500);
        }
    }

    throw new IOException(
        "Service did not become ready after " + maxAttempts + " attempts",
        lastFailure
    );
}

static boolean hasConnectFailure(Throwable failure) {
    for (Throwable current = failure;
            current != null;
            current = current.getCause()) {
        if (current instanceof ConnectException) {
            return true;
        }
    }
    return false;
}

static void sendRequest(Path socketPath) throws IOException, InterruptedException {
    try (SocketChannel client = connectWithRetry(socketPath, 5)) {
        // Gửi request và đọc response theo protocol của ứng dụng.
    }
}
```

`openConnection` là phương thức ở ví dụ trước: nó trả về channel đang kết nối thành công và đóng channel nếu connect thất bại. `sendRequest` sở hữu channel trả về và đóng nó sau khi hoàn tất. Mẫu này giới hạn số lần thử, nhưng không đặt deadline cho từng lần `connect()` blocking. Nếu cần deadline end-to-end nghiêm ngặt, dùng non-blocking channel với `Selector` và deadline monotonic như bài timeout trước. Ứng dụng thực tế nên dùng readiness signal nếu có, thêm jitter vào delay và xác định rõ lỗi nào trong môi trường đích được xem là transient. Không retry mọi `IOException` vì điều đó có thể che giấu lỗi cấu hình hoặc quyền.

## 6. Hiểu đúng lỗi quyền trên đường dẫn

Trên Linux, client kết nối tới pathname socket cần:

- Quyền search/execute (`x`) trên từng thư mục cha trong đường dẫn.
- Quyền write (`w`) trên socket pathname theo quy tắc pathname socket của Linux.

Client không cần quyền write trên thư mục chứa socket chỉ để connect. Quyền write trên thư mục cha cho phép tạo, xóa hoặc đổi tên entry; đó là quyền quản lý pathname và thường chỉ service account cần.

Server cần quyền write và execute trên thư mục chứa socket để tạo entry khi bind và xóa entry khi cleanup. Các thư mục cha khác cũng cần quyền traverse.

Ví dụ mô hình Linux:

```sh
sudo install -d -o appsvc -g appclients -m 2710 /run/myapp
```

Sau khi bind, socket có thể được cấp mode phù hợp, ví dụ `0660` với owner là service và group là client được phép. Cấu hình thực tế phải kiểm tra cả group, ACL, umask và chính sách của service manager.

Không cấp `777` cho thư mục hoặc socket để “sửa nhanh” lỗi permission. Cách đó mở rộng quyền tạo/xóa/thay endpoint cho user không liên quan và che giấu nguyên nhân cấu hình.

## 7. Phân biệt AccessDeniedException và lỗi socket-level

Các thao tác filesystem như tạo thư mục, đọc metadata, đặt POSIX permission hoặc xóa pathname có thể ném `AccessDeniedException`, `SecurityException` hoặc `IOException` khác.

Ví dụ:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

static void setSocketPermissions(Path socketPath) throws IOException {
    try {
        Files.setPosixFilePermissions(
            socketPath,
            PosixFilePermissions.fromString("rw-rw----")
        );
    } catch (AccessDeniedException denied) {
        throw new IOException(
            "Cannot change socket permissions; inspect owner and directory policy",
            denied
        );
    } catch (UnsupportedOperationException unsupported) {
        throw new IOException(
            "Filesystem does not support POSIX permissions",
            unsupported
        );
    }
}
```

Với thao tác `SocketChannel.connect`, OS/provider có thể báo từ chối quyền bằng `SocketException` hoặc một subclass `IOException` khác thay vì `AccessDeniedException`. Vì vậy, hãy phân biệt:

- Lỗi thao tác file: xem exception filesystem, file path, owner và quyền thư mục.
- Lỗi bind/connect: xem socket exception, trạng thái listener và quyền trên pathname.
- Lỗi runtime/security policy: kiểm tra `SecurityException` và chính sách sandbox/runtime nếu môi trường còn áp dụng.

Java 16 trở lên vẫn dùng NIO permission APIs chuẩn; `Files.setPosixFilePermissions` chỉ hoạt động trên filesystem hỗ trợ POSIX. Không giả định mode POSIX có cùng semantics trên Windows hoặc mọi filesystem.

## 8. Chẩn đoán trên Linux bằng công cụ hệ thống

Khi gặp lỗi, chạy các lệnh dưới đúng host/container namespace và user liên quan:

```sh
namei -l /run/myapp/service.sock
stat -c '%F %A %a %U:%G %n' /run/myapp /run/myapp/service.sock
getfacl /run/myapp /run/myapp/service.sock
ss -xlpn
```

Ý nghĩa:

- `namei -l` hiển thị từng thành phần đường dẫn và quyền traverse.
- `stat` cho biết loại file, mode, owner và group.
- `getfacl` hiển thị ACL bổ sung ngoài mode truyền thống.
- `ss -xlpn` liệt kê Unix socket và thông tin process nếu quyền hệ thống cho phép.

Nếu chạy trong container, kiểm tra từ namespace thực tế của service và client. Host có thể nhìn thấy pathname hoặc process khác với container. Kiểm tra cả bind mount, user namespace, group mapping và runtime directory mà container nhận được.

Trên hệ thống bật SELinux hoặc AppArmor, mode POSIX đúng vẫn chưa chắc đủ. Policy bảo mật có thể chặn truy cập; cần xem audit log và label/profile thay vì nới mode filesystem.

## 9. Quy trình chẩn đoán theo từng lỗi

| Triệu chứng | Kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| `BindException` | Có instance đang listen không? Path đã tồn tại và thuộc loại file nào? | Nếu listener đang hoạt động, không xóa. Nếu stale đã xác minh, cleanup dưới single-instance lock rồi bind lại một lần. |
| `ConnectException` | Server đã ready chưa? Path có đúng không? Có listener không? | Sửa path/startup order; retry có giới hạn nếu lỗi thực sự transient. |
| `AccessDeniedException` khi tạo/xóa/đặt mode | Owner, group, ACL và quyền thư mục cha | Sửa quyền đúng service account/group, không cấp quyền rộng. |
| `SocketException` khi connect có reason permission | Quyền traverse mọi thư mục, socket mode/ACL, SELinux/AppArmor | Kiểm tra quyền từ đúng user và namespace. |
| `NoSuchFileException` | Parent directory có tồn tại không? Runtime directory đã được tạo chưa? | Provision thư mục trước khi bind hoặc sửa cấu hình path. |
| `UnsupportedOperationException` | OS/filesystem/provider có hỗ trợ Unix socket hoặc POSIX attribute không? | Dùng nền tảng/filesystem hỗ trợ hoặc chọn transport phù hợp. |

Luôn ghi nhận operation (`bind`, `connect`, `set permissions`, `delete`), pathname, exception class, message và cause. Không ghi dữ liệu nhạy cảm trong request hoặc thông tin xác thực vào log.

## 10. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| `BindException` luôn có nghĩa socket cũ và có thể xóa ngay. | **Sai** | Một server khác có thể đang sử dụng pathname. |
| `ConnectException` luôn có nghĩa server đã tắt. | **Sai** | Sai path, stale entry, quyền hoặc trạng thái khởi động cũng có thể gây lỗi kết nối. |
| Mọi lỗi permission khi connect đều là `AccessDeniedException`. | **Sai** | Socket-level error có thể được biểu diễn bằng `SocketException` hoặc subclass khác. |
| Client cần quyền ghi thư mục chứa socket để connect trên Linux. | **Sai** | Client cần traverse thư mục cha và quyền trên socket pathname; không cần quản lý entry trong thư mục. |
| `BasicFileAttributes.isOther()` chứng minh pathname là socket. | **Sai** | Đây chỉ là phân loại special file tổng quát. |
| `Files.isWritable` là bằng chứng đầy đủ cho mọi ACL/security policy. | **Sai** | Đây là tín hiệu kiểm tra access hữu ích nhưng cần đối chiếu ACL và policy của OS. |
| Retry ConnectException vô hạn sẽ làm startup ổn định hơn. | **Sai** | Cần giới hạn số lần thử hoặc deadline tổng, backoff và phân loại lỗi transient. |
| Lock single-instance giúp tránh hai instance cùng cleanup pathname. | **Đúng** | Điều kiện là mọi instance tuân thủ cùng lock và giữ lock xuyên suốt lifecycle. |

## 11. Checklist xử lý lỗi

1. Lỗi xảy ra ở `bind`, `connect`, thao tác filesystem hay bước set permission?
2. Đã ghi nhận exception class, message, cause chain và pathname chưa?
3. Nếu là `BindException`, đã kiểm tra listener và owner trước khi cleanup chưa?
4. Nếu là `ConnectException`, đã xác minh server readiness và đúng pathname chưa?
5. Có kiểm tra mọi thư mục cha và quyền traverse của user client không?
6. Server account có quyền tạo/xóa entry trong runtime directory không?
7. Socket owner/group/mode và ACL có đúng chính sách không?
8. Có phân biệt stale socket với regular file, symlink và special file khác không?
9. Cleanup stale path có được bảo vệ bởi single-instance lock không?
10. Có kiểm tra container namespace, SELinux/AppArmor khi mode POSIX đã đúng không?
11. Retry có giới hạn số lần thử hoặc deadline tổng và chỉ áp dụng cho lỗi transient không?
12. Có tránh cấp `777` hoặc xóa pathname mù quáng không?

**Ghi nhớ:** Xử lý `BindException`, `ConnectException` và lỗi quyền bằng cách xác định chính xác thao tác thất bại, kiểm tra listener, pathname, owner/group/ACL và quyền traverse. Chỉ xóa stale socket khi đã xác minh nó thuộc service và đang giữ single-instance lock. Với client, xác nhận server đã ready và retry có giới hạn số lần thử hoặc deadline tổng. Không dựa vào message text, không cấp quyền rộng và không xóa endpoint chỉ để làm cho bind thành công.

## Tài liệu chính thức

- [Java SE 26 API — `BindException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/BindException.html).
- [Java SE 26 API — `ConnectException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/ConnectException.html).
- [Java SE 26 API — `SocketChannel.connect`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html#connect(java.net.SocketAddress)).
- [Java SE 26 API — `ServerSocketChannel.bind`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html#bind(java.net.SocketAddress,int)).
- [Java SE 26 API — `AccessDeniedException` và `FileSystemException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/AccessDeniedException.html).
- [Java SE 26 API — `Files.readAttributes` và `LinkOption.NOFOLLOW_LINKS`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#readAttributes(java.nio.file.Path,java.lang.Class,java.nio.file.LinkOption...)).
- [JEP 380 — Unix-Domain Socket Channels, Java 16](https://openjdk.org/jeps/380).
- [Linux man-pages — `unix(7)`, pathname socket permissions](https://man7.org/linux/man-pages/man7/unix.7.html).
- [Linux man-pages — `path_resolution(7)`, directory search permissions](https://man7.org/linux/man-pages/man7/path_resolution.7.html).
