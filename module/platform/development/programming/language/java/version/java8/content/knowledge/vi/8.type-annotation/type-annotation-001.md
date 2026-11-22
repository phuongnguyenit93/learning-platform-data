# Annotation trên vị trí sử dụng kiểu (Type-use annotations) trong Java 8

## 1. Khái niệm

Từ Java 8, **type-use annotation** cho phép đặt annotation lên **một lần sử dụng kiểu** (*type context*), bên cạnh kiểu annotation truyền thống đánh dấu một **khai báo**. Cơ chế này xuất phát từ JSR 308 và **vẫn còn áp dụng trong Java hiện đại**. Nó hỗ trợ mô tả bổ sung cho kiểu field, parameter, return, generic argument, wildcard bound, array component/level, cast và các vị trí kiểu khác. Không dùng API đã lỗi thời để triển khai tính năng này.

Ví dụ, giả sử đã khai báo `@Mark` với `@Target(TYPE_USE)`:

```java
@Mark("outer") List<String> first;
List<@Mark("element") String> second;
```

Hai dòng này là **field minh họa trong class**, có import `List`. Dòng đầu đánh dấu kiểu **List**; dòng sau đánh dấu kiểu **String được dùng làm generic argument**. Đó là hai vị trí annotation khác nhau dù cả hai field vẫn là `List<String>` theo generic type system mặc định.

Sau bài học, bạn có thể:

- Phân biệt declaration annotation với type-use annotation.
- Tự định nghĩa annotation bằng `@Target(ElementType.TYPE_USE)`, `TYPE_PARAMETER` và `@Retention`.
- Đặt marker đúng vị trí trong generic, wildcard, array, return/parameter type, cast, `implements` và `extends`.
- Đọc metadata bằng `AnnotatedType` và các API reflection Java 8.
- Hiểu vì sao annotation tự định nghĩa không tự làm `javac` kiểm tra nullness/taint.
- Xác định giới hạn retention, type erasure, reflection và các sai lầm phổ biến khi thiết kế contract thư viện.

## 2. Declaration annotation và type annotation khác nhau

Một annotation dành cho khai báo field:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface FieldTag { }

class Example {
    @FieldTag String name;
}
```

`@FieldTag` gắn với **khai báo field `name`**, vì `@Target(FIELD)`. Nó không được phép dùng làm `List<@FieldTag String>`: generic type argument không phải một field declaration.

Một annotation dành cho lần dùng kiểu:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.TYPE_USE)
@interface TypeTag { }

class Example {
    @TypeTag String name;
    List<@TypeTag String> names;
}
```

Trong ví dụ thứ hai, `TypeTag` đánh dấu **kiểu String**, có thể là kiểu field hoặc type argument. JLS quy định rằng ở một số vị trí cú pháp, annotation có thể áp dụng lên declaration, lên type-use hoặc **cả hai** tùy `@Target`. Do đó, khi sử dụng reflection:

- `Field.getAnnotation(X.class)` tra annotation trên **declaration**.
- `Field.getAnnotatedType().getAnnotation(X.class)` tra annotation trên **type-use của field**.
- Hai truy vấn không thể tùy tiện thay thế nhau.

Đây là khác biệt **vị trí metadata**, không phải một kiểu generic mới. `List<@TypeTag String>` không tự trở thành một runtime class khác `List<String>` và Java không tự kiểm tra dữ liệu dựa trên chuỗi `TypeTag`.

## 3. Khai báo type-use annotation đúng cách

Một định nghĩa dễ sử dụng cho ví dụ học tập:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE_USE, ElementType.TYPE_PARAMETER})
@interface Mark {
    String value();
}
```

Vai trò:

- **`TYPE_USE`** cho phép annotation trong các **type context**: type argument `<String>`, return/parameter type, array level, cast, wildcard bound và các vị trí type-use khác. Theo Javadoc/JLS, target này còn bao phủ một số declaration context, gồm class/interface declaration và type-parameter declaration.
- **`TYPE_PARAMETER`** cho phép đánh dấu **khai báo type parameter** như `T` trong `class Box<@Mark("T") T>`. Điều này khác việc đánh dấu `String` ở lần sử dụng `Box<@Mark("arg") String>`.
- **`TYPE`** chủ yếu dùng cho **khai báo class/interface/enum/annotation type**; không thay thế `TYPE_USE` nếu muốn annotate `List<@X String>`.
- **`FIELD`**, **`METHOD`**, **`PARAMETER`** nhắm vào declaration context tương ứng. Chúng không đồng nghĩa với kiểu của field/method/parameter.
- **`@Retention(RUNTIME)`** làm annotation có thể truy cập được từ runtime reflection ở những vị trí được API hỗ trợ.

Có thể dùng `TYPE_USE` mà không khai báo riêng `TYPE_PARAMETER` trong những trường hợp ngôn ngữ cho phép; khai báo cả hai như trên giúp ý định của bài học rõ ràng. Không phải mọi annotation sản phẩm đều cần mọi target.

| Mục đích | Target |
| --- | --- |
| Khai báo field | `FIELD` |
| Khai báo method | `METHOD` |
| Khai báo formal parameter | `PARAMETER` |
| Khai báo generic type parameter `<T>` | `TYPE_PARAMETER` hoặc `TYPE_USE` theo JLS |
| Annotation trên `List<@X String>` | `TYPE_USE` |
| Annotation trên thành phần hoặc chiều mảng | `TYPE_USE` |
| Annotation trên cast, wildcard bound, `implements` | `TYPE_USE` |

## 4. Retention: metadata được giữ đến lúc nào?

`@Target` điều khiển nơi **được viết annotation**; `@Retention` điều khiển **metadata còn tồn tại tới đâu**.

| `RetentionPolicy` | Ý nghĩa | Truy vấn bằng Java runtime reflection? |
| --- | --- | --- |
| `SOURCE` | Annotation phục vụ source tools hoặc annotation processing; không ghi vào class file | Không |
| `CLASS` | Annotation được ghi vào class file theo hợp đồng Java, nhưng không được phản chiếu như RUNTIME | Không |
| `RUNTIME` | Annotation có thể được đọc ở runtime qua API reflection phù hợp | Có |

**Retention mặc định là `CLASS`**, nếu không có `@Retention`. Đây là lỗi rất thường gặp: người viết tạo annotation `@Target(TYPE_USE)`, rồi gọi `Field.getAnnotatedType().getAnnotation(...)` mà không thấy gì. Nguyên nhân có thể là annotation không có `RUNTIME` retention, không phải tính năng type-use không hoạt động.

Ví dụ metadata chỉ cần ở class file:

```java
@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE_USE)
@interface BuildMark { }
```

Đây là annotation declaration minh họa có import tương ứng. Nếu cần static analyzer đọc class file, `CLASS` có thể phù hợp. Nếu một **framework chạy trong JVM** phải truy cập marker, cần `RUNTIME` (và framework phải dùng API đúng).

Retention không tự thực hiện validation, và `RUNTIME` cũng không biến annotation thành một rule của `javac`.

## 5. Những vị trí type-use cần thành thạo

### 5.1. Field, local và parameter type

```java
class Sample {
    @Mark("field-type") String name;

    void rename(@Mark("input-type") String value) {
        @Mark("local-type") String cleaned = value.trim();
        name = cleaned;
    }
}
```

Đây là class minh họa, giả sử `Mark` đã được định nghĩa. Cả ba annotation nói về **kiểu được sử dụng**, không tự động về annotation khai báo field/method/parameter. Type-use annotation trên local variable hoặc cast trong method body có thể được giữ dưới dạng class-file metadata, nhưng core reflection không có API tổng quát để duyệt mọi expression trong một method; static analyzer hoặc bytecode tooling có thể phải xử lý.

### 5.2. Type parameter so với type argument

```java
class Box<@Mark("decl-T") T> {
    java.util.List<@Mark("element-String") String> values;
}
```

`@Mark("decl-T")` thuộc về **khai báo T**. `@Mark("element-String")` thuộc về **lần sử dụng String** làm type argument. Tương tự, một vị trí client `Box<@Mark("client-arg") String>` mô tả lần dùng kiểu ở client, không sửa định nghĩa `Box<T>`.

Với generic lồng nhau:

```java
java.util.Map<@Mark("key") String,
        java.util.List<@Mark("item") Integer>> table;
```

Đây là một field minh họa. Marker ở key và item nằm tại **hai nút khác nhau** của type tree. Khi đọc, cần theo type-argument path; không đọc annotation ở outer `Map` rồi kết luận mọi argument đều không annotate.

### 5.3. Wildcard bound

```java
java.util.List<? extends @Mark("upper") Number> numbers;
java.util.List<? super @Mark("lower") Integer> integers;
```

Marker ở **bound type**. Quy tắc generic của Java vẫn giữ nguyên: `? extends Number` được dùng khi đọc Number như producer; `? super Integer` cho phép nhận Integer như consumer theo các giới hạn bình thường. `AnnotatedWildcardType` có phương thức để đi vào upper/lower annotated bounds.

### 5.4. Mảng: annotation trước kiểu khác annotation ở dấu `[]`

```java
@Mark("component") String[] names;
String @Mark("array") [] labels;
String @Mark("outer") [] @Mark("inner") [] matrix;
```

Tất cả là field minh họa. Trong type annotation:

- `@Mark String[]`: marker trên **kiểu thành phần `String`**.
- `String @Mark []`: marker trên **array type `String[]`**.
- `String @Mark [] @Mark []`: đánh dấu **các cấp mảng khác nhau** trong `String[][]`.

Nếu áp dụng nullness analysis, hai khẳng định "array reference không null" và "mỗi phần tử String không null" là **hai contract khác nhau**. Đặt annotation trước `String` thay vì gần dấu `[]` có thể khiến checker hiểu sai ý định.

Reflection hỗ trợ duyệt array qua `AnnotatedArrayType` và `getAnnotatedGenericComponentType()`. Với mảng nhiều chiều, có thể tiếp tục duyệt thành phần ở mỗi cấp.

### 5.5. Return, parameter và kế thừa kiểu

```java
static @Mark("return") String normalize(
        @Mark("parameter") String value) {
    return value.trim();
}
```

Đây là method minh họa nằm trong class. Marker đầu thuộc **return type**, marker sau thuộc **formal parameter type**. Java core reflection cung cấp `getAnnotatedReturnType()` và `getAnnotatedParameterTypes()` để đọc những vị trí này.

Với implements:

```java
class Job implements @Mark("interface") Runnable {
    @Override public void run() { }
}
```

Đây là class minh họa hợp lệ. Marker được đặt ở **lần sử dụng kiểu Runnable trong implements**, không phải trên class declaration `Runnable` trong JDK. Có thể dùng `Class.getAnnotatedInterfaces()` để đọc. Type-use annotation cũng có thể đặt ở superclass type trong `extends`.

### 5.6. Cast và biểu thức tạo object

```java
Object value = "text";
String text = (@Mark("cast") String) value;
```

Đây là các statement minh họa trong method. Marker thuộc **kiểu đích của cast**; phép cast vẫn bị kiểm tra theo quy tắc JVM bình thường. Nếu object không phải String, marker không ngăn `ClassCastException`. Một số type context của `new` và kiểu exception cũng có thể annotate theo cú pháp và ràng buộc JLS.

**Không nhầm metadata type-use với cơ chế bảo vệ dữ liệu tự động.**

## 6. Đọc type-use annotations bằng Reflection

Java reflection có **`AnnotatedType`**, biểu diễn một lần sử dụng kiểu có thể mang annotation:

| API | Đọc metadata nào? |
| --- | --- |
| `Field.getAnnotatedType()` | Kiểu của field |
| `Method.getAnnotatedReturnType()` | Kiểu trả về |
| `Executable.getAnnotatedParameterTypes()` | Các kiểu tham số method/constructor |
| `Class.getAnnotatedSuperclass()` | Kiểu superclass dùng ở khai báo |
| `Class.getAnnotatedInterfaces()` | Các kiểu interface dùng ở khai báo |
| `TypeVariable.getAnnotatedBounds()` | Các bound của type variable |
| `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` | Các type arguments generic |
| `AnnotatedArrayType.getAnnotatedGenericComponentType()` | Component của array |
| `AnnotatedWildcardType.getAnnotatedUpperBounds()` | Upper bounds của wildcard |
| `AnnotatedWildcardType.getAnnotatedLowerBounds()` | Lower bounds của wildcard |
| `AnnotatedType.getAnnotation(Mark.class)` | Annotation tại **nút type-use hiện tại** |

Một field `List<@Mark("item") String>` không nhất thiết có marker trên **nút ngoài List**. Nó nằm ở `getAnnotatedActualTypeArguments()[0]`. Reflection ở mức kiểu phải **đi theo type tree**, không chỉ gọi `getAnnotation` trên nút gốc.

So sánh:

```java
field.getAnnotation(Column.class); // Annotation trên khai báo field.
field.getAnnotatedType();          // Metadata trên kiểu của field.
field.getGenericType();            // Kiểu generic; không tự diễn đạt type-use markers.
```

Các dòng trên là minh họa, giả sử biến `field` và annotation `Column` đã tồn tại. Một annotation có thể được cấu hình target cho cả declaration và type-use; trong trường hợp đó cùng vị trí nguồn có thể được phản ánh qua những API khác nhau theo JLS.

## 7. Chương trình Java chạy độc lập: generic, array, implements và reflection

Tạo tệp **`TypeUseDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

public class TypeUseDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE_USE, ElementType.TYPE_PARAMETER})
    @interface Mark {
        String value();
    }

    static class Box<@Mark("type-parameter") T> {
        @Mark("list-type") List<@Mark("element-type") String> items;
        String @Mark("array-type") [] labels;

        Box(List<String> items) {
            this.items = items;
            this.labels = new String[]{"a", "b"};
        }
    }

    static class Job implements @Mark("interface-type") Runnable {
        @Override public void run() { }
    }

    static @Mark("return-type") String echo(
            @Mark("parameter-type") String text) {
        return text;
    }

    static String mark(AnnotatedType type) {
        Mark mark = type.getAnnotation(Mark.class);
        return mark == null ? "(none)" : mark.value();
    }

    public static void main(String[] args) throws Exception {
        Field items = Box.class.getDeclaredField("items");
        AnnotatedParameterizedType parameterized =
                (AnnotatedParameterizedType) items.getAnnotatedType();
        System.out.println("outer=" + mark(parameterized));
        System.out.println("element=" +
                mark(parameterized.getAnnotatedActualTypeArguments()[0]));

        AnnotatedArrayType array = (AnnotatedArrayType)
                Box.class.getDeclaredField("labels").getAnnotatedType();
        System.out.println("array=" + mark(array));

        System.out.println("typeParameter=" +
                Box.class.getTypeParameters()[0].getAnnotation(Mark.class).value());
        System.out.println("implements=" +
                mark(Job.class.getAnnotatedInterfaces()[0]));

        Method echo = TypeUseDemo.class.getDeclaredMethod("echo", String.class);
        System.out.println("return=" + mark(echo.getAnnotatedReturnType()));
        System.out.println("parameter=" + mark(echo.getAnnotatedParameterTypes()[0]));

        Box<String> box = new Box<>(Arrays.asList("alpha", "beta"));
        System.out.println("values=" + box.items + ", " + Arrays.toString(box.labels));
        System.out.println("echo=" + echo("ok"));
    }
}
```

Biên dịch/chạy trên JDK 17+; code chỉ dùng API từ Java 8:

```bash
javac TypeUseDemo.java
java TypeUseDemo
```

Stdout chính xác:

```text
outer=list-type
element=element-type
array=array-type
typeParameter=type-parameter
implements=interface-type
return=return-type
parameter=parameter-type
values=[alpha, beta], [a, b]
echo=ok
```

**Giải thích từng kết quả:**

1. `outer=list-type`: `getAnnotatedType()` trên field `items` là `AnnotatedParameterizedType` ở **nút List bên ngoài**, nơi có `@Mark("list-type")`.
2. `element=element-type`: `getAnnotatedActualTypeArguments()[0]` truy cập type argument `String`, nơi có marker riêng.
3. `array=array-type`: `String @Mark("array-type") []` đặt marker ở array level, được thấy qua `AnnotatedArrayType`.
4. `typeParameter=type-parameter`: `Box.class.getTypeParameters()[0]` là khai báo `T` có annotation được giữ tới runtime.
5. `implements=interface-type`: `Job.class.getAnnotatedInterfaces()[0]` là type-use `Runnable` trong mệnh đề implements.
6. `return=return-type` và `parameter=parameter-type`: hai đường đi riêng đến return type và parameter type của `echo`.
7. `values=...` và `echo=ok`: code xử lý danh sách và chuỗi bình thường. `Mark` chỉ giúp reflection đọc metadata, không thay đổi cơ chế của `List` hay `String`.

Đây là **chương trình độc lập**, không dựa vào công cụ bên ngoài. Nó kiểm chứng nơi metadata nằm và cách đọc đúng ở runtime. Trong framework thực tế, hãy kiểm tra `instanceof AnnotatedParameterizedType` hoặc loại subtype tương ứng trước khi cast để tránh `ClassCastException` nếu signature khác kỳ vọng.

## 8. Type erasure không làm mọi metadata generic biến mất

Java generic sử dụng **type erasure**, nhưng class file vẫn có thể lưu generic signature và type-use annotation metadata ở các vị trí phù hợp. Cần phân biệt:

- **Runtime class của object**, ví dụ `java.util.ArrayList`.
- **Kiểu generic được khai báo ở field/method**, ví dụ `List<String>`.
- **Annotation gắn với việc dùng kiểu trong signature**, ví dụ `List<@Mark String>`.

Một instance của String **không tự mang** marker của từng chỗ String từng được tham chiếu. Nhưng một framework biết **field/method signature** có thể đọc marker `RUNTIME` tại đúng vị trí qua `AnnotatedType`.

Java core reflection có phạm vi nhất định: field type, method return/parameter types, superclass/interfaces, generic type arguments và annotated bounds có API rõ ràng. Metadata type-use trong **method body** (cast, local variable) có thể nằm trong class file nhưng không có đường đi phản chiếu thống nhất qua `Method` cho mọi biểu thức. Một bytecode analyzer hoặc source analyzer có thể cần thiết để kiểm tra chúng.

Với `CLASS` retention, một công cụ class-file có thể đọc metadata theo thiết kế, nhưng Java reflection runtime không được yêu cầu công bố annotation đó.

## 9. Type-use annotation và static analysis: nullness, taint, immutability

Ví dụ một annotation gắn trên type:

```java
@Target(ElementType.TYPE_USE)
@interface NonNull { }
```

Đây là ví dụ declaration cần import `ElementType` và `Target`. Nếu chỉ định nghĩa `@NonNull` như vậy, `javac` thông thường **không tự động cấm**:

```java
@NonNull String name = null;
```

Về syntactic annotation target, dòng trên có thể là một khai báo hợp lệ trong method/class; **nullness rule chưa tồn tại** nếu không có analyzer hiểu `NonNull`.

Để có bảo đảm có ích:

1. **Định nghĩa semantics:** non-null áp dụng cho array reference hay từng element, generic argument hay collection object, input hay return?
2. **Chọn checker/framework:** mỗi công cụ có bộ annotation và rules riêng; `@NonNull` tự đặt tên chưa chắc tương thích với tool.
3. **Tích hợp build/CI:** đặt chế độ kiểm tra và thử **negative test** để xác nhận vi phạm thực sự bị phát hiện.
4. **Kiểm tra dữ liệu ngoài hệ kiểu:** database, network, reflection, deserialization vẫn có thể mang dữ liệu không hợp lệ; dùng runtime validation tại boundary khi cần.
5. **Cập nhật API có kỷ luật:** đổi type annotation trong public method dù không đổi Java descriptor vẫn có thể ảnh hưởng client được static checker kiểm tra.

Các type-use annotation trong Java hiện đại có thể diễn đạt nullness, taint/trust, ownership, đơn vị đo hoặc các qualifier khác, nhưng **ý nghĩa cụ thể không phải một luật built-in của Java**. Cần tài liệu và implementation tương ứng.

## 10. Những lỗi thường gặp

| Lỗi | Cách hiểu đúng |
| --- | --- |
| `@Target(FIELD)` rồi viết `List<@X String>` | Type argument cần `TYPE_USE`, không phải field declaration target. |
| Dùng `TYPE` thay `TYPE_USE` | `TYPE` chủ yếu dùng cho khai báo kiểu, không bao phủ mọi type context. |
| Quên `@Retention(RUNTIME)` khi muốn đọc reflection | Mặc định `CLASS`; runtime reflection cần retention phù hợp. |
| Chỉ gọi `field.getAnnotation(X.class)` | Với kiểu của field, dùng `field.getAnnotatedType()`; với type argument tiếp tục duyệt tree. |
| `getAnnotatedType().getAnnotation(X.class)` trả null ở `List<@X String>` | Marker có thể nằm ở **nút `String`**, không phải nút `List`. |
| Nhầm `@X String[]` với `String @X []` | Đánh dấu component type khác array level. |
| Nhầm `<@X T>` với `<@X String>` | Type-parameter declaration khác type-argument use. |
| Mong `@NonNull` tự thay hệ kiểu Java | Annotation tự khai báo không tự enforce; phải tích hợp checker/validation. |
| Nghĩ `List<@X String>` là runtime class khác `List<String>` | Type-use marker là metadata, không tạo specialized JVM class. |
| Mong mọi marker trong method body đều đọc được bằng core reflection | Một số vị trí cần source/bytecode analyzer. |
| Dùng marker làm policy nhưng không tài liệu semantics | Caller và tool có thể hiểu khác; phải định nghĩa contract rõ. |
| Thay annotation public API mà không kiểm thử client | Analyzer có thể báo lỗi mới dù Java signature không đổi. |

## 11. Bài tập có đáp án

**Câu 1.** Dùng target nào để annotate `String` trong `List<@X String>`?  
**Đáp án:** `TYPE_USE`, vì đây là generic type argument.

**Câu 2.** `class C<@X T>` gắn marker ở đâu?  
**Đáp án:** Trên **khai báo type parameter T**, không phải trên một type argument khi client dùng C.

**Câu 3.** `@X String[] a` và `String @X [] a` là cùng vị trí?  
**Không.** Một marker trên component String, một marker trên array type.

**Câu 4.** Nếu annotation không có `@Retention`, Java reflection runtime có bảo đảm thấy không?  
**Không.** Mặc định là CLASS, không phải RUNTIME.

**Câu 5.** Để lấy marker `@X` ở `List<@X String>`, cần làm gì?  
**Đáp án:** Truy cập `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]` và đọc annotation tại nút con.

**Câu 6.** `@NonNull String s = null;` có tự động lỗi compiler không?  
**Không**, nếu chỉ tự tạo annotation mà không tích hợp một checker hiểu semantics.

**Câu 7.** Đọc annotation trên kiểu trả về của method bằng API nào?  
**Đáp án:** `Method.getAnnotatedReturnType()`.

**Câu 8.** Annotation trong `implements @X Runnable` có thể đọc bằng API nào?  
**Đáp án:** `Class.getAnnotatedInterfaces()`.

**Câu 9.** `List<@X String>` có là một JVM generic specialization độc lập không?  
**Không.** Annotation không làm generic trở thành reified class mới.

**Câu 10.** Đổi marker nullable thành non-null trong public API có thể ảnh hưởng client không?  
**Có**, nếu static analyzer hoặc framework dùng marker như một phần contract.

## 12. Checklist triển khai và tổng kết

Khi thiết kế annotation, hãy xác định **đang đánh dấu declaration hay type-use**, đặt đúng `@Target`, đúng **type path**, chọn retention đúng, tài liệu semantics, xác minh bằng compilation/reflection và tích hợp checker nếu thực sự cần ràng buộc dữ liệu. Với mảng và generic lồng nhau, kiểm tra riêng từng mức. Với public API, xem marker là một phần của hợp đồng công cụ và kiểm thử khi thay đổi phiên bản.

**Tóm lại:** type-use annotations mở rộng khả năng mô tả lần sử dụng kiểu trong Java 8, và vẫn được dùng trong Java hiện đại. `TYPE_USE` cho phép đánh dấu type contexts; `TYPE_PARAMETER` mô tả khai báo generic parameter; `AnnotatedType` giúp đọc metadata runtime phù hợp. Annotation không tự động ép buộc non-null hoặc làm thay đổi kiểu Java cơ bản: hiệu lực của ràng buộc phụ thuộc **checker/framework thực sự diễn giải annotation**.

**Tài liệu chính thức:**

- [JLS §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.7.4).
- [JLS §4.11 — Where Types Are Used](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.11).
- [`ElementType` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/ElementType.html).
- [`AnnotatedType` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedType.html).
- [`AnnotatedParameterizedType` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).
- [`AnnotatedArrayType` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html).
