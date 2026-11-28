# Đo thay đổi về dung lượng heap, cấp phát, GC và hiệu năng ứng dụng

**Compact Object Headers** là thay đổi ở cách HotSpot lưu metadata trong header của object. Trên JVM 64-bit, layout thông thường có header 96 bit (12 byte) khi dùng compressed class pointers; một số cấu hình có thể dùng 128 bit (16 byte). Layout gọn đưa header về 64 bit (8 byte). Phần tiết kiệm thường thấy là khoảng 4 byte trên mỗi object trong cấu hình phổ biến, nhưng dung lượng object thực tế còn phụ thuộc field và quy tắc căn chỉnh bộ nhớ.

Java 25 đưa tính năng này thành **product feature** qua **JEP 519**. Trong JDK 25, tính năng vẫn **tắt mặc định** và được bật bằng `-XX:+UseCompactObjectHeaders`; không cần `-XX:+UnlockExperimentalVMOptions`. Bài này thuộc chương **Header đối tượng gọn** của module `JAVA_VERSION_JAVA25`, tập trung đo tác động lên heap, allocation, garbage collection và hiệu năng của ứng dụng.

Một khác biệt theo phiên bản cần ghi rõ khi đọc tài liệu hiện tại: JDK 27 đã bật Compact Object Headers mặc định theo JEP 534. Vì vậy, khi benchmark hoặc chuyển runtime, hãy đặt rõ cả chế độ bật và tắt để phép so sánh không phụ thuộc mặc định của runtime.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích header của object chứa metadata gì và Compact Object Headers thay đổi phần nào.
2. Phân biệt header gọn với Compressed OOPs, nén class pointer và payload của object.
3. Ước lượng giới hạn lý thuyết về số byte tiết kiệm theo số lượng object.
4. Xác định workload nào có khả năng hưởng lợi lớn và workload nào ít thay đổi.
5. Bật/tắt tính năng trên JDK 25 bằng product flag.
6. Thiết kế phép đo A/B có cùng JDK, heap, collector, workload và môi trường.
7. Dùng JMH, JFR, GC log, heap histogram và công cụ layout để thu thập bằng chứng.
8. Đọc đúng các chỉ số live set, allocation rate, GC count, pause, throughput và latency.
9. Phát hiện giới hạn class count, cấu hình JVM và các tương tác có thể làm kết quả khác dự kiến.
10. Lập kế hoạch rollout và rollback dựa trên số liệu của ứng dụng thực tế.

## 2. Header của object lưu những gì?

Mỗi object trên Java heap có phần header do JVM quản lý. Header chứa thông tin phục vụ runtime như:

- **Class metadata reference:** xác định object thuộc class nào.
- **Mark word:** chứa trạng thái khóa, identity hash code khi đã được tạo, tuổi của object phục vụ GC và các bit trạng thái nội bộ.
- **Thông tin liên quan đến array:** object dạng array còn cần lưu độ dài mảng theo layout JVM.

Sau header là phần instance fields hoặc phần tử của array, tiếp theo là padding nếu cần để đáp ứng object alignment. Đây là layout nội bộ của HotSpot; Java Language Specification không quy định số byte header cụ thể và ứng dụng không nên phụ thuộc vào offset nội bộ này.

### 2.1. Layout thông thường và layout gọn

Với cấu hình HotSpot 64-bit phổ biến có compressed class pointers:

```text
Layout thông thường:
+-------------------------------+
| Mark word                 8 B |
+-------------------------------+
| Compressed class pointer  4 B |
+-------------------------------+
| Instance fields / array data  |
+-------------------------------+
Header thường gặp: 12 bytes (96 bits)

Compact Object Headers:
+-------------------------------+
| Mark word + encoded class 8 B |
| information in one 64-bit word|
+-------------------------------+
| Instance fields / array data  |
+-------------------------------+
Header: 8 bytes (64 bits)
```

Compact Object Headers mã hóa thông tin class vào cùng một word 64-bit với metadata khác. Vì thế, JVM có thể giảm header từ 96 hoặc 128 bit xuống 64 bit theo cấu hình. Trong trường hợp thường gặp 12 byte xuống 8 byte, mức giảm raw header là 4 byte mỗi object.

### 2.2. Những thứ không thay đổi

Compact Object Headers không:

- Xóa field của class hoặc giảm số phần tử trong array.
- Thay đổi kiểu dữ liệu Java hoặc kích thước payload do ứng dụng định nghĩa.
- Tự động giảm số object được tạo.
- Thay thế Compressed OOPs, vốn nén các reference trỏ đến object.
- Thay đổi cấu trúc serialization hay định dạng dữ liệu trên mạng.
- Thay đổi thuật toán GC hoặc thay thế collector.

Tính năng thay đổi **cách HotSpot biểu diễn metadata của object trong heap**. Lợi ích xuất hiện khi chi phí header chiếm tỷ lệ đáng kể trong tổng dung lượng object.

## 3. Ước lượng mức tiết kiệm bộ nhớ

Nếu một workload giữ sống N object và mức giảm header thực tế trung bình là 4 byte/object, ước lượng raw saving là:

```text
raw saving = N × 4 bytes
100,000,000 objects × 4 bytes
            = 400,000,000 bytes
            ≈ 381.5 MiB
```

Đây là phép ước lượng lý thuyết, không phải cam kết rằng heap usage hoặc RSS sẽ giảm đúng 381.5 MiB. Kích thước object được làm tròn theo alignment; có object giảm được cả một đơn vị alignment, có object sau khi làm tròn vẫn chiếm cùng kích thước. Array, object có nhiều field và cách bố trí field cũng ảnh hưởng kết quả.

| Workload | Số object còn sống | Mức giảm raw giả định | Cách diễn giải |
|---|---:|---:|---|
| Cache chứa 10 triệu node nhỏ | 10 triệu | 40 MB | Có thể thấy khác biệt nếu node nhỏ và sống lâu |
| Graph chứa 100 triệu node | 100 triệu | 400 MB | Header có thể chiếm phần đáng kể của live set |
| Một số ít object lớn | 100 nghìn | 0.4 MB | Lợi ích thường nhỏ so với payload |
| Ứng dụng chủ yếu dùng byte array lớn | Phụ thuộc số array | Không thể suy ra từ tổng byte payload | Phải đo layout và tỷ trọng header của từng array |

Không dùng số lượng object tổng thể để dự đoán trực tiếp dung lượng giảm. Hãy xem object size histogram và phân bố class để biết ứng dụng có nhiều object nhỏ hay không.

## 4. Workload nào có khả năng hưởng lợi?

Compact headers thường đáng thử với workload có nhiều object nhỏ, ví dụ:

- Map, Set và cấu trúc collection có nhiều entry/node.
- Object graph của JSON/XML, DTO và dữ liệu đã deserialize.
- AST, compiler model, biểu thức và cấu trúc cây.
- Cache trong bộ nhớ chứa nhiều record/domain object.
- ORM entity graph hoặc mô hình dữ liệu quan hệ có nhiều object.
- Message processing, event pipeline và ứng dụng tạo nhiều object ngắn hạn.
- Dịch vụ có live set lớn gồm nhiều object nhỏ.

Workload ít có khả năng thay đổi đáng kể nếu phần lớn bộ nhớ nằm trong:

- Một vài primitive array rất lớn.
- Direct buffer hoặc native/off-heap memory.
- Byte buffer chứa payload lớn.
- Một số ít object lớn có nhiều field/payload.
- Bộ nhớ native của thư viện, metaspace hoặc thread stack.

| Dấu hiệu đo được | Mức ưu tiên thử Compact Object Headers |
|---|---|
| Rất nhiều instance nhỏ và live set lớn | Cao |
| Allocation rate theo byte cao do tạo nhiều object nhỏ | Cao |
| Heap histogram có nhiều class node/entry/record nhỏ | Cao |
| Phần lớn heap là byte[]/char[] lớn | Cần benchmark, lợi ích có thể thấp |
| RSS chủ yếu do direct memory/native library | Thấp |
| Ứng dụng đã dư RAM và startup/latency không nhạy | Đánh giá lợi ích chi phí trước khi rollout |

## 5. Trạng thái và cách bật trong Java 25

JEP 519 chuyển Compact Object Headers từ experimental feature của JDK 24 thành product feature trong JDK 25. Flag có thể dùng trực tiếp:

```bash
java -XX:+UseCompactObjectHeaders -jar app.jar
```

Trong Java 25, flag mặc định là tắt. Có thể ép chế độ tắt rõ ràng cho baseline:

```bash
java -XX:-UseCompactObjectHeaders -jar app.jar
```

Không cần thêm `-XX:+UnlockExperimentalVMOptions` khi chạy Java 25. Cờ mở khóa đó thuộc giai đoạn experimental trước đây; bài thực hành Java 25 dùng product flag hiện hành.

### 5.1. Xác nhận trạng thái flag

Trên Linux/macOS:

```bash
java -XX:+PrintFlagsFinal -version 2>&1 | grep UseCompactObjectHeaders
```

Trên Windows PowerShell:

```powershell
java -XX:+PrintFlagsFinal -version 2>&1 | findstr UseCompactObjectHeaders
```

Có thể kiểm tra cờ của tiến trình đang chạy bằng:

```bash
jcmd <pid> VM.flags -all
```

Thay `<pid>` bằng process ID của JVM cần kiểm tra. Xác minh đúng executable/JDK mà tiến trình sử dụng; `java --version` trong một terminal khác không đảm bảo service production đang chạy cùng JDK.

### 5.2. Trạng thái ở các phiên bản

| JDK | Trạng thái |
|---|---|
| JDK 24 | Experimental feature; không dùng quy trình này cho triển khai hiện hành |
| JDK 25 | Product feature, mặc định tắt; bật bằng `-XX:+UseCompactObjectHeaders` |
| JDK 26 | Vẫn cần kiểm tra và đặt flag tường minh theo runtime |
| JDK 27 | Bật mặc định theo JEP 534; có thể tắt bằng `-XX:-UseCompactObjectHeaders` |

Vì module này học Java 25, các lệnh benchmark chính bên dưới đặt rõ `-XX:-UseCompactObjectHeaders` và `-XX:+UseCompactObjectHeaders`. Cách này cũng phù hợp khi so sánh trên JDK 27, nơi mặc định đã thay đổi.

## 6. Nguyên tắc thiết kế benchmark A/B

Phép đo có ý nghĩa khi hai lần chạy chỉ khác trạng thái Compact Object Headers. Giữ các yếu tố sau giống nhau:

- Cùng vendor, JDK update/build và kiến trúc CPU.
- Cùng binary ứng dụng, dependency, cấu hình và dữ liệu.
- Cùng `-Xms`, `-Xmx`, GC collector và các GC flags.
- Cùng CPU quota, memory limit, container image và host class.
- Cùng workload, concurrency, thời gian warm-up và thời gian đo.
- Cùng JFR settings hoặc cùng trạng thái không bật JFR.
- Cùng CDS setting và cách khởi chạy.
- Cùng cách thu thập RSS, heap, GC và latency.

Không thay đồng thời Compact Object Headers, collector, heap size và JDK update. Nếu thay nhiều biến, bạn sẽ không biết biến nào tạo ra khác biệt.

### 6.1. Hai cấu hình cần so sánh

| Run | Cấu hình object header | Mục tiêu |
|---|---|---|
| Baseline | `-XX:-UseCompactObjectHeaders` | Đo layout thông thường |
| Treatment | `-XX:+UseCompactObjectHeaders` | Đo layout gọn |

Chạy nhiều lần theo thứ tự xen kẽ, ví dụ baseline → compact → compact → baseline. Cách này giảm ảnh hưởng do tải máy, nhiệt độ CPU hoặc các tiến trình nền thay đổi theo thời gian.

### 6.2. Không thay heap limit giữa hai lần chạy

Ví dụ cả hai cấu hình cùng dùng heap 4 GiB:

```bash
java -Xms4g -Xmx4g \
     -XX:+UseG1GC \
     -XX:-UseCompactObjectHeaders \
     -jar app.jar

java -Xms4g -Xmx4g \
     -XX:+UseG1GC \
     -XX:+UseCompactObjectHeaders \
     -jar app.jar
```

Trong benchmark này, G1 được chọn để cố định collector; không có ý nghĩa rằng G1 luôn là lựa chọn tốt nhất cho mọi ứng dụng. Nếu production dùng collector khác, hãy chạy thêm một bộ A/B với đúng collector production và kiểm tra khả năng tương thích của runtime cụ thể.

## 7. Đo object layout và heap live set

Để biết ứng dụng có nhiều object nhỏ hay không, cần quan sát **số lượng instance, shallow size, retained/live data và phân bố class**. Không chỉ nhìn heap committed hoặc RSS.

### 7.1. Heap histogram

Dùng `jcmd` trên tiến trình staging:

```bash
jcmd <pid> GC.class_histogram
```

Histogram hiển thị số instance và tổng shallow bytes theo class. Đây là dữ liệu hữu ích để tìm class có số lượng instance rất lớn. Lưu ý lệnh có thể gây ảnh hưởng lớn đến tiến trình và có thể yêu cầu GC; chỉ chạy trong môi trường đo có kiểm soát, không gọi lặp lại trên production nhạy latency.

Để xem thông tin heap hiện tại:

```bash
jcmd <pid> GC.heap_info
```

Histogram không cho biết chính xác retained size của toàn bộ object graph. Nếu cần tìm object giữ lại nhiều bộ nhớ, dùng heap dump và công cụ phân tích heap phù hợp.

### 7.2. Object layout với JOL

Java Object Layout (JOL) là công cụ ngoài JDK có thể giúp kiểm tra layout của class trong một JVM cụ thể. Ví dụ:

```java
import org.openjdk.jol.info.ClassLayout;
import org.openjdk.jol.vm.VM;

public class LayoutInspection {
    static final class Node {
        int id;
        Node next;
    }

    public static void main(String[] args) {
        System.out.println(VM.current().details());
        System.out.println(
            ClassLayout.parseInstance(new Node()).toPrintable()
        );
    }
}
```

Chạy cùng chương trình hai lần với flag tắt/bật và cùng JDK 25. Chọn phiên bản JOL có hỗ trợ layout của JDK đang dùng; công cụ layout cũ có thể không hiểu compact header và đưa ra diễn giải sai. JOL là bằng chứng hỗ trợ ở cấp class, còn benchmark heap/application vẫn cần đo độc lập.

### 7.3. Đọc đúng các đại lượng bộ nhớ

| Đại lượng | Ý nghĩa |
|---|---|
| Shallow size | Dung lượng trực tiếp của một object, không gồm object được tham chiếu |
| Retained size | Dung lượng có thể được giải phóng nếu object/nhánh đó không còn reachable |
| Live set | Dữ liệu còn sống sau khi GC thu hồi các object không còn reachable |
| Heap used | Phần heap đang được sử dụng tại thời điểm quan sát |
| Heap committed | Bộ nhớ heap JVM đã commit từ hệ điều hành |
| Heap max | Giới hạn heap tối đa theo cấu hình/runtime |
| RSS | Bộ nhớ resident của process, bao gồm heap resident và nhiều vùng native khác |

Với `-Xms` cố định, heap committed có thể gần như không đổi dù object nhỏ hơn. Hãy so sánh live set và heap used sau cùng một giai đoạn workload; RSS là chỉ số tổng hợp và có thể bị ảnh hưởng bởi metaspace, code cache, thread stack, direct memory và native library.

## 8. Đo allocation bằng JMH

JMH phù hợp để so sánh chi phí cấp phát của một cấu trúc object nhỏ. Ví dụ dưới đây tạo một graph gồm ba node; trả về root để object thoát khỏi method và được benchmark harness tiêu thụ.

```java
import org.openjdk.jmh.annotations.Benchmark;

public class CompactHeaderBench {

    @Benchmark
    public Node createSmallGraph() {
        Node root = new Node(1);
        root.next = new Node(2);
        root.next.next = new Node(3);
        return root;
    }

    static final class Node {
        final int id;
        Node next;

        Node(int id) {
            this.id = id;
        }
    }
}
```

Đây là ví dụ microbenchmark. Trong dự án thật, cần đóng gói bằng JMH theo build đã chọn và thêm benchmark cho object shape đại diện của ứng dụng, chẳng hạn map entry, DTO graph hoặc AST node.

### 8.1. Chạy baseline

```bash
java -jar target/benchmarks.jar CompactHeaderBench.createSmallGraph \
     -wi 5 -i 8 -f 3 -prof gc \
     -jvmArgsAppend "-Xms2g -Xmx2g -XX:+UseG1GC -XX:-UseCompactObjectHeaders"
```

### 8.2. Chạy Compact Object Headers

```bash
java -jar target/benchmarks.jar CompactHeaderBench.createSmallGraph \
     -wi 5 -i 8 -f 3 -prof gc \
     -jvmArgsAppend "-Xms2g -Xmx2g -XX:+UseG1GC -XX:+UseCompactObjectHeaders"
```

Giữ nguyên số warm-up iterations, measurement iterations, forks, heap và collector. JMH profiler `gc` có thể cung cấp các số liệu như:

- `gc.alloc.rate`: tốc độ cấp phát theo byte/giây.
- `gc.alloc.rate.norm`: số byte cấp phát trung bình trên mỗi operation.
- `gc.count`: số lần GC trong phép đo.
- `gc.time`: tổng thời gian GC được ghi nhận.

`gc.alloc.rate.norm` hữu ích để xem object graph tương tự có tốn ít byte hơn không. Số object được tạo mỗi operation không tự giảm; thay đổi chủ yếu nằm ở số byte chiếm dụng trên mỗi object và tác động gián tiếp lên locality/GC.

### 8.3. Tránh kết luận từ microbenchmark duy nhất

Một class `Node` không đại diện cho mọi object trong ứng dụng. Tạo thêm benchmark cho:

- Object không có field hoặc chỉ có primitive field.
- Object chứa reference tới object khác.
- Graph có nhiều node nhỏ.
- Array object và array chứa primitive.
- Collection có nhiều entry.
- Workload có `synchronized` hoặc gọi `System.identityHashCode` nếu ứng dụng thực sự sử dụng các thao tác đó.

Microbenchmark giúp giải thích cơ chế, nhưng quyết định rollout cần dựa trên benchmark ứng dụng hoặc replay traffic gần production.

## 9. Đo GC và allocation trong ứng dụng thực

Để kiểm tra tác động khi chạy ứng dụng, dùng cùng một workload trong hai tiến trình JVM riêng.

### 9.1. Baseline: header thông thường

```bash
java -Xms4g -Xmx4g \
     -XX:+UseG1GC \
     -XX:-UseCompactObjectHeaders \
     -Xlog:gc*,gc+heap=debug:file=baseline-gc.log:time,uptime,level,tags \
     -XX:StartFlightRecording=filename=baseline.jfr,settings=profile,dumponexit=true \
     -jar app.jar
```

### 9.2. Treatment: compact headers

```bash
java -Xms4g -Xmx4g \
     -XX:+UseG1GC \
     -XX:+UseCompactObjectHeaders \
     -Xlog:gc*,gc+heap=debug:file=compact-gc.log:time,uptime,level,tags \
     -XX:StartFlightRecording=filename=compact.jfr,settings=profile,dumponexit=true \
     -jar app.jar
```

Hai lần chạy cần nhận cùng dữ liệu đầu vào và cùng số request/job. Nếu ứng dụng là server, dùng load generator có tốc độ, concurrency và thời gian warm-up cố định; không so một lần chạy tải thấp với một lần chạy tải cao.

### 9.3. Phân tích GC log

GC log giúp xem:

- Số lần young/mixed/full GC.
- Dung lượng heap trước và sau GC.
- Pause duration và tổng thời gian GC.
- Heap occupancy theo thời gian.
- Có xảy ra allocation stall hoặc GC overhead bất thường không.

Đọc hai file bằng cùng công cụ phân tích hoặc cùng quy tắc lọc. Nếu số GC giảm, cần kiểm tra workload có cùng lượng công việc và cùng thời gian chạy hay không; số lần GC ít hơn không tự chứng minh latency tốt hơn.

## 10. Dùng JFR quan sát allocation và GC

JFR có thể thu thập allocation sample, heap summary và GC events. Recording profile giúp quan sát các điểm cấp phát và sự kiện GC, nhưng allocation sample là dữ liệu lấy mẫu, không phải bộ đếm chính xác mọi object.

Xem tổng quan recording:

```bash
jfr summary baseline.jfr
jfr summary compact.jfr
```

Xem allocation samples:

```bash
jfr view allocation-by-site baseline.jfr
jfr view allocation-by-site compact.jfr
```

Nếu JDK build không có view tương ứng, kiểm tra lệnh hỗ trợ:

```bash
jfr view --help
```

Hoặc in các event cần phân tích:

```bash
jfr print --events jdk.ObjectAllocationSample baseline.jfr
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary baseline.jfr
```

So sánh allocation sites, tỷ lệ sample, GC events và heap summary. Không dùng riêng số `ObjectAllocationSample` để tính tổng byte cấp phát tuyệt đối; kết hợp JMH `gc.alloc.rate.norm`, GC log hoặc công cụ đo allocation phù hợp.

## 11. Đo hiệu năng ứng dụng

Mục tiêu không chỉ là giảm heap. Cần xác minh thay đổi có cải thiện hành vi mà người dùng và hệ thống quan tâm không.

| Chỉ số | Cách đo | Ý nghĩa |
|---|---|---|
| Throughput | Request/operation mỗi giây | Khả năng xử lý công việc |
| Latency p50 | Phân vị trung vị | Trải nghiệm điển hình |
| Latency p95/p99 | Tail latency | Các request chậm ở phần đuôi |
| CPU time / CPU utilization | Process/container metrics | Chi phí tính toán |
| Allocation bytes/op | JMH `gc.alloc.rate.norm` | Byte cấp phát cho mỗi operation |
| Allocation rate | JFR/JMH/GC metrics | Áp lực cấp phát theo thời gian |
| GC count/time | GC log/JFR | Tần suất và chi phí thu gom |
| Live set sau GC | Heap metrics/heap analysis | Dữ liệu còn sống |
| RSS/container memory | OS/container metrics | Bộ nhớ thực tế của process |

### 11.1. Vì sao throughput có thể tăng?

Khi nhiều object nhỏ chiếm ít byte hơn:

- Nhiều object có thể nằm trong cùng vùng cache line hơn.
- GC có ít byte heap cần scan/copy hơn trong các tình huống phù hợp.
- Cùng heap limit có thể chứa được live set lớn hơn.
- Ít áp lực cấp phát theo byte có thể làm giảm tần suất một số GC.

Các lợi ích này phụ thuộc cấu trúc dữ liệu, collector, CPU, object alignment và workload. Không bảo đảm mọi ứng dụng đều tăng throughput.

### 11.2. Vì sao một số workload có thể không cải thiện?

- Ứng dụng chủ yếu xử lý primitive arrays hoặc off-heap buffer.
- Thời gian chủ yếu nằm ở network, database hoặc external service.
- Object ít và phần payload lớn.
- Chi phí locking, identity hash hoặc các đường code nhạy layout làm kết quả khác dự đoán.
- Workload không tạo áp lực heap/GC đáng kể.

Nếu heap giảm nhưng p99 không đổi, có thể ứng dụng bị giới hạn bởi I/O hoặc một thành phần khác. Nếu heap giảm nhưng CPU tăng, hãy phân tích profile và lock-heavy paths trước khi rollout.

## 12. Diễn giải kết quả: allocation, GC và heap có liên hệ thế nào?

Compact headers không làm chương trình tạo ít object hơn. Nó giảm phần metadata của từng object; do đó số byte được cấp phát có thể giảm trong workload object-dense.

Ví dụ cùng một operation tạo 1.000 object:

| Đại lượng | Baseline | Compact headers |
|---|---:|---:|
| Số object logic được tạo | 1.000 | 1.000 |
| Payload và field | Theo class | Không đổi |
| Header raw mỗi object | Lớn hơn | Nhỏ hơn |
| Tổng byte cấp phát | Phụ thuộc layout/alignment | Có thể thấp hơn |
| Số GC | Phụ thuộc heap pressure | Có thể giảm |
| Thời gian GC | Phụ thuộc collector/workload | Có thể giảm |
| Throughput | Kết quả baseline | Phải đo |

Đừng nhầm **object allocation count** với **allocation bytes**. Nếu số lượng object mỗi request giữ nguyên nhưng `gc.alloc.rate.norm` giảm, điều đó phù hợp với kỳ vọng của compact headers.

### 12.1. Heap committed không nhất thiết giảm ngay

Nếu cả hai JVM đều chạy với `-Xms4g -Xmx4g`, JVM có thể commit cùng dung lượng heap ngay từ đầu. Tính năng làm giảm dung lượng object đang dùng, không yêu cầu JVM tự trả ngay phần heap đã commit về hệ điều hành.

Vì vậy, khi đánh giá cần tách:

- Heap used và live set.
- Heap committed và heap max.
- RSS của process/container.
- Native memory và metaspace.

### 12.2. GC count không phải chỉ số duy nhất

GC count có thể giảm khi cùng một heap chứa được nhiều object hơn hoặc allocation bytes thấp hơn. Tuy nhiên, pause time, concurrent CPU, promotion rate và p99 latency vẫn cần theo dõi. Một collector có thể đổi tần suất hoặc cấu trúc pause khi heap occupancy thay đổi.

## 13. Benchmark workload thật và replay traffic

Một bài benchmark tốt nên có ít nhất hai lớp:

**Microbenchmark:** dùng JMH để cô lập object allocation và đo byte/op.

**Macrobenchmark:** chạy toàn ứng dụng hoặc replay traffic để đo heap, GC, CPU, throughput và latency end-to-end.

### 13.1. Chuẩn hóa workload

- Dùng cùng dataset, kích thước payload và phân bố request.
- Dùng cùng concurrency và thời gian chạy.
- Đưa ứng dụng qua warm-up trước khi lấy số liệu.
- Chạy nhiều lần, ghi median và percentile thay vì chỉ lấy một lần chạy.
- Đổi thứ tự baseline/treatment giữa các lượt.
- Tách thời gian khởi động khỏi thời gian đo steady-state.
- Ghi lại CPU quota, RAM limit, GC và JDK build.

### 13.2. Test cả đường nóng và đường hiếm

Nếu chỉ chạy happy path, bạn có thể bỏ sót:

- Đường xử lý lỗi tạo nhiều exception/stack object.
- Batch lớn tạo graph object phức tạp.
- Cache eviction hoặc refresh.
- Lock contention ở cache dùng chung.
- Các thao tác gọi identity hash.
- Các job chạy định kỳ tạo lượng object khác request thường.

Tập workload phải phản ánh tỷ trọng thực tế và các đường có chi phí bộ nhớ đáng kể.

### 13.3. Kết quả tham khảo không phải mục tiêu bắt buộc

JEP 519 công bố các kết quả benchmark trong những cấu hình cụ thể: một cấu hình SPECjbb2015 giảm khoảng 22% heap usage và 8% CPU time; cấu hình khác giảm khoảng 15% số lần GC với G1 và Parallel; benchmark JSON parser song song cao chạy nhanh hơn khoảng 10%. Những con số này chỉ mô tả các workload được đo, không phải cam kết cho ứng dụng của bạn.

## 14. Giới hạn và điều kiện tương thích

Oracle Java SE 25 GC tuning guide ghi nhận một số điều kiện cần lưu ý:

- Compact headers giảm header xuống 64 bit.
- Khi bật, số lượng class khác nhau đã load bị giới hạn ở khoảng **4 triệu**.
- Compressed class pointers là điều kiện của layout compact; không tắt chúng khi dùng tính năng này.
- Đây là layout riêng của HotSpot; các JVM khác có thể có cách bố trí object khác.

Nếu ứng dụng tạo class động với số lượng rất lớn, chẳng hạn framework sinh proxy/class liên tục, hãy kiểm tra class count và khả năng chạm giới hạn trước khi bật.

### 14.1. Kiểm tra class loading

Dùng công cụ theo dõi class loading và histogram trong môi trường staging. Có thể xem class metadata và số class đang load qua JMX/management tooling hoặc công cụ vận hành hiện có. Đặc biệt chú ý hệ thống plugin, code generation và classloader sống lâu.

### 14.2. Tương tác với công cụ thấp tầng

Các thư viện, agent hoặc profiler đọc trực tiếp object header bằng `Unsafe`, JVMTI hoặc cơ chế nội bộ có thể giả định layout cũ. Đây không phải API Java được bảo đảm ổn định. Kiểm tra phiên bản agent, profiler, APM và native integration trước khi bật cho toàn bộ fleet.

Không viết ứng dụng phụ thuộc vào byte offset của mark word hoặc class pointer. Dùng API Java được hỗ trợ cho synchronization, identity hash và reflection.

### 14.3. Kiểm tra cấu hình khóa và runtime

Compact headers thay đổi cách HotSpot lưu metadata khóa trong object header. Với ứng dụng nhạy với synchronization hoặc identity hash, benchmark các đường đó bằng đúng JDK build và workload. Không suy luận từ một benchmark chỉ cấp phát object rằng mọi đường locking đều có cùng kết quả.

Nếu runtime không thể dùng layout compact do điều kiện tương thích, hãy đọc startup log và trạng thái flag để biết JVM có thực sự bật tính năng hay đã tắt theo ergonomics.

## 15. CDS và custom runtime image

JDK 25 cung cấp các CDS archive phù hợp với cấu hình Compact Object Headers để hỗ trợ startup. Nếu tạo custom runtime bằng `jlink`, cần tạo CDS archive tương ứng sau khi tạo image.

Ví dụ:

```bash
<image>/bin/java -XX:+UseCompactObjectHeaders -Xshare:dump
```

Lệnh này tạo archive `classes_coh.jsa` cho image với compact headers. Nếu tự đóng gói custom runtime, đưa bước tạo archive vào pipeline build và xác minh đúng image/flag khi chạy. Không lấy CDS archive từ cấu hình khác rồi giả định chúng luôn tương thích.

Với benchmark heap/GC, giữ CDS setting nhất quán giữa baseline và treatment. Nếu thay đổi CDS cùng lúc với object header, kết quả startup có thể bị nhiễu bởi hai biến.

## 16. Các lỗi thường gặp khi đo

| Sai lầm | Vì sao kết quả sai | Cách khắc phục |
|---|---|---|
| So sánh hai lần chạy với `-Xmx` khác nhau | Heap capacity làm thay đổi GC và live set | Giữ cùng `-Xms`/`-Xmx` |
| Chỉ xem RSS | RSS gồm heap, native, metaspace, stacks và code cache | Đo thêm heap used/live set và native memory |
| Chỉ xem số GC | GC count không cho biết pause/CPU/latency | So GC count, GC time, pause và p99 |
| Chỉ chạy một lần | JIT, OS cache và tải máy gây nhiễu | Nhiều forks/lượt chạy và xen kẽ A/B |
| Dùng workload không đại diện | Không phản ánh object distribution production | Replay traffic hoặc dùng dataset thực tế đã ẩn dữ liệu |
| Đo khi JFR bật ở một phía | Instrumentation làm thay đổi chi phí | Cùng recording settings hoặc tách lượt benchmark không JFR |
| Dùng histogram trong lúc tải cao | Lệnh có thể gây pause/GC và làm lệch số đo | Chạy ở staging hoặc cửa sổ đo có kiểm soát |
| Coi JFR allocation sample là số đếm tuyệt đối | Allocation sample là lấy mẫu | Dùng JMH allocation profiler/metrics phù hợp để đo bytes/op |
| Cho rằng object count giảm | Header gọn không loại bỏ object | Phân biệt object count và allocation bytes |
| Dùng kết quả SPECjbb làm SLA | Benchmark khác workload và phần cứng | Tự đo ứng dụng của mình |
| Bật flag mà không kiểm tra runtime thực | Service có thể chạy bằng JDK khác | Kiểm tra `java --version`, command line và VM flags |
| Thêm cờ experimental unlock trên Java 25 | Không còn cần thiết cho product option | Chỉ dùng `-XX:+UseCompactObjectHeaders` |

## 17. Ma trận nghiệm thu

| Mã | Kịch bản | Kết quả kỳ vọng |
|---|---|---|
| COH-01 | Xác nhận JDK runtime là Java 25 | Đúng JDK vendor/build được chọn |
| COH-02 | Kiểm tra trạng thái flag mặc định trên JDK 25 | `UseCompactObjectHeaders` mặc định tắt |
| COH-03 | Khởi chạy với `-XX:+UseCompactObjectHeaders` | JVM bật layout gọn |
| COH-04 | Khởi chạy với `-XX:-UseCompactObjectHeaders` | JVM dùng layout thông thường |
| COH-05 | Xác nhận không cần experimental unlock | Product flag hoạt động trực tiếp trên JDK 25 |
| COH-06 | So header layout bằng JOL tương thích | Header compact nhỏ hơn theo layout HotSpot |
| COH-07 | So histogram cùng workload | Số instance theo class tương đương |
| COH-08 | Chạy JMH với `-prof gc` | Có allocation bytes/op và GC metrics |
| COH-09 | Chạy cùng workload A/B | Chỉ khác flag Compact Object Headers |
| COH-10 | So heap live set sau cùng giai đoạn | Có số liệu live set có thể so sánh |
| COH-11 | So allocation rate | Phân biệt bytes/s với object count/s |
| COH-12 | So GC count và GC time | Có dữ liệu tần suất và chi phí GC |
| COH-13 | So p50/p95/p99 và throughput | Xác định tác động ở cấp ứng dụng |
| COH-14 | Kiểm tra lock/identity hash path | Không có regression không giải thích được |
| COH-15 | Kiểm tra class count | Không tiến gần giới hạn 4 triệu class |
| COH-16 | Kiểm tra agent/profiler/native library | Tất cả thành phần quan sát tương thích |
| COH-17 | Kiểm tra custom `jlink` image nếu có | CDS archive đúng cấu hình được tạo |
| COH-18 | Chạy lại nhiều lần và đổi thứ tự A/B | Kết quả ổn định, không phụ thuộc thứ tự |
| COH-19 | Kiểm tra JDK 27 nếu migration | Hiểu mặc định đã bật và ép flag khi benchmark |
| COH-20 | Tổng hợp báo cáo rollout | Có lợi ích, rủi ro, phạm vi và rollback rõ |

## 18. Bài thực hành tổng hợp

### Bài A — Kiểm tra layout của một class nhỏ

Tạo class `Node` có một primitive field và một reference field. Dùng JOL tương thích với JDK 25 để in layout khi flag tắt và bật. Ghi lại header, field offset, object size và alignment. Giải thích vì sao raw header saving không phải lúc nào cũng bằng mức giảm object size đã làm tròn.

### Bài B — Đo allocation bytes/op

Dùng JMH tạo graph gồm nhiều node nhỏ. Chạy baseline và treatment với cùng heap, collector, warm-up, measurement và số fork. Ghi `gc.alloc.rate.norm`, `gc.alloc.rate`, throughput và GC count/time. Giải thích vì sao số node mỗi operation có thể không đổi nhưng bytes/op giảm.

### Bài C — Đo service thực tế

Chạy cùng phiên bản ứng dụng với hai cờ `-XX:-UseCompactObjectHeaders` và `-XX:+UseCompactObjectHeaders`. Replay cùng traffic trong staging. Ghi heap live set, allocation rate, GC pause, CPU, RSS, throughput và p95/p99. Lặp lại ít nhất ba lần theo thứ tự xen kẽ.

### Bài D — Phân tích workload ít hưởng lợi

Tạo workload xử lý payload lớn trong `byte[]` hoặc direct buffer. So sánh với workload có nhiều node/DTO nhỏ. Giải thích vì sao tỷ trọng header trong tổng footprint khác nhau.

### Bài E — Kiểm tra giới hạn tương thích

Chạy test với các agent/profiler và framework đang dùng. Xác nhận không có thành phần nào phụ thuộc layout nội bộ. Kiểm tra class count nếu ứng dụng dùng proxy hoặc code generation động.

### Bài F — Viết quyết định rollout

Từ dữ liệu đo, đề xuất bật hay giữ tắt trên JDK 25. Báo cáo phải có:

- Mức thay đổi live set và allocation bytes/op.
- Mức thay đổi GC count, pause và CPU.
- Throughput, p95/p99 và error rate.
- Tác động tới RSS/container memory.
- Các framework, agent và collector đã kiểm thử.
- Phạm vi rollout, điều kiện theo dõi và cách rollback bằng cờ tắt.

## 19. Câu hỏi tự đánh giá

1. Header của object HotSpot chứa những loại metadata nào?
2. Compact Object Headers giảm header từ bao nhiêu bit xuống bao nhiêu bit?
3. Vì sao mức tiết kiệm raw header không luôn bằng mức giảm object size thực tế?
4. Compact Object Headers khác Compressed OOPs ở điểm nào?
5. Vì sao workload có nhiều object nhỏ thường hưởng lợi hơn workload có vài array lớn?
6. Vì sao số object tạo ra không tự giảm khi bật compact headers?
7. JDK 25 bật tính năng bằng flag nào và trạng thái mặc định là gì?
8. Vì sao benchmark cần đặt rõ cả flag bật và tắt?
9. `gc.alloc.rate.norm` cho biết gì và khác allocation count ra sao?
10. Vì sao RSS có thể không giảm dù heap live set giảm?
11. Cần đo những chỉ số GC nào ngoài GC count?
12. Vì sao JFR allocation sample không phải bộ đếm tuyệt đối?
13. Vì sao JMH microbenchmark chưa đủ để quyết định rollout?
14. Giới hạn số class đã load khi dùng compact headers là bao nhiêu?
15. Vì sao cần kiểm tra profiler, agent và native library?
16. JDK 27 thay đổi mặc định Compact Object Headers như thế nào?
17. Vì sao cần kiểm tra lock-heavy path và identity hash?
18. Khi nào custom `jlink` image cần tạo CDS archive riêng?

**Tiêu chí hoàn thành:** Bạn có thể bật/tắt Compact Object Headers trên Java 25, thiết kế phép đo A/B có thể lặp lại, giải thích được thay đổi về object layout, heap live set, allocation bytes và GC, đồng thời đưa ra quyết định dựa trên throughput, latency và tài nguyên của ứng dụng thật.

## 20. Nguồn tham khảo chính thức

- [OpenJDK JEP 519 — Compact Object Headers](https://openjdk.org/jeps/519)
- [OpenJDK JEP 450 — Compact Object Headers (Experimental, lịch sử JDK 24)](https://openjdk.org/jeps/450)
- [Oracle Java SE 25 — Garbage Collection Tuning Guide: Other Considerations / Compact Object Headers](https://docs.oracle.com/en/java/javase/25/gctuning/other-considerations.html)
- [Oracle Java SE 25 — Consolidated Release Notes: UseCompactObjectHeaders Is a Product Option](https://www.oracle.com/java/technologies/javase/25all-relnotes.html)
- [Inside.java — Performance Improvements in JDK 25](https://inside.java/2025/10/20/jdk-25-performance-improvements/)
- [OpenJDK JEP 534 — Compact Object Headers by Default (JDK 27)](https://openjdk.org/jeps/534)
- [Oracle JDK 27 Release Notes — Compact Object Headers Are Enabled by Default](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/)
- [JOL — Java Object Layout](https://openjdk.org/projects/code-tools/jol/)

**Điểm cần nhớ:** Compact Object Headers giảm metadata trên mỗi object, không giảm số object hay payload của chúng. Muốn chứng minh lợi ích, hãy đo đồng thời object layout, live set, allocation bytes/op, GC và hiệu năng end-to-end. Trên Java 25 hãy bật bằng product flag và luôn so sánh với baseline có flag tắt rõ ràng; kết quả tốt cần được xác nhận trên workload và runtime thực tế.
