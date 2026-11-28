# Kiểm tra null, miền giá trị và quan hệ giữa các component

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — khám phá các cải tiến từ Java 16 vẫn còn áp dụng trong Java hiện đại, đặc biệt là `record`. Bài này hướng dẫn thiết lập bất biến dữ liệu ngay tại constructor để mọi đối tượng record được tạo thành công đều thỏa các điều kiện của miền nghiệp vụ.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao record không tự động bảo đảm component khác null hoặc nằm trong miền giá trị hợp lệ.
- Kiểm tra giá trị null bằng `Objects.requireNonNull` và chọn ngoại lệ phù hợp.
- Xác thực miền giá trị như số dương, giới hạn min/max, chuỗi không rỗng và tập giá trị cho phép.
- Kiểm tra quan hệ giữa nhiều component, chẳng hạn ngày bắt đầu không sau ngày kết thúc.
- Tổ chức thứ tự kiểm tra để tránh lỗi phụ và thông báo khó hiểu.
- Viết compact constructor hoặc canonical constructor đầy đủ để bảo vệ bất biến của record.
- Thiết kế test cho giá trị hợp lệ, biên hợp lệ và dữ liệu không hợp lệ.

## 1. Record không tự xác thực dữ liệu

Record tạo ra một kiểu dữ liệu gắn với các component được khai báo trong header:

```java
public record Customer(String name, int age) {}
```

Java cung cấp field component, accessor, `equals()`, `hashCode()`, `toString()` và canonical constructor. Tuy nhiên, các thành phần được sinh tự động **không tự áp đặt quy tắc nghiệp vụ** lên dữ liệu đầu vào.

Vì vậy, đoạn mã sau vẫn có thể tạo đối tượng:

```java
Customer a = new Customer(null, -10);
Customer b = new Customer("", 250);
```

Nếu ứng dụng yêu cầu tên phải có nội dung và tuổi phải nằm trong một khoảng cụ thể, những đối tượng trên có trạng thái không hợp lệ theo nghiệp vụ dù Java vẫn cho phép khởi tạo.

Cách giải quyết là kiểm tra dữ liệu trong **canonical constructor**. Mọi lời gọi constructor chuẩn đều đi qua các kiểm tra này, bất kể đối tượng được tạo trực tiếp hay thông qua một constructor nạp chồng ủy quyền đến canonical constructor.

## 2. Chọn loại ngoại lệ phù hợp

Hai nhóm lỗi đầu vào thường gặp:

- **Giá trị bắt buộc bị null:** thường dùng `NullPointerException`, có thể phát sinh thuận tiện từ `Objects.requireNonNull`.
- **Giá trị có mặt nhưng vi phạm quy tắc nghiệp vụ:** thường dùng `IllegalArgumentException`.

Ví dụ:

```java
import java.util.Objects;

public record Customer(String name, int age) {
    public Customer {
        name = Objects.requireNonNull(name, "name").strip();

        if (name.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }
    }
}
```

Kết quả:

```java
Customer customer = new Customer("  Minh  ", 30);

System.out.println(customer.name()); // Minh
System.out.println(customer.age());  // 30

// new Customer(null, 30); // NullPointerException: name
// new Customer("   ", 30); // IllegalArgumentException
// new Customer("Minh", -1); // IllegalArgumentException
```

`Objects.requireNonNull(value, "name")` trả lại chính giá trị nếu không null; nếu null, nó ném `NullPointerException` với thông điệp được cung cấp. Vì thế, ta có thể kết hợp kiểm tra null và chuẩn hóa trong một biểu thức.

Thông điệp ngoại lệ nên nêu rõ component hoặc điều kiện bị vi phạm. Điều này giúp người gọi nhanh chóng xác định đầu vào nào cần sửa.

## 3. Kiểm tra miền giá trị (range validation)

Một component có thể không null nhưng vẫn nằm ngoài miền giá trị được chấp nhận. Ví dụ, số lượng hàng phải lớn hơn 0, tỷ lệ phần trăm nằm trong một khoảng, hoặc cổng mạng phải thuộc miền cho phép.

```java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be greater than zero"
            );
        }
    }
}
```

Giá trị hợp lệ:

```java
Quantity one = new Quantity(1);
Quantity many = new Quantity(25);

// new Quantity(0);  // IllegalArgumentException
// new Quantity(-1); // IllegalArgumentException
```

### Miền đóng và miền mở

Khi xác thực giới hạn, hãy xác định rõ có chấp nhận giá trị tại biên hay không.

| Quy tắc | Điều kiện | Giá trị biên |
| --- | --- | --- |
| Từ 1 đến 100, bao gồm cả hai đầu | `value >= 1 && value <= 100` | 1 và 100 hợp lệ |
| Lớn hơn 0 | `value > 0` | 0 không hợp lệ |
| Từ 0 đến dưới 1 | `value >= 0 && value < 1` | 0 hợp lệ, 1 không hợp lệ |
| Không âm | `value >= 0` | 0 hợp lệ |

Ví dụ tỷ lệ phần trăm:

```java
public record DiscountRate(int percent) {
    public DiscountRate {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException(
                    "percent must be between 0 and 100"
            );
        }
    }
}
```

Ở đây 0 và 100 đều hợp lệ. Không nên viết điều kiện `percent <= 0 || percent >= 100` nếu nghiệp vụ cho phép hai giá trị biên đó.

### Kiểm tra số thực và giá trị đặc biệt

Với `double` hoặc `float`, cần cân nhắc cả `NaN` và vô cực. Các phép so sánh thông thường không xử lý `NaN` giống số hữu hạn; ví dụ `NaN < 0` và `NaN > 0` đều là false.

Nếu component phải là số hữu hạn và không âm:

```java
public record Measurement(double value) {
    public Measurement {
        if (!Double.isFinite(value) || value < 0.0) {
            throw new IllegalArgumentException(
                    "value must be finite and non-negative"
            );
        }
    }
}
```

`Double.isFinite` loại cả `NaN` lẫn dương/âm vô cực. Sau đó phép so sánh đảm bảo giá trị không âm. Nếu nghiệp vụ phân biệt `-0.0` và `+0.0`, cần xác định chính sách riêng; phép so sánh `value < 0.0` xem cả hai là không âm.

## 4. Kiểm tra chuỗi: null, rỗng và định dạng

Chuỗi cần được kiểm tra theo hợp đồng cụ thể. Các trường hợp thường không tương đương:

- `null`: không có đối tượng chuỗi.
- `""`: chuỗi có độ dài bằng 0.
- Chuỗi chỉ có khoảng trắng: không rỗng nhưng có thể không mang nội dung hữu ích.
- Chuỗi có nội dung nhưng sai định dạng hoặc vượt giới hạn.

Ví dụ mã định danh:

```java
import java.util.Objects;
import java.util.regex.Pattern;

public record ProductCode(String value) {
    private static final Pattern FORMAT =
            Pattern.compile("[A-Z]{2}-[0-9]{4}");

    public ProductCode {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(java.util.Locale.ROOT);

        if (!FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "product code must match AA-0000 format"
            );
        }
    }
}
```

Một số ví dụ:

```java
ProductCode code = new ProductCode(" ab-1234 ");
System.out.println(code.value()); // AB-1234

// new ProductCode(null);       // NullPointerException
// new ProductCode("   ");      // IllegalArgumentException
// new ProductCode("ABC-1234"); // IllegalArgumentException
// new ProductCode("AB-12X4");  // IllegalArgumentException
```

Ở đây constructor chuẩn hóa khoảng trắng và chữ hoa trước khi kiểm tra định dạng. Quyết định chuẩn hóa hay từ chối đầu vào phụ thuộc hợp đồng API. Nếu chữ hoa/thường có ý nghĩa phân biệt, không được tự ý chuyển đổi.

`Pattern` được khai báo là static field vì đây là dữ liệu dùng chung để kiểm tra, không phải trạng thái riêng của từng đối tượng record.

## 5. Kiểm tra null an toàn trước khi sử dụng component

Khi một component có thể null, hãy xác thực trước khi gọi phương thức trên nó.

Sai thứ tự:

```java
public record Customer(String name) {
    public Customer {
        name = name.strip(); // Có thể ném NPE mà không có thông điệp rõ ràng.
        if (name == null) {
            throw new IllegalArgumentException("name is required");
        }
    }
}
```

Điều kiện `name == null` không bao giờ được kiểm tra nếu dòng `strip()` đã ném ngoại lệ trước đó.

Cách viết rõ ràng:

```java
import java.util.Objects;

public record Customer(String name) {
    public Customer {
        name = Objects.requireNonNull(name, "name").strip();

        if (name.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }
    }
}
```

Hoặc tách từng bước để thông điệp lỗi thể hiện đúng chính sách:

```java
import java.util.Objects;

public record Customer(String name) {
    public Customer {
        Objects.requireNonNull(name, "name");

        String normalized = name.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        name = normalized;
    }
}
```

Cả hai cách đều kiểm tra null trước khi gọi phương thức trên chuỗi. Chọn cách nào tùy theo độ phức tạp của quy tắc xác thực và mức độ dễ đọc.

## 6. Kiểm tra quan hệ giữa các component

Không phải quy tắc hợp lệ nào cũng có thể kiểm tra riêng từng component. Nhiều bất biến phụ thuộc vào **quan hệ giữa hai hoặc nhiều component**.

Ví dụ, một khoảng ngày có ngày bắt đầu không được sau ngày kết thúc:

```java
import java.time.LocalDate;
import java.util.Objects;

public record DateRange(LocalDate start, LocalDate end) {
    public DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");

        if (start.isAfter(end)) {
            throw new IllegalArgumentException(
                    "start must not be after end"
            );
        }
    }
}
```

Sử dụng:

```java
DateRange valid = new DateRange(
        LocalDate.of(2026, 1, 1),
        LocalDate.of(2026, 1, 31)
);

// Khoảng một ngày vẫn hợp lệ nếu nghiệp vụ cho phép start == end.
DateRange oneDay = new DateRange(
        LocalDate.of(2026, 1, 1),
        LocalDate.of(2026, 1, 1)
);

// new DateRange(
//     LocalDate.of(2026, 2, 1),
//     LocalDate.of(2026, 1, 1)
// ); // IllegalArgumentException
```

Ta kiểm tra null của cả hai component trước, rồi mới gọi `start.isAfter(end)`. Nhờ đó, phép so sánh không bị lỗi null ngoài dự kiến.

Nếu nghiệp vụ yêu cầu ngày bắt đầu phải **trước hẳn** ngày kết thúc, hãy dùng điều kiện từ chối phù hợp:

- `start.isAfter(end)`: từ chối trường hợp `start > end`, do đó vẫn cho phép `start == end`.
- `!start.isBefore(end)`: từ chối trường hợp `start >= end`, do đó chỉ chấp nhận `start < end`.

Một cách viết rõ ràng:

```java
if (!start.isBefore(end)) {
    throw new IllegalArgumentException(
            "start must be before end"
    );
}
```

Điểm quan trọng là diễn đạt đúng điều kiện biên của nghiệp vụ, đặc biệt khi component có cùng giá trị.

## 7. Ví dụ quan hệ nhiều component: giá trị và đơn vị tiền

Giả sử một khoản tiền gồm số tiền và mã tiền tệ. Ta có thể yêu cầu số tiền không âm và mã tiền tệ phải thuộc tập định dạng được hỗ trợ.

```java
import java.math.BigDecimal;
import java.util.Objects;
import java.util.Set;

public record Money(BigDecimal amount, String currency) {

    private static final Set<String> SUPPORTED_CURRENCIES =
            Set.of("VND", "USD", "EUR");

    public Money {
        amount = Objects.requireNonNull(amount, "amount");
        currency = Objects.requireNonNull(currency, "currency")
                .strip()
                .toUpperCase(java.util.Locale.ROOT);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "amount must not be negative"
            );
        }

        if (!SUPPORTED_CURRENCIES.contains(currency)) {
            throw new IllegalArgumentException(
                    "unsupported currency: " + currency
            );
        }

        if ("VND".equals(currency)
                && amount.scale() > 0
                && amount.stripTrailingZeros().scale() > 0) {
            throw new IllegalArgumentException(
                    "VND amount must not contain a fractional part"
            );
        }
    }
}
```

Ví dụ này minh họa ba tầng kiểm tra:

1. **Null:** `amount` và `currency` đều bắt buộc.
2. **Miền giá trị:** `amount` không âm; `currency` phải nằm trong tập hỗ trợ.
3. **Quan hệ theo chính sách:** khi `currency` là VND, số tiền không được có phần lẻ khác 0.

Chính sách số lẻ là quy tắc minh họa cho hệ thống cụ thể, không phải khẳng định rằng mọi hệ thống tiền tệ đều phải xử lý giống nhau. Trong ứng dụng thực tế, quy tắc scale, làm tròn và độ chính xác cần theo hợp đồng nghiệp vụ và đơn vị tiền được hỗ trợ.

Cũng nên phân biệt `BigDecimal` với `double` khi biểu diễn tiền. `BigDecimal` cho phép kiểm soát độ chính xác thập phân; tuy nhiên, ứng dụng vẫn cần định nghĩa rõ cách tạo, so sánh và làm tròn giá trị.

## 8. Tổ chức thứ tự kiểm tra

Một thứ tự kiểm tra tốt giúp tránh lỗi phụ và làm cho thông báo lỗi có ý nghĩa:

1. **Kiểm tra null** cho các component tham chiếu bắt buộc.
2. **Chuẩn hóa** dữ liệu nếu hợp đồng cho phép, chẳng hạn trim khoảng trắng hoặc chuẩn hóa mã.
3. **Kiểm tra miền giá trị** của từng component độc lập.
4. **Kiểm tra quan hệ** giữa nhiều component sau khi tất cả giá trị liên quan đã hợp lệ.
5. **Gán lại tham số** trong compact constructor để compiler lưu giá trị cuối cùng vào field.

Ví dụ tổng hợp:

```java
import java.time.LocalDate;
import java.util.Objects;

public record Subscription(
        String planCode,
        LocalDate startsOn,
        LocalDate endsOn,
        int seats
) {
    public Subscription {
        planCode = Objects.requireNonNull(planCode, "planCode")
                .strip()
                .toUpperCase(java.util.Locale.ROOT);

        Objects.requireNonNull(startsOn, "startsOn");
        Objects.requireNonNull(endsOn, "endsOn");

        if (planCode.isEmpty()) {
            throw new IllegalArgumentException("planCode is required");
        }

        if (seats < 1 || seats > 500) {
            throw new IllegalArgumentException(
                    "seats must be between 1 and 500"
            );
        }

        if (startsOn.isAfter(endsOn)) {
            throw new IllegalArgumentException(
                    "startsOn must not be after endsOn"
            );
        }
    }
}
```

Sau khi thân compact constructor kết thúc bình thường, compiler gán bốn tham số cuối cùng vào các component field theo thứ tự trong header. Nếu một kiểm tra thất bại, constructor ném ngoại lệ và không tạo đối tượng hợp lệ.

Thứ tự trên là một mẫu tổ chức hữu ích, không phải yêu cầu mọi constructor phải có đúng số bước này. Với dữ liệu phức tạp, hãy chia logic thành các hàm kiểm tra private static để thân constructor dễ đọc hơn.

## 9. Dùng hàm kiểm tra riêng khi quy tắc phức tạp

Không nên để compact constructor trở thành một khối mã quá dài. Có thể tách logic kiểm tra thành các phương thức trợ giúp:

```java
public record Coordinate(double latitude, double longitude) {

    public Coordinate {
        validate(latitude, longitude);
    }

    private static void validate(double latitude, double longitude) {
        if (!Double.isFinite(latitude)
                || latitude < -90.0
                || latitude > 90.0) {
            throw new IllegalArgumentException(
                    "latitude must be between -90 and 90"
            );
        }

        if (!Double.isFinite(longitude)
                || longitude < -180.0
                || longitude > 180.0) {
            throw new IllegalArgumentException(
                    "longitude must be between -180 and 180"
            );
        }
    }
}
```

Trong ví dụ này, hai component là kiểu primitive nên không có null. Phương thức `validate` kiểm tra từng miền giá trị độc lập. Nếu hệ thống còn quy tắc quan hệ giữa latitude và longitude, có thể bổ sung tại đây.

Phương thức trợ giúp dùng `static` vì nó chỉ cần các tham số đầu vào, không cần truy cập trạng thái instance. Trong compact constructor, không cần và cũng không nên dựa vào component field như thể compiler đã gán chúng.

## 10. Canonical constructor đầy đủ cũng áp dụng cùng quy tắc

Kiểm tra dữ liệu không phụ thuộc vào việc chọn compact hay dạng đầy đủ. Cả hai đều là canonical constructor, và đều là nơi phù hợp để bảo vệ bất biến của record.

Ví dụ dạng đầy đủ:

```java
import java.time.LocalDate;
import java.util.Objects;

public record DateRange(LocalDate start, LocalDate end) {

    public DateRange(LocalDate start, LocalDate end) {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");

        if (start.isAfter(end)) {
            throw new IllegalArgumentException(
                    "start must not be after end"
            );
        }

        this.start = start;
        this.end = end;
    }
}
```

Trong dạng đầy đủ, bạn tự gán tất cả component field bằng `this.start = start` và `this.end = end`. Mỗi field `final` phải được gán đúng một lần trên mọi đường thực thi kết thúc bình thường.

Trong compact constructor, bạn gán lại tham số nếu cần và compiler tự gán field ở cuối. Không khai báo cả hai canonical constructor trong cùng một record.

## 11. Constructor nạp chồng phải đi qua canonical validation

Một record có thể có constructor nạp chồng với chữ ký khác. Constructor nạp chồng phải ủy quyền qua `this(...)`; nhờ đó mọi đường khởi tạo cuối cùng vẫn đi qua canonical constructor và các quy tắc xác thực.

```java
public record UserName(String value) {

    public UserName {
        value = java.util.Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }

    public UserName() {
        this("guest");
    }
}
```

Lời gọi `new UserName()` sẽ gọi constructor nạp chồng, sau đó ủy quyền đến canonical constructor `UserName(String value)`. Vì thế, giá trị `"guest"` cũng được kiểm tra và chuẩn hóa.

Không nên lặp lại toàn bộ quy tắc xác thực trong mỗi overload. Hãy tập trung bất biến ở canonical constructor để tránh các đường khởi tạo có hành vi khác nhau.

## 12. Kiểm thử các bất biến

Khi viết test cho record, đừng chỉ kiểm tra một trường hợp hợp lệ. Hãy bao phủ ít nhất:

- Giá trị hợp lệ thông thường.
- Giá trị tại biên dưới và biên trên.
- Giá trị ngay ngoài biên.
- Component bắt buộc là null.
- Chuỗi rỗng hoặc chỉ có khoảng trắng.
- Quan hệ giữa các component đúng và sai.
- Trường hợp constructor nạp chồng ủy quyền đến canonical constructor.

Ví dụ với `DiscountRate`:

```java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class DiscountRateTest {

    @Test
    void acceptsBoundaryValues() {
        assertDoesNotThrow(() -> new DiscountRate(0));
        assertDoesNotThrow(() -> new DiscountRate(100));
    }

    @Test
    void rejectsValuesOutsideRange() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new DiscountRate(-1)
        );
        assertThrows(
                IllegalArgumentException.class,
                () -> new DiscountRate(101)
        );
    }
}
```

Đây là ví dụ dùng JUnit Jupiter. Các assertion giúp kiểm tra hợp đồng constructor từ góc nhìn người gọi. Nếu dự án dùng framework test khác, hãy chuyển cùng các trường hợp biên sang framework đó.

Với `DateRange`, cần kiểm tra cả ba trường hợp quan hệ:

| Trường hợp | Kỳ vọng nếu cho phép khoảng một ngày |
| --- | --- |
| `start < end` | Hợp lệ |
| `start == end` | Hợp lệ |
| `start > end` | Ném `IllegalArgumentException` |

Test phải phản ánh đúng quy tắc nghiệp vụ đã chọn, đặc biệt là các giá trị bằng nhau ở biên.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `strip()` trước khi kiểm tra null | Ném NPE tại thao tác chuỗi, không theo thông điệp mong muốn. | Dùng `Objects.requireNonNull` trước. |
| Chỉ kiểm tra null, không kiểm tra miền giá trị | Giá trị như số âm hoặc chuỗi rỗng vẫn được lưu. | Thêm điều kiện nghiệp vụ rõ ràng. |
| Dùng `<=` thay vì `<` hoặc ngược lại | Có thể từ chối nhầm hoặc chấp nhận nhầm giá trị biên. | Xác định miền đóng/mở trước khi viết điều kiện. |
| Kiểm tra quan hệ trước khi kiểm tra null | Có thể ném NPE ngoài dự kiến khi so sánh. | Kiểm tra các component tham chiếu trước. |
| Kiểm tra từng component nhưng bỏ quan hệ liên component | Record có thể chứa tổ hợp giá trị mâu thuẫn. | Xác thực bất biến tổng thể sau kiểm tra độc lập. |
| Lặp validation trong từng constructor overload | Các đường khởi tạo có thể lệch quy tắc. | Ủy quyền overload đến canonical constructor. |
| Chỉ test giá trị thông thường | Bỏ sót lỗi ở biên và dữ liệu sai. | Test null, biên, ngoài biên và quan hệ. |
| Cho rằng record tự động bất biến sâu | Component tham chiếu mutable vẫn có thể đổi trạng thái. | Dùng defensive copy và thiết kế kiểu phần tử phù hợp. |

## 14. Bài tập tự luyện

### Bài 1: Kiểm tra null và miền giá trị

Viết record `PageRequest(int page, int size)` với quy tắc:

- `page` bắt đầu từ 1.
- `size` nằm trong khoảng từ 1 đến 100, bao gồm cả hai đầu.

**Đáp án tham khảo:**

```java
public record PageRequest(int page, int size) {
    public PageRequest {
        if (page < 1) {
            throw new IllegalArgumentException("page must be >= 1");
        }
        if (size < 1 || size > 100) {
            throw new IllegalArgumentException("size must be between 1 and 100");
        }
    }
}
```

### Bài 2: Kiểm tra quan hệ component

Viết record `PriceRange(BigDecimal min, BigDecimal max)` với quy tắc:

- Hai giá trị không null.
- Hai giá trị không âm.
- `min` không được lớn hơn `max`.

**Đáp án tham khảo:**

```java
import java.math.BigDecimal;
import java.util.Objects;

public record PriceRange(BigDecimal min, BigDecimal max) {
    public PriceRange {
        min = Objects.requireNonNull(min, "min");
        max = Objects.requireNonNull(max, "max");

        if (min.signum() < 0 || max.signum() < 0) {
            throw new IllegalArgumentException("prices must be non-negative");
        }
        if (min.compareTo(max) > 0) {
            throw new IllegalArgumentException("min must not exceed max");
        }
    }
}
```

Dùng `compareTo` để so sánh giá trị số của `BigDecimal`. Không dùng `equals` cho mục đích so sánh thứ tự số học vì `equals` còn xét scale.

### Bài 3: Chọn điều kiện biên đúng

Một khoảng thời gian yêu cầu `start` phải **trước hẳn** `end`. Điều kiện nào đúng?

- A. `start.isAfter(end)`
- B. `!start.isBefore(end)`
- C. `!start.isAfter(end)`

**Đáp án:** B là điều kiện để từ chối trường hợp start bằng hoặc sau end. Nếu cần kiểm tra điều kiện hợp lệ trực tiếp, dùng `start.isBefore(end)`.

### Bài 4: Phân biệt null với giá trị không hợp lệ

Với component `String email`, hãy chọn loại ngoại lệ phù hợp:

- `email == null`.
- `email = " "`.
- `email = "not-an-email"`.

**Đáp án tham khảo:** Dùng `NullPointerException` cho giá trị null bắt buộc (ví dụ `Objects.requireNonNull`), và `IllegalArgumentException` cho chuỗi rỗng hoặc sai định dạng theo hợp đồng email của ứng dụng.

## Ghi nhớ

Record không tự đảm bảo dữ liệu đúng nghiệp vụ. Hãy đặt bất biến trong canonical constructor: kiểm tra null trước khi sử dụng component, chuẩn hóa nếu hợp đồng cho phép, kiểm tra miền giá trị và cuối cùng xác thực quan hệ giữa các component. Dùng thông điệp ngoại lệ rõ ràng, xác định chính xác việc có chấp nhận giá trị biên hay không, và kiểm thử cả trường hợp hợp lệ lẫn không hợp lệ. Khi mọi constructor nạp chồng ủy quyền đến canonical constructor, các đường khởi tạo đều đi qua cùng một chính sách xác thực.

## Tài liệu tham khảo

- [Java Language Specification — `8.10.4, Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4).
- [Java API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)).
- [Java API — Double.isFinite](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html#isFinite(double)).
- [JEP 395 — Records (được hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
