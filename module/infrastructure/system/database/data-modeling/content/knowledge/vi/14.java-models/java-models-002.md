# Tạo đối tượng giá trị cho định danh, tiền tệ, đại lượng và khoảng thời gian

Trong một hệ thống nghiệp vụ, `UUID`, `BigDecimal`, `String` và `Instant` là các kiểu Java hữu ích nhưng chưa nói đủ **giá trị đó có nghĩa gì**. Cùng là `UUID`, mã đơn hàng không được dùng nhầm làm mã khách hàng. Cùng là `BigDecimal`, số tiền 100 USD không thể cộng trực tiếp với 100 VND, còn 5 kg không thể cộng với 5 mét. Cùng là hai mốc thời gian, một khoảng đặt chỗ cần quy tắc rõ ràng về đầu mút và múi giờ.

**Đối tượng giá trị (value object)** giúp đưa những ý nghĩa và ràng buộc ấy vào mô hình Java. Bài học thuộc chương **Mô hình Java** của module **DATABASE_DATA_MODELING**: rèn kỹ năng chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, ràng buộc, khóa, chỉ mục và lược đồ vật lý; so sánh cách mô hình hóa cho dữ liệu quan hệ, document, đồ thị và phân tích. Ta sẽ thiết kế bốn nhóm value object rồi xem cách giữ nguyên ngữ nghĩa của chúng khi đi qua API và cơ sở dữ liệu.

## 1. Value object là gì và khác entity như thế nào?

Value object được xác định bằng **giá trị và ý nghĩa của các thành phần bên trong**, thay vì danh tính độc lập của chính đối tượng. Hai đối tượng biểu diễn cùng 20,00 USD được xem là cùng giá trị, bất kể chúng được tạo ở đâu. Ngược lại, hai đơn hàng có cùng tổng tiền và ngày tạo vẫn là hai thực thể khác nhau nếu chúng mang mã đơn khác nhau.

| Khía cạnh | Value object | Entity |
| --- | --- | --- |
| Định nghĩa bình đẳng | Bằng nhau khi các thành phần có ý nghĩa bằng nhau | Cùng danh tính nghiệp vụ, kể cả khi thuộc tính thay đổi |
| Vòng đời | Có thể tạo lại và thay thế bằng giá trị mới | Có danh tính và vòng đời cần được theo dõi |
| Thay đổi | Ưu tiên bất biến; thao tác tạo ra giá trị mới | Thay đổi trạng thái qua hành vi được kiểm soát |
| Ví dụ | `OrderId`, `Money`, `Quantity`, `TimeWindow` | `Order`, `Customer`, `Reservation` |
| Ánh xạ dữ liệu | Thường trải trên một hoặc nhiều cột/thuộc tính của entity | Thường gắn với khóa chính và quan hệ giữa các thực thể |

Lưu ý: **`OrderId` là value object**, nhưng **`Order` là entity**. Mã đơn là một giá trị đại diện cho danh tính của entity; bản thân đối tượng Java chứa mã không có vòng đời độc lập. Một đối tượng giá trị có thể được lưu cùng entity hoặc truyền qua API mà không cần bảng và khóa chính riêng.

Thiết kế tốt thường có các tính chất:

1. **Ngữ nghĩa rõ:** tên kiểu và trường mô tả được miền giá trị, đơn vị và ranh giới sử dụng.
2. **Hợp lệ ngay khi tạo:** constructor/factory từ chối giá trị vô nghĩa; không tạo đối tượng “tạm sai” rồi mong nơi khác sửa.
3. **Bất biến:** không có setter; các thao tác `plus`, `multiply` hoặc `shift` trả về giá trị mới.
4. **Bình đẳng theo giá trị:** cách chuẩn hóa dữ liệu bảo đảm hai cách biểu diễn tương đương được so sánh đúng.
5. **Tương thích lưu trữ:** có cách chuyển đổi rõ ràng sang cột SQL, JSON hoặc dạng dữ liệu khác mà vẫn giữ ràng buộc.

Java 17+ có `record` rất tiện cho value object vì sinh accessor, constructor chuẩn, `equals`/`hashCode` và `toString`. Tuy nhiên, `record` **chỉ bất biến nông**; các thành phần chứa danh sách, mảng hoặc đối tượng mutable vẫn cần sao chép phòng vệ. Nếu cần chính sách tạo đặc biệt, hiệu năng hoặc tương thích framework, có thể dùng `final class` với trường `private final` và tự viết bình đẳng.

## 2. Từ yêu cầu nghiệp vụ đến bốn kiểu giá trị

Giả sử ứng dụng nhận một yêu cầu đặt chỗ và tính tiền:

- Một đơn hàng và một khách hàng đều có mã UUID, nhưng không được truyền nhầm cho nhau.
- Giá cần có **số tiền và loại tiền**, với chính sách làm tròn được chỉ định.
- Số lượng cần có **giá trị số và đơn vị đo**, đồng thời không được cộng đại lượng khác thứ nguyên.
- Suất đặt chỗ có **thời điểm bắt đầu và kết thúc**, không được rỗng và phải kiểm tra được trùng lặp.

| Khái niệm nghiệp vụ | Biểu diễn yếu | Value object đề xuất | Bất biến tiêu biểu |
| --- | --- | --- | --- |
| Mã đơn | `String` hoặc `UUID` dùng chung khắp nơi | `OrderId(UUID)` | UUID không `null`; loại mã khác nhau không thể hoán đổi |
| Số tiền | `double` hoặc `BigDecimal` đứng một mình | `Money(BigDecimal, Currency)` | Cùng tiền tệ mới cộng; số chữ số thập phân phù hợp chính sách |
| Số lượng | `double quantity` | `Quantity(BigDecimal, Unit)` | Đơn vị bắt buộc; quy tắc số lượng âm/0 rõ ràng |
| Khoảng thời gian | Hai `LocalDateTime` rời rạc | `TimeWindow(Instant, Instant)` | Bắt đầu sớm hơn kết thúc; thống nhất quy tắc bao gồm đầu mút |

Trong chương này, tên field của record là một phần ngữ nghĩa: `startInclusive` và `endExclusive` cung cấp nhiều thông tin hơn `from` và `to` vốn mơ hồ.

## 3. Ví dụ Java 17+ đầy đủ, có thể chạy

Lưu đoạn sau vào `ValueObjectDemo.java`. Các record đặt trong cùng lớp để dễ chạy minh họa. Trong dự án thực tế, mỗi kiểu có thể nằm trong tệp riêng, theo package của miền nghiệp vụ.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.Instant;
import java.util.Currency;
import java.util.Objects;
import java.util.UUID;

public final class ValueObjectDemo {

    record OrderId(UUID value) {
        public OrderId {
            Objects.requireNonNull(value, "value");
        }

        static OrderId parse(String raw) {
            return new OrderId(UUID.fromString(raw));
        }
    }

    record CustomerId(UUID value) {
        public CustomerId {
            Objects.requireNonNull(value, "value");
        }
    }

    record Money(BigDecimal amount, Currency currency) {
        public Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");

            int fractionDigits = currency.getDefaultFractionDigits();
            if (fractionDigits < 0) {
                throw new IllegalArgumentException(
                    "Currency has no defined minor unit: " + currency
                );
            }
            // Chuẩn hóa scale; không tự động làm tròn khi nhận dữ liệu.
            amount = amount.setScale(
                fractionDigits, RoundingMode.UNNECESSARY
            );
        }

        static Money of(String amount, String currencyCode) {
            return new Money(
                new BigDecimal(amount),
                Currency.getInstance(currencyCode)
            );
        }

        Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException(
                    "Cannot add different currencies"
                );
            }
            return new Money(amount.add(other.amount), currency);
        }

        Money times(BigDecimal factor, RoundingMode rounding) {
            Objects.requireNonNull(factor, "factor");
            Objects.requireNonNull(rounding, "rounding");
            BigDecimal calculated = amount.multiply(factor);
            int scale = currency.getDefaultFractionDigits();
            return new Money(calculated.setScale(scale, rounding), currency);
        }
    }

    enum Unit {
        PIECE, KILOGRAM, METER
    }

    record Quantity(BigDecimal value, Unit unit) {
        public Quantity {
            Objects.requireNonNull(value, "value");
            Objects.requireNonNull(unit, "unit");
            if (value.signum() < 0) {
                throw new IllegalArgumentException(
                    "Quantity must not be negative"
                );
            }

            // 2.500 và 2.5 đại diện cùng một đại lượng.
            value = value.signum() == 0
                ? BigDecimal.ZERO
                : value.stripTrailingZeros();
        }

        static Quantity of(String raw, Unit unit) {
            return new Quantity(new BigDecimal(raw), unit);
        }

        Quantity plus(Quantity other) {
            Objects.requireNonNull(other, "other");
            if (unit != other.unit) {
                throw new IllegalArgumentException(
                    "Cannot add different measurement units"
                );
            }
            return new Quantity(value.add(other.value), unit);
        }
    }

    record TimeWindow(Instant startInclusive, Instant endExclusive) {
        public TimeWindow {
            Objects.requireNonNull(startInclusive, "startInclusive");
            Objects.requireNonNull(endExclusive, "endExclusive");
            if (!startInclusive.isBefore(endExclusive)) {
                throw new IllegalArgumentException(
                    "Start must be earlier than end"
                );
            }
        }

        boolean contains(Instant instant) {
            Objects.requireNonNull(instant, "instant");
            return !instant.isBefore(startInclusive)
                && instant.isBefore(endExclusive);
        }

        boolean overlaps(TimeWindow other) {
            Objects.requireNonNull(other, "other");
            return startInclusive.isBefore(other.endExclusive)
                && other.startInclusive.isBefore(endExclusive);
        }

        Duration elapsed() {
            return Duration.between(startInclusive, endExclusive);
        }
    }

    public static void main(String[] args) {
        UUID rawId = UUID.randomUUID();
        OrderId orderId = new OrderId(rawId);
        CustomerId customerId = new CustomerId(rawId);
        // Dù cùng UUID, OrderId và CustomerId là hai kiểu khác nhau.
        System.out.println(orderId.value().equals(customerId.value())); // true

        Money base = Money.of("19.90", "USD");
        Money fee = Money.of("0.10", "USD");
        Money total = base.plus(fee);
        System.out.println(total.amount());                              // 20.00
        System.out.println(Money.of("10.0", "USD")
            .equals(Money.of("10.00", "USD")));                             // true

        Quantity cargo = Quantity.of("2.500", Unit.KILOGRAM);
        Quantity extra = Quantity.of("0.5", Unit.KILOGRAM);
        System.out.println(cargo.plus(extra).value());                   // 3

        TimeWindow first = new TimeWindow(
            Instant.parse("2026-11-22T01:00:00Z"),
            Instant.parse("2026-11-22T02:00:00Z")
        );
        TimeWindow next = new TimeWindow(
            first.endExclusive(),
            Instant.parse("2026-11-22T03:00:00Z")
        );
        System.out.println(first.overlaps(next));                        // false
        System.out.println(first.elapsed().toMinutes());                  // 60
    }
}
```

**Vì sao các constructor quan trọng?** Nếu ứng dụng có thể tạo `new TimeWindow(end, start)` hay `new Money(amount, null)` rồi mới kiểm tra ở tầng dịch vụ, đối tượng sai có thể đi vào những lớp khác. Constructor chuẩn của record biến ràng buộc thành điều kiện bắt buộc tại mọi điểm tạo trực tiếp, kể cả khi đối tượng sinh từ phép tính.

Các phương thức `plus` đều tạo **đối tượng mới**. Lời gọi `base.plus(fee)` không thay đổi `base`. Tính bất biến này giúp việc truyền giá trị giữa các phương thức và luồng xử lý dễ dự đoán hơn.

## 4. Đối tượng định danh: chống nhầm khóa mà không làm mất danh tính

Một lỗi thường gặp là khai báo:

```java
void transferOrder(UUID orderId, UUID customerId) { /* ... */ }
```

Trình biên dịch không phát hiện lời gọi đảo hai UUID. Nếu dùng hai kiểu khác nhau:

```java
final class TransferService {
    void transferOrder(ValueObjectDemo.OrderId orderId,
                       ValueObjectDemo.CustomerId customerId) {
        /* ... */
    }
}
```

Thì một `CustomerId` không thể truyền vào tham số `OrderId`. Các kiểu trong ví dụ được để cùng package nhằm minh họa cú pháp; trong ứng dụng, cần thiết kế phạm vi truy cập và package phù hợp.

**Quy tắc cho định danh:**

- Bọc giá trị nguyên thủy bằng đúng kiểu nghiệp vụ: `OrderId`, `CustomerId`, `ReservationId`. Không dùng lại một lớp `Id` chung cho mọi loại thực thể nếu điều đó làm mất sự phân biệt.
- Phân biệt **định danh nội bộ** và **mã hiển thị**: UUID có thể là khóa chính, còn mã đơn dạng `ORD-2026-000042` có thể là trường nghiệp vụ riêng cần tính duy nhất. Mã hiển thị có thể thay đổi quy tắc mà không nhất thiết đổi khóa.
- Factory `parse` là biên chuyển đổi từ chuỗi API sang kiểu mạnh. Xử lý lỗi chuỗi UUID không hợp lệ ở biên bằng thông báo phù hợp; không để exception thấp tầng rò vào thông điệp công khai.
- Hai value object `new OrderId(sameUuid)` có `equals` bằng nhau; nhưng hai kiểu `OrderId` và `CustomerId` là hai miền khác nhau dù bọc cùng UUID.
- Định danh không phải mật khẩu hay quyền truy cập: biết ID không được tự động cấp quyền đọc/sửa dữ liệu. Kiểm tra phân quyền vẫn bắt buộc ở tầng ứng dụng.

Trong cơ sở dữ liệu quan hệ, khóa chính `orders.id UUID PRIMARY KEY` bảo đảm duy nhất, còn khóa ngoại ở bảng liên quan bảo đảm tham chiếu hợp lệ. Trình biên dịch Java giúp tránh nhầm loại mã trong code, nhưng **không thể thay thế khóa ngoại và ràng buộc duy nhất** trên database.

## 5. Đối tượng tiền tệ: số tiền, đơn vị tiền và phép làm tròn

`Money` cần ít nhất hai thành phần: **`amount`** và **`currency`**. Không được viết `Money(100)` rồi ngầm hiểu USD hay VND. Mỗi nghiệp vụ phải xác định số tiền đó là giá, thuế, giảm giá, số dư, khoản hoàn tiền hay tỷ giá.

### Chọn `BigDecimal` thay vì số thực nhị phân

`double` không thể biểu diễn chính xác nhiều phân số thập phân; tính toán liên tiếp có thể tạo sai số không mong muốn. Với số tiền, hãy nhập từ chuỗi hoặc biểu diễn thập phân có kiểm soát:

```java
import java.math.BigDecimal;

final class DecimalExample {
    void illustrate() {
        BigDecimal correct = new BigDecimal("0.10");
        // Cách dưới đây giữ xấp xỉ nhị phân của double:
        BigDecimal risky = new BigDecimal(0.10);
    }
}
```

Phép cộng/trừ có thể được thực hiện trực tiếp bằng `BigDecimal`; phép chia và nhân sinh nhiều chữ số cần chính sách làm tròn minh bạch. Ví dụ `Money.times(factor, RoundingMode.HALF_EVEN)` buộc caller chỉ định quy tắc làm tròn tại nơi phép tính có thể mất độ chính xác.

### Chuẩn hóa và bình đẳng

`BigDecimal("10.0").equals(BigDecimal("10.00"))` trả `false` vì `equals` xét cả **scale**, mặc dù `compareTo` xem chúng bằng nhau. `record` tự sinh `equals` từ các component nên nếu không chuẩn hóa, hai khoản tiền tương đương có thể bị so sánh khác.

Ví dụ `Money` dùng `currency.getDefaultFractionDigits()` để chuẩn hóa số chữ số thập phân của đơn vị tiền:

| Giá trị nhập | Tiền tệ | Kết quả với mô hình ví dụ |
| --- | --- | --- |
| `"10.0"` | USD (2 chữ số lẻ) | `10.00` |
| `"10.00"` | USD | `10.00`; bằng giá trị phía trên |
| `"10.001"` | USD | Bị từ chối do phải làm tròn mà chưa có chính sách |
| `"2500"` | VND (0 chữ số lẻ) | `2500` |
| `"2500.5"` | VND | Bị từ chối trong chính sách này |

Đây là **chính sách minh họa cho giá trị tiền đã chốt thanh toán**. Trong thực tế, đơn giá theo trọng lượng, giá điện, thuế suất hoặc tỷ giá có thể cần nhiều chữ số hơn đơn vị tiền nhỏ nhất. Khi đó nên dùng các kiểu/phân lớp riêng như `UnitPrice`, `ExchangeRate` hay `TaxRate`, giữ độ chính xác nội bộ phù hợp và chỉ làm tròn ở bước nghiệp vụ được quy định. Không dùng một quy tắc scale chung cho mọi loại số có liên quan đến tiền.

### Các bất biến phụ thuộc ngữ cảnh

- **Không cộng khác tiền tệ:** `Money(10 USD) + Money(10 EUR)` phải lỗi hoặc đi qua quy trình quy đổi rõ ràng. Quy đổi cần tỷ giá, nguồn, thời điểm hiệu lực và chính sách làm tròn; không thể tự lấy một tỷ giá “mặc định” từ hai mã tiền.
- **Không mặc định chặn số âm trong mọi `Money`:** số âm có thể hợp lệ cho bút toán điều chỉnh hoặc hoàn tiền. Nhưng `ProductPrice` và `AmountToPay` có thể cần ràng buộc `>= 0` riêng.
- **Phân biệt tính toán và phân bổ:** chia 10,00 USD cho 3 người cần một quy tắc phân bổ đồng xu còn dư; chỉ làm tròn ba kết quả độc lập có thể khiến tổng khác 10,00 USD. Đơn vị tiền nhỏ nhất phải được bảo toàn theo chính sách đối soát.
- **Không dùng `ordinal` của enum hoặc số nguyên tùy ý để biểu diễn tiền tệ:** nên lưu mã ISO 4217 hoặc mã miền ổn định theo yêu cầu và xác thực tập mã hỗ trợ.

## 6. Đối tượng đại lượng: giá trị số luôn đi cùng đơn vị

`Quantity(BigDecimal, Unit)` thể hiện rằng **3** chỉ có ý nghĩa khi đi cùng đơn vị. Phép tính chỉ hợp lệ khi hai toán hạng cùng đơn vị và cùng ý nghĩa.

```text
2.5 KILOGRAM + 0.5 KILOGRAM = 3 KILOGRAM
2.5 KILOGRAM + 0.5 METER    = không hợp lệ
```

Trong ví dụ, `Quantity.plus` chỉ cộng khi `unit` giống nhau. Nếu hệ thống hỗ trợ thêm `GRAM`, việc `500 GRAM + 1 KILOGRAM` phải đi qua **hàm chuyển đổi có kiểm soát**, sau khi xác nhận cùng thứ nguyên khối lượng; không chỉ so sánh tên chuỗi. Quy đổi nên chỉ rõ hệ số, độ chính xác và đơn vị kết quả.

**Giới hạn theo miền nghiệp vụ:**

- `Quantity` tổng quát trong ví dụ cho phép `0` vì tồn kho bằng 0 là hợp lệ. `OrderLineQuantity` có thể yêu cầu `> 0`.
- Số lượng **cái** thường phải là số nguyên; `Quantity(2.5, PIECE)` chỉ hợp lệ nếu nghiệp vụ cho phép hàng lẻ. Nếu không, hãy thêm ràng buộc theo đơn vị hoặc định nghĩa kiểu riêng như `PieceCount`.
- Số lượng âm có thể có ý nghĩa trong **biến động tồn kho**; hãy mô hình `StockDelta` tách khỏi `StockOnHand` thay vì nới lỏng mọi `Quantity`.
- Khi đo lường, `2.50 kg` và `2.5 kg` có thể bằng nhau về **độ lớn**, nhưng khác nhau về **độ chính xác được công bố**. Ví dụ chuẩn hóa bằng `stripTrailingZeros()` cố ý bỏ thông tin số chữ số có nghĩa; nếu thông tin này quan trọng, cần lưu thêm metadata độ chính xác/thiết bị đo.

Không phải tất cả đơn vị đều quy đổi bằng một phép nhân: nhiệt độ Celsius/Fahrenheit có điểm gốc khác nhau; tỉ lệ phần trăm, thời lượng và số đếm cũng có quy tắc riêng. Hãy đặt phép toán ở kiểu đại lượng hoặc dịch vụ chuyển đổi thích hợp, không dùng một `Unit` duy nhất vô hạn trách nhiệm.

## 7. Đối tượng khoảng thời gian: mốc tuyệt đối và đầu mút nửa mở

Thiết kế `TimeWindow(startInclusive, endExclusive)` dùng quy ước **[bắt đầu, kết thúc)**: bao gồm thời điểm bắt đầu, loại trừ thời điểm kết thúc.

```text
A = [08:00, 09:00)
B = [09:00, 10:00)
A và B kề nhau nhưng KHÔNG chồng lấn.

C = [08:30, 09:30)
A và C CÓ chồng lấn.
```

Với quy ước này, `contains` trả `true` tại `startInclusive` và `false` tại `endExclusive`. Công thức chồng lấn đối với hai khoảng **không rỗng** là:

\[
A_{\text{start}} < B_{\text{end}}
\quad\land\quad
B_{\text{start}} < A_{\text{end}}
\]

Đây là điều kiện đang dùng trong `overlaps`. Nếu cho phép khoảng rỗng (`start == end`), công thức và ý nghĩa kiểm tra cần xem xét lại, nên ví dụ từ chối ngay tại constructor.

### Chọn kiểu thời gian đúng với câu hỏi nghiệp vụ

| Câu hỏi | Kiểu Java thường phù hợp | Ghi chú |
| --- | --- | --- |
| “Sự kiện diễn ra chính xác lúc nào?” | `Instant` | Một mốc trên dòng thời gian; phù hợp lưu và so sánh thời điểm tuyệt đối |
| “Người dùng đặt lịch 09:00 tại Hà Nội?” | `LocalDateTime` cùng `ZoneId` | Phải giải quyết thành mốc tuyệt đối khi xác nhận lịch |
| “Ngày nghỉ 22/11/2026?” | `LocalDate` | Ngày lịch, không tự gắn UTC hoặc một giờ cụ thể |
| “Khoảng cách giữa hai thời điểm?” | `Duration` | Thời lượng tuyệt đối tính theo giây/nano |
| “Cộng một tháng theo lịch?” | `Period` hoặc phép tính ngày theo múi giờ | Tháng không có số giờ cố định |

`LocalDateTime` **không chứa múi giờ** và không xác định duy nhất một `Instant`. Khi lưu lịch hẹn theo giờ địa phương, phải biết `ZoneId`; múi giờ có chuyển giờ mùa hè có thể có giờ không tồn tại hoặc bị lặp. Một ngày theo giờ địa phương cũng không nhất thiết dài 24 giờ tuyệt đối ở mọi nơi. Nếu cần lịch lặp “09:00 mỗi thứ Hai”, hãy lưu quy tắc lịch địa phương và `ZoneId`, không chỉ cộng `Duration.ofDays(7)` vào lần chạy trước trong mọi trường hợp.

Ví dụ chuyển thời điểm UTC thành giờ địa phương Việt Nam:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

final class TimeZoneExample {
    static void show() {
        Instant point = Instant.parse("2026-11-22T02:00:00Z");
        ZonedDateTime local = point.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println(local);
        // 2026-11-22T09:00+07:00[Asia/Ho_Chi_Minh]
    }
}
```

Lưu ý `TimeWindow` biểu diễn khoảng giữa hai **thời điểm đã xác định**, còn quy tắc lịch lặp và “giờ làm việc” theo múi giờ là những khái niệm khác; đừng ép tất cả thành hai `Instant` nếu cần tái lập lịch trong tương lai.

## 8. Bất biến và bình đẳng: những cạm bẫy của `record`

Một `record` chỉ ngăn gán lại các trường thành phần, không biến đối tượng bên trong thành bất biến. Ví dụ:

```java
import java.util.List;
import java.util.Objects;

record SelectedTags(List<String> values) {
    public SelectedTags {
        Objects.requireNonNull(values, "values");
        values = List.copyOf(values);
    }
}
```

`List.copyOf` giúp ngăn việc sửa danh sách qua tham chiếu bên ngoài và tạo danh sách không cho sửa cấu trúc, đồng thời từ chối phần tử `null`. Nếu phần tử là đối tượng mutable, vẫn cần thiết kế sao chép sâu hoặc kiểu phần tử bất biến. Mảng `byte[]` có thêm vấn đề: so sánh của mảng mặc định theo tham chiếu, vì vậy `record Payload(byte[] data)` không tự có `equals` theo nội dung.

**Điểm cốt lõi với giá trị số** là định nghĩa chính xác “bằng nhau”:

- `Money` chuẩn hóa `BigDecimal` theo chữ số thập phân của tiền tệ. Cùng số tiền và tiền tệ thì bằng nhau theo record.
- `Quantity` chuẩn hóa bằng `stripTrailingZeros` để `2.500 kg` bằng `2.5 kg`. Nếu độ chính xác của phép đo có ý nghĩa nghiệp vụ, không dùng ngữ nghĩa bình đẳng ấy một cách mù quáng.
- `TimeWindow` bằng nhau khi hai mốc `Instant` bằng nhau; hai cách viết giờ địa phương mô tả cùng thời điểm tuyệt đối có thể quy về cùng `Instant`.
- `OrderId` bằng nhau khi UUID bên trong bằng nhau, nhưng bình đẳng của mã không biến hai đối tượng `Order` thành một cấu trúc có cùng mọi thuộc tính.

Không xây dựng value object với trường mutable làm khóa của `HashMap` hoặc phần tử của `HashSet` rồi thay đổi những trường có tham gia `hashCode`. Đây là một lý do thiết kế value object bất biến.

## 9. Ánh xạ value object sang lược đồ dữ liệu

Giá trị Java không bắt buộc phải có bảng riêng. Trong mô hình quan hệ, value object thường được **flatten** thành các cột của entity; khi đọc lại, adapter/repository tái tạo value object và chạy các kiểm tra hợp lệ.

Ví dụ một phần schema đặt chỗ trong PostgreSQL:

```sql
CREATE TABLE reservations (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    total_amount NUMERIC(20, 4) NOT NULL,
    total_currency VARCHAR(3) NOT NULL,
    reserved_quantity NUMERIC(20, 6) NOT NULL,
    quantity_unit VARCHAR(16) NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT ck_total_nonnegative CHECK (total_amount >= 0),
    CONSTRAINT ck_quantity_positive CHECK (reserved_quantity > 0),
    CONSTRAINT ck_window_nonempty CHECK (starts_at < ends_at),
    CONSTRAINT ck_unit CHECK (
        quantity_unit IN ('PIECE', 'KILOGRAM', 'METER')
    )
);
```

Các cột `id` và `customer_id` đều là UUID ở tầng lưu trữ nhưng ánh xạ về những kiểu Java khác nhau: `ReservationId` và `CustomerId`. Trong hệ thống thực tế, `customer_id` cần khóa ngoại tới bảng khách hàng nếu quan hệ được quản lý bởi database. `NUMERIC` giúp giữ số thập phân chính xác trong giới hạn precision/scale đã cấu hình, tránh sự sai lệch của kiểu số thực nhị phân.

**Những điều schema trên chưa tự bảo đảm:**

1. `NUMERIC(20,4)` và `NUMERIC(20,6)` là **quyết định độ chính xác lưu trữ**, không phải quy tắc chung cho mọi loại tiền/đại lượng. Ví dụ này có thể cần điều chỉnh nếu yêu cầu giá nhiều chữ số hơn hoặc đại lượng có độ phân giải cao hơn.
2. `total_currency VARCHAR(3)` chưa chắc là mã tiền hợp lệ. Có thể dùng bảng tham chiếu tiền tệ, khóa ngoại và kiểm tra miền giá trị; luật scale theo từng mã tiền vẫn cần xác định ở nơi thích hợp.
3. `CHECK (starts_at < ends_at)` chặn khoảng rỗng/đảo ngược **trong một hàng** nhưng không ngăn hai hàng đặt chỗ cùng tài nguyên và chồng lấn. Cần ràng buộc chồng lấn chuyên biệt, giao dịch/khóa hoặc chiến lược đồng thời phù hợp. Hàm `TimeWindow.overlaps` trong Java không đủ bảo đảm an toàn khi nhiều tiến trình ghi đồng thời.
4. Kiểu `TIMESTAMPTZ` biểu diễn mốc thời gian tuyệt đối; không tự lưu tên múi giờ gốc của người dùng. Nếu cần diễn giải lịch địa phương hoặc hiển thị đúng múi giờ đã lựa chọn, lưu thêm `zone_id` riêng.
5. Không ép value object thành bảng lookup khi bản thân nó không có danh tính/vòng đời riêng. Ví dụ mỗi `Money` có một hàng chỉ để chứa số tiền thường làm tăng độ phức tạp. Trái lại, nếu `Unit` là danh mục cấu hình với mô tả, chuyển đổi, phiên bản và quản lý độc lập, bảng tham chiếu có thể hợp lý.

### JPA/Hibernate, JSON và các kiểu kho dữ liệu khác

Với **JPA**, một `record` không phù hợp làm entity chuẩn vì entity cần khả năng khởi tạo và quản lý trạng thái theo quy tắc của JPA. Đối với value object, có thể cân nhắc `@Embeddable` với kiểu được provider hỗ trợ hoặc `AttributeConverter` cho kiểu ánh xạ thành một cột. Khả năng map trực tiếp `record` dưới dạng embeddable phụ thuộc phiên bản JPA/provider; nếu chưa chắc, sử dụng class embeddable hoặc converter phù hợp và kiểm thử mapping. Không giả định mọi ORM đều tự hiểu `Currency`, `OrderId` hay `Quantity`.

Với **JSON/API**, nên truyền tên thuộc tính mang ngữ nghĩa, ví dụ:

```json
{
  "orderId": "b6e8be40-e148-4e31-80f4-efab7880a552",
  "total": { "amount": "19.90", "currency": "USD" },
  "quantity": { "value": "2.5", "unit": "KILOGRAM" },
  "timeWindow": {
    "startInclusive": "2026-11-22T01:00:00Z",
    "endExclusive": "2026-11-22T02:00:00Z"
  }
}
```

Chuỗi số thập phân giúp tránh việc client JavaScript biến tiền thành phép tính dấu phẩy động ngoài ý muốn. Khi nhận request, API phải phân tích dữ liệu, kiểm tra mã tiền/đơn vị, chuẩn hóa và bắt lỗi validation. Thêm hoặc đổi trường value object là **thay đổi hợp đồng API**, cần quy tắc tương thích và migration khi cần.

Trong **document database**, có thể lưu `total` và `quantity` dưới dạng object lồng nhau, nhưng vẫn cần tính đến tính nguyên tử khi cập nhật và kiểm tra dữ liệu. Trong **đồ thị**, value object thường trở thành thuộc tính của nút/cạnh thay vì một nút độc lập, trừ khi dữ liệu có quan hệ và vòng đời riêng. Trong **hệ phân tích**, nên giữ cả giá trị chuẩn hóa, mã đơn vị/tiền tệ, thời điểm hiệu lực và thông tin chuyển đổi cần thiết để không cộng gộp sai những đại lượng khác nhau.

## 10. Kiểm chứng bằng các trường hợp biên

Đối tượng giá trị đặc biệt cần được kiểm tra ở **biên miền giá trị**: nơi dễ xảy ra lỗi mà kiểu nguyên thủy không phát hiện.

| Trường hợp | Kết quả mong đợi | Lý do |
| --- | --- | --- |
| `new OrderId(null)` | Bị từ chối | Định danh không hợp lệ |
| `Money.of("10.0", "USD")` so với `Money.of("10.00", "USD")` | Bằng nhau | Cùng số tiền, chuẩn hóa scale |
| `Money.of("10.001", "USD")` | Bị từ chối | Chưa có chính sách làm tròn đầu vào |
| Cộng `10 USD` với `10 VND` | Bị từ chối | Khác tiền tệ |
| `Quantity.of("2.500", KILOGRAM)` so với `Quantity.of("2.5", KILOGRAM)` | Bằng nhau | Chuẩn hóa độ lớn |
| Cộng `2 KILOGRAM` với `2 METER` | Bị từ chối | Khác đơn vị |
| `TimeWindow(t, t)` hoặc `TimeWindow(later, earlier)` | Bị từ chối | Khoảng rỗng hoặc đảo đầu mút |
| `[08:00,09:00)` so với `[09:00,10:00)` | Không chồng lấn | Quy ước nửa mở |
| Hai đặt chỗ trùng tài nguyên được ghi đồng thời | Phải có cơ chế database bảo vệ | Kiểm tra riêng từng đối tượng không đủ |

Đừng chỉ kiểm tra constructor. Cần kiểm tra phép tính tạo giá trị mới, chuyển đổi API/database, thay đổi chuẩn dữ liệu và tình huống cập nhật đồng thời. Ví dụ, khi bổ sung đơn vị `GRAM`, phải có thử nghiệm rõ ràng cho đổi đơn vị và làm tròn.

## 11. Bài tập ứng dụng

Một cửa hàng cho khách đặt giao hàng theo khung giờ, có các yêu cầu:

1. Mỗi sản phẩm có `ProductId`, mỗi đơn có `OrderId`; cả hai được lưu thành UUID.
2. Giá niêm yết dùng VND, một số mặt hàng tính theo `KILOGRAM`, một số theo `PIECE`.
3. Cửa hàng chia khung giao hàng thành 09:00–10:00 và 10:00–11:00, tính theo giờ địa phương tại từng khu vực.
4. Chính sách có thể phát sinh giảm giá, hoàn tiền và điều chỉnh tồn kho.
5. Hệ thống phục vụ nhiều tiến trình xử lý đơn cùng lúc.

Hãy thực hiện:

- Xác định những value object và entity cần có; giải thích vì sao `ProductId` không thể truyền cho tham số `OrderId`.
- Đề xuất kiểu `Money`, `Price`, `Quantity`, `StockDelta` với ràng buộc âm/không âm, phần lẻ và tiền tệ phù hợp.
- Chọn dữ liệu cần lưu cho một khung giờ địa phương, cách chuyển thành `Instant` và cách xác định hai khung giờ kề nhau có trùng không.
- Thiết kế cột cơ sở dữ liệu cho giá, số lượng, đơn vị, múi giờ và khung thời gian; chỉ rõ validation ở Java, constraint ở database và phần cần kiểm soát đồng thời.
- Nêu một thay đổi nghiệp vụ (thêm ngoại tệ, thêm đơn vị, đổi độ chính xác hoặc thay đổi lịch) và mô tả tác động đến API, dữ liệu đã lưu và kiểm thử.

**Gợi ý đối chiếu:** `Product` và `Order` thường là entity; `ProductId` và `OrderId` là hai value object riêng. `Price` yêu cầu không âm nhưng `StockDelta` có thể âm. Khung giờ cần mốc thời gian và múi giờ theo địa điểm, cùng quy ước `[start,end)`. Kiểm tra Java bảo vệ nghĩa của một giá trị, còn tính duy nhất, khóa ngoại và cạnh tranh ghi phải được xử lý thêm tại database/giao dịch.

## 12. Checklist thiết kế trước khi lưu lược đồ

- [ ] Từng giá trị mang **tên kiểu và ý nghĩa nghiệp vụ**, không chỉ dùng `String`, `UUID` hoặc `BigDecimal` trần.
- [ ] Constructor/factory chặn `null`, miền số sai, đơn vị sai và khoảng thời gian không hợp lệ.
- [ ] Quy tắc `equals`/`hashCode` phản ánh **bình đẳng theo ý nghĩa**, kể cả sau chuẩn hóa `BigDecimal`.
- [ ] Giá trị bất biến thật sự; với các thành phần mutable đã sao chép hoặc chọn kiểu thay thế.
- [ ] Phép cộng, nhân, quy đổi và làm tròn có chính sách cụ thể; không trộn lẫn tiền tệ hay đơn vị khác loại.
- [ ] Đã tách `Instant` khỏi giờ địa phương và dùng quy ước đầu mút khoảng thời gian thống nhất.
- [ ] Ánh xạ Java ↔ API ↔ database giữ đủ thông tin tiền tệ, đơn vị, múi giờ và độ chính xác.
- [ ] Có ràng buộc ở database cho dữ liệu dùng chung, khóa chính/khóa ngoại và cập nhật đồng thời khi cần.
- [ ] Có kế hoạch tiến hóa schema, chuyển đổi dữ liệu và kiểm tra tương thích khi miền giá trị thay đổi.

**Ghi nhớ:** value object là cách biến các quy tắc ngầm của nghiệp vụ thành kiểu dữ liệu có thể kiểm tra. `OrderId` tránh nhầm danh tính; `Money` gắn số tiền với loại tiền và chính sách làm tròn; `Quantity` gắn số với đơn vị; `TimeWindow` cố định ý nghĩa của hai đầu mút thời gian. Khi những ý nghĩa đó được giữ xuyên suốt Java, API và hệ lưu trữ, mô hình dữ liệu sẽ rõ ràng, nhất quán và dễ tiến hóa hơn.
