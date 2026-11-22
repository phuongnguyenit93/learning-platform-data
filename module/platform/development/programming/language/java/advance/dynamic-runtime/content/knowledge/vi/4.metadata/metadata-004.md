# 4.4 Đọc kiểu generic khai báo qua Type, ParameterizedType và TypeVariable

Java generics cho phép khai báo những kiểu như `List<String>`, `Map<String, List<Integer>>`, `Repository<T>` hoặc `T extends Number`. Sau khi biên dịch, phần lớn thao tác với generic chịu ảnh hưởng của **type erasure**, nhưng nhiều **thông tin kiểu được viết trong chữ ký khai báo** vẫn lưu lại trong metadata của class và có thể đọc bằng Reflection.

Bài này tập trung vào ba API cốt lõi: `java.lang.reflect.Type` (đầu mối biểu diễn kiểu), `ParameterizedType` (kiểu đã được khai báo với đối số generic) và `TypeVariable` (tham số kiểu như `T` hoặc `E`). Để đọc đúng cây kiểu phức tạp, ta cũng cần nhận biết `WildcardType`, `GenericArrayType` và `Class<?>`.

## 1. Phân biệt kiểu generic **khai báo** và kiểu của đối tượng lúc chạy

Xét chương trình:

~~~java
List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
System.out.println(names.getClass() == numbers.getClass()); // true
~~~

Cả hai đối tượng đều có runtime class `java.util.ArrayList`. `getClass()` **không thể nói** một instance là `ArrayList<String>` hay `ArrayList<Integer>` vì kiểu đối số trong việc tạo instance thông thường đã bị xóa ở runtime. `ArrayList<String>.class` cũng không phải cú pháp Java hợp lệ.

Tuy nhiên, trường khai báo `List<String> names;`, phương thức trả về `Map<String, Integer>` và lớp con khai báo `extends Box<Long>` thường có **generic signature** trong class file. Các API `getGeneric...()` dùng chữ ký đó để tái dựng cấu trúc kiểu khai báo; kết quả không nói nội dung thực của một danh sách đang chứa những đối tượng gì.

Ví dụ:

~~~java
class Holder<T> {
    List<String> names;
    T current;
}
~~~

Với `Holder.class.getDeclaredField("names").getGenericType()`, ta có thể thấy `List<String>`; với field `current`, ta thấy **`T`**, chưa phải `String` hay `Integer`. Reflection giữ chính xác sự khác biệt giữa một đối số kiểu cụ thể trong khai báo và một biến kiểu chờ được gắn ở một ngữ cảnh khác.

## 2. Hệ kiểu của Reflection: Type là một interface

`Type` là interface trong `java.lang.reflect`, cung cấp `getTypeName()` để mô tả kiểu. Một `Type` không nhất thiết là `Class<?>`. Các trường hợp thường gặp:

| Dạng Type | Đọc được gì? | Ví dụ |
| --- | --- | --- |
| `Class<?>` | Kiểu cụ thể, raw class, primitive hoặc mảng reifiable | `String.class`, `List.class`, `int.class`, `String[].class` |
| `ParameterizedType` | Raw type, đối số generic, owner type | `List<String>`, `Map<String, List<Integer>>` |
| `TypeVariable<?>` | Biến kiểu được khai báo, nơi khai báo và bounds | `T` trong `class Box<T>`, `R` trong `<R> R read()` |
| `WildcardType` | Wildcard cùng upper/lower bounds | `? extends Number`, `? super Integer` |
| `GenericArrayType` | Mảng có component type không reifiable | `T[]`, `List<String>[]` |

`Type` là **kiểu chung để đi qua cây metadata**, còn `Class<?>` là **một** dạng triển khai của `Type`. Khi đọc kết quả Reflection, sử dụng `instanceof` để xác định nhánh:

~~~java
static void describe(Type type) {
    if (type instanceof ParameterizedType p) {
        System.out.println("Parameterized: " + p.getTypeName());
    } else if (type instanceof TypeVariable<?> variable) {
        System.out.println("Variable: " + variable.getName());
    } else if (type instanceof WildcardType wildcard) {
        System.out.println("Wildcard: " + wildcard.getTypeName());
    } else if (type instanceof GenericArrayType array) {
        System.out.println("Array: " + array.getGenericComponentType().getTypeName());
    } else if (type instanceof Class<?> concrete) {
        System.out.println("Class: " + concrete.getName());
    }
}
~~~

Đoạn trên là **phương thức minh họa**: đặt trong một class và import `java.lang.reflect.*` rồi mới chạy. Trong Java 17+, pattern matching `instanceof` như `type instanceof ParameterizedType p` là hợp lệ. Không cast mọi kết quả `Type` thành `ParameterizedType`; kiểu không có đối số generic (hoặc raw type) có thể là `Class<?>`.

## 3. Những điểm đọc metadata generic trong Reflection

| Nguồn khai báo | API đọc generic | API đọc kiểu đã erasure / đối chiếu |
| --- | --- | --- |
| Một field | `Field.getGenericType()` | `Field.getType()` |
| Kiểu cha trực tiếp của class | `Class.getGenericSuperclass()` | `Class.getSuperclass()` |
| Interface được class khai báo trực tiếp | `Class.getGenericInterfaces()` | `Class.getInterfaces()` |
| Các tham số kiểu khai báo trên class/interface | `Class.getTypeParameters()` | Không có counterpart thông tin generic |
| Kiểu trả về của method | `Method.getGenericReturnType()` | `Method.getReturnType()` |
| Tham số của method/constructor | `Executable.getGenericParameterTypes()` | `Executable.getParameterTypes()` |
| Các biến kiểu do method/constructor khai báo | `Method.getTypeParameters()` / `Constructor.getTypeParameters()` | Không áp dụng |
| Exception khai báo trên method/constructor | `Executable.getGenericExceptionTypes()` | `Executable.getExceptionTypes()` |
| Component của record (Java 16+) | `RecordComponent.getGenericType()` | `RecordComponent.getType()` |

`getDeclaredField` / `getDeclaredMethod` chỉ tìm thành viên **được khai báo ở lớp đó**. Ví dụ lớp con không khai báo lại field kế thừa thì `Child.class.getDeclaredField("item")` thất bại, dù class cha có `item`; hãy đọc field ở lớp sở hữu khai báo hoặc duyệt superclass hợp lệ.

`getGenericSuperclass()` có thể trả `Class<?>` (kế thừa raw/không parameterized), `ParameterizedType` hoặc `null` (ví dụ `Object`/interface). `getGenericInterfaces()` trả mảng `Type[]` có thể chứa những dạng khác nhau. `getTypeParameters()` trả các **biến kiểu được khai báo tại chính class/method**, không phải đối số đã truyền trong một lớp con.

## 4. Đọc ParameterizedType: raw type, actual arguments và owner type

Nếu một class khai báo:

~~~java
class Archive {
    Map<String, List<Long>> entries;
}
~~~

thì:

~~~java
Type declared = Archive.class.getDeclaredField("entries").getGenericType();
ParameterizedType outer = (ParameterizedType) declared;

Type raw = outer.getRawType();                  // interface java.util.Map
Type[] args = outer.getActualTypeArguments(); // String.class, List<Long>
Type owner = outer.getOwnerType();             // null đối với Map top-level
~~~

Ở đây `outer.getRawType()` là kiểu `Map` (đối tượng `Class<?>` trong trường hợp này); `args[0]` là `String.class`; `args[1]` lại là một `ParameterizedType` biểu diễn `List<Long>`. Vì đối số cũng là `Type`, muốn tìm `Long` phải **đi thêm một tầng** qua `((ParameterizedType) args[1]).getActualTypeArguments()[0]`.

Ba phương thức chính của `ParameterizedType`:

1. **`getRawType()`**: phần kiểu nguyên gốc, ví dụ `Map.class` cho `Map<String, Long>`. Thông thường là một `Class<?>`, nhưng return type của API là `Type` nên cần kiểm tra khi xây tiện ích tổng quát.
2. **`getActualTypeArguments()`**: mảng `Type[]` của những đối số generic xuất hiện trong chữ ký. Phần tử có thể là `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`.
3. **`getOwnerType()`**: kiểu chứa đối với nested/member type; `null` nếu kiểu không có owner. Với non-static member class của generic outer class, owner cũng có thể là một `ParameterizedType` và giữ đối số của outer class.

Không giả định mọi `ParameterizedType` luôn có ít nhất một actual argument: một kiểu thành viên không khai báo tham số riêng vẫn có thể có owner được parameterize. Cũng không lấy `getTypeName()` rồi tách chuỗi bằng dấu phẩy hay dấu `<...>`: generic có thể lồng nhiều tầng; phải duyệt cấu trúc `Type`.

## 5. Đọc TypeVariable: biến kiểu, nơi khai báo và giới hạn

Trong khai báo:

~~~java
class Box<T extends Number & Comparable<T>> {
    T value;

    <R extends CharSequence> R identity(R input) {
        return input;
    }
}
~~~

`T` và `R` là hai `TypeVariable` **khác nhau**, dù cả hai đều biểu diễn một vị trí kiểu chưa biết trước. `Box.class.getTypeParameters()` trả `T`; `Method.getTypeParameters()` trên `identity` trả `R`.

`TypeVariable<D extends GenericDeclaration>` có các phương thức:

- `getName()`: tên được khai báo, ví dụ `"T"`, `"R"`.
- `getGenericDeclaration()`: đối tượng khai báo nó (một `Class`, `Method` hoặc `Constructor`), giúp biết `T` thuộc phạm vi nào.
- `getBounds()`: `Type[]` chứa upper bounds theo thứ tự khai báo. Với `T extends Number & Comparable<T>`, có hai bounds: `Number.class` và `Comparable<T>` (`ParameterizedType`).
- `getAnnotatedBounds()`: khi cần cả type-use annotations đặt trên bounds.

Nếu không viết bound, `<T>` mặc định có bound `Object`. Với F-bound đệ quy như `E extends Enum<E>`, cây `Type` có thể quay lại `E`; code duyệt cây cần giới hạn chu trình. Các `TypeVariable` có cùng **tên chữ** nhưng từ hai nơi khai báo khác nhau không đại diện cùng biến kiểu; khi lập ánh xạ kiểu, dùng identity/declaration thay vì chỉ string `"T"`.

`TypeVariable` chỉ nói “có một biến `T` ở đây”, **không tự tra được kiểu gắn vào `T` trong mọi object**. Muốn xác định `T = Integer` cho `class IntBox extends Box<Integer>`, phải đọc chữ ký generic của lớp con rồi đối chiếu biến của lớp cha với đối số cụ thể.

## 6. Ví dụ đầy đủ: đọc cây Type ở class, field và method

Tạo file **GenericMetadataDemo.java** (Java 17+):

~~~java
import java.lang.reflect.*;
import java.util.*;

public class GenericMetadataDemo {
    static class Bucket<T extends Number & Comparable<T>> {
        Map<String, List<T>> index;
        List<? extends T> samples;
        T[] items;

        public <R extends CharSequence> List<R> echo(R value) {
            return List.of(value);
        }
    }

    static class IntegerBucket extends Bucket<Integer> {
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        TypeVariable<?> t = Bucket.class.getTypeParameters()[0];
        System.out.println("type variable: " + t.getName());
        System.out.println("declared by: " +
                ((Class<?>) t.getGenericDeclaration()).getSimpleName());
        System.out.println("bound[0]: " + t.getBounds()[0].getTypeName());
        System.out.println("bound[1]: " + t.getBounds()[1].getTypeName());

        ParameterizedType superType = (ParameterizedType)
                IntegerBucket.class.getGenericSuperclass();
        System.out.println("parent raw: " +
                ((Class<?>) superType.getRawType()).getSimpleName());
        System.out.println("parent arg: " +
                superType.getActualTypeArguments()[0].getTypeName());

        Field field = Bucket.class.getDeclaredField("index");
        System.out.println("field erased: " + field.getType().getTypeName());
        ParameterizedType mapType = (ParameterizedType) field.getGenericType();
        System.out.println("field generic: " + mapType.getTypeName());

        Type nested = mapType.getActualTypeArguments()[1];
        Type nestedArg =
                ((ParameterizedType) nested).getActualTypeArguments()[0];
        System.out.println("inner arg: " + nestedArg.getTypeName());

        ParameterizedType listType = (ParameterizedType)
                Bucket.class.getDeclaredField("samples").getGenericType();
        WildcardType wildcard = (WildcardType)
                listType.getActualTypeArguments()[0];
        System.out.println("wildcard upper: " +
                wildcard.getUpperBounds()[0].getTypeName());

        Type arrayType = Bucket.class.getDeclaredField("items").getGenericType();
        System.out.println("is generic array: " +
                (arrayType instanceof GenericArrayType));
        System.out.println("array component: " +
                ((GenericArrayType) arrayType)
                        .getGenericComponentType().getTypeName());

        Method method = Bucket.class.getDeclaredMethod("echo", CharSequence.class);
        TypeVariable<Method> r = method.getTypeParameters()[0];
        System.out.println("method variable: " + r.getName());
        System.out.println("method bound: " + r.getBounds()[0].getTypeName());
        System.out.println("method parameter: " +
                method.getGenericParameterTypes()[0].getTypeName());
        System.out.println("method return: " +
                method.getGenericReturnType().getTypeName());
    }
}
~~~

Biên dịch/chạy trong thư mục chứa file:

~~~bash
javac GenericMetadataDemo.java
java GenericMetadataDemo
~~~

Stdout:

~~~text
type variable: T
declared by: Bucket
bound[0]: java.lang.Number
bound[1]: java.lang.Comparable<T>
parent raw: Bucket
parent arg: java.lang.Integer
field erased: java.util.Map
field generic: java.util.Map<java.lang.String, java.util.List<T>>
inner arg: T
wildcard upper: T
is generic array: true
array component: T
method variable: R
method bound: java.lang.CharSequence
method parameter: R
method return: java.util.List<R>
~~~

### Phân tích kết quả từng nhánh

**Nhánh class:** `Bucket.class.getTypeParameters()[0]` tạo `TypeVariable` cho `T`. Bound đầu là `Number` (`Class`); bound thứ hai là `Comparable<T>` (`ParameterizedType`). `IntegerBucket.class.getGenericSuperclass()` lại chứa `Bucket<Integer>`, vì vậy `getActualTypeArguments()[0]` là `Integer.class`. Đây là nơi tìm được đối số đã gắn khi khai báo lớp con.

**Nhánh field:** `field.getType()` nhìn thấy `Map.class` vì erasure, trong khi `field.getGenericType()` nhìn thấy `Map<String, List<T>>`. Đối số thứ nhất là `String.class` và đối số thứ hai là `ParameterizedType` cho `List<T>`. Lúc đi vào `List<T>`, ta nhận lại `TypeVariable T`, **không tự đổi thành `Integer`**.

**Nhánh wildcard:** field `samples` được khai báo `List<? extends T>`. Bên trong `ParameterizedType` có `WildcardType`; `getUpperBounds()[0]` là `TypeVariable T`. Wildcard cũng có `getLowerBounds()`, thường rỗng với `? extends ...`.

**Nhánh mảng:** `items` có kiểu `T[]`; `getGenericType()` cho `GenericArrayType`, component type là biến `T`. Trái lại `String[].class` là một `Class<?>` vì kiểu phần tử đã xác định và có thể reify.

**Nhánh method:** `echo` khai báo riêng `R extends CharSequence`. Khi tìm method bằng `getDeclaredMethod` phải dùng **erased parameter class** `CharSequence.class`, không truyền `R` (không có class token cho type variable). `getGenericParameterTypes()[0]` vẫn trả `R` và `getGenericReturnType()` giữ chữ ký `List<R>`.

## 7. Tình huống quan trọng: map TypeVariable sang actual type trong lớp con

Xét hai khai báo:

~~~java
class Container<T> {
    List<T> values;
}

class StringContainer extends Container<String> {
}
~~~

Reflection hoạt động theo **ngữ cảnh khai báo**:

- `Container.class.getDeclaredField("values").getGenericType()` trả `List<T>`, vì field được khai báo ở `Container<T>`.
- `StringContainer.class.getGenericSuperclass()` trả `Container<String>`, bên trong có một actual argument `String.class`.
- `Container.class.getTypeParameters()[0]` trả `TypeVariable T` thuộc `Container`.
- Để diễn giải field của `Container` trong ngữ cảnh `StringContainer`, cần ghép ánh xạ **`Container.T → String.class`**, rồi thay `T` bên trong `List<T>` thành `String`.

Java Reflection **không có API chuẩn tự động resolve mọi field của class cha thành `List<String>`** chỉ bằng `field.getGenericType()`. Một bộ giải kiểu thực tế phải:

1. Đi qua `getGenericSuperclass()` và `getGenericInterfaces()` theo chuỗi thừa kế.
2. Ở mỗi `ParameterizedType`, lấy `getRawType()`, các `getTypeParameters()` của raw class và `getActualTypeArguments()` để xây ánh xạ tương ứng.
3. Thay `TypeVariable` theo **GenericDeclaration + biến kiểu**, kể cả bên trong `ParameterizedType`, `WildcardType` và `GenericArrayType`.
4. Xử lý các tầng trung gian như `class Mid<U> extends Container<List<U>>`, thay biến theo nhiều vòng, tránh vòng lặp từ recursive bounds, và quyết định cách biểu diễn những biến vẫn chưa được gắn.

Chú ý: `StringContainer.class.getDeclaredField("values")` thất bại với `NoSuchFieldException` vì field chỉ **được khai báo ở lớp cha**. Tìm đúng field ở `Container.class`, sau đó áp dụng ánh xạ kiểu theo chuỗi thừa kế.

Nếu cần resolver tổng quát, nên cân nhắc API của framework đã được kiểm thử (ví dụ công cụ xử lý `ResolvableType` của Spring) thay vì tự viết một resolver thiếu xử lý owner type, wildcard và multi-level inheritance. Trong bài này, trọng tâm là hiểu chính xác dữ liệu mà Java Reflection thực sự trả về.

## 8. Giữ generic type token bằng anonymous subclass

Một object `new ArrayList<String>()` không mang `String` trong `getClass()`. Tuy vậy, **một anonymous subclass được khai báo với generic superclass cụ thể** có thể mang dấu vết `T` trong metadata superclass. Đây là nền tảng của mẫu *type token/type reference* được dùng bởi nhiều thư viện JSON và serialization.

Tạo file **TypeCaptureDemo.java**:

~~~java
import java.lang.reflect.*;
import java.util.*;

public class TypeCaptureDemo {
    abstract static class TypeRef<T> {
        private final Type captured;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType p)) {
                throw new IllegalStateException("Subclass must bind T directly");
            }
            captured = p.getActualTypeArguments()[0];
        }

        public final Type getType() {
            return captured;
        }
    }

    public static void main(String[] args) {
        Type captured = new TypeRef<Map<String, List<Integer>>>() {
        }.getType();

        System.out.println("captured: " + captured.getTypeName());
        ParameterizedType map = (ParameterizedType) captured;
        System.out.println("raw: " + map.getRawType().getTypeName());
        System.out.println("key: " +
                map.getActualTypeArguments()[0].getTypeName());
        System.out.println("value: " +
                map.getActualTypeArguments()[1].getTypeName());

        List<String> list = new ArrayList<>();
        System.out.println("instance: " + list.getClass().getTypeName());
    }
}
~~~

~~~bash
javac TypeCaptureDemo.java
java TypeCaptureDemo
~~~

Stdout:

~~~text
captured: java.util.Map<java.lang.String, java.util.List<java.lang.Integer>>
raw: java.util.Map
key: java.lang.String
value: java.util.List<java.lang.Integer>
instance: java.util.ArrayList
~~~

**Vì sao capture thành công?** Anonymous class ở `new TypeRef<Map<String, List<Integer>>>() {}` là một lớp con thực sự, với generic superclass khai báo `TypeRef<Map<String, List<Integer>>>`. Constructor `TypeRef` đọc `getClass().getGenericSuperclass()` của anonymous subclass và lấy đối số. Đây là **metadata trên class được tạo**, không phải khôi phục tùy ý type argument từ một instance `ArrayList` thông thường.

**Hai giới hạn:** (1) Subclass phải gắn `T` **trực tiếp** trong generic superclass mà code trên đọc; nếu có lớp trung gian, phải duyệt chuỗi superclass. (2) Với mã chạy trong một phương thức generic `<X>`, biểu thức `new TypeRef<List<X>>() {}` chỉ capture được cấu trúc `List<X>`; bản thân `X` vẫn là `TypeVariable`, không thể suy ra giá trị gọi như `String` sau erasure.

## 9. WildcardType và GenericArrayType khi đi qua cây generic

Dù tiêu đề tập trung vào ba kiểu chính, việc duyệt metadata cần nhận biết hai nhánh kèm theo.

### WildcardType

Trong `List<? extends Number>`, đối số của `List` là một `WildcardType`:

- `getUpperBounds()` trả các upper bounds; với `? extends Number` là `Number.class`.
- `getLowerBounds()` rỗng nếu không có `super` bound; với `? super Integer` là `Integer.class`.
- `?` không ràng buộc tường minh sẽ có upper bound mặc định `Object.class` và không có lower bound.
- Wildcard **khác** `TypeVariable`: `? extends Number` không khai báo một biến `T` có thể được tái sử dụng trong chữ ký.

Các bounds vẫn trả về `Type[]` nên có thể chứa biến hoặc kiểu parameterized lồng nhau. Ví dụ `List<? extends Comparable<T>>` có upper bound là `ParameterizedType Comparable<T>`.

### GenericArrayType

`T[]`, `List<String>[]` xuất hiện ở vị trí khai báo hợp lệ có thể trả `GenericArrayType`. Phương thức `getGenericComponentType()` trả `Type` của phần tử, có thể lại là `TypeVariable` hoặc `ParameterizedType`. Ngược lại, `String[]` hoặc `int[]` được biểu diễn bằng đối tượng `Class<?>`, không phải `GenericArrayType`.

Chỉ kiểm tra `type instanceof GenericArrayType` không đủ để nhận diện mọi kiểu mảng; nếu `type instanceof Class<?> clazz && clazz.isArray()` thì đọc `clazz.getComponentType()`. Không cast `String[].class` sang `GenericArrayType`.

## 10. Các hiểu lầm và lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `(ParameterizedType) someType` ném `ClassCastException` | `someType` thật sự là `Class`, `TypeVariable` hoặc dạng khác | Dùng `instanceof` trước khi ép kiểu |
| `field.getType()` chỉ là `List.class` | Phương thức trả erased/raw runtime type | Dùng `field.getGenericType()` |
| `getGenericType()` trả `T` dù object là `Container<String>` | Field được khai báo ở `Container<T>`; Reflection chưa thay biến theo subclass | Tìm ánh xạ type variable từ generic superclass/interface |
| `Child.class.getDeclaredField("values")` thất bại | Field khai báo ở lớp cha | Truy cập reflection vào declaring class hoặc duyệt hierarchy |
| `getTypeParameters()` của subclass không có `T` | Subclass không khai báo biến kiểu riêng, chỉ gắn đối số cho lớp cha | Dùng `getGenericSuperclass()` để đọc `Base<String>` |
| Giả định mọi `getGenericSuperclass()` là `ParameterizedType` | Raw/non-generic superclass có thể trả `Class<?>`; có thể trả `null` | Kiểm tra dạng `Type` và kết quả `null` |
| Tên biến trùng nhau bị gộp sai | `T` của hai class/method có thể là hai declarations khác nhau | Dùng `getGenericDeclaration()` khi lập mapping |
| Chỉ đọc `getActualTypeArguments()[0]` là đủ | Có thể chứa nested parameterized type, wildcard, array, variable | Duyệt cây `Type` đệ quy có kiểm soát |
| Nhầm `List<String>` reflection với dữ liệu của instance | Generic khai báo khác type argument thực của instance sau erasure | Phân biệt nguồn metadata và kiểu runtime |
| Duyệt bounds của `E extends Enum<E>` vô hạn | Self-referential bound | Theo dõi các `TypeVariable` đã thăm để cắt chu trình |

Phần signature generic trong class file có thể bị thiếu, hỏng hoặc tham chiếu kiểu không thể tải. Một số lời gọi Reflection liên quan có thể ném `GenericSignatureFormatError`, `TypeNotPresentException` hoặc `MalformedParameterizedTypeException`. Đọc metadata cũng **không cấp thêm quyền truy cập** field/method bị hạn chế; Java module system vẫn áp dụng kiểm soát truy cập khi thao tác phản xạ lên thành viên.

Đặc biệt ở method generic có bridge/synthetic methods do compiler phát sinh để hỗ trợ erasure và overriding. Khi liệt kê method để xây metadata API, nên phân biệt `Method.isBridge()`/`isSynthetic()` với method nguồn, tránh đếm trùng những chữ ký mà compiler thêm vào.

## 11. Quy trình đọc generic metadata có hệ thống

Khi một thư viện muốn phân tích kiểu trả về `Map<String, List<? extends T>>` của method, hãy áp dụng chuỗi bước sau:

1. **Chọn đúng điểm khai báo**: lấy `Method` ở class khai báo; gọi `getGenericReturnType()` để có một `Type`.
2. **Rẽ theo loại Type**: nếu là `ParameterizedType`, đọc raw type và từng đối số; nếu là `TypeVariable`, lấy declaration và bounds; nếu là `WildcardType`, đọc upper/lower; nếu là `GenericArrayType`, đọc component; nếu là `Class`, đọc kiểu cụ thể.
3. **Duyệt lồng nhau**: với `Map`, đối số đầu là `String.class`; đối số thứ hai là `List<? extends T>`; đối số của `List` lại là một wildcard có upper bound `T`.
4. **Xác định ngữ cảnh gắn biến**: nếu method thuộc class generic và có subclass cụ thể, đi qua superclass/interface để lập ánh xạ. Nếu `T` là biến riêng của method được gọi lúc chạy, Reflection thường không biết caller đã chọn kiểu thực nào.
5. **Xử lý missing/erased information**: khi chữ ký chỉ chứa raw type hoặc biến chưa gắn, trả cấu trúc trung thực; không tự giả định `Object` hoặc đoán một đối số cụ thể.
6. **Dùng Type object cho logic**: `getTypeName()` chỉ phục vụ hiển thị/logging; đừng parse chuỗi dạng `Map<...>` để thực hiện type resolution.

Đối với các API đăng ký serializer, DI, validation, mapping và framework generic, mục tiêu là giữ nguyên ý nghĩa của type tree ở **vị trí khai báo** và xử lý các biến kiểu chưa được giải quyết đúng cách.

## 12. Tự kiểm tra

**Câu 1.** `class B<T> { List<T> items; }` và `class S extends B<String> {}`. `B.class.getDeclaredField("items").getGenericType()` trả gì?  
**Đáp án:** `List<T>`. Phải đọc `S.class.getGenericSuperclass()` rồi map `B.T` sang `String.class` mới suy ra `List<String>` trong ngữ cảnh `S`.

**Câu 2.** `List<String> list = new ArrayList<>();`, gọi `list.getClass()` có thấy `String` không?  
**Đáp án:** Không. Runtime class là `ArrayList`; generic argument chỉ tồn tại ở vị trí khai báo có lưu signature phù hợp.

**Câu 3.** Hai field `List<String> a;` và `List<Integer> b;` khác nhau ở `getType()` hay `getGenericType()`?  
**Đáp án:** `getType()` đều là `List.class`. `getGenericType()` phản ánh hai `ParameterizedType` với actual argument khác nhau.

**Câu 4.** `class X<T extends Number & Comparable<T>>`, `getBounds()` của `T` có mấy phần tử, kiểu nào?  
**Đáp án:** Hai: `Class<Number>` và `ParameterizedType` cho `Comparable<T>`.

**Câu 5.** `? extends Number` có phải `TypeVariable` không?  
**Đáp án:** Không, đó là `WildcardType`; dùng `getUpperBounds()` để lấy `Number`.

**Câu 6.** Vì sao `T[]` khác `String[]` trong Reflection?  
**Đáp án:** `T[]` có component type chưa reify nên được biểu diễn bằng `GenericArrayType`; `String[]` là một runtime array class nên là `Class<?>`.

**Câu 7.** Lớp con `class Fixed extends Generic<String>` có `getTypeParameters()` cho `String` không?  
**Đáp án:** Không; `Fixed` không khai báo type variable mới. `String` là actual argument trong `Fixed.class.getGenericSuperclass()`.

**Câu 8.** Khi nào cần `getGenericDeclaration()`?  
**Đáp án:** Khi cần xác định biến `T` thuộc class/method/constructor nào, đặc biệt để tránh nhập nhằng các biến cùng tên và xây ánh xạ generic đúng theo inheritance.

## 13. Ghi nhớ

- **`Type`** là interface chung biểu diễn cây generic metadata, không đồng nhất với `Class<?>`.
- **`ParameterizedType`** mô tả kiểu có generic arguments trong chữ ký khai báo; truy cập `getRawType()`, `getActualTypeArguments()`, `getOwnerType()` để đi sâu.
- **`TypeVariable`** mô tả biến kiểu được khai báo; đọc `getName()`, `getGenericDeclaration()` và `getBounds()` để hiểu nguồn gốc và ràng buộc.
- **Type erasure** làm biến mất phần lớn thông tin actual type argument của object thông thường, nhưng generic signatures trong class/field/method vẫn cho Reflection đọc cấu trúc kiểu **ở nơi khai báo**.
- **Không tự giải biến**: một field `List<T>` không trở thành `List<String>` chỉ vì đọc từ ngữ cảnh lớp con. Muốn diễn giải chính xác cần nối chữ ký superclass/interface với nơi khai báo field và thay biến theo mapping.
- Đọc kết quả qua **`instanceof` và đối tượng `Type`**, không dựa vào parse `getTypeName()` hay cast mù quáng.

Nắm chắc ba API `Type`, `ParameterizedType` và `TypeVariable` giúp bạn hiểu cách Java lưu metadata generic, tại sao một số thông tin vẫn đọc được sau erasure, và cách các thư viện Reflection/serialization/DI diễn giải các kiểu lồng nhau và biến kiểu.
