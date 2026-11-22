# Đối chiếu chế độ -Xint với thực thi kết hợp trong thí nghiệm có kiểm soát

## 1. Mục đích: đo một thay đổi JVM mà không đánh đồng tốc độ với tính đúng

Trong **HotSpot JVM**, cùng một tệp bytecode có thể được chạy bằng **trình thông dịch (interpreter)**, **mã máy do JIT biên dịch**, hoặc phối hợp cả hai. Hai tùy chọn quan trọng khi quan sát sự khác biệt là:

- **`-Xint`:** yêu cầu HotSpot thực thi **Java bytecode chỉ bằng interpreter**, tắt JIT compilation cho bytecode. Không còn lợi ích của machine code do JIT sinh cho các Java methods.
- **`-Xmixed`:** chế độ thực thi **kết hợp interpreter + JIT**: bytecode được diễn giải khi thích hợp; những methods/loops đủ nóng có thể được compile thành native machine code. Đây là **mặc định** ở HotSpot thông thường; có thể ghi tường minh để dễ đối chiếu.

Các modes này **không làm thay đổi ý nghĩa của ngôn ngữ Java**. Nếu một chương trình hợp lệ, không phụ thuộc data races hoặc những hành vi ngoài đặc tả, kết quả logic phải nhất quán dù bytecode chạy interpreted hay JIT-compiled. Điều có thể khác là **thời gian**, **CPU usage**, **warm-up**, **compilation activity** và cách JVM phân bố tài nguyên.

### Câu hỏi thí nghiệm cần trả lời

1. Hai chế độ có cho **cùng checksum/output** với cùng chương trình và input không?
2. Một workload tính toán lặp nhiều lần có **độ trễ** khác ra sao trong hai chế độ?
3. Vì sao lần khởi động đầu, giai đoạn warm-up và steady state phải **đo riêng**?
4. Dấu hiệu nào cho thấy JIT thực sự compile methods trong `-Xmixed`?
5. Có thể kết luận gì từ một lần đo, và điều gì **không thể kết luận**?
6. `-Xcomp`, `-XX:-TieredCompilation` và `-XX:TieredStopAtLevel` khác `-Xint` như thế nào?

**Giới hạn:** bài này hướng dẫn **thí nghiệm nhỏ có thể tái lập về mặt chương trình** trên HotSpot JDK 17+, không hứa cùng thời gian chạy, tỷ lệ tăng tốc hay cùng JIT compilation events trên mọi máy.

## 2. Hai lệnh gốc và điều thực sự khác nhau

Sau khi đã biên dịch một tệp Java thành class file:

```bash
java -Xint ExecutionModeDemo
java -Xmixed ExecutionModeDemo
```

Ở mức trực giác:

```text
                     Same .class bytecode
                              |
                     HotSpot JVM startup
                              |
              +---------------+----------------+
              |                                |
            -Xint                            -Xmixed
              |                                |
    Interpreter executes                 Interpreter starts
    application bytecode                  executing bytecode
              |                                |
      No JIT compilation                  invocation/backedge
      of Java bytecode                    hotness/profile data
              |                                |
              |                        sufficiently hot?
              |                           /          \
              |                         no            yes
              |                         |              |
              |                    interpreter     C1 / C2 JIT
              |                                         |
              +----------------+------------------------+
                               |
                         Same Java semantics
                               |
                      Different CPU and timing
```

Sơ đồ minh họa **không phải một lịch compile cố định**: JVM có thể tạo C1/C2 code, OSR code cho loop, inline methods, deoptimize code hoặc không bao giờ JIT compile những methods chạy quá ít.

### 2.1. `-Xint` có tắt toàn bộ native code của tiến trình không?

**Không.** HotSpot vẫn có runtime code viết bằng C/C++, native stubs, VM services, system calls, JNI và những phần JVM không phải bytecode Java thuần túy. `-Xint` nói rằng **Java bytecode được thực thi theo interpreter**, không phải “CPU không được chạy bất kỳ native instruction nào”.

Một ứng dụng gọi native library vẫn dùng library đó; đừng mô tả `-Xint` là chế độ “mọi thao tác đều chạy dưới interpreter”.

### 2.2. `-Xmixed` có nghĩa tất cả methods đều JIT ngay không?

**Không.** Một cold method có thể vẫn interpreted. JIT compilation được quyết định bởi **HotSpot compilation policy**, các counters, profiling và tài nguyên compiler/code cache. Trong HotSpot tiered configuration, những methods nóng có thể qua C1 rồi C2, và những loop dài có thể kích hoạt on-stack replacement (OSR).

### 2.3. Cả hai modes vẫn dùng GC

Interpreter-only không vô hiệu hóa garbage collection, class loading, verifier, synchronization, heap management hay memory safety của Java. Một lần đo `-Xint` có thể chậm do interpreted execution và vẫn có GC pauses; một lần đo `-Xmixed` có thể xuất hiện JIT compilation và GC.

**Chỉ kết luận nguyên nhân thời gian chậm khi có bằng chứng**, không tự gán mọi millisecond chênh lệch cho JIT.

## 3. Định nghĩa “thí nghiệm có kiểm soát” trong JVM

Đối với bài này, **biến độc lập** là execution mode `-Xint` hoặc `-Xmixed`. Những yếu tố còn lại cố gắng giữ nguyên:

| Thành phần | Thiết lập thí nghiệm |
| --- | --- |
| JVM vendor/build | Cùng đường dẫn `java`, cùng `java -version` |
| Java class files | Cùng `ExecutionModeDemo.class` do `javac --release 17` tạo |
| Input | Cùng warm-up calls, measured calls, steps per call |
| Heap flags | Ban đầu để JVM defaults giống nhau; nếu đặt `-Xms/-Xmx` thì cả hai modes cùng dùng |
| Machine | Cùng host/container, CPU quota và workload nền càng ổn định càng tốt |
| Chế độ chạy | Từng process riêng, mỗi lần chỉ đổi `-Xint`/`-Xmixed` |
| Đo | Cùng cách gọi `System.nanoTime`, không in ra console bên trong vòng tính |
| Kết quả | So sánh checksum đúng trước, latency sau |
| Lặp | Nhiều runs độc lập, đổi/thay phiên thứ tự để giảm bias |

**Vì sao cần process riêng?** Một JVM đang chạy có trạng thái profiling/compiled methods, heap và caches tích lũy theo thời gian. Chạy hai chế độ trong hai processes mới giúp không dùng nhầm compiled code đã làm nóng của lần thử trước.

### 3.1. Biến phụ thuộc cần quan sát

- **Correctness:** checksum và các giá trị logic in ra.
- **Elapsed time:** thời gian *measured section* tính bằng `System.nanoTime()`.
- **Time per call:** có thể tính từ elapsed time và số calls, nhưng phải hiểu đó là average của workload đang đo, không phải thời gian từng invocation.
- **Compilation activity:** log `-XX:+PrintCompilation` khi dùng `-Xmixed`.
- **Whole-process time:** có thể đo riêng từ bên ngoài, bao gồm JVM startup, class loading và teardown.
- **CPU/memory:** thông số OS, nếu mục tiêu thí nghiệm mở rộng.

### 3.2. Thứ không thể kiểm soát tuyệt đối

- CPU frequency/boost, nhiệt độ và power management.
- Scheduling, JVM compiler threads, background services.
- GC timing và safepoints.
- Cache state, JIT inlining choices, deoptimization.
- JDK ergonomics và available CPUs của container.
- Native code/intrinsics sử dụng bởi Java standard library.

Vì vậy phải **đo nhiều lần và báo phân phối kết quả**, thay vì một “giá trị chuẩn cho mọi máy”.

## 4. Chuẩn bị môi trường Java 17+

Đầu tiên xác nhận runtime:

```bash
java -version
javac -version
```

Để biết JVM có hỗ trợ HotSpot flags nào:

```bash
java -Xint -version
java -Xmixed -version
```

Những lệnh trên **không phải benchmark**: chúng chỉ kiểm tra parser/runtime nhận các options và in thông tin JVM. Không suy rằng `java -Xint -version` nhanh/chậm hơn `java -Xmixed -version` là kết quả cho một ứng dụng thực.

Nên dùng một JDK với đủ `java` và `javac` tương thích. Nếu IDE cấu hình nhiều JDK, **xác minh chính xác binary** đang dùng để chạy hai modes; nếu không, sự khác biệt phiên bản có thể lớn hơn sự khác biệt execution mode.

### 4.1. Cần cùng JVM implementation

`-Xint` và `-Xmixed` trong bài này là **HotSpot-specific execution mode switches**. Những VM khác có thể hỗ trợ, từ chối hoặc triển khai khác. Không tuyên bố mọi JVM buộc có hai options theo Java Language Specification.

### 4.2. Không thêm logging vào vòng đo ngay lúc đầu

Các flags `PrintCompilation`, `PrintInlining` và logging chi tiết có thể phát sinh I/O, thay đổi timing/scheduling. Trước tiên đo baseline **không bật diagnostic output**, sau đó **chạy lại riêng** để quan sát compiler events.

## 5. Ví dụ Java 17+ hoàn chỉnh cho cả hai chế độ

Tạo tệp **`ExecutionModeDemo.java`** với toàn bộ nội dung sau:

```java
public final class ExecutionModeDemo {
    private static volatile long sink;

    static int mix(int x) {
        x ^= x >>> 13;
        x *= 0x5bd1e995;
        x ^= x >>> 15;
        return x;
    }

    static long work(int calls, int steps) {
        long total = 0;
        for (int c = 0; c < calls; c++) {
            int value = c + 1;
            for (int i = 0; i < steps; i++) {
                value = mix(value + i);
            }
            total += Integer.toUnsignedLong(value);
        }
        sink = total;
        return total;
    }

    public static void main(String[] args) {
        final int warmupCalls = 800;
        final int measuredCalls = 1500;
        final int steps = 1024;

        work(warmupCalls, steps);
        long start = System.nanoTime();
        long checksum = work(measuredCalls, steps);
        long nanos = System.nanoTime() - start;

        System.out.println("warmupCalls=" + warmupCalls);
        System.out.println("measuredCalls=" + measuredCalls);
        System.out.println("stepsPerCall=" + steps);
        System.out.println("checksum=" + checksum);
        System.out.println("sinkMatches=" + (sink == checksum));
        System.out.printf(java.util.Locale.ROOT,
                "elapsedMs=%.3f%n", nanos / 1_000_000.0);
    }
}
```

Chương trình có:

- Một **method nhỏ `mix`** đủ đơn giản để JIT có thể cân nhắc inlining.
- Một **`work`** chứa hai vòng lặp; workload đủ rõ để đếm số lần thực hiện.
- **Data dependency**: kết quả iteration trước là đầu vào iteration sau, giảm nguy cơ toàn bộ loop trở thành phép tính bất biến tầm thường.
- **`volatile sink`** làm giá trị tính cuối trở thành một side effect có thể quan sát; không tự đảm bảo mọi machine instruction giống nhau giữa hai modes.
- **Warm-up trước đo** và sử dụng `System.nanoTime` cho **khoảng đo**.
- **Không in log trong vòng lặp tính**, tránh I/O áp đảo computation.
- **`Locale.ROOT`** để định dạng dấu thập phân trong dòng timing nhất quán hơn giữa các locale.

### 5.1. Biên dịch

```bash
javac --release 17 ExecutionModeDemo.java
```

Sử dụng cùng class file cho mọi lần chạy. Không cần build bằng các flags `-Xint`/`-Xmixed` vì chúng là **runtime options** của lệnh `java`, không phải tùy chọn compile source của `javac`.

### 5.2. Chạy hỗn hợp mặc định và tường minh

```bash
java ExecutionModeDemo
java -Xmixed ExecutionModeDemo
```

Trên HotSpot, `-Xmixed` là execution mode mặc định điển hình, nhưng thực tế cần xem JVM options/environment nếu có cấu hình đặc biệt.

### 5.3. Chạy interpreter-only

```bash
java -Xint ExecutionModeDemo
```

### 5.4. Các dòng stdout xác định

Khi chạy thành công ở cả hai modes, **năm dòng đầu** phải là:

```text
warmupCalls=800
measuredCalls=1500
stepsPerCall=1024
checksum=3215795315003
sinkMatches=true
```

**Dòng cuối là số đo biến thiên**, ví dụ định dạng:

```text
elapsedMs=2.291
```

Giá trị `2.291` là **một phép đo cục bộ của một lần chạy** `-Xmixed` khi thử nghiệm, **không phải stdout chính xác cố định**. Chạy lại hoặc dùng `-Xint` sẽ cho elapsedMs khác. Cần phân biệt **kết quả logic đã được kiểm chứng** và **thời gian đo không mang guarantee**.

### 5.5. Kiểm tra thực nghiệm đã thực hiện

Ví dụ đã được biên dịch với `javac --release 17`, sau đó chạy trên OpenJDK/HotSpot ở bốn cấu hình:

- `-Xmixed`
- `-Xint`
- `-XX:-TieredCompilation`
- `-Xcomp`

Cả bốn lần chạy đều in cùng **checksum `3215795315003`** và `sinkMatches=true`. Việc chúng có thời gian khác nhau không chứng minh rằng mỗi cấu hình sẽ có cùng thứ hạng tốc độ trên mọi hệ thống; cách triển khai JDK/build và lượng warm-up có ảnh hưởng lớn.

## 6. Giải thích chính xác phép đo của chương trình

### 6.1. Workload đã làm những gì?

`work(warmupCalls, steps)` gọi `mix` bên trong 800 × 1024 iterations. Tiếp đó `work(measuredCalls, steps)` làm thêm 1500 × 1024 iterations dưới khoảng `nanoTime`.

Tổng số thao tác `mix` theo cấu trúc vòng lặp Java:

```text
Warm-up:   800 × 1024 =   819,200 iterations
Measured: 1500 × 1024 = 1,536,000 iterations
Total:                = 2,355,200 iterations
```

Đây là **số lần đánh giá logic** từ cấu trúc Java, không nhất thiết là số machine-level call instructions. JIT có thể inline `mix` vào `work`.

### 6.2. Vì sao checksum giống nhau?

Phép tính dùng integer arithmetic với Java semantics:

- Dịch bit không dấu `>>>`.
- Nhân `int` theo quy tắc overflow/wrap-around modulo \(2^{32}\).
- XOR bitwise.
- `Integer.toUnsignedLong` chuyển `int` thành giá trị long không dấu tương ứng.

Dù interpreter hay compiled code thực thi, **kết quả Java phải giống nhau** nếu JVM hợp lệ.

### 6.3. `sinkMatches=true` có tác dụng gì?

`sink` là static volatile field được gán trong `work`. Sau khi đo, code đọc lại nó để kiểm tra kết quả được giữ. Việc viết volatile là một **observable side effect** theo Java Memory Model, tránh một số tình huống benchmark đơn giản trong đó JIT có thể loại hẳn phép tính vì kết quả không được sử dụng.

Tuy nhiên đây **không phải blackhole hoàn hảo của JMH** và không ngăn mọi hình thức compiler optimization. Bài demo thích hợp để học chế độ thực thi; không thay công cụ benchmark chuyên dụng.

### 6.4. `System.nanoTime()` đo gì?

Nó trả giá trị thời gian đơn điệu phù hợp để đo **elapsed durations** khi lấy hiệu, không phải đồng hồ wall-clock có ngày/tháng/năm. Phép đo:

```java
long start = System.nanoTime();
long result = work(1500, 1024);
long elapsed = System.nanoTime() - start;
```

là đoạn minh họa lấy từ chương trình. `elapsed` là **thời gian trôi qua giữa hai lần đọc clock**, bao gồm những gián đoạn có thể xảy ra như scheduler preemption, GC pauses hoặc JIT compilation xen vào. Nó không phải thời gian CPU thuần của riêng hàm `work`.

### 6.5. Vì sao không in “thời gian chuẩn” cố định?

Trên mỗi JDK/OS/CPU, elapsed time có thể thay đổi. Ngay trên cùng một máy, lần đầu chạy, các lần sau, CPU load và compilation timing cũng khác. **Không bao giờ so elapsedMs với một hằng số cố định để chấm pass/fail**.

## 7. Warm-up của `-Xmixed` và `-Xint` có ý nghĩa khác nhau

Ở **`-Xmixed`**, warm-up có thể:

- Nạp, verify, link và initialize những classes cần thiết.
- Thực thi những paths bằng interpreter.
- Tăng invocation/backedge counters.
- Thu branch/type profiles.
- Kích hoạt C1/C2 compilation và OSR khi đủ điều kiện.
- Làm nóng code/data cache.

Ở **`-Xint`**, warm-up vẫn có thể làm những việc như **class loading, initialization, cache warming và GC activity**, nhưng **không chuyển bytecode Java sang JIT-compiled native code** theo chế độ đó.

Do vậy:

> Warm-up là một bước kiểm soát tình trạng khởi động, nhưng “warm-up cùng số iterations” **không có nghĩa JVM đạt cùng trạng thái tối ưu hóa**.

### 7.1. Warm-up không tự bảo đảm steady state

800 × 1024 iterations trong demo là mức thực hành, **không cam kết** JIT đã đạt C2 level 4 cho mọi method trước khi lấy `start = System.nanoTime()`. Các compiler threads có thể vẫn đang xử lý công việc trong lúc measured phase bắt đầu.

Muốn nghiêm túc phân tích steady state, cần quan sát JIT logs/traces hoặc tăng warm-up bằng những điều kiện benchmark được thiết kế đúng, thay vì chỉ giả định số lần cố định là đủ.

### 7.2. Khi nào `-Xint` có thể tỏ ra tương tự `-Xmixed`?

Nếu chương trình **rất ngắn**, khởi động/chấm dứt process và I/O chiếm phần lớn thời gian, sự khác biệt ở phần bytecode được compile có thể rất nhỏ. Chi phí JVM startup cũng có thể che khuất khác biệt computation.

Vì vậy nếu chỉ đo `java -Xint -version` vs `java -Xmixed -version`, bạn chưa đo lợi ích thực tế của JIT trên code nóng.

### 7.3. Ngược lại, công việc rất nóng có thể làm chênh lệch lớn

Khi cùng một phép tính chạy hàng triệu lần, interpreter phải xử lý bytecode trong nhiều iterations, còn JIT có thể optimize/inlining/strength reduction theo dữ liệu runtime. Nhưng mức tăng tốc cụ thể **không được Java Specification cam kết** và phụ thuộc workload.

## 8. Một kết quả thử nghiệm cục bộ và cách diễn giải

Trong một lần chạy bằng OpenJDK/HotSpot, chương trình trả những elapsed times sau:

| Chế độ | Measured section | Correctness |
| --- | ---: | --- |
| `-Xmixed` | **2.291 ms** | PASS — checksum giống |
| `-Xint` | **25.124 ms** | PASS — checksum giống |
| `-XX:-TieredCompilation` | **2.230 ms** | PASS — checksum giống |
| `-Xcomp` | **4.327 ms** | PASS — checksum giống |

**Đây là một mẫu đo cục bộ duy nhất, chỉ minh họa cách đọc dữ liệu**, không phải dữ liệu benchmark đủ để tuyên bố `-Xmixed` nhanh hơn `-Xint` đúng 10.97 lần cho mọi chương trình. Không dùng bảng này làm SLA, threshold hay guideline chọn production flag.

### 8.1. Cách hiểu đúng

Trong mẫu cục bộ, measured section với `-Xmixed` ngắn hơn `-Xint`. Điều này **phù hợp** với dự đoán rằng hot computation được hưởng lợi từ JIT. Tuy nhiên, chỉ từ elapsedMs chưa thể phân tách chính xác số millisecond dành cho compilation, GC, CPU scheduling và machine-code execution.

### 8.2. Cách hiểu sai

Không được kết luận:

- “Mọi Java service đều chậm gấp mười nếu bật `-Xint`.”
- “`-Xcomp` luôn nhanh hơn `-Xint` nhưng chậm hơn `-Xmixed`.”
- “`-XX:-TieredCompilation` luôn là cấu hình production nhanh nhất.”
- “Không có GC/JIT overhead vì chương trình chỉ in sáu dòng.”
- “Một lần đo đủ để xếp hạng các VM flags.”

**Mọi kết luận hiệu năng cần repetitions, mô tả môi trường và phân phối số đo.**

## 9. Lặp thí nghiệm và chống sai lệch thứ tự

Một cách học có kiểm soát:

1. Biên dịch tệp **một lần**, không rebuild giữa hai modes.
2. Chạy **ít nhất vài vòng độc lập** cho mỗi chế độ.
3. Không mở IDE build/indexing nặng song song nếu có thể.
4. Xen kẽ thứ tự thay vì luôn chạy tất cả `-Xint` trước rồi tất cả `-Xmixed`.
5. Ghi lại từng `elapsedMs`, không chỉ chọn lần nhanh nhất.
6. So sánh median, độ phân tán (p25/p75 hoặc p95) và kiểm tra outliers.
7. Khi số liệu không ổn định, tăng repetitions hoặc điều tra CPU/GC/I/O.

### 9.1. Lệnh trên shell kiểu Bash

Một vòng chạy thử, mỗi mode là một process riêng:

```bash
for mode in -Xmixed -Xint; do
  echo "MODE: $mode"
  for run in 1 2 3 4 5; do
    java "$mode" ExecutionModeDemo
  done
done
```

Đây là **lệnh Bash/POSIX-like shell**, không áp dụng nguyên xi cho PowerShell.

### 9.2. Lệnh trên Windows PowerShell

```powershell
foreach ($mode in @("-Xmixed", "-Xint")) {
    Write-Output "MODE: $mode"
    foreach ($run in 1..5) {
        java $mode ExecutionModeDemo
    }
}
```

Lệnh trên chỉ thực hiện nhiều lần và hiển thị kết quả, **chưa tự tính median**. Có thể xuất `elapsedMs` sang file rồi phân tích bằng spreadsheet/script nếu cần.

### 9.3. Cần giữ cả stdout correctness

Đừng chỉ lưu dòng `elapsedMs` mà bỏ checksum. Nếu chương trình tính sai, bị OOME, thất bại do flag, hoặc input bị thay đổi, số thời gian ấy không còn so sánh cùng công việc.

### 9.4. Vì sao nên đảo thứ tự?

Nếu JVM/OS vừa khởi động hoặc CPU chuyển power state, các lần chạy về sau có thể nhanh/chậm khác. Khi luôn chạy một mode trước, **mode order** trở thành biến gây nhiễu. Xen kẽ `-Xint` và `-Xmixed` giúp giảm một số bias, dù không loại bỏ được mọi yếu tố ngoại lai.

### 9.5. JVM startup vs measured section

`elapsedMs` của chương trình **không bao gồm việc tạo process và phần startup trước `main`**; nó đo vùng code giữa hai `nanoTime`. Nếu mục tiêu là thời gian end-to-end của CLI, cần thêm một phép đo từ bên ngoài process:

```powershell
Measure-Command { java -Xint ExecutionModeDemo }
Measure-Command { java -Xmixed ExecutionModeDemo }
```

Output của `Measure-Command` khác dòng `elapsedMs`, vì có **JVM startup + class loading + program + shutdown + shell/process overhead**. Đây là hai metrics khác nhau, không nên cộng hoặc thay thế nhau.

## 10. Kiểm chứng đường JIT bằng `PrintCompilation`

Để biết `-Xmixed` có thực sự kích hoạt JIT hay không, chạy một lượt **diagnostic riêng**:

```bash
java -Xmixed -XX:+PrintCompilation ExecutionModeDemo
```

Trên HotSpot có hỗ trợ, option này in **các sự kiện compilation**, thường có:

- Timestamp tương đối từ lúc khởi động VM.
- Compile ID.
- Compilation level (nếu tiered).
- Marker `%` khi dùng OSR.
- Class/method, bytecode size.
- Những sự kiện đánh dấu compiled code không còn được dùng cho method entry.

Lệnh có thể trộn compilation logs với stdout của chương trình. **Không dùng trực tiếp thời gian của diagnostic run làm baseline sạch**, vì log I/O có thể ảnh hưởng scheduling/performance.

### 10.1. Một số dòng kiểu mẫu đã được quan sát

```text
27   13       3       ExecutionModeDemo::mix (21 bytes)
27   14       4       ExecutionModeDemo::mix (21 bytes)
28   15 %     3       ExecutionModeDemo::work @ 20 (62 bytes)
28   17 %     4       ExecutionModeDemo::work @ 20 (62 bytes)
```

Đây là **trích mẫu từ một lần chạy thử** trong môi trường kiểm tra. Số đầu dòng, ID, cấp compilation và thứ tự events **không là đầu ra chuẩn cố định**. Một máy khác hoặc lần chạy khác có thể không sinh đúng các dòng này.

### 10.2. Cách đọc level 3 và 4

Trong mô hình HotSpot tiered C1/C2 thông thường:

- **Level 0:** Interpreter.
- **Level 1:** C1 simple (no profiling).
- **Level 2:** C1 với limited profiling.
- **Level 3:** C1 với full profiling.
- **Level 4:** C2 tối ưu hóa mạnh.

Một method **có thể đi theo đường 0 → 3 → 4**, nhưng không bắt buộc phải qua mọi levels hay compile lên level 4.

### 10.3. `%` là gì?

Trong `PrintCompilation`, ký hiệu `%` thường cho biết **OSR (On-Stack Replacement)** compilation, tức JVM có thể chuyển execution state của một loop đang chạy sang compiled code tại một **bytecode index (BCI)** phù hợp.

Ví dụ `ExecutionModeDemo::work @ 20` cho thấy một vị trí BCI liên quan loop, **không phải invocation thứ 20**.

### 10.4. `(21 bytes)` có phải độ dài machine code không?

Không. Trong dòng `PrintCompilation`, kích thước hiển thị thông thường là **bytecode size của method**, không phải tổng machine instructions được sinh. C2-compiled code có thể dài hơn hoặc ngắn hơn tùy optimization/code shape.

### 10.5. Vì sao có dòng `made not entrant`?

Một nmethod cũ có thể bị đưa vào trạng thái không còn dùng cho những entry mới sau khi phiên bản compiled code tốt hơn xuất hiện hoặc assumption không còn hợp lệ. Đây **không tự là lỗi ứng dụng**.

## 11. Kiểm tra sự khác biệt giữa `-Xint` và `-Xmixed` trong logs

### 11.1. `-Xmixed`

```bash
java -Xmixed -XX:+PrintCompilation ExecutionModeDemo
```

Có thể thấy `ExecutionModeDemo::mix`, `ExecutionModeDemo::work` và những methods của JDK được JIT compile. Nhưng **không cam kết mọi method xuất hiện trong log**: policy, inlining, startup và compilation timing có thể thay đổi.

### 11.2. `-Xint`

```bash
java -Xint -XX:+PrintCompilation ExecutionModeDemo
```

Trên HotSpot interpreter-only, JVM không JIT compile Java bytecode của demo, nên bạn **không nên mong chờ các C1/C2 compilation events** cho những methods Java như trong `-Xmixed`. Diagnostics khác hoặc thông tin JVM có thể vẫn được in tùy options/runtime.

**Tránh suy luận quá mức từ “log rỗng”**: log chỉ cho thấy thông tin công cụ bật và VM ghi nhận, không phải một phép chứng minh tuyệt đối về tất cả code/native instructions đang thực thi.

### 11.3. Dòng in compiler không quyết định mức tăng tốc

Nhìn thấy `level 4` có thể cho thấy method đã được C2 compile trong lần chạy ấy, nhưng tốc độ thật còn chịu ảnh hưởng inlining, CPU, GC, code cache, data distributions và workload.

Không nên xếp hạng code chất lượng chỉ bằng “bao nhiêu methods level 4”.

## 12. Khác biệt quan trọng với `-Xcomp`

**`-Xcomp`** là chế độ dùng để **stress/test compiler** bằng cách ưu tiên compile methods thay vì chạy interpreted. Theo tài liệu OpenJDK/Oracle, đây là **testing mode**, không phải option được khuyến nghị dùng trong production để tăng tốc.

```bash
java -Xcomp ExecutionModeDemo
```

### 12.1. Vì sao `-Xcomp` có thể khởi động chậm hơn?

Một ứng dụng rất ngắn có nhiều methods chỉ chạy một lần. Biên dịch những methods này có thể tốn nhiều thời gian hơn lợi ích thu được từ machine code khi chúng gần như không được tái sử dụng.

Vì thế không nên coi “compile sớm mọi thứ” chắc chắn nhanh hơn interpreter + selective JIT.

### 12.2. `-Xcomp` không bảo đảm C2 level 4 cho mọi method

Flag này thay chính sách thực thi/biên dịch để stress JIT; nó **không cam kết** compiler level 4 trong mọi trường hợp. JVM có thể có những giới hạn/compiler policies khác, hoặc một số methods không phù hợp để compile theo cách mong đợi.

### 12.3. Không đưa `-Xcomp` vào baseline production

Trong một thí nghiệm mở rộng, bạn có thể chạy `-Xcomp` để quan sát chi phí compilation/startup, nhưng **trọng tâm so sánh hợp lý nhất vẫn là `-Xint` vs `-Xmixed`** khi phân tích lợi ích selective JIT của HotSpot.

## 13. `-XX:-TieredCompilation` không đồng nghĩa `-Xint`

Hai flags:

```bash
java -XX:-TieredCompilation ExecutionModeDemo
java -Xint ExecutionModeDemo
```

**không cùng nghĩa**.

- `-Xint`: tắt JIT compilation cho Java bytecode.
- `-XX:-TieredCompilation`: tắt **tiered compilation policy**, không nhất thiết tắt JIT; tùy HotSpot build, một optimizing compiler vẫn có thể compile methods.

Nếu hai lần chạy vô tình có elapsedMs gần bằng nhau, **không thể kết luận chúng dùng cùng engine**.

### 13.1. `-XX:TieredStopAtLevel=1`

```bash
java -XX:+TieredCompilation -XX:TieredStopAtLevel=1 ExecutionModeDemo
```

Với HotSpot tiered C1/C2 hỗ trợ flag, cấu hình này giới hạn mức compilation tối đa ở level tương ứng, hữu ích khảo sát C1. Nó **không phải** interpreter-only vì C1 là JIT compiler sinh machine code.

### 13.2. Tại sao không so sánh tất cả flags trong một bảng “hơn/thua” tuyệt đối?

Các flags khác nhau ở mục đích:

| Mode | Câu hỏi thí nghiệm | Giới hạn |
| --- | --- | --- |
| **`-Xint`** | Bytecode interpreted tốn bao lâu? | Không có JIT hot-path optimizations |
| **`-Xmixed`** | Interpreter + selective JIT hoạt động ra sao? | Có warm-up và compiler scheduling |
| **`-XX:-TieredCompilation`** | Không dùng tiered heuristics thì sao? | JIT vẫn có thể hoạt động |
| **`-XX:TieredStopAtLevel=1`** | C1-only-like path ra sao? | Không dùng C2 level 4; tùy build |
| **`-Xcomp`** | Compiler stress/testing có gì xảy ra? | Startup và compilation cost có thể lớn |

Nếu mục đích chỉ là so `-Xint` với default JVM, không cần tự động kết luận mode thứ ba nào đó “tốt hơn”.

## 14. Inlining: tại sao Java method calls không tương đương machine-code calls?

Trong demo:

```java
static int mix(int x) {
    x ^= x >>> 13;
    x *= 0x5bd1e995;
    x ^= x >>> 15;
    return x;
}
```

Một loop trong `work` gọi method `mix` mỗi iteration. JIT có thể **inline body của `mix` vào loop**, tức machine code không nhất thiết phải thực hiện một native method call riêng cho mỗi iteration.

### 14.1. Vì sao điều này quan trọng?

Với interpreter, JVM thực hiện theo bytecode execution model; HotSpot JIT có thể loại bỏ overhead gọi method và tối ưu xuyên qua method boundary. Đây là một lý do compute-intensive repeated workloads có thể hưởng lợi từ `-Xmixed`.

Nhưng cùng một code có thể cho kết quả khác nếu JIT quyết định không inline vì size, profile, code cache hoặc heuristics.

### 14.2. `PrintInlining`

Trên một số HotSpot builds:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining ExecutionModeDemo
```

Output có thể in những quyết định inlining và lý do. Đây là **run diagnostic**, không nên trộn vào phép đo baseline cần độ sạch.

### 14.3. Đừng kết luận mỗi lần gọi `mix` mất đúng một fixed nanosecond

Thời gian có thể phụ thuộc instruction scheduling, CPU cache, inlining, arithmetic throughput, branch predictors và đo lường. Method-call overhead không bằng một con số cố định cho mọi JVM.

## 15. OSR: vòng lặp có thể nóng dù method không được gọi nhiều

**On-Stack Replacement (OSR)** cho phép HotSpot chuyển một loop đang chạy interpreted/C1 sang một entry native compiled tương ứng trong quá trình method chưa return.

Trong demo, phương thức `work` có vòng lặp trong. Một lần gọi `work(800, 1024)` thực hiện nhiều iterations mà invocation count của chính `work` có thể ít. **Backedge counts** của loop có thể kích hoạt OSR.

```text
work() method invocation
      |
      v
Interpreter / tier thấp
      |
      v
loop backedge activity tăng
      |
      +---- compiler policy requests OSR at BCI
                           |
                           v
                      OSR nmethod
                           |
                   execution chuyển state
                           |
                           v
                    tiếp tục loop đúng
```

### 15.1. `%` trong `PrintCompilation`

Một bản ghi:

```text
28   15 %     3       ExecutionModeDemo::work @ 20 (62 bytes)
```

là ví dụ một **OSR compilation event**, không phải “method `work` được gọi 15 lần” hay “method nóng sau 28 ms đúng trên mọi máy”.

### 15.2. OSR không buộc xuất hiện

Khi vòng lặp quá ngắn, interpreter-only được bật, hoặc compiler chọn đường khác, OSR có thể không xảy ra. Không viết unit test assert “phải thấy ký hiệu `%` đúng một lần”.

### 15.3. OSR khác compiled method entry

Một OSR nmethod cho bytecode index trong loop **khác** một nmethod cho normal method entry. Có thể quan sát cả hai cho cùng Java method.

## 16. Những sai lệch benchmark cần tránh

### 16.1. Constant folding

Nếu benchmark luôn gọi một phép tính với cùng constant và kết quả không được dùng, JIT có thể **fold** toàn bộ expression thành hằng số hoặc loại đi khi hợp lệ. Lúc đó `-Xmixed` tưởng như nhanh vô lý, nhưng thí nghiệm không còn đo công việc mong muốn.

Demo sử dụng input thay đổi qua `c`, `i` và phép mixing phụ thuộc state trước đó để giảm bẫy này, nhưng vẫn không tạo guarantee “không có tối ưu nào”.

### 16.2. Dead-code elimination

Nếu benchmark tính giá trị không được quan sát:

```java
for (int i = 0; i < 1_000_000; i++) {
    expensiveButPureCalculation(i);
}
```

đây là **snippet minh họa**, method `expensiveButPureCalculation` chưa định nghĩa. Compiler có thể loại bỏ computation nếu kết quả không có tác dụng quan sát được. Dùng result consumption/blackhole đúng, tốt nhất bằng JMH.

### 16.3. Class loading và JIT warm-up

Nếu chỉ đo lần đầu gọi `work`, bạn có thể đo cả interpreter execution và compilation scheduling. Một phép đo steady-state cần warm-up đủ và phương pháp đo thích hợp, không chỉ đặt timer quanh first call.

### 16.4. GC noise

Nếu workload cấp phát nhiều objects, GC pauses có thể xen vào khoảng đo; ta có thể vô tình so sánh GC behavior thay vì engine execution. Demo chủ yếu dùng arithmetic và không tạo mảng lớn trong inner loop, nhằm **giảm chứ không loại trừ** ảnh hưởng GC.

### 16.5. Console I/O

In từng iteration làm I/O áp đảo phép tính, khiến dữ liệu không đại diện hot numeric loop. Demo chỉ in sau timed section.

### 16.6. Clock granularity và measurement overhead

Nếu measured section quá ngắn (gần độ phân giải clock), noise từ `System.nanoTime`/scheduling có thể tương đối lớn. Tăng workload/repetitions đúng mức, hoặc dùng JMH có thiết kế timer/sample tốt hơn.

### 16.7. Biên dịch và chạy đồng thời với tiến trình nặng

IDE indexing, antivirus, JVM khác hoặc CPU thermal throttling có thể ảnh hưởng kết quả. Một giá trị elapsedMs bất thường không nhất thiết do Java optimizer.

### 16.8. Benchmark dựa vào nội dung của GC log

Đừng dùng `-XX:+PrintCompilation` khi đo baseline rồi so với `-Xint` không logging: đó là thay đổi **hai yếu tố cùng lúc** — engine và log I/O.

## 17. Mở rộng: đo cold startup riêng với steady-state

Hai bài toán cần phân biệt:

1. **Cold CLI:** người dùng chạy một lệnh, JVM startup, làm một việc ngắn rồi thoát. `-Xmixed` có thể chưa hưởng lợi nhiều từ JIT vì workload kết thúc trước khi code đủ hot.
2. **Long-lived service:** ứng dụng chạy hàng giờ, xử lý nhiều requests tương tự, profile đủ để JIT compile hot paths. `-Xmixed` có thể có lợi ích lớn hơn so với interpreter-only.

### 17.1. “Thực thi kết hợp” giúp startup vì sao?

Với cold methods, JVM tránh biên dịch chúng trước khi biết chúng đáng tối ưu. C1 có thể compile nhanh hơn C2 trên những hot paths ban đầu, còn C2 được sử dụng sau khi có profile đủ chất lượng.

Do vậy HotSpot tiered compilation cố gắng cân bằng **startup time và peak performance**, khác với quan niệm “compile toàn bộ trước khi chạy”.

### 17.2. Không chuyển trực tiếp kết quả CLI demo sang web service

Một request-based service có:

- JIT profile thay đổi theo traffic.
- Nhiều classes/frameworks/threads.
- GC và allocation pattern.
- Database/network I/O.
- Thread scheduling và container CPU quota.

Nếu chỉ dùng compute demo để kết luận “service sẽ nhanh gấp N lần”, bạn đã bỏ qua những thành phần chi phối end-to-end latency.

## 18. Đọc kết quả như một nhà thực nghiệm

Một báo cáo kết quả đáng tin cần ghi:

| Nội dung | Ví dụ cách ghi |
| --- | --- |
| Hypothesis | “Với numeric loop nóng, mixed JIT có thể giảm measured elapsed time so với interpreter-only” |
| Java/JVM | `java -version` của máy chạy |
| Input | warm-up 800 calls, measured 1500 calls, 1024 steps/call |
| Process isolation | Mỗi run khởi động process Java mới |
| Modes | `-Xint` và `-Xmixed` |
| Correctness | Checksum bằng nhau: `3215795315003` |
| Data collection | Từng elapsedMs, ít nhất vài runs/mode |
| Summary | Median, spread, số runs, outliers |
| Diagnostics | `PrintCompilation` chạy riêng, không trộn baseline |
| Conclusion | Phạm vi kết luận giới hạn trong workload/JVM/host đã đo |

### 18.1. Phải kiểm tra correctness trước khi so tốc độ

Nếu một mode ra checksum khác, ưu tiên điều tra code/VM flags, version và state khác biệt. Đừng coi một lần nhanh hơn mà sai checksum là “optimization thành công”.

### 18.2. Cần báo hiệu ứng bằng tỷ lệ có đơn vị đúng

Nếu cả hai timed sections đo cùng số operations, tỷ lệ *elapsedMs_Xint / elapsedMs_Xmixed* có thể dùng như **speedup quan sát trong mẫu**. Nhưng hãy báo kèm điều kiện thí nghiệm và interval/spread; đừng biến tỷ lệ một lần thành general performance claim.

### 18.3. Cân nhắc CPU quota và thermal effects

Nếu container chỉ có 1 vCPU, compiler threads của `-Xmixed` cạnh tranh CPU với application. Nếu CPU quota khác giữa các runs, thí nghiệm không còn giữ các điều kiện tương đương.

### 18.4. Nếu nhu cầu là so độ nhanh thật, dùng JMH

**OpenJDK JMH — Java Microbenchmark Harness** là công cụ thích hợp cho microbenchmark với warm-up, measurement iterations, forks và blackholes. Demo trong bài giúp quan sát khái niệm và kiểm tra cả correctness, không thay một benchmark tối ưu cho quyết định production.

Tham khảo: https://openjdk.org/projects/code-tools/jmh/

## 19. JMH mở rộng: nên kiểm tra những gì?

Để dùng JMH cho so sánh execution modes, nên:

1. Viết benchmark method trả về một kết quả được JMH tiêu thụ (hoặc dùng `Blackhole`) nhằm tránh DCE.
2. Có `@Warmup` với đủ thời gian/iterations cho môi trường.
3. Có `@Measurement` với đủ runs.
4. Chạy **forks riêng** với `-Xint` và `-Xmixed`.
5. Dùng cùng inputs, JDK build, heap và CPU quota.
6. Ghi rõ **score units** như operations/second hoặc ns/op.
7. Đọc variance và error bars.
8. Kiểm tra JIT compilation profile nếu muốn giải thích nguyên nhân tốc độ.
9. Đừng quên startup và compiler CPU khi đánh giá ứng dụng thực tế.

**Không nhầm `ns/op` của một method riêng với p99 request latency** của toàn hệ thống.

### 19.1. Cẩn trọng với `-Xint` khi warm-up quá dài

Trong interpreter-only, một phép tính có thể chậm hơn đáng kể. JMH với số iterations/measurement time được thiết kế cho JIT mode có thể mất nhiều thời gian nếu dùng interpreter-only. Điều chỉnh benchmark plan để vừa đủ dữ liệu, nhưng **giữ comparable operations và reporting rõ ràng**.

### 19.2. Tại sao chạy hai modes không chỉ là thay một annotation?

Execution mode là **VM option ở thời điểm khởi động process**. Với JMH, nên truyền JVM args phù hợp cho các forks; không cố thay `-Xint` và `-Xmixed` giữa chừng trong cùng một JVM đang chạy.

## 20. Những nhầm lẫn thường gặp

| Nhận định sai | Diễn giải đúng |
| --- | --- |
| “`-Xint` tắt mọi native instruction của JVM.” | Nó tắt JIT cho Java bytecode; runtime/native services vẫn tồn tại. |
| “`-Xmixed` biên dịch mọi method trước main.” | It chọn selective JIT cho hot paths; cold code có thể interpreted. |
| “Chạy cùng checksum nghĩa thời gian phải giống nhau.” | Correctness giống, performance có thể khác. |
| “`-Xint` làm tắt GC.” | GC và heap management vẫn hoạt động. |
| “`-Xmixed` có nghĩa mỗi method luôn vừa interpreted vừa compiled.” | Một method có thể chỉ interpreted, hoặc được compile theo tier/policy. |
| “`-Xcomp` là chế độ production tối ưu nhất.” | Testing mode; có thể tăng startup/compilation cost lớn. |
| “`-XX:-TieredCompilation` giống `-Xint`.” | Tiered off không đồng nghĩa JIT off. |
| “`TieredStopAtLevel=1` là interpreter-only.” | Level 1 dùng C1 compiled code trên HotSpot phù hợp. |
| “PrintCompilation luôn xuất hiện đúng bốn dòng cho demo.” | Compile events phụ thuộc runtime/timing; không deterministic. |
| “Level 4 là thời gian chính xác bốn nanoseconds.” | Đó là compilation tier, không một đơn vị thời gian. |
| “`%` nghĩa CPU utilization percent.” | Trong compilation logs thường là OSR marker. |
| “`@ 20` nghĩa 20 lời gọi method.” | Là bytecode index (BCI) trong OSR entry. |
| “Warm-up 800 calls bảo đảm steady state.” | Không có guarantee đó. |
| “Một lần đo cho speedup phổ quát.” | Chỉ là một mẫu có nhiều biến gây nhiễu. |
| “Thêm `PrintInlining` không ảnh hưởng đo.” | Diagnostic output có overhead/log I/O. |
| “`System.nanoTime` trả thời gian CPU thuần.” | Nó đo elapsed interval, gồm scheduling delays. |
| “Giữ sink volatile thì mọi compiler optimization biến mất.” | Volatile giữ side effects, JIT vẫn tối ưu phần có thể. |
| “Tất cả JIT speedups đến từ method call overhead.” | Inlining, loop optimizations, branch/type profile và nhiều yếu tố khác. |
| “Method được gọi một lần không thể nóng.” | Một loop dài có thể kích hoạt OSR bằng backedge counts. |
| “CLI benchmark đủ để kết luận HTTP server p99.” | Startup, I/O, workload và concurrency rất khác. |

## 21. Bài tập tự kiểm tra có đáp án

**Câu 1.** `-Xint` và `-Xmixed` khác nhau ở điểm chính nào?

**Đáp án:** `-Xint` thực thi Java bytecode interpreted-only, tắt JIT; `-Xmixed` cho phép interpreter và JIT compiled hot methods phối hợp.

**Câu 2.** `-Xint` có tắt GC, native libraries và OS system calls không?

**Đáp án:** Không. Nó tác động execution mode của Java bytecode, không loại bỏ runtime services.

**Câu 3.** Vì sao cùng bytecode chạy ở hai modes phải cho cùng checksum?

**Đáp án:** Java semantics không được đổi bởi việc VM chọn interpreter hay compiler; modes chỉ là cách thực hiện đúng các instructions.

**Câu 4.** Dòng `checksum=3215795315003` có là thời gian đo không?

**Đáp án:** Không. Nó là giá trị logic của workload, dùng kiểm tra correctness.

**Câu 5.** `elapsedMs` có được kỳ vọng giống nhau giữa mọi runs không?

**Đáp án:** Không. Timing phụ thuộc CPU, JIT, GC, scheduling, warm-up và môi trường.

**Câu 6.** Vì sao cần khởi động process riêng cho từng mode?

**Đáp án:** Vì compiled/profile/cache state của một JVM đang chạy không thể reset đơn giản giữa hai chế độ; mode là VM startup option.

**Câu 7.** Warm-up có ích gì cho `-Xmixed`?

**Đáp án:** Tạo opportunity cho class loading/profiling và JIT compile hot code trước measured section; không bảo đảm mọi method đã C2.

**Câu 8.** Warm-up `-Xint` có làm bytecode được C2 compile không?

**Đáp án:** Không, vì mode này tắt JIT compilation cho bytecode.

**Câu 9.** Làm sao quan sát JIT events trên HotSpot?

**Đáp án:** Chạy riêng với `-XX:+PrintCompilation`; tìm class/method của demo và các compilation levels/OSR markers.

**Câu 10.** Nếu `PrintCompilation` in level 3 và 4, điều đó thường biểu thị gì?

**Đáp án:** C1 full-profiling compilation và C2 optimized compilation trong mô hình tiered HotSpot tương ứng.

**Câu 11.** `%` trong log thường có nghĩa gì?

**Đáp án:** OSR compilation cho một điểm bytecode trong loop.

**Câu 12.** Vì sao không đo elapsedMs khi bật hàng nghìn dòng `PrintCompilation`?

**Đáp án:** Logging/I/O làm thay đổi điều kiện thực thi và có thể gây nhiễu latency.

**Câu 13.** `-Xcomp` có nghĩa “mọi method đều level 4” không?

**Đáp án:** Không. Nó ưu tiên compilation như một testing mode nhưng không cam kết cấp tối ưu cụ thể.

**Câu 14.** `-XX:-TieredCompilation` có tắt JIT hoàn toàn không?

**Đáp án:** Không nhất thiết. Nó tắt tiered policy, khác interpreter-only.

**Câu 15.** Một workload có nhiều I/O có chắc `-Xmixed` nhanh hơn `-Xint` nhiều lần không?

**Đáp án:** Không. Nếu thời gian chủ yếu chờ I/O, lợi ích tối ưu bytecode có thể nhỏ so với end-to-end latency.

**Câu 16.** Vì sao code trong `mix` có thể không còn là một native call riêng mỗi iteration?

**Đáp án:** JIT có thể inline `mix` vào vòng lặp của caller.

**Câu 17.** Vì sao dùng `System.nanoTime` thay `System.currentTimeMillis` cho khoảng đo ngắn?

**Đáp án:** `nanoTime` được thiết kế cho đo elapsed durations; `currentTimeMillis` là wall-clock có độ phân giải/điều chỉnh không phù hợp bằng cho microtiming.

**Câu 18.** Tại sao nên báo median/spread thay vì lấy lần nhanh nhất?

**Đáp án:** Giá trị min có thể thiên lệch do may mắn scheduling/cache; distribution giúp hiểu biến động và outliers.

**Câu 19.** Nếu checksum khác giữa modes, có thể kết luận JIT nhanh hơn không?

**Đáp án:** Không. Phải xác minh chương trình/môi trường/correctness trước khi diễn giải performance.

**Câu 20.** Công cụ nào thích hợp hơn demo `nanoTime` tự viết nếu muốn microbenchmark nghiêm túc?

**Đáp án:** OpenJDK JMH, với forks, warm-up, measurement và blackhole.

## 22. Checklist thí nghiệm thực hành

1. Cố định cùng tệp `ExecutionModeDemo.java` và compile một lần bằng `javac --release 17`.
2. Ghi `java -version` và `javac -version`.
3. Dùng `-Xint` và `-Xmixed` ở **hai processes** độc lập.
4. Giữ warm-up calls, measured calls và steps per call bằng nhau.
5. Kiểm tra năm dòng stdout xác định và checksum trước khi đo timing.
6. Ghi `elapsedMs` của từng lần chạy, không lấy một lần làm luật.
7. Lặp nhiều runs và xen kẽ execution mode order.
8. Đo whole-process startup riêng khi đó là mục tiêu.
9. Ghi CPU/container quotas nếu có.
10. Chạy `PrintCompilation` riêng để quan sát interpreter vs C1/C2/OSR.
11. Đừng áp số compile events hay C2 thresholds cố định cho mọi HotSpot.
12. Không gộp `-Xint`, `-Xcomp`, tiered-off vào một khái niệm.
13. Không bật thêm heap/GC/JIT tuning flags khác khi chưa có giả thuyết rõ.
14. Tránh output I/O trong timed computation.
15. Dùng JMH nếu kết quả cần phục vụ quyết định performance production.
16. Đọc profiler/JFR/JIT logs khi muốn giải thích nguyên nhân khác biệt.
17. Giữ code đúng Java semantics; không viết code dựa vào timing race/undefined assumptions.
18. Công bố giới hạn thí nghiệm: CPU, JVM, build, số runs, warm-up, inputs.

### Tổng kết

```text
                  SAME JAVA BYTECODE
                          |
                +---------+----------+
                |                    |
              -Xint               -Xmixed
                |                    |
        Interpreter only    Interpreter + selective JIT
                |                 /        \
         No C1/C2 for       Cold paths    Hot paths
         Java bytecode     interpreted   C1/C2 / OSR
                |                    |
                +----------+---------+
                           |
                 SAME LOGICAL RESULTS
                           |
                Different elapsed time,
                compiler CPU, warm-up
                           |
            Measure multiple isolated runs
            Check correctness before timing
```

**Kết luận cốt lõi:** `-Xint` là đối chứng hữu ích để hiểu chi phí interpreted execution, còn `-Xmixed` cho HotSpot **thông dịch cold code và JIT-biên dịch code nóng khi có lợi**. Một thí nghiệm đúng phải giữ cùng bytecode/input/JVM conditions, phân biệt **stdout logic cố định** với **timing thay đổi**, đo nhiều lần và dùng compiler logs để xác nhận các sự kiện JIT. Tốc độ đo được trên một máy không trở thành lời cam kết của Java.

### Tài liệu tham khảo

- [Oracle JDK 17 — `java` command, các mode `-Xint`, `-Xmixed`, `-Xcomp`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): định nghĩa interpreter-only, mixed (mặc định) và testing compilation mode.
- [OpenJDK — `java` command source documentation](https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md): các option HotSpot với mô tả giải nghĩa.
- [Microsoft OpenJDK Engineering — How Tiered Compilation Works in OpenJDK](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/): C1/C2 profiling, các compilation levels và những cảnh báo về `-Xint`/`-Xcomp`.
- [Oracle — HotSpot Compilation Optimization](https://docs.oracle.com/javacomponents/jrockit-hotspot/migration-guide/comp-opt.htm): interpreter/JIT và tiered compilation dưới góc nhìn runtime.
- [OpenJDK — Compiler configuration/source](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compiler_globals.hpp): những cờ liên quan compiler và tiered policy, phụ thuộc version.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): benchmark có warm-up, forks, instrumentation và thống kê.
- [JVMS `2` — The Structure of the Java Virtual Machine (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html): Java execution semantics không yêu cầu tất cả JVM dùng HotSpot C1/C2.
