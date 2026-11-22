# Quản lý vị trí biến cục bộ, nhãn nhảy và đường đi ngoại lệ bằng Class-File API

## 1. Mục tiêu và phiên bản Java

Trong mã Java, ta quen viết biến cục bộ, `if`, `while`, `try/catch` và `finally`. Khi tạo hoặc sửa classfile, JVM không nhìn thấy những cấu trúc nguồn ấy như các đối tượng cú pháp Java. JVM thực thi **lệnh bytecode** với hai vùng chính: **bảng local variable slots** và **operand stack**, di chuyển điều khiển bằng **nhảy tới bytecode index (BCI)**, và xử lý lỗi bằng **exception table**.

Java **Class-File API** (`java.lang.classfile`) được chuẩn hóa trong **JDK 24** (JEP 484). Với `CodeBuilder`, ta có API để:

- Lấy đúng slot của `this`/tham số và **cấp phát slot cục bộ mới** với `parameterSlot(...)`, `receiverSlot()`, `allocateLocal(TypeKind)`.
- Phát lệnh nạp/lưu theo kiểu: `iload`, `istore`, `aload`, `astore`, `lload`, `lstore`, hoặc `loadLocal`/`storeLocal`.
- Tạo **nhãn trừu tượng** bằng `newLabel()`, gắn nhãn vào vị trí bằng `labelBinding(label)`, phát nhảy điều kiện/vô điều kiện (`ifeq`, `ifne`, `goto_`...), và định nghĩa phạm vi gỡ lỗi.
- Khai báo **exception table entry** với `exceptionCatch(tryStart, tryEnd, handler, catchType)` hoặc `exceptionCatchAll(...)`; đảm bảo stack tại handler và đường chạy bình thường đều hợp lệ.
- Để API tạo **StackMapTable** khi cần, sau đó xác minh bằng JVM verifier, thử cả nhánh thường lẫn nhánh ngoại lệ.

**Yêu cầu chạy ví dụ trong bài:** JDK **24 trở lên**, không cần `--enable-preview` khi dùng API đã chính thức từ JDK 24. Không thể dùng `javac --release 17` để biên dịch mã trực tiếp gọi `java.lang.classfile`; **Java 17 không có API chuẩn này**. Khái niệm JVM slots/labels/exception table vẫn áp dụng cho classfile do Java 17 tạo ra, nhưng ví dụ Java nguồn dùng Class-File API phải biên dịch với JDK 24+ và target API phù hợp.

## 2. Bức tranh: local slots, operand stack và control flow

Mỗi *frame* của một method JVM chứa hai cấu trúc cần phân biệt:

| Thành phần | Cách truy cập | Vai trò | Ví dụ |
|---|---|---|---|
| **Local variable array** | Chỉ số `slot` | Giữ `this`, tham số và giá trị cục bộ | `iload(0)`, `istore(2)` |
| **Operand stack** | Push/pop theo lệnh | Đầu vào/đầu ra trung gian của phép toán | `iload` đẩy `int` lên stack; `idiv` lấy 2 `int` và đẩy thương |
| **Program counter/BCI** | Instruction offset | Chỉ thị lệnh kế tiếp hoặc đích nhảy | `ifeq(label)`, `goto_(label)` |
| **Exception table** | Khoảng BCI và handler | Khi lỗi được ném từ vùng được bảo vệ, JVM tìm handler phù hợp | `[tryStart, tryEnd) → handler` |

Ví dụ phép tính `result = a / b` ở mức khái niệm:

~~~text
Local slots:                 Operand stack:
slot 0: a                   []
slot 1: b

iload(0)                    [a]
iload(1)                    [a, b]
idiv()                      [a / b]      hoặc ArithmeticException
istore(resultSlot)          []           resultSlot chứa thương
~~~

**Điểm mấu chốt:** `istore(slot)` không phải lệnh “tạo biến Java”; nó lấy một `int` từ operand stack và ghi vào slot của frame. `allocateLocal` là thao tác của *builder* để chọn một chỉ số slot mới cho mã được xây; nó không tạo ra một vùng heap hay một biến Java runtime riêng.

Số slot và độ sâu operand stack là hai đại lượng khác nhau. Trong classfile, thuộc tính `Code` có `max_locals` và `max_stack`. Xem được qua `CodeAttribute.maxLocals()`, `maxStack()` khi đọc một classfile đã xây.

## 3. Quản lý vị trí biến cục bộ đúng cách

### 3.1. Slot của tham số: static khác instance

Đối với method **instance**, `slot 0` dành cho tham chiếu `this`. Các tham số theo sau, nhưng `long` và `double` cần **hai slot liên tiếp**. Với method **static**, không có `this`.

Xét chữ ký minh họa:

~~~java
void process(int count, long timestamp, double ratio)
~~~

Bố cục locals của method instance:

| Slot | Nội dung |
|---|---|
| 0 | `this` (reference) |
| 1 | `count` (`int`) |
| 2–3 | `timestamp` (`long`, category 2) |
| 4–5 | `ratio` (`double`, category 2) |
| 6 trở đi | Có thể cấp phát locals mới |

Nếu cùng chữ ký nhưng là `static`:

| Slot | Nội dung |
|---|---|
| 0 | `count` |
| 1–2 | `timestamp` |
| 3–4 | `ratio` |
| 5 trở đi | Có thể cấp phát locals mới |

Không nên tự tính index bằng công thức `paramNo + 1`. `CodeBuilder.parameterSlot(int paramNo)` nhận **số thứ tự tham số tính từ 0**, rồi tự xét receiver và độ rộng kiểu; `receiverSlot()` chỉ dùng cho method instance và ném `IllegalStateException` đối với method static.

Phần mã sử dụng `CodeBuilder` dưới đây là **đoạn minh họa nằm trong callback builder**, chưa phải chương trình độc lập:

~~~java
int slotOfFirstParam = code.parameterSlot(0);
int slotOfSecondParam = code.parameterSlot(1);
int temporaryInt = code.allocateLocal(TypeKind.INT);
int temporaryLong = code.allocateLocal(TypeKind.LONG);
int temporaryObject = code.allocateLocal(TypeKind.REFERENCE);
~~~

`allocateLocal(TypeKind.LONG)` hoặc `allocateLocal(TypeKind.DOUBLE)` cần đủ **hai** ô liên tiếp. Builder có chính sách tìm slot khả dụng; không nên hard-code chỉ số tiếp theo bằng `previous + 1`. Khi *transform* một method đã tồn tại, API cố tránh đụng locals cũ, thường bắt đầu locals mới ở sau `max_locals` của method gốc.

### 3.2. Chọn đúng opcode theo loại dữ liệu

| Loại trong JVM | Nạp từ local | Lưu vào local | Độ rộng local |
|---|---|---|---:|
| `int` và các kiểu `boolean/byte/char/short` ở computational level | `iload(slot)` | `istore(slot)` | 1 |
| Reference (`Object`, array, exception...) | `aload(slot)` | `astore(slot)` | 1 |
| `long` | `lload(slot)` | `lstore(slot)` | 2 |
| `double` | `dload(slot)` | `dstore(slot)` | 2 |
| `float` | `fload(slot)` | `fstore(slot)` | 1 |

Ví dụ đúng khi có `int resultSlot`:

~~~java
code.iload(code.parameterSlot(0))
    .iload(code.parameterSlot(1))
    .iadd()
    .istore(resultSlot);

code.iload(resultSlot)
    .ireturn();
~~~

Sau `iadd()`, operand stack có một `int` để `istore` pop xuống slot. Nếu thay `istore` bằng `astore`, kiểu stack và kiểu opcode không tương thích, khiến class không thể được kiểm chứng đúng.

### 3.3. Local slot khác LocalVariableTable

`CodeBuilder.allocateLocal(...)` quản lý **slot cho mã máy ảo**, còn `CodeBuilder.localVariable(...)` tạo **metadata gỡ lỗi** trong `LocalVariableTable`, ví dụ:

~~~java
code.localVariable(
    resultSlot,
    "result",
    ConstantDescs.CD_int,
    scopeStart,
    scopeEnd
);
~~~

Đây là đoạn minh họa thuộc một `CodeBuilder` có sẵn các biến `resultSlot`, `scopeStart`, `scopeEnd`. Nó **không cấp phát** slot mới và **không sinh lệnh `istore`**. Vì thế:

- Phải cấp phát slot/nạp/lưu đúng ngay cả khi không có debug attribute.
- Phải đặt `scopeStart`/`scopeEnd` tại vị trí phù hợp; phạm vi debug là **nửa mở** `[start, end)`.
- `ClassFile.DebugElementsOption.DROP_DEBUG` có thể làm dữ liệu debug bị bỏ qua. Đừng dựa vào tên biến debug để bảo đảm semantics runtime.
- Với kiểu generic, `localVariableType(...)` có thể ghi signature; khi có type entry, thường cũng cần local variable entry với descriptor theo type erasure.
- Một slot có thể được tái sử dụng cho các local có vòng đời không giao nhau, nhưng quá trình phân tích verifier/type frame vẫn phải hợp lệ trên tất cả nhánh hợp nhất.

**Sai lầm phổ biến:** nghĩ mỗi tên biến Java là một slot mới mãi mãi. Slot là ô có thể tái sử dụng khi vòng đời cho phép; tên chỉ là thông tin tùy chọn cho debugger.

## 4. Nhãn nhảy: `Label` là vị trí, không phải số dòng

### 4.1. Vì sao không tự cộng BCI?

Instruction bytecode có kích thước không đồng đều: `iload_0` khác `iload <index>`, opcode có thể dùng dạng `wide`, `goto` có dạng mở rộng `goto_w`, và `tableswitch/lookupswitch` cần alignment/padding. Nếu tự tính offset ngay lúc viết lệnh, chỉ cần thêm một instruction trước đó là các nhánh và exception table bị lệch.

`Label` giải quyết vấn đề này: là **marker trừu tượng của một vị trí**. Khi dựng classfile, builder quy đổi nhãn sang vị trí BCI phù hợp.

- `code.newLabel()`: tạo **unbound label**; có thể tham chiếu từ nhảy trước khi đặt vị trí.
- `code.labelBinding(label)`: gắn nhãn chưa bind vào **vị trí hiện tại**.
- `code.newBoundLabel()`: tạo nhãn và bind ngay tại vị trí hiện tại.
- `code.startLabel()` và `code.endLabel()`: nhãn có sẵn cho đầu/cuối block hiện tại.
- `CodeAttribute.labelToBci(label)`: khi đọc một `CodeAttribute` hoàn chỉnh, chuyển một nhãn thuộc attribute đó sang BCI.

**Phải bind nhãn được dùng** trong builder tương ứng, và không bind cùng một nhãn hai lần. Nhãn từ một `CodeModel` khi transform không tự động có vị trí tương ứng trong builder mới; cần ánh xạ hoặc bind theo contract.

### 4.2. Nhảy điều kiện và merge point

Để biểu diễn logic `if (a == 0) result = 0; else result = a/b;`, có thể tạo nhãn `whenZero` và `afterIf`:

~~~text
iload(a)
ifeq whenZero
     |
     | a != 0
     v
iload(a), iload(b), idiv, istore(result)
goto afterIf
whenZero:
iconst_0, istore(result)
afterIf:
iload(result), ireturn
~~~

Khi dịch sang builder, **đặt nhãn ngay trước instruction là đích cần chạy**:

~~~java
Label whenZero = code.newLabel();
Label afterIf = code.newLabel();

code.iload(aSlot).ifeq(whenZero);
code.iload(aSlot).iload(bSlot).idiv().istore(resultSlot);
code.goto_(afterIf);

code.labelBinding(whenZero)
    .iconst_0()
    .istore(resultSlot);

code.labelBinding(afterIf)
    .iload(resultSlot)
    .ireturn();
~~~

Đoạn này giả định `aSlot`, `bSlot`, `resultSlot` đã có và được cấp phát đúng. `ifeq` **lấy một `int` khỏi stack** để kiểm tra bằng 0; nhảy có điều kiện không giữ bản sao `a` trên stack. Do đó khi thực hiện phép chia, phải `iload(aSlot)` lại.

Ở điểm nhập nhánh `afterIf`, tất cả đường tới đó cần có **stack height và verification types tương thích**. Trong ví dụ, cả hai đường đều lưu giá trị vào `resultSlot` trước khi nhập nhánh, nên tại `afterIf` stack rỗng và `resultSlot` có kiểu `int`.

### 4.3. Nhảy vô điều kiện và tên method Java

`goto` là keyword của Java (dù không được sử dụng trong source language), nên factory của `CodeBuilder` được đặt tên `goto_(label)`. Tương tự `return_()` đại diện cho opcode `return` của method `void`. Các method chuyên biệt như `ireturn()` dùng cho trả `int`.

Có thể dùng:

~~~java
code.branch(Opcode.GOTO, afterIf);
~~~

hoặc `code.goto_(afterIf)`. Nếu đích nhảy quá xa cho dạng ngắn, tùy chọn `ClassFile.ShortJumpsOption` ảnh hưởng cách builder mở rộng nhảy. Không nên tự chèn giá trị BCI hoặc tự sửa bytes opcode nhảy.

### 4.4. Nhánh hợp lệ khác dead/unreachable code

Một chuỗi như:

~~~text
ireturn
iconst_1
ireturn
~~~

chứa đoạn không thể tới bằng control flow thường. Với classfile mới có StackMapTable, **dead code** và frame inference có thể khiến việc tạo stack map thất bại tùy tùy chọn. Xây CFG có đường đi hợp lệ, tránh để handler bị fall-through ngoài ý muốn. Các tùy chọn `ClassFile.DeadCodeOption` hoặc `ClassFile.StackMapsOption` là công cụ hỗ trợ khi đã hiểu cấu trúc mã, không phải cách để che lỗi đồ thị điều khiển.

## 5. Exception table: vùng bảo vệ, handler và tính nửa mở

### 5.1. Bytecode không có “try block” như cú pháp Java

Ở cấp classfile, một entry của `exception_table` có bốn phần chính:

| Trường | Ý nghĩa |
|---|---|
| `start_pc` | BCI bắt đầu vùng có handler, **bao gồm** |
| `end_pc` | BCI kết thúc vùng có handler, **không bao gồm** |
| `handler_pc` | BCI bắt đầu phần mã xử lý ngoại lệ |
| `catch_type` | Kiểu exception được bắt, hoặc 0 để bắt tất cả |

Với Class-File API:

~~~java
code.exceptionCatch(
    tryStart,
    tryEnd,
    catchStart,
    ClassDesc.of("java.lang.ArithmeticException")
);
~~~

Ba `Label` đại diện cho các điểm BCI. Hợp đồng `[tryStart, tryEnd)` có nghĩa lệnh ngay tại `tryEnd` không còn nằm trong vùng bảo vệ của entry đó.

Một helper khác:

~~~java
code.exceptionCatchAll(tryStart, tryEnd, catchAllStart);
~~~

tạo entry bắt mọi `Throwable` (exception và error). **Catch-all không tự tạo semantics của Java `finally`**: nếu dùng để mô phỏng `finally`, người xây bytecode phải tự phát lệnh cleanup, lưu/rethrow exception, đồng thời xử lý cả đường chạy bình thường, `return` và các cạnh điều khiển có liên quan.

### 5.2. Handler bắt đầu với một exception reference trên operand stack

Khi một lệnh trong vùng try ném ngoại lệ khớp `catch_type`:

1. JVM tìm exception table entry phù hợp theo thứ tự.
2. Stack tại lối vào handler chứa **một reference đến exception vừa bị ném**.
3. Handler thường bắt đầu bằng `astore(exceptionSlot)` để pop reference vào local, hoặc dùng trực tiếp object trên stack theo hợp đồng.
4. Handler chạy mã xử lý; nếu cần đi tới điểm join, phải đưa stack và locals về trạng thái phù hợp.

Minh họa:

~~~text
tryStart:
    ... phép toán có thể ném ArithmeticException ...
tryEnd:
    goto done           # đường thường bỏ qua handler
catchStart:
    astore(errorSlot)    # top stack ban đầu là exception object
    iconst_m1
    istore(resultSlot)
done:
    iload(resultSlot)
    ireturn
~~~

Nếu bỏ `astore(errorSlot)` rồi ngay lập tức `iload(resultSlot)`, stack còn exception ở trên cùng: verifier có thể từ chối hoặc instruction hoạt động không như ý. Nếu bỏ `goto done` trên đường bình thường, luồng có thể **rơi vào handler dù không có exception**, làm lỗi semantics và stack shape.

### 5.3. Thứ tự nhiều handler và kiểu bắt

Nếu một vùng code có `catch (IllegalArgumentException)` và `catch (RuntimeException)`, handler đặc thù cần được khai báo đúng thứ tự ưu tiên. JVM xét exception table theo thứ tự; một handler rộng có thể “nuốt” cơ hội của handler hẹp nếu đặt trước.

~~~text
tryStart..tryEnd:
  1) IllegalArgumentException -> handlerA
  2) RuntimeException         -> handlerB
  3) catch-all                -> handlerFinal
~~~

Nếu có các vùng try lồng nhau, cần xem độ ưu tiên entry, phạm vi bảo vệ và nhánh ra khỏi block. Một `exceptionCatch` chỉ tạo entry, **không** đảm bảo tự sinh mã ở handler, hay dọn stack, chạy finally, đóng resource và ném lại exception.

Đừng dùng `catch-all` một cách tùy tiện để “bảo đảm agent không crash”: bắt cả `Error` có thể che các vấn đề nghiêm trọng. Với code instrumentation, lựa chọn catch/finally cần đúng hợp đồng vận hành và giữ hành vi gốc của method.

### 5.4. Dùng builder cấp cao khi phù hợp

Ngoài các primitive `newLabel`/`labelBinding`/`exceptionCatch`, `CodeBuilder` còn có `trying(...)` và `CatchBuilder.catching(...)`/`catchingAll(...)` để xây các block có cấu trúc. Builder cấp cao giúp bớt quản lý thủ công các nhãn break/handler, nhưng người viết vẫn phải bảo đảm đúng **semantics** của cleanup, exception flow và return path.

Các ví dụ ở phần tiếp theo cố ý dùng nhãn và exception table trực tiếp để cho thấy chính xác ba cơ chế mà bạn cần nắm.

## 6. Ví dụ JDK 24+ đầy đủ: locals, nhảy và ArithmeticException

Ta sẽ tự **sinh một classfile**, nạp class đã sinh vào JVM, rồi gọi method qua reflection. Không cần Java agent hay thư viện bytecode bên ngoài, vì mục tiêu là tập trung vào `CodeBuilder` và bytecode control flow.

Method tạo ra có chữ ký:

~~~java
public static int eval(int a, int b)
~~~

Hành vi thiết kế:

~~~text
nếu a == 0:       trả 0 (fast path, không thực hiện phép chia)
ngược lại:
    thử a / b
    nếu ArithmeticException: trả -1
~~~

Thí nghiệm bao phủ cả **nhảy điều kiện**, **nhảy tránh catch**, **local slots**, **typed exception handler** và **điểm hợp nhánh**.

### 6.1. Tạo tệp `ClassFileFlowDemo.java`

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.Label;
import java.lang.classfile.TypeKind;
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.MethodTypeDesc;
import java.lang.reflect.Method;

public final class ClassFileFlowDemo {

    private ClassFileFlowDemo() {}

    private static byte[] buildClass() {
        ClassDesc generated = ClassDesc.of("demo.GeneratedMath");

        return ClassFile.of().build(generated, classBuilder ->
                classBuilder
                    .withFlags(ClassFile.ACC_PUBLIC)
                    .withSuperclass(ConstantDescs.CD_Object)
                    .withMethodBody(
                        "eval",
                        MethodTypeDesc.of(
                            ConstantDescs.CD_int,
                            ConstantDescs.CD_int,
                            ConstantDescs.CD_int),
                        ClassFile.ACC_PUBLIC | ClassFile.ACC_STATIC,
                        code -> {
                            // Method static eval(int a, int b):
                            // parameterSlot(0) = 0, parameterSlot(1) = 1.
                            int aSlot = code.parameterSlot(0);
                            int bSlot = code.parameterSlot(1);

                            // Cấp phát locals MỚI ngoài vùng tham số.
                            int resultSlot = code.allocateLocal(TypeKind.INT);
                            int errorSlot =
                                    code.allocateLocal(TypeKind.REFERENCE);

                            Label tryStart = code.newLabel();
                            Label tryEnd = code.newLabel();
                            Label catchStart = code.newLabel();
                            Label fastZero = code.newLabel();
                            Label done = code.newLabel();

                            // [tryStart, tryEnd): vùng được catch bảo vệ.
                            code.labelBinding(tryStart);

                            // if (a == 0) goto fastZero;
                            code.iload(aSlot).ifeq(fastZero);

                            // Đường a != 0: result = a / b.
                            code.iload(aSlot)
                                .iload(bSlot)
                                .idiv()
                                .istore(resultSlot)
                                .goto_(done);

                            // Đường a == 0: result = 0.
                            code.labelBinding(fastZero)
                                .iconst_0()
                                .istore(resultSlot);

                            code.labelBinding(tryEnd)
                                .goto_(done); // Tránh rơi vào handler.

                            // JVM chuyển vào handler với exception
                            // reference trên đỉnh operand stack.
                            code.labelBinding(catchStart)
                                .astore(errorSlot)
                                .iconst_m1()
                                .istore(resultSlot);

                            // Điểm hợp nhánh: stack rỗng, result int.
                            code.labelBinding(done)
                                .iload(resultSlot)
                                .ireturn();

                            // Tạo exception table entry.
                            code.exceptionCatch(
                                tryStart,
                                tryEnd,
                                catchStart,
                                ClassDesc.of(
                                    "java.lang.ArithmeticException"));

                            // Metadata cho debugger; không tạo slot.
                            code.localVariable(
                                resultSlot,
                                "result",
                                ConstantDescs.CD_int,
                                tryStart,
                                done);
                        }));
    }

    private static Class<?> loadGenerated(byte[] bytes) {
        // Một class loader nhỏ để định nghĩa generated class;
        // không cần ghi file .class xuống đĩa.
        return new ClassLoader(
                ClassFileFlowDemo.class.getClassLoader()) {
            Class<?> defineGenerated() {
                return defineClass(
                    "demo.GeneratedMath",
                    bytes,
                    0,
                    bytes.length);
            }
        }.defineGenerated();
    }

    private static int call(Method method, int a, int b)
            throws ReflectiveOperationException {
        return (int) method.invoke(null, a, b);
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = buildClass();
        Class<?> generatedClass = loadGenerated(bytes);
        Method eval = generatedClass.getMethod(
                "eval", int.class, int.class);

        System.out.println("eval(12,3)=" + call(eval, 12, 3));
        System.out.println("eval(0,0)=" + call(eval, 0, 0));
        System.out.println("eval(5,0)=" + call(eval, 5, 0));
    }
}
~~~

**Vì sao đây là chương trình hoàn chỉnh?** Nó tự tạo `demo.GeneratedMath` bằng `ClassFile.of().build(...)`, tự định nghĩa class qua `ClassLoader#defineClass` và tự gọi static method. Không yêu cầu class `demo.GeneratedMath` có mặt trên classpath trước, không cần tệp manifest hay agent; input chỉ có một tệp nguồn `ClassFileFlowDemo.java`.

### 6.2. Biên dịch và chạy

Mở terminal trong thư mục chứa đúng tệp trên, với JDK 24:

~~~bash
javac --release 24 ClassFileFlowDemo.java
java -Xverify:all ClassFileFlowDemo
~~~

Tương tự, khi dùng JDK mới hơn có hỗ trợ `--release 24`, có thể giữ target 24 để dùng API tương ứng. Nếu chỉ có JDK 17 hoặc JDK 21, lệnh sẽ không thành công vì `java.lang.classfile` chuẩn chưa có trong các bản ấy.

**Kết quả stdout mong đợi:**

~~~text
eval(12,3)=4
eval(0,0)=0
eval(5,0)=-1
~~~

Tại sao:

- `12 / 3` đi qua nhánh chia bình thường, lưu thương 4 vào `resultSlot` rồi tới `done`.
- `a = 0` khiến `ifeq(fastZero)` nhảy vào nhánh đặt 0; `b = 0` lúc đó không quan trọng vì **không thực thi `idiv`**.
- `5 / 0` thực hiện `idiv` và ném `ArithmeticException`. JVM tìm entry `[tryStart, tryEnd)`, chuyển tới `catchStart` cùng reference exception trên stack. `astore(errorSlot)` pop exception, rồi ghi `-1` vào `resultSlot`.
- Tất cả các đường tới `done` có **operand stack rỗng** và một `int` hợp lệ trong `resultSlot`, nên `iload(resultSlot).ireturn()` xử lý thống nhất.

Ví dụ đã được kiểm tra trực tiếp trên một JDK 24 đối với phần lõi `ClassFile.of().build`, `allocateLocal`, nhãn nhảy, `exceptionCatch`, `localVariable` và việc định nghĩa/gọi class động, cho kết quả `4,0,-1`. Chương trình nguồn dạng tệp ở trên vẫn nên được người học chạy bằng hai lệnh `javac`/`java` để kiểm thử môi trường của mình.

### 6.3. Bảng trạng thái locals và stack ở các điểm quan trọng

Với method static `eval(int a, int b)` mới được xây:

| Mốc | Locals có ý nghĩa | Operand stack | Đi tiếp |
|---|---|---|---|
| Vào method | `a` ở slot 0; `b` ở slot 1 | `[]` | `tryStart` |
| Trước `ifeq` sau `iload(a)` | Chưa có result | `[a]` | Pop `a` để so sánh |
| Nhánh a != 0, trước `idiv` | `a, b` trong locals | `[a, b]` | Chia hai số |
| Sau `istore(result)` thành công | `result = a/b` | `[]` | `goto done` |
| Nhánh `fastZero` sau `istore` | `result = 0` | `[]` | `goto done` |
| Vừa vào `catchStart` | `result` chưa nhất thiết đã được ghi ở đường lỗi | `[ArithmeticException]` | `astore(error)` |
| Sau `astore(error)` và `istore(result)` | `error` lưu exception; `result = -1` | `[]` | `done` |
| Tại `done` | `result` có kiểu `int` trên mọi đường | `[]` | `iload` rồi `ireturn` |

Nếu đổi một nhánh để đến `done` khi `result` chưa được định nghĩa, hoặc để stack còn dữ liệu khác nhau ở các predecessor, verifier/stack-map generation có thể phản ánh lỗi. Đây là lý do không thể chỉ nhìn cú pháp Java của `CodeBuilder` mà khẳng định bytecode hợp lệ.

## 7. Quản lý StackMapTable và verifier ở nơi giao nhánh

Từ classfile version hiện đại, `StackMapTable` mô tả trạng thái verification types tại những vị trí quan trọng của control flow. JVM verifier kiểm tra khả năng hợp nhất frame của các nhánh và của handler.

Đối với API JDK 24:

- `ClassFile.StackMapsOption.STACK_MAPS_WHEN_REQUIRED` là **mặc định**: API tạo stack maps hoặc tái sử dụng khi tương thích.
- `ClassFile.StackMapsOption.GENERATE_STACK_MAPS` buộc tạo mới; hữu ích khi muốn phát hiện sớm lỗi biểu diễn graph/frame.
- `ClassFile.StackMapsOption.DROP_STACK_MAPS` bỏ tạo stack maps; **không phù hợp mặc định** với method hiện đại có nhảy/handlers nếu bạn không tự cung cấp attribute tương ứng.
- Tính toán stack maps có thể báo lỗi với unreachable code hoặc kỹ thuật nhảy di sản. Đừng dùng “drop stack maps” chỉ để che lỗi; JVM có thể từ chối class tại link/verify time.

Ví dụ kiến trúc khi cần ép tính toán lại:

~~~java
ClassFile classFile = ClassFile.of(
    ClassFile.StackMapsOption.GENERATE_STACK_MAPS
);
~~~

Đây là **đoạn cấu hình minh họa**, không phải một chương trình hoàn chỉnh. Từ `classFile`, bạn có thể gọi `build(...)` như ví dụ chính. Không cần bật tùy chọn này cho bài thực hành; mặc định đã tạo stack maps khi cần.

### 7.1. Quy tắc merge frame

Ở mỗi label nhận nhiều đường nhảy:

1. **Stack height** của mọi predecessor phải tương thích.
2. **Kiểu của stack entries** phải hợp nhất được theo verifier.
3. **Local variable verification types** phải hợp nhất được; slot chưa khởi tạo trên một nhánh không thể được đọc như kiểu `int` trên nhánh khác.
4. Cả nhánh bình thường lẫn nhánh ngoại lệ phải được xét, không chỉ các đường `if/else`.
5. Với constructor, trạng thái `uninitializedThis` và lời gọi `<init>` có quy tắc riêng; không nên áp dụng đơn giản logic của static method cho mọi constructor.

Vì lý do đó, đoạn sau là **phản ví dụ**:

~~~text
if (condition) goto done
iconst_1
done:
ireturn
~~~

Một đường tới `done` có `int` trên stack, đường kia không có: operand stack không thống nhất. Cách sửa là để mọi đường đều tạo giá trị (hoặc lưu vào slot) trước điểm merge.

### 7.2. Khi class gốc thuộc loader/module lạ

Nếu bạn biến đổi class qua `CodeTransform` trong Java agent, việc sinh stack maps có thể phải giải quyết quan hệ type ở các class do custom class loader/module layer định nghĩa. `ClassFile.ClassHierarchyResolverOption` cho phép cung cấp resolver phù hợp ngữ cảnh. Không mặc định system class loader có thể resolve toàn bộ kiểu của plugin/OSGi/application server; nếu resolver nhìn sai hierarchy, kết quả verification có thể không khớp runtime đích.

Ví dụ tĩnh dùng `int` và `ArithmeticException` chuẩn của Java nên tránh hầu hết khó khăn này, thích hợp làm bước học đầu tiên.

## 8. Khi chuyển từ build mới sang transform một method đã có

Đối với classfile sẵn có, bạn có thể đọc `ClassModel`, tìm `MethodModel` và `CodeModel` rồi dùng `CodeTransform` để phát lệnh mới. Bài toán khó không nằm ở việc copy bytearray đơn thuần, mà ở việc giữ **toàn bộ những tham chiếu đến vị trí code** nhất quán.

Cần kiểm tra:

- **Existing locals:** method gốc đã dùng `max_locals`; locals mới không được đè tham số hoặc biến còn sống. `allocateLocal` giúp lấy slot an toàn hơn việc chọn một số cố định.
- **Branch targets:** nhãn từ `CodeModel` cũ không tự bind trong builder mới; khi copy/transform, phải chuyển nhãn và bind đúng nơi. Đừng nhảy bằng offset cũ sau khi chèn instruction.
- **Exception ranges:** thêm instruction **trước hay sau** một label đầu/cuối try có thể làm nó nằm trong/ngoài handler, ảnh hưởng semantics khi chính instrumentation code ném lỗi.
- **Handlers:** nếu chèn event logging ở đầu handler, nhớ stack đầu vào là exception reference. Logging helper có thể ném lỗi và làm exception gốc mất dấu nếu không bảo vệ thích hợp.
- **LineNumberTable/LocalVariableTable:** debug attributes dùng nhãn/vị trí; `DebugElementsOption`, `LineNumbersOption` và thứ tự bind ảnh hưởng chúng có được bảo toàn hay không.
- **Stack maps:** thêm nhánh hoặc local reference có thể đổi frame. Sử dụng chế độ sinh stack maps tương thích và verifier, không giả định table gốc luôn còn đúng sau transform.
- **Synchronized method/monitor:** `monitorenter` và `monitorexit`, exception paths, early return phải cân bằng; một early return mới có thể làm mất cleanup.

**Không đồng nhất `LocalVariableTable` với runtime local array.** Method không có thông tin debug vẫn có `max_locals` và `iload/istore`; một agent chỉ dựa vào tên biến trong LocalVariableTable sẽ thất bại khi class đã bị strip debug symbols.

### 8.1. Cân nhắc chèn mã ở ranh giới try

Giả sử method gốc có:

~~~text
tryStart:
    callBusiness()
tryEnd:
    goto done
handler:
    ...
~~~

Nếu instrument thêm `logEnter()`:

- Chèn **trước `tryStart`**: ngoại lệ do logEnter thường không thuộc protected range của handler này.
- Chèn **sau `tryStart`**: logEnter có thể được handler bắt, làm thay đổi behavior, kể cả khiến exception của agent bị xử lý như exception nghiệp vụ.
- Chèn ở đầu handler: operand stack đang chứa exception, nên nếu helper muốn gọi API khác cần giữ hoặc lưu object ấy trước.
- Chèn trước `return` trong vùng try: mọi đường return phải được instrument; code logging cũng có thể ném lỗi hoặc thêm locals/stack.

Đây là lý do một transformer chuyên nghiệp phải quyết định **chính xác ranh giới bảo vệ** của instrumentation code và cách khôi phục ngoại lệ gốc. Đừng gắn nhãn tùy tiện chỉ để code “compile được”.

### 8.2. Try-with-resources không chỉ là một catch-all

Java source `try-with-resources` còn có semantics đóng resource theo thứ tự, xử lý exception chính và `suppressed exceptions`. Tự tạo một `exceptionCatchAll` và gọi `close()` không đủ để tái tạo mọi tình huống. Khi cần bảo toàn semantics của chương trình gốc, ưu tiên transform có cấu trúc, kiểm thử đầy đủ nhánh thường/ngoại lệ và xem bytecode được `javac` tạo cho trường hợp tương đương.

## 9. Đọc và quan sát classfile đã xây

Class-File API có các model phù hợp cho kiểm tra:

| Model/API | Thông tin |
|---|---|
| `ClassFile.of().parse(byte[])` | Trả `ClassModel` từ classfile bytes |
| `ClassModel.methods()` | Các `MethodModel` của class |
| `MethodModel.code()` | `Optional<CodeModel>` đối với method có code |
| `CodeModel.exceptionHandlers()` | Danh sách `ExceptionCatch` |
| `CodeAttribute.maxLocals()` | Số local slots tối đa trong Code attribute hoàn chỉnh |
| `CodeAttribute.maxStack()` | Độ sâu operand stack tối đa |
| `CodeAttribute.labelToBci(label)` | BCI cho nhãn thuộc CodeAttribute đó |

Đoạn kiểm tra khái niệm bên dưới giả định `bytes` là classfile đã tạo; là **mảnh code minh họa**, không phải chương trình độc lập:

~~~java
var model = ClassFile.of().parse(bytes);
var method = model.methods().stream()
    .filter(m -> m.methodName().stringValue().equals("eval"))
    .findFirst().orElseThrow();

var code = method.code().orElseThrow();
System.out.println(code.exceptionHandlers().size());
~~~

Với method `eval` của ví dụ chính, danh sách exception handlers được thiết kế có **một** entry typed `ArithmeticException`. Khi cần xem mã máy JVM chi tiết, có thể lưu bytes vào đường dẫn `demo/GeneratedMath.class` rồi chạy `javap -c -v` trên class đã lưu; không nhầm class file động với file của `ClassFileFlowDemo.class` do javac tạo.

Lưu ý rằng `LineNumberTable` và `LocalVariableTable` là dữ liệu debug tùy chọn; một công cụ phân tích không nên coi việc thiếu chúng là lỗi classfile.

## 10. Các lỗi thường gặp và cách gỡ

### Lỗi 1: hard-code slot trùng tham số hoặc giá trị còn sống

~~~java
// Sai nếu slot 1 đang giữ tham số b của eval(int a,int b):
code.iconst_0().istore(1);
~~~

Hậu quả: thay đổi giá trị tham số hoặc phá type state. Dùng `parameterSlot` để lấy tham số, `allocateLocal(TypeKind)` để tạo slot mới.

### Lỗi 2: quên `long`/`double` cần hai slots

Đối với method static `m(int, long, double)`, chỉ số tham số lần lượt là 0, 1, 3; không phải 0, 1, 2. Dùng `parameterSlot(paramNo)` thay vì tính thủ công.

### Lỗi 3: nhầm local array và operand stack

`istore(resultSlot)` cần có một `int` trên top stack. `iload` mới đưa local lên stack. Không thể gọi `ireturn()` khi stack rỗng hoặc chứa exception reference.

### Lỗi 4: tạo label nhưng không bind

~~~java
Label target = code.newLabel();
code.goto_(target);
// Không đặt labelBinding(target): sai.
~~~

Với label được sử dụng, builder cần biết vị trí đích. Dùng `labelBinding(target)` tại điểm thích hợp và chỉ bind một lần.

### Lỗi 5: bind handler ngay sau try mà không nhảy vòng

Nếu đường bình thường rơi xuống lệnh đầu handler, nhưng top stack không có exception reference, `astore(exceptionSlot)` sẽ thiếu operand đúng kiểu. Thêm `goto_(afterHandler)` hoặc tổ chức block khác để luồng thường bỏ qua handler.

### Lỗi 6: dùng nhãn kết thúc try sai phạm vi

`[tryStart, tryEnd)` loại trừ instruction tại `tryEnd`. Nếu bind `tryEnd` quá muộn, bạn có thể vô tình bắt exception do chính mã instrumentation; bind quá sớm thì một instruction nghiệp vụ quan trọng không nằm trong protected range.

### Lỗi 7: quên handler entry stack có một exception

Khi nhảy vào catch do exception, stack chứa thrown object. Phải tiêu thụ/lưu nó đúng cách, đặc biệt trước các lệnh mới có yêu cầu stack rỗng.

### Lỗi 8: nhánh nhập chung nhưng locals chưa được khởi tạo

`resultSlot` phải có giá trị hợp lệ trên **mọi** đường tới `done`. Nếu nhánh `fastZero` không `istore(resultSlot)`, một đường tới `iload(resultSlot)` dùng uninitialized local.

### Lỗi 9: chọn catch-all như cách triển khai `finally` hoàn chỉnh

Catch-all chỉ tạo **exception table entry**. Muốn có `finally`, còn phải xử lý đường thường, đường return, throw và các cạnh điều khiển khác, và phải giữ nguyên exception theo semantics cần bảo toàn.

### Lỗi 10: bỏ `StackMapTable` để hết lỗi build

Lỗi stack-map generation thường báo vấn đề thực trong control-flow graph hoặc type merge. Class hiện đại có nhánh/handler thiếu frame hợp lệ có thể bị `VerifyError`. Nên sửa CFG và xác minh dưới `-Xverify:all`.

### Lỗi 11: kỳ vọng Java 17 biên dịch được Class-File API chuẩn

`java.lang.classfile` chính thức từ JDK 24. Với Java 17, có thể dùng thư viện bytecode tương thích như ASM/Byte Buddy cho một mục tiêu instrumentation khác, nhưng **không thể** copy nguyên ví dụ JDK24 và chạy với `javac 17`.

### Lỗi 12: chỉ chạy “happy path”

Một method có `idiv` phải kiểm thử mẫu số 0, đồng thời kiểm thử nhánh fast path. Đường exception handler có thể chưa bao giờ được verify thực sự trong những test không kích hoạt lỗi.

## 11. Checklist kiểm định bytecode trước khi phát hành

| Bước | Câu hỏi | Cách xác nhận |
|---|---|---|
| Phiên bản API | Runtime/compiler có từ JDK 24? | `java -version`, `javac -version` |
| Tham số | `this` và tham số chiếm slot nào? | `receiverSlot()`, `parameterSlot(...)` |
| Locals mới | Có đè biến đang sống hoặc slot category-2 không? | `allocateLocal(TypeKind)` |
| Opcode | Kiểu nạp/lưu/trả về phù hợp stack? | `iload/istore`, `aload/astore`, `ireturn/areturn` |
| Nhãn | Mọi nhãn được dùng đã bind đúng một lần? | Review `newLabel/labelBinding` và kiểm tra build |
| Branch merge | Stack height/types hợp lệ trên mọi predecessor? | Stack-map generation và JVM verifier |
| Try range | `tryStart` bao gồm lệnh nào? `tryEnd` loại lệnh nào? | Xem vị trí label; `[start, end)` |
| Exception handler | Có reference trên stack lúc vào handler? | `astore(exceptionSlot)` hoặc xử lý tương đương |
| Normal path | Có bypass handler không? | `goto_(done)` hoặc graph tương ứng |
| Catch priority | Handler hẹp và rộng có thứ tự đúng? | Review thứ tự exception table |
| Debug | Local variable scope có nhãn đúng? | `localVariable(...)` và chính sách debug attributes |
| StackMapTable | Frame có đúng mọi branch/handler? | Default stack maps, `-Xverify:all` |
| Hành vi | Đường bình thường và exception có kết quả đúng? | Test `eval(12,3)`, `eval(0,0)`, `eval(5,0)` |
| Agent/loader | Helper và class đích có đúng loader/module? | Test runtime thực nếu nhúng vào agent |
| Thay đổi method cũ | Có giữ nguyên semantics của finally/monitor/return không? | Differential testing trên bytes trước/sau |

**Điểm giới hạn:** trình dựng thành công và class load thành công **không đủ** chứng minh mọi đường chạy logic đúng. Kết hợp API kiểm tra model, verifier và test đối chiếu kết quả. Với classfile instrument từ ứng dụng thật, cần thêm test về concurrency, reflection, exception suppression và custom class loaders tùy phạm vi.

## 12. Câu hỏi ôn tập có đáp án

**1.** Tại sao `long` và `double` có thể khiến slot của tham số sau lệch so với `paramNo`?

> Chúng dùng hai slot trong local array; `paramNo` là thứ tự tham số, không phải chỉ số slot. `parameterSlot` tính đúng cả receiver và độ rộng loại.

**2.** `allocateLocal(TypeKind.INT)` có thêm một entry vào `LocalVariableTable` không?

> Không. Nó chọn một slot mới cho mã sinh ra. `localVariable(...)` mới khai báo metadata debug với name, descriptor và scope.

**3.** `newLabel()` khác `newBoundLabel()` như thế nào?

> `newLabel` tạo marker chưa bind, có thể làm forward jump target; `newBoundLabel` tạo và bind ngay tại vị trí hiện tại. Nhãn dùng trong code cần được bind theo hợp đồng.

**4.** Trong handler `catch (ArithmeticException e)`, top của operand stack chứa gì?

> Một reference tới exception được ném. Có thể `astore(errorSlot)` để chuyển nó vào local trước khi xây các instruction khác.

**5.** Tại sao code bình thường phải nhảy qua handler?

> Handler được phát thành instructions trong code array; nếu không có branch/return thích hợp, đường chạy bình thường có thể fall through vào handler khi stack không có exception reference.

**6.** `exceptionCatch(tryStart, tryEnd, handler, type)` có tự tạo logic `finally` không?

> Không. Nó chỉ thêm một entry vào exception table cho khoảng `[tryStart, tryEnd)`. Logic cleanup trên mọi đường, xử lý exception gốc và return phải được tạo rõ ràng.

**7.** `goto_(done)` từ hai nhánh khác nhau luôn hợp lệ không?

> Chỉ khi trạng thái operand stack và verification types/locals có thể hợp nhất. Nhãn không tự chữa lỗi lệch kiểu hoặc thiếu giá trị.

**8.** Nếu generated method dùng `resultSlot` nhưng không có tên biến trong debugger thì JVM có chạy được không?

> Có. Local slots và bytecode là phần thực thi; tên biến trong LocalVariableTable là metadata tùy chọn, không phải điều kiện để load/store.

**9.** Tại sao mặc định sinh stack maps thường tốt hơn `DROP_STACK_MAPS`?

> Với classfile hiện đại có nhánh/handler, JVM verifier cần thông tin frame hợp lệ. Mặc định của API tạo hoặc tái sử dụng stack maps khi cần; bỏ hẳn mà không cung cấp bảng đúng có thể dẫn đến `VerifyError`.

**10.** Vì sao thử `eval(5,0)` quan trọng dù `eval(12,3)` đã đúng?

> `5/0` buộc JVM đi vào handler, kiểm chứng phạm vi try, việc lưu exception reference và giá trị result trên đường ngoại lệ; happy path không kiểm tra các yếu tố đó.

## 13. Tài liệu chuẩn để tra cứu

- JEP 484 — Class-File API được chuẩn hóa trong JDK 24: https://openjdk.org/jeps/484
- Java SE 24, `ClassFile` — build, parse, các tùy chọn cho classfile và stack maps: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html
- Java SE 24, `ClassBuilder` — `withMethodBody`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassBuilder.html
- Java SE 24, `CodeBuilder` — `allocateLocal`, `parameterSlot`, `newLabel`, `labelBinding`, `exceptionCatch`, `localVariable`, instruction factories: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html
- Java SE 24, `TypeKind` — tính toán loại `int`, reference, category-2 `long`/`double`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/TypeKind.html
- Java SE 24, `CodeAttribute` — `maxLocals`, `maxStack`, `labelToBci`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/attribute/CodeAttribute.html
- Java SE 24, `CodeModel` và `ExceptionCatch` — exception handlers trong model: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeModel.html
- Java SE 24, `ClassFile.StackMapsOption` — mặc định và các lựa chọn sinh stack maps: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.StackMapsOption.html
- JVM Specification Java SE 24 — local variable array, operand stack, `Code` attribute, exception table, verifier: https://docs.oracle.com/javase/specs/jvms/se24/html/index.html
