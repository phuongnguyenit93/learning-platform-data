# Phân biệt loại bỏ cấp phát với giả định đối tượng luôn được chuyển lên stack

Khi đọc về **escape analysis (EA)** trong HotSpot JVM, ta thường gặp lời giải thích: “Nếu đối tượng không escape khỏi method, JVM sẽ chuyển nó từ heap lên stack”. Câu này **không mô tả chính xác tối ưu hóa của HotSpot C2 trong Java 17**. Escape analysis là quá trình **phân tích khả năng tham chiếu tới đối tượng thoát ra khỏi một phạm vi**. Khi chứng minh được đối tượng đủ điều kiện, C2 có thể áp dụng **scalar replacement**: thay các thao tác trên đối tượng bằng các giá trị thành phần, thậm chí **loại bỏ hoàn toàn thao tác cấp phát đối tượng**.

Nói cách khác:

- **Allocation elimination:** một object allocation mà source/bytecode biểu diễn có thể **không còn được thực hiện** trong machine code được tối ưu.
- **Scalar replacement:** các field của object có thể được xử lý dưới dạng scalars, compiler temporaries hoặc registers/stack slots theo nhu cầu của machine code. **Không bắt buộc tồn tại một object nguyên vẹn ở stack.**
- **Stack allocation:** một object có cấu trúc/identity được lưu trong stack frame thay vì Java heap. Đây là **một kỹ thuật khác**; tài liệu về escape analysis của HotSpot nêu rõ rằng C2 không đơn giản thực hiện stack allocation cho object chỉ vì không escape.
- **Thông thường**, nếu object thật sự vẫn phải được materialize/allocate, HotSpot vẫn quản lý nó trên **Java heap** theo đường cấp phát phù hợp, thường qua Eden/TLAB. Không có hợp đồng “mọi local object đều nằm trên stack”.

Bài thuộc mục **Tối ưu HotSpot**, sử dụng bối cảnh **HotSpot C2 trên Java 17**. Nội dung phân biệt khái niệm, điều kiện tối ưu, escape states, các giới hạn của compiler, deoptimization/materialization, tác động tới GC, cùng các ví dụ **Java 17 biên dịch/chạy được** và phương pháp đo mà không đưa ra kết luận từ phỏng đoán.

## 1. Bốn lớp cần phân biệt: source, bytecode, machine code và runtime allocation

```text
Java source:
    Pair p = new Pair(a, b);
    return p.left() + p.right();
                 │
                 ▼ javac
Class file bytecode:
    new Pair
    dup
    invokespecial Pair.<init>
    invokevirtual Pair.left ...
                 │
                 ▼ interpreter / C1 / C2
JIT optimized machine code (một khả năng):
    result = a + b
    [không cần new Pair, không cần object header]
                 │
                 ▼ runtime
    Không nhất thiết có heap object Pair tương ứng mỗi call.
    Không có nghĩa một Pair nguyên vẹn được đặt trên native stack.
```

**Source `new` không phải một cam kết tạo allocation có thể đo ở mỗi lần thực thi** sau khi JIT đã tối ưu. Nó biểu diễn semantics: tạo đối tượng mới với giá trị/identity phù hợp **nếu identity được quan sát**. Compiler có quyền làm một biến đổi nội bộ miễn Java behavior vẫn đúng.

**`javap -c` có `new` cũng không chứng minh runtime đã cấp phát object**: `javap` in bytecode, không in optimized machine code mà C2 sẽ sử dụng về sau.

### 1.1. Local variable là reference, không phải vị trí vật lý của object

```java
Object obj = new Object();
```

`obj` là biến local chứa **reference** về mặt Java semantics. Điều đó **không** chứng minh object đã được đặt trên JVM stack. Trong interpreter, local variables nằm trong **frame** của lời gọi method; reference có thể nằm trong local variable array. Trong compiled code, reference/giá trị có thể được giữ trong register, stack slot hoặc bị tối ưu đi.

**JVM stack frame** chứa execution state như locals, operand stack theo mô hình JVMS; **Java heap** là nơi quản lý phần lớn Java object allocations thực sự. Tránh dùng từ “biến local nằm trên stack” để suy ngược rằng “object mà biến trỏ tới cũng nằm trên stack”.

### 1.2. JVM stack và native stack không phải heap

Các thuật ngữ:

| Khái niệm | Chức năng | Điều không thể suy ra |
| --- | --- | --- |
| Local variable/reference | Giữ hoặc biểu diễn tham chiếu tới object | Object đích chắc chắn nằm cùng frame |
| Operand stack theo JVMS | Mô hình thao tác trung gian của bytecode | Mọi toán hạng đang nằm nguyên như vậy trong optimized machine code |
| Native thread stack | Bộ nhớ thực thi của native/JIT frames và registers spilled | HotSpot C2 sẽ chuyển mọi non-escaping object thành stack object |
| Java heap | Không gian quản lý Java object allocations | Mỗi từ khóa `new` luôn tạo một heap allocation sau JIT |
| TLAB | Vùng thread-local cấp phát nhanh từ heap | Một “thread stack” cho objects |
| Code Cache | Chứa compiled native machine code | Java heap chứa các object dữ liệu nghiệp vụ |

Từ **stack** bị dùng lẫn cho nhiều cơ chế, dẫn tới một hiểu nhầm cốt lõi: “reference/field scalar nằm trong stack slot” khác hoàn toàn “một object nguyên vẹn được stack-allocate”.

## 2. Escape analysis là điều kiện chứng minh, không phải chỉ nhìn biến local

HotSpot C2 phân tích **đường đi của reference trong phạm vi compiled graph** để quyết định object còn có thể được quan sát ở đâu. Một object tạo bên trong method vẫn có thể **escape** qua return value, static/shared field, JNI hoặc lời gọi mà compiler chưa chứng minh được; trái lại, `return new Pair(...)` vẫn có cơ hội được tối ưu nếu caller được inline và object không bị công bố ngoài graph.

Trong tài liệu HotSpot, các trạng thái thường được gọi là **NoEscape**, **ArgEscape**, **GlobalEscape**. Đây là phân loại **nội bộ của compiler**, không phải annotation hay thuộc tính trên Java object. `NoEscape` chỉ mở **khả năng** scalar replacement, không bảo đảm C2 loại được allocation; `ArgEscape` và `GlobalEscape` cũng cần xét cách call graph/alias/side effects thực sự được phân tích.

**Trọng tâm riêng của bài này:** một object *có thể không escape* vẫn không hề có quy tắc bắt buộc phải **được cấp phát trên native stack**. Để hiểu vì sao, phải xét cách C2 thay cả object bằng scalars và phân biệt ba kết quả: heap allocation, scalar replacement, stack object allocation.

## 3. Scalar replacement: bỏ biểu diễn object nguyên khối

Xét ví dụ trong một class có `Pair(int left, int right)` và hai field `int left, right`:

~~~java
static int sum(int a, int b) {
    Pair p = new Pair(a, b);
    return p.left + p.right;
}
~~~

Đây là **mảnh code**; cần định nghĩa `Pair` trước khi compile. Sau khi inline constructor và phân tích reference đủ mạnh, C2 **có thể** thay các thao tác trên object bằng `left=a`, `right=b` rồi chỉ còn `return a+b`. Khi đó **không cần heap allocation tương ứng mỗi lần gọi** trong optimized path, nhưng **cũng không có object `Pair` đầy đủ được chuyển lên stack**.

Giá trị scalars có thể ở register, spilled stack slot, hoặc constant-fold tiếp; vị trí vật lý không phải Java API contract. Phải phân biệt **escape analysis (điều kiện phân tích)**, **scalar replacement (thay object bằng các giá trị)**, **allocation elimination (không cấp phát object thực)** và **dead-code elimination (bỏ phần không ảnh hưởng hành vi)**. Một allocation không xuất hiện trong profile **không tự chứng minh** tối ưu nào gây ra việc đó.

Điều kiện và giới hạn thực tế của EA được phân tích chuyên sâu ở bài trước; phần tiếp theo của bài này tập trung trả lời vì sao **allocation biến mất ≠ stack allocation**.

## 4. Vì sao không được dạy “NoEscape object luôn lên stack”?

Nguồn nghiên cứu về **HotSpot Escape Analysis and Scalar Replacement Status** công khai chỉ ra: **HotSpot không thực hiện stack allocation** như một kết quả mặc định của escape analysis C2. Tài liệu Oracle về HotSpot performance cũng mô tả compiler **eliminates scalar-replaceable allocations** và **does not replace heap allocation with a stack allocation** cho non-global-escaping objects.

So sánh:

| Cơ chế | Object header đầy đủ? | Object còn có identity materialized? | Điều có thể diễn ra |
| --- | --- | --- | --- |
| Heap allocation thông thường | Có trong heap object | Có | `new` được thực thi theo đường VM cấp phát |
| Stack allocation đúng nghĩa | Có thể có representation object trong stack frame theo một VM khác | Có thể tồn tại trong frame | **Không phải lời mô tả mặc định về HotSpot C2/Java 17** |
| Scalar replacement / allocation elimination | **Không nhất thiết có object header** | Có thể chưa cần materialize | Các fields được thay thành scalars và allocation bị bỏ |
| TLAB fast allocation | **Có object thật trên heap** | Có | Cấp phát rẻ, nhưng không phải eliminated allocation |
| Escape nhưng field read optimized | Có thể vẫn có heap object | Có | Compiler vẫn có thể inline/copy-propagate một số fields dù object escape |

Giải thích chính xác hơn:

> “Nếu C2 chứng minh một allocation không escape và đủ điều kiện scalar replacement, nó **có thể loại allocation ấy**. Điều này không tương đương với việc **cấp phát cùng object trên thread stack**.”

### 4.1. Java specification có bắt buộc mọi object vật lý nằm heap không?

JVMS mô tả **heap là runtime data area dùng cấp phát cho class instances và arrays**, đồng thời cho phép implementation dùng các tối ưu không quan sát được miễn semantics được giữ. Developer không nên khẳng định “stack allocation mọi object” chỉ dựa trên quy tắc local variable. Với C2 hiện hành trong phạm vi bài, kỹ thuật đáng tập trung là **scalar replacement**, không phải stack object allocation.

Tranh luận “object có trên heap hay stack” cần xác định rõ **object runtime materialized có thực sự tồn tại không?** Nếu compiler xóa allocation và tính được kết quả bằng constants/scalars, câu hỏi “đối tượng nằm stack hay heap” có thể trở thành **câu hỏi sai tiền đề**.

## 5. TLAB: cấp phát trên heap có thể rất nhanh mà không cần stack

**TLAB (Thread-Local Allocation Buffer)** là cơ chế HotSpot tối ưu đường cấp phát **heap objects** bằng cách dành một vùng dung lượng thuộc Eden/young heap cho một thread thực hiện allocations nhanh. Khi đủ chỗ trong TLAB, một allocation thường gần với thao tác bump pointer, hạn chế lock chung.

```text
Java heap (ví dụ vùng Eden):
  ├─ TLAB của thread A ─► object1, object2, object3
  ├─ TLAB của thread B ─► object4, object5
  └─ vùng khác / allocation slow paths

Các TLAB ở trên vẫn nằm trong JAVA HEAP.
Không nằm trên native call stack của thread.
```

Do đó:

- “Object tạo quá nhanh, chắc nằm stack” là sai.
- Allocation còn diễn ra nhưng rẻ nhờ TLAB **khác** với allocation hoàn toàn bị loại.
- GC vẫn phải quản lý objects được tạo trong TLAB nếu chúng thật sự materialize trên heap.
- Khi JIT loại allocation, nó giảm work của cả allocator và GC theo cách khác TLAB optimization.

**Không phải mọi allocation đều đi qua TLAB**, ví dụ một số object lớn/slow paths hoặc compiler/collector behavior đặc biệt; điều này không làm TLAB trở thành một thế hệ GC riêng.

## 6. Khi nào đối tượng có thể escape?

### 6.1. Return reference khỏi method

```java
static Box makeBox(int value) {
    return new Box(value);
}
```

Ở ranh giới method source, return `Box` cho caller. Nếu caller có thể giữ, so identity hoặc truyền đối tượng đi xa, compiler thường cần materialized object. Tuy nhiên, **sau inlining**, JIT có thể nhìn thấy caller chỉ đọc field rồi bỏ reference; ở compiled region lớn hơn nó có thể vẫn loại allocation.

Không dùng “method trả object ⇒ tuyệt đối không thể scalarize” như một định luật xuyên toàn chương trình.

### 6.2. Lưu vào static field

```java
private static volatile Object shared;

static void publish(Box box) {
    shared = box;
}
```

Object được publish qua một field có thể truy cập từ code khác và thread khác. Khi assignment thực sự xảy ra và object có thể được quan sát, compiler phải bảo đảm Java memory model/object identity; không thể đơn giản xóa object mà làm mất observable reference.

`volatile` ở đây giúp mô hình công bố giữa threads rõ ràng hơn; nó **không** phải nguyên nhân duy nhất của escape. Một shared static field thông thường cũng có thể giữ object.

### 6.3. Đưa object vào container có vòng đời dài

```java
private static final java.util.List<Object> CACHE =
        new java.util.ArrayList<>();

static void remember(Object value) {
    CACHE.add(value);
}
```

Object lưu trong `CACHE` có strong path từ static collection. Nó có thể vượt qua lifetime của method tạo object và gây retained heap memory. Dù vậy JIT vẫn có thể loại các temporary objects khác trên đường chạy nếu chúng không escape.

### 6.4. Truyền vào method khác

```java
static int readValue(Box b) {
    return b.value;
}

static int caller(int n) {
    Box b = new Box(n);
    return readValue(b);
}
```

Truyền `b` làm argument **không tự chứng minh global escape**. Nếu C2 có thể inline `readValue`, thấy callee chỉ đọc field, và object graph đủ đơn giản, allocation có thể vẫn được loại.

Ngược lại, nếu callee là native method, reflective/dynamic call hoặc method quá lớn không được inline, compiler có thể không chứng minh được object không escape và phải materialize nó.

### 6.5. Ghi reference vào lambda/closure hoặc chuyển cho thread

Nếu một closure/lambda/task giữ reference và được lưu vào executor queue hoặc thread khác, đối tượng có thể sống lâu hơn method tạo nó. Tránh suy “lambda được khai báo trong method” nên toàn bộ captures nằm trên method stack.

Compiler có thể tối ưu những lambdas không escape trong tình huống đơn giản; nhưng các capture graphs cần phân tích chứ không thể kết luận theo hình thức source.

## 7. Không escape khỏi thread chưa đủ để loại allocation

Một object được giữ trong một `ThreadLocal`:

```java
static final ThreadLocal<Box> LOCAL = new ThreadLocal<>();

static void store(int v) {
    LOCAL.set(new Box(v));
}
```

**Thread confinement** có thể giúp lập luận về data races/locking, nhưng object vẫn có thể tồn tại sau khi `store()` kết thúc và được lấy lại từ `LOCAL.get()`. Nó **escape khỏi method** dù thông thường không được thread khác dùng.

Đây là một ví dụ điển hình: “không được thread khác chạm đến” **không** đồng nghĩa “nếu method kết thúc thì object không cần tồn tại”. Ngữ nghĩa của `ThreadLocal` đòi object identity/state tồn tại khi cần được truy xuất.

### 7.1. NoEscape, ArgEscape và GlobalEscape không phải public memory locations

Các escape classifications mô tả compiler biết gì về các references. Chúng **không** tự ánh xạ:

```text
NoEscape       ⇒ stack
ArgEscape      ⇒ survivor
GlobalEscape   ⇒ old
```

Cả ba mũi tên trên đều **sai**. Eden/Survivor/Old là **GC generations**, còn escape analysis là **compiler dataflow reasoning**. Một object GlobalEscape có thể cấp phát ở Eden rồi promoted; một NoEscape object có thể vẫn materialize trên heap nếu optimizer không thể hoặc không chọn scalar replacement.

## 8. Đánh đổi và giới hạn của scalar replacement

Một đối tượng “không escape theo trực giác” vẫn có thể không bị loại allocation vì:

- Compiler chưa compile method bằng C2, hoặc method chưa đủ “hot”.
- Đường gọi không được inline nên phạm vi phân tích bị giới hạn.
- Object graph phức tạp, aliasing nhiều hoặc control-flow merges khó phân tích.
- Arrays lớn, index access không biết tại compile time, hoặc số elements vượt giới hạn scalarization của JVM.
- Escape analysis/compiler budgets/timeouts/heuristics giới hạn work.
- Identity-sensitive operations và APIs yêu cầu materialized object.
- JVMTI/debugging/instrumentation, safepoints hoặc khả năng deopt cần giữ trạng thái phù hợp.
- Native/reflective calls có semantics khó chứng minh từ IR.
- Tối ưu bị tắt bằng flags hoặc JVM không dùng compiler hỗ trợ tương tự.

**Không phải mỗi mục trên là một blocker tuyệt đối trong mọi chương trình.** Một số field reads/aliases/calls vẫn được tối ưu nhờ inlining, constant folding và version-specific improvements.

### 8.1. Identity và `System.identityHashCode`

```java
Box a = new Box(7);
Box b = new Box(7);
boolean same = a == b;  // false đối với hai allocations quan sát độc lập
```

Nếu compiler tối ưu loại materialization, nó vẫn phải giữ `same == false` theo Java semantics. Việc không có heap allocation thực tế **không được làm đổi kết quả các phép so identity có thể quan sát**.

Gọi `System.identityHashCode(obj)`, dùng object monitor hoặc truyền object tới API có thể giữ reference có thể làm việc materialization cần thiết hoặc hạn chế scalar replacement. Nhưng không nói máy móc rằng “chỉ cần dùng `==` hoặc `synchronized` là mọi compiler bắt buộc tạo heap object” — một số comparisons/locks vẫn có thể được giải quyết hoặc loại bỏ khi chứng minh an toàn.

### 8.2. Arrays và scalar replacement

`new int[2]` trong một phép tính nhỏ có thể là ứng viên tối ưu khi kích thước/indices đủ rõ:

```java
static int sumTwo(int a, int b) {
    int[] values = {a, b};
    return values[0] + values[1];
}
```

Nhưng `new int[100_000]` với accesses động khác nhiều về khả năng scalarization và compiler costs. Tránh kết luận “mảng local luôn trên stack” hoặc “mảng không bao giờ scalarize”; kích thước, truy cập, aliasing và compiler version đều quan trọng.

### 8.3. Boxing, records và value-like temporary objects

`Integer` boxing, small immutable records và tiny holder objects là những ví dụ ứng viên tối ưu khi object identity không cần được quan sát. Nhưng:

- Autoboxing có thể dùng **cache** nên không nhất thiết tạo object mới ngay cả trước EA.
- Java 17 `record` vẫn là **reference class**, không phải primitive value type theo cách các dự án JVM giá trị tiên tiến từng đề xuất.
- `record Pair(int x, int y)` có thể là candidate cho scalar replacement, **không có hợp đồng record luôn unboxed**.
- Code size và polymorphism vẫn giới hạn khả năng JIT inline.

Không trộn scalar replacement với primitive specialties hay Project Valhalla proposals của các phiên bản/đề xuất khác.

## 9. Chương trình Java 17 đầy đủ: tạo object local và object escape

Lưu file **`EscapeAnalysisDemo.java`**:

```java
public class EscapeAnalysisDemo {
    record Pair(int left, int right) {}

    private static volatile Pair keepAlive;

    static long localSum(int n) {
        Pair pair = new Pair(n, n + 1);
        return (long) pair.left() + pair.right();
    }

    static Pair makePair(int n) {
        return new Pair(n, n + 1);
    }

    public static void main(String[] args) {
        long total = 0L;
        for (int i = 0; i < 100_000; i++) {
            total += localSum(i);
        }

        Pair retained = makePair(7);
        keepAlive = retained;

        Pair first = makePair(1);
        Pair second = makePair(1);

        System.out.println("sum=" + total);
        System.out.println("retainedValue=" +
                (retained.left() + retained.right()));
        System.out.println("distinctObjects=" + (first != second));
        System.out.println("sameRecordValue=" + first.equals(second));
    }
}
```

Biên dịch/chạy (JDK 17+):

```bash
javac --release 17 EscapeAnalysisDemo.java
java EscapeAnalysisDemo
```

**Stdout chính xác khi chương trình hoàn tất, không bật logging:**

```text
sum=10000000000
retainedValue=15
distinctObjects=true
sameRecordValue=true
```

**Giải thích:**

1. Mỗi iteration gọi `localSum(i)`, về semantics tạo `Pair(i, i+1)` rồi chỉ cộng hai field. Đây là ứng viên tốt cho **scalar replacement / allocation elimination** khi C2 tối ưu vùng code.
2. Tổng `2×i+1` với `i=0..99_999` là **100.000² = 10.000.000.000**, và được giữ bằng `long` để tránh overflow.
3. `makePair(7)` trả reference; `retained` được publish vào `static volatile keepAlive`, nên object có thể được code khác quan sát. Không thể tự suy lần gọi này được loại allocation.
4. `first` và `second` là hai allocations riêng. `first != second` là **true**, nhưng record `equals` so field contents nên `true`.
5. Java-level stdout giống nhau dù compiler dùng interpreter, C1 hay C2; **không có dòng nào cho biết allocation của `localSum` thật sự được eliminated trong lần chạy này**.

### 9.1. Kết quả khác nhau giữa source và runtime

`javap` vẫn có thể hiển thị:

```bash
javap -c -p EscapeAnalysisDemo
```

trong đó bytecode của `localSum` có `new` để tạo record object. Trong thời gian chạy, optimized code C2 **có thể** không thực hiện allocation ấy.

Vì thế **`javap -c` không chứng minh stack allocation, heap allocation hay scalar replacement runtime**. Nó chỉ là điểm đầu khi học bytecode và điều JVM có quyền tối ưu.

### 9.2. So sánh các chế độ thực thi mà không bịa stdout GC

```bash
# Bình thường: JVM tự profile và tier compile nếu phù hợp
java EscapeAnalysisDemo

# HotSpot interpreter-oriented, không dùng JIT compilation thông thường
java -Xint EscapeAnalysisDemo

# HotSpot JDK 17: tắt escape analysis
java -XX:-DoEscapeAnalysis EscapeAnalysisDemo
```

**Ba lệnh phải có cùng bốn dòng stdout Java-level** khi thực thi thành công. Nhưng runtime allocations, warm-up cost, GC activity và elapsed time có thể khác. `-Xint` có thể chậm hơn đáng kể; không dùng một lần chạy ngắn để tuyên bố hệ số tốc độ.

## 10. Chương trình thứ hai: escape qua field và qua return

Tạo file **`EscapePathsDemo.java`**:

```java
public class EscapePathsDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    private static volatile Box published;

    static int localOnly(int n) {
        Box b = new Box(n);
        b.value += 2;
        return b.value;
    }

    static Box returnsReference(int n) {
        return new Box(n);
    }

    static void publish(Box b) {
        published = b;
    }

    public static void main(String[] args) {
        System.out.println("local=" + localOnly(40));

        Box returned = returnsReference(5);
        System.out.println("returned=" + returned.value);

        Box first = new Box(9);
        publish(first);
        System.out.println("published=" + published.value);

        Box second = new Box(9);
        System.out.println("sameIdentity=" + (first == second));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 EscapePathsDemo.java
java EscapePathsDemo
```

**Stdout chính xác:**

```text
local=42
returned=5
published=9
sameIdentity=false
```

**Học được gì?**

- `localOnly` tạo `Box` chỉ dùng cho primitive result; có khả năng scalarize.
- `returnsReference` cho caller reference. Nếu JIT inline và thấy caller chỉ lấy field, **vẫn có trường hợp** compiler loại allocation ở vùng lớn hơn.
- `published` là một field chung, có thể được thread khác đọc; object đích cần tồn tại theo observable Java semantics.
- Hai lần `new Box(9)` tạo hai conceptual objects distinct. JIT không được biến `sameIdentity=false` thành true.
- Đây là **ví dụ phân tích đường escape**, không phải một tracer xác định physical allocation location.

### 10.1. Return object có phải lúc nào cũng GlobalEscape?

Tài liệu HotSpot mô tả return reference như ví dụ của **GlobalEscape** ở phạm vi analyzed method. Nhưng sau method inlining, compiler có thể biết caller không giữ reference ngoài phạm vi optimized region. Vì vậy cách diễn giải trong code review nên là:

> “Return reference là một **escape edge ở ranh giới method**, làm việc loại allocation phức tạp hơn; compiler có thể vẫn tối ưu nếu phân tích cả caller.”

Đừng đổi điều đó thành “return từ mọi method đều tạo permanent heap object” hoặc “nếu không có explicit return thì không thể escape qua field”.

## 11. Chương trình thứ ba: lock elimination không đồng nghĩa stack object

Một tác động khác của EA là **lock elimination**: nếu compiler có thể chứng minh lock trên một object không cần thiết để đồng bộ với thread khác và việc bỏ lock không làm sai observable semantics, nó có thể loại một số monitor enter/exit operations.

Tạo file **`LocalLockDemo.java`**:

```java
public class LocalLockDemo {
    static int calculate(int n) {
        Object guard = new Object();
        synchronized (guard) {
            return n + 1;
        }
    }

    public static void main(String[] args) {
        long total = 0L;
        for (int i = 0; i < 100_000; i++) {
            total += calculate(i);
        }
        System.out.println("total=" + total);
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 LocalLockDemo.java
java LocalLockDemo
```

**Stdout chính xác:**

```text
total=5000050000
```

`guard` được tạo để dùng bên trong `calculate`; vì code không công bố nó ra ngoài, compiler **có thể** chứng minh monitor operations không cần thiết và bỏ lock, thậm chí loại allocation. Nhưng:

- `synchronized` Java semantics không biến mất: nếu có exception/monitor-observable behavior, compiler phải giữ hành vi hợp lệ.
- Không khẳng định mọi local lock trong mọi JVM đều bị elide.
- Đây **không phải** bằng chứng `guard` đã được stack-allocate.
- Nếu thay `guard` bằng một shared lock field, việc bỏ mutual exclusion có thể không hợp lệ do thread khác cần đồng bộ.

**Lưu ý:** “lock elimination” khác với việc người viết code xóa từ khóa `synchronized`. Trong source, giữ synchronization cần thiết; JVM chỉ bỏ máy móc khi chứng minh hợp lệ.

## 12. Deoptimization: object bị scalarize có thể cần materialization

Một khó khăn lớn của scalar replacement là **JIT có thể cần deoptimize** và quay về interpreter khi một speculative assumption không còn đúng.

Giả sử:

```text
Java-level:
  Pair p = new Pair(3, 4);
  doSomething();
  use(p.left, p.right);

Optimized machine state:
  scalar_left = 3
  scalar_right = 4
  [không có physical Pair heap allocation]

Đột nhiên deoptimization ở một điểm cần resume interpreter:
  JVM dùng scope/debug info và virtual-object metadata
  để reconstruct Java-level frames, locals, operand stack
  và materialize Pair object nếu thực sự cần identity/reference.

Sau materialization nếu cần:
  có thể tồn tại heap object Pair để Java code tiếp tục đúng.
```

Điều đó **không** có nghĩa:

- Compiler phải giữ sẵn một “Pair object trên stack” trong suốt optimized execution.
- Deopt luôn tạo một object cho mọi scalarized allocation, bất kể Java state có cần quan sát nó hay không.
- Deopt chạy lại cả method từ đầu và lặp side effects.
- Vì thấy một allocation xuất hiện sau deopt nên mọi lời gọi trước đó đều đã cấp phát object.

Đúng hơn: **runtime có metadata đủ để khôi phục trạng thái Java tương đương**, bao gồm các virtual objects/frames khi cần. Deoptimization/materialization là một phần thiết yếu giúp **allocation elimination và speculative JIT optimization vẫn giữ correctness**.

### 12.1. Tại sao ảnh chụp stack không chỉ ra object ở stack?

Một optimized stack frame có thể chứa scalar fields, references, spills hoặc metadata phục vụ reconstruct. Việc công cụ nhìn thấy một vài int values trong native stack frame **không chứng minh** có một `Pair` nguyên vẹn đang cư trú ở đó.

Muốn phân tích thực sự phải xét compiler IR/machine code/VM metadata theo build phù hợp; Java stack trace chủ yếu mô tả call scopes, không phải physical object allocation.

### 12.2. Materialization có thể làm allocation metrics thay đổi

Trong phần lớn execution, allocation bị bỏ thì giảm pressure lên GC. Nhưng nếu chương trình thường xuyên deopt/reconstruct objects, một số allocations có thể xuất hiện tại những điểm khác so với trực giác từ source. Vì vậy không lấy một thời điểm GC allocation histogram và khẳng định object “luôn được đưa lên stack”.

**GC logs không nêu một trường “stack allocations eliminated by EA”**. Khi nhìn GC activity giảm, nguyên nhân có thể từ EA, dead-code elimination, allocation batching, TLAB sizing hoặc workload changes; cần thí nghiệm đối chứng.

## 13. Khi object không được loại allocation thì sao?

Giả sử ứng dụng tạo 100.000 `Box` rồi giữ tất cả trong một collection:

```java
java.util.List<Box> boxes = new java.util.ArrayList<>();

for (int i = 0; i < 100_000; i++) {
    boxes.add(new Box(i));
}
```

Đây là **snippet**, không phải file độc lập; sử dụng class `Box` từ ví dụ trước.

Nếu list còn reachable và code khác có thể truy cập các Boxes, runtime cần giữ object graph thực. Trên HotSpot với generational GC, các allocations vật lý thường nằm ở heap young/Eden theo đường phù hợp, có thể promoted nếu sống lâu.

Compiler vẫn có thể tối ưu constructor field stores, remove redundant bounds checks hoặc inline methods; **không loại allocation không có nghĩa không có bất kỳ tối ưu nào**.

### 13.1. Allocation trên heap không nhất thiết đắt

Với TLAB và GC generational, tạo các objects nhỏ chết trẻ thường có chi phí rất thấp trên HotSpot. Vì vậy, khuyến cáo “đừng bao giờ dùng `new` trong hot method” quá cực đoan.

Quan trọng là **allocation rate, survival/retention, cache locality và GC pause/cpu metrics**. Chuyển mọi object thành mutable reusable buffer có thể tạo aliasing bugs, dữ liệu cũ bị lộ và lock contention; đôi khi code immutable đơn giản, dễ tối ưu còn nhanh hơn.

### 13.2. Có thể tối ưu từ compiler mà không làm code khó đọc

Một holder object nhỏ, immutable dùng để biểu diễn cặp giá trị trong helper methods có thể làm code rõ ràng hơn so với truyền nhiều primitives. Nếu performance profiling không chỉ ra vấn đề, ưu tiên correctness/maintainability trước. JIT có thể scalarize một số temporary holders, nhưng đó là **cơ hội**, không là hợp đồng API.

## 14. Các cờ HotSpot Java 17 để thử nghiệm

### 14.1. Tắt escape analysis để so sánh

Oracle JDK 17 `java` manual ghi rõ:

```bash
-XX:+DoEscapeAnalysis       # Bật EA, mặc định trên HotSpot phù hợp
-XX:-DoEscapeAnalysis       # Tắt EA
```

Chạy:

```bash
java EscapeAnalysisDemo
java -XX:-DoEscapeAnalysis EscapeAnalysisDemo
```

Kết quả nghiệp vụ của hai lần chạy **giống nhau**. Nếu cấu hình khác/phiên chạy ngắn, có thể không thấy chênh lệch memory đáng kể; **không có bằng chứng từ stdout xác định EA đã loại bao nhiêu objects**.

### 14.2. `EliminateAllocations` trên HotSpot C2

Trong source của **OpenJDK JDK 17 C2** có VM option:

```bash
-XX:+EliminateAllocations
-XX:-EliminateAllocations
```

Option này điều khiển một nhánh loại allocations dựa trên EA của C2. Khi dùng HotSpot build hỗ trợ, thử:

```bash
java -XX:-EliminateAllocations EscapeAnalysisDemo
```

Nhưng **không suy việc tắt option bảo đảm mỗi source `new` sẽ tạo heap allocation**: còn các optimizations khác như dead-code elimination, constant folding, intrinsics, boxing caches và compiler policy. Cũng không coi option này là Java SE portable API.

**Chú ý:** Nếu JVM/vendor phản hồi `Unrecognized VM option`, dừng thử nghiệm và kiểm tra version/`PrintFlagsFinal`; không ép các option nội bộ của HotSpot lên JVM khác.

### 14.3. Tắt JIT để đối chiếu semantics

```bash
java -Xint EscapeAnalysisDemo
```

`-Xint` trên HotSpot chạy bytecode theo interpreter mode chủ yếu, vì thế các tối ưu C2 scalar replacement không có trong cùng code path; nhưng semantics/output Java vẫn đúng. Hiệu năng có thể giảm mạnh; không dùng nó để chạy benchmark throughput production.

`-XX:-TieredCompilation` **không đồng nghĩa tắt JIT**. Nó thay chính sách tiering, và một compiler khác vẫn có thể tối ưu.

### 14.4. Kiểm tra flags đang có thay vì nhớ tên từ tutorial cũ

```bash
java -XX:+PrintFlagsFinal -version
```

Có thể kết hợp filter theo shell/platform để xem `DoEscapeAnalysis`, `EliminateAllocations`, `EliminateLocks` và các flags liên quan.

Cẩn thận với cờ `PrintEscapeAnalysis` hoặc `PrintEliminateAllocations`: trên nhiều HotSpot **product/release builds**, đây là các options chỉ dành cho **non-product/debug VM**. Không đưa một lệnh `-XX:+PrintEscapeAnalysis` như thể bắt buộc chạy được trên mọi bản OpenJDK 17 production.

## 15. Đo allocation elimination đúng cách

Một phần mềm Java chạy nhanh hơn khi tắt/mở EA không tự chứng minh toàn bộ khác biệt đến từ một allocation site cụ thể. Có thể còn JIT warm-up, inlining, tiering, code cache, GC policy và CPU scheduling.

**Quy trình tối thiểu:**

1. **Cố định JDK vendor/version**: ghi chính xác `java -version`, architecture và server/client VM.
2. **Giữ workload đại diện**: inputs, object life spans và method polymorphism tương tự production.
3. **Warm-up đúng**: để JIT profile/compile trước khi lấy thông số steady state.
4. **So ba cấu hình**: baseline, `-XX:-DoEscapeAnalysis` và (nếu build hỗ trợ) `-XX:-EliminateAllocations`.
5. **So với `-Xint` về semantics**, nhưng không dùng interpreter performance để suy chi phí allocation C2.
6. **Dùng JFR/allocator counters/profiler** để so allocations, gc pauses, heap allocation rates và hotspots với settings giống nhau.
7. **Dùng nhiều forks/repetitions**, không tin một lần chạy 100 ms.
8. **Tránh benchmark chết**: không cho compiler xóa toàn bộ phép tính chỉ vì result không được dùng.
9. **Đo CPU và throughput cùng allocations**: giảm allocation không tự động cải thiện end-to-end p99 hay toàn bộ CPU.
10. **Không tuyên bố physical stack location** nếu chưa có bằng chứng cấp machine-code/runtime tương ứng.

### 15.1. Vì sao `new` trong vòng lặp không có nghĩa 1 triệu allocations?

```java
static long sum(int limit) {
    long result = 0;
    for (int i = 0; i < limit; i++) {
        Pair pair = new Pair(i, i + 1);
        result += (long) pair.left + pair.right;
    }
    return result;
}
```

Đây là **snippet**, cần định nghĩa class `Pair` có fields `left/right`. Nếu C2 inline/optimize, đôi khi object không còn materialized. Với interpreter hoặc nếu optimization không áp dụng, allocations vẫn có thể được thực hiện.

Đếm từ khóa `new` hoặc số vòng lặp chỉ đếm **source-level allocation expressions**, không đo actual heap allocations. Ngược lại, nếu JFR cho thấy allocation events ít hơn, cần hiểu JFR có thể dùng sampling/throttling tùy events/settings chứ không có nghĩa nó là exact per-object tracing.

### 15.2. JFR để đo theo vùng phương pháp

Khởi chạy:

```bash
java -XX:StartFlightRecording=filename=ea-test.jfr,settings=profile \
     EscapeAnalysisDemo
```

Một recording rất ngắn có thể có ít sự kiện hoặc không đủ warm-up. Java Flight Recorder có nhiều event types/thresholds/sampling settings. Trong JDK 17, theo dõi allocation/GC/compilation events với cấu hình thích hợp, sau đó xem trong JDK Mission Control hoặc tooling JFR.

JFR **không phải oracle xác nhận C2 đã stack-allocate một object**. Khi allocation rate giảm, điều có thể đúng là allocations đã bị eliminated; stack allocation vẫn phải có bằng chứng riêng từ implementation, không suy chỉ từ số alloc events.

### 15.3. GC logs có thể hỗ trợ, nhưng không kết luận được riêng EA

```bash
java -Xms256m -Xmx256m \
     -Xlog:gc*:file=gc-ea.log:uptime,level,tags \
     EscapeAnalysisDemo
```

Trong workload thực, có thể so allocation rate và GC frequency khi EA bật/tắt. Nhưng:

- GC logs thường chỉ cho **collectors events**, không phải danh sách mọi `new`.
- Một chương trình nhỏ có thể không trigger GC nào trong test run.
- Một ít GC events hơn không chứng minh chính xác allocation nào bị eliminated.
- Heap committed/RSS không nhất thiết giảm ngay dù số allocations giảm.
- Cần profiler/JIT compiler analysis khi muốn chỉ rõ một allocation site.

## 16. Microbenchmark: tránh “đo” chính compiler bỏ hết công việc

**Phản ví dụ:**

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    new Pair(i, i + 1);
}
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

Đây là **snippet phản mẫu**, không phải một class độc lập. Nếu việc tạo `Pair` không có observable effects, JIT có thể xóa toàn bộ work; kết quả đo có thể phản ánh một vòng lặp rỗng hoặc ít work hơn dự kiến. Không thể kết luận “stack allocation cực nhanh” từ một benchmark như vậy.

**Phương pháp tốt hơn:**

- Sử dụng kết quả tính toán thật sự (hoặc JMH Blackhole phù hợp).
- Cố định inputs nhưng tránh compiler biết trước/tối ưu toàn bộ một cách không đại diện.
- Warm-up, nhiều iterations/forks, đo memory allocations bằng profiler được cấu hình đúng.
- Tách benchmark **candidate scalarization** khỏi benchmark **object graph escape**.
- Chạy JDK17 cùng flags, heap size và workload trong các lần đối chứng.
- Nếu muốn xem compiler IR, dùng tooling/diagnostic build phù hợp; không áp dụng “mắt thường thấy ít GC thì object nằm stack”.

### 16.1. JMH không thay profiler

**JMH (Java Microbenchmark Harness)** giúp giảm nhiều sai lầm benchmark về JIT compilation, warm-up và dead-code elimination, nhưng **không** tự chỉ ra nguyên nhân nội bộ của mọi performance delta. Khi đo allocation rate, có thể dùng JMH GC profiler/appropriate JVM diagnostic tooling và xem kết quả theo bytes/op; xác thực JVM/GC/JIT settings.

**Bytes/op thấp** không tự chứng minh “object nằm stack”. Nó có thể xuất phát từ scalar replacement, allocation elimination hoặc loại bỏ hoàn toàn work.

## 17. Các sai lầm thường gặp khi đọc bộ nhớ

| Khẳng định sai | Tại sao sai | Cách nói đúng hơn |
| --- | --- | --- |
| “Biến local ở stack → object cũng ở stack.” | Biến có thể là reference; object có lifetime khác. | JVM stack giữ frame/values; object materialized thường ở Java heap. |
| “Object không escape thì luôn stack allocate.” | HotSpot C2 dùng scalar replacement, không mặc định stack allocation. | Non-escaping object có thể **được loại allocation** nếu đủ điều kiện. |
| “Mỗi `new` gây một GC heap object.” | JIT có thể optimize allocation đi. | Phân biệt bytecode allocation expression với runtime allocation. |
| “Không thấy GC events nghĩa objects đã ở stack.” | Có thể do heap đủ chỗ, TLAB, ít allocations, GC chưa chạy. | Đo allocations/profiler và compiler behavior. |
| “TLAB là thread stack.” | TLAB là heap allocation buffer. | Vẫn là heap allocation nhưng đường nhanh. |
| “Scalar replacement chuyển field values sang heap.” | Scalar values có thể ở registers, stacks hoặc tối ưu bỏ. | Object không cần tồn tại nguyên khối nếu semantics cho phép. |
| “Đối tượng return từ helper không thể được loại.” | Caller may inline helper. | Escape phải xét compiled scope/graph. |
| “Nếu không có cross-thread sharing thì chắc NoEscape.” | Object có thể sống qua method qua ThreadLocal. | Thread confinement khác method escape. |
| “EA lúc nào cũng loại mọi lock của local object.” | Compiler cần chứng minh correctness. | Lock elimination có điều kiện, không tự do bỏ synchronization. |
| “Record luôn được unbox thành primitive.” | Record Java17 vẫn là reference class. | Nó có thể là candidate scalar replacement. |
| “Một heap dump không thấy `Pair` nghĩa nó nằm trên stack.” | Object có thể đã chết/được GC/eliminated/chưa materialized. | Phải phân tích runtime conditions và compiler. |
| “`javap` có `new` chứng minh JIT đã cấp phát.” | Bytecode khác optimized machine code. | `javap` cho source-level VM instructions. |
| “Tắt EA sẽ làm logic chương trình sai.” | Optimization không được đổi Java semantics. | Có thể đổi performance/allocations, không đổi kết quả hợp lệ. |
| “Đổi JVM flag một lần là đủ chứng minh.” | JIT/GC/timing biến thiên. | Thử nhiều forks và workload đại diện. |
| “Scalarized object không thể xuất hiện lúc deopt.” | HotSpot có metadata/materialization. | Runtime dựng lại Java state khi cần. |
| “C2 luôn biên dịch ngay method sau 10.000 calls.” | Tiering/hotness/heuristics phụ thuộc workload/build. | Xác minh compiler activity thực tế. |

## 18. Bài tập có đáp án

**Câu 1.** Trong `Point p = new Point(1,2)` ở một method local, có thể chắc chắn object nằm trên stack không?

**Đáp án:** **Không.** `p` là reference; runtime object có thể được cấp phát trên heap, hoặc C2 có thể loại allocation nhờ scalar replacement; đó không đồng nghĩa stack allocation.

**Câu 2.** Nếu C2 loại toàn bộ allocation, có còn một object header của `Point` trên stack không?

**Đáp án:** Không có lý do phải tồn tại một object header nguyên vẹn. Compiler có thể chỉ giữ các scalars/giá trị đã tính, thậm chí xóa luôn computations dư.

**Câu 3.** Object được tạo rồi trả reference cho caller. Có chắc chắn allocation không bao giờ bị eliminated không?

**Đáp án:** Không. Caller có thể được inline và reference không còn escape khỏi compiled region. Cần phân tích graph tối ưu thực tế.

**Câu 4.** Object được lưu vào `static volatile Object shared` và dùng từ thread khác. Nó có thể đơn giản bị biến thành hai int locals của caller không?

**Đáp án:** Không theo cách phá observable shared-reference semantics. Object có thể cần materialize và maintain identity/visibility.

**Câu 5.** Nếu benchmark không dùng kết quả của `new Box(...)`, một thời gian cực ngắn có chứng minh stack allocation hiệu quả không?

**Đáp án:** Không. Compiler có thể dead-code-eliminate toàn bộ object creation và các computations không quan sát được.

**Câu 6.** TLAB là stack hay heap?

**Đáp án:** TLAB là **một vùng heap**, cho thread cấp phát nhanh. Object trong TLAB vẫn là heap object.

**Câu 7.** `-XX:-DoEscapeAnalysis` có nghĩa JVM bỏ qua mọi khả năng tối ưu không?

**Đáp án:** Không. Nó tắt EA theo HotSpot option, nhưng constant folding, DCE, inlining, các tối ưu khác vẫn có thể diễn ra.

**Câu 8.** Có thể lấy số objects trong heap dump lúc cuối process để tính chính xác bao nhiêu `new` đã chạy không?

**Đáp án:** Không. Heap dump chỉ chứa objects còn tồn tại tại snapshot; objects đã GC và allocations eliminated không hiện diện.

**Câu 9.** Scalar replacement có buộc tất cả fields ở CPU registers không?

**Đáp án:** Không. Scalars có thể được register allocate, spill vào stack slot, constant-fold hoặc tối ưu bỏ.

**Câu 10.** Vì sao JVM có thể materialize object khi deoptimization xảy ra?

**Đáp án:** Vì Java execution state sau fallback có thể cần object identity/reference; JIT lưu metadata để tái tạo trạng thái đúng.

**Câu 11.** `new int[2]` và `new int[100_000]` có khả năng scalar replacement giống nhau không?

**Đáp án:** Không. Arrays nhỏ, kích cỡ/indices rõ có thể dễ optimize hơn; arrays lớn/dynamic indices khó hơn và có compiler limits.

**Câu 12.** Vì sao “object không escape thread” không đủ để nói object có thể bị xóa?

**Đáp án:** Nó vẫn có thể sống sau method thông qua `ThreadLocal` hoặc một cấu trúc riêng của thread. Method lifetime và thread visibility là hai tiêu chí khác.

**Câu 13.** `EscapeAnalysisDemo` in `sum` bằng bao nhiêu, tại sao?

**Đáp án:** **10.000.000.000**, vì tổng các số lẻ `1,3,...,199999` bằng `100000²`.

**Câu 14.** Kết quả `distinctObjects=true` có thay đổi khi JIT bật scalar replacement không?

**Đáp án:** Không. JVM phải giữ semantics hai allocations riêng khi identity được quan sát trong phép so.

**Câu 15.** Nếu `System.identityHashCode` có trong method, JIT luôn cấm mọi dạng allocation elimination ở cả method không?

**Đáp án:** Không nhất thiết cấm toàn method; nó có thể tạo ràng buộc tại object/site liên quan, còn những allocations khác vẫn tối ưu được. Cần quan sát compiler behavior thật.

**Câu 16.** Khi code dùng `synchronized` trên một object cục bộ không escape, lock elimination có an toàn không?

**Đáp án:** Có thể, nếu compiler chứng minh không phá semantics/observable synchronization; không được hiểu rằng mọi `synchronized` là không cần thiết.

**Câu 17.** Chạy `-Xint` và baseline cho stdout khác nhau ở ba demos thì nên làm gì?

**Đáp án:** Kiểm tra code/data race/undefined assumptions và môi trường, vì logic Java hợp lệ phải giữ kết quả Java-level; khác biệt về performance/GC events thì bình thường.

**Câu 18.** Nên viết gì trong tài liệu kỹ thuật thay cho “HotSpot đưa object local lên stack”?

**Đáp án:** “HotSpot C2 có thể **loại bỏ allocation** của một object khi escape analysis và scalar replacement chứng minh đủ điều kiện; nếu allocation vẫn cần thực hiện, object thường được cấp phát trên heap.”

## 19. Tóm tắt

```text
Source:
    new Pair(a, b)
          │
          ▼
  Escape analysis của JIT
    │
    ├─ Có escape hoặc không thể chứng minh NoEscape
    │       │
    │       ▼
    │    Materialized object có thể phải nằm Java heap
    │       ├─ TLAB/Eden fast allocation
    │       └─ đường allocation khác theo GC/VM
    │
    └─ NoEscape + scalar replaceable + compiler chọn tối ưu
            │
            ▼
      Scalar replacement
        field.left  → scalar a
        field.right → scalar b
            │
            ▼
      Allocation elimination
      (object có thể không tồn tại nguyên khối)
            │
            ▼
      Deoptimization khi cần:
      reconstruct state / materialize object phù hợp

KHÔNG CÓ HỆ QUẢ TẤT YẾU:
  "NoEscape ⇒ đặt nguyên Java object lên native stack".
```

**Chốt kiến thức:** **Escape analysis** cung cấp thông tin về các đường object reference có thể đi ra khỏi phạm vi. Trên **HotSpot C2/Java 17**, tối ưu chủ chốt là **scalar replacement kết hợp allocation elimination**, có thể làm object không cần được cấp phát dưới dạng một đơn vị nguyên vẹn. **Stack allocation** là một cơ chế khác và không phải kết luận mặc định của EA trong HotSpot. Nếu object thực sự phải tồn tại và được truy cập qua references có thể quan sát, VM dùng heap allocation theo policy; **TLAB vẫn thuộc heap**. Hãy đo bằng benchmark/profiler và so EA bật–tắt, không suy physical memory placement từ từ khóa `new`, phạm vi biến local hoặc sự im lặng của GC logs.

### Tài liệu tham khảo và nguồn đối chiếu

- [HotSpot Escape Analysis and Scalar Replacement Status](https://cr.openjdk.org/~cslucas/escape-analysis/EscapeAnalysis.html): mô tả EA, scalar replacement và ghi rõ HotSpot không thực hiện stack allocation theo nghĩa đang tranh luận.
- [Oracle Java HotSpot VM Performance Enhancements — Escape Analysis](https://docs.oracle.com/javase/8/docs/technotes/guides/vm/performance-enhancements-7.html): các nhóm NoEscape/ArgEscape/GlobalEscape, scalar replacement, lock elimination và không thay heap allocation bằng stack allocation.
- [Oracle Java SE 17 — `java` launcher documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `DoEscapeAnalysis`, `PrintFlagsFinal`, `-Xint`, `-Xlog` và JFR.
- [OpenJDK JDK 17 C2 VM options](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/opto/c2_globals.hpp): `EliminateAllocations`, `EliminateLocks`, `DoEscapeAnalysis` và debug-only printing flags.
- [OpenJDK JDK 17 `escape.cpp`](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/opto/escape.cpp): connection graph, NoEscape và scalar-replaceable allocation paths.
- [JVMS Java SE 17 §2.5 — Runtime Data Areas](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5): JVM stacks, frames và heap model.
- [Java SE 17 Javadoc — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): records là reference classes trong Java 17.
- [Microsoft for Java Developers — Improving OpenJDK Scalar Replacement](https://devblogs.microsoft.com/java/improving-openjdk-scalar-replacement-part-2-3/): ví dụ những limitations và điều kiện phức tạp của scalar replacement.
