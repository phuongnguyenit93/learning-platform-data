# javac -parameters và lưu tên tham số trong Java

## Mục tiêu học tập

Từ Java 8, reflection cung cấp **java.lang.reflect.Parameter** để truy vấn metadata về từng tham số của phương thức và constructor. Một điểm rất quan trọng: **tên tham số bạn viết trong source Java không mặc nhiên được lưu để truy vấn ở runtime**.

Tùy chọn **javac -parameters** yêu cầu trình biên dịch lưu tên của các formal parameters vào class file, thông qua metadata **MethodParameters**, để **Parameter.getName()** có thể trả đúng tên đã lưu. Nếu metadata tên không có, **getName()** có thể trả một tên tổng hợp như **arg0**, **arg1**; **Parameter.isNamePresent()** cho biết tên thật có được lưu hay không.

Bài học này giúp bạn hiểu chính xác -parameters làm gì; phân biệt thông tin tên tham số với kiểu, annotation và debug information; đọc tên tham số bằng reflection; kiểm chứng kết quả có/không có -parameters; xử lý constructor, generic, varargs và method override; cấu hình build cũng như thiết kế fallback. Các quy tắc này còn áp dụng trong Java hiện đại, gồm JDK 17+. Mọi ví dụ độc lập dùng cú pháp và API đã có từ Java 8.

## 1. Tại sao cần lưu tên formal parameter?

Giả sử có phương thức:

~~~java
static String makeLabel(String accountId, int sequence) {
    return accountId + "-" + sequence;
}
~~~

Đây là đoạn **minh họa cần đặt trong một lớp**, chưa phải chương trình độc lập. Đối với người đọc source code, accountId và sequence có ý nghĩa rõ ràng. Nhưng một framework hoặc công cụ có thể chỉ nhìn thấy tệp **.class** đã biên dịch, không có source.

Các nhu cầu thường gặp:

- Sinh tài liệu từ chữ ký phương thức hoặc constructor.
- Hiển thị thông báo lỗi có tên tham số dễ hiểu.
- Hỗ trợ một framework cấu hình mapping/binding bằng tên khi framework đó được thiết kế như vậy.
- Phân tích API bằng reflection và tạo metadata mô tả giao diện.
- Truy xuất tên các constructor parameters để công cụ hỗ trợ tạo đối tượng theo chính sách riêng.

**-parameters chỉ giúp lưu và đọc tên**. Nó không tự thực hiện JSON binding, dependency injection, validation hay bất kỳ business rule nào. Các công cụ phải chủ động sử dụng metadata này.

Lời gọi Java thông thường vẫn truyền đối số **theo vị trí**:

~~~java
makeLabel("ACC", 7);
~~~

Java không có cơ chế gọi method theo cú pháp có tên đối số như một số ngôn ngữ khác:

~~~java
// Không phải Java:
// makeLabel(accountId: "ACC", sequence: 7);
~~~

Đối với Java overload, **tên tham số không phân biệt chữ ký**. Hai phương thức có cùng tên và danh sách kiểu tham số không trở thành hai overload chỉ vì người viết dùng tên khác nhau.

## 2. -parameters ghi metadata vào lúc biên dịch

Lệnh:

~~~bash
javac -parameters Example.java
~~~

yêu cầu **javac** ghi tên các formal parameters của method/constructor được biên dịch vào class file. Metadata này gắn với **MethodParameters attribute**.

Ba lớp thông tin cần phân biệt:

1. **Tên trong source:** accountId, sequence, requestId, v.v.
2. **Tên được ghi trong class file:** có thể hiện diện khi compiler được cấu hình phù hợp.
3. **Tên do reflection trả về:** Parameter.getName() lấy tên đã lưu, hoặc tên do API tạo ra nếu thiếu metadata.

Điều này không thay đổi cách chương trình truyền đối số và không sửa mã nghiệp vụ của method. Class file vẫn chứa chữ ký phương thức với các kiểu tham số cần thiết dù **không** lưu tên.

**Không tự mở lại .java:** reflection đọc thông tin từ class đã được JVM nạp, không tự tìm tệp source để đoán tên.

**Không tự tác động lên thư viện khác:** nếu ứng dụng A được biên dịch có -parameters nhưng JAR thư viện B không lưu tên, A không thể tự thêm tên source vào các class của B tại runtime.

**Không lưu mọi local variable:** mục đích của cờ là tên **formal method/constructor parameters**, không phải biến trong thân phương thức hoặc mọi tên được compiler tạo ra.

## 3. API reflection dùng để đọc tham số

Các lớp **Method** và **Constructor** đều kế thừa **java.lang.reflect.Executable**, có các API liên quan tới tham số.

| Phương thức/API | Công dụng |
| --- | --- |
| **Executable.getParameters()** | Mảng Parameter theo thứ tự chữ ký runtime |
| **Executable.getParameterCount()** | Số tham số |
| **Parameter.getName()** | Tên được lưu hoặc tên tổng hợp |
| **Parameter.isNamePresent()** | Cờ xác nhận có tên được lưu |
| **Parameter.getType()** | Kiểu runtime dạng Class |
| **Parameter.getParameterizedType()** | Thông tin kiểu generic dạng Type khi có |
| **Parameter.getAnnotations()** | Annotation trên khai báo tham số theo retention/target |
| **Parameter.isVarArgs()** | Tham số có đánh dấu varargs hay không |
| **Parameter.isImplicit()** | Có phải tham số implicit/mandated theo metadata |
| **Parameter.isSynthetic()** | Có phải tham số synthetic theo metadata |

Ví dụ lấy method bằng tên và kiểu tham số:

~~~java
java.lang.reflect.Method method =
    Example.class.getDeclaredMethod(
        "makeLabel", String.class, int.class);

java.lang.reflect.Parameter[] parameters =
    method.getParameters();
~~~

Đây là mã minh họa, cần lớp Example có method makeLabel(String,int). **getDeclaredMethod** tìm theo tên method và các parameter types; nó không dựa vào tên formal parameter.

### getName() không phải phép thử tên thật

Không nên kiểm tra có tên bằng cách:

~~~java
// Không nên xem đây là cách xác nhận tên thật:
// if (parameter.getName() != null) { ... }
~~~

Vì **getName() có thể trả arg0 hoặc arg1 dù không có metadata tên**. Cách đúng:

~~~java
if (parameter.isNamePresent()) {
    System.out.println("Tên thật: " + parameter.getName());
} else {
    System.out.println("Không lưu tên tham số");
}
~~~

Các đoạn này cần một biến parameter kiểu java.lang.reflect.Parameter.

Cũng không nên viết **getName().startsWith("arg")** rồi kết luận đó là tên tổng hợp: người lập trình hoàn toàn có thể tự đặt tên tham số là arg0. **isNamePresent()** mới là tín hiệu chính thức.

## 4. Ví dụ hoàn chỉnh: biên dịch có và không có -parameters

Tạo tệp **ParameterFlagDemo.java**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterFlagDemo {

    public static String format(String customerId, int sequence) {
        return customerId + "-" + sequence;
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterFlagDemo.class.getDeclaredMethod(
            "format", String.class, int.class);

        System.out.println("Method: " + method.getName());

        for (Parameter parameter : method.getParameters()) {
            System.out.println(
                parameter.getName()
                + " | type=" + parameter.getType().getSimpleName()
                + " | present=" + parameter.isNamePresent());
        }

        System.out.println("Result: " + format("CUS", 7));
    }
}
~~~

### Biên dịch có lưu tên

~~~bash
javac -encoding UTF-8 -parameters ParameterFlagDemo.java
java ParameterFlagDemo
~~~

Kết quả:

~~~text
Method: format
customerId | type=String | present=true
sequence | type=int | present=true
Result: CUS-7
~~~

### Biên dịch lại không bật cờ

~~~bash
javac -encoding UTF-8 ParameterFlagDemo.java
java ParameterFlagDemo
~~~

Kết quả với javac thông thường:

~~~text
Method: format
arg0 | type=String | present=false
arg1 | type=int | present=false
Result: CUS-7
~~~

**Phân tích chính xác:**

- Method vẫn nhận String và int dù có hay không có metadata tên.
- Với -parameters, class file giữ customerId và sequence; reflection đọc tên và cờ present = true.
- Không có flag, getName() cung cấp tên tổng hợp arg0, arg1; present = false.
- Method body vẫn chạy cùng kết quả CUS-7; metadata tên không thay đổi tính toán.
- Khi so sánh, phải bảo đảm đã biên dịch lại và chương trình nạp **đúng class file**: nếu classpath trỏ đến một phiên bản khác, kết quả có thể gây hiểu nhầm.

**Kết luận:** tên tham số là một thành phần metadata tùy cấu hình biên dịch. Không có nghĩa thiếu tên thì lời gọi Java bị lỗi.

## 5. Xem MethodParameters trong class file bằng javap

Sau lệnh:

~~~bash
javac -parameters ParameterFlagDemo.java
javap -v ParameterFlagDemo
~~~

hãy tìm phần liên quan tới method **format** và mục **MethodParameters**. Một đoạn dạng minh họa:

~~~text
MethodParameters:
  Name                           Flags
  customerId
  sequence
~~~

Đây là ví dụ phần thông tin cần quan sát, **không phải toàn bộ stdout của javap**. Phiên bản JDK có thể trình bày các mục khác nhau. Khi không bật -parameters, method thông thường này có thể không có mục chứa tên như trên.

**javap -v** hữu ích vì kiểm tra **class file cụ thể**, không phụ thuộc vào một lời khẳng định rằng IDE hoặc build script đã bật đúng option.

Nếu dùng JAR, có thể trích/quan sát class phù hợp trong JAR theo công cụ và classpath của dự án. Quan trọng là **đọc đúng artifact cuối được ứng dụng sử dụng**.

## 6. -g và -parameters có giống nhau?

Không. Đây là một trong những lỗi hiểu thường gặp nhất.

**-g** liên quan debug information, ví dụ thông tin source, line numbers, local variables theo cấu hình. **-g:vars** yêu cầu debug local variable information. **-parameters** nhắm vào formal parameter names và **MethodParameters attribute**.

| Lệnh | Ý nghĩa | Có nên dùng để bảo đảm Parameter.isNamePresent()? |
| --- | --- | --- |
| **javac Example.java** | Biên dịch mặc định | Không |
| **javac -g Example.java** | Debug information | Không thay thế -parameters |
| **javac -g:vars Example.java** | Debug variable information | Không thay thế -parameters |
| **javac -parameters Example.java** | Giữ formal parameter names | Có, trong trường hợp phù hợp |
| **javac -g -parameters Example.java** | Cả hai loại thông tin | Có |

Một debugger có thể hiển thị tên biến từ thông tin debug. Nhưng Parameter API không được định nghĩa như công cụ đọc local variable table để bảo đảm tên formal parameter.

Nếu chương trình cần **Parameter.getName()** cho một method/constructor, hãy kiểm tra **isNamePresent()** trên chính class file đã biên dịch với **-parameters**.

## 7. Annotation của tham số không cần -parameters

Một annotation được gắn vào khai báo tham số có thể tồn tại tại runtime nếu nó có **RetentionPolicy.RUNTIME** và target phù hợp. Nó **không cần cờ -parameters** để lưu giá trị annotation.

### Ví dụ độc lập: tên tổng hợp nhưng annotation vẫn đọc được

Tạo tệp **ParameterAnnotationDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterAnnotationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface Key {
        String value();
    }

    static void lookup(@Key("user") String userId, int limit) {
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterAnnotationDemo.class
            .getDeclaredMethod("lookup", String.class, int.class);

        Parameter first = method.getParameters()[0];
        Key key = first.getAnnotation(Key.class);

        System.out.println("Name present: " + first.isNamePresent());
        System.out.println("Name: " + first.getName());
        System.out.println("Key: " + key.value());
        System.out.println("Count: " + method.getParameterCount());
    }
}
~~~

Biên dịch **không** có -parameters:

~~~bash
javac -encoding UTF-8 ParameterAnnotationDemo.java
java ParameterAnnotationDemo
~~~

Kết quả:

~~~text
Name present: false
Name: arg0
Key: user
Count: 2
~~~

Tại sao đúng?

- Không lưu tên formal parameter userId nên reflection trả arg0/present false.
- Annotation **@Key("user")** có retention RUNTIME và target PARAMETER nên reflection đọc được **Key.value() = "user"**.
- Method.getParameterCount() vẫn bằng 2; nó không cần tên để đếm.
- Biên dịch có -parameters sẽ thay đổi metadata tên, không phải là điều kiện để annotation Key được lưu.

**Lưu ý thêm:** annotation gắn lên **type use** của tham số có thể cần **getAnnotatedParameterTypes()**; không nên nhầm metadata của parameter declaration với metadata của kiểu sử dụng.

## 8. Generic, varargs và metadata tên là các khía cạnh khác nhau

Xét method:

~~~java
static <T> void send(
        java.util.List<T> items,
        String... tags) {
}
~~~

Đây là đoạn minh họa. Nó có hai formal parameters: items và tags. **tags** là varargs nhưng chữ ký runtime sử dụng kiểu mảng **String[]**.

### Ví dụ độc lập

Tạo tệp **GenericParameterDemo.java**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.List;

public class GenericParameterDemo {

    static <T> void send(List<T> items, String... tags) {
    }

    public static void main(String[] args) throws Exception {
        Method method = GenericParameterDemo.class.getDeclaredMethod(
            "send", List.class, String[].class);

        System.out.println("Method varargs: " + method.isVarArgs());

        for (Parameter parameter : method.getParameters()) {
            System.out.println(
                parameter.getName()
                + " | generic=" +
                    parameter.getParameterizedType().getTypeName()
                + " | varargs=" + parameter.isVarArgs()
                + " | named=" + parameter.isNamePresent());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 -parameters GenericParameterDemo.java
java GenericParameterDemo
~~~

Kết quả:

~~~text
Method varargs: true
items | generic=java.util.List<T> | varargs=false | named=true
tags | generic=java.lang.String[] | varargs=true | named=true
~~~

Giải thích:

1. **getDeclaredMethod("send", List.class, String[].class)** dựa trên kiểu tham số runtime. List<T> chịu type erasure thành List.
2. **getParameterizedType()** có thể mô tả **List<T>** dựa trên generic signature metadata; thông tin này không phải tên formal parameter.
3. **isVarArgs()** ở cấp Method là true; ở cấp Parameter là true cho tags, tham số varargs cuối.
4. **-parameters** làm isNamePresent true và tên items/tags hiện diện. Nếu bỏ flag, thông tin generic/varargs vẫn có thể được truy vấn bình thường.

Một method khai báo **String[] tags** không tự được xem là varargs chỉ vì có mảng. Cú pháp **String... tags** mới là dấu hiệu khai báo varargs.

## 9. Constructor cũng hỗ trợ parameter names

Tùy chọn -parameters lưu metadata formal parameters không chỉ cho method mà còn cho constructor. **Constructor.getParameters()** dùng cùng kiểu Parameter.

### Ví dụ độc lập

Tạo tệp **ConstructorParametersDemo.java**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class ConstructorParametersDemo {

    static final class Order {
        private final String orderId;
        private final long createdAt;

        Order(String orderId, long createdAt) {
            this.orderId = orderId;
            this.createdAt = createdAt;
        }

        String describe() {
            return orderId + "@" + createdAt;
        }
    }

    public static void main(String[] args) throws Exception {
        Constructor<Order> ctor =
            Order.class.getDeclaredConstructor(
                String.class, long.class);

        for (Parameter parameter : ctor.getParameters()) {
            System.out.println(
                parameter.getName()
                + " | " + parameter.getType().getSimpleName()
                + " | named=" + parameter.isNamePresent());
        }

        System.out.println(new Order("ORD-1", 120L).describe());
    }
}
~~~

Biên dịch:

~~~bash
javac -encoding UTF-8 -parameters ConstructorParametersDemo.java
java ConstructorParametersDemo
~~~

Kết quả:

~~~text
orderId | String | named=true
createdAt | long | named=true
ORD-1@120
~~~

Các công cụ tạo đối tượng có thể dùng tên constructor parameters, nhưng **-parameters không tự bật bất kỳ framework nào**. Từng framework có hợp đồng lựa chọn constructor, mapping, annotation và cấu hình riêng.

Một số constructor của inner classes, enum hoặc code do compiler sinh có thể chứa tham số implicit/synthetic hoặc metadata đặc biệt. Với công cụ reflection tổng quát, đừng giả định mọi Parameter tương ứng một tham số được người viết nhìn thấy trực tiếp trong source.

## 10. Interface và implementation có thể giữ tên khác nhau

Java không yêu cầu formal parameter names giống nhau giữa interface và class triển khai:

~~~java
interface Handler {
    void handle(String requestId);
}

class HandlerImpl implements Handler {
    @Override
    public void handle(String traceId) {
    }
}
~~~

Đây là hai khai báo minh họa. Chữ ký override vẫn hợp lệ vì tham số cùng kiểu String. Nếu cả hai được biên dịch có -parameters, reflection của method interface có thể trả requestId, còn method implementation trả traceId.

### Chương trình hoàn chỉnh

Tạo tệp **OverrideNamesDemo.java**:

~~~java
import java.lang.reflect.Method;

public class OverrideNamesDemo {

    interface Handler {
        void handle(String requestId);
    }

    static final class HandlerImpl implements Handler {
        @Override
        public void handle(String traceId) {
        }
    }

    public static void main(String[] args) throws Exception {
        Method contract = Handler.class.getDeclaredMethod(
            "handle", String.class);

        Method impl = HandlerImpl.class.getDeclaredMethod(
            "handle", String.class);

        System.out.println(
            "Interface: " + contract.getParameters()[0].getName());
        System.out.println(
            "Implementation: " + impl.getParameters()[0].getName());
        System.out.println(
            "Both present: " +
            (contract.getParameters()[0].isNamePresent()
             && impl.getParameters()[0].isNamePresent()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 -parameters OverrideNamesDemo.java
java OverrideNamesDemo
~~~

Kết quả:

~~~text
Interface: requestId
Implementation: traceId
Both present: true
~~~

Đây là một vấn đề thực tế khi thiết kế framework binding: nếu tên tham số có vai trò nghiệp vụ, phải định nghĩa **Method nào là nguồn metadata**, interface hay implementation. Reflection không tự đổi tên implementation thành tên interface, cũng không coi việc khác tên là vi phạm override.

## 11. -parameters là cờ compile-time, không phải runtime

Nếu bạn biên dịch module A với -parameters nhưng module B đã là JAR không có metadata tên, khi A dùng reflection với class của B vẫn có thể nhận **isNamePresent() = false**. Cờ của A không sửa class file B.

Không có cách dùng lệnh chạy JVM để tự biến class không có tên formal parameter thành class có tên thật. Muốn có tên của library B, phải có metadata trong artifact B hoặc một nguồn mapping khác được framework hỗ trợ.

Đây là lý do build đa module cần xác định **module nào phát hành lớp chứa method/constructor cần đọc tên**. Bật flag ở sai module sẽ không giải quyết lỗi.

## 12. Cấu hình javac và các hệ thống build

Với javac:

~~~bash
javac -encoding UTF-8 -parameters Example.java
~~~

Với **Maven Compiler Plugin** có hỗ trợ cấu hình parameters, có thể dùng đoạn XML minh họa trong pom.xml hợp lệ:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Cần chọn phiên bản plugin phù hợp và kiểm tra cấu hình thật sự có hiệu lực ở module chứa source.

Với Gradle Groovy DSL, một ví dụ cấu hình JavaCompile:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Đây là **đoạn cấu hình Groovy DSL**, không phải Kotlin DSL; cú pháp của build.gradle.kts khác. Các phiên bản Gradle hoặc plugin có thể yêu cầu điều chỉnh để phù hợp môi trường dự án.

**IDE và CI:** nếu IDE dùng một compiler/cấu hình khác với pipeline chính thức, kết quả build có thể không giống nhau. Nên đặt compiler arguments trong build system chính thức và xác nhận artifact cuối.

**JAR và transformation:** bytecode processing, shading, minification hoặc obfuscation có thể ảnh hưởng tới metadata. Cần xác minh tệp class cuối được phát hành, không chỉ tin rằng lệnh đầu tiên có -parameters.

## 13. Kiểm tra đúng artifact

Một quy trình QA có thể thực hiện:

1. Build sạch module thực sự chứa method cần tên.
2. Dùng **javap -v** xem MethodParameters của class sau build.
3. Chạy test reflection trên **đúng class** dùng trong production.
4. Kiểm tra tên và **isNamePresent()** cho những method/constructor quan trọng.
5. Thử cả trường hợp JAR sau packaging, nếu có quá trình xử lý bytecode.
6. Nếu thiếu metadata, kiểm tra compiler args, build cache, multi-module setup và classpath.
7. Không suy luận từ tên arg0 rằng lớp được biên dịch bằng một trình biên dịch cụ thể; hãy kiểm tra isNamePresent.

Một method minh họa có thể yêu cầu metadata ngay lúc khởi tạo:

~~~java
static void requireParameterNames(
        java.lang.reflect.Executable executable) {
    for (java.lang.reflect.Parameter p : executable.getParameters()) {
        if (!p.isNamePresent()) {
            throw new IllegalStateException(
                "Missing parameter names for " +
                executable.getName() +
                "; compile declaring class with -parameters");
        }
    }
}
~~~

Điều này phù hợp nếu hệ thống **bắt buộc** có tên thật cho binding. Không nhất thiết áp cho mọi method bên thứ ba vì nhiều API không cần lưu tên tham số.

## 14. Xử lý khi metadata không có

Nếu tên chỉ dùng để hiển thị, một fallback rõ ràng:

~~~java
static String displayName(
        java.lang.reflect.Parameter p, int index) {
    return p.isNamePresent()
        ? p.getName()
        : "parameter#" + index;
}
~~~

Nếu framework dùng tên để ánh xạ dữ liệu đầu vào theo key, tốt hơn nên **báo lỗi cấu hình** hoặc yêu cầu explicit mapping, thay vì âm thầm xem arg0 là tên do người lập trình đặt.

Một chính sách binding có thể chỉ định tên thông qua annotation cấu hình riêng do framework hỗ trợ. Khi đó hãy tuân theo hợp đồng của chính framework, không giả định mọi thư viện đều có chung cách dùng -parameters.

**Lưu ý về thay đổi API:** đổi tên formal parameter không ảnh hưởng trực tiếp đến cách Java gọi method theo vị trí, nhưng có thể ảnh hưởng một framework dựa trên tên. Nếu tên là hợp đồng bên ngoài, cần tài liệu hóa và kiểm thử nó.

## 15. Không nhầm metadata với validation

Một method khai báo tham số **age** và được biên dịch -parameters. Java vẫn không tự kiểm tra rằng age phải không âm.

~~~java
static void register(int age) {
    if (age < 0) {
        throw new IllegalArgumentException(
            "age must not be negative");
    }
}
~~~

Đây là phương thức minh họa. **Điều kiện if** thực thi kiểm tra; tên age trong class-file metadata không phải một validator.

Đừng kết luận một framework tự động mapping/validation chỉ vì getName() trả customerId. Metadata là **dữ liệu để công cụ sử dụng**, không phải một hook runtime được kích hoạt mặc định.

Tên định danh cũng không được chứa thông tin bí mật; tên tham số có thể được người khác quan sát trong class file. Nhưng việc không giữ tên cũng **không phải** cơ chế bảo mật để bảo vệ giá trị dữ liệu thực.

## 16. Những trường hợp đặc biệt cần thận trọng

**Synthetic/implicit parameters:** một số method/constructor do compiler sinh hoặc xử lý có thể có thêm formal parameters hoặc flags đặc biệt. Dùng **isImplicit()**, **isSynthetic()** và **isNamePresent()** đúng mục đích; chúng không cùng một nghĩa.

**Method instance:** receiver **this** thông thường không phải phần tử Parameter riêng trong chữ ký của method instance. getParameters() mô tả formal parameters, không tự thêm this vào danh sách.

**Overload:** getDeclaredMethod dùng tên method và các kiểu như String.class, int.class để tìm đúng overload. Không chọn overload bằng tên accountId hay sequence.

**Generic:** Parameter.getType() trả Class runtime, có thể đã xóa type arguments; getParameterizedType() có thể mô tả List<T> từ generic signature. -parameters không thay thế generic metadata.

**Varargs:** String... thể hiện ở runtime là String[] cộng cờ varargs. Không nhầm một tham số varargs thành nhiều Parameter.

**Lambda/synthetic methods:** chi tiết method do compiler sinh không nên trở thành hợp đồng public dựa trên tên tham số. Tên có thể phụ thuộc cách compiler sinh bytecode.

**Record trên JDK mới:** record (ổn định từ Java 16) có metadata riêng cho record components. Không coi mọi tên record component là bằng chứng rằng mọi constructor/method Java thường đều được biên dịch có -parameters.

**Obfuscation:** công cụ xử lý class file có thể đổi tên hoặc loại bỏ metadata. Hãy xác minh artifact cuối khi ứng dụng phụ thuộc vào parameter names.

## 17. Lỗi thường gặp và cách khắc phục

| Nhầm lẫn | Thực tế | Cách làm |
| --- | --- | --- |
| Tên trong source luôn truy cập được bằng reflection | .class có thể không giữ tên | Bật -parameters |
| getName() trả null nếu thiếu tên | Có thể trả arg0/arg1 | Kiểm tra isNamePresent |
| Tên bắt đầu arg chứng tỏ tên tổng hợp | Người viết có thể đặt tên arg0 | Không suy đoán qua chuỗi |
| -g:vars thay thế -parameters | Debug metadata và MethodParameters khác nhau | Dùng đúng cờ |
| -parameters là lựa chọn lúc chạy JVM | Đây là cờ javac lúc biên dịch | Đặt ở compile task |
| Bật flag ở app khiến JAR phụ thuộc có tên | Metadata thuộc từng class file | Kiểm tra/chỉnh build library |
| Tên tham số được dùng để chọn overload | Tên method và parameter types quyết định | Truy vấn đúng chữ ký |
| Interface và implementation phải dùng cùng tên | Override không phụ thuộc formal parameter name | Quy định chính sách đọc Method |
| Annotation cần -parameters | Retention/target độc lập | Đọc annotation theo API thích hợp |
| getType() cho biết đầy đủ List<String> | Generic type arguments có thể bị erasure | Dùng getParameterizedType |
| -parameters lưu mọi local variable | Chỉ formal parameters theo cơ chế này | Không dùng Parameter cho locals |
| -parameters tự validation | Không thêm logic kiểm tra | Viết code hoặc cấu hình framework |
| Cấu hình build tồn tại là đủ | Artifact cuối có thể khác | Kiểm tra javap và reflection |
| Tên formal parameter luôn là contract API | Java thường gọi theo vị trí | Tài liệu hóa nếu binding dựa vào tên |

## 18. Bài tập thực hành

**Bài 1.** Với method **void send(String topic, int retries)** được biên dịch có -parameters, getName()/isNamePresent() thường trả gì?

**Đáp án:** topic/true và retries/true.

**Bài 2.** Cùng method biên dịch không có cờ, theo javac thông thường nhận gì?

**Đáp án:** arg0/false và arg1/false; kiểu String/int không đổi.

**Bài 3.** Chỉ dùng -g:vars có bảo đảm isNamePresent true không?

**Đáp án:** không; debug information không thay thế metadata MethodParameters.

**Bài 4.** App bật -parameters nhưng JAR thư viện không có tên formal parameter. App có đọc lại tên source của JAR nhờ cờ riêng không?

**Đáp án:** không; phải kiểm tra artifact của thư viện.

**Bài 5.** Vì sao @Key("user") có thể đọc được khi Parameter.getName() trả arg0?

**Đáp án:** annotation với RUNTIME retention và parameter name metadata là hai cơ chế độc lập.

**Bài 6.** Method send(List<T> items,String... tags) có bao nhiêu Parameter? Kiểu runtime của tags là gì?

**Đáp án:** hai Parameter; tags là String[] và có cờ varargs.

**Bài 7.** Interface khai báo requestId, implementation khai báo traceId. Java override có hợp lệ không?

**Đáp án:** có; tên formal parameter không phải phần của quan hệ override.

**Bài 8.** Hệ thống bắt buộc tên thật để binding nhưng isNamePresent false. Nên tiếp tục dùng arg0 hay báo lỗi?

**Đáp án:** trừ khi framework có binding theo vị trí rõ ràng, nên fail fast hoặc yêu cầu explicit mapping.

**Bài 9.** Dùng công cụ nào để xác nhận metadata của tệp class cuối?

**Đáp án:** javap -v và một test reflection chạy trên đúng class file được sử dụng.

**Bài 10.** Tên tham số age được lưu có tự chặn -1 không?

**Đáp án:** không. Cần code validation thực tế.

## Tổng kết

**javac -parameters** giúp lưu tên formal parameters của method/constructor vào class file thông qua metadata **MethodParameters**. Reflection **Parameter.getName()** có thể trả tên thật khi metadata có mặt; **isNamePresent()** cho biết điều đó. Khi tên bị thiếu, getName() vẫn có thể trả arg0/arg1, nhưng isNamePresent() là false.

Tùy chọn này **không** thay thế -g, không tự sửa dependency đã biên dịch, không thay đổi chữ ký method hay cách truyền đối số, không lưu mọi local variable, và không tự tạo validation. Để dùng an toàn trong Java hiện đại: **bật -parameters đúng module khi cần, kiểm tra artifact cuối, phân biệt tên thật với tên tổng hợp và định nghĩa fallback/hợp đồng rõ ràng**.