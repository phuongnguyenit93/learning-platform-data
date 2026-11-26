# Đọc cùng tạo lệnh bytecode, label, nhánh rẽ và vùng xử lý ngoại lệ

## Mục tiêu

Class-File API cho phép chương trình Java đọc, tạo và biến đổi file `.class` mà không phải tự phân tích từng byte trong constant pool hay tự tính offset của lệnh nhảy. Khi làm việc với phần thân method, API cung cấp hai góc nhìn:

- **Đọc bytecode:** `CodeModel` biểu diễn phần `Code` attribute của method. Ta duyệt các `CodeElement`, trong đó có instruction, label target và exception table entry.
- **Tạo bytecode:** `CodeBuilder` cung cấp các factory method theo mnemonic như `iload`, `ifge`, `goto_`, `ireturn`, đồng thời cho phép tạo và gắn `Label` để mô tả luồng điều khiển.

Class-File API xuất hiện ở JDK 22 dưới dạng preview trong JEP 457, tiếp tục preview ở JDK 23 qua JEP 466 và trở thành API chính thức từ JDK 24 qua JEP 484. Các ví dụ trong bài dùng API final từ JDK 24 trở lên, không cần bật `--enable-preview`.

## Bytecode và luồng điều khiển của method

Khi biên dịch Java source, compiler chuyển `if`, `else`, vòng lặp và `try/catch` thành các thành phần trong `Code` attribute của method:

- **Instruction** là lệnh JVM có thể thực thi, ví dụ `ILOAD`, `IADD`, `IFGE`, `GOTO`, `IRETURN`.
- **Branch instruction** thay đổi vị trí thực thi dựa trên điều kiện hoặc chuyển vô điều kiện đến một vị trí khác.
- **Label** đánh dấu một vị trí trong danh sách instruction. Lệnh nhảy và exception handler tham chiếu đến label thay vì tự tính bytecode index.
- **Exception table** mô tả đoạn instruction được bảo vệ và vị trí handler sẽ nhận exception nếu có lỗi phù hợp xảy ra.
- **Pseudo-instruction** là thành phần mô tả như label target, exception handler hoặc debug metadata; chúng không phải instruction JVM thông thường.

```text
MethodModel
    |
    +-- code(): Optional<CodeModel>
             |
             +-- CodeElement theo thứ tự
             |      +-- Instruction
             |      +-- LabelTarget
             |      +-- ExceptionCatch
             |      +-- PseudoInstruction / Attribute
             |
             +-- exceptionHandlers(): List<ExceptionCatch>
```

Thứ tự các element trong `CodeModel` có ý nghĩa. Đặc biệt, thứ tự instruction quyết định luồng bytecode; không sắp xếp lại danh sách này như thể nó là tập hợp không có thứ tự.

## Đọc CodeModel và instruction

`ClassFile.of().parse(...)` đọc file `.class` thành `ClassModel`. Từ `ClassModel.methods()` lấy các `MethodModel`; method có phần thân sẽ trả về `Optional<CodeModel>` qua `code()`.

Ví dụ sau in opcode, nhánh rẽ và các label target trong từng method:

```java
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.CodeElement;
import java.lang.classfile.CodeModel;
import java.lang.classfile.Instruction;
import java.lang.classfile.MethodModel;
import java.lang.classfile.instruction.BranchInstruction;
import java.lang.classfile.instruction.ExceptionCatch;
import java.lang.classfile.instruction.LabelTarget;
import java.nio.file.Path;

public class ReadMethodBytecode {
    public static void main(String[] args) throws IOException {
        ClassModel classModel = ClassFile.of().parse(Path.of(args[0]));

        for (MethodModel method : classModel.methods()) {
            System.out.println("Method: "
                    + method.methodName().stringValue()
                    + method.methodType().stringValue());

            method.code().ifPresent(code -> printCode(code));
        }
    }

    private static void printCode(CodeModel code) {
        for (CodeElement element : code) {
            if (element instanceof LabelTarget target) {
                System.out.println("  label target: " + target.label());
            } else if (element instanceof BranchInstruction branch) {
                System.out.println("  branch: " + branch.opcode()
                        + " -> " + branch.target());
            } else if (element instanceof Instruction instruction) {
                System.out.println("  instruction: " + instruction.opcode());
            }
        }

        for (ExceptionCatch handler : code.exceptionHandlers()) {
            String catchType = handler.catchType()
                    .map(type -> type.asInternalName())
                    .orElse("<catch all>");

            System.out.println("  exception range: "
                    + handler.tryStart() + " .. " + handler.tryEnd()
                    + ", handler=" + handler.handler()
                    + ", type=" + catchType);
        }
    }
}
```

Chạy với đường dẫn đến class file đã biên dịch, ví dụ:

```shell
javac -g Sample.java
javac ReadMethodBytecode.java
java ReadMethodBytecode Sample.class
```

Các kiểu quan trọng trong ví dụ:

| Kiểu | Ý nghĩa |
|---|---|
| `CodeModel` | Mô hình phần thân method; có thể duyệt như một `Iterable<CodeElement>`. |
| `CodeElement` | Kiểu gốc của các element xuất hiện trong phần thân method. |
| `Instruction` | Lệnh JVM thực thi được; `opcode()` trả về mnemonic dưới dạng `Opcode`. |
| `BranchInstruction` | Instruction có đích nhảy; `target()` trả về `Label` đích. |
| `LabelTarget` | Pseudo-instruction đánh dấu vị trí mà một `Label` đại diện. |
| `ExceptionCatch` | Entry trong exception table; chứa `tryStart`, `tryEnd`, `handler` và `catchType`. |

`CodeModel` cũng cung cấp `exceptionHandlers()` để đọc exception table trực tiếp. Trong biểu diễn streaming, exception entry còn xuất hiện như một `CodeElement` dạng pseudo-instruction.

### Label không phải bytecode offset cố định

`Label` là một marker cho vị trí trong danh sách instruction. Khi đọc class file, label gắn với bytecode index (BCI) trong `Code` attribute. Khi xây dựng hoặc biến đổi code, label giúp tham chiếu vị trí mà không cần tự tính BCI.

Khi duyệt `CodeModel`, `LabelTarget` cho biết label tương ứng với vị trí hiện tại. Khi tạo code, `CodeBuilder.newLabel()` tạo label chưa gắn vị trí; `labelBinding(label)` gắn label tại vị trí hiện tại. Mỗi label phải được bind đúng một lần trong `CodeBuilder` nơi nó được sử dụng.

Không nên lưu BCI rồi giả định nó vẫn đúng sau khi biến đổi bytecode. Thêm hoặc bỏ instruction có thể làm thay đổi offset. Khi biến đổi, hãy giữ và xử lý các label theo mô hình của Class-File API.

## Các loại nhánh rẽ thường gặp

`CodeBuilder` có các factory method tương ứng với mnemonic của JVM. Một số lệnh thường dùng:

| Factory method | Điều kiện hoặc hành vi |
|---|---|
| `ifeq(label)` | Nhảy nếu giá trị int trên operand stack bằng 0. |
| `ifne(label)` | Nhảy nếu giá trị int khác 0. |
| `iflt(label)`, `ifge(label)` | Nhảy nếu int nhỏ hơn 0 hoặc lớn hơn/bằng 0. |
| `if_icmplt(label)`, `if_icmpge(label)` | So sánh hai int trên stack rồi nhảy theo quan hệ nhỏ hơn hoặc lớn hơn/bằng. |
| `ifnull(label)`, `ifnonnull(label)` | Nhảy theo việc reference có phải `null` hay không. |
| `goto_(label)` | Nhảy vô điều kiện. Dùng tên `goto_` vì `goto` là keyword của Java. |
| `tableswitch(...)`, `lookupswitch(...)` | Nhánh theo một giá trị int với tập key liên tiếp hoặc rời rạc. |

Các nhánh có điều kiện tiêu thụ operand theo quy tắc của opcode. Vì vậy, khi tạo bytecode, cần kiểm soát chính xác giá trị nào đang nằm trên operand stack trước lệnh nhảy.

## Tạo bytecode với CodeBuilder

`ClassFile.of().build(...)` tạo class file mới. `ClassBuilder.withMethodBody(...)` là cách ngắn gọn để thêm method có phần thân; tham số cuối nhận một `Consumer<CodeBuilder>` để sinh các instruction.

Ví dụ method `abs(int)` được tạo bằng một nhánh điều kiện:

```java
Label nonNegative = code.newLabel();

code.iload(0)
    .ifge(nonNegative)
    .iload(0)
    .ineg()
    .ireturn()
    .labelBinding(nonNegative)
    .iload(0)
    .ireturn();
```

Giải thích:

1. `iload(0)` đưa tham số đầu tiên lên operand stack.
2. `ifge(nonNegative)` nhảy đến label nếu giá trị lớn hơn hoặc bằng 0; lệnh này lấy giá trị vừa đưa lên stack ra để kiểm tra.
3. Nếu điều kiện sai, `iload(0)` nạp lại tham số, `ineg()` đổi dấu và `ireturn()` trả kết quả.
4. `labelBinding(nonNegative)` gắn vị trí hiện tại cho nhánh không âm; code nạp tham số rồi trả nguyên giá trị.

Đối với method `static`, slot `0` là tham số đầu tiên. Với method instance, slot `0` thường dành cho `this`, nên tham số đầu tiên bắt đầu ở slot `1`. Kiểu `long` và `double` chiếm hai local variable slot.

## Tạo vòng lặp bằng label và goto

Một vòng lặp `for` hoặc `while` thường được biểu diễn bằng một label đầu vòng, nhánh kiểm tra điều kiện và một nhánh quay lại đầu vòng.

Ví dụ tạo method `sumTo(int n)` tính tổng từ 1 đến `n`:

```java
Label loop = code.newLabel();
Label done = code.newLabel();

code.iconst_0().istore(1)       // sum = 0
    .iconst_1().istore(2)       // i = 1
    .labelBinding(loop)
    .iload(2)
    .iload(0)
    .if_icmpgt(done)            // nếu i > n thì thoát
    .iload(1)
    .iload(2)
    .iadd()
    .istore(1)                  // sum += i
    .iinc(2, 1)                 // i++
    .goto_(loop)
    .labelBinding(done)
    .iload(1)
    .ireturn();
```

Ở đây:

- Slot `0` giữ tham số `n`.
- Slot `1` giữ biến cục bộ `sum`.
- Slot `2` giữ biến cục bộ `i`.
- `loop` là đích của nhánh quay lại sau mỗi vòng.
- `done` là đích của nhánh khi điều kiện dừng được thỏa mãn.

Đây là vòng lặp với biến `int`; nếu `n` quá lớn, tổng có thể tràn số nguyên như phép cộng `int` thông thường của Java. Khi cần miền giá trị rộng hơn, dùng local `long` và các instruction `lload`, `ladd`, `lstore`, `lreturn` phù hợp.

## Tạo exception handler

Trong file `.class`, `try/catch` được lưu trong exception table của `Code` attribute. Một entry mô tả:

- `tryStart`: đầu vùng instruction được bảo vệ.
- `tryEnd`: cuối vùng instruction được bảo vệ; đây là ranh giới không bao gồm instruction ở vị trí cuối.
- `handler`: vị trí bắt đầu đoạn xử lý exception.
- `catchType`: kiểu exception cần bắt; giá trị rỗng có nghĩa bắt tất cả exception và error.

`CodeBuilder.exceptionCatch(start, end, handler, catchType)` thêm entry có kiểu bắt cụ thể. `exceptionCatchAll(start, end, handler)` thêm entry bắt tất cả.

Khi JVM chuyển điều khiển tới handler, exception object được đặt trên operand stack. Handler phải tiêu thụ hoặc lưu object đó bằng `pop`, `astore` hoặc instruction phù hợp trước khi thực hiện các thao tác tiếp theo.

Ví dụ tạo method `safeDivide(int a, int b)`. Nếu chia cho 0, method bắt `ArithmeticException` và trả `-1`:

```java
Label tryStart = code.newLabel();
Label tryEnd = code.newLabel();
Label handler = code.newLabel();

code.labelBinding(tryStart)
    .iload(0)
    .iload(1)
    .idiv()
    .ireturn()
    .labelBinding(tryEnd)
    .labelBinding(handler)
    .pop()                       // bỏ ArithmeticException khỏi operand stack
    .iconst_m1()
    .ireturn()
    .exceptionCatch(
            tryStart,
            tryEnd,
            handler,
            ClassDesc.of("java.lang.ArithmeticException"));
```

Đường đi bình thường kết thúc tại `ireturn`. Nếu `idiv` ném `ArithmeticException`, JVM tìm entry phù hợp trong exception table và chuyển đến `handler`; `pop()` bỏ exception object rồi trả `-1`.

Khi nhiều exception handler có vùng bảo vệ chồng lấp, thứ tự entry trong exception table có ý nghĩa: JVM chọn handler phù hợp đầu tiên. Hãy sắp xếp entry theo đúng ý định bắt exception, từ kiểu cụ thể tới kiểu tổng quát nếu cần.

## Ví dụ hoàn chỉnh: sinh class có nhánh, vòng lặp và try/catch

Chương trình sau tạo `GeneratedFlow.class` với ba method tĩnh:

- `abs(int)`: tạo nhánh `ifge`.
- `sumTo(int)`: tạo vòng lặp bằng `Label`, `if_icmpgt` và `goto_`.
- `safeDivide(int, int)`: tạo exception table để bắt `ArithmeticException`.

```java
import java.lang.classfile.ClassFile;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;
import java.nio.file.Files;
import java.nio.file.Path;

import static java.lang.constant.ConstantDescs.CD_Object;
import static java.lang.constant.ConstantDescs.CD_int;

public class GenerateControlFlowClass {
    private static final int PUBLIC_STATIC =
            ClassFile.ACC_PUBLIC | ClassFile.ACC_STATIC;

    public static void main(String[] args) throws Exception {
        ClassDesc generatedClass = ClassDesc.of("GeneratedFlow");

        byte[] bytes = ClassFile.of().build(generatedClass, classBuilder ->
                classBuilder
                        .withVersion(ClassFile.JAVA_24_VERSION, 0)
                        .withFlags(ClassFile.ACC_PUBLIC | ClassFile.ACC_FINAL)
                        .withSuperclass(CD_Object)

                        .withMethodBody(
                                "abs",
                                MethodTypeDesc.of(CD_int, CD_int),
                                PUBLIC_STATIC,
                                code -> {
                                    var nonNegative = code.newLabel();

                                    code.iload(0)
                                        .ifge(nonNegative)
                                        .iload(0)
                                        .ineg()
                                        .ireturn()
                                        .labelBinding(nonNegative)
                                        .iload(0)
                                        .ireturn();
                                })

                        .withMethodBody(
                                "sumTo",
                                MethodTypeDesc.of(CD_int, CD_int),
                                PUBLIC_STATIC,
                                code -> {
                                    var loop = code.newLabel();
                                    var done = code.newLabel();

                                    code.iconst_0().istore(1)
                                        .iconst_1().istore(2)
                                        .labelBinding(loop)
                                        .iload(2)
                                        .iload(0)
                                        .if_icmpgt(done)
                                        .iload(1)
                                        .iload(2)
                                        .iadd()
                                        .istore(1)
                                        .iinc(2, 1)
                                        .goto_(loop)
                                        .labelBinding(done)
                                        .iload(1)
                                        .ireturn();
                                })

                        .withMethodBody(
                                "safeDivide",
                                MethodTypeDesc.of(CD_int, CD_int, CD_int),
                                PUBLIC_STATIC,
                                code -> {
                                    var tryStart = code.newLabel();
                                    var tryEnd = code.newLabel();
                                    var handler = code.newLabel();

                                    code.labelBinding(tryStart)
                                        .iload(0)
                                        .iload(1)
                                        .idiv()
                                        .ireturn()
                                        .labelBinding(tryEnd)
                                        .labelBinding(handler)
                                        .pop()
                                        .iconst_m1()
                                        .ireturn()
                                        .exceptionCatch(
                                                tryStart,
                                                tryEnd,
                                                handler,
                                                ClassDesc.of("java.lang.ArithmeticException"));
                                })
        );

        Files.write(Path.of("GeneratedFlow.class"), bytes);
    }
}
```

Chạy chương trình tạo class:

```shell
javac GenerateControlFlowClass.java
java GenerateControlFlowClass
```

Sau đó tạo một chương trình gọi các method vừa sinh:

```java
public class RunGeneratedFlow {
    public static void main(String[] args) {
        System.out.println(GeneratedFlow.abs(-7));
        System.out.println(GeneratedFlow.sumTo(5));
        System.out.println(GeneratedFlow.safeDivide(20, 0));
    }
}
```

Chạy:

```shell
javac RunGeneratedFlow.java
java RunGeneratedFlow
javap -c -v GeneratedFlow
```

Kết quả chạy chương trình:

```text
7
15
-1
```

`javap -c -v` hiển thị bytecode, branch offset và exception table để đối chiếu với các label và handler đã tạo. `javap` là công cụ quan sát class file; phần sinh class ở trên được thực hiện bằng Class-File API.

## Stack map và tính hợp lệ của bytecode

Một method có nhánh hoặc exception handler cần có trạng thái operand stack và local variable nhất quán tại các điểm điều khiển có thể hợp nhất. JVM dùng `StackMapTable` để hỗ trợ xác minh kiểu trong bytecode.

Class-File API mặc định dùng `StackMapsOption.STACK_MAPS_WHEN_REQUIRED`: tạo stack map hoặc tái sử dụng dữ liệu hiện có nếu tương thích. Khi tự tạo hoặc biến đổi bytecode, hãy giữ cấu trúc control flow hợp lệ để quá trình tạo stack map thành công.

`DROP_STACK_MAPS` chỉ phù hợp khi chương trình tự cung cấp `StackMapTable` cần thiết. Nếu code có branch hoặc exception handler mà bỏ stack map nhưng không cung cấp bảng tương ứng, class file có thể không vượt qua verifier của JVM.

Các điểm cần kiểm tra khi tạo bytecode:

- Mọi label được branch hoặc exception table tham chiếu phải được bind đúng một lần trong cùng `CodeBuilder`.
- Các nhánh hợp nhất phải có kiểu operand stack tương thích.
- Handler phải xử lý exception object đang có trên operand stack.
- Local variable slot phải đúng kiểu và đúng chỉ số; `long` và `double` chiếm hai slot.
- Instruction phải để lại stack shape phù hợp với đường đi tiếp theo và kiểu trả về của method.
- Vùng `tryStart` đến `tryEnd` phải bao đúng các instruction cần bảo vệ.
- Không tạo nhánh tới vị trí không hợp lệ hoặc để lại dead code khiến stack map generation thất bại.

Sau khi tạo file, có thể dùng `javap -c -v` để kiểm tra cấu trúc, rồi tải class và gọi method trong một chương trình thử nghiệm. Class-File API giúp xây dựng và kiểm tra cấu trúc class; nó không thay thế việc kiểm thử hành vi của chương trình.

## Chọn cách viết bytecode phù hợp

| Nhu cầu | Cách tiếp cận |
|---|---|
| Tạo một nhánh đơn giản | Dùng các factory method như `ifeq`, `ifge`, `if_icmpgt`, `goto_`. |
| Tạo vòng lặp hoặc control flow phức tạp | Dùng `newLabel`, `labelBinding` và branch instruction để điều khiển vị trí. |
| Tạo `if/else` thông thường | Có thể dùng `CodeBuilder.ifThen`, `ifThenElse` ở mức trừu tượng cao hơn. |
| Đăng ký vùng xử lý exception chính xác | Dùng `exceptionCatch` hoặc `exceptionCatchAll` với label đầu, cuối và handler. |
| Đọc bytecode hiện có | Duyệt `CodeModel` và phân loại `Instruction`, `BranchInstruction`, `LabelTarget`, `ExceptionCatch`. |
| Biến đổi bytecode hiện có | Dùng `CodeTransform`/`CodeBuilder.transforming` và giữ quan hệ giữa branch target, label cùng exception range. |

Với code được sinh từ Java source, thường không cần tạo bytecode thủ công. Class-File API hữu ích khi xây dựng compiler, agent, instrumentation, công cụ phân tích hoặc thư viện cần tạo và biến đổi class file ở cấp thấp.

## Tài liệu tham khảo

### JEP

- [JEP 457 — Class-File API (Preview, JDK 22)](https://openjdk.org/jeps/457)
- [JEP 466 — Class-File API (Second Preview, JDK 23)](https://openjdk.org/jeps/466)
- [JEP 484 — Class-File API (JDK 24)](https://openjdk.org/jeps/484)

### Java SE API

- [Java SE 27 API — `CodeModel`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/CodeModel.html)
- [Java SE 27 API — `CodeElement`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/CodeElement.html)
- [Java SE 27 API — `CodeBuilder`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/CodeBuilder.html)
- [Java SE 27 API — `Label`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/Label.html)
- [Java SE 27 API — `BranchInstruction`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/instruction/BranchInstruction.html)
- [Java SE 27 API — `ExceptionCatch`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/instruction/ExceptionCatch.html)
- [Java SE 27 API — `ClassFile.StackMapsOption`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.StackMapsOption.html)
- [Java Virtual Machine Specification — The `Code` Attribute](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html#jvms-4.7.3)
- [Java Virtual Machine Specification — Instructions](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-6.html#jvms-6.5)
