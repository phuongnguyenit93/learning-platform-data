# Warm-up, trạng thái ổn định và khác biệt giữa thời gian khởi động với hiệu năng đỉnh

## 1. Tại sao cùng một phương thức Java chạy lúc đầu chậm hơn lúc sau?

Với **HotSpot JVM**, bytecode Java có thể được thực thi bằng **interpreter**, sau đó những phương thức hoặc vòng lặp có lợi được **JIT (Just-in-Time) compiler** dịch thành mã máy tối ưu. Trong quá trình chương trình chạy, JVM còn thu thập thông tin về kiểu đối tượng, nhánh điều kiện và tần suất gọi, nạp class, giải quyết liên kết, khởi tạo dữ liệu, mở kết nối, làm nóng cache và thực hiện garbage collection (GC).

Do đó, hai lần chạy **cùng một đoạn source code** có thể có thời gian khác nhau:

- **Cold start:** tiến trình JVM mới bắt đầu, nhiều class chưa nạp/khởi tạo, nhiều method chưa được JIT compile, business caches chưa sẵn sàng.
- **Warm-up:** một hoặc nhiều thành phần đang chuyển đổi trạng thái: JIT biên dịch và tái biên dịch, profiling trưởng thành, code cache tăng, thread pools và connection pools hình thành, dữ liệu hoặc OS page cache được làm nóng.
- **Steady state — trạng thái ổn định:** hệ thống hoạt động trong một khoảng đo mà phân bố throughput/latency, allocation, GC, CPU, compilation và workload không còn xu hướng chuyển tiếp lớn; vẫn có nhiễu và biến động tự nhiên.
- **Peak performance — hiệu năng đỉnh:** throughput lớn nhất hoặc latency thấp nhất theo một **định nghĩa và tài nguyên cụ thể**, đạt được ở một giai đoạn thí nghiệm. Nó **không tự chứng minh** hệ thống ổn định, đáp ứng SLO, hoặc duy trì được mức ấy trong production.

**Đề bài không chỉ hỏi “JIT có nhanh hơn interpreter không”.** Cần hiểu *khi nào* hệ thống bắt đầu phục vụ, *khi nào* kết quả đo đáng tin, *tại sao* một lần chạy nhanh không phải kết quả bền vững và *mục tiêu nào* cần tối ưu cho loại ứng dụng cụ thể.

> **Quy tắc vàng:** `time to first useful result`, `time to readiness`, `time to steady-state throughput` và `peak throughput` là **bốn phép đo khác nhau**. Không đánh đồng thời gian khởi động với tốc độ của một vòng lặp đã nóng.

## 2. Một timeline điển hình từ process launch đến trạng thái ổn định

~~~text
Thời gian →
OS start Java process
      |
      +-- JVM initialization, class loading, verification/linking
      |
      +-- Application/bootstrap/static initializers
      |
      +-- First successful request / first useful result
      |         |
      |         +-- Class/method nạp thêm theo đường xử lý thực
      |         +-- Interpreter/C1, profiling, C2 compilation (tùy HotSpot)
      |         +-- Cache, connection pool, GC/heap occupancy thay đổi
      |         |
      +-- Readiness signal (do ứng dụng định nghĩa)
      |         |
      +-- Warm-up workload, JIT/code cache/GC tiến tới nhịp vận hành
      |         |
      +-- Candidate steady-state measurement windows
      |         |
      +-- Peak throughput point hoặc latency mục tiêu
~~~

**Các mốc không bắt buộc có thứ tự tuyệt đối như sơ đồ.** Một service có thể báo readiness trước khi mọi route nóng; một hệ khác chỉ readiness sau khi preload dữ liệu; background class loading hoặc recompilation có thể diễn ra **sau** một khoảng tưởng như đã ổn định. Đỉnh throughput có thể xuất hiện trước hoặc sau steady-state window, thậm chí ở điểm saturate làm p99 latency rất xấu.

### 2.1. Startup latency — thời gian khởi động

Định nghĩa phải có **hai mốc rõ ràng**:

- `process_start → main entry`: từ lệnh khởi chạy đến khi bước vào `main`.
- `process_start → first result`: từ process launch đến request thành công đầu tiên / kết quả nghiệp vụ đầu tiên.
- `process_start → ready`: đến khi readiness probe đáp ứng contract hệ thống.
- `deploy → ready`: còn chứa image pull, container create, scheduling, network và orchestration; **không còn chỉ là JVM startup**.

Một JVM có thể vào `main` rất nhanh nhưng application mất nhiều giây để tạo connection pool hoặc tải model. Ngược lại, ứng dụng báo ready sớm nhưng first requests sau ready bị chậm do class/JIT còn lạnh.

**Đừng gọi `main` in `READY` là bằng chứng toàn bộ service đã sẵn sàng**, trừ khi chương trình thật có protocol readiness phản ánh dependencies, routes và khả năng phục vụ mục tiêu.

### 2.2. Warm-up duration — khoảng chuyển tiếp

Có thể định nghĩa warm-up là **một tập requests hoặc một khoảng thời gian** được chạy trước khi thu thập số liệu chính. Nhưng `warmup = 5s` chỉ là *chính sách thí nghiệm*, **không phải cam kết JVM đã JIT compile mọi method sau 5 giây**.

Một service có hàng chục route có thể làm nóng route A rồi vẫn lạnh route B khi traffic mix đổi. Một method với input loại `Cat` được profile trước có thể bị deoptimize khi lần đầu gặp `Dog`. Warm-up hợp lệ phải đi cùng **representative workload** và kiểm tra hoạt động thực tế, không chỉ chờ đồng hồ.

### 2.3. Steady state — phải được đo và kiểm nghiệm

Một khoảng đo là ứng viên steady state khi ít nhất:

1. **Offered workload ổn định** (arrival rate, request mix, payload, concurrency, data sizes).
2. **Throughput, p50/p99, CPU/GC metrics** không có trend chuyển pha rõ rệt ngoài noise dự kiến.
3. **Số lượng JIT compilations và deoptimizations** không xuất hiện các cơn bùng phát kéo dài tác động lớn.
4. **Live set và heap occupancy** có nhịp tương đối ổn định; không âm thầm tích lũy leak.
5. **External state** như DB cache, TLS sessions, page cache, thread pools đã đi vào trạng thái đại diện.
6. Đã đo qua **nhiều cửa sổ thời gian**, không chỉ một average gộp từ lúc app khởi động.

Đây là **định nghĩa thực dụng có kiểm chứng**, không phải một flag JVM bật lên báo `STEADY_STATE=true`. Một service dùng nhiều feature theo giờ/ngày có thể **không bao giờ đạt một steady state toàn cục duy nhất**; khi đó đo riêng từng regime tải.

## 3. Cơ chế interpreter và tiered compilation trên HotSpot

### 3.1. Interpreter giúp bắt đầu thực thi ngay

Bytecode được JVM thực thi theo contract ngôn ngữ, và HotSpot có interpreter. Interpreter không cần biên dịch thành native optimized code cho mọi method trước khi chạy. Điều đó thuận lợi cho startup/fallback, nhưng các đoạn code được gọi lặp lại nhiều thường có cơ hội được JIT tối ưu.

Không suy luận rằng **toàn bộ một ứng dụng luôn interpreter trong X requests đầu**, rồi chuyển đồng loạt sang compiled. Các methods có thể được JIT compile ở **những thời điểm khác nhau**; một phần code đang interpreter trong khi phần khác đã compiled.

### 3.2. C1 và C2 — trade-off compilation cost và code quality

Trong mô hình HotSpot tiered compilation thường dùng với JDK 17:

- **C1** hướng tới compilation tương đối nhanh, có những tiers thu thập hoặc tận dụng profiling ở các mức khác nhau.
- **C2** có thể sử dụng thông tin profile để thực hiện optimization mạnh hơn, tốn CPU/thời gian compile hơn nhưng thường tạo code tốt hơn cho những hot paths.
- JVM lựa chọn compilation policy dựa trên số lần gọi, loop backedges, profile data, compiler queue và các điều kiện runtime.

Có thể hình dung đơn giản:

~~~text
                 Bytecode / interpreter (tier 0)
                              |
                    profiling và hotness
                              |
               C1 tiers (1 / 2 / 3, tùy đường đi)
                              |
                   thêm profiling / hotness
                              |
                C2 optimized code (tier 4)

Sau đó vẫn có thể:
  - deoptimization → interpreter / compiled tier khác
  - recompilation sau khi profile thay đổi
  - code invalidation / code cache cleanup
~~~

**Đây không phải pipeline cứng bắt buộc cho mỗi method.** Có thể có tier transitions khác nhau, inlining và OSR, phương thức rất nhỏ, code được sử dụng hiếm, VM flags khác biệt. Không đòi “mọi method đều phải đi qua đủ 0→1→2→3→4”.

JDK/implementation có thể dùng compiler khác hoặc cách tổ chức khác; **C1/C2/tiered** là các chi tiết nổi bật của HotSpot, không phải cấu trúc bắt buộc của Java Virtual Machine Specification.

### 3.3. Hot code, call counters, backedges và OSR

HotSpot dùng profiling và hotness estimates, trong đó có **method invocation count** và **loop backedge activity**. Một vòng lặp chạy rất lâu trong một lần gọi có thể trở nên hot ngay khi method chỉ gọi một lần. **On-Stack Replacement (OSR)** giúp VM chuyển một loop đang chạy sang optimized compiled code tại vị trí thích hợp, thay vì phải đợi method kết thúc rồi gọi lại.

Vì vậy:

- “Chỉ gọi method 1 lần nên không bao giờ JIT” là **sai** với loops đủ hot.
- “Gọi 10.000 lần thì chắc C2” cũng **sai**; compiler thresholds/policy không phải constant portable.
- `-XX:CompileThreshold` và các JIT flags có ngữ nghĩa/phạm vi phụ thuộc tiered mode và JDK; không dùng một giá trị như định luật tổng quát.

### 3.4. Speculative optimization và deoptimization

JIT có thể dựa vào profile hiện tại. Ví dụ một virtual call site trong warm-up chỉ nhận object của một class; runtime có thể tối ưu devirtualization và inlining theo giả định có kiểm tra. Khi input kiểu khác xuất hiện hoặc giả định không còn đúng, code có thể **deoptimize** và chạy an toàn theo semantics Java, rồi được recompile khi cần.

~~~text
Warm-up: 99.9% PaymentCard
        |
        v
JIT có profile gần đơn hình, tối ưu nhánh phổ biến
        |
New traffic: PaymentCrypto hoặc edge-case chưa từng thấy
        |
        v
Uncommon trap / deoptimization / recompilation có thể xảy ra
        |
        v
Latency spike ngắn hạn, hành vi sau đó đổi
~~~

Đây là **tình huống mô hình**, không tuyên bố rằng mỗi thay đổi input type chắc chắn deoptimize hoặc luôn tạo một spike có cùng duration.

**Warm-up bằng dữ liệu không đại diện** có thể cho ra một optimized code path đẹp nhưng làm kết quả đo sau đó nhiễu hoặc còn tệ hơn dưới traffic thực.

## 4. Warm-up chịu ảnh hưởng của nhiều yếu tố ngoài JIT

| Thành phần | Khi lạnh | Trong warm-up | Điều có thể ổn định |
| --- | --- | --- | --- |
| **Class loading/linking** | Chưa nạp những classes ít sử dụng | Load khi route/feature được gọi | Ít class loads bất ngờ trên hot paths |
| **Static initialization** | Một số `<clinit>` chưa chạy | Khởi tạo lazy singletons, registries | Ít init đột biến ở request path |
| **Interpreter/JIT** | Nhiều methods interpreted/C1 | Compilation/profiling, OSR, inlining | Ít transitions có ảnh hưởng lớn |
| **Code cache** | Native code cache còn ít compiled methods | Compiled code được thêm/swept | Số đo không tăng bùng phát liên tục |
| **GC/heap** | Heap ít live objects | Promotion, aging, caches được giữ, GC frequency thay đổi | Live set/GC pattern đại diện |
| **Application caches** | Empty/cold | Load DB rows, templates, regex, config, class metadata | Cache-hit rate đại diện |
| **Thread/connection pools** | Chưa tạo hoặc ít active | Spawn, handshake, kết nối, TLS sessions | Capacity/queueing tương đối ổn |
| **OS page cache** | Disk pages chưa resident | Files/resources được truy cập | Fewer disk misses ở workload tương tự |
| **External dependencies** | DB/cache/server ở trạng thái ban đầu | Connection establishment/prepared statements | Response times hợp tải thực |

**Một hiện tượng latency giảm trong 20 giây đầu không đủ chứng minh do JIT.** Cần phân rã thời gian và sử dụng compilation logs/JFR, allocation profiles, class-load logs và dependency metrics.

### `static` và lazy initialization làm first-hit khác steady-state

Một expression như `Pattern.compile`, load JDBC driver, initialize JSON serializer, mở TLS connection hoặc lần đầu gọi một dependency phức tạp có thể chiếm CPU/I/O và class loading. JIT có thể chưa phải phần chi phối.

Điều này đặc biệt rõ với ứng dụng serverless, command-line tool và autoscaling burst: **mỗi process mới lại có startup/cold paths**. “Service đã nhanh sau 5 phút” có thể không cứu first-response SLO khi instance bị tạo và huỷ liên tục.

### CDS và AOT: không suy luận quá phiên bản

**Class Data Sharing (CDS)** và ứng dụng preload/class sharing có thể cải thiện một số phần class loading/startup, nhưng không mặc nhiên đưa tất cả methods của ứng dụng tới **C2 peak**. Các kỹ thuật AOT và VM warm startup tiếp tục tiến hóa giữa JDK releases; **không sử dụng tính năng JDK đời mới như thể JDK 17 có cùng behavior**.

Nếu bật CDS/AppCDS hay flags đặc thù, cần benchmark **cùng JVM build, cùng artifact và cùng cấu hình**; đo startup riêng và peak riêng.

## 5. Java 17 runnable lab: nhìn các batches trước và sau warm-up

Chương trình dưới đây:

1. Chạy **4 warm-up batches**.
2. Đo **6 measured batches** dùng cùng hàm tính toán, cùng số operations.
3. Công bố số iterations không đổi, checksum đầu ra cố định và thời gian từng batch **phụ thuộc môi trường**.
4. Công khai rằng một batch nhanh hơn **không tự chứng minh đã đạt steady state**.

Tạo file **`WarmupLab.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public final class WarmupLab {
    private static volatile long published;

    static long compute(int seed) {
        long x = seed + 0x9E3779B97F4A7C15L;
        for (int i = 0; i < 256; i++) {
            x ^= x >>> 27;
            x *= 0x3C79AC492BA7B653L;
            x ^= x >>> 33;
        }
        return x & 0xffL;
    }

    static long runBatch(int firstSeed, int ops) {
        long sum = 0;
        for (int i = 0; i < ops; i++) {
            sum += compute(firstSeed + i);
        }
        published = sum;
        return sum;
    }

    public static void main(String[] args) {
        final int warmupBatches = 4;
        final int measuredBatches = 6;
        final int operationsPerBatch = 6000;
        final long[] elapsedNs = new long[measuredBatches];

        System.out.println("warmupBatches=" + warmupBatches);
        System.out.println("measuredBatches=" + measuredBatches);
        System.out.println("operationsPerBatch=" + operationsPerBatch);

        for (int i = 0; i < warmupBatches; i++) {
            long start = System.nanoTime();
            runBatch(100_000 + i * operationsPerBatch, operationsPerBatch);
            long elapsed = System.nanoTime() - start;
            System.out.println("warmup" + i + "Ns=" + elapsed);
        }

        long checksum = 0;
        for (int i = 0; i < measuredBatches; i++) {
            long start = System.nanoTime();
            checksum += runBatch(
                    200_000 + i * operationsPerBatch, operationsPerBatch);
            elapsedNs[i] = System.nanoTime() - start;
            System.out.println("measured" + i + "Ns=" + elapsedNs[i]);
        }

        long[] ordered = elapsedNs.clone();
        Arrays.sort(ordered);
        long totalNs = 0;
        for (long n : elapsedNs) totalNs += n;

        System.out.printf(Locale.ROOT, "avgBatchMs=%.3f%n",
                totalNs / (measuredBatches * 1_000_000.0));
        System.out.println("checksum=" + checksum);
        System.out.println("lastBatchPublished=" + published);
    }
}
~~~

### 5.1. Biên dịch/chạy

~~~bash
javac --release 17 WarmupLab.java
java WarmupLab
~~~

**Các dòng output có giá trị xác định theo chương trình:**

~~~text
warmupBatches=4
measuredBatches=6
operationsPerBatch=6000
~~~

Sau đó chương trình in `warmup0Ns=...` đến `warmup3Ns=...`, `measured0Ns=...` đến `measured5Ns=...`, và `avgBatchMs=...`. **Các thời gian này là số động, không có một stdout nanosecond cố định** trên mọi CPU/JIT/OS.

**Hai dòng kết quả tính toán cố định:**

~~~text
checksum=4596631
lastBatchPublished=763004
~~~

Phần mã đã được **biên dịch với `javac --release 17` và chạy trên OpenJDK 24**, ở chế độ HotSpot JIT mặc định và `-Xint`. Hai chế độ đều cho ba dòng cấu hình và hai dòng checksum nói trên.

**Một lần đo cục bộ đã quan sát** khoảng `avgBatchMs=2.023` với JIT mặc định và `avgBatchMs=18.018` với `-Xint`. Đây chỉ là minh họa rằng execution mode có thể ảnh hưởng performance; **không phải benchmark chuẩn của Java 17 runtime, không phải tốc độ trung bình mọi máy và không đủ khẳng định peak/steady state**. Các lần chạy lại có thể khác.

### 5.2. Vì sao có `volatile` và checksum?

`compute` trả về một giá trị phụ thuộc `seed`; `runBatch` cộng kết quả và ghi vào trường `volatile published`, làm phép tính có kết quả có thể quan sát. Điều này giảm nguy cơ JVM loại bỏ toàn bộ nội dung test như dead code. Tuy nhiên `volatile` **không biến một vòng lặp tự viết thành microbenchmark chuẩn**; profiling, inlining, loop optimization, cache, scheduling và độ phân giải `nanoTime()` vẫn có thể làm số đo lệch.

`Arrays.sort(ordered)` diễn ra **sau** các measured batches, không được tính vào các elapsed durations đã lưu; nó giúp minh họa việc có thể xử lý mẫu sau khi đo, dù demo này chỉ in average và không công bố percentile. Nếu muốn so **p99 của từng request** phải đo từng request, không diễn giải `avgBatchMs` là p99.

### 5.3. Những suy luận có thể và không thể rút ra

**Có thể kết luận:** trong môi trường/lần chạy cụ thể, HotSpot mixed-mode và interpreter-only có throughput/timing khác nhau; program output business logic như checksum không đổi.

**Không thể kết luận:** bốn warm-up batches đã chắc chắn làm C2 compile mọi method; sáu batches chứng minh steady state; JIT sẽ nhanh đúng 8.9× ở production; first request chỉ chậm vì interpreter; hoặc `-Xint` là mô phỏng chính xác cold start mặc định.

## 6. Quan sát JIT bằng cờ chẩn đoán thay vì phỏng đoán

### 6.1. `-XX:+PrintCompilation`

Trên HotSpot/JDK 17:

~~~bash
java -XX:+PrintCompilation WarmupLab
~~~

JVM có thể in dòng báo methods được biên dịch cùng các trường như thời gian kể từ JVM start, compilation ID, tier level và method name. **Format/IDs/timing khác nhau theo JVM build và trạng thái tải**, không thể đưa stdout nguyên văn bất biến. Output chẩn đoán có thể xen với `System.out` của ứng dụng, nên **không dùng một lần chạy logging để suy ra benchmark throughput chuẩn**.

Hãy tìm những compilation entries liên quan:

~~~text
WarmupLab::compute
WarmupLab::runBatch
WarmupLab::main
~~~

Sự xuất hiện của method trong log không đảm bảo method được compile **đúng một lần**, compile ở tier cuối hoặc tất cả code ngay lập tức dùng phiên bản ấy. JVM có thể in nhiều entries, OSR compilations, made-not-entrant hoặc deoptimization events.

### 6.2. So với interpreter-only `-Xint`

~~~bash
java -Xint WarmupLab
~~~

`-Xint` buộc interpreter-only theo HotSpot/Java launcher contract và vô hiệu hóa lợi ích JIT compilation. Nó có thể chạy chậm hơn nhiều trên loops tính toán.

**Không dùng `-Xint` như phép đo cold startup production**: ở cold JVM chạy mặc định, VM vẫn có thể compile hot methods trong quá trình phục vụ. `-Xint` chủ động tắt cơ chế đó, nên đây chỉ là **thí nghiệm cơ chế**, không phải cấu hình production được suy ra.

### 6.3. Chỉ dừng tiered compilation ở mức C1

Với HotSpot và cấu hình cho phép:

~~~bash
java -XX:TieredStopAtLevel=1 WarmupLab
~~~

Flag này thường được dùng để giới hạn compiler pipeline ở mức C1 tương ứng, hữu ích khi muốn xem trade-off **thời gian compilation so với chất lượng compiled code**. Nó **không phải công tắc “startup luôn nhanh hơn”**, không cam kết output/timing, và semantics có thể thay đổi giữa releases. Cần đo cả first-response latency lẫn sustained throughput.

### 6.4. Không dùng `-Xcomp` để tự động tuyên bố peak

`-Xcomp` yêu cầu compilation-first ở HotSpot và có thể làm thời gian khởi động/compilation rất khác bình thường. Nó **không đồng nghĩa** một JVM đã được warm-up bằng workload đại diện hoặc mọi branch profile đã chín. Không dùng `-Xcomp` là đường tắt tính “maximum possible Java speed”.

### 6.5. Code cache và compiler queues

JIT-compiled machine code nằm trong **code cache**. Nếu code cache bị giới hạn quá mức hoặc compiler queues quá tải, những hot paths có thể mất cơ hội compile/recompile như kỳ vọng; throughput và warm-up profile bị ảnh hưởng.

Có thể dùng `jcmd` để xem các commands VM thực sự hỗ trợ; ví dụ một số HotSpot có thông tin compiler/code cache:

~~~text
jcmd
jcmd <PID> help
jcmd <PID> Compiler.codecache
~~~

**`<PID>` là ký hiệu trong hướng dẫn**, thay bằng process ID thật trước khi chạy, không dán nguyên dấu `< >` vào shell. Tên command và quyền attach phụ thuộc JDK/VM. Không suy đoán một `jcmd` subcommand có ở mọi vendor.

## 7. Đo startup từ ngoài JVM: phải chọn mốc chính xác

Java code bên trong `main` không thể một mình đo đầy đủ **OS launch → JVM initialization → application startup** bằng cách bắt đầu `System.nanoTime()` khi main chạy: các bước trước main đã qua.

### 7.1. Đo toàn thời gian chạy của một CLI process

Bash/Linux/macOS:

~~~bash
time java -cp . WarmupLab
~~~

PowerShell:

~~~powershell
Measure-Command { java -cp . WarmupLab | Out-Null }
~~~

**Lưu ý**: các lệnh trên đo **cả thời gian warmup và measured batches bên trong `main`**, cộng JVM startup và process shutdown. Chúng **không** tách được từng mốc startup/ready/steady state. Trong PowerShell, `Measure-Command` còn có overhead shell/pipeline; nếu so các run, giữ cùng wrapper.

Để đo **time to first response** của service, nên dùng load generator/client có timestamp trước khi gửi request và sau khi nhận kết quả. Để đo **time to readiness**, đọc sự kiện readiness do service thực sự phát trong lifecycle, không chỉ đo lúc port mở hay process tồn tại.

### 7.2. Đo lần chạy mới mỗi lần

Mỗi lần gọi `java ...` là một process mới với một JIT/code cache state mới. Điều này giúp so cold process, nhưng **OS filesystem page cache, JIT artifacts trong shared/runtime facilities, containers và external databases có thể vẫn ấm**. Cold JVM process không đồng nghĩa cold toàn bộ hệ thống.

Nếu thử startup nhiều lần:

1. Cố định **JDK build, image, flags, classpath, environment**.
2. Dùng process mới mỗi lượt, không tái sử dụng một JVM đã phục vụ.
3. Giữ dataset và external dependencies giống nhau, hoặc ghi rõ warm/cold external cache.
4. Chạy đủ repetitions, đảo thứ tự ứng viên để giảm ảnh hưởng OS/noisy neighbor.
5. Báo median, p95/p99, variability và outliers; không chỉ lượt nhanh nhất.

**Không xoá OS caches trên production** hoặc thực hiện thao tác hệ thống nguy hiểm để “làm lạnh” bài test. Có thể tổ chức node/VM được kiểm soát riêng hoặc benchmark warm-OS-cache và cold-OS-cache thành hai scenario có ghi nhãn.

## 8. Vì sao warm-up không chỉ là “chạy vòng lặp đủ nhiều lần”?

### 8.1. Profile mismatch

Warm-up chạy 100% input ngắn, đo input rất dài có nhánh/allocations khác. JIT có thể đã optimize code chủ yếu cho hot branch ngắn, còn đường dài vẫn lạnh hoặc cần deoptimization. Hãy giữ **data shape và type distribution đại diện**.

### 8.2. Dead-code elimination

~~~java
for (int i = 0; i < 1000000; i++) {
    Math.sqrt(123.456);
}
~~~

Đây chỉ là **đoạn minh họa**, không có class/main. Kết quả `Math.sqrt` không được sử dụng; optimizer có thể bỏ lời gọi hoặc cả vòng lặp. Đo thời gian của đoạn này không đo đúng 1 triệu lần căn bậc hai.

### 8.3. Constant folding

~~~java
double value = 100 * 200.0;
~~~

Compiler có thể tính giá trị hằng ngay từ lúc biên dịch/optimization. Benchmark “một triệu phép nhân” với các operands compile-time constant có thể trở thành benchmark assignment, không phải phép nhân runtime.

### 8.4. Escape analysis và allocation elimination

Một object được tạo ra rồi chỉ dùng nội bộ, không thoát khỏi phạm vi mà optimizer quan sát được, có thể được scalar replace hoặc loại bỏ allocation trong một số trường hợp. Nếu ứng dụng thật có object sống qua request boundaries, benchmark với object dễ escape-analyze có thể không đại diện allocation pressure production.

### 8.5. Inlining và call-site profile

Một method rất nhanh khi JIT inline vào caller có thể chậm hơn khi đo như một virtual interface call với nhiều concrete receiver types. Cần mô phỏng **call-site polymorphism** của workload thực.

### 8.6. Warm-up tác động GC/lifetime

Heap occupancy, object ages, young/old generation và GC frequency có thể thay đổi sau hàng nghìn requests. Một benchmark chỉ xét JIT compilation nhưng lại có object allocations lớn có thể đo xen lẫn GC; cần bật GC logs để giải thích.

### 8.7. OS, CPU và JIT background compilation

OS scheduler, CPU turbo/frequency scaling, thermal throttling, CPU affinity, process priority, heap page faults và compiler threads chạy background đều gây noise. Những yếu tố này có thể tạo ra “tăng tốc” hoặc “chậm đi” mà code machine-level không đổi.

**Một phép đo tốt luôn mô tả workload và environment, không chỉ mã Java.**

## 9. JMH: công cụ phù hợp hơn tự viết vòng `nanoTime()`

**Java Microbenchmark Harness (JMH)** là công cụ từ dự án OpenJDK để benchmark những đoạn Java nhỏ. Nó hỗ trợ forks, warm-up iterations, measurement iterations, modes, output units, parametrization và một số cơ chế tránh sai lệch phổ biến.

Ví dụ **minh họa API JMH, không phải file Java SE 17 độc lập** vì cần JMH dependencies/build plugin:

~~~java
@State(Scope.Thread)
public class ComputeBenchmark {
    private int seed = 12_345;

    @Benchmark
    public long compute() {
        return transform(seed++);
    }

    private static long transform(int s) {
        long x = s;
        for (int i = 0; i < 256; i++) {
            x = (x ^ (x >>> 13)) * 31 + i;
        }
        return x;
    }
}
~~~

Để biên dịch đoạn JMH này cần `org.openjdk.jmh.annotations.*` và thư viện JMH trên classpath; snippet trên chỉ cho thấy cấu trúc `@State`/`@Benchmark`, **không hứa `javac` của JDK trần compile được**.

**Tại sao forks quan trọng?** Mỗi fork có JVM riêng, tránh chạy thử nghiệm ứng viên B trên heap/code cache đã bị ứng viên A warm-up trong cùng process. JMH warm-up cũng có thể cấu hình theo thời gian/iterations để xác định rõ phase nào được bỏ qua khỏi số đo chính.

**Nhưng JMH không giải quyết mọi thứ:**

- Microbenchmark không tự mô phỏng HTTP queueing, DB, network, thread contention hoặc load distribution.
- Warm-up trong JMH cũng phải có input distribution đúng.
- JMH không tự định nghĩa business SLO/production readiness.
- Benchmark tốt vẫn cần nhiều forks/repetitions và thống kê hợp lý.

Với service, sử dụng **JMH cho hàm nóng** và **end-to-end load testing cho application latency/throughput**.

## 10. Throughput, average latency và tail latency trong warm-up

Giả sử một service vừa start:

~~~text
Window 1 (0–10s): throughput  700 req/s, p99 300ms
Window 2 (10–20s): throughput 1400 req/s, p99 120ms
Window 3 (20–30s): throughput 1800 req/s, p99  75ms
Window 4 (30–40s): throughput 1850 req/s, p99  72ms
Window 5 (40–50s): throughput 1830 req/s, p99  78ms
~~~

**Bảng số chỉ minh họa, không phải kết quả benchmark đo thật.** Bạn có thể xem windows 4–5 là những ứng viên trạng thái ổn định, nhưng **không thể xác nhận chỉ từ năm số này**: còn phải xem offered load, CPU, GC, JIT events, memory retention và tính thống kê.

Nếu chỉ lấy **average throughput của toàn 50 giây**, bạn sẽ đo cả warm-up lẫn thời gian gần ổn định. Đó có thể là đúng nếu bài toán hỏi **số request xử lý trong vòng đời ngắn**, nhưng lại là phép đo sai nếu muốn so **steady-state capacity**.

Ngược lại, nếu loại bỏ mọi lần chạy đầu tiên rồi báo **best stable 10 seconds**, có thể tạo cherry-picking và lạc quan quá mức. Cần tiêu chí tách warm-up/measurement được định trước.

### Peak throughput có thể phá vỡ latency SLO

Một service có thể đạt **3.000 req/s tối đa** nhưng p99 latency lúc ấy 900 ms vì queueing. Nếu yêu cầu p99 ≤ 100 ms, có thể throughput **bền vững đúng SLO** chỉ là 2.100 req/s. Do đó:

- **Unconstrained peak throughput:** mức ops/s cao nhất đo được, có thể tại điểm latency xấu hoặc error rate cao.
- **SLO-constrained sustainable throughput:** tải cao nhất đạt p99/error/memory/CPU constraints trong khoảng đo đủ lâu.
- **Steady-state throughput:** mức xử lý trong một regime tương đối ổn định; có thể thấp hơn peak.
- **Startup average throughput:** số work trong cửa sổ bắt đầu ở process launch, gồm cả cold/warm transitions.

Đừng viết bảng performance chỉ một cột `ops/s` mà không ghi phase, SLO và thời gian đo.

### Coordinated omission

Load generator **closed-loop** gửi request mới sau khi request cũ hoàn thành, nên khi server tạm dừng, client có thể phát yêu cầu ít hơn, che tail latency do queueing. Với mục tiêu đo một arrival rate cố định, dùng workload **open-loop/rate-controlled**, ghi offered requests, completed, failed và timed out; áp histogram recording theo thời điểm scheduled arrival phù hợp để giảm coordinated omission.

Không loại các timeouts/failed requests rồi chỉ công bố p99 của requests thành công, vì service xử lý chậm/đánh rơi requests có thể nhìn “nhanh” một cách giả.

## 11. JIT logs và JFR để kiểm chứng warm-up thật

### `-XX:+PrintCompilation`

Phù hợp cho lab, kiểm tra **method nào** được biên dịch và tier activity. Nhưng output có thể rất nhiều và làm thay đổi timing; chạy riêng một lượt **diagnostic**, còn các lượt benchmark dùng logging nhất quán và overhead được kiểm soát.

### Java Flight Recorder

JFR trên JDK 17 có thể ghi các events về compilation, deoptimization, CPU samples, GC, allocation, classes và thread activity khi **được bật theo settings phù hợp**. Các event như `jdk.Compilation` hoặc `jdk.Deoptimization` có thể hữu ích tùy JDK build và recording configuration. **Không mặc định tất cả events đều được bật** trong `default.jfc`/`profile.jfc`.

Ví dụ khởi động recording cho một application thật:

~~~bash
java '-XX:StartFlightRecording=filename=warmup.jfr,settings=profile' \
  -jar app.jar
~~~

Lệnh minh họa này cần `app.jar` thật của ứng dụng; với `WarmupLab`, có thể dùng:

~~~bash
java '-XX:StartFlightRecording=filename=warmup.jfr,settings=profile' WarmupLab
~~~

Xem metadata/events bằng:

~~~bash
jfr summary warmup.jfr
jfr print --events jdk.Compilation,jdk.Deoptimization warmup.jfr
~~~

JFR recording ngắn có thể ít hoặc không có event mong muốn do threshold/settings. Không dùng “không có event” như bằng chứng “JIT hoàn toàn không chạy” khi chưa xác nhận event enablement.

### GC và class loading

~~~bash
java '-Xlog:gc=info,class+load=info:file=runtime.log:uptime,level,tags' WarmupLab
~~~

Log có thể cho biết GC events/class loading activity trong process. **Class load không đồng nghĩa class initialization**; GC elapsed pause cũng không phải toàn bộ stop interval. Khi cần safepoint timings, thêm tag `safepoint=info` nếu JVM hỗ trợ.

### `CompilationMXBean` có giới hạn

`java.lang.management.CompilationMXBean` có method `getTotalCompilationTime()`, nhưng JVM có thể không hỗ trợ monitoring phần này (API cho biết khi không hỗ trợ). Giá trị tổng cũng **không tự chứng minh mọi hot methods đã ở tier 4**, hay ứng dụng đạt steady state. Không dùng tổng compilation milliseconds làm điều kiện readiness đơn lẻ.

## 12. Thiết kế benchmark ba bài riêng thay vì một số tổng

### Bài A — Cold-start / readiness latency

**Câu hỏi:** một instance mới mất bao lâu từ process launch đến khi xử lý được yêu cầu đầu tiên ở mức chất lượng chấp nhận?

- Mỗi sample: **process JVM mới**.
- Mốc đo: timestamp từ ngoài process; xác định rõ probe/response thành công.
- Giữ cùng JDK, image, memory/CPU budget, dependency state.
- Đo cold image/cache scenario riêng nếu quan trọng cho autoscaling/serverless.
- Báo p50/p95/p99 startup + first response; ghi failure rate.

**Không dùng** `WarmupLab.avgBatchMs` làm time-to-ready.

### Bài B — Time to steady state

**Câu hỏi:** sau bao lâu ứng dụng đạt throughput/latency tương đối ổn định dưới workload đại diện?

- Phát requests theo arrival rate kiểm soát, bắt đầu từ mốc ứng dụng sẵn sàng.
- Đo liên tục qua những fixed windows (ví dụ mỗi 5 hoặc 10 giây).
- Kiểm tra throughput, p99, JIT/deopt events, GC, CPU và memory.
- Đặt tiêu chí ổn định trước experiment, ví dụ ba cửa sổ liên tiếp không có trend lớn và SLO pass; ngưỡng phải phù hợp variability.
- Báo **thời gian đạt điều kiện** và tỷ lệ các runs thực sự đạt, không chỉ mẫu chạy đẹp.

**Cẩn trọng:** việc runtime không còn compile một lúc **không đủ** để gọi steady state nếu DB cache vẫn tăng, live set vẫn trôi hoặc load generator đang thay đổi offered rate.

### Bài C — Sustainable steady-state throughput / peak

**Câu hỏi:** trong cùng ngân sách CPU/memory, dưới SLO đã đặt, hệ thống phục vụ được tải ổn định bao nhiêu?

- Warm-up với representative traffic.
- Dùng nhiều offered rates: dưới target, target, gần saturation.
- Không xóa request timeout/failed khi tính kết quả.
- Đo p95/p99/p99.9, achieved throughput, CPU, RSS/cgroup và GC/JIT cost.
- Chạy long soak để thấy rare GC, native retention, thermal/CPU throttling, leaks.
- Công bố **SLO-constrained sustained throughput** và peak không ràng buộc như hai cột riêng.

Nếu ứng dụng sống ngắn như CLI chạy 2 giây rồi kết thúc, bài B/C có thể ít ý nghĩa hơn **total job elapsed** ở cold process. Chọn KPI theo vòng đời sản phẩm.

## 13. Warm-up trong hệ microservices/autoscaling

Ứng dụng Java chạy theo deployment có một bài toán đặc biệt: không thể lấy steady-state capacity của **một instance đã chạy 3 giờ** để suy ra cold instance mới tự động phục vụ full traffic.

### Readiness, liveness và traffic shifting

- **Liveness:** process/service còn hoạt động về mặt kiểm tra cơ bản.
- **Readiness:** instance đủ điều kiện để **nhận traffic** theo giao thức deployment; không mặc định mọi JIT path đã peak.
- **Warm-up status nội bộ:** optional signal theo route/request mix và khả năng phục vụ workload mục tiêu.
- **Traffic ramp:** tăng tải dần để tránh nhiều cold instances cùng lúc gây request latency spike hoặc compiled-code CPU pressure.

Không nên trì hoãn readiness vô hạn chỉ để chờ “C2 compile hết mọi thứ”, vì đó không phải mốc JVM có thể đảm bảo. Thay vào đó, đặt **acceptance criteria hữu hạn** cho chức năng cần sẵn sàng, preload những dependencies quan trọng, warm representative hot routes nếu đáng giá và dùng traffic ramp có giám sát.

### Scale-out và warm-up cost

Khi workload đột ngột tăng, autoscaler tạo nhiều pods/JVM mới. Chúng có thể cùng:

- Nạp classes và tạo connection pools.
- Compile code trong background, tranh CPU quota với requests.
- Làm nóng DB/cache, tạo burst tải vào downstream.
- Gặp GC heap occupancy transitions.
- Chỉ đạt throughput thấp hơn trong vài chục giây đầu.

Nếu capacity planner lấy **steady-state req/s mỗi pod** nhân ngay với số pods mới, dự báo công suất thời gian đầu có thể quá lạc quan. Cần profile **warm-up ramp curve** và autoscaler readiness strategy phù hợp.

### Serverless, short-lived jobs và peak JIT

Một CLI task 300 ms có thể kết thúc trước khi nhiều hot paths được tối ưu mạnh. Trong workload như vậy, **minimize class loading/bootstrapping** có thể quan trọng hơn C2 peak throughput. Đó là lý do “cấu hình tăng peak throughput” không mặc nhiên giúp startup.

## 14. Nhiều kịch bản cần phân biệt khi báo kết quả

### Kịch bản 1 — Bản A startup nhanh hơn nhưng đỉnh chậm hơn

Bản A ready sau 700 ms và xử lý ổn định 2.000 req/s; bản B ready sau 1.8 giây nhưng sau warm-up xử lý 2.500 req/s. Nếu serverless chỉ chạy 4 giây, A có thể thắng total work; nếu chạy 24 giờ với CPU budget phù hợp, B có thể thắng. Không có kết luận chung khi chưa có **lifecycle và SLO**.

### Kịch bản 2 — Request đầu tiên chậm do lazy class initialization

Một class chỉ được load/init khi route `/generate` lần đầu được gọi. Readiness probe `/health` trả ngay, nhưng `/generate` request đầu mất thêm chi phí. Cần warm-up đúng route hoặc đo cold-path riêng; đừng quy mọi chi phí cho JIT.

### Kịch bản 3 — Warm-up input khác production

Trong warm-up, 100% requests sử dụng JSON nhỏ. Production chứa 30% payload lớn và nhiều receiver types. C2 optimization có thể thiên về profile cũ, workload thực làm đường chạy khác; warm-up 5.000 requests vẫn không đảm bảo representative.

### Kịch bản 4 — Đỉnh đẹp nhưng GC/CPU không bền

Thí nghiệm 30 giây đạt 100k ops/s, nhưng sau 30 phút heap live set tăng và Full GC xuất hiện. Đỉnh 30 giây không phải sustainable throughput; cần soak để phát hiện nonstationarity/memory leak.

### Kịch bản 5 — C1-only làm first request cải thiện

Nếu `TieredStopAtLevel=1` làm first response nhanh hơn một lần chạy, chưa được kết luận flag luôn tốt. Có thể giảm compilation overhead ban đầu nhưng làm steady peak xấu hơn. Chạy A/B nhiều lần với startup và sustained SLO riêng.

### Kịch bản 6 — `-Xint` rất chậm

Điều này cho thấy JIT mang lại lợi ích với hot kernel cụ thể, không chứng minh production cold start là interpreter-only, cũng không chứng minh toàn bộ application speedup bằng kernel speedup.

### Kịch bản 7 — JIT log còn compilation trong steady measurement

Có thể có route ít dùng mới nóng lên hoặc runtime bù đắp recompilation. Xem magnitude và sự liên quan với p99; không nhất thiết mọi compilation đều vi phạm steady state, nhưng một burst lớn có thể cần phân đoạn lại window.

### Kịch bản 8 — CPU quota khiến warm-up kéo dài

JIT compiler threads và Java workers tranh một quota 1 vCPU; instance có thể cần nhiều thời gian hơn để đạt candidate steady-state so với benchmark trên 16 cores không giới hạn. Đo trong cùng container CPU quota và ghi CPU throttling; `ActiveProcessorCount` không tự đặt cgroup quota.

## 15. Checklist một kết quả warm-up/peak có thể tin

- [ ] Định nghĩa rõ `process start`, `first useful result`, `ready`, `warm-up end`, `measurement start/end`.
- [ ] Ghi JDK vendor/build, VM flags, OS, vCPU quota, heap và memory cap.
- [ ] Không lẫn cold startup với steady-state throughput.
- [ ] Representative request mix, object lifetime và data shapes.
- [ ] Không bỏ failures/timeouts/dropped requests khỏi latency accounting.
- [ ] Có nhiều process forks/repetitions và randomized run order.
- [ ] Có warm-up time windows/criteria từ trước; không chọn thủ công đoạn nhanh nhất.
- [ ] Kiểm tra JIT compilation/OSR/deoptimization khi phân tích.
- [ ] Kiểm tra GC, class loading, pools, cache, external dependencies và CPU.
- [ ] Phân biệt `-Xint` diagnostic với cold startup thực tế.
- [ ] Dùng JMH cho microbenchmark, production-like load generator cho service.
- [ ] Báo achieved vs offered load; tránh coordinated omission.
- [ ] Báo p50/p95/p99/p99.9 cùng throughput và resource footprint.
- [ ] Có cold-path, warm-up ramp và long steady-state experiments riêng.
- [ ] Không kết luận từ một JVM ngắn có 4 warm-up batches rằng đã C2 peak.
- [ ] Mọi output thời gian và compilation logs được gắn nhãn **environment-dependent**.

## 16. Câu hỏi tự kiểm tra

1. **Warm-up là gì?** Quá trình runtime/application thay đổi trạng thái khi thực thi workload: JIT profiling/compilation, class/init, caches, pools, heap/GC...
2. **Một method Java sau 10.000 calls chắc chắn ở C2?** Không; VM policy, JIT tiers, hotness, compiler queue và flags khác nhau.
3. **Một vòng loop rất dài nhưng chỉ gọi một method một lần có thể được JIT không?** Có; HotSpot có thể dùng OSR/backedge hotness.
4. **`-Xint` tương đương first request của JVM JIT mặc định?** Không; nó chủ động tắt JIT.
5. **C1 và C2 có mục tiêu giống nhau?** Không hoàn toàn; C1 compile nhanh hơn, C2 có thể tối ưu sâu hơn, đổi lại compilation cost.
6. **Compiled code có luôn tồn tại bất biến tới process exit?** Không; có deoptimization, code invalidation, recompile và code cache management.
7. **Readiness thành công đồng nghĩa JIT đã peak?** Không.
8. **Steady state có phải flag JVM có thể kiểm tra 1 lần là biết?** Không; cần nhiều metrics/windows và định nghĩa workload.
9. **Peak throughput có chắc đạt request p99 SLO?** Không; peak có thể tại saturation với queueing/latency xấu.
10. **Warm-up chỉ bằng 5 giây có được JVM bảo đảm không?** Không.
11. **JIT compilation log im lặng có chứng minh không còn JIT?** Không nếu chưa kiểm tra settings và timing.
12. **Một benchmark chứa phép tính không dùng kết quả đáng tin không?** Không; dead-code elimination có thể bỏ work.
13. **Tại sao dùng process forks?** Để mỗi thí nghiệm có trạng thái JVM/JIT/heap mới.
14. **`time java WarmupLab` đo điều gì?** Tổng OS process invocation đến exit, gồm startup + toàn bộ work của main + shutdown/overhead.
15. **JMH có thay thế HTTP end-to-end load test không?** Không; JMH đo micro-workload, không tự phản ánh mạng/queueing/DB.
16. **Nếu warm-up route A nhưng production route B, JIT đã đại diện chưa?** Chưa chắc; type/branch/class paths có thể khác.
17. **GC có góp phần vào warm-up không?** Có; live-set/heap occupancy/GC cadence có thể thay đổi.
18. **Một số `avgBatchMs` trong lab là p99 request latency?** Không, chỉ là trung bình duration các batches đã chọn.
19. **Khi JDK 17 benchmark code trên JDK 24 với `--release 17`, runtime đã là JDK 17 chưa?** Chưa; bytecode/API target là 17, compiler/runtime VM vẫn JDK 24.
20. **Với CLI sống 0.3 giây, ưu tiên startup hay C2 peak?** Tuỳ SLO; startup/total job time thường quan trọng hơn peak của hot method.
21. **CDS có bảo đảm C2 peak ngay khi process mới chạy?** Không.
22. **Tại sao cần CPU quota giống production?** Compiler threads và app threads tranh tài nguyên; warm-up/throughput thay đổi theo quota.
23. **Một app đạt p99 ổn định nhưng heap live set cứ tăng?** Chưa đáng xem là trạng thái ổn định lâu dài; cần soak và leak analysis.
24. **Cấu hình có throughput cao nhưng vi phạm memory/CPU/latency budget có phải thắng?** Không; cần xem SLO-constrained sustained performance.

## 17. Tài liệu chuẩn và tham khảo sâu

- Oracle JDK 17 `java` launcher: `-Xint`, `-XX:+PrintCompilation`, `-XX:-TieredCompilation`, `-Xlog`, JFR và các VM flags: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle — Understanding Java JIT Compilation with JITWatch (C1/C2, tiered compilation, optimization): https://www.oracle.com/technical-resources/articles/java/architect-evans-pt1.html
- OpenJDK HotSpot — JIT compilation policy và compiler infrastructure (JDK source): https://github.com/openjdk/jdk17/tree/master/src/hotspot/share/compiler
- Oracle JDK 17 `jcmd`: compiler diagnostics, JFR và process introspection: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle JDK 17 `jfr`: inspection của Java Flight Recorder recordings: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- Java SE 17 JFR API/module: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html
- Java SE 17 `CompilationMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/CompilationMXBean.html
- OpenJDK Java Microbenchmark Harness (JMH): https://openjdk.org/projects/code-tools/jmh/
- Oracle JDK 17 Garbage Collection Tuning Guide (hiệu ứng GC, throughput/latency): https://docs.oracle.com/en/java/javase/17/gctuning/

**Kết luận kỹ thuật:** **Khởi động nhanh không đồng nghĩa hiệu năng đỉnh cao; hiệu năng đỉnh cao không đồng nghĩa trạng thái ổn định; trạng thái ổn định không đồng nghĩa đạt SLO**. HotSpot đi từ interpreter qua profiling và tiered JIT, có thể OSR, deoptimize và recompile, trong khi class loading, heap/GC, caches và dependencies cùng ảnh hưởng warm-up. Hãy đo **cold process startup, time-to-ready, warm-up ramp, steady-state throughput và SLO-constrained peak** thành những KPI rõ ràng, dùng nhiều repetitions, workload đại diện, JMH/JFR và tracing phù hợp. Đừng coi một batch chạy nhanh hoặc một JIT compilation event là bằng chứng đã đạt hiệu năng tối ưu.
