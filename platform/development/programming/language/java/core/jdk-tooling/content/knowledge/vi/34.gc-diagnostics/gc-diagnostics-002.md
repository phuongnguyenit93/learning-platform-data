# Bật GC logging trong Java

GC logging ghi lại hoạt động của Garbage Collector (GC) trong JVM. Log cho biết khi nào GC chạy, nguyên nhân kích hoạt, thời gian pause, lượng heap trước và sau collection, các pha xử lý và thông tin CPU. Đây là dữ liệu nền tảng khi điều tra latency spike, Full GC, heap tăng, allocation pressure hoặc khác biệt giữa các collector.

Từ JDK 9, Java dùng Unified JVM Logging với tùy chọn `-Xlog`. Trên JDK 8, GC logging dùng nhóm cờ riêng như `-XX:+PrintGCDetails`, `-Xloggc` và các cờ rotation. Không nên sao chép nguyên cấu hình JDK 8 sang JDK mới; hãy chọn cú pháp theo runtime thực tế.

Bài học này đã được kiểm tra trên Zulu/OpenJDK 24.0.2. Các ví dụ lệnh dùng Java 17+; nội dung log chi tiết có thể thay đổi theo JDK, collector và workload.

## 1. GC logging dùng để làm gì?

GC log giúp trả lời các câu hỏi vận hành:

- GC chạy bao nhiêu lần và loại collection nào đang xảy ra?
- Pause nào ảnh hưởng tới request latency?
- Heap dùng bao nhiêu trước và sau GC?
- Young GC có thường xuyên không? Có xuất hiện Mixed GC hoặc Full GC?
- Có dấu hiệu allocation pressure, humongous allocation hoặc promotion pressure?
- GC tiêu tốn bao nhiêu CPU time?
- Có safepoint dài không liên quan trực tiếp đến GC?
- Khi thay đổi heap size hoặc collector, hành vi GC có thay đổi không?

Một số triệu chứng và dữ liệu cần xem:

| Triệu chứng | Nội dung log nên tập trung |
|---|---|
| Request latency tăng theo đợt | Pause duration, GC cause, safepoint |
| Full GC lặp lại | `Pause Full`, heap before/after, cause |
| Heap sau GC vẫn tăng | Occupancy sau collection, old generation, allocation |
| Young GC quá dày | Tần suất young collection, allocation rate |
| G1 Mixed GC kéo dài | Mixed collection, phases, region/reclaim |
| Allocation lớn bất thường | Allocation/heap events, humongous regions |
| CPU tăng khi GC chạy | GC worker CPU, user/sys/real time |
| Pause không giải thích được bởi GC | Safepoint log và VM operation |

GC log cung cấp bằng chứng về JVM. Nó không tự xác định object nào trong source code tạo allocation; có thể kết hợp JFR, heap dump, application metrics và trace để tìm nguồn gốc.

## 2. Khác biệt giữa JDK 8 và JDK 9+

### JDK 8: cờ GC logging riêng

Ví dụ cấu hình phổ biến trên HotSpot JDK 8:

~~~text
java -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:/var/log/myapp/gc.log -XX:+UseGCLogFileRotation -XX:NumberOfGCLogFiles=5 -XX:GCLogFileSize=20M -jar application.jar
~~~

Ý nghĩa:

- `-XX:+PrintGCDetails`: ghi thông tin GC chi tiết.
- `-XX:+PrintGCDateStamps`: thêm timestamp dạng ngày giờ.
- `-Xloggc:<file>`: ghi GC log vào file.
- `-XX:+UseGCLogFileRotation`: bật xoay vòng file.
- `-XX:NumberOfGCLogFiles=5`: số file trong bộ rotation.
- `-XX:GCLogFileSize=20M`: kích thước mục tiêu cho mỗi file.

Một số bản JDK 8 hoặc JVM vendor có khác biệt về cờ và định dạng; kiểm tra `java -XX:+PrintFlagsFinal -version` và tài liệu đúng vendor trước khi triển khai.

### JDK 9+: Unified JVM Logging

JDK 9 hợp nhất nhiều hệ thống log của JVM thành Unified Logging. GC log được chọn bằng `-Xlog`:

~~~text
java -Xlog:gc -jar application.jar
~~~

Cấu hình tương đương cho GC chi tiết hơn:

~~~text
java -Xlog:gc*=info -jar application.jar
~~~

Unified Logging cho phép chọn tag, mức log, output, decorators và rotation trong cùng một biểu thức. Đây là cú pháp nên dùng cho JDK 9 trở lên.

### Bảng chuyển đổi khái niệm

| JDK 8 | Unified Logging |
|---|---|
| `-verbose:gc` | `-Xlog:gc` |
| `-XX:+PrintGCDetails` | `-Xlog:gc*` |
| `-XX:+PrintGCDateStamps` | Decorator `time` hoặc `utctime` |
| `-XX:+PrintGCTimeStamps` | Decorator `uptime` |
| `-Xloggc:<file>` | `file=<file>` trong `-Xlog` |
| `-XX:+UseGCLogFileRotation` | `filecount=<n>` |
| `-XX:NumberOfGCLogFiles=<n>` | `filecount=<n>` |
| `-XX:GCLogFileSize=<size>` | `filesize=<size>` |

Bảng này thể hiện cách chuyển ý định cấu hình. Định dạng dòng log và nội dung event không giống hệt giữa hai thế hệ. Trên JDK mới, hãy dùng `-Xlog` thay vì dựa vào cờ cũ.

## 3. Cấu trúc của tùy chọn `-Xlog`

Cú pháp tổng quát:

~~~text
-Xlog[:[selections][:[output][:[decorators][:output-options]]]]
~~~

Có thể đọc theo bốn phần:

1. `selections`: chọn tag và level cần ghi.
2. `output`: ghi ra `stdout`, `stderr` hoặc file.
3. `decorators`: thông tin phụ thêm vào mỗi dòng log.
4. `output-options`: tùy chọn cho file, ví dụ rotation.

Ví dụ:

~~~text
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Lệnh trên chọn các tag combination có `gc`, ghi tới mức `info`, lưu vào `gc.log`, thêm thời gian/level/tags và xoay vòng với năm file rotation, mỗi file có kích thước mục tiêu 20 MB.

Để xem cú pháp, tag, level và decorator có trong runtime:

~~~text
java -Xlog:help
~~~

Danh sách tag có thể khác theo phiên bản và build. Khi một selector không hoạt động, kiểm tra trợ giúp của đúng binary `java` dùng để chạy ứng dụng.

## 4. Tag, wildcard và log level

Unified Logging phân loại thông điệp bằng tag. Một thông điệp có thể mang nhiều tag, ví dụ `gc,heap`, `gc,phases` hoặc `gc,cpu`.

### 4.1. Chọn tag

| Selector | Ý nghĩa |
|---|---|
| `gc` | Chỉ thông điệp có đúng tag combination `gc` |
| `gc+heap` | Thông điệp có đồng thời tag `gc` và `heap` |
| `gc+phases` | Thông điệp có cả `gc` và `phases` |
| `gc+ergo` | Thông điệp GC ergonomics |
| `gc+ref` | Thông điệp xử lý reference |
| `safepoint` | Thông điệp safepoint |
| `gc*` | Các tag combination có tag `gc`, kể cả combination mở rộng |

Dấu `+` biểu thị điều kiện đồng thời giữa các tag. Dấu phẩy giữa các selector biểu thị các lựa chọn độc lập.

Ví dụ ghi GC và safepoint:

~~~text
-Xlog:gc,safepoint
~~~

Ví dụ chỉ ghi heap detail của GC:

~~~text
-Xlog:gc+heap=debug
~~~

Ví dụ ghi các pha GC và ergonomics:

~~~text
-Xlog:gc+phases=debug,gc+ergo=debug
~~~

### 4.2. Các mức log

JDK 24.0.2 cung cấp các level:

| Level | Ý nghĩa |
|---|---|
| `off` | Tắt selector |
| `trace` | Chi tiết rất cao |
| `debug` | Thông tin phục vụ điều tra sâu |
| `info` | Thông tin vận hành thông thường |
| `warning` | Cảnh báo |
| `error` | Lỗi |

Nếu không chỉ định level, mặc định là `info`. Level cao hơn như `debug` và `trace` có thể tạo nhiều dữ liệu, vì vậy nên bật theo mục tiêu và thời gian giới hạn.

Ví dụ:

~~~text
-Xlog:gc*=info
-Xlog:gc+heap=debug
-Xlog:gc+phases=trace
~~~

`-Xlog:gc*=debug` có thể rất verbose. Không bật toàn bộ tag ở `trace` trong production lâu dài nếu chưa đánh giá dung lượng và overhead.

## 5. Ghi GC log ra console

Cách đơn giản nhất:

~~~text
java -Xlog:gc -jar application.jar
~~~

Log được ghi ra `stdout` theo mặc định. Có thể chọn rõ output:

~~~text
java -Xlog:gc=info:stdout -jar application.jar
~~~

Hoặc ghi sang `stderr`:

~~~text
java -Xlog:gc=info:stderr -jar application.jar
~~~

Ghi console hữu ích khi chạy container và nền tảng triển khai thu thập stdout/stderr vào log platform. Hãy kiểm tra cấu hình log driver, giới hạn retention, multiline parsing và chi phí lưu trữ.

Nếu ứng dụng chạy dưới service manager, container runtime hoặc Kubernetes, cần bảo đảm GC log được gom về hệ thống quan sát tập trung và có thể tìm theo pod, container, process hoặc instance.

## 6. Ghi GC log ra file

Ví dụ production cơ bản:

~~~text
java -Xms512m -Xmx512m -Xlog:gc*=info:file=/var/log/myapp/gc.log:time,uptime,level,tags -jar application.jar
~~~

Có thể dùng tên file riêng cho từng process:

~~~text
java -Xlog:gc*=info:file=/var/log/myapp/gc-%p-%t.log:time,uptime,level,tags -jar application.jar
~~~

Các placeholder trong tên file:

- `%p`: PID của JVM.
- `%t`: timestamp lúc JVM khởi chạy.
- `%hn`: hostname.

Thư mục đích phải tồn tại và user chạy JVM cần quyền ghi. Trên Windows, dùng đường dẫn hợp lệ của máy và tránh ký tự phân cách `:` trong phần cấu hình selector/output. Với đường dẫn có khoảng trắng, kiểm tra cách quote theo shell và launcher thực tế.

Nếu chạy nhiều JVM trên cùng host, thêm PID hoặc hostname để tránh các process cùng ghi vào một file. Nếu dùng container có filesystem ephemeral, cần xác định volume và chính sách thu thập file trước khi deploy.

## 7. Decorator: thêm thời gian và ngữ cảnh

Decorator là metadata được thêm vào mỗi dòng log.

| Decorator | Thông tin |
|---|---|
| `time` | Ngày giờ local |
| `utctime` | Ngày giờ UTC |
| `uptime` | Thời gian kể từ lúc JVM khởi chạy |
| `timemillis` | Epoch time theo millisecond |
| `uptimemillis` | Uptime theo millisecond |
| `timenanos` | Epoch time theo nanosecond |
| `uptimenanos` | Uptime theo nanosecond |
| `hostname` | Hostname |
| `pid` | Process ID |
| `tid` | Thread ID |
| `level` | Level của thông điệp |
| `tags` | Tag combination |

Ví dụ:

~~~text
-Xlog:gc*=info:file=gc.log:time,uptime,pid,level,tags
~~~

`time` giúp đối chiếu với log ứng dụng, alert và incident timeline. `uptime` hữu ích để so sánh sự kiện trong cùng một vòng đời JVM và không phụ thuộc thay đổi đồng hồ hệ thống.

Có thể bỏ toàn bộ decorator:

~~~text
-Xlog:gc=debug:file=gc.log:none
~~~

Trong production, nên giữ ít nhất timestamp, uptime, level và tags. Nếu nhiều JVM ghi log chung một hệ thống, PID hoặc hostname giúp phân biệt nguồn.

## 8. Xoay vòng file để giới hạn dung lượng

Không nên để GC log tăng vô hạn trên volume production. Unified Logging hỗ trợ file rotation:

~~~text
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Ý nghĩa:

- `filesize=20M`: kích thước mục tiêu trước khi tự động rotate.
- `filecount=5`: số file rotation được giữ lại, không tính file đang hoạt động.
- File đang hoạt động tiếp tục nhận log sau khi rotate.

Khi file đạt kích thước mục tiêu, JVM xoay file và tiếp tục ghi. Kích thước thực tế có thể lệch nhẹ so với ngưỡng do cách ghi chunk và thời điểm kiểm tra rotation.

Một số lưu ý:

- `filecount=0` tắt rotation; các file cũ có thể bị ghi đè.
- `filesize=0` tắt automatic rotation, nhưng có thể rotate thủ công bằng `VM.log`.
- Chọn số file và kích thước theo tốc độ phát sinh log, thời gian cần giữ và dung lượng volume.
- Nếu log shipper đọc file theo tên, kiểm tra cách nó theo dõi file sau khi rotate.
- Đừng để rotation cục bộ và log shipper cùng xóa file khi chưa thống nhất retention.

Có thể dùng tên có PID và timestamp cùng rotation:

~~~text
-Xlog:gc*=info:file=gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

## 9. Các cấu hình GC logging thường dùng

### 9.1. Production baseline

~~~text
-Xlog:gc*=info,safepoint=info:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Ghi GC event và safepoint với mức `info`, có timestamp, uptime và rotation. Đây là điểm khởi đầu phù hợp để quan sát hành vi GC trong thời gian dài.

### 9.2. Điều tra heap

~~~text
-Xlog:gc*=info,gc+heap=debug:file=gc-heap.log:time,uptime,level,tags:filecount=5,filesize=50M
~~~

Thêm thông tin heap để hiểu occupancy và hành vi region/generation theo collector.

### 9.3. Điều tra GC phase

~~~text
-Xlog:gc*=info,gc+phases=debug,gc+ergo=debug:file=gc-detail.log:time,uptime,level,tags:filecount=5,filesize=50M
~~~

Dùng khi cần hiểu thời gian ở các pha hoặc quyết định ergonomics của JVM. Cấu hình này tạo nhiều log hơn baseline.

### 9.4. Điều tra reference processing

~~~text
-Xlog:gc+ref=debug:file=gc-ref.log:uptime,level,tags:filecount=3,filesize=20M
~~~

Dùng khi nghi ngờ xử lý soft/weak/phantom reference hoặc reference queue ảnh hưởng tới thời gian GC.

### 9.5. Chỉ lấy safepoint

~~~text
-Xlog:safepoint=info:file=safepoint.log:time,uptime,level,tags:filecount=5,filesize=10M
~~~

Hữu ích khi pause quan sát được không giải thích đầy đủ bằng các GC pause event.

Không cần bật mọi cấu hình cùng lúc. Bắt đầu từ baseline, xác định câu hỏi cần trả lời rồi tăng mức log cho tag liên quan.

## 10. Đọc một dòng GC log

Ví dụ một dòng thực tế thu được từ Zulu/OpenJDK 24.0.2:

~~~text
[0.842s][info][gc             ] GC(4) Pause Full (System.gc()) 6M->1M(32M) 2.290ms
~~~

Có thể đọc như sau:

- `[0.842s]`: uptime của JVM tại thời điểm log.
- `[info]`: level của thông điệp.
- `[gc]`: tag.
- `GC(4)`: ID của collection; các dòng cùng ID thuộc cùng sự kiện/chuỗi xử lý.
- `Pause Full`: loại collection và pause.
- `(System.gc())`: nguyên nhân/cause được báo.
- `6M->1M`: heap usage trước và sau collection.
- `(32M)`: heap capacity được ghi tại sự kiện.
- `2.290ms`: thời lượng của pause event.

Dòng CPU có thể đi kèm:

~~~text
[0.842s][info][gc,cpu] GC(4) User=0.00s Sys=0.00s Real=0.00s
~~~

- `User`: CPU time ở user mode.
- `Sys`: CPU time ở kernel mode.
- `Real`: thời gian thực trôi qua.

Với GC song song, tổng `User` có thể lớn hơn `Real` vì nhiều worker chạy đồng thời. `Real` thường gần với thời lượng quan sát được, nhưng cần đối chiếu với pause và safepoint event.

Định dạng trên là ví dụ của một phiên bản và collector cụ thể. Không giả định mọi collector hoặc JDK đều in đúng cùng một câu.

## 11. Phân biệt các loại GC event

### G1 GC

G1 thường có các thông điệp:

- `Pause Young`: young collection.
- `Pause Young (Concurrent Start)`: young pause khởi động concurrent cycle.
- `Pause Remark`: remark pause trong chu kỳ concurrent marking.
- `Pause Cleanup`: cleanup pause.
- `Pause Mixed`: mixed collection xử lý cả young và một phần old regions.
- `Pause Full`: Full GC.

Khi điều tra G1, xem cả thời lượng pause, region count, humongous allocation, mixed collection và các pha evacuation/marking. Một chuỗi Mixed GC dài không nhất thiết có cùng nguyên nhân với Full GC.

### Parallel GC

Parallel collector thường có young/full collection với các cause như allocation failure. Xem tần suất, pause duration, heap before/after và worker CPU.

### ZGC và collector concurrent

Các collector concurrent có chu kỳ và pha riêng. Nhiều phần công việc diễn ra đồng thời với application threads, nên tổng thời gian chu kỳ không đồng nghĩa với thời gian application bị pause. Xem các pause event riêng, cycle phase và phiên bản JDK.

Tên event, tag và mức chi tiết thay đổi theo collector và JDK. Dùng `java -Xlog:help` và một recording đại diện của chính môi trường để xác nhận tag có sẵn.

## 12. Safepoint log và pause của ứng dụng

GC pause thường diễn ra tại safepoint, nhưng không phải mọi safepoint đều là GC. JVM có thể dừng thread cho nhiều VM operation khác.

Bật safepoint log:

~~~text
-Xlog:safepoint=info
~~~

Có thể kết hợp với GC log:

~~~text
-Xlog:gc*=info,safepoint=info:file=gc-safepoint.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Khi latency spike xuất hiện:

1. Tìm khoảng thời gian tương ứng trong application log/metrics.
2. Tìm GC event gần cùng timestamp.
3. So sánh pause duration với request latency.
4. Nếu không có GC pause tương ứng, xem safepoint event và VM operation.
5. Đối chiếu thread dump hoặc JFR khi cần hiểu thread nào bị ảnh hưởng.

Không cộng thời lượng của mọi dòng phase vào nhau để tính pause. Nhiều pha lồng nhau hoặc chạy song song; dùng event pause tổng thể và safepoint timing để so sánh.

## 13. Thay đổi GC logging khi JVM đang chạy bằng `jcmd`

Từ JDK 9, Unified Logging có thể được cấu hình lúc runtime bằng diagnostic command `VM.log`, nếu target JVM hỗ trợ attach và quyền attach phù hợp.

Liệt kê cấu hình log hiện tại:

~~~text
jcmd <PID> VM.log list=true
~~~

Xem trợ giúp command:

~~~text
jcmd <PID> help VM.log
~~~

Bật GC logging động ra file:

~~~text
jcmd <PID> VM.log what=gc*=debug output=file=gc-live.log decorators=uptime,level,tags output_options=filecount=3,filesize=20M
~~~

Trong ví dụ:

- `what=gc*=debug`: bật các tag combination GC ở mức debug.
- `output=file=gc-live.log`: tạo file log trong working directory của JVM.
- `decorators=uptime,level,tags`: thêm uptime, level và tags.
- `output_options=filecount=3,filesize=20M`: giới hạn file rotation.

Xem lại cấu hình:

~~~text
jcmd <PID> VM.log list=true
~~~

Rotate thủ công các log output:

~~~text
jcmd <PID> VM.log rotate=true
~~~

`VM.log` cũng có thể cấu hình output `stdout` hoặc `stderr`. Tham số và khả năng thay đổi phụ thuộc phiên bản JDK. JDK 8 không dùng Unified Logging/`VM.log` theo cách này; với JDK 8, cấu hình GC logging thường phải đặt lúc khởi chạy JVM.

Nếu cần dừng hoặc đổi một output cụ thể, đọc `jcmd <PID> help VM.log` của target JVM và xác định output index trước khi thao tác. Tránh dùng `disable=true` một cách tùy tiện vì tùy chọn đó xóa toàn bộ cấu hình logging.

## 14. Ví dụ Java 17+: tạo GC log có rotation

Tạo file `GcLoggingDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class GcLoggingDemo {
    private GcLoggingDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("GC_LOG_DEMO_READY");

        for (int round = 0; round < 10; round++) {
            List<byte[]> retained = new ArrayList<>();

            for (int i = 0; i < 16; i++) {
                retained.add(new byte[256 * 1024]);
            }

            retained.clear();
            System.gc();
            Thread.sleep(200);
        }

        System.out.println("GC_LOG_DEMO_DONE");
    }
}
~~~

Biên dịch:

~~~text
javac --release 17 GcLoggingDemo.java
~~~

Chạy với heap nhỏ và GC logging ra file có rotation:

~~~text
java -Xms32m -Xmx32m -Xlog:gc*=info:file=gc.log:uptime,level,tags:filecount=3,filesize=8k GcLoggingDemo
~~~

Stdout của chương trình:

~~~text
GC_LOG_DEMO_READY
GC_LOG_DEMO_DONE
~~~

Sau khi chạy, kiểm tra các file:

~~~text
dir gc.log*
~~~

Có thể xem một phần log:

~~~text
type gc.log
~~~

Trong lần kiểm tra với Zulu/OpenJDK 24.0.2, log có các file `gc.log` và `gc.log.0`, chứng minh rotation đã hoạt động. Một dòng thu được:

~~~text
[0.842s][info][gc             ] GC(4) Pause Full (System.gc()) 6M->1M(32M) 2.290ms
~~~

Thời gian, GC ID, heap occupancy và số file thực tế thay đổi theo lần chạy và môi trường. `System.gc()` chỉ được dùng trong lab để tạo sự kiện dễ quan sát; không thêm lệnh này vào ứng dụng production để ép GC.

## 15. Phân tích GC log theo câu hỏi vận hành

### Pause time và latency

Theo dõi pause duration và phân phối P50/P95/P99 từ các lần GC. Một vài pause dài có thể ảnh hưởng tới tail latency dù thời gian GC trung bình thấp. So sánh timestamp với request latency và SLO.

### Heap trước/sau GC

Quan sát occupancy sau collection theo thời gian. Nếu heap sau GC tăng đều qua nhiều chu kỳ, điều tra retained objects, cache, queue hoặc object lifetime. Một lần heap tăng sau GC chưa đủ kết luận memory leak.

### Allocation pressure

Young GC dày có thể phản ánh allocation rate cao. Kết hợp JFR allocation events hoặc application profiling để tìm class/method cấp phát nhiều. GC log một mình thường không cho biết đầy đủ call site.

### Full GC

Full GC lặp lại cần điều tra nguyên nhân: allocation failure, promotion failure, explicit GC, metadata pressure hoặc collector-specific condition. Xem cause, heap before/after, phases và log ngay trước Full GC.

### Humongous allocation với G1

G1 có thể ghi thông tin region/humongous allocation. Object lớn chiếm nhiều region liên tiếp và có thể làm tăng áp lực heap. Kiểm tra object size, allocation site và cấu hình region; không đổi heap hoặc collector chỉ dựa trên một log line.

### CPU và safepoint

So sánh `User`, `Sys`, `Real` và safepoint duration. Nếu pause app dài hơn GC pause, điều tra safepoint synchronization hoặc VM operation khác. Nếu `User` lớn, GC worker có thể đang dùng nhiều CPU dù wall-clock pause thấp hơn.

## 16. Kết hợp GC logging với JFR và metrics

Mỗi công cụ trả lời một lớp câu hỏi:

| Công cụ | Câu hỏi phù hợp |
|---|---|
| GC log | Khi nào GC chạy, loại/cause nào, pause bao lâu, heap thay đổi ra sao? |
| JFR | Thread, allocation sample, lock, I/O và event nào liên quan cùng thời điểm? |
| Heap dump | Object nào đang giữ heap và quan hệ reference ra sao? |
| Application metrics | Request latency, throughput, queue depth, error rate biến động thế nào? |
| Distributed tracing | Request đi qua service/database nào và chậm ở span nào? |

Một quy trình điều tra:

1. Dùng GC log xác định timestamp và loại pause.
2. Tìm cùng cửa sổ thời gian trong JFR.
3. Kiểm tra allocation, execution samples, thread park và lock events.
4. Đối chiếu application metrics và trace.
5. Nếu post-GC occupancy cao và kéo dài, cân nhắc heap dump theo quy trình bảo vệ dữ liệu.
6. Đặt giả thuyết cụ thể rồi thay đổi một yếu tố tại một thời điểm.

GC log nên được bật liên tục với mức hợp lý để có lịch sử trước incident. JFR có thể chạy recording mặc định để cung cấp ngữ cảnh sâu hơn khi cần.

## 17. Đưa GC logging vào service, container và Kubernetes

### Service chạy trực tiếp

Đặt JVM options trong startup script hoặc service configuration. Xác nhận user chạy JVM có quyền ghi log directory và rotation không xung đột với log shipper.

### Container

Nếu log được thu thập từ stdout/stderr, dùng:

~~~text
-Xlog:gc*=info,safepoint=info:stdout:time,uptime,level,tags
~~~

Nếu ghi file bên trong container, mount volume có dung lượng và retention phù hợp. Filesystem của container có thể bị xóa khi pod/container bị thay thế.

### Kubernetes

Có thể chuyển log ra stdout để container runtime thu thập. Đảm bảo log collector parse timestamp, giữ pod/container metadata và không loại bỏ các dòng GC nhiều dòng. Nếu dùng file output, mount volume và cấu hình sidecar/agent thu thập file đã rotate.

Trong mọi môi trường, cần tính dung lượng dựa trên số JVM, log volume mỗi giờ, số ngày retention và số file rotation. Không giả định một mức `filesize` phù hợp cho mọi workload.

## 18. Troubleshooting

### `Unrecognized VM option '-Xlog...'`

**Nguyên nhân:** đang dùng JDK 8 hoặc runtime không hỗ trợ Unified Logging.

**Cách xử lý:** xác nhận `java -version`. Với HotSpot JDK 8, dùng cờ GC logging cũ; với JDK 9+, dùng `-Xlog`.

### Không thấy GC log

**Nguyên nhân:** selector sai, output path không ghi được, log đang đi ra stdout/stderr khác hoặc workload chưa kích hoạt GC.

**Cách xử lý:** thử `-Xlog:gc` trước, kiểm tra `java -Xlog:help`, quyền thư mục và command line thực tế của JVM.

### File log không được tạo

**Nguyên nhân:** thư mục chưa tồn tại, quyền ghi không đủ, đường dẫn sai hoặc JVM thoát trước khi mở output.

**Cách xử lý:** tạo thư mục trước khi start, xác nhận user service có quyền và thử file tương đối trong working directory kiểm soát được.

### Rotation không xảy ra

**Nguyên nhân:** file chưa đạt `filesize`, `filecount=0`, hoặc cấu hình output không chứa file rotation options.

**Cách xử lý:** kiểm tra `VM.log list=true`, dùng file nhỏ trong lab để xác nhận, sau đó chọn kích thước phù hợp production.

### Log quá lớn

**Nguyên nhân:** bật `gc*=debug`/`trace`, nhiều tag, workload allocation cao hoặc rotation không được cấu hình.

**Cách xử lý:** trở lại `gc*=info`, chỉ bật tag cần thiết, giới hạn `filecount`/`filesize` và đặt retention ở log platform.

### Log có GC pause nhưng request latency không khớp

**Nguyên nhân:** timestamp không đồng bộ, request không chạy trên cùng JVM, hoặc latency do I/O/lock/safepoint khác.

**Cách xử lý:** thêm `time` và `uptime`, đối chiếu trace ID, JFR và safepoint log. Kiểm tra timezone của hệ thống log tập trung.

### Không hiểu heap before/after

**Nguyên nhân:** nhầm dung lượng heap sau collection với `-Xmx`, hoặc so sánh các collector/phase khác nhau.

**Cách xử lý:** đọc capacity trong cùng dòng, kiểm tra `-Xms`/`-Xmx`, collector và các event liên quan. Dùng heap metrics để theo dõi xu hướng.

### Không thể đổi log runtime bằng `jcmd`

**Nguyên nhân:** JDK không hỗ trợ Unified Logging, attach bị tắt, khác user/PID namespace hoặc command không có trên target.

**Cách xử lý:** chạy `jcmd <PID> help VM.log`, kiểm tra quyền attach và đúng PID. Nếu không hỗ trợ, cấu hình log lúc JVM khởi chạy.

### GC log không đủ thông tin để tìm allocation site

**Nguyên nhân:** GC log tập trung vào collection và heap, không ghi đầy đủ call site cho mọi allocation.

**Cách xử lý:** dùng JFR allocation profiling hoặc profiler phù hợp; nếu nghi memory leak, dùng heap dump và retained-size analysis.

## 19. Checklist bật GC logging trong production

- [ ] Đã xác nhận JDK vendor/version.
- [ ] Đã chọn cú pháp đúng: JDK 8 legacy flags hoặc JDK 9+ `-Xlog`.
- [ ] Đã bật baseline `gc*=info` và safepoint nếu cần.
- [ ] Đã chọn output stdout/stderr hoặc file theo cách thu thập log.
- [ ] Đã thêm timestamp, uptime, level và tags.
- [ ] Đã cấu hình `filecount` và `filesize` nếu ghi file.
- [ ] Thư mục log tồn tại và user chạy JVM có quyền ghi.
- [ ] Đã tính disk budget, rotation và retention.
- [ ] Đã xác định log shipper xử lý file rotation hoặc stdout đúng cách.
- [ ] Đã thử cấu hình trên staging với workload đại diện.
- [ ] Đã biết cách đọc GC ID, cause, heap before/after và pause duration.
- [ ] Đã bật tag chi tiết chỉ khi có giả thuyết cần điều tra.
- [ ] Đã biết cách kiểm tra/đổi log runtime bằng `jcmd VM.log` nếu JDK hỗ trợ.
- [ ] Đã đồng bộ timestamp để đối chiếu với application logs và metrics.
- [ ] Đã có quy trình bảo vệ và lưu giữ log theo chính sách vận hành.

## 20. Tài liệu tham khảo

- Oracle JDK 24 — `java` Command, phần Unified Logging: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- Oracle JDK 24 — `jcmd` Command và diagnostic commands: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- OpenJDK JEP 158 — Unified JVM Logging: https://openjdk.org/jeps/158
- OpenJDK JEP 271 — Unified GC Logging: https://openjdk.org/jeps/271
- Oracle JDK 24 — Java Garbage Collection Tuning Guide: https://docs.oracle.com/en/java/javase/24/gctuning/

Bật GC logging bằng cú pháp phù hợp với phiên bản JDK, chọn tag và level theo mục tiêu, thêm timestamp và giới hạn dung lượng bằng rotation. Dùng GC log để tìm thời điểm, nguyên nhân và pause; kết hợp JFR, metrics và tracing khi cần xác định vì sao ứng dụng tạo áp lực bộ nhớ hoặc bị chậm.