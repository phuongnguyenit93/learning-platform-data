# ParameterizedType: raw type, owner type và actual type arguments trong Java Generics

## 1. Mục tiêu học tập

Java Generics cho phép viết những kiểu như `List<String>`, `Map<String, List<Integer>>` hoặc `Outer<String>.Inner<Integer>`. Sau *type erasure*, JVM không tạo riêng một class cho từng cách tham số hóa. Tuy nhiên, **thông tin generic được khai báo trên field, method, superclass, interface hoặc một anonymous subclass vẫn có thể được lưu trong class file** và được API reflection đọc lại.

`java.lang.reflect.ParameterizedType` là interface biểu diễn **một kiểu tham số hóa** trong thế giới reflection. Ba phương thức quan trọng nhất là:

- `getRawType()`: kiểu được khai báo làm nền cho việc tham số hóa, ví dụ `List` trong `List<String>`.
- `getOwnerType()`: kiểu bao ngoài mà một kiểu thành viên (member type) thuộc về, nếu có; đặc biệt quan trọng với nested/inner classes.
- `getActualTypeArguments()`: danh sách các đối số kiểu trực tiếp, ví dụ `String` trong `List<String>` hoặc `String` và `List<Integer>` trong `Map<String, List<Integer>>`.

Sau bài này, bạn sẽ biết cách lấy `ParameterizedType` từ các API phản chiếu, hiểu **giá trị `null` của owner**, phân biệt owner có generic với nested class static, đọc đệ quy các đối số kiểu, nhận diện `Class`, `TypeVariable`, `WildcardType`, `GenericArrayType`, và tránh nhầm **metadata khai báo** với **kiểu dữ liệu thực được kiểm tra lúc chạy**.

## 2. `Type` và `ParameterizedType` nằm ở đâu trong reflection?

Một số API reflection hữu ích:

```java
Field field = SomeClass.class.getDeclaredField("names");
Type declared = field.getGenericType();

Type superclass = SomeSubclass.class.getGenericSuperclass();
Type[] interfaces = SomeImplementation.class.getGenericInterfaces();
```

Đây là minh họa cách gọi API; các lớp và field tương ứng phải được định nghĩa nếu chạy độc lập. Chương trình hoàn chỉnh ở phần 8 sẽ cung cấp ví dụ thực tế.

Các kiểu reflective chính:

| API/kiểu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Type` | Interface cha chung của các dạng mô tả kiểu reflection. | Kết quả `Field.getGenericType()`. |
| `Class<?>` | Kiểu class, interface, primitive hoặc array reifiable có Class object tương ứng. | `String.class`, `List.class`, `String[].class`. |
| `ParameterizedType` | Một cách sử dụng kiểu có đối số generic hoặc kiểu thành viên với owner tham số hóa. | `List<String>`, `Outer<String>.Inner<Integer>`. |
| `TypeVariable<?>` | Biến kiểu được khai báo trên class, interface hoặc method. | `T` trong `class Box<T>`. |
| `WildcardType` | Wildcard cùng upper/lower bounds. | `? extends Number`, `? super Integer`. |
| `GenericArrayType` | Mảng mà component type không reifiable theo mô hình generic reflection. | `T[]`, `List<T>[]`. |

Một `ParameterizedType` **không phải** một `Class`. Nó mô tả cấu trúc kiểu generic xuất hiện trong khai báo. Khi cần gọi `Class.isInstance` hoặc `Class.cast`, bạn đang kiểm tra kiểu runtime có thể biểu diễn bằng `Class`, chứ không tự động kiểm tra tất cả đối số generic.

Ví dụ, `List.class` có thể nhận diện một đối tượng triển khai List; nó không phân biệt `List<String>` và `List<Integer>`. Ngược lại, một `ParameterizedType` đọc từ metadata có thể cho biết một field được khai báo là `List<String>`; đó là thông tin **về field**, không phải một cơ chế JVM quét mọi phần tử của danh sách tại runtime.

### Lấy kiểu generic và kiểu raw của field

Giả sử:

```java
class Profile {
    List<String> names;
}
```

Đặt các khai báo trong cùng một file có import `java.util.List` và `java.lang.reflect.Field`:

```java
Field field = Profile.class.getDeclaredField("names");

Class<?> rawFieldType = field.getType();
Type genericFieldType = field.getGenericType();
```

`field.getType()` trả về `Class` biểu diễn `java.util.List`. `field.getGenericType()` thường trả về một `ParameterizedType` biểu diễn `java.util.List<java.lang.String>`.

Muốn truy cập ba thành phần, hãy kiểm tra kiểu trước:

```java
if (genericFieldType instanceof ParameterizedType type) {
    Type raw = type.getRawType();
    Type owner = type.getOwnerType();
    Type[] arguments = type.getActualTypeArguments();
}
```

Kết quả `Type` không phải lúc nào cũng là `ParameterizedType`. Ví dụ field khai báo `String name` thường cho `Class<String>`; field khai báo raw `List names` thường cho `Class<List>`. Nếu ép vô điều kiện `(ParameterizedType) field.getGenericType()`, code có thể gặp `ClassCastException`.

## 3. `getRawType()`: phần nền đã bỏ đối số kiểu

Với `List<String>`, thành phần raw type là `java.util.List`:

```text
List<String>
┌───┘└────┘
 raw   actual type argument
```

Ví dụ:

```java
Type declared = field.getGenericType();

if (declared instanceof ParameterizedType p) {
    System.out.println(p.getRawType().getTypeName());
}
```

Kết quả với field `List<String>`:

```text
java.util.List
```

Với `Map<String, List<Integer>>`:

- Raw type ngoài cùng: `java.util.Map`.
- Actual type argument thứ nhất: `java.lang.String`.
- Actual type argument thứ hai: một **ParameterizedType khác** đại diện `List<Integer>`.
- Raw type của argument thứ hai: `java.util.List`.
- Actual type argument bên trong: `java.lang.Integer`.

**Đừng chỉ gọi `getRawType()` rồi kết luận đã hiểu đầy đủ kiểu.** Nó cố ý không chứa các type arguments, wildcard bounds hoặc thông tin owner đã tham số hóa.

### `getRawType()` trả `Type`, không khai báo trả `Class<?>`

Chữ ký phương thức là:

```java
Type getRawType();
```

Trong những phản chiếu phổ biến trên class/interface Java, giá trị trả về thường là một `Class<?>`. Tuy nhiên, API khai báo kiểu tổng quát `Type`, nên code thư viện đọc reflection nên kiểm tra trước khi downcast:

```java
Type raw = parameterized.getRawType();
if (raw instanceof Class<?> rawClass) {
    System.out.println(rawClass.getName());
}
```

`parameterized` ở đây là biến `ParameterizedType` đã lấy được trong ngữ cảnh. Nếu mục tiêu chỉ là in hoặc so sánh mô tả, `raw.getTypeName()` có thể đủ, không nhất thiết phải cast.

### Raw type khác với raw type usage trong mã nguồn

Cùng cụm từ “raw type” được dùng ở hai ngữ cảnh:

- `getRawType()` mô tả phần class/interface đứng sau một `ParameterizedType`.
- Một **raw usage** trong mã nguồn là khai báo thiếu đối số kiểu, ví dụ `List raw;`.

Field khai báo raw `List` có thể khiến `getGenericType()` trả trực tiếp `Class<List>`, chứ không phải `ParameterizedType` với danh sách argument rỗng. Vì vậy không nên dùng “có `Class<List>`” và “có `ParameterizedType<List<String>>`” như hai cấu trúc reflective tương đương.

## 4. `getActualTypeArguments()`: danh sách đối số kiểu trực tiếp

Với kiểu đơn:

```java
List<String>
```

`getActualTypeArguments()` trả một mảng `Type[]` có **1 phần tử**, mô tả `String`.

Với:

```java
Map<String, List<Integer>>
```

nó trả **2 phần tử**:

```text
Map<String, List<Integer>>
 ├── arg[0]: Class<String>
 └── arg[1]: ParameterizedType(List<Integer>)
                     ├── raw: Class<List>
                     └── arg[0]: Class<Integer>
```

Dù kiểu lồng nhau chứa một Integer, điều đó **không** có nghĩa `Map` có ba actual type arguments. `Map<K,V>` có đúng hai argument trực tiếp; muốn xem Integer, bạn phải đi sâu vào argument thứ hai.

### Cách đọc đệ quy

```java
static void inspectArguments(ParameterizedType type) {
    Type[] arguments = type.getActualTypeArguments();
    for (int index = 0; index < arguments.length; index++) {
        Type argument = arguments[index];
        System.out.println("arg[" + index + "]=" + argument.getTypeName());

        if (argument instanceof ParameterizedType nested) {
            inspectArguments(nested);
        }
    }
}
```

Đây là helper minh họa cần import `Type`, `ParameterizedType`. Trong ứng dụng thực, một trình duyệt Type tổng quát còn phải xử lý `Class`, `WildcardType`, `TypeVariable`, `GenericArrayType` và có thể tránh duyệt vô hạn khi phân tích cấu trúc recursive bounds.

**Điểm quan trọng:** `getActualTypeArguments()` trả `Type[]` chứ không phải `Class<?>[]`, vì argument có thể là nhiều dạng khác nhau.

| Argument được khai báo | Loại reflective thường gặp |
| --- | --- |
| `String` | `Class<?>`. |
| `List<Integer>` | `ParameterizedType`. |
| `T` | `TypeVariable<?>`. |
| `? extends Number` | `WildcardType`. |
| `T[]` khi T là type variable | `GenericArrayType`. |
| `String[]` | `Class<?>`, vì mảng String reifiable. |

Không nên ép mọi phần tử `getActualTypeArguments()` thành `Class`. Việc đó có thể chạy với `List<String>` nhưng ném `ClassCastException` khi gặp `List<T>` hoặc `List<? extends Number>`.

## 5. `getOwnerType()`: kiểu bao ngoài của member type

`Owner type` thường là phần dễ nhầm nhất. Nó **không** đơn giản là superclass, không phải raw type, và không phải một argument nằm chung mảng với type arguments trực tiếp của member class.

Với kiểu top-level `List<String>`, `getOwnerType()` là `null`, bởi `List` không phải member class bên trong một kiểu bao ngoài.

Xét:

```java
class Outer<T> {
    class Inner<U> {}
    class Plain {}
    static class Nested<V> {}
}
```

Ba kiểu thành viên có quan hệ với Outer khác nhau. Khi nhìn khai báo:

```java
Outer<String>.Inner<Integer>
```

ta có hai “tầng” tham số hóa:

- **Inner<U>** có U = Integer.
- **Outer<T>** là owner được tham số hóa với T = String.

Nếu phản chiếu kiểu trên, `ParameterizedType` của `Inner<Integer>` có:

```text
getRawType()            -> Outer$Inner
getOwnerType()          -> ParameterizedType(Outer<String>)
getActualTypeArguments()-> [Integer]
```

Thông tin String thuộc `getOwnerType()`, còn Integer thuộc `getActualTypeArguments()` của Inner. Nếu bạn chỉ duyệt arguments của Inner rồi bỏ owner, bạn **sẽ bỏ sót T = String**.

### 5.1. Inner class không static với owner generic

Khai báo field:

```java
Outer<String>.Inner<Integer> member;
```

Nếu là field trên một lớp và `getGenericType()` trả `ParameterizedType p`:

```java
Type owner = p.getOwnerType();
Type raw = p.getRawType();
Type[] ownArguments = p.getActualTypeArguments();
```

Kết quả điển hình của chương trình phần 8 là:

```text
inner.raw=ParameterizedTypeDemo$Outer$Inner
inner.ownerParameterized=true
inner.ownerRaw=ParameterizedTypeDemo$Outer
inner.ownerArg=java.lang.String
inner.arg=java.lang.Integer
```

Dấu `$` trong tên class binary của các nested types là cách thể hiện tên lớp mà JVM sử dụng trong ví dụ. Khi trình bày cho người đọc, bạn có thể dùng tên nguồn `Outer.Inner`, nhưng khi đối chiếu `Class.getName()`/`Type.getTypeName()`, binary name có thể chứa `$`.

### 5.2. Inner class không tự khai báo tham số kiểu

Đây là tình huống quan trọng:

```java
Outer<String>.Plain plain;
```

`Plain` **không** khai báo `<U>`, nhưng **owner** của nó vẫn là `Outer<String>`. Reflection có thể trả một `ParameterizedType` của member với:

```text
getActualTypeArguments().length -> 0
getOwnerType()                   -> Outer<String>
```

Điều đó chứng minh **một `ParameterizedType` không bắt buộc phải có ít nhất một argument trực tiếp**. Metadata tham số hóa có thể nằm ở owner. Bạn không được suy ra “actual arguments rỗng ⇒ kiểu này chắc chắn không liên quan generic”.

Trong ví dụ được kiểm chứng trên Java 17, `plain.ownArgs=0` và `plain.ownerArg=java.lang.String`.

### 5.3. Static nested class

Khai báo:

```java
Outer.Nested<Long> nested;
```

`Nested<V>` là `static`, do đó không mang type parameter T từ một instance `Outer<T>` cụ thể. Trong kết quả Java reflection đã kiểm chứng:

```text
static.ownerIsClass=true
static.owner=ParameterizedTypeDemo$Outer
static.arg=java.lang.Long
```

`getOwnerType()` lúc này là một `Class` của Outer, **không** phải `ParameterizedType(Outer<String>)`. Argument Long thuộc Nested, không phải Outer.

Đừng kết luận owner luôn là `ParameterizedType` chỉ vì member có generic. Owner có thể là `Class<?>`, `ParameterizedType` hoặc `null`, tùy khai báo. Với member class lồng nhiều tầng, chính owner cũng có thể có owner khác; cần duyệt theo cấu trúc thay vì ghép chuỗi tùy tiện.

### 5.4. Owner không phải superclass

`Outer<String>.Inner<Integer>` có owner `Outer<String>` vì Inner được khai báo là thành viên của Outer. Nó không có nghĩa Outer là superclass trực tiếp của Inner. Quan hệ kế thừa được đọc bằng `getGenericSuperclass()`; quan hệ khai báo member/owner được đọc bằng `getOwnerType()`.

Đây là hai chiều metadata độc lập:

```text
Owner:  Outer<String> ── chứa khai báo ──> Inner<Integer>

Extends: Child ── kế thừa ──> Parent<Something>
```

Khi viết công cụ dựng sơ đồ Type, không nên vẽ cạnh “extends” chỉ dựa trên `getOwnerType()`.

## 6. Những cách lấy `ParameterizedType` đúng ngữ cảnh

Không chỉ field mới có generic type metadata. Tùy nơi Java khai báo kiểu, bạn có thể đọc bằng các API sau:

| Nguồn khai báo | Reflection API | Ví dụ |
| --- | --- | --- |
| Field | `Field.getGenericType()` | `List<String> names`. |
| Superclass của một lớp | `Class.getGenericSuperclass()` | `class Names extends ArrayList<String>`. |
| Interface mà class triển khai trực tiếp | `Class.getGenericInterfaces()` | `implements Supplier<List<String>>`. |
| Kiểu trả về của method | `Method.getGenericReturnType()` | `List<String> fetch()`. |
| Kiểu các tham số method | `Method.getGenericParameterTypes()` | `consume(List<String> values)`. |
| Kiểu exception được khai báo bởi method | `Method.getGenericExceptionTypes()` | Các trường hợp throws dùng type variable hợp lệ. |
| Generic superclass của anonymous TypeRef | `getClass().getGenericSuperclass()` | `new TypeRef<List<String>>() {}`. |

**Không phải mọi giá trị trả về đều là ParameterizedType.** Một method trả `String` có `getGenericReturnType()` thường là `Class<String>`. Một method trả T có thể có `TypeVariable<?>`. Hãy sử dụng `instanceof` để xử lý đúng các dạng.

### 6.1. Generic superclass

Ví dụ:

```java
class StringList extends ArrayList<String> {
    private static final long serialVersionUID = 1L;
}
```

`StringList.class.getGenericSuperclass()` có thể là một `ParameterizedType` với raw type `ArrayList` và actual argument `String`.

`Class.getSuperclass()` chỉ trả raw class của cha là `ArrayList.class`; `getGenericSuperclass()` giữ mô tả cách subclass khai báo tham số hóa cha. Chương trình phần 8 in:

```text
super.raw=java.util.ArrayList
super.arg=java.lang.String
```

### 6.2. Generic interface

Ví dụ:

```java
class StringSource implements Supplier<List<String>> {
    @Override
    public List<String> get() {
        return List.of("hi");
    }
}
```

`StringSource.class.getGenericInterfaces()[0]` mô tả `Supplier<List<String>>` và là `ParameterizedType`. Actual argument trực tiếp của Supplier là **một ParameterizedType khác**, `List<String>`.

Trong chương trình:

```text
interface.raw=java.util.function.Supplier
interface.arg=java.util.List<java.lang.String>
```

`getGenericInterfaces()` trả các interface được khai báo **trực tiếp** trên class/interface được xét. Nó không tự trả mọi interface từ toàn bộ chuỗi kế thừa hay giải quyết mọi type variable của các ancestor thành kiểu cụ thể. Nếu cần dựng một *type resolver* hoàn chỉnh, phải lần qua cây kế thừa và thực hiện thay thế type variables theo từng quan hệ.

### 6.3. Metadata generic không phải “kiểu đầy đủ” của một instance

Với:

```java
class Box<T> {
    List<T> items;
}
```

`Box.class.getDeclaredField("items").getGenericType()` mô tả `List<T>`, trong đó T là `TypeVariable`.

Nếu khởi tạo `new Box<String>()`, bạn không thể đơn giản gọi `getClass()` trên instance rồi mong JVM trả về một class `Box<String>` riêng. Runtime class vẫn là `Box.class`, và metadata trên field gốc vẫn nói `List<T>`. Khi generic được chuyên biệt hóa ở một subclass, reflection có thể thấy cấu trúc chuyên biệt hóa trên generic superclass của subclass; nhưng việc kết nối nhiều tầng và thay T đòi hỏi thêm thuật toán.

## 7. Những dạng `Type` xuất hiện trong actual arguments

### 7.1. `Class<?>`

Trong `List<String>`, argument là `Class<String>`. Bạn có thể kiểm tra:

```java
Type arg = p.getActualTypeArguments()[0];
if (arg instanceof Class<?> c) {
    System.out.println(c.getName());
}
```

Ở đây `p` là ParameterizedType của `List<String>` đã có. Kết quả là `java.lang.String`.

### 7.2. `ParameterizedType` lồng nhau

Trong `Map<String, List<Integer>>`, argument thứ hai là `ParameterizedType` khác:

```java
Type valueArg = mapType.getActualTypeArguments()[1];
if (valueArg instanceof ParameterizedType nestedList) {
    Type listRaw = nestedList.getRawType();
    Type element = nestedList.getActualTypeArguments()[0];
}
```

`mapType` là ParameterizedType mô tả Map ở lớp ngoài. `listRaw` biểu diễn List, `element` biểu diễn Integer. Không cast `valueArg` trực tiếp thành `Class<List<?>>`.

### 7.3. `WildcardType`

Với:

```java
List<? extends Number> producers;
List<? super Integer> consumers;
```

`getActualTypeArguments()[0]` của mỗi khai báo là `WildcardType`.

- `? extends Number` có upper bound Number.
- `? super Integer` có lower bound Integer và upper bound mặc định Object.

Reflection cung cấp `getUpperBounds()` và `getLowerBounds()` trả `Type[]`. Một wildcard không giới hạn `?` có upper bound Object và không có lower bound tường minh.

Không nên suy luận wildcard bound chỉ từ chuỗi `toString()`; dùng đúng API bounds để phân tích có cấu trúc.

### 7.4. `TypeVariable<?>`

Với:

```java
class Samples<N extends Number> {
    List<N> genericList;
}
```

Argument của `List<N>` là một `TypeVariable` đại diện N. Bạn có thể đọc:

- `getName()` → `N`.
- `getBounds()` → Number (trong ví dụ).
- `getGenericDeclaration()` → nơi N được khai báo, là class hoặc method/constructor.

Không được tự thay N thành Object nếu nó có bound Number. Đồng thời, việc nhìn N có bound Number **không** chứng minh N chính là Number trong mọi cách tham số hóa instance.

### 7.5. `GenericArrayType`

Với:

```java
class Samples<N extends Number> {
    N[] genericArray;
    List<N>[] listArray;
}
```

Các khai báo field đều hợp lệ dù bạn **không thể** trực tiếp khởi tạo `new N[3]` hay `new List<N>[3]`.

- `N[]` có thể được reflection biểu diễn bằng `GenericArrayType` với component type N (`TypeVariable`).
- `List<N>[]` có thể là `GenericArrayType` có component là `ParameterizedType` `List<N>`.
- `String[]`, ngược lại, có runtime `Class<String[]>` vì thành phần String reifiable.

Sự khác nhau này giúp tránh việc ép mọi Type mô tả mảng thành `Class<?>`.

## 8. Chương trình Java 17 hoàn chỉnh

Chương trình dưới đây tự khai báo các kiểu cần phản chiếu và in ra chính xác raw type, owner type, actual arguments, wildcard bounds, type variable và generic array types. Nó cũng cho ví dụ lấy metadata từ superclass/interface và một TypeRef.

**Tệp `ParameterizedTypeDemo.java`:**

```java
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;

public class ParameterizedTypeDemo {
    static class Outer<T> {
        class Inner<U> {}
        class Plain {}
        static class Nested<V> {}
    }

    static class Samples<N extends Number> {
        List<String> names;
        Map<String, List<Integer>> nested;
        List<? extends Number> producers;
        List<? super Integer> consumers;
        List<N> genericList;
        N[] genericArray;
        List<N>[] listArray;
        Outer<String>.Inner<Integer> inner;
        Outer<String>.Plain plain;
        Outer.Nested<Long> staticNested;
    }

    static class StringList extends ArrayList<String> {
        private static final long serialVersionUID = 1L;
    }

    static class StringSource implements Supplier<List<String>> {
        @Override public List<String> get() {
            return List.of("hi");
        }
    }

    abstract static class TypeRef<T> {
        final Type getType() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType p)) {
                throw new IllegalStateException("Missing type metadata");
            }
            return p.getActualTypeArguments()[0];
        }
    }

    static Type fieldType(String name) throws ReflectiveOperationException {
        return Samples.class.getDeclaredField(name).getGenericType();
    }

    static ParameterizedType requireParameterized(Type type) {
        if (!(type instanceof ParameterizedType p)) {
            throw new IllegalArgumentException("Not parameterized: " + type);
        }
        return p;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Field field = Samples.class.getDeclaredField("names");
        ParameterizedType names = requireParameterized(field.getGenericType());
        System.out.println("field.rawClass=" + field.getType().getTypeName());
        System.out.println("field.generic=" + field.getGenericType().getTypeName());
        System.out.println("list.raw=" + names.getRawType().getTypeName());
        System.out.println("list.owner=" + names.getOwnerType());
        System.out.println("list.arg=" + names.getActualTypeArguments()[0].getTypeName());

        ParameterizedType nested = requireParameterized(fieldType("nested"));
        Type nestedValue = nested.getActualTypeArguments()[1];
        System.out.println("map.arity=" + nested.getActualTypeArguments().length);
        System.out.println("map.valueParameterized=" + (nestedValue instanceof ParameterizedType));
        System.out.println("map.valueArg=" + requireParameterized(nestedValue)
                .getActualTypeArguments()[0].getTypeName());

        ParameterizedType inner = requireParameterized(fieldType("inner"));
        ParameterizedType innerOwner = requireParameterized(inner.getOwnerType());
        System.out.println("inner.raw=" + inner.getRawType().getTypeName());
        System.out.println("inner.ownerParameterized=" + (inner.getOwnerType() instanceof ParameterizedType));
        System.out.println("inner.ownerRaw=" + innerOwner.getRawType().getTypeName());
        System.out.println("inner.ownerArg=" + innerOwner.getActualTypeArguments()[0].getTypeName());
        System.out.println("inner.arg=" + inner.getActualTypeArguments()[0].getTypeName());

        ParameterizedType plain = requireParameterized(fieldType("plain"));
        System.out.println("plain.ownArgs=" + plain.getActualTypeArguments().length);
        System.out.println("plain.ownerArg=" + requireParameterized(plain.getOwnerType())
                .getActualTypeArguments()[0].getTypeName());

        ParameterizedType staticNested = requireParameterized(fieldType("staticNested"));
        System.out.println("static.ownerIsClass=" + (staticNested.getOwnerType() instanceof Class<?>));
        System.out.println("static.owner=" + staticNested.getOwnerType().getTypeName());
        System.out.println("static.arg=" + staticNested.getActualTypeArguments()[0].getTypeName());

        WildcardType upper = (WildcardType) requireParameterized(fieldType("producers"))
                .getActualTypeArguments()[0];
        WildcardType lower = (WildcardType) requireParameterized(fieldType("consumers"))
                .getActualTypeArguments()[0];
        System.out.println("wildcard.upper=" + upper.getUpperBounds()[0].getTypeName());
        System.out.println("wildcard.lower=" + lower.getLowerBounds()[0].getTypeName());

        TypeVariable<?> variable = (TypeVariable<?>) requireParameterized(fieldType("genericList"))
                .getActualTypeArguments()[0];
        System.out.println("variable.name=" + variable.getName());
        System.out.println("variable.bound=" + variable.getBounds()[0].getTypeName());

        GenericArrayType genericArray = (GenericArrayType) fieldType("genericArray");
        GenericArrayType listArray = (GenericArrayType) fieldType("listArray");
        System.out.println("array.component=" + genericArray.getGenericComponentType().getTypeName());
        System.out.println("array.listComponentParameterized="
                + (listArray.getGenericComponentType() instanceof ParameterizedType));

        ParameterizedType subclass = requireParameterized(StringList.class.getGenericSuperclass());
        System.out.println("super.raw=" + subclass.getRawType().getTypeName());
        System.out.println("super.arg=" + subclass.getActualTypeArguments()[0].getTypeName());

        ParameterizedType implemented =
                requireParameterized(StringSource.class.getGenericInterfaces()[0]);
        System.out.println("interface.raw=" + implemented.getRawType().getTypeName());
        System.out.println("interface.arg=" + implemented.getActualTypeArguments()[0].getTypeName());

        Type captured = new TypeRef<List<String>>() {}.getType();
        System.out.println("captured=" + captured.getTypeName());
        System.out.println("captured.equalsField=" + captured.equals(names));

        List<?> runtimeList = List.of(1, 2);
        System.out.println("runtime.isList=" + List.class.isInstance(runtimeList));
        System.out.println("runtime.isArrayList=" + (runtimeList instanceof ArrayList<?>));
    }
}
```

**Biên dịch và chạy:**

```bash
javac --release 17 -Xlint:all ParameterizedTypeDemo.java
java ParameterizedTypeDemo
```

**Stdout đã kiểm chứng trên JDK hỗ trợ Java 17:**

```text
field.rawClass=java.util.List
field.generic=java.util.List<java.lang.String>
list.raw=java.util.List
list.owner=null
list.arg=java.lang.String
map.arity=2
map.valueParameterized=true
map.valueArg=java.lang.Integer
inner.raw=ParameterizedTypeDemo$Outer$Inner
inner.ownerParameterized=true
inner.ownerRaw=ParameterizedTypeDemo$Outer
inner.ownerArg=java.lang.String
inner.arg=java.lang.Integer
plain.ownArgs=0
plain.ownerArg=java.lang.String
static.ownerIsClass=true
static.owner=ParameterizedTypeDemo$Outer
static.arg=java.lang.Long
wildcard.upper=java.lang.Number
wildcard.lower=java.lang.Integer
variable.name=N
variable.bound=java.lang.Number
array.component=N
array.listComponentParameterized=true
super.raw=java.util.ArrayList
super.arg=java.lang.String
interface.raw=java.util.function.Supplier
interface.arg=java.util.List<java.lang.String>
captured=java.util.List<java.lang.String>
captured.equalsField=true
runtime.isList=true
runtime.isArrayList=false
```

Khi kiểm tra chương trình bằng `javac --release 17 -Xlint:all` sau khi khai báo `serialVersionUID` cho `StringList`, compiler không phát cảnh báo trong phép thử.

### Đọc kết quả theo ba nhóm chính

**Raw type:** `field.getType()` và `names.getRawType()` cùng biểu diễn `List`. `getGenericType()` biểu diễn cả `List<String>`.

**Owner type:** trường `inner` có owner parameterized `Outer<String>`, trường `plain` có **0** actual arguments riêng nhưng owner vẫn chứa String, còn trường `staticNested` có owner dạng Class Outer.

**Actual arguments:** `names` có String; `nested` có String và List<Integer> ở hai vị trí trực tiếp; các field `producers`/`consumers` có wildcard; `genericList` có TypeVariable N, không tự biến thành Number hoặc Integer; các field mảng generic dùng GenericArrayType.

### Vì sao không in tên lớp implementation của `ParameterizedType`?

Một implementation JDK có thể dùng một lớp nội bộ để hiện thực interface `ParameterizedType`. Tên lớp nội bộ đó không phải hợp đồng public API ổn định. Vì vậy chương trình in các kiểm tra `instanceof ParameterizedType` và dữ liệu semantic từ getter, thay vì phụ thuộc vào `type.getClass().getSimpleName()`.

## 9. TypeRef: giữ mô tả `List<String>` qua anonymous subclass

Trong Java, `List<String>.class` không phải biểu thức hợp lệ và `List.class` không lưu argument String. Một kỹ thuật phổ biến để chuyển mô tả generic cho framework là **type reference** (hay *super type token*).

Mẫu tối giản:

```java
abstract static class TypeRef<T> {
    final Type getType() {
        Type superclass = getClass().getGenericSuperclass();
        if (!(superclass instanceof ParameterizedType type)) {
            throw new IllegalStateException("Missing type metadata");
        }
        return type.getActualTypeArguments()[0];
    }
}

Type captured = new TypeRef<List<String>>() {}.getType();
```

Khối trên là trích đoạn phải đặt trong một lớp (và dòng tạo instance trong method); ví dụ hoàn chỉnh ở phần 8 đã đặt đúng vị trí.

Tại sao hoạt động?

1. Biểu thức `new TypeRef<List<String>>() {}` tạo một anonymous subclass.
2. Generic superclass của subclass được **khai báo** là `TypeRef<List<String>>`.
3. Class file có thể lưu metadata về cách subclass khai báo generic superclass.
4. `getGenericSuperclass()` đọc `ParameterizedType` của `TypeRef<List<String>>`.
5. `getActualTypeArguments()[0]` lấy mô tả `List<String>` dưới dạng `Type`.

Trong chương trình phần 8, `captured.equalsField=true` vì `TypeRef` và field `names` cùng mô tả cấu trúc `List<String>`. Đây là bằng chứng so sánh **kiểu khai báo** trong reflection, không có nghĩa hai đối tượng List nào đó đang chứa cùng dữ liệu.

### Khi TypeRef không giúp gì?

Nếu nguồn là:

```java
Object input = List.of(42);
```

thì `TypeRef<List<String>>` **không** chứng minh input chứa toàn String. Nó chỉ lưu mô tả kiểu mà caller mong muốn. Một thư viện deserializer có thể dùng mô tả ấy để quyết định cách tạo/chuyển từng phần tử, nhưng **thư viện phải thực thi việc kiểm tra/chuyển đổi**; JVM không tự gắn metadata của TypeRef lên input.

Một tình huống khác: nếu tạo một TypeRef qua tầng generic mà argument vẫn chỉ là biến kiểu `T`, metadata có thể chứa `TypeVariable<T>` thay vì một Class cụ thể. Không nên kỳ vọng reflection luôn thay T thành kiểu runtime thật của giá trị đang có.

## 10. Phân tích `ParameterizedType` an toàn: mẫu thuật toán

Một Type explorer hữu ích cần phân nhánh theo **loại interface của Type**, không dựa vào tên chuỗi hay class nội bộ của implementation.

Pseudocode định hướng:

```java
static void inspect(Type type) {
    if (type instanceof Class<?> clazz) {
        System.out.println("Class: " + clazz.getName());
    } else if (type instanceof ParameterizedType p) {
        System.out.println("Raw: " + p.getRawType().getTypeName());
        Type owner = p.getOwnerType();
        if (owner != null) {
            System.out.println("Owner:");
            inspect(owner);
        }
        for (Type arg : p.getActualTypeArguments()) {
            inspect(arg);
        }
    } else if (type instanceof TypeVariable<?> variable) {
        System.out.println("Variable: " + variable.getName());
        for (Type bound : variable.getBounds()) {
            System.out.println("Bound: " + bound.getTypeName());
        }
    } else if (type instanceof WildcardType wildcard) {
        for (Type upper : wildcard.getUpperBounds()) {
            System.out.println("Upper: " + upper.getTypeName());
        }
        for (Type lower : wildcard.getLowerBounds()) {
            System.out.println("Lower: " + lower.getTypeName());
        }
    } else if (type instanceof GenericArrayType array) {
        System.out.println("Generic array component:");
        inspect(array.getGenericComponentType());
    }
}
```

Đây là phương thức minh họa: phải đặt trong class với import `java.lang.reflect.*` hoặc import riêng các interface. Một Type explorer sản phẩm cần thêm chính sách tránh lặp/vòng đệ quy của type variables có bounds tự tham chiếu, chẳng hạn `E extends Enum<E>`, và giới hạn độ sâu nếu xử lý metadata không đáng tin.

Các lưu ý:

- Truy cập `getOwnerType()` **trước hoặc cùng lúc** với arguments, để không bỏ sót generic của member enclosing type.
- Đừng giả định `getActualTypeArguments()` luôn có ít nhất một phần tử.
- Đừng ép mọi argument thành Class; dùng `instanceof`.
- Nếu owner là `ParameterizedType`, có thể đi tiếp vào owner của owner.
- Nếu một `TypeVariable` có nhiều bounds, `getBounds()` trả các bound; bounds có thể tự chứa type variable, cần phòng vòng lặp khi phân tích toàn bộ graph.
- `getTypeName()` thích hợp để hiển thị, **không** phải định dạng serialization chuẩn để tự viết parser generic bằng `split("<")` hoặc `split(",")`.

## 11. Những bẫy dễ gặp khi dùng reflection generics

| Nhầm lẫn | Hệ quả | Cách hiểu đúng |
| --- | --- | --- |
| “`getRawType()` trả đầy đủ `List<String>`.” | Mất String khi phân tích. | Raw type chỉ là phần class/interface nền; đọc arguments riêng. |
| “`getOwnerType()` luôn null.” | Bỏ sót Outer<String> trong inner class. | Member types có owner; kiểu top-level thường không. |
| “Owner luôn là `Class<?>`.” | Cast hỏng với `Outer<String>.Inner<Integer>`. | Owner có thể là ParameterizedType mang type arguments. |
| “Mọi argument của nested type đều nằm trong một mảng arguments.” | Trộn hoặc mất argument của owner. | Inner own args và owner args nằm ở hai cấp khác nhau. |
| “ParameterizedType phải có ít nhất một argument.” | Bỏ qua `Outer<String>.Plain`. | Thành viên không generic vẫn có thể có owner tham số hóa và 0 own args. |
| “`List<T>` luôn có argument là Class.” | `ClassCastException` khi gặp TypeVariable. | Argument là Type, có thể có nhiều dạng. |
| “`List<? extends Number>` có argument Number.” | Mất thông tin wildcard. | Actual arg là WildcardType với upper bound Number. |
| “Field.getGenericType() luôn là ParameterizedType.” | Cast lỗi với String, raw List hoặc T[]. | Kiểm tra loại Type thực trước. |
| “`TypeRef<List<String>>` xác thực một List runtime.” | Tin dữ liệu không được kiểm tra. | Nó lưu metadata type declaration; cần validator/deserializer riêng. |
| “Tên lớp nội bộ của reflection là API ổn định.” | Code phụ thuộc JDK implementation. | Phụ thuộc các interface Type, Class, ParameterizedType,... |
| “`getOwnerType()` có nghĩa superclass.” | Dựng sai sơ đồ kiểu. | Owner là quan hệ kiểu khai báo member, khác inheritance. |
| “`getGenericSuperclass()` tự thay thế mọi T trong field kế thừa.” | Resolver generic trả kết quả sai. | Phải đi qua type hierarchy và thay type variables đúng ngữ cảnh. |

## 12. Khi nào raw type, owner và actual args quan trọng trong dự án?

### 12.1. JSON deserialization và data binding

Một thư viện nhận mô tả `List<User>` cần biết:

- Container raw: `List`.
- Type argument: `User`.
- Với `Map<String,List<User>>`, phải đi sâu vào argument thứ hai và argument của List.

Một `Class<List>` riêng chỉ nhận diện container, không nói kiểu object trong mỗi phần tử. `ParameterizedType` giúp truyền **mô tả**; framework vẫn phải tạo object và xác thực/chuyển dữ liệu theo logic của nó.

### 12.2. Dependency injection và generic repositories

Một dependency như `Repository<Order>` và `Repository<Customer>` có cùng raw type Repository. Công cụ có thể đọc actual arguments trong khai báo field/constructor để phân biệt hai dependency mong muốn.

Với inner class chứa generic owner, resolver phải xét `getOwnerType()`; nếu chỉ so raw và actual arguments ở lớp trong, thông tin enclosing generic có thể bị bỏ sót.

### 12.3. ORM/serializer/schema generator

Công cụ tạo schema có thể đọc `Field.getGenericType()` để phân biệt `List<String>`, `List<Money>`, `Map<String,Amount>`. Khi gặp `List<T>`, công cụ có thể cần đi qua type hierarchy để xác định T hoặc chấp nhận rằng T chưa biết.

Không nên dùng metadata làm bằng chứng dữ liệu đã hợp lệ. Ví dụ một trường khai báo `List<String>` vẫn có thể trỏ tới collection bị thêm Integer thông qua raw/unchecked operation.

### 12.4. Công cụ phân tích API và tài liệu

Khi sinh tài liệu từ reflection, cần hiển thị generic declaration chính xác thay vì chỉ `getType()`. Với nested member type, owner quan trọng để hiện dạng `Outer<String>.Inner<Integer>` thay vì chỉ `Inner<Integer>`.

Phải chấp nhận metadata không phải lúc nào cũng có đủ thông tin, nhất là code legacy, raw declarations, erased generic methods và các lớp tạo động không giữ generic Signature như kỳ vọng.

## 13. `equals`, tính bất biến và những điều không nên giả định

`ParameterizedType` định nghĩa `equals` để các implementation phải so sánh dựa trên cùng khai báo generic và các type parameters tương ứng. Vì vậy hai reflective descriptions tương đương về kiểu có thể so sánh bằng `equals`, thay vì kiểm tra cùng tham chiếu object bằng `==`.

Chương trình ở phần 8 đã tạo:

- Type từ field `Samples.names`: `List<String>`.
- Type từ `new TypeRef<List<String>>() {}`: cũng `List<String>`.

Dòng `captured.equalsField=true` minh họa sự tương đương này. Không suy ra các `ParameterizedType` nhất thiết được intern, singleton hoặc trả chính cùng instance giữa các API.

`getActualTypeArguments()` cung cấp một mảng kết quả để người dùng đọc; không nên sửa mảng trả về rồi mong thay đổi metadata của class file hay Type gốc. Hãy xem mô tả kiểu là cấu trúc reflection được dùng để đọc và so sánh; muốn biến đổi một graph of types phục vụ framework, xây dựng mô hình riêng với các quy tắc tương đương rõ ràng.

## 14. Những tình huống biên cần cân nhắc

### 14.1. Kiểu top-level và member type

`List<String>` có owner null. `Outer<String>.Inner<Integer>` có owner `Outer<String>`. `Outer.Nested<Long>` có owner Class Outer. Không có một dạng owner chung dùng được cho mọi member type.

### 14.2. Generic metadata có thể thiếu hoặc hỏng

Reflection có thể gặp metadata `Signature` tham chiếu tới class không tồn tại hoặc cấu trúc signature không phù hợp. Các API reflection generic có thể ném `TypeNotPresentException`, `MalformedParameterizedTypeException` hoặc các ngoại lệ khác tùy tình huống/đường gọi. Đối với công cụ phân tích class file từ nguồn không tin cậy, hãy xử lý lỗi thay vì giả định metadata luôn hợp lệ.

### 14.3. Owner và type variable phức tạp

Với các kiểu lồng nhiều tầng, một inner có thể chịu ảnh hưởng type variable của nhiều owner. Việc ánh xạ tên T ở các scope khác nhau phải dựa trên `TypeVariable.getGenericDeclaration()` và cấu trúc owner, không chỉ so tên chữ `T`.

Ví dụ `Outer<T>` và `Inner<T>` đều có thể đặt tên T trong hai scope khác nhau; hai TypeVariable không tự đồng nhất chỉ vì `getName()` giống nhau.

### 14.4. Đối số là mảng generic

Một field `List<String>[]` có thể khai báo hợp lệ dù không được phép cấp phát trực tiếp `new List<String>[2]`. `getGenericType()` cho Type phản ánh mảng có component tham số hóa. Hãy phân biệt **khai báo kiểu field** với **biểu thức tạo đối tượng mảng**.

### 14.5. TypeName để hiển thị, không phải chứng minh dữ liệu

`type.getTypeName()` giúp in một biểu diễn kiểu dễ đọc. Nó không thực hiện kiểm tra runtime đối với collection, không giải quyết type variables theo object instance và không thay thế một type resolver.

### 14.6. Reflection API và khả năng tương thích JDK

Hãy sử dụng các interface public `java.lang.reflect.Type`, `ParameterizedType`, `WildcardType`, `TypeVariable` và `GenericArrayType`. Tránh phụ thuộc tên hoặc constructor của lớp hiện thực bên trong JDK vì chúng là chi tiết triển khai. Ví dụ mẫu được kiểm thử ở Java 17 và không cần truy cập các internal packages.

## 15. Hướng dẫn đọc `ParameterizedType` khi debug

Nếu log nói “không xác định được generic type” hoặc framework đọc sai một repository nested:

1. **Xác định vị trí khai báo.** Đó là field, generic superclass, implemented interface, return type hay method parameter?
2. **Dùng API `getGeneric...` tương ứng**, không chỉ `getType()`/`getSuperclass()`.
3. **Kiểm tra Type subtype** bằng `instanceof` trước khi cast.
4. **Đọc raw type** để xác định cấu trúc nền: List, Map, Repository, Outer.Inner.
5. **Đọc owner type** và duyệt owner nếu khác null, đặc biệt với inner class không static.
6. **Đọc actual arguments** theo từng cấp; không flatten các nested ParameterizedType tùy tiện.
7. **Xử lý wildcard, variable, generic array** theo API riêng, không cast hết sang Class.
8. **Nếu gặp T chưa biết**, lần theo generic superclass/interfaces và môi trường type variables thay vì tự gán T=Object.
9. **Nếu cần xác thực dữ liệu**, tách bước kiểm tra giá trị khỏi bước đọc metadata. TypeRef hoặc field annotation không đủ làm validator.
10. **Kiểm tra trên đúng bytecode/JDK đang chạy** khi metadata hoặc proxy class khác kết quả mong đợi.

Một cách log ổn định là in `Type.getTypeName()` kèm từng thành phần có cấu trúc và cờ `instanceof`, tránh log tên lớp cài đặt nội bộ của reflection.

## 16. Bài tập và đáp án

### Bài 1: Đọc List String

Field khai báo `List<String> names`. `getRawType()`, `getOwnerType()` và `getActualTypeArguments()` là gì?

**Đáp án:** Raw type là List; owner null; có một actual argument là Class String.

### Bài 2: Map lồng nhau

Với `Map<String,List<Integer>>`, số lượng actual arguments trực tiếp của Map là bao nhiêu?

**Đáp án:** Hai. Argument thứ hai là ParameterizedType List<Integer>, và Integer nằm trong actual arguments của List, không phải argument thứ ba của Map.

### Bài 3: Inner class

Với `Outer<String>.Inner<Integer>`, String nằm ở đâu?

**Đáp án:** Trong `getOwnerType()`, là ParameterizedType Outer<String>. Argument trực tiếp của Inner là Integer.

### Bài 4: Member không generic riêng

Tại sao `Outer<String>.Plain` vẫn có thể được phản chiếu thành ParameterizedType với 0 own arguments?

**Đáp án:** Plain là member không static của một owner được tham số hóa. Kiểu của owner mang String, còn Plain không khai báo type parameter riêng.

### Bài 5: Static nested

Với `Outer.Nested<Long>`, owner có cần mang T của Outer không?

**Đáp án:** Không. Nested static không gắn với một instance Outer<T>; trong ví dụ Java 17, owner là Class Outer và actual argument trực tiếp là Long.

### Bài 6: Wildcard

`List<? extends Number>` có actual argument thuộc loại Class Number hay WildcardType?

**Đáp án:** WildcardType. Number là upper bound đọc từ `getUpperBounds()`.

### Bài 7: Type variable

Một field trong `class Box<T> { List<T> xs; }` có generic argument T được reflection mô tả dưới dạng gì?

**Đáp án:** TypeVariable, không phải Class String tự động theo object Box<String> đang có.

### Bài 8: GenericArrayType

Vì sao `T[]` và `String[]` có thể trả loại Type khác nhau?

**Đáp án:** Mảng `T[]` có component là type variable non-reifiable nên có thể là GenericArrayType; `String[]` có Class runtime cụ thể.

### Bài 9: TypeRef

`new TypeRef<List<String>>() {}.getType()` có xác nhận một List đang chứa toàn String không?

**Đáp án:** Không. Nó mô tả generic superclass của anonymous subclass. Validator hoặc deserializer cần thực sự kiểm tra/chuyển đổi dữ liệu.

### Bài 10: So sánh Type

Có nên so `ParameterizedType` bằng `==` để xác định hai mô tả cùng `List<String>` không?

**Đáp án:** Không. Dùng `equals` cho sự tương đương về mô tả kiểu; hai API không phải trả cùng instance Type.

### Bài 11: Chẩn đoán ClassCastException

Nếu `Field.getGenericType()` trả `Class<?>` nhưng code ép luôn sang `ParameterizedType` rồi lỗi, cần sửa gì?

**Đáp án:** Kiểm tra loại Type bằng `instanceof ParameterizedType`. Field raw hoặc class thường không có ParameterizedType.

### Bài 12: Owner khác extends

`getOwnerType()` có trả superclass không?

**Đáp án:** Không. Nó mô tả owner của member type; quan hệ generic superclass đọc bằng `getGenericSuperclass()`.

## 17. Tóm tắt

`ParameterizedType` giúp Java reflection đọc lại cấu trúc một **kiểu được khai báo** sau khi type erasure khiến các instance không còn lớp runtime riêng cho mọi cách tham số hóa. Hãy hiểu ba thành phần chính:

- **Raw type:** class/interface nền, chẳng hạn List, Map hoặc Outer.Inner.
- **Owner type:** kiểu bao ngoài của member type, có thể null, Class hoặc ParameterizedType.
- **Actual type arguments:** những tham số kiểu được áp dụng trực tiếp cho type này, có thể là Class, ParameterizedType, WildcardType, TypeVariable hoặc các cấu trúc Type khác.

Với member classes, không được bỏ owner: `Outer<String>.Inner<Integer>` chứa String trong owner và Integer trong own arguments. Với generic API phức tạp, hãy duyệt Type như **một cây cấu trúc**, kiểm tra subtype bằng `instanceof`, theo dõi bounds/type variables khi cần, và tách metadata khỏi validation runtime.

**Ghi nhớ:** Reflection có thể mô tả “kiểu đã được viết trong khai báo”, nhưng không biến `List<String>` thành một class runtime mới và không tự bảo đảm dữ liệu thực tế bên trong List là String.
