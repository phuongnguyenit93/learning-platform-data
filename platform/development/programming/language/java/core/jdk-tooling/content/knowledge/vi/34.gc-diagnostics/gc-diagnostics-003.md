# Đọc và cấu hình GC log format trong JVM

## 1. GC log là gì?

GC log là nhật ký do JVM ghi lại các hoạt động Garbage Collection (GC), bao gồm thời điểm collection bắt đầu, loại collection, nguyên nhân, các phase, dung lượng heap trước/sau GC, thời gian pause và thông tin CPU. Với collector như G1, log còn có thể chứa số region Eden/Survivor/Old, trạng thái metaspace, evacuation và các quyết định điều chỉnh heap.

GC log giúp trả lời những câu hỏi vận hành:

- Young GC hoặc Full GC xảy ra bao nhiêu lần và cách nhau bao lâu?
- Mỗi pause kéo dài bao nhiêu milliseconds?
- Heap giảm bao nhiêu sau một collection?
- Old generation có tiếp tục tăng sau GC không?
- GC có thất bại evacuation hoặc gặp allocation pressure không?
- Thời gian bị ảnh hưởng nằm ở GC pause, safepoint hay hoạt động ứng dụng?
- JVM đang dùng collector nào và cấu hình heap ra sao?

Một GC log là chuỗi sự kiện theo thời gian. Để điều tra đúng, cần đọc nhiều dòng thuộc cùng một GC event và so sánh nhiều event liên tiếp. Một dòng hoặc một snapshot đơn lẻ hiếm khi đủ để kết luận memory leak hay GC đang là nguyên nhân gây chậm.

## 2. Unified Logging từ JDK 9 trở lên

Từ JDK 9, HotSpot dùng Unified JVM Logging để cấu hình nhiều nhóm log thông qua option `-Xlog`. GC logging là một nhóm tag trong hệ thống này.

Ví dụ bật GC log cơ bản:

~~~bash
java -Xlog:gc -jar app.jar
~~~

Ghi tất cả nhóm tag có chứa `gc` ở mức `info` vào file:

~~~bash
java -Xlog:gc*=info:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Trong JDK 24.0.2, `java -Xlog:help` liệt kê cú pháp, level, decorator, tag, output và tùy chọn rotation. Tập tag và nội dung log có thể thay đổi theo JDK, vendor và garbage collector.

Với Java 8, cách cấu hình thường gặp là:

~~~bash
java -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:gc.log -jar app.jar
~~~

Các flag cũ thuộc hệ thống GC logging trước Unified Logging. Khi chạy JDK 9+, nên dùng `-Xlog` để chọn tag, level, decorator và output rõ ràng. Không trộn các ví dụ Java 8 với cú pháp Unified Logging mà không kiểm tra runtime đang dùng.

## 3. Cú pháp tổng quát của -Xlog

Cú pháp:

~~~text
-Xlog[:[selections][:[output][:[decorators][:output-options]]]]
~~~

Các phần:

| Thành phần | Ý nghĩa |
|---|---|
| `selections` | Chọn tag set và mức log cần ghi. |
| `output` | Nơi ghi log: stdout, stderr hoặc file. |
| `decorators` | Metadata thêm vào đầu mỗi dòng, ví dụ timestamp, uptime, level, tags. |
| `output-options` | Tùy chọn cho output file như kích thước và số file rotation. |

Ví dụ:

~~~bash
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Có thể đọc theo thứ tự:

1. `gc*=info`: chọn log có tag `gc` ở mức info trở xuống theo độ chi tiết.
2. `file=gc.log`: ghi vào file gc.log.
3. `time,uptime,level,tags`: thêm thời gian, uptime, level và tag.
4. `filecount=5,filesize=20M`: giữ tối đa năm file đã rotation, mỗi file mục tiêu 20 MB.

Nếu bỏ phần output, log mặc định đi ra stdout. Nếu bỏ decorators, JVM dùng bộ decorator mặc định của Unified Logging.

## 4. Tag, tag set và wildcard

Tag xác định nhóm nội dung của log. Ví dụ:

- `gc`: hoạt động GC tổng quát.
- `heap`: thông tin heap.
- `phases`: các phase bên trong collection.
- `ergo`: quyết định ergonomic của JVM.
- `ref`: xử lý reference.
- `metaspace`: class metadata.
- `cpu`: số liệu CPU.
- `safepoint`: hoạt động safepoint.
- `init`: thông tin khởi tạo GC và heap.

Có hai cách kết hợp tag thường gặp:

**Dấu cộng (`+`) yêu cầu các tag cùng xuất hiện trong tag set.**

~~~bash
-Xlog:gc+heap=debug
~~~

Cấu hình này chọn log mang tag set `gc` và `heap`. Không có wildcard thì chỉ tag set khớp chính xác mới được chọn.

**Dấu sao (`*`) là wildcard cho các tag set có chứa tag được chỉ định.**

~~~bash
-Xlog:gc*=info
~~~

Cấu hình này chọn mọi tag set có chứa `gc`, chẳng hạn `gc`, `gc,heap`, `gc,phases` hoặc `gc,metaspace`.

Dấu phẩy phân cách các selection độc lập. Ví dụ:

~~~bash
-Xlog:gc*=info,safepoint*=info
~~~

Lệnh này chọn cả nhóm log GC và nhóm log safepoint. Khi cần phân tích pause, hai nhóm thường hữu ích khi được xem cùng nhau.

Không nhầm `gc+heap` với `gc*`: một lựa chọn là tag set cụ thể, lựa chọn còn lại bao phủ nhiều tag set có chứa gc.

## 5. Các mức log (log levels)

Unified Logging hỗ trợ các mức:

| Level | Mục đích |
|---|---|
| `off` | Tắt log của selection. |
| `error` | Lỗi nghiêm trọng. |
| `warning` | Cảnh báo. |
| `info` | Thông tin vận hành tổng quát. |
| `debug` | Chi tiết phục vụ điều tra. |
| `trace` | Chi tiết rất sâu. |

Mức được chọn là ngưỡng tối đa về độ nghiêm trọng được ghi. Ví dụ `info` bao gồm info, warning và error; `debug` bao gồm debug cùng các mức quan trọng hơn. `trace` tạo lượng log lớn hơn và có thể làm file tăng nhanh.

Ví dụ:

~~~bash
# GC summary thông thường
-Xlog:gc=info

# Chi tiết heap
-Xlog:gc+heap=debug

# Chi tiết các phase
-Xlog:gc+phases=debug

# Quyết định của collector
-Xlog:gc+ergo=debug

# Safepoint
-Xlog:safepoint=info
~~~

Bắt đầu bằng info để theo dõi tổng quan. Chỉ tăng lên debug hoặc trace khi đã xác định cần tìm thêm chi tiết nào.

## 6. Decorators: đọc phần metadata đầu dòng

Decorator bổ sung ngữ cảnh trước nội dung log:

| Decorator | Ý nghĩa |
|---|---|
| `time` | Ngày giờ theo timezone của hệ thống. |
| `utctime` | Ngày giờ UTC. |
| `uptime` | Thời gian kể từ khi JVM khởi động, dạng giây. |
| `timemillis` | Thời gian epoch milliseconds. |
| `uptimemillis` | Uptime milliseconds. |
| `timenanos` | Thời gian epoch nanoseconds. |
| `uptimenanos` | Uptime nanoseconds. |
| `hostname` | Hostname. |
| `pid` | Process ID. |
| `tid` | Thread ID. |
| `level` | Log level. |
| `tags` | Tag set của log event. |

Ví dụ:

~~~bash
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags
~~~

Một dòng log có thể bắt đầu như sau:

~~~text
[2026-11-10T20:10:29.474+0700][0.161s][info][gc,start] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
~~~

Cách đọc:

- `2026-11-10T20:10:29.474+0700`: thời gian theo timezone.
- `0.161s`: JVM đã chạy khoảng 0,161 giây.
- `info`: level của log.
- `gc,start`: tag set.
- Phần sau dấu ngoặc vuông là nội dung event.

Nếu cần so sánh log giữa nhiều máy ở các timezone khác nhau, dùng `utctime` hoặc đồng bộ timezone trước khi phân tích. Nếu cần ghép log với metric theo thời gian JVM, `uptime` rất hữu ích.

Có thể bỏ toàn bộ decorator bằng `none`:

~~~bash
-Xlog:gc=info:stdout:none
~~~

Log lúc này chỉ còn nội dung message, dễ đọc hơn trong một số tình huống nhưng mất ngữ cảnh timestamp và tag.

## 7. Chọn output: stdout, stderr hoặc file

Ghi log ra console:

~~~bash
-Xlog:gc*=info:stdout:uptime,level,tags
~~~

Ghi log ra stderr:

~~~bash
-Xlog:gc*=info:stderr:uptime,level,tags
~~~

Ghi vào file:

~~~bash
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags
~~~

Với ứng dụng server, ghi ra file riêng thường thuận tiện hơn vì:

- Không trộn GC log với application log.
- Có thể đặt retention và rotation riêng.
- Dễ thu thập file khi cần điều tra.
- Dễ tìm các dòng GC theo tag, uptime hoặc GC ID.

Đảm bảo thư mục đã tồn tại và user chạy JVM có quyền ghi. Đường dẫn tương đối được giải quyết theo working directory của process; dùng đường dẫn tuyệt đối khi service có working directory không cố định.

Tên file hỗ trợ placeholder:

- `%p` được thay bằng PID của JVM.
- `%t` được thay bằng timestamp lúc JVM khởi chạy.
- `%hn` được thay bằng hostname.

Ví dụ:

~~~bash
-Xlog:gc*=info:file=gc-%p-%t-%hn.log:time,uptime,level,tags
~~~

Placeholder giúp tránh nhiều JVM ghi trùng một tên file khi chạy trên cùng thư mục chia sẻ.

## 8. Rotation: giới hạn dung lượng và số file

Nếu để GC log tăng vô hạn, file có thể chiếm hết disk. Unified Logging hỗ trợ rotation theo kích thước:

~~~bash
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Ý nghĩa:

- `filesize=20M`: kích thước mục tiêu trước khi kích hoạt rotation.
- `filecount=5`: giữ tối đa năm file đã rotation, không tính file active.
- `filecount=0`: tắt rotation; các file log cũ có thể bị ghi đè khi mở output.
- `filesize=0`: không tự động rotation theo kích thước; có thể rotation thủ công bằng diagnostic command.

Ví dụ fileset có thể gồm:

~~~text
gc.log
gc.log.0
gc.log.1
gc.log.2
gc.log.3
gc.log.4
~~~

Khi file active đạt ngưỡng, JVM xoay các file cũ và tiếp tục ghi file mới. Ngưỡng là kích thước mục tiêu; một file có thể vượt nhẹ ngưỡng do thời điểm kiểm tra và kích thước log record.

Có thể dùng hậu tố `K`, `M` hoặc `G`. Chọn giới hạn dựa trên allocation/GC rate, thời gian cần giữ lịch sử và dung lượng disk được cấp cho ứng dụng.

Nếu cần rotation thủ công, dùng `jcmd PID VM.log rotate=true`. Lệnh này xoay tất cả log output hỗ trợ rotation của JVM đó.

## 9. Cấu hình GC log tổng quan cho production

Một cấu hình phổ biến, đủ để điều tra phần lớn vấn đề GC ban đầu:

~~~bash
java -Xms512m -Xmx2g \
  -Xlog:gc*=info:file=logs/gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
~~~

Cấu hình này:

- Ghi các tag set có chứa `gc`.
- Ghi level info và các mức quan trọng hơn.
- Bao gồm timestamp, uptime, level và tags.
- Ghi ra file có PID và startup timestamp.
- Rotation ở ngưỡng 20 MB, giữ năm file cũ.

Có thể ghi thêm safepoint:

~~~bash
java -Xms512m -Xmx2g \
  -Xlog:gc*=info,safepoint*=info:file=logs/jvm-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
~~~

Dùng chung một file giúp so sánh GC event với safepoint. Nếu muốn tách hai nhóm để thu thập hoặc giữ retention riêng, cấu hình các output riêng và kiểm tra lại command line bằng `-Xlog:help`.

## 10. Bật log chi tiết khi cần điều tra

Khi GC log tổng quan cho thấy vấn đề, tăng độ chi tiết theo đúng khu vực cần kiểm tra.

### Heap và region

~~~bash
-Xlog:gc+heap=debug
~~~

Dùng để xem trạng thái heap và thay đổi các vùng nhớ theo collection. Với G1, log có thể hiển thị Eden, Survivor, Old và Humongous regions trước/sau GC.

### Các phase

~~~bash
-Xlog:gc+phases=debug
~~~

Dùng để xem thời gian từng phase, chẳng hạn evacuation, merge roots hoặc post-evacuation. Nếu tổng pause cao, phase breakdown giúp xác định công đoạn chiếm nhiều thời gian.

### Quyết định của collector

~~~bash
-Xlog:gc+ergo=debug
~~~

Dùng để xem quyết định tự điều chỉnh của JVM như kích thước generation, số worker hoặc lựa chọn collection.

### Reference processing

~~~bash
-Xlog:gc+ref=debug
~~~

Dùng khi nghi ngờ xử lý SoftReference, WeakReference, FinalReference hoặc PhantomReference có liên quan đến thời gian GC.

### Metaspace

~~~bash
-Xlog:gc+metaspace=info
~~~

Dùng để xem thông tin metadata và tác động của class unloading tới memory.

Có thể ghi nhiều nhóm trong cùng một command:

~~~bash
-Xlog:gc*=info,gc+phases=debug,gc+heap=debug
~~~

Nếu chọn debug cho nhiều tag set, log có thể tăng nhanh. Hãy bắt đầu từ một nhóm hẹp và dừng cấu hình chi tiết sau khi thu thập đủ dữ liệu.

## 11. Hiểu GC ID và cách ghép nhiều dòng log

Một collection có thể tạo ra nhiều dòng với cùng GC ID:

~~~text
[0.161s][info][gc,start] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
[0.163s][info][gc,phases] GC(0)   Evacuate Collection Set: 1.67ms
[0.163s][info][gc,heap] GC(0) Eden regions: 17->0(5)
[0.163s][info][gc,heap] GC(0) Survivor regions: 0->3(3)
[0.163s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 17M->15M(32M) 2.242ms
~~~

`GC(0)` là ID của collection trong JVM. Các dòng có cùng ID mô tả các khía cạnh của cùng event. ID tăng dần trong process và hữu ích để ghép start, phases, heap và summary.

Không nên so sánh GC ID giữa hai lần restart JVM như một định danh toàn cục. Sau restart, bộ đếm có thể bắt đầu lại.

Một dòng mở đầu thường cho biết loại collection và nguyên nhân. Dòng summary thường có thông tin heap trước/sau và thời gian pause. Các dòng giữa cung cấp chi tiết phase, region, metaspace và worker.

## 12. Đọc dòng tổng kết pause

Ví dụ:

~~~text
GC(0) Pause Young (Normal) (G1 Evacuation Pause) 17M->15M(32M) 2.242ms
~~~

Diễn giải:

| Thành phần | Ý nghĩa |
|---|---|
| `Pause Young` | Đây là young collection pause. |
| `Normal` | Phân loại collection theo collector. |
| `G1 Evacuation Pause` | G1 thực hiện evacuation pause. |
| `17M` | Heap used trước collection. |
| `15M` | Heap used sau collection. |
| `(32M)` | Heap capacity tại thời điểm ghi. |
| `2.242ms` | Thời gian pause được báo cáo cho event. |

Dạng tổng quát:

~~~text
before->after(capacity) pause-duration
~~~

Đây là số liệu heap tổng quát của event. Không dùng nó để suy ra chính xác live set của từng generation. Với collector khác, nội dung và cách mô tả summary có thể khác.

Một pause ngắn không tự động có nghĩa GC không gây ảnh hưởng. Hãy xem tần suất, tổng thời gian pause, latency của request và khoảng thời gian ứng dụng bị dừng.

## 13. Đọc phase, heap region và CPU

### Phase duration

Ví dụ:

~~~text
GC(0)   Pre Evacuate Collection Set: 0.04ms
GC(0)   Merge Heap Roots: 0.01ms
GC(0)   Evacuate Collection Set: 1.67ms
GC(0)   Post Evacuate Collection Set: 0.16ms
GC(0)   Other: 0.13ms
~~~

Các phase duration giúp xác định phần nào chiếm thời gian. Trong ví dụ, evacuation chiếm phần lớn thời gian của các phase được liệt kê. Tổng các phase có thể không khớp tuyệt đối với tổng pause do cách đo, làm tròn và các phần công việc khác.

### Region changes trong G1

~~~text
GC(0) Eden regions: 17->0(5)
GC(0) Survivor regions: 0->3(3)
GC(0) Old regions: 2->13
GC(0) Humongous regions: 0->0
~~~

Ví dụ:

- Eden giảm từ 17 region xuống 0, capacity mục tiêu hiển thị là 5.
- Survivor tăng từ 0 lên 3 region.
- Old tăng từ 2 lên 13 region do object được promotion hoặc di chuyển.
- Humongous regions không đổi.

Region size được xác định theo heap configuration. Không chuyển số region thành MB nếu chưa biết region size. Log khởi tạo thường có dòng `Heap Region Size`.

### CPU time

Một số log có dạng:

~~~text
GC(0) User=0.00s Sys=0.02s Real=0.00s
~~~

- `User`: CPU time ở user mode của các thread tham gia.
- `Sys`: CPU time ở kernel mode.
- `Real`: thời gian thực tế trôi qua.

Với collection chạy song song, tổng User time có thể lớn hơn Real time vì nhiều worker cùng sử dụng CPU. Đối chiếu CPU với pause duration, worker count và tải hệ thống để hiểu collection có bị giới hạn CPU hay không.

## 14. Phân biệt Young GC, Mixed GC và Full GC

Tên collection trong log phụ thuộc collector:

- **Young GC:** thu gom young generation. Với G1, thường có tên `Pause Young`.
- **Mixed GC:** G1 thu gom young regions và một phần old regions trong cùng collection. Log có thể hiển thị `Pause Young (Mixed)`.
- **Full GC:** collection toàn heap theo cơ chế full collection của collector. Log có thể hiển thị `Pause Full`.

Không phải mọi collector đều dùng cùng tên hoặc cùng chu trình. Ví dụ G1 có concurrent marking cycle, mixed collection và full GC; Serial/Parallel có cách biểu diễn khác.

Một Full GC có thể xuất hiện do allocation failure, explicit GC, metadata pressure hoặc nguyên nhân khác. Xem phần cause trong log và các dòng `gc+ergo` để hiểu quyết định của JVM.

Đừng kết luận Full GC luôn đồng nghĩa memory leak. Cần xem heap occupancy sau Full GC, tần suất lặp lại, allocation rate và object retention.

## 15. Safepoint log và GC pause

GC pause thường cần JVM đưa các thread tới safepoint. Tuy nhiên, không phải mọi safepoint đều là GC và không phải mọi thời gian safepoint đều là thời gian thực hiện GC.

Bật safepoint log:

~~~bash
-Xlog:safepoint=info
~~~

Ghi cả GC và safepoint:

~~~bash
-Xlog:gc*=info,safepoint*=info:file=jvm.log:time,uptime,level,tags
~~~

Safepoint log giúp điều tra thời gian JVM mất để đưa thread tới safepoint và thời gian ở trong safepoint. Nếu ứng dụng có pause dài nhưng GC phase ngắn, kiểm tra safepoint transition và các hoạt động VM khác.

Không cộng mọi safepoint duration vào GC time. Hãy ghép event theo timestamp và nguyên nhân để xác định pause đến từ GC hay một VM operation khác.

## 16. Cấu hình GC logging tại runtime bằng jcmd

Unified Logging có thể thay đổi khi JVM đang chạy mà không cần restart. Dùng diagnostic command `VM.log`.

Xem cấu hình hiện tại:

~~~bash
jcmd 18420 VM.log list=true
~~~

Bật thêm GC output vào file:

~~~bash
jcmd 18420 VM.log output="file=gc-runtime.log" what="gc*=info" decorators="uptime,level,tags" output_options="filecount=3,filesize=20M"
~~~

Kiểm tra lại cấu hình:

~~~bash
jcmd 18420 VM.log list=true
~~~

Xoay tất cả log output:

~~~bash
jcmd 18420 VM.log rotate=true
~~~

`VM.log` có các option chính:

| Option | Ý nghĩa |
|---|---|
| `output` | Tên output hoặc output mới, ví dụ `file=gc-runtime.log`. |
| `what` | Tag selection và level cần ghi. |
| `decorators` | Decorator hiển thị ở mỗi dòng. |
| `output_options` | Rotation và tùy chọn output. |
| `list=true` | Liệt kê log configuration hiện tại. |
| `rotate=true` | Xoay các log output. |
| `disable=true` | Tắt và xóa toàn bộ cấu hình logging. |

`disable=true` tác động tới toàn bộ cấu hình logging của JVM, không chỉ GC output. Chỉ dùng khi có chủ đích tắt toàn bộ log configuration.

Cấu hình runtime chỉ ghi event từ thời điểm bật trở đi; nó không thể khôi phục các GC event đã xảy ra trước đó. Trong thử nghiệm JDK 24.0.2, `VM.log list=true` xác nhận output file mới, selection `gc*=info` và các tùy chọn rotation; `rotate=true` thực hiện rotation thành công.

## 17. Rotation và quản lý file trong thực tế

Ví dụ cấu hình lúc startup:

~~~bash
-Xlog:gc*=info:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Ví dụ runtime:

~~~bash
jcmd 18420 VM.log output="file=logs/gc-runtime.log" what="gc*=info" decorators="time,uptime,level,tags" output_options="filecount=5,filesize=20M"
~~~

Các điểm vận hành:

- Tạo thư mục log trước khi start hoặc bật output.
- Kiểm tra quyền ghi của user chạy JVM.
- Tính tổng dung lượng theo số file rotation và số JVM instance.
- Chuyển file cũ sang hệ thống lưu trữ trước khi bị rotation loại bỏ nếu cần giữ lâu.
- Dùng tên file có PID hoặc timestamp khi nhiều instance cùng ghi.
- Đồng bộ timezone và đồng hồ máy chủ để đối chiếu với application log.
- Không để log chi tiết trace chạy lâu mà không có giới hạn.

Rotation theo kích thước giúp giữ một cửa sổ lịch sử gần nhất. Nó không thay thế chính sách lưu trữ dài hạn hoặc log shipping.

## 18. Ví dụ Java 17 tạo GC log để thực hành

Tạo file `src/GCLogDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GCLogDemo {
    public static void main(String[] args) throws Exception {
        List<byte[]> retained = new ArrayList<>();
        System.out.println("GCLogDemo ready");

        for (int cycle = 1; cycle <= 300; cycle++) {
            for (int i = 0; i < 8; i++) {
                retained.add(new byte[256 * 1024]);
                if (retained.size() > 40) {
                    retained.remove(0);
                }
            }

            if (cycle % 20 == 0) {
                System.gc();
                System.out.println("explicit GC requested at cycle " + cycle);
            }

            Thread.sleep(20);
        }

        System.out.println("GCLogDemo complete");
    }
}
~~~

Chương trình tạo allocation liên tục, giữ lại tối đa 40 array và yêu cầu explicit GC sau mỗi 20 vòng. Mục đích là tạo đủ hoạt động để quan sát log. Không dùng `System.gc()` như cách tối ưu GC trong production.

Biên dịch:

~~~bash
mkdir -p out logs
javac --release 17 -g -d out src/GCLogDemo.java
~~~

Chạy với heap 32 MB và G1:

~~~bash
java -Xms32m -Xmx32m -XX:+UseG1GC -Xlog:gc*=info:file=logs/gc-%p-%t.log:time,uptime,level,tags:filecount=3,filesize=2M -cp out GCLogDemo
~~~

Stdout của chương trình:

~~~text
GCLogDemo ready
explicit GC requested at cycle 20
explicit GC requested at cycle 40
explicit GC requested at cycle 60
explicit GC requested at cycle 80
explicit GC requested at cycle 100
explicit GC requested at cycle 120
explicit GC requested at cycle 140
explicit GC requested at cycle 160
explicit GC requested at cycle 180
explicit GC requested at cycle 200
explicit GC requested at cycle 220
explicit GC requested at cycle 240
explicit GC requested at cycle 260
explicit GC requested at cycle 280
explicit GC requested at cycle 300
GCLogDemo complete
~~~

Số lượng và thời gian GC event phụ thuộc JDK, collector, heap, máy và thời điểm scheduling. Stdout trên là output của chương trình; không suy ra rằng mỗi lời gọi `System.gc()` chắc chắn tạo một Full GC.

## 19. Đọc file log và lọc event cần tìm

Mở file trực tiếp bằng editor hoặc dùng lệnh lọc.

Linux/macOS:

~~~bash
grep -E "Pause Young|Pause Full|System.gc|Metaspace|Humongous" logs/gc-*.log
~~~

Windows PowerShell:

~~~powershell
Select-String -Path logs/gc-*.log -Pattern "Pause Young","Pause Full","System.gc","Metaspace","Humongous"
~~~

Đếm event theo loại:

~~~bash
grep -c "Pause Young" logs/gc.log
grep -c "Pause Full" logs/gc.log
~~~

Để tìm một GC cụ thể, lấy ID từ dòng summary, ví dụ `GC(135)`, rồi lọc các dòng có cùng ID. Khi đọc log đã rotation, có thể phải tìm qua nhiều file.

Không chỉ lọc dòng summary rồi bỏ phần phase. Nếu pause dài, các dòng `gc+phases` và `gc+heap` mới cho biết công việc nào chiếm thời gian và vùng nhớ thay đổi ra sao.

Không viết parser phụ thuộc cứng vào vị trí cột hoặc một chuỗi log duy nhất. Nội dung GC log thay đổi theo collector và phiên bản JDK; nếu cần tự động hóa, hãy cố định JDK/collector và kiểm thử parser với log đại diện từ từng phiên bản.

## 20. Phân tích xu hướng và dấu hiệu bất thường

### Pause dài

Tìm các dòng summary có duration cao, sau đó ghép GC ID với phase log. Nếu một phase chiếm phần lớn pause, xem loại công việc của phase đó. Đối chiếu với latency metrics cùng timestamp.

### Young GC quá dày

Nếu nhiều `Pause Young` xuất hiện sát nhau, ứng dụng có thể đang allocation nhanh. Kiểm tra heap size, allocation rate, object lifetime và thời gian pause. Young GC thường xuyên không tự động là lỗi nếu pause nhỏ và throughput ổn định.

### Old occupancy tăng sau collection

Nếu heap used sau GC tiếp tục tăng, object có thể được promotion hoặc được ứng dụng giữ lại. Kiểm tra old regions, live set sau collection, concurrent marking và Full GC. Dùng heap dump hoặc JFR khi cần xác định object và reference giữ chúng.

### Full GC lặp lại

Tìm cause, heap occupancy trước/sau, metaspace và các thông tin ergonomic. Nếu Full GC liên tục nhưng bộ nhớ thu hồi ít, điều tra memory pressure, object retention và giới hạn heap.

### Evacuation failure hoặc allocation failure

Các thông báo này cho thấy collector không hoàn thành việc di chuyển object hoặc không đáp ứng allocation theo cách dự kiến. Xem phase, region, free space và collector log xung quanh cùng GC ID. Không thay đổi heap flags trước khi hiểu workload và nguyên nhân.

### Metaspace tăng

Tìm các dòng `gc,metaspace` và đối chiếu class loading/unloading. Metaspace tăng có thể bình thường khi ứng dụng nạp class; cần điều tra class loader lifecycle nếu mức sử dụng không ổn định qua nhiều chu kỳ.

### Safepoint dài nhưng GC ngắn

Nếu thời gian pause ứng dụng không khớp với GC duration, xem `safepoint` log và các VM operation khác. GC log và safepoint log bổ sung thông tin cho nhau, không phải hai bộ đếm có thể cộng trực tiếp.

## 21. So sánh GC log với jstat, jcmd và JFR

| Công cụ | Dữ liệu | Phù hợp khi |
|---|---|---|
| GC log | Event timeline, cause, phase, heap change, pause và rotation. | Phân tích GC qua nhiều lần collection. |
| `jstat` | Snapshot memory pool, GC counters và thời gian tích lũy. | Kiểm tra xu hướng nhanh trên JVM đang chạy. |
| `jcmd GC.heap_info` | Heap summary tại thời điểm gọi. | Đối chiếu capacity và cấu trúc heap. |
| JFR | Event runtime theo thời gian, allocation, thread, lock, GC và CPU sampling. | Liên kết GC với hoạt động ứng dụng. |
| Heap dump | Object graph và reference. | Xác định object đang giữ heap khi nghi ngờ leak. |

GC log thường là nguồn chính cho pause timeline. Dùng `jstat` để quan sát nhanh và JFR để ghép GC với allocation, thread và lock. Dùng heap dump khi cần tìm object cụ thể đang giữ bộ nhớ.

## 22. Lỗi thường gặp khi cấu hình và đọc GC log

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không có file log | Sai đường dẫn, thư mục chưa tồn tại hoặc thiếu quyền ghi. | Tạo thư mục và kiểm tra quyền của user chạy JVM. |
| Log chỉ có dòng GC tổng quan | Chọn `gc` thay vì wildcard `gc*` hoặc chưa bật tag chi tiết. | Dùng `-Xlog:gc*=info` và tăng tag cần thiết lên debug. |
| Không thấy phase breakdown | Chưa bật tag `gc+phases` ở mức phù hợp. | Bật `-Xlog:gc+phases=debug`. |
| File log tăng quá nhanh | Chọn trace/debug quá rộng hoặc không có rotation. | Thu hẹp tag/level và đặt filesize/filecount. |
| Log bị ghi đè khi restart | Rotation bị tắt hoặc file name dùng chung. | Bật filecount và dùng `%p`/`%t`. |
| Không tìm thấy log của GC đã xảy ra | Logging được bật sau khi event xảy ra hoặc file cũ đã bị rotation. | Bật từ startup hoặc kiểm tra tất cả file rotation. |
| Không hiểu các dòng cùng event | Chỉ đọc một dòng mà không ghép GC ID. | Tìm toàn bộ dòng cùng `GC(n)`. |
| Thời gian GC và safepoint không giống nhau | Hai số liệu đo phạm vi hoạt động khác nhau. | Đối chiếu event và timestamp, không cộng trực tiếp. |
| Parser hỏng sau khi nâng JDK | Tag, nội dung hoặc định dạng log thay đổi. | Kiểm thử parser theo JDK/collector và tránh giả định cột cố định. |
| Không thể đổi cấu hình runtime | JVM không hỗ trợ diagnostic command hoặc quyền attach không phù hợp. | Kiểm tra `jcmd PID help VM.log` và user/PID namespace. |
| Rotation thủ công không hoạt động | Output không phải file hoặc command nhắm sai JVM. | Xem `jcmd PID VM.log list=true` rồi thử `rotate=true`. |

## 23. Quy trình bật và phân tích GC log trong production

1. Xác định JDK version, JVM vendor, collector, PID và heap flags.
2. Chọn log cơ bản `gc*=info` và decorators gồm time, uptime, level, tags.
3. Ghi vào file riêng, dùng tên có PID/timestamp và đặt rotation.
4. Khởi động ứng dụng hoặc bật logging runtime bằng `jcmd PID VM.log`.
5. Kiểm tra output bằng `VM.log list=true` và xác nhận file đang được ghi.
6. Khi có latency spike, ghi nhận timestamp và tìm các GC ID gần thời điểm đó.
7. Đọc dòng summary để xem loại GC, heap before/after và pause duration.
8. Ghép các dòng phase, heap, metaspace, CPU và safepoint cùng event ID.
9. So sánh nhiều collection để tìm xu hướng thay vì kết luận từ một event.
10. Nếu cần chi tiết hơn, bật tag debug hẹp như `gc+phases` hoặc `gc+heap` trong thời gian điều tra.
11. Đối chiếu với application metrics, JFR, jstat và heap dump khi cần.
12. Lưu file cần thiết trước khi rotation loại bỏ và bảo vệ log theo chính sách dữ liệu nội bộ.

## 24. Tài liệu tham khảo

- [Unified Logging — Java Virtual Machine Guide, JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [The java Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [HotSpot Virtual Machine Garbage Collection Tuning Guide — JDK 24](https://docs.oracle.com/en/java/javase/24/gctuning/)

GC log format trong HotSpot Unified Logging được cấu hình bằng tag selection, level, output, decorators và rotation. Hãy bắt đầu với `-Xlog:gc*=info` để có timeline tổng quan, ghép các dòng bằng GC ID, rồi chỉ bật thêm phase/heap/ergo log khi cần điều tra sâu. Luôn giới hạn dung lượng file, đối chiếu pause với safepoint và application metrics, đồng thời kiểm tra cú pháp trên đúng JDK đang chạy.
