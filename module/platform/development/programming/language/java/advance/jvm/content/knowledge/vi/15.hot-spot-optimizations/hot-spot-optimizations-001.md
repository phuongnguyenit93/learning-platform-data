# Chèn thân phương thức (inlining) và mở rộng phạm vi phân tích trong HotSpot

## 1. Inlining giải quyết vấn đề gì?

Java khuyến khích tách chương trình thành nhiều methods nhỏ để code rõ ràng, tái sử dụng được và dễ kiểm thử:

~~~java
static int twice(int value) {
    return value * 2;
}

static int plusOne(int value) {
    return value + 1;
}

static int pipeline(int value) {
    return plusOne(twice(value));
}
~~~

Ba methods trên là **đoạn minh họa cần nằm trong một class**. Ở mức source, `pipeline` gọi hai methods. Ở mức bytecode, `javac` thường vẫn sinh các lệnh `invokestatic`. Nhưng khi HotSpot JIT compile một caller hot, nó có thể **chèn logic của callee vào intermediate representation (IR) của caller** ngay tại call site: đó là **method inlining**.

Một cách hình dung:

~~~text
Trước inlining (mô hình):
  pipeline(x)
      |
      +--> twice(x)     : 2*x
      |
      +--> plusOne(...) : +1

Sau khi JIT inline vào IR của pipeline (mô hình):
  result = 2*x + 1
~~~

**Inlining không chỉnh sửa source Java và cũng không nhất thiết chỉnh sửa file `.class` trên đĩa.** Nó là quyết định của compiler tại runtime khi tạo **native compiled code**. Bytecode gốc vẫn có thể chứa lời gọi methods.

**Hai lợi ích chính:**

1. **Giảm overhead của lời gọi:** bớt các bước call/return, setup arguments và đường chuyển giao control khi compiler thực sự loại lời gọi.
2. **Mở rộng phạm vi phân tích:** compiler nhìn thấy code ở **hai phía của method boundary** trong cùng IR, nên có thể thực hiện constant propagation, dead-code elimination, value/range analysis, escape analysis, scalar replacement, devirtualization và các tối ưu khác vượt qua ranh giới methods.

**Lợi ích thứ hai thường quan trọng hơn lợi ích “tiết kiệm một lệnh call”.** Trong nhiều chương trình, một method nhỏ chỉ có vài bytecode; việc chèn nó vào caller có thể mở ra phép tối ưu mạnh hơn nhiều so với chi phí invocation ban đầu.

### Một cảnh báo từ đầu

HotSpot **không bảo đảm inline mọi method**, kể cả `private`, `static`, `final` hoặc method chỉ có một dòng. Quyết định phụ thuộc compiler tier, bytecode size, call-site frequency, recursion, call depth, profile types, compilation graph budget và constraints khác.

## 2. Các tầng cần phân biệt: source, bytecode, IR, machine code

| Tầng | Điều thể hiện | Có bị thay đổi khi JIT inline? |
| --- | --- | --- |
| **Java source** | `pipeline` gọi `twice` và `plusOne` | Không; source giữ nguyên |
| **Class-file bytecode** | `invokestatic`, `invokevirtual`, `invokeinterface`… | Không nhất thiết; `javap -c` vẫn thấy calls |
| **Compiler IR / call graph** | Nodes cho calls, operations, types, control flow | **Có thể**: callee body được mở vào caller graph |
| **Compiled native code** | Instructions CPU đã tối ưu | Có thể không còn lời gọi riêng tại site ấy |
| **Runtime semantics** | Kết quả, exceptions, synchronization, type safety | **Phải được bảo toàn** |

Không lấy kết quả `javap -c` để kết luận “JIT chưa inline”: `javap` đọc class file, không disassemble native nmethods của JVM hiện đang chạy. Muốn biết quyết định HotSpot cần xem **`-XX:+PrintInlining`** hoặc các công cụ compiler/JIT phù hợp.

### “Chèn thân phương thức” không phải sao chép text Java

JIT không đơn giản copy đoạn source giữa hai dấu ngoặc. Nó phân tích **bytecode/IR và context tại call site**, tạo IR tương đương, ánh xạ arguments/receiver và locals, nối control-flow edges, return values, exceptions và những hiệu ứng liên quan.

Ví dụ, inlining hai methods có thể mang ý nghĩa:

~~~text
IR caller:
    parameter x
    call twice(x)
    call plusOne(result)

Inline twice:
    v1 = x * 2

Inline plusOne:
    v2 = v1 + 1

Further optimization:
    v2 = x * 2 + 1
~~~

Đây là **sơ đồ IR giả định**, không phải dump chính xác từ C2 hoặc tên nodes trong OpenJDK. Compiler thật còn quản lý safepoints, GC maps, debug state, memory effects, alias information và speculative guards.

## 3. Call site quan trọng hơn tên method

Inlining thường là **quyết định tại một call site cụ thể trong một compilation**.

Ví dụ:

~~~java
static int helper(int value) {
    return value * 5;
}

static int hotCaller(int x) {
    return helper(x) + 1;
}

static int coldCaller(int x) {
    return helper(x) - 1;
}
~~~

Đây là các methods minh họa. JIT có thể inline `helper` ở **`hotCaller`** vì profile cho thấy call site rất hot, nhưng không inline nó trong **`coldCaller`** vì method lạnh, budget khác hoặc chưa được compile. Cũng có thể chọn compile cả hai hoặc không compile một method nào.

**Không nói “method `helper` đã được đánh dấu inline trên toàn JVM”.** Cùng một callee có thể được inline vào nhiều callers, một số call sites vẫn giữ call, và những lần recompile sau có quyết định khác. Các log `PrintInlining` gắn với compilation của caller và chuỗi inlining tree cụ thể.

### Inlining và dynamic dispatch

Một lời gọi `invokestatic` có target rõ ràng theo bytecode/linking; `invokevirtual` và `invokeinterface` thường cần runtime method selection theo receiver type. Nhưng compiler vẫn có thể inline virtual calls khi có đủ chứng cứ đúng đắn, ví dụ:

- Declared target là effectively single implementation phù hợp.
- Type profile của call site chủ yếu thấy một concrete class.
- Class hierarchy analysis (CHA) cho biết tại thời điểm compilation một hướng call khả dụng.
- Compiler thêm **type guard** hoặc dependency để xử lý khi assumption không còn đúng.

**Java interface không tự ngăn inlining.** Và **`final` không bắt buộc đảm bảo inline**: biết target chỉ loại một trở ngại, còn budgets/size/profitability vẫn phải xét.

## 4. Mở rộng phạm vi phân tích: điều cốt lõi

Một optimizer chỉ thấy caller có thể phải bảo thủ về hành vi của callee: method có thể đọc/ghi field, throw exception, escape reference, gọi method khác hoặc có side effects.

Nếu inlining đưa body callee vào cùng IR, compiler có thể phân tích các thao tác **nối tiếp qua nhiều methods**, làm lộ ra các quan hệ mà trước đó bị che bởi call boundary.

### 4.1. Constant propagation qua method

~~~java
static int square(int x) {
    return x * x;
}

static int compute() {
    return square(7) + 3;
}
~~~

Đoạn methods minh họa.

~~~text
Trước mở rộng:
  call square(7) -> kết quả chưa rõ trong caller IR

Sau inline (mô hình):
  (7 * 7) + 3

Constant folding có thể tạo:
  52
~~~

**`compute()` trả 52** theo Java semantics. Inlining giúp compiler thấy argument là constant ngay trong body của `square`. Compiler đôi khi vẫn có thể suy luận kết quả bằng kỹ thuật khác mà không inline, nên không được diễn đạt “chỉ inlining mới có thể constant-fold”.

### 4.2. Dead-code elimination và branch simplification

~~~java
static int choose(boolean enabled, int value) {
    return enabled ? value * 2 : value * 3;
}

static int fastPath(int input) {
    return choose(true, input);
}
~~~

Nếu inline `choose(true, input)`, điều kiện `enabled` đã biết, compiler có thể chỉ giữ nhánh `input * 2`, thay vì giữ cả hai nhánh. Điều này giảm code/runtime work và mở ra tối ưu cho những operations kế tiếp.

**Không suy** rằng một branch có side effects có thể bị loại nếu điều kiện vẫn có thể chọn nhánh đó ở runtime. Optimizer phải chứng minh đường bị loại không thể chạy trong context compiled.

### 4.3. Range check elimination

~~~java
static int readFirst(int[] numbers) {
    return numbers[0];
}

static int readKnownLength() {
    int[] data = new int[] {4, 8, 12};
    return readFirst(data);
}
~~~

Trong context này, sau khi inlining `readFirst`, compiler có thể thấy array length và index 0 đã biết, cho phép loại **bounds check không cần thiết** nếu chứng minh an toàn. Null checks cũng chỉ bị bỏ khi có chứng cứ object non-null hoặc được bảo vệ bằng guard hợp lệ.

**Không bảo đảm** JIT luôn loại cả allocation lẫn mọi checks trong ví dụ; compiler tier, profile, deoptimization requirements và điều kiện implementation quyết định.

### 4.4. Loop optimization

Giả sử một loop gọi helper nhỏ ở mỗi vòng. Inline helper có thể cho optimizer nhìn thấy arithmetic/field reads trong cùng loop body để thực hiện:

- hoisting một phép tính bất biến ra ngoài loop;
- common-subexpression elimination;
- strength reduction;
- loop unrolling hoặc vectorization **nếu hợp lệ và được hỗ trợ**.

Inlining **không phải điều kiện đủ** để loop tự động được vectorize. Memory aliasing, data dependencies, exceptions và architecture constraints vẫn có thể ngăn tối ưu.

## 5. Escape analysis và scalar replacement qua call boundary

Đây là ví dụ nổi bật về lý do inlining quan trọng.

~~~java
static final class Pair {
    final int left;
    final int right;

    Pair(int left, int right) {
        this.left = left;
        this.right = right;
    }
}

static int score(Pair pair) {
    return pair.left * 2 + pair.right;
}

static int makeScore(int base) {
    Pair pair = new Pair(base, base + 1);
    return score(pair);
}
~~~

Đoạn này minh họa các declarations trong cùng class.

Nếu compiler nhìn `makeScore` mà không hiểu effects của `score`, nó có thể phải giả định `pair` được dùng theo một cách đòi object tồn tại. Sau inlining `score` (và những phần liên quan), compiler thấy `Pair` chỉ được đọc fields trong scope đã biết; **escape analysis** có thể xác định không cần materialize object trên heap.

~~~text
Before inline (mô hình):
  p = new Pair(base, base+1)
  result = call score(p)
  return result

After inline:
  p = new Pair(base, base+1)
  result = p.left*2 + p.right
  return result

After scalar replacement nếu đủ điều kiện:
  left = base
  right = base+1
  return left*2 + right

Further simplify:
  return base*3 + 1
~~~

Trên HotSpot C2, **scalar replacement** có thể loại heap allocation và những loads/stores đối với fields; không phải “chuyển mọi object không escape vào JVM stack”. Tài liệu Oracle HotSpot Performance Enhancements giải thích rõ hướng tiếp cận loại allocation và associated locks trong những điều kiện phù hợp.

**Không cam kết** chương trình nhỏ nêu trên chắc chắn được JIT compile hoặc scalar-replace ở lần chạy đầu. Với bytecode `new Pair` vẫn hiện diện trong `javap`, JIT có thể loại allocation **ở runtime compiled machine code**; ngược lại nếu object escape thật, VM phải giữ identity/visibility cần thiết.

### Lợi ích lan truyền qua nhiều methods

~~~text
Caller -> createPair() -> scorePair() -> normalize()

Nếu các lời gọi nhỏ cùng được inline:
  Compiler có thể nhìn graph tạo object -> đọc fields -> tính toán cuối.

Kết quả tiềm năng:
  constant propagation
  scalar replacement
  dead-store elimination
  elimination of redundant null/bounds checks
  register-based execution
~~~

Vì thế inlining **mở rộng biên giới phân tích liên thủ tục (interprocedural analysis)** trong một compilation. Cũng chính vì mở rộng IR mà nó có **chi phí**, buộc compiler dùng heuristics thay vì inline vô hạn.

## 6. Cơ chế speculative inlining với virtual/interface calls

Xem một call site dùng interface:

~~~java
interface Operation {
    int apply(int x);
}

static final class AddOne implements Operation {
    @Override public int apply(int x) { return x + 1; }
}

static final class MultiplyTwo implements Operation {
    @Override public int apply(int x) { return x * 2; }
}

static int execute(Operation operation, int value) {
    return operation.apply(value);
}
~~~

Các declarations trên là **minh họa**, không phải file Java độc lập.

Tại runtime, call site của `operation.apply` có thể:

- **Monomorphic**: gần như chỉ thấy một receiver type, chẳng hạn `AddOne`.
- **Bimorphic/polymorphic**: thấy hơn một receiver type với tần suất khác nhau.
- **Megamorphic**: thấy rất nhiều receiver types khiến inline một target cụ thể có thể không đem lại lợi ích.

HotSpot JIT có thể dùng **profile-based type guards** để inline target phổ biến:

~~~text
if (receiver matches AddOne):        // kiểm tra thực tế tùy compiler
    result = value + 1                // AddOne.apply inlined
else:
    result = genericVirtualDispatch(receiver, value)
~~~

Đây là sơ đồ **guarded inlining** khái niệm. VM có thể dùng deoptimization thay cho generic fallback hoặc nhiều guarded targets khác nhau, miễn giữ đúng Java dynamic-dispatch semantics.

### Nếu sau đó xuất hiện class mới?

Giả sử chương trình trước đây chỉ chạy với `AddOne`, sau đó class `MultiplyTwo` được nạp và một object mới được truyền vào call site. JVM **không được phép** trả `x+1` cho receiver `MultiplyTwo` chỉ vì đã inline `AddOne`. Nó phải:

- cho guard thất bại và dùng đường gọi đúng;
- hoặc **deoptimize** compiled code khi assumptions không còn đúng;
- hoặc áp dụng cơ chế invalidation/recompilation/virtual dispatch tương đương.

**Deoptimization không phải lỗi Java nghiệp vụ**. Nó là phần của adaptive optimization giúp compiled code không sai ngay cả khi profile trước đó trở nên không còn đại diện.

### Class Hierarchy Analysis (CHA)

CHA cho phép optimizer dùng thông tin class hierarchy đang được load/known để nhận ra một call site có target duy nhất. Nhưng với class loading động, giả định có thể mất hiệu lực khi subclass/implementation mới xuất hiện; HotSpot có dependency tracking và deoptimization phù hợp.

Không được kết luận `invokevirtual` luôn quá đắt để inline hoặc mọi lời gọi interface luôn phải tạo native indirect call.

## 7. C1 và C2 cùng có thể inline, nhưng khác budget/policy

HotSpot hỗ trợ **tiered compilation** theo những configurations thường gặp:

| Execution tier | Vai trò | Inlining |
| --- | --- | --- |
| Interpreter (level 0) | Chạy bytecode, tích lũy profiling | Không tạo JIT native code/inlining theo nghĩa compiler |
| C1 (levels 1–3 phổ biến) | Compile nhanh hơn, có các mức profiling | Có inlining với constraints/heuristics riêng |
| C2 (level 4 phổ biến) | Optimizing compiler, đầu tư sâu cho hot code | Có inlining sâu và liên kết nhiều global optimizations |

Không cần mọi method đi đủ 0→1→2→3→4. Một compilation của caller có thể inline callee ngay cả khi callee chưa được compile riêng; ngược lại callee đã compile thành nmethod không bắt buộc caller phải inline nó.

**Một call site có thể có quyết định khác ở các lần compile lại.** C1 và C2 có policies khác nhau; code nóng hơn, profile receiver types khác hoặc kích thước graph thay đổi có thể làm kết quả inlining thay đổi.

## 8. Vì sao HotSpot có thể từ chối inline?

Inlining giúp tối ưu nhưng cũng **tăng kích thước code tại call site**. Nếu caller gọi cùng callee ở nhiều nơi, inlining lặp lại có thể làm graph/machine code phình lớn.

Chi phí tiềm ẩn:

- **Compilation CPU/time:** IR nhiều nodes, optimizer xử lý lâu hơn.
- **Code cache pressure:** native machine code nhiều hơn, tốn bộ nhớ JVM process.
- **Instruction-cache locality:** code quá lớn làm CPU instruction cache kém hiệu quả.
- **Register pressure:** graph phức tạp có thể tăng spills/reloads.
- **Deoptimization metadata:** compiler cần lưu thông tin state/debug mappings để phục hồi execution đúng.
- **Recursion/call depth:** compiler phải có limits để không inline đệ quy vô hạn.
- **Exception/monitor/control-flow complexity:** body callee quá phức tạp có thể không đáng inline hoặc không hợp lệ với một optimization path cụ thể.

### Inlining budget và kích thước method

Oracle JDK 25 `java` manual mô tả các flags:

| Flag HotSpot | Ý nghĩa tổng quát | Lưu ý |
| --- | --- | --- |
| `-XX:+Inline` / `-XX:-Inline` | Bật/tắt method inlining | Flag theo HotSpot; thường bật mặc định |
| `-XX:MaxInlineSize=N` | C2: kích thước bytecode tối đa cho **cold method** được xem xét inline theo cơ chế liên quan | Không phải quy tắc duy nhất quyết định mọi inline |
| `-XX:FreqInlineSize=N` | C2: giới hạn size cho **hot method** | Có thể lớn hơn cold threshold |
| `-XX:InlineSmallCode=N` | C2: giới hạn code size của already-compiled callee trong một số điều kiện inline | Khác kích thước bytecode |
| `-XX:C1MaxInlineSize=N` | C1: kích thước cold method theo policy | Không áp nguyên C2 sang C1 |
| `-XX:MaxTrivialSize=N` | C2: giới hạn cho phương thức rất nhỏ/trivial | Không đồng nghĩa method luôn inline |
| `-XX:MaxNodeLimit=N` | Giới hạn nodes trong một single method compilation | Thay đổi có thể làm compile chậm và tăng memory use |

Các flags có thể thay đổi theo JVM release và không phải portable Java APIs. Những values trong manual là **defaults/examples cho version/configuration cụ thể**, không phải số luật học thuộc để áp mọi HotSpot instance.

### Những reason phổ biến trong `PrintInlining`

Log có thể diễn đạt những lý do như:

- `inline (hot)`: inline vì hot/profile phù hợp.
- `inline (hot)` sau virtual call analysis hoặc `accessor` trong những cases.
- `callee is too large`: callee quá lớn theo budget hiện tại.
- `hot method too big` hoặc các biểu thức tương tự: method hot nhưng vượt giới hạn.
- `already compiled into a big method`: compiled body lớn.
- `recursive inlining too deep`: giới hạn inline recursion.
- `virtual call` / target chưa đủ xác định: compiler có thể giữ dispatch.
- `not inlineable` hoặc những constraints khác: compiler không inline vì method/body policy.

**Các chuỗi reason trong log không được đảm bảo có format cố định qua mọi JDK.** Nhìn cả **inlining tree của caller và compile tier**; không đọc một dòng rời rồi kết luận mọi call sites đều giống nhau.

## 9. Runnable Java 17+: hai methods nhỏ được gọi trong hot loop

Tạo file **`InliningLab.java`**:

~~~java
public class InliningLab {
    private static volatile long result;

    static int twice(int x) {
        return x * 2;
    }

    static int plusOne(int x) {
        return x + 1;
    }

    static int pipeline(int x) {
        return plusOne(twice(x));
    }

    static long calculate(int iterations) {
        long total = 0;
        for (int i = 0; i < iterations; i++) {
            total += pipeline(i);
        }
        return total;
    }

    public static void main(String[] args) {
        result = calculate(100_000);
        System.out.println("total=" + result);
        System.out.println("single=" + pipeline(7));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -g InliningLab.java
java InliningLab
~~~

**Stdout chính xác trong execution bình thường, không bật diagnostics:**

~~~text
total=10000000000
single=15
~~~

Vì:

~~~text
pipeline(i) = 2*i + 1
sum(i=0..99999) = 2*(99999*100000/2) + 100000
                = 10,000,000,000
pipeline(7) = 2*7+1 = 15
~~~

`total` là `long` nên đủ sức chứa 10 tỷ; `twice(i)` là `int` nhưng `i < 100000` nên không overflow.

### Thử hai chiến lược runtime

Trên HotSpot hỗ trợ các flags:

~~~bash
java -Xint InliningLab
java -Xmixed InliningLab
java -XX:-Inline InliningLab
~~~

**Kết quả chương trình vẫn phải là hai dòng trên** khi chạy thành công. Trong `-Xint`, không có JIT compilation; `-XX:-Inline` điều chỉnh HotSpot JIT policy nhưng không đổi phương pháp gọi methods ở source và không phải cờ “chạy mọi thứ qua interpreter”.

Không thể dùng chênh lệch thời gian của ba lần chạy ngắn này để khẳng định inlining “tăng tốc N lần”. JVM startup, tiered warmup, loop OSR, compiler queues và OS scheduling đều nhiễu phép đo.

### So sánh `javap` với JIT

~~~bash
javap -c -p InliningLab
javap -v -p InliningLab
~~~

Trong `pipeline`, bạn thường thấy hai `invokestatic` gọi `twice`/`plusOne` ở class file. Sau khi HotSpot compiler inline ở runtime, native code có thể chứa arithmetic trong caller **mà không còn hai native calls tại call sites ấy**.

`javap` **không thể xác nhận** inlining đã hoặc chưa xảy ra ở execution thực tế, vì nó không hiển thị C1/C2 machine code.

## 10. Runnable Java 17+: mở rộng phạm vi giúp phân tích object

Tạo file **`ScopeExpansionDemo.java`**:

~~~java
public class ScopeExpansionDemo {
    static final class Pair {
        final int left;
        final int right;

        Pair(int left, int right) {
            this.left = left;
            this.right = right;
        }
    }

    static int score(Pair pair) {
        return pair.left * 2 + pair.right;
    }

    static int makeScore(int base) {
        Pair pair = new Pair(base, base + 1);
        return score(pair);
    }

    public static void main(String[] args) {
        long total = 0;
        for (int i = 0; i < 10_000; i++) {
            total += makeScore(i);
        }

        System.out.println("total=" + total);
        System.out.println("one=" + makeScore(7));
    }
}
~~~

~~~bash
javac -g ScopeExpansionDemo.java
java ScopeExpansionDemo
~~~

**Stdout chính xác:**

~~~text
total=149995000
one=22
~~~

Vì:

~~~text
makeScore(base) = 2*base + (base+1) = 3*base+1
sum(i=0..9999) = 3*(9999*10000/2)+10000
               = 149,995,000
makeScore(7) = 3*7+1 = 22
~~~

**Điểm cần học:** nếu HotSpot inline `score` và phân tích object `Pair` không escape, nó **có thể** scalar-replace Pair, bỏ allocation, field loads và một phần operations liên quan trong optimized machine code.

**Không suy** từ kết quả `149995000` rằng scalar replacement chắc chắn xảy ra. Chương trình ngắn có thể chạy interpreter/C1/C2 tùy workload và JIT thresholds. Output chỉ chứng minh Java semantics và đường tính toán.

Nếu muốn khảo sát inlining, có thể chạy chương trình với `PrintCompilation`/`PrintInlining` và quan sát compile của `makeScore`/`score`; nếu muốn chứng minh elimination of allocation, cần profiler/instrumentation phù hợp, JIT compilation state và đủ warmup.

## 11. Runnable Java 17+: virtual call và receiver profile

Tạo file **`ReceiverInliningDemo.java`**:

~~~java
public class ReceiverInliningDemo {
    interface Adjuster {
        int apply(int value);
    }

    static final class AddTwo implements Adjuster {
        public int apply(int value) {
            return value + 2;
        }
    }

    static final class TimesThree implements Adjuster {
        public int apply(int value) {
            return value * 3;
        }
    }

    static int call(Adjuster adjuster, int n) {
        return adjuster.apply(n);
    }

    public static void main(String[] args) {
        Adjuster common = new AddTwo();
        Adjuster other = new TimesThree();

        int sum = 0;
        for (int i = 0; i < 10_000; i++) {
            sum += call(common, 4);
        }

        System.out.println("common-sum=" + sum);
        System.out.println("other=" + call(other, 4));
    }
}
~~~

~~~bash
javac -g ReceiverInliningDemo.java
java ReceiverInliningDemo
~~~

**Stdout chính xác:**

~~~text
common-sum=60000
other=12
~~~

`AddTwo.apply(4)` trả 6, lặp 10.000 lần có tổng 60.000. `TimesThree.apply(4)` trả 12.

**Điều chương trình thể hiện:** một call site qua interface có thể gặp receiver types khác nhau và phải giữ đúng dynamic dispatch.

**Điều chương trình chưa chứng minh:** call site đã monomorphic-optimized, đã inline `AddTwo`, hay đã deopt khi gặp `TimesThree`. Một JVM có thể chưa compile method hoặc có compiled fallback; logs/compiled-code instrumentation mới giúp xác minh.

## 12. Quan sát HotSpot inlining trực tiếp

Theo Oracle JDK 25 `java` manual, bật diagnostics:

~~~bash
java -XX:+PrintCompilation InliningLab
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining -XX:+PrintCompilation InliningLab
~~~

Nếu method chưa đủ hot để compiler ghi sự kiện, **không có lời hứa** log `pipeline` hay `twice` sẽ xuất hiện. Có thể thử tăng workload/iterations trong môi trường test và bảo đảm đủ compilation time, nhưng đừng làm benchmark kết luận từ một run duy nhất.

### Nhìn inlining tree

Một log **minh họa hình thái**, không phải output bắt buộc:

~~~text
   @ 3   InliningLab::twice (4 bytes)   inline (hot)
   @ 6   InliningLab::plusOne (4 bytes) inline (hot)
~~~

Thông thường thụt lề thể hiện nested inlining, `@ BCI` thể hiện call site offset trong caller, còn lý do đi kèm cho biết compiler đánh giá như thế nào. Bytecode size số bytes ở ví dụ là **giả định minh họa**, không học thuộc; `javac` version và class contents có thể sinh số khác.

**Phải ghép log `PrintInlining` với compilation đang xét**: nếu một compiler đang compile `calculate`, tree có thể hiển thị `pipeline`, rồi `twice`/`plusOne` lồng bên trong. Đừng hiểu indentation như runtime Java call stack.

### Đọc lý do từ chối

Ví dụ dạng log giả định:

~~~text
@ 12  SomeClass::largeHelper (350 bytes) callee is too large
@ 21  SomeClass::virtualCall (20 bytes)  virtual call
@ 33  SomeClass::recursive (8 bytes)     recursive inlining too deep
~~~

Các reasons là gợi ý **vì sao một candidate cụ thể bị từ chối ở một call site**. Không có nghĩa method ấy “không thể inline trong mọi chương trình”.

### Log compilation có thể ghi ra file

Với HotSpot có diagnostic support:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation InliningLab
~~~

Thường VM ghi compilation XML/log vào file do `-XX:LogFile` chỉ định hoặc default theo phiên bản. Cách này hữu ích với công cụ phân tích inlining trees/JITWatch thích hợp; log có thể rất lớn, nên đừng bật liên tục trên production mà không quản lý retention/disk.

### Compiler Control (advanced)

Oracle JDK 25 VM Guide có **Compiler Control** cho phép áp directives tại mức method/pattern, gồm các chỉ thị inline hoặc không inline trong phạm vi áp dụng. Đây là công cụ nghiên cứu/diagnostics, **không phải cách mặc định tối ưu Java code ở production**.

Đừng viết code Java phụ thuộc vào một annotation “`@Inline`” giả định là public Java standard. HotSpot có những internal annotations/intrinsics, nhưng không phải API portable mà ứng dụng nên lấy làm hợp đồng ngôn ngữ.

## 13. Inlining và lựa chọn target: `static`, `private`, `final`, virtual, interface

| Loại lời gọi | Target thường rõ đến mức nào? | Còn yếu tố gì? |
| --- | --- | --- |
| `invokestatic` | Target được resolution xác định theo bytecode | Compiler budget, side effects, class-init/linking semantics |
| `invokespecial` | Calls constructor/private/super với semantics phù hợp | Method size, recursion, exceptions và costs |
| `invokevirtual` | Runtime selection theo receiver | Type profiles, class hierarchy, guards, fallback |
| `invokeinterface` | Runtime interface dispatch | Receiver types, devirtualization và guards |
| `invokedynamic` | Dynamically linked call site từ bootstrap | Call-site target stability, MethodHandle graphs, compiler rules |

**Đây không phải bảng “opcode nào được inline / opcode nào không được”.** Các dạng gọi có thể được compiler inline khi thỏa correctness và profitability. Sự khác biệt chính là thông tin chắc chắn về target và điều kiện bảo vệ giả định.

Một `final` method có thể dễ xác định target hơn, nhưng HotSpot vẫn có thể không inline nếu method quá lớn. Ngược lại một interface call có receiver type profile ổn định có thể inline rất hiệu quả.

**`@Override` không phải hint inline.** Annotation này cho compiler kiểm tra Java overriding correctness; không chỉ thị HotSpot phải inline.

## 14. Inlining không được phép thay đổi hành vi Java

Ví dụ:

~~~java
static int safelyDivide(int a, int b) {
    return a / b;
}

static int caller(int value) {
    return safelyDivide(value, 0);
}
~~~

Đây là method minh họa, không phải file độc lập. Nếu compiler inline `safelyDivide(value,0)`, **`ArithmeticException`** vẫn phải xảy ra khi đường code được chạy theo Java semantics. Compiler không được vì inlining mà âm thầm trả 0.

Những quy tắc khác cũng phải được bảo toàn:

- **Null checks:** dereference `null` phải tuân Java `NullPointerException` semantics khi thích hợp.
- **Array bounds:** access ngoài bounds vẫn phải phát sinh `ArrayIndexOutOfBoundsException`.
- **Class initialization/linkage:** compiler phải giữ các hành động và lỗi có thể quan sát đúng theo JVM specification.
- **`synchronized`/monitors:** chỉ được loại monitor operations khi có chứng minh tương đương theo Java Memory Model.
- **`volatile`:** không thể xóa tùy ý các memory ordering/visibility effects.
- **Exceptions và stack traces:** runtime có debug/scope metadata để phục hồi logical Java frames khi cần, kể cả khi native frame được inline.

### Stack traces và inlined frames

Một method có thể được inlined nhưng debugger/profiler vẫn hiển thị nó như một **logical Java frame**. JIT duy trì metadata để khôi phục bối cảnh lời gọi, exceptions và deoptimization. Do đó, **thấy method trong stack trace không chứng minh JIT không inline**.

Cũng đừng xem số lượng Java stack frames trong một profiler sample là số native call instructions thực tế sau inlining.

## 15. Inlining quá mức có thể làm chậm chương trình

Giả sử `BigHelper` dài và được gọi ở 20 call sites khác nhau. Nếu JIT copy logic của nó vào mọi callers:

~~~text
Caller1  +  Body(BigHelper)
Caller2  +  Body(BigHelper)
...
Caller20 +  Body(BigHelper)
~~~

Tổng native code size có thể tăng nhiều so với giữ shared nmethod và calls. Hệ quả:

- Code Cache nhanh đầy hơn.
- CPU instruction cache misses và iTLB pressure có thể tăng.
- Register allocation khó hơn, spills nhiều hơn.
- JIT compilation time và CPU sử dụng tăng.
- Deoptimization metadata phức tạp hơn.
- Startup/warmup latency có thể xấu đi.

Do vậy câu **“inline càng nhiều càng nhanh”** là sai. Một callee nhỏ được gọi cực nhiều thường là ứng viên tốt; một callee khổng lồ có nhiều nhánh lạnh có thể không đáng duplicate.

**Compiler heuristics là compromise thực dụng**, không phải lời hứa tối ưu toàn cục. Các flags `MaxInlineSize` và `FreqInlineSize` là công cụ tuning/diagnostics, không phải giá trị nên tăng tùy tiện.

## 16. Khác biệt giữa inlining và các tối ưu dễ nhầm

| Khái niệm | Bản chất | Có đồng nghĩa inlining? |
| --- | --- | --- |
| **Inlining** | Đưa IR/body callee vào call site của caller | Chính khái niệm đang học |
| **Devirtualization** | Chọn/giới hạn target của virtual call theo type info | Không; giúp mở đường inline nhưng có thể chỉ trực tiếp hóa lời gọi |
| **Tail-call optimization** | Biến tail call theo chiến lược khác | Không; Java/HotSpot không hứa general TCO cho mọi method |
| **Escape analysis** | Xác định object/reference có escape không | Không; inlining có thể mở rộng phân tích |
| **Scalar replacement** | Thay object bằng thành phần fields/value, loại allocation | Không; là tối ưu downstream |
| **Constant folding** | Tính trước biểu thức với constants | Không; inlining thường làm xuất hiện constants |
| **Intrinsic** | Compiler/runtime dùng implementation chuyên biệt cho một method/operation | Không đồng nghĩa JIT copy body bytecode |
| **Loop unrolling** | Lặp lại loop body trong compiled representation | Không; thao tác trên loop, có thể xảy ra sau inlining |
| **OSR** | Chuyển vào compiled loop khi method đang chạy | Không; OSR compilation có thể hoặc không inline callees |
| **AOT** | Chuẩn bị code trước runtime execution theo công nghệ cụ thể | Không; thời điểm biên dịch là khác |
| **`javac` optimization** | Các biến đổi của compiler Java source-to-bytecode | Không tương đương C2 inlining at runtime |

**Inlining thường mang tính “enabler”:** bản thân nó có thể giảm call overhead, nhưng điểm đáng giá là giúp compiler nhìn được những phép tối ưu vốn trước đó bị call boundary che khuất.

## 17. Cách điều tra nếu một method “không inline như mong đợi”

Một quy trình an toàn:

1. **Xác nhận method được compile:** dùng `-XX:+PrintCompilation` hoặc runtime profiler. Không thấy method trong log có thể vì method lạnh hoặc đã bị inline vào compilation của caller khác; cần phân tích đúng.
2. **Xác định caller và call site:** compiler quyết định theo từng site, không phải chỉ tên callee.
3. **Bật `PrintInlining` trong môi trường test:** đọc tree và reasons, phân biệt compile tier C1/C2.
4. **Kiểm tra profiles:** caller có hot không, receiver types mono/poly/mega, method invocation/backedge frequency?
5. **Kiểm tra code size/budget:** bytecode callee dài, graph phức tạp, recursion, inline depth, native code-size.
6. **Kiểm tra JIT state:** method đã warmup chưa, code cache có chật, compilation jobs có bị trì hoãn?
7. **Đo outcome quan trọng:** CPU cycles, throughput, P95/P99 latency, allocation/GC metrics, code cache, compilation time.
8. **Chỉ chỉnh flags khi có chứng cứ:** `-XX:-Inline` để so sánh có kiểm soát; thay size thresholds cần benchmark và kiểm chứng trên JDK/GC/workload thực.

**Không dùng một lần `System.nanoTime()` rồi kết luận inline cải thiện chính xác N%.** Startup, tiered compilation, OSR, dead-code elimination, constant folding, GC và OS scheduling đều ảnh hưởng. Dùng **JMH** cho microbenchmark với warmup/forks, và workload server thực để đo end-to-end impact.

## 18. Các ngộ nhận thường gặp

| Phát biểu | Điều đúng |
| --- | --- |
| “Inline là copy Java source vào method khác.” | JIT mở rộng **IR/body** khi compile, không rewrite source Java. |
| “`javap -c` không còn `invoke` nghĩa đã inline.” | `javap` đọc class-file bytecode; JIT inlining nằm ở runtime compiled code. |
| “`static` method chắc chắn được inline.” | Target rõ hơn nhưng vẫn có compiler budgets và profitability. |
| “`final` hoặc `private` là tín hiệu bắt buộc.” | Không. HotSpot không hứa inline các methods đó. |
| “Java interface call không bao giờ inline.” | Có thể profile-guided devirtualization và guarded inlining. |
| “Inlining chỉ tiết kiệm overhead một lời gọi.” | Nó còn mở phạm vi IR analysis, thường có lợi lớn. |
| “C1 không inline, chỉ C2 inline.” | C1 cũng có inlining policy. |
| “Mọi call site của một callee có cùng inlining decision.” | Quyết định thường per-call-site, per-compilation. |
| “Compile callee riêng xong thì caller buộc phải inline.” | Không. Compilation độc lập khác inlining tại caller. |
| “Sau inline, mọi checks/exceptions bị bỏ.” | Java semantics, guards, exceptions vẫn phải bảo toàn. |
| “JIT luôn cần thể hiện stack frame native riêng cho mỗi inlined method.” | Debug/deopt giữ logical frames, không buộc native call frame riêng. |
| “Có method trong stack trace chứng minh nó chưa inline.” | Không. JIT có thể tái dựng logical Java frames. |
| “Mọi non-escaping object được chuyển lên native stack.” | HotSpot có thể scalar-replace và **loại allocation**, không hứa stack allocation tổng quát. |
| “Tăng MaxInlineSize sẽ chắc chắn tăng throughput.” | Code growth/compile cost/cache pressure có thể làm chậm. |
| “Một caller được tối ưu thì không cần deoptimization nữa.” | Guard assumptions có thể bị invalidated. |
| “Inlining thay đổi nghĩa của synchronized/volatile.” | Compiler phải bảo toàn Java Memory Model. |
| “`-XX:-Inline` biến JVM thành interpreter-only.” | Nó tắt JIT method inlining theo HotSpot policy, không tắt JIT compilation. |
| “`PrintInlining` có output cố định ở mọi JDK.” | Compiler decisions/format tùy JDK, tier, profile và workload. |
| “Source chỉ có một dòng là method luôn trivial.” | Bytecode và side effects, intrinsic/VM behavior vẫn quan trọng. |
| “Chỉ cần một benchmark lạnh là biết inlining đáng giá.” | Phải phân biệt startup, warmup và steady-state. |

## 19. Tự kiểm tra có đáp án

**Câu 1.** Vì sao inlining có thể đem lại lợi ích ngoài việc giảm call overhead?  
**Đáp án:** Nó mở IR giữa caller và callee, cho constant propagation, dead-code elimination, range analysis, escape analysis và những tối ưu khác nhìn xuyên qua method boundary.

**Câu 2.** `private static int f(int)` chắc chắn inline không?  
**Đáp án:** Không. Target có thể rõ nhưng compiler xét hotness, code size, budget, depth và profitability.

**Câu 3.** `javap -c` vẫn thấy `invokestatic` sau khi chương trình từng chạy với JIT. Có chứng minh không inline không?  
**Đáp án:** Không. `javap` đọc class file gốc; JIT inlining tác động compiled IR/native code ở runtime.

**Câu 4.** Hai call sites gọi cùng callee có thể quyết định inline khác nhau không?  
**Đáp án:** Có, dựa trên caller context/profile/budget và compiler tier.

**Câu 5.** Vì sao inlining `score(Pair)` vào `makeScore` có thể giúp loại object allocation?  
**Đáp án:** Sau inlining compiler thấy Pair chỉ được đọc fields mà không escape, có thể áp dụng escape analysis và scalar replacement.

**Câu 6.** Một virtual/interface call có thể được inline không?  
**Đáp án:** Có, nhờ devirtualization/receiver type profiling, guards hoặc CHA khi hợp lệ.

**Câu 7.** Receiver type mới xuất hiện sau optimized compilation thì điều gì đảm bảo correctness?  
**Đáp án:** Runtime guards, generic fallback/deoptimization, dependency invalidation và recompile thích hợp.

**Câu 8.** Inlining C1 và C2 có giống hệt policy không?  
**Đáp án:** Không. Chúng có budgets, optimization goals và profiles khác nhau.

**Câu 9.** `-XX:FreqInlineSize` và `-XX:MaxInlineSize` khác nhau thế nào trong C2?  
**Đáp án:** Cờ đầu liên quan hot-method inline size limit; cờ sau là cold-method bytecode inline size limit trong policy được tài liệu hóa.

**Câu 10.** Vì sao inline một callee rất lớn vào 20 callers có thể làm chậm?  
**Đáp án:** Native code growth, instruction cache pressure, compile CPU/memory overhead và register spills.

**Câu 11.** `InliningLab` cho output nào?  
**Đáp án:** `total=10000000000` và `single=15` trong execution bình thường, bất kể decisions inline.

**Câu 12.** `ReceiverInliningDemo` có chứng minh deoptimization đã xảy ra không?  
**Đáp án:** Không. Output chỉ chứng minh đúng dynamic dispatch; compiler có thể chưa compile hoặc đã có fallback path.

**Câu 13.** Dùng công cụ nào để quan sát HotSpot inline decisions?  
**Đáp án:** `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining -XX:+PrintCompilation` trên HotSpot hỗ trợ.

**Câu 14.** JIT có thể bỏ exception trong method sau inline không?  
**Đáp án:** Không nếu exception vẫn có thể xảy ra theo Java semantics; chỉ được loại checks/paths chứng minh không cần.

## 20. Tài liệu chính thức

- [Oracle JDK 25 — `java` Command, Advanced JIT Compiler Options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:+Inline`, `-XX:-Inline`, `MaxInlineSize`, `FreqInlineSize`, `InlineSmallCode`, `C1MaxInlineSize`, `PrintCompilation` và `PrintInlining`.
- [Oracle JDK 25 — Java HotSpot Virtual Machine Performance Enhancements](https://docs.oracle.com/en/java/javase/25/vm/java-hotspot-virtual-machine-performance-enhancements.html): Tiered Compilation, Code Cache, escape analysis và scalar replacement.
- [Oracle JDK 25 — Java Virtual Machine Guide](https://docs.oracle.com/en/java/javase/25/vm/index.html): HotSpot/compiler technology, Compiler Control và performance.
- [JVMS Java SE 25 — Chapter 6, Instruction Set](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html): `invokestatic`, `invokevirtual`, `invokeinterface`, `invokespecial` và JVM bytecode semantics.
- [JVMS Java SE 25 — §4.7.3 Code Attribute](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3): code bytes của method và metadata cần cho execution.
- [OpenJDK HotSpot — C2 compiler source](https://github.com/openjdk/jdk/tree/master/src/hotspot/share/opto): compiler optimization and inlining implementation; nhánh master có thể khác phiên bản chạy thực.
- [OpenJDK HotSpot — C1 compiler source](https://github.com/openjdk/jdk/tree/master/src/hotspot/share/c1): C1 inlining and compiler policies.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): đo hiệu năng Java đáng tin hơn benchmark lạnh đơn lẻ.

**Ghi nhớ:** Inlining trong HotSpot **đưa code của callee vào phạm vi phân tích của caller tại một call site**, vừa có thể giảm invocation overhead, vừa mở đường cho **các tối ưu liên thủ tục** như constant propagation, escape analysis và scalar replacement. Nhưng inline quá mức có thể gây **code bloat**, tốn compilation time và làm cache locality xấu đi. HotSpot vì vậy dùng **profiling, C1/C2 heuristics, budgets, guards và deoptimization** để cân bằng lợi ích với chi phí mà vẫn giữ nguyên Java semantics.