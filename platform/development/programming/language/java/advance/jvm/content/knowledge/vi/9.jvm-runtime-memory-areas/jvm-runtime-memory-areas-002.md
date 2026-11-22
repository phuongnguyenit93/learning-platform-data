# Thanh ghi pc và JVM stack trong quá trình thực thi một luồng

Khi JVM chạy một phương thức Java, nó phải biết **instruction bytecode nào đang được thực thi** và **trạng thái lời gọi phương thức đang nằm ở đâu**. Hai thành phần nền tảng trong mô hình JVM là:

- **`pc register` (program counter register)**: trạng thái **riêng của mỗi thread** dùng để biểu diễn vị trí instruction JVM đang thực thi.
- **`JVM stack` (Java Virtual Machine stack)**: ngăn xếp **riêng của mỗi thread**, chứa các **frame** của những lần gọi phương thức đang hoạt động.

Một thread đi vào `main`, gọi `service()`, rồi gọi `calculate()` sẽ chuyển qua các frame khác nhau. `pc` cho biết instruction hiện tại của thread; JVM stack giữ local variables, operand stack và thông tin cần thiết để trở lại caller hoặc xử lý exception. Hiểu cả hai mới giải thích được lời gọi lồng nhau, đệ quy, stack trace, `StackOverflowError`, chuyển context giữa threads và vì sao `-Xss` không đồng nghĩa kích thước heap.

Bài sử dụng mô hình từ **JVMS Java SE 17 §2.5.1–§2.5.2 và §2.6**; ví dụ biên dịch với Java 17+. Các thuật ngữ `pc` và frame dưới đây trước hết là **ngữ nghĩa JVM**, không phải lời khẳng định HotSpot luôn lưu chúng vào một thanh ghi CPU vật lý hoặc một vùng RAM liên tục duy nhất.

## 1. Đặt pc register và JVM stack trong toàn cảnh runtime data areas

JVMS phân biệt vùng dữ liệu **theo thread** và **được chia sẻ giữa các threads**:

| Vùng dữ liệu JVM | Phạm vi | Vai trò trong bài |
| --- | --- | --- |
| **pc register** | **Mỗi thread có một** | Theo dõi instruction JVM đang chạy trong thread đó |
| **JVM stack** | **Mỗi thread có một** | Chứa các frame của các lời gọi đang hoạt động |
| **Frame** | Thuộc một lần gọi method trong một thread | Local variables, operand stack, dynamic linking, return/exception state |
| **Heap** | Chia sẻ trong JVM | Chứa objects và arrays; nhiều frame có thể giữ reference tới cùng object |
| **Method area** | Chia sẻ trong JVM | Dữ liệu lớp, method code và những thông tin liên quan |
| **Run-time constant pool** | Dữ liệu liên quan tới từng class/interface, trong vùng do JVM quản lý | Symbolic references được bytecode trong frame sử dụng |
| **Native method stacks** | Phụ thuộc JVM/triển khai và thread/native invocation | Phục vụ thực thi native code nếu implementation sử dụng |

Không gộp **operand stack** trong một frame với **JVM stack** chứa các frame: chúng có quan hệ lồng nhau nhưng khác cấp độ.

```text
                       Một JVM
     +------------------------------------------+
     | Heap, method area, runtime constant pools|
     |        (các threads có thể chia sẻ)      |
     +------------------------------------------+
           ^                         ^
           | references / metadata   |
    +-----------------+      +-----------------+
    | Thread A        |      | Thread B        |
    | pc register A   |      | pc register B   |
    | JVM stack A     |      | JVM stack B     |
    |  [frame m3]     |      |  [frame n2]     |
    |  [frame m2]     |      |  [frame n1]     |
    |  [frame m1]     |      |                 |
    +-----------------+      +-----------------+
```

Ví dụ, local slot 1 của frame thuộc thread A và local slot 1 của frame thuộc thread B **không phải cùng một slot**. Nhưng nếu chúng chứa reference trỏ đến **cùng một object trên heap**, hai thread vẫn có thể đọc/ghi trạng thái object đó. **Thread-private stacks không có nghĩa mọi dữ liệu được tham chiếu đều thread-safe.**

## 2. pc register: mô hình chính xác là gì?

Theo JVMS §2.5.1, **mỗi JVM thread có pc register riêng**, được tạo cùng thread. Ở bất kỳ thời điểm nào, một thread đang thực thi code của một method. Trong trường hợp method đó **không phải native**, giá trị pc register là **địa chỉ instruction JVM hiện đang được thực thi** trong method tương ứng.

Điều này giúp JVM có mô hình điều khiển riêng cho các threads: thread A có thể đang ở opcode `iadd` của `compute`, trong khi thread B đang ở opcode `invokevirtual` của `service`.

### Nếu thread đang thực thi native method?

Khi method hiện tại là **native**, JVMS quy định giá trị pc register là **undefined**. Đây là một câu rất quan trọng:

- Không được khẳng định JVM pc của thread đang chạy JNI/native method luôn chỉ tới “bytecode cuối cùng”.
- Địa chỉ instruction **mã máy native** và JVM pc register trong ngữ nghĩa JVMS là **hai khái niệm khác nhau**.
- Một native call có thể tương tác với C/C++, OS stack hoặc cơ chế native của VM, nhưng cách triển khai ấy **không thay đổi** việc JVM pc register được quy định undefined khi đang ở native method.

### pc register có phải con trỏ instruction phần cứng?

Không nhất thiết. JVM là một **máy ảo trừu tượng**. Interpreter có thể quản lý vị trí bytecode bằng BCI (bytecode index)/con trỏ nội bộ; JIT có thể biên dịch method sang mã máy. CPU vật lý có instruction pointer riêng, còn contract JVMS định nghĩa **trạng thái pc logic của JVM thread**. Không thể yêu cầu `Thread.currentThread()` trả trực tiếp giá trị pc register này như một trường Java public.

### pc, bytecode index (BCI) và dòng source

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `pc` của JVM thread | Vị trí instruction JVM **đang thực thi** trong mô hình JVM | Instruction thuộc `calculate()` của frame hiện tại |
| **BCI / bytecode offset** | Offset tính bằng **byte** từ đầu `code[]` của một method | `0: iload_0`, `1: iconst_1`, `2: iadd` |
| **Source line** | Dòng trong file Java theo debug metadata | `Calculator.java:12` |
| CPU instruction pointer | Địa chỉ instruction native của CPU/JIT/interpreter | Chi tiết triển khai, không phải BCI Java trực tiếp |

Một dòng Java source có thể ánh xạ thành **nhiều** instructions; một instruction có thể ứng với một source line qua `LineNumberTable`, hoặc class không có debug line numbers. `javap -c` hiển thị BCI; `javap -l` có thể hiển thị line/local tables. Các bảng này **không** phải API đọc pc chính xác của một thread bất kỳ ở mọi thời điểm.

## 3. JVM stack: một ngăn xếp các frame, không phải heap

Theo JVMS §2.5.2, mỗi JVM thread có **JVM stack riêng**, được tạo cùng thread, lưu các **frames**. JVM stack không trực tiếp cho phép tùy ý lấy một biến local thuộc frame của thread khác bằng mã Java bình thường.

Một số đặc tính:

1. **LIFO**: gọi một method mới thường dẫn đến frame mới trở thành frame hiện tại; kết thúc method thì frame ấy được rời khỏi và caller tiếp tục.
2. **Mỗi invocation có một frame**: cùng method được gọi lại đệ quy ba lần là ba lời gọi, do đó có ba frame riêng với locals riêng.
3. **Mỗi frame có operand stack riêng**: không có một operand stack chung cho mọi method/thread.
4. **Stack lưu trạng thái phương thức, không lưu toàn bộ object**: các local/reference operands có thể trỏ tới objects trên heap.
5. **JVM stacks có thể cố định hoặc thay đổi kích thước tùy triển khai**, và vùng nhớ frame có thể được cấp phát từ heap hoặc nơi khác trong triển khai phù hợp. Đừng giả định JVMS bắt buộc frame là các khối memory vật lý nằm liên tiếp.
6. **Stack kết thúc cùng thread** ở cấp mô hình vòng đời. Việc JVM/OS thu hồi native memory và tối ưu lưu trữ là chi tiết implementation.

### Khung lời gọi lồng nhau

Giả sử:

```java
public static int first(int x) {
    return second(x) + 1;
}
public static int second(int x) {
    return third(x) * 2;
}
public static int third(int x) {
    return x + 3;
}
```

Đây là **ba method minh họa** cần đặt trong một class để biên dịch. Khi `first(4)` gọi `second(4)` rồi `third(4)`:

```text
Đỉnh JVM stack
+---------------------+
| frame third(4)      | <- CURRENT khi third thực thi
| locals: x=4         |
| operand stack ...   |
+---------------------+
| frame second(4)     | <- tạm dừng chờ third trả giá trị
| locals: x=4         |
| operand stack ...   |
+---------------------+
| frame first(4)      | <- tạm dừng chờ second
| locals: x=4         |
| operand stack ...   |
+---------------------+
Đáy JVM stack
```

Khi `third` trả `7`, frame `third` không còn là frame hiện tại; `second` nhận kết quả, tính `14` rồi trả cho `first`; `first` cộng 1 thành `15`. Mọi `x` đều thuộc frame riêng, dù các giá trị cùng bằng `4`.

### “Thread stack”, “call stack”, “operand stack” dễ bị đánh đồng

- **JVM stack / Java call stack**: mô hình quản lý các frames method đang hoạt động trong thread.
- **Operand stack**: vùng bên trong **mỗi frame**, dùng cho tính toán bytecode; được giới hạn bởi `max_stack`.
- **Native/OS stack**: vùng mà native code và bản thân VM có thể sử dụng theo hệ thống; mối quan hệ vật lý với Java frames phụ thuộc JVM và kiểu thread.
- **Heap**: nơi chứa objects/arrays được cấp phát theo ngữ nghĩa JVM. Reference đến object có thể nằm trong locals/operand stack; không có quy tắc “mọi primitive chỉ nằm trên stack, mọi reference chỉ nằm trên heap”.

## 4. Bên trong một frame có gì?

JVMS §2.6 mô tả một **frame** chứa:

- **Local variable array**: các slot được đánh số, lưu receiver `this` (nếu method instance), tham số và các giá trị cục bộ.
- **Operand stack**: vùng LIFO chứa toán hạng và các kết quả trung gian cho JVM instructions.
- **Tham chiếu tới run-time constant pool** của lớp chứa method: dùng hỗ trợ **dynamic linking**, phân giải symbolic references ở những lệnh như truy cập field, gọi method và tạo object.
- **Thông tin cho normal/abrupt method completion**, bao gồm trả về caller hay xử lý/lan truyền exception theo quy tắc JVM.

Tệp `.class` cung cấp `Code` attribute với các giới hạn `max_locals` và `max_stack` cho method có code. Mỗi lần gọi method tạo trạng thái frame riêng theo những giới hạn này.

| Phần trong frame | Đọc từ bytecode thế nào? | Sai lầm phổ biến |
| --- | --- | --- |
| Local variables | `iload`, `istore`, `aload`, `astore`, `lload`... | Cho rằng local index luôn bằng thứ tự tham số trong source |
| Operand stack | `iconst`, `iadd`, `invoke*`, `dup`, `pop`... | Cho rằng mỗi thread chỉ có một operand stack chung |
| Dynamic linking | `getfield`, `invokevirtual`, `invokestatic`... thông qua constant pool | Cho rằng frame chứa sẵn địa chỉ native cố định cho mọi symbolic reference |
| Return state | `ireturn`, `areturn`, `return`, v.v. | Cho rằng callee tiếp tục chạy sau return |
| Exception handling | Exception table, `athrow`, lỗi JVM instructions | Cho rằng exception luôn kết thúc cả thread |

### Local slot: giá trị category 1 và category 2

- `int`, `float`, reference thuộc loại tính toán **category 1**, mỗi giá trị cần **một slot**.
- `long` và `double` thuộc **category 2**, mỗi giá trị cần **hai slots** trong local-variable array và đóng góp hai đơn vị độ sâu trên operand stack.
- `byte`, `short`, `char` và `boolean` được biểu diễn/xử lý dưới dạng tính toán thích hợp, thường theo `int` trong operand stack/locals.
- Method **instance** thường đặt receiver `this` ở local slot **0**, rồi tham số; method **static** không có receiver ẩn.
- `long` ở slot 1 chiếm slot 1–2; tham số tiếp theo không thể dùng slot 2 như một giá trị độc lập.

Ví dụ method:

```java
static long mix(int count, long amount, double factor) {
    return amount + count;
}
```

Đây là **method minh họa**. Trong static method, `count` ở slot 0, `amount` dùng slot 1–2, `factor` dùng slot 3–4 dù không được dùng trong thân. Compiler có thể thêm local slots nếu cần; `max_locals` tối thiểu phải bao trùm toàn bộ tham số theo descriptor. Operand stack cho `ladd` có thể chứa hai giá trị `long` cùng lúc, tổng **4 slot**.

## 5. pc và JVM stack phối hợp khi gọi method như thế nào?

Mô hình một lần invocation:

1. Caller đang ở **current frame** và pc phản ánh vị trí instruction gọi, ví dụ `invokestatic`.
2. Caller đẩy các arguments (và receiver nếu là instance method) lên **operand stack của caller** theo đúng descriptor.
3. JVM tiến hành invocation, xác định method đích qua cơ chế resolution/selection phù hợp, và thiết lập một **frame mới** cho callee (trừ khi implementation dùng tối ưu vẫn bảo toàn hành vi).
4. Callee trở thành **current method/current frame**; arguments được chuyển vào locals của frame callee theo chỉ số slot tương ứng.
5. pc logic của thread biểu diễn instruction đang thực thi trong callee. Caller tạm dừng tại điểm gọi trong lúc callee thực hiện.
6. Khi callee **normal return**, frame callee được rời khỏi; nếu có return value, caller nhận nó trên **operand stack của caller**; sau đó caller tiếp tục tại phần kế tiếp sau lời gọi.
7. Nếu callee kết thúc **abruptly** vì exception, JVM tìm exception handler trong frame hiện tại hoặc unwind ra caller theo exception table và quy tắc lan truyền.

Điểm chính: pc **thuộc thread**, không phải một pc riêng có thể chạy đồng thời cho mỗi frame. Trạng thái caller cần để resume được bảo toàn qua cơ chế invocation/return; pc của thread đi cùng dòng thực thi chuyển qua callee.

### Một method có thể trả về bằng opcode nào?

| Return type | Lệnh thường dùng | Hiệu ứng |
| --- | --- | --- |
| `void` | `return` | Không đẩy một giá trị trả về |
| `int` và các kiểu primitive nhỏ theo biểu diễn JVM | `ireturn` | Trả một giá trị category 1 |
| `long` | `lreturn` | Trả category 2 |
| `float` | `freturn` | Trả category 1 |
| `double` | `dreturn` | Trả category 2 |
| Object/array reference | `areturn` | Trả reference category 1 |

Callee không “copy nguyên frame” sang caller. Thường chỉ **return value** được truyền theo ngữ nghĩa stack, trong khi locals/operand stack và các trạng thái method riêng của callee kết thúc theo frame ấy.

## 6. Java 17 thực hành: hai lời gọi lồng nhau và bytecode

Tạo file **`FrameCallDemo.java`**:

```java
public class FrameCallDemo {
    static int square(int value) {
        return value * value;
    }

    static int addSquare(int first, int second) {
        int temp = square(first);
        return temp + second;
    }

    public static void main(String[] args) {
        System.out.println("result=" + addSquare(3, 4));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -g FrameCallDemo.java
java FrameCallDemo
javap -c -v -p FrameCallDemo
```

**Stdout của lệnh `java FrameCallDemo`**:

```text
result=13
```

Vì `square(3) = 9` và `addSquare(3,4) = 9 + 4 = 13`.

### Đi theo frames từ `main` đến `square`

```text
A. main
   operand stack: ... arguments (3, 4) cho addSquare
   invokedynamic/println cho phép nối/in có thể xuất hiện tùy compiler

B. vào addSquare
   locals: [first=3, second=4, temp chưa có]
   iload_0  -> [3]
   invokestatic square:(I)I
       |
       v
C. vào square
   locals: [value=3]
   iload_0  -> [3]
   iload_0  -> [3, 3]
   imul     -> [9]
   ireturn  -> caller nhận 9

D. trở lại addSquare
   operand stack sau lời gọi square: [9]
   istore_2 -> []; locals[temp]=9
   iload_2  -> [9]
   iload_1  -> [9,4]
   iadd     -> [13]
   ireturn  -> main nhận 13
```

Đây là **mô hình về các opcode liên quan**. `javap` sẽ có offsets, constant-pool indices, các lệnh chính xác trong `main`; phần nối chuỗi `"result=" + ...` có thể được compiler Java 17 hạ thành `invokedynamic` với `StringConcatFactory`. Tính đúng của `square` và `addSquare` không phụ thuộc vào lựa chọn concat này.

### Trích cấu trúc disassembly thường thấy

```text
static int square(int);
  Code:
    stack=2, locals=1, args_size=1
       0: iload_0
       1: iload_0
       2: imul
       3: ireturn

static int addSquare(int, int);
  Code:
    stack=2, locals=3, args_size=2
       0: iload_0
       1: invokestatic  #...  // Method square:(I)I
       4: istore_2
       5: iload_2
       6: iload_1
       7: iadd
       8: ireturn
```

Các `#...` trong bảng là **chỗ đứng cho constant-pool index**, không phải output nguyên văn có một chỉ số cố định. `javac` phiên bản khác có thể chọn chuỗi opcode tương đương. Tuy vậy:

- `square` cần đồng thời hai `int` trên operand stack trước `imul`: độ sâu tối đa **2**; local có một tham số **1 slot**.
- `addSquare` có hai tham số `int` và một local `temp`, nên `locals=3` là hợp lý cho output điển hình; operand stack tối đa là **2**.
- Opcode `invokestatic` trong `addSquare` làm thread chuyển execution sang frame `square`; opcode `ireturn` chuyển kết quả **9** về stack của caller.
- BCI `1` sau `iload_0` không phải một “thanh ghi pc của square”: đó là offset instruction trong **code của addSquare**.

### Theo dõi từng thời điểm

| Thời điểm | Current method | Frames đang hoạt động (đáy → đỉnh) | Điều pc logic đại diện |
| --- | --- | --- | --- |
| Trước lời gọi `addSquare` | `main` | `main` | Instruction trong `main` |
| Sau invocation `addSquare` | `addSquare` | `main → addSquare` | Instruction thuộc `addSquare` |
| Sau invocation `square` | `square` | `main → addSquare → square` | Instruction thuộc `square` |
| Sau `square.ireturn` | `addSquare` | `main → addSquare` | Instruction tiếp tục trong `addSquare` |
| Sau `addSquare.ireturn` | `main` | `main` | Instruction tiếp tục trong `main` |

Bảng tập trung vào **logical call stack**, không yêu cầu HotSpot phải tạo năm cấu trúc stack máy vật lý như bảng cho từng dòng.

## 7. Đệ quy: mỗi lời gọi cùng một method vẫn là frame mới

Với recursion, một method gọi lại chính nó. Tên method trên stack có thể lặp lại nhưng **locals riêng**, pc phản ánh instruction trong invocation đang chạy của thread.

Tạo file **`RecursiveFrames.java`**:

```java
public class RecursiveFrames {
    static int countDown(int n) {
        if (n == 0) {
            return 0;
        }
        return 1 + countDown(n - 1);
    }

    public static void main(String[] args) {
        System.out.println("depth=" + countDown(3));
    }
}
```

```bash
javac --release 17 RecursiveFrames.java
java RecursiveFrames
```

**Stdout**:

```text
depth=3
```

Khi đi sâu nhất:

```text
main()
  countDown(3)  locals[n=3]
    countDown(2) locals[n=2]
      countDown(1) locals[n=1]
        countDown(0) locals[n=0] -> return 0
      -> return 1
    -> return 2
  -> return 3
```

Nếu cùng một phương thức được gọi vô hạn mà JVM không thể cấp thêm frame, kết quả có thể là **`StackOverflowError`**. Độ sâu tại thời điểm lỗi **không cố định**, phụ thuộc JVM, stack settings, biểu diễn frame, JIT, hệ thống và tình huống runtime. Không cần chạy đệ quy vô hạn để minh họa cơ chế; ví dụ hữu hạn đã chứng minh mỗi invocation có local state riêng.

### Vì sao `StackOverflowError` không đồng nghĩa “heap hết bộ nhớ”?

Đó là lỗi tài nguyên liên quan đến stack của JVM thread, không phải kết luận mặc định rằng heap đã đầy. Ngược lại, chương trình có thể bị `OutOfMemoryError` vì không thể tạo/giãn stack hoặc thiếu tài nguyên native; **loại exception phải được đọc cùng message và ngữ cảnh**.

## 8. Exception làm current frame thay đổi như thế nào?

Một method có thể kết thúc:

- **Normal completion**: một return instruction đưa caller tiếp tục và truyền kết quả nếu có.
- **Abrupt completion**: instruction ném exception, hoặc method gọi tới method khác mà exception chưa được xử lý ở callee.

Khi exception xuất hiện, JVM **không nhất thiết bỏ ngay toàn bộ call stack**. Nó tìm entry phù hợp trong **exception table** của method hiện tại. Nếu có handler, tiếp tục tại **`handler_pc`** trong cùng frame; nếu không, frame kết thúc đột ngột, exception lan ra caller và JVM thử tìm handler tại call site của caller.

### Ví dụ exception được bắt ở caller ngoài

Tạo **`ExceptionFrames.java`**:

```java
public class ExceptionFrames {
    static int quotient(int numerator, int denominator) {
        return numerator / denominator;
    }

    static int transform(int value) {
        return quotient(10, value) + 1;
    }

    public static void main(String[] args) {
        try {
            System.out.println("good=" + transform(2));
            transform(0);
        } catch (ArithmeticException ex) {
            System.out.println("caught=" + ex.getClass().getSimpleName());
        }
        System.out.println("after");
    }
}
```

```bash
javac --release 17 ExceptionFrames.java
java ExceptionFrames
javap -c -v -p ExceptionFrames
```

**Stdout**:

```text
good=6
caught=ArithmeticException
after
```

Giải thích:

1. `transform(2)` gọi `quotient(10,2)` nhận `5`, cộng 1 thành `6`.
2. `transform(0)` gọi `quotient(10,0)`; `idiv` ném `ArithmeticException`.
3. `quotient` không có handler phù hợp, nên frame `quotient` kết thúc đột ngột.
4. `transform` không có handler phù hợp, nên frame `transform` cũng unwind.
5. Trong `main` có `try/catch` bảo vệ vị trí lời gọi; JVM chuyển tới bytecode handler của `main` và thực thi khối `catch`.
6. `main` tiếp tục in `after`.

**pc** lúc ở `quotient` phản ánh instruction của `quotient`; khi exception được bắt trong `main`, current frame và pc logic chuyển tới handler của `main`. Không được suy “`idiv` lỗi nghĩa là JVM thread buộc phải dừng”.

### Khi handler nằm ngay trong cùng method

```java
static int safeDivide(int a, int b) {
    try {
        return a / b;
    } catch (ArithmeticException ex) {
        return -1;
    }
}
```

Đây là **method minh họa**, đặt vào class để biên dịch. Nếu `b=0`, JVM chọn exception handler **trong chính frame `safeDivide`**, không phải tự động pop frame ấy. Khi handler trả `-1`, method mới kết thúc bình thường về caller.

### Exception table dùng bytecode offsets

Đối với `Code_attribute`, mỗi handler entry có dạng `start_pc`, `end_pc`, `handler_pc`, `catch_type`:

- Vùng bảo vệ là **`[start_pc, end_pc)`** — bao gồm start, không bao gồm end.
- `handler_pc` chỉ đầu instruction xử lý exception.
- Handler nhận exception reference trên operand stack theo quy tắc JVM; instruction đầu thường là `astore` để lưu reference vào local.
- Các entries được xét theo thứ tự được định nghĩa trong exception table; entry phù hợp đầu tiên quyết định xử lý.

Những `start_pc/end_pc` trong class file là **BCI offsets**, không phải cùng một ô nhớ “JVM pc register” cấp thread.

## 9. Hai threads: hai pc registers và hai JVM stacks

Đặc tả nói rõ một JVM có thể hỗ trợ nhiều threads thực thi đồng thời; mỗi thread có **pc riêng** và **stack riêng**.

Ví dụ:

```text
Thread "worker"
  pc -> instruction của calculate()
  JVM stack: run() -> calculate()

Thread "main"
  pc -> instruction của main()
  JVM stack: main()
```

Thread main không thể đọc trực tiếp operand stack của worker như đọc một `List` Java. Tuy nhiên, cả hai có thể có references cùng trỏ tới một object trên heap và cần đồng bộ khi truy cập state chung.

### Java 17 chạy được: worker giữ frame trong khi main vẫn chạy

Tạo **`PerThreadStacks.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class PerThreadStacks {

    static int twice(int value) {
        return value * 2;
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            int value = twice(21);
            ready.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            System.out.println("worker=" + value);
        }, "worker-example");

        worker.start();
        ready.await();
        System.out.println("main=ready");

        release.countDown();
        worker.join();
        System.out.println("main=joined");
    }
}
```

```bash
javac --release 17 PerThreadStacks.java
java PerThreadStacks
```

**Stdout của đường chạy bình thường, không bị interrupt**:

```text
main=ready
worker=42
main=joined
```

`CountDownLatch` khiến worker chờ sau khi báo ready; main in `main=ready` **trước khi** release worker. `join()` khiến main chỉ in `main=joined` sau khi worker kết thúc. Trong khoảng worker đợi ở `release.await()`, JVM thread worker vẫn có call stack riêng liên quan tới task và các phương thức thư viện chờ; thread main có frame riêng ở code `main`.

Đây là ví dụ về **hai stacks và đồng bộ**, không phải cách đo độ lớn stack: `CountDownLatch` và `join` chủ yếu điều phối threads, không phơi bày pc register thật.

### Thread-private local state và shared heap object

`int value = twice(21)` là giá trị local của frame chạy trên worker, không tự động trở thành biến local của main. Nếu lambda capture một reference tới object shared, dữ liệu object đó vẫn có thể là state chung. JVM không có phép bảo vệ tự động ngăn data race chỉ vì mỗi thread sở hữu stack riêng. Khi thiết kế concurrency, dùng đúng Java Memory Model, volatile, locks, immutable objects hoặc concurrent utilities.

## 10. JVM stack có thể hết chỗ: `StackOverflowError` và `OutOfMemoryError`

JVMS §2.5.2 nêu hai nhóm lỗi quan trọng:

- **`StackOverflowError`**: một phép tính trong thread yêu cầu JVM stack lớn hơn giới hạn được cho phép. Đệ quy sâu là ví dụ phổ biến nhưng không phải nguồn duy nhất.
- **`OutOfMemoryError`**: nếu một JVM implementation cho phép stack mở rộng động nhưng không thể cấp memory đủ, hoặc không thể tạo initial stack cho thread mới vì thiếu memory, lỗi có thể xuất hiện.

### `-Xss` là gì?

Trên nhiều OpenJDK/HotSpot builds, `-Xss` cấu hình kích thước stack của Java threads theo đơn vị như `k`, `m` (cách áp dụng cụ thể tùy runtime/kiểu thread và nền tảng).

Ví dụ câu lệnh minh họa:

```bash
java -Xss1m RecursiveFrames
```

Đây chỉ là ví dụ **cấu hình**, không hứa một method có thể đệ quy được chính xác bao nhiêu lần. `-Xss` không trực tiếp đặt `max_stack` của bytecode; `max_stack` là **độ sâu operand stack theo slot** cho một method frame trong `Code` attribute, còn `-Xss` liên quan tới tài nguyên stack cấp thread của implementation.

### Vì sao không lấy `StackOverflowError` làm nhánh nghiệp vụ?

- Thời điểm lỗi thay đổi theo JVM build, OS, optimization, frame shape và cách gọi.
- Khi stack đã gần cạn, ngay cả việc tạo log hoặc xây dựng exception message cũng có thể gặp hạn chế tài nguyên.
- Bắt `StackOverflowError` rồi cố tiếp tục như không có gì xảy ra có thể bỏ qua lỗi thuật toán hoặc trạng thái không còn đáng tin cậy.
- Cách sửa tốt hơn là giới hạn recursion depth, dùng thuật toán lặp, tail-recursion transformation do lập trình viên chủ động thực hiện khi phù hợp, hoặc điều chỉnh workload/stack settings sau khi đo.

**Java không bảo đảm tự động tối ưu tail-call/tail-recursion** để loại bỏ stack growth. Đừng viết hàm recursive không giới hạn chỉ vì “JIT chắc sẽ tối ưu đuôi”.

## 11. So sánh JVM stack với heap: object ở đâu?

Đoạn Java:

```java
static int lengthOf(String value) {
    int n = value.length();
    return n;
}
```

Đây là **method minh họa**, không phải file độc lập.

- Tham số `value` là một **reference** trong local slot của frame `lengthOf`.
- `String` object được quản lý theo ngữ nghĩa heap, không bị “copy toàn bộ” vào local slot chỉ vì có tham số.
- `n` là giá trị primitive local; mô hình JVM có local slot chứa kết quả. Với JIT, tối ưu có thể giữ nó trong register CPU hoặc loại bỏ thao tác lưu vật lý không cần thiết.
- Gọi `value.length()` dùng operand stack để truyền receiver, rồi trả `int` về caller. Nếu `value == null`, dereference có thể ném `NullPointerException`; điều đó không làm pc/stack trở thành vùng nhớ đối tượng.
- Nếu một object/reference “escape” khỏi method qua return/store, object có thể tiếp tục tồn tại sau khi frame method kết thúc. Vòng đời heap object được GC quản lý theo reachability chứ không bằng việc một local frame nhất định còn hay mất.

Không đơn giản hóa thành “`new` luôn buộc một heap allocation vật lý trong mọi bản JIT” hoặc “mọi primitive bắt buộc ở thread stack memory”. JVM có thể tối ưu allocation bằng escape analysis/scalar replacement mà vẫn bảo đảm ngữ nghĩa quan sát được.

### Bảng tránh nhầm ba kích thước

| Thuộc tính | Thuộc về | Đơn vị/ý nghĩa |
| --- | --- | --- |
| `max_stack` | `Code_attribute` của **một method** | Slot tối đa trên operand stack của frame method |
| `max_locals` | `Code_attribute` của **một method** | Số slot local variables cần cho frame |
| `-Xss` | Cấu hình JVM implementation | Kích thước/tài nguyên stack của thread, không phải số method hoặc số opcode |
| `-Xmx` | Cấu hình heap trên nhiều JVMs | Giới hạn heap, không quyết định trực tiếp `max_stack` của method |

## 12. Current frame, stack trace và công cụ quan sát

### Stack trace nhìn thấy gì?

`Throwable.getStackTrace()` và `Thread.getStackTrace()`/`StackWalker` cho phép ứng dụng quan sát **thông tin lời gọi**, thường là tên class, tên method, file và source line nếu có debug metadata. Chúng **không** cung cấp quyền đọc trực tiếp toàn bộ local variables/operand stack của frame hay raw pc register của thread.

- Stack trace là một **ảnh chụp logic**, không phải dãy instruction liên tục.
- Trường `StackTraceElement.getLineNumber()` đại diện source line nếu có, có thể là số âm khi không biết/hoạt động native; **không phải BCI tuyệt đối**.
- `StackWalker.StackFrame.getByteCodeIndex()` có thể cung cấp BCI khi có sẵn theo contract của API, nhưng đó **không phải API lấy một địa chỉ pc vật lý của mọi thread**.
- JIT/inlining hoặc hidden frames có thể làm cách hiển thị khác nhau theo công cụ/option, nhưng thread execution vẫn phải tuân theo semantics Java/JVMS.

### Java 17: `StackWalker` quan sát chuỗi frames logic

Tạo **`StackWalkDemo.java`**:

```java
import java.util.stream.Collectors;

public class StackWalkDemo {
    static String snapshot() {
        return StackWalker.getInstance().walk(frames ->
            frames.filter(f -> f.getClassName().equals("StackWalkDemo"))
                  .map(StackWalker.StackFrame::getMethodName)
                  .limit(4)
                  .collect(Collectors.joining(" -> "))
        );
    }

    static String inner() {
        return snapshot();
    }

    static String outer() {
        return inner();
    }

    public static void main(String[] args) {
        System.out.println(outer());
    }
}
```

```bash
javac --release 17 StackWalkDemo.java
java StackWalkDemo
```

**Stdout mong đợi khi chạy class như trên**:

```text
snapshot -> inner -> outer -> main
```

`StackWalker` duyệt các frame từ phương thức gần nhất (`snapshot`) đi ra caller; filter chọn những frames của đúng class này. Cú pháp `Collectors.joining(" -> ")` chỉ định dạng chuỗi; **không phải** JVM stack thực được lưu như một Java `String`.

**Giới hạn quan sát:** Công cụ stack walking không nhất thiết hiện mọi frame ẩn hoặc native frames theo cùng cách; hoạt động được kiểm tra bằng API này không chứng minh HotSpot lưu một frame vật lý cố định cho mỗi dòng in. Không dùng tên/độ sâu trace làm hợp đồng binary layout.

### Công cụ khi JVM bị treo hoặc stack sâu

Các lệnh thông dụng trên JDK hỗ trợ công cụ:

```bash
jcmd <PID> Thread.print
jstack <PID>
javap -c -v -p FrameCallDemo
```

`<PID>` là **placeholder** cho process ID của Java process cần kiểm tra, không phải chuỗi lệnh được chạy nguyên dạng. `jcmd`/`jstack` hiển thị các threads và stack traces (cùng trạng thái/locks tùy công cụ), giúp thấy thread đang chờ lock, sleep, native call hay đang ở method nào. `javap` là disassembler của **class file**, không phải profiler theo thời gian thực.

Để soi bytecode instruction cụ thể, `javap -c` hiển thị các **BCI offsets**; để đối chiếu source line/locals, dùng `javap -l` hoặc `javap -v` khi đã compile với debug info.

### JIT và pc register: đừng trộn ba lớp quan sát

| Điều có thể thấy | Công cụ | Kết luận hợp lệ |
| --- | --- | --- |
| Bytecode offset của một method | `javap -c` | Vị trí instruction trong `Code.code[]` của class file |
| Call frames đang hoạt động | Stack trace, `StackWalker`, `jcmd Thread.print` | Cấu trúc lời gọi logic tại thời điểm quan sát |
| Native instruction address đang chạy | Native debugger/profiler chuyên dụng | Chi tiết cấp OS/CPU/JIT, **không đồng nhất** JVM pc |
| Runtime stack memory size | JVM flags, native diagnostics | Tài nguyên memory của thread, không phải độ sâu `max_stack` |

## 13. Khi native method tham gia call stack

Trong Java 17, nhiều API chuẩn cuối cùng có thể gọi native code (thông qua JNI hoặc cơ chế runtime của JDK). Ví dụ `Thread.sleep(...)` trên một số triển khai dùng native logic nội bộ, nhưng điều đó **không** cho phép suy ra bất kỳ opcode bytecode nào ở native method body.

Trong mô hình JVMS:

1. Khi đang thực thi method **không native**, JVM pc register chứa địa chỉ instruction JVM đang chạy.
2. Khi current method là **native**, JVM pc register được quy định **undefined**.
3. Native invocation có thể dùng native method stack hoặc cấu trúc OS khác theo implementation.
4. Sau native call trở lại Java code, thread lại thực thi các JVM instructions với ngữ nghĩa frame/pc bình thường.

Đừng viết công cụ dựa vào giả định “pc luôn là một BCI kể cả khi thread đang ở JNI”. Khi xem stack dump, một dòng báo `Native Method` thường mô tả **vị trí theo tool**, không cung cấp một JVM BCI có nghĩa như ở method bytecode bình thường.

## 14. Điều gì là bảo đảm của JVMS, điều gì là tùy triển khai?

| Khẳng định | Mức bảo đảm | Lý do |
| --- | --- | --- |
| Mỗi JVM thread có pc register riêng | **JVMS §2.5.1** | Trạng thái điều khiển riêng mỗi thread |
| JVM pc có giá trị undefined khi current method native | **JVMS §2.5.1** | Native code không phải JVM bytecode |
| Mỗi JVM thread có stack riêng | **JVMS §2.5.2** | Quản lý frames method |
| Mỗi invocation có frame riêng về mặt ngữ nghĩa | **JVMS §2.6** | Locals, operands và return/exception state độc lập |
| `long/double` chiếm hai stack slots theo mô hình JVM | **JVMS `2.6.2`** | Cách đếm `max_stack` |
| Normal return truyền return value cho caller | **JVMS `2.6.4`** | Method completion |
| Exception có thể làm unwind qua nhiều frames | **JVMS `2.6.5`** | Abrupt completion |
| JVM stack bắt buộc là block memory liền kề theo layout cố định | **Không được bảo đảm** | JVMS cho phép nhiều chiến lược implementation |
| pc register luôn trùng với CPU instruction pointer | **Không được bảo đảm** | JIT/interpreter/CPU là tầng khác |
| Một Java method luôn tương ứng một native frame có layout cố định | **Không được bảo đảm** | JIT/inlining/optimization có thể thay biểu diễn |
| `-Xss1m` cho phép recursion đúng N lần | **Không được bảo đảm** | Platform, code shape, runtime/JIT |
| Stack traces phải in mọi hidden/native frame chính xác như nhau | **Không được bảo đảm** | API/tool options và cách triển khai |

## 15. Những lỗi suy luận thường gặp

**Nhầm 1: “Mỗi method có một pc register.”** Sai: **mỗi thread có một pc register** theo JVMS; current method/frame thay đổi qua invocation.

**Nhầm 2: “Mỗi thread có một operand stack duy nhất.”** Sai: JVM stack của thread chứa **nhiều frames**, và **mỗi frame có operand stack riêng**.

**Nhầm 3: “Bất kỳ nơi nào có từ stack đều là JVM stack.”** Sai: JVM call stack, frame operand stack và native stack khác vai trò.

**Nhầm 4: “`max_stack = 8` nghĩa thread stack có đúng 8 frames.”** Sai: đó là **độ sâu tối đa 8 slot trong operand stack của một method frame**.

**Nhầm 5: “Mọi object nằm trong JVM stack.”** Sai: frame có thể giữ reference tới objects; bản thân objects có ngữ nghĩa heap và JVM có thể tối ưu vật lý.

**Nhầm 6: “Reference nằm trong local nên object đó thread-private.”** Sai: cùng object trên heap có thể được nhiều threads tham chiếu.

**Nhầm 7: “Trong native method, pc luôn chỉ tới bytecode ngay sau lời gọi native.”** Sai: JVM pc register **undefined** khi current method native.

**Nhầm 8: “Source line number là bytecode PC.”** Sai: line number map qua metadata; BCI là offset trong `code[]`.

**Nhầm 9: “Exception luôn pop mọi frames và kết thúc thread.”** Sai: JVM tìm handler trong current frame rồi các frames ngoài, có thể tiếp tục chương trình.

**Nhầm 10: “StackOverflowError nghĩa là heap đã đầy.”** Sai: đó là tình huống stack vượt giới hạn; heap exhaustion là chuyện khác, dù OOME có thể xảy ra với cấp phát stack trong một số implementation.

**Nhầm 11: “Tăng `-Xss` là sửa triệt để đệ quy vô hạn.”** Sai: nó có thể trì hoãn lỗi, không thay đổi tính đúng của thuật toán.

**Nhầm 12: “Thread context switch làm hai threads chia sẻ pc/register/locals.”** Sai: thread states riêng được quản lý theo ngữ nghĩa thread; việc CPU đổi thread chạy không khiến frame locals nhập làm một.

**Nhầm 13: “Mỗi `ireturn` trả về toàn bộ operand stack của callee.”** Sai: chỉ return value cần thiết được truyền theo quy tắc completion; frame callee kết thúc.

**Nhầm 14: “`jstack` cho thấy toàn bộ local variable values của mọi frame.”** Sai: stack trace chủ yếu mô tả method/call positions, có thể có locks/state; không phải snapshot tùy ý của từng locals/operands.

## 16. Quy trình phân tích lỗi thực thi bằng pc và stack

Khi một Java thread treo, lặp sâu hoặc ném exception:

1. **Xác định thread**: thread nào gây vấn đề, state hiện tại là `RUNNABLE`, `WAITING`, `BLOCKED` hay trạng thái khác? Tránh suy luận mọi `RUNNABLE` đang dùng 100% CPU.
2. **Lấy stack trace**: `jcmd <PID> Thread.print`, `jstack` hoặc logging thích hợp. Tìm các method lặp lại (đệ quy), method chờ lock/I/O và chuỗi caller/callee.
3. **Hiểu frame hiện tại**: method đầu trong phần trace thường là vị trí quan sát được gần nhất; các phương thức bên dưới là callers còn đang hoạt động.
4. **Nếu có exception**, xác định exception ném ở method nào và catch handler nằm ở method hiện tại hay caller bên ngoài.
5. **Kiểm tra bytecode khi nghi ngờ compiler/agent instrumentation**: `javap -c -v -p Class`, xem BCI, `max_stack`/`max_locals`, exception table và `StackMapTable`.
6. **Nếu `StackOverflowError`**, tìm recursion không có điều kiện dừng, vòng gọi hai method (A→B→A), hoặc call chain quá sâu; không chỉ tăng stack size.
7. **Nếu `OutOfMemoryError` khi tạo threads**, điều tra số lượng threads và tài nguyên native/stack, đừng lập tức kết luận cần tăng `-Xmx`.
8. **Nếu thấy native frames**, phân biệt JVM pc undefined ở current native method với native instruction address của tooling.
9. **Nếu debug race/concurrency**, nhớ mỗi thread có stack riêng nhưng references từ locals có thể trỏ tới **shared heap objects**; kiểm tra locks/volatile/happens-before.
10. **Phân biệt contract và implementation**: điều JVM bắt buộc làm khác cách JIT/OS lưu giữ frame vật lý và pc trong thực tế.

## 17. Bài tự kiểm tra

**Câu 1.** Một thread gọi `A() → B() → C()`. Có ba pc registers không?  
**Đáp:** Không. Theo JVMS mỗi thread có **một pc register**; ba method đang hoạt động tạo ba **frames logic**.

**Câu 2.** `B` đang gọi `C`. Locals của `B` bị xóa ngay khi `C` bắt đầu?  
**Đáp:** Không. Frame `B` tạm dừng và giữ trạng thái cần thiết để resume sau `C`; `C` có locals/operand stack riêng.

**Câu 3.** Khi `C` có current method là native, JVM pc phải chứa BCI của caller `B`?  
**Đáp:** Không. JVMS quy định JVM pc register **undefined** khi current method native.

**Câu 4.** `max_stack=4` và `max_locals=6` nói điều gì?  
**Đáp:** Một frame của method cần **tối đa 4 operand-stack slots** và **6 local-variable slots** theo `Code` attribute; không cho số lượng frames của thread.

**Câu 5.** `long` và `double` góp mấy slots vào JVM operand stack?  
**Đáp:** Mỗi giá trị chiếm **hai slots** theo mô hình JVM, dù là một giá trị logic.

**Câu 6.** Một method ném exception nhưng caller có catch phù hợp. Thread nhất thiết chết?  
**Đáp:** Không. JVM có thể unwind frames rồi tiếp tục tại handler trong caller.

**Câu 7.** Hai threads cùng gọi `calculate()`, chúng dùng chung locals slot 0?  
**Đáp:** Không. Mỗi invocation trong mỗi thread có frame và locals riêng, nhưng có thể cùng tham chiếu một object heap.

**Câu 8.** `StackTraceElement.getLineNumber()` có phải địa chỉ pc register vật lý?  
**Đáp:** Không. Nó là source line metadata (nếu có), không phải instruction pointer của CPU hoặc raw JVM pc.

**Câu 9.** Vì sao `-Xss` không bằng `max_stack`?  
**Đáp:** `-Xss` là cấu hình tài nguyên stack của thread theo JVM implementation; `max_stack` là độ sâu operand-stack slots của **một frame**.

**Câu 10.** Có nên tin một đoạn `javap` của JDK 17 là máy trạng thái vật lý HotSpot duy nhất được phép dùng?  
**Đáp:** Không. `javap` mô tả **class file bytecode**; JIT/interpreter có thể triển khai khác nhưng giữ đúng ngữ nghĩa JVM.

## Tài liệu chuẩn Java SE 17

- [JVMS §2.5.1 — The pc Register](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.1): pc riêng mỗi JVM thread và native method.
- [JVMS §2.5.2 — Java Virtual Machine Stacks](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.2): JVM stack per-thread, khả năng mở rộng và các lỗi `StackOverflowError`/`OutOfMemoryError`.
- [JVMS §2.5.3 — Heap](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): heap dùng chung.
- [JVMS §2.6 — Frames](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6): local variables, operand stack, dynamic linking, normal/abrupt completion.
- [JVMS `2.6.1 — Local Variables](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.1) và [`2.6.2 — Operand Stacks](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.2): slot indexes và category-2 values.
- [JVMS §4.7.3 — Code Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3): `max_stack`, `max_locals`, `code_length`, exception table.
- [JVMS §6.5 — JVM Instruction Set](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5): `iload`, `iadd`, `invokestatic`, `ireturn`, `athrow` và các opcode khác.
- [Java SE 17 `StackWalker` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackWalker.html) và [`StackTraceElement` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackTraceElement.html): stack inspection ở mức Java.
- [Java SE 17 `Thread` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): threads, stack traces và lifecycle.
- [Java SE 17 `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html) và [`jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): disassembly và thread diagnostics.

**Ghi nhớ:** **pc register thuộc từng thread** và biểu diễn vị trí instruction JVM hiện tại; **JVM stack cũng thuộc từng thread**, nhưng chứa nhiều **method frames** có locals/operand stack riêng. Lời gọi/return/exception làm **current frame** thay đổi; stack traces mô tả những frames ấy, không phải direct memory dump của một PC register CPU. Phân biệt rõ ngữ nghĩa JVMS với cách HotSpot/JIT lưu state thực tế sẽ giúp tránh lỗi phân tích bộ nhớ, performance và concurrency.
