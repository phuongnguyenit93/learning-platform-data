# Giả định tối ưu, deoptimization và biên dịch lại khi giả định không còn đúng

**JIT compiler** (Just-In-Time) của JVM không chỉ dịch bytecode thành mã máy. Trong HotSpot, JIT có thể **quan sát chương trình đang thực thi**, học kiểu đối tượng hay gặp, nhánh thường được đi qua và những method đang “nóng”, rồi sinh mã máy chuyên biệt để chạy nhanh hơn. Điểm tinh tế: một số phép tối ưu dựa trên **giả định có vẻ đúng ở thời điểm biên dịch nhưng không phải chân lý bất biến**.

Ví dụ: trong 100.000 lần gọi `operator.apply(value)`, receiver đều thuộc class `AddOne`. JIT có thể đặt một **type guard** và inline lời gọi như `AddOne.apply`, thay vì thực hiện virtual dispatch theo cách tổng quát. Nhưng ở lần thứ 100.001, chương trình có thể truyền `TimesTwo`; JVM vẫn phải thực thi đúng `TimesTwo.apply`. Một cách xử lý là **deoptimization**: rời phiên bản mã máy quá chuyên biệt, tái tạo trạng thái Java cần thiết và tiếp tục bằng interpreter hoặc một mức compiled code phù hợp; JVM có thể thu thập profile mới và **biên dịch lại** với giả định phù hợp hơn.

> **Speculative optimization không có nghĩa JVM đoán rồi chấp nhận kết quả sai.** Mọi phép tối ưu hợp lệ phải bảo toàn hành vi mà Java Language Specification và JVM Specification yêu cầu, kể cả khi assumption thất bại.

Bài học thuộc nhóm **Thông dịch và JIT**. Trọng tâm là phân biệt **profiling → speculation → guard/dependency → deoptimization → interpreter/fallback → recompilation**, hiểu uncommon traps, type profile và class hierarchy assumptions, phân biệt **mã biên dịch bị invalidated** với **object Java bị garbage-collected**, và thực hành trên **Java 17/HotSpot** mà không bịa số lượng JIT events.

## 1. Java bytecode, interpreter và compiled nmethod

Java source thường được `javac` dịch thành **class file bytecode**. Tại runtime, HotSpot có thể:

- Thực thi bytecode bằng **interpreter**.
- Thu thập **invocation counts, backedge counts và type/branch profiles** khi chương trình chạy.
- Biên dịch những method/loops “hot” bằng **C1** (client compiler, có các mức instrumentation/optimization) hoặc **C2** (server optimizing compiler), tùy cấu hình tiered compilation.
- Chuyển từ interpreted sang compiled code, hoặc giữa các mức compiled code, khi profile đủ thông tin và biên dịch hoàn tất.
- Nếu compiled code không còn an toàn/hợp lệ hoặc một nhánh “hiếm” bất ngờ xuất hiện, **deoptimize**, chuyển control sang cách thực thi vẫn giữ Java semantics.
- Có thể **reprofile và recompile** nếu method còn nóng và JVM nhận thấy phiên bản code khác sẽ phù hợp hơn.

**Tên `nmethod`** trong HotSpot thường chỉ một đơn vị **native machine code** được sinh để thực thi Java method (bao gồm cả các phiên bản tối ưu/hỗ trợ OSR phù hợp). Nó nằm trong **Code Cache**, không phải một “Java source method” mới và không phải một instance trên Java heap.

```text
Java source
    │ javac
    ▼
Java bytecode  ───────────────────────────────────────┐
    │                                                │
    ▼                                                │
Interpreter / tiered runtime                         │
    │ thu thập profile (hotness, types, branches)     │
    ▼                                                │
C1 / C2 JIT compilation                              │
    │                                                │
    ▼                                                │
Optimized machine code (nmethod)                     │
    │                                                │
    ├── giả định còn đúng → đường chạy nhanh           │
    │                                                │
    └── guard/dependency invalidated                 │
            │                                        │
            ▼                                        │
        DEOPTIMIZATION                               │
          ├─ dựng lại Java-level execution state     │
          ├─ resume interpreter/fallback             │
          └─ profile/recompile khi thích hợp ─────────┘
```

**Cảnh báo:** Đây là hình ảnh logic cho việc học. Compiler decisions, code entrypoints, safepoints, on-stack replacement và khả năng quay về một mức compiled code khác có chi tiết implementation-specific; không có quy tắc “mỗi deopt chắc chắn có một lần compile mới ngay lập tức”.

## 2. Tối ưu có chứng minh và tối ưu dựa trên giả định

Không phải mọi JIT optimization đều speculative.

| Loại | Ý tưởng | Khi nào cần fallback? |
| --- | --- | --- |
| **Tối ưu được chứng minh an toàn** | Compiler biết phép rút gọn luôn giữ semantics, ví dụ constant folding hợp lệ hoặc elimination dưới conditions đã được chứng minh | Không cần deopt chỉ vì giả định profile về nhánh không còn đúng |
| **Speculative optimization theo type profile** | “Phần lớn receivers tại call site này là `AddOne`” | Nếu receiver thuộc type khác, guard phải xử lý đường tổng quát hoặc deopt |
| **Giả định từ class hierarchy** | “Hiện tại chưa có subtype/override làm thay đổi tính duy nhất của target” | Khi class loading/linking làm dependency invalid, VM phải ngừng dùng compiled assumptions không còn đúng |
| **Nhánh hiếm, uncommon path** | “Thông thường điều kiện không bao giờ true trong profile quan sát” | Khi path xuất hiện cần xử lý đúng; có thể dùng uncommon trap |
| **Hoisting/check elimination có guard** | “Đối tượng/giá trị thỏa điều kiện này ở vùng code tối ưu” | Nếu guard fails, tránh thực thi tiếp trên cơ sở giả định sai |
| **Escape-analysis-based optimization** | Allocation/lock có thể được giảm hoặc loại bỏ nếu không ảnh hưởng hành vi quan sát | Tại deopt, JVM cần giữ Java state tương đương, có thể materialize đối tượng ảo theo metadata |

Một giả định **đã được chứng minh** dựa trên quy tắc ngôn ngữ/bytecode không cùng bản chất với giả định **đúng phần lớn do profile**. Lấy `-XX:-TieredCompilation` hoặc tắt JIT để so sánh không làm Java bytecode đổi semantics; nhưng nó có thể làm thay đổi cách runtime thu thập profile, thời gian warm-up và hiệu năng.

### 2.1. Speculation không phải đoán bừa

C2 không “đoán class bất kỳ”. Nó có các nguồn thông tin:

- **MethodData/profile information** thu thập tại một số bytecode sites.
- Tần suất các target receiver types tại `invokevirtual`/`invokeinterface`.
- Nhánh thường đúng/sai ở một điều kiện.
- Lịch sử throw của một số checks, ví dụ null/type checks.
- Trạng thái class hierarchy/dependency mà VM có thể theo dõi.
- Những invariant được chứng minh bằng phân tích bytecode và các tối ưu của compiler.

Dù một profile nói “100% calls là type A” trong giai đoạn warm-up, nó chỉ mô tả quá khứ. JVM phải duy trì **guard hoặc dependency** phù hợp để chương trình còn đúng khi tương lai xuất hiện type B.

## 3. Type profiling, monomorphic và polymorphic call site

Xét Java:

```java
interface Operation {
    int apply(int value);
}

final class AddOne implements Operation {
    public int apply(int value) { return value + 1; }
}

final class TimesTwo implements Operation {
    public int apply(int value) { return value * 2; }
}

static int evaluate(Operation op, int value) {
    return op.apply(value);
}
```

Đây là **snippet minh họa**. Một file chạy độc lập nằm ở mục 10.

- **Monomorphic profile:** ở một call site, runtime chủ yếu quan sát **một receiver type**. JIT có thể devirtualize và inline target.
- **Bimorphic/polymorphic profile:** site quan sát hai hoặc nhiều receiver types; compiler có thể chọn một số guarded inlines, type tests, hoặc virtual dispatch tùy thresholds/heuristics.
- **Megamorphic site:** nhiều receiver types khiến việc chuyên biệt hóa bằng hàng loạt guarded inlines có thể kém hiệu quả; generic dispatch có thể hợp lý.

Các từ “mono/bi/mega” mô tả đặc điểm của **call site và profile** trong một ngữ cảnh, không phải thuộc tính vĩnh viễn của một interface. Cùng method interface được gọi tại nhiều bytecode sites có thể cho profiles khác nhau.

### 3.1. Minh họa guard-based speculative inlining

Giả sử mọi `evaluate` lúc đầu nhận `AddOne`:

```text
Bytecode:
  load op, value
  invokeinterface Operation.apply(I)I

Mã tối ưu MÔ HÌNH:
  if (receiver.type == AddOne) {
      return value + 1;         // inline AddOne.apply
  } else {
      uncommon_trap_or_slow_path(); // không được trả bừa value + 1
  }

Lần đầu gặp TimesTwo:
  fast-path guard không đúng
  → fallback/deopt phải đảm bảo trả TimesTwo.apply(value)
```

Đây là **pseudocode diễn giải chiến lược**, không phải Java source/assembly thực tế của một bản HotSpot. C2 có thể chọn slow path thay cho uncommon trap hoặc không speculate tại site đó; có thể inline cả hai targets nếu profile/heuristics thích hợp.

### 3.2. `final` và `sealed` có bảo đảm không deopt?

Không. Một `final class` không thể bị subclass theo Java rules, có thể làm một số phân tích type dễ hơn. Nhưng một method gọi virtual có thể vẫn nhận những object classes khác nhau cùng triển khai interface, hoặc compilation phụ thuộc những assumptions khác. `sealed` giới hạn direct permitted subclasses theo ngôn ngữ nhưng không tự biến mọi dynamic call thành monomorphic.

Compiler có thể chứng minh target call statically hoặc dùng speculation tùy thông tin; không suy “method trong final class luôn inline” hay “sealed class thì chắc chắn không có deoptimization”.

## 4. Nhánh hiếm (uncommon branch) và uncommon trap

Một method thường xuyên gọi với số dương:

```java
static int normalize(int n) {
    if (n < 0) {
        return -n;
    }
    return n + 1;
}
```

Nếu trong thời gian dài chỉ xuất hiện `n >= 0`, JIT có thể tối ưu cho nhánh chính và giảm gánh nặng của nhánh âm. Một chiến lược HotSpot C2 là **uncommon trap**: khi nhánh/điều kiện ít gặp được kích hoạt, compiler cho JVM chuyển từ optimized code sang runtime path có thể thực hiện lại logic bytecode đúng.

**Điểm quan trọng:** có `if` và dữ liệu chủ yếu dương **không đảm bảo** C2 sẽ tạo uncommon trap. Compiler có thể sinh hai nhánh máy bình thường, dùng conditional move, hoặc tối ưu theo cách khác. Đây là ví dụ **tình huống có khả năng** tạo speculation, không phải hứa về trace của mọi JVM.

### 4.1. Guard failure không nhất thiết là lỗi ứng dụng

Một guard kiểm tra receiver type không đúng không đồng nghĩa `ClassCastException` trong Java source. Đó có thể là tín hiệu **JIT-generated code cần quay về phiên bản tổng quát hơn**.

```text
Fast path giả định: n >= 0
                   │
                   ├─ true  → optimized calculation
                   │
                   └─ false → uncommon trap / general fallback
                               │
                               ▼
                        Java negative branch
                        chạy đúng kết quả
```

Với `normalize(-7)`, kết quả phù hợp Java semantics là `7` (vì `-(-7)==7`), dù method trước đó được biên dịch tối ưu cho các số dương. Deoptimization là **cơ chế giữ correctness**, không có nghĩa application phải catch một Java exception tên “DeoptimizationException”.

### 4.2. Deoptimization synchronous và asynchronous

Hai trường hợp thường được phân biệt trong HotSpot discussions:

- **Synchronous deoptimization:** execution thực sự tới một guard/uncommon path và yêu cầu runtime hỗ trợ deopt. Việc kích hoạt gắn với đang thực thi compiled code.
- **Asynchronous invalidation/deoptimization:** một sự kiện từ thread khác, ví dụ class loading làm hỏng dependency về class hierarchy, khiến compiled method không còn được dùng và active frames phải được xử lý theo cơ chế VM.

“Asynchronous” ở đây không có nghĩa arbitrary instruction có thể bị thay đổi vô điều kiện; JVM phối hợp các điểm an toàn, dependency tracking và metadata để chuyển trạng thái hợp lệ. Tài liệu chi tiết là **HotSpot implementation**, không phải public method `Thread.deoptimize()`.

## 5. Class Hierarchy Analysis (CHA) và assumption bị vô hiệu hóa

C2 có thể quan sát ở thời điểm compile rằng một interface/abstract method chỉ có một receiver target khả dĩ trong hierarchy đã được nạp/liên kết, hoặc target phù hợp đã được xác định bằng profile. Nó có thể tận dụng điều này để inline và giảm virtual dispatch.

Một dependency dựa trên **tập classes hiện có** có thể không còn đúng sau khi JVM nạp thêm class hợp lệ.

```text
Ban đầu:
  interface Formatter
      └── PlainFormatter

C2 có thể chuyên biệt call formatter.format(...) cho PlainFormatter
khi profile/hierarchy cho phép.

Sau đó:
  interface Formatter
      ├── PlainFormatter
      └── HtmlFormatter       (mới được nạp/liên kết)

Nếu assumptions phụ thuộc unique target không còn đúng:
  JVM invalidates/deoptimizes compiled code liên quan.
  Call tiếp theo thực hiện đúng dispatch theo runtime type.
```

**Không khẳng định** mọi class load đều khiến toàn JVM deopt. JVM theo dõi **dependencies cụ thể**, và chỉ những nmethods có assumptions bị ảnh hưởng mới cần xử lý thích hợp. Nếu compiled code vốn có guard và slow path xử lý type mới, nó có thể vẫn hợp lệ.

### 5.1. Ví dụ hierarchy không có nghĩa nạp class là exception

Các class được nạp qua class loaders, reflection hoặc quá trình chạy bình thường. Class loading hợp lệ không khiến Java program phải thất bại chỉ vì JIT từng thấy ít type hơn. Correct implementation giữ phép `invokevirtual`/`invokeinterface` đúng theo ngữ nghĩa bytecode.

Các lỗi `NoClassDefFoundError`, `LinkageError` hoặc `ClassCastException` nếu xảy ra có **nguyên nhân ngôn ngữ/linkage thực**, không phải “JIT thấy class mới nên ném exception”.

### 5.2. Recompilation sau khi hierarchy thay đổi

Sau invalidation, HotSpot có thể:

1. Ngừng cho phiên bản nmethod cũ nhận thêm lời gọi (`not entrant`).
2. Xử lý các compiled frames đang active theo quy tắc deoptimization.
3. Tiếp tục interpreter hoặc code thích hợp.
4. Thu thập profile mới với class A và B.
5. Khi method vẫn đủ “hot” và compiler policy cho phép, biên dịch lại; phiên bản mới có thể chứa **hai guarded targets** hoặc generic dispatch.

Recompile **không nhất thiết diễn ra ngay tại thời điểm class được nạp**. Có các queues, thresholds, compiler threads, profiling heuristics và những giới hạn như code cache.

## 6. Deoptimization thực chất là gì?

**Deoptimization** là quá trình rời thực thi compiled code đang dựa trên assumptions/optimization state và khôi phục một **execution state phù hợp để tiếp tục Java semantics**. Điều này khác hoàn toàn với:

- Garbage collector thu hồi object không còn reachable.
- Java code ném `RuntimeException`.
- JVM dừng hẳn process.
- Build system chạy lại `javac`.
- HotSpot chỉ đơn giản “xóa cache CPU”.

Một compiled frame tối ưu có thể **không có cấu trúc 1–1** với các interpreter frames trong Java source. Compiler có thể:

- Inline nhiều Java methods vào một machine frame.
- Giữ local values trong registers thay vì stack slots như trong bytecode interpreter model.
- Loại bỏ những trung gian chưa escape hoặc biểu diễn objects theo dạng scalarized/virtual.
- Thực hiện loop transformations hoặc hoisting hợp lệ.
- Xóa hay kết hợp những checks trong vùng có assumptions được guard.

Khi deopt, JVM phải dựng lại những **logical frames**, local variables, operand stack values và object states cần thiết cho correct resumption. HotSpot lưu metadata/debug information tại những điểm có thể deopt để phục vụ quá trình này.

### 6.1. On-stack replacement và deoptimization không đồng nghĩa

**OSR (On-Stack Replacement)** cho phép một loop đang được interpreter thực thi chuyển sang compiled code **trong khi loop chưa kết thúc**, thay vì chỉ chờ lần gọi method kế tiếp.

```text
Interpreter bắt đầu một loop chạy rất lâu
      │ backedge counter / hotness
      ▼
JIT sinh OSR nmethod tương thích
      │
      ▼
runtime chuyển execution sang optimized loop body

Deoptimization:
optimized execution → interpreter/fallback
khi giả định không còn phù hợp hoặc theo VM policy
```

OSR là một hướng chuyển **sang compiled execution**, deopt là cơ chế thoát khỏi optimization state. Chúng có thể cùng xuất hiện trong đời sống của một loop/method nhưng không phải một thao tác ngược nhau hoàn toàn ở mọi chi tiết.

### 6.2. Inline stack frames được tái tạo như thế nào?

Giả sử C2 đã inline:

```text
Java source call stack:
  main()
    → service()
       → validate()
          → compute()

JIT optimized:
  một compiled frame chứa code inlined của
  service(), validate(), compute()
```

Khi deopt, VM cần có thể khôi phục những logical frames liên quan để exception handling, bytecode execution và stack traces tiếp tục đúng semantics. Việc inline không được làm mất thông tin Java cần quan sát trong trường hợp fallback hợp lệ.

Đây là một trong các lý do **deoptimization có chi phí**: cần chuyển control, unpack/reconstruct frames, đôi khi materialize data đã được compiler tối ưu bỏ đi.

### 6.3. Escape analysis và materialization

Một object tưởng như được tạo với `new` có thể bị JIT **scalar replace** nếu compiler chứng minh nó không escape khỏi phạm vi phù hợp, và các field được giữ như scalar values thay vì một heap allocation độc lập.

```java
record Point(int x, int y) {}

static int compute() {
    Point p = new Point(2, 3);
    return p.x() + p.y();
}
```

Đây là **snippet minh họa**. Compiler có thể tối ưu `p` đi khi an toàn; nó không bảo đảm loại bỏ trong mọi build/config. Nếu deoptimization/Java state cần object tương đương, VM phải đảm bảo semantics thông qua metadata và materialization thích hợp.

Không quan sát `new` trong bytecode rồi suy mỗi lần Java source `new` tạo một allocation trên heap đã được GC nhìn thấy. Tương tự, không khẳng định mọi object scalar-replaced đều sẽ materialize ở mọi deopt: chỉ khi trạng thái thực thi/quan sát yêu cầu.

## 7. Uncommon trap, invalidation và `nmethod` lifecycle

Ba thuật ngữ thường bị trộn:

| Thuật ngữ | Ý nghĩa khái niệm | Điều không nên suy ra |
| --- | --- | --- |
| **Uncommon trap** | Nhánh/check hiếm kích hoạt VM path có thể gây deoptimization | Không đồng nghĩa Java exception |
| **Deoptimization** | Chuyển một active optimized execution sang trạng thái có thể tiếp tục đúng | Không bắt buộc nmethod bị xóa ngay |
| **Invalidation / made not entrant** | Phiên bản compiled code không còn được chọn làm entrypoint cho calls mới | Không có nghĩa mọi active frame hoặc memory được xóa tức thì |
| **Recompilation** | Compiler tạo code mới theo profile/assumptions mới | Không đảm bảo diễn ra ngay sau mỗi deopt |
| **Code cache reclamation** | VM thu dọn compiled code không còn sử dụng theo lifecycle | Không phải GC reclaim Java object heap |

Trong output `-XX:+PrintCompilation`, có thể thấy trạng thái liên quan compiled methods như `made not entrant` hoặc `made zombie`, tùy HotSpot build/runtime event. Chúng **không phải một dấu hiệu 1–1** chứng minh đúng loại uncommon trap nào đã xảy ra; có nhiều lý do khiến compiled code bị thay thế/không còn được dùng.

### 7.1. Có phải deopt là “trở lại interpreter từ đầu method”?

Không. Deoptimization phải tiếp tục **đúng vị trí và trạng thái ngữ nghĩa thích hợp**, không được tự ý chạy lại side effects từ đầu method. Nếu method đã ghi file, cập nhật database, hoặc tăng counter, deopt không thể tùy tiện làm lại chúng chỉ vì runtime cần đổi implementation.

Một **uncommon trap** có thể dẫn tới việc reexecute một bytecode tại điểm được chọn, nhưng việc đó phải phù hợp với JVM state và chỉ những thao tác được cho phép reexecute an toàn. Không suy “deopt chạy lại cả function” từ từ “reexecute” trong tài liệu thấp cấp của HotSpot.

### 7.2. Java exceptions khác trap nội bộ

Khi Java source đáng lẽ ném `NullPointerException`, `ArrayIndexOutOfBoundsException`, `ClassCastException` hay `ArithmeticException`, compiled execution phải giữ hành vi Java tương đương.

HotSpot có thể:

- Sinh explicit machine check và throw đúng exception.
- Sử dụng một implicit hardware fault an toàn theo runtime contract.
- Đưa một path hiếm về interpreter qua deoptimization để interpreter thực thi exception semantics.

Những lựa chọn này là implementation details; **không nên đọc “uncommon trap” trong compiler log như một exception đã bị chương trình bỏ qua**.

## 8. Vì sao recompilation không phải lúc nào cũng tốt?

Một hot method có thể trải qua các trạng thái:

```text
interpreter → profiled C1 → optimized C2
                   │             │
                   │             ├─ trap/invalidated → fallback
                   │             │                       │
                   │             │                       ▼
                   │             └──────────► new profile/recompile
                   │                                     │
                   └──────────────────────► optimized code khác
```

JIT compilation tiêu tốn CPU, memory và code cache. Deoptimization thường có chi phí **chuyển execution + reconstruct state** và có thể mất lợi ích của compiled code trong một khoảng thời gian. Nếu chương trình liên tục đổi type distributions, compiler có thể “đánh đổi” giữa nhiều versions mà không thấy một profile ổn định.

HotSpot có các policy để hạn chế tối ưu lại vô tận một điểm liên tục gây traps; một số paths có thể được xem là không phù hợp để speculate nữa hoặc compiler sẽ phát sinh code tổng quát hơn.

**Không** cho rằng mỗi nmethod invalidation là một lỗi JVM. Trong dynamic workloads, thay đổi tối ưu là phần bình thường của runtime adaptive compilation.

### 8.1. Profile pollution và warm-up

Một service warm-up với 99% requests từ data type A có thể dẫn JIT chọn fast path A. Sau khi rollout, production traffic chứa tỷ lệ đáng kể type B/C, và code có thể deopt, recompile hoặc chuyển sang generic dispatch.

Điều này lý giải:

- Vì sao microbenchmark với một type duy nhất có thể lạc quan.
- Vì sao A/B testing workload distribution ảnh hưởng latency.
- Vì sao performance “đang nhanh rồi đột nhiên chậm” đôi khi do class loading, profiles hoặc invalidation.
- Vì sao không nên định nghĩa performance regression chỉ từ 100 ms đầu hoặc một vài requests.

Warm-up nên phản ánh **độ đa dạng receiver types và branch outcomes** của production, không chỉ số iterations.

### 8.2. Tiered compilation không phải các mức cố định theo từng giây

HotSpot tiered compilation ở cấu hình phổ biến gồm:

- **Interpreter (level 0)**.
- Các mức **C1** khác nhau có hoặc không có profiling đầy đủ.
- **C2 optimized compilation** (thường level 4 trong tiered design).

Compiler policy quyết định transitions theo hotness, compiler availability, code size, profiles và các heuristics. Không có hợp đồng “sau đúng 10.000 lần gọi thì C2 compile” hoặc “sau 2 giây JIT bật” xuyên mọi JVM/build.

`-XX:-TieredCompilation` thay chính sách compilation, không phải “tắt mọi JIT”. Để chạy hầu hết code bytecode bằng interpreter và bỏ JIT cho thí nghiệm, HotSpot hỗ trợ `-Xint`; hiệu năng có thể giảm rất mạnh.

## 9. Trình tự một lần assumption thất bại

Một timeline hợp lý:

1. Interpreter/C1 quan sát `Operation.apply` nhận `AddOne` hầu hết các lần.
2. C2 dùng profile để phát sinh fast path và có thể inline `AddOne.apply`.
3. Runtime bắt đầu nhận `TimesTwo` ở cùng call site.
4. Một guard fail hoặc compiler dependency bị vô hiệu, tùy cấu trúc code thực.
5. Nếu đường đã compile không xử lý trực tiếp được trường hợp mới, HotSpot có thể deopt, reconstruct frames/state và tiếp tục logic đúng.
6. C2 nmethod cũ có thể không còn entrant nếu policy thấy assumptions không hợp lệ.
7. Profiling có thể phản ánh thêm type `TimesTwo`.
8. Nếu method vẫn hot, JIT có thể compile phiên bản mới: type checks cho cả hai, virtual dispatch, hoặc chiến lược khác.
9. Mọi request vẫn phải nhận **cùng kết quả ngữ nghĩa Java** với execution không được tối ưu.

```text
Time
  │
  ├─ profile A A A A A A A ...
  │
  ├─ compile specialized code for A
  │
  ├─ call with B
  │    └─ type guard fails
  │          └─ deopt / fallback if needed
  │
  ├─ profile A and B ...
  │
  ├─ potential recompile for A+B / generic path
  │
  └─ continue same Java semantics
```

Đó là một **kịch bản được phép xảy ra**, không phải chuỗi 9 events bắt buộc và đồng bộ do JVM “phải” in ra ở mỗi lần chạy.

## 10. Java 17 thực hành: làm nóng một type rồi đổi sang type khác

File độc lập **`SpeculationDemo.java`**:

```java
public class SpeculationDemo {
    interface Operation {
        int apply(int value);
    }

    static final class AddOne implements Operation {
        @Override
        public int apply(int value) {
            return value + 1;
        }
    }

    static final class TimesTwo implements Operation {
        @Override
        public int apply(int value) {
            return value * 2;
        }
    }

    // Call site này có thể nhận nhiều receiver types.
    static int evaluate(Operation op, int value) {
        return op.apply(value);
    }

    public static void main(String[] args) {
        Operation first = new AddOne();
        Operation second = new TimesTwo();

        long phaseOne = 0;
        for (int i = 0; i < 100_000; i++) {
            phaseOne += evaluate(first, i);
        }

        long phaseTwo = 0;
        for (int i = 0; i < 1_000; i++) {
            phaseTwo += evaluate(second, i);
        }

        System.out.println("phaseOne=" + phaseOne);
        System.out.println("phaseTwo=" + phaseTwo);
        System.out.println("semanticsOK=" +
                (phaseOne == 5_000_050_000L && phaseTwo == 999_000L));
    }
}
```

Biên dịch:

```bash
javac --release 17 SpeculationDemo.java
```

Chạy bình thường:

```bash
java SpeculationDemo
```

**Stdout của chương trình Java (không bật JIT diagnostic output):**

```text
phaseOne=5000050000
phaseTwo=999000
semanticsOK=true
```

**Giải thích kết quả:**

- Phase one tính tổng `1+2+...+100000 = 5_000_050_000` trong biến `long`, tránh tràn `int` ở tổng.
- Phase two tính tổng `2×0+2×1+...+2×999 = 999_000`.
- `evaluate` là call site có thể monomorphic trong phase one rồi nhận type thứ hai ở phase two.
- Kết quả **Java-level** phải giống nhau dù `evaluate` được interpreter, C1 hay C2 thực thi.

**Giới hạn thí nghiệm:** Không đảm bảo có `deoptimization` chỉ vì đổi `Operation` từ AddOne sang TimesTwo. Compiler có thể dự đoán sớm, xử lý đa hình bằng slow path, inline cả hai, không compile kịp trước phase two, hoặc tối ưu loops/call sites theo cách khác. Muốn khẳng định một trap cụ thể đã xảy ra phải có **diagnostic evidence** từ đúng phiên chạy.

### 10.1. Chạy với interpreter để đối chiếu semantics

```bash
java -Xint SpeculationDemo
```

Chạy `-Xint` trên HotSpot khiến thực thi bytecode thông thường dựa vào interpreter thay vì JIT compiled application methods. **Stdout vẫn đúng ba dòng ở trên**, nhưng thời gian chạy có thể khác lớn.

Không dùng chênh lệch thời gian của **một lần chạy** với vòng lặp nhỏ để kết luận “JIT tăng tốc X lần”: overhead startup, interpreter/JIT policy và các tối ưu biến thiên; dùng JMH hoặc benchmark có thiết kế tốt nếu mục tiêu là đo microperformance.

### 10.2. Không nhầm output chẩn đoán với stdout nghiệp vụ

Khi bật `PrintCompilation`, JVM có thể in nhiều dòng compiler events trước/giữa các dòng ứng dụng. Đừng coi log số compilation events là stdout cố định của class `SpeculationDemo`.

## 11. Java 17 thực hành thứ hai: nhánh hiếm phải vẫn đúng

Tạo file **`RareBranchDemo.java`**:

```java
public class RareBranchDemo {
    static int normalize(int value) {
        if (value < 0) {
            return -value;
        }
        return value + 1;
    }

    public static void main(String[] args) {
        long checksum = 0;
        for (int i = 0; i < 100_000; i++) {
            checksum += normalize(i);
        }

        System.out.println("warmupSum=" + checksum);
        System.out.println("rareNegative=" + normalize(-7));
        System.out.println("nextPositive=" + normalize(10));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 RareBranchDemo.java
java RareBranchDemo
```

**Stdout chính xác:**

```text
warmupSum=5000050000
rareNegative=7
nextPositive=11
```

Kết quả của nhánh `-7` vẫn đúng bất kể C2 đã đoán “nhánh âm không bao giờ xảy ra” hay compiler vốn vẫn giữ code cho nhánh đó. Ví dụ chỉ thể hiện **correctness xuyên các execution paths**; nó không xác nhận số lần `uncommon_trap`.

**Cảnh báo biên của `int`:** `normalize(Integer.MIN_VALUE)` trả `Integer.MIN_VALUE` do Java `int` overflow theo two's complement semantics. Đây là behavior của Java, **không phải lỗi deoptimization**. Nếu nghiệp vụ cần trị tuyệt đối toán học của mọi `int`, phải thiết kế xử lý overflow bằng `long` hoặc `Math.negateExact` phù hợp.

## 12. Quan sát JIT bằng các cờ HotSpot Java 17

### 12.1. `-XX:+PrintCompilation`

```bash
java -XX:+PrintCompilation SpeculationDemo
```

Cờ này in thông tin mỗi khi HotSpot biên dịch method theo tài liệu `java` của JDK 17. Các dòng có thể chứa:

- Thời điểm tương đối.
- Compilation identifier.
- Compilation level (tùy tiered mode).
- Class và method.
- Trạng thái compiled nmethod (như made not entrant), tùy event.

**Không có một output cố định**. Nếu không thấy `evaluate`, chưa chắc code sai: VM có thể inline/optimize hoặc sample run kết thúc trước khi method được compile ở tier mong muốn.

### 12.2. Inlining decisions — cần diagnostic unlock

```bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+PrintCompilation -XX:+PrintInlining \
     SpeculationDemo
```

`PrintInlining` có thể giải thích vì sao compiler inline một method hoặc không (code too big, hotness, profile, call site...). Chú ý:

- Output của từng HotSpot build có thể khác.
- PrintInlining cho biết **quyết định compile**, không tự chứng minh có deopt khi type distribution đổi.
- Một method `final` vẫn có thể không inline vì compiler budgets/cost model.
- Method được inline có thể không xuất hiện dưới dạng một machine stack frame riêng ở optimized execution.

### 12.3. `LogCompilation` ghi thông tin chi tiết

Oracle JDK 17 hỗ trợ diagnostic compilation logging dạng XML, thường dùng để điều tra uncommon traps và compile decisions:

```bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+LogCompilation -XX:LogFile=jit-hotspot.xml \
     SpeculationDemo
```

File `jit-hotspot.xml` được ghi trong thư mục đang chạy khi JVM/runtime hỗ trợ. Phải đọc **XML/compiler log thực** trước khi kết luận:

- Có `uncommon_trap` hay không?
- Trap reason/bytecode index là gì?
- Method đã bị `made not entrant` theo sự kiện nào?
- Compiler có tạo lại code sau event hay không?
- Call site được tối ưu/inline theo những types nào?

**Quan trọng:** Tên trường, tags và reason/action codes là **HotSpot internals**, không phải stable public logging API. Một số flags chỉ hiện diện ở một số builds, diagnostic builds hoặc yêu cầu `-XX:+UnlockDiagnosticVMOptions`. Nếu JVM báo “Unrecognized VM option”, hãy kiểm tra vendor/release; **không tự bịa rằng mọi JVM luôn có một cờ `TraceDeoptimization` trong production build**.

### 12.4. So sánh interpreter, tiered và non-tiered

```bash
# Interpreter-oriented baseline:
java -Xint RareBranchDemo

# HotSpot tiered compilation mặc định ở các cấu hình phổ biến:
java RareBranchDemo

# Thay đổi compilation policy, KHÔNG phải tắt toàn JIT:
java -XX:-TieredCompilation RareBranchDemo
```

Ba lệnh có **cùng Java-level stdout** trong ví dụ. Nhưng không cần có cùng compiler events, code cache usage hay thời gian thực thi.

`-XX:-TieredCompilation` **không** tương đương `-Xint`: nó thay đổi chính sách tiering, và HotSpot vẫn có thể dùng JIT compiler.

### 12.5. Không dựa vào flag nội bộ làm API production

Tài liệu công khai của JDK 17 liệt kê `-XX:+PrintCompilation`, `-XX:+LogCompilation`, `-XX:+PrintInlining`, `-XX:+UnlockDiagnosticVMOptions`. Những cờ khác như `PrintOptoAssembly`, `TraceDeoptimization` hay instrumentation từ debug builds có khả năng phụ thuộc rất mạnh vào HotSpot flavor/platform. Chỉ dùng chúng khi đã xác nhận `java -XX:+PrintFlagsFinal -version`/build docs; một số flag sẽ không xuất hiện trong production JVM.

### 12.6. JFR và profile timeline

**Java Flight Recorder** hỗ trợ quan sát compilation activities và application runtime events theo những event types được cấu hình, qua JDK Mission Control hoặc tooling tương ứng. Nó hữu ích để liên hệ thời gian:

- Compiler warm-up/compilation queue.
- CPU pressure khi nhiều compiled tasks chạy.
- Request latency spikes.
- Class loading và safepoints.
- GC events, heap allocations, code cache và runtime behavior.

Không mặc định mỗi JFR recording đều chứa mọi deopt event hoặc chi tiết C2 speculation: event availability, settings và JVM build khác nhau. Để xem chi tiết một uncommon trap cụ thể, `LogCompilation`/compiler diagnostic metadata thường phù hợp hơn nếu HotSpot hỗ trợ.

## 13. Cần phân biệt “đã thấy compilation” và “đã thấy deoptimization”

| Quan sát | Kết luận được phép | Không thể kết luận chỉ từ đó |
| --- | --- | --- |
| `PrintCompilation` có tên method | JVM đã có compilation event cho method | Compiler chắc chắn speculative inline một receiver type |
| `PrintInlining` báo inline target | Compiler quyết định inline một call/target trong compilation | Lúc runtime đã xảy ra uncommon trap |
| Log có `made not entrant` | Một phiên bản nmethod không còn được dùng làm entrypoint bình thường | Tất cả active frames đã mất ngay hoặc chỉ có lý do type profile |
| Log có `uncommon_trap` reason/action | HotSpot ghi trap metadata/event theo reason tương ứng | Java code đã sai semantics hoặc cần ném exception cho caller |
| Không thấy traps trong một run | Run đó không có evidence traps theo mức logging | Chương trình không thể deopt trong tương lai |
| Runtime p99 chậm tăng sau rollout | Có performance change | Deopt chắc chắn là nguyên nhân duy nhất |
| `javap -c` có `invokeinterface` | Bytecode theo semantics có lời gọi interface | JIT không thể inline target vào machine code |

**`javap` quan sát bytecode**, còn compiled nmethod behavior cần compiler/runtime diagnostics. Java source không có từ khóa `deoptimize`, và một method Java không tự biết nó đang chạy bằng C1 hay C2 thông qua public Java API chuẩn.

## 14. Deoptimization có chi phí gì?

Các nguồn overhead có thể gồm:

- Chuyển từ compiled code sang runtime handler/fallback.
- Xác định vị trí bytecode cần tiếp tục và **reconstruct deoptimized frames**.
- Materialize objects hoặc undo/reconcile trạng thái scalarized khi cần.
- Thao tác invalidation/marking compiled code nếu dependency hết hợp lệ.
- Thu thập profile mới trong interpreter/C1.
- CPU và memory để JIT **compile lại**.
- Code cache footprint và công tác thu dọn obsolete nmethods.
- Mất hiệu quả của một số optimizations cho đến khi runtime có profile phù hợp.

**Một lần deopt không nhất thiết làm ứng dụng chậm đến mức đáng kể**. Việc chuyển execution có overhead, nhưng có thể tiết kiệm rất nhiều CPU trước đó nhờ fast path. Khi deopt xảy ra hiếm, tổng lợi ích vẫn dương.

Điều đáng điều tra là **liên tục deopt/recompile cùng điểm trong hot code**, profile không ổn định hoặc compiled code bị invalidated thường xuyên gây CPU spikes/tail latency.

### 14.1. Tại sao một benchmark có thể bị nhiễu bởi warm-up?

Microbenchmark chỉ chạy vài chục milliseconds có thể gồm cả:

- Class loading, bytecode verification và interpreter startup.
- JIT compilation chạy song song với work đang đo.
- Thay đổi tốc độ khi C1/C2 code trở thành active.
- OSR khi loop nóng.
- Deoptimization/recompilation khi thay data distribution.
- GC, CPU scheduling và thermal throttling.

Đó là lý do **JMH** thường được dùng cho Java microbenchmarks: framework hỗ trợ warm-up, forks, multiple iterations và tránh một số compiler pitfalls. Nhưng JMH cũng không thể thay workload production hay tự chứng minh deadline/latency SLO.

### 14.2. Profiling overhead và tier transitions

C1 code có instrumentation/profiling để cung cấp dữ liệu cho C2. Khi method đủ nóng, tiered policy có thể thay code profiled bằng code tối ưu hơn. Các transitions này không phải “đề bài bị compile lại vì compiler biết sai”; có thể chỉ là **lộ trình bình thường** tới performance tốt hơn.

Ngược lại, một C2 nmethod đã được tối ưu theo assumption cũ có thể bị invalidated, và code được biên dịch lại theo assumption khác. Chúng là **hai nguyên nhân khác nhau để có nhiều compilation events trên cùng method**.

## 15. Tình huống thực tế: service, plugin và đa hình

### 15.1. Service với nhiều triển khai chiến lược

Một ứng dụng dùng interface `PaymentStrategy`, ban đầu phần lớn calls thuộc `CardStrategy`. Sau khi thêm một plugin `WalletStrategy`, số lượng receiver types tăng. JIT có thể:

- Trước đó inline `CardStrategy`.
- Gặp type profile khác và deopt/fallback hoặc dùng polymorphic dispatch.
- Compile phiên bản phù hợp cho traffic mới.
- Giảm hoặc tăng throughput tùy inlining, code size, CPU caches và branch predictions.

Không phải việc load plugin **luôn** gây deopt. Chỉ những compiled dependencies/specializations có liên quan mới có rủi ro; code đã handle generic types thì có thể không phải thay đổi.

### 15.2. Workload thay đổi sau warm-up

Kịch bản:

```text
T0-T1  warm-up chỉ dữ liệu loại A
T1-T2  production traffic A + B + C
T2     p99 latency spike, compiler activity tăng
T3     throughput ổn định sau khi runtime thích ứng
```

Đây là **mô hình giả lập**. Để xác định nguyên nhân cần correlate:

- Compilation logs gần T2.
- Deopt/trap reasons nếu có.
- Class loading timeline và method code cache transitions.
- Request traces và CPU/GC metrics.
- Changes trong input mix (receiver types/branch distributions).

Không nên tắt toàn JIT chỉ để loại bỏ một spike rồi bỏ qua regression throughput dài hạn. Hãy đo và sửa nguyên nhân thay đổi data shape/inlining profile nếu thực sự quan trọng.

### 15.3. Proxy, reflection, lambda, dynamic languages

Dynamic proxies, nhiều call site adapters, lambdas và method handles có thể tạo hình thái dispatch khác với Java class call trực tiếp. JIT vẫn có nhiều cơ chế tối ưu, nhưng type profile hoặc hierarchy assumptions có thể phức tạp hơn.

Không kết luận “dùng reflection thì JIT không tối ưu gì” hoặc “interface calls luôn chậm hơn static calls”. Method handles, inlining và profile-guided optimizations có thể tạo kết quả khác trực giác. Benchmark đúng API path trên JDK đang chạy.

## 16. An toàn ngữ nghĩa: deopt không được làm sai chương trình

Ba invariant quan trọng:

1. **Giá trị trả về đúng:** `TimesTwo.apply(7)` phải cho `14` dù trước đó `evaluate` chỉ gặp `AddOne`.
2. **Side effects không bị chạy lại tùy ý:** nếu `counter++` hoặc `socket.write` đã xảy ra, deopt không được tự nhân đôi tác động.
3. **Java exceptions và synchronization vẫn đúng:** optimized code phải giữ contract về NPE, bounds checks, object monitors, happens-before và exception handlers theo JVM rules.

```java
static int compute(int value, java.util.concurrent.atomic.AtomicInteger c) {
    c.incrementAndGet();   // side effect quan sát được
    return value < 0 ? -value : value + 1;
}
```

Đây là **snippet minh họa**. Nếu method được JIT compile và deopt ở nhánh âm, Java logic vẫn phải ghi nhận `c.incrementAndGet()` đúng **một lần mỗi invocation**, không phải hai lần vì compiler phải quay về interpreter.

### 16.1. Tại sao deopt phức tạp hơn generic fallback?

Nếu compiler chỉ sinh hai code paths tổng quát đã guard, nó có thể xử lý type mới **ngay trong compiled code** mà không deopt. Nhưng khi C2 đã aggressively inline, scalar-replace và reorder hợp lệ, một nhánh hiếm có thể cần **đầy đủ interpreter state** để tiếp tục đúng. Deoptimization xử lý tình huống đó bằng cooperation giữa compiler metadata và runtime.

Vì vậy “guard failed ⇒ luôn deopt” cũng sai: một guard có thể dẫn tới compiled slow path thông thường. Chỉ khi compiler/runtime quyết định bỏ về đường thực thi tổng quát hơn mới có deopt theo nghĩa đang xét.

### 16.2. On-stack compiled frames và invalidation

Một method có nhiều active invocations trong các threads. Khi VM phát hiện dependency invalid:

- Không thể giả định bỏ tức thì mọi frames đang chạy trên tất cả threads.
- VM phải dùng mechanisms phù hợp để đảm bảo không frames nào tiếp tục thực hiện **sai assumption**.
- Nmethod có thể được đánh dấu **not entrant** cho calls mới.
- Những active frames cần deopt/invalidation có thể được xử lý tại các điểm VM hỗ trợ.
- Code cache reclaim chỉ xảy ra khi code không còn được sử dụng theo lifecycle.

Không được tự đồng nhất “class loader đã nạp class mới” với “GC đã thu hồi nmethod trong cùng millisecond”.

## 17. Gỡ lỗi hiệu năng khi thấy quá nhiều deopt

**Bước 1 — Xác nhận symptom.** Thu thập p95/p99 latency, throughput, CPU và compiler activity; phân biệt startup với steady state.

**Bước 2 — Ghi JDK và cờ.** Cố định `java -version`, vendor, architecture, tiered compilation policy, heap/code cache settings và CPU quota.

**Bước 3 — Quan sát compilation.** Bật `-XX:+PrintCompilation` ở môi trường thử nghiệm và kiểm tra methods nóng đang được compile nhiều lần.

**Bước 4 — Quan sát inlining.** Bật `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` để thấy nhận định compiler về targets và code size; output lớn nên log/tách file.

**Bước 5 — Lấy compiler logs nếu cần.** Dùng `-XX:+LogCompilation` trên HotSpot build hỗ trợ, đối chiếu uncommon trap reason, compile id, bci và not-entrant transitions.

**Bước 6 — Correlate event timeline.** Xem class load/unload, JFR/compiler activity, GC, safepoints và workload mix gần thời điểm latency spike.

**Bước 7 — Tách nguyên nhân.** Tier transitions bình thường, speculative guard failures, code cache pressure, class hierarchy invalidation hay benchmark noise khác nhau.

**Bước 8 — Benchmark có kiểm soát.** Dùng JMH hoặc representative load, warm-up có A/B/C types và các branch outcomes tương tự production.

**Bước 9 — Điều chỉnh tối thiểu có bằng chứng.** Ví dụ giảm pathological megamorphic call sites trong hot loops, ổn định dispatch data hoặc thay đổi cấu trúc pipeline; không tắt toàn inlining/JIT trừ khi có lý do đo đạc cụ thể.

**Bước 10 — Kiểm tra correctness.** Chạy unit/integration tests với interpreter và HotSpot flags phù hợp để chắc logic không vô tình phụ thuộc vào timing/profiling.

### 17.1. `made not entrant` không luôn là vấn đề lớn

Khi C1 profile code bị thay bằng C2 code tối ưu hơn trong tiered pipeline, một nmethod cũ có thể không còn entrypoint phù hợp. Trạng thái tương tự cũng có thể xuất hiện khi class hierarchy dependency invalid. Chỉ thấy chữ `not entrant` **không cho biết nguyên nhân chính xác**; cần phối hợp compile id, level và log events.

### 17.2. Tránh microbenchmark “tự đo JIT” sai cách

```java
long start = System.nanoTime();
for (int i = 0; i < 10_000; i++) {
    normalize(i);
}
System.out.println(System.nanoTime() - start);
```

Đây là **snippet phản mẫu** để học benchmarking. Nếu kết quả `normalize(i)` không được dùng, JIT có thể loại bỏ phép tính; 10.000 iterations có thể không đủ warm-up hoặc profile thay đổi, và `System.nanoTime` có overhead của nó. Không lấy kết quả một lần chạy rồi tuyên bố compiler đã hoặc chưa deopt.

## 18. Những nhầm lẫn thường gặp

1. **“JIT chỉ là chuyển bytecode sang machine code một lần.”** Sai. HotSpot adaptive profiling, tiering, optimization và có thể recompile.
2. **“JIT speculation đồng nghĩa chấp nhận kết quả sai khi giả định thất bại.”** Sai. Guard/dependency/deopt giữ Java semantics.
3. **“Một call site ban đầu monomorphic sẽ luôn monomorphic.”** Sai. Workload hoặc class loading có thể đổi type distribution.
4. **“Dùng interface chắc chắn không inline.”** Sai. Profiling và CHA có thể cho phép devirtualization/inlining.
5. **“Mọi lần truyền receiver type mới đều bắt buộc deopt.”** Sai. Compiler có thể đã có generic fallback, polymorphic inline hoặc chưa compile.
6. **“`final` class không bao giờ cần fallback.”** Sai. Có nhiều assumptions khác và interface call site vẫn có thể đa hình.
7. **“Deoptimization là Java exception.”** Sai. Đây là runtime/compiler mechanism.
8. **“Uncommon trap nghĩa JIT crash.”** Sai. Đây có thể là đường chuyển trạng thái an toàn cho nhánh hiếm.
9. **“Nếu JIT bỏ null check thì Java NPE biến mất.”** Sai. Optimized code vẫn phải bảo toàn semantics.
10. **“Deopt chạy lại từ đầu method, kể cả side effects.”** Sai. VM phục hồi state để tiếp tục đúng.
11. **“Inline 3 Java methods tạo 3 machine frames riêng.”** Không nhất thiết. Một compiled frame có thể chứa logical inlined scopes.
12. **“Sau deopt JVM không thể dựng lại objects bị scalar replacement.”** Sai. VM/compiler phối hợp metadata/materialization khi cần.
13. **“`made not entrant` = compiled code memory được thu hồi ngay.”** Sai. Nmethod lifecycle và active frames phải được xử lý.
14. **“Compilation event nào cũng do deoptimization.”** Sai. Tiered level upgrades/OSR cũng tạo compilations.
15. **“Một uncommon trap sẽ luôn tái biên dịch ngay.”** Sai. Runtime policy quyết định.
16. **“Một class mới được load khiến toàn bộ JIT code invalid.”** Sai. Chỉ dependencies liên quan.
17. **“OSR chính là deoptimization.”** Sai. OSR cho phép vào compiled code ở loop, deopt thoát code tối ưu.
18. **“`-XX:-TieredCompilation` tắt mọi JIT.”** Sai. `-Xint` mới là chế độ interpreter-oriented.
19. **“`PrintCompilation` luôn báo chính xác trap reason.”** Sai. Cần diagnostics sâu hơn.
20. **“`javap -c` in mã máy đã JIT compile.”** Sai. Nó in Java bytecode.
21. **“Không thấy traps trong một lần chạy chứng minh sẽ không bao giờ deopt.”** Sai. Tùy profile/JDK/cấu hình và logging.
22. **“Performance tốt trong warm-up một type đại diện production đa type.”** Không nhất thiết.
23. **“JIT compile là GC thu gom code cũ.”** Sai. Code cache management khác Java heap GC.
24. **“Đổi interface implementation luôn làm source phải build lại.”** Sai. Java dynamic dispatch và runtime/JIT hỗ trợ type khác.
25. **“JIT có quyền thay đổi kết quả `System.identityHashCode` sau deopt.”** Không theo Java semantics của object identity.
26. **“Tăng `-Xmx` bảo đảm giảm mọi deopt.”** Sai. Heap GC memory và JIT assumptions/profiles khác nhau.
27. **“Tăng số compiler threads vô hạn sẽ tăng throughput.”** Sai. CPU/cache/memory và compilation policy có trade-offs.
28. **“`-XX:+LogCompilation` là Java Language Specification API.”** Sai. HotSpot diagnostic interface riêng.
29. **“Khi JIT inline thì stack trace Java không còn hiển thị được logical methods.”** Sai. VM có scope metadata để support Java behavior tại điểm thích hợp.
30. **“Speculation là lỗi tối ưu.”** Không. Nó là một kỹ thuật có chủ đích, với cost/correctness trade-offs.

## 19. Tự kiểm tra và đáp án

**Câu 1.** Compiler profile thấy receiver luôn là `AddOne`. Tại sao không được giả sử mọi lời gọi tương lai đều là `AddOne` mà không có safeguard?

**Đáp án:** Một receiver `TimesTwo` có thể xuất hiện hợp lệ sau này. Guard/valid dependency hoặc generic fallback bảo đảm correct dynamic dispatch.

**Câu 2.** Nếu speculative guard fails, người dùng Java có phải catch `DeoptimizationException` không?

**Đáp án:** Không. Deopt là HotSpot runtime mechanism, không phải checked/unchecked Java exception công khai.

**Câu 3.** Deopt có thể trở lại đúng giữa một method đang chạy thay vì chạy lại method từ đầu không?

**Đáp án:** Có. JVM/compiler metadata phục vụ reconstruction và resumption tại trạng thái/ngữ nghĩa thích hợp.

**Câu 4.** Tại sao JIT cần metadata cho inlined methods?

**Đáp án:** Một compiled frame có thể chứa nhiều logical Java scopes; khi deopt/exception/stack walking cần dựng lại scopes và values đúng.

**Câu 5.** Tại sao `made not entrant` không có nghĩa method đã bị compiler xóa tất cả active frames?

**Đáp án:** Nó là trạng thái entrypoint/lifecycle của một compiled nmethod; active frames cần được xử lý riêng an toàn trước reclaim.

**Câu 6.** `-XX:-TieredCompilation` có bằng `-Xint` không?

**Đáp án:** Không. Non-tiered vẫn có thể JIT compile; `-Xint` chủ yếu dùng interpreter cho thí nghiệm.

**Câu 7.** `SpeculationDemo` in `phaseTwo` bằng bao nhiêu?

**Đáp án:** **999000**, là tổng `2×i` với `i=0..999`.

**Câu 8.** Thấy `-XX:+PrintInlining` báo một target inline. Điều đó đã chứng minh deopt khi B xuất hiện chưa?

**Đáp án:** Chưa. Cần actual trap/deopt evidence; code có thể có guard + generic fallback.

**Câu 9.** Class loading có thể invalid compiled CHA assumption không?

**Đáp án:** Có nếu dependency tương ứng bị ảnh hưởng; không phải bất kỳ class load nào đều invalid mọi nmethod.

**Câu 10.** Tại sao compiler có thể materialize object sau escape-analysis-based scalar replacement khi deopt?

**Đáp án:** Java-level state yêu cầu object tương đương còn được quan sát/sử dụng sau khi trở về interpreter; compiler lưu metadata phục vụ reconstruction.

**Câu 11.** Nếu JIT bị deopt, liệu kết quả phép tính phải đổi so với `-Xint` không?

**Đáp án:** Không. Với code hợp lệ, interpreter và optimized code phải giữ Java semantics.

**Câu 12.** Vì sao thí nghiệm `RareBranchDemo` không đảm bảo uncommon trap?

**Đáp án:** C2 có thể không compile kịp hoặc sinh nhánh compiled bình thường; type/branch speculation là lựa chọn heuristic, không là nghĩa vụ.

**Câu 13.** Khi benchmark hot method đa hình, nên warm-up với loại input nào?

**Đáp án:** Với phân phối types/branch outcomes đại diện workload thật, tránh warm-up chỉ một type rồi suy ra hiệu năng production.

**Câu 14.** Có nên xem một lần `made not entrant` trên startup là memory leak không?

**Đáp án:** Không. Đây thường là biến đổi hợp lệ của compiled code lifecycle; xem mức độ lặp, code cache/CPU và event reasons trước.

## 20. Tổng kết bằng bản đồ cơ chế

```text
           Java bytecode / interpreter
                      │
                      ▼
             Runtime profiling
          receiver types, branches,
           invocations, backedges
                      │
                      ▼
              C1/C2 compiler
                      │
               speculative code
                      │
       ┌──────────────┴────────────────┐
       │                               │
   Assumption OK                  Assumption FAIL
       │                               │
       ▼                               ▼
   Optimized fast path        guard fails / invalid dependency
                                       │
                              ┌────────┴─────────┐
                              │                  │
                          compiled           DEOPTIMIZE
                          slow path          reconstruct state
                              │                  │
                              │                  ▼
                              │           interpreter / fallback
                              │                  │
                              │           new profiles/heat
                              │                  │
                              │           possible recompile
                              │                  │
                              └────────┬─────────┘
                                       ▼
                            SAME JAVA SEMANTICS

Trong mọi nhánh:
  - return values đúng
  - exceptions đúng
  - side effects đúng
  - object identity đúng
```

**Ghi nhớ:** JIT tối ưu dựa trên **profile và assumptions**, vì biết những đường chạy thường gặp có thể nhanh hơn generic bytecode execution. HotSpot duy trì **guards và class-dependency checks** để không chạy sai khi thế giới thay đổi. **Deoptimization** phục hồi Java execution state từ compiled/inlined/scalarized representation và cho phép tiếp tục đúng bằng interpreter/fallback; runtime có thể reprofile và **compile lại**, nhưng không bắt buộc sau mỗi trap. Khi tìm vấn đề hiệu năng, hãy xem **compile levels, inlining, actual uncommon traps, class loading, code-cache events và workload input mix** thay vì đoán chỉ từ kết quả một lần chạy.

### Tài liệu tham khảo

- [Oracle JDK 17 — `java` command / JIT flags](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `PrintCompilation`, `PrintInlining`, `LogCompilation`, `TieredCompilation`, `Xint`.
- [OpenJDK HotSpot Wiki — Compiler](https://wiki.openjdk.org/display/HotSpot/Compiler): overview optimizing compilers và HotSpot internals.
- [OpenJDK HotSpot Wiki — Deoptimization](https://wiki.openjdk.org/display/HotSpot/Deoptimization): khái niệm deoptimization trong HotSpot.
- [Red Hat Developer — How JIT Compiler Boosts Java Performance](https://developers.redhat.com/articles/2021/06/23/how-jit-compiler-boosts-java-performance-openjdk): type profiles, speculation, traps và class hierarchy invalidation.
- [Red Hat Developer — Runtime Profiling in OpenJDK's HotSpot JVM](https://developers.redhat.com/articles/2021/11/18/runtime-profiling-openjdks-hotspot-jvm): branch/type profiling phục vụ C2 speculation.
- [JVMS Java SE 17 — `invokevirtual` và `invokeinterface`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): bytecode invocation semantics mà JIT phải giữ.
- [Java SE 17 — `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): xem bytecode/class file, không phải JIT native code.
