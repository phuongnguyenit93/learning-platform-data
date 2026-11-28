# Viết mapper dựa trên component và constructor thay vì sửa field final

Record được thiết kế để biểu diễn dữ liệu bất biến theo cấu trúc đã khai báo. Mỗi component có một field `private final`, một accessor và một tham số tương ứng trong canonical constructor. Khi cần ánh xạ dữ liệu từ `Map`, cấu hình, kết quả truy vấn hoặc một nguồn khác vào record, cách phù hợp là **đọc metadata component rồi tạo một instance mới qua canonical constructor**.

Java Reflection cung cấp đủ API chuẩn để thực hiện công việc này:

- `Class.getRecordComponents()` lấy tên, kiểu và accessor của từng component theo thứ tự khai báo.
- `RecordComponent.getAccessor()` và `Method.invoke()` đọc giá trị từ một record hiện có.
- `RecordComponent.getType()` cung cấp kiểu runtime cần để tìm constructor.
- `Class.getDeclaredConstructor(...)` tìm canonical constructor theo đúng thứ tự component.
- `Constructor.newInstance(...)` tạo record mới từ các giá trị đã ánh xạ.

Bài học thuộc chương **Metadata record** của module **JAVA_VERSION_JAVA16**. Record và các API trên được chuẩn hóa từ Java 16, vẫn là cách làm ổn định trong Java hiện đại. Ví dụ tập trung vào mapper tổng quát, quy tắc kiểm tra dữ liệu và cách tạo bản sao record khi cần thay đổi giá trị.

## 1. Vì sao mapper không nên sửa field của record?

Xét record:

```java
record Product(String sku, int quantity) {}
```

Các field thành phần của record là `private final`. Giá trị được thiết lập khi constructor chạy; record không cung cấp setter để thay đổi component sau khi tạo đối tượng.

Vì vậy, cách làm như sau không phải một chiến lược cập nhật record hợp lệ:

```java
Field field = Product.class.getDeclaredField("quantity");
field.setAccessible(true);
field.set(product, 10);
```

Java không cho phép dùng Reflection để bật quyền ghi vào final field của record. `Field.set(...)` sẽ không ghi được field đó và có thể ném `IllegalAccessException`, kể cả khi đã gọi `setAccessible(true)`. `setAccessible` không biến record thành đối tượng có thể sửa field.

Một mapper nên tạo **instance mới** với các giá trị đích:

```java
Product updated = new Product(product.sku(), 10);
```

Đây là cách phù hợp với mô hình dữ liệu của record. Nếu record có compact hoặc normal canonical constructor chứa kiểm tra hợp lệ, logic đó vẫn chạy khi tạo instance mới.

## 2. Metadata nào giúp mapper làm việc tổng quát?

Với:

```java
record Product(String sku, int quantity, java.math.BigDecimal price) {}
```

`Product.class.getRecordComponents()` trả về các component theo đúng thứ tự record header:

| Vị trí | Tên | `getType()` |
| ---: | --- | --- |
| 0 | `sku` | `String.class` |
| 1 | `quantity` | `int.class` |
| 2 | `price` | `BigDecimal.class` |

Mỗi `RecordComponent` cung cấp những thông tin mapper cần:

| API | Vai trò trong mapper |
| --- | --- |
| `getName()` | Tìm giá trị nguồn theo tên component |
| `getType()` | Kiểm tra kiểu giá trị và dựng chữ ký constructor |
| `getGenericType()` | Đọc kiểu khai báo nếu cần xử lý generic |
| `getAccessor()` | Lấy method đọc giá trị từ instance hiện có |

Điểm quan trọng là mapper dùng **tên component để tìm dữ liệu**, nhưng dùng **thứ tự component để dựng mảng tham số constructor**. Thứ tự các entry trong `Map` không ảnh hưởng đến kết quả.

## 3. Luồng ánh xạ từ Map sang record

Giả sử nguồn dữ liệu là:

```java
Map<String, Object> values = new HashMap<>();
values.put("price", new BigDecimal("125000.00"));
values.put("sku", "BK-100");
values.put("quantity", 3);
```

Mapper thực hiện các bước:

1. Xác nhận kiểu đích là record bằng `Class.isRecord()`.
2. Lấy danh sách component bằng `getRecordComponents()`.
3. Duyệt component theo thứ tự khai báo, lấy giá trị từ map bằng `component.getName()`.
4. Kiểm tra giá trị có phù hợp với kiểu component không.
5. Tạo `Class<?>[]` từ `component.getType()` theo đúng thứ tự.
6. Tìm canonical constructor bằng `getDeclaredConstructor(parameterTypes)`.
7. Gọi `newInstance(arguments)` để tạo record mới.

Ví dụ, mặc dù map được thêm theo thứ tự `price`, `sku`, `quantity`, mảng đối số vẫn phải được dựng theo thứ tự `sku`, `quantity`, `price`.

## 4. Ví dụ hoàn chỉnh: mapper hai chiều Map và record

Đoạn mã sau tạo mapper nhỏ, không phụ thuộc thư viện bên ngoài. Mapper:

- Chuyển một `Map<String, ?>` thành record.
- Chuyển record thành map theo thứ tự component.
- Kiểm tra thiếu key, key dư, giá trị null cho kiểu nguyên thủy và kiểu dữ liệu không tương thích.
- Dùng canonical constructor để tạo instance.

Lưu thành tệp `RecordMapperDemo.java`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;
import java.math.BigDecimal;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class RecordMapperDemo {

    public record Product(
            String sku,
            int quantity,
            BigDecimal price
    ) {}

    public static <T> T fromMap(
            Class<T> recordType,
            Map<String, ?> values
    ) throws ReflectiveOperationException {
        Objects.requireNonNull(recordType, "recordType");
        Objects.requireNonNull(values, "values");

        if (!recordType.isRecord()) {
            throw new IllegalArgumentException(
                    "Target type must be a record: " + recordType.getName());
        }

        RecordComponent[] components = recordType.getRecordComponents();
        Class<?>[] parameterTypes = new Class<?>[components.length];
        Object[] arguments = new Object[components.length];
        Set<String> componentNames = new HashSet<>();

        for (int i = 0; i < components.length; i++) {
            RecordComponent component = components[i];
            String name = component.getName();
            Class<?> componentType = component.getType();
            componentNames.add(name);

            if (!values.containsKey(name)) {
                throw new IllegalArgumentException(
                        "Missing component: " + name);
            }

            Object value = values.get(name);
            if (value == null && componentType.isPrimitive()) {
                throw new IllegalArgumentException(
                        "Primitive component cannot be null: " + name);
            }

            Class<?> expectedType = boxedType(componentType);
            if (value != null && !expectedType.isInstance(value)) {
                throw new IllegalArgumentException(
                        "Component " + name + " expects "
                                + expectedType.getTypeName() + " but got "
                                + value.getClass().getTypeName());
            }

            parameterTypes[i] = componentType;
            arguments[i] = value;
        }

        Set<String> unknownNames = new HashSet<>(values.keySet());
        unknownNames.removeAll(componentNames);
        if (!unknownNames.isEmpty()) {
            throw new IllegalArgumentException(
                    "Unknown components: " + unknownNames);
        }

        Constructor<T> canonicalConstructor =
                recordType.getDeclaredConstructor(parameterTypes);

        return canonicalConstructor.newInstance(arguments);
    }

    public static Map<String, Object> toMap(Object record)
            throws ReflectiveOperationException {
        if (record == null || !record.getClass().isRecord()) {
            throw new IllegalArgumentException(
                    "Source value must be a non-null record");
        }

        Map<String, Object> result = new LinkedHashMap<>();
        for (RecordComponent component :
                record.getClass().getRecordComponents()) {
            Method accessor = component.getAccessor();
            Object value = accessor.invoke(record);
            result.put(component.getName(), value);
        }

        return Collections.unmodifiableMap(result);
    }

    private static Class<?> boxedType(Class<?> type) {
        if (!type.isPrimitive()) {
            return type;
        }
        if (type == boolean.class) return Boolean.class;
        if (type == byte.class) return Byte.class;
        if (type == short.class) return Short.class;
        if (type == char.class) return Character.class;
        if (type == int.class) return Integer.class;
        if (type == long.class) return Long.class;
        if (type == float.class) return Float.class;
        if (type == double.class) return Double.class;
        throw new IllegalArgumentException("Unsupported primitive: " + type);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("price", new BigDecimal("125000.00"));
        input.put("quantity", 3);
        input.put("sku", "BK-100");

        Product product = fromMap(Product.class, input);
        System.out.println(product);
        System.out.println(toMap(product));
    }
}
```

Biên dịch và chạy bằng JDK 16 trở lên:

```bash
javac RecordMapperDemo.java
java RecordMapperDemo
```

Kết quả:

```text
Product[sku=BK-100, quantity=3, price=125000.00]
{sku=BK-100, quantity=3, price=125000.00}
```

`fromMap` lấy dữ liệu theo tên nhưng dựng `parameterTypes` và `arguments` bằng chỉ số `i` trong mảng component. Do đó, chữ ký constructor và giá trị luôn khớp với record header. `toMap` dùng accessor của từng component và `LinkedHashMap`, vì vậy thứ tự đầu ra cũng phản ánh thứ tự khai báo.

`Collections.unmodifiableMap` tạo view chỉ đọc mà vẫn cho phép map chứa giá trị null. Điều này hữu ích vì `Map.copyOf(...)` không chấp nhận key hoặc value null.

## 5. Vì sao phải dùng kiểu từ component để tìm constructor?

Canonical constructor nhận toàn bộ component theo thứ tự khai báo. Có thể tự dựng chữ ký bằng reflection:

```java
RecordComponent[] components = recordType.getRecordComponents();
Class<?>[] parameterTypes = new Class<?>[components.length];

for (int i = 0; i < components.length; i++) {
    parameterTypes[i] = components[i].getType();
}

Constructor<?> constructor =
        recordType.getDeclaredConstructor(parameterTypes);
```

Không nên chọn constructor đầu tiên từ `getDeclaredConstructors()`, vì record có thể có overloaded constructor. `getDeclaredConstructor(parameterTypes)` tìm chính xác chữ ký canonical dựa trên kiểu và thứ tự component.

Việc này cũng hoạt động với:

- Compact canonical constructor: compiler tạo danh sách tham số từ record header.
- Normal canonical constructor: chữ ký vẫn khớp với component.
- Record generic: chữ ký runtime dùng kiểu sau type erasure.
- Record không component: mảng kiểu rỗng tương ứng constructor không tham số.

Ví dụ với generic:

```java
record Box<T>(T value) {}
```

`getType()` của component `value` là `Object.class` khi `T` không có bound, vì vậy chữ ký runtime là:

```java
Box.class.getDeclaredConstructor(Object.class);
```

`getGenericType()` hữu ích để hiểu kiểu khai báo `T`, nhưng `getDeclaredConstructor(...)` nhận `Class<?>...`; vì vậy mapper cần `getType()` để tìm constructor runtime.

## 6. Kiểm tra kiểu và giới hạn của mapper đơn giản

Mapper ở ví dụ trên chọn quy tắc kiểm tra kiểu nghiêm ngặt:

- Với component tham chiếu, giá trị phải là instance của kiểu component.
- Với component nguyên thủy, giá trị phải là wrapper tương ứng, ví dụ `int` nhận `Integer`, `long` nhận `Long`.
- Giá trị null được chấp nhận cho kiểu tham chiếu; canonical constructor có thể tiếp tục kiểm tra null theo quy tắc nghiệp vụ.
- Giá trị null không thể gán cho component nguyên thủy.
- Key không có trong record bị từ chối, giúp phát hiện lỗi chính tả hoặc schema không đồng nhất.

Quy tắc này có chủ ý: mapper không tự chuyển `Integer` thành `Long`, chuỗi thành ngày tháng hoặc `BigDecimal` thành `double`. Nếu nguồn dữ liệu cần chuyển đổi, hãy thêm một lớp converter rõ ràng theo từng kiểu hoặc từng component trước khi gọi constructor.

`getType()` chỉ cho biết raw type sau type erasure. Với component `List<String>`, mapper đơn giản có thể xác nhận giá trị là một `List`, nhưng không xác nhận từng phần tử đều là `String`. Muốn kiểm tra generic, cần đọc `getGenericType()` hoặc `getAnnotatedType()` và viết validator/converter phù hợp. Không nên giả định Reflection có thể suy ra đầy đủ kiểu phần tử từ một `List` bất kỳ ở runtime.

Mapper này cũng chỉ xử lý một tầng dữ liệu. Nếu component là một record lồng nhau, map nguồn phải được chuyển thành instance record con bằng một lần ánh xạ đệ quy hoặc converter tùy chỉnh. Với collection, map hoặc kiểu miền như `LocalDate`, `UUID`, enum, cần quy tắc chuyển đổi riêng theo hợp đồng dữ liệu.

## 7. Xử lý thiếu key, null và constructor validation

Có ba tình huống cần phân biệt:

| Dữ liệu nguồn | Hành vi mapper |
| --- | --- |
| Không có key component | Báo lỗi thiếu component |
| Có key và giá trị null cho kiểu tham chiếu | Truyền null vào constructor; constructor quyết định có hợp lệ không |
| Có key và giá trị null cho kiểu nguyên thủy | Báo lỗi trước khi gọi constructor |

Không dùng `values.get(name) == null` để kiểm tra key có tồn tại hay không, vì `null` có thể là giá trị được cung cấp có chủ ý. Hãy dùng `containsKey(name)` như ví dụ.

Nếu record có compact canonical constructor:

```java
record Customer(String name, int age) {
    Customer {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }
    }
}
```

`Constructor.newInstance(...)` thực thi constructor này. Khi validation ném exception, Reflection bọc lỗi gốc trong `InvocationTargetException`; có thể đọc nguyên nhân bằng `getCause()`. Vì vậy, mapper không được bỏ qua quy tắc validation chỉ vì dữ liệu đã qua kiểm tra kiểu.

## 8. Tạo bản sao record khi cần cập nhật một component

Record không có setter để thay đổi component. Khi cần cập nhật, đọc các giá trị hiện tại, thay giá trị cần đổi trong dữ liệu trung gian rồi tạo instance mới.

Có thể thêm hàm sau vào `RecordMapperDemo`:

```java
public static <T> T withChanges(
        Class<T> recordType,
        T current,
        Map<String, ?> changes
) throws ReflectiveOperationException {
    Objects.requireNonNull(recordType, "recordType");
    Objects.requireNonNull(changes, "changes");
    if (current == null || !recordType.isInstance(current)) {
        throw new IllegalArgumentException(
                "Current value must be an instance of recordType");
    }

    Map<String, Object> merged = new LinkedHashMap<>(toMap(current));
    merged.putAll(changes);
    return fromMap(recordType, merged);
}
```

Sử dụng:

```java
Product original = new Product(
        "BK-100", 3, new BigDecimal("125000.00"));

Map<String, Object> changes = Map.of("quantity", 5);
Product updated = withChanges(Product.class, original, changes);

System.out.println(original.quantity()); // 3
System.out.println(updated.quantity());  // 5
```

`original` vẫn giữ giá trị cũ; `updated` là một record mới. `withChanges` tái sử dụng mapper để bảo đảm dữ liệu được kiểm tra và canonical constructor được gọi.

Đây là cách cập nhật phù hợp với record. Tuy nhiên, record chỉ bất biến ở các component reference: nếu một component trỏ tới `List` hoặc đối tượng mutable khác, nội dung của đối tượng được tham chiếu vẫn có thể thay đổi. Muốn bất biến sâu, cần thiết kế component và quy tắc sao chép dữ liệu tương ứng.

## 9. Quyền truy cập và lỗi Reflection

`getDeclaredConstructor(...)` có thể tìm constructor được khai báo trong record, nhưng tìm thấy không đồng nghĩa với được phép gọi constructor từ mọi nơi.

Các điều kiện thực tế:

- Kiểu record và constructor phải truy cập được từ vị trí mapper.
- Với record public trong package được export phù hợp, canonical constructor public là API thuận tiện cho mapper.
- Nếu record hoặc constructor không public, lời gọi có thể phát sinh `IllegalAccessException`.
- Trong ứng dụng dùng module, cần cấu hình quan hệ đọc và `exports`/`opens` phù hợp với kiểu truy cập thực tế.

Không nên mặc định gọi `setAccessible(true)` để vượt qua mọi lỗi truy cập. Hãy công khai API record theo đúng ranh giới package/module của ứng dụng.

Các lỗi mapper nên phân biệt:

| Lỗi | Nguồn phát sinh | Hướng xử lý |
| --- | --- | --- |
| `IllegalArgumentException` | Thiếu key, key dư, kiểu giá trị không hợp lệ hoặc kiểu đích không phải record | Kiểm tra schema và dữ liệu nguồn |
| `NoSuchMethodException` | Không tìm được constructor theo kiểu component | Kiểm tra cách dựng `parameterTypes` và kiểu record |
| `IllegalAccessException` | Mapper không được phép gọi constructor hoặc accessor | Kiểm tra khả năng truy cập class, package và module |
| `InvocationTargetException` | Constructor hoặc accessor phát sinh exception | Đọc `getCause()` để xem lỗi gốc |
| `NullPointerException` | Đầu vào bắt buộc như `recordType`, `values` hoặc record nguồn là null | Kiểm tra tại ranh giới API |

## 10. Khi nào nên dùng mapper tự viết và khi nào nên dùng thư viện?

| Tình huống | Lựa chọn |
| --- | --- |
| Cần ánh xạ một vài record đơn giản từ `Map` | Mapper nhỏ dựa trên component và canonical constructor |
| Cần chuyển đổi số, ngày, enum hoặc kiểu miền | Bổ sung converter rõ ràng hoặc dùng thư viện mapping |
| Cần hỗ trợ JSON, schema phức tạp, generic lồng nhau và annotation | Dùng thư viện serialization/mapping có hỗ trợ record rõ ràng |
| Kiểu record đã biết khi biên dịch | Gọi constructor trực tiếp thường dễ đọc và an toàn kiểu hơn |
| Cần xử lý nhiều loại record chỉ biết ở runtime | Reflection dựa trên `RecordComponent` và canonical constructor |

Một thư viện mapping hiện đại có thể hỗ trợ record bằng canonical constructor. Khi chọn thư viện, hãy kiểm tra phiên bản và hợp đồng hỗ trợ record của nó; không cần viết cơ chế sửa field final để ép record hoạt động với mapper.

## 11. Bài tập tự kiểm tra

Cho record:

```java
record Order(String orderId, long totalCents, boolean paid) {}
```

Và map nguồn:

```java
Map<String, Object> values = new HashMap<>();
values.put("paid", true);
values.put("orderId", "OD-200");
values.put("totalCents", 450_000L);
```

Hãy trả lời:

1. Thứ tự `parameterTypes` cần truyền vào `getDeclaredConstructor(...)` là gì?
2. Vì sao thứ tự entry trong `HashMap` không ảnh hưởng đến thứ tự tham số constructor?
3. Giá trị cho component `totalCents` nên có kiểu wrapper nào trong mapper nghiêm ngặt ở bài học?
4. Điều gì xảy ra nếu thiếu key `paid`?
5. Vì sao không nên dùng `Field.set(...)` để cập nhật `totalCents`?
6. Nếu component có kiểu `List<String>`, kiểm tra `getType().isInstance(value)` có xác nhận mọi phần tử là `String` không?

**Đáp án:**

1. `String.class`, `long.class`, `boolean.class`, theo thứ tự record header.
2. Mapper duyệt `RecordComponent[]` theo thứ tự khai báo và tra từng giá trị bằng tên component.
3. `Long`, vì `long` là kiểu nguyên thủy và mapper yêu cầu wrapper tương ứng.
4. Mapper báo lỗi thiếu component trước khi gọi constructor.
5. Field của record là final và Java không cho phép Reflection bật quyền ghi vào final field của record.
6. Không. Kiểm tra đó chỉ xác nhận giá trị là một `List`; muốn kiểm tra phần tử cần logic generic validator riêng.

## Ghi nhớ

**Mapper cho record nên đọc và ghi dữ liệu qua component và constructor.** Khi đọc, duyệt `RecordComponent[]` và gọi accessor. Khi tạo, lấy tên và kiểu từng component, dựng mảng tham số theo đúng thứ tự record header, tìm canonical constructor rồi gọi `newInstance(...)`. Cách này tôn trọng thiết kế final của record, giữ validation trong constructor và tạo instance mới có cấu trúc nhất quán. Nếu cần chuyển đổi kiểu phức tạp hoặc kiểm tra generic sâu, bổ sung converter/validator rõ ràng thay vì sửa field bằng Reflection.

## Tài liệu tham khảo

- [Oracle Java SE API — `Class.getRecordComponents()` và `Class.getDeclaredConstructor()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html)
- [Oracle Java SE API — `RecordComponent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html)
- [Oracle Java SE API — `Constructor.newInstance()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...))
- [Oracle Java SE API — `Field.set()` and access restrictions for record fields](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html#set(java.lang.Object,java.lang.Object))
- [Oracle Java SE — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html)
- [Java Language Specification — Record Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10)
