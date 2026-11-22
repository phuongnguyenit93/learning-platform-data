# Bytecode là gì trong Java?

## Mục tiêu

Sau bài này, bạn có thể giải thích bytecode và file .class khác nhau thế nào; mô tả cách javac chuyển source code thành bytecode; nhận biết cấu trúc cơ bản của class file; hiểu operand stack, local variables và các nhóm JVM instruction; dùng javap để đọc bytecode; kiểm tra class-file version; và liên hệ bytecode với quá trình class loading, verification, interpretation và JIT compilation.

## 1. Bytecode là gì?

**Bytecode** là tập lệnh trung gian mà compiler tạo ra để một runtime có thể thực thi. Trong Java, bytecode được thiết kế cho **Java Virtual Machine (JVM)**. JVM đọc bytecode, kiểm tra tính hợp lệ và thực thi theo đặc tả JVM.

Ví dụ, source code:

~~~java
int sum = 7 + 5;
~~~

có thể được compiler chuyển thành một chuỗi lệnh JVM như:

~~~text
bipush 7
iconst_5
iadd
istore_1
~~~

Các lệnh trên đẩy hai số nguyên lên operand stack, cộng chúng rồi lưu kết quả vào local variable. Đây là bytecode của JVM, không phải lệnh máy trực tiếp của CPU.

### Bytecode khác machine code như thế nào?

| Đặc điểm | JVM bytecode | Native machine code |
|---|---|---|
| Đích thực thi | JVM tương thích | CPU/ISA cụ thể như x86-64 hoặc AArch64 |
| Biểu diễn | JVM instruction set | Lệnh máy của bộ xử lý |
| Phụ thuộc kiến trúc | Không gắn với một CPU cụ thể | Phụ thuộc kiến trúc CPU |
| Kiểm tra | JVM có thể verify cấu trúc và kiểu | CPU không hiểu quy tắc kiểu Java |
| Thực thi | Interpreter và/hoặc JIT compiler của JVM | CPU thực thi trực tiếp |

Bytecode giúp cùng một class file có thể chạy trên các hệ điều hành và kiến trúc khác nhau, miễn là có JVM tương thích và các dependency cần thiết. Điều đó không có nghĩa mọi ứng dụng Java tự động chạy ở mọi nơi: phiên bản class file, API của JDK, thư viện native, quyền hệ thống và môi trường triển khai vẫn có thể tạo ra khác biệt.

### Bytecode không phải Java source code

Bytecode đã được compiler dịch từ source. Nó không giữ nguyên comment, khoảng trắng hoặc cách trình bày ban đầu. Một số thông tin như tên biến local và số dòng source có thể được lưu trong debug attributes, nhưng các thông tin này có thể bị lược bỏ.

Một class file cũng có thể được tạo từ ngôn ngữ khác trên JVM như Kotlin hoặc Scala. Vì vậy, .class không nhất thiết được tạo từ một file .java.

## 2. Từ source code đến bytecode

Quy trình cơ bản:

~~~text
BytecodeDemo.java
       |
       | javac
       v
BytecodeDemo.class
       |
       | java / Java launcher
       v
JVM
       |
       +--> Load class
       +--> Link and verify
       +--> Initialize class
       +--> Execute bytecode
                 |
                 +--> Interpreter
                 +--> JIT compiler
                           |
                           v
                    Native machine code
~~~

**javac** đọc source code, kiểm tra cú pháp và kiểu, thực hiện các bước phân tích cần thiết rồi sinh class file. Nếu có lỗi biên dịch, compiler không tạo được class file hợp lệ cho phần code lỗi.

**java** là Java launcher. Launcher xác định class/JAR/module/source file cần chạy, thiết lập môi trường và khởi động JVM phù hợp. JVM nạp class file, kiểm tra, liên kết, khởi tạo và thực thi bytecode.

Không nên hiểu rằng mọi bytecode đều được dịch toàn bộ thành native code ngay khi JVM bắt đầu. JVM có thể thông dịch bytecode trước, thu thập thông tin về hành vi thực tế, rồi JIT compile những method hoặc đoạn code đủ nóng (hot) thành native code. Cách tối ưu cụ thể phụ thuộc JVM và workload.

## 3. File .class và bytecode khác nhau

Hai khái niệm liên quan nhưng không đồng nghĩa:

- **Class file (.class)** là định dạng file nhị phân được JVM hiểu.
- **Bytecode instructions** là các lệnh nằm trong Code attribute của method trong class file.

Một class file chứa nhiều metadata ngoài bytecode, ví dụ:

- Phiên bản định dạng class file.
- Tên class, superclass và interfaces.
- Constant pool với các hằng số và symbolic reference.
- Field và method declarations.
- Access flags như public, final, abstract, interface.
- Descriptors mô tả kiểu field và chữ ký method.
- Attributes như Code, Exceptions, SourceFile, Signature, annotations, StackMapTable và thông tin debug.

Một file source có thể tạo nhiều class file. Ví dụ, class lồng nhau, anonymous class hoặc một số cấu trúc được compiler sinh thêm có thể tạo các file như Outer.class, Outer$Inner.class. Ngược lại, một class file cũng có thể được tạo bởi compiler của ngôn ngữ JVM khác.

JAR là một gói lưu trữ dựa trên ZIP có thể chứa nhiều class file, resource và metadata. JAR không phải bytecode; nó là container chứa class file cùng các tài nguyên khác.

## 4. Cấu trúc cơ bản của class file

Class file có cấu trúc nhị phân được định nghĩa trong JVM Specification. Có thể hình dung các trường chính như sau:

~~~text
ClassFile {
    magic
    minor_version
    major_version
    constant_pool
    access_flags
    this_class
    super_class
    interfaces
    fields
    methods
    attributes
}
~~~

Đây là sơ đồ khái quát, không phải source code Java.

### Magic number

Bốn byte đầu tiên của một class file hợp lệ là:

~~~text
CA FE BA BE
~~~

Đây là magic number **0xCAFEBABE**, giúp nhận diện định dạng class file. Nếu file bị hỏng, tải nhầm file hoặc đổi phần mở rộng một file không phải class file thành .class, JVM có thể báo lỗi định dạng class.

### Class-file version

Class file chứa minor_version và major_version. Major version thể hiện thế hệ định dạng class file mà compiler tạo ra.

Một số mốc thường gặp:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |
| Java 26 | 70 |

Ví dụ, class file major version 61 tương ứng Java 17. Nếu class file được tạo bằng Java 25 (major 69) nhưng chạy trên JVM chỉ hỗ trợ đến Java 21 (major 65), JVM không thể nạp class đó và có thể ném UnsupportedClassVersionError.

Với class file sử dụng preview features, minor version có thể là 65535. Những class file preview này cần runtime cùng release tương ứng và tùy chọn --enable-preview; không thể mang class preview của một release sang chạy như class preview của release khác.

### Constant pool

Constant pool lưu các hằng số và symbolic reference mà class file cần dùng. Các entry có thể mô tả:

- Tên class, interface, field và method.
- Chuỗi literal và numeric constants.
- Field reference, method reference và interface method reference.
- Name-and-type descriptors.
- Method handle và method type.
- Dynamic hoặc invokedynamic call-site metadata.
- Module và package metadata.

Ví dụ, lệnh gọi System.out.println(...) cần tham chiếu đến field System.out và method PrintStream.println. Class file lưu các symbolic reference trong constant pool; JVM sẽ phân giải chúng theo cơ chế linking khi cần.

Constant pool không chỉ là danh sách literal. Nó còn là cầu nối giữa bytecode instruction và tên class/member mà instruction cần truy cập.

### Fields, methods và attributes

Phần fields mô tả field của class: access flags, tên, descriptor và attributes. Phần methods mô tả method/constructor tương tự.

Với method có thân thực thi, bytecode thường nằm trong Code attribute. Method abstract hoặc native không có phần Code thông thường vì chúng không có Java bytecode body trong class file.

Attributes cung cấp metadata mở rộng. Một số ví dụ:

| Attribute | Mục đích |
|---|---|
| Code | Bytecode, stack/local limits, exception table và attributes của method |
| LineNumberTable | Ánh xạ vị trí bytecode với số dòng source |
| LocalVariableTable | Tên và kiểu local variable phục vụ debug |
| StackMapTable | Các verification type frame phục vụ bytecode verification |
| SourceFile | Tên file source liên quan nếu được ghi |
| Signature | Thông tin generic signature |
| RuntimeVisibleAnnotations | Annotation cần giữ để runtime có thể đọc |
| BootstrapMethods | Bootstrap method metadata cho invokedynamic/dynamic constants |

Không phải class file nào cũng có đầy đủ mọi attribute. Một số attributes chỉ xuất hiện khi compiler hoặc công cụ cần chúng.

## 5. Code attribute và stack frame

Một Code attribute của method chứa các thành phần quan trọng:

- max_stack: độ sâu tối đa của operand stack mà method cần.
- max_locals: số slot local variable cần thiết.
- code: chuỗi bytecode instructions.
- exception_table: thông tin xử lý exception trong vùng code.
- Các nested attributes như StackMapTable, LineNumberTable hoặc LocalVariableTable.

Khi một method được gọi, JVM tạo một **frame** cho lần gọi đó. Frame có:

1. **Local variable array:** chứa tham số và local variables.
2. **Operand stack:** nơi các instruction lấy toán hạng và đẩy kết quả.
3. **Reference đến runtime constant pool:** phục vụ symbolic resolution và thao tác với constant pool của class.

Mỗi method invocation có frame riêng. Khi method kết thúc bình thường, giá trị trả về (nếu có) được chuyển về caller và frame bị loại bỏ. Khi exception được ném, JVM tìm exception handler phù hợp theo exception table và stack unwinding.

Local variables được truy cập bằng các instruction như iload, istore, aload, astore. Operand stack được sử dụng bởi các instruction như iadd, imul, getfield, invokevirtual và ireturn.

Đây là mô hình stack-based: phần lớn phép toán JVM thao tác trên operand stack thay vì chỉ định trực tiếp các thanh ghi CPU như trong native machine code.

## 6. Một số nhóm JVM bytecode instructions

JVM có instruction set được mô tả trong JVM Specification. Tên instruction thường thể hiện kiểu dữ liệu hoặc hành động.

### Nạp và lưu local variable

| Instruction | Ý nghĩa |
|---|---|
| iload | Đẩy local variable kiểu int lên operand stack |
| lload | Đẩy local variable kiểu long lên operand stack |
| fload / dload | Nạp float / double |
| aload | Nạp reference |
| istore / astore | Lấy giá trị trên stack và lưu vào local variable |

Ví dụ:

~~~text
iload_0
istore_1
~~~

Nạp local variable slot 0 lên stack rồi lưu giá trị đó vào slot 1. Các dạng có hậu tố _0, _1, _2, _3 là dạng rút gọn cho một số slot phổ biến.

### Hằng số và phép toán

| Instruction | Ý nghĩa |
|---|---|
| iconst_0, iconst_1, ... | Đẩy một số int nhỏ thường dùng lên stack |
| bipush | Đẩy một hằng số byte có dấu |
| sipush | Đẩy một hằng số short có dấu |
| ldc | Nạp một hằng số từ constant pool |
| iadd / isub / imul / idiv | Cộng / trừ / nhân / chia int |
| ladd / dadd | Cộng long / double |

Ví dụ:

~~~text
bipush 7
iconst_5
iadd
~~~

Sau ba lệnh, operand stack chứa kết quả int 12.

### Điều khiển luồng

- ifeq, ifne, iflt, if_icmpge: nhảy có điều kiện.
- goto: nhảy không điều kiện.
- tableswitch, lookupswitch: triển khai nhánh switch.
- ireturn, areturn, return: kết thúc method và trả về giá trị phù hợp.

Các nhánh trong bytecode sử dụng offset để xác định vị trí đích. Compiler có thể chuyển một cấu trúc if/else hoặc loop trong source thành nhiều instruction và nhánh khác nhau.

### Truy cập field và gọi method

| Instruction | Ý nghĩa khái quát |
|---|---|
| getstatic / putstatic | Đọc / ghi static field |
| getfield / putfield | Đọc / ghi instance field |
| invokestatic | Gọi static method |
| invokevirtual | Gọi instance method theo cơ chế virtual dispatch |
| invokespecial | Gọi constructor, private method hoặc một số lời gọi đặc biệt |
| invokeinterface | Gọi method qua interface |
| invokedynamic | Gọi thông qua call site được bootstrap method liên kết |

### Tạo object, kiểm tra kiểu và exception

- new: tạo object chưa khởi tạo trên heap theo quy tắc JVM.
- dup: nhân đôi giá trị ở đỉnh operand stack, thường thấy trong chuỗi tạo object.
- invokespecial <init>: gọi constructor để khởi tạo object.
- checkcast: kiểm tra và cast reference; có thể ném ClassCastException.
- instanceof: kiểm tra object có tương thích với kiểu hay không.
- athrow: ném exception.

Một biểu thức new User("An") trong source thường được compiler chuyển thành chuỗi instruction có new, dup, nạp đối số và invokespecial tới constructor. Không có một instruction duy nhất tương đương toàn bộ biểu thức source này.

## 7. Bytecode của một phép cộng đơn giản

Source code:

~~~java
public class BytecodeDemo {
    public static int add(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) {
        int result = add(7, 5);
        System.out.println("sum=" + result);
    }
}
~~~

Method add có thể được biểu diễn bằng các instruction chính sau:

~~~text
iload_0
iload_1
iadd
ireturn
~~~

Giải thích:

1. iload_0 đẩy tham số left lên operand stack.
2. iload_1 đẩy tham số right lên operand stack.
3. iadd lấy hai số int, cộng chúng và đẩy kết quả lên stack.
4. ireturn lấy int kết quả và trả về caller.

Với method main, compiler cần nạp hai đối số 7 và 5, gọi add bằng invokestatic, lưu kết quả, truy cập System.out, tạo chuỗi và gọi println. Các chi tiết như constant-pool index, bytecode offset và cách nối chuỗi có thể khác giữa các compiler/JDK.

## 8. Tạo và chạy ví dụ thực tế

Tạo file BytecodeDemo.java:

~~~java
public class BytecodeDemo {
    public static int add(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) {
        int result = add(7, 5);
        System.out.println("sum=" + result);
    }
}
~~~

Biên dịch bằng JDK 17 trở lên, đồng thời yêu cầu source/API và class-file target Java 17:

~~~bash
javac --release 17 -g BytecodeDemo.java
~~~

Lệnh trên tạo BytecodeDemo.class trong thư mục hiện tại. Tùy chọn -g yêu cầu compiler ghi thông tin debug.

Chạy chương trình:

~~~bash
java BytecodeDemo
~~~

Output chính xác:

~~~text
sum=12
~~~

Dùng javap để đọc bytecode:

~~~bash
javap -c -p -s BytecodeDemo
~~~

- -c: hiển thị bytecode instructions.
- -p: hiển thị cả member private.
- -s: hiển thị internal type signatures/descriptors.

Để xem cấu trúc chi tiết:

~~~bash
javap -v BytecodeDemo
~~~

Output verbose bao gồm class-file version, constant pool, access flags, field/method descriptors và attributes. Dòng major version: 61 xác nhận class file được tạo cho Java 17.

Có thể xem bytecode của class trong JAR bằng cách chỉ định classpath:

~~~bash
javap -classpath app.jar -c -p com.example.Main
~~~

Nếu javap báo không tìm thấy class, kiểm tra package name và classpath. javap là disassembler để đọc class file; nó không khôi phục chính xác Java source ban đầu.

## 9. Đọc method descriptor

Trong class file, descriptor mô tả kiểu tham số và kiểu trả về của field/method theo cú pháp JVM.

Một số ký hiệu:

| Ký hiệu | Kiểu |
|---|---|
| Z | boolean |
| B | byte |
| C | char |
| S | short |
| I | int |
| J | long |
| F | float |
| D | double |
| V | void (chỉ dùng cho kiểu trả về) |
| Ljava/lang/String; | java.lang.String |
| [I | int[] |
| [Ljava/lang/String; | String[] |

Ví dụ descriptor:

~~~text
(II)I
~~~

Có nghĩa method nhận hai tham số int và trả về int.

~~~text
([Ljava/lang/String;)V
~~~

Có nghĩa method nhận một tham số String[] và trả về void. Đây là descriptor quen thuộc của main(String[] args).

Descriptor không chứa tên tham số source như left hoặc right. Tên tham số chỉ có thể xuất hiện trong debug metadata nếu compiler ghi lại.

## 10. Bytecode verification

Trước khi thực thi class, JVM kiểm tra class file có tuân thủ các ràng buộc cấu trúc và type-safety mà JVM Specification yêu cầu hay không.

Verifier kiểm tra nhiều điều kiện, ví dụ:

- Cấu trúc class file và constant pool hợp lệ.
- Bytecode instruction có opcode và operand hợp lệ.
- Operand stack không bị underflow hoặc có trạng thái kiểu không hợp lệ.
- Local variable và operand stack được sử dụng theo kiểu phù hợp.
- Các nhánh điều khiển và exception handler có trạng thái stack tương thích.
- Truy cập và lời gọi member phù hợp với các quy tắc kiểm tra liên quan.

StackMapTable có thể cung cấp verification type frames tại các điểm điều khiển quan trọng. JVM dùng các frame này cùng bytecode để kiểm tra tính nhất quán của kiểu và trạng thái stack. Class file do compiler chuẩn tạo ra thường có metadata cần thiết cho quá trình này.

Verification giúp JVM từ chối bytecode sai cấu trúc hoặc vi phạm quy tắc an toàn trước khi thực thi phần code tương ứng. Tuy nhiên, verification không chứng minh ứng dụng đúng nghiệp vụ, không ngăn mọi lỗi logic, không bảo đảm không có NullPointerException và cũng không thay thế kiểm thử bảo mật.

## 11. Từ bytecode đến native code: interpreter và JIT

JVM có thể thực thi bytecode theo nhiều cách:

### Interpreter

Interpreter đọc bytecode instruction và thực hiện hành động tương ứng. Cách này cho phép bắt đầu chạy nhanh mà không cần compile trước toàn bộ ứng dụng sang native code.

### JIT compiler

Just-In-Time compiler quan sát code khi chương trình chạy. Method hoặc code path được thực thi thường xuyên có thể được compile thành native machine code để tăng hiệu năng.

HotSpot JVM có các tầng biên dịch và tối ưu hóa khác nhau. JIT có thể inline method, loại bỏ một số kiểm tra khi có đủ bằng chứng, tối ưu vòng lặp và tận dụng thông tin runtime. Tối ưu hóa phụ thuộc profile và có thể bị deoptimize khi giả định không còn đúng.

### Vì sao không nên suy luận hiệu năng chỉ từ bytecode?

Bytecode là một phần của đầu vào cho JVM. Hiệu năng thực tế còn phụ thuộc:

- JVM implementation và phiên bản.
- JIT compiler, tiered compilation và profiling.
- Garbage collector và cấu hình heap.
- CPU, RAM, hệ điều hành và container limits.
- Dữ liệu đầu vào, concurrency và workload.
- Thư viện, I/O, network và native code.

Hai distribution có thể chạy cùng class file nhưng có hiệu năng khác nhau. Ngay cả hai phiên bản JVM cùng vendor cũng có thể tối ưu khác nhau. Hãy benchmark trên workload thực tế thay vì chỉ đếm số bytecode instruction.

## 12. Tương thích class-file version

Một JVM chỉ hỗ trợ một dải class-file version nhất định. Khi class file mới hơn runtime, lỗi thường gặp là:

~~~text
java.lang.UnsupportedClassVersionError
~~~

Ví dụ: code được biên dịch bằng JDK 25 tạo major version 69, nhưng ứng dụng lại chạy trên JDK 21 chỉ hỗ trợ major version đến 65.

### Dùng --release để chọn target

Nếu đang dùng JDK 21 nhưng muốn tạo class file tương thích Java 17:

~~~bash
javac --release 17 -d out src/BytecodeDemo.java
~~~

--release 17 yêu cầu compiler dùng quy tắc ngôn ngữ, API Java SE và class-file target của Java 17. Nó an toàn hơn việc chỉ đặt -source 17 -target 17, vì hai tùy chọn cũ không tự giới hạn API platform theo release đích.

Nếu dự án dùng Gradle hoặc Maven, hãy cấu hình Java toolchain và release target nhất quán trong build thay vì chỉ dựa vào JDK đang có trong terminal.

### Kiểm tra class-file version

~~~bash
javap -verbose BytecodeDemo
~~~

Tìm dòng major version. Đối chiếu con số với bảng version ở phần trên để xác định release mục tiêu.

Preview class file cần runtime đúng release và --enable-preview. Một class file preview của Java 25 không phải class file preview của Java 26.

## 13. Debug metadata và giới hạn khi đọc ngược bytecode

Compiler có thể lưu một số metadata giúp debugger và công cụ phân tích liên hệ bytecode với source:

- SourceFile: tên file source.
- LineNumberTable: ánh xạ bytecode offset với số dòng source.
- LocalVariableTable: tên và descriptor của local variable trong một khoảng bytecode.
- LocalVariableTypeTable: generic signature của local variable nếu có.

Dùng javac -g để yêu cầu ghi thông tin debug đầy đủ. Có thể dùng javac -g:none để loại bỏ debug information.

Khi thiếu debug metadata:

- Debugger có thể không hiển thị tên local variable.
- Stack trace vẫn thường có class, method và số dòng nếu LineNumberTable còn tồn tại; nếu không có, số dòng có thể là Unknown Source.
- javap vẫn hiển thị instruction nhưng khó liên hệ chúng với tên biến source.

Bytecode không giữ nguyên comment, tên biến cục bộ nếu không được ghi, cấu trúc vòng lặp/điều kiện đúng như source, hoặc cách viết biểu thức ban đầu. Decompiler có thể dựng lại source gần đúng nhưng không thể bảo đảm tái tạo nguyên văn file gốc.

## 14. Những hiểu lầm thường gặp

### “Bytecode là mã máy”

Không đúng. Bytecode là instruction set của JVM. JVM interpreter hoặc JIT mới chuyển hành vi đó thành các thao tác phù hợp với nền tảng, có thể gồm native machine code.

### “Một file .class chỉ chứa bytecode”

Không đúng. Class file còn chứa constant pool, class/member metadata, descriptors, access flags, attributes và có thể có bytecode trong Code attribute của từng method.

### “Java chạy được ở mọi nơi vì bytecode độc lập nền tảng”

Độc lập nền tảng chỉ có nghĩa class file nhắm đến JVM tương thích. Ứng dụng vẫn cần đúng Java API, dependency, native library, quyền hệ thống và cấu hình phù hợp.

### “javap có thể khôi phục source code chính xác”

Không đúng. javap disassemble bytecode và hiển thị metadata. Nó không khôi phục comment, formatting hay mọi tên biến đã bị compiler loại bỏ.

### “Bytecode verification bảo đảm chương trình không có bug”

Không đúng. Verification tập trung vào tính hợp lệ và an toàn cấu trúc/kiểu của bytecode theo JVM. Lỗi nghiệp vụ, dữ liệu null, race condition, deadlock, lỗi I/O và nhiều vấn đề runtime vẫn có thể xảy ra.

## 15. Quy trình thực hành khi cần kiểm tra bytecode

1. Xác định source file hoặc class file cần kiểm tra.
2. Biên dịch bằng đúng JDK và --release mục tiêu.
3. Dùng javap -verbose để xem class-file version và constant pool.
4. Dùng javap -c -p để xem instruction của từng method.
5. Theo dõi local variable và operand stack để hiểu từng phép toán.
6. Xem descriptor để biết kiểu tham số/kiểu trả về.
7. Kiểm tra StackMapTable và exception table khi điều tra lỗi verification hoặc control flow.
8. Nếu class nằm trong JAR, chỉ định đúng classpath và fully qualified class name.
9. Đối chiếu runtime JDK với class-file major version.
10. Dùng profiler/JFR và benchmark nếu mục tiêu là phân tích hiệu năng; không kết luận hiệu năng chỉ từ disassembly.

## 16. Checklist ghi nhớ

- [ ] Phân biệt bytecode với native machine code.
- [ ] Hiểu .class là container nhị phân, còn bytecode nằm trong Code attribute.
- [ ] Nhận biết magic number CAFEBABE.
- [ ] Biết class-file major version và lỗi UnsupportedClassVersionError.
- [ ] Hiểu constant pool, fields, methods và attributes.
- [ ] Hiểu local variables, operand stack và frame.
- [ ] Nhận biết các nhóm instruction như load/store, arithmetic, branch, invoke và return.
- [ ] Dùng javap -c để disassemble và javap -v để xem metadata.
- [ ] Dùng javac --release để tạo class file tương thích với release mục tiêu.
- [ ] Phân biệt bytecode verification với kiểm thử chức năng và bảo mật.
- [ ] Hiểu interpreter/JIT và không đánh giá hiệu năng chỉ qua bytecode.
- [ ] Biết giới hạn của debug metadata và decompilation.

## 17. Tài liệu tham khảo chính thức

- [Java Virtual Machine Specification, Java SE 26 — Chapter 4: The class File Format](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html) — cấu trúc class file, constant pool, Code attribute, verification và attributes.
- [Java Virtual Machine Specification, Java SE 26 — Chapter 6: The Java Virtual Machine Instruction Set](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-6.html) — danh sách bytecode instructions và semantics của từng lệnh.
- [javac — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — compiler options, --release, -g và cách tạo class file.
- [javap — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html) — cách disassemble và đọc class file.
- [Java Virtual Machine Specification, Java SE 26 — Chapter 5: Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-5.html) — vòng đời nạp, liên kết, verification và khởi tạo class.

Bytecode là lớp trung gian kết nối Java source với JVM. Khi biết cách đọc class-file structure, operand stack và instruction, bạn có thể hiểu compiler đã tạo gì, chẩn đoán lỗi tương thích class file và đọc được nhiều chi tiết runtime mà source code không thể hiện trực tiếp.
