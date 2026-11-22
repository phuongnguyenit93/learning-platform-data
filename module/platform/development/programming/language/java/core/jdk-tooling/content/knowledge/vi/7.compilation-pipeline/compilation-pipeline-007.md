# Kiểm tra bytecode Java

Sau khi biên dịch mã nguồn Java, trình biên dịch `javac` tạo ra các tệp `.class` chứa **bytecode**. Bytecode là tập lệnh trung gian mà Java Virtual Machine (JVM) đọc, kiểm tra và thực thi. Kiểm tra bytecode giúp hiểu trình biên dịch đã chuyển mã nguồn thành gì, xác định phiên bản class file, xem lời gọi phương thức và hằng số, cũng như chẩn đoán lỗi tương thích giữa các phiên bản Java.

Công cụ dòng lệnh chính để đọc cấu trúc và giải mã bytecode là **`javap`**, được cung cấp trong JDK.

## 1. Bytecode là gì?

Bytecode Java là tập lệnh trung gian được lưu trong tệp class. Nó được thiết kế để JVM có thể thực thi trên nhiều hệ điều hành và kiến trúc phần cứng.

Quy trình tổng quát:

1. Lập trình viên viết mã nguồn trong tệp `.java`.
2. `javac` kiểm tra mã nguồn và biên dịch thành bytecode.
3. Bytecode được lưu trong tệp `.class`.
4. JVM nạp class, kiểm tra tính hợp lệ và thực thi bytecode.
5. JVM có thể thông dịch lệnh hoặc biên dịch các đoạn mã thường chạy thành mã máy bằng JIT (Just-In-Time Compiler).

Ví dụ:

```text
BytecodeDemo.java
       |
       | javac
       v
BytecodeDemo.class
       |
       | JVM: load, verify, execute
       v
Kết quả chương trình
```

Bytecode không phải mã máy dành riêng cho CPU. Một tệp `.class` thường có thể chạy trên các nền tảng khác nhau nếu JVM tương thích được cài đặt và các dependency cần thiết có mặt.

## 2. Tạo tệp class để kiểm tra

Tạo tệp **`BytecodeDemo.java`**:

```java
public class BytecodeDemo {
    public static int add(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) {
        int result = add(7, 5);
        System.out.println("result=" + result);
    }
}
```

Biên dịch vào thư mục `out`:

```bash
javac -g -d out BytecodeDemo.java
```

Giải thích:

- `-g` yêu cầu compiler tạo thông tin debug như số dòng và thông tin biến cục bộ.
- `-d out` đặt thư mục gốc cho các tệp class đầu ra.
- `BytecodeDemo.java` là mã nguồn được biên dịch.

Sau khi biên dịch, cấu trúc thư mục:

```text
project/
  BytecodeDemo.java
  out/
    BytecodeDemo.class
```

Vì lớp không khai báo package, `BytecodeDemo.class` nằm trực tiếp trong `out`.

## 3. javap là gì?

`javap` là công cụ disassembler đi kèm JDK. Công cụ này đọc tệp class và hiển thị thông tin về lớp, phương thức, trường, chữ ký và bytecode.

Kiểm tra công cụ:

```bash
javap -help
```

Nếu terminal không nhận diện `javap`, hãy kiểm tra JDK đã được cài đặt và thư mục `bin` của JDK có trong `PATH`. `javap` thường không có trong một runtime-only package.

Để xem các khai báo public của lớp:

```bash
javap -classpath out BytecodeDemo
```

Kết quả rút gọn:

```text
Compiled from "BytecodeDemo.java"
public class BytecodeDemo {
  public BytecodeDemo();
  public static int add(int, int);
  public static void main(java.lang.String[]);
}
```

Đây là dạng hiển thị chữ ký lớp và phương thức. Nó chưa hiển thị các lệnh bytecode bên trong từng phương thức.

## 4. Xem bytecode bằng tùy chọn -c

Tùy chọn `-c` yêu cầu `javap` disassemble phần bytecode của các phương thức.

Chạy:

```bash
javap -classpath out -c BytecodeDemo
```

Trong kết quả, tìm phương thức:

```text
public static int add(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
```

Đây là chuỗi lệnh điển hình mà `javac` tạo cho phương thức `add` trong ví dụ:

| Lệnh | Ý nghĩa |
| --- | --- |
| `iload_0` | Đưa biến nguyên ở local variable slot 0 lên operand stack |
| `iload_1` | Đưa biến nguyên ở local variable slot 1 lên operand stack |
| `iadd` | Lấy hai giá trị int trên stack, cộng chúng và đẩy kết quả trở lại stack |
| `ireturn` | Trả về giá trị int ở đỉnh stack |

Các chỉ số trước dấu hai chấm như `0`, `1`, `2`, `3` là bytecode offset trong phần mã của phương thức, không phải số dòng trong mã nguồn.

Tên lệnh bắt đầu bằng chữ chỉ kiểu dữ liệu trong nhiều trường hợp:

- `i`: thao tác với `int`.
- `l`: thao tác với `long`.
- `f`: thao tác với `float`.
- `d`: thao tác với `double`.
- `a`: tham chiếu đối tượng (reference).

Một số lệnh thường gặp:

| Lệnh | Ý nghĩa |
| --- | --- |
| `bipush` | Đẩy một hằng số byte có dấu lên stack |
| `iconst_0`, `iconst_1` | Đẩy hằng số int nhỏ lên stack |
| `iload`, `istore` | Đọc/ghi biến int trong local variable array |
| `aload`, `astore` | Đọc/ghi biến tham chiếu |
| `iadd`, `isub`, `imul`, `idiv` | Cộng, trừ, nhân, chia số nguyên |
| `getstatic`, `putstatic` | Đọc/ghi trường static |
| `getfield`, `putfield` | Đọc/ghi trường của đối tượng |
| `invokevirtual` | Gọi phương thức instance theo cơ chế virtual dispatch |
| `invokestatic` | Gọi phương thức static |
| `invokespecial` | Gọi constructor hoặc một số phương thức đặc biệt |
| `invokeinterface` | Gọi phương thức qua interface |
| `ireturn`, `areturn`, `return` | Trả về int, reference hoặc kết thúc phương thức void |

Bytecode là dạng lệnh dựa trên stack. Khi đọc một đoạn disassembly, hãy theo dõi giá trị được đẩy lên stack, lấy ra khỏi stack và lưu vào local variable để hiểu luồng thực thi.

Các lệnh của phương thức `main` có thể khác nhau giữa các phiên bản JDK và compiler. Ví dụ, nối chuỗi có thể được biên dịch thành `invokedynamic` trên JDK hiện đại. Vì vậy, hãy xem output thực tế của JDK đang sử dụng thay vì yêu cầu toàn bộ disassembly phải giống hệt một bản mẫu.

## 5. Xem cấu trúc class file với -verbose

Tùy chọn `-verbose` (viết tắt `-v`) hiển thị thông tin chi tiết của class file.

Chạy:

```bash
javap -classpath out -verbose BytecodeDemo
```

Thông tin thường gồm:

- Phiên bản class file (minor version và major version).
- Access flags của lớp.
- Tên lớp hiện tại và lớp cha.
- Constant pool.
- Interface, field và method.
- Thuộc tính của class và method.
- Code attribute, bytecode và exception table.
- Thông tin debug nếu class được biên dịch kèm các thuộc tính đó.

### Constant pool

Constant pool là bảng chứa các hằng số và tham chiếu được class file sử dụng. Các mục thường gặp gồm:

- Chuỗi UTF-8 dùng cho tên lớp, tên phương thức, descriptor và literal.
- Thông tin lớp và interface.
- Tham chiếu trường và phương thức.
- Số nguyên, số thực và chuỗi literal.
- Name-and-type và các tham chiếu phục vụ liên kết.

Ví dụ, lời gọi `System.out.println(...)` cần các tham chiếu đến lớp `java/lang/System`, trường `out` và phương thức `println`. Những thông tin liên quan có thể được quan sát trong constant pool và bytecode.

Constant pool không phải danh sách tất cả đối tượng đang tồn tại trong heap. Nó là cấu trúc dữ liệu của class file phục vụ việc mô tả hằng số và tham chiếu.

## 6. Kiểm tra phiên bản class file

Trong kết quả `javap -verbose`, tìm các dòng tương tự:

```text
minor version: 0
major version: 61
```

`major version` xác định phiên bản định dạng class file. Một số giá trị thường gặp:

| Phiên bản Java | Major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Ví dụ, major version 61 tương ứng với Java 17. Runtime phải hỗ trợ phiên bản class file đó mới có thể nạp lớp theo cách thông thường.

Nếu biên dịch bằng JDK mới rồi chạy trên runtime quá cũ, có thể gặp lỗi:

```text
UnsupportedClassVersionError
```

Với JDK 9 trở lên, có thể dùng `--release` để biên dịch theo phiên bản nền tảng mục tiêu được hỗ trợ:

```bash
javac --release 17 -d out17 BytecodeDemo.java
```

Khi đó, class file được tạo hướng tới nền tảng Java 17 và API Java tiêu chuẩn tương ứng. `--release` giúp kiểm soát tương thích ở cấp ngôn ngữ, bytecode và API tiêu chuẩn; nó không tự bảo đảm mọi thư viện bên ngoài hoặc mã native đều tương thích.

## 7. Xem access flags, descriptor và thành viên private

Một số tùy chọn hữu ích khác:

| Tùy chọn | Công dụng |
| --- | --- |
| `-p` hoặc `-private` | Hiển thị cả thành viên private |
| `-s` | Hiển thị internal type signature/descriptor |
| `-l` | Hiển thị line number table và local variable table nếu có |
| `-constants` | Hiển thị giá trị hằng số static final phù hợp |
| `-v` | Hiển thị thông tin chi tiết class file |

Ví dụ:

```bash
javap -classpath out -p -s BytecodeDemo
```

Tùy chọn `-p` hữu ích khi cần xem các phương thức hoặc trường không public. Tùy chọn `-s` hiển thị descriptor của thành viên, ví dụ descriptor của phương thức nhận hai `int` và trả về `int` là:

```text
(II)I
```

Trong descriptor:

- `I` biểu diễn kiểu `int`.
- `V` biểu diễn kiểu `void`.
- `L...;` biểu diễn kiểu tham chiếu.
- `[` biểu diễn mảng.

Ví dụ, descriptor `([Ljava/lang/String;)V` tương ứng phương thức nhận một mảng `String` và không trả về giá trị.

## 8. Xem thông tin debug và ánh xạ về mã nguồn

Khi biên dịch với tùy chọn `-g`, compiler có thể lưu thêm các thuộc tính debug như:

- `LineNumberTable`: ánh xạ bytecode offset về số dòng mã nguồn.
- `LocalVariableTable`: tên biến cục bộ, kiểu và phạm vi tồn tại trong bytecode.
- `SourceFile`: tên tệp nguồn liên quan.

Kiểm tra bằng:

```bash
javap -classpath out -l BytecodeDemo
```

Hoặc kết hợp nhiều tùy chọn:

```bash
javap -classpath out -c -l -p BytecodeDemo
```

Nếu không có thông tin debug tương ứng, `javap -l` có thể không hiển thị các bảng này. Có thể biên dịch lại với `javac -g` để yêu cầu tạo thông tin debug.

Tên biến cục bộ không phải lúc nào cũng được lưu trong class file. Vì vậy, khi kiểm tra một class được build ở chế độ tối ưu kích thước hoặc không có debug info, bạn có thể chỉ thấy slot và kiểu dữ liệu thay vì tên biến ban đầu.

## 9. Kiểm tra quá trình xác minh bytecode của JVM

Khi JVM nạp một lớp, nó kiểm tra class file và bytecode để bảo đảm cấu trúc và các quy tắc an toàn kiểu được đáp ứng trước khi thực thi.

Bytecode verifier thực hiện các kiểm tra như:

- Cấu trúc class file và định dạng lệnh hợp lệ.
- Kiểu dữ liệu trên operand stack tại các điểm trong luồng điều khiển.
- Cách sử dụng local variable.
- Tính nhất quán của kiểu tại các nhánh và điểm hợp nhất luồng điều khiển.
- Quy tắc truy cập và các ràng buộc của JVM.

Có thể yêu cầu JVM xác minh lớp trong chế độ đầy đủ khi chạy:

```bash
java -Xverify:all -cp out BytecodeDemo
```

Kết quả chương trình:

```text
result=12
```

`-Xverify:all` yêu cầu JVM xác minh tất cả các lớp liên quan theo chế độ xác minh đầy đủ. Đây là tùy chọn chẩn đoán hữu ích khi điều tra vấn đề bytecode hoặc class loading; nó không thay thế kiểm thử chức năng.

Xác minh bytecode chỉ kiểm tra các quy tắc của JVM và tính nhất quán cấu trúc. Nó không chứng minh thuật toán của chương trình đúng về mặt nghiệp vụ, không phát hiện mọi lỗi logic và không đảm bảo ứng dụng không có lỗ hổng bảo mật.

## 10. Phân biệt bytecode với mã máy do JIT tạo ra

Bytecode nằm trong tệp `.class` và là đầu vào của JVM. Trong lúc chạy, JVM có thể:

- Thông dịch bytecode.
- Thu thập thông tin profiling về hành vi thực thi.
- Dùng JIT compiler để chuyển các đoạn mã thường chạy thành mã máy phù hợp với CPU.
- Tối ưu hóa dựa trên thông tin runtime và có thể hủy tối ưu hóa (deoptimization) khi giả định tối ưu không còn đúng.

Vì vậy, kết quả `javap -c` cho thấy bytecode được lưu trong class file, không phải mã máy cuối cùng CPU đang thực thi sau tối ưu JIT.

Không nên suy luận hiệu năng thực tế chỉ từ số lượng lệnh bytecode. Hiệu năng còn phụ thuộc JIT, dữ liệu đầu vào, GC, hệ điều hành, CPU, thư viện và cách benchmark.

## 11. Một số lệnh javap thường dùng

Giả sử class file nằm trong thư mục `out`:

| Mục đích | Lệnh |
| --- | --- |
| Xem chữ ký lớp | `javap -classpath out BytecodeDemo` |
| Xem bytecode | `javap -classpath out -c BytecodeDemo` |
| Xem chi tiết class file | `javap -classpath out -v BytecodeDemo` |
| Xem cả thành viên private | `javap -classpath out -p BytecodeDemo` |
| Xem descriptor | `javap -classpath out -s BytecodeDemo` |
| Xem thông tin debug | `javap -classpath out -l BytecodeDemo` |
| Kết hợp bytecode và debug info | `javap -classpath out -c -l -p BytecodeDemo` |

Nếu lớp thuộc package, hãy dùng tên đầy đủ, ví dụ `com.example.BytecodeDemo`, và đặt classpath tại thư mục gốc chứa thư mục `com`.

Có thể kiểm tra class nằm trong JAR bằng cách thêm JAR vào classpath:

```bash
javap -classpath lib/example.jar -c com.example.Tool
```

Nếu có nhiều vị trí chứa dependency, truyền danh sách classpath với dấu phân cách phù hợp:

- Windows: dấu chấm phẩy `;`.
- macOS/Linux: dấu hai chấm `:`.

## 12. Lỗi thường gặp khi kiểm tra bytecode

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `javap` không được nhận diện | Chưa cài JDK hoặc thư mục `bin` chưa nằm trong `PATH` | Cài JDK và kiểm tra `PATH` |
| `Class not found` khi gọi javap | Sai classpath hoặc tên lớp không đầy đủ | Đặt classpath ở thư mục gốc và dùng tên package đầy đủ |
| Không thấy bytecode | Chưa thêm tùy chọn `-c` | Chạy `javap -c` |
| Không thấy tên biến cục bộ | Class không có `LocalVariableTable` | Biên dịch với `javac -g` rồi kiểm tra lại |
| Runtime báo `UnsupportedClassVersionError` | Runtime không hỗ trợ major version của class file | Nâng runtime hoặc biên dịch với `--release` phù hợp |
| Bytecode không giống ví dụ | Khác JDK/compiler, tùy chọn biên dịch hoặc tối ưu hóa | Dựa vào output thực tế; chỉ so sánh ý nghĩa lệnh và luồng thực thi |
| Lớp phụ thuộc không được tìm thấy | Thiếu JAR hoặc thư mục dependency trong classpath | Bổ sung dependency khi chạy và kiểm tra classpath |

## 13. Quy trình kiểm tra bytecode đề xuất

Khi cần điều tra một tệp class:

1. Biên dịch mã nguồn bằng đúng JDK và giữ lại tệp `.class`.
2. Dùng `javap -classpath ... -c` để xem các lệnh bytecode.
3. Dùng `javap -verbose` để xem major version, constant pool, access flags và các attribute.
4. Dùng `javap -p -s` để kiểm tra thành viên private và descriptor.
5. Dùng `javap -l` nếu cần ánh xạ bytecode về số dòng hoặc tên biến.
6. Dùng `java -Xverify:all` khi cần kiểm tra quá trình xác minh của JVM.
7. Đối chiếu classpath, phiên bản runtime và dependency nếu lớp không nạp được.

Giữ lại mã nguồn, lệnh biên dịch và phiên bản JDK giúp kết quả kiểm tra có thể tái lập. Với dự án build tự động, nên lưu thông tin phiên bản compiler và cấu hình build cùng artifact để thuận tiện điều tra.

## 14. Ghi nhớ

- `.java` là mã nguồn; `.class` chứa bytecode và metadata của lớp.
- `javap -c` dùng để đọc bytecode của phương thức.
- `javap -v` hiển thị cấu trúc class file, constant pool và major version.
- `javap -p`, `-s`, `-l` lần lượt giúp xem thành viên private, descriptor và thông tin debug.
- JVM verifier kiểm tra tính hợp lệ của bytecode trước khi thực thi; `-Xverify:all` yêu cầu chế độ xác minh đầy đủ.
- Bytecode khác mã máy mà JIT có thể tạo ra khi ứng dụng đang chạy.
- Major version của class file phải được runtime hỗ trợ.

Biết dùng `javap` giúp lập trình viên nhìn sâu hơn vào kết quả biên dịch, hiểu cách Java biểu diễn lệnh và dữ liệu, đồng thời chẩn đoán lỗi tương thích giữa compiler, class file và JVM.
