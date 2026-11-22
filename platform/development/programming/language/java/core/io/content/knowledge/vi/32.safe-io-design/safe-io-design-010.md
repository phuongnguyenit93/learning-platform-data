# Phân biệt quyền hệ điều hành với các cơ chế bảo mật Java lịch sử

## 1. Vì sao phải phân biệt hai lớp bảo vệ?

Trong Java Core I/O, một ứng dụng đọc file, ghi log, tạo thư mục hay mở socket không chỉ chịu quy tắc của ngôn ngữ Java. Nó chạy **bên trong một tiến trình do hệ điều hành quản lý**, với tài khoản, quyền truy cập, mount, sandbox hoặc chính sách hệ thống cụ thể.

Ngày trước, Java còn có cơ chế **`SecurityManager` + `Policy` + `Permission` + `AccessController`** để hạn chế **code chạy trong cùng JVM** theo các quyền do Java xét. Cơ chế đó khác với quyền filesystem do hệ điều hành thực thi, và hiện không còn là hướng xây dựng sandbox mới:

- Trong **JDK 17**, `SecurityManager` và API liên quan được **deprecated for removal** theo **JEP 411**. Ở các JDK còn hỗ trợ, nếu không có Security Manager đang được bật, cơ chế policy kiểm tra quyền kiểu lịch sử không cung cấp lớp sandbox như nhiều ví dụ Java cũ mô tả.
- Từ **JDK 24**, `SecurityManager` bị **vô hiệu hóa vĩnh viễn** theo **JEP 486**: không thể bật bằng tùy chọn khởi động và không thể cài Security Manager mới lúc runtime; API cũ còn tồn tại trong một số phiên bản cho tương thích nhưng hành vi đã thay đổi.
- **Quyền của hệ điều hành vẫn hoạt động bình thường** trong cả hai trường hợp: nếu tiến trình không có quyền mở file, hệ điều hành/filesystem có thể từ chối dù JVM không có Security Manager.

Bài tập trung vào **thiết kế I/O an toàn**: hiểu ai thực sự cấp/từ chối quyền, xử lý lỗi đúng, quản lý danh tính tiến trình, giới hạn path và cách thay thế những kỳ vọng sai về Java sandbox lịch sử.

> **Quy tắc nhớ ngay:** “Không có `SecurityManager`” **không** có nghĩa Java có thể đọc mọi file. “Có `FilePermission`” **không** có nghĩa bạn đã cấp quyền ở hệ điều hành.

## 2. Hai lớp quyền: hình dung đường đi của một lệnh đọc

Một chương trình gọi:

```java
String text = Files.readString(
        Path.of("/srv/app/config.txt"),
        StandardCharsets.UTF_8);
```

Đây là đoạn minh họa, dùng import `java.nio.file.Files`, `Path` và `StandardCharsets`, cần xử lý `IOException`. Trên một JVM hiện đại, đường đi khái quát:

```text
Java application
   |
   | Files.readString(path)
   v
Java NIO provider / native filesystem API
   |
   v
Hệ điều hành + filesystem + mount
   |
   +-- Danh tính tiến trình: UID/GID, token/privileges...
   +-- Quyền file và thư mục: mode/ACL/ownership
   +-- Mount read-only, sandbox, container, security policy...
   |
   +-- Cho phép -> đọc được bytes
   |
   +-- Từ chối  -> lỗi I/O hoặc lỗi phù hợp provider
```

Trong một JVM **cũ có Security Manager đang hoạt động**, còn có thể có lớp kiểm tra `Permission` của Java trước khi tới hệ điều hành. Nhưng ngay cả khi Java cho phép, **OS vẫn có quyền từ chối**. Java permission là một lớp kiểm soát bổ sung, không phải “vé thông hành” để bỏ qua ACL của OS.

### Bảng đối chiếu

| Câu hỏi | Quyền hệ điều hành | Java Security Manager lịch sử |
|---|---|---|
| Ai áp đặt? | Kernel/filesystem/OS security subsystem | Cơ chế kiểm tra permission bên trong Java runtime khi được bật |
| Danh tính chính | User/group/token/process và quyền liên quan | ProtectionDomain, CodeSource, policy và ngữ cảnh stack |
| Đối tượng thường bảo vệ | File, directory, socket, process, device, syscall, mount | Thao tác Java được instrument để kiểm tra `Permission` |
| Ví dụ | POSIX mode, ACL, Windows access token + DACL | `FilePermission`, `SocketPermission`, `RuntimePermission` |
| Khi Java gọi Files.readString | OS kiểm tra khả năng mở/đọc | JDK cũ **có thể** xét Java permission nếu Security Manager đang bật |
| Có thể vượt OS ACL? | Không: OS là nguồn quyết định cuối cùng về tài nguyên | Không |
| Tình trạng trong JDK 24+ | Vẫn có hiệu lực | Security Manager không thể được bật |
| Phạm vi bảo vệ | Tiến trình, user, namespace, OS-level enforcement | Chủ yếu intended sandbox/kiểm soát code trong JVM theo mô hình lịch sử |

Một ứng dụng có thể có **thêm** xác thực, phân quyền nghiệp vụ, giới hạn tên file, kiểm soát tenant hoặc cơ chế trong thư viện. Những lớp đó **khác** cả quyền OS lẫn Security Manager cũ.

## 3. Quyền filesystem ở Linux/Unix: owner, group, others

Với filesystem hỗ trợ mô hình POSIX, file thường có owner, group và các bit quyền:

```text
-rw-r-----  1 appuser appgroup ... config.txt
 ||| ||| |||
 ||| ||| +++-- others: ---
 ||| +++------ group: r--
 +++---------- owner: rw-
```

Ba quyền cơ bản:

- `r` (read): được đọc nội dung file nếu việc truy cập đường dẫn đến được file và không bị lớp kiểm soát khác cấm.
- `w` (write): được sửa nội dung file khi cách mở và các điều kiện filesystem cho phép.
- `x` (execute): với file thực thi có ý nghĩa chạy file; với **thư mục**, có ý nghĩa **traverse/search** mục bên trong.

Quyền của **thư mục** đặc biệt quan trọng:

| Quyền thư mục | Ý nghĩa thường gặp trên POSIX |
|---|---|
| `r` | Liệt kê tên các mục khi điều kiện khác phù hợp |
| `w` | Thay đổi directory entries: tạo/xóa/đổi tên khi kết hợp các quyền cần thiết |
| `x` | Truy cập/traverse tên mục, cần để đi qua thư mục khi resolve path |

Vì thế một file có `r--` chưa chắc đọc được nếu tiến trình không có quyền đi qua thư mục cha. Tương tự, **xóa/rename một file** chủ yếu liên quan quyền trên thư mục chứa nó, không phải cứ file có bit `w` mới xóa được. Quy tắc cụ thể còn liên quan sticky bit, ACL, mount options, ownership và hệ thống bảo vệ khác.

### Các công cụ hệ điều hành (minh họa)

```bash
id
ls -ld /srv/app /srv/app/data
ls -l /srv/app/data/config.txt
stat /srv/app/data/config.txt
getfacl /srv/app/data/config.txt
```

Các lệnh là **ví dụ trên Linux/Unix**, có thể không được cài đầy đủ hoặc có output khác tùy hệ thống. `getfacl` có thể không có sẵn và filesystem có thể không hỗ trợ cùng kiểu ACL. Không chạy `chmod -R 777` hay cấp quyền rộng chỉ để “chữa lỗi Java”.

## 4. Quyền Windows: access token và ACL

Trên Windows, access check thường dựa vào **access token** của tiến trình/luồng và **security descriptor/DACL** của đối tượng file/folder; danh tính có thể bao gồm user, groups, integrity level và privilege đặc thù.

Một số khái niệm cần phân biệt:

- **Owner**: danh tính sở hữu đối tượng, có tác động tới quản trị quyền nhưng không đồng nghĩa được phép mọi thao tác trong mọi điều kiện.
- **DACL/ACE**: các entry allow/deny quyền với các principal; inheritance từ thư mục cha có thể ảnh hưởng.
- **Access token**: danh tính và privileges mà tiến trình thực sự đang dùng; “đang đăng nhập bằng tài khoản admin” không đồng nghĩa tiến trình luôn chạy với đầy đủ quyền elevated.
- **UAC, integrity levels, policy**: có thể bổ sung hạn chế; không quy tất cả lỗi `AccessDeniedException` về một ACE đơn giản.
- **File sharing/locking**: cách mở và handle của tiến trình khác có thể khiến rename/delete/open thất bại ngay cả khi ACL có vẻ cho phép.

`DosFileAttributeView` của Java NIO (read-only, hidden, system, archive) **không phải** bộ ACL đầy đủ của Windows. Đánh dấu read-only không thay thế cấu hình DACL. Muốn làm việc với ACL khi provider hỗ trợ, xem `AclFileAttributeView`, `AclEntry` và `UserPrincipalLookupService`.

Cách kiểm tra quyền Windows thường dùng công cụ quản trị hệ điều hành như `icacls`, PowerShell và giao diện Security của file/folder, với tài khoản chạy ứng dụng thực tế. Không dùng kết quả trên máy developer để suy luận quyền trên production server.

## 5. Java NIO kiểm tra/đọc metadata quyền như thế nào?

Java `java.nio.file.Files` cho phép tương tác với thuộc tính filesystem **khi provider hỗ trợ**:

| API | Mục đích |
|---|---|
| `Files.getOwner(path)` | Đọc owner của file |
| `Files.setOwner(path, principal)` | Yêu cầu đổi owner, cần OS cho phép |
| `Files.getPosixFilePermissions(path)` | Đọc bộ POSIX permissions nếu có view hỗ trợ |
| `Files.setPosixFilePermissions(path, perms)` | Yêu cầu sửa POSIX mode khi có quyền |
| `Files.getFileAttributeView(path, PosixFileAttributeView.class)` | Lấy view quản lý thuộc tính POSIX nếu provider hỗ trợ |
| `Files.getFileAttributeView(path, AclFileAttributeView.class)` | Lấy view ACL nếu được hỗ trợ |
| `Files.isReadable(path)` | Kiểm tra sơ bộ xem JVM có thể đọc file hay không |
| `Files.isWritable(path)` | Kiểm tra sơ bộ khả năng ghi |
| `Files.readAttributes(path, ...)` | Đọc các thuộc tính chỉ định qua provider |
| `Files.createTempFile(..., attrs)` | Có thể tạo file với attributes khởi tạo thích hợp và được hỗ trợ |

**Sử dụng API để xem/sửa quyền không làm JVM có quyền quản trị file vô hạn.** Lời gọi `setOwner` hay `setPosixFilePermissions` cũng bị OS kiểm tra. Khi không hỗ trợ, API có thể ném `UnsupportedOperationException` hoặc ngoại lệ khác theo hợp đồng.

### POSIX permissions trong Java (mã minh họa)

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;
import java.nio.file.attribute.PosixFilePermission;

Path path = Path.of("/srv/app/secrets.txt");

// Chỉ chạy trên filesystem/provider hỗ trợ POSIX attributes
// và khi tiến trình có quyền thay đổi permissions.
Set<PosixFilePermission> ownerOnly =
        PosixFilePermissions.fromString("rw-------");

Files.setPosixFilePermissions(path, ownerOnly);
```

Đây là **đoạn mã minh họa**, yêu cầu đặt trong method xử lý `IOException` và phải áp dụng với đối tượng được phép quản trị. Không áp dụng `setPosixFilePermissions` bừa lên file hệ thống hoặc nhầm `"rw-------"` với một “role” độc lập của ứng dụng.

### Kiểm tra provider

```java
var view = Files.getFileAttributeView(
        path,
        PosixFileAttributeView.class);

if (view != null) {
    Set<PosixFilePermission> permissions = view.readAttributes().permissions();
    System.out.println(PosixFilePermissions.toString(permissions));
}
```

Đây là snippet cần import `PosixFileAttributeView`, `PosixFilePermission`, `PosixFilePermissions` và xử lý lỗi. `view != null` chỉ nói provider có API tương ứng cho path; không hứa việc thay đổi permission sau đó sẽ luôn thành công.

## 6. isReadable/isWritable không phải cơ chế cấp quyền

`Files.isReadable(path)` và `Files.isWritable(path)` thường tiện cho UX hoặc quan sát, nhưng **không phải quyết định an ninh bất biến**.

Phản ví dụ:

```java
if (Files.isWritable(target)) {
    Files.writeString(target, content);
}
```

Trong khoảng giữa `isWritable` và `writeString`:

- ACL có thể thay đổi.
- File có thể bị xóa/đổi tên.
- Symlink có thể trỏ sang mục khác.
- Mount có thể chuyển sang read-only.
- Handle khác hoặc policy có thể thay đổi điều kiện thao tác.

Đây là **TOCTOU** (time-of-check to time-of-use). Check trả true không đảm bảo operation sau thành công. Check trả false cũng không nói chính xác vì sao: không tồn tại, không thể xác định, điều kiện truy cập không đủ, hoặc provider không trả lời đáng tin cậy.

Mẫu tốt hơn trong nhiều trường hợp là **thực hiện thao tác được phép trong ranh giới kiểm soát và xử lý ngoại lệ thực tế**:

```java
try {
    String text = Files.readString(target, StandardCharsets.UTF_8);
    // Xử lý text theo schema nghiệp vụ.
} catch (NoSuchFileException ex) {
    // File không còn tồn tại ở thời điểm mở/đọc.
} catch (AccessDeniedException ex) {
    // Filesystem/provider báo từ chối truy cập.
} catch (IOException ex) {
    // Các lỗi I/O khác.
}
```

Đây là đoạn code minh họa, cần imports/biến `target`. Không phải mọi provider trả đúng subclass `AccessDeniedException` khi bị từ chối; `IOException` tổng quát cũng cần được xử lý. Ở JDK 17 với Security Manager lịch sử được bật, một số API còn có thể ném `SecurityException` cho Java permission; không nên nhầm nó với OS ACL.

## 7. Java SecurityManager trong lịch sử hoạt động thế nào?

Trong các Java đời cũ, `SecurityManager` được thiết kế để kiểm soát một số hành động nhạy cảm của code Java theo **permission check**.

Ví dụ các khái niệm:

- `java.io.FilePermission`: biểu diễn quyền như `read`, `write`, `execute`, `delete` đối với file/path theo policy Java.
- `java.net.SocketPermission`: đại diện một số quyền network như connect/accept/listen/resolve trong cơ chế cũ.
- `java.lang.RuntimePermission`: quyền với một số khả năng runtime.
- `java.security.Policy`: nguồn chính sách map nguồn code/protection domain tới permissions.
- `java.security.AccessController` và `AccessControlContext`: liên quan tới stack-based access checks trong mô hình lịch sử.
- `ProtectionDomain`/`CodeSource`: mô tả code và miền quyền trong policy model.

Với Security Manager hoạt động, lời gọi Java I/O có thể đi qua `checkRead`/`checkWrite` hoặc `checkPermission` trước khi tới OS. Nếu policy Java từ chối, code có thể nhận `SecurityException` hoặc subclass. Nếu policy Java cho phép nhưng OS từ chối, I/O vẫn thất bại.

**Đừng lấy mã Java 8 với `System.setSecurityManager(new SecurityManager())` làm công thức cấu hình bảo mật ứng dụng mới.** Ở JDK 17 các API này đã bị deprecated for removal; từ JDK 24 không thể bật cơ chế ấy.

## 8. FilePermission của Java không phải chmod hay ACL

Đây là một lỗi diễn giải phổ biến. Với `java.io.FilePermission` (API lịch sử):

```java
import java.io.FilePermission;

FilePermission permission =
        new FilePermission("/srv/app/data/report.csv", "read");
```

Đoạn trên **chỉ tạo một đối tượng `Permission` trong JVM** để dùng trong mô hình Java security cũ. Nó **không**:

- Gọi `chmod`.
- Đặt POSIX mode `r--------` hay `rw-------`.
- Thêm một ACE vào Windows ACL.
- Cấp quyền truy cập cho process account.
- Làm OS bỏ qua mount read-only hoặc policy.
- Tự kích hoạt `SecurityManager`.
- Đảm bảo tệp tồn tại hoặc đọc được.

Ngược lại, `Files.setPosixFilePermissions(path, perms)` yêu cầu thay đổi **metadata quyền của filesystem**, nếu provider hỗ trợ và hệ điều hành cho phép.

Bảng minh họa:

| Code/khái niệm | Kết quả liên quan quyền |
|---|---|
| `new FilePermission(path, "read")` | Tạo Java permission object, không sửa OS |
| `Policy` cấp FilePermission (JDK cũ có Security Manager) | Có thể cho phép qua lớp Java policy nếu check liên quan được thực thi |
| `chmod 600 secret.txt` trên POSIX | Thay mode của file khi OS cho phép |
| `Files.setPosixFilePermissions(...)` | Thay POSIX permission qua NIO nếu provider hỗ trợ/quyền đủ |
| Windows `icacls` | Xem/sửa ACL theo khả năng và quyền hệ thống |
| Chạy service bằng user ít quyền | OS giới hạn tài nguyên mà process có thể sử dụng |
| Docker/container mount file read-only | Áp ràng buộc từ môi trường chạy theo cơ chế container/host |

Tên `Permission` trong Java rất dễ gây nhầm vì nó giống “permission” của OS. Cần luôn hỏi: **quyền thuộc lớp policy JVM lịch sử hay metadata/enforcement của OS?**

## 9. JDK 17, JDK 24 và hướng phát triển

Sự thay đổi của Security Manager có ý nghĩa trực tiếp khi đọc code, README, khóa học hoặc tutorial Java cũ.

| Dòng thời gian | Trạng thái cần biết |
|---|---|
| Các Java đời cũ | Có cơ chế Security Manager và policy được sử dụng trong một số môi trường sandbox/plugin |
| JDK 17 — JEP 411 | Security Manager cùng API liên quan **deprecated for removal**; không nên dùng cho thiết kế mới |
| JDK 18–23 | Tiếp tục quá trình chuyển dịch với các thay đổi/cảnh báo theo từng release; tham khảo docs phiên bản chính xác |
| JDK 24 — JEP 486 | **Permanently disable Security Manager**; không thể bật lúc startup hoặc runtime |
| JDK sau 24 | Theo hướng dẫn migration, Java native Security Manager không phải giải pháp sandbox cho ứng dụng hiện đại; API legacy có thể còn để chuyển tiếp nhưng không có cơ chế quản lý policy như trước |

Khi kiểm tra JVM thực tế:

```bash
java -version
```

Đừng viết một phần mềm mới yêu cầu `-Djava.security.manager=allow` để bảo vệ plugin rồi chạy nó trên JDK 24+: cơ chế này **không thể được bật**. Trên JDK 17, những cách bật/cấu hình còn tồn tại chủ yếu phục vụ tương thích/migration, không phải lời khuyên kiến trúc dài hạn.

### JEP 411 vs JEP 486

- **JEP 411 — Deprecate the Security Manager for Removal**: từ JDK 17, cảnh báo và định hướng loại bỏ.
- **JEP 486 — Permanently Disable the Security Manager**: JDK 24 chặn việc kích hoạt; các API liên quan có hành vi degraded để hỗ trợ quá trình chuyển tiếp.

**Permanently disabled không nhất thiết nghĩa mọi class API đã bị xóa khỏi bytecode ngay trong JDK 24.** Phải phân biệt “vô hiệu hóa chức năng” với “xóa class khỏi JDK”. Khi migration, kiểm tra release notes theo phiên bản đang sử dụng.

## 10. AccessController.doPrivileged từng dùng để làm gì?

Trong kiến trúc Security Manager lịch sử, stack-based checks có thể xem xét các protection domains trong call stack. `AccessController.doPrivileged` dùng để thực hiện đoạn code với ngữ nghĩa truy cập đặc biệt trong bối cảnh Java policy.

Ví dụ kiểu tài liệu cũ:

```java
String value = AccessController.doPrivileged(
        (PrivilegedAction<String>) () -> System.getProperty("user.home"));
```

**Đây là snippet lịch sử, không khuyến nghị cho code mới.** Cần import `AccessController` và `PrivilegedAction`, compiler JDK 17 có thể cảnh báo deprecated.

Điểm cần phân biệt:

- `doPrivileged` không cấp quyền đọc tệp theo OS cho process.
- Nó không giúp thoát khỏi UID/GID, Windows DACL, read-only mount hoặc sandbox của container.
- Từ JDK 24, khi Security Manager không còn hoạt động, các overload phổ biến của `doPrivileged` chỉ chạy action ngay theo hành vi không có Security Manager, không còn là ranh giới đặc quyền JVM như thiết kế ban đầu.
- Đừng dùng `doPrivileged` để “bọc” thao tác file bị `AccessDeniedException`; đó không phải cách sửa quyền hệ thống.

Khi thấy code legacy lạm dụng `doPrivileged`, hãy xem xét **loại bỏ phụ thuộc vào Security Manager**, rồi thiết kế quyền tiến trình/kiểm soát nghiệp vụ tương ứng thay vì chỉ xóa cảnh báo compiler.

## 11. Không có SecurityManager không đồng nghĩa JVM an toàn hoặc không an toàn tuyệt đối

Java runtime có những cơ chế an toàn khác với Security Manager:

- **Type safety, bytecode verification, access modifiers, module boundaries**: bảo vệ tính đúng đắn/giới hạn một số tương tác ở mức ngôn ngữ và runtime.
- **Quyền OS, process account, filesystem permissions, networking controls**: kiểm soát thực tế việc truy cập tài nguyên hệ thống.
- **Xác thực và phân quyền ứng dụng**: quyết định user/tenant nào được thực hiện thao tác nghiệp vụ.
- **Crypto, TLS, key management**: bảo vệ tính bí mật/toàn vẹn và xác thực theo giao thức.
- **Process isolation/container/VM**: tạo ranh giới độc lập hơn với các chương trình ít tin cậy.

Các cơ chế này giải quyết **những loại rủi ro khác nhau**, không thay thế tất cả lẫn nhau.

Một class `private` không ngăn cùng tiến trình có quyền OS đọc file mật khẩu nếu code có khả năng I/O và được gọi không đúng chỗ. Ngược lại, bảo vệ file bằng mode `600` cũng không ngăn chính ứng dụng có quyền đọc file ấy vô tình log secret ra ngoài hoặc gửi tới user sai tenant.

Đây là hai lớp kiểm tra cần độc lập: **authorization nghiệp vụ** và **authority của process**.

## 12. Chọn danh tính tiến trình theo nguyên tắc least privilege

Thay vì trông chờ Java policy để cấm từng thư viện, ứng dụng nên được chạy với **ít quyền hệ điều hành nhất đủ thực hiện công việc**.

Ví dụ service chỉ cần đọc file cấu hình và ghi log:

```text
Process identity: app-service

Allowed:
  /etc/my-app/config.yaml       read
  /var/lib/my-app/data/         read/write theo nghiệp vụ
  /var/log/my-app/              append/write theo chính sách
  outbound network             chỉ các đích được cho phép nếu có egress control

Not necessary:
  /root/, user home khác, /etc/shadow
  /var/run/docker.sock
  host device nodes
  quyền thay owner/chmod rộng
```

Một triển khai production có thể dùng:

- Dedicated service user, không chạy root/Administrator trừ khi có lý do bắt buộc.
- POSIX mode + ACL hoặc Windows DACL theo thư mục/file thực tế.
- Container run-as non-root; tránh mount thư mục host nhạy cảm và container privileged.
- Read-only root filesystem khi ứng dụng chỉ cần một vài writable directories.
- Giới hạn network egress/ingress, capabilities và namespace theo nền tảng.
- Secret injection và quyền đọc file secret hẹp; không đóng gói secret trực tiếp trong artifact.
- Audit logs và monitoring các lỗi `AccessDeniedException` mà không in nội dung bí mật.

**Process user trong container không tự động có cùng ý nghĩa với user trên host.** UID mapping, volume mounts, Kubernetes securityContext, SELinux/AppArmor và cấu hình platform cần được kiểm tra theo môi trường.

### Nguy hiểm của “chạy admin để hết AccessDenied”

Việc tăng quyền cho toàn bộ JVM có thể làm lỗi tạm biến mất nhưng **mở rộng blast radius** khi ứng dụng có path traversal, deserialization vulnerability hoặc dependency bị tấn công. Sửa quyền chính xác vào thư mục cần dùng, hoặc thay đổi vị trí lưu file theo cấu trúc phù hợp thay vì nâng đặc quyền toàn tiến trình.

## 13. Ví dụ Java 17+ hoàn chỉnh: thao tác file và giải thích ranh giới quyền

Chương trình sau chạy **không dùng SecurityManager**. Nó tạo file tạm dưới thư mục mà OS cho phép, viết và đọc bằng NIO, rồi minh họa một phép kiểm tra path **chỉ ở mức từ vựng (lexical)**. Ví dụ **không** cố tạo lỗi permission bằng cách thay quyền OS, vì kết quả phụ thuộc hệ điều hành/user/ACL.

Lưu tên **`OsVsJavaPermissionsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class OsVsJavaPermissionsDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("os-permissions-");
        Path file = directory.resolve("record.txt");

        try {
            Files.writeString(
                    file,
                    "approved-data\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            String loaded = Files.readString(
                    file, StandardCharsets.UTF_8);

            Path relative = Path.of("reports", "..", "record.txt");
            Path candidate = directory.resolve(relative).normalize();

            System.out.println("Read: " + loaded.strip());
            System.out.println("Lexically within directory: "
                    + candidate.startsWith(directory));
            System.out.println("Same normalized target: "
                    + candidate.equals(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac OsVsJavaPermissionsDemo.java
java OsVsJavaPermissionsDemo
```

**Stdout chính xác nếu OS cho phép tạo/đọc/ghi/xóa trong temp directory:**

```text
Read: approved-data
Lexically within directory: true
Same normalized target: true
```

Giải thích:

1. `Files.createTempDirectory` yêu cầu OS cấp phép tạo một thư mục tạm mới. Nếu temp dir không writable, chương trình có thể ném `IOException` trước khi in.
2. `CREATE_NEW` tạo file chưa tồn tại, tránh vô tình truncate một file có sẵn tại tên `record.txt`. Nó không tự cung cấp một sandbox chống các tấn công bằng đường dẫn ngoài thư mục tin cậy.
3. `Files.readString` đọc qua provider theo quyền thực của process. Không có Java `FilePermission` nào được sử dụng để “cấp” quyền OS.
4. `normalize()` bỏ phần `reports/..` ở mức cấu trúc chuỗi path; `startsWith(directory)` trả true cho ví dụ đơn giản này.
5. **Kiểm tra lexical trên không phải chứng minh chống symlink/TOCTOU**. Nó chỉ cho thấy một kỹ thuật lọc sơ bộ, tuyệt đối không dùng riêng cặp `normalize()+startsWith()` như ranh giới bảo mật hoàn chỉnh với path do attacker kiểm soát.
6. Mọi temp resources được xóa ở `finally` khi chương trình chạy bình thường. Khi kill đột ngột/crash, `finally` có thể không chạy; ứng dụng production cần chiến lược cleanup khác.

Mã này độc lập, dùng Java 17+ và không có thao tác admin; không đưa `SecurityManager` vào vì nó không phải nền tảng xây ứng dụng mới.

## 14. POSIX FileAttributeView: tạo file riêng tư từ đầu

Nếu file lưu secret trên provider hỗ trợ POSIX, có thể yêu cầu attributes khi **tạo file** thay vì tạo file với quyền rộng rồi sửa lại:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermissions;

Path directory = Path.of("/srv/app/secrets");

FileAttribute<?> ownerOnly =
        PosixFilePermissions.asFileAttribute("rw-------");

Path secret = Files.createTempFile(
        directory,
        ".secret-",
        ".tmp",
        ownerOnly);
```

Đây là **đoạn minh họa**, không chạy độc lập; thư mục phải tồn tại, có quyền tạo, và provider hỗ trợ POSIX attributes. Trên Windows filesystem/view không hỗ trợ, yêu cầu attributes có thể ném `UnsupportedOperationException`. Cần chọn biện pháp Windows ACL phù hợp chứ không bắt IOException rồi tự động tạo một file secret với quyền mặc định rộng.

**Lợi ích:** đặt permission trong thao tác tạo file (nếu provider hỗ trợ) giúp tránh khoảng thời gian file nhạy cảm tồn tại với permission không phù hợp trước lúc gọi `setPosixFilePermissions`.

Tuy nhiên, chế độ đọc/ghi thực tế vẫn có thể bị hạn chế bởi ACL/mount/SELinux, và root/elevated principal có thể có những quyền khác. `rw-------` không phải bảo đảm “không user nào khác trên thế giới có thể truy cập dưới mọi cơ chế”.

### Khi filesystem không hỗ trợ POSIX view

Đừng gắn chặt ứng dụng đa nền tảng vào `PosixFilePermissions` mà không kiểm tra môi trường. Có thể:

1. Xác định yêu cầu bảo mật của file.
2. Kiểm tra view/provider hỗ trợ.
3. Nếu yêu cầu “owner only” là bắt buộc nhưng không thể cấu hình, **fail closed** thay vì tạo file nhạy cảm với quyền không kiểm soát.
4. Dùng nền tảng lưu secret/ACL đúng OS hoặc chuyển sang môi trường có isolation phù hợp.

## 15. AccessDeniedException, SecurityException và các lỗi khác

Các lỗi Java I/O dễ bị hiểu nhầm:

| Loại lỗi | Thường thể hiện | Có luôn do Java SecurityManager? |
|---|---|---|
| `AccessDeniedException` | Filesystem/provider báo không được phép truy cập path | Không |
| `FileSystemException` | Vấn đề filesystem, có thể chứa reason/otherFile | Không |
| `NoSuchFileException` | Mục không tồn tại khi thao tác | Không |
| `FileAlreadyExistsException` | Tạo mới với tên đã tồn tại | Không |
| `SecurityException` | Lỗi quyền/kiểm soát đặc thù API/runtime, trong các JDK cũ có thể từ security manager | Không được mặc định suy ra OS ACL |
| `UnsupportedOperationException` | Provider/API không hỗ trợ thao tác/attribute view | Không |
| `IOException` | Nhóm lỗi I/O rộng hơn | Không |

Những phương thức `Files.*` thường nêu `SecurityException` trong tài liệu lịch sử khi có Security Manager đang bật. Ở JDK 24+ bạn không được dùng sự tồn tại của khai báo ấy để kết luận một Java policy đang bảo vệ file. Ngược lại, khi OS từ chối, mã thường nhận exception loại I/O; xử lý theo provider và message thực tế.

**Không viết logic kiểu: “Bắt SecurityException rồi cấp FilePermission là hết lỗi”.** Việc cấp quyền thực phải giải quyết qua OS/admin hoặc policy ứng dụng, không được thực hiện ngầm bởi mã không đủ đặc quyền.

### Logging an toàn

Log thông tin có ích: operation, mã lỗi, path đã redacted khi cần, principal của service theo quy trình quan sát phù hợp và correlation ID. Không log toàn bộ nội dung file bí mật, password hay access token để chẩn đoán permission failure.

## 16. Path traversal là lỗi ứng dụng, không phải lỗi OS permissions

Giả sử web endpoint nhận tên file từ người dùng:

```text
GET /download?file=invoice.pdf
```

Nếu dùng trực tiếp:

```java
Path target = root.resolve(userInput);
byte[] bytes = Files.readAllBytes(target);
```

attacker có thể thử `../secret.txt` hoặc dạng tương đương trên OS đích.

Nếu tiến trình **có quyền OS** đọc file secret đó, OS sẽ không từ chối chỉ vì người gọi HTTP không được phép xem nó. Kernel nhìn thấy **một request từ process account**, không biết user HTTP nào đang yêu cầu.

Ứng dụng cần kiểm soát:

1. Xác thực danh tính user/request.
2. Phân quyền theo tenant/document ID và trạng thái nghiệp vụ.
3. Không sử dụng path tùy ý như đối tượng authority; tốt hơn map ID đã được xác thực tới file do ứng dụng quản lý.
4. Giới hạn file root cố định, phân biệt file và thư mục, tránh symlink escape.
5. Xử lý race giữa check và open, đặc biệt ở thư mục attacker có thể ghi.
6. Vẫn chạy process dưới account ít quyền, để OS chặn phần lớn đường dẫn không thuộc phạm vi service.

### Kiểm tra lexical: cần nhưng chưa đủ

```java
Path base = root.toAbsolutePath().normalize();
Path candidate = base.resolve(userProvidedName).normalize();

if (!candidate.startsWith(base)) {
    throw new IllegalArgumentException("Path outside allowed root");
}
```

Đây là snippet minh họa. Nó chặn một số trường hợp `..` sau khi normalize nhưng **không chứng minh đường dẫn thực nằm trong root** nếu attacker có thể tạo/thay đổi symlink hoặc file trong thư mục. Ngoài ra, phải xử lý absolute input policy, case/volume semantics và encoding/canonicalization nhất quán.

Nếu provider hỗ trợ `SecureDirectoryStream`, có thể thực hiện một số thao tác tương đối so với directory handle để giảm race do thay tên/symlink. Không phải mọi provider hỗ trợ; thiết kế chặt hơn thường gồm quyền thư mục hạn chế, không để attacker sửa namespace, kiểm tra theo file descriptor/handle và isolation OS. Không dùng `toRealPath()` một lần rồi tin path bất biến cho mọi I/O về sau.

## 17. Thư mục tạm, file nhạy cảm và symlink

`Files.createTempFile` là API tốt hơn cách tự ghép tên như `secret-<timestamp>.tmp` vì API tạo một file mới với tên duy nhất theo semantics provider, giảm khả năng collision.

Nhưng thiết kế an toàn còn cần:

- Chọn **thư mục tin cậy**, có quyền phù hợp với tài khoản chạy service.
- Nếu tạo file secret, bảo đảm permission/ACL thích hợp **ngay khi tạo** nếu provider hỗ trợ.
- Không dùng tên cố định trong thư mục world-writable mà không có chiến lược chống race.
- Không lấy `/tmp` làm chỗ để lưu secret lâu dài mặc định; hiểu sticky bit, policy cleanup và quyền hệ điều hành.
- Không truyền path tạm cho tiến trình khác rồi giả định nó không thể thay nội dung trước khi file được đọc lại.
- Kiểm soát symlink/hardlink và file thay thế ở những đường dẫn attacker có thể tác động.
- Đóng file handle, bảo đảm dữ liệu không bị công bố trước khi validate.
- Nếu cần thay thế file quan trọng, cân nhắc write-temp-then-rename, atomic move khi hỗ trợ, và yêu cầu durability riêng.

Lưu ý: **atomic rename, file permission và quyền truy cập ứng dụng là ba vấn đề độc lập**. Một file được đổi tên nguyên tử vẫn có thể mang ACL sai; một file có ACL đúng vẫn có thể chứa dữ liệu nghiệp vụ sai; một app xác thực user đúng vẫn cần chống race trên filesystem.

## 18. Không dựa vào “sandbox Java” để chạy plugin không tin cậy

Một yêu cầu thường gặp là “chạy đoạn Java do người dùng gửi nhưng không cho đọc file”. Trong Java đời cũ từng có mô hình sandbox cùng JVM dựa trên Security Manager. Với Java hiện đại:

- Không dùng `SecurityManager` làm ranh giới bảo mật mới; từ JDK 24 không thể bật.
- Cùng một JVM thường không phải security boundary phù hợp để thực thi mã tùy ý có thể dùng các API mạnh.
- ClassLoader, module access, Java visibility, bytecode verification không cung cấp cách thay thế tương đương để ngăn code không tin cậy truy cập OS resources.
- Cần **cô lập ở mức tiến trình/OS** với account ít quyền, filesystem namespaces/mounts, sandbox/container/VM, network policy, CPU/memory/time quotas và giám sát.
- Với code thật sự không tin cậy, container bản thân nó không tự động tạo isolation mạnh nếu chạy privileged, mount socket host, cho quyền cao hoặc tắt security restrictions.
- Không để secret production nằm trong cùng filesystem namespace hoặc môi trường của tiến trình chạy code không tin cậy khi không có lý do bắt buộc.
- Quản lý cleanup của child process, timeout, stdout/stderr, quota và tránh cho phép child truy cập runtime/host control sockets.

Thành phần lập trình có thể hạn chế “API nào được phép gọi” vẫn hữu ích để thực thi **business rules**, nhưng không nên quảng cáo nó là sandbox vững chắc trước attacker có thể chạy bytecode tùy ý cùng quyền OS của tiến trình.

## 19. Xác thực/authorization của người dùng ứng dụng là lớp thứ ba

Một server chạy bằng user `app-service` có thể đọc toàn bộ thư mục `/var/lib/app/orders`. Nhưng khi Alice gọi `GET /orders/123`, việc Alice có quyền xem order 123 phải do ứng dụng xác định:

```text
HTTP request từ Alice
   |
   v
Authentication: Alice là ai?
   |
   v
Authorization: Alice có quyền xem order 123?
   |
   v
Lấy path từ ID đã được kiểm tra theo domain model
   |
   v
Filesystem open/read dưới quyền OS của app-service
   |
   v
Response chỉ chứa dữ liệu đã được phép tiết lộ
```

OS không tự biết “order 123 thuộc Alice”. Nếu ứng dụng bỏ qua bước authorization, lệnh đọc file vẫn có thể thành công vì process service được phép. Đây là lỗi **IDOR/broken object-level authorization**, không thể giải quyết chỉ bằng chmod cho một user service chung.

Với hệ thống multi-tenant:

- Map tenant + resource ID ở server side.
- Kiểm tra quyền trên từng thao tác read/write/delete.
- Tránh dùng raw filename hoặc đường dẫn làm object ID có thể chỉnh tùy ý.
- Giới hạn worker/service account tới thư mục chứa dữ liệu cần thiết, hoặc cô lập theo tenant khi yêu cầu cao.
- Audit truy cập dữ liệu với actor ứng dụng **và** process/service identity, không trộn hai danh tính.

## 20. ACL trong Java NIO: khác gì với POSIX mode?

`AclFileAttributeView` cung cấp cách làm việc với danh sách `AclEntry` khi filesystem hỗ trợ:

```java
AclFileAttributeView view = Files.getFileAttributeView(
        path,
        AclFileAttributeView.class);

if (view != null) {
    List<AclEntry> entries = view.getAcl();
    for (AclEntry entry : entries) {
        System.out.println(entry.principal() + ": " + entry.permissions());
    }
}
```

Đây là đoạn minh họa, cần import `AclFileAttributeView`, `AclEntry`, `List`, `Files`, `Path` và xử lý `IOException`; biến `path` giả định được khai báo.

Không kết luận:

- `getAcl()` trả một list nghĩa là Windows ACL được mô phỏng y hệt POSIX `rwx`.
- Thứ tự/loại ACE không ảnh hưởng việc đánh giá quyền; ACL có các quy tắc phức tạp.
- Mọi provider đều cho phép `setAcl`.
- Có thể sử dụng `AclEntryPermission.READ_DATA` để “trao quyền” bằng cách tự tạo một đối tượng enum mà không sửa metadata.
- Chuyển nguyên xi ACL từ hệ điều hành này sang hệ khác luôn giữ semantics.

Để sửa ACL, cần có hiểu biết về principals, ACE allow/deny, inheritance và quyền thay đổi security descriptor trên nền tảng thực. Không tự động thêm entry `ALLOW ALL` để giải quyết lỗi ghi file trong production.

## 21. Quyền thư mục và atomic file updates

Giả sử ứng dụng ghi file cấu hình một cách an toàn:

1. Tạo file tạm trong thư mục đích.
2. Ghi dữ liệu mới và validate.
3. Đồng bộ temp file nếu yêu cầu durability.
4. Di chuyển temp để thay tên đích theo atomic rename khi được hỗ trợ.
5. Kiểm tra/giữ quyền file mới phù hợp; dọn temp khi lỗi.

OS có thể kiểm tra nhiều khả năng khác nhau:

- Tạo temp yêu cầu quyền thích hợp trên **thư mục**.
- Ghi nội dung yêu cầu được phép mở/ghi **file**.
- Rename/replace yêu cầu quyền trên directory entries và có thể phụ thuộc ACL/handle.
- Đồng bộ dữ liệu có thể bị hạn chế bởi provider/filesystem.
- Đổi owner hoặc ACL của file mới không mặc định được phép cho process.

Một chi tiết đáng chú ý: khi tạo **file tạm mới rồi thay thế file đích**, metadata owner/ACL của temp có thể trở thành metadata của file đang ở tên đích. Không nên tưởng atomic replace tự giữ nguyên ACL cũ. Cần đặt metadata phù hợp **trước** khi công bố nếu bài toán yêu cầu.

**Không nên để Java tự xóa file đích rồi rename temp** để “vượt lỗi permissions”. Cách đó vừa có thể làm mất bản cũ vừa tạo khoảng trống reader nhìn thấy, và nếu OS không cho phép thì thao tác vẫn thất bại.

## 22. Sự khác nhau giữa Java module/security và OS access control

Java Platform Module System (`module-info.java`) cho phép khai báo `requires`, `exports`, `opens`... để kiểm soát khả năng truy cập code/package qua module boundaries. Đây **không phải** hệ thống cấp phép đọc file.

Ví dụ:

```java
module com.example.viewer {
    requires java.base;
}
```

Đây là ví dụ `module-info.java`, không phải chương trình runnable độc lập. Module `java.base` vốn được đọc mặc định; khai báo chỉ nhằm minh họa cú pháp.

Không suy ra rằng vì module không `requires java.io`, code không thể đọc filesystem: `java.io` là một **package** trong `java.base`, không phải một module riêng. Cũng không suy ra `exports` hay `opens` là quyền OS. Java module boundaries hướng tới encapsulation, readability và reflective access constraints; ranh giới quyền I/O cần OS/process/application policy.

Tương tự, `private`, `protected`, classpath isolation hay package visibility không tạo một filesystem sandbox trước code có khả năng chạy trong cùng JVM và cùng OS principal.

## 23. So sánh lỗi thực tế bằng bảng chẩn đoán

| Triệu chứng | Khả năng cần kiểm tra | Không nên làm |
|---|---|---|
| `AccessDeniedException` khi đọc tệp | Process user, ACL/owner, parent dir traverse, mount, sandbox, lock/provider | Tạo `new FilePermission` rồi tưởng OS cấp quyền |
| Ghi file bị từ chối trên Linux | Mode/ACL file, dir permissions, read-only mount, SELinux/AppArmor | Chạy toàn app bằng root ngay |
| File có `rw-------` nhưng process khác vẫn đọc được | Owner thực, elevated privileges, namespace, ACL, shared hardlinks, data đã bị sao chép | Xem mode bits là biện pháp mã hóa |
| `SecurityException` trong code Java 8/17 với manager | Java policy/permission check, cấu hình Security Manager, classpath | Nhầm ngay thành thiếu chmod |
| `System.setSecurityManager` không hoạt động JDK 24+ | JEP 486 đã vô hiệu hóa tính năng | Cố tìm flag “bật lại” |
| `Files.isReadable` true nhưng đọc vẫn lỗi | TOCTOU, mount/provider, race, share/lock, path đã đổi | Coi probe là authorization quyết định |
| Một user HTTP xem được file user khác | Application authorization/tenant isolation/path traversal | Chỉ đổi Java SecurityManager policy |
| Plugin tùy ý đọc được secrets | Cùng process account/namespace, thiếu OS isolation | Chỉ dùng ClassLoader để sandbox |
| POSIX permission API unsupported | Filesystem/provider không có view | Bỏ qua yêu cầu file private rồi vẫn công bố |
| Container vẫn thấy host secret | Volume mounts, root/capabilities, securityContext | Tin “đã dùng Docker” là đủ |

## 24. Thực hành: thiết kế các phép thử kiểm soát

Các bài kiểm tra nên tách riêng hành vi hệ điều hành và cơ chế Java:

**Bài 1 — Khác nhau giữa user process.** Tạo file dữ liệu trong môi trường thực hành, đặt mode/ACL chỉ cho service A đọc. Chạy **hai tiến trình thật sự** bằng hai tài khoản/nhóm phù hợp và thử `Files.readString`. Đừng thay đổi file hệ thống hoặc secrets thực.

**Bài 2 — Directory traverse.** Cấp quyền đọc cho file nhưng bỏ quyền traverse từ một thư mục cha trong môi trường test POSIX, quan sát khả năng mở file. Khôi phục permission sau test để không khóa đường truy cập của chính mình.

**Bài 3 — Probe vs operation.** Kiểm tra `Files.isReadable` và sau đó thử đọc; thảo luận vì sao hai thời điểm có thể khác nhau. Không tạo điều kiện race bằng cách thay symlink ngoài thư mục test.

**Bài 4 — Giới hạn Java policy lịch sử.** Đọc tài liệu JDK 17/JEP 411 và JDK 24/JEP 486; ghi rõ `FilePermission` từng có vai trò nào và vì sao không còn dùng nó làm sandbox trong Java mới. Không cài Security Manager vào hệ thống đang hoạt động chỉ để thử.

**Bài 5 — Path traversal.** Viết hàm resolve tên file trong thư mục staging do ứng dụng kiểm soát. Thử các input `file.txt`, `../file.txt`, absolute path và symlink. Nhận diện điểm lexical check giúp lọc nhưng không thay thế chống symlink race.

**Bài 6 — Container.** Chạy service ở môi trường test với root filesystem read-only và một writable volume được cấp đúng quyền. Liệt kê các đường dẫn cần ghi: temp, logs, cache, uploads. Xử lý lỗi bằng cách sửa mount/ACL có chủ đích, không bật privileged container.

**Bài 7 — Kiểm tra file secret mới.** Trên POSIX view phù hợp, tạo file ngay với attributes owner-only; trên Windows dùng ACL policy tương ứng. Xác nhận không có khoảng thời gian file nằm trên shared folder với quyền mặc định quá rộng.

## 25. Câu hỏi tự kiểm tra

**1.** Không có Security Manager, `Files.readString` có luôn đọc được bất kỳ file nào không?  
**Không.** OS/filesystem/mount tiếp tục thực thi quyền của process.

**2.** `new FilePermission(path,"read")` có tương đương `chmod u+r path` không?  
**Không.** Nó chỉ là Java Permission object trong mô hình cũ; không sửa POSIX mode.

**3.** Từ JDK nào Security Manager permanently disabled?  
**JDK 24**, theo JEP 486. JDK 17 đã deprecated for removal theo JEP 411.

**4.** `AccessController.doPrivileged` có giúp một process không đủ quyền OS đọc `/etc/shadow` không?  
**Không.** Nó không thay OS identity/ACL.

**5.** Trên POSIX, vì sao một file có bit read vẫn không mở được?  
**Có thể** thiếu quyền traverse trên thư mục cha, ACL/mount/OS policy khác, hoặc identity của process không tương ứng với quyền đó.

**6.** `Files.isReadable(path) == true` có bảo đảm lệnh mở file sau một giây thành công?  
**Không.** Có race/TOCTOU và điều kiện hệ thống có thể đổi.

**7.** Một process service được OS cho đọc mọi file tenant. Nếu API không kiểm tra tenant, OS có tự từ chối Alice đọc file của Bob không?  
**Không theo logic tenant ứng dụng.** OS thấy process service; ứng dụng phải tự enforce authorization.

**8.** Có thể dùng ClassLoader hoặc JPMS thay Security Manager để sandbox bytecode không tin cậy không?  
**Không như một ranh giới OS security đầy đủ.** Cần isolation ở mức process/OS/container/VM phù hợp.

**9.** File quyền `rw-------` có bảo đảm không ai có thể lấy dữ liệu nếu chạy app bằng root và log toàn bộ nội dung?  
**Không.** OS mode không bảo vệ khỏi ứng dụng/privileged process đã có authority và việc rò rỉ dữ liệu ở tầng ứng dụng.

**10.** Khi dùng temp file rồi atomic rename thay đích, file mới có chắc giữ ACL cũ không?  
**Không.** Đối tượng được công bố là file mới và có thể mang metadata của temp; cần policy bảo toàn quyền.

## 26. Checklist thiết kế Java I/O an toàn

Trước khi triển khai hoặc review hệ thống đọc/ghi:

- [ ] Xác định **process account** đang chạy JVM thực tế.
- [ ] Xác định tài nguyên nào cần đọc, ghi, tạo, xóa, rename; cấp quyền tối thiểu.
- [ ] Kiểm tra quyền **thư mục cha**, không chỉ file.
- [ ] Hiểu filesystem/provider và OS: POSIX mode/ACL, Windows DACL, mount và sandbox.
- [ ] Không dựa vào `FilePermission` hoặc `SecurityManager` lịch sử để cấp/quản lý OS access.
- [ ] Hiểu JDK 17 deprecated và JDK 24 permanently disabled đối với Security Manager.
- [ ] Xác thực và phân quyền **người dùng nghiệp vụ** trước khi map ID sang path.
- [ ] Hạn chế path traversal và symlink; không dựa riêng vào `normalize()+startsWith()` chống attacker.
- [ ] Không dùng `isReadable/isWritable` như bảo đảm thành công hay security check cuối cùng.
- [ ] Thực hiện I/O thật trong try/catch và xử lý `IOException` theo ngữ cảnh.
- [ ] Tạo file nhạy cảm với permission/ACL thích hợp từ đầu khi có hỗ trợ.
- [ ] Tách namespace/process nếu phải thực thi plugin hoặc code không tin cậy.
- [ ] Không chạy JVM với quyền root/Administrator chỉ để tránh kiểm soát ACL.
- [ ] Khi dùng container, kiểm tra mount, user, capabilities và secret exposure.
- [ ] Khi xuất bản file tạm, xét atomicity, metadata ACL và durability **độc lập**.
- [ ] Có test thật trên OS/filesystem triển khai, không suy ra từ máy developer.
- [ ] Không log secret trong lỗi quyền hoặc ngoại lệ I/O.
- [ ] Có security review khi thay đổi quyền file, token, sandbox hoặc service principal.

## 27. Tổng kết

- **Quyền hệ điều hành** do kernel/filesystem/access token/ACL/mount kiểm soát, quyết định tiến trình có thể sử dụng tài nguyên hệ thống hay không.
- **Java Security Manager lịch sử** là lớp kiểm tra permission bên trong JVM, **không bao giờ thay quyền OS**; `FilePermission` chỉ là biểu diễn policy Java chứ không phải thao tác chmod/ACL.
- **JDK 17**: Security Manager deprecated for removal (JEP 411). **JDK 24+**: Security Manager permanently disabled (JEP 486); đừng xây sandbox mới dựa vào nó.
- **Ứng dụng phải tự authorization theo user/tenant**; OS process account không tự biết quyền nghiệp vụ của từng request.
- **`Files.isReadable/isWritable` là probe, không phải authority**; filesystem race, symlink và path traversal cần thiết kế xử lý riêng.
- **Least privilege + OS/process isolation + kiểm tra dữ liệu/đường dẫn + quản lý lifecycle I/O** là nền tảng thực tế cho Java I/O an toàn.

### Tài liệu tham khảo chính thức

- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411)
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486)
- [Oracle: The Security Manager Is Permanently Disabled, JDK 25](https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html)
- [Oracle: SecurityManager, Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SecurityManager.html)
- [Java FilePermission (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FilePermission.html)
- [Java Files API (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [PosixFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html)
- [AclFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html)
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html)
