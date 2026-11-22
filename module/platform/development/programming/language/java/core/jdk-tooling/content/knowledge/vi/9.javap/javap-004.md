# Xem constant pool bằng javap

**Constant pool** là bảng hằng số và tham chiếu nằm trong class file của Java. Bảng này lưu những thông tin mà JVM cần để mô tả lớp và liên kết các thành phần của nó, chẳng hạn tên lớp, tên trường, tên phương thức, descriptor, chuỗi literal, giá trị số, method handle và các tham chiếu gọi động.

Công cụ `javap` đi kèm JDK có thể giải mã class file thành dạng văn bản. Để xem constant pool, tùy chọn quan trọng nhất là `-verbose` (viết tắt `-v`). Đây là cách thực tế để quan sát các mục constant pool và lần theo quan hệ giữa các chỉ mục mà không phải tự đọc dữ liệu nhị phân.

## 1. Constant pool nằm ở đâu trong class file?

Class file có cấu trúc tổng thể:

```text
ClassFile
├── magic
├── minor_version / major_version
├── constant_pool
├── access_flags
├── this_class / super_class
├── interfaces
├── fields
├── methods
└── attributes
```

Constant pool nằm sau phần phiên bản class file và trước các thông tin mô tả lớp. Các phần khác trong class file thường tham chiếu constant pool bằng chỉ mục thay vì lặp lại tên và descriptor.

Ví dụ, trường `this_class` không chứa trực tiếp chuỗi `com/example/Message`; nó chứa một chỉ mục đến mục `CONSTANT_Class_info`. Mục Class này lại trỏ đến một mục UTF-8 chứa tên nội bộ của lớp.

Vì vậy, khi đọc constant pool, cần hiểu hai điều:

- Một mục có thể chứa dữ liệu trực tiếp, ví dụ một số nguyên hoặc chuỗi UTF-8.
- Một mục khác có thể chứa chỉ mục trỏ đến mục khác trong cùng constant pool.

Constant pool không phải danh sách đơn giản các literal xuất hiện trong mã nguồn. Nó còn chứa cấu trúc tham chiếu cần cho quá trình liên kết và thực thi.

## 2. Lệnh javap để xem constant pool

Giả sử class file nằm trong thư mục `out` và tên lớp đầy đủ là `com.example.Message`. Chạy:

```sh
javap -verbose -classpath out com.example.Message
```

Có thể viết ngắn:

```sh
javap -v -cp out com.example.Message
```

Ý nghĩa:

- `javap`: công cụ phân tích class file.
- `-verbose` hoặc `-v`: hiển thị thông tin chi tiết, bao gồm constant pool và attributes.
- `-classpath out` hoặc `-cp out`: chỉ định thư mục gốc để tìm lớp.
- `com.example.Message`: tên lớp đầy đủ, dùng dấu chấm giữa các package.

Để xem cả thành viên private và chi tiết class file:

```sh
javap -v -p -classpath out com.example.Message
```

Nếu class file nằm trong một JAR:

```sh
javap -v -classpath app.jar com.example.Message
```

Để lưu kết quả ra tệp văn bản:

```sh
javap -v -p -classpath out com.example.Message > constant-pool.txt
```

Tệp đầu ra là bản trình bày đã giải mã bởi `javap`, không phải bản sao byte-for-byte của class file. Các chỉ mục và cách trình bày có thể thay đổi khi mã nguồn, compiler hoặc phiên bản JDK thay đổi.

## 3. Ví dụ tạo class file để quan sát

Tạo cấu trúc:

```text
project/
└── src/
    └── com/
        └── example/
            └── ConstantPoolDemo.java
```

Nội dung `ConstantPoolDemo.java`:

```java
package com.example;

public class ConstantPoolDemo {
    private static final int MAX_RETRIES = 3;
    private static final String LABEL = "jdk-tooling";

    private final String name;

    public ConstantPoolDemo(String name) {
        this.name = name;
    }

    public String message(int count) {
        return LABEL + ":" + name + ":" + count;
    }

    public static void main(String[] args) {
        ConstantPoolDemo demo = new ConstantPoolDemo("Java");
        System.out.println(demo.message(MAX_RETRIES));
    }
}
```

Biên dịch vào thư mục `out`:

```sh
mkdir -p out
javac -d out src/com/example/ConstantPoolDemo.java
```

Trên Windows PowerShell có thể tạo thư mục bằng:

```powershell
New-Item -ItemType Directory -Force out
javac -d out src/com/example/ConstantPoolDemo.java
```

Chạy chương trình:

```sh
java -cp out com.example.ConstantPoolDemo
```

Kết quả:

```text
jdk-tooling:Java:3
```

Xem constant pool:

```sh
javap -v -p -classpath out com.example.ConstantPoolDemo
```

Trong kết quả, tìm phần bắt đầu bằng:

```text
Constant pool:
```

Các mục được đánh số như `#1`, `#2`, `#3`... Các chỉ mục thực tế có thể khác giữa các lần biên dịch hoặc các phiên bản compiler. Hãy dùng chúng để hiểu cách các mục tham chiếu nhau, không ghi nhớ một chỉ mục cố định.

## 4. Cách đọc một mục constant pool

Một dòng trong phần constant pool có dạng khái quát:

```text
#<index> = <tag> <data>
```

Ví dụ minh họa:

```text
#1 = Methodref          #2.#3
#2 = Class              #4
#3 = NameAndType        #5:#6
#4 = Utf8               java/lang/Object
#5 = Utf8               <init>
#6 = Utf8               ()V
```

Cách lần theo:

1. `#1` là một mục Methodref, biểu diễn tham chiếu đến phương thức.
2. Methodref tham chiếu `#2` để xác định lớp sở hữu và `#3` để xác định tên cùng descriptor.
3. `#2` là Class, tham chiếu `#4`.
4. `#4` là UTF-8 chứa tên nội bộ `java/lang/Object`.
5. `#3` là NameAndType, kết hợp `#5` và `#6`.
6. `#5` là tên phương thức `<init>`; `#6` là descriptor `()V`.

Như vậy, mục `#1` mô tả lời gọi constructor `java.lang.Object()`. Đây là ví dụ minh họa cách tham chiếu; thứ tự và chỉ mục trong class file thật phụ thuộc mã nguồn và compiler.

Trong kết quả `javap -v`, phần chú thích sau `//` thường giúp con người đọc nhanh quan hệ đó. Tuy vậy, khi phân tích cấu trúc, cần hiểu các chỉ mục trước dấu chú thích vì đó mới là các tham chiếu thực sự được lưu trong class file.

## 5. Các loại mục thường gặp

Mỗi mục constant pool bắt đầu bằng tag xác định loại dữ liệu. Các loại thường thấy:

| Tag | Tên mục | Ý nghĩa |
|---:|---|---|
| 1 | `Utf8` | Chuỗi Modified UTF-8, dùng cho tên và descriptor |
| 3 | `Integer` | Hằng số nguyên 32-bit |
| 4 | `Float` | Hằng số dấu phẩy động 32-bit |
| 5 | `Long` | Hằng số nguyên 64-bit |
| 6 | `Double` | Hằng số dấu phẩy động 64-bit |
| 7 | `Class` | Tham chiếu tên lớp hoặc interface |
| 8 | `String` | Tham chiếu chuỗi literal |
| 9 | `Fieldref` | Tham chiếu trường của lớp |
| 10 | `Methodref` | Tham chiếu phương thức của lớp |
| 11 | `InterfaceMethodref` | Tham chiếu phương thức của interface |
| 12 | `NameAndType` | Cặp tên và descriptor |
| 15 | `MethodHandle` | Tham chiếu đến một trường hoặc phương thức theo loại handle |
| 16 | `MethodType` | Descriptor của kiểu phương thức |
| 17 | `Dynamic` | Hằng số được tính toán thông qua bootstrap method |
| 18 | `InvokeDynamic` | Call site được liên kết thông qua bootstrap method |
| 19 | `Module` | Tên module |
| 20 | `Package` | Tên package |

Các tag mới được bổ sung theo từng phiên bản class file. Một JDK cũ có thể không hiểu một tag được dùng bởi class file mới hơn.

### 5.1. Utf8

Mục `Utf8` lưu các chuỗi được dùng bởi những phần khác của class file, ví dụ:

- Tên lớp: `com/example/ConstantPoolDemo`.
- Tên phương thức: `message`.
- Tên trường: `name`.
- Descriptor: `(I)Ljava/lang/String;`.
- Tên attribute: `Code`, `LineNumberTable`, `SourceFile`.
- Chuỗi literal: `jdk-tooling`.

Định dạng chuỗi trong constant pool là **Modified UTF-8**, không hoàn toàn giống UTF-8 tiêu chuẩn. Khi viết công cụ đọc class file, không nên giải mã các byte này bằng giả định UTF-8 thông thường.

### 5.2. Integer, Float, Long và Double

Các mục này biểu diễn hằng số số học. Ví dụ, literal `3` có thể được lưu dưới dạng Integer; literal dấu phẩy động có thể xuất hiện dưới dạng Float hoặc Double tùy kiểu.

`Long` và `Double` chiếm hai vị trí trong constant pool. Vị trí thứ hai được dành riêng và không thể được tham chiếu như một mục độc lập. Vì vậy, khi lần theo chỉ mục, có thể thấy một khoảng trống sau mục Long hoặc Double.

### 5.3. Class

Mục Class tham chiếu đến mục Utf8 chứa tên nội bộ của lớp hoặc interface. Ví dụ:

```text
java/lang/String
com/example/ConstantPoolDemo
[I
[Ljava/lang/String;
```

Tên lớp thông thường dùng dấu gạch chéo `/` để phân tách package. Kiểu mảng có dạng descriptor đặc biệt, ví dụ `[I` là mảng int và `[Ljava/lang/String;` là mảng String.

### 5.4. String

Mục String tham chiếu đến một mục Utf8 chứa nội dung literal. Ví dụ, literal:

```java
String label = "jdk-tooling";
```

có thể dẫn đến một mục `String` tham chiếu đến chuỗi `jdk-tooling`.

Không nhầm mục `CONSTANT_String` trong class file với toàn bộ cơ chế String Pool của JVM. Constant pool là cấu trúc trong class file; khi JVM nạp và xử lý literal, nó áp dụng quy tắc runtime về đối tượng String và intern. `String.intern()` là API runtime liên quan đến canonical string, không phải lệnh xem constant pool.

## 6. Fieldref, Methodref và InterfaceMethodref

Ba loại tham chiếu này là phần quan trọng khi muốn hiểu lớp gọi hoặc truy cập thành phần nào.

### 6.1. Fieldref

`Fieldref` biểu diễn tham chiếu đến một trường. Nó liên kết:

- Lớp hoặc interface sở hữu trường.
- Tên trường.
- Descriptor của trường.

Ví dụ mã nguồn:

```java
class Counter {
    int value;

    int read() {
        return value;
    }
}
```

Trong class file, việc truy cập trường có thể dùng một mục Fieldref để xác định `Counter.value` với descriptor kiểu int (`I`). Bytecode tương ứng thường có lệnh như `getfield` hoặc `putfield`, tùy thao tác.

### 6.2. Methodref

`Methodref` biểu diễn tham chiếu đến phương thức được khai báo trong lớp. Mục này tham chiếu Class và NameAndType.

Ví dụ, lời gọi:

```java
System.out.println("Hello");
```

cần tham chiếu đến lớp `java/io/PrintStream`, phương thức `println` và descriptor tương ứng với kiểu đối số. Trong constant pool, các thành phần này có thể được thể hiện qua Methodref, Class, NameAndType và Utf8.

### 6.3. InterfaceMethodref

`InterfaceMethodref` dùng để tham chiếu phương thức được khai báo trong interface. Ví dụ, lời gọi phương thức qua một biến có kiểu interface có thể dùng mục tham chiếu này.

Khi đọc `javap -v`, hãy lần theo Class và NameAndType để trả lời ba câu hỏi:

1. Lớp/interface nào sở hữu thành viên?
2. Tên thành viên là gì?
3. Kiểu tham số và kiểu trả về là gì?

Đây là cách hữu ích để phân tích dependency ở mức bytecode.

## 7. NameAndType và descriptor

Mục `NameAndType` kết hợp tên thành viên với descriptor. Descriptor mô tả kiểu trường hoặc chữ ký phương thức theo định dạng JVM.

Ví dụ descriptor:

| Java declaration | Descriptor |
|---|---|
| `int count` | `I` |
| `String name` | `Ljava/lang/String;` |
| `int[] values` | `[I` |
| `void reset()` | `()V` |
| `int add(int a, int b)` | `(II)I` |
| `String format(int code)` | `(I)Ljava/lang/String;` |
| `void save(String path, boolean force)` | `(Ljava/lang/String;Z)V` |

Các kiểu primitive có ký hiệu riêng:

| Kiểu Java | Descriptor |
|---|---|
| boolean | `Z` |
| byte | `B` |
| char | `C` |
| short | `S` |
| int | `I` |
| long | `J` |
| float | `F` |
| double | `D` |
| void | `V` |

Với phương thức, các kiểu tham số nằm trong cặp ngoặc tròn; kiểu trả về đứng sau dấu đóng ngoặc. Ví dụ `(II)I` có hai tham số int và trả về int.

Descriptor không giữ đầy đủ kiểu generic sau type erasure. Ví dụ, `List<String>` và `List<Integer>` đều dùng descriptor kiểu raw `Ljava/util/List;`. Thông tin generic có thể được lưu riêng trong attribute `Signature`.

## 8. MethodHandle, MethodType và InvokeDynamic

Các mục này thường xuất hiện khi mã nguồn dùng lambda, method reference hoặc cơ chế gọi động.

### 8.1. MethodHandle

`MethodHandle` mô tả một handle đến trường hoặc phương thức. Nó có một loại reference kind xác định cách truy cập, ví dụ lấy trường, đặt trường hoặc gọi một phương thức theo quy tắc tương ứng.

Method handle là nền tảng cho nhiều API trong `java.lang.invoke`, bao gồm `MethodHandles` và `MethodHandle`.

### 8.2. MethodType

`MethodType` mô tả kiểu tham số và kiểu trả về của một phương thức. Nó thường được dùng cùng method handle và cơ chế liên kết động.

### 8.3. InvokeDynamic

`InvokeDynamic` đại diện cho call site được liên kết thông qua bootstrap method. Cơ chế này cho phép JVM hoặc runtime liên kết một lời gọi theo cách linh hoạt.

Một số trường hợp thường tạo các mục liên quan:

- Lambda expression.
- Method reference.
- String concatenation trong các phiên bản Java hiện đại.
- Các framework hoặc thư viện sử dụng cơ chế `invokedynamic`.

Trong `javap -v`, có thể thấy mục `InvokeDynamic` trong constant pool và attribute `BootstrapMethods` ở phần attributes của class. Mục InvokeDynamic chỉ đến NameAndType và một bootstrap method entry; attribute BootstrapMethods cung cấp thông tin về bootstrap method cùng các đối số liên quan.

Ví dụ:

```java
import java.util.function.IntUnaryOperator;

public class DynamicDemo {
    public static void main(String[] args) {
        IntUnaryOperator twice = value -> value * 2;
        System.out.println(twice.applyAsInt(4));
    }
}
```

Biên dịch và xem:

```sh
javac -d out DynamicDemo.java
javap -v -p -classpath out DynamicDemo
```

Kết quả chương trình:

```text
8
```

Với compiler hiện đại, lambda thường được biểu diễn qua invokedynamic và bootstrap method liên quan đến cơ chế lambda metafactory. Chi tiết chỉ mục và bytecode có thể thay đổi giữa các phiên bản JDK; điều quan trọng là nhận diện quan hệ giữa InvokeDynamic, NameAndType và BootstrapMethods.

## 9. Dynamic constant, Module và Package

### 9.1. Dynamic constant

`CONSTANT_Dynamic` (tag 17) biểu diễn một hằng số được tạo ra thông qua bootstrap method khi runtime liên kết constant đó. Nó khác hằng số số học hoặc chuỗi literal được lưu trực tiếp.

Dynamic constant cho phép runtime tạo và cache giá trị theo quy tắc của class file. Nó có thể được sử dụng bởi compiler hoặc công cụ sinh bytecode; không phải mọi mã nguồn Java thông thường đều tạo ra mục này.

### 9.2. Module và Package

`CONSTANT_Module` và `CONSTANT_Package` xuất hiện trong class file có thông tin module, đặc biệt `module-info.class`. Chúng tham chiếu tên module hoặc package trong cấu trúc module.

Có thể xem module descriptor bằng:

```sh
javap -v module-info.class
```

Hoặc dùng cú pháp module phù hợp khi phân tích một module đã cài. Các mục này phục vụ mô hình module của Java Platform Module System, không phải package/class reference thông thường trong mọi lớp ứng dụng.

## 10. Lần theo constant pool từ bytecode

Constant pool gắn chặt với các lệnh bytecode. Một số lệnh dùng chỉ mục constant pool để tìm thành phần cần thao tác:

| Bytecode instruction | Tham chiếu thường gặp |
|---|---|
| `ldc`, `ldc_w`, `ldc2_w` | Literal hoặc dynamic constant |
| `getfield`, `putfield` | Fieldref |
| `getstatic`, `putstatic` | Fieldref |
| `invokevirtual` | Methodref |
| `invokespecial` | Methodref hoặc loại tham chiếu được đặc tả cho lệnh |
| `invokestatic` | Methodref hoặc InterfaceMethodref theo phiên bản/định nghĩa |
| `invokeinterface` | InterfaceMethodref |
| `invokedynamic` | InvokeDynamic |

Dùng cả `-v` và `-c` để xem constant pool cùng bytecode:

```sh
javap -v -c -p -classpath out com.example.ConstantPoolDemo
```

Khi thấy một lệnh như `getfield #...`, tìm chỉ mục tương ứng trong phần Constant pool để biết lớp, tên trường và descriptor. Khi thấy `invokevirtual #...`, lần theo Methodref để xác định phương thức được gọi.

Đây là kỹ thuật quan trọng khi điều tra:

- Một thư viện đang tham chiếu phiên bản API nào.
- Vì sao xuất hiện `NoSuchMethodError` hoặc `NoSuchFieldError`.
- Bytecode gọi phương thức của lớp hay interface.
- Một thao tác trong mã nguồn được compiler chuyển thành những lệnh JVM nào.

## 11. Phân biệt constant pool với các khái niệm gần giống

| Khái niệm | Phạm vi | Vai trò |
|---|---|---|
| Class-file constant pool | Mỗi class file | Lưu hằng số, tên và symbolic reference của lớp |
| Runtime constant pool | Mỗi lớp/interface khi JVM biểu diễn lúc chạy | Biểu diễn runtime của constant pool theo JVM |
| String Pool | Cơ chế quản lý canonical String ở runtime | Quản lý các chuỗi được intern |
| Java constant variable | Biến `final` có kiểu primitive/String và được khởi tạo bằng constant expression | Có thể được compiler inline tại nơi sử dụng |
| `ConstantValue` attribute | Attribute của field trong class file | Ghi giá trị khởi tạo cho một số static constant field |

Một biến `static final` không tự động trở thành một mục Fieldref trong constant pool. Với constant variable kiểu primitive hoặc String, compiler có thể thay chỗ sử dụng bằng giá trị literal. Field vẫn có thể có `ConstantValue` attribute trong class file.

Tương tự, việc nhìn thấy mục `String` trong constant pool không có nghĩa toàn bộ String Pool runtime được lưu trong class file. Class file chứa literal và tham chiếu; việc tạo/resolve đối tượng String diễn ra theo quy tắc JVM.

## 12. Một số tùy chọn javap hữu ích khi phân tích

| Tùy chọn | Tác dụng |
|---|---|
| `-v`, `-verbose` | In thông tin chi tiết, bao gồm constant pool và attributes |
| `-p`, `-private` | Hiển thị cả thành viên private |
| `-c` | Disassemble bytecode của các phương thức |
| `-s` | Hiển thị internal type signatures |
| `-constants` | Hiển thị giá trị static final constant khi có |
| `-classpath`, `-cp`, `--class-path` | Chỉ định nơi tìm lớp |
| `-sysinfo` | Hiển thị thông tin hệ thống của class file, như đường dẫn, kích thước và checksum |

Lưu ý: `-constants` chỉ hiển thị giá trị constant field phù hợp; nó không thay thế `-verbose` khi cần xem toàn bộ constant pool. Nếu muốn kiểm tra symbolic references, descriptor, InvokeDynamic và BootstrapMethods, hãy dùng `-v`.

## 13. Quy trình đọc constant pool có hệ thống

Khi phân tích một class file chưa quen thuộc, có thể thực hiện theo thứ tự:

1. Xác định đúng class file và classpath/module path.
2. Chạy `javap -v -p` để xem toàn bộ thông tin.
3. Đọc major/minor version trước để biết compiler target.
4. Tìm tên lớp, superclass và interface.
5. Trong Constant pool, phân loại các mục Utf8, Class, String, số, Fieldref, Methodref và NameAndType.
6. Lần theo các chỉ mục để tìm owner, member name và descriptor.
7. Đối chiếu mục tham chiếu với bytecode bằng `javap -c`.
8. Kiểm tra BootstrapMethods nếu có InvokeDynamic hoặc Dynamic.
9. Xem attributes như Signature, ConstantValue, RuntimeVisibleAnnotations và Code khi cần.
10. Ghi nhận compiler/JDK version và cấu hình release để so sánh kết quả giữa các lần build.

Đừng cố hiểu toàn bộ constant pool theo thứ tự từ đầu đến cuối ngay lập tức. Hãy bắt đầu từ một bytecode instruction hoặc một member cụ thể, sau đó lần theo chỉ mục mà nó sử dụng. Cách này giúp tìm ra đúng thông tin cần thiết nhanh hơn.

## 14. Lỗi thường gặp khi xem constant pool

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Error: class not found` | Sai tên lớp đầy đủ hoặc classpath không trỏ đến output root | Dùng `javap -v -cp out com.example.ClassName` và kiểm tra vị trí package |
| `javap` báo class file không hợp lệ | Tệp không phải class file, bị hỏng hoặc bị cắt | Build lại artifact; xác nhận đường dẫn không trỏ nhầm sang file khác |
| Không thấy phần Constant pool | Không dùng `-v`/`-verbose` hoặc đang xem dạng output rút gọn | Chạy `javap -verbose` |
| Chỉ thấy thành viên public | Chưa bật hiển thị private | Thêm `-p` |
| Không tìm thấy một tên biến local | Tên biến không được lưu do compiler không tạo debug metadata | Biên dịch với `-g`; lưu ý tên local không nhất thiết nằm trong constant pool |
| Không thấy tên generic như mong đợi | Descriptor đã dùng kiểu sau type erasure | Tìm attribute `Signature` thay vì chỉ đọc descriptor |
| Chỉ mục constant pool khác ví dụ | Mã nguồn hoặc compiler đã tạo thứ tự mục khác | Lần theo chỉ mục trong chính class file đang xem, không dựa vào số mẫu |
| Không thấy Fieldref cho biến static final | Compiler có thể inline constant variable | Xem `ConstantValue` và bytecode nơi sử dụng |
| Không hiểu mục InvokeDynamic | Chưa xem BootstrapMethods hoặc NameAndType tương ứng | Dùng `javap -v -c` và lần theo các tham chiếu |
| `javap` của JDK cũ không đọc được class file mới | Tool không hỗ trợ major version hoặc tag mới | Dùng javap từ JDK tương thích với class file |

## 15. Checklist

- [ ] Đã xác định đúng class file và output root.
- [ ] Dùng `javap -v` hoặc `javap -verbose` để hiển thị constant pool.
- [ ] Dùng `-p` nếu cần xem cả thành viên private.
- [ ] Hiểu chỉ mục constant pool bắt đầu từ 1; chỉ mục 0 không được sử dụng.
- [ ] Biết Long và Double chiếm hai slot.
- [ ] Phân biệt Utf8, Class, String, NameAndType, Fieldref và Methodref.
- [ ] Đọc descriptor để xác định kiểu trường, tham số và giá trị trả về.
- [ ] Phân biệt class-file constant pool với String Pool runtime.
- [ ] Dùng `-c` để liên kết constant pool với bytecode instruction.
- [ ] Kiểm tra BootstrapMethods khi có InvokeDynamic hoặc Dynamic.
- [ ] Không dựa vào chỉ mục cố định từ một ví dụ hoặc một lần biên dịch.

Constant pool là bản đồ các tên, kiểu và symbolic reference mà JVM dùng để hiểu nội dung một lớp. Khi biết cách xem bằng `javap -v` và lần theo các chỉ mục, bạn có thể xác định chính xác một class file đang tham chiếu lớp, trường, phương thức và API nào, đồng thời hiểu mối liên hệ giữa mã nguồn, bytecode và quá trình liên kết của JVM.