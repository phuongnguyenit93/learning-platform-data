# Xử lý wildcard, generic array và owner type khi phân giải generic bằng Java Reflection

## 1. Bài toán: `Type` không phải lúc nào cũng là `Class<?>`

Khi lập trình với generics trong Java, một khai báo có thể chứa kiểu tham số hóa, wildcard, mảng generic và kiểu bao ngoài của nested class:

```java
List<? extends Number> numbers;
List<? super Integer> targets;
List<String>[] pages;
Outer<String>.Inner<Integer> entry;
```

Đây là **các khai báo minh họa**, cần đặt trong class thích hợp với import và định nghĩa `Outer` tương ứng.

Nếu công cụ Reflection chỉ gọi `Field.getType()` rồi ép kết quả thành `Class<?>`, phần lớn cấu trúc generic đã bị **type erasure**. Để đọc và phân giải đúng, cần bắt đầu từ `Field.getGenericType()`, `Method.getGenericReturnType()`, `Method.getGenericParameterTypes()`, `Constructor.getGenericParameterTypes()` hoặc `Class.getGenericSuperclass()` / `getGenericInterfaces()`.

Những API đó trả các đối tượng thuộc họ **`java.lang.reflect.Type`**. Ba nhánh đặc biệt quan trọng trong bài này:

- **`WildcardType`:** tham số kiểu `?`, `? extends X` hoặc `? super X` với các giới hạn trên/dưới.
- **`GenericArrayType`:** kiểu mảng có component type là kiểu generic không reifiable, chẳng hạn `T[]` hoặc `List<String>[]`.
- **`ParameterizedType.getOwnerType()`:** kiểu sở hữu của một nested/member type, ví dụ phần `Outer<String>` trong `Outer<String>.Inner<Integer>`.

Để **phân giải generic** chứ không chỉ liệt kê, bạn còn phải xử lý `TypeVariable<?>` và ánh xạ biến kiểu theo class/method và quan hệ kế thừa. Nếu bỏ qua một nhánh, thuật toán có thể mất bounds, thông tin component hay ánh xạ generic của outer.

## 2. Cây `Type` cần nhận diện

`java.lang.reflect.Type` là một interface. Một công cụ phân tích generic phải biết các triển khai cơ bản sau:

| Loại `Type` | Ví dụ khai báo | Ý nghĩa / cách xử lý |
| --- | --- | --- |
| `Class<?>` | `String`, `int`, `String[]` | Kiểu runtime; với mảng thông thường dùng `Class.isArray()` và `getComponentType()` |
| `ParameterizedType` | `List<String>`, `Map<String,Integer>`, `Outer<String>.Inner<Integer>` | Xử lý `getRawType()`, `getActualTypeArguments()` và `getOwnerType()` |
| `TypeVariable<?>` | `T` trong `class Box<T>` | Tra ánh xạ theo biến kiểu **của đúng declaration**, không chỉ tên chuỗi |
| `WildcardType` | `? extends Number`, `? super Integer` | Đọc `getUpperBounds()` và `getLowerBounds()`, có thể cần phân giải đệ quy |
| `GenericArrayType` | `T[]`, `List<? extends Number>[]` | Đọc `getGenericComponentType()` và phân giải component đệ quy |

Nhận diện bằng `instanceof` (Java 17+):

```java
if (type instanceof ParameterizedType parameterized) {
    // Có raw type, actual arguments và có thể có owner type.
} else if (type instanceof WildcardType wildcard) {
    // Đọc upper/lower bounds.
} else if (type instanceof GenericArrayType array) {
    // Đọc generic component type.
} else if (type instanceof TypeVariable<?> variable) {
    // Tra binding / bounds của type variable.
} else if (type instanceof Class<?> clazz) {
    // Kiểu thường, primitive hoặc class array.
}
```

Đây là **mảnh thuật toán**, không phải chương trình độc lập; cần import các interface từ `java.lang.reflect` và khai báo `type`.

**Nguyên tắc không được bỏ qua:** Cấu trúc có thể lồng nhau ở nhiều tầng. Ví dụ `List<? extends T[]>[]` có outer `GenericArrayType`, component `ParameterizedType`, argument `WildcardType` và upper bound là một `GenericArrayType` khác chứa `TypeVariable<T>`. Thuật toán xử lý một cấp rồi ép tất cả các con về `Class<?>` sẽ làm sai kết quả.

## 3. `WildcardType`: phân biệt bounds trên và dưới

Wildcard xuất hiện trong *type argument*, không phải mọi vị trí có biến kiểu:

```java
List<?> any;
List<? extends Number> producers;
List<? super Integer> consumers;
```

Khi đọc `List<? extends Number>` qua Reflection:

1. Type của field là `ParameterizedType` có raw type `List.class`.
2. `getActualTypeArguments()[0]` là một `WildcardType`.
3. `wildcard.getUpperBounds()` có `Number.class`.
4. `wildcard.getLowerBounds()` là mảng rỗng.

Tương tự, với `List<? super Integer>`, lower bound là `Integer.class`, còn upper bound thường là `Object.class`.

### 3.1. Hai hàm bounds của `WildcardType`

| Cú pháp | `getUpperBounds()` | `getLowerBounds()` |
| --- | --- | --- |
| `?` | `[Object.class]` | `[]` |
| `? extends Number` | `[Number.class]` | `[]` |
| `? super Integer` | `[Object.class]` | `[Integer.class]` |
| `? extends T` | `[TypeVariable<T>]` | `[]` |

Các ô trên mô tả cấu trúc điển hình của wildcard do Java compiler tạo, **không** phải chuỗi stdout của `Arrays.toString`. API trả `Type[]`, nên bounds có thể là `Class<?>`, `TypeVariable<?>`, `ParameterizedType` hoặc các kiểu `Type` khác. Khi viết code tổng quát, đừng giả định `getUpperBounds()[0]` luôn là `Class<?>`.

- **Wildcard không giới hạn `?`:** upper bound mang mặc định `Object`; không có lower bound.
- **`? extends U`:** ràng buộc trên bằng `U`. Nếu `U` là `T`, sau khi suy ra `T → String`, biểu diễn đã giải quyết tương ứng là `? extends String`.
- **`? super L`:** ràng buộc dưới bằng `L`; upper bound thông thường là `Object`.
- **Cần giữ đúng hướng ràng buộc:** không được biến `? super Integer` thành `? extends Integer` khi thay kiểu.

### 3.2. Liên hệ sử dụng: PECS

Cụm *Producer Extends, Consumer Super* giúp ghi nhớ nhiều tình huống:

```java
List<? extends Number> src;  // Đọc phần tử như Number; hạn chế thêm giá trị khác null
List<? super Integer> dst;   // Có thể thêm Integer; đọc thường chỉ bảo đảm Object
```

Đây là mô tả về ràng buộc sử dụng trong Java source; trong Reflection, ta đọc **cấu trúc bounds** để phục vụ validation, serialization hoặc sinh metadata. Không dùng `WildcardType` để tự suy luận rằng `List` ở runtime thực sự chứa đúng kiểu phần tử: generic type information của object có thể đã bị erase.

### 3.3. Wildcard không đồng nghĩa `TypeVariable`

`? extends Number` là **wildcard**; `T extends Number` trong `class Holder<T extends Number>` là một **type variable được khai báo có tên**.

Đừng lấy `TypeVariable.getBounds()` rồi nghĩ nó giống hoàn toàn `WildcardType.getUpperBounds()`. `TypeVariable` có declaration identity và có thể có intersection bounds; wildcard là type argument mô tả khoảng biến thiên kiểu.

## 4. `GenericArrayType`: component generic nằm trong mảng

Một khai báo như `T[]` hoặc `List<String>[]` không luôn phản ánh bằng `Class<?>` thông thường.

```java
class Store<T> {
    T[] items;
    List<String>[] lists;
    String[] strings;
}
```

Với `Store.class.getDeclaredField(...).getGenericType()`:

| Field | Dạng `Type` thường nhận được | Component type |
| --- | --- | --- |
| `items` (`T[]`) | `GenericArrayType` | `TypeVariable<T>` |
| `lists` (`List<String>[]`) | `GenericArrayType` | `ParameterizedType List<String>` |
| `strings` (`String[]`) | `Class<?>` có `isArray() == true` | `String.class` |

**Không phải tất cả mảng đều là `GenericArrayType`.** Trong thuật toán phân giải, cần xử lý cả nhánh `Class.isArray()` để đi sâu vào mảng thông thường, đặc biệt khi định dạng hoặc chuyển đổi nhiều tầng mảng.

Chẳng hạn:

```java
Type fieldType = Store.class.getDeclaredField("lists")
        .getGenericType();
GenericArrayType array = (GenericArrayType) fieldType;
Type component = array.getGenericComponentType();
// component là ParameterizedType biểu diễn List<String>
```

Đoạn minh họa yêu cầu import `Type` và `GenericArrayType`, cũng như xử lý `NoSuchFieldException`. Không dùng `(Class<?>) component` nếu chưa kiểm tra subtype.

### 4.1. Vì sao có generic array nhưng không được `new List<String>[10]`?

Java thường **cấm tạo trực tiếp** array với component parameterized không reifiable:

```java
// Không biên dịch:
// List<String>[] data = new List<String>[10];
```

Dù vậy, **khai báo field hoặc tham số** có kiểu `List<String>[]` là hợp lệ. Reflection có thể giữ cấu trúc generic của khai báo đó trong `GenericArrayType`. Sự xuất hiện của generic array metadata không chứng minh bạn được phép tạo mảng ấy bằng cú pháp `new List<String>[...]`.

Một mảng runtime thực tế vẫn có class theo erased component, ví dụ `List[].class`. Phân giải metadata `List<String>[]` không biến runtime array store checks thành hệ kiểm tra type argument `String`; giới hạn type erasure vẫn còn.

### 4.2. Khi thay `T`, nên xử lý thế nào?

Giả sử:

```java
class Base<T> {
    T[] values;
    List<? extends T>[] groups;
}

class StringBase extends Base<String> {}
```

Ánh xạ từ `StringBase` cho biến `T` của `Base` là `T → String`. Khi phân giải *cấu trúc generic*:

- `T[]` trở thành biểu diễn `String[]`.
- `List<? extends T>[]` trở thành `List<? extends String>[]`.
- Nếu cần trả một đối tượng `Type` thực, phải tái tạo/biểu diễn đúng các node sau thay thế; không thể chỉ thay chuỗi trong `getTypeName()`.

Nếu component đã thay thế thành một `Class<?>` cụ thể và bài toán cần **Class object của mảng**, có thể lấy một class tương ứng bằng `java.lang.reflect.Array.newInstance(componentClass, 0).getClass()`. Nếu component vẫn là `ParameterizedType` hoặc chứa wildcard, không có `Class<?>` nào biểu diễn trực tiếp toàn bộ thông tin parameterized; cần giữ một `GenericArrayType` hoặc đối tượng metadata tương đương.

## 5. `ParameterizedType.getOwnerType()`: chủ sở hữu generic của member type

Xét khai báo:

```java
class Outer<A> {
    class Inner<B> {
        A fromOuter;
        B fromInner;
    }
}
```

Một field ở nơi thích hợp có thể dùng kiểu:

```java
Outer<String>.Inner<Integer> entry;
```

Đây là **member inner class**. `ParameterizedType` của field `entry` có cấu trúc:

```text
ParameterizedType: Outer<String>.Inner<Integer>
├── getRawType()                 → Class: Outer.Inner
├── getActualTypeArguments()     → [Class: Integer]
└── getOwnerType()               → ParameterizedType: Outer<String>
    ├── getRawType()             → Class: Outer
    └── getActualTypeArguments() → [Class: String]
```

Điểm quan trọng: **`getActualTypeArguments()` của `Inner<Integer>` chỉ có `Integer`**, không tự lặp lại `String` từ outer. Muốn giải được field `fromOuter` có kiểu `A`, thuật toán phải đi lên **`getOwnerType()`** để lấy binding `A → String`.

Nếu bạn chỉ xây `Map<TypeVariable<?>, Type>` từ `Inner.class.getTypeParameters()`, bạn chỉ có `B → Integer` và sẽ làm mất ý nghĩa của `A`.

### 5.1. Owner type khác enclosing instance

Ba ý nghĩa không được đồng nhất:

- **`getOwnerType()`:** đối tượng `Type` mô tả kiểu chứa member type, có thể mang generic arguments như `Outer<String>`. Đây là **metadata về kiểu**.
- **Enclosing instance:** một **object** cụ thể kiểu `Outer<?>` cần để tạo non-static member inner object, ví dụ `outer.new Inner<Integer>()`. Đây là **giá trị runtime**, không phải `Type`.
- **`Class.getEnclosingClass()` / `getDeclaringClass()`:** trả metadata `Class<?>` về nơi khai báo/bối cảnh từ vựng, không nhất thiết bao gồm type arguments của cách dùng cụ thể.

Không truyền `ParameterizedType getOwnerType()` làm đối số constructor thay cho một instance `Outer` thật.

### 5.2. Owner type của static nested class

`static nested class` có thể có owner type metadata mặc dù nó **không gắn với enclosing instance**. Ví dụ:

```java
class Outer<A> {
    static class Nested<B> {}
}
```

Kiểu sử dụng hợp lệ là `Outer.Nested<Integer>`, **không** phải `Outer<String>.Nested<Integer>` vì static nested class không phụ thuộc parameterization của outer. Trong Reflection, owner có thể biểu diễn `Outer.class` (một `Class<?>`), thay vì `Outer<String>`; bạn vẫn không được suy từ `getOwnerType() != null` rằng phải truyền enclosing instance.

Với top-level parameterized type như `List<String>`, `getOwnerType()` trả `null`. Tuy nhiên, khi raw type là member class, owner có thể khác `null`, và `getActualTypeArguments()` thậm chí có thể rỗng nếu member **không khai báo type parameters** nhưng được đặt dưới một parameterized owner. Xây traversal phải xét owner độc lập với độ dài danh sách actual arguments.

## 6. Thuật toán phân giải generic có hệ thống

Một trình phân giải kiểu (*type resolver*) nên nhận hai thứ:

1. Một **`Type` cần phân giải**, chẳng hạn generic type của field/return/parameter.
2. Một môi trường binding **`Map<TypeVariable<?>, Type>`** đã suy ra từ ngữ cảnh sử dụng (subclass, interface implementation, parameterized owner, method context...).

Sau đó đi đệ quy:

```text
resolve(type, bindings)
    Class:
        nếu là mảng → resolve(component); có thể dựng Class-array nếu phù hợp
        nếu không → giữ nguyên
    TypeVariable:
        tìm binding bằng chính TypeVariable declaration; nếu không có → giữ nguyên
        nếu có → resolve(binding) (với bảo vệ vòng lặp)
    ParameterizedType:
        resolve(owner) nếu khác null
        resolve từng actual type argument
        giữ raw type; kết hợp thành biểu diễn ParameterizedType mới nếu có thay đổi
    GenericArrayType:
        resolve(generic component)
        kết hợp thành array type, giữ tham số hóa nếu component không reifiable
    WildcardType:
        resolve toàn bộ upper bounds
        resolve toàn bộ lower bounds
        giữ nguyên hướng extends/super và sự phân biệt wildcard
    Khác:
        lưu nguyên hoặc báo rõ kiểu không được hỗ trợ
```

Đây là **pseudocode**, không phải cú pháp Java để biên dịch.

**Quan trọng về identity:** Hai biến có cùng tên `T` nhưng thuộc `class Box<T>` và `<T> void send(T item)` là **hai `TypeVariable<?>` khác nhau**. Không dùng `Map<String, Type>` thuần với khóa `"T"`; dùng trực tiếp `TypeVariable<?>` làm khóa và xác định `getGenericDeclaration()` khi debug.

**Quan trọng về chuỗi ánh xạ:** Trong kế thừa nhiều tầng, có thể gặp `U → T` rồi `T → String`. Phân giải phải tiếp tục theo mapping đến khi ổn định, nhưng cần bảo vệ vòng lặp/bounds tự tham chiếu. Nếu không có binding, trả về type variable chưa giải quyết, **không tự đổi thành `Object`** một cách tùy tiện.

### 6.1. Thu thập bindings từ supertype

```java
class Parent<T> {
    T[] values;
}

class Child<U> extends Parent<U> {}

class Concrete extends Child<String> {}
```

Ánh xạ ban đầu từ `Concrete` là `U → String`. Khi xét superclass của `Child<U>`, thêm `T → U`. Thuật toán phải theo tiếp `T → U → String` rồi mới đưa ra kết quả `String[]` cho field `Parent.values`.

Để chạy trên nhiều tầng interface/superclass, hãy dùng `getGenericSuperclass()`, `getGenericInterfaces()` và đi theo đúng đường dẫn từ class thực tế tới declaration sở hữu member. Không nhập nhằng binding từ các nhánh unrelated; một `TypeVariable` luôn thuộc một declaration cụ thể.

### 6.2. Thu thập bindings từ owner trước member

Với `Outer<String>.Inner<Integer>`:

1. Xử lý `getOwnerType() == Outer<String>`, ánh xạ `Outer.A → String`.
2. Xử lý `getRawType() == Inner.class` và arguments của chính `Inner`, ánh xạ `Inner.B → Integer`.
3. Phân giải field trong `Inner`: `A` và `B` sẽ lần lượt trở thành `String` và `Integer`.

Đối với nested type nhiều tầng, đi tiếp theo chuỗi owner đến lúc `null` hoặc tới `Class<?>` không parameterized. Không coi `getOwnerType()` luôn là `ParameterizedType`: nó có thể là `Class<?>`.

## 7. Chương trình Java 17+ đầy đủ: đọc và phân giải ba nhánh

Chương trình sau dùng một **type renderer** đệ quy. Nó không cố giả làm một thư viện tạo `ParameterizedType`/`WildcardType` mới; thay vào đó, nó đọc cấu trúc Reflection và áp dụng bindings để sinh biểu diễn dễ kiểm thử. Đây là bước học thuật toán trước khi viết resolver trả về `Type` mới.

Tạo tệp **`GenericGraphDemo.java`**:

```java
import java.lang.reflect.*;
import java.util.*;

public class GenericGraphDemo {
    static class Container<A> {
        class Entry<B> {
            A ownerValue;
            B value;
            List<? extends A>[] grids;
        }

        static class Nested<C> {
            C data;
        }
    }

    static class Template<T> {
        T[] values;
        List<? extends T>[] producers;
        List<? super T> consumers;
    }

    static class TextTemplate extends Template<String> {}

    static class Cases {
        Container<String>.Entry<Integer> member;
        Container<String>.Entry<Integer>[] memberArray;
        List<? extends Number>[] numberArrays;
        List<? super Integer> sinks;
        List<?> anything;
        String[] ordinaryArray;
    }

    // Thu thập type-variable bindings từ owner trước,
    // rồi từ type arguments của chính member type.
    static void bind(Type type, Map<TypeVariable<?>, Type> env) {
        if (!(type instanceof ParameterizedType p)) {
            return;
        }
        if (p.getOwnerType() != null) {
            bind(p.getOwnerType(), env);
        }

        Class<?> raw = (Class<?>) p.getRawType();
        TypeVariable<?>[] vars = raw.getTypeParameters();
        Type[] args = p.getActualTypeArguments();

        for (int i = 0; i < vars.length; i++) {
            env.put(vars[i], args[i]);
        }
    }

    static String show(Type type, Map<TypeVariable<?>, Type> env) {
        return show(type, env, new HashSet<>());
    }

    static String show(Type type, Map<TypeVariable<?>, Type> env,
                       Set<TypeVariable<?>> visiting) {
        if (type instanceof Class<?> c) {
            return c.isArray()
                    ? show(c.getComponentType(), env, visiting) + "[]"
                    : c.getSimpleName();
        }

        if (type instanceof TypeVariable<?> v) {
            Type replacement = env.get(v);
            if (replacement == null || replacement.equals(v)
                    || !visiting.add(v)) {
                return v.getName();
            }
            try {
                return show(replacement, env, visiting);
            } finally {
                visiting.remove(v);
            }
        }

        if (type instanceof GenericArrayType a) {
            return show(a.getGenericComponentType(), env, visiting) + "[]";
        }

        if (type instanceof WildcardType w) {
            Type[] lowers = w.getLowerBounds();
            if (lowers.length != 0) {
                return "? super " + show(lowers[0], env, visiting);
            }
            Type[] uppers = w.getUpperBounds();
            if (uppers.length == 0 ||
                    (uppers.length == 1 && uppers[0] == Object.class)) {
                return "?";
            }
            StringJoiner upper = new StringJoiner(" & ");
            for (Type bound : uppers) {
                upper.add(show(bound, env, visiting));
            }
            return "? extends " + upper;
        }

        if (type instanceof ParameterizedType p) {
            Class<?> raw = (Class<?>) p.getRawType();
            Type owner = p.getOwnerType();
            String head = owner == null
                    ? raw.getSimpleName()
                    : show(owner, env, visiting) + "." + raw.getSimpleName();
            Type[] args = p.getActualTypeArguments();
            if (args.length == 0) {
                return head;
            }

            StringJoiner body = new StringJoiner(", ", "<", ">");
            for (Type arg : args) {
                body.add(show(arg, env, visiting));
            }
            return head + body;
        }

        // Để không giả định về các implementation Type khác.
        return type.getTypeName();
    }

    public static void main(String[] args) throws Exception {
        Type numbers = Cases.class
                .getDeclaredField("numberArrays").getGenericType();
        GenericArrayType array = (GenericArrayType) numbers;
        ParameterizedType list =
                (ParameterizedType) array.getGenericComponentType();
        WildcardType upper =
                (WildcardType) list.getActualTypeArguments()[0];

        System.out.println("numberArrays generic array: "
                + (numbers instanceof GenericArrayType));
        System.out.println("component raw List: "
                + (list.getRawType() == List.class));
        System.out.println("upper is Number: "
                + (upper.getUpperBounds()[0] == Number.class));
        System.out.println("lower bound count: "
                + upper.getLowerBounds().length);

        ParameterizedType sinks = (ParameterizedType) Cases.class
                .getDeclaredField("sinks").getGenericType();
        WildcardType lower =
                (WildcardType) sinks.getActualTypeArguments()[0];
        System.out.println("super lower Integer: "
                + (lower.getLowerBounds()[0] == Integer.class));
        System.out.println("super upper Object: "
                + (lower.getUpperBounds()[0] == Object.class));

        Type plain = Cases.class
                .getDeclaredField("ordinaryArray").getGenericType();
        System.out.println("ordinary array Class: "
                + (plain instanceof Class<?>));

        Type members = Cases.class
                .getDeclaredField("memberArray").getGenericType();
        System.out.println("memberArray generic array: "
                + (members instanceof GenericArrayType));

        Type memberType = Cases.class
                .getDeclaredField("member").getGenericType();
        ParameterizedType entry = (ParameterizedType) memberType;
        ParameterizedType owner =
                (ParameterizedType) entry.getOwnerType();
        System.out.println("owner argument String: "
                + (owner.getActualTypeArguments()[0] == String.class));
        System.out.println("inner argument Integer: "
                + (entry.getActualTypeArguments()[0] == Integer.class));

        Map<TypeVariable<?>, Type> byOwner = new HashMap<>();
        bind(memberType, byOwner);

        System.out.println("outer field resolved: "
                + show(Container.Entry.class
                        .getDeclaredField("ownerValue").getGenericType(),
                        byOwner));
        System.out.println("inner field resolved: "
                + show(Container.Entry.class
                        .getDeclaredField("value").getGenericType(),
                        byOwner));
        System.out.println("grids resolved: "
                + show(Container.Entry.class
                        .getDeclaredField("grids").getGenericType(),
                        byOwner));

        Type base = TextTemplate.class.getGenericSuperclass();
        Map<TypeVariable<?>, Type> bySubclass = new HashMap<>();
        bind(base, bySubclass);

        System.out.println("T array resolved: "
                + show(Template.class
                        .getDeclaredField("values").getGenericType(),
                        bySubclass));
        System.out.println("wildcard array resolved: "
                + show(Template.class
                        .getDeclaredField("producers").getGenericType(),
                        bySubclass));
        System.out.println("super wildcard resolved: "
                + show(Template.class
                        .getDeclaredField("consumers").getGenericType(),
                        bySubclass));
    }
}
```

Biên dịch và chạy trong thư mục chứa file bằng JDK 17 trở lên:

```bash
javac GenericGraphDemo.java
java GenericGraphDemo
```

**Stdout dự kiến:**

```text
numberArrays generic array: true
component raw List: true
upper is Number: true
lower bound count: 0
super lower Integer: true
super upper Object: true
ordinary array Class: true
memberArray generic array: true
owner argument String: true
inner argument Integer: true
outer field resolved: String
inner field resolved: Integer
grids resolved: List<? extends String>[]
T array resolved: String[]
wildcard array resolved: List<? extends String>[]
super wildcard resolved: List<? super String>
```

### 7.1. Giải thích cây kiểu quan sát được

- `numberArrays` là mảng với component `List<? extends Number>`; `getGenericType()` trả `GenericArrayType`, bên trong là `ParameterizedType`, rồi một `WildcardType`. Upper bound là `Number`.
- `sinks` có argument `? super Integer` nên lower bound là `Integer`, upper bound mặc định là `Object`.
- `ordinaryArray` có generic type là một `Class<?>` đại diện `String[]`.
- `memberArray` có generic component là `Container<String>.Entry<Integer>` nên là `GenericArrayType`.
- `entry.getActualTypeArguments()` chỉ có `Integer`. `String` nằm ở `entry.getOwnerType()`.
- Hàm `bind` đi qua owner và thêm biến `A` của `Container` cùng biến `B` của `Entry`. Do đó khi duyệt field của `Entry`, `A` được giải thành `String`, `B` thành `Integer`.
- Với `TextTemplate extends Template<String>`, binding từ `getGenericSuperclass()` là `T → String`. Hàm `show` duyệt `T[]`, wildcard và generic array, giữ nguyên cấu trúc rồi thay đúng biến kiểu.

**Giới hạn có chủ đích của ví dụ:** `show` tạo **chuỗi mô tả**, không phải một đối tượng `Type` mới. `bind` minh họa hai tình huống cụ thể (owner parameterized và một superclass parameterized). Trình phân giải dùng trong thư viện thực tế phải hỗ trợ nhiều tầng kế thừa/interface, generic method context, việc thiếu `Signature`, raw types và các triển khai `Type` không chuẩn. Không coi đoạn demo là hệ thống generic resolver đầy đủ cho mọi bytecode hợp lệ.

## 8. Nếu cần trả về `Type` đã thay thế, không chỉ một chuỗi

Trong những ứng dụng như schema generation hoặc serializer, kết quả thường cần là **cấu trúc `Type` mới** chứ không phải chuỗi hiển thị. Khi đó:

- `Class<?>` thông thường có thể giữ nguyên.
- `TypeVariable<?>` có binding phải được thay bằng `Type` tương ứng.
- `ParameterizedType` cần biểu diễn mới chứa **owner đã phân giải**, **raw type** và **actual type arguments đã phân giải**.
- `GenericArrayType` cần biểu diễn mới chứa **generic component type đã phân giải**; nếu component đã thành một `Class<?>` hợp lệ, có thể tạo class mảng tương ứng bằng `Array.newInstance(...)`.
- `WildcardType` cần biểu diễn mới với **upper/lower bounds đã phân giải**, không đánh mất hướng `extends`/`super`.
- Nếu không đổi gì, có thể giữ nguyên `Type` ban đầu thay vì tự tạo object.

Các interface `ParameterizedType`, `GenericArrayType` và `WildcardType` mô tả giao diện dữ liệu; Java SE không cung cấp một public factory chuẩn chung để bạn tùy ý tạo mọi tổ hợp. Thư viện có thể sử dụng implementation `Type` riêng, nhưng cần thực hiện đúng `equals`/`hashCode`, mảng bounds/arguments mang bản sao phòng thủ, và semantics của `getTypeName()`/`toString()`. **Không tạo `Class<?>` giả để biểu diễn `List<String>`:** tại runtime, `List.class` không chứa type argument `String`.

Ví dụ, sau `T → String`:

- `T[]` có thể trở thành `String[].class` nếu cần class mảng reifiable.
- `List<? extends T>[]` vẫn cần biểu diễn kiểu generic cho component `List<? extends String>`; không có class literal `List<? extends String>[].class`.
- `Outer<T>.Inner<Integer>` phải thay cả owner `Outer<String>`, không chỉ inner argument `Integer`.

## 9. Giới hạn type erasure và metadata

Không phải `Type` nào bạn mong muốn cũng luôn tồn tại với đủ thông tin:

- **Generic signature có thể bị thiếu.** JVM descriptors của field/method sau erasure không mô tả đầy đủ wildcard và type arguments. Reflection generic APIs dựa vào metadata `Signature` nếu có.
- **Raw type không đủ để tái tạo generic.** Từ `List.class` không thể suy ra giá trị là `List<String>` hay `List<Integer>`.
- **Method type parameters có phạm vi riêng.** Một `<T> T convert(T input)` không tự giải được `T` chỉ nhờ class generic bindings; có thể cần thông tin từ ngữ cảnh gọi mà Reflection cơ bản không cung cấp.
- **Generic arrays không biến JVM array thành cấu trúc kiểm tra type argument.** Kiểu của array ở runtime vẫn chịu erasure và có thể dẫn đến heap pollution nếu lập trình viên dùng raw types/unchecked casts sai.
- **Recursive bounds:** `class Node<T extends Comparable<T>>` có tham chiếu lại chính `T`. Thuật toán in/giải bounds cần chặn vòng lặp, tránh đệ quy vô hạn.
- **Module visibility / classpath:** khi đọc generic metadata, Reflection có thể gặp `TypeNotPresentException`, `MalformedParameterizedTypeException` hoặc `GenericSignatureFormatError` nếu kiểu liên quan không có hoặc signature không hợp lệ. Không coi mọi thông tin thiếu là do wildcard logic.
- **Không suy ra syntax gốc:** dạng viết import, whitespace hoặc cách khai báo tương đương không thể tái tạo chính xác từ `Type.getTypeName()`.

### 9.1. Đừng “giải” type variable bằng upper bound một cách âm thầm

Giả sử:

```java
class NumericBox<T extends Number> {
    T value;
}
```

Nếu bạn đọc `NumericBox.class` mà **chưa có** ngữ cảnh như `NumericBox<Integer>`, `T` vẫn là `TypeVariable<T>`. Biết `getBounds()[0] == Number.class` không cho phép kết luận field thực tế là `Number` về generic semantic: `Number` chỉ là **giới hạn trên**, không phải argument đã gắn. Có thể dùng bound trong validation hoặc erased view nếu bài toán yêu cầu, nhưng phải giữ rõ sự khác biệt.

### 9.2. Chuỗi tên không thay thế cấu trúc

`Type.getTypeName()` hữu ích để log. Tuy nhiên:

- Không parse/replace `"T"` bằng `"String"` trong một chuỗi dài vì có thể trùng tên kiểu, trùng tên biến hoặc biến ở declaration khác.
- Không cắt chuỗi theo dấu `<`, `>`, `[` để tìm wildcard/array; đây là công việc của cây `Type` và các API phản ánh.
- Không dựa hoàn toàn vào tên do implementation `toString()` sinh ra để xác định type identity.
- Dùng `TypeVariable.getGenericDeclaration()`, `ParameterizedType.getRawType()` và các mảng `Type` con để phân giải chính xác.

## 10. Quy trình ứng dụng trong framework

Một cách triển khai có kiểm soát:

1. **Xác định member declaration:** field, method, parameter, superclass hay interface.
2. **Lấy generic metadata:** `getGenericType()` / `getGenericReturnType()` / `getGenericParameterTypes()`; tránh bắt đầu bằng `getType()` nếu cần generic arguments.
3. **Xác định ngữ cảnh sử dụng:** class con, owner type đã parameterized, hoặc type token có lưu generic args.
4. **Xây binding theo declaration:** đi từ context tới class sở hữu member; duyệt superclass/interface và owner type; dùng `TypeVariable<?>` làm khóa.
5. **Duyệt đệ quy mọi nhánh:** `ParameterizedType`, `WildcardType`, `GenericArrayType`, `TypeVariable`, `Class<?>`, kể cả mảng thường.
6. **Giữ đúng semantics:** wildcard bounds theo chiều, array component, owner parameterization, thứ tự type arguments và raw type.
7. **Xử lý chưa xác định:** giữ biến chưa ràng buộc thay vì tự cho là `Object`; nếu signature sai/mất, báo hạn chế.
8. **Kiểm thử:** có test cho `List<?>`, `? extends`, `? super`, `T[]`, `List<T>[]`, `Outer<String>.Inner<Integer>`, static nested class và kế thừa nhiều tầng.

### Bảng lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cast mọi `Type` thành `Class<?>` | `ClassCastException` hoặc mất generics | Duyệt theo `instanceof` |
| Bỏ `WildcardType.getLowerBounds()` | `? super Integer` bị hiểu sai | Phân biệt upper/lower |
| Mặc định wildcard có lower bound | Sai với `?` và `? extends X` | Mảng lower có thể rỗng |
| Giải wildcard bằng cách lấy upper bound duy nhất | Mất dấu `?` và hướng variance | Giữ node wildcard khi tái cấu trúc |
| Chỉ hỗ trợ `GenericArrayType` | Bỏ sót `String[]` phản ánh bằng `Class` | Xử lý cả `Class.isArray()` |
| Chỉ dùng `getActualTypeArguments()` ở inner type | Mất `A → String` từ `Outer<String>` | Đọc `getOwnerType()` đệ quy |
| `getOwnerType() != null` nghĩa là cần outer object | Nhầm generic metadata với enclosing instance | Xét `static` và cấu trúc member class riêng |
| Dùng `Map<String,Type>` với tên `T` | Đụng tên type variable khác declaration | Dùng `TypeVariable<?>` làm key |
| Gặp `T extends Number` thì luôn map `T → Number` | Cố định hóa type argument chưa biết | Giữ unresolved `T` |
| Parse `getTypeName()` thay vì đi cây | Sai khi lồng generic/wildcard/owner | Dùng các subtype `Type` |
| Giữ nguyên `ParameterizedType` dù owner đã đổi | Kết quả nội bộ bất nhất | Phân giải cả owner và arguments |
| Giả định metadata generic luôn đầy đủ | Không xử lý class file thiếu/malformed `Signature` | Xử lý trường hợp thiếu và các lỗi phản ánh |

## 11. Bài tự kiểm tra

### Câu 1: wildcard bounds

Với `List<? super Long>`, `getUpperBounds()` và `getLowerBounds()` của wildcard thường có gì?

**Đáp án:** Upper chứa `Object.class`; lower chứa `Long.class`. Nếu bạn chỉ đọc upper, bạn đã làm mất thông tin quan trọng nhất của `super`.

### Câu 2: generic array

Field `Map<String,Integer>[] mapping` có `getGenericType()` là `Class<?>` hay `GenericArrayType`?

**Đáp án:** `GenericArrayType`; component là `ParameterizedType` biểu diễn `Map<String,Integer>`. Nó khác field `String[] names` có `Class<?>` là array class.

### Câu 3: owner type

Cho `Outer<String>.Inner<Integer>` với `class Outer<A> { class Inner<B> {} }`. Vì sao `Inner.class.getTypeParameters()` không giúp tìm `A → String`?

**Đáp án:** `Inner` chỉ khai báo biến `B`. `A` thuộc declaration `Outer`, và argument `String` nằm trong `ParameterizedType.getOwnerType()`.

### Câu 4: nested static

`Outer.Nested<Integer>` là static nested class. Nếu Reflection cho thấy owner type khác `null`, có bắt buộc tạo một đối tượng `Outer` để gọi constructor của `Nested` không?

**Đáp án:** Không. Owner type ở đây là thông tin cấu trúc kiểu. Static nested class không cần enclosing instance cho riêng quan hệ lồng lớp này.

### Câu 5: chuỗi thay thế kiểu

Giả sử `Parent<T>`, `Child<U> extends Parent<U>`, `Concrete extends Child<String>`. Muốn giải field `Parent<T>.value` trong ngữ cảnh `Concrete` thì đi như thế nào?

**Đáp án:** Xây `U → String` và `T → U`, sau đó đệ quy `T → U → String`. Ánh xạ theo `TypeVariable<?>` của từng declaration, không theo tên string.

### Câu 6: metadata chưa đủ

Nếu chỉ có `List.class` trong runtime, thuật toán có thể biết chắc type argument nguồn là `String` không?

**Đáp án:** Không. Erasure đã bỏ tham số kiểu; cần một `ParameterizedType` trong generic declaration, type token, hoặc metadata khác có thực, nếu không phải ghi nhận là chưa biết.

## 12. Tổng kết

Khi phân giải generic bằng Reflection, cần xem `Type` là **cây cấu trúc**:

- **`WildcardType`:** bảo toàn upper/lower bounds và hướng `extends`/`super`.
- **`GenericArrayType`:** phân giải đệ quy component type; phân biệt với mảng thường phản ánh bằng `Class<?>`.
- **`ParameterizedType.getOwnerType()`:** lần theo kiểu sở hữu của member type để không mất bindings của outer generic class.
- **`TypeVariable<?>`:** ánh xạ bằng identity của declaration, đi theo các ràng buộc ngữ cảnh và bảo vệ vòng lặp.

Một resolver tốt trả về metadata có ý nghĩa hoặc ghi rõ điểm chưa biết; nó không tự chế lại generic arguments từ raw `Class<?>` và không đồng nhất type metadata với enclosing instance runtime.

### Tài liệu tham khảo

- [Java SE 21 — `Type`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Type.html)
- [Java SE 21 — `ParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html)
- [Java SE 21 — `WildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/WildcardType.html)
- [Java SE 21 — `GenericArrayType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/GenericArrayType.html)
- [Java SE 21 — `TypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html)
- [Java Language Specification `4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html)
