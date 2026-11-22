# Xem system property của JVM bằng jcmd

`jcmd <pid> VM.system_properties` là diagnostic command của JDK dùng để in các system property hiện tại của một Java Virtual Machine (JVM) đang chạy. Lệnh hữu ích khi cần kiểm tra cấu hình thực tế của tiến trình mà không phải dừng ứng dụng hoặc chỉ dựa vào cấu hình lúc build.

System property có thể được truyền lúc khởi động bằng tùy chọn `-Dkey=value`, được đặt trong mã bằng `System.setProperty`, hoặc được thư viện/framework thêm vào trong quá trình chạy. `VM.system_properties` hiển thị các giá trị hiện tại mà JVM đang giữ, gồm cả property do ứng dụng tự tạo.

Lệnh này **chỉ đọc và in property**. Nó không thêm, sửa hoặc xóa system property. Muốn thay đổi giá trị sau khi JVM đã khởi động, ứng dụng cần tự hỗ trợ cơ chế cấu hình runtime, chẳng hạn gọi `System.setProperty` hoặc cung cấp API quản trị an toàn.

## 1. System property là gì?

System property là cặp key/value dạng chuỗi được lưu trong đối tượng `java.util.Properties` của JVM. Ứng dụng Java có thể đọc chúng bằng `System.getProperty` hoặc lấy toàn bộ tập property bằng `System.getProperties`.

Một số property tiêu chuẩn thường gặp:

| Property | Ý nghĩa |
|---|---|
| `java.version` | Phiên bản Java runtime |
| `java.home` | Thư mục cài đặt runtime |
| `java.class.path` | Classpath của ứng dụng |
| `os.name` | Tên hệ điều hành |
| `os.arch` | Kiến trúc hệ điều hành |
| `user.dir` | Thư mục làm việc hiện tại |
| `user.home` | Thư mục home của user |
| `file.encoding` | Charset mặc định được runtime báo cáo |
| `java.io.tmpdir` | Thư mục tạm |
| `path.separator` | Ký tự phân tách path theo hệ điều hành |

Ứng dụng cũng có thể định nghĩa property riêng, thường đặt tên theo namespace của ứng dụng, ví dụ `app.profile`, `app.region` hoặc `service.endpoint`. Dùng tiền tố riêng giúp tránh xung đột với property tiêu chuẩn hoặc thư viện khác.

System property khác với environment variable. Environment variable được hệ điều hành cung cấp cho tiến trình và đọc trong Java bằng `System.getenv`; chúng không tự động trở thành system property. Chỉ những giá trị được ứng dụng sao chép hoặc đặt vào `System.getProperties()` mới xuất hiện trong báo cáo `VM.system_properties`.

## 2. Cú pháp jcmd và cách chọn JVM đích

Cú pháp tổng quát:

~~~sh
jcmd <pid> <command> [arguments]
~~~

Trong đó `jcmd` là công cụ chẩn đoán đi kèm JDK, `<pid>` là process ID của JVM cần kiểm tra, và `<command>` là diagnostic command mà JVM đích hỗ trợ.

Liệt kê JVM đang chạy trên máy:

~~~sh
jcmd -l
~~~

Kết quả minh họa:

~~~text
36008 PropertyProbe
51276 com.example.Server
~~~

PID và tên main class phụ thuộc máy đang chạy. Dùng PID cụ thể để tránh gửi lệnh tới nhầm tiến trình. Có thể dùng tên main class thay PID, nhưng nếu có nhiều JVM cùng chạy class đó, lệnh có thể được gửi tới tất cả tiến trình khớp tên.

Xem danh sách command mà JVM đích hỗ trợ:

~~~sh
jcmd 36008 help
~~~

Xem cú pháp và mô tả riêng của command:

~~~sh
jcmd 36008 help VM.system_properties
~~~

Các diagnostic command có thể khác nhau tùy JVM, JDK và phiên bản. Luôn dùng `help` trên chính tiến trình đích trước khi giả định một command có sẵn.

Không dùng PID `0` nếu chỉ muốn kiểm tra một ứng dụng: PID 0 yêu cầu `jcmd` gửi command tới tất cả Java process mà công cụ có thể tiếp cận.

## 3. In system property bằng VM.system_properties

Lệnh chính:

~~~sh
jcmd 36008 VM.system_properties
~~~

Kết quả có thể chứa hàng trăm property. Ví dụ rút gọn:

~~~text
#Tue Nov 10 18:52:44 GMT+07:00 2026
app.mode=diagnostic
app.profile=qa
app.region=test-lab
file.encoding=UTF-8
java.class.version=68.0
java.runtime.version=24.0.2+12
java.specification.version=24
os.arch=amd64
os.name=Windows 11
user.dir=H\:\\projects\\sample
~~~

Đây là ví dụ rút gọn; ngày giờ, phiên bản Java, đường dẫn và property phụ thuộc tiến trình thực tế. Dòng đầu có thể là timestamp của báo cáo. Các giá trị có dấu gạch chéo ngược hoặc dấu phân tách đặc biệt có thể được escape theo định dạng tương tự Java properties.

`VM.system_properties` đọc tập system property trong JVM được chọn. Nếu ứng dụng gọi `System.setProperty("app.mode", "diagnostic")` trước lúc kiểm tra, property đó sẽ xuất hiện trong báo cáo. Giá trị do startup option `-Dapp.profile=qa` cũng xuất hiện.

Nếu cần lưu toàn bộ báo cáo để phân tích:

~~~sh
jcmd 36008 VM.system_properties > vm-properties.txt
~~~

Trên PowerShell:

~~~powershell
jcmd 36008 VM.system_properties | Out-File -Encoding utf8 vm-properties.txt
~~~

Có thể lọc riêng nhóm property ứng dụng để đọc nhanh:

~~~sh
jcmd 36008 VM.system_properties | grep '^app\.'
~~~

PowerShell:

~~~powershell
jcmd 36008 VM.system_properties | Select-String '^app\.'
~~~

Lọc output chỉ giúp hiển thị ít dòng hơn; JVM vẫn trả về toàn bộ tập property cho command. Hãy bảo vệ file output như dữ liệu cấu hình nội bộ.

## 4. Ví dụ hoàn chỉnh: tạo JVM có property để kiểm tra

Tạo file `PropertyProbe.java`:

~~~java
public class PropertyProbe {
    public static void main(String[] args) throws InterruptedException {
        System.setProperty("app.mode", "diagnostic");
        System.setProperty("app.region", "test-lab");

        System.out.println("probe-ready");
        Thread.sleep(120_000);
    }
}
~~~

Chương trình đặt hai property trong runtime rồi giữ JVM chạy trong hai phút để có thời gian kiểm tra từ terminal khác. `Thread.sleep` chỉ giữ tiến trình sống cho bài thực hành; ứng dụng production thường có vòng đời riêng.

Biên dịch:

~~~sh
mkdir -p out
javac -d out PropertyProbe.java
~~~

Khởi chạy với một property được truyền từ command line:

~~~sh
java -Dapp.profile=qa -cp out PropertyProbe
~~~

Kết quả stdout của chương trình:

~~~text
probe-ready
~~~

Mở terminal thứ hai và liệt kê JVM:

~~~sh
jcmd -l
~~~

Tìm dòng `PropertyProbe` để lấy PID, sau đó thay PID vào lệnh:

~~~sh
jcmd <pid> VM.system_properties
~~~

Trong output, tìm ba property:

~~~text
app.mode=diagnostic
app.profile=qa
app.region=test-lab
~~~

`app.profile` đến từ `-Dapp.profile=qa` lúc khởi động. `app.mode` và `app.region` được đặt trong ứng dụng bằng `System.setProperty`. Ví dụ này cho thấy `VM.system_properties` phản ánh property hiện có trong JVM, không chỉ những giá trị được truyền lúc khởi động.

Khi kiểm tra xong, quay lại terminal đang chạy `PropertyProbe` và nhấn `Ctrl+C` để kết thúc chương trình.

## 5. Phân biệt system properties, VM flags và command line

`jcmd` có các command khác nhau cho những loại thông tin khác nhau:

| Command | Nội dung |
|---|---|
| `VM.system_properties` | Các system property hiện tại của JVM |
| `VM.command_line` | Command line và VM arguments dùng để khởi chạy tiến trình |
| `VM.flags` | Các JVM flag cùng giá trị hiện tại |
| `VM.version` | Thông tin phiên bản JVM |
| `VM.uptime` | Thời gian JVM đã chạy |

Ví dụ:

~~~sh
jcmd 36008 VM.system_properties
jcmd 36008 VM.command_line
jcmd 36008 VM.flags
~~~

Các điểm cần phân biệt:

- `-Dname=value` tạo system property.
- `-Xmx` và `-XX:...` là JVM options/flags, không phải system property thông thường.
- `VM.system_properties` hiển thị property.
- `VM.flags` hiển thị cờ cấu hình VM.
- `VM.command_line` cho biết các đối số khởi động; nó không phải báo cáo đầy đủ trạng thái property hiện tại.

Không nhầm `VM.set_flag` với thao tác đặt system property. `VM.set_flag` dùng cho một số JVM flag có thể thay đổi khi chạy; nó không cung cấp một lệnh tổng quát để đặt giá trị `System.getProperty`.

## 6. Thay đổi system property sau khi JVM đã chạy

`VM.system_properties` là command đọc. Không có tham số để truyền một key/value mới vào command này.

Ứng dụng có thể thay đổi property trong chính tiến trình bằng API Java:

~~~java
System.setProperty("app.mode", "maintenance");
String mode = System.getProperty("app.mode");
System.out.println(mode);
~~~

Kết quả:

~~~text
maintenance
~~~

Nếu đoạn code này chạy trong JVM đang được kiểm tra, lần gọi `jcmd <pid> VM.system_properties` tiếp theo sẽ hiển thị `app.mode=maintenance`.

Nếu muốn đổi cấu hình runtime từ bên ngoài, ứng dụng cần chủ động cung cấp một cơ chế được kiểm soát, ví dụ JMX MBean, endpoint quản trị có xác thực hoặc cơ chế reload cấu hình. `jcmd` không tự tạo endpoint thay đổi property và không biến command in property thành command setter.

Lưu ý: thay đổi property không đảm bảo mọi thư viện sẽ lập tức áp dụng giá trị mới. Một framework có thể đã đọc và cache property khi khởi tạo. Hãy xem tài liệu thành phần liên quan để biết có cần reload, restart hoặc gọi API cấu hình riêng hay không.

## 7. Quyền truy cập và điều kiện attach

`jcmd` gửi diagnostic request tới JVM qua cơ chế attach cục bộ. Theo tài liệu JDK, công cụ phải chạy trên cùng máy với JVM đích và cùng effective user/group đã khởi chạy JVM đó.

Một số điều kiện có thể ảnh hưởng:

- JVM đích đã thoát hoặc PID không còn tồn tại.
- Dùng sai PID hoặc PID thuộc tiến trình không phải Java.
- Người dùng hiện tại không có quyền attach vào tiến trình đích.
- JVM được khởi chạy với `-XX:+DisableAttachMechanism`.
- Tiến trình chạy trong container hoặc PID namespace khác, khiến PID nhìn từ host không trùng PID trong container.
- JVM đích không hỗ trợ diagnostic command được yêu cầu.

Trong môi trường container, hãy xác định PID trong đúng namespace và chạy công cụ từ môi trường có thể attach vào JVM đó. `jcmd -l` không nhất thiết liệt kê các JVM nằm trong Docker process riêng; có thể cần tra PID bằng công cụ của hệ điều hành hoặc thực hiện lệnh bên trong container.

Dùng JDK tương ứng với JVM đích khi có thể. Sau khi attach, chạy `jcmd <pid> help` để xác nhận danh sách command khả dụng.

## 8. Bảo mật khi đọc system properties

System property không mặc nhiên là dữ liệu công khai. Báo cáo có thể chứa:

- Đường dẫn thư mục home, thư mục làm việc, thư mục tạm và thư viện.
- Tên tài khoản hoặc thông tin môi trường.
- URL nội bộ, endpoint, tên database hoặc cấu hình dịch vụ.
- Property tùy chỉnh mà ứng dụng vô tình dùng để lưu token, password hoặc secret.

Không nên truyền secret qua `-Dpassword=...` hoặc lưu credential trong system property. Property có thể bị lộ qua command line, diagnostic output, log hoặc công cụ giám sát. Dùng secret manager hoặc cơ chế credential phù hợp.

Khi chia sẻ output để điều tra:

1. Chỉ lấy những property cần thiết, ví dụ lọc tiền tố `app.`.
2. Che token, password, URL có credential và thông tin nhận dạng nội bộ.
3. Không đưa toàn bộ `VM.system_properties` vào ticket công khai hoặc repository.
4. Giới hạn quyền đọc diagnostic interface và file output.
5. Xóa file tạm theo chính sách lưu trữ của tổ chức sau khi hoàn tất điều tra.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jcmd: command not found` | Chưa cài JDK hoặc PATH thiếu JDK bin | Kiểm tra `JAVA_HOME` và PATH |
| Không thấy JVM trong `jcmd -l` | Sai user, JVM nằm trong container riêng hoặc process đã dừng | Kiểm tra PID bằng công cụ hệ điều hành trong đúng môi trường |
| `AttachNotSupportedException` hoặc không attach được | Attach bị vô hiệu hóa, quyền không phù hợp hoặc JVM không hỗ trợ | Dùng cùng user, kiểm tra `-XX:+DisableAttachMechanism` và log lỗi |
| `Unknown diagnostic command` | Command không được JVM đích hỗ trợ hoặc gõ sai tên | Chạy `jcmd <pid> help` |
| Không thấy custom property | Ứng dụng chưa đặt property, dùng nhầm tên hoặc kiểm tra nhầm JVM | Kiểm tra `System.setProperty`, `-D...` và PID |
| Giá trị khác cấu hình dự kiến | Startup args, config reload hoặc code runtime đã thay đổi property | So sánh `VM.system_properties` với `VM.command_line` và cấu hình ứng dụng |
| Output quá dài | JVM có nhiều property | Chuyển output vào file và lọc theo prefix cần xem |
| Property không đổi hành vi ứng dụng | Thư viện đã cache cấu hình hoặc không hỗ trợ reload | Kiểm tra API reload/restart của thành phần sử dụng property |

## 10. Quy trình kiểm tra system property trong production

Khi cần xác định một cấu hình thực tế của ứng dụng:

1. Xác định đúng máy/container và tiến trình Java cần kiểm tra.
2. Dùng `jcmd -l` hoặc công cụ hệ điều hành để tìm PID.
3. Chạy `jcmd <pid> help` để xác nhận JVM nhận diagnostic command.
4. Chạy `jcmd <pid> VM.system_properties` để lấy giá trị hiện tại.
5. Lọc các key cần thiết và đối chiếu với cấu hình mong đợi.
6. Nếu cần biết giá trị được truyền lúc khởi động, xem thêm `VM.command_line`.
7. Nếu đang điều tra JVM tuning, kiểm tra `VM.flags` riêng.
8. Nếu property không như mong đợi, kiểm tra code khởi tạo, `System.setProperty`, thứ tự nạp cấu hình và cơ chế cache.
9. Bảo vệ output vì nó có thể chứa thông tin nội bộ hoặc bí mật.
10. Chỉ thay đổi cấu hình qua cơ chế quản trị mà ứng dụng hỗ trợ; `VM.system_properties` không sửa giá trị.

### Checklist

- [ ] Đã xác định đúng PID của JVM cần kiểm tra.
- [ ] Đã dùng cùng máy và đúng user/group để attach.
- [ ] Đã xác nhận command bằng `jcmd <pid> help`.
- [ ] Đã chạy `jcmd <pid> VM.system_properties`.
- [ ] Đã phân biệt system property với VM flag và environment variable.
- [ ] Đã đối chiếu startup property `-D` với giá trị runtime.
- [ ] Đã hiểu command chỉ đọc và không thay đổi property.
- [ ] Đã lọc/che thông tin nhạy cảm trước khi chia sẻ output.
- [ ] Đã kiểm tra giới hạn attach/container nếu không truy cập được JVM.

`jcmd <pid> VM.system_properties` cho phép xem system property thực tế của một JVM đang chạy, kể cả các giá trị được ứng dụng thay đổi trong runtime. Kết hợp đúng PID, quyền attach và việc đối chiếu với `VM.command_line` sẽ giúp chẩn đoán cấu hình chính xác mà không nhầm lẫn giữa property, VM flag và environment variable.

## Tài liệu tham khảo

- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle Java Troubleshooting Guide — jcmd utility](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)