# Quyền truy cập thư mục chứa socket và phân tách người dùng hệ điều hành

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Vận hành socket  
**Áp dụng:** Java 16 trở lên; ví dụ quyền file tập trung vào Linux/POSIX hiện đại.

Java 16 đưa Unix-domain socket vào API NIO chuẩn thông qua `UnixDomainSocketAddress`, `SocketChannel` và `ServerSocketChannel`. Unix-domain socket cho phép các tiến trình trên cùng hệ điều hành giao tiếp qua một đường dẫn trong filesystem, không cần mở cổng TCP.

Khi triển khai kiểu IPC này, quyền truy cập filesystem là một phần của ranh giới bảo mật. Tiến trình client phải đi qua các thư mục cha để tới socket; hệ điều hành kiểm tra quyền trên đường dẫn và, tùy nền tảng, quyền của socket file. Vì vậy cần thiết kế cả thư mục chứa socket, owner/group của socket và tài khoản chạy từng tiến trình.

Mục tiêu thường gặp là: một service chạy bằng tài khoản riêng, chỉ những user thuộc nhóm được phép mới kết nối, còn các user khác không thể đọc, thay thế hoặc xóa socket path.

## 1. Unix-domain socket dùng đường dẫn filesystem

Một server Java có thể bind socket vào một pathname:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Path;

static void runServer() throws IOException {
    Path socketPath = Path.of("/run/myapp/service.sock");

    try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
        server.bind(UnixDomainSocketAddress.of(socketPath));
        // server.accept() để nhận kết nối từ client.
    }
}
```

Client kết nối đến cùng địa chỉ:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

static void sendMessage() throws IOException {
    Path socketPath = Path.of("/run/myapp/service.sock");

    try (SocketChannel client =
             SocketChannel.open(StandardProtocolFamily.UNIX)) {
        client.connect(UnixDomainSocketAddress.of(socketPath));
        client.write(StandardCharsets.UTF_8.encode("hello"));
    }
}
```

Địa chỉ là một pathname, vì thế quyền trên mọi thư mục cha của pathname có thể ảnh hưởng đến việc kết nối. Trên Linux, client cần quyền search/execute trên từng thư mục trong đường dẫn và quyền write trên socket pathname để connect. Chi tiết kiểm tra quyền socket file có thể khác giữa các hệ điều hành và filesystem; không nên giả định mọi Unix-like platform có hành vi giống hệt Linux.

## 2. Phân biệt quyền trên thư mục và quyền trên socket file

Hai lớp quyền này kiểm soát các thao tác khác nhau:

| Vị trí | Quyền cần quan tâm | Ý nghĩa |
| --- | --- | --- |
| Mỗi thư mục cha | `x` (search/traverse) | Cho phép đi qua thư mục để truy cập pathname con. |
| Thư mục chứa socket | `w` + `x` | Cho phép tạo, xóa hoặc đổi tên entry trong thư mục. |
| Thư mục chứa socket | `r` | Cho phép liệt kê tên các entry; không bắt buộc nếu client đã biết chính xác pathname. |
| Socket pathname trên Linux | `w` | Cần cho client kết nối đến pathname socket. |
| Socket pathname | owner/group/mode/ACL | Quyết định user hoặc group nào được phép truy cập theo cơ chế của OS/filesystem. |

Một nhầm lẫn nguy hiểm là chỉ đặt mode của socket file rồi bỏ qua thư mục cha. Nếu client có quyền write và execute trên thư mục chứa socket, họ có thể xóa hoặc thay thế entry socket trong thư mục, dù bản thân socket file có mode hạn chế. Quyền tạo/xóa entry thuộc về thư mục cha.

Với service socket, thường chỉ service account cần quyền ghi thư mục. Client chỉ cần quyền traverse thư mục và quyền kết nối theo chính sách của hệ điều hành.

## 3. Dùng service account và group để phân tách user

Một mô hình phổ biến trên Linux:

- Service chạy bằng user chuyên dụng, ví dụ `appsvc`.
- Các client được phép kết nối thuộc group `appclients`.
- Thư mục runtime do service sở hữu, group là `appclients`.
- Group client có quyền traverse thư mục nhưng không có quyền ghi/xóa entry.
- Socket file cho owner và group được phép truy cập.
- User không thuộc group không có quyền traverse hoặc connect.

Ví dụ tạo thư mục runtime:

```sh
sudo install -d -o appsvc -g appclients -m 2710 /run/myapp
```

Mode `2710` có nghĩa:

- Chữ số `2`: bật setgid bit trên thư mục. Trên Linux, entry mới trong thư mục setgid thường kế thừa group của thư mục.
- Owner `appsvc`: `rwx`, có thể tạo socket và quản lý entry.
- Group `appclients`: `--x`, có thể traverse pathname đã biết nhưng không thể liệt kê hoặc thay đổi entry.
- Others: không có quyền.

Client thuộc `appclients` cần biết trước đường dẫn `/run/myapp/service.sock`. Nếu cần cho client liệt kê nội dung thư mục, có thể cấp thêm quyền `r` cho group, nhưng không cấp `w` nếu client không cần quản lý socket path.

Setgid inheritance và quyền trên pathname socket là hành vi hệ điều hành/filesystem. Ví dụ này mô tả cấu hình Linux; hãy kiểm tra lại owner, group, ACL và mode thực tế trên nền tảng triển khai.

## 4. Đặt quyền socket sau khi bind bằng Java NIO

Java SE cung cấp POSIX file permission API trên filesystem hỗ trợ POSIX. Có thể đặt mode socket sau khi bind:

```java
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

static void runServerWithPermissions() throws IOException {
    Path socketPath = Path.of("/run/myapp/service.sock");
    boolean bound = false;

    try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
        server.bind(UnixDomainSocketAddress.of(socketPath));
        bound = true;

        Files.setPosixFilePermissions(
            socketPath,
            PosixFilePermissions.fromString("rw-rw----")
        );

        // server.accept() để phục vụ client.
    } finally {
        if (bound) {
            // Chỉ xóa pathname do tiến trình này sở hữu
            // trong thư mục runtime được bảo vệ.
            Files.deleteIfExists(socketPath);
        }
    }
}
```

Mode `rw-rw----` tương ứng `0660`: owner và group có quyền đọc/ghi, user khác không có quyền. Trên Linux, quyền write trên pathname socket cho phép client trong group được kết nối. Group của socket cần được thiết lập đúng; thư mục setgid là một cách thường dùng để socket kế thừa group của thư mục.

Đoạn code minh họa một server xử lý vòng đời pathname. Trong ứng dụng thực tế, phần `accept()` thường chạy trong vòng lặp hoặc executor; chỉ dọn socket path sau khi server channel đã đóng và khi tiến trình có quyền sở hữu thư mục/path đó.

Có một khoảng thời gian giữa `bind()` và `setPosixFilePermissions()`. Vì vậy, cần tạo thư mục cha với quyền an toàn trước khi server bind. Trong ví dụ trên, group client không có quyền ghi thư mục, nên họ không thể thay thế socket pathname trong khoảng thời gian đó; client có thể chưa kết nối được cho đến khi mode socket được đặt xong.

`Files.setPosixFilePermissions` chỉ hoạt động trên filesystem hỗ trợ POSIX. Trên nền tảng không hỗ trợ, phương thức có thể ném `UnsupportedOperationException`; thao tác file cũng có thể thất bại với `IOException` hoặc `SecurityException`. Không giả định mode `0660` có cùng tác dụng trên mọi OS.

## 5. Không cấp quyền ghi thư mục cho client group

Xét hai cấu hình:

| Cấu hình thư mục | Owner | Group | Rủi ro |
| --- | --- | --- | --- |
| `2710 appsvc:appclients` | `rwx` | `--x` | Client có thể traverse pathname đã biết, không thể sửa entry. |
| `2770 appsvc:appclients` | `rwx` | `rwx` | Client group có thể tạo, xóa hoặc đổi tên entry trong thư mục. |

Nếu group client có `w+x` trên thư mục, một client bị xâm nhập có thể thử xóa hoặc thay thế pathname socket, làm gián đoạn service hoặc hướng client khác tới endpoint giả. Setgid bit chỉ giúp kế thừa group; nó không hạn chế thao tác xóa/đổi tên.

Vì thế, hãy tách quyền kết nối khỏi quyền quản lý thư mục:

- Client được quyền traverse thư mục và connect theo socket mode/ACL.
- Chỉ service account hoặc tiến trình quản trị tin cậy được quyền ghi thư mục.
- Không dùng group client làm owner có quyền ghi thư mục chỉ để client kết nối.

Sticky bit có thể hạn chế xóa entry của user khác trong một số thư mục dùng chung, nhưng không thay thế thiết kế thư mục runtime riêng do service quản lý.

## 6. Thư mục riêng an toàn hơn pathname trong thư mục dùng chung

Không nên đặt socket nhạy cảm trực tiếp trong một thư mục dùng chung mà mọi user đều có thể ghi, ví dụ một thư mục tạm có quyền rộng. Các rủi ro gồm:

- User khác có thể tạo trước pathname để làm server bind thất bại.
- User khác có thể thay thế hoặc xóa socket entry nếu quyền thư mục cho phép.
- Symlink hoặc pathname bị thay thế có thể dẫn đến hành vi ngoài dự kiến.
- Tên socket dễ bị dò thấy nếu thư mục cho phép liệt kê.

Hãy tạo thư mục runtime riêng, quyền được thiết lập trước khi bind. Trên Linux, `/run` thường là nơi phù hợp cho socket runtime của service nếu thư mục con được tạo với owner/group/mode đúng. Thư mục `/run` thường được làm sạch khi khởi động lại; service manager có thể tạo runtime directory với chính sách owner/group phù hợp.

Khi server khởi động mà pathname đã tồn tại, `bind()` có thể thất bại. Không xóa mù quáng pathname cũ: trước khi dọn, cần xác minh đó là socket stale thuộc service, nằm trong thư mục được bảo vệ và không phải file hoặc symlink do tiến trình khác tạo. Việc dọn dẹp an toàn phụ thuộc quyền sở hữu thư mục và quy trình quản lý service.

## 7. ACL và quyền nhóm cần được kiểm tra cùng nhau

Mode POSIX `rwx` không phải lúc nào cũng là toàn bộ chính sách truy cập. Filesystem có thể hỗ trợ ACL; một ACL entry có thể cấp hoặc hạn chế quyền cho user/group cụ thể ngoài cách nhìn đơn giản từ mode.

Trên Linux, có thể kiểm tra quyền thực tế bằng các công cụ hệ thống:

```sh
namei -l /run/myapp/service.sock
stat -c '%A %a %U:%G %n' /run/myapp /run/myapp/service.sock
getfacl /run/myapp /run/myapp/service.sock
```

Các lệnh này giúp kiểm tra từng thư mục trên đường dẫn, owner/group/mode và ACL. Nếu hệ thống dùng container, mount namespace hoặc bind mount, cần kiểm tra quyền từ namespace mà server và client thực sự chạy; quyền nhìn thấy trên host chưa chắc là toàn bộ góc nhìn của container.

Khi thay đổi group membership của user, tiến trình đang chạy có thể vẫn giữ danh sách group cũ. Cần khởi động lại session hoặc service theo quy trình quản trị để tiến trình nhận group membership mới.

## 8. Phân tách OS user không thay thế xác thực ở tầng ứng dụng

Quyền filesystem trả lời câu hỏi “user/group nào có thể mở kết nối đến socket path?”. Điều đó rất hữu ích để giới hạn bề mặt truy cập IPC, nhưng không tự cung cấp vai trò nghiệp vụ cho từng request.

Ví dụ, nếu nhiều user cùng thuộc group `appclients`, họ đều có thể được phép kết nối. Nếu service cần phân quyền khác nhau giữa từng client, cần thêm cơ chế nhận diện và authorization phù hợp:

- Xác thực client bằng credential ở giao thức ứng dụng.
- Dùng cơ chế peer credential của hệ điều hành nếu nền tảng và runtime hỗ trợ, đồng thời kiểm tra đúng API/version đang triển khai.
- Gắn quyền vào danh tính đã xác thực và kiểm tra quyền cho từng thao tác.
- Giới hạn group chỉ còn các user thực sự cần truy cập.

Không coi pathname bí mật hoặc quyền group là cơ chế xác thực người dùng ở cấp nghiệp vụ. Người có quyền connect vẫn có thể gửi request sai định dạng hoặc cố thực hiện thao tác vượt quyền nếu server không kiểm tra.

## 9. Lưu ý về vòng đời socket và dọn pathname

Đối với pathname Unix-domain socket, khi server đóng channel, entry filesystem có thể vẫn còn tùy nền tảng. Ứng dụng thường cần quản lý pathname khi shutdown và xử lý socket stale khi startup.

Các nguyên tắc an toàn:

1. Dùng một thư mục riêng mà chỉ service account có quyền ghi.
2. Chỉ bind một pathname cố định đã được cấu hình.
3. Không xóa file bất kỳ chỉ vì tên trùng socket mong đợi.
4. Xác minh loại file, owner và thư mục cha trước khi dọn socket stale.
5. Chỉ xóa pathname sau khi server channel đã đóng.
6. Giữ quyền thư mục an toàn trong toàn bộ vòng đời, kể cả lúc restart.

Nếu nhiều instance service có thể chạy đồng thời, cần thiết kế lock/ownership hoặc pathname riêng cho từng instance. Không để hai instance tranh nhau một pathname và không để cleanup của instance cũ xóa socket của instance mới.

## 10. Ma trận quyền mẫu cho service và client

Ví dụ một cấu hình Linux có service user `appsvc`, group client `appclients`:

| Đối tượng | Owner | Group | Mode | Mục đích |
| --- | --- | --- | --- | --- |
| `/run/myapp` | `appsvc` | `appclients` | `2710` | Service quản lý entry; client chỉ traverse. |
| `service.sock` | `appsvc` | `appclients` | `0660` | Service và client group được truy cập socket theo Linux pathname permission. |
| User không thuộc group | — | — | Không có quyền | Không thể traverse thư mục hoặc kết nối qua path. |

Đây là một điểm xuất phát, không phải mode phổ quát cho mọi ứng dụng. Nếu client cần liệt kê thư mục, group cần quyền `r`; nếu chỉ cần connect bằng pathname đã biết, quyền `x` có thể đủ. Nếu cần giới hạn chặt hơn theo từng user, cân nhắc ACL hoặc socket path riêng.

## 11. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Chỉ cần đặt mode cho socket file là đủ bảo vệ pathname. | **Sai** | Quyền traverse và quyền ghi thư mục cha cũng quyết định khả năng truy cập/thay thế entry. |
| Client cần quyền ghi thư mục chứa socket để kết nối. | **Sai** | Trên Linux, client cần traverse thư mục và quyền write trên socket path; không cần ghi thư mục cha. |
| Setgid bit ngăn client xóa socket. | **Sai** | Setgid hỗ trợ group inheritance, không phải cơ chế cấm xóa entry. |
| Record Java tự cung cấp quyền socket. | **Sai** | Quyền truy cập socket do OS/filesystem kiểm soát. |
| `Files.setPosixFilePermissions` chạy trên mọi filesystem. | **Sai** | Chỉ dùng được khi filesystem hỗ trợ POSIX permissions. |
| User cùng group được phép connect có cùng quyền nghiệp vụ. | **Sai** | Group chỉ là lớp kiểm soát truy cập OS; server vẫn cần authorization cho request. |
| Thư mục riêng không cho client ghi giúp giảm nguy cơ thay thế pathname. | **Đúng** | Client không có quyền tạo/xóa/đổi tên entry trong thư mục. |

## 12. Checklist triển khai

1. OS và filesystem đích có hỗ trợ Unix-domain socket và pathname socket không?
2. Server chạy bằng service account riêng, không cần chạy root không?
3. Thư mục cha được tạo trước khi bind và có owner/group/mode phù hợp không?
4. Client có quyền `x` trên mọi thư mục cha không?
5. Client group có bị cấp `w` trên thư mục chứa socket không?
6. Socket file có owner/group/mode hoặc ACL đúng sau khi bind không?
7. Group inheritance trên thư mục setgid có được xác minh trên OS đích không?
8. Có kiểm tra ACL và quyền thực tế từ đúng user/container namespace không?
9. Startup có xử lý stale pathname an toàn, không xóa mù quáng không?
10. Shutdown có đóng channel trước khi xóa pathname không?
11. Nhiều instance có thể tranh cùng socket path không?
12. Service có xác thực và phân quyền ở tầng ứng dụng nếu cần nhận diện từng client không?

**Ghi nhớ:** Hãy bảo vệ cả socket file lẫn thư mục cha. Một cấu hình Linux thường dùng là thư mục runtime do service sở hữu, setgid để kế thừa group client, group chỉ có quyền traverse và socket file có mode cho phép group kết nối. Dùng Java NIO chuẩn từ Java 16 để bind/connect, kiểm tra POSIX permission và ACL trên hệ điều hành triển khai, đồng thời giữ quyền quản lý pathname ở service account. Quyền filesystem giới hạn ai có thể kết nối; server vẫn phải kiểm tra quyền của từng request theo yêu cầu nghiệp vụ.

## Tài liệu chính thức

- [JEP 380 — Unix-Domain Socket Channels](https://openjdk.org/jeps/380).
- [Java SE 26 API — `UnixDomainSocketAddress`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/UnixDomainSocketAddress.html).
- [Java SE 26 API — `StandardProtocolFamily.UNIX`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardProtocolFamily.html).
- [Java SE 26 API — `ServerSocketChannel`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html).
- [Java SE 26 API — `Files.setPosixFilePermissions`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#setPosixFilePermissions(java.nio.file.Path,java.util.Set)).
- [Linux man-pages — `unix(7)`, pathname socket permissions](https://man7.org/linux/man-pages/man7/unix.7.html).
- [Linux man-pages — `path_resolution(7)`, directory search permissions](https://man7.org/linux/man-pages/man7/path_resolution.7.html).
