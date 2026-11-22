# Khi nào dùng jinfo?

`jinfo` là công cụ dòng lệnh đi kèm JDK để đọc thông tin cấu hình của một JVM đang chạy. Nó có thể hiển thị các system properties, VM flags và đọc giá trị của một flag cụ thể. Với một số flag có thể quản lý động (*manageable flags*), công cụ còn cho phép bật, tắt hoặc đổi giá trị khi process vẫn đang chạy.

Tuy vậy, Oracle đánh dấu `jinfo` là *experimental and unsupported* và khuyến nghị dùng `jcmd` thay cho các công cụ chẩn đoán đời cũ như `jinfo`, `jstack` và `jmap`. Vì thế, bài học này tập trung vào việc nhận biết đúng trường hợp `jinfo` còn hữu ích, hiểu giới hạn của nó và chọn công cụ thay thế phù hợp.

## 1. jinfo dùng để làm gì?

Một JVM đang chạy có nhiều thông tin cấu hình cần kiểm tra khi điều tra sự cố:

- JVM được khởi chạy với những VM flag nào?
- Giá trị hiện tại của một flag cụ thể là gì?
- Ứng dụng đang dùng phiên bản Java, thư mục cài đặt và classpath nào?
- Những system property nào đang được JVM cung cấp?
- Một flag có thể quản lý động có đang bật hay không?

`jinfo` có thể trả lời những câu hỏi này cho một Java process được chỉ định bằng PID.

Ví dụ:

~~~bash
jinfo 12345
~~~

Nếu không truyền option, `jinfo` in cả VM flags và các cặp tên/giá trị system property. Output có thể dài và chứa thông tin nhạy cảm, vì vậy trong thao tác thực tế nên chọn option hẹp nhất đáp ứng mục đích.

### 1.1. Khi nào nên dùng?

`jinfo` có thể phù hợp trong các trường hợp sau:

1. Một runbook hoặc script cũ của đội vận hành đã dùng `jinfo` và môi trường hiện tại vẫn cung cấp công cụ này.
2. Cần kiểm tra nhanh flags hoặc system properties của một JVM đang chạy, chẳng hạn khi điều tra khác biệt giữa hai instance.
3. Cần đọc giá trị một flag cụ thể mà không muốn in toàn bộ cấu hình.
4. Cần bật/tắt tạm thời một flag có thể quản lý động trong một phiên xử lý sự cố đã được phê duyệt, và đã hiểu tác động của flag đó.
5. Đang học hoặc hỗ trợ một hệ thống legacy cần hiểu các lệnh `jinfo` trước khi chuyển runbook sang `jcmd`.

Nếu đang viết automation mới, chuẩn hóa CI/CD hoặc thiết kế quy trình diagnostics dài hạn, hãy ưu tiên `jcmd`. Công cụ này được Oracle khuyến nghị cho chẩn đoán JVM hiện đại và có nhiều diagnostic command hơn.

## 2. Những option chính của jinfo

Cú pháp trên Java SE 21:

~~~text
jinfo [option] pid
~~~

`pid` là process ID của JVM cần kiểm tra. `jinfo` nhận PID; không dùng tên main class làm đối số thay cho PID.

| Lệnh | Công dụng |
|---|---|
| `jinfo <pid>` | In VM flags và system properties |
| `jinfo -flags <pid>` | In các VM flags |
| `jinfo -sysprops <pid>` | In system properties dạng name-value |
| `jinfo -flag <name> <pid>` | Đọc giá trị một VM flag |
| `jinfo -flag +<name> <pid>` | Bật một Boolean VM flag |
| `jinfo -flag -<name> <pid>` | Tắt một Boolean VM flag |
| `jinfo -flag <name>=<value> <pid>` | Đặt giá trị cho VM flag nếu flag cho phép thay đổi |
| `jinfo -h` / `jinfo -help` | In trợ giúp |

### 2.1. Xem tất cả cấu hình

~~~bash
jinfo 12345
~~~

Output gồm các phần như:

~~~text
Java System Properties:
java.version=21.0.x
java.home=/opt/jdk-21
user.dir=/srv/orders
...

VM Flags:
-XX:InitialHeapSize=...
-XX:MaxHeapSize=...
-XX:+UseG1GC
...
~~~

Đây là ví dụ minh họa; tên, thứ tự và giá trị thực tế phụ thuộc JDK, JVM vendor và cách ứng dụng được khởi chạy.

Chỉ dùng lệnh không option khi thật sự cần cả hai nhóm thông tin. Một số system property có thể chứa URL, đường dẫn nội bộ, username hoặc thông tin cấu hình nhạy cảm.

### 2.2. Chỉ xem VM flags

~~~bash
jinfo -flags 12345
~~~

Dùng khi cần đối chiếu cấu hình heap, GC hoặc một số tùy chọn HotSpot đã được truyền vào JVM.

Lưu ý: output là những flag mà JVM báo cáo; nó không phải danh sách đầy đủ mọi flag mà JVM có thể hỗ trợ. Với HotSpot, `-XX` là nhóm tùy chọn phụ thuộc implementation và có thể thay đổi giữa các release.

### 2.3. Chỉ xem system properties

~~~bash
jinfo -sysprops 12345
~~~

Ví dụ lọc một số property sau khi lưu output:

~~~bash
jinfo -sysprops 12345 > jvm-properties.txt
grep -E '^(java.version|java.home|user.dir|app.mode)=' jvm-properties.txt
~~~

Trên Windows PowerShell:

~~~powershell
jinfo -sysprops 12345 |
    Select-String '^(java.version|java.home|user.dir|app.mode)='
~~~

Không nên đưa toàn bộ output vào log công khai. System properties có thể chứa endpoint nội bộ, đường dẫn file, cấu hình database hoặc dữ liệu mà tổ chức xem là bí mật.

### 2.4. Đọc một flag cụ thể

~~~bash
jinfo -flag MaxHeapSize 12345
jinfo -flag UseG1GC 12345
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

Cách này hữu ích khi chỉ cần xác nhận một cấu hình đang hoạt động. Ví dụ, `MaxHeapSize` giúp xem giới hạn heap tối đa theo byte; `UseG1GC` cho biết flag chọn G1 có bật hay không.

Tên và khả năng truy vấn của flag phụ thuộc HotSpot/JDK version. Nếu không chắc flag có tồn tại trong target JVM, kiểm tra tài liệu của đúng JDK hoặc dùng `jcmd <pid> VM.flags -all`.

## 3. Khi nào được thay đổi VM flag bằng jinfo?

`jinfo` hỗ trợ ba dạng thay đổi:

~~~bash
# Bật Boolean flag
jinfo -flag +HeapDumpOnOutOfMemoryError 12345

# Tắt Boolean flag
jinfo -flag -HeapDumpOnOutOfMemoryError 12345

# Đặt giá trị flag
jinfo -flag HeapDumpOnOutOfMemoryError=true 12345
~~~

Chỉ những flag có thể thay đổi khi JVM đang chạy mới chấp nhận thao tác này. Trong HotSpot, chúng thường được gọi là *manageable flags*. Flag chỉ có thể đặt lúc startup sẽ từ chối thay đổi.

### 3.1. Ví dụ: bật heap dump khi OutOfMemoryError

`HeapDumpOnOutOfMemoryError` là một Boolean flag có thể quản lý động. Có thể kiểm tra trạng thái hiện tại:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

Nếu output cho biết flag đang tắt, có thể bật trong một phiên xử lý sự cố:

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError 12345
~~~

Đọc lại để xác nhận:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

Khi flag được bật, JVM có thể tạo heap dump nếu xảy ra OutOfMemoryError sau đó. Theo mặc định, file dump được ghi trong working directory của process với tên dạng `java_pid<pid>.hprof`; có thể cấu hình đường dẫn bằng `-XX:HeapDumpPath` khi khởi chạy. Heap dump có thể rất lớn và chứa object, chuỗi, token hoặc dữ liệu người dùng trong bộ nhớ. Trước khi bật, cần xác định nơi file được ghi, quyền truy cập, dung lượng ổ đĩa và quy trình bảo vệ/xóa file.

Thay đổi qua `jinfo` chỉ tác động lên JVM hiện tại. Nó không sửa source code, file cấu hình khởi động hay cấu hình của lần chạy tiếp theo. Nếu muốn flag luôn được bật sau khi restart, hãy cập nhật tham số khởi chạy hoặc cấu hình deployment theo quy trình của dự án.

### 3.2. Flag nào không thể thay đổi?

Không phải mọi VM flag đều có thể đổi trong runtime. Ví dụ, kích thước heap tối đa thường phải xác định khi khởi chạy:

~~~bash
jinfo -flag MaxHeapSize=268435456 12345
~~~

Với JVM có `MaxHeapSize` không phải manageable flag, lệnh sẽ thất bại với thông báo tương tự:

~~~text
AttachOperationFailedException:
flag 'MaxHeapSize' cannot be changed
~~~

Đây là hành vi dự kiến: một flag không cho phép thay đổi runtime không thể được ép đổi bằng `jinfo`. Muốn thay đổi heap sizing, cần cấu hình `-Xmx` phù hợp và khởi động lại JVM trong cửa sổ triển khai đã được phê duyệt.

Không thử thay đổi flag production theo kiểu dò từng giá trị. Trước khi chạy lệnh ghi, xác nhận flag có thể quản lý động, hiểu tác động và có kế hoạch rollback.

## 4. jinfo hay jcmd?

Oracle JDK 21 khuyến nghị dùng `jcmd` thay cho `jinfo` trong chẩn đoán hiện đại. Các tác vụ đọc cấu hình và thay đổi một số flag có thể thực hiện bằng diagnostic command tương ứng.

| Mục đích | jinfo | jcmd được khuyến nghị |
|---|---|---|
| Đọc VM flags | `jinfo -flags <pid>` | `jcmd <pid> VM.flags` |
| Đọc tất cả flag được VM hỗ trợ | Không có option tương đương đầy đủ | `jcmd <pid> VM.flags -all` |
| Đọc system properties | `jinfo -sysprops <pid>` | `jcmd <pid> VM.system_properties` |
| Đọc một flag | `jinfo -flag <name> <pid>` | `jcmd <pid> VM.flags -all` rồi lọc flag |
| Đổi một manageable flag | `jinfo -flag <name>=<value> <pid>` | `jcmd <pid> VM.set_flag <name> <value>` |
| Xem phiên bản JVM | Không phải mục đích chính | `jcmd <pid> VM.version` |
| Xem uptime | Không phải mục đích chính | `jcmd <pid> VM.uptime` |
| Thread dump, heap info, JFR | Không phải công cụ phù hợp | Các command như `Thread.print`, `GC.heap_info`, `JFR.start` |

Ví dụ tương đương:

~~~bash
# Đọc flags
jcmd 12345 VM.flags

# Đọc toàn bộ system properties
jcmd 12345 VM.system_properties

# Liệt kê mọi flag được VM hỗ trợ
jcmd 12345 VM.flags -all

# Đổi một manageable flag
jcmd 12345 VM.set_flag HeapDumpOnOutOfMemoryError true
~~~

Dùng `jcmd <pid> help` để xem các diagnostic command có trên JVM đích. Tập lệnh khả dụng có thể khác giữa các JVM và phiên bản.

### 4.1. Vì sao nên ưu tiên jcmd?

- Được Oracle khuyến nghị thay cho các công cụ chẩn đoán cũ như `jinfo`.
- Có command riêng cho flags, system properties, heap, thread, class loading, logging và Flight Recorder.
- Có thể kiểm tra cú pháp và mức ảnh hưởng của command qua `help <command>`.
- Phù hợp hơn cho runbook và automation mới.
- Một giao diện thống nhất giúp giảm số công cụ legacy cần duy trì.

`jinfo` vẫn có thể hữu ích khi hỗ trợ hệ thống cũ hoặc khi một quy trình đã được kiểm chứng phụ thuộc vào nó. Không nên chọn nó chỉ vì tên lệnh ngắn hơn.

## 5. Ví dụ thực hành Java 17+: đọc cấu hình của JVM đang chạy

Tạo file `JinfoTarget.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class JinfoTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("jinfo target ready");

        new CountDownLatch(1).await();
    }
}
~~~

Biên dịch và chạy ở terminal thứ nhất:

~~~bash
javac --release 17 JinfoTarget.java

java -Xmx128m \
  -Dapp.mode=staging \
  -Dapp.region=ap-southeast-1 \
  JinfoTarget
~~~

Stdout có dạng:

~~~text
PID=12345
jinfo target ready
~~~

PID là giá trị do hệ điều hành cấp; hãy dùng PID thật mà chương trình in ra.

Ở terminal thứ hai, kiểm tra cấu hình:

~~~bash
jinfo -flags 12345
jinfo -sysprops 12345
jinfo -flag MaxHeapSize 12345
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

Trong output system properties, tìm các dòng như:

~~~text
app.mode=staging
app.region=ap-southeast-1
~~~

Với lệnh đọc flag, output có thể có dạng:

~~~text
-XX:MaxHeapSize=134217728
-XX:-HeapDumpOnOutOfMemoryError
~~~

Các giá trị minh họa ở đây tương ứng với ví dụ heap 128 MiB; giá trị thực tế có thể khác theo JDK và môi trường.

### 5.1. Bật flag rồi xác nhận

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError 12345
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

Output đọc lại phải thể hiện:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
~~~

Tắt lại sau khi kiểm thử:

~~~bash
jinfo -flag -HeapDumpOnOutOfMemoryError 12345
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

Output sau cùng phải thể hiện:

~~~text
-XX:-HeapDumpOnOutOfMemoryError
~~~

### 5.2. So sánh bằng jcmd

~~~bash
jcmd 12345 VM.flags
jcmd 12345 VM.system_properties
jcmd 12345 VM.flags -all
jcmd 12345 VM.set_flag HeapDumpOnOutOfMemoryError true
jcmd 12345 VM.set_flag HeapDumpOnOutOfMemoryError false
~~~

Kết thúc ví dụ bằng `Ctrl+C` ở terminal thứ nhất. Không cần tạo OutOfMemoryError thật để kiểm tra việc đọc/bật/tắt flag.

## 6. Khi JVM đã crash: dùng jhsdb jinfo

Cần phân biệt hai trường hợp:

- `jinfo <pid>` đọc cấu hình của một JVM đang chạy.
- `jhsdb jinfo` dùng Serviceability Agent để đọc thông tin từ core dump sau sự cố.

Ví dụ trên Linux:

~~~bash
jhsdb jinfo \
  --exe /opt/jdk-21/bin/java \
  --core /var/crash/core.19256
~~~

Đường dẫn executable phải khớp với binary đã tạo ra core dump. Nếu process được tạo qua JNI Invocation API, tên binary có thể không phải `java`; cần cung cấp đúng executable gốc.

Đọc core dump là thao tác postmortem. Nó không thay đổi flag của một JVM đang chạy và không thay thế công cụ phân tích core chuyên sâu. Core dump có thể chứa dữ liệu bộ nhớ nhạy cảm, nên phải giới hạn quyền đọc và thời gian lưu trữ.

## 7. Giới hạn và điều kiện cần biết

### 7.1. jinfo là công cụ experimental và unsupported

Tài liệu Oracle JDK 21 ghi rõ `jinfo` là công cụ experimental and unsupported. Nó có thể thay đổi hoặc không còn được cung cấp ở các bản JDK tương lai.

Do đó:

- Không xây dựng hệ thống production mới phụ thuộc vào output format của `jinfo`.
- Không giả định lệnh và flag giống nhau giữa mọi vendor/JDK.
- Ưu tiên `jcmd` trong runbook mới.
- Nếu phải giữ script cũ, pin JDK/toolchain, kiểm thử khi nâng phiên bản và có phương án chuyển đổi.

### 7.2. Cần chọn đúng process và quyền attach

`jinfo` cần PID của Java process. Có thể tìm process bằng:

~~~bash
jcmd -l
jps -l
ps -ef | grep '[j]ava'
~~~

Trên Windows PowerShell:

~~~powershell
Get-Process java
where.exe jinfo
~~~

Với process đang chạy, thực hiện attach cục bộ trên cùng máy và dưới danh tính có quyền truy cập phù hợp. Các yêu cầu OS, user, container và Attach API có thể ảnh hưởng tới kết quả.

Nếu PID đã kết thúc hoặc bị tái sử dụng, lệnh có thể thất bại hoặc nhắm nhầm process. Hãy xác minh PID, main class và thời điểm khởi chạy trước khi đọc hoặc thay đổi flag.

### 7.3. Điều kiện trên Windows

Oracle JDK 21 ghi chú rằng nếu `dbgeng.dll` không có trong môi trường Windows, có thể cần cài Debugging Tools for Windows để các công cụ này hoạt động. Biến môi trường `PATH` cần chứa vị trí `jvm.dll` được target process sử dụng hoặc vị trí tạo core dump.

Khi `jinfo` chạy được trên máy Linux nhưng lỗi trên Windows, hãy kiểm tra đúng JDK, kiến trúc, thư viện debug và PATH trước khi kết luận JVM bị lỗi.

### 7.4. Output có thể tiết lộ thông tin nhạy cảm

System properties và VM flags có thể tiết lộ:

- Đường dẫn cài đặt, thư mục làm việc và classpath.
- Endpoint, profile, region và tên môi trường.
- Các tham số `-D...` do ứng dụng truyền vào.
- Thông tin cấu hình có thể giúp người khác suy ra cấu trúc hạ tầng.

Không đưa output đầy đủ vào ticket công khai hoặc log build không giới hạn quyền. Chỉ trích phần cần thiết và che giá trị nhạy cảm.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `jinfo` không được nhận diện | JDK `bin` không nằm trong `PATH` hoặc chỉ cài JRE/runtime | Dùng đường dẫn `JAVA_HOME/bin/jinfo` hoặc JDK phù hợp |
| `Unable to open socket file` / attach failed | PID sai, process đã kết thúc hoặc quyền attach không phù hợp | Xác minh PID và danh tính người chạy tool |
| `flag 'MaxHeapSize' cannot be changed` | Flag không thể thay đổi trong runtime | Cấu hình lại tham số startup và restart theo kế hoạch |
| Không thấy property mong muốn | Sai tên property, property không được JVM cung cấp hoặc nhầm process | Kiểm tra PID và dùng `-sysprops` |
| Output có quá nhiều dòng | Dùng `jinfo <pid>` không option | Chuyển sang `-flags`, `-sysprops` hoặc `-flag <name>` |
| Tool không tương thích với target JVM | Dùng JDK tool khác release/vendor | Dùng tool phù hợp với JDK của process đích |
| Windows báo thiếu `dbgeng.dll` | Thiếu Debugging Tools for Windows | Cài thành phần debug phù hợp và kiểm tra PATH |
| Flag đổi xong nhưng restart lại mất | Thay đổi chỉ áp dụng cho JVM hiện tại | Cập nhật tham số khởi chạy/deployment config nếu muốn duy trì |

## 9. Quy trình chọn công cụ

Có thể quyết định theo nhu cầu:

~~~text
Cần đọc JVM flags hoặc system properties?
                 |
                 v
        Dùng jcmd trước
                 |
                 v
Có runbook legacy bắt buộc jinfo
hoặc cần tương thích công cụ cũ?
          /              \
        Có                Không
        |                  |
        v                  v
Dùng jinfo có kiểm soát   Tiếp tục jcmd
        |
        v
Có cần đổi flag runtime?
        |
        v
Xác nhận flag manageable,
đánh giá tác động và rollback
~~~

Nếu vấn đề là thread, heap, class loading, GC hoặc profiling, hãy chọn diagnostic command chuyên biệt của `jcmd` hoặc JDK Mission Control/Flight Recorder. `jinfo` chỉ cung cấp thông tin cấu hình và thay đổi một số flag; nó không phải profiler hay công cụ phân tích heap.

## 10. Checklist trước khi chạy jinfo

- [ ] Xác định đúng PID và main class của JVM.
- [ ] Kiểm tra `jinfo` thuộc JDK nào và target JVM dùng JDK nào.
- [ ] Ưu tiên `jcmd` nếu đang viết runbook hoặc automation mới.
- [ ] Chỉ dùng `-sysprops` hoặc lệnh không option khi thật sự cần toàn bộ output.
- [ ] Che hoặc bảo vệ system properties và VM flags có thông tin nhạy cảm.
- [ ] Trước khi thay đổi flag, xác nhận flag có thể quản lý động.
- [ ] Đánh giá tác động của flag và chuẩn bị rollback.
- [ ] Không kỳ vọng thay đổi runtime sẽ tồn tại sau khi JVM restart.
- [ ] Nếu cần phân tích core dump, dùng `jhsdb jinfo` với đúng executable và core file.
- [ ] Kiểm tra lại sau khi nâng JDK vì `jinfo` là công cụ unsupported.

## 11. Ghi nhớ

Dùng `jinfo` khi cần đọc nhanh VM flags/system properties của một JVM cũ, hỗ trợ runbook legacy hoặc tạm thời thay đổi một manageable VM flag trong một phiên xử lý có kiểm soát. Không dùng nó để thay đổi mọi tùy chọn JVM; các flag startup-only như `MaxHeapSize` không thể được thay đổi khi process đang chạy.

Với dự án mới, hãy ưu tiên `jcmd`: `VM.flags`, `VM.system_properties` và `VM.set_flag` bao phủ các tác vụ cấu hình phổ biến, trong khi `jcmd` còn hỗ trợ nhiều chẩn đoán khác. Nếu phân tích core dump, dùng `jhsdb jinfo` thay cho lệnh `jinfo` dành cho process đang chạy.

Tài liệu tham khảo:

- [The jinfo Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jinfo.html)
- [Diagnostic Tools — Java SE 21: jinfo and jcmd](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
- [The jcmd Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Java HotSpot VM Command-Line Options — Serviceability and heap dump options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)