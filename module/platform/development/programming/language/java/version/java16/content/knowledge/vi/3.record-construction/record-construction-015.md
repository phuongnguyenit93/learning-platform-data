# Kiểm thử giá trị biên, dữ liệu không hợp lệ và dữ liệu đã chuẩn hóa

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — khám phá các cải tiến từ Java 16 vẫn hữu ích trong Java hiện đại, đặc biệt là `record`. Bài này trình bày cách kiểm thử canonical constructor qua các giá trị biên, đầu vào sai hợp đồng và kết quả chuẩn hóa, để xác nhận record chỉ được tạo với trạng thái hợp lệ.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Chia miền đầu vào thành các nhóm tương đương và chọn giá trị đại diện để kiểm thử.
- Kiểm tra giá trị tại biên dưới, biên trên và ngay bên ngoài miền hợp lệ.
- Kiểm thử riêng null, giá trị sai định dạng và quan hệ không hợp lệ giữa các component.
- Xác nhận accessor trả về dữ liệu đã được chuẩn hóa trong compact constructor.
- Nhận diện lỗi tràn số, NaN, vô cực và sai lệch khi so sánh số thập phân.
- Dùng JUnit Jupiter parameterized tests để kiểm thử nhiều trường hợp rõ ràng.
- Viết test tập trung vào hợp đồng quan sát được của record thay vì chi tiết implementation.

## 1. Vì sao cần kiểm thử constructor của record?

Record được dùng để biểu diễn dữ liệu có cấu trúc. Canonical constructor là điểm kiểm soát việc tạo đối tượng: nó có thể kiểm tra đầu vào, chuẩn hóa giá trị và từ chối trạng thái không hợp lệ.

Ví dụ:

```java
public record Percentage(int value) {
    public Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "value must be between 0 and 100"
            );
        }
    }
}
```

Chỉ kiểm tra trường hợp `50` chưa đủ để chứng minh hợp đồng. Cần xác nhận cả:

- Biên hợp lệ nhỏ nhất: `0`.
- Biên hợp lệ lớn nhất: `100`.
- Giá trị ngay dưới biên: `-1`.
- Giá trị ngay trên biên: `101`.
- Một vài giá trị đại diện ở giữa miền.
- Giá trị hợp lệ được lưu đúng trong record.

Một bộ test tốt giúp phát hiện lỗi ở điều kiện so sánh, thứ tự validation, chuẩn hóa dữ liệu và xử lý các trường hợp đặc biệt.

## 2. Chia đầu vào thành các nhóm tương đương

Trước khi viết test, hãy xác định các nhóm đầu vào có cùng kết quả theo hợp đồng. Đây là kỹ thuật *equivalence partitioning* (phân hoạch tương đương).

Với `Percentage` có miền hợp lệ từ 0 đến 100:

| Nhóm | Ví dụ | Kết quả mong đợi |
| --- | --- | --- |
| Dưới biên dưới | `-1`, `-20` | Từ chối |
| Đúng biên dưới | `0` | Chấp nhận |
| Bên trong miền | `1`, `50`, `99` | Chấp nhận |
| Đúng biên trên | `100` | Chấp nhận |
| Trên biên trên | `101`, `150` | Từ chối |

Không cần thử mọi số nguyên trong từng nhóm. Chọn các giá trị đại diện đủ để kiểm tra quy tắc và những điểm dễ sai.

Với component kiểu tham chiếu, các nhóm có thể gồm:

- Null nếu component bắt buộc.
- Chuỗi rỗng hoặc chỉ có khoảng trắng.
- Giá trị có định dạng sai.
- Giá trị hợp lệ nhưng cần chuẩn hóa.
- Giá trị hợp lệ đã ở dạng chuẩn.

Với nhiều component, cần thêm nhóm cho từng quan hệ: hai ngày đảo ngược, khoảng bằng nhau, danh sách vượt kích thước tối đa hoặc hai giá trị mâu thuẫn.

## 3. Kiểm thử đúng biên và ngay ngoài biên

Kỹ thuật *boundary value analysis* tập trung vào các điểm sát giới hạn, nơi lỗi dấu so sánh thường xuất hiện.

Với miền `0 <= value <= 100`, các điểm quan trọng là:

- `-1`: ngay dưới biên.
- `0`: biên dưới hợp lệ.
- `1`: ngay phía trong biên dưới.
- `99`: ngay phía trong biên trên.
- `100`: biên trên hợp lệ.
- `101`: ngay trên biên.

JUnit Jupiter có thể dùng `@ParameterizedTest` và `@ValueSource` để kiểm thử các trường hợp hợp lệ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class PercentageTest {

    @ParameterizedTest
    @ValueSource(ints = {0, 1, 50, 99, 100})
    void acceptsValuesInsideInclusiveRange(int value) {
        Percentage percentage = new Percentage(value);

        assertEquals(value, percentage.value());
    }
}
```

Kiểm thử các trường hợp không hợp lệ riêng:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class PercentageInvalidTest {

    @ParameterizedTest
    @ValueSource(ints = {-1, -100, 101, 200})
    void rejectsValuesOutsideRange(int value) {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Percentage(value)
        );
    }
}
```

Các test xác nhận cả hai phía của mỗi biên. Nếu điều kiện vô tình đổi từ `value < 0` thành `value <= 0`, test tại `0` sẽ phát hiện lỗi. Nếu đổi điều kiện trên thành `value >= 100`, test tại `100` sẽ phát hiện lỗi.

## 4. Kiểm thử miền có cả giới hạn kiểu dữ liệu

Khi component là `int` hoặc `long`, cần quan tâm cả giới hạn của kiểu nguyên thủy. Một biểu thức kiểm tra có thể tràn số trước khi kết quả được so sánh.

Ví dụ sai khi muốn giới hạn giá trị tuyệt đối:

```java
public record BoundedOffset(int value) {
    public BoundedOffset {
        if (Math.abs(value) > 100) {
            throw new IllegalArgumentException(
                    "absolute value must not exceed 100"
            );
        }
    }
}
```

`Math.abs(Integer.MIN_VALUE)` vẫn bằng một số âm do giá trị dương tương ứng không biểu diễn được trong kiểu `int`. Vì vậy điều kiện có thể không phát hiện `Integer.MIN_VALUE`.

Một cách viết an toàn hơn với giới hạn đối xứng 100:

```java
public record BoundedOffset(int value) {
    public BoundedOffset {
        if (value < -100 || value > 100) {
            throw new IllegalArgumentException(
                    "value must be between -100 and 100"
            );
        }
    }
}
```

Test nên bao gồm các biên miền và giá trị cực trị của kiểu:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class BoundedOffsetTest {

    @Test
    void rejectsIntegerExtremes() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new BoundedOffset(Integer.MIN_VALUE)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> new BoundedOffset(Integer.MAX_VALUE)
        );
    }
}
```

Nếu phép tính nghiệp vụ có thể vượt giới hạn kiểu, hãy kiểm tra khả năng tràn hoặc dùng API số học có kiểm tra như `Math.addExact`, `Math.subtractExact` và `Math.multiplyExact` khi phù hợp. Không nên dựa vào kết quả đã tràn để xác thực dữ liệu.

## 5. Kiểm thử số thực: NaN, vô cực và biên kế cận

Với `float` và `double`, chỉ kiểm tra điều kiện nhỏ hơn và lớn hơn có thể bỏ sót `NaN`. Các phép so sánh với `NaN` đều trả về false.

Ví dụ:

```java
public record Ratio(double value) {
    public Ratio {
        if (value < 0.0 || value > 1.0) {
            throw new IllegalArgumentException(
                    "value must be between 0 and 1"
            );
        }
    }
}
```

Đoạn mã trên không từ chối `Double.NaN`. Hợp đồng cần kiểm tra tính hữu hạn trước:

```java
public record Ratio(double value) {
    public Ratio {
        if (!Double.isFinite(value) || value < 0.0 || value > 1.0) {
            throw new IllegalArgumentException(
                    "value must be finite and between 0 and 1"
            );
        }
    }
}
```

Bộ test nên bao gồm:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class RatioTest {

    @Test
    void acceptsBothInclusiveBoundaries() {
        assertEquals(0.0, new Ratio(0.0).value(), 0.0);
        assertEquals(1.0, new Ratio(1.0).value(), 0.0);
    }

    @Test
    void rejectsValuesImmediatelyOutsideRange() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Ratio(Math.nextDown(0.0))
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> new Ratio(Math.nextUp(1.0))
        );
    }

    @Test
    void rejectsNonFiniteValues() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Ratio(Double.NaN)
        );
        assertThrows(
                IllegalArgumentException.class,
                () -> new Ratio(Double.POSITIVE_INFINITY)
        );
        assertThrows(
                IllegalArgumentException.class,
                () -> new Ratio(Double.NEGATIVE_INFINITY)
        );
    }
}
```

`Math.nextDown` và `Math.nextUp` hữu ích khi cần tạo giá trị biểu diễn gần nhất ở dưới hoặc trên một số thực. Với bài toán tiền tệ hoặc số thập phân chính xác, nên cân nhắc `BigDecimal` thay vì dùng `double`.

## 6. Kiểm thử BigDecimal và so sánh theo giá trị

`BigDecimal` có thể biểu diễn cùng giá trị số với scale khác nhau. Ví dụ `1.0` và `1.00` có giá trị so sánh bằng nhau bằng `compareTo`, nhưng `equals` trả false vì scale khác nhau.

Ví dụ record chấp nhận số tiền không âm và chuẩn hóa bỏ các số 0 dư ở cuối:

```java
import java.math.BigDecimal;
import java.util.Objects;

public record Amount(BigDecimal value) {

    public Amount {
        value = Objects.requireNonNull(value, "value");

        if (value.signum() < 0) {
            throw new IllegalArgumentException(
                    "value must be non-negative"
            );
        }

        value = value.stripTrailingZeros();

        if (value.scale() < 0) {
            value = value.setScale(0);
        }
    }
}
```

Test cần xác nhận biên 0, giá trị dương và giá trị âm bị từ chối:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class AmountTest {

    @Test
    void acceptsZeroAndNormalizesScale() {
        Amount zero = new Amount(new BigDecimal("0.00"));
        Amount amount = new Amount(new BigDecimal("12.3400"));

        assertEquals(0, zero.value().compareTo(BigDecimal.ZERO));
        assertEquals(new BigDecimal("12.34"), amount.value());
    }

    @Test
    void rejectsNegativeAmount() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Amount(new BigDecimal("-0.01"))
        );
    }
}
```

Không dùng `BigDecimal.equals` để kiểm tra hai giá trị có cùng trị số khi scale có thể khác nhau. Dùng `compareTo` nếu hợp đồng nói về giá trị số. Nếu scale là một phần của hợp đồng, hãy kiểm thử scale riêng và chuẩn hóa theo chính sách nghiệp vụ.

## 7. Kiểm thử dữ liệu đã chuẩn hóa trong compact constructor

Một compact constructor có thể gán lại tham số ngầm trước khi compiler lưu chúng vào component field. Test nên kiểm tra giá trị quan sát được qua accessor sau khi tạo record.

Ví dụ:

```java
import java.util.Locale;
import java.util.Objects;

public record CountryCode(String value) {

    public CountryCode {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z]{2}")) {
            throw new IllegalArgumentException(
                    "value must contain two ASCII letters"
            );
        }
    }
}
```

Test xác nhận đầu vào được chuẩn hóa và đầu vào sai bị từ chối:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CountryCodeTest {

    @Test
    void storesNormalizedValue() {
        CountryCode code = new CountryCode("  vn ");

        assertEquals("VN", code.value());
    }

    @Test
    void rejectsWrongLength() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new CountryCode("VNM")
        );
    }

    @Test
    void rejectsNonAsciiLetters() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new CountryCode("éV")
        );
    }
}
```

Test `storesNormalizedValue` quan trọng vì chỉ kiểm tra constructor không ném ngoại lệ chưa chứng minh rằng component được lưu ở dạng chuẩn. Hãy kiểm tra accessor để xác nhận kết quả thực tế.

Dùng `Locale.ROOT` cho phép chuyển đổi chữ hoa ổn định, không phụ thuộc locale mặc định của máy. Quy tắc regex trong ví dụ cố ý chỉ chấp nhận hai chữ cái ASCII; nếu miền nghiệp vụ cần Unicode, hãy định nghĩa rõ quy tắc khác và kiểm thử tương ứng.

## 8. Kiểm thử thứ tự chuẩn hóa và validation

Thứ tự xử lý có thể thay đổi kết quả. Nếu yêu cầu là chấp nhận chuỗi có khoảng trắng hai đầu nhưng sau khi bỏ khoảng trắng phải còn nội dung, hãy chuẩn hóa trước rồi mới kiểm tra rỗng.

Ví dụ:

```java
import java.util.Objects;

public record UserName(String value) {

    public UserName {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException(
                    "value must not be blank"
            );
        }
    }
}
```

Các trường hợp cần kiểm tra:

| Đầu vào | Sau chuẩn hóa | Kết quả |
| --- | --- | --- |
| `"  linh  "` | `"linh"` | Chấp nhận, lưu `"linh"` |
| `"linh"` | `"linh"` | Chấp nhận |
| `"   "` | `""` | Từ chối |
| `""` | `""` | Từ chối |
| `null` | Không có giá trị | Ném `NullPointerException` |

JUnit test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class UserNameTest {

    @Test
    void trimsWhitespaceBeforeStoring() {
        assertEquals("linh", new UserName("  linh  ").value());
    }

    @Test
    void rejectsBlankAfterTrimming() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new UserName("   ")
        );
    }

    @Test
    void rejectsNullInput() {
        assertThrows(
                NullPointerException.class,
                () -> new UserName(null)
        );
    }
}
```

Không chỉ kiểm tra đầu vào thô. Hợp đồng của record thường nói về giá trị cuối cùng được lưu, vì vậy cần xác nhận component sau chuẩn hóa.

## 9. Kiểm thử giới hạn độ dài chuỗi

Nếu component có giới hạn độ dài, hãy kiểm tra ngay dưới giới hạn, đúng giới hạn và ngay trên giới hạn.

Ví dụ record giới hạn mã tối đa 12 ký tự UTF-16 code unit:

```java
import java.util.Objects;

public record ProductCode(String value) {

    public ProductCode {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty() || value.length() > 12) {
            throw new IllegalArgumentException(
                    "value must contain 1 to 12 UTF-16 code units"
            );
        }
    }
}
```

Bộ test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ProductCodeTest {

    @Test
    void acceptsLengthBelowMaximum() {
        ProductCode code = new ProductCode("ABCDEFGHIJK");

        assertEquals(11, code.value().length());
    }

    @Test
    void acceptsMaximumLength() {
        ProductCode code = new ProductCode("ABCDEFGHIJKL");

        assertEquals(12, code.value().length());
    }

    @Test
    void rejectsLengthAboveMaximum() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new ProductCode("ABCDEFGHIJKLM")
        );
    }
}
```

Lưu ý `String.length()` đếm UTF-16 code unit, không phải số Unicode code point hay số ký tự người dùng nhìn thấy. Nếu yêu cầu nghiệp vụ giới hạn code point, dùng `codePointCount`; nếu giới hạn ký tự hiển thị (grapheme cluster), cần định nghĩa rõ và dùng công cụ Unicode phù hợp. Tên đơn vị đo trong hợp đồng giúp tránh hiểu nhầm.

## 10. Kiểm thử collection theo số lượng biên

Với component collection, cần kiểm thử:

- Rỗng nếu được phép.
- Một phần tử nếu đó là giá trị nhỏ nhất hợp lệ.
- Đúng số lượng tối đa.
- Nhiều hơn tối đa một phần tử.
- Null collection và null element theo chính sách.

Ví dụ:

```java
import java.util.List;
import java.util.Objects;

public record Tags(List<String> values) {

    public Tags {
        values = List.copyOf(
                Objects.requireNonNull(values, "values")
        );

        if (values.size() > 3) {
            throw new IllegalArgumentException(
                    "values must contain at most 3 elements"
            );
        }
    }
}
```

Test các biên số lượng:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;

import org.junit.jupiter.api.Test;

class TagsTest {

    @Test
    void acceptsEmptyCollection() {
        assertEquals(List.of(), new Tags(List.of()).values());
    }

    @Test
    void acceptsOneElement() {
        assertEquals(List.of("a"), new Tags(List.of("a")).values());
    }

    @Test
    void acceptsMaximumSize() {
        assertEquals(
                3,
                new Tags(List.of("a", "b", "c")).values().size()
        );
    }

    @Test
    void rejectsOneAboveMaximum() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Tags(List.of("a", "b", "c", "d"))
        );
    }
}
```

Trong ví dụ, `List.copyOf` chạy trước kiểm tra số lượng, nên null collection hoặc null element sẽ bị từ chối bằng `NullPointerException`. Nếu thứ tự lỗi là một phần hợp đồng, hãy viết test riêng cho từng trường hợp. Nếu collection có thể thay đổi đồng thời từ thread khác, cần kiểm soát việc snapshot trước khi kiểm tra kích thước.

## 11. Kiểm thử quan hệ giữa các component

Mỗi component có thể hợp lệ riêng nhưng kết hợp lại vi phạm quy tắc nghiệp vụ.

Ví dụ khoảng ngày yêu cầu `start` không sau `end`:

```java
import java.time.LocalDate;
import java.util.Objects;

public record DateRange(LocalDate start, LocalDate end) {

    public DateRange {
        start = Objects.requireNonNull(start, "start");
        end = Objects.requireNonNull(end, "end");

        if (start.isAfter(end)) {
            throw new IllegalArgumentException(
                    "start must not be after end"
            );
        }
    }
}
```

Các trường hợp biên:

- `start` bằng `end`: hợp lệ nếu khoảng một ngày được cho phép.
- `start` ngay trước `end`: hợp lệ.
- `start` ngay sau `end`: không hợp lệ.
- `start` hoặc `end` null: không hợp lệ theo hợp đồng bắt buộc.

Test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalDate;

import org.junit.jupiter.api.Test;

class DateRangeTest {

    @Test
    void acceptsSameStartAndEnd() {
        LocalDate day = LocalDate.of(2026, 5, 10);

        DateRange range = new DateRange(day, day);

        assertEquals(day, range.start());
        assertEquals(day, range.end());
    }

    @Test
    void acceptsStartBeforeEnd() {
        LocalDate start = LocalDate.of(2026, 5, 10);
        LocalDate end = start.plusDays(1);

        DateRange range = new DateRange(start, end);

        assertEquals(start, range.start());
        assertEquals(end, range.end());
    }

    @Test
    void rejectsStartAfterEnd() {
        LocalDate start = LocalDate.of(2026, 5, 11);
        LocalDate end = LocalDate.of(2026, 5, 10);

        assertThrows(
                IllegalArgumentException.class,
                () -> new DateRange(start, end)
        );
    }
}
```

Đừng chỉ kiểm thử hai component riêng lẻ. Hãy kiểm thử chính quan hệ giữa chúng ở cả biên hợp lệ và không hợp lệ.

## 12. Kiểm thử dữ liệu null và dữ liệu sai định dạng

Với component tham chiếu bắt buộc, cần kiểm tra null tách biệt với chuỗi rỗng hoặc định dạng sai.

Ví dụ `EmailAddress`:

```java
import java.util.Objects;

public record EmailAddress(String value) {

    public EmailAddress {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty() || !value.contains("@")) {
            throw new IllegalArgumentException(
                    "value must be a non-blank email-like address"
            );
        }
    }
}
```

Test:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class EmailAddressTest {

    @Test
    void rejectsNull() {
        assertThrows(
                NullPointerException.class,
                () -> new EmailAddress(null)
        );
    }

    @Test
    void rejectsBlank() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new EmailAddress("  ")
        );
    }

    @Test
    void rejectsMissingAtSign() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new EmailAddress("user.example.com")
        );
    }
}
```

Ví dụ này chỉ minh họa kiểm thử hợp đồng đơn giản, không phải bộ xác thực email đầy đủ theo chuẩn email Internet. Không nên suy ra rằng một phép kiểm tra chứa ký tự `@` là đủ để xác nhận mọi địa chỉ email thực tế.

## 13. Kiểm thử constructor bổ sung và static factory

Constructor bổ sung và factory thường ủy quyền đến canonical constructor. Test cần xác nhận chúng tạo ra cùng trạng thái chuẩn và không bỏ qua validation.

Ví dụ:

```java
public record PageSize(int value) {

    public PageSize {
        if (value < 1 || value > 200) {
            throw new IllegalArgumentException(
                    "value must be between 1 and 200"
            );
        }
    }

    public PageSize() {
        this(20);
    }

    public static PageSize defaultSize() {
        return new PageSize();
    }
}
```

Test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PageSizeTest {

    @Test
    void constructorAndFactoryUseExpectedDefault() {
        assertEquals(20, new PageSize().value());
        assertEquals(20, PageSize.defaultSize().value());
    }

    @Test
    void canonicalValidationAppliesToEveryCreationPath() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new PageSize(0)
        );
    }
}
```

Với factory nhận đầu vào khác dạng, kiểm thử cả lỗi chuyển đổi riêng của factory và validation cuối cùng của canonical constructor. Đừng lặp lại toàn bộ test của canonical constructor cho mọi overload nếu các overload chỉ chuyển tiếp một cách đơn giản; hãy kiểm tra hành vi đặc thù mà từng đường tạo bổ sung mang lại.

## 14. Dùng parameterized tests cho các nhóm trường hợp

JUnit Jupiter hỗ trợ nhiều nguồn dữ liệu cho `@ParameterizedTest`. Một số annotation thường dùng:

| Annotation | Dùng khi |
| --- | --- |
| `@ValueSource` | Danh sách giá trị đơn giản cùng kiểu |
| `@NullSource` | Kiểm tra đầu vào null |
| `@EmptySource` | Kiểm tra chuỗi hoặc collection rỗng |
| `@NullAndEmptySource` | Kiểm tra cả null và rỗng |
| `@MethodSource` | Cần tạo dữ liệu nhiều tham số hoặc đối tượng phức tạp |
| `@CsvSource` | Dữ liệu dạng bảng với một vài cột đơn giản |

Ví dụ dùng `@MethodSource` để kiểm thử các trường hợp có tên:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

class PercentageCasesTest {

    static Stream<Integer> invalidValues() {
        return Stream.of(-1, -100, 101, 200);
    }

    @ParameterizedTest
    @MethodSource("invalidValues")
    void rejectsInvalidValues(int value) {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Percentage(value)
        );
    }
}
```

Nếu muốn thể hiện cả giá trị và kết quả mong đợi, dùng `Arguments`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class CountryCodeCasesTest {

    static Stream<Arguments> validInputs() {
        return Stream.of(
                Arguments.of("vn", "VN"),
                Arguments.of(" VN ", "VN"),
                Arguments.of("us", "US")
        );
    }

    @ParameterizedTest
    @MethodSource("validInputs")
    void normalizesInput(String input, String expected) {
        assertEquals(expected, new CountryCode(input).value());
    }
}
```

Parameterized test giảm lặp lại nhưng vẫn nên giữ tên test mô tả rõ nhóm hành vi. Nếu mỗi trường hợp có ý nghĩa khác nhau hoặc cần setup riêng, các test độc lập có thể dễ đọc hơn.

## 15. Kiểm thử kết quả chuẩn hóa, không kiểm tra field nội bộ

Component field của record là private. Test nên xác nhận dữ liệu thông qua accessor công khai:

```java
CountryCode code = new CountryCode(" vn ");

assertEquals("VN", code.value());
```

Không cần reflection để đọc field. Kiểm thử qua API công khai xác nhận đúng điều người dùng record quan sát được và không phụ thuộc cách compiler sinh field.

Với collection hoặc array có defensive copy, test cả hai chiều:

- Sửa nguồn sau khi tạo record không làm thay đổi accessor.
- Sửa bản sao lấy từ accessor không làm thay đổi lần đọc tiếp theo.

Với object mutable lồng bên trong, cần kiểm tra sâu hơn theo hợp đồng copy đã chọn. Một phép so sánh tham chiếu hoặc chỉ kiểm tra kích thước collection chưa chứng minh dữ liệu đã được bảo vệ.

## 16. Tránh test phụ thuộc thông báo mặc định của JDK

Nếu constructor tự đặt thông báo ổn định và API cam kết nó, có thể kiểm tra `getMessage()`. Nhưng không nên phụ thuộc câu chữ mặc định do JDK tự tạo ra.

Ví dụ, test nên ưu tiên:

```java
assertThrows(
        NullPointerException.class,
        () -> new UserName(null)
);
```

Thay vì kiểm tra thông điệp mặc định của một `NullPointerException` phát sinh từ dereference. Câu chữ mặc định có thể thay đổi giữa phiên bản hoặc cách phát sinh ngoại lệ.

Tương tự, với API parse của JDK, hãy kiểm tra loại ngoại lệ và kết quả theo hợp đồng. Chỉ kiểm tra chính xác message nếu chính code của ứng dụng chủ động đặt và cam kết giữ ổn định.

## 17. Kiểm thử thời gian và dữ liệu phụ thuộc môi trường

Không nên để test biên phụ thuộc ngày giờ hiện tại, múi giờ mặc định hoặc locale mặc định của máy.

Ví dụ record có factory tạo ngày hiện tại nên nhận `Clock` để test kiểm soát thời gian:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

public record ReportDay(LocalDate value) {

    public ReportDay {
        value = Objects.requireNonNull(value, "value");
    }

    public static ReportDay today(Clock clock) {
        Objects.requireNonNull(clock, "clock");
        return new ReportDay(LocalDate.now(clock));
    }
}
```

Test dùng clock cố định:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class ReportDayTest {

    @Test
    void usesProvidedClock() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-05-10T10:00:00Z"),
                ZoneOffset.UTC
        );

        ReportDay day = ReportDay.today(clock);

        assertEquals(LocalDate.of(2026, 5, 10), day.value());
    }
}
```

Test không phụ thuộc ngày chạy thật. Tương tự, dùng `Locale.ROOT` cho chuẩn hóa kỹ thuật khi hợp đồng không phụ thuộc ngôn ngữ hệ thống.

## 18. Các lỗi thường gặp khi kiểm thử constructor

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ kiểm thử một giá trị hợp lệ ở giữa miền | Không phát hiện sai dấu tại biên. | Kiểm tra min, max và giá trị ngay ngoài biên. |
| Chỉ kiểm thử biên dưới | Bỏ sót lỗi ở biên trên. | Kiểm tra cả hai đầu miền. |
| Không kiểm thử null riêng | Không xác nhận hợp đồng tham chiếu bắt buộc. | Thêm test null cho component tham chiếu. |
| Chỉ kiểm tra constructor không ném lỗi | Không biết giá trị đã chuẩn hóa được lưu hay chưa. | Kiểm tra accessor sau khởi tạo. |
| So sánh BigDecimal bằng equals khi scale không quan trọng | Test có thể thất bại với cùng trị số khác scale. | Dùng compareTo hoặc kiểm tra scale theo hợp đồng. |
| Bỏ qua NaN và vô cực | Validation số thực có thể chấp nhận dữ liệu không hữu hạn. | Kiểm tra Double.isFinite hoặc Float.isFinite. |
| Dùng Math.abs để kiểm tra giới hạn int | Integer.MIN_VALUE có thể làm điều kiện sai do tràn. | So sánh trực tiếp với biên âm và dương. |
| Chỉ kiểm thử component riêng lẻ | Không phát hiện quan hệ giữa component sai. | Tạo test cho các tổ hợp hợp lệ và không hợp lệ. |
| Test phụ thuộc ngày hoặc locale hiện tại | Kết quả khác nhau giữa máy và CI. | Inject Clock và dùng Locale.ROOT khi phù hợp. |
| Test mọi chi tiết implementation | Test giòn, cản trở refactor. | Kiểm thử hợp đồng quan sát được qua accessor và exception. |

## 19. Bài tập tự luyện

### Bài 1: Giá trị biên của Percentage

Record `Percentage(int value)` chấp nhận từ 0 đến 100. Hãy liệt kê ít nhất sáu giá trị nên kiểm thử và kết quả mong đợi.

**Đáp án:**

| Giá trị | Kết quả |
| --- | --- |
| `-1` | Từ chối |
| `0` | Chấp nhận |
| `1` | Chấp nhận |
| `99` | Chấp nhận |
| `100` | Chấp nhận |
| `101` | Từ chối |

### Bài 2: Kiểm thử chuẩn hóa

Record `UserName(String value)` gọi `strip()` rồi từ chối chuỗi rỗng. Viết test chứng minh `"  linh  "` được lưu thành `"linh"` và `"   "` bị từ chối.

**Đáp án tham khảo:**

```java
assertEquals("linh", new UserName("  linh  ").value());

assertThrows(
        IllegalArgumentException.class,
        () -> new UserName("   ")
);
```

### Bài 3: Phát hiện lỗi NaN

Một record `Ratio(double value)` chỉ kiểm tra `value < 0 || value > 1`. Trường hợp nào có thể lọt qua và test thế nào?

**Đáp án:** `Double.NaN` vì các phép so sánh nhỏ hơn/lớn hơn với NaN đều false. Thêm kiểm tra `Double.isFinite(value)` và test NaN cùng hai giá trị vô cực.

### Bài 4: Kiểm thử collection tối đa

Record `Tags(List<String> values)` cho phép tối đa ba phần tử và cho phép danh sách rỗng. Nêu các kích thước cần kiểm tra.

**Đáp án:** 0, 1, 3 và 4 phần tử. Kích thước 0, 1 và 3 được chấp nhận; 4 bị từ chối. Kiểm tra thêm null collection và null element theo chính sách của `List.copyOf`.

### Bài 5: Quan hệ giữa hai ngày

Record `DateRange(start, end)` yêu cầu start không sau end. Hãy chọn ba trường hợp biên và kết quả.

**Đáp án:**

- start bằng end: chấp nhận nếu khoảng rỗng được cho phép.
- start ngay trước end: chấp nhận.
- start ngay sau end: ném `IllegalArgumentException`.

## Ghi nhớ

Kiểm thử constructor record nên bao phủ các nhóm đầu vào, hai biên và giá trị ngay bên ngoài miền hợp lệ. Với dữ liệu tham chiếu, kiểm tra riêng null, chuỗi rỗng và định dạng sai. Với compact constructor có chuẩn hóa, luôn xác nhận giá trị cuối cùng qua accessor. Chú ý NaN, vô cực, tràn số, scale của BigDecimal và quan hệ giữa nhiều component. Dùng parameterized tests khi nhiều trường hợp cùng một quy tắc, đồng thời giữ test tập trung vào hợp đồng công khai của record.

## Tài liệu tham khảo

- [JUnit Jupiter User Guide — Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests).
- [JUnit Jupiter User Guide — Assertions](https://junit.org/junit5/docs/current/user-guide/#writing-tests-assertions).
- [Java API — Double.isFinite](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Double.html#isFinite(double)).
- [Java API — Math.nextDown and Math.nextUp](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html).
- [Java API — BigDecimal.compareTo](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html#compareTo(java.math.BigDecimal)).
- [Java API — Math exact arithmetic methods](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html).
- [Java Language Specification — Java SE 26, `8.10` Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records (hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
