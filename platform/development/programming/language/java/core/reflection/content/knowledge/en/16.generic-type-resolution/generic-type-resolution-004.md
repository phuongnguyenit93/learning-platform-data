# Thay thế kiểu lồng trong ParameterizedType bằng Java Reflection

Khi Reflection đọc một khai báo generic, kết quả thường vẫn chứa các biến kiểu như `T`, `U`, `V`, dù ta đang phân tích lớp con đã gắn chúng với các kiểu cụ thể. Ví dụ, field `Map<T, List<U[]>>` của một lớp lồng có thể cần được hiểu dưới ngữ cảnh thành `Map<String, List<Integer[]>>`. Đây là bài toán **generic type substitution**: lần theo quan hệ thừa kế và lớp sở hữu, xây ánh xạ từ `TypeVariable` tới `Type`, rồi thay thế **đệ quy** trong cây `Type`.

Điểm khó nhất là không chỉ thay `T` xuất hiện ở phần tử đầu tiên của `ParameterizedType`. Phải đi sâu vào từng `getActualTypeArguments()`, xử lý `GenericArrayType`, `WildcardType`, các ánh xạ nhiều bước và `getOwnerType()` của kiểu lồng như `Outer<String>.Inner<Integer>`. Bài học dưới đây phân biệt **đọc metadata**, **xây ngữ cảnh generic** và **tạo cấu trúc `Type` đã được thay thế**.

## 1. Các thành phần tạo nên cây `Type`

`java.lang.reflect.Type` là giao diện gốc cho những cách biểu diễn kiểu generic trong Reflection:

| Dạng `Type` | Ví dụ | API dùng để đi sâu |
| --- | --- | --- |
| `Class<?>` | `String.class`, `int.class`, `String[].class` | `getComponentType()` nếu là mảng |
| `ParameterizedType` | `List<T>`, `Map<String, List<U[]>>`, `Outer<T>.Inner<U>` | `getRawType()`, `getActualTypeArguments()`, `getOwnerType()` |
| `TypeVariable<?>` | `T`, `U`, `V` | `getGenericDeclaration()`, `getName()`, `getBounds()` |
| `WildcardType` | `? extends U`, `? super T` | `getUpperBounds()`, `getLowerBounds()` |
| `GenericArrayType` | `U[]`, `List<T>[]` ở khai báo kiểu tổng quát | `getGenericComponentType()` |

Với một field khai báo `Map<T, List<U[]>>`, `field.getType()` chỉ là `Map.class` do *type erasure*. Nhưng `field.getGenericType()` trả về cây `ParameterizedType` chứa `T` và một `ParameterizedType` con là `List<U[]>`. Phần `U[]` được mô tả bởi `GenericArrayType`, vì thành phần `U` chưa phải kiểu reifiable.

Dễ hình dung cấu trúc trước thay thế:

~~~text
ParameterizedType: Map<T, List<U[]>>
├── rawType: Map.class
├── arg[0]: TypeVariable T
└── arg[1]: ParameterizedType List<U[]>
    └── arg[0]: GenericArrayType
        └── component: TypeVariable U
~~~

Ngữ cảnh `T → String`, `U → Integer` sẽ biến nó thành:

~~~text
ParameterizedType: Map<String, List<Integer[]>>
├── rawType: Map.class
├── arg[0]: Class String
└── arg[1]: ParameterizedType List<Integer[]>
    └── arg[0]: Class Integer[] 
~~~

`Integer[]` lúc này là một `Class` đại diện mảng thật vì `Integer` là kiểu cụ thể. **Không bỏ qua các tầng lồng**: thay mỗi `arg[0]` ở cấp Map nhưng không đi vào `List<U[]>` thì vẫn còn biến `U` chưa được giải.

## 2. Vì sao không thể thay biến kiểu chỉ bằng tên?

Giả sử hai khai báo khác nhau đều tên `T`:

~~~java
class First<T> {}
class Second<T> {}
~~~

Hai biến kiểu ở đây **không cùng định danh**. Mỗi `TypeVariable` liên quan đến chính `GenericDeclaration` đã khai báo nó. Một method generic có `<T> void doWork(T value)` còn có thể có một biến `T` khác với biến `T` của lớp.

Do đó, nên dùng:

~~~java
Map<TypeVariable<?>, Type> bindings = new HashMap<>();
~~~

thay vì `Map<String, Type>` theo tên như `"T"`. Dùng `getTypeParameters()` từ đúng raw class để lấy khóa; dùng `getActualTypeArguments()` từ đúng `ParameterizedType` để lấy giá trị tương ứng.

**Không dùng `getSimpleName()`, `getTypeName()` hay thay chuỗi bằng regex** làm cơ chế phân giải kiểu. Các API ấy phục vụ biểu diễn tên; chúng không giữ đầy đủ identity của `TypeVariable`, raw type, owner type, mảng và wildcard.

## 3. Kiểu lồng có hai tầng tham số: owner và chính inner

Ví dụ:

~~~java
class Outer<T> {
    class Slot<U> {
        Map<T, List<U[]>> table;
    }
}
~~~

Ở một sử dụng cụ thể `Outer<String>.Slot<Integer>`:

- `T` thuộc về khai báo `Outer<T>`, nhận `String`.
- `U` thuộc về khai báo `Outer<T>.Slot<U>`, nhận `Integer`.
- `ParameterizedType` biểu diễn **Slot** có `getRawType() == Outer.Slot.class`.
- `getActualTypeArguments()` của **Slot** chỉ chứa `Integer` (biến `U`).
- **Tham số `String` cho `T` nằm trong `getOwnerType()`** — nó không bị gộp thành hai phần tử trong mảng đối số của Slot.

Đây là lỗi cơ bản khi xử lý kiểu lồng: chỉ duyệt `getActualTypeArguments()` mà bỏ `getOwnerType()` sẽ không tìm được ánh xạ `Outer.T → String`.

**Lưu ý:** các nested type `static` không giữ một instance của outer class theo cách của non-static inner class. Owner metadata của một `ParameterizedType` có thể vẫn biểu diễn enclosing type, nhưng không nên suy luận từ đó rằng static nested class sử dụng generic parameter của outer; static nested type không được tham chiếu biến kiểu của outer instance như một inner class non-static.

## 4. Phân giải qua nhiều cấp kế thừa

Xét chuỗi khai báo:

~~~java
class Outer<T> {
    class Slot<U> {}
}

class Middle<V> extends Outer<V>.Slot<Integer> {
    Middle(Outer<V> owner) {
        owner.super();
    }
}

class End extends Middle<String> {
    End() {
        super(new Outer<String>());
    }
}
~~~

**Ví dụ mã minh họa**, chỉ ra quan hệ kiểu. Lưu ý `owner.super()` là cú pháp gọi constructor của inner class không `static` từ subclass.

Các metadata quan trọng:

| Bước đọc | `Type` khai báo | Ánh xạ thu thập |
| --- | --- | --- |
| `End.class.getGenericSuperclass()` | `Middle<String>` | `Middle.V → String` |
| `Middle.class.getGenericSuperclass()` | `Outer<V>.Slot<Integer>` | `Outer.T → Middle.V`, `Slot.U → Integer` |
| Thay thế bắc cầu | `Outer.T → V → String` | `Outer.T → String`, `Slot.U → Integer` |

Không được dừng ở ánh xạ `T → V`; phải tiếp tục tra `V` trong ngữ cảnh. Vì `getGenericSuperclass()` trên `Middle.class` mô tả **khai báo của Middle**, nó vẫn chứa `V`, không tự biến thành `String` chỉ vì caller xuất phát từ `End.class`.

Quy trình chung cho class inheritance chain: bắt đầu ở kiểu đích cụ thể; duyệt từng `getGenericSuperclass()` từ dưới lên; với mỗi `ParameterizedType`, thu ánh xạ biến kiểu cho **raw type** và cả **owner** nếu có; sau đó thế biến đệ quy khi đọc field/method generic ở lớp khai báo ban đầu.

Nếu đường kế thừa liên quan **generic interface**, phải đọc thêm `getGenericInterfaces()` ở các nút liên quan. Các lớp dữ liệu hoặc thư viện có thể có nhiều đường interface; cần giữ quan hệ theo từng nhánh và phát hiện khi thông tin không được cung cấp đầy đủ.

## 5. Thuật toán thay thế đệ quy đúng cấu trúc

Cho `resolve(type, bindings)`:

1. Nếu `type` là `TypeVariable`, tra theo khóa `TypeVariable` và **tiếp tục resolve** kiểu ánh xạ. Nếu chưa có ánh xạ, giữ nguyên `TypeVariable`. Chặn chu trình ánh xạ để tránh đệ quy vô hạn.
2. Nếu là `ParameterizedType`, **resolve owner**, rồi resolve **mọi actual type argument** theo đúng thứ tự, giữ nguyên `rawType`; dựng một `ParameterizedType` mới bảo toàn cấu trúc.
3. Nếu là `GenericArrayType`, resolve component. Khi component là `Class<?>` cụ thể, có thể biểu diễn bằng array `Class` (chẳng hạn `Integer[].class`); nếu vẫn còn generic component, giữ dạng `GenericArrayType`.
4. Nếu là `WildcardType`, resolve cả `getUpperBounds()` và `getLowerBounds()` mà không xóa dấu `? extends` hoặc `? super`.
5. Với `Class<?>` bình thường, giữ nguyên nó. Một `Class<?>[]` hay `String[].class` đã là kiểu runtime có thật, không chứa `TypeVariable` để thay.

Để **trả về một `Type` thực sự**, không thể thay đổi đối tượng `ParameterizedType` mà Reflection cung cấp tại chỗ; cần dựng đối tượng khác triển khai `ParameterizedType`, `GenericArrayType`, `WildcardType` khi cần. Các implementation nên bất biến, có `equals`/`hashCode` nhất quán với hợp đồng của giao diện và trả mảng bản sao. Bên dưới là một implementation nhỏ dành cho học tập, dựa trên record của Java 17.

## 6. Chương trình Java 17+ đầy đủ: thay cả owner, nested arguments, array và wildcard

Tạo tệp **`NestedTypeSubstitutionDemo.java`**:

~~~java
import java.lang.reflect.*;
import java.util.*;

class Outer<T> {
    class Slot<U> {
        Map<T, List<U[]>> table;
        List<? extends U> upper;
    }
}

class Middle<V> extends Outer<V>.Slot<Integer> {
    Middle(Outer<V> outer) {
        outer.super();
    }
}

class End extends Middle<String> {
    End() {
        super(new Outer<String>());
    }
}

public class NestedTypeSubstitutionDemo {
    record P(Type owner, Type raw, List<Type> args)
            implements ParameterizedType {
        P { args = List.copyOf(args); }
        public Type getOwnerType() { return owner; }
        public Type getRawType() { return raw; }
        public Type[] getActualTypeArguments() {
            return args.toArray(Type[]::new);
        }
        public String getTypeName() { return describe(this); }
        @Override public String toString() { return getTypeName(); }
        @Override public boolean equals(Object other) {
            return other instanceof ParameterizedType p
                    && Objects.equals(owner, p.getOwnerType())
                    && Objects.equals(raw, p.getRawType())
                    && Arrays.equals(getActualTypeArguments(),
                                     p.getActualTypeArguments());
        }
        @Override public int hashCode() {
            return Arrays.hashCode(getActualTypeArguments())
                    ^ Objects.hashCode(owner) ^ Objects.hashCode(raw);
        }
    }

    record A(Type component) implements GenericArrayType {
        public Type getGenericComponentType() { return component; }
        public String getTypeName() { return describe(this); }
        @Override public String toString() { return getTypeName(); }
        @Override public boolean equals(Object other) {
            return other instanceof GenericArrayType a
                    && component.equals(a.getGenericComponentType());
        }
        @Override public int hashCode() { return component.hashCode(); }
    }

    record W(List<Type> upper, List<Type> lower)
            implements WildcardType {
        W {
            upper = List.copyOf(upper);
            lower = List.copyOf(lower);
        }
        public Type[] getUpperBounds() {
            return upper.toArray(Type[]::new);
        }
        public Type[] getLowerBounds() {
            return lower.toArray(Type[]::new);
        }
        public String getTypeName() { return describe(this); }
        @Override public String toString() { return getTypeName(); }
        @Override public boolean equals(Object other) {
            return other instanceof WildcardType w
                    && Arrays.equals(getUpperBounds(), w.getUpperBounds())
                    && Arrays.equals(getLowerBounds(), w.getLowerBounds());
        }
        @Override public int hashCode() {
            return Arrays.hashCode(getUpperBounds())
                    ^ Arrays.hashCode(getLowerBounds());
        }
    }

    static void bind(Type type, Map<TypeVariable<?>, Type> env) {
        if (!(type instanceof ParameterizedType p)) {
            return;
        }
        bind(p.getOwnerType(), env);
        TypeVariable<?>[] keys =
                ((Class<?>) p.getRawType()).getTypeParameters();
        Type[] values = p.getActualTypeArguments();
        for (int i = 0; i < keys.length; i++) {
            env.put(keys[i], values[i]);
        }
    }

    static Type substitute(Type type, Map<TypeVariable<?>, Type> env) {
        return substitute(type, env, new HashSet<>());
    }

    private static Type substitute(Type type,
            Map<TypeVariable<?>, Type> env,
            Set<TypeVariable<?>> visiting) {
        if (type instanceof TypeVariable<?> v) {
            Type replacement = env.get(v);
            if (replacement == null || replacement.equals(v)
                    || !visiting.add(v)) {
                return v;
            }
            try {
                return substitute(replacement, env, visiting);
            } finally {
                visiting.remove(v);
            }
        }
        if (type instanceof ParameterizedType p) {
            Type owner = p.getOwnerType() == null ? null
                    : substitute(p.getOwnerType(), env, visiting);
            List<Type> args = new ArrayList<>();
            for (Type arg : p.getActualTypeArguments()) {
                args.add(substitute(arg, env, visiting));
            }
            return new P(owner, p.getRawType(), args);
        }
        if (type instanceof GenericArrayType a) {
            Type child = substitute(
                    a.getGenericComponentType(), env, visiting);
            if (child instanceof Class<?> c) {
                return java.lang.reflect.Array.newInstance(c, 0)
                        .getClass();
            }
            return new A(child);
        }
        if (type instanceof WildcardType w) {
            List<Type> upper = new ArrayList<>();
            List<Type> lower = new ArrayList<>();
            for (Type t : w.getUpperBounds()) {
                upper.add(substitute(t, env, visiting));
            }
            for (Type t : w.getLowerBounds()) {
                lower.add(substitute(t, env, visiting));
            }
            return new W(upper, lower);
        }
        return type;
    }

    static String describe(Type t) {
        if (t instanceof ParameterizedType p) {
            Class<?> raw = (Class<?>) p.getRawType();
            String base = p.getOwnerType() == null
                    ? raw.getSimpleName()
                    : describe(p.getOwnerType()) + "."
                            + raw.getSimpleName();
            Type[] args = p.getActualTypeArguments();
            if (args.length == 0) return base;
            List<String> parts = new ArrayList<>();
            for (Type arg : args) parts.add(describe(arg));
            return base + "<" + String.join(", ", parts) + ">";
        }
        if (t instanceof GenericArrayType a) {
            return describe(a.getGenericComponentType()) + "[]";
        }
        if (t instanceof WildcardType w) {
            Type[] lower = w.getLowerBounds();
            if (lower.length > 0) {
                return "? super " + describe(lower[0]);
            }
            Type[] upper = w.getUpperBounds();
            if (upper.length == 0 || (upper.length == 1
                    && upper[0] == Object.class)) return "?";
            return "? extends " + describe(upper[0]);
        }
        if (t instanceof TypeVariable<?> v) return v.getName();
        if (t instanceof Class<?> c) {
            return c.isArray()
                    ? describe(c.getComponentType()) + "[]"
                    : c.getSimpleName();
        }
        return t.getTypeName();
    }

    public static void main(String[] args) throws NoSuchFieldException {
        Map<TypeVariable<?>, Type> env = new LinkedHashMap<>();

        Type endParent = End.class.getGenericSuperclass();
        bind(endParent, env); // V -> String
        Type middleParent = Middle.class.getGenericSuperclass();
        bind(middleParent, env); // T -> V, U -> Integer

        System.out.println("T -> " + describe(substitute(
                Outer.class.getTypeParameters()[0], env)));
        System.out.println("U -> " + describe(substitute(
                Outer.Slot.class.getTypeParameters()[0], env)));
        System.out.println("V -> " + describe(substitute(
                Middle.class.getTypeParameters()[0], env)));

        ParameterizedType nested = (ParameterizedType) middleParent;
        System.out.println("Owner: " + describe(
                substitute(nested.getOwnerType(), env)));
        System.out.println("Nested: " + describe(
                substitute(middleParent, env)));

        Field table = Outer.Slot.class.getDeclaredField("table");
        Type declared = table.getGenericType();
        Type resolved = substitute(declared, env);
        System.out.println("Raw field: " + table.getType().getSimpleName());
        System.out.println("Declared: " + declared.getTypeName());
        System.out.println("Resolved: " + describe(resolved));
        System.out.println("Nested argument: "
                + (((ParameterizedType) resolved)
                    .getActualTypeArguments()[1]
                    instanceof ParameterizedType));
        Type upper = Outer.Slot.class.getDeclaredField("upper")
                .getGenericType();
        System.out.println("Wildcard: "
                + describe(substitute(upper, env)));
    }
}
~~~

Biên dịch và chạy ở thư mục chứa tệp:

~~~bash
javac --release 17 NestedTypeSubstitutionDemo.java
java NestedTypeSubstitutionDemo
~~~

**Stdout:**

~~~text
T -> String
U -> Integer
V -> String
Owner: Outer<String>
Nested: Outer<String>.Slot<Integer>
Raw field: Map
Declared: java.util.Map<T, java.util.List<U[]>>
Resolved: Map<String, List<Integer[]>>
Nested argument: true
Wildcard: List<? extends Integer>
~~~

`describe(Type)` của ví dụ **cố ý dùng `Class#getSimpleName()`** để hiển thị gọn; vì vậy chuỗi `Resolved: Map<String, List<Integer[]>>` không in `java.util.` hoặc `java.lang.`. Trong hệ thống cần định danh duy nhất hoặc ghi cache bền vững, dùng cấu trúc `Type` và `Class` thay vì dựa vào chuỗi rút gọn này.

### Điều cần nhận ra trong kết quả

- **`T → String`**: đi qua `End → Middle<String>` rồi `Outer<V>`, nên có ánh xạ bắc cầu.
- **`U → Integer`**: nhận trực tiếp từ type argument của `Slot<Integer>`.
- **`Owner: Outer<String>`**: chứng minh thuật toán không quên `getOwnerType()`.
- **`Nested: Outer<String>.Slot<Integer>`**: vừa thay owner, vừa thay argument của inner type.
- **`Raw field: Map`**: `Field#getType()` đã mất các argument do type erasure.
- **`Declared: java.util.Map<T, java.util.List<U[]>>`**: `Field#getGenericType()` phản ánh khai báo, chưa tự biết `End`.
- **`Resolved: Map<String, List<Integer[]>>`**: thuật toán vào sâu qua `Map`, `List`, `GenericArrayType`, rồi thay `U` bằng `Integer`.
- **`Nested argument: true`**: kết quả vẫn có argument `ParameterizedType` thực sự ở cấp `List<...>`; không bị rút thành một chuỗi.
- **`Wildcard: List<? extends Integer>`**: wildcard vẫn giữ toán tử bound; biến kiểu nằm trong upper bound được thay.

### Vì sao có ba record `P`, `A`, `W`?

Chúng là những implementation `Type` **dành cho bài tập**, không thuộc các lớp public JDK cung cấp để dựng `ParameterizedType` bất kỳ:

- `P` lưu owner, raw type và arguments, triển khai `ParameterizedType`.
- `A` giữ generic array component khi component chưa phải `Class<?>.`
- `W` giữ upper/lower bounds của wildcard.
- `List.copyOf` và `toArray(Type[]::new)` tránh cho caller chỉnh mảng/lists nội bộ.
- `equals`/`hashCode` so sánh các thành phần theo hợp đồng phản chiếu; phần hiển thị `getTypeName()` sử dụng `describe` riêng.

Các implementation ở ví dụ phù hợp với mục tiêu học tập và kiểu generic mà Java source có thể tạo ra. Framework production cần thêm kiểm tra invariant (raw type thực sự phù hợp, số lượng argument hợp lệ, owner hợp lệ, bounds không null/sai cấu trúc), chính sách cache, mô hình phân giải đa nhánh và kiểm thử với các dạng kiểu phức tạp khác.

## 7. Dùng `ParameterizedType` đúng cách sau khi thay thế

Một `ParameterizedType` đã được giải có thể kiểm tra bằng API thay vì tách chuỗi:

~~~java
ParameterizedType mapType = (ParameterizedType) resolved;
Type key = mapType.getActualTypeArguments()[0];
Type list = mapType.getActualTypeArguments()[1];

System.out.println(key == String.class); // true
System.out.println(list instanceof ParameterizedType); // true
~~~

Đây là **đoạn mã minh họa** đặt sau phần tạo biến `resolved` trong chương trình chính, với import `java.lang.reflect.*`. Chúng là các đối tượng `Type`, nên có thể tiếp tục đọc raw type, owner, arguments; không cần parse `getTypeName()`.

Kiểm tra generic array sau thay thế:

~~~java
ParameterizedType listType = (ParameterizedType) list;
Type arrayArg = listType.getActualTypeArguments()[0];
System.out.println(arrayArg == Integer[].class); // true
~~~

Sau khi `U` được giải thành `Integer.class`, mảng `U[]` được biểu diễn bằng `Integer[].class`. Nếu component vẫn là một tham số kiểu chưa giải, `GenericArrayType` tiếp tục là biểu diễn phù hợp.

**Không hiểu `substitute` là thay đổi khai báo Java hay bytecode.** `Field#getGenericType()` trên trường `Outer.Slot.table` vẫn trả metadata `Map<T, List<U[]>>`; đối tượng `Type` mới chỉ là **kết quả diễn giải dưới ngữ cảnh** mà chương trình xây dựng. Bản thân `Outer<T>`, `Slot<U>` và các đối tượng runtime không bị sửa.

## 8. Những kiểu lồng khác cần xét

### 8.1. Nested `ParameterizedType` trong collection

Ví dụ `Map<String, List<Map<T, U>>>`. Nếu chỉ duyệt một tầng, `T` và `U` nằm tận bên trong `Map<T,U>` sẽ vẫn chưa được thay. Quy tắc đúng là **duyệt mọi phần tử của `getActualTypeArguments()` rồi gọi cùng thuật toán đệ quy**.

### 8.2. Generic wildcard ở nhiều mức

`List<? extends U>` sử dụng `WildcardType` ở argument của `List`. `Map<? super T, ? extends List<U>>` có thể chứa cả lower bound và upper bound. Cần đi vào `getLowerBounds()` và `getUpperBounds()`, không chuyển wildcard thành kiểu bound trực tiếp; `? extends Integer` **không phải** cùng một khai báo với `Integer`.

### 8.3. Generic array trong argument

`U[]` khác `List<U>`. Khi đang generic, nó có thể là `GenericArrayType`; khi `U` thành `Integer`, kết quả có thể là `Class` của mảng `Integer[].class`. Nếu `U` lại thay bằng một `ParameterizedType` như `List<String>`, một mảng `List<String>[]` cần được giữ dạng `GenericArrayType`, vì không có `Class` reifiable cho `List<String>[]`.

### 8.4. Static nested type và owner

Một static nested class không sử dụng generic parameter của enclosing instance theo cách của non-static inner class. Cần đọc metadata thực tế từ `getOwnerType()` và `getActualTypeArguments()`, tránh "điền" type arguments của enclosing class theo phỏng đoán. `ownerType` không đồng nghĩa với instance reference hay một argument generic mới của raw inner class.

### 8.5. `TypeVariable` khai báo ở method

Một generic method như `<X> X convert(X input)` có `X` khai báo trên chính `Method`, không phải parameter của class. Ánh xạ xây chỉ từ superclass **không tự giải được `X`**. Cần ngữ cảnh riêng (ví dụ chữ ký method và type inference của framework) nếu thật sự có đủ thông tin. Nếu không, giữ `TypeVariable` chưa giải là kết quả đúng hơn tự đoán `Object`.

## 9. Giới hạn quan trọng: type erasure và ngữ cảnh sẵn có

Reflection không thể suy ra mọi tham số generic từ một **instance runtime**.

Ví dụ hai object được tạo từ:

~~~java
// Minh họa; không phải đoạn chương trình độc lập.
List<String> a = new ArrayList<>();
List<Integer> b = new ArrayList<>();
~~~

Cả `a.getClass()` và `b.getClass()` đều có thể là `ArrayList.class`; type arguments `String` và `Integer` không lưu trên instance theo cách Reflection có thể tự khôi phục. Nếu có generic field ở một subclass cụ thể hoặc interface/superclass được parameterize trong khai báo, Reflection mới có metadata cần thiết.

Chính vì vậy ví dụ dùng **`class End extends Middle<String>`**: khai báo superclass của `End` giữ `String`, khai báo của `Middle` giữ `Outer<V>.Slot<Integer>`. Hai liên kết này cung cấp đủ ngữ cảnh để giải `T` và `U`.

Nếu một đường kiểu bị sử dụng dưới dạng **raw type**, một số tham số có thể không còn ánh xạ cụ thể. Đừng coi `null`/thiếu mapping là bằng chứng biến kiểu phải được thay bằng `Object` theo mọi trường hợp. Giữ unresolved `TypeVariable` hoặc biểu diễn bounds rõ ràng, tùy mục đích API.

## 10. Tránh năm lỗi thiết kế thường gặp

| Sai lầm | Tác hại | Cách sửa |
| --- | --- | --- |
| `Map<String, Type>` với khóa `"T"` | Gộp các `T` của lớp/method không liên quan | Dùng `Map<TypeVariable<?>, Type>` |
| Chỉ duyệt arguments tầng ngoài của `ParameterizedType` | Bỏ lại `List<U[]>` hoặc `Map<T, U>` chưa giải | Resolve đệ quy mọi argument |
| Bỏ `getOwnerType()` | Mất ánh xạ `Outer.T` trong `Outer<T>.Inner<U>` | Bind/resolve owner trước hoặc đồng thời với inner |
| Thế `T → V` một lần rồi dừng | Không tới `V → String` ở supertype gần hơn | Resolve bắc cầu kèm phát hiện chu trình |
| Ép mọi `Type` về `Class` | Mất wildcard, parameterization và generic array | Phân nhánh theo các giao diện `Type` tương ứng |

Ngoài ra, khi tạo `ParameterizedType` tùy chỉnh, **đừng chỉ override `toString()`** rồi coi nó là type resolver. Phải lưu và trả về đúng raw type, owner, arguments, bảo toàn cấu trúc và thực hiện `equals`/`hashCode` phù hợp. Chuỗi hiển thị không thay cho thông tin kiểu thực.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Với `Outer<String>.Inner<Integer>`, tại sao `inner.getActualTypeArguments()` không bắt buộc chứa cả `String` và `Integer`?

**Đáp án:** `String` nằm trong metadata của **owner** `Outer<String>`, còn `getActualTypeArguments()` của `Inner<Integer>` chứa argument `Integer` tương ứng biến kiểu do chính `Inner` khai báo.

**Câu 2.** Từ `Map<T, List<U[]>>`, nếu `T → String`, `U → Integer`, kết quả sau khi thay đầy đủ là gì?

**Đáp án:** `Map<String, List<Integer[]>>`. Phải duyệt nested `List` và `GenericArrayType` của `U[]`.

**Câu 3.** Vì sao không dùng `Map<String, Type>` để lưu ánh xạ cho các biến tên `T`?

**Đáp án:** Những biến cùng tên có thể được khai báo bởi các `GenericDeclaration` khác nhau. Khóa đúng là đối tượng `TypeVariable`, không phải riêng chuỗi tên.

**Câu 4.** Cho `End extends Middle<String>`, `Middle<V> extends Outer<V>.Slot<Integer>`. Phải đi qua mấy lớp ánh xạ để giải `Outer.T`?

**Đáp án:** Hai liên kết: `Outer.T → Middle.V` và `Middle.V → String`; kết quả `Outer.T → String`.

**Câu 5.** Nếu một wildcard là `? extends U` và `U → Integer`, ta có nên bỏ dấu `?` không?

**Đáp án:** Không. Kết quả là `? extends Integer`, vẫn là `WildcardType`, không phải `Integer` đơn thuần.

**Câu 6.** `field.getGenericType()` có tự đổi thành kiểu đã thay thế sau khi gọi utility resolver không?

**Đáp án:** Không. Resolver chỉ tạo một `Type` mô tả cách hiểu metadata dưới ngữ cảnh riêng; nó không sửa khai báo field hoặc bytecode lớp.

**Câu 7.** Có thể tìm type argument `String` chỉ từ `new ArrayList<String>().getClass()` không?

**Đáp án:** Không. `getClass()` trả `ArrayList.class`, còn tham số của biểu thức tạo instance thường bị xóa ở runtime; cần thông tin từ khai báo generic có lưu signature.

## 12. Tổng kết quy trình

Khi phải giải một kiểu lồng trong `ParameterizedType`: bắt đầu bằng một kiểu cụ thể còn lưu chữ ký generic, **theo dõi chuỗi superclass/interface và owner**, ánh xạ các `TypeVariable` đúng identity, rồi **resolve đệ quy** trên `ParameterizedType`, `GenericArrayType` và `WildcardType`. Sau đó kiểm tra kết quả bằng API `Type` thay vì chỉ bằng chuỗi.

Trong ví dụ, chính việc ghép `Middle.V → String`, `Outer.T → V` và `Slot.U → Integer` cho phép biến field khai báo `Map<T, List<U[]>>` thành cây `Type` biểu diễn `Map<String, List<Integer[]>>` mà không mất owner hay các tầng lồng.
