# 17.3. Nhận diện vòng lặp tốn CPU, thuật toán đắt và công việc lặp ngoài dự kiến

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt **CPU thực sự bận chạy mã** với **wall-clock latency** do I/O, chờ khóa, GC hoặc scheduler; không nhìn một chỉ số CPU rồi kết luận nguyên nhân.
- Nhận diện ba nhóm vấn đề: **hot loop/busy spin**, **thuật toán có độ phức tạp cao**, và **công việc bị gọi lặp ngoài dự kiến**.
- Dùng số liệu hệ điều hành, **JFR/JDK Mission Control**, thread dump, counters và phép thử thay đổi kích thước dữ liệu để lần từ triệu chứng đến vị trí mã.
- Hiểu vai trò của **JIT warm-up/inlining**, GC, native code và môi trường nhiều core trong kết quả đo.
- Đề xuất cách sửa có kiểm chứng: thay polling bằng blocking đúng cách, giảm độ phức tạp, hoist/cache công việc hợp lệ và dùng JMH hoặc phép đo ổn định để xác nhận lợi ích.

Ví dụ dùng **Java 17+**. Công cụ Linux được ghi rõ; tên giao diện JDK Mission Control (JMC) có thể khác giữa các phiên bản.

## 1. Đặt câu hỏi đúng trước khi tìm “dòng code chậm”

**CPU-bound** nghĩa là tốc độ thực thi bị giới hạn chủ yếu bởi lượng công việc CPU: nếu tăng sức tính toán hoặc giảm phép tính thì có thể cải thiện throughput/latency. **I/O-bound** hoặc **contention-bound** có thể có latency lớn nhưng CPU tương đối thấp vì thread đang đợi disk/network/lock.

Ba triệu chứng của đề bài khác nhau:

| Dạng vấn đề | Mô tả | Dấu hiệu thường gặp | Ví dụ |
|---|---|---|---|
| **Vòng lặp tốn CPU** | Chạy/quay liên tục, có thể không mang lại tiến triển tương xứng | Một hoặc vài thread thường xuyên ở trạng thái đang thực thi; samples lặp tại loop/predicate | `while (!ready) { }`, poll queue không sleep/block |
| **Thuật toán đắt** | Mỗi lần gọi thực hiện quá nhiều bước so với kích thước đầu vào | CPU tăng phi tuyến theo `n`; stack nóng ở so sánh, sort, regex, parse | Quét cặp bằng hai vòng lặp `O(n²)` thay vì đếm bằng hash |
| **Công việc lặp ngoài dự kiến** | Việc đúng nhưng được làm nhiều lần hơn nhu cầu nghiệp vụ | Counter invocation tăng đột biến, cùng stack xuất hiện nhiều request/lượt; có thể gây CPU, I/O hoặc allocation | Đọc config mỗi item, N+1 query, retry loop, scheduler chạy trùng |

Một đường code nằm trong profiler “nóng” chưa chắc là **nguyên nhân gốc**. Nó có thể là công việc hợp lệ đang xử lý tải cao, framework hot path, GC do allocation của đoạn code khác, hoặc một lời gọi bị nhân số lần do caller.

**Quan hệ cơ bản:**

```text
Tổng chi phí ≈ số lần thực hiện × chi phí mỗi lần
           + chi phí bộ nhớ / GC / đồng bộ / hệ thống
```

Cần trả lời đồng thời: **đoạn nào bận?** (where), **mỗi lần tốn bao nhiêu?** (cost), **vì sao chạy bao nhiêu lần?** (frequency), **lúc nào?** (time window), và **kết quả có cần thiết không?** (correctness).

## 2. CPU usage, CPU time và elapsed time không phải một

### 2.1. Ba đại lượng hay bị trộn lẫn

- **Process CPU usage**: tỷ lệ CPU mà *toàn tiến trình* tiêu thụ trong một khoảng. Tùy công cụ/quy ước, một process chạy đồng thời trên nhiều core có thể được hiển thị vượt **100%**.
- **Thread CPU time**: thời gian một thread thật sự được CPU chạy trong user mode và/hoặc kernel mode. Trên HotSpot có thể quan sát qua OS hoặc `ThreadMXBean` với **platform thread** nếu hỗ trợ/bật đo.
- **Wall-clock elapsed time**: thời gian thực từ lúc bắt đầu đến lúc kết thúc công việc; gồm CPU, chờ I/O, lock, sleep, pause, scheduler, GC.

Ví dụ một HTTP request mất **500 ms** do chờ network 480 ms và tính toán 20 ms. Request **chậm về wall time**, nhưng không phải 500 ms CPU. Ngược lại, một polling loop không chờ gì có thể giữ một core bận gần liên tục dù throughput bằng 0.

### 2.2. Quan sát CPU time trong mã Java

Trong **platform thread**, có thể lấy số đo bằng `java.lang.management.ThreadMXBean` khi JVM hỗ trợ:

```java
// Đoạn minh họa đặt xung quanh phần việc trong platform thread;
 // cần import java.lang.management.* và mã xử lý cụ thể.
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
if (bean.isCurrentThreadCpuTimeSupported()
        && bean.isThreadCpuTimeEnabled()) {
    long cpuBefore = bean.getCurrentThreadCpuTime();
    long wallBefore = System.nanoTime();

    // Chạy đoạn công việc cần quan sát tại đây.

    long wallNanos = System.nanoTime() - wallBefore;
    long cpuNanos = bean.getCurrentThreadCpuTime() - cpuBefore;
    System.out.println("wallNs=" + wallNanos + ", cpuNs=" + cpuNanos);
}
```

Đây là **snippet minh họa**, không phải file Java độc lập. Không tính `cpuNanos` nếu phương thức không được hỗ trợ hoặc trả `-1`. Độ phân giải nano-giây của API **không bảo đảm độ chính xác nano-giây**. `System.nanoTime()` dùng đo **chênh lệch** elapsed time, không phải thời gian lịch.

**Lưu ý Java hiện đại:** `ThreadMXBean` truyền thống báo CPU time cho **platform thread**, không phải virtual thread; `getThreadCpuTime(id)` có thể trả `-1` cho virtual thread, thread đã chết hoặc measurement chưa bật. Nếu workload dùng virtual thread, không suy luận “không có CPU” chỉ vì MXBean không cung cấp CPU time của virtual thread. Dùng JFR/OS/carrier profiling và cơ chế quan sát phù hợp.

## 3. Workflow điều tra từ bên ngoài vào trong

### Bước 1 — Xác nhận triệu chứng và phạm vi

Lấy cùng lúc **CPU theo process**, **CPU toàn host/container**, throughput, request rate, p95/p99 latency, error rate, allocation/GC, và số job đang xử lý.

- Máy 90% CPU nhưng JVM chỉ 5%: chưa có bằng chứng CPU hotspot trong JVM; kiểm tra process khác.
- JVM tăng CPU cùng lúc traffic tăng 4 lần: có thể chỉ là tải hợp lệ; cần so **CPU/request** hoặc **work/item**, không chỉ so CPU tuyệt đối.
- JVM tăng CPU khi traffic không đổi, latency/queue tăng: đáng nghi hot loop, thuật toán phi tuyến, retry amplification, leak task/job hoặc GC.
- Latency tăng mạnh nhưng JVM CPU thấp: ưu tiên I/O, lock contention, upstream dependency, starvation; không đổ lỗi thuật toán ngay.

### Bước 2 — Xem thread nào đang thực sự tiêu CPU

Trên **Linux**, khi biết PID JVM:

```bash
PID=12345                       # Thay bằng PID thực
top -H -p "$PID"               # Threads của tiến trình
ps -L -p "$PID" -o pid,tid,pcpu,stat,comm
```

`%CPU` có đơn vị/diễn giải phụ thuộc công cụ và khoảng lấy mẫu; không suy đoán core usage từ một ảnh chụp. Khi dùng `top -H`, cột PID của dòng thread thường tương ứng **TID/LWP** Linux.

Lấy thread dump gần cùng thời điểm:

```bash
jcmd "$PID" Thread.print -l
```

Với **platform thread**, có thể đối chiếu **TID thập phân** trong `top -H` với `nid` **hex** trong thread dump HotSpot:

```bash
TID=12346
printf '%x\n' "$TID"          # nid thường hiển thị dạng 0x303a...
```

Chỉ đối chiếu khi biết đang quan sát đúng PID/thread và runtime hỗ trợ kiểu định danh đó. Tên thread có thể giống nhau, ID đổi sau restart, và virtual-thread/carrier model làm liên kết OS thread ↔ tác vụ ứng dụng không còn một-một.

Lấy **nhiều thread dump cách nhau ngắn**, thay vì dựa vào một snapshot. Một stack lặp lại ở cùng vòng lặp, trong thread đang tiêu CPU, là manh mối mạnh hơn chỉ thấy chữ `RUNNABLE` một lần. `RUNNABLE` của Java **không đồng nghĩa** chắc chắn đang chiếm CPU tại thời điểm đó; nó cũng có thể bao gồm trường hợp đang ở native call.

### Bước 3 — Lấy CPU sampling bằng JFR

Khi đủ quyền truy cập JVM và có JDK:

```bash
jcmd -l
jcmd <PID> JFR.start name=CpuCheck settings=profile duration=60s filename=cpu-check.jfr
jcmd <PID> JFR.check
```

**Thay `<PID>` bằng PID thật**, không gõ nguyên văn dấu `< >`. Chọn khoảng thời gian **có tải/sự cố**; cấu hình `profile` thường thu nhiều mẫu profiling hơn `default` và có overhead cao hơn. Lệnh có `duration` sẽ tự kết thúc theo thời lượng, sau đó lưu recording theo filename. Với recording dài đang chạy, dùng `JFR.dump` để lấy ảnh chụp dữ liệu mà không dừng recording.

Trên máy có tệp:

```bash
jfr summary cpu-check.jfr
jfr print --events jdk.ExecutionSample cpu-check.jfr
```

`jfr print` có thể xuất ra rất nhiều dòng. `jdk.ExecutionSample` phải **được bật và có sự kiện thực sự phát** thì mới có mẫu; file ít mẫu/không có mẫu không chứng minh code không chạy.

Mở `cpu-check.jfr` trong **JDK Mission Control** và xem trang **Code / Method Profiling / Hot Methods / Call Tree** (tên tùy bản). Chọn time range đúng lúc CPU tăng. Đọc:

- **Hot Methods / execution samples**: phương thức hoặc stack thường xuyên xuất hiện khi CPU đang chạy mã; là **phân bố mẫu**, không phải bảng thời gian tuyệt đối của từng lời gọi.
- **Call Tree / Stack Trace**: ai gọi hot method; lần từ `for`/`while` hay thao tác đắt tới caller tạo ra tần suất.
- **`jdk.CPULoad` / `jdk.ThreadCPULoad`** nếu có: xu hướng tải JVM và thread; kiểm tra event có trong file và đủ mẫu.
- **GC / Compilation / Allocation**: phân biệt CPU chạy code nghiệp vụ với GC, JIT compiler hoặc chi phí cấp phát.
- **Threads / Locks / I/O**: kiểm tra phần thời gian chờ khi wall latency lớn.

Theo tài liệu Oracle, execution sampling tập trung vào thread đang chạy mã, thường không lấy mẫu những thread đang sleep, chờ I/O hoặc lock. **Ít CPU samples có thể là vì thread đang đợi**, chứ không phải vì request nhanh. Đọc stack và time window cùng với OS metrics.

### Bước 4 — Chuyển stack nóng thành giả thuyết có thể kiểm chứng

Một stack ví dụ:

```text
OrderService.search()
  -> OrderMatcher.findDuplicates()
     -> OrderMatcher.comparePairs()
```

Nếu `comparePairs()` chiếm nhiều mẫu, không dừng ở tên method. Hỏi:

1. `n` là bao nhiêu? Có hai vòng lặp lồng nhau, regex backtracking, parse hay sort lặp?
2. Có cache/index/hash map phù hợp hơn thuật toán duyệt toàn bộ không?
3. Method này được gọi bao nhiêu lần mỗi request/batch?
4. Có caller retry, scheduled task chạy đôi, cache miss hoặc pipeline lặp khiến cost bị nhân lên không?
5. Có giá trị đầu ra/side effect nào bắt buộc giữ nguyên nếu tối ưu không?

Bổ sung **counter cho số lời gọi, số item duyệt, số pair so sánh, retry count**, rồi so với số nghiệp vụ kỳ vọng. Dữ liệu này thường giúp phân biệt “một lời gọi quá đắt” với “một lời gọi bình thường nhưng bị gọi quá nhiều”.

## 4. Nhận diện vòng lặp tốn CPU

### 4.1. Busy spin: chờ nhưng không thật sự ngủ

Ví dụ đối lập:

```java
// Minh họa ANTI-PATTERN, không phải chương trình standalone:
while (!ready.get()) {
    // Không có blocking/wait; liên tục đọc cùng trạng thái.
}
```

Nếu `ready` không chuyển `true`, vòng lặp chạy hàng triệu lượt và có thể chiếm gần trọn một core dù **không tạo tiến triển**. Dùng `Thread.onSpinWait()` có thể cung cấp gợi ý cho CPU trong một số spin loop có chủ đích, nhưng **không biến busy spin thành blocking**; nó vẫn tiêu tài nguyên CPU.

Phương án phù hợp hơn khi thời gian đợi không cực ngắn là primitive có khả năng **chờ tín hiệu**:

```java
// Minh họa: cần khai báo latch và bên phát tín hiệu;
 // đây là đoạn xử lý, không phải chương trình độc lập.
CountDownLatch readySignal = new CountDownLatch(1);

// Thread cần chờ:
readySignal.await();

// Thread hoàn tất khởi tạo:
readySignal.countDown();
```

Ở code thực, bạn có thể dùng `BlockingQueue.take()`, `Semaphore.acquire()`, `Lock/Condition.await()`, `CompletableFuture` hoặc I/O bất đồng bộ. Chọn đúng primitive và xử lý **interrupt/timeout/cancellation**; đừng đổi sang `Thread.sleep(1)` như một bản sửa mặc định vì vừa còn poll vừa đổi latency.

### 4.2. Vòng lặp có điều kiện thoát sai hoặc đầu vào bất thường

Ví dụ thường thấy:

- `while` với điều kiện luôn đúng do biến trạng thái không được cập nhật/không bảo đảm visibility giữa thread.
- Lỗi retry: kết quả lỗi lập tức retry không giới hạn, không backoff/jitter/circuit breaker.
- Consumer đọc queue rỗng và thử lại liên tục.
- Poll một trạng thái với thời lượng rất nhỏ và không có budget.
- Vòng lặp có tiến triển nhưng input tăng vô hạn do bug.

Cách phân biệt: xem **loop-iteration counter, retry rate, trạng thái thoát, kết quả mỗi lượt** và **thread CPU**; đặt một lần sampling/timebox. Sửa đúng logic termination và synchronization trước khi tối ưu instruction. Với retry, giới hạn attempt/budget, backoff có kiểm soát và tránh tạo storm khi dependency lỗi.

### 4.3. Khi spin có thể là chủ ý

Một số cơ chế cực thấp latency có thể spin rất ngắn trong vùng đã được thiết kế và benchmark cụ thể. Nhưng cần chứng minh lợi ích latency so với việc chiếm core, xác định **bounded spin** và fallback sang blocking. Không suy rộng tối ưu của runtime/lock-free library sang loop nghiệp vụ thông thường.

## 5. Thuật toán đắt: dùng work units và độ phức tạp để giải thích

### 5.1. Ví dụ tìm mọi cặp giá trị bằng nhau

Giả sử cần đếm các cặp chỉ số `(i, j)` với `i < j` và `a[i] == a[j]`.

Cách trực tiếp là hai vòng lặp:

```java
for (int i = 0; i < values.length; i++) {
    for (int j = i + 1; j < values.length; j++) {
        if (values[i] == values[j]) {
            pairs++;
        }
    }
}
```

Đây là **đoạn minh họa**, biến `values` và `pairs` phải tồn tại. Có đúng `n(n - 1)/2` phép so sánh, tức `O(n²)`. Khi `n` gấp đôi, số cặp so sánh **xấp xỉ gấp bốn** (không phải luôn chính xác 4 do hệ số và phần `-1`).

Thay vì so mọi cặp, dùng map ghi số lần giá trị đã xuất hiện. Khi đọc một giá trị `v`, nếu đã thấy `k` lần, có thêm đúng `k` cặp mới. Như vậy chỉ cần **một lượt duyệt**, kỳ vọng `O(n)` nếu hash map có thao tác trung bình hiệu quả, đổi lại dùng bộ nhớ bổ sung theo số giá trị khác nhau.

### 5.2. Khi `O(n log n)`/`O(n²)` không đủ để ra quyết định

Không phải cứ thấy hai vòng lặp là bug. Nếu đầu vào luôn rất nhỏ hoặc một thuật toán cần chính xác mọi cặp, chi phí có thể chấp nhận được. Ngược lại, một biểu thức regex hoặc thuật toán backtracking có thể chạy cực đắt ngay cả khi mã chỉ có một lời gọi. Hãy kiểm tra:

- Giới hạn kích thước và hình dạng dữ liệu **thực tế**.
- Worst case và dữ liệu bất thường; ví dụ regex có thể bị **catastrophic backtracking** trên một số input.
- Số truy vấn DB hoặc network phát sinh trong loop (N+1): latency có thể tốn chủ yếu ở I/O, dù code nhìn như `O(n)`.
- Số lần tạo object tạm; allocation/GC cũng tiêu CPU.
- Trade-off đúng đắn của HashMap: hashCode/equals, collision, memory và độ ổn định key; độ phức tạp trung bình không phải bất biến của mọi input.

Phép thử tốt là giữ **kết quả nghiệp vụ không đổi**, đo `n` và work units, sau đó so thời gian CPU/wall ở workload đại diện. Tránh tối ưu code nhỏ không nằm trên hot path.

## 6. Công việc lặp ngoài dự kiến: “đúng một lần” nhưng bị gọi quá nhiều

Trong hệ thống thực, lỗi không nhất thiết nằm trong method nóng:

```text
1 request
  -> 100 items
     -> loadRules() mỗi item
     -> normalize() mỗi item dù input giống nhau
     -> lookupUser() nhiều lần cho cùng key
     -> retry operation không giới hạn khi lỗi
```

Đây là **sơ đồ**, không phải Java source. Mỗi `loadRules` có thể nhanh trong microbenchmark, nhưng khi gọi hàng nghìn lần/request và nhân với hàng trăm request/giây, CPU, allocation, lock contention hoặc I/O đều tăng.

Những dạng cần điều tra:

- **Loop-invariant work:** kết quả một phép tính/parse/config trong suốt batch không đổi nhưng bị tạo lại ở mỗi vòng. Có thể tính **trước vòng lặp**.
- **N+1 access:** nhiều truy vấn dữ liệu cho từng item thay vì batch fetch/cache hợp lệ.
- **Cache misses** bất thường do key/TTL sai hoặc invalidate quá rộng; cần xem hit/miss và cost.
- **Duplicate scheduling:** cùng job được chạy ở nhiều instance hoặc bị trigger song song ngoài dự kiến.
- **Retry amplification:** dependency lỗi làm số lần thực hiện tăng gấp nhiều lần; cần giới hạn budget và idempotency.
- **Repeated transformation/serialization:** parse cùng JSON, compile cùng regex, map cùng object qua nhiều lớp.
- **Recursive traversal không memoization:** xử lý lại cùng subproblem trong cây/đồ thị (ví dụ Fibonacci naïve hoặc dynamic programming thiếu memoization).

**Không cache một cách vô điều kiện:** một dữ liệu có thể thay đổi theo tenant/request, cần đúng isolation, TTL/invalidation, thread-safety, bộ nhớ và yêu cầu freshness. Chuyển `loadRules()` ra khỏi loop chỉ hợp lệ khi rules thật sự **không cần được đọc lại cho mỗi item**. Với side effects, việc bỏ số lần gọi có thể thay đổi behavior.

### Bằng chứng của duplicated work

Đặt counter/trace tại entry point: `jobsStarted`, `batchSize`, `configLoads`, `queriesPerRequest`, `retriesPerKey`, `cacheHits/cacheMisses`. So sánh tỷ lệ kỳ vọng; ví dụ một config load/batch nhưng quan sát **3.000 loads cho 3.000 items** là tín hiệu mạnh hơn chỉ nhìn stack của `loadRules`.

## 7. Java 17+ runnable: cùng kết quả, khác độ phức tạp và số lần gọi

Ví dụ sau chứng minh **hai kiểu bất thường bằng con số đếm xác định**: so cặp `O(n²)` so với đếm bằng hash map, và tải rules cho từng request thay vì một lần/batch. Nó còn có chế độ tạo **CPU hot loop có chủ đích** để bạn dùng JFR profiler.

Tạo tệp **`CpuPatternDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CpuPatternDemo {
    private static volatile long blackhole;

    private record Result(long pairs, long operations) {}

    private static Result quadratic(int[] input) {
        long pairs = 0;
        long comparisons = 0;
        for (int i = 0; i < input.length; i++) {
            for (int j = i + 1; j < input.length; j++) {
                comparisons++;
                if (input[i] == input[j]) pairs++;
            }
        }
        return new Result(pairs, comparisons);
    }

    private static Result linear(int[] input) {
        Map<Integer, Integer> previous = new HashMap<>();
        long pairs = 0;
        long visits = 0;
        for (int value : input) {
            int seen = previous.getOrDefault(value, 0);
            pairs += seen;
            previous.put(value, seen + 1);
            visits++;
        }
        return new Result(pairs, visits);
    }

    private static int loadRules(AtomicInteger calls) {
        calls.incrementAndGet();
        return 7;
    }

    private static void profileHotLoop(int seconds) {
        if (seconds < 1 || seconds > 60) {
            throw new IllegalArgumentException("seconds must be 1..60");
        }
        long until = System.nanoTime() + TimeUnit.SECONDS.toNanos(seconds);
        long accumulator = 1;
        while (System.nanoTime() < until) {
            for (int i = 0; i < 100_000; i++) {
                accumulator = (accumulator * 1664525L + 1013904223L) & 0x7fffffffL;
            }
            blackhole = accumulator;
        }
        System.out.println("Profile run done");
    }

    public static void main(String[] args) {
        if (args.length == 2 && "profile".equals(args[0])) {
            profileHotLoop(Integer.parseInt(args[1]));
            return;
        }

        int n = 6000;
        int distinct = 200;
        int[] input = new int[n];
        for (int i = 0; i < input.length; i++) {
            input[i] = i % distinct;
        }

        Result slow = quadratic(input);
        Result fast = linear(input);
        if (slow.pairs() != fast.pairs()) {
            throw new AssertionError("Results differ");
        }

        System.out.println("Equal pairs: " + slow.pairs());
        System.out.println("Quadratic comparisons: " + slow.operations());
        System.out.println("Linear visits: " + fast.operations());

        int requests = 3000;
        AtomicInteger repeatedCalls = new AtomicInteger();
        long repeatedTotal = 0;
        for (int i = 0; i < requests; i++) {
            repeatedTotal += loadRules(repeatedCalls);
        }

        AtomicInteger cachedCalls = new AtomicInteger();
        int rule = loadRules(cachedCalls);
        long cachedTotal = 0;
        for (int i = 0; i < requests; i++) {
            cachedTotal += rule;
        }

        System.out.println("Repeated rule loads: " + repeatedCalls.get());
        System.out.println("Once-per-batch rule loads: " + cachedCalls.get());
        System.out.println("Same rule result: " + (repeatedTotal == cachedTotal));
    }
}
```

### 7.1. Chạy bài toán so sánh số thao tác

```bash
javac CpuPatternDemo.java
java CpuPatternDemo
```

**Stdout chính xác** của đường chạy mặc định:

```text
Equal pairs: 87000
Quadratic comparisons: 17997000
Linear visits: 6000
Repeated rule loads: 3000
Once-per-batch rule loads: 1
Same rule result: true
```

Giải thích:

- `n = 6000`, có `200` giá trị khác nhau lặp đều, mỗi giá trị xuất hiện `30` lần. Tổng cặp trùng: `200 × 30 × 29 / 2 = 87.000`.
- Cách `quadratic` duyệt `6000 × 5999 / 2 = 17.997.000` cặp, dù chỉ có 87.000 cặp bằng nhau.
- Cách `linear` duyệt đúng 6.000 input, cập nhật `Map` để tính số cặp mới; hai cách trả **cùng kết quả**.
- `loadRules` ở đây chỉ trả một số cố định, **không phải thao tác cấu hình tốn CPU thực**. Counter minh họa **3.000 calls so với 1 call**; nó không chứng minh tiết kiệm CPU cụ thể bao nhiêu trong production.
- Chỉ chuyển việc load ra trước vòng lặp khi rules/side effect cho phép; nếu cấu hình thay đổi theo request thì cách cache này có thể **sai nghiệp vụ**.

**Không dùng 17.997.000/6.000 như tỷ số tăng tốc CPU.** Số thao tác ở hai giải thuật có *đơn vị khác nhau* (so sánh số nguyên vs truy cập hash map) và JIT, allocation, memory locality khác nhau. Nó chứng minh **hình dạng công việc**, không phải tốc độ chính xác.

### 7.2. Tạo JFR để nhìn thấy CPU hot loop

Chạy **chế độ profiling** của cùng chương trình:

```bash
java -XX:StartFlightRecording=filename=cpu-pattern.jfr,settings=profile,dumponexit=true CpuPatternDemo profile 15
jfr summary cpu-pattern.jfr
jfr print --events jdk.ExecutionSample cpu-pattern.jfr
```

Chương trình chạy loop tính toán khoảng **15 giây**, sau đó in:

```text
Profile run done
```

Với `dumponexit=true`, JVM dump recording khi thoát bình thường; file `cpu-pattern.jfr` có thể mở bằng JMC để xem Code/Hot Methods/Call Tree. Mã dùng biến `blackhole` dạng `volatile` để kết quả từ các chunk tính toán là observable, giảm khả năng JIT loại hẳn phép tính như dead code. Nó là **workload nhân tạo dùng để học profiler**, không phải đoạn code nên đưa vào ứng dụng thật.

Một lần chạy kiểm tra bằng OpenJDK 24 với **`profile 2`** đã tạo file hợp lệ và `jfr summary` ghi nhận **188 `jdk.ExecutionSample`**; số mẫu thay đổi theo JDK, máy, thời gian, CPU load và cấu hình. **Không coi 188 là kết quả cố định** hoặc cam kết phải có mẫu giống hệt. Nếu file không có `jdk.ExecutionSample`, kiểm tra template, thời lượng và công cụ trước khi suy luận về mã.

Khi mở recording, chọn đoạn có CPU loop, tìm phương thức `profileHotLoop` trong sampled stacks. Nếu profiler cho thấy `Thread.sleep` hoặc hành vi khác chiếm wall time ở bài toán thật, đừng dùng CPU flame graph để suy ra thời gian blocked.

### 7.3. Vì sao không in “nhanh hơn X ms” làm output chuẩn?

`System.nanoTime()` hoặc thời gian CPU đọc từ MXBean phụ thuộc máy, JIT warm-up, OS scheduling, độ nóng CPU, GC và dữ liệu đầu vào. Một lần chạy nhanh/chậm không phải benchmark có ý nghĩa. Để đo hiệu quả thật:

1. Chuẩn bị input đại diện, nhiều kích thước và phân bố (ít/nhiều key trùng).
2. **Warm up** JVM/JIT; chạy nhiều vòng đo sau warm up.
3. Giữ kết quả luôn được dùng/kiểm tra để tránh dead-code elimination.
4. Tách riêng kết quả đúng, operations count, throughput, CPU time, wall time, allocation và p95/p99 khi cần.
5. Dùng **JMH** cho microbenchmark Java; đánh giá end-to-end trên tải gần thực tế để bảo đảm cải thiện vẫn giữ nguyên.

## 8. Đọc “CPU nóng” mà không bị JIT, GC và profiler đánh lừa

### 8.1. JIT warm-up và code shape

HotSpot/JIT có thể tối ưu code sau một số lần thực thi: **inlining**, loop optimizations, escape analysis, constant folding, hoặc deoptimization khi giả định không còn đúng. Vì thế:

- Giai đoạn startup/warm up có thể có CPU cho **JIT compilation** và class loading; không quy tất cả CPU đó cho vòng lặp nghiệp vụ.
- Method xuất hiện trong stack profiler có thể bị **inline**; tên/stack được tái dựng phụ thuộc profiler và JDK. Không mặc định một phương thức biến mất khỏi sample là nó không được gọi.
- Hai benchmark đơn giản chạy liên tiếp có thể bị bias bởi thứ tự thực thi, JIT nóng dần và cache; đừng khẳng định thuật toán nào nhanh hơn chỉ từ một snapshot.
- Code hot chưa chắc nên sửa: cần đo **chi phí liên quan đến mục tiêu SLO** và khả năng giữ nguyên semantics.

Dùng JFR event về JVM compilation nếu cần, cùng thay đổi theo thời gian, không cần bật logging JIT quá nhiều trên production chỉ để nhìn một method.

### 8.2. Allocation và garbage collector cũng tiêu CPU

Một loop tạo nhiều object ngắn hạn có thể đẩy allocation rate/GC lên cao. Phương pháp:

1. Kiểm tra GC pause/time, số collection, allocation rate trong JFR/JMC.
2. Tìm **allocation call site**; xem có parse, boxing hoặc buffer mới ở mỗi vòng hay không.
3. Phân biệt CPU do GC với thread nghiệp vụ và CPU do JIT/native.
4. Thay đổi cấu trúc code để giảm **công việc cần thiết**, không vội chỉnh heap/GC flags nếu gốc là allocation vô ích.

Nếu một request tốn 200 ms vì chờ network, việc allocation giảm một ít có thể không xử lý được p99 latency. Ngược lại, khi CPU GC cao do tạo hàng triệu object tạm từ loop, sửa code có thể quan trọng hơn nâng tài nguyên.

### 8.3. Native code, synchronization và virtual threads

- JFR `jdk.ExecutionSample` chủ yếu cho biết nơi Java thread được sampling lúc chạy; native hotspot có thể cần `jdk.NativeMethodSample` hoặc profiler OS/native chuyên dụng, tùy platform/recording.
- Một `RUNNABLE` Java thread trong native I/O không đủ để kết luận CPU đang đốt trong Java.
- Với **virtual threads**, OS quan sát carrier/platform threads. Đừng đối chiếu 1:1 virtual thread ID với Linux TID; cần công cụ JFR, thread dump tương thích virtual thread và đo ở nơi thích hợp.
- Lock contention khiến wall time tăng nhưng nhiều thread **không** tiêu CPU; spin lock do ứng dụng tự viết lại có thể tiêu CPU thật. Nhận dạng hai trường hợp trước khi chọn cách sửa.

## 9. Phân tích tình huống thực tế

| Hiện tượng | Giả thuyết ưu tiên | Cách chứng minh | Hướng xử lý |
|---|---|---|---|
| Một core gần 100%, queue rỗng, cùng stack `while` lặp trong dump | Busy spin không có progress | CPU thread, JFR samples, loop count, queue-depth | Thay bằng blocking/signal/timeout có điều kiện |
| CPU tăng rất mạnh khi danh sách từ 1.000 lên 10.000 items | Thuật toán `O(n²)` hoặc worse | Đếm số phép so, profile inner loop, scaling theo `n` | Chọn map/index, batch xử lý, tránh scan trùng |
| CPU tăng nhưng request rate không đổi sau release | Retry amplification, scheduler trùng, cache miss, hot loop | Request/job/retry counters, thread profile, diff code | Giới hạn retry, idempotency, dedupe, sửa cache |
| `loadRules` xuất hiện nhiều trong samples | Loop-invariant work bị gọi lặp | `configLoads / requests` hoặc `/ batch` cao bất thường | Hoist/cache có kiểm chứng freshness và side effects |
| CPU JVM cao cùng GC nhiều và allocation rate tăng | Tạo object trong loop, churn | JFR Allocation/GC + CPU samples | Giảm allocation dư, cân nhắc bộ nhớ/GC sau |
| JVM CPU thấp nhưng latency cao | Chờ I/O, lock, downstream | JFR Thread/Lock/I/O event, traces, timing | Sửa dependency/contended resource; không tối ưu CPU |
| CPU host cao, JVM CPU thấp | Process/container khác dùng CPU | Host/process/cgroup metrics | Xử lý đúng owner của CPU |
| Profile thay đổi mạnh giữa lần đầu và lần sau | JIT warm-up, class loading, GC, cache | Warm-up, JFR compilation, thử lặp JMH | Đo sau warm-up; tránh kết luận từ một lần |

### Case A — Polling loop chiếm core

**Trước:** một worker dùng `while(queue.isEmpty()) { }`. Trong giờ rảnh, CPU vẫn cao; OS xác định thread nóng, JFR và thread dumps liên tiếp thấy worker ở cùng vòng lặp. **Sau:** worker chờ `BlockingQueue.take()`, xử lý phần tử khi có, bảo toàn cơ chế shutdown/cancellation. Cần đo lại CPU idle và độ trễ khi có item; không chỉ xác nhận CPU giảm mà bỏ quên responsiveness.

### Case B — Thuật toán tăng theo kích thước input

**Trước:** method so sánh mọi cặp sản phẩm để tìm duplicate: với 6.000 items có 17.997.000 comparisons. **Sau:** đếm bằng map với 6.000 lượt duyệt kỳ vọng, trả đúng 87.000 cặp trùng với dữ liệu ví dụ. Cần kiểm tra tính đúng đắn của `equals/hashCode`, phân bố input và memory overhead; kết quả trên data nhỏ có thể không phản ánh workload lớn.

### Case C — Caller lặp thao tác, không phải callee chậm

**Trước:** 3.000 request/items đều gọi `loadRules()` dù batch chỉ cần một phiên bản rules. **Sau:** một lần load/batch và chia sẻ kết quả khi invariant đúng. Counter giảm từ 3.000 xuống 1; CPU có thể giảm nếu load thật đắt, nhưng bài học chính là **chẩn đoán tần suất bất thường**. Nếu rules phân biệt tenant hoặc thay đổi tức thời, cache batch bừa bãi là bug nghiêm trọng.

### Case D — Retry storm trong incident

**Trước:** dependency trả lỗi, một lệnh retry ngay lập tức và lặp mã hóa/signature/parse payload nhiều lần, khiến CPU tăng trong lúc success rate bằng 0. **Sau:** retry budget, exponential backoff có jitter, giới hạn concurrency, circuit breaker/idempotency phù hợp. Theo dõi `attempts / original request`, CPU/request, queue và error rate; CPU thấp đi **không đủ** nếu bạn vô tình bỏ luôn yêu cầu xử lý hợp lệ.

## 10. Cách kết luận root cause bằng bằng chứng

Một báo cáo kỹ thuật nên phân biệt **quan sát**, **giả thuyết**, **thí nghiệm** và **kết quả**:

```text
Quan sát: JVM CPU tăng từ mức cơ sở khi số items/batch tăng,
          nhưng request rate gần như không đổi.

Bằng chứng: CPU samples tập trung ở OrderMatcher.comparePairs;
            log/counter cho thấy n = 6000 và ~18 triệu comparisons.

Giả thuyết: Thuật toán quét cặp O(n²) là phần việc CPU dư.

Thử nghiệm: Thay bằng phép đếm dựa trên Map, giữ kết quả nghiệp vụ;
            chạy correctness tests + workload tương đương sau warm-up.

Kết luận: So CPU/batch, throughput, p95/p99, allocation, GC trước/sau.
          Chỉ gọi là cải thiện khi số đo và tính đúng đắn đều đạt.
```

Đừng trộn các bước: việc method ở top Hot Methods mới là **chỉ báo vị trí**, chưa tự chứng minh **vì sao** nó chạy nhiều hoặc liệu sửa nó có giúp người dùng.

### Checklist thực hiện

1. Xác định **process và time window** CPU cao; so CPU process với CPU host, throughput và request rate.
2. Lấy **JFR `profile`** trong lúc có tải; xem Hot Methods/Call Tree, phân biệt execution sample và latency blocked.
3. Nếu cần, map Linux hot TID với **platform thread** trong `jcmd Thread.print`, lấy nhiều mẫu liên tiếp.
4. Tại điểm nóng, kiểm tra **loop termination/progress**, số vòng, `n`, số lời gọi, retry, cache hit/miss.
5. Phân biệt **thuật toán đắt mỗi lần** với **công việc lặp nhiều lần**, GC/JIT/OS contention.
6. Sửa có điều kiện **giữ kết quả đúng**; tránh cache/hoist làm stale dữ liệu hoặc mất side effect.
7. Kiểm chứng bằng tests, workload cùng điều kiện, JFR/OS measurements sau warm-up và benchmark JMH nếu đo vi mô.
8. Báo cáo CPU/request, tổng CPU, throughput, latency và memory/GC; đừng dùng một phần trăm CPU đơn lẻ.

### Câu hỏi tự kiểm tra

- Vì sao request chậm 500 ms chưa chắc tiêu 500 ms CPU?
- Tại sao ba thread dumps liên tiếp cùng chỉ vào một vòng lặp thường hữu ích hơn một snapshot `RUNNABLE`?
- Với `n = 6000`, tại sao hai vòng lặp so tất cả cặp có 17.997.000 comparisons, nhưng phép đếm bằng Map có thể chỉ duyệt 6.000 items?
- Vì sao một method xuất hiện rất nhiều trong JFR samples chưa chắc chính nó có thuật toán sai?
- Tại sao số `loadRules` calls giảm 3.000 → 1 chưa chứng minh “CPU nhanh hơn 3.000 lần”?
- Khi CPU JVM cao, làm sao phân biệt CPU của application, JIT compiler, GC và native code?
- Với virtual threads, vì sao `ThreadMXBean` và OS TID không trực tiếp biểu diễn CPU của từng virtual thread?

## Tài liệu tham khảo

- [Oracle Java SE 17 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html): CPU load, execution samples, Method Profiling/Hot Methods và diễn giải stack.
- [Oracle JDK Mission Control User Guide — Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html): tạo/open recording, xem Code/Memory/Threads và chọn event.
- [Java SE 21 — ThreadMXBean API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread CPU time, khả năng hỗ trợ, điều kiện enabled và giới hạn với virtual threads.
- [Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `Thread.print`.
- [Java SE 21 — `jfr`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): đọc, lọc và tóm tắt các event trong `.jfr`.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): harness cho microbenchmark Java, giảm các sai lầm về warm-up, JIT và tối ưu hóa compiler.
