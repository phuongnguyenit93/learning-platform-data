# 17.7 Nhận diện code cache đầy hoặc hoạt động biên dịch bất thường trước khi đổi tham số

## 1. Vấn đề cần chẩn đoán

Một ứng dụng Java chạy ổn sau khi khởi động, nhưng vài giờ sau CPU tăng, throughput giảm hoặc p95/p99 xấu đi. Trong log đôi khi xuất hiện thông báo liên quan đến **CodeCache** hoặc compiler; người vận hành định tăng ngay `-XX:ReservedCodeCacheSize`, số compiler threads hoặc ngưỡng JIT. Việc đó có thể che mất nguyên nhân và tạo áp lực native memory/CPU mới.

Cần phân biệt ít nhất ba tình huống:

1. **Code cache/đúng code heap đang bị áp lực:** không đủ chỗ thích hợp để lưu compiled code mới; có thể xảy ra thông báo code cache full, tạm dừng/không tiếp tục biên dịch ở một giai đoạn và hiệu năng giảm.
2. **Hoạt động biên dịch bất thường dù vẫn còn chỗ:** hàng đợi compiler kéo dài, số compilation/failed compilation/deoptimization tăng, compiler threads dùng CPU nhiều, class hoặc method churn khiến JIT phải làm lại công việc.
3. **Warm-up hoặc biến động bình thường:** JIT biên dịch nhiều ở đầu vòng đời hoặc sau thay đổi tải; queue ngắn, code heaps có vùng trống và hiệu năng ổn định sau warm-up. CPU cao có thể do business code, GC hoặc native work chứ không phải compiler.

**Đầu ra mong muốn:** có dữ liệu theo thời gian về tình trạng từng code heap, compiler queue/compilation events, CPU và workload; xác định giả thuyết bằng chứng rồi mới cân nhắc thay đổi tham số HotSpot. Bài dùng thuật ngữ và công cụ **HotSpot JVM**, chủ yếu JDK 17–24; bản build/JDK khác cần kiểm tra lệnh thực tế.

## 2. JIT, compiled code và Code Cache

Khi JVM thực thi bytecode, một phần code ban đầu được diễn giải (interpreter). Trong HotSpot với **tiered compilation**, mã được thực thi thường xuyên có thể được biên dịch ở các mức tối ưu khác nhau, thường liên quan đến compiler C1 và C2. JVM thu thập profiling, tối ưu và có thể **deoptimize** compiled method khi các giả định về kiểu/class/path không còn phù hợp. Quá trình này hữu ích nhưng cũng cần CPU và nơi lưu compiled code.

**Code cache** là bộ nhớ *native executable* chứa các `nmethod` đã biên dịch và những đoạn code runtime khác do JVM sử dụng. Nó khác:

- **Java heap:** lưu đối tượng Java, có GC quản lý; tăng `-Xmx` không tự tăng code cache.
- **Metaspace:** chủ yếu chứa metadata của class; tải nhiều class có thể tác động gián tiếp đến JIT, nhưng metaspace ≠ code cache.
- **Compilation queue:** danh sách công việc chờ compiler xử lý; queue dài không tự đồng nghĩa code cache hết chỗ.
- **JIT compiler CPU:** công sức để tạo/tối ưu machine code; compiler CPU cao không tự chứng minh code cache đã đầy.

Khi **segmented code cache** được bật, HotSpot có thể chia vùng thành những code heaps:

| Code heap | Vai trò điển hình | Cần quan sát |
| --- | --- | --- |
| `non-nmethods` | Interpreter/runtime stubs, adapters và đoạn code không phải `nmethod` | Không nên gộp bừa với compiled Java methods; sức chứa và khả năng thu hồi khác |
| `profiled nmethods` | Compiled methods ở giai đoạn có thông tin profiling, thường gắn tiered compilation | Áp lực tăng khi nhiều code được biên dịch ở các tier phù hợp |
| `non-profiled nmethods` | Compiled methods không cần profiling bổ sung, thường bao gồm code tối ưu cao | Có thể là vùng chịu áp lực trong ứng dụng lâu chạy |

**Cấu hình heap phân đoạn không phải lúc nào cũng giống nhau.** `-XX:+SegmentedCodeCache`, `-XX:ReservedCodeCacheSize`, tiered compilation và build của JDK quyết định tổ chức vùng. Khi segmented, ba code heaps có ngân sách riêng; việc *toàn bộ code cache còn dư* không bảo đảm heap cụ thể cần cấp chỗ còn đủ block liên tục. Trong chế độ không segmented, một vùng code cache duy nhất có cách báo cáo khác. Không tự giả định mọi ứng dụng có đúng ba heap.

HotSpot có **code sweeper** để dọn compiled methods không còn sử dụng/thích hợp. Nhiều `nmethod` có thể bị invalidated, không còn entrant, rồi thu hồi theo cơ chế JVM; quá trình không nhất thiết diễn ra ngay tức thì. Phân mảnh và trạng thái block trống cũng đáng xem khi có lỗi phân bổ, ngoài phép tính đơn giản `used/max`.

## 3. Nhận diện triệu chứng và bẫy suy luận

| Triệu chứng | Giả thuyết nên kiểm tra | Chưa đủ để kết luận |
| --- | --- | --- |
| Log `CodeCache is full` / `Compiler has been disabled`, JFR `jdk.CodeCacheFull`, đúng code heap gần hoặc hết chỗ, compilation status thay đổi | **Code cache pressure/đã xảy ra full**; có thể ảnh hưởng JIT và throughput | Một cảnh báo ở startup cũ không chứng minh hiện vẫn bị disable; có thể đã thu hồi/vận hành lại |
| `Compiler.queue` tồn đọng qua nhiều snapshot, compiler threads dùng CPU cao, nhiều `jdk.Compilation` hoặc compilation failure | **Compiler backlog / compilation churn**; phân biệt tác vụ hợp lệ do warm-up với bất thường kéo dài | Queue dài một lần không chứng minh cache thiếu chỗ |
| JFR `jdk.Deoptimization` tăng, cùng methods được biên dịch lại nhiều lần | Speculation invalidation, thay đổi kiểu/class hoặc logic workload; có thể dẫn đến recompilation | Một vài deoptimization là hành vi JVM bình thường |
| Code heap gần mức capacity nhưng queue rỗng, không có full events, throughput/latency ổn | Code được lưu và tái sử dụng; **chưa thấy tác hại** | Phần trăm `used/max` cao đơn lẻ không phải sự cố |
| CPU cao, code heaps dư, compilation events hiếm, execution samples ở application methods | **Business CPU-bound**, thuật toán hoặc GC khác | Không giải quyết bằng `ReservedCodeCacheSize` |
| Code cache `used` tăng sau deploy, rồi chững lại | JIT warm-up hoặc tải mới khiến code được compile | Không phải leak chỉ vì chưa giảm sau khi tải xuống |

**Bằng chứng mạnh** cần ghép: cùng khoảng thời gian có lỗi/performance regression **và** code heap không còn sức chứa phù hợp hoặc có `CodeCacheFull`, trạng thái compiler/queue thay đổi, người dùng thấy hiệu năng xấu đi. Một bộ đếm không thay thế toàn bộ chuỗi nguyên nhân.

### Nhận biết compiler dừng và hoạt động trở lại

Một số cấu hình HotSpot có thể **ngừng/tạm ngừng compiler khi code cache đầy**, sau đó quét/thu hồi code và tiếp tục biên dịch nếu điều kiện cho phép. Vì thế cả hai câu “JIT đã bị tắt vĩnh viễn” và “JIT chắc chắn sẽ tự phục hồi” đều quá mạnh nếu chưa thấy log và status ở các thời điểm khác nhau.

Nếu compiler không còn tạo được code tối ưu mới, những đường chưa warm-up có thể tiếp tục chạy bằng interpreted hoặc compiled code ở tier thấp hơn; hiệu quả tùy workload. **Không suy ra mọi compiled method cũ bị xóa** chỉ vì có thông báo compiler disabled.

## 4. Quy trình thu thập bằng chứng trước khi tuning

### Bước 1 — Chốt phiên bản, workload và mốc thời gian

Ghi **Java vendor/build**, `java -version`, tiến trình/PID và CPU quota, giới hạn bộ nhớ container, uptime, thời điểm deploy, số classes loaded/unloaded, request/s, in-flight, p50/p95/p99, error rate, GC pauses và process CPU. Xác định **tốc độ biến đổi** trong khoảng bất thường: code heap đầy dần trong giờ hay bùng một lần ngay khi warm-up? Đo cùng traffic/workload nếu so hai bản chạy.

Đầu tiên xác minh các cờ JVM đang có:

~~~bash
# Thay <PID> bằng PID của JVM đích.
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> VM.flags -all
~~~

`VM.flags -all` có nhiều dòng; tìm các cờ thực liên quan như `ReservedCodeCacheSize`, `InitialCodeCacheSize`, `SegmentedCodeCache`, `TieredCompilation`, `CICompilerCount` và `UseCodeCacheFlushing` trên đúng JDK. Không dùng giá trị mặc định trên blog của phiên bản khác thay giá trị runtime.

### Bước 2 — Chụp đúng CodeCache và Compiler queue

~~~bash
jcmd <PID> Compiler.codecache
jcmd <PID> Compiler.queue
jcmd <PID> Compiler.CodeHeap_Analytics aggregate
~~~

- `Compiler.codecache`: in **layout, size, used, max_used, free** hoặc các thống kê tương ứng của code heaps và thông tin compilation tùy bản HotSpot. Quan sát từng heap, không chỉ một tổng.
- `Compiler.queue`: chụp **các methods đang xếp hàng** chờ biên dịch. Queue là snapshot; chạy thêm vài lần cách nhau đủ để thấy tiến triển trước khi kết luận bị backlog.
- `Compiler.CodeHeap_Analytics aggregate`: bổ sung góc nhìn trạng thái code heap, phân bố khoảng trống và hoạt động sweeper khi cần. Trên JDK hỗ trợ, có các function như `UsedSpace`, `FreeSpace`, `MethodCount`. Lệnh có thể giữ `CodeCache_lock` trong lúc phân tích, nên chọn thời điểm và mức chi tiết phù hợp.
- `Compiler.codelist` (tùy chọn) in compiled methods hiện còn sống, hữu ích khi cần so những method bị tích lũy trong code cache; output có thể lớn, tác động cao hơn lệnh codecache thông thường.

Dùng `jcmd <PID> help` và `jcmd <PID> help Compiler.CodeHeap_Analytics` để xác nhận các lệnh/mức tác động trên JVM thực tế. Lưu **nhiều snapshot** (ví dụ lúc bình thường, ngay trước giảm throughput, trong khoảng sự cố, sau hồi phục); ghi timestamp và load cùng mỗi snapshot. Không chỉ gọi một lần khi sự cố đã qua.

### Bước 3 — Kết hợp JFR để thấy diễn tiến theo thời gian

Có thể mở recording hữu hạn từ JVM đang chạy:

~~~bash
jcmd <PID> JFR.start name=jit-triage settings=profile duration=60s filename=jit-triage.jfr
# Sau khi recording đã hoàn tất:
jfr summary jit-triage.jfr
jfr print --events jdk.CodeCacheFull,jdk.CodeCacheStatistics,jdk.Compilation,jdk.CompilationFailure,jdk.CompilerStatistics,jdk.Deoptimization jit-triage.jfr
~~~

**Diễn giải event, không chỉ tên event:**

| Event | Hỏi điều gì | Lưu ý |
| --- | --- | --- |
| `jdk.CodeCacheFull` | Có thời điểm code heap báo full không, ở heap nào? | Event có thể hiếm và phụ thuộc cách bật; không có event không phủ nhận sự cố trước recording |
| `jdk.CodeCacheStatistics` | Dung lượng/nhóm code heap thay đổi ra sao theo recording? | Tần suất sự kiện và trường dữ liệu khác nhau theo JDK/settings |
| `jdk.Compilation` | Những compilation attempts nào đã diễn ra, thời lượng, compiler/tier và phương thức? | Compilation nhiều ngay warm-up chưa phải bất thường |
| `jdk.CompilationFailure` | Có compilation thất bại và reason cụ thể không? | Failure có thể do hạn chế optimizer/phương thức phức tạp, không tự đồng nghĩa cache full |
| `jdk.CompilerStatistics` | Thống kê hoạt động compiler nào xuất hiện? | Dùng xu hướng và ngữ cảnh; có thể không được bật trong mọi template |
| `jdk.Deoptimization` | Có compiled code bị deopt, với lý do nào? | Deopt có thể bình thường khi speculation bị phủ nhận |

Lệnh `jfr summary` cho **event count thực được ghi**. Nếu một loại event không có trong file, kiểm tra **event enabled/period/threshold của recording**; nhiều event chỉ xuất hiện khi điều kiện đặc biệt xảy ra. Không kết luận “không bao giờ full” từ 60 giây không có `CodeCacheFull`. Có thể mở `.jfr` bằng **JDK Mission Control** để đối chiếu timeline CPU, compiler events, code cache metrics, GC, class loading, JIT/deoptimization và thời điểm request latency tăng. Tên trang JMC phụ thuộc phiên bản.

### Bước 4 — Đo CPU của compiler và những nhánh khác

Compiler C1/C2 chạy trên các compiler threads và có thể dùng CPU đáng kể trong giai đoạn warm-up hoặc compilation churn. Dùng OS process/thread CPU, JFR ThreadCPULoad/Compiler events hoặc CPU profiler **có hỗ trợ JVM native/compiler threads**. `jdk.ExecutionSample` chủ yếu quan sát mã Java đang thực thi, nên không mặc định thấy đầy đủ phần CPU của native compiler threads.

Đặt cạnh số compilation, queue và `codecache used/free`:

- CPU tiến trình tăng **cùng compiler queue tồn đọng và compilation events kéo dài** → có cơ sở điều tra compiler backlog.
- CPU tăng nhưng queue rỗng, class loading ổn định và code cache còn dư → profile business methods, GC và native work.
- Không gian code heap giảm tới điểm đầy, có full event/log, rồi các compilation mới giảm hoặc compiler status thay đổi → có cơ sở điều tra code cache.

### Bước 5 — So sánh trước/sau thay đổi một biến

Không đổi hàng loạt `ReservedCodeCacheSize`, `CICompilerCount`, `TieredCompilation`, `CompileThreshold` cùng một lần. Nếu muốn xác minh giả thuyết, chọn một cấu hình thử trên staging, giữ workload/container/JDK nhất quán, đo lại:

- Code heap utilization, free blocks, `CodeCacheFull` count và compilation status;
- Compiler queue, compilation/deoptimization/failure rates;
- Process/compiler CPU, throughput, p95/p99, lỗi;
- Native memory/container headroom và thời gian warm-up.

Mục tiêu là chứng minh **đúng bottleneck đã đổi** và hiệu năng người dùng cải thiện; không chỉ khiến cảnh báo biến mất.

## 5. Cây quyết định: điểm nghẽn đang nằm ở đâu?

~~~text
CPU/p99 xấu hoặc có cảnh báo JIT
             |
             v
  Kiểm tra JVM flags + CodeCache từng heap + logs/JFR
             |
     Có CodeCacheFull/log full gắn thời điểm lỗi?
        /                              \
      Có                              Không/chưa rõ
      |                                  |
      v                                  v
  Kiểm tra heap nào,             Compiler.queue có tăng
  free blocks, sweeper,          kéo dài qua nhiều snapshot?
  compile status                         /       \
      |                                Có        Không
      v                                 |          |
  Xác nhận impact                       v          v
  + code cache pressure           JFR Compilation/   CPU samples,
      |                            Failure/Deopt,     GC, I/O, class
      v                            compiler CPU        load/workload
  Tìm nguyên nhân code                  |                |
  tích lũy, phân mảnh,                  v                v
  class/method churn;              Compilation churn  Khả năng không
  cân nhắc tuning có QA             hoặc warm-up?       phải code cache
~~~

Cây này **không phải phép kiểm tra nhị phân tuyệt đối**. Có thể vừa code cache pressure vừa compiler churn; queue rỗng ở snapshot hiện tại không chứng minh trước đó không có backlog. Ưu tiên tương quan theo timestamp và phép thử can thiệp.

## 6. Các tình huống chẩn đoán minh họa

### Tình huống A — Đúng code heap hết chỗ

Sau deploy, hệ thống sinh nhiều phương thức được JIT biên dịch. Log tại `t1` xuất hiện `CodeCache is full`, JFR `jdk.CodeCacheFull` tại cùng khoảng, `Compiler.codecache` cho thấy **một code heap cụ thể** gần hết `free`, compiler tạm disabled rồi resumed (hoặc vẫn disabled) và p99 tăng theo pha hoạt động. Đây là bộ bằng chứng mạnh cho **code cache pressure**.

Điều tra tiếp: code heap nào; tăng sau class loading hoặc code generation nào; code có được sweeper tái thu hồi; có fragmentation/free blocks phù hợp không; workload có nhảy từ warm-up sang loại path mới không. Nếu code tồn tại nhiều do thực sự có nhiều methods hot, tăng capacity có thể hữu ích **sau đo**. Nếu code churn do class loader leak, dynamic proxy hoặc công cụ tạo class lặp vô hạn, chỉ tăng capacity có thể trì hoãn lần full tiếp theo.

### Tình huống B — Queue dài nhưng cache còn nhiều chỗ

Một đợt burst mới chạm rất nhiều methods chưa được biên dịch. `Compiler.queue` tăng trong vài snapshot; OS cho thấy compiler CPU cao, JFR `jdk.Compilation` tăng, nhưng các heaps vẫn có dư đáng kể, không có `CodeCacheFull` tương ứng. Đó có thể là **warm-up hợp lệ** hoặc compiler capacity/workload churn, chưa phải cache exhaustion.

Nếu queue tự tiêu hết, latency trở về nền và compilation rate giảm, đây nhiều khả năng là warm-up. Nếu cùng một đường code lặp đi lặp lại mất nhiều compilation CPU, xem class churn, deoptimization reasons, generated code, class loaders và Compiler failures. Tăng `ReservedCodeCacheSize` không giải quyết việc code **chưa được biên dịch kịp**.

### Tình huống C — Deoptimization và recompile lặp

Một service thường xuyên thay class shape, chạy dynamic invocation hoặc liên tục đi qua các kiểu object khác nhau. JFR cho thấy deoptimization và compilation lặp ở những phương thức/nhánh tương ứng, compiler CPU cao và throughput giảm, nhưng code cache chưa đầy. Đặt giả thuyết **unstable profiling/speculation hoặc class/method churn**; xác nhận bằng traces và các thay đổi đầu vào/tải.

Deoptimization không phải lúc nào là lỗi: HotSpot có thể bảo thủ điều chỉnh code tối ưu khi giả định không đúng. Chỉ coi là bất thường khi tần suất/số lần recompile đáng kể, tương quan performance regression và có code path xác định.

### Tình huống D — CPU cao không liên quan JIT

Process dùng gần hết CPU quota, `Compiler.queue` thường rỗng, compiled code ổn định, JFR `jdk.ExecutionSample` tập trung ở vòng lặp serialize/crypto và không có codecache-full evidence. Nguyên nhân khả dĩ là **workload CPU-bound**. Điều tra thuật toán/dữ liệu/parallelism trước khi chỉnh JIT flags.

### Tình huống E — Code cache dùng nhiều nhưng hệ thống khỏe

Sau warm-up, code cache occupancy cao và giữ ổn định hàng giờ; không có full events/log, compiler status enabled, p99 và throughput ổn. Chỉ số occupancy cao **không phải một incident độc lập**. Thiết lập giám sát xu hướng và headroom, không đổi `ReservedCodeCacheSize` chỉ vì một ngưỡng phần trăm tùy ý.

## 7. Lab Java 17+: quan sát CodeHeap và thời gian compiler

Lab này dùng **Java Management API** để đọc memory pools có tên `CodeHeap` hoặc `Code Cache` và `CompilationMXBean`. Nó cố ý thực thi code để JIT có cơ hội warm-up, rồi in nhiều snapshot. Mục đích là **nhận diện và đo**, không ép Code Cache full. Kết quả thay đổi theo vendor/JDK, CPU, tiered compilation và môi trường.

Tạo file **`JitCodeCacheProbe.java`**:

~~~java
import java.lang.management.CompilationMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.util.Locale;

public final class JitCodeCacheProbe {
    private static volatile long sink;

    private static long mix(long n) {
        for (int i = 0; i < 100; i++) {
            n ^= n << 13;
            n ^= n >>> 7;
            n ^= n << 17;
        }
        return n;
    }

    private static void workload() {
        long value = 0;
        for (int i = 0; i < 250_000; i++) {
            value ^= mix(i + 1L);
        }
        sink = value;
    }

    private static void snapshot(String label) {
        CompilationMXBean compiler =
                ManagementFactory.getCompilationMXBean();
        long compileMs = -1;
        if (compiler != null
                && compiler.isCompilationTimeMonitoringSupported()) {
            compileMs = compiler.getTotalCompilationTime();
        }
        System.out.printf(Locale.ROOT,
                "phase=%s totalCompilationTimeMs=%d%n",
                label, compileMs);

        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            String name = pool.getName();
            String normalized = name.toLowerCase(Locale.ROOT);
            if (!normalized.contains("codeheap")
                    && !normalized.contains("code cache")) {
                continue;
            }
            MemoryUsage usage = pool.getUsage();
            if (usage == null) {
                continue;
            }
            System.out.printf(Locale.ROOT,
                    "pool=%s usedKiB=%d committedKiB=%d maxKiB=%d%n",
                    name, usage.getUsed() / 1024,
                    usage.getCommitted() / 1024,
                    usage.getMax() / 1024);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 1
                || (args.length == 1 && !args[0].equals("--inspect"))) {
            System.out.println("Usage: java JitCodeCacheProbe [--inspect]");
            return;
        }

        System.out.println("pid=" + ProcessHandle.current().pid());
        snapshot("start");

        for (int batch = 1; batch <= 4; batch++) {
            workload();
            snapshot("batch" + batch);
        }

        if (args.length == 1) {
            System.out.println("inspectionWindowSeconds=20");
            Thread.sleep(20_000);
        }
        System.out.println("checksum=" + sink);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac JitCodeCacheProbe.java
java JitCodeCacheProbe
~~~

**Dạng output** (giá trị và tên pool thay đổi; không có stdout cố định):

~~~text
pid=<PID>
phase=start totalCompilationTimeMs=<số hoặc -1>
pool=CodeHeap 'non-nmethods' usedKiB=<...> committedKiB=<...> maxKiB=<...>
pool=CodeHeap 'profiled nmethods' usedKiB=<...> committedKiB=<...> maxKiB=<...>
pool=CodeHeap 'non-profiled nmethods' usedKiB=<...> committedKiB=<...> maxKiB=<...>
phase=batch1 totalCompilationTimeMs=<...>
...
phase=batch4 totalCompilationTimeMs=<...>
...
checksum=<giá trị số nguyên>
~~~

**Đọc số liệu:**

- Tên `pool` là tên runtime thực; môi trường không segmented có thể hiển thị `Code Cache` thay vì ba `CodeHeap`.
- `usedKiB` là dung lượng đang dùng được MXBean báo trong code memory pool; `committedKiB` và `maxKiB` có nghĩa khác nhau. `maxKiB=-1` là giá trị API có thể dùng khi max chưa xác định, không diễn giải thành code cache âm.
- `totalCompilationTimeMs` là bộ đếm **tích lũy** thời gian compiler theo `CompilationMXBean` khi có hỗ trợ; `-1` có nghĩa không được hỗ trợ. Nó **không phải duration của batch**, không phải thời gian biên dịch riêng phương thức `mix`, và không thể dùng riêng để tính CPU saturation.
- Một hoặc vài pool tăng `used` sau warm-up là bình thường. Lab không đủ methods để bảo đảm code cache đầy hoặc tạo `jdk.CodeCacheFull`; nếu không xuất hiện warning là kết quả hợp lý.

Để kiểm tra bằng `jcmd`, chạy lệnh này ở terminal thứ nhất:

~~~bash
java JitCodeCacheProbe --inspect
~~~

Lúc chương trình in `inspectionWindowSeconds=20`, mở terminal thứ hai, thay `<PID>` bằng số vừa in:

~~~bash
jcmd <PID> Compiler.codecache
jcmd <PID> Compiler.queue
jcmd <PID> Compiler.CodeHeap_Analytics aggregate
~~~

**Lưu ý thực nghiệm:** chương trình chỉ giữ cửa sổ 20 giây để attach, không cố tình ép đầy cache. Nếu bạn muốn khảo sát một sự cố thực, thực hiện các lệnh trên **PID của ứng dụng đích** và đo thêm JFR/CPU/throughput trong cùng thời gian.

Có thể tạo recording JFR khi chạy ví dụ:

~~~bash
java -XX:StartFlightRecording=filename=jit-probe.jfr,settings=profile,dumponexit=true JitCodeCacheProbe
jfr summary jit-probe.jfr
jfr print --events jdk.CodeCacheFull,jdk.CodeCacheStatistics,jdk.Compilation,jdk.CompilationFailure jit-probe.jfr
~~~

`jit-probe.jfr` là file mới sinh ra khi chương trình hoàn tất. Một recording bình thường có thể **không có** CodeCacheFull hoặc CompilationFailure; đó là điều mong đợi trong lab. Các event CodeCacheStatistics/Compilation có thể tùy cấu hình ghi. Nếu muốn thí nghiệm JFR có thể kiểm soát, chỉnh recording profile ở staging; không thử ép CodeCache full trên production.

## 8. Khi nào mới cân nhắc thay tham số?

Sau khi chẩn đoán, phân biệt **chỉnh dung lượng** và **chỉnh hoạt động compiler**:

| Điều đã xác nhận | Việc nên ưu tiên | Cấu hình chỉ cân nhắc sau khi đo |
| --- | --- | --- |
| Đúng code heap thực sự hết chỗ, có warning/event và performance impact | Xem code churn, sweeper, fragmentation, số compiled methods và cấu trúc segmented | `-XX:ReservedCodeCacheSize=<size>`; nếu segmented, nghiên cứu các ngân sách `NonNMethodCodeHeapSize`, `ProfiledCodeHeapSize`, `NonProfiledCodeHeapSize` tương thích |
| Compiler backlog do lượng compilation tăng đột biến | Kiểm tra warm-up, code generation, dynamic proxies, class churn, compilation failures | `CICompilerCount`/tier strategy chỉ sau khi profiler chứng minh compiler CPU/queue là bottleneck |
| Recompile/deopt bất thường | Tìm lý do thay đổi types/classes, code path hoặc build/dependency đổi | Không vội ép `CompileThreshold` hay tắt tiered JIT; các cờ có thể ảnh hưởng startup/steady-state và che lỗi |
| Code cache cao nhưng không có full/stall | Theo dõi capacity và diễn tiến, không có tác động user | Chưa cần đổi flag |
| CPU-bound business code, GC, I/O | Tối ưu đúng tầng và tăng CPU/downstream capacity nếu cần | Tuning CodeCache thường không đúng nguyên nhân |

**Không coi các con số default trong tài liệu là giá trị runtime.** `ReservedCodeCacheSize` phụ thuộc JDK, lựa chọn tiered compilation và cấu hình hiện tại; `SegmentedCodeCache` có thể bật hoặc tắt. Những tham số thay cấu trúc code cache thường phải đặt lúc startup và restart. Dung lượng lớn hơn có chi phí virtual/native memory và có thể đẩy process gần giới hạn container; cần xem memory headroom.

**Không thử “chữa” bằng cách vô hiệu code-cache flushing** (`UseCodeCacheFlushing`), tắt JIT/tiered compilation hoặc tăng compiler threads tùy tiện. Tắt flushing có thể làm áp lực codecache khó hồi phục hơn; tắt tiered làm đổi chế độ compilation/throughput. Những thay đổi này cần bài đo riêng và rollback plan, không phải bước đầu chẩn đoán.

### Kế hoạch thử nghiệm thay đổi tham số có bằng chứng

1. Giữ **JDK/build, CPU quota, traffic, data, class-loading pattern, GC settings** giống nhau ở baseline và candidate.
2. Chỉ đổi **một** cờ liên quan tới nguyên nhân đã xác định, ghi flags thực qua `VM.flags -all`.
3. Chạy từ cold start qua warm-up đến steady state; đo cả thời gian warm-up lẫn throughput/p95/p99 lâu dài.
4. So JFR `CodeCacheFull`, các code heaps, compiler queue/CPU, compilation failures/deoptimization, GC và memory footprint.
5. Chỉ nhận thay đổi khi nó giải quyết nguyên nhân mà không làm xấu latency, CPU hoặc giới hạn bộ nhớ; có hướng rollback nếu tải khác tái hiện vấn đề.

## 9. Những lỗi diễn giải thường gặp

1. **“Code cache used 90% nghĩa là đã full.”** Sai: có thể vẫn cấp phát bình thường; phải xem heap cụ thể, free blocks, logs/events và ảnh hưởng thực tế.
2. **“Code cache đầy thì Java heap hết chỗ.”** Sai: code cache là vùng native executable, khác `-Xmx`; metaspace cũng khác.
3. **“Tăng `ReservedCodeCacheSize` sẽ hết mọi lỗi JIT.”** Sai: compiler queue CPU-bound, deoptimization lặp và generated-code churn không tự biến mất.
4. **“`Compiler.queue` rỗng chứng minh không có sự cố.”** Sai: đó là snapshot; compiler có thể đã tạm disabled hoặc backlog vừa qua.
5. **“Một lần compilation failure là compiler hỏng.”** Sai: JIT có thể bỏ một tối ưu hoặc fallback, phụ thuộc lý do và kết quả thực thi.
6. **“Nhiều compilation là bất thường.”** Sai: warm-up, load classes và profile mới khiến JIT hoạt động là điều thiết kế.
7. **“Mọi deoptimization là regression.”** Sai: speculative optimization cần deopt khi giả định không còn đúng; cần đánh giá tần suất và cost.
8. **“Khi có full event thì JIT tắt mãi mãi.”** Sai: tình trạng có thể thay đổi sau sweeping/flushing; xem compiler status theo thời gian.
9. **“NMT Code committed cho biết code heap còn trống đủ block.”** Sai: NMT mô tả các vùng VM cấp phát, không thay thế `Compiler.codecache`/heap analytics.
10. **“CPU cao chắc do C2 compiler.”** Sai: profile code ứng dụng, GC, native và compiler threads theo đúng loại sự kiện.
11. **“Một bản ghi JFR không có CodeCacheFull là chưa từng full.”** Sai: recording có time window và event configuration, không thấy trong khoảng đo không loại trừ trước đó.
12. **“Càng nhiều compiler threads càng nhanh.”** Sai: compiler workers tranh CPU với threads phục vụ request và có thể làm tail latency xấu hơn.

## 10. Checklist sự cố trước khi thay cờ JVM

- [ ] Đã ghi JDK vendor/build, `VM.command_line`, `VM.flags -all`, CPU/memory quota và thời gian deploy.
- [ ] Có throughput, p50/p95/p99, errors, process CPU, compiler-thread CPU, GC và class-load trend **cùng khoảng thời gian**.
- [ ] Có nhiều snapshot `Compiler.codecache` theo từng heap; biết chính xác heap nào còn/thiếu chỗ.
- [ ] Có nhiều snapshot `Compiler.queue` và biết queue có tiến triển hay không.
- [ ] Đã kiểm tra log/JFR `jdk.CodeCacheFull`, `jdk.CodeCacheStatistics`, `jdk.Compilation`, `jdk.CompilationFailure`, `jdk.Deoptimization` theo cấu hình recording thực.
- [ ] Đã phân biệt warm-up hợp lệ, codecache pressure, compiler backlog, compilation churn và CPU/GC/I/O không liên quan.
- [ ] Đã xét `Compiler.CodeHeap_Analytics` khi nghi fragmentation/sweeper/code pressure.
- [ ] Nếu nghi code cache full, có bằng chứng tác động tới compilation status hoặc latency/throughput, không chỉ % used.
- [ ] Nếu muốn chỉnh flag, có **một giả thuyết → một biến → phép đo xác nhận → rollback**.
- [ ] Báo cáo kết luận ghi rõ quan sát, mức độ tin cậy và điểm chưa được xác minh.

### Tài liệu chuẩn theo phiên bản

- Oracle JDK 21 — Java launcher / Advanced JIT Compiler Options và Code Heap State Analytics: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21 — `jcmd`, `Compiler.codecache`, `Compiler.queue`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — JFR và công cụ chẩn đoán: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JFR Event Reference/JMC events (`CodeCacheFull`, `Compilation`, `CompilationFailure`): https://docs.oracle.com/en/java/java-components/jdk-mission-control/8/jmc-flightrecorder/constant-values.html

**Tiêu chí kết luận:** trước khi tăng code cache hoặc thay tham số JIT, phải trả lời được **đúng heap nào bị thiếu sức chứa, compiler đang làm gì, sự kiện đó có trùng thời điểm hiệu năng xấu đi hay không, và thay đổi dự kiến giải quyết bottleneck nào**.