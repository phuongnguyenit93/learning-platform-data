# Đối tượng giá trị (Value Object): ý nghĩa được xác định bởi giá trị

Trong Domain-Driven Design (DDD), **Value Object (đối tượng giá trị)** là đối tượng miền được nhận diện bằng giá trị của các thuộc tính cấu thành nó, thay vì bằng một định danh riêng. Hai giá trị `Money` có cùng số tiền và cùng loại tiền tệ thường được xem là tương đương; hai địa chỉ có cùng các thành phần theo quy tắc so sánh của miền cũng có thể là cùng một giá trị.

Value Object thường bất biến: sau khi tạo, các thuộc tính không bị sửa trực tiếp. Nếu cần thay đổi, ta tạo một giá trị mới. Cách thiết kế này giúp gom dữ liệu có ý nghĩa nghiệp vụ cùng với quy tắc kiểm tra và phép toán liên quan, tránh truyền các kiểu dữ liệu nguyên thủy rời rạc rồi lặp lại logic ở nhiều nơi.

## 1. Value Object là gì?

Một Value Object biểu diễn một khái niệm được xác định bởi toàn bộ giá trị cấu thành nó. Nó không cần identity độc lập để nghiệp vụ theo dõi qua thời gian.

Ví dụ:

- `Money`: số tiền và loại tiền tệ.
- `Address`: các thành phần địa chỉ theo quy tắc của miền.
- `DateRange`: thời điểm bắt đầu và kết thúc của một khoảng thời gian.
- `EmailAddress`: địa chỉ email đã được chuẩn hóa theo quy tắc của ứng dụng.
- `Quantity`: số lượng kèm đơn vị đo.
- `Percentage`: tỷ lệ phần trăm có quy tắc về miền giá trị và độ chính xác.

Khi hai giá trị `Money` đều là 100.000 VND, chúng có thể được xem là bằng nhau nếu các quy tắc tiền tệ của miền xác định như vậy. Nếu một giá trị là 100.000 VND và giá trị kia là 100.000 USD, chúng không bằng nhau dù phần số giống hệt.

Value Object có thể chứa nhiều thuộc tính. Điều quan trọng là ý nghĩa của nó đến từ tổ hợp các giá trị đó, không phải từ một mã định danh để phân biệt từng instance.

## 2. So sánh Value Object với Entity

Entity và Value Object đều là các khối xây dựng của mô hình miền, nhưng cách nhận diện khác nhau:

| Tiêu chí | Entity | Value Object |
| --- | --- | --- |
| Cách nhận diện | Identity ổn định | Giá trị của các thuộc tính |
| So sánh | Cùng định danh trong cùng loại và ngữ cảnh | Cùng giá trị theo quy tắc equality |
| Thay đổi | Có thể thay đổi qua hành vi trong vòng đời | Thường bất biến; thay bằng giá trị mới |
| Vòng đời | Có thể được theo dõi độc lập | Thường phụ thuộc vào Entity hoặc Aggregate sở hữu nó |
| Ví dụ | `Customer`, `Order`, `Invoice` | `Money`, `Address`, `DateRange` |

Hai khách hàng có cùng tên và địa chỉ vẫn là hai Entity khác nhau nếu có `CustomerId` khác nhau. Ngược lại, hai Value Object `Address` có cùng các thành phần và cùng quy tắc chuẩn hóa có thể được xem là tương đương dù được tạo thành hai instance riêng.

Một khái niệm có thể là Entity trong ngữ cảnh này nhưng là Value Object trong ngữ cảnh khác. Ví dụ, địa chỉ giao hàng được lưu như một giá trị của đơn hàng có thể là Value Object; một hệ thống quản lý địa chỉ có lịch sử, quyền sở hữu và vòng đời riêng có thể mô hình hóa từng địa chỉ như Entity. Hãy dựa vào nhu cầu nghiệp vụ của bounded context để quyết định.

## 3. Equality: khi nào hai Value Object bằng nhau?

Với Value Object, equality thường dựa trên tất cả thuộc tính có ý nghĩa trong định nghĩa của nó. Nếu hai giá trị có cùng các thành phần theo quy tắc miền, chúng được xem là tương đương.

Ví dụ, với `Money`:

| Giá trị A | Giá trị B | Có bằng nhau? | Lý do |
| --- | --- | --- | --- |
| 100 USD | 100 USD | Có | Cùng số tiền và loại tiền |
| 100 USD | 100 EUR | Không | Khác loại tiền |
| 100.0 USD | 100.00 USD | Có, nếu miền chuẩn hóa độ chính xác như nhau | Khác biểu diễn thập phân nhưng cùng giá trị tiền |
| 100 USD | 101 USD | Không | Khác số tiền |

Quy tắc equality cần được định nghĩa rõ. Với một số kiểu dữ liệu, biểu diễn khác nhau có thể mang cùng ý nghĩa. Ví dụ `BigDecimal("10.0")` và `BigDecimal("10.00")` có cùng giá trị số khi dùng `compareTo`, nhưng `equals` của `BigDecimal` xem scale là một phần của equality. Nếu dùng `BigDecimal` trong record mà không chuẩn hóa, equality tự sinh có thể không khớp ý nghĩa tiền tệ mà miền mong muốn.

Không phải mọi thuộc tính đều cần tham gia equality. Chỉ những thuộc tính cấu thành ý nghĩa của Value Object mới nên được dùng. Một trường ghi chú phục vụ hiển thị hoặc metadata kỹ thuật có thể không thuộc giá trị miền.

## 4. Tính bất biến giúp bảo vệ giá trị

Value Object thường được thiết kế bất biến để người dùng có thể chia sẻ và truyền nó mà không lo một nơi khác âm thầm sửa nội dung.

Ví dụ, nếu một đơn hàng đang dùng `Money(100, USD)`, việc tính thêm phí nên tạo ra một `Money` mới. Giá trị ban đầu vẫn giữ nguyên. Điều này làm cho các phép tính dễ theo dõi và giảm lỗi do aliasing — nhiều đối tượng cùng giữ tham chiếu đến một object mutable.

Một Value Object bất biến thường có các đặc điểm:

- Các trường là `private final` hoặc thành phần record.
- Không cung cấp setter hay phương thức thay đổi nội dung tại chỗ.
- Kiểm tra bất biến khi khởi tạo.
- Các phép toán trả về Value Object mới.
- Nếu chứa collection hoặc object mutable, phải sao chép phòng vệ (defensive copy) và không để lộ tham chiếu có thể sửa.

Java `record` là lựa chọn thuận tiện cho nhiều Value Object vì cung cấp constructor, accessor, `equals()`, `hashCode()` và `toString()` dựa trên các thành phần. Tuy nhiên, record chỉ bất biến nông: nếu một thành phần là `List` mutable, nội dung danh sách vẫn có thể thay đổi trừ khi được sao chép và bảo vệ.

## 5. Ví dụ Java: Money

`Money` là Value Object phổ biến vì số tiền luôn cần đi cùng loại tiền tệ. Dùng `BigDecimal` giúp biểu diễn số thập phân chính xác hơn kiểu `double` cho các phép tính tiền tệ.

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount is required");
        Objects.requireNonNull(currency, "currency is required");

        // Chuẩn hóa scale để 10.0 và 10.00 có cùng biểu diễn giá trị.
        amount = amount.stripTrailingZeros();
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money subtract(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    public Money multiply(BigDecimal factor) {
        Objects.requireNonNull(factor, "factor is required");
        return new Money(amount.multiply(factor), currency);
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other is required");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
    }
}
```

Ví dụ sử dụng:

```java
Money unitPrice = new Money(new BigDecimal("125.50"), Currency.getInstance("USD"));
Money shippingFee = new Money(new BigDecimal("8.00"), Currency.getInstance("USD"));

Money total = unitPrice.add(shippingFee);
// total là 133.5 USD; unitPrice và shippingFee không thay đổi.
```

Đoạn mã minh họa phép cộng, trừ và nhân trong cùng một loại tiền. Nó cố ý không tự động đổi tiền tệ và không tự áp dụng quy tắc làm tròn. Trong nghiệp vụ thực tế, chuyển đổi tỷ giá cần nguồn tỷ giá, thời điểm áp dụng và quy tắc làm tròn rõ ràng; làm tròn theo số chữ số thập phân của tiền tệ cũng phải được quyết định bởi chính sách miền. `stripTrailingZeros()` giải quyết khác biệt scale phổ biến trong equality, nhưng không thay thế quy tắc kế toán hoặc quy tắc lưu trữ.

Nếu miền không cho phép số tiền âm đối với một khái niệm như `UnitPrice`, có thể tạo Value Object chuyên biệt hoặc thêm validation ở kiểu đó. Không nên áp đặt quy tắc “mọi Money đều không âm” nếu nghiệp vụ còn có khoản hoàn tiền, điều chỉnh hoặc số dư âm.

## 6. Ví dụ Value Object khác

### 6.1. Address

`Address` có thể gồm số nhà, đường, thành phố, vùng, mã bưu chính và quốc gia. Các thành phần được xem như một giá trị tổng thể theo quy tắc của miền.

```java
import java.util.Locale;

public record Address(
    String line1,
    String city,
    String postalCode,
    String countryCode
) {
    public Address {
        line1 = requireText(line1, "line1");
        city = requireText(city, "city");
        postalCode = postalCode == null || postalCode.isBlank()
            ? null
            : postalCode.trim();
        countryCode = requireText(countryCode, "countryCode").toUpperCase(Locale.ROOT);
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
        return value.trim();
    }
}
```

Đây là ví dụ rút gọn. Mã bưu chính không bắt buộc ở mọi quốc gia, cách chuẩn hóa địa chỉ có thể khác nhau và việc kiểm tra địa chỉ giao được có thể cần dịch vụ bên ngoài. Hãy chỉ đưa vào constructor những bất biến mà chính Value Object có thể bảo vệ một cách ổn định.

Khi khách hàng đổi địa chỉ, Entity `Customer` có thể nhận một `Address` mới:

```java
customer.changeAddress(new Address(
    "12 Nguyen Hue",
    "Ho Chi Minh City",
    "700000",
    "VN"
));
```

Entity giữ nguyên identity; giá trị địa chỉ được thay thế. Nếu cần lịch sử địa chỉ, nghiệp vụ có thể lưu các phiên bản hoặc một khái niệm lịch sử riêng thay vì làm `Address` mutable.

### 6.2. DateRange

Một `DateRange` có thể biểu diễn khoảng thời gian với ngày bắt đầu và ngày kết thúc. Constructor có thể bảo vệ bất biến `start` không sau `end`. Các phép toán như `contains(date)`, `overlaps(other)` hoặc `intersection(other)` có thể được đặt trong Value Object vì chúng thuộc ý nghĩa của khoảng thời gian.

### 6.3. Quantity

`Quantity` có thể kết hợp giá trị số với đơn vị đo, ví dụ 5 kg hoặc 3 chiếc. Nếu chỉ lưu `BigDecimal` và một chuỗi unit rời rạc, hệ thống có thể vô tình cộng 5 kg với 3 chiếc. Value Object có thể kiểm tra đơn vị tương thích và cung cấp phép cộng, so sánh hoặc chuyển đổi đơn vị theo quy tắc được hỗ trợ.

## 7. Đặt validation và quy tắc ở đúng nơi

Value Object là nơi phù hợp để bảo vệ các bất biến nội tại của chính giá trị đó. Ví dụ:

- `EmailAddress` không được rỗng và phải thỏa định dạng mà miền chấp nhận.
- `DateRange` phải có thứ tự thời gian hợp lệ.
- `Money` phải có số tiền và loại tiền tệ; phép cộng phải cùng loại tiền.
- `Percentage` phải tuân theo miền giá trị mà nghiệp vụ quy định.
- `Quantity` phải có đơn vị đo hợp lệ và không được âm nếu khái niệm đó yêu cầu.

Tuy nhiên, không phải mọi quy tắc có liên quan đến Value Object đều nên đặt vào constructor. Ví dụ, địa chỉ có thể đúng cấu trúc nhưng không giao được tới khu vực cụ thể; điều này phụ thuộc dịch vụ vận chuyển, thời điểm và chính sách giao hàng. Quy tắc đó thuộc một domain service hoặc quy trình ứng dụng thích hợp.

Phân biệt hai loại kiểm tra:

1. **Bất biến nội tại:** luôn đúng đối với mọi instance hợp lệ của Value Object, có thể kiểm tra ngay khi tạo.
2. **Quy tắc theo ngữ cảnh:** phụ thuộc vào Entity, hợp đồng, thời gian hoặc dữ liệu bên ngoài; cần được kiểm tra ở nơi có đủ thông tin.

Không nên tạo một `Address` không hợp lệ rồi hy vọng mọi nơi sử dụng sẽ nhớ kiểm tra. Ngược lại, cũng không nên buộc `Address` truy cập cơ sở dữ liệu hoặc gọi API vận chuyển để tự xác nhận khả năng giao hàng.

## 8. Tránh Primitive Obsession bằng Value Object

Primitive Obsession xảy ra khi các khái niệm miền được biểu diễn bằng các kiểu nguyên thủy như `String`, `int`, `long` hoặc `BigDecimal` dù chúng có ý nghĩa và quy tắc riêng.

Ví dụ một phương thức:

```java
void createShipment(String orderId, String postalCode, BigDecimal weight);
```

Người đọc khó biết `orderId` có thể là mã nào, `postalCode` thuộc quốc gia nào và `weight` dùng đơn vị kg hay lb. Việc truyền nhầm thứ tự các chuỗi cũng có thể không bị trình biên dịch phát hiện.

Có thể dùng kiểu miền rõ nghĩa:

```java
void createShipment(OrderId orderId, PostalCode postalCode, Weight weight);
```

Các kiểu này làm hợp đồng phương thức rõ hơn, đồng thời cung cấp nơi để kiểm tra quy tắc. Không cần tạo Value Object cho mọi biến nguyên thủy; chỉ nên tạo khi khái niệm có ý nghĩa miền, bất biến hoặc hành vi đáng được biểu diễn.

## 9. Value Object trong Entity và Aggregate

Value Object thường là một phần của Entity hoặc Aggregate. Entity sở hữu giá trị đó và có thể thay thế nó bằng một giá trị mới khi nghiệp vụ cho phép.

Ví dụ:

```java
public final class Customer {
    private final CustomerId id;
    private Address address;

    public Customer(CustomerId id, Address address) {
        this.id = Objects.requireNonNull(id);
        this.address = Objects.requireNonNull(address);
    }

    public void changeAddress(Address newAddress) {
        this.address = Objects.requireNonNull(newAddress);
    }
}
```

`Customer` là Entity vì có identity và vòng đời riêng. `Address` là Value Object vì ý nghĩa của nó đến từ các thành phần địa chỉ. Thay địa chỉ không tạo ra một khách hàng mới.

Một Aggregate có thể chứa nhiều Value Object để bảo vệ bất biến. Ví dụ, `Order` có thể chứa `Money` cho tổng tiền, `ShippingAddress` cho địa chỉ giao và `Quantity` cho số lượng từng dòng. Aggregate kiểm soát khi nào các giá trị được thay đổi và bảo đảm các quy tắc ở cấp tổng thể.

## 10. Value Object và dữ liệu collection

Value Object có thể chứa danh sách hoặc tập hợp nếu tập hợp đó là một phần của ý nghĩa giá trị. Tuy nhiên, collection mutable có thể phá vỡ tính bất biến nếu bị sửa từ bên ngoài.

Ví dụ, nếu một `Route` gồm danh sách các điểm dừng, constructor nên sao chép danh sách và accessor không được để lộ collection có thể sửa:

```java
public record Route(List<Stop> stops) {
    public Route {
        stops = List.copyOf(stops);
        if (stops.isEmpty()) {
            throw new IllegalArgumentException("Route must contain a stop");
        }
    }
}
```

`List.copyOf` tạo một danh sách không thể sửa và từ chối phần tử `null`. Tuy nhiên, đây là sao chép nông: nếu `Stop` mutable thì nội dung của từng phần tử vẫn có thể thay đổi. Vì vậy, các phần tử của Value Object dạng collection cũng nên bất biến hoặc được sao chép thích hợp.

## 11. Lưu trữ và truyền Value Object

Value Object thuộc mô hình miền, không phụ thuộc vào cách lưu trữ. Tùy nhu cầu, nó có thể được ánh xạ thành:

- Một hoặc nhiều cột trong cùng bảng với Entity sở hữu nó.
- Một cột JSON hoặc cấu trúc nhúng.
- Một kiểu dữ liệu riêng trong cơ sở dữ liệu nếu hệ quản trị hỗ trợ.
- Một phần của message hoặc API contract sau khi được chuyển sang kiểu giao tiếp phù hợp.

Ví dụ, `Money` có thể được lưu thành hai cột `amount` và `currency_code`; `Address` có thể được lưu thành các cột địa chỉ bên trong bản ghi `Customer`. Việc có bảng riêng hay không là quyết định persistence, không quyết định Value Object có identity hay không.

Khi gửi Value Object qua API hoặc message, cần xác định định dạng, đơn vị, độ chính xác và phiên bản hợp đồng. Không nên serialize trực tiếp object nội bộ nếu điều đó làm lộ chi tiết implementation hoặc khiến bên nhận phụ thuộc vào cấu trúc không ổn định.

## 12. Khi nào nên dùng Value Object?

Một khái niệm thường phù hợp làm Value Object khi:

- Ý nghĩa của nó được xác định bởi các giá trị cấu thành.
- Nghiệp vụ không cần theo dõi identity riêng của nó.
- Nó có quy tắc kiểm tra, chuẩn hóa hoặc phép toán liên quan.
- Nó thường được truyền như một giá trị giữa các Entity hoặc phương thức.
- Thay đổi nó có thể được diễn đạt bằng cách thay giá trị cũ bằng giá trị mới.

Ví dụ, `Money`, `Address`, `DateRange`, `Coordinates`, `Quantity`, `Percentage` và `EmailAddress` thường phù hợp, tùy ngữ cảnh.

Không nên dùng Value Object nếu nghiệp vụ cần theo dõi từng instance qua thời gian, phân biệt các đối tượng có cùng thuộc tính hoặc quản lý vòng đời độc lập. Khi đó, khái niệm có thể phù hợp làm Entity.

## 13. Những lỗi thường gặp khi thiết kế Value Object

**Tạo Value Object nhưng vẫn mutable.** Setter hoặc collection có thể sửa làm giá trị thay đổi sau khi được chia sẻ. Hãy thiết kế bất biến và sao chép phòng vệ khi cần.

**Không định nghĩa equality đúng ý nghĩa miền.** Ví dụ, `Money` có thể bị so sánh sai do scale của `BigDecimal`, hoặc `Address` bị coi là khác nhau chỉ vì khoảng trắng không có ý nghĩa. Hãy quy định chuẩn hóa và equality rõ ràng.

**Dùng một kiểu chung cho các khái niệm khác nhau.** `String` có thể đại diện cho `CustomerId`, `OrderId`, `PostalCode` và `EmailAddress`. Kiểu riêng giúp giảm lỗi truyền nhầm và thể hiện ý nghĩa.

**Đưa quy tắc phụ thuộc bên ngoài vào Value Object.** Một `Address` không nên tự gọi dịch vụ vận chuyển để kiểm tra khả năng giao hàng. Hãy giữ bất biến nội tại trong Value Object và quy tắc theo ngữ cảnh ở nơi phù hợp.

**Tạo lớp cho mọi primitive.** Việc bọc `int` thành một lớp mà không có ý nghĩa, bất biến hoặc hành vi miền có thể chỉ làm tăng mã nguồn. Chỉ tạo Value Object khi nó giúp mô hình rõ hơn.

**Nhầm Value Object với bảng dữ liệu.** Việc một Value Object được lưu trong cột riêng hoặc bảng riêng không làm nó tự động trở thành Entity. Identity được quyết định bởi nghiệp vụ.

**Chia sẻ Value Object giữa các bounded context mà không kiểm tra ý nghĩa.** `Money`, `Address` hoặc `Quantity` có thể có quy tắc khác nhau giữa các context. Chỉ chia sẻ kiểu hoặc hợp đồng khi định nghĩa thực sự thống nhất.

## 14. Quy trình thiết kế Value Object

Khi nhận diện một khái niệm có thể là Value Object, hãy thực hiện các bước:

1. **Xác định ý nghĩa nghiệp vụ:** hỏi khái niệm này biểu diễn điều gì và được dùng trong tình huống nào.
2. **Xác định thành phần cấu thành:** liệt kê thuộc tính nào quyết định giá trị và thuộc tính nào chỉ là metadata.
3. **Định nghĩa equality:** xác định khi nào hai giá trị được xem là tương đương, bao gồm quy tắc chuẩn hóa.
4. **Ghi bất biến:** xác định các điều kiện luôn phải đúng đối với một instance hợp lệ.
5. **Chọn tính bất biến:** dùng final field hoặc record, tránh setter và bảo vệ collection mutable.
6. **Đặt hành vi liên quan:** đưa phép toán, so sánh hoặc kiểm tra thuộc về chính giá trị vào Value Object.
7. **Phân biệt quy tắc nội tại và theo ngữ cảnh:** không để Value Object phụ thuộc vào service hoặc repository bên ngoài.
8. **Tích hợp vào Entity/Aggregate:** xác định ai sở hữu giá trị và khi nào có thể thay thế nó.
9. **Quyết định ánh xạ lưu trữ và giao tiếp:** chọn cách persistence hoặc serialization mà không làm thay đổi ý nghĩa miền.
10. **Kiểm thử:** kiểm tra equality, hash code, validation, phép toán và tính bất biến.

## 15. Kiểm thử Value Object

Kiểm thử nên tập trung vào giá trị và các quy tắc của nó:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Hai `Money` cùng amount và currency | Bằng nhau |
| Hai `Money` cùng amount nhưng khác currency | Không bằng nhau |
| Cộng hai `Money` cùng currency | Trả về giá trị mới với tổng chính xác |
| Cộng hai `Money` khác currency | Bị từ chối nếu chưa có quy tắc chuyển đổi |
| Tạo `DateRange` với ngày bắt đầu sau ngày kết thúc | Bị từ chối |
| Tạo `Address` thiếu trường bắt buộc | Bị từ chối |
| Thay đổi collection đầu vào sau khi tạo `Route` | Không làm thay đổi danh sách bên trong `Route` |
| Thay đổi giá trị trong Entity sở hữu VO | Identity của Entity không đổi |

Ngoài việc kiểm tra kết quả, hãy kiểm tra `equals()` và `hashCode()` nhất quán để Value Object hoạt động đúng trong collection như `HashSet` hoặc làm khóa của `HashMap`.

## 16. Nguyên tắc cần ghi nhớ

Value Object biểu diễn một khái niệm mà ý nghĩa được xác định bởi giá trị của các thuộc tính. Nó thường bất biến, có equality theo giá trị và là nơi phù hợp để bảo vệ các bất biến nội tại cũng như cung cấp phép toán thuộc về khái niệm đó.

Hãy dùng Value Object để thay các nhóm primitive rời rạc bằng kiểu miền rõ nghĩa, phân biệt nó với Entity dựa trên identity, và chỉ chia sẻ giữa các bounded context khi ngữ nghĩa thực sự giống nhau. Khi được thiết kế đúng, Value Object giúp mã nguồn diễn đạt nghiệp vụ chính xác hơn, giảm trạng thái không hợp lệ và làm các phép tính hoặc quy tắc dễ kiểm thử.
