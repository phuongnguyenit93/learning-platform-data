# `AnnotatedArrayType` và annotation ở các chiều mảng — Java Reflection

## 1. Vấn đề: một mảng nhiều chiều có nhiều vị trí được annotation

Trong Java, annotation có `@Target(ElementType.TYPE_USE)` có thể nằm **trên kiểu phần tử** hoặc **trên từng chiều của kiểu mảng**. Ví dụ:

~~~java
@Pos("element") String @Pos("outer") [] @Pos("inner") [] matrix;
~~~

Giả sử `@Pos` là annotation TYPE_USE được giữ ở runtime. Khai báo trên có ba vị trí độc lập:

- `@Pos("outer")`: vị trí **mảng ngoài cùng**, có kiểu nền `String[][]`.
- `@Pos("inner")`: vị trí **mảng thành phần**, có kiểu nền `String[]`.
- `@Pos("element")`: vị trí **kiểu phần tử cuối cùng**, có kiểu nền `String`.

Nếu chỉ gọi `Field.getType()` hoặc `Field.getGenericType()`, ta nhận cấu trúc kiểu nhưng **không truy vấn được annotation riêng tại từng chiều**. Java Reflection biểu diễn cây này bằng `AnnotatedType`, cụ thể là các nút `AnnotatedArrayType`.

**Quy tắc ghi nhớ:** một mảng có `n` chiều cần được duyệt qua `n` nút `AnnotatedArrayType` trước khi tới kiểu phần tử, có thể được annotation riêng.

## 2. `AnnotatedArrayType` là gì?

`java.lang.reflect.AnnotatedArrayType` là giao diện con của `AnnotatedType` (từ Java 8) mô tả một **vị trí sử dụng kiểu mảng**, kèm các type-use annotations của **chính vị trí đó**.

Hai thao tác quan trọng:

~~~java
AnnotatedType root = field.getAnnotatedType();
Type underlying = root.getType();

if (root instanceof AnnotatedArrayType array) {
    AnnotatedType component =
            array.getAnnotatedGenericComponentType();
}
~~~

Đây là đoạn minh họa trong một phương thức có biến `Field field`, import `java.lang.reflect.*`; chưa phải chương trình độc lập.

- `root.getType()` trả **kiểu nền** dạng `java.lang.reflect.Type`. Với `String[][]`, giá trị đó thông thường là `Class` của kiểu mảng; với `T[]`, nó có thể là `GenericArrayType`.
- `root.getAnnotation(Pos.class)` hỏi annotation nằm tại **nút root hiện tại**, không tự gộp annotation của các chiều bên trong.
- `getAnnotatedGenericComponentType()` đi xuống **chính xác một mức kiểu thành phần**, nhưng vẫn giữ metadata type-use annotation tại mức tiếp theo.
- Sau khi đi qua đủ chiều, ta đến kiểu phần tử như `String`, `int`, `T` hoặc `List<String>`. Nút cuối không nhất thiết là `AnnotatedArrayType`.
- `AnnotatedArrayType.getAnnotatedOwnerType()` trả `null`: một kiểu mảng không phải trường hợp owner type của một member class.

Javadoc của `AnnotatedArrayType` không chỉ dành cho mảng có annotation. Ngay cả khi một chiều **không có annotation**, nó vẫn có thể là nút `AnnotatedArrayType`; khi đó `getAnnotations().length == 0` và `getAnnotation(Pos.class) == null`.

## 3. Phân biệt annotation trên phần tử và trên dấu `[]`

So sánh ba khai báo:

~~~java
@Pos("element") String[] first;
String @Pos("dimension") [] second;
@Pos("element") String @Pos("dimension") [] third;
~~~

Giả sử chúng nằm trong một class dùng annotation `@Pos` có `TYPE_USE` và `RUNTIME`.

| Khai báo | Annotation ở nút mảng `String[]` | Annotation ở nút phần tử `String` |
| --- | --- | --- |
| `@Pos("element") String[] first` | Không | `element` |
| `String @Pos("dimension") [] second` | `dimension` | Không |
| `@Pos("element") String @Pos("dimension") [] third` | `dimension` | `element` |

**Đặt annotation trước `String` không tương đương đặt annotation trước `[]`.**

Mã kiểm tra từng nơi:

~~~java
AnnotatedType root = field.getAnnotatedType();
Pos onArray = root.getAnnotation(Pos.class);

AnnotatedType component =
        ((AnnotatedArrayType) root).getAnnotatedGenericComponentType();
Pos onElement = component.getAnnotation(Pos.class);
~~~

Ví dụ chỉ minh họa khi `field` là field mảng, `Pos` khả dụng và đã khai báo/xử lý ngoại lệ ở phần gọi Reflection. Không ép kiểu sang `AnnotatedArrayType` khi field thực tế không có kiểu mảng.

### Với mảng hai chiều

~~~java
@Pos("element") String @Pos("outer") [] @Pos("inner") [] matrix;
~~~

Ta đi theo thứ tự:

~~~text
AnnotatedArrayType: String[][]   → @Pos("outer")
    │ getAnnotatedGenericComponentType()
    ▼
AnnotatedArrayType: String[]     → @Pos("inner")
    │ getAnnotatedGenericComponentType()
    ▼
AnnotatedType:      String      → @Pos("element")
~~~

Chiều ngoài là **nút đầu tiên** mà `Field.getAnnotatedType()` trả về, không phải chiều cuối. Vì thế đừng đảo thứ tự annotation trong lúc tạo schema JSON hoặc thông báo lỗi.

Đối với ba chiều trở lên, áp dụng cùng quy tắc đệ quy: mỗi lần gọi `getAnnotatedGenericComponentType()` bỏ đi một chiều mảng bên ngoài và chuyển xuống nút kiểu thành phần kế tiếp.

## 4. Lấy metadata annotation ở mức nào?

Có ba câu hỏi khác nhau:

| Câu hỏi | API |
| --- | --- |
| Field được khai báo với kiểu gì, bỏ qua generic? | `field.getType()` |
| Field có cấu trúc generic gì? | `field.getGenericType()` |
| Type-use annotation đặt trên chiều mảng và phần tử nào? | `field.getAnnotatedType()`, sau đó duyệt `AnnotatedArrayType` |

Một `Field` cũng là `AnnotatedElement`, nhưng:

~~~java
field.getDeclaredAnnotations();
~~~

hỏi annotation khai báo **trên chính field**, không tự gom annotation type-use trên `String` hay từng `[]`.

Ngay cả khi `field.getDeclaredAnnotations()` trả mảng trống, `field.getAnnotatedType()` và các node con vẫn có thể chứa annotation ở các vị trí kiểu. Đó không phải dữ liệu mâu thuẫn; chúng mô tả **hai mục tiêu annotation khác nhau**.

Chú ý `getAnnotatedType().getType()` trả `Type`, không luôn là `Class<?>`. Nếu làm việc với kiểu generic array như `T[]`, ép trực tiếp sang `Class<?>` có thể gây `ClassCastException`.

## 5. Chương trình Java 17+ hoàn chỉnh: duyệt từng chiều mảng

Lưu mã sau vào **`AnnotatedArrayDemo.java`**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;

public class AnnotatedArrayDemo {
    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface Pos {
        String value();
    }

    static class Sample<T extends @Pos("bound") Number> {
        public @Pos("element") String
                @Pos("outer") [] @Pos("inner") [] matrix;

        public List<
                @Pos("member-element") String
                @Pos("member-dimension") []> groups;

        public T @Pos("generic-dimension") [] genericArray;

        public @Pos("return-element") String
                @Pos("return-dimension") [] echo(
                    @Pos("param-element") String
                    @Pos("param-dimension") [] words) {
            return words;
        }
    }

    static String ann(AnnotatedType type) {
        Pos p = type.getAnnotation(Pos.class);
        return p == null ? "-" : p.value();
    }

    static void walk(String label, AnnotatedType type) {
        int depth = 0;
        while (type instanceof AnnotatedArrayType array) {
            System.out.println(label + "[" + depth + "] "
                    + type.getType().getTypeName()
                    + " @" + ann(type));
            type = array.getAnnotatedGenericComponentType();
            depth++;
        }
        System.out.println(label + "[" + depth + "] "
                + type.getType().getTypeName()
                + " @" + ann(type));
    }

    public static void main(String[] args) throws Exception {
        Field matrix = Sample.class.getDeclaredField("matrix");
        walk("matrix", matrix.getAnnotatedType());
        System.out.println("field annotations="
                + matrix.getDeclaredAnnotations().length);

        Field groups = Sample.class.getDeclaredField("groups");
        AnnotatedParameterizedType parameterized =
                (AnnotatedParameterizedType) groups.getAnnotatedType();
        walk("groups.arg",
                parameterized.getAnnotatedActualTypeArguments()[0]);

        Field generic = Sample.class.getDeclaredField("genericArray");
        System.out.println("generic underlying is GenericArrayType="
                + (generic.getAnnotatedType().getType()
                        instanceof GenericArrayType));
        walk("generic", generic.getAnnotatedType());

        TypeVariable<?> t = Sample.class.getTypeParameters()[0];
        System.out.println("T.bound @"
                + ann(t.getAnnotatedBounds()[0]));

        Method echo = Sample.class.getDeclaredMethod(
                "echo", String[].class);
        walk("return", echo.getAnnotatedReturnType());
        walk("parameter", echo.getAnnotatedParameterTypes()[0]);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AnnotatedArrayDemo.java
java AnnotatedArrayDemo
~~~

Stdout:

~~~text
matrix[0] java.lang.String[][] @outer
matrix[1] java.lang.String[] @inner
matrix[2] java.lang.String @element
field annotations=0
groups.arg[0] java.lang.String[] @member-dimension
groups.arg[1] java.lang.String @member-element
generic underlying is GenericArrayType=true
generic[0] T[] @generic-dimension
generic[1] T @-
T.bound @bound
return[0] java.lang.String[] @return-dimension
return[1] java.lang.String @return-element
parameter[0] java.lang.String[] @param-dimension
parameter[1] java.lang.String @param-element
~~~

### Giải thích đầy đủ

1. **`matrix`**: `walk` đi từ kiểu `String[][]` xuống `String[]`, rồi tới `String`. Annotation ở mỗi nút lần lượt là `outer`, `inner`, `element`. Tên kiểu nền được in bằng `Type.getTypeName()`, không phụ thuộc `toString()` của implementation Reflection.
2. **`field annotations=0`**: annotation `@Pos` chỉ có target `TYPE_USE`. Nó gắn lên các phần của **kiểu field**, không phải annotation khai báo riêng trên đối tượng `Field`.
3. **`groups`**: kiểu ngoài cùng là `List<...>`, nên root là `AnnotatedParameterizedType`. Phải đi vào `getAnnotatedActualTypeArguments()[0]`, rồi mới gặp `AnnotatedArrayType` biểu diễn `String[]`.
4. **`genericArray`**: kiểu nền là `T[]`, được biểu diễn bằng `GenericArrayType`, không phải `Class` của một mảng đã biết kiểu phần tử cụ thể. Nhưng `AnnotatedArrayType` vẫn giúp đi từ `T[]` xuống type variable `T`.
5. **`T.bound`**: annotation `@Pos("bound")` ở khai báo `T extends Number`; nó **không tự động xuất hiện trên mọi lần dùng `T`**, nên `generic[1]` có `@-`. Phải lấy bound bằng `TypeVariable.getAnnotatedBounds()`.
6. **Method**: `getAnnotatedReturnType()` và `getAnnotatedParameterTypes()` cũng giữ annotation theo từng chiều mảng; không chỉ field mới làm được.

Ví dụ này kiểm tra metadata, không tạo đối tượng `Sample` và không đọc nội dung mảng; Reflection đọc được cấu trúc khai báo **mà không cần giá trị mảng thực tế**.

## 6. Generic array, parameterized type và kiểu thành phần

Có hai kiểu mảng cần phân biệt khi xem `Type` nền:

| Khai báo | `AnnotatedType` root | `getType()` root thường là |
| --- | --- | --- |
| `String[][]` | `AnnotatedArrayType` | `Class` đại diện `String[][].class` |
| `int[]` | `AnnotatedArrayType` | `Class` đại diện `int[].class` |
| `T[]` trong generic class | `AnnotatedArrayType` | `GenericArrayType` |
| `List<String>[]` trong khai báo hợp lệ | `AnnotatedArrayType` | `GenericArrayType` |
| `List<String[]>` | `AnnotatedParameterizedType` ở root | `ParameterizedType`; nút generic argument mới là `AnnotatedArrayType` |

Trường hợp `List<String[]>`:

~~~text
AnnotatedParameterizedType: List<String[]>
    └── AnnotatedArrayType: String[]
            └── AnnotatedType: String
~~~

Trong khi với `List<String>[]`:

~~~text
AnnotatedArrayType: List<String>[]
    └── AnnotatedParameterizedType: List<String>
            └── AnnotatedType: String
~~~

Điểm mấu chốt: hai khai báo này **khác vị trí mảng trong cây kiểu**. Một cái là **danh sách các mảng**; cái kia là **mảng các danh sách**. Việc ép kiểu root phải dựa trên cấu trúc thực tế, không dựa vào tên field hoặc giả định “có generic thì root là `AnnotatedParameterizedType`”.

Khi muốn tính số chiều của một nút mảng, duyệt `while (type instanceof AnnotatedArrayType)` và đếm số lần đi xuống. Với một cây generic phức tạp, việc duyệt đầy đủ cần thêm nhánh cho `AnnotatedParameterizedType`, `AnnotatedWildcardType`, `AnnotatedTypeVariable`; riêng `AnnotatedArrayType` chỉ giải quyết đoạn đường qua các chiều mảng.

## 7. Vì sao không dùng `Class.getComponentType()` thay thế?

Có hai API có tên gần giống nhưng nhiệm vụ khác nhau.

`Class.getComponentType()`:

~~~java
Class<?> component = String[][].class.getComponentType();
// String[].class
~~~

trả **Class kiểu thành phần** của một kiểu mảng runtime. Nó không giữ type-use annotations và không trực tiếp biểu diễn `T[]` có kiểu nền generic.

`AnnotatedArrayType.getAnnotatedGenericComponentType()`:

~~~java
AnnotatedType node = field.getAnnotatedType();
AnnotatedType next =
        ((AnnotatedArrayType) node).getAnnotatedGenericComponentType();
~~~

trả **AnnotatedType của kiểu thành phần**, tức vẫn truy vấn được annotation gắn với chiều tiếp theo hoặc kiểu phần tử. Trong trình phân tích schema cần giữ annotation theo vị trí, API thứ hai là quan trọng.

**Đừng chỉ đi xuống `getType()` rồi tìm cách khôi phục annotation:** thông tin annotation không được mã hóa thành nội dung của `Class`, `ParameterizedType` hay `GenericArrayType` nền. Bạn phải đi qua **cây `AnnotatedType`** song song với cây `Type`.

## 8. Annotation ở các dấu ngoặc mảng sau tên biến

Java cho phép cú pháp mảng kiểu cũ với `[]` sau tên biến, ví dụ:

~~~java
// Không khuyến khích cho mã mới:
String[] names[];
~~~

Dạng này có thể gây nhầm lẫn về vị trí chiều mảng và annotation, nhất là khi trộn với `[]` đặt gần kiểu. Trong mã mới, ưu tiên đưa toàn bộ các chiều mảng vào phần khai báo **type** trước tên biến:

~~~java
String[][] names;
~~~

Khi có type-use annotation, đặt dấu chú thích sát chiều mảng mà nó mô tả:

~~~java
@Pos("element") String @Pos("outer") [] @Pos("inner") [] names;
~~~

Nếu đang phân tích source code của thư viện hoặc bộ sinh mã, đừng suy luận vị trí annotation chỉ bằng cách đếm chuỗi `[]` trong văn bản; hãy kiểm tra kiểu tại vị trí sử dụng theo quy tắc Java và metadata biên dịch. Thứ tự chiều có thể khó đọc khi dùng cú pháp đặt bracket sau tên biến.

## 9. Bẫy của `@Target` và `@Retention`

Một annotation muốn được đọc tại runtime trong **vị trí sử dụng kiểu mảng** nên có:

~~~java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface Pos {
    String value();
}
~~~

Đây là mảnh khai báo cần import `java.lang.annotation.*` và đặt trong ngữ cảnh Java phù hợp.

- `TYPE_USE` cho phép annotation gắn trên kiểu phần tử và các chiều mảng. `ElementType.FIELD` chỉ dành cho vị trí khai báo field, không thay cho `TYPE_USE`.
- `RetentionPolicy.RUNTIME` cần thiết nếu muốn `AnnotatedType.getAnnotation()` đọc được annotation khi JVM đang chạy. `CLASS` vẫn ghi metadata vào class file nhưng không hiển thị qua Java Reflection runtime thông thường; `SOURCE` không giữ qua biên dịch.
- `@Target({FIELD, TYPE_USE})` cho phép dùng annotation ở nhiều vị trí. Khi đó cần xác định chính xác bạn muốn metadata của declaration hay metadata của type-use.
- `AnnotatedType.getAnnotation(Pos.class)` chỉ kiểm tra **nút hiện tại**. Nếu `null`, hãy duyệt các chiều hoặc các generic argument tương ứng, thay vì kết luận toàn bộ field không có annotation.
- Không có lời gọi nào trên `AnnotatedArrayType` làm JVM tự động kiểm tra các phần tử mảng có `null` hay không. Annotation là metadata; validation phải được ứng dụng/framework cài đặt riêng.

## 10. Những lỗi thường gặp khi viết code Reflection

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “`String[][]` là một mảng, chỉ cần đọc annotation ở root.” | Có **hai chiều**, cần hai nút `AnnotatedArrayType`, rồi đến kiểu phần tử. |
| “`@A String[]` và `String @A []` mang ý nghĩa type-use như nhau.” | `@A` đầu tiên gắn trên phần tử; dạng sau gắn trên chiều mảng. |
| “`getAnnotatedGenericComponentType()` luôn trả `AnnotatedArrayType`.” | Sau chiều cuối, có thể trả AnnotatedType của `String`, `T`, `List<...>`, v.v. |
| “`AnnotatedArrayType.getType()` luôn là `Class`.” | `T[]` và mảng của một parameterized type có thể dùng `GenericArrayType`. |
| “Annotation ở bound của `T` tự xuất hiện ở `T[]`.” | Bound annotation và annotation của lần sử dụng `T` là các vị trí khác nhau. |
| “Đọc `field.getDeclaredAnnotations()` là thấy annotation trên `[]`.” | Cần `field.getAnnotatedType()` và duyệt node mảng. |
| “`getAnnotation()` trên một chiều tìm xuyên mọi chiều còn lại.” | Chỉ hỏi node hiện tại; phải đệ quy qua component. |
| “Không có annotation trong kết quả tức kiểu mảng không được annotation.” | Có thể đang ở sai node hoặc annotation không có retention runtime. |
| “Type-use annotation sẽ được JVM tự động thực thi để validate.” | Reflection chỉ cung cấp metadata; mã ứng dụng phải triển khai quy tắc nghiệp vụ. |

## 11. Mẫu duyệt mảng dùng trong ứng dụng

Một tiện ích **chỉ duyệt đường mảng**, dùng cho mọi trường mảng có thể có annotation ở từng chiều:

~~~java
static void visitArray(AnnotatedType type) {
    int dimension = 0;
    while (type instanceof AnnotatedArrayType array) {
        // Ở đây đọc annotation của chiều mảng hiện tại.
        // Ví dụ: type.getAnnotations(), type.getType().getTypeName()
        dimension++;
        type = array.getAnnotatedGenericComponentType();
    }

    // Đã tới loại phần tử, vẫn có thể có annotation riêng.
    // Nếu là AnnotatedParameterizedType, có thể tiếp tục duyệt generics.
}
~~~

Đây là method minh họa trong một lớp có import `java.lang.reflect.*`; `dimension` đang biểu thị số mức mảng đã đi qua, không phải chỉ số chiều quy ước của một ứng dụng cụ thể.

Khi thiết kế schema/validator:

1. Lấy `Field.getAnnotatedType()` hoặc API tương đương cho method parameter, return type, record component.
2. Nếu nút là `AnnotatedArrayType`, lấy annotation tại **nút chiều mảng** rồi đi xuống `getAnnotatedGenericComponentType()`.
3. Nếu nút là `AnnotatedParameterizedType`, đi vào `getAnnotatedActualTypeArguments()` để kiểm tra mảng nằm trong generic argument.
4. Nếu nút là `AnnotatedWildcardType` hoặc `AnnotatedTypeVariable`, duyệt bounds đúng API.
5. Tách phần đọc metadata khỏi phần **đánh giá dữ liệu runtime**. Type-use annotation không tự kiểm tra nội dung mảng.
6. Kiểm tra `instanceof` trước khi ép kiểu, và không đánh đồng `Type` nền với `AnnotatedType`.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `@A String @B [] @C [] matrix` chứa annotation tại những vị trí nào?  
`@B` ở chiều mảng ngoài `String[][]`; `@C` ở chiều trong `String[]`; `@A` ở kiểu phần tử `String`.

**Câu 2.** `field.getAnnotatedType().getAnnotation(A.class)` không thấy `@A` thì có nghĩa không có annotation nào trên các chiều mảng?  
**Không.** Có thể annotation ở node con, phải đi theo `getAnnotatedGenericComponentType()`.

**Câu 3.** `T[]` với `T` là type parameter có `getType()` nền thường thuộc loại nào?  
**`GenericArrayType`**. Nhưng nút annotated root vẫn có thể là `AnnotatedArrayType`.

**Câu 4.** `List<String[]>` có root là `AnnotatedArrayType` không?  
**Không.** Root là `AnnotatedParameterizedType`; đi vào type argument mới gặp `AnnotatedArrayType`.

**Câu 5.** `List<String>[]` có root là `AnnotatedArrayType` không?  
**Có.** Đây là mảng của danh sách; component là parameterized type.

**Câu 6.** `Class.getComponentType()` và `AnnotatedArrayType.getAnnotatedGenericComponentType()` có hoán đổi được khi cần annotation mỗi chiều?  
**Không.** API `Class` không giữ annotation type-use của component; API `AnnotatedArrayType` có thể giữ được.

**Câu 7.** Một annotation có `@Target(TYPE_USE)` nhưng `@Retention(CLASS)` có đọc bằng `AnnotatedType.getAnnotation()` tại runtime không?  
**Không qua Reflection runtime thông thường.** Cần `RUNTIME`.

**Kết luận:** `AnnotatedArrayType` biểu diễn **từng mức của kiểu mảng đã được annotation**. Gọi `getAnnotation()` ở từng node, sau đó dùng `getAnnotatedGenericComponentType()` để đi từ chiều ngoài vào chiều trong và tới kiểu phần tử. Nhờ vậy không làm mất annotation khi phân tích mảng nhiều chiều, mảng generic hoặc mảng nằm trong generic argument.

### Tài liệu chính thức

- [JDK 17 — `AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html)
- [JDK 17 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [JDK 17 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [JDK 17 — `GenericArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html)
- [JDK 17 — `Field.getAnnotatedType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#getAnnotatedType())
- [JLS 17 §10.1 — Array Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.1)
- [JLS 17 §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4)
