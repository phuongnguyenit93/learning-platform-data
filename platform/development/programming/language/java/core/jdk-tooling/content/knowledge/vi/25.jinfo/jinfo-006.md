# Kiểm tra cấu hình JVM bằng `jinfo`

`jinfo` là công cụ trong JDK dùng để đọc cấu hình của một Java Virtual Machine (JVM) đang chạy. Công cụ hiển thị hai nhóm thông tin chính: các JVM flag và Java system property. Nhờ đó, người vận hành có thể kiểm tra heap size, garbage collector, tùy chọn `-XX`, thuộc tính `-D` và nhiều thông tin runtime khác mà không cần khởi động lại ứng dụng.

Các lệnh cơ bản:

~~~text
jinfo -flags <PID>
jinfo -flag MaxHeapSize <PID>
jinfo -sysprops <PID>
~~~

`jinfo` cũng có cú pháp để thay đổi một số JVM flag trong lúc process đang chạy. Chỉ những flag hỗ trợ thay đổi runtime mới có thể được cập nhật; các flag khởi tạo hoặc không manageable sẽ bị từ chối. Thay đổi runtime có thể ảnh hưởng trực tiếp đến ứng dụng, vì vậy cần kiểm tra metadata của flag và chính sách vận hành trước khi sử dụng.

Có một lưu ý quan trọng: tài liệu Oracle JDK 24 đánh dấu `jinfo` là experimental và unsupported, đồng thời khuyến nghị dùng `jcmd` cho chẩn đoán hiện đại. Bài này giải thích cách đọc `jinfo` để hiểu các hệ thống hiện có và cách chuyển sang lệnh `jcmd` tương đương khi phù hợp.

Toolchain dùng để kiểm tra bài này là Zulu/OpenJDK 24.0.2. Cú pháp và các flag phụ thuộc JVM, nhà cung cấp và phiên bản JDK. Hãy kiểm tra `jinfo -h` và `jcmd <PID> help` trên môi trường thực tế.

## 1. `jinfo` hiển thị những loại cấu hình nào?

Có thể chia thông tin cấu hình thành ba nhóm:

| Nhóm | Ví dụ | Nguồn |
|---|---|---|
| JVM flag | `-Xms`, `-Xmx`, `-XX:+UseG1GC` | Tùy chọn khởi chạy và flag do VM lựa chọn |
| Java system property | `java.version`, `user.timezone`, `app.profile` | `-Dname=value` hoặc `System.setProperty()` |
| Environment variable | `JAVA_HOME`, `PATH`, `APP_ENV` | Môi trường của process do hệ điều hành cung cấp |

`jinfo` tập trung vào JVM flag và Java system property. Nó không phải công cụ liệt kê toàn bộ environment variable của hệ điều hành.

Một system property có thể được tạo khi khởi chạy:

~~~text
java -Dapp.profile=staging -Dapp.region=ap-southeast com.example.ConfigProbe
~~~

Ứng dụng có thể đọc bằng:

~~~java
String profile = System.getProperty("app.profile");
~~~

Trong khi đó, environment variable được đọc bằng `System.getenv("APP_ENV")`. Hai cơ chế này khác nhau và không nên nhầm lẫn khi điều tra cấu hình.

## 2. Cú pháp và cách chọn đúng process

Cú pháp theo trợ giúp của JDK 24.0.2:

~~~text
jinfo <option> <pid>
~~~

Đối số `<pid>` là process ID của JVM cần kiểm tra. Bắt đầu bằng cách liệt kê Java process:

~~~text
jps -l
~~~

Ví dụ output minh họa:

~~~text
18240 com.example.OrderService
29116 com.example.ReportWorker
~~~

PID thay đổi theo máy và mỗi lần khởi chạy. Hãy lấy PID mới từ môi trường thực tế; không dùng lại PID trong tài liệu hoặc log cũ vì hệ điều hành có thể tái sử dụng PID.

Có thể dùng công cụ của hệ điều hành nếu `jps` không thấy process:

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^java(w)?\.exe$' } |
    Select-Object ProcessId, Name, CommandLine
~~~

macOS/Linux:

~~~sh
ps -ef | grep '[j]ava'
~~~

Sau khi xác định đúng PID, kiểm tra cấu hình:

~~~text
jinfo -flags 18240
~~~

Không chọn process chỉ dựa vào PID. Đối chiếu thêm tên ứng dụng, command line, user chạy process và môi trường deploy trước khi đọc hoặc thay đổi cấu hình.

## 3. Các tùy chọn đọc cấu hình

Theo `jinfo -h` trên JDK 24.0.2, các dạng chính là:

| Lệnh | Kết quả |
|---|---|
| `jinfo <PID>` | In cả JVM flag và Java system property |
| `jinfo -flags <PID>` | In các JVM flag |
| `jinfo -flag <name> <PID>` | In giá trị của một flag |
| `jinfo -sysprops <PID>` | In các Java system property |
| `jinfo -h` | Hiển thị trợ giúp |

### 3.1. Xem tất cả JVM flag

~~~text
jinfo -flags 18240
~~~

Output thường có phần mở đầu `VM Flags:` và các flag dạng:

~~~text
VM Flags:
-XX:InitialHeapSize=67108864
-XX:MaxHeapSize=268435456
-XX:+UseG1GC
-XX:+UseCompressedOops
~~~

Đây là ví dụ minh họa. Flag thực tế, thứ tự và giá trị phụ thuộc JVM, phần cứng, collector và tùy chọn khởi chạy.

Cần hiểu:

- `-XX:+FlagName`: flag Boolean đang bật.
- `-XX:-FlagName`: flag Boolean đang tắt.
- `-XX:FlagName=value`: flag có giá trị cụ thể.
- Giá trị heap thường được hiển thị theo byte trong output của một số lệnh.
- Một số giá trị do JVM tự chọn theo ergonomics, không nhất thiết xuất hiện nguyên văn trong command line ban đầu.

`jinfo -flags` hữu ích để xem trạng thái flag. Nếu cần biết chính xác đối số khởi chạy ban đầu, dùng `jcmd <PID> VM.command_line`.

### 3.2. Xem một flag cụ thể

~~~text
jinfo -flag MaxHeapSize 18240
jinfo -flag InitialHeapSize 18240
jinfo -flag UseG1GC 18240
~~~

Ví dụ output:

~~~text
-XX:MaxHeapSize=268435456
-XX:InitialHeapSize=67108864
-XX:+UseG1GC
~~~

Chỉ cần kiểm tra một flag sẽ dễ đọc hơn khi điều tra một cấu hình cụ thể, ví dụ:

- `MaxHeapSize`: giới hạn heap tối đa.
- `InitialHeapSize`: heap ban đầu.
- `UseG1GC`: trạng thái sử dụng G1 collector.
- `MaxMetaspaceSize`: giới hạn Metaspace nếu có cấu hình.
- `ActiveProcessorCount`: số CPU mà JVM dùng cho một số quyết định runtime.

Tên flag phải được kiểm tra theo đúng JDK. Không phải mọi flag đều tồn tại trong mọi phiên bản.

### 3.3. Xem Java system property

~~~text
jinfo -sysprops 18240
~~~

Output minh họa:

~~~text
java.version=24.0.2
java.specification.version=24
file.encoding=UTF-8
user.timezone=Asia/Ho_Chi_Minh
app.profile=staging
app.region=ap-southeast
~~~

Có thể lọc property cần xem để tránh phải đọc hàng trăm dòng:

PowerShell:

~~~powershell
jinfo -sysprops 18240 |
    Select-String 'java.version=|app.profile=|app.region='
~~~

macOS/Linux:

~~~sh
jinfo -sysprops 18240 |
    grep -E '^(java.version|app.profile|app.region)='
~~~

Nếu property chứa ký tự đặc biệt, dấu `=`, newline hoặc dữ liệu nhạy cảm, hãy dùng cách lưu và lọc output phù hợp với định dạng thực tế. Không giả định mọi property đều là chuỗi cấu hình công khai.

## 4. Phân biệt JVM flag với command line ban đầu

`jinfo -flags` cho biết trạng thái flag của VM. Nó không phải bản sao hoàn chỉnh của câu lệnh `java` đã chạy.

Ví dụ process được khởi chạy bằng:

~~~text
java -Xms64m -Xmx256m -XX:+UseG1GC -Dapp.profile=staging -Dapp.region=ap-southeast -cp . com.example.ConfigProbe
~~~

Có thể quan sát riêng từng phần:

~~~text
jinfo -flags <PID>
jinfo -sysprops <PID>
jcmd <PID> VM.command_line
~~~

- `jinfo -flags`: các VM flag đang có hiệu lực.
- `jinfo -sysprops`: các system property hiện tại.
- `VM.command_line`: command line mà JVM nhận lúc khởi chạy, bao gồm JVM arguments, main class và class path.

Một số flag được JVM tự chọn theo môi trường. Vì vậy, `MaxHeapSize` có thể xuất hiện trong `jinfo -flags` dù người vận hành không truyền `-Xmx` theo đúng giá trị đó.

Khi so sánh cấu hình giữa hai máy, ghi nhận cả JDK version, command line, JVM flags, system properties, container memory limit và CPU limit. Chỉ so sánh một flag có thể dẫn đến kết luận sai nếu hai môi trường có giới hạn tài nguyên khác nhau.

## 5. Đọc giá trị heap và các flag thường gặp

Các flag thường được kiểm tra khi điều tra bộ nhớ:

| Flag | Ý nghĩa |
|---|---|
| `InitialHeapSize` | Heap ban đầu mà JVM sử dụng |
| `MaxHeapSize` | Giới hạn heap tối đa |
| `MinHeapSize` | Mức heap tối thiểu theo VM |
| `MaxMetaspaceSize` | Giới hạn Metaspace nếu được cấu hình |
| `UseG1GC` | Có bật G1 garbage collector không |
| `UseParallelGC` | Có bật Parallel collector không |
| `UseSerialGC` | Có bật Serial collector không |
| `HeapDumpOnOutOfMemoryError` | Có tạo heap dump khi gặp OutOfMemoryError không |
| `ActiveProcessorCount` | Số processor JVM dùng cho một số quyết định runtime |

Ví dụ:

~~~text
jinfo -flag InitialHeapSize <PID>
jinfo -flag MaxHeapSize <PID>
jinfo -flag MaxMetaspaceSize <PID>
jinfo -flag UseG1GC <PID>
jinfo -flag HeapDumpOnOutOfMemoryError <PID>
~~~

Nếu `MaxMetaspaceSize` hoặc một flag khác không được đặt tường minh, JVM có thể dùng giá trị mặc định hoặc giá trị ergonomics. Không kết luận rằng flag bị thiếu đồng nghĩa với giá trị bằng `0`.

`-XX` là tùy chọn riêng của HotSpot VM, không phải Java SE API. Tên flag, mặc định và khả năng thay đổi có thể khác giữa các bản JDK hoặc nhà cung cấp JVM.

## 6. Phân biệt system property, environment variable và application config

Ba nguồn cấu hình này cần được kiểm tra bằng công cụ phù hợp:

| Nguồn | Cách đặt | Cách đọc |
|---|---|---|
| JVM flag | `-Xmx256m`, `-XX:+UseG1GC` | `jinfo -flags`, `jcmd VM.flags` |
| Java system property | `-Dapp.profile=staging` | `jinfo -sysprops`, `jcmd VM.system_properties` |
| Environment variable | `APP_ENV=staging` | `System.getenv`, OS process tools |
| Application config | YAML, properties, JSON, database | Cơ chế cấu hình của ứng dụng |

Ví dụ:

~~~java
String profile = System.getProperty("app.profile");
String environment = System.getenv("APP_ENV");

System.out.println("profile=" + profile);
System.out.println("environment=" + environment);
~~~

`jinfo -sysprops` sẽ hiển thị `app.profile` nếu property tồn tại. Nó không tự liệt kê biến `APP_ENV`.

Ứng dụng cũng có thể thay đổi system property sau khi khởi động bằng `System.setProperty()`. Vì vậy, giá trị trong `jinfo -sysprops` là giá trị hiện tại của process, không nhất thiết giống nguyên văn đối số `-D` lúc khởi chạy. Dùng `VM.command_line` để xem đối số ban đầu.

## 7. Thay đổi JVM flag trong lúc process chạy

Ngoài chế độ đọc, `jinfo` có các cú pháp thay đổi flag:

~~~text
jinfo -flag +<BooleanFlag> <PID>
jinfo -flag -<BooleanFlag> <PID>
jinfo -flag <FlagName>=<value> <PID>
~~~

Ví dụ về cú pháp:

~~~text
jinfo -flag +HeapDumpOnOutOfMemoryError <PID>
jinfo -flag -HeapDumpOnOutOfMemoryError <PID>
jinfo -flag MaxHeapSize=268435456 <PID>
~~~

Các lệnh trên minh họa cú pháp, không phải khuyến nghị thay đổi các flag đó trên production. `MaxHeapSize` thường không thể thay đổi sau khi JVM đã khởi tạo; lệnh sẽ bị từ chối nếu flag không hỗ trợ runtime update.

### 7.1. Kiểm tra flag có thể thay đổi hay không

Dùng `jcmd` để xem metadata:

~~~text
jcmd <PID> VM.flags -all
~~~

Output có thể đánh dấu một số flag bằng `{manageable}`. Đây là nhóm flag có thể được quản lý khi JVM đang chạy theo cơ chế của VM.

Ví dụ minh họa:

~~~text
bool HeapDumpOnOutOfMemoryError = false {manageable} {default}
bool ShowCodeDetailsInExceptionMessages = true {manageable} {default}
size_t MaxHeapSize = 268435456 {default}
~~~

Chỉ dùng thao tác runtime khi flag có khả năng thay đổi và đã hiểu tác động. Một số flag chỉ được đọc; một số flag chỉ có ý nghĩa trong giai đoạn startup; một số flag không thể thay đổi vì VM đã khởi tạo cấu trúc liên quan.

### 7.2. Runtime update không giống khởi động lại

Thay đổi flag bằng `jinfo` hoặc `jcmd VM.set_flag` chỉ tác động đến process hiện tại. Nó không tự sửa service file, Docker image, Kubernetes manifest, startup script hoặc cấu hình deploy.

Khi JVM restart, cấu hình startup mới sẽ quyết định giá trị ban đầu. Nếu muốn thay đổi lâu dài, cập nhật nguồn cấu hình được quản lý trong quy trình build/deploy và xác minh lại sau khi khởi động.

Không dùng runtime update để che giấu cấu hình sai trong deployment. Ghi nhận ai thay đổi, thời điểm, flag cũ, flag mới, lý do và cách khôi phục.

## 8. Dùng `jcmd` thay cho `jinfo`

Oracle khuyến nghị dùng `jcmd` thay cho các công cụ cũ như `jinfo` trong quy trình chẩn đoán hiện đại.

Các lệnh tương đương thường dùng:

| Mục tiêu | `jinfo` | `jcmd` |
|---|---|---|
| Xem VM flag | `jinfo -flags <PID>` | `jcmd <PID> VM.flags` |
| Xem mọi flag và metadata | Không có dạng tương đương trực tiếp | `jcmd <PID> VM.flags -all` |
| Xem một flag | `jinfo -flag <name> <PID>` | `jcmd <PID> VM.flags -all` rồi lọc |
| Xem system properties | `jinfo -sysprops <PID>` | `jcmd <PID> VM.system_properties` |
| Xem command line | Không chuyên biệt | `jcmd <PID> VM.command_line` |
| Xem JVM version | `jinfo` không phải lựa chọn phù hợp | `jcmd <PID> VM.version` |
| Thay đổi flag manageable | `jinfo -flag <name>=<value> <PID>` | `jcmd <PID> VM.set_flag <name> <value>` |

Ví dụ:

~~~text
jcmd 18240 VM.flags
jcmd 18240 VM.flags -all
jcmd 18240 VM.system_properties
jcmd 18240 VM.command_line
jcmd 18240 VM.version
~~~

Để tìm một flag trong danh sách:

PowerShell:

~~~powershell
jcmd 18240 VM.flags -all |
    Select-String 'MaxHeapSize|UseG1GC|HeapDumpOnOutOfMemoryError'
~~~

macOS/Linux:

~~~sh
jcmd 18240 VM.flags -all |
    grep -E 'MaxHeapSize|UseG1GC|HeapDumpOnOutOfMemoryError'
~~~

`jcmd` cung cấp thêm các lệnh chẩn đoán như `VM.info`, `VM.uptime`, `VM.classloader_stats`, `GC.heap_info`, `Thread.print` và `JFR.*`. Hãy chạy `jcmd <PID> help` để xem lệnh mà JVM cụ thể hỗ trợ.

## 9. Quyền truy cập và attach vào JVM

`jinfo` cần kết nối vào một JVM đang chạy. Nếu không attach được, kiểm tra:

- PID có đúng và process còn tồn tại không?
- Công cụ có chạy trên cùng máy với JVM đích không?
- User chạy công cụ có quyền truy cập process không?
- JVM có chạy dưới user hoặc group khác không?
- Attach mechanism có bị vô hiệu hóa bằng `-XX:+DisableAttachMechanism` không?
- Process có nằm trong container hoặc PID namespace khác không?
- Tool JDK có tương thích với runtime đích không?

Với `jcmd`, Oracle yêu cầu chạy trên cùng máy và cùng effective user/group identifiers với JVM đã khởi chạy. Với `jinfo`, cũng cần quyền OS phù hợp để attach vào process.

Trong container, PID từ host có thể khác PID bên trong container. `jps` trên host cũng có thể không liệt kê JVM ở container riêng. Khi đó, chạy công cụ từ đúng container hoặc dùng container runtime để xác định process trong namespace tương ứng.

Không tắt cơ chế bảo vệ hoặc nâng quyền tùy tiện chỉ để attach thành công. Nếu môi trường không cho phép attach, dùng diagnostics được nền tảng cung cấp như GC log, JFR, JMX có xác thực hoặc log ứng dụng.

## 10. Bảo vệ thông tin cấu hình

Output của `jinfo -sysprops` có thể chứa dữ liệu nhạy cảm. Ví dụ:

- Token, password hoặc API key được đặt nhầm trong `-D`.
- JDBC URL chứa username/password.
- Đường dẫn nội bộ, tên tài khoản, thư mục home.
- Thông tin endpoint, profile hoặc cấu hình tenant.
- `java.class.path` chứa tên module hoặc đường dẫn triển khai nội bộ.

`jinfo -flags` cũng có thể tiết lộ heap sizing, cấu hình GC, đường dẫn dump hoặc tùy chọn bảo mật.

Khi lưu output:

1. Chỉ thu thập property và flag cần điều tra.
2. Redact credential trước khi chia sẻ.
3. Giới hạn quyền đọc file report.
4. Không gửi toàn bộ output vào ticket hoặc chat công khai.
5. Xóa report tạm theo chính sách lưu giữ.
6. Nếu phát hiện secret bị lộ, xử lý theo quy trình rotation/incident response.

Không truyền password thật qua `-D` nếu có thể dùng secret manager hoặc cơ chế credential chuyên dụng. System property không phải kho bí mật an toàn.

## 11. Ví dụ Java 17+: kiểm tra cấu hình một JVM đang chạy

Tạo file `ConfigProbe.java`:

~~~java
public final class ConfigProbe {
    private ConfigProbe() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("app.profile=" + System.getProperty("app.profile"));
        System.out.println("app.region=" + System.getProperty("app.region"));

        Thread.sleep(300_000);
    }
}
~~~

Chương trình in hai property rồi chờ năm phút để người vận hành có thời gian kiểm tra process.

Biên dịch:

~~~text
javac --release 17 ConfigProbe.java
~~~

Khởi chạy:

~~~text
java -Xms64m -Xmx256m -XX:+UseG1GC -Dapp.profile=staging -Dapp.region=ap-southeast ConfigProbe
~~~

Stdout:

~~~text
app.profile=staging
app.region=ap-southeast
~~~

Mở terminal thứ hai và tìm process:

~~~text
jps -l
~~~

Lấy PID của `ConfigProbe`, sau đó chạy:

~~~text
jinfo -flags <PID>
jinfo -flag MaxHeapSize <PID>
jinfo -flag UseG1GC <PID>
jinfo -sysprops <PID>
~~~

Kết quả cần thấy:

- `MaxHeapSize` tương ứng cấu hình `-Xmx256m`.
- `UseG1GC` được bật.
- `app.profile=staging`.
- `app.region=ap-southeast`.

Kiểm tra command line ban đầu:

~~~text
jcmd <PID> VM.command_line
~~~

Output sẽ có các đối số `-Xms64m`, `-Xmx256m`, `-XX:+UseG1GC`, hai property `-D` và tên main class `ConfigProbe`.

Khi hoàn tất, dừng chương trình bằng `Ctrl+C`. PID và các flag khác có thể thay đổi theo runtime; hai dòng stdout về application property là cố định với lệnh khởi chạy mẫu.

## 12. Kiểm tra core dump bằng `jhsdb jinfo`

Nếu JVM đã crash và có core dump, `jinfo` thông thường không phải lệnh xử lý core file trong cú pháp hiện tại. Dùng Serviceability Agent:

~~~text
jhsdb jinfo --exe <path-to-java> --core <core-file>
~~~

Ví dụ trên Linux:

~~~text
jhsdb jinfo --exe /usr/lib/jvm/jdk-24/bin/java --core core.19256
~~~

Đường dẫn Java executable phải tương ứng với binary đã tạo ra core dump. Với JVM được tạo qua JNI Invocation API, binary gốc có thể không mang tên `java`.

Postmortem attach cần đúng quyền và symbol/debug information phù hợp. Serviceability Agent có thể dừng process hoặc có tác động đáng kể nếu dùng chế độ attach vào process đang chạy; hãy xem `jhsdb jinfo --help` và quy trình phân tích crash dump của môi trường.

## 13. Troubleshooting

### `AttachNotSupportedException`

**Nguyên nhân:** JVM không cho phép attach, sai user, sai namespace hoặc process không còn tồn tại.

**Cách xử lý:** xác nhận PID, host, user/group và `-XX:+DisableAttachMechanism`. Nếu chạy trong container, thực hiện từ đúng namespace.

### `Not enough permissions`

**Nguyên nhân:** tài khoản hiện tại không có quyền truy cập process hoặc thư mục tạm dùng cho attach.

**Cách xử lý:** chạy bằng tài khoản vận hành phù hợp, kiểm tra quyền OS và cấu hình thư mục tạm. Không nâng quyền toàn cục nếu chỉ cần quyền attach giới hạn.

### `Could not find ... JVM`

**Nguyên nhân:** PID sai, process đã kết thúc hoặc target không phải JVM tương thích.

**Cách xử lý:** chạy lại `jps -l` hoặc dùng process manager để xác nhận PID và executable.

### `Unknown VM flag`

**Nguyên nhân:** flag không tồn tại trong JDK/runtime đích hoặc đã bị đổi tên/xóa.

**Cách xử lý:** kiểm tra `jcmd <PID> VM.flags -all`, JDK version và tài liệu của đúng phiên bản.

### Không thể thay đổi flag

**Nguyên nhân:** flag không manageable hoặc chỉ được đọc sau startup.

**Cách xử lý:** xem metadata bằng `jcmd <PID> VM.flags -all`; nếu không có `{manageable}`, không giả định có thể đổi runtime. Cập nhật startup config và restart theo quy trình nếu cần.

### Property không có trong `jinfo -sysprops`

**Nguyên nhân:** ứng dụng đọc environment variable hoặc file config thay vì Java system property; property được đặt sau thời điểm kiểm tra hoặc tên key sai.

**Cách xử lý:** kiểm tra `System.getenv`, application config, command line và code gọi `System.setProperty()`.

### Giá trị `jinfo -flags` khác startup script

**Nguyên nhân:** JVM chọn giá trị ergonomics, wrapper thêm option, environment inject `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS` hoặc flag được thay đổi runtime.

**Cách xử lý:** so sánh `VM.command_line`, `VM.flags -all`, environment của process và cấu hình deploy. Ghi nhận cả JDK version và container resource limit.

### Không thấy JVM trong `jps`

**Nguyên nhân:** JVM ở container khác, user khác, custom launcher hoặc PID namespace khác.

**Cách xử lý:** lấy PID bằng OS process manager/container runtime và chạy diagnostics trong đúng môi trường.

### Output có credential

**Nguyên nhân:** secret được đặt trong system property hoặc command-line argument.

**Cách xử lý:** ngừng chia sẻ report chưa redact, rotate secret nếu đã bị lộ và chuyển sang secret management phù hợp.

## 14. Quy trình kiểm tra cấu hình JVM trong vận hành

Một quy trình ngắn có thể thực hiện như sau:

1. Xác định đúng host, container, service và PID.
2. Ghi nhận JDK vendor/version bằng `jcmd <PID> VM.version`.
3. Đọc JVM flag bằng `jcmd <PID> VM.flags` hoặc `jinfo -flags`.
4. Kiểm tra flag quan trọng bằng `jinfo -flag <name> <PID>` hoặc lọc `VM.flags -all`.
5. Đọc system property cần thiết; redact dữ liệu nhạy cảm.
6. Đối chiếu `VM.command_line` với startup script/deployment manifest.
7. Kiểm tra container CPU/memory limit và environment variable nếu giá trị ergonomics khác dự kiến.
8. Chỉ thay đổi runtime flag sau khi xác nhận flag manageable và đánh giá tác động.
9. Cập nhật nguồn cấu hình deploy nếu muốn thay đổi tồn tại sau restart.
10. Lưu report đã redact cùng timestamp, PID, JDK version và owner.

## 15. Checklist trước khi kết luận cấu hình JVM

- [ ] Đã xác nhận đúng process và PID hiện tại.
- [ ] Đã ghi nhận JDK vendor/version.
- [ ] Đã xem `jinfo -flags` hoặc `jcmd VM.flags`.
- [ ] Đã kiểm tra riêng heap size, collector và các flag liên quan.
- [ ] Đã xem system property cần thiết.
- [ ] Đã phân biệt system property với environment variable.
- [ ] Đã kiểm tra command line gốc bằng `VM.command_line`.
- [ ] Đã xem metadata `{manageable}` trước khi đề xuất thay đổi flag.
- [ ] Đã hiểu runtime update không tự cập nhật startup/deploy config.
- [ ] Đã kiểm tra user, quyền attach và container/PID namespace.
- [ ] Đã redact token, password, URL credential và thông tin nội bộ.
- [ ] Đã lưu report có timestamp và JDK version nếu cần audit.
- [ ] Đã dùng `jcmd` cho quy trình diagnostics mới thay cho `jinfo` khi phù hợp.

## 16. Tài liệu tham khảo

- Oracle JDK 24 — The `jinfo` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jinfo.html
- Oracle JDK 24 — Diagnostic Tools, phần `jinfo` và `jcmd`: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Oracle JDK 24 — Java HotSpot VM Command-Line Options: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html

`jinfo` giúp xem nhanh JVM flag và system property của một process đang chạy, đồng thời hỗ trợ thay đổi một số flag có thể quản lý trong runtime. Để kết luận cấu hình chính xác, hãy đối chiếu trạng thái hiện tại với command line, metadata flag, environment và cấu hình deploy. Vì `jinfo` là công cụ experimental/unsupported, ưu tiên `jcmd` cho quy trình chẩn đoán mới.