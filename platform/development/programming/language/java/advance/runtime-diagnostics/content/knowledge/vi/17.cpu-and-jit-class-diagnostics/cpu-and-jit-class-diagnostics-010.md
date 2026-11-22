# 17.10 Phân biệt thay đổi do JIT hoặc tải với bằng chứng của một lỗi hiệu năng

## Mục tiêu bài học

Khi CPU của một ứng dụng Java tăng hoặc p95 latency xấu đi, có ba cách giải thích rất khác nhau:

1. **JIT, class loading và warm-up:** JVM đang tải lớp, thu profile, biên dịch và tối ưu các method; vì vậy cùng một mã và cùng tải có thể nhanh/chậm khác nhau theo thời điểm.
2. **Tải hoặc tài nguyên thay đổi:** số request, concurrency, payload, cache hit, CPU quota, queue hay dependency latency đã đổi; p95 có thể tăng khi bão hòa dù không có thay đổi mã.
3. **Lỗi hiệu năng (regression) có bằng chứng:** ở điều kiện so sánh tương đương, cùng chức năng, một thay đổi làm tăng công việc hoặc thời gian chờ, kết quả lặp lại và tìm được cơ chế gây chênh lệch.

Bài này hướng dẫn **tách tín hiệu của JVM và tải khỏi chứng cứ của bug**, không gắn nhãn “regression” chỉ dựa trên một biểu đồ CPU. Người học sẽ biết đặt giả thuyết kiểm chứng được, dùng JFR/JIT/class metrics, tổ chức thí nghiệm A/B, đọc một ví dụ Java 17+ chạy được, và viết báo cáo với mức tin cậy phù hợp.

## 1. Chênh lệch hiệu năng không đồng nghĩa lỗi

**Latency** là thời gian tường (wall-clock) từ khi request bắt đầu đến khi trả kết quả. Nó có thể chứa **CPU computation**, **queue wait**, GC pause, lock contention, sleep, I/O, network, database và scheduling. **CPU time** đo thời gian CPU thực sự dùng chạy thread, không bao gồm phần lớn thời gian chờ.

```text
Latency của request
  = queue wait + application service time + các thời gian chờ liên quan
Application service time
  = CPU work + GC/lock/I/O/dependency/scheduling delays (tùy đường đo)

Process CPU usage cao
  có thể do nhiều request hơn, mỗi request đắt hơn,
  JIT/GC/background work, hoặc busy-loop.
```

Đừng suy:

- **CPU tăng → lỗi:** 600 RPS thường cần nhiều tổng CPU hơn 300 RPS.
- **CPU thấp → ứng dụng nhanh:** hệ thống chờ DB/lock có thể CPU thấp nhưng p95 rất cao.
- **p95 tăng → mỗi method chậm:** khi queue dài, request mất thêm thời gian đợi dù code phục vụ không đổi.
- **Method X có 60% sample CPU → X vừa chậm 60%:** tỉ lệ mẫu là phần của tổng mẫu trong cửa sổ, không phải độ trễ tuyệt đối của method.
- **Sau restart khác tốc độ → chắc là JIT bug:** JVM uptime, class initialization, cache và compiler tier chưa tương đương.

### Bộ số đo tối thiểu phải đọc cùng nhau

| Khía cạnh | Metrics | Mục đích |
| --- | --- | --- |
| Người dùng | p50/p95/p99, error/timeout, SLO | Xác nhận triệu chứng |
| Offered workload | arrival RPS, concurrency, request mix, payload size | Biết có thực sự cùng tải không |
| Served workload | completed RPS, queue depth, active workers, rejection | Biết hệ thống đang phục vụ hay từ chối |
| CPU | process/thread CPU time, CPU%, CPU quota, cgroup throttling | Phân biệt dùng CPU với chờ CPU |
| JVM | uptime, class load/unload, JIT compilation, code cache, GC pauses | Nhận diện warm-up và overhead JVM |
| Ngoài CPU | lock waits, I/O, database/network, cache hit | Tránh đổ lỗi sai cho JIT |

Chỉ khi biết đơn vị, mẫu số và cửa sổ đo, mới có thể so hai giá trị.

## 2. Giả thuyết 1 — Warm-up/JIT/Class loading

HotSpot Java có interpreter và JIT. **Tiered compilation** thường bật mặc định trên Server VM: JVM ban đầu chạy mã ở mức ít tối ưu hơn và thu thông tin về call sites, branches, type profiles; C1/C2 hoặc compiler tương ứng dần tạo machine code được tối ưu. Trong ứng dụng Java 17+/21, một tiến trình vừa start có thể trải qua:

1. **Class load/link/init:** framework khởi tạo, reflection, proxy, lambda, serialization và class loader nạp lớp.
2. **Profile collection:** các hot paths được gọi lặp lại; JVM biết các type và nhánh thường gặp.
3. **Compilation/inlining:** compiler tạo optimized code; code cache và compiler threads tiêu thụ tài nguyên.
4. **Steady state:** cùng workload thường có throughput/latency ổn định hơn sau warm-up.
5. **Profile thay đổi:** khi workload chuyển dạng, JVM có thể **deoptimize** rồi biên dịch lại. Deoptimization là cơ chế thích nghi bình thường, **không tự động là bug**.

### Dấu hiệu thường thấy

| Quan sát | Giả thuyết JIT/class loading | Cách xác minh |
| --- | --- | --- |
| p95 xấu lúc đầu rồi giảm ở RPS cố định | Warm-up và nạp lớp | Plot latency theo uptime và compilation/class load |
| Compiler threads ngắn hạn dùng CPU | Nhiều method được compile | JFR compilation events, compiler queue, log biên dịch |
| Khi lần đầu gọi endpoint X mới chậm | Lazy initialization/class load/cache miss | Đối chiếu class load, first-hit logs, cache warm-up |
| Thay đổi request mix gây chậm ngắn hạn | Type profile/compiled code thay đổi | JIT/compiler data và cùng workload replay |
| Code cache sát giới hạn | Compilation có thể bị ảnh hưởng | `Compiler.codecache` và JVM logs |

**Quan trọng:** nếu sản phẩm có cold-start SLO, warm-up gây p95 quá cao **vẫn là một vấn đề hiệu năng cần sửa**. “Giải thích bằng JIT” không có nghĩa “không có tác động người dùng”; nó chỉ phân biệt với regression của steady-state business code.

Không thấy compiler activity ở một thời điểm không chứng minh trước đó không có compilation. Không thấy class load event trong JFR cũng chưa đủ kết luận không nạp lớp: event có thể không được bật hoặc cửa sổ thu không bao phủ hoạt động.

### Khác nhau giữa class loading và class loader leak

Số `totalLoadedClassCount` là **tích lũy**, nên tăng ngay cả khi class có thể unload về sau. Số class đang loaded và số class unload phải đọc riêng. Dynamic proxies/lambdas/plugin reload có thể hợp lệ, nhưng nếu mỗi lần reload đều giữ loader cũ và metaspace tăng, đó là giả thuyết **retention** cần điều tra riêng. Dù vậy, số class tăng không tự chứng minh hot-path CPU regression.

## 3. Giả thuyết 2 — Tải tăng, CPU bão hòa và queueing

Giả sử ứng dụng chạy 300 request/giây với 45% CPU, p95=70ms. Khi lên 650 request/giây, CPU gần quota và p95=280ms. Các số này **chỉ là giả định minh họa**.

Có thể lý giải không cần một commit lỗi:

- **Làm nhiều việc hơn:** RPS cao hơn khiến tổng CPU time tăng, kể cả khi CPU dùng cho mỗi request giữ nguyên.
- **Queueing tăng mạnh gần saturation:** hệ thống có thể xử lý từng request với cùng CPU work nhưng request phải chờ lâu hơn vì arrival rate vượt hoặc gần service capacity.
- **Request mix đổi:** một endpoint nặng chiếm tỉ lệ lớn hơn, payload lớn hơn, key cardinality cao hơn hoặc cache miss nhiều hơn.
- **Cgroup throttling:** container được cấp quota CPU nhỏ hơn trước, làm thread bị trì hoãn mặc dù đồ thị host CPU không cao.
- **Host contention:** một tiến trình khác dùng CPU; JVM bị cạnh tranh tài nguyên.

### Tại sao CPU% dễ gây hiểu lầm?

Một công cụ trên Linux có thể hiển thị 100% khi **một logical core** bận hoàn toàn; dashboard khác chuẩn hóa theo tổng số cores hoặc quota nên 100% tương ứng mức sử dụng ngân sách CPU đầy đủ. Cần ghi **đơn vị và mẫu số** của metric, số vCPU được phép dùng và CPU throttling.

### Ước tính CPU-seconds/request

Ở một cửa sổ tương đối ổn định:

```text
CPU-seconds per completed request
≈ Δ(process CPU time tính bằng giây) / số request hoàn thành

Ví dụ giả định:
  120 CPU-seconds trong 60 giây,
  12.000 request hoàn thành
  => khoảng 0,010 CPU-second/request = 10ms CPU/request.
```

Đây là **trung bình cấp process**, gồm JVM GC/JIT/background work và không phải CPU time chính xác của một request. Chỉ so khi operation mix, error rate, retries và background load tương đương. Nếu CPU/req gần như ổn nhưng tổng CPU tăng theo RPS, chưa thể gọi đó là regression CPU; nếu CPU/req tăng khi RPS giữ nguyên thì cần điều tra chi phí thực thi/GC/JIT/tập dữ liệu.

### Thí nghiệm đường cong tải

Đừng chỉ so A ở 300 RPS với B ở 650 RPS. Hãy chạy cả A và B lần lượt ở 300, 450, 600 RPS với cùng request mix, concurrency policy, payload và resource quota. Plot throughput completed, error, p95, CPU/req, backlog. Khi một phiên bản đạt saturation sớm hơn **ở cùng điều kiện**, đó là bằng chứng đáng tin hơn về giảm capacity.

## 4. Giả thuyết 3 — Khi nào có bằng chứng regression?

Một kết luận “B chậm hơn A vì lỗi trong code” phải vượt qua nhiều mức độ:

| Mức | Bằng chứng | Suy luận hợp lệ |
| --- | --- | --- |
| 1. Triệu chứng | Dashboard báo p95 hoặc CPU tăng | Có hiện tượng cần điều tra |
| 2. Cùng điều kiện | JDK, GC, quota, data, mix, RPS và warm-up tương đương | Giảm khả năng nhiễu do tải/JIT |
| 3. Tái hiện | Nhiều lượt A/B, đảo thứ tự, khoảng đo ổn định, chênh lệch vượt noise | Bằng chứng regression có thể lặp lại |
| 4. Cơ chế | JFR/profile và phân tích code chỉ ra CPU work, allocation, waiting hoặc thuật toán mới | Có giả thuyết nguyên nhân gắn với thay đổi |
| 5. Can thiệp | Rollback một thay đổi hoặc sửa đúng đường đó, đo lại cùng điều kiện, hiệu năng phục hồi | Bằng chứng nhân quả mạnh hơn |

**Không có phép thử nào chỉ bằng một con số chứng minh mọi nguyên nhân.** A/B và rollback phải được lặp lại, tính đến biến động cache, GC, runtime tier, host/noisy-neighbor và dữ liệu nghiệp vụ.

Ví dụ regression logic: cùng 400 RPS và cùng data sau warm-up, phiên bản B làm CPU/req từ 8ms thành 13ms, p95 từ 88ms thành 158ms; CPU profile cho thấy nhiều work hơn trong `List.contains`; thay lại cách lookup có hiệu quả giúp CPU/req và p95 trở về gần baseline. Đây là **mẫu lập luận**, không phải số liệu thực của ứng dụng.

### Cùng p95 nhưng CPU khác, hoặc ngược lại

- **CPU cao, p95 cao:** có thể là extra CPU work, GC, JIT, busy-loop hoặc saturation/queueing. Cần thêm threads/GC/profile.
- **CPU thấp, p95 cao:** nghi I/O, downstream, lock, park, request queue. Một CPU profiler thu sample CPU sẽ không nói hết thời gian **off-CPU**.
- **CPU cao, p95 vẫn đạt SLO:** có thể workload hợp lệ; cân nhắc efficiency/cost nhưng chưa có bằng chứng lỗi sản phẩm.
- **Completed RPS giảm, errors/rejection tăng:** phải so **offered rate**; đừng đọc số request hoàn thành thấp thành “có ít tải”.

## 5. Thu bằng chứng JVM: JFR, jcmd và metrics

### 5.1. Các lệnh chẩn đoán HotSpot

`12345` chỉ là PID ví dụ: thay bằng PID Java thật, bảo đảm quyền attach phù hợp và chú ý PID namespace nếu ứng dụng trong container.

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.flags
jcmd 12345 Compiler.queue
jcmd 12345 Compiler.codecache
jcmd 12345 VM.classloader_stats
```

- `VM.version`, `VM.flags` kiểm tra runtime/flags; không so hai lần chạy khác JDK/GC như thể cùng điều kiện.
- `Compiler.queue` là ảnh chụp các method đang chờ biên dịch **ở lúc gọi**, không phải lịch sử JIT.
- `Compiler.codecache` cho code cache statistics; cần đối chiếu log và thời điểm nếu nghi cache pressure.
- `VM.classloader_stats` cho thông tin class loader/classes; không tự chứng minh class loader leak hoặc CPU bug.

Có thể bật log compiler **trong một lần chạy chẩn đoán riêng**:

```bash
java -XX:+PrintCompilation -cp . CpuJitEvidenceDemo
java -Xlog:class+load=info -cp . CpuJitEvidenceDemo
```

Các lệnh có thể in rất nhiều dòng khác nhau giữa JDK/runs; chỉ để quan sát, **không dùng thời gian thu cùng verbose log như benchmark chuẩn**. Nếu cần thử `-Xint` hoặc `-XX:-TieredCompilation` để khảo sát cơ chế, nhớ rằng việc đó thay đổi lớn chế độ thực thi; không kết luận “code bị JIT bug” chỉ vì kết quả tốc độ khác biệt giữa chế độ đó và production.

### 5.2. Thu JFR khi tái hiện

```bash
jcmd 12345 JFR.start name=perf-check settings=profile duration=120s filename=perf-check.jfr
jcmd 12345 JFR.check name=perf-check verbose=true

# Khi file JFR hoàn tất:
jfr summary perf-check.jfr
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad perf-check.jfr
```

Trong ví dụ, recording dài 120 giây, workload phải thực sự chạy trong cửa sổ này. `profile` có thể thu nhiều event/samples hơn `default`, với overhead tăng; **không bảo đảm mọi event đã bật**. Nếu cần snapshot trong khi recording vẫn đang chạy:

```bash
jcmd 12345 JFR.dump name=perf-check filename=perf-check-now.jfr
```

Lệnh `JFR.dump` không tự dừng recording. Kiểm tra timestamp, nội dung và đường dẫn file; tệp cũ cùng tên không phải chứng cứ dump mới thành công.

Các tín hiệu nên đối chiếu:

| Event/metric | Ý nghĩa | Hạn chế |
| --- | --- | --- |
| `jdk.CPULoad` | CPU của JVM và máy theo thời gian | Không cho biết method gây CPU |
| `jdk.ThreadCPULoad` | Thread nào đang tiêu tốn CPU | Khác với stack sampling; cần so các cửa sổ |
| `jdk.ExecutionSample` | Stack của thread đang thực thi được lấy mẫu | Sampling, không phải số lần gọi method |
| `jdk.Compilation` | Activity/time biên dịch của JIT | Có thể chưa bật; event không tự chứng minh gây chậm |
| `jdk.ClassLoad`/`jdk.ClassUnload` | Hoạt động lớp theo thời gian | Tần suất/enable tùy cấu hình |
| GC events/GC logs | Allocation/collection/pause có thể kéo p95 | Phải phân biệt GC và CPU application |
| Monitor/park/file/socket events | Thread bị chờ ở đâu | Threshold có thể loại bỏ các sự kiện ngắn |

JDK Mission Control hỗ trợ xem CPU, hot methods, call tree, class load, GC và compilations; hãy chọn **cùng khoảng thời gian và cấu hình thu** cho hai bản ghi. Trước khi nói “không có compilation”, chạy `jfr summary`, xem `JFR.check verbose=true` khi recording hoạt động, kiểm tra event enabled, threshold, sampling và retention.

### 5.3. Không lấy phần trăm sample làm độ chậm

Nếu method A chiếm 30% CPU samples trước và 60% sau, **không chứng minh A tốn gấp đôi CPU time**: các method khác có thể bớt hoạt động, tổng sample thay đổi hoặc input mix thay đổi. Self time và inclusive time khác nhau; kiểm tra call tree, per-request CPU và số lượng công việc thực tế.

## 6. Bài thực hành Java 17+: cùng kết quả, khác chi phí thuật toán

Ví dụ dưới đây cố ý so hai cách lookup cùng dữ liệu:

- `ArrayList.contains` phải tìm tuần tự, mỗi lookup tốn O(N) trong trường hợp xấu; N queries có thể kéo tới O(N²).
- `HashSet.contains` có kỳ vọng trung bình gần O(1) mỗi lookup khi hash tốt; N queries có thể gần O(N), **không kể chi phí xây set**.

Đây là **thí nghiệm giảng dạy**, không phải benchmark chuẩn: chương trình warm-up 6 lượt, đo 7 lượt, xen kẽ thứ tự, tính median, dùng `volatile` và kiểm chứng kết quả để hạn chế dead-code elimination. Nó vẫn chịu noise của JIT, GC, CPU frequency và không dùng nhiều process forks. Dùng JMH để đo microbenchmark nghiêm túc.

### Chương trình hoàn chỉnh

```java
// File: CpuJitEvidenceDemo.java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class CpuJitEvidenceDemo {
    private static volatile int observed;

    private static int countList(List<Integer> keys, int[] queries) {
        int matches = 0;
        for (int query : queries) {
            if (keys.contains(query)) {
                matches++;
            }
        }
        return matches;
    }

    private static int countSet(Set<Integer> keys, int[] queries) {
        int matches = 0;
        for (int query : queries) {
            if (keys.contains(query)) {
                matches++;
            }
        }
        return matches;
    }

    private static long timeList(List<Integer> keys, int[] queries, int expected) {
        long start = System.nanoTime();
        int result = countList(keys, queries);
        long elapsed = System.nanoTime() - start;
        observed = result;
        if (result != expected) {
            throw new AssertionError("list mismatch: " + result);
        }
        return elapsed;
    }

    private static long timeSet(Set<Integer> keys, int[] queries, int expected) {
        long start = System.nanoTime();
        int result = countSet(keys, queries);
        long elapsed = System.nanoTime() - start;
        observed = result;
        if (result != expected) {
            throw new AssertionError("set mismatch: " + result);
        }
        return elapsed;
    }

    private static long median(long[] samples) {
        long[] copy = samples.clone();
        Arrays.sort(copy);
        return copy[copy.length / 2];
    }

    public static void main(String[] args) {
        int count = 4_000;
        List<Integer> list = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            list.add(i);
        }
        Set<Integer> set = new HashSet<>(list);
        int[] queries = new int[count];
        for (int i = 0; i < count; i++) {
            queries[i] = i * 2;
        }

        int expected = count / 2;
        for (int i = 0; i < 6; i++) {
            timeList(list, queries, expected);
            timeSet(set, queries, expected);
        }

        int rounds = 7;
        long[] listTimes = new long[rounds];
        long[] setTimes = new long[rounds];
        for (int i = 0; i < rounds; i++) {
            if (i % 2 == 0) {
                listTimes[i] = timeList(list, queries, expected);
                setTimes[i] = timeSet(set, queries, expected);
            } else {
                setTimes[i] = timeSet(set, queries, expected);
                listTimes[i] = timeList(list, queries, expected);
            }
        }

        System.out.println("keys=" + count);
        System.out.println("queries=" + queries.length);
        System.out.println("expectedHits=" + expected);
        System.out.println("sameResult=" + (countList(list, queries) == countSet(set, queries)));
        System.out.println("measurementRounds=" + rounds);
        System.err.printf(Locale.ROOT, "listMedianMs=%.3f%n", median(listTimes) / 1_000_000.0);
        System.err.printf(Locale.ROOT, "setMedianMs=%.3f%n", median(setTimes) / 1_000_000.0);
    }
}
```

Biên dịch/chạy bằng JDK 17+ (không dùng thư viện ngoài):

```bash
javac CpuJitEvidenceDemo.java
java CpuJitEvidenceDemo
```

**Stdout xác định**, đã kiểm chứng thực tế bằng OpenJDK 24:

```text
keys=4000
queries=4000
expectedHits=2000
sameResult=true
measurementRounds=7
```

**Stderr thay đổi giữa các máy/lần chạy.** Một lần đo minh họa đã thực hiện:

```text
listMedianMs=4.629
setMedianMs=0.130
```

Không coi hai giá trị thời gian ở stderr là cam kết tốc độ. Dòng `sameResult=true` chỉ cho thấy các phép tra cứu cho cùng kết quả trên bộ input này, không chứng minh hai phương pháp tương đương về mọi thuộc tính ứng dụng.

### Từ thí nghiệm đến bằng chứng regression

Nếu một commit chuyển lookup từ `HashSet` sang `ArrayList` và dữ liệu lớn lên, Big-O cho **giả thuyết** về CPU work tăng. Để xác nhận lỗi production, cần cùng input distribution, cùng số lượng request, cùng warm-up và quota; đo CPU/request và latency nhiều lượt; JFR/profile thấy chi phí tăng trong đường lookup; sửa/rollback đúng yếu tố rồi lặp lại.

Chi phí **xây HashSet**, memory footprint và lifecycle cũng phải tính nếu set được xây lại trên mỗi request. Một cấu trúc lookup nhanh hơn có thể không mang lại lợi ích end-to-end khi dữ liệu nhỏ hoặc chi phí tạo index lấn át. Đừng coi Big-O hoặc một lần chạy demo là kết luận cuối.

### Vì sao cần JMH?

Các vòng đo `System.nanoTime()` có thể bị nhiễu bởi warm-up, JIT inlining/deoptimization, DCE/constant folding, GC, CPU scheduler và việc đo quá ngắn. **OpenJDK JMH** hỗ trợ warm-up iterations, measurement iterations, forks, tiêu thụ kết quả, statistical reporting. Dùng JMH cho **hot-path microbenchmark**; dùng **end-to-end load test** để kết luận throughput/p95 dưới concurrency, vì JMH không đo toàn bộ queue, network, DB và dependency path của dịch vụ.

## 7. Ba tình huống giải thích cùng một triệu chứng

Các số trong ba bảng sau là **dữ liệu giả định minh họa**, không phải hệ thống thật.

### A — Tạm thời do JIT/class initialization

| Từ lúc start, cùng 400 RPS | CPU theo quota | p95 | Compilation/class load |
| --- | ---: | ---: | --- |
| 0–30 giây | 78% | 240ms | Nhiều |
| 2–3 phút | 53% | 112ms | Giảm |
| 5–10 phút | 50% | 105ms | Tương đối ổn định |

Kết luận phù hợp: có **warm-up effect**, chưa có bằng chứng lỗi steady-state. Nhưng nếu cold-start SLO yêu cầu p95 dưới 150ms, vẫn cần giải pháp cho giai đoạn đầu. Không dùng trạng thái ổn định để xóa bỏ trải nghiệm startup của người dùng.

### B — Tăng theo tải và hàng đợi

| Offered RPS | CPU theo quota | Queue depth | p95 |
| --- | ---: | ---: | ---: |
| 300 | 43% | 0–3 | 70ms |
| 450 | 65% | 4–10 | 85ms |
| 650 | 96% | 120+ | 280ms |

Kết luận sơ bộ: dấu hiệu capacity/queueing gần saturation; **chưa có chứng cứ commit regression**. Kiểm tra completed RPS, CPU/req, resource quota, errors, request mix. Nếu B chậm hơn A tại cùng 450 RPS, trở lại giả thuyết lỗi.

### C — Lỗi có đối chứng và can thiệp

| Điều kiện chung: 400 RPS, sau warm-up | A | B | B sau fix |
| --- | ---: | ---: | ---: |
| p95 | 88ms | 158ms | 91ms |
| CPU/request | 8ms | 13ms | 8,2ms |
| Error rate | 0,1% | 0,1% | 0,1% |
| Profile | Lookup ít CPU samples | Nhiều sample trong đường `List.contains` | Trở lại gần baseline |

Nếu A/B lặp nhiều lượt trong cùng điều kiện, B có CPU work/request tăng, JFR hỗ trợ cơ chế lookup đắt hơn và fix đúng đường đó phục hồi metrics, đây là **bằng chứng mạnh** của regression. Vẫn phải báo độ phân tán, các điều kiện chưa kiểm soát và xác minh tính đúng đắn sau fix.

## 8. Thiết kế phép đo A/B đủ tin cậy

1. **Định nghĩa triệu chứng:** endpoint/job, p50/p95/p99, throughput, error, thời điểm và SLO. “CPU tăng” là tín hiệu, chưa phải đề bài chẩn đoán đầy đủ.
2. **Khóa cấu hình:** app commit, JDK vendor/version, GC, JVM flags, CPU quota, memory, concurrency, feature flags, host và dependencies. Nếu đang kiểm tra đổi JDK, nói rõ **runtime là biến A/B**.
3. **Giữ workload tương đương:** cùng RPS/concurrency, data/cardinality, payload, request mix, cache warm/cold và error handling. Tránh Simpson’s paradox khi tỷ trọng endpoint nặng thay đổi.
4. **Xác định warm-up:** chờ hot paths, class load, JIT compilation và caches tương đối ổn; đo startup riêng nếu có cold-start SLO.
5. **Lặp lượt/đảo thứ tự:** không luôn chạy A trước B. Dùng vài lượt và theo dõi median, percentile, dispersion; tránh kết luận từ một khác biệt 3% trong môi trường noise 10%.
6. **Thu profile tương đồng:** JFR cùng settings, cùng cửa sổ, CPU/GC/class/compilation. Chú ý overhead, sampling, threshold, missing data.
7. **Kiểm tra cơ chế:** CPU/req, code hot path, allocations/GC, lock/I/O/queue. Mọi kết luận “do JIT” phải hợp với thời điểm compilation/profile change.
8. **Can thiệp một yếu tố:** rollback/fix nghi vấn, chạy lại workload tương đương và theo dõi cả chức năng lẫn hiệu năng.

### Mẫu bảng kiểm thử

| Trường | A | B |
| --- | --- | --- |
| JDK/GC/flags | Ghi chính xác | Ghi chính xác |
| App commit/flag | Ghi ID | Ghi ID |
| CPU quota, memory, host | Ghi | Ghi |
| Warm-up và thời lượng đo | Ghi tiêu chí ổn định | Cùng tiêu chí |
| Offered/completed RPS, mix | Ghi | Cùng mix |
| Cache/key cardinality/data | Ghi | Tương đương |
| p50/p95/p99/errors | Đo | Đo |
| Process CPU time, CPU/req | Đo | Đo |
| GC/queue/throttling | Đo | Đo |
| JFR/compiled methods/class activity | Thu cùng setting | Thu cùng setting |
| Số lượt, độ biến thiên | Ghi | Ghi |

## 9. Những tình huống dễ nhầm

**“JIT deoptimization = bug.”** Không. Deoptimization là cơ chế HotSpot thích nghi khi giả định tối ưu không còn phù hợp. Cần thấy deopt/recompile lặp lại bất thường và hiệu ứng định lượng dưới tải ổn định mới có giả thuyết performance issue.

**“Code cache lớn = RAM leak.”** Không. Code cache chứa compiled code hợp lệ; chỉ khi pressure/compilation disable hoặc hành vi tương ứng làm giảm năng lực thì điều tra sâu. Đọc `Compiler.codecache` và các dấu hiệu runtime.

**“Class count tăng = CPU regression.”** Không. Class load hợp lệ sau warm-up hoặc khi tạo proxy cũng làm count tăng. Xem thời gian class loading, classloader lifetime và impact thật lên CPU/latency.

**“GC pause làm chậm tức là JIT không liên quan.”** Không nhất thiết, nhưng phải phân biệt cơ chế. Thu GC logs, allocation rate và JFR GC events trước khi quy nguyên nhân. Một request có thể chậm do GC mà application CPU thấp.

**“CPU thấp mà p95 cao → JIT optimizer làm chậm.”** Không đủ. Kiểm tra off-CPU waits: monitor/park, network, DB, thread scheduling và queue. CPU profiler chỉ quan sát phần đang chạy.

**“Profile method A từ 30% lên 60% → A chậm gấp đôi.”** Không đúng. Phần trăm sample phụ thuộc mẫu số, sampling và đường gọi. Ưu tiên CPU work/request, thread CPU và JFR call tree.

**“Tắt JIT bằng -Xint cho kết quả khác → lỗi do JIT.”** Tắt JIT làm thay đổi phương thức chạy và performance rất lớn; đó là một thử nghiệm khảo sát, không phải baseline so sánh production.

**“Chạy nhiều lần System.nanoTime đã đủ.”** Chưa chắc. JMH giúp giảm bẫy DCE/constant folding, warm-up/fork/order; load test end-to-end mới mô tả queue và downstream.

**“Chỉ cần sửa xong CPU giảm.”** Nếu p95 và completion/error không cải thiện, có thể chỉ tối ưu resource cost chứ chưa sửa bottleneck tác động người dùng. Đặt mục tiêu đúng.

## 10. Checklist quyết định và mẫu kết luận

Trước khi gọi một thay đổi là regression:

- [ ] Biết **triệu chứng thực**: p95, p99, throughput, error/SLO, phạm vi endpoint.
- [ ] So workload theo **offered rate, completed rate, mix, data và concurrency**, không chỉ tổng request.
- [ ] Kiểm tra **CPU denominator/quota/throttling**, tránh so tỷ lệ CPU không đồng đơn vị.
- [ ] Đã tách **startup/warm-up** khỏi steady-state, hoặc chủ động đo cold-start theo SLO.
- [ ] Xem JIT compilation/class loading/code cache/GC trong cửa sổ tương ứng; không kết luận từ một event đơn lẻ.
- [ ] A/B chạy cùng JDK/config/resource, cùng load và nhiều lượt; chênh lệch lớn hơn noise.
- [ ] Đã kiểm tra CPU/request, queue, off-CPU waits, GC và JFR call stacks.
- [ ] Có giả thuyết về method/thuật toán/lock/alloc và cách kiểm chứng độc lập.
- [ ] Fix/rollback một yếu tố phục hồi kết quả trong lần đo lặp lại, chức năng vẫn đúng.
- [ ] Báo rõ **đã xác nhận / nghi ngờ / chưa đủ bằng chứng**, cùng những giới hạn dữ liệu JFR và thí nghiệm.

Mẫu kết luận:

```text
Triệu chứng: p95 /search tăng từ 90ms lên 160ms.
Cửa sổ: sau warm-up, 400 RPS, cùng input mix, quota, JDK/GC.
Quan sát: CPU-seconds/request tăng; errors, throughput và queue đã đối chiếu.
JIT/class loading: activity không giải thích được thay đổi kéo dài
    trong cửa sổ đo (theo các event/setting thực tế có thể thu).
Profile: CPU tăng ở method X trên call path Y.
Can thiệp: thay đổi X hoặc rollback commit Z, đo lại cùng điều kiện.
Kết luận: regression đã xác nhận / còn nghi ngờ / chưa đủ chứng cứ.
Giới hạn: độ phân tán, event bị lọc và điều kiện chưa khống chế.
```

**Thông điệp cốt lõi:** JIT và class loading giải thích thay đổi **theo thời gian/pha thực thi**; tăng tải giải thích thay đổi **theo offered work, saturation và queueing**. Một lỗi hiệu năng được bảo vệ bằng **đối chứng cùng điều kiện**, **tái hiện**, **cơ chế đo được** và **can thiệp xác nhận**. Không dùng một đồ thị CPU, một JFR hot method hay một lần benchmark ngắn làm bằng chứng duy nhất.

## Tài liệu tham khảo

- Oracle JDK 21 — Java HotSpot VM Performance Enhancements (tiered compilation, code cache): https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html
- Oracle JDK 21 — Diagnostic Tools, JFR và `jcmd`: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21 — `jcmd` command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — JFR event settings: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle JDK 21 — `jfr` command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- OpenJDK JMH — Java Microbenchmark Harness: https://github.com/openjdk/jmh
