# Nhận diện record bằng `Class.isRecord()`

Từ Java 16, **record** là một dạng khai báo lớp chính thức trong ngôn ngữ Java, phù hợp để biểu diễn những nhóm dữ liệu có cấu trúc rõ ràng. Khi xây dựng công cụ dùng reflection, bộ kiểm tra kiểu dữ liệu, thư viện ánh xạ dữ liệu hay bộ sinh tài liệu API, ta thường cần trả lời câu hỏi: *Một kiểu Java có thực sự được khai báo là record hay không?*

API chuẩn để trả lời câu hỏi đó là **`Class.isRecord()`**. Phương thức này có từ Java 16 và vẫn là cách trực tiếp, ổn định để nhận diện record trong Java hiện đại.

## 1. `Class.isRecord()` kiểm tra điều gì?

Chữ ký phương thức trong `java.lang.Class`:

```java
public boolean isRecord()
```

Giá trị trả về:

- `true` nếu đối tượng `Class<?>` đại diện cho **một lớp record**.
- `false` nếu nó đại diện cho lớp thông thường, interface, enum, kiểu nguyên thủy, kiểu mảng hoặc chính lớp nền `java.lang.Record`.

Ví dụ, hai kiểu sau đều chứa dữ liệu về khách hàng, nhưng chỉ kiểu thứ nhất là record:

```java
record Customer(long id, String name) {}

final class CustomerClass {
    private final long id;
    private final String name;

    CustomerClass(long id, String name) {
        this.id = id;
        this.name = name;
    }
}
```

`Customer.class.isRecord()` trả về `true`, còn `CustomerClass.class.isRecord()` trả về `false`. Việc một lớp có các trường `private final`, constructor hoặc getter giống record không biến nó thành record. Kết quả được xác định theo loại lớp ở runtime, không phải dựa vào tên, quy ước đặt tên hay hình dạng API.

> **Phân biệt:** `java.lang.Record` là lớp nền trực tiếp của các record, nhưng bản thân `Record` **không phải** một record. Vì vậy, `Record.class.isRecord()` trả về `false`.

## 2. Ví dụ hoàn chỉnh: Nhận diện nhiều loại `Class`

Lưu đoạn mã sau vào `RecordInspectionDemo.java`:

```java
import java.lang.reflect.RecordComponent;

public class RecordInspectionDemo {
    record Customer(long id, String name) {}
    record EmptyRecord() {}

    static final class CustomerClass {
        private final long id;
        private final String name;

        CustomerClass(long id, String name) {
            this.id = id;
            this.name = name;
        }
    }

    public static void main(String[] args) {
        inspect(Customer.class);
        inspect(CustomerClass.class);
        inspect(EmptyRecord.class);
        inspect(java.lang.Record.class);
        inspect(String[].class);
        inspect(int.class);
    }

    private static void inspect(Class<?> type) {
        System.out.printf("%s -> isRecord=%s%n",
                type.getSimpleName(), type.isRecord());

        if (!type.isRecord()) {
            return;
        }

        for (RecordComponent component : type.getRecordComponents()) {
            System.out.printf("  %s: %s [accessor: %s()]%n",
                    component.getName(),
                    component.getType().getTypeName(),
                    component.getAccessor().getName());
        }
    }
}
```

Chạy bằng JDK 16 trở lên:

```bash
javac RecordInspectionDemo.java
java RecordInspectionDemo
```

Kết quả:

```text
Customer -> isRecord=true
  id: long [accessor: id()]
  name: java.lang.String [accessor: name()]
CustomerClass -> isRecord=false
EmptyRecord -> isRecord=true
Record -> isRecord=false
String[] -> isRecord=false
int -> isRecord=false
```

Những điểm cần quan sát:

1. `Customer` là record nên trả về `true`, đồng thời có hai *record component* là `id` và `name`.
2. `CustomerClass` là lớp thông thường, dù có trường bất biến, nên trả về `false`.
3. `EmptyRecord` vẫn là record dù khai báo không có component nào.
4. `java.lang.Record` không tự nhận là record; `String[]` là một **kiểu mảng**, còn `int` là kiểu nguyên thủy.

Trong ví dụ, phương thức `inspect` chỉ gọi `getRecordComponents()` sau khi `isRecord()` trả về `true`. Đây là cách sử dụng an toàn, rõ mục đích và dễ bảo trì.

## 3. Nhận diện record từ một đối tượng ở runtime

Khi đã có `Class<?>`, gọi `type.isRecord()` trực tiếp. Nếu chỉ có một đối tượng, có thể lấy kiểu runtime của nó bằng `getClass()`. Ví dụ:

```java
public class RecordInstanceDemo {
    record OrderId(long value) {}

    static boolean isRecordInstance(Object value) {
        return value != null && value.getClass().isRecord();
    }

    public static void main(String[] args) {
        System.out.println(isRecordInstance(new OrderId(1001))); // true
        System.out.println(isRecordInstance("ORD-1001"));        // false
        System.out.println(isRecordInstance(null));              // false
    }
}
```

Điểm cốt lõi là phép kiểm tra `value != null`: gọi `getClass()` trên `null` sẽ phát sinh `NullPointerException`.

Hai cách kiểm tra phục vụ hai tình huống khác nhau:

| Đầu vào hiện có | Cách kiểm tra | Ví dụ |
| --- | --- | --- |
| Kiểu `Class<?>` | `type.isRecord()` | `OrderId.class.isRecord()` |
| Đối tượng không biết trước kiểu | `value != null && value.getClass().isRecord()` | `isRecordInstance(new OrderId(1))` |
| Kiểu phần tử của một mảng | `arrayType.getComponentType().isRecord()`, sau khi xác định đây là mảng | `OrderId[].class.getComponentType().isRecord()` |

**Chú ý trường hợp mảng:** `OrderId[].class.isRecord()` là `false` vì bản thân *kiểu mảng* không phải lớp record. Nếu cần biết **phần tử mảng** có phải record hay không, kiểm tra `getComponentType()`:

```java
System.out.println(OrderId[].class.isRecord());                  // false
System.out.println(OrderId[].class.getComponentType().isRecord()); // true
```

Không nên gọi `getComponentType().isRecord()` trên một kiểu chưa được xác định là mảng vì `getComponentType()` sẽ trả về `null` khi kiểu đó không phải mảng.

## 4. Dùng `isRecord()` trước khi đọc metadata

`isRecord()` chỉ trả lời **có hay không**. Khi cần biết record gồm những thành phần nào, dùng thêm `Class.getRecordComponents()`, trả về mảng `java.lang.reflect.RecordComponent[]`.

| API | Ý nghĩa | Kết quả với kiểu không phải record |
| --- | --- | --- |
| `Class.isRecord()` | Nhận diện một lớp record | `false` |
| `Class.getRecordComponents()` | Lấy metadata các component trong record header | `null` |
| `RecordComponent.getName()` | Tên component | Chỉ gọi trên một `RecordComponent` đã lấy được |
| `RecordComponent.getType()` | Kiểu của component dưới dạng `Class<?>` | Chỉ gọi trên một `RecordComponent` đã lấy được |
| `RecordComponent.getGenericType()` | Thông tin kiểu khai báo, kể cả kiểu generic nếu có | Chỉ gọi trên một `RecordComponent` đã lấy được |
| `RecordComponent.getAccessor()` | Phương thức accessor tương ứng, chẳng hạn `name()` | Chỉ gọi trên một `RecordComponent` đã lấy được |

**Quy tắc quan trọng:**

- Nếu `type.isRecord() == false` thì `type.getRecordComponents() == null`.
- Nếu `type.isRecord() == true` thì `type.getRecordComponents()` **không null**; nó có thể là mảng rỗng khi record không có component.
- Các component được trả về **đúng thứ tự khai báo trong record header**.

Ví dụ một hàm đọc metadata để xây dựng mô tả cấu trúc đầu vào:

```java
import java.lang.reflect.RecordComponent;

public class RecordSchemaDemo {
    record Product(String sku, int quantity, double unitPrice) {}

    static void printSchema(Class<?> type) {
        if (type == null || !type.isRecord()) {
            throw new IllegalArgumentException("Expected a record class");
        }

        System.out.println("Record: " + type.getSimpleName());
        for (RecordComponent component : type.getRecordComponents()) {
            System.out.printf("- %s: %s%n",
                    component.getName(),
                    component.getType().getTypeName());
        }
    }

    public static void main(String[] args) {
        printSchema(Product.class);
    }
}
```

Kết quả:

```text
Record: Product
- sku: java.lang.String
- quantity: int
- unitPrice: double
```

Với ứng dụng sinh schema, kiểm tra `isRecord()` là bước đầu. Sau đó có thể dùng `RecordComponent` để lấy tên, kiểu, thông tin generic, annotation và accessor theo nhu cầu. Đây là các API reflection chuẩn; riêng `isRecord()` **không** tạo schema, chuyển đối tượng thành JSON hay tự động ánh xạ dữ liệu.

## 5. Phân biệt các trường hợp dễ nhầm

| Khai báo hoặc biểu thức | `isRecord()` | Giải thích |
| --- | :---: | --- |
| `record Point(int x, int y) {}` — `Point.class` | `true` | Được khai báo là record |
| `record Marker() {}` — `Marker.class` | `true` | Record không có component vẫn là record |
| `final class PointClass { ... }` — `PointClass.class` | `false` | `final` không đồng nghĩa với record |
| `java.lang.Record.class` | `false` | Đây là lớp nền, không phải khai báo record |
| `Point[].class` | `false` | Đây là kiểu mảng |
| `int.class` | `false` | Đây là kiểu nguyên thủy |
| `String.class` | `false` | Đây là lớp thông thường |

Một vài sai lầm cần tránh:

- **Đoán record bằng lớp cha.** Record có superclass trực tiếp là `java.lang.Record`, nhưng `Class.isRecord()` diễn đạt đúng chủ đích hơn và là API được thiết kế dành riêng cho việc nhận diện record.
- **Đếm field để nhận diện record.** `getDeclaredFields()` cho biết các trường khai báo trong lớp, kể cả trường `static`; nó không thay thế danh sách component trong record header. Hãy dùng `getRecordComponents()` khi cần metadata của record.
- **Cho rằng record luôn có component.** `record Empty() {}` là hợp lệ; mảng trả về từ `getRecordComponents()` trong trường hợp này có độ dài bằng 0.
- **Đồng nhất record với bất biến sâu.** Các field thành phần record là `final`, nhưng nếu một component tham chiếu tới đối tượng có thể thay đổi (chẳng hạn `List` có thể sửa), trạng thái bên trong đối tượng đó vẫn có thể thay đổi. Việc nhận diện bằng `isRecord()` không đưa ra đảm bảo về bất biến sâu.
- **Gọi reflection thiếu kiểm tra null.** Bản thân `type.isRecord()` yêu cầu `type` không null; và `getRecordComponents()` có thể trả về `null` đối với kiểu không phải record.

## 6. Khi nào nên áp dụng?

Trong mã ứng dụng thông thường, nếu đã biết rõ kiểu là record tại thời điểm biên dịch thì có thể truy cập component thông qua accessor như `product.sku()`, `product.quantity()`. Không cần reflection chỉ để sử dụng một record đã biết kiểu.

`Class.isRecord()` đặc biệt hữu ích khi **kiểu chỉ được biết tại runtime**:

1. Bộ sinh schema cần phân biệt record với lớp Java thông thường trước khi liệt kê các trường dữ liệu.
2. Thư viện mapping hoặc serialization cần lựa chọn nhánh xử lý thích hợp cho các component trong record header; khả năng hỗ trợ cụ thể vẫn phụ thuộc vào thư viện.
3. Công cụ kiểm tra cấu trúc mô hình dữ liệu cần áp dụng quy tắc riêng cho record, ví dụ báo lỗi nếu API yêu cầu input phải là record.
4. Bộ phân tích metadata hoặc công cụ tài liệu hóa cần hiển thị các component theo đúng thứ tự khai báo.

Nếu cần viết hàm kiểm tra để dùng lại trong ứng dụng, có thể kết hợp kiểm tra null ngay tại điểm đầu vào:

```java
static boolean isRecordType(Class<?> type) {
    return type != null && type.isRecord();
}
```

Hàm trên phù hợp khi nguồn cung cấp `Class<?>` có thể trả về `null`. Với một `Class<?>` chắc chắn không null, gọi trực tiếp `isRecord()` là đủ.

## 7. Tự kiểm tra kiến thức

**Câu 1.** Đoạn mã dưới đây in ra gì?

```java
class EmptyRecordCheck {
    record Empty() {}

    public static void main(String[] args) {
        System.out.println(Empty.class.isRecord());
        System.out.println(Empty.class.getRecordComponents().length);
    }
}
```

Đáp án: `true` và `0`. Record không bắt buộc phải có component.

**Câu 2.** Vì sao `java.lang.Record.class.isRecord()` trả về `false`?

Đáp án: `java.lang.Record` là lớp nền của record. Nó không phải một lớp được khai báo là record.

**Câu 3.** Có thể thay `type.isRecord()` bằng `type.getRecordComponents().length > 0` để nhận diện record không?

Đáp án: Không. Với kiểu không phải record, `getRecordComponents()` trả về `null`, dẫn tới `NullPointerException` khi truy cập `length`. Với record rỗng, độ dài bằng 0 dù đó vẫn là record.

**Câu 4.** Vì sao `SomeRecord[].class.isRecord()` trả về `false` trong khi phần tử mảng là record?

Đáp án: `isRecord()` đang kiểm tra đối tượng `Class` của **mảng**, không phải `Class` của kiểu phần tử. Cần lấy `getComponentType()` nếu mục tiêu là kiểm tra kiểu phần tử.

## Ghi nhớ

**`Class.isRecord()` là API chuẩn để xác định một `Class<?>` có đại diện cho lớp record hay không.** Nó có sẵn từ Java 16, hoạt động với cả record không có component và kết hợp tự nhiên với `getRecordComponents()` khi cần đọc metadata. Khi đầu vào có thể null hoặc là kiểu mảng, hãy xác định chính xác kiểu cần kiểm tra trước khi gọi phương thức.

## Tài liệu tham khảo

- [Oracle Java SE API — `Class.isRecord()` và `Class.getRecordComponents()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html)
- [Oracle Java SE API — `RecordComponent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html)
- [Oracle Java SE — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html)
