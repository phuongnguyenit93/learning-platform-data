# Ảnh hưởng đến thời gian khởi động, JIT, inlining, GC và độ trễ

> **Luận điểm chính:** Một Java agent có thể làm tăng **thời gian khởi động**, kéo dài **class loading**, thay đổi quyết định **JIT và inlining**, tạo thêm **allocation/GC**, tăng **CPU hoặc contention** trên hot path và cuối cùng ảnh hưởng **latency p95/p99**. Không có tỷ lệ overhead chung cho mọi agent. Để đánh giá đúng phải tách **chi phí khi JVM biến đổi lớp** với **chi phí lặp lại mỗi lần bytecode đã instrument được thực thi**, rồi so trên cùng JVM, tải, JIT warmup và cấu hình exporter.

Bài học thuộc nhóm **Đồng thời và hiệu năng** trong Java Advance – instrumentation. Nội dung đi từ cơ chế JVM đến phương pháp đo, lỗi benchmark, khả năng giảm overhead và thí nghiệm Java 17+ dùng **startup agent có `ClassFileTransformer` thật**. Thí nghiệm có ba trường hợp: không agent, agent chỉ quan sát class loading và agent thực sự thay bytecode một method. Các thông số đo thời gian được để biến động theo máy; chỉ stdout kiểm chứng logic và số lượt đo mới được ghi chính xác.

## 1. Hai loại chi phí phải đo riêng

Sơ đồ tổng quan:

~~~text
                    COLD START
Process start
    |
    v
JVM startup -> load agent JAR -> premain -> application bootstrap
                                  |
                                  +-- config/helper/JAR I/O, classloader
                                  |
                                  +-- register transformer
                                             |
                                             v
                   class definition -> transform -> verify/link
                                             |
                                             v
                                          READY
                                             |
                                             v
                    STEADY STATE
              Hot business method invocation
                 |                   |
                 +-- business bytecode
                 +-- injected hook (timer/context/metric/log)
                 +-- JIT compilation & possible inlining decisions
                 +-- allocation, locks, CPU, exporter queue
                                    |
                                    v
                          response latency
~~~

| Loại chi phí | Phát sinh ở đâu? | Bằng chứng nên thu |
| --- | --- | --- |
| Agent startup | Khi JVM xử lý `-javaagent`, gọi `premain` và khởi tạo helper | External process-to-ready time, premain duration, startup CPU |
| Class transform | Lúc JVM load/define/redefine/retransform một class | Số callback, thời gian biến đổi, class-loading logs |
| JIT/inlining | Khi method đạt độ nóng phù hợp và qua nhiều compilation tiers | Compilation events, inlining decision, time-to-steady-state |
| Per-invocation | Mỗi lượt gọi method sau khi hook đã được chèn | Count, CPU/op, ns/op, throughput, lock contention |
| Allocation/GC | Hook tạo span, string, buffer, context hoặc giữ references | Bytes/op, allocation rate, pause/safepoint, retained heap |
| Tail latency | Trong toàn bộ request/job từ ingress đến completion | p50/p95/p99, queue time, error/timeout, exporter backpressure |

Các chi phí có thể **tương tác**: method lớn hơn có thể thay đổi quyết định inline, làm CPU tăng; CPU tăng làm hàng đợi dài hơn; allocation tăng khiến GC nhiều hơn; exporter chậm gây blocking. Tuy vậy đây chỉ là **các cơ chế có thể xảy ra**, không phải tuyên bố mọi JVM đều có cùng kết quả.

Phân biệt hai phép đo:

- **Time-to-ready:** bao gồm process start, JVM initialization, agent initialization, application boot và class loading trước readiness.
- **Operation latency:** đo đúng boundary một giao dịch hoặc method. Nếu tính từ ingress thì bao gồm hàng đợi của service ở vị trí ingress đó; nếu timer chỉ đặt trong `checkout()` thì không bao gồm mọi bước trước/sau method.

Đừng dùng timer bên trong `premain` làm đại diện cho toàn bộ startup; cũng đừng dùng latency của một `ClassFileTransformer.transform()` làm chi phí cho **mọi lần gọi method**.

## 2. Ảnh hưởng đến thời gian khởi động JVM

### 2.1. Startup agent đi trước `main`

Một cách khởi động thông thường:

~~~bash
java -javaagent:agent.jar=options -jar application.jar
~~~

Với manifest và JVM phù hợp, `premain(String, Instrumentation)` của agent được gọi trước application `main`. Trong thực tế startup còn liên quan các công việc không nằm trong timer của `premain`:

- JVM tìm và nạp agent JAR, xác minh manifest, nạp class agent và dependencies.
- `premain` đọc config, tạo helper, khởi tạo logger/metrics exporter, đăng ký transformer.
- Ứng dụng nạp nhiều class ban đầu; mỗi transformer có thể kiểm tra hoặc biến đổi các class cần thiết.
- Các bytes mới được JVM kiểm tra/verify/link và JIT warmup về sau; transformer không phải bước duy nhất.
- Một số library bị load sớm hơn vì chính instrumentation/helper gọi chúng.

Nếu agent tạo kết nối exporter hoặc DNS lookup đồng bộ trong `premain`, timeout có thể làm startup chậm ngay cả khi **không class nào bị biến đổi**. Nếu agent scan toàn bộ classpath/JAR hoặc parse mọi class vô điều kiện, latency khởi động tăng theo số class và số work callback.

**Chiến lược:** giữ `premain` tối giản, đặt timeout cho external operations, chỉ khởi tạo những gì bắt buộc để không bỏ lỡ điểm instrument, filter lớp trước khi parse bytecode, tránh disk/network I/O trong callback và ghi telemetry startup có giới hạn. Trì hoãn init không phải luôn đúng: một helper cần có trước khi class đầu tiên được định nghĩa có thể buộc khởi tạo sớm.

### 2.2. Lần load class đầu tiên là đường đồng bộ đáng chú ý

Khi JVM chuẩn bị định nghĩa một class, callback có thể được gọi:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> beingRedefined, ProtectionDomain domain, byte[] bytes) {
    if (className == null || !className.startsWith("com/acme/orders/")) {
        return null;
    }
    return weaveOnlySelectedMethods(bytes);
}
~~~

**Mảnh code minh họa**, chưa chạy độc lập vì `weaveOnlySelectedMethods` thuộc thư viện bytecode của agent. Ý tưởng là trả `null` càng sớm càng tốt cho class ngoài allowlist. Trả `null` nghĩa transformer này **không thay đổi bytes** ở lượt gọi đó; không có nghĩa callback miễn phí.

Một callback tốn thời gian có thể nằm trong **critical path của class loading**. Khi nhiều thread nạp các class khác nhau, nhiều callback có thể chạy đồng thời; một lock global, việc load class helper từ bên trong transformer hoặc thao tác exporter có thể tạo contention/recursion/deadlock. Dùng thread-safe state nhưng tránh gom mọi call vào cùng monitor.

Tổng chi phí callback phụ thuộc vào:
- Tần suất classes được định nghĩa (startup và lazy loads).
- Số transformer và thứ tự transformations.
- Parser/sinh bytes, số method được chọn và độ lớn classfile.
- I/O/resource lookup trong callback, cache và classloader behavior.
- Verify/link/JIT consequences của bytes cuối.

**Lưu ý lazy initialization:** Service có thể báo ready trước khi class của một endpoint/serialization library thực sự được load. Khi request đầu tiên tới, nó chịu cả load class, transform và JIT. Vì vậy có thể thấy startup gần như không đổi nhưng **first-request p99** lại xấu.

### 2.3. Đừng nhầm registration với code đã instrument

`Instrumentation.addTransformer(transformer)` đăng ký callback; `ClassFileTransformer` có thể trả `null`, chỉ thống kê class loading mà không sửa method body. Ngược lại, nếu transformer trả classfile bytes mới và JVM định nghĩa thành công, **bytecode đã chèn tiếp tục chạy trong class đang loaded** dù transformer về sau bị gỡ.

`removeTransformer` chỉ hủy registration; nó **không tự hoàn tác instrumentation**. Vì thế overhead khi chạy method có thể tồn tại rất lâu sau lúc không còn callback mới.

## 3. JIT compilation và inlining có thể thay đổi ra sao?

### 3.1. Bytecode shape quan trọng

JIT sử dụng runtime profile, tiered compilation, kích thước bytecode, hotness, type profile và nhiều heuristics để quyết định tối ưu. Một method nhỏ ban đầu có thể được inline vào caller; khi chèn timer/trace hook, method có thêm calls, branches, exception handler và bytecode:

~~~java
// Trước instrumentation, mảnh method minh họa:
public int calculate(int x) {
    return (x * 31) ^ (x >>> 3);
}
~~~

~~~java
// Sau instrumentation, mảnh method minh họa:
public int calculate(int x) {
    long started = System.nanoTime();
    try {
        return (x * 31) ^ (x >>> 3);
    } finally {
        ProbeRecorder.record(System.nanoTime() - started);
    }
}
~~~

Nếu bản mới dài hơn, ở một số compilation/call sites, JIT có thể không inline vì giới hạn kích thước, độ phức tạp hoặc profile. Khi không inline, compiler có thể mất cơ hội constant propagation hoặc tối ưu xuyên method. Tuy nhiên, **không** có quy tắc “thêm một hook là chắc chắn không inline”: compiler vẫn có thể inline method/hook khi đủ nóng hoặc điều kiện khác thuận lợi.

Một inline decision không là chân lý bất biến:

~~~text
tier / call-site A:  failed to inline: callee is too large
tier / call-site B:  inline (hot)
helper call:         inline (hot)
~~~

Các dòng ở trên mô tả **dạng kết quả diagnostic**, không phải stdout cố định của bất kỳ JVM nào. Trong thử nghiệm của bài, chính `PulseWork::calculate` có trạng thái inline khác nhau ở những lượt JIT.

### 3.2. JIT warmup và throughput

Trước khi nóng, code có thể chạy qua interpreter/C1 và sau đó được tối ưu bằng compiler khác như C2 trên HotSpot. Điều kiện phụ thuộc JVM/JDK/options, không phải quá trình cố định cho tất cả VM. Instrumentation có thể:
- Thay đổi số bytecode và số calls mà compiler cần xem.
- Thay đổi type/profile của call sites và inlining.
- Tạo code cho helper hoặc các compiled variants khác.
- Tăng compilation CPU/code-cache use.
- Thay đổi thời gian cần để throughput đạt vùng tương đối ổn định.

Do đó đo 100 request đầu tiên của baseline sau warmup và 100 request đầu tiên của một agent vừa mới khởi động là **không công bằng**. Cần so **cold start riêng**, **warmup riêng**, và **steady state riêng**, cùng điều kiện đầu vào.

### 3.3. Xem JIT log trên HotSpot

Ví dụ:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining WindowExperiment
~~~

Với agent của phần thực hành:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining -javaagent:probe-agent.jar=inject WindowExperiment
~~~

`PrintCompilation` cho thấy method compilation, `PrintInlining` cho thấy decision theo call site. `-XX:+UnlockDiagnosticVMOptions` là tiền đề của `PrintInlining` trên HotSpot tương ứng. Đây là **lượt chẩn đoán**; lượng log/format output có thể rất lớn, chính logging cũng gây overhead, vì vậy không bật nó trong lần benchmark timing chính.

Trong lượt kiểm chứng OpenJDK 24, `PulseWork::calculate` sau khi instrument được log là **47 bytes** và có lúc `failed to inline: callee is too large`, về sau `inline (hot)`; `ProbeRecorder::record` cũng có `inline (hot)`. Không quy 47 bytes thành ngưỡng áp dụng cho mọi JVM: heuristic/tier/call site có thể khác.

**Khác biệt quan trọng:** JIT có thể inline chính hook, nhưng việc ghi counter, đọc đồng hồ hoặc lưu context **không vì thế hoàn toàn không tốn chi phí**. Inlining bỏ một phần overhead lời gọi và mở cơ hội tối ưu, không xóa nghĩa vụ ghi phép đo.

## 4. Redefinition, retransformation và deoptimization

Một agent startup có thể chỉ transform class ở **lần định nghĩa đầu**. Nhưng một agent attach muộn hoặc cần bật/tắt quy tắc khi đang chạy có thể gọi `retransformClasses`/`redefineClasses` lên class đã loaded. Tình huống này thêm **một loại chi phí khác** ngoài startup và per-call hook.

Chuỗi có thể xảy ra:

~~~text
Method đã được JIT compile, có thể đã inline vào callers
    |
    v
retransformClasses(target) / redefineClasses(definition)
    |
    v
JVM xử lý transformer/verify/install definition mới
    |
    v
Compiled dependencies có thể cần invalidation/deoptimization
    |
    v
Profile/compilation mới, latency có thể biến động
~~~

Một số điều **được hợp đồng Java Instrumentation xác định**:

- Method có active stack frames vẫn có thể tiếp tục thực hiện bytecode **của định nghĩa cũ** trong những frames đó.
- Những invocation mới dùng method definition mới.
- Class initialization không tự chạy lại; static fields giữ giá trị hiện tại.
- Đối tượng hiện có vẫn là chính nó.
- Không có cơ chế `removeTransformer` tự rollback method đã cài.

Việc có safepoint/deoptimization/compiled dependency invalidation và chi phí cụ thể là **chi tiết implementation/tình huống**. Không khẳng định mỗi lần retransform sẽ làm toàn JVM dừng X ms hay luôn compile lại mọi method.

Nếu production bật instrumentation động:
1. Ghi timestamp chính xác lúc gọi API.
2. Đo duration riêng của API call và tình trạng lỗi.
3. Theo dõi p95/p99, JIT log/safepoint và warmup sau thay definition.
4. Thực hiện theo batch nhỏ hoặc canary khi phù hợp, tránh retransform hàng nghìn class đồng thời chỉ để kiểm tra một giả thuyết.
5. Phân biệt **one-time spike** của class processing/JIT với **steady-state overhead** của hook được cài.

## 5. Allocation, GC, metaspace và lifetime references

### 5.1. Không phải mọi hook đều có chi phí allocation giống nhau

| Hook hoặc cách viết | Rủi ro CPU/allocation | Lưu ý |
| --- | --- | --- |
| `System.nanoTime()` + tính hiệu | Chi phí gọi đồng hồ, không cần tạo object ở source | Đo elapsed, không phải CPU time |
| `LongAdder.increment()` | Atomic/striped updates và memory traffic | Có overhead; không cần tạo object mới ở mỗi invocation theo source |
| Tạo `Span`/context object | Có thể cấp phát object | Sampling và fast path khi disabled |
| `String.format`, dynamic log message | Có thể tạo string/buffer/varargs | Kiểm tra logging guard trước format |
| Stack trace mỗi lần gọi | Chi phí rất cao, allocation lớn | Chỉ hợp lý cho sự kiện bất thường |
| `ThreadLocal` context | Truy cập state, có thể giữ object lâu trên pool thread | Phải `remove()`/restore đúng lifecycle |
| Queue/export telemetry | Allocation, scheduling, backpressure | Tránh I/O đồng bộ trên request hot path |
| Cache `Class<?>`/`ClassLoader` toàn JVM | Retained references, rủi ro classloader leak | Cache có ownership/teardown |

Hai khái niệm thường bị trộn:

- **Heap pressure**: short-lived spans, strings, trace context, exporters.
- **Metaspace/class metadata**: classes/loaders sống lâu, dynamic proxies, helper classes; một static cache giữ mạnh `Class<?>` của loader cũ có thể cản class unloading qua nhiều redeploy.

Một agent làm allocation rate tăng nhưng collector đủ mạnh có thể vẫn có latency chấp nhận được; ở hệ khác, GC pauses hoặc concurrent GC CPU tăng sẽ gây p99 xấu hơn. **Không kết luận chỉ từ số classes transformed.**

### 5.2. Chuỗi hệ quả cần đo, không tự suy diễn

~~~text
Hook tạo object nhiều trên hot path
       |
       v
Allocation rate có thể tăng
       |
       +-- Young GC / promotion / concurrent work thay đổi
       +-- CPU và memory bandwidth bị dùng thêm
       +-- Heap occupancy hoặc retained data có thể đổi
       |
       v
Throughput và latency tails có thể bị ảnh hưởng
~~~

Theo dõi **allocation bytes/op**, GC count/pause, live heap/heap occupancy, metaspace/classloader count và safepoint time; nhưng cũng đo **CPU và throughput** để tìm chi phí không qua GC. Ví dụ atomic contention có thể kéo dài request mà không tạo nhiều object.

Nếu cần class unloading, không giữ tất cả đối tượng `Class<?>[]` hoặc `Map<ClassLoader, ...>` trong static registry của agent chỉ để làm báo cáo. Đo count/category rồi giải phóng references; dùng cache per-class/có lifecycle khi thật sự cần. `System.gc()` không bảo đảm class unloading trong một thời hạn xác định.

### 5.3. GC logs và JFR

Trên HotSpot/OpenJDK, có thể dùng:

~~~bash
java -Xlog:gc*,safepoint=info -javaagent:agent.jar -jar application.jar
~~~

Đây là **lệnh mẫu**, thay tên JAR thật trước khi chạy. Khi đánh giá, so với baseline dùng **cùng collector/JDK/heap/CPU quota**. Không suy mọi biến động GC đều do agent; traffic, object lifetime và heap sizing cũng ảnh hưởng.

Dùng Java Flight Recorder (JFR) cho allocation, CPU, GC, lock/contention và nhiều sự kiện runtime:

~~~bash
java -XX:StartFlightRecording=filename=agent.jfr,settings=profile,dumponexit=true -javaagent:agent.jar -jar application.jar
~~~

Với tiến trình Java đã chạy:

~~~bash
jcmd 12345 JFR.start name=agent-check settings=profile duration=60s filename=agent-check.jfr
~~~

`12345` là **PID minh họa**. Trên JDK có công cụ `jfr`, có thể đọc `jfr summary agent.jfr`; hoặc dùng JDK Mission Control. JFR profile cũng có overhead và mức độ bao phủ phụ thuộc event settings: nên ghi lại settings, chạy thời gian đủ dài và nếu cần đo **overhead của chính JFR**, so các lượt bật/tắt giống nhau.

## 6. Độ trễ: p95/p99, blocking và concurrency

### 6.1. Timer trong method đo interval, không đo CPU

`System.nanoTime()` thích hợp để lấy **thời gian tương đối** giữa hai thời điểm trong cùng JVM:

~~~java
long started = System.nanoTime();
try {
    businessOperation();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    // Record elapsed; không coi đây là thời gian CPU thuần.
}
~~~

Đây là mảnh code minh họa, không độc lập vì thiếu `businessOperation`. Nếu method bị block trên lock, sleep, I/O, mất thời gian scheduler hay chịu GC pause, elapsed timer vẫn bao gồm **khoảng wall-clock**. Nếu cần on-CPU/off-CPU, dùng profiler/JFR phù hợp, không tự gán `nanoTime` là CPU clock.

### 6.2. Một chi phí nhỏ có thể bị khuếch đại

Nếu hook thêm một chi phí trung bình `c` vào hot method được gọi `N` lần mỗi request, một model bậc lớn là:

~~~text
extra_work_per_request  ~  N * c
~~~

Đây là **mô hình đơn giản**, không phải phương trình wall latency chính xác. Chi phí thực còn chịu JIT optimization, concurrency, queueing, GC, locks và exporter. Đừng gắn `c = 20 ns` cố định nếu chưa đo trên JVM đích.

Ví dụ thêm một lock chung hoặc một exporter synchronous tạo queue. Ở concurrency thấp, mean latency có thể ít đổi; ở load cao, request cạnh tranh lock/queue → p99 tăng mạnh. Vì vậy **đo cả throughput và p50/p95/p99** dưới cùng client concurrency, rate, payload và dependency state.

### 6.3. Không đếm trùng các khoảng thời gian lồng nhau

Nếu một checkout span chứa payment span, không cộng trực tiếp duration của checkout và payment để suy ra end-to-end: payment vốn đã nằm trong checkout. Tương tự, với `CompletableFuture`, timer quanh lời gọi tạo future chỉ đo scheduling, **không** đo tới lúc future hoàn thành. Một phép đo sai boundary có thể tạo “số liệu” nhưng không trả lời được câu hỏi vận hành.

**Thiết kế điểm đo:** đặt hook ở boundary nghiệp vụ/dependency có ý nghĩa, không instrument mọi getter/helper/iterator vì có thể. Nếu cần hotspot CPU trong logic thuần tính toán, hãy dùng profiling/lấy mẫu trước rồi quyết định chèn hook sâu có đáng không.

## 7. Thí nghiệm Java 17+: ba chế độ baseline / observe / inject

Ví dụ sử dụng startup agent thật. Để không cần ASM/Byte Buddy, nó biên dịch hai `PulseWork.class` **cùng binary name, cùng cấu trúc** vào hai thư mục khác nhau. Transformer trả classfile có timer chỉ khi mode là `inject`. Đây là cách tạo fixture để hiểu cơ chế, **không** phải phương pháp an toàn thay classfile bất kỳ trong hệ thống production có nhiều loaders/modules.

### 7.1. Tệp gốc `PulseWork.java`

~~~java
public final class PulseWork {
    public int calculate(int x) {
        int a = (x * 31) ^ (x >>> 3);
        return a + (x & 7);
    }
}
~~~

Đây là một hot method tính toán rất nhỏ, dễ cho thấy overhead tương đối của timer/hook. Không có I/O, không có network, không đại diện cho toàn bộ dịch vụ thanh toán/HTTP.

### 7.2. Bộ ghi `ProbeRecorder.java`

~~~java
import java.util.concurrent.atomic.LongAdder;

public final class ProbeRecorder {
    private static final LongAdder CALLS = new LongAdder();
    private static final LongAdder TOTAL_NANOS = new LongAdder();

    private ProbeRecorder() {}

    public static void record(long elapsedNanos) {
        CALLS.increment();
        TOTAL_NANOS.add(elapsedNanos);
    }

    public static long calls() { return CALLS.sum(); }
    public static long totalNanos() { return TOTAL_NANOS.sum(); }
}
~~~

`LongAdder` lưu tổng số observation và tổng `elapsedNanos`. `sum()` không phải atomic snapshot của mọi concurrent updates, nhưng demo chỉ đọc khi tất cả loops đã kết thúc trong một thread. **Tổng thời gian/count không tính được p95/p99**; nếu cần percentile production hãy dùng histogram có boundary và nhãn phù hợp.

### 7.3. Tệp biến thể `variant/PulseWork.java`

~~~java
public final class PulseWork {
    public int calculate(int x) {
        long started = System.nanoTime();
        try {
            int a = (x * 31) ^ (x >>> 3);
            return a + (x & 7);
        } finally {
            ProbeRecorder.record(System.nanoTime() - started);
        }
    }
}
~~~

Đây là **version thay method body**. Agent trả bytes variant ở **initial class definition**, không cần xin quyền redefine/retransform. `finally` bảo đảm một observation cho mỗi invocation kể cả khi có exception; method demo không chủ động ném exception. Record time của mỗi invocation **không bao gồm toàn bộ external overhead** của agent (class loading, JIT compilation, queueing bên ngoài method).

### 7.4. `ScopedTransformer.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ScopedTransformer implements ClassFileTransformer {
    private final byte[] replacement;

    public ScopedTransformer(byte[] replacement) {
        this.replacement = replacement == null ? null : replacement.clone();
    }

    @Override
    public byte[] transform(Module module, ClassLoader loader, String className,
            Class<?> beingRedefined, ProtectionDomain domain, byte[] original) {
        if (!"PulseWork".equals(className)) return null;
        System.out.println("transform=PulseWork");
        return replacement == null ? null : replacement.clone();
    }
}
~~~

Chỉ mục tiêu `PulseWork` được biến đổi. Nếu `replacement == null` (mode `observe`), callback trả `null` và method body gốc được giữ nguyên. Trong mode `inject`, transformer trả classfile variant. Không ghi `System.out.println` với mọi class trong production; in một lần trong demo chỉ để kiểm tra callback đã xảy ra.

Tên `className` trong callback là **JVM internal name**; với class có package `com.acme`, tên thường là `com/acme/PulseWork`. Trong production, phải kiểm tra class loader/module/descriptor và patch class bytes đầu vào thay vì trả một file biên dịch sẵn cho mọi loader có cùng tên.

### 7.5. Startup `ProbeAgent.java`

~~~java
import java.io.IOException;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ProbeAgent {
    public static void premain(String args, Instrumentation inst) throws IOException {
        String mode = args == null ? "observe" : args;
        if (!"observe".equals(mode) && !"inject".equals(mode)) {
            throw new IllegalArgumentException("Expected observe or inject");
        }
        byte[] replacement = "inject".equals(mode)
            ? Files.readAllBytes(Path.of("variant/PulseWork.class"))
            : null;
        inst.addTransformer(new ScopedTransformer(replacement));
        System.out.println("agent-mode=" + mode);
    }
}
~~~

Agent đọc bytes trước khi đăng ký transformer. Điều này giúp callback không chạm disk; nhưng **đọc file trong `premain` vẫn là chi phí startup mode inject**. Manifest phải trỏ đúng `Premain-Class`. `addTransformer` không bật `canRetransform=true`, vì demo chỉ xử lý lần đầu class được định nghĩa.

### 7.6. Workload `WindowExperiment.java`

~~~java
public final class WindowExperiment {
    private static final int WARMUP = 80_000;
    private static final int MEASURE = 120_000;

    public static void main(String[] args) {
        PulseWork work = new PulseWork();
        long checksum = 0;

        for (int i = 0; i < WARMUP; i++) checksum += work.calculate(i);
        long started = System.nanoTime();
        for (int i = 0; i < MEASURE; i++) checksum += work.calculate(i);
        long elapsed = System.nanoTime() - started;

        System.out.println("warmup_ops=" + WARMUP);
        System.out.println("measure_ops=" + MEASURE);
        System.out.println("checksum=" + checksum);
        System.out.println("window_positive=" + (elapsed > 0));
        System.out.println("probe_calls=" + ProbeRecorder.calls());
        System.out.println("probe_time_positive=" + (ProbeRecorder.totalNanos() > 0));

        if (Boolean.getBoolean("showTimes")) {
            System.out.println("window_ns=" + elapsed);
            System.out.println("window_ns_per_op=" + ((double) elapsed / MEASURE));
        }
    }
}
~~~

Giải thích kết quả:

- Có **80.000 warmup** và **120.000 measured calls**; hook trong mode inject ghi **200.000** observations vì được đặt trực tiếp trong method, không chỉ measured loop.
- `checksum` dùng để kiểm tra đầu ra nghiệp vụ và hạn chế một số dạng dead-code elimination; nó **không** loại hết bias benchmark của compiler.
- `window_positive` tránh đặt một số timing không thể tái lập thành “stdout chuẩn”.
- `showTimes=true` cung cấp số đo thực, nhưng một lần chạy với timer ở ngoài vòng **chưa đủ** để đo overhead có ý nghĩa thống kê.
- `ProbeRecorder` ghi tổng nanos của method theo boundary của từng invocation; tổng đó **khác** timing của whole measured loop.

### 7.7. Manifest `agent.mf` và thư mục

~~~text
Manifest-Version: 1.0
Premain-Class: ProbeAgent
~~~

Manifest phải có newline cuối. Cấu trúc:

~~~text
demo/
  PulseWork.java
  ProbeRecorder.java
  ScopedTransformer.java
  ProbeAgent.java
  WindowExperiment.java
  agent.mf
  variant/
    PulseWork.java
~~~

Hai version `PulseWork.java` **không** được compile vào cùng thư mục output. Bản gốc ở application classpath `.`; bản instrumented ở `variant/` chỉ được agent đọc như bytes dữ liệu.

### 7.8. Biên dịch và chạy

~~~bash
javac --release 17 PulseWork.java ProbeRecorder.java ScopedTransformer.java ProbeAgent.java WindowExperiment.java

javac --release 17 -classpath . -d variant variant/PulseWork.java

jar --create --file probe-agent.jar --manifest agent.mf ProbeAgent.class ScopedTransformer.class

java WindowExperiment

java -javaagent:probe-agent.jar=observe WindowExperiment

java -javaagent:probe-agent.jar=inject WindowExperiment
~~~

Dùng JDK 17+ và chạy từ thư mục `demo` chứa các tệp trên. Những lệnh này đã được kiểm thử thực với `javac --release 17` trên OpenJDK 24.

### 7.9. Stdout thực tế

**Baseline (không agent):**

~~~text
warmup_ops=80000
measure_ops=120000
checksum=322399513344
window_positive=true
probe_calls=0
probe_time_positive=false
~~~

**Observe-only:**

~~~text
agent-mode=observe
transform=PulseWork
warmup_ops=80000
measure_ops=120000
checksum=322399513344
window_positive=true
probe_calls=0
probe_time_positive=false
~~~

**Inject:**

~~~text
agent-mode=inject
transform=PulseWork
warmup_ops=80000
measure_ops=120000
checksum=322399513344
window_positive=true
probe_calls=200000
probe_time_positive=true
~~~

Các dòng này là **output xác minh logic**, không phải báo cáo performance. Kết quả nghiệp vụ `checksum` giống nhau ở ba chế độ, nhưng số timer observations thay đổi đúng như thiết kế.

| So sánh | Câu hỏi có thể nghiên cứu | Không suy luận quá mức |
| --- | --- | --- |
| Baseline vs Observe | Chi phí startup agent, transformer đăng ký, callback mà không đổi bytes | Không suy “observe mode overhead luôn bằng 0” |
| Observe vs Inject | Chi phí thêm bytecode hook và thay đổi JIT/GC | Một lượt chạy không chứng minh phần trăm overhead production |
| First request vs steady state | Chi phí lazy class loading/JIT warmup | Không dùng first request làm đại diện steady-state |
| Inject enabled vs disabled-fast-path | Overhead nhánh kiểm tra disabled và telemetry thật | Disabled hook vẫn để lại bytecode và có chi phí kiểm tra |

## 8. Đo timing, đọc JIT và kiểm tra GC trên demo

### 8.1. Hiển thị con số thời gian nếu cần

~~~bash
java -DshowTimes=true WindowExperiment

java -DshowTimes=true -javaagent:probe-agent.jar=observe WindowExperiment

java -DshowTimes=true -javaagent:probe-agent.jar=inject WindowExperiment
~~~

Sẽ in thêm `window_ns=...` và `window_ns_per_op=...`; dấu `...` là **phần số thực tế thay đổi**, không phải một stdout cố định. Với một method cực nhỏ và chỉ một JVM fork, kết quả chịu ảnh hưởng JIT tier, CPU frequency, clock resolution, scheduling, GC, heap và workload optimization.

**Không dùng output này để kết luận “inject chậm 30%” chỉ dựa vào một cặp số.** Muốn microbenchmark đáng tin hơn, dùng JMH nhiều forks, warmup/measurement iterations, state/blackhole hợp lý và so trên workload kiểm soát. JMH cũng **không thay thế** load test p99 end-to-end.

### 8.2. Kiểm tra bytecode/JIT

~~~bash
javap -c -p -classpath . PulseWork

javap -c -p -classpath variant PulseWork

java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining -javaagent:probe-agent.jar=inject WindowExperiment
~~~

Hai lệnh `javap` cho thấy khác biệt trong method body: bản variant có `System.nanoTime()`, `ProbeRecorder.record()` và đường `finally`/exception handler. Lệnh diagnostic có thể in quyết định `inline (hot)`, `callee is too large`, hoặc compiled code `made not entrant`; không giả định output/ordering giống nhau trên các JDK khác.

Trong lượt kiểm thử của bài, `PulseWork::calculate` instrumented có **47 bytes** và cùng một tên method xuất hiện ở log inlining với các quyết định khác nhau tại các call sites/tiers. Điều đó cho thấy **độ nóng và compiler quyết định**, không phải trạng thái “có agent” đơn giản.

### 8.3. Đo full process time để nhìn startup, không đánh đồng với method latency

Trên PowerShell:

~~~powershell
Measure-Command { java WindowExperiment | Out-Null }

Measure-Command { java -javaagent:probe-agent.jar=observe WindowExperiment | Out-Null }

Measure-Command { java -javaagent:probe-agent.jar=inject WindowExperiment | Out-Null }
~~~

Các lệnh này đo **toàn process wall time** bao gồm JVM startup, agent, workload, output và shutdown; không đo “chỉ `premain`”. Để đánh giá ứng dụng server, thay bằng mốc **process start → readiness/first successful request** do hệ thống giám sát bên ngoài xác định. Chạy nhiều trials xen kẽ thứ tự để giảm ảnh hưởng cache và CPU warmup.

### 8.4. Chẩn đoán GC/JFR

~~~bash
java -Xlog:gc*,safepoint=info -javaagent:probe-agent.jar=inject WindowExperiment

java -XX:StartFlightRecording=filename=inject.jfr,settings=profile,dumponexit=true -javaagent:probe-agent.jar=inject WindowExperiment
~~~

JFR/GC logs chỉ có ích khi workload đủ lớn/có sự kiện phù hợp. Demo chạy rất nhanh và không cố tình tạo object nhiều, nên **không kỳ vọng** sẽ có GC event khác biệt rõ hoặc profiling đủ mẫu để phân tích p99. Dùng cùng config với baseline rồi chạy một workload thực tế, đủ thời gian, thay vì “không thấy GC” nghĩa là “agent không tạo overhead”.

## 9. Phương pháp benchmark để có kết luận đáng tin

Đặt ba câu hỏi **riêng** và chọn công cụ tương ứng:

### 9.1. Cold start và first-request

- Dùng **JVM process mới cho mỗi trial**, không chạy lại `main` trong một JVM.
- Cùng JDK vendor/version, args, CPU/memory limits, GC, heap, classpath, disk/container image, dependencies.
- Đo **time-to-ready** từ ngoài JVM và thêm first-successful-request; cần readiness probe thật.
- Chạy nhiều lần, xen kẽ baseline/observe/inject, theo dõi warm filesystem/JIT cache và noise của máy.
- Tách agent `premain`, app initialization và first-request lazy class loading khi thu được dấu vết phù hợp.

### 9.2. Steady-state

- Warmup đủ lâu; không nhất thiết 80.000 loops đã đạt trạng thái ổn định.
- Đưa lưu lượng gần production: request mix, payload, retries, concurrent clients, latency của dependencies.
- Đo throughput, error/timeout, p50/p95/p99/p99.9, CPU, allocation rate, GC, JIT compilation, queue depth, dropped telemetry.
- Đảm bảo **business output và error behavior giống nhau** ở các cấu hình; instrumentation không được che exception.
- Mỗi configuration phải có nhiều forks/trials và phân phối kết quả, không chỉ một mean hay một single-shot ns/op.

### 9.3. Dynamic retransformation

Nếu agent đổi class đã loaded trong lúc chạy, đánh dấu chính xác **lúc gửi `retransformClasses`/`redefineClasses`** và đo:

- Duration riêng của API call và lỗi.
- Latency p99 trong cửa sổ đổi class.
- JIT compiled code invalidation/compilation và safepoints nếu VM cung cấp event.
- Warmup sau thay đổi, trạng thái khi method có active frames.
- Steady-state overhead sau khi mọi class đã instrument.

Đây là phép thử riêng, không thể suy ra từ demo chỉ dùng startup initial-load transformer.

### 9.4. Controls quan trọng

| Biến | Cần giữ cố định hay ghi rõ |
| --- | --- |
| JVM/GC | Version, vendor, collector, tiered flags, heap, code cache |
| Hardware | CPU quota, số cores, virtualization, frequency governor, host noise |
| Application | Binary/JARs, số loaded classes, config, startup path |
| Workload | Input/traffic mix, concurrency, tỷ lệ cache hit, network/dependency state |
| Agent | Class/method allowlist, sampling, exporter settings, helper version |
| Trials | Fork count, warmup time, measurement length, order of runs |
| Diagnostics | JFR/GC/JIT logging on/off, vì bản thân chúng có overhead |
| Reporting | p50/p95/p99, confidence/variability, correctness và failure rate |

**Một phép đo sai:** baseline đã chạy nóng 10 phút, inject mới chạy 15 giây rồi lấy throughput chênh lệch làm overhead của agent. Điều kiện JIT khác nhau khiến kết luận không thể tin.

**Một phép đo sai khác:** ghi “timer trong method đo 40 ns nên agent overhead chỉ 40 ns”. Timer trong method không đo đầy đủ chi phí thêm lời gọi timer/record, JIT effects, GC, CPU contention và queueing bên ngoài.

## 10. Tối ưu đúng chỗ theo triệu chứng

| Triệu chứng | Điều cần xem trước | Cách giảm chi phí |
| --- | --- | --- |
| Time-to-ready tăng | `premain`, helper/library loading, transformer callbacks | Lazy init có kiểm soát, lọc sớm, tránh blocking I/O/network |
| First request chậm | Lazy class load, verification, JIT warmup | Warmup hợp lý, cache đúng vòng đời, instrumentation scope hẹp |
| Steady CPU tăng | Hot hook frequency, counter contention, inlining | Giảm số điểm đo, fast path disabled, helper đơn giản |
| p99 xấu nhưng mean gần như cũ | Lock, queue/exporter, GC, safepoint | Bounded queue, async export, sampling, GC/lock profiling |
| Allocation rate tăng | Span/context/string/boxing/stack trace | Tránh tạo object/log động khi không cần |
| Metaspace tăng qua redeploy | ClassLoader/Class<?> retention, helper cache | Cleanup registrations/listeners/ThreadLocal, leak analysis |
| JIT không inline method như trước | Bytecode bloat hoặc profile khác | `javap` + `PrintInlining`, thử thu hẹp hook |
| Spike khi retransform | JVM install new class + compiled code effects | Canary, nhỏ batch, tránh thao tác hàng loạt lúc cao tải |
| Disable agent mà vẫn thấy hooks | Bytecode đã instrument trước đó vẫn nằm trong class | Disabled guard, explicit rollback/redeploy, không chỉ remove transformer |

**Không làm I/O trong hot path** nếu có thể: một event exporter có thể trả về nhanh trung bình nhưng đôi khi block lâu khi queue đầy hoặc network lỗi. Với asynchronous exporter cũng phải có giới hạn memory và backpressure/drop policy, nếu không chuyển vấn đề latency thành memory pressure.

**Không thêm nhãn metric cardinality cao** (`userId`, `orderId`, raw URL, request ID) cho từng invocation chỉ để debug. Nó có thể tạo hàng triệu metric series và backpressure ở backend, dù mã hook rất ngắn.

**Đừng tối ưu bytecode trước khi biết câu hỏi cần trả lời:** Một metric tại `CheckoutService.checkout()` có ý nghĩa thường rẻ và hữu ích hơn tạo span ở mọi getter. Nếu cần tìm hot path CPU không rõ trước, JFR/sampling profiler phù hợp hơn một đợt chèn timer hàng loạt.

## 11. Sai lầm phổ biến về tác động của agent

1. **“Transformer chỉ chạy lúc load nên steady state không bị ảnh hưởng.”** Sai khi transformer chèn hook vào method body: hook thực thi mỗi lần gọi.
2. **“Transformer trả `null` nghĩa là agent overhead bằng 0.”** Không: agent initialization và callback/filter vẫn có chi phí.
3. **“Có thêm method calls thì JIT chắc chắn không inline.”** Không: JIT có thể inline ở call site/tier khác; phải đọc log và đo.
4. **“Gỡ transformer sẽ gỡ mọi bytecode hooks.”** Không: remove chỉ hủy registration, không tự đổi definition đã cài.
5. **“Số class biến đổi cao nghĩa GC chắc tăng.”** Không: GC tăng thường liên quan allocation/live set, không chỉ callback count.
6. **“Timer `nanoTime` đo CPU của method.”** Không: đo elapsed time gồm cả blocking/scheduling/pauses.
7. **“Mean latency không đổi là đủ chứng minh không có tác dụng.”** Không: p99/timeout/queueing có thể xấu.
8. **“Cộng duration của trace con với cha để tính request total.”** Sai: khoảng thời gian lồng nhau bị đếm trùng.
9. **“Một run 120.000 loops là benchmark JIT ổn định.”** Không: cần warmup/trials/forks và kiểm soát compiler optimizations.
10. **“JFR/PrintInlining không có overhead.”** Sai: diagnostics có overhead riêng và có thể làm sai timing.
11. **“Agent disabled là miễn phí.”** Nếu bytecode vẫn chứa nhánh disabled, nhánh đó vẫn có chi phí; cần đo.
12. **“Latency sau retransform phải phản ánh version mới trên mọi active frame ngay lập tức.”** Không: active frames có thể tiếp tục code cũ.
13. **“LongAdder luôn có snapshot nhất quán khi thread khác ghi.”** Không: `sum()` dưới concurrent updates không nhất thiết atomic.
14. **“Nhìn một GC pause dài là đủ kết luận agent gây lỗi.”** Không: cần phân tích root cause, workload, logs và controls.
15. **“Dùng một số overhead % chung cho mọi Java agent.”** Không: chi phí phụ thuộc loại hook, tần suất, JVM, workload và sampling/export settings.

## 12. Tự kiểm tra và checklist trước rollout

**Câu 1.** Agent chỉ đăng ký transformer, callback trả `null`. Có thể làm startup chậm nhưng không thêm per-call bytecode vào một class không?

**Đáp án:** Có. Agent startup, class loading và callback/filter có chi phí; class bytes không đổi nếu transformer đó trả `null`.

**Câu 2.** JIT log lần đầu báo `callee is too large`, lần khác báo `inline (hot)`. Đây là mâu thuẫn?

**Đáp án:** Không. Inlining phụ thuộc call site, tier, độ nóng và profile. Cần phân tích thời điểm và code version.

**Câu 3.** Trong demo `MEASURE=120000` nhưng `probe_calls=200000`. Có sai đếm không?

**Đáp án:** Không. Bytecode hook chạy cả **80.000 warmup** và **120.000 measured** calls.

**Câu 4.** Dùng `TOTAL_NANOS / calls` tính được p99 không?

**Đáp án:** Không. Đó là trung bình theo boundary, không chứa phân phối. Cần histogram hoặc tập quan sát.

**Câu 5.** Sau `removeTransformer`, agent còn làm method chậm. Có vi phạm API?

**Đáp án:** Không. Bytecode đã inject vẫn chạy; remove không tự hoàn tác class definition.

**Câu 6.** Khi GC ít thay đổi nhưng CPU/op tăng, có thể do instrumentation không?

**Đáp án:** Có thể: clock reads, contention, context lookup, mất inlining hay compiled code growth có thể tăng CPU mà không tăng allocation rõ rệt. Cần profile CPU/JIT.

**Câu 7.** Có thể dùng stdout demo `checksum` để khẳng định overhead chính xác là bao nhiêu %?

**Đáp án:** Không. Checksum chứng minh logic không đổi; đo performance đòi nhiều runs, JIT warmup, điều kiện control và phân phối.

**Checklist:**

- [ ] Đã đo riêng process-to-ready, first request, steady state và (nếu có) dynamic retransform?
- [ ] Có baseline không agent và cấu hình observe-only để phân biệt class-loading với hook?
- [ ] Đã xác minh cùng business result/exception/timeout behavior giữa các cấu hình?
- [ ] Transformer chỉ instrument đúng class/method và lọc sớm, không làm blocking I/O trong callback?
- [ ] Đã đối chiếu bytecode method bằng `javap`, xem JIT/inlining diagnostics nếu nghi code growth?
- [ ] Đã đo CPU, allocation, GC/safepoint, throughput và p95/p99 thay vì chỉ mean?
- [ ] Có warmup đủ, nhiều JVM forks, order randomized/interleaved, cùng JDK/heap/GC/load?
- [ ] Có bounded exporter queue, sampling policy, fast path disabled và khả năng rollback?
- [ ] Có kiểm tra agents/helpers/caches không giữ lâu `Class<?>` hoặc classloader cũ?
- [ ] Có kế hoạch canary/monitoring và ngưỡng tắt hook khi overhead không chấp nhận được?

**Kết luận:** Overhead của Java instrumentation là **hiện tượng đa tầng**. Class transformer thêm việc làm trên đường startup/class loading; bytecode mới có thể làm thay đổi JIT/inlining và tạo chi phí ở mỗi invocation; allocation, GC, locking và exporter có thể khuếch đại tail latency. Chỉ kết luận sau khi **đo đúng boundary, có baseline, cùng workload/JVM và có chứng cứ JIT/GC/latency**, không dùng một con số benchmark đơn lẻ làm cam kết chung.

### Tài liệu tham khảo

- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `removeTransformer`, `retransformClasses`, `redefineClasses` và active stack frames.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transform callback, bytes đầu ra và quy tắc chuỗi biến đổi.
- [Java SE 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-javaagent`, `PrintCompilation`, `PrintInlining`, code cache và runtime flags.
- [Java SE 17 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): JDK Flight Recorder, `profile`/`default` settings và `jcmd`.
- [OpenJDK — JMH](https://github.com/openjdk/jmh): Java Microbenchmark Harness và phép benchmark có forks/warmup/measurement.
