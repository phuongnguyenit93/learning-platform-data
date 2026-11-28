# Phân biệt thay đổi bên trong GC với hợp đồng API Java

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích thay đổi nội bộ của G1 trong JDK 26 theo JEP 522.
- Mô tả vai trò của card table, write barrier và hai bảng card table trong thiết kế mới.
- Phân biệt tối ưu hóa implementation của garbage collector với thay đổi hợp đồng API Java.
- Nhận biết API quản trị mới `MemoryMXBean.getTotalGcCpuTime()` trong Java 26 và hiểu giới hạn của số liệu.
- Kết hợp số liệu MXBean, GC log và benchmark để đánh giá tác động lên ứng dụng.
- Tránh phụ thuộc vào chi tiết nội bộ như số instruction, cấu trúc bảng hoặc mức tăng throughput của một benchmark cụ thể.

## 1. Hai lớp thay đổi cần phân biệt

Một bản JDK có thể cải thiện cách JVM thực hiện một chức năng mà không thay đổi cách chương trình Java quan sát hoặc sử dụng chức năng đó. Khi đọc release note về garbage collection, cần phân biệt:

- **Thay đổi implementation:** thuật toán, cấu trúc dữ liệu, write barrier, lịch chạy thread hoặc cách tổ chức công việc bên trong HotSpot thay đổi. Mục tiêu có thể là giảm CPU, giảm đồng bộ, giảm pause hoặc tăng throughput.
- **Thay đổi API/hợp đồng nền tảng:** Java bổ sung hoặc thay đổi kiểu, method, tham số, ngoại lệ, semantics hoặc cam kết quan sát được từ mã nguồn Java/JMX.

JDK 26 có cả hai loại thay đổi liên quan đến GC:

| Thay đổi | Lớp | Ý nghĩa |
|---|---|---|
| JEP 522 – G1 GC: Improve Throughput by Reducing Synchronization | Implementation của HotSpot G1 | Tối ưu cách application threads và GC refinement threads phối hợp qua card table. |
| `MemoryMXBean.getTotalGcCpuTime()` | API quản trị Java SE | Bổ sung method để đọc thời gian CPU tích lũy ước lượng dành cho hoạt động GC. |

JEP 522 không bổ sung cú pháp Java, class hoặc method để ứng dụng điều khiển G1. API `MemoryMXBean.getTotalGcCpuTime()` là thay đổi API riêng trong JDK 26; không nên quy method này thành một phần của cơ chế hai card table.

## 2. G1 cần card table để theo dõi cập nhật tham chiếu

G1 chia heap thành nhiều region và có thể thu gom một tập region trong khi ứng dụng tiếp tục chạy. Khi một object được ghi tham chiếu tới object khác, G1 cần biết vùng heap nào có thể chứa tham chiếu liên vùng để thực hiện công việc GC chính xác.

Một cơ chế quan trọng là **card table**:

- Heap được chia logic thành các card nhỏ.
- Khi ứng dụng ghi một tham chiếu vào heap, write barrier được thực hiện quanh thao tác ghi.
- Write barrier đánh dấu card liên quan là dirty (đã thay đổi).
- Các refinement threads của G1 xử lý card dirty để cập nhật thông tin về tham chiếu liên vùng.
- Thông tin này giúp G1 tránh quét toàn bộ heap trong những giai đoạn cần tìm tham chiếu.

Write barrier là mã do JVM/JIT chèn hoặc phát sinh quanh thao tác ghi tham chiếu. Đây là chi tiết runtime; ứng dụng Java vẫn viết phép gán thông thường:

~~~java
order.setCustomer(customer);
cache.put(key, value);
node.next = nextNode;
~~~

Ứng dụng không phải gọi một API card table hoặc tự đánh dấu card. G1 đảm nhận việc theo dõi cập nhật tham chiếu ở runtime.

## 3. Nút thắt đồng bộ trước JEP 522

Trước thay đổi của JEP 522, application threads và các refinement threads cùng phối hợp trên card table. Khi workload cập nhật nhiều trường tham chiếu, các thao tác đánh dấu và xử lý card có thể cần đồng bộ để tránh hai nhóm thread làm mất thông tin của nhau.

Điều này làm write barrier phức tạp hơn và tạo chi phí cho những workload có nhiều phép ghi tham chiếu. Chi phí không nhất thiết thể hiện thành một GC pause dài; nó có thể xuất hiện liên tục trên đường thực thi của application threads và làm giảm throughput.

Các ứng dụng có thể chịu ảnh hưởng gồm:

- Cache trong bộ nhớ với tần suất cập nhật entry cao.
- Cấu trúc object graph thay đổi thường xuyên.
- Hệ thống xử lý request tạo và liên kết nhiều object.
- In-memory index, graph hoặc data structure có nhiều trường tham chiếu được ghi.
- Workload có nhiều thao tác cập nhật reference hơn so với phép tính số học thuần.

Không phải mọi allocation đều tạo ra cùng mức chi phí card table. Điều cần quan tâm là cập nhật tham chiếu và cách workload tương tác với heap.

## 4. JEP 522: hai card table giảm đồng bộ

JDK 26 đưa vào card table thứ hai để tách phần việc của application threads khỏi refinement threads:

1. Application threads ghi nhận cập nhật trên card table đang hoạt động.
2. Refinement threads xử lý bảng còn lại một cách độc lập.
3. Khi G1 dự đoán việc quét bảng đang hoạt động có thể vượt mục tiêu pause, G1 thực hiện hoán đổi hai bảng một cách nguyên tử.
4. Bảng vừa được tách khỏi application threads trở thành đầu vào cho refinement; bảng còn lại trở thành bảng đang hoạt động để application threads tiếp tục ghi nhận cập nhật.

Sơ đồ khái quát:

~~~text
                 Application threads
                         |
                         | write barrier
                         v
                +-------------------+
                | Active card table |
                +-------------------+
                         |
                 atomic table swap
                         |
                         v
                +-------------------+
                | Card table for    |
                | refinement        |
                +-------------------+
                         ^
                         |
                 Refinement threads
~~~

Nhờ tách bảng, application threads không phải đồng bộ thường xuyên với các refinement threads trên cùng một cấu trúc. Write barrier có thể đơn giản và nhẹ hơn; refinement threads vẫn thực hiện công việc theo dõi tham chiếu liên vùng.

JEP 522 cải thiện cách G1 quản lý công việc card table nhưng không thay đổi mô hình tổng thể của G1. Ứng dụng vẫn chạy với G1, các object vẫn có semantics Java như trước và G1 vẫn phải bảo đảm các tham chiếu được theo dõi chính xác.

## 5. Lợi ích hiệu năng và giới hạn của con số benchmark

Các phép đo được công bố cho thấy workload cập nhật tham chiếu nhiều có thể tăng throughput khoảng 5–15%; một số workload ít cập nhật tham chiếu cũng có thể có lợi ích nhỏ hơn. Thay đổi còn có thể giúp pause time giảm nhẹ và giảm chi phí write barrier.

Đây là kết quả benchmark trên workload và môi trường cụ thể, không phải cam kết rằng mọi ứng dụng sẽ nhanh hơn 5–15%. Kết quả thực tế phụ thuộc:

- Tỷ lệ ghi tham chiếu so với đọc tham chiếu.
- Số application threads và refinement threads.
- Heap size, region size và tỷ lệ object sống.
- CPU, cache hierarchy và băng thông bộ nhớ.
- Tải nền, giới hạn container và cấu hình JVM.
- Tính chất allocation, object graph và thời gian sống của object.

Một ứng dụng chủ yếu xử lý số học, chờ I/O hoặc đọc dữ liệu có thể không thấy khác biệt rõ. Không thay đổi kiến trúc ứng dụng chỉ vì một benchmark tổng quát cho thấy G1 nhanh hơn.

JEP 522 là tối ưu mặc định của implementation G1 trong JDK 26. Không cần bật preview, thêm module hoặc thay đổi code Java để nhận tối ưu này. Nếu ứng dụng chọn GC khác, không thể suy ra GC đó cũng có cùng cải tiến card table.

## 6. Điều gì không thay đổi trong hợp đồng Java?

JEP 522 thay đổi cấu trúc dữ liệu và cách đồng bộ bên trong G1. Nó không thay đổi các quy tắc Java mà ứng dụng dựa vào:

- **Reachability:** object còn reachable vẫn phải được giữ lại theo semantics GC.
- **Reference semantics:** phép gán và đọc tham chiếu trong Java giữ nguyên ý nghĩa.
- **Java Memory Model:** JEP 522 không thay thế `volatile`, monitor, happens-before hoặc quy tắc đồng bộ của ứng dụng.
- **Object identity:** `==`, `equals()` và identity của object không thay đổi vì card table được tách đôi.
- **Allocation API:** ứng dụng không cần gọi API mới để cấp phát object hoặc ghi tham chiếu.
- **GC selection:** G1 vẫn được chọn bằng cấu hình JVM hiện hành; JEP 522 không tạo một collector mới.
- **Pause-time goal:** mục tiêu pause của G1 vẫn là mục tiêu điều khiển, không phải cam kết thời gian dừng tối đa tuyệt đối.

Không nên viết code phụ thuộc vào số card table, kích thước card, số instruction của write barrier hoặc thời điểm hoán đổi bảng. Những chi tiết này thuộc implementation và có thể tiếp tục thay đổi mà không tạo ra thay đổi API Java.

## 7. API quản trị Java 26: MemoryMXBean.getTotalGcCpuTime()

Bên cạnh JEP 522, Java 26 bổ sung method `getTotalGcCpuTime()` vào interface chuẩn `java.lang.management.MemoryMXBean`:

~~~java
long getTotalGcCpuTime()
~~~

Method trả về thời gian CPU tích lũy ước lượng dành cho hoạt động GC, tính bằng nanosecond. Có thể lấy MXBean bằng `ManagementFactory`:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;

public class GcCpuTimeExample {
    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

        long gcCpuNanos = memory.getTotalGcCpuTime();

        if (gcCpuNanos < 0) {
            System.out.println("GC CPU time không được hỗ trợ hoặc chưa có");
        } else {
            System.out.println("Accumulated GC CPU time: " + gcCpuNanos + " ns");
        }
    }
}
~~~

Đây là API thuộc `java.management`, không phải method riêng của G1. Ứng dụng có thể dùng nó để quan sát GC CPU time trên JVM hỗ trợ phép đo, bất kể implementation có phải G1 hay không.

### Cách hiểu giá trị trả về

- Giá trị là tổng tích lũy từ khi JVM chạy, không phải thời gian của lần GC gần nhất.
- Đơn vị là nanosecond.
- Đây là giá trị xấp xỉ, không phải phép đo chính xác tuyệt đối.
- Trả về `-1` nếu implementation không hỗ trợ hoặc thông tin không sẵn có.
- Giá trị có thể khác 0 ngay cả khi chưa có một GC cycle rõ ràng, vì phép đo có thể bao gồm overhead của hoạt động GC.

Javadoc quy định hợp đồng ở mức “approximate accumulated time”. Chi tiết hoạt động nào được tính vào GC CPU time phụ thuộc implementation. Trong HotSpot, số liệu có thể bao gồm driver threads, worker threads, VM operations và string deduplication nếu được bật.

Do đó, không diễn giải giá trị này như tổng thời gian pause của GC. Nó là CPU time của các hoạt động liên quan GC; nhiều GC thread có thể chạy đồng thời nên tổng CPU time có thể lớn hơn elapsed wall-clock time trong cùng khoảng đo.

## 8. Đo mức CPU GC theo khoảng thời gian

Vì `getTotalGcCpuTime()` trả về giá trị tích lũy, muốn đánh giá một khoảng thời gian nên lấy hai mẫu và tính chênh lệch:

~~~java
MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

long before = memory.getTotalGcCpuTime();

// Chạy workload cần quan sát trong khoảng đo.

long after = memory.getTotalGcCpuTime();

if (before >= 0 && after >= before) {
    long gcCpuDelta = after - before;
    System.out.println("GC CPU delta: " + gcCpuDelta + " ns");
} else {
    System.out.println("GC CPU time unavailable");
}
~~~

Không so sánh trực tiếp hai giá trị tích lũy được lấy từ các JVM khác nhau hoặc các process có thời gian sống khác nhau. Hãy so sánh delta trên các khoảng đo tương đương.

Có thể kết hợp với process CPU time để ước lượng phần CPU mà GC sử dụng trong cùng khoảng. `com.sun.management.OperatingSystemMXBean#getProcessCpuTime()` là extension của JDK, không phải Java SE API portable:

~~~java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;

OperatingSystemMXBean os =
    (OperatingSystemMXBean) ManagementFactory.getOperatingSystemMXBean();

long processBefore = os.getProcessCpuTime();
long gcBefore = ManagementFactory.getMemoryMXBean().getTotalGcCpuTime();

// Chạy workload.

long processAfter = os.getProcessCpuTime();
long gcAfter = ManagementFactory.getMemoryMXBean().getTotalGcCpuTime();

if (processBefore >= 0 && processAfter > processBefore
        && gcBefore >= 0 && gcAfter >= gcBefore) {
    double gcCpuShare =
        100.0 * (gcAfter - gcBefore) / (processAfter - processBefore);

    System.out.printf("Approximate GC CPU share: %.2f%%%n", gcCpuShare);
}
~~~

Tỷ lệ này là ước lượng và chỉ có ý nghĩa khi hai bộ đếm cùng đo một process trong cùng khoảng. Nếu nhiều GC threads chạy song song, GC CPU time cộng dồn theo thread; process CPU time cũng là tổng CPU time của process. Không lấy tỷ lệ này làm phần trăm wall-clock time hoặc dùng làm SLA nếu chưa xác định rõ cách implementation đo.

Nếu ứng dụng dùng module system và tham chiếu trực tiếp `com.sun.management.OperatingSystemMXBean`, cần khai báo `requires jdk.management;`. Nếu chỉ dùng `MemoryMXBean`, module chuẩn cần có là `java.management`.

Với ứng dụng cần tương thích JDK trước 26, không thể gọi trực tiếp method mới trong bytecode rồi giả định JVM cũ sẽ chạy được. Hãy đặt baseline compile/runtime phù hợp hoặc tách phần đọc metric thành adapter tương thích. Nếu dùng reflection để kiểm tra method có tồn tại, xử lý trường hợp method không có trên runtime cũ và trường hợp trả về `-1`.

## 9. Kết hợp API với GC log và JFR

Không có một metric duy nhất giải thích đầy đủ hành vi GC. Hãy kết hợp nhiều góc nhìn:

| Nguồn quan sát | Điều có thể biết | Giới hạn |
|---|---|---|
| `MemoryMXBean.getTotalGcCpuTime()` | CPU time GC tích lũy ước lượng | Không cho biết riêng từng pause hoặc nguyên nhân GC |
| `MemoryMXBean.getHeapMemoryUsage()` | Heap used, committed và max | Không mô tả đầy đủ native memory hoặc CPU GC |
| Unified GC logging trên HotSpot | Các chu kỳ GC, pause, phase và heap state | Chi tiết log phụ thuộc collector, build và cấu hình |
| JFR | Sự kiện runtime, GC, allocation, thread và CPU | Recording settings và overhead ảnh hưởng dữ liệu |
| Application metrics | Throughput, latency, error rate và queue depth | Cần tương quan thời gian với dữ liệu GC |

Ví dụ bật GC log trên HotSpot:

~~~bash
java -Xlog:gc*,safepoint -jar app.jar
~~~

Dùng log để tìm thời điểm và loại hoạt động GC, rồi đối chiếu với delta GC CPU time, throughput và latency. Không suy ra GC CPU time chỉ bằng cách cộng pause duration; concurrent GC work và các hoạt động phụ trợ có thể dùng CPU ngoài khoảng pause.

## 10. Benchmark để biết JEP 522 có lợi cho ứng dụng hay không

So sánh JDK 25 và JDK 26 hoặc hai bản JDK cần đánh giá với cùng điều kiện:

1. Dùng cùng artifact hoặc cùng commit và dependency.
2. Giữ nguyên CPU, RAM, container quota, heap size, GC và JVM flags nếu mục tiêu là cô lập tác động JDK.
3. Dùng workload đại diện, đặc biệt có các luồng cập nhật nhiều object reference nếu ứng dụng thực tế có đặc điểm đó.
4. Có warmup, nhiều lần chạy độc lập và thứ tự baseline/candidate hợp lý.
5. Đo throughput, latency p50/p95/p99, GC CPU delta, pause time, allocation rate, heap và RSS.
6. Kiểm tra tính đúng của output và error rate.
7. Lặp lại trên CPU và môi trường triển khai thực tế.

Nếu muốn kiểm tra riêng tác động G1, giữ collector là G1 ở cả hai bản JDK. Không đồng thời đổi từ Parallel GC sang G1 rồi quy toàn bộ chênh lệch cho JEP 522.

Khi workload có nhiều thao tác ghi tham chiếu, throughput có thể cải thiện do write barrier ít tốn kém hơn. Nếu throughput không đổi, điều đó không chứng minh JEP 522 không hoạt động; bottleneck có thể nằm ở I/O, lock ứng dụng, memory bandwidth hoặc phần khác của runtime.

## 11. Điều gì là hợp đồng API và điều gì là implementation detail?

| Nội dung | Phân loại | Cách ứng dụng nên phụ thuộc |
|---|---|---|
| G1 có trách nhiệm thu gom object không còn reachable | Hành vi nền tảng/GC semantics | Có thể dựa vào semantics Java |
| JEP 522 dùng hai card table và atomic swap | Implementation detail của G1 | Không truy cập hoặc phụ thuộc trực tiếp |
| Số instruction trong write barrier giảm từ khoảng 50 xuống khoảng 12 trên một số kiến trúc | Quan sát implementation/benchmark | Không dùng làm cam kết hiệu năng |
| Throughput tăng 5–15% trong một số workload reference-heavy | Kết quả benchmark | Chỉ dùng làm kỳ vọng thử nghiệm, phải đo lại |
| `MemoryMXBean.getTotalGcCpuTime()` có từ Java 26 | Hợp đồng API Java SE | Có thể gọi khi runtime hỗ trợ API |
| Giá trị method là approximate, nanoseconds, `-1` nếu unavailable | Hợp đồng API | Phải xử lý giá trị không khả dụng và không coi là số chính xác |
| Thành phần cụ thể nào được tính vào GC CPU time của HotSpot | Implementation-dependent detail | Không giả định giống mọi JVM/vendor |
| `-Xlog:gc*` và format log HotSpot | Công cụ quan sát của JVM implementation | Dùng cho vận hành, tránh parse format nội bộ như public API |

Điểm cần nhớ: một method thuộc API chuẩn vẫn có thể cố ý mô tả kết quả ở mức xấp xỉ và để một số chi tiết cho implementation. “API chuẩn” không đồng nghĩa mọi chi tiết đo đạc đều giống nhau trên mọi JVM.

## 12. Checklist khi nâng cấp lên JDK 26

- [ ] Xác định ứng dụng có dùng G1 hay collector khác.
- [ ] Ghi baseline throughput, latency, pause, GC CPU và memory trước nâng cấp.
- [ ] Giữ nguyên workload và tài nguyên khi so sánh JDK.
- [ ] Không thêm code phụ thuộc vào card table hoặc write barrier nội bộ.
- [ ] Dùng `MemoryMXBean.getTotalGcCpuTime()` nếu runtime là Java 26 trở lên và cần metric GC CPU tích lũy.
- [ ] Xử lý `-1` và tránh coi metric xấp xỉ là thời gian pause.
- [ ] Nếu cần chạy trên JDK cũ hơn 26, kiểm tra khả năng tương thích trước khi gọi method mới.
- [ ] Kết hợp MXBean với GC log, JFR và application metrics.
- [ ] Không coi mức tăng throughput công bố là cam kết cho workload của mình.
- [ ] Kiểm tra lại kết quả trên môi trường production-like trước khi thay đổi cấu hình GC.

## Kết luận

JEP 522 là thay đổi implementation của G1 trong JDK 26: hai card table tách công việc ghi nhận cập nhật tham chiếu của application threads khỏi refinement threads, giảm đồng bộ và có thể cải thiện throughput. Thay đổi này không tạo API mới và không đổi semantics GC mà ứng dụng Java dựa vào. Một bổ sung riêng của Java 26 là `MemoryMXBean.getTotalGcCpuTime()`, API quản trị chuẩn trả về GC CPU time tích lũy ước lượng, với `-1` khi không có số liệu. Hãy dựa vào hợp đồng API để viết mã giám sát, còn các chi tiết card table, write barrier và kết quả benchmark chỉ dùng để giải thích implementation và định hướng đo đạc.

## Tài liệu tham khảo

- [JEP 522: G1 GC: Improve Throughput by Reducing Synchronization](https://openjdk.org/jeps/522)
- [Oracle JDK 26 – Significant Changes in JDK 26 Release](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html)
- [Java SE 26 API – MemoryMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Java SE 26 API – ManagementFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html)
- [Inside Java – Performance Improvements in JDK 26](https://inside.java/2026/06/09/jdk-26-performance-improvements/)
- [Inside Java – Java 26 for DevOps](https://inside.java/2026/03/02/jdk-26-rn-ops/)
