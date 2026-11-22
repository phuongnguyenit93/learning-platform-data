# Giới hạn của type annotation: annotation không tự tạo kiểm tra runtime trong Java

## Mục tiêu học tập

**Type annotation** cho phép gắn metadata lên **vị trí sử dụng kiểu dữ liệu (type use)**, chẳng hạn kiểu của biến, kiểu phần tử generic, kiểu trả về, kiểu của tham số phương thức hoặc một thành phần trong kiểu mảng. Cú pháp này được mở rộng trong Java 8 và vẫn được sử dụng trên các JDK hiện đại.

Tuy nhiên, một giới hạn đặc biệt quan trọng là: **việc đặt annotation lên kiểu không tự khiến JVM hoặc javac kiểm tra quy tắc nghiệp vụ mà annotation diễn đạt**. Ví dụ, bạn có thể viết một annotation mang ý nghĩa “không được null”, nhưng chỉ riêng annotation đó không tự phát sinh câu lệnh ném lỗi khi bạn truyền null.

Sau bài học, bạn sẽ:

- Hiểu **type annotation** là gì và khác gì với annotation trên khai báo.
- Phân biệt **annotation hiện diện trong source**, **được lưu trong class file**, **đọc được qua reflection** và **thực sự được kiểm tra**.
- Nắm vai trò của **@Target**, **ElementType.TYPE_USE**, **ElementType.TYPE_PARAMETER** và **@Retention**.
- Biết vì sao **@Retention(RUNTIME)** không đồng nghĩa “tự chạy validator”.
- Phân biệt việc **javac kiểm tra cú pháp/vị trí annotation** với việc kiểm tra **quy tắc do annotation muốn diễn đạt**.
- Sử dụng **AnnotatedType** và các API reflection liên quan để đọc annotation trên kiểu.
- Chọn cách triển khai kiểm tra phù hợp: **Objects.requireNonNull**, mã validation thủ công, static checker được cấu hình, hoặc validation framework có cơ chế kích hoạt rõ ràng.
- Nhận ra giới hạn của metadata ở các vị trí generic, mảng, nested type và dữ liệu đến từ bên ngoài.

Các ví dụ hoàn chỉnh dùng cú pháp tương thích Java 8 và có thể chạy trên JDK 8+, gồm JDK 17 và các bản mới hơn. Những thông tin được trình bày là các quy tắc còn áp dụng; không dựa vào cơ chế annotation đã lỗi thời.

## 1. Type annotation là gì?

Trước Java 8, nhiều vị trí phổ biến của annotation thường được hiểu như **chú thích cho một khai báo**: lớp, phương thức, biến, field. Java 8 mở rộng hệ thống annotation để có thể chú thích **kiểu được dùng** trong các biểu thức, khai báo và thành phần kiểu.

Ví dụ minh họa (cần định nghĩa annotation **NonNullLike** và đặt trong một class phù hợp):

~~~java
@NonNullLike String name;

java.util.List<@NonNullLike String> names;

@NonNullLike String findName(@NonNullLike String key);

String @NonNullLike [] values;
~~~

Điểm cần chú ý: type annotation có thể xuất hiện ở những vị trí chi tiết như **String nằm trong List<String>** hoặc **thành phần mảng**. Nó không chỉ gắn nhãn cho một field hay một method như một khối.

Một annotation dùng cho type use có thể khai báo:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface NonNullLike {
}
~~~

Đây là đoạn khai báo minh họa. **ElementType.TYPE_USE** cho phép dùng annotation trên vị trí sử dụng kiểu. **RetentionPolicy.RUNTIME** yêu cầu metadata tương ứng được giữ lại để có thể truy cập qua những API reflection được hỗ trợ tại runtime.

**Điều không xảy ra:** khai báo annotation tên NonNullLike không tự biến String thành kiểu runtime đặc biệt, không làm câu lệnh gán null tự động báo lỗi, cũng không thêm kiểm tra null vào mọi phương thức.

Tên annotation do bạn đặt (NonNullLike, Checked, Safe, Required...) **không phải một từ khóa mà javac hiểu về ý nghĩa**. Nếu không có công cụ phân tích hoặc mã kiểm tra sử dụng annotation, phần lớn các quy tắc nghiệp vụ bạn gắn lên nó chỉ là **metadata**.

## 2. Bốn tầng cần phân biệt

Một annotation có thể tham gia những tầng khác nhau của chương trình. Đừng gộp tất cả thành “Java đã kiểm tra annotation”.

| Tầng | Điều thực sự xảy ra | Điều không được bảo đảm |
| --- | --- | --- |
| **Source/biên dịch** | Javac kiểm tra cú pháp, annotation type, vị trí dùng, giá trị thành phần và các quy tắc Java liên quan | Không mặc định hiểu mọi ý nghĩa nghiệp vụ như “non-null” |
| **Class file** | Metadata có thể được ghi vào bytecode/class file tùy retention và loại annotation | Chỉ có metadata không làm chương trình tự kiểm tra |
| **Reflection runtime** | Annotation có retention RUNTIME có thể được đọc bằng API reflection tương ứng | Reflection không tự gọi validator và không tự sửa dữ liệu |
| **Enforcement** | Một checker, framework, agent hoặc mã ứng dụng **được cấu hình và chạy** sử dụng metadata để kiểm tra | Không xảy ra chỉ vì annotation tồn tại |

Hãy phân biệt các câu sau:

1. **“Annotation được phép đặt ở đó.”** Liên quan @Target và ngữ cảnh cú pháp.
2. **“Annotation được lưu lại.”** Liên quan @Retention và dạng metadata.
3. **“Annotation có thể được tìm thấy.”** Liên quan retention, API reflection và vị trí gắn annotation.
4. **“Một quy tắc được thực thi.”** Đòi một **cơ chế sử dụng annotation**, không phải chỉ có metadata.

Vì vậy câu **“@Retention(RUNTIME) sẽ kiểm tra lúc chạy”** là **sai**. RUNTIME nói về khả năng lưu và truy xuất annotation, không định nghĩa một hook kiểm tra mặc định.

## 3. @Target: annotation được phép dùng ở vị trí nào?

Các giá trị thuộc **ElementType** định nghĩa vị trí mà annotation có thể áp dụng. Với chủ đề này, hai giá trị quan trọng nhất là:

- **ElementType.TYPE_USE**: sử dụng trên một vị trí có kiểu, ví dụ String trong List<String>, kiểu trả về, kiểu tham số, thành phần của mảng, cast hoặc kiểu trong biểu thức tạo đối tượng khi hợp lệ.
- **ElementType.TYPE_PARAMETER**: khai báo tham số kiểu, ví dụ **class Box<@Marker T>** hoặc **<@Marker T> T identity(T value)**.

Khi một annotation được khai báo **@Target(ElementType.TYPE_USE)**, nó còn có phạm vi áp dụng rộng liên quan tới những vị trí sử dụng kiểu theo quy tắc Java. Để tài liệu API dễ hiểu, vẫn nên biết điểm khác biệt giữa **kiểu của một giá trị** và **khai báo một type parameter**.

Các target khác có thể dùng khi cần một annotation trên khai báo:

- **ElementType.FIELD** cho khai báo field.
- **ElementType.PARAMETER** cho khai báo tham số phương thức.
- **ElementType.METHOD** cho khai báo phương thức.
- **ElementType.TYPE** cho khai báo lớp/interface/enum/annotation type.

Một annotation có thể hỗ trợ nhiều target:

~~~java
@Target({
    ElementType.TYPE_USE,
    ElementType.TYPE_PARAMETER,
    ElementType.PARAMETER
})
@Retention(RetentionPolicy.RUNTIME)
@interface DocumentedConstraint {
}
~~~

Đây là đoạn minh họa. Việc đưa thêm PARAMETER không khiến annotation tự kiểm tra giá trị tham số. Nó chỉ cho phép annotation được sử dụng như metadata của khai báo tham số ở những ngữ cảnh phù hợp.

**Cạm bẫy:** annotation gắn lên **khai báo tham số** và annotation gắn lên **kiểu của tham số** không nhất thiết được tìm qua cùng một API reflection. Hãy chọn vị trí đặt và API đọc metadata phù hợp. Nếu annotation chỉ có TYPE_USE, đừng mặc nhiên cho rằng mọi trường hợp đều xuất hiện trong danh sách annotation khai báo trả bởi Parameter.getAnnotations().

## 4. @Retention: SOURCE, CLASS và RUNTIME khác nhau

Ba mức retention phổ biến:

| Retention | Có trong source | Có trong class file | Đọc qua reflection runtime tiêu chuẩn? |
| --- | --- | --- | --- |
| **SOURCE** | Có | Không giữ lại như annotation | Không |
| **CLASS** | Có | Có | Thường không qua reflection runtime tiêu chuẩn |
| **RUNTIME** | Có | Có | Có, qua API tương ứng khi annotation ở vị trí được hỗ trợ |

Nếu không khai báo @Retention, chính sách mặc định là **CLASS**.

Ví dụ:

~~~java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE_USE)
@interface SourceHint {
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE_USE)
@interface ClassHint {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface RuntimeHint {
}
~~~

Đây là ba khai báo minh họa; cần import annotation types. Chúng có thể dùng để bổ sung thông tin cho công cụ, nhưng **cả ba không tự trở thành một điều kiện if hoặc một lệnh throw** trong chương trình.

SOURCE thích hợp nếu thông tin chỉ cần trong quá trình xử lý source. CLASS giữ metadata trong class file để công cụ phân tích class file có thể sử dụng. RUNTIME cho phép code reflection đọc metadata. Chọn retention theo **ai cần tiêu thụ metadata** chứ không theo giả định rằng retention cao hơn đồng nghĩa kiểm tra mạnh hơn.

### “Giữ lại đến runtime” không đồng nghĩa “gọi validator”

Một annotation runtime có thể chỉ mang nhãn hiển thị hoặc chú thích một kiểu. Nếu không có code thực hiện:

~~~java
if (value == null) {
    throw new IllegalArgumentException("value must not be null");
}
~~~

hoặc một cơ chế tương đương, Java không tự suy luận quy tắc kiểm tra từ tên annotation. Đoạn trên là code minh họa kiểm tra thủ công, cần nằm trong phương thức có biến value phù hợp.

## 5. Ví dụ hoàn chỉnh: annotation hiển thị qua reflection nhưng không cấm null

Tạo tệp **TypeAnnotationMetadataDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

public class TypeAnnotationMetadataDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Label {
        String value();
    }

    private final List<@Label("element") String> names =
        Arrays.asList("An", null);

    private @Label("return-type") String first() {
        return names.get(0);
    }

    public static void main(String[] args) throws Exception {
        Field field =
            TypeAnnotationMetadataDemo.class.getDeclaredField("names");

        AnnotatedParameterizedType listType =
            (AnnotatedParameterizedType) field.getAnnotatedType();

        AnnotatedType elementType =
            listType.getAnnotatedActualTypeArguments()[0];

        System.out.println(
            "Element annotation: " +
            elementType.getAnnotation(Label.class).value());

        Method method =
            TypeAnnotationMetadataDemo.class.getDeclaredMethod("first");

        System.out.println(
            "Return annotation: " +
            method.getAnnotatedReturnType()
                .getAnnotation(Label.class).value());

        TypeAnnotationMetadataDemo demo =
            new TypeAnnotationMetadataDemo();

        System.out.println(
            "Null element allowed at runtime: " +
            (demo.names.get(1) == null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 TypeAnnotationMetadataDemo.java
java TypeAnnotationMetadataDemo
~~~

Kết quả:

~~~text
Element annotation: element
Return annotation: return-type
Null element allowed at runtime: true
~~~

Phân tích:

1. Annotation Label được khai báo **TYPE_USE** và **RUNTIME**. Lúc biên dịch, Java cho phép đặt Label trên kiểu String nằm trong **List<String>** và trên kiểu String trả về của phương thức first().
2. **Field.getAnnotatedType()** trả đối tượng mô tả kiểu được chú thích của field. Với List<...>, có thể cast sang **AnnotatedParameterizedType** để xem các tham số kiểu đã chú thích.
3. **getAnnotatedActualTypeArguments()[0]** truy cập metadata của String trong List. **getAnnotation(Label.class)** tìm Label tại vị trí đó.
4. **Method.getAnnotatedReturnType()** truy cập annotation trên kiểu trả về của phương thức; đây không phải luôn là cùng nơi lưu annotation của khai báo phương thức.
5. Danh sách **vẫn chứa null**. JVM không đọc tên "element" hay việc Label gắn lên String rồi tự cấm phần tử null.

**Thông điệp:** reflection cho thấy annotation được **lưu và tìm thấy**, nhưng không có bước kiểm tra tự động. Nếu muốn bảo đảm các phần tử trong danh sách không null, code/framework cần kiểm tra các phần tử bằng một cơ chế riêng.

Một biểu thức có thể dùng List<@Label String> để mô tả ý định, nhưng generic metadata không biến phần tử String thành một runtime type mới. Kiểu Java tham số hóa vẫn tuân theo các quy tắc generics và type erasure hiện hành.

## 6. Type annotation không thay đổi giá trị null được phép ở Java

Giả sử ta định nghĩa:

~~~java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface RequiredValue {
}
~~~

Và viết:

~~~java
static @RequiredValue String echo(@RequiredValue String value) {
    return value;
}
~~~

Hai đoạn này là minh họa cần import annotation types và đặt khai báo trong một lớp.

Nếu gọi **echo(null)**, Java không mặc định phát sinh lỗi chỉ vì tham số được đánh dấu **@RequiredValue**. Thân echo chỉ trả lại value; kết quả có thể là null.

Cần phân biệt các cơ chế:

- **Ngôn ngữ Java**: kiểu tham chiếu như String thường có thể mang giá trị null; type annotation tùy chỉnh không tự biến nó thành loại kiểu khác được JVM cưỡng chế.
- **Static analyzer**: một công cụ được cấu hình có thể diễn giải annotation nullness và báo lỗi/cảnh báo ở compile time.
- **Runtime validator**: mã được kích hoạt có thể kiểm tra null bằng if, Objects.requireNonNull hoặc framework chuyên biệt.
- **Reflection**: chỉ đọc metadata nếu có; tự nó không bắt buộc một hành động nào.

Annotation không phải là một **type system bảo đảm non-null nội tại** của Java. Câu nói “đã ghi @NonNull nên method chắc chắn không nhận null” chỉ đúng nếu kiến trúc dự án có **điều kiện bổ sung được bảo đảm**; bản thân cú pháp không đủ.

## 7. Ví dụ hoàn chỉnh: kiểm tra null đến từ code, không đến từ annotation

Tạo tệp **ExplicitRuntimeValidationDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Objects;

public class ExplicitRuntimeValidationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface RequiredValue {
    }

    static @RequiredValue String unchecked(
            @RequiredValue String value) {
        return value;
    }

    static @RequiredValue String checked(
            @RequiredValue String value) {
        return Objects.requireNonNull(
            value, "value must not be null");
    }

    public static void main(String[] args) {
        System.out.println(
            "Unchecked accepts null: " +
            (unchecked(null) == null));

        try {
            checked(null);
        } catch (NullPointerException ex) {
            System.out.println(
                "Checked error: " + ex.getMessage());
        }

        System.out.println(
            "Checked value: " + checked("Java"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ExplicitRuntimeValidationDemo.java
java ExplicitRuntimeValidationDemo
~~~

Kết quả:

~~~text
Unchecked accepts null: true
Checked error: value must not be null
Checked value: Java
~~~

**Vì sao hai phương thức khác nhau?**

- Cả unchecked và checked cùng có annotation trên kiểu tham số và kiểu trả về.
- **unchecked** không có câu lệnh nào cấm null, nên trả null như bình thường.
- **checked** gọi **Objects.requireNonNull(...)**, do đó ném NullPointerException với thông báo rõ khi giá trị null.
- Nếu xóa annotation khỏi checked mà giữ lại requireNonNull, kiểm tra vẫn chạy. Nếu xóa requireNonNull mà giữ annotation, kiểm tra không còn.

Đó là cách kiểm chứng đơn giản nhất rằng **annotation không phải chính câu lệnh validation**.

### Có phải luôn dùng Objects.requireNonNull?

Không. Chọn exception và chính sách theo hợp đồng API:

- **Objects.requireNonNull(value, "name")** hợp lý khi null vi phạm điều kiện tham số phải có.
- **IllegalArgumentException** có thể phù hợp khi dữ liệu là chuỗi rỗng, số âm hoặc cấu trúc không hợp lệ.
- **Optional** phù hợp khi việc **không có giá trị** là một tình huống bình thường cần được biểu diễn trong kiểu trả về, thay vì một lỗi phải ném.
- Ở biên hệ thống, dữ liệu từ JSON/HTTP/database cần chính sách validation riêng; annotation không tự làm dữ liệu đầu vào đáng tin cậy.

## 8. Reflection chỉ cung cấp nguyên liệu cho một validator được viết rõ

Nếu muốn annotation thực sự có tác dụng ở runtime, bạn có thể **viết một cơ chế kiểm tra**. Mã cần:

1. Xác định nơi đặt annotation và cách đọc metadata.
2. Nhìn vào giá trị thực tế.
3. Quyết định trường hợp hợp lệ/không hợp lệ.
4. Ném exception hoặc trả kết quả lỗi theo hợp đồng.
5. Bảo đảm API gọi cơ chế đó trên mọi đường dữ liệu cần bảo vệ.

Đây là lý do một framework validation thường cần **tích hợp và kích hoạt**: có annotation trên classpath không có nghĩa mọi constructor hoặc method call trong Java sẽ tự chạy framework.

### Ví dụ hoàn chỉnh: tự dùng annotation để chủ động kiểm tra

Tạo tệp **OptInReflectionValidatorDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Method;
import java.util.Locale;

public class OptInReflectionValidatorDemo {

    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Required {
    }

    static String normalize(@Required String value) {
        return String.valueOf(value).toUpperCase(Locale.ROOT);
    }

    static String callChecked(Method method, String value)
            throws Exception {

        AnnotatedType parameterType =
            method.getAnnotatedParameterTypes()[0];

        if (parameterType.isAnnotationPresent(Required.class)
                && value == null) {
            throw new IllegalArgumentException(
                "value is required");
        }

        return (String) method.invoke(null, value);
    }

    public static void main(String[] args) throws Exception {
        Method method =
            OptInReflectionValidatorDemo.class.getDeclaredMethod(
                "normalize", String.class);

        System.out.println(
            "Direct call: " + normalize(null));

        try {
            callChecked(method, null);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                "Validated call: " + ex.getMessage());
        }

        System.out.println(
            "Valid call: " + callChecked(method, "java"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OptInReflectionValidatorDemo.java
java OptInReflectionValidatorDemo
~~~

Kết quả:

~~~text
Direct call: NULL
Validated call: value is required
Valid call: JAVA
~~~

**Điều chứng minh của ví dụ:**

- **normalize(null)** chạy trực tiếp và không bị chặn chỉ vì tham số có @Required. String.valueOf(null) trả "null", sau đó toUpperCase cho "NULL".
- **callChecked** chủ động truy cập **method.getAnnotatedParameterTypes()[0]** và kiểm tra annotation ở **kiểu của tham số**.
- Khi gặp null và có @Required, code viết tay ném **IllegalArgumentException**.
- Khi truyền "java", quá trình kiểm tra cho phép gọi phương thức bằng reflection và nhận "JAVA".

Đây là **trình kiểm tra minh họa rất hẹp**, không phải bộ validation tổng quát. Nó chỉ xử lý một tham số String của một phương thức static, không hỗ trợ đủ nested generic type, instance receiver, overloaded methods, primitive, collections, recursion, exception propagation hoặc chính sách chuẩn hóa lỗi.

**Quan trọng:** việc gọi normalize bằng cách thông thường vẫn không đi qua callChecked. Bạn phải chủ động dẫn lời gọi qua validator, hoặc sử dụng cơ chế của framework để mọi đường thực thi được kiểm tra theo hợp đồng.

## 9. Static checker, IDE và annotation processor khác runtime validator

Một annotation có thể **hữu ích tại compile time** dù nó không tự tạo kiểm tra runtime.

Ví dụ, một dự án có thể dùng **Checker Framework** hoặc một bộ phân tích nullness được cấu hình để hiểu các qualifier liên quan tới nullability. Công cụ đó có thể phát hiện một đường code gửi null vào tham số được đánh dấu non-null, hoặc cảnh báo về các thao tác có nguy cơ.

Nhưng cần nhớ:

- Không phải annotation mang tên **@NonNull** nào cũng được mọi checker hiểu như nhau.
- Một checker phải được **cài đặt/cấu hình** cho build hoặc IDE và sử dụng đúng hệ annotation mà nó hỗ trợ.
- **Javac chuẩn** vẫn kiểm tra các quy tắc Java của annotation, nhưng không tự động hiểu toàn bộ ngữ nghĩa của annotation nghiệp vụ tùy chỉnh.
- Một hệ thống static checker có thể phát hiện lỗi **trước khi chạy**, nhưng nó không tự bảo đảm dữ liệu runtime đến từ bên ngoài tuân thủ hợp đồng nếu đường dữ liệu không được kiểm soát.
- Một annotation processor hoặc compiler plugin cũng không nhất thiết thêm bytecode kiểm tra vào method. Chức năng phụ thuộc công cụ, không phụ thuộc riêng tên annotation.

**Ví dụ giả định:** nếu dự án được cấu hình với một nullness checker hỗ trợ annotation bạn dùng, biểu thức truyền null có thể bị báo lỗi compile-time hoặc warning. Nhưng nếu chỉ viết annotation tùy chỉnh và chạy **javac** thông thường, không có lời hứa rằng phép truyền null bị từ chối.

**Không đánh đồng “IDE gạch đỏ” với “JVM sẽ ném lỗi”.** IDE kiểm tra source theo cấu hình, còn JVM thực thi bytecode và những phép kiểm tra runtime thực tế được chương trình hoặc môi trường hỗ trợ.

### Type annotation không nhất thiết xuất hiện ở runtime

Một annotation có **RetentionPolicy.CLASS** có thể có ích cho công cụ xử lý class file hay static analysis, nhưng **getAnnotation(...)** thông qua reflection thông thường không trả nó như RUNTIME annotation. Vì vậy:

- Muốn **static analysis**, chọn hệ annotation và quy trình build mà công cụ thực sự hỗ trợ.
- Muốn **đọc qua reflection runtime**, cần retention RUNTIME và đúng API.
- Muốn **cưỡng chế runtime**, cần thêm một **cơ chế kiểm tra** rõ ràng.

Ba mục tiêu đó có thể liên quan nhưng không phải cùng một hành động.

## 10. Bean Validation và framework: annotation chỉ hoạt động khi được kích hoạt

Trong hệ sinh thái Java hiện đại, có thể gặp những annotation validation như **@NotNull**, **@Size**, **@Min** từ một API validation phù hợp. Tuy nhiên:

- Các annotation đó **không phải cú pháp tự chạy của ngôn ngữ Java**.
- Chúng thuộc **thư viện/hệ validation** tương ứng, không tự nằm trong mọi chương trình Java thuần chỉ vì javac hỗ trợ @interface.
- Phải có **validation provider** và lời gọi validation hoặc một tích hợp framework thực sự kích hoạt validator, ví dụ ở biên request, bean hoặc method validation khi đã cấu hình.
- Phải kiểm tra **version và namespace** đúng với framework hiện đang dùng; các dự án hiện đại có thể dùng namespace **jakarta.validation**. Không chép máy móc import của một phiên bản khác.
- Nếu gọi một phương thức trực tiếp ngoài cơ chế interception/validation, đừng mặc nhiên cho rằng parameter constraints được kiểm tra.

Ví dụ về mặt ý tưởng (không phải chương trình Java độc lập):

~~~java
// Một mô hình dùng Jakarta Validation khi framework và provider
// đã được cấu hình; import, dependency và lệnh kích hoạt cần có.
class RegistrationInput {
    @jakarta.validation.constraints.NotNull
    String email;
}
~~~

Việc khai báo **@NotNull** trên field là metadata của một constraint. **Khi có validator được gọi hoặc framework kích hoạt**, provider mới đánh giá các constraint theo hợp đồng. Nếu bạn tự tạo đối tượng rồi gán email = null mà **không bao giờ kích hoạt validation**, Java không tự động chặn gán chỉ nhờ field có @NotNull.

**Lưu ý không nhầm:** annotation dùng cho **validation framework** với một annotation **TYPE_USE** tùy chỉnh có thể có target, retention và semantics khác nhau. Dùng đúng annotation do công cụ mục tiêu hỗ trợ; không suy đoán tất cả đều có cùng cách diễn giải.

## 11. Kiểm tra đầu vào tại biên hệ thống vẫn là trách nhiệm riêng

Ngay cả khi một dự án có static nullness checker, dữ liệu runtime vẫn có thể đến từ:

- Body HTTP/JSON của client.
- Database hoặc external API.
- Reflection, serialization, deserialization.
- Code bên thứ ba không tuân theo cùng hệ thống annotation.
- Dữ liệu cũ có chất lượng thấp hoặc bị sai.
- Bất kỳ đường vào nào không được static checker bao phủ đầy đủ.

Ví dụ một method khai báo tham số @NonNullLike String, nhưng HTTP request lại có field null. Static checker phân tích source có thể không chứng minh được giá trị của payload bên ngoài. Thêm một annotation vào DTO cũng chưa tự khởi chạy validator.

**Khuyến nghị thực tế:** xây validation ở **boundary** nơi giá trị không tin cậy đi vào ứng dụng. Sau khi kiểm tra, truyền dữ liệu qua các API domain có invariant rõ ràng, dùng constructor/factory để bảo vệ tính hợp lệ của đối tượng.

Chẳng hạn:

~~~java
static String normalizeEmail(String email) {
    java.util.Objects.requireNonNull(
        email, "email must not be null");

    String value = email.trim();
    if (value.isEmpty()) {
        throw new IllegalArgumentException(
            "email must not be blank");
    }
    return value;
}
~~~

Đoạn này là phương thức minh họa, không nhằm kiểm tra email đầy đủ theo tiêu chuẩn địa chỉ thư điện tử. Nó chứng minh việc **kiểm tra null và chuỗi rỗng** được viết bằng code thực tế, độc lập với annotation.

Đừng xây chính sách bảo mật/validation chỉ dựa vào một annotation mà không kiểm tra xem môi trường runtime có thật sự thực thi nó hay không.

## 12. Type annotation trên generic không kiểm tra tự động từng phần tử

Ví dụ:

~~~java
java.util.List<@NonNullLike String> names;
~~~

Cú pháp này chú thích **kiểu phần tử generic**. Nó không làm cho mỗi lần gọi **names.add(null)** tự động kích hoạt một lệnh kiểm tra do JVM tạo ra. Java generics dùng **type erasure**, và annotation trên generic type argument không biến từng phần tử thành đối tượng có runtime tag non-null.

Ngay cả với retention RUNTIME, reflection chỉ cho phép bạn **xem annotation trên thành phần kiểu khai báo**. Muốn kiểm tra nội dung danh sách, một validator phải duyệt phần tử theo quy tắc nó hỗ trợ.

Ví dụ code thủ công:

~~~java
static void rejectNullElements(
        java.util.List<?> values) {
    for (int i = 0; i < values.size(); i++) {
        if (values.get(i) == null) {
            throw new IllegalArgumentException(
                "Null element at index " + i);
        }
    }
}
~~~

Đoạn này minh họa validation thực tế. Nó không đọc bất kỳ annotation nào: tác dụng đến từ vòng lặp và điều kiện if. Nếu muốn validation dựa trên **List<@NonNullLike T>**, validator cần vừa đọc metadata kiểu lồng nhau, vừa biết dữ liệu tương ứng ở runtime và chính sách xử lý.

### Nested generic và các loại kiểu phức tạp

Các trường hợp như:

~~~java
java.util.Map<String,
    java.util.List<@NonNullLike String>> registry;
~~~

đặt annotation sâu trong generic type. Reflection có thể biểu diễn các cấu trúc kiểu parameterized qua **AnnotatedParameterizedType**, nhưng validator đúng phải xử lý nhiều mức, wildcard, mảng, generic type variables, cycle và null container. Không thể giả định một lệnh **field.getAnnotation(...)** là đủ để hiểu mọi annotation bên trong kiểu.

**Type annotation là thông tin mô tả vị trí kiểu**, không phải một bộ máy duyệt object graph.

## 13. Annotation trên mảng: phân biệt array và element

Cú pháp annotation trên mảng có những vị trí dễ nhầm:

~~~java
@NonNullLike String[] values;
String @NonNullLike [] values2;
~~~

Hai đoạn là minh họa và cần khai báo annotation TYPE_USE hợp lệ. Chúng có thể gắn annotation lên **thành phần kiểu** hoặc **mức mảng** khác nhau, tùy vị trí cú pháp. Với type annotation, vị trí viết annotation trên mảng là có ý nghĩa; đừng mặc nhiên hiểu “không null” gắn cùng một đối tượng trong mọi cách viết.

Đây là một lý do API reflection có các đối tượng **AnnotatedArrayType** để xem component type và annotation trên các mức của kiểu mảng.

Dù chú thích ở mức nào, Java thuần **không tự phát sinh phép kiểm tra null** cho mảng hoặc phần tử mảng khi bạn khai báo annotation tùy chỉnh. Nếu muốn cả **mảng không null** lẫn **mọi phần tử không null**, hãy định nghĩa hợp đồng rõ và dùng static checker/runtime validator phù hợp.

## 14. Phân biệt annotation trên declaration và trên type use khi dùng reflection

Giả sử một field có annotation trên **khai báo field** và annotation trên **kiểu của field**. Hai nơi đó khác nhau về ý nghĩa:

- **Field.getAnnotations()**: lấy annotation của phần tử khai báo (field declaration), theo quy tắc reflection và retention tương ứng.
- **Field.getAnnotatedType()**: lấy AnnotatedType của **kiểu field**.
- **Method.getAnnotatedReturnType()**: lấy annotation của **kiểu trả về**.
- **Method.getAnnotatedParameterTypes()**: lấy các AnnotatedType của **kiểu tham số**.
- **Executable.getAnnotatedExceptionTypes()**: truy cập các kiểu ngoại lệ được chú thích ở phần throws, khi phù hợp.
- **AnnotatedParameterizedType.getAnnotatedActualTypeArguments()**: truy cập type arguments có annotation trong kiểu generic.
- **AnnotatedArrayType.getAnnotatedGenericComponentType()**: truy cập kiểu thành phần mảng có annotation.

Để tránh nhầm, hãy hỏi:

1. Annotation của **cái gì**? Phương thức, field, tham số khai báo, hay kiểu được dùng?
2. Annotation có **retention** nào?
3. API reflection bạn gọi có đọc đúng **vị trí metadata** không?
4. Sau khi đọc được annotation, chương trình có thực sự gọi một **validator** không?

Câu trả lời cho (4) vẫn là **không**, trừ khi bạn đã viết hoặc cấu hình cơ chế đó.

### Annotation không phải runtime subtype

Nếu **@Safe String** là một type use, biểu thức kiểu @Safe String không trở thành một class riêng có thể phân biệt bằng **instanceof @Safe String** theo ý nghĩa dữ liệu non-null. Không có “runtime class SafeString” được sinh ra bởi một annotation tùy chỉnh. Type annotation cũng không làm **String.class** trở thành một Class khác.

## 15. Những gì javac vẫn có thể báo lỗi dù annotation không tự validation

Không nên nói rằng Java **bỏ qua hoàn toàn annotation**. Trình biên dịch vẫn kiểm tra **các quy tắc ngôn ngữ** dành cho annotation:

- Annotation có được phép đặt tại vị trí đó theo **@Target** không?
- Giá trị cho annotation element có đúng kiểu được cho phép không?
- Một element bắt buộc có được cung cấp hay có giá trị mặc định không?
- Có sử dụng annotation lặp lại đúng cách theo **@Repeatable** nếu áp dụng không?
- Các quy tắc về khai báo annotation và các loại target có được tuân thủ không?

Ví dụ, nếu annotation chỉ khai báo **@Target(ElementType.METHOD)**, thì gắn nó lên một type argument trong List<...> là lỗi về **vị trí annotation**.

Nhưng javac chuẩn không tự hiểu rằng tên **@PositiveValue** có nghĩa số phải lớn hơn 0. Một annotation có thể định nghĩa:

~~~java
@Target(ElementType.TYPE_USE)
@interface PositiveValue {
}
~~~

Đây là đoạn khai báo minh họa. Nếu không có công cụ hoặc code xử lý, Java không tự chèn điều kiện **number > 0**. Có sự khác biệt giữa **kiểm tra hợp lệ của annotation** và **kiểm tra điều kiện nghiệp vụ do annotation diễn đạt**.

## 16. Runtime annotation không đồng nghĩa runtime contract

Hãy tưởng tượng API công khai:

~~~java
static @NonNullLike String findUser(
        @NonNullLike String id) {
    return null;
}
~~~

Đây là **phương thức minh họa**. Dù annotation tên NonNullLike xuất hiện ở cả đầu vào và đầu ra, Java thuần vẫn cho phép thân trả null nếu không có checker hoặc ràng buộc khác buộc phát hiện.

Nếu phần mềm giả định **findUser(...) chắc chắn trả String không-null**, có thể dẫn đến NullPointerException ở một nơi xa nguyên nhân ban đầu. Giải pháp bền vững là:

- Tại nơi implement, bảo đảm invariant bằng code hoặc static checker được cấu hình.
- Tại boundary, kiểm tra dữ liệu không đáng tin.
- Nếu không có user là kết quả bình thường, dùng **Optional<String>** hoặc một kiểu kết quả biểu diễn sự vắng mặt hợp lý.
- Không dùng annotation để che giấu một giá trị return vốn có thể null.

**Một API chỉ an toàn bằng những bảo đảm thực sự có hiệu lực.** Annotation giúp truyền đạt hợp đồng và tích hợp công cụ, nhưng không thay thế cơ chế thực thi hợp đồng.

## 17. Thiết kế một hệ thống dựa vào type annotation đúng trách nhiệm

Một thiết kế tốt có thể chia việc thành các tầng:

| Tầng | Vai trò | Công cụ/cách tiếp cận |
| --- | --- | --- |
| **Khai báo hợp đồng** | Mô tả kỳ vọng của kiểu/phương thức | Type annotation nhất quán, JavaDoc, kiểu trả về phù hợp |
| **Phân tích source** | Phát hiện một số sai phạm trước khi chạy | IDE/static analyzer/compiler plugin được cấu hình |
| **Kiểm tra boundary** | Xác nhận dữ liệu thực tế đến từ bên ngoài | Validation framework hoặc code rõ ràng |
| **Kiểm tra invariant** | Không cho đối tượng rơi vào trạng thái sai | Constructor/factory và method guard |
| **Quan sát lỗi** | Thông báo lỗi, log, metric, test | Exception và báo cáo có ngữ cảnh |

Đừng để cùng một quy tắc được kiểm tra ngẫu nhiên ở vài đường code nhưng bỏ sót những đường khác. Ví dụ nếu **@Required** trên tham số chỉ được kiểm tra khi gọi qua một proxy/framework, lời gọi trực tiếp hoặc việc tạo đối tượng thủ công có thể không đi qua cơ chế đó.

Hãy viết test cho **đường gọi thật** của ứng dụng, không chỉ một test chứng minh reflection đọc thấy annotation.

### Kiểm tra không-null trong constructor

Đối với một đối tượng phải luôn có tên:

~~~java
final class User {
    private final String name;

    User(String name) {
        this.name = java.util.Objects.requireNonNull(
            name, "name must not be null");
    }

    String getName() {
        return name;
    }
}
~~~

Đây là đoạn class minh họa. Invariant được bảo vệ ở constructor; nó không lệ thuộc vào lời gọi qua framework hay việc người tạo đối tượng có nhớ kích hoạt validator hay không.

Nếu đặt thêm một annotation TYPE_USE nhằm phục vụ static checker, annotation đó có thể tăng độ rõ của hợp đồng, nhưng **requireNonNull** vẫn là code trực tiếp thực thi việc chặn null ở runtime.

## 18. Sai lầm phổ biến và cách sửa

| Nhận định hoặc thao tác sai | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Đã ghi @NonNull nên null tự bị cấm” | Java thuần không hiểu tự động annotation tùy chỉnh | Dùng checker/validator được cấu hình hoặc code kiểm tra |
| “@Retention(RUNTIME) nghĩa là được validate runtime” | Retention chỉ quy định giữ metadata | Viết/kích hoạt validator riêng |
| “Reflection sẽ tự thực thi constraint” | Reflection chỉ truy xuất metadata | Phải xử lý annotation và dữ liệu bằng code |
| “@Target(TYPE_USE) sẽ kiểm tra mọi phần tử List” | TYPE_USE là vị trí gắn chú thích, không phải loop kiểm tra | Validator phải duyệt phần tử nếu cần |
| “@Target(PARAMETER) và TYPE_USE luôn đọc giống nhau” | Khai báo tham số và kiểu tham số là vị trí khác nhau | Chọn đúng API reflection |
| “CLASS retention vẫn luôn đọc được bằng getAnnotation ở runtime” | Reflection thường cần RUNTIME retention | Chọn RUNTIME khi cần truy cập reflection |
| “Annotation ở generic tạo runtime class mới” | Generics/type annotation không sinh subtype riêng như vậy | Hiểu type erasure và metadata |
| “Có validation dependency thì mọi method call sẽ validate” | Framework phải có đường kích hoạt thực tế | Xác minh provider, interception, configuration |
| “Tất cả annotation @NotNull đều giống nhau” | Khác package, target, retention, checker và semantics | Theo tài liệu công cụ đang dùng |
| “Checker compile-time thay thế validation input” | Dữ liệu ngoài có thể không được checker chứng minh | Vẫn kiểm tra ở boundary |
| “Không cần test null vì field đã annotated” | Annotation không tự ngăn giá trị sai | Test constructor, method và đường vào dữ liệu |
| “Gắn annotation lên mảng ở đâu cũng như nhau” | Vị trí có thể chú thích cấp mảng hoặc phần tử | Đọc đúng cú pháp và AnnotatedArrayType |
| “Có annotation là JVM sẽ ném exception đẹp” | Không có exception mặc định cho ràng buộc tùy chỉnh | Chọn chính sách lỗi cụ thể và nhất quán |
| “Chỉ cần đặt tên annotation là Positive/Valid” | Tên không tạo logic tự động | Dùng công cụ hiểu annotation hoặc kiểm tra thủ công |

## 19. Quy trình kiểm tra khi thấy một type annotation lạ

Khi đọc dự án có các annotation như **@NonNull**, **@Nullable**, **@ReadOnly** hay một tên nội bộ, hãy điều tra theo thứ tự:

1. **Xem import và định nghĩa annotation.** Nó đến từ thư viện nào, package nào, có @Target gì?
2. **Xem retention.** SOURCE, CLASS hay RUNTIME? Ai có thể đọc?
3. **Tìm nơi tiêu thụ annotation.** Static checker, processor, IDE plugin, reflection validator hay framework nào?
4. **Xem cấu hình build/runtime.** Dependency có đủ chưa, plugin có thực chạy không, validator có được kích hoạt không?
5. **Phân biệt đường gọi.** Gọi trực tiếp khác gì gọi qua proxy/framework/validation endpoint?
6. **Xem hành vi khi vi phạm.** Warning, compilation failure, exception, validation result hay không có gì?
7. **Viết test nhỏ cho ràng buộc quan trọng.** Truyền null, danh sách chứa null, dữ liệu thiếu field hoặc giá trị sai rồi quan sát đúng đường vào.
8. **Không kết luận từ mỗi cái tên annotation.** Chỉ tin vào hợp đồng có tài liệu, cấu hình và bằng chứng thực thi.

Những câu hỏi này giúp tránh cả hai cực đoan: **tin annotation tự có phép màu**, hoặc **cho rằng annotation vô dụng**. Annotation có giá trị thực khi đúng công cụ biết cách tiêu thụ nó.

## 20. Bài tập thực hành

### Bài 1: Annotation cấm null chưa?

Có:

~~~java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface Required {
}

static String echo(@Required String text) {
    return text;
}
~~~

Đây là hai khai báo minh họa. Nếu gọi **echo(null)** mà không có checker/validator, có tự ném lỗi không?

**Đáp án:** không. Annotation chỉ là metadata. echo trả lại null. Nếu muốn chặn null runtime, gọi **Objects.requireNonNull(text, "...")** hoặc dùng một cơ chế validation được kích hoạt.

### Bài 2: RUNTIME retention nghĩa là gì?

Nếu annotation khai báo **@Retention(RetentionPolicy.RUNTIME)**, điều gì được bảo đảm?

**Đáp án:** metadata annotation có thể được giữ để truy xuất qua reflection theo quy tắc và vị trí hỗ trợ. Không bảo đảm annotation có logic kiểm tra dữ liệu hoặc được một framework tự thực thi.

### Bài 3: Đọc annotation ở kiểu phần tử generic

Nếu field khai báo **List<@Label String>**, tại sao chỉ gọi **field.getAnnotations()** có thể không thấy annotation đó?

**Đáp án:** annotation gắn lên **kiểu argument String**, không phải bản thân khai báo field. Có thể cần **field.getAnnotatedType()**, cast sang **AnnotatedParameterizedType**, rồi xem type arguments.

### Bài 4: Biến mất khi chạy

Một annotation có retention **CLASS**. Người viết muốn dùng **Field.getAnnotatedType()...getAnnotation(...)** để đọc nó ở runtime thông thường. Có vấn đề gì?

**Đáp án:** CLASS retention không bảo đảm khả năng đọc qua reflection runtime tiêu chuẩn. Nếu runtime reflection là mục tiêu, cần retention RUNTIME. Dù đọc được, vẫn phải tự viết/kích hoạt validator.

### Bài 5: List chứa null

Một List<@Required String> chứa các phần tử ["A", null]. Việc ghi @Required lên type argument tự biến **list.add(null)** thành IllegalArgumentException không?

**Đáp án:** không. Phải có checker/validator được cấu hình hoặc một code path kiểm tra phần tử.

### Bài 6: Phân biệt static và runtime

Một IDE gạch đỏ khi bạn gán null cho tham số annotated. Có thể kết luận JVM cũng chặn null khi nhận dữ liệu JSON từ client không?

**Đáp án:** không. IDE hoặc static checker có thể dựa trên phân tích source, còn JSON là dữ liệu runtime. Cần kiểm tra tại boundary hoặc một đường validation được kích hoạt.

### Bài 7: Kiểm tra invariant

Một class User không bao giờ được có name null. Chỉ viết **@Required String name;** hay dùng constructor có **Objects.requireNonNull(name)** đáng tin hơn cho enforcement runtime?

**Đáp án:** constructor kiểm tra null trực tiếp. Annotation có thể bổ trợ cho tài liệu/static analysis, nhưng không thay thế guard của constructor nếu yêu cầu không-null là invariant cần bảo vệ khi chạy.

### Bài 8: Framework validation

Bạn thêm một dependency chứa @NotNull và đánh dấu field; sau đó tự tạo object, gán null nhưng không gọi validator. Java có luôn ném lỗi không?

**Đáp án:** không. Cần provider và một bước validation hoặc tích hợp framework được cấu hình để kiểm tra đường dữ liệu đó. Tên annotation và dependency riêng lẻ không tự tạo execution path.

### Bài 9: Annotation trên kiểu trả về

Một phương thức trả **@Required String** nhưng trong thân viết **return null;**. Nếu không có checker hay validation, javac chuẩn có mặc định cấm không?

**Đáp án:** không theo ý nghĩa Required tùy chỉnh. Javac vẫn kiểm tra target/cú pháp annotation hợp lệ; việc hiểu “Required = không được null” cần công cụ hoặc code riêng.

### Bài 10: Xác định cơ chế thực thi

Một nhóm muốn dùng annotation để bảo đảm toàn bộ API không nhận null. Họ nên làm những bước nào?

**Đáp án:** chọn annotation và semantics thống nhất; xác định static checker hay runtime validator; cấu hình nó thật trong build/runtime; bảo vệ các boundary; thêm test các đường gọi thực; và tài liệu hóa hành vi lỗi. Chỉ thêm annotation lên chữ ký không đủ.

## Tổng kết

**Type annotation là metadata gắn lên vị trí sử dụng kiểu dữ liệu.** Java 8 mở rộng khả năng viết annotation lên generic type arguments, array components, return types và nhiều vị trí khác. **@Target** cho biết được phép đặt ở đâu; **@Retention** cho biết annotation được giữ đến giai đoạn nào; **reflection** cho phép đọc metadata phù hợp ở runtime.

Nhưng **annotation không tự tạo kiểm tra runtime**. Không có bước cưỡng chế nào được JVM tạo ra chỉ vì một annotation tùy chỉnh có tên Required, NonNull hoặc Positive. Enforcement đến từ **mã kiểm tra được viết rõ**, **framework được kích hoạt** hoặc **static checker được cấu hình**, với phạm vi và giới hạn tương ứng.

Khi gặp một annotation, luôn hỏi: **“Nó được gắn ở đâu, được lưu đến lúc nào, ai đọc nó, và chính xác ai thực thi quy tắc?”** Trả lời đủ bốn câu đó giúp sử dụng type annotation an toàn, tránh kỳ vọng sai và xây dựng ứng dụng Java hiện đại có hợp đồng dữ liệu thực sự được bảo vệ.