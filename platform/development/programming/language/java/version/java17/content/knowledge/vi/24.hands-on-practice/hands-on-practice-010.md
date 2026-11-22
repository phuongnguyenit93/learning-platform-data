# Bộ kiểm thử biên, dữ liệu không hợp lệ và tiêu chí nghiệm thu

## 1. Mục tiêu của bộ kiểm thử dữ liệu

Một chức năng nhận dữ liệu đầu vào cần xác định rõ ba điều:

1. Dữ liệu nào được chấp nhận?
2. Dữ liệu nào phải bị từ chối, và hệ thống phản hồi thế nào?
3. Bằng chứng nào cho thấy chức năng đáp ứng yêu cầu nghiệp vụ?

Chỉ kiểm tra một vài ví dụ “bình thường” thường không đủ. Lỗi dễ xuất hiện ở ranh giới: số lượng bằng 0, chuỗi vừa đạt giới hạn độ dài, ngày kết thúc trùng ngày bắt đầu, giá trị null, chuỗi chỉ có whitespace, hoặc dữ liệu có hình thức hợp lệ nhưng vi phạm một điều kiện kết hợp.

Trong Java 17, có thể xây dựng bộ kiểm thử có hệ thống bằng:

- **Equivalence partitioning:** chia miền dữ liệu thành các nhóm có hành vi dự kiến giống nhau.
- **Boundary-value analysis:** tập trung vào giá trị ở ngay ranh giới và sát hai phía của ranh giới.
- **Negative testing:** cung cấp dữ liệu sai, thiếu, vượt giới hạn hoặc không nhất quán.
- **JUnit 5:** kiểm tra ví dụ, tham số hóa test và xác nhận exception.
- **Property-based/fuzz testing:** khám phá nhiều đầu vào theo các thuộc tính hoặc chiến lược sinh dữ liệu.
- **Acceptance criteria:** mô tả điều kiện nghiệm thu có thể quan sát và xác minh.
- **Traceability:** liên kết yêu cầu, tiêu chí nghiệm thu, test case và kết quả chạy.

Một bộ kiểm thử tốt cần bao phủ cả đường thành công và đường thất bại. Việc chỉ kiểm tra rằng constructor ném exception khi gặp null chưa đủ để chứng minh các giá trị hợp lệ ở biên vẫn được chấp nhận.

## 2. Bắt đầu từ contract và miền dữ liệu

### 2.1. Viết contract trước khi viết test

Giả sử chức năng tạo một dòng đơn hàng có các quy tắc:

- SKU bắt buộc, sau khi bỏ whitespace đầu/cuối phải có từ 3 đến 20 ký tự ASCII chữ hoa, số hoặc dấu gạch nối.
- Số lượng là số nguyên từ 1 đến 1000.
- Đơn giá bắt buộc, không âm và có tối đa hai chữ số thập phân.
- Tổng tiền dòng hàng bằng đơn giá nhân số lượng.
- Dữ liệu hợp lệ được lưu trong object bất biến.

Các quy tắc này tạo ra contract để thiết kế test. Nếu chỉ có câu “validate order line”, người viết test sẽ phải tự đoán dữ liệu nào hợp lệ.

### 2.2. Phân biệt điều kiện bắt buộc và điều kiện tùy chọn

Với mỗi field, xác định:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Presence | Field có bắt buộc không? |
| Nullability | Null có được phép không? |
| Blankness | Chuỗi rỗng hoặc chỉ có whitespace có được phép không? |
| Format | Có pattern hoặc tập giá trị được phép không? |
| Range | Giá trị nhỏ nhất/lớn nhất là bao nhiêu? |
| Length | Đo theo byte, UTF-16 code unit, Unicode code point hay grapheme? |
| Precision | Số thập phân có giới hạn scale/rounding không? |
| Relationship | Field có phụ thuộc field khác không? |
| Mutability | Caller có thể sửa dữ liệu sau khi tạo object không? |
| Normalization | Có trim, canonicalize hoặc chuyển đổi trước khi kiểm tra không? |

Không nên viết test dựa trên suy đoán về ý nghĩa của null hoặc chuỗi rỗng. Ví dụ, “ghi chú” có thể được phép null, nhưng “mã đơn hàng” có thể bắt buộc.

### 2.3. Tách validation tại boundary và invariant của domain

Ở API/controller, validation thường giúp trả lỗi thân thiện cho request: thiếu field, sai định dạng, payload quá lớn hoặc enum không được hỗ trợ.

Ở domain object, constructor hoặc factory bảo vệ invariant để object luôn hợp lệ dù được tạo từ HTTP request, batch job, message consumer, test hay code nội bộ.

Ở persistence/database, constraint bảo vệ dữ liệu trước race condition và nhiều writer. Ví dụ, kiểm tra mã khách hàng chưa tồn tại trong Java không thay thế unique constraint ở database.

Ba tầng có mục đích khác nhau. Bộ kiểm thử nên xác nhận từng contract mà tầng đó chịu trách nhiệm.

## 3. Equivalence partitioning — chia lớp tương đương

### 3.1. Ý tưởng

Một miền đầu vào có thể rất lớn hoặc vô hạn. Không cần thử mọi giá trị nếu nhiều giá trị có cùng hành vi theo contract. Chia chúng thành các lớp tương đương, sau đó chọn đại diện cho từng lớp.

Ví dụ với quantity hợp lệ từ 1 đến 1000:

| Lớp | Miền giá trị | Kết quả mong đợi |
|---|---|---|
| Dưới miền | Số nguyên nhỏ hơn 1 | Từ chối |
| Hợp lệ | 1 đến 1000 | Chấp nhận |
| Trên miền | Số nguyên lớn hơn 1000 | Từ chối |
| Sai kiểu tại API | Chuỗi, số thập phân, object | Từ chối theo contract parsing |
| Thiếu/null | Không gửi hoặc gửi null | Tùy contract; ví dụ này từ chối |

Chọn một giá trị đại diện cho mỗi lớp giúp có bộ test gọn nhưng có chủ đích. Tuy nhiên, các ranh giới vẫn cần test riêng.

### 3.2. Chia lớp cho chuỗi

Với SKU:

| Lớp | Ví dụ | Kết quả |
|---|---|---|
| Null | `null` | Từ chối |
| Rỗng | `""` | Từ chối |
| Chỉ whitespace | `"   "` | Từ chối |
| Quá ngắn | `"A1"` | Từ chối |
| Độ dài hợp lệ, ký tự hợp lệ | `"AB-100"` | Chấp nhận |
| Có lowercase nhưng normalization cho phép | `" ab-100 "` | Chuẩn hóa rồi chấp nhận |
| Có dấu cách ở giữa | `"AB 100"` | Từ chối |
| Có ký tự không cho phép | `"AB_100"` | Từ chối |
| Quá dài | Chuỗi dài hơn 20 ký tự | Từ chối |

Điều kiện “lowercase được phép sau normalization” phải có trong contract. Nếu contract yêu cầu đầu vào đã viết hoa, test cần từ chối lowercase thay vì tự chuẩn hóa.

### 3.3. Chia lớp cho ngày tháng

Với khoảng ngày có `end >= start`:

- End trước start: không hợp lệ.
- End bằng start: hợp lệ nếu khoảng thời gian cho phép cùng ngày.
- End sau start: hợp lệ.
- Start null hoặc end null: từ chối nếu cả hai bắt buộc.
- Chuỗi ngày không parse được tại API boundary: trả lỗi định dạng.

Nếu domain yêu cầu end phải sau start, đổi điều kiện thành `end > start`. Chỉ một từ “sau” hay “không trước” cũng làm thay đổi bộ test biên.

### 3.4. Chia lớp cho collection

Với danh sách người tham gia:

- Null collection.
- Collection rỗng.
- Collection có một phần tử hợp lệ.
- Collection ở đúng số phần tử tối đa.
- Collection vượt giới hạn.
- Có phần tử null.
- Có phần tử blank.
- Có phần tử trùng lặp.
- Có phần tử hợp lệ và không hợp lệ trộn lẫn.

Không giả định collection rỗng luôn sai. Một danh sách nhãn tùy chọn có thể được phép rỗng; danh sách dòng hàng của đơn hàng có thể bắt buộc có ít nhất một phần tử.

## 4. Boundary-value analysis — kiểm tra ranh giới

### 4.1. Quy tắc cơ bản

Với một khoảng hợp lệ đóng ([min, max]), những giá trị quan trọng nhất thường là:

- (min - 1): ngay dưới biên dưới.
- (min): đúng biên dưới.
- (min + 1): ngay trên biên dưới.
- (max - 1): ngay dưới biên trên.
- (max): đúng biên trên.
- (max + 1): ngay trên biên trên.

Với quantity từ 1 đến 1000:

| Giá trị | Kết quả |
|---:|---|
| 0 | Từ chối |
| 1 | Chấp nhận |
| 2 | Chấp nhận |
| 999 | Chấp nhận |
| 1000 | Chấp nhận |
| 1001 | Từ chối |

Các giá trị đại diện ở giữa miền có thể bổ sung để kiểm tra xử lý thông thường, nhưng không thay thế sáu điểm biên.

### 4.2. Biên độ dài chuỗi

Nếu SKU có độ dài 3 đến 20:

- 2 ký tự: từ chối.
- 3 ký tự: chấp nhận.
- 4 ký tự: chấp nhận.
- 19 ký tự: chấp nhận.
- 20 ký tự: chấp nhận.
- 21 ký tự: từ chối.

Nếu giới hạn được định nghĩa theo số Unicode code point, không dùng `String.length()` làm thước đo vì method này đếm UTF-16 code units. Có thể dùng:

~~~java
int codePoints = value.codePointCount(0, value.length());
~~~

Nếu yêu cầu nói về ký tự người dùng nhìn thấy, cần xem xét grapheme cluster; một ký tự hiển thị có thể gồm nhiều code point. Đừng tự chọn thước đo mà không xác định contract.

### 4.3. Biên tiền và độ chính xác

Nếu số tiền không âm và có tối đa hai chữ số thập phân, test các trường hợp:

- Giá trị âm nhỏ nhất theo scale được hỗ trợ.
- Zero.
- Giá trị dương nhỏ.
- Giá trị lớn nhất theo business limit.
- Vượt business limit.
- Scale 0, 1, 2.
- Scale 3.
- Giá trị có biểu diễn tương đương nhưng scale khác.

Ví dụ `new BigDecimal("1.0")` và `new BigDecimal("1.00")` có cùng giá trị số khi so sánh bằng `compareTo`, nhưng `equals` trả false vì scale khác. Test phải theo contract: giới hạn số chữ số thập phân hay yêu cầu scale chính xác là hai điều khác nhau.

### 4.4. Biên ngày giờ

Với timestamp hoặc ngày:

- Ngay trước mốc cho phép.
- Đúng mốc.
- Ngay sau mốc.
- Thời điểm chuyển ngày theo timezone.
- Ngày cuối tháng và đầu tháng kế tiếp.
- Ngày nhuận.
- Chuyển đổi giữa UTC và timezone nghiệp vụ.

Không dùng `LocalDate.now()` trực tiếp trong test nếu kỳ vọng phụ thuộc thời gian hiện tại. Truyền `Clock` để cố định thời gian.

### 4.5. Biên kết hợp

Khi có nhiều field, test riêng từng biên chưa chắc phát hiện lỗi kết hợp:

- Start hợp lệ, end hợp lệ nhưng end trước start.
- Quantity hợp lệ, price hợp lệ nhưng tổng tiền vượt giới hạn.
- Country code hợp lệ nhưng postal code không hợp lệ với country đó.
- Discount hợp lệ nhưng lớn hơn subtotal.
- Currency hợp lệ nhưng không được hỗ trợ cho phương thức thanh toán đã chọn.

Đây là cross-field invariants. Hãy thêm test cho các cặp hoặc tổ hợp có ý nghĩa nghiệp vụ.

## 5. Bộ test dữ liệu không hợp lệ

### 5.1. Nhóm lỗi cần xem xét

| Nhóm | Ví dụ | Câu hỏi kiểm thử |
|---|---|---|
| Thiếu dữ liệu | Field không có trong request | Field có bắt buộc không? |
| Null | JSON null hoặc Java null | Null có được phép không? |
| Blank | `""`, `"   "` | Blank có khác null không? |
| Sai format | Mã chứa ký tự cấm | Có bị từ chối trước khi lưu không? |
| Sai range | Số âm hoặc vượt max | Biên được áp dụng inclusive hay exclusive? |
| Sai precision | Tiền có quá nhiều chữ số thập phân | Từ chối hay làm tròn theo contract? |
| Quá lớn | Payload, chuỗi hoặc collection quá dài | Có giới hạn tài nguyên không? |
| Không nhất quán | End date trước start date | Cross-field rule có được kiểm tra? |
| Trùng lặp | ID hoặc item lặp | Có cho phép duplicate không? |
| Unicode bất thường | Ký tự điều khiển, combining mark, confusable | Policy Unicode được thực hiện thế nào? |
| Sai encoding/parsing | Ngày hoặc số không parse được | Lỗi được trả về ổn định không? |
| Sai trạng thái | Chuyển từ trạng thái không hợp lệ | State transition có bị từ chối? |
| Tấn công đầu vào | Payload quá sâu, injection string | Validation có bảo vệ boundary phù hợp không? |

### 5.2. Null và absent không phải lúc nào cũng giống nhau

Trong JSON API, ba trạng thái có thể khác nhau:

1. Field không xuất hiện.
2. Field xuất hiện với giá trị `null`.
3. Field xuất hiện với chuỗi rỗng hoặc giá trị mặc định.

Với API cập nhật một phần, absent có thể mang nghĩa “giữ nguyên”, null có thể mang nghĩa “xóa giá trị”, còn chuỗi rỗng có thể không hợp lệ. Test cần thể hiện rõ contract của từng trạng thái.

Đừng gom absent, null và blank vào một test nếu hệ thống phải xử lý chúng khác nhau.

### 5.3. Sai format và sai ngữ nghĩa

Một chuỗi có thể đúng cú pháp nhưng sai nghiệp vụ:

- Ngày `2026-02-31` có format ISO nhưng không phải ngày lịch hợp lệ.
- Mã có đúng pattern nhưng không tồn tại trong danh mục.
- Currency code đúng cấu trúc nhưng currency không được sản phẩm hỗ trợ.
- Email parse được nhưng địa chỉ chưa được xác minh.

Tách test parsing, domain validation và kiểm tra tham chiếu ngoài. Không để một regex đơn giản gánh mọi tầng validation.

### 5.4. Giới hạn tài nguyên

Dữ liệu không hợp lệ còn có thể là dữ liệu quá lớn:

- Chuỗi vượt giới hạn.
- Array có hàng triệu phần tử.
- JSON lồng nhau quá sâu.
- File upload vượt kích thước.
- Số lượng item khiến phép tính hoặc xử lý vượt budget.

Các giới hạn này bảo vệ tài nguyên và cần được kiểm tra ở boundary trước khi tạo cấu trúc lớn hoặc thực hiện xử lý tốn kém. Test nên xác nhận hệ thống từ chối sớm và trả lỗi có kiểm soát.

## 6. Thiết kế test case có thể thực thi

### 6.1. Test case cần thông tin gì?

Một test case có thể ghi:

| Trường | Nội dung |
|---|---|
| ID | Mã test ổn định |
| Requirement | Yêu cầu hoặc rule liên quan |
| Input | Dữ liệu đầu vào cụ thể |
| Preconditions | Trạng thái cần có trước test |
| Action | Hành động được thực hiện |
| Expected result | Kết quả hoặc exception mong đợi |
| Observable evidence | HTTP response, persisted state, event hoặc output |
| Priority | Mức độ quan trọng |

Test case không nên chỉ ghi “test dữ liệu sai”. Phải chỉ ra dữ liệu nào sai, sai theo quy tắc nào và hệ thống cần phản hồi ra sao.

### 6.2. Positive và negative test

Với mỗi rule, nên có:

- Ít nhất một trường hợp hợp lệ.
- Một hoặc nhiều trường hợp không hợp lệ đại diện.
- Các điểm ngay sát biên.
- Một trường hợp kiểm tra tương tác với rule khác nếu có.

Ví dụ cho quantity:

| Test ID | Input | Expected |
|---|---:|---|
| QTY-001 | 1 | Chấp nhận |
| QTY-002 | 1000 | Chấp nhận |
| QTY-003 | 0 | Từ chối |
| QTY-004 | -1 | Từ chối |
| QTY-005 | 1001 | Từ chối |

### 6.3. Expected result cần cụ thể

Không ghi expected result kiểu “báo lỗi”. Hãy chỉ rõ:

- Constructor ném exception loại nào.
- API trả HTTP status nào theo contract.
- Response có error code nào.
- Dữ liệu sai không được lưu.
- Không phát event hoặc side effect nếu validation thất bại.
- Các field hợp lệ khác có được giữ nguyên hay không.

Không nên kiểm tra quá chặt exception message nếu message không phải public contract. Thường kiểm tra exception type và error code ổn định sẽ ít gắn chặt test với cách diễn đạt nội bộ hơn.

## 7. JUnit 5 cho kiểm thử dữ liệu

### 7.1. Một test cho một hành vi rõ ràng

JUnit Jupiter dùng annotation `@Test`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class QuantityTest {

    @Test
    void acceptsMinimumQuantity() {
        Quantity quantity = new Quantity(1);

        assertEquals(1, quantity.value());
    }
}
~~~

Tên test mô tả điều kiện và kết quả. Khi test thất bại, tên test giúp đọc report mà không cần mở ngay source.

### 7.2. Kiểm tra exception bằng assertThrows

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class QuantityTest {

    @Test
    void rejectsZero() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Quantity(0)
        );
    }
}
~~~

`assertThrows` trả về exception đã bắt, vì vậy có thể kiểm tra error code/message nếu đó là contract cần thiết:

~~~java
IllegalArgumentException exception = assertThrows(
        IllegalArgumentException.class,
        () -> new Quantity(0)
);
assertEquals("quantity must be between 1 and 1000",
        exception.getMessage());
~~~

Không cần khóa chặt toàn bộ message nội bộ nếu API chỉ cam kết exception type. Nếu caller hoặc client cần xử lý theo mã lỗi, hãy thiết kế error code ổn định thay vì phụ thuộc vào câu chữ.

### 7.3. Parameterized tests

Khi nhiều đầu vào có cùng hành vi, dùng `@ParameterizedTest` để tránh lặp code:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class QuantityInvalidInputTest {

    @ParameterizedTest
    @ValueSource(ints = {-1, 0, 1001, 5000})
    void rejectsOutOfRangeValues(int value) {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Quantity(value)
        );
    }
}
~~~

Parameterized test đặc biệt hữu ích cho boundary values, format variants và các lớp dữ liệu không hợp lệ.

### 7.4. Dùng CsvSource để mô tả bảng dữ liệu

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class QuantityBoundaryTest {

    @ParameterizedTest
    @CsvSource({
            "1, true",
            "2, true",
            "999, true",
            "1000, true",
            "0, false",
            "-1, false",
            "1001, false"
    })
    void validatesBoundary(int value, boolean expectedValid) {
        if (expectedValid) {
            assertEquals(value, new Quantity(value).value());
        } else {
            assertThrows(
                    IllegalArgumentException.class,
                    () -> new Quantity(value)
            );
        }
    }
}
~~~

Ví dụ trên minh họa cách biểu diễn bảng test. Trong code thật, có thể tách test positive và negative để failure report dễ đọc hơn, hoặc dùng `assertDoesNotThrow` cho trường hợp hợp lệ.

### 7.5. MethodSource cho test data phức tạp

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class AccountCodeTest {

    static Stream<Arguments> invalidCodes() {
        return Stream.of(
                Arguments.of(""),
                Arguments.of("  "),
                Arguments.of("A1"),
                Arguments.of("AB_100"),
                Arguments.of("AB 100"),
                Arguments.of("A".repeat(21))
        );
    }

    @ParameterizedTest
    @MethodSource("invalidCodes")
    void rejectsInvalidCodes(String code) {
        assertThrows(
                IllegalArgumentException.class,
                () -> AccountCode.of(code)
        );
    }
}
~~~

MethodSource phù hợp khi mỗi case cần nhiều tham số, object mẫu hoặc dữ liệu được tạo bằng code.

### 7.6. assertAll cho nhiều điều kiện độc lập

~~~java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

assertAll(
        () -> assertEquals("AC-100", account.code()),
        () -> assertEquals("An", account.displayName()),
        () -> assertEquals(1, account.quantity())
);
~~~

`assertAll` chạy các assertion độc lập và báo nhiều failure trong cùng test. Không dùng nó để gom những bước phụ thuộc nhau; nếu bước trước thất bại khiến bước sau không còn ý nghĩa, tách test hoặc dùng assertion tuần tự.

### 7.7. assertDoesNotThrow cho giá trị hợp lệ

~~~java
assertDoesNotThrow(() -> new Quantity(1000));
~~~

Thông thường, tốt hơn là giữ object được tạo và assert trạng thái:

~~~java
Quantity quantity = assertDoesNotThrow(() -> new Quantity(1000));
assertEquals(1000, quantity.value());
~~~

Điều này vừa xác nhận không có exception vừa kiểm tra kết quả.

## 8. Ví dụ domain model và bộ kiểm thử biên

### 8.1. Class Quantity

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value < 1 || value > 1000) {
            throw new IllegalArgumentException(
                    "quantity must be between 1 and 1000"
            );
        }
    }
}
~~~

Record compact constructor bảo vệ invariant ở mọi đường tạo instance.

### 8.2. Test toàn bộ biên

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class QuantityTest {

    @Test
    void acceptsLowerAndUpperBounds() {
        assertEquals(1, new Quantity(1).value());
        assertEquals(1000, new Quantity(1000).value());
    }

    @Test
    void acceptsValuesImmediatelyInsideBounds() {
        assertEquals(2, new Quantity(2).value());
        assertEquals(999, new Quantity(999).value());
    }

    @Test
    void rejectsValuesImmediatelyOutsideBounds() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Quantity(0)
        );
        assertThrows(
                IllegalArgumentException.class,
                () -> new Quantity(1001)
        );
    }
}
~~~

Các test chia theo ý nghĩa, nên khi boundary thay đổi sẽ biết nhóm test nào cần cập nhật.

### 8.3. Test null và blank riêng biệt

Với String, null và blank là các lớp khác nhau:

~~~java
@Test
void rejectsNullCode() {
    assertThrows(
            NullPointerException.class,
            () -> AccountCode.of(null)
    );
}

@ParameterizedTest
@ValueSource(strings = {"", " ", "   ", "\t", "\n"})
void rejectsBlankCode(String value) {
    assertThrows(
            IllegalArgumentException.class,
            () -> AccountCode.of(value)
    );
}
~~~

Các ký tự whitespace cần được chọn theo contract. Nếu code dùng `strip()` và `isBlank()`, hãy thêm test với các whitespace Unicode mà hệ thống cần hỗ trợ.

## 9. Kiểm thử chuẩn hóa và Unicode

### 9.1. Kiểm tra đầu vào được canonicalize đúng

Nếu contract cho phép strip và uppercase:

~~~java
@ParameterizedTest
@CsvSource({
        "' ac-100 ', AC-100",
        "ac-100, AC-100",
        "AC-100, AC-100"
})
void normalizesAccountCode(String input, String expected) {
    assertEquals(expected, AccountCode.of(input).value());
}
~~~

Test cần xác nhận cả giá trị được lưu, không chỉ xác nhận constructor không ném exception.

### 9.2. Kiểm tra normalization idempotence

Nếu hàm chuẩn hóa có contract idempotent:

~~~java
String once = normalize(input);
String twice = normalize(once);
assertEquals(once, twice);
~~~

Tính chất này giúp phát hiện hàm chuẩn hóa tạo ra giá trị thay đổi qua mỗi lần xử lý.

### 9.3. Test Unicode theo thước đo đã chọn

Nếu giới hạn theo code point:

~~~java
int count = value.codePointCount(0, value.length());
~~~

Tạo test với:

- Ký tự ASCII.
- Ký tự ngoài Basic Multilingual Plane.
- Ký tự có combining mark.
- Chuỗi NFC và NFD tương đương.
- Ký tự điều khiển nếu policy cấm.
- Ký tự nhìn giống nhau nhưng khác code point nếu identifier nhạy cảm.

Không dùng một test “tiếng Việt có dấu” để kết luận toàn bộ Unicode đã được xử lý. Test cần gắn với normalization form, character policy và cách đo length cụ thể.

### 9.4. Không phụ thuộc default locale

Với identifier dùng `Locale.ROOT`, test nên xác nhận kết quả không đổi khi default locale của JVM thay đổi. Có thể lưu locale cũ, đổi locale trong test và khôi phục trong finally; cần tránh chạy song song các test cùng thay đổi global default locale.

Một cách khác là kiểm tra trực tiếp helper luôn truyền `Locale.ROOT`, đồng thời dùng input có case mapping nhạy cảm theo locale để chứng minh behavior.

## 10. Kiểm thử ngày giờ một cách xác định

### 10.1. Tránh phụ thuộc đồng hồ thật

Test như sau có thể trở nên flaky khi qua ngày:

~~~java
assertTrue(expiry.isAfter(LocalDate.now()));
~~~

Nếu constructor/service gọi thời gian hiện tại ẩn, kết quả phụ thuộc ngày chạy test và timezone môi trường.

### 10.2. Truyền Clock

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC
);
~~~

Service nhận `Clock` qua constructor:

~~~java
final class ExpiryPolicy {
    private final Clock clock;

    ExpiryPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    boolean isExpired(Instant expiry) {
        return !expiry.isAfter(clock.instant());
    }
}
~~~

Test biên:

~~~java
@Test
void treatsExactExpiryInstantAsExpired() {
    Instant now = Instant.parse("2026-01-15T10:00:00Z");
    Clock clock = Clock.fixed(now, ZoneOffset.UTC);
    ExpiryPolicy policy = new ExpiryPolicy(clock);

    assertTrue(policy.isExpired(now.minusNanos(1)));
    assertTrue(policy.isExpired(now));
    assertFalse(policy.isExpired(now.plusNanos(1)));
}
~~~

Định nghĩa đúng behavior tại thời điểm bằng expiry: ví dụ trên coi `expiry <= now` là hết hạn. Nếu contract khác, thay expected result.

### 10.3. Test timezone và DST

Nếu nghiệp vụ dựa trên ngày địa phương, xác định timezone rõ bằng `ZoneId`, không dựa vào timezone mặc định của máy. Test các thời điểm:

- Trước và sau nửa đêm ở timezone nghiệp vụ.
- Chuyển DST nếu timezone có áp dụng.
- Ngày nhuận.
- Ngày cuối tháng/năm.

Không phải hệ thống nào cũng cần test DST; chỉ thêm khi domain sử dụng timezone có DST hoặc tính toán thời gian địa phương.

## 11. Kiểm thử cross-field và bảng quyết định

### 11.1. Bảng quyết định

Khi kết quả phụ thuộc nhiều điều kiện, bảng quyết định giúp không bỏ sót tổ hợp:

| Start có giá trị? | End có giá trị? | End >= Start? | Kết quả |
|---|---|---|---|
| Không | Có | Không áp dụng | Từ chối |
| Có | Không | Không áp dụng | Từ chối |
| Có | Có | Không | Từ chối |
| Có | Có | Có | Chấp nhận |

Với nhiều boolean condition, không nhất thiết phải test mọi tổ hợp nếu một số tổ hợp không thể xảy ra hoặc có behavior tương đương. Ghi lại lý do chọn test.

### 11.2. Test range kết hợp

~~~java
public record DateRange(LocalDate start, LocalDate end) {
    public DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");
        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                    "end must not be before start"
            );
        }
    }
}
~~~

~~~java
@Test
void acceptsSameDayRange() {
    LocalDate day = LocalDate.of(2026, 5, 10);
    assertEquals(day, new DateRange(day, day).end());
}

@Test
void rejectsEndBeforeStart() {
    LocalDate start = LocalDate.of(2026, 5, 11);
    LocalDate end = LocalDate.of(2026, 5, 10);

    assertThrows(
            IllegalArgumentException.class,
            () -> new DateRange(start, end)
    );
}
~~~

### 11.3. Pairwise testing

Khi có nhiều field độc lập với nhiều giá trị, tích Descartes của tất cả lựa chọn có thể tạo số lượng test rất lớn. Pairwise testing chọn tập test sao cho mỗi cặp giá trị giữa hai tham số xuất hiện ít nhất một lần.

Pairwise hữu ích khi lỗi thường xuất hiện từ tương tác hai yếu tố, nhưng không thay thế test cho invariant quan trọng có tương tác ba hoặc nhiều yếu tố. Những rule nghiệp vụ cụ thể vẫn cần test trực tiếp.

## 12. Kiểm thử API với dữ liệu không hợp lệ

### 12.1. Xác định contract HTTP

Với API tạo đơn hàng, có thể xác định:

- Request hợp lệ: trả status thành công và resource được tạo.
- JSON sai cú pháp: trả lỗi parsing theo API contract.
- Field bắt buộc thiếu/null: trả validation error.
- Quantity ngoài range: trả lỗi field-level.
- Reference không tồn tại: trả lỗi nghiệp vụ phù hợp.
- Request vượt giới hạn payload: từ chối trước khi xử lý sâu.

Không có một HTTP status duy nhất đúng cho mọi API; cần theo contract sản phẩm. Thông thường, lỗi cú pháp/validation của client thuộc nhóm 4xx, còn lỗi hệ thống thuộc nhóm 5xx. Test phải khớp API contract đã công bố.

### 12.2. Kiểm tra response, không chỉ status

Một response validation hữu ích có thể có:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "quantity",
      "code": "OUT_OF_RANGE",
      "message": "quantity must be between 1 and 1000"
    }
  ]
}
~~~

Đây là ví dụ minh họa schema, không phải tiêu chuẩn bắt buộc. Test nên kiểm tra:

- Status code.
- Error code ổn định.
- Field liên quan.
- Không trả stack trace hoặc thông tin nội bộ.
- Không tạo resource hoặc side effect khi request bị từ chối.

Nếu message dành cho người dùng có thể được bản địa hóa, ưu tiên assert error code và field thay vì so khớp câu chữ cố định.

### 12.3. Kiểm tra không có side effect

Khi validation thất bại, xác nhận:

- Không có record mới trong database.
- Không phát message/event.
- Không trừ tiền hoặc thay đổi inventory.
- Không gọi dịch vụ downstream nếu validation phải diễn ra trước bước đó.

Đây là phần quan trọng của negative testing. Chỉ xác nhận API trả 400 nhưng database vẫn ghi dữ liệu sai là chưa đủ.

### 12.4. Kiểm tra lỗi parsing và validation riêng

JSON sai cú pháp khác với JSON đúng cú pháp nhưng dữ liệu sai:

```json
{"quantity":
```

so với:

```json
{"quantity": 0}
```

Trường hợp đầu là parse error; trường hợp sau là validation error. Nếu API có error contract khác nhau, test cần xác nhận chúng không bị gom nhầm.

## 13. Kiểm thử dữ liệu tại persistence boundary

### 13.1. Validation Java không thay thế database constraint

Hai request đồng thời có thể cùng kiểm tra “email chưa tồn tại” rồi cùng insert. Nếu uniqueness là invariant dữ liệu, database cần unique constraint hoặc cơ chế transaction phù hợp.

Test integration nên xác nhận:

- Một insert hợp lệ thành công.
- Insert trùng bị từ chối theo contract.
- Concurrent insert không tạo duplicate.
- Transaction rollback khi constraint thất bại.

Không chỉ mock repository rồi kết luận constraint hoạt động; cần integration test với database tương ứng hoặc test container phù hợp.

### 13.2. Kiểm tra precision và column length

Nếu Java cho phép dữ liệu rộng hơn schema database, lỗi chỉ xuất hiện lúc persistence. Contract phải thống nhất:

- Column length.
- Numeric precision/scale.
- Nullability.
- Unique constraints.
- Foreign key constraints.
- Check constraints.

Test boundary cần xác nhận giá trị hợp lệ ở max database limit lưu và đọc lại đúng, còn giá trị vượt giới hạn bị từ chối có kiểm soát.

### 13.3. Không phụ thuộc database default

Nếu code dựa vào default timezone, collation hoặc case sensitivity của database, test có thể khác nhau giữa developer và production. Cấu hình rõ và chạy integration test với engine/version gần production.

## 14. Property-based testing và fuzz testing

### 14.1. Example-based testing có giới hạn

JUnit parameterized test rất phù hợp với các case đã biết. Nhưng một input space lớn có thể chứa nhiều trường hợp chưa được nghĩ tới.

Property-based testing kiểm tra một thuộc tính trên nhiều input được sinh tự động. Có thể dùng thư viện như jqwik hoặc công cụ tương tự trong dự án nếu được chấp thuận; đây là dependency test bổ sung, không thuộc JDK 17.

### 14.2. Ví dụ thuộc tính normalization idempotent

Với hàm normalize:

```text
normalize(normalize(x)) == normalize(x)
~~~

Thuộc tính này có thể kiểm tra trên nhiều chuỗi được sinh. Nếu fail, có thể normalization không ổn định hoặc có bug ở xử lý Unicode.

### 14.3. Ví dụ thuộc tính range

Với constructor `Quantity`:

- Mọi integer từ 1 đến 1000 đều tạo được object.
- Mọi integer nhỏ hơn 1 hoặc lớn hơn 1000 đều bị từ chối.
- Giá trị được lưu luôn bằng input hợp lệ.

Đây là property đơn giản có thể sinh số ngẫu nhiên hoặc kiểm tra exhaustive cho toàn bộ miền int nếu cần, nhưng không cần chạy hàng tỷ giá trị trong test suite thông thường.

### 14.4. Fuzzing dữ liệu parsing

Fuzz test có thể tạo:

- Chuỗi Unicode ngẫu nhiên.
- JSON sai cấu trúc.
- Chuỗi rất dài.
- Ký tự điều khiển.
- Nested structures sâu.
- Number lớn hoặc biểu diễn exponent.

Mục tiêu không chỉ là “không crash”. Cần xác định behavior mong đợi: reject an toàn, không treo, không dùng tài nguyên quá mức và không tạo side effect.

### 14.5. Seed và khả năng tái hiện

Test sinh dữ liệu cần ghi lại seed hoặc input gây lỗi để tái hiện. Nếu không thể lặp lại failure, rất khó biến phát hiện từ fuzzing thành regression test.

Khi tìm được input gây lỗi:

1. Lưu input tối thiểu gây lỗi.
2. Viết test deterministic tái hiện.
3. Sửa nguyên nhân.
4. Giữ regression test trong suite.

## 15. Tiêu chí nghiệm thu (Acceptance Criteria)

### 15.1. Acceptance criteria khác test case

Acceptance criteria mô tả điều kiện mà chức năng phải đáp ứng để được chấp nhận. Test case là một cách cụ thể để xác minh điều kiện đó.

Một tiêu chí tốt:

- Có thể quan sát.
- Có kết quả pass/fail rõ.
- Gắn với hành vi nghiệp vụ.
- Không phụ thuộc chi tiết implementation không cần thiết.
- Bao gồm cả dữ liệu hợp lệ và không hợp lệ khi cần.

### 15.2. Viết theo Given–When–Then

Ví dụ:

~~~text
Given quantity is an integer from 1 through 1000
When the order line is created
Then the line is accepted and preserves the quantity

Given quantity is 0
When the order line is created
Then creation is rejected with OUT_OF_RANGE

Given the request contains an invalid quantity
When the API receives the request
Then no order line is persisted
~~~

Given–When–Then giúp người viết, developer, tester và product owner hiểu cùng một behavior.

### 15.3. Tiêu chí nghiệm thu mẫu

Với chức năng tạo order line:

| ID | Acceptance criterion | Evidence |
|---|---|---|
| AC-01 | SKU hợp lệ sau normalization được chấp nhận | Unit test kiểm tra giá trị canonical |
| AC-02 | SKU null, blank hoặc sai pattern bị từ chối | Parameterized negative tests |
| AC-03 | Quantity từ 1 đến 1000 được chấp nhận | Boundary tests tại 1, 2, 999, 1000 |
| AC-04 | Quantity ngoài range bị từ chối | Tests tại 0, -1, 1001 |
| AC-05 | Unit price không âm và có scale theo contract | Decimal boundary tests |
| AC-06 | Input collection/array không làm thay đổi state sau khi object tạo | Defensive-copy tests |
| AC-07 | Request lỗi trả error contract đã công bố | API integration tests |
| AC-08 | Request lỗi không ghi dữ liệu hoặc phát event | Persistence/message integration tests |
| AC-09 | Giá trị hợp lệ ở giới hạn database lưu và đọc đúng | Persistence boundary test |
| AC-10 | Validation không phụ thuộc clock/locale máy test | Fixed Clock và locale-specific tests |

### 15.4. Tiêu chí không nên mơ hồ

Mơ hồ:

- “Hệ thống xử lý dữ liệu tốt.”
- “Không được nhập quá dài.”
- “Ngày phải hợp lệ.”
- “Lỗi phải thân thiện.”

Cụ thể hơn:

- “SKU sau normalization phải có từ 3 đến 20 Unicode code point và chỉ chứa tập ký tự được định nghĩa.”
- “End date không được trước start date; hai ngày bằng nhau được chấp nhận.”
- “Request sai quantity trả error code `OUT_OF_RANGE` và không tạo order.”
- “Payload vượt 1 MiB bị từ chối trước khi gọi service xử lý nghiệp vụ.”

Chỉ đưa số giới hạn cụ thể vào acceptance criteria khi sản phẩm/domain đã quyết định. Người viết test không tự đặt business rule.

## 16. Ma trận truy vết yêu cầu và test

### 16.1. Vì sao cần traceability?

Khi một yêu cầu thay đổi, nhóm cần biết test nào liên quan và feature nào có thể bị ảnh hưởng. Ma trận truy vết liên kết:

```text
Requirement
    |
    v
Acceptance Criterion
    |
    v
Test Case
    |
    v
Automated Test / Manual Evidence
    |
    v
Execution Result
~~~

### 16.2. Ví dụ ma trận

| Requirement | Acceptance criteria | Test IDs | Loại test |
|---|---|---|---|
| SKU normalization | AC-01 | SKU-001..SKU-004 | Unit |
| SKU validation | AC-02 | SKU-005..SKU-012 | Parameterized unit |
| Quantity range | AC-03, AC-04 | QTY-001..QTY-006 | Boundary unit |
| Price precision | AC-05 | PRICE-001..PRICE-008 | Unit |
| Defensive copy | AC-06 | IMM-001..IMM-003 | Unit |
| API error contract | AC-07 | API-VAL-001..API-VAL-005 | Integration |
| No side effects | AC-08 | API-VAL-006, DB-VAL-001 | Integration |
| Database limits | AC-09 | DB-VAL-002..DB-VAL-004 | Persistence |
| Deterministic rules | AC-10 | TIME-001..TIME-004 | Unit |

ID là ví dụ để tổ chức suite. Project thật cần dùng convention test ID của nhóm.

### 16.3. Không đo chất lượng chỉ bằng số lượng test

Một trăm test lặp lại cùng một happy path có thể kém giá trị hơn mười test bao phủ đúng ranh giới và cross-field rule. Đánh giá suite bằng:

- Rule quan trọng có test không?
- Biên có được bao phủ không?
- Negative path có xác minh side effect không?
- Có test integration cho constraint ngoài JVM không?
- Test có deterministic và dễ tái hiện không?
- Khi requirement đổi, có biết test nào cần cập nhật không?

Code coverage là một tín hiệu bổ sung, không chứng minh acceptance criteria đã được xác minh đầy đủ.

## 17. Tiêu chí hoàn tất bộ kiểm thử

Một bộ test dữ liệu có thể được xem là sẵn sàng nghiệm thu khi:

1. Mỗi rule nghiệp vụ có ít nhất một test hợp lệ và một test không hợp lệ phù hợp.
2. Các giá trị ở biên dưới/trên được kiểm tra rõ.
3. Null, absent, blank và malformed được phân biệt theo contract.
4. Cross-field invariants có test.
5. Normalization được kiểm tra bằng output cụ thể và tính chất cần thiết.
6. Mutable input không thể thay đổi object sau khi tạo.
7. API errors có status/code/field theo contract.
8. Negative request không tạo side effect ngoài dự kiến.
9. Database constraints được kiểm tra ở integration level khi có liên quan.
10. Time, locale và timezone được cố định trong test cần tính xác định.
11. Test chạy ổn định, không phụ thuộc thứ tự hoặc dữ liệu môi trường không được kiểm soát.
12. Acceptance criteria có evidence và traceability tới test.

Đây là tiêu chí lập kế hoạch cho feature; không phải lý do để tạo test không có giá trị chỉ nhằm đạt một con số.

## 18. Tổ chức test suite và dữ liệu dùng chung

### 18.1. Tách test theo rule

Ví dụ cấu trúc:

~~~text
src/test/java/
└── com/acme/order/
    ├── QuantityTest.java
    ├── AccountCodeTest.java
    ├── MoneyTest.java
    ├── DateRangeTest.java
    ├── OrderLineTest.java
    ├── OrderApiValidationTest.java
    └── OrderPersistenceTest.java
~~~

Tách theo domain rule hoặc test layer giúp người bảo trì tìm đúng test cần sửa khi contract thay đổi.

### 18.2. Test data builder

Khi object có nhiều field, builder test có thể tạo fixture hợp lệ mặc định và chỉ thay field đang kiểm tra:

~~~java
final class OrderLineFixture {
    private String sku = "AB-100";
    private int quantity = 2;
    private BigDecimal unitPrice = new BigDecimal("10.00");

    OrderLineFixture withSku(String value) {
        this.sku = value;
        return this;
    }

    OrderLineFixture withQuantity(int value) {
        this.quantity = value;
        return this;
    }

    OrderLineFixture withUnitPrice(BigDecimal value) {
        this.unitPrice = value;
        return this;
    }

    OrderLine build() {
        return new OrderLine(sku, quantity, unitPrice);
    }
}
~~~

Trong test:

~~~java
OrderLine line = new OrderLineFixture()
        .withQuantity(1000)
        .build();
~~~

Fixture cần có default hợp lệ. Nếu default vô tình vi phạm rule mới, nhiều test không liên quan có thể fail. Hãy giữ builder đơn giản và không giấu logic nghiệp vụ phức tạp trong fixture.

### 18.3. Tránh shared mutable test data

Không chia sẻ một List/Map mutable giữa nhiều test nếu một test có thể thay đổi nó. Tạo fixture mới cho từng test hoặc dùng collection immutable. Test độc lập sẽ ít flaky hơn khi chạy song song.

### 18.4. Test data không nên chứa thông tin thật

Dùng dữ liệu giả lập, deterministic và không nhạy cảm. Không copy dữ liệu khách hàng, token, email thật hoặc thông tin production vào test fixture/log. Nếu cần dữ liệu gần thực tế, tạo dữ liệu synthetic có cùng đặc tính kỹ thuật.

## 19. Chẩn đoán test thất bại

### 19.1. Phân biệt bug code và bug test

Khi test boundary fail:

1. Đọc expected/actual và input chính xác.
2. Kiểm tra contract có thay đổi hay không.
3. Kiểm tra test đang dùng đúng đơn vị đo (byte, code point, scale, timezone).
4. Kiểm tra normalization xảy ra trước hay sau validation theo contract.
5. Kiểm tra test có phụ thuộc locale/time/default timezone không.
6. Kiểm tra dữ liệu dùng chung có bị thay đổi bởi test khác không.

Không sửa expected result chỉ để test xanh nếu chưa xác nhận requirement.

### 19.2. Test flaky

Nguyên nhân thường gặp:

- Dùng thời gian hệ thống trực tiếp.
- Dùng random input nhưng không ghi seed.
- Phụ thuộc thứ tự test.
- Chia sẻ file/database/resource giữa test.
- Test chạy song song nhưng sửa global state.
- Phụ thuộc locale/timezone hoặc môi trường host.

Khắc phục bằng fixed clock, seed xác định, fixture riêng, cleanup và cấu hình môi trường rõ ràng.

### 19.3. Failure chỉ xuất hiện trên database hoặc API

Nếu unit test pass nhưng integration test fail:

- So sánh validation giữa DTO/domain/database.
- Kiểm tra column precision/length và collation.
- Kiểm tra transaction/constraint.
- Kiểm tra JSON deserialization và absent/null semantics.
- Kiểm tra encoding/timezone.

Đừng thêm logic vào constructor chỉ để làm một lỗi database biến mất nếu nguyên nhân thực sự là schema hoặc mapping.

## 20. Ví dụ tổng hợp: acceptance criteria và test cho OrderLine

### 20.1. Domain contract

~~~java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Objects;

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice
) {
    public OrderLine {
        sku = normalizeSku(sku);

        if (quantity < 1 || quantity > 1000) {
            throw new IllegalArgumentException(
                    "quantity must be between 1 and 1000"
            );
        }

        unitPrice = Objects.requireNonNull(
                unitPrice,
                "unitPrice must not be null"
        );

        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                    "unitPrice must not be negative"
            );
        }

        if (unitPrice.scale() > 2) {
            throw new IllegalArgumentException(
                    "unitPrice must have at most two decimal places"
            );
        }
    }

    private static String normalizeSku(String rawSku) {
        Objects.requireNonNull(rawSku, "sku must not be null");
        String value = rawSku.strip().toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z0-9-]{3,20}")) {
            throw new IllegalArgumentException("sku has invalid format");
        }
        return value;
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

Ví dụ này cố định scale tối đa là 2 và không làm tròn. Trong domain thật, quyết định đó phải đến từ quy tắc tiền tệ và business contract.

### 20.2. Acceptance criteria

~~~text
AC-01: A valid SKU is trimmed and uppercased using locale-independent rules.
AC-02: Null, blank, malformed, too-short and too-long SKUs are rejected.
AC-03: Quantity 1 and 1000 are accepted.
AC-04: Quantity 0, negative and greater than 1000 are rejected.
AC-05: Unit price is required and cannot be negative.
AC-06: Unit price with scale greater than 2 is rejected.
AC-07: Line total equals unit price multiplied by quantity.
AC-08: Invalid input does not create or persist an order line.
~~~

### 20.3. Test biên và dữ liệu sai

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class OrderLineTest {

    @Test
    void normalizesSku() {
        OrderLine line = new OrderLine(
                " ab-100 ",
                1,
                new BigDecimal("10.00")
        );

        assertEquals("AB-100", line.sku());
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 2, 999, 1000})
    void acceptsQuantityInsideAndAtBounds(int quantity) {
        OrderLine line = new OrderLine(
                "AB-100",
                quantity,
                new BigDecimal("10.00")
        );

        assertEquals(quantity, line.quantity());
    }

    @ParameterizedTest
    @ValueSource(ints = {-1, 0, 1001, 5000})
    void rejectsQuantityOutsideBounds(int quantity) {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine(
                        "AB-100",
                        quantity,
                        new BigDecimal("10.00")
                )
        );
    }

    @ParameterizedTest
    @ValueSource(strings = {"", " ", "AB", "AB_100", "AB 100"})
    void rejectsInvalidSku(String sku) {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine(
                        sku,
                        1,
                        new BigDecimal("10.00")
                )
        );
    }

    @Test
    void rejectsNullSku() {
        assertThrows(
                NullPointerException.class,
                () -> new OrderLine(
                        null,
                        1,
                        new BigDecimal("10.00")
                )
        );
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine(
                        "AB-100",
                        1,
                        new BigDecimal("-0.01")
                )
        );
    }

    @Test
    void rejectsPriceWithTooManyFractionDigits() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine(
                        "AB-100",
                        1,
                        new BigDecimal("10.001")
                )
        );
    }

    @Test
    void calculatesLineTotal() {
        OrderLine line = new OrderLine(
                "AB-100",
                3,
                new BigDecimal("10.25")
        );

        assertEquals(
                new BigDecimal("30.75"),
                line.lineTotal()
        );
    }
}
~~~

### 20.4. Kiểm tra tính nhất quán của ví dụ

Với contract trên:

- `" ab-100 "` được strip và uppercase thành `"AB-100"`.
- `"AB"` bị từ chối vì quá ngắn.
- `"AB_100"` bị từ chối vì underscore không thuộc pattern.
- Quantity 1 và 1000 được chấp nhận.
- Quantity 0 và 1001 bị từ chối.
- Giá trị âm bị từ chối.
- Scale 3 bị từ chối, không tự làm tròn.

Khi thay đổi contract, cần cập nhật acceptance criteria và test tương ứng cùng lúc.

## 21. Bài tập thực hành

### Bài 1 — Lập equivalence partitions

Chọn một field như username, quantity hoặc discount. Liệt kê các lớp hợp lệ/không hợp lệ và chọn ít nhất một giá trị đại diện cho mỗi lớp. Giải thích vì sao các giá trị trong một lớp có behavior tương đương.

### Bài 2 — Lập boundary matrix

Với range từ 5 đến 50, viết test cho 4, 5, 6, 49, 50 và 51. Thêm một giá trị giữa miền. Tách expected result rõ ràng.

### Bài 3 — Phân biệt absent/null/blank

Thiết kế API cập nhật profile. Xác định semantics của field không gửi, gửi null, chuỗi rỗng và chuỗi chỉ whitespace. Viết test cho từng trường hợp.

### Bài 4 — Kiểm thử Unicode

Tạo input NFC/NFD tương đương, input có code point ngoài BMP và input có combining marks. Xác định giới hạn length tính theo code unit hay code point, rồi viết test.

### Bài 5 — Kiểm thử tiền

Tạo value object Money với currency và BigDecimal. Xác định scale, rounding và range. Viết test zero, âm, biên lớn nhất, scale tối đa và scale vượt giới hạn.

### Bài 6 — Cross-field invariants

Tạo DateRange và DiscountPolicy. Viết bảng quyết định cho các tổ hợp input. Bao gồm trường hợp end trước start và discount lớn hơn subtotal.

### Bài 7 — Kiểm thử defensive copy

Tạo class nhận List và byte array. Thay đổi input sau constructor và thay đổi giá trị trả về từ accessor. Xác nhận object không đổi.

### Bài 8 — Parameterized tests

Chuyển bộ test quantity và SKU sang `@ParameterizedTest`, `@ValueSource`, `@CsvSource` hoặc `@MethodSource`. Đặt tên test thể hiện rõ nhóm dữ liệu.

### Bài 9 — Fixed Clock

Viết policy hết hạn nhận `Clock`. Test thời điểm trước, bằng và sau expiry bằng `Clock.fixed`. Không dùng clock thật trong assertion.

### Bài 10 — API negative tests

Gửi request sai format, thiếu field và sai range. Kiểm tra status/error code/field và xác nhận không có database write hoặc event.

### Bài 11 — Acceptance criteria

Viết ít nhất năm tiêu chí Given–When–Then cho một chức năng tạo resource. Mỗi tiêu chí phải có test ID và evidence.

### Bài 12 — Regression từ fuzz input

Tạo chuỗi Unicode hoặc JSON bất thường. Khi tìm được input gây lỗi, lưu thành test deterministic để ngăn regression.

## 22. Câu hỏi tự kiểm tra

1. Equivalence partitioning giúp giảm số test như thế nào?
2. Boundary-value analysis cần những điểm nào cho một khoảng đóng?
3. Vì sao test đúng min/max quan trọng hơn chỉ test một giá trị giữa miền?
4. Null, absent và blank khác nhau thế nào trong API?
5. Sai format khác sai ngữ nghĩa ra sao?
6. Khi nào cần cross-field validation?
7. Vì sao test negative cần xác nhận không có side effect?
8. `@ParameterizedTest` phù hợp với loại dữ liệu nào?
9. Khi nào dùng `@MethodSource` thay vì `@ValueSource`?
10. `assertThrows` xác nhận điều gì?
11. Khi nào nên kiểm tra exception message và khi nào nên kiểm tra error code?
12. Vì sao không nên dùng clock thật trong test hết hạn?
13. Pairwise testing có giới hạn gì?
14. Property-based testing khác example-based testing thế nào?
15. Vì sao fuzz test cần seed hoặc input có thể tái hiện?
16. Acceptance criteria khác test case thế nào?
17. Traceability matrix giúp ích gì khi requirement thay đổi?
18. Vì sao code coverage cao không chứng minh boundary coverage đầy đủ?
19. Vì sao database unique constraint vẫn cần dù Java đã kiểm tra trước?
20. Làm thế nào để test suite không phụ thuộc locale, timezone và thứ tự chạy?

## 23. Tài liệu tham khảo

- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): Jupiter, parameterized tests, assertions và test lifecycle.
- [JUnit 5 API — Assertions](https://junit.org/junit5/docs/current/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html): `assertThrows`, `assertAll`, `assertDoesNotThrow` và assertion API.
- [JUnit 5 API — ParameterizedTest](https://junit.org/junit5/docs/current/api/org.junit.jupiter.params/org/junit/jupiter/params/ParameterizedTest.html): khai báo parameterized tests.
- [Java SE 17 API — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): clock có thể cố định để kiểm thử xác định.
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): length, code point và các thao tác chuỗi.
- [Java SE 17 API — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode normalization.
- [Java SE 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): scale, precision, compareTo và phép toán decimal.
- [ISTQB Glossary](https://glossary.istqb.org/): thuật ngữ kiểm thử như equivalence partitioning, boundary value analysis và acceptance testing.

Một bộ kiểm thử biên có giá trị bắt đầu từ contract rõ ràng. Hãy chia dữ liệu thành lớp tương đương, kiểm tra ngay dưới/tại/ngay trên ranh giới, thêm negative cases cho null, blank, format và cross-field rules, rồi xác nhận cả kết quả lẫn side effect. Dùng JUnit 5 để tổ chức test có thể lặp lại, cố định thời gian/locale khi cần và liên kết từng acceptance criterion với bằng chứng. Như vậy, bộ test chứng minh được hành vi của ứng dụng với cả dữ liệu hợp lệ lẫn dữ liệu không hợp lệ trên Java 17.
