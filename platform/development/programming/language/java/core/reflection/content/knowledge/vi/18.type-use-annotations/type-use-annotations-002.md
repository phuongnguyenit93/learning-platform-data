# `AnnotatedType` và kiểu nền bên dưới trong Java Reflection

## 1. `AnnotatedType` dùng để làm gì?

Từ Java 8, annotation có thể xuất hiện ngay tại **vị trí sử dụng một kiểu** (*type use*): trên kiểu phần tử generic, kiểu của trường, kiểu trả về, phần tử mảng, wildcard, giới hạn type variable, v.v. Reflection cung cấp giao diện `java.lang.reflect.AnnotatedType` để giữ cả hai phần thông tin:

1. **Kiểu nền** (*underlying type*): trả qua `getType()`, là một `java.lang.reflect.Type`.
2. **Annotation gắn tại chính vị trí sử dụng kiểu đó**: truy cập bằng `getAnnotation(...)`, `getAnnotations()`, `getDeclaredAnnotations()` trên nút `AnnotatedType`.

Ví dụ:

~~~java
List<@NonNull String> names;
~~~

Nếu `@NonNull` là annotation áp dụng cho `TYPE_USE` và có `RetentionPolicy.RUNTIME`, Reflection có thể đọc annotation ở **kiểu đối số `String`**, không phải mặc nhiên ở `List`, tên biến `names` hay mọi đối tượng `String` khác.

Điểm quan trọng nhất: **`AnnotatedType` không phải là một `Type` mới đã được thay đổi**. Nó là lớp biểu diễn vị trí kiểu *kèm annotation*. Gọi `getType()` để lấy `Type` tương ứng; gọi các API `Annotated...` để đi vào cấu trúc con mà vẫn giữ annotation tại từng nút.

## 2. So sánh `Type`, `AnnotatedType` và annotation khai báo

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| `Class<?>` | Kiểu runtime hoặc lớp của trường khi xem dưới dạng raw type | `List.class`, `String[].class` |
| `Type` | Biểu diễn một kiểu Java có thể chứa generic | `List<String>`, `? extends Number`, `T` |
| `AnnotatedType` | Kiểu được **sử dụng tại một vị trí**, cùng annotation ở vị trí ấy | `@Mark List<@Mark String>` |
| `AnnotatedElement` của `Field`/`Method` | Annotation khai báo trên **phần tử** trường/phương thức | `@Deprecated` trên phương thức |

Một `AnnotatedType` chính nó thực hiện `AnnotatedElement`, nên có `getAnnotation()`, `getAnnotations()`. Nhưng điều đó **không khiến nó đồng nhất với `Field` hay `Method`**.

Ví dụ:

~~~java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface Mark { }

class Example {
    List<@Mark String> values;
}
~~~

Đoạn mã trên cần import `java.lang.annotation.*` và `java.util.List`; đây là minh họa, chưa phải chương trình độc lập.

- `Example.class.getDeclaredField("values").getDeclaredAnnotations()` kiểm tra annotation khai báo trực tiếp **trên trường**; trong ví dụ không có annotation declaration tại đó.
- `field.getAnnotatedType()` biểu diễn việc sử dụng `List<...>`. Nếu `List` không có annotation trực tiếp, `getAnnotation(Mark.class)` trên nút gốc là `null`.
- `((AnnotatedParameterizedType) field.getAnnotatedType()).getAnnotatedActualTypeArguments()[0]` biểu diễn `String`, và chính nút này có `@Mark`.

**`field.getAnnotatedType().getType()` chỉ lấy cấu trúc `Type`; không được dùng kết quả đó để hỏi annotation của từng vị trí generic.**

## 3. Lấy `AnnotatedType` từ đâu?

| Nguồn Reflection | API | Vị trí type-use được mô tả |
| --- | --- | --- |
| Field | `Field.getAnnotatedType()` | Kiểu của trường |
| Method | `Method.getAnnotatedReturnType()` | Kiểu trả về |
| Method | `Method.getAnnotatedParameterTypes()` | Mỗi kiểu tham số theo thứ tự |
| Method/Constructor | `getAnnotatedExceptionTypes()` | Các kiểu exception khai báo trong `throws` |
| Constructor/Method | `getAnnotatedReceiverType()` | Kiểu receiver, nếu áp dụng |
| Class | `Class.getAnnotatedSuperclass()` | Kiểu `extends` |
| Class | `Class.getAnnotatedInterfaces()` | Các kiểu `implements` hoặc `extends` interface |
| Type variable | `TypeVariable.getAnnotatedBounds()` | Các kiểu bound của type variable |
| Record component (Java 16+) | `RecordComponent.getAnnotatedType()` | Kiểu thành phần record |

Không phải API nào cũng đảm bảo trả về một đối tượng không `null`: chẳng hạn `getAnnotatedSuperclass()` có thể trả `null` khi không có superclass tương ứng. Các API trả mảng có thể trả mảng rỗng. Kiểm tra giá trị và cấu trúc thực tế trước khi ép kiểu.

Với một field generic:

~~~java
Field field = Box.class.getDeclaredField("labels");

Class<?> raw = field.getType();          // List.class
Type generic = field.getGenericType();  // List<String>
AnnotatedType annotated = field.getAnnotatedType();
Type base = annotated.getType();         // Type biểu diễn List<String>
~~~

Đây là đoạn minh họa, phải có `Box`, import `java.lang.reflect.*` và xử lý `NoSuchFieldException`.

- `getType()` của **Field** trả `Class<?>`, nên trường `List<String>` thường được thấy dưới dạng raw `List.class`.
- `getGenericType()` của **Field** trả `Type` và giữ cấu trúc generic đã khai báo.
- `getType()` của **AnnotatedType** cũng trả `Type` mô tả kiểu nền tại nút đó. Đối với `List<String>`, nó là một `ParameterizedType`, không bắt buộc là `Class`.
- Đừng ép `(Class<?>) annotated.getType()` một cách mù quáng; nếu kiểu là `List<String>`, phép ép kiểu có thể gây `ClassCastException`.

## 4. Phân cấp `AnnotatedType`: đi theo đúng hình dạng kiểu nền

Các giao diện con chuyên biệt cho phép duyệt từng loại kiểu:

| Giao diện | Kiểu nền thường gặp | API lấy nút con chứa annotation |
| --- | --- | --- |
| `AnnotatedParameterizedType` | `ParameterizedType`, ví dụ `List<String>` | `getAnnotatedActualTypeArguments()` |
| `AnnotatedArrayType` | `Class` của mảng hoặc `GenericArrayType` | `getAnnotatedGenericComponentType()` |
| `AnnotatedWildcardType` | `WildcardType`, ví dụ `? extends Number` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `AnnotatedTypeVariable` | `TypeVariable`, ví dụ `T` | `getAnnotatedBounds()` |

Đây là một **cây vị trí kiểu**, không phải một mảng annotation phẳng. Ví dụ:

~~~java
List<@A ? extends @B Number>
~~~

Có thể quan sát các nút (nếu `@A`, `@B` là type-use annotations giữ tới runtime):

1. Gốc `List<...>`: `AnnotatedParameterizedType`.
2. Đối số generic `? extends Number`: `AnnotatedWildcardType`, nhận `@A` trên wildcard.
3. Upper bound `Number`: một `AnnotatedType` riêng, nhận `@B`.

Nếu chỉ hỏi `getAnnotations()` ở gốc `List`, bạn **không tự động nhận** annotation trên wildcard hoặc bound. Phải đi vào những nút con tương ứng.

### Type variable và kiểu được thay vào runtime

Với khai báo:

~~~java
class Repository<T extends @A Number> { }
~~~

Annotation `@A` gắn trên **bound `Number`** của type parameter `T`, không phải lúc nào cũng nằm trên chính `T`. Đọc bằng:

~~~java
TypeVariable<?> t = Repository.class.getTypeParameters()[0];
AnnotatedType bound = t.getAnnotatedBounds()[0];
~~~

Vì **Java generic dùng type erasure**, `AnnotatedType` không nói cho bạn kiểu đối tượng thực tế của mọi phần tử được lưu trong `List<T>` tại runtime. Nó cho biết **khai báo kiểu và type-use annotations có thể giữ được bằng metadata**. Không nhầm thông tin khai báo với kiểm tra giá trị động hoặc khả năng ép kiểu.

## 5. Ví dụ hoàn chỉnh Java 17+: kiểu nền và annotation ở từng nút

Lưu file **`AnnotatedTypeLesson.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.*;
import java.util.List;

public class AnnotatedTypeLesson {
    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Mark {
        String value();
    }

    static class Box<T extends @Mark("bound") Number> {
        public @Mark("list") List<@Mark("element") String> labels;
        public @Mark("component") String @Mark("dimension") [] tags;
        public List<@Mark("wildcard") ? extends @Mark("upper") Number> numbers;

        public @Mark("return") String echo(@Mark("param") String word) {
            return word;
        }
    }

    static String mark(AnnotatedType type) {
        Mark annotation = type.getAnnotation(Mark.class);
        return annotation == null ? "(none)" : annotation.value();
    }

    public static void main(String[] args) throws Exception {
        Field labels = Box.class.getDeclaredField("labels");
        AnnotatedType root = labels.getAnnotatedType();
        System.out.println("root Type=" + root.getType().getTypeName());
        System.out.println("root Mark=" + mark(root));

        AnnotatedParameterizedType parameterized =
                (AnnotatedParameterizedType) root;
        AnnotatedType element =
                parameterized.getAnnotatedActualTypeArguments()[0];
        System.out.println("argument Type=" + element.getType().getTypeName());
        System.out.println("argument Mark=" + mark(element));

        Field tags = Box.class.getDeclaredField("tags");
        AnnotatedArrayType array =
                (AnnotatedArrayType) tags.getAnnotatedType();
        System.out.println("array Type=" + array.getType().getTypeName());
        System.out.println("dimension Mark=" + mark(array));
        System.out.println("component Mark="
                + mark(array.getAnnotatedGenericComponentType()));

        Field numbers = Box.class.getDeclaredField("numbers");
        AnnotatedParameterizedType num =
                (AnnotatedParameterizedType) numbers.getAnnotatedType();
        AnnotatedWildcardType wildcard =
                (AnnotatedWildcardType) num.getAnnotatedActualTypeArguments()[0];
        System.out.println("wildcard Type="
                + wildcard.getType().getTypeName());
        System.out.println("wildcard Mark=" + mark(wildcard));
        System.out.println("upper Mark="
                + mark(wildcard.getAnnotatedUpperBounds()[0]));

        TypeVariable<Class<Box>> var = Box.class.getTypeParameters()[0];
        AnnotatedType bound = var.getAnnotatedBounds()[0];
        System.out.println("bound Type=" + bound.getType().getTypeName());
        System.out.println("bound Mark=" + mark(bound));

        Method echo = Box.class.getDeclaredMethod("echo", String.class);
        System.out.println("return Mark="
                + mark(echo.getAnnotatedReturnType()));
        System.out.println("param Mark="
                + mark(echo.getAnnotatedParameterTypes()[0]));
        System.out.println("declared field annotations="
                + labels.getDeclaredAnnotations().length);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AnnotatedTypeLesson.java
java AnnotatedTypeLesson
~~~

Kết quả stdout từ chương trình trên:

~~~text
root Type=java.util.List<java.lang.String>
root Mark=list
argument Type=java.lang.String
argument Mark=element
array Type=java.lang.String[]
dimension Mark=dimension
component Mark=component
wildcard Type=? extends java.lang.Number
wildcard Mark=wildcard
upper Mark=upper
bound Type=java.lang.Number
bound Mark=bound
return Mark=return
param Mark=param
declared field annotations=0
~~~

### Diễn giải kết quả

- `labels` có kiểu nền `List<String>`: `root.getType()` hiển thị cấu trúc generic, đồng thời `mark(root)` lấy `@Mark("list")` ở vị trí kiểu `List`.
- Nút con của `AnnotatedParameterizedType` có kiểu nền `String` với `@Mark("element")`, không phải annotation của chính field.
- `String @Mark("dimension") []` có `AnnotatedArrayType` ở gốc cho **chiều mảng**, còn `@Mark("component") String` gắn ở kiểu **phần tử**. Hai vị trí annotation là khác nhau.
- Ở `List<@Mark("wildcard") ? extends @Mark("upper") Number>`, wildcard mang `"wildcard"`; upper bound `Number` mang `"upper"`.
- Bound của `T extends Number` mang `@Mark("bound")`; annotation trên return type và parameter type lần lượt là `"return"` và `"param"`.
- `labels.getDeclaredAnnotations().length == 0` vì annotation trong ví dụ nằm ở **type-use**, không phải annotation khai báo trực tiếp của field. Kết quả này minh họa vì sao chỉ đọc annotation từ `Field` chưa đủ.

Chương trình trên không dùng logic suy đoán theo tên lớp của các implementation nội bộ `Type`. `getTypeName()` giúp in hình dạng kiểu một cách dễ hiểu; API gốc vẫn là `Type`.

## 6. Mảng nhiều chiều: annotation nằm trên từng chiều

Java hỗ trợ gắn type-use annotation lên cả kiểu phần tử và từng chiều mảng:

~~~java
@Mark("element") String @Mark("outer") [] @Mark("inner") [] matrix;
~~~

Đoạn khai báo trên chỉ minh họa trong lớp có annotation `@Mark` như ví dụ hoàn chỉnh. Khi Reflection mô tả `matrix`:

1. `field.getAnnotatedType()` biểu diễn **kiểu mảng ngoài cùng** (`AnnotatedArrayType`) và giữ `@Mark("outer")`.
2. `getAnnotatedGenericComponentType()` đi xuống một chiều; với mảng 2 chiều, nút này vẫn là `AnnotatedArrayType`, có `@Mark("inner")`.
3. Đi xuống thêm một lần thì tới kiểu phần tử `String` với `@Mark("element")`.

Cách ghi `String @Mark("x") []` khác về **vị trí annotation** so với `@Mark("x") String[]`. Nếu cần diễn giải field mảng chính xác, phải đi theo các `AnnotatedArrayType` thay vì chỉ xem `String[][].class`. Trên các kiểu mảng generic, underlying type có thể là `GenericArrayType`; không nên giả định luôn là `Class<?>[]`.

## 7. Khi nào nên lấy `getType()`, khi nào phải duyệt `AnnotatedType`?

### Chỉ cần cấu trúc kiểu?

Nếu một thư viện chỉ cần biết field là `List<String>` để ánh xạ dữ liệu, `Field.getGenericType()` hoặc `AnnotatedType.getType()` cung cấp cấu trúc `Type` thích hợp. Khi muốn biết phần tử generic, kiểm tra `instanceof ParameterizedType` rồi gọi `getActualTypeArguments()`. Kết quả là **`Type`**, không chứa trực tiếp type-use annotation của từng nhánh.

### Cần quy tắc được đánh dấu bởi annotation?

Nếu framework dùng `@NonNull`, `@Sensitive`, `@Validated` hoặc một annotation tùy chỉnh để điều khiển kiểm tra schema, nó cần duyệt **các nút AnnotatedType** và đọc annotation đúng vị trí. Dạng mô tả an toàn:

~~~java
AnnotatedType type = field.getAnnotatedType();

if (type instanceof AnnotatedParameterizedType parameterized) {
    for (AnnotatedType argument :
            parameterized.getAnnotatedActualTypeArguments()) {
        // Kiểm tra annotation tại MỖI đối số kiểu, rồi tiếp tục đệ quy.
    }
}
~~~

Đây là đoạn minh họa bên trong phương thức có `Field field`. Đừng ép mọi `AnnotatedType` sang `AnnotatedParameterizedType`; kiểu nền có thể là `Class`, `TypeVariable`, `GenericArrayType`, `WildcardType`, hoặc dạng khác. Khi cần xử lý sâu hơn, phân nhánh theo từng giao diện `Annotated...` tương ứng.

### Type-use metadata không đồng nghĩa validation tự động

Một annotation `@NonNull` trên type argument **không khiến JVM tự động cấm null**, và `AnnotatedType.getAnnotation` chỉ đọc metadata. Muốn kiểm tra dữ liệu thật cần cơ chế thực thi do thư viện hoặc ứng dụng triển khai. Ngay cả khi annotation hiện diện, `Type` không thay thế được việc kiểm tra phần tử runtime.

Tương tự, annotation tại vị trí `List<@NonNull String>` không biến generic của Java thành *reified generics*. Do erasure, JVM không có thông tin runtime để chứng minh toàn bộ các phần tử của một `List` bất kỳ thực sự là `String`.

## 8. Điều kiện để Reflection đọc được annotation

Định nghĩa thường dùng:

~~~java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface NonNull { }
~~~

Cần chú ý:

- `TYPE_USE` cho phép annotation xuất hiện trên các **vị trí sử dụng kiểu**. `TYPE_PARAMETER` là target riêng cho việc khai báo biến kiểu, ví dụ ngay trên chữ `T` của `class Box<@A T>`; nếu cần cả hai, khai báo `@Target({ElementType.TYPE_USE, ElementType.TYPE_PARAMETER})`.
- `RetentionPolicy.RUNTIME` cần thiết nếu muốn đọc annotation từ Reflection lúc chạy. `SOURCE` không tồn tại trong class file; `CLASS` được ghi vào class file nhưng không hiện diện trong Reflection runtime thông thường.
- Compiler có thể đưa type-use annotations vào thuộc tính metadata trong class file; thông tin hiển thị phụ thuộc việc khai báo đúng target/retention và phần tử Java thật sự được biên dịch.
- `getAnnotation(MyAnnotation.class)` trả `null` khi annotation không có ở vị trí đó. Nếu annotation nằm trên **nút con**, chỉ hỏi tại nút gốc không đủ.
- Các annotation áp dụng lên phương thức/lớp **khác** với annotation áp dụng lên kiểu. Một annotation có thể cho phép nhiều target, và cần chọn API theo câu hỏi thực tế.

**Không xem `getType()` là công cụ để lấy annotation:** `Type` là thông tin kiểu nền. Muốn đi qua metadata type-use, phải giữ và duyệt `AnnotatedType`.

## 9. Lỗi phổ biến

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “`AnnotatedType` luôn có `Class<?> getType()`.” | `getType()` trả `Type`; generic thường là `ParameterizedType`, wildcard là `WildcardType`, v.v. |
| “Annotation trên `List<@A String>` nằm ở `List`.” | `@A` nằm trên **đối số `String`**; đi qua `getAnnotatedActualTypeArguments()`. |
| “Đọc `field.getAnnotations()` là đủ cho mọi annotation liên quan.” | API này hỏi annotation **trên phần tử field**; type-use annotation phải hỏi qua `getAnnotatedType()`. |
| “`@A String[]` và `String @A []` giống nhau.” | Annotation có thể gắn vào **thành phần kiểu khác nhau**: phần tử hoặc chiều mảng. |
| “Mọi `AnnotatedType` đều là `AnnotatedParameterizedType`.” | Phải kiểm tra `instanceof` trước khi ép kiểu. |
| “Không thấy annotation nghĩa là class file không có annotation.” | Có thể đang hỏi sai nút, target không thích hợp hoặc retention không phải `RUNTIME`. |
| “`getType()` của `AnnotatedType` cho biết generic type argument của object hiện tại.” | Nó mô tả **kiểu khai báo tại vị trí Reflection**; Java generics không reify mọi đối số kiểu runtime. |
| “`isAnnotationPresent` trên root tự kiểm tra cả cây.” | Không: kiểm tra **nút hiện tại**; muốn kiểm tra con phải duyệt rõ ràng. |

## 10. Checklist thực hành

1. **Xác định vị trí khai báo** cần soi: field, method parameter, return type, superclass, interface, type-variable bound, array hoặc record component.
2. **Lấy `AnnotatedType` đúng API**. Không thay bằng `getAnnotations()` trên phần tử khi cần type-use.
3. **Đọc `getType()`** để hiểu kiểu nền đang được mô tả; dùng `instanceof` cho `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType` khi cần.
4. **Đọc annotation trên đúng nút** bằng `getAnnotation`/`getAnnotations`.
5. **Duyệt các nút con** qua các interface `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedWildcardType`, `AnnotatedTypeVariable`; với inner class có thể xem `getAnnotatedOwnerType()`.
6. **Xác nhận `@Target(TYPE_USE)` và `@Retention(RUNTIME)`** của annotation muốn đọc.
7. **Không suy ra logic validation hoặc khả năng ép kiểu runtime chỉ từ metadata**; các quy tắc đó do ứng dụng triển khai.

### Câu hỏi tự kiểm tra

**1.** Với `List<@Mark String>`, hỏi annotation ở `field.getAnnotatedType()` có chắc tìm được `@Mark` không?  
**Không.** Annotation nằm ở nút generic argument `String`; cần duyệt `getAnnotatedActualTypeArguments()[0]`.

**2.** `AnnotatedType.getType()` trả về `Class<?>` cho `List<String>`?  
**Không mặc định.** Nó trả `Type`, trong trường hợp này thường là `ParameterizedType` mang `List<String>`.

**3.** `String @Mark []` thì `@Mark` gắn vào đâu?  
**Chiều mảng**, do đó kiểm tra nút `AnnotatedArrayType`. `@Mark String[]` có vị trí annotation khác.

**4.** Cách tìm annotation trên `? extends @Mark Number` là gì?  
Vào `AnnotatedWildcardType.getAnnotatedUpperBounds()[0]`, rồi hỏi `getAnnotation(Mark.class)`.

**5.** Annotation có `@Retention(CLASS)` có thể đọc từ `AnnotatedType` bằng Reflection runtime không?  
**Không theo Reflection thông thường.** Muốn đọc tại runtime, cần `RUNTIME`.

**6.** `Field.getType()` và `Field.getAnnotatedType().getType()` luôn giống nhau về mức thông tin generic?  
**Không.** API đầu trả raw `Class<?>`; API sau trả `Type` nền của vị trí kiểu, có thể giữ cấu trúc generic.

**Kết luận:** `AnnotatedType` là **một nút dùng kiểu đã được gắn annotation**. `getType()` trả **kiểu nền ở nút đó**, còn `getAnnotation()` và các interface `Annotated...` giúp đọc các annotation xuất hiện **đúng từng vị trí** trong cây generic, mảng, wildcard và type-variable bounds.

### Tài liệu tham khảo chính thức

- [JDK 17 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [JDK 17 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [JDK 17 — `AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html)
- [JDK 17 — `AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html)
- [JDK 17 — `AnnotatedTypeVariable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedTypeVariable.html)
- [JDK 17 — `Field.getAnnotatedType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#getAnnotatedType())
- [JLS 17 §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4)
