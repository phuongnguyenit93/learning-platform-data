# 4.7 Phân biệt annotation trên khai báo với AnnotatedType trên cách dùng kiểu

Trong Java, một annotation có thể mô tả **thực thể được khai báo** (class, field, method, parameter, type parameter...) hoặc mô tả **một lần sử dụng kiểu** (kiểu phần tử trong `List<String>`, kiểu trả về của method, thành phần mảng, wildcard, kiểu trong `extends`...). Hai loại thông tin có thể trông rất giống nhau trong mã nguồn nhưng nằm ở **những vị trí metadata khác nhau** và phải đọc bằng **những API reflection khác nhau**.

Ví dụ:

~~~java
@FieldLabel("customers")
List<@TypeLabel("element") String> customers;
~~~

- `@FieldLabel` gắn với **khai báo field** `customers`; đọc từ `Field.getAnnotation(FieldLabel.class)`.
- `@TypeLabel` gắn với **lần sử dụng kiểu `String` làm type argument** trong `List<...>`; đọc qua `Field.getAnnotatedType()`, ép đúng dạng `AnnotatedParameterizedType` rồi đi vào `getAnnotatedActualTypeArguments()[0]`.
- Chính object `Field` và object `AnnotatedType` thể hiện hai tầng khác nhau. Không suy ra annotation trên phần tử generic chỉ từ `Field.getAnnotations()`.

Đích của bài là phân biệt hai tầng, tìm đúng API để đọc từng vị trí, hiểu `@Target`/`@Retention`, duyệt cấu trúc kiểu lồng nhau và tránh kết luận rằng annotation loại `TYPE_USE` tự động thực thi ràng buộc lúc chạy.

## 1. Hai tầng metadata: khai báo và chỗ dùng kiểu

| Khía cạnh | Annotation trên khai báo (*declaration annotation*) | Annotation trên chỗ dùng kiểu (*type-use annotation*) |
| --- | --- | --- |
| Gắn với | Thực thể được khai báo: class, field, method, constructor, parameter, record component, type parameter... | Một lần xuất hiện của kiểu: kiểu field, kiểu trả về, generic argument, bound, array level, wildcard... |
| Ví dụ | `@Deprecated class OldApi {}`; `@Column String name;` | `List<@NonNull String>`; `String @NonNull []`; `? extends @Checked Number` |
| Mục tiêu trong `@Target` | `TYPE`, `FIELD`, `METHOD`, `PARAMETER`, `CONSTRUCTOR`, `RECORD_COMPONENT`, `TYPE_PARAMETER`... | `TYPE_USE` (và quy tắc riêng về annotation tại khai báo type parameter) |
| Điểm vào reflection | `Class`, `Field`, `Method`, `Constructor`, `Parameter`, `RecordComponent`, `TypeVariable`... qua `AnnotatedElement` | `AnnotatedType` nhận từ `getAnnotatedType` / `getAnnotatedReturnType` / `getAnnotatedParameterTypes` / `getAnnotatedBounds`... |
| Độ sâu truy vấn | Annotation trên **chính declaration** đang hỏi | Annotation trên **đúng node kiểu** trong cây kiểu, có thể cần đi sâu vào argument, array, wildcard, bound |
| Hành vi thực thi | Annotation thường chỉ là metadata, trừ những annotation có semantics do Java/compiler/framework quy định | Type annotation cũng không tự kiểm tra nullability hay tự ép kiểu tại runtime |

Hình dung cấu trúc:

~~~text
Khai báo field customers
│
├─ Field metadata
│  └─ @FieldLabel("customers")                 <-- declaration annotation
│
└─ Kiểu của field: List<String>
   └─ AnnotatedParameterizedType: List<...>
      └─ AnnotatedType: String
         └─ @TypeLabel("element")               <-- type-use annotation
~~~

Một lần sử dụng kiểu không đồng nhất với bản khai báo của kiểu đó. Chẳng hạn, `List<@NonNull String>` đánh dấu **String ở vị trí type argument này**, không gắn `@NonNull` lên chính khai báo `java.lang.String` và không làm mọi `String` khác có annotation ấy.

## 2. Phân biệt `ElementType.FIELD`, `TYPE_USE` và `TYPE_PARAMETER`

`@Target` xác định annotation có thể dùng ở đâu; `@Retention` xác định nó tồn tại tới giai đoạn nào.

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldLabel {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeLabel {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface TypeParameterLabel {
    String value();
}
~~~

Đây là các khai báo minh họa độc lập; trong chương trình Java hoàn chỉnh ở phần dưới, chúng được khai báo trong class demo để chạy được cùng một file.

- `@Target(FIELD)`: dùng trên **declaration của field**; `Field.getAnnotation(...)` tìm được nếu runtime retention phù hợp.
- `@Target(TYPE_USE)`: dùng tại các **vị trí kiểu** mà ngôn ngữ cho phép, gồm type argument (`List<@TypeLabel String>`), field type, array dimension, bound, kiểu trả về, kiểu tham số, kiểu trong `throws`, kiểu được cast...
- `@Target(TYPE_PARAMETER)`: áp dụng cho **khai báo tham số kiểu** như `class Box<@TypeParameterLabel T>`; có thể đọc declaration annotation trên `TypeVariable<?>`.
- `@Retention(RUNTIME)`: cho phép các API reflection chuẩn quan sát annotation. `CLASS` (mặc định khi không khai báo `@Retention`) được giữ trong class file nhưng không được phản chiếu bởi core reflection; `SOURCE` không được giữ trong class file thông thường.

**Đừng coi declaration và type-use là hai loại annotation không bao giờ giao nhau.** Theo Java Language Specification, một annotation type có thể mang cả `@Target({FIELD, TYPE_USE})`. Khi đặt tại vị trí phù hợp trước kiểu của field, một annotation có thể được xem là áp dụng cho **cả declaration lẫn type-use**. Vì thế vị trí hiển thị trong mã nguồn thôi chưa đủ: hãy xem `@Target` của annotation và xác định đúng đối tượng metadata cần truy vấn.

Tương tự, `TYPE_USE` cũng có quy tắc áp dụng tại khai báo class/interface hoặc type parameter trong những ngữ cảnh được JLS định nghĩa. Khi muốn nhấn mạnh ranh giới trong ví dụ học, dùng các annotation type chỉ có **một target** mỗi loại để tránh trộn hai kết quả.

## 3. `AnnotatedElement` và `AnnotatedType` không cùng “đường đi” reflection

### 3.1. Truy vấn annotation của declaration

Các kiểu reflection như `Field`, `Method`, `Class`, `Parameter` và `RecordComponent` triển khai `AnnotatedElement`. Những phương thức thường dùng:

- `getAnnotation(MyAnnotation.class)`: trả một annotation của loại đó nếu *present* trên element, hoặc `null` nếu không.
- `getDeclaredAnnotation(...)` và `getDeclaredAnnotations()`: chỉ xét trực tiếp annotation trên element đó, không áp dụng inherited semantics.
- `getAnnotations()`: các annotation *present* trên element; không tự đi vào các vị trí kiểu con.
- `getAnnotationsByType(...)` / `getDeclaredAnnotationsByType(...)`: hữu ích với annotation `@Repeatable`, có thể mở container để lấy nhiều annotation.
- `isAnnotationPresent(...)`: kiểm tra sự hiện diện theo semantics của `AnnotatedElement`.

Ví dụ, nếu `Field field` là field trong ví dụ mở đầu:

~~~java
FieldLabel label = field.getAnnotation(FieldLabel.class);
String name = label == null ? "(not found)" : label.value();
~~~

Đoạn minh họa giả định đã có biến `field` và `import java.lang.reflect.Field;`. Đừng dùng `Field.getAnnotation(TypeLabel.class)` để tìm annotation trên `String` nằm **bên trong** `List<...>`; đối tượng `Field` không phải node mô tả chỗ dùng kiểu `String` đó.

### 3.2. Truy vấn annotation của một lần dùng kiểu

`AnnotatedType` là interface **cũng kế thừa `AnnotatedElement`**, nhưng các phương thức `getAnnotation` / `getAnnotations` trên nó nói về **type annotations của chính node kiểu**.

~~~java
AnnotatedType fieldUse = field.getAnnotatedType();
~~~

`AnnotatedType.getType()` trả `java.lang.reflect.Type` bên dưới; giá trị đó có thể là `Class<?>`, `ParameterizedType`, `GenericArrayType`, `TypeVariable<?>` hoặc `WildcardType` tùy cấu trúc kiểu. `getType()` **không thay thế** việc đọc annotation từ chính `AnnotatedType` và **không đảm bảo** trả `Class<?>`.

Bốn subtype cần nhận diện:

| Dạng `AnnotatedType` | Ví dụ vị trí | API đi sâu |
| --- | --- | --- |
| `AnnotatedParameterizedType` | `List<@A String>`, `Map<@A String, @B Integer>` | `getAnnotatedActualTypeArguments()` |
| `AnnotatedArrayType` | `String @A []`, mảng nhiều chiều | `getAnnotatedGenericComponentType()` |
| `AnnotatedWildcardType` | `List<@A ? extends @B Number>` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `AnnotatedTypeVariable` | Dùng tham số kiểu `T` tại một vị trí | `getAnnotatedBounds()` cho bound của biến kiểu |

Mỗi node có thể có annotation riêng. `getAnnotations()` trên outer `List<...>` không tự tổng hợp annotation trên `String` hay trên bound của wildcard. Muốn tìm mọi type annotation, cần **duyệt cây** theo đúng subtype và kiểm tra từng node.

## 4. Tra cứu đúng API theo nơi annotation xuất hiện

| Khai báo / kiểu trong mã | Declaration API | Type-use API |
| --- | --- | --- |
| `@Service class MyService` | `Class.getAnnotation(...)` | Với kiểu được dùng trong quan hệ kế thừa, dùng `getAnnotatedSuperclass()` / `getAnnotatedInterfaces()` |
| `@Column List<@A String> names` | `Field.getAnnotation(Column.class)` | `Field.getAnnotatedType()` → `AnnotatedParameterizedType` → annotated argument |
| `@Trace @A String read()` | `Method.getAnnotation(Trace.class)` | `Method.getAnnotatedReturnType()` |
| `void send(@Param @A String value)` | `Parameter.getAnnotation(Param.class)` hoặc `Executable.getParameterAnnotations()` | `Parameter.getAnnotatedType()` hoặc `Executable.getAnnotatedParameterTypes()` |
| `void run() throws @A IOException` | Annotation thuộc method declaration nếu có annotation dành cho `METHOD` | `Executable.getAnnotatedExceptionTypes()` |
| Instance receiver (ví dụ annotated `this`) | Không phải một declaration annotation trên method body | `Executable.getAnnotatedReceiverType()` |
| `class Box<@TTag T extends @A Number>` | `TypeVariable.getAnnotation(TTag.class)` | `TypeVariable.getAnnotatedBounds()` |
| Record `record Row(@Col @A String key) {}` | `RecordComponent.getAnnotation(Col.class)` | `RecordComponent.getAnnotatedType()` |
| `class Impl extends @A Base implements @B Runnable` | `Class.getAnnotations()` không diễn giải các dấu này là annotation của khai báo `Impl` | `Class.getAnnotatedSuperclass()` và `getAnnotatedInterfaces()` |

**Giới hạn của bảng:** những đoạn là ví dụ cú pháp, không phải toàn bộ chương trình. Các annotation `@A`, `@B`, `@Col`... cần được khai báo `@Target` và `@Retention` hợp lệ trong mã thực. Java không có một method tổng quát duy nhất trên `Class` để lấy mọi type-use annotation của mọi member. Luôn bắt đầu từ member chứa lần dùng kiểu cần phân tích.

`getAnnotatedReceiverType()` trả `null` cho static method và cho những executable không thể có receiver parameter; đối với instance method, nó có thể trả `AnnotatedType` **không có annotation** ngay cả khi không khai báo annotated receiver tường minh.

## 5. Ví dụ Java 17+ đầy đủ: đọc cả hai tầng metadata

Tạo file `AnnotationLocationsDemo.java`:

~~~java
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
import java.lang.reflect.Parameter;
import java.lang.reflect.TypeVariable;
import java.util.List;

public class AnnotationLocationsDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    @interface ColumnLabel { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface ArgumentLabel { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_PARAMETER)
    @interface TypeParameterLabel { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface TypeRole { String value(); }

    static class Catalog<@TypeParameterLabel("T") T extends @TypeRole("bound") Number> {
        @ColumnLabel("names")
        List<@TypeRole("element") String> names;

        @ColumnLabel("codes")
        String @TypeRole("array") [] codes;

        List<@TypeRole("wildcard") ? extends @TypeRole("upper") Number> numbers;

        public @TypeRole("return") List<@TypeRole("return-element") String> find(
                @ArgumentLabel("query") @TypeRole("input") String query) {
            return List.of(query);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Field names = Catalog.class.getDeclaredField("names");
        System.out.println("declaration: " + names.getAnnotation(ColumnLabel.class).value());
        System.out.println("field raw class: " + names.getType().getTypeName());
        System.out.println("field generic type: " + names.getGenericType().getTypeName());
        AnnotatedParameterizedType namesUse = (AnnotatedParameterizedType) names.getAnnotatedType();
        AnnotatedType itemType = namesUse.getAnnotatedActualTypeArguments()[0];
        System.out.println("element type-use: " + itemType.getAnnotation(TypeRole.class).value());
        System.out.println("element type: " + itemType.getType().getTypeName());
        System.out.println("field has TypeRole declaration: " + (names.getAnnotation(TypeRole.class) != null));

        Field codes = Catalog.class.getDeclaredField("codes");
        AnnotatedArrayType arrayType = (AnnotatedArrayType) codes.getAnnotatedType();
        System.out.println("array type-use: " + arrayType.getAnnotation(TypeRole.class).value());
        System.out.println("component type: " + arrayType.getAnnotatedGenericComponentType().getType().getTypeName());

        Field numbers = Catalog.class.getDeclaredField("numbers");
        AnnotatedParameterizedType numbersUse = (AnnotatedParameterizedType) numbers.getAnnotatedType();
        AnnotatedWildcardType wildcard = (AnnotatedWildcardType) numbersUse.getAnnotatedActualTypeArguments()[0];
        System.out.println("wildcard type-use: " + wildcard.getAnnotation(TypeRole.class).value());
        System.out.println("upper bound type-use: " + wildcard.getAnnotatedUpperBounds()[0].getAnnotation(TypeRole.class).value());

        Method find = Catalog.class.getDeclaredMethod("find", String.class);
        AnnotatedParameterizedType returnUse = (AnnotatedParameterizedType) find.getAnnotatedReturnType();
        System.out.println("return type-use: " + returnUse.getAnnotation(TypeRole.class).value());
        System.out.println("return element type-use: " + returnUse.getAnnotatedActualTypeArguments()[0].getAnnotation(TypeRole.class).value());
        Parameter query = find.getParameters()[0];
        System.out.println("parameter declaration: " + query.getAnnotation(ArgumentLabel.class).value());
        System.out.println("parameter type-use: " + query.getAnnotatedType().getAnnotation(TypeRole.class).value());

        TypeVariable<?> typeParameter = Catalog.class.getTypeParameters()[0];
        System.out.println("type-parameter declaration: " + typeParameter.getAnnotation(TypeParameterLabel.class).value());
        System.out.println("type-parameter bound use: " + typeParameter.getAnnotatedBounds()[0].getAnnotation(TypeRole.class).value());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file; yêu cầu JDK 17 trở lên:

~~~bash
javac --release 17 AnnotationLocationsDemo.java
java AnnotationLocationsDemo
~~~

`stdout` chính xác:

~~~text
declaration: names
field raw class: java.util.List
field generic type: java.util.List<java.lang.String>
element type-use: element
element type: java.lang.String
field has TypeRole declaration: false
array type-use: array
component type: java.lang.String
wildcard type-use: wildcard
upper bound type-use: upper
return type-use: return
return element type-use: return-element
parameter declaration: query
parameter type-use: input
type-parameter declaration: T
type-parameter bound use: bound
~~~

Chương trình dùng các annotation type khác target, nên bạn thấy rõ từng tầng:

1. `names.getAnnotation(ColumnLabel.class)` đọc annotation trên **field declaration** và trả `"names"`.
2. `names.getType()` trả raw `java.util.List` do erasure; `names.getGenericType()` giữ `List<String>` trong generic signature nhưng không phản ánh `@TypeRole("element")`.
3. `names.getAnnotatedType()` là `AnnotatedParameterizedType`. Type argument đầu là node `String` có annotation `@TypeRole("element")`. `names.getAnnotation(TypeRole.class)` trả `null` vì annotation đó không nằm trên declaration field.
4. `String @TypeRole("array") [] codes` gắn annotation vào **mức mảng**. `AnnotatedArrayType` chứa `@TypeRole("array")`; `getAnnotatedGenericComponentType()` đi tiếp vào `String`.
5. Với wildcard, `@TypeRole("wildcard")` gắn vào node `?`; `@TypeRole("upper")` gắn vào bound `Number`. Hai vị trí là hai node khác nhau.
6. `find.getAnnotatedReturnType()` chứa annotation trên `List<...>` trả về; `getAnnotatedActualTypeArguments()[0]` chứa annotation riêng trên `String`.
7. `Parameter.getAnnotation(ArgumentLabel.class)` đọc annotation trên **khai báo tham số**, trong khi `Parameter.getAnnotatedType().getAnnotation(TypeRole.class)` đọc annotation trên **kiểu String của tham số**.
8. `TypeVariable.getAnnotation(TypeParameterLabel.class)` đọc annotation trên khai báo `T`; `getAnnotatedBounds()[0]` đọc annotation trên kiểu `Number` dùng làm bound.

Lệnh biên dịch với `--release 17` bảo đảm cú pháp và API của chương trình phù hợp Java SE 17. Giá trị stdout ở trên đã được kiểm tra với JDK thực tế.

## 6. Phân rã generic type nhiều cấp: đừng dừng ở node ngoài

Với khai báo:

~~~java
Map<@Role("key") String, List<@Role("number") Integer>> index;
~~~

Đây là cú pháp minh họa, với `@Role` được khai báo `@Target(TYPE_USE)`. Cây cần đọc:

~~~text
AnnotatedParameterizedType: Map<...>
├─ AnnotatedType: String [@Role("key")]
└─ AnnotatedParameterizedType: List<...>
   └─ AnnotatedType: Integer [@Role("number")]
~~~

Trình tự:

1. Lấy `Field.getAnnotatedType()` cho `index`.
2. Kiểm tra `instanceof AnnotatedParameterizedType` rồi lấy `getAnnotatedActualTypeArguments()`.
3. Argument 0 là `String`: đọc annotation trên **node này**.
4. Argument 1 là `List<Integer>`: lại kiểm tra `AnnotatedParameterizedType` rồi đi sâu vào argument 0 để đọc annotation trên `Integer`.

Một utility duyệt kiểu nên xử lý các nhánh `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedWildcardType`, `AnnotatedTypeVariable`; đồng thời có bộ nhớ “đã thăm” hoặc giới hạn đệ quy nếu đi qua bound vòng như `T extends Comparable<T>`. Nếu chỉ cần một đường path cụ thể, truy vấn trực tiếp thường rõ ràng hơn utility tổng quát.

Ví dụ bộ đọc kiểu tối giản dưới đây chỉ khảo sát **generic arguments và array components**, không phải visitor đầy đủ của mọi dạng AnnotatedType:

~~~java
static void inspect(AnnotatedType type) {
    System.out.println(type.getType().getTypeName());
    for (var annotation : type.getAnnotations()) {
        System.out.println("  annotation: " + annotation.annotationType().getSimpleName());
    }

    if (type instanceof AnnotatedParameterizedType parameterized) {
        for (AnnotatedType argument : parameterized.getAnnotatedActualTypeArguments()) {
            inspect(argument);
        }
    } else if (type instanceof AnnotatedArrayType array) {
        inspect(array.getAnnotatedGenericComponentType());
    }
}
~~~

Đây là **method minh họa** đặt trong một class có `import java.lang.reflect.*;`. Nó không đi vào wildcard bounds, type-variable bounds hoặc owner type; nếu nhiệm vụ cần các vị trí đó, phải bổ sung các nhánh tương ứng và phòng trường hợp đệ quy vòng. Quan trọng hơn, `AnnotatedType.getAnnotations()` chỉ trả annotation của **node đang đứng**, không trả tự động toàn cây.

## 7. Mảng: vị trí của annotation quyết định cấp độ được đánh dấu

Mảng trong Java có thể có annotation trên **kiểu phần tử** hoặc **mỗi chiều mảng**. Ví dụ:

~~~java
@TypeLabel("element") String @TypeLabel("outer") [] @TypeLabel("inner") [] values;
~~~

Dòng này là khai báo minh họa cho annotation có `@Target(TYPE_USE)` và `@Retention(RUNTIME)`. Cách hiểu các node:

~~~text
AnnotatedArrayType: String[][]     [@TypeLabel("outer")]
└─ AnnotatedArrayType: String[]     [@TypeLabel("inner")]
   └─ AnnotatedType: String         [@TypeLabel("element")]
~~~

`@TypeLabel("outer")` trên cặp `[]` đầu tiên ứng với **kiểu mảng ngoài**, `@TypeLabel("inner")` trên cặp `[]` thứ hai ứng với **kiểu mảng thành phần**, còn annotation đặt trước `String` gắn với **kiểu phần tử**. Khi dùng reflection, gọi lặp `getAnnotatedGenericComponentType()` để xuống từng mức.

**Bẫy:** `Field.getType()` sẽ cho biết `String[][].class` nhưng không nói annotation nằm ở chiều nào; `Field.getGenericType()` cũng không cung cấp cây `AnnotatedType`. Một annotation gắn vào `String` không đồng nghĩa gắn vào `String[]`, và ngược lại.

## 8. Wildcard, type parameter, bound và inheritance type-use

### Wildcard khác với upper/lower bound

Với `List<@A ? extends @B Number>`, `@A` gắn vào dấu `?`, `@B` gắn vào kiểu `Number`. Trong reflection:

~~~java
AnnotatedWildcardType wildcard = (AnnotatedWildcardType) annotatedArgument;
AnnotatedType[] upper = wildcard.getAnnotatedUpperBounds();
AnnotatedType[] lower = wildcard.getAnnotatedLowerBounds();
~~~

Đoạn minh họa giả sử `annotatedArgument` đã được lấy từ type argument của parameterized type. Khi có `? super @A Integer`, annotation trên `Integer` được tìm qua `getAnnotatedLowerBounds()`; khi `? extends @B Number` thì tìm qua `getAnnotatedUpperBounds()`. Cần kiểm tra độ dài mảng bounds và từng loại trước khi truy cập.

### Khai báo `T` khác với kiểu dùng trong bound

~~~java
class Container<@TypeParameterLabel("T") T extends @TypeLabel("bound") Number> {}
~~~

`TypeVariable<?> variable = Container.class.getTypeParameters()[0]` (giả định `Container` và annotation types đã khai báo) là metadata cho chính tham số kiểu `T`; `variable.getAnnotation(TypeParameterLabel.class)` đọc annotation trên **declaration của T**. Ngược lại, `variable.getAnnotatedBounds()[0]` là node của kiểu `Number` trong phần `extends`. Hai vị trí có thể mang hai annotation khác nhau.

Nếu sau đó một field có kiểu `@TypeLabel("use-T") T value;`, **lần sử dụng `T` ở field** thuộc một `AnnotatedTypeVariable`; annotation `"use-T"` nằm trên node type-use tại field. Đây là vị trí độc lập với annotation trên declaration của `T` và với annotation trên bound `Number`.

### `extends` và `implements` là lần sử dụng kiểu

~~~java
class Worker extends @TypeLabel("base") Base
        implements @TypeLabel("contract") Runnable {}
~~~

Đây là minh họa cú pháp với giả định `Base` là một class và `@TypeLabel` có `TYPE_USE`. `Worker.class.getAnnotatedSuperclass()` đọc annotation `"base"` trên **kiểu Base được sử dụng**; `Worker.class.getAnnotatedInterfaces()[0]` đọc `"contract"` trên **kiểu Runnable được sử dụng**. Gọi `Base.class.getAnnotations()` sẽ tìm annotation của **khai báo Base**, không phải annotation trên dòng `extends Base` trong `Worker`.

## 9. Type-use annotation không tự thi hành kiểm tra runtime

Một ví dụ thường gặp là `@NonNull`:

~~~java
List<@NonNull String> names;
~~~

Chỉ có metadata `@NonNull` tại chỗ dùng kiểu `String` **không khiến JVM mặc định chặn `null`** đưa vào danh sách. Kiểm tra nullability, dữ liệu hợp lệ hoặc ownership thường cần một trong các thành phần:

- Static checker/annotation processor hiểu semantics của annotation và thực hiện kiểm tra khi biên dịch.
- Framework đọc metadata tại runtime rồi **chủ động** kiểm tra, ví dụ đọc type argument của field và áp dụng validation.
- Kiểm tra rõ ràng trong code, như `Objects.requireNonNull(...)`, Bean Validation thích hợp, hoặc contract riêng của ứng dụng.

Annotation không đổi `Class` thực sự của `String`, không sinh ra một JVM subtype mới và không vô hiệu hóa type erasure. Generic signature có thể còn trong class file và phản chiếu qua `getGenericType()`, nhưng annotation trên các node generic được truy cập qua `AnnotatedType`.

## 10. Lưu ý về annotation lặp, kế thừa và retention

### Retention

| Retention | Tồn tại trong class file? | Core reflection tiêu chuẩn đọc được lúc chạy? |
| --- | --- | --- |
| `SOURCE` | Không (thông thường bị loại khi compile) | Không |
| `CLASS` | Có | Không |
| `RUNTIME` | Có | Có, ở những vị trí được API reflection phơi bày |

Nếu khai báo annotation mà **quên `@Retention(RUNTIME)`**, `Field.getAnnotation(...)` hoặc `AnnotatedType.getAnnotation(...)` có thể trả `null` mặc dù mã nguồn có annotation. Đây là lỗi rất phổ biến khi thiết kế một thư viện dùng reflection.

### `@Inherited` và `@Repeatable`

`@Inherited` chỉ ảnh hưởng một số kiểu truy vấn annotation **trên khai báo class** theo chuỗi superclass. Nó không làm annotation của field/method tự được thừa kế và không làm annotation trên `AnnotatedType` tự lan sang kiểu của subclass. Nếu muốn kiểm tra annotation được khai báo trực tiếp trên class, dùng `getDeclaredAnnotation(...)`; nếu muốn semantics *present* có inheritance theo contract, dùng `getAnnotation(...)` hoặc `getAnnotations()` với annotation được đánh dấu `@Inherited`.

Với annotation `@Repeatable`, `getAnnotationsByType(...)` và `getDeclaredAnnotationsByType(...)` hữu ích cả trên element và trên `AnnotatedType`, tùy bạn đang đọc declaration hay type-use; hai phương thức có logic đọc container annotation, trong khi `getAnnotation(...)` chỉ trả một annotation theo semantics thông thường.

### Một annotation type có thể đặt ở hai tầng

Giả sử:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.TYPE_USE})
@interface Tagged {}
~~~

Trong ngữ cảnh như `@Tagged String title;`, theo quy tắc áp dụng annotation của JLS, annotation có thể áp dụng **đồng thời** cho declaration `title` và type-use `String`. Cần kiểm tra cả `Field.getAnnotation(Tagged.class)` và `Field.getAnnotatedType().getAnnotation(Tagged.class)` nếu contract của bạn muốn cả hai loại metadata. Không được kết luận chỉ nhìn vị trí cú pháp mà thiếu thông tin `@Target`.

## 11. Giới hạn của Java reflection: một số type-use không có đường truy vấn qua `AnnotatedType`

`TYPE_USE` cũng cho phép đặt annotation tại nhiều biểu thức và local context, ví dụ:

~~~java
Object value = "demo";
String text = (@TypeLabel("cast") String) value;
Object object = new @TypeLabel("creation") String("demo");
~~~

Đây là các statement minh họa; annotation đã được khai báo `TYPE_USE`. Annotation trên kiểu trong **cast** hoặc **new expression** là một phần của metadata type annotation trong class file khi retention thích hợp, nhưng **không có API core reflection đơn giản** như `Field.getAnnotatedType()` để tìm lại từng lần cast/new/local-variable-use ở bên trong thân method. Những công cụ cần đọc vị trí code-level như vậy thường phân tích source/AST, `javax.lang.model` trong annotation processing hoặc class file/bytecode bằng công cụ phù hợp.

Đừng viết code quét `Class.getDeclaredFields()` rồi tưởng đã có toàn bộ type annotations trong mọi method body. Reflection chủ yếu cung cấp những vị trí type-use được gắn với **khai báo và chữ ký** mà API phơi bày.

## 12. Chẩn đoán lỗi phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| `field.getAnnotation(TypeLabel.class) == null` mặc dù thấy annotation trong `List<@TypeLabel String>` | Hỏi annotation trên declaration, trong khi annotation nằm trên type argument | `field.getAnnotatedType()` → `AnnotatedParameterizedType` → type argument |
| `getAnnotatedType().getAnnotation(TypeLabel.class) == null` trong `List<@TypeLabel String>` | Chỉ hỏi node `List` bên ngoài; annotation nằm trên `String` | Đi vào `getAnnotatedActualTypeArguments()[0]` |
| Có annotation trong source nhưng reflection trả `null` | `@Retention` mặc định là `CLASS`, hoặc `@Target`/vị trí không khớp | Kiểm tra định nghĩa annotation, biên dịch lại và đọc đúng vị trí |
| `ClassCastException` khi cast `AnnotatedType` | Kiểu đang xét không phải parameterized/array/wildcard/type variable dạng đã giả định | Kiểm tra `instanceof` trước khi downcast |
| Không tìm thấy annotation trên `Number` trong wildcard | Đọc node wildcard thay vì bound | `AnnotatedWildcardType.getAnnotatedUpperBounds()` / `getAnnotatedLowerBounds()` |
| Mất annotation trên một chiều mảng | Chỉ xem base element hoặc outer array, bỏ qua intermediate array type | Duyệt `AnnotatedArrayType.getAnnotatedGenericComponentType()` nhiều lần |
| Không thấy annotation trên `T` hoặc `T extends Number` | Nhầm declaration của type parameter với bound | `TypeVariable.getAnnotation(...)` cho `T`; `getAnnotatedBounds()` cho bound |
| Có annotation của interface nhưng không thấy qua `getAnnotation` trên implementing class | Không có inheritance tự động theo interface, nhầm declaration với type-use | Hỏi `getAnnotatedInterfaces()` cho chỗ `implements`, hoặc đi tìm declaration đúng |
| Annotation trên cast/new không tìm được qua `Field` | Core reflection không phơi bày type-use mọi vị trí method body | Phân tích source/AST hoặc class file/bytecode |

Khi viết code thư viện xử lý annotation, nên phân biệt tên biến như `fieldDeclarationAnnotations`, `fieldTypeUse`, `elementTypeUse` và truyền cả context của node kiểu vào logic xử lý. Cách đặt tên rõ vị trí giúp ngăn việc vô tình áp dụng policy của field cho type argument hoặc ngược lại.

## 13. Quy trình chọn API nhanh

1. **Hỏi annotation gắn vào thực thể hay vào một lần dùng kiểu?** Ví dụ “field có `@Column`?” là declaration; “kiểu phần tử của field là `@NonNull String`?” là type-use.
2. **Kiểm tra annotation type:** `@Target` nào hợp lệ, có `@Retention(RUNTIME)` không, có `@Repeatable` hoặc `@Inherited` không?
3. **Chọn điểm vào:** `Field` / `Method` / `Class` / `Parameter` để đọc declaration; `getAnnotatedType()` / `getAnnotatedReturnType()` / `getAnnotatedParameterTypes()` / `getAnnotatedBounds()` để đọc type-use.
4. **Đi đúng vị trí trong cây kiểu:** parameterized argument, wildcard bound, array component, type-variable bound, annotated owner type khi có.
5. **Xử lý trường hợp absent:** `getAnnotation(...)` trả `null`, các mảng annotation có thể rỗng, `getAnnotatedSuperclass()` có thể trả `null` đối với những kiểu không có superclass áp dụng.
6. **Áp dụng semantics riêng của ứng dụng:** annotation là mô tả, không phải validation tự động; nếu cần thực thi ràng buộc, thiết kế rõ compiler checker/framework/logic tương ứng.

## 14. Tự kiểm tra

**Câu 1:** Trong `@Column List<@NonNull String> names;`, gọi `field.getAnnotation(NonNull.class)` có tìm ra `@NonNull` trên `String` không?

Đáp án: **Không**. Annotation nằm trên type argument; lấy `field.getAnnotatedType()`, cast thành `AnnotatedParameterizedType` và đọc annotated argument thứ nhất.

**Câu 2:** `getGenericType()` và `getAnnotatedType()` khác gì?

Đáp án: `getGenericType()` trả `Type` mô tả generic signature, còn `getAnnotatedType()` trả `AnnotatedType` mô tả lần dùng kiểu và annotation tại các node của kiểu đó, bên cạnh underlying `Type`.

**Câu 3:** `String @A [] values` khác `@A String[] values` ở đâu?

Đáp án: Với `@A` là `TYPE_USE`, dạng thứ nhất gắn annotation vào **kiểu mảng**, dạng thứ hai gắn annotation vào **kiểu phần tử String**. Cần đi qua `AnnotatedArrayType` để phân biệt.

**Câu 4:** `class C<@P T extends @B Number>` dùng API nào cho `@P` và `@B`?

Đáp án: `TypeVariable.getAnnotation(P.class)` cho annotation declaration của `T`; `TypeVariable.getAnnotatedBounds()[0].getAnnotation(B.class)` cho type-use trên bound `Number`.

**Câu 5:** Annotation có cả `@Target({FIELD, TYPE_USE})` đặt trước field type thì nhất định chỉ thuộc một bên?

Đáp án: **Không**. Theo JLS, khi annotation hợp lệ ở cả hai context, nó có thể áp dụng cho cả declaration và type-use gần nhất. Phải xác định target, retention và API phù hợp.

**Câu 6:** `@NonNull String` đã có `RUNTIME` retention thì JVM tự ném exception khi giá trị là `null`?

Đáp án: **Không**. Cần compiler checker, framework hoặc code kiểm tra theo contract riêng.

**Câu 7:** Annotation `@A` gắn vào một kiểu xuất hiện trong cast bên trong method có đọc được chỉ với `Method.getAnnotatedReturnType()` không?

Đáp án: **Không**. Return type là vị trí khác; core reflection không cung cấp đường đi trực tiếp đến từng cast trong method body.

## Tài liệu chuẩn

- [JLS Java SE 21 — `9.6.4.1 @Target` và `9.7.4` nơi annotation xuất hiện](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html)
- [Java SE 21 — `AnnotatedElement`, phân biệt declaration và type annotation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [Java SE 21 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java SE 21 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [Java SE 21 — `AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html)
- [Java SE 21 — `AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html)
- [Java SE 21 — `TypeVariable` và `AnnotatedTypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html)
- [Java SE 21 — `RecordComponent.getAnnotatedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html)
