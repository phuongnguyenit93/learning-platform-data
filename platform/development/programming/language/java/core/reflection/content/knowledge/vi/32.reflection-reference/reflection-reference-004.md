# Bảng tra cứu `Class`, `Type`, `AnnotatedType` và các loại generic trong Java Reflection

## 1. Vì sao cần một bảng phân loại kiểu?

Khi dùng Reflection để viết framework, serializer, trình sinh tài liệu API, bộ kiểm tra schema hoặc công cụ phân tích annotation, câu hỏi không chỉ là “đây là lớp nào?” mà còn là:

- Trường dữ liệu khai báo `List<String>` hay một `List` dùng raw type?
- Tham số `T` được khai báo ở đâu, ràng buộc bởi `extends Number` hay interface nào?
- `List<? extends Number>` và `List<? super Integer>` khác nhau ở biên nào?
- `T[]` và `List<String>[]` có gì khác `String[]`?
- Annotation như `@NotNull` hoặc `@Mark` được đặt **trên cách sử dụng kiểu** ở mức ngoài hay đặt vào type argument?

Java phân biệt ba tầng:

1. `Class<?>`: đại diện cho **kiểu runtime đã được nạp** (lớp, interface, kiểu mảng, primitive, `void`); kiểu generic thường đã bị erasure.
2. `java.lang.reflect.Type` và các subtype: diễn tả **kiểu khai báo** có thành phần generic, ví dụ `List<String>`, `T`, `? extends Number`, `T[]`.
3. `java.lang.reflect.AnnotatedType` và các subtype: diễn tả **một lần sử dụng kiểu có thể mang type-use annotation**, chẳng hạn `List<@Mark String>`. Nó cho phép truy vấn cả kiểu nền qua `getType()` và annotation gắn ở vị trí đó.

**Lưu ý quan trọng:** `AnnotatedType` **không kế thừa `Type`**; hai interface phục vụ hai lớp thông tin khác nhau. `AnnotatedType.getType()` trả lại một `Type` nền để tiếp tục phân tích.

## 2. Sơ đồ mối quan hệ

~~~text
java.lang.reflect.Type
  ├── java.lang.Class<?>              [Class implements Type]
  ├── ParameterizedType               [List<String>, Map<K,V>]
  ├── TypeVariable<D>                 [T, E, K, V]
  ├── WildcardType                     [? extends Number, ? super Integer]
  └── GenericArrayType                [T[], List<String>[]]

java.lang.reflect.AnnotatedElement
  └── AnnotatedType
        ├── AnnotatedParameterizedType
        ├── AnnotatedTypeVariable
        ├── AnnotatedWildcardType
        └── AnnotatedArrayType

AnnotatedType.getType() -> Type
~~~

Sơ đồ chỉ tóm tắt **các interface cần tra cứu**, không thể hiện mọi quan hệ triển khai trong JDK. `Class<?>` vừa triển khai `Type` vừa hỗ trợ các API annotation của `AnnotatedElement`, nhưng một đối tượng `Class<?>` không tự biến thành `AnnotatedType`.

Từ đó, **không** cast `Type` sang `AnnotatedType` theo suy đoán. Bạn phải lấy `AnnotatedType` từ API như `Field.getAnnotatedType()`, `Method.getAnnotatedReturnType()`, `Method.getAnnotatedParameterTypes()` hoặc `Class.getAnnotatedSuperclass()`.

## 3. Bảng nhận diện 5 hình dạng `Type`

| Giá trị kiểu khai báo | Kết quả `Type` thường gặp | API trọng tâm |
| --- | --- | --- |
| `String`, `int`, `String[]`, raw `List` | `Class<?>` | `getName()`, `getTypeName()`, `isArray()`, `getComponentType()`, `getTypeParameters()` |
| `List<String>`, `Map<String,Integer>`, `Parent<Long>` | `ParameterizedType` | `getRawType()`, `getActualTypeArguments()`, `getOwnerType()` |
| `T` của `class Box<T>` | `TypeVariable<?>` | `getName()`, `getBounds()`, `getGenericDeclaration()`, `getAnnotatedBounds()` |
| `?`, `? extends Number`, `? super Integer` | `WildcardType` | `getUpperBounds()`, `getLowerBounds()` |
| `T[]`, `List<String>[]` | `GenericArrayType` | `getGenericComponentType()` |

**Không suy luận bằng `getTypeName()` đơn thuần:** chuỗi kiểu giúp hiển thị, còn `instanceof` trên các interface `Type` cho biết cấu trúc để phân nhánh đúng.

Ví dụ:

~~~java
Type type = field.getGenericType();
if (type instanceof ParameterizedType p) {
    Type raw = p.getRawType();
    Type[] arguments = p.getActualTypeArguments();
} else if (type instanceof TypeVariable<?> variable) {
    Type[] bounds = variable.getBounds();
} else if (type instanceof GenericArrayType array) {
    Type component = array.getGenericComponentType();
} else if (type instanceof Class<?> clazz) {
    boolean isRuntimeArray = clazz.isArray();
}
~~~

*Đây là fragment minh họa: `field` là `java.lang.reflect.Field` đã tìm được và `Type` được import từ `java.lang.reflect`. `WildcardType` thường xuất hiện **bên trong** type argument của một `ParameterizedType`, chứ không nhất thiết trực tiếp là kiểu của cả field.*

### 3.1. `Class<?>`: kiểu runtime, kể cả primitive và array

`String.class`, `int.class`, `List.class`, `String[].class` đều là đối tượng `Class`, đồng thời triển khai `Type`. Đối với `Class` của mảng, `getComponentType()` trả kiểu thành phần ở **một chiều** (ví dụ `String[][].class.getComponentType() == String[].class`).

Đừng nhầm `List.class` với `List<String>`: **không tồn tại** cú pháp `List<String>.class`. Vì erasure, đối tượng `new ArrayList<String>().getClass()` vẫn chỉ cho biết runtime class `ArrayList`, không khôi phục `String` từ chính đối tượng đó.

`Class.getTypeParameters()` có thể mô tả **các biến kiểu khai báo của một generic class**, nhưng `Class<?>` của object **không mang giá trị type argument riêng cho instance**.

### 3.2. `ParameterizedType`: generic type đã được tham số hóa

Với field `List<String> names`, `field.getGenericType()` có thể là `ParameterizedType`:

- `getRawType()` → `List.class` (với ví dụ này).
- `getActualTypeArguments()[0]` → `String.class`.
- `getOwnerType()` → có thể là `null` với kiểu không cần owner; với kiểu lồng trong generic owner, cần quan sát chính xác owner type chứ đừng giả định mọi kiểu lồng đều như nhau.

Type argument **không nhất thiết** là `Class`. Nó có thể là `TypeVariable` (`List<T>`), `WildcardType` (`List<? extends Number>`), một `ParameterizedType` khác (`List<Map<String,Integer>>`) hoặc `GenericArrayType`.

Nếu đọc `ParameterizedType`, hãy **đệ quy** qua `getActualTypeArguments()` khi cần mô tả cấu trúc đầy đủ; dừng ở dạng nền (`Class`) hoặc biến kiểu.

### 3.3. `TypeVariable<?>`: biến kiểu tại nơi khai báo

Ví dụ:

~~~java
class NumericBox<T extends Number & Comparable<T>> {
    T value;
}
~~~

`NumericBox.class.getTypeParameters()[0]` là `TypeVariable` biểu diễn `T`. Nó biết:

- `getName()` → `T`.
- `getGenericDeclaration()` → declaration nơi `T` được giới thiệu (class, method hoặc constructor).
- `getBounds()` → các upper bounds đã khai báo; ở đây là `Number` và `Comparable<T>`.
- `getAnnotatedBounds()` → các bounds cùng type-use annotation nếu có.

Nếu không khai báo bounds, upper bound mặc định là `Object`. `TypeVariable` **không tự biết** rằng ở một subclass nào đó `T` đã được thay bằng `Long`. Muốn biết kiểu của `class LongBox extends NumericBox<Long>`, xem `LongBox.class.getGenericSuperclass()` rồi đọc type argument của `ParameterizedType` trả về.

**Bẫy phổ biến:** cast thẳng `TypeVariable.getBounds()[i]` về `Class` có thể sai, vì `Comparable<T>` được biểu diễn bằng `ParameterizedType`.

### 3.4. `WildcardType`: biên của wildcard

Với `List<? extends Number>`, type argument thứ nhất là `WildcardType`:

- `getUpperBounds()[0]` thường là `Number.class`.
- `getLowerBounds()` là mảng rỗng.

Với `List<? super Integer>`:

- `getLowerBounds()[0]` là `Integer.class`.
- `getUpperBounds()[0]` là `Object.class`.

Với `List<?>`, upper bound mặc định là `Object` và không có lower bound. **Không** suy ra từ một `? super Integer` rằng upper bound là `Integer`; đó là **lower bound**. Các giá trị của `WildcardType` mô tả ràng buộc trong *generic declaration*, không phải nội dung thực tế mà collection runtime đang chứa.

### 3.5. `GenericArrayType`: mảng có component không phải `Class` thuần

`T[]` trong generic class và `List<String>[]` trong chữ ký khai báo là các dạng `GenericArrayType` vì component không thể biểu diễn chỉ bằng một reifiable `Class<?>`.

Trong khi đó `String[]` và `int[][]` là `Class<?>` có `isArray() == true`. Hai API dùng để lấy một cấp thành phần:

| Trường hợp | Kiểu tại runtime Reflection | Lấy component |
| --- | --- | --- |
| `String[]` | `Class<?>` | `((Class<?>) t).getComponentType()` |
| `T[]` | `GenericArrayType` | `((GenericArrayType) t).getGenericComponentType()` |
| `List<String>[]` | `GenericArrayType` | `getGenericComponentType()` trả `ParameterizedType` |
| `List[]` (raw array) | `Class<?>` | `getComponentType()` trả `List.class` |

Java cấm trực tiếp `new List<String>[5]` do generic array creation không hợp lệ; điều đó **không** ngăn khai báo field hoặc tham số có kiểu `List<String>[]` để công cụ Reflection phân tích.

## 4. Bảng `AnnotatedType`: xem annotation nằm ở đâu

| Type-use metadata | Interface tương ứng | API xem thành phần đã chú thích |
| --- | --- | --- |
| Một vị trí sử dụng kiểu bất kỳ | `AnnotatedType` | `getType()`, `getAnnotation(...)`, `getAnnotations()`, `getAnnotatedOwnerType()` |
| `List<@Mark String>` | `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` |
| `T` tại một vị trí dùng generic variable | `AnnotatedTypeVariable` | `getAnnotatedBounds()` |
| `? extends @Mark Number` | `AnnotatedWildcardType` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `String @Mark []`, `T[]` | `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` |

Annotation `@Target(ElementType.TYPE_USE)` có thể đặt lên vị trí sử dụng kiểu, ví dụ type argument hoặc array dimension. Để Reflection đọc được lúc chạy, annotation phải có retention `RetentionPolicy.RUNTIME`. Annotation `CLASS` hoặc `SOURCE` sẽ không hiển thị qua runtime Reflection như annotation có `RUNTIME`.

Cần phân biệt ba vị trí:

~~~java
@Mark("field-type") List<@Mark("argument") String> names;
~~~

*Fragment trên phải nằm trong một class, có định nghĩa `@Mark` dùng `TYPE_USE`; chương trình ở mục 7 cung cấp ví dụ hoàn chỉnh.*

- `Field.getAnnotatedType()` đại diện vị trí **kiểu của field**, trả annotation `field-type`.
- Nếu kiểu là `AnnotatedParameterizedType`, `getAnnotatedActualTypeArguments()[0]` đại diện vị trí **type argument**, nhận `argument`.
- `Field.getDeclaredAnnotations()` là **annotation được khai báo trên field** theo ngữ nghĩa declaration annotations, không thay thế cây `AnnotatedType`. Annotation có target cho cả FIELD và TYPE_USE có thể xuất hiện ở nhiều góc nhìn; hãy chọn API đúng mục đích.

Type-use annotation ở một cấp khác **không tự truyền xuống** type argument hoặc array component. Để biết annotation ở cấp nào, duyệt theo `AnnotatedType`, không chỉ xem kiểu chuỗi từ `getTypeName()`.

## 5. Tìm generic metadata từ đâu?

| Nơi khai báo | Đọc cấu trúc generic `Type` | Đọc type-use annotation |
| --- | --- | --- |
| Field | `Field.getGenericType()` | `Field.getAnnotatedType()` |
| Tham số method | `Method.getGenericParameterTypes()` | `Method.getAnnotatedParameterTypes()` |
| Return type method | `Method.getGenericReturnType()` | `Method.getAnnotatedReturnType()` |
| Ngoại lệ trong `throws` | `Method.getGenericExceptionTypes()` | `Method.getAnnotatedExceptionTypes()` |
| Parameter của constructor | `Constructor.getGenericParameterTypes()` | `Constructor.getAnnotatedParameterTypes()` |
| Generic superclass | `Class.getGenericSuperclass()` | `Class.getAnnotatedSuperclass()` |
| Generic interfaces | `Class.getGenericInterfaces()` | `Class.getAnnotatedInterfaces()` |
| Type parameter trên class | `Class.getTypeParameters()` | `TypeVariable.getAnnotatedBounds()` trên từng biến |
| Type parameter trên method | `Method.getTypeParameters()` | `TypeVariable.getAnnotatedBounds()` trên từng biến |

**Kiểm tra null và độ dài:** `Class.getGenericSuperclass()` có thể trả `null` (chẳng hạn cho `Object` hoặc interface); interface list có thể rỗng. `Method.getGenericExceptionTypes()` có thể rỗng. Khi duyệt annotation của generic superclass, nên xác thực có superclass trước.

Đối với kiểu khai báo trên parameter, `java.lang.reflect.Parameter` cũng cung cấp `getParameterizedType()` và `getAnnotatedType()`. Nếu cần tên parameter, lưu ý `Parameter.isNamePresent()` và tùy chọn biên dịch `-parameters`; không giả định source parameter names luôn được lưu.

## 6. Ví dụ đọc cây generic: lựa chọn nhánh theo `instanceof`

Khi viết công cụ xuất sơ đồ kiểu, hãy phân nhánh theo **hình dạng thực tế**:

~~~java
static String kind(Type type) {
    if (type instanceof Class<?>) return "Class";
    if (type instanceof ParameterizedType) return "ParameterizedType";
    if (type instanceof TypeVariable<?>) return "TypeVariable";
    if (type instanceof WildcardType) return "WildcardType";
    if (type instanceof GenericArrayType) return "GenericArrayType";
    return "Other Type";
}
~~~

*Fragment cần `import java.lang.reflect.*;` và đặt trong một class.*

Một bộ duyệt tổng quát có thể áp dụng:

1. `Class` → lấy `getTypeName()`; nếu là mảng, xử lý `getComponentType()`.
2. `ParameterizedType` → lấy `getRawType()`, `getOwnerType()` (nếu có), rồi duyệt `getActualTypeArguments()` theo thứ tự.
3. `TypeVariable` → lấy `getName()`, `getGenericDeclaration()` và duyệt `getBounds()` nếu muốn hiển thị ràng buộc.
4. `WildcardType` → duyệt upper/lower bounds.
5. `GenericArrayType` → duyệt `getGenericComponentType()` và thêm cấp mảng.

Khi duyệt đệ quy, phải nhận ra khả năng có **chu kỳ tham chiếu** qua biến kiểu, ví dụ `T extends Comparable<T>`. Một thuật toán đi sâu qua `TypeVariable.getBounds()` rồi trở lại `Comparable<T>` có thể tiếp tục gặp chính `T`. Dùng tập đang thăm (*active recursion path*) hoặc giới hạn/đánh dấu những biến kiểu đã xét để tránh đệ quy vô hạn.

Với `AnnotatedType`, cần **duyệt cây annotation song song**, không suy từ `Type` rằng annotation ở mọi cấp đều giống nhau.

## 7. Chương trình Java 17+ hoàn chỉnh: `Type` và `AnnotatedType` cùng lúc

Tạo tệp **`GenericTypeLookupDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.List;

public class GenericTypeLookupDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface Mark {
        String value();
    }

    public static class Holder<T extends Number & Comparable<T>> {
        public @Mark("outer") List<@Mark("element") String> list;
        public List<? extends Number> upper;
        public List<? super Integer> lower;
        public T[] values;
        public List<String>[] genericArray;
        public String[] ordinaryArray;
        public List rawList;
    }

    public static class LongHolder extends Holder<Long> {}

    static String kind(Type t) {
        if (t instanceof Class<?>) return "Class";
        if (t instanceof ParameterizedType) return "ParameterizedType";
        if (t instanceof TypeVariable<?>) return "TypeVariable";
        if (t instanceof WildcardType) return "WildcardType";
        if (t instanceof GenericArrayType) return "GenericArrayType";
        return "Other";
    }

    static Field field(String name) throws NoSuchFieldException {
        return Holder.class.getDeclaredField(name);
    }

    public static void main(String[] args) throws Exception {
        Type list = field("list").getGenericType();
        ParameterizedType parameterized = (ParameterizedType) list;
        System.out.println("list kind: " + kind(list));
        System.out.println("list raw: "
                + parameterized.getRawType().getTypeName());
        System.out.println("list argument: "
                + parameterized.getActualTypeArguments()[0].getTypeName());

        TypeVariable<?> variable = Holder.class.getTypeParameters()[0];
        System.out.println("variable: " + variable.getName());
        System.out.println("variable bounds: " + variable.getBounds().length);
        System.out.println("first bound: "
                + variable.getBounds()[0].getTypeName());

        WildcardType upper = (WildcardType)
                ((ParameterizedType) field("upper").getGenericType())
                        .getActualTypeArguments()[0];
        WildcardType lower = (WildcardType)
                ((ParameterizedType) field("lower").getGenericType())
                        .getActualTypeArguments()[0];
        System.out.println("upper bound: "
                + upper.getUpperBounds()[0].getTypeName());
        System.out.println("lower bound: "
                + lower.getLowerBounds()[0].getTypeName());

        Type values = field("values").getGenericType();
        System.out.println("T[] kind: " + kind(values));
        System.out.println("T[] component kind: " + kind(
                ((GenericArrayType) values).getGenericComponentType()));
        System.out.println("List<String>[] kind: "
                + kind(field("genericArray").getGenericType()));
        System.out.println("String[] kind: "
                + kind(field("ordinaryArray").getGenericType()));
        System.out.println("raw List kind: "
                + kind(field("rawList").getGenericType()));

        AnnotatedType annotated = field("list").getAnnotatedType();
        Mark outer = annotated.getAnnotation(Mark.class);
        AnnotatedType argument = ((AnnotatedParameterizedType) annotated)
                .getAnnotatedActualTypeArguments()[0];
        Mark element = argument.getAnnotation(Mark.class);
        System.out.println("outer annotation: " + outer.value());
        System.out.println("argument annotation: " + element.value());

        Type base = LongHolder.class.getGenericSuperclass();
        Type supplied = ((ParameterizedType) base)
                .getActualTypeArguments()[0];
        System.out.println("subclass binds T to: "
                + supplied.getTypeName());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac GenericTypeLookupDemo.java
java GenericTypeLookupDemo
~~~

Kết quả:

~~~text
list kind: ParameterizedType
list raw: java.util.List
list argument: java.lang.String
variable: T
variable bounds: 2
first bound: java.lang.Number
upper bound: java.lang.Number
lower bound: java.lang.Integer
T[] kind: GenericArrayType
T[] component kind: TypeVariable
List<String>[] kind: GenericArrayType
String[] kind: Class
raw List kind: Class
outer annotation: outer
argument annotation: element
subclass binds T to: java.lang.Long
~~~

Bài học từ output:

- `field.getGenericType()` giữ `List<String>` dưới dạng `ParameterizedType`; type argument thứ nhất là `Class<String>`.
- `T` của `Holder<T extends Number & Comparable<T>>` là `TypeVariable` có **hai bounds**; một trong số đó là `Comparable<T>`, bản thân là `ParameterizedType`.
- Wildcard lấy bounds qua `WildcardType`, không phải qua `TypeVariable`.
- `T[]` và `List<String>[]` là `GenericArrayType`, còn `String[]` là `Class`.
- `List` raw type của field là `Class`, không phải `ParameterizedType`.
- `AnnotatedType` của field giữ `@Mark("outer")`; annotation trên type argument được lấy ở cấp `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`.
- `LongHolder.class.getGenericSuperclass()` mô tả `Holder<Long>`; từ đó mới lấy được `Long` đã gắn với type parameter `T` tại quan hệ kế thừa này.

Đây là ví dụ **khám phá metadata từ declaration**, không suy đoán type argument của `new ArrayList<String>()` tại runtime.

## 8. Bảng API `AnnotatedType` mở rộng

Các subtype của `AnnotatedType` phản ánh hình dạng kiểu ở từng vị trí. Một số điểm cần kiểm tra kỹ khi triển khai:

### 8.1. `AnnotatedParameterizedType`

Với `List<@Mark String>`, gọi `getAnnotatedActualTypeArguments()` để lấy từng type argument cùng annotation tương ứng. Nếu type argument lại là `Map<@Mark String, @Mark Integer>`, các phần tử bên trong có thể tiếp tục là `AnnotatedParameterizedType`. Đừng chỉ nhìn annotation ngoài cùng rồi bỏ mất annotation lồng.

### 8.2. `AnnotatedTypeVariable`

Khi một vị trí sử dụng kiểu là biến `T`, hình dạng annotated type có thể là `AnnotatedTypeVariable`. API `getAnnotatedBounds()` cho phép đọc annotation gắn vào bounds của biến. Cần nhớ type-use annotation ở **chỗ dùng** `T` và annotation ở **chỗ khai báo bound** là hai vị trí khác nhau.

### 8.3. `AnnotatedWildcardType`

Với `List<? extends @Mark Number>`, annotation ở `Number` được đọc từ `getAnnotatedUpperBounds()` của `AnnotatedWildcardType` bên trong annotated parameterized type. Tương tự, `? super @Mark Integer` dùng `getAnnotatedLowerBounds()`.

Điểm cần phân biệt: `WildcardType.getUpperBounds()` chỉ trả `Type[]`; nếu muốn annotation trên chính kiểu bound, cần nhánh `AnnotatedWildcardType`.

### 8.4. `AnnotatedArrayType`

Java cho phép type-use annotation tại **mỗi cấp mảng**; ví dụ cú pháp `String @Mark []` gắn annotation vào một vị trí mảng. `AnnotatedArrayType.getAnnotatedGenericComponentType()` đi vào cấp phần tử tiếp theo, có thể là một `AnnotatedArrayType` khác hoặc một `AnnotatedType` đại diện base component. Với mảng nhiều chiều, không đánh đồng annotation trên `[]` ngoài và annotation trên kiểu phần tử cuối.

### 8.5. `getAnnotatedOwnerType()`

Khi kiểu có owner (ví dụ một inner type nằm trong một kiểu bao), `AnnotatedType.getAnnotatedOwnerType()` (Java 9+) có thể cho biết annotated owner type hoặc `null` nếu không áp dụng. Không giả định mọi `ParameterizedType` đều có owner, hoặc owner luôn là `Class<?>`.

## 9. Phân biệt metadata generic, runtime erasure và reifiability

`Type` giúp đọc những gì còn lưu trong **generic signature** của field, method, constructor hoặc superclass. Nhưng Java generic vẫn chịu **type erasure** trong nhiều thao tác runtime.

Ví dụ:

~~~java
List<String> strings = new java.util.ArrayList<>();
List<Integer> numbers = new java.util.ArrayList<>();

boolean sameRuntimeClass =
        strings.getClass() == numbers.getClass(); // true
~~~

*Fragment này cần import `java.util.List` và đặt trong ngữ cảnh cho phép khai báo biến.*

Hai object đều là instance của cùng runtime class `ArrayList`; chỉ dựa `object.getClass()` không thể biết một biến source được khai báo `List<String>` hay `List<Integer>`.

Một số lưu ý:

- Generic type argument được lưu tại **vị trí khai báo** thích hợp; không phải mọi thông tin generic đều tồn tại sau compilation, và compiler có thể bỏ thông tin không được phát ra dưới dạng chữ ký có thể đọc.
- `List<String>.class` không hợp lệ; `List.class` hợp lệ.
- `instanceof List<String>` không hợp lệ trong Java thông thường vì dạng đó không reifiable; `instanceof List<?>` có thể hợp lệ.
- `String[]` có runtime array class riêng (`String[].class`), nhưng `List<String>[]` là khai báo kiểu generic array; không thể tạo trực tiếp `new List<String>[3]`.
- `Type.getTypeName()` tiện cho log, nhưng **không phải định danh runtime toàn cục**. Hai class cùng binary name được nạp bởi hai defining class loader khác nhau vẫn là các kiểu khác nhau.

Khi API có thể trả `TypeVariable` hoặc `ParameterizedType`, **đừng ép kiểu bừa sang `Class<?>`**. Nếu phải lấy runtime class gần đúng, cần một quy tắc rõ về erasure/bounds và ý nghĩa với wildcard; việc đơn giản hóa này có thể làm mất thông tin và không phù hợp để tái dựng chính xác generic signature.

## 10. Lỗi thường gặp khi xây bộ tra cứu

| Sai lầm | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Cast mọi `Field.getGenericType()` sang `Class<?>` | Field generic có thể là `ParameterizedType`, `TypeVariable`, `GenericArrayType` | Phân nhánh `instanceof` theo `Type` |
| Dùng `Field.getType()` để đọc `List<String>` | `getType()` phản ánh kiểu erasure `List.class` | Dùng `getGenericType()` |
| Dùng `getClass()` của object để suy ra `List<String>` | Erasure xóa type argument ở object runtime class | Đọc generic declaration/signature nếu có |
| Cho rằng `? super Integer` có upper bound `Integer` | `Integer` là **lower bound** | Xem `getLowerBounds()` và `getUpperBounds()` |
| Coi `T[]` luôn là `Class` | Component `T` không reifiable | Dùng `GenericArrayType` khi Reflection trả dạng này |
| Dùng `getDeclaredAnnotations()` để tìm mọi type-use annotation | Declaration annotations và annotation trên cây type-use khác vị trí | Dùng `getAnnotatedType()` rồi duyệt annotated arguments/bounds |
| Bỏ qua type-use annotation ở type argument | Annotation có thể nằm bên trong generic nesting | Duyệt `AnnotatedParameterizedType` |
| Duyệt bounds `T extends Comparable<T>` vô hạn | Quay lại cùng type variable `T` | Theo dõi những biến đang duyệt |
| Dùng `getSimpleName()` làm khóa cho mọi kiểu | Dễ trùng package; kiểu local/anonymous khó mô tả | Dùng key có cấu trúc và namespace phù hợp |
| Tin rằng annotation SOURCE/CLASS hiện diện lúc chạy | Retention không phải `RUNTIME` | Chỉ kỳ vọng các annotation được lưu để runtime Reflection đọc |
| Bỏ qua lỗi generic signature | Metadata bytecode có thể thiếu dependency hoặc signature không hợp lệ | Xử lý `TypeNotPresentException`, `MalformedParameterizedTypeException`, `GenericSignatureFormatError` theo ngữ cảnh |

Một framework nên tách **khâu phát hiện kiểu**, **đọc annotation theo vị trí**, **chuẩn hóa/hiển thị**, **giải quyết tên class** và **xử lý lỗi** thành những bước độc lập để dễ kiểm tra.

## 11. Chọn API theo câu hỏi thực tế

- **“Tôi cần biết field có runtime class gì?”** → `Field.getType()`.
- **“Tôi cần biết field khai báo `List<String>` hay `List<T>`?”** → `Field.getGenericType()` rồi phân nhánh `Type`.
- **“Tôi cần annotation trên kiểu của field và trong type argument?”** → `Field.getAnnotatedType()`; duyệt `AnnotatedParameterizedType` hoặc subtype tương ứng.
- **“Tôi cần generic return type của method?”** → `Method.getGenericReturnType()`.
- **“Tôi cần type-use annotation trên giá trị trả về?”** → `Method.getAnnotatedReturnType()`.
- **“Tôi cần bounds của generic parameter `T`?”** → `Class.getTypeParameters()` hoặc `Method.getTypeParameters()` rồi `TypeVariable.getBounds()` / `getAnnotatedBounds()`.
- **“Tôi muốn xem `T` trong superclass được gắn với `Long` như thế nào?”** → `Subclass.class.getGenericSuperclass()` và `ParameterizedType.getActualTypeArguments()`.
- **“Tôi muốn phân biệt `? extends X` với `? super X`?”** → `WildcardType.getUpperBounds()` / `getLowerBounds()`.
- **“Tôi cần xử lý `T[]`?”** → `GenericArrayType.getGenericComponentType()`.
- **“Tôi cần xem array type reifiable `String[]`?”** → `Class.isArray()` / `Class.getComponentType()`.
- **“Tôi muốn giữ đầy đủ nested annotation?”** → xây traversal song song giữa `AnnotatedType` và `Type`, không chỉ dùng một chuỗi tên.

## 12. Gợi ý kiểm thử bộ duyệt kiểu trong dự án

Để bộ phân tích generic hoạt động đáng tin, nên có fixture bao gồm:

1. **Raw và parameterized:** `List`, `List<String>`, `Map<String, List<Integer>>`.
2. **Type variable:** `class Box<T>`, `<T extends Number & Comparable<T>>`.
3. **Wildcard:** `List<?>`, `List<? extends Number>`, `List<? super Integer>`.
4. **Array:** `String[]`, `T[]`, `List<String>[]`.
5. **Type-use annotation nhiều cấp:** `@Mark List<@Mark String>`, annotation ở wildcard bound và array dimension.
6. **Subclass substitution:** `class StringBox extends Box<String>`.
7. **Nesting và owner:** generic member type khi code của bạn hỗ trợ.
8. **Null/rỗng:** class không có generic superclass, không có type parameters, annotation không có retention runtime.
9. **Malformed/missing types:** nếu công cụ đọc bytecode ngoài kiểm soát, xử lý lỗi phản chiếu thay vì crash không rõ nguyên nhân.
10. **Chu kỳ bounds:** `T extends Comparable<T>` không làm traversal đệ quy vô hạn.

Assertion nên dựa vào **hình dạng `Type`, tên/bounds và đúng vị trí annotation** thay vì dựa vào chuỗi `toString()` tình cờ, thứ tự không được đảm bảo của mảng members hay class loader identity hash code.

## 13. Tự kiểm tra

1. `Class<?>` có triển khai `Type` không? **Có.**
2. `AnnotatedType` có phải subtype của `Type` không? **Không; `getType()` trả `Type` nền.**
3. `List<String>` thường được mô tả bằng interface nào khi gọi `Field.getGenericType()`? **`ParameterizedType`.**
4. `List<?>` chứa kiểu gì trong `getActualTypeArguments()[0]`? **`WildcardType`.**
5. `T` của `class Box<T>` là interface gì? **`TypeVariable<?>`.**
6. `T[]` có nhất thiết là `Class<?>` không? **Không; nó thường là `GenericArrayType`.**
7. `String[]` thì sao? **`Class<?>` với `isArray() == true`.**
8. Trong `List<@Mark String>`, lấy annotation của type argument bằng API nào? **`AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0].getAnnotation(Mark.class)`.**
9. `? super Integer` có lower bound là gì? **`Integer.class`; upper bound mặc định thường là `Object.class`.**
10. `new ArrayList<String>().getClass()` có trực tiếp biết `String` không? **Không; generic type argument bị erasure khỏi runtime class của object.**
11. Với `T extends Comparable<T>`, tại sao traversal ngây thơ có thể vòng lặp? **Bounds lại tham chiếu cùng `TypeVariable T`.**
12. `@Target(TYPE_USE)` đủ để Reflection đọc annotation lúc chạy chưa? **Chưa; cần retention `RUNTIME`.**

## 14. Kết luận

Hãy bắt đầu bằng **nguồn khai báo**: đọc `getGenericType` / `getGenericReturnType` / `getGenericSuperclass` khi cần cấu trúc kiểu, và đọc `getAnnotatedType` / `getAnnotatedReturnType` / `getAnnotatedSuperclass` khi cần annotation theo **vị trí sử dụng kiểu**. Sau đó phân nhánh đúng theo `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`; song song duyệt các subtype `AnnotatedType` để không làm mất annotation ở type argument, wildcard bound hoặc chiều mảng. Việc đọc generic signature từ Reflection giúp hiểu declaration, **không xóa được quy tắc type erasure** của đối tượng runtime.

### Tài liệu tham khảo

- [Java SE 21 — `Type`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Type.html)
- [Java SE 21 — `ParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html)
- [Java SE 21 — `TypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html)
- [Java SE 21 — `WildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/WildcardType.html)
- [Java SE 21 — `GenericArrayType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/GenericArrayType.html)
- [Java SE 21 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java SE 21 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [Java SE 21 — `AnnotatedTypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedTypeVariable.html)
- [Java SE 21 — `AnnotatedWildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedWildcardType.html)
- [Java SE 21 — `AnnotatedArrayType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedArrayType.html)
