# Đọc thuộc tính hệ thống bằng jinfo

`jinfo` là công cụ chẩn đoán đi kèm JDK, dùng để đọc thông tin cấu hình của một Java process đang chạy. Với chủ đề system properties, lệnh quan trọng là `jinfo -sysprops <pid>`: nó yêu cầu JVM đích in các thuộc tính hệ thống dưới dạng cặp tên–giá trị.

System properties ảnh hưởng đến cách ứng dụng Java và các thư viện hoạt động. Chúng có thể chứa thông tin do JDK khởi tạo, giá trị được truyền qua tùy chọn `-Dname=value` khi khởi động hoặc giá trị được ứng dụng đặt bằng `System.setProperty()` trong lúc chạy. Đọc chúng từ process đang hoạt động giúp xác nhận cấu hình mà JVM đang giữ tại thời điểm kiểm tra.

Cần nhớ rằng `jinfo` được Oracle đánh dấu là công cụ experimental và unsupported trong tài liệu JDK 21. Công cụ có thể thay đổi hoặc không còn trong các bản JDK tương lai. Với môi trường JDK hiện đại, `jcmd <pid> VM.system_properties` là lựa chọn thay thế phù hợp để in system properties.

## 1. System property là gì?

System property là một mục trong đối tượng `java.util.Properties` mà JVM cung cấp thông qua `System.getProperties()`. Mỗi property có tên và giá trị dạng chuỗi.

Ví dụ:

```java
String version = System.getProperty("java.version");
String workingDirectory = System.getProperty("user.dir");
String profile = System.getProperty("app.profile");
```

Một số system property tiêu chuẩn thường gặp:

| Property | Ý nghĩa |
|---|---|
| `java.version` | Phiên bản Java runtime |
| `java.vendor` | Nhà cung cấp JDK |
| `java.home` | Thư mục cài đặt/runtime Java |
| `java.class.path` | Classpath của ứng dụng |
| `java.library.path` | Đường dẫn tìm native library |
| `user.dir` | Thư mục làm việc hiện tại của process |
| `user.home` | Thư mục home của tài khoản chạy JVM |
| `user.name` | Tên tài khoản hệ điều hành theo môi trường |
| `os.name` | Tên hệ điều hành |
| `os.arch` | Kiến trúc hệ điều hành |
| `file.encoding` | Charset mặc định được báo bởi runtime |
| `line.separator` | Ký tự xuống dòng theo nền tảng |
| `java.io.tmpdir` | Thư mục tạm |
| `user.timezone` | Time zone property nếu được cấu hình/khởi tạo |

Ứng dụng có thể định nghĩa property riêng, ví dụ `app.profile`, `service.region` hoặc `feature.checkout.enabled`. Các thư viện cũng có thể đọc system properties để chọn hành vi.

Giá trị cụ thể phụ thuộc JDK, hệ điều hành, cách khởi chạy và code của ứng dụng. Không giả định mọi property luôn tồn tại hoặc có cùng giá trị trên mọi môi trường.

## 2. jinfo -sysprops làm gì?

Cú pháp chính:

```sh
jinfo -sysprops <pid>
```

`-sysprops` yêu cầu công cụ in các Java system properties dưới dạng name-value pairs. `<pid>` là process ID của JVM cần kiểm tra.

Ví dụ:

```sh
jinfo -sysprops 24680
```

Output có thể chứa các dòng như:

```text
java.version=21.0.x
java.home=/opt/jdk-21
java.class.path=out
user.dir=/opt/app
app.profile=staging
app.region=ap-southeast-1
```

Đây là output minh họa đã rút gọn; thứ tự và giá trị thật phụ thuộc process. Lệnh thực tế thường in nhiều property hơn ví dụ.

`jinfo` đọc trạng thái của JVM đích tại thời điểm truy vấn. Nếu ứng dụng đã thay đổi một property bằng `System.setProperty()`, giá trị hiện tại có thể được phản ánh trong kết quả. Tuy nhiên, điều đó chỉ cho biết giá trị trong system-properties map; một thư viện đã đọc và cache property từ trước có thể vẫn sử dụng cấu hình cũ.

## 3. Tìm PID của Java process

`jinfo` cần PID của một Java process. Có thể liệt kê JVM bằng:

```sh
jps -l
```

Ví dụ:

```text
24680 com.example.SystemPropertiesDemo
25120 com.example.OrderService
```

Sau khi xác định process, dùng PID tương ứng:

```sh
jinfo -sysprops 24680
```

Nếu `jps` không hiển thị process, có thể dùng công cụ hệ điều hành.

Linux/macOS:

```sh
ps -ef
```

Windows PowerShell:

```powershell
Get-Process java, javaw -ErrorAction SilentlyContinue
```

Trong container, PID nhìn từ host có thể khác PID bên trong container. Chạy công cụ trong đúng container/PID namespace hoặc xác định PID theo namespace mà công cụ có thể truy cập. `jps` có thể không liệt kê JVM nằm trong Docker process tách biệt.

Không chọn PID chỉ vì nó xuất hiện đầu tiên. Hãy đối chiếu tên main class/JAR, command line hoặc thông tin service để tránh đọc nhầm ứng dụng.

## 4. Điều kiện attach đến JVM đích

`jinfo` cần kết nối tới JVM đang chạy để đọc dữ liệu. Trong vận hành thông thường:

- Chạy trên cùng máy với JVM đích.
- Dùng tài khoản hệ điều hành có quyền attach phù hợp; thông thường nên dùng cùng user đã khởi chạy JVM.
- Xác định PID còn tồn tại và thuộc đúng process Java.
- Dùng JDK/tool tương thích với runtime đích.
- Kiểm tra attach mechanism không bị tắt hoặc chặn bởi policy, container hay hệ điều hành.
- Với container, dùng đúng PID namespace và quyền truy cập process.

Trên một số cấu hình Windows, tài liệu `jinfo` lưu ý rằng nếu thiếu `dbgeng.dll`, cần cài Debugging Tools for Windows; biến môi trường `PATH` phải chứa vị trí `jvm.dll` tương ứng với target process. Đây là yêu cầu theo môi trường, không phải bước bắt buộc trên mọi máy Windows.

Nếu attach thất bại, kiểm tra process, user, JDK, namespace và thông báo lỗi trước khi kết luận property không tồn tại. Lỗi attach là vấn đề kết nối tới process; nó không chứng minh nội dung system properties bị sai.

## 5. Phân biệt -sysprops, -flags và không có tùy chọn

`jinfo` có thể hiển thị cả system properties và JVM command-line flags.

| Lệnh | Nội dung |
|---|---|
| `jinfo -sysprops <pid>` | Chỉ in Java system properties |
| `jinfo -flags <pid>` | In các JVM flags được truyền khi khởi chạy |
| `jinfo <pid>` | In cả JVM flags và system properties |
| `jinfo -flag <name> <pid>` | In giá trị của một JVM flag cụ thể |
| `jinfo -help` | In trợ giúp |

Ví dụ:

```sh
jinfo 24680
```

Khi không có tùy chọn, tài liệu JDK 21 xác nhận công cụ in cả command-line flags và system property name-value pairs. Output vì vậy có thể dài hơn nhiều so với `-sysprops`.

Không nhầm các nhóm sau:

| Ví dụ | Loại |
|---|---|
| `-Dapp.profile=staging` | System property được đặt từ Java launcher |
| `app.profile=staging` trong output `-sysprops` | Giá trị system property hiện tại |
| `-Xmx2g` | JVM flag, không phải system property |
| `-XX:+UseG1GC` | JVM flag |
| `-XX:MaxRAMPercentage=75` | JVM flag |
| `java.version` | System property tiêu chuẩn |

`-flags` và `-flag` làm việc với JVM flags. Chúng không phải cách đọc hoặc cập nhật system properties.

## 6. Phân biệt system property và environment variable

System property và environment variable là hai nguồn cấu hình khác nhau.

| Nội dung | System property | Environment variable |
|---|---|---|
| API đọc | `System.getProperty(name)` | `System.getenv(name)` |
| Truyền lúc khởi chạy | `-Dname=value` | Thiết lập trong shell/service/container |
| Thay đổi trong Java | `System.setProperty(name, value)` | Không có API Java chuẩn để sửa environment của process |
| Công cụ kiểm tra | `jinfo -sysprops` hoặc `jcmd PID VM.system_properties` | Công cụ hệ điều hành/container |
| Phạm vi | JVM process | Môi trường process được kế thừa |

Ví dụ:

```java
String profile = System.getProperty("app.profile");
String region = System.getenv("APP_REGION");
```

Nếu chỉ đặt environment variable `APP_REGION`, không nên mong đợi nó tự xuất hiện trong `jinfo -sysprops`. Ứng dụng phải đọc environment variable rồi, nếu cần, tự chuyển giá trị thành system property.

Tương tự, `System.setProperty("app.profile", "staging")` không tạo hoặc sửa environment variable của hệ điều hành.

## 7. System properties được tạo và thay đổi như thế nào?

Có ba nguồn thường gặp.

### 7.1. Property do JVM khởi tạo

JDK cung cấp các property tiêu chuẩn như `java.version`, `java.home`, `os.name` và `user.dir`. Giá trị được xác định từ runtime, launcher và môi trường hệ điều hành.

### 7.2. Property truyền bằng -D

Đặt property khi khởi động:

```sh
java -Dapp.profile=staging -Dapp.region=ap-southeast-1 -cp out com.example.OrderService
```

Java launcher đưa các cặp name-value này vào system properties của JVM. Chúng có thể được đọc trong ứng dụng bằng:

```java
String profile = System.getProperty("app.profile");
String region = System.getProperty("app.region");
```

Sau khi process chạy, có thể kiểm tra:

```sh
jinfo -sysprops <pid>
```

Tìm các dòng `app.profile` và `app.region`.

### 7.3. Property được đặt trong code

Ứng dụng có thể đặt hoặc thay đổi property lúc chạy:

```java
System.setProperty("app.runtime.mode", "diagnostic");
```

Đọc lại:

```java
String mode = System.getProperty("app.runtime.mode");
```

Xóa một property:

```java
System.clearProperty("app.runtime.mode");
```

Các thay đổi này tác động đến system-properties map trong JVM hiện tại. Chúng không tự ghi vào command line, file cấu hình hoặc environment variable.

## 8. Ví dụ Java 17+: quan sát property lúc chạy bằng jinfo

Ví dụ sau tạo một JVM chạy liên tục, đặt một property lúc khởi động và một property sau khi chương trình bắt đầu. Nhờ đó có thể kiểm tra cả hai bằng `jinfo`.

Tạo file `SystemPropertiesDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class SystemPropertiesDemo {
    public static void main(String[] args) throws InterruptedException {
        System.setProperty("app.runtime.mode", "diagnostic");

        System.out.println(
            "PID=" + ProcessHandle.current().pid());
        System.out.println(
            "launch.profile=" + System.getProperty("launch.profile"));
        System.out.println(
            "runtime.mode=" + System.getProperty("app.runtime.mode"));

        new CountDownLatch(1).await();
    }
}
```

Biên dịch:

```sh
javac SystemPropertiesDemo.java
```

Chạy với một system property từ launcher:

```sh
java -Dlaunch.profile=staging SystemPropertiesDemo
```

Output chương trình:

```text
PID=24680
launch.profile=staging
runtime.mode=diagnostic
```

`24680` là PID minh họa; giá trị thực tế do `ProcessHandle.current().pid()` trả về. Chương trình chờ vô hạn để process còn tồn tại khi mở terminal thứ hai.

Tại terminal thứ hai, chạy:

```sh
jinfo -sysprops 24680
```

Tìm các dòng:

```text
launch.profile=staging
app.runtime.mode=diagnostic
```

Output `jinfo` đầy đủ có thêm nhiều property của JDK và môi trường. Sau khi kiểm tra, quay lại terminal đầu và nhấn Ctrl+C để dừng chương trình demo.

Ví dụ cho thấy property truyền qua `-D` và property đặt bằng `System.setProperty()` đều thuộc system-properties map mà ứng dụng đang giữ.

## 9. Đọc property cụ thể trong ứng dụng

`jinfo -sysprops` in toàn bộ danh sách, nên kết quả có thể dài. Nếu chỉ cần một property, có thể lọc output bằng công cụ shell.

Linux/macOS:

```sh
jinfo -sysprops 24680 | grep '^app.profile='
```

Windows PowerShell:

```powershell
jinfo -sysprops 24680 | Select-String '^app.profile='
```

Ví dụ tìm nhiều property:

```sh
jinfo -sysprops 24680 | grep -E '^(app.profile|app.region|user.dir)='
```

Lọc output giúp đọc nhanh nhưng không thay đổi nội dung trong JVM. Nếu property không xuất hiện, có thể key chưa được đặt, đã bị xóa, tên key sai hoặc phiên bản/tool không trả về như mong đợi. Xác minh trong chính ứng dụng bằng `System.getProperty()` khi cần.

Trên Windows, `Select-String` là lệnh PowerShell; cú pháp `grep` thường dùng trong Linux/macOS hoặc môi trường có GNU tools.

## 10. jinfo chỉ đọc system properties, không cấu hình lại ứng dụng

`jinfo -sysprops` là lệnh đọc. Nó không cung cấp tùy chọn để sửa system property trong JVM đang chạy.

Nếu cần thay đổi property trong ứng dụng, phải dùng cơ chế cấu hình mà ứng dụng hỗ trợ, ví dụ:

- Đặt `-Dname=value` trước khi JVM khởi động.
- Đọc file cấu hình hoặc configuration service.
- Gọi `System.setProperty()` từ code được kiểm soát.
- Dùng API quản trị riêng của ứng dụng nếu có.

Lưu ý `jinfo -flag` có thể bật/tắt hoặc đặt giá trị cho một số JVM flag. Đó là thao tác khác với system property. Ví dụ `jinfo -flag +PrintGC <pid>` tác động đến VM flag nếu JVM hỗ trợ flag đó; nó không tạo property `PrintGC`.

Không dùng nhầm cú pháp `-flag` để cố sửa một dòng trong kết quả `-sysprops`. Hai loại cấu hình có API và quy tắc riêng.

## 11. Giá trị system property có thể khác cấu hình hiệu lực của thư viện

Đọc được property không có nghĩa mọi thành phần trong JVM đang sử dụng giá trị mới nhất của nó.

Ví dụ:

- Ứng dụng đặt `System.setProperty("app.profile", "production")`; code đọc property sau đó thấy giá trị mới.
- Một thư viện đã đọc `app.profile` lúc khởi tạo và lưu vào field; nó có thể tiếp tục dùng giá trị cũ.
- Một API JDK có thể cache default charset, timezone hoặc cấu hình khi lớp/đối tượng được khởi tạo.
- Một framework có thể chỉ đọc system property ở startup rồi xây dựng configuration object riêng.

Vì vậy, khi debug:

1. Dùng `jinfo -sysprops` để xem giá trị trong system-properties map.
2. Xác định thành phần nào đọc property đó và đọc vào thời điểm nào.
3. Kiểm tra component có cache giá trị hay không.
4. Kiểm tra log/configuration endpoint của ứng dụng để xem giá trị thực tế mà component sử dụng.
5. Nếu property chỉ được đọc lúc startup, thay đổi nó thường yêu cầu khởi động lại hoặc reload theo cơ chế chính thức của framework.

Không kết luận cấu hình của toàn ứng dụng đã thay đổi chỉ từ một dòng `jinfo`.

## 12. System properties, security properties và JVM flags

Ba nhóm này có tên và công cụ kiểm tra khác nhau:

| Nhóm | Ví dụ | Cách đọc |
|---|---|---|
| System properties | `java.version`, `user.dir`, `app.profile` | `System.getProperty()`, `jinfo -sysprops` |
| Security properties | `keystore.type`, `jdk.tls.disabledAlgorithms` | `Security.getProperty()` |
| JVM flags | `-Xmx2g`, `-XX:+UseG1GC` | `jinfo -flags`, `jinfo -flag`, `jcmd PID VM.flags` |

Security property được quản lý bởi `java.security.Security` và cấu hình trong `java.security`. Chúng không tự động trở thành system properties và không phải nội dung mà `jinfo -sysprops` chuyên in.

JVM flags điều khiển VM, ví dụ heap, GC hoặc compiler. Chúng không phải cặp name-value trong system-properties map.

Nếu cần kiểm tra cả ba nhóm, dùng công cụ phù hợp cho từng nhóm thay vì dựa vào một lệnh duy nhất.

## 13. Thay thế bằng jcmd VM.system_properties

Oracle JDK 21 cung cấp diagnostic command `VM.system_properties` thông qua `jcmd`:

```sh
jcmd 24680 VM.system_properties
```

Lệnh này in system properties của JVM được chỉ định. Đây là lựa chọn phù hợp cho quy trình chẩn đoán dựa trên `jcmd`.

Một số command liên quan:

| Lệnh | Mục đích |
|---|---|
| `jcmd -l` | Liệt kê JVM process có thể quan sát |
| `jcmd <pid> help` | Liệt kê diagnostic command mà JVM hỗ trợ |
| `jcmd <pid> VM.system_properties` | In system properties |
| `jcmd <pid> VM.flags` | In JVM flags hiện tại |
| `jcmd <pid> VM.command_line` | In command line dùng để khởi chạy JVM |

Ví dụ:

```sh
jcmd 24680 VM.system_properties
jcmd 24680 VM.flags
jcmd 24680 VM.command_line
```

Trước khi dùng một diagnostic command, có thể hỏi JVM mục tiêu:

```sh
jcmd 24680 help VM.system_properties
```

`jcmd` phải chạy trên cùng máy với JVM và dùng effective user/group ID phù hợp với tài khoản đã khởi chạy JVM. Theo tài liệu JDK 21, `VM.system_properties` có impact Low.

Nếu đang xây dựng quy trình vận hành mới, ưu tiên command được tài liệu `jcmd` hỗ trợ thay cho `jinfo` vì `jinfo` được đánh dấu experimental và unsupported.

## 14. Lưu ý bảo mật khi đọc system properties

System properties có thể chứa thông tin nhạy cảm hoặc thông tin nội bộ:

- Đường dẫn triển khai, thư mục người dùng và classpath.
- Tên dịch vụ, profile, region, hostname hoặc endpoint.
- Token, password hoặc credential nếu ứng dụng truyền chúng qua `-D`.
- Đường dẫn truststore/keystore và đôi khi cả password nếu cấu hình sai.
- Tên package, thư viện và cấu trúc nội bộ của ứng dụng.

Không truyền secret trực tiếp bằng:

```sh
java -Ddb.password=secret -Dapi.token=secret ...
```

Các giá trị này có thể xuất hiện trong system-properties dump, command line, process inspection hoặc log chẩn đoán. Dùng secret manager, credential provider hoặc cơ chế cấp secret được bảo vệ.

Khi chia sẻ output `jinfo`/`jcmd`:

1. Chỉ thu thập các property thực sự cần.
2. Che password, token, key và thông tin định danh nhạy cảm.
3. Lưu file trong thư mục có quyền truy cập hạn chế.
4. Không đính kèm dump đầy đủ vào issue công khai.
5. Xóa bản sao tạm theo chính sách lưu trữ sau khi điều tra.

## 15. Lỗi thường gặp khi dùng jinfo -sysprops

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jinfo: command not found` | Chưa cài JDK hoặc `JAVA_HOME/bin` chưa nằm trong PATH | Dùng đúng JDK và kiểm tra `where jinfo`/`which jinfo` |
| `Could not find process` | PID sai, process đã dừng hoặc PID namespace khác | Dùng `jps -l`/`ps` để xác định lại |
| Attach bị từ chối | Khác user, quyền hệ điều hành hoặc attach mechanism bị chặn | Kiểm tra tài khoản, quyền và cấu hình runtime |
| Không thấy JVM trong `jps` | JVM nằm trong container riêng hoặc công cụ không có quyền quan sát | Tìm PID trong đúng namespace bằng công cụ hệ điều hành |
| Không có property mong đợi | Key chưa được đặt, sai tên hoặc đã bị xóa | Kiểm tra tên key và `System.getProperty()` trong ứng dụng |
| Giá trị trong dump khác log ứng dụng | Component đã cache giá trị hoặc dùng nguồn cấu hình khác | Kiểm tra thời điểm đọc property và configuration object |
| Dùng `-flag` nhưng không thấy system property | `-flag` thao tác JVM flag, không thao tác system property | Dùng `-sysprops` để đọc property |
| Output quá dài | JVM có nhiều property tiêu chuẩn và property tùy chỉnh | Lọc theo key cần tìm hoặc dùng công cụ phân tích phù hợp |
| Windows báo thiếu `dbgeng.dll` | Thiếu Debugging Tools for Windows trong môi trường cần thiết | Cài công cụ debug phù hợp và kiểm tra PATH/`jvm.dll` |
| Công cụ không có ở JDK mới | `jinfo` là experimental/unsupported và có thể bị thay đổi hoặc loại bỏ | Dùng `jcmd PID VM.system_properties` nếu JVM hỗ trợ |

Khi lỗi xảy ra, kiểm tra đúng PID, quyền attach và tool version trước. Nếu attach thành công nhưng key không xuất hiện, điều tra cách ứng dụng đặt property và thời điểm thành phần đọc nó.

## 16. Quy trình kiểm tra system properties trong vận hành

1. Xác định ứng dụng và PID bằng `jps -l` hoặc công cụ process của hệ điều hành.
2. Xác nhận đang thao tác trong đúng host/container và có quyền attach.
3. Chạy `jinfo -sysprops <pid>` nếu môi trường còn hỗ trợ `jinfo`.
4. Tìm property liên quan đến sự cố.
5. Phân biệt property được đặt bằng `-D`, property mặc định của JDK và property được thay đổi lúc runtime.
6. Đối chiếu với environment variable, file cấu hình và log ứng dụng khi cần.
7. Kiểm tra thành phần có cache giá trị hay không.
8. Dùng `jcmd <pid> VM.system_properties` nếu cần công cụ thay thế.
9. Che thông tin nhạy cảm trước khi lưu hoặc chia sẻ output.
10. Ghi lại JDK version, PID, thời điểm và command đã dùng để có thể tái lập.

Không chỉnh sửa cấu hình ứng dụng chỉ dựa trên một property đơn lẻ. Xác định component đọc property, quy tắc ưu tiên cấu hình và thời điểm áp dụng trước khi thay đổi môi trường.

## 17. Checklist

- [ ] Đã xác định đúng JVM PID.
- [ ] Đã xác nhận quyền attach và môi trường/container.
- [ ] Đã dùng `jinfo -sysprops <pid>` để đọc system properties.
- [ ] Đã phân biệt system properties với JVM flags và security properties.
- [ ] Đã hiểu property mặc định, property truyền bằng `-D` và property đặt bằng code.
- [ ] Đã phân biệt system property với environment variable.
- [ ] Đã xác định property có bị component cache hay không.
- [ ] Đã dùng `jcmd <pid> VM.system_properties` khi cần công cụ thay thế.
- [ ] Đã không dùng `-flag` để sửa system property.
- [ ] Đã che password/token và thông tin nhạy cảm trong output.
- [ ] Đã ghi lại JDK version, PID và thời điểm kiểm tra.

## 18. Tài liệu tham khảo

- Oracle JDK 21 Tool Reference — The `jinfo` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jinfo.html
- Oracle JDK 21 Tool Reference — The `jcmd` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Java SE 21 API — `java.lang.System`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html
- Java SE 21 API — `java.util.Properties`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html

`jinfo -sysprops` giúp đọc các thuộc tính hệ thống mà một JVM đang giữ tại thời điểm truy vấn. Hãy dùng đúng PID, phân biệt system properties với JVM flags và environment variables, kiểm tra tác động của cache trong thư viện, đồng thời cân nhắc `jcmd PID VM.system_properties` cho quy trình chẩn đoán hiện đại.