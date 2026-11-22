# Quyền ghi file trong Java Logging

**Quyền ghi file** (file write permission) là điều kiện để tiến trình Java tạo, mở, ghi, đổi tên, xoay vòng hoặc xóa tệp log tại một đường dẫn cụ thể. Trong chủ đề **File logging**, đây không chỉ là câu hỏi “file có writable không?”, mà còn liên quan đến **tài khoản chạy JVM, quyền trên thư mục cha, ACL, filesystem, volume mount, cách backend mở file và quy trình rotation**.

Một ứng dụng có thể gọi `logger.info(...)` thành công nhưng không có dòng nào trong `app.log` vì appender/handler không mở được đích ghi. Trái lại, một file đang ghi tốt vẫn có thể thất bại ở lần **rotate** đầu tiên nếu tiến trình có quyền ghi file nhưng không có quyền tạo/xóa/đổi tên trong thư mục.

**Nguyên tắc:** xác minh cả **đường dẫn thực**, **quyền hiệu lực của tiến trình đang chạy**, **khả năng ghi tại thời điểm sử dụng**, và **lỗi do thư viện logging ghi nhận**. Không sửa lỗi bằng cách cấp `chmod 777` hay chạy cả ứng dụng dưới quyền administrator/root nếu không có lý do bảo mật được phê duyệt.

## 1. Đường đi của một log event tới file

Ví dụ với Java Util Logging (JUL):

~~~text
Ứng dụng gọi Logger.info("...")
                |
                v
        java.util.logging.Logger
       (level/filter, routing)
                |
                v
           FileHandler
        (mở stream và lock)
                |
                v
            Formatter
       (tạo text hoặc XML)
                |
                v
      Hệ điều hành / filesystem
      path, process UID, ACL,
       directory, mount, quota
                |
                v
         /path/to/app.log
~~~

Với **SLF4J + Logback**, tên lớp sẽ khác:

~~~text
SLF4J Logger -> Logback provider -> Logback Logger
                                      |
                                      v
                            FileAppender / RollingFileAppender
                                      |
                                      v
                              Encoder / Layout
                                      |
                                      v
                            OS, directory, filesystem
                                      |
                                      v
                                app.log / archives
~~~

**Logger quyết định có tạo sự kiện**, còn **Handler/Appender quyết định gửi nó đến đâu**. Khi ghi file bị từ chối, sửa mức DEBUG/INFO chưa chắc có tác dụng: cần kiểm tra tầng cuối của tuyến này.

Không mặc nhiên cho rằng một lời gọi log ném lỗi ra mã nghiệp vụ khi file ghi thất bại. Nhiều backend cố ghi nhận lỗi ở **kênh chẩn đoán nội bộ** và tiếp tục chương trình. Vì vậy ứng dụng chạy bình thường không phải bằng chứng log đã được lưu.

## 2. Quyền trên file và quyền trên thư mục khác nhau

Với filesystem kiểu POSIX (Linux và nhiều Unix), cần phân biệt **quyền tệp** và **quyền thư mục**.

| Thao tác | Quyền thường cần | Vì sao? |
| --- | --- | --- |
| Đi qua `/var` rồi `/var/log` | Quyền **execute/search (x)** trên từng thư mục cha | Không có x thì không phân giải được đường dẫn |
| Đọc một file log hiện có | Quyền **read (r)** trên file và x trên thư mục cha | Cho phép xem dữ liệu |
| Append vào file đã tồn tại | Quyền **write (w)** trên file, cùng khả năng đi qua đường dẫn | Ghi tiếp nội dung |
| Tạo file log mới | **write + execute (w+x)** trên thư mục đích | Thêm entry mới vào thư mục |
| Xóa/đổi tên file | Thường cần **w+x trên thư mục chứa file** | Thay đổi directory entry |
| Tạo thư mục con | **w+x trên thư mục cha** | Tạo entry thư mục mới |
| Rotate sang một file khác | Quyền ghi/tạo/đổi tên/xóa ở **các thư mục liên quan** | Có thể phải tạo archive và chuyển file |

Quyền còn chịu tác động của **ACL, sticky bit, mount options, chính sách SELinux/AppArmor, filesystem mạng**, và chính sách hệ thống khác; bảng trên là mô hình POSIX thông thường.

Hai tình huống dễ nhầm:

**A. File cũ tồn tại, ghi được, nhưng file mới không tạo được.** File `app.log` có quyền `w` cho tài khoản chạy Java, trong khi thư mục thiếu `w`. Append có thể vẫn hoạt động; nhưng khi xóa file, rotate hoặc tạo `app.1.log`, chương trình thất bại.

**B. Thư mục có quyền ghi, nhưng file cũ thuộc owner khác.** Tiến trình có thể tạo một file mới trong thư mục, nhưng không mở được file cũ ở chế độ append vì file đó thiếu quyền `w` cho người chạy.

Do đó, kiểm tra `ls -l app.log` **một mình là chưa đủ**. Cần xem cả danh tính tiến trình và toàn bộ các thư mục nằm trên đường dẫn.

## 3. User, group, ACL và quyền hiệu lực

Trên Linux, một tiến trình Java chạy với **UID/GID và supplementary groups** hiệu lực. Đó có thể là:

- Tài khoản service như `appuser` do systemd chỉ định.
- UID số như `10001` bên trong container.
- Một người dùng của máy khi chạy từ IDE/terminal.
- Tài khoản khác khi ứng dụng chạy qua cron, scheduler hoặc application server.

**Tài khoản chạy JVM là người cần quyền, không phải người đang mở terminal để kiểm tra.** Nếu bạn tạo thư mục bằng tài khoản developer nhưng service chạy bằng `appuser`, kết quả kiểm tra có thể khác hoàn toàn.

Lệnh kiểm tra trên Linux:

~~~bash
id
ls -ld /var /var/log /var/log/myapp
ls -l /var/log/myapp/app.log
namei -l /var/log/myapp/app.log
~~~

`id` trong shell hiện tại chỉ mô tả **tài khoản đang chạy lệnh**. Với service, hãy xác định user thật của tiến trình bằng cơ chế quản lý service, cấu hình container hoặc công cụ hệ điều hành rồi mới kiểm tra quyền theo user đó.

`namei -l` cho thấy từng thành phần của đường dẫn, giúp phát hiện một thư mục cha thiếu quyền `x`. Không phải mọi môi trường tối giản đều cài sẵn `namei`; khi thiếu, dùng `stat` và `ls -ld` từng thư mục.

Nếu filesystem sử dụng POSIX ACL, kiểm tra:

~~~bash
getfacl /var/log/myapp
getfacl /var/log/myapp/app.log
~~~

Không phải máy nào cũng có `getfacl`. ACL có thể cho phép hoặc hạn chế quyền ngoài ba nhóm owner/group/others mà `ls -l` hiển thị. **ACL mask** cũng có thể làm quyền hiệu lực khác với điều người đọc suy ra khi chỉ xem tên group.

### Quyền tại thời điểm mở file

Ngay cả khi quyền file đã đổi, **file descriptor đang mở** có thể tiếp tục hoạt động trong một số tình huống; lỗi thường xuất hiện khi reopen hoặc rotate. Ngược lại, file có thể bị thay thế bằng một file mới với owner/quyền khác. Cần kiểm tra **tại thời điểm sự cố** và sau các lần deploy/rotate, không chỉ tại startup.

## 4. chmod, chown và umask: sửa đúng đối tượng

Trên Linux/POSIX, hai cơ chế phổ biến:

- `chown`/ `chgrp`: đổi owner/group, nếu có đủ quyền để làm.
- `chmod`: cấp quyền read/write/execute cho owner/group/others hoặc qua ký hiệu symbolic.

Một sơ đồ cấu hình theo nhóm, **chỉ mang tính minh họa**:

~~~bash
# Giả định admin đã tạo tài khoản appuser và nhóm applog.
sudo install -d -o appuser -g applog -m 0750 /var/log/myapp

# Nếu file log đã tồn tại và thuộc chính dịch vụ này:
sudo chown appuser:applog /var/log/myapp/app.log
sudo chmod 0640 /var/log/myapp/app.log
~~~

Đây là ví dụ dành cho Linux có `sudo` và các user/group đã tồn tại; **không chạy nguyên lệnh trên production nếu chưa xác nhận quyền sở hữu thật, nơi ghi và chính sách của hệ thống**. Thư mục `0750` cho owner quyền `rwx`, group quyền `r-x`; file `0640` cho owner quyền `rw-`, group chỉ đọc.

Trường hợp nhiều tiến trình được phép ghi một directory theo nhóm có thể cần thiết kế group khác, ACL phù hợp, hoặc `setgid` directory. Không tự thêm world-writable permissions chỉ để xử lý nhanh.

### Vì sao không dùng chmod 777?

~~~bash
# Tránh áp dụng đại trà:
chmod -R 777 /var/log/myapp
~~~

`777` cho mọi tài khoản quyền đọc/ghi/đi qua thư mục, có thể cho phép sửa hoặc xóa log, cài file giả hoặc gây rủi ro phân quyền. Quyền execute trên **file log văn bản** cũng không cần thiết. Không dùng “app chạy được rồi” làm tiêu chí an toàn.

Thay vào đó, chọn **least privilege**: user dịch vụ chỉ được ghi vào directory dành riêng cho ứng dụng; người đọc log có thể được cấp quyền đọc thông qua group/ACL; hệ thống thu thập log có vai trò riêng.

### umask và file mới

Khi tiến trình tạo file trên POSIX, quyền ban đầu thường chịu tác động của **mode được yêu cầu, umask và ACL mặc định của thư mục**. Với mô hình thường gặp, một file tạo từ mode `0666` dưới umask `0027` có thể thành `0640`. Đây chỉ là ví dụ; kết quả thực còn phụ thuộc API và filesystem.

Do đó, file vừa tạo sau rotate có thể có mode khác file cũ. Kiểm tra cả **quyền trên file mới và user tạo file**, đặc biệt khi logrotate chạy dưới tài khoản khác với ứng dụng.

## 5. Đường dẫn phải tồn tại, hợp lệ và nằm trên filesystem ghi được

Một lỗi ghi file không nhất thiết do permission bit. Các nguyên nhân khác gồm:

- Thư mục cha chưa tồn tại.
- Cấu hình trỏ đến **một thư mục thay vì tệp**.
- Đường dẫn tương đối được giải từ working directory khác với kỳ vọng.
- Mount có chế độ **read-only**.
- Đĩa đầy, hết inode, vượt disk quota.
- Tệp đang bị khóa hoặc bị phần mềm bảo mật ngăn truy cập.
- Đường dẫn có symlink dẫn sang nơi khác, hoặc filesystem không hỗ trợ thao tác cần thiết.

Ví dụ trong Java:

~~~java
Path file = Path.of("logs", "app.log");
~~~

Đây là đường dẫn **tương đối** so với working directory của tiến trình. Chạy từ IDE, Maven, systemd hay container có thể tạo file ở các thư mục khác nhau. Hãy xác nhận `user.dir` hoặc đặt một đường dẫn tuyệt đối được cấu hình rõ, không giả định thư mục `logs` luôn nằm cạnh JAR.

Một số công cụ chẩn đoán trên Linux:

~~~bash
pwd
df -h /var/log/myapp
df -i /var/log/myapp
findmnt -T /var/log/myapp
stat /var/log/myapp
~~~

`df -h` giúp nhận biết dung lượng, `df -i` giúp nhận biết inode và `findmnt` giúp thấy mount nơi chứa thư mục. Một filesystem read-only hoặc hết quota có thể từ chối ghi dù file mode thể hiện có `w`.

**Không nên thay đổi permissions trước khi xác định đúng loại lỗi.** Nếu mount đang read-only, `chmod` không tự biến nó thành read-write; nếu đĩa đầy, đổi owner cũng không giải quyết được.

## 6. Java NIO: phân biệt kiểm tra trước và mở file thật

Java cung cấp `java.nio.file.Files` để truy vấn và thao tác filesystem.

~~~java
boolean writable = Files.isWritable(logPath);
~~~

Đây là **đoạn minh họa** khi đã có `logPath` kiểu `Path` và import `Files`. Kết quả `true` **không bảo đảm** một lần ghi tiếp theo sẽ thành công, bởi:

1. Quyền, đường dẫn, mount hoặc file có thể thay đổi giữa kiểm tra và mở file (**TOCTOU — time-of-check to time-of-use**).
2. Các provider/filesystem khác nhau có thể đưa ra quyết định kiểm tra quyền khác nhau.
3. Mở file có thể thất bại do lock, quota, dung lượng, số lượng file descriptor hoặc vấn đề I/O dù kiểm tra writable không báo lỗi.
4. Khi cần tạo file mới, quyền tạo trong thư mục quan trọng hơn trạng thái writable của một file chưa tồn tại.

**Cách xác nhận có ý nghĩa là một lần thao tác thực** ở đúng vị trí, với đúng tài khoản/container và điều kiện sử dụng, rồi xử lý kết quả hoặc exception.

Ví dụ mở file và ghi thực (đoạn mã bên trong method có `logPath`):

~~~java
try (var writer = Files.newBufferedWriter(
        logPath,
        java.nio.charset.StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.CREATE,
        java.nio.file.StandardOpenOption.APPEND)) {
    writer.write("event=log_probe");
    writer.newLine();
}
~~~

Đoạn trên **thực sự ghi dữ liệu**; không dùng nó như một “kiểm tra vô hại” với file production đang chứa log thật. Khi chẩn đoán, nên tạo một **tệp probe riêng ở cùng directory**, dùng tên được kiểm soát, xóa có điều kiện và lưu ý rằng quyền trên probe file mới **không bảo đảm** file log cũ cũng writable.

### Các loại exception có thể gặp

| Exception | Gợi ý điều tra | Cảnh báo |
| --- | --- | --- |
| `AccessDeniedException` | Quyền trên file/thư mục, ACL hoặc chính sách truy cập | Không phải hệ nào cũng trả cùng subclass |
| `NoSuchFileException` | Thư mục cha/file chưa tồn tại, đường dẫn sai | Có thể khác với `FileNotFoundException` từ API cũ |
| `FileAlreadyExistsException` | Tạo mới bằng `CREATE_NEW` khi tên đã có | Là xung đột tên, không nhất thiết do quyền |
| `FileSystemException` | Lỗi filesystem như đích là directory, lock, read-only hoặc I/O | Đọc thêm `getReason()` nếu có |
| `IOException` | Lỗi I/O tổng quát | Không giả định tất cả đều là permission denied |
| `SecurityException` | Một chính sách kiểm soát quyền ở runtime | Cơ chế SecurityManager truyền thống đã bị giới hạn/loại bỏ dần trên các JDK mới |

`AccessDeniedException` và `NoSuchFileException` là các subclass của `FileSystemException`. Khi bắt exception, các nhánh cụ thể phải đứng **trước** nhánh `FileSystemException`, rồi mới đến `IOException`.

Ví dụ thứ tự bắt lỗi hợp lý:

~~~java
try (var writer = Files.newBufferedWriter(
        logPath,
        java.nio.charset.StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.CREATE,
        java.nio.file.StandardOpenOption.APPEND)) {
    writer.write("event=example");
    writer.newLine();
} catch (java.nio.file.AccessDeniedException e) {
    // Quyền file/thư mục, ACL hoặc chính sách bảo vệ.
} catch (java.nio.file.NoSuchFileException e) {
    // Thường liên quan đường dẫn hoặc thư mục cha.
} catch (java.nio.file.FileSystemException e) {
    // Kiểm tra e.getFile(), e.getReason(), filesystem/mount.
} catch (java.io.IOException e) {
    // Những lỗi I/O còn lại.
}
~~~

Đây là **đoạn minh họa**, không phải class chạy độc lập; dùng file probe riêng khi thực hiện chẩn đoán có tác động ghi. Không log ra console thông tin đường dẫn hoặc exception chứa dữ liệu nhạy cảm nếu không được phép.

## 7. Ví dụ Java 17+ chạy được: ghi qua JUL FileHandler

Ví dụ sau tạo **một thư mục tạm riêng** do tiến trình sở hữu, cấu hình `FileHandler`, phát log, đọc lại nội dung rồi thử mở **chính thư mục như một file** để minh họa lỗi đích không hợp lệ.

**Lưu ý:** trường hợp thử sai đích bên dưới **không mô phỏng thiếu quyền thực tế**; nó chỉ chứng minh ứng dụng cần xử lý `IOException` thay vì tin rằng mọi đường dẫn có thể được ghi.

Tạo file **FilePermissionDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class FilePermissionDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("file-logging-demo-");
        Path file = directory.resolve("app.log");

        Logger logger = Logger.getLogger("demo.file.PermissionDemo");
        logger.setUseParentHandlers(false);

        FileHandler handler = new FileHandler(file.toString(), true);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        logger.addHandler(handler);
        try {
            logger.info("event=log_written requestId=req-001");
        } finally {
            handler.flush();
            logger.removeHandler(handler);
            handler.close();
        }

        System.out.println("fileExists=" + Files.isRegularFile(file));
        System.out.println("content=" + Files.readString(file).strip());

        boolean invalidTargetRejected = false;
        try (var writer = Files.newBufferedWriter(
                directory, StandardOpenOption.CREATE,
                StandardOpenOption.APPEND)) {
            writer.write("not expected");
        } catch (IOException expected) {
            invalidTargetRejected = true;
        }
        System.out.println("invalidTargetRejected=" + invalidTargetRejected);

        Files.deleteIfExists(file);
        Files.deleteIfExists(directory);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 FilePermissionDemo.java
java FilePermissionDemo
~~~

**Output chính xác trên stdout** của lần kiểm chứng trên môi trường thử nghiệm:

~~~text
fileExists=true
content=INFO | event=log_written requestId=req-001
invalidTargetRejected=true
~~~

Cách đọc kết quả:

- `Files.createTempDirectory` tạo vị trí riêng cho bài thử, không đòi quyền ghi thư mục hệ thống như `/var/log`.
- `new FileHandler(file.toString(), true)` yêu cầu JUL mở đường dẫn ghi log, với lựa chọn append. Handler có thể tạo file và lock phụ trợ theo implementation.
- `logger.info` phát sự kiện, Formatter tạo dòng `INFO | ...`, `flush`/ `close` kết thúc ghi trước khi đọc.
- `Files.isRegularFile(file)` xác nhận đường dẫn trở thành tệp thường. `Files.readString(file)` đối chiếu nội dung đã ghi.
- `Files.newBufferedWriter(directory, ...)` cố mở **đường dẫn là directory** để ghi; hệ điều hành từ chối bằng `IOException`. Đây là ví dụ “đích không phải tệp hợp lệ”, **không phải** bằng chứng quyền `w` bị thiếu.
- Chương trình xóa file/thư mục thử nghiệm sau khi đã xác nhận kết quả, và không sửa bất kỳ file log sản xuất nào.

Đầu ra có thể khác khi một filesystem đặc biệt không tuân theo hành vi tệp/thư mục thông thường, hoặc một lỗi khác xảy ra trước khi bài thử hoàn thành. Trong môi trường tiêu chuẩn đã kiểm chứng, cả ba dòng trên được in đúng.

**Giới hạn:** ví dụ không cố ý tạo file chỉ đọc vì cách thay quyền và hành vi root/ACL trên Windows, Linux, container khác nhau. Để kiểm tra thiếu quyền thật, hãy chạy test với **tài khoản service và mount thực tế** trong một môi trường được phép thử, không tự chmod hệ thống để ép lỗi.

## 8. FileHandler của JDK và quyền ghi

Trong JUL, `java.util.logging.FileHandler` có thể tạo file, append và thực hiện rotation. Chẳng hạn:

~~~java
// Đoạn minh họa bên trong phương thức có biến logDir kiểu Path.
Path logFile = logDir.resolve("application.log");
FileHandler handler = new FileHandler(logFile.toString(), true);
handler.setFormatter(new java.util.logging.SimpleFormatter());
logger.addHandler(handler);
~~~

Các điều kiện cần kiểm tra:

1. **Thư mục chứa file tồn tại**, hoặc ứng dụng có một bước tạo directory phù hợp. Không mặc nhiên cho rằng FileHandler tự tạo toàn bộ thư mục cha ở mọi cấu hình.
2. **User chạy JVM có quyền tạo/mở file** và quyền đi qua các thư mục trên đường dẫn.
3. **File lock và giới hạn số file mở** cho phép handler sử dụng file. FileHandler có cơ chế lock hỗ trợ tránh ghi cùng file theo cách xung đột.
4. **Nếu bật rotation**, handler cần quyền tạo file mới và đổi tên/ghi các file luân phiên.
5. **Formatter và level** đã được cấu hình để có output mong muốn; không phải lỗi permission nào cũng khiến Java ném lỗi ngay khi `logger.info` được gọi.

Các ký hiệu pattern của JUL FileHandler có thể bao gồm `%h` (home directory), `%t` (temporary directory), `%u` (số duy nhất để phân biệt khi trùng) và `%g` (generation cho rotation). Đây là **quy ước pattern của JUL FileHandler**, không phải token của Logback PatternLayout.

Cấu hình `logging.properties` minh họa:

~~~properties
handlers = java.util.logging.FileHandler
.level = INFO

java.util.logging.FileHandler.pattern = /var/log/myapp/java-%u-%g.log
java.util.logging.FileHandler.limit = 10485760
java.util.logging.FileHandler.count = 5
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
~~~

Đây là cấu hình Linux minh họa với **limit 10 MiB** và tối đa 5 generation theo quy ước JUL. Nó chỉ phù hợp khi thư mục đã sẵn sàng và có quyền. **Không dán đường dẫn Linux vào Windows** rồi kỳ vọng hoạt động.

Trong ứng dụng thật, cũng cần kiểm tra cơ chế quản lý LogManager, thời điểm nạp properties, và xung đột giữa code tạo FileHandler thủ công với Handler được cấu hình tự động.

## 9. Logback FileAppender và RollingFileAppender

Khi ứng dụng dùng SLF4J với Logback backend, cách ghi file do **FileAppender** hoặc **RollingFileAppender** đảm nhiệm. Cấu hình Logback ví dụ:

~~~xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>/var/log/myapp/app.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Cấu hình chỉ minh họa trên một môi trường cho phép ghi vào `/var/log/myapp`. Khi Logback không mở được file, vấn đề có thể được báo bằng **internal status messages**, không nhất thiết được ném như exception cho mã đang gọi `logger.info`.

Để chẩn đoán Logback, có thể tạm bật:

~~~xml
<configuration debug="true">
    <!-- Appender và root của ứng dụng -->
</configuration>
~~~

Đoạn này là **fragment**, không phải tệp cấu hình độc lập. Một lựa chọn không phụ thuộc XML là chạy với:

~~~bash
java -Dlogback.statusListenerClass=STDOUT -jar app.jar
~~~

Khi JVM có Logback phù hợp, status có thể cho biết tên file, lỗi tạo appender hoặc lỗi quyền. Cách bật status không tự cấp quyền: phải sửa vấn đề filesystem hoặc đường dẫn theo đúng tài khoản.

### Vì sao file đang ghi được nhưng rolling vẫn thất bại?

Với RollingFileAppender, ngoài ghi file hiện tại còn có thể cần:

- Đổi tên hoặc di chuyển file hiện tại.
- Tạo file mới sau rotation.
- Tạo thư mục archive nếu path khác.
- Nén và xóa archive cũ.
- Ghi đồng thời vào filesystem có mount hoặc quota giới hạn.

**Quyền append lên file hiện tại không bảo đảm có quyền rename/delete/archive.** Cần kiểm tra quyền `w+x` ở directory thích hợp và chính sách filesystem; một lỗi chỉ xuất hiện ở ranh giới thời gian/ngưỡng kích thước thường liên quan rotation.

Nếu hệ thống còn dùng công cụ **logrotate** bên ngoài, phải phối hợp cơ chế reopen/rotate của ứng dụng: đổi tên file nhưng JVM tiếp tục giữ descriptor cũ có thể khiến dữ liệu vẫn được ghi vào inode cũ. Giải pháp phù hợp tùy backend và công cụ; `copytruncate` có cửa sổ mất/nhân bản dữ liệu nên không xem là lựa chọn an toàn mặc định.

## 10. Kiểm tra đúng tài khoản dịch vụ trên Linux

Ví dụ một Java service được systemd chạy dưới tài khoản `appuser`. Hãy xác định user trong cấu hình service và process thực tế:

~~~bash
systemctl cat myapp.service
systemctl show myapp.service -p User -p Group
ps -eo pid,user,group,args
~~~

Các câu lệnh trên là **lệnh xem thông tin**. `myapp.service` là tên minh họa; với đơn vị systemd thật, dùng tên service tương ứng. Không dùng cấu hình một unit giả định để tự thay quyền trên máy khác.

Sau đó kiểm tra đường dẫn:

~~~bash
namei -l /var/log/myapp/app.log
ls -ld /var/log/myapp
ls -l /var/log/myapp/app.log
getfacl /var/log/myapp
df -h /var/log/myapp
~~~

Một bài thử tạo file riêng trong log directory **chỉ nên thực hiện khi được phép**, với đúng user dịch vụ và tên kiểm thử được kiểm soát. Tránh ghi thử vào file log đang hoạt động vì dễ gây nhiễu, rò rỉ dữ liệu hoặc thay đổi lịch sử.

### systemd sandbox và read-only paths

Ngay cả khi file mode cho phép ghi, service có thể bị giới hạn bởi systemd sandbox options, mount namespace hoặc quyền vào thư mục. Ví dụ các thiết lập như `ProtectSystem`, `ReadWritePaths`, `StateDirectory` hoặc `LogsDirectory` ảnh hưởng tới đường ghi được phép. Cần xem **cấu hình unit thực tế và thư mục mà systemd cấp**, không chỉ nhìn `chmod` trong shell bên ngoài.

Nếu cần để systemd quản lý thư mục log, một cấu hình `LogsDirectory` thích hợp có thể hỗ trợ cấp đường dẫn/quyền hợp lệ tùy phiên bản systemd và chính sách. Không mặc định chỉ thêm `ReadWritePaths` là giải quyết được ACL, quota hoặc mount read-only ở tầng thấp.

## 11. Windows: NTFS ACL, service account và file lock

Trên Windows, khái niệm `chmod 640` không diễn tả đầy đủ quyền NTFS. Quyền ghi phụ thuộc **NTFS ACL, tài khoản và nhóm của tiến trình, quyền effective, file sharing mode, security policy và phần mềm bảo vệ**.

Các tình huống thường gặp:

- Chạy từ IDE bằng tài khoản cá nhân thành công, nhưng Windows Service chạy dưới **LocalService**, **NetworkService**, **LocalSystem** hoặc tài khoản miền khác nên không có quyền vào thư mục.
- Đặt log dưới `C:\\Program Files\\...` hoặc thư mục được bảo vệ; ứng dụng không nên mặc nhiên được phép ghi ở đó.
- File được tiến trình khác mở với sharing mode không cho ghi/rename.
- NTFS ACL cho quyền đọc nhưng không cho sửa/xóa; rotate có thể thất bại.
- Dịch vụ bảo mật hoặc Controlled Folder Access có thể ngăn ghi dù ACL trông có vẻ phù hợp.

Một vài lệnh chẩn đoán trong Windows Command Prompt/PowerShell:

~~~powershell
whoami
whoami /groups
icacls "C:\ProgramData\MyApp\logs"
Get-Acl "C:\ProgramData\MyApp\logs" | Format-List
~~~

`whoami` hiển thị người chạy shell hiện tại, không tự chứng minh service JVM dùng cùng token. Cần xác nhận tài khoản service thật trong Services, Task Scheduler hoặc cấu hình ứng dụng.

Với ứng dụng Windows, hãy chọn thư mục dữ liệu/log phù hợp như một directory con có kiểm soát dưới `ProgramData`, rồi cấp **quyền tối thiểu** cho đúng tài khoản. Đừng giải quyết bằng cách chạy toàn bộ chương trình dưới quyền Administrator khi chỉ cần quyền ghi ở một directory riêng.

## 12. Docker và container: UID, bind mount và filesystem chỉ đọc

Trong container, tiến trình Java có thể chạy với một UID khác user trên host. Volume gắn vào container vẫn chịu quyền của filesystem bên dưới.

Ví dụ Dockerfile:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar /app/app.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là **Dockerfile minh họa**, giả định có `app.jar` ở build context. Nếu application muốn ghi `/app/logs/app.log`, directory đó phải writable đối với UID 10001 hoặc được cấp mount phù hợp. File trong image có thể thuộc root hoặc filesystem runtime có thể read-only.

Ví dụ bind mount qua Docker Compose:

~~~yaml
services:
  app:
    image: example/myapp:local
    user: "10001:10001"
    volumes:
      - ./logs:/var/log/myapp
    environment:
      LOG_PATH: /var/log/myapp/app.log
~~~

`example/myapp:local` chỉ là image minh họa. Quyền của thư mục host `./logs` phải được cấu hình phù hợp với UID/GID có hiệu lực trong container; việc khai báo `volumes` **không tự chown/chmod host path**.

Có thể kiểm tra bên trong container bằng công cụ được phép và có sẵn trong image:

~~~bash
id
ls -ld /var/log/myapp
ls -l /var/log/myapp/app.log
~~~

Một số image Java tối giản không có shell hoặc `ls`; khi đó cần quan sát bằng công cụ runtime hoặc một container chẩn đoán được quản trị phù hợp.

**Khuyến nghị vận hành:** đối với container ứng dụng thông thường, cân nhắc xuất log ra **stdout/stderr** để container runtime/collector quản lý, thay vì buộc ứng dụng phải ghi trực tiếp vào filesystem bên trong. Khi thực sự cần file log, hãy thiết kế volume, quyền và rotation rõ ràng.

## 13. Kubernetes: securityContext, volume và readOnlyRootFilesystem

Trong Kubernetes, nhiều ứng dụng chạy non-root và có thể bật `readOnlyRootFilesystem: true`. Khi đó ghi vào một đường dẫn thuộc root filesystem của image có thể bị từ chối, dù quyền mode trên file trông phù hợp.

Có thể dùng volume writable nếu nghiệp vụ yêu cầu ghi file. Ví dụ Pod fragment:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-log-demo
spec:
  securityContext:
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: app
      image: example/myapp:local
      securityContext:
        readOnlyRootFilesystem: true
      volumeMounts:
        - name: log-volume
          mountPath: /var/log/myapp
  volumes:
    - name: log-volume
      emptyDir: {}
~~~

Đây là **manifest minh họa**, không tự bảo đảm ứng dụng hiện có được build/chạy. Volume `emptyDir` có vòng đời gắn với Pod và không phải nơi lưu log bền vững lâu dài. `fsGroup` có thể giúp cấp quyền nhóm cho những loại volume/driver hỗ trợ, nhưng **không bảo đảm mọi CSI/hostPath/NFS mount** sẽ được sửa ownership phù hợp.

Kiểm tra:

- UID/GID thực và `securityContext` của Pod/container.
- Volume được mount vào **đúng đường dẫn** mà backend sử dụng.
- Volume có writable không, filesystem có đủ quota/dung lượng không.
- Nếu dùng persistent volume, CSI driver và ownership/ACL có được áp dụng đúng không.
- Việc rotate/archive cần quyền với cả file hiện tại và các thư mục đích.

Không khuyến nghị bật `privileged` hoặc chạy root chỉ để ghi file. Với phần lớn workload Kubernetes, ghi stdout/stderr và để hạ tầng tập trung log xử lý thường đơn giản hơn việc quản lý file log trong Pod.

## 14. Vấn đề khi rotate: inode, rename, archive và lock

Ghi file không chỉ là `append`. Một tuyến file logging có thể đi qua:

~~~text
app.log đang mở
       |
  đạt ngưỡng kích thước/thời gian
       |
  đóng hoặc chuyển file handle phù hợp
       |
  app.log -> archive/app-2026-11-09.1.log
       |
  tạo app.log mới
       |
  ghi tiếp vào file mới
       |
  xóa/nén archive cũ khi vượt retention
~~~

Từng bước có thể đụng quyền khác nhau:

- Ghi `app.log` cần quyền ghi lên file.
- Đổi tên cần quyền thay đổi entry ở directory, cùng điều kiện về sticky bit/ACL.
- Tạo log mới cần quyền tạo trong directory.
- Nén/xóa archive cần quyền tương ứng tại vị trí archive.
- Copy sang filesystem khác có thể có hành vi khác rename trong cùng filesystem.
- Windows có thể từ chối rename/delete khi một process giữ file handle với sharing mode hạn chế.
- NFS và các filesystem mạng có thể bổ sung yêu cầu lock, UID mapping hoặc chính sách server.

Vì vậy hãy **kiểm tra sau ít nhất một lần rotation** trong môi trường thử, không chỉ kiểm tra dòng đầu tiên sau startup.

Nếu hệ thống vừa dùng rolling của Logback/JUL vừa dùng một chương trình rotate ngoài, tránh hai cơ chế cạnh tranh thao tác trên cùng file; chọn một chiến lược được backend/hạ tầng hỗ trợ và kiểm thử reopen/rename.

## 15. Kiểm tra file permission bằng Java: giới hạn và nguyên tắc an toàn

Một số hàm Java hữu ích:

~~~java
// Đoạn minh họa trong phương thức với Path target:
boolean exists = Files.exists(target);
boolean writable = Files.isWritable(target);
boolean regular = Files.isRegularFile(target);
Path parent = target.getParent();
~~~

Chúng giúp **định hướng chẩn đoán**, không tạo bảo đảm rằng mở file sẽ thành công. File có thể thay đổi ngay sau kiểm tra.

Khi thao tác thực:

- Dùng **đường dẫn được cấu hình tin cậy**, không lấy nguyên input người dùng để chọn nơi ghi.
- Không tự tạo/tùy ý xóa file production khi chỉ đang thử quyền.
- Phân biệt **kiểm thử tạo file mới** và **quyền append vào file đã tồn tại**; đó là hai điều kiện khác nhau.
- Bắt `IOException` theo loại cụ thể khi có lợi, nhưng không hard-code kết luận từ một exception message duy nhất.
- Không ghi exception chứa thông tin đường dẫn nhạy cảm ra kênh công khai.
- Khi ứng dụng không tự tạo được parent directory, có thể dùng `Files.createDirectories(parent)` nếu **được phép và chính sách triển khai cho phép**; không gọi bừa trên hệ thống quản lý bởi hạ tầng.

### Nếu có symlink, không được tin path string đơn thuần

Một đường dẫn file log có thể là symbolic link trỏ sang nơi khác. Chương trình chạy với quyền cao mà ghi vào path do người dùng khác có thể thay thế có nguy cơ **symlink/path traversal attack**.

Giải pháp thiết kế:

1. Đường dẫn log xuất phát từ **trusted configuration**, không ghép thẳng đường dẫn người dùng nhập.
2. Thư mục log nên do user/service hoặc quản trị viên được tin tưởng sở hữu, không cho người không tin cậy tạo/đổi symlink.
3. Xác nhận mount và vị trí thực của file; chỉ cho phép ghi trong vùng được quản lý.
4. Dùng các cơ chế mở file an toàn phù hợp nền tảng khi threat model yêu cầu, không coi một lần `normalize()` là đủ để loại mọi symlink race.
5. Không cấp quyền root chỉ để tránh lỗi permissions, vì hậu quả khi đường dẫn bị chiếm quyền sẽ lớn hơn.

## 16. Ghi log thất bại cần được phát hiện như thế nào?

Khi backend không thể mở hoặc ghi file, một số chiến lược có thể giúp quan sát sự cố:

- **Kênh chẩn đoán của backend:** với Logback, dùng status listener/StatusManager để xem lỗi FileAppender/RollingFileAppender.
- **Log khởi động trên stderr hoặc console:** khi phù hợp, giữ một đường chẩn đoán độc lập với file đang lỗi.
- **Health/monitoring:** theo dõi dung lượng, filesystem read-only, quyền mount, lỗi rotation và trạng thái collector.
- **Kiểm thử đích thật:** phát một sự kiện có ID thử nghiệm không nhạy cảm và xác minh nó được ghi đúng file/collector, không chỉ thấy lời gọi log không ném exception.
- **Thiết kế fallback:** nếu file log thất bại, có thể cấu hình một đích console đáng tin trong phạm vi cho phép; nhưng fallback phải được thử và không tự động “đảm bảo không mất log”.

Đặc biệt, **logging thông thường không phải kho lưu audit giao dịch**. Nếu yêu cầu không được mất dấu vết nghiệp vụ hoặc pháp lý, cần cơ chế lưu trữ bền vững, phân quyền, retention và xác nhận ghi riêng. Không coi một FileAppender thành công lúc startup là cam kết an toàn dữ liệu tuyệt đối.

## 17. Một số tình huống thực tế

### Tình huống A: chạy bằng IDE được, systemd lỗi

Developer có quyền ghi `./logs` trong workspace, nhưng service chạy bằng user khác và working directory khác. Cần xác định user của service, `WorkingDirectory`, đường dẫn tuyệt đối và quyền directory/file; không sửa bằng cách thêm chmod lên một thư mục khác vì tên giống nhau.

### Tình huống B: app.log vẫn ghi nhưng rotate không được

Owner được phép append vào file `app.log`, nhưng directory thiếu quyền đổi tên/tạo archive. Khi đạt ngưỡng, RollingFileAppender có thể báo lỗi. Cần kiểm tra directory archive và quyền rename/create/delete, không chỉ `-rw-` của `app.log`.

### Tình huống C: container báo AccessDeniedException

Container chạy UID 10001, bind mount trên host thuộc UID 1000 và không cho group write. Cần điều chỉnh quyền/ACL hoặc chiến lược volume theo UID/GID phù hợp, **không mặc nhiên dùng chmod 777 hoặc đổi container sang root**.

### Tình huống D: filesystem read-only

File mode hiển thị writable nhưng container dùng read-only root filesystem; file log nằm ngoài các mounted writable volumes. Cần chọn một đường mount có thể ghi hoặc chuyển sang stdout/stderr. Chmod không giải quyết mount read-only.

### Tình huống E: file log nằm trong Program Files

Windows Service không có quyền sửa một file thuộc khu vực cài đặt phần mềm. Nên chuyển log tới thư mục dữ liệu chuyên dụng có ACL đúng tài khoản dịch vụ, thay vì khởi động toàn bộ service dưới Administrator.

### Tình huống F: quyền tốt nhưng file không tạo

Đường dẫn sai, parent không tồn tại, disk quota đầy hoặc backend không nạp config mong đợi. Xem exception/status và đích thực tế thay vì kết luận lỗi permission chỉ vì “không có file”.

### Tình huống G: đổi owner rồi lỗi quay lại sau một ngày

Một tác vụ rotate hoặc deploy tạo file mới dưới user khác, nên file mới có quyền không phù hợp. Cần sửa **quy trình tạo file mới** và chính sách ownership, không chỉ chown thủ công file hiện tại mỗi ngày.

## 18. Bảng lỗi và hướng điều tra

| Triệu chứng | Nguyên nhân có thể | Cần kiểm tra |
| --- | --- | --- |
| `AccessDeniedException` khi mở file | UID/ACL/quyền file hoặc directory, security policy | User chạy JVM, từng parent directory, ACL, mount |
| `NoSuchFileException` | Sai path, directory chưa tồn tại | Absolute path, working directory, bước tạo thư mục |
| File mới không tạo nhưng file cũ append được | Thư mục thiếu `w+x` | Directory permissions, ACL |
| Append thất bại nhưng tạo file mới được | File cũ không writable/lock | File owner, ACL, sharing mode |
| File ghi rồi nhưng rolling fail | Thiếu quyền rename/archive/delete | Quyền directory, archive path và log rotation |
| IDE ghi được, service không | Khác account hoặc working directory | systemd User/Group hoặc Windows Service account |
| Container ghi file thất bại | UID/GID không khớp volume, root filesystem read-only | Mount path, securityContext, host perms |
| Không thấy lỗi trong business code | Backend báo lỗi ở status/error handler | Logback StatusManager, JUL handler config/stderr |
| File không được tạo dù không có lỗi quyền | Logger level/filter/appender không active | Logging config và đường xuất |
| Tên file thay đổi hoặc file khác được tạo | Pattern `%u`/`%g`, working dir hoặc rotation | FileHandler pattern, path và runtime |
| Log trùng | Gắn nhiều Handler/Appender, parent routing | Cấu hình logger hierarchy, additivity |
| Ghi thất bại khi volume đầy | Disk space/inode/quota, không phải chmod | `df -h`, `df -i`, quota, status |
| Windows rename bị từ chối | File handle bị lock/sharing mode | Process đang mở file và policy NTFS |
| Log chứa dữ liệu nhạy cảm | Thiếu chính sách allowlist/redaction | Nội dung message, formatter, quyền đọc file |

## 19. Quy trình khắc phục theo từng bước

Khi file logging không hoạt động, thực hiện theo thứ tự:

1. **Xác định lệnh logger có chạy:** nguồn phát có thực sự đến được `logger.info` hoặc `logger.error` không?
2. **Xác định backend và handler/appender:** JUL FileHandler, Logback FileAppender/RollingFileAppender hay Log4j 2? File cấu hình nào được nạp?
3. **Xác định đường dẫn thực:** absolute path, working directory, container mount; kiểm tra path có bị sai hoặc trỏ vào directory không.
4. **Xác định tài khoản thật:** UID/GID/groups hoặc Windows service identity. Đừng dùng quyền của shell developer thay thế.
5. **Kiểm tra directory và file:** quyền đi qua parent, tạo file, append file, ACL và policy.
6. **Kiểm tra filesystem:** read-only, dung lượng, inode, quota, symlink, lock và mount type.
7. **Đọc lỗi cụ thể:** exception Java khi mở file hoặc status nội bộ của backend; không suy đoán từ “không thấy log”.
8. **Sửa tối thiểu:** owner/group/ACL cho đúng thư mục; hoặc đổi đích ghi sang nơi được hỗ trợ. Tránh chmod 777 và root.
9. **Kiểm thử ghi thực:** một event thử có ID không nhạy cảm; kiểm tra đúng file và collector nhận nó.
10. **Kiểm thử rotation/restart:** quyền tạo/rename/delete có tiếp tục đúng sau restart hoặc log rotation không?
11. **Bảo vệ và giám sát lâu dài:** theo dõi các lỗi appender, đầy ổ đĩa, volume, retention và quyền xem log.

Không nên triển khai một “fix” chỉ vì file có thể tạo sau khi chạy với tài khoản root. Cần xác nhận thiết kế nguyên tắc **quyền tối thiểu** dưới tài khoản dịch vụ thực.

## 20. Bài tập tự kiểm tra

**Bài 1.** Một file `/var/log/myapp/app.log` có owner là `appuser` và mode `0640`, còn thư mục `/var/log/myapp` có mode `0550`, owner `appuser`. Giả sử các thư mục cha có x và không có ACL/chính sách phụ. Điều gì có thể xảy ra?

**Đáp án:** `appuser` có quyền ghi lên **file hiện có** nên append có thể hoạt động, nhưng không có `w` trên directory, vì vậy tạo file mới, đổi tên/xóa entry và rotation có thể thất bại. Quyền `w` trên file không thay quyền `w` trên directory.

**Bài 2.** Một Pod dùng `readOnlyRootFilesystem: true`, không mount volume tại `/app/logs`, nhưng một Logback FileAppender ghi `/app/logs/app.log`. Có nên `chmod 777 /app/logs`?

**Đáp án:** Không. Root filesystem không writable, nên chmod không phải giải pháp. Có thể dùng stdout/stderr hoặc mount một writable volume tại đường dẫn đã kiểm soát.

**Bài 3.** FileHandler tạo được log khi chạy IDE nhưng thất bại dưới Windows Service. Có thể kết luận mã Java sai không?

**Đáp án:** Không. Cần kiểm tra user/token và NTFS ACL của Windows Service, working directory, file locking và đích ghi. Quyền của tài khoản IDE không nói lên quyền của service.

**Bài 4.** Một chương trình gọi `Files.isWritable(file)` và nhận `true`, rồi `newBufferedWriter` ném `IOException`. Đây có phải lỗi Java không?

**Đáp án:** Chưa chắc. `isWritable` chỉ là một kiểm tra tại thời điểm nhất định. Sau đó file/mount/quota/lock có thể thay đổi hoặc các điều kiện khác gây lỗi; phải xem exception và hệ thống file.

**Bài 5.** Khi nào một cảnh báo từ `StatusManager` của Logback hữu ích hơn việc gọi thêm `logger.error`?

**Đáp án:** Khi chính FileAppender/rolling/config của logging bị lỗi. `logger.error` cũng có thể đi qua đường ghi đang hỏng; status cung cấp kênh chẩn đoán nội bộ.

## 21. Checklist trước khi đưa file logging vào production

- [ ] Đường dẫn log được cấu hình rõ, không phụ thuộc working directory bất ngờ.
- [ ] User chạy JVM có đúng UID/GID/ACL cần thiết.
- [ ] Có **x** trên các directory cha, quyền **w** trên file đang append.
- [ ] Có **w+x** trên directory nơi cần tạo file/rotate/archive.
- [ ] Không dùng `chmod 777` hay root/Administrator để che lỗi thiết kế.
- [ ] Filesystem/volume thực sự writable và còn dung lượng/quota.
- [ ] Backend/handler/appender được nạp đúng và có đường báo lỗi nội bộ.
- [ ] Đã kiểm thử một lần ghi thực và đọc lại đích nhận.
- [ ] Đã kiểm thử file mới sau restart và file archive sau rotation.
- [ ] Container/Pod có volume hoặc stdout/stderr strategy rõ ràng.
- [ ] File log không chứa bí mật không cần thiết; quyền đọc và retention được quản lý.
- [ ] Đường dẫn/trusted configuration không cho người không tin cậy thay bằng symlink.
- [ ] Có theo dõi lỗi I/O, lock, đầy ổ, hết inode và mất quyền sau deploy.

**Ghi nhớ:** Để ghi file log, Java cần nhiều hơn một file có chữ `w` trên kết quả `ls -l`. Phải xác định **đúng tiến trình**, **đúng file và thư mục**, **đúng filesystem/mount**, cùng **quyền cho cả append lẫn tạo/đổi tên/xoay vòng**. Dùng thông báo lỗi thật và kiểm thử đầu ra thực tế, sửa quyền **tối thiểu cần thiết** thay vì cấp toàn quyền, sẽ giúp file logging vừa hoạt động ổn định vừa an toàn.