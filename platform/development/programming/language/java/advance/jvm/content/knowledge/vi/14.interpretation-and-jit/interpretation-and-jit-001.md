# Thông dịch bytecode và biên dịch lúc chạy (JIT) giải quyết vấn đề gì?

## 1. Bài toán mà JVM phải giải quyết

`javac` thường biên dịch Java source thành **JVM bytecode** trong file `.class`, không phải native machine code gắn cứng với CPU hiện tại. Khi chạy, JVM phải thực hiện các chỉ thị máy ảo ấy trên một nền tảng phần cứng cụ thể.

Có hai cách thực thi bổ sung cho nhau:

- **Thông dịch (interpretation):** một bytecode interpreter trực tiếp xử lý các lệnh JVM. Nó cho phép bắt đầu chạy phương thức mà không nhất thiết phải tạo native code tối ưu cho phương thức đó.
- **Biên dịch lúc chạy (Just-In-Time, JIT):** JVM nhận diện method hoặc loop được thực thi nhiều, rồi có thể chuyển bytecode thành **native machine code** đã tối ưu cho trạng thái runtime/CPU hiện tại.
- **Profiling và adaptive optimization:** JVM quan sát code path, call frequency, loop iterations, receiver types và hành vi thường gặp để tập trung công biên dịch vào vùng hot.
- **Deoptimization:** nếu các giả định dùng khi tối ưu không còn đúng, runtime có thể quay về một execution mode tương thích và bảo toàn Java semantics.

**Mục tiêu chính là cân bằng thời gian bắt đầu chạy, thời gian khởi động/warmup và hiệu năng lâu dài.** Interpreter có chi phí compilation ban đầu thấp, nhưng phải xử lý bytecode lặp lại. JIT tốn tài nguyên để compile, bù lại native code có thể chạy nhanh hơn và được tối ưu liên phương thức.

Đây là mô hình điển hình của **HotSpot**, không phải quy tắc bắt buộc mọi JVM implementation phải có bộ compiler C1/C2 hoặc cùng chính sách JIT.

## 2. Nhìn toàn bộ đường thực thi

~~~text
Java source
  |
  v
javac
  |
  v
Class file: bytecode + constant pool + class metadata
  |
  v
JVM: loading -> verification/linking -> initialization khi cần
  |
  v
Interpreter chạy bytecode
  |        |
  |        +-- theo dõi call counts, loop backedges, type profiles
  |
  +-- cold method -> có thể tiếp tục thông dịch
  |
  +-- hot method/loop -> yêu cầu JIT
                          |
                          v
                     C1/C2 compiler
                          |
                          v
                     Native code trong code cache
                          |
                          v
                     CPU thực thi compiled code
                          |
                          +-- assumptions invalid?
                                 |
                                 v
                          guard/fallback/deoptimization
~~~

**Không đọc sơ đồ như một thứ tự cưỡng bức cho mọi method.** Một phương thức có thể không được biên dịch; một phương thức khác có thể đi qua nhiều tiers; long-running loop có thể chuyển sang native code bằng OSR mà không cần return. Flags `-Xint` và `-Xcomp` cũng làm execution strategy khác.

### Ba dạng mã khác nhau

| Dạng | Ví dụ | Đơn vị thực thi |
| --- | --- | --- |
| Java source | `return a + b;` | Chương trình nguồn, theo Java Language Specification |
| JVM bytecode | `iload_0`, `iload_1`, `iadd`, `ireturn` | JVM instruction set |
| Native machine code | Instructions của x86-64/AArch64 | CPU thực |

**`javac` không đồng nghĩa JIT.** `javac` thường chạy trước khi ứng dụng chạy; JIT là compiler hoạt động trong JVM lúc ứng dụng đang chạy.

## 3. Interpreter thực thi bytecode như thế nào?

Ví dụ Java method:

~~~java
static int add(int a, int b) {
    return a + b;
}
~~~

Đây là **đoạn method minh họa**, chưa phải một file Java độc lập có `main`. `javac` thông dụng tạo bytecode tương tự:

~~~text
0: iload_0
1: iload_1
2: iadd
3: ireturn
~~~

Với `a=4` và `b=9`:

~~~text
locals: [4, 9], operand stack = []
iload_0 -> [4]
iload_1 -> [4, 9]
iadd    -> [13]
ireturn -> đưa 13 về caller
~~~

Ở mức khái niệm, interpreter lặp lại thao tác “lấy bytecode, xác định opcode, thực hiện semantics và cập nhật pc”. Một pseudo-code:

~~~text
while (method is active):
    opcode = readInstruction(pc)
    dispatch(opcode)
    performJVMOperation()
    advancePcAsRequired()
~~~

Đây **không phải nguyên văn mã nguồn HotSpot interpreter**. HotSpot có template interpreter và machine-code stubs được tối ưu; diễn giải “một switch trong C” chỉ là mô hình học ban đầu.

### Interpreter giải quyết vấn đề gì?

1. Chạy những methods lạnh với ít chi phí chuẩn bị/native-code generation.
2. Hỗ trợ chạy sớm trong quá trình startup/class initialization theo các quy tắc JVM.
3. Ghi nhận profiling data để chính sách compilation quyết định khi nào code trở nên hot.
4. Cung cấp đường fallback khi optimized code bị invalidated hoặc phải deoptimize.
5. Duy trì tính linh hoạt khi class loading, type behavior và method call sites thay đổi.

**Chi phí:** các vòng dispatch/bytecode operations lặp đi lặp lại có thể chậm hơn native optimized code, đặc biệt trong hot loops. Tuy nhiên không phải mọi method đều đáng biên dịch: với method chỉ chạy một lần, compilation cost có thể lớn hơn lợi ích.

## 4. JIT giải quyết vấn đề gì?

Thay vì giải mã các lệnh bytecode lặp lại, JIT có thể chuyển một đoạn bytecode đang hot sang native instructions theo pipeline khái niệm:

~~~text
Bytecode + class metadata + runtime profiles
           |
           v
Compiler intermediate representation
           |
           v
Data-flow/control-flow analysis
Inlining, constant folding, guard insertion,
range-check optimization, escape analysis ...
           |
           v
Register allocation + machine-code generation
           |
           v
Native compiled code -> code cache
~~~

Những lợi ích tiềm năng:

- Giảm interpreter dispatch overhead trên đường nóng.
- **Inlining** loại overhead của nhiều lời gọi method nhỏ và mở ra tối ưu xuyên methods.
- **Devirtualization** tận dụng observed receiver types để tối ưu lời gọi ảo có guard/fallback thích hợp.
- **Constant folding, dead-code elimination** và common-subexpression optimizations.
- **Loop optimizations** như hoisting/unrolling khi an toàn.
- **Range-check elimination** khi chứng minh bounds hợp lệ.
- **Escape analysis/scalar replacement** khi một object không cần materialize thành heap object thực.

**JIT không được vi phạm Java semantics.** Các null/bounds/access checks cần thiết vẫn phải được bảo toàn; `int` overflow, exception paths, Java Memory Model, class loading, dynamic dispatch và GC reachability đều có những ràng buộc đúng đắn.

Một đoạn được JIT compile không bảo đảm chạy nhanh hơn mọi trường hợp: overhead của guards, code size, cache locality và dữ liệu runtime có thể khiến lợi ích thay đổi.

## 5. Hotness: method nóng và loop nóng

HotSpot thường dùng nhiều thông tin để quyết định compile:

- **Invocation count:** method được gọi nhiều lần.
- **Backedge count:** vòng lặp lặp lại nhiều lần, đi qua backward branch trong bytecode.
- **Type profiles:** loại receiver xuất hiện tại call sites, hỗ trợ inlining/devirtualization.
- **Branch behavior:** các đường nóng/lạnh và xác suất thực tế.
- **Compiler queues, code cache, tier, runtime workload:** chọn việc compile nào mang lại hiệu quả.

Một loop chạy lâu có thể làm method trở nên hot **dù method chỉ được gọi một lần**.

~~~java
static long countUp(int limit) {
    long sum = 0;
    for (int i = 0; i < limit; i++) {
        sum += i;
    }
    return sum;
}
~~~

Đây là đoạn method minh họa. Gọi `countUp(1_000_000)` một lần có thể đủ làm loop hot tùy JVM/settings, nhưng **không có lời hứa** “đúng 1.000.000 vòng thì JIT chắc chắn compile”.

**Đừng dùng con số thần kỳ** như “mọi method compile sau đúng 10.000 calls”. Thresholds và decisions thay đổi theo tiered policy, backedges, code characteristics, JVM flags và version. Flag `-XX:CompileThresholdScaling` của HotSpot có thể ảnh hưởng thresholds, nhưng không biến quá trình này thành một phép đếm đồng nhất.

## 6. Tiered Compilation: vì sao cần C1 và C2?

HotSpot thông dụng có **tiered compilation**, tận dụng interpreter và nhiều compiler tiers để cân bằng startup, profiling overhead và peak throughput.

| Tier thường gặp | Engine | Vai trò |
| --- | --- | --- |
| Level 0 | Interpreter | Bytecode execution; có thể thu thập profile |
| Level 1 | C1 | Compiled code với ít/không có profiling |
| Level 2 | C1 | Compiled code với limited profiling |
| Level 3 | C1 | Compiled code thu thập profiling đầy đủ hơn |
| Level 4 | C2 | Optimized compiled code dựa trên profile |

Level numbers là **chi tiết của HotSpot tiered policy**, không được JVMS quy định. Một số builds/configurations dùng compiler khác hoặc chỉ một phần tiers.

**C1 và C2 đều là JIT compilers.** C1 ưu tiên tốc độ biên dịch và hỗ trợ profiling phù hợp; C2 đầu tư tối ưu mạnh hơn cho hot code có đủ dữ liệu.

Không mặc định mọi method đều đi **0→1→2→3→4**. Một số methods chỉ interpreted, một số được C1 compile, một số lên C2, một số được OSR, hoặc bị deopt/recompiled. Chính sách chọn đường phụ thuộc đặc tính workload.

### Vì sao không compile hết bằng C2 ngay lúc startup?

Compilation tiêu tốn CPU, code-cache/native memory và thời gian. Một chương trình có thể load hàng nghìn methods nhưng chỉ sử dụng tỷ lệ nhỏ thường xuyên. **Adaptive optimization** giúp HotSpot chỉ đầu tư vào nơi có khả năng hoàn vốn. C2 compile sớm mà chưa có runtime profile có thể bỏ lỡ thông tin quan trọng để tối ưu.

## 7. OSR: chuyển vào compiled code ngay giữa vòng lặp

**On-Stack Replacement (OSR)** cho phép JVM chuyển trạng thái của **method đang thực thi** từ interpreter (hoặc compiled tier phù hợp) sang OSR compiled code tại điểm bytecode thích hợp.

~~~text
Một lần gọi method có loop rất dài
     |
     v
Interpreter thực thi vài vòng đầu
     |
     v
Loop backedge counter làm method/loop trở nên hot
     |
     v
JIT tạo OSR entry phù hợp
     |
     v
Runtime chuyển execution state tới OSR compiled entry
     |
     v
Các vòng sau có thể chạy native code
~~~

**OSR khác compilation từ method entry:** entry thông thường phục vụ lần gọi bắt đầu method; OSR entry phải thích nghi trạng thái locals/operand stack tại một loop BCI khi method đã chạy dở.

OSR **không bắt buộc** xảy ra với mọi loop. Nếu quá ít iterations, compilation chưa kịp, VM bật interpreter-only hoặc JIT policy không chọn, method có thể hoàn toàn chạy interpreted.

## 8. Speculative optimization và deoptimization

JIT có thể thấy một call site gần như chỉ gọi một implementation của interface. Nó có thể tối ưu đường phổ biến nhờ inlining cùng một **type guard**. Nếu về sau runtime gặp implementation mới, guard có thể thất bại.

~~~text
Profile: receiver type thường là AddOne
         |
         v
Compiled hot path có type guard
         |
         +-- AddOne -> fast inlined behavior
         |
         +-- Other type -> generic path hoặc deoptimization
                               |
                               v
                         correct Java behavior
~~~

**Deoptimization** giúp HotSpot khôi phục/di chuyển một compiled execution state về dạng tương thích để tiếp tục chạy theo Java semantics, khi speculative assumptions không còn phù hợp.

- Deoptimization không tự động là Java exception.
- Không phải cứ receiver type mới thì deoptimization **chắc chắn** xảy ra: compiled code có thể đã có generic fallback hoặc polymorphic inline cache.
- JVM có thể cập nhật profile rồi recompile code phù hợp hơn.
- Dynamic class loading và dynamic dispatch khiến cơ chế này đặc biệt quan trọng.

**Sai lầm thường gặp:** nói “C2 đoán type nên có thể trả kết quả sai”. Runtime guards và deoptimization tồn tại chính để giữ correctness ngay cả khi giả định bị bác bỏ.

## 9. Runnable Java 17+: cùng kết quả ở chế độ interpreter/JIT

Tạo file **`InterpreterJitDemo.java`**:

~~~java
public class InterpreterJitDemo {
    private static volatile long published;

    static int transform(int x) {
        return x * 3 + 1;
    }

    static long sumTransformed(int limit) {
        long total = 0;
        for (int i = 0; i < limit; i++) {
            total += transform(i);
        }
        return total;
    }

    public static void main(String[] args) {
        published = sumTransformed(100_000);
        System.out.println("sum=" + published);
        System.out.println("example=" + transform(7));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -g InterpreterJitDemo.java
java InterpreterJitDemo
~~~

**Stdout chính xác khi chương trình hoàn tất bình thường (không mở compilation diagnostics):**

~~~text
sum=14999950000
example=22
~~~

Vì:

~~~text
transform(i) = 3*i + 1
sum(i=0..99999) = 3*(99999*100000/2)+100000
                 = 14,999,950,000
transform(7) = 3*7+1 = 22
~~~

`total` là `long` nên tổng không bị overflow trong bài này; với `0 <= i < 100000`, `transform(i)` cũng nằm trong miền `int`.

### Thử ba JVM modes

Trên HotSpot hỗ trợ flags:

~~~bash
java -Xint InterpreterJitDemo
java -Xmixed InterpreterJitDemo
java -Xcomp InterpreterJitDemo
~~~

| Mode | Công dụng |
| --- | --- |
| `-Xint` | Interpreter-only: không JIT compile thành native methods |
| `-Xmixed` | Interpreter kết hợp JIT cho hot code |
| `-Xcomp` | Testing mode ưu tiên compilation; không được Oracle khuyến nghị dùng production |

**Java semantics và hai dòng kết quả phải giống nhau** trong các lần chạy thành công. Thời gian chạy, compilation events và GC logs có thể khác. Với chương trình ngắn, không được kết luận chỉ từ stdout rằng method `sumTransformed` đã OSR hay C2 compile.

**Điều ví dụ chứng minh:** cách thực thi có thể khác nhưng kết quả logic Java giữ nguyên. **Không chứng minh:** compiler nào chắc chắn được chọn hoặc throughput cải thiện bao nhiêu lần.

### Xem bytecode bằng javap

~~~bash
javap -c -p InterpreterJitDemo
javap -v -p InterpreterJitDemo
~~~

Những thứ cần tìm:

- `transform` có arithmetic bytecodes tương ứng.
- `sumTransformed` có loop và branch backward.
- `main` có method invocation và output code.

`javap` hiển thị **JVM bytecode trong class file**, **không phải native machine code JIT đã phát sinh**. Vì vậy thấy `invokestatic` ở output `javap` không chứng minh JIT sẽ luôn giữ nguyên call instruction sau inlining.

## 10. Runnable Java 17+: một call site với hai receiver types

Tạo file **`ReceiverProfileDemo.java`**:

~~~java
public class ReceiverProfileDemo {
    interface Operation {
        int apply(int n);
    }

    static final class AddOne implements Operation {
        public int apply(int n) {
            return n + 1;
        }
    }

    static final class DoubleIt implements Operation {
        public int apply(int n) {
            return n * 2;
        }
    }

    static int invoke(Operation op, int n) {
        return op.apply(n);
    }

    public static void main(String[] args) {
        Operation common = new AddOne();
        Operation other = new DoubleIt();

        long sum = 0;
        for (int i = 0; i < 20_000; i++) {
            sum += invoke(common, 3);
        }

        System.out.println("common-sum=" + sum);
        System.out.println("other-receiver=" + invoke(other, 3));
    }
}
~~~

~~~bash
javac ReceiverProfileDemo.java
java ReceiverProfileDemo
~~~

**Stdout:**

~~~text
common-sum=80000
other-receiver=6
~~~

20.000 calls với `AddOne.apply(3)` trả 4 cho tổng 80.000; lần gọi `DoubleIt.apply(3)` trả 6. JIT có thể quan sát receiver type của các calls trước đó và tối ưu common path, nhưng **hai dòng này không chứng minh deoptimization đã xảy ra**. Runtime có thể chưa compile method, hoặc compiled code xử lý polymorphism/fallback.

## 11. Quan sát compiler bằng HotSpot logs

Oracle JDK 25 hướng dẫn các flags:

~~~bash
java -XX:+PrintCompilation InterpreterJitDemo
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining -XX:+PrintCompilation InterpreterJitDemo
~~~

Mở diagnostics sẽ khiến output toàn JVM **có thêm dòng log**. Vì thế hai dòng stdout ở phần 9 là **output của chương trình không bật diagnostics**, không phải toàn bộ output khi thêm flags ở đây.

`PrintCompilation` có thể cho biết:

- Compile task id và tên method.
- Compiler tier, OSR BCI trong những trường hợp được biểu diễn.
- Thời điểm VM ghi compilation event.
- Method trở nên non-entrant hoặc code bị thay thế theo lifecycle.

Một **dòng giả định để đọc định dạng**, không phải output chính xác của lần chạy:

~~~text
  94   67 %  3   InterpreterJitDemo::sumTransformed @ 4 (25 bytes)
~~~

Ký hiệu `%` thường gắn với OSR entry trong format HotSpot; các số chỉ là ví dụ. Không giả định cùng ID, tier, BCI hoặc order trên mọi JDK/máy.

`PrintInlining` có thể giải thích method nào được inlined hoặc bị từ chối do code size, profile, hotness, compiler budget. Nếu `transform` được inline vào caller, một invocation riêng có thể không còn ở optimized machine code nhưng source semantics vẫn được giữ.

**`-Xcomp` là testing mode**, có thể tăng compilation overhead và làm startup chậm. **`-Xint`** là công cụ useful để cô lập sự ảnh hưởng của JIT trong chẩn đoán, không phải cách làm production nhanh nhất.

## 12. Code Cache và chi phí của native compilation

Compiled machine code cần memory để tồn tại. HotSpot dùng **Code Cache** để lưu compiled methods cùng các code artifacts của JVM. Đây **không phải Java heap chứa POJO objects**.

| Tùy chọn | Mục đích |
| --- | --- |
| `-XX:ReservedCodeCacheSize=...` | Giới hạn code cache theo implementation |
| `-XX:+SegmentedCodeCache` | Chia code cache thành những segments khi phù hợp |
| `-XX:-TieredCompilation` | Vô hiệu hóa tiered policy của HotSpot |
| `-XX:CompileThresholdScaling=...` | Scale compilation thresholds |
| `-XX:+PrintCompilation` | In compiler events |
| `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` | In decision inlining |

Compiler sử dụng CPU threads, queues và một lượng memory cho intermediate representation; compiled code còn chiếm Code Cache và có thể ảnh hưởng instruction cache. Khi cache chật, runtime có thể phải reclaim compiled nmethods hoặc hạn chế compiling. Vì vậy “JIT compile mọi bytecode ngay lập tức” không phải cách miễn phí để tăng hiệu năng.

## 13. Interpreter/JIT không làm thay đổi ngữ nghĩa JVM

Đây là một invariant quan trọng:

- `new` vẫn phải cung cấp object identity đúng.
- `getfield`, `putfield`, `invokestatic`, `invokevirtual` phải đáp ứng đúng linking, access và dispatch rules.
- `NullPointerException`/`ArrayIndexOutOfBoundsException` xảy ra khi Java semantics yêu cầu; JIT chỉ được bỏ kiểm tra sau khi chứng minh an toàn hoặc chèn guard tương đương.
- `synchronized`/`volatile` và các quy tắc happens-before phải được bảo toàn.
- GC phải nhận diện references còn live ngay cả trong compiled frames.
- Dynamic class loading và interface polymorphism phải giữ behavior nhất quán.

JIT **có thể hợp nhất, sắp xếp lại hoặc loại những thao tác không quan sát được** khi an toàn, nhưng không được thay đổi observable program behavior được spec bảo vệ.

**Deoptimization là phần của lời giải correctness**, không phải lời thú nhận JIT “đoán rồi trả bừa”. Assumptions có guard và fallback đúng đắn.

## 14. Cách đo hiệu năng JIT mà không mắc bẫy benchmark

Một đo đạc kiểu:

~~~java
long start = System.nanoTime();
long answer = sumTransformed(100_000);
long duration = System.nanoTime() - start;
System.out.println(duration);
~~~

Đây chỉ là **đoạn minh họa cần đặt trong class có method `sumTransformed`**, không phải benchmark đáng tin tự thân.

Các sai số thường gặp:

1. **Startup và class loading** chi phối một chương trình quá ngắn.
2. **JIT warmup** chưa hoàn tất; compile jobs có thể đang chạy đồng thời.
3. **Dead-code elimination:** nếu kết quả không được sử dụng, optimizer có thể xóa công việc.
4. **Constant folding:** input cố định có thể được đơn giản hóa nhiều hơn workload thật.
5. **GC/scheduling/CPU frequency** tạo nhiễu.
6. **Compilation tiers/OSR** đổi giữa các iterations.
7. **Diagnostic logging** tăng overhead đo lường.
8. **Đo một lần** không đủ thông tin về phân bố latency.

**Quy trình phù hợp:** dùng JMH cho microbenchmarks với warmup, forks, measurement iterations, sink/Blackhole và profiler phù hợp. Nếu mục tiêu là server, xem startup, first-request latency, steady-state throughput, P95/P99, CPU và memory trên workload đại diện. Đừng tuyên bố “JIT nhanh hơn chính xác N lần” từ ví dụ số cộng.

## 15. Khi nào Interpreter quan trọng, khi nào JIT quan trọng?

| Tình huống | Diễn giải |
| --- | --- |
| CLI chỉ chạy một task nhỏ rồi thoát | Compilation cost có thể không hoàn vốn; startup có vai trò lớn |
| Server chạy lâu với vài hot handlers | JIT có thể tối ưu hiệu quả, cải thiện throughput sau warmup |
| Ứng dụng có rất nhiều code paths hiếm | Interpreter giữ đường chạy cho cold code mà không compile mọi thứ |
| Method có loop lặp nhiều nhưng chỉ gọi một lần | OSR có thể giúp chuyển hot loop sang compiled code |
| Call site chủ yếu thấy một receiver type | JIT có thể guarded-inline đường thường gặp |
| Runtime nạp implementation mới | Guard/fallback/deopt giúp giữ semantics |
| Code Cache hoặc compiler CPU hạn chế | Biên dịch quá nhiều có chi phí, cần quan sát runtime |
| Lỗi chỉ thấy khi bật JIT | Có thể so `-Xint` để chẩn đoán; không mặc định lỗi do JIT trước khi có chứng cứ |

Một service “chạy nhanh sau 30 giây” **chưa chắc hoàn toàn do JIT**: caches, network/database connections, JIT, class initialization và GC có thể đều tham gia. Cần công cụ đo để xác định.

## 16. Các hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`javac` sinh machine code cho CPU hiện tại.” | `javac` thường sinh JVM bytecode. |
| “Interpreter thực thi source Java từng dòng.” | Nó thực thi bytecode JVM. |
| “Java chỉ interpreted, không native.” | HotSpot thường kết hợp interpreter với JIT. |
| “JIT compile toàn bộ classpath lúc startup.” | HotSpot dùng adaptive profiling/policy; nhiều cold methods không compile. |
| “Hot method = được gọi đúng 10.000 lần.” | Invocation/backedge counts, tiers, policies và runtime state chi phối. |
| “Method gọi đúng một lần không thể được JIT.” | Long loop có thể dùng OSR. |
| “C1 là interpreter, C2 mới là JIT.” | C1 và C2 đều là JIT compilers. |
| “Tiered luôn buộc method qua tất cả levels 0 đến 4.” | Có nhiều đường transitions/skip tiers. |
| “JIT tối ưu bằng cách bỏ hết null/bounds checks bất chấp dữ liệu.” | Chỉ được tối ưu nếu giữ đúng semantics/guards. |
| “JIT compile một method rồi code luôn bất biến.” | Có recompile/invalidation/deoptimization. |
| “Deoptimization là exception Java.” | Đây là cơ chế runtime để bảo toàn thực thi. |
| “OSR là khi method gọi lại từ đầu.” | OSR có thể chuyển method đang chạy tại loop BCI. |
| “`javap -c` cho thấy native machine code.” | Nó cho biết JVM bytecode class file. |
| “`-Xint` tắt GC.” | `-Xint` vô hiệu JIT, GC vẫn cần hoạt động. |
| “`-Xcomp` luôn nhanh hơn mixed mode.” | Testing mode có overhead/thiếu profile; không phải mặc định production. |
| “Code Cache chính là Java heap.” | Code Cache lưu compiled code, khác Java object heap. |
| “PrintCompilation ID/tier luôn giống nhau giữa mọi runs.” | Events phụ thuộc VM settings/runtime. |
| “Một benchmark chạy một lần đủ chứng minh peak throughput.” | Cần warmup, forks, đo noise và JIT state. |
| “JIT làm Java không còn portable.” | Bytecode portable trong phạm vi Java platform; native compilation do runtime thích nghi CPU. |
| “AOT và JIT là cùng một thứ.” | AOT biên dịch/chuẩn bị trước; JIT compile lúc chạy. |

## 17. Tự kiểm tra có đáp án

**1.** `javac` thường tạo gì?  
**Đáp án:** Java class file chứa JVM bytecode và metadata; không phải native CPU instructions cho mọi nền tảng.

**2.** Interpreter giải quyết nhu cầu gì?  
**Đáp án:** Cho phép thực thi bytecode với chi phí compilation ban đầu thấp, hữu ích cho cold code/startup và profiling.

**3.** JIT mang lại lợi ích gì?  
**Đáp án:** Tạo native compiled code cho hot code, tối ưu dựa trên runtime profile và giảm execution overhead.

**4.** Vì sao compiler không tối ưu toàn bộ methods ngay?  
**Đáp án:** Compilation tiêu tốn CPU/memory/code-cache; nhiều methods không chạy đủ để hoàn vốn.

**5.** Hai tín hiệu hotness phổ biến là gì?  
**Đáp án:** Method invocation counts và loop backedge counts, ngoài type/branch profiles.

**6.** Level 3 và Level 4 khác nhau thế nào trong HotSpot tiered mode thông dụng?  
**Đáp án:** Level 3 thường là C1 với profiling đầy đủ hơn; Level 4 thường là C2 optimized code.

**7.** Một loop rất dài có thể dùng JIT dù chỉ gọi method một lần không?  
**Đáp án:** Có thể, qua OSR nếu runtime chọn/biên dịch kịp.

**8.** Receiver type mới nhất thiết gây Java exception?  
**Đáp án:** Không. Generic dispatch, guards và deoptimization vẫn phải cho Java behavior đúng.

**9.** Vì sao chương trình InterpreterJitDemo luôn in cùng kết quả với `-Xint` và `-Xmixed`?  
**Đáp án:** Execution strategies khác nhưng phải giữ cùng Java semantics.

**10.** Để xem compiler đang compile methods nào trên HotSpot, dùng gì?  
**Đáp án:** Thử `-XX:+PrintCompilation`, lưu ý diagnostic output không cố định.

**11.** `javap` đủ chứng minh một method được inline lúc runtime?  
**Đáp án:** Không, nó hiển thị bytecode, không phải optimized machine code.

**12.** JIT có thể ảnh hưởng startup latency không?  
**Đáp án:** Có. Compilation/profiling có overhead; tiered policy cân bằng startup và throughput.

**13.** Có nên dùng `-Xcomp` trong production vì “compile là luôn tốt”?  
**Đáp án:** Không. Oracle đánh dấu testing mode; cần đo workload thực.

**14.** Deoptimization có nhiệm vụ gì?  
**Đáp án:** Giữ execution đúng khi assumptions cho optimized code không còn thỏa, có thể fallback/recompile.

## 18. Nguồn chính thức

- [Oracle Java SE 25 — Java Virtual Machine Guide](https://docs.oracle.com/en/java/javase/25/vm/index.html): JVM/HotSpot runtime, tiered compilation và performance.
- [Oracle JDK 25 — java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Xint`, `-Xmixed`, `-Xcomp`, `PrintCompilation`, `PrintInlining`, `TieredCompilation`, `CompileThresholdScaling` và Code Cache options.
- [Oracle HotSpot Performance Enhancements](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html): tiered compilation, escape analysis và optimization.
- [Oracle — Java HotSpot Performance Engine Architecture](https://www.oracle.com/java/technologies/whitepaper.html): adaptive optimization, hot-spot detection và deoptimization; whitepaper là tài liệu kiến trúc lịch sử, không cam kết chính sách mỗi bản JVM giống hệt.
- [OpenJDK HotSpot — compilationPolicy.hpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.hpp): compiler tiers và policy implementation; nhánh master có thể khác bản đang dùng.
- [JVMS Java SE 25 — `2.11` Instruction Set Summary](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.11): khái niệm bytecode instructions.
- [JVMS Java SE 25 — Chapter 6 Instruction Set](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html): semantics của `iadd`, `invokevirtual`, `ireturn` và những bytecodes khác.
- [JDK 25 — javap](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): xem bytecode/constant pool từ class file.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): benchmarking JVM đáng tin hơn một lần `nanoTime`.
- [Microsoft Java Developers — Tiered Compilation in OpenJDK](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/): cách đọc C1/C2, profiling và compilation logs; đối chiếu cùng Oracle/OpenJDK khi cần xác nhận version.

**Kết luận:** Interpreter cho phép JVM **thực thi bytecode sớm và rẻ về compilation**; JIT **đầu tư sinh native code tối ưu cho các đoạn hot** để tăng hiệu năng khi chạy lâu. Tiered compilation, runtime profiling, OSR, deoptimization và Code Cache là các thành phần giúp HotSpot cân bằng **startup, warmup, throughput, latency, CPU/memory overhead** trong khi luôn phải bảo toàn Java semantics.