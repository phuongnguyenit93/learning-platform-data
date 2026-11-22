# Cố định dữ liệu, phần cứng và cấu hình khi so sánh kết quả đo GC (Java 15+)

## 1. Vì sao một phép so sánh GC cần thí nghiệm có kiểm soát?

Khi đánh giá **Garbage Collector (GC)** của Java, hai lượt chạy có thời gian khác nhau **không nhất thiết do GC khác nhau**. Hiệu năng còn phụ thuộc **dữ liệu đầu vào, lượng object sống, tốc độ cấp phát, máy chủ, CPU quota, giới hạn RAM, JVM/JDK, warmup JIT, số thread, tải hệ thống và cách đo**. Nếu thay đồng thời nhiều yếu tố, ta không thể biết yếu tố nào gây ra sự chênh lệch.

Bài này thuộc nhóm **Đo lường GC** của module **Java 15**, trọng tâm là thiết kế phép so sánh có thể **tái lập, kiểm tra được và có kết luận hợp lệ**. JDK hiện đại vẫn dùng `-Xlog`, Java Flight Recorder (JFR), JMX và các công cụ benchmark. Hai collector làm ví dụ là **G1** và **ZGC**; ZGC trở thành tính năng production trong Java 15, còn từ **JDK 24** chỉ còn chế độ **generational** theo JEP 490. Không sử dụng cờ chọn non-generational ZGC đã bị loại bỏ.

**Nguyên tắc cốt lõi:** trong phép so sánh “G1 hay ZGC tốt hơn với workload X?”, **biến chủ động thay đổi là GC được chọn**; mọi thứ còn lại phải được giữ nguyên trong khả năng thực tế, hoặc được ghi chép để phân tích khi không thể cố định.

Cần phân biệt ba mục tiêu:

1. **So sánh collector:** giữ một phiên bản JDK, ứng dụng, dữ liệu, phần cứng, CPU/RAM và heap giống nhau; chỉ đổi `-XX:+UseG1GC` với `-XX:+UseZGC`.
2. **So sánh cấu hình của cùng một GC:** chỉ đổi một yếu tố như `-Xmx`, CPU limit hoặc một option có ý nghĩa; giữ các yếu tố khác cố định.
3. **So sánh JDK hoặc máy chủ:** chính JDK/phần cứng là biến được thay đổi có chủ đích. Khi đó **không thể nói chênh lệch hoàn toàn do collector** nếu cả JDK/hardware cũng khác.

Các phép thử nhỏ và chạy ít lần chỉ là **smoke test** của quy trình; không đủ chứng minh SLO độ trễ của ứng dụng.

## 2. Ma trận: cố định biến nào, thay đổi biến nào?

| Yếu tố | Khi so sánh G1 với ZGC trên cùng JDK | Vì sao quan trọng? |
| --- | --- | --- |
| **Ứng dụng / commit / artifact** | Cùng file JAR, mã nguồn, dependencies, cấu hình nghiệp vụ | Một thay đổi code có thể làm khác allocation rate và live set. |
| **Dữ liệu đầu vào** | Cùng fixture/snapshot, seed, kích thước, phân bố, thứ tự và tỷ lệ request | Payload lớn/nhỏ hoặc phân bố key khác làm biến dạng object graph và GC behavior. |
| **Load pattern** | Cùng request rate, concurrency, ramp-up, burst, thời lượng và chuỗi thao tác | GC rất nhạy với allocation rate, số object sống và vòng đời object. |
| **JDK** | Cùng vendor, build, architecture, version, VM flags và chế độ JIT | GC implementation/ergonomics thay đổi giữa các bản JDK. |
| **Collector** | **Biến thay đổi:** `UseG1GC` so với `UseZGC` | Đây là yếu tố muốn kiểm định. |
| **Heap** | Cùng `-Xms`, `-Xmx` và chính sách memory, trừ thí nghiệm riêng | Heap headroom ảnh hưởng frequency, concurrent GC, pauses và stalls. |
| **Phần cứng** | Cùng CPU model, RAM, NUMA topology, storage, network; tránh host contention | IPC, memory bandwidth, page faults và scheduler gây nhiễu. |
| **CPU được cấp** | Cùng quota, cpuset/affinity, `ActiveProcessorCount` nếu chủ động đặt | GC threads và ứng dụng tranh CPU; quota thấp gây throttling. |
| **Container/OS** | Cùng image, kernel, cgroups, memory limits, CPU limits, mount & network | Container OOM hay CPU throttling có thể lớn hơn khác biệt GC pause. |
| **JVM/GC logging và JFR** | Cùng nhóm tag, log level, rotation và recording policy | Instrumentation cũng tạo overhead, so sánh phải cùng mức quan sát. |
| **Warmup và phép đo** | Cùng thời lượng warmup, steady state, số lượt đo và cách thống kê | JIT, class loading, caches, heap state làm lượt đầu khác các lượt sau. |
| **Dịch vụ phụ thuộc** | Cùng DB dataset, network path, downstream load hoặc stub cố định | Nếu backend của một lượt chậm hơn, p99 request có thể không liên quan GC. |

**Đừng “công bằng giả”.** Bắt tất cả collector có đúng cùng số GC threads hoặc cùng `MaxGCPauseMillis` không phải lúc nào cũng là hợp đồng tương đương: một số option không áp dụng giống nhau, các thuật toán có cơ chế khác nhau. Phép so sánh baseline nên giữ **cùng ngân sách RAM/CPU và để ergonomics mặc định của từng collector**. Có thể làm thêm vòng **tuned-best-per-GC** sau, nhưng ghi thành thí nghiệm riêng và công bố các điều chỉnh.

## 3. Cố định dữ liệu: quan trọng hơn chỉ giữ seed

### 3.1. Một seed cố định là điểm khởi đầu, không phải toàn bộ fixture

Ví dụ dùng `SplittableRandom` với seed cố định:

~~~java
SplittableRandom rng = new SplittableRandom(20261108L);
int[] data = new int[16384];
for (int i = 0; i < data.length; i++) {
    data[i] = rng.nextInt(256);
}
~~~

Trong **cùng chương trình và môi trường đã kiểm tra**, seed giúp tạo lại tập giá trị tương tự, tránh mỗi lần đo nhận một tập random mới. Tuy nhiên, vẫn cần giữ:

- **Số bản ghi** và **độ lớn payload**, kể cả các bản ghi ngoại lệ có kích thước lớn.
- **Phân bố dữ liệu** (hot keys, tỷ lệ đọc/ghi, object lifetime, tỷ lệ null, trùng lặp).
- **Thứ tự thao tác** và lịch chạy; cùng tập dữ liệu nhưng reorder có thể đổi live set.
- **Trạng thái trước khi đo**: cache nóng/lạnh, queue backlog, kết nối, DB state, heap occupancy.
- **Tiêu chuẩn kiểm tra dữ liệu**: một checksum/hash hay fingerprint ghi lại ở mỗi lượt.

**Checksum cộng đơn giản** có ích để phát hiện lỗi ngẫu nhiên trong fixture minh họa, nhưng **không phải fingerprint chống va chạm**. Khi chuyển fixture giữa ngôn ngữ/JDK/máy, nên lưu **các bytes đầu vào chuẩn** hoặc dùng một SHA-256 digest của snapshot cùng version/schema để chứng minh dữ liệu thật sự giống nhau. Nếu dùng dữ liệu sản xuất được sao chép, cần tuân thủ yêu cầu ẩn danh, quyền riêng tư và phân quyền.

### 3.2. Kiểm soát object graph và lượng rác

GC đo **phân bố tuổi thọ, live set, allocation rate, reference graph và heap pressure**, không chỉ đo tổng số bytes cấp phát.

Ví dụ cùng 1 GiB bytes được tạo ra nhưng:

- Workload A tạo nhiều object ngắn hạn rồi bỏ ngay.
- Workload B giữ nhiều object sống qua nhiều GC cycles.
- Workload C giữ object lớn/array lớn, dùng direct buffers hoặc native resources.

Ba kiểu tải có thể đưa đến kết quả rất khác nhau. Để so sánh **GC**, phải mô tả cả **số object giữ sống (retained)**, kích thước object, tốc độ cấp phát và các ràng buộc tài nguyên. Chỉ ghi `-Xmx` hoặc số request là chưa đủ.

Bản thử ở mục 7 cố định **16.384 bản ghi**, mỗi lượt tạo một mảng `8.192 + value` byte và giữ tối đa **256 mảng**; có vòng warmup riêng. Đây là một fixture **để học kỹ thuật kiểm soát thí nghiệm**, không được xem là đại diện cho dịch vụ web thật.

## 4. Cố định phần cứng, CPU và bộ nhớ hệ thống

### 4.1. CPU model, NUMA và nhiễu nền

Trên cùng một máy vật lý, CPU vẫn có thể chạy ở tần số khác nhau vì turbo boost, power/thermal throttling, công việc của process khác, số core còn trống hoặc NUMA memory placement. Vì vậy:

1. Ghi **CPU model, số core/thread, RAM, NUMA, kernel/OS** và môi trường ảo hóa.
2. Chạy A/B trên **cùng host** nếu mục tiêu là collector comparison. Nếu chạy ở hai host, ít nhất phải có nhóm host tương đương và lặp lại theo các cặp host.
3. Cô lập job benchmark khỏi những tải nặng khác; tránh chạy song song GC test với compiler, backup hay ứng dụng ngốn CPU.
4. Ổn định chính sách CPU frequency/power ở mức thực tế được phép, ghi nhận nếu không kiểm soát được.
5. Nếu dùng bare metal, xem xét **CPU affinity/cpuset** và ảnh hưởng NUMA; đừng tự pin tùy tiện gây nghẽn core hoặc đổi locality.

Không thể “cố định hoàn toàn” OS scheduler, network hay nhiệt độ. Cách làm chuyên nghiệp là **giảm nhiễu, ghi log môi trường và chạy nhiều lượt**.

### 4.2. Container CPU quota không phải JVM CPU count

Trên Kubernetes, **CPU request** chủ yếu tác động tới scheduling/ưu tiên chia sẻ tài nguyên, còn **CPU limit** thường được thực thi qua cgroup quota, có thể gây **CPU throttling**. `-XX:ActiveProcessorCount=2` chỉ báo số CPU hiệu dụng cho tính toán ergonomics trong JVM; **nó không tự giới hạn kernel cho process ở hai core**.

Nếu muốn thử hai collector trong cùng ngân sách CPU:

- giữ đồng nhất `requests.cpu`/`limits.cpu` hoặc Docker `--cpus`;
- kiểm tra `cpu.stat` (cgroups v2) như `nr_throttled` và `throttled_usec`;
- ghi nhận `Runtime.availableProcessors()`, GC worker counts và `ActiveProcessorCount`;
- nếu cần core placement giống nhau, dùng cơ chế affinity/cpuset của môi trường, **không chỉ cờ JVM**.

### 4.3. Giới hạn RAM container khác Java heap

`-Xmx128m` là trần Java heap; container còn tính metaspace, code cache, thread stacks, direct buffers, native GC/JVM memory và các thành phần cgroup khác. **OOMKilled** ở cấp container không tương đương `OutOfMemoryError: Java heap space`. Khi chạy cùng `-Xmx` cho G1 và ZGC, vẫn cần theo dõi **RSS, container memory, committed heap, native memory và OOM events**; cùng heap max không bảo đảm cùng memory footprint.

Nếu một collector cần nhiều headroom hơn để thực hiện concurrent GC và bị allocation stalls tại cùng `-Xmx`, đó là **kết quả có ý nghĩa trong ngân sách đã chọn**. Đừng sửa `-Xmx` riêng cho nó rồi vẫn trình bày như phép so sánh chỉ đổi GC. Có thể làm phép so sánh thứ hai cho mỗi collector với ngân sách đã tune, nhưng phải công bố khác biệt.

## 5. Giữ cấu hình JVM cố định

### 5.1. Đúng phiên bản và flag có hiệu lực

Trước mỗi đợt đo, lưu:

~~~bash
java -version
java -XX:+PrintFlagsFinal -version
java -Xlog:help
~~~

Ghi **JDK vendor, số build, architecture, GC được chọn**, `-Xms`, `-Xmx`, `ActiveProcessorCount`, `UseContainerSupport`, các options JIT, code cache, logging và OS settings có ý nghĩa. `-XX:+PrintFlagsFinal` có nhiều dòng; dùng thông tin cần thiết để chứng minh VM thực sự chạy như kế hoạch thay vì chỉ chép tham số khởi động.

Trong phép baseline G1/ZGC, chọn collector bằng:

~~~bash
-XX:+UseG1GC
-XX:+UseZGC
~~~

Các dòng này là **flag JVM**, được dùng đầy đủ trong lệnh `java` ở mục 8, không phải shell command độc lập.

Trên **JDK 24+**, ZGC chỉ còn generational theo JEP 490; không dùng cờ `ZGenerational` để bật/tắt chế độ non-generational cũ. So sánh “ZGC Java 15” với “ZGC JDK 27” còn thay đổi nhiều thành phần khác, không thể gọi đó là thí nghiệm chỉ thay GC.

### 5.2. Cùng heap, cùng giới hạn tài nguyên, cùng mức instrumentation

Một baseline thực tế có thể cố định:

~~~text
JDK:             cùng vendor / build / OS / architecture
Ứng dụng:        cùng class/JAR và dependencies
Dữ liệu:         cùng seed, số bản ghi, thứ tự và checksum
Heap:            -Xms128m -Xmx128m
CPU JVM:         -XX:ActiveProcessorCount=2
OS CPU quota:    giữ nguyên ở cả hai lượt (và đo throttling)
GC log:          -Xlog:gc*,safepoint cùng mức cho cả hai
Biến được đổi:   -XX:+UseG1GC  <->  -XX:+UseZGC
~~~

Các giá trị `128m`, `2` là **mẫu dạy học trên máy thử** chứ không phải cấu hình production. `-Xms=-Xmx` làm trần/sàn heap bằng nhau để dễ so baseline; nó cũng tác động tới footprint và hành vi mở rộng heap, nên nếu production sử dụng heap elastic hãy có **thí nghiệm phản ánh production riêng**.

**Không so “G1 có `-Xlog:gc*=trace`” với “ZGC không logging”** nếu định lượng latency vi mô: logging chính là một phần của workload. Ghi log giống nhau nhưng cho phép nội dung/khối lượng log khác nhau theo collector; cân nhắc đo thêm một baseline **không có logging nặng** để lượng hóa observer overhead.

### 5.3. Mục tiêu GC khác với mục tiêu request

`-XX:MaxGCPauseMillis` là mục tiêu mềm được dùng trong ergonomic GC như G1, **không phải** cam kết p99 request, và không có nghĩa hai collector được cấu hình “tương đương” khi gán chung một giá trị. Baseline nên giữ ergonomic defaults phù hợp; khi tunings khác nhau, ghi rõ lý do và target.

## 6. Thiết kế phép đo có kiểm soát: warmup, repetitions và thứ tự A/B

### 6.1. Khởi động JVM mới và warmup

Một JVM mới có chi phí **class loading, JIT compilation, code cache warmup và cache của ứng dụng**. Cùng một chương trình có thể có iteration đầu khác đáng kể các iteration sau.

Với phép đo nghiêm túc:

1. Khởi động process/fork riêng cho mỗi lượt thử.
2. Dùng **warmup đủ dài** để quan sát độ ổn định của throughput/JIT/heap state.
3. Đo trên cửa sổ **steady state**, không gộp phần warmup vào các số liệu chính (trừ khi mục tiêu là startup performance).
4. Nếu cold start cũng là SLO, đo nó **tách riêng** với warm steady-state.

Ba warmup và năm measurement rounds trong code phía dưới chỉ đủ làm **bài kiểm tra quy trình**, không có nghĩa JIT đã thật sự ổn định hay p99 thống kê đủ tin cậy.

### 6.2. Nhiều process độc lập và thứ tự cân bằng

Nếu chạy G1 toàn bộ vào buổi sáng, ZGC toàn bộ vào lúc máy nóng/tải cao, kết luận dễ bị nhiễu. Dùng nhiều vòng **paired A/B**, đổi thứ tự ở các lần đo (ví dụ **G1 → ZGC → ZGC → G1**, rồi đổi một trình tự khác), ghi từng kết quả và đồng thời giám sát nhiệt độ/tải nền. Một số thí nghiệm dùng thứ tự randomized có seed để giảm order effects.

**Không lựa chọn duy nhất lượt chạy đẹp nhất**. Thu các phân phối và dùng thống kê phù hợp như median, percentile/CI, variation giữa process runs, không chỉ min/average của năm lần. Nếu thử nhiều biến điều chỉnh, ghi rõ cách chọn và tránh công bố kết quả “winner” mà bỏ các lần thất bại.

### 6.3. Microbenchmark khác load test toàn hệ thống

- **JMH** (OpenJDK Java Microbenchmark Harness) được thiết kế cho microbenchmark JVM với warmup, measurement, fork, state và cơ chế hạn chế những lỗi đo lường thường gặp. Dùng JMH khi muốn so một **đoạn mã nhỏ**. Không tự thay JMH bằng một vòng `System.nanoTime()` rồi tuyên bố kết quả có độ chính xác cao.
- **GC benchmarking với whole application:** thường cần load generator cố định request rate/concurrency, dataset/DB snapshot, real service dependencies, đủ thời gian steady-state, theo dõi GC logs/JFR và **end-to-end p95/p99/p99.9**.
- **Chương trình học ở mục 7** nằm ở giữa: tự tạo allocation workload **có checksum kiểm soát** và đo thời gian cả một round. Nó hữu ích để **thử quy trình**, không đo đại diện p99 HTTP hoặc GC pause.

## 7. Chương trình Java 17+ chạy độc lập với fixture cố định

Tạo file **`GcFairCompare.java`**, lưu UTF-8. Chương trình giữ nguyên cấu trúc/tập dữ liệu giữa các lượt, kiểm tra checksum và in thời lượng từng measurement round. **Lưu ý:** giá trị `elapsed_ms` chắc chắn biến động theo GC, hệ điều hành, JIT và tải nền, nên không có một stdout thời gian cố định để áp dụng cho mọi máy.

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Locale;
import java.util.SplittableRandom;

public class GcFairCompare {
    private static final long SEED = 20261108L;
    private static final int ROWS = 16384;
    private static final int WARMUP = 3;
    private static final int MEASURE = 5;
    private static final int BASE_BYTES = 8192;
    private static final int RETAINED = 256;
    private static volatile long blackhole;

    private static int[] dataset() {
        SplittableRandom random = new SplittableRandom(SEED);
        int[] values = new int[ROWS];
        for (int i = 0; i < ROWS; i++) {
            values[i] = random.nextInt(256);
        }
        return values;
    }

    private static long expected(int[] values) {
        long total = 0;
        for (int value : values) {
            total += BASE_BYTES + value + value + (value ^ 0x5A);
        }
        return total;
    }

    private static long round(int[] values) {
        Deque<byte[]> live = new ArrayDeque<>();
        long sum = 0;
        for (int value : values) {
            byte[] buffer = new byte[BASE_BYTES + value];
            buffer[0] = (byte) value;
            buffer[buffer.length - 1] = (byte) (value ^ 0x5A);
            live.addLast(buffer);
            if (live.size() > RETAINED) live.removeFirst();
            sum += buffer.length + Byte.toUnsignedInt(buffer[0])
                    + Byte.toUnsignedInt(buffer[buffer.length - 1]);
        }
        if (live.size() != RETAINED) throw new AssertionError("live set changed");
        return sum;
    }

    public static void main(String[] args) {
        int[] values = dataset();
        long dataSum = 0;
        for (int value : values) dataSum += value;
        long reference = expected(values);

        System.out.println("ROWS=" + ROWS);
        System.out.println("SEED=" + SEED);
        System.out.println("WARMUP=" + WARMUP);
        System.out.println("MEASURE=" + MEASURE);
        System.out.println("DATA_SUM=" + dataSum);
        System.out.println("ROUND_CHECKSUM=" + reference);

        for (int i = 0; i < WARMUP; i++) {
            if (round(values) != reference) {
                throw new AssertionError("warmup data changed");
            }
        }

        System.out.println("iteration,elapsed_ms,checksum");
        for (int i = 1; i <= MEASURE; i++) {
            long start = System.nanoTime();
            long got = round(values);
            long elapsed = System.nanoTime() - start;
            if (got != reference) throw new AssertionError("measurement data changed");
            blackhole ^= got;
            System.out.printf(Locale.ROOT, "%d,%.3f,%d%n",
                    i, elapsed / 1_000_000.0, got);
        }
        System.out.println("CHECKSUM_CHECK=PASS");
    }
}
~~~

### Chương trình cố định những gì?

- `SEED=20261108`, `ROWS=16384`, `WARMUP=3` và `MEASURE=5` là các hằng cố định cho mọi run.
- `SplittableRandom` tạo đúng dãy 16.384 giá trị từ 0 đến 255 trên môi trường kiểm thử.
- Mỗi bản ghi tạo một mảng `8192 + value` byte, ghi bytes ở hai đầu, rồi giữ tối đa `256` mảng mới nhất trong `Deque`.
- `expected(values)` tính kết quả tham chiếu mà không phụ thuộc GC; `round(values)` tính lại từ dữ liệu thật của mảng đã cấp phát. Nếu checksum lệch, chương trình dừng bằng `AssertionError`.
- `blackhole` là biến `volatile` giúp có một kết quả quan sát được, nhưng không biến vòng đo đơn giản này thành JMH.
- `System.nanoTime()` đo thời gian của **toàn bộ một round cấp phát**, có thể bao gồm GC stalls, GC pauses, scheduling và phần code khác; **nó không trực tiếp đo GC pause p99**.
- Vì các round chạy trong một JVM process, GC state/heap occupancy có thể khác giữa round trước và sau; không được coi năm round là năm mẫu độc lập như năm process forks.

### Những dòng stdout ổn định đã được xác minh

Đã biên dịch với `javac --release 17` và chạy trên **JDK 24** bằng cả G1 và ZGC. Phần đầu stdout của **cả hai**:

~~~text
ROWS=16384
SEED=20261108
WARMUP=3
MEASURE=5
DATA_SUM=2080952
ROUND_CHECKSUM=140465440
iteration,elapsed_ms,checksum
~~~

Sau dòng tiêu đề, chương trình in **năm dòng** theo định dạng `iteration,elapsed_ms,checksum`. Thời gian ở giữa khác nhau giữa các lần chạy; **mỗi dòng có checksum `140465440`**. Dòng cuối:

~~~text
CHECKSUM_CHECK=PASS
~~~

Ví dụ hai kết quả thực từ cùng một máy JDK 24 ở một lượt thử:

| Run | Năm giá trị elapsed_ms theo iteration | Kết luận hợp lệ |
| --- | --- | --- |
| G1, một process | 11,696; 13,196; 13,874; 12,623; 11,032 | Fixture hợp lệ, thời lượng round theo môi trường thử. |
| ZGC, một process | 9,633; 78,869; 16,035; 14,991; 13,126 | Fixture hợp lệ, có một outlier lớn. **Chưa thể khẳng định ZGC kém hay tốt hơn G1**. |

Số liệu chỉ là **mẫu từ một lượt chạy cục bộ**, không phải benchmark đủ số mẫu; kết quả thay đổi khi tải nền, GC cycles, OS scheduler và CPU khác nhau. Chính sự xuất hiện của một outlier là ví dụ về lý do **không chọn collector theo một lần chạy**.

## 8. Lệnh chạy hai collector cùng điều kiện

Tại thư mục chứa `GcFairCompare.java`:

~~~bash
javac --release 17 -encoding UTF-8 GcFairCompare.java
~~~

**Run G1** — chọn heap, CPU ergonomics và GC logging:

~~~bash
java -Xms128m -Xmx128m -XX:ActiveProcessorCount=2 -XX:+UseG1GC -Xlog:gc*,safepoint:file=g1-run1.log:time,uptime,level,tags:filecount=0 GcFairCompare
~~~

**Run ZGC** — chỉ đổi collector và tên file log:

~~~bash
java -Xms128m -Xmx128m -XX:ActiveProcessorCount=2 -XX:+UseZGC -Xlog:gc*,safepoint:file=zgc-run1.log:time,uptime,level,tags:filecount=0 GcFairCompare
~~~

Hai lệnh này đã được kiểm chứng với **JDK 24** và compiler `--release 17`. Dùng tên file riêng cho từng collector để không trộn log. `filecount=0` chỉ phù hợp bài thử **ngắn** muốn lưu một file; trong production hoặc benchmark lâu dài phải có chính sách rotation/disk budget thích hợp.

**Lưu ý về CPU:** `ActiveProcessorCount=2` kiểm soát cách JVM tính số CPU cho một số heuristics; nó **không giới hạn CPU quota/cpuset ở OS**. Trong container Linux, muốn giữ cùng quota phải cấu hình cgroups/Docker/Kubernetes tương ứng rồi kiểm chứng. Việc chạy ở máy Windows cục bộ trong bài **không kiểm chứng cgroup hoặc production-container fairness**.

**Lưu ý về output:** khi phân tích thời gian trong từng process, đo ở cả hai phiên bản JDK cùng cấu hình. Nhưng để kết luận collector hơn kém, cần chạy **nhiều JVM processes** theo thứ tự cân bằng/randomized, không chỉ hai lệnh một lần. Khuyến khích thu log metadata và phiên bản kèm từng result.

### Cách lưu kết quả để đối chiếu

Trong shell có hỗ trợ redirect stdout, có thể ghi riêng measurement output:

~~~bash
java -Xms128m -Xmx128m -XX:ActiveProcessorCount=2 -XX:+UseG1GC -Xlog:gc*,safepoint:file=g1-run2.log:time,uptime,level,tags:filecount=0 GcFairCompare > g1-run2.txt
~~~

Đừng dùng chung một tên file khi chạy song song; tránh dữ liệu của hai run bị ghi đè. Tên file log nên chứa **GC, JDK build, run ID, thời gian và định danh workload** ở hệ thống benchmark hoàn chỉnh.

## 9. Đo đúng các metric để không “thắng giả”

So GC không chỉ so `elapsed_ms` của vòng Java. Thu và so các thước đo sau:

| Metric | Công cụ | Tại sao phải có? |
| --- | --- | --- |
| **Application throughput** (ops/s, req/s) | Load generator/JMH hoặc số round trên thời gian | Collector pause thấp nhưng throughput có thể kém do CPU overhead. |
| **Request latency p50/p95/p99/p99.9** | Histogram ứng dụng, tracing hoặc load test | Đây mới là kết quả người dùng quan sát, không suy ra từ GC log. |
| **GC STW pause events**: count, max, p99, sum | `-Xlog:gc*`, JFR GC pause events | Đánh giá collector có đáp ứng mục tiêu pause trong cửa sổ thử hay không. |
| **Allocation stalls / GC pressure** | ZGC logs/JFR, allocation/heap telemetry | Concurrent GC có thể pause ngắn nhưng thread phải chờ cấp phát. |
| **GC CPU / concurrent cycles** | CPU profiler, GC logs/JFR, runtime metrics | GC cạnh tranh CPU với request và làm đổi throughput. |
| **Heap used/committed/max, live set** | JMX/GC logs/JFR | Hai run có cùng heap max nhưng trạng thái sống thực tế khác nhau. |
| **Memory total / RSS / native memory** | OS/container metrics, NMT khi cần | Cùng `-Xmx` không bảo đảm cùng memory footprint. |
| **CPU quota/throttling** | cgroup `cpu.stat`, container monitoring | CPU bị throttle dễ làm request p99 khác biệt lớn. |
| **Lỗi/OOM/crashes** | Logs, exit status, OOMKilled, error rate | Một run nhanh nhưng OOM hoặc mất request không phải kết quả tốt. |
| **JIT/code cache và safepoint** | JFR, `-Xlog:safepoint` và tooling phù hợp | Lý giải outlier không chỉ do GC. |

**Không gộp duration của toàn bộ concurrent GC cycle thành STW pause.** Với ZGC, cần phân biệt pha `Pause` và `Allocation Stall`. Với G1, parse các pause events/GC causes tương ứng theo format của bản JVM đang chạy. **Hai collector có log format và event taxonomy khác nhau**; công cụ so sánh phải dùng định nghĩa chung cho tiêu chí chứ không giả định một regex giống nhau áp dụng chính xác cho cả hai.

### JFR và JMH

**Java Flight Recorder (JFR)** giúp quan sát nhiều sự kiện JVM theo cấu trúc và ghép với timeline ứng dụng. Thêm recording cho các lượt chạy nếu mục tiêu cần so GC pauses, allocation stalls, CPU, monitor contention hoặc safepoints, nhưng phải giữ **mức recording và overhead tương đương** ở hai collector.

**JMH** được khuyến nghị khi so microbenchmarks JVM. Nó hỗ trợ warmup, measurement, forks, nhiều mode và benchmark states; vẫn phải thiết kế workload để tránh dead-code elimination, constant folding, đo cả setup hoặc đo không đại diện. JMH **không tự làm benchmark đáng tin** nếu dataset, machine và ứng dụng không được kiểm soát.

## 10. Phân tích thống kê: lặp lại, gắn cặp và không bỏ outlier tùy tiện

### 10.1. Ba lớp mẫu khác nhau

- **Một lần operation/request**: đơn vị tính latency request.
- **Một measurement round bên trong JVM**: ví dụ năm giá trị `elapsed_ms` từ `GcFairCompare`; chúng **có thể tương quan** vì cùng process, cùng heap/JIT state.
- **Một process fork / benchmark run độc lập**: mẫu giúp đo biến thiên giữa các JVM startups, lịch GC và môi trường.

Đừng tính confidence interval như thể 5.000 request trong cùng một process độc lập hoàn toàn với năm JVM forks. Có thể cần phân tích phân cấp hoặc bootstrap theo block/process để tránh đánh giá thấp độ bất định.

### 10.2. Phân phối và cách trình bày

Với mỗi GC, báo:

1. Số process forks, warmup duration, measurement duration, số operations/requests và các run bị loại (lý do).
2. Median, p95/p99 của **latency app** với số mẫu đủ lớn; thông số throughput và tỷ lệ lỗi.
3. GC pause-event count/max/p99 theo đúng định nghĩa, allocation-stall events và GC CPU.
4. CPU/RSS/container metrics, dấu hiệu throttling/OOM, độ ổn định của host.
5. Khoảng tin cậy hoặc độ biến thiên **giữa các run**; không chỉ một giá trị “nhanh nhất”.

**Không tự xóa outlier vì nó bất lợi cho collector.** Outlier phải được xem cùng log, CPU throttling, mức tải, GC events và nguyên nhân. Nếu run thật sự sai fixture (checksum khác, OOM, mất request, thiết bị đang lỗi), ghi rõ và loại theo **quy tắc thiết lập trước**, không chỉnh quy tắc sau khi nhìn kết quả.

Một khác biệt vài phần trăm trên dữ liệu rất nhiễu có thể chưa đủ căn cứ. Cần chạy nhiều lượt và thảo luận độ bất định; không có một số rounds cố định luôn đủ cho mọi workload.

## 11. Quy trình A/B thực dụng và có thể kiểm tra

### Bước 1: đóng băng artifact và workload

Ghi commit/image digest, dependencies, dataset version, seed, checksum, snapshot DB và kịch bản request mix. Nếu dữ liệu thay đổi từ lần G1 sang lần ZGC, kết quả so GC sẽ bị nhiễu. Với distributed services, kiểm soát cả downstream latency và state.

### Bước 2: đóng băng ngân sách phần cứng

Ghi host/CPU/NUMA/OS/kernel, CPU quota & cpuset, memory limit, thread counts và tài nguyên thực đang còn trống. Nếu chỉ có Kubernetes shared nodes, cần coi **noisy neighbors** là nguồn biến thiên và lấy đủ mẫu trên nhiều cặp run.

### Bước 3: đóng băng JDK/JVM

Đảm bảo cùng JDK build, cùng `-Xms`/`-Xmx`, cùng non-GC flags, mức logging/JFR và startup options. Với phép baseline, chỉ đổi collector; với phép tune nâng cao, ghi bảng flags theo GC và tách khỏi baseline.

### Bước 4: thực hiện thử nghiệm có thứ tự cân bằng

Một chuỗi A/B minh họa là **G1 → ZGC → ZGC → G1** trong cùng block điều kiện; ở block khác dùng thứ tự khác hoặc randomized. Tất cả lượt phải làm warmup và đo steady-state theo cùng protocol. Dừng và khởi động JVM mới cho các process forks cần so.

### Bước 5: kiểm chứng đầu vào/output

Đối chiếu `DATA_SUM` và `ROUND_CHECKSUM` của chương trình mẫu, số request đã phục vụ, error rate, kết quả nghiệp vụ và version. Nếu dữ liệu không khớp, **không dùng thời gian của lượt đó để chấm GC**.

### Bước 6: phân tích latency/throughput + GC + host

Ghép timeline GC pauses, allocation stalls, safepoints và CPU throttling với request p99. Ví dụ một run có throughput cao nhưng tăng OOMKilled không đạt mục tiêu availability. Một run có GC pause dưới 1ms nhưng CPU throttling kéo p99 request lên cũng không đạt SLO.

### Bước 7: ra quyết định có điều kiện

Kết luận nên ghi dạng: **“Trên JDK/build, phần cứng, CPU/RAM budget, dữ liệu và tải X, collector Y có phân bố latency/throughput như số liệu đính kèm, với các giới hạn đo lường đã nêu.”** Không khái quát “collector Y luôn nhanh hơn” cho mọi ứng dụng.

## 12. Các lỗi thường gặp khi thiết kế phép so sánh

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Chạy G1 với 10.000 requests, ZGC với 20.000 requests | Thay đổi workload cùng collector | Dùng đúng cùng dữ liệu, số request, mix và concurrency/rate. |
| G1 dùng `-Xmx128m`, ZGC dùng `-Xmx512m` nhưng gọi là so GC thuần | Thay cả heap headroom | Baseline cố định heap; phép tune memory là thí nghiệm riêng. |
| Chạy G1 trên máy phát triển, ZGC trên server lớn | Hardware/JDK/OS khác | Dùng cùng host hoặc thiết kế thử nghiệm bắt cặp và ghi nhiễu. |
| Chỉ đặt `ActiveProcessorCount` rồi nghĩ đã áp CPU quota | Cờ JVM không ép quota OS | Kiểm tra cgroups/CPU quota/cpuset và throttling thực. |
| Chạy một lần rồi lấy số nhỏ nhất | Scheduling/GC/JIT có nhiễu | Warmup, nhiều forks, cân bằng thứ tự, báo phân phối. |
| Thấy p99 GC pause nhỏ nên nói request p99 đạt | Hai phân phối khác nhau | Đo request end-to-end riêng. |
| Chỉ so duration của mọi dòng GC log | Có STW, concurrent cycle và thống kê lồng nhau | Phân loại events theo đúng collector/build. |
| Gọi `System.gc()` giữa các phép đo để “làm sạch” | Can thiệp nhân tạo vào GC và khác thực tế | Tạo JVM process mới cho fork, định nghĩa warmup/cold-vs-warm hợp lý. |
| Vừa benchmark vừa chạy backup/CI build | CPU/IO/memory contention | Cô lập host hoặc ghi nhận/tách block nhiễu. |
| Bỏ những lần có allocation stall vì “ngoại lệ” | Có thể chính là vấn đề cần đo | Điều tra và công bố, không loại sau khi thấy bất lợi. |
| Ghi log debug cho một GC nhưng không ghi GC kia | Khác overhead quan sát | Dùng policy log/JFR tương đương. |
| So ZGC trên JDK 15 với G1 trên JDK 27 rồi đổ chênh lệch cho GC | JDK và collector cùng thay đổi | Chạy hai GC trên cùng JDK cho so GC; thử version như biến độc lập. |
| Cùng dataset sum là đủ chứng minh dữ liệu giống tuyệt đối | Checksum cộng có thể va chạm | Với benchmark quan trọng, lưu fixture bytes và hash mạnh. |
| Dùng microbenchmark cấp phát để đại diện mọi dịch vụ | Không có DB/network/traffic mix thật | Đo lại trên whole-application workload của sản phẩm. |

## 13. Checklist trước khi công bố benchmark GC

1. Có **giả thuyết** và **duy nhất một biến chủ động** trong phép so sánh baseline.
2. Có **artifact/JDK build/OS** được ghi lại và dùng đồng nhất.
3. Có dataset version, seed, **fixture fingerprint**, số bản ghi và phân bố.
4. Có số request, concurrency, target rate, arrival pattern và thời lượng được cố định.
5. Có mô tả object lifetime/live set, allocation rate và bộ nhớ giữ lại.
6. Có host/CPU/RAM/NUMA, CPU quota/cpuset và memory limits được ghi nhận.
7. Có `-Xms`, `-Xmx` và các JVM flags được công bố; GC collector là biến cần so.
8. Có warmup tách riêng, nhiều process forks và thứ tự A/B cân bằng.
9. Có quan sát GC log/JFR và app-level p95/p99, throughput, error rate.
10. Có thông tin CPU throttling, RSS/native memory, OOM và các sự cố môi trường.
11. Có quy tắc kiểm tra checksum, loại run lỗi và xử lý outlier được định nghĩa trước.
12. Có phân bố, số mẫu, độ bất định và kết luận **giới hạn trong môi trường đã thử**.
13. Đã kiểm tra flags của JDK hiện tại; không dùng cấu hình ZGC non-generational đã bị loại bỏ từ JDK 24.
14. Nếu dùng JMH, có forks/warmups/measurements và kiểm soát tránh các tối ưu làm mất workload; nếu dùng custom harness, ghi rõ hạn chế.

## 14. Tài liệu chuẩn còn áp dụng

- [Java SE 27 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/27/gctuning/): mục tiêu GC, throughput, latency và các collector hiện hành.
- [Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `-Xms`, `-Xmx`, `-XX:+UseG1GC`, `-XX:+UseZGC`, `ActiveProcessorCount`, `-Xlog` và GC ergonomics.
- [Java SE 24 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html): hoạt động concurrent, headroom, low pause, generational ZGC.
- [JEP 377 — ZGC Production](https://openjdk.org/jeps/377): ZGC trở thành production trong Java 15.
- [JEP 490 — Remove the Non-Generational Mode of ZGC](https://openjdk.org/jeps/490): từ JDK 24 chỉ còn generational ZGC.
- [OpenJDK — JMH Java Microbenchmark Harness](https://github.com/openjdk/jmh): công cụ hiện hành để thiết kế microbenchmark JVM có warmup/measurement/forks.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): requests, limits, CPU throttling và memory enforcement.
- [Linux kernel — Control Group v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html): CPU quota, `cpu.stat` và memory accounting.

**Kết luận:** kết quả đo GC chỉ có ý nghĩa khi **dữ liệu, phần cứng, JDK, heap, CPU/memory budget, load profile và phương pháp đo** được cố định hoặc được công bố rõ. Hãy dùng fixture có checksum để xác minh workload, so **nhiều JVM runs** theo thứ tự cân bằng, và xem **application latency/throughput, GC pauses, allocation stalls, RSS và CPU throttling** cùng nhau. Một lần chạy G1 nhanh hơn ZGC — hoặc ngược lại — chưa phải bằng chứng để chọn collector cho production.