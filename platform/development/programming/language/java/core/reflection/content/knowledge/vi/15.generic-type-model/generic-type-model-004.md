# TypeVariable và GenericDeclaration trong Java Reflection

Java generic cho phép khai báo `class Box<T>`, `interface Pair<K,V>`, phương thức `<U> U convert(U value)` hoặc constructor có tham số kiểu riêng. Khi phân tích những khai báo này bằng Reflection, hai giao diện `java.lang.reflect.TypeVariable` và `java.lang.reflect.GenericDeclaration` giải quyết hai câu hỏi khác nhau:

- **`TypeVariable<D extends GenericDeclaration>`** biểu diễn một **biến kiểu được khai báo**, như `T` hoặc `U`, kèm tên, upper bounds, annotations và chủ thể khai báo.
- **`GenericDeclaration`** biểu diễn **nơi được phép khai báo tham số kiểu**: `Class<?>`, `Method` và `Constructor<?>` đều triển khai giao diện này. Phương thức chung `getTypeParameters()` trả các biến kiểu khai báo trực tiếp tại đó.

Đây là metadata của **khai báo generic**, không phải nơi Java lưu riêng mọi kiểu đối số trên từng object runtime. Phân biệt khai báo, vị trí sử dụng và đối số kiểu cụ thể là trọng tâm để tránh sai lầm do *type erasure*.

## 1. Biến kiểu khác đối số kiểu cụ thể

Xét:

```java
class Box<T extends Number> {
    T value;
}

class IntegerBox extends Box<Integer> {}
```

`T` thuộc `Box<T extends Number>` là **biến kiểu**. Nó được Reflection biểu diễn bằng `TypeVariable`, trong đó upper bound là `Number`. Ngược lại, `Integer` trong `extends Box<Integer>` là **đối số kiểu** của một kiểu parameterized, được đọc từ `ParameterizedType` trên superclass của `IntegerBox`.

`Box.class.getTypeParameters()` trả khai báo `T`. `IntegerBox.class.getTypeParameters()` là mảng rỗng vì lớp con không **tự** khai báo một tham số kiểu nào. `IntegerBox.class.getGenericSuperclass()` lại cho thông tin tương đương `Box<Integer>`.

`new Box<Integer>().getClass()` là `Box.class`, cũng như `new Box<Long>().getClass()`. Generic argument `Integer` hoặc `Long` thường không được reify trong runtime class của một object `Box` thông thường. `TypeVariable.getBounds()` không tự cung cấp kiểu `Integer` cho một object cụ thể.

## 2. `TypeVariable` nằm trong hệ thống `Type`

`java.lang.reflect.Type` là giao diện chung biểu diễn kiểu mà các API Reflection trả về khi đọc metadata generic.

| Dạng `Type` | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `Class<?>` | `String`, `int`, `String[]` | Kiểu class/interface/primitive/array thông thường |
| `ParameterizedType` | `List<String>`, `Map<K,V>` | Kiểu parameterized có các type arguments |
| `TypeVariable<?>` | `T` của `class Box<T>` | Biến kiểu có declaration riêng |
| `WildcardType` | `? extends Number`, `? super T` | Wildcard trong một lần sử dụng generic |
| `GenericArrayType` | `T[]` | Array với generic component type không phải class array thông thường |

`TypeVariable<D>` triển khai `Type` và `AnnotatedElement`. Giao diện `GenericDeclaration` không phải là một loại `Type`: nó mô tả nơi khai báo biến kiểu. Tuy nhiên `Class<?>` vừa là một `Type` vừa triển khai `GenericDeclaration`; `Method` và `Constructor<?>` triển khai `GenericDeclaration` nhưng không phải các `Type`.

Không có `T.class` cho biến kiểu `T` trong source. Nếu muốn hỏi về một biến kiểu trong khai báo, dùng `TypeVariable`; nếu muốn biết kiểu `List<T>` tại vị trí field, dùng `ParameterizedType` và tiếp tục kiểm tra các phần tử `Type` bên trong.

## 3. `GenericDeclaration.getTypeParameters()`

API cốt lõi:

```java
TypeVariable<?>[] variables = declaration.getTypeParameters();
```

Trong minh họa trên, `declaration` là một biến kiểu `GenericDeclaration` đã được cung cấp. Kết quả là một mảng theo **thứ tự khai báo**; nếu thực thể không trực tiếp khai báo tham số kiểu thì mảng rỗng.

**Class/interface generic:**

```java
class Pair<K, V> {}
```

`Pair.class.getTypeParameters()` trả hai biến `K`, `V`, cùng owner là class `Pair`.

**Method generic:**

```java
class Util {
    public <U extends CharSequence> U echo(U input) {
        return input;
    }
}
```

`Util.class.getMethod("echo", CharSequence.class).getTypeParameters()` trả `U`, owner là `Method` của `echo`. Khi tìm method, tham số runtime sau erasure là `CharSequence.class`: không có `U.class`.

**Constructor generic:**

```java
class Handler {
    public <C extends Runnable> Handler(C action) {}
}
```

`Handler.class.getConstructor(Runnable.class).getTypeParameters()` trả `C` thuộc constructor, dù `Handler.class.getTypeParameters()` rỗng.

`Field` không triển khai `GenericDeclaration`: field **sử dụng** một `T` đã khai báo bởi class/method thích hợp, nhưng không khai báo type parameters theo cách `Class`, `Method` hoặc `Constructor` làm. Đọc generic type của field bằng `Field.getGenericType()`.

## 4. Những phương thức quan trọng của `TypeVariable`

| API | Kết quả | Cách hiểu |
| --- | --- | --- |
| `getName()` | `String` | Tên như `T`, `E`, `K` |
| `getTypeName()` | `String` | Tên mô tả kiểu; với biến kiểu thường là tên biến |
| `getGenericDeclaration()` | `D extends GenericDeclaration` | Class, method hay constructor **sở hữu khai báo** |
| `getBounds()` | `Type[]` | Upper bounds theo thứ tự khai báo |
| `getAnnotatedBounds()` | `AnnotatedType[]` | Upper bounds cùng type-use annotations |
| `getAnnotations()` / `getDeclaredAnnotations()` | `Annotation[]` | Annotations gắn trên **chính tham số kiểu** |

Ví dụ `<T>` có upper bound ngầm định là `Object`, vì vậy `getBounds()` trả một phần tử tương đương `Object.class`, không phải mảng rỗng.

Với `<T extends Number & Comparable<T>>`, `getBounds()` chứa hai phần tử: `Number` (thường là `Class<?>`) và `Comparable<T>` (là `ParameterizedType`). Vì vậy **không ép toàn bộ `getBounds()` sang `Class<?>`**.

Bound đầu tiên quyết định erasure của biến kiểu: `T extends Number & Comparable<T>` được erase thành `Number`; `U extends CharSequence` được erase thành `CharSequence`; `T` không bound được erase thành `Object`. Mọi bound đều góp phần giới hạn type arguments hợp lệ, chứ không chỉ bound đầu.

## 5. Ví dụ Java 17+ chạy độc lập

Lưu đoạn sau vào `TypeVariableDemo.java`. Chương trình có generic class với intersection bounds, method có type variable cùng tên với class, generic constructor và subclass cố định một type argument.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;
import java.util.List;

public class TypeVariableDemo<T extends Number & Comparable<T>> {
    public List<T> items;

    public TypeVariableDemo() {}

    public <C extends Runnable> TypeVariableDemo(C action) {}

    // T của method là biến mới, không phải T của class.
    public <T extends CharSequence> T echo(T value) {
        return value;
    }

    public static class Fixed extends TypeVariableDemo<Integer> {}

    public static void main(String[] args) throws Exception {
        TypeVariable<?> classVar =
                TypeVariableDemo.class.getTypeParameters()[0];

        System.out.println("Class variable: " + classVar.getName());
        System.out.println("Class owner: "
                + ((Class<?>) classVar.getGenericDeclaration())
                        .getSimpleName());
        System.out.println("Class bounds: "
                + Arrays.toString(classVar.getBounds()));
        System.out.println("Annotated bounds count: "
                + classVar.getAnnotatedBounds().length);

        Method method = TypeVariableDemo.class.getMethod(
                "echo", CharSequence.class);
        TypeVariable<?> methodVar = method.getTypeParameters()[0];

        System.out.println("Method variable: " + methodVar.getName());
        System.out.println("Method bounds: "
                + Arrays.toString(methodVar.getBounds()));
        System.out.println("Same T variable: "
                + classVar.equals(methodVar));
        System.out.println("Method owner equals: "
                + methodVar.getGenericDeclaration().equals(method));

        Constructor<?> constructor =
                TypeVariableDemo.class.getConstructor(Runnable.class);
        TypeVariable<?> ctorVar = constructor.getTypeParameters()[0];

        System.out.println("Constructor variable: " + ctorVar.getName());
        System.out.println("Constructor bounds: "
                + Arrays.toString(ctorVar.getBounds()));
        System.out.println("Constructor owner equals: "
                + ctorVar.getGenericDeclaration().equals(constructor));

        Field field = TypeVariableDemo.class.getField("items");
        ParameterizedType fieldType =
                (ParameterizedType) field.getGenericType();

        System.out.println("Field generic type: "
                + fieldType.getTypeName());
        System.out.println("Field argument equals class T: "
                + fieldType.getActualTypeArguments()[0]
                        .equals(classVar));
        System.out.println("Field raw type: "
                + field.getType().getTypeName());

        System.out.println("Fixed type parameters: "
                + Fixed.class.getTypeParameters().length);
        ParameterizedType superclass =
                (ParameterizedType) Fixed.class.getGenericSuperclass();
        System.out.println("Fixed raw superclass: "
                + ((Class<?>) superclass.getRawType()).getSimpleName());
        System.out.println("Fixed type argument: "
                + superclass.getActualTypeArguments()[0].getTypeName());
    }
}
```

Biên dịch và chạy:

```bash
javac TypeVariableDemo.java
java TypeVariableDemo
```

Đầu ra:

```text
Class variable: T
Class owner: TypeVariableDemo
Class bounds: [class java.lang.Number, java.lang.Comparable<T>]
Annotated bounds count: 2
Method variable: T
Method bounds: [interface java.lang.CharSequence]
Same T variable: false
Method owner equals: true
Constructor variable: C
Constructor bounds: [interface java.lang.Runnable]
Constructor owner equals: true
Field generic type: java.util.List<T>
Field argument equals class T: true
Field raw type: java.util.List
Fixed type parameters: 0
Fixed raw superclass: TypeVariableDemo
Fixed type argument: java.lang.Integer
```

Điểm cần quan sát:

1. Biến class `T` do `TypeVariableDemo.class` khai báo; bounds là `Number` và `Comparable<T>`.
2. Method cũng dùng tên `T` nhưng sở hữu một declaration riêng. Bởi vậy `classVar.equals(methodVar) == false`. Lời gọi `getMethod("echo", CharSequence.class)` sử dụng chữ ký đã erasure.
3. Generic constructor khai báo `C extends Runnable`; `getGenericDeclaration()` trỏ đến đối tượng `Constructor` tương ứng.
4. Field `List<T>` khi đọc `Field.getGenericType()` tạo `ParameterizedType`, có actual type argument là cùng biến class `T`. Nhưng `Field.getType()` chỉ là `List.class`.
5. `Fixed.class.getTypeParameters()` rỗng vì `Fixed` không tự khai báo biến kiểu. Thay vào đó, `Fixed.class.getGenericSuperclass()` giữ metadata `TypeVariableDemo<Integer>`; từ `getActualTypeArguments()` đọc được `Integer`.

Những giá trị trên là metadata từ khai báo Java, không phải kết quả suy ra kiểu chung từ mọi instance runtime.

## 6. Trùng tên không có nghĩa cùng biến kiểu

Ví dụ:

```java
class Outer<T> {
    public <T> T convert(T value) {
        return value;
    }
}
```

Hai biến đều có `getName()` là `"T"` nhưng khai báo ở hai nơi:

- `Outer.class.getTypeParameters()[0]` là biến class `T`.
- `Outer.class.getDeclaredMethod("convert", Object.class).getTypeParameters()[0]` là biến method `T`.

Method type parameter che khuất tên type parameter ở class trong phạm vi của nó. Theo ngữ nghĩa `equals()`, hai `TypeVariable` khác nhau vì chúng biểu diễn hai khai báo khác nhau.

Không dùng khóa map đơn giản như `"T" -> someType` khi làm generic resolver: T từ class khác, method khác hoặc constructor khác có thể trùng tên. Dùng cặp **declaration + name**, hoặc dùng chính `TypeVariable` với `equals()` và `hashCode()`.

API không bắt buộc Reflection trả về một **instance object duy nhất** cho mọi lần đọc cùng biến kiểu; đừng dựa trên `==` để nhận diện. `equals()` biểu thị biến kiểu theo declaration, có ý nghĩa hơn.

## 7. Đọc bounds của biến kiểu

`TypeVariable.getBounds()` trả mọi **upper bounds** theo thứ tự: `<T>` cho `Object`; `<T extends Number>` cho `Number`; `<T extends Number & Comparable<T>>` cho `Number` và `Comparable<T>`. Bound đầu tiên quyết định erasure; các bound còn lại vẫn ràng buộc kiểu hợp lệ. Mỗi phần tử là `Type`, do đó `Comparable<T>` là `ParameterizedType` và không được ép tất cả sang `Class`. Vòng tham chiếu `T extends Comparable<T>` cần theo dõi khi duyệt đệ quy.

Điểm cần phân biệt trong bài này là **bounds thuộc declaration**, không phải actual type arguments. Các quy tắc class/interface bounds, wildcard upper/lower, annotation trên bound và nhiều trường hợp biên được thực hành chuyên sâu ở mục học `getBounds()` tiếp theo.

## 8. Annotations trên type parameter và trên bound

`TypeVariable` triển khai `AnnotatedElement` để đọc annotation của **chính biến kiểu**; `getAnnotatedBounds()` giúp đọc annotations ở **vị trí sử dụng kiểu trong bound**.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface ParameterHint {}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface BoundHint {}

class AnnotatedExample<
        @ParameterHint T extends @BoundHint Number> {}
```

Trong ví dụ:

- `AnnotatedExample.class.getTypeParameters()[0].getAnnotations()` tìm annotation `@ParameterHint`.
- `getAnnotatedBounds()[0]` mô tả bound `Number` cùng annotation type-use `@BoundHint`.
- `getBounds()[0]` mô tả bản thân kiểu `Number`, không đầy đủ thông tin type-use annotation tại bound.

Phải có `RetentionPolicy.RUNTIME` khi muốn các annotation này xuất hiện qua Reflection tại runtime. Không nên trộn annotation trên type parameter với annotation trên kiểu trong bound.

## 9. Một `TypeVariable` có thể được gặp ở nơi sử dụng

Ngoài `getTypeParameters()`, nhiều API trả `Type` và có thể chứa một `TypeVariable`:

```java
class Holder<T> {
    T value;

    T get() { return value; }

    void set(T input) { value = input; }
}
```

Trong ngữ cảnh class `Holder`, ta có thể xem:

```java
TypeVariable<?> declared = Holder.class.getTypeParameters()[0];

Field field = Holder.class.getDeclaredField("value");
java.lang.reflect.Type fieldType = field.getGenericType();

Method getter = Holder.class.getDeclaredMethod("get");
java.lang.reflect.Type returnType = getter.getGenericReturnType();

Method setter = Holder.class.getDeclaredMethod("set", Object.class);
java.lang.reflect.Type parameterType =
        setter.getGenericParameterTypes()[0];
```

Đây là đoạn minh họa với imports `TypeVariable`, `Field`, `Method` và ngữ cảnh `throws Exception`. `T` không có bound rõ ràng nên erasure của setter parameter là `Object`.

Ba vị trí sử dụng trên đều nói tới biến `T` đã được `Holder` khai báo. Có thể ép kiểu sang `TypeVariable<?>` khi đã kiểm tra loại thực tế và dùng `getGenericDeclaration()`/`equals()` để nhận diện declaration.

Ngược lại, `Field.getType()` và `Method.getReturnType()` trả raw/erased types, không giữ đầy đủ cấu trúc generic. Khi cần đọc cấu trúc, dùng các phương thức bắt đầu bằng `getGeneric...` thích hợp.

## 10. Giải `T` trong ngữ cảnh một lớp con

Xét:

```java
class Base<T> {
    T item;
}

class Child extends Base<String> {}
```

`Base.class.getTypeParameters()[0]` vẫn là một biến kiểu `T`, không biến thành `String` khi truy cập từ `Child`. Muốn biết `T` tương ứng kiểu gì trong ngữ cảnh `Child`, phải:

1. Đọc `Child.class.getGenericSuperclass()` và xác nhận kết quả là `ParameterizedType` biểu diễn `Base<String>`.
2. Đọc type arguments qua `getActualTypeArguments()`.
3. Ánh xạ biến kiểu `T` của declaration `Base` với đối số kiểu `String` ở vị trí tương ứng.
4. Áp dụng ánh xạ vào generic field/method type nếu muốn biết kiểu hiệu dụng trong ngữ cảnh `Child`.

Với nhiều cấp như `Middle<U> extends Base<List<U>>` rồi `Leaf extends Middle<Integer>`, phải xử lý tuần tự các `ParameterizedType`, có thể là ánh xạ từ type variable này sang cấu trúc generic chứa type variable khác. Java Reflection cung cấp metadata nhưng không cung cấp một phương thức lõi duy nhất tự động giải mọi biến generic theo receiver subclass.

Điều này khác hoàn toàn với `getBounds()`: upper bound mô tả *điều kiện một type argument phải thỏa*, còn mapping theo subclass cho biết *type argument được khai báo* ở một quan hệ kế thừa cụ thể.

## 11. `TypeVariable` khác wildcard và parameterized type

Ví dụ bên trong class `<T>`:

```java
java.util.Map<String, java.util.List<? extends T>> values;
```

Nếu đọc `Field.getGenericType()`:

1. Outer `Map<...>` là `ParameterizedType`.
2. `String` là `Class<?>`.
3. `List<? extends T>` là một `ParameterizedType` khác.
4. `? extends T` là `WildcardType`.
5. Upper bound của wildcard là `T`, một `TypeVariable<?>` đã được class hoặc method khai báo.

Wildcard `?` **không tạo ra một declaration mới** như `T`; nó là một cấu trúc ở nơi sử dụng. `WildcardType.getUpperBounds()` nói về giới hạn wildcard, trong khi `TypeVariable.getBounds()` nói về giới hạn trên biến kiểu tại declaration.

Khi một generic parser trả về `Type`, hãy dùng `instanceof` phân nhánh theo `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType` và `GenericArrayType`. Ép mọi giá trị thành `Class<?>` dễ phát sinh `ClassCastException` hoặc làm mất thông tin.

## 12. Những lỗi thực tế khi dùng Reflection generic

| Nhầm lẫn | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Hai biến đều tên `T` là một | Scope/declaration khác nhau | Xét `getGenericDeclaration()` và `equals()` |
| `getBounds()` chứa actual type argument | Bounds là giới hạn khai báo | Đọc `ParameterizedType.getActualTypeArguments()` khi cần |
| `getBounds()` của `<T>` là mảng rỗng | Bound ngầm định là `Object` | Nhận `Object.class` |
| Mọi bounds đều là `Class` | `Comparable<T>` là `ParameterizedType` | Phân loại từng `Type` |
| Lớp con tự động có type parameters của cha | `getTypeParameters()` chỉ trả biến khai báo trực tiếp | Đọc thêm generic superclass/interfaces |
| `getClass()` của `Box<Integer>` chứa `Integer` | Erasure bỏ type arguments runtime trên instance | Dùng metadata subclass/type token hoặc đầu vào rõ ràng |
| `Field.getType()` thể hiện `List<T>` | Nó trả raw class `List` | Dùng `Field.getGenericType()` |
| `getAnnotations()` trả annotations trên bounds | Annotation type parameter khác annotation type-use | Dùng `getAnnotatedBounds()` |
| Dùng `==` để so hai `TypeVariable` | Instance identity không được bảo đảm | Dùng `equals()` |
| Duyệt `T extends Comparable<T>` vô hạn | Bound có thể tự tham chiếu | Theo dõi biến/declaration đã thăm |

Metadata cũng có thể lỗi nếu generic signature tham chiếu đến type không hiện diện hoặc mô hình parameterized không hợp lệ; các API generic có thể ném `TypeNotPresentException` hoặc `MalformedParameterizedTypeException`. Bộ phân tích metadata nghiêm túc cần báo đúng nguyên nhân thay vì coi mọi lỗi là một biến kiểu rỗng.

Với bridge methods do compiler sinh ra khi generic bị erasure, `Method.isBridge()` và `isSynthetic()` giúp bộ quét method phân biệt khai báo thực tế với mã hỗ trợ compiler-generated. Đừng gộp tên method hoặc tên `T` làm khóa mà bỏ qua signature và declaration.

## 13. Quy trình dùng `TypeVariable` trong framework

Khi xây dựng mapper, serializer, schema inspector hay công cụ tài liệu:

1. **Xác định GenericDeclaration.** Đây là `Class`, `Method` hay `Constructor` nào? Gọi `getTypeParameters()` ở chủ thể đúng.
2. **Định danh biến kiểu.** Dùng `getName()` và `getGenericDeclaration()` hoặc `equals()`; chú ý method có thể khai báo biến cùng tên class.
3. **Đọc mọi bounds.** Dùng `getBounds()`, xử lý `ParameterizedType`, `TypeVariable` và các cấu trúc lồng nhau đúng cách.
4. **Đọc annotation đúng vị trí.** Dùng `getAnnotations()` cho type parameter, `getAnnotatedBounds()` cho annotations của bounds.
5. **Đọc nơi sử dụng.** Dùng `getGenericType()`, `getGenericReturnType()`, `getGenericParameterTypes()`, `getGenericSuperclass()` hoặc `getGenericInterfaces()` tùy mục tiêu.
6. **Giải đối số kiểu theo ngữ cảnh nếu cần.** Từ `ParameterizedType` của lớp con hoặc type token, xây mapping từ declaration variable sang type argument cụ thể. Không biến `TypeVariable` nguyên gốc thành một kiểu khác.
7. **Tính đến erasure và metadata thiếu.** Không cố suy ra `Integer` từ một `new Box<Integer>()` thông thường khi thông tin ấy không còn trong runtime class; xử lý cycles khi bound tự tham chiếu.

### Tự kiểm tra

**Câu 1.** `class A<T>` và `class B<T>` cùng khai báo tên `T`. Hai type variables có bằng nhau không?  
Không. Chúng thuộc hai `GenericDeclaration` khác nhau.

**Câu 2.** `class Child extends Parent<String>`. Vì sao `Child.class.getTypeParameters()` rỗng?  
Vì `Child` không khai báo type parameter mới. Kiểu `String` nằm ở `ParameterizedType` của `getGenericSuperclass()`.

**Câu 3.** Tại sao `getBounds()` của `T extends Number & Comparable<T>` không nên ép tất cả sang `Class`?  
Vì `Comparable<T>` là `ParameterizedType`.

**Câu 4.** Nếu method `<U> U echo(U x)` khai báo `U`, `getGenericDeclaration()` của U trả gì?  
Đối tượng `Method` sở hữu khai báo `U`, không phải mặc định class chứa method.

**Câu 5.** `TypeVariable.getBounds()` có cho biết chính xác type argument của mọi instance `Box<T>` không?  
Không. Bounds là ràng buộc; type arguments cụ thể thường bị erasure trên instance và chỉ đọc được khi metadata phù hợp tồn tại.

## Ghi nhớ

- **`GenericDeclaration`** là nơi khai báo tham số kiểu: class/interface, method hoặc constructor; đọc bằng `getTypeParameters()`.
- **`TypeVariable`** biểu diễn biến kiểu của declaration, có tên, owner, upper bounds và annotations.
- **Tên `T` không đủ để nhận diện biến.** Xét owner và dùng `equals()`.
- **Upper bound khác actual type argument.** `getBounds()` không thay thế `ParameterizedType.getActualTypeArguments()`.
- **Type erasure** khiến việc suy ra generic runtime phụ thuộc metadata còn tồn tại trong khai báo.

Khi hiểu rõ thứ tự **declaration → type variable → nơi sử dụng → type arguments theo ngữ cảnh**, ta có thể đọc và xử lý hệ thống generic bằng Java Reflection mà không nhầm lẫn biến kiểu với kiểu cụ thể.
