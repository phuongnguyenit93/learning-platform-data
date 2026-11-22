# Các ngôn ngữ khác trên JVM và hợp đồng chung của tệp class

## 1. JVM chạy bytecode, không chỉ chạy mã nguồn Java

Java Virtual Machine (JVM) là một máy ảo có đặc tả cho **class file**, bytecode, tải lớp, liên kết, kiểu dữ liệu, lời gọi phương thức và thực thi. JVM không yêu cầu chương trình ban đầu được viết bằng Java: bất kỳ công cụ nào sinh ra tệp `.class` phù hợp với đặc tả, cùng những thư viện runtime cần thiết, đều có thể chạy trên JVM tương thích.

~~~text
Java (.java) ──────── javac ──────────────┐
Kotlin/JVM (.kt) ──── kotlinc ────────────┤
Scala (.scala) ────── scalac ─────────────┼─→ .class (có thể gói trong .jar)
Groovy (.groovy) ──── compiler/runtime ───┤                    │
Clojure (.clj) ────── compiler/runtime ───┘                    ▼
                                           class loader → verify/link → JVM
~~~

Các ngôn ngữ chia sẻ **đích thực thi**, không nhất thiết chia sẻ cú pháp, hệ kiểu hay cách tổ chức chương trình. Kotlin có nullability ở cấp compiler; Scala có các cách biểu diễn kiểu/hàm khác Java; Clojure có namespace, dữ liệu bất biến và mô hình động; Groovy hỗ trợ metaprogramming. Compiler/runtime của từng ngôn ngữ ánh xạ các đặc trưng ấy thành các cấu trúc JVM: class, method, field, instruction, metadata và thư viện hỗ trợ.

**Phạm vi:** ở đây “Kotlin” nghĩa là **Kotlin/JVM**, không phải Kotlin/JS hay Kotlin/Native. Những triển khai khác của cùng một ngôn ngữ có thể sử dụng nền tảng khác. Các tên JRuby, Jython, v.v. chỉ những triển khai cụ thể chạy trên JVM, không phải bằng chứng rằng mọi triển khai Ruby/Python tự động chạy được Java bytecode.

## 2. Những ngôn ngữ JVM tiêu biểu và ranh giới tương tác

| Ngôn ngữ | Mô hình chạy phổ biến | Khi giao tiếp với Java |
| --- | --- | --- |
| Java | `javac` biên dịch sang class file | Java API và ABI là chuẩn liên kết quen thuộc |
| Kotlin/JVM | `kotlinc` sinh class, dùng Kotlin standard library | Getter, hàm top-level, tham số mặc định và nullability có ánh xạ riêng |
| Scala | `scalac` sinh class, dùng scala-library | Trait, companion object, hàm và tên member có thể sinh bytecode khác biểu đạt nguồn |
| Groovy | Compiler/runtime trên JVM, có cơ chế gọi động | Một phần thao tác phụ thuộc Groovy runtime và call site |
| Clojure | Compiler/runtime tạo hoặc nạp class JVM | Function/namespace và dữ liệu Clojure không tự thành JavaBean thông thường |
| JRuby và ngôn ngữ khác | Interpreter, sinh bytecode hay JIT tùy triển khai | Interop tùy API bridge và runtime của triển khai đó |

Một JAR là một kho lưu trữ ZIP thường chứa `.class`, resources và metadata, **không phải một thứ bytecode thứ hai**. JAR có thể thiếu dependency runtime; chạy thành công cần classpath/module path và phiên bản thư viện thích hợp. Một class hợp lệ cũng không có nghĩa mọi phương thức của ngôn ngữ nguồn đều có một public Java method dễ gọi.

## 3. Hợp đồng nhị phân chung: class-file format

Ở mức cấu trúc, định dạng `ClassFile` gồm:

~~~text
magic (0xCAFEBABE)
minor_version, major_version
constant_pool_count, constant_pool
access_flags
this_class, super_class
interfaces_count, interfaces
fields_count, fields
methods_count, methods
attributes_count, attributes
~~~

- **Magic** nhận diện class file; **major/minor version** cho biết mức định dạng mà JVM phải hỗ trợ.
- **Constant pool** chứa thông tin hằng, tên, descriptor, tham chiếu kiểu/thành viên và dữ liệu liên quan để bytecode tham chiếu.
- **Access flags** mô tả đặc điểm class/interface; **this_class**, **super_class**, **interfaces** mô tả quan hệ kiểu ở JVM-level.
- **Fields/methods** chứa tên, quyền truy cập, kiểu theo **descriptor** và thuộc tính liên quan. Với method có bytecode, thuộc tính `Code` chứa instruction và thông tin phục vụ thực thi.
- **Attributes** cho phép ghi `Code`, `StackMapTable`, `Signature`, exceptions, annotations, thông tin debug và metadata riêng của compiler/ngôn ngữ.

Tên nội bộ kiểu JVM dùng dấu `/` như `java/lang/String`; Java hiển thị tên nhị phân dạng `java.lang.String`. Descriptor là một phần quan trọng của ABI:

| Descriptor JVM | Kiểu/ý nghĩa |
| --- | --- |
| `I`, `J`, `Z` | `int`, `long`, `boolean` |
| `V` | `void`, dùng cho return type |
| `Ljava/lang/String;` | tham chiếu `java.lang.String` |
| `[I` | mảng `int[]` |
| `(I)Ljava/lang/String;` | method nhận `int`, trả `String` |
| `(Ljava/lang/String;)V` | method nhận `String`, trả `void` |

Lời gọi JVM liên kết dựa trên class/interface sở hữu member, tên, descriptor, loại lời gọi và quy tắc truy cập. Một phương thức được Java mô tả là `String greet(String)` có descriptor `(Ljava/lang/String;)Ljava/lang/String;`. Kiểu generic ở mã nguồn có thể đi qua **type erasure** và được biểu diễn bổ sung trong `Signature`. Descriptor bytecode không tự chứa mọi ràng buộc cấp nguồn như Kotlin nullable/non-nullable hoặc mọi chi tiết generic Scala.

### Phiên bản tệp class

Ví dụ, Java 17 phát hành class file major **61**; Java 21 dùng major **65**. JVM chỉ đọc được những mức class-file version được đặc tả cho bản runtime ấy. Nếu mang class xây bằng mục tiêu mới sang JVM cũ không hỗ trợ, có thể gặp `UnsupportedClassVersionError`.

Với mã Java, `javac --release 17` trên JDK hỗ trợ tùy chọn đó đặt mức bytecode và giới hạn các API Java chuẩn theo Java 17. Với Kotlin/Scala hoặc các compiler khác, tùy chọn JVM target cần được kiểm tra riêng: đặt target bytecode **không tự chứng minh** mọi dependency và API được gọi đều có thể chạy trên JVM cũ. Các tính năng preview còn có quy tắc class-file riêng; tránh suy đoán chỉ qua số major nếu chương trình sử dụng preview.

## 4. JVM tải, kiểm chứng, liên kết và thực thi class như thế nào?

1. **Loading:** class loader tìm hoặc nhận bytes và định nghĩa kiểu. Định danh runtime của một class phụ thuộc **tên nhị phân và defining class loader**; hai defining loader khác nhau có thể tạo hai kiểu riêng dù tên trùng nhau.
2. **Linking:** JVM **verify** ràng buộc class/bytecode, **prepare** dữ liệu static và **resolve** tham chiếu biểu tượng theo quy tắc; việc resolve có thể diễn ra từng phần khi cần.
3. **Initialization:** tại các điểm kích hoạt được đặc tả, JVM khởi tạo class/interface và thực hiện các static initializer tương ứng.
4. **Execution:** instruction hoạt động với local variables, operand stack, đối tượng/heap và cơ chế runtime khác. JVM cụ thể có thể thông dịch rồi JIT-compile mã nóng; điều này không đòi hỏi nguồn ban đầu là Java.

Các instruction gọi như `invokevirtual`, `invokestatic`, `invokeinterface`, `invokespecial`, `invokedynamic` thực hiện cơ chế gọi khác nhau. Một compiler có thể tạo lambda, bridge method, synthetic class, state machine hoặc bootstrap method để chuyển đặc trưng ngôn ngữ thành thao tác JVM. Việc nhìn thấy `invokedynamic` cũng không đồng nghĩa nguồn chắc chắn là ngôn ngữ động: Java cũng có các trường hợp dùng instruction ấy.

**Verifier** kiểm tra tính hợp lệ của bytecode theo đặc tả, không chứng minh chương trình đúng nghiệp vụ, không áp đặt mọi quy tắc nullability của compiler Kotlin và không phải cơ chế sandbox bảo mật toàn diện.

## 5. Ví dụ Java 17+: tự tạo và xem class file

Tạo tệp `src/demo/ContractDemo.java` với nội dung **đầy đủ**:

~~~java
package demo;

interface Message {
    String text();
}

final class Greeting implements Message {
    private final String name;

    Greeting(String name) {
        this.name = name;
    }

    @Override
    public String text() {
        return "Xin chào, " + name;
    }
}

public class ContractDemo {
    public static void main(String[] args) {
        Class<?> type = Greeting.class;
        System.out.println(type.getName());
        System.out.println(type.getSuperclass().getName());
        System.out.println(type.getInterfaces()[0].getName());
        System.out.println(new Greeting("JVM").text());
    }
}
~~~

Từ thư mục chứa `src`, dùng JDK 17+:

~~~bash
javac --release 17 -d out src/demo/ContractDemo.java
java -cp out demo.ContractDemo
~~~

Stdout chính xác:

~~~text
demo.Greeting
java.lang.Object
demo.Message
Xin chào, JVM
~~~

Mặc dù cùng khai báo trong một source file, trình biên dịch tạo các class file riêng cho `ContractDemo`, `Greeting` và `Message`. Công cụ `javap` của JDK cho phép đọc hợp đồng nhị phân thực tế:

~~~bash
javap -classpath out -p -s demo.Greeting
javap -classpath out -c -p demo.Greeting
javap -classpath out -v -p demo.Greeting
~~~

`-s` hiện descriptor, chẳng hạn `text()` trả `java.lang.String` có descriptor `()Ljava/lang/String;`; `-c` hiện instruction, `-v` hiện constant pool, version và attribute; `-p` xem cả member không public. Vì lệnh biên dịch dùng `--release 17`, class file có major version **61**. Chi tiết instruction nối chuỗi có thể khác giữa compiler, nên không ép toàn bộ output `javap` giống hệt mọi bản JDK.

Quan sát trên giúp phân biệt ba cấp: **source Java** (cú pháp bạn viết), **class-file API/bytecode** (compiler tạo) và **hành vi runtime** (JVM thực thi). Ngôn ngữ JVM khác vẫn phải qua ranh giới class file nhưng có thể chọn cách sinh code khác.

## 6. Ví dụ Kotlin/JVM sinh class để Java gọi

Ví dụ này yêu cầu **JDK 17+ và Kotlin command-line compiler/runtime**. Tạo `src/demo/Greeter.kt`:

~~~kotlin
package demo

class Greeter(private val who: String) {
    fun greet(): String = "Hello, $who"
}
~~~

Tạo `src/demo/JavaCaller.java`:

~~~java
package demo;

public class JavaCaller {
    public static void main(String[] args) {
        Greeter greeter = new Greeter("JVM");
        System.out.println(greeter.greet());
    }
}
~~~

Các lệnh dưới đây giả định `kotlinc`, `javac` và `kotlin` nằm trong PATH:

~~~bash
kotlinc -jvm-target 17 src/demo/Greeter.kt -d out
javac --release 17 -cp out -d out src/demo/JavaCaller.java
kotlin -cp out demo.JavaCaller
~~~

Stdout:

~~~text
Hello, JVM
~~~

Vì `kotlinc` đã tạo `demo/Greeter.class`, `javac` có thể biên dịch `JavaCaller` nhờ classpath `out`. Java gọi constructor và public method `greet()` dựa trên ABI JVM, không cần hiểu cú pháp Kotlin. Lệnh `kotlin` cung cấp Kotlin standard library khi chạy. Nếu thay bằng `java -cp out demo.JavaCaller` mà không bổ sung Kotlin runtime, chương trình có thể lỗi thiếu class runtime; dự án thực tế dùng Gradle/Maven để khai báo và đóng gói dependency.

Kiểm tra trực tiếp ABI bằng:

~~~bash
javap -classpath out -p -s demo.Greeter
~~~

Kết quả sẽ cho thấy JVM constructor, private field và method được compiler tạo ra; không cần suy luận member JVM chỉ từ hình dạng cú pháp Kotlin.

## 7. Vì sao interop đa ngôn ngữ không hoàn toàn trong suốt?

### 7.1. API nhìn từ nguồn khác API nhìn từ JVM

Với Kotlin/JVM, thuộc tính `val name: String` thường có getter `getName()` để Java gọi thay vì mặc định là public field. Hàm top-level được sinh trong class có tên theo file hoặc tên được tùy biến. Tham số mặc định **không đương nhiên** tạo mọi overload Java; `@JvmOverloads` hỗ trợ một số trường hợp. `@JvmName`, `@JvmStatic`, `@JvmField` điều chỉnh cách trình bày API JVM khi thích hợp.

`suspend` function có thể dùng continuation và state machine; method JVM trong `javap` có thể khác chữ ký Kotlin đọc ở source. Scala có companion object, trait và các cấu trúc biên dịch riêng; Groovy/Clojure có chức năng được gọi qua runtime động. Muốn caller Java sử dụng ổn định, hãy thiết kế và kiểm tra **public JVM API**, không đoán dựa trên tính giống nhau của tên hàm nguồn.

### 7.2. Nullability, generic và kiểu nâng cao

JVM phân biệt primitive/reference và các descriptor, nhưng không có một chế độ type system chung cho mọi ngôn ngữ nguồn. Ví dụ Kotlin `String` và `String?` có thể đều dùng descriptor tham chiếu `Ljava/lang/String;`; compiler, annotation, metadata và các kiểm tra runtime bổ sung diễn đạt khác biệt. Code Java vẫn có thể truyền `null`, nên ranh giới Java/Kotlin cần hợp đồng nullability rõ ràng.

Với Java generic thông thường, `List<String>` và `List<Integer>` cùng dùng một kiểu JVM sau erasure; thông tin generic nguồn có thể xuất hiện ở `Signature` và không tương đương với hai runtime class riêng. Bridge method, cast hoặc runtime type token có thể cần thiết khi ánh xạ những abstraction khác nhau.

### 7.3. Exception và thư viện runtime

Checked exception là quy tắc kiểm tra ở compiler Java, **không phải quy tắc verifier ép mọi caller JVM phải catch**. Kotlin không áp dụng kiểm tra checked exception giống Java; việc công bố thông tin `throws` cho Java cần cơ chế compiler/annotation tương ứng khi cần.

Code biên dịch xong không có nghĩa đã độc lập với runtime ngôn ngữ. Kotlin có Kotlin standard library; Scala có scala-library; Groovy/Clojure có runtime tương ứng. Phải kiểm tra cả **compile classpath** (để biên dịch caller), **runtime classpath/module path** (để nạp và chạy), phiên bản các dependency và cách đóng gói JAR. “Có một file .jar” chưa chứng minh nó là executable fat JAR tự đủ thư viện.

### 7.4. Class loader và ranh giới kiểu runtime

Nếu hai defining class loader nạp hai bản cùng tên `example.Greeter`, JVM xem chúng là hai kiểu; cast có thể ném `ClassCastException` dù tên hiển thị giống nhau. Tình huống thường gặp ở plugin, container ứng dụng và hot reload. Hợp đồng class file không tự loại bỏ vấn đề định danh kiểu bởi loader.

## 8. Source compatibility, binary compatibility và hành vi

Có ba tầng tương thích cần xét độc lập:

1. **Source compatibility:** caller giữ nguyên source có còn biên dịch được với API mới?
2. **Binary compatibility (ABI):** caller đã biên dịch có còn liên kết/chạy với thư viện mới, không cần biên dịch lại?
3. **Behavioral compatibility:** API vẫn chạy nhưng kết quả, side effect và quy ước có còn đúng?

Xóa method/constructor, đổi tên JVM member, đổi descriptor, thay static thành instance hoặc thay quan hệ kế thừa có thể gây lỗi liên kết của caller cũ. Ngược lại, giữ ABI chưa chắc giữ hành vi. Version compiler và runtime của Kotlin/Scala cũng có cam kết binary compatibility riêng: cùng là bytecode JVM không chứng minh mọi phiên bản của chúng hoán đổi cho nhau.

| Lỗi/hiện tượng | Hướng điều tra |
| --- | --- |
| `UnsupportedClassVersionError` | Class-file version cao hơn mức JVM hiện chạy hỗ trợ |
| `ClassNotFoundException` | Cơ chế tìm class theo tên không tìm được class phù hợp |
| `NoClassDefFoundError` | Class cần lúc thực thi không nạp/định nghĩa được, có thể do dependency hoặc lỗi khởi tạo trước đó |
| `NoSuchMethodError` | Caller đòi method name/descriptor không tồn tại trong library runtime |
| `AbstractMethodError`, `IncompatibleClassChangeError` | Quan hệ class/method lúc chạy lệch với cách caller đã liên kết |
| `VerifyError` | Bytecode/class file không vượt qua kiểm chứng |
| `ClassCastException` khi tên kiểu giống nhau | Kiểm tra quan hệ kế thừa và defining class loader |

Không kết luận nguyên nhân chỉ dựa vào tên exception; cần stack trace, dependency tree, classpath/module path, class loader và class file thật đã tải.

## 9. Quy trình khám phá một thư viện JVM lạ

Khi muốn gọi thư viện biên dịch từ Java hoặc ngôn ngữ JVM khác, đi theo các bước thực tế:

1. **Xem các class và resources:** `jar tf library.jar`.
2. **Xác minh API công khai:** `javap -classpath library.jar -public -s ten.package.TenClass`, chú ý member name và descriptor.
3. **Xem metadata và version khi cần:** `javap -classpath library.jar -p -v ten.package.TenClass`; kiểm tra class-file major, `Signature`, annotation, synthetic/bridge method.
4. **Đối chiếu môi trường runtime:** JDK version, compiler target, Kotlin/Scala/Groovy/Clojure runtime, dependency versions, module path hoặc classpath.
5. **Biên dịch một Java caller tối thiểu:** chạy thử với đúng runtime/dependency để kiểm tra linkage thay vì chỉ nhìn được source.
6. **Khi nâng phiên bản:** so sánh ABI đã sinh và chính sách tương thích của thư viện/compiler, nhất là khi caller không được biên dịch lại.

Cùng chạy trên JVM **không bảo đảm hiệu năng giống nhau**. Allocation, boxing, lời gọi động, reflection, coroutine scheduling, JIT warm-up và implementation thư viện đều ảnh hưởng. Muốn so sánh công bằng phải đo bằng workload/benchmark phù hợp.

## 10. Sai lầm thường gặp

- “JVM chỉ chạy Java”: sai, nó chạy code theo hợp đồng JVM class-file/runtime.
- “Tất cả class file chạy trên mọi JVM”: sai, phải xét bytecode version, runtime, dependency và môi trường.
- “Cùng JVM nên cùng nullability/generic/exception rule”: sai, nhiều ràng buộc do compiler nguồn hoặc runtime riêng đảm nhận.
- “Mã Kotlin/Scala hợp lệ thì Java gọi mọi hàm bằng cùng tên”: sai, cần kiểm tra JVM ABI thực tế.
- “JAR đã có mọi dependency”: sai, chỉ đúng với những kiểu đóng gói đã bao gồm chúng.
- “Verifier chứng minh bytecode đúng và an toàn”: sai, nó xác minh các ràng buộc JVM, không thay logic testing và security review.

## 11. Câu hỏi tự kiểm tra

1. Vì sao `javap` đọc được `Greeter.class` do Kotlin compiler sinh? Vì `.class` tuân thủ cấu trúc JVM class-file format.
2. Phân biệt `(Ljava/lang/String;)V` với `()Ljava/lang/String;`? Cái đầu nhận `String` và không trả kết quả; cái sau không nhận tham số và trả `String`.
3. Hai class cùng tên nhưng do hai defining loader khác nhau định nghĩa có phải một kiểu runtime? Không.
4. Khi Java gọi Kotlin library và xuất hiện lỗi thiếu `kotlin.*`, cần kiểm tra gì trước? Runtime classpath/dependency và Kotlin standard library.
5. Khi cập nhật JAR gây `NoSuchMethodError`, công cụ đầu tiên nào giúp kiểm tra? `javap -s` trên class của JAR runtime để so method name và descriptor với ABI caller mong đợi.

**Điểm cốt lõi:** JVM class file là hợp đồng chung để tải, kiểm chứng, liên kết và thực thi nhiều ngôn ngữ. Khả năng hợp tác thực tế phụ thuộc thêm vào **ABI được compiler tạo**, version và runtime dependency, class loader và ngữ nghĩa bổ sung của từng ngôn ngữ.
