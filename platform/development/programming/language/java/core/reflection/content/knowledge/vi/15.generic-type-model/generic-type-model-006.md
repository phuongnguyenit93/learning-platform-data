# WildcardType với upper bound và lower bound trong Java Reflection

Trong Java generics, dấu `?` biểu diễn một **wildcard**: đối số kiểu chưa biết tại một vị trí sử dụng kiểu generic. Ví dụ `List<?>`, `List<? extends Number>` và `List<? super Integer>` đều là những `ParameterizedType` ở cấp `List<...>`, và mỗi dấu `?` bên trong được mô hình hóa bằng `java.lang.reflect.WildcardType`.

`WildcardType` là một nhánh của `java.lang.reflect.Type`. Nó cung cấp hai phương thức quan trọng:

- `Type[] getUpperBounds()`: lấy giới hạn trên của kiểu chưa biết.
- `Type[] getLowerBounds()`: lấy giới hạn dưới của kiểu chưa biết.

Bài học tập trung vào cách đọc **chữ ký generic đã khai báo** bằng Reflection, diễn giải hai mảng bound, đi qua các kiểu generic lồng nhau và phân biệt generic metadata với dữ liệu runtime.

## 1. Ý nghĩa của ba dạng wildcard

| Khai báo | Upper bounds qua Reflection | Lower bounds qua Reflection | Ý nghĩa |
| --- | --- | --- | --- |
| `List<?>` | `[Object]` | `[]` | Một đối số kiểu không xác định |
| `List<? extends Number>` | `[Number]` | `[]` | Đối số kiểu là `Number` hoặc subtype của `Number` |
| `List<? super Integer>` | `[Object]` | `[Integer]` | Đối số kiểu là `Integer` hoặc supertype của `Integer` |

**Upper bound** của `? extends T` là `T`: bất kỳ type argument thực tế nào đều phải thỏa ràng buộc subtype tương ứng. **Lower bound** của `? super T` là `T`: type argument thực tế phải là `T` hoặc supertype của `T`.

Với `?`, upper bound mặc định là `Object` và không có lower bound. Với `? super Integer`, upper bound mặc định **vẫn là `Object`**, còn lower bound là `Integer`. Vì vậy đừng kết luận `getUpperBounds()` rỗng khi khai báo dùng `super`.

Một điểm rất dễ nhầm: `getLowerBounds().length == 0` **không** chứng minh wildcard là `?`; `? extends Number` cũng có mảng lower rỗng. Ngược lại, upper bound `Object` không đủ để kết luận khai báo chỉ là `?`, vì `? super T` và `? extends Object` cũng có cùng giới hạn trên.

## 2. WildcardType nằm trong cây Type ở đâu?

Các kiểu mô tả generic thuộc `java.lang.reflect.Type` bao gồm:

```text
Type
├── Class<?>            ví dụ String.class, Number.class
├── ParameterizedType   ví dụ List<String>, List<? extends Number>
├── TypeVariable<?>     ví dụ T trong class Box<T>
├── WildcardType        ví dụ ?, ? extends Number, ? super Integer
└── GenericArrayType    ví dụ T[] trong chữ ký generic
```

Nếu field khai báo `List<? extends Number> numbers`, lời gọi `Field.getGenericType()` trả một `ParameterizedType` đại diện cho **toàn bộ** `List<? extends Number>`. Để lấy `WildcardType` cần vào `getActualTypeArguments()[0]`:

```text
Field: List<? extends Number> numbers
                 |
                 v
       field.getGenericType()
                 |
                 v
    ParameterizedType: List<? extends Number>
                 |
                 v
       getActualTypeArguments()[0]
                 |
                 v
      WildcardType: ? extends Number
             /                 \
            v                   v
    getUpperBounds()       getLowerBounds()
       [Number]                 []
```

Không ép trực tiếp `field.getGenericType()` sang `WildcardType`, vì kiểu field ở đây là `ParameterizedType`. Với `List<String>`, đối số đầu tiên là `String.class`, **không** phải `WildcardType`. Với `List<T>`, đối số đầu tiên có thể là `TypeVariable`.

## 3. Chương trình Java 17+ đầy đủ và stdout

Lưu mã vào tệp `WildcardTypeDemo.java`. Chương trình tra cứu field, tham số method, wildcard lồng nhau và bound là generic type; sau đó minh họa thao tác đọc/ghi theo `extends`/`super`.

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.WildcardType;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class WildcardTypeDemo {
    static class Examples {
        List<?> anything;
        List<? extends Number> numbers;
        List<? super Integer> integers;
        List<? extends Comparable<String>> comparable;
        Map<String, ? super List<String>> mappings;
        List<List<? extends Number>> nested;

        void accept(List<? super Integer> values) {
        }
    }

    static Type argument(String fieldName, int index)
            throws NoSuchFieldException {
        Field field = Examples.class.getDeclaredField(fieldName);
        Type generic = field.getGenericType();
        if (!(generic instanceof ParameterizedType parameterized)) {
            throw new IllegalArgumentException("Not parameterized");
        }
        return parameterized.getActualTypeArguments()[index];
    }

    static String format(Type[] bounds) {
        return Arrays.stream(bounds)
                .map(Type::getTypeName)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    static void printBounds(String label, Type type) {
        if (!(type instanceof WildcardType wildcard)) {
            throw new IllegalArgumentException("Not wildcard");
        }
        System.out.println(label
                + ": upper=" + format(wildcard.getUpperBounds())
                + "; lower=" + format(wildcard.getLowerBounds()));
    }

    public static void main(String[] args) throws Exception {
        printBounds("unbounded", argument("anything", 0));
        printBounds("extends", argument("numbers", 0));
        printBounds("super", argument("integers", 0));
        printBounds("parameterizedUpper",
                argument("comparable", 0));
        printBounds("parameterizedLower",
                argument("mappings", 1));

        Type inner = argument("nested", 0);
        ParameterizedType innerList = (ParameterizedType) inner;
        printBounds("nested",
                innerList.getActualTypeArguments()[0]);

        Method method = Examples.class.getDeclaredMethod(
                "accept", List.class);
        ParameterizedType parameter = (ParameterizedType)
                method.getGenericParameterTypes()[0];
        printBounds("method",
                parameter.getActualTypeArguments()[0]);

        System.out.println("erased="
                + Examples.class.getDeclaredField("numbers")
                        .getType().getName());

        List<? extends Number> source = List.of(1, 2);
        Number first = source.get(0);
        List<Number> storage = new ArrayList<>();
        List<? super Integer> target = storage;
        target.add(7);
        Object stored = target.get(0);

        System.out.println("producerRead=" + first);
        System.out.println("consumerRead=" + stored);
    }
}
```

Tại thư mục chứa tệp, biên dịch và chạy:

```bash
javac WildcardTypeDemo.java
java WildcardTypeDemo
```

Đầu ra dự kiến:

```text
unbounded: upper=[java.lang.Object]; lower=[]
extends: upper=[java.lang.Number]; lower=[]
super: upper=[java.lang.Object]; lower=[java.lang.Integer]
parameterizedUpper: upper=[java.lang.Comparable<java.lang.String>]; lower=[]
parameterizedLower: upper=[java.lang.Object]; lower=[java.util.List<java.lang.String>]
nested: upper=[java.lang.Number]; lower=[]
method: upper=[java.lang.Object]; lower=[java.lang.Integer]
erased=java.util.List
producerRead=1
consumerRead=7
```

**Diễn giải từng trường hợp:**

1. `anything` là `List<?>`, nên giới hạn trên `Object`, không có giới hạn dưới.
2. `numbers` là `List<? extends Number>` nên giới hạn trên `Number`.
3. `integers` là `List<? super Integer>` nên giới hạn dưới `Integer`, giới hạn trên ngầm định là `Object`.
4. Bound của `? extends Comparable<String>` không phải `Class<?>` đơn giản mà là một `ParameterizedType`; `getTypeName()` cho ra `java.lang.Comparable<java.lang.String>`.
5. Với `Map<String, ? super List<String>>`, wildcard nằm ở **đối số kiểu thứ hai** của `Map`; lower bound `List<String>` cũng là một `ParameterizedType`.
6. `List<List<? extends Number>>` có một tầng `List` bên trong. Phải đi qua đối số kiểu là `List<? extends Number>` trước, rồi mới tìm wildcard `? extends Number`.
7. `accept(List<? super Integer>)` được tra cứu bằng `getDeclaredMethod("accept", List.class)` vì các tham số generic bị erase ở chữ ký method dùng cho lookup. Sau đó `getGenericParameterTypes()` mới cung cấp chữ ký generic chứa wildcard.
8. `Field.getType()` trả `java.util.List` cho field `List<? extends Number>`; nó không chứa thông tin wildcard. `Field.getGenericType()` mới cho phép lấy `ParameterizedType`.
9. Hai dòng cuối dùng collection thông thường: `? extends Number` cho phép đọc như `Number`; `? super Integer` cho phép thêm `Integer` và đọc an toàn như `Object`. Đây là các ràng buộc được compiler kiểm tra, không phải Reflection đang kiểm soát collection ở runtime.

Chương trình dùng pattern matching cho `instanceof` có trong Java 17 và định dạng bound qua `Type.getTypeName()`, tránh phụ thuộc vào `toString()` của một implementation cụ thể.

## 4. Đọc bound qua Type[] thay vì ép về Class[]

Cả `getUpperBounds()` và `getLowerBounds()` đều trả về **`Type[]`**. Các phần tử có thể là `Class<?>` hoặc các biểu diễn generic phức tạp hơn, đặc biệt là `ParameterizedType`. Không viết code giả định mọi bound đều là `Class<?>`:

```java
// Đoạn minh họa khi đã có đối tượng WildcardType wildcard:
for (Type upper : wildcard.getUpperBounds()) {
    System.out.println(upper.getTypeName());
    if (upper instanceof ParameterizedType parameterized) {
        System.out.println(parameterized.getRawType().getTypeName());
    }
}

for (Type lower : wildcard.getLowerBounds()) {
    System.out.println(lower.getTypeName());
}
```

Đoạn này **không phải chương trình độc lập**; nó cần biến `wildcard` và các import `Type`, `ParameterizedType`. Có thể còn gặp `TypeVariable` hoặc những dạng `Type` khác trong metadata phức tạp. Vì thế, khi cần xử lý nghiêm túc, hãy duyệt toàn bộ mảng `Type[]` và phân loại từng phần tử bằng `instanceof`.

Trong cú pháp Java nguồn thường gặp, `? extends T` cho upper bound `T` còn `? super T` cho lower bound `T`. Không nên viết code suy luận tuyệt đối “có upper bound nghĩa là extends”: cả wildcard không ràng buộc và wildcard `super` đều có upper bound mặc định `Object`. Khi Reflection mô tả các bounds, nó phản ánh ý nghĩa kiểu, không nhất thiết lưu lại mọi chi tiết cú pháp người viết đã dùng.

## 5. Tìm wildcard trong field, method và generic superclass/interface

Bước đầu tiên luôn là chọn API Reflection **generic**, không dùng API chỉ trả raw class:

| Vị trí khai báo | API đọc generic metadata | Cách tìm wildcard |
| --- | --- | --- |
| Field `List<? extends Number> values` | `Field.getGenericType()` | `ParameterizedType.getActualTypeArguments()` |
| Parameter `void take(List<? super Integer> values)` | `Method.getGenericParameterTypes()[i]` | Lấy đối số kiểu của `ParameterizedType` |
| Return type `List<?> load()` | `Method.getGenericReturnType()` | Lấy đối số kiểu của `ParameterizedType` |
| `class Child extends Parent<? extends Number>` | `Class.getGenericSuperclass()` | Kiểm tra `ParameterizedType` |
| `class HandlerImpl implements Handler<? super Integer>` | `Class.getGenericInterfaces()` | Kiểm tra từng `Type` trong mảng |

Ví dụ khai báo return type:

```java
public List<? extends Number> find() {
    return List.of(1, 2);
}
```

Với biến `Method method` trỏ đúng vào `find`, logic đọc là:

```java
Type result = method.getGenericReturnType();
if (result instanceof ParameterizedType parameterized) {
    Type first = parameterized.getActualTypeArguments()[0];
    if (first instanceof WildcardType wildcard) {
        System.out.println(
                wildcard.getUpperBounds()[0].getTypeName());
    }
}
```

Hai đoạn trên là **minh họa ngữ cảnh**, không phải một chương trình đầy đủ: cần đặt method vào class, lấy `Method` tương ứng và import các loại `Type` cần thiết. Trong trường hợp nêu trên, dòng in là `java.lang.Number`.

Lưu ý sự khác biệt giữa `Method.getParameterTypes()` (trả `Class<?>[]` sau erasure) và `getGenericParameterTypes()` (trả `Type[]` giữ metadata generic). Tương tự, `Field.getType()` và `getGenericType()` phục vụ hai mục tiêu khác nhau.

## 6. WildcardType không phải TypeVariable

Ví dụ:

```java
class Box<T extends Number> {
    T element;
    List<? extends Number> elements;
}
```

- `T` trong khai báo `Box<T extends Number>` là **type variable có tên**, được mô hình hóa bằng `TypeVariable<?>`. Khi đọc `element` qua `getGenericType()`, có thể gọi `TypeVariable.getBounds()` để biết `T` có bound `Number`.
- `? extends Number` trong `List<? extends Number>` là một **wildcard** được mô hình hóa bằng `WildcardType` khi đi vào đối số kiểu của `ParameterizedType`.

Nếu field là `List<T>`, đối số kiểu là `TypeVariable`, không phải wildcard — mặc dù `T` có thể có cùng bound `Number`. Vì thế không ép mọi đối số generic có `extends` thành `WildcardType`. Type variable là tham số có tên được tái sử dụng trong phạm vi generic declaration; wildcard là một đối số kiểu chưa biết ở **vị trí sử dụng**.

Điều này ảnh hưởng tới công cụ giải kiểu: để giải `T` theo một subclass cụ thể, có thể phải đọc các tham số generic của superclass/interface và lập ánh xạ type variable. Chỉ gọi `WildcardType.getUpperBounds()` không giải được một `TypeVariable`.

## 7. PECS: vì sao extends để đọc và super để ghi?

Quy tắc **Producer Extends, Consumer Super (PECS)** mô tả một cách chọn wildcard theo vai trò của collection:

**`? extends T`** thường phù hợp khi API chỉ cần **đọc** dữ liệu như `T`. Ví dụ:

```java
static double sum(List<? extends Number> numbers) {
    double result = 0;
    for (Number number : numbers) {
        result += number.doubleValue();
    }
    return result;
}
```

Với `List<? extends Number>`, type argument thực tế có thể là `Integer`, `Double` hoặc `Number`. Không được thêm một giá trị `Number` bất kỳ vì có thể không hợp với type argument chưa biết; trường hợp đặc biệt `null` vẫn có thể được thêm.

**`? super T`** phù hợp khi API cần **đưa vào** giá trị kiểu `T`:

```java
static void appendOne(List<? super Integer> destination) {
    destination.add(1);
}
```

Collection có thể thực tế là `List<Integer>`, `List<Number>` hoặc `List<Object>`; cả ba đều nhận được `Integer`. Nhưng khi đọc từ `List<? super Integer>`, kiểu chung được bảo đảm là `Object`, không thể tự động gán cho `Integer` nếu không có kiểm tra/ép kiểu.

**`?`** dùng khi code không cần biết type argument cụ thể. Có thể đọc như `Object`, nhưng không thể thêm tùy ý một giá trị khác `null`.

Hai method trong phần này là **mã minh họa**, cần import `java.util.List` và đặt trong class. `WildcardType` chỉ giúp Reflection **quan sát** chữ ký khai báo; nó không thực thi quy tắc PECS ở runtime. Compiler mới là nơi kiểm tra phần lớn ràng buộc generics trong source Java.

## 8. Type erasure và giới hạn của generic metadata

Giả sử code tạo hai object:

```java
List<String> names = new ArrayList<>();
List<Integer> counts = new ArrayList<>();
```

Trong tình huống này, `names.getClass()` và `counts.getClass()` đều là `java.util.ArrayList.class`. Đối số kiểu `String` hay `Integer` của từng biến không tự tồn tại như thuộc tính runtime có thể truy vấn từ object bằng `getClass()`.

Ngược lại, chữ ký của **field được khai báo** là `List<? super Integer>` vẫn có thể được lưu trong bytecode, cho phép `Field.getGenericType()` đọc được wildcard. Phải phân biệt:

1. **Runtime class của object** — ví dụ `ArrayList.class`.
2. **Chữ ký generic được khai báo** — ví dụ `List<? extends Number>`.
3. **Các phần tử thực tế trong collection** — có thể cần kiểm tra từng giá trị; generic signature không thay thế validation.

Raw types, unchecked casts hoặc bytecode không tuân thủ generic type safety có thể phá giả định của source-level generics. Đừng xem `getUpperBounds()` là bằng chứng rằng tất cả phần tử runtime trong một collection đều phù hợp với bound.

Khi phân tích class file không nhất quán hoặc có kiểu không còn tồn tại, các API generic có thể phát sinh `TypeNotPresentException`, `MalformedParameterizedTypeException` hoặc `GenericSignatureFormatError` tùy API/ngữ cảnh. Ngoại lệ `ClassCastException` khi bạn ép `ParameterizedType` sang `WildcardType` lại là lỗi logic phân nhánh `Type` của chính ứng dụng.

## 9. Các nhầm lẫn thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| `getUpperBounds()` của `? super Integer` là mảng rỗng | Upper bound ngầm định là `Object` |
| `getLowerBounds()` rỗng nghĩa là `?` | `? extends T` cũng có lower bound rỗng |
| `? extends Number` chỉ tương ứng đúng `Number` | Có thể tương ứng subtype của `Number` |
| `? super Integer` đọc ra chắc chắn `Integer` | Đọc theo type safety chỉ được bảo đảm là `Object` |
| `Field.getGenericType()` của `List<?>` là `WildcardType` | Nó là `ParameterizedType`; wildcard là type argument bên trong |
| Mọi bound đều là `Class<?>` | Bound có thể là `ParameterizedType` như `Comparable<String>` |
| `T extends Number` và `? extends Number` đều là wildcard | `T` là `TypeVariable`, `?` là `WildcardType` |
| `Field.getType()` cho biết wildcard | `getType()` trả raw/erased class; dùng `getGenericType()` |
| Có thể viết `List<?>.class` | Java không có class literal cho parameterized type; đọc từ declaration |
| Reflection kiểm tra type argument thật của mọi collection object | Reflection đọc metadata khai báo, không thay thế generic type checking ở compile time |

## 10. Quy trình áp dụng khi xây công cụ đọc generic

1. Xác định nơi chứa **chữ ký**: field, parameter, return type, superclass hay interface.
2. Dùng API `getGeneric...` phù hợp để nhận `Type`.
3. Phân nhánh bằng `instanceof`: `ParameterizedType` để đi vào type arguments; `WildcardType` để đọc upper/lower; `TypeVariable` để đọc generic parameter bounds.
4. Với generic lồng nhau như `List<List<? extends Number>>`, đi từng tầng `ParameterizedType`, không giả định wildcard luôn nằm ở chỉ số đầu tiên của tầng ngoài.
5. Duyệt toàn bộ `Type[]` của upper/lower bounds, giữ thông tin `ParameterizedType` khi bound còn chứa type argument.
6. Diễn giải theo `extends`/`super` và nhu cầu đọc/ghi thực tế; không dùng Reflection metadata như phép xác thực phần tử runtime.

**Ghi nhớ:** `WildcardType` biểu diễn **`?` bên trong chữ ký generic**. `getUpperBounds()` mô tả giới hạn trên; `getLowerBounds()` mô tả giới hạn dưới. `?` có upper `Object` và lower rỗng; `? extends T` dùng upper `T`; `? super T` dùng lower `T` và upper `Object` ngầm định. Để tìm wildcard trong `List<? ...>`, phải đi qua `ParameterizedType.getActualTypeArguments()` trước.