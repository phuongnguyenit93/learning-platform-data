# 4.5. Xử lý WildcardType, GenericArrayType và giới hạn của type erasure

> **Bối cảnh:** Trong module *Java Advance – dynamic-runtime*, nhóm **4. Siêu dữ liệu**, bài này tập trung vào cách đọc và diễn giải chữ ký generic bằng Reflection trong Java 21. Hai trường hợp cần xử lý cẩn thận là **`WildcardType`** và **`GenericArrayType`**. Ta cũng cần hiểu chính xác thông tin nào còn trong metadata của một khai báo và thông tin nào bị **type erasure** loại bỏ ở runtime. Các ví dụ chạy với JDK 21, không dùng thư viện ngoài.

## 1. Mục tiêu và kiến thức đầu vào

Sau bài này, bạn cần làm được những việc sau:

1. Nhận diện đúng năm dạng phổ biến của `java.lang.reflect.Type`: `Class<?>`, `ParameterizedType`, `TypeVariable<?>`, `WildcardType` và `GenericArrayType`.
2. Đọc được giới hạn trên (`getUpperBounds()`) và giới hạn dưới (`getLowerBounds()`) của wildcard, kể cả trường hợp `?` không khai báo bounds.
3. Tách được component của mảng generic theo `GenericArrayType.getGenericComponentType()` và phân biệt nó với một array type được biểu diễn bởi `Class<?>`.
4. Giải thích type erasure theo quy tắc JLS, xác định tại sao `getGenericType()` có thể cung cấp chữ ký generic của *khai báo* trong khi `getType()` chỉ cung cấp kiểu sau erasure.
5. Viết code Reflection kiểm tra `instanceof` trước khi ép kiểu `Type`, duyệt cấu trúc generic lồng nhau và không giả định có thể truy ngược tham số kiểu chỉ từ một object.
6. Chỉ ra cách subclass/type reference lưu dấu generic declaration, các giới hạn của nó, và bridge methods do compiler tạo ra.

**Cần biết trước:** Java generics (`List<T>`, `? extends T`, `? super T`), arrays, Reflection cơ bản (`Class`, `Field`, `Method`), phương thức generic và cách chạy chương trình bằng `javac`/`java`.

## 2. Mô hình `Type`: nhìn metadata như một cây

`Type` là một interface của `java.lang.reflect`. Kết quả từ Reflection không nhất thiết là một `Class<?>`. Mô hình nền tảng:

```text
java.lang.reflect.Type
  ├── Class<?>             : String, int, String[], List (raw)
  ├── ParameterizedType    : List<String>, Map<String, Integer>
  ├── TypeVariable<?>      : T trong class/method <T extends Number>
  ├── WildcardType         : ?, ? extends Number, ? super Integer
  └── GenericArrayType    : T[], List<String>[]
```

Một ví dụ khai báo đa tầng:

```java
// Đoạn khai báo minh họa; đặt bên trong class có import java.util.Map và List.
Map<String, List<? extends Number>[]> payload;
```

Khi truy cập `Field.getGenericType()`, Reflection nhìn thấy cấu trúc tương đương:

```text
ParameterizedType: Map<..., ...>
  ├── Class: String
  └── GenericArrayType: List<? extends Number>[]
      └── ParameterizedType: List<...>
          └── WildcardType: ? extends Number
              └── upper bound: Class Number
```

**Bài học quan trọng:** Không gọi trực tiếp `(Class<?>) field.getGenericType()`. Tùy khai báo, phép ép có thể gây `ClassCastException`. Phân nhánh theo loại thực tế rồi đi vào children.

| Nơi đọc | API | Kết quả cần hiểu |
| --- | --- | --- |
| Field | `Field.getType()` | `Class<?>` của kiểu sau erasure: `List<String>` → `List.class`, `T[]` → array của bound bị erase. |
| Field | `Field.getGenericType()` | Một `Type`, có thể là `ParameterizedType`, `GenericArrayType`, `TypeVariable`, `Class<?>`. |
| Method | `Method.getReturnType()` / `getGenericReturnType()` | Kiểu trả về erased so với khai báo generic. |
| Method | `Method.getParameterTypes()` / `getGenericParameterTypes()` | Mảng các `Class<?>` đã erase so với mảng `Type` generic. |
| Class | `getSuperclass()` / `getGenericSuperclass()` | Superclass erased so với generic declaration của superclass. |
| Class | `getInterfaces()` / `getGenericInterfaces()` | Interfaces erased so với generic declarations. |
| Generic declaration | `Class.getTypeParameters()` hoặc `Method.getTypeParameters()` | `TypeVariable<?>[]` mô tả **định nghĩa** của tham số kiểu, không phải kiểu được một instance gắn vào. |

`Type.getTypeName()` hữu ích cho log. Với class array, `Class.getName()` có thể cho định dạng JVM như `[Ljava.lang.String;`, còn `getTypeName()` phù hợp để trình bày dạng `java.lang.String[]`. Khi dùng `ParameterizedType`, `getRawType()` thường là `Class<?>`; `getActualTypeArguments()` trả một mảng `Type[]` mà từng phần tử có thể lại là generic type khác. `getOwnerType()` đáng quan tâm khi gặp nested/member classes.

## 3. `WildcardType`: xử lý `?`, `extends` và `super`

Wildcard diễn đạt một **kiểu chưa xác định cụ thể** ở vị trí type argument. Nó khác với `TypeVariable` được **khai báo có tên** như `T` trong `class Box<T>`.

| Khai báo | Runtime node của argument | `getUpperBounds()` | `getLowerBounds()` |
| --- | --- | --- | --- |
| `List<?>` | `WildcardType` | `[Object]` | `[]` |
| `List<? extends Number>` | `WildcardType` | `[Number]` | `[]` |
| `List<? super Integer>` | `WildcardType` | `[Object]` | `[Integer]` |
| `List<String>` | `Class<?>` argument `String.class` | Không phải `WildcardType` | Không phải `WildcardType` |
| `List<T>` | `TypeVariable<?>` argument `T` | Dùng `getBounds()` của `TypeVariable` | Không phải lower-bound wildcard |

Cách đọc giới hạn:

- **`? extends Number`:** kiểu chưa biết là một subtype nào đó của `Number`. Dùng `getUpperBounds()`; lower bounds trống.
- **`? super Integer`:** kiểu chưa biết là `Integer` hoặc một supertype của nó. Dùng `getLowerBounds()`; upper bound mặc định là `Object`.
- **`?`:** không khai báo upper/lower bound, nên upper bound mặc định `Object` và mảng lower bound **rỗng**.
- **`T extends Number & Comparable<T>`:** đây là `TypeVariable`, và `getBounds()` có thể chứa **nhiều** upper bounds, một trong số đó là `ParameterizedType`; không trộn lẫn với wildcard.

API trả **mảng `Type[]`**, không trả trực tiếp `Class<?>` hoặc một chuỗi. Không viết `wildcard.getLowerBounds()[0]` trước khi kiểm tra độ dài. Theo cú pháp Java hiện tại, một wildcard thường có tối đa một bound ở mỗi phía, nhưng hãy xử lý toàn bộ phần tử mà API trả về để tránh giả định cứng.

### 3.1. PECS và hành vi đọc/ghi

PECS (*Producer Extends, Consumer Super*) giải thích vì sao wildcard này hữu ích trong mã nguồn:

- `List<? extends Number>`: đọc phần tử như `Number` được; không thể thêm một `Integer`/`Double` bất kỳ vì element type thật có thể là một subtype khác (thêm `null` là trường hợp đặc biệt được phép).
- `List<? super Integer>`: có thể thêm `Integer`; đọc lại theo kiểu an toàn chung là `Object`.
- `List<?>`: đọc như `Object`; không thêm phần tử non-null tùy ý.

Đây là **quy tắc kiểm tra kiểu khi biên dịch**. Reflection trả metadata mô tả quy tắc ấy, nhưng không biến generic element type thành một runtime check tự động cho từng phần tử.

## 4. `GenericArrayType`: khi component chưa phải kiểu reifiable đầy đủ

Mảng có component là **parameterized type** hoặc **type variable** trong generic declaration thường được biểu diễn bởi `GenericArrayType`:

| Khai báo field | `getGenericType()` là | Component đọc bằng |
| --- | --- | --- |
| `String[] texts;` | `Class<?>` (array class) | `((Class<?>) type).getComponentType()` |
| `int[][] matrix;` | `Class<?>` (array class) | Lặp `Class.getComponentType()` tới phần tử cuối |
| `T[] values;` | `GenericArrayType` | `getGenericComponentType()` → `TypeVariable<?>` |
| `List<String>[] groups;` | `GenericArrayType` | `getGenericComponentType()` → `ParameterizedType` của `List<String>` |
| `List<?>[] groups;` | `GenericArrayType` trong metadata khai báo của field | `getGenericComponentType()` → `ParameterizedType` có wildcard argument |

Phân biệt rõ **khai báo một biến có kiểu mảng generic** và **tạo một mảng**:

- `List<String>[] groups;` là một khai báo field/biến **hợp lệ**.
- `new List<String>[3]` là **lỗi biên dịch** (*generic array creation*): component `List<String>` không reifiable.
- `new T[3]` cũng không được phép khi `T` là type variable thông thường.
- `List<?>[] slots = new List<?>[3];` được phép, vì `List<?>` là dạng reifiable theo JLS.
- `String[] strings = new String[3];` hoạt động vì `String` reifiable và runtime array biết component là `String.class`.

**Vì sao?** Arrays mang runtime component type và có kiểm tra khi gán phần tử; generic type arguments thông thường bị erase. Nếu cho phép `new List<String>[n]` trong khi array covariance vẫn hoạt động, sẽ dễ phá vỡ giả định kiểm tra kiểu của phần tử generic. `GenericArrayType` chỉ là **mô tả kiểu ở metadata**, không phải một đối tượng array thực để cấp phát.

`java.lang.reflect.Array.newInstance(Class<?> component, int length)` chỉ nhận runtime `Class<?>` của component. Nó không thể tạo một `List<String>[]` có runtime enforcement cho tham số `String` chỉ từ `ParameterizedType`. Nếu dùng unchecked cast cho generic array, phải hiểu rõ và giới hạn miền tin cậy của dữ liệu.

**Mảng nhiều chiều:** với `T[][]`, `GenericArrayType.getGenericComponentType()` có thể tiếp tục là một `GenericArrayType` khác; cần đệ quy cho đến `TypeVariable`. Với `String[][]`, outer type vẫn là `Class<?>` và có thể dùng `getComponentType()` nhiều lần.

## 5. Lab 1: đọc bounds và generic array bằng Reflection

Tạo file **`TypeInspectionLab.java`**:

```java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public final class TypeInspectionLab<T extends Number & Comparable<T>> {
    private List<? extends Number> source;
    private List<? super Integer> target;
    private List<?> unknown;
    private List<String>[] listArray;
    private T[] genericArray;
    private String[] ordinaryArray;

    private static String names(Type[] bounds) {
        return Arrays.stream(bounds)
                .map(Type::getTypeName)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    private static void inspect(String name) throws NoSuchFieldException {
        Type type = TypeInspectionLab.class.getDeclaredField(name).getGenericType();
        if (type instanceof ParameterizedType parameterized) {
            Type[] arguments = parameterized.getActualTypeArguments();
            if (arguments.length == 1 && arguments[0] instanceof WildcardType wildcard) {
                System.out.println(name + ": upper=" + names(wildcard.getUpperBounds())
                        + ", lower=" + names(wildcard.getLowerBounds()));
            }
        } else if (type instanceof GenericArrayType array) {
            System.out.println(name + ": generic array of "
                    + array.getGenericComponentType().getTypeName());
        } else if (type instanceof Class<?> arrayClass && arrayClass.isArray()) {
            System.out.println(name + ": ordinary array of "
                    + arrayClass.getComponentType().getTypeName());
        }
    }

    public static void main(String[] args) throws NoSuchFieldException {
        inspect("source");
        inspect("target");
        inspect("unknown");
        inspect("listArray");
        inspect("genericArray");
        inspect("ordinaryArray");
        TypeVariable<?> variable = TypeInspectionLab.class.getTypeParameters()[0];
        System.out.println("T bounds=" + names(variable.getBounds()));
    }
}
```

Biên dịch/chạy trong thư mục chứa file, bằng **JDK 21**:

```sh
javac --release 21 -Xlint:all TypeInspectionLab.java
java TypeInspectionLab
```

**Stdout chính xác:**

```text
source: upper=[java.lang.Number], lower=[]
target: upper=[java.lang.Object], lower=[java.lang.Integer]
unknown: upper=[java.lang.Object], lower=[]
listArray: generic array of java.util.List<java.lang.String>
genericArray: generic array of T
ordinaryArray: ordinary array of java.lang.String
T bounds=[java.lang.Number, java.lang.Comparable<T>]
```

### 5.1. Giải thích kết quả

1. `getDeclaredField(name).getGenericType()` đọc chữ ký field từ **khai báo** trong class file. Không cần tạo instance của `TypeInspectionLab` hoặc khởi tạo giá trị field.
2. `List<? extends Number>` là `ParameterizedType` với raw type `List` và argument là `WildcardType` có upper bound `Number`.
3. `List<? super Integer>` có lower bound `Integer`, upper bound mặc định `Object`. `List<?>` có upper bound mặc định `Object` và lower array rỗng.
4. `List<String>[]` có component là `ParameterizedType`; `T[]` có component là `TypeVariable<?>`. Không được cast hai dạng đó thành `Class<?>`.
5. `String[]` là reifiable array class, nên nhánh `Class<?> && isArray()` dùng `getComponentType()`.
6. `T extends Number & Comparable<T>` giữ **hai bound trong generic declaration**. Đây không phải hai bound của một wildcard; đó là thông tin của `TypeVariable`.

**Một giới hạn có chủ ý của lab:** hàm `inspect` chỉ in dạng field đã biết trong bài. Ở code xử lý metadata tổng quát, bạn cần duyệt đệ quy các generic arguments và array components, không mặc định field có đúng một type argument.

## 6. Lab 2: wildcard dùng trong code khác metadata wildcard

Tạo **`WildcardUseLab.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public final class WildcardUseLab {
    static void addScores(List<? super Integer> destination) {
        destination.add(7);
        destination.add(5);
    }

    static int sum(List<? extends Number> source) {
        int total = 0;
        for (Number n : source) {
            total += n.intValue();
        }
        return total;
    }

    public static void main(String[] args) {
        List<Number> scores = new ArrayList<>();
        addScores(scores);
        System.out.println("sum=" + sum(scores));
    }
}
```

```sh
javac --release 21 -Xlint:all WildcardUseLab.java
java WildcardUseLab
```

**Stdout:**

```text
sum=12
```

`? super Integer` cho phép `addScores` nhận `List<Integer>` hoặc `List<Number>` và ghi `Integer` vào đó. `? extends Number` cho phép `sum` đọc phần tử như `Number`. Dù `List<Number>` có thể truyền vào cả hai, **`List<Integer>` không phải subtype của `List<Number>`**: generic types của Java về cơ bản bất biến (*invariant*), wildcard tạo giới hạn sử dụng theo phương sai.

Bằng Reflection, `Method.getGenericParameterTypes()` có thể đọc chữ ký `List<? super Integer>` và `List<? extends Number>` tương ứng từ khai báo. Ngược lại, `Method.getParameterTypes()` sẽ cho kiểu parameter sau erasure là `List.class` đối với mỗi phương thức (mỗi phương thức ở đây có tên khác nhau nên không xung đột).

## 7. Type erasure: dữ liệu nào còn, dữ liệu nào mất?

Java generics có **type erasure**: phần lớn type arguments dùng để kiểm tra kiểu tại **compile time**, sau đó nhiều vị trí trong bytecode sử dụng kiểu erased. Theo JLS `4.6:

| Kiểu trong mã nguồn | Erasure |
| --- | --- |
| `List<String>` | `List` |
| `Map<String, List<Integer>>` | `Map` |
| `T` khi `<T>` không giới hạn | `Object` |
| `T` khi `<T extends Number>` | `Number` |
| `T` khi `<T extends Number & Comparable<T>>` | `Number` (leftmost bound) |
| `T[]` | Mảng của kiểu erased của `T`, ví dụ `Number[]` |
| `List<String>[]` | `List[]` (runtime component không mang argument `String`) |

Erasure **không có nghĩa** Java xóa mọi dấu vết generics trong class file. Compiler thường lưu **generic signatures của khai báo** (field, method, superclass/interface, type parameters), và Reflection có API `getGeneric...` để đọc lại phần metadata đó. Tuy nhiên, đối tượng `new ArrayList<String>()` tự nó **không mang** một runtime class riêng cho `ArrayList<String>`. Bạn cũng không thể suy ra `String` chỉ bằng `list.getClass()`.

Hai mệnh đề phải cùng đúng:

- `getGenericType()` của một field được khai báo `List<String>` có thể trả `ParameterizedType` mô tả `List<String>`, vì đó là **thông tin ở vị trí khai báo**.
- `getClass()` của một instance `ArrayList<String>` và `ArrayList<Integer>` trả cùng runtime class `ArrayList` (trong ví dụ dùng class thật giống nhau), vì type argument không được reify thành hai class khác nhau.

**Các phép không hợp lệ tại compile time:**

- `List<String>.class` (không có class literal cho concrete generic instantiation).
- `value instanceof List<String>` (không kiểm tra được argument `String` ở runtime; `instanceof List<?>` được phép).
- `new List<String>[2]` (generic array creation không hợp lệ).
- Khai báo hai overload chỉ khác `List<String>` với `List<Integer>` ở cùng vị trí tham số, vì sau erasure chúng có cùng method signature.

### 7.1. Rủi ro heap pollution

`List<String>` không tự kiểm tra mỗi element chứa `String` ở runtime. Nếu một raw/unchecked path chèn `Integer` vào cấu trúc mà client tưởng là `List<String>`, lỗi `ClassCastException` có thể xuất hiện **muộn khi đọc phần tử và compiler chèn cast**. Generics cũng không cho phép bạn dùng `getClass()` để thực thi một validator đầy đủ dựa trên nested type arguments.

Arrays thì khác: runtime vẫn biết component class của `String[]` nên một phép ghi kiểu sai qua alias `Object[]` có thể ném `ArrayStoreException`. Sự khác biệt giữa **array covariance + runtime component check** và **generic invariance + erasure** giải thích nhiều quy tắc khó nhớ về generic arrays và unchecked conversions.

Khi xử lý dữ liệu ngoài (JSON, plugin payload, RPC), metadata generic là **schema/hint**, không phải bằng chứng rằng object hiện tại thực sự chứa element đúng kiểu. Nếu cần tính đúng đắn, kiểm tra cấu trúc dữ liệu và giá trị ở ranh giới tin cậy.

## 8. Lab 3: đối chiếu generic declaration và runtime class

Tạo **`ErasureLab.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.List;

public final class ErasureLab {
    static class Holder<T extends Number> {
        T item;
        List<String> names;
    }

    static final class IntegerHolder extends Holder<Integer> { }

    static abstract class TypeRef<T> {
        private final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType parameterized)) {
                throw new IllegalStateException("Missing type argument");
            }
            type = parameterized.getActualTypeArguments()[0];
        }

        Type type() {
            return type;
        }
    }

    public static void main(String[] args) throws NoSuchFieldException {
        Class<?> stringListClass = new ArrayList<String>().getClass();
        Class<?> integerListClass = new ArrayList<Integer>().getClass();
        System.out.println("same runtime class: " + (stringListClass == integerListClass));

        Field item = Holder.class.getDeclaredField("item");
        Field names = Holder.class.getDeclaredField("names");
        System.out.println("item generic: " + item.getGenericType().getTypeName());
        System.out.println("item runtime: " + item.getType().getTypeName());
        System.out.println("names generic: " + names.getGenericType().getTypeName());
        System.out.println("names runtime: " + names.getType().getTypeName());

        ParameterizedType parent =
                (ParameterizedType) IntegerHolder.class.getGenericSuperclass();
        System.out.println("subclass argument: "
                + parent.getActualTypeArguments()[0].getTypeName());

        Type captured = new TypeRef<List<String>>() { }.type();
        System.out.println("captured: " + captured.getTypeName());
    }
}
```

```sh
javac --release 21 -Xlint:all ErasureLab.java
java ErasureLab
```

**Stdout chính xác:**

```text
same runtime class: true
item generic: T
item runtime: java.lang.Number
names generic: java.util.List<java.lang.String>
names runtime: java.util.List
subclass argument: java.lang.Integer
captured: java.util.List<java.lang.String>
```

### 8.1. Phân tích điều gì được bảo tồn

- Hai `ArrayList` có cùng `Class<?>`; không có `Class<List<String>>` riêng để tra cứu từ instance.
- `Holder.item` khai báo `T extends Number`: `Field.getGenericType()` cho `T`, trong khi `Field.getType()` cho `Number.class` vì erasure của `T` là bound đầu tiên.
- `Holder.names` khai báo cụ thể `List<String>`: generic signature đọc được tham số `String`, còn runtime field type chỉ là `List`.
- `IntegerHolder extends Holder<Integer>` đưa **cụ thể hóa `Integer` vào supertype declaration**, nên `getGenericSuperclass()` thấy argument đó.
- `new TypeRef<List<String>>() { }` tạo một **anonymous subclass** có generic superclass chứa `List<String>` trong metadata. `TypeRef` đọc signature của **subclass**, không suy đoán kiểu từ `ArrayList` ở bên trong object.

Đây là cơ chế nền tảng của nhiều kiểu *type token/type reference* trong thư viện. Nó hoạt động khi lập trình viên **cố ý ghi một generic type vào khai báo kế thừa**. Nếu chỉ có một object không lưu generic argument ở bất kỳ signature đáng tin cậy nào, API Reflection chuẩn **không thể khôi phục** argument đã mất do erasure.

**Giới hạn thêm:** field `List<T>` trong một generic base class vẫn mô tả chữ `T` khi gọi `getGenericType()` trực tiếp trên field đó. Nếu một subclass gắn `T = Integer`, bộ xử lý metadata cần xây phép ánh xạ `TypeVariable → Type` theo đường kế thừa, chứ không thể mặc định `Field.getGenericType()` sẽ tự thay `T` bằng `Integer` trong mọi ngữ cảnh.

## 9. Bridge method: một hệ quả khi override generic

Type erasure đôi khi khiến compiler tạo thêm **bridge method** để giữ đúng đa hình ở mức bytecode. Khi dùng Reflection để duyệt method, đừng mặc định mọi method bạn thấy đều là method viết trực tiếp trong source.

Tạo **`BridgeLab.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

public final class BridgeLab {
    static class Parent<T> {
        T get() { return null; }
    }

    static final class Child extends Parent<String> {
        @Override String get() { return "ok"; }
    }

    public static void main(String[] args) {
        Arrays.stream(Child.class.getDeclaredMethods())
                .filter(m -> m.getName().equals("get"))
                .sorted(Comparator.comparing(Method::isBridge))
                .forEach(m -> System.out.println(m.getReturnType().getSimpleName()
                        + " bridge=" + m.isBridge()));
    }
}
```

```sh
javac --release 21 -Xlint:all BridgeLab.java
java BridgeLab
```

**Stdout chính xác trên JDK 21 với `javac`:**

```text
String bridge=false
Object bridge=true
```

`Parent<T>.get()` bị erase thành phương thức trả `Object`. `Child.get()` trả `String`, nên compiler phát sinh một method bridge trả `Object` và chuyển tiếp sang implementation trả `String`. `Method.isBridge()` giúp phát hiện; `isSynthetic()` cũng hữu ích khi lọc method do compiler tạo. Việc sắp xếp theo `isBridge` trong lab giúp output có thứ tự xác định, vì thứ tự nguyên thủy của `getDeclaredMethods()` không được cam kết.

Một framework tự phát hiện handler hoặc mapping method cần quyết định có bỏ bridge hay gộp nó với target không, tránh đăng ký hai lần cùng một hành vi. Quan sát thêm bằng:

```sh
javap -v 'BridgeLab$Child'
```

Trên Windows PowerShell hoặc Linux/macOS có thể dùng dấu nháy đơn như trên; trên Windows CMD, dùng dấu nháy kép để tránh phụ thuộc cú pháp shell. Hãy chú ý cờ `ACC_BRIDGE` và `ACC_SYNTHETIC` trong class file.

## 10. Xử lý tổng quát một cây `Type`

Trong thư viện mapper, validator hay plugin registry, một hàm chỉ xử lý `ParameterizedType` rồi cast mọi argument về `Class<?>` sẽ vỡ khi gặp `List<? extends T[]>`. Tư duy xử lý phải **đệ quy theo dạng node**, không tách chuỗi từ `getTypeName()` bằng regex.

### 10.1. Quy tắc duyệt và hành động

| Node | Cần đọc gì | Bước tiếp theo |
| --- | --- | --- |
| `Class<?>` | `isArray()`, `getComponentType()`, class identity | Nếu là array, duyệt component; nếu không, là kiểu leaf (hoặc tra metadata class khi cần). |
| `ParameterizedType` | `getRawType()`, `getOwnerType()`, `getActualTypeArguments()` | Duyệt từng argument và owner type nếu có, giữ quan hệ với raw type. |
| `WildcardType` | **Cả hai** `getUpperBounds()` và `getLowerBounds()` | Duyệt mọi bound; phân biệt mặc định Object với explicit constraints. |
| `GenericArrayType` | `getGenericComponentType()` | Duyệt component; có thể là `ParameterizedType`, `TypeVariable` hoặc array generic khác. |
| `TypeVariable<?>` | `getName()`, `getGenericDeclaration()`, `getBounds()` | Giữ scope của declaration; nếu cần resolve, dùng mapping theo superclass/interface/method context. |

Mẫu lõi xử lý một node (đoạn helper minh họa, đặt trong class đã có import `java.lang.reflect.*` và `java.util.Set`):

```java
static void walk(Type type, Set<Type> active) {
    if (!active.add(type)) {
        return; // tránh đệ quy vô hạn, ví dụ T extends Comparable<T>
    }
    try {
        if (type instanceof Class<?> cls) {
            if (cls.isArray()) walk(cls.getComponentType(), active);
        } else if (type instanceof ParameterizedType p) {
            walk(p.getRawType(), active);
            if (p.getOwnerType() != null) walk(p.getOwnerType(), active);
            for (Type t : p.getActualTypeArguments()) walk(t, active);
        } else if (type instanceof WildcardType w) {
            for (Type b : w.getUpperBounds()) walk(b, active);
            for (Type b : w.getLowerBounds()) walk(b, active);
        } else if (type instanceof GenericArrayType a) {
            walk(a.getGenericComponentType(), active);
        } else if (type instanceof TypeVariable<?> v) {
            for (Type b : v.getBounds()) walk(b, active);
        }
    } finally {
        active.remove(type);
    }
}
```

Hàm trên minh họa **cấu trúc duyệt** nên chưa ghi log hoặc tạo AST output; trong ứng dụng, thêm callback cho mỗi node/edge và giữ cả path/scope. `active` là **tập node đang nằm trên nhánh đệ quy**, không phải danh sách global “đã thấy”: một cùng `Type` có thể xuất hiện hợp lệ ở nhiều nhánh. `TypeVariable` tự tham chiếu qua `Comparable<T>` khiến naive recursion không có cycle guard có nguy cơ chạy vô hạn. Dùng `Set<Type>` theo `equals`, tránh dựa vào identity (`==`) của mọi object Reflection.

**Điểm cần kiểm tra thêm ở code production:**

- `TypeVariable` có cùng tên `T` ở hai generic declarations khác nhau **không tương đương**. Đừng dùng riêng chuỗi tên làm key; giữ `getGenericDeclaration()`.
- Khi gặp `ParameterizedType`, `getOwnerType()` có thể mang type arguments của outer class; bỏ qua owner có thể làm sai việc resolve nested generic class.
- Phân tích dữ liệu từ bytecode không chuẩn có thể gặp `GenericSignatureFormatError`, `TypeNotPresentException` hoặc `MalformedParameterizedTypeException`. Xử lý lỗi theo ranh giới plugin/module và thông báo đủ ngữ cảnh chẩn đoán.
- Nếu cần xem annotation ngay tại type use/bound, API `AnnotatedType` và `TypeVariable.getAnnotatedBounds()` có thể cung cấp metadata ngoài cây `Type` thông thường.
- Khi Reflection lookup method bằng tên và parameter `Class<?>...`, truyền các **kiểu erased** tương ứng; `Method.getGenericParameterTypes()` chỉ đọc lại generic signature sau khi đã tìm được method.

### 10.2. Vì sao không tự viết parser chuỗi type?

`getTypeName()` phù hợp để in, nhưng không phải AST/parser contract cho một hệ thống generic resolver. Tách `Map<String, List<? extends T[]>[]>` bằng dấu phẩy hoặc dấu `<` sẽ sai khi nhiều lớp lồng nhau. Dùng chính các interface `Type` để giữ thứ tự, biên giới generic arguments, arrays, wildcard bounds và owner declarations.

## 11. Các lỗi và giả định sai dễ gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `ClassCastException` khi cast `Type` sang `Class<?>` | Type thực tế là `ParameterizedType`, `WildcardType` hoặc `GenericArrayType` | Phân nhánh `instanceof` trước; duyệt đệ quy. |
| `ArrayIndexOutOfBoundsException` với `getLowerBounds()[0]` | `?` hoặc `? extends ...` có lower bounds rỗng | Kiểm tra mảng, duyệt toàn bộ bounds. |
| Tưởng `? super Integer` có upper bound `Integer` | Nhầm ý nghĩa “super” | Upper mặc định `Object`; lower chứa `Integer`. |
| `getGenericType()` cho `T` chứ không phải `String` | Field được khai báo trong generic base class, chưa resolve context kế thừa | Xây mapping type variables từ generic superclass/interfaces. |
| `getClass()` chỉ cho `ArrayList` | Type erasure ở runtime instance | Lấy type từ contract/declaration hoặc type reference đã khai báo trước; không tự suy từ instance. |
| `ClassCastException` hoặc dữ liệu sai sau unchecked cast | Heap pollution, type argument không được kiểm tra trong collection | Loại raw types, giảm unchecked conversion, validate elements ở boundary. |
| `GenericSignatureFormatError` / `TypeNotPresentException` | Signature bytecode hỏng hoặc thiếu referenced type | Kiểm tra classpath/module path, build tool/bytecode source và thông báo rõ type/field. |
| Mất dữ liệu generic array khi dùng `getType()` | Chỉ lấy erased class của array | Dùng `getGenericType()` rồi kiểm tra `GenericArrayType`. |
| Method bị xử lý hai lần | Có bridge/synthetic methods | Xem `Method.isBridge()`, `isSynthetic()` và mapping method thực. |
| Đệ quy không dừng ở `T extends Comparable<T>` | Duyệt bounds tự tham chiếu không có guard | Dùng tập type đang hoạt động trong nhánh, giữ declaration scope. |

**Checklist khi viết thư viện runtime metadata:**

1. Dùng generic Reflection API ở đúng vị trí khai báo; bảo toàn `Type` object khi truyền giữa các tầng.
2. Phân nhánh đủ các dạng `Type`, không index bounds hoặc cast tùy tiện.
3. Đảm bảo rõ ràng bạn đang đọc **generic signature metadata** hay đang kiểm tra **runtime object values**; hai việc không thay thế nhau.
4. Giải quyết generic inheritance dựa trên mapping declaration có ngữ cảnh; quản lý vòng lặp trong type graph.
5. Với dữ liệu ngoại lai, tạo validation ở boundary; tránh dùng generic metadata như chứng cứ runtime type safety.
6. Chạy lại lab bằng `javac --release 21 -Xlint:all`, kiểm tra warnings và xem bytecode/bridge khi cần.

## 12. Bài tập tự kiểm tra

**Bài 1 – Wildcard bounds.** Thêm field `List<? super Number> destination;` vào `TypeInspectionLab`. Cập nhật `inspect` để in bounds. Tự suy ra trước: upper `Object`, lower `Number`, rồi so với output thật. Thử tương tự `List<?>` để kiểm tra mảng lower rỗng.

**Bài 2 – Generic arrays nhiều tầng.** Khai báo field `T[][] matrix;` và `List<? extends Number>[][] nested;`. Viết một hàm đệ quy in từng component cho đến node không còn là array. Giải thích tại sao không thể cast `GenericArrayType` thành `Class<?>`.

**Bài 3 – Erasure.** Đổi `Holder<T extends Number>` thành `Holder<T extends CharSequence>`, giữ giới hạn tương thích khi cần và quan sát `item.getType().getTypeName()`. So sánh với `getGenericType()` để nêu quy tắc leftmost bound.

**Bài 4 – Đọc method generic.** Từ `WildcardUseLab`, dùng `getDeclaredMethod("addScores", List.class)` rồi kiểm tra `getGenericParameterTypes()[0]`. Tìm wildcard argument và lower bound bằng interface `ParameterizedType` và `WildcardType`. Tại sao lookup phải dùng `List.class` thay vì một class literal cho `List<? super Integer>`?

**Bài 5 – Type reference.** Thay `new TypeRef<List<String>>() { }` bằng `new TypeRef<List<? extends Number>[]>() { }`. Duyệt `Type` trả về để chỉ ra lần lượt `GenericArrayType`, `ParameterizedType` và `WildcardType`. Giải thích nơi thông tin này được lưu và tại sao object `new ArrayList<String>()` vẫn không tự cung cấp type argument.

**Bài 6 – Bridge method.** Xem `javap -v` của `BridgeLab$Child` và đối chiếu với `Method.isBridge()`. Vì sao việc lọc method dựa duy nhất vào tên không đủ an toàn?

**Tự chấm:** Bạn hoàn thành bài khi có thể phân tích `Map<String, List<? extends Number>[]>` thành các node `Type`, giải thích ba output wildcard của Lab 1, phân biệt `Class<?>` array với `GenericArrayType`, và nêu được một trường hợp Reflection giữ chữ ký generic nhưng runtime instance không giữ type argument.

## 13. Tài liệu chuẩn Java 21

- [`WildcardType` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/WildcardType.html): `getUpperBounds()`, `getLowerBounds()`.
- [`GenericArrayType` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/GenericArrayType.html): `getGenericComponentType()`.
- [`ParameterizedType` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html): raw type, type arguments, owner type.
- [`TypeVariable` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html): bound và generic declaration.
- [`Field` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html): `getType()`, `getGenericType()`.
- [Java Language Specification 21, chương 4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html): `4.5.1` (wildcards), `4.6` (type erasure), `4.7` (reifiable types).
- [Java Language Specification 21, chương 10](https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html): array types, generic array creation và store checks.

**Thông điệp kỹ thuật:** `WildcardType` và `GenericArrayType` giúp đọc chính xác **hình dạng generic của khai báo**. Type erasure vẫn giới hạn những gì runtime biết về **type argument của một instance**. Bộ xử lý metadata tốt cần tôn trọng cả hai sự thật này.
