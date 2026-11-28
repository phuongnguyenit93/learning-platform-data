# Đọc danh sách component theo thứ tự bằng `Class.getRecordComponents()`

Một **record** định nghĩa cấu trúc dữ liệu ngay trong phần khai báo, ví dụ `record Product(String sku, int quantity, BigDecimal price) {}`. Khi viết công cụ tạo schema, kiểm tra hợp đồng dữ liệu, sinh tài liệu hay ánh xạ dữ liệu bằng reflection, ta cần đọc **các record component theo đúng thứ tự mà người lập trình đã khai báo**.

Từ Java 16, record đã là tính năng chính thức của ngôn ngữ. API `Class.getRecordComponents()` trong Java Reflection cho phép làm việc này một cách trực tiếp và vẫn hữu ích trong Java hiện đại. Bài học thuộc chương **Metadata record** của module **JAVA_VERSION_JAVA16**, tập trung vào hành vi ổn định của API thay vì các kỹ thuật thử nghiệm đã lỗi thời.

## 1. Record component là gì?

Hãy xem khai báo:

```java
record Product(String sku, int quantity, java.math.BigDecimal price) {}
```

Ba khai báo trong dấu ngoặc `( ... )` của record header là **record component**:

| Vị trí | Component | Kiểu khai báo |
| ---: | --- | --- |
| 0 | `sku` | `String` |
| 1 | `quantity` | `int` |
| 2 | `price` | `BigDecimal` |

Mỗi component biểu diễn một phần trong trạng thái được khai báo của record. Đối với mỗi component, Java cung cấp metadata qua lớp `java.lang.reflect.RecordComponent`, chẳng hạn tên, kiểu, kiểu generic, annotation và phương thức accessor.

**Thứ tự component là một phần của cấu trúc record.** Với `Product`, thứ tự là `sku` → `quantity` → `price`; không phải thứ tự chữ cái, tên kiểu hay thứ tự của bất kỳ collection nào mà ứng dụng tự tạo.

## 2. API `Class.getRecordComponents()`

Phương thức thuộc `java.lang.Class`:

```java
public RecordComponent[] getRecordComponents()
```

Đây là một trong các API reflection ổn định của Java 16 trở lên. Nó trả về:

| Kiểu được kiểm tra | Kết quả |
| --- | --- |
| Một lớp record có component | Mảng `RecordComponent[]` chứa các component theo **thứ tự xuất hiện trong record header** |
| Một record không có component, ví dụ `record Empty() {}` | **Mảng rỗng** có độ dài `0` |
| Một kiểu không phải record: lớp thông thường, interface, enum, mảng, kiểu nguyên thủy hoặc `java.lang.Record` | `null` |

Quy tắc cốt lõi: **`null` và mảng rỗng có ý nghĩa khác nhau**. `null` nghĩa là đối tượng `Class<?>` không đại diện cho một lớp record; mảng rỗng nghĩa là đây **vẫn là record**, chỉ không khai báo component nào.

Khi không chắc kiểu đầu vào có phải record hay không, có thể kiểm tra trước bằng `Class.isRecord()`:

```java
static void inspect(Class<?> type) {
    if (type == null || !type.isRecord()) {
        System.out.println("Không phải kiểu record");
        return;
    }

    // isRecord() == true: getRecordComponents() trả về mảng không null.
    java.lang.reflect.RecordComponent[] components =
            type.getRecordComponents();
    System.out.println("Số component: " + components.length);
}
```

Lưu ý: `Class.isRecord()` và `Class.getRecordComponents()` là hai API phục vụ hai mục đích khác nhau: một API nhận diện loại lớp, API còn lại trả về metadata các component.

## 3. Ví dụ hoàn chỉnh: Duyệt theo thứ tự khai báo

Lưu thành tệp `RecordComponentsOrderDemo.java`:

```java
import java.lang.reflect.RecordComponent;
import java.math.BigDecimal;

public class RecordComponentsOrderDemo {

    record Product(String sku, int quantity, BigDecimal price) {}
    record Empty() {}

    static void printComponents(Class<?> type) {
        System.out.println("Type: " + type.getSimpleName());

        RecordComponent[] components = type.getRecordComponents();
        if (components == null) {
            System.out.println("  Không phải record");
            return;
        }
        if (components.length == 0) {
            System.out.println("  Record không có component");
            return;
        }

        for (int index = 0; index < components.length; index++) {
            RecordComponent component = components[index];
            System.out.printf(
                    "  [%d] %s: %s (accessor: %s())%n",
                    index,
                    component.getName(),
                    component.getType().getTypeName(),
                    component.getAccessor().getName());
        }
    }

    public static void main(String[] args) {
        printComponents(Product.class);
        printComponents(Empty.class);
        printComponents(String.class);
    }
}
```

Biên dịch và chạy bằng JDK 16 trở lên:

```bash
javac RecordComponentsOrderDemo.java
java RecordComponentsOrderDemo
```

Kết quả:

```text
Type: Product
  [0] sku: java.lang.String (accessor: sku())
  [1] quantity: int (accessor: quantity())
  [2] price: java.math.BigDecimal (accessor: price())
Type: Empty
  Record không có component
Type: String
  Không phải record
```

Ở đây, phần tử `components[0]` luôn tương ứng với `sku`, `components[1]` với `quantity` và `components[2]` với `price` trong chính khai báo `Product`. Không cần sắp xếp thêm; API đã trả về đúng thứ tự record header.

**Điểm cần nhớ:** Mỗi `RecordComponent` mô tả một component. Bản thân đối tượng metadata này không chứa giá trị `sku`, `quantity` hay `price` của một *instance* cụ thể. Muốn lấy giá trị từ một instance, cần gọi accessor trên đối tượng đó.

## 4. Những metadata hữu ích có thể đọc từ mỗi component

Các phương thức chính của `RecordComponent`:

| API | Giá trị cung cấp |
| --- | --- |
| `getName()` | Tên component trong record header |
| `getType()` | `Class<?>` biểu diễn kiểu của component sau khi xét erasure |
| `getGenericType()` | `Type` mô tả kiểu khai báo, có thể bao gồm tham số generic |
| `getAccessor()` | `Method` biểu diễn accessor tương ứng, chẳng hạn `sku()` |
| `getAnnotations()` / `getAnnotation(...)` | Các annotation có thể đọc được tại runtime và áp dụng cho component |
| `getAnnotatedType()` | `AnnotatedType` nếu cần metadata annotation trên kiểu của component |

Ví dụ, với:

```java
record TaggedProduct(
        java.util.List<String> tags,
        java.util.Map<String, Integer> stockByStore
) {}
```

Đối với component `tags`:

- `getName()` trả về `"tags"`.
- `getType().getTypeName()` trả về `"java.util.List"`.
- `getGenericType().getTypeName()` trả về `"java.util.List<java.lang.String>"`.
- `getAccessor().getName()` trả về `"tags"`.

**`getType()` và `getGenericType()` không luôn giống nhau.** Khi tạo schema hoặc kiểm tra kiểu có tham số như `List<String>`, nên cân nhắc `getGenericType()` để giữ được thông tin kiểu generic có trong khai báo.

Đối với type variable, thông tin runtime vẫn chịu cơ chế *type erasure* của Java; reflection không thể tự suy ra mọi tham số kiểu từ một đối tượng generic cụ thể.

## 5. Xây dựng danh sách có thứ tự bằng Stream API

Java 16 đồng thời giới thiệu `Stream.toList()`, một API vẫn được sử dụng trong Java hiện đại. Ta có thể kết hợp `getRecordComponents()` với Stream để xây dựng danh sách metadata mà **giữ nguyên thứ tự component**.

Ví dụ sau trả về danh sách thông tin component, kèm vị trí trong record header:

```java
import java.lang.reflect.RecordComponent;
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.IntStream;

public class RecordSchemaDemo {
    record Product(String sku, int quantity, BigDecimal price) {}

    record FieldInfo(int position, String name, String declaredType) {}

    static List<FieldInfo> describeRecord(Class<?> type) {
        if (type == null || !type.isRecord()) {
            throw new IllegalArgumentException("Expected a record class");
        }

        RecordComponent[] components = type.getRecordComponents();
        return IntStream.range(0, components.length)
                .mapToObj(i -> new FieldInfo(
                        i,
                        components[i].getName(),
                        components[i].getGenericType().getTypeName()))
                .toList();
    }

    public static void main(String[] args) {
        for (FieldInfo field : describeRecord(Product.class)) {
            System.out.printf("%d - %s: %s%n",
                    field.position(), field.name(), field.declaredType());
        }
    }
}
```

Kết quả:

```text
0 - sku: java.lang.String
1 - quantity: int
2 - price: java.math.BigDecimal
```

Vì `IntStream.range(0, components.length)` tạo ra các chỉ số tăng dần và pipeline trên giữ thứ tự, danh sách `FieldInfo` duy trì đúng vị trí của từng component. `Stream.toList()` trả về danh sách không cho phép sửa cấu trúc; muốn danh sách thay đổi được, có thể tạo collection phù hợp từ kết quả.

Ví dụ trên phù hợp để làm cơ sở sinh schema, trình bày thông tin cấu trúc hoặc kiểm tra vị trí component. Đây chỉ là bước trích xuất metadata: nó **không tự động** đảm bảo tương thích định dạng dữ liệu của một thư viện serialization cụ thể.

## 6. Đừng nhầm component với field, constructor hoặc method

Record component có liên hệ với nhiều thành phần được Java tạo ra hoặc cho phép khai báo, nhưng các API reflection tương ứng phục vụ mục đích khác nhau.

```java
record Invoice(String number, long totalCents) {
    static final String CURRENCY = "VND";

    String summary() {
        return number + ": " + totalCents + " " + CURRENCY;
    }
}
```

Với `Invoice`:

- `Invoice.class.getRecordComponents()` trả về **hai** component `number` và `totalCents`, theo thứ tự đó.
- Trường `static final CURRENCY` **không** phải record component vì không nằm trong record header.
- Phương thức `summary()` **không** phải record component.
- Các accessor `number()` và `totalCents()` tương ứng với component, nhưng liệt kê tất cả method qua `getDeclaredMethods()` không phải là cách xác định danh sách component.

| API reflection | Dữ liệu biểu diễn | Có dùng để lấy danh sách component theo thứ tự header? |
| --- | --- | --- |
| `getRecordComponents()` | Các component được khai báo trong record header | **Có** |
| `getDeclaredFields()` | Các field khai báo trong lớp, bao gồm field `static` | Không |
| `getDeclaredMethods()` | Các method khai báo trong lớp, có thể bao gồm accessor và method khác | Không |
| `getDeclaredConstructors()` | Các constructor khai báo trong lớp | Không |

Không nên suy ra cấu trúc record bằng cách tìm field `private final`, tìm accessor theo tên hoặc đoán từ constructor. Chúng có thể cho thông tin liên quan nhưng không thể thay thế danh sách component do `getRecordComponents()` cung cấp.

## 7. Đọc annotation trên record component

Một ứng dụng tạo schema có thể muốn lấy nhãn hiển thị của các component. Ta có thể định nghĩa annotation chỉ áp dụng cho `RECORD_COMPONENT` và đọc lại qua reflection.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.RecordComponent;

public class RecordAnnotationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    @interface DisplayName {
        String value();
    }

    record Customer(
            @DisplayName("Mã khách hàng") long id,
            @DisplayName("Tên khách hàng") String name
    ) {}

    public static void main(String[] args) {
        for (RecordComponent component :
                Customer.class.getRecordComponents()) {
            DisplayName annotation =
                    component.getAnnotation(DisplayName.class);

            String label = annotation != null
                    ? annotation.value()
                    : component.getName();

            System.out.println(component.getName() + " -> " + label);
        }
    }
}
```

Kết quả:

```text
id -> Mã khách hàng
name -> Tên khách hàng
```

Ở đây, `@Target(ElementType.RECORD_COMPONENT)` cho phép annotation áp dụng cho chính record component; `@Retention(RetentionPolicy.RUNTIME)` cho phép reflection đọc annotation lúc chạy. Với annotation khác, cần kiểm tra `@Target` và `@Retention` trước khi kỳ vọng `getAnnotation(...)` trả về giá trị.

## 8. Tình huống biên và lỗi phổ biến

| Tình huống | Điều nên làm |
| --- | --- |
| Kiểu đầu vào là `null` | Kiểm tra `type != null` trước khi gọi phương thức trên `Class<?>` |
| Kiểu không phải record | Kiểm tra `isRecord()` hoặc xử lý kết quả `getRecordComponents() == null` |
| `record Empty() {}` | Xử lý mảng độ dài `0` như một record hợp lệ |
| Mảng của record, ví dụ `Product[].class` | `getRecordComponents()` trên kiểu mảng trả về `null`; cần `getComponentType()` nếu muốn kiểm tra kiểu phần tử |
| Record có tham số generic | Xem `getGenericType()` khi cần thông tin khai báo generic |
| Cần duy trì thứ tự trong kết quả | Duyệt mảng theo index, hoặc sử dụng collection/pipeline giữ thứ tự; tránh tự sắp xếp theo tên |
| Một component bị đổi vị trí trong record header | Danh sách reflection sẽ phản ánh thứ tự mới; cần xem xét ảnh hưởng lên schema hay hợp đồng dữ liệu phụ thuộc vị trí |

### Câu hỏi thường gặp

**1. `getRecordComponents()` có trả về danh sách theo bảng chữ cái không?**

Không. Thứ tự trả về là thứ tự khai báo các component trong record header.

**2. Hai lần gọi `getRecordComponents()` có thể dùng để suy ra thứ tự khai báo không?**

Có. Mỗi kết quả phản ánh cùng thứ tự component của định nghĩa record đó. Tuy nhiên, không nên viết logic phụ thuộc vào việc hai mảng trả về có cùng danh tính đối tượng; điều cần dựa vào là metadata và thứ tự phần tử.

**3. Có cần gọi `getDeclaredFields()` để bảo đảm đủ component không?**

Không. `getRecordComponents()` đã mô tả toàn bộ component của record header; field `static` hoặc thành phần triển khai không phải là record component.

**4. Record không có component có phải một kiểu hợp lệ không?**

Có. `record Empty() {}` là khai báo record hợp lệ. `Empty.class.isRecord()` trả về `true`, còn `Empty.class.getRecordComponents().length` bằng `0`.

**5. Phương thức này có đọc giá trị một bản ghi cụ thể không?**

Không. API làm việc trên **kiểu** (`Class<?>`) và trả về metadata. Để lấy giá trị, cần một instance và có thể gọi accessor tương ứng; khi dùng reflection để gọi accessor, cần xử lý các yêu cầu về quyền truy cập và ngoại lệ của `Method.invoke(...)`.

## 9. Bài tập tự kiểm tra

Xét khai báo:

```java
record Measurement(double value, String unit, long timestamp) {}
record Empty() {}
```

Hãy dự đoán:

1. `Measurement.class.getRecordComponents()[0].getName()` trả về gì?
2. `Measurement.class.getRecordComponents()[2].getType()` trả về đối tượng `Class` nào?
3. `Empty.class.getRecordComponents()` trả về `null` hay mảng rỗng?
4. `Measurement[].class.getRecordComponents()` trả về gì?
5. Khi đổi khai báo thành `record Measurement(long timestamp, double value, String unit) {}` thì vị trí các component thay đổi như thế nào?

**Đáp án:**

1. `"value"`.
2. `long.class` (kiểu nguyên thủy `long`).
3. Mảng rỗng, độ dài bằng `0`.
4. `null`, vì kiểu mảng không phải record.
5. Thứ tự trả về là `timestamp`, `value`, `unit`; chỉ số mới tương ứng `0`, `1`, `2`.

## Ghi nhớ

**`Class.getRecordComponents()` trả về các record component đúng thứ tự xuất hiện trong record header.** Với record rỗng, kết quả là mảng rỗng; với kiểu không phải record, kết quả là `null`. Mỗi `RecordComponent` cung cấp metadata như tên, kiểu khai báo, accessor và annotation. Đây là API reflection chuẩn, ổn định từ Java 16, đặc biệt hữu ích khi xây dựng các công cụ xử lý record mà kiểu dữ liệu chỉ được biết ở runtime.

## Tài liệu tham khảo

- [Oracle Java SE API — `Class.getRecordComponents()` và `Class.isRecord()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#getRecordComponents())
- [Oracle Java SE API — `RecordComponent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html)
- [Oracle Java SE — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html)
- [Oracle Java SE API — `Stream.toList()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#toList())
