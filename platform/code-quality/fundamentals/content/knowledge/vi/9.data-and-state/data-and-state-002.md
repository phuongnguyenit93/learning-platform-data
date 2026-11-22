# Kiểu dữ liệu, đơn vị và ràng buộc miền giá trị

Hãy xem chữ ký phương thức Java sau:

```java
void reserve(String productId, int quantity, long amount, long expiresAt);
```

Trình biên dịch biết các kiểu `String`, `int` và `long`, nhưng người đọc vẫn phải đoán: `quantity` có được bằng 0 không, `amount` tính bằng đồng hay xu, `expiresAt` là mili giây Unix hay số giây, và `productId` có được là chuỗi rỗng không? Những câu hỏi này quyết định tính đúng đắn của nghiệp vụ. Nếu câu trả lời chỉ tồn tại trong tài liệu, chú thích hoặc kiến thức của người viết, mỗi điểm gọi đều có nguy cơ hiểu khác nhau.

Trong chương **Dữ liệu và trạng thái** của module `CODE_QUALITY_FUNDAMENTALS`, lựa chọn kiểu dữ liệu là một phần quan trọng để mã **đáng tin cậy, dễ hiểu và dễ thay đổi**. Kiểu tốt cho người đọc biết giá trị đang đại diện cho khái niệm nào; ràng buộc tốt ngăn trạng thái không hợp lệ xuất hiện hoặc đi sâu vào hệ thống; đơn vị rõ ràng ngăn phép tính hợp lệ về cú pháp nhưng sai về ý nghĩa.

Sau bài học, bạn có thể:

- Phân biệt **kiểu lưu trữ kỹ thuật** với **kiểu dữ liệu nghiệp vụ**.
- Chọn cách biểu diễn đúng cho số lượng, tiền, tỷ lệ, thời điểm và khoảng thời gian.
- Phát hiện khi hai giá trị cùng kiểu nguyên thủy nhưng khác đơn vị hoặc khác ý nghĩa.
- Mô tả miền giá trị hợp lệ và thực thi ràng buộc ở nơi thích hợp.
- Dùng `record`, `enum`, lớp bất biến và kiểm tra ở ranh giới để làm rõ hợp đồng dữ liệu.
- Nhận diện giới hạn của validation, hệ kiểu và các ràng buộc trong môi trường nhiều luồng hoặc nhiều dịch vụ.

## 1. Một kiểu dữ liệu trả lời nhiều hơn câu hỏi “lưu bằng gì?”

Kiểu dữ liệu trong ngôn ngữ lập trình thường cho biết cách biểu diễn và tập thao tác khả dụng. Ví dụ `int` cho phép số nguyên 32 bit có dấu; `String` cho phép chuỗi; `Instant` đại diện cho một thời điểm trên trục thời gian. Nhưng nghiệp vụ có thể đòi hỏi tập giá trị hẹp hơn:

- Số lượng đặt hàng phải từ 1 đến 100.
- Số tiền thanh toán phải không âm và có đơn vị tiền tệ xác định.
- Ngày giao hàng không được trước ngày đặt hàng theo lịch nghiệp vụ.
- Trạng thái thanh toán chỉ được là `PENDING`, `PAID` hoặc `FAILED`.
- ID đơn hàng không được rỗng và không được hoán đổi với ID người dùng.

Có thể xem thiết kế dữ liệu qua ba câu hỏi:

| Câu hỏi | Ví dụ | Điều thiết kế cần nói rõ |
| --- | --- | --- |
| **Nó là gì?** | ID đơn hàng, số lượng, thời điểm | Tên và kiểu diễn tả khái niệm |
| **Nó dùng đơn vị nào?** | VND, USD, giây, mili giây | Đơn vị ở kiểu, tên hoặc hợp đồng |
| **Nó được phép mang giá trị nào?** | 1–100, không âm, danh sách trạng thái | Ràng buộc miền giá trị và cách báo lỗi |

Một biến tên `value` có kiểu `long` chỉ nói rất ít. Một giá trị `MoneyVnd`, `Quantity` hoặc `Duration` biểu diễn nhiều thông tin hơn và giúp phát hiện một số sai sót sớm.

### Miền giá trị (*domain*) không nhất thiết trùng miền của kiểu nguyên thủy

Với `int`, Java cho phép số âm, số 0 và số dương trong phạm vi của kiểu. Nhưng miền của “số lượng mua” có thể chỉ gồm số nguyên dương và giới hạn trên do nghiệp vụ quy định.

Nếu mỗi nơi tự viết `if (quantity <= 0)`, quy tắc bị phân tán. Nếu một nơi quên kiểm tra, dữ liệu xấu có thể lọt vào. Khi ràng buộc có ý nghĩa rộng và ổn định, có thể đưa nó vào một kiểu hoặc điểm tạo giá trị dùng chung.

**Nguyên tắc:** biểu đạt các ràng buộc chắc chắn của khái niệm ở gần nơi khởi tạo nhất có thể, đồng thời giữ các ràng buộc phụ thuộc bối cảnh tại nơi sở hữu bối cảnh ấy.

## 2. Sai đơn vị: chương trình biên dịch nhưng kết quả sai

Hai giá trị cùng kiểu `long` vẫn có thể biểu diễn hai đại lượng không tương thích:

```java
long timeout = 3_000;
long elapsedSeconds = 5;

if (elapsedSeconds > timeout) {
    // ...
}
```

Nếu `timeout` là mili giây, điều kiện đang so sánh **giây với mili giây**. Java không báo lỗi vì cả hai đều là `long`. Tương tự, cộng 100 USD với 100 VND hay so sánh kilogram với gram mà không quy đổi có thể tạo kết quả sai dù toán tử hợp lệ.

Một số loại đơn vị thường gặp:

| Dữ liệu | Mơ hồ thường gặp | Cách biểu đạt rõ hơn |
| --- | --- | --- |
| Số tiền | Đồng, xu, USD, VND | `MoneyVnd`, tiền theo đơn vị nhỏ nhất, hoặc `Money(currency, amount)` |
| Khoảng thời gian | Giây, mili giây, nano giây | `Duration` |
| Mốc thời gian | Unix seconds/millis, giờ địa phương | `Instant`, `ZonedDateTime` theo yêu cầu |
| Ngày trên lịch | Ngày theo múi giờ nào? | `LocalDate` kèm ngữ cảnh lịch |
| Khoảng cách | Mét hay kilomet | Tên rõ đơn vị hoặc kiểu đo lường |
| Tỷ lệ | 0,15 hay 15 hay 1.500 basis points | `Percentage` hoặc `DiscountRate` có quy ước cụ thể |

Khi chưa có kiểu nghiệp vụ riêng, hậu tố tên như `timeoutMillis`, `amountVnd`, `distanceMeters` có thể giảm nhầm lẫn đáng kể. Khi đơn vị được dùng xuyên nhiều lớp hoặc có phép toán riêng, một kiểu mô tả đại lượng sẽ bảo vệ tốt hơn.

### Dùng kiểu thời gian có sẵn

Thay vì:

```java
long timeoutMillis = 3_000;
long startedAtMillis = System.currentTimeMillis();
```

có thể diễn đạt bằng:

```java
import java.time.Duration;
import java.time.Instant;

Duration paymentTimeout = Duration.ofSeconds(3);
Instant startedAt = Instant.now();
Instant deadline = startedAt.plus(paymentTimeout);
```

`Duration` là **độ dài khoảng thời gian**; `Instant` là **mốc thời gian**. Hai khái niệm này không thể thay thế trực tiếp cho nhau. Nếu phải đếm thời gian timeout trong tiến trình, đồng hồ đơn điệu phù hợp hơn phép trừ các giá trị `Instant.now()` hoặc `System.currentTimeMillis()` vì đồng hồ thực có thể được điều chỉnh; cách chọn API phụ thuộc mục đích đo.

Nếu một API yêu cầu mili giây, hãy chuyển tại ranh giới rõ ràng, chẳng hạn `paymentTimeout.toMillis()`, và lưu ý trường hợp tràn số khi chuyển những khoảng thời gian rất lớn.

### Ngày, thời điểm và múi giờ không phải một

Giả sử yêu cầu “đơn hàng hết hạn vào cuối ngày 30/11 theo giờ Việt Nam”. `LocalDate.of(2026, 11, 30)` biểu diễn **ngày trên lịch**, nhưng không có giờ hoặc múi giờ; `Instant` biểu diễn một thời điểm tuyệt đối; `ZonedDateTime` kết hợp giờ địa phương với múi giờ.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate expiryDate = LocalDate.of(2026, 11, 30);
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant exclusiveDeadline = expiryDate.plusDays(1)
        .atStartOfDay(businessZone)
        .toInstant();
```

Ví dụ chọn **đầu ngày kế tiếp là thời hạn loại trừ**, phù hợp với điều kiện “hợp lệ khi `now.isBefore(exclusiveDeadline)`”. Không nên suy ra thời điểm tuyệt đối từ một `LocalDate` khi chưa biết múi giờ nghiệp vụ. Với những múi giờ có chuyển đổi giờ mùa hè, độ dài một ngày lịch cũng không phải lúc nào cũng đúng 24 giờ.

## 3. Tiền: kiểu số đúng chưa đủ khi thiếu quy tắc

Đoạn sau dễ viết nhưng dễ tạo sai số:

```java
double total = 0.1 + 0.2;
boolean exact = total == 0.3; // Thường là false trong IEEE 754.
```

`double` là số dấu phẩy động nhị phân, không biểu diễn chính xác mọi phân số thập phân. Vì vậy, dùng `double` cho nhiều phép tính tiền đòi hỏi chính xác theo quy tắc thập phân thường không phù hợp.

Hai cách biểu diễn hay dùng:

1. **Số nguyên đơn vị nhỏ nhất**: `long amountMinorUnits`, với hợp đồng ghi rõ đơn vị (ví dụ cent của USD hoặc đồng của VND).
2. **Số thập phân chính xác**: `BigDecimal`, kết hợp mã tiền tệ, quy tắc scale và làm tròn được định nghĩa rõ.

Chọn cách nào phụ thuộc đơn vị tiền, phạm vi số, nghiệp vụ thuế/chiết khấu và cách lưu trữ/giao tiếp. Không tự mặc định mọi đồng tiền đều có hai chữ số sau dấu thập phân.

### Một kiểu nhỏ cho VND không âm

Giả sử miền hiện tại chỉ làm việc với số tiền **không âm, nguyên đồng Việt Nam**:

```java
record MoneyVnd(long amount) {
    MoneyVnd {
        if (amount < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
    }

    MoneyVnd add(MoneyVnd other) {
        if (other == null) {
            throw new IllegalArgumentException("Money is required");
        }
        return new MoneyVnd(Math.addExact(amount, other.amount()));
    }

    MoneyVnd multiply(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("Quantity cannot be negative");
        }
        return new MoneyVnd(Math.multiplyExact(amount, quantity));
    }
}
```

Ở đây:

- Tên `MoneyVnd` làm rõ đơn vị.
- Constructor từ chối giá trị âm theo **miền đã chọn**.
- `Math.addExact` và `Math.multiplyExact` phát hiện tràn số, tránh kết quả đảo dấu hoặc sai số mà `long` thông thường có thể gây ra.
- Phép cộng chỉ nhận cùng loại `MoneyVnd`, ngăn cộng trực tiếp tiền VND với một đại lượng khác.

**Giới hạn:** kiểu này không đại diện tiền âm dùng trong bút toán, khoản điều chỉnh hoặc nhiều loại tiền. Nếu nghiệp vụ cần các trường hợp đó, nên thiết kế thêm các khái niệm phù hợp, thay vì lách ràng buộc hoặc bỏ kiểm tra một cách tùy tiện.

### Tiền đa loại: làm rõ cả loại tiền và làm tròn

Ví dụ dùng `BigDecimal` với `Currency`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

record Money(Currency currency, BigDecimal amount) {
    Money {
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(amount, "amount");

        int fractionDigits = currency.getDefaultFractionDigits();
        if (fractionDigits < 0) {
            throw new IllegalArgumentException("Unsupported currency scale");
        }

        amount = amount.setScale(fractionDigits, RoundingMode.UNNECESSARY);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
    }

    Money add(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(currency, amount.add(other.amount()));
    }
}
```

`RoundingMode.UNNECESSARY` từ chối giá trị yêu cầu làm tròn để phù hợp scale, thay vì tự âm thầm làm tròn. Đây là một **chính sách minh họa**: trong sản phẩm thật, một phép tính thuế hoặc tỷ giá có thể cần giữ độ chính xác nội bộ lớn hơn rồi chỉ làm tròn tại thời điểm quy định. Không nên dùng constructor trên cho mọi công đoạn tính toán tài chính.

Để tạo số thập phân từ văn bản, ưu tiên `new BigDecimal("12.50")` hoặc nguồn thập phân xác định. Tránh `new BigDecimal(0.1)` nếu kỳ vọng đúng giá trị thập phân 0,1. Khi so sánh `BigDecimal`, `equals` còn xét scale (ví dụ `1.0` khác `1.00`), còn `compareTo` so sánh giá trị số; phải chọn phù hợp với hợp đồng của mình.

## 4. Miền giá trị và bất biến: đưa điều chắc chắn vào chỗ tạo dữ liệu

Một số lượng đặt hàng phải dương. Nếu quy tắc này áp dụng cho mọi dòng hàng, ta có thể tạo một kiểu với constructor kiểm tra:

```java
record Quantity(int value) {
    Quantity {
        if (value <= 0 || value > 100) {
            throw new IllegalArgumentException(
                    "Quantity must be between 1 and 100");
        }
    }
}
```

Giả định ở đây là mỗi dòng hàng được phép đặt từ 1 tới 100 sản phẩm. Nếu “100” thay đổi theo khách, tồn kho hay chiến dịch thì giới hạn này có thể thuộc về chính sách kiểm tra đơn hàng, không phải tính chất vĩnh viễn của `Quantity`. Kiểu dữ liệu cần bảo vệ **bất biến của khái niệm**, tránh gắn quy tắc thay đổi theo ngữ cảnh vào một constructor được dùng khắp hệ thống.

Với `record` trong Java 17, compact constructor nhận tham số cùng tên thành phần. Nếu constructor ném ngoại lệ thì đối tượng không được tạo thành công. Cách này giảm khả năng tồn tại `Quantity(0)` qua các điểm khởi tạo thông thường.

### Kiểu dữ liệu nên bảo vệ được điều nó tuyên bố

Với một lớp có getter/setter công khai, việc kiểm tra constructor chưa đủ:

```java
class QuantityBox {
    private int value;

    QuantityBox(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        this.value = value;
    }

    void setValue(int value) {
        this.value = value; // Có thể phá bất biến sau khi khởi tạo.
    }
}
```

Để duy trì tính hợp lệ, mọi thao tác thay đổi phải giữ bất biến. Một giá trị bất biến (*immutable value*) với thao tác tạo giá trị mới thường dễ kiểm chứng hơn:

```java
record InventoryCount(int value) {
    InventoryCount {
        if (value < 0) {
            throw new IllegalArgumentException("Stock cannot be negative");
        }
    }

    InventoryCount remove(int quantity) {
        if (quantity < 0 || quantity > value) {
            throw new IllegalArgumentException("Invalid removal");
        }
        return new InventoryCount(value - quantity);
    }
}
```

`InventoryCount` tự bảo vệ quy tắc không âm **trong một phép tính cục bộ**. Tuy nhiên, hai server cùng đọc tồn kho rồi tính giá trị mới có thể vẫn ghi đè nhau. Bất biến trong object không tự thay thế transaction hoặc cập nhật nguyên tử ở kho dữ liệu dùng chung.

## 5. Bảo vệ hai khái niệm dùng cùng kiểu nguyên thủy

Ví dụ API hủy đơn:

```java
void cancelOrder(String orderId, String userId) {
    // ...
}

cancelOrder(userId, orderId); // Vẫn biên dịch nếu hai biến đều là String.
```

Hai ID cùng là `String` ở mức lưu trữ nhưng thuộc hai miền giá trị khác nhau. Có thể diễn đạt chúng bằng hai kiểu:

```java
record OrderId(String value) {
    OrderId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Order ID is required");
        }
    }
}

record UserId(String value) {
    UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("User ID is required");
        }
    }
}

void cancelOrder(OrderId orderId, UserId userId) {
    // ...
}
```

Giờ đây, truyền một `UserId` vào vị trí `OrderId` là sai kiểu tại thời điểm biên dịch. Lợi ích lớn khi hệ thống dùng nhiều ID, đơn vị hoặc khái niệm giống nhau về cấu trúc nhưng khác về ý nghĩa.

Đổi lại là chi phí chuyển đổi tại API, database và thư viện. Không cần tạo lớp bọc cho **mọi** chuỗi nếu chỉ làm tăng số tầng mà không bảo vệ một khái niệm thực sự. Nên ưu tiên nơi có nguy cơ truyền nhầm hoặc cần tập trung validation.

### Kiểu là một phần của hợp đồng, không chỉ tên biến

Tên `userId` chỉ hỗ trợ người đọc; trình biên dịch vẫn cho phép truyền `orderId` vào đó khi cùng kiểu `String`. Kiểu `UserId` ngăn được sự hoán đổi này. Nhưng kiểu cũng có giới hạn: một `UserId` được tạo từ chuỗi hợp lệ chưa chứng minh rằng người dùng đó tồn tại, có quyền hủy đơn hay đang hoạt động. Những thông tin đó phụ thuộc dữ liệu và ngữ cảnh tại thời điểm thực hiện.

## 6. Mô hình tập giá trị hữu hạn bằng enum

Giả sử hệ thống lưu trạng thái thanh toán bằng mã số:

```java
int status = 2;

if (status == 2) {
    // Đã thanh toán?
}
```

Một kiểu `enum` thể hiện tập lựa chọn hữu hạn và tên của từng lựa chọn:

```java
enum PaymentStatus {
    PENDING,
    PAID,
    FAILED
}

void process(PaymentStatus status) {
    if (status == null) {
        throw new IllegalArgumentException("Missing status");
    }

    switch (status) {
        case PENDING -> displayPending();
        case PAID -> displayPaid();
        case FAILED -> displayFailure();
    }
}
```

Đây là cú pháp Java 17. Tập giá trị được mô tả ngay ở kiểu, thay vì trông chờ các điểm sử dụng nhớ 1, 2 hoặc 3 nghĩa là gì.

Nếu dữ liệu từ hệ thống ngoài dùng chuỗi `"P"`, `"D"`, `"F"`, nên ánh xạ chúng sang `PaymentStatus` tại ranh giới nhập dữ liệu và quyết định rõ cách xử lý mã lạ. Không được mặc định một mã không nhận biết là `PAID` chỉ để tránh lỗi parse.

### Tránh tập trạng thái không hợp lệ từ nhiều cờ

Hai boolean như `isPaid` và `isFailed` tạo ra bốn tổ hợp, trong đó `true/true` có thể vô nghĩa. Một enum có thể giới hạn các trạng thái đơn giản còn ba lựa chọn phù hợp. Tuy nhiên, nếu quy trình có nhiều chiều độc lập thật sự, chẳng hạn **trạng thái thanh toán** và **trạng thái vận chuyển**, không nên ép hai chiều vào một enum chứa hàng chục tên ghép. Có thể cần hai trạng thái với ràng buộc liên kết ở cấp đối tượng nghiệp vụ.

Một enum giúp xác định **tập trạng thái**; nó chưa tự xác định **chuyển trạng thái hợp lệ**. Điều này phải được biểu diễn ở lớp sở hữu hành vi hoặc mô hình trạng thái.

## 7. Ràng buộc liên trường không nằm trong một thuộc tính đơn lẻ

Một số bất biến phụ thuộc **nhiều thuộc tính cùng lúc**. Ví dụ, nếu một khoản thanh toán ở trạng thái `PAID` thì phải có mã xác nhận thu tiền, và một mã xác nhận trong mô hình này chỉ hợp lệ khi đã `PAID`:

```java
record PaymentSnapshot(
        String paymentId,
        PaymentStatus status,
        String captureReference
) {
    PaymentSnapshot {
        if (paymentId == null || paymentId.isBlank()) {
            throw new IllegalArgumentException("Payment ID is required");
        }
        if (status == null) {
            throw new IllegalArgumentException("Status is required");
        }

        boolean hasCaptureReference =
                captureReference != null && !captureReference.isBlank();
        if ((status == PaymentStatus.PAID) != hasCaptureReference) {
            throw new IllegalArgumentException(
                    "Capture reference must exist exactly for PAID");
        }
    }

    PaymentSnapshot markPaid(String confirmedCaptureReference) {
        if (status != PaymentStatus.PENDING) {
            throw new IllegalStateException("Payment is not pending");
        }
        return new PaymentSnapshot(
                paymentId, PaymentStatus.PAID, confirmedCaptureReference);
    }
}
```

Mô hình này **cố ý đơn giản hóa** nghiệp vụ: chỉ trạng thái đã thu tiền mới có `captureReference`. Trong hệ thống thanh toán thật có thể tồn tại các mã giao dịch ở bước ủy quyền, đang đối soát hoặc hoàn tiền; khi đó tên trường và bất biến phải phản ánh trạng thái thực tế. Không được áp quy tắc minh họa cho mọi hệ thống thanh toán.

Nhờ constructor, snapshot không được tạo với `PAID` nhưng thiếu bằng chứng. Phương thức `markPaid` đặt tên rõ chuyển trạng thái và từ chối chuyển từ `FAILED` hoặc trạng thái không cho phép.

### Phân biệt trạng thái trong bộ nhớ và trạng thái dùng chung

Một `PaymentSnapshot` hợp lệ tại thời điểm tạo **không đảm bảo** nó còn mới khi ghi vào cơ sở dữ liệu. Hai yêu cầu đồng thời có thể đọc cùng trạng thái `PENDING` rồi cùng tìm cách chuyển trạng thái.

Với dữ liệu chia sẻ, phải có cơ chế kiểm soát đồng thời như cập nhật có điều kiện, phiên bản bản ghi hoặc transaction phù hợp. Ví dụ dạng SQL minh họa:

```sql
UPDATE payments
SET status = 'PAID',
    capture_reference = :capture_reference,
    version = version + 1
WHERE id = :payment_id
  AND status = 'PENDING'
  AND version = :expected_version;
```

Nếu số hàng được cập nhật bằng 0, có thể trạng thái đã đổi hoặc phiên bản không khớp; phía gọi cần xác định xử lý tiếp dựa trên nghiệp vụ. Các tham số có dấu `:` ở đây là cú pháp minh họa của framework, không phải cú pháp bind chung cho mọi JDBC driver.

Một mô hình trong Java bảo vệ đối tượng đang được sử dụng; database và transaction bảo vệ cạnh tranh giữa các tiến trình.

## 8. Ranh giới dữ liệu: kiểm tra ở đâu và bao nhiêu lần?

Hầu hết ứng dụng nhận dữ liệu từ JSON, form, file, message queue hay hệ thống ngoài. Đầu vào ban đầu không thể được coi là hợp lệ chỉ vì kiểu Java của DTO đã khớp.

Ví dụ request:

```java
record CreateOrderRequest(
        String productId,
        int quantity,
        long unitPriceVnd
) {}
```

Bản DTO trên vẫn có thể chứa `productId = ""`, `quantity = -10` hoặc `unitPriceVnd = -1`. Trước khi đưa dữ liệu vào nghiệp vụ, một hàm chuyển đổi có thể tạo những kiểu đã kiểm tra:

```java
record OrderLine(
        String productId,
        Quantity quantity,
        MoneyVnd unitPrice
) {
    OrderLine {
        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException("Product ID is required");
        }
        if (quantity == null || unitPrice == null) {
            throw new IllegalArgumentException("Line data is required");
        }
    }

    MoneyVnd lineTotal() {
        return unitPrice.multiply(quantity.value());
    }
}

final class OrderLineMapper {
    OrderLine toDomain(CreateOrderRequest request) {
        if (request == null) {
            throw new IllegalArgumentException("Request is required");
        }
        return new OrderLine(
                request.productId(),
                new Quantity(request.quantity()),
                new MoneyVnd(request.unitPriceVnd())
        );
    }
}
```

Ở đây DTO mô tả cấu trúc đi qua mạng; `OrderLine` biểu đạt dữ liệu miền đã được kiểm tra. Không cần bắt mọi exception rồi trả giá trị mặc định. Tầng API có thể chuyển `IllegalArgumentException` thành phản hồi lỗi đầu vào với thông tin thích hợp, trong khi các lỗi không mong đợi cần được xử lý riêng.

### Phân biệt ba lớp ràng buộc

| Vị trí | Điều cần bảo vệ | Ví dụ |
| --- | --- | --- |
| **Ranh giới nhận dữ liệu** | Định dạng, trường bắt buộc, giới hạn độ dài/kiểu có thể parse | JSON thiếu `productId`, chuỗi mã quá dài |
| **Mô hình miền** | Bất biến luôn đúng với khái niệm | `Quantity > 0`, `MoneyVnd >= 0` |
| **Nghiệp vụ có ngữ cảnh / lưu trữ** | Quyền hạn, tồn kho, ràng buộc liên bản ghi, cập nhật đồng thời | Khách đủ quyền, kho còn hàng, mã đơn duy nhất |

Không nên chỉ kiểm tra ở controller rồi tin mọi điểm gọi nội bộ sẽ luôn đúng. Nhưng cũng không nên kiểm tra quyền truy cập khách hàng ngay trong constructor của một kiểu `Quantity`: đó không phải bất biến của số lượng.

Trong môi trường có nhiều nguồn dữ liệu, kiểm tra tại ranh giới là cần thiết để phản hồi lỗi rõ. Kiểu miền là lớp phòng vệ bổ sung giúp logic bên trong ít phải xử lý các tổ hợp giá trị không hợp lệ.

## 9. Bất biến của tập hợp và dữ liệu có thể thay đổi

Một `record` không tự động làm **toàn bộ đồ thị dữ liệu** bất biến. Nếu record chứa danh sách có thể chỉnh sửa, phía gọi có thể thay đổi dữ liệu sau khi validation:

```java
record Cart(List<OrderLine> items) {}
```

Nếu `items` là `ArrayList`, người gọi vẫn giữ tham chiếu tới danh sách và có thể thêm hoặc xóa phần tử. Với quy tắc “giỏ hàng phải có ít nhất một dòng”, việc validate lúc tạo chưa đủ nếu danh sách có thể thay đổi sau đó.

Một phiên bản kiểm soát tốt hơn:

```java
import java.util.List;

record Cart(List<OrderLine> items) {
    Cart {
        if (items == null || items.isEmpty()) {
            throw new IllegalArgumentException("Cart cannot be empty");
        }
        items = List.copyOf(items);
    }

    MoneyVnd totalVnd() {
        MoneyVnd total = new MoneyVnd(0);
        for (OrderLine line : items) {
            total = total.add(line.lineTotal());
        }
        return total;
    }
}
```

`List.copyOf` tạo danh sách không thể sửa qua API danh sách và không giữ cùng danh sách có thể sửa bên ngoài. Nó cũng từ chối phần tử `null`. Tuy nhiên, đây là **bản sao nông** (*shallow copy*): nếu phần tử chứa đối tượng mutable thì trạng thái bên trong phần tử vẫn có thể bị thay đổi. Ví dụ trên dùng `OrderLine`, `Quantity` và `MoneyVnd` dưới dạng các record chứa dữ liệu bất biến để tránh nguy cơ đó.

Nếu lớp cần cho phép cập nhật tập hợp, hãy cung cấp các phương thức nghiệp vụ rõ nghĩa như `addItem` hoặc `removeItem`, bảo đảm mọi trạng thái sau cập nhật vẫn hợp lệ. Không nên chỉ công khai danh sách mutable rồi dựa vào các nơi gọi tự tuân thủ quy tắc.

## 10. Giá trị “không có”, “chưa biết” và “không áp dụng” là những ý nghĩa khác nhau

Nhiều API dùng `null`, `0` hoặc `-1` để mang nhiều ý nghĩa. Ví dụ:

```java
long shippingFeeVnd = -1;
```

`-1` có thể nghĩa là chưa tính, không hỗ trợ giao hàng, chưa có địa chỉ hoặc dịch vụ phí đang lỗi. Các trường hợp đó cần hành vi khác nhau; gộp chúng vào một giá trị đặc biệt làm mã khó hiểu và dễ trả kết quả sai.

Nếu chỉ cần diễn đạt **có hoặc không có một kết quả**, `Optional<T>` hoặc `OptionalLong` có thể phù hợp:

```java
import java.util.Optional;

Optional<MoneyVnd> fee = calculateShippingFee(order);

if (fee.isPresent()) {
    showFee(fee.get());
} else {
    showFeeNotAvailable();
}
```

Nhưng nếu nghiệp vụ cần phân biệt **chưa tính**, **không hỗ trợ** và **lỗi tạm thời**, `Optional.empty()` vẫn thiếu thông tin. Có thể tạo kết quả riêng có tên:

```java
sealed interface ShippingFeeResult
        permits FeeCalculated, UnsupportedDestination, FeeUnavailable {}

record FeeCalculated(MoneyVnd fee) implements ShippingFeeResult {}
record UnsupportedDestination(String region) implements ShippingFeeResult {}
record FeeUnavailable(String reason) implements ShippingFeeResult {}
```

Cú pháp `sealed interface` và `record` sử dụng được trong Java 17. Với kết quả này, từng trạng thái có kiểu riêng. Cần chọn cách biểu diễn phù hợp với phiên bản Java và khả năng xử lý của ứng dụng.

**Không nên biến mọi lỗi hạ tầng thành trạng thái nghiệp vụ bình thường.** Ví dụ timeout hệ thống có thể cần exception hoặc kiểu lỗi vận hành riêng; chỉ chọn kiểu kết quả khi người gọi có trách nhiệm xử lý tình huống đó theo hợp đồng.

## 11. Kiểu phù hợp giúp giảm trạng thái không thể xảy ra

Một mô hình yếu có thể lưu nhiều cờ:

```java
record PaymentFlags(
        boolean paid,
        boolean failed,
        boolean pending
) {}
```

Ba cờ boolean tạo tới tám tổ hợp, trong khi nghiệp vụ có thể chỉ có ba trạng thái loại trừ nhau. Những tổ hợp như `paid = true` và `failed = true` khiến người đọc phải đoán ưu tiên xử lý.

Một `PaymentStatus` duy nhất xóa được các tổ hợp không hợp lệ này ngay ở mô hình. Nếu trạng thái cần mang theo dữ liệu khác nhau, các kiểu con như `PendingPayment`, `PaidPayment(captureId)` và `FailedPayment(reason)` có thể phù hợp hơn.

Về mặt tư duy, hãy hỏi: **“Có bao nhiêu cách tạo ra trạng thái mà nghiệp vụ nói là không thể có?”** Nếu con số lớn, nên xem liệu mô hình dữ liệu đang biểu diễn quá nhiều tổ hợp vô nghĩa hay không.

Tuy vậy, không nên mô hình hóa quá mức. Một biến boolean như `isArchived` vẫn hợp lý khi nó là thuộc tính hai trạng thái độc lập, có ý nghĩa rõ. Việc thêm hàng loạt lớp kiểu chỉ để tránh `boolean` có thể làm tăng độ phức tạp mà không bảo vệ thêm bất biến.

## 12. Ràng buộc dữ liệu ở database và bảo vệ cạnh tranh

Mô hình Java bảo vệ các đối tượng được tạo theo đường đi bình thường, nhưng hệ thống còn có dữ liệu nhập từ migration, batch job, script, dịch vụ khác hoặc phiên bản cũ của ứng dụng. Nếu quy tắc quan trọng với dữ liệu lưu trữ, cần cân nhắc thêm ràng buộc ở database.

Ví dụ minh họa:

```sql
CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    product_id VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_vnd BIGINT NOT NULL,
    CONSTRAINT chk_quantity_positive CHECK (quantity > 0),
    CONSTRAINT chk_unit_price_non_negative CHECK (unit_price_vnd >= 0)
);
```

Những ràng buộc này ngăn một số dữ liệu sai đi vào bảng bất kể đường ghi. Tùy hệ quản trị, còn có `UNIQUE` cho khóa nghiệp vụ, `FOREIGN KEY` cho liên kết, `NOT NULL` và các cơ chế khác.

Nhưng database constraint cũng không thể thay tất cả chính sách nghiệp vụ:

- Điều kiện “số lượng tối đa 100” có thể phụ thuộc từng sản phẩm hoặc khách hàng.
- Bảo vệ “không bán vượt tồn kho” thường cần câu lệnh cập nhật có điều kiện, khóa hoặc transaction phù hợp khi có cạnh tranh.
- Kiểm tra số tiền bằng loại tiền và quy tắc làm tròn cần mô hình rõ, không chỉ một cột số.
- Thông tin từ dịch vụ bên ngoài có thể không nằm trong cùng transaction database.

Một giá trị hợp lệ **đơn lẻ** không có nghĩa cả phép cập nhật **nhiều thực thể** sẽ nhất quán. Kiểu, bất biến, transaction và kiểm soát đồng thời bổ sung cho nhau.

## 13. Chọn mức mô hình hóa vừa đủ theo rủi ro

Không phải giá trị nào cũng cần thành một lớp riêng. Có thể chọn mức biểu đạt phù hợp với chi phí thay đổi và nguy cơ lỗi.

| Tình huống | Giải pháp thường đủ | Khi nào nâng mức mô hình |
| --- | --- | --- |
| Một phép cộng đếm vòng lặp | `int`, tên biến rõ | Nếu xuất hiện quy tắc miền cụ thể cần bảo vệ |
| Timeout API | `Duration` | Khi có chính sách timeout theo từng loại tác vụ |
| Tiền trong ứng dụng chỉ dùng VND nguyên đồng | `long amountVnd` hoặc `MoneyVnd` | Khi nhiều hàm truyền tiền, cần bất biến/phép tính chung |
| Tiền đa loại | `Currency` + `BigDecimal` trong kiểu miền | Khi có quy đổi, làm tròn, nhiều loại bút toán |
| Trạng thái cố định | `enum` | Khi trạng thái mang dữ liệu hoặc hành vi phức tạp riêng |
| ID dễ truyền nhầm | `OrderId`, `UserId` | Khi ranh giới lớn, nhiều điểm gọi hoặc rủi ro cao |
| Danh sách cần luôn hợp lệ | Bản sao bất biến hoặc API thao tác có kiểm tra | Khi có thay đổi theo vòng đời và cạnh tranh |
| Giá trị tùy chọn | `Optional` | Khi cần nhiều trạng thái vắng mặt khác nhau |

Mỗi kiểu miền mới tạo thêm chi phí chuyển đổi dữ liệu, tích hợp thư viện, serialization và học khái niệm. Hãy chọn kiểu khi nó thực sự làm rõ khái niệm, ngăn nhầm lẫn hoặc tập trung quy tắc quan trọng.

Một chỉ báo hữu ích: nếu một quy tắc phải được nhắc lại ở nhiều chỗ, khó phát hiện khi sửa hoặc thường bị vi phạm, đưa nó thành bất biến tập trung có thể giảm tổng chi phí bảo trì.

## 14. Refactor kiểu dữ liệu mà không làm đổi hành vi ngoài ý muốn

Giả sử hệ thống hiện dùng:

```java
long price = 25_000;
int quantity = 2;
long total = price * quantity;
```

Bạn muốn chuyển sang `MoneyVnd` và `Quantity`. Nên thực hiện có kiểm soát:

1. **Xác nhận hợp đồng cũ:** giá tính bằng đơn vị gì, có cho phép số âm không, số lượng có cho phép 0 không, có giới hạn trên không.
2. **Ghi lại ca biên:** số lượng 0, âm, lớn nhất; giá 0; nhân tràn `long`; dữ liệu thiếu hoặc sai kiểu từ API.
3. **Tạo kiểu mới với ràng buộc đã xác nhận:** tránh tự thêm quy tắc vì “có vẻ hợp lý” nhưng chưa được nghiệp vụ đồng ý.
4. **Chuyển đổi ở ranh giới:** DTO hoặc tầng lưu trữ vẫn có thể dùng số nguyên trong giai đoạn đầu, chuyển sang kiểu miền khi đi vào xử lý nghiệp vụ.
5. **Thay từng điểm gọi:** loại bỏ phép tính thô ở nơi đã có thao tác `MoneyVnd.multiply` hoặc `OrderLine.lineTotal`.
6. **Kiểm thử lại hành vi:** đặc biệt chú ý khác biệt giữa overflow bị bỏ qua trước đây và overflow giờ ném ngoại lệ; đây có thể là thay đổi có chủ ý nhằm ngăn dữ liệu sai.
7. **Xóa đường biểu diễn cũ khi không còn dùng:** tránh hai cách tính tiền song song dẫn tới sai khác.

Ví dụ JUnit 5 kiểm tra các ràng buộc chính:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OrderLineTest {
    @Test
    void calculatesTotalUsingVnd() {
        OrderLine line = new OrderLine(
                "sku-123",
                new Quantity(2),
                new MoneyVnd(25_000)
        );

        assertEquals(new MoneyVnd(50_000), line.lineTotal());
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class, () -> new Quantity(0));
        assertThrows(IllegalArgumentException.class, () -> new Quantity(101));
    }

    @Test
    void rejectsOverflowInsteadOfProducingWrongTotal() {
        OrderLine line = new OrderLine(
                "sku-123",
                new Quantity(2),
                new MoneyVnd(Long.MAX_VALUE)
        );

        assertThrows(ArithmeticException.class, line::lineTotal);
    }
}
```

Những test này bảo vệ hành vi cục bộ. Với dữ liệu lưu trữ và nhiều yêu cầu đồng thời, cần thêm test tích hợp cho constraint, transaction và cập nhật cạnh tranh; một unit test trên record không chứng minh được tính nhất quán toàn hệ thống.

## 15. Tình huống vận dụng

### Tình huống A: phí vận chuyển theo cân nặng

Một API nhận `weight = 1_500` và bảng giá ghi “20.000 đồng mỗi kilogram”. Bạn không biết `weight` là gram hay kilogram.

Hãy đề xuất tên hoặc kiểu biểu đạt khối lượng, điểm chuyển đổi đơn vị, quy tắc làm tròn cân nặng tính phí và các test biên. Chú ý rằng phép chia nguyên `1500 / 1000` cho kết quả `1`, có thể sai nếu chính sách tính tròn lên 2 kg.

### Tình huống B: giảm giá với nhiều loại tiền

Một đơn có `amount = 100` và `currency = "USD"`; một voucher ghi `discount = 50` nhưng thiếu loại tiền.

Hãy xác định ràng buộc cần có trước khi trừ, cách biểu diễn loại tiền, xử lý sai khác currency và quy tắc làm tròn. Không nên trừ 50 một cách mù quáng hoặc mặc định voucher cùng loại tiền.

### Tình huống C: cập nhật trạng thái đơn

DTO lưu ba cờ `isPaid`, `isCancelled`, `isShipped`. Một bản ghi có cả `isCancelled` và `isShipped` là `true`, trong khi chính sách nói đơn hủy không thể giao.

Hãy chọn mô hình trạng thái phù hợp, xác định chuyển trạng thái được phép và nơi thực thi ràng buộc nếu có nhiều worker cập nhật đồng thời.

### Tình huống D: thời hạn khuyến mãi

Khuyến mãi có hiệu lực đến **hết ngày 31/12** theo giờ của từng thị trường. Hệ thống đang lưu `expiresAt = "2026-12-31"` rồi so sánh trực tiếp với timestamp UTC.

Hãy xác định những dữ liệu đang thiếu, cách chuyển một ngày lịch sang mốc thời gian theo múi giờ và lý do điều kiện giới hạn trên nên được viết rõ là bao gồm hay loại trừ.

### Tình huống E: tìm khách hàng không thấy kết quả

Hàm trả `customerLevel = -1` khi không tìm thấy, `0` khi khách mới và số dương cho khách thân thiết. Nhóm khác muốn thêm trạng thái “không được phép xem”.

Hãy chọn một kiểu kết quả phân biệt không tìm thấy, không được phép và cấp độ 0 hợp lệ; giải thích tại sao một con số sentinel không đủ.

Với mỗi tình huống, hãy trả lời bằng ba bước: **giá trị là gì**, **đơn vị và miền hợp lệ là gì**, **nơi nào chịu trách nhiệm giữ quy tắc đúng**.

## 16. Ghi nhớ

Kiểu dữ liệu, đơn vị và ràng buộc miền giá trị là một phần của thiết kế, không chỉ là chi tiết khai báo biến.

- Kiểu nguyên thủy mô tả cách lưu; kiểu miền giúp diễn đạt ý nghĩa và ràng buộc quan trọng.
- Hai giá trị cùng là `long` có thể mang đơn vị và ngữ nghĩa hoàn toàn khác; làm rõ đơn vị trước khi tính.
- Dùng `Duration`, `Instant`, `LocalDate`, `Currency`, `BigDecimal` hoặc kiểu miền khi chúng khớp bài toán.
- Đặt các bất biến chắc chắn ở điểm tạo và thay đổi dữ liệu, nhưng để quy tắc phụ thuộc bối cảnh ở nơi có đủ thông tin.
- Dùng `enum` hoặc các kiểu kết quả có tên để tránh trạng thái mơ hồ và những tổ hợp boolean vô nghĩa.
- Bảo vệ dữ liệu mutable, ranh giới nhập và quy tắc lưu trữ; đối tượng hợp lệ không thay thế kiểm soát đồng thời.
- Giữ khả năng đọc và thay đổi bằng cách chọn mức mô hình hóa tương xứng với rủi ro, không tạo kiểu chỉ vì có thể.

Khi tên, kiểu, đơn vị và ràng buộc cùng diễn đạt đúng khái niệm nghiệp vụ, người đọc ít phải đoán hơn, trình biên dịch và validation bắt được nhiều sai sót hơn, và thay đổi mã dễ được kiểm chứng hơn.

