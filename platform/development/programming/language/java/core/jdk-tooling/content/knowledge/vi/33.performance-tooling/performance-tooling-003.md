# Đo allocation trong Java

**Allocation** là quá trình JVM cấp phát bộ nhớ heap cho object và array mới. Đo allocation giúp biết ứng dụng tạo ra bao nhiêu byte object trong một khoảng thời gian, class nào được tạo nhiều, method nào là allocation site chính và thread nào tạo nhiều object nhất.

Allocation rate cao có thể làm Eden đầy nhanh, tăng tần suất garbage collection (GC), tăng CPU dành cho GC và ảnh hưởng throughput. Tuy nhiên, allocation cao không tự động là memory leak: nhiều object chỉ sống ngắn rồi được GC thu hồi. Muốn hiểu vấn đề, cần đo lượng object được tạo, lượng object còn sống sau GC và code path thực hiện cấp phát.

Các công cụ thường dùng:

- **Java Flight Recorder (JFR) và JDK Mission Control (JMC)**: tìm class, thread và stack trace tạo nhiều object.
- **ThreadMXBean**: đo gần đúng số byte heap được cấp phát bởi một platform thread.
- **JMH với GC profiler**: đo allocation trên mỗi operation trong benchmark.
- **jstat và GC logs**: quan sát allocation pressure gián tiếp qua Eden, heap và GC.

## 1. Allocation là gì và tại sao cần đo?

Khi code chạy lệnh \`new\`, JVM cấp phát vùng nhớ cho object. Ví dụ:

~~~java
Customer customer = new Customer();
byte[] payload = new byte[4096];
List<String> names = new ArrayList<>();
~~~

Mỗi object hoặc array được cấp phát làm tăng lượng heap đang sử dụng. Ứng dụng thường tạo nhiều object ngắn hạn như request DTO, iterator, temporary String, wrapper, collection trung gian và buffer.

Nếu object không còn reachable, GC có thể thu hồi chúng. Việc tạo rồi thu hồi object vẫn có chi phí:

- JVM phải cấp phát bộ nhớ và cập nhật metadata.
- TLAB có thể đầy và cần được cấp mới.
- GC phải tìm và thu hồi object không còn sống.
- Allocation và GC có thể làm tăng CPU usage.
- GC pause hoặc hoạt động concurrent có thể ảnh hưởng latency và throughput.

Đo allocation trả lời các câu hỏi:

- Ứng dụng cấp phát bao nhiêu MB mỗi giây?
- Mỗi request hoặc operation tạo bao nhiêu byte?
- Class nào được cấp phát nhiều nhất?
- Method nào là allocation site chính?
- Thread nào tạo nhiều object?
- Object được cấp phát trong TLAB hay ngoài TLAB?
- Allocation tăng có làm GC thường xuyên hơn không?

## 2. Phân biệt allocation, live set, retained heap và RSS

Đây là bốn số liệu khác nhau.

| Khái niệm | Ý nghĩa | Câu hỏi |
|---|---|---|
| Allocation | Tổng lượng object mới được tạo trong khoảng đo | Ứng dụng tạo bao nhiêu byte? |
| Live set | Lượng object còn sống sau khi GC thu hồi object không còn reachable | Bao nhiêu byte vẫn cần giữ? |
| Retained heap | Lượng heap có thể được thu hồi nếu object đang xét không còn reachable | Object nào đang giữ bộ nhớ? |
| RSS | Bộ nhớ resident của process trong hệ điều hành | Process đang chiếm bao nhiêu RAM? |

Ví dụ một request tạo 10 MB object tạm thời nhưng chỉ giữ lại 100 KB sau xử lý:

- Allocation của request: khoảng 10 MB.
- Live set tăng thêm sau request: có thể chỉ khoảng 100 KB.
- Retained heap phụ thuộc các reference giữ object sống.
- RSS còn phụ thuộc native memory, metaspace, thread stack và các vùng khác.

Ứng dụng có thể có allocation rate cao nhưng live set ổn định. Đây thường là allocation pressure, không nhất thiết là memory leak.

Ngược lại, allocation rate không quá cao nhưng live set tăng liên tục có thể là dấu hiệu object bị giữ lại ngoài dự kiến.

## 3. Các đơn vị và công thức đo allocation

### Allocation rate

Allocation rate là lượng bộ nhớ được cấp phát trên một đơn vị thời gian:

\[
\text{Allocation rate} =
\frac{\text{allocated bytes}_{after}-\text{allocated bytes}_{before}}
{\text{elapsed seconds}}
\]

Ví dụ trong 10 giây, một thread cấp phát thêm 200 MB:

\[
200/10 = 20\ \text{MB/s}
\]

Ghi rõ MB là \(10^6\) byte hay MiB là \(2^{20}\) byte vì công cụ có thể dùng quy ước khác nhau.

### Bytes per operation

Khi đo workload có số operation xác định:

\[
\text{Bytes/op} =
\frac{\Delta \text{allocated bytes}}{\text{operation count}}
\]

Nếu 100.000 operation tạo tổng cộng 50 MiB:

\[
50 \times 1024^2 / 100000 = 524.29\ \text{B/op}
\]

Chỉ số này hữu ích khi so sánh hai cách triển khai cùng một chức năng.

### Allocation theo thread

Với từng thread:

\[
\text{Thread allocation rate} =
\frac{\text{allocated bytes của thread trong khoảng đo}}
{\text{elapsed seconds}}
\]

So sánh theo thread giúp tìm worker hoặc request handler tạo nhiều object nhất.

### Dùng delta thay vì counter tuyệt đối

Nhiều API cung cấp tổng allocation tích lũy từ khi JVM hoặc thread khởi chạy. Hãy lấy hai snapshot:

~~~text
allocated_before = 120,000,000 bytes
allocated_after  = 220,000,000 bytes
delta            = 100,000,000 bytes
~~~

Không dùng giá trị tích lũy trực tiếp để kết luận allocation rate của một request hoặc một khoảng thời gian.

## 4. TLAB và allocation ngoài TLAB

HotSpot thường sử dụng **Thread Local Allocation Buffer (TLAB)** để cấp phát object nhỏ nhanh hơn.

TLAB là vùng heap dành riêng cho một thread. Khi thread tạo object phù hợp, JVM có thể cấp phát bằng cách di chuyển con trỏ trong TLAB thay vì đồng bộ với các thread khác cho từng object.

~~~text
Java heap
+----------------------------------------------------+
| TLAB của thread A | TLAB của thread B | vùng khác  |
| [obj][obj][obj]   | [obj][obj]        |            |
+----------------------------------------------------+
       |                    |
       v                    v
  Thread A              Thread B
~~~

Khi TLAB gần đầy, thread cần một TLAB mới. Object lớn hoặc không phù hợp với TLAB có thể được cấp phát trực tiếp ngoài TLAB.

| Nhóm allocation | Đặc điểm |
|---|---|
| In TLAB | Thường là object nhỏ, cấp phát trong vùng riêng của thread |
| Outside TLAB | Object được cấp phát trực tiếp ngoài TLAB |
| TLAB refill | Thread cần cấp một TLAB mới khi vùng hiện tại không còn đủ chỗ |

TLAB giảm contention trong đường cấp phát object. Allocation trong TLAB vẫn chiếm heap và vẫn phải được GC xử lý khi object không còn reachable.

## 5. Đo allocation bằng Java Flight Recorder

JFR phù hợp để tìm allocation site trong ứng dụng đang chạy. Recording có thể chứa thông tin về class được tạo, thread, kích thước allocation và stack trace tùy event/settings.

Các event thường dùng:

| Event | Mục đích |
|---|---|
| \`jdk.ObjectAllocationInNewTLAB\` | Allocation liên quan đến việc cấp TLAB mới |
| \`jdk.ObjectAllocationOutsideTLAB\` | Object được cấp phát ngoài TLAB |
| \`jdk.ThreadAllocationStatistics\` | Thống kê allocation theo thread |

Event và field khả dụng có thể thay đổi theo JDK/JVM. Kiểm tra metadata và settings của recording thực tế.

### Chọn recording settings

Template \`default.jfc\` được thiết kế cho continuous recording có overhead thấp. Trong JDK 26, continuous recording với default template không thu thập allocation profiling.

Template \`profile.jfc\` thu thập nhiều dữ liệu hơn, phù hợp với profiling trong một khoảng thời gian ngắn. Recording có thể tạo nhiều dữ liệu và overhead cao hơn.

Không bật allocation profiling chi tiết vô thời hạn trên production nếu chưa đánh giá overhead và dung lượng.

### Bắt đầu recording bằng jcmd

Tìm JVM:

~~~bash
jcmd -l
~~~

Giả sử PID ứng dụng là 2125. Bắt đầu recording 60 giây:

~~~bash
jcmd 2125 JFR.start name=allocation settings=profile duration=60s filename=allocation.jfr
~~~

Kiểm tra recording:

~~~bash
jcmd 2125 JFR.check
~~~

Dừng sớm và lưu file nếu cần:

~~~bash
jcmd 2125 JFR.stop name=allocation filename=allocation-final.jfr
~~~

Dùng PID thật. jcmd cần chạy trên cùng máy và bằng effective user/group phù hợp với process đích.

### Đọc allocation events

Xem summary:

~~~bash
jfr summary allocation.jfr
~~~

Lọc allocation events:

~~~bash
jfr print --events jdk.ObjectAllocationInNewTLAB,jdk.ObjectAllocationOutsideTLAB,jdk.ThreadAllocationStatistics allocation.jfr
~~~

Xem metadata:

~~~bash
jfr metadata allocation.jfr
~~~

Nếu event không xuất hiện, kiểm tra template và active settings trước khi kết luận rằng ứng dụng không cấp phát object.

## 6. Phân tích allocation bằng JDK Mission Control

JMC cung cấp trang **TLAB Allocations** để xem allocation trong TLAB và ngoài TLAB.

| View | Câu hỏi |
|---|---|
| Allocation by Class | Class nào được cấp phát nhiều nhất? |
| Allocation by Thread | Thread nào tạo nhiều object nhất? |
| Allocation Profile | Stack trace nào tạo nhiều allocation? |
| By Top Methods | Method nào tạo nhiều allocation? |
| Alloc Total | Tổng lượng allocation theo thời gian là bao nhiêu? |

Quy trình:

1. Mở file allocation.jfr trong JMC.
2. Xác nhận thời gian recording và workload.
3. Mở trang Memory hoặc TLAB Allocations.
4. Xem Allocation by Class để tìm class có allocation lớn.
5. Xem Allocation by Thread để tìm thread tạo nhiều object.
6. Mở Allocation Profile để xem stack trace tổng hợp.
7. Chọn top method và mở source code tương ứng.
8. Kiểm tra object được tạo trong vòng lặp, mapping, serialization hay xử lý request.
9. Đối chiếu allocation với GC events và heap usage.
10. Đo lại sau khi tối ưu bằng cùng workload.

Không chỉ nhìn số lượng instance. Một class có nhiều instance nhỏ có thể tiêu tốn ít bộ nhớ hơn một class tạo ít instance nhưng mỗi instance chứa array lớn.

### Đọc allocation profile

Ví dụ minh họa:

~~~text
com.acme.OrderService.process
  com.acme.OrderMapper.map
    java.lang.String
    java.util.ArrayList
    byte[]
  com.acme.JsonEncoder.encode
    byte[]
~~~

Nếu byte[] xuất hiện nhiều dưới JsonEncoder, hãy kiểm tra việc encode có tạo buffer trung gian hoặc copy dữ liệu nhiều lần không.

Stack trace giúp xác định allocation site. Từ đó kiểm tra:

- Có tạo object trong vòng lặp không?
- Có thể tái sử dụng buffer an toàn không?
- Có thể giảm số lần copy không?
- Có thể dùng collection với capacity phù hợp không?
- Có thể tránh boxing hoặc chuyển đổi dữ liệu lặp lại không?

Mọi tối ưu phải giữ đúng semantics và thread safety. Không tái sử dụng mutable object giữa nhiều thread nếu chưa có cơ chế ownership và đồng bộ rõ ràng.

## 7. Đo allocation theo thread bằng ThreadMXBean

HotSpot cung cấp extension \`com.sun.management.ThreadMXBean\` để đo gần đúng tổng số byte heap được cấp phát bởi một platform thread.

| Method | Ý nghĩa |
|---|---|
| \`getCurrentThreadAllocatedBytes()\` | Tổng byte heap được cấp phát bởi thread hiện tại |
| \`getThreadAllocatedBytes(id)\` | Tổng byte heap được cấp phát bởi thread có ID chỉ định |
| \`getTotalThreadAllocatedBytes()\` | Tổng byte heap được cấp phát bởi các thread từ khi JVM khởi chạy |
| \`isThreadAllocatedMemorySupported()\` | JVM có hỗ trợ đo allocation theo thread không |
| \`isThreadAllocatedMemoryEnabled()\` | Đo allocation theo thread đã bật chưa |
| \`setThreadAllocatedMemoryEnabled(true)\` | Bật đo allocation nếu JVM hỗ trợ |

Số liệu là giá trị xấp xỉ. Đây không phải lượng object còn sống hoặc retained heap.

### Ví dụ đo delta của thread hiện tại

~~~java
import java.lang.management.ManagementFactory;

public class ThreadAllocationCounter {
    public static void main(String[] args) {
        java.lang.management.ThreadMXBean platformBean =
                ManagementFactory.getThreadMXBean();

        if (!(platformBean instanceof com.sun.management.ThreadMXBean bean)
                || !bean.isThreadAllocatedMemorySupported()) {
            System.out.println("ALLOC_METRIC_SUPPORTED=false");
            return;
        }

        if (!bean.isThreadAllocatedMemoryEnabled()) {
            bean.setThreadAllocatedMemoryEnabled(true);
        }

        long before = bean.getCurrentThreadAllocatedBytes();

        byte[][] values = new byte[1000][];
        for (int i = 0; i < values.length; i++) {
            values[i] = new byte[1024];
        }

        long after = bean.getCurrentThreadAllocatedBytes();
        long allocated = after - before;

        System.out.println("ALLOC_METRIC_SUPPORTED=true");
        System.out.println("OBJECTS=" + values.length);
        System.out.println("ALLOCATED_BYTES=" + allocated);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 ThreadAllocationCounter.java
java ThreadAllocationCounter
~~~

Output có dạng:

~~~text
ALLOC_METRIC_SUPPORTED=true
OBJECTS=1000
ALLOCATED_BYTES=<giá trị do JVM đo>
~~~

Giá trị byte phụ thuộc object layout, JDK, JVM và nền tảng. Ví dụ đo allocation của thread main trong đoạn code nằm giữa hai lần đọc counter.

Giới hạn:

- Counter là tổng allocation tích lũy của thread; lấy delta để đo một khoảng.
- Giá trị gần đúng và có thể được cập nhật trễ tùy JVM.
- Nếu measurement chưa bật, method có thể trả về -1.
- JVM implementation có thể không hỗ trợ tính năng này.
- Trong JDK 26, \`getThreadAllocatedBytes\` trả về -1 với virtual thread.
- Counter không cho biết class hoặc method nào đã cấp phát; dùng JFR để tìm allocation site.

## 8. Đo allocation bằng JMH GC profiler

Khi so sánh hai cách triển khai một operation nhỏ, **Java Microbenchmark Harness (JMH)** phù hợp hơn việc tự đo bằng vòng lặp và \`System.nanoTime()\`.

Chạy benchmark với GC profiler:

~~~bash
java -jar target/benchmarks.jar -prof gc
~~~

Các chỉ số thường gặp:

| Metric | Ý nghĩa |
|---|---|
| \`gc.alloc.rate\` | Allocation rate, thường tính MB/s |
| \`gc.alloc.rate.norm\` | Allocation trên mỗi operation, thường là B/op |
| \`gc.churn.*\` | Lượng object được thu hồi trong các memory pool theo thời gian |
| \`gc.churn.*.norm\` | Churn được chuẩn hóa theo operation |
| \`gc.count\` | Số collection trong benchmark |
| \`gc.time\` | Thời gian collection được ghi nhận trong benchmark |

Ví dụ output minh họa:

~~~text
Benchmark                         Mode  Cnt    Score
StringMapping.benchmark           avgt    5  1200.0 ns/op

StringMapping.benchmark:gc.alloc.rate       500.0 MB/sec
StringMapping.benchmark:gc.alloc.rate.norm  512.0 B/op
StringMapping.benchmark:gc.count            12 counts
StringMapping.benchmark:gc.time             18 ms
~~~

Số liệu trên chỉ minh họa định dạng. Nếu implementation A tạo 512 B/op và B tạo 128 B/op, B giảm allocation trên mỗi operation:

\[
\frac{512-128}{512}\times100 = 75\%
\]

Đây là mức giảm allocation, không đồng nghĩa latency cũng giảm 75%. Cần so sánh throughput, latency, GC count và GC time.

Để benchmark đáng tin cậy:

- Dùng warmup và nhiều measurement iterations.
- Dùng nhiều forks để giảm ảnh hưởng trạng thái JVM trước đó.
- Chọn input đại diện cho production.
- Dùng Blackhole hoặc kết quả có thể quan sát để tránh dead-code elimination.
- Giữ cùng JDK, collector, heap và phần cứng khi so sánh.
- Đọc cả \`gc.alloc.rate\` và \`gc.alloc.rate.norm\`.

Allocation rate tuyệt đối phụ thuộc tốc độ benchmark. Vì vậy, bytes/op thường hữu ích hơn khi đánh giá lượng allocation của một operation.

## 9. Dùng jstat để quan sát allocation pressure gián tiếp

jstat không cung cấp allocation site và cũng không phải công cụ đo chính xác từng byte được cấp phát. Tuy vậy, thống kê Eden và GC giúp quan sát allocation pressure.

Tìm JVM:

~~~bash
jps -l
~~~

Lấy mẫu GC utilization:

~~~bash
jstat -gcutil 2125 1000 10
~~~

Các cột thường quan tâm:

| Cột | Ý nghĩa |
|---|---|
| E | Phần trăm Eden đang sử dụng |
| O | Phần trăm Old Space đang sử dụng |
| YGC | Số Young GC tích lũy |
| YGCT | Tổng thời gian Young GC tích lũy |
| FGC | Số Full GC tích lũy |
| FGCT | Tổng thời gian Full GC tích lũy |
| GCT | Tổng thời gian GC tích lũy |

E tăng nhanh rồi giảm khi YGC xảy ra cho thấy Eden đang nhận allocation. YGC tăng nhanh có thể phản ánh allocation pressure. O tăng qua nhiều chu kỳ có thể do promotion hoặc live set tăng.

Không suy ra chính xác allocation bytes/second chỉ từ E hoặc YGC. Kích thước Eden có thể thay đổi và object có thể được promote hoặc thu hồi.

## 10. GC logs giúp hiểu tác động của allocation

GC log cho biết khi nào collection xảy ra, nguyên nhân, heap trước/sau và thời gian pause.

Bật unified GC logging:

~~~bash
java -Xlog:gc*:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Ví dụ ghi thêm chi tiết GC phases:

~~~bash
java -Xlog:gc*,gc+phases=debug:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Xem danh sách tag và level:

~~~bash
java -Xlog:help
~~~

Ví dụ một dòng log minh họa:

~~~text
[0.123s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 25M->4M(64M) 2.345ms
~~~

- 0.123s là thời gian từ khi JVM khởi chạy.
- GC(0) là ID của collection.
- Pause Young mô tả loại collection và pause.
- 25M->4M là heap used trước và sau collection.
- (64M) là dung lượng heap đã commit trong ví dụ.
- 2.345ms là thời gian pause.

GC log không cho biết trực tiếp method nào tạo object. Dùng JFR allocation profile để tìm allocation site.

## 11. Đo allocation và GC bằng JFR

JFR giúp đối chiếu allocation, heap usage và GC theo cùng timeline.

Các event hữu ích:

| Event | Mục đích |
|---|---|
| \`jdk.GarbageCollection\` | Thông tin về một chu kỳ GC |
| \`jdk.GCPhasePause\` | Thời gian các pause phase |
| \`jdk.GCHeapSummary\` | Thống kê heap quanh GC |
| \`jdk.ObjectAllocationInNewTLAB\` | Allocation liên quan đến TLAB refill |
| \`jdk.ObjectAllocationOutsideTLAB\` | Allocation ngoài TLAB |
| \`jdk.ThreadAllocationStatistics\` | Allocation theo thread |

Bắt đầu recording profile 5 phút:

~~~bash
jcmd 2125 JFR.start name=memory-profile settings=profile duration=5m filename=memory-profile.jfr
~~~

Đọc allocation và GC events:

~~~bash
jfr print --events jdk.ObjectAllocationInNewTLAB,jdk.ObjectAllocationOutsideTLAB,jdk.ThreadAllocationStatistics,jdk.GarbageCollection,jdk.GCPhasePause memory-profile.jfr
~~~

Trong JMC, xem TLAB Allocations và Garbage Collections để tìm allocation site, thread và pause. Không bật Heap Statistics nếu đang đo latency và không cần live-set analysis, vì tính năng này có thể kích hoạt old GC bổ sung ở đầu và cuối recording.

## 12. Những lỗi thường gặp khi đo allocation

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nhầm allocation với live set | Kết luận sai về memory leak | Đối chiếu allocation và heap sau GC |
| Chỉ nhìn số object | Bỏ qua object lớn | Xem allocated bytes và class |
| Dùng counter tích lũy làm rate | Kết quả không theo khoảng đo | Lấy delta và chia elapsed time |
| Đo trước warmup | Kết quả bị ảnh hưởng JIT và class loading | Warmup trước khi lấy baseline |
| Benchmark không có nhiều forks | Kết quả dễ nhiễu | Dùng JMH và nhiều forks |
| Chỉ xem jstat | Không tìm được allocation site | Dùng JFR/JMC |
| Chỉ xem JFR default | Không có allocation profiling | Dùng profile hoặc custom settings |
| Đo tất cả thread bằng một counter | Không biết thread nào tạo object | Dùng ThreadMXBean theo thread hoặc JMC |
| Dùng ThreadMXBean với virtual thread | Counter có thể trả -1 | Dùng JFR hoặc công cụ phù hợp |
| Tái sử dụng object không an toàn | Tạo race condition | Kiểm tra ownership và thread safety |
| Bật profiling chi tiết quá lâu | Recording lớn và overhead tăng | Giới hạn duration và event settings |

## 13. Quy trình đo allocation trong thực tế

1. Xác định triệu chứng: GC thường xuyên, latency tăng hay heap tăng.
2. Ghi lại JDK, collector, heap size và workload.
3. Chọn chỉ số: MB/s, B/op, allocation theo thread hay allocation site.
4. Dùng JFR profile ngắn để tìm class và stack trace cấp phát nhiều.
5. Dùng JMC Allocation by Class, Thread và Allocation Profile.
6. Dùng ThreadMXBean khi cần counter theo platform thread.
7. Dùng JMH \`-prof gc\` khi so sánh các implementation.
8. Dùng jstat và GC logs để xem allocation pressure và tác động tới GC.
9. Phân biệt object tạm thời với object còn sống sau GC.
10. Chọn allocation site lớn nhất có thể tối ưu mà vẫn giữ semantics.
11. Thay đổi một yếu tố tại một thời điểm.
12. Đo lại cùng workload và cùng cấu hình.
13. So sánh B/op, MB/s, GC count, GC time, latency và throughput.
14. Ghi lại JDK, collector, settings và kết quả.

## 14. Ghi nhớ

- Allocation là tổng lượng object mới được tạo; live set là object còn sống sau GC.
- Allocation rate đo byte/giây; bytes/op đo byte trên mỗi operation.
- TLAB giúp cấp phát object nhỏ nhanh hơn; object lớn có thể được cấp phát ngoài TLAB.
- JFR và JMC giúp tìm class, thread và stack trace tạo nhiều object.
- JFR default continuous template không thu thập allocation profiling trong JDK 26; dùng profile cho profiling ngắn.
- ThreadMXBean cung cấp counter allocation gần đúng theo platform thread.
- JMH \`-prof gc\` đo allocation rate, bytes/op, GC count và GC time.
- jstat chỉ cho tín hiệu allocation pressure gián tiếp qua Eden và GC.
- GC log cho biết collection và heap before/after, không chỉ ra allocation site.
- Allocation cao không tự động là memory leak; phải đối chiếu live set và retained heap.
- Luôn đo lại bằng workload tương đương sau khi tối ưu.

## Tài liệu tham khảo chính thức

- [Diagnostic Tools — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [Troubleshoot Performance Issues Using Flight Recorder — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [ThreadMXBean — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/ThreadMXBean.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The java Command — Unified Logging, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [JMH GC Profiler Sample — OpenJDK](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java)