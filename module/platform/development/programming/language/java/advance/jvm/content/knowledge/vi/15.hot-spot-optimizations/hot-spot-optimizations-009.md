# Vì sao thay đổi mã nguồn nhỏ có thể làm kết quả hiệu năng thay đổi lớn?

Trong **HotSpot JVM**, một thay đổi chỉ vài ký tự trong Java source có thể tạo khác biệt hiệu năng lớn, nhỏ, hoặc thậm chí **đảo chiều** sau khi ứng dụng chạy đủ lâu. Nguyên nhân không đơn thuần là “dòng code ngắn hơn chạy nhanh hơn”: Java source được biên dịch thành **bytecode**, sau đó HotSpot có thể **thông dịch**, **thu thập profile**, **JIT compile** bằng C1/C2, **inline**, **devirtualize**, **loại bỏ allocation**, **tối ưu vòng lặp**, **vectorize**, hoặc **deoptimize** khi giả định về runtime không còn hợp lệ.

Một chỉnh sửa nhỏ đôi khi vô tình làm compiler vượt hoặc không vượt một **ngưỡng quyết định tối ưu**. Ví dụ một method lớn thêm một ít bytecode có thể không còn phù hợp với **inlining heuristic**, hoặc thay một field thành `volatile` có thể ngăn các phép đơn giản hóa từng có trước đó. Ngược lại, thay một cấu trúc dữ liệu có thể giảm rất nhiều cache misses hoặc allocations dù chỉ thay vài dòng.

Bài học giải thích **cơ chế nhân–quả**, **khi nào không được quy kết cho JIT**, và **cách thiết kế thí nghiệm đáng tin** trên Java 17+.

## 1. Hiệu năng không tỉ lệ tuyến tính với số dòng source

Sơ đồ pipeline điển hình:

```text
Java source
   │ javac
   ▼
JVM bytecode
   │ class loading / linking / execution
   ▼
Interpreter + profiling (level 0)
   │ method/loop "hot", compiler queues
   ▼
C1 (levels 1–3) ────► C2 (level 4)
   │                      │
   │       type/branch profiles + speculation
   └──────────────────────┘
               │
               ▼
      native machine code
      trong HotSpot code cache
               │
               ▼
  CPU pipeline, caches, memory hierarchy,
  allocation, GC, OS scheduler, contention
```

**Một diff nhỏ ở source** có thể tác động tại nhiều tầng:

- Thay đổi bytecode size/cấu trúc control flow.
- Thay độ nóng của method hoặc vòng lặp và thời điểm JIT compile.
- Thay các receiver types quan sát tại một call site.
- Thay cơ hội **method inlining**, đặc biệt ở những chuỗi lời gọi.
- Thay khả năng **constant folding**, **dead-code elimination** hay **escape analysis**.
- Thay phân bố nhánh, locality, branch prediction và cache behavior.
- Thay tốc độ cấp phát, thời điểm GC và safepoint.
- Thay lock contention hoặc ràng buộc memory ordering.
- Thay tính chất thí nghiệm: compiler đã tối ưu bỏ thứ được “đo”.

**Không có luật “thêm 1 dòng = chậm thêm X nanosecond”**. Phải xác định đường mã thực tế CPU chạy và toàn bộ điều kiện đo.

## 2. Hiểu đúng hai kiểu thay đổi

### 2.1. Thay đổi hành vi chương trình

Ví dụ thay thuật toán O(n²) bằng O(n log n), đổi danh sách liên kết thành mảng liên tiếp, thêm bộ nhớ đệm hoặc thay truy cập I/O. Những thay đổi đó có thể làm tốc độ khác lớn **mà không cần viện dẫn JIT**.

```java
// Đoạn minh họa trong một method, không phải chương trình độc lập.
for (int i = 0; i < values.length; i++) {
    result += values[i];
}
```

Nếu `values` là `int[]`, cách biểu diễn trực tiếp khác với `List<Integer>` có boxing/references và cách truy cập khác. Nhưng không được khẳng định mảng luôn nhanh hơn trong mọi tác vụ; API, access patterns, nullability và collections khác nhau có trade-off riêng.

### 2.2. Không đổi kết quả chức năng nhưng đổi đường tối ưu

Ví dụ thay một method nhỏ thành một chuỗi delegates, thêm một tầng interface/proxy, hoặc thêm một lệnh ghi `volatile`. Kết quả trả về có thể vẫn đúng như cũ, nhưng JIT và CPU nhìn thấy **khác hẳn**.

Chìa khóa là biết **đã thay cái gì**: semantic work, compiler opportunity hay môi trường đo? Nếu không phân loại, dễ quy mọi khác biệt cho “HotSpot khó đoán”.

## 3. Ngưỡng biên dịch phân tầng: thay đổi làm method nóng sớm hay muộn

HotSpot thường bắt đầu thực thi bytecode bằng **interpreter**, có thể biên dịch C1 rồi C2 khi profile và policy thích hợp:

| Level | Thành phần | Vai trò khái quát |
| --- | --- | --- |
| 0 | Interpreter | Thực thi ban đầu, thu thập counters/profile |
| 1 | C1 không full profiling | Compiled code nhẹ, không nhắm thu nhiều dữ liệu |
| 2 | C1 limited profiling | Theo dõi độ nóng với instrumentation hạn chế |
| 3 | C1 full profiling | Thu type/branch data phục vụ tối ưu tiếp |
| 4 | C2 | Optimized code, có thể dùng profile và assumptions |

**Không phải mọi method đều đi tuần tự qua 0 → 1 → 2 → 3 → 4.** Policy lựa chọn dựa trên invocation/backedge counters, thời điểm compiler threads xử lý queue, method size, code cache và những điều kiện khác.

### Một dòng thay đổi số lần gọi có thể đổi cả cấp execution

Giả sử method `process` trước đây được gọi 50 lần khi startup, sau khi refactor được gọi 50.000 lần. Cùng phần thân method có thể:

- Ban đầu chạy interpreter.
- Được C1 compile khi đủ nóng.
- Nhận type/branch profiles.
- Được C2 tối ưu sâu hơn sau warm-up.

Trong một benchmark quá ngắn, thay đổi như vậy khiến ta đang **so interpreter ở bản A với optimized code ở bản B**, không phải đang đo “tác động trực tiếp của một dòng refactor”.

### Vòng lặp dài và OSR

**On-Stack Replacement (OSR)** cho phép HotSpot chuyển một method **đang chạy trong loop dài** sang compiled code tại một bytecode index thích hợp. Vì vậy một thay đổi nhỏ về loop bounds có thể ảnh hưởng độ nóng qua backedge counters; kết quả chạy lần đầu và các lần sau khác nhau.

**Không suy** cứ vượt chính xác 10.000 iterations là OSR bắt buộc; compiler policy, flags và môi trường khác nhau.

## 4. Inlining cliff: thay vài bytecode nhưng mất cơ hội inline

**Inlining** thay lời gọi method bằng body của callee trong compiled caller (khi compiler thấy phù hợp). Với HotSpot, đó là quyết định theo **heuristics, profiling, bytecode size và budgets**, không phải quy tắc “mọi method dưới N dòng đều được inline”.

Ví dụ:

```java
static int addOne(int x) {
    return x + 1;
}

static int compute(int x) {
    return addOne(x) * 2;
}
```

Hai methods trên là **snippet đặt trong cùng class**. Nếu compiler inline `addOne`, nó có thể thấy toàn biểu thức `(x + 1) * 2` và tối ưu thêm. Nhưng không bảo đảm tất cả JDK builds/conditions phải inline.

### Một thay đổi nhỏ có thể vượt ngưỡng inlining

Giả sử bổ sung validation, logging, exception handling hoặc các nhánh vào callee:

```java
static int addOneWithCheck(int x) {
    if (x < 0) {
        throw new IllegalArgumentException("negative");
    }
    return x + 1;
}
```

Trên dữ liệu toàn số dương, kết quả kinh doanh vẫn là cộng 1. Nhưng body/call graph/cost thay đổi:

- Callee có nhiều bytecode hơn.
- Có nhánh mới và đường exception.
- Compiler phải bảo toàn exception semantics.
- Inlining decision có thể đổi.
- Khi không inline, caller có thể mất cơ hội constant propagation và các tối ưu xuyên method.

**Đây là khả năng, không phải một kết quả đo sẵn:** HotSpot có thể vẫn inline callee có kiểm tra, hoặc hoist/eliminate kiểm tra nếu đủ căn cứ. Không tuyên bố cứ thêm `if` sẽ làm code chậm.

### Inlining heuristic không phải ABI

Có những cờ HotSpot như `MaxInlineSize`, `FreqInlineSize`, `MaxTrivialSize` và các giới hạn ngân sách khác. Nhưng một threshold bytecode không độc lập quyết định tất cả: **hot methods** có thể có ngưỡng khác cold methods; call depth, recursive inlining, compiler budgets, type profile, code cache cũng tác động.

Khi sửa một method đúng gần ngưỡng, performance có thể có dạng **bước nhảy** chứ không tăng đều theo số bytecode. Vì thế gọi hiện tượng này là một **optimization cliff** hữu ích hơn diễn giải “dòng mới tốn 3 ns”.

## 5. Devirtualization cliff: receiver profile đổi khi refactor

Một interface call thường được biên dịch thành `invokeinterface` trong bytecode. Nhưng ở hot call site, HotSpot có thể dùng **class hierarchy analysis (CHA)** và **type profiling** để xác định đích, rồi direct call hoặc inline.

Ví dụ:

```java
interface Operation {
    int apply(int x);
}

final class AddOne implements Operation {
    public int apply(int x) {
        return x + 1;
    }
}

final class TimesTwo implements Operation {
    public int apply(int x) {
        return x * 2;
    }
}
```

Đây là những types minh họa, chưa có `main`. Một caller:

```java
static int route(Operation operation, int value) {
    return operation.apply(value);
}
```

**Case A:** trong warm-up, `route` gần như chỉ nhận `AddOne`. Type profile có thể **monomorphic**, thuận lợi cho guarded devirtualization và inlining.

**Case B:** chỉ thêm một đường gọi với `TimesTwo`, call site có thể trở thành **polymorphic**. Compiler có thể tạo guarded paths cho một vài targets, hoặc chọn generic dispatch, hoặc deopt/recompile nếu assumptions cũ không phù hợp.

**Không đồng nhất “có 2 implementations trong source” với “call site bimorphic”:** profile theo **runtime receiver types ở chính site**. Interface có 100 implementations nhưng site chỉ gặp một type vẫn có thể monomorphic.

### Giả định có thể bị mất hiệu lực

- New plugin class được load.
- Dynamic proxy hoặc subclass xuất hiện.
- Traffic chuyển sang một concrete type khác.
- Class hierarchy dependency không còn đúng.
- Code C2 từng inline target dựa trên speculative type data.

HotSpot cần **guard/fallback/deoptimization/compiled dependency invalidation** để bảo toàn Java semantics. Một site có target bất ngờ **không được** gọi nhầm implementation cũ. Nhưng không phải **mọi lần** gặp type mới đều buộc deopt: compiler có thể có fallback path phù hợp.

### Vì sao chênh lệch có thể lớn?

Nếu devirtualization giúp inline method nhỏ, còn inlining cho phép constant folding/escape analysis xuyên method, mất optimized target có thể làm mất **cả chuỗi tối ưu**. Không chỉ thêm chi phí một virtual dispatch instruction.

## 6. Escape analysis: thêm một reference escape làm biến mất scalar replacement

**Escape analysis (EA)** xem một object có thể thoát khỏi method/thread hay không. HotSpot C2 có thể dùng thông tin ấy để **scalar-replace** một object: giữ các giá trị field như scalars thay vì duy trì một heap allocation vật lý trong optimized path.

Ví dụ:

```java
static int localScore(int x) {
    Pair p = new Pair(x, x * 2);
    return p.left + p.right;
}
```

Đây là snippet; `Pair` phải được định nghĩa trong cùng class. Nếu `p` không escape và compiler hiểu toàn đường xử lý, việc tạo object có thể bị loại bỏ trong compiled code.

Chỉnh nhẹ:

```java
static volatile Object published;

static int publishedScore(int x) {
    Pair p = new Pair(x, x * 2);
    published = p;
    return p.left + p.right;
}
```

Đây là snippet minh họa trong một class. Ghi reference tới **static volatile field** làm object **được công bố ra ngoài scope cục bộ**, thường ngăn việc loại bỏ allocation bằng cùng chiến lược scalar replacement. Chênh lệch có thể liên quan hàng loạt:

- Heap allocations.
- TLAB refill và allocation fast path.
- Garbage generation/GC work.
- Write barriers và volatile memory-ordering costs.
- CPU cache traffic và memory bandwidth.

**Cẩn trọng:** không tuyên bố mọi `new Pair` tạo object vật lý trong mọi JVM/mọi path; cũng không nói local version chắc chắn được scalar-replace. Đây là **cơ hội tối ưu phụ thuộc C2/JDK/profile**.

### HotSpot EA không đồng nghĩa tự động cấp phát trên stack

Tài liệu HotSpot EA mô tả **scalar replacement**, không nên khẳng định HotSpot C2 JDK 17 mặc định thực hiện **general-purpose stack allocation** của mọi object non-escaping. “Allocation đã biến mất” có thể là vì các fields được thay thế bằng scalars/optimized operations, không phải vì object chỉ chuyển nơi cấp phát từ heap sang stack.

### Không chỉ `volatile` mới gây escape

Object có thể escape qua:

- Return object reference.
- Ghi vào field của một object sống lâu hoặc static field.
- Đưa vào collection được giữ từ ngoài.
- Truyền qua call mà JIT không thể chứng minh receiver/callee không giữ reference.
- Native/JNI interaction.
- Cấu trúc concurrent/shared state.

Tuy vậy, **return object** không tự có nghĩa allocation chắc chắn tồn tại sau inline của caller; compiler có thể phân tích xuyên method trong ngữ cảnh tối ưu. Cần xem escape **trong compiled scope**, không chỉ một câu lệnh Java.

## 7. Dead-code elimination: phép đo trông nhanh vì công việc đã bị xóa

Một microbenchmark ngây thơ:

```java
static int pure(int x) {
    return x * x + 1;
}

static void suspicious() {
    for (int i = 0; i < 1_000_000; i++) {
        pure(42);
    }
}
```

Đây là hai methods minh họa trong một class. Kết quả mỗi lần gọi `pure(42)` **không được sử dụng**, và `pure` không có side effects. JVM/JIT có thể loại bỏ phép tính cùng phần lớn/all vòng lặp khi quan sát rằng nó không ảnh hưởng hành vi chương trình.

Nếu một phiên bản benchmark **in kết quả** còn phiên bản khác **bỏ kết quả**, sự khác biệt tốc độ có thể khổng lồ vì **không còn đo cùng công việc**. Nhận định “phiên bản B chạy nhanh gấp 1.000 lần” lúc đó hoàn toàn không chứng minh thuật toán B tốt hơn.

### Khắc phục khi benchmark

- Kết quả phải được **consume** bằng cách mà harness làm phù hợp.
- Với **JMH**, có thể **return result** từ `@Benchmark` hoặc dùng `Blackhole.consume(result)`.
- Không vội dùng một `volatile` store **mỗi iteration** để “chống DCE” rồi quên rằng bạn vừa thêm chi phí synchronization/memory ordering vào phép đo.
- Dữ liệu đầu vào phải thay đổi theo trường hợp thực, không chỉ một literal compiler có thể constant-fold.
- Hãy đọc JMH samples chính thức về **Dead Code Elimination** và **Constant Folding**.

**Tránh hiểu quá mức:** chỉ vì bạn “dùng kết quả” trong Java source không đồng nghĩa benchmark đã đúng. JIT vẫn có thể xác định output là hằng số hoặc hoist công việc ra khỏi vùng đang đo. JMH giúp thiết kế harness, nhưng **không thay tư duy kiểm chứng**.

## 8. Constant folding và constant propagation: literal nhỏ cũng khác

Ví dụ:

```java
static int calculate(int x) {
    return (x * 31 + 7) & 1023;
}

static int constantInput() {
    return calculate(42);
}
```

Đây là snippet minh họa trong class. Nếu compiler inline `calculate`, input hằng `42` làm biểu thức có thể tính **ngay tại compile time**; chương trình chạy sau đó không còn thực hiện phép nhân/cộng ấy ở hot path.

Thay `42` bằng một runtime field:

```java
static volatile int changingInput = 42;

static int runtimeInput() {
    return calculate(changingInput);
}
```

Lệnh đọc `volatile` phải tuân thủ Java Memory Model, giá trị có thể thay đổi bởi thread khác. Compiler không thể tự biến mọi lần đọc thành một literal nếu như thế làm thay đổi semantics.

**Hai phiên bản không còn đo cùng điều kiện tính toán.** Nếu purpose là đo cost của `calculate` với inputs runtime, dùng non-constant `@State` trong JMH, tránh thiết kế loop để JIT suy đầu vào bất biến vô tình.

### `final` và compile-time constants

`static final int VALUE = 42;` là **constant variable** phù hợp với Java constant expressions và có thể được inlined tại bytecode level ở những call sites. Nhưng **không phải mọi `final` field là compile-time constant**: `final Object`, `final` field được khởi tạo runtime hoặc giá trị lấy từ I/O có ngữ nghĩa khác.

**Cẩn trọng khi benchmark:** “chỉ thêm `final`” đôi khi cho phép constant propagation, nhưng hiệu ứng phụ thuộc dữ liệu, cách khởi tạo, phạm vi compiled method và JIT.

## 9. Loop transformations: một nhánh hoặc alias thay đổi vectorization

Những biến đổi có thể áp dụng trên loops gồm:

- **Loop unrolling**: xử lý nhiều iterations mỗi lượt.
- **Loop invariant code motion**: đẩy biểu thức bất biến ra ngoài loop.
- **Range-check elimination**: bỏ bounds checks đã chứng minh dư thừa.
- **SuperWord/vectorization**: có thể dùng SIMD instructions khi mẫu truy cập/data dependencies phù hợp.
- **Strength reduction**: biến đổi phép toán tốn chi phí thành dạng phù hợp.
- **Auto-vectorization constraints**: aliasing, dependencies, exception semantics và CPU instruction set.

Ví dụ:

```java
static void addArrays(int[] a, int[] b, int[] out) {
    for (int i = 0; i < out.length; i++) {
        out[i] = a[i] + b[i];
    }
}
```

Đây là method có thể biên dịch khi đặt trong class, nhưng **nó chỉ đúng nếu a/b có độ dài tối thiểu bằng out**. VM phải giữ khả năng ném `ArrayIndexOutOfBoundsException` khi inputs ngắn. Không được bỏ checks nếu chưa chứng minh an toàn theo luật exception ordering.

Chỉnh loop:

```java
static void addArraysWithSideEffect(int[] a, int[] b, int[] out) {
    for (int i = 0; i < out.length; i++) {
        out[i] = a[i] + b[i];
        counter++;
    }
}
```

Đây là snippet; `counter` phải là field được khai báo. Với `counter` thông thường, JIT có thể gộp/di chuyển một số updates nếu không quan sát xen kẽ. Với `volatile counter`, mỗi iteration mang semantics khác, làm vectorization/hoisting phức tạp và tăng memory-ordering cost.

**Không khẳng định** vòng đầu luôn vectorized, vòng sau luôn scalar: cần kiểm tra CPU, compiler logs/assembly, array aliasing, hotness và JDK build. Chỉ sửa một dòng có thể làm **mất điều kiện áp dụng** một tối ưu, không bảo đảm kích hoạt/tắt một instruction duy nhất.

### Dependency giữa các vòng lặp

`out[i] = out[i - 1] + x` tạo loop-carried dependency (với i bắt đầu từ 1). Nó khác một loop độc lập mỗi element. Một refactor thay cách đọc/ghi có thể tạo data dependency khiến SIMD không còn phù hợp, dù số dòng rất ít.

## 10. Branch prediction và dữ liệu đầu vào

Một thay đổi nhỏ ở điều kiện `if` có thể:

- Làm hot path trở thành nhánh khó dự đoán.
- Thay số CPU branch mispredictions.
- Thay code layout sau JIT.
- Thay cơ hội hoist/inline/loop predication.
- Làm profile tại thời điểm warm-up không đại diện production.

Ví dụ minh họa:

```java
static int countPositive(int[] values) {
    int count = 0;
    for (int value : values) {
        if (value > 0) {
            count++;
        }
    }
    return count;
}
```

Nếu 99,9% values dương thì branch có phân bố khác với dữ liệu random 50/50. CPU và compiler có thể ứng xử khác, ngay cả khi source **không đổi**.

### “Chỉ đổi một phép so sánh” không tự chứng minh branch misprediction

Compiler có thể dùng branchless operations, vectorize hoặc hoán đổi branch order. Trong thực tế:

1. Đảm bảo hai phiên bản xử lý **cùng đầu vào và cùng semantic workload**.
2. Profiling bằng JFR/async-profiler/perf (nếu có quyền), so CPU hotspots/counters.
3. Kiểm tra compiled code nếu cần phân biệt branch/conditional move/vector instructions.
4. Đo sau warm-up đủ và trên nhiều runs.

**Không dùng một bảng “if/else luôn chậm hơn ternary”**; HotSpot quyết định codegen, CPU predictor quyết định chi phí theo mẫu data.

## 11. Cache locality và cấu trúc dữ liệu

Một thao tác đổi `int[]` thành `List<Integer>` nhìn có thể chỉ sửa một chữ ký, nhưng ảnh hưởng cả:

- Các element được lưu trực tiếp hay qua object references.
- Boxing/unboxing (có thể được tối ưu ở một số paths nhưng không nên mặc định).
- Memory footprint/header/padding của boxed values.
- Object graph và GC scanning.
- CPU cache misses, prefetching và pointer chasing.
- Allocation rate và retained heap.

Ví dụ conceptual:

```java
int[] numbers = new int[1000];
java.util.List<Integer> boxed = new java.util.ArrayList<>();

for (int i = 0; i < numbers.length; i++) {
    numbers[i] = i;
    boxed.add(i);
}
```

Đây là snippet trong method. `boxed` chứa references tới các `Integer` objects; có thể có boxing cache cho một số values, nhưng không được suy tất cả phần tử đều tạo object riêng hoặc `boxed` luôn chậm hơn trong mọi phép toán.

### Một sửa nhỏ thay allocation pattern

Trong một hot loop, thay `new StringBuilder()` mỗi iteration bằng một instance tái sử dụng có thể giảm allocations; nhưng nếu instance sống lâu và bị giữ qua thread/shared state, nó có thể tăng footprint, contention hoặc tạo bug. Cần đánh giá **ownership và thread safety** chứ không chỉ số lần `new`.

## 12. `volatile`, đồng bộ hóa và lock elision

Một field bình thường và một field `volatile` có semantics Java Memory Model khác nhau. Đổi khai báo:

```java
int counter;
```

thành:

```java
volatile int counter;
```

có thể ảnh hưởng memory ordering, CPU cache coherence và cơ hội compiler optimize reads/writes. Nhưng **không nên bỏ `volatile` chỉ vì benchmark chậm**: nếu nhiều threads cần visibility/happens-before, đó là yêu cầu correctness.

**Điểm quan trọng:** `volatile++` **không nguyên tử** khi nhiều threads cùng cập nhật; phép read-modify-write vẫn có thể mất update. Nếu cần atomic increment, dùng `AtomicInteger.incrementAndGet()` hoặc synchronization phù hợp.

### Lock elimination

Nếu compiler chứng minh object không escape và synchronization trên object không thể ảnh hưởng thread khác, HotSpot có thể thực hiện lock elision thích hợp. Nhưng một refactor đưa object vào static shared field/collection có thể mất proof, khiến synchronization thật sự tốn kém.

**Không định lượng trước** “synchronized thêm đúng X ns”; contention, biased/modern locking implementation, monitor inflation, safepoints và JVM release đều ảnh hưởng.

## 13. GC, allocation và safepoints khuếch đại khác biệt

Một allocation nhỏ tăng lên mỗi request đôi khi làm tốc độ thay đổi đáng kể vì:

- Tăng Eden/TLAB refill rate.
- Young GC diễn ra thường hơn.
- Promotion pressure làm old generation căng.
- More references trong object graph tăng tracing work.
- Safepoint pauses đụng vào request latency.
- CPU của GC threads cạnh tranh với application/JIT threads.

Ví dụ, nếu một refactor tạo 50.000 temporary objects mỗi request và tải là 100 requests/giây, số allocations tăng theo workload: **5 triệu objects/giây** chỉ từ nguồn đó, trước khi tính những allocations khác. Đây là phép nhân điều kiện, **không tự chứng minh GC pause tăng gấp bao nhiêu** vì object sizes/lifetimes/collector/JIT có thể khác.

### Đừng suy đoán do GC từ một lần đo

Một run “bản A 20 ms, bản B 50 ms” có thể chỉ khác GC timing. Cần nhiều iterations/forks và GC logs để phân biệt:

- Thời gian code thật.
- GC pauses phát sinh trong measurement.
- JIT compilation trong measurement.
- Allocation pressure/trạng thái heap.
- OS scheduling, CPU frequency và thermal throttling.

**Heap used giảm** cũng không tự nói end-to-end throughput tăng: collector khác nhau có thể giữ committed memory cho lần dùng sau, RSS không đồng nhất với live-set.

## 14. Code cache và compilation budget

HotSpot tạo machine code C1/C2 trong **code cache** (native executable memory), khác Java heap. Một thay đổi source nhỏ có thể:

- Làm JIT inline thêm hoặc bớt method.
- Tạo nmethod lớn/nhỏ khác.
- Thay số compiled variants và OSR entries.
- Tăng compilation CPU/time.
- Thay áp lực lên profiled/non-profiled code heaps.
- Khi cực đoan, góp phần làm code cache đầy và compilation bị hạn chế.

**C2 compile nhiều không phải luôn tốt hơn**: tăng code size có thể gây instruction-cache misses hoặc compilation overhead lớn hơn lợi ích runtime.

Nếu code cache đầy, JVM có thể in cảnh báo liên quan:

```text
CodeCache is full. Compiler has been disabled.
```

Đây là **mẫu có thể gặp**, không phải log bắt buộc. Muốn xác minh cần xem `Compiler.codecache`, flags và compilation logs chứ không dựa một symptom throughput thấp.

## 15. Ví dụ Java 17+ runnable: cùng kết quả logic, khác cơ hội tối ưu

Tạo file **`HotSpotSmallChangeDemo.java`**:

```java
public class HotSpotSmallChangeDemo {
    interface Operation {
        int apply(int x);
    }

    static final class AddOne implements Operation {
        @Override
        public int apply(int x) {
            return x + 1;
        }
    }

    static final class TimesTwo implements Operation {
        @Override
        public int apply(int x) {
            return x * 2;
        }
    }

    static final class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        int score() {
            return x + y;
        }
    }

    // Giữ object reference ra ngoài phạm vi local.
    static volatile Point published;

    static int call(Operation operation, int value) {
        return operation.apply(value);
    }

    static long monomorphic(int count) {
        Operation add = new AddOne();
        long sum = 0;

        for (int i = 0; i < count; i++) {
            sum += call(add, i % 10);
        }
        return sum;
    }

    static long polymorphic(int count) {
        Operation add = new AddOne();
        Operation times = new TimesTwo();
        long sum = 0;

        for (int i = 0; i < count; i++) {
            Operation target = (i & 1) == 0 ? add : times;
            sum += call(target, i % 10);
        }
        return sum;
    }

    static long localPoints(int count) {
        long sum = 0;

        for (int i = 0; i < count; i++) {
            int value = i % 7;
            Point point = new Point(value, value * 2);
            sum += point.score();
        }
        return sum;
    }

    static long publishedPoints(int count) {
        long sum = 0;

        for (int i = 0; i < count; i++) {
            int value = i % 7;
            Point point = new Point(value, value * 2);
            published = point;
            sum += point.score();
        }
        return sum;
    }

    public static void main(String[] args) {
        long mono = monomorphic(100_000);
        long poly = polymorphic(100_000);
        long local = localPoints(70_000);
        long escaped = publishedPoints(70_000);

        System.out.println("monomorphic: " + mono);
        System.out.println("polymorphic: " + poly);
        System.out.println("local points: " + local);
        System.out.println("published points: " + escaped);
        System.out.println("equal point results: " + (local == escaped));
        System.out.println("last published x: " + published.x);
    }
}
```

### Biên dịch và chạy

```bash
javac -encoding UTF-8 HotSpotSmallChangeDemo.java
java HotSpotSmallChangeDemo
```

**Standard output xác định, không bật compiler/GC logging:**

```text
monomorphic: 550000
polymorphic: 750000
local points: 630000
published points: 630000
equal point results: true
last published x: 6
```

**Vì sao các số đúng:**

- `i % 10` lặp qua 0..9, tổng 45; `AddOne` cộng thêm 1 mỗi lần, tổng một chu kỳ 55. Có 10.000 chu kỳ: `55 × 10.000 = 550000`.
- Ở `polymorphic`, các chỉ số chẵn có inputs 0,2,4,6,8, `AddOne` tạo tổng 1+3+5+7+9 = **25** mỗi chu kỳ. Các chỉ số lẻ có inputs 1,3,5,7,9; `TimesTwo` tạo tổng 2+6+10+14+18 = **50**. Tổng mỗi chu kỳ 75, lặp 10.000 lần: **750000**.
- `Point(value, value * 2)` cho `score = 3 × value`. Với value 0..6, tổng một chu kỳ = `3 × 21 = 63`. Có 10.000 chu kỳ: **630000** ở cả local và published versions.
- Lượt cuối `i = 69999`, `i % 7 = 6`, nên `published.x` là **6**.

### Demo này chứng minh gì?

1. Runtime dispatch chọn đúng method khi call site nhận một hoặc hai implementation types.
2. Hai body khác nhau về object publication nhưng giữ **cùng kết quả số học** cho chuỗi inputs.
3. Ghi reference vào `volatile` field có semantics observable; đường local không tự động buộc object escape.
4. Có thể kiểm tra output đúng trên Java 17+ độc lập với JIT policy.

### Demo không chứng minh gì?

- **Không chứng minh** monomorphic path chắc chắn nhanh hơn polymorphic path: hai operations ở ví dụ còn khác phép toán, nên không thể dùng tổng thời gian để tách riêng dispatch cost.
- **Không chứng minh** localPoints luôn không allocate: còn phụ thuộc JIT, inlining/EA và runtime version.
- **Không chứng minh** publishedPoints nhất định gây N GC collections: timing và heap ergonomics không xác định.
- **Không chứng minh** chỉ tăng 1 dòng là tốc độ đổi X lần: muốn kết luận performance phải có benchmark tách workload và điều kiện đo.
- **Không chứng minh** JIT phải compile `call` ở level 4: code có thể còn interpreter/C1 hoặc bị inline vào caller.

**Đây là bài thử correctness và giải thích optimization opportunities, không phải microbenchmark chuẩn.**

## 16. Quan sát JIT behavior với cùng chương trình

Trên HotSpot JDK 17+:

```bash
java -XX:+PrintCompilation HotSpotSmallChangeDemo
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining HotSpotSmallChangeDemo
```

Bạn có thể thấy compiler activity cho cả Java standard library; logging có thể xen với output từ `System.out.println`. Tìm những method names như:

```text
HotSpotSmallChangeDemo::call
HotSpotSmallChangeDemo::localPoints
HotSpotSmallChangeDemo::publishedPoints
HotSpotSmallChangeDemo$Point::score
```

Đây là **các tên gợi ý để lọc logs**, không đảm bảo cả bốn được compile hoặc tên format y hệt ở mọi JDK/vendor.

### Những dấu hiệu cần phân biệt

| Dấu hiệu | Cách diễn giải đúng |
| --- | --- |
| Compile ID mới cho method | HotSpot ghi nhận một compilation event theo format JVM |
| Level 3/4 | Tiered compilation policy đưa method vào mức phù hợp |
| `inline (hot)` | Một compilation context đã chọn inline target |
| `virtual call` | Ở context đó có thể chưa inline/general dispatch vẫn cần |
| `made not entrant` | Một compiled version không còn nhận entries mới |
| Dấu `%` của compilation event | Thường báo OSR compilation |
| Không thấy method | Chưa chắc method không được tối ưu; có thể inline vào caller, chưa hot hoặc logs không hiện như mong đợi |

**Không kết luận DCE/EA/vectorization chỉ từ `PrintCompilation`:** công cụ này cho biết compilation events chứ không chứng minh machine instructions nào còn tồn tại.

### Chạy các JIT modes khác nhau

```bash
java -Xint HotSpotSmallChangeDemo
java -XX:TieredStopAtLevel=1 HotSpotSmallChangeDemo
java -XX:+PrintCompilation HotSpotSmallChangeDemo
java -XX:-TieredCompilation HotSpotSmallChangeDemo
```

Nếu binary hỗ trợ các HotSpot flags, **stdout tính toán vẫn phải giữ nguyên**. Nhưng execution mode, compile activity và timing có thể khác. **`-XX:-TieredCompilation` không đồng nghĩa `-Xint`**: nó thay policy chứ không bắt buộc tắt JIT hoàn toàn.

### Kiểm tra bytecode, không nhầm với machine code

```bash
javap -c -p HotSpotSmallChangeDemo
```

`javap` đọc bytecode trong class file: `invokeinterface`, `new`, `getfield`, `putstatic` ... vẫn có thể thấy dù compiled machine code đã inline hoặc scalar-replace. Không dùng sự tồn tại của `new` opcode như bằng chứng allocation vật lý chắc chắn xảy ra trong optimized execution.

## 17. Cách thiết kế benchmark thực sự bằng JMH

**Java Microbenchmark Harness (JMH)** là dự án của OpenJDK thiết kế để chạy và phân tích nano/micro/milli benchmarks, giúp kiểm soát warm-up, forks, iterations và những bẫy JIT phổ biến. Nhưng một benchmark dùng JMH **vẫn có thể sai** nếu so hai workloads khác nghĩa hoặc JIT optimize luôn công việc định đo.

### Thiết lập dự án

Cách khuyến nghị là dùng **Maven archetype chính thức của JMH**, cấu hình dependency và annotation processor đúng bản JMH bạn chọn. Xem README dự án để lấy **archetype version mới thực sự có ở môi trường build**, tránh tự đoán phiên bản:

- https://github.com/openjdk/jmh
- https://github.com/openjdk/jmh/tree/master/jmh-samples

Sau khi tạo một project JMH chuẩn (trong đó đã có `pom.xml` hợp lệ), thêm class sau vào source package phù hợp.

### Ví dụ JMH: tách các benchmark methods

Tạo file `DispatchBench.java` trong package `org.sample` của project JMH đã được cấu hình:

```java
package org.sample;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class DispatchBench {
    interface Op {
        int apply(int x);
    }

    static final class AddOne implements Op {
        public int apply(int x) {
            return x + 1;
        }
    }

    static final class TimesTwo implements Op {
        public int apply(int x) {
            return x * 2;
        }
    }

    private Op first;
    private Op second;
    private int counter;

    @Setup
    public void setup() {
        first = new AddOne();
        second = new TimesTwo();
        counter = 0;
    }

    private static int call(Op op, int value) {
        return op.apply(value);
    }

    @Benchmark
    public int oneReceiverType() {
        int x = counter++;
        return call(first, x & 31);
    }

    @Benchmark
    public int alternatingTypes() {
        int x = counter++;
        Op op = (x & 1) == 0 ? first : second;
        return call(op, x & 31);
    }
}
```

**Code trên yêu cầu thư viện JMH** và project có annotation processing, **không** được chạy bằng `javac DispatchBench.java` thuần nếu chưa có dependencies. Nó được thiết kế để biên dịch trong Maven JMH archetype project.

Build/run trong project JMH:

```bash
mvn -q clean package
java -jar target/benchmarks.jar DispatchBench
```

**Không có stdout nanoseconds cố định.** Results phụ thuộc CPU/JDK/GC/environment, harness forks và những optimizations ở mỗi benchmark. Chỉ nên dùng làm điểm bắt đầu để **quan sát behavior**, chưa đủ chứng minh riêng chi phí interface dispatch.

### Giới hạn quan trọng của ví dụ benchmark này

Hai phương thức khác nhau không thực hiện cùng một phép toán mỗi iteration: `alternatingTypes` có phép chọn receiver và đôi khi phép nhân thay vì cộng. Vì thế nếu kết quả timing khác, **chưa thể quy toàn bộ chênh lệch cho devirtualization**.

Để cô lập giả thuyết, cần thiết kế controls cùng operations, kiểm tra profiles/compiled code và chỉ thay một yếu tố; ví dụ hai implementations có **cùng math** nhưng khác concrete class, rồi benchmark target selection overhead độc lập. Thậm chí thế vẫn còn ảnh hưởng từ branch selection, class loading, JIT inlining context.

### Nguyên tắc JMH quan trọng

- **`@State`:** mang runtime inputs thay vì để mọi thứ thành compile-time constants.
- **`@Benchmark` trả về result:** harness consume để giảm rủi ro DCE.
- **`@Warmup`:** giúp compiler có thời gian profile/compile; số iterations phải phù hợp workload.
- **`@Fork`:** tách JVM processes, tránh nhiễm compiled state giữa cases.
- **`@Measurement`:** đo nhiều iterations sau warm-up, báo distribution/error.
- **`@Param`:** hữu ích để kiểm tra nhiều input distributions, nhưng không tự giải quyết mọi alias/profile issue.
- **`Blackhole`:** dùng khi cần consume nhiều outputs; không lạm dụng trong nội vòng nếu chính overhead của nó làm lệch kết quả.
- **Test setup:** tránh object creation/file I/O trong `@Benchmark` nếu mục tiêu chỉ là đo pure computation và việc setup có thể tách ra hợp lệ.

**Không dùng benchmark “càng nhanh càng tốt” nếu tối ưu loại bỏ công việc làm hai phiên bản không còn cùng semantics**. Luôn có correctness oracle độc lập.

## 18. Phương pháp A/B để tìm nguyên nhân thật sự

Khi thay một vài dòng mà thời gian đổi lớn, làm theo trình tự:

### Bước 1 — Chốt metric

Bạn đang đo **startup**, **time to first request**, **steady-state throughput**, **allocation rate**, **GC pause p99**, **request latency p99** hay **CPU cycles trên hot path**? Cùng code có thể tốt ở một metric và kém ở metric khác.

### Bước 2 — Giữ ổn định điều kiện

- Cùng **JDK vendor, build, JVM flags, garbage collector**.
- Cùng OS, CPU architecture, core availability, power plan/frequency, container CPU/memory limits.
- Cùng dữ liệu đầu vào và phân bố receiver types.
- Cùng heap, cache warm state và resource limits khi hợp lý.
- Cùng chuẩn chọn concurrency/thread count.
- Đo qua nhiều lần/forks, xem variability/error bars thay vì chỉ giá trị tốt nhất.

### Bước 3 — Kiểm tra đúng kết quả

Hai phiên bản phải cùng **ngữ nghĩa và side effects** trong yêu cầu nghiệp vụ. Kết quả số học bằng nhau chưa đủ nếu version mới loại bỏ logging, locking, I/O hoặc xử lý lỗi cần thiết.

### Bước 4 — Xem codegen/JIT evidence

Dùng compilation/inlining logs, JFR, perf profiler hoặc assembly (khi có) để kiểm tra:

- Method có tới cùng compilation level không?
- Inlining tree có khác?
- Có deopt/uncommon traps hoặc class hierarchy invalidations?
- Escape analysis/scalar replacement có tạo khác biệt không?
- Có số allocations, GC cycles, code cache growth khác?
- Có branch/cache misses khác khi profiler hỗ trợ?

### Bước 5 — Kiểm chứng giả thuyết bằng biến đổi nhỏ

Ví dụ nghi mất inlining, kiểm tra body bytecode `javap -c`, inlining logs, rồi tách một thay đổi nhỏ để cô lập. Nghi escape, dùng allocation profiler và cases local vs published. Nghi cache locality, đổi container/data layout với cùng workload.

**Tránh “shotgun tuning”** thay đồng thời 10 flags, rồi không biết điều gì làm khác.

### Bước 6 — Đánh giá dưới tải đại diện

Một microbenchmark thắng 25% chưa đủ để chứng minh service throughput sẽ tăng 25%. Khi phần lớn thời gian chờ I/O, database, lock contention hoặc GC, tối ưu một method có thể không ảnh hưởng mục tiêu đầu cuối.

## 19. Công cụ theo loại nguyên nhân

| Cần xác minh | Công cụ/phương pháp | Cẩn trọng |
| --- | --- | --- |
| Source đổi bytecode thế nào | `javap -c -p`, `javap -v` | Không phản ánh native code đã JIT |
| Method được compile ở level nào | `-XX:+PrintCompilation` | Logs biến động theo JVM/run |
| Caller/callee có inline không | `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` | Inlining context và formatting phức tạp |
| Cần JIT detail | `-XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation` | Có thể tạo log lớn |
| Machine code thật | `PrintAssembly` cùng `hsdis` đúng binary, JIT analyzers | Không có hsdis không đồng nghĩa JIT không chạy |
| Allocation pressure | JFR allocation events, async-profiler, GC logs | Sampling/overhead và attribution cần xem |
| GC pause/throughput | `-Xlog:gc*`, JFR, production telemetry | Không nhầm GC duration với end-to-end latency |
| Code cache/queues | `jcmd PID Compiler.codecache`, `Compiler.queue` | PID thật, tool availability |
| CPU hot paths | JFR, async-profiler hoặc OS perf tools | Có thể cần quyền đặc biệt |
| Microbenchmark | JMH warm-up/forks/Blackhole | Harness tốt không chữa benchmark design sai |
| Retaining paths | Heap dump + dominator analysis | Live set khác allocation rate |
| Hardware memory/cache | Hardware PMU counters khi được phép | CPU/OS-specific và dễ nhiễu |

Một vài HotSpot JDK 17 diagnostics:

```bash
java -XX:+PrintCompilation HotSpotSmallChangeDemo
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining HotSpotSmallChangeDemo
java -Xlog:gc*:info HotSpotSmallChangeDemo
jcmd -l
jcmd PID Compiler.queue
jcmd PID Compiler.codecache
```

**Thay `PID` bằng process ID thực tế** của JVM còn chạy. Demo ngắn có thể thoát trước khi `jcmd` attach. Những commands/JVM flags có thể khác giữa vendors/builds, không được copy mặc định sang OpenJ9 hoặc Native Image.

### Diagnostic flags có thể thay cả measurement

Bật `PrintInlining`, `LogCompilation`, JFR heavy events hoặc profiler instrumentation có thể tạo overhead và thay timing. Dùng chúng để **giải thích** compiler decisions; không dùng thời gian từ một run có logging rất nặng để kết luận tốc độ production.

## 20. “Thay ít mà chênh lớn” cũng có thể là thống kê

Giả sử đo hai phiên bản:

```text
Run 1: A=18 ms, B=26 ms
Run 2: A=22 ms, B=17 ms
Run 3: A=20 ms, B=19 ms
```

Đây là **số giả định để luyện suy luận**, không phải một benchmark kết quả thật. Nếu chỉ lấy Run 1, người đọc sẽ thấy B chậm 44% và dễ đưa ra kết luận sai. Nhưng các runs sau đảo thứ tự, cho thấy môi trường hoặc trạng thái JVM đang nhiễu.

Khi phân tích phải báo:

- Số forks/iterations, warm-up và measurement duration.
- Center estimates (mean/median) kèm variability/error bars.
- Distribution/percentiles nếu đo latency.
- Input distributions và CPU/runtime configuration.
- Có outliers, GC events, compiler transitions hay OS interference.
- Tác động lên resource footprint và semantics.

**Không cherry-pick** run đẹp nhất, không dùng một median microbenchmark để cam kết p99 request latency sẽ tương ứng.

### Amdahl’s Law: tối ưu hot path chưa chắc đổi tổng throughput lớn

Nếu một method chỉ chiếm 1% tổng request time, làm method ấy nhanh gấp 10 lần chỉ có thể cải thiện nhỏ ở end-to-end time (bỏ qua tương tác hệ thống khác). Ngược lại, một thay đổi gây leak/GC pauses có thể làm p99 tăng vọt dù average CPU trên hot method chỉ nhích chút ít.

**Đo bottleneck thực tế** trước khi chỉnh source để JIT “vui hơn”.

## 21. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Ít dòng code hơn chắc chắn nhanh hơn.” | Bytecode, JIT, allocations và CPU path mới quyết định |
| “Cùng thuật toán thì cùng performance.” | Data layout, profiling, cache và compiler khác |
| “`javap` thấy `new` nghĩa object chắc chắn được cấp phát vật lý.” | JIT có thể scalar-replace nếu đủ điều kiện |
| “Thêm một `if` luôn khiến code chậm.” | Branch có thể được fold, predict, hoist hoặc optimized |
| “`final` luôn giúp method nhanh.” | Có thể tạo opportunities, nhưng không bảo đảm thắng |
| “Interface calls luôn phải làm virtual dispatch.” | JIT có thể devirtualize/inline |
| “Một method thêm bytecode làm nó luôn mất inline.” | Thresholds là heuristic, cần logs và compile context |
| “C1/C2 biên dịch method ngay khi gọi đúng N lần.” | Tiered policy/queues/counters phức tạp hơn |
| “OSR chỉ xuất hiện sau khi method return.” | Có thể chuyển code trong loop đang chạy |
| “Profile monomorphic sẽ mãi mono.” | Traffic/class loading thay đổi, có guard/deopt |
| “Một deopt là JIT bug.” | Speculation có cơ chế rút lui đúng semantics |
| “`volatile` chỉ là gợi ý cho compiler.” | Là ràng buộc Java Memory Model |
| “`volatile++` đã atomic.” | Không, increment gồm read-modify-write |
| “Tắt inlining đồng nghĩa tắt JIT.” | Không, các cơ chế khác nhau |
| “`-XX:-TieredCompilation` = `-Xint`.” | Sai, một bên đổi policy, một bên chạy interpreter-only |
| “Output nanosecond trong benchmark phải cố định.” | Timing phụ thuộc nhiều yếu tố runtime/OS/CPU |
| “Dùng `System.nanoTime()` là tự động đo đúng.” | Không chữa warm-up, DCE và constant folding |
| “`Blackhole` bảo đảm benchmark không thể sai.” | Vẫn cần đúng workload/methodology |
| “GC pause là toàn bộ thời gian của service.” | Một nguồn trễ, phải đối chiếu traces |
| “Có logging JIT mà không thấy method thì chắc không có tối ưu.” | Nó có thể inline vào caller/chưa hot hoặc khác log format |
| “Microbenchmark nhanh gấp 2 → service cũng tăng 2x.” | Bottleneck end-to-end có thể ở nơi khác |
| “Đổi Java source là nguyên nhân duy nhất.” | CPU quota, heap, flags, thermal và dữ liệu có thể khác |

## 22. Bài tập kèm đáp án

**Bài 1.** Một method chỉ tăng vài bytecode nhưng hot caller bỗng chậm. Có thể có nguyên nhân JIT nào?  
**Đáp án:** Mất một inlining decision, làm mất các tối ưu xuyên method; xác minh bằng `PrintInlining` và benchmark đủ warm-up.

**Bài 2.** Tại sao loop triệu lần với kết quả không sử dụng có thể “nhanh phi lý”?  
**Đáp án:** Dead-code elimination/constant folding có thể xóa công việc. Dùng JMH result consumption/Blackhole và runtime inputs.

**Bài 3.** Đổi `calculate(42)` thành `calculate(dynamicValue)` làm thời gian tăng. Có chắc dynamic version kém?  
**Đáp án:** Không. Phiên bản literal có thể constant-fold, nên hai tests không đo cùng work.

**Bài 4.** Một interface có 20 concrete classes nhưng tại site chỉ nhận một type. Có phải site megamorphic?  
**Đáp án:** Không. Profile theo receiver types quan sát **tại call site**.

**Bài 5.** Một type mới xuất hiện sau warm-up, có thể tác động gì?  
**Đáp án:** Guard failure/fallback, deopt hoặc recompile; không được phá dynamic dispatch semantics.

**Bài 6.** C1 level 3 có phải luôn nhanh hơn C1 level 2?  
**Đáp án:** Không. Level 3 thu profile phong phú hơn và có instrumentation costs.

**Bài 7.** Một method được gọi một lần nhưng loop rất dài có thể được JIT không?  
**Đáp án:** Có thể qua OSR và backedge counters.

**Bài 8.** Tại sao ghi một object vào static volatile field có thể tăng allocation cost?  
**Đáp án:** Nó escape khỏi local scope, thường ngăn scalar replacement và thêm volatile semantics/write barrier.

**Bài 9.** Escape analysis có nghĩa mọi object non-escaping chuyển lên stack không?  
**Đáp án:** Không. HotSpot C2 có scalar replacement; không mô tả đó là general-purpose stack allocation.

**Bài 10.** Trong demo, `monomorphic(100000)` cho bao nhiêu?  
**Đáp án:** **550000**, mỗi chu kỳ 0..9 cộng 1 có tổng 55.

**Bài 11.** Trong demo, `polymorphic(100000)` cho bao nhiêu?  
**Đáp án:** **750000**, mỗi chu kỳ có tổng chẵn-plus-one 25 và lẻ-times-two 50.

**Bài 12.** Hai Point variants trong demo trả số nào?  
**Đáp án:** Cùng **630000**, vì tổng 0..6 nhân 3 là 63, lặp 10.000 chu kỳ.

**Bài 13.** Chỉ sửa `int` thành `volatile int` có phải chỉ thay một từ không ảnh hưởng correctness?  
**Đáp án:** Không. Nó làm thay đổi memory-visibility/order semantics; phải đánh giá concurrency correctness và performance.

**Bài 14.** Code truy cập `int[]` và `List<Integer>` có thể khác memory behavior ở đâu?  
**Đáp án:** Direct primitive storage so với boxing/references và backing arrays/objects, GC và cache locality.

**Bài 15.** JIT không inline một method có làm program sai logic?  
**Đáp án:** Không. Cách gọi khác, semantics bắt buộc không đổi.

**Bài 16.** Có thể khẳng định một loop với `if` luôn không vectorized?  
**Đáp án:** Không. Compiler/CPU/version/data dependencies quyết định.

**Bài 17.** GC log xuất hiện trong lần đo chậm có chứng minh code mới kém hơn?  
**Đáp án:** Chưa. Cần nhiều runs và kiểm tra allocation rate/live set/GC causality.

**Bài 18.** Cách dùng `-Xint` trong chẩn đoán là gì?  
**Đáp án:** So sánh với interpreter-only path về correctness/performance; không đại diện production JIT throughput.

**Bài 19.** Vì sao `javap -c` không đủ xác nhận C2 đã vectorize loop?  
**Đáp án:** Nó chỉ in JVM bytecode, không đọc machine code đã JIT.

**Bài 20.** Một microbenchmark thắng 20% có bảo đảm latency p99 API cũng tốt 20%?  
**Đáp án:** Không. End-to-end có I/O, queues, GC, locks và bottlenecks khác.

**Bài 21.** Sao phải fork JVM khi đo JMH?  
**Đáp án:** Giảm nhiễm state giữa benchmark runs, warm-up/compiler profiles/GC khác nhau; vẫn cần thiết kế inputs đúng.

**Bài 22.** Mục tiêu startup 200 ms, có nên warm-up 30 phút rồi chỉ đo steady-state?  
**Đáp án:** Không. Cần đo mục tiêu thật là startup/time-to-ready, song song với steady-state nếu cần.

**Bài 23.** `System.nanoTime()` trả kết quả rất khác sau khi bật `PrintInlining`; kết luận gì?  
**Đáp án:** Diagnostics có overhead và có thể thay scheduling. Không dùng logging-heavy run làm performance baseline.

**Bài 24.** Nên sửa interface thành concrete class trước khi đo để tránh virtual dispatch?  
**Đáp án:** Không mặc định; JIT có thể devirtualize và thiết kế OO có giá trị. Profile chứng minh bottleneck trước khi đổi API.

## 23. Checklist thực hành trước khi tin một “speedup” lớn

- [ ] Có cùng **kết quả chức năng và side effects** không?
- [ ] Đang đo **startup, warm-up, steady-state, throughput hay latency**?
- [ ] Đã giữ JVM vendor, version, collector, flags và CPU/memory constraints giống nhau?
- [ ] Có dùng inputs runtime đủ đa dạng, tránh constant folding ngoài ý định?
- [ ] Có dùng result consumption/Blackhole để tránh DCE?
- [ ] Có warm-up/forks/measurement iterations đủ và kết quả sai số?
- [ ] Có kiểm tra JIT compilation levels, `PrintInlining`, deopt khi cần?
- [ ] Có phân biệt interface-call cost với operation/branch cost?
- [ ] Có xem allocation profiler/GC logs nếu code tạo nhiều objects?
- [ ] Có phân biệt escape analysis opportunity với allocation vật lý đã được đo?
- [ ] Có cân nhắc vectorization/aliasing/CPU instruction availability?
- [ ] Có kiểm tra concurrency semantics khi thêm/bỏ `volatile` hoặc locks?
- [ ] Có ghi lại input distribution/receiver types của workload?
- [ ] Có chạy benchmark trên cùng máy/điều kiện power/CPU throttling?
- [ ] Có tách logging/profiling runs khỏi timing baselines?
- [ ] Có đo impact end-to-end sau microbenchmark?
- [ ] Có phân tích confidence/variance thay vì chỉ so hai con số?
- [ ] Có tài liệu hóa lý do thực nghiệm trước khi thay JIT flags production?

## 24. Tóm tắt

**Thay đổi ít ở Java source không có nghĩa thay đổi ít ở runtime.** HotSpot là compiler thích nghi với workload, nên một diff nhỏ có thể làm thay **thời điểm method được biên dịch, profile của call site, khả năng inline, escape, constant fold, loại dead code, vectorize, branch prediction, code cache và GC behavior**. Nhiều tối ưu tác động theo chuỗi, do đó tốc độ có thể thay đổi theo **bậc nhảy** thay vì tỉ lệ với độ dài diff.

Song song, benchmark có thể “nhanh lên” chỉ vì đã **không còn làm công việc cần đo**. Một kết quả tốc độ lớn chỉ có ý nghĩa khi đã kiểm chứng **cùng semantics, cùng workload, JIT phase tương đương và điều kiện hệ thống kiểm soát**.

### Tài liệu tham khảo

- **OpenJDK Java Microbenchmark Harness (JMH)** — cách xây dựng và chạy benchmark JVM: https://github.com/openjdk/jmh
- **OpenJDK JMH Sample 08 — Dead Code Elimination:** https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java
- **OpenJDK JMH Sample 10 — Constant Folding:** https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java
- **Oracle JDK 17 — The java Command** (TieredCompilation, PrintCompilation, PrintInlining, Inline, Code Cache): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **OpenJDK — HotSpot Escape Analysis and Scalar Replacement Status:** https://cr.openjdk.org/~cslucas/escape-analysis/EscapeAnalysis.html
- **OpenJDK — JEP 197 Segmented Code Cache:** https://openjdk.org/jeps/197
- **Oracle JDK 17 — HotSpot GC Tuning Guide:** https://docs.oracle.com/en/java/javase/17/gctuning/
- **OpenJDK JMH Blackhole source:** https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/infra/Blackhole.java

**Thông điệp cuối:** một regression hay speedup lớn sau refactor ngắn **là tín hiệu để điều tra cơ chế, không phải bằng chứng mã ngắn hơn hoặc một keyword cụ thể nhanh hơn**. Hãy dùng JMH và công cụ JIT/GC phù hợp để kiểm tra điều JVM thực sự đã làm, rồi đánh giá kết quả trên toàn ứng dụng.