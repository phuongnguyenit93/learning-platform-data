# Xem bytecode Java bằng javap

Sau khi biên dịch, mã nguồn Java được chuyển thành các tệp class chứa bytecode và metadata theo định dạng class file. Khi cần hiểu compiler đã tạo ra gì, kiểm tra chữ ký phương thức, xem lệnh bytecode hoặc điều tra một thư viện không có source code, công cụ `javap` là lựa chọn trực tiếp của JDK.

`javap` là class-file disassembler: nó đọc một hoặc nhiều class file và in thông tin ra standard output. Công cụ giúp quan sát biểu diễn đã biên dịch; nó không chạy chương trình và cũng không khôi phục nguyên vẹn mã nguồn ban đầu.

## 1. Bytecode là gì?

Bytecode Java là tập lệnh trung gian được lưu trong class file. JVM đọc và thực thi các lệnh này; tùy JVM và quá trình chạy, mã nóng có thể được biên dịch tiếp thành mã máy bởi JIT compiler.

Một quy trình khái quát:

~~~text
Source code (.java)
       |
       v
     javac
       |
       v
Class file (.class)
       |
       v
JVM nạp, kiểm tra và liên kết
       |
       v
Thực thi bytecode / JIT compile
~~~

Bytecode được thiết kế để JVM có thể thực thi độc lập với kiến trúc CPU cụ thể. Một class file không chỉ có danh sách lệnh; nó còn chứa thông tin phiên bản, constant pool, khai báo lớp, trường, phương thức và các attributes.

Ví dụ, phép cộng hai số nguyên có thể được biểu diễn bằng các lệnh nạp biến cục bộ, cộng trên operand stack và trả về kết quả. `javap -c` cho phép xem các lệnh này ở dạng dễ đọc.

## 2. javap dùng để làm gì?

Các tình huống phổ biến:

- Kiểm tra public API của một class hoặc thư viện JAR.
- Xem bytecode mà `javac` sinh ra từ một đoạn mã nguồn.
- Kiểm tra phương thức private, field, constructor và modifier.
- Đọc JVM descriptor để hiểu kiểu tham số và kiểu trả về ở mức class file.
- Xem constant pool, class-file version và attributes.
- Kiểm tra line number/local variable metadata phục vụ debug.
- So sánh class file giữa các lần build hoặc giữa các phiên bản thư viện.
- Kiểm tra class thuộc một module hoặc một phiên bản trong multi-release JAR.

`javap` ghi kết quả ra standard output. Bạn có thể xem trực tiếp trong terminal hoặc chuyển hướng ra tệp để so sánh.

## 3. Cú pháp cơ bản

Cú pháp tổng quát:

~~~text
javap [options] classes...
~~~

Có thể chỉ định lớp bằng tên đầy đủ, đường dẫn tới tệp class hoặc URL của class file.

Ví dụ:

~~~bash
# Xem một lớp trong JDK
javap java.lang.String

# Xem class file theo đường dẫn
javap out/com/example/Calculator.class

# Xem lớp theo tên đầy đủ qua class path
javap -cp out com.example.Calculator
~~~

Nếu class nằm trong package, dùng tên đầy đủ như `com.example.Calculator` hoặc chỉ định class file tương ứng. Khi dùng tên lớp, `javap` phải tìm được lớp qua class path/module path phù hợp.

Kiểm tra phiên bản công cụ và trợ giúp:

~~~bash
javap -version
javap --help
~~~

## 4. Ví dụ biên dịch một lớp để quan sát

Tạo tệp `src/com/example/Calculator.java`:

~~~java
package com.example;

public class Calculator {
    public int add(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) {
        System.out.println("sum=" + new Calculator().add(3, 4));
    }
}
~~~

Biên dịch với thông tin debug:

~~~bash
javac -g -d out src/com/example/Calculator.java
~~~

Chạy ứng dụng:

~~~bash
java -cp out com.example.Calculator
~~~

Kết quả:

~~~text
sum=7
~~~

Lúc này thư mục output có class file:

~~~text
out/
└── com/
    └── example/
        └── Calculator.class
~~~

Chúng ta sẽ dùng chính class file này cho các lệnh tiếp theo. Nếu biên dịch lại với mã nguồn hoặc tùy chọn khác, nội dung class file có thể thay đổi.

## 5. Xem khai báo lớp và thành viên

Chạy:

~~~bash
javap -cp out com.example.Calculator
~~~

Đầu ra có dạng:

~~~text
Compiled from "Calculator.java"
public class com.example.Calculator {
  public com.example.Calculator();
  public int add(int, int);
  public static void main(java.lang.String[]);
}
~~~

Đầu ra cho thấy lớp có constructor, phương thức `add` và phương thức `main`. Đây là góc nhìn về khai báo và chữ ký, chưa phải danh sách bytecode instructions.

Mặc định, `javap` hiển thị các thành viên public và protected. Các lựa chọn lọc thành viên:

| Tùy chọn | Nội dung |
|---|---|
| `-public` | Chỉ lớp/thành viên public |
| `-protected` | Public và protected |
| `-package` | Package-private, protected và public |
| `-private` hoặc `-p` | Tất cả thành viên, gồm private |

Để kiểm tra cả field và method private:

~~~bash
javap -cp out -p com.example.Calculator
~~~

Điều này hữu ích khi xem thư viện bên thứ ba, nhưng hãy nhớ rằng tên thành viên private và cấu trúc nội bộ không phải hợp đồng API công khai mà ứng dụng khác nên phụ thuộc.

## 6. Disassemble bytecode với -c

Tùy chọn `-c` in các lệnh bytecode của từng phương thức:

~~~bash
javap -cp out -c com.example.Calculator
~~~

Trong phần phương thức `add`, đoạn bytecode điển hình:

~~~text
public int add(int, int);
  Code:
     0: iload_1
     1: iload_2
     2: iadd
     3: ireturn
~~~

Đọc từng lệnh:

1. `iload_1` đẩy biến cục bộ thứ nhất (tham số `left`) lên operand stack.
2. `iload_2` đẩy biến cục bộ thứ hai (tham số `right`) lên operand stack.
3. `iadd` lấy hai giá trị int trên stack, cộng chúng và đẩy kết quả trở lại stack.
4. `ireturn` lấy giá trị int kết quả và trả về cho bên gọi.

Trong instance method, slot biến cục bộ số 0 chứa `this`; hai tham số `left` và `right` vì vậy nằm ở slot 1 và 2. Offset ở đầu mỗi dòng là vị trí bytecode trong method code, không phải số dòng trong source file.

Đây là cách đọc hữu ích khi tìm hiểu cách biểu thức Java được compiler chuyển thành thao tác trên local-variable array và operand stack.

## 7. Kết hợp các tùy chọn quan trọng

Các tùy chọn thường dùng có thể kết hợp để tạo góc nhìn phù hợp:

~~~bash
# Bytecode của mọi phương thức, kể cả private
javap -cp out -c -p com.example.Calculator

# Thêm JVM descriptor của thành viên
javap -cp out -s com.example.Calculator

# Thêm metadata và constant pool
javap -cp out -v com.example.Calculator

# Xem line number và local variable tables
javap -cp out -l com.example.Calculator

# Xem các hằng static final
javap -cp out -constants com.example.Calculator

# Xem hash và thông tin tệp class được tìm thấy
javap -cp out -sysinfo com.example.Calculator
~~~

| Tùy chọn | Ý nghĩa |
|---|---|
| `-c` | Disassemble bytecode instructions của các method |
| `-v` hoặc `-verbose` | In thông tin chi tiết của class |
| `-p` hoặc `-private` | Hiển thị mọi thành viên |
| `-s` | In internal type signatures (JVM descriptors) |
| `-l` | In line number và local variable tables |
| `-constants` | Hiển thị giá trị constant của static final fields |
| `-sysinfo` | Hiển thị đường dẫn, kích thước, thời gian và SHA-256 của class file |
| `-version` | Hiển thị phiên bản javap |
| `-Joption` | Truyền tùy chọn cho JVM chạy chính công cụ javap |

Có thể kết hợp `-c`, `-p` và `-v` khi cần xem cả phương thức private, instructions và cấu trúc class file:

~~~bash
javap -cp out -c -p -v com.example.Calculator
~~~

Đầu ra verbose khá dài. Khi điều tra một câu hỏi cụ thể, hãy bắt đầu bằng góc nhìn nhỏ rồi bổ sung tùy chọn khi cần.

## 8. Đọc constant pool và class-file metadata

Class file có một constant pool lưu các hằng và symbolic reference mà class sử dụng. Ví dụ: tên class, tên method, field reference, string literal, numeric constant, method handle và các kiểu dữ liệu liên quan.

Xem bằng:

~~~bash
javap -cp out -v com.example.Calculator
~~~

Một phần đầu ra verbose thường có dạng:

~~~text
Classfile /.../out/com/example/Calculator.class
  Last modified ...; size ... bytes
  SHA-256 checksum ...
  Compiled from "Calculator.java"
public class com.example.Calculator
  minor version: ...
  major version: ...
  flags: ...
Constant pool:
   #1 = Methodref ...
   #2 = Class ...
   ...
~~~

Các thông tin quan trọng:

- **Classfile:** tệp class đang được đọc.
- **minor/major version:** phiên bản định dạng class file.
- **flags:** modifier ở cấp class, field hoặc method, ví dụ public, final, abstract, static.
- **Constant pool:** các hằng và symbolic reference được đánh chỉ số.
- **Fields/Methods:** khai báo field, constructor và method.
- **Attributes:** metadata bổ sung cho class, field hoặc method.

Các chỉ số như `#1`, `#2` trong constant pool là vị trí tham chiếu nội bộ. Chúng có thể thay đổi giữa các lần biên dịch; không nên viết công cụ dựa trên một chỉ số cụ thể nếu không phân tích class file đúng chuẩn.

### 8.1. Class-file version

Có thể dùng `-v` để đọc major version. Một số mốc phổ biến:

| Java release | Major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Ví dụ, class file có major version 65 được tạo theo định dạng Java 21. Điều này cho biết phiên bản bytecode, không chứng minh rằng toàn bộ dependency hoặc môi trường chạy đều tương thích.

Nếu muốn kiểm soát phiên bản đích, hãy dùng `javac --release N` khi biên dịch, sau đó dùng `javap -verbose` để kiểm tra class-file version đã sinh ra.

## 9. Đọc JVM descriptor với -s

JVM descriptor biểu diễn kiểu tham số và kiểu trả về theo cú pháp nội bộ của class file. Tùy chọn `-s` giúp in descriptor bên cạnh khai báo method/field:

~~~bash
javap -cp out -s com.example.Calculator
~~~

Một số quy tắc:

| Ký hiệu | Kiểu |
|---|---|
| `B` | byte |
| `C` | char |
| `D` | double |
| `F` | float |
| `I` | int |
| `J` | long |
| `S` | short |
| `Z` | boolean |
| `V` | void |
| `Lpkg/Type;` | Tham chiếu tới kiểu |
| `[T` | Mảng của kiểu T |

Ví dụ:

- `(II)I`: method nhận hai tham số int và trả về int.
- `([Ljava/lang/String;)V`: method nhận một mảng `java.lang.String` và trả về void.
- `()Ljava/lang/String;`: method không nhận tham số và trả về `java.lang.String`.

Descriptor hữu ích khi phân tích lỗi liên kết, API generic đã bị type erasure hoặc so sánh chữ ký giữa hai phiên bản thư viện. Generic type argument thường không nằm trong descriptor method thông thường; thông tin generic có thể xuất hiện ở Signature attribute.

## 10. Đọc attributes và debug metadata

Class file có nhiều attribute cung cấp thông tin cho JVM, compiler, debugger hoặc công cụ khác. `javap -v` giúp xem chúng; `javap -l` tập trung vào line number/local variable tables.

Một số attribute thường gặp:

- **SourceFile:** tên tệp source được compiler ghi lại.
- **LineNumberTable:** ánh xạ offset bytecode tới số dòng source.
- **LocalVariableTable:** tên và kiểu biến cục bộ cùng phạm vi hiệu lực, nếu thông tin này được sinh.
- **Code:** bytecode của method, giới hạn stack/local và các exception handler.
- **StackMapTable:** thông tin frame phục vụ bytecode verification.
- **Exceptions:** danh sách checked exception được khai báo trên method.
- **Signature:** thông tin generic signature.
- **InnerClasses / EnclosingMethod:** metadata về lớp lồng nhau và phương thức bao ngoài.
- **BootstrapMethods:** dữ liệu bootstrap cho các lệnh như `invokedynamic`.

Để tăng thông tin debug khi biên dịch:

~~~bash
javac -g -d out src/com/example/Calculator.java
~~~

`-g` yêu cầu compiler sinh thông tin debug. `javap -l` chỉ có thể hiển thị những bảng thực sự tồn tại trong class file; nếu class không chứa local-variable metadata, tên biến local có thể không xuất hiện dù bytecode vẫn chạy bình thường.

## 11. Nhận diện một số bytecode instruction

Các opcode thường thấy:

| Nhóm | Ví dụ | Ý nghĩa |
|---|---|---|
| Load/store | `iload`, `aload`, `istore`, `astore` | Đọc/ghi biến cục bộ |
| Hằng số | `iconst_0`, `bipush`, `ldc` | Đưa hằng lên operand stack |
| Số học | `iadd`, `isub`, `imul`, `idiv` | Thực hiện phép toán số nguyên |
| Object | `new`, `getfield`, `putfield` | Tạo object, đọc/ghi field |
| Invocation | `invokevirtual`, `invokestatic`, `invokespecial`, `invokeinterface` | Gọi method |
| Dynamic invocation | `invokedynamic` | Gọi qua cơ chế dynamic call site |
| Branch | `ifeq`, `if_icmpge`, `goto` | Rẽ nhánh |
| Return | `ireturn`, `areturn`, `return` | Trả về từ method |

Một số quy tắc khi đọc:

- Opcode thường có tiền tố theo loại dữ liệu: `i` cho int, `l` cho long, `f` cho float, `d` cho double, `a` cho reference.
- Lệnh invocation thường tham chiếu tới constant pool entry chứa owner, tên method và descriptor.
- Nhánh điều khiển dùng offset bytecode để xác định vị trí đích.
- Một số lệnh có dạng ngắn như `iload_1` để nạp biến local ở slot cố định.
- Lệnh thao tác operand stack; khi đọc một method cần theo dõi giá trị được push/pop theo thứ tự.

Không cần ghi nhớ mọi opcode ngay từ đầu. Hãy dùng `javap -c` để tìm nhóm lệnh liên quan đến câu hỏi đang điều tra, rồi tra JVM Specification khi cần hiểu chính xác semantics.

## 12. Xem class trong JAR và module

### 12.1. Class trong JAR

Nếu class nằm trong thư viện JAR, dùng class path:

~~~bash
javap -cp lib/example.jar com.example.LibraryClass
javap -cp lib/example.jar -c com.example.LibraryClass
~~~

Có thể truyền nhiều class cùng lúc:

~~~bash
javap -cp lib/example.jar com.example.First com.example.Second
~~~

Khi class phụ thuộc vào các JAR khác, `javap` thường chỉ cần tìm đúng class đang kiểm tra; nếu output tham chiếu kiểu ngoài, class path phù hợp giúp công cụ phân giải các tên đó.

Trên macOS/Linux, dấu phân cách class path thường là dấu hai chấm; trên Windows là dấu chấm phẩy:

~~~bash
# macOS / Linux
javap -cp "lib/a.jar:lib/b.jar" com.example.LibraryClass
~~~

~~~powershell
# Windows PowerShell
javap -cp "lib/a.jar;lib/b.jar" com.example.LibraryClass
~~~

### 12.2. Class trong module

Dùng `--module` để chỉ định module chứa class, và `--module-path` để tìm application modules:

~~~bash
javap --module java.base java.lang.String
~~~

Với module ứng dụng:

~~~bash
javap --module-path mods --module com.example.app com.example.Main
~~~

Cần phân biệt module path với class path. Module chứa class được chọn bằng tùy chọn module; classpath thông thường không thay thế module path trong mọi trường hợp.

### 12.3. Multi-release JAR

Multi-release JAR có thể chứa nhiều phiên bản của cùng một class trong các thư mục `META-INF/versions/N`. Theo mặc định, dạng classpath của `javap` hiển thị entry nền (base entry), không tự chọn class version theo runtime mục tiêu.

Dùng `--multi-release` để chọn phiên bản cần kiểm tra:

~~~bash
javap --multi-release 17 -cp lib/multi-release.jar com.example.VersionedClass
~~~

Điều này hữu ích khi kiểm tra JAR có implementation khác nhau theo từng Java release. Hãy xác nhận JAR thật sự chứa entry cho release đã chọn.

## 13. Giới hạn của javap

`javap` là công cụ đọc class file; cần hiểu đúng những gì nó cho biết:

- Nó hiển thị bytecode và metadata, không tái tạo chính xác source code ban đầu.
- Tên biến, comment, format, cấu trúc biểu thức và cú pháp gốc có thể đã mất sau biên dịch.
- Output bytecode không phải assembly của CPU và không phản ánh mã máy mà JIT tạo ra tại runtime.
- Một class file không cho biết đầy đủ hành vi của toàn ứng dụng, bởi hành vi còn phụ thuộc class khác, configuration, input, environment và runtime.
- `javap` không thay thế công cụ phân tích dependency toàn dự án như `jdeps`.
- Class file có thể chứa debug metadata hoặc tên nội bộ; không xem đó là bảo đảm API.

Đặc biệt, Oracle ghi rõ `javap` không tự nhận biết phiên bản trong multi-release JAR khi dùng classpath thông thường. Hãy dùng `--multi-release` khi cần đọc entry theo release cụ thể.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `class not found` | Sai tên lớp hoặc classpath không trỏ tới thư mục/JAR chứa class | Kiểm tra package, output directory và `-cp` |
| Chỉ thấy public/protected members | Đang dùng chế độ mặc định | Thêm `-p` hoặc `-private` |
| Không thấy bytecode | Chỉ chạy `javap` không có `-c` | Thêm `-c` |
| Không thấy tên biến local | Class file không chứa LocalVariableTable | Biên dịch với `javac -g` rồi chạy lại `javap -l` |
| Không hiểu descriptor | Đang xem ký hiệu JVM nội bộ | Dùng `-s` và tra bảng descriptor |
| Output verbose quá dài | `-v` hiển thị nhiều metadata | Bắt đầu với `-c`, `-p` hoặc `-s` rồi mở rộng khi cần |
| Xem nhầm class trong multi-release JAR | Dùng classpath thông thường nên đọc entry base | Dùng `--multi-release N` |
| Bytecode khác kỳ vọng | Compiler/JDK hoặc tùy chọn build khác nhau | Kiểm tra `javac --version`, release target và cấu hình build |

## 15. Quy trình thực hành

Khi muốn kiểm tra một class cụ thể:

1. **Tìm đúng class file:** xác định package, thư mục output hoặc JAR đang được ứng dụng sử dụng.
2. **Xem chữ ký:** chạy `javap -cp out com.example.Calculator` để xem API và thành viên.
3. **Xem bytecode:** thêm `-c` để đọc instructions của method.
4. **Xem member private:** thêm `-p` nếu cần kiểm tra implementation nội bộ.
5. **Xem descriptor:** thêm `-s` để kiểm tra kiểu tham số và giá trị trả về ở mức JVM.
6. **Xem class metadata:** dùng `-v` để kiểm tra major version, constant pool, flags và attributes.
7. **Đối chiếu source/debug:** dùng `-l` khi cần line number hoặc local variable tables.
8. **Kiểm tra đúng phiên bản thư viện:** dùng class path, module path hoặc `--multi-release` phù hợp.

Ví dụ chuỗi lệnh:

~~~bash
javac -g -d out src/com/example/Calculator.java
javap -cp out com.example.Calculator
javap -cp out -c com.example.Calculator
javap -cp out -p -s -c com.example.Calculator
javap -cp out -v com.example.Calculator
~~~

## 16. Ghi nhớ

`javap` cho phép quan sát class file ở nhiều mức: khai báo thành viên, bytecode instructions, JVM descriptors, constant pool, version và attributes. `-c` là tùy chọn chính để xem bytecode; `-p` mở rộng phạm vi thành viên; `-s` hiển thị descriptor; `-v` cung cấp metadata chi tiết; `-l` xem thông tin debug.

Khi đọc bytecode, hãy xác định đúng class file, bắt đầu từ một method nhỏ, theo dõi operand stack và liên hệ từng lệnh với source code tương ứng. Dùng công cụ để trả lời một câu hỏi cụ thể, đồng thời nhớ rằng bytecode là biểu diễn trung gian của JVM chứ không phải source code hay mã máy sau JIT.

Tài liệu tham khảo: [The javap Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html); [The Java Virtual Machine Specification, Chapter 4 — The class File Format](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html); [The Java Virtual Machine Specification, Chapter 6 — The Java Virtual Machine Instruction Set](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html).