# getBounds() và nhiều giới hạn kiểu trong Java Reflection

## 1. Mục tiêu và vấn đề cốt lõi

Trong Java Generics, một tham số kiểu không nhất thiết chấp nhận mọi kiểu tham chiếu. Người lập trình có thể khai báo **giới hạn trên (upper bounds)** để yêu cầu kiểu thực tế phải là subtype của một lớp và/hoặc triển khai những interface nhất định:

```java
class Metric<T extends Number & Comparable<T> & java.io.Serializable> {
    T value;
}
```

Khai báo này yêu cầu `T` đồng thời:

- Là một subtype của `Number`.
- Thực hiện `Comparable<T>` (so sánh được với kiểu `T` tương ứng).
- Thực hiện `Serializable`.

Dấu `&` có nghĩa **giao (intersection)** của các ràng buộc kiểu; không phải phép AND trên giá trị runtime và cũng không phải nhiều đối số generic khác nhau.

Với Reflection, câu hỏi quan trọng là: **Làm sao đọc được từng bound, theo đúng thứ tự và đúng cấu trúc generic?** API trung tâm là `java.lang.reflect.TypeVariable.getBounds()`.

Bài học phân biệt rõ:

1. `TypeVariable.getBounds()` dùng cho type parameter như `T`, `U`.
2. `WildcardType.getUpperBounds()` và `getLowerBounds()` dùng cho wildcard như `? extends Number` và `? super Integer`.
3. Quy tắc **nhiều bounds**, class bound, interface bounds và **type erasure**.
4. Cách đọc các bounds phức tạp như `Comparable<T>`, annotation trên bound và bound tự tham chiếu.
5. Giới hạn của Reflection: biết **hợp đồng kiểu được khai báo**, chưa chắc biết kiểu cụ thể được dùng cho một object tại runtime.

## 2. Bắt đầu từ `TypeVariable<?>`

Một type parameter được phản ánh qua interface `java.lang.reflect.TypeVariable<D>`, trong đó `D` là dạng generic declaration sở hữu type parameter (class, method hoặc constructor).

Ví dụ:

```java
class Holder<T extends Number> {
    T item;
}
```

Để lấy metadata của `T`:

```java
TypeVariable<?> variable = Holder.class.getTypeParameters()[0];
System.out.println(variable.getName()); // T
```

Các API thiết yếu:

| API | Kết quả | Ý nghĩa |
|---|---|---|
| `getName()` | `String` | Tên khai báo của type variable (`T`, `U`...) |
| `getBounds()` | `Type[]` | Các **upper bounds** theo khai báo |
| `getAnnotatedBounds()` | `AnnotatedType[]` | Những upper bounds kèm type-use annotations |
| `getGenericDeclaration()` | `GenericDeclaration` | Class, method hoặc constructor **khai báo** type variable |
| `getTypeName()` | `String` | Tên biểu diễn type variable; thường là `T` |

Đây là đoạn minh họa rời, cần import `java.lang.reflect.TypeVariable` và đưa lớp `Holder` vào cùng ngữ cảnh; chương trình chạy được hoàn chỉnh ở mục 10.

Muốn lấy type parameters từ các điểm khai báo khác:

```java
TypeVariable<?>[] fromClass = Holder.class.getTypeParameters();
TypeVariable<?>[] fromMethod = someMethod.getTypeParameters();
TypeVariable<?>[] fromConstructor = someConstructor.getTypeParameters();
```

`someMethod` phải là một `java.lang.reflect.Method`, `someConstructor` là một `Constructor<?>` đã tra cứu hợp lệ. `Class`, `Method` và `Constructor` đều cung cấp `getTypeParameters()` vì chúng là những `GenericDeclaration`. Mảng trống nếu chính declaration đó không khai báo type parameter.

**Quan trọng:** Tham số kiểu của một class, ví dụ `Holder<T>`, và tham số kiểu của một method, ví dụ `<T> void work(T arg)`, là **hai khai báo khác nhau** dù cùng tên `T`. Dùng `getGenericDeclaration()` để phân biệt khi phân tích metadata.

## 3. `TypeVariable.getBounds()` thực sự trả gì?

Chữ ký:

```java
Type[] getBounds()
```

Giá trị trả về là mảng các đối tượng `java.lang.reflect.Type`, tương ứng với **những upper bounds của type variable**. Với nhiều bound, chúng xuất hiện theo thứ tự khai báo, vì vậy không được tự sắp xếp lại nếu đang phân tích ý nghĩa erasure.

Ba tình huống quan trọng:

| Khai báo | Nội dung `getBounds()` | Diễn giải |
|---|---|---|
| `class A<T> {}` | `[Object.class]` | Không ghi bound thì upper bound ngầm định là `Object` |
| `class B<T extends Number> {}` | `[Number.class]` | Một bound là class |
| `class C<T extends Number & Comparable<T> & Serializable> {}` | `[Number.class, Comparable<T>, Serializable.class]` | Ba bounds theo thứ tự; bound thứ hai là `ParameterizedType` |

Không nên giả định rằng các phần tử mảng đều là `Class<?>`. Bởi `getBounds()` trả `Type[]`, phần tử có thể biểu diễn:

- `Class<?>`: bound thông thường như `Number`, `Serializable`.
- `ParameterizedType`: bound có type arguments như `Comparable<T>` hoặc `Function<String, Integer>`.
- `TypeVariable<?>`: bound trỏ tới một type parameter khác, như `<A extends Number, B extends A>`.

Với trường hợp không khai báo bound, **`getBounds()` vẫn trả mảng một phần tử `Object.class`**, chứ không phải mảng rỗng. Do đó code liệt kê bounds nên xử lý `Object` như upper bound mặc định, không suy từ `array.length == 0` rằng “không có ràng buộc”.

Ví dụ:

```java
TypeVariable<?> t = C.class.getTypeParameters()[0];
for (Type bound : t.getBounds()) {
    System.out.println(bound.getTypeName());
}
```

Trong ngữ cảnh `C<T extends Number & Comparable<T> & Serializable>` đã khai báo, kết quả là:

```text
java.lang.Number
java.lang.Comparable<T>
java.io.Serializable
```

Các đoạn trên là minh họa phụ thuộc lớp `C` và import `java.lang.reflect.Type`, `TypeVariable`. `getTypeName()` phù hợp để hiển thị; khi cần phân tích nghĩa của một bound, dùng các interface `Type` thay vì cắt chuỗi ở ký tự `<` hoặc `>`.

## 4. Cú pháp nhiều giới hạn: class trước, interface sau

Java cho phép viết nhiều upper bounds cho một type parameter:

```java
class Processor<T extends Number & Comparable<T> & java.io.Serializable> {
}
```

Các luật nguồn quan trọng:

1. Nếu có **class bound**, class đó phải **đứng đầu**, theo sau (nếu có) là các interface.
2. Tối đa **một class** trong danh sách bounds (Java không hỗ trợ kế thừa nhiều class).
3. Có thể có **nhiều interface bounds**, nối bằng `&`.
4. Nếu **chỉ có interface bounds**, interface đầu tiên đứng đầu danh sách và quyết định erasure.
5. Khi không có `extends` thì upper bound ngầm định là `Object`.
6. Java không hỗ trợ `<T super Number>` cho khai báo type parameter. `super` là cú pháp lower bound của **wildcard**, không phải cú pháp bound cho `T`.
7. Các bounds cần tuân theo quy tắc kiểu Java, chẳng hạn không được lặp interface theo cách tạo ra những cách tham số hóa khác nhau có cùng erasure.

Một số ví dụ:

```java
// Hợp lệ: class trước, interfaces sau
class A<T extends Number & Comparable<T> & java.io.Serializable> {}

// Hợp lệ: chỉ interfaces
class B<T extends Runnable & AutoCloseable> {}

// Hợp lệ: một bound
class C<T extends Number> {}

// Hợp lệ: không khai báo bound (ngầm định Object)
class D<T> {}
```

Các khai báo sau **không hợp lệ** (chỉ dùng để nhận diện lỗi, không đưa vào chương trình cần biên dịch):

```java
// Sai: đặt class sau interface
// class WrongA<T extends Comparable<T> & Number> {}

// Sai: không thể có hai class bounds
// class WrongB<T extends Number & java.util.ArrayList<String>> {}

// Sai: khai báo type variable không cho phép "super"
// class WrongC<T super Integer> {}
```

Việc hỗ trợ nhiều interface bounds hữu ích khi thuật toán cần **nhiều khả năng đồng thời**. Ví dụ một kiểu thỏa `Runnable & AutoCloseable` vừa có thể được thực thi qua `run()` vừa có thể đóng qua `close()`, dù không buộc nó kế thừa một class riêng của thư viện.

## 5. Bound đầu tiên và type erasure: tại sao thứ tự quan trọng?

**Erasure** là một lý do phải giữ nguyên thứ tự bounds. Theo luật Java, type parameter được thay bằng erasure của **bound đầu tiên**; nếu không khai báo bound, là `Object`.

Ví dụ:

```java
class Numeric<T extends Number & Comparable<T> & java.io.Serializable> {
    T value;
}
```

Với `Numeric.value`:

- `field.getType()` trả `Number.class`, vì `T` bị erasure thành `Number`.
- `field.getGenericType()` trả một `TypeVariable<?>` biểu diễn `T`.
- `((TypeVariable<?>) field.getGenericType()).getBounds()` vẫn có cả `Number`, `Comparable<T>` và `Serializable`.

Như vậy **erasure không có nghĩa Reflection xóa sạch mọi chữ ký generic**. Erasure ảnh hưởng kiểu runtime/code liên quan, còn metadata signature generic có thể giữ cấu trúc khai báo để Reflection phân tích.

Khi chỉ có các interface bounds:

```java
class ComparableHolder<U extends Comparable<U> & java.io.Serializable> {
    U value;
}
```

`field.getType()` của `value` là `Comparable.class`, không phải `Serializable.class` và không phải `Object.class`. Interface đầu tiên giữ vai trò erasure khi không có class bound.

Khi không có bound:

```java
class AnyHolder<V> {
    V value;
}
```

`getType()` của `value` là `Object.class`; `getGenericType()` là `V`; `getBounds()` của `V` là `[Object.class]`.

Bảng so sánh:

| Khai báo tham số kiểu | Erasure của tham số | `getBounds()` |
|---|---|---|
| `<T>` | `Object` | `[Object]` |
| `<T extends Number>` | `Number` | `[Number]` |
| `<T extends Number & Serializable>` | `Number` | `[Number, Serializable]` |
| `<T extends Comparable<T> & Serializable>` | `Comparable` | `[Comparable<T>, Serializable]` |
| `<T extends Runnable & AutoCloseable>` | `Runnable` | `[Runnable, AutoCloseable]` |

**Không hoán đổi bounds để “đẹp hơn”** khi phân tích chữ ký: thứ tự có thể ảnh hưởng erasure và bytecode method/field descriptors. Nếu chỉ muốn hiển thị thứ tự alphabet cho giao diện, hãy hiểu rằng bạn đang tạo một cách trình bày phụ, không phải thứ tự nguồn có ý nghĩa ngữ nghĩa.

## 6. Phân tích từng bound theo cấu trúc `Type`

Với một type variable, đừng viết code như sau:

```java
Class<?> bound = (Class<?>) variable.getBounds()[0];
```

Cách ép kiểu trực tiếp chỉ hợp lệ nếu bound đầu tiên thật sự được biểu diễn bởi `Class<?>`. Với `T extends Comparable<T>`, bound đầu tiên là `ParameterizedType` và phép ép trên sẽ ném `ClassCastException`.

Hướng an toàn:

```java
for (Type bound : variable.getBounds()) {
    if (bound instanceof Class<?> clazz) {
        System.out.println("Class/interface: " + clazz.getName());
    } else if (bound instanceof ParameterizedType p) {
        System.out.println("Parameterized: " + p.getTypeName());
        System.out.println("Raw: " + p.getRawType().getTypeName());
    } else if (bound instanceof TypeVariable<?> other) {
        System.out.println("Type parameter khác: " + other.getName());
    } else {
        System.out.println("Loại Type khác: " + bound.getTypeName());
    }
}
```

Đoạn minh họa trên giả định đã có biến `variable` hợp lệ và import các kiểu thuộc `java.lang.reflect`. Các đối tượng `Type` có thể lồng nhau: với `Comparable<T>`, `getRawType()` cho `Comparable` và `getActualTypeArguments()[0]` cho type variable `T`. Phải đi vào `ParameterizedType` để giữ được type arguments.

Ví dụ:

```java
class Ranked<T extends Comparable<T>> {
}
```

```java
TypeVariable<?> t = Ranked.class.getTypeParameters()[0];
ParameterizedType p = (ParameterizedType) t.getBounds()[0];

System.out.println(p.getRawType().getTypeName());           // java.lang.Comparable
System.out.println(p.getActualTypeArguments()[0].getTypeName()); // T
```

Nếu cần hỗ trợ các kiểu phức tạp hơn, một bộ phân tích metadata có thể phải xử lý cả `GenericArrayType` và `WildcardType` khi duyệt sâu các type arguments. Nhưng **không phải mọi `Type` đều có `getBounds()`**: đây là phương thức chuyên biệt của `TypeVariable` (và các accessor tương ứng của `WildcardType`).

### Bound là một type variable khác

Java cho phép type parameter phụ thuộc type parameter được khai báo trước:

```java
class Pair<A extends Number, B extends A> {
    B value;
}
```

`Pair.class.getTypeParameters()[1].getBounds()[0]` phản ánh biến kiểu `A` (một `TypeVariable<?>`), chứ không thay tự động thành `Number.class`. Muốn suy ra bound hữu hiệu sâu hơn, công cụ cần đi tiếp tới bounds của `A` và tránh vòng lặp với những kiểu tự tham chiếu.

## 7. Giới hạn tự tham chiếu và xử lý chu trình

Một kiểu generic hợp lệ có thể tham chiếu lại chính type parameter của nó:

```java
class Node<T extends Comparable<T>> {
}
```

Một ví dụ quen thuộc hơn từ Java API:

```java
public abstract class Enum<E extends Enum<E>>
        implements Comparable<E>, java.io.Serializable {
    // Khai báo rút gọn để minh họa signature,
    // không phải toàn bộ mã nguồn của java.lang.Enum.
}
```

Đây là **F-bounded polymorphism**: bound của `E` là `Enum<E>`, trong đó type argument của `Enum` lại là chính `E`. Dữ liệu Reflection biểu diễn quan hệ này hợp lệ; đừng triển khai bộ hiển thị đệ quy theo cách liên tục phân tích `E` → `Enum<E>` → `E` → ... vô hạn.

Ví dụ đọc một cấp:

```java
TypeVariable<?> e = Enum.class.getTypeParameters()[0];
Type[] bounds = e.getBounds();
System.out.println(bounds[0].getTypeName()); // java.lang.Enum<E>
```

Nếu xây dựng schema graph, hãy lưu tập type variables/declarations đã đi qua để cắt chu trình. Khi so sánh type variables, dùng ngữ nghĩa `equals`/`getGenericDeclaration()` phù hợp; không giả định reference identity (`==`) luôn là cách duy nhất nhận diện metadata Reflection được biểu diễn lại.

Một biến kiểu có bound phức tạp **không đồng nghĩa** chương trình đã biết type argument cụ thể tại runtime. Ví dụ `class Holder<T extends Number>` khi nhận `Holder<Integer>` vẫn thường chỉ có một `Class` của `Holder` sau erasure; Reflection không đọc ra `Integer` từ một instance bất kỳ chỉ bằng `T.getBounds()`.

## 8. `getBounds()` của TypeVariable và upper/lower bounds của wildcard

Đây là nhầm lẫn thường gặp nhất khi xây generic inspector.

### 8.1. Type parameter: `T extends ...`

`TypeVariable.getBounds()` trả danh sách **upper bounds**. Type parameter không có API `getLowerBounds()` vì cú pháp khai báo `<T super X>` không được Java hỗ trợ.

Ví dụ:

```java
class Service<T extends Number & Comparable<T>> {
}
```

Kết quả là hai bounds: `Number`, `Comparable<T>`.

### 8.2. Wildcard: `? extends ...` hoặc `? super ...`

Wildcards xuất hiện trong type arguments, ví dụ:

```java
java.util.List<? extends Number> producers;
java.util.List<? super Integer> consumers;
java.util.List<?> unknown;
```

Mỗi wildcard được phản ánh qua `java.lang.reflect.WildcardType` với hai API riêng:

| Wildcard | `getUpperBounds()` | `getLowerBounds()` |
|---|---|---|
| `? extends Number` | `[Number]` | `[]` |
| `? super Integer` | `[Object]` | `[Integer]` |
| `?` | `[Object]` | `[]` |

Nếu wildcard không có upper bound tường minh, API trả upper bound `Object`. Nếu không có lower bound tường minh, `getLowerBounds()` trả **mảng rỗng**, không phải `[Object]`. Với `? super Integer`, upper bound mặc định vẫn là `Object`; lower bound là `Integer`.

Muốn tìm wildcard của một field khai báo `List<? extends Number>`:

```java
Field f = Example.class.getDeclaredField("producers");
ParameterizedType list = (ParameterizedType) f.getGenericType();
WildcardType wildcard =
        (WildcardType) list.getActualTypeArguments()[0];

for (Type upper : wildcard.getUpperBounds()) {
    System.out.println(upper.getTypeName());
}
```

Đây là đoạn minh họa phụ thuộc lớp `Example` có trường `producers`, cần import các reflection types tương ứng. Lưu ý `field.getGenericType()` là **`ParameterizedType` của `List`**, chưa phải `WildcardType`. Phải đi tới actual type argument mới lấy được wildcard.

### 8.3. “Nhiều bounds” ở wildcard có giống TypeVariable không?

**Không giống trong cú pháp Java source hiện nay.**

- Type parameter cho phép `<T extends Number & Comparable<T>>`.
- Wildcard dùng `? extends Number`, `? super Integer` hoặc `?`. Java source **không cho phép viết `List<? extends Number & Serializable>`** với intersection bound theo cú pháp type parameter.
- API `WildcardType.getUpperBounds()` và `getLowerBounds()` vẫn trả **mảng `Type[]`**; tài liệu lưu ý code dùng API nên được viết đủ tổng quát để xử lý nhiều phần tử nếu dạng kiểu trong tương lai có hỗ trợ. Không suy từ kiểu trả về mảng rằng source syntax hiện tại đã chấp nhận nhiều bounds của wildcard.

Các quy tắc generics như **PECS** (producer extends, consumer super) có ích khi quyết định thao tác đọc/ghi collection, nhưng đó là bài về type safety của collection. Trong Reflection, nhiệm vụ trực tiếp ở đây là xác định **cấu trúc bound metadata**, không phải tự ý thay đổi các phần tử của collection.

## 9. Annotation trên từng bound: `getAnnotatedBounds()`

Từ Java 8, annotation có thể được đặt trên **nơi sử dụng kiểu** (`ElementType.TYPE_USE`) nếu annotation được định nghĩa phù hợp.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Marked {}

class Sample<T extends @Marked Number & @Marked Comparable<T>> {}
```

`TypeVariable.getBounds()` cung cấp các `Type`, giúp biết `Number` và `Comparable<T>`, nhưng không giữ giao diện truy vấn **annotation trên từng bound**. Để lấy những annotation đó, dùng:

```java
TypeVariable<?> t = Sample.class.getTypeParameters()[0];
AnnotatedType[] annotatedBounds = t.getAnnotatedBounds();

boolean firstMarked =
        annotatedBounds[0].isAnnotationPresent(Marked.class);
boolean secondMarked =
        annotatedBounds[1].isAnnotationPresent(Marked.class);
```

Hai đoạn này minh họa trong cùng ngữ cảnh; cần import `Retention`, `RetentionPolicy`, `Target`, `ElementType` và `AnnotatedType`. Một ví dụ chạy đầy đủ có type-use annotations được cung cấp ở mục 10.

Khác biệt giữa hai API:

- `getBounds()`: cấu trúc kiểu theo khai báo, với `Type[]`.
- `getAnnotatedBounds()`: cùng các upper bounds nhưng được bọc dưới `AnnotatedType[]` để đọc type-use annotations.
- `AnnotatedType.getType()` cho `Type` của bound tương ứng.
- `AnnotatedType.getAnnotations()` / `getAnnotation(...)` giúp đọc annotation trên **việc sử dụng kiểu**, không phải mọi annotation được khai báo trên bản thân class `Number` hoặc interface `Comparable`.

Khi không khai báo bound, `getAnnotatedBounds()` thể hiện upper bound `Object` không được gắn annotation. Chú ý retention policy: annotation chỉ có trong Reflection runtime nếu metadata được giữ ở runtime theo cách áp dụng.

## 10. Chương trình Java 17+ hoàn chỉnh: class, method, erasure, wildcard và annotation

Ví dụ sau dùng một file `BoundsDemo.java` và bao gồm:

- Nhiều bounds gồm class + interfaces.
- Nhiều bounds chỉ gồm interfaces.
- Type parameter không bound, bound tự tham chiếu và method type parameter.
- Bound có annotation tại nơi sử dụng kiểu.
- Phân biệt `TypeVariable.getBounds()` với các bounds của wildcard.
- Sự khác biệt giữa erasure và generic metadata khi truy vấn field qua subclass.

### 10.1. Mã nguồn

Lưu nguyên văn vào `BoundsDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.Arrays;
import java.util.List;

public class BoundsDemo {
    static class Multi<T extends Number & Comparable<T> & java.io.Serializable> {
        public T item;
    }

    static class IntegerMulti extends Multi<Integer> { }

    static class Interfaces<U extends Comparable<U> & java.io.Serializable> {
        U value;
    }

    static class Unbounded<V> {
        V value;
    }

    static class Recursive<E extends Enum<E>> { }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Marked { }

    static class Annotated<A extends @Marked Number & @Marked Comparable<A>> { }

    static class Wildcards {
        List<? extends Number> upper;
        List<? super Integer> lower;
        List<?> any;
    }

    static <M extends Runnable & AutoCloseable> void process(M value) { }

    private static String names(Type[] types) {
        return Arrays.toString(Arrays.stream(types)
                .map(Type::getTypeName).toArray(String[]::new));
    }

    private static void wildcard(String fieldName) throws NoSuchFieldException {
        Field field = Wildcards.class.getDeclaredField(fieldName);
        ParameterizedType list = (ParameterizedType) field.getGenericType();
        WildcardType wildcard = (WildcardType) list.getActualTypeArguments()[0];
        System.out.println(fieldName + " upper=" + names(wildcard.getUpperBounds())
                + " lower=" + names(wildcard.getLowerBounds()));
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        TypeVariable<?> multi = Multi.class.getTypeParameters()[0];
        System.out.println("Multi bounds: " + names(multi.getBounds()));
        System.out.println("Multi erased: "
                + Multi.class.getDeclaredField("item").getType().getTypeName());
        System.out.println("Multi generic: "
                + Multi.class.getDeclaredField("item").getGenericType().getTypeName());

        System.out.println("Interfaces bounds: "
                + names(Interfaces.class.getTypeParameters()[0].getBounds()));
        System.out.println("Interfaces erased: "
                + Interfaces.class.getDeclaredField("value").getType().getTypeName());
        System.out.println("Unbounded bounds: "
                + names(Unbounded.class.getTypeParameters()[0].getBounds()));
        System.out.println("Recursive bounds: "
                + names(Recursive.class.getTypeParameters()[0].getBounds()));

        Method method = BoundsDemo.class.getDeclaredMethod("process", Runnable.class);
        System.out.println("Method bounds: "
                + names(method.getTypeParameters()[0].getBounds()));

        AnnotatedType[] annotated =
                Annotated.class.getTypeParameters()[0].getAnnotatedBounds();
        System.out.println("Annotated count: " + annotated.length);
        System.out.println("Annotations present: "
                + (annotated[0].isAnnotationPresent(Marked.class)
                && annotated[1].isAnnotationPresent(Marked.class)));

        wildcard("upper");
        wildcard("lower");
        wildcard("any");

        System.out.println("Subclass field generic: "
                + IntegerMulti.class.getField("item").getGenericType().getTypeName());
        System.out.println("Subclass generic parent: "
                + IntegerMulti.class.getGenericSuperclass().getTypeName());
    }
}
```

### 10.2. Biên dịch và chạy

Dùng JDK 17 trở lên:

```bash
javac --release 17 BoundsDemo.java
java BoundsDemo
```

Kết quả đã được đối chiếu qua biên dịch `--release 17` và chạy trên OpenJDK 21:

```text
Multi bounds: [java.lang.Number, java.lang.Comparable<T>, java.io.Serializable]
Multi erased: java.lang.Number
Multi generic: T
Interfaces bounds: [java.lang.Comparable<U>, java.io.Serializable]
Interfaces erased: java.lang.Comparable
Unbounded bounds: [java.lang.Object]
Recursive bounds: [java.lang.Enum<E>]
Method bounds: [java.lang.Runnable, java.lang.AutoCloseable]
Annotated count: 2
Annotations present: true
upper upper=[java.lang.Number] lower=[]
lower upper=[java.lang.Object] lower=[java.lang.Integer]
any upper=[java.lang.Object] lower=[]
Subclass field generic: T
Subclass generic parent: BoundsDemo$Multi<java.lang.Integer>
```

### 10.3. Giải thích kết quả từng nhóm

**`Multi<T>`:** Có ba upper bounds. `Number` đứng đầu nên field `item` có runtime type sau erasure là `Number`. Tuy vậy `getGenericType()` của field vẫn trả type variable `T`.

**`Interfaces<U>`:** Chỉ có interface bounds. `Comparable<U>` đứng đầu nên erasure thành `Comparable`; `Serializable` vẫn xuất hiện trong kết quả `getBounds()`.

**`Unbounded<V>`:** Không khai báo `extends` thì `getBounds()` trả `Object`.

**`Recursive<E>`:** Bound là `Enum<E>`, chứa tham chiếu ngược tới `E`. Đây là một dạng `ParameterizedType`, không phải `Enum.class` đơn thuần.

**Method `process`:** Tham số kiểu `M` thuộc **generic declaration của method**. `getDeclaredMethod("process", Runnable.class)` dùng `Runnable.class` vì đây là erasure của bound đầu tiên `M extends Runnable & AutoCloseable`.

**Type-use annotations:** Hai bounds của `A` đều có `@Marked`, vì vậy `getAnnotatedBounds()` trả hai phần tử và cả hai đều chứa annotation tại runtime.

**Wildcards:** `? extends Number` có upper bound `Number`, không có lower bound; `? super Integer` có upper bound mặc định `Object` và lower bound `Integer`; `?` có `Object` và không có lower bound.

**`IntegerMulti`:** Dù subclass cố định type argument `Integer`, field `item` vẫn do `Multi<T>` khai báo. Lấy field đó qua subclass, `getGenericType()` **vẫn là `T`**. Quan hệ `Multi<Integer>` nằm trong metadata `IntegerMulti.class.getGenericSuperclass()`, cần được kết hợp nếu muốn suy ra kiểu cụ thể theo ngữ cảnh subclass.

## 11. Ứng dụng của bounds trong framework và công cụ phân tích

### 11.1. Kiểm tra contract của generic API

Một thư viện plugin có thể yêu cầu type parameter phải đáp ứng nhiều khả năng:

```java
interface Task { void run(); }
interface Stoppable { void stop(); }

class TaskPool<T extends Task & Stoppable> { }
```

Một metadata scanner đọc `TaskPool.class.getTypeParameters()[0].getBounds()` sẽ biết contract yêu cầu **cả `Task` lẫn `Stoppable`**. Nếu chỉ xem raw erasure, có thể thấy `Task` rồi bỏ sót `Stoppable`.

Điều đó hữu ích khi tạo tài liệu API, kiểm tra chữ ký plugin hoặc phân tích schema; bản thân metadata không thay thế compile-time generic type checking.

### 11.2. Mapper / serializer có generic superclass

Một serializer có thể khảo sát `T extends Number` để biết contract cơ bản của trường; nhưng khi object thuộc subclass `IntegerMulti`, muốn biết `T = Integer` phải đọc thêm `ParameterizedType` của generic superclass và xây ánh xạ biến kiểu (`T`) sang type argument (`Integer`).

`getBounds()` trả về **giới hạn cho phép**, không trả về **type argument thực tế được chọn**. Đó là hai câu hỏi độc lập:

- `T extends Number` trả lời “`T` tối thiểu phải thỏa kiểu nào?”
- `Multi<Integer>` trả lời “trong quan hệ kế thừa cụ thể này, `T` được gán kiểu nào?”

Không suy rằng khi `T extends Number`, mọi instance đều chứa `Integer`; `Double` hoặc một subtype `Number` khác có thể cũng hợp lệ nếu thỏa các interface bounds bổ sung.

### 11.3. Xây generic inspector robust

Một inspector thường cần:

1. Lấy `Class.getTypeParameters()` hoặc `Method.getTypeParameters()`.
2. Với mỗi `TypeVariable<?>`, lưu `getName()` và `getGenericDeclaration()`.
3. Duyệt **tất cả** phần tử `getBounds()` theo đúng thứ tự.
4. Phân loại từng `Type` bằng `instanceof`.
5. Khi có `ParameterizedType`, đi tiếp vào `getRawType()` và `getActualTypeArguments()`.
6. Với type-use annotations, đọc `getAnnotatedBounds()` theo thứ tự tương ứng.
7. Với recursive bounds, nhận diện chu trình; với superclass generic, lập ánh xạ type variables theo ngữ cảnh.

**Không bắt buộc dùng `setAccessible(true)`** để đọc metadata của generic type parameters. Access suppression liên quan đến thao tác vào thành viên bị hạn chế quyền, không phải điều kiện chung cho `getBounds()`.

## 12. Lỗi phổ biến và cách tránh

| Sai lầm | Nguyên nhân | Cách sửa |
|---|---|---|
| Nghĩ `getBounds()` rỗng khi `<T>` | Không khai báo bound vẫn có `Object` ngầm định | Xử lý `[Object.class]` |
| Chỉ đọc `getBounds()[0]` | Bỏ sót các interface bounds bổ sung | Duyệt toàn bộ `Type[]` |
| Ép mọi bound thành `Class<?>` | `Comparable<T>` là `ParameterizedType` | Phân loại `Type` bằng `instanceof` |
| Đổi thứ tự bounds tùy ý | Erasure dựa trên bound đầu tiên | Giữ nguyên thứ tự nguồn |
| Cho rằng nhiều bound = nhiều class | Java không có multiple class inheritance | Chỉ một class bound, còn lại interfaces |
| Viết `T super Number` | Type parameter không có lower-bound syntax | Dùng `extends` cho type parameter; `? super` cho wildcard |
| Viết `List<? extends A & B>` trong Java source | Wildcard không hỗ trợ intersection syntax này | Dùng type parameter `<T extends A & B>` ở declaration thích hợp |
| Gọi `getBounds()` trực tiếp trên `ParameterizedType` | `ParameterizedType` không có API này | Duyệt `getActualTypeArguments()`, rồi nhận diện `TypeVariable` hoặc `WildcardType` |
| Nghĩ `? super Integer` có upper bound là `Integer` | `Integer` là **lower bound** | `upper=[Object]`, `lower=[Integer]` |
| Cho rằng `getBounds()` cho type cụ thể của `Box<Integer>` | Bounds là metadata của declaration | Xem `getGenericSuperclass()`/generic interfaces và giải biến kiểu |
| Đệ quy vô hạn với `Enum<E extends Enum<E>>` | Bound tham chiếu lại type variable | Ghi nhận các declaration/type variables đã thăm |
| Tìm bound annotation trong `getBounds()` | `Type[]` không có giao diện annotation-use | Dùng `getAnnotatedBounds()` |
| Dùng `Type.getTypeName()` để parse generic bằng regex đơn giản | Type lồng nhau và wildcard làm parsing thủ công dễ sai | Phân tích cấu trúc `Type` |
| Giả định metadata luôn hoàn hảo | Generic signature có thể thiếu/không hợp lệ | Xử lý `TypeNotPresentException`, `MalformedParameterizedTypeException`, `GenericSignatureFormatError` phù hợp |

Một số lưu ý thêm:

- `TypeVariable.getBounds()` có thể kích hoạt việc phân giải kiểu được nhắc tới trong bounds. Với metadata không hợp lệ hoặc type không thể tải, Javadoc cho phép `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` trong những trường hợp cụ thể.
- Chữ ký generic lấy từ bytecode/class metadata. Đừng dùng kết quả Reflection làm cơ chế kiểm chứng an ninh để cho phép tự do tải/chạy class tùy ý; việc đọc schema và việc thực thi mã là hai hoạt động khác nhau.
- Hai type variables trùng tên `T` có thể thuộc các generic declarations khác nhau. Khi xây bảng tra cứu, khóa nhận diện cần tính tới declaration, không chỉ tên ký tự.

## 13. Tự kiểm tra kiến thức

1. Với `class A<T> {}`, `A.class.getTypeParameters()[0].getBounds()` trả mảng mấy phần tử, và phần tử đó là gì?
2. Với `T extends Number & Comparable<T> & Serializable`, tại sao có ba bounds nhưng field kiểu `T` chỉ có một raw `Class<?>` là `Number`?
3. Tại sao `getBounds()[1]` của `Comparable<T>` không nên ép về `Class<?>`?
4. Nếu chỉ viết `T extends Runnable & AutoCloseable`, interface nào quyết định erasure?
5. `<T extends A & B>` khác `List<? extends A>` ở chỗ nào? Có dùng `? extends A & B` được trong Java source không?
6. `getBounds()` và `getAnnotatedBounds()` khác nhau ở dữ liệu nào?
7. Vì sao bound `Enum<E>` của `E extends Enum<E>` có thể dẫn tới vòng lặp khi phân tích đệ quy?
8. Khi field `T` khai báo ở superclass generic nhưng truy vấn qua subclass `Superclass<Integer>`, tại sao `Field.getGenericType()` vẫn có thể trả `T`?
9. Với `List<? super Integer>`, lower bound và upper bound của wildcard lần lượt là gì?
10. Muốn hiển thị tất cả upper bounds của method type parameter, bắt đầu từ đối tượng `Method` và gọi các API nào?

**Ghi nhớ:** `TypeVariable.getBounds()` trả **toàn bộ upper bounds** của một tham số kiểu, với `Object` ngầm định nếu không khai báo bound. Khi có nhiều bounds, **bound đầu tiên quyết định erasure**, nhưng metadata generic còn giữ những bounds bổ sung. `WildcardType` có API upper/lower bounds riêng, và `getAnnotatedBounds()` dùng để khảo sát annotations trên từng giới hạn kiểu.

Tài liệu chuẩn để đối chiếu: [TypeVariable (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html), [WildcardType (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html), [ParameterizedType (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html), [AnnotatedType (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html), [JLS §4.4 — Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4), [JLS §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6).