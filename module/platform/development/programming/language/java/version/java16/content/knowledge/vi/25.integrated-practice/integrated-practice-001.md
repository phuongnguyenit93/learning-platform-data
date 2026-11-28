# Xây mô hình đơn hàng bằng record với validation và defensive copy

> **Chương:** Thực hành tổng hợp  
> **Học phần:** `JAVA_VERSION_JAVA16` — áp dụng record trong mô hình dữ liệu Java hiện đại. Bài thực hành xây dựng đơn hàng gồm tiền tệ, dòng hàng và trạng thái; dùng compact constructor để bảo vệ invariant, defensive copy để ngăn thay đổi collection từ bên ngoài và các phương thức tạo giá trị mới theo value semantics.

## Mục tiêu thực hành

Sau bài này, bạn có thể:

- Chọn record cho các kiểu dữ liệu mô tả giá trị và dữ liệu bất biến.
- Thiết kế các record nhỏ có trách nhiệm rõ ràng: `Money`, `OrderLine` và `Order`.
- Dùng compact canonical constructor để kiểm tra và chuẩn hóa dữ liệu đầu vào.
- Bảo vệ invariant của đơn hàng như số lượng dương, danh sách dòng hàng không rỗng và tiền tệ nhất quán.
- Dùng `List.copyOf` và `Map.copyOf` để tạo snapshot không thể sửa đổi từ bên ngoài.
- Hiểu giới hạn của defensive copy nông và vai trò của immutable element.
- Tính subtotal, total và tạo trạng thái đơn hàng mới mà không sửa object hiện tại.
- Viết unit test cho validation, defensive copy và phép tính.
- Nhận diện các trường hợp record không tự tạo ra deep immutability.

## 1. Bài toán: mô hình hóa một đơn hàng

Một hệ thống bán hàng cần biểu diễn đơn hàng gồm mã đơn, khách hàng, thời điểm tạo, danh sách dòng hàng, ghi chú và trạng thái. Mỗi dòng hàng có mã sản phẩm, mô tả, số lượng và đơn giá.

Ta muốn mô hình có các quy tắc:

1. Đơn hàng phải có mã và khách hàng hợp lệ.
2. Đơn hàng phải có ít nhất một dòng hàng.
3. Số lượng của mỗi dòng hàng phải lớn hơn 0.
4. Đơn giá không được âm và phải có loại tiền tệ.
5. Tất cả dòng hàng trong cùng đơn phải dùng cùng tiền tệ.
6. Danh sách dòng hàng và bản đồ ghi chú không được thay đổi thông qua tham chiếu đầu vào hoặc accessor.
7. Tổng tiền phải được tính từ các dòng hàng hiện tại.
8. Khi đổi trạng thái, tạo một đơn hàng mới với cùng dữ liệu còn lại.

Đây là bài toán phù hợp với record vì các kiểu dữ liệu chủ yếu mô tả giá trị. Record cung cấp constructor, accessor, `equals`, `hashCode` và `toString` dựa trên component, giúp giảm mã lặp. Từ Java 16, record là tính năng ngôn ngữ đã được hoàn thiện và tiếp tục dùng được trong Java hiện đại.

## 2. Chọn record cho value model

Record phù hợp khi một object được xác định chủ yếu bởi dữ liệu component và không cần identity hay trạng thái thay đổi sau khi tạo.

Trong bài này:

| Kiểu | Dữ liệu | Trách nhiệm |
| --- | --- | --- |
| `Money` | Số tiền và tiền tệ | Bảo vệ giá trị tiền hợp lệ, cộng và nhân số tiền |
| `OrderLine` | Sản phẩm, số lượng, đơn giá | Kiểm tra dòng hàng và tính subtotal |
| `Order` | Mã đơn, khách hàng, thời điểm, dòng hàng, ghi chú, trạng thái | Bảo vệ invariant của toàn đơn và tính total |
| `OrderStatus` | Trạng thái đơn | Tập giá trị trạng thái hữu hạn |

Record không thay thế mọi class. Nếu một đối tượng cần thay đổi trạng thái nội bộ, quản lý tài nguyên, identity riêng hoặc kế thừa từ class khác, class thông thường có thể phù hợp hơn.

Record là `final`, không thể kế thừa từ class khác và các component tương ứng với field `private final`. Tuy nhiên, `final` chỉ cố định tham chiếu component; nó không tự làm object được tham chiếu trở nên bất biến.

## 3. Compact canonical constructor dùng để bảo vệ invariant

Record có canonical constructor nhận các component theo đúng thứ tự khai báo. Với compact constructor, ta không cần viết lại danh sách tham số và không cần gán từng field:

```java
record ProductCode(String value) {
    ProductCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Product code must not be blank"
            );
        }

        value = value.trim();
    }
}
```

Trong compact constructor:

- Các tên component được dùng như tham số constructor.
- Có thể kiểm tra, từ chối hoặc chuẩn hóa tham số.
- Có thể gán lại tham số, như `value = value.trim()`.
- Sau khi phần thân constructor kết thúc bình thường, Java tự gán các tham số cuối cùng vào field tương ứng.
- Không viết `this.value = value` trong compact constructor.

Nếu validation thất bại, constructor ném exception và object không được tạo. Vì vậy, các phương thức khác có thể dựa vào invariant đã được thiết lập khi object tồn tại.

Không nên đặt validation chỉ trong setter hoặc ở tầng UI. Dữ liệu có thể được tạo từ API, message queue, database mapper hoặc test. Constructor là ranh giới phù hợp để bảo vệ invariant của value object.

## 4. Xây dựng record Money

`Money` giữ một `BigDecimal` và `Currency`. Cả hai đều là kiểu bất biến, phù hợp làm component của record.

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

record Money(BigDecimal amount, Currency currency) {

    Money {
        amount = Objects.requireNonNull(amount, "amount");
        currency = Objects.requireNonNull(currency, "currency");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "Money amount must not be negative"
            );
        }
    }

    Money add(Money other) {
        Objects.requireNonNull(other, "other");

        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                    "Cannot add different currencies"
            );
        }

        return new Money(amount.add(other.amount), currency);
    }

    Money multiply(int factor) {
        if (factor < 0) {
            throw new IllegalArgumentException(
                    "Factor must not be negative"
            );
        }

        return new Money(
                amount.multiply(BigDecimal.valueOf(factor)),
                currency
        );
    }
}
```

Các quyết định thiết kế:

- `amount` không được null hoặc âm.
- `currency` không được null.
- Không cộng hai giá trị có tiền tệ khác nhau.
- Phép cộng và phép nhân trả về một `Money` mới; không sửa object hiện tại.
- Không tự động làm tròn hoặc đổi scale trong constructor.

`BigDecimal` có quy tắc `equals` xét cả giá trị và scale. Ví dụ `new BigDecimal("10.0")` không bằng `new BigDecimal("10.00")` theo `equals`, dù `compareTo` trả về 0. Hệ thống tiền tệ cần quyết định rõ quy tắc scale và làm tròn theo nghiệp vụ; không nên tự ý chuẩn hóa nếu chưa xác định chính sách.

## 5. Xây dựng record OrderLine

Một dòng hàng cần mã sản phẩm, mô tả, số lượng và đơn giá.

```java
import java.util.Objects;

record OrderLine(
        String productCode,
        String description,
        int quantity,
        Money unitPrice
) {

    OrderLine {
        if (productCode == null || productCode.isBlank()) {
            throw new IllegalArgumentException(
                    "Product code must not be blank"
            );
        }

        productCode = productCode.trim();

        if (description == null || description.isBlank()) {
            throw new IllegalArgumentException(
                    "Description must not be blank"
            );
        }

        description = description.trim();

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be greater than zero"
            );
        }

        unitPrice = Objects.requireNonNull(
                unitPrice,
                "unitPrice"
        );
    }

    Money subtotal() {
        return unitPrice.multiply(quantity);
    }
}
```

`OrderLine` kiểm tra dữ liệu ngay khi được tạo. `subtotal()` chỉ thực hiện phép nhân và trả về một `Money` mới.

Vì `String` và `Money` là immutable, record này không cần defensive copy cho các component. Nếu component là một object mutable, cần có chiến lược bảo vệ riêng.

## 6. Xây dựng record Order với defensive copy

`Order` chứa hai collection: `List<OrderLine>` và `Map<String, String>`. Nếu chỉ gán tham chiếu đầu vào, code gọi constructor vẫn có thể sửa dữ liệu đơn hàng sau khi tạo object:

```java
List<OrderLine> lines = new ArrayList<>();
Order order = new Order(/* ... */, lines, /* ... */);

lines.clear(); // Có thể làm thay đổi dữ liệu bên trong order
```

Để ngăn điều này, tạo snapshot không thể sửa đổi trong compact constructor bằng `List.copyOf` và `Map.copyOf`.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Currency;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

record Order(
        UUID id,
        String customerId,
        Instant createdAt,
        List<OrderLine> lines,
        Map<String, String> notes,
        OrderStatus status
) {

    Order {
        id = Objects.requireNonNull(id, "id");

        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer ID must not be blank"
            );
        }
        customerId = customerId.trim();

        createdAt = Objects.requireNonNull(
                createdAt,
                "createdAt"
        );

        lines = List.copyOf(
                new ArrayList<>(
                        Objects.requireNonNull(lines, "lines")
                )
        );

        if (lines.isEmpty()) {
            throw new IllegalArgumentException(
                    "Order must contain at least one line"
            );
        }

        notes = Map.copyOf(
                new HashMap<>(
                        Objects.requireNonNull(notes, "notes")
                )
        );

        status = Objects.requireNonNull(status, "status");

        Currency orderCurrency =
                lines.get(0).unitPrice().currency();

        for (OrderLine line : lines) {
            if (!orderCurrency.equals(
                    line.unitPrice().currency()
            )) {
                throw new IllegalArgumentException(
                        "All order lines must use the same currency"
                );
            }
        }
    }

    Money total() {
        BigDecimal amount = lines.stream()
                .map(OrderLine::subtotal)
                .map(Money::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        Currency currency =
                lines.get(0).unitPrice().currency();

        return new Money(amount, currency);
    }

    Order withStatus(OrderStatus newStatus) {
        return new Order(
                id,
                customerId,
                createdAt,
                lines,
                notes,
                newStatus
        );
    }
}
```

Trách nhiệm của constructor:

1. Kiểm tra ID, khách hàng, thời điểm và trạng thái.
2. Tạo bản sao độc lập, không thể sửa đổi của danh sách dòng hàng.
3. Từ chối đơn hàng rỗng.
4. Tạo bản sao độc lập, không thể sửa đổi của map ghi chú.
5. Kiểm tra mọi dòng hàng dùng cùng tiền tệ.

`new ArrayList<>(lines)` và `new HashMap<>(notes)` tạo bản sao từ collection nguồn; `List.copyOf` và `Map.copyOf` tạo collection không thể sửa đổi để lưu trong record. Cách kết hợp này cũng tránh phụ thuộc vào một collection nguồn vốn chỉ là unmodifiable view của cấu trúc mutable khác.

Các factory method `List.copyOf` và `Map.copyOf` có từ trước Java 16 và vẫn là API phù hợp trong Java hiện đại. Chúng từ chối phần tử null hoặc key/value null bằng `NullPointerException`.

`Map.copyOf` không cam kết giữ thứ tự iteration của map nguồn. Trong mô hình này, ghi chú không cần thứ tự. Nếu nghiệp vụ cần giữ insertion order, hãy copy vào `LinkedHashMap` rồi bọc bản copy bằng `Collections.unmodifiableMap`.

Các component `OrderLine`, `String`, `UUID`, `Instant` và `Money` đều bất biến trong mô hình này. Vì vậy, defensive copy nông của collection là đủ cho cấu trúc đã chọn.

## 7. Tại sao cần defensive copy ở constructor?

Nếu chỉ khai báo component kiểu `List<OrderLine>`, record giữ tham chiếu đến list được truyền vào. `final` không ngăn code bên ngoài sửa nội dung list.

Ví dụ không an toàn:

```java
record UnsafeOrder(List<OrderLine> lines) {
    UnsafeOrder {
        Objects.requireNonNull(lines);
    }
}
```

Code gọi có thể sửa list sau khi tạo:

```java
List<OrderLine> source = new ArrayList<>();
UnsafeOrder order = new UnsafeOrder(source);

source.add(newLine); // Nội dung order.lines() thay đổi theo
```

Bản an toàn tạo snapshot:

```java
record SafeOrder(List<OrderLine> lines) {
    SafeOrder {
        lines = List.copyOf(new ArrayList<>(lines));
    }
}
```

Sau khi tạo `SafeOrder`, việc thêm hoặc xóa trên `source` không làm thay đổi collection được lưu trong record. Accessor `lines()` cũng trả về collection không thể sửa đổi.

Defensive copy ở constructor và collection không thể sửa đổi giải quyết hai đường thay đổi khác nhau:

- Copy ở constructor ngăn caller thay đổi object thông qua collection nguồn.
- Collection không thể sửa đổi ngăn caller thay đổi object qua accessor.

Nếu chỉ copy bằng `new ArrayList<>(lines)`, caller không còn ảnh hưởng qua list nguồn nhưng vẫn có thể gọi `order.lines().clear()`. Nếu chỉ bọc list nguồn bằng `Collections.unmodifiableList(lines)`, caller vẫn có thể sửa list gốc. Kết hợp copy độc lập với immutable collection giải quyết cả hai cho collection được lưu.

## 8. Defensive copy là nông, không tự tạo deep immutability

`List.copyOf` chỉ bảo vệ cấu trúc collection. Nó không clone từng phần tử.

Ví dụ:

```java
record Basket(List<StringBuilder> items) {
    Basket {
        items = List.copyOf(new ArrayList<>(items));
    }
}
```

Caller không thể thêm hoặc xóa phần tử trong `items()`, nhưng vẫn có thể sửa một `StringBuilder` đã nằm trong list:

```java
StringBuilder label = new StringBuilder("Book");
Basket basket = new Basket(List.of(label));

label.append(" revised");
// basket.items().get(0) cũng quan sát thấy thay đổi
```

Có ba cách xử lý:

- Ưu tiên component là kiểu immutable như `String`, `BigDecimal`, `Instant`, enum hoặc record chỉ chứa immutable component.
- Nếu cần nhận kiểu mutable, copy từng phần tử sang representation immutable trong constructor.
- Nếu phải lưu kiểu mutable, copy khi nhận và khi trả qua accessor; cân nhắc cả `equals`/`hashCode` theo value semantics.

Ví dụ record chứa mảng byte:

```java
record Payload(byte[] content) {

    Payload {
        content = Objects.requireNonNull(content).clone();
    }

    @Override
    public byte[] content() {
        return content.clone();
    }
}
```

Constructor clone mảng đầu vào; accessor trả về bản clone để caller không sửa được trạng thái nội bộ. Tuy nhiên, `equals` và `hashCode` mặc định của record không so sánh nội dung mảng theo giá trị mà dựa trên semantics của array object. Nếu cần value equality cho mảng, phải triển khai `equals` và `hashCode` phù hợp hoặc dùng kiểu biểu diễn khác.

Với order model, chọn `List<OrderLine>` và `Map<String, String>` cùng các phần tử immutable giúp tránh phải viết deep-copy logic phức tạp.

## 9. Tạo trạng thái mới thay vì sửa record

Record không cung cấp setter và component là final. Khi cần chuyển đơn hàng từ `DRAFT` sang `CONFIRMED`, phương thức `withStatus` tạo một record mới:

```java
Order confirmed = draftOrder.withStatus(OrderStatus.CONFIRMED);
```

Hai object có cùng ID, khách hàng, thời điểm, dòng hàng và ghi chú nhưng trạng thái khác nhau. `draftOrder` vẫn giữ trạng thái ban đầu.

Enum:

```java
enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
```

Đây là cách biểu diễn thay đổi theo value semantics. Nếu hệ thống cần kiểm soát chuyển trạng thái, có thể đưa quy tắc vào phương thức domain:

```java
Order confirm() {
    if (status != OrderStatus.DRAFT) {
        throw new IllegalStateException(
                "Only a draft order can be confirmed"
        );
    }

    return withStatus(OrderStatus.CONFIRMED);
}
```

Trong hệ thống lớn, có thể mở rộng thành các phương thức `cancel()`, `ship()` hoặc `complete()` với điều kiện chuyển trạng thái rõ ràng. Không để code bên ngoài tự tạo trạng thái không hợp lệ.

## 10. Chương trình hoàn chỉnh

Đặt các khai báo sau trong file `OrderDemo.java`. Chỉ `OrderDemo` là public; các record và enum còn lại là top-level package-private để ví dụ có thể biên dịch trong một file.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Currency;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

public class OrderDemo {

    public static void main(String[] args) {
        Currency vnd = Currency.getInstance("VND");

        List<OrderLine> draftLines = new ArrayList<>();
        draftLines.add(new OrderLine(
                "BK-101",
                "Java Programming",
                2,
                new Money(new BigDecimal("150000"), vnd)
        ));
        draftLines.add(new OrderLine(
                "BK-205",
                "Clean Code",
                1,
                new Money(new BigDecimal("250000"), vnd)
        ));

        Map<String, String> draftNotes = new HashMap<>();
        draftNotes.put("channel", "web");
        draftNotes.put("promotion", "WELCOME");

        Order draftOrder = new Order(
                UUID.randomUUID(),
                "CUS-1042",
                Instant.now(),
                draftLines,
                draftNotes,
                OrderStatus.DRAFT
        );

        // Thay đổi collection nguồn sau khi tạo order.
        draftLines.clear();
        draftNotes.put("channel", "modified");

        System.out.println(
                "Line count: " + draftOrder.lines().size()
        );
        System.out.println(
                "Channel: " + draftOrder.notes().get("channel")
        );
        System.out.println(
                "Total: " + draftOrder.total().amount()
                        + " " + draftOrder.total().currency()
        );

        // Accessor trả về collection không thể sửa đổi.
        try {
            draftOrder.lines().clear();
        } catch (UnsupportedOperationException expected) {
            System.out.println("Order lines are unmodifiable");
        }

        Order confirmedOrder = draftOrder.confirm();

        System.out.println(
                "Draft status: " + draftOrder.status()
        );
        System.out.println(
                "Confirmed status: " + confirmedOrder.status()
        );
    }
}

record Money(BigDecimal amount, Currency currency) {

    Money {
        amount = Objects.requireNonNull(amount, "amount");
        currency = Objects.requireNonNull(currency, "currency");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "Money amount must not be negative"
            );
        }
    }

    Money add(Money other) {
        Objects.requireNonNull(other, "other");

        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                    "Cannot add different currencies"
            );
        }

        return new Money(amount.add(other.amount), currency);
    }

    Money multiply(int factor) {
        if (factor < 0) {
            throw new IllegalArgumentException(
                    "Factor must not be negative"
            );
        }

        return new Money(
                amount.multiply(BigDecimal.valueOf(factor)),
                currency
        );
    }
}

record OrderLine(
        String productCode,
        String description,
        int quantity,
        Money unitPrice
) {

    OrderLine {
        if (productCode == null || productCode.isBlank()) {
            throw new IllegalArgumentException(
                    "Product code must not be blank"
            );
        }
        productCode = productCode.trim();

        if (description == null || description.isBlank()) {
            throw new IllegalArgumentException(
                    "Description must not be blank"
            );
        }
        description = description.trim();

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be greater than zero"
            );
        }

        unitPrice = Objects.requireNonNull(
                unitPrice,
                "unitPrice"
        );
    }

    Money subtotal() {
        return unitPrice.multiply(quantity);
    }
}

record Order(
        UUID id,
        String customerId,
        Instant createdAt,
        List<OrderLine> lines,
        Map<String, String> notes,
        OrderStatus status
) {

    Order {
        id = Objects.requireNonNull(id, "id");

        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer ID must not be blank"
            );
        }
        customerId = customerId.trim();

        createdAt = Objects.requireNonNull(
                createdAt,
                "createdAt"
        );

        lines = List.copyOf(
                new ArrayList<>(
                        Objects.requireNonNull(lines, "lines")
                )
        );

        if (lines.isEmpty()) {
            throw new IllegalArgumentException(
                    "Order must contain at least one line"
            );
        }

        notes = Map.copyOf(
                new HashMap<>(
                        Objects.requireNonNull(notes, "notes")
                )
        );

        status = Objects.requireNonNull(status, "status");

        Currency orderCurrency =
                lines.get(0).unitPrice().currency();

        for (OrderLine line : lines) {
            if (!orderCurrency.equals(
                    line.unitPrice().currency()
            )) {
                throw new IllegalArgumentException(
                        "All order lines must use the same currency"
                );
            }
        }
    }

    Money total() {
        BigDecimal amount = lines.stream()
                .map(OrderLine::subtotal)
                .map(Money::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        Currency currency =
                lines.get(0).unitPrice().currency();

        return new Money(amount, currency);
    }

    Order withStatus(OrderStatus newStatus) {
        return new Order(
                id,
                customerId,
                createdAt,
                lines,
                notes,
                newStatus
        );
    }

    Order confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Only a draft order can be confirmed"
            );
        }

        return withStatus(OrderStatus.CONFIRMED);
    }
}

enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
```

## 11. Biên dịch và chạy

Record đã là tính năng chính thức từ Java 16. Có thể biên dịch ví dụ với JDK 16 trở lên:

```bash
mkdir -p out
javac --release 16 -d out OrderDemo.java
java -cp out OrderDemo
```

`--release 16` yêu cầu compiler kiểm tra source/API theo Java 16. Nếu dùng JDK 16 trực tiếp, có thể bỏ `--release 16`.

Kết quả minh họa:

```text
Line count: 2
Channel: web
Total: 550000 VND
Order lines are unmodifiable
Draft status: DRAFT
Confirmed status: CONFIRMED
```

Hai dòng hàng có subtotal lần lượt là 300000 VND và 250000 VND. Tổng đơn là 550000 VND. Sau khi xóa `draftLines` và sửa `draftNotes`, snapshot trong `draftOrder` vẫn giữ dữ liệu ban đầu.

## 12. Viết unit test cho validation và defensive copy

Ví dụ dưới đây dùng JUnit Jupiter. Test tập trung vào hợp đồng của domain model thay vì kiểm tra implementation detail.

Đặt `OrderTest.java` trong cùng package với các record của mô hình. Ví dụ chính ở trên dùng package mặc định; dự án thực tế nên khai báo package rõ ràng cho cả source và test.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Currency;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.Test;

class OrderTest {

    private static final Currency VND =
            Currency.getInstance("VND");

    private static OrderLine line(
            String code,
            int quantity,
            String amount
    ) {
        return new OrderLine(
                code,
                code + " description",
                quantity,
                new Money(new BigDecimal(amount), VND)
        );
    }

    private static Order order(
            List<OrderLine> lines,
            Map<String, String> notes
    ) {
        return new Order(
                UUID.randomUUID(),
                "CUS-42",
                Instant.parse("2026-01-10T08:00:00Z"),
                lines,
                notes,
                OrderStatus.DRAFT
        );
    }

    @Test
    void copiesInputCollections() {
        List<OrderLine> sourceLines = new ArrayList<>();
        sourceLines.add(line("BK-1", 2, "100000"));

        Map<String, String> sourceNotes = new HashMap<>();
        sourceNotes.put("channel", "web");

        Order order = order(sourceLines, sourceNotes);

        sourceLines.clear();
        sourceNotes.put("channel", "changed");

        assertEquals(1, order.lines().size());
        assertEquals("web", order.notes().get("channel"));
    }

    @Test
    void exposesUnmodifiableCollections() {
        Order order = order(
                List.of(line("BK-1", 1, "100000")),
                Map.of("channel", "web")
        );

        assertThrows(
                UnsupportedOperationException.class,
                () -> order.lines().clear()
        );

        assertThrows(
                UnsupportedOperationException.class,
                () -> order.notes().put("source", "mobile")
        );
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(
                IllegalArgumentException.class,
                () -> line("BK-1", 0, "100000")
        );
    }

    @Test
    void rejectsEmptyOrder() {
        assertThrows(
                IllegalArgumentException.class,
                () -> order(List.of(), Map.of())
        );
    }

    @Test
    void rejectsMixedCurrencies() {
        OrderLine vndLine = line("BK-1", 1, "100000");

        OrderLine usdLine = new OrderLine(
                "BK-2",
                "USD item",
                1,
                new Money(
                        new BigDecimal("10.00"),
                        Currency.getInstance("USD")
                )
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> order(
                        List.of(vndLine, usdLine),
                        Map.of()
                )
        );
    }

    @Test
    void calculatesOrderTotal() {
        Order order = order(
                List.of(
                        line("BK-1", 2, "100000"),
                        line("BK-2", 1, "250000")
                ),
                Map.of()
        );

        assertEquals(
                new BigDecimal("450000"),
                order.total().amount()
        );

        assertEquals(VND, order.total().currency());
    }

    @Test
    void confirmationCreatesNewOrder() {
        Order draft = order(
                List.of(line("BK-1", 1, "100000")),
                Map.of()
        );

        Order confirmed = draft.confirm();

        assertEquals(OrderStatus.DRAFT, draft.status());
        assertEquals(OrderStatus.CONFIRMED, confirmed.status());
        assertEquals(draft.id(), confirmed.id());
    }
}
```

Các test xác nhận:

- Thay đổi collection nguồn không ảnh hưởng order đã tạo.
- Accessor không cho phép sửa collection.
- Constructor từ chối quantity không hợp lệ và order rỗng.
- Constructor từ chối các dòng hàng dùng khác tiền tệ.
- Tổng tiền được tính đúng.
- Chuyển trạng thái tạo object mới và giữ nguyên object cũ.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ dùng `final List` mà không copy | Caller vẫn sửa được nội dung list | Tạo bản copy rồi dùng `List.copyOf` |
| Chỉ dùng `Collections.unmodifiableList(source)` | Caller vẫn sửa list nguồn | Copy trước rồi mới công bố collection |
| Nghĩ record tự làm mọi component immutable | Component mutable vẫn thay đổi được | Chọn immutable type hoặc defensive copy sâu |
| Chỉ copy ở constructor | Accessor có thể để lộ mutable collection | Dùng immutable collection hoặc copy khi trả về |
| Chỉ validate ở UI | API hoặc code nội bộ có thể tạo dữ liệu sai | Đặt invariant trong constructor |
| Cho phép số lượng bằng 0 | Dòng hàng không có ý nghĩa nghiệp vụ | Kiểm tra `quantity > 0` |
| Cộng tiền khác currency | Tổng tiền sai đơn vị | Kiểm tra currency trước phép cộng |
| Dùng `double` cho tiền | Sai số biểu diễn số thực | Dùng `BigDecimal` với chính sách scale rõ ràng |
| Dùng `BigDecimal.equals` để so số học | Scale khác nhau làm equality khác nhau | Dùng `compareTo` khi cần so sánh giá trị số |
| Cố thay đổi record sau khi tạo | Đi ngược value semantics | Tạo record mới qua phương thức domain |

## 14. Bài tập tự luyện

### Bài 1: Tạo kiểu định danh riêng

Tạo record `OrderId(UUID value)` và kiểm tra `value` không null. Cập nhật `Order` để dùng `OrderId` thay cho `UUID` trực tiếp.

**Kết quả mong đợi:** Không thể vô tình truyền `CustomerId` hoặc một UUID không đúng ngữ cảnh vào constructor của `Order` nếu hệ thống định nghĩa các kiểu ID riêng.

### Bài 2: Thêm ghi chú mà không sửa order cũ

Viết phương thức `withNote(String key, String value)` trả về một `Order` mới. Phương thức phải từ chối key rỗng, copy map ghi chú hiện tại, thêm cặp key/value vào bản copy và gọi constructor để tạo order mới.

**Kết quả mong đợi:** Order mới có ghi chú bổ sung; `notes()` của order ban đầu không đổi. Bản copy vẫn phải đi qua constructor để invariant được kiểm tra tập trung.

### Bài 3: Kiểm tra quy tắc giảm giá

Thêm component `discount` kiểu `Money` vào order. Bảo đảm discount cùng currency với total và không lớn hơn tổng tiền hàng.

**Kết quả mong đợi:** Constructor từ chối discount âm, khác currency hoặc lớn hơn subtotal. Bổ sung test cho cả trường hợp hợp lệ và không hợp lệ.

### Bài 4: Chứng minh defensive copy nông

Tạo một record thử nghiệm chứa `List<StringBuilder>`, copy list trong constructor rồi thay đổi một `StringBuilder` từ bên ngoài.

**Kết quả mong đợi:** Không thể thêm/xóa phần tử qua list accessor, nhưng nội dung `StringBuilder` vẫn đổi. Sau đó thay component bằng `List<String>` hoặc copy từng phần tử sang kiểu immutable để loại bỏ đường thay đổi gián tiếp.

### Bài 5: Kiểm thử chuyển trạng thái

Viết phương thức `cancel()` chỉ cho phép hủy order ở trạng thái `DRAFT` hoặc `CONFIRMED`. Các trạng thái còn lại phải ném `IllegalStateException`.

**Kết quả mong đợi:** Phương thức trả về order mới ở trạng thái `CANCELLED`; order ban đầu không thay đổi. Có test cho từng trạng thái đầu vào.

## 15. Mở rộng bài thực hành

Sau khi hoàn thành mô hình cơ bản, có thể mở rộng theo các yêu cầu nghiệp vụ:

- Thêm `discount` dưới dạng `Money`, đồng thời xác thực discount không vượt quá subtotal.
- Thêm `shippingFee` và quy tắc miễn phí vận chuyển.
- Thêm `OrderStatus` transition như `confirm`, `cancel`, `ship` và `complete`.
- Thêm `OrderId` hoặc `CustomerId` thành record riêng để tránh truyền nhầm String.
- Thêm phương thức `withNotes` trả về order mới khi cập nhật ghi chú.
- Thêm kiểm tra trùng `productCode` nếu nghiệp vụ yêu cầu gộp cùng sản phẩm thành một dòng.
- Xác định chính sách scale và rounding theo currency, thay vì áp dụng một quy tắc làm tròn chung.

Nếu hệ thống cần lưu lịch sử thay đổi, hãy xem mỗi lần cập nhật là một giá trị order mới hoặc một domain event. Record không tự tạo event sourcing, nhưng cấu trúc bất biến giúp lưu snapshot và so sánh trạng thái rõ ràng.

## 16. Checklist review mô hình

Trước khi dùng record làm domain model, kiểm tra:

- [ ] Component có thể biểu diễn bằng dữ liệu giá trị và không cần identity mutable không?
- [ ] Mọi component bắt buộc đã được kiểm tra null?
- [ ] Chuỗi đã được kiểm tra blank và chuẩn hóa nếu nghiệp vụ yêu cầu?
- [ ] Số lượng, số tiền và trạng thái có invariant rõ ràng?
- [ ] Collection đầu vào đã được copy?
- [ ] Accessor có để lộ mutable collection không?
- [ ] Phần tử trong collection có immutable không?
- [ ] Các kiểu mutable như array, `Date` hoặc custom object có defensive copy hai chiều không?
- [ ] Quy tắc currency, scale và rounding có rõ ràng không?
- [ ] Phương thức cập nhật trả về object mới và không làm thay đổi object cũ?
- [ ] Unit test đã kiểm tra cả input mutation và accessor mutation chưa?

## Ghi nhớ

Record phù hợp để biểu diễn value model như `Money`, `OrderLine` và `Order`. Compact canonical constructor là nơi bảo vệ invariant ngay khi tạo object. `List.copyOf` và `Map.copyOf` tạo snapshot collection không thể sửa đổi, còn immutable element giúp mô hình không bị thay đổi gián tiếp. Defensive copy của collection là copy nông; component mutable cần được copy sâu hoặc thay bằng kiểu immutable. Khi thay đổi trạng thái, tạo record mới qua phương thức domain như `confirm()` để giữ object cũ nguyên vẹn. Kiểm thử cả validation, thay đổi collection nguồn, accessor và phép tính để xác nhận hợp đồng của mô hình.

## Tài liệu tham khảo

- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [Java Language Specification — Java SE 16, Records](https://docs.oracle.com/javase/specs/jls/se16/html/jls-8.html#jls-8.10).
- [Java API — List.copyOf](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).
- [Java API — Map.copyOf](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)).
- [Java API — BigDecimal](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html).
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/).
