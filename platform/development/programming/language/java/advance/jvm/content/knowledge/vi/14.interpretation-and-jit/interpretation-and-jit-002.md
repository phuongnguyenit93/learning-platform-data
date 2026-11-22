# Đường đi từ phương thức ít chạy đến đoạn mã nóng trong HotSpot JVM

## 1. Câu hỏi cốt lõi: vì sao Java không biên dịch tối ưu mọi phương thức ngay?

Khi chạy một chương trình Java trên **HotSpot JVM**, các class files mang **bytecode**. HotSpot thường bắt đầu thực thi code mới bằng **interpreter**, quan sát hành vi runtime, rồi có thể sử dụng **Just-In-Time (JIT) compilation** để chuyển những phương thức/vòng lặp được dùng thường xuyên thành **machine code**.

Một phương thức ít chạy (*cold method*) có thể không bao giờ cần được JIT biên dịch. Một phương thức được gọi nhiều lần hoặc có vòng lặp chạy dài có thể trở thành **hot code** và đáng chi trả chi phí biên dịch để những lần chạy sau nhanh hơn.

```text
.class / bytecode
       |
       v
Class loading + verification + linking khi cần
       |
       v
Interpreted execution (tier 0)
       |
       +--- ít gọi, ít chạy ---> giữ interpreted hoặc chiến lược khác
       |
       +--- nhiều invocations / loop backedges
       |             |
       |             v
       |       profiling + compilation policy
       |             |
       |             v
       |       compilation queue / compiler threads
       |             |
       |             v
       |          C1 compiled code
       |             |
       |         thêm runtime profiles,
       |         compiler nhận thấy đáng tối ưu
       |             |
       |             v
       |          C2 compiled code
       |             |
       |       guard/assumption thất bại?
       |             |
       |             v
       +------ deoptimization / interpreter / recompile
```

Đây là **sơ đồ trực giác**, không phải một chuỗi bắt buộc cho mọi phương thức. Có đường nhảy cấp, có phương thức chỉ qua C1, có phương thức không được biên dịch, có compilation xảy ra trong vòng lặp qua **OSR**, và có trường hợp JIT hủy hoặc thay một bản machine code cũ.

### Cần phân biệt ba khái niệm

1. **Warm-up:** thời gian đầu chương trình chạy khi classes được nạp, thông tin runtime được tích lũy và JIT có thể bắt đầu tối ưu.
2. **Hotness:** đánh giá nội bộ của VM rằng một method/loop đủ quan trọng để biên dịch hoặc biên dịch lại.
3. **Tiered compilation:** chính sách HotSpot dùng các cấp thực thi/biên dịch khác nhau để cân bằng **startup time**, **profiling overhead**, **peak performance** và **chi phí compilation**.

**Không có hợp đồng của Java Language Specification** rằng “lần gọi thứ 10.000 thì phương thức chắc chắn chuyển sang C2”. Hotness thresholds và các đường chuyển cấp thuộc **HotSpot implementation**, phụ thuộc JDK build, JVM flags, runtime load và workload.

## 2. Java source, bytecode và machine code là ba thứ khác nhau

Ví dụ:

```java
static int square(int x) {
    return x * x;
}
```

Sau khi dùng `javac`, class file có bytecode biểu diễn phép lấy tham số, nhân số nguyên và trả kết quả. Khi chạy, HotSpot có nhiều lựa chọn để thực hiện đúng semantics của các instructions đó:

- **Interpreter** đọc/thực thi bytecode theo runtime engine.
- **C1 compiler** tạo machine code nhanh, có thể thu thập thêm profiling tùy tier.
- **C2 compiler** dùng các phân tích/tối ưu phức tạp hơn để tạo machine code tối ưu.
- JIT có thể **inline** `square` vào caller, vì vậy không phải lúc nào bạn cũng thấy một lời gọi native tới compiled code riêng biệt của `square`.

```text
Java source: square(x)
        |
      javac
        |
        v
Bytecode in square.class
        |
   HotSpot runtime
        |
        +--> Interpreter executes bytecode
        +--> C1 creates compiled machine code
        +--> C2 creates aggressively optimized machine code
                  |
                  +--> có thể inline square vào caller
```

**JIT không thay đổi file `.class` trên đĩa khi tối ưu trong process.** Machine code do JIT tạo được lưu trong các cấu trúc runtime (như **code cache/nmethods**), được dùng khi phù hợp và có thể bị thay thế/hủy.

### 2.1. “Compiled” ở đây nghĩa gì?

`javac` đã biên dịch **source → bytecode** trước khi chạy. JIT là bước khác: **bytecode/runtime IR → machine code cho CPU cụ thể**, thực hiện trong runtime.

Vì vậy hai câu sau đều có thể đúng:

- “Java được biên dịch trước khi chạy” — đúng ở giai đoạn `javac` tạo bytecode.
- “HotSpot có thể thông dịch bytecode rồi JIT biên dịch khi đang chạy” — đúng về thực thi runtime.

### 2.2. Không phải mọi JVM đều bắt buộc C1/C2

JVMS quy định **hành vi bytecode**, không bắt buộc có interpreter tên HotSpot, C1/C2, tiered compilation hoặc số lần gọi phải được đếm theo một cách cụ thể.

Bài này tập trung **HotSpot với tiered compilation được hỗ trợ**, đặc biệt dễ thực hành bằng **JDK 17+**. JVM khác như OpenJ9/GraalVM hay những cấu hình HotSpot khác có thể có compiler pipeline riêng.

## 3. Tại sao phương thức ít chạy thường bắt đầu từ interpreter?

**Interpreter** có lợi thế **không cần trả toàn bộ chi phí tối ưu native code trước lần dùng đầu tiên**. Nếu một phương thức chỉ chạy một lần trong startup, compile C2 đắt đỏ có thể lãng phí nhiều CPU/memory hơn thời gian tiết kiệm được.

Ví dụ:

```java
static void printHelp() {
    System.out.println("Usage: ...");
}
```

Nếu `printHelp()` chỉ chạy một lần khi người dùng nhập `--help`, interpreter có thể thực thi đủ nhanh; một JIT compilation nhiều vòng phân tích khó tạo giá trị ròng.

Ngược lại:

```java
static int decode(int x) {
    return (x * 31) ^ (x >>> 3);
}
```

Nếu `decode` được gọi hàng triệu lần ở đường xử lý dữ liệu, chi phí JIT có thể được bù bằng lợi ích lặp lại.

### 3.1. Startup time vs steady-state performance

- **Startup:** chạy được ứng dụng và trả kết quả đầu tiên nhanh.
- **Warm-up:** JIT thu thập profile, compile/recompile; tốc độ có thể thay đổi.
- **Steady state:** các đường hot có thể chạy compiled code tối ưu hơn.

Nhưng **không hứa steady state đến đúng sau N giây**. Một web service có thể luôn gặp những phương thức mới được gọi lần đầu sau mỗi request mới, plugin mới hoặc class loader mới.

### 3.2. Interpreted không có nghĩa “không an toàn”

Dù interpreted hay compiled, code Java vẫn phải tuân thủ semantics (kiểu, exceptions, concurrency rules, access checks) phù hợp. JIT không được hợp lệ hóa một hành vi Java sai chỉ vì nó chạy nhanh hơn.

### 3.3. Interpreter không phải một cấp thấp vĩnh viễn

Khi phương thức/vòng lặp trở nên hot, compilation policy có thể yêu cầu tạo compiled entry; lần gọi tiếp theo có thể đi vào native code, hoặc với loop dài JVM có thể chuyển giữa chừng qua OSR.

## 4. Hotness: invocation counters và loop backedges

HotSpot theo dõi **số lần gọi phương thức** và **số lần quay lại trong một vòng lặp** (backedges) cùng thông tin profiling khác để quyết định có nên compile/recompile.

Hai nguồn tín hiệu rất khác nhau:

| Tín hiệu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Method invocation count** | `process()` được gọi liên tục từ request handler | Method hot vì **nhiều lần vào method** |
| **Loop backedge count** | `process()` chỉ được gọi một lần nhưng vòng lặp có hàng triệu iterations | Một method/loop hot dù **số invocation ít** |

### 4.1. Nhiều lần gọi, mỗi lần ít việc

```java
static int addOne(int x) {
    return x + 1;
}

static int callManyTimes() {
    int result = 0;
    for (int i = 0; i < 100_000; i++) {
        result += addOne(i);
    }
    return result;
}
```

Đây là **mã minh họa** trong class, chưa phải chương trình `main` độc lập. `addOne` được gọi nhiều lần, nhưng JIT có thể **inline** nó vào caller; do đó profiling log không nhất thiết cho thấy một compiled native method độc lập ở mọi hoàn cảnh.

### 4.2. Một lần gọi, vòng lặp rất dài

```java
static long bigLoop(int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += i;
    }
    return sum;
}
```

Nếu `bigLoop(1_000_000)` được gọi một lần, **invocation count chỉ là một**, nhưng **backedge count** có thể rất lớn. Điều đó có thể kích hoạt **on-stack replacement (OSR)**.

### 4.3. “Hot method” và “hot loop” không nhất thiết giống nhau

Một method có thể nổi bật vì số calls; loop trong một method khác nổi bật vì số iterations. HotSpot có thể compile method entry riêng, compile OSR entry riêng, hoặc một trong hai theo policy/runtime state.

**Không coi số source-code dòng lặp hay độ dài phương thức là thước đo trực tiếp của hotness.** Runtime execution frequency và compiler heuristics quan trọng hơn.

## 5. Tiered compilation: năm mức thực thi của HotSpot truyền thống

Mô hình tiered compilation trong HotSpot C1/C2 thường mô tả **mức 0–4**:

| Level | Engine | Điểm cốt lõi |
| --- | --- | --- |
| **0** | **Interpreter** | Thực thi bytecode; có thể thu thông tin runtime |
| **1** | **C1, simple compilation** | C1 native code, **không thu full profiling** |
| **2** | **C1, limited profiling** | C1 có các counters cơ bản, ít overhead hơn full profiling |
| **3** | **C1, full profiling** | C1 có instrumentation/profile phong phú hơn để hỗ trợ lựa chọn và C2 |
| **4** | **C2 optimization** | Native code tối ưu mạnh, dùng profile/assumptions khi phù hợp |

Tên trong OpenJDK có thể gặp:

```text
CompLevel_none                  (0)
CompLevel_simple                (1)
CompLevel_limited_profile       (2)
CompLevel_full_profile          (3)
CompLevel_full_optimization     (4)
```

Các tên này là **thông tin triển khai HotSpot**. **Không suy ra luôn phải đi tuần tự 0 → 1 → 2 → 3 → 4.** Thực tế một đường rất thường gặp là:

```text
Interpreter (0) ---> C1 with profiling (3) ---> C2 (4)
```

Và cũng có thể:

```text
Interpreter (0) ---> C1 limited profiling (2)
                        |
                        v
                     C1 full profiling (3)
                        |
                        v
                        C2 (4)
```

Mọi mô hình trên **chỉ là lộ trình có thể**, không phải timeline cứng cho từng method.

### 5.1. Tại sao có nhiều tier C1?

C1 thường biên dịch nhanh hơn C2, vì vậy có thể cung cấp native code sớm hơn. Level 3 thu profile chi tiết hơn để C2 có dữ liệu cho speculative optimizations, nhưng việc thu profile cũng có overhead.

Level 2 có thể được dùng khi compilation queues/load tình huống khiến việc chạy C1 full profiling quá lâu chưa đáng, rồi có thể chuyển tiếp sau. Level 1 có thể phù hợp với những methods không cần profile hoặc chính sách đặc biệt.

### 5.2. C2 có phải lúc nào cũng nhanh hơn C1 không?

Không có bảo đảm **mọi method riêng lẻ** chạy C2 sẽ nhanh hơn C1 trong mọi microbenchmark. C2 thường hướng đến peak optimization, nhưng code size, profile quality, JIT decisions, CPU microarchitecture, warm-up và compiler overhead ảnh hưởng.

Các performance claims cần đo end-to-end theo workload, không chỉ nhìn “level 4” rồi tuyên bố nhanh hơn chính xác một tỷ lệ.

### 5.3. Tier names có thể không xuất hiện giống nhau trên JVM khác

Các tools có thể hiện level numbers trong HotSpot log; JVM khác hoặc HotSpot build thiếu C2 có thể có cách mapping/compilation policy riêng. Khi đọc log, cần kiểm tra `java -version` trước.

## 6. Từ invocation/backedge counters đến quyết định compile

Một compilation policy phải cân bằng hai loại chi phí:

1. **Chi phí chạy interpreted hoặc C1 profiling** ở mỗi lần thực thi.
2. **Chi phí biên dịch, code cache, compile threads, profile storage** và rủi ro compiled code không còn được dùng nhiều.

Ngưỡng kích hoạt có thể bị ảnh hưởng bởi:

- Invocation/backedge counts.
- Tốc độ tăng của các counts và method activity.
- Hàng đợi C1/C2, số compiler threads và tải CPU.
- Tier đang thực thi và quality của profile hiện có.
- Compile directives, excluded methods, JVM flags.
- Code cache availability.
- Deoptimization/uncommon traps hoặc trạng thái compiled versions.

**Không viết “`CompileThreshold=10000` nghĩa đúng lời gọi thứ 10000 mọi method sẽ thành C2”.** Tiered policy có nhiều ngưỡng và quy tắc kết hợp counts/counters, cộng thêm queue/load heuristics.

### 6.1. Threshold không là hợp đồng API

Có các cờ HotSpot như:

```text
-XX:CompileThreshold=...
-XX:TieredStopAtLevel=...
-XX:+TieredCompilation
-XX:-TieredCompilation
```

Nhưng tương tác các cờ khác nhau theo JDK/VM. Với **tiered compilation** bật, không nên coi **`CompileThreshold` đơn lẻ** là cách chính xác điều khiển mọi đường chuyển tier.

### 6.2. Compilation threshold không đo đơn thuần theo wall time

Một method chạy 10 giây vì chờ I/O có thể có rất ít invocations và không có loop backedges nóng. Ngược lại, một method tính toán trong vài trăm mili giây có thể đã vượt nhiều counters.

“Hot” không đồng nghĩa “method xuất hiện lâu nhất trong thread dump” hay “method tốn nhiều wall-clock vì đang blocked”.

### 6.3. Compilation queues

Khi policy quyết định một method đáng compile, yêu cầu có thể vào **compiler queue**. Compiler thread làm việc độc lập với mutator thread, tạo nmethod trong **code cache**. Trong lúc chờ, application có thể tiếp tục chạy ở interpreted/C1 code.

```text
Application thread:
  interpreted / C1 execution --- tiếp tục công việc --->
                    |
                    +-- enqueue method for C2 compilation
                                      |
Compiler thread:                  compile, optimize
                                      |
                                      v
                                publish nmethod
                                      |
Application later:                    use compiled entry
```

Vì compilation có thể diễn ra bất đồng bộ, **thời điểm method chuyển cấp không được xác định bởi một dòng source duy nhất**.

## 7. Method Data và profiling: JIT học từ runtime như thế nào?

Trong HotSpot, **MethodData** và các runtime profiling structures có thể ghi nhận những tín hiệu như:

- Lượng invocations/backedges ở mức cần thiết.
- Tần suất đường nhánh thường được chọn.
- Kiểu runtime xuất hiện ở những call sites.
- Loại exception hoặc hình dạng control flow theo nơi có instrumentation.
- Thông tin phục vụ inlining, virtual-call optimization, loop optimization.

Ví dụ:

```java
interface Handler {
    int apply(int x);
}

static int dispatch(Handler h, int x) {
    return h.apply(x);
}
```

Đây là **code minh họa chưa có `main`**. Nếu mọi lần chạy thực tế `h` là một implementation duy nhất, profile có thể hỗ trợ JIT tối ưu call site. Nếu về sau một implementation khác xuất hiện, giả định tối ưu có thể không còn phù hợp, dẫn tới deoptimization/recompilation khi cần.

### 7.1. Monomorphic, bimorphic, megamorphic — hiểu theo call site

Một call site có thể thấy:

- **Monomorphic:** một receiver type là chủ yếu/duy nhất trong profile.
- **Bimorphic:** hai receiver types nổi bật.
- **Megamorphic:** nhiều receiver types khiến các chiến lược type-specialized optimization ít hiệu quả hơn.

Đây là **mô tả runtime profile**, không phải thuộc tính cố định của cú pháp `interface`. Không có một công thức số implementations duy nhất đảm bảo chính xác mọi quyết định của JIT.

### 7.2. Profile-guided optimization có thể speculative

HotSpot có thể tối ưu dựa trên thông tin quan sát được kèm **guards**. Nếu runtime đi theo đường ít gặp hoặc xuất hiện receiver type mới, VM phải duy trì hành vi đúng — bằng slow path, guard failure, deoptimization hoặc recompilation.

**Speculation không cho phép JIT làm sai Java semantics.**

### 7.3. Profiling không đồng nghĩa mọi nhánh đều đã được chạy

Nếu một nhánh exception hiếm chưa từng xuất hiện trong warm-up, C2 có thể tối ưu cho đường phổ biến, nhưng nó vẫn phải có cơ chế đúng để xử lý exception khi phát sinh. Benchmark chỉ làm nóng “happy path” không chứng minh production code luôn ở điều kiện đó.

## 8. C1 vs C2: chi phí biên dịch và chất lượng code

### 8.1. C1 — native code sớm, có thể gắn instrumentation

C1 thường được mô tả là **client compiler**, thiết kế tương đối nhanh và dùng trong các tier thấp để cải thiện startup/warm-up mà chưa trả toàn bộ chi phí C2. Khi ở profiling tier, C1 có thể chèn instrumentation thu type/branch/counter data.

### 8.2. C2 — tối ưu sâu hơn

C2 thường được mô tả là **server/optimizing compiler**. Những kỹ thuật có thể gồm:

- Inlining qua method boundaries khi profile/size cho phép.
- Devirtualization/speculative type-check optimization.
- Common subexpression elimination, constant propagation.
- Loop optimizations (unrolling, range-check elimination… khi an toàn).
- Escape analysis và scalar replacement trong những điều kiện phù hợp.
- Dead-code elimination và những IR/low-level optimizations khác.

Không phải mọi kỹ thuật đều được áp dụng vào mọi method; optimization pipeline phụ thuộc compiler IR, flags, method shape, CPU capabilities và runtime assumptions.

### 8.3. Một method có thể có nhiều compiled versions

Một method có thể có:

- Compiled C1 entry (tier 3).
- Compiled C2 entry (tier 4).
- OSR nmethod cho một loop backedge.
- Những compiled versions cũ ở trạng thái không còn được dùng để vào method.
- Code được inline ở những callers khác.

**Không gộp “một Java method” với “duy nhất một đoạn machine code bất biến”.**

### 8.4. “JIT chuyển interpreter thành C2 rồi hết” là sơ đồ thiếu

JIT không phải chỉ chạy một lần. Runtime có thể tiếp tục profiling, nâng tier, deoptimize và recompile nếu môi trường thay đổi, hoặc code cache cần quản lý.

## 9. OSR — chuyển sang compiled code ngay giữa vòng lặp

**On-Stack Replacement (OSR)** đặc biệt quan trọng với bài “từ phương thức ít chạy thành đoạn nóng”.

Giả sử một method được gọi đúng một lần nhưng chạy loop lâu:

```java
static long aggregate(int n) {
    long result = 0;
    for (int i = 0; i < n; i++) {
        result += (i & 255);
    }
    return result;
}
```

Nếu interpreter/level thấp phát hiện **loop backedges** nóng, HotSpot có thể compile một **OSR version** của method cho một **bytecode index (BCI)** cụ thể, rồi thay execution state ngay khi loop đang chạy.

```text
Thread chạy aggregate(n)
     |
     v
Interpreter đi vào loop
     |
     +-- iterations rất nhiều --> backedge counter vượt ngưỡng thích hợp
     |
     +-- yêu cầu OSR compilation ở loop-entry/backedge BCI
                         |
                         v
                  OSR compiled nmethod
                         |
             thread đang ở loop chuyển vào code mới
                         |
                         v
                  tiếp tục đúng trạng thái local/stack
```

### 9.1. OSR khác method-entry compilation

- **Normal compiled entry:** những lần gọi method sau có thể vào machine code từ đầu.
- **OSR compiled entry:** một frame đang thực thi một loop có thể được chuyển sang compiled execution **mà không cần return rồi gọi lại method**.

**Một compiled OSR version không tự đồng nghĩa normal method entry đã có level 4.** Log thường có ký hiệu riêng cho OSR, ví dụ ký tự **`%`** và `@ bytecodeIndex`.

### 9.2. Log mẫu, không phải đầu ra cố định

```text
27   15 %     3       HotMethodDemo::loop @ 4 (25 bytes)
```

Đây là **mẫu hình giống sự kiện quan sát được trong thử nghiệm HotSpot**, không phải cam kết timestamp/compile ID/tier trong mọi lần chạy. Ký hiệu `%` cho biết OSR compilation; `@ 4` cho biết vị trí bytecode index có liên quan.

### 9.3. Khi nào OSR không xuất hiện?

- Loop chưa chạy đủ nhiều để policy thấy đáng compile.
- Method đã được compiled ở mức phù hợp ngay từ đầu.
- JIT bị tắt hoặc compilation bị hạn chế bằng flags.
- Workload/JIT optimizer làm đổi shape loop hoặc code path.
- VM chọn chiến lược khác hoặc compile chưa hoàn tất trước khi loop kết thúc.

**Không viết test assert “mọi vòng lặp trên 10.000 iterations đều phải có OSR”.**

## 10. Deoptimization — khi tối ưu từng đúng nhưng giả định không còn phù hợp

JIT thường tối ưu cho **đường được quan sát nhiều**. Nhưng runtime có thể xuất hiện tình huống mới.

Ví dụ:

```java
interface Worker {
    int work(int x);
}

final class FastWorker implements Worker {
    public int work(int x) { return x + 1; }
}

final class AlternateWorker implements Worker {
    public int work(int x) { return x * 2; }
}
```

Nếu một call site thường chỉ gặp `FastWorker`, JIT có thể tối ưu/inlining dựa trên profile. Khi `AlternateWorker` xuất hiện, một guard/class hierarchy assumption có thể cần được kiểm tra và runtime có thể **deoptimize** một nmethod nếu assumptions của optimized version bị invalidated.

### 10.1. Deoptimization thực hiện gì?

Ở mức trực giác:

1. Runtime phát hiện compiled code không còn phù hợp với điều kiện mà nó giả định.
2. JVM tạo/khôi phục **interpreter-compatible execution state** khi cần.
3. Thread có thể tiếp tục bằng interpreter/code khác mà không mất Java semantics.
4. Policy có thể compile lại với profile/assumptions phù hợp hơn.

Không phải mọi receiver type mới đều làm deoptimization. Optimized code có thể đã chứa checks/slow paths; việc deopt cụ thể phụ thuộc phiên bản và compiler strategy.

### 10.2. Uncommon traps

HotSpot có cơ chế **uncommon traps** cho những paths giả định hiếm gặp, như một nhánh/kiểu không được profile trước hoặc một tình huống cần quay về runtime.

Trên logs diagnostics, có thể thấy khái niệm `uncommon_trap`; điều đó không tự chứng minh ứng dụng có exception hay bug.

### 10.3. “Made not entrant” và “made zombie”

Một bản compiled code có thể được đánh dấu **not entrant**: runtime không dùng nó cho những lần method entry mới nữa, ví dụ vì đã có bản tối ưu hơn hoặc cần vô hiệu hóa code cũ. Quản lý lifecycle code cache về sau có thể chuyển code cũ sang trạng thái **zombie** khi không còn frames dùng phù hợp.

Các trạng thái này **không phải Java object bị GC thu hồi** theo kiểu application heap, và dòng log đó không nhất thiết là lỗi.

### 10.4. Deopt không được thay đổi kết quả đúng của chương trình

Nếu compiler tối ưu với assumptions, JVM vẫn phải bảo toàn Java semantics, bao gồm return values, exceptions, memory visibility và những side effects theo đặc tả.

## 11. Code cache — machine code JIT nằm ở đâu?

HotSpot lưu compiled methods ở **code cache**, một tập vùng bộ nhớ runtime cho code do JVM/JIT sinh. Nó khác Java heap chứa những object ứng dụng.

```text
Java heap:
   Object instances, arrays, class mirrors

Native/runtime memory:
   Code cache:
     - compiled C1 methods
     - compiled C2 methods
     - runtime/adapters/stubs theo VM
   Metaspace:
     - class metadata, method metadata theo HotSpot
```

Sơ đồ chỉ là cách phân loại khái niệm; các segment code cache cụ thể và phạm vi từng nhóm thay đổi theo JDK/build.

### 11.1. Compilation không miễn phí

Chi phí JIT bao gồm:

- CPU cho compiler threads.
- Memory cho compiler data structures và profiling.
- Code cache space cho compiled code.
- Instruction-cache pressure của machine code.
- Deoptimization/recompilation nếu profile thay đổi.

Không hợp lý nếu ép compile mọi method ngay startup chỉ vì compiled code có thể chạy nhanh hơn interpreted code.

### 11.2. Code cache đầy ảnh hưởng gì?

Nếu code cache đạt giới hạn khả dụng, JVM có thể hạn chế hoặc vô hiệu hóa thêm JIT compilation; app vẫn có thể tiếp tục nhưng throughput/latency có thể giảm. Ngữ nghĩa chính xác phụ thuộc HotSpot version/options.

Kiểm tra logs và metrics trước khi tăng code cache tùy tiện.

### 11.3. Thông số theo runtime

Một số flags để nhận diện:

```text
-XX:ReservedCodeCacheSize=...
-XX:+SegmentedCodeCache
```

Đây là HotSpot-specific options, không là phần bắt buộc trong Java Specification. Khi nghiên cứu, xem `java -XX:+PrintFlagsFinal -version` để biết giá trị thực trên JVM mục tiêu.

## 12. Java 17+ demo độc lập: chứng minh tính đúng, quan sát đường nóng qua JIT log

Tạo tệp **`HotMethodDemo.java`**:

```java
public final class HotMethodDemo {
    private static volatile long blackhole;

    static int transform(int x) {
        return (x * 31 ^ (x >>> 3)) & 1023;
    }

    static long loop(int count) {
        long sum = 0;
        for (int i = 0; i < count; i++) {
            sum += transform(i);
        }
        return sum;
    }

    public static void main(String[] args) {
        long calls = 0;
        for (int i = 0; i < 20_000; i++) {
            calls += transform(i & 255);
        }
        long loops = loop(1_000_000);
        blackhole = calls + loops;
        System.out.println("method calls=20000");
        System.out.println("call checksum=" + calls);
        System.out.println("loop checksum=" + loops);
        System.out.println("combined checksum=" + blackhole);
    }
}
```

### 12.1. Biên dịch/chạy theo chế độ mặc định

```bash
javac --release 17 HotMethodDemo.java
java HotMethodDemo
```

**Stdout chính xác của chương trình khi chạy thành công:**

```text
method calls=20000
call checksum=10169104
loop checksum=511499680
combined checksum=521668784
```

Tệp trên đã được thử bằng `javac --release 17` và chạy trên OpenJDK/HotSpot; kết quả trên cũng khớp khi chạy với `-Xint` và `-XX:-TieredCompilation`.

### 12.2. Giải thích ý đồ của demo

- `transform(int)` là method nhỏ được gọi nhiều lần.
- Vòng lặp ngoài `main` gọi `transform` **20.000 lần**, truyền dữ liệu trong khoảng `0..255`.
- `loop(1_000_000)` chỉ được gọi **một lần** nhưng có vòng lặp dài với nhiều backedges.
- `volatile blackhole` nhận kết quả để tạo một side effect có thể quan sát, giảm khả năng compiler bỏ hẳn tính toán do nó cho rằng không cần.
- `checksum` và `loop checksum` dùng phép tính số nguyên xác định; chương trình không lấy clock/timing làm đầu ra.

**Điều quan trọng:** `volatile` không tự bảo đảm **tất cả lời gọi đều còn là machine-level calls độc lập** hoặc JIT chắc chắn biên dịch level 4. JIT vẫn có thể inline/tối ưu miễn giữ đúng observable behavior.

### 12.3. Vì sao demo cố ý không in “số lần JIT”?

Số compilations, compile IDs, tiers, OSR events và thứ tự xuất hiện phụ thuộc HotSpot/JDK, platform, CPU và scheduling. Java Specification không cố định chúng.

Chương trình chỉ in kết quả logic ổn định. Để quan sát JIT, sử dụng **runtime diagnostics** riêng — đừng hardcode “sẽ thấy 3 lần compile” vào stdout.

## 13. Thực hành `-XX:+PrintCompilation`

Chạy:

```bash
java -XX:+PrintCompilation HotMethodDemo
```

Ở HotSpot JDK 17+, option này thường ghi các compilation events theo thời gian, gồm cả những methods của JDK. Output **không cố định** và có thể xen vào stdout của ứng dụng.

Để nghiên cứu, tìm những dòng chứa:

```text
HotMethodDemo::transform
HotMethodDemo::loop
HotMethodDemo::main
```

### 13.1. Cách hiểu các trường thường thấy

Một bản ghi có thể dạng:

```text
23   13       3       HotMethodDemo::transform (13 bytes)
26   15       4       HotMethodDemo::transform (13 bytes)
26   14 %     3       HotMethodDemo::loop @ 4 (25 bytes)
```

**Đây là các ví dụ định dạng được quan sát trên một lần thử HotSpot, KHÔNG phải output chuẩn cho mọi máy.** Các trường thường có:

- **Timestamp** tính từ khởi động VM (đơn vị/format theo output).
- **Compile ID** của nmethod/task.
- **Marker** như `%` cho OSR.
- **Compilation level** (chẳng hạn 3 cho C1 profiling, 4 cho C2).
- **Class::method** và phần bytecode size.
- **`@ bci`** trong trường hợp OSR.

Không giải thích `(13 bytes)` là **13 byte machine code**: đó thường là bytecode size của method, không phải compiled machine code footprint.

### 13.2. Nhìn thấy cả C1 và C2 cho cùng method

Nếu log có:

```text
... 3 ... HotMethodDemo::transform ...
... 4 ... HotMethodDemo::transform ...
```

thì đây là một bằng chứng runtime đã yêu cầu/hoàn tất compilation ở những tiers tương ứng trong lần chạy này. Nhưng **không có guarantee mỗi lần chạy đều xuất hiện cả hai bản hoặc đúng thứ tự trong stdout**.

### 13.3. OSR được đánh dấu bằng `%`

Một ví dụ:

```text
... % 3 HotMethodDemo::loop @ 4 ...
```

cho thấy phương thức có một **OSR compilation** cho loop tại BCI được ghi, chứ không phải “`loop` đã được gọi lại lần thứ ba”.

### 13.4. Dòng `made not entrant`

Bạn có thể thấy:

```text
... HotMethodDemo::transform ... made not entrant
```

Đây có thể là nmethod cũ được đưa khỏi compiled method entry khi có code tối ưu hơn, không phải fatal error. Cần xem timeline và runtime state trước khi đánh giá.

### 13.5. Log nhiều không có nghĩa chương trình sai

JVM cũng JIT compile một số methods của runtime/JDK trong cùng process. Nếu log có hàng trăm dòng không chứa `HotMethodDemo`, đó là bình thường.

## 14. Tách chế độ interpreter, tiered JIT và non-tiered để so sánh

### 14.1. Interpreter-only với `-Xint`

```bash
java -Xint HotMethodDemo
```

Trên HotSpot, `-Xint` yêu cầu thực thi Java bytecode theo interpreted mode, hữu ích làm đối chứng khi khảo sát hiệu ứng JIT. Nó **không có nghĩa mọi native runtime stub hoặc library call biến thành Java bytecode interpreted**.

**Stdout kết quả ứng dụng vẫn phải:**

```text
method calls=20000
call checksum=10169104
loop checksum=511499680
combined checksum=521668784
```

Chạy `-Xint` thường chậm hơn đối với compute-intensive workloads, nhưng không có quy luật một tỷ lệ cố định.

### 14.2. Tắt tiered compilation

```bash
java -XX:-TieredCompilation HotMethodDemo
```

Cờ này làm HotSpot không dùng chính sách tiered C1→C2 như mặc định. **Không diễn giải rằng tắt tiered là tắt toàn bộ JIT**: các compiler configurations vẫn có thể biên dịch methods bằng chế độ khác, tùy VM build.

### 14.3. Giới hạn tier bằng `TieredStopAtLevel`

```bash
java -XX:+TieredCompilation -XX:TieredStopAtLevel=1 HotMethodDemo
```

Trong HotSpot C1/C2 cấu hình phù hợp, cách đặt level 1 có thể giúp nghiên cứu đường C1 mà không đạt C2 level 4. Nhưng **nội dung “level 1” là chi tiết HotSpot**, không phải option portable mọi Java VM.

### 14.4. Bảng so sánh

| Cách chạy | Ý đồ | Điều không được suy |
| --- | --- | --- |
| `java HotMethodDemo` | Mặc định HotSpot/JDK hiện tại | Chắc chắn mọi hot method phải level 4 |
| `java -Xint HotMethodDemo` | Đối chứng interpreted execution | Mọi runtime/native code bị tắt |
| `java -XX:-TieredCompilation HotMethodDemo` | Không dùng tiered policy mặc định | JIT bị vô hiệu hoàn toàn |
| `java -XX:TieredStopAtLevel=1 HotMethodDemo` | Giới hạn tier trên build hỗ trợ | Tất cả methods đều compiled C1 level 1 |
| `java -XX:+PrintCompilation HotMethodDemo` | Ghi compilation events | Event count/timestamps cố định |

**Khi kiểm chứng một flag, đọc `java -version` và tài liệu JVM đang dùng.**

## 15. `PrintInlining`, `LogCompilation` và các công cụ chẩn đoán

### 15.1. PrintInlining

Trên các HotSpot builds hỗ trợ, có thể bật thông tin inlining khi compile:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining HotMethodDemo
```

Output có thể đề cập những thông tin như `inline (hot)`, `callee is too large` hoặc những lý do theo compiler heuristic. Cách in thay đổi theo JDK; **không dùng một chuỗi log cố định làm API**.

Nếu muốn kết hợp:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation \
     -XX:+PrintInlining HotMethodDemo
```

Dấu `\` ở cuối dòng là **cú pháp nối dòng của shell kiểu Bash**, không dùng y nguyên trên Windows PowerShell. Trên Windows, viết lệnh **một dòng** hoặc dùng cú pháp nối dòng phù hợp PowerShell.

### 15.2. PrintAssembly cần hỗ trợ bổ sung

Tùy bản HotSpot, các cờ kiểu `-XX:+PrintAssembly` hoặc compiler command để in machine code có thể cần tool/disassembler hỗ trợ, ví dụ thư viện `hsdis` tương ứng. Không giả định mọi JDK bundle đều hiển thị assembly có chú giải đầy đủ.

**Không dùng binary assembly dump làm ví dụ “stdout chuẩn”** vì khác CPU architecture, compiler/code layout và runtime.

### 15.3. `-XX:+LogCompilation`

HotSpot hỗ trợ logging chi tiết một số compilation metadata vào file với options diagnostic thích hợp. Việc đọc log thường kết hợp công cụ phân tích riêng.

Ví dụ gợi ý:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation HotMethodDemo
```

Log có thể tạo tệp tùy VM options/current directory; nên kiểm tra `java -XX:+PrintFlagsFinal -version`, quyền ghi và nơi output được tạo. Đừng sử dụng log này mà không cân nhắc kích thước/tác động lên workload production.

### 15.4. Java Flight Recorder (JFR)

JFR có thể ghi sự kiện liên quan JIT compilation/code cache, CPU usage và execution samples trên cấu hình hỗ trợ. Cần kiểm tra event settings trong build mục tiêu; không phải mọi compilation event đều bật trong mọi recording profile.

JFR giúp nối runtime behavior với application performance; `PrintCompilation` thường tiện hơn cho bài tập đơn giản vì log trực tiếp theo method.

### 15.5. `jcmd`

Nếu cần xem JVM đang chạy:

```bash
jcmd -l
jcmd <pid> Compiler.codecache
jcmd <pid> Compiler.queue
jcmd <pid> Compiler.codelist
```

Lệnh availability thay đổi theo JDK; thay `<pid>` bằng PID thực tế. Có thể kiểm tra:

```bash
jcmd <pid> help
```

Những lệnh này giúp quan sát compilation queue, code cache và compiled methods trong HotSpot; không phải API cần chạy ở mọi Java application.

## 16. Về thresholds và compilation policy: tránh ghi “một con số thần kỳ”

Một số tài liệu cũ nói “HotSpot compile sau 10.000 lần gọi”. Đó là cách diễn đạt **quá đơn giản**, đặc biệt với tiered compilation.

### 16.1. Các ngưỡng thực tế có thể phức tạp hơn

OpenJDK tiered policy có các ngưỡng điều khiển:

- Tần suất cập nhật và kiểm tra counters.
- Invocation thresholds theo tier.
- Backedge thresholds theo tier cho OSR.
- Min invocation thresholds.
- Tổng invocation + backedge activity.
- Queue-length factors làm điều chỉnh compilation policy.

Các tên option như `Tier3InvocationThreshold` hoặc `Tier4BackEdgeThreshold` thuộc phiên bản/cấu hình HotSpot, không nên xem là public stable API.

### 16.2. Thay ngưỡng thấp để “ép JIT” có đúng không?

Trong môi trường thử nghiệm, có thể chỉnh compilation policy flags để nghiên cứu. Nhưng **không coi threshold thấp hơn luôn làm ứng dụng nhanh hơn**:

- Compiler threads dùng thêm CPU.
- Method có thể không đủ profile tốt, dẫn đến speculation kém.
- Code cache có thể chịu áp lực.
- Compilation/recompilation chiếm tài nguyên startup.
- Benchmark dễ bị nhiễu.

### 16.3. Tại sao queue pressure ảnh hưởng cấp biên dịch?

Nếu hàng đợi C2 quá dài, việc đẩy quá nhiều methods lên C1 full profiling rồi chờ C2 có thể gây overhead profiling không đáng. Chính sách tiered có thể lựa chọn các lộ trình C1 phù hợp hơn theo tải compiler.

Tức “hotness” không chỉ là một counter độc lập; nó được kết hợp với **chi phí tài nguyên biên dịch**.

## 17. Inlining khiến method “nóng” khó nhìn thấy trong stack trace

Một call site hot có thể được tối ưu bằng **inlining**: body của callee được tích hợp vào caller, giúp giảm call overhead và mở khóa constant propagation, bounds-check elimination hoặc các tối ưu xuyên qua method boundary.

```java
static int twice(int x) {
    return x + x;
}

static int runMany(int n) {
    int sum = 0;
    for (int i = 0; i < n; i++) {
        sum += twice(i);
    }
    return sum;
}
```

Code này chỉ là **snippet**. JIT có thể inline `twice` vào `runMany`. Không bắt buộc kết quả phải có một call instruction riêng đến `twice` trong compiled machine code.

### 17.1. Tại sao nhìn runtime profile có thể khác hình dạng source?

- Một method Java có thể xuất hiện logic trong machine code của caller.
- Một method dài có thể được chia thành những compiled hot/cold paths.
- Speculative guard và uncommon-trap edges có thể không giống `if` source.
- OSR entry vào giữa loop khác normal method entry.

Thêm/bớt một method Java không tự quyết định chi phí method-call cuối cùng sau JIT.

### 17.2. Đừng dùng “trừu tượng hóa thành nhiều method nhỏ luôn chậm”

Java method boundaries có thể được inlined. Thiết kế source nên ưu tiên tính rõ ràng/correctness; những tối ưu hóa micro cần benchmark và profiling thật, không dựa vào số lời gọi nhìn thấy trong source.

## 18. Warm-up ảnh hưởng phép đo hiệu năng thế nào?

Một microbenchmark đo ngay lần gọi đầu:

```java
long start = System.nanoTime();
someMethod();
long elapsed = System.nanoTime() - start;
```

không chỉ đo “tốc độ của someMethod ở steady state”. Nó còn có thể gồm:

- Class loading/linking/initialization.
- Interpreter execution và runtime resolution.
- JIT compilation/warm-up đang diễn ra.
- GC và safepoints.
- Thread scheduling, CPU scaling/JIT code cache activity.
- Dead-code elimination, constant folding nếu phép đo không chống tối ưu đúng cách.

### 18.1. Một vòng lặp timing tự viết dễ sai

```java
for (int i = 0; i < 1_000_000; i++) {
    compute(42);
}
```

Snippet này chưa độc lập; `compute` cần khai báo. JIT có thể inline `compute`, hoist các computations bất biến hoặc loại bỏ những kết quả không được dùng. Đây là lý do “một triệu vòng” không tự là benchmark đáng tin.

### 18.2. JMH là lựa chọn ưu tiên cho microbenchmark

**JMH (Java Microbenchmark Harness)** của OpenJDK cung cấp warm-up iterations, measurement iterations, forks, blackholes và những cơ chế giảm bẫy benchmark. Nếu mục tiêu là đo mức tăng tốc do JIT/C1/C2, nên dùng JMH thay vì viết một vòng `nanoTime` tùy tiện.

Trang dự án: https://openjdk.org/projects/code-tools/jmh/

### 18.3. Benchmark cần ổn định environment

Giữ cùng:

- JDK vendor/build và VM flags.
- CPU quota/affinity, host load và power policies.
- Heap sizing và GC.
- Dữ liệu đầu vào/tỷ lệ nhánh/hình dạng đối tượng.
- Warm-up, forks và lượng samples.

Một khác biệt chỉ xảy ra ở một run chưa đủ để chứng minh C2 luôn cải thiện hiệu năng.

## 19. Một timeline học tập từ cold method đến hot path

Giả sử một service có `parse(int)` ở request handler:

```text
t0: JVM bắt đầu
    parse() chưa từng được gọi

t1: request đầu
    parse() được executed interpreted
    JVM thu các profiling/counter data phù hợp

t2: requests tăng
    invocation count tăng
    policy coi parse() đủ nóng
    enqueue C1 compile

t3: C1 version được published
    requests về sau có thể dùng C1
    profiling tier tiếp tục thu branch/type data

t4: requests tiếp tục
    policy có đủ profile, enqueue C2
    trong lúc đợi, application vẫn tiếp tục

t5: C2 version available
    requests mới có thể dùng optimized code
    parse() có thể inline vào handler

t6: kiểu input/call path mới xuất hiện
    guards/assumptions có thể bị invalidated
    deoptimization/recompilation có thể xảy ra
```

Đây là **timeline minh họa**, không nói rằng mọi service nhất định đi qua t2–t6 hoặc mỗi bước cần đúng một request. Một phương thức ít chạy mãi có thể không đến t2. Một loop dài có thể OSR mà method invocation count không lớn.

## 20. So sánh Java 17 HotSpot với các trường hợp ngoại lệ

### 20.1. Native methods

`native` methods thường thực thi qua native implementation/ABI/JNI, không phải bytecode Java thông thường để HotSpot C1/C2 biên dịch y hệt một Java method body.

### 20.2. Abstract methods

Một abstract method không có bytecode body để JIT compile độc lập. Những concrete implementations/call sites có thể được biên dịch và optimized.

### 20.3. Large or complex methods

Một số methods quá lớn hoặc không phù hợp với một compiler tier có thể không được compile ở cấp đó; VM có thể chọn tier khác, fallback hoặc để interpreted tùy policy. Không phải mọi hot method đều chắc chắn C2 level 4.

### 20.4. Synchronized methods

JIT có thể optimize synchronization trong các điều kiện hợp lệ, nhưng phải bảo đảm Java Memory Model. Không phải vì method hot mà JIT được xóa synchronization làm thay đổi correctness.

### 20.5. Exceptions

Các exception paths ít gặp có thể ảnh hưởng profiling/uncommon traps. Không nên cố tăng exception rate để “làm nóng” method mà không xét business correctness và GC/allocation overhead.

### 20.6. Multiple class loaders

Hai class cùng binary name do hai defining class loaders khác nhau tạo thành hai runtime classes khác. Compilation metadata/code và profiling có thể được tổ chức riêng theo method identity; không suy rằng một method được hot ở loader A thì loader B đã được compile tương tự.

## 21. Những hiểu lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Java luôn interpreted, không có machine code.” | HotSpot có JIT C1/C2 và chạy compiled native code khi phù hợp. |
| “`javac` tạo code C2.” | `javac` tạo bytecode; HotSpot JIT là bước runtime riêng. |
| “Mọi method chạy lần đầu đều được compile ngay.” | Interpreter có thể là điểm khởi đầu, compilation dựa policy/hotness. |
| “Hot = method có thời gian wall-clock lâu nhất.” | Invocation/backedge activity, profile, queue và heuristics quan trọng. |
| “Method được gọi 10.000 lần chắc chắn level 4.” | Không có ngưỡng tuyệt đối portable; tiered policy phức tạp hơn. |
| “Tier luôn đi lần lượt 0→1→2→3→4.” | Đường thường gặp là 0→3→4; có thể bỏ cấp/đổi đường. |
| “C1 là interpreter.” | C1 là JIT compiler tạo native code; level 0 là interpreter. |
| “C2 phải nhanh hơn C1 đúng một tỷ lệ.” | Tùy method/profile/CPU và benchmark. |
| “Chỉ method gọi nhiều lần mới hot.” | Một method gọi một lần có loop dài có thể cần OSR. |
| “OSR là một request gọi method mới.” | OSR có thể thay execution của frame đang chạy tại loop BCI. |
| “`%` trong PrintCompilation nghĩa lỗi.” | `%` thường là marker OSR compilation. |
| “`@ 4` trong OSR log là số lần gọi thứ tư.” | Nó chỉ một bytecode index (BCI), không phải invocation count. |
| “`13 bytes` trong log là kích thước machine code.” | Thường là bytecode method size. |
| “`made not entrant` nghĩa app hỏng.” | Thường là trạng thái compiled code không dùng cho entry mới. |
| “Deoptimization làm Java trả kết quả khác.” | JVM phải bảo toàn semantics khi chuyển execution/recompile. |
| “-Xint giống -XX:-TieredCompilation.” | `-Xint` yêu cầu interpreter; tắt tiered không đồng nghĩa tắt JIT. |
| “Thêm volatile field buộc từng call không inline.” | Volatile side effects phải bảo toàn, nhưng inlining vẫn có thể xảy ra. |
| “PrintCompilation luôn có cùng số dòng.” | Compilation events phụ thuộc JVM/load/timing, không deterministic. |
| “Inlining làm mọi API abstraction luôn free.” | Chỉ khi JIT thực sự inline/tối ưu theo điều kiện. |
| “Code cache là Java heap.” | Code cache là runtime memory khác với Java objects trong heap. |
| “JIT compiler chỉ chạy trước main().” | JIT có thể chạy bất kỳ lúc nào trong runtime khi method hot. |
| “Benchmark một run cold có thể kết luận steady-state performance.” | Cần warm-up/forks/JMH và đo nhiều runs. |

## 22. Tự kiểm tra kèm đáp án

**Câu 1.** `javac` biên dịch Java thành gì và C1/C2 biên dịch gì?

**Đáp án:** `javac` tạo bytecode trong `.class`; C1/C2 là các HotSpot runtime JIT compilers tạo machine code phù hợp CPU/runtime.

**Câu 2.** Vì sao method chỉ chạy một lần có thể không được JIT compile?

**Đáp án:** Chi phí compile/profiling có thể lớn hơn lợi ích từ một lần chạy; policy giữ interpreted là một lựa chọn hợp lý.

**Câu 3.** Có thể hot dù chỉ gọi một lần không?

**Đáp án:** Có. Một vòng lặp rất dài tăng backedge activity và có thể kích hoạt OSR.

**Câu 4.** Tier 0 tương ứng với gì?

**Đáp án:** Interpreter execution trong mô hình HotSpot tiered compilation.

**Câu 5.** Level 3 và level 4 khác nhau thế nào?

**Đáp án:** Level 3 là C1 với full profiling; level 4 là C2 optimized compiled code trong mô hình HotSpot thông thường.

**Câu 6.** Mọi method luôn đi qua C1 level 1 rồi mới level 2/3/4 không?

**Đáp án:** Không. Có thể đi 0→3→4 hoặc các đường khác tùy policy.

**Câu 7.** Invocation count và backedge count có cùng ý nghĩa không?

**Đáp án:** Không. Invocation đếm lần vào method; backedge liên quan loop iterations và có thể làm nóng loop trong một invocation.

**Câu 8.** OSR là gì?

**Đáp án:** On-Stack Replacement: runtime có thể chuyển frame đang chạy loop từ interpreted/compiled tier thấp sang OSR compiled code tại một vị trí bytecode phù hợp.

**Câu 9.** C2 dùng runtime profiles để làm gì?

**Đáp án:** Chọn/tối ưu những đường thường gặp, ví dụ inlining hoặc devirtualization, với guards và deoptimization khi cần để bảo toàn semantics.

**Câu 10.** Deoptimization có nghĩa “GC thu hồi compiled code” không?

**Đáp án:** Không. Nó liên quan việc vô hiệu hóa/rời optimized compiled execution và khôi phục trạng thái runtime phù hợp; code cache management là vấn đề riêng.

**Câu 11.** Vì sao sau warm-up hiệu năng có thể tăng?

**Đáp án:** Hot methods/loops có thể được JIT compile và tối ưu dựa trên profiling, nhưng mức tăng phụ thuộc workload.

**Câu 12.** `-Xint` có tắt JIT compilation cho bytecode ứng dụng trên HotSpot không?

**Đáp án:** Có, nó yêu cầu interpreted mode cho Java bytecode; nhưng không làm mọi thành phần native runtime biến mất.

**Câu 13.** `-XX:-TieredCompilation` có nghĩa giống `-Xint` không?

**Đáp án:** Không. Nó tắt tiered policy, không nhất thiết tắt mọi JIT compiler.

**Câu 14.** `PrintCompilation` có giúp chứng minh event compilation được log trong lần chạy đó không?

**Đáp án:** Có, đối với events/log format mà JVM báo; nhưng không cam kết tất cả compiler decisions sẽ luôn có cùng số dòng/timing.

**Câu 15.** Trong log `HotMethodDemo::loop @ 4`, số 4 thường là gì?

**Đáp án:** Bytecode index (BCI) dùng cho OSR compilation trong kiểu log đó.

**Câu 16.** Tại sao một method rất nhỏ có thể không xuất hiện như một machine-level call riêng biệt trong hot path?

**Đáp án:** JIT có thể inline nó vào caller.

**Câu 17.** Vì sao chỉ lấy `System.nanoTime` quanh một lời gọi cold không phải benchmark steady state?

**Đáp án:** Nó có thể bao gồm class initialization/interpreter/warm-up/JIT/GC/OS noise và bị compiler optimization đánh lừa.

**Câu 18.** Công cụ nào phù hợp hơn để xây Java microbenchmark có warm-up và forks?

**Đáp án:** OpenJDK **JMH**.

**Câu 19.** Khi code cache đầy, kết quả Java có được phép đổi không?

**Đáp án:** Không. JVM phải giữ semantics; có thể hạn chế compilation/tác động hiệu năng theo runtime.

**Câu 20.** Có thể ép mọi method hot sang level 4 trong một khoảng thời gian cố định không?

**Đáp án:** Không có guarantee API portable như vậy; policy, compiler queues, profile quality và constraints khác ảnh hưởng.

## 23. Checklist thực hành

1. Kiểm tra **`java -version`** để biết JVM vendor/build và tiered compiler availability.
2. Đọc class bytecode bằng `javap -c` khi cần hiểu method shape/loop backedges.
3. Phân biệt **method-entry compilation** với **OSR compilation**.
4. Sử dụng `-XX:+PrintCompilation` để nhìn compilation events, nhận diện levels 3/4, `%` và `@ BCI`.
5. Đừng so sánh timestamp/log count giữa hai runs như một hợp đồng.
6. Dùng `-Xint` làm đối chứng interpreted behavior, hiểu khác `-XX:-TieredCompilation`.
7. Quan sát inlining khi có công cụ, không đoán từ source.
8. Tránh tối ưu microbenchmark theo kết quả tính toán bị compiler loại bỏ.
9. Dùng JMH nếu mục tiêu là so sánh hiệu năng.
10. Đo compilation CPU, code cache và application latency khi chỉnh policy flags.
11. Ghi lại warm-up/forks/heap/CPU/GC để có kết quả lặp lại.
12. Tránh cài compilation thresholds trên production nếu chưa có bằng chứng đo lường.
13. Nếu throughput giảm sau khởi động lâu, kiểm tra code cache, deoptimizations và profile shifts.
14. Nếu application có class loaders/redeploy liên tục, nhớ compilation state và runtime class identity có vòng đời riêng.
15. Phân biệt **optimized machine code** với bảo đảm ngôn ngữ Java; correctness phải giống nhau qua interpreter/C1/C2.

### Tóm tắt cuối

```text
Cold method
     |
     v
HotSpot interpreter (tier 0)
     |
     +-- số calls thấp và loops ngắn --> có thể vẫn interpreted
     |
     +-- nhiều calls / loop backedges --> hotness / profiling
                                             |
                                             v
                                      JIT compilation policy
                                             |
                     +-----------------------+------------------+
                     |                                          |
                   C1 tiers                                 OSR entry
                  (1,2,3)                                cho loop nóng
                     |
                thu profile
                     |
                     v
               C2 (tier 4)
                     |
            guards / assumptions
                     |
                  deopt?
                     |
                     +--> interpreter / reprofile / recompile

GC, JIT và Java app vẫn là một tiến trình;
mọi đường thực thi phải giữ cùng Java semantics.
```

**Kết luận:** HotSpot không tối ưu mọi bytecode ngay lập tức. Nó **thực thi**, **quan sát**, **xác định code nóng**, rồi **biên dịch có chọn lọc** để cân bằng startup và throughput. Một method gọi nhiều lần có thể được C1 rồi C2 compile; một loop chạy dài có thể chuyển sang compiled code giữa chừng bằng OSR; tối ưu speculative có thể được hủy khi assumptions thay đổi. **Các bước này là chính sách HotSpot, không phải lịch cố định của ngôn ngữ Java.**

### Nguồn chính thức và tài liệu kỹ thuật

- [Oracle Java HotSpot VM FAQ — HotSpot, JIT và OSR](https://www.oracle.com/java/technologies/hotspotfaq.html): giải thích interpreter, JIT và on-stack replacement.
- [Oracle JDK 17 — `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xint`, `PrintCompilation`, `CompileCommand`, `TieredCompilation`, JIT/compiler flags.
- [OpenJDK — Tiered compilation policy sources](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.hpp): cách policy sử dụng invocation/backedge counters và compilation thresholds.
- [OpenJDK — Tiered threshold policy](https://cr.openjdk.org/~xliu/8165056/v4/webrev/src/hotspot/share/compiler/tieredThresholdPolicy.hpp.html): mô hình levels 0–4 và các đường transition.
- [Microsoft for Java Developers — How Tiered Compilation Works in OpenJDK](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/): phân biệt C1 levels, C2, profiling và deoptimization.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): thiết kế microbenchmark đúng với đặc điểm JIT và warm-up.
- [JVMS `2` — Structure of the JVM](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html): runtime model, bytecode và những gì JVM Specification quy định, không bắt buộc C1/C2.
