# Thu thập hồ sơ thực thi từ số lần gọi, vòng lặp và kiểu đối tượng

## 1. Tại sao HotSpot phải quan sát chương trình khi đang chạy?

Một file Java `.class` chứa bytecode có thể kiểm tra được về mặt cú pháp và kiểu dữ liệu, nhưng nó **không nói trước** method nào sẽ được gọi hàng triệu lần, vòng lặp nào chạy rất lâu, nhánh nào thường xuyên được đi qua hoặc một lời gọi interface thực tế thường nhận object thuộc class nào.

HotSpot sử dụng **execution profiling** để thu thập một phần hành vi thực thi, từ đó quyết định **mã nào đáng JIT compile** và **các compiler nên tối ưu theo giả định nào**. Ba nhóm dữ liệu quan trọng:

- **Invocation counters**: tín hiệu về số lần method được gọi, phục vụ đánh giá method hotness.
- **Backedge/loop counters**: tín hiệu về hoạt động lặp trong bytecode; giúp phát hiện method chỉ được gọi một lần nhưng có vòng lặp hàng triệu iterations, phục vụ **On-Stack Replacement (OSR)**.
- **Type profiles**: thống kê các kiểu receiver thực sự gặp tại những bytecode call sites hoặc những vị trí profiling tương ứng; hỗ trợ suy đoán kiểu, **devirtualization**, **inlining** và điều phối những đường chạy hiếm.

HotSpot cũng có thể thu thập **branch frequencies**, **type-check feedback**, information về **uncommon traps** và những dữ liệu nội bộ khác; tuy nhiên trọng tâm bài này là lời gọi, vòng lặp và kiểu object.

Bài sử dụng **HotSpot/OpenJDK Java 17**, interpreter, **C1**, **C2** và tiered compilation. Tên metadata, counters, thresholds và compilation levels dưới đây là **implementation details của HotSpot** chứ không phải hợp đồng của Java Language Specification (JLS) hay Java Virtual Machine Specification (JVMS). Một JVM tương thích khác có thể tối ưu khác nhưng vẫn phải bảo toàn kết quả Java.

**Phân biệt ngay:** “profile” là thông tin cho runtime đưa ra quyết định, không phải bằng chứng chắc chắn rằng một method đã được inline, một object đã đổi loại, hoặc Java method hiện có một số lời gọi chính xác bằng số counter hiển thị trong cấu trúc nội bộ.

## 2. Từ bytecode tới mã máy: bức tranh tổng thể

```text
.java
  |
  | javac
  v
.class (bytecode)
  |
  | class loading / verification / linking
  v
Interpreter + counters/profile instrumentation
  |
  | hotness, branch and receiver feedback
  v
Tiered compilation policy
  |
  +--> C1: compiled code sớm, profiling tùy tier
  |
  +--> C2: optimization sâu dựa trên static + dynamic facts
           |
           v
       compiled machine code
           |
           | assumptions/guards
           v
    Nếu giả định không còn đúng:
      fallback / deoptimization / reprofile / recompile
```

Các bước có thể chồng lấn về thời gian:

1. Application thread đang chạy bytecode trong interpreter hoặc nmethod đã compiled.
2. JVM cập nhật counters hoặc profile records tùy mức execution.
3. Compilation policy quyết định enqueue một compile task.
4. Một **compiler thread** (khác application thread) có thể xử lý task từ compile queue.
5. Khi compiled code hợp lệ, VM có thể cho những lần gọi sau sử dụng compiled entry, hoặc đang chạy trong loop thì có thể dùng OSR entry.
6. Một method có thể được compile nhiều lần, với các compilation levels và giả định khác nhau.

Không thể dựa vào tên method “hot” rồi khẳng định **luôn** có C2 code sau một số lần gọi cố định. Thời điểm biên dịch còn phụ thuộc compile queue load, profile maturity, flags, code cache, compiler availability và JVM build.

## 3. Invocation counter: biết method được gọi nhiều lần

Xét method:

```java
static int twice(int value) {
    return value * 2;
}

static long applyManyTimes() {
    long total = 0;
    for (int i = 0; i < 100_000; i++) {
        total += twice(i % 10);
    }
    return total;
}
```

Đây là **hai method fragments**, chưa phải file biên dịch độc lập. Trong mô hình này, `twice` được gọi nhiều lần từ một vòng lặp. HotSpot có thể quan sát những lời gọi để tăng **invocation counter** hoặc cập nhật tín hiệu sử dụng method phù hợp với compilation tier.

### Counter giúp JVM quyết định điều gì?

- Method có đủ “hot” để compiler đầu tư thời gian hay không?
- Nên chuyển từ interpreter sang C1 ở mức profiling nào?
- Khi nào dữ liệu đã đủ và hiệu quả dự kiến biện minh cho C2 compilation?
- Một method có khả năng trở nên cold hoặc chưa có ích để tiếp tục enqueue compile request không?

**Invocation count không phải CPU profiler.** Một getter rất ngắn được gọi nhiều lần có thể ít tốn thời gian hơn một method chỉ chạy một lần nhưng duyệt hàng triệu elements. Một code path đã được inline có thể không có số máy-level function calls bằng số lời gọi viết trong Java source.

### Những giới hạn của bộ đếm

Các counters của HotSpot là **VM-internal**, không phải `long invocationCount` đặt trong mỗi Java object. Chúng có thể được đọc/điều chỉnh bởi tiered compilation policy và cập nhật khác nhau tùy execution engine. Không có API Java SE quy định một threshold như “gọi đúng 10.000 lần thì chắc chắn thành C2”; những ngưỡng/tần suất notifications có thể thay đổi theo runtime state và JDK update.

Không dùng `AtomicLong` trong application để giả làm số raw JVM invocation counter. Nó là **business instrumentation**, có overhead và semantics riêng; JIT có thể inline calls hoặc tối ưu code nhưng bộ đếm nghiệp vụ phải phản ánh những thao tác mà ứng dụng yêu cầu.

## 4. Backedge counter: một lời gọi vẫn có thể là điểm rất nóng

Một method có thể được gọi một lần nhưng bên trong có vòng lặp dài:

```java
static long accumulate(int n) {
    long total = 0;
    for (int i = 0; i < n; i++) {
        total += i;
    }
    return total;
}
```

Đây cũng là **method fragment**. Về bytecode, một compiler Java thông thường tạo một phép kiểm tra điều kiện và một nhánh quay về bytecode offset (BCI) thấp hơn — gọi là **backward branch/backedge**.

```text
BCI 0:   init i = 0
BCI 4:   check i < n      <--- loop header
BCI 9:   body total += i
BCI 18:  increment i
BCI 21:  goto BCI 4       <--- backedge
```

Các BCIs và instruction descriptions trong sơ đồ là **minh họa**, không phải nguyên văn `javap`. Nội dung bytecode thực có thể khác tùy compiler.

HotSpot có thể dựa vào **backedge notifications/counters** để phát hiện vòng lặp chiếm nhiều thời gian, ngay cả khi invocation counter không cao.

### “Backedge count = số vòng lặp” có phải luôn đúng?

Không. Nó phụ thuộc control-flow graph của bytecode và vị trí branches. Một `for` source có thể biến thành nhiều bytecode edges; nested loops có nhiều backedges; JIT có thể **unroll**, **peel**, **vectorize**, **eliminate** hoặc biến đổi loops khi sinh machine code. Vì vậy không đọc backedge count như một API đếm source iterations chính xác cho mọi tình huống.

## 5. On-Stack Replacement (OSR): JIT khi loop vẫn đang chạy

**OSR** giúp JVM đổi từ interpretation/compiled representation hiện tại sang một compiled entry cho **một vị trí trong method**, thông thường tại loop backedge, **ngay khi method invocation ấy vẫn chưa kết thúc**.

```text
Method longTask() được gọi một lần
    |
    v
Interpreter bắt đầu loop
    |
    | số lần qua backedge tăng
    v
Runtime yêu cầu OSR compilation tại BCI của loop
    |
    | compiler thread chuẩn bị machine code
    v
Application chuyển sang OSR entry khi điều kiện cho phép
    |
    v
Tiếp tục loop đã compiled -> return method
```

Nếu không có OSR, một method có vòng lặp dài có thể phải đợi tới **lần gọi thứ hai** mới dùng compiled entry, điều không có lợi cho batch job chỉ gọi một lần. OSR là một cách giảm sự hạn chế này.

**OSR khác normal compilation:**

| Normal entry compilation | OSR compilation |
| --- | --- |
| Entry thường dùng khi invocation bắt đầu tại đầu method | Entry dùng để tiếp tục ở một BCI thuộc invocation đang chạy |
| Thường liên quan invocation hotness | Thường liên quan loop/backedge hotness |
| Có thể áp dụng cho những lời gọi tiếp theo | Có thể giúp một lời gọi rất dài đang diễn ra |
| Một compiled version có entry tại đầu method | Có thể có nmethod/entry chuyên cho BCI của loop |

Đừng cho rằng OSR chắc chắn xuất hiện trong **mọi** loop dài. JVM có thể compile trước khi loop chạy, code có thể được tối ưu rất mạnh, hoặc compile policy/thresholds không chọn OSR trong lần thử nghiệm cụ thể.

## 6. Java 17 chạy được: quan sát vòng lặp dài

Tạo **`BackedgeOsrDemo.java`**:

```java
public class BackedgeOsrDemo {
    static volatile long observed;

    static long calculate(int n) {
        long sum = 0;
        for (int i = 0; i < n; i++) {
            sum += (i & 7);
        }
        return sum;
    }

    public static void main(String[] args) {
        observed = calculate(8_000_000);
        System.out.println("iterations=8000000");
        System.out.println("sum=" + observed);
    }
}
```

```bash
javac --release 17 BackedgeOsrDemo.java
java BackedgeOsrDemo
```

**Stdout xác định của chính chương trình:**

```text
iterations=8000000
sum=28000000
```

Vì mỗi nhóm 8 giá trị `(i & 7)` là `0 + 1 + ... + 7 = 28`, có 1.000.000 nhóm nên tổng bằng 28.000.000.

Để nhìn compiler events trên HotSpot:

```bash
java -XX:+PrintCompilation BackedgeOsrDemo
```

**Không có stdout compiler cố định:** log có thể chứa nhiều methods thuộc JDK, các compilation levels khác nhau hoặc không thấy OSR đúng cách bạn kỳ vọng. Ký hiệu `%` thường liên quan OSR trong `PrintCompilation` của HotSpot và một đoạn `@ BCI` thể hiện điểm bắt đầu; phải đọc compiler log thực tế, không dùng kết quả hai dòng `System.out` làm bằng chứng OSR đã xảy ra.

### Dùng javap để tìm backedge

```bash
javap -c -p BackedgeOsrDemo
```

`javap -c` hiện offsets và bytecode instructions. Tìm conditional branch và jump quay về BCI trước để hiểu vòng lặp của bytecode. Đây không phải disassembler mã máy C2; JIT có thể tối ưu machine loop khác với cấu trúc trong `.class`.

## 7. Tiered compilation: C1, C2 và các mức profiling

HotSpot Java 17 thường sử dụng các **compilation levels 0–4**:

| Level | Execution engine | Mục tiêu phổ biến |
| --- | --- | --- |
| **0** | Interpreter | Thực thi bytecode, có thể cập nhật counters/profiling |
| **1** | C1 optimized code, không full profiling | Native code sớm khi profiling sâu không cần thiết |
| **2** | C1 với limited profiling | Invocation/backedge counting và thông tin hotness hạn chế |
| **3** | C1 với fuller profiling | Đóng góp MethodData/receiver, branch profiles để C2 dùng |
| **4** | C2 | Optimized native code sâu dựa trên static information và profile feedback |

Một đường thường gặp là `0 → 3 → 4`, nhưng các đường `0 → 2 → 3 → 4`, `0 → 1` hoặc đường khác đều có thể hợp lệ, tùy compilation policy. Không phải **mọi** method đi qua đủ các levels, và các compilation requests có thể nằm đợi trong compiler queues.

### Vì sao tier 2 và tier 3 khác nhau?

Full profiling có **runtime overhead**: cập nhật metadata và counters mất CPU/cache bandwidth, đôi khi còn ảnh hưởng compiled code size. C1 tier 2 cung cấp một mức chạy nhanh với limited notifications; tier 3 thu thêm feedback giúp C2 suy đoán và tối ưu có chất lượng hơn.

Tự suy rằng “C1 = không profiling” sẽ sai, nhưng “mọi C1 method luôn có full receiver type profile” cũng sai.

### Những factors khác ngoài counter

Tier transition còn xét compiler queue load, method kích thước lớn/nhỏ, code cache, tình trạng compiler, method đã compile hay chưa, profiling maturity và policy/flags. Có thể xuất hiện C2 compile cho method có nhiều invocations, hoặc không xuất hiện trong một test chạy rất ngắn.

## 8. MethodCounters và MethodData (MDO) khác nhau thế nào?

HotSpot có các cấu trúc VM-internal phục vụ quản lý method activity và dynamic profile:

- **MethodCounters** hoặc các counters nằm trong runtime method metadata: tín hiệu invocation, backedge và một số trạng thái phục vụ compilation policy.
- **MethodData / MethodDataObject (MDO)**: hồ sơ phong phú hơn gắn với method, trong đó có những **records liên hệ với BCIs** cụ thể, ví dụ type profiles tại virtual call site, branch-related counts và các data kinds khác.
- Data collection có thể bắt đầu từ interpreter và tiếp tục trong compiled code có instrumentation ở level phù hợp.
- Không có Java SE API cho ứng dụng đọc trực tiếp raw MDO receiver rows của HotSpot như một `Map<Class<?>, Long>`.

```text
Method com.example.Worker.process
   |
   +-- invocation/backedge counters
   |
   +-- MethodData (khi được tạo):
       |
       +-- @BCI 10: branch taken/not-taken tendencies
       |
       +-- @BCI 24: invokevirtual
       |            observed receiver: FastImpl, SafeImpl ...
       |
       +-- @BCI 52: invokeinterface
                    observed receiver distribution khác BCI 24
```

Đây là sơ đồ cấu trúc **ý niệm**, không phải layout/histogram được trích từ một JVM đang chạy. MDO có các record kinds/row counts giới hạn theo build, và nội dung có thể bị cập nhật/aging/reprofile; nó **không phải bản ghi chính xác đầy đủ của mọi object type từng đến call site**.

## 9. Type profile được thu thập ở đâu?

Ở **virtual dispatch**, method đích phụ thuộc **runtime class của receiver**. Ví dụ:

```java
interface Converter {
    int convert(int x);
}

final class FastConverter implements Converter {
    public int convert(int x) {
        return x + 1;
    }
}

final class SafeConverter implements Converter {
    public int convert(int x) {
        return x * 2;
    }
}
```

Đây là fragments của interface/classes; chưa có `main` để chạy độc lập.

Tại một bytecode `invokeinterface Converter.convert`, HotSpot có thể thu thập feedback receiver type đã quan sát. Một site nhận `FastConverter` gần như toàn bộ lần chạy có thể phù hợp cho **speculative inlining**; một site nhận nhiều implementations có thể dẫn tới guarded multimorphic paths hoặc generic dispatch.

### Monomorphic, bimorphic và megamorphic

| Thuật ngữ | Mô hình tại **một call site** | Hệ quả có thể |
| --- | --- | --- |
| **Monomorphic** | Một class receiver phổ biến/duy nhất đã quan sát | Dễ specialize, direct/guarded call hoặc inline |
| **Bimorphic** | Hai classes receiver phổ biến | Có thể inline một/vài đường với guards |
| **Polymorphic** | Nhiều receiver classes | Tối ưu phụ thuộc tần suất và inline budget |
| **Megamorphic** | Rất nhiều receiver classes | Một giả định đơn type thường kém hiệu quả |

Đây là **mô hình diễn giải**, không phải các kiểu bytecode do JVMS định nghĩa. “Monomorphic” không bảo đảm compiler luôn inline; “megamorphic” không bảo đảm chương trình luôn chậm. JIT còn xét receiver types, method size, call-site hotness, code-cache budget, CHA/static type information và machine-code properties.

**Profile theo site, không chỉ theo interface:** hai call sites cùng gọi `Converter.convert` có thể thấy type distributions hoàn toàn khác nhau. Type profile có gắn với vị trí bytecode/method chứ không phải bảng đếm tất cả `Converter` instances trong toàn heap.

## 10. Java 17 chạy được: một call site gặp hai kiểu receiver

Tạo file **`ReceiverProfileDemo.java`**:

```java
public class ReceiverProfileDemo {
    interface Operation {
        int apply(int x);
    }

    static final class AddOne implements Operation {
        public int apply(int x) {
            return x + 1;
        }
    }

    static final class DoubleIt implements Operation {
        public int apply(int x) {
            return x * 2;
        }
    }

    static int dispatch(Operation operation, int x) {
        return operation.apply(x);
    }

    static long run(Operation operation, int count) {
        long sum = 0;
        for (int i = 0; i < count; i++) {
            sum += dispatch(operation, i % 10);
        }
        return sum;
    }

    public static void main(String[] args) {
        long first = run(new AddOne(), 20_000);
        long second = run(new DoubleIt(), 5);

        System.out.println("addOne=" + first);
        System.out.println("double=" + second);
    }
}
```

```bash
javac --release 17 ReceiverProfileDemo.java
java ReceiverProfileDemo
```

**Stdout xác định:**

```text
addOne=110000
double=20
```

`AddOne` cho các giá trị từ 0 đến 9 tổng `1+2+...+10=55` trong một chu kỳ, có 2.000 chu kỳ nên được 110.000; `DoubleIt` cho 5 input 0–4, tổng bằng `0+2+4+6+8=20`.

Tại **cùng một site** `operation.apply(x)` trong `dispatch`, runtime được đưa vào một receiver type nhiều lần rồi một type khác. **Java semantics luôn phải đúng**, ngay cả nếu compiler đã chọn đường specialized dựa vào profile trước đó.

Điều mà output **không chứng minh**:

- Method `dispatch` đã được C2 compile.
- JIT chắc chắn đã inline `AddOne.apply`.
- Gặp `DoubleIt` chắc chắn gây một deoptimization.
- Dữ liệu receiver trong MDO có đúng tỷ lệ 20.000:5.

Các điều ấy phải được chứng minh bằng compiler diagnostics **trên JVM đang chạy**; JIT có thể inline vào caller, không compile trước type switch hoặc chọn fallback hợp lệ.

## 11. Type profiling và speculative inlining

Nếu một call site phần lớn gặp receiver class `AddOne`, C2 có thể tối ưu đường hot theo mô hình:

```text
Bytecode:
  invokeinterface Operation.apply

Observed at site:
  AddOne thường xuyên
  DoubleIt hiếm

Optimized fast path (mô hình):
  if receiver is AddOne:
      inline AddOne.apply(x)
  else:
      đúng hành vi dynamic dispatch (fallback/deopt)
```

**Không bắt buộc JIT phải sinh đúng một lệnh `if`** như sơ đồ. Compiler có thể dùng inline caches, devirtualization nhờ class hierarchy, exact types hoặc guards ở cấp mã máy; loại guard và cách fallback tùy build.

### Tại sao dữ liệu profile có thể không còn đại diện?

Application warmup chỉ chạy `AddOne`; sau rollout production bắt đầu nhận requests dùng `DoubleIt` hoặc thêm implementations mới. Profile ban đầu không còn đại diện cho phân phối hiện tại.

Nếu một speculative assumption trở nên sai, JVM có thể:

- Đi qua **generic fallback** đã sinh sẵn.
- Thực hiện **deoptimization** để trả execution về representation an toàn.
- Tiếp tục profiling và **recompile** với dữ liệu mới.
- **Invalidate/make not entrant** nmethod có dependency không còn đúng.

**Không bao giờ được cho kết quả sai** chỉ vì profile cũ. Guards/deopt/fallback là cách HotSpot khai thác đoán định nhưng giữ **Java-visible semantics**. Deopt là hành vi VM bình thường, không phải một Java exception nghiệp vụ.

## 12. Class Hierarchy Analysis (CHA) khác dynamic type profiling

Một lời gọi interface có thể được tối ưu vì:

1. Compiler thấy kiểu đích **exact/final** qua thông tin static.
2. **Class Hierarchy Analysis** nhận thấy một hierarchy/implementation phù hợp ở thời điểm compile và ghi dependency cần thiết.
3. **Dynamic type profile** cho thấy receiver type thường gặp nhất tại call site.
4. Những phân tích khác (inlining, escape, call graph) cho thấy đích gọi đủ đơn giản.

| Nguồn kiến thức | Ví dụ | Giới hạn |
| --- | --- | --- |
| Bytecode/static type | Variable được khai báo `Operation` | Không luôn xác định implementation |
| `final`/exact inferred type | Receiver chắc chắn class cụ thể trong path | Không quyết định một mình inline |
| CHA | Hierarchy ở VM thời điểm compile | Class mới có thể làm dependency cần invalidation |
| Type profile | Site thấy nhiều `AddOne` hơn `DoubleIt` | Profile có thể chưa đầy đủ hoặc lệch warmup |
| Compiler heuristic | Callee nhỏ, call hot | Có thể thay đổi theo JDK/flags |

Do đó, log cho biết một call được inline **không đủ chứng minh** rằng đó là thành quả trực tiếp của MDO type profile, nếu JIT đã biết đích gọi từ static/CHA.

## 13. Branch profile và type-check feedback bổ sung điều gì?

Bài tập trung ba tín hiệu, nhưng một MDO có thể có thống kê khác giúp chọn hot path:

```java
static int normalize(int value) {
    if (value >= 0) {
        return value + 1;
    }
    return -1;
}
```

Đây là **method fragment**. Nếu hầu hết input dương, compiler có thể bố trí code để đường hot ít overhead hơn. Tuy nhiên:

- Một Java `if` không tương đương một raw branch counter ổn định; bytecode và machine code có thể có CFG khác.
- Profile đo các paths đã quan sát, không chứng minh input tương lai vẫn cùng phân phối.
- Branch profiling không thay thế data validation; mọi input hợp lệ vẫn phải được xử lý đúng.
- Một số type-check records và uncommon-trap feedback giúp compiler tránh tiếp tục đặt giả định đã bị phá quá nhiều.

Không coi “99% true trong test” là license để xóa nhánh còn lại khỏi Java behavior. Nếu deoptimization/fallback xảy ra, code vẫn phải cho kết quả đúng.

## 14. Compiler levels 0–4 không phải dấu xác nhận tốc độ

Một method đã được compile level 4 có thể vẫn chậm vì:

- Algorithm có độ phức tạp lớn.
- Code phải truy cập dữ liệu không nằm trong CPU cache.
- Làm I/O, locks hoặc các safepoints.
- Có nhiều allocations/GC pressure.
- Receiver profile đa dạng và compiled code cần generic virtual calls.
- Method chịu frequent deoptimization hoặc code cache pressure.
- Startup JIT compilation cost cao so với thời gian tồn tại workload.

Ngược lại, một helper ngắn ở C1 hoặc được inline vào caller có thể đủ nhanh. **Tier là trạng thái compilation**, không phải xếp hạng hiệu năng trên dữ liệu thực.

### Một method có thể được compile nhiều lần

Các trường hợp hợp lệ:

- Promotion từ C1 tier 3 lên C2 tier 4.
- OSR entry cho loop đang chạy.
- Recompilation sau khi profile đủ mature hoặc dữ liệu thay đổi.
- Invalidation/deoptimization do class hierarchy dependency.
- Thay thế một compiled version không còn entrant.

Đừng đọc mỗi dòng `made not entrant` rồi gọi là memory leak hoặc crash. Cần timeline và lý do compile/deopt.

## 15. Quan sát bằng PrintCompilation

Trên HotSpot Java 17:

```bash
java -XX:+PrintCompilation BackedgeOsrDemo
```

Thông tin có thể xuất hiện: compile ID, timestamp, level, method name, bytecode size, marker `%` cho OSR, `@ BCI`, trạng thái `made not entrant` hoặc `made zombie`. Định dạng chính xác và các markers phụ thuộc build.

| Quan sát | Suy luận có căn cứ | Không thể kết luận |
| --- | --- | --- |
| Level 3 | C1 đã compile ở tier có profiling phù hợp | C2 chắc chắn sẽ xảy ra ngay |
| Level 4 | Có compilation task/result C2 | Future calls luôn chỉ dùng đúng nmethod này |
| `%` và `@ ...` | Có OSR compilation tại BCI | Vòng lặp Java luôn có OSR |
| `made not entrant` | Nmethod bị rút khỏi đường nhập mới | Chương trình có lỗi semantics |
| Compile IDs liên tục | Có activity của compiler threads | CPU bottleneck chính là JIT |

**Cảnh báo:** output của `PrintCompilation` thường có các methods nội bộ JDK, không chỉ class do bạn viết. Đừng tạo test assert thứ tự chính xác của compiler events; HotSpot scheduling/tiering/JIT thresholds đều biến động theo machine và version.

## 16. Quan sát inlining với PrintInlining

Một phương thức có thể hot nhưng JIT không inline vì code quá lớn, thiếu thông tin receiver, call not hot enough hoặc inlining budget. Dùng diagnostic options:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining ReceiverProfileDemo
```

Đây là một dòng lệnh Bash, PowerShell hoặc CMD đều có thể dùng trên HotSpot build hỗ trợ các options ấy. `PrintInlining` thường được khóa bởi **diagnostic VM options**; đặt `UnlockDiagnosticVMOptions` trước nó.

Đọc các dòng liên quan `ReceiverProfileDemo::dispatch`, `AddOne::apply`, `DoubleIt::apply` rồi đối chiếu compilation level. Thấy `inline (hot)` hay một lý do không inline có thể giúp giải thích decision, nhưng **không được bịa một log cố định**. Compiler có thể inline toàn bộ `dispatch` vào `run` và phân bố receiver profile theo inline context.

### Log nhiều không phải lúc nào cũng tốt

Diagnostic logging có thể tạo nhiều I/O, ảnh hưởng startup và benchmark; chỉ bật trong môi trường phù hợp, lọc/thu thập có giới hạn, không khẳng định “bật PrintInlining là cách làm app nhanh hơn”.

## 17. LogCompilation để phân tích sâu hơn

Một số HotSpot JDK 17 builds hỗ trợ log XML từ compiler:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -XX:LogFile=jit-log.xml ReceiverProfileDemo
```

Bạn có thể phân tích với **JITWatch** hoặc công cụ hiểu HotSpot compilation logs để quan sát tier transitions, inline attempts, failure reasons, trap/deoptimization patterns.

**Giới hạn cần nhớ:**

- Đây không phải API Java SE portable.
- File có thể lớn, tốn CPU/I/O và chứa thông tin về class/method names.
- Tên/định dạng các records có thể khác theo build.
- Compilation log không phải profiler CPU sampled stack và không cung cấp per-business-request invocation counts.
- Không nên diễn giải “không có method trong log” là method không từng chạy; có thể method chưa được JIT compile hoặc đã inline vào caller khác.

## 18. JFR, JMC và jcmd: xem compilation trong timeline thật

**Java Flight Recorder (JFR)** của JDK 17 có thể ghi sự kiện liên quan compiler, JVM runtime, GC, CPU và application time. Ví dụ trên một **server còn chạy** với PID thật:

```bash
jcmd <PID> JFR.start name=jit-observe settings=profile
jcmd <PID> JFR.dump name=jit-observe filename=jit-observe.jfr
jcmd <PID> JFR.stop name=jit-observe
```

`<PID>` là placeholder; thay bằng PID của process đang chạy, có quyền attach và JFR enabled. File `jit-observe.jfr` có thể được phân tích bằng Java Mission Control (JMC). Configuration `settings=profile` giúp bật những categories/events phù hợp với bộ setting của JDK, nhưng các event thresholds/sampling cũng phụ thuộc build và recording configuration.

JFR hữu ích để nối compiler events với **CPU samples, allocation/GC**, nhưng **không** phải một API công khai hiển thị **mọi raw MethodData counter/receiver record** từ interpreter/C1.

### Vì sao JFR có thể không thấy compiler event bạn muốn?

- Application chạy quá nhanh và kết thúc trước khi recording hoạt động.
- JVM đã compile method từ giai đoạn startup trước khi bắt đầu record.
- Profile settings không ghi một event type/threshold nào đó.
- Method được inline hoặc code chưa đủ hot để compile.
- Logging/sampling chi phí và data-loss conditions làm việc quan sát không tuyệt đối.

Không lấy sự vắng mặt của một JFR event làm bằng chứng rằng Java bytecode chưa bao giờ được chạy.

## 19. Dùng javap để nhận diện invoke và backedges

`javap -c -p` hiển thị **bytecode** trong class file, không phải machine code đã được JIT sinh:

```bash
javap -c -p ReceiverProfileDemo
javap -c -p BackedgeOsrDemo
```

Trong `ReceiverProfileDemo.dispatch`, thường có `invokeinterface` tới `Operation.apply`, nhưng **constant-pool index và BCI** tùy build. Trong `BackedgeOsrDemo.calculate`, có thể thấy branch/quay ngược tới loop header.

**Phân biệt rõ:**

| Công cụ | Quan sát được |
| --- | --- |
| `javap` | Class-file bytecode, BCI, method descriptors, metadata |
| `PrintCompilation` | JIT compile events, levels, OSR hints |
| `PrintInlining` | Inlining decisions/reasons của compiler |
| `LogCompilation`/JITWatch | Timeline và compiler diagnostics chi tiết hơn |
| JFR/JMC | Runtime activity, compilation-related events và sampled performance |
| CPU profiler | Code paths đang tiêu CPU theo sampling/instrumentation |
| Heap dump | Object graph/reachability, không phải invocation/type callsite profile |

Một log của C2 có thể nhắc BCI được lấy từ bytecode của method, nhưng nó **không** là Java source line. Một dòng source có thể tạo nhiều bytecode instructions; cần `LineNumberTable` nếu muốn đối chiếu source.

## 20. Vai trò của speculative optimization và deoptimization

Khi C2 dùng profile, nó có thể ưu tiên một hot path với **guards**:

```text
C2 thấy site đa số AddOne:
   |
   v
Guard receiver type == AddOne
   | true                   | false
   v                        v
Inlined fast path      Generic call / deopt
   |                        |
   +------> correct Java result
```

Nếu assumption bị phá, JVM có thể dùng **uncommon trap** để phục hồi interpreter-compatible state, sau đó reprofile/recompile. Những sự kiện này có cost nhưng là một phần của cơ chế **giữ an toàn cho speculative optimization**.

Ngoài receiver types, HotSpot có thể invalidate compiled code khi một assumption về **class hierarchy** không còn đúng sau khi class mới được load. Vì vậy đừng luôn quy một `made not entrant` cho receiver type profile sai; có thể do dependency khác.

Một deoptimization event **không phải Java exception** và không đồng nghĩa Java application trả kết quả sai. Nếu nó diễn ra liên tục trong workload ổn định, mới nên điều tra tính bền vững của profile và compile policies.

## 21. Profile pollution: dữ liệu warmup khác production

Ví dụ một server ban đầu chỉ xử lý JSON qua interface `Serializer`, rồi 30 phút sau nhận thêm Binary và XML formats. Callsite type profile của một đoạn code có thể biến đổi:

```text
Khởi động:
  Serializer.encode at BCI K
  JSON 100%

Sau rollout:
  JSON 50%
  Binary 30%
  XML 20%
```

Các tỷ lệ này là **mô hình**, không phải số liệu JVM đã quan sát. Nếu JIT đã special-case một receiver, workload shift có thể làm generic fallback tăng hoặc gây reoptimization.

Một kết luận sai thường gặp: “JVM profile sai, vậy Java interface là vấn đề.” Thực tế interface dispatch là ngữ nghĩa đúng; cách tối ưu profile-guided chỉ có lợi khi dữ liệu thống kê phù hợp. Có thể cải thiện bằng thiết kế callsite ổn định hơn **nếu CPU profiler chứng minh đó là bottleneck**, nhưng không phá abstraction chỉ để ép monomorphic.

## 22. Tránh nhầm Java benchmark với JIT profile

Một vòng lặp tự đo `System.nanoTime()` quanh cùng một method có thể sai lệch vì:

- **Warmup chưa đủ:** class loading, C1/C2 compilation, profile collection trộn vào thời gian đo.
- **Dead-code elimination (DCE):** result không được dùng nên JIT bỏ bớt logic.
- **Constant folding:** input cố định có thể được tính trước.
- **Loop unrolling/vectorization:** source iteration count không tương ứng machine operations.
- **Inlining:** số call instructions ở máy khác số lời gọi source.
- **OSR:** giữa lúc loop chạy có thể đổi sang compiled representation khác.
- **GC, CPU frequency, OS scheduling và background work** làm nhiễu.
- **Diagnostic logging** làm lệch thời gian.
- **Workload distribution** khác thực tế làm type profile không đại diện.

Dùng **JMH** (Java Microbenchmark Harness) với warmup, measurement, forks và result consumption thích hợp cho microbenchmark. Dùng **load test/JFR** cho end-to-end performance. Một microbenchmark chỉ kiểm tra một implementation type có thể không đại diện cho một polymorphic production callsite.

### Điều gì có thể suy ra từ output ví dụ?

- `BackedgeOsrDemo` in 28.000.000: vòng lặp tính đúng.
- `ReceiverProfileDemo` in 110.000 và 20: dynamic dispatch tính đúng cho cả hai receiver types.
- **Không** thể kết luận C2 đã inline, OSR đã diễn ra, hay một object đã đổi loại. Những điều đó cần **compiler diagnostics trên bản JDK cụ thể**.

## 23. Hạn chế của phương pháp đếm và lấy mẫu

**Invocation/backedge counters** hỗ trợ tiering, nhưng HotSpot có thể thay đổi cách cập nhật do execution tier. **Type profiles** lưu distributions tại một số sites, nhưng không phải mọi event đều phải được giữ thành một row. **JFR/JMC** và profilers lại dùng event/sampling semantics riêng.

Những yếu tố làm khác số đo:

1. Interpreter, C1 và C2 có instrumentation khác nhau.
2. Một method có thể được inline hoặc compiled theo nhiều versions.
3. Counters có thể được tổng hợp/decay/reset theo chính sách.
4. MDO record capacity cho receiver types hữu hạn.
5. Compile policy có thể giảm profiling overhead ở tiers nhất định.
6. JFR event sampling không phản ánh mọi invocation theo cùng nghĩa.
7. Java bytecode sites và machine-level control flow không trùng nhau sau optimization.
8. Workload thay đổi sau giai đoạn collecting profile.

Đừng so “100.000 calls” trong application metric với “hotness counter” trong internal diagnostic rồi quy mọi sai khác cho bug JVM. Hai số có **mục đích và definition khác nhau**.

## 24. Khi nào cân nhắc `-Xint` và `TieredStopAtLevel`?

Trong môi trường học tập, có thể thử:

```bash
java -Xint BackedgeOsrDemo
java -XX:TieredStopAtLevel=1 BackedgeOsrDemo
java -XX:+PrintCompilation BackedgeOsrDemo
```

- `-Xint` ưu tiên interpreted-only mode, nên không áp dụng JIT compilation thông thường.
- `-XX:TieredStopAtLevel=1` giới hạn compile levels ở C1 level 1, không phải tắt JIT.
- `PrintCompilation` quan sát compilation activity mà vẫn dùng tiering policy mặc định.

Những flags này thuộc HotSpot/launcher implementation; không phải lời khuyên production tuning tổng quát. Đừng lấy một lần đo rồi kết luận interpreter luôn chậm hơn chính xác một hệ số cố định; CPU/JVM/benchmark setup ảnh hưởng mạnh.

### Đừng sửa thresholds bừa bãi

Giảm threshold có thể compile quá sớm với profile chưa đủ đại diện, tăng compiler CPU/code cache overhead và dễ làm việc profiling khác đi. Tăng threshold có thể khiến ứng dụng ngắn hạn không bao giờ dùng C2 trong giai đoạn đo. Trước khi tuning, ưu tiên xem **real CPU hotspots, compile queue, inlining và deoptimization evidence**.

## 25. Một tình huống kiểm chứng từng bước

Giả sử service Java 17 có interface `PricingRule`, mỗi request áp dụng một rule:

- **Triệu chứng:** CPU tăng sau khi thêm nhiều rule implementations.
- **Giả thuyết A:** callsite `rule.evaluate` từ monomorphic thành polymorphic, nên C2 inline ít hơn.
- **Giả thuyết B:** thuật toán ở một rule mới phức tạp hơn, dù dispatch không đổi.
- **Giả thuyết C:** các requests mới allocate/parse nhiều dữ liệu hơn; bottleneck ở GC chứ không phải virtual call.
- **Giả thuyết D:** lúc rollout code bị deopt/recompile tạm thời, sau warmup ổn định.

Quy trình kiểm chứng:

1. Cố định input mix và đo p95/p99 latency, CPU, GC, throughput.
2. Dùng CPU profiler/JFR xác định code path thực sự đang chiếm CPU.
3. Bật `PrintCompilation`/`PrintInlining` ở môi trường chẩn đoán phù hợp.
4. Xem `PricingRule.evaluate` có hot, được compiled/inlined hay không.
5. So compilation profile trước và sau rollout **trên cùng JVM version**.
6. Kiểm tra if/branches và call site type distributions bằng evidence phù hợp.
7. Tách CPU của method implementation ra khỏi dispatch overhead bằng benchmark riêng.
8. Chỉ refactor/tune nếu có cải thiện đo được, không chỉ vì thấy một log “virtual call”.

Một callsite có nhiều receiver types không tự là bug. **Độ đa hình chỉ là một biến** trong performance của Java; thiết kế đúng và khả năng bảo trì vẫn quan trọng.

## 26. Checklist đọc compiler diagnostics có kỷ luật

| Câu hỏi | Công cụ/đầu mối | Lưu ý |
| --- | --- | --- |
| Method được gọi nhiều nhưng có compile không? | `PrintCompilation`, JFR | Compiler event không đếm từng invocation |
| Loop dài có OSR compilation không? | `PrintCompilation` dấu `%`/`@ BCI` | Không phải mọi loop chắc OSR |
| Bytecode site nào chứa invoke? | `javap -c -p` | Bytecode không có dynamic receiver distribution |
| C2 có inline không? | `PrintInlining`, LogCompilation/JITWatch | Output thay đổi theo thresholds/call graph |
| Type profile có ổn định không? | JVM-specific diagnostics, workload tracing | Không có Java SE API đọc raw MDO |
| Có deoptimization/recompile quá nhiều không? | Compilation logs, JFR events/VM diagnostics | Không tự coi deopt là bug |
| Method chậm do CPU hay GC? | CPU profiler, JFR GC/CPU data | Compiler log không phải CPU flame graph |
| Compiler bị nghẽn queue/code cache? | VM/compilation diagnostics | Hot method có thể chờ compiler |
| Tối ưu thực sự nhanh hơn không? | JMH hoặc end-to-end load test | Warmup/forks/input mix quyết định |

## 27. Những hiểu lầm thường gặp

| Khẳng định sai | Điều đúng |
| --- | --- |
| “JIT chỉ đếm method calls” | HotSpot còn quan sát loop backedges, receiver types, branches |
| “Method gọi N lần chắc chắn thành C2” | Tiers/thresholds/queues là dynamic VM policy |
| “Loop phải gọi method hàng nghìn lần mới compile” | Một long-running loop có thể kích hoạt OSR |
| “Backedge = source-level loop iteration” | Liên quan bytecode CFG, không phải contract source counter |
| “C1 không hỗ trợ profiling” | C1 tiers có limited/full profiling tùy level |
| “C2 luôn tiếp tục ghi toàn bộ profile như interpreter” | Profiling strategy khác nhau theo tier |
| “MDO là một Java Map public” | MDO là HotSpot internal profiling metadata |
| “Type profile chỉ có một bảng cho cả interface” | Nó có tính **site-specific** |
| “Monomorphic luôn được inline” | Còn cost model, static type, code size và budget |
| “Megamorphic luôn chậm” | Cost thực phải đo, nhất là khi callsite không hot |
| “Inlining dựa trên type profile nghĩa type khác sẽ tính sai” | Guards/fallback/deoptimization bảo toàn Java semantics |
| “Deoptimization là lỗi runtime” | Có thể là phần bình thường của speculative JIT |
| “OSR là gọi method lại từ đầu” | OSR tiếp tục invocation đang chạy ở một BCI |
| “`javap` hiển thị mã máy của JIT” | `javap` disassemble **bytecode** |
| “PrintCompilation là per-call trace” | Nó ghi compiler events và state |
| “PrintInlining output ổn định cho mọi JDK” | Diagnostic output và decisions khác build |
| “Chạy ra đúng kết quả chứng minh JIT đã OSR” | Java semantics đúng không chứng minh compiler path |
| “JFR profile là raw MDO dump” | JFR có sự kiện/sampling riêng |
| “Cứ bật nhiều log thì app sẽ nhanh hơn” | Logging có overhead, chỉ để chẩn đoán |
| “Một benchmark không warmup đủ để kết luận” | Warmup, DCE, JIT/OSR và CPU noise có thể làm sai |

## 28. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** Một method được gọi một lần nhưng có vòng lặp 50 triệu iterations. Tại sao JVM vẫn có thể muốn compile nó?

**Đáp:** Backedge activity báo loop nóng, có thể kích hoạt **OSR**.

**Câu 2.** Method invocation counter có bắt buộc bằng đúng số lần gọi Java source?

**Không.** Nó là VM-internal hotness/profiling signal và còn phụ thuộc execution tiers, compilation/inlining.

**Câu 3.** C1 level 2 và 3 khác nhau cơ bản ở đâu?

Level 2 thường thu **invocation/backedge signals hạn chế**; level 3 tạo **fuller profiling**, gồm type/branch feedback.

**Câu 4.** Cùng interface nhưng hai callsites có thể có receiver distributions khác nhau không?

**Có.** Type profiling tại từng callsite/BCI cung cấp dữ liệu theo site.

**Câu 5.** Profile cho thấy 99% `AddOne`. C2 chắc chắn phải inline `AddOne.apply`?

**Không.** Inlining còn phụ thuộc hotness, code size, CHA, budget và compiler policy.

**Câu 6.** Gặp receiver class mới có được phép cho kết quả cũ của class khác không?

**Không.** JVM phải dùng guards/fallback/deopt để bảo đảm Java dynamic dispatch semantics.

**Câu 7.** Dấu `%` trong HotSpot compilation log thường gợi ý gì?

Một **OSR compilation event**, thường kèm vị trí `@ BCI`.

**Câu 8.** `javap -c` có hiển thị C2 machine code không?

**Không.** Nó hiện JVM bytecode từ class file.

**Câu 9.** `BackedgeOsrDemo` in tổng đúng có chứng minh OSR đã xảy ra?

**Không.** Chỉ chứng minh phép tính đúng; cần diagnostics để biết OSR.

**Câu 10.** `PrintInlining` có thể dùng làm benchmark latency trực tiếp không?

**Không.** Nó là compiler diagnostic và có logging overhead; dùng JMH/load tests để đo latency.

**Câu 11.** Deoptimization có luôn là Java exception hoặc memory leak?

**Không.** Nó là một phần của speculation/fallback hợp lệ.

**Câu 12.** Warmup chỉ có một receiver type, production nhiều types. Điều gì có thể đổi?

Type profile, inline guards, deoptimization/recompilation và throughput; không có kết luận tốc độ cố định.

## Tài liệu chuẩn và nguồn kiểm chứng

- [Oracle Java SE 17 — `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:+PrintCompilation`, `-XX:+LogCompilation`, flags JIT và diagnostic options.
- [Oracle Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): bytecode BCI và invoke/branch instructions.
- [JVMS Java SE 17 — Instruction Set (`6.5`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5): `invokeinterface`, `invokevirtual`, `goto` và control flow.
- [JVMS Java SE 17 — JVM Frames (`2.6`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6): locals/operand stack phục vụ hiểu OSR và deopt.
- [OpenJDK 17 MethodData source](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/oops/methodData.hpp): receiver/branch profile data và counters, chi tiết thay đổi theo bản build.
- [OpenJDK 17 tiered compilation policy](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/compiler/tieredThresholdPolicy.hpp): các levels/notification/counter heuristics thuộc runtime.
- [How Tiered Compilation Works in OpenJDK — Microsoft Java Engineering](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/): diễn giải C1/C2, profile và transitions.
- [Java SE 17 — JFR](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html) và [`jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): timeline quan sát compilation/runtime.
- [JITWatch](https://github.com/AdoptOpenJDK/jitwatch): công cụ phân tích compilation logs và inline decisions của HotSpot.

**Ghi nhớ:** HotSpot không tối ưu chỉ dựa vào “method nào được gọi nhiều”. **Invocation counters** phát hiện repeated calls; **backedge counters** phát hiện loops nóng và giúp chọn **OSR**; **receiver type profiles** cung cấp thông tin tại các callsites phục vụ guarded/inlined dispatch. Tiered C1/C2 cân bằng profiling cost với tốc độ máy mã, còn **fallback/deoptimization** bảo đảm kết quả Java vẫn đúng khi profile hoặc class hierarchy thay đổi. Khi muốn chứng minh JIT đang làm gì, dùng compiler diagnostics trên **đúng JVM Java 17** và benchmark hợp lệ, không phán đoán từ source loop count hay output một lần chạy.
