# Nhãn nhảy, bảng xử lý ngoại lệ và StackMapTable trong JVM class file

Khi đọc hoặc sửa bytecode bằng công cụ instrumentation, ba thành phần phải khớp với nhau: **đích nhảy của luồng điều khiển**, **phạm vi bắt ngoại lệ** và **trạng thái kiểu mà bộ kiểm tra bytecode (verifier) kỳ vọng**. Sai một offset hoặc một stack frame có thể khiến lớp bị từ chối bởi `VerifyError` hay `ClassFormatError`, dù mã nguồn Java ban đầu hợp lệ.

Sau bài này, bạn có thể đọc các mục `Code`, `Exception table` và `StackMapTable` trong kết quả `javap -v`; giải thích mối liên hệ giữa label, PC offset, handler và frame; đồng thời biết cách giữ bytecode hợp lệ khi chèn lệnh với ASM.

## 1. Ba thành phần nằm ở đâu?

Một phương thức có bytecode (khác phương thức `abstract` hoặc `native`) mang một thuộc tính `Code` trong cấu trúc `method_info`. Lược đồ rút gọn:

~~~text
method_info
└── Code
    ├── max_stack                 độ sâu operand stack tối đa
    ├── max_locals                số slot biến cục bộ
    ├── code[]                    dãy byte lệnh JVM
    ├── exception_table[]         các vùng bảo vệ và handler
    └── attributes[]
        ├── StackMapTable         trạng thái kiểu phục vụ verifier
        ├── LineNumberTable?      ánh xạ dòng nguồn (nếu có)
        └── LocalVariableTable?   thông tin debug biến (nếu có)
~~~

**Ba khái niệm khác nhau:**

| Thành phần | Câu hỏi nó trả lời | Hình thức |
|---|---|---|
| Nhãn nhảy (*label*) | Lệnh rẽ nhánh sẽ tới đâu? | Tên/ký hiệu của assembler hoặc thư viện bytecode; khi ghi class file được giải thành offset |
| `exception_table` | Ngoại lệ xảy ra ở đoạn nào thì chuyển tới handler nào? | Bảng các vùng `[start_pc, end_pc)` cùng `handler_pc`, `catch_type` trong `Code` |
| `StackMapTable` | Tại điểm điều khiển quan trọng, locals và operand stack phải có kiểu gì? | Các `stack_map_frame` bên trong `Code.attributes` |

**PC/bytecode offset** đếm **byte từ đầu mảng `code[]`**, không phải số thứ tự lệnh, dòng Java hay vị trí trong toàn bộ file `.class`. Lệnh JVM dài ngắn khác nhau, nên hai lệnh kề nhau không nhất thiết có offset chênh đúng 1.

## 2. Nhãn nhảy và luồng điều khiển

Ở mã Java, `if`, `while`, `for`, `switch`, `break` và `continue` tạo các đường đi khác nhau. Ở bytecode, JVM thực hiện lệnh rẽ nhánh tới một offset:

- `ifeq`, `ifne`, `iflt`, `ifge`, `if_icmp*`, `if_acmp*`, `ifnull`, `ifnonnull`: nhảy có điều kiện; nếu điều kiện sai, chạy tiếp lệnh kế.
- `goto` và `goto_w`: nhảy vô điều kiện. `goto` dùng độ dời có dấu 16 bit; `goto_w` dùng 32 bit.
- `tableswitch` và `lookupswitch`: nhiều đích nhảy, có cả nhánh mặc định; định dạng có byte đệm căn chỉnh nên thay đổi độ dài mã có thể dịch chuyển các offset.
- `return`, `ireturn`, `areturn`, `athrow`: kết thúc đường đi hiện tại theo cách tương ứng; chúng không phải label.

Trong biểu diễn class file, toán hạng của các lệnh nhảy thường là **độ dời có dấu tính từ byte đầu của chính opcode nhảy**. `javap -c` hiển thị **offset đích tuyệt đối** cho dễ đọc. Ví dụ một lệnh ở offset 1 được in `1: ifge 6` có độ dời được mã hóa là `6 - 1 = +5`, không phải `6 - offset của lệnh tiếp theo`.

Một `Label` trong ASM đánh dấu **vị trí**: `visitLabel(target)` xác định nơi các lệnh tham chiếu tới label sẽ trỏ đến; bản thân nó **không sinh một opcode**. Nhiều label có thể cùng trỏ một vị trí. Khi xuất bytecode, assembler tính lại độ dời và điều chỉnh độ rộng nhánh nếu cần. Mục tiêu nhảy phải là **đầu một opcode hợp lệ**, không được nhảy vào giữa toán hạng của lệnh khác.

Một điểm dễ nhầm: `LineNumberTable` phục vụ debug và ánh xạ dòng nguồn; nó không định nghĩa đích nhảy. Tên label do công cụ disassemble đặt ra cũng không phải tên được lưu nguyên văn trong class file.

## 3. Exception table: phạm vi bảo vệ và lối vào handler

Mỗi phần tử của `Code.exception_table` có bốn trường:

| Trường | Ý nghĩa | Ràng buộc trọng yếu |
|---|---|---|
| `start_pc` | Byte đầu của vùng được bảo vệ | Offset của một opcode; bao gồm điểm này |
| `end_pc` | Điểm kết thúc vùng được bảo vệ | **Không bao gồm** điểm này; là đầu opcode hoặc bằng `code_length` |
| `handler_pc` | Offset opcode đầu tiên của handler | Phải trỏ vào một opcode trong `code[]` |
| `catch_type` | Chỉ số tới `CONSTANT_Class_info` mô tả kiểu ngoại lệ | Khác 0: bắt kiểu đó và lớp con; bằng 0: bắt mọi ngoại lệ |

Điều kiện cốt lõi: `0 <= start_pc < end_pc <= code_length`, và `handler_pc < code_length`. Các trường đều là offset byte, không phải nhãn hoặc chỉ số dòng mã.

Giả sử một entry có phạm vi `[6, 10)`. Ngoại lệ phát sinh tại lệnh ở offset 6, 7, 8 hoặc 9 có thể khớp; **offset 10 thì không**, kể cả khi offset 10 chính là handler.

Khi một lệnh ném ngoại lệ, JVM xét các entry **theo đúng thứ tự trong bảng**. Entry đầu tiên thỏa cả hai điều kiện sẽ được chọn: vị trí lệnh ném nằm trong vùng bảo vệ và loại ngoại lệ phù hợp `catch_type` (hoặc `catch_type = 0`). Vì vậy, thứ tự handler rất quan trọng khi các vùng/kiểu bắt chồng lấn. Không có entry khớp thì ngoại lệ tiếp tục lan lên phương thức gọi.

Khi chuyển vào handler, operand stack của luồng thực thi được đặt lại để chỉ chứa **một tham chiếu đến ngoại lệ đang được xử lý**. Handler thường bắt đầu bằng `astore` để lưu tham chiếu đó vào một local; verifier phải biết loại tham chiếu hợp lệ tại điểm vào handler.

Trong bytecode, `try`/`catch` không có opcode riêng: **bảng ngoại lệ + các lệnh handler** biểu diễn chúng. Với `finally`, trình biên dịch có thể tạo đoạn cleanup dùng cả đường đi bình thường và handler bắt mọi ngoại lệ (`catch_type = 0`, rồi `athrow` để ném lại). `try-with-resources` còn tạo logic đóng tài nguyên và ngoại lệ bị ức chế (*suppressed exceptions*); không được suy ra đầy đủ cấu trúc Java chỉ từ một entry duy nhất.

**Đừng nhầm `exception_table` với thuộc tính `Exceptions`:** `Exceptions` liệt kê các checked exception đã khai báo ở chữ ký `throws`; `exception_table` mới quyết định bắt và chuyển luồng tại runtime. Việc JVM bắt unchecked exception cũng dựa trên bảng này khi có handler phù hợp.

## 4. StackMapTable: hợp đồng kiểu tại các điểm luồng hợp nhất

Một **type frame** mô tả hai trạng thái ở một vị trí bytecode:

1. **Locals:** kiểu verifier của từng biến cục bộ/slot còn có nghĩa tại điểm đó.
2. **Operand stack:** các kiểu đang nằm trên ngăn xếp toán hạng, theo đúng thứ tự và số phần tử.

Các nhánh có thể hội tụ về cùng offset. Verifier cần bảo đảm mọi đường đến đó mang trạng thái tương thích: chẳng hạn cùng chiều cao operand stack, giá trị trên stack phù hợp lệnh tiếp theo, các local đọc sau đó đã được khởi tạo và có kiểu hợp lệ. Nếu một đường mang `int`, đường khác mang tham chiếu đối tượng tới một lệnh đòi `int`, class sẽ không được chấp nhận chỉ vì mã có thể chạy ở một nhánh cụ thể.

`StackMapTable` lưu **các frame tại những offset cần thiết**, chứ không phải ảnh chụp tại từng lệnh. Đích rẽ nhánh, đích của `switch` và đầu handler là các vị trí đặc biệt cần xét. **Frame đầu tiên của phương thức là frame ngầm định** suy từ descriptor và cờ phương thức: với method instance có `this`; với static method chỉ có tham số. Trong constructor, `this` ban đầu có trạng thái `uninitializedThis` cho đến khi hoàn tất lời gọi khởi tạo phù hợp. Operand stack ban đầu rỗng.

Từ class file phiên bản **50.0 trở lên** (Java 6+), nếu một `Code` không có `StackMapTable`, JVM hiểu là có bảng frame ngầm định với **0 entry**. Điều này **không** có nghĩa có thể xóa mọi frame của phương thức có nhiều đích nhảy: bytecode vẫn phải đáp ứng quy tắc xác minh tương ứng. Một `Code` chỉ có tối đa một thuộc tính `StackMapTable`.

### 4.1. Kiểu dùng bởi verifier

Các dạng `verification_type_info` gồm `Top`, `Integer`, `Float`, `Long`, `Double`, `Null`, `UninitializedThis`, `Object` và `Uninitialized(offset)`.

- `Integer` đại diện trạng thái kiểm tra kiểu của `int` và các giá trị `boolean`, `byte`, `char`, `short` khi ở operand stack.
- `Object` tham chiếu kiểu qua constant pool; `Null` biểu diễn tham chiếu `null`.
- `Long` và `Double` chiếm **hai slot** theo mô hình JVM; định dạng frame có quy tắc riêng khi mã hóa các giá trị hai slot.
- `Uninitialized(offset)` theo dõi đối tượng vừa tạo bằng `new` nhưng chưa được khởi tạo hợp lệ qua `<init>`; không thể xem nó như tham chiếu đã khởi tạo.

Các kiểu này phục vụ **xác minh luồng dữ liệu**, không phải danh sách tên biến. `LocalVariableTable` nếu có chỉ là dữ liệu debug khác với `StackMapTable`.

### 4.2. Các dạng frame nén

| Dạng frame | Diễn đạt chính |
|---|---|
| `same_frame` | Locals như frame trước, operand stack rỗng |
| `same_locals_1_stack_item_frame` | Locals giữ nguyên, stack có đúng một kiểu |
| `same_locals_1_stack_item_frame_extended` | Như trên, nhưng dùng trường delta mở rộng |
| `chop_frame` | Bỏ một số local cuối so với frame trước |
| `append_frame` | Thêm một số local cuối so với frame trước |
| `same_frame_extended` | Locals giữ nguyên và stack rỗng, dùng delta mở rộng |
| `full_frame` | Ghi tường minh toàn bộ locals và operand stack |

Thay vì ghi offset tuyệt đối cho từng frame, `StackMapTable` mã hóa `offset_delta`:

- **Entry tường minh đầu tiên:** `offset = offset_delta`.
- **Các entry tiếp theo:** `offset = previous_offset + offset_delta + 1`.

Ví dụ frame ở offset 6 rồi offset 10 thì delta của frame thứ hai là `10 - 6 - 1 = 3`. Với các dạng frame ngắn, chính giá trị `frame_type` còn mang delta; chẳng hạn `same_frame` với delta 6 có `frame_type = 6`, còn `same_locals_1_stack_item_frame` với delta 3 có `frame_type = 64 + 3 = 67`.

**Một frame có offset đúng nhưng kiểu sai vẫn vô hiệu.** Thêm một lệnh `dup`, `astore`, `new`, hoặc thay đổi một nhánh có thể khiến cả stack height lẫn kiểu ở điểm hợp nhất thay đổi. `max_stack` và `max_locals` phải phù hợp nhưng **không thay thế** cho việc cập nhật StackMapTable.

## 5. Thực hành với Java 17+: tạo class file để xem ba thành phần

Lưu chương trình độc lập sau thành `BytecodeFlowDemo.java`:

~~~java
public final class BytecodeFlowDemo {
    static int safeDivide(int numerator, int denominator) {
        if (numerator < 0) {
            return -2;
        }
        try {
            return numerator / denominator;
        } catch (ArithmeticException ex) {
            return -1;
        }
    }

    public static void main(String[] args) {
        System.out.println(safeDivide(8, 2));
        System.out.println(safeDivide(8, 0));
        System.out.println(safeDivide(-3, 0));
    }
}
~~~

Biên dịch bằng JDK 17 hoặc mới hơn và chạy:

~~~bash
javac --release 17 BytecodeFlowDemo.java
java BytecodeFlowDemo
javap -v -c -p BytecodeFlowDemo
~~~

Stdout của lệnh `java BytecodeFlowDemo` là:

~~~text
4
-1
-2
~~~

Giải thích: `8 / 2` trả `4`; `8 / 0` ném `ArithmeticException` và handler trả `-1`; với `numerator = -3`, nhánh `if` trả `-2` **trước khi** phép chia được thực thi, nên không có ngoại lệ.

Trong đầu ra `javap`, tìm phương thức `safeDivide(int, int)` rồi đọc:

- `Code:` có các offset bytecode ở mép trái. `ifge`/lệnh rẽ nhánh tương đương dẫn vào nhánh tính toán; không có label tên như ở mã nguồn.
- `Exception table:` sẽ có entry bảo vệ phần phép chia và trỏ tới handler bắt `java/lang/ArithmeticException`; kiểm tra `from`, `to`, `target`.
- `StackMapTable:` cho biết các frame tại điểm rẽ nhánh và handler. Ở handler, stack có tham chiếu ngoại lệ phù hợp. Cách nén frame, số hiệu constant pool và các offset cụ thể có thể khác theo bản `javac`; **hãy đọc số do công cụ vừa tạo ra**, đừng sao chép một offset giả định.

Lệnh `javap -v` còn hiển thị **major version 61** khi biên dịch với `--release 17`. Nếu không thấy tên local hoặc số dòng, đó có thể là do thông tin debug không được sinh; quy tắc exception table và verifier vẫn tồn tại độc lập.

## 6. Đọc một ví dụ bytecode có offset được chọn rõ ràng

Xét **mã bytecode minh họa được thiết kế bằng tay** cho phương thức static nhận hai `int`: nếu đối số thứ nhất âm, trả `-1`; ngược lại chia hai số, nếu chia cho 0 thì trả `0`. Đây không phải khẳng định về offset do `javac` sinh.

~~~text
Offset  Lệnh       Ý nghĩa
0       iload_0    đưa a lên stack
1       ifge 6     nếu a >= 0, nhảy đến offset 6
4       iconst_m1  nhánh a < 0: đưa -1 lên stack
5       ireturn    trả -1
6       iload_0    bắt đầu vùng try
7       iload_1
8       idiv       có thể ném ArithmeticException
9       ireturn
10      astore_2   bắt đầu handler: lấy ngoại lệ từ stack
11      iconst_0
12      ireturn

Exception table:
From  To  Target  Type
6     10  10      java/lang/ArithmeticException
~~~

**Kiểm tra liên kết:**

1. `ifge` ở offset 1 nhảy tới **6**; độ dời được mã hóa là `+5`. Nhánh không thỏa điều kiện đi tới offset 4.
2. Vùng bảo vệ **`[6,10)`** bao gồm lệnh `idiv` tại 8 nhưng không bao gồm handler tại 10.
3. Khi `idiv` ném `ArithmeticException`, JVM đặt tham chiếu ngoại lệ lên operand stack và nhảy tới `10: astore_2`.
4. Hai frame tường minh tương ứng có thể mã hóa như sau (locals ban đầu là `[int, int]`):
   - Frame ở **6**: `same_frame`, `offset_delta = 6`, stack rỗng, `frame_type = 6`.
   - Frame ở **10**: `same_locals_1_stack_item_frame`, `offset_delta = 3`, stack chứa `Object(java/lang/ArithmeticException)`, `frame_type = 67`.
5. `max_stack = 2` đủ cho hai toán hạng trước `idiv`; `max_locals = 3` đủ cho đối số ở slot 0/1 và ngoại lệ ở slot 2.

Nếu chèn lệnh mới trước offset 6, các offset của nhánh, vùng bắt ngoại lệ và frame có thể cùng thay đổi. Chỉ sửa đích `ifge` mà giữ nguyên hai cấu trúc còn lại là một nguyên nhân thường gặp của class file hỏng.

## 7. Khi instrumentation bằng ASM

ASM cung cấp `org.objectweb.asm.Label` để biểu diễn vị trí và các visitor để xây dựng/sửa method. Đoạn sau là **một phần của trình tạo bytecode ASM**, không phải chương trình Java độc lập: giả định đã có `ClassWriter cw`, đã khai báo class và đang tạo method `static int divideOrZero(int, int)` với descriptor `(II)I`.

~~~java
MethodVisitor mv = cw.visitMethod(
        Opcodes.ACC_PUBLIC | Opcodes.ACC_STATIC,
        "divideOrZero", "(II)I", null, null);

Label start = new Label();
Label end = new Label();
Label handler = new Label();

mv.visitCode();
// Khai báo phạm vi catch trước khi visit các label liên quan.
mv.visitTryCatchBlock(
        start, end, handler, "java/lang/ArithmeticException");

mv.visitLabel(start);
mv.visitVarInsn(Opcodes.ILOAD, 0);
mv.visitVarInsn(Opcodes.ILOAD, 1);
mv.visitInsn(Opcodes.IDIV);

mv.visitLabel(end);                // end là exclusive
mv.visitInsn(Opcodes.IRETURN);     // đường đi thành công

mv.visitLabel(handler);            // handler nhận 1 exception trên stack
mv.visitVarInsn(Opcodes.ASTORE, 2);
mv.visitInsn(Opcodes.ICONST_0);
mv.visitInsn(Opcodes.IRETURN);

mv.visitMaxs(0, 0);                // ASM tự tính nếu COMPUTE_FRAMES
mv.visitEnd();
~~~

Để tính lại frame cho method được tạo/sửa, cấu hình writer ngay từ đầu, ví dụ:

~~~java
ClassWriter cw = new ClassWriter(ClassWriter.COMPUTE_FRAMES);
~~~

`COMPUTE_FRAMES` tính lại `StackMapTable` và **đồng thời** bao hàm `COMPUTE_MAXS`; nếu chỉ dùng `COMPUTE_MAXS`, ASM tính giới hạn stack/locals nhưng **không tự sửa các frame sai hoặc bị thiếu**. Việc tính frame cần biết quan hệ kế thừa của các kiểu đối tượng; triển khai mặc định của `getCommonSuperClass` có thể tải class. Với agent/class loader riêng hoặc biến đổi class chưa sẵn có trong classpath, hãy cấu hình chiến lược tra cứu hệ phân cấp phù hợp, không đoán mọi kiểu đều là `java/lang/Object`.

Một quy trình sửa method có kiểm soát:

1. Đọc **version**, descriptor, các nhánh, exception handlers và frames hiện có.
2. Đặt label ở **đầu opcode**; xác định rõ lệnh chèn nằm trong hay ngoài vùng `try`. ASM yêu cầu `visitTryCatchBlock` trước khi các label được tham chiếu đã được thăm.
3. Giữ nguyên thứ tự ưu tiên các handler chồng lấn; không để handler bắt rộng vô ý nuốt ngoại lệ hoặc thay đổi đường đi `finally`.
4. Tính lại nhánh, `max_stack`, `max_locals` và các frame theo bytecode sau cùng. Nếu giữ frame thủ công, phải cập nhật cả offsets lẫn trạng thái kiểu ở các điểm nhận điều khiển.
5. Kiểm tra class sau biến đổi bằng `javap -v -c -p` và thử tải/chạy với verifier. Nếu dùng ASM, `CheckClassAdapter` có thể giúp phát hiện lỗi cấu trúc/phân tích trước khi chạy.

Với biến đổi phương thức khởi tạo, tránh chèn thao tác sử dụng `this` như đối tượng đã hoàn tất khởi tạo trước lời gọi constructor hợp lệ. Khi chèn mã vào `try`/`finally`, nhớ rằng **ngoại lệ từ chính đoạn mã chèn** có thể được một handler hiện hữu bắt; đó là thay đổi hành vi đáng cân nhắc dù class vẫn qua verifier.

## 8. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `VerifyError: Expecting a stackmap frame at branch target ...` | Thêm/di chuyển đích nhảy nhưng thiếu frame thích hợp | Đối chiếu target trong `javap -c` với offset frame trong `javap -v` |
| `VerifyError: Bad type on operand stack` | Hai đường đi hợp nhất có kiểu stack không tương thích; hoặc dùng local chưa có kiểu đúng | Theo dõi hiệu ứng push/pop của từng opcode và trạng thái locals tại frame |
| `ClassFormatError` liên quan exception table | `start_pc`, `end_pc`, `handler_pc` sai ranh giới hoặc vượt `code_length` | Đọc lại `[start_pc, end_pc)` và đầu các opcode thực tế |
| Ngoại lệ bị bắt bởi nhánh `catch` bất ngờ | Thứ tự entry, kiểu bắt hoặc phạm vi bắt bị thay đổi | So sánh các handler theo **thứ tự xuất hiện** |
| Chạy thành công nhưng xử lý `finally` sai | Chèn code ngoài/giữa vùng cleanup, `return`/`athrow` đổi đường đi | Kiểm tra cả đường đi bình thường lẫn khi có ngoại lệ |
| ASM tính frame lỗi do không tìm thấy class | Giải hệ phân cấp dựa trên class loader/classpath không phù hợp | Kiểm tra `getCommonSuperClass` và class loader dùng cho transform |

Có thể chạy kiểm tra:

~~~bash
javap -v -c -p BytecodeFlowDemo
java -Xverify:all BytecodeFlowDemo
~~~

`-Xverify:all` yêu cầu JVM kiểm tra bytecode khi tải class theo chính sách xác minh hiện hành; việc chạy thử các nhánh có và không có ngoại lệ vẫn cần thiết để xác nhận **ngữ nghĩa**. Một chương trình vượt qua verifier chưa chắc đúng hành vi mong muốn.

## 9. Bài tự kiểm tra

1. Với entry `[6,10)` và ngoại lệ phát sinh ở offset `10`, entry đó có bắt không? **Không**, vì `end_pc` là exclusive.
2. Frame trước ở offset `6`, frame kế tiếp ở `10`: `offset_delta` của frame sau là bao nhiêu? **3**, vì `10 = 6 + 3 + 1`.
3. Khi vừa vào handler `catch (ArithmeticException e)`, operand stack có gì? **Một tham chiếu ngoại lệ** tương thích với kiểu catch, chứ không phải stack còn sót từ phép toán đang thực hiện.
4. Vì sao thêm một lệnh trước `goto` có thể làm hỏng class? Vì vị trí đích/vùng handler/frame và trạng thái stack có thể phải tính lại; label chỉ là cách công cụ giữ các tham chiếu nhất quán.
5. `COMPUTE_MAXS` có đủ để sửa một `StackMapTable` sai không? **Không**; cần cung cấp frame đúng hoặc tính lại bằng `COMPUTE_FRAMES` với thông tin kiểu đầy đủ.

**Ghi nhớ:** label giúp xác định **đi tới đâu**; `exception_table` quy định **ngoại lệ từ đâu tới handler nào**; `StackMapTable` bảo đảm **trạng thái kiểu ở điểm đến hợp lệ**. Cả ba cùng mô tả một đồ thị luồng điều khiển, nên instrumentation phải xem xét và kiểm chứng chúng như một chỉnh thể.

### Tài liệu chuẩn

- [JVMS Java SE 21, §4.7.3 — Code attribute và exception table](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.3)
- [JVMS Java SE 21, §4.7.4 — StackMapTable](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.4)
- [JVMS Java SE 21, §4.10.1 — Verification by Type Checking](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.10.1)
- [ASM MethodVisitor — visitLabel, visitTryCatchBlock](https://asm.ow2.io/javadoc/org/objectweb/asm/MethodVisitor.html)
- [ASM ClassWriter — COMPUTE_FRAMES và COMPUTE_MAXS](https://asm.ow2.io/javadoc/org/objectweb/asm/ClassWriter.html)