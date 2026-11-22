# Kiểm tra tag cùng tùy chọn trên JVM đang dùng

Unified JVM Logging cung cấp một hệ thống log chung cho các thành phần của HotSpot JVM. Khi điều tra GC, class loading, safepoint, compiler hoặc một thành phần runtime khác, cần xác định **JVM đang chạy hỗ trợ tag, level, decorator và output option nào**. Danh sách thay đổi theo phiên bản, nhà cung cấp và bản build; không nên lấy danh sách tag từ máy khác rồi mặc định JVM đích cũng hỗ trợ.

Có hai câu hỏi riêng:

- **JVM binary hiện tại hỗ trợ gì?** Chạy `java -Xlog:help` bằng đúng launcher cần kiểm tra.
- **Một JVM process đang chạy hỗ trợ và đang cấu hình gì?** Dùng `jcmd <pid> VM.log list` và `jcmd <pid> help VM.log` để hỏi trực tiếp process đích.

`-Xlog:help` chỉ in thông tin rồi thoát; nó không bật log và không sửa cấu hình. `VM.log list` cũng chỉ đọc trạng thái hiện tại. Các lệnh `VM.log` có tham số thay đổi cấu hình là thao tác khác và cần cân nhắc trước khi chạy trên production.

## 1. Xác định đúng JVM cần kiểm tra

Trước khi đọc tag, xác định lệnh `java` đang trỏ đến runtime nào:

~~~bash
java -version
~~~

Trên Windows có thể kiểm tra đường dẫn được shell phân giải:

~~~powershell
Get-Command java
where.exe java
~~~

Trên Linux/macOS:

~~~bash
command -v java
which java
~~~

Nếu máy có nhiều JDK, `java -Xlog:help` chỉ kiểm tra binary được gọi bởi lệnh `java` hiện tại. Muốn kiểm tra một JDK cụ thể, gọi launcher bằng đường dẫn đầy đủ:

~~~bash
"$JAVA_HOME/bin/java" -Xlog:help
~~~

Trên Windows PowerShell:

~~~powershell
& "$env:JAVA_HOME\bin\java.exe" -Xlog:help
~~~

Lệnh này không đọc cấu hình của process đã chạy. Một service có thể được khởi động từ JDK khác hoặc chạy trong container khác. Khi cần kiểm tra process đang chạy, lấy PID và truy vấn trực tiếp bằng `jcmd`.

## 2. Kiểm tra tag, level và tùy chọn bằng -Xlog:help

Chạy:

~~~bash
java -Xlog:help
~~~

Kết quả mô tả cú pháp và các nhóm được runtime hiện tại hỗ trợ:

- **Log levels:** `off`, `trace`, `debug`, `info`, `warning`, `error`.
- **Log tags:** tên thành phần hoặc loại sự kiện, ví dụ `gc`, `heap`, `class`, `os`, `safepoint`, `thread`, `jit`.
- **Decorators:** metadata ở đầu mỗi dòng log, ví dụ `uptime`, `time`, `pid`, `tid`, `level`, `tags`.
- **Outputs:** `stdout`, `stderr` hoặc `file=<filename>`.
- **Output options:** ví dụ `filesize`, `filecount`, `foldmultilines`.
- **Logging mode:** runtime có thể liệt kê hỗ trợ asynchronous logging và các tùy chọn liên quan.

Ví dụ một phần output trên Zulu OpenJDK 24.0.2:

~~~text
Available log levels:
 off, trace, debug, info, warning, error

Available log decorators:
 time, utctime, uptime, timemillis, uptimemillis,
 timenanos, uptimenanos, hostname, pid, tid, level, tags

Available log outputs:
 stdout/stderr
 file=<filename>

Available log output options:
 foldmultilines=..
 filesize=..
 filecount=..
~~~

Danh sách tag thực tế dài hơn nhiều. Dùng toàn bộ output của `-Xlog:help` trên đúng runtime để tra cứu; các tag trong ví dụ chỉ minh họa, không phải danh sách cố định cho mọi JVM.

## 3. Phân biệt tag đơn, tag set và wildcard

Mỗi log message có một level và một **tag set**. Tag mô tả nội dung hoặc thành phần JVM liên quan đến message.

Cú pháp lựa chọn có dạng:

~~~text
tag1[+tag2...][*][=level][,...]
~~~

| Cú pháp | Ý nghĩa |
| --- | --- |
| `gc` | Chọn tag set chính xác chỉ gồm tag gc |
| `gc+heap` | Chọn tag set có cả gc và heap |
| `gc*` | Chọn các tag set có chứa gc, kể cả tổ hợp với tag khác |

Dấu `+` kết hợp các tag trong cùng một tag set; dấu phẩy phân tách nhiều lựa chọn độc lập.

Ví dụ:

~~~bash
# Chỉ message có tag set gc
java -Xlog:gc=info -version

# Message có đồng thời hai tag gc và heap
java -Xlog:gc+heap=debug -version

# Các tag set có chứa gc
java -Xlog:gc*=info -version

# Chọn hai nhóm độc lập
java -Xlog:gc=info,safepoint=info -version
~~~

Nếu không có wildcard, JVM chỉ khớp tag set chính xác. Vì vậy `gc+heap` không đồng nghĩa với “mọi message có tag gc hoặc heap”. Dùng `gc*` khi muốn bao phủ các tổ hợp chứa `gc`.

`all` là meta tag chọn tất cả tag set mà runtime cung cấp. Đây là lựa chọn rộng, có thể tạo lượng log rất lớn; không nên bật tùy tiện trên production.

## 4. Hiểu các log level

Các level hiện hành:

| Level | Mức chi tiết |
| --- | --- |
| `off` | Tắt log cho lựa chọn tương ứng |
| `error` | Lỗi |
| `warning` | Cảnh báo |
| `info` | Thông tin vận hành |
| `debug` | Chi tiết phục vụ chẩn đoán |
| `trace` | Chi tiết sâu nhất |

Khi chọn `=debug`, JVM ghi message ở mức debug và các mức ít chi tiết hơn như info, warning, error; message trace không được chọn. `=trace` cho lượng thông tin lớn nhất.

Ví dụ:

~~~bash
java -Xlog:gc=debug -version
~~~

Nếu tag set hợp lệ nhưng không có sự kiện tương ứng trong lần chạy, output có thể không xuất hiện. Điều đó không chứng minh tag không được hỗ trợ. Cần phân biệt:

1. Tag có nằm trong danh sách hỗ trợ hay không.
2. Tag set kết hợp có được runtime sử dụng hay không.
3. Có sự kiện ở level đã chọn trong khoảng thời gian quan sát hay không.

Không tăng lên `trace` nếu chưa cần; log quá chi tiết có thể tăng dung lượng, I/O và chi phí xử lý.

## 5. Kiểm tra decorator

Decorator bổ sung ngữ cảnh cho từng log message. Các tên thường gặp:

| Decorator | Nội dung |
| --- | --- |
| `time` | Thời gian dạng ngày/giờ |
| `utctime` | Thời gian UTC |
| `uptime` | Thời gian từ khi JVM khởi động |
| `uptimemillis` | Uptime theo mili giây |
| `pid` | Process ID |
| `tid` | Thread ID của JVM |
| `level` | Level của message |
| `tags` | Tag set của message |
| `hostname` | Hostname |

Ví dụ:

~~~bash
java -Xlog:gc=info:stdout:uptime,level,tags -version
~~~

Nếu cần đối chiếu log nhiều process, decorator `pid` hữu ích. Nếu cần biết message thuộc nhóm nào, giữ `tags`. Nếu cần xem thời gian tương đối từ lúc JVM khởi động, dùng `uptime`.

Có thể dùng `none` để không in decorator:

~~~bash
java -Xlog:gc=info:stdout:none -version
~~~

Chỉ chọn decorator có trong output của runtime đích; tên viết tắt có thể xuất hiện song song với tên đầy đủ.

## 6. Kiểm tra output và output option

Unified Logging hỗ trợ ba nhóm output chính:

- `stdout`: standard output.
- `stderr`: standard error.
- `file=<filename>`: ghi vào file.

Ví dụ ghi GC log vào file riêng, kèm PID và xoay file:

~~~bash
java -Xlog:gc*=info:file=gc-%p.log:time,level,tags:filecount=5,filesize=10M -jar app.jar
~~~

Trong ví dụ:

- `gc*=info` chọn các tag set chứa `gc` ở level info.
- `file=gc-%p.log` tạo file có PID trong tên.
- `time,level,tags` thêm thời gian, level và tag set.
- `filesize=10M` đặt kích thước mục tiêu cho mỗi file.
- `filecount=5` cấu hình số file luân phiên được giữ lại.

`filesize` là kích thước mục tiêu, không phải cam kết file sẽ dừng chính xác tại byte đó. Nếu đặt `filecount=0`, rotation bị tắt; file hiện có có thể bị ghi đè. Hãy kiểm tra thư mục đích và quyền ghi trước khi khởi động ứng dụng.

Một số output option khác như `foldmultilines=true` gộp log event nhiều dòng thành một dòng bằng cách escape newline. Chỉ bật khi consumer downstream cần định dạng một dòng và encoding tương thích.

## 7. Kiểm tra JVM process đang chạy bằng jcmd

`java -Xlog:help` kiểm tra launcher được gọi ở terminal. Muốn kiểm tra process đang chạy, dùng `jcmd`.

Trên cùng máy:

~~~bash
jcmd -l
~~~

Lệnh liệt kê các Java process mà công cụ có thể nhìn thấy, thường kèm PID và main class. Chọn đúng PID của ứng dụng, sau đó kiểm tra phiên bản:

~~~bash
jcmd <PID> VM.version
~~~

Liệt kê tag, level, decorator và cấu hình log hiện tại:

~~~bash
jcmd <PID> VM.log list
~~~

Xem cú pháp cùng các option mà command của process hỗ trợ:

~~~bash
jcmd <PID> help VM.log
~~~

`VM.log list` trả cả danh sách tag/level/decorator khả dụng của process đích và các output đang cấu hình, ví dụ:

~~~text
Available log levels: off, trace, debug, info, warning, error
Available log decorators: time, utctime, uptime, pid, tid, level, tags
Available log tags: ... gc, heap, os, safepoint, thread, ...
Log output configuration:
 #0: stdout all=warning uptime,level,tags foldmultilines=false
 #1: stderr all=off uptime,level,tags foldmultilines=false
~~~

Đây là output minh họa rút gọn. Tên tag, decorator và cấu hình output phụ thuộc process đích. Đọc cấu hình đang hoạt động ở phần `Log output configuration`; đừng nhầm danh sách hỗ trợ với những lựa chọn đang bật.

## 8. Thay đổi logging của process đang chạy

Sau khi đã xác nhận PID, tag và cú pháp, có thể thay đổi cấu hình Unified Logging mà không khởi động lại JVM bằng diagnostic command `VM.log`.

Ví dụ bật log `gc+heap` ở debug, ghi ra stdout với ba decorator:

~~~bash
jcmd <PID> VM.log output=stdout what=gc+heap=debug decorators=uptime,level,tags
~~~

Đọc lại cấu hình sau khi thay đổi:

~~~bash
jcmd <PID> VM.log list
~~~

Các option của `VM.log` gồm:

| Option | Mục đích |
| --- | --- |
| `output` | Chọn tên hoặc chỉ số output cần cấu hình |
| `what` | Chọn tag set và level |
| `decorators` | Chọn decorator |
| `output_options` | Cấu hình option cho output |
| `list` | Liệt kê cấu hình hiện tại |
| `rotate` | Yêu cầu xoay các log output |
| `disable` | Tắt logging và xóa cấu hình |

`VM.log list` và `help VM.log` là thao tác kiểm tra. Lệnh `VM.log` có `what`, `output` hoặc `disable` có thể thay đổi cấu hình của process đang phục vụ người dùng. Ghi lại cấu hình trước khi đổi và xác minh lại sau khi đổi.

Không dùng `disable=true` như một lệnh “dọn log” chung: nó tắt toàn bộ logging và xóa cả cấu hình mặc định cho warning/error. Chỉ thực hiện khi đã hiểu tác động và có kế hoạch khôi phục cấu hình.

## 9. Ví dụ Java hoàn chỉnh: giữ một JVM sống để kiểm tra bằng jcmd

Chương trình sau in PID của chính nó rồi chờ tối đa 60 giây. Trong thời gian đó, mở terminal thứ hai để chạy `jcmd` trên PID được in ra. Đây là chương trình kiểm thử, không thay đổi cấu hình JVM nào khi tự khởi động.

Tạo tệp `LoggingProbe.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class LoggingProbe {
    public static void main(String[] args) throws InterruptedException {
        long pid = ProcessHandle.current().pid();
        System.out.println("READY pid=" + pid);
        System.out.flush();

        CountDownLatch stop = new CountDownLatch(1);
        stop.await(60, TimeUnit.SECONDS);
    }
}
~~~

Biên dịch và chạy trong terminal thứ nhất:

~~~bash
javac --release 17 -Xlint:all LoggingProbe.java
java LoggingProbe
~~~

Ví dụ stdout:

~~~text
READY pid=82956
~~~

PID thay đổi theo mỗi lần chạy. Trong terminal thứ hai, thay `<PID>` bằng số vừa in:

~~~bash
jcmd <PID> VM.version
jcmd <PID> help VM.log
jcmd <PID> VM.log list
~~~

Sau khi xem cấu hình ban đầu, có thể thử cấu hình runtime trên chính process kiểm thử:

~~~bash
jcmd <PID> VM.log output=stdout what=gc+heap=debug decorators=uptime,level,tags
jcmd <PID> GC.run
~~~

Nếu tag set được hỗ trợ và output được bật, stdout của process kiểm thử sẽ có các dòng dạng:

~~~text
[0.652s][debug][gc,heap] GC(0) Heap before GC invocations=0 (full 0):
[0.660s][info ][gc,heap] GC(0) Eden regions: 1->0(2)
[0.661s][debug][gc,heap] GC(0) Heap after GC invocations=1 (full 1):
~~~

Giá trị uptime, số GC và số liệu heap thay đổi theo runtime. `GC.run` yêu cầu JVM thực hiện GC; chỉ dùng trong chương trình kiểm thử hoặc khi đã hiểu tác động trên process đích. Không kích hoạt GC chỉ để kiểm tra logging trên production.

Chương trình tự kết thúc sau 60 giây. Có thể bỏ qua bước `GC.run` nếu chỉ cần xem danh sách tag và cấu hình.

## 10. Đọc kết quả đúng cách

Khi kiểm tra một cấu hình, đi theo thứ tự:

1. `java -version` để xác định launcher.
2. `java -Xlog:help` để xem tag, level, decorator, output và output option của launcher đó.
3. `jcmd -l` để tìm process cần điều tra.
4. `jcmd <PID> VM.version` để xác nhận runtime của process đích.
5. `jcmd <PID> VM.log list` để xem hỗ trợ và cấu hình đang áp dụng.
6. `jcmd <PID> help VM.log` để xác nhận option runtime có sẵn.
7. Chọn tag set và level hẹp nhất đáp ứng câu hỏi chẩn đoán.
8. Nếu đổi cấu hình runtime, đọc lại `VM.log list` và xác nhận output thực tế.
9. Sau khi điều tra xong, khôi phục cấu hình theo trạng thái đã ghi nhận trước khi thay đổi.

Nếu `jcmd -l` không liệt kê process chạy trong container riêng, hãy kiểm tra PID trong đúng container/process namespace và chạy công cụ tại môi trường có thể attach tới JVM đó.

## 11. Lỗi thường gặp và cách xử lý

- **Tag có trên máy A nhưng không có trên máy B:** kiểm tra `-Xlog:help` trên từng runtime; danh sách tag phụ thuộc phiên bản và build.
- **Dùng `java -Xlog:help` nhưng vẫn không biết process service đang dùng gì:** truy vấn PID thực bằng `jcmd <PID> VM.log list`.
- **Không tìm thấy PID:** xác nhận process còn sống, đúng máy/container và công cụ nhìn thấy cùng PID namespace.
- **Không attach được:** kiểm tra quyền user/group, môi trường chạy, attach listener/chính sách bảo mật và khả năng hỗ trợ diagnostic command của JVM.
- **`VM.log` không có trong process:** xác nhận runtime có hỗ trợ Unified Logging và diagnostic command này; dùng `jcmd <PID> help` để xem danh sách command thực tế.
- **Cấu hình hợp lệ nhưng không thấy log:** kiểm tra level, tag set chính xác, wildcard, output, thời điểm có sự kiện và cấu hình khác đang ghi đè cùng output.
- **Dùng `gc+heap` nhưng chỉ muốn tag gc:** dấu `+` yêu cầu message mang cả hai tag.
- **Dùng dấu phẩy như phép kết hợp tag:** dấu phẩy tạo các lựa chọn riêng; dùng `+` cho tag set kết hợp.
- **Bật `all` hoặc `trace` trên production:** lượng log có thể tăng mạnh; thu hẹp tag/level và chọn output có giới hạn.
- **File log tăng không kiểm soát:** cấu hình `filesize` và `filecount`; kiểm tra quyền ghi và dung lượng đĩa.
- **Cho rằng danh sách tag là danh sách mọi tổ hợp hợp lệ:** `-Xlog:help` liệt kê tag; lựa chọn thực tế còn phụ thuộc tag set được các log site sử dụng.
- **Dùng output của JDK khác làm chuẩn:** luôn kiểm tra runtime thực tế, nhất là khi ứng dụng chạy bằng container image hoặc JDK vendor khác.

## 12. Quy trình vận hành an toàn

- Ghi nhận vendor, version, build và đường dẫn binary.
- Lấy danh sách tag/option từ đúng JVM cần kiểm tra.
- Đọc cấu hình đang hoạt động trước khi thay đổi.
- Bắt đầu bằng level info hoặc debug trên một tag set hẹp.
- Chọn stdout/stderr hoặc file theo hệ thống thu thập log.
- Khi ghi file, cấu hình rotation và giới hạn dung lượng.
- Theo dõi lượng log, I/O và tác động hiệu năng.
- Chỉ thay đổi process đích sau khi xác nhận PID và hiểu tác động của lệnh.
- Ghi lại cấu hình ban đầu để có thể khôi phục.
- Không dùng danh sách tag tĩnh từ một máy làm cam kết cho mọi môi trường.

## Tài liệu tham khảo

- [Java Launcher — Unified Logging (-Xlog), Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [jcmd — Diagnostic Commands, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html)
- [JEP 158: Unified JVM Logging](https://openjdk.org/jeps/158)

`java -Xlog:help` là cách nhanh để kiểm tra khả năng logging của đúng JVM binary; `jcmd <PID> VM.log list` là cách kiểm tra runtime và cấu hình của process đang chạy. Kết hợp hai bước này giúp chọn tag, level, decorator và output option theo đúng môi trường, đồng thời tránh bật log không được hỗ trợ hoặc tạo lượng log vượt nhu cầu chẩn đoán.