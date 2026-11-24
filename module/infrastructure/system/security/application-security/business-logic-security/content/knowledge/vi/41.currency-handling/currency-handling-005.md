# Currency precision: bảo vệ độ chính xác của tiền trong logic nghiệp vụ

## 1. Một chữ số thừa có thể phá vỡ quy tắc nghiệp vụ

Giả sử API nhận yêu cầu trả 10,009 đơn vị tiền. Lớp kiểm tra số dư cắt xuống thành 10,00, nhưng lớp ghi nhận cho người nhận lại làm tròn thành 10,01. Mỗi lần xử lý, hệ thống có thể tạo ra một chênh lệch nhỏ. Khi lặp lại nhiều lần hoặc chia giao dịch thành nhiều phần, sai lệch trở thành một cách lạm dụng nghiệp vụ.

Một tình huống khác: backend chấp nhận giá trị có ba chữ số thập phân, database tự làm tròn xuống hai chữ số, còn mã idempotency được tính từ chuỗi đầu vào chưa chuẩn hóa. Cùng một ý nghĩa tiền có nhiều cách biểu diễn; một yêu cầu có thể được kiểm tra, lưu và đối chiếu theo các giá trị khác nhau.

*Currency precision* là việc xác định và duy trì độ chính xác của số tiền theo tiền tệ, đơn vị biểu diễn và công đoạn xử lý. Trong bảo mật logic nghiệp vụ, mục tiêu là giữ invariant: **số tiền được xác thực, được duyệt, được trừ, được cộng và được đối soát phải có cùng ý nghĩa nghiệp vụ**.

Bài học tập trung vào cách biểu diễn tiền, kiểm tra phần lẻ, làm tròn, chuyển đổi đơn vị và ngăn lợi dụng sai lệch. Những cơ chế này cần kết hợp với quyền theo đối tượng, state machine, transaction và idempotency; tính toán chính xác vẫn có thể chuyển tiền sai người nếu thiếu kiểm tra quyền.

## 2. Phân biệt precision, scale và đơn vị tiền

### 2.1. Precision và scale không phải cùng một khái niệm

Trong `BigDecimal` của Java:

- **Precision** là số chữ số của phần số nguyên không dấu dùng để biểu diễn giá trị, tức unscaled value.
- **Scale** mô tả vị trí dấu thập phân: giá trị bằng `unscaledValue × 10^(-scale)`.

Ví dụ:

| Chuỗi tạo `BigDecimal` | Unscaled value | Precision | Scale |
|---|---:|---:|---:|
| `123.45` | 12345 | 5 | 2 |
| `10.000` | 10000 | 5 | 3 |
| `0.10` | 10 | 2 | 2 |

Precision không có nghĩa là “số chữ số sau dấu thập phân”. `new MathContext(2)` giới hạn hai chữ số có nghĩa; nó không tương đương với quy tắc tiền có hai chữ số thập phân. Ví dụ, làm tròn `123.45` với precision bằng 2 có thể cho giá trị `1.2E+2`, tức 120, tùy chế độ làm tròn.

`BigDecimal` cũng có thể có scale âm, chẳng hạn sau một số thao tác loại bỏ số 0 tận cùng. Không dùng dấu của scale hoặc một kiểm tra chuỗi đơn giản để suy ra tiền tệ của giá trị.

### 2.2. Đơn vị hiển thị và đơn vị lưu trữ

Giả sử một sản phẩm cấu hình USD với hai chữ số thập phân:

```text
Đơn vị chính:       12.34 USD
Đơn vị nhỏ nhất:      1234 đơn vị, với scale = 2

major = minor / 10^scale
minor = major × 10^scale
```

Trong bài, ví dụ dùng USD với scale 2, JPY với scale 0 và KWD với scale 3. Đây là các cấu hình minh họa theo tiền tệ; triển khai thực tế phải có danh mục được quản lý và đối chiếu thêm hợp đồng của nhà cung cấp. Không dùng một hằng số `100` cho mọi tiền tệ.

Cần phân biệt ba loại quy tắc:

| Quy tắc | Ví dụ | Ý nghĩa |
|---|---|---|
| Độ chính xác của số tiền | Cho phép hai chữ số thập phân | Miền số tiền có thể ghi nhận |
| Bước giao dịch | Chỉ cho đặt số tiền theo bội của 0,05 | Giới hạn bổ sung của sản phẩm hoặc phương thức |
| Độ chính xác tính trung gian | Tỷ giá hoặc đơn giá có nhiều chữ số hơn số tiền cuối | Giữ thông tin để tính và lượng tử hóa tại điểm đã định |

Một số tiền biểu diễn được bằng hai chữ số thập phân chưa chắc là bội của 0,05. Ngược lại, không được lấy quy tắc làm tròn tiền mặt của một phương thức áp cho mọi giao dịch điện tử.

### 2.3. Tiền luôn đi kèm ngữ cảnh

`1000` đứng một mình không đủ để diễn giải tiền. Nó có thể là 1.000 đơn vị chính hoặc 10,00 đơn vị chính tùy hợp đồng.

Một giá trị tiền cần gắn với:

```text
currency + amount + đơn vị biểu diễn + quy tắc đơn vị đã áp dụng
```

Nếu lưu số nguyên đơn vị nhỏ nhất, phải biết số nguyên đó thuộc tiền tệ và định nghĩa đơn vị nào. Khi quy tắc thay đổi, không được diễn giải dữ liệu lịch sử theo một scale mới mà không có kế hoạch chuyển đổi rõ ràng.

## 3. Chốt invariant trước khi chọn kiểu dữ liệu

Đối với API chuyển tiền, có thể xác định những invariant sau:

1. Tiền tệ thuộc danh mục được phép cho sản phẩm và tài khoản liên quan.
2. Số tiền dương, đạt mức tối thiểu và không vượt giới hạn nghiệp vụ.
3. Đầu vào biểu diễn chính xác theo đơn vị cho phép; không âm thầm bỏ phần lẻ không hợp lệ.
4. Chuyển đổi giữa đơn vị chính và đơn vị nhỏ nhất không làm mất thông tin hoặc tràn số.
5. Mọi phép cộng, nhân, tính phí và hoàn tiền dùng cùng quy tắc đã định.
6. Số tiền được thực thi khớp nội dung đã được phê duyệt.
7. Tổng tiền sau phân bổ vẫn bằng tổng tiền trước phân bổ theo chính sách.
8. Retry không tạo hiệu lực tài chính mới và không thay đổi ý nghĩa số tiền.

Một endpoint điều chỉnh sổ cái có thể cho phép số âm, nhưng đó là loại hành động khác với chuyển tiền dương. Không vì cần điều chỉnh mà bỏ kiểm tra dấu trên toàn bộ API thanh toán.

Lựa chọn số nguyên hay `BigDecimal` chỉ là một phần của giải pháp. Cả hai đều cần giới hạn đầu vào, đơn vị rõ ràng và kiểm tra tại mọi đường ghi.

## 4. Thiết kế hợp đồng API không mơ hồ

### 4.1. Hai cách biểu diễn phổ biến

Cách thứ nhất là số nguyên đơn vị nhỏ nhất, biểu diễn bằng chuỗi để tránh mất chính xác ở các hệ thống xử lý JSON:

```json
{
  "currency": "USD",
  "amount_minor": "1234"
}
```

Cách thứ hai là chuỗi thập phân theo đơn vị chính:

```json
{
  "currency": "USD",
  "amount": "12.34"
}
```

Trong cùng một endpoint, nên có một biểu diễn có thẩm quyền. Nếu nhận đồng thời `amount = "12.34"` và `amount_minor = "9999"`, phải có quy tắc từ chối xung đột; không để lớp kiểm tra dùng trường này còn lớp ghi tiền dùng trường kia.

Nếu nhận tiền tệ từ client, backend phải đối chiếu với tiền tệ của tài khoản, đơn hàng hoặc báo giá liên quan. Client không được tự gửi `scale = 0` để làm cho `1234` được hiểu theo đơn vị có lợi hơn.

### 4.2. Chuỗi tiền cho máy khác chuỗi tiền cho người

Một hợp đồng máy có thể quy định dấu chấm là dấu thập phân và không có dấu phân cách hàng nghìn. Các chuỗi hiển thị như `1.234,56` hoặc `1,234.56` phải được xử lý theo locale tại giao diện rồi chuyển sang định dạng API đã định.

Không dùng thao tác thay mọi dấu phẩy bằng dấu chấm để parse tiền. Chuỗi `1,234` có thể được hiểu là một phẩy hai ba bốn hoặc một nghìn hai trăm ba mươi bốn tùy locale.

Hợp đồng cần nói rõ có chấp nhận hay không:

- Ký pháp khoa học như `1e3`.
- Khoảng trắng, dấu cộng và số 0 ở đầu.
- Phần lẻ chỉ gồm số 0, như `10.000` cho tiền tệ scale 2.
- Số âm, giá trị 0 và đầu vào quá dài.

Nên giới hạn chiều dài trước khi parse. Đầu vào chứa hàng triệu chữ số hoặc số mũ cực lớn có thể tiêu tốn tài nguyên dù thư viện số học có độ chính xác tùy ý.

### 4.3. Không đưa tiền qua dấu phẩy động

Các số thập phân như 0,1 thường không có biểu diễn nhị phân hữu hạn. Vì thế, không dùng `float` hoặc `double` làm đường trung gian cho số tiền cần chính xác.

Trong Java:

```java
// Không giữ được ý nghĩa thập phân ban đầu một cách đáng tin cậy.
BigDecimal fromBinary = new BigDecimal(0.1);

// Giá trị thập phân chính xác từ hợp đồng chuỗi.
BigDecimal fromText = new BigDecimal("0.10");
```

`BigDecimal.valueOf(double)` có cách chuyển đổi thuận tiện hơn việc gọi constructor từ `double`, nhưng không thể khôi phục thông tin đã mất ở một phép tính dấu phẩy động trước đó. Giữ chuỗi thập phân hoặc số nguyên chính xác xuyên suốt luồng.

Tương tự, không để client JavaScript chuyển số nguyên rất lớn sang `Number` rồi mới biến thành chuỗi; phần chính xác có thể đã mất. Hợp đồng chuỗi chỉ giúp nếu các thành phần giữ đúng hợp đồng đó.

## 5. Biểu diễn bằng số nguyên đơn vị nhỏ nhất

### 5.1. Lợi ích và giới hạn

Với một tiền tệ có scale cố định, số nguyên giúp cộng trừ số tiền cuối mà không có phần lẻ. Ví dụ `1234` đơn vị nhỏ nhất cộng `66` bằng đúng `1300`.

Tuy nhiên:

- Phải kiểm tra tràn số.
- Không thể cộng hai giá trị khác tiền tệ chỉ vì đều là `long`.
- Đơn giá, tỷ giá và tỷ lệ phí có thể cần số thập phân ở bước trung gian.
- Đơn vị của nhà cung cấp có thể khác đơn vị nội bộ.

`long` có miền hữu hạn. Nếu nhân tiền với số lượng bằng phép `*` thông thường rồi kết quả tràn, hệ thống có thể kiểm tra sai hạn mức hoặc ghi số âm.

```java
long lineTotalMinor = Math.multiplyExact(unitPriceMinor, quantity);
long orderTotalMinor = Math.addExact(previousTotalMinor, lineTotalMinor);
```

Các phép toán chính xác vẫn cần giới hạn nghiệp vụ cho số lượng và số tiền. Lỗi tràn phải trở thành lỗi đầu vào hoặc lỗi miền nghiệp vụ được xử lý, không được bắt rồi trả về 0.

### 5.2. Đầu vào số nguyên vẫn cần validation

Với `amount_minor`, chỉ nhận chuỗi số nguyên theo schema đã định, kiểm tra giới hạn chiều dài, chuyển đổi chính xác và so với hạn mức. Không parse chuỗi bằng `double`, không gọi `longValue()` trên giá trị có phần lẻ để âm thầm cắt số.

`BigInteger` có thể phù hợp với miền giá trị lớn hơn, nhưng không có nghĩa là được nhận đầu vào không giới hạn. Cơ sở dữ liệu, giao thức và nhà cung cấp vẫn có miền hỗ trợ riêng.

## 6. Dùng `BigDecimal` và từ chối phần lẻ không hợp lệ

### 6.1. Từ chối không đồng nghĩa với làm tròn

Khi API nhận một số tiền thanh toán cuối cùng, thường cần xác minh giá trị đã thuộc miền cho phép. `RoundingMode.UNNECESSARY` hữu ích cho mục đích này:

```java
BigDecimal accepted = new BigDecimal("10.000")
    .setScale(2, RoundingMode.UNNECESSARY); // 10.00, không đổi giá trị

BigDecimal rejected = new BigDecimal("10.001")
    .setScale(2, RoundingMode.UNNECESSARY); // ArithmeticException
```

Ví dụ chọn chấp nhận chữ số 0 thừa vì giá trị vẫn biểu diễn chính xác ở scale 2. Nếu hợp đồng yêu cầu đúng số chữ số trong chuỗi, cần kiểm tra cú pháp thêm; đó là quy tắc biểu diễn khác với quy tắc giá trị.

`BigDecimal` là bất biến. Gọi `amount.setScale(...)` mà bỏ qua giá trị trả về không thay đổi biến `amount`.

### 6.2. Ví dụ Java chuyển đầu vào sang tiền nguyên chính xác

Lớp dưới đây minh họa Java 17 trở lên. `CurrencyRule` phải được backend lấy từ cấu hình đáng tin cậy sau khi xác minh tiền tệ và sản phẩm; không dựng rule từ `fractionDigits` hay hạn mức do client gửi.

Miền scale từ 0 đến 6 và chiều dài chuỗi tối đa 32 trong ví dụ là giới hạn của sản phẩm minh họa, không phải định nghĩa chung cho mọi tài sản hoặc tiền tệ.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.regex.Pattern;

public final class MoneyAmount {
    private static final Pattern DECIMAL =
        Pattern.compile("[0-9]+(?:\\.[0-9]+)?");

    public record CurrencyRule(
        String code,
        int fractionDigits,
        long maxMinor
    ) {
        public CurrencyRule {
            if (code == null || !code.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("Invalid currency rule");
            }
            if (fractionDigits < 0 || fractionDigits > 6 || maxMinor <= 0) {
                throw new IllegalArgumentException("Invalid monetary limits");
            }
        }
    }

    private final String currency;
    private final long minor;
    private final int fractionDigits;

    private MoneyAmount(String currency, long minor, int fractionDigits) {
        this.currency = currency;
        this.minor = minor;
        this.fractionDigits = fractionDigits;
    }

    public static MoneyAmount parsePositiveMajor(
        String raw,
        CurrencyRule rule
    ) {
        if (rule == null) {
            throw new IllegalArgumentException("Unsupported currency");
        }
        if (raw == null || raw.length() > 32 || !DECIMAL.matcher(raw).matches()) {
            throw new IllegalArgumentException("Invalid amount format");
        }

        final long units;
        try {
            BigDecimal major = new BigDecimal(raw)
                .setScale(rule.fractionDigits(), RoundingMode.UNNECESSARY);
            units = major.movePointRight(rule.fractionDigits())
                .longValueExact();
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                "Unsupported amount precision or range", ex
            );
        }

        if (units <= 0 || units > rule.maxMinor()) {
            throw new IllegalArgumentException("Amount outside allowed range");
        }

        return new MoneyAmount(rule.code(), units, rule.fractionDigits());
    }

    public String currency() {
        return currency;
    }

    public long minor() {
        return minor;
    }

    public String toMajorString() {
        return BigDecimal.valueOf(minor, fractionDigits).toPlainString();
    }
}
```

Điểm quan trọng của ví dụ:

- Regex cố ý không chấp nhận dấu, số mũ, khoảng trắng hoặc dấu phân cách hàng nghìn.
- Kiểm tra chiều dài xảy ra trước parse.
- `UNNECESSARY` không cho bỏ đi phần giá trị không biểu diễn được.
- `longValueExact()` không cho cắt phần lẻ hoặc tràn miền `long`.
- Giới hạn cuối được so trên cùng đơn vị nguyên.
- Giá trị kết quả giữ tiền tệ và scale để không format bằng một quy tắc ngẫu nhiên khác.

Lớp này chưa xử lý quyền, đối tượng nguồn/đích, số dư, transaction hoặc idempotency. Những kiểm tra đó thuộc luồng nghiệp vụ sử dụng giá trị tiền đã được chuẩn hóa.

Ví dụ hành vi, giả sử hạn mức cấu hình đủ lớn trừ khi có ghi chú:

| Rule | Chuỗi đầu vào | Kết quả |
|---|---|---|
| USD, scale 2 | `10.00` | 1000 đơn vị nhỏ nhất |
| USD, scale 2 | `10.000` | 1000, không thay đổi giá trị |
| USD, scale 2 | `10.001` | Từ chối phần lẻ |
| KWD, scale 3 | `0.001` | 1 đơn vị nhỏ nhất |
| JPY, scale 0 | `10.0` | 10, giá trị vẫn nguyên |
| JPY, scale 0 | `10.5` | Từ chối phần lẻ |
| USD, scale 2 | `0` | Từ chối vì chuyển tiền yêu cầu dương |
| USD, scale 2 | `1e3` | Từ chối theo schema ví dụ |
| USD, scale 2 | `92233720368547758.08` | Từ chối vì vượt miền `long` sau đổi đơn vị |

### 6.3. So sánh tiền phải xét cả giá trị và tiền tệ

Trong Java, `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` là `false` do khác scale, còn `compareTo()` trả về 0 vì cùng giá trị số.

Nếu kiểm tra giá trị tiền, dùng quy tắc so sánh đã chuẩn hóa, đồng thời kiểm tra tiền tệ. Không chỉ đổi `equals()` thành `compareTo()` rồi cho phép cộng hoặc so hạn mức giữa USD và JPY.

Với object dùng làm khóa map, fingerprint hoặc nội dung ký, cần một biểu diễn chuẩn thống nhất. Hai đối tượng “cùng tiền” không được bất ngờ trở thành hai khóa nghiệp vụ khác nhau do scale chuỗi khác nhau.

## 7. Làm tròn tại điểm nghiệp vụ đã xác định

### 7.1. Phân biệt validation và tính toán

Đầu vào số tiền cuối có thể phải bị từ chối nếu thừa phần lẻ. Trong khi đó, tính phí, thuế, chia khoản hoặc quy đổi có thể tạo kết quả cần làm tròn. Hai tình huống không nên dùng chung một hàm “normalize money” luôn tự làm tròn.

Quy tắc làm tròn cần nêu rõ:

- Áp dụng ở bước nào: từng dòng, từng hóa đơn, từng giao dịch hay tổng trong một kỳ.
- Scale hoặc bước tiền mục tiêu.
- Chế độ làm tròn.
- Cách xử lý chênh lệch phân bổ.
- Phiên bản quy tắc gắn với báo giá hoặc quyết định phê duyệt.

Ví dụ với giá trị dương ở scale 2:

| Giá trị | `HALF_UP` | `HALF_EVEN` |
|---|---:|---:|
| 1.005 | 1.01 | 1.00 |
| 1.015 | 1.02 | 1.02 |

Không có một chế độ làm tròn đúng cho mọi nghiệp vụ. Chọn theo chính sách sản phẩm và hợp đồng áp dụng, rồi dùng nhất quán. Không để mỗi service tự chọn mặc định.

`RoundingMode.DOWN` là hướng về 0, còn `FLOOR` là về âm vô cùng; chúng khác nhau với số âm. Nếu dùng số âm cho điều chỉnh, cần kiểm thử riêng thay vì suy từ các ví dụ số dương.

### 7.2. Thứ tự làm tròn ảnh hưởng tổng

Giả sử có ba dòng trung gian, mỗi dòng là 0,335 đơn vị tiền. Với `HALF_UP` tại scale 2:

```text
Làm tròn từng dòng rồi cộng:
  0.34 + 0.34 + 0.34 = 1.02

Cộng trước rồi làm tròn:
  0.335 × 3 = 1.005 -> 1.01
```

Hai kết quả khác nhau dù không có lỗi dấu phẩy động. Đây là khác biệt chính sách về điểm làm tròn.

Kẻ tấn công có thể thay đổi cách chia dòng, số lượng hoặc số giao dịch để hưởng cách làm tròn có lợi. Nếu nghiệp vụ yêu cầu phí tính theo tổng đơn hàng, không cho client tách payload thành nhiều phần rồi tính phí độc lập để giảm tổng phí.

Ngược lại, nếu hợp đồng quy định tính từng dòng, hệ thống phải giữ quy tắc đó và ghi nhận phần chênh lệch theo cách nhất quán. Không tự chuyển sang làm tròn cuối chỉ vì kết quả nhỏ hơn.

### 7.3. Bước tiền không phải số chữ số thập phân

Muốn số tiền là bội của 0,05 trong một miền scale 2, có thể kiểm tra số nguyên đơn vị nhỏ nhất chia hết cho 5. `setScale(2)` chỉ bảo đảm độ chính xác đến phần trăm; nó vẫn chấp nhận 0,03.

Nếu sản phẩm cần làm tròn theo bước, phải quy định riêng cách làm tròn bước và thời điểm áp dụng. Không dùng định dạng hiển thị hai chữ số để giả lập quy tắc này.

## 8. Phân bổ và hoàn tiền không được tạo thêm phần lẻ

### 8.1. Chia tổng có thể phát sinh số dư

Chia 0,05 đơn vị tiền cho ba người ở scale 2 không thể cho ba phần bằng nhau tuyệt đối. Nếu mỗi phần 0,01666... được làm tròn thành 0,02, tổng thành 0,06, vượt số tiền gốc.

Một cách phân bổ cho các phần có trọng số bằng nhau là làm việc bằng số nguyên:

```text
Tổng: 5 đơn vị nhỏ nhất
Số phần: 3

Thương nguyên: 5 / 3 = 1
Số dư:        5 % 3 = 2

Phân bổ: 2, 2, 1
Tổng:    5
```

Quy tắc chọn hai phần được thêm một đơn vị phải xác định được, chẳng hạn theo khóa đối tượng ổn định. Không để client sắp xếp lại mảng tùy ý để luôn nhận phần dư vào đối tượng có lợi.

Với trọng số khác nhau, có thể phân bổ theo phần nguyên và phần dư theo một thuật toán được quy định rõ. Cần giữ các invariant:

- Tổng các phần bằng đúng tổng ban đầu.
- Mỗi phần thuộc đơn vị được hỗ trợ.
- Không có phần âm ngoài ý nghĩa nghiệp vụ cho phép.
- Cùng đầu vào và cùng phiên bản chính sách cho cùng kết quả.

### 8.2. Hoàn tiền dựa trên số đã thu và phân bổ gốc

Khi hoàn từng phần, không nên tính lại mọi thứ theo giá, tỷ giá hoặc quy tắc làm tròn hiện tại nếu nghiệp vụ yêu cầu hoàn theo khoản gốc. Cần tham chiếu số tiền đã thu, phân bổ và chính sách hoàn tương ứng.

Ví dụ một đơn chỉ thu 0,05 nhưng ba lần hoàn độc lập đều làm tròn lên 0,02 sẽ tạo tổng hoàn 0,06. Cần giới hạn tổng hoàn thành công cộng phần đang giữ hạn mức không vượt số được phép hoàn.

Kiểm tra tổng này phải an toàn khi chạy đồng thời. Hai request cùng đọc “còn được hoàn 0,03” không được cùng hoàn 0,02 mà không phối hợp bằng transaction hoặc cập nhật có điều kiện.

Idempotency ngăn cùng một yêu cầu tạo hiệu lực lặp. Hạn mức hoàn bảo vệ tổng giữa nhiều yêu cầu khác nhau, kể cả khi kẻ tấn công đổi idempotency key.

## 9. Tỷ giá có precision riêng với số tiền

### 9.1. Không làm tròn tỷ giá theo scale của tiền

Tỷ giá là một tỷ lệ có hướng, không phải một số tiền trong tiền tệ nguồn. Scale 2 của một số tiền không có nghĩa tỷ giá cũng chỉ được giữ hai chữ số thập phân.

Ví dụ giả định, không phải báo giá thị trường:

```text
Nguồn: 10.01 USD
Tỷ giá: 25000 VND cho 1 USD

10.01 USD × 25000 VND/USD = 250250 VND
```

Nếu nhận số nguyên nguồn là 1001 mà quên đổi scale 2 trước khi nhân tỷ giá, kết quả sẽ sai 100 lần. Phải ghi rõ tỷ giá áp dụng cho đơn vị chính hay đơn vị nhỏ nhất của từng phía.

### 9.2. Chỉ lượng tử hóa ở ranh giới đã định

Một luồng chuyển đổi có thể gồm:

1. Chuyển số nguyên nguồn sang đơn vị chính chính xác.
2. Nhân với tỷ giá thập phân có độ chính xác phù hợp.
3. Tính phí hoặc chênh lệch theo thứ tự đã quy định.
4. Làm tròn số tiền đích theo chính sách của sản phẩm và tiền tệ đích.
5. Chuyển sang đơn vị nhỏ nhất đích bằng phép chuyển đổi chính xác.

Phép chia tỷ giá có thể tạo số thập phân vô hạn; cần precision trung gian hoặc scale và chế độ làm tròn được thiết kế cho công thức đó. `BigDecimal.divide()` không có quy tắc làm tròn có thể ném lỗi khi kết quả không biểu diễn hữu hạn. Không bắt lỗi rồi tùy tiện giảm độ chính xác cho tới khi chạy được.

Precision tính trung gian phải đủ cho miền giá trị và sai số cho phép đã xác định. Không có một con số precision mặc định bảo đảm đúng mọi công thức nhiều bước.

### 9.3. Gắn báo giá với nội dung được thực thi

Một báo giá có thể cần lưu tiền tệ nguồn/đích, số tiền, hướng tỷ giá, phí, chế độ làm tròn, thời hạn và phiên bản chính sách. Backend phải xác minh báo giá thuộc đúng người hoặc ngữ cảnh nghiệp vụ.

Không cho client tự thay tỷ giá, thay mã tiền tệ hoặc đổi số tiền nguồn trong khi tái sử dụng quyết định duyệt cũ. Nếu chỉ lưu số tiền cuối mà không lưu hoặc tham chiếu được phép tính đã áp dụng, việc đối soát chênh lệch sau này sẽ khó khăn.

Việc đổi qua lại hai tiền tệ nhiều lần có thể làm lộ lỗi làm tròn hoặc quy tắc phí không nhất quán. Kiểm thử cần bao gồm chuỗi thao tác, không chỉ từng phép đổi đơn lẻ.

## 10. Giữ nguyên độ chính xác qua database và nhà cung cấp

### 10.1. Kiểu decimal có scale cố định có thể tự làm tròn

Trong PostgreSQL, cột `NUMERIC(18, 2)` giới hạn precision và scale, nhưng đầu vào có phần lẻ thừa có thể được làm tròn về scale trước khi lưu. Không coi việc chọn kiểu cột đó là bằng chứng đầu vào thừa phần lẻ đã bị từ chối.

Một `CHECK` trên giá trị đã lưu kiểu scale 2 không thể khôi phục các chữ số đã bị loại khi chuyển kiểu. Điều kiện dạng “giá trị bằng chính nó sau làm tròn hai chữ số” không phát hiện được `10.009` nếu nó đã trở thành `10.01` trước lúc kiểm tra.

Nếu yêu cầu phải từ chối phần lẻ, thực hiện validation trước chuyển đổi mất thông tin và kiểm soát các đường ghi khác. Với lớp database cần kiểm tra đầu vào nguyên gốc, phải chọn cấu trúc lưu hoặc thủ tục tiếp nhận còn giữ được giá trị để kiểm tra; không dựa vào một constraint đặt sau phép ép kiểu đã làm tròn.

### 10.2. Lưu số nguyên vẫn phải gắn đúng tiền tệ

Một thiết kế có thể lưu:

```text
tenant_id
movement_id
currency_code
unit_policy_version
amount_minor
```

`amount_minor` có thể dùng kiểu số nguyên phù hợp với miền giá trị. Cần constraint về dấu và phạm vi, khóa ngoại hoặc quan hệ đảm bảo tiền tệ phù hợp với tài khoản, cùng kiểm tra quyền theo đối tượng ở luồng nghiệp vụ.

JDBC cần bind theo kiểu chính xác, chẳng hạn `setLong` cho số nguyên hoặc `setBigDecimal` cho decimal. Không qua `setDouble` hoặc lớp mapping tự chuyển tiền sang dấu phẩy động.

Các batch job, import, script quản trị và webhook handler phải theo cùng đơn vị và quy tắc. Validation chỉ nằm ở controller không bảo vệ đường ghi bỏ qua controller.

### 10.3. Chuyển đổi qua adapter có hợp đồng riêng

Nhà cung cấp có thể nhận số nguyên, chuỗi thập phân hoặc quy ước đơn vị riêng. Adapter phải xác định rõ:

- Giá trị nội bộ đang dùng đơn vị nào.
- Trường API bên ngoài yêu cầu đơn vị nào.
- Có thể chuyển đổi chính xác hay cần quy tắc lượng tử hóa nào.
- Số tiền tối thiểu, tối đa và tiền tệ được hỗ trợ.

Không chỉ đổi tên `amount_minor` thành `amount` rồi gửi đi. Cần kiểm thử giá trị đã serialize thực tế, nhất là tiền tệ scale 0 hoặc scale 3, nơi giả định nhân chia 100 thường gây lỗi.

Khi nhận phản hồi hoặc webhook, so khớp số tiền và tiền tệ theo đơn vị được khai báo. Không lấy chuỗi hiển thị trên trình duyệt làm nguồn xác nhận thanh toán.

## 11. Chuẩn hóa, phê duyệt và idempotency phải dùng cùng giá trị

### 11.1. Một số tiền có nhiều biểu diễn

Theo chính sách chấp nhận số 0 thừa, các chuỗi `10`, `10.0` và `10.00` đều có thể cùng biểu diễn 1000 đơn vị nhỏ nhất của USD.

Nếu fingerprint nghiệp vụ tính trên JSON thô, các biểu diễn này cho kết quả khác nhau dù cùng tiền. Ngược lại, nếu chuẩn hóa bằng cách làm tròn cả `10.001` về `10.00`, hệ thống có thể che mất đầu vào không hợp lệ.

Thứ tự an toàn cho hợp đồng giá trị là:

```text
Kiểm tra schema và giới hạn tài nguyên
  -> xác minh tiền tệ và quy tắc đơn vị từ nguồn tin cậy
  -> kiểm tra số tiền biểu diễn chính xác
  -> tạo giá trị tiền chuẩn
  -> tính fingerprint nội dung nghiệp vụ
  -> kiểm tra idempotency và thực thi theo quyền
```

Đây không phải yêu cầu mọi hệ thống ký HTTP đều phải bỏ body gốc. Nếu có chữ ký trên bytes của request, vẫn xác minh chữ ký theo đúng giao thức trước khi xử lý. Fingerprint nghiệp vụ và chữ ký truyền tải có mục đích khác nhau.

### 11.2. Fingerprint phải chứa đủ ngữ cảnh

Ngoài số tiền chuẩn, cần có tenant, loại thao tác, tiền tệ, nguồn, đích và các tham chiếu ảnh hưởng ý nghĩa nghiệp vụ. `1000` USD không tương đương `1000` JPY, dù cùng một chuỗi số nguyên.

Cùng idempotency key nhưng nội dung nghiệp vụ khác phải bị từ chối theo hợp đồng. Việc đổi cách viết số không được tạo thêm hiệu lực hoặc bỏ qua kiểm tra quyền.

Nếu số tiền cần phê duyệt, gắn quyết định duyệt với giá trị chuẩn và phiên bản chính sách đã áp dụng. Không duyệt chuỗi ở UI rồi để backend thực thi một giá trị được tính lại bằng quy tắc khác.

### 11.3. Audit đủ để tái dựng phép tính

Với thao tác nhạy cảm, cần lưu hoặc tham chiếu được:

- Số tiền chuẩn, tiền tệ và định nghĩa đơn vị.
- Giá trị trung gian cần thiết để giải thích phí, phân bổ hoặc quy đổi.
- Chế độ và điểm làm tròn, phiên bản chính sách.
- Nội dung được duyệt và movement đã thực thi.
- Số tiền thực tế gửi/nhận với nhà cung cấp theo đơn vị của họ.

Không ghi bí mật hoặc toàn bộ payload thanh toán vô điều kiện. Mục tiêu là bằng chứng tính toán đủ dùng, có cấu trúc và có kiểm soát truy cập.

## 12. Kiểm thử theo tình huống tấn công logic

### 12.1. Ma trận đầu vào và ranh giới

| Nhóm tình huống | Ví dụ | Điều cần chứng minh |
|---|---|---|
| Biên phần lẻ | `0.001` với scale 2 | Bị từ chối, không làm tròn ngầm |
| Số 0 thừa | `10.000` | Theo đúng chính sách biểu diễn; không đổi ý nghĩa tiền |
| Tiền tệ khác scale | Scale 0, 2, 3 | Không hardcode nhân chia 100 |
| Dấu và giá trị 0 | `-1`, `0`, `-0.00` | Không vượt điều kiện số tiền dương của API chuyển tiền |
| Locale | `1,234`, `1.234,56` | Không được diễn giải mơ hồ trong API máy |
| Ký pháp số | `1e3`, `+10`, khoảng trắng | Theo schema rõ ràng, không có parser trước/sau hiểu khác nhau |
| Miền lớn | Vượt giới hạn `long`, tổng nhiều dòng lớn | Không tràn số hoặc cắt giá trị |
| Tài nguyên | Chuỗi rất dài, số mũ cực lớn | Bị chặn sớm theo giới hạn đầu vào |
| Nhầm tiền tệ | Đơn USD nhưng request ghi JPY | Bị từ chối dù số tiền nguyên hợp lệ |
| Nhầm đơn vị | Nội bộ minor, nhà cung cấp major | Giá trị serialize đúng, không chênh 10, 100 hoặc 1000 lần |

### 12.2. Kiểm thử chuỗi hành động và đồng thời

Các kịch bản cần đi xa hơn việc gọi riêng hàm parse:

1. Chia một giao dịch thành nhiều phần để tìm lợi ích từ phí hoặc làm tròn.
2. Thay số lượng, thứ tự dòng hoặc thứ tự người nhận để chiếm phần dư phân bổ.
3. Hoàn từng phần nhiều lần sao cho tổng các phần sau làm tròn vượt khoản đã thu.
4. Gửi hai yêu cầu hoàn đồng thời cùng tranh hạn mức còn lại.
5. Thay scale hoặc tiền tệ trong request sau khi có phê duyệt.
6. Gửi lại cùng idempotency key với các biểu diễn số tương đương hoặc nội dung thực sự khác.
7. Đổi tiền qua lại nhiều lượt để phát hiện cách làm tròn hoặc tính phí không nhất quán.
8. Ghi qua import, job nền và webhook để tìm đường bypass validation của API.

Với các trường hợp có tranh chấp dữ liệu, cần kiểm tra trạng thái cuối sau commit và dùng điểm đồng bộ để tạo cuộc đua có kiểm soát. Hàm số học chính xác không tự bảo vệ hạn mức khi hai transaction cùng ghi.

### 12.3. Những thuộc tính có thể kiểm tra

Ngoài ví dụ cụ thể, có thể sinh nhiều đầu vào trong miền được phép để kiểm tra:

```text
Đổi major -> minor -> major giữ nguyên giá trị số đã chấp nhận.

Tổng phần phân bổ = tổng ban đầu.

Tổng tiền đã hoàn + phần còn giữ hạn mức <= số được phép hoàn.

Cùng dữ liệu chuẩn và cùng chính sách -> cùng kết quả tính.

Thực thi một lần hay nhận lại cùng yêu cầu -> cùng hiệu lực tài chính.
```

Không yêu cầu phép quy đổi qua lại tiền tệ luôn trả đúng số ban đầu: phí, chênh lệch tỷ giá và làm tròn có thể làm giảm số tiền theo chính sách. Thuộc tính cần kiểm tra phải phản ánh mô hình nghiệp vụ, tránh đặt một điều kiện toán học không đúng với sản phẩm.

Sau kiểm thử, quan sát cả database, bút toán, số dư, audit và payload nhà cung cấp. Mã HTTP đúng chưa chứng minh tiền được giữ chính xác trên toàn bộ luồng.

## 13. Những quyết định phải được thống nhất

- Mỗi tiền tệ, sản phẩm và phương thức sử dụng đơn vị nào?
- Số tiền cuối nhận từ client sẽ bị từ chối hay được làm tròn khi thừa phần lẻ?
- Precision trung gian, điểm làm tròn và chế độ làm tròn do chính sách nào quyết định?
- Tổng, từng dòng, phí và phần dư phân bổ được giữ nhất quán thế nào?
- API, Java, database và nhà cung cấp có chuyển đổi qua kiểu hoặc đơn vị gây mất thông tin không?
- Phê duyệt, idempotency và audit có cùng tham chiếu một giá trị tiền chuẩn không?
- Hạn mức hoàn, số dư và tổng tiền được bảo vệ ra sao khi có nhiều request đồng thời?

Khi các quyết định này được mô hình hóa rõ, độ chính xác tiền trở thành một invariant có thể kiểm chứng. Mọi lớp xử lý cùng một giá trị tiền có ý nghĩa thống nhất, thay vì mỗi lớp tự diễn giải, làm tròn hoặc đổi đơn vị theo cách riêng.
