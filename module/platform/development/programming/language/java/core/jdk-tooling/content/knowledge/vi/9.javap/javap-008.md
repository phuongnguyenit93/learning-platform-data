# Đọc bytecode Java bằng javap

**javap** là công cụ dòng lệnh đi kèm JDK để đọc thông tin của class file và hiển thị bytecode dưới dạng mnemonic dễ quan sát hơn. Nó giúp hiểu compiler đã biến mã nguồn Java thành các lệnh JVM như thế nào, kiểm tra phiên bản class file, descriptor của method, constant pool, thông tin debug và cấu trúc class.

javap thường được gọi là *disassembler* cho Java bytecode. Nó không khôi phục đầy đủ source code gốc như một decompiler. Công cụ hiển thị cấu trúc đã được lưu trong file .class; tên biến cục bộ, comment, định dạng source và một số thông tin khác có thể đã mất sau biên dịch.

## 1. Bytecode là gì và javap giúp gì?

Khi biên dịch một tệp Java, javac chuyển source code thành một hoặc nhiều class file. Mỗi class file chứa cấu trúc mà JVM hiểu, gồm constant pool, thông tin class, field, method, attributes và các chuỗi bytecode của method.

Bytecode là tập lệnh trung gian của JVM, không phải mã máy dành riêng cho một CPU. JVM có thể diễn giải bytecode hoặc biên dịch các đoạn code thường chạy thành mã máy bằng JIT compiler.

Ví dụ, biểu thức Java:

~~~java
int sum = a + b;
~~~

có thể được biểu diễn bằng các lệnh JVM như:

~~~text
iload_0
iload_1
iadd
istore_2
~~~

Các lệnh này lần lượt tải hai biến kiểu int lên operand stack, cộng chúng và lưu kết quả vào local variable slot. javap giúp xem những lệnh tương tự bên trong class file thực tế.

Các tình huống thường dùng javap:

- Hiểu compiler sinh bytecode nào cho một đoạn Java.
- Kiểm tra class file major/minor version.
- Đọc method descriptor, access flags và constant pool.
- Tìm lời gọi method, field access, nhánh điều khiển và exception handler.
- Điều tra khác biệt giữa các compiler option hoặc phiên bản JDK.
- Xác minh class trong JAR, dependency hoặc module.
- Kiểm tra thông tin debug như line number và local variable table.

## 2. Chuẩn bị và cú pháp cơ bản

javap nằm trong thư mục **bin** của JDK, cùng nhóm công cụ với javac, java và jar. Có thể kiểm tra:

~~~bash
javap -version
javap -help
~~~

Cú pháp tổng quát:

~~~bash
javap [options] class...
~~~

Đầu vào thường là tên class đầy đủ (fully qualified class name), đường dẫn tới file .class hoặc class được tìm thấy qua classpath/module path.

Ví dụ, nếu class nằm trong package demo và thư mục output là out:

~~~bash
javap -classpath out demo.Calculator
~~~

Nếu truyền trực tiếp đường dẫn class file:

~~~bash
javap out/demo/Calculator.class
~~~

Tên class có package phải dùng dấu chấm, ví dụ demo.Calculator; đường dẫn file dùng dấu gạch chéo theo cấu trúc thư mục. Khi kiểm tra nhiều class, có thể truyền nhiều tên class trong cùng một lệnh.

## 3. Những tùy chọn javap quan trọng

| Tùy chọn | Công dụng |
|---|---|
| -c | Hiển thị bytecode instructions trong method |
| -p hoặc -private | Hiển thị mọi class member, gồm private |
| -v hoặc -verbose | Hiển thị thông tin chi tiết: constant pool, flags, attributes, stack map frames và nhiều metadata khác |
| -l | Hiển thị line number table và local variable table nếu class file có lưu |
| -s | Hiển thị internal type signature / descriptor của field và method |
| -constants | Hiển thị giá trị hằng số static final có thể biểu diễn trong constant pool |
| -sysinfo | Hiển thị thông tin hệ thống về class file đang kiểm tra |
| -classpath hoặc --class-path | Chỉ định nơi tìm class |
| --module | Chỉ định module chứa class cần xem |
| --module-path | Chỉ định nơi tìm các module |
| --multi-release | Chọn phiên bản entry trong multi-release JAR để phân tích |

Các tùy chọn có thể kết hợp. Ví dụ:

~~~bash
javap -c -p -classpath out demo.Calculator
javap -v -p -classpath out demo.Calculator
javap -c -l -p -classpath out demo.Calculator
javap -s -p -classpath out demo.Calculator
~~~

Cách đọc thường hiệu quả là bắt đầu bằng -c -p, sau đó thêm -v khi cần constant pool, descriptor, flags hoặc metadata sâu hơn.

## 4. Ví dụ thực hành: xem bytecode của một class

Tạo file **Calculator.java**:

~~~java
package demo;

public class Calculator {
    public static int add(int left, int right) {
        return left + right;
    }

    public static int absolute(int value) {
        if (value < 0) {
            return -value;
        }
        return value;
    }

    public static void main(String[] args) {
        int result = add(2, 3);
        System.out.println(result);
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -g -d out Calculator.java
~~~

Tùy chọn -g yêu cầu javac lưu thông tin debug như line number và local variable table. Tùy chọn -d out đặt class file vào thư mục output.

Xem cấu trúc class và bytecode:

~~~bash
javap -classpath out -c -p demo.Calculator
~~~

Trong output, phần method add có thể có dạng:

~~~text
public static int add(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
~~~

Giải thích:

- iload_0: đẩy giá trị int trong local variable slot 0 lên operand stack.
- iload_1: đẩy int trong slot 1 lên stack.
- iadd: lấy hai int trên stack, cộng chúng và đẩy kết quả trở lại stack.
- ireturn: trả về giá trị int ở đỉnh stack từ method.

Vì add là static, hai tham số nằm ở slot 0 và slot 1. Với instance method, slot 0 thường chứa this, nên tham số đầu tiên bắt đầu từ slot 1. Kiểu long và double chiếm hai local variable slots theo mô hình JVM.

Phần absolute có thể có các lệnh:

~~~text
iload_0
ifge
iload_0
ineg
ireturn
iload_0
ireturn
~~~

Compiler có thể dùng nhánh có offset cụ thể để chuyển đến đoạn trả về giá trị không âm. ifge kiểm tra giá trị int trên stack: nếu lớn hơn hoặc bằng 0 thì nhảy đến nhánh tương ứng; ineg đổi dấu số nguyên. Offset và cách sắp xếp lệnh phụ thuộc bytecode thực tế mà compiler sinh ra.

Chạy chương trình:

~~~bash
java -cp out demo.Calculator
~~~

Stdout:

~~~text
5
~~~

Đây là một chương trình nhỏ có thể biên dịch và chạy độc lập. Bytecode minh họa nên được đối chiếu với output từ JDK đang sử dụng vì compiler có thể thay đổi cách sắp xếp lệnh giữa các phiên bản hoặc tùy chọn build.

## 5. Cách đọc một dòng bytecode

Một dòng disassembly thường có dạng:

~~~text
12: invokevirtual #18 // Method java/io/PrintStream.println:(I)V
~~~

Các phần:

- 12 là bytecode offset trong method, tính theo byte từ đầu code array.
- invokevirtual là opcode gọi instance method theo cơ chế virtual dispatch.
- #18 là chỉ số tham chiếu tới entry trong constant pool.
- Phần comment giúp con người hiểu entry đang tham chiếu tới method nào và descriptor ra sao.

Offset không phải số thứ tự dòng. Một opcode có thể dài hơn một byte vì có operand đi kèm; vì vậy offset kế tiếp có thể tăng nhiều hơn 1.

Các nhóm opcode thường gặp:

| Nhóm | Ví dụ | Ý nghĩa |
|---|---|---|
| Nạp và lưu local variable | iload, aload, istore, astore | Chuyển giá trị giữa local variables và operand stack |
| Hằng số | iconst_0, bipush, ldc | Đẩy constant lên operand stack |
| Toán học | iadd, isub, imul, idiv, ineg | Thực hiện phép toán |
| So sánh và nhảy | if_icmpge, ifeq, ifnull, goto | Điều khiển luồng thực thi |
| Field | getfield, putfield, getstatic, putstatic | Đọc hoặc ghi field |
| Method invocation | invokestatic, invokevirtual, invokeinterface, invokespecial, invokedynamic | Gọi method hoặc call site |
| Object và array | new, anewarray, newarray, aaload, aastore | Tạo object/array và truy cập phần tử |
| Trả về | ireturn, areturn, return | Kết thúc method và trả kết quả |
| Exception | athrow | Ném throwable |

Tiền tố opcode thường gợi ý loại dữ liệu:

- i: int.
- l: long.
- f: float.
- d: double.
- a: reference tới object hoặc array.

Đây là quy ước hữu ích để đọc bytecode. Một số lệnh có dạng riêng cho constant nhỏ hoặc local slot cố định, ví dụ iconst_0, iload_1, aload_0.

## 6. Operand stack và local variables

Mỗi lần JVM thực thi method, frame của method có vùng local variables và operand stack riêng.

**Local variables** chứa tham số method và biến cục bộ. Các lệnh như iload, aload, istore và astore đọc/ghi các slot này.

**Operand stack** là nơi bytecode lấy toán hạng và đặt kết quả trung gian. Ví dụ phép cộng int:

~~~text
iload_0
iload_1
iadd
istore_2
~~~

Trình tự:

1. iload_0 đẩy a lên stack.
2. iload_1 đẩy b lên stack.
3. iadd lấy hai giá trị int, cộng chúng và đẩy kết quả.
4. istore_2 lấy kết quả khỏi stack và lưu vào slot 2.

Stack là nền tảng của bytecode JVM. Khi đọc một chuỗi opcode, hãy theo dõi giá trị được đẩy lên và lấy khỏi stack để hiểu mỗi lệnh đang làm gì.

Trong output javap -v, thuộc tính Code có thể chứa stack=... và locals=.... stack là độ sâu tối đa của operand stack trong method; locals là số local variable slots được cấp phát. Các giá trị này được compiler ghi vào class file và JVM dùng khi thực thi/kiểm tra bytecode.

## 7. Đọc descriptor của method và field

Trong class file, method và field dùng descriptor để mô tả kiểu dữ liệu. Descriptor là dạng biểu diễn nội bộ của JVM, khác với cách viết kiểu trong Java source.

Các ký hiệu cơ bản:

| Ký hiệu | Kiểu Java |
|---|---|
| B | byte |
| C | char |
| D | double |
| F | float |
| I | int |
| J | long |
| S | short |
| Z | boolean |
| V | void, chỉ dùng làm kiểu trả về |
| L...; | reference tới class/interface |
| [...] | array của kiểu theo sau |

Method descriptor có dạng:

~~~text
(parameter-types)return-type
~~~

Ví dụ:

| Descriptor | Diễn giải |
|---|---|
| (II)I | Nhận hai int, trả về int |
| (Ljava/lang/String;)V | Nhận một String, trả về void |
| ([Ljava/lang/String;)V | Nhận một String array, trả về void |
| ()Z | Không nhận tham số, trả về boolean |
| (J[D)Ljava/lang/String; | Nhận long và double array, trả về String |

Với class demo.Calculator, descriptor của method add(int, int) là (II)I. Có thể xem nhanh bằng:

~~~bash
javap -s -p -classpath out demo.Calculator
~~~

Lưu ý: descriptor mô tả kiểu sau khi compiler áp dụng quy tắc ngôn ngữ và type erasure. Generic type argument thường không xuất hiện trong descriptor của method; thông tin generic có thể được lưu riêng trong attribute Signature.

## 8. Đọc constant pool và output verbose

Constant pool là bảng các hằng số và tham chiếu mà class file sử dụng. Nó có thể chứa:

- Tên class và tên package.
- Tên field và method.
- Method descriptor và field descriptor.
- String literal và numeric constants.
- Method handle, method type và dynamic call site.
- Các tham chiếu dùng bởi bytecode instructions.

Xem thông tin chi tiết:

~~~bash
javap -v -p -classpath out demo.Calculator
~~~

Trong output, phần đầu thường có các entry dạng:

~~~text
Constant pool:
   #1 = Methodref          #2.#3
   #2 = Class              #4
   #3 = NameAndType        #5:#6
   #4 = Utf8               java/lang/Object
~~~

Chỉ số #1, #2... là constant pool index. Một instruction có thể tham chiếu tới entry qua chỉ số này. Khi đọc javap -c, comment sau opcode thường đã giải thích entry; nếu cần biết chi tiết hơn, tìm index tương ứng trong phần Constant pool của output -v.

Chỉ số constant pool không phải định danh ổn định giữa các lần build. Thêm một method, thay đổi source hoặc dùng compiler khác có thể làm thứ tự entry thay đổi. Khi so sánh bytecode, hãy đối chiếu nội dung tham chiếu thay vì chỉ so sánh số #.

## 9. Xem thông tin debug bằng -l

Khi biên dịch với debug information, javac có thể lưu:

- **LineNumberTable**: ánh xạ bytecode offset với dòng source.
- **LocalVariableTable**: tên biến cục bộ, descriptor và phạm vi sống của biến.
- **LocalVariableTypeTable**: thông tin generic type cho biến, nếu có.

Ví dụ:

~~~bash
javac -g -d out Calculator.java
javap -c -l -p -classpath out demo.Calculator
~~~

Phần line number có thể có dạng:

~~~text
LineNumberTable:
  line 5: 0
  line 6: 4
~~~

Các con số minh họa ánh xạ offset trong method tới dòng source. Bảng thực tế phụ thuộc source và compiler.

Nếu class file được biên dịch bằng -g:none, các bảng debug có thể không tồn tại. Khi đó javap -l không thể tự suy ra tên biến cục bộ hoặc dòng source đã bị loại bỏ. Việc thiếu LocalVariableTable không có nghĩa bytecode không có local variable slots; chỉ là tên và phạm vi debug không được lưu.

## 10. Kiểm tra các cấu trúc Java thường gặp

### Vòng lặp và điều kiện

if, for, while và switch thường được biểu diễn bằng lệnh so sánh và nhảy. Hãy tìm các opcode như:

~~~text
ifeq
ifne
if_icmplt
if_icmpge
goto
tableswitch
lookupswitch
~~~

Compiler có thể đổi thứ tự nhánh hoặc tối ưu biểu thức. Vì thế, không nên giả định mỗi câu lệnh Java tương ứng đúng một opcode.

### Gọi method

Các lệnh invocation phổ biến:

- invokestatic: gọi static method.
- invokevirtual: gọi instance method theo virtual dispatch.
- invokeinterface: gọi method qua interface.
- invokespecial: dùng cho constructor, private method hoặc một số lời gọi đặc biệt theo quy tắc JVM.
- invokedynamic: gọi qua dynamic call site, thường được dùng cho lambda và một số cơ chế ngôn ngữ/runtime.

### Lambda và string concatenation

Lambda thường được biểu diễn qua invokedynamic cùng các thông tin bootstrap method. Với JDK hiện đại, nối chuỗi bằng toán tử + cũng có thể dùng invokedynamic và StringConcatFactory, thay vì luôn tạo chuỗi StringBuilder như một số compiler đời cũ.

Để xem chi tiết, dùng:

~~~bash
javap -v -c -p -classpath out demo.Calculator
~~~

Tìm các phần InvokeDynamic, BootstrapMethods và các method handle liên quan.

### Exception handling

Các cấu trúc try, catch, finally được biểu diễn qua bytecode và exception table trong Code attribute. Khi xem javap -v, tìm phần:

~~~text
Exception table:
  from    to  target type
~~~

Các cột cho biết vùng bytecode được bảo vệ, vị trí handler và loại exception được bắt. finally có thể được compiler triển khai bằng nhiều đoạn code hoặc cơ chế exception handler; không nên kỳ vọng chỉ có một khối bytecode riêng mang tên finally.

### Constructor và static initializer

- Constructor Java được lưu dưới tên đặc biệt <init>.
- Static initializer được lưu trong method đặc biệt <clinit>.
- Constructor mặc định do compiler tạo vẫn là một method trong class file.
- Lệnh gọi constructor của superclass thường xuất hiện dưới dạng invokespecial.

Tìm các method này bằng:

~~~bash
javap -c -p -classpath out demo.Calculator
~~~

## 11. Đọc class trong JAR, dependency và module

### Class nằm trong JAR

Dùng -classpath để chỉ định JAR:

~~~bash
javap -classpath library.jar -c -p com.example.Library
~~~

Nếu class phụ thuộc vào nhiều JAR, nối chúng bằng path separator của hệ điều hành. Dấu phân cách thường là : trên Linux/macOS và ; trên Windows.

Ví dụ PowerShell:

~~~powershell
javap -classpath "app.jar;lib/dependency.jar" -c -p com.example.Main
~~~

Linux/macOS:

~~~bash
javap -classpath "app.jar:lib/dependency.jar" -c -p com.example.Main
~~~

### Class trong module của JDK

Có thể xem class thuộc module bằng --module:

~~~bash
javap --module java.base java.lang.String
~~~

Hoặc kết hợp với -c và -p để xem method và bytecode có thể truy cập qua class file:

~~~bash
javap --module java.base -c -p java.util.ArrayList
~~~

### Multi-release JAR

Một multi-release JAR có thể chứa implementation khác nhau theo Java release. Dùng --multi-release N để chọn phiên bản entry cần phân tích:

~~~bash
javap --multi-release 17 -classpath library.jar -c -p com.example.Feature
~~~

Giá trị N chỉ định phiên bản release cần chọn khi tra cứu trong multi-release JAR. Khi kết quả khác giữa các release, hãy kiểm tra cả manifest Multi-Release: true và các entry dưới META-INF/versions/.

## 12. Kiểm tra class file version bằng javap

javap có thể hiển thị major/minor version trong chế độ verbose:

~~~bash
javap -verbose -classpath out demo.Calculator
~~~

Tìm các dòng:

~~~text
minor version: 0
major version: 61
~~~

Major version 61 tương ứng Java 17. Nếu gặp UnsupportedClassVersionError, hãy dùng javap để kiểm tra class gây lỗi, kể cả khi class nằm trong dependency JAR.

Một quy trình kiểm tra:

1. Đọc java -version để biết runtime đang chạy.
2. Xác định đúng class file mà JVM báo lỗi.
3. Dùng javap -verbose để đọc major/minor version.
4. Đối chiếu với phiên bản tối đa mà runtime hỗ trợ.
5. Kiểm tra dependency và cấu hình --release của build.

javap chỉ đọc file class. Nó không chứng minh rằng mọi class khác trong ứng dụng đều tương thích; cần kiểm tra dependency và các class được nạp động khi cần.

## 13. So sánh bytecode giữa hai lần build

javap hữu ích khi muốn hiểu vì sao thay đổi source hoặc compiler option làm thay đổi bytecode.

Ví dụ:

~~~bash
javap -c -p -classpath build-old com.example.Service > old.txt
javap -c -p -classpath build-new com.example.Service > new.txt
~~~

Sau đó so sánh hai file bằng công cụ diff:

~~~bash
diff -u old.txt new.txt
~~~

Trên PowerShell có thể dùng:

~~~powershell
Compare-Object (Get-Content old.txt) (Get-Content new.txt)
~~~

Khi so sánh, lưu ý:

- Constant pool index có thể đổi dù logic bytecode không đổi.
- Tên file, line number, local variable và debug attributes có thể khác.
- JDK khác nhau có thể chọn opcode hoặc cách tối ưu khác.
- Source thay đổi nhỏ có thể làm offset và nhánh trong method thay đổi.
- Hai đoạn bytecode khác nhau vẫn có thể có cùng ngữ nghĩa.

Để so sánh hành vi, kết hợp bytecode inspection với test và phân tích logic. Không nên coi diff văn bản của javap -v là bằng chứng duy nhất về regression.

## 14. Các lỗi thường gặp khi dùng javap

| Vấn đề | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Error: class not found | Sai tên class hoặc classpath | Kiểm tra package, thư mục output và -classpath |
| javap đọc nhầm class | Có nhiều phiên bản class cùng tên trên classpath | Chỉ định classpath cụ thể hoặc truyền đường dẫn file .class |
| Không thấy private method | Chế độ mặc định chỉ hiển thị member theo phạm vi mặc định | Thêm -p |
| Không thấy bytecode | Chưa dùng tùy chọn disassemble | Thêm -c |
| Không thấy tên biến/dòng source | Class không lưu debug metadata | Biên dịch lại với -g nếu có source |
| Output quá dài | Dùng -v cho class lớn | Bắt đầu bằng -c -p, thêm -v khi cần |
| Không hiểu #12 | Đây là constant pool index | Dùng -v để tra entry tương ứng |
| Không đọc được class mới | JDK javap quá cũ so với class file | Dùng javap từ JDK hỗ trợ phiên bản class đó |
| Kết quả khác giữa các JDK | Compiler thay đổi cách sinh bytecode | So sánh source, flags và JDK version cùng lúc |

## 15. Quy trình đọc bytecode có hệ thống

Khi phân tích một class chưa quen thuộc, có thể làm theo thứ tự:

1. **Xác định class**: tìm đúng file .class, JAR hoặc module; kiểm tra package và classpath.
2. **Xem cấu trúc**: chạy javap -p để biết fields, constructors và methods.
3. **Xem instructions**: chạy javap -c -p và chọn method cần phân tích.
4. **Theo dõi stack**: với mỗi opcode, xác định giá trị được push/pop và local slot được truy cập.
5. **Giải descriptor**: dùng -s hoặc -v để hiểu tham số, kiểu trả về và field type.
6. **Tra constant pool**: dùng -v khi cần hiểu method reference, field reference, string hoặc bootstrap method.
7. **Xem debug metadata**: thêm -l nếu cần liên hệ offset với source line.
8. **Kiểm tra runtime compatibility**: xem major/minor version và đối chiếu với JVM mục tiêu.
9. **So sánh và kiểm chứng**: dùng diff, test và runtime behavior để xác nhận kết luận.

Không cần bắt đầu bằng output verbose cho mọi class. Hãy thu hẹp vào một method và một câu hỏi cụ thể, ví dụ “method này gọi virtual hay static?”, “giá trị được lưu ở slot nào?” hoặc “class này được biên dịch cho Java release nào?”.

## 16. Ghi nhớ

- javap là công cụ disassembler để đọc class file; nó không khôi phục đầy đủ source code gốc.
- -c hiển thị bytecode; -p hiện cả private member; -v hiện constant pool và metadata; -l hiện debug tables; -s hiện descriptor.
- Bytecode JVM là tập lệnh trung gian, dùng operand stack và local variables trong mỗi method frame.
- Offset trong output là vị trí byte trong code array, không phải số dòng source.
- Descriptor như (II)I mô tả hai tham số int và giá trị trả về int.
- Constant pool index chỉ là tham chiếu trong một class file; không phải định danh ổn định giữa các lần build.
- invokedynamic, BootstrapMethods, exception table và stack map frames giúp hiểu sâu hơn về lambda, string concat và control flow.
- Có thể dùng javap để kiểm tra class trong thư mục, JAR và module của JDK.
- Khi so sánh bytecode, cần xét JDK version, compiler flags và debug metadata; khác biệt văn bản chưa chắc là khác biệt hành vi.

## Tài liệu tham khảo chính thức

- [javap Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html)
- [Java Virtual Machine Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html)
- [Java Virtual Machine Specification — Instruction Set](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-6.html)
- [Java Language Specification — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se26/html/jls-13.html)