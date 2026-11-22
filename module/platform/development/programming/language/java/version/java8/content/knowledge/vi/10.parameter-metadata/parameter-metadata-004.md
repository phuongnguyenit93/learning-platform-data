# `Parameter.isNamePresent()` và tên khi thiếu metadata trong Java

## 1. Tại sao tên tham số trong source có thể biến mất khi chạy?

Java 8 bổ sung API reflection cho **metadata tham số** thông qua `java.lang.reflect.Parameter`. Nhờ đó, chương trình có thể xem danh sách tham số của phương thức hoặc constructor, đọc kiểu, annotation, modifier và — khi class file có thông tin — **tên tham số đã được biên dịch**.

Xét source:

~~~java
// Mảnh mã minh họa:
public String greet(String userName, int times) {
    return userName + times;
}
~~~

Ở source có hai tên `userName` và `times`. Nhưng tên biến này **không phải** thành phần cần thiết để JVM gọi method. Lời gọi được liên kết bởi tên method và descriptor gồm các kiểu tham số/kiểu trả về theo quy tắc JVM; tên tham số người viết đặt chủ yếu phục vụ khả năng đọc, công cụ, hoặc framework.

Nếu class file **không lưu metadata tên tham số** mà Java reflection dùng, thì:

~~~java
// Mảnh mã minh họa bên trong một chương trình reflection:
Parameter[] parameters = method.getParameters();
System.out.println(parameters[0].getName());          // arg0
System.out.println(parameters[0].isNamePresent());     // false
~~~

Trong trường hợp thiếu tên thật, `getName()` **không trả null** mà trả một tên được tổng hợp như `arg0`, `arg1`, ... theo chỉ số vị trí. `isNamePresent()` cho biết tên đó có thật sự hiện diện trong metadata của class file hay không.

> Điểm cốt lõi: **`getName()` có giá trị không đồng nghĩa với tên nguồn đã được lưu**. Nếu một API cần tên tham số đáng tin cậy, phải kiểm tra `isNamePresent()` trước khi dùng `getName()` làm khóa ánh xạ.

Đây là tính năng từ Java 8, vẫn chính xác và hữu ích trong JDK 17+ và Java hiện đại.

## 2. Hai API quan trọng nhất: `getName()` và `isNamePresent()`

Đối tượng `Parameter` có những phương thức:

~~~java
String name = parameter.getName();
boolean present = parameter.isNamePresent();
~~~

Hai dòng trên là **mảnh mã minh họa**, giả định biến `parameter` đã được lấy từ reflection.

### `Parameter.getName()`

Trả về tên của tham số dưới dạng `String`:

- Nếu class file chứa tên tham số theo metadata được reflection hỗ trợ, trả tên đó.
- Nếu không có tên theo metadata, Java tạo tên theo **vị trí** như `arg0`, `arg1`, `arg2`.
- Giá trị trả về không phải một bằng chứng độc lập rằng tên gốc trong source đã được bảo toàn.
- Giá trị như `arg0` **cũng có thể là tên thật mà tác giả source cố ý đặt**. Vì vậy không được đoán `isNamePresent` bằng cách nhìn xem tên có bắt đầu bằng `arg` hay không.

### `Parameter.isNamePresent()`

Trả `true` nếu thông tin tên tham số có mặt theo cấu trúc class file mà Java reflection sử dụng; trả `false` khi thiếu.

Điều này thường phụ thuộc cách class được biên dịch hoặc được công cụ tạo ra:

- Source method Java thông thường được `javac` biên dịch **không có `-parameters`** thường không lưu tên theo `MethodParameters`, nên `isNamePresent()` là `false`.
- Biên dịch **với `javac -parameters`** yêu cầu lưu tên tham số trong class file để reflection đọc; với method thông thường, `isNamePresent()` trở thành `true`.
- Một số dạng thành phần do compiler tạo hoặc có quy tắc ngôn ngữ đặc biệt (ví dụ record constructor) có thể được xử lý khác; không đưa ra giả thiết rằng **mọi method trong mọi thư viện** đều có cùng giá trị chỉ vì project dùng một phiên bản JDK.
- Trên các class file do công cụ khác tạo, biến đổi, rút gọn hoặc obfuscate, cần kiểm tra metadata thực tế. `true` nghĩa là tên có mặt; **không bảo đảm** nó vẫn trùng tên mà người lập trình đã viết trong source ban đầu.

### Bảng phân biệt

| Tình huống | `getName()` có thể trả | `isNamePresent()` | Cách diễn giải |
| --- | --- | --- | --- |
| Method thường, biên dịch không `-parameters` | `arg0`, `arg1` | `false` | Tên tổng hợp, không phải contract nguồn |
| Method thường, biên dịch với `-parameters` | `userName`, `times` | `true` | Tên từ metadata class file |
| Source thực sự đặt tên tham số là `arg0`, metadata được lưu | `arg0` | `true` | Đây có thể là tên thật |
| Bytecode đã biến đổi/obfuscate nhưng còn tên | Tên sau biến đổi | `true` | Có metadata, chưa chắc là tên gốc |
| Tham số của thư viện tải từ dependency khác | Tùy cách dependency biên dịch | Tùy từng parameter | Không suy từ compiler flags của ứng dụng |

**Lưu ý quan trọng:** `isNamePresent()` mô tả **sự hiện diện của tên trong metadata**, không đánh giá tên đó có hợp lệ cho JSON field, HTTP request, database column hoặc mục đích nghiệp vụ khác hay không.

## 3. Metadata tên được lưu ở đâu?

Trong định dạng JVM class file, phần metadata dành cho tên tham số mà API reflection này dùng là thuộc tính **`MethodParameters`**. Tùy công cụ biên dịch, thuộc tính này có thể chứa thông tin tên và cờ liên quan tham số.

Từ Java 8, `javac` hỗ trợ tùy chọn:

~~~bash
javac -parameters Example.java
~~~

Mục đích: yêu cầu compiler phát ra metadata tên tham số của method/constructor vào class file.

Nếu không dùng tùy chọn này, ví dụ:

~~~bash
javac Example.java
~~~

thì đối với method thông thường do `javac` tạo, tên từ source thường không hiện diện qua `Parameter.isNamePresent()`.

### Tùy chọn khi chạy JVM có sửa được class đã biên dịch không?

**Không.** `-parameters` là một **tùy chọn biên dịch**, không phải phép bật tên tham số lúc gọi `java`:

~~~bash
javac -parameters Example.java
java Example
~~~

Đổi cách gọi `java` không tự thêm metadata bị thiếu vào class file. Muốn thay đổi kết quả phải tạo lại hoặc thay class file bằng bản đã chứa metadata.

### Có thể dùng `-g` thay `-parameters` không?

**Không nên xem chúng tương đương.** `javac -g` yêu cầu nhiều thông tin gỡ lỗi hơn, có thể bao gồm local-variable tables trong class file. Nhưng API `Parameter.getName()`/`isNamePresent()` dựa trên metadata **`MethodParameters`**, không bắt buộc suy tên tham số từ debug `LocalVariableTable`.

Một số framework có thể hỗ trợ chiến lược riêng, thậm chí đọc debug symbols để khám phá tên, nhưng đó là cơ chế của **framework**, không phải bảo đảm của `Parameter.isNamePresent()`.

### Tên tham số không thuộc chữ ký method ở mức source

~~~java
// Hai khai báo dưới đây là mảnh mã minh họa, KHÔNG được đặt cùng class:
void send(String source) {}
void send(String target) {}
~~~

Hai phương thức có cùng tên và cùng danh sách kiểu tham số `String`; Java không cho overload chỉ bằng cách đổi tên biến tham số. Metadata tên hỗ trợ công cụ nhưng không thay đổi nguyên tắc chọn overload, override hay liên kết method.

## 4. Lấy danh sách `Parameter` từ reflection

Các bước thường dùng:

~~~java
// Mảnh mã minh họa, giả định đã có class Service:
java.lang.reflect.Method method =
        Service.class.getDeclaredMethod(
                "transfer", String.class, int.class);

java.lang.reflect.Parameter[] params = method.getParameters();

for (int i = 0; i < params.length; i++) {
    java.lang.reflect.Parameter p = params[i];
    System.out.println(i + ": " + p.getName()
            + " / present=" + p.isNamePresent());
}
~~~

`getDeclaredMethod` nhận tên method và các **kiểu tham số chính xác** để xác định overload. Các annotation hoặc tên biến tham số không được dùng để chọn overload.

`Method` và `Constructor` cùng là các loại `Executable`, và `Executable.getParameters()` cung cấp danh sách `Parameter` theo vị trí khai báo ở mức phản chiếu.

### Những điều luôn hữu ích dù không có tên

Thiếu metadata tên **không** đồng nghĩa reflection không còn biết gì về tham số. Các thông tin khác có API riêng:

~~~java
// Mảnh mã minh họa, cần có biến Parameter p:
Class<?> rawType = p.getType();
java.lang.reflect.Type genericType = p.getParameterizedType();
java.lang.reflect.AnnotatedType annotatedType = p.getAnnotatedType();
java.lang.annotation.Annotation[] declared = p.getAnnotations();
~~~

- `getType()` cho kiểu thô ở runtime.
- `getParameterizedType()` cho thông tin kiểu generic (nếu metadata generic hiện diện).
- `getAnnotatedType()` cho type-use annotations theo retention và vị trí phù hợp.
- `getAnnotations()` cho annotations ở **parameter declaration**, không tự suy tên biến.
- `getDeclaringExecutable()` cho biết parameter thuộc method/constructor nào.

Những trường này có cơ chế metadata và quy tắc riêng. **Không được suy rằng `isNamePresent()==false` thì annotation tham số cũng mất.**

## 5. Ví dụ hoàn chỉnh 1 — so sánh cùng source khi có/không `-parameters`

Tạo tệp **ParameterNamesDemo.java**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterNamesDemo {

    static String format(String accountId, int copies) {
        return accountId + ":" + copies;
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterNamesDemo.class.getDeclaredMethod(
                "format", String.class, int.class);

        Parameter[] parameters = method.getParameters();

        System.out.println("method=" + method.getName());

        for (int i = 0; i < parameters.length; i++) {
            Parameter p = parameters[i];
            System.out.println(
                    i + ":" + p.getName()
                            + ":" + p.isNamePresent()
                            + ":" + p.getType().getSimpleName());
        }

        System.out.println("sample=" + format("A", 2));
    }
}
~~~

### Lần 1: biên dịch thông thường

Chạy từ thư mục chứa file:

~~~bash
javac ParameterNamesDemo.java
java ParameterNamesDemo
~~~

**Stdout dự kiến:**

~~~text
method=format
0:arg0:false:String
1:arg1:false:int
sample=A:2
~~~

Đây là kết quả cho **method thường do `javac` biên dịch không bật `-parameters`**. `arg0` và `arg1` phản ánh vị trí, không phải các tên source `accountId` và `copies`.

### Lần 2: biên dịch lại có `-parameters`

Chạy tiếp ở cùng thư mục, ghi đè class file vừa biên dịch:

~~~bash
javac -parameters ParameterNamesDemo.java
java ParameterNamesDemo
~~~

**Stdout dự kiến:**

~~~text
method=format
0:accountId:true:String
1:copies:true:int
sample=A:2
~~~

Vì `-parameters` thêm metadata tên vào class file, `getName()` trả tên `accountId`, `copies`, và `isNamePresent()` trả `true`.

Hãy quan sát điều **không thay đổi**: method vẫn có hai tham số `String` và `int`, và `format("A",2)` vẫn trả `A:2`. Metadata tên thay đổi khả năng **introspection**, không đổi cách method tính kết quả.

### Những nhầm lẫn dễ xảy ra khi chạy ví dụ

- Nếu IDE và command-line dùng cấu hình compiler khác nhau, kết quả có thể khác. Kiểm tra compile command thật đang tạo class file.
- Nếu vừa bật `-parameters` nhưng chạy bản class file cũ từ một output directory hoặc JAR khác, reflection vẫn thấy metadata cũ. Phải đảm bảo classpath đang chứa bản đã biên dịch lại.
- Với code dùng Maven/Gradle, cấu hình compiler cần áp dụng **cho module thực sự sở hữu class chứa method**, không chỉ cho module gọi reflection.
- Nếu framework đang đọc class từ dependency, bật `-parameters` ở ứng dụng **không tự thêm metadata** vào dependency đã được biên dịch.

## 6. Vì sao `arg0` không phải tên để tin tưởng?

Giả sử một framework ánh xạ query string vào tham số:

~~~java
// Mảnh mã minh họa:
@Get("/users")
User findUser(String userId, int limit) { ... }
~~~

Nếu framework chỉ viết:

~~~java
String requestKey = parameter.getName();
~~~

thì khi thiếu `MethodParameters`, key có thể thành `arg0` hoặc `arg1` thay vì `userId` và `limit`. Kết quả là request được binding sai, hoặc hệ thống phát báo lỗi khó hiểu.

Đây là tình huống mà việc kiểm tra `isNamePresent()` trở thành **một phần hợp đồng API**, không phải chi tiết phụ.

~~~java
// Mảnh mã minh họa:
if (!parameter.isNamePresent()) {
    throw new IllegalStateException(
            "Parameter name metadata is required");
}

String requestKey = parameter.getName();
~~~

Đoạn trên phù hợp khi framework **quy định bắt buộc** mỗi tham số phải có tên thực trong class metadata. Nó thất bại rõ ràng thay vì âm thầm dùng tên tổng hợp.

### Có nên phân biệt bằng regex `arg[0-9]+`?

**Không.** Một developer hoàn toàn có thể khai báo:

~~~java
void submit(String arg0) {}
~~~

và biên dịch với `-parameters`. Khi đó `getName()` vẫn là `arg0`, nhưng `isNamePresent()` là `true`. Vì vậy không dùng:

~~~java
// Mảnh mã minh họa về cách kiểm tra KHÔNG đáng tin:
boolean missing = parameter.getName().matches("arg[0-9]+");
~~~

Thay bằng API được thiết kế cho chính mục đích này: `!parameter.isNamePresent()`.

### Tên có metadata vẫn cần validate

`isNamePresent()==true` chỉ nói rằng tên tồn tại, không bảo đảm `getName()`:

- Là tên HTTP parameter bạn muốn public ra ngoài.
- Khớp schema JSON hay database column.
- Không bị đổi do obfuscation.
- Có thể dùng như tên key an toàn trong một framework cụ thể.
- Giữ nguyên giữa các phiên bản API khi developer đổi tên tham số.

Khi tên là **hợp đồng bên ngoài**, định nghĩa tên tường minh bằng annotation hoặc cấu hình có kiểm soát thường bền vững hơn phụ thuộc hoàn toàn vào tên biến source.

## 7. Có ba cách xử lý khi metadata thiếu

### Cách A — Bắt buộc compile với `-parameters`

Khi nhóm kiểm soát toàn bộ source và compiler settings, định nghĩa yêu cầu build:

~~~bash
javac -parameters MyApi.java
~~~

Với dự án nhiều module, áp dụng cho tất cả module chứa những method/constructor có tên tham số được framework yêu cầu.

Ưu điểm: mã API gọn, có thể dựa vào tên tham số viết tại source. Hạn chế: tên có thể thay đổi do refactor, dependency có thể thiếu flag, compiler/bytecode transform khác nhau có thể cho kết quả không đồng đều.

### Cách B — Dùng tên hợp đồng tường minh trong annotation

Ví dụ framework có annotation như:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface WireName {
    String value();
}
~~~

Khi khai báo:

~~~java
// Mảnh mã minh họa:
void submit(@WireName("account_id") String accountId) { }
~~~

`WireName("account_id")` mô tả tên dữ liệu bên ngoài **độc lập** với tên biến `accountId` trong source. Muốn đọc annotation ở runtime, `WireName` phải được giữ đến runtime. Cách này hữu ích khi hợp đồng request/serialization cần ổn định và khác phong cách đặt tên Java.

### Cách C — Fallback có chính sách rõ

Nếu API cho phép tên tùy chọn, có thể ưu tiên annotation, rồi tên thật của reflection, cuối cùng là trạng thái **thiếu tên** rõ ràng.

Không nên im lặng coi `arg0` là key nghiệp vụ. Nếu việc thiếu tên là lỗi cấu hình, phải **fail fast**. Nếu thật sự muốn định danh theo chỉ số, hãy dùng chỉ số **một cách tường minh** với hợp đồng đã được tài liệu hóa — không giả vờ đó là tên source.

## 8. Ví dụ hoàn chỉnh 2 — ưu tiên tên tường minh và báo thiếu metadata

Tạo tệp **ParameterBindingNamesDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterBindingNamesDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface WireName {
        String value();
    }

    static final class Endpoint {
        public void send(
                @WireName("destination") String dest,
                int retries) {
            // Hành vi nghiệp vụ không liên quan đến bài demo.
        }
    }

    static String logicalName(Parameter parameter, int index) {
        WireName explicit = parameter.getAnnotation(WireName.class);
        if (explicit != null) {
            if (explicit.value().isBlank()) {
                throw new IllegalStateException("Blank WireName");
            }
            return explicit.value();
        }
        if (parameter.isNamePresent()) {
            return parameter.getName();
        }
        return "<missing@" + index + ">";
    }

    public static void main(String[] args) throws Exception {
        Method method = Endpoint.class.getDeclaredMethod(
                "send", String.class, int.class);

        Parameter[] parameters = method.getParameters();

        for (int i = 0; i < parameters.length; i++) {
            System.out.println(i + ":metadata="
                    + parameters[i].isNamePresent()
                    + ",name=" + logicalName(parameters[i], i));
        }
    }
}
~~~

### Không bật `-parameters`

~~~bash
javac ParameterBindingNamesDemo.java
java ParameterBindingNamesDemo
~~~

**Stdout dự kiến:**

~~~text
0:metadata=false,name=destination
1:metadata=false,name=<missing@1>
~~~

`@WireName("destination")` giữ được tên hợp đồng cho tham số đầu tiên dù `isNamePresent()` false; tham số `retries` không có annotation nên helper cố ý ghi **thiếu** thay vì dùng `arg1` làm tên nghiệp vụ.

### Bật `-parameters`

~~~bash
javac -parameters ParameterBindingNamesDemo.java
java ParameterBindingNamesDemo
~~~

**Stdout dự kiến:**

~~~text
0:metadata=true,name=destination
1:metadata=true,name=retries
~~~

`WireName` tiếp tục ưu tiên cho tham số đầu tiên, còn tham số thứ hai lấy tên source `retries` từ metadata.

**Cảnh báo thực tế:** chuỗi `<missing@1>` trong ví dụ chỉ là dấu hiệu để **chẩn đoán**. Framework xử lý request thật không nên dùng chuỗi này làm tên field; hãy báo lỗi cấu hình, yêu cầu annotation hoặc quy định binding theo vị trí nếu đó là hợp đồng được chấp nhận.

### Vì sao annotation vẫn thấy khi thiếu tên?

`@WireName` sử dụng metadata của parameter annotation với `RetentionPolicy.RUNTIME`, **khác** metadata tên qua `MethodParameters`. Hai cơ chế độc lập đủ để ví dụ có `metadata=false` nhưng annotation vẫn được đọc.

## 9. `-parameters` trong dự án có build tool

Tùy build system, người phát triển thường cấu hình **compiler arguments**, không thêm option ở runtime.

### Maven

Trong dự án dùng `maven-compiler-plugin`, có thể cấu hình thuộc tính plugin `parameters` cho các phiên bản plugin hỗ trợ:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <release>17</release>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Đây là **mảnh cấu hình minh họa**, cần đặt vào `<plugins>` thuộc phần `<build>` của POM thích hợp, và dùng một phiên bản plugin đang được hỗ trợ trong dự án. Nếu module phải phát hành bytecode cho Java 8, chọn `release` phù hợp thay vì sao chép `17` máy móc.

### Gradle (Java plugin)

Có thể truyền tùy chọn cho `JavaCompile`:

~~~groovy
// Mảnh cấu hình Groovy DSL cho build.gradle:
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Điều này dành cho task compile Java, không phải JVM flags ở task chạy. Nếu dùng Kotlin DSL, syntax cấu hình tương ứng sẽ khác; hãy đặt option trong cấu hình compiler của module có method được phản chiếu.

**Không nên mặc định chỉ một cách cấu hình:** dự án có thể dùng compiler plugin, annotation processing, module build, bytecode enhancement, ahead-of-time compilation hoặc code generation. Quy tắc cần kiểm chứng vẫn là: **class file cuối cùng được chạy có chứa tên tham số hay không**.

### Test build để không bị mất metadata âm thầm

Có thể viết một test reflection:

~~~java
// Mảnh mã minh họa, giả định method đã được tìm đúng:
for (Parameter parameter : method.getParameters()) {
    if (!parameter.isNamePresent()) {
        throw new AssertionError(
                "Missing parameter names for " + method);
    }
}
~~~

Khi đưa vào CI, test này cảnh báo nếu một module mất `-parameters` sau khi sửa build. Chỉ áp dụng cho tập method mà dự án **chủ đích yêu cầu** tên tham số, đừng ép mọi bytecode của dependency/JDK thỏa giả định mà mình không quản lý.

## 10. Method, constructor và số lượng tham số

`Parameter` không chỉ có trong `Method`. Constructor cũng hỗ trợ:

~~~java
// Mảnh mã minh họa:
java.lang.reflect.Constructor<Account> constructor =
        Account.class.getDeclaredConstructor(String.class, int.class);

for (Parameter parameter : constructor.getParameters()) {
    System.out.println(parameter.getName());
}
~~~

Biên dịch class `Account` với hoặc không `-parameters` có thể thay đổi việc tên constructor parameters có mặt giống như method thường.

### Đừng giả định số tham số phản chiếu luôn trùng source trong mọi trường hợp

Một số cấu trúc Java có thể liên quan tham số được compiler thêm hoặc xử lý đặc biệt, như:

- Constructor của inner class không static có thể cần tham chiếu đến outer instance.
- Enum constructor có những tham số nội bộ do cơ chế enum.
- Một số compiler-generated constructs và record constructors có yêu cầu riêng về cấu trúc metadata.
- Compiler và bytecode transformer có thể tạo bridge/synthetic methods.

`Parameter.isImplicit()` và `Parameter.isSynthetic()` giúp mô tả những đặc điểm nhất định khi class file có metadata tương ứng, nhưng **không** biến mọi trường hợp thành một chuỗi tham số đúng như source. Nếu scanner hỗ trợ các cấu trúc đặc biệt, hãy test chúng bằng đúng compiler/JDK được dùng.

Đừng “sửa” trường hợp có tham số bổ sung bằng cách lấy `arg0` làm tên source. Khi binding theo vị trí, cần hiểu chính xác descriptor và semantics của executable.

## 11. Thông tin `Parameter` khác tên không được tự động mất

Trong cùng một method, các thành phần có thể được lưu và phản chiếu theo **những cơ chế độc lập**:

| Thông tin | API | Có nhất thiết cần `-parameters`? |
| --- | --- | --- |
| Tên tham số từ metadata | `getName()`, `isNamePresent()` | Thông thường cần tùy chọn tương đương hoặc metadata từ compiler |
| Kiểu tham số thô | `getType()` | Không |
| Kiểu generic | `getParameterizedType()` | Không phải chỉ vì tên thiếu; phụ thuộc thông tin generic trong class |
| Annotation của khai báo tham số | `getAnnotation(...)` | Không; phụ thuộc `@Retention` và nơi đặt |
| Type-use annotation trên kiểu tham số | `getAnnotatedType()` | Không; phụ thuộc type-use metadata/retention |
| Thứ tự tham số trong descriptor | `getParameters()` | Không |
| Tham số varargs | `isVarArgs()` | Không chỉ phụ thuộc tên |
| Modifier/implicit/synthetic | `getModifiers()`, `isImplicit()`, `isSynthetic()` | Phụ thuộc metadata/class file phù hợp, không suy tên |

Có thể xây một API chỉ cần kiểu và annotation mà **không cần** tên biến. Chỉ bật `-parameters` khi có lý do rõ, hoặc khi framework được tích hợp đòi hỏi.

### Thiếu tên không cấm đọc generic type

~~~java
// Mảnh mã minh họa:
void importItems(java.util.List<String> items) {}
~~~

Dù `getName()` có thể là `arg0`, `getParameterizedType()` vẫn có thể phản ánh `List<String>` khi thông tin generic signature còn trong class file. Tên `items` và đối số kiểu `String` được lưu/đọc qua cơ chế khác nhau.

## 12. Ví dụ hoàn chỉnh 3 — tên thiếu nhưng kiểu và annotation vẫn có

Tạo tệp **IndependentParameterMetadataDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.List;

public class IndependentParameterMetadataDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface External {
        String value();
    }

    static void inspect(
            @External("account_ids") List<String> ids,
            int retries) {
    }

    public static void main(String[] args) throws Exception {
        Method method =
                IndependentParameterMetadataDemo.class.getDeclaredMethod(
                        "inspect", List.class, int.class);

        Parameter[] parameters = method.getParameters();
        Parameter first = parameters[0];
        Parameter second = parameters[1];

        System.out.println("count=" + parameters.length);
        System.out.println("type=" + first.getType().getSimpleName());
        System.out.println("generic="
                + first.getParameterizedType().getTypeName());
        System.out.println("annotation="
                + first.getAnnotation(External.class).value());
        System.out.println("annotation-count="
                + first.getAnnotations().length);
        System.out.println("second-type="
                + second.getType().getSimpleName());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ **không cần** `-parameters`:

~~~bash
javac IndependentParameterMetadataDemo.java
java IndependentParameterMetadataDemo
~~~

**Stdout chính xác:**

~~~text
count=2
type=List
generic=java.util.List<java.lang.String>
annotation=account_ids
annotation-count=1
second-type=int
~~~

Ngay cả khi tên `ids` không được lưu cho reflection, class file vẫn có:

- Tham số đầu tiên mang kiểu thô `List`.
- Generic signature chứa `String`, nên `getParameterizedType().getTypeName()` phản ánh `List<String>`.
- Annotation `@External("account_ids")` có retention runtime và target parameter declaration nên đọc được.
- Tham số thứ hai là kiểu `int`.

Nếu biên dịch ví dụ này với `-parameters`, stdout trên **không đổi**, vì chương trình không in tên. Điều này cho thấy metadata tên và các loại metadata khác phục vụ những bài toán riêng.

### `@Target(PARAMETER)` khác `@Target(TYPE_USE)`

Annotation đặt trên **declaration của tham số** thường được đọc bằng `Parameter.getAnnotation(...)`. Annotation được đặt trên **kiểu tham số** có `ElementType.TYPE_USE` được đọc qua `Parameter.getAnnotatedType()` hoặc `Method.getAnnotatedParameterTypes()`.

Hai mục tiêu khác nhau, và không cái nào tự khôi phục tên source bị mất. Đối với một annotation có nhiều target, cần kiểm tra định nghĩa và đúng API vì chỉ nhìn vị trí cú pháp dễ nhầm lẫn.

## 13. Reflection trên interface, abstract method và dependency

Giả sử một interface có method:

~~~java
interface Processor {
    void execute(String input);
}
~~~

và class thực thi:

~~~java
class ProcessorImpl implements Processor {
    @Override
    public void execute(String input) {}
}
~~~

Khi dùng reflection, `Processor.class.getMethod("execute", String.class)` lấy một `Method` mô tả **khai báo trên interface**, trong khi `ProcessorImpl.class.getMethod(...)` thường trỏ đến **method được khai báo ở implementation**. Hai khai báo nằm trong hai class file khác nhau, có thể đã biên dịch bằng cờ compiler khác nhau và có tên metadata khác nhau.

Do đó **đừng mặc định** rằng tên parameter trên interface sẽ được truyền sang implementation hoặc ngược lại. Việc có cùng source name cũng không khiến hai `Method` chia sẻ metadata.

Tương tự, dependency JAR có thể biên dịch không bật `-parameters` dù dự án của bạn bật. Khi một framework dựa vào reflection, cần biết **nó đang phản chiếu executable nào**, và test đúng artifact cuối cùng.

### Không nhầm với annotation kế thừa

Các quy tắc `@Inherited` chủ yếu áp dụng cho annotation trên **class declaration**, không phải cơ chế tự khôi phục hoặc kế thừa tên tham số giữa các method override. Nếu tên là phần hợp đồng API, hãy xác định rõ nguồn chuẩn và cách xử lý khi các khai báo khác nhau.

## 14. Vì sao compile-time biết tên nhưng runtime không biết?

Trình biên dịch đọc source và đương nhiên thấy `accountId`, `copies`. Nhưng nhiều thông tin source **không buộc phải** được giữ trong class file dùng ở runtime. Việc một IDE hiển thị tên tham số từ source attachment cũng không có nghĩa API `Parameter.isNamePresent()` sẽ trả `true`.

Có ít nhất ba môi trường khác nhau:

1. **Source/IDE:** có file `.java`, chỉ số IDE và thông tin cú pháp. IDE có thể biết tên ngay cả khi bytecode đã build không lưu.
2. **Compile-time tools:** annotation processors và compiler plugins có thể đọc AST hoặc mô hình source theo cơ chế riêng.
3. **Runtime reflection:** đọc metadata tồn tại trong class file thật được nạp bởi class loader; `isNamePresent()` kiểm tra nguồn metadata thuộc class file đó.

Một kết quả IDE “parameter name: accountId” không chứng minh JAR phát hành sẽ hiển thị `accountId` qua `getName()`. Hãy viết test runtime hoặc xem class file.

### Dùng `javap` để kiểm tra artifact

JDK có công cụ `javap`. Có thể chạy:

~~~bash
javap -v ParameterNamesDemo
~~~

và tìm phần `MethodParameters:` của method `format` khi class được biên dịch với `-parameters`. Không cần dựa vào debug symbols. Kết quả `javap -v` chứa nhiều phần của class file; ở bài này chỉ cần xác minh sự tồn tại và các tên trong `MethodParameters` của **đúng executable**.

Khi build ra JAR, phải trỏ `javap` hoặc kiểm thử đến **class trong JAR đang được chạy**, không chỉ file `.class` thử nghiệm khác.

## 15. Điều kiện biên và nguyên tắc xử lý lỗi

### 15.1. Method không có tham số

`getParameters()` trả mảng rỗng. Không có `arg0` vì không có `Parameter` nào; đừng truy cập phần tử `[0]` mà không kiểm tra độ dài.

### 15.2. Có tham số nhưng không có metadata tên

Trường hợp phổ biến: `getParameters().length > 0`, `isNamePresent()==false` và `getName()` dạng `argN`. Hãy chọn hợp đồng:

- **Bắt buộc có tên:** báo lỗi cấu hình rõ ngay khi đăng ký API.
- **Có annotation đặt tên tường minh:** dùng giá trị annotation nếu hợp lệ.
- **API chỉ hỗ trợ positional arguments:** dùng index một cách chính thức, không dùng `argN` như tên public ngẫu nhiên.
- **API không cần tên:** bỏ qua `getName()`, dùng kiểu và thứ tự phù hợp.

### 15.3. Có annotation nhưng giá trị rỗng/trùng

`@WireName("")` không nên trở thành tên hợp lệ nếu API yêu cầu key khác rỗng. Hai tham số cùng `@WireName("id")` có thể gây xung đột binding. Chính framework cần kiểm tra rỗng, trùng, cú pháp tên và quy tắc ưu tiên.

### 15.4. Có metadata tên nhưng bị obfuscate

`isNamePresent()==true` không đủ cho một API public ổn định nếu bytecode transform có thể đổi `accountId` thành `a`. Với contract bên ngoài, tên tường minh hoặc schema/versioning thường bền hơn tên biến source.

### 15.5. Class file thiếu/không hợp lệ

Reflection có thể ném ngoại lệ khi gặp class file malformed hoặc sai chữ ký khi bạn truy vấn. Không dùng `isNamePresent` để “bảo đảm mọi metadata đều an toàn”; xử lý các lỗi reflection phù hợp ở ranh giới load/scanning.

### 15.6. Chính sách trên mọi method trong thư viện

Không nên ép **toàn bộ** method của các JAR bên ngoài phải `isNamePresent()==true`. Một thư viện hợp lệ vẫn có thể không cung cấp tên tham số. Chỉ ràng buộc những executable mà API của bạn **thực sự phụ thuộc** vào tên và bạn có quyền kiểm soát build hoặc định nghĩa fallback.

## 16. Thứ tự ưu tiên khi bind tên tham số: quyết định thiết kế

Khi viết framework, một chính sách dễ hiểu là:

| Bước | Kiểm tra | Kết quả |
| --- | --- | --- |
| 1 | Có annotation khai báo tên explicit? | Dùng tên sau khi validate |
| 2 | Không có annotation, `isNamePresent()==true`? | Dùng `getName()` nếu hợp đồng cho phép |
| 3 | Không có cả hai | Báo lỗi cấu hình hoặc dùng positional mapping đã được quy định |
| 4 | Sau khi chọn tên | Kiểm tra uniqueness và yêu cầu schema |
| 5 | Khi thực thi bind | Convert/validate giá trị theo kiểu và chính sách lỗi riêng |

**Không được lẫn ba bài toán:** tìm **tên tham số**, chuyển **chuỗi request thành giá trị có kiểu**, và kiểm tra **giá trị có hợp lệ**. `-parameters` chỉ giải quyết bài toán lưu tên; nó không tự kiểm tra null, số âm, format hoặc authorization.

### Nếu đang dùng một framework cụ thể

Framework có thể cung cấp cơ chế đặt tên tham số bằng annotation riêng, convention, Kotlin metadata, record component metadata, bytecode scanning hoặc cách khác. Không áp dụng một “quy tắc chung” mà không đọc hợp đồng framework. Dù vậy, hiểu `Parameter.isNamePresent()` giúp giải thích tại sao cùng một method có thể bind bình thường trong một build nhưng thất bại ở build khác.

## 17. Bảng so sánh nhanh

| Câu hỏi | Trả lời đúng |
| --- | --- |
| `getName()` có thể trả tên dù thiếu metadata? | Có, thường `arg0`, `arg1` |
| Làm sao biết tên hiện diện theo metadata? | `isNamePresent()` |
| `-parameters` là Java compile hay runtime option? | Compile option |
| Debug `-g` bảo đảm `isNamePresent()==true`? | Không |
| Tên biến ảnh hưởng method overload? | Không |
| Metadata tên thiếu thì kiểu tham số mất? | Không |
| Annotation parameter declaration có cần `-parameters`? | Không, có retention/target riêng |
| `isNamePresent()==true` có bảo đảm public name ổn định? | Không |
| Method của dependency có chắc lưu tên vì app bật `-parameters`? | Không |
| Tên `arg0` chứng minh metadata thiếu? | Không, hãy kiểm tra `isNamePresent()` |
| Constructor cũng có `Parameter`? | Có |
| `getParameters()` của method không đối số? | Mảng rỗng |

## 18. Lỗi thường gặp

1. **Gọi `getName()` rồi trực tiếp dùng làm request key.** Có thể tạo key `arg0`, `arg1` nếu thiếu metadata.
2. **Đoán thiếu tên bằng regex `arg\\d+`.** Tên thật có thể là `arg0`; dùng `isNamePresent()`.
3. **Bật `-parameters` ở runtime.** Đây là compiler option; cần biên dịch lại đúng module.
4. **Chỉ bật `-parameters` ở app, không bật ở library chứa class được phản chiếu.** JAR thư viện không tự thay đổi.
5. **Tin rằng `-g` thay được `-parameters`.** Debug table và MethodParameters có mục đích khác nhau.
6. **Cho rằng mọi tham số sẽ có `isNamePresent()==false` khi không bật flag.** Một số cấu trúc/compiler có quy tắc khác; kiểm tra metadata thực tế.
7. **Cho rằng `isNamePresent()==true` thì không cần validate.** Tên có thể bị đổi do build, không phù hợp schema hoặc trùng.
8. **Đồng nhất parameter annotation với parameter name.** Annotation vẫn có thể hiện diện dù tên mất.
9. **Đọc nhầm `Method` của interface với implementation.** Hai khai báo có thể có metadata riêng.
10. **Dùng tên tham số làm một phần API public mà không kiểm soát thay đổi.** Rename biến ở source có thể thay đổi binding khi build giữ tên.
11. **Không test artifact cuối cùng.** IDE nhìn thấy source không chứng minh bytecode runtime lưu metadata.
12. **Cố xử lý mảng `getParameters()` rỗng bằng tên `arg0`.** Không có parameter thì không có tên fallback.
13. **Tự động dùng positional fallback không tài liệu hóa.** Có thể âm thầm gán giá trị sai vị trí khi method thay đổi.
14. **Nhầm annotation `TYPE_USE` với `PARAMETER`.** Phải đọc từ đối tượng reflection phù hợp.

## 19. Bài tập thực hành

**Bài 1 — Hai cách biên dịch.** Viết `void save(String id, int count)`, dùng reflection in `getName()` và `isNamePresent()`. Biên dịch một lần không flag, một lần với `-parameters`. Giải thích kết quả và xác định class file được chạy có phải bản mới không.

**Bài 2 — Tên trông như `arg0`.** Viết method có tham số tên thật là `arg0`, biên dịch với `-parameters`. Chứng minh `getName().equals("arg0")` không đủ để suy tên bị tổng hợp.

**Bài 3 — Binding phải có tên.** Viết utility nhận `Method`, kiểm tra toàn bộ `Parameter`. Nếu thiếu tên, ném `IllegalStateException` nêu rõ method và vị trí tham số. Dùng test xác minh lỗi khi thiếu `-parameters`.

**Bài 4 — Binding theo annotation.** Thêm `@WireName("account_id")` cho một tham số, bỏ trống metadata của tham số khác. Viết utility ưu tiên tên explicit; với tên thiếu hãy trả thông báo cấu hình hoặc fail fast. Thử trường hợp tên explicit rỗng và trùng.

**Bài 5 — Constructor.** Viết constructor `Order(String code, int amount)`, dùng `getDeclaredConstructor(...).getParameters()`. So sánh có/không `-parameters` và chú ý constructor overload phải xác định theo kiểu tham số.

**Bài 6 — Method interface và implementation.** Tạo `interface Service { void run(String task); }` và `class Impl implements Service`. Biên dịch chúng với các thiết lập khác nhau khi có thể, sau đó phản chiếu trên interface/implementation. Vì sao không được mặc định hai `Method` có cùng metadata?

**Bài 7 — Debug option.** Thử `javac -g` và `javac -parameters` riêng, xem `javap -v`. Ghi lại `MethodParameters` và các bảng debug để hiểu vì sao một công cụ source/debug khác với Java reflection.

**Bài 8 — API không phụ thuộc tên.** Viết một executor dùng danh sách kiểu và positional arguments, không cần `getName()`. Liệt kê điều kiện nào khiến positional binding an toàn và điều kiện nào làm nó trở nên mong manh.

## 20. Checklist khi code review

- **Đúng mục tiêu:** API thực sự cần tên tham số hay chỉ cần kiểu/thứ tự?
- **Đúng executable:** đang phản chiếu method/constructor của class, interface hoặc dependency nào?
- **Kiểm tra metadata:** có dùng `isNamePresent()` trước khi tin vào `getName()` không?
- **Build:** cờ `-parameters` đã được áp dụng cho module sở hữu class chưa?
- **Artifact:** đã test đúng class/JAR cuối cùng, không chỉ nhìn IDE source attachment chưa?
- **Fallback:** nếu thiếu tên, API báo lỗi rõ, dùng annotation, hoặc positional contract được định nghĩa đúng chưa?
- **Tương thích:** đổi tên tham số có làm đổi public binding hay phá tương thích không?
- **An toàn:** tên sau khi đọc có được validate theo schema, kiểm tra trùng và khả năng obfuscation không?
- **Dữ liệu khác:** có phân biệt parameter declaration annotations, type-use annotations và generic metadata không?
- **Trường hợp biên:** 0 tham số, nhiều tham số, constructor, method override, dependency khác compiler flag đã được test chưa?
- **Phiên bản:** đang dùng Java 8+ và các compiler/framework hiện được hỗ trợ, không dựa vào cơ chế legacy không được bảo đảm chưa?

## 21. Tóm tắt

- **`Parameter.getName()` luôn có thể cung cấp một chuỗi**, nhưng chuỗi đó có thể là tên tổng hợp `arg0`, `arg1` khi class file không lưu tên thật.
- **`Parameter.isNamePresent()` là kiểm tra đáng tin cậy** về sự hiện diện của tên theo metadata `MethodParameters`; đừng đoán từ hình dạng tên.
- **`javac -parameters`** là tùy chọn biên dịch cần thiết trong trường hợp thông thường để Java reflection giữ tên tham số, còn `-g` không phải một thay thế tương đương.
- **Metadata tên không phải toàn bộ metadata tham số.** Kiểu, generic signature và annotation có cơ chế riêng và có thể vẫn hiện diện khi tên không được lưu.
- **API tốt không âm thầm coi `argN` là tên hợp đồng.** Hãy ưu tiên tên explicit khi phù hợp, kiểm tra `isNamePresent()`, báo lỗi cấu hình hoặc dùng positional contract rõ ràng, đồng thời kiểm tra đúng artifact cuối cùng.
