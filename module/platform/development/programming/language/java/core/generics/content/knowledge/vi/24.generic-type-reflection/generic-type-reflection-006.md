# WildcardType và GenericArrayType trong Java Reflection

## 1. Bức tranh tổng quan

Java Generics cho phép khai báo những kiểu không chỉ có một tên class đơn giản, ví dụ:

```java
List<?> any;
List<? extends Number> readableNumbers;
List<? super Integer> writableIntegers;
List<String>[] groups;
T[] elements;
```

Đây là các **khai báo minh họa**; cần import `java.util.List`, đặt vào class tương ứng và khai báo `T` là type parameter. Trong công cụ serialization, dependency injection, mapping, validation hoặc code generator, ta có thể cần đọc lại chính xác cấu trúc kiểu đã khai báo.

Hai interface thuộc `java.lang.reflect` giải quyết những phần khác nhau của bài toán đó:

- **`WildcardType`** mô tả type argument dùng wildcard: `?`, `? extends Number`, `? super Integer`.
- **`GenericArrayType`** mô tả kiểu mảng có component type là generic type variable hoặc parameterized type: `T[]`, `List<String>[]`, `List<? extends Number>[]`.

Cả hai kế thừa `Type`. Chúng là **mô tả kiểu trong metadata reflection**, không phải runtime class đặc biệt được JVM sinh riêng cho mỗi generic argument.

Điểm phải nắm trước khi đọc ví dụ:

> `Field.getGenericType()` có thể mô tả `List<String>[]` nhưng một runtime array object tương ứng chỉ kiểm tra component raw `List` khi lưu phần tử. Reflection metadata **không xóa bỏ type erasure** và không tự kiểm tra nội dung một collection.

Bài trình bày API, upper/lower bounds, generic component types, sự kết hợp nhiều cấp, ví dụ Java 17 chạy được, lỗi thường gặp và cách xây type walker an toàn.

## 2. Hệ sinh thái `Type`: đừng cast mọi thứ thành `Class<?>`

`java.lang.reflect.Type` không đồng nghĩa `java.lang.Class`. Khi một field hoặc method mang generic declaration, reflection có thể trả nhiều dạng `Type`.

| Kiểu reflection | Khi nào xuất hiện điển hình | API cần biết |
|---|---|---|
| `Class<?>` | `String`, `Number`, `String[]`, `int` | `getTypeName`, `isArray`, `getComponentType` |
| `ParameterizedType` | `List<String>`, `Map<String,Integer>` | `getRawType`, `getActualTypeArguments`, `getOwnerType` |
| `TypeVariable<?>` | `T` trong `class Store<T>` | `getName`, `getBounds`, `getGenericDeclaration` |
| `WildcardType` | `?`, `? super Integer` | `getUpperBounds`, `getLowerBounds` |
| `GenericArrayType` | `T[]`, `List<String>[]` | `getGenericComponentType` |

Ví dụ cấu trúc:

```text
Map<String, List<? extends Number>[]>
└── ParameterizedType Map<..., ...>
    ├── Class<String>
    └── GenericArrayType
        └── ParameterizedType List<...>
            └── WildcardType ? extends Number
                └── upper bound: Class<Number>
```

Sơ đồ không mô tả nội dung của một object `Map` đang chạy. Đây là **cây kiểu được khai báo**. Một parser phải dùng `instanceof` để chọn nhánh thích hợp thay vì ép thẳng toàn bộ cây thành `Class<?>`.

## 3. `WildcardType`: upper bounds và lower bounds

Interface `WildcardType` cung cấp:

```java
Type[] getUpperBounds();
Type[] getLowerBounds();
```

Đây là chữ ký minh họa API; `Type` cần được import từ `java.lang.reflect`.

Giá trị thường gặp:

| Cú pháp wildcard | Upper bounds | Lower bounds |
|---|---|---|
| `?` | `Object` | rỗng |
| `? extends Number` | `Number` | rỗng |
| `? super Integer` | `Object` | `Integer` |
| `? extends Comparable<String>` | `Comparable<String>` (`ParameterizedType`) | rỗng |

Vì sao `? super Integer` vẫn có upper bound `Object`? Mọi kiểu tham chiếu hợp lệ đều bị giới hạn trên bởi `Object`; còn `Integer` đóng vai trò **lower bound**.

Vì sao `?` không tương đương `Object` dù upper bound của nó là Object? `List<?>` biểu diễn một element type **chưa biết**; không được tùy tiện thêm `"x"` hay `123`. `List<Object>` lại có element type **xác định là `Object`**, nên các thao tác thêm đối tượng phù hợp là hợp lệ.

Bounds của reflection có kiểu `Type[]`, không nhất thiết `Class<?>[]`. Một bound có thể tiếp tục là parameterized type hoặc cấu trúc reflection khác.

## 4. Ví dụ đầy đủ: đọc ba loại wildcard từ field

Tạo tệp **`WildcardBoundsDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.WildcardType;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class WildcardBoundsDemo {
    static class Fields {
        List<?> any;
        List<? extends Number> upper;
        List<? super Integer> lower;
    }

    static String display(Type[] types) {
        return Arrays.stream(types)
                .map(Type::getTypeName)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    static void show(String fieldName) throws Exception {
        Field field = Fields.class.getDeclaredField(fieldName);
        ParameterizedType list = (ParameterizedType) field.getGenericType();
        WildcardType w = (WildcardType) list.getActualTypeArguments()[0];

        System.out.println(fieldName
                + ": upper=" + display(w.getUpperBounds())
                + ", lower=" + display(w.getLowerBounds()));
    }

    public static void main(String[] args) throws Exception {
        show("any");
        show("upper");
        show("lower");
    }
}
```

Chạy trên JDK 17:

```bash
javac WildcardBoundsDemo.java
java WildcardBoundsDemo
```

Stdout:

```text
any: upper=[java.lang.Object], lower=[]
upper: upper=[java.lang.Number], lower=[]
lower: upper=[java.lang.Object], lower=[java.lang.Integer]
```

Các bước phản chiếu:

1. `getDeclaredField(...)` lấy **declaration** của field.
2. `getGenericType()` trả `ParameterizedType` vì field dùng `List<...>`.
3. `getActualTypeArguments()[0]` trả phần `?`.
4. `WildcardType` cho phép đọc upper/lower bounds.
5. `Type.getTypeName()` dùng để hiển thị tên kiểu.

Các cast trong chương trình hợp lệ vì đã **biết trước cấu trúc** các field demo. Với input tùy ý, phải kiểm tra `instanceof` và cả số lượng type arguments trước khi truy cập.

## 5. Upper bound có thể là `ParameterizedType`

Đừng giả định `getUpperBounds()[0]` là một `Class<?>`.

Ví dụ:

```java
List<? extends Comparable<String>> values;
```

`Comparable<String>` không phải một runtime class chuyên biệt; nó là parameterized type. Vì vậy upper bound là `ParameterizedType`.

Tệp **`ParameterizedWildcardDemo.java`**:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.WildcardType;
import java.util.List;

public class ParameterizedWildcardDemo {
    static class Data {
        List<? extends Comparable<String>> values;
    }

    public static void main(String[] args) throws Exception {
        ParameterizedType list = (ParameterizedType)
                Data.class.getDeclaredField("values").getGenericType();

        WildcardType wildcard = (WildcardType)
                list.getActualTypeArguments()[0];

        Type upper = wildcard.getUpperBounds()[0];
        System.out.println(upper instanceof ParameterizedType);
        System.out.println(upper.getTypeName());
    }
}
```

Chạy:

```bash
javac ParameterizedWildcardDemo.java
java ParameterizedWildcardDemo
```

Stdout:

```text
true
java.lang.Comparable<java.lang.String>
```

Nếu code cố `Class<?> clazz = (Class<?>) upper;`, nó sẽ ném `ClassCastException`. Điều đúng là duyệt tiếp `ParameterizedType`: raw type `Comparable`, actual argument `String`.

## 6. Type variable `T` không phải wildcard `?`

Xét generic class:

```java
class Store<T extends Number> {
    List<T> values;
    List<? extends Number> view;
}
```

Đây là class minh họa, cần import `List` nếu dùng đơn lẻ.

- `T` là **type parameter có tên**, được khai báo bởi `Store<T extends Number>`.
- `? extends Number` là **wildcard vô danh** ở vị trí type argument.
- Reflection của argument trong `List<T>` trả `TypeVariable<?>`.
- Reflection của argument trong `List<? extends Number>` trả `WildcardType`.

`TypeVariable` có `getName()`, `getBounds()`, `getGenericDeclaration()`; `WildcardType` có `getUpperBounds()` và `getLowerBounds()`.

Tệp **`WildcardVsVariableDemo.java`**:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.List;

public class WildcardVsVariableDemo {
    static class Store<T extends Number> {
        List<T> values;
        List<? extends Number> view;
    }

    static Type argument(String fieldName) throws Exception {
        ParameterizedType list = (ParameterizedType)
                Store.class.getDeclaredField(fieldName).getGenericType();
        return list.getActualTypeArguments()[0];
    }

    public static void main(String[] args) throws Exception {
        Type a = argument("values");
        Type b = argument("view");
        System.out.println(a instanceof TypeVariable<?>);
        System.out.println(b instanceof WildcardType);

        TypeVariable<?> t = (TypeVariable<?>) a;
        System.out.println(t.getName());
        System.out.println(t.getBounds()[0].getTypeName());
    }
}
```

Chạy:

```bash
javac WildcardVsVariableDemo.java
java WildcardVsVariableDemo
```

Stdout:

```text
true
true
T
java.lang.Number
```

Nhìn bounds thấy đều liên quan `Number` **không có nghĩa hai kiểu reflection có cùng bản chất**. `T` có thể xuất hiện nhiều lần trong cùng khai báo và buộc các vị trí liên hệ với nhau; từng wildcard đại diện một kiểu chưa biết thích hợp với giới hạn.

## 7. PECS ở mã nguồn và những gì reflection thực sự biết

Khi lập trình, wildcard bounds có tác dụng trong kiểm tra kiểu tĩnh:

```java
static double total(List<? extends Number> values) {
    double sum = 0;
    for (Number n : values) {
        sum += n.doubleValue();
    }
    return sum;
}

static void appendDefaults(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
```

Đây là các method minh họa; đặt trong class và import `List`.

- `? extends Number` là **producer**: đọc phần tử như `Number`; không được tùy tiện thêm một `Double` vì list thực có thể là `List<Integer>`.
- `? super Integer` là **consumer**: có thể thêm `Integer`; đọc phần tử chỉ chắc chắn là `Object`.
- `?` không cho phép tự ý thêm phần tử non-null có loại chưa biết.

Reflection chỉ cho biết các bounds đã khai báo; nó không thay compiler quyết định những thao tác được phép trên một variable kiểu generic, và không tự duyệt list để chứng minh dữ liệu phù hợp.

## 8. Wildcard lồng trong `Map` rồi `List`

Một field có kiểu:

```java
Map<String, List<? super Integer>> mapping;
```

gồm nhiều lớp:

```text
ParameterizedType Map
  Class<String>
  ParameterizedType List
    WildcardType ? super Integer
      lower bound Integer
      upper bound Object
```

Tệp **`NestedWildcardDemo.java`**:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.WildcardType;
import java.util.List;
import java.util.Map;

public class NestedWildcardDemo {
    static class Fields {
        Map<String, List<? super Integer>> mapping;
    }

    public static void main(String[] args) throws Exception {
        ParameterizedType map = (ParameterizedType)
                Fields.class.getDeclaredField("mapping").getGenericType();

        Type valueArgument = map.getActualTypeArguments()[1];
        ParameterizedType list = (ParameterizedType) valueArgument;

        WildcardType wildcard = (WildcardType)
                list.getActualTypeArguments()[0];

        System.out.println(map.getRawType().getTypeName());
        System.out.println(list.getRawType().getTypeName());
        System.out.println(wildcard.getTypeName());
        System.out.println(wildcard.getLowerBounds()[0].getTypeName());
    }
}
```

Lệnh:

```bash
javac NestedWildcardDemo.java
java NestedWildcardDemo
```

Stdout:

```text
java.util.Map
java.util.List
? super java.lang.Integer
java.lang.Integer
```

Đừng chỉ dựa vào `Map.class` hoặc `List.class`: các raw class tokens đó không giữ các nested type arguments. Với reflection metadata đã khai báo, lần lượt dùng `getActualTypeArguments()` để đi sâu.

## 9. `GenericArrayType` mô tả array declaration với generic component

`GenericArrayType` là interface của `Type` và có phương thức chính:

```java
Type getGenericComponentType();
```

Nó xuất hiện trong các kiểu như:

```java
class Examples<T> {
    T[] elements;
    T[][] grid;
    List<String>[] names;
    List<? extends Number>[] numericGroups;
}
```

Các **field declarations** trên được phép, giả sử import `List`. Chúng không phải thao tác tạo mảng.

- Với `T[]`, generic component là `TypeVariable` `T`.
- Với `List<String>[]`, component là `ParameterizedType` `List<String>`.
- Với `T[][]`, component của outer `GenericArrayType` lại là một `GenericArrayType` khác cho `T[]`.
- Với `List<? extends Number>[]`, component `List<...>` có một nested `WildcardType`.

`GenericArrayType` là **type metadata**, không phải một instance của mảng, không phải mảng có thể `get(index)`, và không có phương thức tạo array object. Khi muốn runtime array component class, xem `Class<?>` của object mảng thực tế hoặc dùng API tạo mảng phù hợp.

## 10. So sánh với mảng có runtime `Class<?>`

Một object `String[]` thực có runtime array class. Reflection có thể trả một `Class<?>` đại diện cho `String[]`:

```java
Class<?> clazz = String[].class;

System.out.println(clazz.isArray());
System.out.println(clazz.getComponentType().getTypeName());
```

Nếu nằm trong method, stdout là:

```text
true
java.lang.String
```

Từ `String[]`, JVM biết runtime component `String` và có thể kiểm tra một store qua `Object[]`.

Trái lại, khai báo `List<String>[]` trong class file có thể được `Field.getGenericType()` thể hiện bằng `GenericArrayType` vì phần `List<String>` vẫn là metadata generic; object array thực ở runtime không có specialized class `List<String>[]`.

Bảng phân biệt:

| Câu hỏi | Reflection API |
|---|---|
| Kiểu runtime của một mảng đang chạy? | `array.getClass()` |
| Component class runtime? | `array.getClass().getComponentType()` |
| Một field khai báo kiểu mảng generic nào? | `field.getGenericType()` |
| Generic component của declaration? | `GenericArrayType.getGenericComponentType()` |
| Một method trả `T[]` hay `Number[]` sau erasure? | `getGenericReturnType()` so với `getReturnType()` |

## 11. Ví dụ phản chiếu nhiều loại array field

Tệp **`GenericArrayFieldsDemo.java`**:

```java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.Type;
import java.util.List;

public class GenericArrayFieldsDemo {
    static class Fields<T> {
        String[] plain;
        List<String>[] stringLists;
        List<?>[] unknownLists;
        T[] values;
        T[][] grid;
    }

    static void inspect(String name) throws Exception {
        Type type = Fields.class.getDeclaredField(name).getGenericType();
        System.out.println(name + ": "
                + (type instanceof GenericArrayType)
                + " | " + type.getTypeName());
    }

    public static void main(String[] args) throws Exception {
        inspect("plain");
        inspect("stringLists");
        inspect("unknownLists");
        inspect("values");
        inspect("grid");
    }
}
```

Chạy:

```bash
javac GenericArrayFieldsDemo.java
java GenericArrayFieldsDemo
```

Stdout:

```text
plain: false | java.lang.String[]
stringLists: true | java.util.List<java.lang.String>[]
unknownLists: true | java.util.List<?>[]
values: true | T[]
grid: true | T[][]
```

Giải thích:

- `String[]` phản chiếu như một `Class` array.
- `List<String>[]` mang parameterized component, phản chiếu như `GenericArrayType`.
- `List<?>[]` có generic declaration component nên reflection giữ cấu trúc `List<?>`, dù kiểu component `List<?>` là **reifiable** theo JLS.
- `T[]` và `T[][]` chứa type variable, nên dùng `GenericArrayType`.

Không nên tự kết luận “hễ là `GenericArrayType` thì mảng không bao giờ được tạo” — reifiability và cấu trúc generic declaration là hai khía cạnh khác nhau.

## 12. Đọc các component trong mảng nhiều chiều

Tệp **`GenericArrayComponentDemo.java`**:

```java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.List;

public class GenericArrayComponentDemo {
    static class Data<T> {
        T[][] grid;
        List<String>[] groups;
    }

    public static void main(String[] args) throws Exception {
        Type grid = Data.class.getDeclaredField("grid")
                .getGenericType();

        GenericArrayType outer = (GenericArrayType) grid;
        GenericArrayType inner = (GenericArrayType)
                outer.getGenericComponentType();
        Type element = inner.getGenericComponentType();

        System.out.println(element instanceof TypeVariable<?>);
        System.out.println(element.getTypeName());

        Type groups = Data.class.getDeclaredField("groups")
                .getGenericType();
        Type component = ((GenericArrayType) groups)
                .getGenericComponentType();

        System.out.println(component instanceof ParameterizedType);
        System.out.println(component.getTypeName());
    }
}
```

Lệnh:

```bash
javac GenericArrayComponentDemo.java
java GenericArrayComponentDemo
```

Stdout:

```text
true
T
true
java.util.List<java.lang.String>
```

Với `T[][]`, ta phải gọi `getGenericComponentType()` **hai lần** để đến `T`. Với `List<String>[]`, chỉ một lần là tới `ParameterizedType`.

Nếu framework xử lý mảng đa chiều, đừng lấy `((Class<?>) type).getComponentType()` ngay trên một `GenericArrayType`: đó là hai mô hình API khác nhau.

## 13. Khai báo `List<String>[]` được, nhưng `new List<String>[n]` bị cấm

Một bẫy thường gặp:

```java
List<String>[] groups; // Khai báo hợp lệ.
```

nhưng:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
List<String>[] groups = new List<String>[2];
```

Biểu thức tạo mảng yêu cầu **component type reifiable**. `List<String>` không reifiable vì type argument `String` không được biểu diễn đầy đủ để JVM array-store check.

Tương tự:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
new List<? extends Number>[2];
new List<Integer>[2];
new T[2];
```

Ngược lại:

```java
List<?>[] groups = new List<?>[2];
```

là hợp lệ vì `List<?>` dùng wildcard không giới hạn và là reifiable type theo quy tắc của Java. Runtime component class vẫn là raw `List`.

**Reflection đọc được một kiểu declaration không có nghĩa compiler cho phép tạo một runtime array object bằng chính biểu thức `new` với kiểu đó.**

## 14. Ví dụ runtime component class thực tế

Tệp **`RuntimeArrayClassDemo.java`**:

```java
import java.util.List;

public class RuntimeArrayClassDemo {
    public static void main(String[] args) {
        String[] words = new String[1];
        List<?>[] lists = new List<?>[2];

        System.out.println(words.getClass()
                .getComponentType().getTypeName());
        System.out.println(lists.getClass()
                .getComponentType().getTypeName());
        System.out.println(lists instanceof Object[]);
        System.out.println(lists.getClass().isArray());
    }
}
```

Chạy:

```bash
javac RuntimeArrayClassDemo.java
java RuntimeArrayClassDemo
```

Stdout:

```text
java.lang.String
java.util.List
true
true
```

JVM kiểm tra store theo runtime component class `String` hoặc `List`. Nó không có component class riêng cho `List<String>` hay `List<Integer>`.

`Class.getComponentType()` chỉ dùng cho runtime `Class` của mảng, còn `GenericArrayType.getGenericComponentType()` chỉ dùng cho một generic array declaration được reflection mô tả.

## 15. Generic array xuất hiện ở method, không chỉ field

Một generic method có thể nhận và trả `T[]`.

Tệp **`GenericMethodArrayDemo.java`**:

```java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.Method;
import java.lang.reflect.Type;

public class GenericMethodArrayDemo {
    static <T extends Number> T[] identity(T[] input) {
        return input;
    }

    public static void main(String[] args) throws Exception {
        Method method = GenericMethodArrayDemo.class
                .getDeclaredMethod("identity", Number[].class);

        Type parameter = method.getGenericParameterTypes()[0];
        Type result = method.getGenericReturnType();

        System.out.println(parameter instanceof GenericArrayType);
        System.out.println(parameter.getTypeName());
        System.out.println(result instanceof GenericArrayType);
        System.out.println(result.getTypeName());
        System.out.println(method.getReturnType().getTypeName());
    }
}
```

Biên dịch/chạy:

```bash
javac GenericMethodArrayDemo.java
java GenericMethodArrayDemo
```

Stdout:

```text
true
T[]
true
T[]
java.lang.Number[]
```

Tại sao tra method bằng `Number[].class` thay vì `Object[].class`? `T` có upper bound đầu tiên `Number`, nên erasure của `T` là `Number`; của `T[]` là `Number[]`.

`getGenericParameterTypes()` và `getGenericReturnType()` đọc declaration generic. `getParameterTypes()` và `getReturnType()` phản ánh class runtime sau erasure.

## 16. Trường hợp chứa cả wildcard và generic array

Xét:

```java
List<? extends Number>[] groups;
```

Cây reflection:

```text
GenericArrayType
  ParameterizedType List<...>
    WildcardType ? extends Number
      upper bound Class Number
```

Tệp **`WildcardArrayReflectionDemo.java`**:

```java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.WildcardType;
import java.util.List;

public class WildcardArrayReflectionDemo {
    static class Fields {
        List<? extends Number>[] groups;
    }

    public static void main(String[] args) throws Exception {
        Type declared = Fields.class.getDeclaredField("groups")
                .getGenericType();
        GenericArrayType array = (GenericArrayType) declared;

        ParameterizedType list = (ParameterizedType)
                array.getGenericComponentType();

        WildcardType wildcard = (WildcardType)
                list.getActualTypeArguments()[0];

        System.out.println(array.getTypeName());
        System.out.println(list.getRawType().getTypeName());
        System.out.println(wildcard.getTypeName());
        System.out.println(wildcard.getUpperBounds()[0].getTypeName());
    }
}
```

Chạy:

```bash
javac WildcardArrayReflectionDemo.java
java WildcardArrayReflectionDemo
```

Stdout:

```text
java.util.List<? extends java.lang.Number>[]
java.util.List
? extends java.lang.Number
java.lang.Number
```

Điều quan trọng: phản chiếu được các phần này **không làm** `new List<? extends Number>[2]` hợp lệ. Với code cần nhóm số, `List<List<? extends Number>>` có thể là thiết kế thích hợp hơn.

## 17. Đọc một `Type` bất kỳ cần xử lý năm nhánh

Đối với một thư viện xử lý schema hoặc generic API, có thể viết một bộ duyệt `Type`:

```text
Nếu Type là Class<?>:
    đọc tên, kiểm tra isArray() nếu cần
Nếu Type là ParameterizedType:
    đọc raw type, owner type, actual arguments
Nếu Type là WildcardType:
    đọc upper/lower bounds
Nếu Type là TypeVariable<?>:
    đọc tên, generic declaration, bounds có kiểm soát
Nếu Type là GenericArrayType:
    đọc generic component type
```

Cần hiểu hai nguy cơ:

- **Kiểu lồng nhau nhiều cấp**: không thể dừng ngay khi gặp một `ParameterizedType` hoặc `GenericArrayType`.
- **Bound tự tham chiếu**: ví dụ `T extends Comparable<T>` chứa lại `T` ở bên trong bound. Nếu walker cứ mở rộng bounds không giới hạn, nó có thể đệ quy vô hạn.

Một walker đơn giản có thể **in tên type variable nhưng không mở rộng bounds**. Một công cụ hoàn chỉnh cần tập đã thăm để ngắt chu kỳ.

## 18. Chương trình type walker tổng quát

Tệp **`TypeTreeWalkerDemo.java`**:

```java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.List;
import java.util.Map;

public class TypeTreeWalkerDemo {
    static class Fields {
        Map<String, List<? extends Number>[]> data;
    }

    static void walk(Type type, int level) {
        String pad = "  ".repeat(level);

        if (type instanceof ParameterizedType p) {
            System.out.println(pad + "Parameterized: "
                    + p.getRawType().getTypeName());
            for (Type argument : p.getActualTypeArguments()) {
                walk(argument, level + 1);
            }
        } else if (type instanceof GenericArrayType array) {
            System.out.println(pad + "GenericArray");
            walk(array.getGenericComponentType(), level + 1);
        } else if (type instanceof WildcardType wildcard) {
            System.out.println(pad + "Wildcard");
            for (Type upper : wildcard.getUpperBounds()) {
                System.out.println(pad + "  Upper:");
                walk(upper, level + 2);
            }
            for (Type lower : wildcard.getLowerBounds()) {
                System.out.println(pad + "  Lower:");
                walk(lower, level + 2);
            }
        } else if (type instanceof TypeVariable<?> variable) {
            System.out.println(pad + "Variable: "
                    + variable.getName());
        } else if (type instanceof Class<?> clazz) {
            System.out.println(pad + "Class: "
                    + clazz.getTypeName());
        } else {
            System.out.println(pad + "Other: "
                    + type.getTypeName());
        }
    }

    public static void main(String[] args) throws Exception {
        Type declared = Fields.class.getDeclaredField("data")
                .getGenericType();
        walk(declared, 0);
    }
}
```

Biên dịch/chạy:

```bash
javac TypeTreeWalkerDemo.java
java TypeTreeWalkerDemo
```

Stdout:

```text
Parameterized: java.util.Map
  Class: java.lang.String
  GenericArray
    Parameterized: java.util.List
      Wildcard
        Upper:
          Class: java.lang.Number
```

Đây là một walker minh họa đủ năm nhánh, không có vòng lặp do không mở rộng `TypeVariable` bounds. Framework lớn còn cần kiểm tra owner types của inner classes, quy ước schema, xử lý thiếu class và tối ưu caching.

Không nên dùng `Type.getTypeName()` rồi tách chuỗi bằng dấu phẩy hoặc dấu `<` như thể đó là một ngôn ngữ schema đơn giản. Với nested types, hãy duyệt **cấu trúc `Type`**.

## 19. Một mảng `List<?>[]` reifiable vẫn có generic declaration

Đây là trường hợp giúp phân biệt chính xác **reifiability** và **reflection object type**.

Java cho phép tạo:

```java
List<?>[] values = new List<?>[3];
```

Runtime component class là `java.util.List`, nên `values.getClass().getComponentType()` trả token cho `List`.

Trong một field khai báo `List<?>[]`, reflection có thể giữ lại tham số hóa `List<?>` và trả `GenericArrayType` có component là `ParameterizedType`.

Vậy:

- **Reifiable:** Java có đủ thông tin runtime để kiểm tra một object lưu vào array có là `List` hay không.
- **Parameterized generic declaration:** Reflection vẫn lưu được phần `<?>` ở source declaration, nên cấu trúc kiểu có thể là `GenericArrayType`.

Không đánh đồng: “Hễ `GenericArrayType` là không thể tạo mảng”, hoặc “Hễ mảng tạo được thì `Field.getGenericType()` phải là `Class`”.

## 20. Vì sao metadata không loại bỏ heap pollution?

Giả sử một tham chiếu được nhìn thành `List<String>[]` qua unchecked conversion, nhưng runtime array component chỉ là raw `List`.

Khi có một alias:

```java
Object[] alias = someArray;
```

thao tác lưu một `List<Integer>` vào slot vẫn có thể vượt qua runtime array store check, vì đó là object implements `List`. Sau đó, đọc giá trị qua `List<String>[]` và cast phần tử thành `String` mới phát hiện lỗi.

`GenericArrayType` có thể cho biết một **field khai báo `List<String>[]`**, nhưng JVM không dùng generic declaration metadata đó để kiểm tra từng type argument trong array store.

Đây là một động cơ của quy tắc cấm trực tiếp tạo `new List<String>[n]`.

## 21. Ví dụ kiểm chứng: heap pollution và ngoại lệ muộn

Tệp **`GenericArrayPollutionDemo.java`**:

```java
import java.util.List;

public class GenericArrayPollutionDemo {

    @SuppressWarnings("unchecked")
    static List<String>[] unsafeArray() {
        return (List<String>[]) new List<?>[1];
    }

    public static void main(String[] args) {
        List<String>[] groups = unsafeArray();
        groups[0] = List.of("safe");

        Object[] alias = groups;
        alias[0] = List.of(123);

        System.out.println(groups.getClass()
                .getComponentType().getName());

        try {
            String value = groups[0].get(0);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac GenericArrayPollutionDemo.java
java GenericArrayPollutionDemo
```

Stdout:

```text
java.util.List
ClassCastException
```

Giải thích:

1. `new List<?>[1]` hợp lệ.
2. Cast sang `List<String>[]` không được compiler kiểm tra đầy đủ.
3. `Object[] alias` trỏ đến cùng object array.
4. `List.of(123)` phù hợp runtime component `List`, nên không gây `ArrayStoreException`.
5. `get(0)` đọc một `Integer` trong ngữ cảnh cần `String`, nên gây `ClassCastException`.

Đoạn `unsafeArray` **cố ý không an toàn** để giải thích cơ chế, không phải factory nên tái sử dụng. `@SuppressWarnings` chỉ tắt warning, không thêm runtime generic checks.

## 22. Giữ một kiểu generic array phức tạp bằng `TypeRef`

Đôi khi không có field hoặc method cụ thể cho framework đọc `Type`. Một anonymous subclass có thể giữ một generic superclass declaration.

Tệp **`GenericTypeReferenceDemo.java`**:

```java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.List;

public class GenericTypeReferenceDemo {

    static abstract class TypeRef<T> {
        final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            type = ((ParameterizedType) parent)
                    .getActualTypeArguments()[0];
        }
    }

    public static void main(String[] args) {
        TypeRef<List<? super Integer>[]> ref =
                new TypeRef<List<? super Integer>[]>() {};

        System.out.println(ref.type.getTypeName());
        System.out.println(ref.type instanceof GenericArrayType);
    }
}
```

Chạy:

```bash
javac GenericTypeReferenceDemo.java
java GenericTypeReferenceDemo
```

Stdout:

```text
java.util.List<? super java.lang.Integer>[]
true
```

Anonymous subclass ghi `TypeRef<List<? super Integer>[]>` trong generic superclass metadata; reflection có thể đọc lại một cây gồm `GenericArrayType`, `ParameterizedType`, `WildcardType`.

Điều này không phải một runtime object array chứa sẵn type argument `Integer`. Nếu thư viện muốn dùng metadata để validate hoặc decode, nó cần một bộ xử lý dữ liệu riêng.

## 23. Wildcard có thể ở tham số phương thức

Một method nhận `List<? super Integer>` giữ wildcard trong generic parameter declaration.

Tệp **`WildcardMethodDemo.java`**:

```java
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.WildcardType;
import java.util.List;

public class WildcardMethodDemo {
    static void receive(List<? super Integer> values) {
        values.add(10);
    }

    public static void main(String[] args) throws Exception {
        Method method = WildcardMethodDemo.class
                .getDeclaredMethod("receive", List.class);

        ParameterizedType parameter = (ParameterizedType)
                method.getGenericParameterTypes()[0];

        WildcardType wildcard = (WildcardType)
                parameter.getActualTypeArguments()[0];

        System.out.println(method.getParameterTypes()[0].getTypeName());
        System.out.println(wildcard.getTypeName());
        System.out.println(
                wildcard.getLowerBounds()[0].getTypeName());
    }
}
```

Biên dịch/chạy:

```bash
javac WildcardMethodDemo.java
java WildcardMethodDemo
```

Stdout:

```text
java.util.List
? super java.lang.Integer
java.lang.Integer
```

`getDeclaredMethod` dùng runtime signature với `List.class` sau erasure. `getGenericParameterTypes()` mới trả phần `List<? super Integer>` được khai báo.

Nếu method nhận generic array, `getGenericParameterTypes()` có thể tiếp tục trả `GenericArrayType`.

## 24. `getType` so với `getGenericType`

Hai API trên `Field` trả hai lớp thông tin khác nhau:

- `field.getType()`: `Class<?>` phản ánh runtime/erased type.
- `field.getGenericType()`: `Type` phản ánh generic type của field declaration khi metadata còn sẵn.

Tệp **`GenericVsErasedArrayDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.util.List;

public class GenericVsErasedArrayDemo {
    static class Fields {
        List<String>[] groups;
    }

    public static void main(String[] args) throws Exception {
        Field field = Fields.class.getDeclaredField("groups");

        System.out.println(field.getType().getTypeName());
        System.out.println(field.getGenericType().getTypeName());
        System.out.println(
                field.getGenericType() instanceof GenericArrayType);
    }
}
```

Chạy:

```bash
javac GenericVsErasedArrayDemo.java
java GenericVsErasedArrayDemo
```

Stdout:

```text
java.util.List[]
java.util.List<java.lang.String>[]
true
```

`getType()` chỉ biết mảng component `List`. `getGenericType()` mô tả component `List<String>`. Không có mâu thuẫn: hai method phục vụ hai nhu cầu phản chiếu khác nhau.

Tương ứng, method reflection có `getReturnType()` so với `getGenericReturnType()`, và `getParameterTypes()` so với `getGenericParameterTypes()`.

## 25. Metadata `Signature` và ranh giới runtime

Compiler Java có thể lưu generic declaration trong **`Signature` attribute** của class file. Reflection dùng thông tin này để trả `ParameterizedType`, `WildcardType`, `TypeVariable` hoặc `GenericArrayType` ở những declaration phù hợp.

Nhưng không được hiểu rằng:

- Mọi object runtime đều mang một `Signature` ghi rõ type arguments tại nơi `new`.
- `Field.getGenericType()` tự kiểm tra nội dung đang nằm trong field.
- `Class.getComponentType()` kiểm tra được `List<String>` khác `List<Integer>`.
- Một chuỗi trả bởi `Type.getTypeName()` đủ để thực hiện deserialization an toàn.

Khi thông tin generic được tạo từ class files thiếu hoặc hỏng metadata, reflection cũng có thể phát sinh những ngoại lệ/lỗi theo contract API. Framework thực tế cần xử lý các trường hợp như thiếu type được tham chiếu, chữ ký không phù hợp, hoặc recursive type bounds.

Nếu kiểm tra classfile bằng `javap -v`, có thể so sánh JVM descriptor sau erasure với thuộc tính `Signature`. **Signature là metadata declaration, không phải một runtime enforcement mechanism** cho generic element types.

## 26. Những sai lầm phổ biến với `WildcardType`

**Sai lầm 1:** `List<?>` giống `List<Object>`. Không: wildcard có element type chưa biết, còn Object là một argument cụ thể.

**Sai lầm 2:** `? super Integer` có upper bound `Integer`. Không: `Integer` là lower bound; upper bound mặc định `Object`.

**Sai lầm 3:** `getLowerBounds()` luôn có một phần tử. Không: nó rỗng đối với `?` và `? extends Number`.

**Sai lầm 4:** Mọi upper bound đều là `Class<?>`. Không: `Comparable<String>` là `ParameterizedType`.

**Sai lầm 5:** `WildcardType` có `getName()` như `TypeVariable`. Không: wildcard không phải type parameter có tên.

**Sai lầm 6:** Mọi generic argument trả về từ `getActualTypeArguments()` đều có thể cast sang `WildcardType`. Không: chúng có thể là `Class`, `TypeVariable`, `ParameterizedType` hoặc dạng khác.

**Sai lầm 7:** Reflection bounds tự quyết định toàn bộ thao tác ghi vào generic list. Không: quy tắc compiler và hợp đồng API vẫn có vai trò chính.

**Sai lầm 8:** Đọc được wildcard nghĩa là đã xác minh mọi phần tử runtime của một collection. Không: metadata khai báo khác với validation dữ liệu.

## 27. Những sai lầm phổ biến với `GenericArrayType`

**Sai lầm 1:** Mọi kiểu mảng từ reflection là `GenericArrayType`. Không: `String[]` được biểu diễn bằng `Class<?>`.

**Sai lầm 2:** Có thể cast `GenericArrayType` thành `Class<?>` để tạo mảng. Không: chúng là những biểu diễn `Type` khác nhau.

**Sai lầm 3:** Component của `GenericArrayType` luôn là `Class<?>`. Không: có thể là `TypeVariable`, `ParameterizedType` hoặc nested `GenericArrayType`.

**Sai lầm 4:** `T[][]` chỉ có một lớp generic array. Không: phải đi qua hai component levels.

**Sai lầm 5:** Có `GenericArrayType` thì có thể `new T[n]`. Không: array creation theo cú pháp Java đòi component type reifiable.

**Sai lầm 6:** `List<?>[]` không bao giờ tạo được. Không: `new List<?>[2]` hợp lệ.

**Sai lầm 7:** Runtime array component `List` bảo vệ được type argument `String`. Không: nó chỉ kiểm tra object thuộc raw `List`.

**Sai lầm 8:** `Array.newInstance(List.class, n)` tạo một mảng có specialized component `List<String>`. Không: nó tạo mảng raw `List[]`.

**Sai lầm 9:** Unchecked cast `(List<String>[]) ...` làm array trở nên an toàn. Không: có thể tạo heap pollution qua alias kiểu rộng.

## 28. Bài tập có đáp án

### Bài 1 — Wildcard không bound

`List<?>` có upper và lower bounds nào trong reflection?

**Đáp án:** Upper chứa `Object`, lower rỗng.

### Bài 2 — Upper/lower

`List<? super Integer>` lấy `Integer` bằng method nào?

**Đáp án:** `WildcardType.getLowerBounds()[0]`.

### Bài 3 — Bound parameterized

`List<? extends Comparable<String>>` có upper bound thuộc `Class<?>` không?

**Đáp án:** Không; đây là `ParameterizedType` của `Comparable<String>`.

### Bài 4 — Type variable

`List<T>` trong `class Box<T>` có argument reflection loại gì?

**Đáp án:** `TypeVariable<?>`, không phải `WildcardType`.

### Bài 5 — Array declaration

`List<String>[] values;` hợp lệ còn `new List<String>[5]` hợp lệ không?

**Đáp án:** Khai báo hợp lệ; array creation bị cấm vì component non-reifiable.

### Bài 6 — Array of wildcard

Có thể viết `new List<?>[5]` không?

**Đáp án:** Có. Runtime component class là raw `List`.

### Bài 7 — String array

`String[]` nhận được từ `Field.getGenericType()` có dạng nào?

**Đáp án:** `Class<?>` array type trong trường hợp khai báo đó, không phải `GenericArrayType`.

### Bài 8 — Multi-dimensional

Với `T[][]`, cần bao nhiêu bước `getGenericComponentType()` để đến `T`?

**Đáp án:** Hai bước.

### Bài 9 — Kết hợp

`List<? extends Number>[]` phân rã thành những kiểu nào?

**Đáp án:** `GenericArrayType` → `ParameterizedType` → `WildcardType` → upper bound `Class` Number.

### Bài 10 — Method reflection

Với `<T extends Number> T[] identity(T[] input)`, vì sao tra parameter bằng `Number[].class`?

**Đáp án:** Erasure của `T` là `Number`, vì upper bound đầu tiên là `Number`.

### Bài 11 — Metadata và object

Đọc được `List<String>[]` từ field có chứng minh array runtime chỉ chứa các list của String không?

**Đáp án:** Không. Generic metadata không tự áp dụng runtime validation cho content.

### Bài 12 — Type walker

Vì sao `T extends Comparable<T>` có thể gây vòng lặp khi mở rộng bounds?

**Đáp án:** Bound `Comparable<T>` chứa lại chính type variable `T`.

### Bài 13 — Exception

Ghi `List<Integer>` qua một alias `Object[]` đến array runtime `List[]` có thể thành công không?

**Đáp án:** Có, vì runtime store check chỉ thấy raw `List`; việc dùng như `List<String>` về sau mới có thể thất bại.

### Bài 14 — `getTypeName`

Có nên parse `Type.getTypeName()` bằng các phép tách chuỗi đơn giản để xây type validator không?

**Đáp án:** Không. Nên duyệt cây `Type` để giữ các nested arguments, bounds, owner types và arrays.

## 29. Checklist thực hành

1. Xác định declaration cần đọc: field, method parameter, return type, superclass hoặc interface.
2. Dùng API **generic reflection** thay vì chỉ lấy runtime raw `Class`.
3. Kiểm tra `instanceof` trước khi cast `Type`.
4. Với `ParameterizedType`, đọc `getRawType`, `getActualTypeArguments`, và owner type khi cần.
5. Với `WildcardType`, đọc **cả** upper và lower bounds.
6. Đừng đồng nhất unbounded `?` với `Object` chính xác.
7. Với `GenericArrayType`, duyệt `getGenericComponentType` từng cấp.
8. Xét mảng nhiều chiều và generic components lồng nhau.
9. Phân biệt `TypeVariable<?>` và `WildcardType`.
10. Chặn đệ quy vô hạn với self-referential type-variable bounds.
11. Không xem metadata reflection là chứng minh các phần tử runtime đáp ứng generic argument.
12. Không dùng unchecked casts để hợp thức hóa `new List<String>[]`.
13. Khi cần mảng runtime, xét component type reifiable và các array factory hợp lệ.
14. Khi cần lưu nhiều danh sách, cân nhắc `List<List<String>>` thay cho generic arrays.
15. Viết test cho các cây gồm `?`, `? super`, `? extends`, `T[]`, `List<?>[]`, `T[][]` và nested `Map`.
16. Khi xử lý dữ liệu chưa tin cậy, tách bước đọc `Type` khỏi bước parse/validate.

## 30. Tổng kết và tài liệu chuẩn

**`WildcardType`** là đối tượng reflection đại diện wildcard type argument và cung cấp `getUpperBounds()` cùng `getLowerBounds()`. **`GenericArrayType`** mô tả mảng có generic component như `T[]` hoặc `List<String>[]`, cung cấp `getGenericComponentType()`.

Hai loại `Type` này thường nằm bên trong các cây khai báo phức tạp cùng `ParameterizedType`, `TypeVariable` và `Class`. Chúng là công cụ quan trọng khi viết framework xử lý generic signatures.

Quan trọng nhất là phân biệt **thông tin generic ở declaration** với **runtime class của object**. Một `Field` có thể khai báo `List<String>[]` và được reflection mô tả đầy đủ, nhưng array store check vẫn không biết type argument `String` của từng list. Java dùng type erasure; khả năng mô tả không đồng nghĩa khả năng xác minh hoặc tạo object.

Đọc cây `Type` có cấu trúc, không parse chuỗi tên kiểu; kiểm tra `instanceof` trước cast; xử lý bounds và các cấp mảng; bảo toàn an toàn kiểu khi tạo hoặc chuyển đổi dữ liệu.

Tài liệu đối chiếu:

- [Java SE 17 — `WildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html): API upper/lower bounds.
- [Java SE 17 — `GenericArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html): API generic component type.
- [Java SE 17 — `Type`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html): interface chung.
- [Java SE 17 — `ParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html): raw type và actual arguments.
- [Java SE 17 — `TypeVariable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html): type variables và bounds.
- [JLS §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): wildcard type arguments.
- [JLS §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): reifiable generic types.
- [JLS §10 — Arrays](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html): mảng và kiểm tra runtime.
- [JLS §15.10.1 — Array Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.1): quy tắc array creation.
- [JVMS §4.7.9 — Signature Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.9): generic declaration metadata.