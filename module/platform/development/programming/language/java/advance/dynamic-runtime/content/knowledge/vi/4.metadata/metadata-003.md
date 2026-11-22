# 4.3 Khám phá Parameter, tên tham số và tác động của tùy chọn javac -parameters

**Module:** Java Advance - dynamic-runtime  
**Chủ đề cha:** 4. Siêu dữ liệu

## Mục tiêu

Sau bài học, bạn có thể:

- Lấy metadata của từng tham số trong **method** và **constructor** bằng `java.lang.reflect.Parameter`, không nhầm tham số khai báo với đối số được truyền lúc gọi.
- Phân biệt **tên tham số do class file cung cấp** với tên thay thế `arg0`, `arg1` mà Reflection tự tạo khi thiếu metadata.
- Hiểu `javac -parameters` lưu thông tin gì, vì sao `isNamePresent()` quan trọng và vì sao `-g`/`LocalVariableTable` không thay thế `MethodParameters`.
- Đọc kiểu, generic type, annotation, varargs, tham số implicit/synthetic; nhận diện rủi ro khi framework bind theo tên tham số.
- Tự biên dịch cùng một mã nguồn theo hai cách và quan sát sự khác biệt ở runtime.

## 1. `Parameter` là gì và được khám phá từ đâu?

Giả sử có phương thức:

~~~java
String hello(String userName, int repeat)
~~~

`userName` và `repeat` là **formal parameters** (tham số khai báo); `"An"` và `2` trong `hello("An", 2)` là **arguments** (đối số thực tế).

Ở runtime, Reflection mô tả mỗi formal parameter bằng đối tượng **`java.lang.reflect.Parameter`**. Đối tượng này cho biết vị trí trong danh sách, kiểu, thông tin annotation và một số đặc điểm của tham số; **tên nguồn ban đầu có thể có hoặc không**. `Parameter` không giữ giá trị argument của một lần gọi và cũng không cho phép đọc giá trị của biến cục bộ trong stack frame đang chạy.

Quan hệ API:

~~~text
Class<?> (chứa class)
    |
    +-- getDeclaredMethod(name, parameterTypes...)
    |      -> Method extends Executable
    |
    +-- getDeclaredConstructor(parameterTypes...)
           -> Constructor<?> extends Executable
                        |
                        +-- getParameterCount()
                        +-- getParameters() -> Parameter[]
                                                 |
                                                 +-- getName()
                                                 +-- isNamePresent()
                                                 +-- getType() / getParameterizedType()
                                                 +-- getAnnotations() / getAnnotatedType()
                                                 +-- isVarArgs() / isImplicit() / isSynthetic()
~~~

`Method` và `Constructor` cùng kế thừa `Executable`, nên có thể viết một hàm khám phá tham số áp dụng cho cả hai. `getParameters()` trả về các tham số **theo thứ tự của khai báo runtime**. Muốn biết vị trí, duyệt mảng với chỉ số; `Parameter` không có phương thức chuẩn `getIndex()`.

**Chú ý:** Lời gọi tìm phương thức như `getDeclaredMethod("hello", String.class, int.class)` định vị theo **tên phương thức và kiểu tham số**, không theo tên `userName` hay `repeat`. Việc thiếu tên tham số không làm thay đổi cách dispatch, overload resolution hoặc khả năng gọi phương thức của JVM.

## 2. Các API quan trọng của `Parameter`

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `getName()` | Tên được ghi trong class file, hoặc tên thay thế dạng `argN` | **Không** suy ra tên thật chỉ từ giá trị chuỗi |
| `isNamePresent()` | Xác nhận tên có thực sự hiện diện trong metadata `MethodParameters` | Kiểm tra trước khi bind theo tên |
| `getType()` | `Class<?>` biểu diễn kiểu đã khai báo ở mức runtime/erasure | Ví dụ `List<String>` có raw type `List.class` |
| `getParameterizedType()` | `Type` có thể giữ thông tin generic từ `Signature` | Có thể là `ParameterizedType`, `TypeVariable` hoặc kiểu thường |
| `getAnnotatedType()` | Thông tin annotation trên **type use** của tham số | Khác annotation trực tiếp trên declaration của tham số |
| `getAnnotation(...)` / `getAnnotations()` | Annotation runtime gắn trực tiếp trên formal parameter | Annotation cần retention phù hợp, thường `RUNTIME` |
| `isVarArgs()` | Cho biết tham số đại diện cho danh sách varargs | Trong method `String... tags`, tham số cuối có kiểu runtime `String[]` |
| `isImplicit()` | Tham số được khai báo ngầm theo quy tắc ngôn ngữ | Có thể gặp ở constructor đặc biệt do compiler tạo |
| `isSynthetic()` | Tham số do compiler sinh, không được khai báo tường minh/ngầm trong source | Không nên giả định mọi tham số đều xuất hiện trong mã nguồn |
| `getDeclaringExecutable()` | Method/constructor sở hữu tham số | Hữu ích để log lỗi với đúng thành viên |
| `getModifiers()` | Các modifier/flag Java của tham số | Ví dụ `final`, có thể kiểm tra bằng `Modifier` |

Một tên chuỗi `arg0` có thể là tên **tự tạo** khi thiếu metadata, nhưng cũng có thể thật sự là tên do tác giả đặt. Vì vậy:

~~~java
if (!parameter.isNamePresent()) {
    throw new IllegalStateException("Missing runtime parameter name");
}
String reliableName = parameter.getName();
~~~

Đây là đoạn mã minh họa bên trong hàm có biến `parameter`; nó không phải chương trình chạy độc lập.

`isNamePresent()` kiểm tra **có tên trong class file hay không**, chứ không kiểm tra tên đó có ý nghĩa nghiệp vụ, đúng phiên bản API hoặc còn khớp tên trong source mới nhất.

## 3. `javac -parameters` tác động thế nào?

### 3.1. Lớp dữ liệu nằm trong class file

Khi biên dịch Java, JVM cần biết số lượng và **kiểu** tham số để nhận diện descriptor của method/constructor. Tuy nhiên, tên `userName`, `repeat` không bắt buộc để JVM gọi được phương thức. Compiler có thể không lưu chúng.

Với tùy chọn:

~~~bash
javac -parameters Example.java
~~~

`javac` phát hành metadata tên formal parameters của constructor/method vào **`MethodParameters` attribute** của `.class`. Khi Reflection đọc:

- **Có tên:** `getName()` trả tên metadata; `isNamePresent()` trả `true`.
- **Thiếu tên:** `getName()` tạo tên kiểu `arg0`, `arg1`,...; `isNamePresent()` trả `false`.

`MethodParameters` có cấu trúc chứa danh sách tên tham số (nếu có) và flag như `synthetic`/`mandated`. Nó khác method descriptor, metadata generic, và annotation metadata. Trong những dạng class/member đặc biệt do compiler tạo, thông tin tham số có thể được phát hành theo quy tắc riêng; **không phát biểu rằng mọi method/constructor thiếu `-parameters` đều nhất định mất mọi tên**. Kết quả so sánh phần sau áp dụng chính xác cho các method/constructor thông thường trong ví dụ.

### 3.2. `-parameters` khác `-g`

| Thành phần class file | Công dụng chính | Reflection `Parameter.getName()` có dựa trực tiếp vào nó không? |
| --- | --- | --- |
| **`MethodParameters`** | Tên và flag của formal parameters | **Có**; `isNamePresent()` được xác định từ đây |
| **`LocalVariableTable`** (debug info, có thể do `-g:vars` tạo) | Tên và phạm vi sống của local variables trong mã phương thức | **Không** phải nguồn tên của API `Parameter` |
| **Method descriptor** | Kiểu tham số, kiểu trả về ở mức JVM | Cho biết kiểu và vị trí; **không** có tên nguồn |
| **`Signature`** | Thông tin generic vượt trên type erasure | Liên quan `getParameterizedType()`; không thay `MethodParameters` |
| **`RuntimeVisibleParameterAnnotations`** | Declaration annotations của tham số có retention runtime | Không phụ thuộc vào sự hiện diện của tên tham số |

Lệnh `javac -g:vars` có thể giúp debugger đọc tên local variables, nhưng **không bảo đảm** `Parameter.isNamePresent() == true`. Ngược lại, `-parameters` vẫn có ý nghĩa với **interface/abstract method**, nơi không có method body và do đó không có bảng local variables bên trong `Code` attribute.

`-parameters` là **tùy chọn lúc biên dịch**, không phải cờ bật ở lệnh `java` lúc chạy. Một thư viện đã build không chứa metadata cần được **biên dịch lại bằng tùy chọn thích hợp** (hoặc xử lý artifact trước khi dùng); không thể khôi phục tên nguồn thật chỉ bằng việc thay cờ chạy chương trình.

## 4. Thực hành Java 17+: biên dịch hai phiên bản từ cùng một tệp

Ví dụ khám phá cả **constructor**, **method**, **generic parameter**, **annotation** và **varargs**. Chỉ thay cờ `javac`; mã nguồn không thay đổi.

**Tệp độc lập:** `ParameterNamesDemo.java`

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.List;

public class ParameterNamesDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface Label { String value(); }

    public static class Greeter {
        private final String prefix;
        public Greeter(String prefix) { this.prefix = prefix; }
        public String hello(@Label("name") String userName, int repeat) {
            return prefix + userName + ":" + repeat;
        }
        public void log(List<String> messages, String... tags) { }
    }

    private static void inspect(Executable member) {
        String title = member instanceof Constructor<?> ? "<init>" : member.getName();
        System.out.println("member=" + title);
        int index = 0;
        for (Parameter p : member.getParameters()) {
            System.out.println("  #" + index++ + " name=" + p.getName()
                    + " present=" + p.isNamePresent()
                    + " type=" + p.getType().getSimpleName()
                    + " generic=" + p.getParameterizedType().getTypeName()
                    + " annotated=" + p.isAnnotationPresent(Label.class)
                    + " varArgs=" + p.isVarArgs());
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        inspect(Greeter.class.getDeclaredConstructor(String.class));
        inspect(Greeter.class.getDeclaredMethod("hello", String.class, int.class));
        inspect(Greeter.class.getDeclaredMethod("log", List.class, String[].class));
        System.out.println("invoke=" + new Greeter("Hi, ").hello("An", 2));
    }
}
~~~

Từ thư mục chứa file, tạo hai output directory **tách biệt** để class cũ không bị nhầm với class mới:

~~~bash
javac --release 17 -d out-plain ParameterNamesDemo.java
javac --release 17 -parameters -d out-named ParameterNamesDemo.java

java -cp out-plain ParameterNamesDemo
java -cp out-named ParameterNamesDemo
~~~

`--release 17` yêu cầu JDK 17 hoặc mới hơn và biên dịch theo API/language target Java 17. Các thư mục output khác nhau giúp việc so sánh minh bạch. Nếu chạy trên Windows hoặc Linux/macOS, `-cp` chấp nhận một directory như ví dụ.

### 4.1. Kết quả **không** có `-parameters`

~~~text
member=<init>
  #0 name=arg0 present=false type=String generic=java.lang.String annotated=false varArgs=false
member=hello
  #0 name=arg0 present=false type=String generic=java.lang.String annotated=true varArgs=false
  #1 name=arg1 present=false type=int generic=int annotated=false varArgs=false
member=log
  #0 name=arg0 present=false type=List generic=java.util.List<java.lang.String> annotated=false varArgs=false
  #1 name=arg1 present=false type=String[] generic=java.lang.String[] annotated=false varArgs=true
invoke=Hi, An:2
~~~

### 4.2. Kết quả **có** `-parameters`

~~~text
member=<init>
  #0 name=prefix present=true type=String generic=java.lang.String annotated=false varArgs=false
member=hello
  #0 name=userName present=true type=String generic=java.lang.String annotated=true varArgs=false
  #1 name=repeat present=true type=int generic=int annotated=false varArgs=false
member=log
  #0 name=messages present=true type=List generic=java.util.List<java.lang.String> annotated=false varArgs=false
  #1 name=tags present=true type=String[] generic=java.lang.String[] annotated=false varArgs=true
invoke=Hi, An:2
~~~

Hai output đã được kiểm chứng bằng biên dịch `javac --release 17` và chạy chương trình trên JDK tương thích.

### 4.3. Đọc đúng từ kết quả

- `name=userName` chỉ xuất hiện khi compiler ghi thông tin tên tương ứng. Khi không ghi, `arg0` là **tên fallback** do Reflection tạo.
- `annotated=true` trên tham số đầu của `hello` trong **cả hai phiên bản**: annotation `@Label("name")` có retention `RUNTIME` và nằm ở metadata annotation, không cần `-parameters`.
- `getType()` của `List<String>` trả `List.class` do type erasure. `getParameterizedType()` vẫn biểu diễn `java.util.List<java.lang.String>` vì compiler giữ thông tin generic thích hợp.
- `String... tags` có `getType().getSimpleName() == "String[]"`; chỉ tham số `tags` là `varArgs=true`.
- `invoke=Hi, An:2` **không đổi**. Tên tham số dùng cho khám phá/binding ở tầng ứng dụng, không thay khả năng gọi method theo chỉ số và kiểu của JVM.
- `Greeter` là `static nested class`, nên constructor ở ví dụ không có tham số instance của enclosing class. Một non-static inner class có thể có hình dạng constructor khác.

**Kiểm tra class file khi cần:** chạy `javap -v -p -classpath out-named ParameterNamesDemo` để xem `MethodParameters` của `main`; so sánh với `out-plain`. Muốn xem `hello` và `Greeter`, dùng tên binary của nested class `ParameterNamesDemo$Greeter`, lưu ý cách shell escape ký tự `$`. Không dựa vào nội dung `LocalVariableTable` để kết luận `getName()` sẽ trả tên nguồn.

## 5. Khi cần dùng tên tham số cho dynamic binding

### 5.1. Binding theo vị trí và kiểu

Ví dụ một hệ thống plugin tìm method:

~~~java
Method target = Greeter.class.getDeclaredMethod(
        "hello", String.class, int.class);
~~~

Đoạn minh họa này giả định `Greeter` là class có thể truy cập trong cùng ngữ cảnh như ví dụ. Nó **không** dùng `userName` hoặc `repeat` để tìm method: Reflection đối sánh theo tên thành viên và danh sách **kiểu tham số**. Để thực thi `Method.invoke`, arguments vẫn truyền theo thứ tự của formal parameters.

### 5.2. Binding theo tên

Một framework HTTP, CLI, dependency injection hoặc data mapper đôi khi cần ánh xạ input `"userName"` đến đúng tham số. Khi dùng Reflection Java thuần:

1. Lấy `Method` hoặc `Constructor` đúng loại.
2. Duyệt `getParameters()`, kiểm tra `isNamePresent()` **cho từng tham số cần ánh xạ tên**.
3. Khi thiếu tên, dùng **contract tường minh** (chẳng hạn annotation có giá trị tên) hoặc báo lỗi cấu hình có ý nghĩa; không coi `arg0` là tên nguồn.
4. Khi có tên, áp dụng kiểm tra kiểu/chuyển đổi input và xử lý giá trị thiếu, null, primitive, overload đúng quy tắc của framework.
5. Xem tên tham số như metadata đi cùng phiên bản artifact; đổi tên source khi framework bind theo tên có thể trở thành **thay đổi hành vi**, dù chữ ký bytecode vẫn tương thích.

Ví dụ có `@Label("name")`: nếu hệ thống định nghĩa annotation này làm tên binding, nó vẫn có thể lấy `p.getAnnotation(Label.class).value()` ở runtime khi thiếu `-parameters`. **Đây là chính sách riêng của ứng dụng**; Java Reflection không tự động hiểu `@Label` là tên để bind.

### 5.3. Khi nào nên yêu cầu `-parameters`?

Nên bật khi cần runtime access đến tên tham số nguồn để tạo schema, tài liệu, CLI flags, constructor injection hoặc reflection-based binding. Nhưng việc bật không thay thế contract công khai: tên nguồn có thể bị đổi bởi refactor, tool obfuscation, code generation, bytecode transformation hoặc artifact không được build đồng nhất. Với API cần ổn định, metadata tường minh ở annotation/schema thường dễ kiểm soát hơn.

Có thể bật cho task `JavaCompile` của dự án **Gradle Groovy DSL** (minh họa cấu hình build, không phải tệp chạy độc lập):

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
~~~

Với **Maven Compiler Plugin**, cấu hình tương đương thường là:

~~~xml
<configuration>
    <parameters>true</parameters>
</configuration>
~~~

Cần áp dụng đúng module chứa class được Reflection đọc, không chỉ module **đang gọi** Reflection. Khi kiểm thử, hãy dùng chính artifact sau đóng gói (JAR/AOT/bytecode transform) thay vì chỉ dựa vào output build tạm.

## 6. Trường hợp đặc biệt: metadata không trùng đơn giản với source

### 6.1. Implicit và synthetic parameters

`Parameter.isImplicit()` và `Parameter.isSynthetic()` phân loại tham số đặc biệt dựa trên ngữ nghĩa/ngữ cảnh và flag trong class metadata. Compiler có thể tạo các parameter mà source không viết thành danh sách formal parameter tường minh, đặc biệt ở constructor của **non-static inner class**, **enum** hoặc một số class do compiler sinh. Khi đó, chỉ số tham số trên descriptor runtime có thể khác điều ta đếm bằng mắt trong source.

Không nên tự mặc định “tham số có thứ tự 0 là parameter đầu tiên người lập trình viết” trong mọi constructor. Hãy kiểm tra `Constructor.getParameters()` và `isImplicit()`/`isSynthetic()`; đối chiếu đúng classfile/compiler nếu hành vi quan trọng. Các compiler và kiểu class đặc biệt có thể ghi metadata khác nhau.

`isSynthetic()` của **parameter** cũng không đồng nghĩa với `Method.isSynthetic()` của **method**. Synthetic/bridge method được sinh cho mục đích compiler (ví dụ để hỗ trợ generic override) có thể xuất hiện trong `getDeclaredMethods()`; khi xây registry, cần chủ động quyết định có lọc `method.isSynthetic()` hay `method.isBridge()` không.

### 6.2. Generic và type-use annotation

Một formal parameter có thể chứa đồng thời các loại metadata độc lập:

~~~java
void consume(List<String> items)
~~~

- `getType()` trả `Class<?>` biểu diễn `List`.
- `getParameterizedType()` có thể trả `ParameterizedType` biểu diễn `List<String>`.
- `getAnnotatedType()` giúp đọc annotation gắn ở vị trí **sử dụng kiểu** khi annotation được khai báo `@Target(TYPE_USE)` và có metadata runtime.
- `getAnnotations()` của `Parameter` đọc annotation **trên khai báo tham số**; không tự động gộp mọi annotation của type use.

Thông tin generic cũng có thể thiếu hoặc thay đổi sau xử lý bytecode, nên chỉ dùng kết quả sau khi kiểm tra kiểu `Type` thực tế. Không ép mọi `Type` sang `ParameterizedType`.

### 6.3. Các nguồn tên khác không đồng nghĩa

- **IDE/debugger** có thể hiển thị tên nhờ source hoặc debug information, nhưng Reflection `Parameter` có thể vẫn `isNamePresent() == false`.
- **Annotation processor** chạy lúc biên dịch có thể đọc tên từ source model; việc đó không chứng minh runtime class file giữ tên.
- **Framework** có thể dùng chiến lược discovery của riêng nó (annotation, debug symbols, generated index); không suy ra kết quả `Parameter.getName()` từ khả năng binding của framework.
- **Source code và Javadoc** không phải nguồn dữ liệu mà `Parameter` tự động đọc ở runtime.
- **Parameter name** không tham gia method descriptor/overload: đổi tên tham số mà giữ nguyên kiểu và thứ tự thường không đổi bytecode method signature, nhưng có thể phá contract binding theo tên ở tầng ứng dụng.

## 7. Chẩn đoán lỗi

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `getName()` là `arg0`, `isNamePresent()` false | Class chứa method được compile thiếu tên | So sánh output `javac` không/có `-parameters`; kiểm tra `MethodParameters` |
| Đã cấu hình `-parameters` nhưng runtime vẫn không thấy tên | Đang chạy JAR khác, dependency/module khác chưa build lại, cached class hoặc bước transform làm mất attribute | In nguồn class `clazz.getProtectionDomain().getCodeSource()` khi phù hợp; kiểm tra class thật bằng `javap` |
| Bật `-g` mà `isNamePresent()` vẫn false | Lầm `LocalVariableTable` với `MethodParameters` | Thêm `-parameters` ở compile task đúng |
| Framework không bind được input theo tên | Thiếu metadata hoặc tên runtime không trùng tên input | Xác minh `isNamePresent()`, annotation/config explicit, tên input, conversion |
| `NoSuchMethodException` khi tra cứu | Sai tên method, thứ tự/kiểu runtime, nhầm `List<String>` với `List.class`, sai constructor | Sử dụng erased parameter types thực tế |
| Có parameter lạ trong constructor hoặc method | Implicit/synthetic parameter, bridge/synthetic method | Kiểm tra `isImplicit()`, `isSynthetic()`, `isBridge()` và descriptor |
| `MalformedParametersException` | `MethodParameters` trong class file không hợp lệ | Kiểm tra artifact/compiler/transform, build lại |
| Reflection lấy annotation rỗng | Annotation không có retention runtime, sai target hoặc đọc nhầm declaration/type-use | Kiểm tra `@Retention`, `@Target`, API tương ứng |

**Checklist debug tối thiểu:** xác định **class đang chạy**, **constructor/method chính xác**, **mảng `Parameter[]`**, mỗi `getName()/isNamePresent()`, flags implicit/synthetic, annotation và **lệnh build thực tế**. Thường không cần bật deep reflection hoặc `setAccessible(true)` chỉ để đọc metadata của tham số đã lấy được.

## 8. Bài tập tự kiểm tra

1. Biên dịch `ParameterNamesDemo.java` bằng `-g:vars` nhưng không có `-parameters`. Dự đoán `isNamePresent()` rồi kiểm chứng bằng cách chạy demo. Lý giải vì sao debugger và Reflection có thể nhìn thấy dữ liệu khác nhau.
2. Thêm `@Label("count")` vào `repeat` và in `p.getAnnotation(Label.class).value()` khi annotation tồn tại. Kiểm tra rằng annotation vẫn đọc được trong cả hai lần build.
3. Đổi tên `userName` thành `customer` nhưng giữ nguyên `String` và vị trí. Quan sát điều gì đổi khi có `-parameters` và điều gì không đổi ở `getDeclaredMethod("hello", String.class, int.class)`.
4. Đổi `log(List<String> messages, String... tags)` thành `log(List<Integer> messages, String... tags)`; so sánh `getType()` và `getParameterizedType()`. Vì sao Reflection method lookup vẫn dùng `List.class`?

**Kết luận:** `Parameter` giúp khám phá **metadata về formal parameters** từ method/constructor. Tên hiển thị có thể chỉ là `argN` được tổng hợp, vì JVM không cần tên nguồn để gọi phương thức. `javac -parameters` bổ sung `MethodParameters` để Reflection lấy tên thật ở runtime; người xây dynamic binding phải kiểm tra `isNamePresent()`, hiểu sự khác biệt giữa tên, kiểu, generic, annotation và tham số compiler sinh, rồi lựa chọn chính sách fallback rõ ràng.

## Tài liệu tham khảo

- [Java SE 17: `java.lang.reflect.Parameter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html)
- [Java SE 17: `java.lang.reflect.Executable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html)
- [Java SE 17: `javac` — tùy chọn `-parameters`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [JVMS 17: `MethodParameters` attribute — `4.7.24`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.24)
- [JVMS 17: `LocalVariableTable` attribute — `4.7.13`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.13)
