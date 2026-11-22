# Bộ ca constructor, nhánh điều kiện, nhiều return, ngoại lệ và phương thức synchronized

> **Mục tiêu:** Kiểm thử Java instrumentation phải vượt qua câu hỏi “transformer đã được gọi chưa?”. Một bản bytecode instrumented đúng phải giữ **kết quả nghiệp vụ, ngoại lệ, trạng thái đối tượng, khả năng xác minh classfile và ngữ nghĩa đồng bộ**, đồng thời phát ra tín hiệu đúng cho **mỗi lượt vào/thoát method**. Những đường khó nhất thường nằm trong constructor (`<init>`), nhiều nhánh `if`/`switch`, nhiều opcode `return`, ngoại lệ được bắt/thoát ra ngoài và method mang cờ `ACC_SYNCHRONIZED`.

Bài học thuộc chủ đề **Kiểm thử và chẩn đoán** của Java Advance – instrumentation. Ta xây ma trận ca thử để phát hiện lỗi bytecode weaving, giải thích các bẫy của JVM verifier và Java monitor, rồi chạy một **bộ test Java 17+ thực sự** với startup Java agent. Ví dụ có ba chế độ: baseline, agent chỉ quan sát class load và agent thay classfile bằng phiên bản có instrumentation; assertions kiểm tra cả business semantics lẫn probe counters.

## 1. Định nghĩa đúng tiêu chí “instrumentation hoạt động”

Một chương trình có Java agent chưa chắc đã được instrument thành công: `ClassFileTransformer.transform()` có thể nhận callback rồi trả `null`, bytes thay thế có thể bị JVM từ chối, hoặc method có hook nhưng hook chỉ chạy trên một nhánh và bỏ sót đường thoát khác.

**Bộ ca phải kiểm tra năm loại tính đúng đắn:**

| Chiều kiểm thử | Câu hỏi cần trả lời | Ví dụ assertion |
| --- | --- | --- |
| **Business behavior** | Kết quả/ngoại lệ/state có giữ như trước không? | Cùng input cho ra cùng return/exception message |
| **Control-flow coverage** | Mọi nhánh, mọi return và exception path có được thực thi? | `x<0`, `x==0`, `x>0`; return sớm và cuối |
| **Probe semantics** | Entry/exit, success/failure có đúng số lần và boundary? | Mỗi invocation đúng một entry và một exit |
| **JVM verification & loading** | Classfile có định dạng/stack map/constructor state hợp lệ? | Chạy `java -Xverify:all ...` không có `VerifyError` |
| **Concurrency & monitor** | Có giữ khóa đúng lúc, không deadlock/race/thay đổi sync semantics? | `Thread.holdsLock(this)` trong synchronized method, final state |

Ta cần phân biệt **coverage của test** và **coverage của probe**. Ví dụ method có ba return nhưng probe chỉ đếm ba entry không tự chứng minh exit đã được ghi ba lần. Tương tự, một exception được method tự bắt và xử lý **không phải failure ở method boundary** nếu phương thức trả về bình thường. Một exception để thoát khỏi method mới là **abrupt completion** tại boundary đó.

Một mẫu trạng thái lý tưởng cho một invocation:

~~~text
method entry
   |
   v
business code
   |
   +-- return bình thường --------> exit(success) đúng một lần
   |
   +-- exception được bắt bên trong -> tiếp tục -> exit(success) đúng một lần
   |
   +-- exception thoát ra ngoài ---> exit(failure) đúng một lần
~~~

Không giả định hook luôn có thể ghi đầy đủ ở mọi sự cố như process bị kill, `Runtime.halt` hoặc một lỗi xảy ra trước điểm chèn hook. Nếu chính helper của instrumentation ném exception, nó có thể **làm thay đổi** control flow; cần thiết kế và thử nghiệm failure policy.

## 2. Ma trận ca thử tối thiểu trước khi chèn bytecode

| ID | Loại code | Input/diễn biến | Output nghiệp vụ cần giữ | Probe cần quan sát |
| --- | --- | --- | --- | --- |
| CTOR-1 | Constructor thành công | `new BoundaryCases(5)` | Object tạo được, seed = 5 | Constructor 1 entry, 1 success exit |
| CTOR-2 | Constructor ném exception sau `super()` | `new BoundaryCases(-1)` | `IllegalArgumentException("negative seed")`, không có object sử dụng được | 1 entry, 1 failure exit |
| BR-1 | Nhánh âm | `branch(-1)` | `"NEG"` | Method 1 success exit |
| BR-2 | Nhánh bằng không | `branch(0)` | `"ZERO"` | Method 1 success exit |
| BR-3 | Nhánh dương | `branch(1)` | `"POS"` | Method 1 success exit |
| RET-1 | Return sớm đầu tiên | `multiple(-1)` | `-1` | 1 exit |
| RET-2 | Return sớm thứ hai | `multiple(0)` | `0` | 1 exit |
| RET-3 | Return cuối | `multiple(2)` với seed 5 | `7` | 1 exit |
| EX-1 | Tính toán bình thường | `divideOrFallback(2)` | `10` | Success exit |
| EX-2 | Exception bị bắt bên trong | `divideOrFallback(0)` | `-20` | **Success**, không phải failure |
| EX-3 | Exception thoát ra ngoài | `failOrReturn(13)` | `IllegalStateException("unlucky")` | Failure exit, giữ nguyên type/message |
| EX-4 | Method có khả năng ném nhưng chạy bình thường | `failOrReturn(2)` | `7` | Success exit |
| SYNC-1 | Synchronized bình thường | `increment(3)`, `increment(-1)` | State tăng/giảm đúng | Probe thấy monitor được giữ |
| SYNC-2 | Synchronized ném exception | `increment(Integer.MIN_VALUE)` | `IllegalArgumentException("bad delta")`, state không đổi | Failure exit **bên trong monitor** |
| SYNC-3 | Concurrent callers | 4 threads × 200 increments | Tổng không mất cập nhật | 800 success exits, không deadlock |
| SYNC-4 | Monitor release sau exception | Gọi lại `increment` sau exception | Gọi tiếp được | Không giữ monitor ngoài invocation |

Trong bộ test cuối, còn một lời gọi `increment(0)` để đọc state qua chính synchronized method. Vì vậy tổng cho method sync là **804 entries = 803 successes + 1 failure**, không phải chỉ 803. Mọi số đếm trong bảng và stdout đều có thể truy ra từ lời gọi cụ thể; không được “làm tròn” cho dễ nhìn.

### Những invariant nên luôn đúng

1. **Không thay output và exception contract** khi thêm instrumentation.
2. **Không bỏ hoặc đếm đôi** một method-level event khi có nhiều nhánh/return.
3. `entries == successes + failures` sau khi mọi invocation đã kết thúc, nếu chính probe vận hành bình thường và instrumentation được đặt ở entry/exit hợp lệ.
4. **Internal catch** không tự được phân loại thành method failure.
5. **Monitor** của synchronized method được JVM giữ trong phần thân method; dù return hay throw, method invocation rời đi thì monitor được giải phóng.
6. Probe không thay đổi modifier `synchronized`, không sửa descriptor, không thêm side effect nghiệp vụ và không làm Java verifier từ chối class.

Không biến các invariant thành giả định **đúng với mọi hook**: chúng là **hợp đồng chúng ta muốn hiện thực và kiểm thử**. Một instrumentation được thiết kế để ghi mọi throw event có thể có semantics khác một instrumentation chỉ phân biệt **method-level success/failure**.

## 3. Constructor: vị trí chèn hook và `uninitializedThis`

### 3.1. Vì sao `<init>` khác method thường?

Constructor có tên JVM `<init>` và return type `void`, nhưng nó chạy khi đối tượng đang được khởi tạo. Trước khi hoàn thành lời gọi khởi tạo superclass hoặc constructor được delegate, verifier có thể coi local 0 là **`uninitializedThis`**. Không được tùy tiện dùng đối tượng `this` như một instance hoàn chỉnh vào thời điểm ấy.

Với Java 17 source:

~~~java
public BoundaryCases(int seed) {
    if (seed < 0) throw new IllegalArgumentException("negative seed");
    this.seed = seed;
}
~~~

Compiler tạo lời gọi `Object.<init>()` **trước những statement thông thường** trong constructor này (vì Java 17 yêu cầu constructor chaining ở vị trí thích hợp). Trong bản instrumented của bài, ta chèn `ProbeRecorder.enter(...)` **sau điểm `invokespecial` khởi tạo superclass**.

Sơ đồ khái niệm:

~~~text
new BoundaryCases(seed)
    |
    v
<init> entry: this còn chưa được khởi tạo hoàn chỉnh
    |
    v
aload_0 / invokespecial java/lang/Object.<init>
    |
    v
an toàn hơn để dùng this; probe.enter("ctor")
    |
    +-- seed < 0 -> throw IllegalArgumentException -> probe.exit(failure)
    |
    +-- seed >= 0 -> gán seed -> probe.exit(success)
~~~

**Cạm bẫy verifier:** nếu một bytecode weaver “đẩy” `ALOAD 0`, gọi virtual method trên `this` hoặc đưa `uninitializedThis` vào helper trước khi constructor chain hợp lệ, JVM có thể ném `VerifyError`. Exception handler bao quanh cả lời gọi `<init>` của superclass cũng khó vì trạng thái uninitialized verifier cần được bảo toàn.

**Giới hạn coverage cần ghi thật:** Probe được đặt **sau** superclass constructor nên nếu superclass constructor ném exception **trước** điểm probe, đó **không** phải failure mà probe này quan sát được. Đừng báo “100% mọi lần new đều có entry” khi vị trí advice không cho phép. Nếu cần đo lifecycle khởi tạo đầy đủ, phải chọn boundary khác hoặc thiết kế instrumentation phù hợp với verifier/constructor chaining.

### 3.2. Constructor chaining `this(...)` và các bẫy khác

Nếu một class có:

~~~java
public Order() {
    this(0);
}

public Order(int amount) {
    this.amount = amount;
}
~~~

Đây là **mảnh code minh họa** bên trong class có field `amount`. Một lần gọi `new Order()` có thể thực hiện **hai `<init>` methods** theo chuỗi delegation. Nếu instrument mọi constructor và đếm như “mỗi object một sự kiện”, sẽ có **hai records cho một object**. Cần phân biệt:

- **Constructor invocation**: mỗi `<init>` thật sự được gọi.
- **Object construction attempt**: một nỗ lực tạo đối tượng ở bên ngoài (có thể đi qua nhiều `<init>`).
- **Object successfully initialized**: quá trình thành công và object hợp lệ.

Không tự thêm lời gọi helper trước `super()`/`this()` hoặc thêm catch handler phủ cả constructor chain mà không hiểu `StackMapTable`/verifier semantics. Với thư viện như ASM/Byte Buddy, dùng API/hook có bảo đảm rõ ràng về constructor advice trên đúng phiên bản thư viện/JDK thay vì copy method-exit transformer dành cho method thường vào `<init>`.

**Test bắt buộc:** constructor thành công, exception ném **sau** chain, constructor delegation, lớp có superclass constructor ném exception và class verifier với `-Xverify:all`. Nếu một case không thể quan sát theo vị trí hook, báo giới hạn rõ thay vì silently bỏ qua.

## 4. Nhánh điều kiện: method count không phải branch coverage

### 4.1. Ba đường `if` trong ví dụ

~~~java
public String branch(int x) {
    if (x < 0) return "NEG";
    if (x == 0) return "ZERO";
    return "POS";
}
~~~

Nếu test chỉ dùng `x=-1`, có thể nhận đúng `"NEG"` và một probe success, nhưng chưa có bằng chứng hai nhánh còn lại vẫn đúng. Ta cần tối thiểu:

~~~text
branch(-1) -> NEG
branch( 0) -> ZERO
branch( 1) -> POS
~~~

Đây là **expected-value table**, không phải output của một chương trình riêng.

Instrumentation có thể chèn hook tại entry/exit hoặc **trước từng branch/edge**. Hai loại coverage khác nhau:

| Loại đo | Điều nó có thể xác nhận | Điều nó không tự xác nhận |
| --- | --- | --- |
| Method entry count | Bao nhiêu invocation đã tới method | Từng nhánh condition đã được đi qua? |
| Method success/failure exit | Method đã return hay ném ra ngoài | Nhánh `if`/`else` nào được chọn? |
| Branch/edge coverage | Các cạnh true/false đã chạy hay chưa | Output/business logic có đúng sau biến đổi? |
| Line coverage | Những dòng source được ánh xạ đã chạy | Mọi nhánh của line đó đã được kiểm thử? |

Với `switch`, `tableswitch`/`lookupswitch` và exception edges, nên bổ sung test cho **mỗi case và default**, kể cả null/default policies khi thích hợp. Bytecode optimizer/compiler có thể tạo jump targets khác source nhìn thấy. Bộ test nên so sánh output gốc và instrumented, đồng thời nếu mục tiêu là branch coverage dùng một công cụ branch coverage hoặc counter chuyên trách thay vì suy từ method entry.

### 4.2. Tránh làm thay đổi thứ tự evaluation

Nếu điều kiện gốc:

~~~java
if (a != null && a.isReady()) {
    process(a);
}
~~~

thì `a.isReady()` **không** được gọi khi `a == null`, do short-circuit evaluation. Một instrumentation viết lại điều kiện mà gọi helper/`isReady()` vô điều kiện sẽ làm thay đổi behavior (thậm chí tạo `NullPointerException` mới). Với `&&`, `||`, ternary, pattern matching và `switch` expression, giữ nguyên thứ tự đánh giá, số lần gọi và loại exception.

**Probe có thể quan sát outcome của điều kiện** mà không sửa outcome; tuy nhiên việc ghi log có side effect/lock vẫn làm thay đổi timing. Không được vì mục tiêu coverage mà evaluate một expression thứ hai lần.

## 5. Nhiều return: exit hook phải phủ tất cả đường thoát

### 5.1. `ireturn`, `areturn`, `return` và các loại khác

Một Java method có thể chứa nhiều `return` từ các nhánh:

~~~java
public int multiple(int x) {
    if (x < 0) return -1;
    if (x == 0) return 0;
    return x + seed;
}
~~~

Về bytecode, JVM có nhiều opcode return: `ireturn` cho `int`/các kiểu int-compatible, `lreturn`, `freturn`, `dreturn`, `areturn` cho reference và `return` cho `void`. Nếu transformer chỉ gắn advice trước `return` cuối trong source hoặc chỉ xử lý một opcode, nó sẽ bỏ sót các đường thoát khác.

Một chiến lược semantic rõ là bao quanh body bằng `try/finally`:

~~~java
public int multiple(int x) {
    ProbeRecorder.enter("multiple", false);
    boolean ok = false;
    try {
        if (x < 0) { ok = true; return -1; }
        if (x == 0) { ok = true; return 0; }
        ok = true;
        return x + seed;
    } finally {
        ProbeRecorder.exit("multiple", ok, false);
    }
}
~~~

Đây là **một method instrumented cụ thể**, cần class có `seed` và `ProbeRecorder`; chương trình đầy đủ có ở phần 8. `finally` chạy cho **ba normal returns**, với `ok=true`, và ghi failure khi exception thoát ra trước khi set `ok=true`.

**Nhưng không phải cứ tìm từ khóa `finally` là xong:** Bytecode weaver phải sinh đúng exception table, jump targets, max locals/max stack và `StackMapTable` frames. Compiler có thể nhân bản bytecode của finally tại các exit sites hoặc tạo handler; counter của **method invocation** phải vẫn đúng một lần, không được nhân lên vì có ba return instructions.

### 5.2. Phải giữ nguyên return value và exception

Advice around `areturn` phải bảo toàn reference/object identity, `ireturn` giữ `int`, `lreturn`/`dreturn` giữ giá trị hai slot. Nếu code instrumentation làm rơi giá trị trên operand stack, đổi type hoặc khiến verifier merge frames sai, có thể gặp `VerifyError` hay sai nghiệp vụ.

`finally` có thể **ghi đè return hoặc exception** nếu bản thân callback `ProbeRecorder.exit` ném exception. Production cần thiết kế hook có failure policy rõ, chẳng hạn chỉ xử lý lỗi được dự báo từ exporter/serialization, không để telemetry đánh hỏng nghiệp vụ. Không nên dùng `catch(Throwable)` tràn lan để ém các lỗi nghiêm trọng của JVM mà không có chính sách an toàn.

**Case quan trọng:** Test cả return object `null`, object non-null, primitive values, void method, và method có early exit từ loop nếu transformer được dùng rộng. Bộ code dưới chỉ thử `String` và `int`; mở rộng theo signature thực tế của lớp mục tiêu.

## 6. Ngoại lệ: phân biệt caught, propagated và failure của hook

### 6.1. Một exception bị bắt bên trong method

~~~java
public int divideOrFallback(int denominator) {
    try {
        return 20 / denominator;
    } catch (ArithmeticException expected) {
        return -20;
    }
}
~~~

Với `denominator=0`, JVM ném `ArithmeticException` tại phép chia, nhưng method **bắt nó** và trả `-20`. Method-level instrumentation nên ghi **success** tại exit vì caller không nhận exception. Nếu mục tiêu là đếm nội bộ exception occurrences thì cần một loại event khác, được ghi ngay trong catch hoặc qua cơ chế quan sát phù hợp.

**Không nhầm throw-event với failure-event:**

- **Thrown exception event:** một exception được tạo/ném tại một điểm trong bytecode; có thể sẽ được catch.
- **Method failure at boundary:** method kết thúc đột ngột và exception thoát tới caller.
- **Business failure:** phương thức có thể trả `Result.error` bình thường mà không ném; cần định nghĩa theo domain, không tự coi mọi return là business success.

### 6.2. Một exception thoát khỏi method

~~~java
public int failOrReturn(int x) {
    if (x == 13) throw new IllegalStateException("unlucky");
    return x + seed;
}
~~~

Test phải kiểm tra **đúng loại exception và message**, không chỉ “có exception”. Instrumentation không được thay đổi loại, message, suppression hay cause của exception một cách vô ý.

Chỉ instrument các `ATHROW` instruction bên trong method **không đủ để bắt mọi exception thoát ra ngoài**: một invocation hoặc phép toán có thể ném exception ngầm, và exception có thể propagate mà method không có `ATHROW` tường minh. Muốn **on-exit on throwable** phải tạo exception handler bao phủ đúng vùng logic, có cấu trúc frames/handler hợp lệ, không vô tình bắt rồi biến thành success.

### 6.3. `try/finally` và failure flag trong demo

~~~java
public int failOrReturn(int x) {
    ProbeRecorder.enter("throwing", false);
    boolean ok = false;
    try {
        if (x == 13) throw new IllegalStateException("unlucky");
        ok = true;
        return x + seed;
    } finally {
        ProbeRecorder.exit("throwing", ok, false);
    }
}
~~~

Trong đây `finally` chạy khi method return hoặc throw, nhưng method không tự bắt `IllegalStateException`, nên caller vẫn nhận nó. Nếu hook `exit` tự throw, nó **có thể che** exception ban đầu; đây là lỗi instrumentation thường bị bỏ sót trong unit test chỉ kiểm tra happy path.

**Test thêm:** error từ một method được gọi bên trong, `RuntimeException`, checked exception, `Error` theo chính sách, nested try/catch/finally, exception filter, suppressed exception trong try-with-resources và throw từ constructor/helper. Không hứa exception exit được ghi cho mọi tình huống JVM termination/fatal failure; đặc tả bytecode và phạm vi advice quyết định.

## 7. Phương thức `synchronized`: monitor và đường ngoại lệ

### 7.1. `synchronized` method khác `synchronized(this)` block

Với một instance synchronized method:

~~~java
public synchronized int increment(int delta) {
    total += delta;
    return total;
}
~~~

Compiler đặt **`ACC_SYNCHRONIZED`** trong `method_info` flags. Theo JVMS 17, JVM tự **enter monitor** khi method được invoke và tự **exit monitor** khi method return bình thường hoặc đột ngột. Bytecode của method **không nhất thiết có `monitorenter`/`monitorexit`** như một `synchronized(obj) { ... }` block.

| Construct | Đối tượng monitor | Cách JVM giữ khóa |
| --- | --- | --- |
| `public synchronized void instanceMethod()` | `this` | Implicit lock theo `ACC_SYNCHRONIZED` |
| `public static synchronized void classMethod()` | `DeclaringClass.class` | Implicit lock theo `ACC_SYNCHRONIZED` |
| `synchronized(lock) { ... }` | Object `lock` | `monitorenter`/`monitorexit` trong bytecode |

**Không nên** chèn `monitorenter`/`monitorexit` thủ công cho một method đã mang `ACC_SYNCHRONIZED`: nếu không giữ balance/structured locking đúng, có thể gây deadlock hoặc `IllegalMonitorStateException`.

### 7.2. Probe có chạy trong monitor không?

Vì JVM lấy lock trước khi vào body của synchronized method, nếu probe được chèn vào **đầu body**, `Thread.holdsLock(this)` phải là `true` đối với instance synchronized method. Khi method thoát (kể cả exception), JVM giải phóng implicit monitor.

Mã variant của bài:

~~~java
public synchronized int increment(int delta) {
    ProbeRecorder.enter("sync", Thread.holdsLock(this));
    boolean ok = false;
    try {
        if (delta == Integer.MIN_VALUE) throw new IllegalArgumentException("bad delta");
        total += delta;
        ok = true;
        return total;
    } finally {
        ProbeRecorder.exit("sync", ok, Thread.holdsLock(this));
    }
}
~~~

Cả entry/exit probes đều chạy **khi còn giữ lock**. Bởi vậy một recorder blocking/locking có thể **kéo dài critical section**, ảnh hưởng contention và p99 ngay cả khi body nghiệp vụ rất nhanh. Phép thử ghi `sync_monitor_violations=0` là assertion cho việc monitor đang được giữ ở cả hai callback locations.

Đối với static synchronized method, đừng dùng `Thread.holdsLock(this)` vì không có `this`; kiểm tra monitor của đối tượng `Class<?>` phù hợp nếu cần. Với `synchronized(lock)` block, chỉ những advice đặt **bên trong block** mới nhất thiết chạy khi monitor `lock` đang held.

### 7.3. Tính đúng đắn dưới nhiều threads

Test 4 threads × 200 `increment(1)` cùng trên **một** instance. Nếu không có điều kiện đua mới và method vẫn synchronized, state sẽ tăng đúng 800. Bộ test còn làm:
1. `increment(3)` → tổng 3.
2. `increment(Integer.MIN_VALUE)` → throw; tổng vẫn 3.
3. `increment(-1)` → tổng 2.
4. 800 increments từ 4 threads → tổng 802.
5. `increment(0)` → đọc lại tổng **802**.

Không dùng `Thread.sleep` để đoán thứ tự concurrency; `Future.get()` xác nhận worker tasks đã hoàn tất và truyền lỗi từ worker về main, `awaitTermination` đảm bảo executor được đóng trong phạm vi ví dụ.

**Lưu ý:** Test chạy thành công một lần **không chứng minh vắng mặt mọi race/deadlock** dưới mọi lịch trình. Muốn độ tin cậy cao hơn, chạy lặp lại, stress trên nhiều JVM/CPU, bổ sung timeout và khi có lock phức tạp hãy xét công cụ kiểm thử concurrency. Probe cũng phải thread-safe; `LongAdder` giúp đếm dưới concurrency nhưng `sum()` trong lúc threads đang cập nhật **không phải atomic snapshot tuyệt đối**.

## 8. Ví dụ thực thi đầy đủ Java 17+: baseline, observe và inject

Để tập trung vào test semantics mà không phụ thuộc thư viện ASM/Byte Buddy, ta **biên dịch trước hai phiên bản cùng binary name `BoundaryCases`**:
- Bản gốc ở root classpath, **không** gọi probe.
- Bản variant ở `variant/`, có lời gọi `ProbeRecorder` đặt trong method/constructor qua Java source.
- Một startup agent dùng `ClassFileTransformer` để trả đúng **classfile bytes variant** ngay khi JVM định nghĩa `BoundaryCases` trong mode `inject`.

Đây là **instrumentation thật ở class-load time**, không phải giả lập bằng cách gọi trực tiếp subclass. Tuy nhiên **cách tạo advice bằng source variant** chỉ phục vụ bài học; công cụ production thường cần patch bytes đầu vào theo classloader/module, đúng method descriptor và xử lý verifier/StackMapTable. Không trả toàn bộ một bản `.class` compile sẵn cho mọi class có cùng tên ở các loader khác nhau.

### 8.1. File `BoundaryCases.java` — phiên bản gốc

~~~java
public final class BoundaryCases {
    private final int seed;
    private int total;

    public BoundaryCases(int seed) {
        if (seed < 0) throw new IllegalArgumentException("negative seed");
        this.seed = seed;
    }

    public String branch(int x) {
        if (x < 0) return "NEG";
        if (x == 0) return "ZERO";
        return "POS";
    }

    public int multiple(int x) {
        if (x < 0) return -1;
        if (x == 0) return 0;
        return x + seed;
    }

    public int divideOrFallback(int denominator) {
        try { return 20 / denominator; }
        catch (ArithmeticException expected) { return -20; }
    }

    public int failOrReturn(int x) {
        if (x == 13) throw new IllegalStateException("unlucky");
        return x + seed;
    }

    public synchronized int increment(int delta) {
        if (delta == Integer.MIN_VALUE) throw new IllegalArgumentException("bad delta");
        total += delta;
        return total;
    }
}
~~~

Không có method `main` trong file này; chương trình được kiểm thử bằng `CaseSuite`. Constructor gốc có `final int seed` được gán trên nhánh thành công; ở nhánh âm nó ném exception.

### 8.2. File `ProbeRecorder.java` — bộ đếm thread-safe

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public final class ProbeRecorder {
    private static final ConcurrentHashMap<String, LongAdder> ENTER = new ConcurrentHashMap<>();
    private static final ConcurrentHashMap<String, LongAdder> OK = new ConcurrentHashMap<>();
    private static final ConcurrentHashMap<String, LongAdder> FAIL = new ConcurrentHashMap<>();
    private static final LongAdder BAD_MONITOR_OBSERVATIONS = new LongAdder();

    private ProbeRecorder() {}

    private static void add(ConcurrentHashMap<String, LongAdder> counters, String name) {
        counters.computeIfAbsent(name, ignored -> new LongAdder()).increment();
    }

    public static void enter(String name, boolean monitorHeld) {
        if ("sync".equals(name) && !monitorHeld) BAD_MONITOR_OBSERVATIONS.increment();
        add(ENTER, name);
    }

    public static void exit(String name, boolean succeeded, boolean monitorHeld) {
        if ("sync".equals(name) && !monitorHeld) BAD_MONITOR_OBSERVATIONS.increment();
        add(succeeded ? OK : FAIL, name);
    }

    private static long read(ConcurrentHashMap<String, LongAdder> map, String name) {
        LongAdder counter = map.get(name);
        return counter == null ? 0 : counter.sum();
    }

    public static long entered(String name) { return read(ENTER, name); }
    public static long succeeded(String name) { return read(OK, name); }
    public static long failed(String name) { return read(FAIL, name); }
    public static long invalidMonitorCount() { return BAD_MONITOR_OBSERVATIONS.sum(); }
}
~~~

Bộ đếm này **cố tình đơn giản**: chỉ dùng một tập tên method cố định, nên không sinh metric label cardinality vô hạn. `ConcurrentHashMap` + `LongAdder` cho phép nhiều threads cập nhật. Phần kiểm tra `sum()` chạy **sau** `Future.get()` và executor shutdown, vì đọc trong lúc concurrent updates chỉ cho approximate snapshot.

Recorder này vẫn có overhead từ map lookups và counter updates; trong synchronized method, thao tác recorder chạy **bên trong critical section**. Vì mục tiêu chính là correctness, không suy ra latency production từ kết quả bộ test.

### 8.3. File `variant/BoundaryCases.java` — phiên bản có probe

~~~java
public final class BoundaryCases {
    private final int seed;
    private int total;

    public BoundaryCases(int seed) {
        ProbeRecorder.enter("ctor", false);
        boolean ok = false;
        try {
            if (seed < 0) throw new IllegalArgumentException("negative seed");
            this.seed = seed;
            ok = true;
        } finally {
            ProbeRecorder.exit("ctor", ok, false);
        }
    }

    public String branch(int x) {
        ProbeRecorder.enter("branch", false);
        boolean ok = false;
        try {
            if (x < 0) { ok = true; return "NEG"; }
            if (x == 0) { ok = true; return "ZERO"; }
            ok = true;
            return "POS";
        } finally {
            ProbeRecorder.exit("branch", ok, false);
        }
    }

    public int multiple(int x) {
        ProbeRecorder.enter("multiple", false);
        boolean ok = false;
        try {
            if (x < 0) { ok = true; return -1; }
            if (x == 0) { ok = true; return 0; }
            ok = true;
            return x + seed;
        } finally {
            ProbeRecorder.exit("multiple", ok, false);
        }
    }

    public int divideOrFallback(int denominator) {
        ProbeRecorder.enter("caught", false);
        boolean ok = false;
        try {
            int result;
            try { result = 20 / denominator; }
            catch (ArithmeticException expected) { result = -20; }
            ok = true;
            return result;
        } finally {
            ProbeRecorder.exit("caught", ok, false);
        }
    }

    public int failOrReturn(int x) {
        ProbeRecorder.enter("throwing", false);
        boolean ok = false;
        try {
            if (x == 13) throw new IllegalStateException("unlucky");
            ok = true;
            return x + seed;
        } finally {
            ProbeRecorder.exit("throwing", ok, false);
        }
    }

    public synchronized int increment(int delta) {
        ProbeRecorder.enter("sync", Thread.holdsLock(this));
        boolean ok = false;
        try {
            if (delta == Integer.MIN_VALUE) throw new IllegalArgumentException("bad delta");
            total += delta;
            ok = true;
            return total;
        } finally {
            ProbeRecorder.exit("sync", ok, Thread.holdsLock(this));
        }
    }
}
~~~

Lưu ý: Đây là **toàn bộ file variant** nhưng không được compile cùng lúc với `BoundaryCases.java` root vào cùng output directory. Hai file có cùng `public class BoundaryCases`; compiler sẽ báo duplicate class nếu đặt chung source-set. Cách build ở phần 8.7 dùng `-d variant` riêng.

Một constructor được biên dịch từ file này có lời gọi `Object.<init>` **trước** `ProbeRecorder.enter`, vì Java 17 compiler tạo implicit superclass constructor call. Điều này giữ khả năng xác minh classfile. Điều tương tự **không tự xảy ra** nếu một bytecode weaver viết tay di chuyển instructions.

### 8.4. File `ScopedTransformer.java` — lọc đúng class ở initial definition

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ScopedTransformer implements ClassFileTransformer {
    private final byte[] bytes;

    public ScopedTransformer(byte[] bytes) { this.bytes = bytes == null ? null : bytes.clone(); }

    @Override
    public byte[] transform(Module module, ClassLoader loader, String internalName,
            Class<?> redefining, ProtectionDomain protectionDomain, byte[] original) {
        if (!"BoundaryCases".equals(internalName)) return null;
        System.out.println("transform=BoundaryCases");
        return bytes == null ? null : bytes.clone();
    }
}
~~~

`internalName` là JVM internal class name. Vì `BoundaryCases` ở default package, tên chính là `"BoundaryCases"`; với package `org.demo`, tên có slash: `"org/demo/BoundaryCases"`.

- Mode **observe**: transformer nhận callback rồi trả `null`, JVM giữ class gốc.
- Mode **inject**: transformer trả classfile variant được biên dịch trước; JVM dùng method có probe.
- Transformer chỉ dùng **first load**; không cần `canRetransform=true`.
- Ví dụ không giải quyết nhiều loaders cùng define một binary name; production phải lọc defining loader/module, giữ method descriptors và classfile constraints.

Không sửa trực tiếp `original` byte array; `ClassFileTransformer` Javadoc yêu cầu trả một mảng bytes hợp lệ mới hoặc `null`. Đừng nạp helper từ callback một cách gây class-loading recursion.

### 8.5. File `CaseAgent.java` — startup agent

~~~java
import java.io.IOException;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class CaseAgent {
    public static void premain(String args, Instrumentation instrumentation) throws IOException {
        String mode = args == null ? "observe" : args;
        if (!"observe".equals(mode) && !"inject".equals(mode)) {
            throw new IllegalArgumentException("Expected observe or inject");
        }
        byte[] changed = "inject".equals(mode)
                ? Files.readAllBytes(Path.of("variant/BoundaryCases.class")) : null;
        instrumentation.addTransformer(new ScopedTransformer(changed));
        if ("inject".equals(mode)) System.setProperty("cases.instrumented", "true");
        System.out.println("agent-mode=" + mode);
    }
}
~~~

Agent đọc bytes **trước** khi đăng ký transformer, không thực hiện I/O ngay trong `transform`. Property `cases.instrumented=true` **chỉ là tín hiệu cho assertions của bộ test**, không phải cơ chế xác minh instrumentation trong production. Bộ test vẫn kiểm tra bằng counter và behavior thực tế.

Nếu `variant/BoundaryCases.class` không tồn tại hoặc working directory sai, `Files.readAllBytes` sẽ báo lỗi và agent không chạy thành công. Khởi động agent lỗi trong `premain` có thể khiến JVM không chạy tới `main`; đó là failure setup, không được báo như “test đã pass”.

### 8.6. File `CaseSuite.java` — test assertions, exception và concurrency

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class CaseSuite {
    private static void eq(Object expected, Object actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError("expected=" + expected + " actual=" + actual);
        }
    }

    private static void count(String name, long entries, long ok, long fail) {
        eq(entries, ProbeRecorder.entered(name));
        eq(ok, ProbeRecorder.succeeded(name));
        eq(fail, ProbeRecorder.failed(name));
        System.out.println(name + "=" + entries + "/" + ok + "/" + fail);
    }

    public static void main(String[] args) throws Exception {
        try {
            new BoundaryCases(-1);
            throw new AssertionError("constructor should throw");
        } catch (IllegalArgumentException expected) {
            eq("negative seed", expected.getMessage());
        }
        BoundaryCases subject = new BoundaryCases(5);

        eq("NEG", subject.branch(-1));
        eq("ZERO", subject.branch(0));
        eq("POS", subject.branch(1));

        eq(-1, subject.multiple(-1));
        eq(0, subject.multiple(0));
        eq(7, subject.multiple(2));

        eq(10, subject.divideOrFallback(2));
        eq(-20, subject.divideOrFallback(0));

        eq(7, subject.failOrReturn(2));
        try {
            subject.failOrReturn(13);
            throw new AssertionError("method should throw");
        } catch (IllegalStateException expected) {
            eq("unlucky", expected.getMessage());
        }

        eq(3, subject.increment(3));
        try {
            subject.increment(Integer.MIN_VALUE);
            throw new AssertionError("synchronized method should throw");
        } catch (IllegalArgumentException expected) {
            eq("bad delta", expected.getMessage());
        }
        eq(false, Thread.holdsLock(subject));
        eq(2, subject.increment(-1));

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> work = new ArrayList<>();
            for (int thread = 0; thread < 4; thread++) {
                work.add(pool.submit(() -> {
                    for (int i = 0; i < 200; i++) subject.increment(1);
                }));
            }
            for (Future<?> task : work) task.get();
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new AssertionError("worker timeout");
            }
        }
        eq(802, subject.increment(0));

        boolean injected = Boolean.getBoolean("cases.instrumented");
        System.out.println("instrumented=" + injected);
        long factor = injected ? 1 : 0;
        count("ctor", 2 * factor, factor, factor);
        count("branch", 3 * factor, 3 * factor, 0);
        count("multiple", 3 * factor, 3 * factor, 0);
        count("caught", 2 * factor, 2 * factor, 0);
        count("throwing", 2 * factor, factor, factor);
        count("sync", 804 * factor, 803 * factor, factor);
        eq(0L, ProbeRecorder.invalidMonitorCount());
        System.out.println("sync_monitor_violations=0");
        System.out.println("final_total=802");
        System.out.println("ASSERTIONS_PASSED");
    }
}
~~~

Bộ test dùng `AssertionError` trực tiếp thay vì cần JUnit, nên chạy được chỉ bằng JDK. Trong production, có thể chuyển thành **JUnit 5 tests** và thêm coverage/bytecode scanning, nhưng ví dụ này không yêu cầu thư viện ngoài.

Chi tiết cần chú ý:

- `Future.get()` đưa exception của worker về main; nếu một thread làm sai state hoặc ném exception, test không thể silently pass.
- `ExecutorService.shutdown()` và `awaitTermination(...)` đóng executor; giá trị 5 giây là timeout **cho demo**, có thể điều chỉnh theo môi trường CI.
- `Thread.holdsLock(subject)` kiểm tra **thread đang gọi** có sở hữu monitor hay không. Sau lần exception, main không được còn giữ monitor của `subject`.
- `eq(802, subject.increment(0))` thêm **một** call synchronized bình thường. Counter sync vì thế có **803 success exits**.
- `factor` chỉ điều chỉnh expected counts ở baseline/observe; **business assertions giống hệt** trong cả ba chế độ.

### 8.7. Tệp `agent.mf` và lệnh chạy

Manifest:

~~~text
Manifest-Version: 1.0
Premain-Class: CaseAgent
~~~

Lưu manifest với newline cuối. Cấu trúc file:

~~~text
demo/
  BoundaryCases.java
  ProbeRecorder.java
  ScopedTransformer.java
  CaseAgent.java
  CaseSuite.java
  agent.mf
  variant/
    BoundaryCases.java
~~~

Từ thư mục `demo`, dùng **JDK 17+**:

~~~bash
javac --release 17 BoundaryCases.java ProbeRecorder.java ScopedTransformer.java CaseAgent.java CaseSuite.java

javac --release 17 -classpath . -d variant variant/BoundaryCases.java

jar --create --file case-agent.jar --manifest agent.mf CaseAgent.class ScopedTransformer.class

java CaseSuite

java -javaagent:case-agent.jar=observe CaseSuite

java -javaagent:case-agent.jar=inject CaseSuite
~~~

`-classpath .` ở bước biên dịch variant cho compiler thấy `ProbeRecorder` từ root. `-d variant` đưa **classfile variant** vào đúng thư mục agent đọc lúc runtime. Không copy `variant/BoundaryCases.class` đè lên root class trước khi chạy; nếu làm vậy, bạn sẽ không còn đang kiểm thử phép thay bytes qua transformer.

### 8.8. Kết quả chạy đã kiểm chứng

Toàn bộ code được compile bằng `javac --release 17` và chạy thực trên OpenJDK 24. Các đoạn bên dưới là stdout của **ba lượt JVM riêng**.

**Baseline:**

~~~text
instrumented=false
ctor=0/0/0
branch=0/0/0
multiple=0/0/0
caught=0/0/0
throwing=0/0/0
sync=0/0/0
sync_monitor_violations=0
final_total=802
ASSERTIONS_PASSED
~~~

**Observe-only:**

~~~text
agent-mode=observe
transform=BoundaryCases
instrumented=false
ctor=0/0/0
branch=0/0/0
multiple=0/0/0
caught=0/0/0
throwing=0/0/0
sync=0/0/0
sync_monitor_violations=0
final_total=802
ASSERTIONS_PASSED
~~~

**Inject:**

~~~text
agent-mode=inject
transform=BoundaryCases
instrumented=true
ctor=2/1/1
branch=3/3/0
multiple=3/3/0
caught=2/2/0
throwing=2/1/1
sync=804/803/1
sync_monitor_violations=0
final_total=802
ASSERTIONS_PASSED
~~~

`name=entered/succeeded/failed`. Cụ thể:

| Kind | Entries | Successes | Failures | Ý nghĩa |
| --- | ---: | ---: | ---: | --- |
| `ctor` | 2 | 1 | 1 | Một constructor ném, một thành công |
| `branch` | 3 | 3 | 0 | Âm, không và dương |
| `multiple` | 3 | 3 | 0 | Ba normal return paths |
| `caught` | 2 | 2 | 0 | Divide by zero **được bắt** nên vẫn success |
| `throwing` | 2 | 1 | 1 | Một return và một uncaught `IllegalStateException` |
| `sync` | 804 | 803 | 1 | Main calls + 800 concurrent calls + final state read |

Trong cả ba chế độ, `final_total=802` và mọi behavior assertions đều pass. Đó là bằng chứng rằng **bản demo không đổi logic**, trong phạm vi ca đã chạy. Nó không chứng minh weaver sản xuất có thể transform mọi class, mọi JVM version hoặc mọi constructor pattern.

## 9. Kiểm tra classfile và JVM verifier, không chỉ stdout

Một bản transform có thể lộ lỗi khi class được verify hoặc khi chạm một nhánh ít dùng; cần chạy thêm các phép kiểm tra **artifact bytes**.

### 9.1. `javap` cho constructor

~~~bash
javap -c -p -classpath variant BoundaryCases
~~~

Trong bản variant kiểm thử, constructor có `invokespecial java/lang/Object."<init>"` tại đầu body, sau đó mới tới `ProbeRecorder.enter`. Đây là bằng chứng **compiler đã đặt hook sau superclass initialization** trong fixture Java source. Không được suy ra một bytecode weaver tùy ý sẽ tự bố trí an toàn.

Khi xem output, cần phân biệt:
- `invokespecial ... <init>`: đường khởi tạo superclass/constructor chain.
- `StackMapTable`: trạng thái verifier tại branch/handler frames.
- `Exception table`: vùng try/catch/finally; bổ sung handler sai có thể bắt nhầm exception hoặc gặp invalid frame.
- `max_stack`/`max_locals`: instrumentation có thêm local `ok` và có thể thêm operand stack depth.
- `LineNumberTable`/source mapping: nên giữ metadata hữu ích để stack traces vẫn có ích; không phải mọi transformer bắt buộc giữ mọi debug attribute.

### 9.2. `ACC_SYNCHRONIZED` và bytecode

~~~bash
javap -v -p -classpath . BoundaryCases
javap -v -p -classpath variant BoundaryCases
~~~

Kiểm tra `increment(int)` còn mang `ACC_SYNCHRONIZED` ở **cả hai phiên bản**. Với synchronized method, JVM xử lý monitor implicit; không nên kỳ vọng thấy cặp `monitorenter`/`monitorexit` trong body chỉ vì method có từ khóa `synchronized`.

### 9.3. Buộc verifier kiểm tra toàn bộ class được load

~~~bash
java -Xverify:all CaseSuite
java -Xverify:all -javaagent:case-agent.jar=observe CaseSuite
java -Xverify:all -javaagent:case-agent.jar=inject CaseSuite
~~~

`-Xverify:all` tăng phạm vi bytecode verification; chạy nó như một lượt CI test riêng, không dùng để đo throughput production. Nếu có `VerifyError`, `ClassFormatError`, `NoClassDefFoundError`, `IllegalAccessError` hoặc class loader linkage issues, dừng và kiểm tra classfile/StackMapTable/helper visibility thay vì bỏ flags để che lỗi.

**Điểm khác nhau giữa các loại thất bại:**

| Dấu hiệu | Khả năng liên quan |
| --- | --- |
| `VerifyError` | Invalid operand-stack/local types, constructor `uninitializedThis`, stack map frames, handler targets |
| `ClassFormatError` | Classfile bytes/constant pool/attributes/Code structure sai |
| `NoClassDefFoundError` | Helper không nhìn thấy từ defining loader hoặc target class binary name sai |
| `IllegalAccessError` | Helper field/method không accessible do package/module/protection |
| `UnsupportedClassVersionError` | Classfile version vượt JVM đang chạy |
| `ExceptionInInitializerError` | Helper/probe class initialization hỏng |
| Test business result sai nhưng class load thành công | Rewrite làm thay đổi return/branch/throw semantics |
| Monitor contention/deadlock | Probe làm I/O, lock hoặc chèn monitor operations sai |
| Counter `entries != exits` | Bỏ sót normal/exception exit, hoặc probe tự thất bại/đếm đôi |

Không ngộ nhận `ClassFileTransformer` callback được gọi là classfile chắc chắn đã được install: nếu trả bytes không hợp lệ, JVM có thể từ chối class loading. Nếu callback ném uncaught exception, Javadoc cho biết JVM vẫn có thể tiếp tục các transformer tiếp theo và quá trình định nghĩa; phải có log và assertion behavior thay vì chỉ nhìn callback.

## 10. Tự động hóa kiểm thử cho một weaver dùng ASM hoặc Byte Buddy

Demo dùng precompiled variant, nhưng khi phát triển một weaver thực tế, cần kiểm tra **đúng một pipeline bytecode**:

~~~text
Original class bytes
    |
    v
Transformer: select class/method by name + loader + descriptor
    |
    v
Inject entry/exit advice, rewrite branches/handlers
    |
    v
Recompute/maintain max_stack, max_locals, StackMapTable
    |
    v
ClassLoader.defineClass / JVM verify
    |
    v
Run behavior assertions + probe assertions
    |
    v
Concurrency & error-path stress
~~~

### 10.1. Đúng signature và điều kiện lọc

Đối với overload, không chọn chỉ theo tên `process`: phải xét descriptor, chẳng hạn `process(I)I` khác `process(Ljava/lang/String;)Ljava/lang/String;`. Constructors có tên `<init>`, static initializer là `<clinit>`; `native` và `abstract` methods không có Code attribute để inject method-body advice thông thường. Bridge/synthetic methods cũng có thể xuất hiện, cần chính sách test để không double instrument một logical call vô tình.

**Hợp đồng transformer:** `transform(...)` nhận bytes đầu vào của chuỗi transformer và trả classfile hợp lệ trong `byte[]` mới, hoặc `null` nếu bỏ qua. Không mutate `classfileBuffer` tại chỗ. Với retransform/redefine của class đã loaded, còn phải giữ những giới hạn cấu trúc của API, không mặc nhiên thêm/xóa field/method.

### 10.2. Test bytecode của đường exception và return

Với một method body:
- Cover mọi `RETURN`/`IRETURN`/`LRETURN`/`FRETURN`/`DRETURN`/`ARETURN` thực tế.
- Cover explicit `ATHROW` và các exception có thể phát sinh **ngầm** từ instruction hoặc lời gọi method.
- Đặt try/catch handler đúng **thứ tự**; không bắt hết và khiến exception đáng ra được catch trong business code bị propagate.
- Không thay đổi return value đang nằm trên operand stack khi gọi helper.
- Không biến exception exit thành normal return; không để helper exception che business exception.
- Giữ đúng xử lý null, boxed primitives, method descriptor và generic bridge semantics.

Một công cụ có hỗ trợ advice entry/exit không có nghĩa mặc định mọi exception đều được quan sát. Ví dụ một advice cấu hình “normal exit only” sẽ bỏ qua abrupt completion. **Cấu hình phải gắn với semantics của test**, không chỉ tên annotation/API.

### 10.3. Test riêng constructor và synchronized

- Constructors: sau `super()/this()` chain, `uninitializedThis`, exception handlers và overload/chaining; không đếm nhầm số objects từ số constructor calls.
- Synchronized instance methods: còn `ACC_SYNCHRONIZED`, monitor `this` held trong body, released khi normal/abrupt completion.
- Synchronized static methods: monitor `DeclaringClass.class`.
- `synchronized(lock)` blocks: explicit `monitorenter/monitorexit`, balanced structured locking trên mọi nhánh, kể cả exception.
- `wait`/`notify` nếu code nghiệp vụ dùng monitor: test cả signaling/liveness, không chỉ counter.
- Asynchronous or concurrent events: callbacks/probe thread-safety, worker task exceptions, per-invocation context cleanup và exporter backpressure.

Tuyệt đối không tạo thêm `synchronized` trên helper toàn cục chỉ để dễ ghi metric mà không đo contention: nó có thể biến một method nhiều-thread vốn chấp nhận được thành điểm nghẽn mới.

### 10.4. Chạy matrix trên JVM thực tế

| Chiều | Trường hợp đề xuất |
| --- | --- |
| Java runtime | JDK thấp nhất còn hỗ trợ (bài: 17), JDK đang deploy, nhiều vendor khi cần |
| JVM flags | Default, `-Xverify:all`, các chế độ GC/diagnostic có liên quan |
| Class kind | Public/private methods, constructors, abstract/native exclusions, interface default, record/enum khi công cụ hỗ trợ |
| Method return | `void`, primitives, reference, `null`, nhiều `return` |
| Exceptions | Internal catch, explicit throw, implicit throw, nested finally, checked/unchecked |
| Monitor | Instance/static synchronized, synchronized block, normal + exceptional paths |
| Class loader | Application loader, custom loader và bootstrap targets nếu có chủ đích |
| Retransformation | First definition và existing class với `canRetransform=true` khi công cụ cần |
| Race/performance | Concurrency stress, lock contention, latency p99 và GC pressure |
| Application semantics | Kết quả, side effects, ordering, state mutation, observable exceptions |

Đừng dùng một lần chạy một fixture nhỏ như bằng chứng đủ cho mọi tổ hợp. Tuy nhiên một bộ test nhỏ có **đối chứng baseline + inject, chính xác số events và verifier pass** là nền tảng tốt để phát hiện regression sớm.

## 11. Các lỗi dễ lọt qua review

| Sai lầm | Vì sao sai | Cách phát hiện |
| --- | --- | --- |
| Chỉ test return cuối | Early return không được ghi exit hoặc trả sai giá trị | `multiple(-1)`, `(0)`, `(2)` với output + counter |
| Đếm mọi exception là method failure | Exception nội bộ được catch vẫn return bình thường | `divideOrFallback(0)` phải thành công ở boundary |
| Chỉ instrument `ATHROW` | Exception từ divide/invoke có thể propagate mà không có `ATHROW` tường minh | Test implicit exception không được catch |
| Đặt hook trên `this` trước `super()` | Constructor verifier thấy `uninitializedThis` | `-Xverify:all`, `javap -c` constructor |
| Catch handler phủ cả constructor chain | Verifier state không hợp lệ khi init superclass thất bại | Test superclass throwing + frames |
| Một object tương đương một `<init>` | Constructor delegation có thể gọi nhiều `<init>` | Test `this(...)` overload/chaining |
| Bỏ `ACC_SYNCHRONIZED` khi rewrite | Monitor semantics thay đổi, state races | `javap -v`, concurrency test |
| Thêm `monitorenter` cho synchronized method | JVM đã lock implicit; sai balance gây lỗi | Đọc flags/bytecode, monitor assertions |
| Hook chặn hoặc thay exception | Probe failure che business failure | Assert exception type/message/cause |
| Một entry count chứng minh branch coverage | Method-level metrics không chỉ ra true/false edges | Branch-specific cases và coverage tool |
| `LongAdder.sum()` luôn atomic | Đọc trong khi nhiều threads ghi không phải consistent snapshot | Chờ `Future.get()` trước assertion |
| Chỉ nhìn transformer callback | Callback có thể trả `null` hoặc bytes sai | Verify class và test `ProbeRecorder` |
| Thấy `ASSERTIONS_PASSED` ở baseline là đủ | Baseline không chạy hook, có thể bỏ sót lỗi inject | Chạy cả ba chế độ |
| Java source variant thành công là ASM weaver đúng | Bytecode injection có verifier/handler issues riêng | Test actual woven bytes với `-Xverify:all` |
| Probe trong synchronized method miễn phí | Hook kéo dài critical section/lock hold time | Stress, latency và contention metrics |

## 12. Checklist và bài tập vận dụng

Trước khi chấp nhận một phiên bản instrumentation:

- [ ] Có đối chứng baseline, observe-only và inject trên **cùng business suite**?
- [ ] Đã test constructor thành công/thất bại, chaining `this(...)`, superclass initialization và `uninitializedThis`?
- [ ] Tất cả nhánh điều kiện quan trọng và return sites có output/assertions riêng?
- [ ] Có testcase cho primitive/reference/void returns nếu instrumentation áp dụng rộng?
- [ ] Exception được catch **bên trong** method vẫn là success theo method-boundary policy?
- [ ] Explicit throw và implicit exception propagation đều được kiểm thử?
- [ ] Probe exit được gọi đúng một lần và không che/rewrite exception nghiệp vụ?
- [ ] Synchronized method giữ nguyên `ACC_SYNCHRONIZED` và monitor implicit semantics?
- [ ] Test normal/exception synchronized exits, worker concurrency và monitor release?
- [ ] Có `javap -c/-v`, `-Xverify:all` và classfile verifier trên final transformed bytes?
- [ ] Có kiểm tra StackMapTable, max locals/max stack, branch targets và exception table sau weave?
- [ ] Helper classes có visible theo defining loader/module của class đã instrument?
- [ ] Có chạy test trên các JDK/VM versions thực sự deploy và bytecode tools tương thích?
- [ ] Nếu hỗ trợ retransformation, có test chính class đã loaded và giới hạn thay đổi structure?
- [ ] Có theo dõi chi phí probe trong critical section/GC/latency khi dùng thật?

**Câu 1.** Một method có ba return nhưng probe ghi ba entry, chỉ hai exits. Test có pass vì số business output đúng?

**Đáp án:** Không. Phải có đúng một exit mỗi invocation; thiếu một exit làm sai telemetry khi nhánh đó được chạy, dù method output đúng.

**Câu 2.** `20/0` được catch rồi trả `-20`. Có phải method failure?

**Đáp án:** Không theo policy method-boundary của bài. Method hoàn thành bình thường, mặc dù một exception đã xảy ra nội bộ. Đếm throw events là câu hỏi riêng.

**Câu 3.** Probe của constructor đặt sau `Object.<init>`; superclass constructor ném trước đó. Tại sao không thấy failure event?

**Đáp án:** Probe chưa chạy. Không thể suy một event ở sau superclass initialization bao phủ mọi construction attempt; cần xác định rõ phạm vi instrument và giới hạn verifier.

**Câu 4.** Vì sao `synchronized` method không có `monitorenter` nhưng vẫn được lock?

**Đáp án:** JVM kiểm tra cờ `ACC_SYNCHRONIZED` và quản lý monitor **implicit** khi method được invoke/return. `monitorenter`/`monitorexit` là cơ chế bytecode thường thấy trong synchronized block.

**Câu 5.** Trong demo có 800 concurrent `increment(1)` và state cuối là 802. Vì sao probe count sync lại là 804?

**Đáp án:** Ngoài 800 concurrent calls, còn hai normal calls trước đó, một exception call và một final `increment(0)` dùng để đọc state: 800 + 2 + 1 + 1 = 804.

**Câu 6.** Bộ test baseline và observe-only đều pass với mọi probe counter bằng 0. Có thể dừng ở đây?

**Đáp án:** Không. Hai chế độ này chưa có method-body instrumentation; cần mode inject kiểm tra counters và monitor semantics.

**Câu 7.** Có nên đo latency của synchronized method mà bỏ qua probe thời gian trong monitor?

**Đáp án:** Không. Entry/exit advice chạy khi monitor vẫn held, có thể kéo dài critical section; benchmark phải so baseline/inject dưới cùng concurrency và quan sát tail latency.

**Kết luận:** Một bộ ca instrumentation tốt phải hỏi **“bytecode mới còn tuân đúng semantics của Java/JVM không?”** chứ không chỉ “có callback chưa?”. Constructors đòi vị trí advice an toàn sau initialization chain; nhiều nhánh/return đòi exit coverage; exception cần phân loại theo method boundary; synchronized đòi giữ nguyên monitor semantics. **Kết hợp test behavior, counter invariant, verifier và concurrency** mới tạo được bằng chứng đáng tin.

### Tài liệu chính thức

- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback, bytes trả về, `null` và exception semantics.
- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, retransformation và `removeTransformer`.
- [JVMS 17 — 2.11.10 Synchronization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.10): synchronized method với `ACC_SYNCHRONIZED` và implicit monitor.
- [JVMS 17 — 4.6 Methods](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.6): method flags, Code attribute, semantics của `ACC_SYNCHRONIZED`.
- [JVMS 17 — 4.10 Verification](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10): type verification, `uninitializedThis`, `StackMapTable` và exception handlers.
- [JVMS 17 — 6 Instructions](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): `ireturn`/`areturn`/`athrow`/`monitorenter`/`monitorexit` và operand stack semantics.
