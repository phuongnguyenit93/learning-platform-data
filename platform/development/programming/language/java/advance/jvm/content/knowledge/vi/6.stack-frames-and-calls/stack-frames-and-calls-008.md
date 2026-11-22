# `athrow`, bảng xử lý ngoại lệ và tháo frame khi lời gọi thất bại

Java không xử lý ngoại lệ như một giá trị trả về bình thường. Khi một phương thức gặp lỗi và không bắt được, JVM loại frame của lời gọi đó khỏi call stack, tìm tiếp handler phù hợp trong frame của caller. Cơ chế kết hợp **`athrow`**, **`Code.exception_table`** và **frame unwinding** bảo đảm ngoại lệ có thể đi qua nhiều phương thức cho tới khi được xử lý hoặc thread kết thúc.

Bài này thuộc chủ đề **Frame và lời gọi**, giải thích các quy tắc bytecode, cách `try/catch/finally` và `try-with-resources` được biểu diễn, sự khác nhau giữa exceptional completion và normal return, cũng như cách đọc `javap`. Ví dụ chạy được bằng **Java 17+**. Chi tiết class-file và hành vi JVM dựa trên JVMS Java SE 17.

## 1. Phân biệt normal completion với abrupt completion

| Con đường | Điều xảy ra ở callee | Caller nhận gì? |
| --- | --- | --- |
| **Bình thường** | Lệnh `ireturn`, `lreturn`, `freturn`, `dreturn`, `areturn` hoặc `return` hoàn tất lời gọi | Non-`void` có giá trị trả về trên operand stack caller; `void` không có giá trị |
| **Bất thường** | Có exception được ném và callee không có handler phù hợp | **Không có normal return value**; ngoại lệ lan lên caller và được tìm handler tiếp |

Ví dụ:

```java
static int divide(int x, int y) {
    return x / y;
}
```

Với `divide(10, 2)`, phép chia nguyên trả `5`. Với `divide(10, 0)`, opcode chia nguyên `idiv` gây `ArithmeticException`; `ireturn` không hoàn thành, nên caller không nhận số nguyên `0` hay `null` giả làm kết quả.

**Không phải mọi exception đều phát sinh từ từ khóa `throw` trong mã nguồn.** Các instruction như `idiv`, `aaload`, `getfield`, `invokevirtual`, những thao tác truy cập mảng hoặc liên kết lớp có thể gây exception theo quy tắc runtime. Cả exception tường minh và ngầm đều có thể được bắt bởi `exception_table`.

```text
main frame
   └── caller frame (invoke callee)
         └── callee frame
               ├── return bình thường → caller tiếp tục với kết quả
               └── ngoại lệ E
                    ├── handler ngay trong callee → chạy catch tương ứng
                    └── không có handler
                           ↓
                       pop callee frame
                           ↓
                   tìm handler ở caller, tại vị trí invoke
                           ↓
              bắt được → chạy handler | không → pop caller
```

## 2. Opcode `athrow` là gì?

`athrow` có opcode **191** (hexadecimal **`0xbf`**), dùng để ném một object thuộc lớp `java.lang.Throwable` hoặc subclass, chẳng hạn `Exception`, `RuntimeException` hoặc `Error`.

Trước `athrow`, operand stack của frame đang có một giá trị reference tới exception object ở đỉnh:

```text
operand stack trước: [..., exceptionRef]
                           │
                           ▼
                         athrow
                           │
                tìm handler hoặc unwind
```

Nếu ném trong Java:

```java
static void fail() {
    throw new IllegalStateException("bad state");
}
```

Bytecode do `javac` sinh thường chứa mẫu:

```text
new           java/lang/IllegalStateException
dup
ldc           "bad state"
invokespecial java/lang/IllegalStateException.<init>:(Ljava/lang/String;)V
athrow
```

`new` tạo object chưa hoàn tất initialization theo JVM model; `dup` giữ reference trong lúc constructor nhận receiver qua `invokespecial`; cuối cùng `athrow` dùng reference đã được khởi tạo. Đây là trích đoạn **minh họa opcode**, vì output `javap -c` có thêm offset/constant-pool indexes.

### 2.1. `athrow` khác `areturn`

- `areturn` hoàn tất phương thức **bình thường**, trả một reference đúng return descriptor cho caller.
- `athrow` làm phương thức chuyển sang **exceptional control flow**, đi tìm handler; không dùng return descriptor và không trả exception object như một normal result.
- `athrow` có thể ném `Error`; JVM không có opcode riêng tên `throwerror`.
- Checked và unchecked exceptions đều có thể được ném qua cùng cơ chế bytecode; khác biệt checked/unchecked nằm chủ yếu ở quy tắc biên dịch Java.

### 2.2. Nếu operand của `athrow` là `null`?

`athrow` với `objectref = null` sẽ ném **`NullPointerException`**, không phải ném một “exception không có đối tượng”.

```java
static void throwNull() {
    RuntimeException problem = null;
    throw problem;
}
```

Nếu caller catch `NullPointerException` bao quanh lời gọi thì có thể xử lý. Đoạn phương thức trên là ví dụ minh họa; chương trình đầy đủ ở mục 7.

### 2.3. Có exception mà bytecode không có `athrow` ngay tại vị trí lỗi

Trong `return 100 / value;`, phép `idiv` với `value = 0` làm phát sinh exception theo semantics của `idiv`. Không cần lệnh `athrow` tường minh tiếp sau `idiv`. Từ thời điểm đó JVM vẫn tìm handler bằng cùng cơ chế.

Ngược lại, một `catch` có thể `throw ex;`, thường sinh `aload` rồi `athrow` để **rethrow** cùng reference, không nhất thiết tạo một exception object mới.

## 3. Cấu trúc của `Code.exception_table`

Bytecode Java của một phương thức nằm trong **`Code` attribute** của `method_info`. Ngoài `code[]`, `max_stack`, `max_locals`, `Code` còn có `exception_table_length` và mảng **`exception_table[]`**.

Một entry gồm bốn trường `u2`:

```text
exception_table entry
├─ start_pc     // đầu vùng code được bảo vệ
├─ end_pc       // điểm kết thúc mở của vùng
├─ handler_pc   // offset bắt đầu handler
└─ catch_type   // class reference trong constant pool, hoặc 0
```

| Trường | Ý nghĩa chính xác |
| --- | --- |
| **`start_pc`** | Offset instruction đầu tiên có thể được handler áp dụng, **bao gồm** |
| **`end_pc`** | Offset giới hạn cuối, **không bao gồm** |
| **`handler_pc`** | Offset của instruction bắt đầu code handler |
| **`catch_type`** | Constant-pool class index để so kiểu exception, hoặc **0** để match mọi Throwable |

Vùng được bảo vệ là **`[start_pc, end_pc)`**. Nếu `start_pc=2, end_pc=10` thì exception tại opcode bắt đầu ở offset **2 tới trước 10** có thể được entry xử lý; tại opcode offset **10** thì không do entry đó.

`handler_pc` phải trỏ tới **đầu instruction** hợp lệ trong cùng `code[]`, không được trỏ vào byte operand ở giữa instruction. `end_pc` có thể trỏ tới đầu instruction hoặc đúng `code_length` theo ràng buộc của class-file structure.

### 3.1. Cách đọc bảng từ `javap`

Giả sử công cụ hiển thị mẫu:

```text
Exception table:
   from    to  target type
       0     4       5 Class java/lang/NumberFormatException
```

- `from 0` là `start_pc`.
- `to 4` là `end_pc` **exclusive**.
- `target 5` là `handler_pc`.
- Cột `type` là class được catch qua `catch_type`.

Nếu `invokestatic` ở offset 1 gọi phương thức ném `NumberFormatException`, entry có thể match vì 1 thuộc `[0,4)`. Không quan trọng exception có bắt nguồn từ bytecode offset nào của **callee**; khi lan về **caller**, vị trí phải kiểm là offset của **lệnh gọi trong caller**.

### 3.2. `catch_type = 0` không phải kiểu `Object`

Giá trị `0` là sentinel **catch-all**: match bất kỳ throwable nào đang được xử lý tại pc thuộc vùng bảo vệ. `javap` thường in `any`.

Nó **khác**:

- `catch (Throwable t)`: handler bắt type cụ thể `java/lang/Throwable`, thường có non-zero `catch_type` trỏ tới constant pool.
- `catch (Exception e)`: không bắt các loại `Error` chỉ kế thừa `Throwable`.
- `catch (RuntimeException e)`: chỉ bắt loại RuntimeException và subclasses.

`catch_type=0` thường dùng trong bytecode cleanup như `finally` hoặc các đường xử lý monitor. Không thể kết luận một method “nuốt mọi exception” chỉ vì thấy entry `any`: handler có thể cleanup xong **`athrow` lại**.

### 3.3. `Exceptions` attribute khác `exception_table`

`void work() throws IOException` khai báo một phần hợp đồng checked exception ở Java source. Class file có thể lưu loại khai báo qua **`Exceptions` attribute** của method.

`exception_table` lại là **bảng handler thực sự** của `Code`, mô tả runtime catch/cleanup. Method chỉ khai báo `throws` có thể **không có** exception table; method không khai báo `throws` vẫn có thể có try/catch/finally và bảng handler.

## 4. Quy tắc tìm handler: thứ tự và kiểu ngoại lệ

JVM tìm exception handler trong frame hiện tại theo thuật toán:

1. Xác định offset `pc` của instruction nơi exception phát sinh (hoặc vị trí invoke trong frame caller khi exception đã lan lên).
2. Duyệt từng entry `exception_table[]` **theo thứ tự ghi trong bảng**.
3. Kiểm tra `start_pc <= pc < end_pc`.
4. Kiểm tra type: exception là instance của class trong `catch_type` hoặc subclass; `catch_type=0` luôn match type.
5. Chọn **entry đầu tiên thỏa cả vùng và type**. Đặt pc tới `handler_pc`.
6. Không entry nào phù hợp → phương thức kết thúc bất thường, frame bị tháo và tìm ở caller.

### 4.1. JVM không tự chọn “handler hẹp nhất”

Giả sử bytecode của một phương thức có entries cùng vùng:

```text
from to target type
0    15  25     Class java/lang/RuntimeException
0    15  35     Class java/lang/IllegalArgumentException
```

Nếu ném `IllegalArgumentException` ở pc 9, JVM chọn **target 25**, vì RuntimeException ở entry đầu tiên đã match. Nó **không tự bỏ qua** handler đứng trước để tìm subtype cụ thể hơn.

Compiler Java source kiểm tra các catch clauses reachable: đặt catch rộng trước catch hẹp cùng try có thể làm `javac` báo lỗi. Nhưng khi đọc **class file**, quy tắc JVM vẫn là **entry đầu match**; bytecode generator phải lưu đúng thứ tự để không đổi ngữ nghĩa.

### 4.2. Có nhiều vùng bảo vệ chồng nhau thì sao?

Một method có nested try/catch/finally có thể có nhiều entry `[start_pc,end_pc)` chồng lấn. JVM **không** chọn vùng ngắn nhất bằng một thuật toán độc lập. Nó duyệt bảng theo thứ tự và chọn entry đầu tiên match.

Đó là lý do tự ý **sort exception table theo offset hoặc theo class name** trong bytecode instrumentation có thể làm thay đổi hành vi. Nếu handler đang chạy lại ném exception, JVM tra bảng một lần nữa theo pc mới của handler.

## 5. Stack của handler có trạng thái ra sao?

Khi tìm được handler phù hợp:

- JVM đặt pc vào `handler_pc`.
- **Xóa toàn bộ các giá trị cũ trong operand stack** của frame xử lý.
- Đẩy **một reference đến chính exception object** đang ném vào operand stack.
- Chạy instruction đầu của handler.

```text
Trước khi exception xảy ra:
  operand stack: [..., temporary1, temporary2, ...]

Khi chuyển đến handler:
  operand stack: [exceptionRef]      // một phần tử logic

Handler thông dụng:
  astore_1                           // lưu exceptionRef vào local 1
  ...                                // xử lý, return hoặc rethrow
```

**Không có normal return value** được đẩy vào caller stack khi exception lan qua callee. Nếu ở frame caller có handler bắt ngoại lệ, operand stack **của frame caller tại handler** được xóa rồi nhận một reference ngoại lệ.

Local-variable array của **frame đang xử lý** vẫn là local array của nó và phải đáp ứng verifier/StackMapTable. Còn local variables của **các frame đã unwind** không thể được truy cập từ handler của caller.

### 5.1. Vì sao handler hay bắt đầu bằng `astore`?

Java source `catch (IllegalArgumentException e)` cần dùng biến `e`. Vì khi vào handler operand stack chứa exception reference, compiler thường dùng `astore` để đưa reference vào một local slot. Nhưng `astore_1` chỉ là ví dụ; index khác tùy layout. Một cleanup handler cũng có thể lưu exception tạm, làm việc khác rồi load lại cho `athrow`.

## 6. Frame unwinding xuyên qua lời gọi phương thức

Xét chuỗi `top() → middle() → leaf()`:

```java
static int leaf() {
    throw new IllegalArgumentException("negative");
}

static int middle() {
    return leaf();
}

static void top() {
    try {
        System.out.println(middle());
    } catch (IllegalArgumentException ex) {
        System.out.println("handled=" + ex.getMessage());
    }
}
```

Trình tự ở JVM:

```text
1. leaf() chạy, athrow E.
2. Tìm exception_table của leaf: không có handler phù hợp.
3. Pop frame leaf, không trả int.
4. Phục hồi frame middle ở vị trí gọi leaf().
5. Tìm exception_table của middle cho pc của lệnh invoke leaf.
6. Không có handler → pop frame middle, vẫn không trả int.
7. Phục hồi frame top ở vị trí gọi middle().
8. Tìm exception_table của top cho pc của lệnh invoke middle.
9. Có handler catch IllegalArgumentException → top vào handler.
10. Operand stack top tại handler = [E]; handler in message.
```

**Điểm tinh tế:** khi tìm handler của `top`, JVM dùng offset của **instruction gọi `middle` trong `top`**, không phải offset `athrow` của `leaf`. Mỗi method có code array riêng; các offset không dùng chung.

Nếu không frame nào có handler, thread kết thúc do uncaught exception. Uncaught exception handler của thread hoặc runtime có thể báo lỗi. Các thread khác **không nhất thiết cùng chết**, và một JVM có non-daemon threads khác có thể tiếp tục hoạt động.

### 6.1. Stack trace khác với call stack còn sống

Stack trace trên exception có thể ghi lại thông tin những phương thức liên quan tới lúc lỗi xảy ra. Nhưng sau khi unwind, các frame callee đã bị loại khỏi call stack đang chạy. Những dòng stack trace là thông tin chẩn đoán, **không** giữ local variables sống để handler ở caller đọc lại.

## 7. Chương trình Java 17+ đầy đủ: return, `athrow` ngầm và tường minh

Tạo file **`ExceptionFlowDemo.java`**:

```java
public class ExceptionFlowDemo {

    static int leaf(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative");
        }
        return 100 / value;
    }

    static int middle(int value) {
        try {
            return leaf(value);
        } finally {
            System.out.println("middle finally (" + value + ")");
        }
    }

    static void run(int value) {
        try {
            int result = middle(value);
            System.out.println("result=" + result);
        } catch (IllegalArgumentException ex) {
            System.out.println("argument=" + ex.getMessage());
        } catch (ArithmeticException ex) {
            System.out.println("arithmetic=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        run(2);
        run(-1);
        run(0);
    }
}
```

Chạy:

```bash
javac --release 17 ExceptionFlowDemo.java
java ExceptionFlowDemo
```

**Stdout chính xác:**

```text
middle finally (2)
result=50
middle finally (-1)
argument=negative
middle finally (0)
arithmetic=/ by zero
```

Ba đường thực thi:

| Đầu vào | `leaf` | `middle` | `run` |
| --- | --- | --- | --- |
| `2` | Trả `50` qua `ireturn` | Chạy `finally` rồi trả `50` | In `result=50` |
| `-1` | Tạo IllegalArgumentException rồi `athrow` | Chạy `finally` và ném tiếp | Catch IllegalArgumentException, in message |
| `0` | `idiv` ném ArithmeticException ngầm | Chạy `finally` và ném tiếp | Catch ArithmeticException, in `/ by zero` |

Dòng `middle finally (...)` xuất hiện cả trong **normal path** lẫn **exceptional path**. Khi ném lỗi, `middle` không trả `int` giả rồi “báo lỗi song song”; nó **không normal-complete** và ngoại lệ tìm handler ở `run`.

### 7.1. Quan sát bytecode bằng `javap`

```bash
javap -c -p ExceptionFlowDemo
javap -v -p ExceptionFlowDemo
```

Tìm từng nơi:

- `leaf` có `new`, `dup`, `invokespecial`, **`athrow`** ở nhánh âm, và `idiv` ở đường chia.
- `middle` có code đảm bảo `finally` chạy cả hai đường. Compiler thường sinh **catch-all handler** cùng code cleanup và một `athrow` để rethrow.
- `run` có entries trong **Exception table** cho `IllegalArgumentException` và `ArithmeticException`.
- Code của `catch` thường có `astore` lưu exception reference trước khi gọi `getMessage()`.
- `main` gọi `run` ba lần.

Một bảng mẫu minh họa cấu trúc (offset không lấy từ bản build cố định):

```text
Exception table:
  from   to   target   type
     0   12       20   Class java/lang/IllegalArgumentException
     0   12       35   Class java/lang/ArithmeticException
```

Không dùng các offset ví dụ để debug file thật. `javap` từ class do bạn biên dịch mới cho vị trí chính xác.

## 8. Cách `try/catch/finally` được compiler hạ xuống bytecode

### 8.1. `catch` không phải phương thức riêng

`catch (NumberFormatException e)` được hạ thành một hoặc nhiều entry trong `exception_table` và **bytecode handler** trong cùng `Code` attribute của method chứa try/catch. Handler không phải một method tên `catch`.

```java
static int parse(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        return -1;
    }
}
```

Cấu trúc ý tưởng:

```text
try code:
   aload_0
   invokestatic Integer.parseInt
   ireturn
handler:
   astore_1
   iconst_m1
   ireturn
exception_table:
   [try code range) -> handler, catch_type NumberFormatException
```

### 8.2. `finally` không phải opcode JVM

Java compiler sinh đủ code để `finally` chạy theo đường rời `try`/`catch`:

- Khi return bình thường, chạy cleanup rồi đưa normal value về caller.
- Khi ném exception, handler có thể lưu exception tạm, chạy cleanup rồi **`athrow` lại**.
- Với `break`, `continue` hay nhiều exits, compiler tổ chức branches và có thể nhân bản cleanup code.

Ví dụ mô hình catch-all:

```text
Exception table:
  from  to  target  type
     0  10      18  any

18: astore_2
19: ... mã cleanup ...
24: aload_2
25: athrow
```

`any` thường biểu thị `catch_type=0`. Không nên nhìn mỗi chữ `any` rồi kết luận method đã nuốt hết lỗi: ở ví dụ handler **ném lại exception sau cleanup**.

**Không giả định compiler hiện đại luôn dùng `jsr` / `ret` cho finally.** Đó là cơ chế lịch sử, không phải sơ đồ mặc định của `javac` Java 17.

### 8.3. Ngoại lệ hoặc `return` trong chính `finally`

Java `finally` có thể làm thay đổi con đường hoàn tất:

```java
static int unsafe() {
    try {
        throw new IllegalStateException("first");
    } finally {
        return 99;
    }
}
```

Trong trường hợp này, `return` của `finally` có thể **thay thế** việc ném ngoại lệ từ `try`, khiến `unsafe()` trả `99` bình thường. Đây là lý do nên tránh `return` trong `finally`: nó che giấu exception cần điều tra.

Nếu cleanup tự ném exception khác, error đó cũng có thể thay thế exception đang truyền theo quy tắc Java thông thường. Try-with-resources xử lý tình huống đồng thời hai exception bằng **suppressed exceptions**, khác với `finally` tự viết đơn giản.

## 9. `try-with-resources` và `getSuppressed()`

Tạo file **`SuppressedDemo.java`**:

```java
public class SuppressedDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    static void work() throws Exception {
        try (Resource resource = new Resource()) {
            throw new Exception("body failed");
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (Exception ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressed=" + ex.getSuppressed().length);
            System.out.println("suppressed-message=" +
                    ex.getSuppressed()[0].getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 SuppressedDemo.java
java SuppressedDemo
```

Stdout:

```text
primary=body failed
suppressed=1
suppressed-message=close failed
```

Vì thân `try` ném lỗi `body failed` trước và `close()` cũng ném `close failed`, Java giữ lỗi body làm **primary exception** rồi gắn lỗi close dưới dạng **suppressed exception**. Compiler có thể dùng handlers, locals và lời gọi `Throwable.addSuppressed` để bảo đảm hành vi.

`getCause()` và `getSuppressed()` là hai khái niệm khác nhau: cause mô tả chuỗi nguyên nhân, còn suppressed lưu những lỗi thứ cấp xảy ra trong cleanup hoặc hoàn cảnh phù hợp.

**Thực hành:** không dựa vào GC để đóng file/socket/DB connection; dùng `try-with-resources` hoặc cleanup rõ ràng khi tài nguyên cần được đóng theo vòng đời.

## 10. `synchronized` và việc nhả monitor khi ném lỗi

Với **synchronized instance/static method**, JVM quản lý monitor khi method invocation bắt đầu. Khi method kết thúc bất thường, monitor đã được vào cho lời gọi này phải được thoát theo quy tắc của JVM.

Với khối `synchronized (lock)`, compiler thường dùng `monitorenter` / `monitorexit` và handler để thoát monitor trên đường exception:

```java
static void guarded(Object lock) {
    synchronized (lock) {
        throw new IllegalStateException("inside lock");
    }
}
```

Dù câu lệnh trong block ném lỗi, Java vẫn yêu cầu rời synchronized block đúng cách. Một bytecode generator tự chèn `monitorenter` mà quên đường `monitorexit` khi exception xảy ra có thể phá vỡ tính hợp lệ/đúng đắn.

**Không đồng nhất** monitor management với việc `finally` tự đóng mọi loại tài nguyên. Monitor có quy tắc JVM riêng; file handle và network socket cần thao tác đóng rõ ràng.

## 11. Checked và unchecked exceptions đều dùng cùng đường truyền runtime

Java compiler kiểm tra checked exceptions như `IOException` theo quy tắc `catch` hoặc `throws`. Nhưng lúc JVM chạy:

- `athrow` không có một opcode cho checked và opcode khác cho unchecked.
- Handler so **exception object type** với `catch_type` và vị trí `pc`.
- `Exceptions` attribute từ `throws` khác `exception_table` dùng để bắt.
- `Error` và `RuntimeException` cũng có thể được throw/catch theo JVM, dù thiết kế ứng dụng thường không nên catch `Throwable` bao quát.

Ví dụ:

```java
static void checked() throws java.io.IOException {
    throw new java.io.IOException("cannot read");
}
```

Lệnh `throws` giúp kiểm tra ở source/caller, trong khi đường ném thực tế của body vẫn kết thúc bằng `athrow`. Không có typed return đặc biệt cho checked exception.

### 11.1. Thư viện bất đồng bộ có thể đóng gói lỗi

Nếu task trên thread khác ném lỗi, `Future.get()` có thể ném `ExecutionException` bao bọc lỗi task; `CompletableFuture.join()` có thể ném `CompletionException`. Đây là **cơ chế thư viện truyền trạng thái lỗi giữa các task/thread**, không có nghĩa `athrow` trực tiếp vượt từ stack của thread A sang stack thread B.

Mỗi thread có call stack riêng; frame unwinding xử lý dọc chuỗi lời gọi của chính thread hiện tại.

## 12. Đọc stack trace và exception handler đúng công cụ

- **`javap -c -v ClassName`**: xem bytecode, `Code`, `Exception table`, type, handler offsets và `StackMapTable`.
- **Stack trace**: thông tin call chain khi Throwable nhận stack trace, không hiển thị trực tiếp handler table hoặc local-variable array.
- **Debugger**: có thể dừng tại exception throw/catch, xem frame và biến còn sống tùy debug info.
- **`javac -g`**: cung cấp thêm thông tin debug như `LocalVariableTable` giúp tìm tên biến; không biến `exception_table` thành source-level data.

Ví dụ stack trace **chỉ minh họa**:

```text
java.lang.IllegalArgumentException: negative
    at ExceptionFlowDemo.leaf(ExceptionFlowDemo.java:6)
    at ExceptionFlowDemo.middle(ExceptionFlowDemo.java:12)
    at ExceptionFlowDemo.run(ExceptionFlowDemo.java:21)
```

Chương trình ví dụ ở mục 7 **bắt được exception**, nên không tự in stack trace này ra stdout. Các số dòng không nhất thiết trùng với file của bạn.

## 13. Khi chỉnh bytecode, lỗi handler thường xuất phát ở đâu?

Nếu viết ASM/Byte Buddy hoặc instrument class files, cần giữ những bất biến:

1. **`start_pc < end_pc`**, cả `start_pc` và `handler_pc` chỉ vào đầu instruction hợp lệ, `end_pc` chỉ vào đầu instruction hợp lệ hoặc bằng `code_length`.
2. **`catch_type` hợp lệ**: 0 hoặc constant-pool index đến `CONSTANT_Class_info` phù hợp.
3. **Thứ tự bảng giữ đúng semantics**: entry đầu tiên match sẽ thắng; đổi thứ tự có thể thay đổi handler được chạy.
4. **Stack tại handler** có một reference Throwable phù hợp với verification state. Handler không được suy rằng operand stack cũ còn tồn tại.
5. **`StackMapTable` và locals** phải hợp lệ tại đường điều khiển hội tụ theo class-file version.
6. **Monitor cleanup** của synchronized blocks và logic `finally` phải hoạt động trên mọi đường thoát được Java quy định.
7. **Không dùng typed return sai** để che exception hoặc tạo giá trị normal giả.

Vi phạm có thể dẫn tới `ClassFormatError`, `VerifyError` hoặc lỗi khi liên kết/thực thi tùy tính chất. Không có một thông điệp lỗi cố định cho mọi exception table sai.

### 13.1. Ví dụ lỗi `end_pc` exclusive

```text
bytecode offsets:
  0 ...  first protected instruction
  8 ...  last protected instruction
 11 ...  next instruction (outside try)
```

Nếu muốn bảo vệ instruction ở 8 nhưng không bảo vệ instruction ở 11, dùng `start_pc=0, end_pc=11`. Dùng `end_pc=8` lại **bỏ chính instruction ở 8** khỏi vùng bảo vệ.

### 13.2. Tháo frame không có nghĩa mất mọi đối tượng heap

Frame bị unwind không còn hoạt động; local refs trong frame đó không còn là nguồn giữ object theo trạng thái logic. Nhưng object trên heap **có thể vẫn reachable** từ caller, static fields, collections, exception object hoặc nguồn khác. GC không bắt buộc chạy ngay khi frame bị tháo.

Đừng lẫn **frame unwinding** với **garbage collection** hoặc cleanup tài nguyên hệ điều hành.

## 14. Những nhầm lẫn thường gặp

1. **“`athrow` giống `areturn` nhưng trả exception.”** Sai. `athrow` kích hoạt exceptional flow, `areturn` là normal return.
2. **“Mọi exception trong Java đều có chữ `throw` ở đúng dòng lỗi.”** Sai. Runtime có thể ném từ opcode như `idiv` hoặc field access.
3. **“Bảng `exception_table` chứa danh sách exception ghi ở `throws`.”** Sai. `throws` và runtime handler table khác mục đích.
4. **“`end_pc` bao gồm bytecode ở đúng offset đó.”** Sai. Vùng handler là `[start_pc,end_pc)`.
5. **“JVM chọn catch subtype đặc hiệu nhất.”** Sai. Nó tìm **entry đầu tiên** thỏa cả range và type.
6. **“`catch_type=0` là type `Object`.”** Sai. Đây là catch-all sentinel.
7. **“Handler nhận nguyên operand stack ngay trước khi ném.”** Sai. Stack được xóa, chỉ còn một exception reference.
8. **“Không có catch trong callee thì caller nhận `null`.”** Sai. Không có normal return value; ngoại lệ lan tới caller.
9. **“Unwinding luôn tháo hết mọi frame.”** Sai. Dừng khi tìm được handler hợp lệ.
10. **“`finally` là một bytecode instruction.”** Sai. Compiler sinh các đường code và handlers phù hợp.
11. **“`try-with-resources` luôn thay primary exception bằng lỗi `close`.”** Sai. Trong nhiều trường hợp close exception được suppressed.
12. **“Exception không bắt ở một worker luôn giết toàn JVM.”** Sai. Các thread có thể tiếp tục theo vòng đời độc lập.
13. **“Unwind tự đóng mọi stream và socket.”** Sai. Dùng explicit cleanup/try-with-resources.
14. **“Exception object bị tạo lại mỗi khi vượt một frame.”** Sai. Rethrow có thể giữ cùng reference; wrapper exception mới là lựa chọn của code.
15. **“Stack trace là ảnh chụp các live frames hiện có mãi sau khi catch.”** Sai. Nó là thông tin chẩn đoán; nhiều frames đã unwind.

## 15. Tự kiểm tra có đáp án

**Câu 1.** Entry có `start_pc=3, end_pc=10, handler_pc=20`. Exception ở bytecode offset 10 có match entry này không?

**Đáp án:** Không; `end_pc` **exclusive**. Exception ở offset 9 có thể match nếu type phù hợp.

**Câu 2.** Handler `RuntimeException` đứng trước handler `IllegalArgumentException` trong cùng range. Nếu ném `IllegalArgumentException` thì handler nào được chọn?

**Đáp án:** Entry `RuntimeException` đứng trước, vì `IllegalArgumentException` kế thừa `RuntimeException`.

**Câu 3.** Lệnh `athrow` gặp `null` thì sao?

**Đáp án:** JVM ném `NullPointerException`; một handler phù hợp có thể bắt nó.

**Câu 4.** Khi bắt exception ở caller, operand stack của caller tại handler chứa gì?

**Đáp án:** Một exception reference; những giá trị operand khác bị xóa.

**Câu 5.** `leaf` ném ở offset 30, còn caller `top` gọi `leaf` ở offset 5. Handler table của `top` dùng pc nào?

**Đáp án:** Pc của **lệnh invoke trong `top`**, tức 5.

**Câu 6.** Vì sao ví dụ `middle` in dòng `finally` kể cả khi `leaf` ném lỗi?

**Đáp án:** Compiler dùng các nhánh code/handler để thực hiện finally trên cả normal và exceptional exits theo ngữ nghĩa Java, rồi tiếp tục return hoặc rethrow.

**Câu 7.** Trong `SuppressedDemo`, lỗi nào là primary, lỗi nào suppressed?

**Đáp án:** `body failed` là primary; `close failed` là suppressed.

**Câu 8.** Thấy một `exception_table` có `type any`. Có thể kết luận phương thức đã nuốt mọi lỗi?

**Đáp án:** Không. Handler có thể cleanup và thực hiện `athrow` rethrow; cần đọc chính bytecode tại `handler_pc`.

**Câu 9.** Nếu exception không bắt được trong thread xử lý request, mọi thread khác có bắt buộc chết theo không?

**Đáp án:** Không; chính thread đó có thể kết thúc bất thường, còn các thread khác và tiến trình phụ thuộc lifecycle của ứng dụng/runtime.

## 16. Tổng hợp ngắn bằng luồng điều khiển

```text
instruction phát sinh Throwable E
           │
           ▼
   athrow hoặc implicit exception
           │
           ▼
tra exception_table của current frame:
  [start_pc, end_pc) chứa pc?
  catch_type match type E?
  lấy entry ĐẦU TIÊN thỏa
           │
     ┌─────┴─────────┐
     │ Có handler    │ Không
     ▼               ▼
handler_pc         unwind frame
stack = [E]        không normal return
chạy handler       phục hồi caller tại invoke
                   └─ tra handler ở caller, lặp tiếp
```

**Ghi nhớ:** `athrow` dùng để ném đối tượng `Throwable`; bảng `exception_table` cho biết **pc nào được handler nào bảo vệ** và **type nào được phép bắt**. Khi match, operand stack được thiết lập với **một exception reference**. Khi không match, JVM tháo frame và tìm tiếp ở caller **không qua typed return**. `finally`, monitor cleanup và try-with-resources phối hợp với cơ chế này để thực thi đúng ngữ nghĩa Java.

### Tài liệu chuẩn

- [JVMS Java SE 17 — Exceptions (`2.10`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.10): tìm handler, ưu tiên theo thứ tự, tháo frame.
- [JVMS Java SE 17 — Frames and abrupt invocation completion (`2.6`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6).
- [JVMS Java SE 17 — `athrow` (`6.5`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.athrow).
- [JVMS Java SE 17 — `Code` attribute và `exception_table` (`4.7.3`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3).
- [JVMS Java SE 17 — Exception Handling (`3.12`)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-3.html#jvms-3.12).
- [JLS Java SE 17 — Exceptions (`11`)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html).
- [JLS Java SE 17 — `try`, `catch`, `finally` và try-with-resources (`14.20`)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20).
- [JDK 17 `javap` documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
