# VM flag trong Java: đọc và thay đổi bằng jinfo

## Mục tiêu

Sau bài này, bạn có thể giải thích VM flag và phân biệt nó với system property; đọc cấu hình của JVM đang chạy bằng jinfo; dùng cú pháp -flag để xem, bật, tắt hoặc đặt giá trị; phân biệt flag chỉ có hiệu lực lúc khởi động với diagnostic option có thể thay đổi động; dùng jcmd làm công cụ chẩn đoán được khuyến nghị; kiểm tra giá trị, nguồn gốc và khả năng ghi của VM option bằng HotSpotDiagnosticMXBean; và xác minh thay đổi trước khi đưa cấu hình vào vận hành.

## 1. VM flag là gì?

**VM flag** là một tùy chọn cấu hình của Java Virtual Machine (JVM). Flag điều khiển cách JVM khởi động, quản lý heap, garbage collection, JIT compiler, class loading, logging, diagnostics và nhiều hoạt động nội bộ khác.

Ví dụ:

~~~bash
java -Xms512m -Xmx2g -XX:+UseG1GC -jar service.jar
~~~

- -Xms512m đặt heap ban đầu.
- -Xmx2g đặt giới hạn heap tối đa.
- -XX:+UseG1GC yêu cầu sử dụng G1 garbage collector.
- -jar service.jar khởi chạy ứng dụng từ JAR.

Các flag thường được truyền vào lúc khởi chạy JVM. Một số flag có thể thay đổi khi JVM đang chạy, nhưng phần lớn flag ảnh hưởng đến cấu trúc hoặc cách khởi tạo VM chỉ có thể đặt lúc startup.

Flag có thể mang giá trị boolean, số, kích thước bộ nhớ, chuỗi hoặc tham số phức tạp. Không phải flag nào cũng có thể thay đổi động.

### Các dạng flag thường gặp

| Dạng | Ví dụ | Ý nghĩa |
|---|---|---|
| Boolean | -XX:+UseG1GC | Bật flag |
| Boolean | -XX:-UseG1GC | Tắt flag |
| Kích thước | -Xmx2g | Đặt heap tối đa |
| Giá trị -XX | -XX:MaxRAMPercentage=75.0 | Đặt tỷ lệ RAM tối đa cho heap |
| Stack | -Xss1m | Đặt kích thước stack mỗi thread |

Các tùy chọn -XX chủ yếu là tùy chọn riêng của HotSpot VM. Chúng có thể thay đổi giữa các phiên bản JDK và vendor; không xem chúng như API Java ổn định.

## 2. Phân biệt VM flag và system property

VM flag và system property đều có thể được truyền khi khởi chạy Java, nhưng chúng có mục đích khác nhau.

### VM flag

Flag điều khiển JVM hoặc một tính năng của runtime:

~~~bash
java -Xmx2g -XX:+HeapDumpOnOutOfMemoryError -jar service.jar
~~~

### System property

System property là cặp tên/giá trị được truyền bằng -D. Ứng dụng có thể đọc bằng System.getProperty:

~~~bash
java -Dapp.region=ap-southeast-1 -Dapp.mode=production -jar service.jar
~~~

Trong Java:

~~~java
String region = System.getProperty("app.region");
~~~

| Nội dung | VM flag | System property |
|---|---|---|
| Cú pháp phổ biến | -X..., -XX:... | -Dname=value |
| Mục đích | Cấu hình JVM/HotSpot | Cung cấp cấu hình cho ứng dụng và thư viện |
| Ví dụ | -Xmx2g | -Dapp.region=ap-southeast-1 |
| Công cụ đọc | jinfo -flag, jinfo -flags, jcmd VM.flags | jinfo -sysprops, jcmd VM.system_properties |
| Thay đổi lúc chạy | Chỉ một số flag được phép | Có thể thay đổi qua System.setProperty; hiệu lực tùy ứng dụng |

Thay đổi system property không tự động thay đổi VM flag. Ví dụ, gọi System.setProperty("java.heap.max", "2g") không làm heap của JVM tăng lên.

## 3. jinfo dùng để làm gì?

jinfo là công cụ dòng lệnh đi kèm JDK, dùng để in thông tin cấu hình của một Java process. Thông tin gồm JVM command-line flags và Java system properties.

jinfo có thể:

- In cả flag và system property của JVM.
- In giá trị hiện tại của một flag.
- Bật hoặc tắt một flag boolean mà JVM cho phép thay đổi.
- Đặt giá trị cho một flag có thể ghi.
- Hỗ trợ điều tra cấu hình của một process Java đang chạy.

Cú pháp JDK 26:

~~~bash
jinfo [option] pid
~~~

Trong đó pid là process ID của JVM đích. jinfo yêu cầu một Java process đang chạy.

**Lưu ý quan trọng:** tài liệu Java SE 26 đánh dấu jinfo là experimental và unsupported. Công cụ có thể không còn trong một phiên bản JDK tương lai. Oracle khuyến nghị dùng jcmd cho chẩn đoán JVM mới vì có nhiều diagnostic command hơn và giảm overhead so với các tiện ích cũ như jinfo.

Bài này giải thích jinfo để bạn hiểu công cụ và cú pháp VM flag. Với quy trình vận hành mới, ưu tiên jcmd hoặc JMX/HotSpotDiagnosticMXBean khi phù hợp.

## 4. Tìm PID của JVM cần kiểm tra

jinfo cần PID của Java process. Có thể dùng jcmd hoặc công cụ hệ điều hành để tìm PID.

### Dùng jcmd

~~~bash
jcmd -l
~~~

Ví dụ output:

~~~text
4128 com.example.OrderService
7852 org.apache.catalina.startup.Bootstrap
~~~

PID và tên ứng dụng thực tế sẽ khác. jcmd -l không liệt kê mọi JVM trong một số môi trường Docker có PID namespace riêng; khi đó hãy dùng ps bên trong đúng container để tìm PID.

### Dùng công cụ hệ điều hành

Linux:

~~~bash
ps -ef | grep '[j]ava'
~~~

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^java(w)?\.exe$' } |
    Select-Object ProcessId, Name, CommandLine
~~~

Hãy xác nhận đúng PID, main class và đường dẫn ứng dụng trước khi chạy lệnh có khả năng thay đổi cấu hình.

## 5. Cú pháp jinfo để đọc VM flag

### In toàn bộ thông tin

~~~bash
jinfo <PID>
~~~

Nếu không chỉ định option, jinfo in cả command-line flags và system property dạng name/value.

Output có thể dài vì JVM có nhiều property. Cần bảo vệ kết quả vì system property hoặc command line đôi khi chứa endpoint nội bộ, username hoặc dữ liệu nhạy cảm.

### Chỉ in command-line flags

~~~bash
jinfo -flags <PID>
~~~

Tùy chọn -flags in các flag được truyền khi khởi chạy JVM. Nó hữu ích khi cần tìm lại tham số startup trong lúc ứng dụng đang chạy.

Không nhầm kết quả này với toàn bộ giá trị mặc định và giá trị do JVM tự chọn theo cấu hình máy. Nếu cần xem đầy đủ flag và giá trị hiện tại, dùng jcmd VM.flags hoặc -XX:+PrintFlagsFinal khi khởi động một JVM mới.

### Chỉ in system properties

~~~bash
jinfo -sysprops <PID>
~~~

Lệnh in các system property theo dạng:

~~~text
java.version=...
java.home=...
os.name=...
user.dir=...
app.region=...
~~~

Các dấu ba chấm là giá trị minh họa; giá trị thật phụ thuộc process và môi trường.

### In một VM flag cụ thể

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError <PID>
~~~

Cú pháp -flag name in tên và giá trị hiện tại của flag được chỉ định. Đây là lựa chọn phù hợp khi chỉ cần kiểm tra một flag, thay vì in toàn bộ cấu hình JVM.

## 6. Bật, tắt và đặt giá trị bằng jinfo -flag

jinfo hỗ trợ các dạng cú pháp -flag:

| Cú pháp | Tác dụng |
|---|---|
| -flag name | In tên và giá trị flag |
| -flag +name | Bật flag boolean |
| -flag -name | Tắt flag boolean |
| -flag name=value | Đặt flag thành giá trị chỉ định |

### Bật một flag boolean

Ví dụ bật tạo heap dump khi xảy ra OutOfMemoryError:

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError <PID>
~~~

### Tắt một flag boolean

~~~bash
jinfo -flag -HeapDumpOnOutOfMemoryError <PID>
~~~

### Đặt một flag dạng giá trị

Với flag có kiểu giá trị, dùng cú pháp name=value:

~~~bash
jinfo -flag HeapDumpPath=./dumps <PID>
~~~

Thư mục đích phải tồn tại và JVM phải có quyền ghi khi tạo heap dump. Chỉ thay đổi flag này nếu đã xác định rõ vị trí lưu file, dung lượng và chính sách bảo vệ dữ liệu.

### Xác minh sau khi thay đổi

Đọc lại flag:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError <PID>
~~~

Hoặc dùng jcmd:

~~~bash
jcmd <PID> VM.flags
~~~

Không kết luận thay đổi thành công chỉ vì lệnh không in lỗi. Hãy đọc lại giá trị và kiểm tra hành vi thực tế nếu flag có tác động đến ứng dụng.

## 7. Không phải mọi VM flag đều thay đổi được lúc runtime

Một số flag có thể thay đổi động, chủ yếu là các diagnostic option được JVM cho phép ghi. Các flag khác chỉ có hiệu lực khi JVM khởi tạo.

Ví dụ:

| Flag | Cách sử dụng | Khả năng thay đổi |
|---|---|---|
| HeapDumpOnOutOfMemoryError | Tự tạo heap dump khi OOME | Diagnostic option có thể thay đổi động trên HotSpot hỗ trợ |
| HeapDumpPath | Chọn vị trí heap dump | Diagnostic option có thể thay đổi động trên HotSpot hỗ trợ |
| Xms | Heap ban đầu | Thiết lập lúc khởi động |
| Xmx | Heap tối đa | Thiết lập lúc khởi động; không dùng jinfo để thay đổi sau startup |
| Xss | Stack size cho thread | Thiết lập lúc khởi động |
| UseG1GC | Chọn GC | Cấu hình lúc khởi động |
| MaxRAMPercentage | Tỷ lệ RAM dùng để tính heap tối đa | Cấu hình lúc khởi động |

Bảng nêu các trường hợp phổ biến; khả năng cụ thể phụ thuộc JDK, vendor và JVM implementation.

Một flag có thể tồn tại nhưng không writable. Khi cố thay đổi flag không được hỗ trợ, jinfo hoặc diagnostic interface sẽ báo lỗi. Không thử thay đổi hàng loạt flag để tìm flag nào hoạt động trên production.

### Diagnostic option và khả năng ghi

HotSpotDiagnosticMXBean cung cấp danh sách diagnostic option có thể ghi. API này cho phép:

- getDiagnosticOptions(): lấy danh sách diagnostic option.
- getVMOption(name): lấy giá trị và thông tin của một VM option.
- setVMOption(name, value): đặt giá trị mới nếu option có thể ghi.

Đối tượng VMOption có các thông tin:

- getName(): tên option.
- getValue(): giá trị tại thời điểm object được tạo.
- getOrigin(): nguồn gốc giá trị.
- isWriteable(): option có thể được thay đổi động hay không.

Nếu isWriteable() trả false, không thể dùng HotSpotDiagnosticMXBean.setVMOption để thay đổi option đó.

## 8. Nguồn gốc của giá trị VM option

Giá trị flag có thể đến từ nhiều nguồn:

| Origin | Ý nghĩa |
|---|---|
| DEFAULT | JVM đang dùng giá trị mặc định |
| VM_CREATION | Giá trị được đặt lúc tạo JVM, thường qua command line |
| ENVIRON_VAR | Giá trị đến từ environment variable |
| CONFIG_FILE | Giá trị đến từ file cấu hình |
| MANAGEMENT | Giá trị được thay đổi qua management interface sau khi JVM chạy |
| ERGONOMIC | JVM tự chọn giá trị dựa trên môi trường và cấu hình |
| ATTACH_ON_DEMAND | Giá trị được đặt qua attach framework |
| OTHER | Nguồn khác |

Origin giúp giải thích vì sao giá trị hiện tại khác với mặc định. Ví dụ, heap tối đa có thể được JVM chọn dựa trên RAM máy thay vì một giá trị do developer truyền trực tiếp.

Nếu cần kiểm toán cấu hình, hãy ghi lại tên flag, giá trị, origin, JDK version và thời điểm thu thập.

## 9. Dùng jcmd thay cho jinfo trong quy trình mới

jcmd là công cụ diagnostic command được Oracle khuyến nghị thay cho jinfo trong chẩn đoán JVM mới.

### In flag và giá trị hiện tại

~~~bash
jcmd <PID> VM.flags
~~~

VM.flags in các VM flag và giá trị hiện tại.

Muốn xem toàn bộ flag mà VM hỗ trợ:

~~~bash
jcmd <PID> VM.flags -all
~~~

### Thay đổi flag có thể ghi

~~~bash
jcmd <PID> VM.set_flag HeapDumpOnOutOfMemoryError true
~~~

VM.set_flag đặt VM flag theo tên và giá trị truyền vào. Flag phải tồn tại, giá trị phải hợp lệ và JVM phải cho phép thay đổi động.

### Xác minh lại

~~~bash
jcmd <PID> VM.flags -all
~~~

Tìm HeapDumpOnOutOfMemoryError trong kết quả để xác nhận giá trị.

### Đọc system properties và command line

~~~bash
jcmd <PID> VM.system_properties
jcmd <PID> VM.command_line
~~~

- VM.system_properties in các system property.
- VM.command_line in command line đã dùng để khởi chạy JVM.

Đây là các command tương đương hữu ích khi thay thế thói quen dùng jinfo -sysprops hoặc jinfo không có option.

### Khám phá command trên JVM đích

~~~bash
jcmd <PID> help
jcmd <PID> help VM.set_flag
jcmd <PID> help VM.flags
~~~

Danh sách diagnostic command có thể khác giữa JDK version và JVM vendor. Hãy xem help của chính process đích trước khi đưa lệnh vào automation.

## 10. Ví dụ Java: đọc giá trị và writeability bằng HotSpotDiagnosticMXBean

Java cung cấp API quản lý HotSpot diagnostic option qua module jdk.management. Ví dụ sau đọc giá trị, nguồn gốc và khả năng ghi của flag HeapDumpOnOutOfMemoryError.

Tạo file VmFlagInspector.java:

~~~java
import com.sun.management.HotSpotDiagnosticMXBean;
import com.sun.management.VMOption;
import java.lang.management.ManagementFactory;

public class VmFlagInspector {
    public static void main(String[] args) {
        HotSpotDiagnosticMXBean bean =
                ManagementFactory.getPlatformMXBean(
                        HotSpotDiagnosticMXBean.class);

        VMOption option =
                bean.getVMOption("HeapDumpOnOutOfMemoryError");

        System.out.println("name=" + option.getName());
        System.out.println("value=" + option.getValue());
        System.out.println("writeable=" + option.isWriteable());
        System.out.println("origin=" + option.getOrigin());
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac --add-modules jdk.management VmFlagInspector.java
java --add-modules jdk.management VmFlagInspector
~~~

Với HotSpot mặc định, chưa đặt flag này qua command line hoặc management interface, output:

~~~text
name=HeapDumpOnOutOfMemoryError
value=false
writeable=true
origin=DEFAULT
~~~

Giải thích:

- value=false: JVM hiện không bật tự động heap dump khi xảy ra OutOfMemoryError.
- writeable=true: option có thể được thay đổi động trong HotSpot implementation hỗ trợ.
- origin=DEFAULT: giá trị hiện tại đến từ mặc định của JVM.

Nếu chạy JVM với -XX:+HeapDumpOnOutOfMemoryError, giá trị và origin sẽ khác ví dụ trên.

Ví dụ này chỉ đọc cấu hình của chính JVM đang chạy chương trình. Để kiểm tra process khác, dùng jinfo/jcmd hoặc kết nối management interface đã được cấu hình và bảo vệ phù hợp.

## 11. Ví dụ thực hành: thay đổi một VM flag trên JVM đang chạy

Ví dụ tạo một process Java đơn giản để bạn có thể attach từ terminal thứ hai.

Tạo file FlagTarget.java:

~~~java
public class FlagTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("vm-flag-target-ready");

        while (true) {
            Thread.sleep(1_000);
        }
    }
}
~~~

### Bước 1: biên dịch

~~~bash
javac --release 17 FlagTarget.java
~~~

### Bước 2: khởi chạy JVM đích

~~~bash
java -XX:-HeapDumpOnOutOfMemoryError FlagTarget
~~~

Output chính xác:

~~~text
vm-flag-target-ready
~~~

Giữ process này chạy. Mở terminal thứ hai để thực hiện các bước tiếp theo.

### Bước 3: tìm PID

~~~bash
jcmd -l
~~~

Tìm dòng có main class FlagTarget và ghi lại PID.

### Bước 4: đọc flag bằng jinfo

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError <PID>
~~~

Flag ban đầu được đặt false bởi tùy chọn -XX:-HeapDumpOnOutOfMemoryError. Output cụ thể phụ thuộc phiên bản và cách hiển thị của công cụ; điều cần xác nhận là giá trị hiện tại đang false.

### Bước 5: bật flag động

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError <PID>
~~~

Nếu jinfo được hỗ trợ trên môi trường đang dùng và JVM cho phép ghi flag này, giá trị được bật trong process hiện tại.

Có thể dùng jcmd thay thế:

~~~bash
jcmd <PID> VM.set_flag HeapDumpOnOutOfMemoryError true
~~~

### Bước 6: xác minh

~~~bash
jcmd <PID> VM.flags -all
~~~

Tìm HeapDumpOnOutOfMemoryError và xác nhận giá trị đã đổi thành true.

### Bước 7: kết thúc

Quay lại terminal chạy FlagTarget và nhấn Ctrl+C.

Ví dụ này không cố tình tạo OutOfMemoryError. Mục tiêu chỉ là chứng minh một diagnostic flag có thể được bật động và đọc lại. Trong môi trường thật, việc bật heap dump có thể tạo file rất lớn khi ứng dụng hết heap; hãy xác định vị trí lưu, dung lượng và quyền truy cập trước khi bật.

## 12. Thay đổi runtime không đồng nghĩa thay đổi cấu hình khởi động

Khi jinfo hoặc jcmd thay đổi một writable flag, giá trị mới có hiệu lực trong JVM process hiện tại.

Thay đổi đó thường không tự ghi lại:

- Script khởi động ứng dụng.
- Dockerfile hoặc container command.
- Kubernetes manifest.
- systemd unit.
- Service wrapper.
- File cấu hình triển khai.
- Environment variable dùng khi khởi động.

Khi process restart, JVM đọc lại cấu hình khởi động và các nguồn cấu hình được hỗ trợ. Nếu không lưu thay đổi vào cấu hình triển khai, giá trị động có thể quay về mặc định hoặc giá trị startup ban đầu.

Quy trình đúng:

1. Dùng runtime flag change để điều tra hoặc xử lý tạm thời khi phù hợp.
2. Ghi lại giá trị cũ, giá trị mới, lý do, thời gian và người thực hiện.
3. Xác minh hành vi của ứng dụng.
4. Nếu thay đổi là yêu cầu lâu dài, cập nhật cấu hình startup qua quy trình deployment.
5. Restart trong cửa sổ được phép nếu flag chỉ áp dụng lúc khởi động.
6. Kiểm tra lại giá trị sau restart.

Không coi một lệnh jinfo thành công là bằng chứng cấu hình đã được lưu bền vững.

## 13. Flag nào nên đặt lúc khởi động?

Những flag ảnh hưởng đến cấu trúc heap, lựa chọn garbage collector, thread stack, module system hoặc cách VM khởi tạo thường cần được đặt lúc khởi động.

Ví dụ:

~~~bash
java -Xms512m -Xmx2g -Xss1m -XX:+UseG1GC -jar service.jar
~~~

Không dùng jinfo để cố thay đổi Xms, Xmx, Xss hoặc collector selection trên một JVM đã chạy. Nếu cần điều chỉnh, cập nhật cấu hình startup rồi restart theo quy trình.

Các flag diagnostic như HeapDumpOnOutOfMemoryError hoặc HeapDumpPath có thể writable trên HotSpot. Danh sách writable thực tế nên được kiểm tra bằng HotSpotDiagnosticMXBean hoặc command help của JVM.

## 14. jinfo, jcmd và HotSpotDiagnosticMXBean khác nhau thế nào?

| Công cụ/API | Đọc flag | Đổi flag | Phù hợp |
|---|---|---|---|
| jinfo | Có | Một số flag | Tương thích và học cú pháp cũ; experimental/unsupported |
| jcmd VM.flags | Có | Không, chỉ đọc | Chẩn đoán giá trị hiện tại |
| jcmd VM.set_flag | Không phải mục đích chính | Flag được JVM cho phép | Thay đổi flag qua diagnostic command |
| HotSpotDiagnosticMXBean | Có | Diagnostic option writable | Tích hợp quản trị bằng Java/JMX |
| java -XX:+PrintFlagsFinal | In flag của JVM mới khi khởi chạy | Không | Kiểm tra default/ergonomic values của lần khởi tạo mới |

jcmd là lựa chọn CLI được khuyến nghị cho chẩn đoán hiện đại. HotSpotDiagnosticMXBean phù hợp khi một ứng dụng quản trị hoặc công cụ JMX cần xem và thay đổi diagnostic option có thể ghi.

## 15. Lỗi thường gặp và cách xử lý

### jinfo không tìm thấy process

**Dấu hiệu:** công cụ báo không thể tìm PID hoặc không phải Java process.

**Nguyên nhân:** PID sai, process đã dừng, JVM chạy trong PID namespace khác hoặc user không có quyền truy cập.

**Cách xử lý:** dùng jcmd -l hoặc công cụ OS trong đúng container/host; xác nhận PID và môi trường chạy trước khi attach.

### jinfo không có trong JDK

**Dấu hiệu:** shell báo command not found hoặc không tìm thấy jinfo executable.

**Nguyên nhân:** JDK distribution không đóng gói công cụ này hoặc phiên bản tương lai đã loại bỏ công cụ unsupported.

**Cách xử lý:** dùng jcmd VM.flags, VM.system_properties, VM.command_line và VM.set_flag nếu JVM đích hỗ trợ. Không tải một bản jinfo không rõ nguồn để chạy trên production.

### jinfo attach không hoạt động trên Windows

**Dấu hiệu:** lỗi liên quan dbgeng.dll, jvm.dll hoặc debugging tools.

**Nguyên nhân:** tài liệu jinfo JDK 26 nêu rằng trên Windows thiếu dbgeng.dll có thể cần cài Debugging Tools for Windows; PATH phải chứa vị trí jvm.dll của process đích hoặc core dump.

**Cách xử lý:** xác nhận JDK/tool tương thích, PATH và thành phần debugging tools theo tài liệu nền tảng. Nếu không cần jinfo, dùng jcmd được hỗ trợ trên môi trường đó.

### Flag không tồn tại

**Dấu hiệu:** jinfo hoặc jcmd báo không tìm thấy flag.

**Nguyên nhân:** sai tên, flag đã thay đổi/loại bỏ ở JDK khác hoặc flag không có trên vendor/VM hiện tại.

**Cách xử lý:** kiểm tra JDK version và tên flag trong tài liệu của đúng phiên bản; dùng jcmd VM.flags -all để xem flag VM hỗ trợ.

### Flag không thể thay đổi động

**Dấu hiệu:** công cụ báo flag không writable, không manageable hoặc giá trị không thể cập nhật.

**Nguyên nhân:** flag chỉ áp dụng lúc startup hoặc JVM không đánh dấu option là writable.

**Cách xử lý:** kiểm tra VMOption.isWriteable() hoặc danh sách getDiagnosticOptions(); nếu không writable, thay đổi cấu hình startup và restart theo quy trình.

### Giá trị không hợp lệ

**Dấu hiệu:** JVM từ chối giá trị mới.

**Nguyên nhân:** sai kiểu, sai đơn vị, vượt range hoặc vi phạm ràng buộc giữa các flag.

**Cách xử lý:** xem help và tài liệu của flag; dùng đúng đơn vị, kiểu và khoảng giá trị. Không thử giá trị ngẫu nhiên trên production.

### Đổi flag nhưng ứng dụng không có hành vi mong muốn

**Dấu hiệu:** jinfo/jcmd báo đổi thành công nhưng ứng dụng không thay đổi như dự kiến.

**Nguyên nhân:** flag không điều khiển hành vi đang quan sát, subsystem đã khởi tạo trước đó hoặc ứng dụng dùng cấu hình riêng.

**Cách xử lý:** đọc tài liệu flag, xác minh giá trị sau thay đổi và kiểm thử hành vi thực tế. Một số flag chỉ ảnh hưởng tới lần allocation, OOME hoặc hoạt động tiếp theo.

### Giá trị quay lại sau restart

**Dấu hiệu:** flag đã đổi runtime nhưng sau khi restart trở về giá trị cũ.

**Nguyên nhân:** thay đổi runtime không cập nhật script/configuration khởi động.

**Cách xử lý:** sửa cấu hình deployment và xác minh startup arguments của process mới.

### Lẫn lộn flag và system property

**Dấu hiệu:** dùng jinfo -flag với tên property được tạo bằng -D hoặc tìm flag trong -sysprops.

**Nguyên nhân:** nhầm hai loại cấu hình.

**Cách xử lý:** dùng jinfo -flag hoặc jcmd VM.flags cho VM option; dùng jinfo -sysprops hoặc jcmd VM.system_properties cho system property.

## 16. An toàn khi thay đổi VM flag

Thay đổi VM flag có thể ảnh hưởng hiệu năng, bộ nhớ, garbage collection, logging hoặc khả năng tạo diagnostic artifact.

Trước khi đổi:

- Xác định đúng PID và đúng môi trường.
- Ghi lại giá trị hiện tại.
- Xác minh flag có writable không.
- Đọc tài liệu về side effect và phạm vi hiệu lực.
- Chuẩn bị giá trị rollback.
- Đánh giá dung lượng disk nếu flag tạo heap dump/log.
- Xác định thay đổi là tạm thời hay cần lưu vào startup config.
- Kiểm tra quyền attach và quyền quản trị.

Sau khi đổi:

- Đọc lại flag để xác nhận.
- Theo dõi log, metrics và hành vi ứng dụng.
- Ghi lại thay đổi trong incident/change record.
- Hoàn nguyên nếu không đạt mục tiêu.
- Cập nhật startup configuration nếu thay đổi cần tồn tại sau restart.

Không dùng VM flag để tắt kiểm tra bảo mật, bỏ qua certificate validation hoặc nới lỏng policy chỉ để che lỗi. Mọi thay đổi cần có lý do, phạm vi và phương án khôi phục.

## 17. Checklist làm việc với VM flag

- [ ] Xác định JDK version và JVM vendor của process đích.
- [ ] Xác định đúng PID.
- [ ] Phân biệt VM flag với system property.
- [ ] Dùng jinfo -flag name để đọc một flag khi jinfo có sẵn.
- [ ] Dùng jinfo -flags để xem flags truyền khi khởi động.
- [ ] Dùng jinfo -sysprops để xem system properties.
- [ ] Ưu tiên jcmd VM.flags và VM.system_properties trong quy trình mới.
- [ ] Dùng jcmd VM.flags -all để xem các flag VM hỗ trợ.
- [ ] Chỉ thay đổi flag được JVM cho phép ghi.
- [ ] Kiểm tra writeability bằng HotSpotDiagnosticMXBean khi cần.
- [ ] Dùng đúng cú pháp boolean +name/-name hoặc name=value.
- [ ] Đọc lại giá trị sau khi thay đổi.
- [ ] Cập nhật startup configuration nếu cần giữ giá trị sau restart.
- [ ] Ghi lại giá trị cũ, mới, lý do và thời điểm thay đổi.
- [ ] Kiểm thử hành vi thực tế và có phương án rollback.

## 18. Tài liệu tham khảo chính thức

- [The jinfo Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jinfo.html) — trạng thái experimental/unsupported, cú pháp -flag, -flags và -sysprops.
- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — VM.flags, VM.set_flag, VM.system_properties và các diagnostic command thay thế.
- [Diagnostic Tools — Java SE 26 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html) — khuyến nghị dùng jcmd thay jinfo và cách dùng jinfo để kiểm tra cấu hình JVM.
- [HotSpotDiagnosticMXBean — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html) — getDiagnosticOptions, getVMOption và setVMOption.
- [VMOption — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/VMOption.html) — giá trị, origin và isWriteable của VM option.
- [VMOption.Origin — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/VMOption.Origin.html) — các nguồn gốc DEFAULT, VM_CREATION, ENVIRON_VAR, CONFIG_FILE, MANAGEMENT và ERGONOMIC.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — tùy chọn launcher, JVM flags và cách xác minh giá trị flag.

VM flag cho phép cấu hình hành vi của JVM. jinfo cung cấp cú pháp ngắn để đọc và thay đổi một số flag, nhưng vì công cụ đã được đánh dấu unsupported, hãy ưu tiên jcmd và HotSpotDiagnosticMXBean trong hệ thống mới. Chỉ thay đổi option writable, xác minh lại giá trị và lưu thay đổi lâu dài vào cấu hình khởi động khi cần.
