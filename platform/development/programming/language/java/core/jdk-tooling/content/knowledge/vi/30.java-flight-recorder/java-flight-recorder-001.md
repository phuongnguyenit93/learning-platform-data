# JFR là gì? Java Flight Recorder trong JDK

**Java Flight Recorder (JFR)** là hệ thống ghi nhận sự kiện và dữ liệu chẩn đoán của Java Virtual Machine (JVM) theo dòng thời gian. JFR thu thập các sự kiện như CPU sampling, cấp phát object, garbage collection (GC), thread, khóa đồng bộ, I/O, class loading và hoạt động của JIT compiler. Dữ liệu này giúp tìm nguyên nhân ứng dụng chậm, tốn CPU, cấp phát bộ nhớ nhiều, GC kéo dài hoặc bị tranh chấp lock.

JFR được tích hợp trong HotSpot JDK. Có thể bắt đầu recording khi khởi chạy ứng dụng hoặc bật recording trên JVM đang chạy bằng **jcmd**. Dữ liệu được lưu thành file nhị phân có phần mở rộng **.jfr**, sau đó phân tích bằng JDK Mission Control (JMC) hoặc công cụ dòng lệnh **jfr**.

JFR phù hợp để quan sát ứng dụng trong thời gian chạy và thu thập bằng chứng khi có sự cố. Nó không phải bộ ghi log từng dòng code và cũng không đảm bảo ghi lại mọi thao tác của chương trình. Mỗi loại event có cấu hình bật/tắt, ngưỡng và cách thu thập riêng.

## 1. JFR thu thập những dữ liệu gì?

JFR ghi lại các **event** có timestamp và các trường mô tả sự kiện. Tùy loại event, bản ghi có thể chứa thời điểm bắt đầu/kết thúc, thread, class, kích thước, stack trace hoặc thông tin liên quan tới JVM.

| Nhóm | Ví dụ dữ liệu | Câu hỏi có thể điều tra |
|---|---|---|
| CPU và execution | Execution samples, thread CPU load, compiler activity | Thread hoặc method nào tiêu thụ CPU? |
| Memory và allocation | Object allocation samples, heap summary, allocation requiring GC | Ứng dụng cấp phát object ở đâu và với tần suất nào? |
| Garbage collection | Garbage collection, GC phases, heap usage, pause duration | Vì sao GC xảy ra thường xuyên hoặc pause kéo dài? |
| Thread và synchronization | Thread park, monitor enter/wait, thread start/end | Thread đang chờ ở đâu? Có lock contention không? |
| I/O và network | File read/write, socket read/write, file force | Ứng dụng bị chậm do thao tác I/O nào? |
| Class loading | Class load/unload, classloader statistics | Có class được nạp quá nhiều hoặc classloader tồn tại lâu không? |
| Exception và error | Exception throw, error event | Loại exception nào xuất hiện thường xuyên? |
| JVM và OS | JVM flags, system properties, process/OS information | Tiến trình chạy với cấu hình và môi trường nào? |

Không phải tất cả event đều được bật trong mọi recording. Một số event I/O chỉ ghi khi thời gian thao tác vượt ngưỡng; một số event allocation là sampling nên không đại diện cho từng object được cấp phát. Cần đọc event setting và loại event trước khi kết luận từ dữ liệu.

JFR hỗ trợ ba kiểu event thường gặp:

- **Instant event:** xảy ra tại một thời điểm, ví dụ một thao tác hoặc trạng thái được ghi nhận ngay.
- **Duration event:** có thời điểm bắt đầu và kết thúc, ví dụ một lần chờ lock hoặc thao tác I/O.
- **Sample event:** được lấy mẫu theo chu kỳ, ví dụ execution sample để quan sát nơi thread đang chạy.

Một event có stack trace giúp lần ngược từ sự kiện tới method liên quan. Tuy nhiên, stack trace chỉ có khi event được cấu hình thu thập stack và JVM có thể cung cấp dữ liệu đó.

## 2. JFR hoạt động như thế nào?

Khi recording được bật, JVM ghi các event đã cấu hình vào các buffer nội bộ. Recording có thể giữ dữ liệu trong buffer bộ nhớ hoặc ghi ra disk repository tùy cấu hình. Khi cần phân tích, JFR kết xuất dữ liệu thành file .jfr.

~~~text
Java application
       |
       v
HotSpot JVM + JFR event producers
       |
       v
Configured events and buffers
       |
       +------> Disk repository / rolling data
       |
       v
Dump recording to .jfr
       |
       +------> jfr CLI
       |
       +------> JDK Mission Control
       |
       +------> JFR consumer API
~~~

JFR có thể ghi dữ liệu liên tục trong thời gian dài bằng cấu hình phù hợp, hoặc chạy một profiling recording trong khoảng thời gian ngắn. Cấu hình event quyết định lượng dữ liệu và overhead.

JFR thường có overhead thấp khi dùng cấu hình mặc định, nhưng **không phải bằng không**. Recording profile, bật thêm event có stack trace, hạ threshold hoặc thu thập dữ liệu chi tiết có thể tăng CPU, dung lượng file và ảnh hưởng latency. Hãy chọn cấu hình theo mục tiêu điều tra và kiểm tra tác động trong môi trường phù hợp.

## 3. Hai cấu hình có sẵn: default và profile

JDK thường cung cấp hai recording template trong thư mục JAVA_HOME/lib/jfr:

| Template | Đặc điểm | Khi nào dùng |
|---|---|---|
| **default.jfc / default** | Thu thập tập event hữu ích với overhead thấp | Recording liên tục, quan sát production trong thời gian dài |
| **profile.jfc / profile** | Thu thập nhiều thông tin hơn, overhead cao hơn | Profiling ngắn hạn khi cần điều tra sâu |

**default** thường là lựa chọn phù hợp để bắt đầu quan sát lâu dài. **profile** giúp phân tích method, allocation và hoạt động JVM chi tiết hơn nhưng nên dùng trong khoảng thời gian giới hạn.

Các file template nằm trong:

~~~text
<JAVA_HOME>/lib/jfr/default.jfc
<JAVA_HOME>/lib/jfr/profile.jfc
~~~

Không sửa trực tiếp file template đi kèm JDK. Nếu cần thay đổi event, hãy tạo một cấu hình riêng dựa trên template có sẵn rồi sử dụng cấu hình mới cho recording.

## 4. Bắt đầu JFR khi khởi chạy Java

Có thể bật recording ngay khi chạy ứng dụng bằng tùy chọn **-XX:StartFlightRecording**.

Ví dụ recording 60 giây:

~~~sh
java -XX:StartFlightRecording=filename=app-startup.jfr,settings=profile,duration=60s -jar app.jar
~~~

Ý nghĩa:

- **filename=app-startup.jfr**: nơi ghi file recording.
- **settings=profile**: dùng cấu hình profile.
- **duration=60s**: tự dừng recording sau 60 giây.

Nếu muốn bắt đầu sau một khoảng trễ:

~~~sh
java -XX:StartFlightRecording=delay=20s,duration=60s,filename=app.jfr,settings=profile -jar app.jar
~~~

JVM sẽ chờ 20 giây rồi ghi trong 60 giây. Cách này hữu ích khi chỉ muốn thu thập giai đoạn ứng dụng đã khởi động xong hoặc khi một workload cụ thể bắt đầu.

Để chạy continuous recording với dữ liệu lưu trữ có giới hạn:

~~~sh
java -XX:StartFlightRecording=disk=true,settings=default,maxage=6h,maxsize=500m -jar app.jar
~~~

**maxage** và **maxsize** giới hạn dữ liệu lưu giữ trên disk repository. Khi cần lấy dữ liệu để phân tích, có thể dump recording ra một file .jfr.

## 5. Bắt đầu recording trên JVM đang chạy bằng jcmd

Trong nhiều tình huống, ứng dụng đã chạy và bạn không muốn restart. Có thể dùng **jcmd** để điều khiển JFR trên JVM đích.

Liệt kê Java process:

~~~sh
jcmd -l
~~~

Kết quả minh họa:

~~~text
69872 com.example.Server
84664 com.example.Worker
~~~

Chọn PID đúng của ứng dụng cần kiểm tra. Bắt đầu recording:

~~~sh
jcmd 69872 JFR.start name=Incident settings=profile duration=60s filename=incident.jfr
~~~

Một recording liên tục có thể được bắt đầu như sau:

~~~sh
jcmd 69872 JFR.start name=Continuous settings=default disk=true maxage=2h maxsize=500m
~~~

Một số tham số thường dùng:

| Tham số | Ý nghĩa |
|---|---|
| **name** | Tên recording để dùng khi check/dump/stop |
| **settings** | Template default, profile hoặc file .jfc |
| **duration** | Thời gian recording chạy trước khi tự dừng |
| **filename** | Đường dẫn file ghi khi recording dừng |
| **disk** | Cho phép ghi dữ liệu recording xuống disk trong lúc chạy |
| **maxage** | Giới hạn tuổi dữ liệu lưu trên disk repository |
| **maxsize** | Giới hạn kích thước dữ liệu lưu trên disk |

Xem command mà JVM đích hỗ trợ:

~~~sh
jcmd 69872 help JFR.start
jcmd 69872 help JFR.dump
jcmd 69872 help JFR.stop
~~~

Danh sách tham số có thể thay đổi theo JDK. Hãy xem **help** trên JVM thực tế trước khi dùng option nâng cao.

## 6. Kiểm tra, dump và dừng recording

Sau khi bắt đầu recording, có thể kiểm tra trạng thái:

~~~sh
jcmd 69872 JFR.check
~~~

Hoặc xem chi tiết một recording:

~~~sh
jcmd 69872 JFR.check name=Incident verbose=true
~~~

Dump dữ liệu hiện tại ra file mà không cần dừng recording:

~~~sh
jcmd 69872 JFR.dump name=Incident filename=incident-snapshot.jfr
~~~

**JFR.dump** tạo bản ghi file từ dữ liệu recording tại thời điểm dump; recording đang chạy vẫn có thể tiếp tục thu thập event.

Khi muốn dừng recording và lưu file:

~~~sh
jcmd 69872 JFR.stop name=Incident filename=incident-final.jfr
~~~

Nếu đã dump bằng **JFR.dump**, có thể dừng recording sau đó:

~~~sh
jcmd 69872 JFR.stop name=Continuous
~~~

Lưu ý: nếu gọi **JFR.stop** mà không cung cấp **filename**, dữ liệu recording có thể bị loại bỏ khi dừng. Hãy dump hoặc chỉ định filename nếu cần giữ lại dữ liệu.

Quy trình điều khiển thường dùng:

1. **jcmd <pid> JFR.start ...** để bắt đầu.
2. **jcmd <pid> JFR.check** để xác nhận recording đang chạy.
3. **jcmd <pid> JFR.dump ...** để lưu snapshot nếu muốn tiếp tục thu thập.
4. **jcmd <pid> JFR.stop ...** để dừng và lưu file cuối.

## 7. Đọc file recording bằng lệnh jfr

JDK cung cấp công cụ **jfr** để kiểm tra file .jfr mà không cần mở giao diện đồ họa.

Xem tổng quan recording:

~~~sh
jfr summary incident.jfr
~~~

Output hiển thị phiên bản recording, thời lượng, số chunk, từng loại event, số lượng và kích thước dữ liệu. Đây là bước đầu tiên để biết recording có chứa event mà bạn cần hay không.

In event ra terminal:

~~~sh
jfr print incident.jfr
~~~

Chỉ in các event cần điều tra:

~~~sh
jfr print --events jdk.ObjectAllocationSample,jdk.GarbageCollection incident.jfr
~~~

Một số event thường xem:

- **jdk.ExecutionSample**: sample về nơi thread đang thực thi.
- **jdk.ObjectAllocationSample**: sample về cấp phát object.
- **jdk.GarbageCollection**: thông tin lần GC.
- **jdk.JavaMonitorEnter**: thời gian chờ vào monitor/lock.
- **jdk.SocketRead** và **jdk.SocketWrite**: thao tác socket khi event được bật.
- **jdk.FileRead** và **jdk.FileWrite**: thao tác file khi event được bật.

Ví dụ chỉ xem allocation sample:

~~~sh
jfr print --events jdk.ObjectAllocationSample incident.jfr
~~~

Kết quả event có thể gồm:

~~~text
jdk.ObjectAllocationSample {
  startTime = 19:34:05.700
  objectClass = byte[]
  weight = 21.7 MB
  eventThread = "main"
  stackTrace = [
    com.example.Worker.run() line: 42
  ]
}
~~~

Đây là output minh họa. **weight** trong allocation sample là trọng số ước lượng mà JFR dùng để biểu diễn lượng cấp phát được sample; không được hiểu là một object duy nhất có kích thước bằng toàn bộ weight.

Xem các event metadata có trong recording:

~~~sh
jfr metadata incident.jfr
~~~

Xem các lệnh và tùy chọn của tool:

~~~sh
jfr help
jfr help print
~~~

## 8. Phân tích bằng JDK Mission Control

**JDK Mission Control (JMC)** là công cụ đồ họa để mở và phân tích file .jfr. JMC cung cấp các view giúp tìm vấn đề mà việc đọc output text khó thể hiện.

| View / nhóm | Nội dung cần xem |
|---|---|
| General | Thời lượng recording, JVM, hệ điều hành, thông tin tổng quan |
| Method Profiling | Method và stack trace có nhiều execution sample |
| Threads | Thread state, thread activity và thời gian chờ |
| Memory | Heap usage, allocation, object và GC |
| Garbage Collections | Số lần GC, thời gian pause, các phase |
| Locks | Monitor contention, thread chờ lock |
| I/O | File/socket operation và thời gian thực hiện |
| Exceptions | Exception event khi đã bật cấu hình tương ứng |

Khi CPU tăng cao, mở Method Profiling để xem stack trace nào xuất hiện nhiều trong execution samples. Khi heap tăng nhanh, xem allocation và GC để tìm class cấp phát nhiều. Khi ứng dụng phản hồi chậm nhưng CPU thấp, xem thread state, monitor contention và I/O.

Không nên chỉ nhìn một biểu đồ để kết luận. Hãy đối chiếu timestamp, workload, thread, stack trace và các event liên quan trong cùng khoảng thời gian.

## 9. Các tình huống JFR giúp điều tra

### 9.1. CPU cao

Triệu chứng: CPU process tăng mạnh trong khi request chậm.

1. Tạo recording với **settings=profile**.
2. Mở Method Profiling hoặc xem **jdk.ExecutionSample**.
3. Tìm stack trace xuất hiện thường xuyên.
4. Kiểm tra vòng lặp tốn CPU, xử lý dữ liệu lớn, regex, serialization hoặc code được gọi quá nhiều.
5. Sửa bottleneck và ghi recording mới để so sánh.

Execution sample là lấy mẫu tại các thời điểm; nó giúp ước lượng nơi CPU được sử dụng, không phải danh sách đầy đủ mọi lần gọi method.

### 9.2. Allocation cao hoặc nghi ngờ memory leak

Triệu chứng: heap tăng theo workload, GC thường xuyên hoặc bộ nhớ không giảm sau khi tải kết thúc.

1. Xem allocation sample và stack trace để tìm vị trí tạo object.
2. Xem GC event và heap summary để hiểu tác động tới heap.
3. So sánh recording trong các giai đoạn workload tương đương.
4. Nếu nghi ngờ leak, cân nhắc cấu hình event memory leak hoặc thu thập path to GC roots theo hướng dẫn JDK.
5. Phân tích heap dump khi cần xác định object nào đang giữ tham chiếu.

**path-to-gc-roots** có thể tốn thời gian và gây pause ngắn. Chỉ bật khi đã có giả thuyết memory leak; không bật thường xuyên chỉ để thu thập mọi thứ.

### 9.3. Thread bị block hoặc lock contention

Triệu chứng: throughput giảm, request chờ lâu dù CPU không cao.

1. Xem **jdk.JavaMonitorEnter** và các event liên quan tới thread/lock.
2. Tìm thread chờ monitor trong thời gian dài.
3. Đọc stack trace để xác định đoạn code giữ lock.
4. Kiểm tra vùng synchronized quá rộng, lock ordering hoặc tác vụ I/O chạy bên trong lock.
5. Đo lại sau khi tối ưu.

### 9.4. I/O chậm

Triệu chứng: request chậm nhưng CPU thấp và thread thường chờ.

1. Xem file/socket event nếu recording đã bật chúng.
2. Tìm thao tác có duration cao hoặc xuất hiện thường xuyên.
3. Đối chiếu với thread và stack trace.
4. Kiểm tra filesystem, network, remote service, timeout và kích thước payload.
5. Điều chỉnh event threshold nếu cần thêm dữ liệu, đồng thời cân nhắc overhead.

## 10. Tùy chỉnh event và recording template

Nếu template mặc định không thu thập event cần thiết, có thể tạo file cấu hình .jfc tùy chỉnh. JDK cung cấp lệnh:

~~~sh
jfr configure --interactive
~~~

Có thể sao chép template profile.jfc từ JAVA_HOME/lib/jfr về thư mục làm việc, rồi tạo cấu hình riêng:

~~~sh
jfr configure --input profile.jfc --output custom.jfc
~~~

Cấu hình được truyền khi bắt đầu recording:

~~~sh
jcmd 69872 JFR.start name=Custom settings=C:/jfr/custom.jfc duration=60s filename=custom.jfr
~~~

Event setting có thể bật/tắt event, bật stack trace, đặt threshold hoặc điều chỉnh chu kỳ lấy mẫu. Với event duration, threshold giúp chỉ ghi những thao tác đủ dài để điều tra bottleneck. Threshold quá thấp có thể làm recording tăng kích thước và overhead.

Không bật tất cả event cùng lúc mà không có mục tiêu cụ thể. Hãy bắt đầu từ template phù hợp, bật thêm event liên quan tới giả thuyết và ghi nhận thay đổi cấu hình để có thể lặp lại phép đo.

## 11. JFR API và custom event

Ngoài công cụ dòng lệnh, ứng dụng có thể dùng module **jdk.jfr** để tạo custom event cho nghiệp vụ. Ví dụ, hệ thống có thể ghi event khi xử lý một đơn hàng, hoàn tất một batch hoặc gọi một bước xử lý quan trọng.

Ví dụ minh họa custom event:

~~~java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.example.OrderProcessed")
@Label("Order Processed")
@Category({"Application", "Orders"})
class OrderProcessed extends Event {
    @Label("Order ID")
    String orderId;

    @Label("Item Count")
    int itemCount;
}
~~~

Khi muốn ghi event trong code:

~~~java
OrderProcessed event = new OrderProcessed();
event.orderId = "ORD-1001";
event.itemCount = 3;
event.begin();
processOrder();
event.end();
event.commit();
~~~

Đây là đoạn code minh họa cách định nghĩa và phát event; **processOrder()** đại diện cho logic nghiệp vụ của ứng dụng. Trong dự án thực tế, nên kiểm tra **event.shouldCommit()** trước khi tính toán dữ liệu đắt tiền chỉ phục vụ event. Phương thức này xét cả trạng thái bật của event và threshold đang áp dụng. Event class mặc định được bật, trừ khi bị đánh dấu **@Enabled(false)** hoặc bị tắt trong recording settings. Event chỉ được ghi khi có recording đang chạy và event đang được bật.

Custom event giúp nối thông tin nghiệp vụ với các event JVM. Khi phân tích, bạn có thể đặt thời gian xử lý một đơn hàng cạnh allocation, GC, thread và I/O xảy ra trong cùng khoảng thời gian.

## 12. JFR khác gì với log, JMX và profiler?

| Công cụ | Thông tin chính | Điểm mạnh |
|---|---|---|
| Application log | Message nghiệp vụ do ứng dụng chủ động ghi | Theo dõi lỗi, trạng thái và hành động nghiệp vụ |
| JMX / MXBean | Gauge, counter và trạng thái quản trị JVM | Đọc metric hiện tại và tích hợp monitoring |
| JFR | Event có timestamp, duration, stack và dữ liệu JVM/OS | Điều tra nguyên nhân theo timeline |
| CPU profiler | Stack sample hoặc instrumentation tập trung vào CPU | Tìm method tiêu thụ CPU |
| Heap dump | Snapshot object và reference graph | Phân tích object đang giữ bộ nhớ |

JFR bổ sung cho log và metrics. Ví dụ, log có thể cho biết request bị timeout; JFR có thể cho thấy trong cùng khoảng thời gian thread chờ socket, bị block ở monitor hay bị ảnh hưởng bởi GC.

JFR không thay thế application log vì nó không tự hiểu toàn bộ ngữ nghĩa nghiệp vụ. Nó cũng không thay thế heap dump khi cần phân tích chi tiết reference graph hoặc retained heap.

## 13. Tác động hiệu năng và cách dùng trong production

JFR được thiết kế cho chẩn đoán JVM với overhead thấp khi dùng cấu hình phù hợp. Tuy vậy, overhead phụ thuộc event, threshold, stack trace, tần suất sample, kích thước heap, workload và thời gian recording.

- Dùng **default** cho recording liên tục và giới hạn **maxage/maxsize**.
- Dùng **profile** trong thời gian ngắn khi cần nhiều dữ liệu hơn.
- Chỉ bật event bổ sung khi có giả thuyết cụ thể.
- Không đặt threshold quá thấp nếu chưa đánh giá lượng event và overhead.
- Dùng **duration** để tự kết thúc recording ngắn hạn.
- Kiểm tra dung lượng disk repository và thư mục chứa file .jfr.
- Theo dõi latency/CPU trong khi recording, đặc biệt khi cấu hình nhiều event.
- Thử cấu hình trên staging hoặc replica trước khi triển khai rộng.

JFR không phải công cụ “zero overhead”. Một số diagnostic command có thể tạo tác động đáng kể tùy thao tác và dung lượng heap. Đọc impact trong **jcmd <pid> help JFR.start** và hướng dẫn của JDK trước khi bật cấu hình chuyên sâu.

## 14. Bảo mật dữ liệu recording

File .jfr có thể chứa thông tin nhạy cảm:

- Tên class, method, package và stack trace nội bộ.
- Đường dẫn file, tên process và thông tin hệ điều hành.
- System properties và một số environment variable được ghi nhận.
- Endpoint, tên host, thông tin I/O hoặc dữ liệu nghiệp vụ xuất hiện trong custom event.
- Thông tin thread, request context hoặc dữ liệu được ứng dụng gắn vào event.

Hãy xem .jfr là dữ liệu chẩn đoán nội bộ:

1. Lưu file trong thư mục có quyền truy cập giới hạn.
2. Không commit recording vào repository hoặc tải lên nơi công khai.
3. Che hoặc loại bỏ dữ liệu nhạy cảm trước khi chia sẻ với bên ngoài.
4. Dùng công cụ scrub hoặc cấu hình event để giảm dữ liệu không cần thiết.
5. Xóa recording và bản sao theo chính sách lưu trữ của tổ chức.

Không đưa password, token hoặc dữ liệu cá nhân vào custom event. Stack trace và tên property cũng có thể tiết lộ cấu trúc hệ thống.

## 15. Ví dụ thực hành hoàn chỉnh với Java 17+

Ví dụ sau tạo workload có cấp phát mảng byte liên tục. Bạn sẽ khởi chạy ứng dụng, bật recording bằng **jcmd**, dump file, rồi dùng **jfr** để đọc allocation sample.

Tạo file **JfrProbe.java**:

~~~java
public class JfrProbe {
    static final byte[][] retained = new byte[200][];

    public static void main(String[] args) throws InterruptedException {
        int next = 0;
        System.out.println("jfr-probe-ready");

        while (true) {
            retained[next] = new byte[64 * 1024];
            next = (next + 1) % retained.length;
            Thread.sleep(20);
        }
    }
}
~~~

Biên dịch:

~~~sh
mkdir -p out
javac --release 17 -d out JfrProbe.java
~~~

Chạy chương trình:

~~~sh
java -Xms128m -Xmx128m -cp out JfrProbe
~~~

Stdout chính xác khi ứng dụng khởi động:

~~~text
jfr-probe-ready
~~~

Giữ terminal này mở. Mở terminal thứ hai, tìm PID:

~~~sh
jcmd -l
~~~

Giả sử PID là **69872**. Bắt đầu recording:

~~~sh
jcmd 69872 JFR.start name=Demo settings=profile disk=true maxage=2m maxsize=64m
~~~

Kiểm tra recording:

~~~sh
jcmd 69872 JFR.check name=Demo
~~~

Lấy snapshot ra file:

~~~sh
jcmd 69872 JFR.dump name=Demo filename=demo.jfr
~~~

Đọc tổng quan:

~~~sh
jfr summary demo.jfr
~~~

Xem allocation sample:

~~~sh
jfr print --events jdk.ObjectAllocationSample demo.jfr
~~~

Dừng recording:

~~~sh
jcmd 69872 JFR.stop name=Demo
~~~

Trong thử nghiệm với JDK 24.0.2, **JfrProbe** biên dịch bằng **javac --release 17** và in chính xác **jfr-probe-ready**. Recording profile thực tế được tạo, kiểm tra, dump và dừng thành công. **jfr summary** báo recording khoảng 2 giây với 253 KB dữ liệu; **jfr print** hiển thị class **byte[]**, thread **main** và stack trace trỏ tới **JfrProbe.main**. Các con số này chỉ là kết quả của lần chạy thử, không phải output cố định.

Khi hoàn tất, quay lại terminal chạy **JfrProbe** và nhấn **Ctrl+C** để kết thúc JVM.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Unknown diagnostic command: JFR.start | JVM không hỗ trợ JFR hoặc command không có trên runtime đích | Kiểm tra JDK/JVM và **jcmd <pid> help** |
| Không attach được vào PID | Sai PID, sai user, JVM đã dừng hoặc attach bị vô hiệu hóa | Xác định PID lại và kiểm tra quyền attach |
| JFR.start chạy nhưng không thấy file | Recording chưa dump, chưa stop có filename hoặc đường dẫn không hợp lệ | Dùng **JFR.dump** hoặc **JFR.stop ... filename=...** |
| JFR.check không hiển thị recording mong đợi | Tên recording sai hoặc recording đã kết thúc | Kiểm tra tất cả recording không truyền name rồi xác định đúng ID/tên |
| File .jfr quá lớn | Dùng profile quá lâu hoặc bật quá nhiều event | Dùng default, giới hạn maxage/maxsize và rút ngắn thời gian |
| Không thấy event mong đợi | Event bị tắt, threshold quá cao hoặc loại recording không thu thập event đó | Xem event settings, metadata và cấu hình .jfc |
| Allocation sample không khớp số object thực tế | Đây là dữ liệu sampling, không phải log mọi allocation | Dùng weight như ước lượng và chọn event/config phù hợp |
| JFR làm ứng dụng chậm hơn | Recording profile hoặc event chi tiết gây overhead | Giảm event, tăng threshold, dùng default hoặc thu ngắn thời gian |
| Không mở được file | File chưa hoàn chỉnh, bị ghi dở hoặc tool không tương thích | Kiểm tra **JFR.stop**/dump đã hoàn tất và dùng JDK/JMC phù hợp |
| Không có stack trace | Event setting không bật stack trace hoặc event không hỗ trợ | Kiểm tra cấu hình event cụ thể |
| Recording không đủ thời gian sự cố | Bắt đầu quá muộn hoặc chỉ dùng recording ngắn | Dùng continuous recording với giới hạn maxage/maxsize rồi dump khi có sự cố |

## 17. Quy trình điều tra bằng JFR

1. Xác định triệu chứng: CPU cao, GC nhiều, allocation cao, lock contention, I/O chậm hay exception.
2. Xác định JVM/PID bằng **jcmd -l**.
3. Chọn **default** cho continuous recording hoặc **profile** cho profiling ngắn.
4. Bắt đầu recording bằng **-XX:StartFlightRecording** hoặc **jcmd JFR.start**.
5. Xác nhận bằng **JFR.check**.
6. Tái hiện workload hoặc chờ sự cố trong thời gian recording.
7. Dump dữ liệu bằng **JFR.dump** hoặc dừng và lưu bằng **JFR.stop filename=...**.
8. Kiểm tra recording bằng **jfr summary**.
9. Mở file bằng JMC hoặc lọc event bằng **jfr print**.
10. Đối chiếu timestamp, thread, event, stack trace và workload để tìm nguyên nhân.
11. Đề xuất thay đổi, đo lại bằng recording tương đương và so sánh.
12. Bảo vệ file .jfr và xóa theo chính sách dữ liệu.

### Checklist

- [ ] Đã xác định đúng JVM/PID.
- [ ] Đã chọn template phù hợp với mục tiêu và thời lượng.
- [ ] Đã kiểm tra recording bằng **JFR.check**.
- [ ] Đã dump hoặc stop với filename để lưu dữ liệu.
- [ ] Đã xem **jfr summary** và xác nhận có event cần thiết.
- [ ] Đã phân biệt event sampling với event ghi nhận từng thao tác.
- [ ] Đã phân tích timestamp, thread và stack trace trong bối cảnh workload.
- [ ] Đã đánh giá overhead, dung lượng file và tác động tới latency.
- [ ] Đã bảo vệ recording vì có thể chứa thông tin nhạy cảm.
- [ ] Đã so sánh recording trước/sau khi thay đổi để xác nhận kết quả.

Java Flight Recorder cung cấp dữ liệu sự kiện có thời gian và ngữ cảnh để điều tra hoạt động bên trong JVM. Khi chọn đúng template, giới hạn thời gian/dung lượng recording và kết hợp **jcmd**, **jfr** hoặc JMC, bạn có thể thu thập bằng chứng về CPU, memory, GC, thread và I/O để tìm nguyên nhân sự cố mà không cần thêm logging thủ công cho mọi điểm trong ứng dụng.

## Tài liệu tham khảo

- [Oracle JDK 24 — Diagnostic Tools: Java Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle JDK 24 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html)
- [Oracle JDK 24 — JFR Recording API](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle JDK 24 — JFR Event API](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Oracle JDK Mission Control 9 — User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)