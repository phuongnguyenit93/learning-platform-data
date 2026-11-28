# Record implements interface và triển khai hành vi theo hợp đồng

## 1. Record có thể triển khai interface

Record là một dạng class mang dữ liệu, nhưng vẫn tham gia hệ thống kiểu Java như các class khác. Một record có thể triển khai một hoặc nhiều interface bằng từ khóa `implements`. Nhờ vậy, ta kết hợp cấu trúc dữ liệu trong record header với hợp đồng hành vi do interface định nghĩa.

```java
interface Identified {
    String id();
}

record Customer(String id, String name) implements Identified {}
```

Record `Customer` có component `id`. Java tự cung cấp accessor công khai `id()`, accessor này đồng thời đáp ứng phương thức `id()` trong interface `Identified`. Không cần viết lại phương thức nếu chữ ký tương thích.

Record được hoàn thiện trong Java 16 và khả năng triển khai interface vẫn là phần ổn định của Java hiện đại.

Mục tiêu bài học:

- Hiểu quan hệ giữa record và interface.
- Biết accessor sinh từ component có thể đáp ứng abstract method của interface.
- Triển khai hành vi còn thiếu trong record body.
- Kết hợp generic interface, default method và nhiều interface.
- Xử lý xung đột default method và khác biệt chữ ký.
- Chọn interface phù hợp để record tham gia kiến trúc ứng dụng.

## 2. Cú pháp implements trong record declaration

Cấu trúc khai báo:

```java
record RecordName(Type component1, Type component2)
        implements InterfaceA, InterfaceB {
    // Constructor và các phương thức bổ sung
}
```

Record có thể triển khai nhiều interface, phân cách bằng dấu phẩy. Record không thể `extends` class nghiệp vụ khác vì lớp cha trực tiếp của mọi record đã cố định là `java.lang.Record`; tuy nhiên, nó có thể triển khai hợp đồng từ nhiều interface.

Ví dụ:

```java
interface Identified {
    String id();
}

interface Describable {
    String description();
}

record Product(String id, String name)
        implements Identified, Describable {

    @Override
    public String description() {
        return id + " - " + name;
    }
}
```

`Product` triển khai hai interface:

- `Identified` được đáp ứng bởi accessor `id()` sinh từ component `id`.
- `Describable` được đáp ứng bằng phương thức `description()` do record tự triển khai.

Code gọi có thể phụ thuộc vào interface mà không cần biết record đang lưu những component nào ngoài những gì hợp đồng công khai.

## 3. Accessor được sinh tự động có thể triển khai abstract method

Một interface có thể khai báo phương thức trừu tượng. Nếu phương thức đó trùng tên, không có tham số và có kiểu trả về tương thích với accessor của một component, accessor được sinh tự động có thể triển khai phương thức đó.

```java
interface HasName {
    String name();
}

record Person(String name, int age) implements HasName {}
```

Record `Person` không cần viết phương thức `name()` vì component `name` đã làm phát sinh accessor công khai tương ứng.

Có thể sử dụng qua kiểu interface:

```java
Person person = new Person("Lan", 25);

HasName named = person;
System.out.println(named.name()); // Lan
```

Đối tượng thực tế vẫn là `Person`. Biến `named` chỉ giới hạn những thao tác có thể gọi ở hợp đồng `HasName`.

### Kiểu trả về phải tương thích

Accessor mặc định có kiểu trả về đúng bằng kiểu component. Khi đáp ứng phương thức interface, kiểu trả về phải tuân thủ quy tắc override của Java.

Với kiểu tham chiếu, kiểu component có thể là kiểu con của kiểu trả về trong interface nhờ covariant return:

```java
interface HasLabel {
    CharSequence label();
}

record ProductLabel(String label) implements HasLabel {}
```

Accessor `String label()` của `ProductLabel` có thể triển khai `CharSequence label()` vì `String` là subtype của `CharSequence`.

Ngược lại, nếu kiểu component không tương thích với kiểu trả về của interface, accessor không thể đáp ứng hợp đồng đó:

```java
interface HasCount {
    long count();
}

// Không hợp lệ: accessor count() trả int, không thể override long count().
// record ItemCount(int count) implements HasCount {}
```

Không thể khai báo thêm một phương thức `count()` chỉ khác kiểu trả về để sửa lỗi, vì Java không cho overload phương thức chỉ dựa trên kiểu trả về. Hãy đổi tên component hoặc thiết kế lại hợp đồng nếu cần.

### Interface dùng JavaBean getter không tự được đáp ứng

Accessor record không tự thêm tiền tố `get`:

```java
interface HasDisplayName {
    String getDisplayName();
}

// Component displayName tạo displayName(), không tạo getDisplayName().
record User(String displayName) implements HasDisplayName {
    @Override
    public String getDisplayName() {
        return displayName;
    }
}
```

Trong trường hợp này, record phải triển khai `getDisplayName()` tường minh. Không nên giả định component `displayName` tự đáp ứng một interface chỉ khai báo `getDisplayName()`.

## 4. Triển khai hành vi còn thiếu trong record body

Record không chỉ có component và accessor. Ta có thể thêm phương thức instance để triển khai hợp đồng nghiệp vụ, miễn là không bổ sung field instance ngoài header.

```java
interface Billable {
    long totalInCents();
}

record OrderLine(String sku, int quantity, long unitPriceInCents)
        implements Billable {

    @Override
    public long totalInCents() {
        return quantity * unitPriceInCents;
    }
}
```

Các component mô tả dữ liệu đầu vào; phương thức `totalInCents()` tính kết quả từ dữ liệu đó. Không cần lưu thêm field tổng tiền có thể trở nên lệch với `quantity` hoặc `unitPriceInCents`.

Sử dụng qua interface:

```java
Billable line = new OrderLine("SKU-01", 3, 25_000);
System.out.println(line.totalInCents()); // 75000
```

### Kiểm tra dữ liệu tại constructor

Interface mô tả hành vi mà object cung cấp; constructor vẫn chịu trách nhiệm bảo đảm trạng thái record hợp lệ:

```java
import java.util.Objects;

interface Billable {
    long totalInCents();
}

record OrderLine(String sku, int quantity, long unitPriceInCents)
        implements Billable {

    OrderLine {
        sku = Objects.requireNonNull(sku, "sku").strip();
        if (sku.isEmpty()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (quantity <= 0 || unitPriceInCents < 0) {
            throw new IllegalArgumentException("Invalid order line values");
        }
    }

    @Override
    public long totalInCents() {
        return Math.multiplyExact(quantity, unitPriceInCents);
    }
}
```

Compact canonical constructor xác thực component khi tạo record. `Math.multiplyExact` giúp phát hiện tràn số nguyên thay vì âm thầm trả kết quả sai. Đây là cách kết hợp invariant dữ liệu với hành vi theo interface.

## 5. Record triển khai generic interface

Record có thể triển khai interface generic như class thông thường. Type parameter của record có thể được truyền vào interface:

```java
interface ValueProvider<T> {
    T value();
}

record ConstantValue<T>(T value) implements ValueProvider<T> {}
```

Accessor `value()` sinh từ component đáp ứng phương thức `value()` trong `ValueProvider<T>`.

Sử dụng:

```java
ValueProvider<String> text = new ConstantValue<>("Java");
ValueProvider<Integer> number = new ConstantValue<>(16);

System.out.println(text.value());   // Java
System.out.println(number.value()); // 16
```

Record cũng có thể triển khai interface generic với kiểu cố định:

```java
interface Identifier {
    String id();
}

record CustomerId(String id) implements Identifier {}
```

Hoặc triển khai một interface có nhiều tham số kiểu:

```java
interface Converter<S, R> {
    R convert(S source);
}

record StringLengthConverter(String name)
        implements Converter<String, Integer> {

    @Override
    public Integer convert(String source) {
        return source.length();
    }
}
```

Trong ví dụ cuối, record phải triển khai `convert(String)` vì không có component nào tạo accessor tương ứng. Việc khai báo `implements Converter<String, Integer>` xác định kiểu đầu vào và đầu ra của hợp đồng.

## 6. Kết hợp nhiều interface và default method

Interface có thể cung cấp default method. Record có thể thừa hưởng phương thức mặc định đó mà không cần viết lại:

```java
interface Described {
    String name();

    default String description() {
        return "Item: " + name();
    }
}

record Product(String name) implements Described {}
```

Accessor `name()` được sinh tự động đáp ứng abstract method của `Described`. Phương thức `description()` được thừa hưởng từ default method.

Nếu record cần thay đổi hành vi mặc định, có thể override:

```java
record Product(String name) implements Described {
    @Override
    public String description() {
        return "Product[" + name + "]";
    }
}
```

### Xử lý xung đột giữa các default method

Nếu hai interface không có quan hệ kế thừa cung cấp default method cùng chữ ký, record phải override phương thức để giải quyết xung đột:

```java
interface Printable {
    default String label() {
        return "Printable";
    }
}

interface Auditable {
    default String label() {
        return "Auditable";
    }
}

record Document(String id) implements Printable, Auditable {
    @Override
    public String label() {
        return Printable.super.label() + ":" + id;
    }
}
```

`Document` chọn rõ triển khai từ `Printable` bằng cú pháp `Printable.super.label()`. Record có thể kết hợp kết quả từ nhiều default method nếu nghiệp vụ yêu cầu.

Nếu một interface chỉ khai báo abstract method và interface còn lại cung cấp default method có chữ ký tương thích, default method có thể đáp ứng hợp đồng abstract. Tuy nhiên, khi có nhiều default method xung đột, cần override tường minh.

### Static method của interface không được kế thừa như instance method

Static method thuộc về interface khai báo nó. Record không gọi static method đó qua instance:

```java
interface Identifiers {
    static boolean isValid(String id) {
        return id != null && !id.isBlank();
    }
}

record CustomerId(String value) {}

class IdentifierDemo {
    public static void main(String[] args) {
        boolean valid = Identifiers.isValid("C-100");
        System.out.println(valid);
    }
}
```

Gọi bằng tên interface `Identifiers.isValid(...)`. Không dùng `customerId.isValid(...)` để gọi static method của interface.

## 7. Dùng interface để đa hình hóa các record

Một lợi ích lớn của interface là code xử lý có thể làm việc với nhiều record khác nhau qua cùng hợp đồng.

```java
interface Shape {
    double area();
}

record Circle(double radius) implements Shape {
    Circle {
        if (radius < 0) {
            throw new IllegalArgumentException("radius must be non-negative");
        }
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}

record Rectangle(double width, double height) implements Shape {
    Rectangle {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("dimensions must be non-negative");
        }
    }

    @Override
    public double area() {
        return width * height;
    }
}
```

Cả `Circle` và `Rectangle` đều triển khai `Shape`. Code gọi có thể xử lý danh sách các hình mà không cần biết từng record lưu component nào:

```java
import java.util.List;

List<Shape> shapes = List.of(
    new Circle(2),
    new Rectangle(3, 4)
);

double totalArea = shapes.stream()
    .mapToDouble(Shape::area)
    .sum();

System.out.println(totalArea);
```

Đây là đa hình thông qua interface. Record chịu trách nhiệm biểu diễn dữ liệu và triển khai hành vi riêng; code tổng quát phụ thuộc vào hợp đồng `Shape`.

### Pattern matching instanceof với interface

Pattern matching cho `instanceof` đã là tính năng chính thức trong Java 16 (JEP 394). Có thể dùng nó để kiểm tra object có triển khai interface hay không:

```java
class ShapePrinter {
    static void printArea(Object value) {
        if (value instanceof Shape shape) {
            System.out.println(shape.area());
        } else {
            System.out.println("Unsupported object");
        }
    }
}
```

Cách viết này áp dụng cho bất kỳ object nào triển khai `Shape`, không chỉ record. Nếu chỉ cần hành vi theo hợp đồng, nên kiểm tra interface thay vì phụ thuộc vào class record cụ thể.

## 8. Interface và giới hạn kế thừa của record

Record có thể triển khai nhiều interface nhưng không thể kế thừa một class nghiệp vụ khác. Mọi record đều có `java.lang.Record` làm lớp cha trực tiếp và ngầm định là `final`.

Vì vậy, khi thiết kế hợp đồng dùng chung:

- Dùng interface cho hành vi mà nhiều record hoặc class khác nhau cần cung cấp.
- Dùng component để mô tả dữ liệu riêng của từng record.
- Dùng default method cho hành vi chung có thể triển khai dựa trên các phương thức interface.
- Dùng composition nếu cần hợp tác với một object class khác.
- Không cố đưa trạng thái dùng chung vào superclass khi record cần triển khai hợp đồng đó; hãy cân nhắc interface và object được composition.

Ví dụ interface định nghĩa hợp đồng, còn record giữ dữ liệu riêng:

```java
interface Auditable {
    String createdBy();
    java.time.Instant createdAt();

    default boolean createdBySystem() {
        return "system".equalsIgnoreCase(createdBy());
    }
}

record AuditEntry(
    String createdBy,
    java.time.Instant createdAt,
    String action
) implements Auditable {}
```

Hai accessor `createdBy()` và `createdAt()` đáp ứng interface; default method `createdBySystem()` sử dụng các accessor đó để tạo hành vi chung.

## 9. Các quy tắc chữ ký cần kiểm tra khi implements

| Thành phần hợp đồng | Quy tắc |
| --- | --- |
| Abstract method | Record phải triển khai bằng accessor tương thích hoặc phương thức tường minh, trừ khi method được đáp ứng bởi default method kế thừa. |
| Accessor component | Có tên trùng component, không tham số, public và có kiểu trả về đúng kiểu component. |
| Kiểu trả về | Phải tương thích theo quy tắc override; kiểu tham chiếu có thể dùng covariant return. |
| Phương thức có tham số | Accessor không đáp ứng được vì chữ ký khác; cần triển khai phương thức riêng. |
| Default method | Được thừa hưởng nếu không có xung đột; có thể override để tùy chỉnh. |
| Nhiều default method cùng chữ ký | Phải giải quyết bằng override tường minh. |
| Static method của interface | Gọi qua tên interface; không phải instance method được kế thừa. |
| Generic interface | Type parameter phải được cung cấp hoặc truyền tiếp theo khai báo generic record. |

Ví dụ interface yêu cầu phương thức có tham số, nên accessor không thể đáp ứng:

```java
interface Validator<T> {
    boolean isValid(T value);
}

record EmailAddress(String value) implements Validator<String> {
    @Override
    public boolean isValid(String candidate) {
        return candidate != null && candidate.contains("@");
    }
}
```

Component `value` chỉ tạo `value()` không tham số. Phương thức `isValid(String)` có tham số nên cần triển khai riêng.

## 10. Ví dụ hoàn chỉnh: record làm DTO và triển khai hợp đồng

Ví dụ sau kết hợp accessor, phương thức nghiệp vụ, generic interface, default method và đa hình. Lưu vào tệp **`Demo.java`**:

```java
import java.util.List;
import java.util.Objects;

public class Demo {
    interface Identified {
        String id();
    }

    interface Described {
        String description();

        default String display() {
            return description();
        }
    }

    interface RepositoryView<T> {
        T value();
    }

    record Customer(String id, String name)
            implements Identified, Described {

        Customer {
            id = Objects.requireNonNull(id, "id").strip();
            name = Objects.requireNonNull(name, "name").strip();

            if (id.isEmpty() || name.isEmpty()) {
                throw new IllegalArgumentException("id and name are required");
            }
        }

        @Override
        public String description() {
            return id + " - " + name;
        }
    }

    record DataView<T>(String key, T value)
            implements RepositoryView<T> {}

    public static void main(String[] args) {
        Customer customer = new Customer(" C-01 ", " Lan ");

        Identified identified = customer;
        Described described = customer;

        System.out.println(identified.id());       // C-01
        System.out.println(described.display());   // C-01 - Lan

        List<Described> items = List.of(
            customer,
            new Customer("C-02", "Minh")
        );

        items.stream()
            .map(Described::description)
            .forEach(System.out::println);

        RepositoryView<Integer> count =
            new DataView<>("active-users", 120);

        System.out.println(count.value()); // 120
    }
}
```

Biên dịch và chạy trên JDK 16 trở lên:

```bash
javac --release 16 Demo.java
java Demo
```

Điểm cần quan sát:

1. `Customer` triển khai hai interface; accessor `id()` đáp ứng `Identified`, còn `description()` được triển khai tường minh.
2. `Described` có default method `display()`; record thừa hưởng phương thức này.
3. Danh sách `List<Described>` có thể chứa nhiều record khác nhau miễn cùng triển khai interface.
4. `DataView<T>` triển khai generic interface `RepositoryView<T>`; accessor `value()` đáp ứng hợp đồng.
5. Compact constructor xác thực và chuẩn hóa dữ liệu trước khi object được sử dụng qua interface.

## 11. Lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Nghĩ component tự tạo getter JavaBean | Accessor mặc định là `name()`, không phải `getName()`. | Triển khai getter interface tường minh nếu hợp đồng yêu cầu. |
| Component trùng tên nhưng sai kiểu trả về interface | Accessor không thỏa quy tắc override. | Chọn kiểu component tương thích hoặc đổi tên component và triển khai method riêng nếu khả thi. |
| Quên triển khai abstract method có tham số | Accessor chỉ có chữ ký không tham số. | Viết phương thức đúng chữ ký trong record body. |
| Hai interface có default method cùng chữ ký | Không có lựa chọn mặc định duy nhất. | Override phương thức và chọn rõ `InterfaceName.super.method()`. |
| Gọi static method interface qua instance | Static method thuộc interface, không được kế thừa như instance method. | Gọi bằng `InterfaceName.method()`. |
| Cố `extends` class nghiệp vụ | Record đã có `java.lang.Record` làm superclass. | Dùng interface hoặc composition. |
| Dùng interface chỉ để truy cập mọi component | Mỗi record có header và accessor riêng. | Khai báo interface mô tả đúng hợp đồng nghiệp vụ cần dùng. |
| Cho rằng implements interface làm record mutable | Interface chỉ quy định hành vi; field component vẫn final. | Giữ dữ liệu qua component và bảo vệ object mutable bên trong khi cần. |

## 12. Bài tập thực hành

1. Khai báo interface `HasCode` có phương thức `String code()`. Tạo record `Product(String code, String name)` implements interface mà không viết lại accessor.
2. Khai báo interface `HasLabel` có `CharSequence label()`. Dùng record component kiểu `String` để đáp ứng phương thức và giải thích covariant return.
3. Khai báo interface `Describable` có abstract method `description()` và default method `display()`. Viết record triển khai abstract method và gọi default method.
4. Tạo hai interface cùng khai báo default method `label()`. Viết record implements cả hai và giải quyết xung đột.
5. Khai báo generic interface `ValueProvider<T>` và record `Value<T>(T value)` implements interface. Tạo instance cho String và Integer.
6. Viết interface có phương thức nhận tham số, sau đó chứng minh accessor không thể thay thế phương thức đó.
7. Tạo interface `Shape` và hai record `Circle`, `Rectangle`; dùng `List<Shape>` để tính tổng diện tích.

## Ghi nhớ

Record có thể triển khai một hoặc nhiều interface để tham gia hợp đồng hành vi trong ứng dụng. Accessor được sinh từ component có thể đáp ứng abstract method nếu tên, số tham số và kiểu trả về tương thích; phương thức có tham số hoặc khác chữ ký phải được triển khai tường minh. Record cũng có thể triển khai generic interface, thừa hưởng default method và override để giải quyết xung đột giữa nhiều interface. Static method của interface được gọi qua tên interface. Vì record không thể extends class nghiệp vụ, interface là cơ chế quan trọng để chia sẻ hợp đồng mà vẫn giữ cấu trúc dữ liệu gọn và rõ. Các quy tắc này là phần ổn định của Java record và interface, tiếp tục áp dụng trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
- [Java Language Specification – Interfaces, mục 9](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html)
- [Java Language Specification – Method Overriding, mục 8.4.8](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.4.8)
- [OpenJDK JEP 394 – Pattern Matching for instanceof](https://openjdk.org/jeps/394)
