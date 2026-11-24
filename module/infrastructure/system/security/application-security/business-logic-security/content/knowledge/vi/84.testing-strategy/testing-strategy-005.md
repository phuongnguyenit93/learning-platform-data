# Kiểm thử phép tính tài chính (Financial calculation tests)

Trong chương **Testing Strategy** của module bảo vệ logic nghiệp vụ, kiểm thử phép tính tài chính nhằm chứng minh hai điều: hệ thống tính đúng theo chính sách đã công bố và người dùng không thể thao túng đầu vào, thứ tự thao tác hoặc số lần gửi yêu cầu để nhận một kết quả tài chính trái phép.

Một hàm cộng tiền có thể hoàn toàn đúng nhưng luồng thanh toán vẫn có lỗ hổng nếu máy chủ tin `total` từ trình duyệt. Một lệnh hoàn tiền có thể tính đúng từng lần nhưng tổng hoàn vượt số tiền đã thu khi hai yêu cầu chạy đồng thời. Vì vậy, bài học này kết hợp kiểm thử số học với các bất biến nghiệp vụ, quyền theo đối tượng, trạng thái đơn hàng, transaction và idempotency.

Các mức thuế, giới hạn tiền và chính sách ưu đãi dưới đây là **quy tắc giả định của hệ thống minh họa**, không phải hướng dẫn thuế hay kế toán. Khi áp dụng, đội sản phẩm phải xác nhận công thức và chính sách thực tế trước khi biến chúng thành kết quả mong đợi của test.

## 1. Xác định điều cần bảo vệ trước khi viết test

### 1.1. Kết quả tài chính là một hợp đồng nghiệp vụ

Một phép tính tiền không được xác định đầy đủ chỉ bằng biểu thức `price * quantity`. Hợp đồng còn phải trả lời:

- Giá lấy từ bảng giá nào, tại thời điểm nào và phiên bản nào?
- Đơn vị tiền tệ là gì, có bao nhiêu chữ số thập phân được hệ thống hỗ trợ?
- Ưu đãi phần trăm và ưu đãi cố định được kết hợp ra sao?
- Thuế áp dụng trước hay sau giảm giá; phí vận chuyển có nằm trong cơ sở tính thuế không?
- Làm tròn từng dòng hay toàn đơn; làm tròn ở bước nào và theo chế độ nào?
- Đơn đã thanh toán có được tính lại theo bảng giá mới không?
- Hoàn một phần phân bổ giảm giá, thuế và phí thế nào?
- Ai có quyền thay đổi giá, áp dụng mã giảm giá hoặc yêu cầu hoàn tiền?

Nếu chưa có câu trả lời, một expected value duy nhất có thể chỉ đang khóa một giả định sai vào bộ test. Phải chốt quy tắc trước, rồi dùng quy tắc đó để phân biệt hành vi hợp lệ với hành vi lạm dụng.

### 1.2. Các bất biến tài chính tiêu biểu

| Bất biến | Cách kiểm tra | Dấu hiệu lỗ hổng nếu vi phạm |
|---|---|---|
| Tổng trước thuế bằng tổng hàng trừ ưu đãi theo chính sách | Đối chiếu từng thành phần của bản phân rã giá | Trừ ưu đãi hai lần hoặc bỏ sót dòng hàng |
| Tiền giảm không vượt phạm vi được phép | Kiểm tra giới hạn phần trăm, số tiền và điều kiện sử dụng | Dùng coupon để tạo số tiền phải trả âm |
| Các khoản cộng/trừ chỉ dùng cùng tiền tệ | Kiểm tra currency và scale ở ranh giới hệ thống | Coi USD và VND là cùng một đơn vị |
| Khoản thu gắn với phiên bản báo giá đã xác nhận | Đối chiếu order, quote version, currency và amount | Sửa báo giá hoặc dùng báo giá cũ để thanh toán |
| Tổng hoàn đã hoàn tất và đang giữ chỗ không vượt số tiền có thể hoàn | Kiểm tra dữ liệu bền vững và các lời gọi ra cổng thanh toán | Hai yêu cầu hoàn cùng sử dụng một số dư |
| Một ý định thanh toán/hoàn tiền chỉ tạo một hiệu ứng tài chính | Retry, timeout, callback trùng và kiểm tra số hiệu ứng | Thu hoặc hoàn tiền hai lần |
| Chỉ chủ thể có quyền mới tạo được điều chỉnh | Gửi yêu cầu với order, wallet, coupon của người khác | Tính đúng tiền trên đối tượng không được phép thao tác |

Không phải hệ thống nào cũng có các công thức giống nhau. Ví dụ, đơn được miễn phí có thể có tổng bằng 0; ví điện tử có thể cho phép số dư âm theo một hạn mức tín dụng riêng. Test phải diễn đạt bất biến cụ thể, không tự áp đặt `total > 0` hoặc `balance >= 0` cho mọi mô hình.

## 2. Viết đặc tả phép tính đủ rõ để tạo oracle

**Oracle** là cơ sở xác định kết quả đúng. Oracle có thể là một bảng tính đã được duyệt, ví dụ tính tay hoặc mô hình tham chiếu độc lập. Không lấy chính kết quả của hàm đang kiểm thử làm expected value.

### 2.1. Hợp đồng minh họa cho một báo giá

Để giữ ví dụ dễ kiểm tra, báo giá dưới đây chỉ có một loại hàng, không có phí vận chuyển hay chuyển đổi tiền tệ:

| Thành phần | Quy tắc minh họa |
|---|---|
| Currency | VND; hệ thống dùng scale 0 |
| Đơn giá `P` | Số nguyên dương; lấy từ nguồn giá được máy chủ tin cậy |
| Số lượng `q` | Số nguyên từ 1 đến 100 |
| Tổng hàng `S` | `P × q`, không vượt 1.000.000.000 VND |
| Tỷ lệ giảm `r` | Trong đoạn `[0; 0,50]` |
| Giảm theo phần trăm `Dp` | Làm tròn `S × r` về scale 0 bằng `HALF_UP` |
| Giảm cố định `Df` | Số nguyên không âm, áp dụng sau `Dp` |
| Cơ sở tính thuế `B` | `S − Dp − Df`; từ chối nếu âm |
| Tỷ lệ thuế `t` | Trong đoạn `[0; 1]`, được cấu hình ở máy chủ |
| Thuế `T` | Làm tròn `B × t` về scale 0 bằng `HALF_UP` |
| Tổng phải trả `A` | `B + T`, không vượt 1.000.000.000 VND |

Tỷ lệ được biểu diễn dưới dạng phần của 1: `0.10` nghĩa là 10%, không phải `10`. Giá trị có biểu diễn `250.00` vẫn có thể được chuẩn hóa thành 250 vì không mất giá trị; `250.01` phải bị từ chối theo hợp đồng scale 0 này.

Đầu vào tiền được nhận qua kiểu số thập phân chính xác. Dùng `new BigDecimal("0.10")` trong Java; tránh tạo số tiền từ `double`, chẳng hạn `new BigDecimal(0.1)`. API cũng cần giới hạn độ dài và độ chính xác của đầu vào để tránh một chuỗi số khổng lồ tiêu tốn tài nguyên trước khi kiểm tra giới hạn nghiệp vụ.

### 2.2. Ví dụ vàng cần kiểm tra từng thành phần

Cho `P = 199.999`, `q = 3`, `r = 0,10`, `Df = 20.000`, `t = 0,08`:

| Bước | Phép tính | Kết quả VND |
|---|---|---:|
| Tổng hàng | `199999 × 3` | 599.997 |
| Giảm phần trăm | `round(599997 × 0.10)` | 60.000 |
| Giảm cố định | Theo ưu đãi được phép | 20.000 |
| Cơ sở thuế | `599997 − 60000 − 20000` | 519.997 |
| Thuế | `round(519997 × 0.08)` | 41.600 |
| Tổng phải trả | `519997 + 41600` | 561.597 |

Nếu chỉ assert tổng cuối, hai lỗi bù trừ nhau có thể bị che khuất. Test nên kiểm tra subtotal, từng loại discount, tax base, tax và total, đồng thời xác minh chúng được lưu và dùng nhất quán trong thanh toán.

### 2.3. Quyết định làm tròn là một phần của chính sách

Giả sử hai dòng hàng có cơ sở tính thuế 5 VND mỗi dòng, thuế suất giả định 10%:

- Làm tròn thuế từng dòng bằng `HALF_UP`: `round(0,5) + round(0,5) = 2` VND.
- Gộp cơ sở thuế rồi làm tròn: `round((5 + 5) × 0,10) = 1` VND.

Hai kết quả đều có thể đúng với hai chính sách khác nhau. Lỗ hổng xuất hiện khi khách có thể chọn chia/gộp giỏ hàng để khai thác một chính sách mà hệ thống không dự kiến, hoặc các thành phần báo giá, thu tiền và hoàn tiền sử dụng hai cách khác nhau.

Phải có test tại các mốc ngay dưới, đúng và ngay trên điểm làm tròn, ví dụ kết quả thô `0,49`, `0,50`, `0,51`. Nếu nhiều thuế hoặc nhiều loại tiền tồn tại, ma trận test phải gắn mỗi trường hợp với chính sách tương ứng; không dùng một scale toàn cục cho mọi currency.

## 3. Phân bố test theo nơi có thể phát sinh sai lệch

| Lớp kiểm thử | Điều cần chứng minh | Ví dụ |
|---|---|---|
| Unit cho phép tính thuần | Công thức, giới hạn và làm tròn đúng | Giảm giá trước thuế; từ chối cơ sở thuế âm |
| Property-based | Bất biến đúng trên nhiều tổ hợp dữ liệu | Tổng thành phần khớp tổng cuối; không vượt trần |
| Service/API | Nguồn giá, quyền và trạng thái được bảo vệ | Khách tự gửi `unitPrice=1` vẫn không thay giá |
| Integration với database | Commit, rollback, tranh chấp và ràng buộc dữ liệu đúng | Hai lần giữ chỗ hoàn tiền không vượt số dư |
| Contract với bên thanh toán | Amount, currency, đơn vị và retry được diễn giải đúng | `1234` có đúng nghĩa là 12,34 đơn vị với currency được chọn |
| Luồng đầu cuối có chọn lọc | Kết quả bền vững xuyên các bước | Báo giá → thu tiền → callback → hoàn một phần |

Tập trung nhiều trường hợp số học ở lớp chạy nhanh. Dùng integration test thật cho đặc tính phụ thuộc database, transaction và locking. Mock một repository không chứng minh được khả năng chống race condition.

## 4. Ví dụ Java: tách phép tính thuần để kiểm thử

Đoạn mã sau minh họa hợp đồng ở mục 2 bằng Java 17 trở lên. Nó chỉ thực hiện số học: service gọi nó phải tự xác thực người dùng, lấy giá và tỷ lệ từ nguồn có thẩm quyền, kiểm tra quyền sử dụng ưu đãi và quản lý trạng thái đơn.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class PriceCalculator {
    private static final BigDecimal MAX_AMOUNT =
            new BigDecimal("1000000000");
    private static final BigDecimal MAX_DISCOUNT_RATE =
            new BigDecimal("0.50");

    public record Quote(
            BigDecimal subtotal,
            BigDecimal percentageDiscount,
            BigDecimal fixedDiscount,
            BigDecimal taxBase,
            BigDecimal tax,
            BigDecimal total) {}

    public static Quote quote(
            BigDecimal unitPrice,
            int quantity,
            BigDecimal discountRate,
            BigDecimal fixedDiscount,
            BigDecimal taxRate) {

        require(quantity >= 1 && quantity <= 100, "invalid quantity");
        BigDecimal price = wholeAmount(unitPrice);
        BigDecimal fixed = wholeAmount(fixedDiscount);
        require(price.signum() > 0, "unit price must be positive");
        require(fixed.signum() >= 0, "negative fixed discount");
        requireRate(discountRate, MAX_DISCOUNT_RATE);
        requireRate(taxRate, BigDecimal.ONE);

        BigDecimal subtotal = price.multiply(BigDecimal.valueOf(quantity));
        require(subtotal.compareTo(MAX_AMOUNT) <= 0, "subtotal exceeds limit");

        BigDecimal percentage = subtotal.multiply(discountRate)
                .setScale(0, RoundingMode.HALF_UP);
        BigDecimal base = subtotal.subtract(percentage).subtract(fixed);
        require(base.signum() >= 0, "discount exceeds subtotal");

        BigDecimal tax = base.multiply(taxRate)
                .setScale(0, RoundingMode.HALF_UP);
        BigDecimal total = base.add(tax);
        require(total.compareTo(MAX_AMOUNT) <= 0, "total exceeds limit");

        return new Quote(subtotal, percentage, fixed, base, tax, total);
    }

    private static BigDecimal wholeAmount(BigDecimal value) {
        return Objects.requireNonNull(value, "missing amount")
                .setScale(0, RoundingMode.UNNECESSARY);
    }

    private static void requireRate(BigDecimal rate, BigDecimal maximum) {
        Objects.requireNonNull(rate, "missing rate");
        require(rate.signum() >= 0 && rate.compareTo(maximum) <= 0,
                "rate out of range");
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalArgumentException(message);
        }
    }
}
```

Không tự sửa đầu vào sai bằng cách lấy trị tuyệt đối, ép discount về trần hoặc đổi tổng âm thành 0, trừ khi chính sách yêu cầu rõ hành vi đó. Nếu API cần trả lỗi nghiệp vụ ổn định, hãy ánh xạ lỗi đầu vào thành mã lỗi phù hợp tại ranh giới API; không để chi tiết exception trở thành hợp đồng công khai ngoài ý muốn.

`BigDecimal` tránh sai số biểu diễn nhị phân, nhưng không tự quyết định scale, chế độ làm tròn hay giới hạn nghiệp vụ. Nếu hệ thống dùng số nguyên theo đơn vị nhỏ nhất, cần thêm test tràn số khi nhân/cộng và khi chuyển đổi kiểu, ví dụ dùng `Math.multiplyExact`, `Math.addExact` hoặc phép chuyển đổi exact phù hợp.

## 5. Unit test: dùng kết quả độc lập và kiểm tra các ranh giới

### 5.1. Một nhóm test JUnit 5

Các test dưới đây dùng số kỳ vọng cố định từ hợp đồng. Chúng không gọi lại helper tính thuế hoặc tính discount của production để suy ra expected value.

```java
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {
    private static BigDecimal d(String text) {
        return new BigDecimal(text);
    }

    private static void assertMoney(String expected, BigDecimal actual) {
        assertEquals(0, d(expected).compareTo(actual),
                () -> "expected " + expected + " but got " + actual);
        assertEquals(0, actual.scale(), "VND output must use scale 0");
    }

    @Test
    void calculatesDiscountBeforeTax() {
        var quote = PriceCalculator.quote(
                d("199999"), 3, d("0.10"), d("20000"), d("0.08"));

        assertMoney("599997", quote.subtotal());
        assertMoney("60000", quote.percentageDiscount());
        assertMoney("20000", quote.fixedDiscount());
        assertMoney("519997", quote.taxBase());
        assertMoney("41600", quote.tax());
        assertMoney("561597", quote.total());
    }

    @Test
    void roundsHalfUpAtTheTaxBoundary() {
        var below = PriceCalculator.quote(
                d("49"), 1, d("0"), d("0"), d("0.01"));
        var tie = PriceCalculator.quote(
                d("50"), 1, d("0"), d("0"), d("0.01"));
        var above = PriceCalculator.quote(
                d("51"), 1, d("0"), d("0"), d("0.01"));

        assertMoney("0", below.tax());
        assertMoney("1", tie.tax());
        assertMoney("1", above.tax());
    }

    @Test
    void allowsAZeroTotalWhenDiscountExactlyCoversTheSubtotal() {
        var quote = PriceCalculator.quote(
                d("100"), 1, d("0.50"), d("50"), d("0.08"));

        assertMoney("0", quote.taxBase());
        assertMoney("0", quote.tax());
        assertMoney("0", quote.total());
    }

    @Test
    void rejectsDiscountBeyondTheRemainingSubtotal() {
        assertThrows(IllegalArgumentException.class, () ->
                PriceCalculator.quote(
                        d("100"), 1, d("0.50"), d("51"), d("0.08")));
    }

    @Test
    void rejectsFractionsOfVndInsteadOfSilentlyRoundingInput() {
        assertThrows(ArithmeticException.class, () ->
                PriceCalculator.quote(
                        d("100.01"), 1, d("0"), d("0"), d("0")));
    }

    @Test
    void checksTheFinalLimitAfterAddingTax() {
        var atLimit = PriceCalculator.quote(
                d("10000000"), 100, d("0"), d("0"), d("0"));
        assertMoney("1000000000", atLimit.total());

        assertThrows(IllegalArgumentException.class, () ->
                PriceCalculator.quote(
                        d("10000000"), 100, d("0"), d("0"), d("0.01")));
    }
}
```

`BigDecimal.equals` xét cả scale, nên `1.0` và `1.00` không bằng nhau theo phương thức đó. Test ở đây tách việc so sánh giá trị bằng `compareTo` khỏi việc kiểm tra scale đầu ra. Với một kiểu `Money` riêng, hãy xác định rõ equality có bao gồm currency và quy tắc chuẩn hóa nào.

Các đoạn mã là ví dụ học tập, không khẳng định bộ test đã được chạy trong một project cụ thể. Khi đưa vào ứng dụng, cần cấu hình phiên bản Java, JUnit và các phụ thuộc theo project đó.

### 5.2. Ma trận dữ liệu tối thiểu

| Nhóm | Dữ liệu cần có | Kỳ vọng |
|---|---|---|
| Số lượng | `0`, `1`, `100`, `101`, số âm | Chỉ khoảng hợp lệ được chấp nhận |
| Đơn giá | Âm, 0, nhỏ nhất hợp lệ, có phần lẻ, sát giới hạn | Không mất phần lẻ đầu vào một cách im lặng |
| Tỷ lệ giảm | Âm, 0, `0.50`, lớn hơn `0.50`, `10` thay cho `0.10` | Áp dụng đúng đơn vị và giới hạn |
| Giảm cố định | Âm, 0, bằng phần còn lại, vượt phần còn lại 1 VND | Không tạo cơ sở thuế âm |
| Thuế | Âm, 0, giá trị thông thường, 1, lớn hơn 1 | Đúng miền hợp lệ của hợp đồng minh họa |
| Điểm làm tròn | Dưới nửa, đúng nửa, trên nửa | Đúng chế độ ở cả discount và tax |
| Tổng tiền | Đúng trần; vượt trần sau nhân; vượt trần sau cộng thuế | Không chỉ kiểm tra đơn giá riêng lẻ |
| Biểu diễn | `100`, `100.0`, `100.00`, `100.01` | Chuẩn hóa các giá trị nguyên, từ chối phần lẻ thật |
| Currency | Currency đúng, thiếu, không hỗ trợ, khác currency của đơn | Không tính cộng/trừ giữa hai đơn vị |
| Payload | Thiếu trường, null, chuỗi sai định dạng, số quá dài | Từ chối có kiểm soát trước khi gây hiệu ứng tài chính |

Currency, payload và nguồn dữ liệu không nằm trong hàm minh họa; phải kiểm tra ở lớp API/service tương ứng. Đừng đánh dấu hoàn thành một yêu cầu chỉ vì một hàm không có tham số đó đã pass test.

## 6. Property-based và metamorphic testing

### 6.1. Kiểm tra bất biến trên miền dữ liệu hợp lệ

Property-based testing sinh nhiều đầu vào để tìm tổ hợp mà các ví dụ cố định chưa bao phủ. Với hợp đồng minh họa, mỗi quote thành công phải thỏa mãn:

```text
subtotal = unitPrice × quantity
taxBase = subtotal − percentageDiscount − fixedDiscount
total = taxBase + tax
percentageDiscount >= 0
fixedDiscount >= 0
taxBase >= 0
tax >= 0
0 <= total <= MAX_AMOUNT
scale của mọi khoản tiền đầu ra = 0
```

Nhóm kiểm tra này chứng minh tính nhất quán nhưng chưa chứng minh công thức đã đúng: một implementation luôn trả toàn số 0 có thể qua nhiều bất biến yếu. Phải kết hợp với ví dụ vàng và oracle độc lập cho công thức, thứ tự tính và làm tròn.

Thiết kế generator nên có hai nhóm:

1. **Đầu vào hợp lệ có chủ đích:** chọn giá, số lượng và tỷ lệ; giới hạn discount cố định theo số tiền còn lại và giữ tổng trong trần. Những trường hợp này phải tạo quote thành công.
2. **Đầu vào vi phạm có chủ đích:** tạo đúng một hoặc một nhóm vi phạm, chẳng hạn giảm vượt mức 1 VND hoặc quantity vượt trần. Những trường hợp này phải bị từ chối và không ghi dữ liệu tài chính.

Tránh lọc bỏ gần hết dữ liệu ngẫu nhiên bằng điều kiện `assume`: bộ test có thể chạy lâu nhưng chỉ kiểm tra rất ít trường hợp có ích. Nên tăng xác suất tại biên, các khoản tiền nhỏ và điểm làm tròn. Khi phát hiện lỗi, lưu seed và ví dụ đã thu nhỏ làm regression test cố định.

### 6.2. Quan hệ biến đổi chỉ đúng khi có điều kiện rõ ràng

Metamorphic testing kiểm tra quan hệ giữa hai lần chạy thay vì cần biết mọi kết quả cụ thể:

| Quan hệ | Điều kiện để áp dụng | Assertion |
|---|---|---|
| Đổi thứ tự dòng không đổi tổng | Không có ưu đãi phụ thuộc thứ tự và phân bổ có quy tắc ổn định | Cùng tổng và phân bổ theo định danh dòng |
| Tăng ưu đãi cố định không làm tăng tổng | Giữ nguyên giá, thuế, chính sách; cả hai đầu vào hợp lệ | Tổng mới nhỏ hơn hoặc bằng tổng cũ |
| Biểu diễn tương đương cho cùng giá trị | Cùng currency; chuẩn hóa không làm mất giá trị | `100` và `100.00` tạo cùng quote |
| Retry cùng ý định không đổi kết quả | Cùng key, chủ thể, đối tượng và payload hợp lệ | Trả cùng tài nguyên, không tăng hiệu ứng tiền |
| Hoàn toàn bộ sau nhiều lần hoàn một phần khớp khoản được hoàn | Chính sách phân bổ cố định, không có phí không hoàn lại bị bỏ sót | Tổng phần hoàn bằng đúng khoản được phép |

Không áp dụng máy móc các quan hệ sau:

- **Nhân đôi số lượng thì tổng luôn gấp đôi:** có thể sai vì làm tròn, trần giảm giá, bậc giá hoặc giới hạn tiền.
- **Chia một đơn thành hai thì tổng không đổi:** có thể sai vì phí trên đơn, mức giảm tối thiểu và thuế làm tròn theo đơn.
- **Tăng thuế luôn tăng tổng nghiêm ngặt:** do làm tròn, tổng có thể giữ nguyên trong một đoạn; chỉ có thể đòi quan hệ không giảm khi các điều kiện khác giữ nguyên.
- **Mọi khoản hoàn đều bằng đơn giá hiện tại nhân số lượng:** sai nếu giá đã đổi hoặc giao dịch gốc có ưu đãi, thuế, phí và phân bổ khác.

Một property sai có thể ép đội phát triển sửa chương trình đúng thành chương trình sai. Viết điều kiện áp dụng ngay cạnh property và nhờ người sở hữu chính sách xác nhận.

## 7. Kiểm thử API để ngăn thao túng phép tính

### 7.1. Nguồn tin cậy của từng giá trị

Khách có thể gửi lựa chọn sản phẩm, số lượng, mã ưu đãi hoặc mã báo giá. Máy chủ phải tự quyết định giá có thẩm quyền và xác minh quyền áp dụng ưu đãi. Trường do khách gửi để hiển thị hoặc đối soát không được mặc nhiên trở thành giá trị tính tiền.

| Tình huống tấn công | Cách dựng test | Kết quả cần quan sát |
|---|---|---|
| Sửa đơn giá/tổng | Gửi giá 1 VND hoặc `total` thấp hơn báo giá | API từ chối hoặc dùng giá máy chủ theo hợp đồng; dữ liệu lưu và yêu cầu thanh toán có số tiền đúng |
| Sửa tỷ lệ giảm/thuế | Thêm `discountRate`, `taxRate` ngoài quyền của khách | Không có thay đổi chính sách trái phép |
| Đổi chủ thể | Người B dùng `orderId`, `quoteId`, coupon riêng của A | Bị từ chối; không lộ hoặc thay đổi kết quả tiền của A |
| Tái dùng báo giá | Dùng quote hết hạn, đã tiêu thụ hoặc không khớp giỏ hàng | Bị từ chối hoặc yêu cầu xác nhận báo giá mới theo chính sách |
| Cộng dồn ưu đãi | Áp hai mã loại trừ nhau bằng hai endpoint hay hai thứ tự | Chỉ tổ hợp được phép được commit |
| Bỏ qua trạng thái | Hoàn đơn chưa thu tiền; sửa dòng hàng sau khi thanh toán | Chuyển trạng thái trái phép bị chặn |
| Đổi currency | Giữ nguyên số nhưng đổi đơn vị tiền | Bị từ chối; không tạo yêu cầu thanh toán sai currency |
| Sửa callback | Gửi sự kiện thành công có amount/currency/order không khớp | Không đánh dấu đã thanh toán; ghi nhận sai lệch để xử lý |

Với callback, kiểm tra cả xác thực nguồn sự kiện và đối chiếu nội dung. Một sự kiện có nguồn hợp lệ vẫn có thể bị gắn sai order trong logic ứng dụng. Không chỉ assert HTTP status: hãy kiểm tra trạng thái đơn, dòng tiền, số lần gọi bên ngoài và dữ liệu bền vững.

### 7.2. Tính nhất quán của báo giá qua thay đổi thời gian

Giả sử người dùng xem quote phiên bản 7 lúc 10:00, sau đó bảng giá đổi lúc 10:01. Tại bước xác nhận, hệ thống cần có chính sách rõ: giữ giá phiên bản 7 trong thời hạn cho phép, hoặc phát hành quote mới và yêu cầu xác nhận lại. Test không nên ngầm chọn một trong hai chính sách.

Một kịch bản kiểm thử nên:

1. Tạo quote với phiên bản giá, ưu đãi và chính sách làm tròn đã biết.
2. Thay đổi cấu hình giá hoặc tỷ lệ sau khi tạo quote.
3. Thanh toán theo quote cũ ở trước và sau mốc hết hạn, dùng clock kiểm soát được.
4. Kiểm tra amount thu thực tế và dữ liệu phiên bản được lưu.
5. Hoàn tiền sau khi cấu hình đổi một lần nữa; xác minh khoản hoàn dựa vào giao dịch gốc và chính sách hoàn đã chốt.

Không dùng bảng giá hiện hành để tái tính lịch sử nếu hợp đồng yêu cầu dùng giá đã chấp nhận. Với cấu hình có thể thay đổi, lưu phiên bản và bản phân rã cần thiết để giải thích được số tiền đã thu.

## 8. Hoàn một phần: kiểm tra bảo toàn tiền và phần dư

### 8.1. Không chia rồi làm tròn độc lập mọi lần

Giả sử một dòng có 3 đơn vị hàng và tổng tiền được phép hoàn của dòng là 10 đơn vị tiền nhỏ nhất. Nếu mỗi lần hoàn một đơn vị đều tính `round(10 / 3) = 3`, ba lần hoàn chỉ được 9, còn dư 1.

Một chính sách minh họa có thể dùng **tổng hoàn lũy kế**. Với `A` là khoản được phép hoàn của dòng, `N` là số lượng gốc và `k` là số lượng đã hoàn tính cả yêu cầu mới:

```text
F(k) = round(A × k / N), theo chế độ làm tròn đã chốt
Khoản hoàn mới = F(k_mới) − F(k_cũ)
0 <= k_cũ <= k_mới <= N
```

Với `A = 10`, `N = 3` và làm tròn `HALF_UP`:

| Lần hoàn | Số lượng hoàn lũy kế | Tổng hoàn lũy kế | Tiền của lần hiện tại |
|---|---:|---:|---:|
| 1 | 1 | 3 | 3 |
| 2 | 2 | 7 | 4 |
| 3 | 3 | 10 | 3 |

Đây là một lựa chọn chính sách, không phải công thức bắt buộc cho mọi cửa hàng. Một hệ thống khác có thể phân bổ phần dư cho từng đơn vị từ lúc bán. Dù chọn cách nào, cần có quy tắc ổn định, tổng khớp giao dịch gốc và không cho người dùng tự chọn cách làm tròn có lợi ở từng lần hoàn.

### 8.2. Các test phân bổ cần có

- Hoàn cả dòng một lần và hoàn qua nhiều lần đều đạt đúng tổng được phép hoàn.
- Hoàn 1 rồi 2 đơn vị, hoàn 2 rồi 1 đơn vị và hoàn từng đơn vị đều tuân thủ quy tắc lũy kế.
- Lần hoàn cuối hấp thụ đúng phần còn lại, không mất hoặc sinh thêm đơn vị tiền nhỏ nhất.
- Tổng discount phân bổ cho các dòng bằng discount của đơn; tương tự với tax và các phí được phân bổ.
- Khi các dòng có cùng phần dư, tiêu chí chọn dòng nhận phần dư phải xác định được, ví dụ theo định danh dòng ổn định.
- Đổi thứ tự trả về của database không thay đổi phân bổ nếu thứ tự đó không phải đầu vào nghiệp vụ.
- Đổi giá, coupon hay thuế hiện tại không làm đổi khoản được hoàn của giao dịch gốc.
- Số lượng hoàn bằng 0, âm, vượt số đã mua hoặc vượt số còn được hoàn bị xử lý theo chính sách; không tạo khoản tiền trái phép.
- Phí không hoàn lại, hoàn vận chuyển và hoàn thuế có test riêng, không gộp chung thành giả định mọi khoản đều hoàn theo tỷ lệ.

Nếu một khoản được hoàn sau phân bổ có giá trị 0, hệ thống cần quy tắc cho việc ghi nhận trả hàng mà không tạo lệnh hoàn tiền bằng 0 ra bên ngoài. Test phải tách sự kiện trả hàng khỏi hiệu ứng tiền khi hai sự kiện này không tương đương.

Không đọc `k_cũ`, tính tiền rồi ghi `k_mới` bằng hai thao tác không được bảo vệ. Hai yêu cầu đồng thời có thể cùng đọc một giá trị cũ. Cập nhật số lượng, phân bổ và giữ chỗ tiền hoàn cần cùng tuân theo chiến lược transaction/đồng thời của hệ thống.

## 9. Đồng thời, idempotency và transaction

### 9.1. Kiểm thử vượt mức hoàn khi chạy đồng thời

Gọi:

```text
R = tổng tiền được phép hoàn theo giao dịch gốc và chính sách
F = tổng tiền đã hoàn thành công
P = tổng tiền đã giữ chỗ cho các yêu cầu chưa có kết quả cuối cùng
available = R − F − P
```

Các bất biến cần giữ là `F >= 0`, `P >= 0` và `F + P <= R`. Một yêu cầu hoàn mới chỉ được giữ chỗ khi amount hợp lệ và không vượt `available` trong cùng cơ chế bảo vệ cập nhật.

Kịch bản integration test với hai ý định hoàn khác nhau:

1. Chuẩn bị một giao dịch có `R = 100.000`, `F = 0`, `P = 0`.
2. Hai client hợp lệ đồng thời yêu cầu hoàn 70.000, dùng hai idempotency key khác nhau.
3. Đồng bộ hai tác vụ tại điểm trước thao tác kiểm tra/giữ chỗ để tạo tranh chấp có chủ đích.
4. Chờ cả hai tác vụ tới trạng thái quan sát được và kiểm tra dữ liệu đã commit.
5. Chỉ một yêu cầu được giữ chỗ 70.000; yêu cầu còn lại phải bị từ chối, chờ rồi kiểm tra lại hoặc nhận kết quả tương đương theo thiết kế. Tổng tiền được giữ chỗ và đã hoàn không được thành 140.000.
6. Kiểm tra các tác vụ thanh toán bên ngoài: không được tạo hai khoản hoàn 70.000 cho hai lần giữ chỗ không hợp lệ.

Nếu dùng row lock, không đặt barrier theo cách bắt buộc hai transaction cùng đi qua một câu lệnh mà chỉ một transaction được giữ khóa; điều đó có thể gây deadlock do chính test. Dùng hai connection/transaction thật và điểm điều phối phù hợp với cách triển khai. Kiểm thử concurrency bằng `sleep` ngẫu nhiên thường khó tái hiện và không chứng minh được đường tranh chấp đã xảy ra.

Một cách bảo vệ có thể là khóa hàng, optimistic locking có retry hoặc câu lệnh cập nhật có điều kiện. Test nên xác nhận bất biến và kết quả bền vững; lựa chọn cơ chế cụ thể tùy database và thiết kế ứng dụng.

### 9.2. Ma trận idempotency cho thao tác có tiền

| Trường hợp | Điều phải kiểm tra |
|---|---|
| Cùng key, cùng chủ thể và cùng payload, gửi tuần tự | Cùng tài nguyên/kết quả theo hợp đồng; chỉ một hiệu ứng tiền |
| Cùng key và payload, gửi đồng thời | Ràng buộc duy nhất bền vững ngăn hai lần thực thi độc lập |
| Cùng key nhưng amount, order hoặc currency khác | Bị từ chối do xung đột; không tái dùng kết quả của ý định khác |
| Cùng key nhưng khác người hoặc tenant | Phạm vi key rõ ràng, không trả dữ liệu của người khác |
| Khác key nhưng cùng ý định nghiệp vụ đã hoàn tất | Trạng thái và ràng buộc nghiệp vụ vẫn ngăn hiệu ứng trùng |
| Retry sau timeout | Đọc được trạng thái đang xử lý hoặc kết quả đã có; không mặc định coi lần trước thất bại |
| Key hết thời gian lưu nhưng yêu cầu cũ được gửi lại | Ràng buộc giao dịch gốc vẫn bảo vệ thao tác không được lặp |

Idempotency key không thay thế kiểm tra quyền hay kiểm tra số dư. Nó cũng không tự ngăn hai yêu cầu có key khác nhau vượt giới hạn tổng. Cần kiểm tra cả danh tính ý định nghiệp vụ, trạng thái tài nguyên và bất biến tổng tiền.

### 9.3. Tiêm lỗi tại ranh giới transaction và hệ thống ngoài

Transaction database không bao trùm tự động cổng thanh toán. Nên kiểm thử các điểm đứt sau:

| Điểm tiêm lỗi | Trạng thái an toàn cần chứng minh |
|---|---|
| Trước commit giữ chỗ | Không có giữ chỗ hoặc công việc bên ngoài được coi là đã chấp nhận nếu transaction rollback |
| Sau commit giữ chỗ, trước khi worker xử lý | Công việc đã ghi bền vững còn có thể được xử lý lại |
| Bên thanh toán thành công nhưng phản hồi bị timeout | Ứng dụng giữ trạng thái chưa xác định và đối soát; không giải phóng tiền để hoàn tiếp ngay |
| Bên thanh toán thành công nhưng ghi kết quả local thất bại | Retry/đối soát liên kết được kết quả cũ; không phát sinh khoản hoàn thứ hai |
| Worker hoặc callback nhận cùng sự kiện nhiều lần | Chỉ một chuyển trạng thái và một lần ghi hiệu ứng tài chính |
| Callback đến không theo thứ tự | Sự kiện cũ không kéo trạng thái đã thành công về đang xử lý hoặc thất bại |
| Bên thanh toán xác nhận thất bại cuối cùng | Giữ chỗ được giải phóng đúng một lần theo chính sách |

Nếu dùng outbox, kiểm tra bản ghi nghiệp vụ và công việc outbox được commit cùng nhau; worker phát lại vẫn phải an toàn. Nếu nhà cung cấp hỗ trợ idempotency, kiểm tra ứng dụng tái dùng đúng khóa cho cùng ý định qua các lần retry. Nếu kết quả bên ngoài chưa rõ, cơ chế tra cứu/đối soát phải giải quyết trạng thái đó trước khi quyết định tạo lệnh mới.

Không assert “chỉ có một HTTP request” như một tiêu chí chung cho mọi retry. Có thể có nhiều lần gửi hợp lệ nhưng chỉ một khoản thu/hoàn thực sự. Cần phân biệt số lần thử, số giao dịch bên ngoài và số bút toán hoặc bản ghi hiệu ứng đã commit.

## 10. Contract test ở ranh giới tiền tệ

Sai số lớn thường xuất hiện khi hai hệ thống hiểu khác đơn vị. Ví dụ, một provider dùng số nguyên theo đơn vị nhỏ nhất, còn ứng dụng dùng số thập phân theo đơn vị chính. Với currency có hai chữ số phần lẻ và hợp đồng đó, `12.34` phải được gửi thành `1234`, không phải `12` hoặc `123400`.

Contract test cần bao phủ:

- Từng currency được hỗ trợ và bảng quy đổi đơn vị thực sự của provider; không mặc định mọi currency có hai chữ số thập phân.
- Chuyển đổi hai chiều không mất giá trị với đầu vào hợp lệ; từ chối độ chính xác không được hỗ trợ thay vì âm thầm làm tròn ở adapter.
- Giới hạn số tiền của provider, giới hạn kiểu dữ liệu và lỗi tràn khi chuyển sang số nguyên.
- JSON/request body, cột database và sự kiện giữ được currency, amount, scale cần thiết và định danh giao dịch.
- Payment/callback khớp order, amount, currency và giao dịch bên ngoài đã được kỳ vọng.
- Quy tắc về dấu: hoàn tiền có thể được biểu diễn bằng một thao tác riêng với amount dương, thay vì amount âm. Test theo hợp đồng thực của provider.

Các giá trị đặc thù của nhà cung cấp phải được lấy từ hợp đồng tích hợp đã xác nhận khi triển khai. Fake dùng trong test phải phản ánh hợp đồng ấy; fake luôn trả thành công cho mọi amount sẽ che khuất lỗi ở adapter. Sandbox hữu ích để kiểm tra tích hợp, nhưng không thay được oracle số học và các integration test có tiêm lỗi chủ động.

## 11. Tổ chức dữ liệu kiểm thử và đánh giá độ mạnh

### 11.1. Lưu một bộ ví dụ vàng có thể giải thích

Mỗi ví dụ nên có mã chính sách, currency, đầu vào, từng bước trung gian và lý do tồn tại. Ví dụ:

```text
caseId: VND_PERCENT_THEN_FIXED_THEN_TAX
policyVersion: example-v1
currency: VND
unitPrice: 199999
quantity: 3
discountRate: 0.10
fixedDiscount: 20000
taxRate: 0.08
expected:
  subtotal: 599997
  percentageDiscount: 60000
  taxBase: 519997
  tax: 41600
  total: 561597
reason: phát hiện thay đổi thứ tự giảm giá và tính thuế
```

Khi chính sách thay đổi có chủ đích, thêm phiên bản mới và xác định giao dịch nào dùng phiên bản nào. Không sửa expected value hàng loạt chỉ để test xanh mà không giải thích thay đổi nghiệp vụ. Giữ test hồi quy cho các giao dịch lịch sử cần tiếp tục được xử lý theo chính sách cũ.

### 11.2. Dùng lỗi giả định để nhận diện khoảng trống

Đánh giá bộ test bằng cách hỏi liệu nó có phát hiện được các thay đổi sai sau hay không:

- Chuyển `HALF_UP` thành `DOWN` ở discount hoặc tax.
- Tính thuế trên subtotal trước khi trừ discount.
- Đổi điều kiện `>` thành `>=` ở trần tiền, khiến giá trị đúng trần bị từ chối.
- Bỏ kiểm tra tổng sau khi cộng thuế.
- Thay giá máy chủ bằng giá khách gửi.
- Bỏ điều kiện chủ sở hữu của order hoặc coupon.
- Bỏ tính duy nhất của ý định thanh toán/hoàn tiền.
- Bỏ điều kiện giữ chỗ nguyên tử, làm hai transaction cùng tiêu một số dư.
- Cho timeout đồng nghĩa thất bại cuối cùng và giải phóng khoản giữ chỗ quá sớm.

Đây là cách suy nghĩ theo mutation testing; không bắt buộc dùng một công cụ để áp dụng được. Một test tốt phải có khả năng thất bại vì một lỗi có ý nghĩa. Code coverage cao nhưng không phân biệt các thay đổi trên vẫn có thể bỏ lọt lỗ hổng nghiệp vụ.

### 11.3. Giữ test xác định và dễ điều tra

- Cố định clock, phiên bản chính sách, tỷ giá nếu có và trạng thái giao dịch ban đầu.
- Dùng decimal chính xác, tránh tolerance tùy tiện cho số tiền vốn phải khớp theo đơn vị nhỏ nhất.
- Cô lập dữ liệu theo test; dùng transaction thật và kết nối riêng trong test đồng thời.
- Với xử lý bất đồng bộ, chờ điều kiện có deadline; khi thất bại xuất trạng thái để chẩn đoán thay vì chỉ tăng thời gian chờ.
- Assertion nêu rõ order/refund, currency, expected, actual và policy version bằng dữ liệu giả lập phù hợp.
- Kiểm tra cả phản hồi, dữ liệu đã commit, các khoản đang giữ chỗ và hiệu ứng bên ngoài.

## 12. Bài tập áp dụng và tiêu chí hoàn thành

Cho một API xác nhận đơn và một API hoàn tiền, hãy thực hiện lần lượt:

1. Viết hợp đồng tiền tệ: nguồn giá, currency, scale, thứ tự ưu đãi, thuế, làm tròn và giới hạn.
2. Lập ít nhất một ví dụ vàng có tính tay mọi thành phần; thêm các ca tại biên làm tròn và biên số tiền.
3. Viết unit test cho phép tính thuần, kèm một property về bảo toàn thành phần và một property về miền đầu ra.
4. Gửi yêu cầu sửa giá, sửa tỷ lệ, đổi order sang người khác và dùng báo giá hết hạn; kiểm tra trạng thái bền vững sau mỗi lần.
5. Hoàn một giao dịch qua nhiều phần, bao gồm trường hợp phát sinh phần dư của đơn vị tiền nhỏ nhất.
6. Chạy hai yêu cầu hoàn có key khác nhau nhưng tổng vượt khoản được hoàn; xác nhận bất biến cả khi có tranh chấp.
7. Gửi lại cùng key tuần tự và đồng thời; thử cùng key với payload khác.
8. Tiêm timeout sau khi bên thanh toán đã xử lý thành công; kiểm tra retry/đối soát không tạo khoản tiền trùng.

Hoàn thành bài thực hành khi có bằng chứng cho cả ba lớp: **phép tính đúng theo chính sách**, **đầu vào và trạng thái được kiểm soát**, **hiệu ứng tài chính không bị nhân đôi hoặc vượt giới hạn khi retry và chạy đồng thời**. Những chính sách chưa chốt phải được ghi thành câu hỏi cần giải quyết, không được che bằng một expected value tùy ý.
