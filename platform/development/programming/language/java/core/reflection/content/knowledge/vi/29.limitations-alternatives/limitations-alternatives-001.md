# Reflection không khôi phục đầy đủ mã nguồn hoặc thân phương thức

**Java Reflection cho phép quan sát metadata của kiểu và thành viên tại runtime, đồng thời thực hiện những thao tác như đọc field hoặc gọi method khi có quyền. Nó không có API chuẩn để trả về toàn văn Java source code hoặc thân Java source của một phương thức.** Một `java.lang.reflect.Method` mô tả *phương thức nào* (tên, tham số, kiểu trả về, modifiers, annotations...), chứ không cung cấp *các câu lệnh Java nào* đã viết để triển khai phương thức ấy.

Điều này quan trọng khi thiết kế công cụ quét class, trình tạo tài liệu, mapper, serializer, debugger và framework: có những dữ kiện lấy được từ Reflection, những dữ kiện chỉ có thể suy ra từ bytecode khi còn bytecode, và những dữ kiện đã mất sau quá trình biên dịch nên **không thể phục hồi chính xác chỉ từ `.class`**.

## 1. Phân biệt ba lớp thông tin

| Lớp thông tin | Ví dụ | Công cụ/phạm vi |
| --- | --- | --- |
| **Mã nguồn (`.java`)** | Câu lệnh, cách đặt dấu ngoặc, chú thích, cách đặt tên biến cục bộ, imports, biểu thức viết ban đầu | Trình phân tích source/AST khi có tệp nguồn; Reflection không trả những đoạn này |
| **Class file / bytecode (`.class`)** | Constant pool, descriptors, metadata, attributes và thường có mã lệnh JVM trong `Code` attribute của method thông thường | `javap`, thư viện phân tích class file/bytecode, decompiler; đây là dữ liệu sau biên dịch, không phải nguyên văn source |
| **Runtime Reflection** | `Class<?>`, `Method`, `Field`, `Constructor`, tham số, các annotation được giữ ở runtime; đọc/gọi thành viên nếu truy cập hợp lệ | `java.lang.Class`, `java.lang.reflect`; các API công khai để kiểm tra kiểu/thành viên và invocation |

Một đoạn Java source có thể được biên dịch thành nhiều class, synthetic members, lambda-related constructs hoặc các lệnh bytecode không tương ứng một-một với dòng nguồn. Khi chỉ còn `.class`, thông tin đã bị bỏ đi (ví dụ comment/format/imports) không tồn tại để Reflection “trả lại”.

### Reflection cho biết gì?

Ví dụ với `Method m`, các API có ích:

- `m.getName()`, `m.getDeclaringClass()`, `m.getModifiers()`: tên method, lớp khai báo, modifier.
- `m.getParameterTypes()`, `m.getReturnType()`, `m.getExceptionTypes()`: kiểu tham số runtime, kiểu trả về, danh sách ngoại lệ **được khai báo** trong chữ ký.
- `m.getGenericParameterTypes()`, `m.getGenericReturnType()`: thông tin generic được khai báo và còn được lưu ở metadata phù hợp.
- `m.getParameters()`: đối tượng `Parameter`; tên thực sự của tham số chỉ đáng tin nếu `isNamePresent()` báo có.
- `m.getDeclaredAnnotations()`: các annotation khai báo tại method mà JVM cho phép quan sát bằng Reflection, chủ yếu annotation có retention `RUNTIME`.
- `m.isBridge()`, `m.isSynthetic()`: xác định một số phương thức hỗ trợ do compiler/sinh bytecode tạo.

Reflection cũng có thể đọc/ghi giá trị field khi được phép và gọi một phương thức qua `m.invoke(receiver, args...)`. Tuy nhiên, **giá trị hiện tại hoặc kết quả khi gọi không cho biết câu lệnh nguồn đã tạo ra chúng**.

### Reflection không trả về gì?

Không có phương thức chuẩn như `Method.getBody()` hay `Method.getSourceCode()` trong `java.lang.reflect`. Những điều sau không được Reflection chuẩn khôi phục đầy đủ:

- Toàn văn câu lệnh trong method: vòng lặp, nhánh `if`, biểu thức, lambda ở dạng source và các comment.
- Khoảng trắng, thứ tự import, cách viết literal, phong cách dấu ngoặc, các comment/Javadoc ban đầu.
- Tên và scope của mọi biến cục bộ, tên biến tạm compiler sinh; một số tên có thể hiện diện trong debug attributes, nhưng Reflection không cung cấp API đọc một AST hoàn chỉnh từ đó.
- Đồ thị điều khiển (CFG), danh sách lệnh JVM, stack frames, biểu thức gốc hoặc ánh xạ chính xác từ instruction ngược về từng đoạn source.
- Lý do tác giả chọn một thuật toán hoặc ý định nghiệp vụ đằng sau một method.

Ví dụ hai cách cài đặt `square(int x)`, một dùng `x * x`, một dùng `Math.multiplyExact(x, x)`, có thể có **metadata Reflection gần như giống nhau** mặc dù hành vi khác nhau ở trường hợp overflow. Chỉ nhìn chữ ký `int square(int)` không thể suy ra logic bên trong.

## 2. Tại sao `Method.toString()` và `Method.invoke()` không phải mã nguồn?

Giả sử:

~~~java
public String greet(String name) {
    String message = "Hello, " + name;
    return message.trim();
}
~~~

Gọi `getDeclaredMethod("greet", String.class)` tìm đối tượng `Method` ứng với tên và kiểu tham số. `m.toString()` hoặc `m.toGenericString()` tạo **chuỗi mô tả chữ ký** (modifier, kiểu, tên, danh sách tham số/throws...), không in ra các câu lệnh `String message = ...` hay `return ...`.

`m.invoke(object, "Lan")` thực thi method thực tế và có thể trả `"Hello, Lan"`, nhưng Reflection không ghi nhận một “bản source” của method để trả lại. Việc thử vài input/output để đoán thuật toán cũng không thể chứng minh phương thức được viết bằng các câu lệnh nào.

- `getDeclaredMethods()` liệt kê các method khai báo trực tiếp (có thể gồm bridge/synthetic), không giải mã thân method.
- `getMethods()` tìm các public methods có tính đến kế thừa theo API, vẫn không trả source.
- `Method.getDefaultValue()` nếu có là **default của phần tử annotation type**, không phải câu lệnh `return` của một method thông thường.
- `MethodHandle` hoặc `MethodHandles.Lookup` cho phép liên kết/gọi hành vi theo capability/quyền, nhưng cũng không phải API truy xuất source code.

Một method `abstract` không có implementation trực tiếp; `native` triển khai bằng mã ngoài bytecode Java; method trong bytecode được tạo động có thể không có tệp `.java` tương ứng. Vì vậy việc mong chờ Reflection trả “thân Java source” cho mọi method là sai từ mô hình ban đầu.

## 3. Dữ liệu nào có thể mất tùy cách biên dịch?

### 3.1. Tên tham số: `-parameters`

Trong tệp Java:

~~~java
public void send(String recipient) { }
~~~

`Method.getParameters()[0].getName()` **không phải lúc nào cũng trả `"recipient"`**. Nếu method không có metadata tên tham số phù hợp trong class file, Reflection có thể đặt tên tổng hợp như `"arg0"`; hãy kiểm tra `Parameter.isNamePresent()` trước khi dùng tên vào mapping hoặc tài liệu.

Với các method Java thông thường do `javac` biên dịch:

~~~bash
javac -parameters ReflectionLimitsDemo.java
~~~

Tùy chọn `-parameters` lưu tên tham số của methods/constructors vào `MethodParameters` attribute, nên `isNamePresent()` có thể là `true`. Đây là **tên tham số ở chữ ký**, không phải danh sách mọi biến cục bộ hoặc thân method. Trình biên dịch khác, class do công cụ sinh, record constructor và metadata bị biến đổi có thể có những đặc điểm riêng; hãy dùng chính `isNamePresent()` làm nguồn kiểm chứng.

### 3.2. Generic: erasure và `Signature` attribute

Xét `class Box<T> { T echo(T value) { return value; } }`. Trong mô hình runtime erasure, kiểu thực dùng trong descriptor của `echo` là `Object`. `getReturnType()` trả `Object.class`, trong khi `getGenericReturnType()` có thể trả type variable `T` nhờ thông tin generic signature còn trong class file.

Vì vậy cần phân biệt **runtime type đã erasure** với **mô tả generic ở metadata**. Reflection có thể đọc một phần thông tin generic khai báo (nếu còn), nhưng không suy ngược toàn bộ kiểu của biến cục bộ, cách lập trình viên đặt type argument ở các biểu thức, hay mọi ràng buộc đã biến mất sau erasure.

### 3.3. Annotation: `SOURCE`, `CLASS` và `RUNTIME`

| `RetentionPolicy` | Khi biên dịch và chạy | Reflection runtime |
| --- | --- | --- |
| `SOURCE` | Compiler bỏ annotation khỏi class file | Không đọc được bằng Reflection |
| `CLASS` | Annotation được ghi vào class file nhưng không bắt buộc giữ lại ở runtime | Core Reflection thông thường không trả annotation này |
| `RUNTIME` | Annotation được giữ để đọc phản xạ tại runtime | Có thể đọc bằng `getAnnotation`/`getDeclaredAnnotations` |

Việc class file có lưu một annotation `CLASS` không có nghĩa `Method.getDeclaredAnnotations()` sẽ liệt kê nó. Nếu mục tiêu là đọc annotation dành cho compiler hoặc classfile tools, chọn đúng tầng dữ liệu thay vì mở rộng Reflection vô ích.

### 3.4. Debug information có giới hạn riêng

Class file có thể chứa `SourceFile`, `LineNumberTable` và (tùy cách build) `LocalVariableTable`/`LocalVariableTypeTable`. Những attribute này hỗ trợ debugger, ánh xạ số dòng hoặc công cụ bytecode, nhưng **không dựng lại comment, biểu thức Java, scope và AST một cách chính xác**.

`javac -g` yêu cầu sinh thông tin debug phong phú hơn; `javac -g:none` loại nhiều thông tin debug. `javac -parameters` phục vụ metadata tên tham số cho Reflection và **không đồng nghĩa** với `-g`. Stack trace có thể chứa tên file và số dòng khi metadata tương ứng còn đó, nhưng số dòng không phải thân method.

## 4. Ví dụ Java 17+: kiểm tra chính xác giới hạn Reflection

Lưu toàn bộ ví dụ vào tệp **`ReflectionLimitsDemo.java`**:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@interface AtRuntime {}

@Retention(RetentionPolicy.CLASS)
@interface InClass {}

@Retention(RetentionPolicy.SOURCE)
@interface InSource {}

public class ReflectionLimitsDemo {
    @AtRuntime @InClass @InSource
    public String greet(String name) {
        String message = "Hello, " + name;
        return message.trim();
    }

    public static class Box<T> {
        public T echo(T value) {
            return value;
        }
    }

    public static void main(String[] args) throws Exception {
        Method greet = ReflectionLimitsDemo.class
                .getDeclaredMethod("greet", String.class);
        System.out.println("method: " + greet.getName());
        System.out.println("return: " + greet.getReturnType().getSimpleName());
        System.out.println("parameter type: " +
                greet.getParameterTypes()[0].getSimpleName());
        System.out.println("name present: " +
                greet.getParameters()[0].isNamePresent());
        System.out.println("parameter name: " +
                greet.getParameters()[0].getName());
        System.out.println("runtime annotation: " +
                greet.isAnnotationPresent(AtRuntime.class));
        System.out.println("class annotation: " +
                greet.isAnnotationPresent(InClass.class));
        System.out.println("source annotation: " +
                greet.isAnnotationPresent(InSource.class));
        System.out.println("invoke: " +
                greet.invoke(new ReflectionLimitsDemo(), "Lan"));
        Method echo = Box.class.getDeclaredMethod("echo", Object.class);
        System.out.println("erased return: " +
                echo.getReturnType().getSimpleName());
        System.out.println("generic return: " +
                echo.getGenericReturnType().getTypeName());
    }
}
~~~

Biên dịch lần đầu **không dùng `-parameters`** để quan sát sự thiếu vắng metadata tên tham số:

~~~bash
javac --release 17 ReflectionLimitsDemo.java
java ReflectionLimitsDemo
~~~

Output đã kiểm chứng với Java 17 source/API:

~~~text
method: greet
return: String
parameter type: String
name present: false
parameter name: arg0
runtime annotation: true
class annotation: false
source annotation: false
invoke: Hello, Lan
erased return: Object
generic return: T
~~~

Đọc kết quả:

1. Có thể xác định tên, return type, parameter type bằng `Method`; **không có câu lệnh nào** trong thân `greet` xuất hiện trong output Reflection.
2. Tham số có tên khai báo là `name` nhưng Reflection chỉ cho `arg0` và `isNamePresent() == false` do lựa chọn biên dịch.
3. Chỉ annotation có `RetentionPolicy.RUNTIME` được trả qua `isAnnotationPresent`.
4. `invoke` trả giá trị thực tế, còn `getReturnType`/`getGenericReturnType` cho biết những góc nhìn khác nhau về kiểu generic.

Nếu biên dịch lại bằng:

~~~bash
javac --release 17 -parameters ReflectionLimitsDemo.java
java ReflectionLimitsDemo
~~~

Hai dòng thay đổi là:

~~~text
name present: true
parameter name: name
~~~

Các dòng khác vẫn như ví dụ trước. Việc này **không** bổ sung cách truy xuất thân `greet` hay biến cục bộ `message` qua `Method`.

## 5. Khi nào dùng `javap`, bytecode reader hay decompiler?

Nếu có class file mà bạn có quyền phân tích và cần xem cách JVM thực thi một method, hãy dùng **công cụ phân tích bytecode**, không kỳ vọng Reflection làm thay.

~~~bash
javap -c -p ReflectionLimitsDemo
javap -v -p ReflectionLimitsDemo
javap -l -p ReflectionLimitsDemo
~~~

- `javap -c -p`: in lệnh JVM bytecode của method, gồm private members; đó là disassembly, không phải text Java source.
- `javap -v -p`: mô tả chi tiết class file, attributes, constant pool và metadata; hữu ích để phân biệt descriptor, `Signature` và attributes khác.
- `javap -l -p`: in thông tin số dòng và local variable tables **nếu có**; không thể tạo lại những thông tin compiler đã không lưu.

Trong ví dụ, `javap -c` có thể cho thấy các lệnh phục vụ nối chuỗi, gọi `trim()` và trả kết quả. Nó không cho biết lập trình viên đã xuống dòng, viết comment hay đặt dấu ngoặc theo phong cách nào. JDK/compiler còn có thể chọn các cách biểu diễn bytecode khác nhau cho mã nguồn tương đương.

Một **Java decompiler** (ví dụ CFR, Vineflower hoặc công cụ tương đương) phân tích bytecode rồi **suy dựng mã nguồn gần đúng** để đọc hiểu. Chương trình decompile có thể khác mã nguồn ban đầu về tên biến, cấu trúc điều khiển, anonymous/lambda, generic, annotation, cú pháp và khả năng biên dịch lại. Không thể xem output của decompiler là bản gốc hoặc dùng nó như bằng chứng duy nhất về source đã được viết.

Nếu cần kiểm tra chính xác source, hãy ưu tiên **tệp `.java` và thông tin build/commit gốc**. Nếu cần vị trí và cấu trúc cú pháp khi source hiện diện, dùng công cụ phân tích AST như API `com.sun.source.tree` trong javac hoặc parser chuyên dụng. AST là đại diện của source đang được phân tích, khác với đối tượng `Method` ở runtime.

### Lựa chọn công cụ theo câu hỏi

| Nhu cầu thực tế | Hướng phù hợp |
| --- | --- |
| Liệt kê tên, chữ ký, kiểu, modifier, runtime annotation | Core Reflection |
| Gọi method, đọc/ghi field tại runtime (được cấp quyền) | Core Reflection hoặc `MethodHandle`/`VarHandle` |
| Biết implementation gồm các câu lệnh JVM nào | `javap -c`, ASM hoặc thư viện đọc class file |
| Hiểu logic của class chỉ còn bytecode | Decompiler kết hợp kiểm tra disassembly và test; ghi rõ tính suy dựng |
| Lấy nguyên văn source, comment, formatting, import | Kho lưu `.java` / artifact source tương ứng |
| Phân tích cú pháp tại thời điểm build | Java compiler AST / parser chạy trên source |
| Biết method chạy qua những nhánh nào trong thực tế | Debugger, tracer, profiling hoặc instrumentation thích hợp |
| Xem số dòng/biến cục bộ để debug | Debug attributes, debugger, `javap -l` khi metadata tồn tại |

## 6. Các ranh giới cần nhớ khi làm công cụ Reflection

**Đừng xem mọi metadata là có sẵn.** Một class được compiler bình thường tạo khác một class do bytecode generator/proxy tạo; class có thể bị obfuscate hoặc biến đổi, generic signatures/debug attributes bị bỏ, annotation có retention khác nhau. `getDeclaredMethods()` có thể chứa bridge/synthetic methods không có một method source riêng. Thứ tự mảng trả về cũng không được bảo đảm: nếu phải xuất schema ổn định, hãy sắp xếp và lọc theo chính sách rõ ràng.

**Đừng coi thấy metadata là có quyền truy cập.** Có thể tìm thấy khai báo private qua `getDeclaredMethod` nhưng khi invoke vẫn cần quyền phù hợp. Java Platform Module System (JPMS) phân biệt `exports` và `opens`; `setAccessible(true)` không tự vượt mọi ranh giới module. Việc đọc metadata, đọc bytecode và gọi method là ba hoạt động có cơ chế và điều kiện riêng.

**Đừng suy luận source từ behavior.** Output có thể phụ thuộc trạng thái, I/O, thời gian, concurrency hoặc thư viện bên ngoài; hai implementation khác nhau có thể cho cùng output ở nhiều input. Reflection invocation không cung cấp bằng chứng về các nhánh chưa chạy, phép biến đổi bytecode hoặc cấu trúc source ban đầu.

**Đừng lấy tên `arg0` làm dữ liệu nghiệp vụ.** Nếu đang thiết kế router, serializer hay mapper phụ thuộc tên tham số, yêu cầu build lưu `-parameters`, hỗ trợ annotation tên logic, hoặc định nghĩa cơ chế ánh xạ cấu hình rõ ràng. Nếu `!isNamePresent()`, nên trả thông báo cụ thể hoặc fallback có kiểm soát thay vì giả định `arg0` là tên tác giả đặt.

## 7. Nhầm lẫn thường gặp và tự kiểm tra

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`getDeclaredMethod` lấy luôn thân method.” | Chỉ lấy đối tượng `Method` mô tả thành viên; không có `getBody` chuẩn. |
| “`Method.toGenericString` là mã Java đầy đủ.” | Nó biểu diễn chữ ký có thông tin generic, không phải implementation. |
| “Dùng `invoke` có thể lấy lại câu lệnh đã chạy.” | `invoke` thực thi hành vi; không trả về source/AST. |
| “Class file chính là source code được đóng gói.” | Class file là kết quả biên dịch, có descriptors/bytecode và một số metadata được giữ lại. |
| “`javap -c` tạo lại nguyên bản `.java`.” | Nó in bytecode; decompiler cũng chỉ suy dựng source gần đúng. |
| “Tên tham số luôn tồn tại trong `Parameter.getName()`.” | Kiểm tra `isNamePresent()`; `-parameters` có thể cần thiết. |
| “Mọi annotation trong source đều đọc được lúc chạy.” | Core Reflection chủ yếu đọc annotation có `RUNTIME` retention. |
| “Generic source luôn được giữ nguyên sau biên dịch.” | Runtime erasure mất nhiều chi tiết; một phần generic declarations có thể được giữ trong signature metadata. |
| “Số dòng stack trace là nguyên văn nội dung source.” | Nó chỉ là metadata vị trí có điều kiện, không phải câu lệnh. |

Tự trả lời ba câu hỏi:

1. Nếu Reflection cho biết một method trả `String` và nhận `String`, liệu bạn có thể biết nó đang dùng `StringBuilder`, phép nối chuỗi hay thư viện bên ngoài? **Không**; chữ ký không tiết lộ thuật toán.
2. Nếu `Parameter.isNamePresent()` bằng `false`, tên `arg0` có được dùng để khẳng định tác giả đặt tên `arg0` không? **Không**; đó có thể là tên tổng hợp.
3. Khi chỉ còn `.class`, làm thế nào xem instruction và vì sao decompile chưa phải source gốc? Xem `javap -c` hoặc bytecode reader; decompiler **suy dựng** biểu diễn Java từ dữ liệu đã biên dịch, còn thông tin đã bị bỏ thì không thể phục hồi nguyên vẹn.

**Ghi nhớ:** Reflection là công cụ cho **metadata và invocation tại runtime**. `javap`/bytecode analysis trả lời câu hỏi về **class file và lệnh JVM**, còn source parser trả lời câu hỏi về **mã Java đang có**. Phân biệt đúng ba lớp này giúp thiết kế công cụ chính xác, không hứa hẹn phục hồi những dữ liệu Java đã không lưu.

**Tài liệu chính thức:** [`Class` (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html), [`Method` (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html), [`Parameter` (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html), [`RetentionPolicy` (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/RetentionPolicy.html), [`javap` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html).