# Phân biệt mọi lệnh `return` với các đường thoát do ngoại lệ khi thiết kế điểm đo Java

Khi thiết kế một Java agent để đo **thời gian thực thi, số lần gọi, kết quả thành công/thất bại hoặc tracing**, việc đặt điểm đo tại cuối phương thức có vẻ đơn giản. Nhưng ở cấp bytecode, một lần gọi method có thể kết thúc theo **hai cơ chế khác nhau**:

1. **Normal completion**: thực thi tới một trong **sáu opcode return** (`ireturn`, `lreturn`, `freturn`, `dreturn`, `areturn`, `return`).
2. **Abrupt completion**: ngoại lệ hoặc `Error` **thoát khỏi frame của method** mà không được xử lý bên trong method đó.

Hai cơ chế không tương đương. **Bắt đủ tất cả `return` vẫn bỏ sót những lần gọi kết thúc do ngoại lệ**; còn đặt điểm đo tại mọi `athrow` lại có thể **ghi nhầm ngoại lệ được bắt và xử lý nội bộ** thành thất bại của method. Đây là ranh giới phải làm rõ trong phần **Thiết kế điểm đo** của Java instrumentation.

Mục tiêu sau bài học:

- Nhận diện chính xác **sáu opcode trả về bình thường**.
- Hiểu tại sao `athrow` **không** đồng nghĩa “method này chắc chắn thất bại”.
- Thấy được ngoại lệ **ngầm** từ JVM instruction và ngoại lệ **lan truyền** từ method con.
- Thiết kế điểm đo để phân loại **NORMAL / EXCEPTIONAL** theo **kết quả cuối của một lần gọi**, không theo cú pháp `return`/`throw` trong source.
- Chọn chiến lược bytecode/Advice phù hợp và tránh phá operand stack, exception table, `finally`, constructor hoặc trình xác minh bytecode.
- Tự chạy ví dụ Java 17+, kiểm tra `javap` và diễn giải stdout.

## 1. Phải xác định đang đo điều gì

Có ít nhất ba loại sự kiện khác nhau:

| Sự kiện | Câu hỏi trả lời | Có đồng nghĩa method kết thúc bất thường không? |
|---|---|---|
| Một opcode `return` được thực thi | Có nhánh nào trả về bình thường không? | Không; đây là nhánh kết thúc bình thường |
| Một exception được **ném** tại một instruction | Ở đâu đã phát sinh hành vi throw? | Không nhất thiết; exception có thể được catch ngay trong method |
| Một method invocation **hoàn tất bất thường** | Ngoại lệ nào không được giải quyết trong method và thoát tới caller? | **Có**; đây là kết quả exceptional của lần gọi |

Ví dụ:

```java
static int handled() {
    try {
        throw new IllegalStateException("inside");
    } catch (IllegalStateException problem) {
        return 9;
    }
}
```

Source có `throw` và bytecode có `athrow`, nhưng caller nhận được **giá trị 9**. Nếu đếm `athrow` như một “exceptional method exit”, phép đo sẽ **sai**.

Ví dụ ngược lại:

```java
static int callee(int x) {
    return 100 / x;
}

static int caller(int x) {
    return callee(x);
}
```

Với `x == 0`, JVM phát sinh `ArithmeticException` ở phép chia nguyên `idiv` trong `callee`. Khi exception lan ra `caller`, `caller` cũng kết thúc bất thường dù mã bytecode của `caller` **không bắt buộc phải có instruction `athrow`**. Chỉ tìm `athrow` trong `caller` sẽ **bỏ sót** thất bại đó.

**Định nghĩa dùng cho điểm đo:** một lần gọi được ghi `NORMAL` nếu nó thực sự hoàn tất bình thường; được ghi `EXCEPTIONAL` nếu một `Throwable` không bị xử lý nội bộ khiến invocation hoàn tất bất thường. Hai nhãn này nói về **kết quả cuối**, không nói về tất cả exception từng phát sinh bên trong.

## 2. Sáu opcode `return` của JVM: “mọi return” nghĩa là đủ sáu

Theo Java Virtual Machine Specification, các opcode trả về bình thường là:

| Opcode | Kiểu trả về ở bytecode | Ghi chú |
|---|---|---|
| `ireturn` | `int`, `boolean`, `byte`, `char`, `short` | Năm kiểu Java này đều dùng giá trị operand stack dạng `int` ở mức JVM |
| `lreturn` | `long` | Giá trị chiếm hai slot trong operand stack |
| `freturn` | `float` | Một slot |
| `dreturn` | `double` | Hai slot |
| `areturn` | Object reference hoặc array reference | Một slot |
| `return` | `void`, instance initializer `<init>`, class initializer `<clinit>` | Không có giá trị trả về |

Trong ASM, tên hằng thường thấy tương ứng là:

```java
Opcodes.IRETURN
Opcodes.LRETURN
Opcodes.FRETURN
Opcodes.DRETURN
Opcodes.ARETURN
Opcodes.RETURN
```

Đây là **danh sách hằng ASM minh họa**, không phải chương trình độc lập. Với một `MethodVisitor`, muốn đặt lời gọi “normal exit” tại mọi đường trả về thì phải xét **đủ sáu opcode**, chứ không chỉ `RETURN` viết hoa.

Không có opcode JVM riêng mang tên `breturn`, `creturn`, `sreturn` hoặc `booleanreturn`. Các kiểu `boolean`/`byte`/`char`/`short` sử dụng `ireturn`.

### `return` trong Java source không hoàn toàn là một điểm đo bytecode

Một method có nhiều nhánh:

```java
static int choose(int x) {
    if (x < 0) return -1;
    if (x == 0) return 0;
    return 1;
}
```

Compiler có thể tạo **nhiều instruction `ireturn`**. Một điểm đo đặt “sau dòng `return` cuối cùng trong source” không thể bao phủ các nhánh đã trả về trước đó.

Ngược lại, với `try/finally`, compiler có thể **sao chép code `finally` vào nhiều nhánh**, đổi cấu trúc control flow hoặc giữ giá trị trả về tạm thời. Phân tích source để đếm vị trí `return` **không thay thế** việc xác định các opcode thực tế của class đã biên dịch.

> Nguyên tắc: nếu chọn **instruction-level instrumentation**, duyệt và xử lý mọi **return instruction sau biên dịch** thuộc phương thức cần đo, không chỉ lần xuất hiện cuối hoặc mỗi từ khóa `return` trong mã nguồn.

## 3. `athrow` là lệnh ném, không phải “opcode return thứ bảy”

`athrow` (mã opcode `0xbf`) lấy một tham chiếu `Throwable` từ operand stack và kích hoạt quá trình tìm exception handler.

Có hai kết cục:

1. **Có handler phù hợp trong cùng method:** điều khiển chuyển đến handler. Method có thể khôi phục và cuối cùng **return bình thường**.
2. **Không có handler phù hợp trong method:** frame hiện tại bị unwind, exception tiếp tục đi lên caller. Invocation kết thúc **bất thường**.

Ví dụ có handler cục bộ:

```java
static int recovered(int n) {
    try {
        return 100 / n;
    } catch (ArithmeticException problem) {
        return 42;
    }
}
```

Khi `n == 0`, `idiv` phát sinh `ArithmeticException`, nhưng handler bắt được và method hoàn tất với **`42`**. Không được ghi method exit là `EXCEPTIONAL` chỉ vì có exception phát sinh trung gian.

**Quan trọng hơn:** exception không nhất thiết bắt đầu bằng `athrow` trong bytecode của chính method đang đo. JVM có thể phát sinh ngoại lệ khi xử lý instruction:

| Instruction / tình huống | Ngoại lệ ví dụ | Có cần `athrow` hiện diện trong method đó? |
|---|---|---|
| `idiv`, `ldiv` với số chia 0 | `ArithmeticException` | Không |
| `arraylength`, `getfield`, `invokevirtual` trên reference `null` | `NullPointerException` | Không |
| Truy cập phần tử mảng ngoài giới hạn | `ArrayIndexOutOfBoundsException` | Không |
| `checkcast` không tương thích | `ClassCastException` | Không |
| `new` khi cấp phát thất bại | `OutOfMemoryError` | Không |
| `invokestatic`/`invokevirtual` gọi method con rồi con ném exception | Exception truyền ngược từ callee | Không |
| `athrow` từ `throw new ...` trong source | Throwable do code ném tường minh | Có, trong nhánh được biên dịch phù hợp |

Các ví dụ là **khả năng phát sinh**, không phải mọi lần thực thi instruction đều ném ngoại lệ. Một `invoke*` cũng có thể thất bại trong resolution, class initialization hoặc runtime theo quy tắc JVM.

### Không bắt ngoại lệ ở caller thì điều gì xảy ra?

```text
caller() được gọi
    |
    v
invokestatic callee()
    |
    v
callee(): idiv, mẫu số = 0
    |
    v
JVM tạo ArithmeticException
    |
    +-- callee có catch phù hợp? -- Không -> unwind callee
    |
    +-- caller có catch phù hợp? -- Không -> unwind caller
    |
    v
caller() hoàn tất EXCEPTIONAL
```

`caller()` không cần tự `new` exception hoặc chạy `athrow`. Đếm những opcode `athrow` **trong caller** không đủ để quan sát đường thoát bất thường của caller.

## 4. Phân loại theo kết quả cuối: bốn tình huống phải tách biệt

| Mã/diễn biến | Có exception từng xảy ra? | Kết thúc method? | Nhãn exit đúng |
|---|---:|---|---|
| Chạy đến `ireturn`/`areturn`/`return` | Có thể không | Trả về bình thường | `NORMAL` |
| `throw`, không có catch tại method | Có | Unwind tới caller | `EXCEPTIONAL` |
| `throw` hoặc `idiv` lỗi, **được catch** rồi `return` | Có | Trả về bình thường | `NORMAL` |
| Method con ném, method hiện tại không catch | Có | Unwind mà không chạy return opcode của method hiện tại | `EXCEPTIONAL` |

Ngoài ra còn những trường hợp làm thay đổi kết quả cuối:

**`finally` thay thế giá trị `return`:**

```java
static int finallyThrows() {
    try {
        return 8;
    } finally {
        throw new IllegalStateException("finally");
    }
}
```

Ở mức source có `return 8`, nhưng invocation **không trả 8**: `finally` ném exception trước khi hoàn tất bình thường, nên nhãn là `EXCEPTIONAL`.

**`finally` thay thế exception bằng return:** một `finally` có `return` có thể nuốt/ghi đè exception đang chờ truyền ra. Cách viết này nên tránh vì khó hiểu, nhưng khi instrument **kết quả cuối** phải quan sát return thực tế thay vì gắn nhãn thất bại từ exception cũ đã bị thay thế.

**Try-with-resources:** nếu đóng resource ném exception trong lúc một exception khác đã tồn tại, Java có thể giữ primary exception và đưa lỗi đóng resource vào danh sách **suppressed exceptions**. Một invocation kết thúc bất thường chỉ có **một Throwable đang truyền ra** (có thể mang suppressed), không có nghĩa số lỗi bên trong phải bằng số event `EXCEPTIONAL` của method.

**Catch rồi rethrow:** nếu method catch exception và `throw` tiếp ra ngoài, invocation vẫn `EXCEPTIONAL`. Phân loại phải dựa vào việc exception có **thoát khỏi** method hay không.

## 5. Ví dụ Java 17+ chạy được: chín đường thực thi, một bảng kết quả

Ví dụ sau cố ý **không yêu cầu thư viện instrumentation**: nó làm rõ ngữ nghĩa phương thức trước khi triển khai bytecode weaving. Đây là bước test oracle hữu ích: nếu một Java agent phân loại khác với các kết quả này thì điểm đo cần kiểm tra lại.

Tạo thư mục:

```text
exit-path-demo/
└── src/
    ├── ExitCases.java
    └── ReturnKinds.java
```

### 5.1. `src/ExitCases.java` — normal/exceptional và ngoại lệ bị catch

```java
import java.util.function.IntSupplier;

public final class ExitCases {
    private ExitCases() {}

    static int multi(int n) {
        if (n < 0) return -1;
        if (n == 0) return 0;
        return 1;
    }

    static int explicit(int n) {
        if (n < 0) throw new IllegalArgumentException("negative");
        return n;
    }

    static int nullArray(int[] values) {
        return values.length;
    }

    static int helper(int n) {
        return 100 / n;
    }

    static int propagate(int n) {
        return helper(n);
    }

    static int recovered(int n) {
        try {
            return helper(n);
        } catch (ArithmeticException exception) {
            return 42;
        }
    }

    static int localThrowCaught() {
        try {
            throw new IllegalStateException("inside");
        } catch (IllegalStateException exception) {
            return 9;
        }
    }

    static int finallyThrows() {
        try {
            return 8;
        } finally {
            throw new IllegalStateException("finally");
        }
    }

    static void observe(String name, IntSupplier action) {
        try {
            int value = action.getAsInt();
            System.out.println(name + " => NORMAL " + value);
        } catch (Throwable problem) {
            System.out.println(name + " => EXCEPTION "
                    + problem.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        observe("multi(-1)", () -> multi(-1));
        observe("multi(0)", () -> multi(0));
        observe("multi(3)", () -> multi(3));
        observe("explicit(-1)", () -> explicit(-1));
        observe("nullArray(null)", () -> nullArray(null));
        observe("propagate(0)", () -> propagate(0));
        observe("recovered(0)", () -> recovered(0));
        observe("localThrowCaught()", ExitCases::localThrowCaught);
        observe("finallyThrows()", ExitCases::finallyThrows);
    }
}
```

Lưu ý: `observe(...)` là **lớp bọc ở phía caller** nhằm xác nhận kết quả cuối của lời gọi, **không phải một `ClassFileTransformer`**, cũng không tự phân tích bytecode. Nếu caller dùng `observe`, nó chỉ nhìn thấy giá trị/exception đã đi đến caller, không nhìn thấy chính xác các instruction nội bộ hoặc số exception đã được catch ở bên trong.

Từng tình huống trong code:

- `multi`: ba nhánh `ireturn` bình thường.
- `explicit`: `throw new ...` tạo đường `athrow` không bị bắt.
- `nullArray`: `arraylength` trên `null` sinh `NullPointerException` từ instruction JVM.
- `propagate`: method con `helper` chia cho 0, ngoại lệ truyền tới `propagate` **mà không cần `athrow` tại `propagate`**.
- `recovered`: lỗi phép chia bị `catch`, trả `42` bình thường.
- `localThrowCaught`: có `throw` tường minh nhưng catch ngay trong method, trả `9` bình thường.
- `finallyThrows`: `finally` ném và ghi đè giá trị trả về đang chờ, nên kết thúc bất thường.

### 5.2. `src/ReturnKinds.java` — nhìn đủ sáu return opcode

```java
public final class ReturnKinds {
    private ReturnKinds() {}

    public static boolean flag() { return true; }
    public static byte small() { return 7; }
    public static char letter() { return 'A'; }
    public static short shortValue() { return 3; }
    public static int number() { return 5; }
    public static long longValue() { return 10L; }
    public static float floatValue() { return 1.5f; }
    public static double doubleValue() { return 2.5; }
    public static String text() { return "ok"; }
    public static void nothing() {}
}
```

Method `flag`, `small`, `letter`, `shortValue`, `number` đều có opcode kết thúc thuộc **họ `ireturn`**. Các method còn lại lần lượt thể hiện `lreturn`, `freturn`, `dreturn`, `areturn`, `return`.

### 5.3. Biên dịch và chạy với JDK 17+

Mở terminal trong thư mục `exit-path-demo` và chạy:

```bash
mkdir out

javac --release 17 -encoding UTF-8 -d out src/ExitCases.java src/ReturnKinds.java
java -cp out ExitCases
```

`--release 17` yêu cầu JDK 17+ có compiler. `mkdir out` chỉ cần tạo một lần; nếu đã có thư mục, có thể bỏ bước này.

**Stdout chính xác:**

```text
multi(-1) => NORMAL -1
multi(0) => NORMAL 0
multi(3) => NORMAL 1
explicit(-1) => EXCEPTION IllegalArgumentException
nullArray(null) => EXCEPTION NullPointerException
propagate(0) => EXCEPTION ArithmeticException
recovered(0) => NORMAL 42
localThrowCaught() => NORMAL 9
finallyThrows() => EXCEPTION IllegalStateException
```

Điểm học tập nổi bật là:

- `localThrowCaught()` có `athrow` trên đường đã đi qua, **nhưng không phải exceptional exit**.
- `propagate(0)` kết thúc exceptional dù method `propagate` **không có lệnh `throw` trong source**.
- `finallyThrows()` có `return` trong source, **nhưng không normal exit**.
- `recovered(0)` có ArithmeticException trong nội bộ, nhưng kết quả cuối là `NORMAL 42`.

### 5.4. Dùng `javap` quan sát bytecode

```bash
javap -c -p -classpath out ReturnKinds
javap -c -p -classpath out ExitCases
```

`javap -c` in bytecode, `-p` hiển thị cả method không `public`. Trong output của `ReturnKinds`, kiểm tra **opcode cuối** tương ứng:

```text
flag()        -> ireturn
small()       -> ireturn
letter()      -> ireturn
shortValue()  -> ireturn
number()      -> ireturn
longValue()   -> lreturn
floatValue()  -> freturn
doubleValue() -> dreturn
text()        -> areturn
nothing()     -> return
```

Đây là **bảng đối chiếu tóm tắt**, không phải nguyên văn output `javap` (offset và constant-pool index có thể thay đổi).

Trong `ExitCases`, xem các method:

- `explicit(int)`: nhánh tạo exception và có `athrow`.
- `nullArray(int[])`: phép `arraylength` có thể ném NPE mà không cần một `athrow` tường minh.
- `helper(int)`: phép chia nguyên `idiv` có thể ném `ArithmeticException`.
- `propagate(int)`: có lời gọi `helper` rồi đường return bình thường; khi `helper` ném, nhánh return của `propagate` **không được thực thi**.
- `localThrowCaught()`: có `athrow`, **Exception table** dẫn đến handler sau đó method trả về `9`.
- `finallyThrows()`: kiểm tra đoạn code của `finally`; kết quả là exception dù source trong `try` chứa `return`.

`javap` cho phép nhìn thấy lý do “đếm mọi `athrow`” và “đếm mọi `return`” **không thể thay thế định nghĩa method invocation outcome**.

## 6. Thiết kế một điểm đo method exit đúng ngữ nghĩa

Định nghĩa trước **event contract** cho mỗi *method invocation* đủ điều kiện instrument:

```text
METHOD_ENTER(methodId, invocationId, startTime)

METHOD_EXIT_NORMAL(methodId, invocationId, elapsed, returnValue?)
    hoặc
METHOD_EXIT_EXCEPTIONAL(methodId, invocationId, elapsed, throwableType?)
```

Khi agent hoạt động bình thường và vùng instrumented code chạy trọn tới một kết thúc theo định nghĩa, mục tiêu là:

- Một lần **enter**.
- Đúng **một** trong hai loại **exit**.
- Thời gian được tính từ cùng start timestamp đến thời điểm kết thúc thực tế.
- `NORMAL` có thể có hoặc không có giá trị trả về.
- `EXCEPTIONAL` có đối tượng `Throwable` đang thoát khỏi method, nếu có thể quan sát an toàn.
- Không đếm lỗi **đã bị catch và phục hồi** là exceptional exit của method.
- Không được làm thay đổi giá trị trả về, exception gốc hoặc luồng điều khiển do instrumentation gây ra.

Đây là **mục tiêu thiết kế**, không phải bảo đảm tuyệt đối cho JVM termination, sự cố VM hay lỗi của chính agent. Các đường dừng không theo completion của Java method như `Runtime.halt`, `System.exit` khi JVM kết thúc, crash native hoặc kill process không nhất thiết kích hoạt exit advice.

### 6.1. Kết hợp điểm đo normal và exceptional

```text
                           Method entered
                                  |
                                  v
                           Original bytecode
                                  |
                   +--------------+--------------+
                   |                             |
                   v                             v
          Normal return opcode         Throwable không được
          (một trong sáu loại)          xử lý trong method
                   |                             |
                   v                             v
          save return value            exception handler tổng quát
          if needed                    quan sát Throwable
                   |                             |
                   v                             v
          record NORMAL                 record EXCEPTIONAL
                   |                             |
                   v                             v
          restore return value           rethrow Throwable gốc
          emit original return           (athrow)
```

Cần **hai vùng quan sát**: sáu opcode return cho normal, và một cơ chế bao phủ **ngoại lệ thoát khỏi method**. Nếu chỉ làm nửa đầu, phép đo có thiên lệch: những method lỗi hay bị mất event exit và thống kê latency/success rate sẽ sai.

### 6.2. Một số metric nên tách riêng

| Metric | Ý nghĩa | Nguồn |
|---|---|---|
| `invocations` | Số lần method bắt đầu | Entry hook |
| `normal_exits` | Số lần kết thúc bình thường | Hook vào sáu return opcodes |
| `exceptional_exits` | Số lần Throwable không được xử lý tại method | Exceptional-exit handler/advice |
| `duration` | Thời gian của mỗi lần gọi có cặp enter-exit | Timestamp trước/sau một invocation |
| `internal_exceptions` | Exception từng phát sinh *bên trong*, kể cả được catch | Phép đo exception riêng, **khác** method exit |

Không được tự tuyên bố `internal_exceptions == exceptional_exits`. Một method có thể bắt và xử lý nhiều exception rồi trả bình thường; hoặc một exception duy nhất có thể dẫn đến exceptional exit của **nhiều frame** trên call stack.

Nếu tổng hợp `normal_exits + exceptional_exits` để đối chiếu `invocations`, cần xét cả *in-flight* calls và những lần không hoàn tất do process dừng, sampling hoặc lỗi instrumentation.

## 7. Vì sao hook vào mọi `athrow` vẫn sai?

Một chiến lược naive thường viết:

```text
if opcode in {IRETURN, LRETURN, FRETURN, DRETURN, ARETURN, RETURN}:
    record NORMAL
else if opcode == ATHROW:
    record EXCEPTIONAL
```

Chiến lược này có **hai lỗi độc lập**.

### Lỗi A: false positive — `athrow` bị catch ở cùng method

```java
static int handled() {
    try {
        throw new IllegalArgumentException();
    } catch (IllegalArgumentException problem) {
        return 7;
    }
}
```

Bytecode thực thi `athrow`, handler nhận object và sau đó trả `7`. Nếu hook `athrow` ghi exceptional, tiếp theo hook `ireturn` ghi normal, **một invocation có hai nhãn exit** trái với hợp đồng.

### Lỗi B: false negative — ngoại lệ không đi qua `athrow` của method hiện tại

```java
static int wrong(int[] values) {
    return values.length;
}
```

`values == null` gây NPE tại `arraylength`, khiến method unwind **trước khi đạt `ireturn`**, và method này không cần có `athrow`. Hook hai loại instruction không thấy exceptional exit.

Tương tự, một `invoke*` có thể làm current method unwind do method con ném. Việc listener thấy exception ở callee **không chứng minh** current method đã kết thúc — caller còn có thể catch và trả về.

**Kết luận:** `athrow` là một **instruction liên quan đến cơ chế throw**, còn exceptional method exit là **kết quả tìm handler và unwind**. Muốn đo kết quả invocation phải đặt điểm đo theo ranh giới **frame**, không chỉ theo opcode `athrow`.

## 8. Chiến lược bytecode: normal returns + catch-all cho vùng method

Một triển khai bytecode-level điển hình có hai phần bổ sung nhau.

### 8.1. Normal exit: xử lý đủ sáu opcode

Với ASM `MethodVisitor` hoặc API xây bytecode tương đương:

```text
for each instruction in method body:
    if opcode == IRETURN or LRETURN or FRETURN
       or DRETURN or ARETURN or RETURN:
        emit NORMAL probe immediately before this opcode
    emit original instruction
```

Đây là **pseudocode khái niệm**, chưa phải Java chạy độc lập.

Trước `ireturn`/`freturn`/`areturn` có **một slot giá trị** ở top of operand stack; trước `lreturn`/`dreturn` có **hai slot**; trước `return` không có return value.

Nếu probe cần đọc giá trị trả về, phải:

- Lưu vào một local slot phù hợp rồi reload, hoặc dùng thao tác `dup`/`dup2` và giữ đúng stack discipline.
- Không làm biến đổi reference, widening/narrowing hay kiểu operand stack.
- Với `void`, không cố lấy một giá trị không tồn tại.
- Chú ý generic type erasure, bridge methods, method descriptor và verifier.

Một instrumentation sai stack size sẽ sinh `VerifyError` hoặc làm chương trình sai ngữ nghĩa. Vì vậy với ASM nên dùng helper phù hợp như `AdviceAdapter`/`LocalVariablesSorter` hoặc frame computation **đúng điều kiện**, chứ không chèn instruction thủ công mà không hiểu stack.

**Rất quan trọng:** normal probe cần tránh tự ném exception. Nếu chính logger ném trong lúc chuẩn bị return, method sẽ chuyển thành exceptional exit do **instrumentation**, không phải do logic gốc.

### 8.2. Exceptional exit: handler tổng quát cho Throwable **thoát ra**

Ý tưởng:

```text
START_OF_INSTRUMENTED_BODY:
    ... original code, including original exception handlers ...
END_OF_INSTRUMENTED_BODY:

CATCH_ALL_HANDLER(Throwable t):
    recordExceptional(t)
    throw t
```

Mô hình trên là **pseudocode**, không đủ để viết `tryCatchBlock` ASM một cách máy móc. Trong class file thật, exception handler là các entry trong **exception table** với đoạn bytecode được bảo vệ và vị trí handler. Cách dựng vùng được bảo vệ, thứ tự handler và thời điểm thêm code phải được tính toán đúng.

Những nguyên tắc bắt buộc:

1. **Đừng làm mất handler gốc:** `try/catch`, `finally`, `synchronized` và try-with-resources của chương trình phải còn đúng.
2. **Đừng “đánh cắp” ngoại lệ sẽ được handler gốc xử lý:** nếu catch-all được ưu tiên trước handler gốc, một exception nội bộ chưa rời method đã bị ghi nhầm thành exceptional exit. Với các vùng chồng lấn, thứ tự entry trong exception table có ý nghĩa.
3. **Bao phủ cả vùng có thể thoát từ code handler gốc:** exception có thể phát sinh ngay trong một `catch` hoặc `finally`; chỉ bao phủ “thân try đầu tiên” không đủ cho mọi exceptional exit.
4. **Không tự catch lại probe rồi tạo loop:** thông thường tách code đo lường và handler tổng hợp khỏi vùng bảo vệ thích hợp, đồng thời có chiến lược phòng thủ nếu probe thất bại.
5. **Giữ Throwable gốc:** sau khi đo, rethrow chính object đang thoát, không tự thay bằng exception mới nếu mục tiêu là đo không can thiệp.
6. **Cập nhật stack map frames/max stack/max locals đúng cách**, nhất là khi thêm nhánh và handler. Class file hợp lệ là điều kiện tối thiểu.
7. **Tính đúng vùng constructor `<init>`:** trước khi gọi super/constructor khác, `this` còn chưa khởi tạo; không thể áp dụng mọi mẫu handler và advice như trên một method thông thường.
8. **Phân biệt synchronization:** method `synchronized` và block `synchronized` có quy tắc thoát monitor khi normal/exceptional; không phá `monitorexit` và handler được compiler sinh ra.

Nếu chưa có kinh nghiệm trực tiếp viết exception table, nên ưu tiên thư viện hỗ trợ method advice và thử nghiệm trên class bytecode đa dạng. Không tự triển khai một catch-all handler duy nhất rồi cho rằng đã bao phủ mọi method Java.

### 8.3. Chiến lược một điểm kết thúc sau khi hợp nhất control flow

Một số công cụ có thể viết lại nhiều `return` thành đường nhảy đến một epilogue chung. Khi đó điểm đo normal có thể nằm ở epilogue. Nhưng đây là **biến đổi control flow thực sự**:

- Cần bảo toàn kết quả mỗi return, kể cả `long`/`double` hai slot.
- Không được làm sai exception tables, `finally`, frames và monitor.
- Không được biến exceptional unwind thành normal completion.
- Không phải lúc nào hợp nhất mọi nhánh cũng cần hoặc đáng làm.

Nếu chỉ cần số lượng exit và timing, một advice tại mỗi return thường dễ kiểm soát hơn việc viết lại toàn bộ CFG.

## 9. Byte Buddy: `OnMethodExit` mặc định không bao phủ exceptional exit

Byte Buddy cung cấp abstraction `Advice` để thêm logic tại method entry và exit. Một chi tiết rất quan trọng trong API:

**`@Advice.OnMethodExit` mặc định chỉ chạy khi method kết thúc bình thường.** Để yêu cầu advice chạy cả khi method kết thúc bằng `Throwable`, chỉ rõ:

```java
@Advice.OnMethodExit(onThrowable = Throwable.class)
public static void onExit(@Advice.Thrown Throwable thrown) {
    if (thrown == null) {
        System.out.println("[advice] NORMAL");
    } else {
        System.out.println("[advice] EXCEPTIONAL "
                + thrown.getClass().getSimpleName());
    }
}
```

Đây là **method advice minh họa**, không phải chương trình standalone. Nó phải nằm trong class có import `net.bytebuddy.asm.Advice` và phải được **thực sự áp dụng** lên method mục tiêu thông qua Byte Buddy/agent hoặc quá trình tạo class phù hợp.

`@Advice.Thrown` nhận throwable thoát khỏi instrumented method, hoặc `null` nếu method trả bình thường. `onThrowable = Throwable.class` yêu cầu bao gồm cả các subclass `Error`, không chỉ `Exception`. Trong các phiên bản Byte Buddy mới, cách cấu hình này được ghi rõ trong Javadoc `Advice.OnMethodExit`.

Những lưu ý:

- Nếu **không có** `onThrowable = Throwable.class`, advice kết thúc bình thường **không đủ** để đo số lần method thất bại.
- Không tự sửa `@Advice.Thrown` (ví dụ qua writable binding) để nuốt exception trừ khi đó là yêu cầu nghiệp vụ có chủ ý; thay exception là đổi ngữ nghĩa.
- Không giả định advice có cùng độ phủ ở constructor đặc biệt, native/abstract method hoặc các method không được thực sự instrument.
- Logging qua `System.out` trong advice chỉ phù hợp để học. Trong môi trường production, nên dùng tracer/metric recorder nhẹ, có bảo vệ reentrancy và tránh ném exception.
- Đây là **một lựa chọn triển khai**, không phải thuộc tính tự có của JVM `ClassFileTransformer`.

Với một instrumenter dựa trên ASM, cần tự đảm bảo cả hai loại đường thoát như mục 8. Với Byte Buddy Advice đã cấu hình phù hợp, thư viện cung cấp sự trừu tượng hóa hợp đồng exit, nhưng vẫn phải test các ca khó.

## 10. `finally` có phải là điểm đo exit tốt nhất?

`finally` chạy khi rời vùng `try` trong các trường hợp bình thường và nhiều trường hợp bất thường. Tuy nhiên **một hook `finally` đơn thuần không tự phân biệt nguyên nhân**:

```java
static int sample(int x) {
    try {
        if (x == 0) return 0;
        return 100 / x;
    } finally {
        System.out.println("finally");
    }
}
```

Với `x == 0`, `finally` chạy rồi method trả bình thường; với `x != 0` và phép chia bình thường, cũng chạy; nếu phép chia ném, `finally` vẫn chạy rồi exception tiếp tục đi ra. **Cùng một dòng log** không cho biết event cuối là `NORMAL` hay `EXCEPTIONAL`.

Trong nguồn Java, có thể thiết kế wrapper dùng `try`, `catch(Throwable)` và `finally` cùng một biến trạng thái, nhưng phải cẩn thận:

- Nếu biến trạng thái được gán “success” **trước khi hoàn tất `finally`**, rồi chính `finally` ném exception, nhãn có thể sai.
- Nếu logging trong finally ném, nó có thể **ghi đè exception gốc**.
- Với `try-with-resources`, việc đóng resource có thể đổi kết quả hoặc thêm suppressed exceptions.
- Dựng lại chính xác semantics trong bytecode cần nhiều hơn một lời gọi vào cuối `try`.

Khi đo **method exit**, nên xác nhận kết quả sau khi tất cả cleanup liên quan đã thực sự xảy ra, theo control flow của class file đã biên dịch.

## 11. Cách giữ ngữ nghĩa và độ tin cậy cho điểm đo

Một agent quan sát tốt nên có các bất biến rõ ràng:

### 11.1. Không thay đổi kết quả

- Nếu code gốc trả giá trị `v`, caller vẫn phải nhận `v`.
- Nếu code gốc ném Throwable object `t`, caller vẫn phải nhận chính `t` (nếu không có chính sách sửa đổi riêng).
- Advice không được tự ý đổi `null` thành giá trị khác, nuốt exception hay bọc Throwable vào exception mới.
- Khi đo method có `void`, outcome vẫn có thể là `NORMAL` mặc dù không có return value.

### 11.2. Không đếm hai lần

Nếu một method có `athrow` cục bộ được catch rồi đi tới `ireturn`, phải chỉ ghi **một normal exit** của invocation đó. Nếu method không catch và unwind, chỉ ghi **một exceptional exit** của invocation đó.

Nếu có nhiều agent hoặc advice được đăng ký trùng, event có thể bị nhân đôi; cần quản lý cấu hình instrumentation và nhận dạng một invocation.

### 11.3. Không để phép đo ném exception

Trong sản phẩm thực tế, tránh ghi log đồng bộ phức tạp ngay tại return hoặc exception handler; tốt hơn dùng recorder nhẹ, buffer có giới hạn, sampling và cơ chế xử lý lỗi không làm hỏng chương trình. Một lỗi logger có thể biến normal exit thành exceptional exit, tạo sai lệch dữ liệu **và** hành vi ứng dụng.

Dùng `Throwable` trong handler quan sát để bao phủ cả `Error`, nhưng không nên vô điều kiện **nuốt** những lỗi nghiêm trọng như `OutOfMemoryError`. Phân biệt “ghi nhận rồi truyền tiếp” với “bắt rồi xử lý”.

### 11.4. Tương quan enter và exit

Ghi một ID hoặc ngữ cảnh cho lần gọi, ví dụ:

```text
traceId | invocationId | methodId | outcome | durationNs | errorType
```

Tránh đặt `Throwable` hoặc toàn bộ stack trace thành nhãn metric có độ phân biệt cao (*high cardinality*). Có thể ghi tên kiểu exception vào trace/log đã sampling, còn metric tổng hợp dùng các nhãn ổn định.

Một exception có thể unwind qua **nhiều methods được instrument**: mỗi method có **một exceptional exit riêng** nếu exception thực sự rời frame của method đó. Đó là **nhiều invocation thất bại**, không phải việc ném nhiều exception object khác nhau.

## 12. Giới hạn cần ghi rõ: “mọi return” vẫn không phải mọi cách JVM dừng

Một số trường hợp đặc biệt:

| Trường hợp | Hệ quả khi instrument |
|---|---|
| `native` hoặc `abstract` method | Không có `Code` attribute Java bytecode để đặt hook vào return instruction của method đó |
| Constructor `<init>` | Bị ràng buộc bởi uninitialized `this` trước `super(...)`; cần logic advice chuyên biệt |
| Class initializer `<clinit>` | Có opcode `return` khi thành công; lỗi khởi tạo có ngữ nghĩa exception riêng |
| Method có `synchronized` | Monitor phải được giải phóng đúng khi hoàn tất bình thường/bất thường |
| `try-with-resources` | Cleanup có thể ném, đổi Throwable chính hoặc thêm suppressed exceptions |
| Reflection, lambda, method handle, bridge method | Cần xác định method/class nào thực sự được instrument; không suy theo tên source בלבד |
| JVM crash, `Runtime.halt`, kill process | Không có bảo đảm nhận được method exit event |
| `System.exit` được phép kết thúc JVM | Có thể dừng tiến trình trước khi bất kỳ return/exceptional hook nào chạy |
| Agent được attach sau khi class đã load | Chỉ đăng ký transformer không tự biến đổi class đã load; cần retransform/redefine khi được hỗ trợ |
| Multiple class loaders/module boundaries | Cùng tên method có thể có nhiều định nghĩa class, nên nhận dạng theo loader/module phù hợp |

**Điểm đo ở opcode** phải tách khỏi **điểm đo ở Java source**. JIT và tối ưu runtime có thể thay đổi cách thực thi nội bộ, nhưng hợp đồng bytecode và đường exception mà JVM phải giữ là nền tảng để agent đúng về ngữ nghĩa. Không dựa vào offset instruction cố định giữa các phiên bản compiler.

Ngoài ra, một method chạy rất lâu hoặc chưa trả cũng chưa có exit; số `enter` nhiều hơn `normal + exceptional` tại một thời điểm không tự động chứng minh bị mất event.

## 13. Checklist QA cho một agent đo method exit

Dùng bảng này khi review code instrumentation:

| Nội dung kiểm tra | Kỳ vọng |
|---|---|
| Bao phủ sáu return opcodes? | Có `IRETURN`, `LRETURN`, `FRETURN`, `DRETURN`, `ARETURN`, `RETURN` |
| Exceptional exit có được quan sát? | Có handler/advice bao phủ Throwable **thoát khỏi method** |
| Có nhầm `athrow` cục bộ là method failure? | Không |
| Ngoại lệ ngầm từ `idiv`/`arraylength`/`invoke*` được phát hiện? | Có, nếu thực sự gây abrupt completion |
| Exception bị catch trong method rồi trả về? | Ghi `NORMAL` |
| Exception bị rethrow ra caller? | Ghi `EXCEPTIONAL` |
| `finally` đổi kết quả cuối? | Phân loại theo kết cục sau cleanup |
| Giá trị return được bảo toàn? | Đúng cả một-slot và hai-slot |
| Throwable gốc được bảo toàn? | Có; không nuốt/đổi nếu chỉ làm phép đo |
| Handler mới có làm sai handler gốc không? | Không; exception table priority và vùng được bảo vệ phải đúng |
| Có nguy cơ recursion hoặc logger throwing? | Có biện pháp phòng vệ |
| Verifier/StackMapTable qua được? | Class sau sửa được JVM nạp, chạy thử |
| Có nhiều overload, bridge, constructor, native? | Có phạm vi/ngoại lệ được tài liệu hóa |
| Kết quả quan sát có khớp bài test? | Đủ các case normal, explicit, implicit, propagated, caught, finally |

### Gợi ý bộ kiểm thử tự động

Một test suite nghiêm túc nên gồm ít nhất:

1. `int` nhiều nhánh, có nhiều `ireturn`.
2. `void` method và method trả Object (`return`/`areturn`).
3. `long` và `double`, đảm bảo không sai stack two-slot.
4. `throw new ...` không được catch.
5. Ngoại lệ ngầm `arraylength` trên `null`.
6. Ngoại lệ ngầm `idiv` chia cho 0.
7. Exception ném ở method con rồi truyền qua method cha.
8. Exception được catch nội bộ rồi method trả bình thường.
9. Exception bị catch rồi rethrow.
10. `finally` ghi đè return, `finally` ghi đè exception hoặc có suppressed exceptions.
11. Constructor/synchronized/try-with-resources nếu thật sự thuộc phạm vi agent.
12. Chạy với và không với agent; so sánh kết quả/Throwable type và số event cho **từng invocation**.

Không chỉ khẳng định “agent chạy không crash” là đủ. Điều cần chứng minh là **mỗi invocation thuộc phạm vi được gắn nhãn đúng theo kết quả thực tế**.

## 14. Bài tập tư duy

**Câu 1.** Có mấy opcode dùng để trả về bình thường ở JVM, và `boolean` thuộc opcode nào?

**Đáp án:** Sáu: `ireturn`, `lreturn`, `freturn`, `dreturn`, `areturn`, `return`. `boolean` dùng `ireturn`.

**Câu 2.** Method có `throw` trong `try`, `catch` bên trong rồi `return 9`. Có nên ghi exceptional method exit khi thấy `athrow`?

**Đáp án:** Không. Method hoàn tất bình thường với 9; `athrow` là throw event nội bộ được xử lý.

**Câu 3.** Method `return values.length;` với `values == null` có nhất thiết chứa `athrow` trong bytecode không?

**Đáp án:** Không. JVM có thể phát sinh `NullPointerException` tại `arraylength`; method không đạt `ireturn` và có exceptional exit.

**Câu 4.** Method `caller()` chỉ gọi `helper()` rồi trả kết quả. Nếu `helper()` ném và `caller()` không catch, có cần `athrow` trong `caller()` để đo failure không?

**Đáp án:** Không. Exception lan truyền qua frame `caller`, làm invocation hoàn tất bất thường.

**Câu 5.** Vì sao chỉ instrument `RETURN` là sai?

**Đáp án:** `RETURN` chỉ dùng cho void/initializer; các method trả primitive/reference dùng năm opcode khác.

**Câu 6.** Vì sao nên đặt catch-all handler sau logic handler gốc và thiết kế vùng bảo vệ cẩn thận?

**Đáp án:** Nếu catch-all bắt trước, exception lẽ ra được code gốc xử lý sẽ bị đánh dấu sai là exceptional exit, và có thể làm thay đổi control flow.

**Câu 7.** Nếu `@Advice.OnMethodExit` không khai báo `onThrowable`, nó mặc định đo những trường hợp nào?

**Đáp án:** Chỉ method kết thúc bình thường. Muốn quan sát cả exceptional completion, dùng cấu hình thích hợp như `onThrowable = Throwable.class`.

**Câu 8.** Có 100 method invocations, trong đó 10 method catch exception rồi trả bình thường và 5 invocation khác để exception truyền ra ngoài. Bao nhiêu exceptional exits?

**Đáp án:** 5, theo điều kiện tất cả 100 invocations đã hoàn tất và các 5 exceptional là năm invocation khác nhau; 10 trường hợp đã catch/return được tính normal.

**Câu 9.** Method có `return 8` trong `try`, nhưng `finally` ném `IllegalStateException`. Event cuối là gì?

**Đáp án:** `EXCEPTIONAL`; return đang chờ đã bị exception từ finally thay thế.

**Câu 10.** Vì sao một `Throwable` có thể dẫn tới nhiều `EXCEPTIONAL` method-exit events?

**Đáp án:** Nó có thể lần lượt unwind qua nhiều method frames không catch; mỗi invocation đó đều kết thúc bất thường, dù exception object là một.

## 15. Kết luận cần nhớ

- **Mọi normal return ở bytecode có sáu opcode**, không phải một.
- **`athrow` không phải exceptional method exit**: exception có thể được catch ngay trong cùng method.
- **Exceptional exit không nhất thiết có `athrow` trong method**: JVM có thể ném ngầm hoặc exception từ callee có thể truyền qua.
- Phân loại phải dựa vào **kết quả cuối của invocation** sau `catch`, `finally`, cleanup và quá trình unwind.
- Một thiết kế instrumentation đúng thường cần **normal-return advice + exceptional-exit advice/handler**, không chỉ chèn log vào `return`.
- Duy trì tính đúng của stack, exception table, verifier, constructor/monitor semantics và Throwable gốc là bắt buộc.
- Ví dụ Java 17+ cùng `javap` giúp kiểm tra hai nhóm đường thoát trước khi triển khai agent thực tế.

## Tài liệu tham khảo

- Oracle Java SE 17, [The Java Virtual Machine Specification — Normal and Abrupt Method Invocation Completion (§2.6.4–§2.6.5)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html).
- Oracle Java SE 17, [The Java Virtual Machine Specification — Method Invocation and Return Instructions (§2.11.8)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.8).
- Oracle Java SE 17, [The Java Virtual Machine Specification — Instruction Set, including `athrow` and return opcodes](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html).
- Oracle Java SE 17, [Exception handlers and their search order (§2.10)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.10).
- Oracle Java SE 17, [The Java Language Specification — Exceptions and handling](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html).
- Byte Buddy, [`Advice.OnMethodExit` — `onThrowable` behavior](https://javadoc.io/static/net.bytebuddy/byte-buddy/1.18.2/net/bytebuddy/asm/Advice.OnMethodExit.html).
- Byte Buddy, [`Advice.Thrown` — observed thrown value or null](https://javadoc.io/static/net.bytebuddy/byte-buddy/1.18.2/net/bytebuddy/asm/Advice.Thrown.html).
