# Quy tắc đặt tên component và các tên xung đột với phương thức Object

## 1. Tên component trở thành tên accessor

Mỗi record component được khai báo bằng kiểu và một identifier trong record header. Nếu không tự khai báo accessor, Java cung cấp một phương thức public, không tham số, có tên trùng component.

```java
record Customer(String id, String displayName) {}

Customer customer = new Customer("C-100", "An");
System.out.println(customer.id());
System.out.println(customer.displayName());
```

Vì tên component trở thành một phần API công khai, việc đặt tên phải tuân thủ quy tắc identifier Java, bảo đảm duy nhất trong header và tránh xung đột với các phương thức không tham số của `java.lang.Object`.

Bài học tập trung vào quy tắc ổn định từ Java 16, vẫn áp dụng trong Java hiện đại.

## 2. Quy tắc cơ bản

Một component phải có kiểu và tên hợp lệ theo cú pháp identifier Java.

- Tên không được là từ khóa dành riêng như `class`, `int`, `return` hoặc `public`.
- Java phân biệt chữ hoa và chữ thường; `id` và `ID` là hai identifier khác nhau.
- Các component trong cùng header phải có tên khác nhau.
- Tên không được thuộc danh sách xung đột với phương thức không tham số của `Object`.
- Nên dùng lowerCamelCase theo convention Java; đây là quy ước, không phải ràng buộc cú pháp.

Ví dụ không hợp lệ vì trùng tên:

```java
// Lỗi biên dịch: hai component cùng tên.
// record Pair(String value, int value) {}
```

Ví dụ tốt:

```java
record InvoiceLine(String sku, int quantity, long unitPriceInCents) {}
```

## 3. Vì sao có tên bị cấm?

Mỗi component tạo accessor không tham số, ví dụ component `name` tạo `name()`. Nếu tên accessor trùng chữ ký với phương thức không tham số kế thừa từ `Object`, có thể xảy ra xung đột: phương thức do record cần cung cấp, hoặc phương thức final không thể bị override.

Do đó Java Language Specification định nghĩa một danh sách tên bị cấm ngay ở cấp ngôn ngữ. Vi phạm gây lỗi biên dịch, không chỉ là cảnh báo phong cách.

## 4. Tám tên component bị cấm

Java Language Specification quy định record không được khai báo component có một trong tám tên sau:

**`clone`, `finalize`, `getClass`, `hashCode`, `notify`, `notifyAll`, `toString`, `wait`.**

| Tên | Phương thức không tham số trong Object | Lý do chính |
| --- | --- | --- |
| `clone` | `protected Object clone()` | Record có thể khai báo `clone()`; component cùng tên sẽ không thể luôn có accessor riêng. |
| `finalize` | `protected void finalize()` | Record có thể khai báo `finalize()`; component cùng tên sẽ không thể luôn có accessor riêng. Phương thức này đã deprecated for removal. |
| `getClass` | `public final Class<?> getClass()` | Phương thức final, không thể bị accessor override. |
| `hashCode` | `public int hashCode()` | Record có phương thức hashCode() dựa trên toàn bộ component. |
| `notify` | `public final void notify()` | Phương thức final, không thể bị accessor override. |
| `notifyAll` | `public final void notifyAll()` | Phương thức final, không thể bị accessor override. |
| `toString` | `public String toString()` | Record có phương thức toString() mô tả toàn bộ record. |
| `wait` | `public final void wait()` | Phương thức final, không thể bị accessor override. |

Các khai báo sau đều gây lỗi biên dịch:

```java
// record A(String clone) {}
// record B(String finalize) {}
// record C(String getClass) {}
// record D(int hashCode) {}
// record E(boolean notify) {}
// record F(boolean notifyAll) {}
// record G(String toString) {}
// record H(long wait) {}
```

Danh sách cấm xét tên chính xác, không phải mọi tên chứa các chuỗi đó. `waitDuration`, `hashCodeText` và `toStringValue` không bị cấm.

## 5. Vì sao equals được phép nhưng hashCode bị cấm?

`Object` có `equals(Object)` nhận một tham số, trong khi accessor cho component `equals` có dạng `equals()` không tham số. Hai chữ ký khác nhau nên có thể cùng tồn tại.

```java
record ComparisonLabel(String equals, String hashCodeText) {}

ComparisonLabel label = new ComparisonLabel("same", "computed");
System.out.println(label.equals()); // accessor component
System.out.println(label.hashCode()); // hashCode() của record
System.out.println(label.equals(new ComparisonLabel("same", "computed")));
```

Ở ví dụ này:

- `label.equals()` trả về giá trị component kiểu `String`.
- `label.hashCode()` vẫn là phương thức mã băm của record.
- `label.equals(other)` vẫn là phương thức so sánh object nhận một đối số.

Ngược lại, accessor cho component `hashCode` sẽ có cùng chữ ký `hashCode()` mà record cung cấp. Tương tự, `toString` bị cấm vì accessor sẽ xung đột với `toString()`.

Không nên tự suy rộng danh sách: `equals`, `getName`, `hashCodeText` và `toStringValue` không thuộc tám tên bị cấm.

## 6. Tên gần giống vẫn hợp lệ

| Component | Accessor |
| --- | --- |
| `getClassName` | `getClassName()` |
| `hashCodeText` | `hashCodeText()` |
| `toStringValue` | `toStringValue()` |
| `waitDuration` | `waitDuration()` |
| `notifyAdmin` | `notifyAdmin()` |
| `finalizeAt` | `finalizeAt()` |
| `cloneCount` | `cloneCount()` |
| `equals` | `equals()` |

Java phân biệt hoa thường, nên `HashCode` không phải cùng identifier với `hashCode`. Tuy vậy, nên tuân thủ lowerCamelCase và chọn tên theo ý nghĩa dữ liệu. Ví dụ `checksum`, `digest` hoặc `hashValue` thường rõ nghĩa hơn `HashCode`.

## 7. Lưu ý hiện đại về finalize

`finalize` vẫn nằm trong danh sách tên component bị cấm của JLS. Tuy nhiên, `Object.finalize()` đã deprecated for removal; không nên dùng finalization để giải phóng tài nguyên trong code mới.

Với file, socket hoặc kết nối, hãy dùng `AutoCloseable` và `try-with-resources`. Nếu cần lưu thời điểm hoàn tất công việc, chọn tên như `finalizedAt`, `completedAt` hoặc `closedAt`, không dùng chính xác tên component `finalize`.

## 8. Tên component là hợp đồng API

Từ khai báo:

```java
public record Customer(String name) {}
```

đổi component `name` thành `fullName` sẽ đổi accessor từ `name()` sang `fullName()` và thay đổi tên tham số canonical constructor. Code gọi `customer.name()` sẽ không còn biên dịch.

Khi record được dùng trong API công khai hoặc DTO giữa các tầng:

- Chọn tên thể hiện ý nghĩa nghiệp vụ.
- Dùng lowerCamelCase nhất quán.
- Tránh tên quá chung chung nếu có tên cụ thể hơn.
- Không giả định accessor mặc định có tiền tố `get`.
- Xem việc đổi tên component là thay đổi API; kiểm tra tác động đến code gọi, reflection, serializer và framework.

Record `Person(String name)` cung cấp `name()`, không tự cung cấp `getName()`. Nếu thư viện yêu cầu JavaBean convention, kiểm tra khả năng hỗ trợ record của thư viện đó.

## 9. Kiểm tra component bằng reflection

Reflection cho phép đọc tên component của một record sau khi biên dịch. API này hữu ích khi xây dựng công cụ tài liệu hóa hoặc kiểm tra cấu trúc kiểu ở runtime.

```java
import java.lang.reflect.RecordComponent;

record Customer(String id, String displayName, int points) {}

public class InspectRecord {
    public static void main(String[] args) {
        Class<?> type = Customer.class;
        if (type.isRecord()) {
            for (RecordComponent component : type.getRecordComponents()) {
                System.out.println(component.getName());
                System.out.println(component.getType().getTypeName());
                System.out.println(component.getAccessor().getName());
            }
        }
    }
}
```

`Class.isRecord()` nhận diện record class. `Class.getRecordComponents()` trả metadata component theo thứ tự header; mỗi `RecordComponent` cho phép đọc tên, kiểu và accessor. Reflection quan sát cấu trúc đã biên dịch, không bỏ qua các quy tắc tên của compiler.

## 10. Ví dụ tổng hợp

```java
import java.lang.reflect.RecordComponent;

public class Demo {
    record ApiOperation(
        String operationId,
        String displayName,
        String checksum,
        long waitDurationMillis,
        String completionTime
    ) {}

    public static void main(String[] args) {
        ApiOperation operation = new ApiOperation(
            "OP-100", "Create customer", "sha256:abc123", 500,
            "2026-11-27T10:30:00Z"
        );

        System.out.println(operation.operationId());
        System.out.println(operation.displayName());
        System.out.println(operation.checksum());
        System.out.println(operation.waitDurationMillis());
        System.out.println(operation.completionTime());

        for (RecordComponent component : ApiOperation.class.getRecordComponents()) {
            System.out.println(
                component.getName() + " -> " + component.getAccessor().getName()
            );
        }
    }
}
```

Biên dịch bằng JDK 16 trở lên:

```bash
javac --release 16 Demo.java
java Demo
```

Các tên component đều hợp lệ và thể hiện dữ liệu nghiệp vụ, không trùng tám tên bị cấm.

## 11. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Component tên `toString` | Xung đột với phương thức record `toString()`. | Dùng `description` hoặc `displayText`. |
| Component tên `hashCode` | Xung đột với `hashCode()`. | Dùng `checksum` hoặc `digest`. |
| Component tên `getClass` | Xung đột với phương thức final của `Object`. | Dùng `className` hoặc `runtimeTypeName`. |
| Hai component trùng tên | Header yêu cầu identifier duy nhất. | Đặt tên khác nhau theo ý nghĩa. |
| Cho rằng `equals` bị cấm | Nhầm `equals()` với `equals(Object)`. | Phân biệt số tham số và chữ ký. |
| Dựa vào `finalize()` để giải phóng tài nguyên | Finalization đã deprecated for removal. | Dùng `AutoCloseable` và `try-with-resources`. |
| Đổi tên component tùy tiện | Accessor và constructor API thay đổi. | Quản lý đổi tên như thay đổi API. |

## 12. Bài tập thực hành

1. Khai báo `record Product(String sku, String description, int quantity)` và liệt kê accessor được tạo.
2. Giải thích vì sao `record Result(String equals)` hợp lệ nhưng `record Result(String hashCode)` không hợp lệ.
3. Phân loại tám tên bị cấm theo nguyên nhân xung đột: phương thức record cung cấp, phương thức final của `Object` và phương thức kế thừa có thể xung đột.
4. Đổi các tên `value1`, `value2`, `data` thành tên component rõ nghĩa cho mô hình đơn hàng.
5. Dùng `Class.getRecordComponents()` để in tên và kiểu component.
6. Giải thích vì sao đổi `name` thành `fullName` làm code gọi accessor cũ không biên dịch.

## Ghi nhớ

Tên component là một phần API record vì Java tạo accessor không tham số cùng tên từ mỗi component. Tên phải là identifier hợp lệ, duy nhất trong cùng header và không được là một trong tám tên `clone`, `finalize`, `getClass`, `hashCode`, `notify`, `notifyAll`, `toString`, `wait`. `equals` được phép vì accessor `equals()` khác chữ ký với `Object.equals(Object)`. Các tên gần giống như `hashCodeText` và `waitDuration` vẫn hợp lệ, nhưng nên ưu tiên tên có ý nghĩa nghiệp vụ và lowerCamelCase. Đây là quy tắc ngôn ngữ ổn định của Java record, không phải cảnh báo phong cách.

**Tài liệu tham khảo chính thức:**

- [Java Language Specification – Record Classes, mục 8.10.1](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10.1)
- [Java Language Specification Java SE 16 – Record Classes](https://docs.oracle.com/javase/specs/jls/se16/jls16.pdf)
- [Java API – java.lang.Object](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html)
- [Java API – java.lang.reflect.RecordComponent](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/RecordComponent.html)
