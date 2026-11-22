# Giới hạn metadata khi dependency được build khác cấu hình

## 1. Bối cảnh và mục tiêu

Một ứng dụng Java thường dùng **dependency đã được build** thành các tệp `.class` hoặc `.jar`, chứ không biên dịch lại toàn bộ mã nguồn của thư viện. Java Reflection đọc **thông tin còn tồn tại trong class file được class loader nạp ở runtime**. Vì vậy, nếu dependency được build với một bộ compiler flags, annotation processors, bytecode transformers hoặc cấu hình đóng gói khác, ứng dụng có thể nhìn thấy metadata khác với những gì tác giả thư viện nhìn thấy trong source/IDE.

Chủ đề thuộc nhóm **Metadata tham số**. Trọng tâm là `java.lang.reflect.Executable`, `Parameter`, `Method` và `Constructor` từ Java 8, kết hợp các vấn đề generic signatures, annotations, debug information và Java modules vẫn còn áp dụng ở Java hiện đại.

Sau bài này, bạn sẽ:

- Giải thích vì sao `-parameters` phải được bật tại **module thực sự biên dịch dependency**, không chỉ ở module ứng dụng.
- Phân biệt tên tham số, kiểu tham số sau erasure, generic signature, declaration annotations, type-use annotations, debug symbols và flags implicit/synthetic.
- Dùng `Parameter.isNamePresent()` để xác định tên nguồn có thật trong class file hay không.
- Biết đọc `@Retention`, `@Target` và các điểm vào reflection thích hợp.
- So sánh **hai binary cùng source** nhưng khác compiler flags qua một ví dụ chạy được trên JDK 17+.
- Kiểm tra chính binary bằng `javap -v` và xác minh dependency phiên bản nào được nạp.
- Thiết kế phương án dự phòng rõ ràng cho routing, binding, dependency injection và các framework phụ thuộc metadata.

**Nguyên tắc:** nguồn sự thật của Reflection runtime là **artifact được nạp**, không phải nội dung file nguồn, cấu hình của một module khác hay nhận định từ IDE.

## 2. Những loại metadata có điều kiện tồn tại khác nhau

Một method:

~~~java
public String format(String input, int times) {
    return input.repeat(times);
}
~~~

có những thông tin khác nhau:

| Metadata | API hoặc nơi lưu | Ý nghĩa |
| --- | --- | --- |
| Tên method và kiểu tham số | `getName()`, `getParameterTypes()`, method descriptor | JVM cần cho linking và invocation |
| Tên formal parameters | `Parameter.getName()`, `isNamePresent()`, `MethodParameters` attribute | Có thể không được lưu nếu không dùng `-parameters` |
| Generic declaration | `getGenericParameterTypes()`, `Signature` attribute | Có thể mang `List<String>` thay vì chỉ `List` |
| Parameter declaration annotations | `Parameter.getAnnotation(...)` | Phụ thuộc retention, target và class-file attributes |
| Type-use annotations | `getAnnotatedParameterTypes()` | Có thể ở kiểu tham số, type argument hoặc các tầng khác |
| Debug metadata | `-g`, `LocalVariableTable`, line numbers | Phục vụ debugger, không thay `MethodParameters` |
| Synthetic/implicit flags | `isSynthetic()`, `isImplicit()` | Phản ánh cấu trúc do compiler/bytecode generator tạo |
| Module metadata | `module-info.class`, `exports`, `opens` | Điều chỉnh khả năng truy cập; không tái tạo tên bị mất |

Nếu `getParameterTypes()` vẫn cho `String.class` và `int.class`, điều đó **không** chứng minh tên `input` và `times` tồn tại. Nếu `getGenericParameterTypes()` tìm được `List<String>`, điều đó cũng không chứng minh có annotation ở runtime.

**Không có một cờ compiler duy nhất làm cho mọi loại metadata đều xuất hiện.** Mỗi loại có cơ chế lưu/đọc riêng.

## 3. Flag -parameters và giới hạn khi dependency được build riêng

Trên `javac`, `-parameters` yêu cầu compiler giữ tên formal parameters của methods/constructors trong class file:

~~~bash
javac --release 17 -parameters DependencyApi.java
~~~

Với dependency được build theo cách đó:

~~~java
Method m = DependencyApi.class.getMethod(
        "format", String.class, int.class);

Parameter first = m.getParameters()[0];

System.out.println(first.isNamePresent());
System.out.println(first.getName());
~~~

Nếu class file thật giữ `MethodParameters` và tên `input`, hai dòng in tương ứng `true` và `input`. Các dòng trên là **mã minh họa**, cần imports và xử lý `NoSuchMethodException`.

Khi không có metadata tên, `getName()` thường trả tên **tổng hợp** dạng `arg0`, `arg1`; `isNamePresent()` báo `false`. Không kiểm tra `getName() != null` để đoán có tên thật, vì `getName()` không dùng `null` làm tín hiệu thiếu metadata.

### Vì sao bật -parameters trong ứng dụng không giúp JAR phụ thuộc?

Giả sử:

~~~text
module application ─ javac -parameters ─ application classes
module library ───── javac không có flag ─ library classes
                                     |
                               runtime classpath
~~~

`-parameters` chỉ ảnh hưởng **những source files được compiler task tương ứng biên dịch**. Nếu library đã được publish thành JAR, compiler của application không mở JAR và ghi thêm tên tham số vào mọi method của nó.

Hậu quả:

- Reflection có thể lấy tên source của classes trong application, nhưng không lấy được tên từ dependency.
- Recompile chỉ consumer mà không recompile provider không bổ sung `MethodParameters` vào library.
- JVM không thể suy ra chính xác tên source chỉ từ kiểu `(String,int)`.
- Một công cụ decompile có thể dựng tên để hiển thị, nhưng tên dựng lại không phải bằng chứng rằng tên thật đã được lưu.

Giải pháp là sửa **build pipeline của dependency và phát hành artifact mới**, hoặc không phụ thuộc tên source: dùng explicit annotation values, schema, configuration hay positional contract được thiết kế rõ ràng.

## 4. -g không phải -parameters

`-g` và `-g:vars` bật một số **debugging attributes** như `LocalVariableTable`. Một debugger có thể đọc tên biến từ chúng, nhưng hợp đồng `Parameter.isNamePresent()` dựa vào **MethodParameters attribute** trong class file, không phải việc debugger từng nhìn thấy một cái tên.

| Tùy chọn | Dữ liệu nhắm tới | Có đủ để `isNamePresent()` bảo đảm true? |
| --- | --- | --- |
| `-parameters` | Metadata tên formal parameters | Có thể, nếu artifact giữ đúng thuộc tính |
| `-g` | Debug information | Không |
| `-g:vars` | Local-variable debug info | Không |
| `-g:none` | Không sinh debug info | Không tự quyết định trạng thái của `MethodParameters` |

Một số công cụ có cách đọc local-variable metadata riêng. Nhưng đó là **implementation detail của công cụ**, không phải cam kết của `java.lang.reflect.Parameter`.

Khi điều tra, đừng coi “source name thấy trong debugger” là dấu hiệu rằng `Parameter.getName()` ở production cũng trả tên ấy.

## 5. Ví dụ Java 17+ độc lập: cùng client, hai binary dependency

Hai file dưới đây được kiểm thử trên OpenJDK với `--release 17`. Một file định nghĩa dependency, file còn lại là client sử dụng Reflection. Chúng được build thành các thư mục riêng, để chỉ thay **binary dependency** ở runtime.

### DependencyApi.java

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;

public class DependencyApi {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface Role {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeMark {
        String value();
    }

    public String format(
            @Role("text")
            @TypeMark("string-type") String input,
            int times) {
        return input.repeat(times);
    }

    public List<String> collect(
            List<@TypeMark("element-type") String> values) {
        return List.copyOf(values);
    }
}
~~~

Ở đây:
- `input` và `times` là **tên formal parameters** có thể được lưu nhờ `-parameters`.
- `Role` là annotation trên **parameter declaration** và có `RUNTIME` retention.
- `TypeMark` đánh dấu **type use**, gồm kiểu `String` của tham số đầu và type argument `String` trong `List<String>`.
- `String.repeat` có từ Java 11, `List.copyOf` từ Java 10: chương trình này dùng JDK 17+, không phải ví dụ chạy trên runtime Java 8 cũ.

### DependencyProbe.java

~~~java
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class DependencyProbe {

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Method format = DependencyApi.class.getMethod(
                "format", String.class, int.class);

        System.out.println("count=" + format.getParameterCount());

        for (int i = 0; i < format.getParameterCount(); i++) {
            Parameter p = format.getParameters()[i];

            DependencyApi.Role role =
                    p.getAnnotation(DependencyApi.Role.class);

            DependencyApi.TypeMark marker =
                    p.getAnnotatedType()
                     .getAnnotation(DependencyApi.TypeMark.class);

            System.out.println("parameter." + i + ".name=" +
                    (p.isNamePresent() ? p.getName() : "<missing>"));

            System.out.println("parameter." + i + ".type=" +
                    p.getType().getSimpleName());

            System.out.println("parameter." + i + ".role=" +
                    (role == null ? "-" : role.value()));

            System.out.println("parameter." + i + ".typeMark=" +
                    (marker == null ? "-" : marker.value()));
        }

        Method collect = DependencyApi.class.getMethod(
                "collect", java.util.List.class);

        AnnotatedParameterizedType parameter =
                (AnnotatedParameterizedType)
                        collect.getAnnotatedParameterTypes()[0];

        DependencyApi.TypeMark item =
                parameter.getAnnotatedActualTypeArguments()[0]
                         .getAnnotation(DependencyApi.TypeMark.class);

        System.out.println("elementMark=" +
                (item == null ? "-" : item.value()));

        DependencyApi service = new DependencyApi();
        System.out.println("result=" + service.format("ha", 2));
    }
}
~~~

`main` khai báo `throws ReflectiveOperationException` để bao phủ checked exceptions của `getMethod(...)`. `format("ha",2)` không khai báo checked exceptions. Tên thiếu được hiển thị bằng `<missing>`, không phải dùng `arg0` như tên hợp đồng.

### Biên dịch và chạy trên Linux/macOS

~~~bash
mkdir -p out/plain out/named out/client

javac --release 17 -d out/plain DependencyApi.java
javac --release 17 -parameters -d out/named DependencyApi.java
javac --release 17 -cp out/named -d out/client DependencyProbe.java

java -cp out/plain:out/client DependencyProbe
java -cp out/named:out/client DependencyProbe
~~~

**Windows PowerShell:** dấu phân cách classpath là **`;`** thay vì `:`. Thay hai lệnh chạy bằng:

~~~powershell
java -cp "out/plain;out/client" DependencyProbe
java -cp "out/named;out/client" DependencyProbe
~~~

Tạo ba thư mục output tương ứng trước khi compile. Không đặt thêm bản `DependencyApi.class` khác vào `out/client`, vì classpath có thể nạp nhầm bản dependency và làm sai phép so sánh.

### Output 1: dependency thiếu -parameters

~~~text
count=2
parameter.0.name=<missing>
parameter.0.type=String
parameter.0.role=text
parameter.0.typeMark=string-type
parameter.1.name=<missing>
parameter.1.type=int
parameter.1.role=-
parameter.1.typeMark=-
elementMark=element-type
result=haha
~~~

### Output 2: dependency có -parameters

~~~text
count=2
parameter.0.name=input
parameter.0.type=String
parameter.0.role=text
parameter.0.typeMark=string-type
parameter.1.name=times
parameter.1.type=int
parameter.1.role=-
parameter.1.typeMark=-
elementMark=element-type
result=haha
~~~

**Điều cần quan sát:** Hai binary dùng cùng source và hai lệnh chạy dùng **cùng một client**. Chỉ **tên tham số** thay đổi. Kiểu `String`/`int`, annotations có `RUNTIME` retention, annotation lồng trong `List<...>` và kết quả tính toán không đổi. Đây là một minh họa rằng `-parameters` và annotation metadata là **hai cơ chế độc lập**. Ví dụ đã được biên dịch và so sánh stdout thực tế trên OpenJDK.

## 6. Method descriptor vẫn tồn tại khi tên biến mất

Một phương thức `format(String input,int times)` cần biết danh sách **kiểu JVM-level** để JVM và compiler liên kết lời gọi. Reflection:

~~~java
Class<?>[] rawTypes = method.getParameterTypes();
~~~

có thể cung cấp `String.class` và `int.class` ngay cả khi tên source không còn trong class file.

Những điểm cần phân biệt:
- Tên formal parameter **không** là thành phần lựa chọn overload của Java.
- `Class.getMethod(name, Class<?>... parameterTypes)` tra cứu chữ ký dựa trên tên method và kiểu tham số (theo reflection), không dựa vào tên `input` hay `times`.
- Method descriptor không có nghĩa là **generic type arguments** `<String>` được reify ở runtime.
- Method có thể chạy đúng qua lời gọi Java bình thường trong khi một framework phụ thuộc tên tham số lại bind sai request.

## 7. Generic Signature không đồng nghĩa MethodParameters

Ví dụ:

~~~java
public void accept(java.util.List<String> values) {
}
~~~

Phản chiếu có nhiều góc nhìn:

~~~java
Class<?> raw = method.getParameterTypes()[0];
java.lang.reflect.Type generic =
        method.getGenericParameterTypes()[0];
~~~

`raw` thường là `List.class` vì **type erasure**. Khi generic signature được lưu trong artifact, `generic` có thể là `ParameterizedType` mô tả `List<String>`.

Thông tin generic như vậy thường nằm ở **`Signature` attribute** trong class file; còn tên `values` thuộc metadata `MethodParameters` khi có.

- Bật `-parameters` **không** phải cách tái tạo `Signature` đã mất.
- Một thư viện có `Signature` không chắc có tên formal parameters.
- Bytecode transformation có thể xóa/biến đổi generic signatures, khiến một framework phản chiếu generic types bị thiếu thông tin.
- Một object `new ArrayList<String>()` không tự mang một runtime class riêng cho `String`; đó không phải cách khôi phục generic declaration metadata.

Nếu công cụ DI/serialization cần phân biệt `List<String>` với `List<Order>`, phải kiểm tra binary có giữ những metadata generic mà contract đòi hỏi hay không.

## 8. Annotation retention và metadata độc lập với tên tham số

Annotation có `@Retention(RetentionPolicy.RUNTIME)` được giữ để đọc qua Java Reflection runtime khi xuất hiện đúng vị trí và metadata không bị loại bỏ.

| Retention | Ý nghĩa | Java runtime Reflection |
| --- | --- | --- |
| `SOURCE` | Annotation không được giữ vào class file | Không đọc được |
| `CLASS` | Được ghi vào class file nhưng không bắt buộc xuất hiện qua Reflection runtime | Không phải nguồn đọc thông thường |
| `RUNTIME` | Được giữ để Reflection có thể đọc | Có, với API/vị trí phù hợp |

Nếu annotation type không khai báo `@Retention`, mặc định là `CLASS`. **Không có compiler flag của consumer tự biến CLASS thành RUNTIME.**

Hai vị trí khác nhau:

~~~java
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface FieldName {
    String value();
}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface ElementMark {
    String value();
}
~~~

Một method:

~~~java
void submit(
        @FieldName("customer")
        java.util.List<@ElementMark("item") String> values) {
}
~~~

có thể được đọc như sau:

~~~java
Parameter p = method.getParameters()[0];

FieldName binding = p.getAnnotation(FieldName.class);

AnnotatedParameterizedType list =
        (AnnotatedParameterizedType) p.getAnnotatedType();

ElementMark element = list.getAnnotatedActualTypeArguments()[0]
        .getAnnotation(ElementMark.class);
~~~

Đây là **các đoạn minh họa**, cần imports và class bao ngoài. Annotation trên **declaration của parameter** khác với annotation nằm **trên type argument**. Nếu chỉ đọc `p.getAnnotations()`, có thể không thấy metadata ở `List<@ElementMark String>`.

**Không nên coi sự có mặt của annotation tự động xác thực dữ liệu**. Một marker tên `NonNull` hoặc `Positive` chỉ mang semantic validation khi checker/framework có khả năng xử lý nó.

## 9. Class file đã qua transformation hoặc obfuscation

Dependency có thể trải qua các giai đoạn:

~~~text
source -> compiler -> .class -> optimizer/obfuscator/weaver
       -> packager/shader -> published JAR -> class loader
~~~

Những công cụ sau compile **có thể** đổi tên class/member, sinh bridge methods, đổi hoặc bỏ metadata attributes. Điều đó phụ thuộc công cụ và cách cấu hình; không được mặc định cứ dùng shading là mất tất cả annotation hay cứ dùng obfuscation là Reflection chắc chắn hỏng.

Những metadata quan trọng cần kiểm tra trong artifact cuối cùng:

- `MethodParameters` nếu framework dùng tên tham số.
- `Signature` nếu framework dùng generic type information.
- `RuntimeVisibleParameterAnnotations` cho runtime declaration annotations.
- `RuntimeVisibleTypeAnnotations` cho runtime type-use annotations.
- Các annotations và attributes khác mà framework cần theo hợp đồng.
- Tên/descriptor của class/method/field khi có các quy tắc keep/renaming.

Nên viết **integration test chạy với JAR sau bước biến đổi cuối**, không chỉ unit test trên output `javac` trước khi obfuscate. Nếu bạn dùng một công cụ cụ thể, hãy kiểm tra tài liệu cấu hình keep attributes của **chính phiên bản công cụ đó**.

## 10. Dùng javap -v để kiểm tra artifact thực tế

Công cụ `javap` đi kèm JDK giúp inspect class file:

~~~bash
javap -v -p -classpath out/plain DependencyApi
javap -v -p -classpath out/named DependencyApi
~~~

Tập trung vào đúng method và các attributes:

- **`MethodParameters`**: tên tham số (và flags) được giữ hay không.
- **`Signature`**: metadata generic nếu có.
- **`RuntimeVisibleParameterAnnotations`**: annotations trên khai báo tham số.
- **`RuntimeVisibleTypeAnnotations`**: annotations trên các vị trí sử dụng kiểu.
- **`LocalVariableTable`** / **`LineNumberTable`**: debug metadata.

`javap -v` có thể in rất nhiều dữ liệu; không phải class nào cũng có đủ mọi attribute. Dùng đúng JAR/class path của artifact lỗi. Nếu cần xác nhận ở một JAR được publish, chỉ vào JAR đó thay vì output directory của một build cục bộ khác.

**Điều cần phân biệt:** Build configuration mô tả cách *dự định* sinh bytecode. `javap` trên published JAR cho bằng chứng về thứ **thực sự còn sau đóng gói**.

## 11. Runtime đang nạp đúng dependency version chưa?

Có những trường hợp ứng dụng compile với phiên bản thư viện A nhưng runtime classpath/module path lại nạp B:

- Method có signature khác, dẫn tới `NoSuchMethodException` khi reflective lookup.
- Tên tham số, annotation hoặc generic signature khác.
- Một artifact đã bị tối ưu loại bỏ metadata.
- Quy tắc module `exports`/`opens` khác kỳ vọng.
- Class bị định nghĩa bởi class loader khác.

Có thể quan sát nguồn nạp class khi môi trường cho phép:

~~~java
Class<?> type = DependencyApi.class;

java.security.ProtectionDomain domain =
        type.getProtectionDomain();

if (domain != null && domain.getCodeSource() != null) {
    System.out.println(domain.getCodeSource().getLocation());
}
~~~

Đây là **mã minh họa**, không nên dựa vào nó như API luôn trả URL: `getCodeSource()` có thể `null`. Khi điều tra, xem thêm class loader, module, resolved dependency graph và version/hash của artifact.

Trong hệ thống plugin/application server, hai class có cùng tên đầy đủ nhưng được định nghĩa bởi hai class loaders khác nhau vẫn có thể là hai runtime types khác nhau. So sánh tên string thôi chưa đủ để xác minh identity.

## 12. Các fallback an toàn khi tên tham số thiếu

### A. Fail fast nếu contract thực sự yêu cầu tên source

~~~java
static void requireNames(java.lang.reflect.Executable executable) {
    for (java.lang.reflect.Parameter parameter :
            executable.getParameters()) {
        if (!parameter.isNamePresent()) {
            throw new IllegalStateException(
                    "Missing parameter names: " +
                    executable.getDeclaringClass().getName()
                    + "#" + executable.getName());
        }
    }
}
~~~

Nếu framework thực sự bind theo tên, một lỗi cấu hình rõ ràng lúc khởi động thường an toàn hơn việc âm thầm dùng `arg0` làm tên trường request.

### B. Dùng annotation value làm tên công khai

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface RequestField {
    String value();
}

void handle(@RequestField("user_id") String id) {
}
~~~

Nếu runtime có annotation metadata và framework đọc đúng, `"user_id"` không phụ thuộc source parameter name `id`. Cách này giúp giữ hợp đồng ổn định khi đổi tên biến nội bộ.

### C. Dùng descriptor/schema/configuration riêng

Có thể mô tả tên, kiểu, thứ tự, validation và phiên bản API trong schema hoặc generated adapter được kiểm thử. Cách này hữu ích khi không kiểm soát JAR bên ngoài. Nhưng phải giữ schema đồng bộ với chữ ký thực tế.

### D. Positional binding chỉ khi API thiết kế theo vị trí

Nếu protocol đã định nghĩa rõ tham số `0` và `1` có nghĩa gì, binding theo vị trí có thể hợp lệ. Không tự động đổi từ binding theo tên sang theo vị trí khi source names biến mất: đổi thứ tự method parameters có thể âm thầm gán sai dữ liệu.

**Tránh:** dựa vào chuỗi tên bắt đầu bằng `arg` để suy đoán metadata có thật hay không. Một developer hoàn toàn có thể đặt tên nguồn là `arg0`; kiểm tra đúng là `Parameter.isNamePresent()`.

## 13. Build flags trong Maven và Gradle: đặt ở module tạo bytecode

Với Maven, cấu hình điển hình ở **POM của module cần giữ parameter names**:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <parameters>true</parameters>
  </configuration>
</plugin>
~~~

Đoạn XML này cần đặt trong cấu trúc build/plugins hợp lệ. Quản lý plugin version theo chính sách của dự án, không cần sao chép một số phiên bản cũ cố định.

Với Gradle Java plugin trong **Groovy DSL**:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Kotlin DSL có cú pháp khác; cần kiểm tra task thực sự sinh class và các source sets hoặc toolchains có liên quan.

**Đặt flag ở application không build lại dependency từ Maven repository.** Nếu bạn muốn sửa metadata của thư viện đã publish, nhà cung cấp/thư viện phải phát hành artifact phù hợp hoặc bạn phải dùng một contract không phụ thuộc tên tham số.

## 14. -parameters có thể đủ cho method thường nhưng không giải quyết mọi edge case

### Implicit/synthetic parameters

Constructor của non-static inner class có thể cần enclosing-instance parameter, còn compiler-generated methods và bridge methods cũng có thể có cấu trúc đặc biệt. Vì thế:

- `Executable.getParameterCount()` có thể không trùng số lượng tham số tác giả thấy trong một declaration đặc biệt.
- `Parameter.isImplicit()` và `isSynthetic()` cung cấp thông tin khi metadata phù hợp.
- `Method.isBridge()` và `Method.isSynthetic()` giúp xử lý các method do compiler tạo.
- Không coi mọi reflected executable là một public API method viết trực tiếp trong source.

### Records và generated bytecode

Records (Java 16+) và các language compilers/code generators có metadata rules riêng. Không suy rằng tất cả constructors/generated members đều có cùng naming/annotation behavior như một method thường được compile bằng `javac -parameters`.

### Multi-release JAR

Nếu JAR có các class variants dành cho nhiều Java versions, runtime có thể chọn class khác nhau theo JDK. Khi điều tra, phải xác định entry class thật được nạp; không chỉ đọc một file ở root JAR rồi kết luận về mọi runtime.

## 15. Access control/JPMS không phải vấn đề tên bị mất

Từ Java 9, Java Platform Module System (JPMS) đưa ra các quy tắc `exports`, `opens`. Một dependency có đầy đủ metadata vẫn có thể từ chối reflective deep access từ module khác.

Phân biệt triệu chứng:

| Triệu chứng | Nhóm nguyên nhân cần kiểm tra |
| --- | --- |
| `isNamePresent() == false` | Metadata `MethodParameters` thiếu |
| `NoSuchMethodException` | Lookup sai tên/signature/phạm vi |
| `IllegalAccessException` | Access rules của method/constructor |
| `InaccessibleObjectException` | Deep reflection bị module/access hạn chế |
| `ClassNotFoundException` | Class resolution/loading |
| `TypeNotPresentException` | Type được metadata tham chiếu không khả dụng |
| `GenericSignatureFormatError` | Generic signature không hợp lệ |

Bật `--add-opens` chỉ tác động một số ràng buộc module; nó **không** tái tạo tên source đã mất. Đừng dùng mở toàn bộ modules như phương án mặc định cho một vấn đề vốn thuộc build metadata.

## 16. Hậu quả thực tế với dependency injection và HTTP binding

Một framework DI có thể scan constructors:

~~~java
java.lang.reflect.Constructor<?> ctor =
        Service.class.getDeclaredConstructor(
                Repository.class, Config.class);
~~~

Nếu framework dùng **kiểu tham số** và explicit qualifier annotations, nó không nhất thiết cần tên source. Nhưng nếu framework dùng tên formal parameters để phân biệt các dependencies cùng kiểu, thiếu `-parameters` có thể làm binding thất bại.

Với HTTP routing, nếu framework muốn biến:

~~~json
{"input":"ha","times":2}
~~~

thành lời gọi `format(String input,int times)` theo **tên**, thì `arg0`/`arg1` không đủ để suy ra mapping sang JSON keys. Framework cần:
- Explicit annotation names;
- Schema/configuration đã được kiểm chứng;
- Parameter names được dependency giữ lại; hoặc
- Báo lỗi rõ khi thiếu contract.

**Method chạy đúng không chứng minh binding framework đúng.** Một unit test gọi trực tiếp `format("ha",2)` vẫn pass ở cả hai binary dù tên tham số phản chiếu khác nhau.

## 17. Test metadata contract trên artifact sau đóng gói

Nếu framework phụ thuộc `-parameters`, thêm một test:

~~~java
Method m = DependencyApi.class.getMethod(
        "format", String.class, int.class);

Parameter[] parameters = m.getParameters();

if (!parameters[0].isNamePresent()) {
    throw new AssertionError(
            "Library must be compiled with parameter metadata");
}

if (!"input".equals(parameters[0].getName())) {
    throw new AssertionError("Unexpected parameter contract");
}
~~~

Đoạn này là **mã minh họa** với imports và throws/try-catch phù hợp. Test nên chạy trên **published JAR hoặc kết quả pipeline cuối cùng**, không chỉ trên output trung gian của compiler.

Không bắt buộc mọi dependency có `-parameters` nếu application không cần metadata đó. Test đúng thứ mà contract yêu cầu, tránh tạo một ràng buộc build không cần thiết.

Nếu app cần generic annotations, thêm test trên `getGenericParameterTypes()` và `getAnnotatedParameterTypes()`. Nếu app cần deep reflection, thêm integration test ở môi trường modules thật. Những loại metadata này không thay thế cho nhau.

## 18. Quy trình chẩn đoán lỗi theo thứ tự

Khi framework không lấy được thông tin tham số của một library:

1. **Chỉ rõ method/constructor**: declaring class, tên, kiểu tham số erasure và overload.
2. **Xác minh đúng binary runtime**: JAR version, class loader, module, classpath/module path.
3. **Kiểm tra tên**: `getParameters()`, `isNamePresent()`; tránh phỏng đoán từ `getName()`.
4. **Kiểm tra generic type**: `getParameterTypes()` so với `getGenericParameterTypes()`.
5. **Kiểm tra annotation**: `@Retention`, `@Target`; declaration vs type-use API.
6. **Dùng javap -v** trên artifact thực tế để inspect `MethodParameters`, `Signature` và runtime annotation attributes.
7. **So sánh compiler/build config** của module sinh ra dependency, không chỉ application.
8. **Xác minh post-processors**: optimizer, obfuscator, bytecode weaving, shading, packaging.
9. **Kiểm tra JPMS/access** riêng nếu reflection gặp lỗi truy cập.
10. **Tái hiện bằng một ví dụ tối thiểu** với cùng client và hai phiên bản binary.
11. **Sửa đúng tầng**: dependency recompile, keep rules, explicit annotation/schema hoặc contract fallback.
12. **Khóa bằng integration test** trên published artifact và runtime JDK mục tiêu.

Đây là quy trình giúp tránh sửa sai chỗ. Lỗi “không tìm được tên parameter” không tự giải quyết bằng thay overload, bật debug flag, hay mở module.

## 19. Lỗi và hiểu nhầm phổ biến

1. **Ứng dụng bật `-parameters` thì dependencies cũng có tên.** Sai: các dependencies đã build riêng.
2. **`getName()` trả `null` khi thiếu metadata.** Sai: reflection có tên tổng hợp; dùng `isNamePresent()`.
3. **Tên `arg0` chắc chắn không thể là tên thật.** Sai: tên source cũng có thể là `arg0`; đừng dùng string heuristic.
4. **`-g` thay cho `-parameters`.** Sai: `LocalVariableTable` khác `MethodParameters`.
5. **Thiếu source name khiến method không thể gọi.** Sai: JVM descriptor vẫn có kiểu tham số.
6. **Có generic signature là có parameter names.** Sai: hai attributes khác nhau.
7. **Annotation `CLASS` tự được runtime Reflection đọc.** Không: cần retention/điểm đọc phù hợp, thường là `RUNTIME`.
8. **`@Retention(RUNTIME)` tự validate nullness.** Sai: metadata không tự thi hành quy tắc.
9. **Type-use annotations nằm cùng chỗ với parameter declaration annotations.** Sai: reflection paths khác nhau.
10. **Decompile JAR luôn khôi phục tên tham số source.** Sai: công cụ có thể đặt tên phỏng đoán.
11. **Obfuscator nào cũng bỏ hoặc luôn giữ mọi metadata.** Không: tùy tool và keep rules.
12. **Chỉ nhìn source đúng version là đủ.** Không: runtime có thể nạp binary khác.
13. **`--release` hoặc đổi JDK sẽ vá JAR cũ.** Không: cần đúng artifact build.
14. **`setAccessible(true)` giải quyết missing names.** Không: access control khác metadata.
15. **Một object `List<String>` luôn giữ type argument trong runtime class.** Sai: generics phần lớn chịu erasure.
16. **Unit test hành vi pass chứng minh metadata đúng.** Không: introspection phải test riêng.
17. **Class loader không ảnh hưởng reflection.** Sai: runtime identity và artifact được nạp có thể khác.
18. **Mọi reflected parameter đều tương ứng 1–1 với source.** Không tuyệt đối: có implicit/synthetic parameters.

## 20. Bài tập thực hành

**Bài 1:** Build `DependencyApi` với và không có `-parameters`. Chạy cùng `DependencyProbe`. Hãy chỉ ra chính xác những dòng stdout khác nhau và giải thích vì sao kiểu/annotation không đổi.

**Bài 2:** Biên dịch bản dependency chỉ có `-g:vars`, không có `-parameters`. Dùng `javap -v` và `isNamePresent()` để so sánh debug name với reflection name.

**Bài 3:** Đổi `Role` từ `RUNTIME` sang `CLASS`. Dự đoán kết quả `p.getAnnotation(Role.class)` và giải thích cơ chế retention.

**Bài 4:** Cho method `void save(List<@TypeMark String> values)`. Viết chuỗi API từ `getAnnotatedParameterTypes()[0]` tới annotation của type argument.

**Bài 5:** Một framework cần bind JSON key `user_id` nhưng dependency thiếu parameter name. Thiết kế `@RequestField("user_id")` hoặc descriptor tường minh, nêu fallback an toàn.

**Bài 6:** Một JAR sau obfuscation vẫn chạy nhưng `getGenericParameterTypes()` chỉ cho thông tin erased. Attributes nào cần kiểm tra bằng `javap`? Vì sao `-parameters` không phải cách sửa mặc định?

**Bài 7:** Application build với `-parameters` nhưng một dependency từ Maven repository không có tên. Nêu ba cách xác minh artifact và giải pháp dài hạn.

**Bài 8:** Lỗi `InaccessibleObjectException` xảy ra khi truy cập private member của module khác. Vì sao nó khác `isNamePresent()==false` và nên kiểm tra những module directives nào?

**Bài 9:** Viết test build kiểm tra parameter name contract trên JAR sau packaging. Giải thích vì sao test trên source output trước shading chưa đủ.

**Bài 10:** Cùng một class name tồn tại ở hai version JAR. Cách xác nhận class loader/source binary thực sự và tránh đặt niềm tin vào thứ tự classpath không được kiểm soát?

## 21. Kết luận

- **Dependency build config quyết định metadata tồn tại trong binary của chính dependency đó.** Compiler flags của consumer không tự sửa metadata trên class files đã xuất bản.
- **`-parameters` và `Parameter.isNamePresent()`** là cơ chế cốt lõi để phát hiện tên formal parameters trong Reflection hiện đại.
- **`-g`, generic `Signature`, runtime annotations, type annotations, implicit/synthetic flags** không đồng nhất và có thể tồn tại/thiếu độc lập.
- **`javap -v` và metadata integration tests trên artifact cuối cùng** cung cấp bằng chứng rõ hơn việc nhìn vào source hoặc cấu hình build.
- **Class loaders, module access và bytecode transformations** có thể làm runtime khác môi trường phát triển; phải tách các nguyên nhân khi chẩn đoán.
- Nếu contract cần tên tham số và metadata không có, **fail fast hoặc dùng explicit annotation/schema**. Không âm thầm sử dụng `argN` như tên nghiệp vụ.
- Những kiến thức này vẫn đúng và hữu ích trên JDK hiện đại; ví dụ mã chọn Java 17+ để sử dụng API còn được hỗ trợ.

## 22. Tài liệu chính thức

1. Java SE 17 — `Parameter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html
2. Java SE 17 — `Executable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html
3. Java SE 17 — `Method`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
4. JDK 17 — lệnh `javac` (`-parameters`, `-g`, `--release`): https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
5. JDK 17 — lệnh `javap`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
6. Java SE 17 — `RetentionPolicy`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html
7. Java SE 17 — `AnnotatedType`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html
8. JVM Specification, Chapter 4 — class file attributes (`MethodParameters`, `Signature`, runtime annotations): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
9. Java Language Specification — `8.4.1 Formal Parameters`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1

Khi gặp một lỗi Reflection trong hệ thống thật, hãy hỏi trước tiên: **artifact nào đang được nạp, và artifact ấy thực sự có những metadata attributes nào?** Từ câu trả lời đó, chọn sửa build, cấu hình bytecode transformation, hoặc hợp đồng dữ liệu công khai; tránh suy đoán từ source hay từ cấu hình của một module không tạo ra class đang bị lỗi.