# `TypeVariable`: nơi khai báo và các giới hạn trong Java Reflection

Trong Java Generics, một tham số kiểu như `T`, `E` hay `U` có thể được **khai báo bởi class, interface, method hoặc constructor**. Khi dùng reflection để nghiên cứu tham số kiểu đó, Java biểu diễn nó bằng interface **`java.lang.reflect.TypeVariable<D extends GenericDeclaration>`**.

Ví dụ:

```java
class Box<T extends Number> {
    T value;

    <U extends CharSequence> U echo(U input) {
        return input;
    }
}
```

Ở đây:

- `T` là **type variable do class `Box` khai báo**, với upper bound `Number`.
- `U` là **type variable do method `echo` khai báo**, với upper bound `CharSequence`.
- `T` và `U` không phải tên của các runtime class cụ thể. Chúng đại diện cho **biến kiểu của khai báo**; cách gắn type arguments ở nơi sử dụng sẽ được compiler kiểm tra theo hợp đồng generic.

Dùng reflection:

```java
java.lang.reflect.TypeVariable<?> t =
        Box.class.getTypeParameters()[0];

System.out.println(t.getName()); // T
System.out.println(t.getBounds()[0].getTypeName());
// java.lang.Number
```

**Hai câu hỏi cốt lõi khi gặp `TypeVariable` là: “Ai khai báo biến kiểu này?” và “Các upper bounds của nó là gì?”** Câu trả lời nằm ở `getGenericDeclaration()` và `getBounds()`, không phải bằng cách đoán từ tên `T` hay runtime object.

## 1. Vị trí của `TypeVariable` trong hệ thống `Type`

`java.lang.reflect.Type` là interface chung cho những mô tả kiểu được reflection cung cấp. Các dạng tiêu biểu:

| Đối tượng reflection | Đại diện cho | Ví dụ |
| --- | --- | --- |
| `Class<?>` | Runtime class/interface/primitive/array với component type phù hợp | `String.class`, `Number.class`, `String[].class` |
| `ParameterizedType` | Kiểu tham số hóa của một khai báo | `List<String>`, `Comparable<T>` |
| **`TypeVariable<D>`** | **Biến kiểu được khai báo bởi generic declaration** | `T` trong `Box<T>`, `U` trong `<U> U echo(U)` |
| `WildcardType` | Type argument dạng wildcard | `? extends Number`, `? super Integer` |
| `GenericArrayType` | Array có generic component type không reifiable | `T[]`, `List<String>[]` |

`TypeVariable` cũng liên quan `AnnotatedElement`, vì có thể đọc annotation trên **khai báo type parameter** (khi annotation có retention phù hợp).

Không được đánh đồng:

```java
class Example<T extends Number> {
    java.util.List<T> values;
}
```

- `T` là **`TypeVariable`**.
- `List<T>` là **`ParameterizedType`** ở ngoài; phần tử của `getActualTypeArguments()` là `TypeVariable` của `T`.
- `Number.class` là **`Class`** mô tả upper bound đã nêu.
- `T[]` trong một khai báo là **`GenericArrayType`** ở ngoài, và generic component type bên trong là `TypeVariable`.

Một cây reflection có thể chứa nhiều dạng `Type` lồng nhau. Đừng cast mọi giá trị `Type` thành `Class`.

## 2. Chữ ký `TypeVariable<D extends GenericDeclaration>` nói gì?

Có thể hình dung những thành viên quan trọng của interface:

```java
// SƠ ĐỒ API, không phải mã nguồn định nghĩa lại TypeVariable:
interface TypeVariable<D extends java.lang.reflect.GenericDeclaration>
        extends java.lang.reflect.Type,
                java.lang.reflect.AnnotatedElement {

    java.lang.reflect.Type[] getBounds();
    D getGenericDeclaration();
    String getName();
    java.lang.reflect.AnnotatedType[] getAnnotatedBounds();
}
```

Tham số `D` trong **chính interface `TypeVariable<D>`** chỉ định **loại đối tượng reflection đại diện cho nơi khai báo**. `GenericDeclaration` được hiện thực bởi `Class`, `Method` và `Constructor` cho các trường hợp liên quan.

Ví dụ bạn có thể gặp `TypeVariable<Class<MyBox>>` khi đọc type parameters của class và `TypeVariable<Method>` khi đọc từ một method. Trong code xử lý chung, `TypeVariable<?>` đủ dùng nếu không cần giữ loại declaration chính xác ở compile time.

Các thành viên có vai trò khác nhau:

- `getName()`: tên nguồn của type variable, ví dụ `T`, `E`, `K`.
- `getGenericDeclaration()`: đối tượng **Class/Method/Constructor đã khai báo** type variable, không phải object generic ở runtime.
- `getBounds()`: danh sách **upper bounds** dưới dạng `Type[]`, theo thứ tự được biểu diễn trong khai báo.
- `getAnnotatedBounds()`: các upper bounds ở dạng **`AnnotatedType[]`**, để đọc type-use annotations trên bounds.
- Các API từ `AnnotatedElement`, chẳng hạn `getAnnotation(...)`, cho phép đọc annotations đặt trên **chính khai báo type parameter**, khi phù hợp với `@Target` và `@Retention`.

**Lưu ý:** đoạn trên chỉ minh họa hình dạng API. Trong chương trình thực tế, bạn import và sử dụng `java.lang.reflect.TypeVariable` có sẵn, không tự định nghĩa interface trùng tên.

## 3. Ai có thể khai báo type variable?

Một điểm đặc biệt của Java reflection: **generic declaration** có thể là class/interface, method hoặc constructor.

### 3.1. Class/interface generic

```java
class Pair<K, V> {
    K key;
    V value;
}
```

Đọc type variables do class khai báo:

```java
java.lang.reflect.TypeVariable<?>[] variables =
        Pair.class.getTypeParameters();

for (java.lang.reflect.TypeVariable<?> variable : variables) {
    System.out.println(variable.getName());
}
```

Đầu ra:

```text
K
V
```

`Pair.class.getTypeParameters()` trả các tham số kiểu **được khai báo trực tiếp ở `Pair`**, theo thứ tự; không trả type arguments cụ thể của một instance `Pair<String, Integer>`.

Một interface generic cũng là generic declaration:

```java
interface Repository<ID, ENTITY> {
    ENTITY find(ID id);
}
```

`Repository.class.getTypeParameters()` cho hai biến `ID` và `ENTITY`.

### 3.2. Generic method

```java
class Utilities {
    static <T extends Number> T same(T value) {
        return value;
    }
}
```

Đọc từ chính đối tượng `Method`:

```java
java.lang.reflect.Method method =
        Utilities.class.getDeclaredMethod("same", Number.class);

java.lang.reflect.TypeVariable<?> t =
        method.getTypeParameters()[0];

System.out.println(t.getGenericDeclaration().equals(method)); // true
```

**Tại sao tìm method bằng `Number.class` thay vì `T.class`?** Vì `T` có bound `Number`, nên erasure của tham số `T` trong descriptor dùng để tìm `getDeclaredMethod` là `Number`.

### 3.3. Generic constructor

Constructor của một class có thể tự khai báo type parameter:

```java
class Message {
    <T extends CharSequence> Message(T text) {
        System.out.println(text);
    }
}
```

Ví dụ reflection:

```java
java.lang.reflect.Constructor<?> ctor =
        Message.class.getDeclaredConstructor(CharSequence.class);

java.lang.reflect.TypeVariable<?> t =
        ctor.getTypeParameters()[0];

System.out.println(t.getGenericDeclaration().equals(ctor)); // true
```

Constructor type parameter **khác** type parameter của class, ngay cả khi constructor nằm trong một generic class. `getTypeParameters()` của constructor chỉ trả những tham số mà **constructor tự khai báo**.

**Quan trọng:** khi so sánh các đối tượng `Method`/`Constructor` do reflection trả về, dùng `.equals()` thay vì dựa vào tham chiếu `==`. Hai lần truy vấn reflection có thể cung cấp wrapper objects khác nhau đại diện cho cùng một declaration. Với class object, ví dụ `Box.class`, đối tượng `Class` biểu diễn cùng class do một class loader cụ thể định danh.

## 4. `getGenericDeclaration()`: tên giống nhau không có nghĩa cùng một biến kiểu

Java cho phép một generic method dùng lại tên `T` của class; method-level `T` che khuất class-level `T` trong phạm vi method:

```java
class Container<T extends Number> {
    T classValue;

    <T extends CharSequence> T echo(T value) {
        return value;
    }
}
```

Ở đây có **hai type variables độc lập**:

- `T` của `Container<T extends Number>`, được **class `Container`** khai báo.
- `T` của `<T extends CharSequence> T echo(T)`, được **method `echo`** khai báo.

So sánh theo tên là sai:

```java
// Hai TypeVariable đọc từ class và method:
// classT.getName().equals(methodT.getName()) -> true
// classT.equals(methodT)                   -> false
```

Đây không phải mâu thuẫn: **tên `T` chỉ là nhãn**, giống việc hai method khác nhau có cùng tên biến local `value`. Để hiểu type variable, phải xét **generic declaration** và vị trí khai báo.

Nếu đang dựng bản đồ ánh xạ generic types cho một framework, không dùng chuỗi `"T"` làm key toàn cục. Những biến kiểu có tên trùng trong hai class, hai method hoặc hai constructor khác nhau có ý nghĩa và bounds riêng.

### Cách so sánh đúng

```java
boolean sameDeclaration =
        classT.getGenericDeclaration()
              .equals(methodT.getGenericDeclaration());

boolean sameVariable = classT.equals(methodT);
```

Các kết quả phản ánh **định danh khai báo**, không chỉ tên. `TypeVariable` có hợp đồng `equals`/`hashCode` để đại diện type variables của cùng generic declaration; không nên dựa vào object identity `==` của các wrapper reflection.

## 5. `getBounds()`: đọc upper bounds và mặc định `Object`

Xét:

```java
class Simple<T, N extends Number> {}
```

Nếu `T` không có `extends` rõ ràng, nó có **upper bound ngầm `Object`**. Khi đọc qua reflection:

```java
java.lang.reflect.TypeVariable<?>[] vars =
        Simple.class.getTypeParameters();

System.out.println(vars[0].getBounds()[0].getTypeName());
System.out.println(vars[1].getBounds()[0].getTypeName());
```

Đầu ra:

```text
java.lang.Object
java.lang.Number
```

Vì vậy, `getBounds()` không trả một mảng rỗng chỉ vì bạn không ghi `extends`.

### Upper bounds khác actual type arguments

Với `N extends Number`:

- **Bound:** `Number`, mô tả giới hạn trên của các type arguments có thể gắn với `N`.
- **Actual type argument:** chẳng hạn `Integer` tại nơi sử dụng `Simple<String, Integer>`.
- **Type variable:** `N`, vẫn được biểu diễn là `TypeVariable` khi đọc khai báo `Simple`.

Reflection không tự biến `getBounds()` thành `Integer.class` chỉ vì có một instance `Simple<String, Integer>` ở đâu đó.

Tương tự, `T extends Number` không có nghĩa `T` luôn bằng `Number`: `Integer`, `Double` và các lớp con phù hợp cũng có thể là type arguments.

## 6. Nhiều giới hạn: `T extends A & B & C`

Java cho phép khai báo type variable với **intersection bounds**:

```java
class Numeric<T extends Number & Comparable<T>> {
    T value;
}
```

`T` phải thỏa cả hai ràng buộc:

1. Là một subtype của `Number`.
2. Có quan hệ triển khai `Comparable<T>` phù hợp.

Reflection:

```java
java.lang.reflect.TypeVariable<?> variable =
        Numeric.class.getTypeParameters()[0];

for (java.lang.reflect.Type bound : variable.getBounds()) {
    System.out.println(bound.getTypeName());
}
```

Đầu ra:

```text
java.lang.Number
java.lang.Comparable<T>
```

`getBounds()` trả **từng bound theo thứ tự**. Không có một `Class` riêng tên `Number & Comparable<T>`. Cấu trúc intersection được lưu như **nhiều phần tử `Type`**, trong đó:

- `Number` thường là `Class`.
- `Comparable<T>` thường là `ParameterizedType` với type argument `T` là một `TypeVariable` tham chiếu chính nó.

### Vị trí class bound và interface bounds

Nếu có class bound thì nó đứng đầu; các interface bounds theo sau và nối bằng `&`. Không thể khai báo nhiều class bounds độc lập như `T extends Number & String`.

Nếu bound đầu tiên là interface, erasure của `T` dựa trên **bound đầu tiên** ấy. Ví dụ:

```java
class Task<T extends Runnable & AutoCloseable> {
    T task;
}
```

Erasure của `T` dùng `Runnable`, không phải tự động `Object` chỉ vì cả hai bounds đều là interface.

**Thứ tự bounds ảnh hưởng erasure** và có thể ảnh hưởng chữ ký bytecode/các ràng buộc tương thích nguồn. Không nên đảo thứ tự bounds chỉ vì trông tương đương về quan hệ subtype mà bỏ qua tác động đến API đã biên dịch.

### Điều kiện từ bound không biến thành type argument

Nếu `T extends Comparable<T>`, `getBounds()[0]` có thể là một `ParameterizedType` biểu diễn `Comparable<T>`. Đừng cast nó thành `Class` và đừng nhầm `T` bên trong với một runtime class cụ thể.

## 7. Type erasure: bound đầu tiên quyết định góc nhìn runtime

Khi generic type bị xóa, Java dùng erasure của **leftmost bound** đối với type variable. Với:

```java
class Envelope<T extends Number & Comparable<T>> {
    T number;
}
```

Bạn có thể quan sát hai lớp thông tin:

```java
java.lang.reflect.Field f =
        Envelope.class.getDeclaredField("number");

System.out.println(f.getType().getTypeName());
System.out.println(f.getGenericType().getTypeName());
```

Đầu ra:

```text
java.lang.Number
T
```

- `Field.getType()` trả `Class` của kiểu erasure: `Number`.
- `Field.getGenericType()` giữ mô tả khai báo bằng `TypeVariable`: `T`.

Đây là ranh giới quan trọng: **giữ được generic signature qua reflection không có nghĩa một instance `Envelope<Integer>` sẽ có một runtime field class riêng là `Integer`**. Runtime class thông thường vẫn dùng erasure `Number`.

Với method:

```java
<T extends CharSequence & Comparable<T>> T echo(T value)
```

`Method.getReturnType()` có thể trả `CharSequence.class`; `Method.getGenericReturnType()` trả `TypeVariable` tên `T`. Tương tự, `getParameterTypes()` dùng erasure, còn `getGenericParameterTypes()` có thể biểu diễn `T`.

**Không được đồng nhất bound với actual type argument:** `CharSequence` là upper bound, không có nghĩa mọi lời gọi `echo` trả chính một object thuộc runtime class `CharSequence` (đây là interface).

## 8. `getAnnotatedBounds()` khác annotation trên chính type parameter

Java hỗ trợ đặt annotation ở hai vị trí có ý nghĩa khác nhau:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface NamedParameter {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NumberBound {}

class Box<@NamedParameter T extends @NumberBound Number> {}
```

`@NamedParameter` đặt **trên khai báo type parameter `T`**. `@NumberBound` đặt **trên type use `Number` làm bound**.

Reflection:

```java
java.lang.reflect.TypeVariable<?> variable =
        Box.class.getTypeParameters()[0];

boolean onParameter =
        variable.isAnnotationPresent(NamedParameter.class);

boolean onFirstBound =
        variable.getAnnotatedBounds()[0]
                .isAnnotationPresent(NumberBound.class);
```

Cả hai là `true` với ví dụ trên.

Phân biệt:

- `TypeVariable.getAnnotations()` và các phương thức từ `AnnotatedElement` nói về annotations của **khai báo type parameter**.
- `getAnnotatedBounds()` trả `AnnotatedType[]` có annotations của **các kiểu đang được dùng làm bounds**.
- `getBounds()` trả `Type[]` không chứa API đọc trực tiếp annotation cho từng vị trí type use.

Để phản chiếu được annotation lúc chạy, cần `RetentionPolicy.RUNTIME` thích hợp. Nếu annotation chỉ tồn tại ở nguồn hoặc class file mà không có runtime retention, không nên kỳ vọng các lời gọi reflection như trên sẽ thấy nó.

### Annotated bound không thay thế bound

Một `AnnotatedType` cung cấp thêm metadata annotation ở vị trí kiểu, nhưng bạn vẫn có thể gọi `getType()` để lấy `Type` nền. Chẳng hạn:

```java
java.lang.reflect.AnnotatedType annotated =
        variable.getAnnotatedBounds()[0];

java.lang.reflect.Type underlying = annotated.getType();
```

`underlying` có thể là `Number.class`. Khi xây schema hoặc framework cần annotation, hãy giữ đồng thời **cấu trúc `Type`** và **annotation ở đúng vị trí**.

## 9. Chương trình Java 17+ hoàn chỉnh: class, method, constructor và bounds

Lưu mã dưới đây vào **`TypeVariableDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;

public class TypeVariableDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_PARAMETER)
    @interface NamedParameter {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface NumberBound {}

    static class Envelope<
            @NamedParameter T extends @NumberBound Number & Comparable<T>,
            E> {
        T number;
        List<T> numbers;
        E other;

        public <U extends CharSequence> Envelope(U label) {}

        // T của echo được khai báo bởi method, không phải Envelope.
        public <T extends CharSequence & Comparable<T>> T echo(T value) {
            return value;
        }
    }

    static class IntegerEnvelope extends Envelope<Integer, String> {
        IntegerEnvelope() {
            super("ok");
        }
    }

    static String bounds(TypeVariable<?> variable) {
        return String.join(
                " & ",
                Arrays.stream(variable.getBounds())
                        .map(Type::getTypeName)
                        .toArray(String[]::new));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        TypeVariable<?> classT =
                Envelope.class.getTypeParameters()[0];
        TypeVariable<?> classE =
                Envelope.class.getTypeParameters()[1];

        // Lookup reflection theo erased parameter type CharSequence.
        Method method = Envelope.class.getDeclaredMethod(
                "echo", CharSequence.class);
        TypeVariable<?> methodT = method.getTypeParameters()[0];

        Constructor<?> ctor = Envelope.class.getDeclaredConstructor(
                CharSequence.class);
        TypeVariable<?> ctorU = ctor.getTypeParameters()[0];

        System.out.println("Class T belongs to Envelope: "
                + classT.getGenericDeclaration().equals(Envelope.class));
        System.out.println("Class T bounds: " + bounds(classT));
        System.out.println("Class T annotation: "
                + classT.isAnnotationPresent(NamedParameter.class));
        System.out.println("First bound annotation: "
                + classT.getAnnotatedBounds()[0]
                        .isAnnotationPresent(NumberBound.class));

        System.out.println("Class E implicit bound: "
                + bounds(classE));

        System.out.println("Method T belongs to echo: "
                + methodT.getGenericDeclaration().equals(method));
        System.out.println("Method T bounds: " + bounds(methodT));
        System.out.println("Same type variable name: "
                + classT.getName().equals(methodT.getName()));
        System.out.println("Same type variable identity: "
                + classT.equals(methodT));

        System.out.println("Constructor U belongs to ctor: "
                + ctorU.getGenericDeclaration().equals(ctor));
        System.out.println("Constructor U bound: " + bounds(ctorU));

        Field field = Envelope.class.getDeclaredField("number");
        System.out.println("Field erased type: "
                + field.getType().getTypeName());
        System.out.println("Field generic type: "
                + field.getGenericType().getTypeName());

        ParameterizedType list = (ParameterizedType)
                Envelope.class.getDeclaredField("numbers")
                        .getGenericType();
        System.out.println("List argument is class T: "
                + list.getActualTypeArguments()[0].equals(classT));

        ParameterizedType parent = (ParameterizedType)
                IntegerEnvelope.class.getGenericSuperclass();
        System.out.println("Subclass argument T: "
                + parent.getActualTypeArguments()[0].getTypeName());
        System.out.println("Subclass argument E: "
                + parent.getActualTypeArguments()[1].getTypeName());

        System.out.println("Method erased return: "
                + method.getReturnType().getTypeName());
        System.out.println("Method generic return: "
                + method.getGenericReturnType().getTypeName());
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 TypeVariableDemo.java
java TypeVariableDemo
```

**Standard output:**

```text
Class T belongs to Envelope: true
Class T bounds: java.lang.Number & java.lang.Comparable<T>
Class T annotation: true
First bound annotation: true
Class E implicit bound: java.lang.Object
Method T belongs to echo: true
Method T bounds: java.lang.CharSequence & java.lang.Comparable<T>
Same type variable name: true
Same type variable identity: false
Constructor U belongs to ctor: true
Constructor U bound: java.lang.CharSequence
Field erased type: java.lang.Number
Field generic type: T
List argument is class T: true
Subclass argument T: java.lang.Integer
Subclass argument E: java.lang.String
Method erased return: java.lang.CharSequence
Method generic return: T
```

Giải thích các nhóm kết quả:

1. **Class-level `T`** thuộc `Envelope.class`, có hai upper bounds `Number` và `Comparable<T>`; bound đầu tiên có annotation riêng.
2. **Class-level `E`** không có `extends` tường minh, nhưng `getBounds()` vẫn phản ánh upper bound ngầm `Object`.
3. **Method-level `T`** thuộc `echo`; nó có cùng tên với class-level `T`, nhưng là biến kiểu **khác khai báo** nên `equals` cho `false`.
4. **Constructor-level `U`** thuộc constructor, có upper bound `CharSequence`. `getDeclaredConstructor(CharSequence.class)` dựa trên erasure của tham số `U`.
5. **Field `T number`** có erased type `Number`, nhưng generic type là `T`. Trường `List<T> numbers` có type argument phản chiếu trỏ đúng tới class-level `T`.
6. **Subclass `IntegerEnvelope`** khai báo rõ `extends Envelope<Integer, String>`, nên `getGenericSuperclass()` cho `ParameterizedType` với hai actual type arguments cụ thể. Điều đó **không thay đổi** `TypeVariable` được khai báo trên `Envelope`.
7. **Return type method `echo`** có erasure `CharSequence`, còn generic return `T` là type variable của chính method.

Chương trình sử dụng các API có sẵn trong Java 17 và không cần thư viện ngoài.

## 10. Khi subclass chọn kiểu cụ thể: không được nhầm `TypeVariable` với actual type argument

Xét:

```java
class Base<T> {}
class Child extends Base<String> {}
```

Có hai nguồn thông tin **khác nhau**:

```java
java.lang.reflect.TypeVariable<?> parameter =
        Base.class.getTypeParameters()[0];

java.lang.reflect.Type actual =
        ((java.lang.reflect.ParameterizedType)
                Child.class.getGenericSuperclass())
                .getActualTypeArguments()[0];
```

- `parameter` là **`T` do `Base` khai báo**. `parameter.getGenericDeclaration()` chỉ về `Base`.
- `actual` là **`String` do `Child` sử dụng khi kế thừa `Base<String>`**. Trong ví dụ này nó là `Class` tương ứng `String.class`.

Nếu framework muốn biết type argument nào đã gắn với `T` trong bối cảnh `Child`, nó phải **ánh xạ biến kiểu khai báo của `Base` sang type argument ở cạnh kế thừa**. `TypeVariable` riêng lẻ không giữ một đáp án `String` duy nhất cho mọi nơi dùng `Base`.

### Nhiều tầng thừa kế cần giải type bindings

```java
class Base<T> {}
class Middle<U> extends Base<java.util.List<U>> {}
class Child extends Middle<String> {}
```

Muốn suy ra type argument của `Base<T>` từ `Child`, một công cụ phải theo chuỗi:

```text
Child
  extends Middle<String>
      U -> String
  Middle<U> extends Base<List<U>>
      T -> List<U>
  => trong ngữ cảnh Child: T -> List<String>
```

Không thể chỉ đọc `Base.class.getTypeParameters()[0].getBounds()` rồi nhận ngay `List<String>`. `getBounds()` chỉ cho ràng buộc trên của `T`, không phải **actual type argument do một subtype lựa chọn**.

Thư viện như ORM, serializer và dependency-injection framework thường cần giải những ánh xạ này để suy luận schema hoặc kiểu property trong ngữ cảnh kế thừa.

## 11. Giới hạn của `TypeVariable` và type erasure

Một số kết luận cần ghi nhớ:

**Không khôi phục type argument từ instance thông thường.**

```java
class Box<T> {}

Box<String> a = new Box<>();
Box<Integer> b = new Box<>();

boolean same = a.getClass() == b.getClass(); // true
```

Cả hai instance có cùng runtime class `Box`. Dù `Box.class.getTypeParameters()` cho biến `T`, nó không thể tự trả lời “instance `a` đã chọn `String` còn instance `b` đã chọn `Integer`”.

**Không có `T.class` hoặc `new T[]` thông thường.**

```java
class Holder<T> {
    void inspect(Object value) {
        // Class<?> type = T.class;        // KHÔNG BIÊN DỊCH
        // boolean ok = value instanceof T; // KHÔNG BIÊN DỊCH
        // T[] items = new T[3];          // KHÔNG BIÊN DỊCH
    }
}
```

Đây là giới hạn của non-reifiable type variables, không được giải quyết bằng cách phản chiếu `T` thành `TypeVariable`.

**Bound chỉ cho một giới hạn trên.** Với `T extends Number`, việc một object là `Number` không chứng minh nó là một subtype cụ thể `T` mà caller kỳ vọng. Một cast theo erasure có thể thành công với `Double` trong khi caller đang mong `Integer`, khiến lỗi lộ ra sau đó.

**Generic signature là metadata khai báo.** Reflection giữ được `T` hoặc `Comparable<T>` ở khai báo, nhưng không duyệt dữ liệu và không xác thực mọi phần tử của collection generic ở runtime.

Nếu cần kiểm tra một class cụ thể được caller cung cấp, có thể nhận `Class<T>` token:

```java
static <T> boolean accepts(Class<T> expected, Object value) {
    return expected.isInstance(value);
}
```

Token giúp kiểm tra một runtime class cụ thể, nhưng không mang đầy đủ nested generic type arguments kiểu `Map<String, List<Integer>>` theo cơ chế `Class` đơn lẻ.

## 12. `TypeVariable` so với `WildcardType`: hai ý nghĩa khác nhau

Dễ nhầm `T extends Number` với `? extends Number` vì cả hai có chữ `extends`.

```java
class Example<T extends Number> {
    T value;
    java.util.List<? extends Number> readings;
}
```

Chúng khác nhau:

- **`T extends Number`** là một **type parameter declaration**, đặt tên `T` để nhiều vị trí trong cùng generic declaration có thể liên hệ tới nhau. Reflection biểu diễn `T` bằng `TypeVariable`.
- **`? extends Number`** là **wildcard type argument** ở vị trí sử dụng một kiểu tham số hóa. Reflection biểu diễn wildcard đó bằng `WildcardType`.

Trường `value` có `getGenericType()` là `TypeVariable`. Trường `readings` có `getGenericType()` là `ParameterizedType` của `List<? extends Number>`, và phần tử `getActualTypeArguments()[0]` mới là `WildcardType`.

| Câu hỏi | `TypeVariable` | `WildcardType` |
| --- | --- | --- |
| Có tên do programmer khai báo? | Có, như `T`, `U` | Không có tên type parameter |
| Có `getGenericDeclaration()`? | Có | Không |
| Có `getBounds()`? | Có, upper bounds | Dùng `getUpperBounds()` và `getLowerBounds()` |
| Có thể kết nối nhiều vị trí bằng cùng tên/khai báo? | Có, cùng một type variable | Wildcard là đối số kiểu tại vị trí sử dụng |
| Ví dụ | `<T extends Number>` | `List<? extends Number>` |

Không dùng `((TypeVariable<?>) type)` trên bất cứ thứ gì có `extends`. Phải kiểm tra dạng `Type` thực tế.

## 13. Không phải `Type[]` nào từ reflection cũng chứa `Class`

Mã sai phổ biến:

```java
java.lang.reflect.TypeVariable<?> t =
        SomeClass.class.getTypeParameters()[0];

for (java.lang.reflect.Type bound : t.getBounds()) {
    // Class<?> boundClass = (Class<?>) bound; // KHÔNG AN TOÀN
}
```

Với `T extends Number & Comparable<T>`, bound `Number` là `Class`, nhưng `Comparable<T>` là `ParameterizedType`.

Nếu chỉ muốn in tên:

```java
for (java.lang.reflect.Type bound : t.getBounds()) {
    System.out.println(bound.getTypeName());
}
```

Nếu cần phân tích cấu trúc, nhánh theo từng dạng:

```java
static void inspectBound(java.lang.reflect.Type bound) {
    if (bound instanceof Class<?> c) {
        System.out.println("Class bound: " + c.getName());
    } else if (bound instanceof java.lang.reflect.ParameterizedType p) {
        System.out.println("Parameterized bound: "
                + p.getRawType().getTypeName());
    } else if (bound instanceof java.lang.reflect.TypeVariable<?> v) {
        System.out.println("Variable bound: " + v.getName());
    } else {
        System.out.println("Other bound: " + bound.getTypeName());
    }
}
```

Khi gặp cấu trúc đệ quy như `T extends Comparable<T>`, một trình duyệt type graph cần **phát hiện vòng lặp**: nếu cứ theo type argument `T` rồi đọc `getBounds()` của `T` mà không ghi nhận node đã thăm, thuật toán có thể lặp mãi. Dùng tập node/declaration đã thăm theo semantics `TypeVariable.equals`, không dựa vào tên `"T"` đơn thuần.

## 14. Cẩn trọng khi xây framework xử lý generic type variables

Một schema resolver hoặc serializer dùng reflection thường phải giải bài toán lớn hơn việc in tên `T`:

1. **Đọc khai báo:** lấy `TypeVariable` từ `Class.getTypeParameters()`, `Method.getTypeParameters()` hoặc `Constructor.getTypeParameters()`.
2. **Duy trì scope:** xác định `getGenericDeclaration()` cho từng biến kiểu. Hai biến tên `T` ở hai declarations không thể tự trộn vào một.
3. **Đọc bounds như cấu trúc `Type`:** không mặc định tất cả bounds là `Class`; chúng có thể có parameterized arguments.
4. **Resolve qua inheritance hoặc method context:** lấy actual type arguments từ `ParameterizedType` của superclass/interface/owner khi có, rồi áp dụng các ánh xạ `TypeVariable -> Type`.
5. **Giữ annotations:** nếu schema cần `@TYPE_PARAMETER` và `@TYPE_USE` annotations, đọc đúng API và vị trí.
6. **Phát hiện vòng lặp:** ví dụ `Comparable<T>` tham chiếu lại chính `T`.
7. **Xử lý metadata không sẵn có:** `Type` được phản chiếu có thể chỉ còn type variable hoặc raw type; không tự bịa type argument cụ thể cho object runtime.
8. **Tách khai báo khỏi dữ liệu:** một field khai báo `List<String>` không chứng minh collection hiện tại chứa toàn `String` nếu hệ thống có raw/unchecked operations.

Các lời gọi reflection chuyên sâu có thể ném những exception như `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` khi phải phân tích type metadata không giải được/hỏng. Code framework nên có chiến lược xử lý lỗi, không mặc định chữ ký generic phản chiếu từ mọi class ngoài luôn hoàn hảo.

## 15. Các lỗi thường gặp

**Lỗi 1 — “`TypeVariable` chính là runtime class đã chọn cho `T`.”** Sai. Nó mô tả biến kiểu ở nơi khai báo, không mang riêng type argument của mọi instance.

**Lỗi 2 — “`getBounds()` trả actual type arguments.”** Sai. `Number` là upper bound, không phải `Integer` do caller đã chọn.

**Lỗi 3 — “Không ghi `extends` thì `getBounds()` rỗng.”** Sai. Upper bound ngầm thông thường là `Object`.

**Lỗi 4 — “Hai type variables tên `T` luôn bằng nhau.”** Sai. Class-level `T` và method-level `T` có generic declarations khác nhau.

**Lỗi 5 — “`getGenericDeclaration()` luôn trả `Class`.”** Sai. Method và constructor cũng có thể khai báo type parameters.

**Lỗi 6 — “Cứ dùng `==` trên `Method` trả bởi reflection là đủ.”** Không nên. So sánh declaration wrappers bằng `.equals()` khi cần đối chiếu logic.

**Lỗi 7 — “Bounds lúc nào cũng là `Class`.”** Sai. `Comparable<T>` là parameterized bound, thường được mô tả qua `ParameterizedType`.

**Lỗi 8 — “Erasure của `T` luôn là `Object`.”** Sai. Nó theo erasure của bound đầu tiên; `T extends Number` có erasure `Number`.

**Lỗi 9 — “`T extends Number & Comparable<T>` tạo một runtime class giao hai interface.”** Sai. Reflection giữ hai bounds, không sinh runtime class mang tên intersection.

**Lỗi 10 — “`getAnnotatedBounds()` và `TypeVariable.getAnnotations()` xem cùng vị trí.”** Sai. Một cái đọc type-use annotations ở bounds, cái kia đọc annotations trên chính type parameter declaration.

**Lỗi 11 — “Có `TypeVariable` thì dùng `T.class` hoặc `new T[]` được.”** Sai. `T` vẫn là non-reifiable type variable theo ngôn ngữ Java.

**Lỗi 12 — “`T extends Comparable<T>` có thể đệ quy duyệt vô hạn mà không cần visited set.”** Sai. Bounds có thể trỏ trở lại type variable ban đầu; cần guard khi duyệt type graph.

## 16. Bài tập tự kiểm tra

**Câu 1.** Trong `class Box<T extends Number>`, ai là generic declaration của `T`?

Chính **`Box.class`**. `getGenericDeclaration()` trả declaration ở class, không phải một `Box<Integer>` instance.

**Câu 2.** Với `<T> T identity(T x)`, nơi khai báo `T` là gì?

Đối tượng **`Method`** của `identity`. `getBounds()` có upper bound ngầm `Object` nếu không ghi `extends`.

**Câu 3.** Constructor có thể có type parameter riêng không?

Có. Ví dụ `<U extends CharSequence> Box(U text)`; phản chiếu bằng `Constructor.getTypeParameters()`.

**Câu 4.** `T extends Number & Comparable<T>` có bao nhiêu upper bounds?

Hai: `Number` và `Comparable<T>`, theo thứ tự; erasure dùng bound đầu tiên `Number`.

**Câu 5.** `T` của class và `T` của method cùng tên có phải cùng type variable?

Không. Cần xét `getGenericDeclaration()` và semantics `TypeVariable.equals`, không chỉ `getName()`.

**Câu 6.** Vì sao `Field.getType()` của field `T value` trong `Box<T extends Number>` là `Number.class`?

Vì `getType()` cung cấp góc nhìn erasure/runtime của field, và erasure của `T` theo upper bound đầu tiên là `Number`. `getGenericType()` vẫn có thể trả `TypeVariable` `T`.

**Câu 7.** `getBounds()` và `getAnnotatedBounds()` khác nhau thế nào?

`getBounds()` trả cấu trúc `Type[]`; `getAnnotatedBounds()` trả `AnnotatedType[]` để xem type-use annotations ở các bounds.

**Câu 8.** Nếu `class Child extends Base<String>`, `Base.class.getTypeParameters()` có trả `String` không?

Không. Nó trả biến kiểu do `Base` khai báo. `Child.class.getGenericSuperclass()` mới mô tả việc `Child` gắn `String` vào generic superclass.

**Câu 9.** Muốn dùng `TypeVariable` làm key khi resolve generic, có nên chỉ dùng tên `"T"`?

Không. Cần giữ identity của declaration và type variable; tên trùng ở nhiều scope không có nghĩa cùng biến kiểu.

**Câu 10.** Vì sao parser Type phải phát hiện vòng lặp khi xử lý `T extends Comparable<T>`?

Vì bound tham chiếu lại chính `T`; nếu liên tục khai triển mà không ghi nhận node đã thăm, traversal có thể không kết thúc.

## 17. Checklist áp dụng nhanh

Khi đọc một `TypeVariable<?> variable`, hãy theo trình tự:

```text
TypeVariable<?> variable
    |
    +-- getName()                    -> Tên hiển thị của type parameter
    |
    +-- getGenericDeclaration()      -> Class / Method / Constructor khai báo
    |
    +-- getBounds()                  -> Danh sách Type upper bounds
    |     +-- Class?
    |     +-- ParameterizedType?     -> Có thể chứa chính T
    |
    +-- getAnnotatedBounds()         -> Annotation ở bound type uses
    |
    +-- getAnnotations()             -> Annotation ở parameter declaration
    |
    +-- Có actual type arguments?    -> Tìm ở generic superclass/interface
          và ánh xạ theo ngữ cảnh, không tự suy ra từ bounds
```

**Kết luận:** `TypeVariable` không đại diện cho một class runtime mới mà đại diện cho **tham số kiểu được khai báo**. Để hiểu nó chính xác, phải xét **nơi khai báo** qua `getGenericDeclaration()`, **tên** qua `getName()`, **upper bounds** qua `getBounds()`, và **type-use annotations** qua `getAnnotatedBounds()`. Hai biến cùng tên vẫn khác nhau nếu được khai báo ở hai scope. Bounds ràng buộc các type arguments hợp lệ và ảnh hưởng erasure, nhưng không thay thế actual type arguments do class/method/constructor ở một ngữ cảnh cụ thể sử dụng. Đây là nền tảng quan trọng để xử lý reflection, serialization, schema resolution và Java Generics một cách đáng tin.