# Sinh bytecode trong Java

## 1. Sinh bytecode là gì?

**Sinh bytecode** là bước trong quá trình biên dịch Java, nơi compiler chuyển mã nguồn `.java` thành các tệp class (`.class`) chứa lệnh của máy ảo Java (Java Virtual Machine, JVM).

Bytecode là dạng mã trung gian độc lập với kiến trúc CPU. JVM trên từng nền tảng đọc class file, kiểm tra tính hợp lệ và thực thi các lệnh bytecode. Tùy JVM và cách chạy, mã có thể được diễn giải hoặc được biên dịch JIT thành mã máy để tăng hiệu năng.

Luồng tổng quát:

```text
Mã nguồn .java
      |
      v
Phân tích cú pháp và kiểm tra kiểu
      |
      v
Biểu diễn trung gian của compiler
      |
      v
Sinh bytecode và class file
      |
      v
Tệp .class
      |
      v
Class loader và bytecode verifier
      |
      v
JVM thực thi / JIT biên dịch mã nóng
```

Trong JDK, công cụ chính để thực hiện bước biên dịch và sinh bytecode là `javac`. Công cụ `javap` giúp xem cấu trúc class file và các lệnh bytecode đã được sinh ra.

## 2. Bytecode khác mã nguồn và mã máy như thế nào?

Ba dạng mã có vai trò khác nhau:

| Dạng mã | Nội dung | Thành phần sử dụng |
|---|---|---|
| Mã nguồn Java (`.java`) | Cú pháp Java mà lập trình viên viết | Compiler như `javac` |
| Bytecode (`.class`) | Lệnh và metadata theo định dạng class file của JVM | JVM và các công cụ phân tích bytecode |
| Mã máy (native machine code) | Lệnh dành cho kiến trúc CPU cụ thể | CPU của máy đang chạy |

Ví dụ, câu lệnh:

```java
int total = left + right;
```

có thể được chuyển thành một số lệnh bytecode để đọc hai biến, cộng chúng trên operand stack và trả kết quả.

Bytecode không phải mã máy x86-64 hay ARM64. Vì vậy, một class file có thể chạy trên nhiều hệ điều hành và kiến trúc CPU nếu có JVM tương thích với phiên bản class file đó và ứng dụng không phụ thuộc vào thành phần đặc thù của một nền tảng.

`javac` thông thường sinh bytecode, không sinh trực tiếp mã máy native cho CPU. Việc JIT biên dịch bytecode thành mã máy diễn ra trong JVM khi ứng dụng chạy. Đây là hai giai đoạn khác nhau.

## 3. Các bước chính từ mã nguồn đến bytecode

Có thể mô tả quy trình biên dịch của `javac` theo các bước khái niệm sau. Chi tiết nội bộ và thứ tự triển khai có thể thay đổi giữa các phiên bản compiler, nhưng các nhiệm vụ chính vẫn tương tự.

### 3.1. Đọc mã nguồn và phân tích từ vựng

Compiler đọc nội dung tệp `.java`, nhận diện các token như:

- Từ khóa: `class`, `public`, `static`, `return`, `if`.
- Tên định danh: tên class, method, biến và package.
- Literal: `10`, `"hello"`, `true`.
- Toán tử và dấu phân cách: `+`, `=`, `{`, `}`, `;`.

Ví dụ:

```java
int result = left + right;
```

được nhận diện thành các token tương ứng với kiểu `int`, tên biến `result`, dấu gán, các toán hạng, phép cộng và dấu kết thúc câu lệnh.

### 3.2. Phân tích cú pháp và tạo AST

Parser kiểm tra xem chuỗi token có tuân theo ngữ pháp Java hay không, sau đó tạo cây cú pháp trừu tượng (Abstract Syntax Tree, AST).

AST biểu diễn cấu trúc chương trình: khai báo class, field, method, câu lệnh, biểu thức, điều kiện và lời gọi phương thức.

Ví dụ, biểu thức `left + right` được biểu diễn như một nút phép cộng có hai nút con tương ứng với hai biến. Compiler có thể xử lý cấu trúc này mà không cần dựa vào cách xuống dòng hay khoảng trắng trong mã nguồn.

Nếu thiếu dấu `;`, ngoặc không cân bằng hoặc cú pháp không hợp lệ, compiler phát sinh lỗi cú pháp và không thể tạo class file hợp lệ cho phần mã bị lỗi.

### 3.3. Phân giải tên và kiểm tra kiểu

Compiler phân giải các tên được sử dụng trong mã nguồn và kiểm tra chúng có hợp lệ trong ngữ cảnh hay không.

Các công việc thường gồm:

- Tìm khai báo của class, method, field và biến.
- Kiểm tra phạm vi truy cập và phạm vi tồn tại của tên.
- Chọn overload phù hợp cho lời gọi phương thức.
- Kiểm tra kiểu của biểu thức và phép gán.
- Kiểm tra kiểu trả về của method.
- Kiểm tra các quy tắc như `final`, generic và checked exception.

Ví dụ:

```java
int count = "five";
```

không hợp lệ vì một giá trị `String` không thể gán trực tiếp cho biến kiểu `int`. Compiler báo lỗi kiểu và không sinh class file hợp lệ cho mã nguồn đó.

### 3.4. Annotation processing và các bước chuyển đổi

Nếu dự án có annotation processor, compiler có thể chạy các processor để phân tích annotation và sinh thêm mã nguồn hoặc tài nguyên. Các mã nguồn được sinh có thể tiếp tục được biên dịch trong cùng quy trình.

Sau đó, compiler thực hiện các bước chuyển đổi nội bộ (thường được gọi là lowering hoặc desugaring) để chuyển một số cấu trúc Java cấp cao thành dạng phù hợp hơn với bytecode.

Ví dụ, một số cấu trúc cú pháp có thể được biểu diễn bằng lời gọi method, nhánh điều khiển hoặc phương thức tổng hợp (synthetic methods) trong class file. Lambda và method reference trong các bản Java hiện đại thường được triển khai thông qua cơ chế `invokedynamic` cùng các thành phần runtime tương ứng.

### 3.5. Sinh bytecode và ghi class file

Ở giai đoạn code generation, compiler tạo các lệnh bytecode cho method, constructor và các thành phần cần thiết, sau đó ghi chúng vào class file.

Mỗi class, interface, enum hoặc record được biên dịch thường tạo một class file riêng. Class lồng nhau, class nội bộ hoặc class ẩn danh cũng có thể tạo thêm class file. Tài nguyên như ảnh, cấu hình hoặc tệp văn bản được đóng gói cùng JAR nhưng bản thân chúng không phải bytecode Java.

## 4. Bytecode là tập lệnh dạng stack-based

JVM sử dụng mô hình thực thi dựa trên operand stack kết hợp với local variable array cho mỗi frame của method.

Khi thực hiện một method:

- Các biến cục bộ và tham số được lưu trong vùng local variables.
- Các lệnh bytecode lấy toán hạng từ operand stack.
- Lệnh tính toán thường lấy giá trị khỏi stack, xử lý rồi đẩy kết quả trở lại stack.
- Lệnh gọi method tạo frame mới cho lời gọi.
- Lệnh trả về đưa kết quả về frame của caller hoặc kết thúc method.

Ví dụ, phép cộng hai số nguyên có thể dùng các lệnh:

```text
iload_0
iload_1
iadd
ireturn
```

Ý nghĩa:

| Lệnh | Tác dụng |
|---|---|
| `iload_0` | Đưa biến local ở vị trí 0 (kiểu int) lên operand stack |
| `iload_1` | Đưa biến local ở vị trí 1 lên operand stack |
| `iadd` | Lấy hai giá trị int trên stack, cộng và đẩy tổng trở lại |
| `ireturn` | Trả về giá trị int từ method |

Các lệnh có tiền tố `i` thường liên quan đến kiểu `int`; `l` dùng cho `long`; `f` cho `float`; `d` cho `double`; `a` cho tham chiếu object. Đây là quy ước thường thấy trong tên lệnh bytecode.

## 5. Cấu trúc của một Java class file

Tệp `.class` là một định dạng nhị phân có cấu trúc được đặc tả. Nó không chỉ chứa các lệnh bytecode mà còn có metadata để JVM nạp, liên kết, xác minh và thực thi class.

Các phần chính gồm:

1. **Magic number:** bốn byte đầu có giá trị `CAFEBABE`, dùng để nhận diện class file.
2. **Minor version và major version:** phiên bản định dạng class file.
3. **Constant pool:** bảng hằng số và tham chiếu symbolic như tên class, tên method, descriptor, chuỗi và số.
4. **Access flags:** thông tin modifier như `public`, `final`, `interface`, `abstract`.
5. **This class và super class:** class hiện tại và class cha.
6. **Interfaces:** các interface được triển khai.
7. **Fields:** khai báo field và metadata liên quan.
8. **Methods:** tên, descriptor, access flags và các thuộc tính của method.
9. **Attributes:** metadata bổ sung ở cấp class, field, method hoặc Code.

### 5.1. Constant pool

Constant pool lưu các thông tin mà bytecode tham chiếu tới, ví dụ:

- Tên class và interface.
- Tên method và field.
- Method descriptor và field descriptor.
- Chuỗi literal.
- Số nguyên, số thực và các hằng số khác.
- Method handle, method type và dynamic call site.

Bytecode thường tham chiếu tới mục trong constant pool bằng chỉ số thay vì nhúng toàn bộ tên class hoặc chữ ký method vào từng lệnh.

Ví dụ, lệnh `invokestatic` có thể tham chiếu tới một mục constant pool mô tả class sở hữu method, tên method và descriptor của nó.

### 5.2. Code attribute của method

Method có phần thân thực thi thường chứa thuộc tính `Code`. Thuộc tính này bao gồm:

- `max_stack`: độ sâu tối đa của operand stack cần cho method.
- `max_locals`: số slot local variable cần thiết.
- `code`: mảng byte chứa các lệnh bytecode.
- Exception table: phạm vi bảo vệ và đích xử lý exception.
- Các thuộc tính bổ sung như `LineNumberTable`, `LocalVariableTable` và `StackMapTable` khi có.

Method abstract hoặc native không có phần bytecode `Code` như method thông thường vì phần thực thi được cung cấp theo cơ chế khác.

### 5.3. Descriptor của field và method

Descriptor mô tả kiểu dữ liệu trong class file. Ví dụ:

| Descriptor | Ý nghĩa |
|---|---|
| `I` | `int` |
| `J` | `long` |
| `Z` | `boolean` |
| `Ljava/lang/String;` | Tham chiếu tới `java.lang.String` |
| `(II)I` | Method nhận hai `int`, trả về `int` |
| `([Ljava/lang/String;)V` | Method nhận mảng `String`, trả về `void` |

Descriptor là một phần quan trọng để JVM và công cụ phân tích nhận biết chữ ký method và field.

## 6. Các nhóm lệnh bytecode thường gặp

Bytecode có nhiều nhóm lệnh phục vụ các thao tác khác nhau.

| Nhóm | Ví dụ lệnh | Mục đích |
|---|---|---|
| Tải và lưu biến | `iload`, `aload`, `istore`, `astore` | Chuyển giá trị giữa local variables và operand stack |
| Hằng số | `iconst_0`, `bipush`, `ldc` | Đưa hằng số lên stack |
| Số học | `iadd`, `isub`, `imul`, `idiv` | Tính toán số học |
| So sánh và nhảy | `if_icmpge`, `ifeq`, `goto` | Điều khiển luồng thực thi |
| Tạo object và array | `new`, `newarray`, `anewarray` | Cấp phát object hoặc mảng |
| Truy cập field | `getfield`, `putfield`, `getstatic`, `putstatic` | Đọc hoặc ghi field |
| Gọi method | `invokevirtual`, `invokestatic`, `invokespecial`, `invokeinterface`, `invokedynamic` | Thực hiện lời gọi method |
| Trả về | `ireturn`, `areturn`, `return` | Kết thúc method và trả kết quả |
| Exception | `athrow` | Ném exception |
| Kiểm tra kiểu | `checkcast`, `instanceof` | Chuyển kiểu tham chiếu hoặc kiểm tra kiểu |

Không phải mọi dòng Java đều ánh xạ một-một sang một lệnh bytecode. Một biểu thức có thể tạo ra nhiều lệnh, và compiler có thể chọn chuỗi lệnh khác nhau miễn là giữ đúng ngữ nghĩa chương trình.

## 7. Ví dụ thực hành: biên dịch và xem bytecode bằng javap

Ví dụ sau dùng Java 17 trở lên. Tạo tệp `src/com/example/BytecodeDemo.java`:

```java
package com.example;

public class BytecodeDemo {
    public static int add(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) {
        int total = add(2, 3);
        System.out.println("total=" + total);
    }
}
```

Tạo thư mục đầu ra. Trong Linux/macOS:

```bash
mkdir -p out
```

Trong Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
```

Biên dịch từ thư mục gốc của dự án:

```bash
javac --release 17 -g -d out src/com/example/BytecodeDemo.java
```

Ý nghĩa:

- `--release 17`: biên dịch theo ngôn ngữ, bytecode và API công khai của Java 17.
- `-g`: yêu cầu tạo thông tin debug.
- `-d out`: ghi class file vào thư mục `out`, theo cấu trúc package.

Chạy chương trình:

```bash
java -cp out com.example.BytecodeDemo
```

Kết quả stdout chính xác:

```text
total=5
```

### 7.1. Xem các lệnh bytecode

Dùng `javap` với tùy chọn `-c`:

```bash
javap -classpath out -c -p com.example.BytecodeDemo
```

Phần method `add` có dạng bytecode:

```text
public static int add(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
```

Giải thích từng bước:

1. `iload_0` lấy tham số `left` từ local variable slot 0 và đẩy lên stack.
2. `iload_1` lấy tham số `right` từ slot 1 và đẩy lên stack.
3. `iadd` lấy hai giá trị int, cộng chúng và đẩy tổng lên stack.
4. `ireturn` lấy kết quả int và trả về cho method gọi `add`.

Các chỉ số constant pool và phần bytecode của method `main` có thể khác tùy phiên bản compiler và cách compiler biểu diễn các biểu thức khác. Đoạn trên minh họa phần phép cộng đơn giản.

### 7.2. Xem cấu trúc class file

Dùng chế độ verbose:

```bash
javap -classpath out -v com.example.BytecodeDemo
```

Kết quả hiển thị nhiều thông tin hơn, bao gồm:

- Major version và minor version.
- Constant pool.
- Access flags và class hierarchy.
- Descriptor của field và method.
- Code attribute, exception table và stack map frame.
- Debug attributes nếu được tạo khi biên dịch.

Vì dùng `--release 17`, class file được sinh có major version `61`. Có thể tìm dòng `major version: 61` trong kết quả.

### 7.3. Xem descriptor và thông tin debug

Một số tùy chọn hữu ích:

```bash
javap -classpath out -s com.example.BytecodeDemo
javap -classpath out -l com.example.BytecodeDemo
javap -classpath out -p com.example.BytecodeDemo
```

- `-s`: hiển thị descriptor nội bộ của field và method.
- `-l`: hiển thị thông tin debug về số dòng và biến cục bộ nếu class file có các thuộc tính đó.
- `-p`: hiển thị cả thành viên không public.

`javap` là công cụ đọc và phân tích class file. Nó không sửa bytecode và không thay thế compiler.

## 8. Chọn phiên bản bytecode bằng javac

Một class file có major version tương ứng với phiên bản JVM tối thiểu có thể hiểu định dạng đó.

Một số mốc thường gặp:

| Phiên bản Java mục tiêu | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Ví dụ, khi biên dịch với JDK 21 nhưng muốn tạo bytecode tương thích Java 17:

```bash
javac --release 17 -d out src/com/example/BytecodeDemo.java
```

`--release 17` đồng thời giới hạn ngôn ngữ, định dạng bytecode và API Java SE mà compiler cho phép sử dụng ở mức Java 17.

Không nên chỉ dùng `-target 17` mà bỏ qua việc kiểm soát API. Tùy chọn `-target` điều khiển phiên bản class file nhưng tự nó không bảo đảm mã nguồn chỉ gọi API có trong Java 17. `--release` là lựa chọn phù hợp hơn cho trường hợp biên dịch nhắm tới một release cụ thể.

Nếu một dependency được biên dịch cho Java 21 nhưng ứng dụng chạy trên Java 17, JVM 17 vẫn có thể từ chối nạp dependency đó dù mã nguồn ứng dụng đã được biên dịch với `--release 17`. Mọi class file cần nạp phải tương thích với runtime mục tiêu.

## 9. Bytecode verifier và quá trình thực thi

Sau khi class file được class loader nạp, JVM thực hiện các bước liên quan đến linking. Trong đó, verification kiểm tra class file đáp ứng các ràng buộc của JVM.

Verifier kiểm tra các yếu tố như:

- Cấu trúc class file và kiểu dữ liệu hợp lệ.
- Lệnh bytecode hợp lệ và không vi phạm ràng buộc kiểu.
- Operand stack được sử dụng đúng kiểu và đúng trạng thái.
- Nhánh điều khiển có trạng thái stack tương thích.
- Lời gọi method, truy cập field và các thao tác tham chiếu đáp ứng quy tắc tương ứng.

Các class file hiện đại thường chứa `StackMapTable` để cung cấp thông tin frame hỗ trợ quá trình verification tại các điểm điều khiển luồng.

Verification không chứng minh chương trình đúng về mặt nghiệp vụ. Nó không thể xác nhận thuật toán cộng tiền, phân quyền hoặc tính toán kết quả có đúng yêu cầu hay không. Nó chủ yếu kiểm tra tính hợp lệ và an toàn kiểu của bytecode theo quy tắc JVM.

Sau khi class được nạp và liên kết, JVM có thể diễn giải bytecode hoặc biên dịch các đoạn mã thường được thực thi thành mã máy bằng JIT. Cơ chế tối ưu và ngưỡng biên dịch phụ thuộc implementation của JVM.

## 10. Debug metadata và các tùy chọn biên dịch liên quan

Ngoài lệnh bytecode, class file có thể chứa metadata phục vụ debug và reflection.

### 10.1. Thông tin debug

Tùy chọn `-g` yêu cầu compiler tạo thông tin debug, thường bao gồm:

- Thông tin nguồn và số dòng.
- Thông tin biến cục bộ.
- Thông tin hỗ trợ debugger ánh xạ bytecode về mã nguồn.

Nếu không cần metadata debug, có thể dùng:

```bash
javac -g:none -d out src/com/example/BytecodeDemo.java
```

Khi thiếu thông tin debug, debugger và `javap -l` có thể không hiển thị đầy đủ tên biến hoặc ánh xạ dòng mã.

### 10.2. Lưu tên tham số cho reflection

Tên tham số trong mã nguồn không phải lúc nào cũng được lưu trong class file theo cách reflection có thể truy xuất.

Có thể yêu cầu compiler ghi metadata tên tham số bằng `-parameters`:

```bash
javac -parameters -d out src/com/example/BytecodeDemo.java
```

Khi đó, reflection có thể đọc tên tham số thông qua `java.lang.reflect.Parameter`, nếu class file chứa metadata tương ứng.

`-parameters` và `-g` phục vụ mục đích khác nhau: một tùy chọn lưu tên tham số cho reflection, tùy chọn kia tạo thông tin debug.

## 11. Lambda, method reference và các cấu trúc Java hiện đại

Một số cấu trúc Java cấp cao cần cách biểu diễn đặc biệt trong bytecode.

Ví dụ lambda:

```java
Runnable task = () -> System.out.println("running");
task.run();
```

Compiler thường dùng lệnh `invokedynamic` để liên kết lambda với cơ chế runtime, cùng các metadata và method handle cần thiết. Vì vậy, khi dùng `javap -c -v`, bạn có thể thấy `invokedynamic` và các mục liên quan trong constant pool.

Một số điểm cần nhớ:

- `invokedynamic` là lệnh bytecode dành cho cơ chế liên kết lời gọi động.
- Lambda không nhất thiết tạo một class file ẩn danh giống cách lập trình viên tự viết class.
- Cách biểu diễn cụ thể có thể thay đổi theo phiên bản compiler và JVM, trong khi hành vi Java mà chương trình yêu cầu vẫn được giữ.
- Không nên phụ thuộc vào tên method tổng hợp hoặc chỉ số constant pool để xây dựng logic ứng dụng.

Compiler cũng có thể tạo synthetic members để hỗ trợ các cấu trúc ngôn ngữ. Các thành phần này thường được nhận diện qua metadata hoặc cờ `ACC_SYNTHETIC` trong class file.

## 12. Lỗi thường gặp liên quan đến sinh bytecode

| Lỗi hoặc hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `';' expected` hoặc lỗi cú pháp | Mã nguồn không tuân theo ngữ pháp Java | Sửa cú pháp trước khi biên dịch lại |
| `incompatible types` | Kiểu dữ liệu không tương thích | Sửa kiểu, phép chuyển kiểu hoặc chữ ký method |
| `UnsupportedClassVersionError` | Runtime cũ hơn major version của class file | Dùng runtime mới hơn hoặc biên dịch với `--release` phù hợp |
| `ClassFormatError` | Class file sai định dạng hoặc bị hỏng | Build lại từ nguồn đáng tin cậy và kiểm tra artifact |
| `VerifyError` | Bytecode không vượt qua được kiểm tra của JVM | Xác định compiler, bytecode transformer, agent hoặc công cụ sinh class file gây ra lỗi |
| `NoSuchMethodError` | Class được biên dịch với chữ ký method không còn khớp lúc chạy | Kiểm tra phiên bản dependency và classpath runtime |
| `javap` không tìm thấy class | Sai classpath hoặc tên đầy đủ của class | Kiểm tra `-classpath`, thư mục output và package |
| Chạy nhầm class file cũ | Output directory còn artifact từ lần build trước | Dùng build sạch hoặc thư mục output mới |
| Debugger không hiển thị tên biến | Class file thiếu debug metadata cần thiết | Biên dịch lại với `-g` |

Không phải mọi lỗi runtime đều do sinh bytecode. Ví dụ, `NoSuchMethodError` thường liên quan đến sự không đồng nhất của classpath hoặc phiên bản thư viện khi liên kết. Cần kiểm tra nguyên nhân cụ thể trước khi thay đổi compiler options.

## 13. Quy trình kiểm tra bytecode trong một dự án

Khi cần hiểu compiler đã sinh gì từ mã nguồn:

1. Xác định JDK và phiên bản Java mục tiêu mà dự án yêu cầu.
2. Build từ mã nguồn bằng cấu hình release phù hợp.
3. Dùng một thư mục output sạch để tránh nhầm class file cũ.
4. Chạy chương trình hoặc test để xác nhận hành vi.
5. Dùng `javap -c` xem lệnh bytecode của method cần phân tích.
6. Dùng `javap -v` kiểm tra constant pool, class version và attributes.
7. Nếu cần debug, kiểm tra `LineNumberTable`, `LocalVariableTable` và tùy chọn `-g`.
8. Nếu cần reflection lấy tên tham số, kiểm tra việc biên dịch với `-parameters`.
9. Nếu class file không nạp được, kiểm tra major version, verifier error và dependency trước khi kết luận lỗi nằm ở compiler.

Các bước này giúp nối được ba phần: mã nguồn mà lập trình viên viết, bytecode compiler tạo ra và hành vi JVM quan sát được khi chạy.

## 14. Tổng kết

Sinh bytecode là bước chuyển mã nguồn Java thành class file theo định dạng JVM. Đây là kết quả trực tiếp của compiler `javac`, còn việc diễn giải hoặc JIT biên dịch bytecode thành mã máy xảy ra trong runtime.

Những điểm cần nhớ:

- `javac` phân tích cú pháp, kiểm tra kiểu, thực hiện các bước chuyển đổi và sinh class file.
- Bytecode là tập lệnh độc lập với CPU, được JVM thực thi.
- Class file chứa magic number, phiên bản, constant pool, field, method và attributes.
- JVM verifier kiểm tra tính hợp lệ và an toàn kiểu của bytecode.
- `javap -c` xem lệnh bytecode; `javap -v` xem cấu trúc chi tiết.
- `--release` giúp kiểm soát ngôn ngữ, bytecode và API Java mục tiêu.
- `-g` hỗ trợ debug; `-parameters` lưu tên tham số cho reflection.
- JIT biên dịch mã nóng thành mã máy trong runtime; đó không phải bước sinh bytecode của `javac`.

Hiểu quá trình sinh bytecode giúp lập trình viên đọc kết quả compiler, phân tích lỗi tương thích class file, kiểm tra hành vi method và hiểu rõ hơn cách mã Java được JVM thực thi.
