# Class file, bytecode và kiểm tra bằng javap

Khi biên dịch mã Java, trình biên dịch `javac` chuyển source code thành **class file** chứa bytecode cho Java Virtual Machine (JVM). Class file lưu cấu trúc lớp, phương thức, constant pool, bytecode và metadata cần thiết để JVM liên kết, kiểm tra và thực thi chương trình.

Trong JDK 17, công cụ dòng lệnh **`javap`** giúp đọc cấu trúc class file và disassemble bytecode để quan sát cách compiler biểu diễn mã nguồn. Đây là công cụ hữu ích khi tìm hiểu compiler, điều tra lỗi tương thích phiên bản class file, xem method descriptor, kiểm tra annotation/attribute hoặc hiểu vì sao một đoạn Java tạo ra instruction nhất định.

Bài này trình bày class file và bytecode theo góc nhìn Java 17, cách biên dịch có kiểm soát bằng `javac --release`, các tùy chọn `javap` thường dùng, cách đọc output và một quy trình kiểm tra thực tế. Bytecode là định dạng trung gian dành cho JVM; nó không phải source Java và cũng không phải mã máy native của một CPU cụ thể.

## 1. Từ source code đến class file

Quá trình cơ bản:

~~~text
Hello.java
    |
    | javac
    v
Hello.class
    |
    | JVM class loader
    v
Load -> Link -> Initialize
    |
    v
Bytecode execution
    |
    +--> Interpreter
    |
    +--> JIT compilation -> Native machine code
~~~

Ví dụ source:

~~~java
package demo;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java 17!");
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d out src/demo/Hello.java
~~~

Kết quả có file `out/demo/Hello.class`. Chạy:

~~~bash
java -cp out demo.Hello
~~~

Kết quả:

~~~text
Hello, Java 17!
~~~

`javac` tạo class file; JVM nạp class file và thực thi bytecode. Tùy JVM và mức độ nóng của code, một số method có thể được JIT compiler biên dịch thành mã máy native trong lúc chạy.

### 1.1. Class file có tính độc lập nền tảng

Một class file Java không được biên dịch riêng cho x86-64, ARM64 hoặc một hệ điều hành cụ thể. Nó chứa bytecode theo đặc tả JVM. Các JVM tương thích với class file version và tính năng được dùng có thể chạy bytecode đó trên nền tảng của mình.

Tính độc lập này có điều kiện:

- Runtime phải hỗ trợ class file version tương ứng.
- Các API mà chương trình gọi phải có trên runtime.
- Các thư viện phụ thuộc phải tương thích.
- Nếu code dùng native library/JNI, phần native vẫn phụ thuộc nền tảng.
- Một số tính năng preview yêu cầu runtime bật preview tương ứng.

Vì thế, class file có thể portable hơn native executable, nhưng không bảo đảm mọi ứng dụng Java chạy giống nhau trên mọi runtime.

## 2. Class file chứa những gì?

Class file có cấu trúc nhị phân theo định dạng được JVM Specification quy định. Khi dùng `javap -v`, có thể quan sát nhiều thành phần:

1. Magic number.
2. Minor version và major version.
3. Constant pool.
4. Access flags.
5. Thông tin class hiện tại và superclass.
6. Interfaces.
7. Fields.
8. Methods.
9. Attributes.

Có thể hình dung cấu trúc tổng quát:

~~~text
ClassFile
|
+-- magic
+-- minor_version
+-- major_version
+-- constant_pool
+-- access_flags
+-- this_class
+-- super_class
+-- interfaces
+-- fields
+-- methods
+-- attributes
~~~

### 2.1. Magic number

Bốn byte đầu của một class file hợp lệ là:

~~~text
CA FE BA BE
~~~

Đây là magic number `0xCAFEBABE`, giúp nhận diện định dạng class file. Nếu file bị hỏng, không phải class file hoặc bị đọc sai định dạng, công cụ có thể báo lỗi ngay khi kiểm tra phần đầu.

### 2.2. Major version và minor version

Class file lưu phiên bản định dạng bằng hai trường:

- `major_version`: phiên bản chính của class file.
- `minor_version`: phiên bản phụ, trong đó có quy ước dành cho preview feature.

Class file được tạo bởi Java 17 thông thường có:

| Trường | Giá trị |
| --- | ---: |
| `major_version` | 61 |
| `minor_version` | 0 |

Một số major version thường gặp:

| Java release | Class file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Nếu class file có major version mới hơn mà runtime không hỗ trợ, JVM có thể ném `UnsupportedClassVersionError`.

Ví dụ, class file major version 61 cần runtime hỗ trợ định dạng Java 17 trở lên. Chạy một class file Java 17 trên Java 11 không thể chỉ giải quyết bằng cách thêm JAR; cần biên dịch lại cho phiên bản mục tiêu phù hợp hoặc nâng runtime.

### 2.3. Constant pool

Constant pool là bảng chứa hằng số và tham chiếu mà class file sử dụng. Các entry có thể biểu diễn:

- Literal số nguyên, số thực, long và double.
- String constant.
- Tên class và tên interface.
- Tên field và method.
- Field/method reference.
- Method handle và method type.
- Dynamic constant và invokedynamic metadata.

Ví dụ source:

~~~java
public class Greeting {
    public static final String MESSAGE = "Hello";

    public static void print(String name) {
        System.out.println(MESSAGE + ", " + name);
    }
}
~~~

Constant pool có thể chứa các chuỗi `"Hello"`, `", "`, tên lớp `java/lang/System`, tên field `out`, tên method `println` và các descriptor liên quan.

Trong output `javap -v`, các mục được đánh số `#1`, `#2`, ... Những số này là index trong constant pool; bytecode có thể tham chiếu đến chúng bằng instruction như `ldc`, `getstatic`, `invokevirtual` hoặc `invokedynamic`.

Constant pool không phải một danh sách literal đơn giản. Nó còn mô tả liên kết symbolic giữa class, field, method, kiểu dữ liệu và bootstrap method.

### 2.4. Fields và methods

Phần fields mô tả các field của class, gồm access flags, tên, descriptor và attributes nếu có.

Phần methods mô tả constructor, method thường, method tổng hợp (synthetic) hoặc method được compiler sinh ra. Mỗi method có thể có các thuộc tính như:

- Access flags (`public`, `private`, `static`, `final`, ...).
- Method descriptor.
- `Code` attribute nếu method có bytecode.
- `Exceptions` attribute.
- `Signature` cho generic signature khi cần.
- `RuntimeVisibleAnnotations` hoặc annotation attributes khác.
- `MethodParameters` nếu compiler ghi tên/thông tin tham số.

Một abstract method hoặc native method không có `Code` attribute chứa bytecode như method thông thường.

## 3. Bytecode là gì?

Bytecode là tập instruction của JVM. JVM là máy ảo dạng stack-based: nhiều instruction lấy operand từ **operand stack**, thực hiện thao tác rồi đẩy kết quả trở lại stack.

Ví dụ phép cộng hai số nguyên:

~~~java
public static int add(int left, int right) {
    return left + right;
}
~~~

Bytecode minh họa:

~~~text
0: iload_0
1: iload_1
2: iadd
3: ireturn
~~~

Diễn giải:

1. `iload_0`: đẩy giá trị int ở local variable slot 0 lên operand stack.
2. `iload_1`: đẩy giá trị int ở slot 1 lên stack.
3. `iadd`: lấy hai int trên stack, cộng và đẩy kết quả.
4. `ireturn`: trả về int.

Với method static, hai tham số `left` và `right` thường nằm ở slot 0 và 1. Với method instance, slot 0 chứa `this`; các tham số bắt đầu từ slot 1. `long` và `double` chiếm hai local variable slots trong mô hình JVM.

### 3.1. Local variables và operand stack

Mỗi lần thực thi method có một frame. Frame chứa:

- Local variable array.
- Operand stack.
- Tham chiếu đến runtime constant pool của class hiện tại.

Một số instruction thao tác với local variables, một số thao tác với operand stack, một số truy cập field hoặc gọi method.

~~~text
Method frame
+---------------------------+
| Local variables           |
|  slot 0: left             |
|  slot 1: right            |
+---------------------------+
| Operand stack             |
|  [left]                   |
|  [left, right]            |
|  [sum]                    |
+---------------------------+
~~~

Đây là mô hình giúp đọc bytecode; JVM implementation có thể tối ưu cách thực thi bên dưới nhưng phải giữ đúng semantics của bytecode.

### 3.2. Một số nhóm instruction thường gặp

| Nhóm | Ví dụ instruction | Ý nghĩa |
| --- | --- | --- |
| Load/store | `iload`, `aload`, `istore`, `astore` | Đọc/ghi local variable |
| Constant | `iconst`, `bipush`, `sipush`, `ldc` | Đẩy hằng số lên stack |
| Arithmetic | `iadd`, `isub`, `imul`, `idiv` | Phép toán số học |
| Compare/branch | `if_icmpge`, `ifeq`, `goto` | So sánh và rẽ nhánh |
| Object | `new`, `checkcast`, `instanceof` | Tạo/kiểm tra object |
| Field | `getfield`, `putfield`, `getstatic`, `putstatic` | Đọc/ghi field |
| Method call | `invokevirtual`, `invokestatic`, `invokespecial`, `invokeinterface` | Gọi method |
| Dynamic call | `invokedynamic` | Liên kết lời gọi động qua bootstrap method |
| Array | `newarray`, `anewarray`, `iaload`, `aastore` | Tạo và truy cập mảng |
| Return | `ireturn`, `areturn`, `return` | Trả kết quả hoặc kết thúc void method |
| Exception | `athrow` | Ném throwable |

Tên instruction thường có tiền tố mô tả kiểu dữ liệu. Ví dụ `iadd` cho int, `ladd` cho long, `fadd` cho float và `dadd` cho double.

Không cần học thuộc toàn bộ opcode để dùng `javap`. Hãy nhận diện các instruction chính và lần theo operand stack, local variables, constant pool reference.

## 4. Descriptor và kiểu dữ liệu trong class file

Class file dùng descriptor để mô tả kiểu field và chữ ký method. Descriptor không giống cú pháp generic trong source; nó là biểu diễn cấp JVM.

### 4.1. Descriptor của kiểu cơ bản và reference

| Java type | Descriptor |
| --- | --- |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `void` (return) | `V` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

Reference type có dạng `L` + tên nội bộ + `;`. Tên nội bộ dùng dấu `/` để phân tách package.

### 4.2. Method descriptor

Method descriptor có dạng:

~~~text
(parameter-descriptors)return-descriptor
~~~

Ví dụ:

~~~java
public boolean isValid(String name, int age) {
    return name != null && age >= 0;
}
~~~

Descriptor:

~~~text
(Ljava/lang/String;I)Z
~~~

Nó biểu diễn hai tham số (`String`, `int`) và kết quả `boolean`.

Một method khác:

~~~java
public static void log(long id, String[] tags) {
}
~~~

Descriptor:

~~~text
(J[Ljava/lang/String;)V
~~~

Method descriptor hữu ích khi đọc `javap -s`, stack trace cấp thấp, reflection metadata hoặc lỗi liên kết method.

### 4.3. Generic signature và type erasure

Java generic thường được type erasure khi biểu diễn trong bytecode. Ví dụ:

~~~java
List<String> names;
~~~

Descriptor của field có thể chỉ là:

~~~text
Ljava/util/List;
~~~

Generic signature riêng có thể lưu thông tin `List<String>` trong `Signature` attribute. Vì thế descriptor và generic signature phục vụ hai mục đích khác nhau: descriptor xác định kiểu JVM dùng để liên kết; signature giữ metadata generic cho compiler/reflection/tooling.

## 5. Attributes trong class file

Attributes bổ sung metadata cho class, field, method hoặc code. Một số attribute thường thấy:

| Attribute | Nội dung |
| --- | --- |
| `SourceFile` | Tên file source liên quan |
| `LineNumberTable` | Ánh xạ bytecode offset sang số dòng source |
| `LocalVariableTable` | Tên và kiểu local variable khi debug metadata được ghi |
| `StackMapTable` | Thông tin stack map frame phục vụ bytecode verification |
| `Exceptions` | Các exception được khai báo trong `throws` |
| `Signature` | Generic signature |
| `RuntimeVisibleAnnotations` | Annotation cần giữ ở runtime |
| `BootstrapMethods` | Bootstrap method cho `invokedynamic` và dynamic constant |
| `NestHost`, `NestMembers` | Metadata về nest-based access |
| `Record` | Metadata cho record class |
| `PermittedSubclasses` | Danh sách subclass được phép của sealed class |
| `Module` | Module descriptor trong `module-info.class` |

Không phải class file nào cũng có tất cả attributes. Một số metadata chỉ được ghi nếu source có cấu trúc tương ứng hoặc compiler được yêu cầu lưu debug information.

### 5.1. Debug information

Có thể điều khiển debug information bằng `javac`:

~~~bash
javac --release 17 -g -d out src/demo/Hello.java
~~~

`-g` yêu cầu compiler ghi thông tin debug. Có thể chọn thành phần cụ thể:

~~~bash
javac --release 17 -g:lines,source -d out src/demo/Hello.java
~~~

Hoặc bỏ debug information:

~~~bash
javac --release 17 -g:none -d out src/demo/Hello.java
~~~

Debug metadata giúp debugger và công cụ quan sát ánh xạ bytecode với source. Nó không thay đổi logic nghiệp vụ của chương trình. Tên local variable có thể không có trong class file nếu compiler không ghi `LocalVariableTable`.

## 6. Biên dịch đúng phiên bản bằng javac --release

Khi phát hành thư viện hoặc ứng dụng, cần xác định phiên bản Java thấp nhất mà artifact hỗ trợ.

Trên JDK 17:

~~~bash
javac --release 17 -d out src/demo/Hello.java
~~~

`--release 17` cấu hình đồng thời:

- Mức ngôn ngữ Java được chấp nhận.
- Phiên bản class file được tạo.
- Tập API Java SE được phép sử dụng cho release mục tiêu.

Điểm cuối rất quan trọng. Nếu chỉ dùng `-source 17 -target 17` trên một JDK mới hơn, compiler có thể vẫn nhìn thấy API mới của JDK hiện tại; class file tạo ra có thể gọi method không tồn tại trên runtime Java 17. `--release` giúp ràng buộc cả API surface của release mục tiêu.

### 6.1. So sánh các tùy chọn

| Tùy chọn | Tác dụng |
| --- | --- |
| `--release 17` | Source level, target class version và API của Java 17 |
| `-source 17` | Mức cú pháp/ngôn ngữ được chấp nhận |
| `-target 17` | Major version của class file |
| `-g` | Ghi debug information |
| `-parameters` | Ghi tên tham số method để reflection có thể đọc |
| `-encoding UTF-8` | Chọn encoding source file |

Với dự án cần tương thích Java 17, ưu tiên `--release 17` thay vì tự ghép `-source` và `-target`.

### 6.2. Preview features

Preview feature được bật tường minh khi biên dịch và chạy. Ví dụ cú pháp tổng quát trên JDK 17:

~~~bash
javac --release 17 --enable-preview -d out src/demo/PreviewDemo.java
java --enable-preview -cp out demo.PreviewDemo
~~~

Class file được biên dịch với preview feature của một release có minor version đặc biệt (65535). Runtime phải bật preview cho đúng release để chạy class file đó. Không dùng `--enable-preview` như một tùy chọn chung để chạy class file preview từ release khác.

## 7. Dùng javap để đọc class file

`javap` là disassembler đi kèm JDK. Nó đọc class file và hiển thị cấu trúc class, field, method, descriptor, bytecode và attributes tùy tùy chọn.

Kiểm tra phiên bản và trợ giúp:

~~~bash
javap -version
javap --help
~~~

Công cụ thường nằm cùng thư mục `bin` với `javac` và `java` trong JDK. Nếu terminal báo không tìm thấy `javap`, hãy kiểm tra `JAVA_HOME` và `PATH` đang trỏ đến JDK chứ không chỉ JRE/runtime image rút gọn.

### 7.1. Xem chữ ký class và method

~~~bash
javap -classpath out demo.Hello
~~~

Output mặc định tập trung vào thông tin class và các thành viên public/protected. Nó không hiển thị đầy đủ bytecode.

Muốn xem cả thành viên private:

~~~bash
javap -classpath out -p demo.Hello
~~~

`-p` (hoặc `-private`) hiển thị mọi class member mà công cụ có thể trình bày, gồm private field và method.

### 7.2. Disassemble bytecode bằng -c

~~~bash
javap -classpath out -c demo.Hello
~~~

`-c` hiển thị bytecode của từng method. Đây là tùy chọn quan trọng nhất khi muốn quan sát instruction do compiler tạo ra.

### 7.3. Xem descriptor bằng -s

~~~bash
javap -classpath out -s demo.Hello
~~~

`-s` in internal type signatures/descriptors. Hữu ích khi cần đối chiếu overload, method descriptor hoặc kiểu field.

### 7.4. Xem line number và local variable bằng -l

~~~bash
javap -classpath out -l demo.Hello
~~~

`-l` hiển thị thông tin line number và local variable table nếu các metadata đó có trong class file. Nếu class được biên dịch mà không lưu thông tin tương ứng, output có thể thiếu phần này.

### 7.5. Xem toàn bộ chi tiết bằng -v

~~~bash
javap -classpath out -v demo.Hello
~~~

`-v` (hoặc `-verbose`) hiển thị thông tin chi tiết hơn, thường gồm:

- Class file path.
- Minor/major version.
- Access flags.
- Constant pool.
- Field và method descriptor.
- Bytecode và stack/local limits.
- Exception table.
- Class/method/code attributes.
- Annotation và bootstrap metadata nếu có.

Đây là lựa chọn phù hợp khi cần kiểm tra class file version, constant pool, annotation hoặc lý do liên kết một method.

### 7.6. Các tùy chọn thường dùng

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-c` | Hiển thị bytecode |
| `-p` / `-private` | Hiển thị mọi class member |
| `-s` | Hiển thị descriptor |
| `-l` | Hiển thị line number và local variable table nếu có |
| `-v` / `-verbose` | Hiển thị chi tiết class file và attributes |
| `-constants` | Hiển thị hằng số `static final` |
| `-public` | Chỉ hiển thị public member |
| `-protected` | Hiển thị public và protected member |
| `-package` | Hiển thị package, protected và public member |
| `-classpath` / `-cp` | Chỉ định nơi tìm class |
| `--module` | Chỉ định module chứa class |
| `--multi-release` | Chọn phiên bản entry trong multi-release JAR |
| `-sysinfo` | Hiển thị thông tin hệ thống về class file |
| `-version` | Hiển thị phiên bản `javap` |

Có thể kết hợp các tùy chọn, ví dụ `-c -p -l`. Khi cần toàn bộ chi tiết, `-v` thường đã bao gồm nhiều thông tin mà các tùy chọn riêng lẻ hiển thị.

## 8. Ví dụ đọc bytecode từng bước

Tạo source:

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
}
~~~

Biên dịch:

~~~bash
javac --release 17 -g -d out src/demo/Calculator.java
~~~

Xem bytecode:

~~~bash
javap -classpath out -c -p demo.Calculator
~~~

Phần `add` có dạng:

~~~text
public static int add(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
~~~

Phần `absolute` có thể có dạng:

~~~text
public static int absolute(int);
  Code:
     0: iload_0
     1: ifge          7
     4: iload_0
     5: ineg
     6: ireturn
     7: iload_0
     8: ireturn
~~~

Bytecode offset và cách bố trí instruction phụ thuộc compiler, nhưng ý nghĩa logic tương ứng:

- `iload_0`: nạp tham số `value`.
- `ifge`: nếu giá trị lớn hơn hoặc bằng zero, nhảy đến nhánh trả nguyên giá trị.
- `ineg`: đổi dấu số nguyên.
- `ireturn`: trả về kết quả.

Khi đọc output thực tế, dùng offset được in trong class file thay vì giả định offset phải giống ví dụ.

## 9. Hiểu output của javap -v

Với lệnh:

~~~bash
javap -classpath out -v demo.Calculator
~~~

Một phần output có thể có dạng minh họa:

~~~text
Classfile .../demo/Calculator.class
  Last modified ...; size ...
  SHA-256 checksum ...
  Compiled from "Calculator.java"
public class demo.Calculator
  minor version: 0
  major version: 61
  flags: (0x0021) ACC_PUBLIC, ACC_SUPER
Constant pool:
   #1 = Methodref          #2.#3
   #2 = Class              #4
   #3 = NameAndType        #5:#6
   ...
{
  public demo.Calculator();
    descriptor: ()V
    flags: (0x0001) ACC_PUBLIC
    Code:
      stack=1, locals=1, args_size=1
      ...

  public static int add(int, int);
    descriptor: (II)I
    flags: (0x0009) ACC_PUBLIC, ACC_STATIC
    Code:
      stack=2, locals=2, args_size=2
      ...
}
~~~

Đây là output rút gọn để giải thích các trường; số constant pool index và offset thực tế phụ thuộc class được biên dịch.

Các mục đáng chú ý:

- `major version: 61`: class file mục tiêu Java 17.
- `flags`: modifier ở cấp JVM.
- `descriptor: (II)I`: hai tham số int, kết quả int.
- `stack=2`: operand stack tối đa của method trong ví dụ.
- `locals=2`: hai local variable slots được sử dụng.
- `args_size=2`: hai tham số của static method.

Với instance method, `args_size` còn tính slot dành cho `this`. `long` và `double` chiếm hai local variable slots theo mô hình JVM.

## 10. Các instruction gọi method và truy cập field

Khi xem bytecode, các instruction gọi method thường cho biết cách compiler biểu diễn dispatch.

| Instruction | Ý nghĩa tổng quát |
| --- | --- |
| `invokestatic` | Gọi static method |
| `invokevirtual` | Gọi instance method với virtual dispatch |
| `invokespecial` | Gọi constructor, private method hoặc một số lời gọi đặc biệt như superclass |
| `invokeinterface` | Gọi method qua interface |
| `invokedynamic` | Gọi theo cơ chế dynamic linkage qua bootstrap method |

Truy cập field:

- `getstatic`: đọc static field.
- `putstatic`: ghi static field.
- `getfield`: đọc instance field.
- `putfield`: ghi instance field.

Ví dụ:

~~~java
public class Counter {
    private int value;

    public int increment() {
        value++;
        return value;
    }
}
~~~

Bytecode có thể dùng `aload_0` để nạp `this`, `dup` để nhân đôi reference trên operand stack, `getfield` để đọc field, `iconst_1` và `iadd` để cộng, rồi `putfield` để ghi lại. `javap -c -p` cho phép quan sát chuỗi instruction cụ thể.

## 11. Lambda, string concatenation và invokedynamic

Một số code Java hiện đại có thể tạo ra bytecode dùng `invokedynamic`.

Ví dụ lambda:

~~~java
Runnable task = () -> System.out.println("run");
~~~

Compiler có thể phát sinh một `invokedynamic` instruction cùng bootstrap metadata liên quan đến `LambdaMetafactory`. JVM liên kết lời gọi động để tạo hành vi lambda theo cơ chế runtime.

String concatenation:

~~~java
String message = "Hello, " + name;
~~~

Với compiler Java hiện đại, nối chuỗi có thể được biểu diễn bằng `invokedynamic` và bootstrap method của `StringConcatFactory`. Cách sinh bytecode phụ thuộc compiler và phiên bản; không nên giả định mọi phép nối chuỗi luôn có cùng một chuỗi instruction.

Để quan sát:

~~~bash
javap -classpath out -c -v demo.LambdaDemo
~~~

Tìm `InvokeDynamic`, `BootstrapMethods`, `LambdaMetafactory` hoặc `StringConcatFactory` trong output. Điều này giúp hiểu liên kết động ở mức bytecode mà không cần xem implementation nội bộ của JVM.

## 12. Kiểm tra class trong JAR và module JDK

### 12.1. Đọc class trong JAR

Nếu class nằm trong JAR, truyền JAR vào classpath:

~~~bash
javap -classpath app.jar -c -p com.example.App
~~~

Với dependency ngoài:

~~~bash
javap -classpath "app.jar;lib/dependency.jar" -c com.example.App
~~~

Dấu phân cách classpath tùy hệ điều hành: Windows thường dùng `;`, Linux/macOS thường dùng `:`. Trong script dùng đa nền tảng, nên để build tool hoặc launcher tạo classpath thay vì hard-code dấu phân cách.

Với multi-release JAR, có thể chỉ định phiên bản entry muốn xem:

~~~bash
javap --multi-release 17 -classpath library.jar -c com.example.Library
~~~

Điều này hữu ích khi JAR chứa class khác nhau cho các release Java.

### 12.2. Xem class trong module của JDK

`javap` có thể đọc class thuộc module JDK:

~~~bash
javap --module java.base -p java.lang.String
~~~

Để xem bytecode:

~~~bash
javap --module java.base -c -p java.lang.String
~~~

Class trong JDK có thể rất lớn; nên kết hợp class/method cụ thể hoặc dùng output có mục tiêu khi điều tra. Việc đọc bytecode của class JDK giúp hiểu implementation của một bản JDK cụ thể, nhưng không biến chi tiết đó thành API được bảo đảm tương thích.

### 12.3. Xem module descriptor

Module descriptor nằm trong class file đặc biệt `module-info.class`. Có thể xem descriptor của module:

~~~bash
javap --module java.base module-info
~~~

Hoặc xem chi tiết:

~~~bash
javap -v --module java.base module-info
~~~

Output có thể hiển thị các directive như `requires`, `exports`, `opens`, `uses` và `provides`.

## 13. Bytecode verification và StackMapTable

Trước khi thực thi bytecode, JVM thực hiện các bước loading/linking. Trong quá trình verification, JVM kiểm tra tính hợp lệ về cấu trúc và kiểu của bytecode, chẳng hạn:

- Operand stack được dùng đúng kiểu.
- Local variable có kiểu hợp lệ tại các điểm điều khiển.
- Lời gọi method và truy cập field phù hợp với kiểu.
- Nhánh điều khiển không dẫn đến trạng thái stack không hợp lệ.
- Stack map frame đáp ứng quy tắc verification của class file version.

`StackMapTable` chứa thông tin stack map frame tại các điểm liên quan trong method. Nó hỗ trợ verifier kiểm tra kiểu và trạng thái stack/local variables trên các nhánh điều khiển.

`javap -v` có thể hiển thị `StackMapTable`. Công cụ này giúp quan sát metadata, nhưng việc đọc output không thay thế toàn bộ quy trình verifier của JVM.

### 13.1. Loading, linking và initialization

Ba khái niệm thường được nhắc khi JVM xử lý class:

1. **Loading:** tìm và nạp binary representation của class.
2. **Linking:** gồm verification, preparation và resolution theo nhu cầu.
3. **Initialization:** chạy static initializer và khởi tạo static field theo thứ tự quy định.

`javap` chỉ kiểm tra biểu diễn class file. Để xác nhận class có thể được nạp và chạy trong môi trường cụ thể, cần thực thi trên đúng JVM với classpath/module path và dependency thực tế.

## 14. Dùng javap để điều tra lỗi tương thích

### 14.1. UnsupportedClassVersionError

Nếu log báo:

~~~text
UnsupportedClassVersionError
~~~

Hãy kiểm tra major version:

~~~bash
javap -verbose -classpath out demo.Hello
~~~

Đối chiếu major version với runtime. Java 17 tạo class file major version 61; runtime cũ hơn không hỗ trợ định dạng này.

Giải pháp thường là:

- Nâng runtime lên phiên bản hỗ trợ class file.
- Hoặc biên dịch source bằng JDK phù hợp và `--release` tương ứng.
- Kiểm tra cả dependency, vì một JAR bên thứ ba cũng có thể chứa class file mới hơn.

### 14.2. NoSuchMethodError

`NoSuchMethodError` có thể xuất hiện khi code được biên dịch với một phiên bản thư viện nhưng runtime nạp phiên bản khác không có method descriptor tương ứng.

Dùng `javap -s -p` trên class thư viện thực tế để xem method và descriptor:

~~~bash
javap -classpath lib/dependency.jar -s -p com.example.Library
~~~

So sánh classpath lúc compile và runtime. `javap` cho biết method nào có trong class file đang kiểm tra; nó không tự phát hiện toàn bộ thứ tự class loader hoặc dependency conflict trong ứng dụng.

### 14.3. Kiểm tra annotation và generic metadata

Khi framework không nhận annotation hoặc generic type như mong đợi, dùng:

~~~bash
javap -v -p -classpath out demo.Model
~~~

Tìm các attribute như `RuntimeVisibleAnnotations`, `RuntimeInvisibleAnnotations`, `Signature` và `MethodParameters`.

Annotation có retention `SOURCE` không được giữ trong class file. Annotation có retention `CLASS` có thể được lưu nhưng không nhất thiết hiển thị qua reflection runtime. Annotation có retention `RUNTIME` được lưu để reflection có thể đọc.

## 15. javap không phải Java decompiler

`javap` disassemble class file và trình bày bytecode cùng metadata. Nó không tái tạo source Java ban đầu.

Một số lý do:

- Nhiều cấu trúc source khác nhau có thể sinh bytecode tương đương.
- Tên biến local có thể không được ghi.
- Comment và formatting source không nằm trong class file.
- Generic được type erasure ở runtime descriptor.
- Compiler có thể tạo synthetic method, bridge method hoặc bootstrap metadata.
- Tối ưu hóa và lowering làm cấu trúc bytecode khác source.

Nếu cần tái tạo source gần đúng từ class file, cần một decompiler chuyên dụng. Dù vậy, source decompile cũng chỉ là bản tái dựng; không thể khôi phục comment, formatting hoặc mọi quyết định viết code ban đầu.

`javap` phù hợp hơn khi câu hỏi là: class file có version nào, method descriptor ra sao, instruction nào được sinh, field/method/attribute nào tồn tại và bytecode tham chiếu đến class nào.

## 16. Quy trình thực hành từ source đến bytecode

Có thể dùng một quy trình lặp lại để hiểu một thay đổi Java:

1. Viết một ví dụ nhỏ với một cấu trúc cụ thể.
2. Biên dịch bằng JDK 17 và `--release 17`.
3. Dùng `javap -c -p` xem bytecode.
4. Dùng `javap -v` khi cần constant pool, version hoặc attributes.
5. Thay đổi một cấu trúc source và biên dịch lại.
6. So sánh bytecode trước/sau.
7. Chạy trên JVM mục tiêu để kiểm tra hành vi thực tế.

Ví dụ bộ lệnh:

~~~bash
javac --release 17 -g -d out src/demo/Calculator.java
javap -classpath out -c -p demo.Calculator
javap -classpath out -s demo.Calculator
javap -classpath out -v demo.Calculator
java -cp out demo.Calculator
~~~

Khi so sánh output, hãy giữ JDK/compiler version và tùy chọn biên dịch giống nhau. Thay đổi compiler version hoặc flags có thể làm bytecode khác dù source không đổi.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `javap` không tìm thấy class | Classpath không trỏ đến thư mục/JAR chứa class hoặc tên class sai | Dùng `-classpath` và tên đầy đủ có package |
| Class file có major version mới hơn runtime | Artifact được biên dịch bằng JDK mới hơn | Nâng runtime hoặc biên dịch với `--release` phù hợp |
| Không thấy bytecode trong output | Chưa dùng `-c` hoặc `-v` | Thêm `-c` |
| Không thấy private method/field | Output mặc định không hiển thị mọi member | Thêm `-p` |
| Không thấy local variable name | Class file không lưu `LocalVariableTable` | Biên dịch lại với `-g` nếu kiểm soát source |
| Không thấy generic type trong descriptor | Descriptor dùng type erasure | Xem `Signature` bằng `-v` |
| Không hiểu `#12`, `#25` | Đây là constant pool index | Đối chiếu phần Constant pool trong `-v` |
| Bytecode khác ví dụ | Compiler version/flags hoặc source khác | Kiểm tra JDK, `--release`, debug flags và source |
| Không hiểu `invokedynamic` | Dynamic linkage dùng bootstrap metadata | Xem `BootstrapMethods` với `-v` |
| Tưởng `javap` đã xác nhận class chạy được | Disassembly không thay thế runtime linking/verification | Chạy test trên JVM mục tiêu |
| Tưởng bytecode là mã máy CPU | Nhầm JVM instruction với native machine code | Phân biệt bytecode và JIT-compiled code |

## 18. Bài tập thực hành

### Bài 1 — Xem class file version

Biên dịch một class đơn giản bằng JDK 17 và `--release 17`. Dùng `javap -v` tìm `minor version` và `major version`. Giải thích ý nghĩa của major version 61.

### Bài 2 — Đọc phép cộng

Tạo method `add(int, int)`. Dùng `javap -c` để tìm `iload`, `iadd` và `ireturn`. Mô tả giá trị trên operand stack sau từng instruction.

### Bài 3 — Quan sát rẽ nhánh

Tạo method trả trị tuyệt đối hoặc kiểm tra số chẵn. Xem các instruction `if*`, `goto` và offset đích. Liên hệ với cấu trúc `if/else` trong source.

### Bài 4 — Descriptor

Tạo method nhận `String`, `long`, `int[]` và trả về `boolean`. Dùng `javap -s` để viết lại method descriptor. Giải thích descriptor của array và primitive.

### Bài 5 — Debug attributes

Biên dịch cùng source với `-g` và `-g:none`. Dùng `javap -l -v` so sánh `LineNumberTable` và `LocalVariableTable`.

### Bài 6 — Lambda và invokedynamic

Tạo một lambda và một phép nối chuỗi. Dùng `javap -c -v` tìm `invokedynamic` và `BootstrapMethods`. Xác định bootstrap method được tham chiếu.

### Bài 7 — Kiểm tra JAR

Đóng gói class vào JAR rồi dùng `javap -classpath app.jar -c -p` đọc class. Nếu là multi-release JAR, thử `--multi-release 17`.

### Bài 8 — Lỗi phiên bản

Biên dịch class với target release mới hơn runtime thử nghiệm. Quan sát `UnsupportedClassVersionError`, kiểm tra major version bằng `javap` và giải thích cách khắc phục.

## 19. Nguyên tắc cần nhớ

- `javac` biên dịch source Java thành class file chứa bytecode và metadata.
- Class file có magic number `CAFEBABE`; Java 17 thông thường dùng major version 61.
- Bytecode là instruction cho JVM, thường được mô tả bằng operand stack và local variable slots.
- Constant pool chứa literal và symbolic reference đến class, field, method, type và bootstrap metadata.
- Descriptor biểu diễn kiểu field/method ở cấp JVM; generic signature có thể lưu riêng.
- `javap -c` đọc bytecode; `-p` hiển thị private member; `-s` xem descriptor; `-l` xem debug table; `-v` xem chi tiết class file.
- Dùng `javac --release 17` để ràng buộc source level, class file version và API Java 17.
- `invokedynamic` cùng bootstrap metadata được dùng cho một số cấu trúc như lambda và string concatenation.
- `javap` là disassembler, không phải decompiler và không thay thế việc chạy class trên JVM mục tiêu.
- Khi điều tra lỗi tương thích, kiểm tra cả class file version, descriptor, dependency thực tế và runtime classpath/module path.

Hiểu class file và bytecode giúp nhìn rõ cầu nối giữa source Java và JVM. Với `javap`, lập trình viên có thể kiểm tra artifact đã biên dịch, xác định phiên bản class file, đọc instruction và metadata, từ đó điều tra lỗi tương thích hoặc hiểu cách compiler biểu diễn chương trình trong Java 17.
