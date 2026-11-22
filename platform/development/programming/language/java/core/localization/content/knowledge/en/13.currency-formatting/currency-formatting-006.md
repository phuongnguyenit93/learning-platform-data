# Tách giá trị BigDecimal, mã tiền và quy tắc làm tròn trong Java

Khi xử lý tiền tệ trong ứng dụng Java, một giá trị như `12.345 USD` thực ra chứa **ba loại thông tin độc lập**:

1. **Giá trị số:** số tiền được biểu diễn chính xác, thường dùng `BigDecimal`.
2. **Đơn vị tiền:** mã tiền tệ, thường dùng `java.util.Currency` với mã ISO 4217 như `USD`, `VND`, `JPY`, `KWD`.
3. **Quy tắc làm tròn:** làm tròn lúc nào, đến bao nhiêu chữ số thập phân hoặc bước tiền nào, bằng `RoundingMode` và quy tắc nghiệp vụ phù hợp.

Ba yếu tố này **không thể thay thế cho nhau**. Chỉ có `BigDecimal` không biết đơn vị là đô la hay đồng Việt Nam. `Currency` không thực hiện phép làm tròn. `RoundingMode` không tự quyết định số chữ số, thời điểm làm tròn hoặc luật thuế áp dụng. Một hệ thống tài chính an toàn cần mô hình hóa cả ba, đồng thời phân biệt **số tiền dùng để tính toán**, **số tiền được chốt/thanh toán**, và **chuỗi hiển thị theo locale**.

## 1. Vì sao phải tách ba thành phần?

Xét hai tình huống:

~~~text
Hóa đơn A: 12.345 USD
Hóa đơn B: 12.345 KWD
~~~

Cùng một giá trị `12.345` nhưng `USD` và `KWD` có số chữ số thập phân mặc định khác nhau theo dữ liệu tiền tệ mà Java cung cấp. Việc nên làm tròn hay giữ nguyên phải dựa vào **quy tắc của phép tính và mục đích sử dụng**, không chỉ nhìn vào số chữ số mà người dùng nhìn thấy.

Tương tự:

~~~text
10.00 USD + 5.00 USD → phép cộng hợp lệ
10.00 USD + 5.00 VND → không thể cộng trực tiếp như cùng một đơn vị
~~~

Muốn đổi từ USD sang VND phải có **tỷ giá, thời điểm, nguồn tỷ giá và chính sách chuyển đổi/làm tròn**. `Currency` không chứa tỷ giá và `BigDecimal` cũng không tự quy đổi.

| Thành phần | Java API chính | Trả lời câu hỏi | Không có trách nhiệm |
| --- | --- | --- | --- |
| Giá trị số | `BigDecimal` | Có bao nhiêu đơn vị, kết quả số học là gì? | Không xác định tiền tệ hoặc luật thanh toán |
| Mã tiền | `Currency` | Số thuộc loại tiền nào? | Không đổi tiền, không tự làm tròn |
| Quy tắc làm tròn | `RoundingMode`, `setScale`, phép chia có mode | Giữ bao nhiêu chữ số và chọn phía nào? | Không xác định tỷ giá, thuế hoặc mốc làm tròn |
| Cách hiển thị | `NumberFormat` / `DecimalFormat` + `Locale` | Hiển thị số tiền như thế nào cho người đọc? | Không thay đổi số tiền gốc nếu chỉ dùng để định dạng |

Nguyên tắc nền tảng: **giá trị tiền có nghĩa phải đi kèm đơn vị tiền**, còn quy tắc làm tròn phải được chỉ định ở đúng ranh giới nghiệp vụ.

## 2. BigDecimal: biểu diễn số thập phân chính xác

`java.math.BigDecimal` biểu diễn một giá trị thập phân bằng một hệ số nguyên không giới hạn độ lớn và một `scale` (số chữ số thập phân trong biểu diễn). Về mặt toán học, giá trị là `unscaledValue × 10^(-scale)`.

Ví dụ:

~~~java
BigDecimal a = new BigDecimal("12.345");
BigDecimal b = new BigDecimal("0.015");

BigDecimal sum = a.add(b); // 12.360
~~~

Trong chương trình đã import `java.math.BigDecimal`, tổng có giá trị số học chính xác. Kết quả giữ thông tin scale theo quy tắc phép cộng, nhưng vẫn chưa có thông tin `USD` hay `VND`.

### Không dùng double để tạo số tiền theo dạng con người nhập

Ví dụ:

~~~java
BigDecimal safe = new BigDecimal("0.1");  // chính xác bằng 0.1
BigDecimal exactBinary = new BigDecimal(0.1);
~~~

`new BigDecimal(0.1)` lấy **chính xác giá trị nhị phân mà double đang lưu**, vốn không bằng 0.1 trong hệ thập phân; vì vậy giá trị BigDecimal tạo ra có nhiều chữ số. Các đường tạo thường dùng:

- `new BigDecimal("0.1")`: dùng chuỗi thập phân đã được kiểm tra.
- `BigDecimal.valueOf(0.1)`: dùng biểu diễn chuỗi chuẩn của `double`, thường tốt hơn constructor nhận `double` trực tiếp, nhưng **không thể phục hồi mọi độ chính xác đã mất trước đó**.
- `BigDecimal.valueOf(12345, 2)`: tạo số `123.45` từ hệ số nguyên và scale đã chỉ định; phù hợp khi giao thức gửi đơn vị nhỏ nhất theo một **thang đo đã được thỏa thuận**.

Ví dụ dùng integer minor units:

~~~java
BigDecimal amount = BigDecimal.valueOf(12345, 2); // 123.45
~~~

Nhưng đừng coi `2` là scale cố định của **mọi loại tiền**. Một giao thức có thể gửi số tiền nguyên theo đơn vị nhỏ nhất, song hệ số chia phải được hợp đồng giao tiếp quy định cho từng loại tiền hoặc từng phiên bản API; `Currency.getDefaultFractionDigits()` không thay thế đặc tả API.

### Scale và precision là hai khái niệm khác nhau

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `scale()` | `new BigDecimal("12.340").scale() == 3` | Ba chữ số sau dấu thập phân trong biểu diễn |
| `precision()` | `new BigDecimal("12.340").precision() == 5` | Năm chữ số có nghĩa của hệ số thập phân |
| Giá trị số học | `12.34` và `12.340` | Bằng nhau theo `compareTo`, dù scale khác |
| `MathContext` | `new MathContext(5, HALF_EVEN)` | Điều khiển **precision** của phép tính, không phải chính sách luôn giữ 2 chữ số thập phân |

`setScale(2, RoundingMode.HALF_EVEN)` chỉ định số chữ số ở phần thập phân. `round(new MathContext(5, ...))` giới hạn số chữ số có nghĩa. Với tiền, hai hành vi này có mục đích khác nhau, không được thay thế máy móc.

## 3. Currency: mã tiền và thông tin tiền tệ

`java.util.Currency` đại diện cho một đơn vị tiền được JDK nhận biết.

~~~java
import java.util.Currency;

Currency usd = Currency.getInstance("USD");
Currency vnd = Currency.getInstance("VND");
Currency jpy = Currency.getInstance("JPY");
Currency kwd = Currency.getInstance("KWD");

System.out.println(usd.getCurrencyCode());         // USD
System.out.println(usd.getDefaultFractionDigits()); // 2
System.out.println(vnd.getDefaultFractionDigits()); // 0
System.out.println(jpy.getDefaultFractionDigits()); // 0
System.out.println(kwd.getDefaultFractionDigits()); // 3
~~~

Đoạn code trên minh họa các kết quả thường gặp với dữ liệu tiền tệ của JDK; mã và dữ liệu có thể được cập nhật theo phiên bản/runtime. Khi sản phẩm dựa trên thông tin tiền tệ có hiệu lực theo thời điểm, cần kiểm tra phiên bản dữ liệu và chính sách pháp lý/nghiệp vụ tương ứng.

`Currency.getInstance(code)` nhận **mã tiền tệ**, không nhận một chuỗi số tiền. Với mã không hợp lệ hoặc không được hỗ trợ, nó có thể ném `IllegalArgumentException`; `null` gây `NullPointerException`. Với input từ người dùng/API, phải kiểm tra và xử lý thay vì ghi nhận tùy ý một mã sai.

### getDefaultFractionDigits() chỉ là metadata

`Currency.getDefaultFractionDigits()` cho biết số chữ số thập phân mặc định được xác định trong dữ liệu tiền tệ mà JDK dùng; API có thể trả `-1` cho trường hợp không áp dụng/không xác định số chữ số thông thường.

**Không đồng nhất số này với chính sách làm tròn bắt buộc của mọi nghiệp vụ.**

- Một phép tính thuế bằng USD có thể cần nhiều chữ số trung gian hơn 2.
- Một khoản thanh toán bằng VND thường được chốt ở số nguyên đồng, nhưng các phép tính trước đó có thể mang phần lẻ.
- Một luồng tiền mặt có thể phải làm tròn đến **bước giá trị cụ thể**, không chỉ chọn số chữ số sau dấu thập phân. Ví dụ yêu cầu làm tròn theo bội số `0.05` không tương đương `setScale(2, mode)`.
- Phương pháp hạch toán, chính sách của cổng thanh toán và quy định pháp lý có thể khác nhau; phải xác nhận chúng thay vì suy ra từ `Currency`.

`Currency.getSymbol(locale)` và `getDisplayName(locale)` phục vụ **trình bày**, không nên là định danh lưu trữ. Ký hiệu `$` có thể liên quan đến nhiều đồng tiền; mã `USD` và `CAD` thì khác nhau.

### Mã tiền không phải locale

`Locale.forLanguageTag("en-US")` là ngữ cảnh ngôn ngữ/vùng. `Currency.getInstance("USD")` là đơn vị tiền. Một người dùng hiển thị giao diện tiếng Việt có thể xem giá trị tính bằng USD, JPY hoặc EUR.

Không suy ra currency chỉ từ locale khi người dùng/hợp đồng giao dịch đã chỉ rõ mã tiền. `Currency.getInstance(locale)` có thể hữu ích để lấy đồng tiền mặc định gắn với vùng phù hợp, nhưng nó **không chứng minh đồng tiền được dùng cho một giao dịch cụ thể**.

## 4. RoundingMode: chỉ định hành vi, không chỉ kết quả

Với số `2.345` cần làm tròn đến 2 chữ số thập phân:

~~~java
BigDecimal value = new BigDecimal("2.345");

value.setScale(2, RoundingMode.HALF_UP);   // 2.35
value.setScale(2, RoundingMode.HALF_EVEN); // 2.34
~~~

Đây là đoạn minh họa trong phương thức đã import `java.math.BigDecimal` và `java.math.RoundingMode`. Hai kết quả khác nhau **đều có thể hợp lệ** tùy hợp đồng. Ứng dụng không nên tùy tiện đổi mode chỉ để nhìn “đẹp” hơn.

### Những mode cần hiểu

| RoundingMode | Ý nghĩa cơ bản | Lưu ý |
| --- | --- | --- |
| `UP` | Tăng độ lớn, xa 0 nếu phải bỏ chữ số | Không giống `CEILING` với số âm |
| `DOWN` | Giảm độ lớn, về 0 | Không giống `FLOOR` với số âm |
| `CEILING` | Hướng tới (+∞) | Với số âm có thể gần 0 hơn |
| `FLOOR` | Hướng tới (-∞) | Với số âm có thể xa 0 hơn |
| `HALF_UP` | Gần nhất; nếu đúng giữa hai mức, chọn xa 0 | Thường gặp nhưng không mặc nhiên là chuẩn pháp lý |
| `HALF_DOWN` | Gần nhất; nếu đúng giữa hai mức, chọn gần 0 | Cần kiểm tra ví dụ tie |
| `HALF_EVEN` | Gần nhất; ở điểm giữa, chọn chữ số cuối giữ lại là chẵn | Thường được gọi là “banker's rounding” |
| `UNNECESSARY` | Không chấp nhận trường hợp phải làm tròn | Ném `ArithmeticException` nếu mất độ chính xác |

Làm tròn ở số âm cần được kiểm thử riêng: `RoundingMode.CEILING` không có nghĩa “luôn tăng phần trị tuyệt đối” mà là hướng về (+∞). Tương tự, `HALF_UP` không đơn giản là cộng `0.5` rồi cắt phần nguyên với mọi số và scale.

Một ví dụ điểm giữa khác: `new BigDecimal("2.355").setScale(2, HALF_EVEN)` thành `2.36` vì chữ số hàng phần trăm cuối cùng `6` là chẵn. Không diễn giải “HALF_EVEN luôn làm tròn xuống”; ở điểm tie, nó chọn phía cho chữ số giữ lại là chẵn.

### Không làm tròn ngầm

Có thể cho phép số tiền chứa scale cao trong tính toán, rồi chỉ làm tròn ở ranh giới được quy định như **chốt đơn hàng**, **ghi số tiền phải thanh toán**, **tính thuế theo dòng hóa đơn** hoặc **xuất báo cáo**.

Cách thiết kế sai là mỗi phép `add`, `multiply`, `divide` hoặc constructor `Money` đều tự áp `setScale(currency.getDefaultFractionDigits(), HALF_UP)` mà không có lý do nghiệp vụ. Nó làm mất thông tin trung gian và có thể tạo tổng tiền khác khi đổi thứ tự các phép tính.

## 5. Quy tắc làm tròn còn gồm thời điểm và đơn vị làm tròn

Một `RoundingPolicy` hữu dụng phải mô tả nhiều hơn `RoundingMode`:

- **Phép tính nào:** thuế, phí, giảm giá, tổng thanh toán, đổi tiền, lãi.
- **Làm tròn khi nào:** trên từng dòng, từng đơn vị, theo từng loại thuế hay trên tổng.
- **Độ chia/step:** `scale=2`, `scale=0` hoặc bội số `0.05` tùy ngữ cảnh.
- **Mode:** `HALF_UP`, `HALF_EVEN`, `DOWN`, v.v.
- **Cách xử lý hoàn tiền, số âm và phần dư:** phải nhất quán với yêu cầu nghiệp vụ.
- **Thông tin pháp lý hoặc hợp đồng:** nếu có, phải được rà soát bởi chủ sở hữu nghiệp vụ.

Hai cách làm tròn đều có thể “đúng theo mode”, nhưng tổng khác nhau vì **thời điểm làm tròn khác**:

~~~text
Giá trị 1: 0.005 USD
Giá trị 2: 0.005 USD

Làm tròn từng giá trị với HALF_UP, scale 2:
0.005 → 0.01
0.005 → 0.01
Tổng: 0.02 USD

Cộng trước rồi làm tròn với HALF_UP, scale 2:
0.005 + 0.005 = 0.010
Tổng sau làm tròn: 0.01 USD
~~~

Sự khác biệt không phải lỗi của `BigDecimal`; đây là hệ quả của chính sách. Cần quy định rõ nghiệp vụ tính theo từng dòng hay tổng, đặc biệt với thuế, chiết khấu và chia tiền cho nhiều người.

### Làm tròn theo bước không chỉ dùng setScale

Nếu một chính sách tiền mặt đòi bước `0.05`, `setScale(2, ...)` đơn thuần vẫn cho phép `10.01` hoặc `10.02`, tức **không ép thành bội số 0.05**.

Một cách biểu diễn khái niệm:

~~~text
amount / 0.05 → làm tròn số đơn vị bước → nhân lại 0.05
~~~

Đây chỉ là mô tả quy trình; khi hiện thực cần dùng `BigDecimal` và xác nhận quy tắc cho số âm, tie, thời điểm áp dụng, giá trị bước và kết quả cần bảo toàn. Không áp dụng bước tiền mặt cho khoản chuyển khoản chỉ vì giao dịch dùng cùng mã tiền.

## 6. Xây một Money value object bằng Java 17

Một cách bảo vệ invariant là gói `BigDecimal` và `Currency` trong một kiểu bất biến, rồi để thao tác chốt tiền nhận **quy tắc làm tròn tường minh**. Java 17 hỗ trợ `record`, phù hợp minh họa mô hình này.

Tạo tệp **`MoneyDimensionsDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

public class MoneyDimensionsDemo {
    record Money(BigDecimal amount, Currency currency) {
        Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");
        }

        Money add(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("Currency mismatch");
            }
            return new Money(amount.add(other.amount), currency);
        }

        Money rounded(int scale, RoundingMode mode) {
            return new Money(amount.setScale(scale, mode), currency);
        }

        String displayRaw() {
            return currency.getCurrencyCode() + " " + amount.toPlainString();
        }
    }

    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        Currency vnd = Currency.getInstance("VND");
        Currency kwd = Currency.getInstance("KWD");

        System.out.println("Digits USD="
                + usd.getDefaultFractionDigits()
                + ", VND=" + vnd.getDefaultFractionDigits()
                + ", KWD=" + kwd.getDefaultFractionDigits());

        Money a = new Money(new BigDecimal("12.345"), usd);
        Money b = new Money(new BigDecimal("0.015"), usd);

        System.out.println("Exact sum: " + a.add(b).displayRaw());
        System.out.println("Settled sum: " + a.add(b)
                .rounded(2, RoundingMode.HALF_EVEN).displayRaw());

        BigDecimal tie = new BigDecimal("2.345");
        System.out.println("HALF_UP: "
                + tie.setScale(2, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN: "
                + tie.setScale(2, RoundingMode.HALF_EVEN));

        System.out.println("One third: "
                + BigDecimal.ONE.divide(
                        new BigDecimal("3"),
                        2,
                        RoundingMode.HALF_UP));

        try {
            a.add(new Money(new BigDecimal("100"), vnd));
        } catch (IllegalArgumentException ex) {
            System.out.println("Mismatch: " + ex.getMessage());
        }

        try {
            tie.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("Precision loss: rejected");
        }

        System.out.println("String construction: "
                + new BigDecimal("0.1").toPlainString());
        System.out.println("Double construction exact 0.1: "
                + (new BigDecimal(0.1)
                        .compareTo(new BigDecimal("0.1")) == 0));
    }
}
~~~

Biên dịch/chạy (Java 17 trở lên):

~~~bash
javac -encoding UTF-8 MoneyDimensionsDemo.java
java MoneyDimensionsDemo
~~~

Stdout đã đối chiếu với JDK:

~~~text
Digits USD=2, VND=0, KWD=3
Exact sum: USD 12.360
Settled sum: USD 12.36
HALF_UP: 2.35
HALF_EVEN: 2.34
One third: 0.33
Mismatch: Currency mismatch
Precision loss: rejected
String construction: 0.1
Double construction exact 0.1: false
~~~

**Giải thích:**

1. `Currency` giữ mã tiền và metadata số chữ số thập phân mặc định; ba mã trong ví dụ có thông số lần lượt `2`, `0`, `3`.
2. Hai khoản USD được cộng **chính xác**: `12.345 + 0.015 = 12.360`. Phép cộng không tự bỏ số lẻ.
3. `rounded(2, HALF_EVEN)` tạo **Money mới** với amount `12.36`; bản gốc không bị thay đổi. Việc chọn `2` ở đây là chính sách chốt số của ví dụ, không được suy ra tự động từ mọi phép tính.
4. `2.345` nằm đúng giữa `2.34` và `2.35`; `HALF_UP` chọn `2.35`, `HALF_EVEN` chọn `2.34`.
5. Phép chia `1/3` chỉ ra một điểm cần quyết định mode/scale: `divide(..., 2, HALF_UP)` trả `0.33`.
6. Cộng USD với VND bị từ chối, tránh âm thầm trộn đơn vị.
7. `UNNECESSARY` báo lỗi nếu việc đặt scale buộc phải bỏ chữ số có ý nghĩa.
8. `new BigDecimal("0.1")` giữ đúng 0.1 thập phân; `new BigDecimal(0.1)` phản ánh xấp xỉ nhị phân nên không bằng 0.1 chính xác.

`displayRaw()` cố ý in theo định dạng máy ổn định `USD 12.36` để dễ kiểm thử; đây **không phải** định dạng UI bản địa hóa. Mã tiền và amount được lưu riêng trong record, còn quy tắc làm tròn được truyền khi cần.

**Giới hạn của ví dụ:** record không thay thế một thư viện tiền tệ sản xuất. Nó chưa lưu policy theo từng chức năng, chưa giải quyết tỷ giá, ngân hàng, phí, cash rounding, lịch sử dữ liệu tiền, giới hạn tối đa hoặc việc phân bổ phần dư. Mục đích là thể hiện rõ ba trách nhiệm độc lập.

## 7. Phép tính: giữ chính xác tới ranh giới được phép làm tròn

### Cộng và trừ

Dùng `add`/`subtract` cho hai amount cùng mã tiền. Nếu sử dụng Money wrapper, bắt buộc check currency khi cộng hoặc trừ.

~~~java
BigDecimal subtotal = new BigDecimal("10.005")
        .add(new BigDecimal("1.005")); // 11.010
~~~

Đoạn trên chưa làm tròn và chưa chọn chính sách tiền; hợp lệ nếu nghiệp vụ giữ ba chữ số trung gian.

### Nhân đơn giá với số lượng hoặc tỷ lệ

~~~java
BigDecimal unitPrice = new BigDecimal("1.235");
BigDecimal quantity = new BigDecimal("3");
BigDecimal exactLine = unitPrice.multiply(quantity); // 3.705
~~~

Nếu nghiệp vụ yêu cầu `scale=2`, cần quy định làm tròn `unitPrice` trước khi nhân hay `exactLine` sau khi nhân. Hai phương pháp có thể tạo kết quả khác, nên phải có quy tắc nghiệp vụ thống nhất và testcase.

### Phép chia

Một số phép chia thập phân không có kết quả hữu hạn. Ví dụ:

~~~java
BigDecimal.ONE.divide(new BigDecimal("3"));
~~~

có thể ném `ArithmeticException` vì `1/3` là thập phân vô hạn, không thể biểu diễn chính xác bằng một `BigDecimal` hữu hạn. Phải chỉ định độ chính xác/scale và mode khi nghiệp vụ cho phép làm tròn:

~~~java
BigDecimal third = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_EVEN);
// 0.3333
~~~

Không bắt mọi `ArithmeticException` rồi thay kết quả bằng 0. Trường hợp phép chia vô hạn, chia cho 0 và lỗi do `UNNECESSARY` thể hiện các tình huống khác nhau; lựa chọn xử lý phải phù hợp nguyên nhân.

### Khi chia một khoản tiền thành nhiều phần

Nếu chia `10.00 USD` cho ba người, phép chia chính xác hữu hạn theo cent sẽ không tồn tại (`10.00 / 3`). Làm tròn mỗi phần thành `3.33` cho cả ba chỉ thu được `9.99`. Cần chính sách **phân bổ phần dư** có thể kiểm toán, ví dụ hai người nhận `3.33`, người cuối nhận `3.34`, sao cho tổng đúng `10.00`.

Đây là một ví dụ rõ ràng: `BigDecimal` bảo đảm số học đúng theo thao tác đã yêu cầu, nhưng **không tự định nghĩa công bằng hoặc phân bổ tiền**.

## 8. BigDecimal.equals() và compareTo() không tương đương

Hai amount có thể bằng nhau về giá trị số nhưng khác scale:

~~~java
BigDecimal x = new BigDecimal("12.30");
BigDecimal y = new BigDecimal("12.300");

x.compareTo(y) == 0; // true: cùng giá trị số
x.equals(y);         // false: scale khác nhau
~~~

Điểm này quan trọng khi dùng `BigDecimal` làm khóa `Map`, phần tử `Set` hoặc thành phần trong `record Money`: phương thức `equals` mặc định của record dựa vào `equals` của các thành phần, nên `Money(12.30, USD)` và `Money(12.300, USD)` không nhất thiết bằng nhau theo `equals`.

Một số giải pháp hợp lý tùy miền nghiệp vụ:

- Chuẩn hóa scale tại **ranh giới lưu/truyền** nếu hợp đồng yêu cầu biểu diễn duy nhất.
- So sánh giá trị số qua `compareTo` khi chỉ muốn hỏi bằng nhau về mặt số học, đồng thời bảo đảm currency trùng.
- Giữ nguyên scale đầu vào khi thông tin đó có ý nghĩa, chẳng hạn độ chính xác đã được khai báo.
- Thận trọng với `stripTrailingZeros()`: nó có thể tạo scale âm, ví dụ số `1000` có thể được biểu diễn ở dạng số mũ. Không dùng nó một cách tự động cho mọi bản ghi tiền.

Không để cách thức so sánh ngầm làm các khoản tiền hợp lệ bị xem là khác nhau hoặc ngược lại.

## 9. Định dạng hiển thị là bước khác với lượng tiền lưu trữ

Khi giao diện cần in số tiền theo vùng, dùng `NumberFormat` hoặc `DecimalFormat` với `Locale`, đồng thời chỉ định `Currency` của **giao dịch**, thay vì tin rằng currency mặc định của locale luôn đúng:

~~~java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

NumberFormat formatter = NumberFormat.getCurrencyInstance(
        Locale.forLanguageTag("vi-VN"));
formatter.setCurrency(Currency.getInstance("USD"));
String ui = formatter.format(new java.math.BigDecimal("1234.50"));
~~~

Đây là **đoạn mã minh họa** không độc lập; output cụ thể phụ thuộc dữ liệu bản địa hóa/JDK và cấu hình formatter. Khi dùng `setCurrency`, cần đặc biệt lưu ý API `NumberFormat` **không bắt buộc tự điều chỉnh số chữ số thập phân theo currency mới**. Nếu ứng dụng cần một cách hiển thị nhất quán theo chính sách, hãy cấu hình các thuộc tính fraction digits phù hợp và kiểm thử.

Quan trọng: **format một số tiền không đồng nghĩa chốt số tiền đó**. Một formatter có thể làm tròn giá trị để hiện thị, trong khi amount nguồn vẫn có nhiều chữ số. Không dùng chuỗi UI đã được format làm nguồn sự thật để tính tổng hoặc lưu vào sổ cái.

### Không trộn currency symbol với mã tiền

Các ký hiệu như `$`, `¥`, `kr` có thể dùng cho nhiều đơn vị tiền hoặc khác cách biểu diễn theo locale. Khi truyền dữ liệu qua hệ thống hoặc audit, giữ mã như `USD`, `VND`, `JPY` hoặc một định danh tiền đã thỏa thuận. Chỉ tạo symbol cho lớp giao diện.

### Locale và tỷ giá là các vấn đề độc lập

Một số tiền `100 USD` được hiển thị cho người dùng Việt Nam không tự đổi thành VND. Muốn đổi tiền, cần tỷ giá được công bố:

~~~text
convertedAmount = sourceAmount × exchangeRate
~~~

Cần xác định currency nguồn, currency đích, rate, chiều tỷ giá, thời điểm/nguồn và chính sách làm tròn. `Currency` không có phương thức chuyển đổi giữa USD và VND.

## 10. Lưu trữ, API và hợp đồng trao đổi dữ liệu

Một thiết kế dữ liệu dễ kiểm toán là tách các trường:

~~~json
{
  "amount": "1234.50",
  "currency": "USD"
}
~~~

Ở đây `amount` là chuỗi số thập phân chuẩn do API quy định và `currency` là mã tiền. Cách dùng chuỗi tránh việc nhiều client hoặc thư viện trung gian tự chuyển giá trị thành kiểu floating-point với độ chính xác không đáp ứng nghiệp vụ. Đây là **một lựa chọn thiết kế API**, không có nghĩa mọi giao thức đều bắt buộc dùng chuỗi.

Nếu API dùng số nguyên minor units:

~~~json
{
  "minorUnits": 123450,
  "currency": "USD",
  "scale": 2
}
~~~

thì số tiền là `1234.50 USD` theo hợp đồng `minorUnits × 10^(-scale)`. Không được chỉ dựa vào tên trường `minorUnits` rồi đoán scale là 2 cho mọi đồng tiền. Thậm chí với cùng một loại tiền, một số hệ thống thanh toán có quy tắc scale chuyên biệt theo phiên bản hoặc kênh; phải tuân thủ tài liệu hệ thống đó.

### Cơ sở dữ liệu

Các cột thường dùng là `DECIMAL/NUMERIC` cho amount và `CHAR(3)` hoặc `VARCHAR(3)` cho mã ISO currency (tùy hệ quản trị). Tránh `FLOAT/DOUBLE` cho số tiền cần độ chính xác thập phân.

Ví dụ cấu trúc khái niệm:

~~~sql
CREATE TABLE invoice_amount (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(20, 6) NOT NULL,
    currency_code CHAR(3) NOT NULL
);
~~~

Đây là **minh họa SQL**; cú pháp, kiểu dữ liệu và giới hạn có thể khác theo database. `DECIMAL(20,6)` nghĩa là tổng precision 20 chữ số và scale 6 — **không phải chính sách chốt tiền**. Cần thiết kế precision/scale dựa trên giá trị tối đa, số lượng trung gian và ràng buộc sản phẩm. Đừng để database tự làm tròn hoặc cắt dữ liệu âm thầm khi ứng dụng chưa định nghĩa hành vi đó.

Khi ghi tiền vào ledger hoặc tạo sự kiện thanh toán, nên lưu chính sách/phiên bản tính toán cần thiết để đối chiếu về sau, nhất là với thuế, đổi tiền hoặc giao dịch bị hoàn tiền nhiều năm sau.

## 11. Xác thực tiền và chính sách rounding

Một `Money` phù hợp production nên xét:

- `amount` và `currency` không `null`.
- Mã tiền thuộc danh sách hợp lệ/được chấp nhận của hệ thống, không chỉ đúng cú pháp.
- Giới hạn số chữ số và biên giá trị phù hợp database, API và nhà cung cấp thanh toán.
- Cho phép hay cấm số âm theo **loại nghiệp vụ**, không cấm mọi số âm vì hoàn tiền/điều chỉnh có thể âm.
- Có cho phép `amount=0` hay không, theo đặc tả.
- Trạng thái trước khi làm tròn và sau khi chốt, không tự làm tròn tất cả phép toán.
- Bảo đảm các phép cộng/trừ không trộn currency; phép đổi tiền phải có rate rõ ràng.
- Kiểm soát logic rounding tại cùng một điểm duy nhất của nghiệp vụ và kiểm thử nhiều lần.
- Chốt scale/step/mode vào tài liệu hợp đồng giao tiếp, cùng thay đổi phiên bản nếu có.
- Bảo đảm số sau chốt không vượt giới hạn được hệ thống downstream chấp nhận.

Nếu hệ thống chỉ xử lý USD, có thể chọn một chính sách phù hợp đơn giản; khi mở rộng sang JPY, VND, KWD hoặc thanh toán tiền mặt, đừng giả định chính sách USD hiện tại vẫn đúng.

## 12. Bảng lỗi phổ biến

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| `new BigDecimal(0.1)` cho giá người dùng nhập | Nhận chính xác xấp xỉ double, không phải 0.1 thập phân | Tạo từ chuỗi thập phân hoặc integer + scale đã thỏa thuận |
| Chỉ lưu amount, bỏ currency | Không biết USD hay VND | Luôn lưu mã tiền cùng giá trị |
| Dùng currency symbol làm định danh | `$` không phân biệt nhiều đồng tiền | Dùng mã ISO 4217 |
| Cộng USD với VND | Tổng sai về đơn vị | Từ chối hoặc quy đổi minh bạch trước |
| Dùng `getDefaultFractionDigits()` như luật làm tròn mọi phép tính | Mất phần lẻ cần thiết, có thể sai thuế/phí | Tách metadata khỏi chính sách nghiệp vụ |
| Làm tròn mỗi phép trung gian theo default | Tổng phụ thuộc thứ tự xử lý | Định nghĩa thời điểm rounding chính xác |
| Nhầm precision với scale | Kết quả sai mức độ chính xác cần giữ | Dùng `MathContext` và `setScale` đúng mục đích |
| Dùng `divide` không có mode trong phép chia vô hạn | `ArithmeticException` | Chọn scale/precision và rounding mode theo nghiệp vụ |
| Dùng `equals` để so BigDecimal về giá trị số | `12.30` khác `12.300` | Kiểm tra currency và dùng `compareTo` nếu cần so giá trị |
| Coi định dạng UI đã làm tròn là số tiền chính thức | Chốt số sai hoặc mất tính truy vết | Giữ giá trị gốc và bước chốt riêng |
| Bỏ qua số âm | Phát sinh lỗi với hoàn tiền, CEILING/FLOOR | Kiểm thử số âm và quy tắc hoàn tiền |
| Cho rằng `scale=2` là làm tròn tiền mặt theo 0.05 | Có thể ra 10.02, không phải bội 0.05 | Dùng chính sách làm tròn theo bước |
| Dùng `double` lưu tiền trong JSON/DB | Mất độ chính xác thập phân trong một số hệ thống | Hợp đồng decimal string/minor units, cột DECIMAL |
| Dùng locale để suy ra currency giao dịch | Chọn sai đơn vị của giao dịch | Currency là dữ liệu nghiệp vụ độc lập |
| Không lưu phiên bản policy | Khó tái lập số tiền trên hóa đơn cũ | Ghi đủ quy tắc và lịch sử tính toán cần thiết |

## 13. Kiểm thử những trường hợp dễ gây sai số

Một bảng test tốt cần bao phủ **giá trị**, **currency**, **scale**, **mode** và **thời điểm làm tròn**, không chỉ ví dụ `1.23`:

| Input / tình huống | Kỳ vọng hoặc kiểm tra |
| --- | --- |
| `2.345` → scale 2, `HALF_UP` | `2.35` |
| `2.345` → scale 2, `HALF_EVEN` | `2.34` |
| `2.355` → scale 2, `HALF_EVEN` | `2.36` |
| `-2.345` → scale 2, `HALF_UP` | `-2.35` |
| `-2.345` → scale 2, `HALF_EVEN` | `-2.34` |
| `1 / 3` → scale 2, `HALF_UP` | `0.33` |
| `1 / 3` → chia chính xác không mode | Có thể ném `ArithmeticException` |
| `12.30` so với `12.300` | `compareTo==0`, `equals==false` |
| `12.345 USD + 0.015 USD` | `12.360 USD` trước rounding |
| `USD + VND` | Bị từ chối |
| `0.005 + 0.005`, rounding từng dòng so với tổng | `0.02` so với `0.01` với HALF_UP scale 2 |
| `VND`, `JPY`, `KWD` | Kiểm tra policy riêng, không mặc định scale 2 |
| `1000.00` với giới hạn DB nhỏ | Xác nhận giới hạn và hành vi ghi không bị cắt |
| Bước tiền `0.05` | Mọi số đã chốt phải là bội số chính xác của `0.05` |
| Tổng phân bổ cho ba người | Tổng các phần phải bằng khoản tiền ban đầu |
| Format bằng `Locale` khác | Số tiền gốc/currency không thay đổi |

Các test property-based hữu ích: phép cộng không đổi mã tiền; số tiền không đổi khi chỉ định dạng; việc chốt lần hai theo cùng scale/mode không đổi số đã chốt; tổng các phần phân bổ khớp tổng gốc; mọi giao dịch qua ranh giới API/DB đều giữ đúng số và currency.

Nếu luật rounding bị ràng buộc bởi quy định pháp luật hoặc chuẩn của đơn vị thanh toán, phải có testcase do chủ sở hữu nghiệp vụ xác nhận; ví dụ kiến thức Java không thể thay cho đặc tả chính thức.

## 14. Bài tập tự đánh giá

**Câu 1.** Tại sao dùng `BigDecimal` vẫn chưa đủ để đại diện cho tiền?

**Đáp án:** `BigDecimal` chỉ nắm giá trị số, không biết mã currency, thời điểm làm tròn, bước tiền, tỷ giá hoặc chính sách nghiệp vụ.

**Câu 2.** `Currency.getDefaultFractionDigits()` trả `0` với VND. Có phải mọi phép tính bằng VND phải lập tức chuyển về số nguyên?

**Đáp án:** Không. Đây là metadata chữ số thập phân mặc định. Phép tính thuế/giảm giá có thể giữ phần lẻ trung gian; việc chốt giao dịch và làm tròn dựa vào nghiệp vụ.

**Câu 3.** `new BigDecimal("2.345")` làm tròn scale 2 bằng `HALF_EVEN` và `HALF_UP` cho cùng kết quả không?

**Đáp án:** Không. `HALF_EVEN` trả `2.34`; `HALF_UP` trả `2.35`.

**Câu 4.** Vì sao `new BigDecimal("1").divide(new BigDecimal("3"))` có thể ném lỗi?

**Đáp án:** `1/3` có biểu diễn thập phân vô hạn, không thể lưu chính xác dưới dạng `BigDecimal` hữu hạn nếu không quy định scale/precision cùng mode.

**Câu 5.** Khi người dùng mở giao diện ở locale `vi-VN`, tiền trong hóa đơn có tự chuyển từ USD sang VND không?

**Đáp án:** Không. Locale chỉ tác động ngữ cảnh hiển thị/định dạng; chuyển currency cần tỷ giá và quy tắc chuyển đổi tường minh.

**Bài thực hành.** Mở rộng `MoneyDimensionsDemo` với kiểu `RoundingPolicy(scale, mode)` và hai chính sách riêng: làm tròn tiền từng dòng với `HALF_UP` và làm tròn trên tổng với `HALF_EVEN`. Cho ba giá trị có phần nghìn và chứng minh sự khác nhau. Thêm test số âm, currency mismatch, `UNNECESSARY` và bất biến tổng sau khi phân bổ. Giải thích trường hợp nào trong nghiệp vụ sẽ chọn từng policy.

## 15. Tài liệu chính thức

- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): số học thập phân, scale, precision, `setScale`, `divide`, `equals` và `compareTo`.
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): các mode và quy tắc làm tròn.
- [Java SE 17 — MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): giới hạn số chữ số có nghĩa và rounding.
- [Java SE 17 — Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html): mã tiền, symbol và default fraction digits.
- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): định dạng số và tiền theo locale.

**Kết luận:** Một số tiền đáng tin cậy là **giá trị BigDecimal chính xác + mã Currency xác định + quy tắc làm tròn nghiệp vụ tường minh**. Không đồng nhất scale với precision, metadata currency với chính sách chốt tiền, hoặc chuỗi định dạng UI với dữ liệu dùng tính toán. Xác định **làm tròn khi nào, ở mức nào và bằng mode nào** trước khi viết phép tính tài chính.
