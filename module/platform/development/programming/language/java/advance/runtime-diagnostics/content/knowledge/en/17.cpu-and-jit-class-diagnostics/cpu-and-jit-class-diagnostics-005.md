# 17.5 Khởi động nóng, tiered compilation và ảnh hưởng tới kết quả profiling

## 1. Vì sao cùng một đoạn Java có thể chạy nhanh dần?

Trên HotSpot, **một phương thức Java không nhất thiết được thực thi bằng một dạng mã cố định trong suốt vòng đời JVM**. Lần đầu, JVM thường sử dụng interpreter; khi phương thức hoặc vòng lặp được gọi đủ nhiều, JIT (*Just-In-Time compiler*) có thể biên dịch thành machine code và tiếp tục tối ưu dựa trên dữ liệu hành vi thực tế. Cơ chế **tiered compilation** phối hợp các mức biên dịch nhanh và tối ưu sâu để cân bằng **thời gian khởi động, chi phí profiling nội bộ, hiệu năng ổn định và độ chính xác của giả định tối ưu**.

Do đó, hai phép đo cùng chạy một logic có thể khác nhau vì:

- Lần đầu JVM còn phải load/verify/initialize class, tạo cấu trúc runtime, kích hoạt những đường mã chưa nóng.
- Interpreter và mã do C1 tạo ra có thể có tốc độ, chi phí thu thập profile và hình dạng stack khác C2.
- Các compiler thread có thể đang tiêu thụ CPU trong nền, cạnh tranh tài nguyên với application threads.
- C2 có thể inline method, loại allocation tạm, hoán đổi vị trí phép tính hoặc tối ưu nhánh dựa trên type profile.
- Một giả định tối ưu về type/nhánh bị phá vỡ có thể gây **deoptimization**, làm phương thức quay về đường thực thi an toàn rồi được biên dịch lại.
- GC, class loading, cache, connection pools và OS còn tạo hiệu ứng warm-up riêng, **không được mặc định quy hết cho JIT**.

**Mục tiêu bài học:** giải thích đúng các mức HotSpot, nhận ra trạng thái warm-up trong compilation log/JFR, tránh kết luận sai từ biểu đồ CPU/latency khi mã còn thay đổi, và thiết kế phép đo phân biệt **startup** với **steady-state**.

Phạm vi là HotSpot trên JDK 17+, minh họa theo JDK 21. JVM khác (chẳng hạn runtime sử dụng compiler khác, native image) có chính sách không giống toàn bộ mô tả C1/C2 dưới đây; cần xác minh JVM/version/flags thực tế.

## 2. “Cold”, “warming up” và “hot” là trạng thái quan sát, không phải số giây cố định

| Giai đoạn | Điều thường diễn ra | Dấu hiệu có thể đo | Nhầm lẫn cần tránh |
| --- | --- | --- | --- |
| **Cold start** | JVM khởi chạy; class loading, initialization; code lần đầu qua interpreter hoặc mã đã sẵn có | Startup time, số class load, compilation bắt đầu, latency request đầu | Gắn mọi độ trễ đầu tiên cho JIT |
| **Warm-up** | Phương thức/vòng lặp thường dùng đạt ngưỡng “hot”; C1/C2 compile, thu thập type profile, cache/pool khởi tạo | Compilation events, code cache tăng, throughput/latency thay đổi theo vòng | Nghĩ ứng dụng đã warm chỉ vì trôi qua 30 giây |
| **Tương đối ổn định** | Các đường mã chính đã được tối ưu phù hợp với workload hiện tại; một số cache đạt trần | Chỉ số theo các cửa sổ lặp gần nhau dưới tải tương đương | Tuyên bố toàn bộ JVM “hết JIT”; đường mã hiếm vẫn có thể nóng lên |
| **Tái tối ưu** | Workload/type distribution đổi; deopt, class loading, recompilation, code cache pressure | Spike CPU/latency, sự kiện deopt hoặc compile mới | Cho rằng một lần ổn định là ổn định mãi mãi |

Một service mở sẵn 2 giờ vẫn có thể **cold đối với một code path hiếm** mới được gọi lần đầu. Ngược lại, một job chạy vài giây có thể có vòng lặp rất nóng đủ để được OSR/JIT tối ưu ngay trong lần chạy đó.

**Warm-up phải định nghĩa theo thứ bạn đo:** startup latency cần bao gồm phần cold hợp lệ; đo peak throughput cần ghi rõ cách loại hoặc báo riêng phần warm-up. Không âm thầm bỏ dữ liệu startup rồi gọi đó là hiệu năng tổng thể của sản phẩm.

## 3. Tiered compilation trên HotSpot: Interpreter, C1 và C2

Trong HotSpot Server VM điển hình, tiered compilation thường được bật mặc định. Bảng dưới mô tả **các cấp thực thi**; con số là *compilation level* trong diagnostic output, không phải số lần method được gọi.

| Level | Cơ chế | Dữ liệu profile | Mục tiêu |
| ---: | --- | --- | --- |
| **0** | Interpreter | Có thể thu thập thông tin chạy để quyết định biên dịch | Bắt đầu thực thi nhanh về thời gian chuẩn bị |
| **1** | C1, tối ưu cơ bản | Không gắn instrumentation profiling đầy đủ | Mã native tạo nhanh, phù hợp method đơn giản/đường đi nhất định |
| **2** | C1, profiling hạn chế | Chủ yếu counter invocation/backedge | Giữ tốc độ trong khi theo dõi mức “hot” |
| **3** | C1, profiling đầy đủ | Thu dữ liệu động phục vụ quyết định/tối ưu tiếp | Cân bằng tốc độ và chất lượng profile đầu vào cho C2 |
| **4** | C2, tối ưu sâu | Sử dụng profile đã tích lũy, không nhất thiết tiếp tục tạo cùng loại profiling data | Hiệu năng dài hạn trên đường mã nóng |

Một diễn biến **thường gặp nhưng không bắt buộc**:

```text
Method mới -> Level 0 (interpreter)
               |
               +----> Level 3 (C1 + full profiling)
                           |
                           +----> Level 4 (C2 optimized)
               |
               +----> Level 2 (C1, profile hạn chế khi tải compiler thay đổi)
               |
               +----> Level 1 (C1 không profile, phù hợp method đơn giản)

Compiled code --[giả định không còn đúng]--> deoptimization
                  |
                  v
          Interpreter / code phù hợp khác
                  |
                  +----> compilation lại ở level thích hợp
```

Không phải mọi method đi đúng đường `0 → 3 → 4`. Chính sách còn xét invocation counter, số lần backedge của loop, compiler queues, kích thước method, thông tin type, khả năng compile, và các ngưỡng phụ thuộc VM/configuration. Một method hiếm có thể mãi ở interpreter; một method đơn giản có thể dừng ở level 1. Có thể có bước chuyển, thay thế hoặc loại bỏ compiled code trong quá trình chạy.

**C1** chủ yếu tối ưu nhanh với chi phí biên dịch thấp hơn; **C2** có thể cần nhiều CPU/thời gian hơn để tối ưu sâu như inlining và speculative optimizations. Điều này giải thích vì sao có thể **tốn thêm CPU cho compiler ở startup** trong khi các request về sau được xử lý nhanh hơn.

### Tiered không có nghĩa “compile tất cả ngay lập tức”

JIT thường biên dịch theo **nhu cầu quan sát được**, không phải chạy một bước compile toàn bộ bytecode trước khi service nhận request. Method có hotness cao mới có khả năng được đưa vào compile queue. Bởi vậy không thể đo “thời gian startup đã xong” rồi giả định tất cả endpoint, payload type, query path đã được tối ưu.

### OSR: vòng lặp nóng lên trước khi method trả về

**On-Stack Replacement (OSR)** cho phép chuyển một vòng lặp đang chạy lâu từ interpreted/mức cũ sang compiled code ở một vị trí an toàn khi điều kiện cho phép; không nhất thiết phải chờ method return rồi gọi lại.

Trong `-XX:+PrintCompilation`, ký hiệu `%` thường chỉ compilation cho OSR. Một method xuất hiện một lần trong request nhưng chứa loop hàng triệu iteration có thể đủ nóng để kích hoạt OSR. Khi đọc kết quả profiling, hãy xem có compilation giữa **chính một lần thực thi** hay không.

## 4. Hotness, type profile, inlining và deoptimization

### 4.1. “Hot” được quyết định bằng hoạt động, không bằng tên method

Thường có hai nguồn quan trọng:

1. **Invocation count:** method được gọi bao nhiêu lần.
2. **Backedge count:** execution quay lại đầu vòng lặp bao nhiêu lần.

Mức tải và compiler queue có thể điều chỉnh ngưỡng thực tế. Không đưa một con số cố định kiểu “chính xác 10.000 lần gọi là C2” vào bài benchmark: ngưỡng HotSpot phụ thuộc policy, build, flags và hành vi runtime.

### 4.2. Profile dữ liệu động cho phép tối ưu theo thực tế

Giả sử interface `Parser` có hai implementation `JsonParser` và `XmlParser`. Nếu phần lớn call site chỉ nhìn thấy `JsonParser` trong giai đoạn đầu, JIT có thể tối ưu theo type profile đó, inline đường gọi thường gặp và gắn kiểm tra bảo vệ. Khi workload bắt đầu có nhiều `XmlParser`, giả định trước có thể không còn có lợi hoặc bị vô hiệu; JVM có thể deopt và/hoặc compile lại để xử lý phân bố mới.

Đây là **một cơ chế có thể xảy ra**, không phải bảo đảm rằng bất kỳ interface call nào cũng deopt nếu xuất hiện subtype mới. Cần nhìn compilation/deoptimization evidence thực tế.

### 4.3. Inlining làm thay đổi hình dạng flame graph

Ví dụ hai method:

```java
static long process(long x) {
    return transform(x) + 1;
}

static long transform(long x) {
    return x * 31;
}
```

Đây là **đoạn minh họa**, không phải một chương trình độc lập. Sau tối ưu, compiler có thể inline `transform` vào `process`, giảm call overhead và thay đổi cách profiler gán frame/hotspot. Một method **ít xuất hiện hoặc biến mất** khỏi sample stack không chứng minh method không được chạy nữa; cần hiểu inlining, stack reconstruction và cách công cụ hiển thị *inlined frames*.

Không đánh đồng “40% sampled stacks” với “chính xác 40% số lời gọi hoặc 40% latency”. CPU sampling là quan sát theo thời điểm và có bias/độ phân giải hữu hạn.

### 4.4. Deoptimization không tự động là lỗi

**Deoptimization** là khả năng bảo đảm tính đúng đắn khi mã tối ưu dựa trên giả định không còn phù hợp hoặc VM cần quay về trạng thái an toàn. Có thể kèm compilation mới. Trong log, “`made not entrant`” có thể chỉ một phiên bản compiled code bị thay thế bằng phiên bản tier cao hơn hoặc không còn phù hợp; nó **không tự chứng minh** lỗi hay regression.

Đọc deopt cùng **thời điểm**, **reason/action**, method/compile id, thay đổi workload và latency. Một deopt đơn lẻ lúc startup rất khác việc deopt/recompile lặp lại liên tục trong steady-state.

## 5. Vì sao profiling thay đổi theo giai đoạn

Khi profiler lấy mẫu từ startup tới steady-state, nó đang trộn **nhiều chế độ thực thi**. Mỗi kiểu đo bị ảnh hưởng khác nhau:

| Số đo | Cold/warm-up có thể làm gì? | Cách đọc đúng |
| --- | --- | --- |
| **Wall-clock latency** | Bao gồm class loading, initialization, interpreter, JIT, queueing, pool/cache khởi tạo | Tách first-hit/cold vs đã warm, không lẫn thời gian chờ vào “CPU method” |
| **CPU profile / JFR execution samples** | Stack có thể ở interpreter/C1/C2; compiler threads hoạt động; inlining/OSR đổi attribution | Phân tích theo cửa sổ thời gian, thread, event setting, số mẫu |
| **JFR compilation events** | Số compilation thường nhiều ở giai đoạn mới nóng; có thể có C1, C2, OSR | Xác minh event enabled và threshold; không thấy event ≠ không có compile |
| **Code cache** | Native compiled code được thêm; có thể có sweeping/unloading hoặc pressure | Xem capacity/used và CodeCacheFull/Compiler queue khi cần |
| **Allocation/GC profile** | Class initialization và cache fill làm allocation tăng; C2 có thể loại một số allocation | So theo workload/sau-GC; không quy mọi allocation delta cho JIT |
| **Throughput** | Có thể tăng khi C2 hoàn tất, nhưng còn phụ thuộc GC, CPU frequency, load và I/O | Báo từng cửa sổ, điều kiện tải và phân bố |
| **p99 latency** | Có thể spike vì compiler CPU, safepoint, GC, connection setup hoặc deopt | Không kết luận nguyên nhân chỉ từ timestamp JIT gần spike |

**Vấn đề cốt lõi:** nếu lấy CPU profile suốt 60 giây gồm 10 giây cold và 50 giây warm, kết quả trung bình không đại diện hoàn toàn cho **10 giây đầu**, cũng không đại diện hoàn toàn cho **steady-state sau 5 phút**.

Nếu mục tiêu là tối ưu startup, hãy **giữ riêng** đoạn cold và phân tích classloading/compile/initialization; nếu mục tiêu là ổn định lâu dài, hãy đo sau warm-up theo tiêu chí có thể kiểm chứng. Hai cách đều đúng khi chúng trả lời hai câu hỏi khác nhau.

## 6. Dùng compilation log để biết method đã chuyển tier khi nào

Trong môi trường thí nghiệm HotSpot, bật:

```bash
java -XX:+PrintCompilation TieredWarmupDemo
```

Flag này in các hoạt động biên dịch method ra console, có thể xen giữa stdout ứng dụng. Nó làm tăng lượng log và có overhead, vì vậy **không dùng nó như một baseline “không quan sát”**. Có thể chuyển hướng stdout khi cần lưu file; kiểm tra cơ chế redirect của shell đang dùng.

Ví dụ **mang tính mô tả cấu trúc**, không phải output cam kết của demo:

```text
[timestamp] [compileId] [flags] [level] [Class::method] [bytecodeSize]
...                    %          3     TieredWarmupDemo::main  (...)
...                               3     TieredWarmupDemo::mix   (...)
...                               4     TieredWarmupDemo::mix   (...)
...                                     made not entrant
```

Khi đọc output thật, tập trung:

- **Cột thời điểm:** thường tính bằng **mili giây từ lúc JVM bắt đầu**; không tự ghép với giờ UTC nếu chưa chuẩn hóa.
- **Compilation ID:** dùng để ghép dấu vết một lần compile; không phải ID của object hay số lần gọi.
- **Level:** `3` thường là C1 full profiling, `4` là C2. Không đồng nhất “level 4” với JFR sample.
- **`%`:** compilation OSR cho code tại loop backedge.
- **`made not entrant` / `made zombie`:** trạng thái compiled code; cần ngữ cảnh trước khi gọi là deoptimization gây chậm.
- **Tên method và bytecode size:** gợi ý điều gì được biên dịch; một method còn có thể inlined vào caller khác.

Nhiều method của **JDK/framework** cũng được biên dịch, không chỉ method của ứng dụng. Một method xuất hiện nhiều lần có thể được biên dịch ở các cấp khác nhau, OSR, hoặc tối ưu lại. Không đo “chính xác số lần method chạy” bằng số dòng compile.

### Ghi compile log có cấu trúc hơn

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -XX:LogFile=hotspot-compile.xml TieredWarmupDemo
```

`-XX:+LogCompilation` và `-XX:LogFile=...` là hướng ghi chi tiết phục vụ phân tích JIT, nhưng có overhead và tệp lớn; kiểm tra quyền ghi và tác động trước khi dùng trên service thật. Bản XML có thể có thông tin chi tiết hơn compilation console, song **không tự thay thế** đo hiệu năng request.

Để khảo sát quyết định inlining trong lab:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining -XX:+PrintCompilation TieredWarmupDemo
```

Output có thể rất lớn; một lời báo “inline” cho biết quyết định của compiler trong ngữ cảnh đó, **không bảo đảm** method luôn inlined ở mọi call site hoặc mọi phiên bản compiled code.

## 7. Quan sát compiler trên JVM đang chạy

Khi có PID của JVM và JDK tool cùng quyền attach:

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.flags
jcmd 12345 Compiler.queue
jcmd 12345 Compiler.codecache
jcmd 12345 Compiler.codelist
```

Thay `12345` bằng PID thật; không lấy PID của tiến trình đã kết thúc. Các lệnh có ý nghĩa khác nhau:

| Lệnh | Cung cấp gì? | Giới hạn |
| --- | --- | --- |
| `VM.flags` | Cấu hình JVM thực tế, gồm những flag được thể hiện | Không thay thế toàn bộ lịch sử tối ưu từng method |
| `Compiler.queue` | Việc biên dịch đang chờ ở thời điểm lấy snapshot | Queue rỗng lúc quan sát không chứng minh không có compilation trước đó |
| `Compiler.codecache` | Dung lượng/sử dụng code cache và các vùng liên quan | Cache đầy có thể ảnh hưởng JIT; cache lớn một mình không phải leak |
| `Compiler.codelist` | Danh sách các compiled methods còn sống trong code cache | Snapshot, output lớn, chi phí cao hơn queue/codecache |
| `jcmd PID JFR.check verbose=true` | Recording JFR và event settings đang chạy | Không cho toàn bộ sự kiện đã rơi khỏi retention/không được ghi |

Các lệnh attach cần user/namespace phù hợp. Ứng dụng chạy trong container có thể có PID khác nhìn từ host; JVM có thể tắt attach hoặc công cụ không được đóng gói trong image runtime tối giản. Không đi tìm bằng chứng bằng cách tự ý đổi namespace/permission trong production.

## 8. JFR: xem thời gian compile, code cache và deoptimization

Khi cần ghép JIT với CPU/latency/GC theo timeline, thu JFR từ **đầu quá trình** hoặc trước khi code path quan tâm trở nên hot. Ví dụ startup recording cho chương trình ở mục 9:

```bash
java -XX:StartFlightRecording=name=jit_warmup,settings=profile,disk=true,dumponexit=true,filename=warmup.jfr,jdk.Compilation#threshold=0ms TieredWarmupDemo
```

Tại đây `jdk.Compilation#threshold=0ms` là một **setting cụ thể** để tránh bỏ qua các compilation ngắn vì ngưỡng duration. Cấu hình `default.jfc` / `profile.jfc` của từng JDK có thể lọc những compilation chỉ tốn ít thời gian; **trống event không có nghĩa JVM không JIT**. Kiểm tra setting thực tế qua `JFR.check verbose=true` (khi JVM còn chạy) hoặc lưu config `.jfc`. Việc hạ threshold có thể tăng số event và overhead; dùng cho thí nghiệm cần độ chi tiết, cân nhắc khi áp dụng lâu dài.

Sau khi JVM đã kết thúc bình thường, xác minh file:

```bash
jfr summary warmup.jfr
jfr print --events jdk.Compilation,jdk.Deoptimization warmup.jfr
jfr print --events jdk.CompilerStatistics,jdk.CodeCacheStatistics warmup.jfr
```

Tên event phải được xác nhận có tồn tại trong **JDK thực tế** qua metadata/`jfr summary`, và phải được bật bằng recording settings. Các event gợi ý:

- **`jdk.Compilation`:** thời lượng compile, compiler, level, method, compilation ID và có thể có chỉ báo OSR. Nó đo **công việc compiler**, không phải thời gian method đã chạy nhanh hơn bao nhiêu.
- **`jdk.CompilerStatistics`:** trạng thái/hoạt động compiler theo các mốc thống kê khi có trong recording.
- **`jdk.CodeCacheStatistics` / `jdk.CodeCacheFull`:** code cache và dấu hiệu áp lực lưu native code; một khoảng thiếu dữ liệu có thể do setting/period.
- **`jdk.Deoptimization`:** thông tin khi VM phát hiện tình huống cần xem xét deopt; một event riêng lẻ không chứng minh regression.
- **`jdk.ExecutionSample`:** mẫu stack của thread thực thi; so các cửa sổ trước/sau warm-up và cả số lượng mẫu hợp lệ.
- **`jdk.GarbageCollection`, `jdk.CPULoad`, thread/lock events:** xem nguyên nhân khác diễn ra đồng thời.

Trong **JDK Mission Control (JMC)**, chọn khoảng thời gian startup và ổn định riêng, lọc theo application threads và compiler threads; so JVM activity với latency/throughput từ hệ thống đo độc lập. Không tính “tỷ lệ CPU method X” chỉ dựa trên tổng số JFR event khác loại. Compilation events, periodic statistics và execution samples có **mẫu số khác nhau**.

**Giới hạn quan trọng:** JFR có thể bỏ sự kiện do threshold, disabled event, sampling, retention, chi phí/khả năng recorder; file ghi muộn không chứa lịch sử trước lúc recording bắt đầu. Cả `PrintCompilation` và JFR có overhead; **giữ nguyên công cụ và thiết lập khi so hai lần đo**.

## 9. Ví dụ Java 17+ tự chạy: latency theo từng vòng trong một JVM

Lưu nguyên mã bên dưới vào **`TieredWarmupDemo.java`**. Chương trình gọi một method chứa nhiều phép tính phụ thuộc dữ liệu trong các vòng liên tiếp, đo `ns/op` *thô* trên cùng JVM, in checksum để kết quả có tác động quan sát được và nghỉ ngắn **bên ngoài vùng đo** giữa các vòng. Đây là ví dụ để **quan sát hiện tượng**, không phải microbenchmark chuẩn.

```java
import java.time.Instant;
import java.util.Locale;

public final class TieredWarmupDemo {
    private static volatile long sink;
    private static final int OPERATIONS = 120_000;

    private static long mix(long value) {
        long x = value;
        for (int i = 0; i < 32; i++) {
            x ^= x << 13;
            x ^= x >>> 7;
            x ^= x << 17;
        }
        return x;
    }

    public static void main(String[] args) throws InterruptedException {
        int rounds = args.length == 0 ? 20
                : Integer.parseInt(args[0]);

        if (rounds < 1 || rounds > 80) {
            throw new IllegalArgumentException(
                    "rounds must be between 1 and 80");
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("mode=single JVM; rounds=" + rounds);

        for (int round = 1; round <= rounds; round++) {
            long checksum = 0;
            long started = System.nanoTime();

            for (int i = 0; i < OPERATIONS; i++) {
                long input = ((long) round << 32) ^ i;
                checksum ^= mix(input);
            }

            long elapsed = System.nanoTime() - started;
            sink = checksum;

            System.out.printf(Locale.ROOT,
                    "round=%02d end=%s ns/op=%.2f checksum=%d%n",
                    round, Instant.now(),
                    elapsed / (double) OPERATIONS, sink);

            Thread.sleep(75);
        }
    }
}
```

### Biên dịch và chạy chế độ thông thường

Trong terminal có JDK 17+:

```bash
javac TieredWarmupDemo.java
java TieredWarmupDemo
```

Các dòng có **dạng**:

```text
PID=<PID của JVM>
mode=single JVM; rounds=20
round=01 end=<timestamp> ns/op=<số đo> checksum=<số nguyên>
...
round=20 end=<timestamp> ns/op=<số đo> checksum=<số nguyên>
```

Đây là **mẫu cấu trúc output**, các trường trong dấu góc là chú thích để thay bằng giá trị thực tế; chúng **không phải stdout literal**. Thời gian `ns/op`, timestamp, checksum tùy lần chạy; không bịa tốc độ hoặc mức tăng cố định. `checksum` phụ thuộc đầu vào/thuật toán và phải ổn định về mặt logic cho cùng `round` trên cùng chương trình; còn số đo hiệu năng thay đổi theo môi trường.

Ở một số máy, vòng đầu chậm hơn rồi giảm khi interpreter/C1/C2 thay đổi; ở máy khác sự khác biệt nhỏ, dao động hoặc vòng sau còn chậm vì GC, CPU frequency, hệ điều hành, tài nguyên cạnh tranh hoặc optimization của compiler. **Không có yêu cầu** mỗi vòng phải nhanh hơn vòng trước. Một biểu đồ tăng/giảm đơn độc không xác nhận tier chuyển.

### Chạy lại với compilation log

```bash
java -XX:+PrintCompilation TieredWarmupDemo
```

Tìm `TieredWarmupDemo::mix` hoặc `TieredWarmupDemo::main` trong compile output. Đối chiếu thời điểm compile, level/OSR với sự thay đổi `ns/op`. Chỉ nói “phù hợp với thay đổi tier” nếu **có chứng cứ compile thật** và chưa loại trừ các yếu tố khác.

### Thử hai chế độ đối chiếu trong lab

```bash
java -XX:TieredStopAtLevel=1 TieredWarmupDemo
java -Xint TieredWarmupDemo
```

- `TieredStopAtLevel=1` giới hạn tier tối ưu chủ yếu ở C1 level 1: hữu ích để minh họa ảnh hưởng của việc không đi tới C2. Không mặc định nó luôn chậm hơn ở mọi workload; runtime flags khác cũng ảnh hưởng startup.
- `-Xint` chạy theo interpreter, **không dùng JIT machine code**. Nó thường chậm hơn đáng kể với compute-intensive loop, nhưng đây là phép so cơ chế, không phải con số speedup áp dụng mọi ứng dụng.
- `-XX:-TieredCompilation` nếu thử riêng sẽ **tắt cơ chế tiered**, nhưng HotSpot vẫn có thể biên dịch bằng compiler khác/theo chính sách non-tiered; **không đồng nghĩa** `-Xint`.

Các lần chạy riêng tạo JVM mới nên không thể lấy `round=20` của JVM trước làm “round tiếp theo” của JVM sau. Nên lặp nhiều lần, đổi thứ tự chạy để giảm ảnh hưởng OS/filesystem/cache; khi cần benchmark nghiêm túc dùng JMH và nhiều forks.

### Khi nào lệnh `jcmd` có tác dụng với demo?

Demo có thể kết thúc nhanh; `jcmd PID Compiler.queue` chỉ quan sát JVM **còn sống** ở thời điểm thực hiện. Có thể chạy với số vòng lớn hơn trong giới hạn program cho phép:

```bash
java TieredWarmupDemo 80
```

Rồi ở terminal khác thay đúng PID được in. Nếu tiến trình đã thoát, đừng suy “JIT không chạy” từ việc attach thất bại. Với profiling dài hạn, thiết kế workload/lifetime riêng; không biến demo nhỏ thành dịch vụ vô hạn.

## 10. Đọc kết quả demo mà không gán nhầm nguyên nhân

Ghi một bảng cho **cùng JVM và cùng flags**:

| Round | ns/op đo được | Compilation gần cửa sổ này | GC / CPU / môi trường | Kết luận tạm |
| --- | ---: | --- | --- | --- |
| 1–2 | Giá trị thực tế | Có/không, C1? | Class init? CPU boost? | Cold / warming; chưa đủ kết luận |
| 3–7 | Giá trị thực tế | OSR/C1/C2? | GC? background compiler? | Chuyển trạng thái có thể diễn ra |
| 8–15 | Giá trị thực tế | Ít compile hơn? | Mức tải tương đương? | Có thể gần ổn định |
| 16–20 | Giá trị thực tế | Có deopt/recompile không? | Nhiễu ngoại lai? | Kiểm tra độ ổn định, không mặc định |

**Cách đọc có điều kiện:**

- Nếu `mix` xuất hiện level 3 rồi level 4 và các cửa sổ sau giảm `ns/op` lặp lại, giả thuyết JIT giúp tăng tốc có cơ sở; cần kiểm soát thêm CPU/GC/overhead trước khi quy định lượng giảm là do C2.
- Nếu `ns/op` giảm **trước** khi có level 4, có thể do C1, OSR, cache, CPU frequency hoặc những thay đổi khác.
- Nếu có level 4 nhưng `ns/op` không giảm, phương thức có thể đã khá hiệu quả ở tier thấp, tốn thời gian ở code khác, hoặc workload quá đơn giản/nhiễu cao.
- Nếu một round bỗng chậm rồi phục hồi, xem GC pause, OS scheduling, compiler queue, CPU throttling, deopt hoặc code cache pressure; không quy ngay cho “JIT bị lỗi”.
- Nếu `-Xint` chậm hơn, điều đó cho thấy compiled execution hữu ích với workload này; **không** cho biết C2 đóng góp bao nhiêu so với C1 nếu chưa so đúng tier.

**Vấn đề đơn vị:** `elapsed/OPERATIONS` ở demo đo **thời gian một lần gọi `mix` trung bình trong vòng ngoài**, gồm cả overhead vòng và checksum; không phải thời gian một request HTTP. Trước khi dùng số đó để báo cáo ứng dụng phải xác định thao tác đo, ổn định CPU, sample size, confidence và môi trường.

## 11. Sai lệch đặc trưng của CPU profiling trong warm-up

### 11.1. Compiler thread có thể chiếm CPU

Trong startup, C1/C2 compilation tiêu thụ CPU **ngoài request thread**. Nếu CPU toàn process tăng, có thể một phần là compiler background; nhìn profile của một request thread có thể không phản ánh tải trên compiler threads. Ngược lại, một CPU flame graph chỉ nhìn application threads có thể bỏ sót compiler CPU.

Giải pháp: kiểm tra JFR compiler statistics/events, thread CPU usage và OS CPU metrics; tách *compiler CPU* khỏi *application CPU* khi đưa ra giả thuyết.

### 11.2. Inlining và OSR làm thay đổi stack attribution

Lúc interpreter, profiler có thể quan sát một chuỗi call frames rõ ràng. Khi C2 inline, một hoặc nhiều frame có thể được trình bày khác tùy cách profiler tái dựng logical stacks; không thể trừ số mẫu ở method A trước/sau và khẳng định logic A đã “biến mất”. OSR có thể thay trạng thái thực thi khi loop đang chạy, làm một khoảng đo có nhiều dạng mã.

### 11.3. Độ dài cửa sổ lấy mẫu và mẫu số

Nếu baseline chỉ 20 execution samples nhưng steady có 2.000 samples, tỷ lệ hot method khác nhau có thể do **độ bất định và selection bias**, chưa chắc code thực sự đổi profile. So cùng cấu hình JFR, khoảng quan sát, workload và số sample đủ lớn; phân tích cả absolute event counts và **denominator đúng của loại event**.

### 11.4. CPU time khác latency

Một method tốn nhiều CPU trong JIT profile không đồng nghĩa nó gây tương ứng phần lớn **wall-clock latency**. Request có thể chờ DB/network/lock, bị queue hoặc chịu GC/safepoint; phải đối chiếu traces, request latency và JVM activity ở cùng khoảng thời gian.

### 11.5. Profile thu muộn bỏ mất câu chuyện startup

Nếu recording bắt đầu sau warm-up, dù JFR thấy code đang ở tier 4 vẫn **không** cho biết bao nhiêu thời gian cold start đã dùng để compile hay classload. Muốn phân tích startup phải bắt đầu thu từ JVM launch hoặc từ thời điểm đủ sớm trước event quan tâm, đồng thời kiểm tra retention/dump không xóa mất phần đầu.

## 12. Thiết kế phép đo để phân biệt startup và steady-state

### Mục tiêu A — ứng dụng phản hồi request đầu tiên nhanh đến đâu?

Chỉ số nên đo:

1. JVM process start → socket/service ready, nếu bạn thực sự quan tâm thời gian khởi động.
2. First successful request latency của từng code path đại diện.
3. p50/p95/p99 của **các request đầu** hoặc 30–60 giây đầu, với lưu lượng/payload đã định nghĩa.
4. JIT compilation, class loading, GC, cache/connection pool initialization trùng giai đoạn.
5. Số lỗi/timeout/retry do client nhìn thấy trong cold phase.

Không loại first-hit latency rồi công bố đó là startup performance. Khi cold startup là trải nghiệm quan trọng, warm-up phải được xem như **một phần của bài toán**, không phải nhiễu cần gạt đi.

### Mục tiêu B — service chạy ổn định xử lý được bao nhiêu?

1. Định nghĩa workload, concurrency, dataset, JVM/GC flags, CPU/memory limits.
2. Đợi **warm-up theo tiêu chí**: các cửa sổ throughput/latency dao động trong mức chấp nhận và không có hoạt động compile/deopt đột biến liên tục. Đây vẫn là tiêu chí thực nghiệm, không phải “JIT đã tắt”.
3. Chỉ bắt đầu **measurement window** sau mốc đã định, ghi rõ thời gian chờ và số thao tác warm-up.
4. Lấy nhiều cửa sổ dưới cùng mức tải, tính phân bố/độ bất định; đối chiếu GC, compiler, CPU throttling và I/O.
5. Lặp lại từ **JVM mới (fork)** nhiều lần để thấy variance giữa các lần khởi chạy; kiểm soát thứ tự thử nghiệm nếu so hai biến thể.
6. Báo cáo throughput, p50/p95/p99 và CPU/GC cùng điều kiện; không chốt bằng một giá trị ns/op duy nhất.

**Không có một số vòng warm-up cố định đúng cho mọi JVM.** Cần cùng workload và bằng chứng hành vi đủ ổn định; đôi khi cache/DB/network warm-up lâu hơn JIT. Với microbenchmark, dùng **JMH** vì nó hỗ trợ warm-up iterations, measurement iterations, forks, tránh nhiều lỗi tối ưu hóa và thiết kế benchmark sai. Demo ở mục 9 chỉ dùng để học hiện tượng.

### Mục tiêu C — hiệu quả của một tối ưu code nhỏ

Khi muốn so **A vs B**:

- Chạy hai bản cùng JDK/GC/flags, hardware/CPU quota, data và workload.
- Định nghĩa cold hay steady **trước** khi đo; lưu riêng cả hai nếu sản phẩm cần.
- Dùng nhiều JVM forks; không chạy A trước, warm JVM rồi B sau trong cùng process mà gọi đó là so sánh công bằng.
- Tránh dead-code elimination bằng cách làm kết quả có thể quan sát, nhưng cũng tránh side-effect/blackhole sai làm méo tác vụ.
- Chọn metric trực tiếp trả lời mục tiêu: CPU, throughput, tail latency, allocation hoặc startup.
- So tổng chi phí vận hành và độ ổn định, không chỉ một lần đạt p50 tốt.

Nếu có JIT flag khác nhau, coi đó là **thay đổi runtime policy**, không phải chỉ thay một “công tắc đo” trung tính. Ghi flag trong báo cáo.

## 13. Ví dụ phân tích số liệu theo hai cửa sổ

Giả sử dưới **cùng một tải giả định** và không có thay đổi deployment:

| Khoảng | Requests/s | p95 latency | Compiler activity | GC |
| --- | ---: | ---: | --- | --- |
| Cold 0–30 s | 500 | 180 ms | C1/C2 tăng, class init | Có hoạt động |
| Warm 30–90 s | 500 | 105 ms | Ít compile hơn, một số code lên level 4 | Có hoạt động |
| Stable 90–180 s | 500 | 80 ms | Không thấy compile đột biến | Không có pause bất thường |

Những con số **hoàn toàn giả định** chỉ để minh họa phương pháp. Có thể phát biểu:

> “Trong 3 cửa sổ cùng workload, p95 giảm từ 180 xuống 80 ms, tức giảm khoảng 55,6%; đồng thời phần lớn compilation quan sát được tập trung ở giai đoạn đầu. Điều này **phù hợp** với hiệu ứng warm-up, nhưng chưa đủ chứng minh toàn bộ giảm là do JIT. Cần kiểm tra cache/pool/GC, compiler thread và thực hiện lại nhiều lần.”

Không nên viết: “JIT chính xác giúp giảm 100 ms p95”. Phần giảm này còn có thể do warm connection pools, class init hoàn tất, DB cache hoặc biến động OS. Nếu muốn quy lượng đóng góp, cần thí nghiệm có kiểm soát, có thể dùng flag thực nghiệm hoặc đo thành phần riêng. Đừng lấy chênh lệch của hai percentile rồi gán cho một method.

### Đối chiếu “tốc độ gấp đôi” cũng có giới hạn

Một vòng trong demo từ `100 ns/op` xuống `50 ns/op` có tỷ lệ `100/50 = 2` lần throughput lý tưởng trên cùng thao tác; đó là so sánh giả định cho **micro-operation** và **cùng môi trường**, không có nghĩa request end-to-end nhanh gấp đôi. Mô hình request gồm network/DB/GC và công việc khác; chỉ tối ưu một phần không thể biến toàn bộ latency theo cùng tỷ lệ.

## 14. Những tình huống thường gặp khi phân tích JIT

| Quan sát | Các cách giải thích còn mở | Hướng xác minh |
| --- | --- | --- |
| First request rất chậm, sau 30 request tốt dần | Class init, cache/pool warm, interpreter→C1/C2, lazy configuration | JFR classloading/compilation, logs, request trace |
| CPU cao lúc startup nhưng request throughput còn thấp | Compiler threads, class load, GC, DB warm-up, contention | Thread CPU + JFR compiler stats + metrics ngoài JVM |
| `PrintCompilation` có level 4, latency vẫn cao | Request chủ yếu chờ I/O/lock, method khác bottleneck, chưa warm toàn bộ paths | Request spans, flame graph đúng cửa sổ, per-endpoint metrics |
| Số sample ở method A giảm sau warm-up | Inlining, optimization, workload mix hoặc thay đổi sampler | JIT logs, stack reconstruction, per-thread sample count |
| Có `made not entrant` sát spike | Phiên compiled code bị thay thế hoặc giả định đổi; trùng thời gian chưa đủ | JFR deopt, reason, repeated measurements, GC |
| Mỗi lần deploy p99 xấu vài phút | JIT, cache/pool warm, traffic shifting và startup load | Đồng bộ ready/startup probes, classloading, workload |
| Service chạy lâu đột nhiên chậm khi traffic type mới xuất hiện | Cold path, uncommon trap/deopt, cache miss, GC, external dependency | Tách traffic mix, compile/deopt events, traces |
| Code cache chật, compiler queue tăng | Áp lực code cache/compilation, nhiều generated classes hoặc đổi workload | `Compiler.codecache`, `Compiler.queue`, JFR CodeCache events |
| JFR không có compilation event nhưng có compiled methods | Recording bắt đầu muộn, threshold lọc, event disabled, retention gap | `PrintCompilation` trong lab, check settings, codelist |
| `-XX:TieredStopAtLevel=1` tốt hơn trong startup nhỏ | C1 khởi động nhanh; C2 có chi phí compile chưa thu hồi lợi ích | So cả cold và steady qua nhiều forks |

## 15. Mười bốn sai lầm nên tránh

1. **“Warm-up = sleep 30 giây”.** Không có workload phù hợp thì method quan trọng có thể vẫn cold.
2. **“Đạt level 4 nghĩa toàn bộ service tối ưu xong”.** Chỉ một method/version được biên dịch; còn các paths khác.
3. **“TieredStopAtLevel=1 tương đương -Xint”.** C1 vẫn tạo native code, interpreter-only là cơ chế khác.
4. **“-TieredCompilation tức không có JIT”.** Non-tiered HotSpot vẫn có thể biên dịch; cần phân biệt với interpreter-only.
5. **“Một dòng compile = một lần gọi method”.** Compilation là hoạt động của compiler, không phải method invocations.
6. **“Nhiều `made not entrant` = JVM có lỗi”.** Có thể là việc thay thế code tier thấp hoặc trạng thái hợp lệ khác.
7. **“Không có JFR compilation event = không có JIT”.** Event có thể bị lọc theo threshold, tắt, hoặc ngoài recording window.
8. **“Sample stack ít method hơn = ít logic chạy hơn”.** Inlining/OSR và attribution thay đổi.
9. **“CPU tăng khi warm-up chắc là app code nóng”.** Compiler threads và class initialization cũng dùng CPU.
10. **“Đo round đầu của A với round cuối của B”.** Hai trạng thái không tương đương.
11. **“Một JVM chạy ấm đã đủ thống kê”.** JIT/OS/GC variance cần nhiều forks/cửa sổ.
12. **“Chèn println ở vòng đo không ảnh hưởng”.** I/O trong hot loop làm méo phép đo; demo in sau mỗi vòng.
13. **“Không thấy deopt trong file là chắc chắn không có”.** Phải biết loại event có bật, mốc JFR và retention.
14. **“p99 giảm đúng bằng hiệu quả của C2”.** Request latency gồm nhiều thành phần; tương quan cần kiểm tra cơ chế.

## 16. Bài tập tự đánh giá

**Câu 1.** Một method xuất hiện level 3 và level 4 ở compilation log. Điều này cho biết gì?

*Gợi ý:* Có các lần biên dịch ở C1 full profiling và C2 cho method/code version; đây là bằng chứng tiered activity. Nó **không** cho biết số lời gọi hoặc mức cải thiện latency của endpoint.

**Câu 2.** JFR ghi nhận ít event `jdk.Compilation` trong giai đoạn startup. Có kết luận là hầu hết code chưa JIT?

*Gợi ý:* Chưa. Kiểm tra recording start, `enabled`, `threshold`, tool/JDK và data retention; ở một số profile event compile ngắn bị lọc.

**Câu 3.** Vòng loop chạy một lần rất lâu nhưng `PrintCompilation` có ký hiệu `%`. Ký hiệu đó liên quan điều gì?

*Gợi ý:* OSR compilation có thể xảy ra khi loop đã ở trên stack; không cần chờ method được gọi lại nhiều lần.

**Câu 4.** Code path A chỉ được gọi lần đầu sau khi service chạy 3 giờ. Có thể gọi nó “warm” vì process đã chạy lâu?

*Gợi ý:* Không. Process uptime khác với mức hotness và lịch sử profiling của **đúng code path đó**.

**Câu 5.** Tại sao flame graph trước warm-up và sau warm-up có thể không hiển thị cùng khung method?

*Gợi ý:* Inlining và OSR thay đổi cách code được thực thi; profiler có thể hiển thị/tái dựng frame khác. Đồng thời workload mix/threads và phương pháp lấy mẫu có thể đổi.

**Câu 6.** Khi `-XX:TieredStopAtLevel=1` cho startup tốt nhưng throughput sau 10 phút kém hơn default, cấu hình nào “tốt” hơn?

*Gợi ý:* Phụ thuộc mục tiêu ứng dụng: job ngắn, FaaS hay service chạy dài. Phải báo **cả startup, steady-state, memory/CPU** và phân bố request dưới điều kiện tương đương; không chọn từ một số duy nhất.

**Thực hành:** chạy `TieredWarmupDemo` ở chế độ mặc định, bật `PrintCompilation` và chạy `-Xint` trong những JVM riêng. Ghi thời điểm/level compile của `mix`, các round `ns/op`, đồng thời đánh dấu nhiễu GC/CPU nếu có. Sau đó thu JFR từ JVM startup, xem `jdk.Compilation` và `jdk.Deoptimization`; viết một nhận định phân biệt *bằng chứng quan sát* và *giả thuyết hiệu năng*. Không bắt buộc level 4 phải xuất hiện ở mỗi run.

## 17. Tài liệu gốc để tra cứu

- [Oracle JDK 21 — Java HotSpot VM Performance Enhancements: Tiered Compilation](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html).
- [Oracle JDK 21 — `java` launcher: `PrintCompilation`, `LogCompilation`, `TieredCompilation` và JIT flags](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle JDK 21 — `jcmd`: `Compiler.queue`, `Compiler.codecache`, `Compiler.codelist`, `JFR.check`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — `jfr`: `summary`, `print`, `metadata`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [Oracle Java 21 — `jdk.jfr`: event settings, `threshold`, `period`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
- [Microsoft OpenJDK engineering — How Tiered Compilation Works in OpenJDK](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/).
- [OpenJDK — tiered compilation policy và các level/transition](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.hpp).
- [OpenJDK — `default.jfc` và compiler-related JFR event settings](https://github.com/openjdk/jdk/blob/master/src/jdk.jfr/share/conf/jfr/default.jfc).

**Nguyên tắc áp dụng:** mỗi số CPU/latency được tạo ra trong một **trạng thái JVM và một cửa sổ workload cụ thể**. Hãy biết method còn ở interpreter/C1/C2, có compilation/deopt trong cửa sổ đo hay không, rồi mới so profile. Warm-up là một **quá trình có thể quan sát và kiểm chứng**, không phải một khoảng chờ cố định hoặc lý do để bỏ qua dữ liệu bất lợi.
