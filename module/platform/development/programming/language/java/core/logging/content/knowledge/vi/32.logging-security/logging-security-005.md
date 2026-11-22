# Giới hạn quyền file log trong Java: bảo vệ nội dung, đường dẫn và vòng đời log

## 1. Mục tiêu

File log có thể chứa thông tin về luồng xử lý, địa chỉ IP, mã request, tên tài khoản, lỗi hệ thống, stack trace hoặc dữ liệu nghiệp vụ. Nếu file được tạo với quyền quá rộng, người không cần truy cập vẫn có thể đọc, sửa, xóa hoặc thay thế log. **Giới hạn quyền file log** là áp dụng nguyên tắc *least privilege*: chỉ cho phép các danh tính và dịch vụ thật sự cần thiết đọc/ghi/quản lý log, với quyền thấp nhất phục vụ công việc của họ.

Đây là bài thuộc **Bảo mật logging**. Trọng tâm không chỉ là `chmod` một file hiện tại mà còn là **quyền tại thời điểm tạo**, thư mục chứa, process chạy Java, file sau rotation, bản sao lưu và hệ thống thu thập log.

Sau bài học, bạn có thể:
- Hiểu quyền `owner/group/others` trên POSIX và ACL trên Windows, phân biệt quyền file với quyền thư mục.
- Chọn mức quyền phù hợp cho file riêng tư (`0600`), file cần nhóm đọc (`0640`), thư mục riêng (`0700`) và thư mục có nhóm đọc (`0750`).
- Cấu hình user/umask ở hệ điều hành, systemd hoặc container; xác minh quyền sau khi logger tạo file và xoay vòng.
- Tạo file bằng Java NIO với thuộc tính POSIX ngay lúc tạo; xử lý đúng khi filesystem không hỗ trợ POSIX.
- Phát hiện các lỗ hổng thường gặp: `0777`, `0666`, thư mục writable công khai, symlink, ACL thừa, file archive/backup bị mở rộng quyền.

## 2. Mô hình mối đe dọa: ai có thể làm gì với log?

Giả sử dịch vụ Java ghi `/var/log/example-app/application.log`:

| Tác nhân | Nhu cầu hợp lệ | Rủi ro nếu cấp thừa quyền |
| --- | --- | --- |
| Tài khoản chạy ứng dụng (`exampleapp`) | Tạo và ghi log của ứng dụng | Nếu được ghi cả thư mục dùng chung không kiểm soát, có thể thao tác file khác |
| Agent/shipper thu thập log | Đọc những file được chỉ định | Nếu được quyền ghi, có thể sửa/xóa chứng cứ |
| Nhân viên trực vận hành | Đọc theo quy trình, tra cứu khi sự cố | Nếu mọi tài khoản đều có quyền đọc, dữ liệu nhạy cảm bị lan rộng |
| Backup/rotation service | Đọc, di chuyển, nén, lưu trữ hoặc tạo file mới | File mới/backup có thể được tạo với quyền rộng hơn file gốc |
| Tài khoản không liên quan | Không cần truy cập | Có thể đọc, sửa, thay thế hoặc xóa log nếu ACL/mode bị sai |

**Bảo mật log** bao gồm cả tính bí mật (confidentiality), toàn vẹn (integrity) và khả dụng (availability). Chỉ dùng mode bits chưa bảo đảm log chống sửa hoàn toàn: chủ file thường có thể thay đổi quyền; administrator/root hoặc tài khoản đặc quyền có thể truy cập; file bị xóa, ổ đầy hoặc pipeline hỏng vẫn ảnh hưởng dữ liệu. Với audit nghiêm ngặt phải bổ sung lưu trữ ngoài tiến trình, cơ chế chống giả mạo và retention.

Nguyên tắc trước khi cấu hình:
1. Tách tài khoản service khỏi tài khoản phát triển/đăng nhập thường ngày.
2. Chỉ cấp **ghi** cho service hoặc bộ phận thực sự quản lý file.
3. Chỉ cấp **đọc** cho shipper/người vận hành cần thiết.
4. Hạn chế khả năng liệt kê, tạo, xóa và thay thế file trong thư mục log.
5. Đánh giá quyền trên **mọi bản sao** của log, không chỉ `application.log` hiện tại.

## 3. Quyền POSIX: file và thư mục khác nhau

Trên Linux và nhiều filesystem POSIX, quyền là ba nhóm: **owner**, **group**, **others**. `r` = read, `w` = write, `x` = execute/search. Mỗi nhóm có ba bit; dạng số bát phân và dạng ký hiệu là hai cách biểu diễn cùng quyền.

| Mode | Biểu diễn | Ý nghĩa phổ biến |
| --- | --- | --- |
| File `0600` | `rw-------` | Chỉ owner đọc/ghi; group và others không có quyền |
| File `0640` | `rw-r-----` | Owner đọc/ghi; group chỉ đọc; others không có quyền |
| File `0644` | `rw-r--r--` | Người dùng khác có thể đọc; thường **quá rộng** nếu log có dữ liệu nhạy cảm |
| File `0666` | `rw-rw-rw-` | Mọi người có thể đọc/ghi; không phù hợp với log cần bảo vệ |
| Thư mục `0700` | `rwx------` | Chỉ owner được truy cập/liệt kê/tạo theo quyền của owner |
| Thư mục `0750` | `rwxr-x---` | Owner quản lý; group có thể liệt kê và đi qua thư mục; others không có quyền |
| Thư mục `0777` | `rwxrwxrwx` | Nhiều tài khoản có thể tạo/xóa/đổi tên entry; không nên dùng cho thư mục log |

Quyền `x` trên **file** là quyền thực thi, thường không cần cho `.log`. Nhưng `x` trên **thư mục** cho phép đi qua đường dẫn đến file (search/traverse). Để đọc `/var/log/example-app/application.log`, người dùng cần quyền đọc file **và** quyền đi qua tất cả thư mục cha liên quan. Quyền `r` trên thư mục cho phép đọc danh sách tên, không tự động cấp quyền đọc nội dung từng file.

Đặc biệt, quyền **xóa/đổi tên file** thường được quyết định bởi quyền ghi + đi qua **thư mục cha**, không chỉ bởi bit `w` trên file. Bởi vậy file `0600` đặt trong thư mục `0777` vẫn có nguy cơ bị thay thế/xóa bởi người có quyền trên thư mục (tùy sticky bit và ACL). Đừng chỉ kiểm tra một file rồi kết luận toàn bộ đường dẫn đã an toàn.

`0600` và `0640` chỉ là ví dụ chính sách. Khi cần một shipper đọc log, `0640` với group/ACL giới hạn có thể đúng hơn `0600`. **Không cấp quyền `others` chỉ để làm cho shipper hoạt động**.

## 4. Quyền được quyết định vào lúc tạo file

Một file log mới có thể được tạo khi service khởi động, khi Logback/Log4j/JUL mở đích file, hoặc sau khi rollover. Phải phân biệt:
- **Danh tính tiến trình:** UID/GID hoặc Windows service identity của process Java.
- **Quyền tạo mặc định:** do ứng dụng, thư viện, filesystem và chính sách hệ điều hành quyết định.
- **Umask trên POSIX:** mặt nạ loại bỏ các bit quyền khi tạo file/thư mục theo các cơ chế thông thường.
- **Default ACL, group kế thừa, mount/volume:** có thể ảnh hưởng owner/group, quyền thực tế hoặc hành vi truy cập.

Ví dụ điển hình trên POSIX, nếu ứng dụng xin mode tạo file `0666`:
- `umask 0077` loại quyền group/others, thường cho file mới `0600`.
- `umask 0027` thường cho file mới `0640`.
- Với thư mục xin `0777`, hai umask trên thường tạo `0700` và `0750` tương ứng.

Đây là **cách tính phổ biến**, không phải cam kết rằng mọi logging backend đều yêu cầu đúng `0666` hoặc filesystem không có ACL. Chỉ số `umask` không sửa quyền file đã tồn tại, không bảo đảm backup/rotation luôn dùng mode giống file gốc và không thay thế kiểm tra sau khi tạo.

**Tránh quy trình “tạo file công khai rồi chmod thành riêng tư”**: nếu lúc tạo file đã đọc được bởi người khác, có thể xuất hiện khoảng thời gian lộ dữ liệu trước khi `chmod` chạy. Tốt hơn là cấp đúng mode ngay khi tạo hoặc tạo trong thư mục chỉ service truy cập, sau đó xác nhận.

## 5. Thiết lập thư mục và user trên Linux

Giả sử service tên `exampleapp`, có tài khoản hệ điều hành riêng cùng tên, và chỉ service được đọc/ghi log.

Một ví dụ chuẩn bị thư mục có kiểm soát (do người quản trị thực hiện, **không phải lệnh mà ứng dụng tự chạy**):

```bash
sudo install -d -o exampleapp -g exampleapp -m 0700 /var/log/example-app
sudo ls -ld /var/log/example-app
```

Mục đích:
- `install -d` tạo/cấu hình thư mục log do tài khoản service sở hữu.
- `0700` ngăn các tài khoản khác liệt kê hoặc đi qua thư mục theo mode bits.
- Không cho ứng dụng chạy `root` chỉ vì thiếu quyền ghi log; sửa owner/permission của đúng thư mục hoặc dùng thư mục riêng do service manager cấp.

Ví dụ hiển thị kiểu POSIX khi thiết lập thành công (owner/group là tên phụ thuộc máy):

```text
drwx------ ... exampleapp exampleapp ... /var/log/example-app
```

Các dấu `...` biểu thị trường của `ls` phụ thuộc thời điểm/hệ thống, **không phải stdout cố định**.

Nếu cần **agent thu thập log** đọc:
- Đưa agent vào group được phép đọc hoặc cấp ACL chỉ đọc cho đúng service principal.
- File cần quyền nhóm đọc (thường `0640`) và thư mục cần traverse cho nhóm (thường `0750`).
- Cấu hình group sở hữu file mới cho đúng; trên POSIX có thể dùng group của process, setgid trên thư mục hoặc default ACL tùy chính sách.
- Agent không cần quyền ghi lên file hoặc thư mục, trừ khi có nhiệm vụ thật sự đòi hỏi.

Tránh `chmod -R 777 /var/log/example-app` hoặc `chmod -R 666` để “sửa nhanh lỗi permission”: nó mở rộng quyền quá mức, có thể tạo lỗ hổng đọc/xóa log và không giải quyết đúng nguyên nhân owner/group.

### 5.1. systemd: cấp quyền khi tạo log

Với ứng dụng chạy bằng **systemd system service**, có thể dùng cấu hình unit:

```ini
[Service]
User=exampleapp
Group=exampleapp
UMask=0077
LogsDirectory=example-app
LogsDirectoryMode=0700
ExecStart=/usr/bin/java -jar /opt/example-app/app.jar
```

Đây là **đoạn cấu hình minh họa**, yêu cầu tài khoản, JAR và đường dẫn thực tế có tồn tại. Theo cơ chế `LogsDirectory` của systemd, system service tạo thư mục thích hợp dưới `/var/log/` với owner/group của service; `LogsDirectoryMode` quản lý mode của thư mục. `UMask=0077` giới hạn quyền tạo file mới của process và các tiến trình con theo quy tắc umask.

Hai điểm quan trọng:
1. `UMask` **không hồi tố** chmod file đã tồn tại hoặc file được tạo bằng một tiến trình độc lập không kế thừa umask đó.
2. Rotation do `logrotate`, backend hoặc agent khác thực hiện có thể có cấu hình owner/group/mode riêng; phải kiểm tra file sau rollover.

Không chỉnh trực tiếp unit của dịch vụ đang chạy mà không có quy trình thay đổi/khởi động lại phù hợp. Với container/Kubernetes hoặc service manager khác, áp dụng chính sách tương đương tại đúng tầng.

## 6. Java NIO: tạo file với quyền POSIX ngay khi tạo

Java NIO có `Files.createFile(Path, FileAttribute<?>...)`, `Files.createTempDirectory(...)`, `PosixFilePermissions` và `Files.getPosixFilePermissions`. Khi filesystem hỗ trợ POSIX attribute view, có thể yêu cầu quyền ngay trong thao tác tạo file/thư mục:

```java
Set<PosixFilePermission> perms =
        PosixFilePermissions.fromString("rw-------");
Files.createFile(path,
        PosixFilePermissions.asFileAttribute(perms));
```

Thuộc tính được truyền **cùng thao tác tạo**, giảm cửa sổ file mới bị tạo với quyền mặc định rộng rồi mới được sửa. Theo Java API, quyền thực tế có thể **bằng hoặc chặt hơn** quyền yêu cầu do umask/chính sách filesystem. Kiểm tra lại sau tạo, không mặc định phương thức đã cho ra đúng từng bit.

### 6.1. Ví dụ Java 17+ độc lập: kiểm tra khả năng POSIX và tạo file riêng tư

Chương trình dưới đây dùng thư mục tạm của hệ thống để minh họa, không ghi vào đường dẫn production. Trên hệ thống không hỗ trợ POSIX attribute view (thường là NTFS/Windows), nó **không giả lập Unix chmod** mà báo rằng cần cấu hình ACL theo hệ điều hành.

Tạo **`SecureLogPermissionsDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public final class SecureLogPermissionsDemo {
    public static void main(String[] args) throws Exception {
        Path base = Path.of(System.getProperty("java.io.tmpdir"));

        Set<PosixFilePermission> privateDir =
                PosixFilePermissions.fromString("rwx------");
        Set<PosixFilePermission> privateLog =
                PosixFilePermissions.fromString("rw-------");

        System.out.println("requested-file-mode="
                + PosixFilePermissions.toString(privateLog));

        if (!Files.getFileStore(base)
                .supportsFileAttributeView("posix")) {
            System.out.println("POSIX_NOT_SUPPORTED");
            return;
        }

        Path dir = Files.createTempDirectory(
                base, "safe-logs-",
                PosixFilePermissions.asFileAttribute(privateDir));
        Path log = dir.resolve("application.log");

        try {
            // CREATE_NEW: từ chối nếu đã tồn tại, kể cả symbolic link.
            Files.createFile(log,
                    PosixFilePermissions.asFileAttribute(privateLog));
            Files.writeString(log, "event=demo\n",
                    StandardCharsets.UTF_8, StandardOpenOption.APPEND);

            System.out.println("directory-mode="
                    + PosixFilePermissions.toString(
                            Files.getPosixFilePermissions(dir)));
            System.out.println("file-mode="
                    + PosixFilePermissions.toString(
                            Files.getPosixFilePermissions(log)));
        } finally {
            Files.deleteIfExists(log);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac SecureLogPermissionsDemo.java
java SecureLogPermissionsDemo
```

**Trường hợp filesystem không hỗ trợ POSIX**, kết quả xác định:

```text
requested-file-mode=rw-------
POSIX_NOT_SUPPORTED
```

**Trường hợp filesystem POSIX** với mode được áp dụng đầy đủ, một kết quả thường gặp:

```text
requested-file-mode=rw-------
directory-mode=rwx------
file-mode=rw-------
```

Kết quả POSIX thực tế có thể **chặt hơn** do umask hoặc quy tắc filesystem. Nếu không có quyền tạo/ghi ở thư mục tạm, chương trình có thể phát sinh exception — đó là lỗi quyền môi trường, không phải lý do nới quyền mọi người. Ví dụ sẽ xóa các file nó tạo sau khi chạy thành công.

Cơ chế hoạt động:
1. `PosixFilePermissions.fromString(...)` biểu diễn quyền với `Set<PosixFilePermission>`.
2. `Files.getFileStore(base).supportsFileAttributeView("posix")` kiểm tra hỗ trợ trước khi dùng các thuộc tính POSIX. Không suy đoán hỗ trợ chỉ từ tên OS.
3. `Files.createTempDirectory(..., attrs)` và `Files.createFile(..., attrs)` yêu cầu quyền ngay lúc tạo.
4. `Files.writeString(..., APPEND)` ghi một dòng vào file chỉ service sở hữu; đây là thao tác minh họa, không phải Logback appender.
5. `Files.getPosixFilePermissions` đọc lại mode, `finally` dọn file và thư mục do ví dụ tạo.

**Giới hạn ví dụ:** đây là cơ chế tạo file bảo mật, không phải quy trình cấu hình file appender tự động. Một logger thật có thể **tự tạo hoặc tạo lại** file bằng API riêng. Nếu pre-create file thì cần xác nhận appender có mở đúng file đó và đường dẫn sau rotation còn được bảo vệ.

### 6.2. Vì sao không dùng `setPosixFilePermissions` sau khi tạo là đủ?

`Files.setPosixFilePermissions(path, perms)` sửa mode của một file **đang tồn tại** và hữu ích khi sửa cấu hình. Nhưng khi dùng:

```java
Files.createFile(path);
Files.setPosixFilePermissions(path,
        PosixFilePermissions.fromString("rw-------"));
```

có hai thao tác riêng. Trong khoảng giữa, file có thể mang quyền mặc định rộng hơn yêu cầu (tùy umask/ACL). Đối với file nhạy cảm nên dùng `FileAttribute` tại lúc tạo hoặc tạo trong thư mục bảo mật đã được chuẩn bị trước.

Cũng không dùng `java.io.File#setReadable(...)`/`setWritable(...)` để giả định có cùng một kết quả ACL chuẩn trên mọi OS. Những API thuận tiện có thể không diễn tả đầy đủ Windows ACL, default ACL, owner/group và security policy của volume.

## 7. Java NIO trên Windows: ACL thay cho Unix chmod

Windows với NTFS thường dùng **Discretionary Access Control List (DACL)**. Quyền được gán cho các *security principals* như:
- Tài khoản Windows service chuyên biệt hoặc service SID.
- `SYSTEM`, `Administrators`.
- Nhóm/agent thu thập log được chỉ định rõ.
- Các nhóm mặc định có quyền kế thừa từ thư mục cha (cần kiểm tra).

Không thể lấy `chmod 600` áp vào NTFS rồi xem như đã bảo mật đầy đủ. Trong Java NIO có `AclFileAttributeView`, `AclEntry` và `UserPrincipal` để đọc/thiết lập ACL ở provider hỗ trợ; cách triển khai đúng phụ thuộc service identity, các mục kế thừa và quyền được yêu cầu. Trên Windows, ưu tiên **cấp quyền thư mục log lúc provision/deploy** bằng công cụ hệ điều hành/quy trình IT thay vì ứng dụng cố tự viết lại toàn bộ ACL khi khởi động.

Lệnh **chỉ đọc** để kiểm tra:

```powershell
icacls "C:\ProgramData\ExampleApp\logs"
Get-Acl -Path "C:\ProgramData\ExampleApp\logs" |
    Format-List Owner,AccessToString
```

Phải thay đường dẫn bằng thư mục log thực tế. Các lệnh này không tự thay đổi ACL.

Khi thiết kế DACL, một mô hình là:
- Service: quyền tạo/ghi/đọc phù hợp với việc chạy appender và rotation, chỉ tại thư mục log của nó.
- Shipper: **read/traverse** nếu chỉ cần thu thập.
- Quản trị hệ thống: quyền quản lý theo policy.
- Users/Everyone/Authenticated Users không liên quan: không cấp quyền đọc/ghi vào log chứa dữ liệu nhạy cảm.
- Xác minh **ACE inherited** từ thư mục cha và **effective access**; chỉ thêm một entry Deny/Allow mà không xem toàn DACL có thể dẫn đến mở rộng quyền hoặc khóa dịch vụ.

Không sao chép một lệnh `icacls /inheritance:r` mù quáng vào mọi máy: thay đổi inheritance có thể làm mất quyền quản trị/SYSTEM cần thiết. Hãy thử trên thư mục được provision trong môi trường kiểm thử và đối chiếu tài khoản service thật.

## 8. Logging framework: ai tạo file và ai kiểm soát mode?

Điều kiện quan trọng: **file được tạo bởi thành phần nào** thì thành phần đó và môi trường vận hành phải chịu trách nhiệm về quyền ban đầu.

### 8.1. Log4j 2 Core

Theo tài liệu Log4j 2, `File` và `RollingFile` appender có thuộc tính `filePermissions` (POSIX), cùng `fileOwner`/`fileGroup` khi filesystem và quyền OS hỗ trợ. Ví dụ **đoạn XML cấu hình**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="PRIVATE_FILE"
                     fileName="/var/log/example-app/application.log"
                     filePattern="/var/log/example-app/archive-%d{yyyy-MM-dd}-%i.log.gz"
                     filePermissions="rw-------">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
            <Policies>
                <SizeBasedTriggeringPolicy size="10 MB"/>
            </Policies>
        </RollingFile>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="PRIVATE_FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

Đoạn này cần ứng dụng chạy Log4j 2 Core phiên bản có hỗ trợ các thuộc tính trên, với thư mục đã được provision và service có quyền ghi. `filePermissions="rw-------"` mô tả quyền mong muốn cho file được appender tạo trên POSIX; không làm cho NTFS hỗ trợ POSIX, và không thay thế cấu hình owner, umask hay bảo mật thư mục.

**Kiểm tra các file sau rollover**: tên archive có thể khác và quá trình nén/di chuyển có quyền riêng. Log4j 2 còn có hành động rollover `PosixViewAttribute` để thay đổi quyền của file archive theo điều kiện; chỉ cấu hình khi thực sự cần và kiểm tra phiên bản, phạm vi đường dẫn và `followLinks`. Không mặc định file archive/compressed copy giữ nguyên mọi metadata như file hiện tại.

### 8.2. Logback và JUL

Với **Logback** (`FileAppender`/`RollingFileAppender`) hoặc JUL `FileHandler`, quyền thực tế phụ thuộc cơ chế tạo file, user/group của process, umask và quyền thư mục/volume. Đừng giả định XML của Logback hiểu `filePermissions` chỉ vì Log4j 2 có thuộc tính cùng tên.

Khi dùng Logback/JUL:
1. Provision thư mục log riêng và hạn chế quyền trước khi appender chạy.
2. Chạy JVM dưới tài khoản service ít quyền; thiết lập umask/ACL phù hợp từ service manager.
3. Kiểm tra **file mới** được tạo thực tế, không chỉ xem một file cũ đã `chmod`.
4. Thử rollover, restart, compress và backup; kiểm tra owner/group/mode/ACL ở từng loại file.
5. Nếu có collector đọc file, cấp quyền riêng cho collector, tránh chuyển appender sang chạy root.

Trong ứng dụng dùng SLF4J, hãy nhớ SLF4J là API; chính provider (Logback, Log4j, JUL bridge…) mới quyết định nơi tạo file. Đọc đúng tài liệu backend và phiên bản đang triển khai.

## 9. Rotation và lưu trữ là một phần của quyền file log

File log hiếm khi tồn tại một mình: có file hiện tại, file cũ, file nén, bản sao backup, file được shipper đọc và đối tượng ở collector. Mỗi bước có thể **tạo inode/file mới** với mode/ACL khác nhau.

Các trường hợp cần kiểm tra:
- **Restart:** appender mở lại file hiện có hay tạo file mới? Owner và mode thay đổi thế nào?
- **RollingFile/rolling policy:** file archive được move hay copy/nén, có tạo file mới công khai không?
- **logrotate trên Linux:** nếu dùng `create`, owner/group/mode của file mới theo cấu hình logrotate. Service có thực sự reopen file mới không?
- **Compression:** file `.gz` có được cấp quyền hạn chế và nằm trong thư mục bảo mật không?
- **Backup/restore:** ACL/mode có được giữ hoặc áp dụng lại ở nơi lưu trữ khôi phục không?
- **Retention:** xóa đúng hạn, không làm bản sao cũ sống vô thời hạn trong bucket, thư mục tạm hoặc CI artifacts.

Một đoạn cấu hình **logrotate** minh họa khi có logrotate độc lập:

```text
/var/log/example-app/application.log {
    daily
    rotate 7
    missingok
    notifempty
    create 0600 exampleapp exampleapp
}
```

Mục `create 0600 exampleapp exampleapp` yêu cầu logrotate tạo file mới với mode/owner/group chỉ định. **Không tự áp dụng cấu hình này** nếu logging backend cũng tự rolling: hai cơ chế có thể tranh chấp đường dẫn. Sau khi logrotate di chuyển file hiện tại, JVM có thể vẫn ghi vào file descriptor cũ cho tới khi appender được reopen; phải có quy trình reopen/restart phù hợp. Quyền archive/backup cũng phải được xác minh riêng.

Tránh coi `copytruncate` là giải pháp không có rủi ro: khi vừa copy vừa truncate, bản ghi xuất hiện trong khoảng đua có thể bị mất. Việc chọn rotate strategy liên quan cả tính toàn vẹn dữ liệu, không chỉ permission.

## 10. Thư mục không tin cậy, symlink và path traversal

Giả sử log file có mode `0600` nhưng đường dẫn cha lại cho tài khoản lạ quyền ghi. Kẻ khác có thể cố:
- Tạo symlink ở tên file dự kiến để khiến logger mở nhầm một đích khác.
- Xóa/đổi tên entry rồi thay thế file, làm lệch nguồn dữ liệu.
- Điều khiển tên file hoặc phân đoạn path từ input, đưa log sang vị trí ngoài thư mục dự kiến.

**Đường dẫn log nên cố định và nằm dưới thư mục do service/admin kiểm soát**, không ghép tên tệp từ dữ liệu HTTP/request do người ngoài cung cấp. Không cho user không liên quan quyền ghi vào thư mục log.

Một số lưu ý kỹ thuật:
- `Files.createFile(path, attrs)` dùng thao tác tạo file mới; nếu path cuối đã tồn tại, kể cả symlink, nó không đơn giản ghi đè nội dung đó.
- Kiểm tra `Files.isSymbolicLink(path)` rồi mở file bằng thao tác khác **không phải bảo vệ tuyệt đối** vì có thể có race giữa check và open.
- `LinkOption.NOFOLLOW_LINKS` và `StandardOpenOption.CREATE_NEW` có vai trò ở API hỗ trợ, nhưng không thay thế bảo vệ các thư mục cha, mount và danh tính người mở file.
- Đừng tự động `chmod`/`chown` một path lấy từ đầu vào không tin cậy; thay đổi permission nhầm vị trí có thể là lỗ hổng nghiêm trọng.

Nếu nhiều ứng dụng chia sẻ một thư mục, chia thư mục con theo service và cấp quyền độc lập. Một log file world-readable trong thư mục có thể truy cập rộng làm giảm hiệu quả mọi cố gắng redaction.

## 11. Container, Kubernetes, stdout và collector

Nhiều ứng dụng Java trong container ghi log lên **stdout/stderr** thay vì tự mở `/var/log/...`. Khi đó:
- File trên host do container runtime, log driver, kubelet hoặc collector tạo/quản lý.
- `chmod` hoặc `Files.setPosixFilePermissions` trong JVM **không** tự đổi quyền file log do runtime tạo trên host.
- Phải kiểm tra user/container security context, volume mount, host paths, log driver, runtime và quyền truy cập trong hệ thống tập trung.

Nếu appender viết thẳng lên một mounted volume:
- Xác định UID/GID hữu hiệu trong container và owner/group thực tế của volume.
- Kiểm tra thư mục volume có cho service ghi và hạn chế người khác.
- Không mặc định `runAsUser` hoặc `fsGroup` luôn biến mọi storage provider thành cùng một mô hình permission; kiểm tra hành vi triển khai.
- Đảm bảo init job/sidecar/backup không tạo lại file với mode/ACL rộng.

Nếu sử dụng **journald**, hệ thống thu thập hoặc cloud logging, cần áp dụng quyền người đọc ở **journal/collector** và chính sách IAM/retention, không chỉ mode của một file cục bộ. Cùng một event có thể tồn tại ở nhiều nơi: file ứng dụng, stdout, journal, agent buffer, collector, object storage và bản xuất báo cáo.

## 12. Kiểm tra quyền thực tế: đừng chỉ xem cấu hình

Trên Linux, các lệnh chỉ đọc thường dùng:

```bash
ls -ld /var/log/example-app
ls -l /var/log/example-app/application.log
stat -c '%a %U:%G %n' /var/log/example-app/application.log
namei -l /var/log/example-app/application.log
getfacl -p /var/log/example-app/application.log
```

`stat -c` và `namei` là cú pháp thường có trên hệ thống GNU/Linux; `getfacl` có thể cần package ACL. Kết quả khác nhau theo hệ thống; không đưa ra output cố định. `namei -l` giúp thấy quyền của từng thư mục trong đường dẫn, còn `getfacl` kiểm tra các entry ACL ngoài mode bits đơn giản.

Kiểm tra **trên file mới**:
1. Khởi động appender bằng danh tính service đúng.
2. Gửi một event test không chứa dữ liệu nhạy cảm để chắc chắn file được tạo.
3. Đọc owner/group/mode/ACL và xác định một tài khoản ngoài phạm vi thực sự **không đọc được**.
4. Tạo rollover trong môi trường test, kiểm tra file hiện tại, archive và file nén.
5. Đăng xuất/restart, kiểm tra lại để bắt trường hợp cấu hình chỉ đúng trên file cũ.

Trên Windows, dùng `icacls` và `Get-Acl` ở mục 7 rồi kiểm tra quyền thực của service SID/agent. Có thể cần công cụ quản trị để mô phỏng tài khoản khác; không kết luận DACL an toàn chỉ vì tài khoản admin đọc được (admin vốn có đặc quyền).

### Ma trận kiểm tra tối thiểu

| Tình huống | Kỳ vọng đối với file log riêng tư |
| --- | --- |
| Service ghi log | Có thể mở/append và rollover đúng cách |
| User không liên quan đọc file | Bị từ chối theo policy |
| User không liên quan sửa/xóa file | Bị từ chối qua file và thư mục cha |
| Shipper được chỉ định | Có thể đọc, thường không cần sửa/xóa |
| File mới sau restart | Quyền không rộng hơn policy |
| File archive sau rotation | Được bảo vệ tương đương |
| File nén/backup/restore | Không rơi vào bucket/thư mục công khai |
| Windows/volume không hỗ trợ POSIX | Dùng ACL/provider phù hợp, không giả vờ chmod đã thành công |

## 13. Tách bảo mật quyền file khỏi nội dung log

**Giới hạn quyền file log là lớp bảo vệ cần thiết nhưng chưa đủ.** Ngay cả file `0600` vẫn có thể chứa token hoặc dữ liệu cá nhân mà service, admin hoặc backup có quyền đọc. Quy tắc logging an toàn:
- Không ghi password, API key, bearer token, session cookie, số thẻ hoặc dữ liệu nhạy cảm không cần thiết.
- Giới hạn stack trace/payload khi có khả năng lộ bí mật; ưu tiên ID nghiệp vụ và thông tin lỗi đã kiểm soát.
- Redact/mask ngay tại nguồn khi có thể, đồng thời áp dụng retention.
- Tách audit bắt buộc khỏi debug log nếu cần đảm bảo tính toàn vẹn hoặc điều tra pháp lý.
- Mã hóa tại rest/transit khi yêu cầu, bảo vệ khóa mã hóa ở nơi riêng, kiểm soát IAM của collector và backup.
- Theo dõi các thao tác thay đổi permission/ACL và đọc log nhạy cảm khi có yêu cầu bảo mật.

Một tài khoản có quyền ghi file log có thể sửa nội dung; `chmod 600` **không** bảo đảm log chống sửa bởi chính owner hoặc administrator. Với dấu vết audit quan trọng, cân nhắc append-only/tamper-evident pipeline, lưu ngoài máy ứng dụng và kiểm chứng bản ghi.

## 14. Lỗi phổ biến

| Lỗi | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| `chmod 777` thư mục log cho “dễ ghi” | Mọi người có thể tạo/xóa/đổi tên entry | Tài khoản service riêng, thư mục `0700`/`0750` |
| File `0600` nằm trong thư mục người ngoài được ghi | Có thể thay thế/xóa entry qua thư mục | Khóa quyền thư mục và đường dẫn cha |
| `chmod` sau khi file đã chứa log | Có cửa sổ quyền mặc định quá rộng | Thiết lập khi tạo, umask/ACL từ trước |
| Chỉ sửa permission file hiện tại | Restart/rotation tạo file khác mode | Test file mới và archive sau rollover |
| Chạy Java bằng root để sửa `Permission denied` | Mở rộng đặc quyền toàn bộ ứng dụng | Sửa owner/group/ACL đúng nơi |
| Chỉ xem `ls -l`, bỏ qua ACL và đường dẫn cha | ACL/dir traversal có thể khác | `namei`, `getfacl`, kiểm tra effective access |
| Dùng `setPosixFilePermissions` trên Windows | Provider không hỗ trợ POSIX | Dùng Windows ACL/`AclFileAttributeView` |
| Cho shipper quyền ghi/xóa | Có thể làm hỏng bằng chứng | Chỉ cấp read/traverse khi đủ |
| Dùng cả logrotate và RollingFile không phối hợp | File descriptor, quyền/rotation bất ngờ | Chọn chiến lược rõ ràng và test reopen |
| Ghi stdout rồi `chmod` file trong container | File do runtime quản lý trên host | Kiểm tra runtime/host log policy |
| Log nhạy cảm vì “đã chmod 600” | Owner/admin/backup vẫn đọc được | Minimize, redact, encrypt, retention |
| Dùng tên file từ request | Có thể path traversal hoặc tạo file lạ | Đường dẫn định sẵn, không nhận path không tin cậy |

## 15. Bài tập thực hành

1. Trên Linux test, tạo thư mục riêng với `0700` và file `0600`. Dùng `ls -l`/`stat` xác nhận; thử tài khoản khác để hiểu quyền file và đường dẫn cha.
2. Tạo thư mục `0750` với group shipper và file `0640`. Xác minh shipper chỉ đọc, không thể sửa hoặc xóa file.
3. Chạy `SecureLogPermissionsDemo` trên filesystem POSIX. Giải thích `requested-file-mode`, `directory-mode` và `file-mode`; nếu kết quả chặt hơn, liên hệ umask và chính sách filesystem.
4. Chạy chương trình trên Windows/NTFS. Vì sao có `POSIX_NOT_SUPPORTED`? Dùng `icacls` để xem ACE của thư mục test thay vì cố chạy Unix chmod.
5. Cấu hình một appender Log4j 2 `RollingFile` với `filePermissions="rw-------"` trên Linux test; kiểm tra current file và archive sau rollover.
6. Nếu dùng Logback/JUL, tạo file mới dưới service account đã thiết lập `UMask=0077`; kiểm tra mode thật sau restart, không chỉ file cũ.
7. Mô phỏng logrotate trong môi trường test và xác nhận appender vẫn ghi đến file đúng sau rotation; kiểm tra mode cả log hiện tại và file nén.
8. Kiểm tra sự khác nhau giữa container ghi stdout và container ghi file trên volume: ai tạo file, ai có quyền đọc, policy nằm ở tầng nào?

## 16. Ghi nhớ

- **Bảo vệ file log phải bắt đầu từ user/process, thư mục chứa và quyền lúc tạo**, không chỉ `chmod` sau khi sự cố đã xảy ra.
- Với POSIX, `0600` file và `0700` thư mục là điểm xuất phát tốt cho log riêng; `0640`/`0750` phù hợp khi một nhóm được phép đọc.
- Java NIO hỗ trợ `PosixFilePermissions.asFileAttribute(...)` khi tạo file; kiểm tra provider và đọc lại quyền thực tế. Windows dùng ACL.
- File rollover, bản nén, backup, host log của container và collector là **những bản sao cần kiểm soát riêng**.
- Không dùng quyền rộng hoặc chạy root để che giấu lỗi cấu hình. Và quyền file không thay thế redaction, retention, encryption hay cơ chế audit đáng tin cậy.

### Tài liệu tham khảo

- Oracle Java 17 — `Files.createFile`, `Files.createTempDirectory` và file attributes: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Oracle Java 17 — `PosixFileAttributeView` và quyền ban đầu: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html
- Oracle Java 17 — `PosixFilePermissions`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html
- Oracle Java 17 — `AclFileAttributeView`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html
- Apache Log4j 2 — FileAppender permissions: https://logging.apache.org/log4j/2.x/manual/appenders/file.html
- Apache Log4j 2 — RollingFileAppender và `PosixViewAttribute`: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html
- systemd — `UMask`, `LogsDirectory` và `LogsDirectoryMode`: https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
- Microsoft — `icacls`: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/icacls
