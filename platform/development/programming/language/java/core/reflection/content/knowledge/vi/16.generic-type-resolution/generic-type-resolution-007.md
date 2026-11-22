# Giới hạn kiểu chưa được ràng buộc và trường hợp raw type trong Java Reflection

## 1. Đặt đúng vấn đề: metadata generic không luôn cung cấp một kiểu cụ thể

Java hỗ trợ các kiểu generic như `Box<String>`, `Box<T>` hoặc `Box<?>`, nhưng Reflection không có khả năng tự khôi phục mọi tham số kiểu của object ở runtime. Khi phân tích một lớp generic, field, method hoặc quan hệ kế thừa, ta cần phân biệt rõ ba kết quả:

1. **Đã ràng buộc cụ thể:** ví dụ `class StringBox extends Box<String>`. Khi hỏi generic superclass của `StringBox.class`, chữ ký khai báo vẫn chứa đối số `String`, nên Reflection có thể trả `ParameterizedType` với đối số `String.class`.
2. **Còn biến kiểu chưa được giải quyết:** ví dụ `class OpenBox<U> extends Box<U>`. Generic superclass có dạng `Box<U>`; đối số `U` là `TypeVariable`, **không phải** kiểu dữ liệu cụ thể của một object `OpenBox` đang giữ.
3. **Kế thừa qua raw type:** ví dụ `class RawBox extends Box`. Khai báo `extends Box` không ghi danh sách tham số kiểu, nên `getGenericSuperclass()` có thể chỉ trả `Class` đại diện `Box`. Không có `getActualTypeArguments()` để lấy một `T` bị bỏ trống.

Trong ứng dụng dùng serializer, mapper, dependency injection hoặc thư viện generic, **không được âm thầm diễn giải trường hợp chưa biết thành một kiểu cụ thể tự đoán**. Upper bound như `Object` hoặc `Number` chỉ đặt giới hạn cho biến kiểu; nó không phải giá trị ràng buộc thực tế.

## 2. Các loại `Type` cần nhận diện

Trong `java.lang.reflect`, `Type` là abstraction chung. Kết quả đọc một chữ ký generic có thể là:

| Loại Reflection | Ví dụ trong khai báo | Ý nghĩa |
| --- | --- | --- |
| `Class<?>` | `String` hoặc superclass dùng raw `Box` | Kiểu lớp cụ thể, không mang danh sách đối số generic ở chính giá trị `Class` |
| `ParameterizedType` | `Box<String>`, `Box<U>`, `List<?>` | Khai báo áp dụng kiểu generic kèm danh sách đối số; **đối số bên trong vẫn có thể chưa giải quyết được** |
| `TypeVariable<?>` | `T`, `U`, `N extends Number` | Biến kiểu do một class, method hoặc constructor khai báo |
| `WildcardType` | `?`, `? extends Number`, `? super Integer` | Đối số wildcard, giới hạn quan hệ kiểu chứ không chỉ một kiểu cụ thể |
| `GenericArrayType` | `T[]` trong khai báo generic | Kiểu mảng có component type không biểu diễn được chỉ bằng `Class<?>[]` |

`Class.getGenericSuperclass()` và `Class.getGenericInterfaces()` trả metadata quan hệ trực tiếp với superclass/superinterface; `Field.getGenericType()` và `Method.getGenericReturnType()` trả chữ ký generic của field/return type. Muốn xem các biến kiểu **được khai báo** trên class hoặc executable, dùng `getTypeParameters()`.

Lưu ý: `getTypeParameters()` cung cấp **danh sách biến khai báo**, không phải các đối số đã được thay thế cho một object runtime. Ví dụ `Box.class.getTypeParameters()[0]` là `T` ngay cả khi một instance nào đó từng được tạo bằng `new Box<String>(...)`.

## 3. `TypeVariable`: khi `T` hoặc `U` chưa được ràng buộc

Ví dụ:

```java
class Box<T> {
    T value;
}

class OpenBox<U> extends Box<U> {}
```

Đây là một **đoạn khai báo minh họa**, không phải file Java hoàn chỉnh.

Khi phân tích `OpenBox.class.getGenericSuperclass()`, ta có thể nhận `ParameterizedType` mô tả `Box<U>`. Nhưng đối số thực của nó là `TypeVariable` đại diện `U`; không có cơ sở để nói `U = String`, `U = Integer` hoặc `U = Object` chỉ từ `OpenBox.class`.

`TypeVariable` cung cấp:

- `getName()`: tên biến, chẳng hạn `U`. **Tên đơn lẻ không đủ để định danh**; hai class khác nhau có thể đều khai báo `T`.
- `getGenericDeclaration()`: class, method hoặc constructor **đã khai báo biến**. Dùng thông tin này (cùng thứ tự biến) khi tạo ánh xạ ràng buộc.
- `getBounds()`: mảng upper bounds theo khai báo; có thể chứa `Class`, `ParameterizedType` hoặc `TypeVariable`.
- `getAnnotatedBounds()`: dùng khi cần cả metadata annotation gắn lên vị trí bound.

### 3.1. Không khai báo bound: `Object` là upper bound mặc định

Với `class Box<T>`, `T.getBounds()` trả mảng có upper bound `java.lang.Object`. Điều đó có nghĩa `T` có thể được thay bởi **nhiều kiểu tham chiếu hợp lệ**; không có nghĩa mọi `Box<T>` thực tế là `Box<Object>`.

Vì vậy, khi một resolver thấy `TypeVariable T` mà không có ánh xạ `T -> kiểu cụ thể`, câu trả lời đúng là **UNRESOLVED `T` (upper bound: `Object`)**. Chọn `Object.class` làm *erasure* đôi khi hữu ích cho thao tác trên bytecode, nhưng **không được gọi đó là đối số kiểu thực tế**.

### 3.2. Bound tường minh vẫn không phải một đối số đã được ràng buộc

```java
class NumericBox<N extends Number & Comparable<N>> {}
```

Ở đây `N.getBounds()` có hai phần, lần lượt là `Number` và `Comparable<N>`. Biết các upper bounds giúp kiểm tra giới hạn và erasure, nhưng vẫn chưa thể chọn giữa `Integer`, `Double` hoặc một kiểu phù hợp khác.

Theo quy tắc type erasure của Java, erasure của một type variable lấy theo **leftmost bound**: `T` không bound tường minh có erasure `Object`, còn `N extends Number & Comparable<N>` có erasure `Number`. Erasure là kiểu được compiler sử dụng cho biểu diễn JVM sau khi xóa thông tin generic, **khác với** việc phân giải một đối số kiểu concrete.

### 3.3. Những điều không thể suy ra từ một instance thông thường

`new Box<String>("x").getClass()` và `new Box<Integer>(123).getClass()` là cùng `Class` `Box` runtime (trong cùng class loader). Do đó, đối tượng `Class` tự nó không lưu `String` hay `Integer` của từng instance generic. Quan sát giá trị hiện tại cũng không giải quyết chắc chắn kiểu generic: object có thể chứa `null`, interface/supertype hoặc được truy cập theo nhiều đường generic.

Nếu chương trình cần kiểu tại runtime, có thể truyền `Class<T>`/`Type` token có chủ đích, dùng subclass đóng kiểu trong chữ ký kế thừa hoặc metadata khai báo tương ứng. Không tự đoán từ tên biến hay dữ liệu bất kỳ.

## 4. Raw type: không có danh sách type arguments

Raw type là việc sử dụng một generic type **không kèm type arguments**:

```java
class Box<T> {}
class RawBox extends Box {}          // extends kiểu raw Box
class StringBox extends Box<String> {}
```

Đây là **mảnh khai báo minh họa**. `Box` vốn là một generic class, nhưng ở biểu thức `extends Box` không hề cung cấp `<...>`; đó là sử dụng raw type để tương thích với mã Java cũ.

Phân biệt ba câu sau:

- `Box<String>`: type argument rõ ràng là `String`.
- `Box<?>`: **parameterized type có wildcard**, vẫn có danh sách type arguments.
- `Box`: **raw type**, không có danh sách type arguments.

Đừng coi `Box` raw tương đương `Box<Object>` hay `Box<?>`. Cả ba biểu thức có quan hệ với cùng generic declaration nhưng khác nhau về kiểm tra kiểu ở compile time, metadata generic và khả năng phát sinh unchecked operations.

Theo JLS, supertypes của raw type là **erasure** của các supertype tương ứng. Các lời gọi member qua raw type có thể đưa tới cảnh báo `unchecked` khi kiểu field/parameter đã mất thông tin generic. Việc chương trình có thể biên dịch không đồng nghĩa đảm bảo loại trừ `ClassCastException`.

### 4.1. Reflection của raw superclass

```java
Type parent = RawBox.class.getGenericSuperclass();

if (parent instanceof Class<?> rawClass) {
    System.out.println(rawClass.getSimpleName());
}
```

Trong ví dụ trên, `parent` là `Class` tương ứng `Box`, không phải một `ParameterizedType` với đối số giả `Object`.

Lỗi phổ biến:

```java
ParameterizedType p =
        (ParameterizedType) RawBox.class.getGenericSuperclass();
```

Câu lệnh này có thể ném `ClassCastException` vì kiểu thực của `Type` là `Class`. Luôn kiểm tra bằng `instanceof` trước khi ép kiểu. Nếu kết quả là `Class` của generic declaration được dùng raw, trạng thái phân giải nên báo **RAW / UNKNOWN TYPE ARGUMENT**, không báo đã giải được một đối số cụ thể.

## 5. Ví dụ Java 17+ hoàn chỉnh và kết quả đã kiểm chứng

Tạo file **`GenericLimitsDemo.java`**:

```java
import java.lang.reflect.*;
import java.util.Arrays;
import java.util.stream.Collectors;

public class GenericLimitsDemo {
    static class Box<T> {
        private final T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
    }

    static class StringBox extends Box<String> {
        StringBox() { super("hello"); }
    }

    static class OpenBox<U> extends Box<U> {
        OpenBox(U value) { super(value); }
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static class RawBox extends Box {
        RawBox() { super(42); }
    }

    static class BoundedBox<N extends Number & Comparable<N>>
            extends Box<N> {
        BoundedBox(N value) { super(value); }
    }

    static class IntegerBox extends BoundedBox<Integer> {
        IntegerBox() { super(7); }
    }

    static class Lists {
        java.util.List<?> any;
        java.util.List<String> strings;
    }

    static String kind(Type t) {
        if (t instanceof Class<?>) return "Class";
        if (t instanceof TypeVariable<?>) return "TypeVariable";
        if (t instanceof ParameterizedType) return "ParameterizedType";
        if (t instanceof WildcardType) return "WildcardType";
        if (t instanceof GenericArrayType) return "GenericArrayType";
        return "Other";
    }

    static void inspect(Class<?> type) {
        Type parent = type.getGenericSuperclass();
        System.out.println(type.getSimpleName() + " -> " + parent.getTypeName());

        if (parent instanceof ParameterizedType p) {
            Type arg = p.getActualTypeArguments()[0];
            System.out.println(
                    "  argument=" + arg.getTypeName() + ", kind=" + kind(arg)
            );
        } else if (parent instanceof Class<?>) {
            System.out.println("  raw superclass: no actual type argument");
        }
    }

    public static void main(String[] args) throws Exception {
        inspect(StringBox.class);
        inspect(OpenBox.class);
        inspect(RawBox.class);
        inspect(IntegerBox.class);

        TypeVariable<?> t = Box.class.getTypeParameters()[0];
        TypeVariable<?> u = OpenBox.class.getTypeParameters()[0];
        TypeVariable<?> n = BoundedBox.class.getTypeParameters()[0];

        System.out.println("T bounds=" + Arrays.stream(t.getBounds())
                .map(Type::getTypeName).collect(Collectors.joining(" & ")));
        System.out.println("U bounds=" + Arrays.stream(u.getBounds())
                .map(Type::getTypeName).collect(Collectors.joining(" & ")));
        System.out.println("N bounds=" + Arrays.stream(n.getBounds())
                .map(Type::getTypeName).collect(Collectors.joining(" & ")));

        Field value = Box.class.getDeclaredField("value");
        System.out.println("Box.value generic=" + value.getGenericType().getTypeName()
                + ", erased=" + value.getType().getTypeName());

        Field any = Lists.class.getDeclaredField("any");
        Type wildcard = ((ParameterizedType) any.getGenericType())
                .getActualTypeArguments()[0];
        System.out.println("List<?> argument=" + wildcard.getTypeName()
                + ", kind=" + kind(wildcard));

        System.out.println("Same runtime class="
                + (new Box<>("x").getClass() == new Box<>(123).getClass()));

        @SuppressWarnings({"rawtypes", "unchecked"})
        Box<Integer> unsafe = new Box("not an integer");
        try {
            Integer result = unsafe.get();
            System.out.println(result);
        } catch (ClassCastException e) {
            System.out.println("Raw assignment: ClassCastException on read");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 GenericLimitsDemo.java
java GenericLimitsDemo
```

**Stdout trên JDK 21 với `--release 17`:**

```text
StringBox -> GenericLimitsDemo$Box<java.lang.String>
  argument=java.lang.String, kind=Class
OpenBox -> GenericLimitsDemo$Box<U>
  argument=U, kind=TypeVariable
RawBox -> GenericLimitsDemo$Box
  raw superclass: no actual type argument
IntegerBox -> GenericLimitsDemo$BoundedBox<java.lang.Integer>
  argument=java.lang.Integer, kind=Class
T bounds=java.lang.Object
U bounds=java.lang.Object
N bounds=java.lang.Number & java.lang.Comparable<N>
Box.value generic=T, erased=java.lang.Object
List<?> argument=?, kind=WildcardType
Same runtime class=true
Raw assignment: ClassCastException on read
```

**Phân tích theo từng phần:**

1. `StringBox` có generic superclass `Box<String>`. `getActualTypeArguments()[0]` là một `Class` `String.class`; có thể kết luận đối số của **quan hệ kế thừa được khai báo** là `String`.
2. `OpenBox<U>` cũng trả `ParameterizedType`, nhưng đối số là `TypeVariable U`. Sự tồn tại của `ParameterizedType` **không đảm bảo** mọi đối số đã ràng buộc concrete.
3. `RawBox` trả `Class` vì lớp cha được khai báo dưới dạng raw. Nó không có danh sách type argument để đọc.
4. `IntegerBox` ràng buộc `BoundedBox<Integer>`. Nếu còn đi tiếp qua `BoundedBox<N> extends Box<N>`, muốn kết luận `Box<Integer>` phải **truyền ánh xạ `N -> Integer`** qua từng cấp. Chỉ đọc `BoundedBox.class.getGenericSuperclass()` sẽ thấy `N`, chưa phải `Integer`.
5. `Box.value` có `getGenericType() == T` (về ý nghĩa metadata), còn `getType() == Object.class` vì `T` bị erasure về `Object`. `getType()` không cung cấp actual argument của một instance cụ thể.
6. `List<?>` cho `WildcardType`, không phải raw. `?` là đối số chưa biết có upper bound mặc định `Object`; không thể tùy tiện đổi nó thành actual `Object`.
7. Hai `Box` có đối số compile-time khác nhau dùng cùng runtime class. Cuối cùng, phép gán qua raw type bỏ qua kiểm tra generic khiến `Integer result = unsafe.get()` phát sinh `ClassCastException` khi bytecode ép giá trị `String` về `Integer`.

`@SuppressWarnings({"rawtypes", "unchecked"})` trong ví dụ chỉ được đặt sát nơi **cố ý minh họa rủi ro của raw type**. Nó không biến mã mất an toàn thành an toàn; trong code thực tế nên tránh hoặc cô lập tương tác legacy càng nhỏ càng tốt.

## 6. Vì sao `getBounds()` không thay thế được phân giải kiểu?

Một `TypeVariable` có thể vẫn chưa ràng buộc dù có một hoặc nhiều upper bounds:

| Khai báo | `getBounds()` | Có biết actual argument chưa? |
| --- | --- | --- |
| `class Box<T>` | `Object` | **Chưa** |
| `class Numeric<N extends Number>` | `Number` | **Chưa** |
| `class ComparableBox<N extends Number & Comparable<N>>` | `Number`, `Comparable<N>` | **Chưa** |
| `class StringBox extends Box<String>` | `T` vẫn tồn tại trên declaration `Box` | **Có đối số `String` trong quan hệ kế thừa của `StringBox`** |
| `class OpenBox<U> extends Box<U>` | `U` mặc định bound `Object` | **Chưa**, trừ khi có ánh xạ từ tầng bao ngoài |

**Upper bound** được dùng cho ràng buộc kiểu và erasure. **Actual type argument** là giá trị được đưa vào khi một kiểu parameterized được khai báo/sử dụng. Không có quy tắc “nếu không giải được `T` thì đi lấy bound đầu tiên làm `T`”.

Ví dụ `N extends Number` cho biết `N` là một subtype phù hợp của `Number`. Nó **không** cho phép resolver khẳng định `N = Number`; `Integer`, `Double` và nhiều kiểu khác có thể thỏa mãn bound.

## 7. Phân giải qua nhiều tầng cần thế biến, không chỉ lặp `getGenericSuperclass()`

Xét đoạn khai báo:

```java
class Base<T> {}

class Mid<U> extends Base<java.util.List<U>> {}

class Concrete extends Mid<String> {}
```

Đây là **đoạn code minh họa**, không phải một file Java độc lập.

- `Concrete.class.getGenericSuperclass()` biểu diễn `Mid<String>`, nên có ánh xạ `Mid.U -> String`.
- `Mid.class.getGenericSuperclass()` biểu diễn `Base<List<U>>`. Đối số là một `ParameterizedType` `List<U>`, trong đó `U` vẫn là `TypeVariable`.
- Muốn xác định quan hệ từ `Concrete` tới `Base`, resolver phải thế `U -> String` **bên trong** `List<U>`, để được `Base<List<String>>`.

Một thuật toán generic resolver thực tế cần:

1. Đọc các khai báo `TypeVariable` theo **`getTypeParameters()` của đúng declaring class**.
2. Đọc các actual arguments của `ParameterizedType` trên cạnh kế thừa hiện tại.
3. Ghi ánh xạ từ biến khai báo sang `Type` tương ứng, phân biệt biến cùng tên ở các declaration khác nhau.
4. Áp dụng ánh xạ đệ quy vào `ParameterizedType`, `GenericArrayType`, `WildcardType` và `TypeVariable`, tránh vòng lặp khi bound tự tham chiếu như `T extends Comparable<T>`.
5. Truyền ánh xạ đó khi tiếp tục duyệt superclass hoặc interface, đồng thời xử lý nhiều nhánh interface nếu liên quan.
6. Khi gặp raw edge hoặc biến vẫn chưa có ánh xạ, **báo chưa giải được** và giữ thông tin bounds/erasure riêng; không điền `Object` hoặc `Class` bất kỳ cho đủ chỗ.

Trong ví dụ `Concrete -> Mid<String> -> Base<List<U>>`, một resolver chỉ nhìn từng cạnh độc lập sẽ bỏ lỡ phép thế `U -> String`. Ngược lại, một resolver “đoán `U` bằng bound `Object`” sẽ kết luận sai `List<Object>` dù thông tin `String` tồn tại trên cạnh dưới.

## 8. Raw type nằm giữa chuỗi kế thừa

Ví dụ:

```java
class Store<T> {}
@SuppressWarnings("rawtypes")
class LegacyStore extends Store {}
class SpecializedStore extends LegacyStore {}
```

Đây là **mảnh khai báo minh họa**.

- `LegacyStore.class.getGenericSuperclass()` đại diện raw `Store` và không cung cấp `T`.
- `SpecializedStore.class.getGenericSuperclass()` cho `LegacyStore.class` (một superclass thông thường).
- Khi đi ngược lên `Store<T>`, không thể tạo ra một concrete argument cho `Store.T` từ chuỗi này. Kết quả hợp lệ là **không biết `T` vì đã qua raw edge**.

Cần phân biệt hai mức phân tích:

- **Erasure:** có thể xác định lớp runtime cơ sở, chẳng hạn `Store.class`.
- **Generic argument resolution:** không thể khôi phục một `T` đã không được ghi trong chữ ký raw.

Nếu framework không thể xử lý đầu vào raw, hãy yêu cầu khai báo generic rõ ràng, `Type` token hoặc metadata cấu hình hợp lệ; tránh tự coi raw `Store` là `Store<Object>`.

## 9. Wildcard chưa ràng buộc không phải raw type

Xem hai field:

```java
java.util.List<?> unknownElements;
java.util.List rawElements;
```

Đây là **mảnh khai báo field**; đặt chúng trong một class thì mới biên dịch như một chương trình.

Với `unknownElements`:

- `getGenericType()` là `ParameterizedType` mô tả `List<?>`.
- `getActualTypeArguments()[0]` là `WildcardType`.
- `getUpperBounds()` của wildcard không bound tường minh có `Object`; `getLowerBounds()` rỗng.
- `List<?>` giữ được một phần kiểm tra kiểu tại compile time: bạn không thể tùy tiện `add("text")` vào danh sách đó (ngoại lệ `null`).

Với `rawElements`:

- `getGenericType()` thường là `Class` `List.class`, không có actual arguments.
- Raw type cho phép những thao tác có nguy cơ mất an toàn về kiểu, có thể dẫn tới unchecked warning và lỗi muộn.

Tương tự, `? extends Number` là một wildcard **có upper bound** chứ không phải một biến `N extends Number`; `? super Integer` chứa **lower bound**. Cả wildcard và type variable đều không nên bị ép thành `Class<?> concrete` chỉ vì có bound.

## 10. Cách thiết kế API trả kết quả phân giải đáng tin

Khi xây dựng thư viện Reflection, nên trả về **trạng thái phân giải có giải thích**, thay vì một `Class<?>` bịa ra:

| Trạng thái đề xuất | Ví dụ | Hành vi hợp lý |
| --- | --- | --- |
| `RESOLVED` | `Box<String>` trên `StringBox` | Trả `Type` `String.class` |
| `UNRESOLVED_VARIABLE` | `Box<U>` trên `OpenBox<U>` khi không có ánh xạ `U` | Trả `TypeVariable U`, declaration, bounds |
| `RAW` | `extends Box` | Báo thiếu argument ngay trong cạnh kế thừa raw |
| `WILDCARD` | `List<?>`, `List<? extends Number>` | Giữ `WildcardType` và các bounds |
| `PARTIALLY_RESOLVED` | `List<U>` khi `U` chưa biết | Giữ cấu trúc `ParameterizedType` và vị trí biến chưa biết |

Các nhãn trạng thái trên là **gợi ý thiết kế ứng dụng**, không phải enum có sẵn trong JDK.

Nếu cần một kiểu runtime cho serialization/validation, nhận `Type` hoặc một *type token* từ nơi gọi. Ví dụ chữ ký API có thể là `decode(String json, Type targetType)` thay vì chỉ `decode(String json, Class<?> targetClass)`, vì `Class<List>` không biểu diễn được `List<String>`. Dù có `Type` token, vẫn cần kiểm tra các `TypeVariable` chưa ràng buộc và các trường hợp raw/wildcard theo hợp đồng API.

## 11. Sai lầm thường gặp

| Sai lầm | Vì sao sai và cách sửa |
| --- | --- |
| Ép `getGenericSuperclass()` về `ParameterizedType` vô điều kiện | Raw superclass có thể trả `Class`; kiểm tra `instanceof` |
| Thấy `ParameterizedType` là kết luận đã có concrete type | Đối số bên trong có thể là `TypeVariable`, `WildcardType`, `ParameterizedType` lồng nhau |
| Dùng bound `Object` làm actual argument khi không giải được `T` | Bound/erasure không phải binding; giữ trạng thái unresolved |
| Gộp mọi `T` cùng tên thành một biến | Mỗi biến còn có `GenericDeclaration` riêng; dùng declaration và vị trí |
| Dựa vào `obj.getClass()` để lấy `Box<String>` của `new Box<String>()` | Type erasure khiến class runtime chung cho các instantiation |
| Coi raw `Box` như `Box<Object>` | Raw type mất type argument và có hành vi compile-time khác |
| Coi `List<?>` là raw `List` | `List<?>` giữ wildcard metadata và kiểm tra kiểu khác raw |
| Chỉ đi lên superclass một cấp khi có nhiều tầng generic | Phải truyền ánh xạ biến giữa các cạnh kế thừa |
| Không thế biến đệ quy bên trong `List<U>` | Bỏ sót concrete `List<String>` qua nhiều tầng |
| Bỏ qua cảnh báo `unchecked` ở raw assignment | Có thể phát sinh `ClassCastException` ở lúc đọc/sử dụng |
| Cố kiểm tra `obj instanceof T` với type variable chưa ràng buộc | Không hợp lệ theo hạn chế reifiable type; cần thiết kế kiểm tra kiểu khác |

## 12. Tự kiểm tra

1. Tại sao `OpenBox<String>` tạo bằng `new OpenBox<>("x")` không khiến `OpenBox.class.getGenericSuperclass()` trở thành `Box<String>`?
2. `TypeVariable T` không khai báo bound có `getBounds()` thế nào? Giá trị đó có phải actual argument không?
3. `class RawChild extends Box {}` làm `RawChild.class.getGenericSuperclass()` trả loại `Type` nào? Có thể gọi `getActualTypeArguments()` trực tiếp không?
4. Nếu `N extends Number & Comparable<N>`, erasure của `N` là gì? Từ đó có biết `N = Number` không?
5. `List<?>` và raw `List` khác nhau thế nào ở metadata?
6. Với `Concrete extends Mid<String>` và `Mid<U> extends Base<List<U>>`, cần thao tác nào để tìm `Base<List<String>>`?
7. Vì sao việc gán qua raw `Box` có thể dẫn tới `ClassCastException` dù chương trình đã biên dịch?

**Đáp án:** (1) object dùng runtime class `OpenBox`, chữ ký của declaration vẫn là `Box<U>`; (2) bound `Object`, không phải actual argument; (3) `Class` của `Box`, không có `getActualTypeArguments()`; (4) `Number`, vẫn không suy ra binding concrete; (5) wildcard vs thiếu argument raw; (6) truyền ánh xạ `U -> String` qua quan hệ và thế đệ quy trong `List<U>`; (7) raw bypass kiểm tra generic, lỗi xuất hiện khi có cast tại nơi sử dụng.

## 13. Kết luận và tài liệu tham khảo

Trong phân giải generic bằng Reflection, **không có thông tin** và **kiểu `Object`** là hai trạng thái khác nhau. Đối với `TypeVariable` chưa ràng buộc, giữ biến cùng declaration và bounds; đối với raw type, ghi nhận đã mất type arguments; đối với wildcard, giữ cấu trúc wildcard và giới hạn; đối với chuỗi kế thừa, thế biến theo từng tầng nếu có ánh xạ hợp lệ.

Tài liệu chuẩn:

- [Java SE 21 — `TypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html): `getBounds()`, `getGenericDeclaration()`.
- [Java SE 21 — `ParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html): `getActualTypeArguments()` và `getRawType()`.
- [Java SE 21 — `Class.getGenericSuperclass()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getGenericSuperclass()): quan hệ superclass trong metadata generic.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): quy tắc erasure.
- [Java Language Specification §4.8 — Raw Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8): ý nghĩa và rủi ro raw types.