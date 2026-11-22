# Lệnh javap trong Java

## 1. javap là gì?

`javap` là công cụ dòng lệnh đi kèm JDK, dùng để đọc và hiển thị thông tin từ tệp Java class (`.class`). Nó thường được gọi là **disassembler** vì có thể trình bày các lệnh bytecode mà compiler đã ghi vào class file.

Một class file chứa nhiều thông tin hơn phần thân method: tên class, class cha, interface, modifier, field, method, descriptor, constant pool và các attribute. `javap` cho phép chọn mức chi tiết để xem những phần cần thiết khi học Java, debug hoặc điều tra lỗi tương thích.

Các tình huống thường dùng:

- Xem class có những constructor, field và method nào.
- Kiểm tra modifier như `public`, `private`, `static`, `final` và `abstract`.
- Đọc bytecode của một method bằng tùy chọn `-c`.
- Xem descriptor nội bộ của field và method bằng `-s`.
- Kiểm tra constant pool, class-file version và metadata bằng `-v`.
- Kiểm tra thông tin dòng mã và biến cục bộ bằng `-l`.
- Xem hằng số static final bằng `-constants`.
- Kiểm tra class được lấy từ thư mục, JAR hoặc module nào.

`javap` là công cụ phân tích class file. Nó không chạy chương trình, không biên dịch mã nguồn và không phải decompiler có thể khôi phục nguyên văn mã Java ban đầu.

## 2. javap hoạt động với những loại đầu vào nào?

Thông thường, bạn truyền tên đầy đủ của class (fully qualified class name) cho `javap`. Tên này gồm package và tên class, ví dụ `com.example.Calculator`.

Công cụ có thể tìm class từ:

- Classpath mặc định của môi trường Java.
- Thư mục chứa class file.
- JAR hoặc ZIP có chứa class file.
- Module trên module path hoặc các module của runtime, khi chỉ định tùy chọn module phù hợp.
- Đường dẫn trực tiếp tới một tệp class trong các trường hợp được hỗ trợ.

Ví dụ, nếu class nằm tại:

```text
project/
  out/
    com/
      example/
        Calculator.class
```

thì tên class là `com.example.Calculator`. Thư mục cần đặt trên classpath là `out`, không phải thư mục `out/com/example`.

## 3. Cú pháp tổng quát

Cú pháp cơ bản:

```bash
javap [options] class...
```

Trong đó:

- `javap` là lệnh phân tích class file.
- `options` là các tùy chọn điều khiển phạm vi và mức chi tiết của kết quả.
- `class...` là một hoặc nhiều tên class cần xem.

Ví dụ:

```bash
javap java.lang.String
javap -p com.example.Calculator
javap -classpath out -c com.example.Calculator
```

Nếu không chỉ định tùy chọn, `javap` chủ yếu hiển thị chữ ký class, constructor, field và method ở phạm vi truy cập mặc định. Nó không hiển thị phần bytecode của method.

Có thể xem danh sách tùy chọn được hỗ trợ bởi JDK đang cài:

```bash
javap -help
```

Nội dung help là nguồn kiểm tra chính xác cho phiên bản JDK cụ thể, vì tùy chọn có thể được bổ sung hoặc thay đổi giữa các phiên bản.

## 4. Cấu hình classpath khi dùng javap

Nếu class nằm ngoài classpath mặc định, hãy chỉ rõ vị trí bằng `-classpath`, `--class-path` hoặc dạng viết tắt `-cp`.

Ví dụ:

```bash
javap -classpath out com.example.Calculator
```

Các cách viết sau tương đương:

```bash
javap -cp out com.example.Calculator
javap --class-path out com.example.Calculator
```

Nếu class nằm trong JAR:

```bash
javap -classpath app.jar com.example.Calculator
```

Nếu cần tìm class ở nhiều vị trí, truyền danh sách đường dẫn với dấu phân cách phụ thuộc hệ điều hành:

- Windows: dấu chấm phẩy (`;`).
- Linux và macOS: dấu hai chấm (`:`).

Ví dụ trên Windows:

```powershell
javap -classpath "out;lib\utilities.jar" com.example.Calculator
```

Ví dụ trên Linux/macOS:

```bash
javap -classpath "out:lib/utilities.jar" com.example.Calculator
```

Tên class cần truyền theo dạng package, không thêm đuôi `.class` khi đang dùng tên class trên classpath. Nếu truyền một đường dẫn class file trực tiếp, hãy làm theo cú pháp đường dẫn mà phiên bản `javap` hỗ trợ.

Một lỗi thường gặp là đặt sai thư mục gốc classpath. Với class `com.example.Calculator` nằm trong `out/com/example/Calculator.class`, classpath phải là `out`.

## 5. Các tùy chọn javap quan trọng

Những tùy chọn sau thường hữu ích nhất khi làm việc với class file:

| Tùy chọn | Chức năng |
|---|---|
| `-help` hoặc `--help` | Hiển thị hướng dẫn sử dụng |
| `-version` | Hiển thị phiên bản công cụ |
| `-public` | Chỉ hiển thị class và thành viên public |
| `-protected` | Hiển thị public và protected |
| `-package` | Hiển thị các thành viên trong phạm vi package trở lên; đây là mức mặc định |
| `-p` hoặc `-private` | Hiển thị tất cả thành viên, kể cả private |
| `-c` | Hiển thị bytecode của method và constructor |
| `-s` | Hiển thị internal type signature (descriptor) |
| `-l` | Hiển thị thông tin số dòng và biến cục bộ nếu class file có metadata |
| `-v` hoặc `-verbose` | Hiển thị thông tin chi tiết của class file |
| `-constants` | Hiển thị các hằng số static final |
| `-sysinfo` | Hiển thị thông tin hệ thống về class, như đường dẫn, kích thước, ngày và SHA-256 trên các bản JDK hỗ trợ |
| `-classpath`, `--class-path`, `-cp` | Chỉ định nơi tìm class |
| `--module-path` | Chỉ định module path |
| `--module` | Chỉ định module cần phân tích |
| `--system` | Chỉ định vị trí chứa các system modules |
| `--multi-release` | Chọn phiên bản entry trong multi-release JAR để phân tích |

Có thể kết hợp nhiều tùy chọn, ví dụ `-p -c -s` để xem cả thành viên private, bytecode và descriptor.

### 5.1. Hiển thị thành viên private bằng -p

Theo mặc định, các thành viên private không được hiển thị. Dùng:

```bash
javap -p -classpath out com.example.Calculator
```

Tùy chọn `-p` tương đương `-private`. Nó hữu ích khi cần kiểm tra field hoặc method nội bộ của class đã biên dịch.

Lưu ý: xem được tên private member trong class file không có nghĩa là ứng dụng được phép truy cập member đó từ mã Java thông thường. Quy tắc truy cập của ngôn ngữ và JVM vẫn áp dụng khi liên kết và thực thi.

### 5.2. Hiển thị bytecode bằng -c

`-c` yêu cầu `javap` disassemble phần code của method:

```bash
javap -c -classpath out com.example.Calculator
```

Kết quả cho biết các lệnh bytecode và offset tương ứng trong method. Đây là tùy chọn thường dùng nhất khi muốn hiểu compiler đã chuyển một biểu thức Java thành những lệnh nào.

### 5.3. Hiển thị descriptor bằng -s

`-s` in descriptor nội bộ của field và method:

```bash
javap -s -classpath out com.example.Calculator
```

Descriptor hữu ích khi phân tích overload, generic bridge method, reflection hoặc công cụ bytecode. Ví dụ descriptor `(II)I` có nghĩa method nhận hai tham số kiểu int và trả về int.

### 5.4. Hiển thị thông tin chi tiết bằng -v

`-v` (hoặc `-verbose`) hiển thị nhiều thông tin class-file hơn, bao gồm constant pool và các attribute:

```bash
javap -v -classpath out com.example.Calculator
```

Dùng tùy chọn này khi cần kiểm tra class-file version, access flags, annotation metadata, method descriptor, Code attribute hoặc StackMapTable. Kết quả dài hơn đáng kể so với chế độ mặc định.

### 5.5. Hiển thị thông tin debug bằng -l

`-l` hiển thị các bảng debug như `LineNumberTable` và `LocalVariableTable` nếu chúng được ghi vào class file:

```bash
javap -l -classpath out com.example.Calculator
```

Nếu class được biên dịch mà không có thông tin debug tương ứng, `javap` không thể tự khôi phục tên biến cục bộ hoặc ánh xạ dòng mã ban đầu.

### 5.6. Hiển thị hằng số bằng -constants

`-constants` hiển thị giá trị của các field constant phù hợp, thường là các field `static final` có giá trị hằng tại thời điểm biên dịch:

```bash
javap -p -constants -classpath out com.example.Calculator
```

Kết hợp `-p` để hiển thị cả constant field private trong ví dụ. Tùy chọn này hữu ích khi kiểm tra hằng số được lưu trong class file. Nó không phải công cụ để đọc giá trị runtime của mọi field.

## 6. Ví dụ thực hành: tạo class rồi dùng javap

Ví dụ sau sử dụng Java 17 trở lên. Tạo tệp `src/com/example/Calculator.java`:

```java
package com.example;

public class Calculator {
    private static final int BASE = 10;

    public static int add(int left, int right) {
        return left + right;
    }

    private static int twice(int value) {
        return value * 2;
    }

    public static void main(String[] args) {
        int total = add(2, 3);
        System.out.println("total=" + total);
    }
}
```

Tạo thư mục đầu ra. Trên Linux/macOS:

```bash
mkdir -p out
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
```

Biên dịch từ thư mục gốc dự án:

```bash
javac --release 17 -g -d out src/com/example/Calculator.java
```

Ý nghĩa:

- `--release 17` đặt mức ngôn ngữ, bytecode và API Java SE mục tiêu là Java 17.
- `-g` yêu cầu compiler tạo thông tin debug.
- `-d out` đặt class file vào thư mục `out` theo cấu trúc package.

Chạy chương trình:

```bash
java -cp out com.example.Calculator
```

Stdout chính xác:

```text
total=5
```

Sau khi biên dịch, class file nằm tại `out/com/example/Calculator.class`.

## 7. Đọc kết quả javap ở chế độ mặc định

Chạy:

```bash
javap -classpath out com.example.Calculator
```

Kết quả điển hình:

```text
Compiled from "Calculator.java"
public class com.example.Calculator {
  public com.example.Calculator();
  public static int add(int, int);
  public static void main(java.lang.String[]);
}
```

Ý nghĩa:

- Dòng đầu cho biết tên tệp nguồn được ghi trong metadata.
- Dòng khai báo class cho biết class là public.
- Constructor mặc định được compiler tạo ra vì class không khai báo constructor riêng.
- Method `add` nhận hai tham số int và trả về int.
- Method `main` nhận mảng String và trả về void.
- Field `BASE` và method `twice` không xuất hiện vì chúng là private.

Kết quả mặc định cho biết cấu trúc và chữ ký thành viên trong phạm vi truy cập tương ứng. Nó không cho thấy các câu lệnh bên trong method.

## 8. Hiển thị private member và bytecode

Để xem toàn bộ thành viên:

```bash
javap -p -classpath out com.example.Calculator
```

Kết quả sẽ có thêm field `BASE` và method `twice`:

```text
private static final int BASE;
private static int twice(int);
```

Để xem bytecode:

```bash
javap -p -c -classpath out com.example.Calculator
```

Phần method `add` có dạng:

```text
public static int add(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
```

Cách đọc:

1. `iload_0` đẩy tham số đầu tiên lên operand stack.
2. `iload_1` đẩy tham số thứ hai lên operand stack.
3. `iadd` lấy hai giá trị int, cộng chúng và đẩy kết quả lên stack.
4. `ireturn` trả kết quả kiểu int về cho nơi gọi method.

Các offset là vị trí bytecode trong method. Compiler có thể sinh chuỗi lệnh khác khi mã nguồn hoặc phiên bản compiler thay đổi.

## 9. Xem descriptor, constant pool và class-file version

Có thể kết hợp các tùy chọn để điều tra sâu hơn:

```bash
javap -p -s -classpath out com.example.Calculator
javap -p -constants -classpath out com.example.Calculator
javap -v -classpath out com.example.Calculator
```

### 9.1. Descriptor

Với method `add(int, int)`, descriptor là:

```text
(II)I
```

Đọc từ trái sang phải:

- Dấu ngoặc mở đầu danh sách tham số.
- `I` là tham số int thứ nhất.
- `I` tiếp theo là tham số int thứ hai.
- `I` sau dấu ngoặc đóng là kiểu trả về int.

Một số descriptor phổ biến:

| Descriptor | Ý nghĩa |
|---|---|
| `V` | void |
| `Z` | boolean |
| `I` | int |
| `J` | long |
| `D` | double |
| `Ljava/lang/String;` | java.lang.String |
| `[I` | int array |
| `([Ljava/lang/String;)V` | Nhận String array và trả về void |

### 9.2. Constant pool

Trong kết quả verbose, phần `Constant pool` liệt kê các hằng số và symbolic reference mà class sử dụng.

Có thể gặp các mục như:

- `Utf8`: chuỗi UTF-8 được class file sử dụng cho tên hoặc metadata.
- `Class`: tham chiếu tới class hoặc interface.
- `NameAndType`: kết hợp tên và descriptor.
- `Fieldref`: tham chiếu tới field.
- `Methodref` và `InterfaceMethodref`: tham chiếu tới method.
- `String`: tham chiếu tới chuỗi literal.
- `MethodHandle`, `MethodType` và `InvokeDynamic`: metadata liên quan tới cơ chế gọi động.

Constant pool giúp JVM và công cụ phân tích giải quyết các tham chiếu symbolic trong bytecode.

### 9.3. Class-file version

Trong kết quả `javap -v`, tìm các dòng:

```text
minor version: ...
major version: 61
```

Với ví dụ biên dịch bằng `--release 17`, major version là 61. Đây là phiên bản định dạng class file tương ứng Java 17.

Một số major version thường gặp:

| Java | Major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Nếu runtime quá cũ so với class-file version, ứng dụng có thể gặp `UnsupportedClassVersionError` khi nạp class.

## 10. Xem thông tin dòng mã và biến cục bộ

Vì ví dụ được biên dịch với `-g`, có thể kiểm tra thông tin debug:

```bash
javap -l -classpath out com.example.Calculator
```

`LineNumberTable` ánh xạ offset bytecode với số dòng trong mã nguồn. `LocalVariableTable` có thể lưu tên biến cục bộ, kiểu và khoảng offset mà biến có hiệu lực.

Nếu biên dịch lại không có debug metadata:

```bash
javac -g:none --release 17 -d out src/com/example/Calculator.java
javap -l -classpath out com.example.Calculator
```

kết quả có thể không còn các bảng debug đầy đủ. Tên tham số trong chữ ký method vẫn có thể hiển thị theo dạng kiểu dữ liệu, nhưng tên biến cục bộ không thể tự suy ra từ bytecode.

Muốn lưu tên tham số cho reflection, dùng tùy chọn compiler `-parameters`. Đây là metadata khác với thông tin debug do `-g` tạo ra.

## 11. Phân tích class nằm trong JAR

`javap` có thể đọc class trực tiếp từ JAR thông qua classpath. Ví dụ, sau khi đóng gói thư mục output:

```bash
jar --create --file app.jar --main-class com.example.Calculator -C out .
```

Xem cấu trúc class bên trong JAR:

```bash
javap -classpath app.jar com.example.Calculator
```

Xem bytecode của method:

```bash
javap -classpath app.jar -c com.example.Calculator
```

Nếu có nhiều JAR dependency, thêm chúng vào classpath theo dấu phân cách của hệ điều hành. Cần bảo đảm classpath trỏ tới đúng phiên bản artifact; nếu có nhiều JAR chứa cùng tên class, kết quả có thể phản ánh class được tìm thấy theo thứ tự tra cứu.

Với multi-release JAR, có thể chỉ định phiên bản entry cần xem bằng `--multi-release`. Điều này hữu ích khi JAR chứa các class thay thế theo từng phiên bản Java.

## 12. Phân tích class trong module

Với class thuộc module của JDK hoặc module path, `javap` có các tùy chọn module riêng.

Ví dụ, xem class `java.lang.String` trong module `java.base`:

```bash
javap --module java.base java.lang.String
```

Với module ứng dụng trên module path:

```bash
javap --module-path mods --module com.example.app com.example.Main
```

Trong đó:

- `--module-path mods` chỉ định vị trí chứa các module.
- `--module com.example.app` chọn module cần phân tích.
- `com.example.Main` là class được xem trong module đó.

Tùy chọn `--system` cho phép chỉ định vị trí chứa các system modules khi cần phân tích một runtime image cụ thể. Chỉ dùng các tùy chọn module khi class thực sự thuộc module tương ứng; classpath thông thường vẫn đủ cho các ứng dụng không dùng module.

## 13. javap khác gì các công cụ Java khác?

| Công cụ | Vai trò | Kết quả chính |
|---|---|---|
| `javac` | Biên dịch mã nguồn Java | Tệp class chứa bytecode |
| `java` | Khởi chạy ứng dụng | Thực thi chương trình trên JVM |
| `javap` | Đọc và phân tích class file | Chữ ký class, descriptor, bytecode và metadata |
| `jar` | Đóng gói hoặc liệt kê nội dung JAR | Artifact JAR |
| `jdeps` | Phân tích phụ thuộc class và module | Báo cáo dependency |

Cần phân biệt `javap` với decompiler:

- `javap` hiển thị chữ ký, metadata và lệnh bytecode.
- Decompiler cố gắng chuyển bytecode thành mã Java gần với mã nguồn.
- Không công cụ nào có thể khôi phục đầy đủ comment, định dạng, tên biến đã bị loại bỏ hoặc mọi quyết định ban đầu của lập trình viên chỉ từ class file.

Nếu mục tiêu là hiểu một phép tính được compiler chuyển thành lệnh gì, hãy dùng `javap -c`. Nếu cần kiểm tra cấu trúc class file, dùng `javap -v`. Nếu cần phân tích dependency của một ứng dụng lớn, `jdeps` phù hợp hơn.

## 14. Lỗi thường gặp khi sử dụng javap

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Error: class not found` | Classpath thiếu thư mục gốc hoặc JAR chứa class | Kiểm tra `-classpath` và tên package đầy đủ |
| Không thấy field hoặc method private | Đang dùng mức truy cập mặc định | Thêm `-p` hoặc `-private` |
| Không thấy bytecode | Chưa dùng tùy chọn disassemble | Thêm `-c` |
| Không thấy descriptor | Chưa yêu cầu signature | Dùng `-s` |
| Kết quả verbose quá dài | Dùng `-v` trong khi chỉ cần một phần thông tin | Chuyển sang `-c`, `-s` hoặc `-l` |
| Không có tên biến cục bộ | Class file không chứa LocalVariableTable | Biên dịch với `-g` rồi kiểm tra lại |
| Đọc nhầm phiên bản class | Classpath có nhiều bản JAR hoặc class trùng tên | Thu hẹp classpath và xác định artifact cụ thể |
| Không xem được class trong module | Chỉ định sai module path hoặc module name | Kiểm tra `--module-path` và `--module` |
| Không tìm thấy class trong JAR | Dùng sai package hoặc JAR không chứa class đó | Kiểm tra nội dung JAR bằng `jar --list` |

Một số lệnh chẩn đoán nhanh:

```bash
javap -help
javap -version
javap -classpath out -p com.example.Calculator
javap -classpath out -c com.example.Calculator
javap -classpath out -v com.example.Calculator
```

## 15. Quy trình sử dụng javap trong công việc

Khi cần phân tích một class cụ thể, có thể làm theo trình tự:

1. Xác định class file hoặc artifact JAR cần kiểm tra.
2. Xác định package và đường dẫn classpath chính xác.
3. Chạy chế độ mặc định để xem chữ ký và thành viên public/protected/package.
4. Thêm `-p` nếu cần kiểm tra private member.
5. Thêm `-c` để xem bytecode của method cần điều tra.
6. Thêm `-s` để xem descriptor khi phân tích overload hoặc tương thích chữ ký.
7. Dùng `-v` khi cần constant pool, class-file version, flags và attributes.
8. Dùng `-l` khi cần ánh xạ bytecode với số dòng hoặc biến cục bộ.
9. Nếu class đến từ JAR hoặc module, xác minh đúng artifact và đúng phiên bản.
10. Đối chiếu kết quả với mã nguồn, cấu hình compiler và runtime đang sử dụng.

Không nên bắt đầu bằng verbose output cho mọi trường hợp. Chọn tùy chọn nhỏ nhất đủ trả lời câu hỏi giúp kết quả dễ đọc và tránh bỏ sót phần quan trọng.

## 16. Tổng kết

`javap` là công cụ JDK để kiểm tra nội dung class file đã biên dịch. Nó giúp lập trình viên nhìn thấy cấu trúc và bytecode mà mã nguồn Java tạo ra.

Những tùy chọn cần nhớ:

- `javap className` xem chữ ký class và các thành viên theo phạm vi mặc định.
- `-p` hiển thị cả private member.
- `-c` hiển thị bytecode của method và constructor.
- `-s` hiển thị descriptor nội bộ.
- `-v` hiển thị constant pool, class-file version và attributes.
- `-l` hiển thị debug tables nếu class file có metadata.
- `-constants` hiển thị giá trị các constant field phù hợp.
- `-classpath` hoặc `-cp` giúp tìm class trong thư mục và JAR.
- `--module` và `--module-path` dùng khi phân tích class thuộc module.

Kết hợp `javap` với `javac`, `java` và `jar` giúp theo dõi đường đi từ mã nguồn đến class file và kiểm tra chính xác nội dung compiler đã tạo ra.
