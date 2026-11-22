# Thiếu quyền thao tác trong ứng dụng Java

**Thiếu quyền thao tác** xảy ra khi process Java yêu cầu đọc, ghi, tạo, xóa, thực thi hoặc kết nối tới một tài nguyên mà danh tính đang chạy process không được phép sử dụng. Tài nguyên đó có thể là file, thư mục, socket, cổng mạng, thiết bị, tiến trình khác, database hoặc API.

Một ứng dụng có thể chạy bình thường trên máy developer nhưng lỗi trong CI, service hoặc container vì process ở các môi trường đó chạy bằng tài khoản khác. Quyền của user đang đăng nhập không tự động được áp dụng cho JVM, Windows service, Linux daemon hay container.

Cách xử lý hiệu quả là xác định thao tác bị từ chối, tài nguyên đích và danh tính process; đọc loại exception cùng nguyên nhân hệ điều hành trả về; sau đó cấp đúng quyền tối thiểu tại tài nguyên đó. Chạy ứng dụng bằng Administrator/root hoặc cấp quyền toàn bộ ổ đĩa thường che mất nguyên nhân và tạo thêm rủi ro.

## 1. Xác định thao tác nào bị từ chối

Trước khi thay đổi permission, hãy mô tả thao tác cụ thể:

| Thao tác | Quyền thường cần |
|---|---|
| Đọc file | Quyền đọc file và quyền đi qua các thư mục cha |
| Ghi file đã có | Quyền ghi file; có thể cần quyền trên thư mục tùy thao tác |
| Tạo file mới | Quyền ghi và traverse/search trên thư mục cha |
| Xóa file | Quyền ghi và traverse/search trên thư mục cha; có thể chịu sticky bit hoặc ACL |
| Đổi tên/di chuyển file | Quyền ghi và traverse trên thư mục nguồn/đích liên quan |
| Liệt kê thư mục | Quyền đọc và traverse thư mục |
| Đi qua thư mục | Quyền execute/search trên thư mục |
| Chạy chương trình ngoài | Quyền execute trên file, quyền traverse trên đường dẫn và interpreter hợp lệ |
| Bind cổng mạng | Quyền bind cổng theo OS, capability và chính sách mạng |
| Kết nối dịch vụ | Quyền mạng, firewall/egress policy, proxy và xác thực dịch vụ |
| Đọc secret/device | ACL, service identity, device permission hoặc policy của nền tảng |

Không suy luận rằng “không ghi được file” luôn có nghĩa file đó thiếu write bit. Nếu ứng dụng cần tạo file mới, quyền quan trọng có thể nằm ở thư mục cha. Nếu cần xóa file, quyền write trên chính file thường không quyết định khả năng xóa; hệ thống kiểm tra quyền trên thư mục chứa file và các policy liên quan.

Hãy lấy đúng đường dẫn tuyệt đối, tên thao tác, thời điểm xảy ra, process ID và môi trường chạy. Một thông báo lỗi chỉ nói “access denied” mà thiếu các thông tin này thường chưa đủ để xác định chỗ cần sửa.

## 2. Phân biệt các exception Java

Java biểu diễn lỗi truy cập bằng nhiều loại exception tùy API và hệ thống file.

| Exception | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| **AccessDeniedException** | File system từ chối thao tác, thường do permission hoặc access check | User/group/ACL, parent directory, mount và service identity |
| **FileSystemException** | Lỗi file system có thêm file, file khác hoặc reason | Đọc getFile(), getOtherFile(), getReason() |
| **NoSuchFileException** | Không tìm thấy file hoặc thành phần đường dẫn | Working directory, path, mount và tên file |
| **FileAlreadyExistsException** | File đã tồn tại trong thao tác yêu cầu tạo mới | Kiểm tra CREATE_NEW và logic tên file |
| **SecurityException** | API hoặc thư viện từ chối một thao tác theo quy tắc bảo mật của nó | Stack trace, API gọi và policy của nền tảng |
| **IOException** | Lỗi I/O tổng quát; có thể chứa thông báo do OS/provider cung cấp | Cause, message, file path và hệ điều hành |
| **AccessControlException** | Exception lịch sử gắn với Java Security Manager | Kiểm tra code/library cũ và phiên bản JDK |

AccessDeniedException là checked exception kế thừa FileSystemException, do đó cũng là một dạng IOException. NIO thường ném exception này khi một thao tác file bị từ chối.

SecurityException là unchecked exception. Không nên tự động kết luận nó luôn có nghĩa file system permission sai. Nó có thể được ném bởi API, thư viện hoặc đoạn code ứng dụng có kiểm tra quyền riêng.

Khi log lỗi, giữ lại loại exception, message, cause, stack trace và đường dẫn liên quan. Tránh chỉ ghi e.getMessage() rồi bỏ mất thông tin cần thiết để điều tra.

Ví dụ xử lý:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadConfig {
    public static void main(String[] args) {
        Path path = Path.of("config", "app.properties");

        try {
            String content = Files.readString(path);
            System.out.println(content);
        } catch (AccessDeniedException e) {
            System.err.println("Access denied: " + e.getFile());
            System.err.println("Reason: " + e.getReason());
        } catch (IOException e) {
            System.err.println("I/O error: " + e.getClass().getSimpleName());
            System.err.println("Message: " + e.getMessage());
            e.printStackTrace(System.err);
        } catch (SecurityException e) {
            System.err.println("Operation rejected: " + e.getMessage());
            e.printStackTrace(System.err);
        }
    }
}
```

Ví dụ này minh họa cách phân loại lỗi. File config/app.properties phải tồn tại và được đọc bằng UTF-8 theo hành vi của Files.readString(Path).

## 3. Xác định danh tính thực tế của JVM

Quyền được đánh giá theo process đang thực hiện thao tác. Hãy xác định JVM đang chạy dưới user/group nào.

Trong Java có thể in một số thông tin cơ bản:

```java
System.out.println("user.name=" + System.getProperty("user.name"));
System.out.println("user.dir=" + System.getProperty("user.dir"));
System.out.println("java.home=" + System.getProperty("java.home"));
System.out.println("os.name=" + System.getProperty("os.name"));
System.out.println("os.arch=" + System.getProperty("os.arch"));
```

user.name và user.dir hữu ích để chẩn đoán nhưng không thay thế việc kiểm tra identity ở hệ điều hành. user.name là system property, có thể không phản ánh đầy đủ effective UID/GID, Windows token hoặc service identity.

Trên Linux:

```sh
id
whoami
ps -o pid,user,group,uid,gid,comm -p <PID>
```

Trên Windows:

```powershell
whoami
whoami /all
Get-Process -Id <PID>
```

Trong container, chạy lệnh id bên trong đúng container/process namespace. Đừng suy luận từ user trên host hoặc từ tài khoản đã chạy lệnh docker.

Các tình huống thường gặp:

- Developer chạy ứng dụng bằng tài khoản cá nhân, CI chạy bằng user runner.
- Jenkins agent chạy bằng tài khoản service.
- Linux service chạy bằng user riêng như orders.
- Windows service chạy bằng virtual service account hoặc domain service account.
- Container chạy bằng UID/GID được khai báo trong Dockerfile hoặc runtime.
- Kubernetes Pod dùng runAsUser, runAsGroup và fsGroup.
- Scheduled task chạy bằng tài khoản khác với phiên đăng nhập tương tác.

Hãy kiểm tra danh tính ở đúng nơi lỗi xảy ra, không chỉ trên máy mà bạn đang mở terminal.

## 4. Kiểm tra đường dẫn và working directory

Đường dẫn tương đối được tính từ working directory của process. Khi chạy trong IDE, terminal, service hoặc CI, working directory có thể khác nhau.

Ví dụ data/report.txt có thể trỏ đến:

- C:\app\data\report.txt khi process chạy từ C:\app.
- /opt/orders/data/report.txt khi service chạy từ /opt/orders.
- /data/report.txt khi container có working directory là /.

In đường dẫn tuyệt đối để tránh đoán:

```java
import java.nio.file.Path;

Path relative = Path.of("data", "report.txt");
System.out.println("cwd=" + Path.of("").toAbsolutePath());
System.out.println("target=" + relative.toAbsolutePath().normalize());
```

Kiểm tra thêm:

- File hoặc thư mục có tồn tại không?
- Đường dẫn có đúng chữ hoa/thường không?
- Có symbolic link/junction trỏ sang nơi khác không?
- Mọi thư mục cha có thể được traverse không?
- Thư mục có được mount vào container/service không?
- Đường dẫn có trỏ vào ổ đĩa, network share hoặc volume đang ở trạng thái read-only không?

Trên Linux, tên file phân biệt chữ hoa/thường. Trên nhiều cấu hình Windows, tên file không phân biệt theo cách tương tự. Một path đúng trên máy developer có thể trỏ tới file khác hoặc không tồn tại trên hệ thống CI.

Không tự tạo thư mục ở một vị trí bất kỳ để né lỗi. Hãy xác nhận thư mục dữ liệu mà ứng dụng được thiết kế để sử dụng, sau đó cấp quyền tại đúng vị trí đó.

## 5. Quyền file và thư mục trên Linux/Unix

POSIX thường biểu diễn permission bằng ba nhóm:

- u — owner (chủ sở hữu).
- g — group (nhóm).
- o — others (những user còn lại).

Mỗi nhóm có ba quyền:

- r — read.
- w — write.
- x — execute đối với file hoặc search/traverse đối với directory.

Ví dụ:

```text
-rw-r-----  app.properties
drwxr-x---  data/
```

Với file app.properties, owner có thể đọc/ghi, group có thể đọc, others không có quyền. Với thư mục data, owner có thể đọc/ghi/traverse, group có thể đọc/traverse, others không thể truy cập.

Quyền x trên thư mục có nghĩa là được tìm kiếm/traverse qua thư mục đó. Một process có thể có quyền đọc file nhưng vẫn không mở được file nếu thiếu quyền search trên một thư mục cha.

### Quyền cần cho từng thao tác

| Thao tác trên directory | Quyền thường cần |
|---|---|
| Liệt kê tên entry | r |
| Truy cập một entry đã biết tên | x trên directory |
| Tạo file mới | w và x |
| Xóa hoặc đổi tên entry | w và x trên directory liên quan |
| Đi vào thư mục con | x trên từng thư mục cha |

Đối với file, đọc nội dung thường cần r; ghi nội dung thường cần w; thực thi file thường cần x cùng các điều kiện về interpreter và mount.

Để xóa file, quyền write của file không phải yếu tố quyết định chính. Nếu thư mục cha không cho phép write/search, process vẫn không xóa được file dù file có quyền rw.

### Kiểm tra owner, group và mode

Dùng:

```sh
id
ls -ld /var/lib/orders
ls -l /var/lib/orders/report.txt
stat -c '%A %a %U:%G %n' /var/lib/orders /var/lib/orders/report.txt
namei -l /var/lib/orders/report.txt
```

namei -l hiển thị từng thành phần đường dẫn, giúp tìm thư mục cha đang thiếu quyền search. Nếu công cụ này không có sẵn, kiểm tra lần lượt từng thư mục từ root đến file.

Kiểm tra ACL:

```sh
getfacl /var/lib/orders
getfacl /var/lib/orders/report.txt
```

ACL có thể cấp quyền riêng cho user/group ngoài ba nhóm mode cơ bản. ACL mask có thể giới hạn quyền hiệu lực dù một entry hiển thị rwx; hãy đọc cả phần effective trong kết quả getfacl.

### Kiểm tra umask

umask ảnh hưởng permission mặc định khi process tạo file/thư mục mới. Ví dụ umask 027 thường làm file mới có mode tối đa 640 và directory mới có mode tối đa 750, tùy mode được yêu cầu lúc tạo.

Kiểm tra trong shell:

```sh
umask
```

Umask không sửa permission của file đã tồn tại. Nếu file cũ không ghi được, cần kiểm tra owner/group/mode/ACL của file và directory hiện tại.

### Sửa quyền theo nguyên tắc tối thiểu

Nếu service orders cần ghi vào thư mục dữ liệu riêng, administrator có thể tạo thư mục với owner/group/mode phù hợp:

```sh
sudo install -d -o orders -g orders -m 0750 /var/lib/orders
```

Nếu một nhóm cần cùng ghi vào thư mục chia sẻ, có thể dùng group và setgid directory:

```sh
sudo chgrp orders /srv/orders
sudo chmod 2770 /srv/orders
```

Bit 2 (setgid) trên directory giúp file/thư mục mới kế thừa group của thư mục cha trên hệ thống POSIX hỗ trợ hành vi này.

Nếu chỉ cần cấp quyền cho một service user bằng ACL:

```sh
sudo setfacl -m u:orders:rwx /srv/orders
sudo setfacl -d -m u:orders:rwx /srv/orders
```

Lệnh thứ hai đặt default ACL cho entry mới bên dưới thư mục. Kiểm tra lại bằng getfacl; quyền hiệu lực còn phụ thuộc ACL mask và permission của từng thành phần đường dẫn.

Không dùng chmod -R 777 để sửa nhanh. Lệnh đó cấp quyền rộng cho mọi user và có thể làm lộ hoặc cho phép sửa dữ liệu quan trọng. Chỉ cấp quyền cần thiết cho đúng user/group và đúng thư mục.

## 6. Sticky bit, ACL và filesystem đặc biệt

Một số trường hợp có thể gây nhầm lẫn:

- **Sticky bit:** trên thư mục dùng chung như /tmp, user thường chỉ được xóa/đổi tên file thuộc sở hữu của họ hoặc khi có quyền quản trị phù hợp.
- **ACL mask:** giới hạn quyền hiệu lực của các ACL entry nhóm/user được đặt tên.
- **Read-only mount:** mode file có thể cho phép ghi nhưng filesystem mount vẫn từ chối.
- **Filesystem đầy hoặc hết quota:** có thể gây No space left on device hoặc quota error thay vì permission error.
- **NFS/root squash:** UID/GID trên client và server có thể ánh xạ khác nhau; root trong container/client không nhất thiết có quyền trên server.
- **Network filesystem:** quyền có thể phụ thuộc cả ACL server, mount option và identity được gửi qua giao thức.

Kiểm tra mount:

```sh
findmnt -T /var/lib/orders
df -h /var/lib/orders
df -i /var/lib/orders
```

Nếu quyền mode/ACL trông đúng nhưng thao tác vẫn bị từ chối, kiểm tra mount option, quota, network filesystem và policy bảo mật của host.

## 7. Windows ACL, UAC và service account

Windows sử dụng Access Control List (ACL) để quyết định ai được truy cập file/thư mục và với quyền nào. Các quyền thường gặp gồm Read, Write, Modify, Read & Execute và Full Control.

Kiểm tra identity:

```powershell
whoami
whoami /all
```

Kiểm tra ACL của thư mục/file:

```powershell
icacls "C:\AppData\orders"
Get-Acl "C:\AppData\orders" | Format-List
```

icacls hiển thị và quản lý discretionary ACL (DACL). Hãy xem các ACE được áp dụng trực tiếp và các quyền kế thừa từ thư mục cha. Một entry Deny hoặc inheritance khác kỳ vọng có thể làm thao tác bị từ chối dù bạn nhìn thấy một entry Allow.

Nếu administrator xác nhận service account cần quyền Modify trên thư mục dữ liệu và các entry con, có thể cấp quyền theo identity cụ thể:

```powershell
icacls "C:\AppData\orders" /grant "CONTOSO\svc-orders:(OI)(CI)M"
```

Trong ví dụ, thay CONTOSO\svc-orders bằng đúng tài khoản service đã xác minh. M là Modify; OI và CI cho phép quyền kế thừa xuống file và thư mục con. Chỉ áp dụng khi người quản trị hệ thống phê duyệt phạm vi ACL.

### UAC và quyền Administrator

UAC có thể chạy ứng dụng bằng token quyền hạn chế ngay cả khi user thuộc nhóm Administrators. Một cửa sổ terminal được mở bằng Run as administrator có thể có token khác terminal bình thường.

Dịch vụ Windows thường chạy bằng service account riêng. Khi ứng dụng chạy như service, quyền của user đang đăng nhập không tự động được áp dụng cho process service.

Kiểm tra:

- Service đang chạy dưới account nào trong Services hoặc cấu hình service manager.
- Account đó có quyền trên thư mục log, data, temp và file cấu hình không.
- Account có quyền truy cập certificate/private key hoặc secret store không.
- Nếu dùng network share, account có quyền ở cả share ACL và NTFS ACL không.

Mapped drive như Z: được tạo trong phiên đăng nhập tương tác có thể không tồn tại trong session của service. Với network share, dùng UNC path như \\fileserver\orders-data và cấp quyền cho đúng service identity ở cả file server lẫn share.

### Những nguyên nhân Windows khác

Thông báo access denied đôi khi xuất phát từ:

- File đang bị process khác giữ với sharing mode không tương thích.
- File hoặc thư mục có thuộc tính read-only.
- Controlled Folder Access hoặc antivirus chặn thao tác.
- Chính sách Group Policy hoặc endpoint protection.
- Network share permission không khớp NTFS permission.
- Service account không có quyền truy cập certificate/private key.

Kiểm tra event log và security product policy nếu ACL đúng nhưng thao tác vẫn thất bại. Không tắt antivirus hoặc bảo vệ hệ thống để né lỗi; xác định đúng file, process và policy bị chặn.

## 8. Quyền trong Docker và container

Container có filesystem và process identity riêng. Một Java process trong container có thể chạy bằng UID/GID khác user trên host.

Kiểm tra bên trong container:

```sh
docker exec <container-name> id
docker exec <container-name> pwd
docker exec <container-name> ls -ld /var/lib/orders
```

Docker image có thể chọn user mặc định bằng Dockerfile:

```dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
RUN mkdir -p /var/lib/orders \
    && chown 10001:10001 /var/lib/orders

COPY app.jar /app/app.jar
USER 10001:10001

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Trong ví dụ, JVM chạy bằng UID/GID 10001. Thư mục dữ liệu được tạo và sở hữu bởi user đó trước khi chuyển sang user không đặc quyền.

Khi bind mount thư mục từ host:

```sh
docker run --rm \
  --user 10001:10001 \
  --mount type=bind,src=/srv/orders,dst=/var/lib/orders \
  your-java-image
```

Permission của /srv/orders trên host phải cho UID/GID được ánh xạ truy cập. Việc chown thư mục /var/lib/orders trong image không thay đổi owner của thư mục host đang bind mount lên đó.

Kiểm tra thêm:

- Container có chạy bằng USER đúng như dự kiến không?
- Bind mount có được mount read-only (ro) không?
- UID/GID của container có khớp owner/group trên host không?
- Có user namespace remapping hoặc rootless Docker không?
- Host path có được Docker Desktop chia sẻ không?
- Volume có được mount vào đúng container path không?

Root trong container không luôn tương đương root trên host. Docker user namespace/rootless mode có thể ánh xạ UID/GID sang dải ID khác; Docker Desktop còn dùng cơ chế chia sẻ filesystem riêng. Vì vậy, chạy container bằng root không phải cách sửa quyền đáng tin cậy.

## 9. Kubernetes và quyền volume

Trong Kubernetes, quyền truy cập file có thể phụ thuộc security context của Pod/container và loại volume.

Các trường thường gặp:

- runAsUser: UID của process.
- runAsGroup: primary GID của process.
- fsGroup: group được dùng để cấp quyền truy cập volume theo hành vi của volume driver.
- readOnlyRootFilesystem: làm root filesystem của container chỉ đọc.
- allowPrivilegeEscalation: kiểm soát khả năng nâng quyền của process.
- securityContext: cấu hình bảo mật ở Pod hoặc container level.

Ví dụ:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders
spec:
  securityContext:
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: app
      image: example/orders:1.0.0
      securityContext:
        readOnlyRootFilesystem: true
      volumeMounts:
        - name: data
          mountPath: /var/lib/orders
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: orders-data
```

Đây là cấu hình minh họa. Việc fsGroup thay đổi quyền volume hay không còn phụ thuộc loại volume và CSI driver. Kiểm tra quyền thực tế bên trong Pod bằng id, stat, ls -l và thử thao tác với đúng user.

Nếu root filesystem read-only, ứng dụng không thể ghi log/cache vào các thư mục nằm trong image. Hãy mount writable volume hoặc cấu hình log/cache vào đúng vị trí được thiết kế.

## 10. Java API kiểm tra quyền file

java.nio.file.Files cung cấp các API kiểm tra khả năng đọc/ghi/thực thi:

```java
Path path = Path.of("/var/lib/orders/report.txt");

System.out.println("exists=" + Files.exists(path));
System.out.println("readable=" + Files.isReadable(path));
System.out.println("writable=" + Files.isWritable(path));
System.out.println("executable=" + Files.isExecutable(path));
```

Các kết quả này chỉ mang tính chẩn đoán:

- Files.exists() có thể trả false khi file không tồn tại hoặc khi không thể xác định sự tồn tại do thiếu quyền.
- Files.isReadable() và Files.isWritable() có thể trả false nếu file không tồn tại, quyền bị từ chối hoặc provider không xác định được.
- Kết quả kiểm tra có thể lỗi thời ngay sau khi trả về do quyền, file hoặc mount thay đổi.
- Một lần check không bảo đảm lần open/write kế tiếp sẽ thành công.

Đây là dạng lỗi TOCTOU (time-of-check to time-of-use): trạng thái tài nguyên có thể đổi giữa lúc kiểm tra và lúc thao tác. Trong code thực tế, hãy thực hiện thao tác cần thiết và xử lý exception; dùng các API kiểm tra như thông tin hỗ trợ chẩn đoán, không dùng chúng làm bảo đảm bảo mật.

Có thể đọc owner hoặc POSIX permissions nếu filesystem hỗ trợ:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

Path path = Path.of("/var/lib/orders/report.txt");

try {
    Set<PosixFilePermission> permissions =
            Files.getPosixFilePermissions(path);
    System.out.println(
            "posix.permissions="
                    + PosixFilePermissions.toString(permissions));
    System.out.println("owner=" + Files.getOwner(path));
} catch (UnsupportedOperationException e) {
    System.out.println("POSIX attributes are not supported here");
}
```

Không phải filesystem nào cũng hỗ trợ POSIX attribute view. Trên Windows, dùng ACL API hoặc công cụ hệ điều hành để kiểm tra quyền tương ứng.

## 11. Ví dụ Java 17+: kiểm tra quyền mà không ghi đè file đích

Chương trình dưới đây in danh tính và đường dẫn, kiểm tra khả năng mở file để đọc/ghi, sau đó thử tạo rồi xóa một file tạm trong thư mục cha. Nó không ghi nội dung vào file đích.

Tạo file PermissionProbe.java:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Set;

public class PermissionProbe {
    @FunctionalInterface
    interface IoAction {
        void run() throws IOException;
    }

    private static void check(String label, IoAction action) {
        try {
            action.run();
            System.out.println(label + "=OK");
        } catch (AccessDeniedException e) {
            System.err.println(label + "=DENIED");
            System.err.println("file=" + e.getFile());
            System.err.println("reason=" + e.getReason());
        } catch (IOException e) {
            System.err.println(label + "=IO_ERROR "
                    + e.getClass().getSimpleName());
            System.err.println("message=" + e.getMessage());
        } catch (SecurityException e) {
            System.err.println(label + "=SECURITY_EXCEPTION");
            System.err.println("message=" + e.getMessage());
        }
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java PermissionProbe <target-file>");
            System.exit(2);
        }

        Path target = Path.of(args[0]).toAbsolutePath().normalize();
        Path parent = target.getParent();

        System.out.println("user.name="
                + System.getProperty("user.name"));
        System.out.println("user.dir="
                + System.getProperty("user.dir"));
        System.out.println("target=" + target);
        System.out.println("exists=" + Files.exists(target));
        System.out.println("readable=" + Files.isReadable(target));
        System.out.println("writable=" + Files.isWritable(target));

        if (Files.exists(target)) {
            check("read-open", () -> {
                try (InputStream input = Files.newInputStream(target)) {
                    input.readNBytes(1);
                }
            });

            check("write-open", () -> {
                try (SeekableByteChannel channel =
                        Files.newByteChannel(
                                target,
                                Set.of(StandardOpenOption.WRITE))) {
                    // Open only; do not write or truncate the target.
                }
            });
        } else {
            System.out.println("read-open=SKIPPED_TARGET_MISSING");
            System.out.println("write-open=SKIPPED_TARGET_MISSING");
        }

        if (parent != null) {
            check("create-delete-in-parent", () -> {
                Path probe = Files.createTempFile(
                        parent, ".permission-probe-", ".tmp");
                Files.delete(probe);
            });
        } else {
            System.out.println("create-delete-in-parent=SKIPPED");
        }
    }
}
```

Biên dịch:

```sh
javac PermissionProbe.java
```

Chạy với đường dẫn cần chẩn đoán:

Linux/macOS:

```sh
java PermissionProbe /var/lib/orders/report.txt
```

Windows:

```powershell
java PermissionProbe "C:\AppData\orders\report.txt"
```

Output có thể có dạng:

```text
user.name=orders
user.dir=/opt/orders
target=/var/lib/orders/report.txt
exists=true
readable=true
writable=false
read-open=OK
write-open=DENIED
file=/var/lib/orders/report.txt
reason=null
create-delete-in-parent=OK
```

Đây chỉ là output minh họa; tên user, path và reason phụ thuộc môi trường. Nếu write-open=OK nhưng thao tác ghi thật sau đó vẫn fail, kiểm tra file lock, quota, mount, ACL thay đổi hoặc lỗi phát sinh ở bước ghi/flush/close.

Chạy probe có thao tác tạo/xóa file tạm trong thư mục cha. Chỉ chạy tại thư mục mà bạn được phép thử ghi. Nếu policy không cho phép tạo file kiểm tra, bỏ qua bước đó và dùng công cụ hệ điều hành để kiểm tra quyền.

## 12. Thay đổi POSIX permission từ Java

Java NIO có thể đọc hoặc đặt POSIX permissions khi filesystem hỗ trợ và process có quyền thay đổi chúng.

Ví dụ đặt quyền owner read/write cho một file:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

Path path = Path.of("/var/lib/orders/secret.txt");

Files.setPosixFilePermissions(
        path,
        PosixFilePermissions.fromString("rw-------"));
```

Mode rw------- tương đương quyền đọc/ghi cho owner và không cấp quyền cho group/others. Với directory, quyền traverse thường cần x, ví dụ rwx------.

Files.setPosixFilePermissions() có thể ném UnsupportedOperationException nếu filesystem không hỗ trợ POSIX permissions và IOException nếu thao tác thất bại. Process thường phải là owner hoặc có quyền quản trị thích hợp mới thay đổi được permission.

Không dùng code ứng dụng để tự nâng quyền cho file tùy ý. Quyền nên được thiết lập bởi deployment/provisioning hoặc administrator theo chính sách rõ ràng. Ứng dụng chỉ nên thay đổi permission khi đó là một phần được thiết kế và kiểm soát của chức năng.

## 13. Quyền khi chạy process ngoài bằng ProcessBuilder

Java có thể gặp lỗi quyền khi chạy executable/script:

```java
import java.io.IOException;

public class RunTool {
    public static void main(String[] args) {
        ProcessBuilder builder =
                new ProcessBuilder("tools/report-generator", "--version");
        builder.inheritIO();

        try {
            int exitCode = builder.start().waitFor();
            System.out.println("exitCode=" + exitCode);
        } catch (IOException e) {
            System.err.println("Cannot start process: " + e.getMessage());
            e.printStackTrace(System.err);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            System.err.println("Interrupted while waiting for process");
        }
    }
}
```

Trên Linux/Unix, kiểm tra:

- File có execute bit không?
- Các thư mục trên đường dẫn có quyền search không?
- Filesystem có mount với noexec không?
- Shebang có trỏ tới interpreter tồn tại và thực thi được không?
- Process có quyền đọc thư viện/config mà executable cần không?

Kiểm tra bằng:

```sh
ls -l tools/report-generator
namei -l tools/report-generator
findmnt -T tools/report-generator
```

Trên Windows, kiểm tra file thực thi, extension, PATH, AppLocker/WDAC policy và identity của process. Một lỗi CreateProcess có thể liên quan đến executable không tồn tại, path sai hoặc policy chặn, không chỉ ACL file.

Không cấp quyền execute cho toàn bộ thư mục chỉ để chạy một script. Cấp quyền cần thiết cho executable và các thư mục chứa nó.

## 14. Quyền mạng và cổng lắng nghe

Lỗi mạng thường bị nhầm với lỗi file permission. Hãy phân loại theo exception:

| Exception | Hướng kiểm tra |
|---|---|
| UnknownHostException | DNS, hostname, resolver |
| ConnectException | Dịch vụ không lắng nghe, kết nối bị từ chối hoặc route/firewall |
| SocketTimeoutException | Timeout, firewall/egress hoặc dịch vụ phản hồi chậm |
| BindException | Cổng đã được sử dụng, cổng bị hệ điều hành/policy hạn chế hoặc bind address không phù hợp |
| SSLHandshakeException | TLS certificate, trust store, protocol/cipher và thời gian hệ thống |

Trên Linux, bind vào cổng đặc quyền thấp (thường dưới 1024) có thể cần capability CAP_NET_BIND_SERVICE hoặc cấu hình hệ thống cho phép user bind cổng đó. Một lựa chọn thường dùng là cho Java nghe trên cổng cao hơn rồi để reverse proxy/load balancer nhận cổng public.

Kiểm tra cổng:

```sh
ss -ltnp
sudo ss -ltnp
```

Trên Windows:

```powershell
Get-NetTCPConnection -State Listen
netstat -ano
```

Không nhầm Address already in use với permission denied. Nếu lỗi xảy ra khi kết nối ra ngoài, kiểm tra proxy, DNS, firewall, network policy và service account/network namespace. Không mở toàn bộ outbound network nếu chỉ cần cho phép một host/port cụ thể.

## 15. Service account và systemd trên Linux

Service thường nên chạy dưới user riêng với quyền giới hạn. Ví dụ unit systemd:

```ini
[Service]
User=orders
Group=orders
WorkingDirectory=/opt/orders
StateDirectory=orders
ExecStart=/usr/bin/java -jar /opt/orders/app.jar
ProtectSystem=strict
PrivateTmp=true
```

User và Group quyết định identity của process. WorkingDirectory quyết định path tương đối. StateDirectory yêu cầu systemd quản lý thư mục state của service dưới /var/lib với ownership phù hợp. ProtectSystem=strict làm phần lớn filesystem chỉ đọc đối với service, trừ những path được cho phép theo cấu hình systemd.

Nếu service cần ghi vào path khác khi dùng ProtectSystem=strict, administrator có thể khai báo ReadWritePaths= cho đúng thư mục. Không bỏ toàn bộ hardening chỉ để sửa một lỗi ghi file.

Sau khi sửa unit hoặc permission, reload systemd và restart service theo quy trình vận hành; process cũ có thể vẫn chạy với identity, group membership hoặc mount namespace trước đó.

## 16. SELinux, AppArmor và các policy bảo mật của host

Trên Linux, mode bits và ACL đúng vẫn chưa chắc đủ. Mandatory Access Control (MAC) như SELinux hoặc AppArmor có thể chặn thao tác dựa trên security label/profile.

Dấu hiệu:

- ls -l cho thấy permission có vẻ đúng nhưng process vẫn bị từ chối.
- Chỉ service/container bị lỗi, chạy trong shell tương tác lại thành công.
- Log kernel/audit ghi nhận AVC denial hoặc AppArmor DENIED.
- File được đặt ở path có label/profile không cho service truy cập.

Kiểm tra SELinux:

```sh
getenforce
ls -Z /var/lib/orders
sudo ausearch -m AVC -ts recent
```

Kiểm tra AppArmor:

```sh
sudo aa-status
journalctl -k
```

Nếu có denial, administrator cần điều chỉnh label hoặc policy cho đúng service và path. Không tắt SELinux/AppArmor toàn hệ thống như cách khắc phục mặc định.

Trong container, cũng kiểm tra seccomp, Linux capabilities, read-only root filesystem, device cgroup và security profile. Một process có thể có quyền Unix file mode nhưng vẫn bị policy container chặn.

## 17. Java Security Manager và các phiên bản JDK mới

Java Security Manager từng cho phép giới hạn một số thao tác nhạy cảm bằng policy file. Vòng đời của tính năng này đã thay đổi:

- JDK 17: Security Manager và API liên quan được deprecated for removal.
- JDK 24: Security Manager bị vô hiệu hóa vĩnh viễn; không thể bật bằng startup option hoặc cài custom Security Manager theo cơ chế cũ.
- JDK 24 trở lên: policy file kiểu java.policy không còn là cách cấp quyền file/network cho ứng dụng.

Vì vậy, nếu tài liệu cũ yêu cầu thêm grant permission vào java.policy hoặc chạy với -Djava.security.manager, hãy kiểm tra JDK thực tế trước khi áp dụng. Cách đó không giải quyết quyền OS của một service/container và không còn là cơ chế sandbox được hỗ trợ trên JDK mới.

SecurityException vẫn là một loại exception trong Java. Nó có thể xuất phát từ API hoặc thư viện có kiểm tra bảo mật riêng. Đừng đồng nhất mọi SecurityException với Security Manager; đọc stack trace và tài liệu API cụ thể.

Đối với quyền truy cập tài nguyên trong ứng dụng hiện đại, dùng OS identity, file ACL, container isolation, network policy, cloud IAM và authorization logic ở tầng ứng dụng theo đúng loại tài nguyên.

## 18. Phân biệt OS permission với application authorization

Không phải mọi lỗi “forbidden” đều do hệ điều hành.

Ví dụ:

- HTTP 403 Forbidden: server nhận diện request nhưng policy ứng dụng từ chối user/role/tenant.
- Database permission denied: tài khoản DB thiếu SELECT, INSERT, UPDATE hoặc quyền schema.
- Object storage AccessDenied: IAM policy, bucket policy, service principal hoặc KMS key policy.
- Secret manager từ chối: workload identity/role không có quyền đọc secret.
- File system AccessDeniedException: file system provider từ chối thao tác file.
- Network firewall deny: kết nối bị policy mạng chặn.

Kiểm tra identity ở đúng hệ thống đích. User chạy JVM có thể đọc file local nhưng service account của ứng dụng vẫn không có quyền đọc secret hoặc object storage.

Không cấp quyền OS rộng để sửa lỗi role/tenant trong ứng dụng. Hãy sửa policy ở tầng đang thực sự từ chối request.

## 19. CI/CD và deployment

CI thường chạy dưới service identity khác developer. Một số nguyên nhân phổ biến:

- Workspace hoặc artifact directory thuộc owner khác.
- Runner checkout source vào thư mục read-only.
- Build cache được tạo bởi user khác.
- Deployment key/certificate không được cấp cho job.
- Docker bind mount có UID/GID không khớp.
- Secret file có mode/ACL chỉ cho một account.
- Agent chạy với network egress policy khác local.
- Deployment target hoặc mounted volume chỉ đọc.

Trong pipeline, ghi log an toàn về:

- Process user và working directory.
- JDK version, OS và architecture.
- Đường dẫn tuyệt đối của file bị lỗi.
- Mount/volume và trạng thái read-only nếu có.
- Exit code và exception class.
- Tên service identity/role được dùng, không in secret/token.

Chỉ cấp quyền ghi cho build output, cache hoặc deployment staging directory cần thiết. Source code, build script và executable nên giữ quyền đọc phù hợp. Không chạy CI runner bằng root/Administrator chỉ để làm mọi job ghi được vào mọi thư mục.

## 20. Quy trình xử lý lỗi thiếu quyền

Khi gặp lỗi, đi theo thứ tự:

1. Xác định thao tác bị từ chối: read, write, create, delete, execute, bind hay connect.
2. Ghi lại exception class, message, cause, stack trace và file/host/port liên quan.
3. In path tuyệt đối và working directory của JVM.
4. Xác định process user, group, service account hoặc container UID/GID.
5. Kiểm tra owner, mode, ACL và quyền trên mọi thư mục cha.
6. Kiểm tra mount read-only, filesystem quota, file lock và symlink.
7. Kiểm tra MAC policy, container security context hoặc network policy.
8. Thử thao tác bằng đúng identity của service/runner trong cùng môi trường.
9. Cấp quyền tối thiểu cho đúng tài nguyên hoặc sửa identity/configuration.
10. Chạy lại thao tác và kiểm tra log/deployment.
11. Ghi lại quyền mới, owner/group và lý do thay đổi để audit.

Khi thử bằng shell, phải dùng đúng service user. Một lệnh chạy bằng root hoặc Administrator không chứng minh service account có quyền.

## 21. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/khắc phục |
|---|---|---|
| Java đọc được file local nhưng service không đọc được | Service chạy dưới account khác | Kiểm tra service identity và ACL/owner |
| Tạo file mới bị từ chối dù thư mục có thể đọc | Thiếu write hoặc execute/search trên parent directory | Kiểm tra quyền directory và ACL |
| Đọc file bị từ chối dù file có r | Thiếu x trên một thư mục cha hoặc ACL/MAC chặn | Dùng namei -l, getfacl, audit log |
| Xóa file bị từ chối dù file có rw | Thiếu quyền write/search trên thư mục cha, sticky bit hoặc ACL | Kiểm tra parent directory và sticky bit |
| Files.isWritable() trả true nhưng ghi vẫn fail | Trạng thái quyền thay đổi, file lock hoặc mount/policy | Tin kết quả thao tác thực tế và đọc exception |
| Windows chạy từ terminal được nhưng service fail | Service account khác hoặc UAC/session khác | Kiểm tra account của service và DACL |
| Service không truy cập được ổ Z: | Mapped drive không tồn tại trong service session | Dùng UNC path và cấp share/NTFS permission |
| Container không ghi được bind mount | UID/GID không khớp hoặc mount read-only | Kiểm tra id, host owner, mount flags |
| Kubernetes Pod không ghi được volume | runAsUser, fsGroup, CSI driver hoặc read-only mount | Kiểm tra securityContext và quyền thực tế trong Pod |
| Permission đúng nhưng Linux vẫn deny | SELinux/AppArmor, noexec hoặc read-only mount | Kiểm tra audit log, mount options và policy |
| Chạy script bằng ProcessBuilder bị permission denied | Thiếu execute, parent traverse, shebang hoặc mount noexec | Kiểm tra file mode, interpreter và mount |
| Bind cổng bị từ chối | Cổng đặc quyền thấp hoặc capability/network policy | Dùng cổng cao hoặc capability tối thiểu |
| HTTP trả 403 | Application role/tenant policy từ chối | Kiểm tra principal và authorization policy |
| Database báo permission denied | DB user thiếu grant/schema privilege | Kiểm tra quyền tại database |
| Lỗi chỉ xảy ra trong CI | Runner identity, workspace, cache, secret hoặc network khác local | In environment diagnostics và kiểm tra service account |
| Quyền vừa sửa nhưng process vẫn lỗi | Process cũ, group membership/session chưa cập nhật hoặc mount namespace khác | Restart đúng service/job và xác minh lại identity |

## 22. Nguyên tắc bảo mật khi sửa permission

- Chỉ cấp quyền cho user/group/service identity cần thiết.
- Chỉ cấp quyền trên thư mục/file cần dùng.
- Ưu tiên group hoặc ACL cụ thể cho môi trường chia sẻ.
- Không dùng chmod -R 777, Full Control cho Everyone hoặc chạy ứng dụng bằng root để né lỗi.
- Giữ source code, binary và cấu hình nhạy cảm ở trạng thái không thể bị sửa bởi user runtime nếu không cần.
- Tách thư mục dữ liệu, log, cache, temp và secret.
- Dùng read-only mount cho dữ liệu chỉ cần đọc.
- Dùng secret manager/certificate store thay vì ghi credential vào file public.
- Ghi lại thay đổi owner/ACL/capability trong deployment configuration.
- Kiểm thử lại bằng đúng identity của service sau khi thay đổi.

Quyền rộng có thể làm lỗi biến mất nhưng cũng cho phép process bị xâm nhập sửa file thực thi, đọc secret hoặc xóa dữ liệu ngoài phạm vi chức năng. Quyền tối thiểu giúp giới hạn tác động nếu ứng dụng hoặc dependency gặp sự cố.

## 23. Checklist

- [ ] Đã xác định thao tác và tài nguyên bị từ chối.
- [ ] Đã đọc exception class, message, cause và stack trace.
- [ ] Đã xác định process user/group hoặc service identity thực tế.
- [ ] Đã in working directory và absolute path.
- [ ] Đã kiểm tra từng thư mục cha và symbolic link.
- [ ] Đã kiểm tra owner/group/mode và ACL.
- [ ] Đã hiểu quyền read/write/execute/search theo loại thao tác.
- [ ] Đã kiểm tra umask, sticky bit và ACL mask khi dùng POSIX.
- [ ] Đã kiểm tra Windows DACL, UAC, service account và network share.
- [ ] Đã kiểm tra container UID/GID, volume mount và read-only flags.
- [ ] Đã kiểm tra SELinux/AppArmor, noexec và filesystem mount.
- [ ] Đã phân biệt file permission với network/application authorization.
- [ ] Đã thử thao tác bằng đúng identity của process.
- [ ] Đã cấp quyền tối thiểu tại đúng tài nguyên.
- [ ] Đã kiểm tra lại bằng thao tác thực tế sau khi sửa.
- [ ] Đã ghi lại thay đổi quyền để audit.

## 24. Tài liệu tham khảo

- Java SE 25 API — AccessDeniedException: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/AccessDeniedException.html
- Java SE 25 API — Files.isReadable, isWritable và POSIX attributes: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html
- Oracle JDK 27 — The Security Manager Is Permanently Disabled: https://docs.oracle.com/en/java/javase/27/security/security-manager-is-permanently-disabled.html
- Linux man-pages — access(2): https://www.man7.org/linux/man-pages/man2/access.2.html
- Linux man-pages — getfacl(1): https://www.man7.org/linux/man-pages/man1/getfacl.1.html
- Microsoft Learn — icacls: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/icacls
- Docker Docs — Running containers and user identity: https://docs.docker.com/engine/containers/run/
- Docker Docs — Bind mounts: https://docs.docker.com/engine/storage/bind-mounts/
- Docker Docs — UID/GID mapping: https://docs.docker.com/engine/security/rootless/uid-gid-mapping/

Lỗi thiếu quyền cần được xử lý tại đúng lớp đang từ chối thao tác. Xác định identity của JVM, path và exception trước; kiểm tra owner/group/ACL, service account, container mount hoặc policy mạng theo loại tài nguyên; sau đó cấp quyền tối thiểu và kiểm tra lại bằng chính process cần chạy ứng dụng.