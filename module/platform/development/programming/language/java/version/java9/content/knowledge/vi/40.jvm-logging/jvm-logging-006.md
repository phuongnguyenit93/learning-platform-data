# Theo dõi GC và nạp lớp bằng tag phù hợp

## Mục tiêu

Sau bài học này, bạn có thể:

- Bật Unified JVM Logging bằng tùy chọn `-Xlog`.
- Chọn đúng tag để theo dõi Garbage Collection (GC), class loading, class unloading và class initialization.
- Phân biệt tag, tag set, wildcard và log level.
- Chọn output, decorator và log rotation phù hợp cho môi trường chạy thật.
- Bật hoặc thay đổi cấu hình log khi JVM đang chạy bằng `jcmd VM.log`.
- Đọc log để điều tra pause GC, thay đổi heap và vấn đề class loader.
- Dùng cú pháp hiện hành trên JDK mới và nhận biết các cờ GC logging cũ cần thay thế.

## 1. Unified JVM Logging là gì?

Unified JVM Logging là hệ thống ghi log chung của HotSpot JVM. Trước Java 9, nhiều thành phần JVM dùng các cờ logging riêng. Java 9 đưa vào Unified Logging qua JEP 158; JEP 271 chuyển GC logging sang cùng hệ thống này.

Cấu hình chính dùng tùy chọn dòng lệnh:

~~~bash
java -Xlog:gc*=info,class+load=info -jar app.jar
~~~

Ví dụ trên yêu cầu JVM ghi:

- Các sự kiện có tag set chứa tag `gc`, ở mức `info` trở lên.
- Các sự kiện có tag set chính xác gồm `class` và `load`, ở mức `info` trở lên.

Unified logging vẫn được dùng trong JDK hiện hành. Tên tag và tổ hợp tag có thể thay đổi theo phiên bản, nhà cung cấp và loại VM. Hãy kiểm tra chính JVM triển khai bằng `java -Xlog:help` trước khi đưa cấu hình vào production.

**Phạm vi:** `-Xlog` là tùy chọn của HotSpot/OpenJDK VM. Các JVM khác có thể cung cấp cơ chế logging riêng.

## 2. Cấu trúc của tùy chọn -Xlog

Cú pháp tổng quát:

~~~text
-Xlog[:[tag-selection][:[output][:[decorators][:output-options]]]]
~~~

Một cấu hình gồm bốn phần:

| Phần | Vai trò | Ví dụ |
|---|---|---|
| Tag selection | Chọn sự kiện và mức chi tiết | `gc*=info` |
| Output | Chọn nơi ghi log | `file=logs/gc.log` |
| Decorators | Thêm thông tin trước nội dung log | `uptime,level,tags` |
| Output options | Cấu hình ghi file và rotation | `filecount=5,filesize=10M` |

Ví dụ đầy đủ:

~~~bash
-Xlog:gc*=info:file=logs/gc.log:uptime,level,tags:filecount=5,filesize=10M
~~~

Đọc từ trái sang phải:

1. Chọn mọi tag set có chứa `gc`.
2. Ghi ra file `logs/gc.log`.
3. Thêm uptime, level và tag set vào mỗi dòng.
4. Xoay file theo ngưỡng khoảng 10 MB và giữ 5 file đã xoay.

Nếu bỏ output, log mặc định đi ra `stdout`. Nếu bỏ decorator, JVM mặc định dùng `uptime`, `level` và `tags`.

## 3. Hiểu tag, tag set và level

Mỗi log message của JVM có một level và một tag set.

### 3.1. Tag và tag set

Tag cho biết log liên quan đến thành phần hoặc loại sự kiện nào. Ví dụ:

- `gc`: Garbage Collection.
- `class`: hoạt động liên quan đến class.
- `load`: sự kiện nạp class.
- `unload`: sự kiện gỡ class.
- `init`: khởi tạo class.
- `heap`: thông tin heap.
- `phases`: các pha xử lý.
- `ref`: xử lý reference.

Một tag set có thể chứa nhiều tag. Dấu `+` chọn các tag phải xuất hiện cùng nhau:

~~~bash
-Xlog:gc+ref=debug
~~~

Cấu hình này chọn tag set có cả `gc` và `ref`. Log chỉ có tag `gc` hoặc chỉ có tag `ref` không khớp.

Dấu phẩy phân tách nhiều selector độc lập:

~~~bash
-Xlog:gc,class+load=info
~~~

Cấu hình này chọn log có tag `gc` hoặc tag set `class+load`. Dấu phẩy không có nghĩa là một tag set chứa cả hai nhóm.

### 3.2. Wildcard

Không có wildcard, selector khớp tag set chính xác. Dấu `*` mở rộng selector để khớp các tag set có chứa những tag đã nêu.

~~~bash
-Xlog:gc=info
~~~

Chỉ chọn tag set chính xác là `gc`.

~~~bash
-Xlog:gc*=info
~~~

Chọn tag set có chứa `gc`, chẳng hạn `gc`, `gc,heap` hoặc `gc,phases`, nếu JVM hiện tại phát ra các tag set đó.

Wildcard hữu ích khi điều tra tổng quan GC vì nhiều log chi tiết sử dụng thêm tag phụ.

### 3.3. Log level

Các level hiện hành:

| Level | Mức chi tiết |
|---|---|
| `off` | Tắt log khớp selector |
| `trace` | Rất chi tiết |
| `debug` | Chi tiết phục vụ điều tra |
| `info` | Thông tin vận hành thường dùng |
| `warning` | Cảnh báo |
| `error` | Lỗi |

Một selector đặt ở `info` nhận log ở mức `info` và các mức nghiêm trọng hơn như `warning` và `error`. Chỉ tăng lên `debug` hoặc `trace` khi cần điều tra cụ thể, vì lượng log có thể tăng đáng kể.

## 4. Chọn tag để theo dõi Garbage Collection

GC logging giúp trả lời các câu hỏi:

- GC xảy ra khi nào và do nguyên nhân gì?
- Có bao nhiêu lần collection và thời gian pause là bao lâu?
- Heap trước và sau GC thay đổi thế nào?
- Pha nào đang chiếm nhiều thời gian?
- Có dấu hiệu allocation pressure hoặc heap không thu hồi được như kỳ vọng không?

### 4.1. Bắt đầu bằng tag gc

~~~bash
java -Xlog:gc=info -jar app.jar
~~~

Đây là cấu hình gọn để xem các sự kiện GC chính. Log thường thể hiện loại collection, nguyên nhân, thời gian và thông tin dung lượng liên quan.

### 4.2. Theo dõi các tag set chứa gc

~~~bash
java -Xlog:gc*=info -jar app.jar
~~~

Dùng khi cần bức tranh rộng hơn. Tùy collector và phiên bản JVM, log có thể có các nhóm chi tiết về heap, phases, reference, region, metaspace hoặc quyết định của collector.

### 4.3. Chọn chi tiết theo vấn đề

Một số selector hữu ích trên các HotSpot JVM hiện hành:

| Selector | Mục đích |
|---|---|
| `gc+heap=debug` | Theo dõi thông tin heap quanh các sự kiện GC |
| `gc+phases=debug` | Xem thời gian và hoạt động của các pha GC |
| `gc+ref=debug` | Điều tra xử lý reference |
| `gc+ergo*=debug` | Xem quyết định và heuristic của GC |
| `gc+age*=debug` | Điều tra thông tin tuổi object khi collector phát ra tag này |

Ví dụ kết hợp:

~~~bash
-Xlog:gc=info,gc+heap=debug,gc+phases=debug
~~~

Không nên bật tất cả tag ở `trace` trong thời gian dài. Hãy bắt đầu với `gc=info`, xác định khu vực cần tìm hiểu rồi tăng level cho đúng tag.

Các tag con và log site phụ thuộc collector. Kiểm tra `-Xlog:help` và thử trên đúng JDK/collector đang chạy trước khi phụ thuộc vào một selector cụ thể.

## 5. Theo dõi class loading bằng tag phù hợp

Class loading là quá trình JVM nạp định nghĩa class vào runtime. Nó có thể đến từ classpath/module path, JAR, class loader tùy chỉnh, generated class hoặc các cơ chế runtime khác.

### 5.1. Theo dõi class được nạp

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

Tag set `class+load` tập trung vào sự kiện nạp class. Log thường chứa tên class, class loader và nguồn class khi JVM cung cấp thông tin đó.

Dùng khi điều tra:

- Một class đến từ JAR hoặc vị trí nào.
- Vì sao class loader tùy chỉnh nạp class.
- Vì sao cùng tên class xuất hiện trong nhiều class loader.
- Vì sao startup nạp nhiều class hoặc class ngoài dự kiến.

Nếu cần thêm chi tiết, có thể thử:

~~~bash
-Xlog:class+load=debug
~~~

### 5.2. Phân biệt load, unload và init

Ba hoạt động này liên quan nhưng không giống nhau:

| Tag set | Ý nghĩa |
|---|---|
| `class+load` | JVM nạp định nghĩa class |
| `class+unload` | JVM gỡ định nghĩa class khi đủ điều kiện |
| `class+init` | JVM khởi tạo class, ví dụ chạy static initializer |

Ví dụ theo dõi cả nạp và gỡ class:

~~~bash
-Xlog:class+load=info,class+unload=info
~~~

Nếu nghi ngờ thời gian hoặc thứ tự khởi tạo static, bổ sung:

~~~bash
-Xlog:class+init=info
~~~

Một class được nạp không nhất thiết được khởi tạo ngay. Một class cũng không được unload ngay khi ứng dụng ngừng sử dụng nó; class loader phải trở nên không còn reachable và JVM phải thực hiện quá trình thu hồi phù hợp.

## 6. Kết hợp GC và class loading trong cùng cấu hình

Để theo dõi cả hai loại sự kiện:

~~~bash
java -Xlog:gc*=info,class+load=info -jar app.jar
~~~

Nếu cần tách log để dễ phân tích và lưu trữ:

~~~bash
java \
  -Xlog:gc*=info:file=logs/gc.log:uptime,level,tags:filecount=5,filesize=20M \
  -Xlog:class+load=info:file=logs/class-load.log:uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
~~~

Hai output riêng giúp:

- Phân tích GC mà không phải lọc các dòng class loading.
- Giữ chính sách rotation riêng cho từng file.
- Dễ chuyển từng file sang hệ thống thu thập log.
- Giảm nhiễu khi so sánh timeline.

Nếu dùng nhiều `-Xlog` directive cho cùng một output, cấu hình sau có thể thay thế cấu hình trước theo thứ tự xuất hiện. Hãy kiểm tra output cuối cùng bằng `-Xlog:help` và log khởi động để tránh vô tình ghi đè selector.

## 7. Chọn output, decorator và rotation

### 7.1. Output

Các output cơ bản:

- `stdout`: ghi ra standard output.
- `stderr`: ghi ra standard error.
- `file=filename`: ghi ra file.

Ví dụ:

~~~bash
-Xlog:gc*=info:stderr
~~~

Ghi GC log ra standard error.

~~~bash
-Xlog:gc*=info:file=logs/gc.log
~~~

Ghi GC log ra file. Đảm bảo thư mục tồn tại và process có quyền ghi.

### 7.2. Decorators

Decorator thêm ngữ cảnh vào đầu dòng log:

| Decorator | Ý nghĩa |
|---|---|
| `time` | Thời gian theo ngày giờ |
| `utctime` | Thời gian UTC |
| `uptime` | Thời gian từ lúc JVM khởi động |
| `pid` | Process ID |
| `tid` | Thread ID |
| `level` | Log level |
| `tags` | Tag set |

Ví dụ:

~~~bash
-Xlog:gc*=info:stdout:time,uptime,pid,level,tags
~~~

Một dòng log minh họa:

~~~text
[2026-11-07T10:15:21.120+0000][12.345s][1234][info][gc] GC(7) Pause Young ...
~~~

Đây là định dạng minh họa; timestamp, PID, GC ID và nội dung thực tế phụ thuộc lần chạy.

### 7.3. File rotation

Ví dụ:

~~~bash
-Xlog:gc*=info:file=logs/gc.log:uptime,level,tags:filecount=5,filesize=20M
~~~

- `filesize=20M`: kích thước mục tiêu trước khi xoay file.
- `filecount=5`: giữ tối đa 5 file đã xoay, ngoài file đang hoạt động.
- Kích thước thực tế có thể xấp xỉ, không phải ranh giới tuyệt đối.

Rotation giúp giới hạn dung lượng log trên đĩa. Hãy đặt retention theo dung lượng ổ đĩa, tần suất GC và yêu cầu điều tra sự cố.

## 8. Thay đổi logging khi JVM đang chạy bằng jcmd

Không phải lúc nào cũng có thể khởi động lại ứng dụng để thêm cờ JVM. Diagnostic command `VM.log` cho phép xem và thay đổi cấu hình Unified Logging khi process đang chạy.

Liệt kê JVM:

~~~bash
jcmd -l
~~~

Xem cấu hình log hiện tại:

~~~bash
jcmd <pid> VM.log list
~~~

Bật GC và class-load logging trên output stdout:

~~~bash
jcmd <pid> VM.log output=stdout what="gc*=info,class+load=info" decorators="uptime,level,tags"
~~~

Trong đó:

- `<pid>` là process ID của JVM mục tiêu.
- `output` xác định output cần cấu hình.
- `what` chọn tag set và level.
- `decorators` chọn thông tin được thêm vào dòng log.

`jcmd` cần chạy trên cùng máy với JVM mục tiêu và dưới cùng effective user/group ID đã khởi chạy JVM. Một số môi trường container hoặc quyền hệ điều hành có thể giới hạn khả năng attach.

Sau khi thay đổi, chạy lại:

~~~bash
jcmd <pid> VM.log list
~~~

để xác nhận cấu hình thực tế.

## 9. Ví dụ hoàn chỉnh: tạo class loading và GC event

Tạo file **JvmUnifiedLoggingDemo.java**:

~~~java
public final class JvmUnifiedLoggingDemo {

    private static volatile Object allocationSink;

    public static void main(String[] args) throws Exception {
        // Yêu cầu JVM nạp một số class khi ứng dụng chạy.
        Class<?> zipClass =
                Class.forName("java.util.zip.GZIPInputStream");
        Class<?> instantClass =
                Class.forName("java.time.Instant");

        // Tạo object để minh họa áp lực cấp phát.
        // Gán vào volatile field để các allocation có thể quan sát được.
        for (int i = 0; i < 32; i++) {
            allocationSink = new byte[512 * 1024];
        }
        allocationSink = null;

        // Yêu cầu GC; JVM có thể bỏ qua nếu explicit GC bị vô hiệu hóa.
        System.gc();

        System.out.println("loaded = " + zipClass.getName());
        System.out.println("loaded = " + instantClass.getName());
        System.out.println("explicit GC requested");
    }
}
~~~

Tạo thư mục output, biên dịch bằng JDK 17:

~~~bash
javac --release 17 -Xlint:all -d out JvmUnifiedLoggingDemo.java
~~~

Trước khi chạy, tạo thư mục log. Trên Linux/macOS dùng lệnh mkdir -p logs; trong Windows PowerShell dùng New-Item -ItemType Directory -Force logs.

Chạy với cả hai nhóm tag trong một file:

~~~bash
java \
  -Xlog:gc*=info,class+load=info:file=logs/jvm.log:uptime,level,tags:filecount=5,filesize=10M \
  -cp out JvmUnifiedLoggingDemo
~~~

Stdout của chương trình:

~~~text
loaded = java.util.zip.GZIPInputStream
loaded = java.time.Instant
explicit GC requested
~~~

File `logs/jvm.log` có thể chứa các dòng tương tự:

~~~text
[0.0xxs][info][class,load  ] JvmUnifiedLoggingDemo source: file:/...
[0.1xxs][info][class,load  ] java.util.zip.GZIPInputStream source: jrt:/java.base
[0.2xxs][info][gc     ] Using G1
[0.3xxs][info][gc     ] GC(0) Pause Full ...
~~~

Các dòng trên chỉ minh họa hình thức và tag set. Tên collector, số GC, thời gian, thứ tự class loading và nội dung log thực tế phụ thuộc JDK, collector, heap và môi trường chạy.

Kiểm tra nhanh file log trên Windows PowerShell:

~~~powershell
Select-String -Path logs/jvm.log -Pattern '\[gc'
Select-String -Path logs/jvm.log -Pattern '\[class,load'
~~~

Trên Linux/macOS:

~~~bash
grep '\[gc' logs/jvm.log
grep '\[class,load' logs/jvm.log
~~~

`System.gc()` chỉ là yêu cầu. Nó có thể không tạo collection nếu explicit GC bị vô hiệu hóa hoặc runtime quyết định không thực hiện. Không dùng lệnh này để ép GC trong production hoặc suy luận rằng mọi lần gọi đều tạo một full collection.

Ví dụ dùng API và cú pháp tương thích Java 9. Có thể kiểm tra compile với:

~~~bash
javac --release 9 -Xlint:all -d out9 JvmUnifiedLoggingDemo.java
~~~

Tùy chọn `-Xlog` cũng có từ Java 9 và vẫn hiện diện trong các JDK mới.

## 10. Đọc log để tìm nguyên nhân

### 10.1. Khi pause GC tăng

Bắt đầu từ `gc=info` hoặc `gc*=info`, rồi đối chiếu:

- Tần suất collection có tăng đột ngột không?
- Pause time tăng ở loại collection nào?
- Dung lượng heap sau GC có giảm như kỳ vọng không?
- Có nhiều collection liên tiếp trong thời gian ngắn không?
- Có thay đổi tải, allocation rate hoặc cấu hình heap cùng thời điểm không?

Nếu cần hiểu pha nào tốn thời gian, bổ sung `gc+phases=debug`. Nếu cần heap occupancy, thử `gc+heap=debug`.

Một log riêng lẻ không đủ để kết luận memory leak. Hãy đối chiếu với heap usage, allocation rate, GC metrics, tải ứng dụng và dữ liệu qua nhiều chu kỳ.

### 10.2. Khi startup chậm hoặc nạp class bất thường

Dùng `class+load=info` để xem class nào được nạp và nguồn của chúng. Tìm:

- Class đến từ JAR hoặc module không mong muốn.
- Cùng tên class xuất hiện từ các loader khác nhau.
- Nhiều class được tạo động hoặc nạp lặp trong quá trình startup.
- Thời điểm nạp class tương ứng với giai đoạn khởi động chậm.

Nếu nghi ngờ static initializer tốn thời gian, bật thêm `class+init=info`. Class loading và class initialization là hai hoạt động khác nhau; log một tag không thay thế log tag còn lại.

### 10.3. Khi class unloading không xảy ra

Dùng:

~~~bash
-Xlog:class+unload=info,gc*=info
~~~

Class unloading phụ thuộc khả năng thu hồi class loader và quyết định của GC. Không thấy dòng unload trong một khoảng thời gian ngắn không tự động chứng minh có memory leak.

## 11. Chi phí và giới hạn khi bật log

- `info` thường phù hợp để bắt đầu điều tra vận hành.
- `debug` và `trace` có thể tạo nhiều log hơn, tăng I/O và ảnh hưởng hiệu năng.
- `gc*=info` bao quát hơn `gc=info`, nên file có thể tăng nhanh.
- `class+load=info` có thể tạo nhiều dòng khi ứng dụng nạp nhiều class.
- Log file có thể chứa đường dẫn nội bộ, tên class, tên JAR và thông tin môi trường. Hãy áp dụng quyền truy cập và retention phù hợp.
- Log format có thể khác giữa các phiên bản JDK và collector. Parser cũ dựa vào format GC trước Java 9 có thể cần cập nhật.
- Tag set không giống nhau ở mọi HotSpot build. Luôn xác minh bằng `-Xlog:help`.

Có thể bật asynchronous logging bằng:

~~~bash
-Xlog:async
~~~

Async logging dùng buffer trung gian có giới hạn. Khi buffer đầy, chế độ drop có thể bỏ log; chế độ stall có thể làm thread ghi log chờ. Cân nhắc trade-off giữa độ đầy đủ log và tác động lên ứng dụng trước khi bật.

## 12. Các cờ cũ cần thay thế

GC logging đã được chuyển sang Unified Logging từ Java 9. Với JVM hiện hành, dùng `-Xlog` thay cho các cờ GC logging cũ.

| Cờ cũ | Cách cấu hình hiện hành |
|---|---|
| `-XX:+PrintGC` | `-Xlog:gc` |
| `-XX:+PrintGCDetails` | `-Xlog:gc*` |
| `-Xloggc:gc.log` | `-Xlog:gc:file=gc.log` |
| `-verbose:class` | `-Xlog:class+load=info,class+unload=info` |

Các cờ cũ như `-XX:+PrintGC` và `-XX:+PrintGCDetails` đã bị deprecated trong quá trình chuyển đổi. `-Xloggc` cũng là tùy chọn deprecated trên JDK hiện hành. Không nên xây dựng cấu hình mới dựa trên chúng.

Định dạng log GC mới có thể khác log cũ. Nếu hệ thống đang dùng script hoặc parser đọc GC log theo format cũ, hãy kiểm tra và cập nhật parser trước khi chuyển runtime.

## 13. Lỗi thường gặp

### Dùng dấu phẩy thay cho dấu cộng

`gc,class+load` chọn hai selector độc lập. `gc+class+load` yêu cầu cả ba tag trong cùng tag set. Chọn đúng theo mục đích.

### Nghĩ gc=info đã bao gồm toàn bộ GC detail

`gc=info` chọn tag set chính xác là `gc`. Muốn lấy tag set chứa thêm `heap`, `phases` hoặc tag phụ khác, cân nhắc wildcard `gc*=info`.

### Nhầm class loading với class initialization

`class+load` ghi sự kiện nạp class; `class+init` theo dõi khởi tạo class. Khi điều tra startup, có thể cần cả hai.

### Bật debug hoặc trace trên mọi tag quá lâu

Log volume và chi phí I/O có thể tăng mạnh. Hãy giới hạn tag, level và thời gian bật.

### Ghi log ra file không có rotation

Log có thể làm đầy ổ đĩa. Cấu hình `filesize` và `filecount`, sau đó theo dõi dung lượng thực tế.

### Giả định mọi JVM đều có cùng tag

Tag set phụ thuộc VM và phiên bản. Chạy `java -Xlog:help` trên đúng runtime để xác nhận.

### Coi một dòng GC là bằng chứng memory leak

GC log chỉ là một nguồn quan sát. Phân tích xu hướng heap sau GC, allocation, tải và thời gian trên nhiều chu kỳ trước khi kết luận.

### Dùng cờ GC logging trước Java 9 trên cấu hình mới

Dùng `-Xlog` và kiểm tra parser theo định dạng hiện hành.

## 14. Checklist

- [ ] Đã xác định đúng JVM/HotSpot version đang chạy.
- [ ] Đã kiểm tra tag và level bằng `java -Xlog:help`.
- [ ] Đã dùng `gc=info` hoặc `gc*=info` theo mức độ cần quan sát.
- [ ] Đã dùng `class+load=info` để theo dõi class loading.
- [ ] Đã phân biệt `class+load`, `class+unload` và `class+init`.
- [ ] Đã chọn output và decorators phù hợp.
- [ ] Đã cấu hình file rotation nếu ghi log ra đĩa.
- [ ] Đã biết cách xem và thay đổi cấu hình bằng `jcmd VM.log`.
- [ ] Đã cân nhắc chi phí khi bật `debug`, `trace` hoặc wildcard rộng.
- [ ] Đã cập nhật parser nếu format GC log cũ không còn tương thích.
- [ ] Đã tránh các cờ logging legacy/deprecated trong cấu hình mới.
- [ ] Đã xác minh log trên đúng JDK và collector sẽ triển khai.

## 15. Tài liệu tham khảo

- [Java SE 25: The java Command – Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [Java SE 25: The jcmd Command – VM.log](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html)
- [JEP 158: Unified JVM Logging](https://openjdk.org/jeps/158)
- [JEP 271: Unified GC Logging](https://openjdk.org/jeps/271)
- [Oracle JDK 9: What's New for JVM Tuning](https://docs.oracle.com/javase/9/whatsnew/)
- [Oracle Migration Guide: Changes to GC Log Output](https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html)

