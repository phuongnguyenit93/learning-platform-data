# Kiểm tra class file trong Java

Class file là sản phẩm nhị phân do trình biên dịch Java tạo ra, thường có phần mở rộng `.class`. Nó chứa bytecode, thông tin về class, field, method, kiểu dữ liệu, tham chiếu đến các lớp khác và nhiều thuộc tính phục vụ JVM. Khi chương trình gặp lỗi tương thích phiên bản, lỗi liên kết hoặc hành vi không như mong đợi, kiểm tra class file giúp xác định compiler đã tạo ra nội dung gì.

Công cụ chính trong JDK để đọc cấu trúc và disassemble class file là `javap`. Công cụ này hiển thị metadata và bytecode ở dạng văn bản để người phát triển kiểm tra artifact đã biên dịch.

## 1. Class file là gì?

Java source code trong tệp `.java` được compiler `javac` chuyển thành class file. Class file chứa bytecode theo định dạng chuẩn của JVM, không phải mã máy riêng cho một CPU.

Một class file có thể chứa:

- Tên class, superclass và các interface được triển khai.
- Access flags cho class, field và method.
- Constant pool với hằng số, tên class, tên method, descriptor và symbolic reference.
- Bytecode của từng method.
- Thông tin về exception handler.
- Annotation, generic signature, inner class, record hoặc module metadata.
- Debug attributes như số dòng nguồn và tên biến cục bộ, nếu compiler đã sinh chúng.

JVM nạp class file, kiểm tra định dạng và bytecode, liên kết các symbolic reference rồi thực thi bytecode. JVM có thể diễn giải bytecode hoặc biên dịch các đoạn mã thường chạy thành mã máy bằng JIT compiler.

Class file không nhất thiết chứa toàn bộ mã nguồn ban đầu. Các comment, định dạng khoảng trắng và tên biến cục bộ có thể không còn nếu compiler không lưu debug information. Vì vậy, `javap` là công cụ kiểm tra cấu trúc và bytecode, không phải công cụ khôi phục chính xác source code.

## 2. Tìm class file cần kiểm tra

Khi biên dịch với tùy chọn `-d`, `javac` đặt class file vào thư mục đầu ra theo cấu trúc package.

Ví dụ:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── App.java
└── out/
    └── com/
        └── example/
            └── App.class
~~~

Nếu class có package `com.example`, tên đầy đủ (fully qualified name) của class là `com.example.App`. Khi dùng `javap` với classpath, truyền tên đầy đủ này thay vì đường dẫn package có dấu gạch chéo.

Kiểm tra nội dung thư mục output bằng:

~~~powershell
Get-ChildItem -Recurse out
~~~

Có thể liệt kê nội dung JAR bằng:

~~~powershell
jar --list --file app.jar
~~~

Nếu class nằm trong JAR, `javap` có thể đọc trực tiếp qua classpath; không nhất thiết phải giải nén JAR trước.

## 3. Cú pháp cơ bản của javap

Cú pháp tổng quát:

~~~text
javap [options] class...
~~~

Ví dụ kiểm tra một class đã biên dịch trong thư mục `out`:

~~~powershell
javap -classpath out com.example.App
~~~

`-classpath` (hoặc `-cp`) chỉ định vị trí để `javap` tìm class. Nếu không chỉ định, công cụ dùng classpath mặc định của môi trường.

Đầu ra mặc định hiển thị khai báo class và các thành viên public. Ví dụ, bạn có thể thấy tên class, superclass, constructor và method public. Để xem thành viên private hoặc bytecode, dùng các tùy chọn chi tiết ở phần sau.

Các tùy chọn quan trọng:

| Tùy chọn | Công dụng |
|---|---|
| `-p` hoặc `-private` | Hiển thị mọi class member, gồm private |
| `-c` | Disassemble bytecode của method |
| `-l` | Hiển thị line number table và local variable table nếu có |
| `-s` | Hiển thị internal type signature/descriptor |
| `-constants` | Hiển thị giá trị constant của các field hằng |
| `-v` hoặc `-verbose` | Hiển thị thông tin chi tiết như constant pool, flags, version và attributes |
| `-classpath` hoặc `-cp` | Chỉ định classpath để tìm class |
| `--module-path` | Chỉ định module path |
| `--module` | Chọn module chứa class cần kiểm tra |
| `--multi-release` | Chọn phiên bản entry trong multi-release JAR |

Có thể kết hợp nhiều tùy chọn trong một lần gọi, ví dụ `javap -p -c -l -classpath out com.example.App`.

## 4. Ví dụ thực hành: biên dịch và kiểm tra class

Tạo tệp `src/com/example/App.java`:

~~~java
package com.example;

public class App {
    private static final int BONUS = 10;
    private final String label;

    public App(String label) {
        this.label = label;
    }

    public int measure() {
        return label.length() + BONUS;
    }

    public static void main(String[] args) {
        String label = args.length == 0 ? "Java" : String.join(" ", args);
        App app = new App(label);
        System.out.println("score=" + app.measure());
    }
}
~~~

Biên dịch bằng JDK 17 trở lên, có bật đầy đủ debug information:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac --release 17 -g -d out src/com/example/App.java
~~~

Chạy ứng dụng:

~~~powershell
java -cp out com.example.App Java
~~~

Kết quả:

~~~text
score=14
~~~

Bây giờ kiểm tra khai báo public:

~~~powershell
javap -classpath out com.example.App
~~~

Hiển thị cả private member:

~~~powershell
javap -p -classpath out com.example.App
~~~

Bạn sẽ thấy field `BONUS`, field `label`, constructor, method `measure()` và method `main(String[])`. Nếu không dùng `-p`, các thành viên private như `label` có thể không xuất hiện trong phần khai báo mặc định.

## 5. Kiểm tra bytecode bằng javap -c

Tùy chọn `-c` disassemble bytecode của các method:

~~~powershell
javap -c -classpath out com.example.App
~~~

Đầu ra có dạng tương tự:

~~~text
public int measure();
  Code:
     0: aload_0
     1: getfield      #...  // Field label:Ljava/lang/String;
     4: invokevirtual #...  // Method java/lang/String.length:()I
     7: bipush        10
     9: iadd
    10: ireturn
~~~

Chỉ số constant pool trong dấu `#...` và offset có thể khác giữa các bản compiler hoặc khi source thay đổi. Đoạn trên minh họa luồng bytecode của method `measure()`:

1. `aload_0` đưa tham chiếu `this` lên operand stack.
2. `getfield` đọc field `label`.
3. `invokevirtual` gọi `String.length()`.
4. `bipush 10` đẩy hằng số 10 lên stack.
5. `iadd` cộng hai giá trị integer.
6. `ireturn` trả kết quả integer về caller.

Bytecode thao tác trên operand stack và local variable slots. Đọc bytecode giúp xác định compiler đã biến một biểu thức thành những instruction nào, method nào được gọi và nhánh điều khiển chạy ra sao.

`javap -c` không hiển thị source code nguyên bản. Nó hiển thị instruction JVM ở dạng mnemonic, đủ để phân tích luồng thực thi nhưng không phục hồi comment hay cách trình bày ban đầu.

## 6. Kiểm tra metadata bằng javap -verbose

`-verbose` (viết tắt `-v`) hiển thị nhiều chi tiết nội bộ của class file:

~~~powershell
javap -verbose -classpath out com.example.App
~~~

Một số phần quan trọng:

- `Classfile`: đường dẫn hoặc vị trí class file được đọc.
- `minor version` và `major version`: phiên bản định dạng class file.
- `flags`: các access flag như public, final, super hoặc interface.
- `this_class` và `super_class`: class hiện tại và superclass.
- `interfaces`: danh sách interface mà class triển khai.
- `fields` và `methods`: số lượng field và method cùng mô tả của chúng.
- `Constant pool`: các hằng số, tên class, tên field/method, descriptor và symbolic reference.
- `Code`: bytecode, giới hạn stack/local và exception table của method.
- `Attributes`: metadata bổ sung như SourceFile, LineNumberTable, StackMapTable hoặc RuntimeVisibleAnnotations.

Ví dụ, để kiểm tra version, tìm hai dòng tương tự:

~~~text
minor version: 0
major version: 61
~~~

Với class file Java 17 thông thường, major version là 61. Nếu class sử dụng preview feature, minor version có thể là 65535; runtime tương ứng cần được chạy với tùy chọn preview phù hợp.

`Constant pool` đặc biệt hữu ích khi kiểm tra method reference, tên lớp, descriptor hoặc hằng số mà bytecode sử dụng. Tuy nhiên, đây là cấu trúc nhị phân đã được compiler chuẩn hóa; không nên diễn giải mọi entry như một chuỗi source code.

## 7. Kiểm tra signature, field và debug information

### 7.1. Internal descriptor với -s

Tùy chọn `-s` hiển thị descriptor nội bộ của field và method. Descriptor dùng ký hiệu JVM để biểu diễn kiểu:

| Ký hiệu | Kiểu Java |
|---|---|
| `I` | int |
| `J` | long |
| `Z` | boolean |
| `V` | void |
| `Ljava/lang/String;` | java.lang.String |
| `[I` | int[] |
| `[Ljava/lang/String;` | String[] |

Ví dụ, method `public int measure()` có descriptor `()I`: không nhận tham số và trả về int. Method `main(String[] args)` có descriptor `([Ljava/lang/String;)V`: nhận một mảng String và trả về void.

Chạy:

~~~powershell
javap -s -p -classpath out com.example.App
~~~

Descriptor hữu ích khi debug lỗi liên kết, so sánh binary API hoặc phân tích bytecode có generic và overload.

### 7.2. Debug information với -l

Tùy chọn `-l` hiển thị các debug table có trong class file:

~~~powershell
javap -l -classpath out com.example.App
~~~

Các bảng thường gặp:

- `LineNumberTable` ánh xạ bytecode offset về dòng source.
- `LocalVariableTable` ghi tên và kiểu biến cục bộ cùng phạm vi tồn tại trong method.
- `LocalVariableTypeTable` có thể lưu thông tin kiểu generic của biến cục bộ.

Thông tin này phụ thuộc vào cách biên dịch. Ví dụ, `javac -g` yêu cầu sinh đầy đủ debug information; `javac -g:none` tắt debug information. Nếu class được biên dịch mà không có local variable table, `javap -l` không thể tự suy ra tên biến gốc.

### 7.3. Hằng số với -constants

Tùy chọn `-constants` hiển thị giá trị của các field constant:

~~~powershell
javap -constants -p -classpath out com.example.App
~~~

Nó hữu ích khi kiểm tra các field static final có giá trị hằng được compiler ghi nhận. Không phải mọi field final đều là compile-time constant; giá trị được tính lúc runtime có thể không xuất hiện dưới dạng constant value attribute.

## 8. Kiểm tra class bên trong JAR

Có thể dùng JAR trực tiếp làm classpath:

~~~powershell
javap -classpath app.jar -p -c com.example.App
~~~

Nếu JAR có nhiều thư viện phụ thuộc, truyền danh sách classpath phù hợp. Ví dụ trên Windows:

~~~powershell
javap -classpath "app.jar;lib/*" -verbose com.example.App
~~~

Trên Linux/macOS, dấu phân cách classpath là dấu hai chấm:

~~~bash
javap -classpath "app.jar:lib/*" -verbose com.example.App
~~~

Để xác định class có thật sự nằm trong archive, dùng:

~~~powershell
jar --list --file app.jar
~~~

`javap` đọc class theo tên đầy đủ. Nếu package hoặc tên class không khớp đường dẫn bên trong JAR, công cụ sẽ không tìm thấy class.

Với multi-release JAR, có thể yêu cầu `javap` xem entry dành cho một release cụ thể bằng `--multi-release N`. Điều này hữu ích khi cùng một JAR chứa các implementation khác nhau trong `META-INF/versions`.

## 9. Kiểm tra module và module-info.class

Với dự án modular, class file `module-info.class` lưu module descriptor đã biên dịch. Có thể dùng `javap -verbose` để đọc các thuộc tính module:

~~~powershell
javap -verbose mods/com.example.app/module-info.class
~~~

Đầu ra verbose có thể hiển thị `Module` attribute, gồm module name, các module được yêu cầu, package được xuất hoặc mở và thông tin provider nếu có.

Để xem mô tả module ở mức dễ đọc hơn, dùng công cụ `jar`:

~~~powershell
jar --describe-module --file app.jar
~~~

Nếu module được đặt trên module path, `javap` cũng hỗ trợ chỉ định module path và module cần kiểm tra. Ví dụ:

~~~powershell
javap --module-path mods --module com.example.app com.example.app.Main
~~~

Phân biệt hai việc:

- `javap` kiểm tra class file và bytecode của class.
- `jar --describe-module` hiển thị mô tả module từ modular JAR.

Nếu ứng dụng gặp lỗi module resolution, cần kiểm tra cả module descriptor lẫn vị trí các module trên module path.

## 10. Đọc class file version và xử lý lỗi tương thích

Major version biểu thị phiên bản class file mà JVM cần hỗ trợ. Một số mốc thường gặp:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Ví dụ, nếu `javap -verbose` cho thấy `major version: 61`, class file được tạo theo định dạng Java 17. Runtime Java 11 chỉ hỗ trợ đến major version 55 nên không thể nạp class file này.

Lỗi thường thấy là `UnsupportedClassVersionError`. Cách xử lý:

1. Kiểm tra major version bằng `javap -verbose`.
2. Kiểm tra runtime thực tế bằng `java -version`.
3. Nếu phải hỗ trợ runtime cũ, biên dịch lại bằng `javac --release N` với N là release mục tiêu.
4. Kiểm tra các thư viện phụ thuộc; một dependency có thể được biên dịch cho Java mới hơn ứng dụng.
5. Chạy test trên runtime mục tiêu thực tế.

`--release` giúp giới hạn source language, class file target và API Java Platform khi biên dịch bằng JDK mới. Chỉ kiểm tra major version không đủ để chứng minh ứng dụng tương thích, vì class file có thể gọi API hoặc phụ thuộc thư viện không có trên runtime cũ.

## 11. Class file và các attributes thường gặp

Class file có cấu trúc nhị phân được định nghĩa bởi JVM Specification. Ở mức khái quát, cấu trúc gồm:

1. Magic number: bốn byte mở đầu có giá trị hexadecimal `CAFEBABE`.
2. Minor và major version: phiên bản class file.
3. Constant pool: các hằng số và symbolic reference.
4. Access flags, this class, superclass và danh sách interface.
5. Field table và method table.
6. Attribute table ở cấp class, field, method hoặc code.

Một số attribute thường thấy trong đầu ra verbose:

| Attribute | Ý nghĩa |
|---|---|
| `SourceFile` | Tên tệp source được compiler ghi nhận |
| `LineNumberTable` | Ánh xạ bytecode offset sang số dòng |
| `LocalVariableTable` | Thông tin biến cục bộ khi có debug data |
| `StackMapTable` | Dữ liệu phục vụ bytecode verification |
| `Signature` | Generic signature của class, field hoặc method |
| `RuntimeVisibleAnnotations` | Annotation có thể đọc tại runtime |
| `BootstrapMethods` | Bootstrap method cho invokedynamic hoặc dynamic constant |
| `NestHost` và `NestMembers` | Thông tin nest-based access control |
| `Record` | Metadata của record class |
| `PermittedSubclasses` | Danh sách subclass được phép của sealed class |
| `Module` | Module descriptor metadata |

Không phải class file nào cũng có mọi attribute. Sự hiện diện phụ thuộc tính năng Java được dùng, compiler và các tùy chọn biên dịch.

## 12. Lỗi thường gặp khi kiểm tra class file

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Error: class not found` | Sai classpath hoặc tên đầy đủ của class | Kiểm tra thư mục/JAR và package; dùng `-classpath` chính xác |
| `javap` chỉ hiển thị method public | Chưa bật chế độ hiển thị private member | Dùng `-p` hoặc `-private` |
| Không thấy bytecode | Chỉ dùng lệnh mặc định | Thêm `-c` |
| Không thấy tên biến cục bộ | Class không được biên dịch với local variable debug information | Biên dịch lại bằng `-g` rồi xem `-l` |
| Không thấy số dòng source | Thiếu LineNumberTable hoặc đang xem artifact đã loại debug info | Biên dịch lại với debug info phù hợp |
| `UnsupportedClassVersionError` | Runtime không hỗ trợ major version của class | Xem `major version` và biên dịch bằng `--release` phù hợp hoặc nâng runtime |
| Không thấy class trong JAR | Tên class sai hoặc archive không chứa package đó | Dùng `jar --list` để kiểm tra entry |
| Output verbose quá dài | Dùng `-v` cho class lớn hoặc nhiều dependency | Dùng tùy chọn hẹp hơn như `-c`, `-s`, `-l` hoặc kiểm tra một class cụ thể |
| Module descriptor khó đọc | Đang xem raw attribute hoặc sai module path | Dùng `jar --describe-module` và kiểm tra `module-info.class` |

## 13. Quy trình kiểm tra class file khi debug hoặc review

Khi cần xác minh một artifact, thực hiện theo thứ tự:

1. Xác định đúng file JAR hoặc thư mục output mà ứng dụng thực sự sử dụng.
2. Dùng `jar --list` nếu class nằm trong archive.
3. Dùng `javap -classpath ...` để xác nhận class và public API.
4. Dùng `javap -p` nếu cần kiểm tra private field hoặc method.
5. Dùng `javap -c` để đọc bytecode của method liên quan.
6. Dùng `javap -verbose` để xem version, constant pool, flags và attributes.
7. Dùng `javap -s` hoặc `-l` khi cần descriptor hoặc debug mapping.
8. Đối chiếu major version với runtime và kiểm tra dependency.
9. Chạy test trên đúng runtime, module path và classpath của môi trường triển khai.

Không cần bắt đầu bằng verbose output cho mọi vấn đề. Chọn tùy chọn theo câu hỏi: lỗi API thì xem signature và constant pool; lỗi luồng thực thi thì xem bytecode; lỗi tương thích thì xem major version; lỗi debug thì xem attributes.

## 14. Checklist trước khi xác nhận class file

- [ ] Đang kiểm tra đúng artifact được ứng dụng sử dụng.
- [ ] Đã xác nhận class name, package và classpath/module path.
- [ ] Đã kiểm tra khai báo class và member bằng `javap`.
- [ ] Đã dùng `-c` nếu cần xác minh bytecode.
- [ ] Đã dùng `-verbose` để xem major/minor version khi cần.
- [ ] Đã kiểm tra debug attributes nếu debugger cần số dòng hoặc tên biến.
- [ ] Đã kiểm tra module descriptor nếu ứng dụng dùng JPMS.
- [ ] Đã đối chiếu class file version với runtime mục tiêu.
- [ ] Đã kiểm tra dependency và chạy thử trên môi trường tương thích.

`javap` là công cụ đầu tiên nên dùng khi cần nhìn vào class file đã biên dịch. Kết hợp `-c` để xem bytecode, `-verbose` để xem cấu trúc và version, `-p` để xem member đầy đủ, và `-l`/`-s` để kiểm tra debug data hoặc descriptor. Đọc đúng loại thông tin sẽ giúp tìm lỗi nhanh hơn và xác minh artifact trước khi phát hành.
