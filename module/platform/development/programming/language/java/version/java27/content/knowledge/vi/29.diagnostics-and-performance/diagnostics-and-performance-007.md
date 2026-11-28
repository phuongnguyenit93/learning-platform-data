# Tối ưu CPU, allocation và I/O dựa trên dữ liệu đo

Một ứng dụng Java 27 có thể phản hồi chậm vì **CPU bão hòa**, **tạo quá nhiều đối tượng tạm (allocation)**, **chờ I/O** hoặc một tổ hợp của ba nguyên nhân đó. Nếu chưa đo, những thay đổi như tăng số thread, đổi garbage collector, chuyển mọi lời gọi sang bất đồng bộ hay thêm cache có thể không giải quyết được vấn đề và đôi khi làm ứng dụng tệ hơn.

Nguyên tắc của bài học **Tối ưu CPU, allocation và I/O dựa trên dữ liệu đo**, thuộc chương **Chẩn đoán và hiệu năng** trong mô-đun Java 27, là:

> **Định nghĩa vấn đề → ghi baseline → đo đúng loại tài nguyên → hình thành giả thuyết → thay đổi có kiểm soát → đo lại → giữ hoặc hoàn tác.**

Bài sử dụng những công cụ còn phù hợp trong Java 27: **Java Flight Recorder (JFR)**, **JDK Mission Control (JMC)**, **jcmd**, **jfr**, **Unified JVM Logging**, **ThreadMXBean**, **System.nanoTime()** và **Native Memory Tracking (NMT)**. Với benchmark mức method, bài giải thích **JMH** của OpenJDK; đây là công cụ bổ sung, **không phải một package có sẵn trong JDK**.

## 1. Hiệu năng là một bài toán có mục tiêu đo được

Tối ưu hiệu năng không phải làm cho một vòng lặp trông ngắn hơn. Nó là cải thiện **một hoặc nhiều chỉ số có ý nghĩa** trong những điều kiện xác định, trong khi vẫn giữ đúng chức năng.

Các chỉ số thường dùng:

| Chỉ số | Câu hỏi trả lời | Điểm cần chú ý |
|---|---|---|
| **Throughput** | Hoàn thành bao nhiêu request hoặc job mỗi giây? | Tải quá cao có thể khiến độ trễ tăng mạnh |
| **Latency** | Một request mất bao lâu từ đầu đến cuối? | Cần xem phân vị thay vì chỉ trung bình |
| **p50 / p95 / p99** | 50%, 95%, 99% request có latency không vượt mốc nào? | Phản ánh phần đuôi phân bố, dễ lộ nghẽn hàng đợi |
| **CPU utilization** | CPU đang bận tới mức nào so với quota có thể dùng? | 100% một core khác với 100% cả máy |
| **CPU time** | Một đoạn code thực sự tiêu thụ bao nhiêu thời gian CPU? | Khác **wall-clock time** |
| **Allocation rate** | Tạo bao nhiêu byte đối tượng mới mỗi giây / mỗi request? | Cao chưa chắc là leak |
| **Live heap / retained size** | Bao nhiêu bộ nhớ còn phải giữ lại sau GC? | Khác tổng byte từng được cấp phát |
| **GC pause / GC overhead** | GC ảnh hưởng latency và CPU thế nào? | Không chỉ nhìn số lần GC |
| **I/O latency** | Mạng, DB, file mất bao lâu để hoàn tất? | Bao gồm chờ kết nối, hàng đợi, transfer |
| **Error / timeout rate** | Có bao nhiêu thao tác thất bại hoặc phải thử lại? | Một tối ưu nhanh hơn nhưng lỗi nhiều hơn có thể không đạt |

### 1.1. Chọn tiêu chí thành công trước khi sửa

Ví dụ một API xử lý đơn hàng có:

~~~text
Throughput:       200 request/s
p50 latency:       80 ms
p95 latency:      650 ms
p99 latency:     1500 ms
Error rate:       0.3%
CPU utilization:  45% quota
~~~

Các số trên là **ví dụ giả định**, không phải một kết quả đo trong dự án.

Một mục tiêu tốt có thể là:

~~~text
Ở mức tải 200 request/s:
- p95 giảm dưới 350 ms
- p99 giảm dưới 800 ms
- error rate không tăng
- CPU và bộ nhớ không vượt ngân sách
~~~

Nếu tối ưu chỉ làm p50 giảm 10 ms nhưng p99 tăng gấp đôi, thay đổi đó có thể **không đạt mục tiêu người dùng**.

### 1.2. Không tối ưu theo một con số duy nhất

Giảm allocation có thể đổi lấy CPU cao hơn. Tăng buffer giúp giảm số lần đọc nhưng tăng bộ nhớ trên mỗi kết nối. Thêm cache có thể giảm I/O nhưng giữ nhiều object trong heap hơn.

Mỗi thay đổi có **trade-off**, cần theo dõi các chỉ số liên quan.

## 2. Nhận diện CPU-bound, allocation-heavy và I/O-bound

Ba nhóm này không hoàn toàn tách biệt. Một request có thể chờ network, tạo nhiều object khi parse JSON, rồi sử dụng CPU để tính toán.

| Dạng nút thắt | Dấu hiệu gợi ý | Nên đo trước |
|---|---|---|
| **CPU-bound** | CPU gần quota, profiler có hot methods, tăng concurrency không tăng throughput | CPU profiles, CPU time, hotspot và contention |
| **Allocation-heavy** | Allocation rate cao, GC hoạt động nhiều, nhiều object sống rất ngắn | JFR allocation, GC logs, bytes/request |
| **I/O-bound** | CPU còn rảnh nhưng request chờ socket, database hoặc filesystem | End-to-end spans, SocketRead/Write, file events, connection pool |
| **Lock contention** | Threads chờ lock, CPU có thể thấp hoặc cao tùy trường hợp | JFR monitor/park events, thread dump |
| **Memory retention** | Heap sau GC vẫn tăng theo thời gian | Live set, heap dump, retaining paths |
| **Native memory** | RSS tăng nhưng heap tương đối ổn định | NMT, OS metrics, direct/native allocation |
| **Tác vụ hỗn hợp** | Các chỉ số thay đổi theo giai đoạn | Tách span/timer theo từng stage |

**CPU sử dụng thấp không chứng minh ứng dụng còn nhiều năng lực để phục vụ thêm yêu cầu.** Có thể connection pool đã đầy, database chậm hoặc mọi request đang đứng ở một lock.

**CPU sử dụng cao cũng không chứng minh chỉ cần tăng CPU**: có thể phần lớn thời gian CPU bị tiêu bởi GC, mã hóa dữ liệu lặp hoặc retry storm.

## 3. Phân biệt wall time với CPU time

**Wall time** là thời gian thực trôi qua từ đầu đến cuối một hoạt động.

**CPU time** là tổng thời gian thread thực sự được CPU thực thi trong khoảng đó theo cách đo của JVM/OS.

Ví dụ giả định:

| Công việc | Wall time | CPU time | Đọc kết quả |
|---|---:|---:|---|
| Tính toán số nguyên tố | 300 ms | 280 ms | Chủ yếu chạy CPU |
| Chờ một HTTP response | 300 ms | 8 ms | Chủ yếu chờ |
| Parse response JSON lớn | 300 ms | 230 ms | Có thể chủ yếu CPU |
| Chờ lấy connection từ pool | 300 ms | 2 ms | Nghẽn tài nguyên, không phải CPU |

**Wall time không phải tổng CPU time đơn thuần.** Trong chương trình có nhiều thread song song, tổng CPU time của các thread có thể lớn hơn wall time của một request.

### 3.1. Đo thời lượng bằng System.nanoTime()

~~~java
long started = System.nanoTime();

doWork();

long elapsedNanos = System.nanoTime() - started;
double elapsedMillis = elapsedNanos / 1_000_000.0;

System.out.printf("Elapsed: %.3f ms%n", elapsedMillis);
~~~

**doWork()** là hàm giả định của ứng dụng. **System.nanoTime()** thích hợp để đo **hiệu thời gian** trong cùng một tiến trình, không phải timestamp trên lịch.

Không dùng **Instant.now()**, **LocalDateTime.now()** hay **System.currentTimeMillis()** để làm công cụ đo benchmark chính xác: thời gian trên đồng hồ hệ thống có thể được điều chỉnh.

### 3.2. ThreadMXBean và các giới hạn

**java.lang.management.ThreadMXBean** có thể cung cấp CPU time cho thread khi JVM hỗ trợ và chức năng này được bật.

Ví dụ đầy đủ **CpuVsWaitDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

public class CpuVsWaitDemo {

    @FunctionalInterface
    interface Task {
        void run() throws Exception;
    }

    private static volatile long result;

    static long countPrimes(int max) {
        long count = 0;

        for (int n = 2; n <= max; n++) {
            boolean prime = true;

            for (int d = 2; d <= n / d; d++) {
                if (n % d == 0) {
                    prime = false;
                    break;
                }
            }

            if (prime) {
                count++;
            }
        }

        return count;
    }

    static void measure(String label, Task task) throws Exception {
        ThreadMXBean bean =
            ManagementFactory.getThreadMXBean();

        boolean canReadCpu =
            bean.isCurrentThreadCpuTimeSupported()
                && bean.isThreadCpuTimeEnabled();

        long wallBefore = System.nanoTime();

        long cpuBefore = canReadCpu
            ? bean.getCurrentThreadCpuTime()
            : -1L;

        task.run();

        long cpuAfter = canReadCpu
            ? bean.getCurrentThreadCpuTime()
            : -1L;

        long wallAfter = System.nanoTime();

        double wallMs =
            (wallAfter - wallBefore) / 1_000_000.0;

        System.out.printf("%s: wall=%.3f ms", label, wallMs);

        if (cpuBefore >= 0 && cpuAfter >= 0) {
            double cpuMs =
                (cpuAfter - cpuBefore) / 1_000_000.0;

            System.out.printf(", cpu=%.3f ms", cpuMs);
        } else {
            System.out.print(", cpu=n/a");
        }

        System.out.println();
    }

    public static void main(String[] args) throws Exception {
        measure("CPU", () -> {
            result = countPrimes(150_000);
        });

        measure("WAIT (mô phỏng)", () -> {
            Thread.sleep(300);
        });

        System.out.println("Primes: " + result);
    }
}
~~~

Chạy:

~~~bash
javac CpuVsWaitDemo.java
java CpuVsWaitDemo
~~~

**WAIT** dùng **Thread.sleep(300)** chỉ để mô phỏng chờ, **không phải benchmark I/O thật**. ThreadMXBean có thể không hỗ trợ CPU time trên một môi trường, có thể trả **-1**, và khả năng đo CPU time của virtual threads khác platform threads. Ví dụ cố ý đo trên **platform main thread**, không khẳng định đây là số đo chính xác cho mọi virtual thread.

Chạy chương trình một lần chỉ minh họa cách đo, chưa đủ để kết luận performance. JIT warmup, scheduling và tải nền có thể làm kết quả thay đổi.

## 4. Quy trình tối ưu dựa trên bằng chứng

~~~mermaid
flowchart TD
    A["Xác định mục tiêu và workload"]
    B["Ghi baseline: throughput, latency, errors, CPU, memory"]
    C["Khoanh vùng CPU / allocation / I-O / contention"]
    D["Profiler và traces: tìm đoạn nóng"]
    E["Giả thuyết thay đổi có thể kiểm chứng"]
    F["Chỉ thay đổi một yếu tố chính"]
    G["Chạy lại cùng workload"]
    H{"Đạt mục tiêu và không gây regression?"}
    I["Giữ thay đổi, ghi nhận evidence"]
    J["Hoàn tác hoặc đặt giả thuyết mới"]
    A --> B --> C --> D --> E --> F --> G --> H
    H -->|Có| I
    H -->|Không| J --> C
~~~

### 4.1. Một baseline tốt cần những gì?

- **JDK**: phiên bản, bản build, vendor, JVM flags, collector.
- **Máy chạy**: số CPU khả dụng, container CPU quota, giới hạn RAM.
- **Ứng dụng**: commit/build, cấu hình connection pool, cache, logging.
- **Workload**: endpoint, request mix, payload size, số người dùng đồng thời.
- **Thời gian đo**: warmup, steady-state, tổng thời lượng, thời gian lấy sample.
- **Dependencies**: database, cache ngoài, network, rate limit, thời gian phản hồi.
- **Kết quả**: p50/p95/p99, throughput, error, CPU, allocation, GC, I/O.
- **Sự kiện bất thường**: deploy, autoscaling, GC, lỗi mạng, tải của hệ thống khác.

Nếu dùng một endpoint với payload 1 KB để đo baseline và payload 2 MB để đo sau tối ưu, phép so sánh không có ý nghĩa.

### 4.2. Đo ở mức người dùng và ở mức JVM

**Black-box metrics**: người dùng chờ bao lâu, có bao nhiêu request thành công, p99 thế nào.

**White-box diagnostics**: CPU samples, allocations, GC pause, socket waits, locks, thread states.

Hai lớp thông tin bổ sung nhau. Profile cho thấy một method nóng chưa nói được method đó có phải nguyên nhân của p99 latency hay không; cần đối chiếu với đường đi request.

## 5. Công cụ chẩn đoán hiện hành trong Java 27

| Công cụ | Mục tiêu | Ghi chú |
|---|---|---|
| **Java Flight Recorder (JFR)** | Ghi sự kiện JVM và ứng dụng: CPU samples, allocation, GC, I/O, locks | API trong module **jdk.jfr**; cấu hình ảnh hưởng overhead |
| **JDK Mission Control (JMC)** | Xem và phân tích recording JFR | Công cụ/ứng dụng riêng, không đồng nghĩa JDK luôn cài sẵn JMC |
| **jcmd** | Ra lệnh chẩn đoán tới JVM đang chạy | Có command **JFR.start**, **JFR.dump**, **Thread.print**, **GC.heap_info** |
| **jfr** | Xem thống kê và nội dung tệp **.jfr** | Ví dụ **summary**, **print** |
| **Unified Logging** | Đọc GC, safepoint, class loading và các sự kiện JVM | Tham số **-Xlog** |
| **ThreadMXBean** | CPU time / thread diagnostics khi JVM hỗ trợ | Không phải profiler toàn diện |
| **JMH** | Benchmark micro-level có warmup và thống kê hợp lý | OpenJDK project ngoài API chuẩn của JDK |
| **Native Memory Tracking** | Theo dõi phân bổ bộ nhớ native trong HotSpot | Cần bật từ lúc JVM khởi động; có overhead |
| **APM / tracing / metrics** | Đo end-to-end latency và call tới dependency | Cần hiểu phương pháp lấy mẫu và chi phí instrumentation |
| **OS/container metrics** | CPU quota/throttling, RSS, network, disk | Giúp phân biệt nghẽn JVM với nghẽn môi trường |

### 5.1. JFR không phải “công cụ thương mại cần mở khóa”

Các hướng dẫn rất cũ về **VM.unlock_commercial_features** hoặc bắt buộc bật **-XX:+FlightRecorder** không phù hợp để hướng dẫn cho Java 27. Trên JDK hiện hành, JFR sẵn có; hãy dùng **-XX:StartFlightRecording** hoặc lệnh **jcmd JFR.start**.

### 5.2. Không tự đoán event nào đã được ghi

JFR có các cấu hình **default.jfc** và **profile.jfc**:

- **default.jfc** nhằm quan sát với chi phí thấp, phù hợp thời gian dài hơn.
- **profile.jfc** ghi nhiều sự kiện hơn để phân tích hiệu năng trong cửa sổ có giới hạn.

Một event có thể bị tắt hoặc có threshold/sampling settings làm một số lần xảy ra không xuất hiện. **Không thấy event trong recording không chứng minh event chưa từng xảy ra**.

## 6. Ghi JFR khi khởi động Java

Ví dụ ứng dụng có main class **MyApplication**:

~~~bash
java -XX:StartFlightRecording=filename=app.jfr,settings=profile,dumponexit=true MyApplication
~~~

Với chương trình chạy dài, nên giới hạn cửa sổ ghi hoặc theo chính sách lưu trữ:

~~~bash
java -XX:StartFlightRecording=filename=app.jfr,settings=profile,duration=60s MyApplication
~~~

Đây là lệnh **minh họa** cho người vận hành, không phải lệnh đã chạy khi viết tài liệu.

Mở tệp JFR bằng JDK Mission Control hoặc dùng CLI:

~~~bash
jfr summary app.jfr
~~~

~~~bash
jfr print --events jdk.SocketRead,jdk.SocketWrite app.jfr
~~~

Lệnh **jfr print** chỉ in các sự kiện đã tồn tại trong file. Tên event và trạng thái enable/threshold có thể được xem trong cấu hình và metadata của recording. Không nên in hàng triệu events ra terminal production; hãy lọc và phân tích theo một cửa sổ thời gian phù hợp.

### 6.1. Ghi JFR vào JVM đang chạy

Xác định PID Java được phép chẩn đoán, sau đó:

~~~bash
jcmd <pid> JFR.start name=perf-check settings=profile duration=60s filename=perf-check.jfr
~~~

Kiểm tra recording:

~~~bash
jcmd <pid> JFR.check
~~~

Khi muốn trích xuất một recording đang chạy:

~~~bash
jcmd <pid> JFR.dump name=perf-check filename=perf-snapshot.jfr
~~~

**JFR.dump** tạo bản ghi ra file, **không được hiểu là luôn dừng recording**. Dùng **JFR.stop** nếu cần dừng một recording đang chạy:

~~~bash
jcmd <pid> JFR.stop name=perf-check
~~~

Thay **<pid>** bằng PID hợp lệ, và kiểm tra nơi file được ghi; quyền ghi, không gian đĩa, mount/container và việc JVM có cho phép attach đều ảnh hưởng kết quả.

### 6.2. Một cửa sổ đo phải đại diện

Không chọn 60 giây ngẫu nhiên khi traffic đang giảm xuống gần 0. Nên thu vào lúc phát sinh vấn đề, hoặc tái hiện workload với **cùng request mix và mức tải** như baseline.

Với sự cố chỉ xảy ra 2 phút sau khi warmup, một recording trước thời điểm đó có thể bỏ lỡ nguyên nhân.

## 7. Đọc JFR: CPU samples, allocation, I/O và locks

### 7.1. CPU samples

Trong JFR/JMC, xem những **execution samples**, call tree và các stack traces chiếm tỉ trọng lớn.

Các câu hỏi:

1. Method/package nào xuất hiện nhiều trong samples?
2. CPU đang nằm ở business code, JSON parser, compression, crypto, GC hay code framework?
3. Hot method có thực sự nằm trên critical path của request chậm không?
4. Thời gian CPU có tăng theo kích thước dữ liệu hoặc số request không?
5. Có CPU throttling hoặc tranh chấp lõi trên host/container không?

**Sampling không phải phép đếm từng instruction.** Tần suất sample, JIT inlining, stack unwinding và profile duration ảnh hưởng độ chính xác. Không diễn giải sự khác biệt 0,1% giữa hai stack như bằng chứng chắc chắn.

### 7.2. Allocation profiling

Một số sự kiện JFR liên quan allocation gồm **jdk.ObjectAllocationSample**, **jdk.ObjectAllocationInNewTLAB** và **jdk.ObjectAllocationOutsideTLAB**; việc loại nào được ghi phụ thuộc JDK và cấu hình recording.

Tập trung vào:

- Loại object nào được tạo nhiều?
- Stack trace nào tạo ra lượng byte lớn?
- Bao nhiêu byte mỗi request?
- Có tạo byte arrays hoặc String tạm trong vòng lặp nóng không?
- Allocation rate có tương quan với GC pauses hoặc CPU GC không?

Allocation samples **không phải bản liệt kê mọi object đã cấp phát**. Dùng chúng để nhận diện pattern và ưu tiên điều tra, không dùng số event như số byte tuyệt đối nếu chưa hiểu cách sampling.

### 7.3. I/O và contention

Các sự kiện như **jdk.SocketRead**, **jdk.SocketWrite**, **jdk.FileRead**, **jdk.FileWrite**, **jdk.JavaMonitorEnter** và **jdk.ThreadPark** có thể giúp khoanh vùng chờ.

Hãy xem **duration**, endpoint, thread, stack trace và số lần xuất hiện theo ngữ cảnh. Một lần **SocketRead** kéo dài có thể phản ánh thời gian chờ server, không đồng nghĩa CPU JVM đang chậm.

Đặc biệt, **JFR thread event không phải tất cả đều biểu diễn nguyên nhân chờ với độ chính xác tuyệt đối**; cần kết hợp trace ứng dụng, thời gian trong connection pool và metrics của hệ thống phụ trợ.

### 7.4. Flame graph và call tree

Flame graph dùng bề ngang để biểu diễn tỉ lệ samples trong một tập quan sát, **không phải timeline** và không mặc định là số mili giây thực của từng method.

Đối với một hot path:

- Mở từ request/service package xuống caller/callee.
- Tách code đang tiêu CPU khỏi code bị chặn bởi I/O.
- Tìm nguyên nhân ở tầng cao hơn: một method parse nóng có thể do bị gọi **20 lần không cần thiết**, không chỉ vì bản thân parser chậm.

## 8. CPU: ưu tiên thuật toán và khối lượng công việc

Trước khi tối ưu những phép toán nhỏ, hỏi:

- Có đang xử lý cùng dữ liệu lặp lại không?
- Có thuật toán độ phức tạp cao không?
- Có truy cập database thêm một lần cho mỗi phần tử (N+1) không?
- Có cần xử lý toàn bộ dữ liệu, hay có thể lọc từ nguồn?
- Có phải JSON serialization/logging đang tiêu tốn CPU không?

**Giảm số lần làm việc thường mang lợi ích lớn hơn việc thay đổi cú pháp Java.**

### 8.1. Ví dụ: tìm phần tử trong List so với Set

Nếu cần kiểm tra membership của nhiều khóa trong một danh sách lớn, sử dụng **List.contains** bên trong vòng lặp có thể tạo độ phức tạp xấp xỉ **O(n × m)**.

Chuẩn bị một **HashSet** trước khi kiểm tra nhiều query có chi phí xây dựng khoảng **O(n)**, sau đó trung bình thao tác membership gần **O(1)** nếu hash phân bố phù hợp.

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

List<Integer> allowed = new ArrayList<>();

for (int i = 0; i < 20_000; i++) {
    allowed.add(i);
}

List<Integer> queries = List.of(4, 100, 45_000);

// Đơn giản nhưng có thể phải duyệt list cho mỗi query.
long listHits = queries.stream()
    .filter(allowed::contains)
    .count();

// Xây một index set và sử dụng lại.
Set<Integer> lookup = new HashSet<>(allowed);

long setHits = queries.stream()
    .filter(lookup::contains)
    .count();

System.out.println(listHits == setHits);
~~~

**Không kết luận HashSet luôn nhanh hơn**: nếu danh sách cực nhỏ, số lần tra cứu ít hoặc chi phí hash/khởi tạo lớn hơn lợi ích, List có thể phù hợp hơn. Hãy đo với kích thước/đặc điểm dữ liệu thực tế.

### 8.2. Ví dụ độc lập có kiểm tra tính đúng

Tạo **MembershipComparisonDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class MembershipComparisonDemo {

    private static volatile long observed;

    static long countHits(
        List<Integer> queries,
        java.util.function.Predicate<Integer> contains
    ) {
        long hits = 0;

        for (Integer query : queries) {
            if (contains.test(query)) {
                hits++;
            }
        }

        return hits;
    }

    static long timed(
        String label,
        List<Integer> queries,
        java.util.function.Predicate<Integer> contains
    ) {
        long start = System.nanoTime();

        long hits = countHits(queries, contains);
        observed = hits;

        double elapsedMs =
            (System.nanoTime() - start) / 1_000_000.0;

        System.out.printf(
            "%s: hits=%d, %.3f ms%n",
            label, hits, elapsedMs
        );

        return hits;
    }

    public static void main(String[] args) {
        List<Integer> allowed = new ArrayList<>();
        List<Integer> queries = new ArrayList<>();

        for (int i = 0; i < 20_000; i++) {
            allowed.add(i);
        }

        for (int i = 0; i < 5_000; i++) {
            queries.add(i * 3);
        }

        for (int i = 0; i < 5_000; i++) {
            queries.add(i + 20_000);
        }

        Set<Integer> lookup = new HashSet<>(allowed);

        long slow = timed("List", queries, allowed::contains);
        long indexed = timed("HashSet", queries, lookup::contains);

        if (slow != indexed) {
            throw new AssertionError("Kết quả không tương đương");
        }

        System.out.println("Observed: " + observed);
    }
}
~~~

Chạy:

~~~bash
javac MembershipComparisonDemo.java
java MembershipComparisonDemo
~~~

Ví dụ này nhằm dạy **so sánh cùng đầu vào và giữ kết quả đúng**, **không phải benchmark đáng tin cậy**. Thứ tự chạy, warmup, dữ liệu và JIT có thể làm chênh lệch thời gian của một lần chạy.

**Chi phí xây dựng HashSet** trong ví dụ nằm ngoài khoảng đo membership; trong hệ thống thật, phải cộng cả chi phí đó nếu bạn xây set mới cho mỗi request.

### 8.3. Đừng nhầm nhiều thread với tối ưu CPU

Nếu CPU đã ở sát quota, tăng concurrency có thể tăng context switching, cache misses và p99 latency.

Với CPU-heavy independent tasks, giới hạn parallelism theo số core/quota và bằng chứng đo. **Virtual threads** có ích cho nhiều tác vụ chờ I/O; chúng **không làm một phép tính CPU đơn lẻ nhanh hơn**.

## 9. CPU profiling: method nóng chưa chắc là nguyên nhân gốc

Ví dụ profiler cho thấy:

~~~text
OrderController.handle
  └─ OrderService.create
       └─ PriceService.calculate
            └─ CurrencyConverter.convert    35% samples
~~~

Hai giả thuyết:

1. **CurrencyConverter.convert** có thuật toán chậm.
2. **PriceService.calculate** gọi convert **lặp lại 100 lần** dù chỉ cần một lần.

Tối ưu method convert mà không sửa số lần gọi có thể chỉ giảm nhỏ chi phí. Hãy bổ sung **operation count**, kích thước đầu vào và context của call path.

### 9.1. Khi nghi ngờ lock contention

Nếu JFR chỉ ra các sự kiện monitor enter/park dài:

- Xác định lock nào giữ lâu, ai sở hữu, vì sao thời gian trong critical section lớn.
- Tách I/O chậm ra khỏi critical section nếu hợp đồng cho phép.
- Giảm shared mutable state hoặc thời gian giữ lock.
- Không tự động thay synchronized bằng lock-free code phức tạp khi chưa có số liệu.

Trên Java 27, **JEP 491** đã thay đổi hiện tượng virtual-thread pinning do synchronized từ JDK 24; đừng tối ưu theo những giả định cũ về pinning mà không kiểm tra runtime hiện tại.

## 10. Allocation: tạo object nhiều không đồng nghĩa memory leak

**Allocation rate** là lượng object mới được cấp phát trong một đơn vị thời gian; **retained heap** là lượng bộ nhớ vẫn còn reachable.

| Trạng thái | Ý nghĩa |
|---|---|
| Allocation cao, live heap ổn định | Nhiều object ngắn hạn; có thể tăng tải cho GC |
| Allocation thấp, live heap tăng | Có thể dữ liệu bị giữ lại lâu; cần phân tích retention |
| Allocation cao, live heap tăng | Vừa cấp phát nhiều vừa giữ nhiều; cần xem từng nguồn |
| Heap thấp nhưng RSS tăng | Có thể là native/direct memory, thread stacks hoặc phần khác |

Một JVM có thể cấp phát nhiều đối tượng ngắn hạn rất hiệu quả. **Mục tiêu không phải đưa allocation về 0**, mà là giảm allocation không cần thiết nếu nó đang gây CPU/GC/latency đáng kể.

### 10.1. Đơn vị đo nên dùng

- **bytes/request**: đã cấp phát bao nhiêu byte cho mỗi yêu cầu?
- **MB/s hoặc GB/s**: tốc độ cấp phát trong thời gian ổn định.
- **top allocating types / stacks**: nơi tạo object.
- **post-GC occupancy**: lượng dữ liệu còn sống sau GC.
- **GC pause distribution**: thời gian ngừng ứng dụng.
- **GC CPU time**: phần CPU dành cho GC.

Ví dụ, nếu một service thực sự cấp phát trung bình **2 MB/request** và xử lý **500 request/s**, tổng allocation có thể xấp xỉ **1 GB/s**. Điều này **không** đồng nghĩa heap phải tăng 1 GB mỗi giây, vì GC có thể thu hồi các đối tượng ngắn hạn.

### 10.2. Những nguồn cấp phát thường gặp

- Tạo **String** và **byte[]** qua chuyển đổi encoding lặp lại.
- Tạo collection trung gian cho mỗi record.
- Chia chuỗi/regex không cần thiết trong hot loop.
- Boxing primitive vào wrapper không cần thiết trong dữ liệu lớn.
- Lặp lại parse hoặc serialize cùng dữ liệu.
- Tạo response body trong RAM khi có thể streaming.
- Tạo exception/stack trace trong một đường nóng mà lỗi đã trở thành điều kiện thường xuyên.

**Không có quy tắc cấm String, Stream hoặc Optional.** Chúng thường làm code tốt hơn; chỉ thay đổi nếu profile cho thấy chi phí đáng kể trên workload của bạn.

## 11. Tối ưu allocation có chọn lọc

### 11.1. Tránh tạo cả cây dữ liệu khi chỉ cần tính tổng

Giả sử mỗi request chỉ cần tổng số byte của dữ liệu đã đọc.

Cách có thể gây memory pressure:

~~~java
byte[] allBytes = java.nio.file.Files.readAllBytes(path);

long size = allBytes.length;
~~~

Nếu file cực lớn, **readAllBytes** có thể cấp phát một mảng lớn trong heap. Khi chỉ cần kích thước file:

~~~java
long size = java.nio.file.Files.size(path);
~~~

Hai cách có **ngữ nghĩa khác nhau**:

- **Files.size** trả metadata kích thước theo filesystem tại thời điểm gọi; không kiểm tra nội dung và có thể thay đổi nếu file được ghi đồng thời.
- **readAllBytes** đọc nội dung file vào RAM; phù hợp khi thực sự cần xử lý toàn bộ byte.

Không thay thế máy móc nếu nghiệp vụ yêu cầu đọc và xác minh nội dung. Đây là ví dụ về **giảm công việc không cần thiết**, không phải mẹo cú pháp.

### 11.2. Giảm boxing trong đường dữ liệu lớn

~~~java
long total = 0;

for (int i = 0; i < values.length; i++) {
    total += values[i];
}
~~~

Với **values** là **int[]**, vòng lặp dùng primitive trực tiếp; nếu đổi thành **List<Integer>**, chương trình có thể thêm chi phí boxing/unboxing và object representation.

Đừng tự thay mọi collection thành mảng. Hãy đo throughput, allocation và complexity của API trước.

### 11.3. Tái sử dụng buffer có trách nhiệm

Tái sử dụng một byte buffer trong một vòng đọc tuần tự có thể giảm cấp phát so với tạo một buffer mới mỗi lần đọc:

~~~java
byte[] buffer = new byte[64 * 1024];

int read;

while ((read = input.read(buffer)) != -1) {
    output.write(buffer, 0, read);
}
~~~

**input** và **output** phải là stream đã được mở/quản lý trong phạm vi thích hợp. Ví dụ không tự bảo đảm thread-safety nếu buffer bị chia sẻ qua nhiều request.

Không đặt một **static mutable buffer** dùng chung nhiều thread mà không có hợp đồng đồng bộ; giảm allocation nhưng gây race và sai dữ liệu là thất bại.

### 11.4. Khi nào allocation thấp hơn lại tệ hơn?

Một custom object pool có thể giảm allocation nhưng tăng:

- Số live objects và old-generation occupancy.
- Lock contention.
- Thời gian reset và nguy cơ dùng lại object còn trạng thái cũ.
- Rủi ro bảo mật khi dữ liệu request trước còn trong buffer.

Với các object Java nhỏ, JVM/GC hiện đại thường xử lý tốt; object pooling không phải lời khuyên mặc định. Chỉ áp dụng nếu **đã đo**, có chủ sở hữu rõ ràng và kiểm thử đầy đủ.

## 12. GC: đọc kết quả đo trước khi chỉnh collector

Unified Logging là cơ chế logging JVM hiện hành; không dùng các cờ GC logging đời cũ làm hướng dẫn mặc định.

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags MyApplication
~~~

Có thể giới hạn file rotation:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M MyApplication
~~~

Kiểm tra những tag/level JVM đang hỗ trợ:

~~~bash
java -Xlog:help
~~~

### 12.1. Đọc một GC log cần chú ý gì?

- Heap sử dụng trước và sau GC, có xu hướng ổn định hay tăng.
- Lịch sử pauses, phân bố các pause dài, không chỉ trung bình.
- GC diễn ra thường xuyên vì allocation rate cao hay do heap quá nhỏ.
- GC sử dụng bao nhiêu CPU trong điều kiện tải.
- Có các sự kiện bất thường như allocation failure, humongous allocations hoặc promotion pressure không.
- Dữ liệu sau GC tăng liên tục có tương quan với cache/retention không.

**GC logs không tự chứng minh object nào bị giữ sống**. Nếu nghi memory leak, cần heap histogram, heap dump hoặc phân tích paths to GC roots.

### 12.2. Khi nào nên chỉnh -Xmx hoặc collector?

Chỉ sau khi có baseline và biết nguyên nhân. Ví dụ:

- Heap quá nhỏ so với live set thực tế có thể gây GC thường xuyên.
- Heap quá lớn có thể khiến memory budget của container vượt khả năng.
- Collector được chọn có trade-off về throughput, pauses và tài nguyên CPU.
- Concurrent collector có thể giảm pause nhưng tiêu tài nguyên concurrent đáng kể.

Các lựa chọn GC hiện hành như **G1**, **ZGC** hoặc **Shenandoah** (tùy bản phân phối/JVM) có đặc tính khác nhau. Không khẳng định một collector luôn tốt nhất cho mọi ứng dụng Java 27.

**Không đổi collector, heap size và đồng thời thay code trong cùng một phép thử**: bạn sẽ không biết yếu tố nào tạo ra kết quả.

## 13. Phân biệt allocation cao và retention leak

Khi heap sau nhiều lần GC cứ tăng:

1. Xác nhận mức tải/working set không tăng tương ứng.
2. Xem class histogram và top growing types.
3. Khi được phép, chụp heap dump trong môi trường bảo mật.
4. Phân tích đường giữ **GC roots → đối tượng lớn**.
5. Xem static caches, listeners, ThreadLocal, Futures, queues, classloaders.
6. Sửa vòng đời/eviction, đo lại post-GC heap và p99.

Ví dụ lệnh chẩn đoán:

~~~bash
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
~~~

Trong trường hợp điều tra chuyên sâu:

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

**Cảnh báo:** heap dump có thể gây pause, tiêu tốn đĩa và chứa **token, mật khẩu, dữ liệu cá nhân**. Không chạy trên hệ thống production khi chưa có quyền, kế hoạch bảo mật và đánh giá tác động. Một số diagnostic commands có thể có chi phí rất cao so với JFR lấy mẫu.

## 14. Native memory không nằm hoàn toàn trong heap

Một JVM có thể có:

- Java heap.
- Metaspace/class metadata.
- JIT code cache.
- Thread stacks và cấu trúc runtime.
- Direct buffers/native allocations.
- Memory-mapped regions.
- Các thư viện JNI/foreign code.

Vì vậy **RSS** của tiến trình có thể cao hơn **-Xmx**. Không kết luận leak Java heap chỉ từ RSS.

### 14.1. Native Memory Tracking

Để theo dõi phần bộ nhớ native mà **HotSpot JVM tự quản lý**, bật khi khởi động:

~~~bash
java -XX:NativeMemoryTracking=summary MyApplication
~~~

Sau khi JVM chạy:

~~~bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
~~~

Chạy workload một khoảng thời gian rồi:

~~~bash
jcmd <pid> VM.native_memory summary.diff
~~~

**NMT phải được bật từ khi JVM khởi động**; không có cơ chế đơn giản để bật lại đầy đủ cho một tiến trình đã khởi động mà không bật NMT.

NMT có overhead hiệu năng và bộ nhớ, nên cân nhắc trước khi bật ở production. Nó **không theo dõi mọi native allocation do thư viện bên ngoài/JNI tự thực hiện**, do đó vẫn cần công cụ cấp OS hoặc chuyên dụng nếu nghi leak nằm ngoài JVM.

## 15. I/O-bound: đo nơi chờ trước khi thêm thread

Một request có thể bị giới hạn bởi:

- Đợi lấy connection từ database pool.
- Truy vấn database thực thi chậm.
- Network RTT, DNS, TLS handshake.
- Đợi server HTTP khác xử lý.
- Đọc file trên volume chậm hoặc shared filesystem.
- Serialization/deserialization sau khi nhận dữ liệu.
- Queue chờ vì concurrency limit của service.

Các nguyên nhân đó cần **giải pháp khác nhau**. Thêm 1.000 virtual threads có thể giúp chi phí chờ rẻ hơn về mặt thread nhưng không làm database chạy nhanh hơn hoặc tăng số kết nối có sẵn.

### 15.1. Chia thời gian request thành các stage

Ví dụ:

~~~text
Total:                  450 ms
- Acquire DB connection: 180 ms
- Database query:        35 ms
- HTTP downstream:      150 ms
- Parse/transform:       70 ms
- Other:                 15 ms
~~~

Các số chỉ là **giả định minh họa**.

Nếu chi phí chờ connection là **180 ms**, tối ưu đoạn parse **70 ms** tới mức không tốn CPU cũng chỉ tiết kiệm tối đa khoảng 70 ms trong trường hợp đơn giản. Quan trọng hơn, vấn đề trước mắt có thể là capacity/queue ở connection pool.

### 15.2. Dùng tracing và metric theo stage

Khi đo:

- Ghi **request-id/trace-id** để nối các span.
- Ghi thời gian **acquire connection** riêng với thời gian **execute query**.
- Với HTTP, tách lỗi DNS/connect/TLS/first byte/receive body nếu công cụ hỗ trợ.
- Ghi status, timeout, số retry và kích thước body.
- Phân biệt thời gian queue tại client với thời gian server xử lý.
- Không log body, token hoặc query parameter nhạy cảm chỉ để phục vụ tracing.

Nếu một HTTP client có connection pooling, thời gian chờ lấy connection có thể là nút thắt ngay cả khi endpoint đáp ứng nhanh khi được gọi.

## 16. Tối ưu I/O: giảm công việc thay vì chỉ tăng concurrency

Một số thay đổi có thể mang lại lợi ích, nhưng đều cần đo:

| Nguyên nhân đo được | Thử thay đổi | Chỉ số xác minh |
|---|---|---|
| DB N+1 queries | Batch hoặc query phù hợp hơn | Số query/request, DB time, p95 |
| Payload HTTP quá lớn | Phân trang, projection hoặc nén theo hợp đồng | Bytes/request, CPU encode/decode, latency |
| Đọc file lớn vào RAM | Stream với buffer có giới hạn | Peak heap, allocation, throughput |
| Mở kết nối liên tục | Dùng lại **HttpClient**/connection pool phù hợp | Handshake count, connection latency |
| Too many concurrent DB calls | Giới hạn in-flight bằng pool/semaphore | Queue wait, timeout, DB saturation |
| Ghi log đồng bộ quá nhiều | Điều chỉnh log level/batch an toàn | Disk I/O, CPU, dropped logs |
| Retry storm | Backoff, jitter, circuit breaking theo hợp đồng | Retry rate, error rate, downstream load |
| Băng thông nghẽn | Giảm payload, đặt cache phù hợp | Network bytes, throughput |
| Đọc file tuần tự tốn syscalls | Buffer hoặc API copy thích hợp | File read count, IO latency |

**Không mặc định batching, compression hay caching luôn giảm latency**. Compression tăng CPU; batch lớn làm tăng thời gian chờ gom dữ liệu; cache có nguy cơ stale và tốn bộ nhớ.

## 17. Ví dụ streaming file và đo thời gian thực tế

Nếu chỉ cần tính checksum SHA-256 của một file lớn, không cần đọc toàn bộ file vào một mảng byte.

Tạo **StreamingDigestDemo.java**:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public class StreamingDigestDemo {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                "Usage: java StreamingDigestDemo <file>"
            );
            return;
        }

        Path path = Path.of(args[0]);
        MessageDigest digest =
            MessageDigest.getInstance("SHA-256");

        byte[] buffer = new byte[64 * 1024];
        long totalBytes = 0;
        long started = System.nanoTime();

        try (InputStream input = Files.newInputStream(path)) {
            int read;

            while ((read = input.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
                totalBytes += read;
            }
        }

        long elapsed = System.nanoTime() - started;

        System.out.println("Bytes: " + totalBytes);
        System.out.println(
            "SHA-256: " + HexFormat.of().formatHex(digest.digest())
        );
        System.out.printf(
            "Elapsed: %.3f ms%n",
            elapsed / 1_000_000.0
        );
    }
}
~~~

Chạy trên file **do bạn kiểm soát**:

~~~bash
javac StreamingDigestDemo.java
java StreamingDigestDemo data.bin
~~~

Ưu điểm:

- Buffer sử dụng có kích thước cố định.
- Không cần tạo mảng chứa toàn bộ file.
- Có thể chạy trên file lớn mà không tương ứng tăng heap theo dung lượng file.
- Có kết quả SHA-256 để đối chiếu tính đúng sau thay đổi.

**Giới hạn của phép đo:** thời gian đo gồm cả đọc file và tính digest; OS page cache, loại ổ đĩa, trạng thái cache và mã hóa checksum ảnh hưởng mạnh. Không được kết luận một loại I/O nhanh hơn từ một lần chạy lệnh.

### 17.1. Khi nào nên dùng Files.readAllBytes?

Nếu file nhỏ, toàn bộ nội dung cần xử lý nhiều lần và điều kiện bộ nhớ được bảo đảm, **Files.readAllBytes** có thể đơn giản và phù hợp hơn.

Chọn streaming vì **giới hạn memory footprint / tăng khả năng xử lý file lớn**, không vì giả định streaming luôn nhanh hơn trong mọi workload.

## 18. Little's Law và giới hạn đồng thời

Một hệ thống ổn định có quan hệ gần đúng:

\[
L = \lambda \times W
\]

Trong đó:

- **L**: số request trung bình đang ở trong hệ thống.
- **λ**: throughput (request/giây).
- **W**: thời gian trung bình một request ở trong hệ thống (giây).

Ví dụ giả định:

~~~text
Throughput ổn định:    400 request/s
Thời gian trung bình:  0,25 s
Số request đang bay:   400 × 0,25 = 100
~~~

Nếu latency tăng từ **0,25 s** lên **1 s** tại cùng throughput, số request in-flight trung bình tăng tới **400**. Điều này có thể tăng bộ nhớ giữ request state, queue length và áp lực lên connection pool.

**Little's Law không bảo đảm** cứ mở 400 threads là đạt 400 request/s; nó mô tả một quan hệ trung bình của hệ thống ổn định.

### 18.1. Semaphore và concurrency limit

Với một dịch vụ ngoài có capacity hữu hạn:

~~~java
import java.util.concurrent.Semaphore;

final class LimitedRemoteClient {
    private final Semaphore permits = new Semaphore(20);

    String call() throws Exception {
        permits.acquire();

        try {
            return performRemoteCall();
        } finally {
            permits.release();
        }
    }

    private String performRemoteCall() {
        // Thay bằng HTTP/JDBC call đồng bộ thực tế.
        return "OK";
    }
}
~~~

**Semaphore(20)** chỉ minh họa giới hạn, không phải con số chuẩn cho mọi hệ thống. Mức tối ưu phải dựa vào số liệu: throughput, queue wait, error/timeout và tải phía downstream.

### 18.2. Virtual threads và CPU bound

Virtual threads rất phù hợp cho nhiều lời gọi blocking I/O trên Java 27. Nhưng chúng không tạo thêm lõi CPU. Nếu nhiều tác vụ đang tính toán liên tục, throughput vẫn bị giới hạn bởi CPU và mức contention.

Khi I/O là bottleneck, tăng khả năng concurrent waits có thể có ích cho tới khi downstream bão hòa. Khi CPU là bottleneck, tăng virtual threads thường không giải quyết nguyên nhân.

## 19. Dùng JFR custom events để đo pha nghiệp vụ

Các sự kiện JFR tích hợp cho biết hoạt động JVM, nhưng ứng dụng có thể bổ sung **custom event** để nối thông tin với tên pha nghiệp vụ.

Ví dụ độc lập **JfrPhaseDemo.java**:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

public class JfrPhaseDemo {

    @Name("demo.BusinessPhase")
    @Label("Business phase")
    static class BusinessPhase extends Event {
        @Label("Phase")
        String phase;

        @Label("Items")
        int items;
    }

    private static volatile long sink;

    static void process(String phase, int items) {
        BusinessPhase event = new BusinessPhase();
        event.phase = phase;
        event.items = items;
        event.begin();

        try {
            long sum = 0;

            for (int i = 0; i < items; i++) {
                sum += (long) i * i;
            }

            sink = sum;
        } finally {
            event.commit();
        }
    }

    public static void main(String[] args) {
        for (int i = 0; i < 100; i++) {
            process("calculate", 200_000);
        }

        System.out.println("Sink: " + sink);
    }
}
~~~

Chạy:

~~~bash
javac JfrPhaseDemo.java
java -XX:StartFlightRecording=filename=demo.jfr,settings=profile,dumponexit=true JfrPhaseDemo
~~~

Sau đó:

~~~bash
jfr summary demo.jfr
jfr print --events demo.BusinessPhase demo.jfr
~~~

Lưu ý:

- **@Name("demo.BusinessPhase")** xác định tên sự kiện.
- **begin/commit** bao lấy pha cần đo, không yêu cầu in log từng iteration.
- Sự kiện cần được **enable** trong cấu hình JFR; threshold/sampling và độ ngắn của chương trình có thể ảnh hưởng file kết quả.
- Đây là ví dụ tính toán, không mô tả một luồng CPU thực tế của sản phẩm.
- Khi dùng module Java riêng, có thể phải thêm **requires jdk.jfr** trong module descriptor do project của bạn quản lý.

**Không gắn giá trị nhạy cảm** như token, mật khẩu, dữ liệu khách hàng vào field của JFR event.

## 20. JMH: benchmark method không phải tự viết vòng lặp đo

Khi muốn trả lời câu hỏi hẹp như:

> **HashSet.contains có nhanh hơn List.contains với 10.000 key và 1.000 query không?**

một vòng **System.nanoTime()** quanh method thường không đủ đáng tin do:

- JIT compilation và warmup.
- Dead-code elimination.
- Constant folding.
- Escape analysis và allocation elimination.
- Tác động của GC.
- CPU frequency scaling hoặc tải nền.
- Thứ tự chạy phiên bản A/B.

**JMH (Java Microbenchmark Harness)** của OpenJDK được thiết kế cho benchmark mức method, có warmup, iterations, forks và cách tiêu thụ kết quả hợp lý.

**JMH không nằm sẵn trong module java.base hay bản cài JDK.** Muốn chạy code có annotation **org.openjdk.jmh.annotations**, dự án phải cấu hình dependency và annotation processor JMH phù hợp.

### 20.1. Ví dụ benchmark JMH

Đoạn sau là **mẫu JMH**, không phải file Java có thể chạy bằng **javac** đơn lẻ khi chưa thêm dependency:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class MembershipBenchmark {

    @Param({"1000", "10000"})
    public int size;

    private List<Integer> list;
    private Set<Integer> set;
    private Integer needle;

    @Setup(Level.Trial)
    public void setup() {
        list = new ArrayList<>();
        for (int i = 0; i < size; i++) {
            list.add(i);
        }
        set = new HashSet<>(list);
        needle = size - 1;
    }

    @Benchmark
    public boolean listLookup() {
        return list.contains(needle);
    }

    @Benchmark
    public boolean setLookup() {
        return set.contains(needle);
    }
}
~~~

Điểm học thuật quan trọng:

- **@Param** cho nhiều kích thước input.
- **@Setup(Level.Trial)** đặt việc tạo dữ liệu ngoài đoạn cần đo.
- **@Benchmark** là hai phép kiểm tra membership.
- Return value là kết quả có thể được JMH tiêu thụ, tránh phép đo bị bỏ vì kết quả không được dùng.
- Nếu bài toán production xây lại set ở mỗi request, cần **đo chi phí build set** trong một benchmark hoặc phép đo khác, chứ không chỉ benchmark contains.
- Một benchmark cho **một needle cố định** không đại diện mọi tỷ lệ hit/miss hay phân bố truy vấn. Hãy mở rộng dữ liệu đầu vào theo workload thật.

### 20.2. Không dùng microbenchmark thay cho load test

Một tối ưu method nhanh hơn 20% không có nghĩa API nhanh hơn 20%. Nếu method chỉ chiếm 5% tổng request time, lợi ích end-to-end có thể rất nhỏ.

Vì vậy, workflow hợp lý:

1. **JFR/tracing** chỉ ra method quan trọng.
2. **JMH** trả lời câu hỏi vi mô về cách triển khai.
3. **Load test end-to-end** xác minh kết quả với dependency và concurrency thực tế.
4. **Production metrics** theo dõi sau rollout.

## 21. Amdahl's Law: giới hạn lợi ích tối ưu cục bộ

Nếu một phần chiếm tỉ lệ **p** trong thời gian xử lý, và làm phần đó nhanh hơn **s** lần, tốc độ tối đa tổng thể theo mô hình đơn giản là:

\[
\text{Speedup} = \frac{1}{(1-p)+p/s}
\]

Ví dụ, **parse JSON** chiếm **20%** thời gian request (p = 0,2), và ta làm phần này nhanh gấp đôi (s = 2):

\[
\text{Speedup} = \frac{1}{0,8 + 0,1}
\approx 1,11
\]

Tức tổng thể chỉ nhanh khoảng **11%**, không phải 100%.

Đây là mô hình đơn giản khi tỷ lệ phần việc ổn định và không có hiệu ứng queueing. Với hệ thống server chịu tải, giảm thời gian giữ một tài nguyên bão hòa có thể có tác động **phi tuyến** lên queue wait và p99. Hãy đo end-to-end thay vì dùng Amdahl như con số dự đoán chắc chắn.

## 22. Đo và so sánh A/B đúng cách

Một thay đổi đáng tin cậy cần:

### 22.1. Giữ biến thử nghiệm ổn định

- Cùng JDK/JVM flags/GC/memory quota.
- Cùng máy hoặc môi trường đối chứng tương đương.
- Cùng traffic mix, data size, DB state trong phạm vi có thể.
- Cùng warmup và thời gian steady-state.
- Không đồng thời thay cache, connection pool, collector và thuật toán.
- Chạy lặp nhiều lần, không chỉ một kết quả đẹp nhất.

### 22.2. Tránh thứ tự A rồi B luôn cố định

Nếu A chạy lúc CPU mát và B chạy lúc máy chịu tải lớn, bạn có thể kết luận sai. Đổi thứ tự hoặc xen kẽ các lượt đo khi thích hợp, đồng thời giữ isolation cần thiết.

### 22.3. Quan sát phân bố

Ưu tiên so sánh:

- Throughput tại **cùng error/latency budget**, hoặc latency tại **cùng throughput**.
- p50, p95, p99 và số lượng samples.
- CPU time/request, CPU utilization.
- Allocation bytes/request và GC pauses.
- Network bytes/request, DB time, queue wait.
- Confidence interval hoặc mức biến thiên giữa các lần đo nếu có.

Một thay đổi p99 từ **800 ms** xuống **790 ms** trong khi kết quả dao động ±100 ms chưa phải bằng chứng đủ mạnh.

### 22.4. Tính cải thiện bằng công thức có ngữ nghĩa

Với latency thấp hơn là tốt:

\[
\text{Giảm latency (\%)} =
\frac{L_{\text{trước}}-L_{\text{sau}}}{L_{\text{trước}}}\times100
\]

Với throughput cao hơn là tốt:

\[
\text{Tăng throughput (\%)} =
\frac{T_{\text{sau}}-T_{\text{trước}}}{T_{\text{trước}}}\times100
\]

Không trộn hai tỷ lệ này hoặc gọi cải thiện latency 20% là throughput chắc chắn tăng 20%; quan hệ thực tế phụ thuộc giới hạn và tải.

## 23. Case study: API tạo ảnh thumbnail

Giả sử một endpoint nhận ảnh và trả thumbnail. Pipeline:

~~~mermaid
flowchart LR
    A["Nhận request"] --> B["Đọc upload từ mạng"]
    B --> C["Decode ảnh"]
    C --> D["Resize thumbnail"]
    D --> E["Encode JPEG/WebP"]
    E --> F["Lưu object storage"]
    F --> G["Trả response"]
~~~

Các khả năng:

- **I/O**: chờ upload, chờ object storage.
- **CPU**: decode, resize, encode.
- **Allocation**: pixel arrays, object trung gian, buffers, response serialization.

### 23.1. Giả định baseline

~~~text
p95 latency:                  1200 ms
CPU utilization:               92% quota
Allocation:                    12 MB/request
Top CPU:                       image encoding
Slow external storage call:    60 ms
~~~

Số liệu chỉ là **tình huống giả định**.

**Phân tích:** CPU đang gần bão hòa và phần encode xuất hiện ở top CPU. Vì vậy, thêm nhiều I/O concurrency hoặc tăng connection pool chưa chắc giúp; có thể làm thêm request xếp hàng chờ CPU.

### 23.2. Thay đổi có giả thuyết

Ví dụ:

- Giảm kích thước ảnh trước những bước xử lý không cần độ phân giải gốc, nếu chất lượng/hợp đồng cho phép.
- Không giải mã cùng ảnh hai lần.
- Tránh tạo nhiều intermediate images không cần thiết.
- Đánh giá cấu hình encoder/quality và tính đúng của thumbnail.

**Chỉ thay đổi một nhóm có thể đo rõ**. Sau đó ghi JFR và load test lại với cùng tập ảnh/mức tải.

### 23.3. Diễn giải kết quả giả định

~~~text
p95 latency:                  850 ms
CPU utilization:              70% quota
Allocation:                   8 MB/request
Error rate:                   không đổi
Output quality:               đạt tiêu chí kiểm tra
~~~

Thay đổi này có bằng chứng ủng hộ nếu kết quả lặp lại ổn định và không đánh đổi chất lượng ảnh ngoài yêu cầu.

Nếu allocation giảm mà latency không đổi, cần xem lại giả thuyết: có thể bottleneck đã chuyển sang I/O hoặc một stage khác.

## 24. Mô hình ưu tiên theo dữ liệu

Một danh sách công việc thường có nhiều ý tưởng tối ưu. Ưu tiên dựa trên:

1. **Mức ảnh hưởng** tới p95/p99, throughput hoặc chi phí.
2. **Mức tin cậy của bằng chứng** từ profile/traces.
3. **Chi phí và rủi ro triển khai**.
4. **Khả năng kiểm chứng/rollback**.
5. **Tính tương thích và correctness**.

| Hiện tượng đo được | Giả thuyết mạnh | Hành động ưu tiên |
|---|---|---|
| CPU 95%, encode chiếm 60% samples | Encoder là hot path | Profile sâu, giảm work hoặc tối ưu thuật toán |
| CPU 30%, 300 ms chờ pool connection | Pool/DB là bottleneck | Đo query vs queue, điều chỉnh capacity/tải |
| Allocation 1 GB/s, GC CPU cao | Tạo nhiều object tạm trong hot path | Xem allocation stacks, giảm cấu trúc trung gian |
| Heap sau GC tăng nhiều giờ | Retention leak | Heap dump/retaining path, sửa vòng đời |
| RSS tăng nhưng heap ổn định | Native/direct memory | NMT + OS tools, xem giới hạn NMT |
| p99 tăng sau retry storm | Retry làm tăng tải downstream | Backoff, giới hạn retry, rate limit |
| Rất nhiều log lines / request | Logging tốn CPU/I/O | Đo log volume, giảm log không cần thiết |
| Vấn đề chỉ ở payload lớn | Complexity/buffer behavior phụ thuộc kích thước | Phân nhóm dữ liệu đo theo payload size |

**Không dùng bảng này như một tập quy tắc thay thế profiler.** Nó chỉ giúp đặt giả thuyết ban đầu.

## 25. Anti-patterns khi chẩn đoán và tối ưu

| Sai lầm | Vì sao nguy hiểm | Cách làm đúng |
|---|---|---|
| Tối ưu theo cảm giác | Có thể sửa phần không nằm trên critical path | Đo và ưu tiên hot path |
| Dựa vào average latency | Che khuất p95/p99 và queueing | Đo phân vị, error, throughput |
| Chạy System.nanoTime một lần rồi kết luận | JIT/warmup/tải nền làm sai lệch | JMH và phép đo lặp |
| Bỏ qua CPU quota của container | Diễn giải CPU utilization sai | Đo theo quota và throttling |
| Thấy CPU cao là tăng thread | Tăng contention và p99 | Profile, giới hạn concurrency |
| Thấy GC nhiều là đổi GC ngay | Không biết nguồn allocation/retention | Đọc allocation stacks và GC logs trước |
| Xem allocation rate là live heap | Hai đại lượng khác nhau | Đo cả bytes/request và retained heap |
| Giảm allocation bằng shared mutable buffers | Race, sai dữ liệu | Chỉ reuse trong ownership rõ |
| Dùng object pooling cho mọi object | Tăng live set và complexity | Chỉ pool khi profile chứng minh có ích |
| Dùng System.gc() trong request | Không giải quyết root retention, có thể gây pause | Sửa retaining references |
| Dùng -Xloggc theo hướng dẫn cũ | Cờ cũ đã được thay bằng Unified Logging | Dùng **-Xlog:gc** |
| Bật JFR profile nặng không giới hạn | Gây overhead và tốn dung lượng | Chọn settings/cửa sổ ghi phù hợp |
| In toàn bộ JFR/heap dump vào log | Lộ dữ liệu, tốn đĩa và khó phân tích | Hạn chế quyền, lưu trữ và xử lý an toàn |
| Tin rằng JFR sample bằng exact CPU milliseconds | Sampling/threshold có sai số | Kết hợp CPU metrics và nhiều lần đo |
| Thấy NMT bình thường là không có native leak | NMT không theo dõi mọi thư viện native ngoài JVM | Kết hợp OS/native profiler |
| Tối ưu I/O bằng retry vô hạn | Tạo retry storm | Timeouts, backoff, cancellation, idempotency |
| Tăng cache không giới hạn | Giảm I/O nhưng gây memory retention | TTL, maximum weight và invalidation |
| Thay nhiều yếu tố cùng lúc | Không biết nguyên nhân cải thiện/xấu đi | A/B có kiểm soát |
| Benchmark sai workload thực tế | Tối ưu mẫu dữ liệu không đại diện | Dùng mix/size/concurrency phù hợp |
| Giảm latency nhưng tăng lỗi | Mất độ tin cậy hệ thống | Bắt buộc regression checks |

## 26. Checklist cho một vòng tối ưu

Trước khi bắt đầu:

- [ ] Xác định SLO/tiêu chí latency, throughput, error và memory.
- [ ] Ghi commit/build, Java 27 vendor/build, JVM flags và cấu hình môi trường.
- [ ] Xác nhận CPU quota, heap limit và tài nguyên của database/network.
- [ ] Có workload đại diện, dữ liệu đầu vào và thời gian warmup.
- [ ] Đo baseline với cùng phương pháp sẽ đo sau tối ưu.

Trong khi phân tích:

- [ ] Có JFR/traces hoặc thông tin CPU/allocation/I/O đủ để nêu giả thuyết.
- [ ] Phân biệt CPU time với wall time, allocation với retained heap.
- [ ] Đã xác định method/stage và input size làm xuất hiện bottleneck.
- [ ] Xem thêm GC, queue wait, retry và lock contention nếu cần.
- [ ] Đánh giá overhead và rủi ro dữ liệu của công cụ chẩn đoán.

Sau khi thay đổi:

- [ ] Kiểm thử chức năng, dữ liệu đầu ra và quy tắc nghiệp vụ không bị sai.
- [ ] Chỉ một thay đổi chính được đưa vào phép so sánh.
- [ ] Chạy đủ lượt đo với warmup, load mix và điều kiện tương đương.
- [ ] So sánh p50/p95/p99, throughput, error, CPU, allocation, GC và I/O.
- [ ] Ghi lại bằng chứng, độ biến thiên, trade-off và quyết định giữ/hoàn tác.
- [ ] Theo dõi sau triển khai và có kế hoạch rollback.

## 27. Bài thực hành

### Bài 1 — CPU và đo khối lượng công việc

1. Chạy **MembershipComparisonDemo** với List và HashSet.
2. Thay kích thước **allowed** thành 100, 1.000 và 20.000.
3. Thay tỷ lệ hit/miss của queries.
4. Đo cả chi phí tạo HashSet nếu ứng dụng phải tạo nó mỗi lần.
5. Ghi giả thuyết và so sánh sau nhiều lần chạy.
6. Viết lại benchmark bằng **JMH** nếu có môi trường dependency thích hợp.
7. Xác nhận kết quả của hai phương án luôn tương đương.

### Bài 2 — Allocation và GC

1. Đo baseline của một service xử lý văn bản hoặc JSON.
2. Chạy JFR profile trong một khoảng tải được kiểm soát.
3. Tìm top allocating types và các call stacks tương ứng.
4. Chọn một chỗ tạo đối tượng trung gian không cần thiết.
5. Giảm allocation nhưng giữ đúng dữ liệu đầu ra.
6. So sánh bytes/request, CPU time, p95/p99 và GC logs.
7. Giải thích vì sao allocation giảm mà latency có thể không giảm.

### Bài 3 — I/O streaming

1. Tạo một file dữ liệu lớn trong môi trường test riêng.
2. Chạy **StreamingDigestDemo** và ghi checksum/elapsed time.
3. Thử buffer 4 KiB, 64 KiB và 1 MiB với cùng file.
4. Cân nhắc ảnh hưởng OS page cache và số lần chạy.
5. Đo heap/GC và throughput.
6. Đảm bảo checksum không thay đổi.
7. Phân tích kích thước buffer tối ưu có thật sự ổn định hay không.

### Bài 4 — Case study production

Một API có:

~~~text
p99 latency:               2.0 s
CPU:                       25%
Allocation rate:           300 MB/s
DB connection wait p95:    1.2 s
DB query p95:              80 ms
Retry rate:                12%
~~~

Hãy lập giả thuyết ưu tiên, đề xuất cách đo thêm và phác thảo thử nghiệm A/B.

Gợi ý: đầu tiên nên điều tra **thời gian chờ connection, mức bão hòa downstream và retry**, không bắt đầu bằng việc đổi GC chỉ vì thấy allocation 300 MB/s.

## 28. Câu hỏi tự kiểm tra

1. Vì sao tối ưu một method nóng chưa chắc giảm p99 end-to-end?
2. Wall time và CPU time khác nhau thế nào khi thread phải chờ I/O?
3. Khi allocation rate cao nhưng post-GC heap ổn định, có nhất thiết leak không?
4. Vì sao GC log không chỉ ra trực tiếp retaining path?
5. Điều gì khiến RSS tăng dù Java heap không tăng?
6. JFR **default.jfc** và **profile.jfc** khác nhau về mục đích gì?
7. Vì sao event không xuất hiện trong JFR không chứng minh nó chưa từng xảy ra?
8. JMH giải quyết những vấn đề nào so với đo System.nanoTime một lần?
9. Vì sao cần đo chi phí tạo HashSet, không chỉ contains?
10. Khi CPU thấp nhưng DB wait cao, bạn thử điều gì trước?
11. Bounded concurrency khác gì tăng số virtual threads vô hạn?
12. Amdahl's Law giúp đặt kỳ vọng thế nào?
13. Vì sao cần kiểm tra correctness sau thay đổi tối ưu?
14. Một heap dump có những rủi ro bảo mật và vận hành nào?
15. Tiêu chí nào khiến bạn quyết định hoàn tác một thay đổi dù một microbenchmark nhanh hơn?

## 29. Ghi nhớ

- **Tối ưu phải dựa trên dữ liệu đo và tiêu chí thành công rõ ràng**, không phải cảm giác.
- Đo **latency phân vị, throughput, error** cùng với CPU, allocation, heap, GC và I/O.
- **CPU time** khác **wall time**; chờ mạng/DB có thể làm wall time cao trong khi CPU thấp.
- **JFR/JMC** thích hợp để quan sát CPU samples, allocation, GC, I/O và contention trên Java 27.
- **jcmd** và **jfr** cho phép ghi, xem và phân tích JFR; dùng cấu hình/cửa sổ phù hợp để kiểm soát overhead.
- Với CPU, ưu tiên **giảm công việc và cải thiện thuật toán** trước khi tăng thread.
- Với allocation, phân biệt **byte đã cấp phát** với **đối tượng còn được giữ**; giảm allocation khi nó thật sự gây GC/CPU/latency.
- Với GC, dùng **-Xlog**, đo pauses và live set trước khi đổi collector hoặc heap flags.
- Với I/O, đo **queue wait, network/database latency, connection pool và retry**, không chỉ tăng concurrency.
- **JMH** là công cụ microbenchmark ngoài JDK; load test end-to-end vẫn cần thiết.
- **NMT** giúp quan sát bộ nhớ native do HotSpot quản lý, nhưng không thay thế OS profiler.
- Dùng cùng workload, giữ biến thử nghiệm ổn định, đo nhiều lần và kiểm tra tính đúng.
- Mỗi tối ưu tốt phải có **bằng chứng trước/sau, giới hạn áp dụng và khả năng hoàn tác**.

## Tài liệu tham khảo

- [Oracle Java SE 27 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 27 — The java Command / Unified Logging](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [Oracle Java SE 27 — JFR Configurations](https://docs.oracle.com/en/java/javase/27/jfapi/flight-recorder-configurations.html)
- [Oracle Java SE 27 — Creating and Recording Your First Event](https://docs.oracle.com/en/java/javase/27/jfapi/creating-recording-your-first-event.html)
- [Oracle Java SE 27 — Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/27/troubleshoot/troubleshooting-memory-leaks.html)
- [Oracle Java SE 27 API — ThreadMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Oracle Java SE 27 API — Flight Recorder Event](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Oracle Java SE 27 API — System.nanoTime](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html#nanoTime())
- [Oracle Java SE 27 API — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html)
- [Oracle Java SE 27 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/27/gctuning/)
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://openjdk.org/projects/code-tools/jmh/)
- [OpenJDK — JDK Mission Control](https://openjdk.org/projects/jmc/)
