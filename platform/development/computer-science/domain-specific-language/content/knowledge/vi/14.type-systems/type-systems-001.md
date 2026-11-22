# Kiểu nguyên thủy và kiểu miền

Trong hệ kiểu của một ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL), kiểu dữ liệu cho biết một giá trị thuộc loại nào, có thể tham gia những phép toán nào và được dùng ở đâu. **Kiểu nguyên thủy (primitive type)** biểu diễn những giá trị cơ bản như số nguyên, số thực và giá trị đúng/sai. **Kiểu miền (domain type)** biểu diễn một khái niệm có ý nghĩa trong lĩnh vực mà DSL phục vụ, chẳng hạn mã khách hàng, tiền tệ, số lượng sản phẩm, địa chỉ email, trạng thái đơn hàng hoặc khoảng thời gian.

Phân biệt hai nhóm kiểu giúp DSL vừa có nền tảng tính toán đơn giản, vừa diễn đạt được ý nghĩa của dữ liệu. Một trường `age: Integer` cho biết dữ liệu là số nguyên; một trường `CustomerId` cho biết giá trị đó là định danh khách hàng và không thể tùy tiện dùng thay cho mã đơn hàng. Khi mô hình hóa đúng, trình biên dịch hoặc bộ kiểm tra của DSL có thể phát hiện nhiều lỗi trước khi chương trình chạy, còn người đọc hiểu rõ dữ liệu đang đại diện cho điều gì.

## 1. Kiểu nguyên thủy là gì?

Kiểu nguyên thủy là các kiểu cơ bản do ngôn ngữ lập trình cung cấp. Trong Java, các kiểu nguyên thủy gồm:

| Kiểu | Ý nghĩa | Ví dụ |
|---|---|---|
| `byte` | Số nguyên 8 bit có dấu | `byte retryCount = 3;` |
| `short` | Số nguyên 16 bit có dấu | `short portOffset = 12;` |
| `int` | Số nguyên 32 bit có dấu | `int quantity = 5;` |
| `long` | Số nguyên 64 bit có dấu | `long timestamp = 1730000000L;` |
| `float` | Số thực dấu phẩy động 32 bit | `float ratio = 0.5f;` |
| `double` | Số thực dấu phẩy động 64 bit | `double temperature = 36.5;` |
| `char` | Một đơn vị mã UTF-16 16 bit | `char initial = 'A';` |
| `boolean` | Giá trị đúng hoặc sai | `boolean enabled = true;` |

Các kiểu này phù hợp cho phép toán cơ bản và thường có biểu diễn gọn. Chúng là lựa chọn tự nhiên cho các giá trị như số lần thử, cờ bật/tắt hoặc một chỉ số đếm, nếu ý nghĩa miền không đòi hỏi thêm quy tắc.

Tuy nhiên, kiểu nguyên thủy chủ yếu mô tả hình thức biểu diễn. `int` không cho biết số nguyên là tuổi, mã vùng, số lượng hàng hay số giây. Hai biến cùng kiểu `int` có thể mang ý nghĩa hoàn toàn khác nhau và trình biên dịch không tự phân biệt được.

## 2. Kiểu tham chiếu và lớp bao trong Java

Java có các lớp bao (wrapper classes) tương ứng với phần lớn kiểu nguyên thủy:

| Kiểu nguyên thủy | Lớp bao |
|---|---|
| `byte` | `Byte` |
| `short` | `Short` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |
| `char` | `Character` |
| `boolean` | `Boolean` |

Lớp bao là kiểu tham chiếu, có thể được dùng trong generic và có thể nhận `null`. Java hỗ trợ boxing và unboxing để chuyển đổi tự động giữa giá trị nguyên thủy và lớp bao trong nhiều ngữ cảnh:

```java
int count = 3;
Integer boxedCount = count; // boxing
int value = boxedCount;     // unboxing
```

Sự tiện lợi này không có nghĩa hai loại kiểu giống nhau hoàn toàn. Unboxing một giá trị `null` gây `NullPointerException`; lớp bao cũng có thể tạo thêm chi phí đối tượng và cấp phát trong một số tình huống. Trong DSL, nên phân biệt rõ một trường bắt buộc có giá trị số với một trường có thể vắng mặt.

Ví dụ, `int retryCount` thường thể hiện một số nguyên luôn có giá trị, còn `Integer retryCount` có thể dùng `null` để biểu diễn trạng thái chưa khai báo nếu API cho phép. Tuy nhiên, dùng `null` làm nhiều ý nghĩa khác nhau dễ gây nhầm lẫn; nên quy định rõ khi nào giá trị bị thiếu, chưa biết hay không áp dụng.

## 3. Kiểu nguyên thủy trong DSL

Một DSL thường cần một tập kiểu cơ bản để mô tả literal và thuộc tính. Ví dụ:

```text
service "catalog" {
    replicas = 3
    enabled = true
    timeoutSeconds = 30
    displayName = "Product Catalog"
}
```

Bộ kiểm tra kiểu có thể suy ra:

- `replicas` là số nguyên.
- `enabled` là boolean.
- `timeoutSeconds` là số nguyên.
- `displayName` là chuỗi.

Các kiểu nguyên thủy cung cấp nền tảng cho biểu thức và phép toán. DSL có thể hỗ trợ cộng, trừ, so sánh, logic, nối chuỗi hoặc các thao tác khác tùy mục đích. Tuy nhiên, việc hai trường cùng có kiểu số nguyên không đồng nghĩa chúng có thể thay thế cho nhau. `replicas` và `timeoutSeconds` đều có thể lưu bằng `int`, nhưng cộng thời gian chờ với số bản sao là thao tác vô nghĩa trong miền.

Vì vậy, kiểu nguyên thủy nên được xem là lớp biểu diễn cơ bản. Khi một giá trị có ý nghĩa hoặc quy tắc riêng, kiểu miền giúp nâng cấp cách mô tả.

## 4. Kiểu miền là gì?

Kiểu miền là kiểu được định nghĩa để biểu diễn một khái niệm trong lĩnh vực cụ thể. Nó có thể là:

- **Value object:** giá trị được xác định bởi nội dung, chẳng hạn `Money`, `EmailAddress` hoặc `DateRange`.
- **Entity:** đối tượng có định danh và vòng đời riêng, chẳng hạn `Customer`, `Order` hoặc `Product`.
- **Enumeration:** tập giá trị hữu hạn, chẳng hạn `OrderStatus` hoặc `PaymentMethod`.
- **Kiểu kết hợp:** cấu trúc gồm nhiều thành phần có quan hệ, chẳng hạn `Address` gồm đường, thành phố và mã bưu chính.
- **Kiểu đại diện cho đơn vị:** `Duration`, `Distance`, `Temperature` hoặc `Quantity`.

Kiểu miền bổ sung ý nghĩa mà kiểu nguyên thủy không thể hiện. Ví dụ, `CustomerId` và `OrderId` đều có thể chứa UUID, nhưng chúng đại diện cho hai loại định danh khác nhau. Một API được định kiểu tốt sẽ ngăn việc truyền nhầm mã đơn hàng vào nơi cần mã khách hàng.

## 5. Vấn đề primitive obsession

Primitive obsession là tình trạng sử dụng quá nhiều kiểu nguyên thủy hoặc chuỗi tổng quát để biểu diễn những khái niệm miền có ý nghĩa riêng. Ví dụ:

```java
void transfer(String fromAccount, String toAccount, double amount) {
    // Thực hiện chuyển tiền
}
```

Chữ ký này không cho biết chuỗi nào là tài khoản nguồn, chuỗi nào là tài khoản đích; `amount` dùng loại tiền nào; giá trị âm có hợp lệ không; hoặc độ chính xác tiền tệ được xử lý ra sao.

Có thể cải thiện bằng các kiểu miền:

```java
void transfer(
    AccountId fromAccount,
    AccountId toAccount,
    Money amount
) {
    // Thực hiện chuyển tiền
}
```

Chữ ký mới diễn đạt ý nghĩa rõ hơn. `Money` có thể kiểm tra số tiền và loại tiền, còn `AccountId` giúp phân biệt định danh tài khoản với các chuỗi khác.

Không phải mọi biến nguyên thủy đều cần được bọc trong một lớp riêng. Một biến đếm cục bộ chỉ dùng trong vòng lặp có thể cứ là `int`. Kiểu miền đặc biệt hữu ích khi giá trị đi qua ranh giới module, xuất hiện trong API, có quy tắc xác thực, đơn vị hoặc phép toán riêng, hoặc dễ bị nhầm với một giá trị khác cùng biểu diễn.

## 6. Value object và quy tắc bất biến

Value object là đối tượng được xác định bởi giá trị của các thuộc tính, thường không có định danh vòng đời độc lập. Nó phù hợp để biểu diễn các khái niệm miền như tiền tệ, email, số lượng hoặc khoảng ngày.

Ví dụ, một kiểu email có thể xác thực dữ liệu ngay khi tạo:

```java
import java.util.Objects;

public record EmailAddress(String value) {
    public EmailAddress {
        Objects.requireNonNull(value, "value");
        if (value.isBlank() || !value.contains("@")) {
            throw new IllegalArgumentException("Invalid email address");
        }
    }
}
```

Đây là kiểm tra đơn giản để minh họa việc bảo vệ bất biến. Một hệ thống thực tế có thể cần quy tắc xác thực email phù hợp hơn. Điểm quan trọng là sau khi một `EmailAddress` được tạo thành công, các thành phần khác có thể dựa vào hợp đồng rằng giá trị đã vượt qua kiểm tra cơ bản.

Với record, Java tự cung cấp `equals`, `hashCode` và các phương thức truy cập dựa trên thành phần. Điều này phù hợp với value object bất biến. Nếu cần thay đổi giá trị, thường tạo một value object mới thay vì sửa đối tượng hiện tại.

## 7. Kiểu miền cho định danh

Các định danh thường được lưu bằng `long`, `UUID` hoặc `String`. Nếu dùng trực tiếp cùng một kiểu cho mọi loại ID, rất dễ truyền nhầm:

```java
void cancelOrder(long orderId) { }

long customerId = 1001L;
cancelOrder(customerId); // Vẫn biên dịch dù truyền nhầm loại ID
```

Có thể tạo kiểu riêng:

```java
import java.util.UUID;

public record OrderId(UUID value) {
    public OrderId {
        if (value == null) {
            throw new IllegalArgumentException("OrderId is required");
        }
    }
}

public record CustomerId(UUID value) {
    public CustomerId {
        if (value == null) {
            throw new IllegalArgumentException("CustomerId is required");
        }
    }
}

void cancelOrder(OrderId orderId) { }
```

Giờ đây, `CustomerId` không thể được truyền vào `cancelOrder` nếu không có chuyển đổi tường minh. Các kiểu ID riêng đặc biệt hữu ích trong DSL truy vấn, định nghĩa quan hệ, cấu hình và API nghiệp vụ.

Một định danh miền không nhất thiết phải dùng UUID. Nó có thể bao bọc `long`, `String` hoặc một kiểu khác. Cách biểu diễn bên trong có thể thay đổi mà không làm lộ chi tiết đó ra toàn bộ chương trình.

## 8. Kiểu miền cho tiền tệ và số đo

### 8.1. Tiền tệ

Tiền tệ là ví dụ điển hình cho thấy một kiểu nguyên thủy không đủ để thể hiện ý nghĩa. Không nên dùng `double` để tính tiền theo cách tùy tiện vì số thực dấu phẩy động có thể không biểu diễn chính xác nhiều phân số thập phân.

Java cung cấp `BigDecimal` để biểu diễn số thập phân chính xác theo cơ số 10. Có thể tạo kiểu `Money` chứa giá trị và loại tiền:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(amount.add(other.amount()), currency);
    }
}
```

Kiểu này ngăn cộng trực tiếp hai khoản tiền khác loại. Trong ứng dụng thực tế, còn cần xác định quy tắc làm tròn, số chữ số thập phân, thuế, tỷ giá và cách xử lý số âm theo nghiệp vụ. Những quy tắc đó nên thuộc hợp đồng của kiểu miền hoặc dịch vụ nghiệp vụ liên quan.

Khi tạo `BigDecimal`, nên dùng chuỗi thập phân như `new BigDecimal("0.1")` thay vì `new BigDecimal(0.1)`, vì giá trị `double` đầu vào có thể đã mang sai số nhị phân.

### 8.2. Số đo và đơn vị

Một giá trị `double distance = 5.0` không cho biết đơn vị là mét, kilomet hay dặm. Nếu DSL hỗ trợ tính toán số đo, cần biểu diễn đơn vị rõ ràng:

```text
distance = 5 km
elapsed = 30 s
```

Một mô hình có thể lưu giá trị chuẩn hóa cùng đơn vị:

```java
public enum LengthUnit {
    METER,
    KILOMETER
}

public record Length(double value, LengthUnit unit) {
    public Length {
        if (!Double.isFinite(value) || value < 0) {
            throw new IllegalArgumentException("Length must be finite and non-negative");
        }
    }

    public double inMeters() {
        return switch (unit) {
            case METER -> value;
            case KILOMETER -> value * 1000.0;
        };
    }
}
```

Đây là mô hình đơn giản. Với các hệ thống khoa học hoặc tài chính yêu cầu độ chính xác cao, cần chọn kiểu số và quy tắc chuyển đổi phù hợp. Điều quan trọng là không so sánh hoặc cộng các giá trị khác đơn vị nếu chưa có chuyển đổi được định nghĩa.

## 9. Enum và các tập giá trị miền

Khi một thuộc tính chỉ nhận một tập giá trị hữu hạn, enum thường rõ ràng hơn chuỗi:

```java
public enum OrderStatus {
    DRAFT,
    PENDING_PAYMENT,
    PAID,
    SHIPPED,
    DELIVERED,
    CANCELLED
}
```

Nếu dùng `String status`, các giá trị như `"PAID"`, `"paid"`, `"Payed"` hoặc `"DONE"` có thể xuất hiện ngoài ý muốn. Enum giới hạn lựa chọn và cho IDE khả năng gợi ý các giá trị hợp lệ.

Tuy nhiên, enum chỉ giới hạn tập giá trị, không tự bảo đảm mọi chuyển trạng thái đều hợp lệ. Ví dụ, đơn hàng không thể chuyển thẳng từ `DRAFT` sang `DELIVERED` nếu quy trình yêu cầu phải thanh toán và giao hàng trước. Quy tắc chuyển trạng thái cần được kiểm tra riêng.

Trong DSL, enum có thể được biểu diễn bằng literal:

```text
order.status = PAID
```

Bộ phân giải tên xác nhận `PAID` thuộc `OrderStatus`. Nếu DSL cho phép giá trị enum viết dưới dạng chuỗi, cần quy định cách phân biệt chuỗi thông thường với tên hằng enum.

## 10. Kiểu cấu trúc và kiểu miền tổng hợp

Một khái niệm miền thường gồm nhiều thuộc tính. Ví dụ địa chỉ có thể gồm đường, thành phố, tỉnh và mã bưu chính:

```java
public record Address(
    String street,
    String city,
    String province,
    String postalCode
) {
    public Address {
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("Street is required");
        }
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("City is required");
        }
    }
}
```

Trong DSL, thay vì khai báo bốn chuỗi rời rạc ở nhiều nơi, người dùng có thể viết:

```text
customer.address {
    street = "12 Nguyen Hue"
    city = "Ho Chi Minh City"
    province = "Ho Chi Minh City"
    postalCode = "700000"
}
```

Mô hình `Address` gom các trường liên quan và có thể thực thi quy tắc chung. Kiểu cấu trúc giúp DSL biểu diễn dữ liệu lồng nhau và tránh trùng lặp cách xác thực.

## 11. Kiểu miền và entity

Entity là đối tượng có định danh ổn định và vòng đời riêng. Hai entity có cùng thuộc tính vẫn có thể là hai đối tượng khác nhau vì ID của chúng khác nhau. Ví dụ, hai khách hàng cùng tên và địa chỉ vẫn là hai `Customer` khác nhau nếu mã khách hàng khác nhau.

Value object thường được so sánh theo giá trị; entity thường được nhận diện bằng ID. Phân biệt này ảnh hưởng đến cách DSL xử lý tham chiếu:

```text
order.customer = CustomerId("C-104")
```

Tham chiếu tới khách hàng nên được phân giải thành entity tương ứng hoặc một kiểu tham chiếu miền, thay vì sao chép toàn bộ dữ liệu khách hàng vào đơn hàng.

Trong thiết kế DSL, không phải mọi cấu trúc đều cần entity. Một `Money` hoặc `Address` thường có thể là value object; một `Order` có vòng đời và định danh riêng thường là entity.

## 12. Kiểu nguyên thủy, kiểu miền và hệ thống kiểu của DSL

Một DSL có thể định nghĩa một hệ thống kiểu nhiều tầng:

1. **Kiểu nguyên thủy:** `Integer`, `Decimal`, `Boolean`, `String`, `Date`, `Instant`.
2. **Kiểu miền:** `OrderId`, `Money`, `EmailAddress`, `Quantity`, `Address`.
3. **Kiểu tổng hợp:** danh sách, tập hợp, bản đồ, bản ghi hoặc kiểu tùy chọn.
4. **Kiểu tham chiếu:** tham chiếu đến đối tượng hoặc khai báo khác trong mô hình miền.

Ví dụ khai báo kiểu giả định:

```text
type OrderId = UUID

type Money {
    amount: Decimal
    currency: CurrencyCode
}

entity Order {
    id: OrderId
    total: Money
    status: OrderStatus
}
```

Ở đây, `UUID` và `Decimal` là kiểu nền; `OrderId` và `Money` là kiểu miền; `Order` là entity. Cú pháp thực tế tùy DSL, nhưng hệ thống kiểu cần quy định rõ quan hệ giữa kiểu nền và kiểu miền.

## 13. Tương thích kiểu và chuyển đổi

Hai kiểu có cùng cách lưu trữ không có nghĩa chúng tương thích. `OrderId` và `CustomerId` có thể đều chứa `UUID`, nhưng nên được xem là hai kiểu khác nhau. Tương tự, `Meters` và `Seconds` có thể cùng lưu số thực, nhưng không thể cộng trực tiếp.

Hệ thống kiểu DSL cần quy định:

- **Tương thích chính xác:** hai biểu thức cùng kiểu có thể được dùng ở vị trí yêu cầu kiểu đó.
- **Tương thích theo quan hệ con:** một kiểu con có thể được dùng ở nơi cần kiểu cha nếu mô hình hỗ trợ subtype.
- **Chuyển đổi ngầm định:** DSL có cho phép chuyển kiểu tự động trong những trường hợp an toàn hay không.
- **Chuyển đổi tường minh:** người viết phải yêu cầu phép chuyển đổi khi có nguy cơ mất thông tin hoặc đổi ý nghĩa.
- **Tính toán giữa kiểu miền:** phép cộng, so sánh hoặc kết hợp nào được phép cho từng kiểu.

Ví dụ, chuyển `Integer` sang `Decimal` có thể được xem là an toàn trong một DSL nếu không mất thông tin theo quy ước số học của nó. Chuyển `Decimal` sang `Integer` có thể làm mất phần thập phân, vì vậy nên yêu cầu phép chuyển đổi tường minh hoặc từ chối.

Với kiểu miền, phép chuyển đổi cần giữ ý nghĩa. Chuyển `Money` từ USD sang VND không đơn giản là đổi nhãn tiền tệ; cần tỷ giá và thời điểm áp dụng. Chuyển `Duration` từ phút sang giây có thể an toàn nếu quy tắc và độ chính xác được xác định.

## 14. Giá trị thiếu, null và kiểu tùy chọn

Một trường không xuất hiện trong tài liệu DSL có thể mang nhiều ý nghĩa:

- Người dùng muốn dùng giá trị mặc định.
- Giá trị chưa biết tại thời điểm khai báo.
- Thuộc tính không áp dụng cho đối tượng này.
- Người dùng chủ động xóa giá trị.

Không nên gom mọi trường hợp thành `null` mà không có quy ước. DSL có thể hỗ trợ kiểu tùy chọn như `Optional<T>` hoặc cú pháp riêng:

```text
middleName: Optional<String>
```

Trong Java, `Optional<T>` thường phù hợp cho giá trị trả về có thể vắng mặt; không nhất thiết nên dùng nó cho mọi trường và mọi thuộc tính. Với mô hình miền, có thể dùng một kiểu rõ nghĩa như `OptionalValue<T>`, `Unknown<T>` hoặc trạng thái riêng nếu cần phân biệt `missing`, `null`, `unknown` và `not applicable`.

Nếu dùng `null`, cần xác định rõ bộ kiểm tra kiểu và runtime xử lý nó ra sao. Một phép toán trên giá trị có thể vắng mặt cần quy tắc như từ chối, lan truyền trạng thái thiếu, dùng giá trị mặc định hoặc yêu cầu kiểm tra trước.

## 15. Kiểu nguyên thủy trong generic và collection của Java

Java generic không nhận trực tiếp kiểu nguyên thủy làm tham số kiểu. Ví dụ:

```java
List<Integer> quantities = new ArrayList<>();
quantities.add(3);
```

Ở đây dùng `Integer`, không phải `int`. Java tự boxing khi thêm giá trị nguyên thủy. Với mảng, có thể dùng trực tiếp kiểu nguyên thủy:

```java
int[] quantities = {3, 5, 8};
```

Sự khác biệt này ảnh hưởng đến việc ánh xạ kiểu DSL sang Java. Một danh sách số nguyên có thể được biểu diễn bằng `List<Integer>`, còn mảng hiệu năng cao có thể dùng `int[]`. Với kiểu miền, có thể dùng `List<OrderId>` hoặc `List<Money>` để giữ ý nghĩa từng phần tử.

Không nên dùng `List<Object>` cho mọi giá trị DSL nếu có thể định kiểu cụ thể. Kiểu cụ thể giúp compiler kiểm tra phần tử, IDE gợi ý đúng thao tác và giảm ép kiểu không an toàn.

## 16. Phân tích literal và ánh xạ kiểu từ cú pháp

Khi parser đọc literal, hệ thống cần chuyển token thành giá trị có kiểu phù hợp. Ví dụ:

| Cú pháp DSL | Kiểu trong mô hình | Ví dụ Java |
|---|---|---|
| `42` | `Integer` | `Integer.valueOf(42)` |
| `3.14` | `Decimal` | `new BigDecimal("3.14")` |
| `true` | `Boolean` | `Boolean.TRUE` |
| `"hello"` | `String` | `"hello"` |
| `2026-11-15` | `Date` | `LocalDate.parse(...)` |
| `10 km` | `Length` | `new Length(10, KILOMETER)` |
| `C-104` trong vị trí ID khách hàng | `CustomerId` | `new CustomerId(...)` |

Parser có thể nhận diện cú pháp literal, còn bộ phân tích ngữ nghĩa xác định kiểu đích theo ngữ cảnh. Ví dụ, chuỗi `"C-104"` tự nó chỉ là `String`; khi được gán cho trường `customerId`, hệ thống có thể kiểm tra định dạng rồi chuyển thành `CustomerId`.

Không nên tự động biến mọi chuỗi trông giống ID thành kiểu miền. Việc chuyển đổi cần dựa trên kiểu đích hoặc cú pháp rõ ràng để tránh suy đoán sai.

## 17. Kiểu miền và kiểm tra tính hợp lệ

Kiểu dữ liệu và kiểm tra hợp lệ có liên quan nhưng không giống nhau. Một giá trị có thể đúng kiểu nhưng sai quy tắc miền.

| Giá trị | Kiểu | Có thể hợp lệ về kiểu? | Quy tắc miền có thể áp dụng |
|---|---|---|---|
| `-3` | `Integer` | Có | Số lượng phải lớn hơn 0 |
| `0` | `Money` | Có | Một giao dịch cụ thể không cho phép số tiền bằng 0 |
| `"abc"` | `EmailAddress` sau khi tạo | Có thể bị từ chối khi khởi tạo | Phải đúng định dạng email theo chính sách |
| `PAID` | `OrderStatus` | Có | Chỉ được chuyển sang `PAID` sau khi thanh toán xác nhận |
| `5 km` | `Length` | Có | Khoảng cách giao hàng phải nằm trong giới hạn dịch vụ |

Kiểm tra kiểu xác nhận giá trị được dùng ở đúng loại vị trí. Kiểm tra bất biến hoặc quy tắc nghiệp vụ xác nhận giá trị đó có được phép trong ngữ cảnh hiện tại hay không. Ví dụ, `-3` vẫn là số nguyên hợp lệ về mặt kiểu, nhưng không phải số lượng hàng hợp lệ.

Nên thực hiện kiểm tra tĩnh khi có thể, như kiểu trường và kiểu literal. Các điều kiện phụ thuộc dữ liệu runtime, quyền, trạng thái hiện tại hoặc dịch vụ bên ngoài cần được xác thực khi thực thi.

## 18. Nguyên tắc lựa chọn giữa kiểu nguyên thủy và kiểu miền

Không cần tạo một lớp riêng cho mọi biến. Hãy cân nhắc kiểu miền khi một hoặc nhiều điều sau đúng:

- Giá trị có ý nghĩa nghiệp vụ rõ ràng và dễ bị nhầm với kiểu khác.
- Giá trị có đơn vị, độ chính xác hoặc quy tắc chuyển đổi riêng.
- Giá trị có bất biến cần bảo vệ ngay khi tạo.
- Giá trị xuất hiện trong API công khai hoặc đi qua nhiều module.
- Các thao tác hợp lệ trên giá trị khác với phép toán cơ bản.
- Cần định danh ổn định hoặc tham chiếu đến đối tượng miền.
- DSL cần hiển thị tên kiểu gần với ngôn ngữ của chuyên gia miền.

Giữ kiểu nguyên thủy khi giá trị chỉ phục vụ phép tính cục bộ đơn giản, không có ý nghĩa riêng cần bảo vệ và việc tạo wrapper chỉ làm API nặng nề hơn.

## 19. Ví dụ tổng hợp: mô hình đơn hàng

Một DSL bán hàng có thể khai báo:

```text
entity Order {
    id: OrderId
    customer: CustomerId
    quantity: Quantity
    total: Money
    status: OrderStatus
    deliveryAddress: Address
}
```

Mô hình Java tương ứng có thể dùng record và enum:

```java
public record OrderId(String value) { }
public record CustomerId(String value) { }

public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}

public enum OrderStatus {
    DRAFT,
    PENDING_PAYMENT,
    PAID,
    SHIPPED,
    CANCELLED
}

public record Order(
    OrderId id,
    CustomerId customer,
    Quantity quantity,
    Money total,
    OrderStatus status,
    Address deliveryAddress
) { }
```

Ở đây:

- `OrderId` và `CustomerId` phân biệt hai loại định danh.
- `Quantity` bảo vệ bất biến số lượng dương.
- `Money` mang cả giá trị và loại tiền.
- `OrderStatus` giới hạn trạng thái hợp lệ.
- `Address` gom các trường địa chỉ thành một khái niệm miền.
- `Order` là entity có định danh và vòng đời.

Mô hình có thể được tạo từ tài liệu DSL sau khi parser phân tích cấu trúc, bộ phân giải tên liên kết ID và bộ kiểm tra ngữ nghĩa xác nhận kiểu cùng quy tắc miền. Runtime sau đó có thể dùng mô hình đã kiểm tra để thực hiện các thao tác đơn hàng.

## 20. Nguyên tắc thiết kế hệ kiểu cho DSL

Một hệ kiểu kết hợp kiểu nguyên thủy và kiểu miền hiệu quả nên tuân theo các nguyên tắc:

- **Dùng kiểu nguyên thủy cho dữ liệu cơ bản:** số đếm, cờ logic và phép tính cục bộ đơn giản.
- **Đặt tên miền cho giá trị có ý nghĩa:** `OrderId` rõ hơn `String`, `Money` rõ hơn `double`.
- **Bảo vệ bất biến:** kiểm tra giá trị ở constructor hoặc factory để đối tượng hợp lệ ngay khi được tạo.
- **Tách định danh khỏi giá trị hiển thị:** tên và ID có vai trò khác nhau.
- **Quy định đơn vị và độ chính xác:** tránh cộng hoặc so sánh các giá trị khác đơn vị mà không chuyển đổi.
- **Giới hạn tập lựa chọn:** dùng enum hoặc kiểu biến thể khi miền có tập giá trị xác định.
- **Thiết kế rõ trạng thái thiếu:** phân biệt mặc định, chưa biết, không áp dụng và giá trị rỗng khi nghiệp vụ cần.
- **Kiểm tra tĩnh và runtime đúng chỗ:** compiler kiểm tra quan hệ kiểu; runtime kiểm tra dữ liệu và trạng thái thực tế.
- **Giữ ánh xạ DSL nhất quán:** literal, trường, kiểu Java và serializer phải cùng hiểu một kiểu miền theo một hợp đồng.
- **Tránh lạm dụng wrapper:** chỉ tạo kiểu miền khi nó mang ý nghĩa, quy tắc hoặc lợi ích kiểm soát thực sự.

Kiểu nguyên thủy cung cấp những khối xây dựng cơ bản cho tính toán; kiểu miền đặt những khối đó vào đúng ngữ cảnh nghiệp vụ. Một DSL sử dụng cả hai hợp lý có thể diễn đạt dữ liệu rõ ràng, kiểm soát phép toán, ngăn truyền nhầm giá trị và đưa các quy tắc quan trọng đến gần nơi dữ liệu được tạo. Nhờ vậy, hệ thống kiểu không chỉ giúp parser và compiler kiểm tra chương trình mà còn trở thành một phần của mô hình miền mà người dùng DSL có thể hiểu và tin cậy.
