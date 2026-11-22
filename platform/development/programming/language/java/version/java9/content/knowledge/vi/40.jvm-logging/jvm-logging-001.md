# Cú pháp -Xlog của hệ thống ghi nhật ký thống nhất

`-Xlog` là tùy chọn của HotSpot JVM để cấu hình **Unified JVM Logging**: hệ thống ghi log chung cho các thành phần nội bộ của máy ảo, như garbage collection (GC), class loading, class initialization, safepoint, JIT và hoạt động của hệ điều hành. Unified Logging được đưa vào JDK 9 qua JEP 158 và vẫn là cơ chế cấu hình log JVM hiện hành.

`-Xlog` là tùy chọn ở tầng JVM, được truyền khi khởi chạy process. Nó không thay thế `java.util.logging`, SLF4J hay logger nghiệp vụ trong ứng dụng. Một ứng dụng có thể đồng thời dùng logger riêng cho thông điệp nghiệp vụ và `-Xlog` để quan sát hoạt động nội bộ của JVM.

## Mục tiêu

- Hiểu mục đích và phạm vi của Unified JVM Logging.
- Đọc đúng cấu trúc tùy chọn `-Xlog`.
- Chọn tag, tag combination, wildcard và log level.
- Định tuyến log tới stdout, stderr hoặc tệp.
- Chọn decorators để bổ sung thời gian, PID, thread ID, level và tags.
- Cấu hình file rotation bằng `filesize` và `filecount`.
- Kết hợp nhiều lựa chọn log và hiểu thứ tự cấu hình.
- Dùng `-Xlog:help` để tra cứu tag và cú pháp trên runtime hiện tại.
- Kiểm tra hoặc thay đổi cấu hình đang chạy bằng `jcmd VM.log`.
- Phân biệt JVM logging với application logging và tránh ghi quá nhiều dữ liệu.

## 1. Unified JVM Logging là gì?

Trước Unified Logging, các thành phần JVM có những cơ chế và tùy chọn ghi log riêng. JDK 9 đưa vào một framework chung để các thành phần JVM dùng cùng mô hình tag, level, output và decorators.

Unified Logging cho phép người vận hành:

- Chọn đúng nhóm hoạt động cần quan sát, ví dụ `gc`, `class+load` hoặc `safepoint`.
- Tăng hoặc giảm mức chi tiết mà không phải bật toàn bộ log.
- Gửi log tới console hoặc tệp.
- Thêm metadata như thời gian chạy, PID, thread ID và tag set.
- Giới hạn kích thước file và giữ một số generation để tránh tăng dung lượng vô hạn.
- Thay đổi cấu hình ở runtime qua diagnostic command khi JVM hỗ trợ.

Đây là cơ chế phục vụ chẩn đoán và vận hành JVM. Log level cao như `debug` hoặc `trace` có thể tạo lượng dữ liệu lớn; chỉ bật trong phạm vi cần thiết và theo dõi tác động I/O.

## 2. Cấu trúc tổng quát của -Xlog

Cú pháp tổng quát:

~~~text
-Xlog[:what[:output[:decorators[:output-options]]]]
~~~

Các phần:

| Phần | Vai trò |
| --- | --- |
| `what` | Chọn tag hoặc tổ hợp tag, kèm log level |
| `output` | Chọn `stdout`, `stderr` hoặc `file=filename` |
| `decorators` | Chọn metadata được thêm trước mỗi log message |
| `output-options` | Cấu hình file rotation và các tùy chọn đầu ra được runtime hỗ trợ |

Ví dụ:

~~~text
-Xlog:gc*=info:file=logs/gc-%p.log:uptimemillis,pid,level,tags:filecount=5,filesize=10M
~~~

Đọc từ trái sang phải:

1. `gc*`: chọn các tag set có chứa tag `gc`.
2. `=info`: ghi các mức `info` và nghiêm trọng hơn.
3. `file=logs/gc-%p.log`: ghi vào file; `%p` được thay bằng process ID.
4. `uptimemillis,pid,level,tags`: thêm thời gian từ lúc JVM khởi động, PID, level và tag set.
5. `filecount=5,filesize=10M`: xoay file theo ngưỡng dung lượng và giữ số generation đã cấu hình.

Các dấu `:` phân tách phần của cấu hình; dấu `,` phân tách nhiều tag selection hoặc nhiều output option tùy vị trí. Vì vậy cần giữ đúng thứ tự phần tử.

## 3. Tag và tag selection

Mỗi log message của JVM gắn với một tag set. Tag mô tả thành phần hoặc chủ đề phát sinh log. Một số tag thường gặp:

| Tag | Nội dung thường quan sát |
| --- | --- |
| `gc` | Garbage collection |
| `safepoint` | Safepoint và thời gian dừng thread |
| `class` | Class loading, initialization, resolution |
| `jit` | Hoạt động biên dịch JIT |
| `os` | Tương tác với hệ điều hành |
| `container` | Thông tin môi trường container trên runtime/platform hỗ trợ |
| `exceptions` | Exception ở tầng JVM |
| `metaspace` | Hoạt động liên quan metaspace trên runtime có tag này |

Danh sách tag không cố định cho mọi JVM build hoặc mọi phiên bản. Hãy dùng `java -Xlog:help` trên đúng runtime để xem tag set có sẵn.

### 3.1. Dấu cộng (+): kết hợp tag

Dấu `+` yêu cầu log message có tổ hợp tag tương ứng:

~~~text
-Xlog:gc+heap=debug
~~~

Selection này nhắm tới tag set `gc` và `heap` cùng xuất hiện. Không có wildcard thì việc match là chính xác với tổ hợp tag được chỉ định; một message chỉ có `gc` sẽ không tự động khớp `gc+heap`.

Ví dụ khác:

~~~text
-Xlog:class+load=info
-Xlog:class+init=info
-Xlog:gc+ref=debug
~~~

### 3.2. Dấu phẩy (,): nhiều selection

Dấu phẩy ngăn cách các selection độc lập:

~~~text
-Xlog:gc=info,safepoint=info
~~~

Selection trên yêu cầu log message thuộc `gc` hoặc `safepoint` ở mức `info` trở lên. Một message được gắn cả hai tag không được coi là một selection `gc+safepoint`; nếu muốn yêu cầu cả hai tag cùng có mặt, dùng dấu `+`.

### 3.3. Wildcard (*)

Wildcard sau tag hoặc tổ hợp tag mở rộng match tới các tag set chứa ít nhất những tag đã nêu:

~~~text
-Xlog:gc*=info
-Xlog:gc+heap*=debug
~~~

`gc*=info` bao gồm nhiều tag set có `gc`, chẳng hạn các nhóm GC chi tiết. `gc+heap*=debug` bao gồm tag set có cả `gc` và `heap`, cùng các tag bổ sung khác.

Không dùng wildcard rộng hơn mức cần thiết trong production nếu mục tiêu chỉ là một nhóm log nhỏ; nhiều tag set có thể làm lượng log tăng nhanh.

## 4. Log level

Unified Logging có các level sau, từ ít chi tiết tới chi tiết hơn:

| Level | Ý nghĩa |
| --- | --- |
| `off` | Tắt selection tương ứng |
| `error` | Lỗi |
| `warning` | Cảnh báo |
| `info` | Thông tin vận hành |
| `debug` | Thông tin chẩn đoán chi tiết |
| `trace` | Mức chi tiết cao nhất trong các level chuẩn |

Ví dụ:

~~~text
-Xlog:gc=info
-Xlog:gc=debug
-Xlog:gc=trace
~~~

Khi chọn `debug`, các message `debug` và mức nghiêm trọng hơn như `info`, `warning`, `error` được ghi. `trace` mở rộng thêm những message chi tiết hơn. Chọn level thấp nhất vẫn đủ trả lời câu hỏi chẩn đoán để giảm lượng log.

`off` có thể dùng để loại một selection khỏi cấu hình tổng hợp, ví dụ:

~~~text
-Xlog:gc*=info,safepoint*=off
~~~

Selection này bật log GC ở mức `info` và tắt các tag set có chứa `safepoint`.

## 5. Chọn nơi nhận log

`output` hỗ trợ ba kiểu chính:

| Output | Đích |
| --- | --- |
| `stdout` | Standard output của process |
| `stderr` | Standard error của process |
| `file=filename` | Tệp log do JVM mở và quản lý |

Nếu bỏ phần output trong selection, mặc định output là stdout. Trong cấu hình vận hành, nên chỉ rõ output để tránh hiểu nhầm giữa log JVM và output của ứng dụng.

### 5.1. Ghi ra stdout

~~~text
-Xlog:gc=info:stdout:uptime,level,tags
~~~

Phù hợp khi container runtime, process supervisor hoặc hệ thống thu thập log đã đọc stdout của process. JVM log và `System.out` của ứng dụng có thể cùng xuất hiện trong stream này.

### 5.2. Ghi ra stderr

~~~text
-Xlog:class+load=info:stderr:time,level,tags
~~~

Phù hợp khi hệ thống vận hành thu thập stderr riêng. JVM log trên stderr vẫn có thể xuất hiện cùng stack trace hoặc thông báo lỗi khác của process.

### 5.3. Ghi ra file

~~~text
-Xlog:gc*=info:file=logs/gc.log:uptime,level,tags
~~~

Thư mục cha của file phải tồn tại và user chạy JVM phải có quyền ghi. Đường dẫn tương đối được tính từ working directory của process. Trong môi trường service hoặc container, nên dùng đường dẫn ổn định và có chính sách lưu trữ.

## 6. Decorators

Decorator là metadata được đặt trước nội dung log. Có thể chọn một hoặc nhiều decorator, phân tách bằng dấu phẩy.

| Decorator | Ý nghĩa |
| --- | --- |
| `time` | Ngày giờ hiện tại theo ISO-8601 |
| `utctime` | Thời gian UTC |
| `uptime` | Thời gian từ khi JVM khởi động, tính theo giây |
| `timemillis` | Giá trị tương ứng `System.currentTimeMillis()` |
| `uptimemillis` | Millisecond từ khi JVM khởi động |
| `timenanos` | Giá trị tương ứng `System.nanoTime()` |
| `uptimenanos` | Nanosecond từ khi JVM khởi động |
| `hostname` | Host name |
| `pid` | Process ID của JVM |
| `tid` | Thread ID |
| `level` | Log level |
| `tags` | Tag set của log message |
| `none` | Không thêm decorator |

Ví dụ:

~~~text
-Xlog:gc=info:stdout:time,uptime,pid,tid,level,tags
~~~

Log có thể có dạng:

~~~text
[2026-11-06T10:15:30.120+0000][12.345s][4321][27][info][gc] GC event
~~~

Đây là ví dụ minh họa định dạng; timestamp, PID, thread ID, level và message thực tế phụ thuộc lần chạy.

Nếu bỏ phần decorators, runtime dùng bộ mặc định của nó; thường gồm `uptime`, `level` và `tags`. Có thể chỉ định `none` khi cần output gọn cho parser hoặc pipeline thu thập.

## 7. Ghi file và log rotation

Unified Logging có thể tự xoay file theo dung lượng và số lượng file generation. Hai output option quan trọng:

| Option | Ý nghĩa |
| --- | --- |
| `filesize=10M` | Kích thước mục tiêu mỗi file; hỗ trợ hậu tố K, M, G |
| `filecount=5` | Số file generation được giữ trong rotation |

Ví dụ:

~~~text
-Xlog:gc*=info:file=logs/gc-%p.log:uptimemillis,pid,level,tags:filecount=5,filesize=10M
~~~

JVM sẽ ghi log vào file có tên chứa PID, giới hạn mục tiêu khoảng 10 MB mỗi file và quản lý tối đa số generation được cấu hình. Kích thước thực tế không được bảo đảm tuyệt đối bằng đúng ngưỡng vì rotation được thực hiện tại các ranh giới ghi log.

`%p` trong tên file được thay bằng PID; `%t` có thể dùng để đưa timestamp lúc JVM khởi động vào tên file. Những placeholder và output option có thể thay đổi theo runtime; xác nhận bằng `-Xlog:help`.

Đặt `filecount=0` sẽ tắt rotation. Khi đó file hiện có có thể bị ghi đè lúc JVM khởi chạy; chỉ dùng khi đã kiểm soát rõ vòng đời file.

### 7.1. Ví dụ chọn file theo process và rotation

~~~text
-Xlog:gc=debug:file=logs/gc-%p.log:uptime,level,tags:filecount=5,filesize=20M
~~~

Đây là cấu hình hữu ích khi nhiều JVM chạy trên cùng host hoặc cùng thư mục log. PID giúp phân biệt file theo process; rotation giới hạn dung lượng lưu trữ.

## 8. Các cấu hình thực tế thường dùng

### 8.1. Theo dõi GC ở mức thông tin

~~~text
-Xlog:gc=info:stdout:uptime,level,tags
~~~

Dùng khi cần xem các sự kiện GC chính mà không thu thập toàn bộ chi tiết nội bộ.

### 8.2. Theo dõi nhiều nhóm GC

~~~text
-Xlog:gc*=info:file=logs/gc-%p.log:uptimemillis,pid,level,tags:filecount=5,filesize=10M
~~~

Wildcard cho phép quan sát nhiều tag set liên quan GC. File rotation giúp kiểm soát dung lượng.

### 8.3. Quan sát safepoint cùng GC

~~~text
-Xlog:gc=info,safepoint=info:stdout:uptime,level,tags
~~~

Hữu ích khi điều tra thời gian dừng hoặc hoạt động safepoint cùng với sự kiện GC.

### 8.4. Theo dõi class loading

~~~text
-Xlog:class+load=info:stderr:time,level,tags
~~~

Dùng để tìm hiểu class được nạp trong runtime và hỗ trợ điều tra classpath/class loader. Lượng log có thể lớn ở ứng dụng nhiều dependency.

### 8.5. Theo dõi class initialization

~~~text
-Xlog:class+init=info:file=logs/class-init.log:uptimemillis,pid:filecount=3,filesize=5M
~~~

Phù hợp khi điều tra thời điểm khởi tạo class và thứ tự khởi động.

### 8.6. Theo dõi container

~~~text
-Xlog:os+container=trace:stderr:uptime,level,tags
~~~

Tag set này hữu ích trên runtime/platform có hỗ trợ container logging. Hãy xác nhận tag bằng `-Xlog:help` trên máy đích.

## 9. Nhiều selection và nhiều -Xlog option

Một cấu hình có thể chứa nhiều selection cách nhau bằng dấu phẩy:

~~~text
-Xlog:gc=info,safepoint=info:stdout:uptime,level,tags
~~~

Cũng có thể truyền nhiều `-Xlog` option trong command line để cấu hình các output khác nhau:

~~~text
java -Xlog:gc=info:file=logs/gc.log:uptime,level,tags -Xlog:class+load=info:file=logs/class-load.log:uptime,level,tags com.example.Main
~~~

Các option được xử lý theo thứ tự trên command line. Khi nhiều cấu hình tác động cùng một output, cấu hình xuất hiện sau có thể thay thế cấu hình trước cho output đó. Vì vậy, hãy tránh lặp cấu hình cùng output nếu không có chủ đích.

### 9.1. Tắt cấu hình hiện có rồi bật một nhóm cụ thể

~~~text
-Xlog:disable -Xlog:safepoint=trace:file=logs/safepoint.log:uptime,level,tags
~~~

`-Xlog:disable` xóa cấu hình logging hiện có, bao gồm cấu hình mặc định cho warning/error. Selection theo sau sẽ bật lại nhóm log được chỉ định. Thứ tự này có ý nghĩa: đặt `-Xlog:disable` trước các selection mà bạn muốn giữ.

Không tắt toàn bộ cấu hình nếu mục tiêu chỉ là bổ sung thêm một nhóm log. Chỉ dùng khi muốn kiểm soát lại toàn bộ log output của JVM.

## 10. Tra cứu cấu hình trên runtime đang chạy

Tag set, decorator và một số output option có thể khác nhau theo JDK version, build hoặc JVM implementation. Lệnh tra cứu quan trọng nhất là:

~~~text
java -Xlog:help
~~~

Lệnh này in cú pháp, level, decorator, tag đang hỗ trợ và các ví dụ. Hãy chạy trên chính runtime sẽ dùng trong production; không lấy danh sách tag từ một phiên bản khác rồi giả định mọi tag đều có mặt.

Để kiểm tra JVM options:

~~~text
java -version
java -Xlog:help
~~~

`-Xlog` là tùy chọn mở rộng của HotSpot JVM. Nếu ứng dụng chạy trên JVM implementation khác, cần kiểm tra tài liệu của implementation đó thay vì giả định tùy chọn này được hỗ trợ.

## 11. Thay đổi cấu hình logging lúc JVM đang chạy

Unified Logging có thể được điều khiển bằng diagnostic command `VM.log` qua công cụ `jcmd` trên các JVM hỗ trợ.

Liệt kê process Java:

~~~text
jcmd -l
~~~

Xem cấu hình logging hiện tại:

~~~text
jcmd <pid> VM.log list=true
~~~

`VM.log` có thể liệt kê, thêm hoặc thay đổi cấu hình output, tag selection, decorators và output options; nó cũng hỗ trợ rotate các output. Kiểm tra cú pháp theo đúng runtime bằng:

~~~text
jcmd <pid> help VM.log
~~~

Thông thường `jcmd` cần chạy trên cùng máy với JVM đích và bằng user có quyền phù hợp. Chỉ thay đổi cấu hình của process mà bạn được phép quản trị.

## 12. Ví dụ hoàn chỉnh chạy trên Java 9+

Ví dụ tạo một nested class, sau đó in một dòng ra stdout và một dòng ra stderr. JVM log được định tuyến ra file riêng, nhờ vậy có thể quan sát sự khác nhau giữa log nội bộ JVM và output ứng dụng.

**Tệp:** `XlogSyntaxDemo.java`

~~~java
public class XlogSyntaxDemo {
    static final class Sample {
    }

    public static void main(String[] args) {
        new Sample();
        System.out.println("application stdout");
        System.err.println("application stderr");
    }
}
~~~

Biên dịch source tương thích Java 9:

~~~text
javac --release 9 XlogSyntaxDemo.java
~~~

Tạo thư mục log trước khi khởi chạy:

~~~text
mkdir logs
~~~

Chạy và định tuyến class initialization log tới file có rotation:

~~~text
java -Xlog:class+init=info:file=logs/class-init-%p.log:uptimemillis,pid:filecount=3,filesize=1M XlogSyntaxDemo
~~~

Output ứng dụng trên stdout:

~~~text
application stdout
~~~

Output ứng dụng trên stderr:

~~~text
application stderr
~~~

File `logs/class-init-<pid>.log` chứa các dòng log JVM về class loading/initialization và thông tin runtime. Ví dụ một số dòng có thể có dạng:

~~~text
[31ms][7280] Start class verification for: XlogSyntaxDemo$Sample
[31ms][7280] End class verification for: XlogSyntaxDemo$Sample
~~~

Thời gian, PID và số dòng phụ thuộc lần chạy. Ví dụ được kiểm tra trên OpenJDK 24.0.2; source biên dịch với `javac --release 9`. Cú pháp `-Xlog` có từ Java 9, còn danh sách tag và tùy chọn được hỗ trợ cần kiểm tra bằng `-Xlog:help` trên JDK đích.

## 13. JVM logging khác application logging

`-Xlog` ghi các sự kiện của JVM. Nó không tự động ghi các lời gọi `Logger.info()` của ứng dụng.

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Theo dõi GC, safepoint, class loading, JIT | Unified JVM Logging bằng `-Xlog` |
| Ghi thông điệp nghiệp vụ, request ID, user action | Logging API/framework trong ứng dụng |
| Định tuyến log ứng dụng tới console hoặc file | Handler/backend của application logging |
| Thu thập log process trong container | stdout/stderr hoặc agent/runtime logging collector |

Ứng dụng có thể dùng cả hai. Nên phân biệt nguồn log khi thu thập để không nhầm JVM event với business event.

## 14. Tác động hiệu năng và vận hành

- Log ở `debug` hoặc `trace` có thể tạo nhiều dữ liệu và tăng I/O.
- Ghi ra file cần quyền ghi, dung lượng đĩa và chính sách rotation.
- Ghi ra stdout/stderr có thể chịu backpressure từ collector hoặc process supervisor.
- Dùng tag selection hẹp để chỉ thu thập thông tin cần thiết.
- Chọn decorator theo mục tiêu điều tra; PID và thread ID hữu ích khi nhiều process/thread.
- Không để file rotation bị tắt ngoài ý muốn; `filecount=0` có thể làm file cũ bị ghi đè.
- Không để log JVM tràn vào cùng một file ứng dụng nếu không có quy ước phân loại.
- Sau khi điều tra xong, giảm level hoặc bỏ cấu hình chẩn đoán không còn cần thiết.

## 15. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không có log mong đợi | Tag hoặc level không match | Kiểm tra tag bằng `-Xlog:help`; tăng level khi thật sự cần |
| Chỉ bật `gc` nhưng thiếu log chi tiết | Selection `gc` không bao phủ mọi tag set chi tiết | Dùng `gc*` hoặc tổ hợp tag cụ thể phù hợp |
| Dùng `+` khi muốn chọn một trong hai tag | `+` yêu cầu tổ hợp tag | Dùng nhiều selection phân tách bằng dấu phẩy |
| Log ra sai stream | Output được bỏ qua hoặc ghi nhầm `stdout`/`stderr` | Chỉ rõ output trong cấu hình |
| Không tạo được file log | Thư mục chưa tồn tại hoặc không có quyền ghi | Tạo thư mục trước khi JVM khởi động và kiểm tra quyền |
| File log tăng quá lớn | Không cấu hình rotation phù hợp | Dùng `filesize` và `filecount` |
| Mất file cũ sau khi khởi chạy | `filecount=0` hoặc cấu hình không rotation | Đặt số generation phù hợp và kiểm tra file pattern |
| Log bị thiếu metadata | Decorator bị bỏ hoặc chọn `none` | Chọn `uptime`, `level`, `tags`, `pid` hoặc `tid` theo nhu cầu |
| Cấu hình mới ghi đè cấu hình trước | Nhiều `-Xlog` tác động cùng output theo thứ tự | Hợp nhất selection hoặc dùng output riêng |
| `jcmd VM.log` không kết nối được | PID sai, user không đủ quyền hoặc process khác môi trường | Kiểm tra `jcmd -l`, quyền và runtime đích |
| Dùng tag không tồn tại trên JDK đích | Danh sách tag khác theo version/build | Chạy `java -Xlog:help` ngay trên runtime đích |
| Nghĩ `-Xlog` ghi application logger | Nhầm JVM logging với application logging | Dùng JUL/SLF4J/backend cho log nghiệp vụ |

## 16. Quy tắc thực hành

1. Bắt đầu bằng câu hỏi cần chẩn đoán, rồi chọn tag tương ứng.
2. Dùng `-Xlog:help` để xác nhận tag, level và decorator trên đúng runtime.
3. Chỉ rõ `what`, output và decorators trong cấu hình vận hành.
4. Dùng `+` để yêu cầu tag kết hợp; dùng dấu phẩy để chọn nhiều selection; dùng `*` khi cần match các tag set mở rộng.
5. Bật `debug` hoặc `trace` trong phạm vi cần thiết và theo dõi lượng log.
6. Dùng stdout/stderr khi nền tảng thu thập process streams; dùng file khi cần quản lý file log riêng.
7. Cấu hình `filesize` và `filecount` để kiểm soát file rotation.
8. Đặt thư mục log và quyền ghi trước khi khởi động JVM.
9. Dùng PID trong tên file khi có nhiều JVM cùng ghi log.
10. Dùng `jcmd <pid> VM.log list=true` để kiểm tra cấu hình runtime.
11. Tắt hoặc giảm log chẩn đoán sau khi hoàn tất điều tra.
12. Phân biệt JVM log với application log.
13. Chỉ dựa vào cú pháp và tag được runtime hiện tại xác nhận; không giả định mọi JDK build có cùng tag set.

## 17. Tự kiểm tra

- Unified JVM Logging được đưa vào JDK nào? JDK 9.
- Tùy chọn cấu hình chính là gì? `-Xlog`.
- `-Xlog:help` dùng để làm gì? In cú pháp, tag, level, decorator và ví dụ được runtime hỗ trợ.
- Dấu `+` trong tag selection có ý nghĩa gì? Yêu cầu tổ hợp tag cùng xuất hiện.
- Dấu phẩy giữa các selection có ý nghĩa gì? Chọn nhiều nhóm log độc lập.
- Wildcard `*` dùng khi nào? Khi muốn match các tag set chứa tag hoặc tổ hợp tag đã chỉ định cùng các tag bổ sung.
- Những level chuẩn là gì? `off`, `error`, `warning`, `info`, `debug`, `trace`.
- Output có những loại nào? `stdout`, `stderr`, `file=filename`.
- Decorator `uptime` biểu thị gì? Thời gian từ khi JVM khởi động.
- Decorator `pid` và `tid` cung cấp gì? Process ID và thread ID.
- `filesize` và `filecount` làm gì? Cấu hình kích thước mục tiêu và số file rotation.
- `-Xlog:disable` có tác dụng gì? Xóa cấu hình logging hiện có, kể cả cấu hình mặc định.
- Có thể xem cấu hình đang chạy bằng lệnh nào? `jcmd <pid> VM.log list=true`.
- `-Xlog` có thay thế logger nghiệp vụ của ứng dụng không? Không.
- Vì sao phải kiểm tra `-Xlog:help` trên máy đích? Tag set và một số tùy chọn phụ thuộc JDK version/build.

## Tài liệu tham khảo

- [JEP 158: Unified JVM Logging](https://openjdk.org/jeps/158)
- [JDK 9 Release Notes — JVM Tuning Enhancements](https://docs.oracle.com/javase/9/whatsnew/)
- [The java Command — Unified Logging](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [The jcmd Command — VM.log](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)

Điểm cốt lõi: **`-Xlog` chọn tag và level, định tuyến output, thêm decorators và quản lý rotation cho log nội bộ JVM.** Dùng `-Xlog:help` trên runtime đích để xác nhận chính xác các tag và tùy chọn đang hỗ trợ.