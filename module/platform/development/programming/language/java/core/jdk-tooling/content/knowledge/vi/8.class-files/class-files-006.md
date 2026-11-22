# Attribute trong Java class file

Trong định dạng Java class file, **attribute** là cấu trúc metadata có độ dài xác định, dùng để mô tả thêm thông tin về lớp, trường, phương thức, đoạn bytecode hoặc record component. Attribute cho JVM và các công cụ như compiler, debugger, decompiler, bytecode analyzer biết cách diễn giải những đặc điểm bổ sung của chương trình.

Ví dụ, class file có thể chứa attribute mô tả:

- Mã bytecode của một phương thức và bảng xử lý exception.
- Dòng mã nguồn tương ứng với vị trí bytecode.
- Tên biến cục bộ phục vụ debug.
- Annotation cần đọc bằng reflection.
- Chữ ký generic mà bytecode đã xóa kiểu.
- Quan hệ module, record, sealed class hoặc lớp lồng nhau.
- Dữ liệu bootstrap phục vụ `invokedynamic` và dynamic constant.

Attribute là một phần của **binary format**. Nó không đồng nghĩa với annotation trong mã nguồn: annotation là một cách khai báo metadata, còn `RuntimeVisibleAnnotations`, `RuntimeInvisibleAnnotations` và các attribute liên quan là một số dạng biểu diễn metadata đó trong class file.

## 1. Vị trí của attribute trong class file

Một class file có cấu trúc tổng thể gồm magic number, phiên bản, constant pool, thông tin lớp, interfaces, fields, methods và danh sách attribute:

~~~text
ClassFile {
    magic
    minor_version
    major_version
    constant_pool
    access_flags
    this_class
    super_class
    interfaces[]
    fields[]
    methods[]
    attributes[]
}
~~~

Mỗi cấu trúc `field_info` và `method_info` cũng có danh sách attribute riêng. Một số attribute lại chứa danh sách attribute con. Ví dụ, `Code` chứa bytecode của phương thức và có các attribute lồng bên trong để mô tả line number, local variable hoặc stack map.

Vì vậy, attribute có thể xuất hiện ở nhiều cấp:

- **Class-level:** metadata của toàn bộ lớp, ví dụ `SourceFile`, `InnerClasses`, `NestMembers`, `Record`.
- **Field-level:** metadata của trường, ví dụ `ConstantValue`, `Signature`, annotation.
- **Method-level:** metadata của phương thức, ví dụ `Code`, `Exceptions`, `MethodParameters`, `AnnotationDefault`.
- **Code-level:** metadata gắn với phần bytecode, ví dụ `LineNumberTable`, `LocalVariableTable`, `StackMapTable`.
- **Record-component-level:** metadata của từng thành phần record, bao gồm generic signature và annotation phù hợp.

Không phải attribute nào cũng được phép xuất hiện ở mọi cấp. Vị trí hợp lệ và nội dung của từng attribute được định nghĩa trong Java Virtual Machine Specification (JVMS).

## 2. Cấu trúc nhị phân chung của `attribute_info`

Trong class file, mỗi attribute tuân theo cấu trúc tổng quát:

~~~text
attribute_info {
    u2 attribute_name_index;
    u4 attribute_length;
    u1 info[attribute_length];
}
~~~

Ý nghĩa:

| Trường | Kích thước | Ý nghĩa |
|---|---:|---|
| `attribute_name_index` | 2 byte (`u2`) | Chỉ số trỏ đến mục `CONSTANT_Utf8_info` trong constant pool, chứa tên attribute |
| `attribute_length` | 4 byte (`u4`) | Số byte của phần dữ liệu `info` |
| `info` | Theo độ dài | Dữ liệu riêng của attribute |

Ví dụ, tên `Code`, `SourceFile` hoặc `Signature` được lưu dưới dạng UTF-8 constant trong constant pool. `attribute_name_index` trỏ đến mục tương ứng. Phần `info` được diễn giải theo định nghĩa riêng của từng loại attribute.

Cấu trúc có độ dài tường minh giúp trình đọc class file biết điểm bắt đầu và kết thúc của mỗi attribute. Một công cụ có thể bỏ qua attribute mà nó không hiểu bằng cách dùng `attribute_length` để chuyển đến attribute tiếp theo.

**Lưu ý:** `u2` và `u4` là kiểu số nguyên không dấu trong mô tả định dạng class file, không phải kiểu dữ liệu Java có tên tương ứng. Khi tự viết parser, cần đọc đúng big-endian và kiểm soát biên mảng/độ dài trước khi truy cập dữ liệu.

## 3. Attribute khác constant pool, descriptor và access flag

Các thành phần trong class file có vai trò riêng:

| Thành phần | Mục đích |
|---|---|
| Constant pool | Lưu hằng số, tên lớp, tên trường/phương thức, chuỗi và symbolic reference |
| Descriptor | Mô tả kiểu trường và chữ ký kiểu tham số/kiểu trả về ở mức JVM |
| Access flags | Biểu diễn modifier như `public`, `final`, `static`, `abstract` theo định dạng class file |
| Attribute | Bổ sung metadata hoặc dữ liệu có cấu trúc cho class, field, method, code và record component |

Ví dụ, phương thức:

~~~java
public String greet(int count) {
    return "hello";
}
~~~

có descriptor JVM:

~~~text
(I)Ljava/lang/String;
~~~

Descriptor mô tả kiểu tham số và kiểu trả về đã được biểu diễn ở mức JVM. Attribute `Signature` có thể bổ sung thông tin generic mà descriptor không thể hiện, còn `Code` chứa bytecode thực thi phương thức.

Không nên coi mọi thông tin trong class file là attribute. Tên lớp, descriptor, access flags và constant pool có cấu trúc riêng trong định dạng.

## 4. `Code` — attribute chứa bytecode của phương thức

`Code` là một trong những attribute quan trọng nhất. Nó xuất hiện trong `method_info` của phương thức có phần thân bytecode. Phương thức `abstract` hoặc `native` không có bytecode thân phương thức nên không có `Code` attribute tương ứng.

Một `Code` attribute chứa các thành phần chính:

- `max_stack`: độ sâu tối đa cần thiết của operand stack trong phương thức.
- `max_locals`: số slot local variable cần thiết trong frame.
- `code_length`: số byte của mảng bytecode.
- `code[]`: các instruction bytecode.
- `exception_table[]`: các vùng bytecode và handler xử lý exception.
- `attributes[]`: các attribute lồng bên trong `Code`.

Minh họa:

~~~text
method_info
  |
  +-- Code
        |
        +-- max_stack
        +-- max_locals
        +-- code[]
        +-- exception_table[]
        +-- attributes[]
              |
              +-- LineNumberTable
              +-- LocalVariableTable
              +-- StackMapTable
~~~

Ví dụ với phương thức:

~~~java
static int add(int left, int right) {
    return left + right;
}
~~~

Compiler tạo các instruction tương đương với việc nạp hai biến local, cộng chúng trên operand stack và trả kết quả. `Code` lưu chuỗi instruction thực tế; không nên suy luận rằng mỗi câu lệnh Java tương ứng chính xác một instruction.

### 4.1. Exception table trong `Code`

`exception_table` mô tả các vùng bytecode được bảo vệ và vị trí handler. Mỗi entry chứa:

- `start_pc`: vị trí bytecode bắt đầu vùng được bảo vệ.
- `end_pc`: vị trí kết thúc vùng, theo quy tắc biên của định dạng.
- `handler_pc`: vị trí bytecode của handler.
- `catch_type`: kiểu exception cần bắt; giá trị đặc biệt có thể biểu diễn catch-all/finally handler.

JVM dùng bảng này khi exception được ném trong vùng tương ứng để xác định handler phù hợp. Đây là cơ chế bytecode-level cho `try-catch`, không phải danh sách khai báo `throws` của phương thức.

## 5. Attribute phục vụ debug

Compiler có thể ghi thêm metadata để debugger ánh xạ bytecode về mã nguồn.

### 5.1. `SourceFile`

`SourceFile` lưu tên tệp nguồn được dùng để biên dịch class, thường là tên như `AttributeDemo.java`. Nó không chứa toàn bộ nội dung source code và cũng không đảm bảo tệp nguồn còn tồn tại trên máy chạy.

### 5.2. `LineNumberTable`

`LineNumberTable` ánh xạ offset bytecode sang số dòng nguồn. Debugger dùng thông tin này để đặt breakpoint theo dòng và hiển thị vị trí gần đúng khi chương trình dừng.

Một dòng Java có thể tương ứng với nhiều instruction, hoặc không tạo instruction riêng. Do đó, line mapping là metadata hỗ trợ debug chứ không phải ánh xạ một-một giữa dòng và bytecode.

### 5.3. `LocalVariableTable`

`LocalVariableTable` lưu tên biến local, descriptor, slot index và khoảng bytecode mà biến có hiệu lực. Debugger có thể dùng nó để hiển thị tên biến và giá trị trong stack frame.

Thông tin này phụ thuộc tùy chọn debug khi biên dịch. Nếu compiler không phát sinh local-variable debug metadata, debugger có thể chỉ hiển thị tên slot hoặc không hiển thị tên biến như trong source.

### 5.4. `LocalVariableTypeTable`

`LocalVariableTypeTable` bổ sung generic signature cho biến local khi cần. `LocalVariableTable` thường mô tả kiểu sau erasure bằng descriptor; bảng type bổ sung giúp debugger/tooling biết thông tin generic như `List<String>`.

### 5.5. `SourceDebugExtension`

`SourceDebugExtension` có thể lưu thông tin debug mở rộng, ví dụ dữ liệu SMAP trong các quy trình sinh mã hoặc biến đổi source. Công cụ debug có thể dùng dữ liệu này để ánh xạ mã được sinh ra về ngôn ngữ hoặc tệp nguồn ban đầu.

### 5.6. Điều khiển debug metadata bằng `javac`

Các tùy chọn thường dùng:

~~~text
javac -g -d out AttributeDemo.java
javac -g:none -d out AttributeDemo.java
javac -g:lines,source -d out AttributeDemo.java
javac -g:lines,vars,source -d out AttributeDemo.java
~~~

- `-g` yêu cầu tạo toàn bộ thông tin debug mà compiler hỗ trợ.
- `-g:none` không tạo thông tin debug.
- `-g:lines,source` chọn line number và source file.
- `-g:lines,vars,source` chọn line number, local variable và source file.

Tùy chọn này tác động đến metadata debug trong class file, không thay đổi ý nghĩa logic của chương trình. Một số build tool hoặc IDE có thể đặt cấu hình debug riêng.

## 6. Attribute liên quan đến hằng số và khai báo

### 6.1. `ConstantValue`

`ConstantValue` gắn với field để biểu diễn giá trị khởi tạo hằng số phù hợp trong class file. Trường hợp điển hình là `static final` primitive hoặc `String` được khởi tạo bằng compile-time constant expression.

Ví dụ:

~~~java
public class Limits {
    public static final int MAX_RETRIES = 3;
    public static final String MODE = "safe";
}
~~~

Compiler có thể phát sinh `ConstantValue` cho các trường trên. JVM dùng metadata này khi khởi tạo giá trị trường theo quy tắc class file.

Không phải mọi trường `final` đều có `ConstantValue`. Ví dụ:

~~~java
public static final int MAX = Integer.parseInt("3");
~~~

Biểu thức gọi phương thức không phải compile-time constant expression, vì vậy compiler thường tạo mã khởi tạo trong `<clinit>` thay vì dùng `ConstantValue`.

Ngoài ra, Java compiler có thể inline giá trị compile-time constant vào mã của lớp sử dụng. Nếu thay đổi giá trị hằng số trong thư viện, các lớp client đã biên dịch trước đó có thể tiếp tục dùng giá trị cũ cho đến khi được biên dịch lại.

### 6.2. `Exceptions`

`Exceptions` liệt kê các exception type được khai báo trong mệnh đề `throws` của phương thức.

Ví dụ:

~~~java
void load() throws java.io.IOException {
    // ...
}
~~~

Attribute này lưu metadata khai báo để compiler, IDE và công cụ phản ánh API. JVM không dùng nó để thực thi cơ chế checked exception; checked exception là quy tắc của ngôn ngữ và compiler. Bytecode vẫn có thể ném exception không được liệt kê trong `Exceptions`.

### 6.3. `Signature`

`Signature` lưu generic signature cho class, field, method hoặc record component khi cần. Nó bảo toàn thông tin generic mà descriptor JVM đã xóa kiểu không thể biểu diễn đầy đủ.

Ví dụ:

~~~java
public class Box<T> {
    public T get() {
        return null;
    }
}
~~~

Ở mức JVM, kiểu `T` bị erasure thành giới hạn tương ứng, thường là `Object` nếu không có bound cụ thể. Descriptor của `get()` phản ánh kiểu đã xóa; `Signature` lưu dạng generic để reflection và công cụ có thể khôi phục thông tin `T`.

`Signature` không làm JVM thực thi generic theo kiểu reified. Generic Java vẫn dựa trên type erasure; attribute chỉ giữ metadata khai báo.

### 6.4. `MethodParameters`

`MethodParameters` lưu tên và một số cờ của tham số phương thức hoặc constructor. Compiler có thể phát sinh attribute này khi dùng:

~~~text
javac -parameters -d out AttributeDemo.java
~~~

Reflection đọc thông tin qua `Executable.getParameters()`, `Parameter.getName()` và `Parameter.isNamePresent()`.

Không nhầm `MethodParameters` với `LocalVariableTable`:

- `MethodParameters` là metadata tên tham số ở cấp method và hỗ trợ reflection.
- `LocalVariableTable` là debug metadata về biến local/slot và phạm vi bytecode.
- `-g:vars` và `-parameters` phục vụ hai mục tiêu khác nhau.

Nếu thiếu `MethodParameters`, `Parameter.isNamePresent()` thường trả về `false`; tên trả về có thể là dạng tổng hợp như `arg0`, không phải tên gốc trong source.

### 6.5. `Synthetic` và `Deprecated`

`Synthetic` cho biết một thành phần được compiler sinh ra và không xuất hiện trực tiếp như một khai báo tương ứng trong source theo nghĩa thông thường. Class file cũng có thể biểu diễn synthetic bằng access flag `ACC_SYNTHETIC`, tùy vị trí và cấu trúc.

`Deprecated` là attribute đánh dấu một thành phần đã deprecated ở mức class file. Annotation `@Deprecated` cũng có thể được lưu trong các annotation attribute; công cụ nên đọc metadata theo mục đích thay vì chỉ dựa vào một dấu hiệu duy nhất.

## 7. Attribute của annotation

Annotation trong Java được biểu diễn bằng nhiều attribute class file, tùy vị trí và retention.

| Attribute | Công dụng |
|---|---|
| `RuntimeVisibleAnnotations` | Annotation có thể đọc bằng reflection runtime |
| `RuntimeInvisibleAnnotations` | Annotation không được reflection runtime thông thường trả về, nhưng được lưu trong class file |
| `RuntimeVisibleParameterAnnotations` | Annotation runtime-visible trên tham số phương thức |
| `RuntimeInvisibleParameterAnnotations` | Annotation runtime-invisible trên tham số |
| `RuntimeVisibleTypeAnnotations` | Type-use annotation runtime-visible |
| `RuntimeInvisibleTypeAnnotations` | Type-use annotation runtime-invisible |
| `AnnotationDefault` | Giá trị mặc định của một thành viên annotation type |

Ví dụ:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Marker {
    String value();
}

@Marker("example")
public class AnnotatedType {
}
~~~

Annotation `@Marker("example")` có retention `RUNTIME`, vì vậy class file lưu nó trong attribute runtime-visible phù hợp. Reflection có thể đọc:

~~~java
Marker marker = AnnotatedType.class.getAnnotation(Marker.class);
System.out.println(marker.value());
~~~

Stdout:

~~~text
example
~~~

Nếu annotation dùng `RetentionPolicy.CLASS`, compiler vẫn lưu metadata nhưng reflection runtime thông thường không trả về annotation đó. Với `RetentionPolicy.SOURCE`, annotation bị loại khỏi class file sau biên dịch.

Annotation processing lúc compile và annotation reflection lúc runtime là hai cơ chế khác nhau. Processor đọc annotation qua compiler model; reflection đọc annotation runtime-visible từ class file khi ứng dụng chạy.

## 8. Attribute phục vụ class lồng nhau, nest, record và sealed class

Các phiên bản Java mới bổ sung attribute để mô tả cấu trúc ngôn ngữ và quan hệ lớp.

### 8.1. `InnerClasses`

`InnerClasses` mô tả các lớp thành viên hoặc lớp lồng nhau liên quan đến class file. Nó cung cấp thông tin như lớp trong, lớp ngoài, tên đơn giản và access flags tương ứng.

### 8.2. `EnclosingMethod`

`EnclosingMethod` chỉ ra lớp và method/constructor bao quanh một lớp cục bộ hoặc anonymous class. Tooling có thể dùng metadata này để hiểu nơi lớp được khai báo.

### 8.3. `NestHost` và `NestMembers`

Nestmate metadata biểu diễn quan hệ nest giữa các lớp có quyền truy cập private trong cùng nest. Một lớp thành viên có thể trỏ đến nest host, còn host liệt kê các nest member phù hợp.

Cơ chế này hỗ trợ truy cập private giữa các nestmate mà không cần compiler sinh accessor method như một số cơ chế cũ.

### 8.4. `Record`

`Record` mô tả các record component của một record class. Nó lưu tên, descriptor và metadata liên quan đến từng component. Record component cũng có thể có generic signature và annotation phù hợp.

Ví dụ:

~~~java
public record Point(int x, int y) {
}
~~~

Class file có thể chứa `Record` attribute để biểu diễn hai component `x` và `y`. Ngoài ra record còn có các thành viên được compiler sinh như accessor, constructor và các phương thức tiêu chuẩn.

### 8.5. `PermittedSubclasses`

`PermittedSubclasses` lưu danh sách lớp được phép kế thừa hoặc implement một sealed class/interface.

Ví dụ:

~~~java
public sealed interface Shape permits Circle, Rectangle {
}

final class Circle implements Shape {
}

final class Rectangle implements Shape {
}
~~~

Metadata này cho phép JVM và tooling kiểm tra tập kiểu con được cho phép theo quy tắc sealed type.

## 9. Attribute của module và `invokedynamic`

### 9.1. Module attributes

Khi biên dịch `module-info.java`, class file của module descriptor có thể chứa các attribute:

- `Module`: tên module, flags, version, requires, exports, opens, uses và provides.
- `ModulePackages`: danh sách package thuộc module khi cần.
- `ModuleMainClass`: lớp chính được chỉ định cho module khi có.
- `ModuleTarget`, `ModuleResolution`, `ModuleHashes`: metadata bổ sung phục vụ một số quy trình module/toolchain.

Các attribute này cho phép JVM và công cụ hiểu module graph và metadata đóng gói. Chúng thường xuất hiện trong class file đặc biệt `module-info.class`.

### 9.2. `BootstrapMethods`

`BootstrapMethods` cung cấp thông tin bootstrap method và đối số bootstrap cho các constant pool entry dạng `CONSTANT_InvokeDynamic_info` hoặc dynamic constant tương ứng.

Các ngôn ngữ Java hiện đại có thể dùng `invokedynamic` cho string concatenation, lambda và method reference. Khi class file chứa các call site cần bootstrap, attribute này lưu dữ liệu để JVM liên kết call site theo cơ chế được đặc tả.

Không phải mọi phương thức đều có `BootstrapMethods`. Attribute chỉ xuất hiện khi class file có nội dung cần bootstrap tương ứng.

## 10. `StackMapTable` và bytecode verification

`StackMapTable` là attribute bên trong `Code`, lưu các stack map frame phục vụ bytecode verifier. Frame mô tả trạng thái kiểu của local variables và operand stack tại các vị trí bytecode nhất định.

JVM dùng thông tin này trong quá trình verification để kiểm tra bytecode có tuân thủ các quy tắc an toàn kiểu hay không, chẳng hạn không dùng một giá trị theo kiểu không tương thích với trạng thái frame.

Một số điểm cần nhớ:

- `StackMapTable` là metadata verification, không phải snapshot của Java thread stack lúc chương trình chạy.
- Compiler thường sinh stack map frame khi biên dịch mã Java.
- Các công cụ biến đổi bytecode phải cập nhật frame phù hợp; nếu bytecode và stack map không nhất quán, JVM có thể từ chối nạp lớp với lỗi verification.
- `-Xverify:all` có thể yêu cầu JVM verification nghiêm ngặt hơn trong một số môi trường, nhưng tùy chọn và hành vi cần được kiểm tra theo phiên bản JDK.

Phân biệt `StackMapTable` với `LineNumberTable` và `LocalVariableTable`: một loại phục vụ verification, hai loại còn lại chủ yếu phục vụ debug.

## 11. Xem attribute bằng `javap -v`

`javap` là công cụ đi kèm JDK để đọc thông tin class file. Tùy chọn `-v` hoặc `-verbose` hiển thị thông tin chi tiết, bao gồm constant pool và attribute.

Tạo `AttributeDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Marker {
    String value();
}

@Marker("class")
public class AttributeDemo {
    private static final int LIMIT = 3;

    @Marker("method")
    public static <T> T identity(T value) {
        return value;
    }

    public static String label(String name) {
        return "Hello, " + name + " (" + LIMIT + ")";
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        System.out.println(identity("Java"));
        System.out.println(label("Java"));

        Method method =
                AttributeDemo.class.getDeclaredMethod("identity", Object.class);

        System.out.println(method.getParameters()[0].getName());
        System.out.println(method.getParameters()[0].isNamePresent());
        System.out.println(AttributeDemo.class.getAnnotation(Marker.class).value());
        System.out.println(method.getAnnotation(Marker.class).value());
    }
}
~~~

Tạo thư mục output rồi biên dịch với debug metadata và parameter metadata:

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -g -parameters -d out AttributeDemo.java
~~~

macOS/Linux:

~~~sh
mkdir -p out
javac -g -parameters -d out AttributeDemo.java
~~~

Chạy:

~~~text
java -cp out AttributeDemo
~~~

Stdout:

~~~text
Java
Hello, Java (3)
value
true
class
method
~~~

Lệnh `javap`:

~~~text
javap -v -p -classpath out AttributeDemo
~~~

Trong kết quả, tìm các phần tương ứng:

- `major version: 61` nếu biên dịch bằng JDK 17.
- `ConstantValue` cho trường `LIMIT`.
- `Signature` cho phương thức generic `identity`.
- `RuntimeVisibleAnnotations` cho annotation `Marker`.
- `MethodParameters` cho tên tham số `value`.
- `Code` cho bytecode của phương thức.
- `LineNumberTable` và `LocalVariableTable` do biên dịch với `-g`.
- `StackMapTable` ở các method có frame cần thiết.

Chi tiết output có thể thay đổi theo phiên bản JDK và cấu trúc mã. Ví dụ, một attribute chỉ xuất hiện nếu mã nguồn hoặc tùy chọn biên dịch tạo ra metadata tương ứng.

### 11.1. So sánh khi bỏ debug metadata và parameter metadata

Biên dịch lại không có debug hoặc parameter metadata:

~~~text
javac -g:none -d out AttributeDemo.java
~~~

Chạy lại:

~~~text
java -cp out AttributeDemo
~~~

Các dòng đầu vẫn giống nhau. Tuy nhiên, tên tham số có thể không còn được reflection nhận diện:

~~~text
Java
Hello, Java (3)
arg0
false
class
method
~~~

Tên reflection cụ thể khi thiếu `MethodParameters` có thể là dạng tổng hợp như `arg0`. Annotation runtime vẫn đọc được vì `@Retention(RetentionPolicy.RUNTIME)` độc lập với `-g` và `-parameters`.

## 12. Unknown attribute và custom attribute

Class file có thể chứa attribute được định nghĩa bởi một công cụ, framework hoặc hệ sinh thái bytecode ngoài tập attribute chuẩn. Ví dụ, thư viện thao tác bytecode có thể ghi metadata riêng để phục vụ phân tích hoặc instrumentation.

Một JVM implementation theo JVMS phải bỏ qua attribute mà nó không nhận diện. Điều này cho phép class file mang thêm metadata mà JVM không cần hiểu để thực thi phần bytecode tiêu chuẩn.

Tuy nhiên, có một số giới hạn thực tế:

- Compiler Java thông thường không cung cấp cú pháp source-level để tự khai báo một attribute tùy ý.
- Muốn tạo custom attribute, thường cần thư viện bytecode hoặc công cụ viết class file.
- Công cụ đọc/ghi class file nên bảo toàn attribute lạ nếu mục tiêu là round-trip không mất metadata.
- JVM bỏ qua attribute không có nghĩa mọi công cụ khác cũng bỏ qua; bytecode analyzer hoặc transformer có thể cần hiểu attribute đó.
- Không nên đặt thông tin cần thiết để chương trình thực thi đúng vào custom attribute mà JVM không hiểu.

Attribute có cấu trúc riêng và được nhận diện bằng tên, nhưng cách diễn giải `info` chỉ có ý nghĩa khi consumer biết định nghĩa của attribute đó.

## 13. Attribute ảnh hưởng thế nào đến kích thước, tương thích và tooling?

Attribute làm class file có thêm metadata, vì vậy có thể tăng kích thước file. Debug metadata, annotation, generic signature, bootstrap method và module metadata đều có thể đóng góp vào kích thước.

Tác động thực tế:

- **Debugging:** `LineNumberTable` và `LocalVariableTable` giúp debugger hiển thị dòng và tên biến.
- **Reflection:** runtime-visible annotation và `MethodParameters` giúp framework đọc metadata.
- **Generic tooling:** `Signature` cho phép reflection/tooling đọc generic declaration sau khi bytecode đã erasure.
- **Verification:** `StackMapTable` hỗ trợ xác minh bytecode.
- **Language features:** `Record`, `PermittedSubclasses`, nest và module attributes biểu diễn cấu trúc Java hiện đại.
- **Bytecode transformation:** instrumentation, shading, obfuscation hoặc compiler plugin cần cập nhật hoặc giữ lại attribute phù hợp.

Không nên loại bỏ mọi attribute để giảm dung lượng. Một số metadata là cần thiết cho tính đúng đắn hoặc khả năng tương thích; một số khác chỉ hỗ trợ debug/tooling. Hãy hiểu tác dụng của từng attribute trước khi strip.

## 14. Các lỗi thường gặp khi đọc hoặc xử lý attribute

### `javap` không tìm thấy class

**Nguyên nhân:** classpath sai hoặc tên lớp không đầy đủ.

**Cách xử lý:** kiểm tra thư mục output và dùng `javap -classpath out package.ClassName`. Với lớp không có package, dùng đúng tên lớp.

### Không thấy `LineNumberTable` hoặc `LocalVariableTable`

**Nguyên nhân:** compiler không sinh debug metadata hoặc build tool tắt debug info.

**Cách xử lý:** biên dịch với `javac -g`; kiểm tra cấu hình compiler của Maven/Gradle/IDE. `-g:none` loại bỏ các metadata debug này.

### Reflection không thấy tên tham số

**Nguyên nhân:** class file không có `MethodParameters`, thường do thiếu `-parameters`.

**Cách xử lý:** biên dịch với `javac -parameters`; kiểm tra lại `Parameter.isNamePresent()`. `-g` riêng lẻ không thay thế `-parameters`.

### Reflection không đọc được annotation

**Nguyên nhân:** annotation không có `RetentionPolicy.RUNTIME`, annotation không được đặt ở vị trí phù hợp hoặc đang đọc sai element.

**Cách xử lý:** kiểm tra `@Retention`, `@Target` và dùng API reflection phù hợp với class, method, field hoặc parameter.

### `ClassFormatError` hoặc lỗi verification

**Nguyên nhân:** class file hỏng, độ dài attribute không hợp lệ, bytecode không khớp stack map frame, hoặc công cụ biến đổi class file ghi metadata sai.

**Cách xử lý:** xác định nguồn class file, chạy `javap -v` để xem cấu trúc, build lại từ source hoặc cập nhật bytecode tool. Nếu lỗi xuất hiện sau instrumentation/obfuscation, kiểm tra công cụ có giữ và cập nhật các attribute cần thiết không.

### Generic signature khác với descriptor

**Nguyên nhân:** generic type bị erasure khi tạo bytecode; `Signature` lưu thông tin khai báo bổ sung.

**Cách xử lý:** so sánh descriptor với `Signature` trong `javap -v`. Đây là khác biệt theo thiết kế của Java generics, không nhất thiết là lỗi class file.

## 15. Quy trình kiểm tra attribute trong một class file

Khi cần điều tra class file, có thể làm theo thứ tự:

1. **Xác định class file thực tế:** kiểm tra classpath/module path để chắc chắn đang đọc đúng phiên bản lớp.
2. **Xem header:** dùng `javap -v` để xem major/minor version và constant pool.
3. **Xem khai báo:** kiểm tra access flags, descriptor, fields và methods.
4. **Xem attribute ở class-level:** tìm `SourceFile`, annotation, module, nest, record hoặc sealed metadata.
5. **Xem attribute của field/method:** kiểm tra `ConstantValue`, `Signature`, `Exceptions`, `MethodParameters` và annotation.
6. **Xem `Code`:** kiểm tra bytecode, exception table và attribute lồng.
7. **Đối chiếu tùy chọn compiler:** xác định `-g`, `-parameters`, `--release` và cấu hình build.
8. **Nếu có bytecode transformation:** so sánh class file trước/sau và xác nhận công cụ bảo toàn attribute cần thiết.
9. **Kiểm tra runtime:** chạy ứng dụng hoặc reflection test để xác nhận metadata được JVM/tooling nhìn thấy như mong đợi.

Một số lệnh hữu ích:

~~~text
javap -v -p -classpath out AttributeDemo
javap -c -p -classpath out AttributeDemo
javap -l -p -classpath out AttributeDemo
javap -s -p -classpath out AttributeDemo
~~~

- `-v`: thông tin class file chi tiết, bao gồm attribute.
- `-c`: disassemble bytecode.
- `-l`: hiển thị line/local variable table nếu có.
- `-s`: hiển thị internal type signatures/descriptors.
- `-p`: hiển thị cả thành viên private.

## 16. Checklist ghi nhớ

- [ ] Attribute là metadata/dữ liệu có cấu trúc trong class file, không đồng nghĩa với annotation source.
- [ ] Mỗi attribute có `attribute_name_index`, `attribute_length` và `info`.
- [ ] Tên attribute trỏ đến `CONSTANT_Utf8_info` trong constant pool.
- [ ] Attribute có thể nằm ở class, field, method, Code hoặc record component theo quy định.
- [ ] `Code` chứa bytecode, exception table và attribute con.
- [ ] `LineNumberTable` và `LocalVariableTable` phục vụ debug.
- [ ] `MethodParameters` liên quan đến tên tham số reflection; dùng `-parameters`.
- [ ] `Signature` giữ metadata generic sau type erasure.
- [ ] `ConstantValue` áp dụng cho một số field constant.
- [ ] `Exceptions` mô tả exception khai báo, không phải cơ chế kiểm tra checked exception của JVM.
- [ ] `StackMapTable` phục vụ bytecode verification.
- [ ] Annotation runtime-visible được lưu trong annotation attribute phù hợp.
- [ ] `Record`, `PermittedSubclasses`, nest và module attributes biểu diễn cấu trúc Java hiện đại.
- [ ] Dùng `javap -v` để quan sát attribute trong class file thực tế.
- [ ] Khi biến đổi bytecode, giữ hoặc cập nhật metadata cần thiết.

Attribute là lớp metadata linh hoạt của Java class file. Hiểu cấu trúc nhị phân chung và nhóm attribute theo mục đích sẽ giúp bạn đọc được output `javap`, giải thích hành vi reflection/debugger, phân tích bytecode và chẩn đoán lỗi khi compiler hoặc công cụ build tạo ra class file không như mong đợi.