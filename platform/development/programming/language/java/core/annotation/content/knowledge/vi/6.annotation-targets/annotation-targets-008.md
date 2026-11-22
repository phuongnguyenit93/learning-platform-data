# TYPE_PARAMETER và TYPE_USE trong Java Annotation

Khi viết **@Target** cho một annotation tự định nghĩa, **ElementType.TYPE_PARAMETER** và **ElementType.TYPE_USE** cho phép đặt annotation vào các vị trí liên quan đến kiểu, nhưng hai hằng này không có cùng ý nghĩa.

- **TYPE_PARAMETER**: dùng cho **khai báo tham số kiểu (type parameter declaration)** của generic class, interface, method hoặc constructor, ví dụ chữ **T** được khai báo trong **class Box<T>**.
- **TYPE_USE**: dùng cho **vị trí sử dụng một kiểu (type-use context)**, ví dụ **String** trong **List<String>**, kiểu trả về của phương thức hoặc kiểu thành phần trong mảng. Theo đặc tả Java, TYPE_USE còn bao gồm cả khai báo kiểu và khai báo tham số kiểu để hỗ trợ công cụ kiểm tra kiểu.

Điểm dễ nhầm nhất: **khai báo T** trong **class Box<T>** và **sử dụng T** ở **T value;** là hai vị trí khác nhau. Một annotation chỉ cho phép TYPE_PARAMETER không tự nhiên trở thành annotation hợp lệ cho mọi vị trí có chữ T. Ngược lại, TYPE_USE có phạm vi rộng hơn và **có thể xuất hiện tại khai báo tham số kiểu**.

## 1. Khai báo hai annotation với @Target khác nhau

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_PARAMETER)
@interface ParameterTag {
    String value();
}

@Target(ElementType.TYPE_USE)
@interface TypeTag {
    String value();
}
~~~

Ký hiệu **@Target** là meta-annotation của Java, thuộc package **java.lang.annotation**. Nó quy định vị trí cú pháp mà một annotation type có thể được sử dụng. **TYPE_PARAMETER** và **TYPE_USE** là hai hằng enum của **ElementType**, xuất hiện từ Java 8.

Cách dùng:

~~~java
class Box<@ParameterTag("item") T> {
    @TypeTag("stored-value") T value;
}
~~~

- **@ParameterTag("item")** đặt ngay trước **T** trong danh sách khai báo tham số kiểu **<T>**. Đây là đích TYPE_PARAMETER.
- **@TypeTag("stored-value")** đặt trước **T** trong **T value;**. Đây là annotation trên **kiểu được sử dụng** để khai báo trường value, thuộc TYPE_USE.
- Hai annotation này không thay đổi quy tắc generic, giới hạn kiểu hoặc phép gán tại runtime chỉ nhờ sự hiện diện của ký hiệu @. Muốn thực thi một chính sách kiểm tra null, ta phải có annotation processor, type checker, framework hoặc mã ứng dụng diễn giải metadata.

## 2. TYPE_PARAMETER: chú thích chính khai báo tham số kiểu

TYPE_PARAMETER áp dụng cho khai báo một **type variable** của generic class/interface/method/constructor:

~~~java
@Target(ElementType.TYPE_PARAMETER)
@interface DocumentedVariable {
    String value();
}

class Cache<@DocumentedVariable("key") K,
            @DocumentedVariable("value") V> {
}

interface Mapper<@DocumentedVariable("input") I,
                 @DocumentedVariable("output") O> {
}

class Utility {
    <@DocumentedVariable("result") T> T keep(T input) {
        return input;
    }
}
~~~

Đối với **Cache**, K và V là hai tham số kiểu **được khai báo** trong dấu ngoặc nhọn. Đối với **Utility.keep**, T là tham số kiểu **được khai báo bởi method**, độc lập với tham số kiểu của class.

Generic constructor cũng có thể khai báo tham số kiểu riêng:

~~~java
class Container {
    <@DocumentedVariable("constructor") T> Container(T initial) {
        System.out.println(initial);
    }
}
~~~

Ở ví dụ này, **T** xuất hiện trong phần khai báo generic constructor là TYPE_PARAMETER. Chữ **T** trong **T initial** là **type use**; annotation DocumentedVariable chỉ được viết lên **khai báo T** vì @Target của nó không chứa TYPE_USE.

**Đối chiếu đúng/sai:**

~~~java
class Valid<@DocumentedVariable("declared") T> {
    T item;
}

// Sai: DocumentedVariable không có target TYPE_USE.
// class Invalid<T> {
//     @DocumentedVariable("type-used") T item;
// }

// Sai: String là một type argument được sử dụng, không phải
// khai báo type parameter mới.
// java.util.List<@DocumentedVariable("argument") String> names;
~~~

Ví dụ sai được để trong comment nên không cản trở chương trình biên dịch. Để chú thích kiểu của field hoặc generic argument, dùng annotation có target **TYPE_USE**.

Không đồng nhất TYPE_PARAMETER với **ElementType.PARAMETER**. PARAMETER là **tham số hình thức của method/constructor**, ví dụ **String input** trong **void send(String input)**. TYPE_PARAMETER là **tham số kiểu generic**, ví dụ **T** trong **<T> void send(T input)**.

## 3. TYPE_USE: chú thích vị trí sử dụng kiểu

TYPE_USE cho phép annotation xuất hiện tại các ngữ cảnh mà cú pháp Java dùng đến một kiểu. Các ví dụ tiêu biểu:

~~~java
import java.util.List;
import java.util.Map;

class TypeExamples {
    @TypeTag("field-type")
    String title;

    List<@TypeTag("list-element") String> names;

    Map<@TypeTag("map-key") String,
        @TypeTag("map-value") Integer> counts;

    @TypeTag("return-type")
    String normalize(@TypeTag("argument-type") String input) {
        @TypeTag("local-type") String result = input.trim();
        return result;
    }

    @TypeTag("element-type") String
            @TypeTag("array-dimension") [] items;
}
~~~

Cách đọc:

- **@TypeTag("field-type") String title**: chú thích kiểu **String** được dùng cho field title.
- **List<@TypeTag("list-element") String>**: chú thích chính **đối số kiểu String** trong kiểu tham số hóa **List<String>**.
- **Map<@TypeTag("map-key") String, @TypeTag("map-value") Integer>**: mỗi generic argument có metadata độc lập.
- **@TypeTag("return-type") String normalize(...)**: chú thích **kiểu trả về String**, khác với annotation trực tiếp lên khai báo method.
- **@TypeTag("argument-type") String input**: chú thích **kiểu String** của tham số input, khác với annotation đặt lên khai báo tham số bằng target PARAMETER.
- **@TypeTag("local-type") String result**: chú thích kiểu được dùng bởi biến cục bộ.
- **String @TypeTag("array-dimension") []**: chú thích **chiều mảng**, trong khi annotation trước String chú thích **kiểu thành phần String**. Vị trí dấu @ thay đổi thành phần của kiểu được gắn metadata.

TYPE_USE còn bao phủ các ngữ cảnh như kiểu giới hạn generic (**bounds**), kiểu được chỉ ra trong biểu thức **cast**, kiểu được sử dụng ở **implements/extends** và các vị trí khác theo JLS §4.11. Với mảng hoặc generic lồng nhau, cần đặt dấu @ đúng cạnh thành phần kiểu muốn biểu diễn.

Ví dụ chú thích một generic bound:

~~~java
class NumericBox<T extends @TypeTag("upper-bound") Number> {
}
~~~

Ở đây **Number** là một kiểu được sử dụng trong mệnh đề **extends** của T, không phải tên một tham số kiểu mới. Vì vậy TYPE_USE là đích phù hợp.

## 4. Điểm giao nhau: TYPE_USE cũng cho phép khai báo tham số kiểu

Mặc dù tên **TYPE_USE** gợi ý chỉ vị trí sử dụng, tài liệu Java về **ElementType.TYPE_USE** quy định thêm hai trường hợp khai báo được phép: **khai báo kiểu** và **khai báo tham số kiểu**.

Do đó đoạn sau là hợp lệ:

~~~java
@Target(ElementType.TYPE_USE)
@interface CheckedType {
}

class Holder<@CheckedType T> {
    @CheckedType T value;
}
~~~

**@CheckedType T** trong **Holder<...>** là annotation trên **khai báo tham số kiểu**, được cho phép nhờ TYPE_USE. **@CheckedType T value** là annotation trên **lần sử dụng T làm kiểu của field**. Dù cùng một cú pháp dấu @, nơi đặt metadata không giống nhau.

Bảng so sánh:

| Vị trí cú pháp | TYPE_PARAMETER | TYPE_USE |
| --- | --- | --- |
| **class Box<@A T>** — khai báo T | Có | Có |
| **<@A T> T identity(T x)** — khai báo T của method | Có | Có |
| **T value;** — sử dụng T làm kiểu field | Không | Có |
| **List<@A String>** — generic type argument | Không | Có |
| **T extends @A Number** — generic bound | Không | Có |
| **@A String method()** — kiểu trả về | Không | Có |
| **@A class Service {}** — khai báo kiểu class | Không | Có (ngoại lệ khai báo được TYPE_USE bao gồm) |

**Không kết luận TYPE_PARAMETER và TYPE_USE hoàn toàn tách rời về vị trí cú pháp**; chúng có vùng chồng lấp tại khai báo type parameter. Nhưng về mục đích thiết kế, TYPE_PARAMETER giúp mô tả riêng định nghĩa của type variable, còn TYPE_USE hướng đến thông tin trên các vị trí kiểu xuất hiện.

Nếu muốn một annotation rõ ràng dùng cho cả hai mục đích, có thể khai báo:

~~~java
@Target({ElementType.TYPE_PARAMETER, ElementType.TYPE_USE})
@interface TypeInfo {
    String value();
}
~~~

Về **phạm vi vị trí hợp lệ**, TYPE_USE tự nó đã bao gồm nơi TYPE_PARAMETER được phép xuất hiện. Việc liệt kê cả hai có thể hữu ích khi đọc ý đồ thiết kế hoặc phục vụ công cụ phân tích, nhưng không cần thiết chỉ để cho phép cú pháp trên khai báo type parameter.

## 5. TYPE_USE khác TYPE, FIELD, METHOD và PARAMETER

Đây là những hằng ElementType khác nhau:

| Target | Chú thích vào đâu? | Ví dụ |
| --- | --- | --- |
| **TYPE** | Khai báo class, interface, enum hoặc annotation type | **@ServiceMarker class Service {}** |
| **TYPE_PARAMETER** | Khai báo tham số kiểu generic | **class Box<@ParamTag T> {}** |
| **TYPE_USE** | Kiểu được dùng trong biểu thức/khai báo và hai ngữ cảnh khai báo bổ sung | **List<@NonNull String>** |
| **FIELD** | Khai báo một field | **@AuditField String name;** |
| **METHOD** | Khai báo một method | **@Audited String read() {...}** |
| **PARAMETER** | Khai báo tham số method/constructor | **void send(@Bind String value) {...}** |

Ví dụ cùng một dòng khai báo có thể đề cập đến cả **field declaration** và **type use**. Nếu annotation có target FIELD, nó mô tả khai báo field. Nếu chỉ có target TYPE_USE, annotation trước String được hiểu là annotation trên **kiểu String**. Việc phân biệt có ý nghĩa khi công cụ đọc metadata: API reflection dùng để tìm annotation của field và API đọc annotation trên kiểu của field là hai đường truy cập khác nhau.

~~~java
@Target(ElementType.FIELD)
@interface FieldNote {}

@Target(ElementType.TYPE_USE)
@interface TypeNote {}

class User {
    @FieldNote
    @TypeNote String name;
}
~~~

Để đọc metadata tương ứng:

~~~java
java.lang.reflect.Field field = User.class.getDeclaredField("name");

boolean declarationMarked =
        field.isAnnotationPresent(FieldNote.class);

boolean typeMarked =
        field.getAnnotatedType().isAnnotationPresent(TypeNote.class);
~~~

Hai boolean này đều true khi **@Retention(RUNTIME)** được khai báo trên cả FieldNote và TypeNote. Nếu bỏ @Retention, mặc định là CLASS, và ví dụ reflection trên không thể đảm bảo đọc được annotation lúc runtime. Đoạn trên là mã minh họa trong một context cho phép **NoSuchFieldException**, chưa phải chương trình chạy độc lập.

## 6. Ví dụ Java 17+ hoàn chỉnh và có đầu ra kiểm chứng

Ví dụ này sử dụng hai annotation: **ParameterLabel** chỉ có target TYPE_PARAMETER, và **TypeLabel** chỉ có target TYPE_USE. Cả hai dùng **@Retention(RUNTIME)** để quan sát metadata bằng reflection.

Tạo tệp **src/demo/AnnotationTargetsDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface ParameterLabel {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeLabel {
    String value();
}

class Repository<
        @ParameterLabel("entity") T
        extends @TypeLabel("bound") Number> {

    @TypeLabel("container")
    List<@TypeLabel("item") String> names = List.of("A");

    @TypeLabel("result")
    String echo(@TypeLabel("argument") String input) {
        return input;
    }

    <@ParameterLabel("method-variable") U> U identity(U input) {
        return input;
    }
}

public class AnnotationTargetsDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        TypeVariable<?> typeParameter =
                Repository.class.getTypeParameters()[0];

        System.out.println("type parameter="
                + typeParameter.getName() + ":"
                + typeParameter.getAnnotation(ParameterLabel.class).value());

        System.out.println("bound="
                + typeParameter.getAnnotatedBounds()[0]
                        .getAnnotation(TypeLabel.class).value());

        Field names = Repository.class.getDeclaredField("names");
        AnnotatedParameterizedType fieldType =
                (AnnotatedParameterizedType) names.getAnnotatedType();

        System.out.println("field type="
                + fieldType.getAnnotation(TypeLabel.class).value());

        System.out.println("type argument="
                + fieldType.getAnnotatedActualTypeArguments()[0]
                        .getAnnotation(TypeLabel.class).value());

        Method echo = Repository.class.getDeclaredMethod(
                "echo", String.class);

        System.out.println("return type="
                + echo.getAnnotatedReturnType()
                        .getAnnotation(TypeLabel.class).value());

        System.out.println("parameter type="
                + echo.getAnnotatedParameterTypes()[0]
                        .getAnnotation(TypeLabel.class).value());

        Method identity = Repository.class.getDeclaredMethod(
                "identity", Object.class);

        System.out.println("method type parameter="
                + identity.getTypeParameters()[0]
                        .getAnnotation(ParameterLabel.class).value());
    }
}
~~~

Từ thư mục chứa **src**, biên dịch và chạy:

~~~bash
javac -encoding UTF-8 -d out src/demo/AnnotationTargetsDemo.java
java -cp out demo.AnnotationTargetsDemo
~~~

**Stdout mong đợi:**

~~~text
type parameter=T:entity
bound=bound
field type=container
type argument=item
return type=result
parameter type=argument
method type parameter=method-variable
~~~

**Giải thích theo từng kết quả:**

1. **Repository.class.getTypeParameters()[0]** trả về **TypeVariable** cho T được khai báo trên Repository. **TypeVariable.getAnnotation(ParameterLabel.class)** đọc annotation ở vị trí khai báo tham số kiểu.
2. **typeParameter.getAnnotatedBounds()[0]** đại diện cho giới hạn **Number** đã được chú thích bằng TYPE_USE, nên trả nhãn "bound".
3. **Field.getAnnotatedType()** giữ metadata ở vị trí sử dụng kiểu field, tức **List**. Vì field chứa generic, có thể ép sang **AnnotatedParameterizedType**.
4. **getAnnotatedActualTypeArguments()[0]** đi sâu vào kiểu đối số **String** trong **List<String>**, để đọc nhãn "item". Đây là metadata khác với nhãn "container" trên List bên ngoài.
5. **Method.getAnnotatedReturnType()** đọc annotation trên kiểu trả về, còn **getAnnotatedParameterTypes()[0]** đọc annotation trên kiểu của tham số method.
6. **Method.getTypeParameters()[0]** đọc khai báo U của generic method. Vì U không có explicit bound, kiểu bị xóa của U là **Object**, do đó method reflection được tìm với tham số **Object.class**.

Ví dụ cố ý không dùng cách viết **field.getAnnotation(TypeLabel.class)** để đọc "container", vì đây là annotation trên **type use** của field, không phải metadata thuộc FIELD declaration.

## 7. Lưu trữ metadata và cách đọc đúng bằng reflection

**@Retention** là một quyết định độc lập với **@Target**:

- **SOURCE**: annotation chỉ được giữ trong mã nguồn, không còn trong class file để reflection đọc.
- **CLASS**: annotation được ghi vào class file nhưng không được cung cấp cho Java reflection runtime theo cách thông thường; đây là retention mặc định nếu không có @Retention.
- **RUNTIME**: metadata có thể được Java reflection đọc từ class đã nạp; ví dụ hoàn chỉnh dùng chế độ này.

Dù đều dùng reflection, metadata nằm ở những nơi khác nhau:

| Metadata muốn đọc | API phù hợp |
| --- | --- |
| Annotation trên **khai báo type parameter** T | **Class.getTypeParameters()**, **Method.getTypeParameters()** rồi **TypeVariable.getAnnotation(...)** |
| Annotation trên **generic bound** của T | **TypeVariable.getAnnotatedBounds()** |
| Annotation trên **kiểu field** | **Field.getAnnotatedType()** |
| Annotation trên **generic argument** của một field | **AnnotatedParameterizedType.getAnnotatedActualTypeArguments()** |
| Annotation trên **kiểu trả về** | **Method.getAnnotatedReturnType()** |
| Annotation trên **kiểu tham số method** | **Method.getAnnotatedParameterTypes()** |

Đừng nhầm **Field.getType()** hoặc **Method.getReturnType()** với các phương thức trả về **AnnotatedType**. Cách gọi cũ cung cấp thông tin kiểu cơ bản; cách gọi có tiền tố **getAnnotated...** giúp truy cập annotation trên **vị trí sử dụng kiểu**.

Cùng một class như **String** có thể được dùng ở nhiều vị trí có annotation khác nhau. Chúng không tự biến thành annotation trên chính khai báo **java.lang.String**. Do đó truy vấn annotation trên **String.class** không có nghĩa là đang đọc mọi annotation của các vị trí sử dụng String trong chương trình.

## 8. Những giới hạn và lưu ý khi áp dụng vào type checker

TYPE_USE thường gặp trong các công cụ phân tích tĩnh. Một thư viện có thể định nghĩa **@NonNull** hoặc **@ReadOnly** với target TYPE_USE để gắn vào nhiều vị trí kiểu, ví dụ phần tử trong List hoặc kiểu trả về. Nhưng Java compiler tiêu chuẩn chỉ kiểm tra tính hợp lệ của cú pháp, target và kiểu của các giá trị annotation; nó **không tự suy ra và thi hành** mọi ràng buộc domain của một annotation tùy chỉnh.

Ví dụ:

~~~java
@Target(ElementType.TYPE_USE)
@interface NonNull {}

class Example {
    @NonNull String name;
}
~~~

Điều này **không tự ngăn** phép gán **name = null** hoặc tự thêm NullPointerException có chủ đích. Cần công cụ tương ứng đọc annotation và áp dụng quy tắc kiểm tra, hoặc mã ứng dụng thực hiện logic kiểm tra runtime.

Ngoài ra:

- **TYPE_PARAMETER** và **TYPE_USE** không thay thế hệ thống generic. Annotation trên T không tạo bound mới, không sửa type erasure và không khiến Java lưu đủ generic type arguments của mọi đối tượng ở runtime.
- Khi annotation có cả TYPE_USE và một target declaration như FIELD/METHOD/PARAMETER, cách áp dụng và metadata có thể liên quan nhiều ngữ cảnh tùy vị trí đặt. Hãy thiết kế rõ mục đích và dùng API phù hợp để truy xuất.
- Annotation trên **TYPE_USE** có thể nằm sâu trong cấu trúc phức tạp: generic lồng nhau, wildcard bounds, array dimensions hoặc owner type. Khi đọc bằng reflection, cần duyệt **AnnotatedType** theo cấu trúc thay vì chỉ kiểm tra annotation ngoài cùng.
- Nếu bỏ **@Target** hoàn toàn, annotation tự định nghĩa mặc định áp dụng ở các ngữ cảnh **declaration** được Java quy định, nhưng không có quyền xuất hiện ở **type context** chỉ vì không khai báo target. Do đó phải chỉ định TYPE_USE nếu muốn chú thích type arguments hay kiểu trong cast.

## 9. Lỗi thường gặp và cách khắc phục

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng annotation chỉ có TYPE_PARAMETER trên **List<@A String>** | String là type argument sử dụng kiểu | Đổi target sang TYPE_USE |
| Gắn annotation chỉ có TYPE_PARAMETER trước **T field;** | Đây là lần dùng T làm kiểu field | Dùng annotation TYPE_USE |
| Cho rằng TYPE_USE không được đặt trên khai báo T | TYPE_USE còn bao gồm khai báo type parameter | Có thể viết **class Box<@A T>** khi A có TYPE_USE |
| Nhầm TYPE_PARAMETER với PARAMETER | Type variable khác tham số method/constructor | Xét chữ T trong **<T>**, so với **String name** |
| Dùng **@Target(TYPE)** rồi viết **List<@A String>** | TYPE áp dụng khai báo class/interface/enum/annotation type, không phải generic argument | Dùng TYPE_USE |
| Dùng **@Target(FIELD)** rồi muốn đọc bằng **getAnnotatedType()** | Annotation của FIELD declaration khác annotation của type use | Đặt target đúng và dùng **Field.getAnnotation(...)** cho FIELD |
| Dùng **Field.getType().getAnnotation(TypeTag.class)** | Truy vấn class của kiểu field, bỏ qua vị trí type use | Dùng **Field.getAnnotatedType().getAnnotation(...)** |
| Không dùng @Retention(RUNTIME) nhưng kỳ vọng reflection tìm thấy | Runtime metadata không được giữ với SOURCE/CLASS | Thêm **@Retention(RUNTIME)** nếu thật sự cần reflection |
| Mong **@NonNull** tự chặn null | Annotation tùy chỉnh không mặc nhiên tạo kiểm tra runtime | Tích hợp tool/type checker hoặc logic xử lý |
| Cho rằng mọi annotation nằm trước một method đều có target METHOD | Annotation ở vị trí kiểu trả về có thể thuộc TYPE_USE | Kiểm tra @Target và API đọc metadata |

## 10. Bài tập tự kiểm tra

**Bài 1.** Với **@Target(TYPE_PARAMETER)**, đoạn nào đúng?

~~~java
class Bag<@ParameterTag("decl") T> {}
// List<@ParameterTag("argument") String> a; // Sai
~~~

Dòng đầu đúng vì khai báo T; dòng sau sai vì String là một type argument. Hãy giải thích vì sao cùng xuất hiện trong dấu ngoặc nhọn nhưng có ý nghĩa khác nhau: một bên là **khai báo generic parameter**, bên kia là **truyền generic argument**.

**Bài 2.** Với **@Target(TYPE_USE)**, vị trí nào được phép?

~~~java
class Bag<@TypeTag("declaration") T> {
    java.util.List<@TypeTag("argument") T> elements;
}
~~~

Cả hai đều hợp lệ: TYPE_USE cho phép vị trí khai báo type parameter và vị trí sử dụng T làm type argument.

**Bài 3.** Đọc annotation **@TypeTag("x")** trên **List<@TypeTag("x") String>** bằng cách gọi **String.class.getAnnotation(TypeTag.class)** được không? **Không.** Annotation nằm trên một **vị trí sử dụng String**, không tự được gắn lên khai báo class String.

**Bài 4.** Nếu muốn kiểm tra annotation trên giới hạn của **T extends @TypeTag("bound") Number**, phải dùng API nào? Sử dụng **TypeVariable.getAnnotatedBounds()** rồi đọc annotation trên phần tử **AnnotatedType** của bound tương ứng.

**Bài 5.** Vì sao đoạn **@Target(TYPE_USE) @interface NonNull {}** không bảo đảm mọi biến được gắn @NonNull không thể chứa null? Vì annotation chỉ mang metadata; Java cần một công cụ bổ sung để hiểu và kiểm tra quy tắc non-null mà ta định nghĩa.

## 11. Tài liệu đối chiếu

- **Java SE 17 — ElementType**, mô tả TYPE_PARAMETER, TYPE_USE và việc TYPE_USE bao gồm khai báo tham số kiểu: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html
- **Java Language Specification §4.11 — Where Types Are Used**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.11
- **Java Language Specification §9.6.4.1 — @Target**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1
- **Java SE 17 — AnnotatedParameterizedType**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html

Khi gặp TYPE_PARAMETER và TYPE_USE, hãy xác định chính xác **chỗ đặt dấu @ có đang khai báo một type variable hay đang chú thích một vị trí sử dụng kiểu**, sau đó đối chiếu với @Target. Với annotation chỉ dành cho khai báo type variable, TYPE_PARAMETER là lựa chọn hẹp và rõ; với metadata về các vị trí sử dụng kiểu, TYPE_USE là lựa chọn rộng hơn và bao gồm luôn khai báo type parameter.
