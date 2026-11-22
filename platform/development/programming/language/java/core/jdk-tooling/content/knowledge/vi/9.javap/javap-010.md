# Kiểm tra compiler output bằng `javap`

Sau khi `javac` biên dịch mã nguồn Java, kết quả quan trọng nhất thường là các tệp `.class` chứa bytecode và metadata theo định dạng Java class file. Khi cần biết compiler đã tạo ra gì, kiểm tra đúng tệp nào, phương thức được biểu diễn ra sao hoặc tùy chọn biên dịch đã tác động đến metadata như thế nào, bạn có thể dùng công cụ `javap` đi kèm JDK.

`javac` và `javap` có nhiệm vụ khác nhau:

- `javac` đọc mã nguồn, kiểm tra và tạo class file; tùy cấu hình, nó còn có thể sinh source file, native header và diagnostic.
- `javap` đọc class file hoặc lớp trong JAR/module rồi hiển thị khai báo, descriptor, bytecode và metadata.
- `java` khởi chạy ứng dụng; kết quả stdout/stderr của ứng dụng là đầu ra runtime, tách biệt với đầu ra của compiler.

`javap` không khôi phục nguyên văn mã nguồn ban đầu. Nó trình bày cấu trúc và bytecode mà compiler đã tạo, giúp bạn kiểm tra kết quả build một cách trực tiếp.

## 1. Những loại output có thể xuất hiện khi biên dịch

Một lần biên dịch có thể tạo ra nhiều loại output, tùy mã nguồn và tùy chọn `javac`:

| Output | Tùy chọn/cơ chế | Nội dung |
|---|---|---|
| Java class files | `-d directory` | Bytecode và metadata trong các tệp `.class` |
| Generated source files | Annotation processing và `-s directory` | Tệp `.java` do annotation processor sinh ra |
| Native header files | `-h directory` | Header C/C++ cho các phương thức native phù hợp |
| Compiler diagnostics | Mặc định; có thể kết hợp `-Xdiags` | Lỗi, warning và vị trí mã nguồn liên quan |
| Compiler activity log | `-verbose` | Thông tin compiler đang nạp, phân tích và ghi tệp |
| Processor diagnostics/log | Annotation processor và các tùy chọn `-Xprint...` | Round, processor được gọi và thông báo do processor phát ra |

Một số điểm cần phân biệt:

- `javac` không tự đóng gói các class file thành JAR. Dùng công cụ `jar` cho bước đóng gói.
- Tài nguyên như file cấu hình, ảnh hoặc file dữ liệu không tự động được copy vào thư mục class output chỉ vì chúng nằm cạnh mã nguồn.
- Nếu biên dịch thất bại, có thể một số tệp đầu ra đã được tạo trước khi lỗi xảy ra. Không nên xem thư mục output sau một lần build thất bại là một bản build hoàn chỉnh.
- `javap` kiểm tra class file đã được tạo; nó không thay thế việc đọc diagnostic của `javac`.

## 2. Tạo output vào thư mục riêng bằng `-d`

Với một dự án Java có package, nên tách mã nguồn và class file đầu ra. Ví dụ:

~~~text
project/
  src/
    demo/
      Report.java
  out/
~~~

Từ thư mục `project`, tạo thư mục `out` nếu chưa có rồi biên dịch:

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out src/demo/Report.java
~~~

macOS/Linux:

~~~sh
mkdir -p out
javac -d out src/demo/Report.java
~~~

Tùy chọn `-d out` chỉ định thư mục gốc để lưu class file. Compiler tạo cấu trúc package bên dưới thư mục đó, vì vậy lớp `demo.Report` được ghi thành:

~~~text
out/
  demo/
    Report.class
~~~

Khi chạy hoặc kiểm tra lớp, hãy dùng thư mục gốc `out` làm classpath:

~~~text
java -cp out demo.Report
javap -classpath out demo.Report
~~~

Không đưa đuôi `.class` vào tên lớp khi dùng dạng tên lớp đầy đủ. Với package `demo`, tên lớp là `demo.Report`.

Nếu bỏ `-d`, `javac` thường ghi class file cạnh tệp nguồn tương ứng. Cách này dễ làm lẫn source và build output, đặc biệt khi dự án có nhiều package hoặc biên dịch nhiều lần.

## 3. Kiểm tra output tổng quan bằng `javap`

`javap` có thể hiển thị khai báo lớp và các thành viên ở dạng gần với chữ ký Java:

~~~text
javap -classpath out demo.Report
~~~

Lệnh này hữu ích để kiểm tra:

- Lớp có tên đầy đủ và superclass nào.
- Lớp triển khai interface nào.
- Những constructor và phương thức public/package-visible được hiển thị mặc định.
- Kiểu tham số và kiểu trả về của các phương thức.

Mặc định, `javap` không hiển thị mọi thành viên private. Dùng `-p` hoặc `-private` để xem cả thành viên private:

~~~text
javap -classpath out -p demo.Report
~~~

`javap` hiển thị khai báo suy ra từ class file. Kiểu generic có thể xuất hiện nếu class file lưu `Signature`; tên tham số có thể phụ thuộc `MethodParameters`; các chi tiết này không phải lúc nào cũng có sẵn nếu compiler không sinh metadata tương ứng.

## 4. Các tùy chọn `javap` quan trọng

| Tùy chọn | Công dụng |
|---|---|
| `-c` | Disassemble và hiển thị bytecode của các phương thức |
| `-p` hoặc `-private` | Hiển thị cả thành viên private |
| `-s` | Hiển thị JVM descriptor của trường và phương thức |
| `-l` | Hiển thị line number table và local variable table nếu có |
| `-v` hoặc `-verbose` | Hiển thị thông tin class file chi tiết, constant pool và attributes |
| `-constants` | Hiển thị giá trị của các trường hằng số phù hợp |
| `-classpath path` hoặc `--class-path path` | Chỉ định nơi tìm class file/JAR |
| `--module-path path` | Chỉ định nơi tìm module |
| `--module module` | Chỉ định module chứa lớp cần xem |
| `--multi-release version` | Chọn phiên bản lớp trong multi-release JAR |

Có thể kết hợp nhiều tùy chọn. Ví dụ:

~~~text
javap -classpath out -c -p demo.Report
javap -classpath out -v -p demo.Report
javap -classpath out -s -p demo.Report
javap -classpath out -l -p demo.Report
javap -classpath out -constants -p demo.Report
~~~

Khi cần điều tra một class file, thường bắt đầu với `-p` để thấy đủ thành viên, sau đó dùng `-c` hoặc `-v` để đi sâu vào bytecode và metadata.

## 5. Đọc bytecode bằng `javap -c`

`-c` hiển thị instruction bytecode của từng phương thức:

~~~text
javap -classpath out -c -p demo.Report
~~~

Ví dụ, phương thức:

~~~java
public int add(int left, int right) {
    return left + right;
}
~~~

có thể được biểu diễn bằng các instruction tương tự:

~~~text
0: iload_1
1: iload_2
2: iadd
3: ireturn
~~~

Ý nghĩa:

- `iload_1`: đưa giá trị `int` từ local variable slot 1 lên operand stack.
- `iload_2`: đưa giá trị `int` từ slot 2 lên operand stack.
- `iadd`: lấy hai giá trị `int` trên operand stack, cộng chúng và đẩy kết quả trở lại stack.
- `ireturn`: trả về kết quả kiểu `int`.

Các offset là vị trí bytecode trong method, không phải số dòng source. Instruction cụ thể có thể khác tùy cách viết mã, phiên bản compiler, tối ưu hóa và ngữ cảnh phương thức.

Một số instruction thường gặp:

| Instruction | Ý nghĩa khái quát |
|---|---|
| `aload`, `iload`, `lload`, `dload` | Nạp reference hoặc giá trị primitive từ local variable |
| `astore`, `istore`, `lstore`, `dstore` | Ghi giá trị vào local variable |
| `getfield`, `putfield` | Đọc/ghi instance field |
| `getstatic`, `putstatic` | Đọc/ghi static field |
| `invokevirtual` | Gọi instance method theo cơ chế virtual dispatch |
| `invokestatic` | Gọi static method |
| `invokespecial` | Gọi constructor hoặc một số phương thức đặc biệt |
| `invokeinterface` | Gọi phương thức qua interface |
| `invokedynamic` | Gọi call site được liên kết qua bootstrap method |
| `new` | Tạo đối tượng mới |
| `checkcast`, `instanceof` | Kiểm tra hoặc chuyển kiểu reference |
| `ireturn`, `areturn`, `return` | Trả về giá trị hoặc kết thúc phương thức void |

Bytecode giúp kiểm tra compiler đã chuyển cấu trúc Java thành các thao tác JVM như thế nào. Tuy nhiên, không nên dùng bytecode listing như bằng chứng duy nhất về hiệu năng runtime: JIT có thể biên dịch và tối ưu hóa mã khi chương trình chạy.

## 6. Đọc descriptor bằng `javap -s`

JVM descriptor mô tả kiểu trường và kiểu tham số/kiểu trả về ở mức class file. Tùy chọn `-s` in descriptor cạnh khai báo:

~~~text
javap -classpath out -s -p demo.Report
~~~

Ví dụ:

| Kiểu Java | Descriptor |
|---|---|
| `int` | `I` |
| `long` | `J` |
| `boolean` | `Z` |
| `void` | `V` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

Descriptor phương thức có dạng:

~~~text
(parameter-descriptors)return-descriptor
~~~

Ví dụ phương thức:

~~~java
public String format(int count, boolean active) {
    return "result";
}
~~~

có descriptor:

~~~text
(IZ)Ljava/lang/String;
~~~

`I` biểu diễn `int`, `Z` biểu diễn `boolean`, còn `Ljava/lang/String;` biểu diễn kiểu tham chiếu `String`.

Descriptor không lưu đầy đủ generic type. Nếu cần xem thông tin như `List<String>`, kiểm tra thêm attribute `Signature` bằng `javap -v`.

## 7. Đọc class-file header, constant pool và attribute bằng `javap -v`

Để xem cấu trúc chi tiết:

~~~text
javap -classpath out -v -p demo.Report
~~~

Output verbose thường chứa:

1. Đường dẫn class file được đọc.
2. Minor version và major version.
3. Access flags, tên lớp và superclass.
4. Constant pool.
5. Khai báo field và method.
6. Descriptor và generic signature.
7. Bytecode trong `Code`.
8. Exception table.
9. Các attribute như annotation, debug metadata, `MethodParameters`, `ConstantValue`, `Signature` và `BootstrapMethods` nếu có.

### 7.1. Kiểm tra phiên bản class file

Với class file được tạo theo Java 17, `javap -v` thường hiển thị:

~~~text
minor version: 0
major version: 61
~~~

Major version cho biết định dạng class file. Nó giúp xác định class file được biên dịch theo thế hệ Java nào và điều tra lỗi `UnsupportedClassVersionError`.

### 7.2. Kiểm tra constant pool

Constant pool lưu các hằng số và symbolic reference mà class file sử dụng, ví dụ:

- Tên lớp, interface, field và method.
- Descriptor.
- Chuỗi literal.
- Số nguyên, số thực và các hằng số khác.
- Method handle, method type, dynamic constant và invokedynamic reference.

Các mục constant pool được đánh số. Bytecode instruction có thể tham chiếu đến mục này bằng index. Khi đọc `javap -v`, bạn có thể lần từ instruction đến constant pool để hiểu method hoặc field mà instruction đang gọi.

### 7.3. Kiểm tra attributes

Trong output verbose, tìm tên attribute phù hợp với câu hỏi:

| Attribute | Điều cần kiểm tra |
|---|---|
| `Code` | Bytecode, max stack/local và exception table |
| `SourceFile` | Tên tệp nguồn |
| `LineNumberTable` | Ánh xạ offset bytecode sang số dòng |
| `LocalVariableTable` | Tên, kiểu và phạm vi của biến local khi có debug info |
| `LocalVariableTypeTable` | Generic signature bổ sung cho local variable |
| `MethodParameters` | Tên và cờ tham số khi compiler tạo metadata |
| `Signature` | Generic signature của class/field/method |
| `ConstantValue` | Giá trị compile-time constant của field phù hợp |
| `Exceptions` | Các exception được khai báo trong `throws` |
| `RuntimeVisibleAnnotations` | Annotation có retention runtime |
| `StackMapTable` | Frame metadata phục vụ bytecode verification |
| `BootstrapMethods` | Bootstrap method và đối số cho invokedynamic/dynamic constant |

Không phải class file nào cũng có tất cả các attribute. Sự hiện diện của chúng phụ thuộc mã nguồn, loại thành viên, phiên bản Java và tùy chọn compiler.

## 8. Debug metadata: kết hợp `javac -g` và `javap -l`

Các tùy chọn debug của `javac` quyết định metadata phục vụ debugger được ghi vào class file.

~~~text
javac -g -d out src/demo/Report.java
~~~

`-g` yêu cầu tạo các thông tin debug mà compiler hỗ trợ. Để bỏ debug metadata:

~~~text
javac -g:none -d out src/demo/Report.java
~~~

Có thể chọn nhóm cụ thể:

~~~text
javac -g:lines,source -d out src/demo/Report.java
javac -g:lines,vars,source -d out src/demo/Report.java
~~~

Sau đó kiểm tra:

~~~text
javap -classpath out -l -p demo.Report
~~~

Nếu có debug metadata, output có thể hiển thị:

- `LineNumberTable`: offset bytecode và dòng source.
- `LocalVariableTable`: tên biến local, slot, descriptor và phạm vi.
- `LocalVariableTypeTable`: generic signature bổ sung.

Nếu không thấy các bảng này, kiểm tra lệnh biên dịch và cấu hình build tool. Không thể kết luận source code không có biến hoặc dòng tương ứng chỉ vì class file không lưu debug metadata.

## 9. Kiểm tra tên tham số bằng `-parameters`

Tên tham số trong source không nhất thiết được lưu vào class file theo cách reflection có thể đọc. Dùng `-parameters` khi biên dịch nếu ứng dụng hoặc framework cần tên tham số:

~~~text
javac -parameters -d out src/demo/Report.java
~~~

Kiểm tra bằng:

~~~text
javap -classpath out -v -p demo.Report
~~~

Tìm `MethodParameters` và tên tham số tương ứng. Ở runtime, Reflection API có thể đọc:

~~~java
Parameter parameter = method.getParameters()[0];
System.out.println(parameter.getName());
System.out.println(parameter.isNamePresent());
~~~

Nếu không biên dịch với `-parameters`, `Parameter.isNamePresent()` thường là `false`; tên hiển thị có thể là dạng tổng hợp như `arg0`.

Phân biệt:

- `-parameters` tạo metadata tên tham số ở cấp method.
- `-g:vars` tạo debug metadata về biến local.
- `javap -l` chủ yếu hiển thị các bảng debug; `javap -v` hiển thị chi tiết attribute bao gồm `MethodParameters`.

## 10. Ví dụ hoàn chỉnh: biên dịch và kiểm tra compiler output

Tạo tệp `src/demo/Report.java`:

~~~java
package demo;

import java.io.IOException;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.reflect.Method;
import java.util.List;
import java.nio.file.Files;
import java.nio.file.Path;

@Retention(RetentionPolicy.RUNTIME)
@interface Reviewed {
    String value();
}

@Reviewed("sample")
public class Report {
    public static final int MAX_ITEMS = 5;

    private final String title;

    public Report(String title) {
        this.title = title;
    }

    public String format(List<String> values) {
        String first = values.isEmpty() ? "(empty)" : values.get(0);
        return title + ": " + first + " / " + MAX_ITEMS;
    }

    public static <T> T first(List<T> values) {
        return values.get(0);
    }

    public static String read(Path path) throws IOException {
        return Files.readString(path);
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Report report = new Report("Inventory");
        System.out.println(report.format(List.of("Java")));
        System.out.println(first(List.of("compiler", "output")));

        Method method = Report.class.getDeclaredMethod("first", List.class);
        System.out.println(method.getParameters()[0].getName());
        System.out.println(method.getParameters()[0].isNamePresent());
        System.out.println(Report.class.getAnnotation(Reviewed.class).value());
    }
}
~~~

Từ thư mục gốc `project`, tạo output folder và biên dịch:

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -g -parameters -encoding UTF-8 -d out src/demo/Report.java
~~~

macOS/Linux:

~~~sh
mkdir -p out
javac -g -parameters -encoding UTF-8 -d out src/demo/Report.java
~~~

Sau khi biên dịch, cây output:

~~~text
out/
  demo/
    Reviewed.class
    Report.class
~~~

Chạy ứng dụng:

~~~text
java -cp out demo.Report
~~~

Stdout:

~~~text
Inventory: Java / 5
compiler
values
true
sample
~~~

Bây giờ kiểm tra output theo từng mức:

~~~text
javap -classpath out demo.Report
javap -classpath out -p demo.Report
javap -classpath out -c -p demo.Report
javap -classpath out -s -p demo.Report
javap -classpath out -l -p demo.Report
javap -classpath out -v -p demo.Report
javap -classpath out -constants -p demo.Report
~~~

Những chi tiết đáng chú ý trong verbose output:

- `major version: 61` cho class file Java 17.
- `ConstantValue` cho field `MAX_ITEMS`.
- `Signature` cho phương thức generic `first`.
- `Exceptions` cho phương thức `read`.
- `RuntimeVisibleAnnotations` cho `@Reviewed("sample")`.
- `MethodParameters` cho tên tham số `values`.
- `Code` cho bytecode của constructor và các phương thức.
- `LineNumberTable` và `LocalVariableTable` do tùy chọn `-g`.
- `BootstrapMethods` có thể xuất hiện khi compiler dùng `invokedynamic`, chẳng hạn cho một số cách nối chuỗi.

Output verbose có thể dài. Có thể redirect vào file log để tìm các mục cần thiết, ví dụ `javap -v -p -classpath out demo.Report > report-javap.txt`; cú pháp redirect hoạt động tương tự trong PowerShell, Command Prompt và shell Unix.

## 11. So sánh output khi thay đổi tùy chọn compiler

Một cách kiểm tra hữu ích là biên dịch cùng một source với các tùy chọn khác nhau rồi so sánh class file.

### 11.1. Bản có debug và parameter metadata

~~~text
javac -g -parameters -d out-debug src/demo/Report.java
~~~

Kiểm tra:

~~~text
javap -v -p -classpath out-debug demo.Report
~~~

Bạn có thể tìm `LineNumberTable`, `LocalVariableTable` và `MethodParameters`.

### 11.2. Bản không có debug và parameter metadata

~~~text
javac -g:none -d out-min src/demo/Report.java
~~~

Kiểm tra:

~~~text
javap -v -p -classpath out-min demo.Report
~~~

Các bảng debug như `LineNumberTable` và `LocalVariableTable` không được tạo theo tùy chọn này. `MethodParameters` cũng không có vì lệnh không dùng `-parameters`.

Logic của chương trình vẫn giữ nguyên; metadata phục vụ debug/reflection thay đổi. Khi so sánh class file nhị phân, timestamp, thứ tự constant pool hoặc chi tiết compiler có thể khiến file khác byte-for-byte ngay cả khi hành vi tương đương. Hãy so sánh các phần có ý nghĩa trong `javap` thay vì chỉ dựa vào checksum.

### 11.3. Kiểm tra API theo phiên bản mục tiêu

Nếu đang dùng JDK mới nhưng cần bảo đảm output phù hợp Java 17:

~~~text
javac --release 17 -g -parameters -d out src/demo/Report.java
javap -v -classpath out demo.Report
~~~

Với Java 17, major version của class file là 61. `--release` kiểm soát mức ngôn ngữ, định dạng class file và tập API nền tảng công khai tương ứng; nó hữu ích hơn việc chỉ đặt riêng `-source` và `-target` khi cần kiểm tra API mục tiêu.

## 12. Kiểm tra compiler log và diagnostic

Khi cần hiểu compiler đã làm gì, dùng `-verbose`:

~~~text
javac -verbose -d out src/demo/Report.java
~~~

Tùy phiên bản JDK, log có thể hiển thị hoạt động như phân tích source, nạp class và ghi class file. Tùy chọn này hữu ích khi cần biết compiler đang đọc dependency từ đâu hoặc output được ghi vào vị trí nào.

Để xem diagnostic chi tiết hơn:

~~~text
javac -Xdiags:verbose -d out src/demo/Report.java
~~~

Để bật warning:

~~~text
javac -Xlint:all -d out src/demo/Report.java
~~~

Để coi warning là lỗi:

~~~text
javac -Xlint:all -Werror -d out src/demo/Report.java
~~~

Nếu annotation processor đang được dùng, các tùy chọn sau giúp xem round và processor được gọi:

~~~text
javac -XprintRounds -XprintProcessorInfo -d out src/demo/Report.java
~~~

`-verbose` là log hoạt động compiler; `-Xdiags:verbose` điều chỉnh độ chi tiết của diagnostic; `-Xlint` bật warning. Đây là ba mục đích khác nhau.

Thông thường, khi biên dịch thành công mà không bật log, `javac` không cần in thông báo thành công. Hãy kiểm tra exit code của tiến trình và sự hiện diện của class file. Khi dùng shell script hoặc CI, nên giữ riêng stdout, stderr và exit status để biết build thất bại ở đâu.

## 13. Kiểm tra generated source và native header

### 13.1. Generated source từ annotation processor

Nếu processor sinh mã nguồn, dùng `-s` để chỉ định thư mục chứa source được sinh:

~~~text
javac -processorpath processor-lib.jar -processor com.example.MyProcessor -s generated-src -d out src/demo/App.java
~~~

Kiểm tra `generated-src` để xem `.java` do processor tạo. Compiler có thể đưa các source file này vào các processing round tiếp theo và biên dịch chúng trong cùng lần chạy.

Nếu ứng dụng gọi lớp sinh tự động nhưng `javac` báo `cannot find symbol`, hãy kiểm tra:

- Processor có được nạp và xử lý annotation hay không.
- `-s` có trỏ đến đúng thư mục output hay không.
- Processor có tạo đúng package và tên lớp mà ứng dụng tham chiếu không.
- Diagnostic từ processor có báo lỗi không.

### 13.2. Native header từ phương thức JNI

Với mã Java có khai báo native method, `javac -h` có thể sinh header C/C++:

~~~text
javac -h native-headers -d out src/demo/NativeBridge.java
~~~

Thư mục `native-headers` chứa header được tạo cho các native method phù hợp. `-h` là tùy chọn của `javac`; `javap` không sinh header này.

Nếu cần kiểm tra phần khai báo native trong class file, dùng:

~~~text
javap -classpath out -p -s demo.NativeBridge
~~~

Bạn có thể xem modifier `native` và descriptor của phương thức, rồi đối chiếu với header được sinh.

## 14. Kiểm tra lớp bên trong JAR hoặc module

### 14.1. Kiểm tra class trong JAR

Nếu lớp đã được đóng gói trong JAR, có thể chỉ định JAR làm classpath:

~~~text
javap -classpath app.jar -p com.example.Main
javap -classpath app.jar -c -p com.example.Main
javap -classpath app.jar -v -p com.example.Main
~~~

Để xem danh sách entry trong JAR:

~~~text
jar --list --file app.jar
~~~

Nếu lớp phụ thuộc vào các JAR khác để phân giải kiểu, thêm chúng vào classpath theo đúng ký tự phân cách của hệ điều hành. Windows dùng `;`; macOS/Linux dùng `:`.

### 14.2. Kiểm tra lớp trong module

Với ứng dụng modular, chỉ định module path và module cần xem:

~~~text
javap --module-path mods --module com.example.app com.example.Main
~~~

Nếu cần xem một class trong module JDK, cú pháp module của `javap` cũng có thể dùng để xác định module chứa lớp. Kiểm tra `javap --help` của JDK đang cài để xác nhận tùy chọn được hỗ trợ.

### 14.3. Multi-release JAR

Một multi-release JAR có thể chứa các phiên bản class khác nhau theo phiên bản Java. Dùng `--multi-release` để chọn phiên bản cần xem:

~~~text
javap --multi-release 17 -classpath library.jar -p com.example.Api
~~~

Điều này hữu ích khi cần xác nhận class file mà runtime Java 17 sẽ chọn từ multi-release JAR.

## 15. Lỗi thường gặp khi kiểm tra compiler output

### `Error: class not found`

**Nguyên nhân:** classpath không trỏ đến thư mục gốc package, JAR thiếu lớp hoặc tên lớp đầy đủ bị sai.

**Cách xử lý:** xác nhận class file thực tế nằm ở đâu. Nếu file là `out/demo/Report.class`, dùng `javap -classpath out demo.Report`.

### `javap` hiển thị một class cũ

**Nguyên nhân:** classpath có nhiều bản cùng tên hoặc output directory chưa được build lại.

**Cách xử lý:** dùng classpath tường minh, kiểm tra working directory và chạy clean build khi cần. Không giả định class mà `javap` tìm thấy là bản vừa biên dịch nếu classpath còn chứa output cũ.

### Không thấy bytecode

**Nguyên nhân:** lệnh chưa dùng `-c` hoặc lớp/phương thức không có `Code` attribute, chẳng hạn abstract/native method.

**Cách xử lý:** thêm `-c`; nếu phương thức abstract/native, kiểm tra khai báo và hiểu rằng nó không có bytecode method body thông thường.

### Không thấy tên biến hoặc số dòng

**Nguyên nhân:** class file được biên dịch mà không có debug metadata tương ứng.

**Cách xử lý:** biên dịch lại với `-g`, rồi xem bằng `javap -l` hoặc `javap -v`.

### Không thấy tên tham số gốc

**Nguyên nhân:** thiếu `MethodParameters`.

**Cách xử lý:** biên dịch lại với `-parameters`; `-g` không thay thế tùy chọn này.

### Không thấy generic type như trong source

**Nguyên nhân:** JVM descriptor phản ánh type erasure; generic signature là metadata bổ sung.

**Cách xử lý:** dùng `javap -v` và tìm `Signature`. Không kỳ vọng descriptor luôn chứa kiểu generic đầy đủ.

### Output sau biên dịch khác dự kiến

**Nguyên nhân:** đang dùng sai JDK, sai `--release`, annotation processor khác phiên bản, build cache cũ hoặc compiler options khác.

**Cách xử lý:** ghi lại `java --version`, `javac --version`, toàn bộ lệnh build, classpath/module path và các biến môi trường liên quan. Chạy clean build trong đúng toolchain rồi kiểm tra lại class file.

### Không thể đọc class file

**Nguyên nhân:** class file bị hỏng, bị công cụ bytecode biến đổi sai hoặc không tương thích với phiên bản `javap`.

**Cách xử lý:** xác định nguồn file, kiểm tra lại bằng JDK phù hợp, chạy `javap -v` và build lại từ source nếu cần. Nếu lỗi xuất hiện sau instrumentation hoặc obfuscation, kiểm tra công cụ có bảo toàn attribute và cấu trúc class file hợp lệ không.

## 16. Quy trình kiểm tra compiler output có thể tái hiện

Khi cần điều tra một build, thực hiện theo thứ tự:

1. **Ghi lại toolchain:** `java --version`, `javac --version` và phiên bản build tool.
2. **Ghi lại lệnh biên dịch:** bao gồm `--release`, `-encoding`, `-d`, classpath/module path, processor path và tùy chọn debug.
3. **Xác định output directory:** tìm class file đúng package và tránh đọc nhầm output cũ.
4. **Kiểm tra khai báo:** dùng `javap -p` để xác nhận class, field, constructor và method.
5. **Kiểm tra bytecode:** dùng `javap -c -p` để xem instruction của phương thức cần phân tích.
6. **Kiểm tra descriptor:** dùng `javap -s -p` để đối chiếu kiểu JVM.
7. **Kiểm tra metadata:** dùng `javap -v -p` để đọc constant pool, class-file version và attributes.
8. **Kiểm tra debug/parameter info:** dùng `javap -l` và verbose output; đối chiếu với `-g` và `-parameters`.
9. **Kiểm tra output phụ:** xem generated source, native header và compiler log nếu dự án dùng các tính năng đó.
10. **Kiểm tra runtime:** chạy chương trình hoặc test sau khi xác nhận class file đúng. Bytecode listing không chứng minh logic chạy đúng trên mọi đầu vào.

Nên lưu command line build và toolchain version trong script hoặc CI để người khác tái hiện được kết quả. Nếu so sánh output giữa hai lần build, hãy so sánh cùng phiên bản JDK, cùng dependency và cùng tùy chọn compiler.

## 17. Checklist ghi nhớ

- [ ] Phân biệt compiler output, compiler diagnostics và stdout/stderr lúc runtime.
- [ ] Dùng `javac -d` để ghi class file vào thư mục riêng.
- [ ] Dùng `javap -classpath` để chỉ đúng output directory hoặc JAR.
- [ ] Dùng `javap -p` để xem cả thành viên private.
- [ ] Dùng `javap -c` để kiểm tra bytecode.
- [ ] Dùng `javap -s` để kiểm tra JVM descriptor.
- [ ] Dùng `javap -v` để xem class-file version, constant pool và attributes.
- [ ] Dùng `javap -l` để kiểm tra debug tables khi chúng tồn tại.
- [ ] Dùng `javac -g` cho debug metadata và `javac -parameters` cho tên tham số reflection.
- [ ] Dùng `javac -verbose`, `-Xdiags:verbose` và `-Xlint` đúng mục đích.
- [ ] Kiểm tra `-s` nếu annotation processor sinh source.
- [ ] Kiểm tra `-h` nếu compiler sinh native header.
- [ ] Xác nhận classpath/module path và tránh đọc nhầm class file cũ.
- [ ] Chạy ứng dụng hoặc test để xác nhận hành vi sau khi kiểm tra bytecode.

Kiểm tra compiler output bằng `javap` giúp bạn nối được mã nguồn với sản phẩm thực tế mà compiler tạo ra. Khi biết cách đọc khai báo, bytecode, descriptor, constant pool và attribute, bạn có thể xác nhận cấu hình build, điều tra lỗi tương thích, kiểm tra metadata phục vụ reflection/debugger và hiểu rõ hơn cách Java được biểu diễn trên JVM.