# Phân tích cấp phát, GC và nghẽn xử lý của pipeline

Trong chương **Hiệu năng và bộ nhớ** của **Java Stream API**, một pipeline sử dụng `filter`, `map`, `flatMap`, `reduce`, `collect` hoặc `parallelStream` có thể chạy đúng nhưng tốn nhiều thời gian, cấp phát quá nhiều đối tượng tạm hoặc gây áp lực lên bộ thu gom rác (*garbage collector*, GC). Khi đó, giải pháp không phải tự động bỏ Stream để viết vòng lặp, cũng không phải bật `parallel()` với hy vọng mọi vấn đề biến mất.

Cần trả lời ba câu hỏi **khác nhau**:

1. **Cấp phát (*allocation*):** Những đối tượng nào được tạo trong mỗi lần xử lý, bao nhiêu byte được cấp phát và ở bước nào?
2. **GC và bộ nhớ còn sống (*live heap*):** Bao nhiêu dữ liệu vẫn còn được tham chiếu, GC diễn ra thường xuyên hay gây pause đáng kể, và bộ nhớ đỉnh có vượt giới hạn không?
3. **Nghẽn xử lý (*bottleneck*):** Thời gian kết thúc yêu cầu thực sự bị chi phối bởi CPU, GC, chờ I/O, khóa đồng bộ, lượng dữ liệu phải thu thập, hay khả năng chia nguồn khi chạy song song?

Ba câu hỏi này liên quan nhưng **không đồng nhất**. Một chương trình có thể cấp phát nhiều đối tượng ngắn hạn mà GC vẫn xử lý hiệu quả; hoặc có tốc độ cấp phát thấp nhưng giữ Map khổng lồ khiến heap tăng và phải xử lý nhiều dữ liệu sống. Tương tự, GC có thể xuất hiện nhiều trong log nhưng không phải nguyên nhân chính khiến ứng dụng chậm.

Bài này hướng dẫn cách xây **giả thuyết có thể kiểm chứng**, chọn phép đo phù hợp (JFR, GC log, JMH và đo end-to-end), xác định những chi phí thường gặp của Stream API, thực hiện tối ưu nhỏ có kiểm soát và so sánh lại kết quả đúng cùng với hiệu năng.

> **Môi trường minh họa:** Java 17+. Các API Stream cơ bản có từ Java 8; `Stream.toList()` có từ Java 16. Một số công cụ chẩn đoán và cú pháp ghi log GC trong ví dụ yêu cầu JDK hiện đại. Lệnh đo chỉ để người học thực hành; không có kết quả benchmark thực tế nào được giả định trong bài.

## 1. Đầu tiên, định nghĩa "chậm" bằng chỉ số

Không thể tối ưu đúng nếu chỉ có nhận xét "pipeline này có vẻ chậm". Hãy xác định chỉ số gắn với mục tiêu nghiệp vụ:

| Chỉ số | Câu hỏi trả lời | Đơn vị minh họa |
| --- | --- | --- |
| **Latency** | Một lần xử lý mất bao lâu? | ms/request hoặc ms/batch |
| **Throughput** | Mỗi giây xử lý được bao nhiêu dữ liệu? | requests/s, events/s |
| **CPU usage/time** | Máy đang thực sự tính toán nhiều không? | %, CPU-time |
| **Allocation rate** | JVM cấp phát bao nhiêu byte trong một giây? | MB/s |
| **Allocation per operation** | Mỗi lượt xử lý tạo khoảng bao nhiêu byte? | B/op |
| **Live heap** | Những đối tượng còn được giữ sau khi thu gom là bao nhiêu? | MB |
| **Peak memory** | Bộ nhớ đạt đỉnh bao nhiêu trong một đợt xử lý? | MB, GB |
| **GC frequency/pause** | GC diễn ra ra sao và ảnh hưởng độ trễ thế nào? | lần/s, ms/pause |
| **I/O wait / blocking** | Thread chờ đĩa, mạng, DB hoặc khóa bao lâu? | ms hoặc tỷ lệ thời gian |

Các chỉ số này nên được ghi cùng **kích thước dữ liệu, tỉ lệ bản ghi qua filter, số khóa phân biệt, kích thước nhóm, phiên bản JDK, cấu hình heap và mức đồng thời**. Không có những yếu tố đó, rất khó so sánh phép đo giữa hai ngày hoặc hai môi trường.

### Thí dụ một báo cáo hiệu năng có thể hành động

~~~text
Workload: 100.000 sự kiện/batch, 2.000 khách hàng phân biệt
JDK: phiên bản và GC được ghi từ môi trường chạy
Mode: sequential, cùng input cố định
Metric A: latency p50/p95 và throughput
Metric B: allocation B/op và MB/s
Metric C: GC pauses, heap used after collection
Metric D: CPU hotspots và thời gian chờ I/O
Hypothesis: pipeline tạo object trung gian ở bước map/collect
~~~

**Đừng kết luận nguyên nhân ngay từ triệu chứng.** Cần đo để biết nút thắt thực sự có nằm ở bước đang nghi ngờ hay không.

## 2. Phân biệt allocation, live heap và retention

Ba khái niệm dễ bị đánh đồng:

### 2.1. Allocation: tốc độ tạo đối tượng

Trong một pipeline:

~~~java
List<String> labels = events.stream()
        .map(event -> event.customerId() + ":" + event.latencyMs())
        .toList();
~~~

Biểu thức ghép chuỗi có thể tạo các chuỗi kết quả mới. `toList()` còn cần giữ các phần tử đầu ra. Tuy nhiên, **không thể đếm chính xác số object được cấp phát chỉ bằng cách đọc source code**: compiler, JIT, escape analysis, tối ưu allocation và chi tiết triển khai JDK có thể thay đổi.

Vì vậy, thay vì nói "mỗi map chắc chắn tạo X object", hãy đo `B/op` hoặc allocation samples trong workload cụ thể.

### 2.2. Live heap: dữ liệu chưa thể thu gom

Giả sử:

~~~java
List<String> labels = events.stream()
        .map(Event::customerId)
        .toList();
~~~

Nếu `labels` còn được một cache hoặc field giữ tham chiếu, danh sách và các phần tử nó tham chiếu vẫn có thể là dữ liệu sống. Nếu chỉ tính một tổng rồi trả `long`, nhiều object tạm có thể trở nên không còn được tham chiếu ngay sau khi pipeline hoàn tất.

**Allocation cao không đồng nghĩa live heap cao.** Ngược lại, một cache giữ hàng triệu mục có thể chiếm heap rất lớn dù mỗi request gần như không cấp phát gì mới.

### 2.3. Retention: giữ đối tượng lâu hơn cần thiết

Một ví dụ đáng chú ý:

~~~java
Map<String, List<Event>> byCustomer = events.stream()
        .collect(Collectors.groupingBy(Event::customerId));
~~~

Kết quả giữ **danh sách mọi sự kiện theo khách hàng**. Nếu `byCustomer` tồn tại lâu, phần lớn đối tượng `Event` vẫn còn được tham chiếu; GC không thể giải phóng chúng chỉ vì pipeline đã kết thúc.

Nếu nghiệp vụ chỉ cần số lượng:

~~~java
Map<String, Long> counts = events.stream()
        .collect(Collectors.groupingBy(
                Event::customerId,
                Collectors.counting()
        ));
~~~

Mỗi khách chỉ có một số đếm trong kết quả, không còn `List<Event>` giữ toàn bộ bản ghi. Bộ nhớ tích lũy phụ thuộc chủ yếu số **khách hàng phân biệt**, không phải toàn bộ số sự kiện, dù các đối tượng đầu vào có thể vẫn được nơi khác giữ.

**Bài học:** Một phép tổng hợp đúng loại kết quả có thể giảm *retained heap* đáng kể hơn việc tối ưu vài object tạm.

## 3. Chi phí bộ nhớ thường gặp trong Stream pipeline

| Mẫu pipeline | Chi phí có thể xuất hiện | Câu hỏi cần đo |
| --- | --- | --- |
| `map` trả object mới | Object kết quả, chuỗi, boxing | Object nào thực sự được cấp phát? |
| `map(...).toList()` | Toàn bộ phần tử đầu ra cần được giữ | Có thật sự cần materialize mọi phần tử không? |
| `filter(...).toList()` | Danh sách kết quả tỷ lệ phần tử được giữ | Có thể dùng `count`/`sum` nếu chỉ cần số liệu không? |
| `flatMap` | Stream con, object trung gian, làm phẳng | Fan-out có lớn không? Có nguồn con I/O không? |
| `mapMulti` | Có thể dùng buffer nội bộ theo triển khai | Có tốt hơn `flatMap` trên JDK hiện tại không? |
| `boxed()` / `Stream<Integer>` | Boxing/unboxing, đối tượng wrapper có thể tồn tại | Có thể giữ primitive stream tới terminal không? |
| `sorted()` | Cần sắp xếp, thường phải giữ dữ liệu trung gian | Có cần sắp xếp toàn bộ hay chỉ lấy top-K? |
| `distinct()` | Trạng thái để nhận diện phần tử đã thấy | Số giá trị phân biệt có lớn không? |
| `groupingBy(..., toList())` | Map và các danh sách chứa toàn bộ phần tử theo nhóm | Chỉ cần count/sum/max hay thật sự cần list? |
| `toMap` | Map theo số khóa phân biệt, va chạm/merge | Có bao nhiêu khóa, có nhiều bản ghi trùng khóa không? |
| `parallelStream` | Nhiều phần tác vụ, vùng tích lũy, buffer/merge | Có tăng throughput nhưng lại tăng heap/GC không? |

**Lưu ý:** Bảng trên mô tả những **nguồn chi phí cần kiểm tra**, không bảo đảm một số byte hay số object cố định. Tính lazy, khả năng tối ưu của JIT và terminal operation có thể thay đổi những bước thực sự được chạy.

## 4. Nhận diện boxing trước khi đụng tới GC tuning

Đối với bài toán thuần số học, dùng `Stream<Long>` và các phép biến đổi sinh wrapper có thể tốn chi phí hơn primitive stream.

### Phiên bản boxed

~~~java
long total = events.stream()
        .filter(Event::error)
        .map(Event::latencyMs)
        .reduce(0L, Long::sum);
~~~

`map(Event::latencyMs)` trên `Stream<Event>` tạo `Stream<Long>` về mặt kiểu API; primitive `long` được chuyển thành `Long` khi phát qua Stream object. JIT **có thể** tối ưu một phần boxing, nhưng không nên giả định luôn loại bỏ tất cả.

### Phiên bản primitive

~~~java
long total = events.stream()
        .filter(Event::error)
        .mapToLong(Event::latencyMs)
        .sum();
~~~

`mapToLong` tạo `LongStream` và `sum` xử lý kết quả kiểu `long`. Đây thường là ứng viên tốt để giảm boxing trong pipeline tổng hợp số.

**Hai đoạn mã trên có cùng ý nghĩa** với nguồn `Event` hợp lệ, khi số tổng nằm trong miền `long` và không có side effect trong mapper. Phép cộng `long` có thể tràn theo quy tắc Java; nếu nghiệp vụ không cho phép tràn, cần một giải pháp kiểm tra giới hạn hoặc dùng kiểu số khác.

### Giữ primitive xuyên suốt pipeline

~~~java
long total = events.stream()
        .filter(Event::error)
        .mapToLong(Event::latencyMs)
        .filter(value -> value > 0L)
        .sum();
~~~

Tránh chuyển qua `boxed()` chỉ để tiếp tục tính toán số, trừ khi một API downstream thật sự yêu cầu object.

Ví dụ:

~~~java
// Có thể không cần boxing nếu chỉ tính tổng:
long total = events.stream()
        .mapToLong(Event::latencyMs)
        .boxed()
        .reduce(0L, Long::sum);
~~~

Một phép benchmark công bằng cần so **đúng cùng phép tính và cùng input**, không được cho nhánh primitive bỏ lọc trong khi nhánh boxed vẫn lọc.

## 5. Chương trình hoàn chỉnh: kết quả đúng trước khi đo

Ví dụ sau chạy với **Java 17+**, tạo dữ liệu cố định và so ba dạng tổng hợp:

- Tổng độ trễ lỗi dùng `Stream<Long>` với `reduce`.
- Tổng độ trễ lỗi dùng `LongStream.sum()`.
- Gom tổng độ trễ lỗi theo khách hàng với `groupingBy(..., summingLong(...))`.

Lưu vào `PipelineDiagnosticsDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class PipelineDiagnosticsDemo {

    record Event(
            int customerId,
            long latencyMs,
            boolean error
    ) {}

    // Input deterministic, được tạo ngoài đoạn pipeline cần đo.
    static List<Event> createData(int count) {
        return IntStream.range(0, count)
                .mapToObj(i -> new Event(
                        i % 2_000,
                        1L + i % 97,
                        i % 9 == 0
                ))
                .toList();
    }

    static long boxedTotal(List<Event> events) {
        return events.stream()
                .filter(Event::error)
                .map(Event::latencyMs)
                .reduce(0L, Long::sum);
    }

    static long primitiveTotal(List<Event> events) {
        return events.stream()
                .filter(Event::error)
                .mapToLong(Event::latencyMs)
                .sum();
    }

    static Map<Integer, Long> groupedTotal(
            List<Event> events) {

        return events.stream()
                .collect(Collectors.groupingBy(
                        Event::customerId,
                        Collectors.summingLong(event ->
                                event.error()
                                        ? event.latencyMs()
                                        : 0L)
                ));
    }

    public static void main(String[] args) {
        List<Event> events = createData(100_000);

        long boxed = boxedTotal(events);
        long primitive = primitiveTotal(events);

        Map<Integer, Long> groups = groupedTotal(events);
        long groupedSum = groups.values().stream()
                .mapToLong(Long::longValue)
                .sum();

        if (boxed != primitive || boxed != groupedSum) {
            throw new AssertionError(
                    "Different aggregate results");
        }

        System.out.println(
                "events=" + events.size()
                + ", customers=" + groups.size()
                + ", totalErrorLatency=" + primitive
        );
    }
}
~~~

Chạy:

~~~bash
javac --release 17 PipelineDiagnosticsDemo.java
java PipelineDiagnosticsDemo
~~~

Trong dữ liệu này có 100.000 bản ghi và tối đa 2.000 mã khách khác nhau. Pipeline `groupedTotal` có **nhiệm vụ nghiệp vụ rộng hơn** hai pipeline chỉ tính tổng: nó phải giữ Map cho từng khách. Do đó, **không** so thời gian của `groupedTotal` với `primitiveTotal` như một phép đo "API nào nhanh hơn" khi đầu ra khác nhau. Mục tiêu của ví dụ là kiểm chứng kết quả chung và tạo bối cảnh phân tích retained heap.

Chương trình **không** dùng `System.nanoTime()` để tuyên bố một cách viết nhanh hơn. Muốn đo có độ tin cậy, ta sẽ dùng JMH ở phần tiếp theo.

## 6. Phân biệt CPU bottleneck với GC bottleneck

Một pipeline chậm có thể nằm ở những nơi rất khác nhau:

### Nghẽn CPU

Dấu hiệu cần tìm:

- CPU bận thực hiện mapper, comparator, phép hash hoặc xử lý chuỗi.
- JFR hoặc profiler cho thấy nhiều mẫu CPU ở các hàm xử lý dữ liệu.
- Latency tăng theo số phần tử hoặc độ phức tạp thuật toán.
- GC pause chiếm phần nhỏ tổng thời gian, dù có allocation.

Ví dụ một pipeline như:

~~~java
List<String> normalized = names.stream()
        .map(name -> expensiveNormalize(name))
        .toList();
~~~

Nếu `expensiveNormalize` thật sự đắt, thay `toList` bằng collector khác chưa chắc giải quyết được nút thắt. Phải đo vị trí CPU đang tiêu tốn.

### Nghẽn GC hoặc áp lực heap

Dấu hiệu cần tìm:

- Allocation rate cao đi cùng các đợt GC thường xuyên.
- GC pause hoặc concurrent GC work chiếm tỷ lệ đáng kể thời gian và CPU.
- Heap sau GC tăng dần vì dữ liệu còn được giữ.
- Allocation failures, overhead GC hoặc OutOfMemoryError xuất hiện trong workload thật.
- Độ trễ đuôi (*tail latency*, chẳng hạn p95/p99) có tương quan với hoạt động GC.

Tuy nhiên, **GC log có nhiều dòng không chứng minh GC là nguyên nhân chính**. Một collector hiệu quả có thể xử lý nhiều object ngắn hạn với pause thấp. Cần so timeline của GC với latency, CPU và heap trước khi kết luận.

### Nghẽn chờ I/O hoặc khóa

Dấu hiệu cần tìm:

- CPU có vẻ thấp nhưng request vẫn chậm.
- Thread bị chặn ở đọc tệp, network, JDBC, lock hoặc chờ hàng đợi.
- JFR cho thấy thời gian `FileRead`, `SocketRead`, `ThreadPark` hoặc contention đáng kể.
- Thêm `parallelStream` không tăng throughput, thậm chí tạo thêm contention.

Trong trường hợp này, đổi `map` sang `mapToLong` có thể chỉ tiết kiệm chút overhead mà không giải quyết thời gian chờ chính.

## 7. Pipeline lazy: không đo phần chưa thực thi

Stream chủ yếu dùng **đánh giá lazy**. Đo thời gian chỉ để xây pipeline sau đây dễ gây hiểu lầm:

~~~java
var pipeline = events.stream()
        .filter(Event::error)
        .mapToLong(Event::latencyMs);

// Chưa có terminal operation: pipeline có thể chưa duyệt nguồn.
~~~

Phép đo đáng tin cậy phải có **terminal operation** thực sự tiêu thụ dữ liệu:

~~~java
long result = events.stream()
        .filter(Event::error)
        .mapToLong(Event::latencyMs)
        .sum();
~~~

Nhưng cũng không được cho rằng **mọi lambda luôn được gọi** chỉ vì có terminal operation. Stream API cho phép một số tối ưu dựa trên thuộc tính nguồn và pipeline.

Ví dụ:

~~~java
long count = List.of("a", "b", "c").stream()
        .peek(System.out::println)
        .count();
~~~

Với nguồn `SIZED` có kích thước xác định, một số implementation có thể tính `count()` mà **không thực hiện mọi thao tác không ảnh hưởng tới số lượng**, khiến action của `peek` không được gọi như dự đoán.

**Không dùng số lần gọi `peek` làm thước đo công việc được bảo đảm**, và không đặt logic nghiệp vụ bắt buộc trong `peek`. Trong benchmark, phải chọn terminal operation giúp compiler/harness quan sát được kết quả và không đo một pipeline chưa thực thi.

## 8. Đo GC bằng unified logging

Trên JDK hiện đại, có thể dùng **unified logging** để quan sát hoạt động GC:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags \
     -jar application.jar
~~~

Lệnh minh họa theo shell hỗ trợ dấu `\` nối dòng. Trong PowerShell/Windows, nên đặt toàn bộ tùy chọn trên một dòng hoặc dùng quy tắc xuống dòng của PowerShell:

~~~text
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar application.jar
~~~

File `gc.log` có thể cung cấp thông tin về collector, thời gian GC, heap trước/sau collection và các sự kiện phù hợp với cấu hình JDK. Cần phân tích:

1. **Thời gian GC** theo thời gian chạy ứng dụng; GC pause dài nhất và phân bố pause.
2. **Tần suất GC** so với lượng request/batch và allocation rate.
3. **Heap trước/sau GC**: dữ liệu sống có tăng không hay chỉ là object tạm?
4. **Loại GC**: young collections, concurrent phases, full collections theo collector thực tế.
5. **Tương quan với latency**: thời điểm request chậm có trùng hoạt động GC đáng kể không?
6. **Ngữ cảnh máy**: heap size, CPU, tải, JDK, flags, container memory limit.

**Không lấy riêng số lượng young GC làm KPI tiêu cực.** Tần suất cao hơn có thể đơn giản là collector thu hồi những đối tượng ngắn hạn đúng thiết kế. Điều cần đánh giá là tác động thật lên latency, throughput và tài nguyên.

### GC overhead và retention không giống nhau

Nếu heap sau GC luôn trở về gần cùng mức, có thể workload tạo nhiều object ngắn hạn. Nếu heap sau GC tăng liên tục theo khối dữ liệu/cache, cần điều tra **retained objects** và những tham chiếu giữ chúng sống. Một leak logic có thể là một `List` static, một Map cache không giới hạn, một callback giữ dữ liệu cũ, hoặc quá nhiều khóa trong `groupingBy`.

GC không thể "giải phóng" những object vẫn còn được ứng dụng tham chiếu hợp lệ.

## 9. Sử dụng Java Flight Recorder (JFR)

**Java Flight Recorder** giúp thu thập các sự kiện runtime trong lúc ứng dụng chạy. Với JDK hỗ trợ JFR, có thể ghi profile:

~~~bash
java -XX:StartFlightRecording=filename=pipeline.jfr,settings=profile,dumponexit=true \
     -jar application.jar
~~~

Trên môi trường chỉ chạy một dòng:

~~~text
java -XX:StartFlightRecording=filename=pipeline.jfr,settings=profile,dumponexit=true -jar application.jar
~~~

Sau khi ứng dụng kết thúc, xem tổng quan bằng CLI:

~~~bash
jfr summary pipeline.jfr
~~~

Có thể in một số loại event nếu chúng có mặt trong recording:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.ObjectAllocationSample,jdk.GarbageCollection pipeline.jfr
~~~

Không phải mọi recording đều bật tất cả event; **các sự kiện cấp phát có thể là lấy mẫu**, không phải một bảng đếm chính xác từng object. Cấu hình `profile` có overhead khác `default`, và các phiên bản JDK có thể khác nhau về event/config. Kiểm tra recording đang dùng trước khi kết luận.

Các góc nhìn quan trọng:

| Nhóm JFR | Điều cần tìm |
| --- | --- |
| **Execution samples** | Những phương thức nào chiếm nhiều mẫu CPU? |
| **Allocation samples** | Loại object và stack nào xuất hiện nhiều trong mẫu cấp phát? |
| **GC events** | Hoạt động GC và pause có trùng đỉnh latency không? |
| **File/Socket I/O** | Đọc file, đọc mạng và độ trễ chờ nguồn |
| **Thread parking/locks** | Thread chờ, tranh chấp khóa, mức song song thực tế |
| **Heap/threads** | Xu hướng sử dụng tài nguyên trong quá trình chạy |

Có thể mở `pipeline.jfr` bằng công cụ phân tích tương thích như **Java Mission Control** để xem timeline và call stack thuận tiện hơn. Dùng các kết quả này để tạo **giả thuyết cụ thể**: ví dụ "bước tạo chuỗi trong mapper chiếm nhiều allocation samples" thay vì "Stream API chậm".

### Thận trọng với profiler

Profiler không "nhìn thấy" mọi object bị tối ưu hóa, và công cụ thu thập có chi phí riêng. Không nên coi một screenshot JFR hoặc một lần ghi profile ngắn là bằng chứng đủ để thay kiến trúc. Ghi lại môi trường chạy, thời gian đo, tải, mẫu dữ liệu và các chỉ số trước/sau.

## 10. JMH: đo latency và cấp phát trên mỗi operation

**JMH** (*Java Microbenchmark Harness*) được thiết kế để benchmark mã JVM có warm-up, fork và lặp đo. Khi so hai pipeline cùng ngữ nghĩa, JMH giúp tránh nhiều sai lệch của một vòng lặp `System.nanoTime()` tự viết.

Đây là ví dụ **cần dependency JMH và annotation processor** trong dự án benchmark, không chỉ JDK chuẩn. Nó đo đúng **cùng phép tổng độ trễ lỗi** bằng hai cách: boxed và primitive.

Trong một project JMH phù hợp, lưu vào `src/main/java/benchmark/PipelineAllocationBenchmark.java` (một lớp trong package, không phải default package):

~~~java
package benchmark;

import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 4)
@Measurement(iterations = 6)
@Fork(2)
public class PipelineAllocationBenchmark {

    record Event(long latencyMs, boolean error) {}

    @State(Scope.Thread)
    public static class Data {

        @Param({"1000", "100000"})
        public int count;

        List<Event> input;

        @Setup(Level.Trial)
        public void setup() {
            input = IntStream.range(0, count)
                    .mapToObj(i -> new Event(
                            1L + i % 97,
                            i % 9 == 0
                    ))
                    .toList();
        }
    }

    @Benchmark
    public long boxedSum(Data data) {
        return data.input.stream()
                .filter(Event::error)
                .map(Event::latencyMs)
                .reduce(0L, Long::sum);
    }

    @Benchmark
    public long primitiveSum(Data data) {
        return data.input.stream()
                .filter(Event::error)
                .mapToLong(Event::latencyMs)
                .sum();
    }

    @Benchmark
    public long imperativeSum(Data data) {
        long result = 0L;
        for (Event event : data.input) {
            if (event.error()) {
                result += event.latencyMs();
            }
        }
        return result;
    }
}
~~~

Ba nhánh tạo **cùng tổng** theo bộ dữ liệu đã định nghĩa. Nhánh vòng lặp là **baseline để định lượng overhead**, không phải mặc định cách viết cần chọn trong ứng dụng.

Lệnh chạy JMH phụ thuộc cấu hình build. Với một artifact benchmark JMH đã được tạo đúng, có thể sử dụng dạng:

~~~bash
java -jar benchmarks.jar PipelineAllocationBenchmark -prof gc
~~~

`-prof gc` giúp JMH báo những thống kê cấp phát/GC có sẵn tùy profiler/JVM, chẳng hạn lượng byte cấp phát chuẩn hóa theo operation. Không tự mặc định mọi thông số đều có trên mọi JDK.

### Đọc kết quả đúng phạm vi

Một bảng **mục tiêu đo**, không phải dữ liệu đã đo:

| Benchmark | Ngữ nghĩa | Thông số cần so |
| --- | --- | --- |
| `boxedSum` | Tổng độ trễ của event lỗi | µs/op, B/op, GC |
| `primitiveSum` | Cùng tổng | µs/op, B/op, GC |
| `imperativeSum` | Cùng tổng | µs/op, B/op, GC |

Với từng cấu hình `count`:

- Kiểm tra **kết quả đúng** bằng test riêng trước.
- So **thời gian và cấp phát** cùng trên một lượng dữ liệu.
- Lặp qua nhiều fork để hạn chế sai lệch JIT và lịch hệ thống.
- Không tính việc tạo danh sách vào mỗi phép đo, vì việc tạo dữ liệu nằm trong `@Setup(Level.Trial)`.
- Chỉ kết luận thay đổi khi có chênh lệch đủ ổn định và đáng kể đối với workload thực tế.

JMH trả giá trị `long` của benchmark, giúp harness quan sát kết quả. Với workload khác, có thể dùng `Blackhole` để tiêu thụ kết quả đúng cách. Không cố loại bỏ phép tính chỉ để đo số vòng lặp rỗng.

## 11. Chỉ số B/op và MB/s: hiểu đúng trước khi tối ưu

Hai chỉ số liên quan:

~~~text
allocation per operation ≈ byte cấp phát / số operation
allocation rate ≈ byte cấp phát / thời gian
~~~

Nhưng cách tính thực tế phụ thuộc công cụ đo, đơn vị work/op, profiler và thuật toán lấy mẫu.

Ví dụ **giả định**, không phải kết quả JMH:

~~~text
A: 4 KB/op, 1.000 ops/s -> khoảng 4 MB/s
B: 8 KB/op,   100 ops/s -> khoảng 0,8 MB/s
~~~

B có **B/op cao hơn** nhưng allocation rate mỗi giây thấp hơn vì throughput thấp hơn. Do đó không nên so allocation rate mà bỏ qua throughput, kích thước input và latency.

Tương tự, một optimization giảm B/op nhưng làm thời gian tăng gấp đôi có thể không đáng giá nếu ứng dụng đang nghẽn CPU chứ không nghẽn GC.

**Cẩn thận với "allocation = memory leak":** cấp phát những đối tượng ngắn hạn là một phần bình thường của JVM. Leak logic là khi **dữ liệu đáng lẽ hết vòng đời vẫn bị tham chiếu**, khiến live heap hoặc tài nguyên khác tích tụ ngoài dự kiến.

## 12. Khi nào nên thay toList bằng một phép tổng hợp?

Một pipeline giữ tất cả phần tử đầu ra:

~~~java
List<Long> values = events.stream()
        .filter(Event::error)
        .map(Event::latencyMs)
        .toList();

long total = 0L;
for (Long value : values) {
    total += value;
}
~~~

Đoạn này materialize `List<Long>` và các giá trị trong đó rồi mới tính tổng. Nếu **chỉ cần một tổng số**, có thể tránh giữ danh sách trung gian:

~~~java
long total = events.stream()
        .filter(Event::error)
        .mapToLong(Event::latencyMs)
        .sum();
~~~

Khác biệt trọng tâm không chỉ là boxed/primitive, mà là **dạng kết quả nghiệp vụ**:

- Nếu cần xuất toàn bộ latency cho giao diện, `toList()` có thể là cần thiết.
- Nếu chỉ cần tổng, đếm, min/max, nên dùng terminal operation tương ứng.
- Nếu cần thống kê theo khóa, chọn downstream collector chỉ giữ các chỉ số cần dùng.
- Nếu cần cả danh sách kết quả lẫn tổng, phải cân nhắc có thể tính trong một lượt bằng collector phù hợp hay không.

Một pipeline lazy **không đồng nghĩa không giữ dữ liệu**: `toList`, `sorted` và một số collector vẫn có thể cần giữ rất nhiều phần tử.

## 13. groupingBy: kiểm soát cardinality và downstream collector

Một điểm nghẽn bộ nhớ điển hình là gom theo khóa có **độ phân biệt cao** (*high cardinality*).

~~~java
Map<Integer, List<Event>> grouped = events.stream()
        .collect(Collectors.groupingBy(
                Event::customerId
        ));
~~~

Nếu mỗi event có `customerId` khác nhau, Map phải giữ số lượng mục tăng gần bằng số event. Nếu mỗi nhóm là List, số container và tham chiếu cũng tăng.

Trong trường hợp chỉ cần đếm hoặc cộng:

~~~java
Map<Integer, Long> errorCountByCustomer =
        events.stream().collect(
                Collectors.groupingBy(
                        Event::customerId,
                        Collectors.summingLong(
                                event -> event.error() ? 1L : 0L)
                )
        );
~~~

Kết quả giữ một tổng `Long` cho mỗi khóa thay vì các List chứa mọi `Event`. Tuy vậy, **Map vẫn tăng theo số khách hàng phân biệt**. Không thể gọi đây là bộ nhớ O(1) khi số khóa tăng không giới hạn.

Nếu dữ liệu gốc có một mã khác nhau cho mỗi request, cần đánh giá liệu có thể nhóm theo mã ít phân biệt hơn (chẳng hạn dịch vụ hoặc giờ) mà vẫn đúng nghiệp vụ. Nếu thật sự cần mọi khóa, cân nhắc database, external aggregation hoặc giới hạn/batch rõ ràng.

### Thận trọng với groupingByConcurrent

Trong parallel Stream, `groupingByConcurrent` có thể giảm một số chi phí gộp giữa các Map nhưng đồng thời thay đổi đặc tính về thứ tự; nó không tự bảo đảm tăng tốc hoặc giảm allocation.

Nếu downstream là `toList()` và thứ tự trong từng nhóm có ý nghĩa, không được thay `groupingBy` bằng `groupingByConcurrent` chỉ để tối ưu mà bỏ qua hợp đồng unordered.

## 14. sorted, distinct và tác vụ có trạng thái

Một số thao tác trung gian có thể trở thành nút thắt do cần phối hợp hoặc giữ trạng thái.

### sorted

~~~java
List<Event> ordered = events.stream()
        .sorted(java.util.Comparator.comparingLong(
                Event::latencyMs))
        .toList();
~~~

Sắp xếp toàn bộ nguồn thường có thời gian **O(N log N)** và có thể cần bộ nhớ trung gian O(N) tùy implementation. Nếu nghiệp vụ chỉ cần **phần tử lớn nhất**, dùng phép tổng hợp:

~~~java
java.util.Optional<Event> slowest = events.stream()
        .max(java.util.Comparator.comparingLong(
                Event::latencyMs));
~~~

Cách này không cần tạo danh sách đã sắp xếp toàn bộ chỉ để lấy một phần tử. Nếu cần **top-K** với K nhỏ, có thể cân nhắc heap giới hạn hoặc collector chuyên biệt, nhưng phải thiết kế quy tắc phá hòa và kiểm tra tính đúng.

### distinct

~~~java
long uniqueCustomers = events.stream()
        .map(Event::customerId)
        .distinct()
        .count();
~~~

`distinct` cần theo dõi những khóa đã thấy để không đếm trùng; số khóa phân biệt lớn có thể làm trạng thái tăng. Nếu mục tiêu thực là ước lượng cardinality trên nguồn quá lớn, có thể phải dùng thuật toán xấp xỉ theo sai số được công bố; Stream API không tự biến `distinct` thành bộ đếm cardinality bộ nhớ hằng số.

### Các phép lấy tiền tố

`limit`, `skip`, `takeWhile` và `dropWhile` trên nguồn có encounter order có thể cần phối hợp khi chạy song song, nhất là khi phải giữ ranh giới tiền tố chính xác. Gọi `unordered()` có thể thay đổi ngữ nghĩa; chỉ làm vậy khi ứng dụng không cần thứ tự logic của kết quả.

## 15. Nghẽn ở nguồn: Spliterator và nguồn I/O

Pipeline tính toán hiệu quả đến mấy cũng không vượt được một nguồn cấp dữ liệu chậm mà không thay đổi kiến trúc.

Các trường hợp thường gặp:

| Nguồn | Giới hạn cần kiểm tra | Gợi ý |
| --- | --- | --- |
| `ArrayList`, mảng | CPU, cache locality, kích thước dữ liệu | Dễ chia, thích hợp thử CPU-bound workloads |
| `IntStream.range` | Thao tác trên mỗi phần tử | Nguồn số dễ chia, thường ít overhead |
| `Iterator` bọc thành Stream | `trySplit` và cách truy cập từng phần tử | Có thể phải lấy lô tuần tự, khó tăng tốc |
| `Files.lines` | I/O, charset decode, tốc độ ổ đĩa | Không tự nhanh hơn khi gọi `parallel()` |
| Database cursor | Thời gian DB/network và fetch size | Stream không thay thế tối ưu truy vấn |
| Nguồn tự viết Spliterator | `estimateSize`, `SIZED`, `ORDERED`, `trySplit` | Khai báo đặc tính trung thực và kiểm thử việc chia |

Một nguồn có thể bị nghẽn vì `trySplit()` không hiệu quả hoặc vì bước đọc tuần tự. Trong trường hợp này, `parallelStream` có thể tạo thêm các task nhưng không tăng thông lượng nguồn.

**Không khai báo sai `Spliterator.SIZED` hoặc `SUBSIZED` để mong Stream chạy nhanh hơn.** Các characteristic là hợp đồng được runtime dùng để tối ưu; khai báo sai có thể dẫn đến kết quả không đúng hoặc những tối ưu không hợp lệ.

### Rò rỉ file handle không đồng nghĩa có nhiều object trên heap

Một pipeline có thể không giữ nhiều object nhưng vẫn khiến hệ thống hết file descriptor/handle nếu bỏ quên đóng nguồn I/O. Với `Files.lines`, hãy dùng `try-with-resources` để quản lý vòng đời, kể cả khi terminal operation dừng sớm:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long errorLines(Path path) throws java.io.IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {
        return lines.filter(s -> s.startsWith("ERROR")).count();
    }
}
~~~

`count()` hoàn thành không có nghĩa nó đã tự gọi `close()`. Khi điều tra một ứng dụng chậm hoặc thiếu tài nguyên, ngoài heap/GC hãy kiểm tra cả số lượng file handle, connection, thread và quyền sở hữu nguồn. **GC tuning không sửa được một lỗi quản lý vòng đời nguồn.**

## 16. Parallel stream: phân biệt tăng tốc với contention

Trên công việc CPU-bound độc lập với mỗi phần tử, xử lý song song **có thể** tăng throughput khi nguồn chia được, dữ liệu đủ lớn và chi phí gộp thấp.

Nhưng đồng thời có thể xuất hiện:

- **Cấp phát nhiều hơn** do các vùng tích lũy theo nhánh và dữ liệu gộp tạm.
- **Contended locks** nếu mapper cập nhật state/collection bên ngoài.
- **Nhiều cache misses** hoặc chi phí chia task lớn hơn công việc cần tính.
- **Áp lực CPU** với các request khác đang dùng common pool hoặc tài nguyên hệ thống.
- **Thao tác ordered** buộc phải phối hợp để giữ thứ tự.
- **GC pressure** tăng do nhiều task cấp phát cùng lúc.

Ví dụ **không an toàn**:

~~~java
List<Long> output = new java.util.ArrayList<>();

events.parallelStream()
        .map(Event::latencyMs)
        .forEach(output::add);
~~~

`ArrayList` không được thiết kế để nhiều task cùng ghi mà không đồng bộ. Một lần chạy cho đủ số phần tử không chứng minh chương trình đúng.

Thay bằng terminal operation:

~~~java
List<Long> output = events.parallelStream()
        .map(Event::latencyMs)
        .toList();
~~~

Với nguồn có encounter order, `toList()` giữ thứ tự kết quả. Nhưng nếu chỉ cần tổng độ trễ, một `mapToLong(...).sum()` còn tránh nhu cầu tạo toàn bộ danh sách.

Không suy rằng thêm `synchronized` giải quyết cả vấn đề. Nó có thể đảm bảo một phép cập nhật riêng lẻ, nhưng gây contention và không tự giữ encounter order trong `forEach`.

## 17. Tính chính xác số học khi tối ưu giảm allocation

Một tối ưu hiệu năng **không được đổi ngữ nghĩa nghiệp vụ**.

Nếu đang cộng tiền tệ bằng `BigDecimal`:

~~~java
BigDecimal total = amounts.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Thay bằng `double` có thể giảm hoặc đổi đặc tính allocation nhưng cũng có thể làm mất tính chính xác thập phân và thay đổi quy tắc làm tròn.

Với `BigDecimal`, các phép toán thường trả đối tượng kết quả mới. Điều đó không tự chứng minh `BigDecimal` là lựa chọn cần bỏ. Phải kiểm tra yêu cầu về độ chính xác, throughput và số đo memory thực trước khi đánh đổi.

Nếu nghiệp vụ cho phép lưu **đơn vị nhỏ nhất** của tiền trong `long`, một `LongStream` có thể hiệu quả, nhưng cần kiểm soát overflow và phép đổi đơn vị. Nếu không có hợp đồng chuyển đổi chính xác, **đừng sửa BigDecimal thành long chỉ để benchmark đẹp hơn**.

Tương tự, chuyển từ collector giữ toàn bộ danh sách sang chỉ lấy tổng sẽ giảm memory nhưng **không tương đương** nếu ứng dụng còn cần từng bản ghi đầu ra.

## 18. Chẩn đoán vấn đề bằng một quy trình có thể lặp lại

Có thể áp dụng quy trình chín bước:

### Bước 1 — Viết rõ mục tiêu

Ví dụ: "Giảm p95 thời gian tổng hợp 100.000 sự kiện/batch mà không làm thay đổi tổng và danh sách nhóm."

### Bước 2 — Cố định workload và dữ liệu

Lưu seed/fixture, kích thước input, tỷ lệ qua filter, số khóa phân biệt, fan-out, JDK, heap và mức song song. Không dùng nguồn network live không ổn định làm bằng chứng duy nhất.

### Bước 3 — Đo baseline end-to-end

Ghi thời gian, throughput, CPU, heap, allocation, GC pauses và các chỉ số chờ. Xác định thành phần nào đang chi phối.

### Bước 4 — Dùng JFR/GC log để khoanh vùng

Tìm allocation hotspots, retained heap, thời điểm GC, CPU samples và thread states. Nếu thấy đa phần thời gian ở database/network, đừng bắt đầu bằng thay `map`.

### Bước 5 — Tạo giả thuyết cụ thể

Ví dụ: "Trong hot path, `map(Event::latencyMs).reduce` tạo overhead so với `mapToLong().sum()`." Giả thuyết cần được đo, không kết luận ngay.

### Bước 6 — Đưa ra thay đổi nhỏ

Chỉ đổi một yếu tố tại một thời điểm. Không đồng thời thay GC flags, đổi thuật toán, nâng JDK và bật parallel; như vậy không biết điều gì gây cải thiện hay hồi quy.

### Bước 7 — Kiểm thử đúng trước khi benchmark

So với oracle hoặc fixture: kết quả từng nhóm, thứ tự nếu cần, behavior null, overflow, exception và nguồn I/O được đóng.

### Bước 8 — Benchmark cùng điều kiện

Dùng JMH cho microbenchmark và phép đo tích hợp cho pipeline thật. So latency/throughput **và** B/op, GC, peak memory. Lặp nhiều lượt, xem độ biến thiên.

### Bước 9 — Quyết định và giám sát

Chỉ nhận tối ưu nếu cải thiện đáng kể trên workload đại diện mà không tăng rủi ro/hạn chế bảo trì vượt lợi ích. Khi triển khai, giám sát metric theo thời gian và có cách quay lại nếu hiệu năng thực không như dự đoán.

Sơ đồ quyết định:

~~~text
Pipeline chậm / heap tăng
           |
           v
Xác định workload + baseline
           |
           v
  JFR + GC log + metrics
           |
     +-----+------+------------------+
     |            |                  |
   CPU nóng    GC/heap nóng       I/O/lock chờ
     |            |                  |
 map/hash/      allocation +       nguồn, khóa,
 sort/reduce    retention          truy vấn
     |            |                  |
     +------------+------------------+
                  |
                  v
        Chọn một thay đổi nhỏ
                  |
                  v
       Kiểm thử đúng + Benchmark
                  |
          +-------+-------+
          |               |
      Có cải thiện     Không cải thiện
          |               |
      Theo dõi         Giữ/revert và
      sau triển khai   tìm nút thắt khác
~~~

## 19. Bảng tình huống: đọc triệu chứng, không đoán nguyên nhân

| Quan sát | Giả thuyết nên kiểm tra | Phép đo tiếp theo |
| --- | --- | --- |
| B/op cao, GC pause thấp | Nhiều object ngắn hạn nhưng GC hiệu quả | JMH `-prof gc`; có thật ảnh hưởng throughput? |
| Heap sau GC tăng theo thời gian | Map/cache/List giữ dữ liệu | Heap profile, JFR/heap dump theo quyền vận hành |
| CPU cao trong mapper | Phép xử lý/parse đắt | CPU samples, so thuật toán hoặc dữ liệu |
| CPU thấp, latency cao | Chờ I/O, khóa, queue | JFR I/O/ThreadPark, trace hệ thống |
| `parallelStream` chậm hơn | Chia task/merge/ordered/lock overhead | JMH sequential vs parallel cùng workload |
| GC pause tương quan p99 | Collector/heap pressure | GC log timeline và p99 theo thời điểm |
| `groupingBy` dùng heap lớn | Nhiều nhóm hoặc lưu List mỗi nhóm | Đo cardinality, retained heap, đổi downstream nếu hợp đồng cho phép |
| `sorted` chi phối thời gian | Sắp xếp toàn bộ khi chỉ cần top-K/max | CPU sample, benchmark thuật toán thay thế |
| `flatMap` sinh nhiều Stream con | Fan-out nhỏ, overhead trung gian | So với `mapMulti` cùng ngữ nghĩa/JDK |
| JFR ít allocation samples | Mẫu cấp phát chưa đủ, JIT tối ưu hoặc cấu hình sự kiện khác | Kiểm tra recording, JMH allocation profiler |
| Latency chỉ tăng khi tải cao | Contention, saturation, GC pressure hoặc I/O quota | Load test, theo dõi concurrency và resource usage |

Tránh suy diễn đơn tuyến: một hiện tượng có thể có nhiều nguyên nhân, và hai nguyên nhân có thể cùng xuất hiện.

## 20. Những điều không nên làm khi chưa có phép đo

1. **Không tối ưu bằng cảm giác:** "Stream chậm", "lambda tạo object", "GC nhiều là xấu" không phải kết luận kỹ thuật đầy đủ.
2. **Không thay `flatMap` bằng `mapMulti` hàng loạt:** đo theo fan-out, JDK và short-circuit. Một số triển khai `mapMulti` có thể dùng buffer.
3. **Không chuyển tất cả sang parallel:** đo CPU, chia nguồn, ordered stages, contention và kết quả nghiệp vụ.
4. **Không dùng `toList` nếu chỉ cần một tổng**, nhưng cũng không bỏ danh sách nếu caller thực sự cần mọi phần tử.
5. **Không gỡ validation hoặc logic lỗi để tăng tốc:** điều đó biến benchmark thành một bài toán khác.
6. **Không dùng `peek`/side effect làm thước đo số phần tử chắc chắn đã xử lý.**
7. **Không coi JFR sampling là đếm tuyệt đối từng allocation**, hoặc một log GC là bằng chứng hoàn chỉnh về memory leak.
8. **Không thay cấu hình GC theo kết luận từ một microbenchmark** khi chưa đo tác động end-to-end.
9. **Không cấp heap lớn vô hạn để "chữa" retained objects**: heap lớn có thể che triệu chứng nhưng không sửa mô hình giữ dữ liệu.
10. **Không công bố tốc độ tăng gấp N lần khi chưa có benchmark thực tế** được tái lập.

Những nguyên tắc này giúp phân biệt **tối ưu có căn cứ** với thay đổi phức tạp làm giảm khả năng bảo trì hoặc phá hợp đồng dữ liệu.

## 21. Bài tập thực hành

### Bài 1 — Phân biệt cấp phát và giữ bộ nhớ

Một pipeline tạo 100.000 chuỗi tạm, cuối cùng chỉ trả tổng số phần tử. Một pipeline khác chỉ tạo một Map 50.000 khóa và giữ Map trong cache lâu dài. Pipeline nào có memory pressure lớn hơn?

**Đáp án:** Không đủ dữ liệu để khẳng định. Pipeline đầu có thể có **allocation rate** cao nhưng live heap thấp; pipeline sau có thể giữ nhiều object sống lâu. Phải đo B/op, retained heap và tác động GC/throughput.

### Bài 2 — Chọn primitive pipeline

~~~java
long total = events.stream()
        .map(Event::latencyMs)
        .reduce(0L, Long::sum);
~~~

**Yêu cầu:** Viết phiên bản hạn chế boxing.

**Đáp án:**

~~~java
long total = events.stream()
        .mapToLong(Event::latencyMs)
        .sum();
~~~

Cả hai phải áp dụng cùng input, filter và miền số trước khi benchmark. Phiên bản primitive là ứng viên, không phải kết luận chắc chắn nhanh hơn trên mọi JDK.

### Bài 3 — Khi nào bỏ toList?

Một pipeline tính trung bình latency nhưng hiện tại gọi `toList` để giữ mọi latency trước khi cộng. Nên thử thay gì?

**Đáp án:** Dùng `mapToLong(...).average()` nếu chỉ cần trung bình số học và hợp đồng kiểu `OptionalDouble`/dữ liệu rỗng phù hợp. Nếu còn cần danh sách kết quả để hiển thị hoặc điều tra, không thể bỏ `toList` mà vẫn giữ nguyên chức năng.

### Bài 4 — groupingBy và retention

Một báo cáo dùng `groupingBy(key)` rồi chỉ lấy `size()` của từng danh sách. Có thể giảm retained heap bằng cách nào?

**Đáp án:** Thử `groupingBy(key, counting())` để giữ một số đếm theo khóa, không cần List mọi phần tử. Vẫn phải lưu Map theo số khóa phân biệt.

### Bài 5 — Dựa vào GC log có đủ không?

Một batch chạy 100 giây và có 200 lần young GC, nhưng GC pause tổng chỉ 70 ms. Có thể kết luận GC là nguyên nhân batch mất 100 giây không?

**Đáp án:** Không. Pause time được ghi rất nhỏ so với thời gian chạy; cần kiểm tra CPU, GC concurrent work, allocation, I/O và các yếu tố khác. Số lần collection đơn lẻ không chứng minh GC bottleneck.

### Bài 6 — Mẫu JMH thiếu terminal

~~~java
@Benchmark
public Object buildOnly() {
    return events.stream().filter(Event::error);
}
~~~

**Đáp án:** Chủ yếu đo việc tạo pipeline, không đo công việc duyệt/lọc mọi event. Cần terminal operation thực hiện nhiệm vụ muốn đo, đồng thời dùng input được chuẩn bị bên ngoài phép đo.

### Bài 7 — Hai phép đo có công bằng?

Benchmark A dùng `flatMapToInt` và `sum`; B dùng `mapMulti` ra `Stream<Integer>` rồi `toList`. Có thể kết luận API B chậm hơn không?

**Đáp án:** Không. Hai nhánh khác kiểu dữ liệu, mức boxing, terminal operation và dạng đầu ra. Phải thiết kế phép đo cùng nhiệm vụ, cùng kiểu, cùng dữ liệu và cùng mức song song.

### Bài 8 — Parallel và Map chia sẻ

~~~java
Map<Integer, Long> counts = new HashMap<>();

events.parallelStream().forEach(e ->
        counts.merge(e.customerId(), 1L, Long::sum)
);
~~~

**Đáp án:** `HashMap` bị sửa đồng thời từ nhiều task nên không an toàn. Dùng `collect(groupingBy(..., counting()))` hoặc collector concurrent phù hợp nếu ngữ nghĩa cho phép. Đo lại vì thread-safe không tự đồng nghĩa nhanh hơn.

### Bài 9 — Phân tích nghẽn xử lý

Profiler thấy CPU bận ít, phần lớn thread chờ JDBC và GC pause không đáng kể. Bước ưu tiên nên là gì?

**Đáp án:** Điều tra truy vấn, chỉ mục DB, số lần truy vấn, fetch size, connection pool hoặc thiết kế truy cập dữ liệu. Thay `map` thành `mapToLong` không có khả năng giải quyết phần chờ chính nếu tính toán trên JVM chỉ chiếm tỷ lệ nhỏ.

### Bài 10 — Bảo toàn ngữ nghĩa khi tối ưu

Một pipeline dùng `BigDecimal` để tính tiền chính xác và làm tròn tổng một lần. Có nên đổi ngay sang `double` vì JMH cho kết quả nhanh hơn?

**Đáp án:** Không nếu nghiệp vụ cần chính xác thập phân. Benchmark nhanh của bài toán số học khác không đủ biện minh cho việc đổi hợp đồng. Chỉ đổi biểu diễn số khi có quy tắc chuyển đổi chính xác và đã kiểm thử đầy đủ.

## 22. Checklist nghiệm thu tối ưu

Trước khi coi một tối ưu Stream là hoàn tất:

- [ ] Có **workload đại diện** và mục tiêu latency/throughput cụ thể.
- [ ] Ghi rõ JDK, GC, heap, kích thước input, số khóa và mức đồng thời.
- [ ] Đã đo baseline đủ thời gian, không chỉ một lần chạy.
- [ ] Đã xác định bottleneck qua CPU/GC/I/O/lock, không suy đoán chỉ từ mã.
- [ ] Có phép đo allocation B/op và live/peak heap nếu vấn đề là bộ nhớ.
- [ ] Tách số object tạm khỏi những object đang bị giữ tham chiếu.
- [ ] Nếu đổi thuật toán, đã kiểm tra độ phức tạp, fan-out và số nhóm.
- [ ] Nếu đổi collector, vẫn giữ đúng dữ liệu kết quả và yêu cầu thứ tự.
- [ ] Nếu chuyển sang primitive, đã kiểm tra overflow và ý nghĩa kiểu số.
- [ ] Nếu chuyển sang parallel, không có shared mutable state và đã kiểm tra combiner.
- [ ] Nếu pipeline dùng I/O, nguồn được đóng đúng vòng đời.
- [ ] JMH đo **cùng ngữ nghĩa** và có terminal operation thực sự.
- [ ] Phép đo tích hợp cho thấy cải thiện có ý nghĩa trong hệ thống thật.
- [ ] Có cơ chế quan sát sau triển khai và phương án quay lại thay đổi nếu cần.

## 23. Ghi nhớ

- **Allocation rate, live heap và peak memory là ba khái niệm khác nhau.** Nhiều object ngắn hạn không tự bằng memory leak.
- **GC frequency không đủ xác định bottleneck.** Cần đo pause, CPU work, retained heap và tương quan với latency/throughput.
- **Tối ưu pipeline bắt đầu từ kết quả nghiệp vụ.** Nếu chỉ cần tổng, không materialize cả danh sách; nếu chỉ cần count theo nhóm, không giữ List của mọi bản ghi.
- **Primitive streams có thể giảm boxing**, nhưng kết quả thực phụ thuộc JIT và workload; luôn đo.
- **Các thao tác có trạng thái** như `sorted`, `distinct`, `groupingBy` có chi phí theo kích thước input/số khóa; đừng chỉ nhìn độ ngắn của code.
- **Parallel Stream không chữa được mọi nghẽn:** nguồn chia kém, I/O, contention hoặc ordered stages có thể làm nó chậm hơn.
- **JFR xác định nơi đáng điều tra**, GC log cho biết hoạt động thu gom, và JMH đo những thay đổi nhỏ trên cùng workload; benchmark tích hợp xác nhận lợi ích thật.
- **Không dùng số lần gọi mapper/peek làm KPI đảm bảo** khi pipeline có thể lazy, short-circuit hoặc được tối ưu.
- **Tính đúng trước hiệu năng.** Một pipeline nhanh nhưng bỏ sót dữ liệu, tràn số hoặc rò rỉ nguồn I/O không phải tối ưu thành công.

**Ý chính:** Muốn phân tích cấp phát, GC và nghẽn xử lý trong Java Stream API, hãy **đo các hiện tượng riêng biệt**, khoanh vùng nguyên nhân, thay đổi một yếu tố tại một thời điểm và kiểm tra lại cả kết quả lẫn tài nguyên. Tối ưu có giá trị là tối ưu **được chứng minh trên dữ liệu đại diện, đúng hợp đồng nghiệp vụ và không tạo ra rủi ro bộ nhớ hay vận hành mới**.
