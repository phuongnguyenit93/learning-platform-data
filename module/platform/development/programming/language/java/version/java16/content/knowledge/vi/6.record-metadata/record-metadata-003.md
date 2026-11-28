# RecordComponent.getName, getType và getGenericType

Khi dùng Java Reflection để đọc cấu trúc một record, mỗi phần tử do `Class.getRecordComponents()` trả về là một đối tượng `RecordComponent`. Đối tượng này mô tả một component trong record header. Ba phương thức thường được dùng đầu tiên là **`getName()`**, **`getType()`** và **`getGenericType()`**: chúng lần lượt cho biết tên, kiểu runtime sau khi áp dụng type erasure và kiểu khai báo có giữ thông tin generic.

Bài học này thuộc chương **Metadata record** của module **JAVA_VERSION_JAVA16**. Record và các API reflection liên quan được chuẩn hóa từ Java 16; các ví dụ dưới đây dùng API chuẩn vẫn áp dụng trong các phiên bản Java hiện đại. Trọng tâm là đọc metadata đúng bản chất, đặc biệt phân biệt kiểu đã xóa generic với kiểu khai báo.

## 1. Ba phương thức cung cấp ba phần thông tin

Giả sử có record:

```java
import java.util.List;

record SearchResult<T>(String query, T first, List<T> matches) {}
```

Mỗi component có thể được đọc bằng ba phương thức:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `getName()` | `String` | Tên component trong record header |
| `getType()` | `Class<?>` | Đối tượng `Class` đại diện cho kiểu sau khi áp dụng type erasure |
| `getGenericType()` | `Type` | Kiểu khai báo dưới dạng reflection, giữ thông tin generic khi có thể |

Với `SearchResult<T>`:

| Component | `getName()` | `getType()` | `getGenericType()` |
| --- | --- | --- | --- |
| `query` | `"query"` | `String.class` | `String.class` |
| `first` | `"first"` | `Object.class` | `T` (một `TypeVariable`) |
| `matches` | `"matches"` | `List.class` | `List<T>` (một `ParameterizedType`) |

Điểm quan trọng: `getType()` và `getGenericType()` không phải hai cách gọi thay thế nhau. Nếu chỉ cần kiểm tra kiểu runtime hoặc so sánh với một lớp cụ thể, `getType()` thường phù hợp. Nếu cần tạo schema, hiển thị kiểu khai báo hay phân tích tham số generic, hãy dùng `getGenericType()`.

## 2. `getName()` — đọc tên component

Chữ ký:

```java
public String getName()
```

Phương thức trả về tên component được khai báo trong record header. Ví dụ:

```java
record Employee(long employeeId, String displayName) {}

// Khi duyệt Employee.class.getRecordComponents():
// component thứ nhất có tên "employeeId"
// component thứ hai có tên "displayName"
```

Tên component là một phần của định nghĩa record. Nó hữu ích khi:

- Sinh schema hoặc tài liệu mô tả dữ liệu.
- Ánh xạ component với tên thuộc tính trong một định dạng trao đổi.
- Tạo thông báo lỗi có ngữ cảnh, ví dụ “component `employeeId` có kiểu không hợp lệ”.
- Kết hợp metadata với accessor tương ứng để đọc giá trị từ một instance.

`getName()` trả về tên, không trả về giá trị của component trong một đối tượng cụ thể. Ví dụ, với `Employee employee`, muốn lấy giá trị mã nhân viên thì gọi `employee.employeeId()`; metadata `Employee.class.getRecordComponents()[0].getName()` chỉ trả về `"employeeId"`.

## 3. `getType()` — lấy kiểu dưới dạng `Class<?>`

Chữ ký:

```java
public Class<?> getType()
```

Phương thức trả về đối tượng `Class<?>` đại diện cho kiểu component sau khi áp dụng cơ chế **type erasure** của Java.

Ví dụ:

```java
import java.math.BigDecimal;
import java.util.List;

record Invoice(
        long id,
        BigDecimal total,
        List<String> labels
) {}

// Invoice.class.getRecordComponents():
// id     -> long.class
// total  -> BigDecimal.class
// labels -> List.class
```

Với kiểu không generic, kết quả thường là kiểu ta mong đợi. Với kiểu generic, tham số kiểu bị xóa theo quy tắc của Java:

- `List<String>` có `getType()` là `List.class`.
- `T` không có bound cụ thể trong `record Box<T>(T value) {}` có `getType()` là `Object.class`.
- `T` trong `record NumericBox<T extends Number>(T value) {}` có `getType()` là `Number.class` vì bound đầu tiên là `Number`.

Nếu component có kiểu nguyên thủy, `getType()` trả về đối tượng `Class` của kiểu nguyên thủy tương ứng, chẳng hạn `int.class` hoặc `long.class`; nó không tự động đổi thành `Integer.class` hoặc `Long.class`.

Ví dụ kiểm tra kiểu bằng `getType()`:

```java
import java.lang.reflect.RecordComponent;
import java.util.List;

record Member(String name, List<String> roles, int level) {}

public class ComponentTypeDemo {
    public static void main(String[] args) {
        for (RecordComponent component : Member.class.getRecordComponents()) {
            Class<?> type = component.getType();
            System.out.printf("%s -> %s%n",
                    component.getName(), type.getTypeName());
        }
    }
}
```

Kết quả:

```text
name -> java.lang.String
roles -> java.util.List
level -> int
```

`getType()` phù hợp cho các kiểm tra như:

```java
if (component.getType() == String.class) {
    // Xử lý component có kiểu String sau type erasure.
}
```

Nhưng phép so sánh trên không phân biệt `List<String>` với `List<Long>`, bởi cả hai đều có kiểu runtime `List.class`. Khi cần phân biệt tham số generic, hãy xem `getGenericType()`.

## 4. `getGenericType()` — giữ thông tin kiểu khai báo

Chữ ký:

```java
public Type getGenericType()
```

Phương thức trả về một đối tượng thuộc hệ phân cấp `java.lang.reflect.Type`. Giá trị cụ thể có thể là:

- `Class<?>`: kiểu lớp hoặc kiểu nguyên thủy không có tham số generic.
- `ParameterizedType`: kiểu có tham số, chẳng hạn `List<String>` hoặc `Map<String, Integer>`.
- `TypeVariable<?>`: biến kiểu, chẳng hạn `T`.
- `GenericArrayType`: kiểu mảng có thành phần là kiểu generic, chẳng hạn `T[]`.
- `WildcardType`: wildcard trong một biểu thức kiểu, chẳng hạn `List<? extends Number>`.

Không nên giả định kết quả luôn là `Class<?>`. Đây là khác biệt quan trọng nhất khi làm việc với `getGenericType()`.

### 4.1. Kiểu tham số hóa: `ParameterizedType`

Ví dụ:

```java
import java.util.List;
import java.util.Map;

record Directory(
        List<String> names,
        Map<String, Integer> scores
) {}
```

Với component `names`:

- `getType()` trả về `List.class`.
- `getGenericType()` trả về một `ParameterizedType` mô tả `List<String>`.

Với component `scores`:

- `getType()` trả về `Map.class`.
- `getGenericType()` mô tả `Map<String, Integer>`.

Có thể đọc các tham số kiểu bằng `ParameterizedType.getActualTypeArguments()`:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.Type;
import java.util.List;

record Playlist(List<String> tracks) {}

public class ParameterizedComponentDemo {
    public static void main(String[] args) {
        RecordComponent tracks =
                Playlist.class.getRecordComponents()[0];

        Type genericType = tracks.getGenericType();
        if (genericType instanceof ParameterizedType parameterizedType) {
            System.out.println("Raw type: "
                    + parameterizedType.getRawType().getTypeName());

            for (Type argument :
                    parameterizedType.getActualTypeArguments()) {
                System.out.println("Type argument: "
                        + argument.getTypeName());
            }
        }
    }
}
```

Kết quả:

```text
Raw type: java.util.List
Type argument: java.lang.String
```

Pattern matching cho `instanceof` trong ví dụ trên là cú pháp Java hiện đại đã được chuẩn hóa từ Java 16. Nó giúp kiểm tra kiểu và khai báo biến `parameterizedType` trong cùng một biểu thức.

### 4.2. Biến kiểu: `TypeVariable`

Với record generic:

```java
record Box<T>(T value) {}
```

Component `value` có:

- `getType()` trả về `Object.class` nếu `T` không khai báo bound.
- `getGenericType()` trả về một `TypeVariable<?>` đại diện cho `T`.

Ví dụ đọc tên biến kiểu và bound:

```java
import java.lang.reflect.RecordComponent;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;

record NumericBox<T extends Number>(T value) {}

public class TypeVariableDemo {
    public static void main(String[] args) {
        RecordComponent value =
                NumericBox.class.getRecordComponents()[0];

        System.out.println(value.getType().getTypeName());

        Type genericType = value.getGenericType();
        if (genericType instanceof TypeVariable<?> variable) {
            System.out.println("Variable: " + variable.getName());
            for (Type bound : variable.getBounds()) {
                System.out.println("Bound: " + bound.getTypeName());
            }
        }
    }
}
```

Kết quả:

```text
java.lang.Number
Variable: T
Bound: java.lang.Number
```

`getGenericType()` giúp giữ lại việc component được khai báo bằng biến kiểu `T`. Tuy nhiên, nó không tự thay `T` bằng kiểu đối số thực tế của một instance. Chẳng hạn, dù đang có một đối tượng `NumericBox<Integer>`, đọc component từ `NumericBox.class` vẫn cho metadata của biến kiểu `T extends Number`.

### 4.3. Wildcard và kiểu mảng generic

Với khai báo:

```java
record NumberGroup(
        java.util.List<? extends Number> values,
        T[] items
) {}
```

Đoạn trên chưa hợp lệ vì `T` chưa được khai báo. Phiên bản generic hợp lệ là:

```java
record NumberGroup<T>(
        java.util.List<? extends Number> values,
        T[] items
) {}
```

Trong metadata:

- `values` có kiểu generic là `List<? extends Number>`; phần wildcard có thể được biểu diễn bằng `WildcardType`.
- `items` có kiểu generic là `T[]`; kiểu này có thể được biểu diễn bằng `GenericArrayType`.

Các trường hợp này cho thấy `getGenericType()` trả về một mô hình kiểu tổng quát. Khi xây dựng công cụ phân tích, nên xử lý từng loại `Type` bằng kiểm tra `instanceof` tương ứng thay vì ép kiểu trực tiếp.

## 5. Ví dụ tổng hợp: In tên, kiểu runtime và kiểu khai báo

Chương trình sau duyệt component của một record generic và in cả ba thông tin:

```java
import java.lang.reflect.RecordComponent;
import java.util.List;

record ApiResponse<T>(
        String requestId,
        T data,
        List<T> history
) {}

public class RecordComponentMetadataDemo {
    static void printMetadata(Class<?> recordType) {
        if (recordType == null || !recordType.isRecord()) {
            throw new IllegalArgumentException("Expected a record class");
        }

        for (RecordComponent component :
                recordType.getRecordComponents()) {
            System.out.printf(
                    "name=%s, type=%s, genericType=%s%n",
                    component.getName(),
                    component.getType().getTypeName(),
                    component.getGenericType().getTypeName()
            );
        }
    }

    public static void main(String[] args) {
        printMetadata(ApiResponse.class);
    }
}
```

Kết quả:

```text
name=requestId, type=java.lang.String, genericType=java.lang.String
name=data, type=java.lang.Object, genericType=T
name=history, type=java.util.List, genericType=java.util.List<T>
```

Chương trình thể hiện ba trường hợp điển hình:

1. `requestId` có kiểu cụ thể, vì vậy kiểu runtime và kiểu generic giống nhau.
2. `data` dùng biến kiểu `T` không có bound, vì vậy kiểu sau erasure là `Object`, còn kiểu generic giữ `T`.
3. `history` có raw type là `List`, còn kiểu generic giữ tham số `T`.

`Class<?>` truyền vào hàm là đối tượng đại diện cho khai báo lớp record. Khi cần phân tích kiểu đã được tham số hóa ở một vị trí khai báo khác, phải xác định đúng đối tượng `Type` tương ứng; không thể dựa vào một instance để khôi phục mọi thông tin generic đã bị xóa.

## 6. Chọn API nào cho từng nhu cầu?

| Nhu cầu | API nên dùng | Lý do |
| --- | --- | --- |
| Hiển thị tên component | `getName()` | Trả về tên trong record header |
| Kiểm tra component có kiểu `String` sau erasure | `getType() == String.class` | So sánh trực tiếp với `Class` |
| Kiểm tra component có raw type là `List` | `getType() == List.class` | Tham số generic không nằm trong `Class<?>` |
| Phân biệt `List<String>` và `List<Long>` ở metadata khai báo | `getGenericType()` | Giữ thông tin tham số kiểu |
| Phát hiện component được khai báo bằng `T` | `getGenericType()` kết hợp `TypeVariable` | Nhận diện biến kiểu |
| Đọc bound của biến kiểu | `TypeVariable.getBounds()` | Lấy các giới hạn kiểu được khai báo |
| Đọc wildcard trong kiểu generic | `getGenericType()` kết hợp `ParameterizedType` và `WildcardType` | Phân tích đối số kiểu |

Một hàm kiểm tra đơn giản có thể dùng cả hai API:

```java
import java.lang.reflect.RecordComponent;
import java.lang.reflect.Type;
import java.util.List;

static void inspectListComponent(RecordComponent component) {
    if (component.getType() == List.class) {
        Type declaredType = component.getGenericType();
        System.out.println("List component: "
                + declaredType.getTypeName());
    }
}
```

Ở đây, `getType()` xác nhận raw type là `List`; `getGenericType()` cung cấp thêm kiểu khai báo để hiển thị hoặc phân tích sâu hơn.

## 7. Các lỗi và giới hạn cần hiểu đúng

**Ép kiểu kết quả `getGenericType()` thành `Class<?>`**

Đây là lỗi thường gặp:

```java
Class<?> type = component.getGenericType(); // Không biên dịch
```

Phương thức trả về `Type`, không phải `Class<?>`. Một kiểu generic có thể được biểu diễn bằng `ParameterizedType`, `TypeVariable` hoặc các dạng `Type` khác. Hãy giữ kiểu `Type` hoặc kiểm tra kiểu cụ thể trước khi xử lý.

**Cho rằng `getType()` luôn trả về kiểu được viết nguyên văn**

Với `List<String>`, `getType()` chỉ trả về `List.class`. Với `T` không có bound, nó trả về `Object.class`. Đây là hệ quả của type erasure, không phải lỗi reflection.

**Cho rằng `getGenericType()` khôi phục kiểu thực tế của instance**

API trả về thông tin kiểu được khai báo trong record component. Nó không đọc giá trị đối tượng và không thể khôi phục đối số generic đã bị xóa khỏi một instance chỉ bằng cách gọi `getGenericType()` trên `Class`.

**Nhầm kiểu nguyên thủy với wrapper**

Component khai báo `int count` có `getType()` là `int.class`. Nếu cần kiểm tra kiểu, phải so sánh với `int.class` thay vì `Integer.class`.

**Giả định component nào cũng có tham số generic**

Với component `String name`, cả `getType()` và `getGenericType()` đều trả về đối tượng `Class` tương ứng với `String.class`. Chỉ các kiểu có cấu trúc generic mới cần xử lý các dạng `Type` khác.

**Đọc metadata mà quên kiểm tra kiểu đầu vào**

`getName()`, `getType()` và `getGenericType()` được gọi trên một đối tượng `RecordComponent` hợp lệ. Nếu lấy từ `Class.getRecordComponents()`, hãy xác nhận lớp là record trước hoặc xử lý trường hợp kết quả `null`. Record không có component trả về mảng rỗng, nên vòng lặp sẽ không chạy lần nào.

## 8. Bài tập tự kiểm tra

Cho khai báo:

```java
import java.util.List;
import java.util.Map;

record CacheEntry<K, V>(
        K key,
        V value,
        List<V> previousValues,
        Map<String, V> attributes,
        long createdAt
) {}
```

Hãy xác định:

1. `getName()` của component thứ ba trả về gì?
2. `getType()` của `previousValues` trả về lớp nào?
3. `getGenericType()` của `previousValues` biểu diễn kiểu nào?
4. `getType()` của `key` là gì nếu `K` không có bound?
5. `getGenericType()` của `value` thuộc loại `Type` nào?
6. `getType()` của `createdAt` là gì?

**Đáp án:**

1. `"previousValues"`.
2. `List.class`.
3. `List<V>`, thường được biểu diễn bằng `ParameterizedType`.
4. `Object.class` do `K` không có bound nên erasure là `Object`.
5. `TypeVariable<?>` đại diện cho biến kiểu `V`.
6. `long.class`.

## Ghi nhớ

Ba phương thức của `RecordComponent` bổ sung cho nhau: **`getName()` trả về tên component; `getType()` trả về `Class<?>` sau type erasure; `getGenericType()` trả về `Type` giữ cấu trúc generic của khai báo khi có thể.** Dùng `getType()` cho kiểm tra kiểu runtime và `getGenericType()` cho phân tích schema hoặc tham số kiểu. Luôn xử lý `Type` theo đúng dạng thực tế, vì nó không phải lúc nào cũng là `Class<?>`.

## Tài liệu tham khảo

- [Oracle Java SE API — `RecordComponent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html)
- [Oracle Java SE API — `Type`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Type.html)
- [Oracle Java SE API — `ParameterizedType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/ParameterizedType.html)
- [Oracle Java SE API — `TypeVariable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/TypeVariable.html)
- [Oracle Java SE API — `WildcardType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/WildcardType.html)
- [Oracle Java SE — Type Erasure](https://docs.oracle.com/javase/tutorial/java/generics/erasure.html)
