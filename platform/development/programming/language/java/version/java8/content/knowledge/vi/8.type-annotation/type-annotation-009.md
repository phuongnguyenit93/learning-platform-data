# AnnotatedType và cấu trúc kiểu có annotation trong Java

## Mục tiêu học tập

Trong Java, `java.lang.reflect.AnnotatedType` biểu diễn **một vị trí sử dụng kiểu có thể mang annotation**, chứ không chỉ tên kiểu đơn giản. Từ Java 8, *type annotations* cho phép đặt metadata ở nhiều tầng của một kiểu, chẳng hạn `List<@Tag String>`, `Map<String, List<@Tag Integer>>`, `String @Tag []` hoặc `List<? extends @Tag Number>`. Reflection vì vậy cần một **cây cấu trúc các annotated types**, thay vì chỉ một chuỗi tên kiểu.

Bài này tập trung vào các API đang được Java hiện đại hỗ trợ:

- `AnnotatedType` và mối quan hệ với `Type`, `AnnotatedElement`.
- `AnnotatedParameterizedType` cho type arguments của generic.
- `AnnotatedArrayType` cho kiểu mảng và từng cấp component.
- `AnnotatedWildcardType` cho `? extends` / `? super`.
- `AnnotatedTypeVariable` và `TypeVariable<?>` cho vị trí sử dụng type variable so với khai báo type parameter.
- `getAnnotatedOwnerType()` cho owner của kiểu lồng nhau trong những ngữ cảnh phù hợp.
- `Field`, `Method`, `Constructor`, `Class` và các điểm vào reflection.
- `@Target(TYPE_USE)`, `@Retention(RUNTIME)`, những giới hạn của type erasure và việc annotation **không tự thi hành validation**.

Kết thúc, bạn sẽ tự viết được code phản chiếu đi qua nhiều tầng của kiểu generic; kiểm chứng các annotation xuất hiện đúng vị trí và chọn API thích hợp, thay vì đọc sai annotation ở declaration.

## 1. Từ Type đến AnnotatedType

Java có API `java.lang.reflect.Type` để biểu diễn một kiểu trong hệ thống generic reflection. Những đại diện thường gặp là:

| `Type` | Ví dụ cấu trúc |
| --- | --- |
| `Class<?>` | `String`, `String[]`, `int` |
| `ParameterizedType` | `List<String>`, `Map<String, Integer>` |
| `TypeVariable<?>` | `T` trong `class Box<T>` |
| `WildcardType` | `? extends Number` |
| `GenericArrayType` | `T[]` trong generic declaration |

`Type` trả lời câu hỏi: **kiểu ở vị trí này được cấu tạo như thế nào?** Nhưng nếu khai báo:

~~~java
java.util.List<@Mark String> labels;
~~~

`List<String>` cho biết cấu trúc generic, còn `@Mark` trên **`String` là metadata của type-use**. Chỉ đọc `field.getGenericType()` không đủ để truy cập annotation đó qua API annotated-type.

`AnnotatedType` bổ sung hai việc quan trọng:

1. `getType()` trả về đối tượng `Type` biểu diễn **kiểu Java nền tảng** ở vị trí đó.
2. Các phương thức kế thừa từ `AnnotatedElement` như `getAnnotation(...)`, `getAnnotations()`, `getDeclaredAnnotations()` truy xuất **annotation trên đúng vị trí type-use hiện tại** (nếu metadata được giữ lại phù hợp).

Ví dụ cách lấy điểm vào:

~~~java
java.lang.reflect.Field field =
        Example.class.getDeclaredField("labels");

java.lang.reflect.Type genericType =
        field.getGenericType();

java.lang.reflect.AnnotatedType annotatedType =
        field.getAnnotatedType();
~~~

Đây là **mã minh họa** giả định class `Example` có field `labels` và có ngữ cảnh xử lý `ReflectiveOperationException`. `genericType` và `annotatedType` là hai góc nhìn liên quan đến **cùng vị trí khai báo**, không phải hai kiểu của hai biến khác nhau.

**Đừng nhầm:** Annotation type-use không mặc nhiên trở thành một loại Java mới. Với hệ thống kiểu chuẩn, `List<@Mark String>` vẫn có cấu trúc generic cơ sở của `List<String>`; ý nghĩa bổ sung của marker cần được công cụ phân tích hoặc ứng dụng biết cách đọc.

## 2. @Target và @Retention: hai điều kiện độc lập

Để annotation xuất hiện trên một vị trí sử dụng kiểu, nó cần có target tương ứng:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Mark {
    String value();
}
~~~

- `TYPE_USE` cho phép sử dụng `@Mark` ở những vị trí chú thích kiểu, gồm type arguments, bounds, kiểu field, return type, parameter type, mảng, wildcard và các vị trí khác mà JLS cho phép.
- `RUNTIME` giữ annotation trong class file và làm nó có thể truy cập từ Java reflection tại những vị trí được API hỗ trợ.
- `Mark.value()` là element mang một chuỗi giúp ví dụ phân biệt các tầng metadata.

Nếu **không** viết `@Retention`, mặc định là `RetentionPolicy.CLASS`. Lúc đó annotation thường vẫn có trong class file nhưng **không** được truy cập qua reflection runtime chuẩn. `RetentionPolicy.SOURCE` không giữ annotation trong class file.

Một annotation được target `TYPE_PARAMETER` chỉ tập trung vào **declaration của generic type parameter** như `<@DeclarationMark T>`; nó không thay thế `TYPE_USE` nếu bạn muốn viết `List<@Mark String>`. Lưu ý theo JLS, target `TYPE_USE` còn bao gồm một số ngữ cảnh khai báo type parameter; khi viết bộ phân tích, vẫn cần phân biệt **annotation ở declaration** và **annotation ở một lần sử dụng kiểu**.

**Quan trọng:** Java SE không tự kiểm tra nghiệp vụ chỉ bởi vì marker tên `@NonNull`, `@Positive` hay `@Safe` có mặt. `@Target` bảo đảm tính hợp lệ của vị trí cú pháp; `@Retention` quyết định khả năng lưu/đọc metadata; semantic checker hoặc runtime code mới thực sự áp dụng quy tắc.

## 3. Cây AnnotatedType khác chuỗi tên kiểu

Xét:

~~~java
java.util.Map<
        @Mark("key") String,
        java.util.List<@Mark("element") Integer>
> counts;
~~~

Về mặt cấu trúc có thể hình dung:

~~~text
AnnotatedParameterizedType: Map<String, List<Integer>>
  ├── annotated argument[0]: String
  │     └── @Mark("key")
  └── annotated argument[1]: List<Integer>
        └── annotated argument[0]: Integer
              └── @Mark("element")
~~~

Metadata ở `String` **không tự xuất hiện** khi bạn gọi `getAnnotations()` trên node `Map`. Phải đi tới `getAnnotatedActualTypeArguments()[0]` mới đọc được annotation `"key"`.

Tương tự, `@Mark("element")` nằm ở `Integer` bên trong `List`, nên cần:
1. Lấy annotated type của field `counts`.
2. Cast node gốc sang `AnnotatedParameterizedType`.
3. Chọn type argument thứ hai là `List<Integer>`.
4. Cast node `List` sang `AnnotatedParameterizedType`.
5. Chọn annotated type argument đầu tiên là `Integer`.
6. Đọc `getAnnotation(Mark.class)` tại node `Integer`.

**Không nối chuỗi từ `getType().getTypeName()` rồi tìm `@Mark` trong string.** Annotation có vị trí riêng trong cấu trúc phản chiếu; việc parse tên kiểu bằng regex thường làm mất thông tin trên wildcard, array dimension và owner type.

## 4. Interface AnnotatedType và những phương thức căn bản

`AnnotatedType` nằm trong `java.lang.reflect` và mở rộng `AnnotatedElement`. Các điểm vào thiết yếu:

~~~java
AnnotatedType type = field.getAnnotatedType();

Type base = type.getType();
Mark mark = type.getAnnotation(Mark.class);
Annotation[] annotations = type.getAnnotations();
~~~

Các dòng trên là **mã minh họa** có imports cần thiết. Ý nghĩa:

- `getType()`: trả kiểu cơ sở là `Type`; với generic type thường là `ParameterizedType`.
- `getAnnotation(Mark.class)`: lấy marker **ở node hiện tại** hoặc `null` nếu không có.
- `getAnnotations()`: liệt kê annotation của node theo hợp đồng `AnnotatedElement`, **không tự duyệt tất cả node con**.
- `getAnnotatedOwnerType()`: truy vấn annotated owner type khi cấu trúc kiểu có owner thích hợp; cần kiểm tra `null` trước.

`AnnotatedType` **không** là một instance của `Class<?>`. Một `AnnotatedType` đại diện **một lần sử dụng kiểu được mô tả trong khai báo**, còn `Class<?>` thường đại diện class/interface ở runtime.

Các subtype được chọn dựa vào hình dạng node, thay vì đoán từ annotation:

| Interface | Kiểu cấu trúc | API chuyên biệt |
| --- | --- | --- |
| `AnnotatedParameterizedType` | `List<String>`, `Map<K,V>` | `getAnnotatedActualTypeArguments()` |
| `AnnotatedArrayType` | `String[]`, `T[]` | `getAnnotatedGenericComponentType()` |
| `AnnotatedWildcardType` | `? extends Number`, `? super Integer` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `AnnotatedTypeVariable` | Sử dụng type variable `T` | `getAnnotatedBounds()` |
| `AnnotatedType` đơn giản | Kiểu như `String`, `Number`, primitive | `getType()`, đọc annotation hiện tại |

**Không phải mọi `AnnotatedType` là `AnnotatedParameterizedType`.** Ví dụ field `String text` có thể chỉ là node đơn giản, nên ép kiểu mù sẽ ném `ClassCastException`. Trong công cụ dùng chung, dùng `instanceof` kiểm tra trước mỗi cast.

## 5. AnnotatedParameterizedType: đi vào type arguments

Giả sử một field khai báo:

~~~java
java.util.List<@Mark("item") String> words;
~~~

Bạn có thể đọc annotation như sau:

~~~java
Field field = Example.class.getDeclaredField("words");

AnnotatedParameterizedType listType =
        (AnnotatedParameterizedType) field.getAnnotatedType();

AnnotatedType item =
        listType.getAnnotatedActualTypeArguments()[0];

Mark mark = item.getAnnotation(Mark.class);
System.out.println(mark.value()); // item
~~~

Đây là **đoạn minh họa** dùng class `Example` và các imports phù hợp. `getAnnotatedActualTypeArguments()` trả về mảng theo **thứ tự type arguments** trong khai báo. `List<E>` có một argument; `Map<K,V>` có hai.

Nếu annotation nằm ngay trên **kiểu danh sách bên ngoài**:

~~~java
@Mark("list") java.util.List<@Mark("item") String> words;
~~~

thì:
- `field.getAnnotatedType().getAnnotation(Mark.class)` nhận `"list"`.
- `listType.getAnnotatedActualTypeArguments()[0].getAnnotation(Mark.class)` nhận `"item"`.

Hai vị trí có ý nghĩa độc lập: metadata về **tham chiếu collection** không mặc nhiên giống metadata về **mỗi phần tử**. Khi áp dụng nullability checker, cần phân biệt ràng buộc “list không null” với “các element không null”, theo đúng quy ước của checker được sử dụng.

### Generic lồng nhiều tầng

Với `Map<String,List<@Mark Integer>>`, type argument thứ hai của `Map` lại là một `AnnotatedParameterizedType`. Duyệt **theo cấu trúc**, không dựa vào số lượng dấu `<` hoặc vị trí tên generic trong text.

Khi một API có nhiều tầng wrapper như `Optional<List<Map<String,Order>>>`, cách duyệt này cho phép xác định annotation thuộc **toàn bộ wrapper, type argument hay thành phần sâu hơn**. Mỗi tầng phải được đọc riêng.

## 6. AnnotatedArrayType: annotation trên component và dimension

Mảng tạo ra một điểm dễ nhầm: type annotation có thể đặt **trước component type** hoặc **trên dấu ngoặc mảng**.

~~~java
@Mark("component") String @Mark("array") [] labels;
~~~

Trong cấu trúc phản chiếu:

- Node mảng là `AnnotatedArrayType`; `getAnnotation(Mark.class)` trên node mảng có thể trả `"array"`.
- `getAnnotatedGenericComponentType()` trả node của component `String`; `getAnnotation(Mark.class)` trên component trả `"component"`.

Chúng là hai vị trí khác nhau. Nếu mảng nhiều chiều:

~~~java
String @Mark("outer") []
       @Mark("inner") [] matrix;
~~~

thì mỗi lần gọi `getAnnotatedGenericComponentType()` đi xuống **một cấp component**. Một node mảng nhiều chiều có thể dẫn tới node mảng còn lại, sau đó mới tới kiểu phần tử.

### So sánh với getGenericType()

~~~java
Type type = field.getGenericType();
AnnotatedType annotated = field.getAnnotatedType();
~~~

`type` vẫn có thể mô tả một `Class<?>` biểu diễn `String[]`; nhưng type-use annotations trên từng cấp không thể được suy ra từ tên class mảng. Dùng `AnnotatedArrayType` để duyệt cấu trúc **kèm annotation**.

### Hạn chế quan trọng

Mảng Java có thể có nhiều dimensions, nhưng không có “annotation tự động áp dụng cho mọi phần tử runtime”. Marker trên kiểu mảng hoặc component mô tả metadata của **type-use ở khai báo**, không đi qua từng ô mảng để thực hiện validation. Nếu ứng dụng cần kiểm tra nội dung, hãy thực thi checker phù hợp hoặc kiểm tra tại boundary.

## 7. AnnotatedWildcardType: ? extends và ? super

Wildcard trong generic cung cấp giới hạn kiểu:

~~~java
java.util.List<
        @Mark("wildcard") ? extends @Mark("upper") Number
> numbers;
~~~

Hai vị trí độc lập:

- `@Mark("wildcard")` nằm ngay ở **wildcard use** `?`.
- `@Mark("upper")` nằm trên **upper-bound type `Number`**.

Để đi vào chúng:

~~~java
AnnotatedParameterizedType listType =
        (AnnotatedParameterizedType) field.getAnnotatedType();

AnnotatedWildcardType wildcard =
        (AnnotatedWildcardType)
                listType.getAnnotatedActualTypeArguments()[0];

Mark onWildcard = wildcard.getAnnotation(Mark.class);
Mark onBound = wildcard.getAnnotatedUpperBounds()[0]
                       .getAnnotation(Mark.class);
~~~

Đối với `? super Integer`, dùng `getAnnotatedLowerBounds()` để tìm lower bound tường minh. Với `? extends Number`, dùng `getAnnotatedUpperBounds()`. Không giả định cả hai mảng đều có phần tử trong mọi cấu trúc. Với wildcard không có bound tường minh, Java vẫn có ngữ nghĩa upper bound mặc định `Object`, nhưng **không nên tự nhận định có annotation do người viết khai báo ở bound đó**.

### Wildcard khác type variable

- `? extends Number` là **wildcard**: một type argument với giới hạn.
- `T extends Number` trong `class Box<T extends Number>` là **type parameter declaration**.
- `T` được sử dụng làm kiểu field, return type hay type argument là **type-variable use**.

Phản chiếu các vị trí này qua các API khác nhau. Đừng ép `AnnotatedWildcardType` thành `AnnotatedTypeVariable` vì hai cấu trúc không đồng nhất.

## 8. AnnotatedTypeVariable và TypeVariable: dùng và khai báo T

Ví dụ:

~~~java
@Target(ElementType.TYPE_PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface DeclMark {
    String value();
}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface UseMark {
    String value();
}

class Box<
        @DeclMark("parameter") T
                extends @UseMark("bound") Number> {

    @UseMark("use-of-T") T current;
}
~~~

Ở đây có **ba vị trí**:

1. `@DeclMark("parameter")` đánh dấu **declaration của type parameter `T`**.
2. `@UseMark("bound")` đánh dấu **kiểu `Number` làm bound của `T`**.
3. `@UseMark("use-of-T")` đánh dấu **lần dùng type variable `T` làm kiểu field**.

Cách phản chiếu phù hợp:

~~~java
TypeVariable<?> tv = Box.class.getTypeParameters()[0];
DeclMark declaration = tv.getAnnotation(DeclMark.class);

AnnotatedType bound = tv.getAnnotatedBounds()[0];
UseMark onBound = bound.getAnnotation(UseMark.class);

Field field = Box.class.getDeclaredField("current");
AnnotatedType usedType = field.getAnnotatedType();
UseMark onUse = usedType.getAnnotation(UseMark.class);
~~~

`tv` đại diện **type parameter declaration**, còn `usedType` đại diện **type use tại field**. Khi type use là type variable, reflection cung cấp `AnnotatedTypeVariable` để truy cập thông tin các annotated bounds của type variable thông qua `getAnnotatedBounds()`.

**Điểm dễ sai:** Annotation trên declaration `<@DeclMark T>` không tự xuất hiện trên mọi lần dùng `T`. Ngược lại, annotation trên field `@UseMark T current` không tự gắn vào declaration `T`. Người dùng một checker phải hiểu rõ annotation được công bố ở đâu và nó áp dụng cho phạm vi nào.

## 9. getAnnotatedOwnerType(): kiểu thành viên lồng nhau

Một số kiểu có **owner type**, ví dụ inner class có quan hệ với enclosing class:

~~~java
class Outer<A> {
    class Inner<B> {
    }
}
~~~

Một vị trí sử dụng kiểu như `Outer<String>.Inner<Integer>` chứa cả phần **owner `Outer<String>`** và phần **member `Inner<Integer>`**. Trong Java 9+, `AnnotatedType.getAnnotatedOwnerType()` cho phép truy vấn annotated owner type khi cấu trúc có owner thích hợp.

Điều cần ghi nhớ:

- Một node có thể trả `null` nếu không có owner type.
- Owner type không giống type argument: `getAnnotatedActualTypeArguments()` của `Inner` trả các type arguments của thành phần được phản chiếu, trong khi `getAnnotatedOwnerType()` cho phép truy vết phần owner tương ứng.
- Với kiểu lồng sâu, owner có thể lại có owner khác. Một trình duyệt kiểu nên xử lý đệ quy và bảo vệ khỏi `null`.
- Không ép rằng **mọi nested type đều có owner metadata giống nhau** trong mọi ngữ cảnh; static nested class, member class và các dạng local/anonymous type có quy tắc ngôn ngữ khác nhau.

Ví dụ cách truy vấn an toàn:

~~~java
AnnotatedType member = field.getAnnotatedType();
AnnotatedType owner = member.getAnnotatedOwnerType();

if (owner != null) {
    System.out.println(owner.getType().getTypeName());
}
~~~

Đây là **mã minh họa** giả định `field` mô tả kiểu thành viên hợp lệ. `getAnnotatedOwnerType()` có trong các JDK hiện đại, nhưng **không thuộc mọi API Java 8 ban đầu**: khi phải biên dịch `--release 8`, hãy kiểm tra mức `@since` của phương thức này và chọn giải pháp tương thích.

## 10. Các entry point reflection cần biết

Không phải lúc nào bạn cũng bắt đầu từ `Field`. Một chương trình đọc type annotations có thể cần nhiều điểm vào:

| Nơi khai báo | Reflection API có annotated type | Truy vấn được |
| --- | --- | --- |
| Field | `Field.getAnnotatedType()` | Kiểu field |
| Method result | `Method.getAnnotatedReturnType()` | Kiểu trả về |
| Method parameter types | `Method.getAnnotatedParameterTypes()` | Kiểu từng tham số |
| Method/constructor exceptions | `Executable.getAnnotatedExceptionTypes()` | Kiểu exception được khai báo trong `throws` |
| Generic type parameter declaration | `Class.getTypeParameters()`, `Method.getTypeParameters()`, `Constructor.getTypeParameters()` | `TypeVariable<?>` của `<T>` |
| Bound của type variable | `TypeVariable.getAnnotatedBounds()` | Các kiểu bound |
| Superclass type | `Class.getAnnotatedSuperclass()` | Kiểu superclass có annotation |
| Superinterfaces | `Class.getAnnotatedInterfaces()` | Các interface type-use trong `implements`/`extends` |
| Receiver type | `Executable.getAnnotatedReceiverType()` | Kiểu receiver trong trường hợp có receiver phù hợp |

Với constructor, kiểu parameter/exception được lấy từ `Constructor<?>` do nó kế thừa `Executable`. `Method` cũng là một `Executable`.

### Phân biệt với declaration annotations

Các cách lấy sau **không tương đương**:

~~~java
field.getAnnotation(Mark.class);
field.getAnnotatedType().getAnnotation(Mark.class);
~~~

Lời gọi thứ nhất đọc **annotation gắn trên declaration của field**, lời gọi thứ hai đọc **annotation trên kiểu field**. Với `@Target(TYPE_USE)`, cách thứ hai là entry point thích hợp.

Tương tự:

~~~java
method.getParameterAnnotations();
method.getAnnotatedParameterTypes();
~~~

`getParameterAnnotations()` trả declaration annotations của **value parameters**; `getAnnotatedParameterTypes()` trả annotated types của chúng. Các reflection API khác nhau không phải vì annotation “khác tên”, mà vì vị trí cú pháp thực sự khác.

## 11. Chương trình Java 17+ độc lập: duyệt parameterized, nested, wildcard, array, bound

Lưu toàn bộ chương trình thành **`AnnotatedTypeStructureDemo.java`**.

~~~java
import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedArrayType;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.AnnotatedWildcardType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;
import java.util.List;
import java.util.Map;

public class AnnotatedTypeStructureDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Tag {
        String value();
    }

    static class Sample<T extends @Tag("number-bound") Number> {

        @Tag("field-type")
        String title;

        List<@Tag("list-element") String> names;

        Map<String, List<@Tag("nested-element") Integer>> nested;

        @Tag("array-component")
        String @Tag("array-dimension") [] values;

        List<@Tag("wildcard") ? extends @Tag("upper-bound") Number>
                numbers;

        @Tag("return-list")
        List<@Tag("return-element") String> labels(
                @Tag("parameter-type") String input)
                throws @Tag("exception-type") IOException {
            return List.of(input);
        }
    }

    static String tag(AnnotatedType type) {
        Tag annotation = type.getAnnotation(Tag.class);
        return annotation == null ? "-" : annotation.value();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<?> cls = Sample.class;

        Field title = cls.getDeclaredField("title");
        System.out.println("field=" +
                tag(title.getAnnotatedType()));

        Field names = cls.getDeclaredField("names");
        AnnotatedParameterizedType namesType =
                (AnnotatedParameterizedType) names.getAnnotatedType();
        System.out.println("list.element=" +
                tag(namesType.getAnnotatedActualTypeArguments()[0]));

        Field nested = cls.getDeclaredField("nested");
        AnnotatedParameterizedType mapType =
                (AnnotatedParameterizedType) nested.getAnnotatedType();
        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType)
                        mapType.getAnnotatedActualTypeArguments()[1];
        System.out.println("map.value.element=" +
                tag(listType.getAnnotatedActualTypeArguments()[0]));

        Field values = cls.getDeclaredField("values");
        AnnotatedArrayType arrayType =
                (AnnotatedArrayType) values.getAnnotatedType();
        System.out.println("array.dimension=" +
                tag(arrayType));
        System.out.println("array.component=" +
                tag(arrayType.getAnnotatedGenericComponentType()));

        Field numbers = cls.getDeclaredField("numbers");
        AnnotatedParameterizedType numberListType =
                (AnnotatedParameterizedType) numbers.getAnnotatedType();
        AnnotatedWildcardType wildcard =
                (AnnotatedWildcardType)
                        numberListType.getAnnotatedActualTypeArguments()[0];
        System.out.println("wildcard=" + tag(wildcard));
        System.out.println("wildcard.upper=" +
                tag(wildcard.getAnnotatedUpperBounds()[0]));

        TypeVariable<?> variable = cls.getTypeParameters()[0];
        System.out.println("variable=" + variable.getName());
        System.out.println("variable.bound=" +
                tag(variable.getAnnotatedBounds()[0]));

        Method method =
                cls.getDeclaredMethod("labels", String.class);

        AnnotatedParameterizedType returnType =
                (AnnotatedParameterizedType)
                        method.getAnnotatedReturnType();
        System.out.println("return=" + tag(returnType));
        System.out.println("return.element=" +
                tag(returnType.getAnnotatedActualTypeArguments()[0]));

        System.out.println("parameter=" +
                tag(method.getAnnotatedParameterTypes()[0]));
        System.out.println("throws=" +
                tag(method.getAnnotatedExceptionTypes()[0]));

        Sample<Integer> sample = new Sample<>();
        System.out.println("call=" + sample.labels("Java"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 AnnotatedTypeStructureDemo.java
java AnnotatedTypeStructureDemo
~~~

**Stdout được dự kiến chính xác:**

~~~text
field=field-type
list.element=list-element
map.value.element=nested-element
array.dimension=array-dimension
array.component=array-component
wildcard=wildcard
wildcard.upper=upper-bound
variable=T
variable.bound=number-bound
return=return-list
return.element=return-element
parameter=parameter-type
throws=exception-type
call=[Java]
~~~

### Diễn giải chương trình

1. `Sample` có type parameter `T extends Number`; annotation `"number-bound"` nằm trên **bound `Number`**, được lấy qua `TypeVariable.getAnnotatedBounds()[0]`.
2. `title` nhận `@Tag("field-type")` ở **kiểu `String` của field**, nên `Field.getAnnotatedType()` đọc được.
3. `names` là `List<String>`, nhưng `"list-element"` nằm ở **type argument String**, không phải trên node `List`. Bởi vậy phải dùng `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`.
4. `nested` là `Map<String,List<Integer>>`; type argument thứ hai của `Map` là `List<Integer>`, rồi type argument đầu tiên của `List` là node chứa `"nested-element"`.
5. `values` tách annotation **array dimension** và **component String** qua `AnnotatedArrayType`.
6. `numbers` đặt annotation ở chính wildcard `?` và ở upper bound `Number`; `AnnotatedWildcardType` cho phép truy cập riêng.
7. `labels` trả `List<String>`; annotation trên return type `List` và type argument `String` được truy vấn ở hai tầng khác nhau.
8. Kiểu tham số giá trị của `labels` được đọc bằng `getAnnotatedParameterTypes()`; kiểu exception trong `throws` được đọc bằng `getAnnotatedExceptionTypes()`.
9. Lời gọi thực `sample.labels("Java")` trả về `List.of("Java")`; **annotation không biến đổi kết quả**.

Chương trình dùng `List.of` từ **Java 9** và tùy chọn biên dịch `--release 17`. Các interface reflection lõi cho type annotations có từ Java 8; khi cần hỗ trợ Java 8, phải kiểm tra cụ thể API mới nào đã được dùng. Không sử dụng runtime cũ chỉ vì tính năng được giới thiệu từ Java 8.

## 12. Kiểm tra metadata không được nhầm với kiểm tra dữ liệu

Giả sử một annotation tên `@NonNull`:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {
}
~~~

Và một field:

~~~java
@NonNull String name;
~~~

Javac có thể biên dịch dù `name` chưa được gán và có giá trị mặc định `null` đối với một instance field. **Chỉ có annotation không làm JVM tự cấm null**.

Có ít nhất ba việc khác nhau:

| Việc | Cơ chế |
| --- | --- |
| Được phép viết `@NonNull` trên kiểu | `@Target(TYPE_USE)` |
| Metadata còn để reflection đọc khi chạy | `@Retention(RUNTIME)` |
| Bắt lỗi null theo hợp đồng | Static analysis/checker hoặc validation thực sự hiểu annotation |

Đừng lẫn trường hợp “reflection tìm thấy marker” với “nghiệp vụ được bảo đảm đúng”. Nếu công cụ không kiểm tra, marker chỉ là dữ liệu mô tả.

### Nullability của collection là một ví dụ điển hình

~~~java
@NonNull List<String> listA;
List<@NonNull String> listB;
~~~

Theo quy ước của **một checker có hỗ trợ nullness**, hai khai báo này có thể mang nghĩa khác nhau:

- `listA` chú thích **kiểu tham chiếu của list**.
- `listB` chú thích **kiểu phần tử của list**.

Nhưng Java SE không tự gán nghĩa không-null cho marker do bạn định nghĩa. Chỉ kết luận chính xác sau khi xem **đặc tả annotation/checker đang dùng**.

## 13. Duyệt kiểu bằng instanceof: an toàn hơn cast mù

Trong ví dụ `Sample`, tác giả đã biết trước các field cụ thể. Nếu viết một bộ duyệt generic cho nhiều kiểu chưa biết, tránh ép mọi node thành `AnnotatedParameterizedType`.

Khung tư duy:

~~~java
static void inspect(AnnotatedType type) {
    System.out.println(type.getType().getTypeName());

    if (type instanceof AnnotatedParameterizedType) {
        AnnotatedParameterizedType parameterized =
                (AnnotatedParameterizedType) type;
        for (AnnotatedType argument :
                parameterized.getAnnotatedActualTypeArguments()) {
            inspect(argument);
        }
    } else if (type instanceof AnnotatedArrayType) {
        inspect(((AnnotatedArrayType) type)
                .getAnnotatedGenericComponentType());
    } else if (type instanceof AnnotatedWildcardType) {
        AnnotatedWildcardType wildcard =
                (AnnotatedWildcardType) type;
        for (AnnotatedType upper :
                wildcard.getAnnotatedUpperBounds()) {
            inspect(upper);
        }
        for (AnnotatedType lower :
                wildcard.getAnnotatedLowerBounds()) {
            inspect(lower);
        }
    }
}
~~~

Đây là **mã minh họa cần import và class bao ngoài**. Để thành một walker tổng quát hoàn chỉnh, bạn còn cần xét:

- `AnnotatedTypeVariable` và các bounds.
- `getAnnotatedOwnerType()`.
- Annotation ngay trên **node hiện tại** trước khi duyệt xuống.
- Tránh lặp vô hạn với các bound tự tham chiếu, như `T extends Comparable<T>`.
- Cách diễn đạt đường dẫn node khi báo kết quả, ví dụ `Map.value.List.element`.
- Việc các type-use nodes có thể chứa metadata khác nhau dù `getType()` tương tự.

**Cảnh báo về đệ quy:** Generic bounds có thể tạo đồ thị quay lại type variable, không phải cây hữu hạn theo phép duyệt naive. Nếu bạn duyệt cả bounds của `AnnotatedTypeVariable`, có thể cần cơ chế ghi nhớ node/type-variable đã thăm hoặc giới hạn đường duyệt. Không áp dụng vòng lặp đệ quy vô hạn trong runtime introspection của API lớn.

## 14. AnnotatedTypeVariable: sự khác nhau giữa use-site và declaration-site

Xem:

~~~java
@Target(ElementType.TYPE_PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface Param {
}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface Use {
}

class Store<@Param T extends @Use Number> {
    @Use T value;
}
~~~

Ba vị trí:

- `@Param` trên **declaration `T`**: lấy bằng `Store.class.getTypeParameters()[0].getAnnotation(Param.class)`.
- `@Use` trên **bound `Number`**: lấy bằng `Store.class.getTypeParameters()[0].getAnnotatedBounds()[0].getAnnotation(Use.class)`.
- `@Use` trên **use-site `T` ở field**: lấy bằng `Store.class.getDeclaredField("value").getAnnotatedType().getAnnotation(Use.class)`.

Khi reflect annotated type của field `value`, node này đại diện **một lần dùng type variable**, nên có thể xử lý dưới dạng `AnnotatedTypeVariable`.

Nếu chỉ đọc `field.getGenericType()`, bạn có thể nhận `TypeVariable<?>` mô tả `T`, nhưng mất khả năng trực tiếp truy xuất marker **trên lần dùng `T` cụ thể của field** theo cách của `AnnotatedType`. Đó là lý do hai API cần tồn tại song song.

## 15. Owner types và nested generics: tránh kết luận nhầm

Ví dụ cú pháp generic lồng:

~~~java
class Outer<A> {
    class Inner<B> {
    }
}
~~~

Ở một field có kiểu `Outer<String>.Inner<Integer>`, node `Inner<Integer>` có thể có annotated owner cho phần `Outer<String>`.

Khi phân tích:

~~~java
AnnotatedType type = field.getAnnotatedType();

AnnotatedType owner = type.getAnnotatedOwnerType();
if (owner != null) {
    // Đọc type annotations/structure trên owner,
    // rồi xét tiếp phần member type.
}
~~~

**Lưu ý thực tế:**
- `getAnnotatedOwnerType()` trả về annotated owner **khi thích hợp**, không tạo owner cho những type uses vốn không có.
- Annotation đặt trên owner và annotation đặt trên member không đồng nghĩa nhau.
- Với nested parameterized types, đừng nhầm type arguments của owner với type arguments của member.
- Khi một nested type là static hoặc không phải inner member, mô hình generic của owner cần được đọc theo JLS/Reflection API, không suy luận rằng mọi nested class đều bắt giữ type parameters bên ngoài.

Nếu bạn đang chạy một thư viện phản chiếu cho nhiều phiên bản JDK, phải chú ý `getAnnotatedOwnerType()` là API của JDK hiện đại; có những khác biệt `@since` so với tập API Java 8 gốc. Bài này lấy Java 17+ làm baseline code chính.

## 16. Annotation trên return, parameter, receiver và exceptions

Một method có thể chứa type uses ở nhiều điểm:

~~~java
@Mark("result")
String convert(@Mark("input") String raw)
        throws @Mark("failure") java.io.IOException {
    return raw.strip();
}
~~~

Đây là ví dụ trong class có `@Mark` và imports phù hợp; `String.strip()` từ Java 11. Đọc:

~~~java
Method method =
        Example.class.getDeclaredMethod("convert", String.class);

AnnotatedType result = method.getAnnotatedReturnType();
AnnotatedType input = method.getAnnotatedParameterTypes()[0];
AnnotatedType failure = method.getAnnotatedExceptionTypes()[0];
~~~

Nếu bạn cần metadata trên **declaration** của parameter như `@SomeParameterAnnotation String raw` với annotation target `PARAMETER`, điểm vào khác:

~~~java
java.lang.annotation.Annotation[][] declared =
        method.getParameterAnnotations();
~~~

Cả hai nhóm reflection có thể quan trọng cho framework, nhưng **không đồng nhất về ý nghĩa**. Một annotation có nhiều targets có thể được lưu ở vị trí declaration/type khác nhau theo quy tắc JLS; khi thiết kế annotation cho framework, cần chỉ rõ dữ liệu sẽ được đọc qua API nào.

### Receiver type

Java có khái niệm receiver parameter trong một số declaration contexts. Reflection `Executable.getAnnotatedReceiverType()` truy cập annotated receiver type khi hợp lệ. Đây là một góc cạnh hữu ích cho static analyzers nhưng không cần thiết cho phần lớn logic kinh doanh. Không tự viết receiver annotations chỉ để thay thế `this` trong lời gọi phương thức; nên đọc JLS `8.4.1` và các ràng buộc cú pháp trước khi dùng.

## 17. Type erasure: annotated type không phải runtime reification

Java generics chủ yếu được triển khai qua **type erasure**. Ở runtime, việc tạo hai đối tượng:

~~~java
java.util.List<String> strings =
        new java.util.ArrayList<>();

java.util.List<Integer> integers =
        new java.util.ArrayList<>();
~~~

không tạo hai `Class` khác nhau cho `ArrayList<String>` và `ArrayList<Integer>`. Không thể chỉ gọi `strings.getClass()` rồi mong đọc chính xác type argument `String` từ instance.

Reflection có thể đọc **khai báo**:

~~~java
List<@Mark("element") String> data;
~~~

nếu class file giữ metadata phù hợp và bạn có `Field` tương ứng. Điều đó không có nghĩa type annotation được giữ riêng cho **mỗi object** của cùng runtime class.

Một số giới hạn khác:

- Annotation có `RetentionPolicy.CLASS` có thể còn trong class file, nhưng Java reflection runtime chuẩn không phơi bày như `RUNTIME`.
- Annotation có `RetentionPolicy.SOURCE` phục vụ kiểm tra tại source/compile stages, không còn qua runtime reflection.
- Annotation chỉ có target declaration có thể không xuất hiện trong `getAnnotatedType()` ở vị trí bạn tưởng.
- Generic type signature có thể giữ thông tin cho một **declaration**, không tái hiện mọi generic instantiation xảy ra lúc chạy.
- Các library và bytecode manipulators có thể có cách đọc metadata riêng, nhưng phải kiểm tra sự hỗ trợ của chúng thay vì mặc định chúng giống Java reflection.

## 18. Khi nào dùng AnnotatedType trong ứng dụng thực tế?

Các tình huống có giá trị:

1. **Static analysis/checker**: khám phá annotation đặt tại type argument, array component hoặc bound.
2. **Framework xử lý schema / serialization**: cần xác định metadata ở tầng generic được khai báo khi xây dựng schema hoặc validation; chỉ thực hiện điều này nếu framework có quy tắc đọc và diễn giải phù hợp.
3. **Phân tích API công khai**: công cụ tài liệu hóa type-use annotations trên return type/parameters và nested generic.
4. **Runtime validation được thiết kế rõ**: dùng annotation metadata như đầu vào cho một engine kiểm tra thực sự, không giả định reflection tự validate.
5. **Kiểm thử công cụ**: xác minh những marker được đặt đúng ở type-use path sau compile/package/refactor.

Tuy nhiên, nếu bạn chỉ cần kiểm tra field có một declaration annotation như `@Deprecated` hay annotation do framework đặt trên field, `Field.getAnnotation(...)` có thể phù hợp hơn. Không nên biến mọi yêu cầu metadata thành một traversal phức tạp bằng `AnnotatedType`.

### Lựa chọn retention đúng nhu cầu

Nếu dùng Java reflection trong runtime, thường cần `RUNTIME`. Nếu chỉ xử lý source bằng annotation processor hoặc một checker compile-time, retention và API tiêu thụ khác; có thể không cần đưa marker tới runtime.

Ngoài ra, cùng một tên annotation như `NonNull` từ các thư viện khác nhau **không bảo đảm cùng semantics**. Kiểm tra package, phiên bản, target, retention và công cụ thực sự xử lý nó.

## 19. Những lỗi thường gặp

| Lỗi | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| `field.getAnnotation(Mark.class)` cho annotation trên kiểu field | Nhầm declaration annotation với type use | `field.getAnnotatedType().getAnnotation(...)` |
| Chỉ gọi `getAnnotation` tại node `List` | Annotation của `String` ở node con | Lấy `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]` |
| Ép mọi node thành `AnnotatedParameterizedType` | Node có thể là class, mảng, wildcard, type variable | Kiểm tra `instanceof` |
| Xem `@Mark String[]` và `String @Mark []` như nhau | Component type và dimension khác nhau | Dùng `AnnotatedArrayType` |
| Đọc annotation trên `T` declaration qua field use | Declaration và use-site khác nhau | Dùng `TypeVariable` hoặc `AnnotatedTypeVariable` đúng ngữ cảnh |
| Chờ `@Retention(CLASS)` xuất hiện khi runtime reflection | CLASS không bảo đảm reflection | Dùng `RUNTIME` nếu cần reflection |
| Xem `getType().getTypeName()` như toàn bộ cấu trúc annotation | `Type` không giữ thông tin marker theo từng type-use path | Duyệt các `AnnotatedType` node |
| Giả định `@NonNull` luôn được javac enforce | Java SE không tự hiểu annotation tự định nghĩa | Dùng checker có hợp đồng rõ |
| Truy `getAnnotatedOwnerType()` mà không kiểm tra `null` | Không phải type nào có owner | Kiểm tra trước khi duyệt |
| Duyệt bound generic mà không phát hiện chu kỳ | Bounds có thể tự tham chiếu như `T extends Comparable<T>` | Dùng visited set/giới hạn duyệt |
| Cho rằng annotation biến `List<String>` thành runtime class riêng | Generics vẫn có type erasure | Tách metadata của declaration khỏi object runtime |
| Chỉ test field trực tiếp, bỏ generic lồng nhau | Thông tin nằm ở node sâu hơn | Viết test cho từng type-use path |

## 20. Checklist triển khai một bộ đọc annotated type

Khi triển khai code reflection cho thư viện hoặc ứng dụng, có thể dùng checklist:

1. **Xác định vị trí metadata** được mong đợi: field declaration, field type, type argument, method return, generic bound hay receiver.
2. **Xác nhận annotation target**: `TYPE_USE` cho type-use; `TYPE_PARAMETER` cho type-parameter declaration khi cần.
3. **Xác nhận retention**: runtime reflection cần `RUNTIME`.
4. **Lấy đúng entry point**: `getAnnotatedType()`, `getAnnotatedReturnType()`, `getAnnotatedParameterTypes()`, `getAnnotatedExceptionTypes()`, `getTypeParameters()` hoặc phương thức liên quan.
5. **Duyệt theo node shape**: parameterized, array, wildcard, type variable, owner type.
6. **Đọc annotation tại từng node**; không mặc định annotation ở cha tự áp dụng cho con.
7. **Xem trường hợp không có annotation**: `getAnnotation(...)` trả `null` nếu không có.
8. **Đọc đúng bounds**: upper/lower wildcard, type-variable bounds; chú ý phân biệt declaration vs use.
9. **Tránh recursion không giới hạn** với self-referential generic bounds.
10. **Kiểm thử trên phiên bản JDK/`--release` dự án dùng**, đặc biệt khi dùng những method được bổ sung sau Java 8.
11. **Tách đọc metadata khỏi áp dụng semantic rules**: traversal chỉ thu thập dữ liệu, còn checker/validator quyết định nghĩa của chúng.
12. **Kiểm tra class file/packaging** khi test runtime annotations; annotation không hiện có thể là retention, target hoặc build/instrumentation issue chứ không phải lỗi generic.

## 21. Bài tập thực hành

**Bài 1 — Một tầng generic.** Khai báo field `List<@Mark("item") String> values`. Viết code reflection lấy `"item"`, giải thích tại sao gọi annotation ở node `List` không trả kết quả đó.

**Bài 2 — Hai tầng generic.** Với `Map<String,List<@Mark("number") Integer>> numbers`, chỉ rõ thứ tự truy cập `getAnnotatedActualTypeArguments()` để lấy marker của `Integer`.

**Bài 3 — Mảng.** Khai báo `@Mark("component") String @Mark("array") [] values`. Trả lời node nào là `AnnotatedArrayType`; node nào phải lấy từ `getAnnotatedGenericComponentType()`.

**Bài 4 — Wildcard.** Với `List<@Mark("wildcard") ? extends @Mark("bound") Number>`, trình bày API đọc marker ở `?` và ở `Number`.

**Bài 5 — Type variable.** Cho `class Box<@DeclMark T extends @UseMark Number> { @UseMark T field; }`. Đọc marker tại declaration `T`, bound `Number` và use-site `T` bằng API khác nhau.

**Bài 6 — Reflection từ method.** Viết method trả `List<@Mark String>` và nhận `@Mark String`. Dùng `getAnnotatedReturnType()` và `getAnnotatedParameterTypes()` để đọc hai vị trí.

**Bài 7 — Retention.** Đổi marker từ `RUNTIME` sang `CLASS`. Dự đoán kết quả `getAnnotation(Mark.class)`. Vì sao vẫn có thể có dữ liệu trong class file nhưng runtime reflection không thấy?

**Bài 8 — Owner type.** Viết nested inner class `Outer<A>.Inner<B>`. Tra cứu `getAnnotatedOwnerType()` trên field dùng kiểu đó, kiểm tra `null` rồi xem owner `Outer`. Phân biệt type arguments `A` và `B`.

**Bài 9 — Self-referential bounds.** Với `class E<T extends Comparable<T>>`, giải thích nguy cơ của một hàm đệ quy vừa đi qua `AnnotatedTypeVariable` vừa đi qua bounds mà không có cơ chế chống vòng lặp.

**Bài 10 — Nullness semantics.** Một ứng dụng có `List<@NonNull String>` nhưng cho thêm `null`. Chỉ rõ phần nào là vấn đề của Java SE type checking, phần nào thuộc semantic checker/runtime validation.

## 22. Tổng kết trọng tâm

- **`AnnotatedType` = cấu trúc một type use + annotation metadata ở chính node ấy.** `getType()` trả về `Type` nền tảng, nhưng không thay thế khả năng truy cập annotation trên từng tầng.
- **`AnnotatedParameterizedType`** đọc các annotated type arguments; rất cần cho `List<@Mark String>` và generic lồng nhau.
- **`AnnotatedArrayType`** cho phép phân biệt annotation trên array dimension và component.
- **`AnnotatedWildcardType`** cung cấp annotated upper/lower bounds; annotation trên wildcard và annotation trên bound là hai vị trí khác nhau.
- **`AnnotatedTypeVariable` và `TypeVariable`** phục vụ hai góc nhìn liên quan nhưng khác nhau: một type-variable use và khai báo type parameter/bounds.
- **`getAnnotatedOwnerType()`** dùng cho owner type phù hợp và cần kiểm tra `null`.
- **Entry point reflection phải khớp vị trí annotation**: declaration annotation khác annotation trên field/return/parameter type.
- **`@Target(TYPE_USE)` cho phép vị trí cú pháp, `@Retention(RUNTIME)` giúp reflection đọc được**; chúng không tự thực thi nullness hay validation.
- **Java generics vẫn chịu type erasure**. Reflection đọc metadata của các khai báo chứ không tái hiện mọi type argument của từng object runtime.
- Các cấu trúc trên vẫn là kiến thức áp dụng cho Java hiện đại; dùng đúng JDK/API baseline và công cụ đọc annotation thực tế.

## 23. Tài liệu chính thức

- Java SE 17 API, **AnnotatedType**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html
- Java SE 17 API, **AnnotatedParameterizedType**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html
- Java SE 17 API, **AnnotatedArrayType**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html
- Java SE 17 API, **AnnotatedWildcardType**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html
- Java SE 17 API, **AnnotatedTypeVariable**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedTypeVariable.html
- Java SE 17 API, **TypeVariable**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html
- Java SE 17 API, **AnnotatedElement**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html
- Java SE 17 API, **ElementType** (`TYPE_USE`/`TYPE_PARAMETER`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html
- Java SE 17 API, **RetentionPolicy**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html
- Java Language Specification, **`4.11 Where Types Are Used**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.11
- Java Language Specification, **`9.7 Annotations**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7

Để công cụ reflection hoạt động đáng tin cậy, hãy bắt đầu từ **vị trí type-use cụ thể**, duyệt đúng node trong cấu trúc, đọc retention/target và kiểm thử metadata sau biên dịch. Không giả định có validation, type reification hay annotation propagation nếu hợp đồng của hệ thống Java và checker không xác nhận điều đó.