# Đọc tên kiểu bằng `Type.getTypeName()` thay vì ép mọi `Type` sang `Class`

## 1. Vấn đề thường gặp trong Java Reflection

Trong Java Reflection, nhiều API mô tả kiểu generic bằng giao diện **`java.lang.reflect.Type`**. Khi cần ghi log, hiển thị chữ ký method, mô tả field hoặc chẩn đoán metadata, ta thường muốn đọc **tên của kiểu**.

Cách dễ gây lỗi là giả định mọi `Type` đều là một `Class<?>`:

```java
Type type = field.getGenericType();
String name = ((Class<?>) type).getName(); // Có thể ClassCastException!
```

Đây là **mảnh mã minh họa bên trong method**, nơi `field` là một `Field` hợp lệ. Nó chỉ đúng nếu đối tượng `type` thực sự triển khai `Class<?>`. Nếu field được khai báo `List<String>`, `getGenericType()` thường trả `ParameterizedType`; nếu kiểu là `T`, nó có thể trả `TypeVariable`; với `T[]` có thể là `GenericArrayType`. Ép các đối tượng này thành `Class<?>` gây `ClassCastException`.

Để **đọc chuỗi mô tả kiểu**, hãy gọi trực tiếp:

```java
Type type = field.getGenericType();
String name = type.getTypeName(); // Hoạt động với mọi triển khai Type hợp lệ
```

`Type.getTypeName()` được định nghĩa trên chính giao diện `Type` từ **Java 8**. Nó trả một chuỗi mô tả kiểu, bao gồm thông tin tham số kiểu khi thích hợp; triển khai mặc định của `Type` dùng `toString()`. Vì vậy có thể gọi nó mà không cần ép kiểu sang `Class`.

**Phân biệt rõ hai mục đích:**

- Chỉ cần **hiển thị tên / ghi log / thông báo lỗi** → ưu tiên `type.getTypeName()`.
- Cần **phân tích, so sánh hoặc biến đổi cấu trúc generic** → kiểm tra subtype của `Type` và dùng API tương ứng (`getActualTypeArguments()`, `getBounds()`, `getGenericComponentType()`...). Một chuỗi đẹp không thay thế mô hình dữ liệu kiểu.

## 2. `Type` không đồng nghĩa với `Class<?>`

`Type` là giao diện chung cho các dạng kiểu mà Reflection biểu diễn. `Class<?>` **chỉ là một dạng cụ thể** của `Type`.

| Dạng `Type` | Khai báo ví dụ | Ví dụ của `getTypeName()` | Cách đọc cấu trúc |
| --- | --- | --- | --- |
| `Class<?>` | `String`, `int`, `String[]`, raw `List` | `java.lang.String[]` | `Class` API: `isArray()`, `getComponentType()`... |
| `ParameterizedType` | `List<String>`, `Map<String, Integer>` | `java.util.List<java.lang.String>` | `getRawType()`, `getActualTypeArguments()`, `getOwnerType()` |
| `TypeVariable<?>` | `T` trong `<T extends Number>` | `T` | `getBounds()`, `getGenericDeclaration()`, `getName()` |
| `GenericArrayType` | `T[]`, `List<String>[]` | `T[]`, `java.util.List<java.lang.String>[]` | `getGenericComponentType()` |
| `WildcardType` | `? extends Number`, `? super Integer` | `? extends java.lang.Number` | `getUpperBounds()`, `getLowerBounds()` |

`WildcardType` thường nằm **bên trong đối số kiểu** của `ParameterizedType`, như phần `? extends Number` trong `Map<String, ? extends Number>`. Nó không nhất thiết là `Type` trực tiếp của toàn bộ field/parameter, nhưng có thể lấy ra qua `getActualTypeArguments()`.

Hai điểm dễ nhầm:

1. **`String[]` thường là `Class<?>`**, còn **`T[]` có thể là `GenericArrayType`**. Thấy dấu `[]` trong tên không đủ để suy ra subtype của `Type`.
2. `TypeVariable.getTypeName()` thường chỉ in tên `T`, **không tự liệt kê bound** `Number`/`Comparable<T>`. Muốn biết bounds, phải gọi `getBounds()`.

`ParameterizedType`, `TypeVariable`, `GenericArrayType` và `WildcardType` đều có thể trả chuỗi hiển thị hợp lệ qua cùng phương thức `getTypeName()`; không cần tạo các chuỗi khác nhau bằng ép kiểu.

## 3. Ví dụ Java 17+ đầy đủ: năm dạng `Type`

Tạo tệp **`TypeNameDemo.java`**:

```java
import java.lang.reflect.*;
import java.util.*;

public class TypeNameDemo<T extends Number> {
    List<String> words;
    Map<String, ? extends Number> scores;
    T value;
    T[] history;
    List<String>[] groups;
    String[] labels;

    public void process(List<Integer> input, List<? super Integer> sink) {}

    private static String category(Type type) {
        if (type instanceof Class<?>) return "Class";
        if (type instanceof ParameterizedType) return "ParameterizedType";
        if (type instanceof TypeVariable<?>) return "TypeVariable";
        if (type instanceof GenericArrayType) return "GenericArrayType";
        if (type instanceof WildcardType) return "WildcardType";
        return "Other";
    }

    private static void show(String label, Type type) {
        System.out.println(label + ": " + type.getTypeName()
                + " [" + category(type) + "]");
    }

    public static void main(String[] args) throws Exception {
        for (String name : List.of("words", "scores", "value",
                "history", "groups", "labels")) {
            Field field = TypeNameDemo.class.getDeclaredField(name);
            show(name, field.getGenericType());
            System.out.println("  erased: " + field.getType().getTypeName());
        }

        ParameterizedType map = (ParameterizedType)
                TypeNameDemo.class.getDeclaredField("scores").getGenericType();
        show("map raw", map.getRawType());
        Type wildcard = map.getActualTypeArguments()[1];
        show("wildcard", wildcard);

        Method method = TypeNameDemo.class.getDeclaredMethod(
                "process", List.class, List.class);
        Type[] parameters = method.getGenericParameterTypes();
        show("process param 0", parameters[0]);
        show("process param 1", parameters[1]);

        Type generic = TypeNameDemo.class.getDeclaredField("words")
                .getGenericType();
        System.out.println("words instanceof Class: "
                + (generic instanceof Class<?>));
    }
}
```

Biên dịch/chạy:

```bash
javac TypeNameDemo.java
java TypeNameDemo
```

**Kết quả đã kiểm chứng** khi biên dịch/chạy với JDK hỗ trợ Java 17+:

```text
words: java.util.List<java.lang.String> [ParameterizedType]
  erased: java.util.List
scores: java.util.Map<java.lang.String, ? extends java.lang.Number> [ParameterizedType]
  erased: java.util.Map
value: T [TypeVariable]
  erased: java.lang.Number
history: T[] [GenericArrayType]
  erased: java.lang.Number[]
groups: java.util.List<java.lang.String>[] [GenericArrayType]
  erased: java.util.List[]
labels: java.lang.String[] [Class]
  erased: java.lang.String[]
map raw: java.util.Map [Class]
wildcard: ? extends java.lang.Number [WildcardType]
process param 0: java.util.List<java.lang.Integer> [ParameterizedType]
process param 1: java.util.List<? super java.lang.Integer> [ParameterizedType]
words instanceof Class: false
```

Ví dụ cố ý lấy tên field **theo danh sách cố định**, không dựa vào thứ tự ngẫu nhiên của `getDeclaredFields()`. Vì vậy kết quả in ra có thứ tự xác định.

### Diễn giải kết quả

- `words` khai báo `List<String>`: `Field.getType()` chỉ có erasure `List.class`, còn `Field.getGenericType()` giữ kiểu có argument `String`. `getTypeName()` in đầy đủ `java.util.List<java.lang.String>`.
- `scores` có hai generic arguments; argument thứ hai là wildcard `? extends Number`. Kiểu toàn field là `ParameterizedType`; chỉ khi đọc `map.getActualTypeArguments()[1]` mới có `WildcardType` trực tiếp.
- `value` có kiểu `T extends Number`. Generic representation `TypeVariable` in `T`; kiểu đã erasure là `Number` (bound đầu tiên).
- `history` là mảng của `T`: `getGenericType()` là `GenericArrayType` biểu diễn `T[]`, trong khi `getType()` là `Number[].class`.
- `groups` là `List<String>[]`. Vì thành phần mảng là generic parameterized type, generic representation là `GenericArrayType`; erasure của nó là `List[]`.
- `labels` là `String[]` thông thường, nên kiểu generic cũng chính là `Class<?>`.
- `process` cho thấy `Method.getGenericParameterTypes()` trả `Type[]` cho danh sách tham số. Cả `List<Integer>` và `List<? super Integer>` được hiển thị chính xác mà không cần ép `Type` về `Class`.
- `words instanceof Class: false` là bằng chứng cụ thể tại sao `((Class<?>) field.getGenericType())` không an toàn.

Dùng `Class<?>` khi cần kiểu runtime đã erasure là hợp lý; vấn đề nằm ở việc **ép mọi `Type` thành `Class<?>` mà không kiểm tra**.

## 4. Lấy `Type` từ những API nào?

Các phương thức sau xuất hiện thường xuyên khi viết thư viện mapping, dependency injection, serializer hoặc công cụ phân tích chữ ký:

| Nguồn metadata | Phương thức | Kết quả |
| --- | --- | --- |
| Field | `Field.getGenericType()` | Một `Type` mô tả kiểu khai báo của field |
| Method | `Method.getGenericReturnType()` | Một `Type` mô tả kiểu trả về generic |
| Method/Constructor | `Executable.getGenericParameterTypes()` | `Type[]` mô tả các formal parameters |
| Method/Constructor | `Executable.getGenericExceptionTypes()` | `Type[]` mô tả các kiểu trong `throws` |
| Class | `Class.getGenericSuperclass()` | `Type` biểu diễn superclass có generic args, hoặc `null` khi không có superclass theo hợp đồng |
| Class | `Class.getGenericInterfaces()` | `Type[]` biểu diễn các generic superinterfaces |
| Parameter | `Parameter.getParameterizedType()` | Một `Type` của parameter |
| ParameterizedType | `getActualTypeArguments()` | `Type[]` của đối số kiểu |
| TypeVariable | `getBounds()` | `Type[]` của bounds |
| WildcardType | `getUpperBounds()` / `getLowerBounds()` | `Type[]` của upper/lower bounds |
| GenericArrayType | `getGenericComponentType()` | `Type` của thành phần mảng |

Có thể in nhiều kết quả mà không ép kiểu:

```java
// Các mảnh mã đặt trong một method có Field field, Method method hợp lệ.
System.out.println(field.getGenericType().getTypeName());
System.out.println(method.getGenericReturnType().getTypeName());

for (Type parameterType : method.getGenericParameterTypes()) {
    System.out.println(parameterType.getTypeName());
}
```

Đối với API **có thể trả `null`**, kiểm tra trước khi gọi. Ví dụ `Object.class.getGenericSuperclass() == null`, vì `Object` không có superclass; primitive, void và interface cũng có những trường hợp không có superclass. Không viết `someClass.getGenericSuperclass().getTypeName()` khi chưa chắc kết quả khác `null`.

**Tham số implicit của constructor:** với một số inner-class constructor, `getGenericParameterTypes()` có thể có độ dài khác `getParameterTypes()` do cách metadata generic và tham số implicit/synthetic được biểu diễn. Do đó tránh ghép hai mảng theo cùng index mà không kiểm tra. Việc gọi `getTypeName()` trên từng `Type` đã nhận được vẫn an toàn.

## 5. Muốn đọc cấu trúc: kiểm tra subtype và dùng đúng API

`getTypeName()` cho một **chuỗi để đọc**. Khi muốn biết `List` chứa loại phần tử nào, wildcard có bound gì, hoặc một type variable do declaration nào tạo ra, hãy giữ `Type` và phân nhánh:

```java
// Mảnh phương thức đặt trong một class; cần import java.lang.reflect.*.
static void describe(Type type) {
    System.out.println("type = " + type.getTypeName());

    if (type instanceof Class<?> cls) {
        System.out.println("runtime class = " + cls.getName());
    } else if (type instanceof ParameterizedType p) {
        System.out.println("raw = " + p.getRawType().getTypeName());
        for (Type arg : p.getActualTypeArguments()) {
            System.out.println("argument = " + arg.getTypeName());
        }
    } else if (type instanceof TypeVariable<?> variable) {
        System.out.println("variable = " + variable.getName());
        for (Type bound : variable.getBounds()) {
            System.out.println("bound = " + bound.getTypeName());
        }
    } else if (type instanceof GenericArrayType array) {
        System.out.println("component = "
                + array.getGenericComponentType().getTypeName());
    } else if (type instanceof WildcardType wildcard) {
        for (Type upper : wildcard.getUpperBounds()) {
            System.out.println("upper = " + upper.getTypeName());
        }
        for (Type lower : wildcard.getLowerBounds()) {
            System.out.println("lower = " + lower.getTypeName());
        }
    }
}
```

Đây là **mảnh mã minh họa**, không có `main` độc lập. `instanceof` pattern matching là cú pháp Java 16+, chạy được trên Java 17. Đoạn này chỉ in **một tầng**, không tự đi sâu đệ quy vào generic arguments lồng nhiều cấp. Nếu muốn phân tích `Map<String, List<? extends Number>>`, phải duyệt các `Type` thành phần theo cây.

### Đọc generic arguments

Với `List<String>` trong ví dụ:

```java
Type generic = TypeNameDemo.class.getDeclaredField("words")
        .getGenericType();

if (generic instanceof ParameterizedType p) {
    Type raw = p.getRawType();            // List
    Type element = p.getActualTypeArguments()[0]; // String
    System.out.println(raw.getTypeName());
    System.out.println(element.getTypeName());
}
```

Hai dòng in `java.util.List` và `java.lang.String`. Chỉ ép `ParameterizedType` **sau khi đã xác nhận** kiểu tương ứng; không ép trực tiếp `generic` sang `Class<?>`. Nếu làm việc với `Map<K,V>`, mảng arguments có thể chứa `ParameterizedType`, `TypeVariable` hoặc `WildcardType` lồng nhau.

### Đọc bounds

Một `TypeVariable` như `T` không có đủ thông tin qua chuỗi `"T"`. Ví dụ với `TypeNameDemo<T extends Number>`, `getBounds()` cho `Number`:

```java
Type type = TypeNameDemo.class.getDeclaredField("value").getGenericType();

if (type instanceof TypeVariable<?> variable) {
    System.out.println(variable.getName());
    for (Type bound : variable.getBounds()) {
        System.out.println(bound.getTypeName());
    }
}
```

Các dòng in `T` và `java.lang.Number`. Hai declarations khác nhau có thể dùng cùng tên `T`; chúng không phải cùng một type variable. Nếu xây mô hình generic nghiêm ngặt, dùng `getGenericDeclaration()`/định danh declaration thay vì chỉ so chuỗi `"T"`.

Với wildcard `? super Integer`, `getLowerBounds()` nêu `Integer`; với `? extends Number`, `getUpperBounds()` nêu `Number`. Wildcard không giới hạn tường minh thường có upper bound mặc định `Object`, nhưng chuỗi hiển thị có thể chỉ là `?`. Vì vậy không suy diễn bounds bằng cách tách chuỗi.

### Đọc mảng generic

Đối với `T[]` hoặc `List<String>[]`, hãy dùng `GenericArrayType.getGenericComponentType()`. Với `String[]`, kiểu là `Class<?>` và lấy phần tử bằng `Class.getComponentType()`. Một tiện ích phân tích mảng tổng quát phải xử lý **cả hai nhánh**.

## 6. So sánh `getTypeName()`, `getName()`, `getSimpleName()` và `getCanonicalName()`

Đây là các API dễ bị nhầm do cùng chứa chữ “name”:

| API | Được định nghĩa trên | Dùng cho | Giới hạn |
| --- | --- | --- | --- |
| `Type.getTypeName()` | `Type` | Chuỗi dễ đọc cho **mọi dạng `Type`** | Không bảo đảm là tên `Class` có thể nạp hoặc cú pháp canonical |
| `Class.getTypeName()` | `Class` (ghi đè triển khai `Type`) | Hiển thị tên kiểu kể cả array/primitive | Chỉ áp dụng trực tiếp khi `Type` thực sự là `Class` |
| `Class.getName()` | `Class` | Tên kiểu runtime; thường là binary name với class thông thường, JVM descriptor dạng đặc biệt với mảng | Không giữ `List<String>` từ generic `ParameterizedType` |
| `Class.getSimpleName()` | `Class` | Tên ngắn kiểu nguồn, ví dụ `String` | Không đại diện generic arguments; anonymous class có tên ngắn rỗng |
| `Class.getCanonicalName()` | `Class` | Tên chuẩn nếu kiểu có canonical name | Có thể trả `null` với local/anonymous/hidden classes và một số array tương ứng |

Ví dụ một mảng:

```java
System.out.println(String[].class.getTypeName());
System.out.println(String[].class.getName());
```

Kết quả:

```text
java.lang.String[]
[Ljava.lang.String;
```

`getTypeName()` có thể dễ đọc hơn trong log, nhưng không vì vậy mà hai API trở nên thay thế được ở mọi chỗ. Chẳng hạn, `Class.forName(...)` dành cho **binary names** của class thông thường (và tên descriptor thích hợp cho mảng); không nhận `"java.util.List<java.lang.String>"` để tạo một `Class` của `List<String>`. Trong Java không tồn tại một `Class` riêng cho mỗi tham số hóa như `List<String>` và `List<Integer>`.

Với nested types hoặc triển khai `Type` cụ thể, biểu diễn `getTypeName()` có thể dùng ký tự `$`, dấu `<...>`, `? extends` hoặc `[]`. Đây là **chuỗi mô tả do API cung cấp**, không phải định dạng trao đổi dữ liệu đã được cam kết tương đương Java source canonical name.

## 7. Trường hợp dùng đúng khi cần `Class<?>`

Đừng tránh `Class` trong mọi trường hợp: `Class<?>` là lựa chọn đúng khi thao tác cần **runtime class**, ví dụ `getDeclaredMethod`, `isAssignableFrom`, `isInstance`, `Field.getType` hoặc `Method.getReturnType`.

```java
// Mảnh mã minh họa:
Field field = TypeNameDemo.class.getDeclaredField("words");

Class<?> erased = field.getType();
System.out.println(erased.getTypeName()); // java.util.List

Type declared = field.getGenericType();
System.out.println(declared.getTypeName()); // java.util.List<java.lang.String>
```

Hai kết quả diễn tả hai câu hỏi khác nhau: **erased runtime class** và **generic declaration**.

Đối với `Class.getDeclaredMethod(String, Class<?>...)`, cần truyền erased parameter classes, không thể truyền `Type[]` trực tiếp. Ví dụ method `process(List<Integer>, List<? super Integer>)` trong chương trình:

```java
Method method = TypeNameDemo.class.getDeclaredMethod(
        "process", List.class, List.class);
```

Dùng `List.class` hai lần vì cả hai tham số đã erasure thành `List`. **Không có cú pháp `List<String>.class`**. `getTypeName()` chỉ là phép mô tả; nó không khôi phục các class generic tham số hóa ở runtime.

Nếu nhận `Type type` chưa biết subtype, chỉ cast khi đã kiểm tra:

```java
if (type instanceof Class<?> cls) {
    // Có thể dùng cls để kiểm tra runtime type hoặc lookup.
    System.out.println(cls.getName());
} else {
    // Type này chứa cấu trúc khác: xử lý qua các subtype của Type.
    System.out.println(type.getTypeName());
}
```

Đừng giả định rằng `ParameterizedType.getRawType()` luôn có thể biến mọi `Type` lồng nhau thành `Class<?>` bằng cách cast bừa. Nếu framework cần tính erasure tương ứng cho cả `TypeVariable`, `WildcardType` hay mảng generic, hãy xây thuật toán rõ quy tắc và xử lý giới hạn; `getTypeName()` không thực hiện công việc “erasure” đó.

## 8. Có thể dùng chuỗi `getTypeName()` như một type parser không?

**Không nên** dùng `getTypeName()` như định dạng máy có hợp đồng parsing ổn định. Javadoc mô tả nó là chuỗi **mang thông tin về kiểu**, bao gồm thông tin tham số kiểu; triển khai mặc định của `Type` gọi `toString()`. Hình thức hiển thị không thay thế cấu trúc các đối tượng `Type`.

Những phép xử lý chuỗi dễ sai gồm:

- Tách `List<Map<String, Integer>>` theo dấu phẩy đầu tiên: generic types có thể lồng nhiều cấp.
- Bỏ dấu `<...>` rồi giả định luôn tạo được class với `Class.forName`: tên inner/member và kiểu mảng có quy tắc khác; `T` và wildcard không phải tên class để nạp.
- So `"T"` để đồng nhất type variables từ hai declarations khác nhau: cùng tên chưa chắc cùng biến kiểu.
- Phân tích `? extends Number` bằng substring và bỏ qua bounds lồng nhau/generic owner type.
- Dựa vào tên class triển khai nội bộ của JDK cho `ParameterizedType` thay vì giao diện `java.lang.reflect.ParameterizedType`.

Nếu chỉ cần ghi log hoặc thông báo lỗi, `getTypeName()` rất tiện. Nếu cần mã hóa metadata lâu dài, xây schema chứa category, raw type, type arguments, owner, bounds, component type và thông tin declaration tương ứng. Nếu cần kiểm tra JSON/đối tượng runtime, kiểm tra **giá trị thực** chứ không chỉ chuỗi generic signature.

### Khi không có đủ metadata generic

`Field.getGenericType()`, `Method.getGenericReturnType()` và các API tương tự đọc generic declaration khi class file chứa thông tin cần thiết. Kiểu raw như `List values` không chứa `String` để truy lại; sau type erasure, Reflection không thể nhìn vào instance `List` mà chắc chắn xác định generic argument lúc khai báo ban đầu.

Trong bytecode thiếu/sai generic signature hoặc classpath thiếu kiểu được tham chiếu, một số API generic Reflection có thể ném `GenericSignatureFormatError`, `TypeNotPresentException` hoặc `MalformedParameterizedTypeException`. Những tình huống này khác với `ClassCastException` do code tự ép `Type` không đúng. Một chương trình phân tích bytecode cần báo rõ lỗi metadata, không nên lặng lẽ giả định generic argument là `Object` nếu không có căn cứ.

## 9. Những lỗi lập trình thường gặp

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| `((Class<?>) field.getGenericType()).getName()` | `ClassCastException` nếu là `ParameterizedType` | `field.getGenericType().getTypeName()` để hiển thị |
| `(Class<?>) parameterized.getActualTypeArguments()[0]` | Thất bại nếu argument là wildcard, type variable hoặc parameterized type lồng | Kiểm tra `instanceof` trước khi cast |
| `type.toString()` rồi ép chuỗi theo một định dạng tự đoán | Có thể phá cấu trúc generic phức tạp | `type.getTypeName()` để hiển thị; subtype APIs để phân tích |
| `type.getTypeName()` rồi `Class.forName(name)` | Tên generic/wildcard/variable không phải binary name có thể nạp | Chỉ nạp class theo tên phù hợp hợp đồng của `Class.forName` |
| Cho rằng `getGenericType()` luôn là `ParameterizedType` | Các kiểu nguyên thủy, array thường và raw class trả `Class` | Phân nhánh tất cả dạng `Type` liên quan |
| Cho rằng `TypeVariable.getTypeName()` luôn in cả bounds | Thường chỉ được `T` | Dùng `getBounds()` |
| Dùng `getTypeName()` để suy ra kiểu phần tử của `List` instance | Không phản ánh runtime contents | Kiểm tra metadata declaration và validate dữ liệu riêng |
| Gọi `getGenericSuperclass().getTypeName()` trên `Object` | Có thể `NullPointerException` do superclass là `null` | Kiểm tra `null` trước |

## 10. Bài tập tự kiểm tra

**Bài 1.** Với khai báo `List<String> names`, dự đoán subtype của `getGenericType()` và nội dung của `getTypeName()`. Tại sao cast kết quả thành `Class<?>` thất bại?

**Bài 2.** Với `T extends Number`, đọc generic type của field `T value`. Làm sao lấy `Number` làm bound thay vì chỉ nhận chuỗi `T`?

**Bài 3.** Với `Map<String, ? super Integer> map`, đi từ `ParameterizedType` đến `WildcardType` và in tất cả lower bounds mà không phân tích chuỗi.

**Bài 4.** Với `String[]` và `List<String>[]`, dự đoán loại `Type` và API lấy component type tương ứng.

**Bài 5.** Cho hai method dùng hai biến kiểu `T` khác nhau. Giải thích vì sao so `getTypeName().equals("T")` không chứng minh rằng hai type variables là một declaration.

**Bài 6.** Sửa đoạn sau để vừa in tên kiểu generic vừa tránh `ClassCastException`:

```java
Type[] params = method.getGenericParameterTypes();
for (Type param : params) {
    System.out.println(((Class<?>) param).getName());
}
```

Đáp án cốt lõi:

```java
for (Type param : method.getGenericParameterTypes()) {
    System.out.println(param.getTypeName());
}
```

Đây là **mảnh code bên trong một method** có biến `method` là một `Method` hợp lệ; nếu cần kiểm tra từng generic argument, tiếp tục phân tích subtype của `param`.

**Ghi nhớ:** `Type.getTypeName()` dùng để **mô tả tên kiểu của bất kỳ `Type` nào** mà không ép xuống `Class`. `Class<?>` là **một** triển khai của `Type`. Nếu logic cần hiểu cấu trúc, dùng các interface generic Reflection tương ứng; nếu logic cần erased runtime type, lấy `Class<?>` từ API cung cấp class sau erasure. Ba mục tiêu **hiển thị**, **phân tích generic** và **dùng runtime class** nên được phân biệt rõ ràng.

## 11. Tài liệu tham khảo

- [Java SE 17 — `Type`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html): hợp đồng của `getTypeName()` và các subtype.
- [Java SE 17 — `Field.getGenericType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#getGenericType()): metadata generic của field. 
- [Java SE 17 — `Method.getGenericReturnType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getGenericReturnType()): kiểu trả về generic của method.
- [Java SE 17 — `Executable.getGenericParameterTypes()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html#getGenericParameterTypes()): generic parameters và lưu ý tham số implicit.
- [Java SE 17 — `ParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html), [`TypeVariable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html), [`GenericArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html), [`WildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html): API phân tích cấu trúc `Type`.
- [Java Language Specification, mục 4.6](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): type erasure và cách liên hệ chữ ký generic với runtime types.