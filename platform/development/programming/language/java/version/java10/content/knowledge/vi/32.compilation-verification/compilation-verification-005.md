# Kiểm tra class file và kiểu biến cục bộ bằng `javap` (Java 10+)

## 1. Mục tiêu bài học

Trong **Java 10**, **JEP 286 — Local-Variable Type Inference** bổ sung cú pháp `var` cho **khai báo biến cục bộ có biểu thức khởi tạo**. Khi gặp:

~~~java
var count = 21;
var label = "Java 10";
~~~

`javac` xác định **kiểu tĩnh** của từng biến **tại thời điểm biên dịch**: `count` là `int`, `label` là `String`. `var` **không** tạo một kiểu động đặc biệt ở runtime, không biến Java thành ngôn ngữ dynamic typing và không tạo opcode JVM mang tên `var`.

Câu hỏi thực hành: **làm sao kiểm chứng kiểu đã được suy luận sau khi biên dịch, không chỉ nhìn source code?** Công cụ chuẩn của JDK là **`javap`** (*class-file disassembler*). Với đúng tùy chọn `javac` và `javap`, bạn có thể đọc:

- **Class-file version** để biết định dạng class file mục tiêu.
- **Method descriptors** và bytecode như `iload`, `istore`, `aload`, `astore`.
- **`LocalVariableTable`**, ghi tên, JVM descriptor, slot và khoảng tồn tại của một biến cục bộ.
- **`LocalVariableTypeTable`**, ghi generic signature nếu biến có kiểu generic/tham số hóa.
- **`LineNumberTable`**, phục vụ gắn source line với bytecode, nếu debug data được giữ.
- **`Signature` attributes** khác, phục vụ kiểu generic của field/method/class khi có.

**Điểm quyết định:** những bảng biến cục bộ này là **debug metadata tùy chọn**. Bạn phải chủ động biên dịch với **`javac -g`** hoặc ít nhất **`-g:vars`** nếu muốn dễ nhìn thấy tên/kiểu cục bộ. `javap` không thể khôi phục đáng tin cậy tên biến và kiểu generic từ một class đã bị lược bỏ debug metadata.

Bài viết dùng ví dụ **Java 17+ chạy được**, đồng thời chỉ rõ mã nguồn `var` có từ **Java 10**. Công cụ và các định dạng class file này vẫn được tài liệu hóa trong **Oracle JDK 25/26**, không phải kỹ thuật legacy.

### Kết quả mong đợi

Sau bài, bạn sẽ tự làm được:

1. Biên dịch một chương trình dùng `var` và chạy để kiểm chứng kết quả chức năng.
2. Dùng `javap -c -l -p` xem bytecode và local-variable entries.
3. Dùng `javap -v` phân biệt **descriptor** và **generic signature**.
4. Giải thích vì sao source `var` và source khai báo kiểu tường minh có thể tạo **cùng bytecode**.
5. So sánh biên dịch với `-g`, `-g:vars`, mặc định và `-g:none`.
6. Phân biệt **`--release`**, `major version`, `StackMapTable`, `LocalVariableTable`, `MethodParameters`.
7. Tránh suy luận sai từ một dòng disassembly hoặc từ file `.class` đã bị tối ưu/obfuscate.
8. Sử dụng kết quả để debug, review và kiểm chứng build artifact, thay vì coi `javap` là Java source decompiler.

## 2. Từ Java source đến class file

Luồng xử lý giản lược:

~~~text
VarJavapDemo.java
      |
      |  javac kiểm tra cú pháp, xác định kiểu tĩnh của var
      v
Symbol/type checking và code generation
      |
      +---- bytecode + descriptors cần cho JVM
      |
      +---- debug metadata (nếu chọn -g/-g:vars)
      v
VarJavapDemo.class
      |
      |  javap -v -c -l -p
      v
Class version, bytecode, local slots, descriptor, generic signature
      |
      |  java -cp out VarJavapDemo
      v
JVM verification, linking, execution
~~~

**`javac`** là trình biên dịch; **`javap`** là công cụ **đọc/phân rã class file**. `javap` không chạy `main`, không tự biên dịch source, không tự xác minh rằng logic nghiệp vụ đúng. JVM khi nạp class còn thực hiện các kiểm tra riêng mà output `javap` không thay thế.

### 2.1. Phạm vi của `var` trong Java 10

`var` là một **reserved type name / contextual type identifier**, không phải một kiểu object Java và cũng không phải Java keyword dùng được ở mọi vị trí. Những dạng hợp lệ:

~~~java
var score = 21;                 // int
var greeting = "Hello";        // String
var names = java.util.List.of("A", "B"); // List<String>
~~~

Cú pháp `var` áp dụng cho biến cục bộ có initializer trong methods, constructors, initializer blocks; hỗ trợ biến trong vòng lặp `for` và enhanced `for`, cũng như khai báo tài nguyên trong `try-with-resources`.

Không hợp lệ ở Java 10:

~~~java
// Các ví dụ SAI, chỉ dùng để giải thích compiler errors:
// var missing;                // thiếu initializer
// var unknown = null;         // không suy ra được kiểu từ null đơn lẻ
// class Demo { var field = 1; } // field không được dùng var
// void f(var p) {}            // method parameter không được dùng var
// var f = x -> x + 1;         // lambda thiếu target type
~~~

Lưu ý phiên bản: **`var` trong tham số lambda** là bổ sung của **Java 11 (JEP 323)**, không thuộc Java 10. Đừng nhầm tính năng đó với cách suy luận kiểu biến cục bộ mà bài này kiểm chứng.

`var` không có nghĩa biến có thể tự đổi kiểu. Ví dụ:

~~~java
var n = 21;       // int
// n = "text";    // compile error: String không gán được cho int
~~~

Đây là **static type inference**, hoàn tất trước khi tạo bytecode.

## 3. Tại sao cần `javap`?

Khi chỉ nhìn code:

~~~java
var a = new java.util.ArrayList<String>();
var b = java.util.List.of("Ada", "Linh");
var c = b.get(0);
~~~

bạn có thể phân tích rằng:

- `a` có kiểu tĩnh `ArrayList<String>`.
- `b` có kiểu tĩnh `List<String>`.
- `c` có kiểu tĩnh `String`.

Nhưng trong dự án thực tế, biểu thức khởi tạo có thể gồm **generic inference, overload resolution, method chaining, wildcard capture, nested types và thư viện**. Cần phân biệt **kiểu compiler suy ra** và **đối tượng thực tế có `getClass()` ở runtime**.

`javap` giúp:

- Kiểm tra artifact thực sự được **`javac` tạo**, không chỉ suy luận bằng mắt.
- Tìm loại load/store JVM sẽ dùng cho primitive hay reference.
- Xem **erased descriptor** và, khi có debug data, **generic signature**.
- Đối chiếu một class do CI build với class do IDE build để phát hiện debug metadata khác nhau.
- Xác định có bao nhiêu local **slot**; hiểu `long`/`double` chiếm hai slot.
- Kiểm tra class-file major version trước khi deploy lên một runtime cũ hơn.

**Giới hạn quan trọng:** `javap` không phải source decompiler đầy đủ, không xác định chắc chắn source gốc có dùng `var` hay không. Một khai báo tường minh `int n = 21;` có thể tạo chính những bytecode và debug entries giống `var n = 21;`.

## 4. Các tùy chọn `javac` và `javap` cần nhớ

| Công cụ / cờ | Tác dụng |
| --- | --- |
| `javac -d out` | Lưu class files vào thư mục `out` |
| `javac -g` | Ghi đầy đủ debug information, gồm tên/kiểu local variables |
| `javac -g:vars` | Ghi debug data cho biến cục bộ |
| `javac -g:lines,vars,source` | Chọn rõ ba nhóm debug information |
| `javac -g:none` | Không ghi debug information tùy chọn |
| `javac --release 17` | Biên dịch theo API/ngôn ngữ và class-file target Java 17 |
| `javap -c` | In bytecode instructions của các methods |
| `javap -l` | In `LineNumberTable` và local variable tables khi có |
| `javap -v` | In chi tiết: version, constant pool, attributes, signatures... |
| `javap -p` | Hiển thị cả private members |
| `javap -s` | In JVM **descriptors** của members/methods |
| `javap -cp out` | Tìm user class files trong thư mục/JAR ở classpath |
| `javap -sysinfo` | In path, size, ngày sửa và hash của class được đọc |
| `javap --multi-release N` | Lựa chọn version tương ứng khi đọc multi-release JAR |

Bảng trên phản ánh công cụ JDK hiện hành; các tùy chọn có thể ghép:

~~~bash
javap -v -p -c -l -classpath out VarJavapDemo
~~~

Trong bài này, `-v` cho nhiều chi tiết nhất, còn `-c -l -p` thường đủ để xem bytecode/biến cục bộ. Output của `javap` phụ thuộc phiên bản JDK, compiler, class file và debug flags; không nên so sánh cố định từng **bytecode offset** giữa hai builds khác nhau.

### Phân biệt `--release` với `-g`

- `--release 17`: kiểm soát **ngôn ngữ, API và class-file target**.
- `-g`: kiểm soát **debug attributes** được chèn vào class file.

Chúng độc lập. Bạn có thể biên dịch **target Java 17** có debug data hoặc không. Thêm `-g` **không thay đổi kiểu tĩnh** mà `javac` suy luận từ biểu thức `var`.

### Kiểm tra JDK thực đang dùng

~~~bash
java -version
javac -version
javap -version
~~~

Trong CI, `javac` và `javap` nên thuộc JDK được chọn rõ ràng. Nếu `java` chạy một runtime khác với compiler, output version hoặc classpath có thể gây hiểu nhầm.

## 5. Chương trình Java 17+ hoàn chỉnh để kiểm chứng

Lưu file tên **VarJavapDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class VarJavapDemo {
    public static int inferred() {
        var number = 21;
        var doubled = number * 2;
        return doubled;
    }

    public static int explicit() {
        int number = 21;
        int doubled = number * 2;
        return doubled;
    }

    public static void main(String[] args) {
        var message = "Java 10";
        var names = List.of("Ada", "Linh");
        var copy = new ArrayList<>(names);
        var size = copy.size();

        System.out.println(
                "same result: " + (inferred() == explicit())
        );
        System.out.println("message: " + message);
        System.out.println("size: " + size);
    }
}
~~~

### 5.1. Phân tích kiểu trước khi chạy

| Biến cục bộ | Biểu thức khởi tạo | Kiểu tĩnh được suy luận |
| --- | --- | --- |
| `number` trong `inferred()` | `21` | `int` |
| `doubled` trong `inferred()` | `number * 2` | `int` |
| `message` | `"Java 10"` | `java.lang.String` |
| `names` | `List.of("Ada", "Linh")` | `java.util.List<String>` |
| `copy` | `new ArrayList<>(names)` | `java.util.ArrayList<String>` |
| `size` | `copy.size()` | `int` |

Kiểu của `names` và `copy` là **kiểu tham số hóa**, trong khi JVM descriptor sẽ biểu diễn **erasure** `List` và `ArrayList`.

### 5.2. Biên dịch và chạy

Trong thư mục chứa `VarJavapDemo.java`:

~~~bash
mkdir out
javac --release 17 -g -d out VarJavapDemo.java
java -cp out VarJavapDemo
~~~

**Stdout chính xác đã được kiểm chứng bằng JDK:**

~~~text
same result: true
message: Java 10
size: 2
~~~

Đầu ra xác định vì hai phương thức đều tính `21 * 2 = 42`, `List.of` có hai phần tử và chương trình không dùng thời gian, random hay network.

`--release 17` phù hợp với JDK 17+ và tạo **class-file major version 61**. Nếu muốn kiểm tra **đúng target Java 10**, trên một JDK còn hỗ trợ release target 10 có thể dùng:

~~~bash
javac --release 10 -g -d out VarJavapDemo.java
java -cp out VarJavapDemo
~~~

Đoạn code sử dụng những API đã có ở Java 10 (`List.of` có từ Java 9), nên phù hợp release 10. **Đã chạy trên OpenJDK 24 với `--release 10`**, kết quả stdout giống phần trên và class file có **major version 54**.

**Quan trọng:** không phải mọi JDK tương lai đều phải duy trì khả năng `--release 10` mãi mãi; `javac --help` liệt kê những release còn được hỗ trợ bởi compiler cụ thể. Nếu bản JDK không hỗ trợ target 10, dùng `--release 17` hoặc một target còn được hỗ trợ; đừng tự giả định compile sẽ thành công.

## 6. Xem class file bằng `javap` từng bước

Sau khi biên dịch với `-g`:

~~~bash
javap -classpath out VarJavapDemo
~~~

Lệnh trên in danh sách **fields/methods nhìn thấy được**. Để phân tích bytecode:

~~~bash
javap -c -p -classpath out VarJavapDemo
~~~

Để thấy tên/kiểu các biến cục bộ:

~~~bash
javap -c -l -p -classpath out VarJavapDemo
~~~

Để đọc chi tiết class file:

~~~bash
javap -v -p -c -l -classpath out VarJavapDemo
~~~

Nếu chạy từ một folder khác, thay `out` bằng classpath đúng. Với `javap`, bạn có thể truyền tên class `VarJavapDemo` và `-classpath out`, hoặc đường dẫn trực tiếp tới file class tùy lệnh.

### 6.1. Đọc class-file major version

Khi biên dịch với `--release 10`, một dòng trong `javap -v` là:

~~~text
major version: 54
~~~

Với `--release 17`:

~~~text
major version: 61
~~~

Bảng các mốc hữu ích:

| Target Java | Class-file major version |
| --- | --- |
| Java 8 | 52 |
| Java 9 | 53 |
| **Java 10** | **54** |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |
| Java 25 | 69 |
| Java 26 | 70 |

**Đừng nhầm version class file với version của `javap` đang chạy.** Nếu javac 24 biên dịch với `--release 10`, class file vẫn major **54** chứ không tự thành major 68.

Một JVM cũ thường không chạy được class file có major vượt mức nó hỗ trợ; lỗi điển hình là `UnsupportedClassVersionError`. Tuy vậy major version **chỉ** cho biết target class file, không tự bảo đảm mọi dependency trong classpath có cùng compatibility hay không.

### 6.2. JVM method descriptor không chứa tên `var`

Trong output verbose, phương thức:

~~~java
public static int inferred()
~~~

có method descriptor:

~~~text
descriptor: ()I
~~~

`()` biểu thị **không có parameters** và `I` biểu thị **return type int**.

Với `main(String[] args)`:

~~~text
descriptor: ([Ljava/lang/String;)V
~~~

`[Ljava/lang/String;` là tham số mảng `String[]`, `V` là void. Các descriptors này mô tả **method linkage/verification**, không liệt kê toàn bộ biến local trong thân phương thức.

**Kết luận:** nhìn `descriptor: ()I` không thể biết một local trong method có được khai báo bằng `var` hay `int`; cần xem bytecode và debug tables.

## 7. Các opcode chứng minh kiểu `int` đã được xác định

Với `inferred()`, một trích đoạn bytecode (đã quan sát trên OpenJDK 24 khi compile target Java 10) như sau:

~~~text
0: bipush        21
2: istore_0
3: iload_0
4: iconst_2
5: imul
6: istore_1
7: iload_1
8: ireturn
~~~

Giải thích từng lệnh:

| Opcode | Ý nghĩa |
| --- | --- |
| `bipush 21` | Đưa hằng `int 21` lên operand stack |
| `istore_0` | Lưu `int` vào local slot 0 |
| `iload_0` | Nạp `int` từ slot 0 |
| `iconst_2` | Đưa `int 2` lên operand stack |
| `imul` | Nhân hai `int` |
| `istore_1` | Lưu `int` kết quả vào slot 1 |
| `iload_1` | Nạp kết quả từ slot 1 |
| `ireturn` | Trả về giá trị `int` |

Hai phương thức:

~~~java
public static int inferred() {
    var number = 21;
    var doubled = number * 2;
    return doubled;
}

public static int explicit() {
    int number = 21;
    int doubled = number * 2;
    return doubled;
}
~~~

tạo **cùng chuỗi opcode** trên compiler được kiểm thử. Điều này chứng minh `var` được giải quyết **trong compiler**, còn JVM thực thi theo kiểu đã biết; không cần một opcode riêng cho `var`.

**Giới hạn suy luận:** việc hai phương thức tạo cùng chuỗi bytecode trong một ví dụ **không bảo đảm toàn bộ class file giống nhau từng byte**: tên phương thức khác, constant pool, line numbers, metadata và compiler options vẫn có thể khác.

### 7.1. Khi nào là `aload`/`astore`?

Với biến reference:

~~~java
var message = "Java 10";
~~~

compiler dùng nhóm opcode thao tác với **reference** như `aload`/`astore` trong những tình huống thích hợp.

Các nhóm thường gặp:

| JVM type/category | Nhóm opcode local |
| --- | --- |
| `int` và các primitive dùng int category (`boolean`, `byte`, `char`, `short`) | `iload` / `istore` |
| `long` | `lload` / `lstore` |
| `float` | `fload` / `fstore` |
| `double` | `dload` / `dstore` |
| Object references và arrays | `aload` / `astore` |

`aload` chỉ cho biết giá trị là **reference category**, **không** đủ để phân biệt `String`, `List<String>`, `ArrayList<String>` hay lớp ứng dụng khác. Vì thế cần **debug metadata**, signatures, method calls hoặc nguồn type information khác để suy luận thêm.

## 8. `LocalVariableTable`: tên, slot, phạm vi, JVM descriptor

Khi bạn dùng `javac -g`, `javap -v -l` có thể in bảng:

~~~text
LocalVariableTable:
  Start  Length  Slot  Name       Signature
      3      74     1  message    Ljava/lang/String;
     11      66     2  names      Ljava/util/List;
     20      57     3  copy       Ljava/util/ArrayList;
     26      51     4  size       I
~~~

Các số **Start/Length** ở trên lấy từ một lần build đã kiểm thử với **OpenJDK 24, `javac --release 10 -g`**. Đừng dựa vào chúng như một contract: compiler version/optimization thay đổi có thể tạo vị trí bytecode khác mà ngữ nghĩa vẫn đúng.

Ý nghĩa các cột:

- **`Start`**: bytecode offset (program counter) bắt đầu range mà entry áp dụng.
- **`Length`**: độ dài range tính theo bytecode offsets.
- **`Slot`**: chỉ số local-variable slot trong frame của method.
- **`Name`**: tên biến được lưu trong debug metadata.
- **`Signature`** ở header của **LocalVariableTable**: thực chất chứa **JVM field descriptor**, không phải generic type signature đầy đủ.

### 8.1. Khai báo `var` biến thành kiểu cụ thể

Các entry:

~~~text
size       I
message    Ljava/lang/String;
names      Ljava/util/List;
copy       Ljava/util/ArrayList;
~~~

không chứa cú pháp `var`. Thay vào đó:

- `I` nghĩa là **`int`**.
- `Ljava/lang/String;` nghĩa là **reference `java.lang.String`**.
- `Ljava/util/List;` là **erased type** `java.util.List`.
- `Ljava/util/ArrayList;` là **erased type** `java.util.ArrayList`.

Dấu `L...;` biểu diễn reference class/interface theo tên nội bộ với dấu `/`. Một mảng `String[]` có descriptor `[Ljava/lang/String;`.

### 8.2. Slot không phải tên biến hay địa chỉ RAM

Trong static `main`, slot 0 thường chứa parameter `String[] args`; các local variables có thể dùng slot 1, 2, 3... tùy compiler. Nhưng:

- **Slot index không phải physical memory address**.
- Slot có thể được **reuse** giữa các block có lifetime không chồng nhau.
- `long` và `double` chiếm **hai local slots**.
- Cấu trúc của slot không bảo đảm các biến Java source sẽ luôn tồn tại nguyên dạng lúc runtime.
- Với instance method, slot 0 thường là **`this`**; với static method không có `this`.

**`Start + Length` là phạm vi tồn tại của một entry debug trong bytecode**, không phải timestamp hoặc thời lượng sống của object trên heap.

## 9. `LocalVariableTypeTable`: cách nhìn thấy kiểu generic

Với hai biến:

~~~java
var names = List.of("Ada", "Linh");
var copy = new ArrayList<>(names);
~~~

compiler suy ra kiểu tham số hóa:

~~~text
List<String>
ArrayList<String>
~~~

Nhưng **JVM field descriptors thông thường áp dụng erasure**:

~~~text
Ljava/util/List;
Ljava/util/ArrayList;
~~~

Khi biên dịch với debug variable information, `LocalVariableTypeTable` có thể ghi thêm **generic signatures**:

~~~text
LocalVariableTypeTable:
  Start  Length  Slot  Name    Signature
     11      66     2  names   Ljava/util/List<Ljava/lang/String;>;
     20      57     3  copy    Ljava/util/ArrayList<Ljava/lang/String;>;
~~~

Hai entry này cũng đã được quan sát trong lần compile target Java 10 của ví dụ. Chúng bổ sung thông tin generic bị loại khỏi descriptor thường, chủ yếu để debugger có thể hiển thị local variable types hữu ích hơn.

### 9.1. Tại sao chỉ có một số biến nằm trong `LocalVariableTypeTable`?

Theo **JVMS §4.7.14**, bảng này phục vụ biến cục bộ có kiểu generic/tham số hóa/type variable cần chữ ký chi tiết. Những biến thông thường như `int` hay `String` thường chỉ cần `LocalVariableTable`.

| Local type | Descriptor ở LVT | Generic signature ở LVTT |
| --- | --- | --- |
| `int` | `I` | Thường không cần |
| `String` | `Ljava/lang/String;` | Thường không cần |
| `List<String>` | `Ljava/util/List;` | `Ljava/util/List<Ljava/lang/String;>;` |
| `ArrayList<String>` | `Ljava/util/ArrayList;` | `Ljava/util/ArrayList<Ljava/lang/String;>;` |

**`LocalVariableTypeTable` là attribute tùy chọn**, không có nghĩa mọi class file đều chứa nó. Khi build thiếu `-g:vars`, không nên đòi nó phải tồn tại.

### 9.2. `Signature` attribute và `LocalVariableTypeTable` có giống nhau?

Không hoàn toàn.

- **`Signature`** gắn với class, field hoặc method, mô tả những thông tin generic tương ứng ở nơi JVMS cho phép.
- **`LocalVariableTypeTable`** nằm bên trong **`Code` attribute của method**, mô tả kiểu generic của **local variables** trong một khoảng bytecode.
- **`LocalVariableTable`** chứa JVM descriptors và tên/slot/phạm vi của locals.

Khi `javap -v` hiển thị từ **Signature** ở nhiều nơi, bạn phải đọc **attribute scope** để hiểu đó là method generic signature hay local generic signature.

### 9.3. Runtime reflection có đọc được generic kiểu cục bộ không?

Java Reflection API có thể xem generic signature của **fields, method return types và method parameters** khi metadata phù hợp, nhưng **không cung cấp một API chung để lấy mọi local variable names/types trong method**. Không dùng `Method.getGenericReturnType()` rồi kỳ vọng lấy được danh sách `var` của một local block.

Nếu debug metadata thiếu, việc suy ngược `List<String>` từ JVM erased descriptor `Ljava/util/List;` **không đáng tin cậy**. `javap` có thể thấy generic table khi được ghi, chứ không thể khôi phục mọi generic local type từ bytecode đã bị erasure.

## 10. `-g`, `-g:vars`, mặc định, `-g:none`: khác nhau ra sao?

Thực hiện các lệnh vào **các thư mục output riêng**, không ghi đè class cũ:

~~~bash
mkdir out-all out-vars out-default out-none
javac --release 17 -g -d out-all VarJavapDemo.java
javac --release 17 -g:vars -d out-vars VarJavapDemo.java
javac --release 17 -d out-default VarJavapDemo.java
javac --release 17 -g:none -d out-none VarJavapDemo.java
~~~

Xem từng artifact:

~~~bash
javap -v -p -classpath out-all VarJavapDemo
javap -v -p -classpath out-vars VarJavapDemo
javap -v -p -classpath out-default VarJavapDemo
javap -v -p -classpath out-none VarJavapDemo
~~~

### 10.1. Kỳ vọng cần phân biệt

| Build | SourceFile / lines | Local variable names/types | Ghi chú |
| --- | --- | --- | --- |
| `-g` | Có nếu compiler tạo | Có `LocalVariableTable`; generic có thể có LVTT | Phù hợp khi học `javap` |
| `-g:vars` | Không yêu cầu mọi nhóm debug | Có local variable debug entries | Phục vụ trọng tâm bài |
| Mặc định `javac` | Thường có source + line info | Mặc định **không** có local variable debug tables | Không lạ nếu thiếu tên local |
| `-g:none` | Không thêm debug info tương ứng | Không có local-variable debug tables | Bytecode vẫn dùng được |

Oracle `javac` man page ghi rõ: mặc định tạo **line number** và **source file** information, còn muốn local-variable information phải thêm `-g` hoặc `-g:vars`.

**Không nhầm:** class file **không có `LocalVariableTable`** không có nghĩa Java source không có local variables. JVM vẫn chạy các opcode load/store qua local slots. Chỉ **metadata phục vụ debugger** không được giữ.

### 10.2. Kiểm chứng trên cùng source

~~~bash
javap -c -l -p -classpath out-all VarJavapDemo
javap -c -l -p -classpath out-none VarJavapDemo
~~~

Ở build `-g:none`, bạn vẫn thấy bytecode cho `inferred()`:

~~~text
bipush 21
istore_0
iload_0
iconst_2
imul
istore_1
iload_1
ireturn
~~~

Nhưng không có local table để gắn **slot 0 = `number`** hoặc **slot 1 = `doubled`** với tên nguồn. Nếu chỉ từ opcode, có thể nhận ra dữ liệu dạng `int`, nhưng **không khôi phục được đáng tin tên biến, generic arguments hoặc syntax `var`**.

## 11. `-parameters` không thay `-g:vars`

Một ngộ nhận thường gặp:

~~~bash
javac -parameters -d out VarJavapDemo.java
~~~

`-parameters` tạo thông tin **`MethodParameters`** phục vụ Reflection API đọc tên **method/constructor parameters**.

Ví dụ:

~~~java
static int add(int left, int right) {
    var result = left + right;
    return result;
}
~~~

- `left`, `right` là **method parameters**.
- `result` là **local variable**.

`-parameters` không phải tùy chọn bắt buộc lưu tên `result`. Muốn xem local variable name/type qua `javap`, dùng **`-g` hoặc `-g:vars`**.

Nếu cần cả parameter metadata dùng cho reflection/framework **và** local debugging, có thể dùng đồng thời:

~~~bash
javac --release 17 -parameters -g -d out VarJavapDemo.java
~~~

Nhưng không nên bật mọi metadata chỉ vì tò mò: với build sản phẩm có quy định về binary size, debug data/parameter names cần được quyết định theo khả năng vận hành và bảo mật.

## 12. Bytecode semantics: vì sao `var` không xuất hiện?

Xét hai khai báo:

~~~java
int number = 21;
var otherNumber = 21;
~~~

Trong compiler, `var` là yêu cầu **suy luận kiểu** từ initializer. Sau khi phân tích:

~~~text
number      : int
otherNumber : int
~~~

Với JVM, hai local đó là giá trị **`int`** nằm ở những local slots tương ứng. `javap` không có opcode như `varload` hay `varstore`.

**Điều `javap` có thể chứng minh:**

- Local table cho biết `number`/`doubled` có descriptor `I`.
- Bytecode dùng `iload`/`istore`.
- Generic local table có thể cho biết `names` là `List<String>` khi debug data có mặt.

**Điều `javap` KHÔNG chứng minh:**

- Người viết đã dùng từ khóa `var` hay gõ rõ kiểu tường minh.
- Compiler có suy luận theo cùng cách đối với source khác.
- Runtime object thật luôn có class trùng hệt static type của biến.
- Một generic argument luôn được lưu lại sau erasure.
- Mọi biến ở source đều có một slot riêng vĩnh viễn.

Bạn có thể dùng `javap` để kiểm chứng **kết quả thực thi kiểu ở mức class file**, nhưng nếu cần xác định **cú pháp source gốc**, phải có source hoặc source map/debug data phù hợp; class file không nhất thiết lưu thông tin đó.

## 13. Những khác biệt khó thấy của suy luận kiểu với `var`

### 13.1. Primitive vs wrapper

~~~java
var primitive = 1;              // int
var boxed = Integer.valueOf(1); // Integer
~~~

`javap` với debug data:

~~~text
primitive  I
boxed      Ljava/lang/Integer;
~~~

`primitive` và `boxed` không có cùng static type. Một phép tự động boxing/unboxing có thể xuất hiện ở những đường bytecode cần thiết. Không dùng `getClass()` để kiểm tra kiểu của `int` vì primitive không có method.

### 13.2. `var` với `new ArrayList<>()` và target typing

~~~java
var a = new java.util.ArrayList<>();
java.util.List<String> b = new java.util.ArrayList<>();
~~~

Trong dòng đầu, không có target type `List<String>` từ phía trái, nên diamond thường suy ra `ArrayList<Object>`. Dòng thứ hai có **target type** `List<String>`, nên generic inference có thêm ràng buộc.

**Tránh suy luận `var` luôn giữ đúng ý định generic của người đọc**. Viết rõ kiểu mục tiêu khi nó quan trọng:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
~~~

Hoặc đặt type witness:

~~~java
var names = new java.util.ArrayList<String>();
~~~

### 13.3. `var` không biến kiểu thành dynamic

~~~java
var value = "text";
// value = 42;  // compile-time error
~~~

LVT có thể ghi `value Ljava/lang/String;`; không có loại slot JVM `var` để thay đổi tùy ý thành `int`.

### 13.4. `var` với `null`

~~~java
// var unknown = null; // lỗi: không suy luận được kiểu
var known = (String) null; // hợp lệ: static type String
~~~

Trong trường hợp thứ hai, biến có kiểu `String` dù giá trị runtime có thể là `null`; xem class file metadata không tiết lộ **giá trị thực tại thời điểm chạy**.

### 13.5. Overload resolution đã hoàn tất tại compile-time

~~~java
static void print(Object value) { }
static void print(String value) { }

static void example() {
    var s = "hello"; // String
    print(s);         // overload print(String)
}
~~~

Khi có nhiều overload, compiler chọn method dựa trên **kiểu tĩnh**. `javap -c` có thể cho biết invoke tới method descriptor nào (ví dụ `(Ljava/lang/String;)V`). Điều này giúp kiểm tra một bug khi refactor dùng `var` làm static type khác với dự tính.

### 13.6. `var` với các kiểu suy luận không đơn giản

Suy luận kiểu có thể tạo kiểu chứa wildcard/capture/intersection trong một số ngữ cảnh. Khi debug metadata có mặt, JVM generic signature hoặc biểu diễn mà compiler chấp nhận có thể khó đọc; không có nghĩa tồn tại một class runtime riêng tên như toàn bộ chuỗi ký hiệu.

Với public API hoặc code có kiểu rất phức tạp, **khai báo kiểu tường minh** giúp reviewer nhận biết contract dễ hơn. `var` nên dùng khi initializer làm type rõ ràng, không phải ở mọi local declaration.

## 14. Cách đọc descriptors và generic signatures thực tế

Bảng descriptor cơ bản:

| Ký hiệu JVM | Kiểu Java |
| --- | --- |
| `Z` | `boolean` |
| `B` | `byte` |
| `C` | `char` |
| `S` | `short` |
| `I` | `int` |
| `J` | `long` |
| `F` | `float` |
| `D` | `double` |
| `V` | `void` (ở method return type) |
| `Ljava/lang/String;` | `java.lang.String` |
| `[I` | `int[]` |
| `[Ljava/lang/String;` | `String[]` |

Ví dụ generic signature:

~~~text
Ljava/util/List<Ljava/lang/String;>;
~~~

được đọc là `List<String>`.

Phân biệt:

~~~text
LVT descriptor:
    Ljava/util/List;

LVTT generic signature:
    Ljava/util/List<Ljava/lang/String;>;
~~~

LVT phù hợp với JVM type descriptor/erasure; LVTT thêm thông tin generic mà debugger có thể sử dụng. **Không** thể dùng generic metadata optional như chứng minh rằng JVM kiểm tra `String` ở mọi truy cập `List` runtime: generics Java có cơ chế erasure và compiler-enforced type safety.

## 15. `StackMapTable` là gì, có thay local debug table không?

Trong verbose output, có thể gặp:

~~~text
StackMapTable:
  number_of_entries: ...
~~~

**`StackMapTable`** phục vụ các type verification frames của JVM ở các vị trí bytecode quan trọng. Nó có thể mô tả trạng thái kiểu của operand stack và local variables theo **verification types**.

Nhưng:

- Nó **không phải** một bản dump `LocalVariableTable`.
- Nó **không bắt buộc lưu tên source variable**.
- Nó **không được thiết kế để giữ generic source type như `List<String>`**.
- Nó có thể xuất hiện dù build `-g:none`.

Do đó khi không thấy `LocalVariableTable` mà vẫn thấy `StackMapTable`, class file **không bị hỏng**; chúng phục vụ mục đích khác nhau.

### Vì sao bytecode vẫn kiểm tra được dù không có tên local?

JVM verifier dựa trên JVM class file, instructions, descriptors và verification types để đảm bảo các quy tắc an toàn class file. Nó **không cần** tên biến `number` hoặc `names` để chạy code, vì local slot/type đã được biểu diễn theo thông tin JVM cần.

## 16. `javap` và kiểm chứng build artifact thực tế

### 16.1. Kiểm tra đúng class đã build

~~~bash
javap -sysinfo -classpath out VarJavapDemo
~~~

Ở JDK hiện hành, `-sysinfo` có thể in **path, size, last-modified time và SHA-256 hash** của class đang đọc. Đây là cách xác minh bạn không vô tình đọc file `.class` cũ trên một classpath khác.

Không khẳng định mọi build có cùng SHA-256: debug flags, source timestamps, compiler differences và class-file attributes có thể làm hash thay đổi.

### 16.2. Kiểm tra package path

Nếu source có:

~~~java
package demo.verify;

public class Example {
    public static void main(String[] args) { }
}
~~~

thì compile:

~~~bash
javac -g -d out Example.java
~~~

sẽ đặt class trong đường dẫn dạng:

~~~text
out/demo/verify/Example.class
~~~

Dùng tên **fully qualified**:

~~~bash
javap -v -p -c -l -classpath out demo.verify.Example
~~~

Nếu `javap` báo **class not found**, trước tiên kiểm tra package name, output directory, classpath và tên class, thay vì kết luận compiler không ghi local type.

### 16.3. Đọc class trong JAR

Với artifact:

~~~bash
jar --create --file demo.jar -C out .
javap -c -l -p -classpath demo.jar VarJavapDemo
~~~

Với **multi-release JAR**, cần lưu ý `javap` mặc định có thể đọc **base entry** theo classpath, không phải entry được JVM chọn ở mọi runtime. `javap --multi-release <version>` là tùy chọn hiện hành giúp chỉ định version trong ngữ cảnh phù hợp; điều tra artifact multi-release cần kiểm tra entry/version được phân tích, tránh nhìn nhầm class.

Đối với file do build pipeline tạo, luôn kiểm tra **đúng JAR, đúng classloader/dependency version**; `javap` cho bạn biết **class được chỉ định**, không bảo đảm process sản xuất tải đúng artifact đó nếu runtime classpath/module path khác.

## 17. So sánh bytecode: dùng `var` có làm ứng dụng chạy nhanh hơn không?

Không có một quy luật “`var` nhanh hơn khai báo kiểu tường minh”. `var` là tiện ích **source syntax/type inference**.

Cùng ví dụ:

~~~java
var number = 21;
var doubled = number * 2;
~~~

và:

~~~java
int number = 21;
int doubled = number * 2;
~~~

có thể tạo **cùng bytecode** trong compiler hiện hành. Vì vậy:

- Không dựa vào `var` để tối ưu GC/allocation/JIT.
- Không lấy việc thiếu chữ `var` trong `javap` làm dấu hiệu compiler đã bỏ qua code.
- Không đưa ra benchmark `var` vs `int` rồi quy differences do type inference ở runtime: đó là quyết định compile-time.
- Khác biệt về hiệu năng sau refactor có thể đến từ **kiểu tĩnh thực sự khác**, overload/boxing/algorithm khác, chứ không phải bản thân từ `var`.

Đây cũng là lý do **đọc đúng loại bytecode** và **type signature** giúp kiểm chứng một thay đổi source có làm thay đổi semantics hay không.

## 18. Khi nào `javap` không hiển thị kiểu như bạn kỳ vọng?

| Tình huống | Giải thích có thể | Hướng xử lý |
| --- | --- | --- |
| Không thấy `LocalVariableTable` | Source compile mặc định hoặc `-g:none` | Recompile với `-g`/`-g:vars` nếu được phép |
| Có LVT nhưng thiếu `List<String>` | Descriptor bị erased | Xem `LocalVariableTypeTable` khi có |
| Chỉ thấy `I` | JVM descriptor cho `int` | Đọc bảng descriptor |
| Thấy `aload`, không biết kiểu object | Opcode chỉ thao tác reference | Xem LVT, call signatures và source |
| `javap` không tìm được class | Sai `-cp`, package, module hoặc JAR | Xác minh output artifact |
| Classfile major cao hơn runtime | Build target không phù hợp | `javac --release` theo platform đích |
| Local slot bị dùng cho hai biến | Compiler reuse slot vì lifetime không chồng nhau | Đọc `Start`/`Length`, không suy từ slot đơn lẻ |
| Không thấy tên generic trong build obfuscate | Debug data đã bị loại/sửa | Chỉ phân tích được metadata còn lại |
| `-parameters` có nhưng local names vẫn mất | Cờ này dành cho formal parameters | Thêm `-g:vars` |
| `javap` đọc sai JAR version | Multi-release JAR có nhiều class variants | Kiểm tra `--multi-release`/artifact |
| Bytecode khác giữa hai compiler | Compiler code generation có thể khác | So semantics, descriptors và output |
| Có `StackMapTable` nhưng thiếu LVT | Verification vs debug metadata khác nhiệm vụ | Không coi đó là lỗi |
| Generic local type khác source bạn đoán | Inference/target typing/erasure phức tạp | Xem compiler types và source context |

**Không cố “khôi phục” local names bằng cách đoán theo opcode** nếu kết quả dùng để review bảo mật/kiểm chứng chính xác. Thiếu metadata là giới hạn của artifact; cần source, build có debug symbols hoặc công cụ phân tích tin cậy phù hợp.

## 19. Bài tập thực hành và đáp án

### Bài 1 — tìm kiểu của `var`

~~~java
var count = 100;
var name = "Ada";
~~~

**Hỏi:** LVT sẽ dùng descriptors nào nếu biên dịch có local debug data?

**Đáp án:** `count I`; `name Ljava/lang/String;`. Cả hai là kiểu tĩnh đã được compiler xác định; không có descriptor `var`.

### Bài 2 — kiểm tra generic

~~~java
var names = java.util.List.of("A", "B");
~~~

**Hỏi:** Vì sao LVT thường chỉ có `Ljava/util/List;`?

**Đáp án:** JVM descriptor thể hiện **erasure**. Khi biên dịch `-g` và compiler ghi local generic info, LVTT có thể hiển thị `Ljava/util/List<Ljava/lang/String;>;`.

### Bài 3 — thiếu local variable name

**Hỏi:** `javap -c -l` vẫn có bytecode `istore_1` nhưng không thấy `LocalVariableTable`. Có phải chương trình không có biến cục bộ?

**Đáp án:** Không. Class file có slots/instructions, nhưng compiler không lưu metadata tên/kiểu locals; biên dịch lại với `javac -g` để có dữ liệu đó.

### Bài 4 — `-parameters` hay `-g`?

**Hỏi:** Muốn thấy tên `result` trong method `int add(int left,int right) { var result=left+right; return result; }`, cờ nào đúng?

**Đáp án:** `-g` hoặc `-g:vars`. `-parameters` dành cho `left` và `right` ở mức method-parameter metadata.

### Bài 5 — classfile target

**Hỏi:** Dùng JDK 24 compile `javac --release 10`, `javap -v` in major version nào?

**Đáp án:** **54**, đã xác minh bằng ví dụ thực nghiệm. Chạy không có `--release` trên JDK 24 thường ra target **68**, nhưng default có thể phụ thuộc flags/compiler.

### Bài 6 — `var` có type ở runtime không?

**Hỏi:** Cùng code `var x = 10;` và `int x = 10;` cho cùng `istore`. Có thể chứng minh source gốc dùng `var` bằng `javap` không?

**Đáp án:** Không. Chữ `var` là cú pháp source đã được compiler xử lý; bytecode không ghi “biến này khai báo bằng `var`”.

### Bài 7 — local slots và type width

**Hỏi:** Một biến `long` có local index 2. Nó sử dụng mấy slot?

**Đáp án:** **Hai**, slot 2 và 3, theo JVM local variable model. Không nhầm slot count với số object heap.

### Bài 8 — hiểu kiểu của List

~~~java
var list = new java.util.ArrayList<>();
~~~

**Hỏi:** Có được mặc định kiểu là `ArrayList<String>` chỉ vì về sau thêm một `String` không?

**Đáp án:** Không. Không có target type tường minh, generic inference có thể tạo `ArrayList<Object>`; thêm một phần tử String sau đó **không đổi kiểu tĩnh đã suy luận**.

### Bài 9 — source vs runtime

**Hỏi:** `var list = List.of("A")` suy ra `List<String>`. Có bảo đảm `list.getClass().getSimpleName()` trả `List<String>` không?

**Đáp án:** Không. `List<String>` là static/generic type; runtime class thực có thể là implementation nội bộ của `List.of`, và runtime class name không chứa type argument `String` theo kiểu đó.

### Bài 10 — phân biệt `Signature` và LVTT

**Hỏi:** Thấy trong `javap -v` một `Signature` ở field của class và một `LocalVariableTypeTable` trong method. Có phải cùng một attribute không?

**Đáp án:** Không. Chúng ở **scope** khác nhau: generic field/method/class vs local generic variables trong Code attribute.

### Bài 11 — lệnh nào phù hợp?

**Hỏi:** Để xem cùng lúc bytecode, private members, debug locals và class attributes, dùng lệnh nào?

**Đáp án:**

~~~bash
javap -v -p -c -l -classpath out VarJavapDemo
~~~

Điều kiện là class file đã được biên dịch với local debug data nếu muốn nhìn LVT/LVTT.

### Bài 12 — thay đổi type thật

**Hỏi:** Nếu refactor `List<String> a = List.of("x");` thành `var a = new ArrayList<String>();`, đây có phải chỉ thay syntax bằng `var`?

**Đáp án:** Không. Kiểu tĩnh đổi từ **`List<String>`** sang **`ArrayList<String>`**, đồng thời biểu thức khởi tạo đổi. Refactor như vậy có thể ảnh hưởng overload resolution và hành vi ứng dụng. Đừng quy toàn bộ thay đổi cho `var`.

## 20. Checklist khi kiểm chứng class file của một build Java

- [ ] Xác nhận **JDK version**, `javac -version`, `javap -version`.
- [ ] Chọn `--release` đúng platform mục tiêu; kiểm tra target được compiler hiện tại hỗ trợ.
- [ ] Biên dịch với `-g` hoặc `-g:vars` nếu cần tên/kiểu local.
- [ ] Chạy chương trình để kiểm tra chức năng, ghi lại stdout **đúng theo code**.
- [ ] Dùng `javap -v` kiểm tra **major version** và descriptors.
- [ ] Dùng `javap -c` đọc opcode cho primitive/reference.
- [ ] Dùng `javap -l` xem **LocalVariableTable** (nếu có).
- [ ] Đọc **LocalVariableTypeTable** khi biến có generic type.
- [ ] Không coi `Signature` của field/method là generic info của mọi local.
- [ ] Không nhầm `MethodParameters`/`-parameters` với `-g:vars`.
- [ ] Phân biệt **slot** và **bytecode range** với source variable lifetime, đừng xem slot là RAM address.
- [ ] Ghi rõ nếu build `-g:none` khiến không thể xác định local names/types.
- [ ] Xác nhận đang phân tích đúng classpath, đúng package, đúng JAR/module.
- [ ] Nếu artifact là multi-release JAR, xem đúng class version cần phân tích.
- [ ] Không suy từ class file rằng source đã dùng `var` hoặc explicit type.
- [ ] Dùng source và tests để kiểm chứng semantics, vì `javap` không thay thế unit/integration testing.

## 21. Tóm tắt nhanh

| Câu hỏi | Kết luận |
| --- | --- |
| `var` từ đâu? | **JEP 286, Java 10**, local-variable type inference |
| `var` là dynamic type không? | **Không**, compiler suy luận kiểu tĩnh |
| Có `var` opcode không? | **Không**; dùng opcode theo kiểu JVM đã xác định |
| Muốn xem locals? | **`javac -g`** rồi **`javap -c -l -p`** |
| Muốn xem kiểu generic `List<String>`? | Xem **`LocalVariableTypeTable`** nếu được phát hành |
| LVT có giữ generic đầy đủ không? | **Không**; descriptor áp dụng erasure |
| `-parameters` đủ cho local names? | **Không** |
| Thiếu LVT có nghĩa class sai? | **Không**; debug metadata là tùy chọn |
| Java 10 class-file major version? | **54** |
| Java 17 class-file major version? | **61** |
| Có thể nhìn bytecode để biết source dùng `var` không? | **Không đáng tin**, `var` và explicit typing có thể ra cùng bytecode |
| `javap` thay tests được không? | **Không**; nó là công cụ quan sát class file |

## 22. Nguồn tài liệu chính thức

1. [OpenJDK — JEP 286: Local-Variable Type Inference (Java 10)](https://openjdk.org/jeps/286).
2. [dev.java — Using the var Type Identifier](https://dev.java/learn/language-basics/using-var/).
3. [Oracle Java SE 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html).
4. [Oracle JDK 25 — The javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `-g`, `-g:vars`, `-g:none`, `--release`, `-parameters`.
5. [Oracle JDK 25 — The javap Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): `-c`, `-l`, `-v`, `-p`, `-s`, `-sysinfo`, `--multi-release`.
6. [Java Virtual Machine Specification SE 25 — Chapter 4, Class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html): đặc biệt §4.3 descriptors, §4.7.13 `LocalVariableTable`, §4.7.14 `LocalVariableTypeTable` và các attributes liên quan.
7. [Java Virtual Machine Specification SE 25 — Chapter 6, Instruction Set](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html): `iload`, `istore`, `aload`, `astore`.
8. [Oracle JDK 25 — Class-File API / LocalVariableTableAttribute](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/attribute/LocalVariableTableAttribute.html): cách mô hình hóa debug metadata trong API class file hiện đại.
9. [OpenJDK — JEP 323: Local-Variable Syntax for Lambda Parameters (Java 11)](https://openjdk.org/jeps/323): mốc riêng để không gán khả năng lambda-parameter `var` cho Java 10.

**Kết luận:** Trong Java 10+, `var` chỉ giúp **viết ngắn khai báo biến cục bộ**; `javac` vẫn xác định kiểu tĩnh và tạo bytecode JVM thông thường. Muốn biết class file thể hiện kiểu đó thế nào, hãy **biên dịch có debug locals**, dùng **`javap -v -c -l -p`**, đọc **descriptor ở LocalVariableTable** và **generic signature ở LocalVariableTypeTable**. Nhưng hãy nhớ metadata này **tùy chọn**, và `javap` **không thể chứng minh** source ban đầu đã gõ `var` thay vì một kiểu tường minh.
