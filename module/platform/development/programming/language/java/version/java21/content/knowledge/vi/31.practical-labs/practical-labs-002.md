# Xây bộ xử lý dữ liệu bằng record pattern lồng nhau và pattern switch

Bài thực hành này xây dựng một bộ xử lý sự kiện đơn hàng bằng các tính năng đã được hoàn thiện trong Java 21: **record**, **sealed interface**, **record pattern lồng nhau** và **pattern matching for switch**. Mục tiêu là nhận các sự kiện có cấu trúc, phân rã dữ liệu ngay trong nhánh `switch`, áp dụng điều kiện bằng `when` và tạo kết quả tương ứng với từng loại sự kiện.

Bộ xử lý dùng dữ liệu bất biến để mô hình hóa đơn hàng, khách hàng, tiền tệ, thanh toán và vận chuyển. Khi thêm một loại sự kiện mới vào sealed hierarchy, compiler có thể yêu cầu cập nhật switch expression, giúp phát hiện trường hợp xử lý còn thiếu ngay ở compile time.

Các tính năng được sử dụng trong lab là tính năng chính thức của Java 21. Không cần bật preview flag.

## 1. Mục tiêu thực hành

Sau khi hoàn thành, bạn có thể:

- Thiết kế domain model bằng record và sealed interface.
- Dùng record pattern để lấy component của record mà không phải gọi accessor thủ công.
- Lồng record pattern để phân rã dữ liệu nhiều cấp.
- Dùng pattern matching trong switch expression để xử lý nhiều kiểu sự kiện.
- Dùng guard clause `when` để phân nhánh theo giá trị bên trong record.
- Xử lý `null` tường minh trong switch.
- Dùng tính exhaustive của switch trên sealed hierarchy.
- Viết dữ liệu mẫu, xác minh output và mở rộng bộ xử lý.

## 2. Bài toán

Một dịch vụ đơn hàng nhận bốn loại domain event:

| Sự kiện | Dữ liệu cần xử lý | Kết quả mong muốn |
|---|---|---|
| `OrderPlaced` | Mã đơn, khách hàng, tổng tiền, danh sách mặt hàng | Xác nhận đơn hoặc báo đơn không có mặt hàng |
| `PaymentReceived` | Mã đơn, số tiền thanh toán, mã thanh toán | Chấp nhận khoản thanh toán dương hoặc từ chối khoản không hợp lệ |
| `ShipmentSent` | Mã đơn, mã vận đơn, địa chỉ nhận | Tạo thông báo vận chuyển |
| `CustomerChanged` | Thông tin khách hàng, các trường đã thay đổi | Tạo thông báo cập nhật hồ sơ |

Mỗi event là một kiểu dữ liệu riêng. Thay vì viết chuỗi `instanceof` rồi ép kiểu, ta dùng một switch expression để nhận diện kiểu event và phân rã record trực tiếp trong từng case.

Một số record chứa record khác. Ví dụ `OrderPlaced` có `Customer` và `Money`; `ShipmentSent` có `Address`. Đây là nơi record pattern lồng nhau giúp code thể hiện đúng cấu trúc dữ liệu.

## 3. Thiết kế domain model

Tạo file `Main.java`. Trước tiên, khai báo các record dùng trong bài:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

record Customer(String id, String name, String email) {
    Customer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(email, "email");

        if (id.isBlank() || name.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer id và name không được để trống");
        }
    }
}

record Money(BigDecimal amount, String currency) {
    Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        if (currency.isBlank()) {
            throw new IllegalArgumentException(
                    "currency không được để trống");
        }
    }
}

record LineItem(String sku, int quantity, Money unitPrice) {
    LineItem {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException(
                    "sku phải có giá trị và quantity phải dương");
        }
    }
}

record Address(String city, String country) {
    Address {
        Objects.requireNonNull(city, "city");
        Objects.requireNonNull(country, "country");
    }
}
```

Các record này đại diện cho dữ liệu có cấu trúc:

- `Customer` mô tả khách hàng.
- `Money` giữ số tiền và đơn vị tiền tệ.
- `LineItem` mô tả một mặt hàng trong đơn.
- `Address` mô tả địa chỉ giao hàng.

Compact constructor được dùng để xác thực dữ liệu khi tạo record. Điều này giúp bộ xử lý phía sau có thể dựa vào các invariant cơ bản, chẳng hạn `Customer.id` không null và `LineItem.quantity` phải lớn hơn 0.

Record cung cấp tính bất biến nông (shallow immutability): các component không thể được gán lại sau khi tạo record, nhưng nếu component tham chiếu tới collection mutable thì collection đó vẫn có thể bị thay đổi. Vì vậy, các event chứa collection sẽ sao chép phòng vệ bằng `List.copyOf` hoặc `Set.copyOf`.

## 4. Khai báo sealed hierarchy cho các event

Khai báo một sealed interface để giới hạn những loại event được phép xuất hiện:

```java
sealed interface DomainEvent
        permits OrderPlaced, PaymentReceived,
                ShipmentSent, CustomerChanged {
}

record OrderPlaced(
        String orderId,
        Customer customer,
        Money total,
        List<LineItem> items
) implements DomainEvent {
    OrderPlaced {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customer, "customer");
        Objects.requireNonNull(total, "total");
        items = List.copyOf(items);
    }
}

record PaymentReceived(
        String orderId,
        Money amount,
        String paymentId
) implements DomainEvent {
    PaymentReceived {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(paymentId, "paymentId");
    }
}

record ShipmentSent(
        String orderId,
        String trackingCode,
        Address destination
) implements DomainEvent {
    ShipmentSent {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(trackingCode, "trackingCode");
        Objects.requireNonNull(destination, "destination");
    }
}

record CustomerChanged(
        Customer customer,
        Set<String> changedFields
) implements DomainEvent {
    CustomerChanged {
        Objects.requireNonNull(customer, "customer");
        changedFields = Set.copyOf(changedFields);
    }
}
```

`DomainEvent` chỉ cho phép bốn kiểu con được liệt kê trong `permits`. Các record trong ví dụ nằm cùng package với sealed interface, phù hợp với quy tắc sealed type trong unnamed module.

Các collection được sao chép trong constructor của event. Vì `LineItem`, `Customer`, `Money` và `Address` đều là record dữ liệu bất biến trong ví dụ này, việc sao chép danh sách và tập hợp giúp event không bị thay đổi gián tiếp qua collection mà caller giữ lại.

Khi thêm một event mới, ví dụ `OrderCancelled`, cần thêm nó vào `permits`. Compiler sẽ giúp tìm các switch expression chưa xử lý kiểu mới nếu chúng dựa trên tính exhaustive của sealed hierarchy.

## 5. Viết switch expression với record pattern lồng nhau

Phần quan trọng của lab là phương thức `describe`. Phương thức nhận một `DomainEvent` và trả về chuỗi mô tả phù hợp.

```java
static String describe(DomainEvent event) {
    return switch (event) {
        case null ->
                "INVALID: null event";

        case OrderPlaced(
                String orderId,
                Customer(var customerId, var name, var email),
                Money(var amount, var currency),
                var items
        ) when items.isEmpty() ->
                "ORDER_INVALID order=" + orderId
                        + " reason=no-items";

        case OrderPlaced(
                String orderId,
                Customer(var customerId, var name, var email),
                Money(var amount, var currency),
                var items
        ) ->
                "ORDER_PLACED order=" + orderId
                        + " customer=" + name + "(" + customerId + ")"
                        + " total=" + amount.toPlainString()
                        + " " + currency
                        + " items=" + formatItems(items);

        case PaymentReceived(
                String orderId,
                Money(var amount, var currency),
                String paymentId
        ) when amount.signum() <= 0 ->
                "PAYMENT_REJECTED order=" + orderId
                        + " payment=" + paymentId
                        + " amount=" + amount.toPlainString()
                        + " " + currency;

        case PaymentReceived(
                String orderId,
                Money(var amount, var currency),
                String paymentId
        ) ->
                "PAYMENT_RECEIVED order=" + orderId
                        + " payment=" + paymentId
                        + " amount=" + amount.toPlainString()
                        + " " + currency;

        case ShipmentSent(
                String orderId,
                String trackingCode,
                Address(var city, var country)
        ) ->
                "SHIPPED order=" + orderId
                        + " tracking=" + trackingCode
                        + " destination=" + city + ", " + country;

        case CustomerChanged(
                Customer(var customerId, var name, var email),
                var changedFields
        ) ->
                "CUSTOMER_CHANGED customer=" + customerId
                        + " fields=" + String.join(
                                ",",
                                changedFields.stream().sorted().toList()
                        );
    };
}
```

Đoạn switch có ba kỹ thuật quan trọng:

1. **Pattern matching for switch:** mỗi `case` nhận diện kiểu event.
2. **Record pattern lồng nhau:** `OrderPlaced` được phân rã cùng `Customer` và `Money`; `ShipmentSent` được phân rã cùng `Address`.
3. **Guard clause:** `when items.isEmpty()` và `when amount.signum() <= 0` bổ sung điều kiện dựa trên dữ liệu đã được phân rã.

Các biến được khai báo bằng `var` trong record pattern sẽ nhận kiểu tĩnh từ component tương ứng. Ví dụ `amount` có kiểu `BigDecimal`, `items` có kiểu `List<LineItem>`, và `city` có kiểu `String`.

### 5.1. Vì sao có hai case OrderPlaced?

Hai case cùng phân rã một cấu trúc `OrderPlaced`, nhưng xử lý hai tình huống:

- Case đầu có guard `items.isEmpty()`, nên chỉ khớp đơn không có mặt hàng.
- Case sau không có guard, nên xử lý các đơn còn lại.

Guard không thay thế pattern. Nó chỉ bổ sung điều kiện sau khi pattern đã khớp. Nếu guard trả về false, switch tiếp tục xét case tiếp theo.

Thứ tự case vì vậy rất quan trọng: case có điều kiện cụ thể cần đứng trước case tổng quát hơn.

### 5.2. Vì sao dùng var pattern bên trong record?

Ví dụ:

```java
Customer(var customerId, var name, var email)
```

Cấu trúc này phân rã record `Customer` và gán các component vào biến có kiểu được suy ra. Nó giúp tránh phải viết:

```java
Customer customer = order.customer();
String customerId = customer.id();
String name = customer.name();
String email = customer.email();
```

Record pattern đặc biệt hữu ích khi cấu trúc lồng nhau và cần lấy nhiều component trong cùng một nhánh xử lý.

## 6. Bổ sung hàm định dạng mặt hàng

Phương thức `formatItems` nhận danh sách mặt hàng và tạo chuỗi dễ đọc:

```java
static String formatItems(List<LineItem> items) {
    return items.stream()
            .map(item -> item.sku() + "x" + item.quantity())
            .collect(Collectors.joining(","));
}
```

Ví dụ danh sách gồm hai mặt hàng:

- SKU-1, số lượng 2.
- SKU-2, số lượng 1.

Kết quả là:

```text
SKU-1x2,SKU-2x1
```

Hàm này không phải phần bắt buộc của pattern matching, nhưng giúp nhánh xử lý event tập trung vào ý nghĩa nghiệp vụ thay vì lặp lại logic định dạng.

## 7. Ghép thành chương trình hoàn chỉnh

Thêm class `Main` và dữ liệu mẫu. Toàn bộ file `Main.java` có cấu trúc như sau:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

record Customer(String id, String name, String email) {
    Customer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(email, "email");

        if (id.isBlank() || name.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer id và name không được để trống");
        }
    }
}

record Money(BigDecimal amount, String currency) {
    Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        if (currency.isBlank()) {
            throw new IllegalArgumentException(
                    "currency không được để trống");
        }
    }
}

record LineItem(String sku, int quantity, Money unitPrice) {
    LineItem {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException(
                    "sku phải có giá trị và quantity phải dương");
        }
    }
}

record Address(String city, String country) {
    Address {
        Objects.requireNonNull(city, "city");
        Objects.requireNonNull(country, "country");
    }
}

sealed interface DomainEvent
        permits OrderPlaced, PaymentReceived,
                ShipmentSent, CustomerChanged {
}

record OrderPlaced(
        String orderId,
        Customer customer,
        Money total,
        List<LineItem> items
) implements DomainEvent {
    OrderPlaced {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customer, "customer");
        Objects.requireNonNull(total, "total");
        items = List.copyOf(items);
    }
}

record PaymentReceived(
        String orderId,
        Money amount,
        String paymentId
) implements DomainEvent {
    PaymentReceived {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(paymentId, "paymentId");
    }
}

record ShipmentSent(
        String orderId,
        String trackingCode,
        Address destination
) implements DomainEvent {
    ShipmentSent {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(trackingCode, "trackingCode");
        Objects.requireNonNull(destination, "destination");
    }
}

record CustomerChanged(
        Customer customer,
        Set<String> changedFields
) implements DomainEvent {
    CustomerChanged {
        Objects.requireNonNull(customer, "customer");
        changedFields = Set.copyOf(changedFields);
    }
}

public class Main {
    static String describe(DomainEvent event) {
        return switch (event) {
            case null ->
                    "INVALID: null event";

            case OrderPlaced(
                    String orderId,
                    Customer(var customerId, var name, var email),
                    Money(var amount, var currency),
                    var items
            ) when items.isEmpty() ->
                    "ORDER_INVALID order=" + orderId
                            + " reason=no-items";

            case OrderPlaced(
                    String orderId,
                    Customer(var customerId, var name, var email),
                    Money(var amount, var currency),
                    var items
            ) ->
                    "ORDER_PLACED order=" + orderId
                            + " customer=" + name + "(" + customerId + ")"
                            + " total=" + amount.toPlainString()
                            + " " + currency
                            + " items=" + formatItems(items);

            case PaymentReceived(
                    String orderId,
                    Money(var amount, var currency),
                    String paymentId
            ) when amount.signum() <= 0 ->
                    "PAYMENT_REJECTED order=" + orderId
                            + " payment=" + paymentId
                            + " amount=" + amount.toPlainString()
                            + " " + currency;

            case PaymentReceived(
                    String orderId,
                    Money(var amount, var currency),
                    String paymentId
            ) ->
                    "PAYMENT_RECEIVED order=" + orderId
                            + " payment=" + paymentId
                            + " amount=" + amount.toPlainString()
                            + " " + currency;

            case ShipmentSent(
                    String orderId,
                    String trackingCode,
                    Address(var city, var country)
            ) ->
                    "SHIPPED order=" + orderId
                            + " tracking=" + trackingCode
                            + " destination=" + city + ", " + country;

            case CustomerChanged(
                    Customer(var customerId, var name, var email),
                    var changedFields
            ) ->
                    "CUSTOMER_CHANGED customer=" + customerId
                            + " fields=" + String.join(
                                    ",",
                                    changedFields.stream()
                                            .sorted()
                                            .toList()
                            );
        };
    }

    static String formatItems(List<LineItem> items) {
        return items.stream()
                .map(item -> item.sku() + "x" + item.quantity())
                .collect(Collectors.joining(","));
    }

    static void verify(
            String description,
            String expected,
            String actual
    ) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    description + "\nExpected: " + expected
                            + "\nActual: " + actual
            );
        }
    }

    public static void main(String[] args) {
        Customer customer = new Customer(
                "C-01",
                "An",
                "an@example.com"
        );

        Money total = new Money(
                new BigDecimal("125.50"),
                "USD"
        );

        List<DomainEvent> events = List.of(
                new OrderPlaced(
                        "O-100",
                        customer,
                        total,
                        List.of()
                ),
                new OrderPlaced(
                        "O-101",
                        customer,
                        total,
                        List.of(
                                new LineItem(
                                        "SKU-1",
                                        2,
                                        new Money(
                                                new BigDecimal("50.00"),
                                                "USD"
                                        )
                                ),
                                new LineItem(
                                        "SKU-2",
                                        1,
                                        new Money(
                                                new BigDecimal("25.50"),
                                                "USD"
                                        )
                                )
                        )
                ),
                new PaymentReceived(
                        "O-101",
                        new Money(new BigDecimal("0.00"), "USD"),
                        "P-900"
                ),
                new PaymentReceived(
                        "O-101",
                        total,
                        "P-901"
                ),
                new ShipmentSent(
                        "O-101",
                        "VN-TRACK-001",
                        new Address("Ho Chi Minh City", "VN")
                ),
                new CustomerChanged(
                        customer,
                        Set.of("email", "name")
                )
        );

        List<String> actual = events.stream()
                .map(Main::describe)
                .toList();

        List<String> expected = List.of(
                "ORDER_INVALID order=O-100 reason=no-items",
                "ORDER_PLACED order=O-101 customer=An(C-01)"
                        + " total=125.50 USD items=SKU-1x2,SKU-2x1",
                "PAYMENT_REJECTED order=O-101 payment=P-900"
                        + " amount=0.00 USD",
                "PAYMENT_RECEIVED order=O-101 payment=P-901"
                        + " amount=125.50 USD",
                "SHIPPED order=O-101 tracking=VN-TRACK-001"
                        + " destination=Ho Chi Minh City, VN",
                "CUSTOMER_CHANGED customer=C-01 fields=email,name"
        );

        verify("Event processing", expected.toString(), actual.toString());
        verify(
                "Null handling",
                "INVALID: null event",
                describe(null)
        );

        actual.forEach(System.out::println);
        System.out.println(describe(null));
        System.out.println("All checks passed.");
    }
}
```

Trong chương trình, `verify` ném `AssertionError` nếu kết quả thực tế khác kết quả mong đợi. Cách này giữ bài lab độc lập, không cần thêm test framework. Trong dự án thực tế, có thể chuyển các trường hợp kiểm tra sang JUnit Jupiter.

## 8. Biên dịch và chạy bằng Java 21

Mở terminal tại thư mục chứa `Main.java` và xác minh JDK:

```bash
java --version
javac --version
```

Biên dịch nhắm Java 21:

```bash
javac --release 21 Main.java
```

Chạy chương trình:

```bash
java Main
```

Không cần các tùy chọn `--enable-preview` hoặc `--source 21` vì record patterns và pattern matching for switch đã là tính năng chính thức trong Java 21.

Kết quả mong đợi:

```text
ORDER_INVALID order=O-100 reason=no-items
ORDER_PLACED order=O-101 customer=An(C-01) total=125.50 USD items=SKU-1x2,SKU-2x1
PAYMENT_REJECTED order=O-101 payment=P-900 amount=0.00 USD
PAYMENT_RECEIVED order=O-101 payment=P-901 amount=125.50 USD
SHIPPED order=O-101 tracking=VN-TRACK-001 destination=Ho Chi Minh City, VN
CUSTOMER_CHANGED customer=C-01 fields=email,name
INVALID: null event
All checks passed.
```

Nếu kết quả khác, kiểm tra dữ liệu đầu vào, thứ tự case, guard clause và logic định dạng. Nếu compiler báo lỗi cú pháp ở `when` hoặc record pattern, xác nhận cả `java` và `javac` đang dùng JDK 21 thay vì một JDK cũ hơn.

## 9. Hiểu tính exhaustive của switch

`DomainEvent` là sealed interface với bốn kiểu con được khai báo. Switch expression xử lý tất cả bốn kiểu này và có nhánh `null`, vì vậy không cần `default`.

Tính exhaustive giúp compiler kiểm tra cấu trúc xử lý. Thử thêm record mới:

```java
record OrderCancelled(String orderId, String reason)
        implements DomainEvent {
}
```

Sau đó thêm `OrderCancelled` vào danh sách `permits` của `DomainEvent`. Switch expression hiện tại sẽ không còn exhaustive và compiler yêu cầu bổ sung case xử lý kiểu mới.

Đây là lợi ích quan trọng khi xử lý một tập kiểu dữ liệu được kiểm soát: thay đổi mô hình dữ liệu có thể được phát hiện ở compile time thay vì chờ một event mới xuất hiện trong production.

Nếu dùng `default` để gom mọi kiểu chưa biết, compiler không còn buộc switch phải liệt kê từng subtype. Với sealed hierarchy nội bộ, nên cân nhắc giữ switch exhaustive để phát hiện thay đổi domain model.

## 10. Vai trò của case null

Pattern switch không tự động xem `null` là một kiểu dữ liệu hợp lệ để match vào type pattern. Nếu selector là null và switch không có `case null`, switch ném `NullPointerException`.

Trong bài lab, nhánh:

```java
case null -> "INVALID: null event";
```

xác định chính sách rõ ràng cho đầu vào null. Trong hệ thống thực tế, có thể chọn một trong các cách:

- Trả lỗi validation.
- Ném exception nghiệp vụ.
- Ghi nhận message không hợp lệ vào dead-letter flow.
- Bỏ qua nếu hợp đồng đầu vào cho phép và có metric theo dõi.

Không nên xử lý null một cách im lặng nếu nó biểu thị lỗi dữ liệu hoặc lỗi tích hợp giữa các service.

## 11. Hiểu guard clause when

Guard clause bổ sung điều kiện cho một pattern đã khớp:

```java
case PaymentReceived(
        String orderId,
        Money(var amount, var currency),
        String paymentId
) when amount.signum() <= 0 -> "PAYMENT_REJECTED";
```

Pattern xác định cấu trúc event. Guard kiểm tra giá trị amount sau khi đã phân rã. Nếu điều kiện đúng, case được chọn; nếu sai, switch tiếp tục xét case sau.

Một guard có thể dùng nhiều điều kiện:

```java
case OrderPlaced(
        String orderId,
        Customer(var customerId, var name, var email),
        Money(var amount, var currency),
        var items
) when items.isEmpty() || amount.signum() <= 0 ->
        "ORDER_INVALID";
```

Giữ guard dễ đọc và tránh nhồi toàn bộ quy tắc nghiệp vụ vào một biểu thức dài. Nếu điều kiện phức tạp, hãy chuyển thành method có tên rõ ràng, ví dụ `isValidOrder(amount, items)`.

## 12. Record pattern lồng nhau và null component

Record pattern kiểm tra cấu trúc record ở từng cấp. Nếu một component lồng nhau là null, nested record pattern không khớp.

Ví dụ:

```java
case OrderPlaced(
        String orderId,
        Customer(var customerId, var name, var email),
        Money(var amount, var currency),
        var items
) -> ...
```

Nếu component `customer` của `OrderPlaced` là null, pattern `Customer(...)` không khớp. Trong bài lab, compact constructor của `OrderPlaced` dùng `Objects.requireNonNull(customer)`, do đó invariant này được kiểm tra tại thời điểm tạo event.

Đối với dữ liệu đến từ JSON, database hoặc message broker, validation ở biên hệ thống vẫn cần thiết. Không giả định dữ liệu đã hợp lệ chỉ vì Java type khai báo component là một record khác.

Nếu domain cho phép component tùy chọn, có thể dùng `Optional` hoặc thiết kế một subtype/record thể hiện trạng thái thiếu rõ ràng. Khi đó, pattern matching cần phản ánh các trường hợp null hoặc absent theo hợp đồng dữ liệu.

## 13. Thử thách mở rộng

Sau khi chạy được chương trình cơ bản, thực hiện các bài tập sau.

### Bài tập A: Thêm OrderCancelled

Tạo record:

```java
record OrderCancelled(
        String orderId,
        String reason
) implements DomainEvent {
}
```

Yêu cầu:

1. Thêm kiểu này vào `permits`.
2. Bổ sung validation cho orderId và reason.
3. Thêm case trong switch.
4. Thêm một event mẫu.
5. Cập nhật expected output và chạy lại.

Mục tiêu là quan sát compiler phát hiện switch expression chưa exhaustive khi sealed hierarchy thay đổi.

### Bài tập B: Thêm guard cho đơn hàng giá trị cao

Với `OrderPlaced`, thêm một case có guard:

```java
when amount.compareTo(new BigDecimal("1000.00")) >= 0
```

Trả về trạng thái `HIGH_VALUE_ORDER`. Đặt case này trước case `OrderPlaced` tổng quát và sau case xử lý đơn không có mặt hàng, để đơn rỗng vẫn được báo lỗi đúng.

### Bài tập C: Tính tổng giá trị mặt hàng

Viết method tính tổng từ `LineItem`:

```java
static BigDecimal calculateItemsTotal(List<LineItem> items) {
    return items.stream()
            .map(item -> item.unitPrice().amount()
                    .multiply(BigDecimal.valueOf(item.quantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);
}
```

So sánh tổng tính từ danh sách mặt hàng với `OrderPlaced.total()`. Xác định rõ chính sách làm tròn và currency trước khi dùng trong nghiệp vụ thật.

### Bài tập D: Tách formatter khỏi dispatcher

Chuyển phần định dạng từng loại event sang các method riêng như `describeOrder`, `describePayment` và `describeShipment`. Giữ switch làm nhiệm vụ dispatch và phân rã dữ liệu.

Mục tiêu là cân bằng giữa lợi ích của pattern matching và khả năng bảo trì khi logic từng event phát triển lớn.

## 14. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `instanceof` và ép kiểu thủ công ở mọi nhánh | Không tận dụng pattern switch và record pattern | Dùng switch pattern để dispatch và destructure |
| Đặt case tổng quát trước case có guard | Case tổng quát có thể bắt mất tình huống cụ thể hoặc gây pattern dominance error | Đặt case cụ thể trước |
| Quên xử lý subtype mới của sealed interface | Switch expression không còn exhaustive | Bổ sung case và kiểm tra compile |
| Nghĩ `default` luôn cần thiết | Sealed hierarchy có thể được xử lý exhaustively | Liệt kê các subtype khi muốn compiler kiểm tra |
| Nghĩ type pattern tự khớp null | Type pattern không khớp null | Thêm `case null` hoặc validate đầu vào |
| Giả định nested record pattern khớp component null | Nested pattern thất bại nếu record component là null | Validate invariant hoặc xử lý null riêng |
| Để collection mutable bên trong record | Record chỉ bất biến nông | Sao chép collection bằng `List.copyOf`/`Set.copyOf` |
| Dùng guard quá dài | Quy tắc nghiệp vụ khó đọc và khó kiểm thử | Chuyển điều kiện phức tạp sang method có tên |
| Bật preview flag không cần thiết | Nhầm tính năng Java 21 final với tính năng preview khác | Dùng JDK 21 và `--release 21` |

## 15. Tiêu chí hoàn thành lab

Bài thực hành được xem là hoàn thành khi:

- [ ] Domain model có sealed interface và các record event.
- [ ] Record constructor xác thực dữ liệu bắt buộc.
- [ ] Collection trong event được sao chép phòng vệ.
- [ ] Switch expression dùng nested record patterns.
- [ ] Có ít nhất hai guard clause `when`.
- [ ] Có chính sách rõ ràng cho `null`.
- [ ] Switch xử lý exhaustive toàn bộ permitted event types.
- [ ] Chương trình biên dịch bằng `javac --release 21`.
- [ ] Output khớp dữ liệu mong đợi.
- [ ] Đã thử thêm subtype để quan sát compiler phát hiện case còn thiếu.

## 16. Kết luận thực hành

Record pattern lồng nhau giúp biểu diễn trực tiếp cấu trúc dữ liệu của domain, còn pattern matching for switch giúp chọn hành vi dựa trên kiểu và nội dung của record. Kết hợp sealed interface, các tính năng này tạo nên bộ xử lý dữ liệu có cấu trúc rõ ràng và được compiler hỗ trợ kiểm tra tính đầy đủ.

Trong Java 21, record patterns và pattern matching for switch đã là tính năng chính thức. Có thể dùng chúng trong code production mà không cần preview flag. Hãy giữ record model có invariant rõ ràng, đặt guard cụ thể trước case tổng quát, xử lý null có chủ đích và tận dụng sealed hierarchy để compiler phát hiện khi mô hình event thay đổi.

## Tài liệu tham khảo

- [Oracle Java SE 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns (Final)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Final)](https://openjdk.org/jeps/441)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
