# TYPE_USE và TYPE_PARAMETER trong Java Type Annotations

## Mục tiêu học tập

Từ Java 8, hệ thống annotation hỗ trợ **type annotations**: annotation không chỉ đặt trên khai báo lớp, phương thức hay biến, mà còn đặt trên **vị trí sử dụng một kiểu**. Hai hằng của enum `java.lang.annotation.ElementType` quan trọng nhất khi học phần này là **`TYPE_USE`** và **`TYPE_PARAMETER`**. Cả hai vẫn là thành phần chuẩn của Java hiện đại.

Sau bài này, bạn có thể:

- Phân biệt **khai báo tham số kiểu** (`type parameter declaration`) với **vị trí sử dụng kiểu** (`type use`).
- Viết chính xác `@Target(ElementType.TYPE_PARAMETER)` và `@Target(ElementType.TYPE_USE)`, hiểu khi nào cần kết hợp chúng.
- Annotate kiểu trong generic type argument, kiểu trả về, kiểu tham số phương thức, mảng, wildcard, bound, cast và những vị trí hợp lệ khác.
- Hiểu `@Retention` ảnh hưởng thế nào đến việc lưu annotation và đọc bằng reflection.
- Dùng `TypeVariable`, `AnnotatedType`, `AnnotatedParameterizedType`, `getAnnotatedBounds()` và các reflection API tương ứng.
- Nhận diện sự khác nhau giữa **metadata về kiểu** và **hợp đồng hành vi được công cụ thực sự kiểm tra**.
- Tránh những lỗi thường gặp về `@Target`, import, Java generics, nullability và nhầm declaration annotations với type-use annotations.

**Điểm cần nhớ:** Java compiler kiểm tra annotation có xuất hiện ở **vị trí mà `@Target` cho phép** hay không. Nhưng chỉ viết một annotation tên `@NonNull` hoặc `@Positive` **không mặc nhiên khiến javac kiểm tra mọi giá trị null/số âm**. Muốn thực thi quy tắc nghiệp vụ/kiểu nâng cao, cần công cụ hoặc mã phân tích thực sự hiểu annotation đó.

## 1. Ôn lại annotation và meta-annotation @Target

Một annotation trong Java là metadata gắn lên một phần của chương trình. Bạn khai báo annotation type bằng `@interface` và có thể kiểm soát nơi được phép dùng nó:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_PARAMETER)
@interface ParameterMarker {
}
~~~

`@Target` là **meta-annotation**: annotation áp dụng cho **chính loại annotation khác**. Giá trị của nó chỉ định vị trí cú pháp được phép xuất hiện `@ParameterMarker`.

`ElementType` có nhiều hằng như `TYPE`, `METHOD`, `FIELD`, `PARAMETER`, `LOCAL_VARIABLE`, `ANNOTATION_TYPE`, `CONSTRUCTOR`, `TYPE_USE`, `TYPE_PARAMETER`, ... Chúng không cùng nghĩa. Đặc biệt:

- `TYPE` nói về **khai báo** lớp/interface/enum/record hoặc dạng type declaration tương ứng.
- `PARAMETER` nói về **khai báo tham số giá trị** của phương thức/constructor, chẳng hạn `String name` trong `void send(String name)`.
- `TYPE_PARAMETER` nói về **khai báo tham số kiểu generic** như `<T>`, `<E>`, `<K,V>`.
- `TYPE_USE` nói về **vị trí sử dụng kiểu**, ví dụ phần tử `String` trong `List<String>` hoặc kiểu trả về `String` của một method.

Không nên suy luận rằng `ElementType.PARAMETER` và `ElementType.TYPE_PARAMETER` là hai tên cho cùng một vị trí. **Một tham số giá trị** và **một tham số kiểu generic** là hai khái niệm khác nhau.

## 2. TYPE_PARAMETER: đánh dấu *khai báo* tham số kiểu

Ví dụ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_PARAMETER)
@interface TypeParameterInfo {
    String value();
}

class Repository<@TypeParameterInfo("record-type") T> {
    private T current;

    T get() {
        return current;
    }
}
~~~

`@TypeParameterInfo` xuất hiện tại **khai báo `T`** trong `Repository<...>`. Nó **không** đánh dấu kiểu dữ liệu cụ thể truyền cho `T` sau này.

Khi tạo:

~~~java
Repository<String> names = new Repository<>();
Repository<Integer> ids = new Repository<>();
~~~

các type arguments `String` và `Integer` là **vị trí sử dụng kiểu**. Một annotation chỉ có target `TYPE_PARAMETER` không thể đặt tùy ý vào chúng.

Đoạn sau là **lỗi compile-time có chủ đích**:

~~~java
// Không hợp lệ vì @TypeParameterInfo chỉ target TYPE_PARAMETER:
// Repository<@TypeParameterInfo("string") String> bad;
~~~

### TYPE_PARAMETER cũng áp dụng cho generic method

~~~java
class Algorithms {
    static <@TypeParameterInfo("element") T> T identity(T value) {
        return value;
    }
}
~~~

`<T>` khai báo type parameter của chính phương thức `identity`, nên phù hợp `TYPE_PARAMETER`. Đây là **khai báo**, không phải type argument được gán cho `T` trong một lần gọi như `Algorithms.<String>identity("hi")`.

**Ý nghĩa thực tế:** metadata ở type parameter declaration có thể diễn đạt ý định hoặc ràng buộc quy ước về **tham số kiểu** của một API. Nó không biến một kiểu generic thành runtime-reified generic: `Repository<String>` và `Repository<Integer>` vẫn tuân theo **type erasure** của Java.

## 3. TYPE_USE: đánh dấu *vị trí sử dụng* kiểu

Ví dụ định nghĩa:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface UseInfo {
    String value();
}
~~~

`@UseInfo` có thể xuất hiện khi kiểu được **sử dụng** trong những ngữ cảnh được ngôn ngữ cho phép:

~~~java
java.util.List<@UseInfo("element") String> names;

@UseInfo("return") String getName() {
    return "Java";
}

void print(@UseInfo("parameter-type") String text) {
    System.out.println(text);
}
~~~

Các ví dụ trên **phải được đặt trong class hoặc interface thích hợp**, không phải tệp Java độc lập. Từ khóa `TYPE_USE` không nói rằng annotation “dành cho mọi khai báo biến”, mà nói nó đánh dấu **kiểu** được viết ở vị trí đó.

### Các vị trí TYPE_USE thường gặp

| Vị trí | Ví dụ | Annotation gắn vào |
| --- | --- | --- |
| Kiểu phần tử generic | `List<@UseInfo("element") String>` | Kiểu `String` làm type argument |
| Kiểu trả về | `@UseInfo("return") String read()` | Kiểu `String` của kết quả |
| Kiểu tham số giá trị | `void save(@UseInfo("value") String s)` | Kiểu `String` của `s` |
| Kiểu field | `@UseInfo("field-type") String name;` | Kiểu của field |
| Bound của type parameter | `<T extends @UseInfo("bound") Number>` | Kiểu `Number` làm bound |
| Kiểu trong cast | `(@UseInfo("cast") String) value` | Kiểu đích của phép cast |
| Kiểu trong `throws` | `throws @UseInfo("exception") IOException` | Kiểu exception được khai báo |
| Array dimension | `String @UseInfo("array") [] names` | Kiểu mảng tại chiều được đánh dấu |
| Wildcard/bound | `List<? extends @UseInfo("upper") Number>` | Kiểu bound của wildcard |
| Kiểu được tạo bởi `new` | `new @UseInfo("created") StringBuilder()` | Kiểu được sử dụng trong biểu thức tạo object |

Đây là **ví dụ cú pháp** trong bối cảnh Java phù hợp; riêng một vài dạng có thể yêu cầu phương thức/khối bao ngoài hợp lệ để hoàn chỉnh chương trình. Annotation không thay thế việc kiểm tra kiểu vốn có: `String` vẫn phải được dùng ở nơi chấp nhận `String`, và `IOException` vẫn phải tuân theo checked-exception rules.

### Vị trí đặt annotation trong mảng quan trọng

Xét:

~~~java
@UseInfo("component") String[] first;

String @UseInfo("array") [] second;
~~~

Hai annotation không biểu diễn cùng một vị trí cấu trúc:

- `@UseInfo("component") String[]` chú thích **kiểu phần tử `String`**.
- `String @UseInfo("array") []` chú thích **kiểu mảng ở dimension được đánh dấu**.

Với mảng nhiều chiều, vị trí annotation quanh từng `[]` quyết định cấp của kiểu mảng được đánh dấu. Nếu công cụ phân tích type-use annotations cần thông tin chính xác, phải quan sát **cấu trúc annotated type**, không chỉ đọc một chuỗi ký tự rồi bỏ qua vị trí `[]`.

## 4. TYPE_PARAMETER và TYPE_USE khác nhau như thế nào?

So sánh trực tiếp:

| Tiêu chí | `TYPE_PARAMETER` | `TYPE_USE` |
| --- | --- | --- |
| Mục tiêu chính | Khai báo type parameter (`T`) | Vị trí sử dụng kiểu |
| Ví dụ cơ bản | `class Box<@Mark T>` | `List<@Mark String>` |
| Generic method | `<@Mark T> T get()` | `@Mark String get()` hoặc kiểu đối số |
| Type argument `String` trong `Box<String>` | Không | Có |
| Bound `Number` của `T extends Number` | Không phải đích `TYPE_PARAMETER` riêng | Có |
| Reflection thường dùng | `TypeVariable.getAnnotation(...)` | `AnnotatedType` và các subtype |
| Tự kiểm tra nullability? | Không | Không |
| Trạng thái trong Java hiện nay | Vẫn được hỗ trợ | Vẫn được hỗ trợ |

Điểm tinh tế của JLS: **`TYPE_USE` cũng bao hàm các ngữ cảnh liên quan type parameter declaration**. Vì vậy một annotation target `TYPE_USE` có thể được dùng tại vị trí khai báo type parameter theo quy tắc tương ứng; `TYPE_PARAMETER` là cách biểu đạt **đích chuyên biệt** khi annotation chỉ nhằm vào việc khai báo type parameter.

Đừng suy ra rằng `TYPE_PARAMETER` tự động cho phép annotation được đặt ở `List<@Mark String>` — vị trí ấy cần `TYPE_USE`.

### Định nghĩa cho phép cả hai target

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({
    ElementType.TYPE_USE,
    ElementType.TYPE_PARAMETER
})
@interface TypeMark {
    String value() default "";
}
~~~

Dùng một tên annotation ở nhiều loại vị trí có thể thuận tiện khi một công cụ cùng hiểu cả **khai báo generic** lẫn **type uses**. Tuy nhiên, chỉ thêm hai giá trị trong `@Target` **không định nghĩa thêm thuật toán validate**. Việc semantics của annotation có giống nhau ở mọi vị trí hay không là trách nhiệm của đặc tả/công cụ sử dụng annotation ấy.

## 5. Ví dụ đối chiếu: type parameter và type argument trong cùng chương trình

Giả sử định nghĩa:

~~~java
@Target(ElementType.TYPE_PARAMETER)
@interface GenericTag {
}

@Target(ElementType.TYPE_USE)
@interface UseTag {
}
~~~

Khi đó:

~~~java
class Box<@GenericTag T> {
    java.util.List<@UseTag String> labels;
}
~~~

`@GenericTag` đánh dấu **`T` tại declaration** của `Box`. `@UseTag` đánh dấu **`String` tại actual type argument** của `List`. Trên cùng một kiểu generic, việc chọn target rất quan trọng:

~~~java
// Không hợp lệ: GenericTag không được target vào type argument.
// Box<@GenericTag String> wrong;
~~~

Một class có thể sử dụng cả hai dạng vì chúng phục vụ những nhu cầu metadata khác nhau. Kiểu thực sự của `labels` vẫn là `List<String>`; marker không khiến nó thành một loại collection mới mà Java generics tự hiểu.

## 6. @Retention: annotation có còn tại runtime không?

`@Target` nói **được đặt ở đâu**; `@Retention` nói **metadata được giữ đến giai đoạn nào**:

| Retention | Đặc điểm | Có thể đọc bằng reflection thông thường tại runtime? |
| --- | --- | --- |
| `RetentionPolicy.SOURCE` | Annotation chỉ cần ở source, không giữ trong class file | Không |
| `RetentionPolicy.CLASS` | Được ghi trong class file nhưng không bắt buộc khả dụng qua reflection runtime | Không, theo API reflection chuẩn |
| `RetentionPolicy.RUNTIME` | Metadata được giữ và cho phép truy cập qua reflection theo API tương ứng | Có, nếu truy vấn đúng vị trí |

Nếu bạn **không** khai báo `@Retention`, mặc định là **`RetentionPolicy.CLASS`**, **không** phải `RUNTIME` hoặc `SOURCE`.

Ví dụ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface RuntimeTypeTag {
    String value();
}
~~~

Lưu ý: `RUNTIME` chỉ cho phép metadata được **hiện diện và đọc qua API thích hợp**. Nó không tự làm một chương trình chạy validation, không có cơ chế bắt buộc một thư viện bất kỳ phải diễn giải ý nghĩa `RuntimeTypeTag`.

### Khi nào chọn retention nào?

- Chỉ phục vụ phân tích source hoặc một công cụ biên dịch, có thể chọn `SOURCE` nếu công cụ không cần class file.
- Một công cụ xử lý bytecode/class file có thể khai thác `CLASS` trong bối cảnh phù hợp.
- Nếu **trực tiếp đọc annotation qua Java reflection trong runtime**, cần `RUNTIME` và API phản chiếu thích hợp.

Không chọn `RUNTIME` theo thói quen: quyết định này thuộc hợp đồng giữa **bên định nghĩa annotation**, **công cụ tiêu thụ annotation** và nơi metadata phải tồn tại.

## 7. Reflection: đọc TYPE_PARAMETER khác với TYPE_USE

Java reflection có một số API khác nhau:

- `Class.getTypeParameters()`, `Method.getTypeParameters()` và `Constructor.getTypeParameters()` trả các **`TypeVariable<?>`** mô tả **khai báo** type parameters.
- `TypeVariable` triển khai `AnnotatedElement`, nên `getAnnotation(...)` / `getAnnotations()` có thể trả annotation **trực tiếp trên khai báo type parameter** khi retention cho phép.
- `TypeVariable.getAnnotatedBounds()` trả các **`AnnotatedType`** mô tả **kiểu bound** — đó là type-use position, không phải chính declaration `T`.
- `Field.getAnnotatedType()` đọc **kiểu khai báo của field**, gồm các annotation type-use khả dụng.
- `Method.getAnnotatedReturnType()` đọc **kiểu trả về có annotation**; `Method.getAnnotatedParameterTypes()` đọc kiểu của các tham số.
- Với generic type như `List<@Tag String>`, `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` đi sâu tới **annotation của type argument `String`**.
- Với mảng hoặc wildcard, có các subtype `AnnotatedArrayType` và `AnnotatedWildcardType` để lần theo cấu trúc lồng nhau.

Đừng nhầm:

~~~java
field.getAnnotation(RuntimeTypeTag.class);
~~~

với:

~~~java
field.getAnnotatedType().getAnnotation(RuntimeTypeTag.class);
~~~

Nếu `RuntimeTypeTag` có target **chỉ `TYPE_USE`**, metadata trên **kiểu của field** được truy vấn qua `getAnnotatedType()`, không phải mặc nhiên nằm trong **declaration annotations** của chính field.

Tương tự:

~~~java
method.getParameterAnnotations();
~~~

được dùng cho declaration annotations trên **tham số giá trị**; khi muốn xem annotation trên **kiểu của tham số**, dùng:

~~~java
method.getAnnotatedParameterTypes();
~~~

Hai nhóm thông tin không nên đánh đồng chỉ vì source code đặt annotation cạnh tên kiểu.

## 8. Chương trình Java 17+ chạy độc lập: TYPE_PARAMETER, TYPE_USE và reflection

Tạo tệp **`TypeUseAndParameterDemo.java`** với toàn bộ nội dung sau:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;
import java.util.List;

public class TypeUseAndParameterDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_PARAMETER)
    @interface ParameterMark {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface UseMark {
        String value();
    }

    static class Box<
            @ParameterMark("declaration") T
                    extends @UseMark("number-bound") Number> {

        List<@UseMark("string-element") String> labels =
                List.of("Java");

        @UseMark("return-value")
        String decorate(@UseMark("input-value") String input) {
            return "<" + input + ">";
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        TypeVariable<?> variable =
                Box.class.getTypeParameters()[0];

        System.out.println("type-parameter=" + variable.getName());

        ParameterMark declared =
                variable.getAnnotation(ParameterMark.class);
        System.out.println("parameter-annotation=" + declared.value());

        AnnotatedType bound = variable.getAnnotatedBounds()[0];
        UseMark boundMark = bound.getAnnotation(UseMark.class);
        System.out.println("bound-annotation=" + boundMark.value());

        Field labelsField = Box.class.getDeclaredField("labels");
        AnnotatedParameterizedType fieldType =
                (AnnotatedParameterizedType)
                        labelsField.getAnnotatedType();

        AnnotatedType elementType =
                fieldType.getAnnotatedActualTypeArguments()[0];

        UseMark elementMark =
                elementType.getAnnotation(UseMark.class);
        System.out.println("element-annotation=" + elementMark.value());

        Method method =
                Box.class.getDeclaredMethod("decorate", String.class);

        UseMark resultMark =
                method.getAnnotatedReturnType()
                        .getAnnotation(UseMark.class);

        UseMark inputMark =
                method.getAnnotatedParameterTypes()[0]
                        .getAnnotation(UseMark.class);

        System.out.println("return-annotation=" + resultMark.value());
        System.out.println("input-annotation=" + inputMark.value());

        Box<Integer> box = new Box<>();
        System.out.println("result=" + box.decorate("Java"));
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac --release 17 TypeUseAndParameterDemo.java
java TypeUseAndParameterDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
type-parameter=T
parameter-annotation=declaration
bound-annotation=number-bound
element-annotation=string-element
return-annotation=return-value
input-annotation=input-value
result=<Java>
~~~

### Vì sao từng dòng xuất hiện?

1. `Box` khai báo type variable có tên `T`; `variable.getName()` trả `"T"`.
2. `@ParameterMark("declaration")` được đặt trên **khai báo `T`**, nên `TypeVariable.getAnnotation(ParameterMark.class)` trả annotation đó.
3. `@UseMark("number-bound")` được đặt trên **kiểu `Number` ở bound**, nên `getAnnotatedBounds()[0]` tìm đúng type-use annotation.
4. `List<@UseMark("string-element") String>` chứa annotation ở **type argument**. Cần đi từ `Field.getAnnotatedType()` qua `AnnotatedParameterizedType` và lấy annotated argument đầu tiên.
5. `@UseMark("return-value") String` là **kiểu trả về có annotation**; `getAnnotatedReturnType()` cung cấp dữ liệu đó.
6. `@UseMark("input-value") String` là **kiểu tham số có annotation**; `getAnnotatedParameterTypes()[0]` lấy đúng vị trí.
7. `box.decorate("Java")` vẫn thực thi như phương thức Java bình thường; kết quả `"<Java>"` do **code trong method**, không phải do marker annotation tự thay đổi dữ liệu.

**Vì sao cần `RUNTIME`?** Nếu hai annotation chỉ có mặc định `CLASS`, những lời gọi `getAnnotation(...)` trong chương trình này không thu được các marker qua reflection runtime thông thường, dẫn đến `null` và có thể gây `NullPointerException` khi gọi `value()`.

**Vì sao cần `List.of`?** Đây chỉ là cách tạo một danh sách ví dụ; `List.of` có từ Java 9. Nếu biên dịch ở mức Java 8, thay bằng collection factory tương thích. Bản thân `TYPE_USE` và `TYPE_PARAMETER` là tính năng từ Java 8 nhưng không bắt buộc chạy trên runtime Java 8 cũ.

## 9. Cùng một annotation cho cả TYPE_USE và TYPE_PARAMETER

Nếu muốn một annotation dùng ở cả type parameter declaration lẫn type use, có thể khai báo rõ hai target:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({
        ElementType.TYPE_USE,
        ElementType.TYPE_PARAMETER
})
@interface Label {
    String value();
}
~~~

Sau đó một generic class có thể dùng:

~~~java
class Container<@Label("formal-T") T> {
    java.util.List<@Label("actual-String") String> labels;
}
~~~

- `"formal-T"` đánh dấu **khai báo `T`**.
- `"actual-String"` đánh dấu **kiểu `String` được dùng làm type argument**.

Đây là **mã minh họa** cần các import và phạm vi class hợp lệ. Tùy mục tiêu tool, có thể tốt hơn nếu định nghĩa **hai annotation khác nhau** để không lẫn hai ý nghĩa. Việc kết hợp target có lợi khi cả hai vị trí thực sự có cùng một hợp đồng metadata.

## 10. TYPE_USE trong generic và wildcard

Type annotation thường có ý nghĩa nhất khi gắn vào **một phần nhỏ bên trong generic type**, không chỉ gắn lên tên collection bên ngoài.

Ví dụ:

~~~java
java.util.Map<
        @UseInfo("key") String,
        java.util.List<@UseInfo("value") Integer>
> index;
~~~

Ở đây:

- `@UseInfo("key")` đánh dấu **kiểu khóa `String`**.
- `@UseInfo("value")` đánh dấu **kiểu phần tử `Integer`** của danh sách nằm trong value.
- Annotation không tự giới hạn key phải là chuỗi không rỗng hay value phải dương — đó cần là quy tắc được tool/hợp đồng xác định.

Với wildcard:

~~~java
java.util.List<? extends @UseInfo("bound") Number> source;
~~~

`@UseInfo("bound")` đặt trên **upper-bound type `Number`**. Reflection có thể dùng `AnnotatedWildcardType.getAnnotatedUpperBounds()` khi cần truy vấn cấu trúc wildcard/bound.

### Type argument khác type parameter

~~~java
class Holder<T> {
}

// Khai báo T là type parameter.
// Trong Holder<@UseInfo String>, String là type argument.
Holder<@UseInfo("argument") String> holder;
~~~

Nếu annotation chỉ target `TYPE_PARAMETER`, không được mang nó sang vị trí `String`; nếu muốn đánh dấu type argument, cần `TYPE_USE`.

## 11. TYPE_USE trên kiểu mảng: vị trí đặt ký hiệu quyết định cấu trúc

Ví dụ trong class:

~~~java
@UseInfo("component") String[] names;

String @UseInfo("array") [] otherNames;

String @UseInfo("outer-array") []
       @UseInfo("inner-array") [] matrix;
~~~

Giải thích:

- `names` đánh dấu **component type `String`**.
- `otherNames` đánh dấu **array type**.
- `matrix` có hai chiều, mỗi dimension có thể mang metadata riêng.

Khi đọc bằng reflection, `AnnotatedArrayType` cung cấp `getAnnotatedGenericComponentType()` để đi vào component type. Với mảng đa chiều, việc đặt annotation ở từng cấp có thể mang ý nghĩa nghiệp vụ khác nhau, ví dụ ràng buộc về từng hàng hoặc từng phần tử; compiler không tự hiểu những ý nghĩa ấy.

## 12. TYPE_USE trên cast và extends/implements

Type-use annotations cũng xuất hiện tại những vị trí ngoài khai báo field:

~~~java
Object raw = "Java";

String text = (@UseInfo("cast-type") String) raw;
~~~

Annotation đánh dấu **kiểu đích của cast**. Compiler vẫn kiểm tra cast có hợp lệ theo quy tắc Java; annotation không biến một cast không hợp lệ thành hợp lệ.

Trong khai báo kế thừa:

~~~java
interface Named {
    String name();
}

class Person implements @UseInfo("contract") Named {
    public String name() {
        return "Lan";
    }
}
~~~

`@UseInfo("contract")` đánh dấu **kiểu interface `Named` được dùng trong `implements`**, không phải một declaration annotation trên chính class `Person`. Java có API `Class.getAnnotatedInterfaces()` để truy vấn các type uses trong danh sách superinterfaces khi retention là `RUNTIME`.

**Không nhầm:** `@Target(ElementType.TYPE)` áp dụng cho khai báo class/interface; muốn annotate một **kiểu ở `extends`/`implements`**, cần `TYPE_USE`.

## 13. TYPE_PARAMETER không phải kiểu tham số phương thức bình thường

Xem hai khai báo khác nhau:

~~~java
@Target(ElementType.PARAMETER)
@interface ValueParameterTag {
}

@Target(ElementType.TYPE_PARAMETER)
@interface GenericParameterTag {
}
~~~

Sử dụng:

~~~java
class Examples {
    static <@GenericParameterTag T> void consume(
            @ValueParameterTag T value) {
    }
}
~~~

- `@GenericParameterTag` đứng tại **declaration của type parameter `T`**.
- `@ValueParameterTag` đứng tại **declaration của formal value parameter `value`**.

Nếu muốn chú thích **kiểu** `T` của `value` chứ không phải declaration của tham số, dùng annotation target `TYPE_USE` tại vị trí kiểu tương ứng.

Điểm này thường gây nhầm khi các framework xử lý annotation trên parameter declarations và các tool phân tích type system xử lý annotation **trên loại dữ liệu của tham số**. Hai dữ liệu có thể được lưu/đọc qua các API reflection khác nhau.

## 14. Java có tự kiểm tra @NonNull hoặc @Positive không?

Giả sử bạn tự viết:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface NonNull {
}
~~~

Sau đó:

~~~java
@NonNull String value = null;
~~~

**Trong Java SE, việc bạn tự định nghĩa marker tên `NonNull` không tự khiến dòng trên bị lỗi biên dịch.** `@Target` chỉ cho phép annotation ở vị trí type use. Để annotation thực sự mô tả và kiểm tra tính không-null, bạn cần thêm **hợp đồng và công cụ** có khả năng hiểu annotation đó, ví dụ một static analysis/type-checking tool tương ứng, hoặc kiểm tra runtime được viết rõ ràng.

### Phân biệt ba lớp trách nhiệm

| Cơ chế | Bảo đảm điều gì? |
| --- | --- |
| `@Target(TYPE_USE/TYPE_PARAMETER)` | Annotation có thể xuất hiện ở những vị trí cú pháp nào |
| `@Retention(SOURCE/CLASS/RUNTIME)` | Metadata được giữ đến giai đoạn nào |
| Checker/processor/framework/runtime logic | Có kiểm tra hay diễn giải ý nghĩa domain-specific của annotation hay không |

Một annotation có tên `@Positive` không tự cấm số âm. Một annotation `@NonNull` không tự chặn `null`. Ngay cả annotation có `RUNTIME` cũng chỉ là metadata cho tới khi ứng dụng/công cụ thực sự đọc và áp dụng quy tắc.

### Không giả định thư viện nào cũng có cùng @NonNull

Có nhiều hệ sinh thái/chuẩn hóa nullness annotations và công cụ phân tích khác nhau. Khi dự án dùng một thư viện cụ thể, hãy kiểm tra:

- Annotation của thư viện target `TYPE_USE` hay `PARAMETER`/`FIELD`?
- Retention của nó là gì?
- Công cụ build, IDE hoặc static checker nào thực sự xử lý nó?
- Nó đánh dấu **giá trị của reference**, **type argument**, **element trong collection**, hay một hợp đồng khác?
- Annotation ở một package có được một checker khác hiểu theo cùng nghĩa không?

Đừng tự gán ý nghĩa chuẩn cho một tên annotation chỉ dựa trên spelling. Một framework chỉ phân tích annotation ở declarations có thể không tự đọc mọi vị trí annotated generic type, và ngược lại.

## 15. Type erasure và reflection: những giới hạn cần nhớ

Generic type information và type annotations là những khái niệm khác nhau:

- Java generics chủ yếu dùng **type erasure**: runtime không tạo một `Class` riêng cho từng `List<String>` và `List<Integer>`.
- Runtime reflection vẫn có thể đọc **một số generic signature và type-use annotation metadata tại những vị trí khai báo** khi class file chứa chúng và API cung cấp cấu trúc cần thiết.
- Bạn không thể mặc định hỏi một đối tượng `new ArrayList<String>()` để suy ra chính xác **type argument `String` từ đối tượng ở runtime**.
- Với `Field labels` khai báo `List<@Mark String>`, reflection có thông tin từ **declaration của field**, không phải nhờ quan sát phần tử runtime đang chứa gì.
- `@Retention(RUNTIME)` không làm generics trở thành reified; nó chỉ giữ annotation metadata theo ngữ cảnh tương ứng.

Nếu muốn lưu/kiểm chứng type information khi chạy, hãy thiết kế API đưa vào `Class<T>`, type token hoặc một biểu diễn schema phù hợp **khi thật sự cần**, thay vì kỳ vọng `TYPE_USE` tự giữ mọi đối số kiểu cho mỗi object.

## 16. Những lỗi phổ biến

1. **Dùng `TYPE_PARAMETER` cho `List<@Mark String>`.** Đây là type argument, cần `TYPE_USE`.
2. **Nhầm `PARAMETER` với `TYPE_PARAMETER`.** `PARAMETER` là formal value parameter; `TYPE_PARAMETER` là declaration `<T>`.
3. **Nhầm `TYPE` với `TYPE_USE`.** `TYPE` không tự cho phép annotate mọi kiểu được sử dụng.
4. **Bỏ `@Retention(RUNTIME)` rồi muốn dùng reflection.** Mặc định retention là `CLASS`.
5. **Đọc annotation trên field declaration thay vì annotated field type.** Với `TYPE_USE`, xem `field.getAnnotatedType()`.
6. **Chỉ xem raw `ParameterizedType` mà bỏ `AnnotatedParameterizedType`.** Khi muốn đọc annotation của `List<@Mark String>`, phải đi vào annotated type argument.
7. **Quên bounds có annotation riêng.** `<T extends @Mark Number>` đánh dấu `Number`, không phải declaration `T`.
8. **Cho rằng annotation có tên NonNull làm compiler Java SE tự kiểm tra null.** Không đúng nếu không có cơ chế hiểu annotation.
9. **Cho rằng `RUNTIME` là phép validate tự động.** Nó chỉ cho phép giữ và truy cập metadata runtime.
10. **Tưởng annotation thay đổi kiểu generic.** `List<@Mark String>` về Java generics cơ sở vẫn là `List<String>`; việc diễn giải marker thuộc một hệ thống checker nếu có.
11. **Đặt annotation ở sai chỗ của array dimensions.** `@Mark String[]` và `String @Mark []` chú thích hai vị trí cấu trúc khác nhau.
12. **Bỏ qua baseline API.** `TYPE_USE`/`TYPE_PARAMETER` có từ Java 8, nhưng `List.of` trong ví dụ JDK 17 có từ Java 9.
13. **Dựa vào một thư viện annotation quá cũ không còn được duy trì.** Nên dùng annotation và checker đã được dự án cập nhật, tài liệu hóa rõ nghĩa và phù hợp compiler/JDK đích.
14. **Không test reflection.** Nếu chương trình runtime phụ thuộc annotation metadata, thêm test xem annotation có thực sự còn sau compile/package và được truy vấn ở đúng annotated type path hay không.

## 17. Bài tập luyện tập

**Bài 1 — Nhận diện target.** Với `class Box<T>`, hãy phân biệt `T` trong declaration của `Box` với `String` trong `Box<String>`. Annotation nào cần `TYPE_PARAMETER` và annotation nào cần `TYPE_USE` nếu chỉ định từng vị trí?

**Bài 2 — Type parameter của generic method.** Viết annotation target `TYPE_PARAMETER`, đặt vào `static <@Marker T> T identity(T x)`, và giải thích vì sao không được dùng marker đó trong `List<@Marker String>`.

**Bài 3 — Type argument của nested generic.** Cho `Map<String,List<Integer>>`, dùng một annotation target `TYPE_USE` đánh dấu `String` và riêng `Integer`. Hãy chỉ ra đường đi trong `AnnotatedParameterizedType` để đọc annotation của nested `Integer`.

**Bài 4 — Retention.** Thay `@Retention(RUNTIME)` của ví dụ `TypeUseAndParameterDemo` bằng `@Retention(CLASS)`. Dự đoán kết quả khi gọi reflection và giải thích vì sao không thể tiếp tục gọi `value()` trên annotation `null`.

**Bài 5 — Reflection.** Tìm trong `TypeUseAndParameterDemo` lời gọi nào đọc:
- Annotation trên declaration của type parameter `T`.
- Annotation trên bound `Number`.
- Annotation trên generic type argument `String`.
- Annotation trên return type và parameter type.

**Bài 6 — Array type.** Viết `@UseInfo String[]` và `String @UseInfo []`. Hai annotation gắn vào cùng kiểu cấu trúc hay khác vị trí? Muốn đọc metadata của array dimension, nên bắt đầu từ reflection interface nào?

**Bài 7 — Không tự thực thi quy tắc.** Tạo marker `@NonNull` có target `TYPE_USE`. Đặt `@NonNull String value = null;`. Vì sao Java compiler cơ bản vẫn có thể cho code biên dịch? Bạn sẽ dùng loại công cụ nào để kiểm tra đúng nghĩa?

**Bài 8 — Bound.** Đánh dấu kiểu `Number` trong `<T extends Number>` bằng `@UseInfo`. Giải thích vì sao annotation này không đồng nghĩa đánh dấu `T` bằng `TYPE_PARAMETER`.

**Bài 9 — API thực tế.** Một thư viện gửi event có method `void publish(List<String> events)`. Nếu muốn đánh dấu **từng phần tử** không-null, vị trí annotation cần là `List<@NonNull String>` hay `@NonNull List<String>`? Khi nào cần cả hai? Lưu ý nghĩa chính xác phụ thuộc công cụ hiểu annotation.

## 18. Tóm tắt cốt lõi

- **`ElementType.TYPE_PARAMETER`** là target chuyên biệt cho **khai báo tham số kiểu**: `class Box<@Mark T>` hoặc `<@Mark T> T method(...)`.
- **`ElementType.TYPE_USE`** dùng cho **vị trí sử dụng kiểu**, ví dụ `List<@Mark String>`, kiểu trả về, kiểu tham số, bound, wildcard, cast, array dimension, `extends`/`implements`.
- **`TYPE_USE` bao gồm cả những ngữ cảnh type-parameter declaration theo JLS**, nhưng `TYPE_PARAMETER` thể hiện mục đích hẹp hơn; chúng không phải hai hằng có thể thay thế vô điều kiện trong mọi ngữ cảnh.
- **`@Target` kiểm soát nơi đặt**; **`@Retention` kiểm soát thời gian giữ metadata**. Mặc định retention là `CLASS`; cần `RUNTIME` để truy vấn bằng reflection chuẩn.
- **`TypeVariable`** là điểm bắt đầu để đọc metadata trên khai báo type parameter; **`AnnotatedType` và các subtype** hỗ trợ đọc metadata trên từng phần của một kiểu được sử dụng.
- **Annotation không tự kiểm tra nullability/validation** và không thay thế kiểm tra kiểu Java, generic bounds hay runtime validation.
- **Type erasure vẫn tồn tại**. Type annotations và annotated generic signatures có thể quan sát ở những vị trí khai báo phù hợp, nhưng không làm mỗi `List<String>` trở thành một kiểu runtime được tái hiện đầy đủ.
- Đây là các tính năng **vẫn dùng trong Java hiện hành**; khi tham gia dự án cần xác định rõ baseline JDK, thư viện annotation/checker thực tế và những công cụ xử lý nó.

## 19. Tài liệu chính thức và tra cứu thêm

1. **Java Language Specification, `9.6.4.1 @Target và `9.7.4 Where Annotations May Appear**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html
2. **Java Language Specification, `4.11 Where Types Are Used**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.11
3. **Java SE 17, `java.lang.annotation.ElementType`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html
4. **Java SE 17, `java.lang.annotation.Target`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html
5. **Java SE 17, `java.lang.annotation.Retention` và `RetentionPolicy`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html
6. **Java SE 17, `java.lang.reflect.TypeVariable`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html
7. **Java SE 17, `java.lang.reflect.AnnotatedType`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html
8. **Java SE 17, `java.lang.reflect.AnnotatedParameterizedType`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html
9. **Java SE 17, `java.lang.reflect.AnnotatedArrayType`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html
10. **Java SE 17, `java.lang.reflect.AnnotatedWildcardType`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html

Khi làm việc với type annotations ngoài ví dụ học tập, hãy dựa trên **JLS/Javadoc của phiên bản Java mục tiêu** và tài liệu của **công cụ thực sự đọc annotation**. Đúng `@Target` và `@Retention` là điều kiện để metadata đi đúng chỗ, nhưng ý nghĩa và độ tin cậy của việc kiểm tra hợp đồng còn phụ thuộc hệ thống sử dụng nó.