# Phân biệt chuỗi hiển thị với biểu diễn số để lưu trữ hoặc trao đổi trong Java

## Mục tiêu

Một giá trị số có thể được hiển thị theo nhiều ngôn ngữ và vùng mà **giá trị toán học không thay đổi**. Ví dụ, cùng một số mười hai nghìn ba trăm bốn mươi lăm phẩy sáu bảy tám có thể được trình bày là `12,345.678` hoặc `12.345,678`. Các chuỗi này phục vụ **người đọc**, không phải là định dạng dữ liệu ổn định để ghi cơ sở dữ liệu hoặc truyền giữa các hệ thống.

Bài học tập trung vào ranh giới giữa hai nhu cầu:

- **Hiển thị (presentation):** chọn dấu thập phân, dấu phân nhóm, chữ số, số chữ số thập phân, ký hiệu phần trăm/tiền tệ và quy tắc làm tròn theo `Locale`.
- **Lưu trữ hoặc trao đổi (storage / interchange):** giữ số dưới kiểu dữ liệu số hoặc một dạng văn bản có **ngữ pháp cố định**, độc lập với locale của máy/người dùng và có hợp đồng độ chính xác rõ ràng.

Sau bài, bạn có thể dùng `NumberFormat` và `DecimalFormat` đúng chỗ, lựa chọn `BigDecimal`/`toPlainString()` khi cần số thập phân chính xác, nhận diện rủi ro khi parse chuỗi đã định dạng, và thiết kế hợp đồng dữ liệu ổn định cho JSON, CSV hoặc cơ sở dữ liệu.

## 1. Một số, nhiều cách viết cho con người

Xét giá trị toán học `12345.6789`. Một chương trình có thể hiển thị gần đúng:

| Ngữ cảnh | Chuỗi minh họa | Ý nghĩa dấu phân cách |
| --- | --- | --- |
| Tiếng Anh (Hoa Kỳ), 3 chữ số thập phân | `12,345.679` | `,` phân nhóm; `.` là dấu thập phân |
| Tiếng Đức (Đức), 3 chữ số thập phân | `12.345,679` | `.` phân nhóm; `,` là dấu thập phân |
| Biểu diễn thập phân ASCII không nhóm | `12345.6789` | `.` là dấu thập phân theo hợp đồng dữ liệu |

Hai chuỗi hiển thị trong bảng đã **làm tròn** đến ba chữ số sau dấu thập phân: chúng không còn đủ thông tin để tái tạo chính xác `12345.6789`. Còn chuỗi cuối biểu diễn đầy đủ những chữ số ban đầu mà ví dụ yêu cầu giữ lại.

Thực tế, kết quả hiển thị có thể còn khác về ký hiệu nhóm (khoảng trắng thường, khoảng trắng không ngắt, khoảng trắng hẹp không ngắt), bộ chữ số, ký hiệu âm và quy ước tiền tệ. Đó là lý do một chương trình không nên định nghĩa format dữ liệu bằng câu “lưu đúng chuỗi mà người dùng đang thấy trên màn hình”.

**Phân biệt ba thực thể:**

1. **Giá trị số:** ví dụ đối tượng `BigDecimal("12345.6789")`.
2. **Chuỗi hiển thị:** kết quả `NumberFormat.format(value)` cho một locale cụ thể.
3. **Biểu diễn trao đổi:** ví dụ trường số theo ngữ pháp JSON hoặc chuỗi decimal có dấu `.`, không có grouping, kèm tài liệu schema.

Chuỗi hiển thị và biểu diễn trao đổi đều là text, nhưng **không có cùng hợp đồng**. Sự khác biệt nằm ở đối tượng đọc và khả năng parse ổn định, không nằm ở việc chúng cùng có kiểu Java `String`.

## 2. NumberFormat dành cho tầng trình bày

`java.text.NumberFormat` cung cấp các formatter dựa trên `Locale`:

```java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat number = NumberFormat.getNumberInstance(Locale.GERMANY);
NumberFormat percent = NumberFormat.getPercentInstance(Locale.GERMANY);
NumberFormat currency = NumberFormat.getCurrencyInstance(Locale.GERMANY);
```

Đây là đoạn minh họa trong một phương thức. Các formatter thực hiện những vai trò khác nhau:

- `getNumberInstance(locale)`: biểu diễn số thập phân theo quy ước của locale.
- `getIntegerInstance(locale)`: định dạng kiểu số nguyên theo quy ước locale.
- `getPercentInstance(locale)`: định dạng tỷ lệ phần trăm; một giá trị `0.25` có thể hiển thị thành 25%.
- `getCurrencyInstance(locale)`: định dạng theo quy ước tiền tệ mặc định gắn với locale, nếu có dữ liệu phù hợp.

Các formatter có thể tác động đến dấu nhóm, dấu thập phân, chữ số, kiểu dấu âm, số chữ số thập phân và **làm tròn**. Đó là hành vi mong muốn ở giao diện, nhưng là nguồn nguy hiểm nếu lấy kết quả để lưu như dữ liệu gốc.

Ví dụ:

```java
BigDecimal amount = new BigDecimal("12345.6789");
NumberFormat german = NumberFormat.getNumberInstance(Locale.GERMANY);
german.setMaximumFractionDigits(3);
String display = german.format(amount);
```

Đây là đoạn minh họa trong một phương thức, có `import java.math.BigDecimal;` và `import java.util.Locale;`. Chuỗi `display` được tạo để **đọc** theo locale Đức, chứ không phải giao thức nội bộ để một dịch vụ khác parse bằng mặc định của nó.

### Không dùng Locale mặc định một cách vô thức

Hai lệnh:

```java
NumberFormat.getNumberInstance()
NumberFormat.getNumberInstance(Locale.GERMANY)
```

không tương đương về tính ổn định. Lệnh đầu sử dụng mặc định phù hợp với việc định dạng của JVM (category `FORMAT`); cấu hình có thể khác giữa máy phát triển, CI và production. Lệnh thứ hai nêu rõ locale.

Trong ứng dụng phục vụ nhiều người dùng, hãy lấy locale từ ngữ cảnh của request và **truyền tường minh**. Đừng đổi `Locale.setDefault(...)` cho từng người dùng: default là trạng thái chung cấp JVM, có thể làm các request khác thay đổi kết quả.

## 3. Định dạng số không phải quá trình bảo toàn giá trị

Một số hệ thống chỉ muốn hiển thị tối đa hai chữ số thập phân. Khi formatter làm tròn:

```text
Giá trị:        12345.6789
Hiển thị 2 số:  12,345.68      (minh họa theo en-US)
```

Thông tin `89` ở phần cuối đã mất trong chuỗi hiển thị. Nếu parse `12,345.68`, bạn nhận số đại diện cho **giá trị đã được làm tròn**, không thể khôi phục chính xác số ban đầu.

Không chỉ làm tròn gây mất dữ liệu:

- Định dạng phần trăm nhân giá trị với 100 và thêm ký hiệu %, ví dụ `0.25` ↔ `25%`. Parse bằng formatter không cùng kiểu có thể hiểu sai 100 lần.
- Định dạng tiền tệ có thể làm tròn theo số chữ số thập phân mặc định của đơn vị tiền.
- Một formatter có thể bỏ các số 0 thập phân không cần hiển thị, làm mất thông tin về **scale** trong `BigDecimal`.
- Chuỗi có thể dùng chữ số hoặc dấu nhóm khác ASCII theo locale.
- Hai con số khác nhau có thể cùng một kết quả nếu được làm tròn đến độ chính xác thấp.

Vì vậy, **không nên dùng `format` rồi `parse` như một cách lưu trữ trung gian**. Định dạng dùng để làm thông điệp dễ đọc; dữ liệu gốc phải được giữ riêng.

### Trường hợp tiền tệ

Cặp thông tin `amount` và `currency` là dữ liệu nghiệp vụ. Locale có thể quyết định **cách hiển thị**, nhưng không phải lúc nào cũng quyết định **đồng tiền của giao dịch**. Một người chọn giao diện tiếng Việt có thể thanh toán bằng USD hoặc EUR.

Đừng chỉ lưu `"$1,234.50"`: ký hiệu `$` có thể ứng với các đồng tiền khác nhau, dấu nhóm và dấu thập phân phụ thuộc ngữ cảnh, còn số chữ số thập phân khi hiển thị không nói toàn bộ quy tắc tính tiền. Nên lưu **giá trị số chính xác + mã ISO 4217 của đồng tiền**, và áp dụng quy tắc làm tròn nghiệp vụ một cách tường minh.

## 4. Định dạng ổn định phải có ngữ pháp rõ ràng

Đối với trường trao đổi dữ liệu số, hợp đồng thường cần quy định:

- **Loại dữ liệu:** số nguyên hay thập phân, có âm hay không, có hỗ trợ ký pháp mũ không.
- **Bộ ký tự:** chữ số ASCII `0–9`, dấu âm `-`, dấu thập phân `.`, không sử dụng dấu phân nhóm.
- **Scale/precision/range:** giới hạn chữ số, giới hạn giá trị, có giữ số 0 cuối phần thập phân hay không.
- **Ý nghĩa đơn vị:** ví dụ tổng tiền với mã tiền riêng, trọng lượng tính bằng kilogram, tỷ lệ `0.25` hay phần trăm `25`.
- **Cách biểu diễn giá trị vắng mặt:** `null` theo schema hay trường không tồn tại; không tự ghi ký tự `"null"` như một số.
- **Quy tắc parse và báo lỗi:** đầu vào sai phải bị từ chối, không đoán theo locale hệ thống.

Một cách biểu diễn decimal theo hợp đồng đơn giản:

```text
-12345.6789
0
0.125
1000
```

Chúng **không có dấu phân nhóm**; dấu thập phân luôn là `.`. Ví dụ này minh họa một profile trao đổi với số thập phân dạng text, không tuyên bố rằng nó là format duy nhất cho mọi giao thức.

JSON cho phép number theo ngữ pháp cố định (dấu thập phân `.`, có thể có ký pháp mũ); JSON **không chấp nhận** group separator theo locale, và cũng không chấp nhận `NaN` hay `Infinity` dưới dạng số. Một schema cụ thể có thể chọn JSON number hoặc JSON string chứa decimal chuẩn. Chúng khác nhau về kiểu dữ liệu và tương thích giữa những client.

### JSON number so với chuỗi decimal chính xác

Hai ví dụ sau mang hợp đồng khác nhau:

```json
{"quantity": 12345.6789}
```

```json
{"amount": "12345.6789", "currency": "EUR"}
```

Ở ví dụ thứ nhất, `quantity` là **JSON number**. JSON syntax không tự đảm bảo rằng mọi client giữ được đầy đủ độ chính xác của số, vì một số client đọc mọi JSON number bằng IEEE 754 binary64. Ở ví dụ thứ hai, `amount` là **JSON string** theo schema quy định một chuỗi thập phân chuẩn; client cần parse vào kiểu decimal phù hợp, không đối xử tùy tiện như một chuỗi giao diện.

Không thể nói “mọi số cần gửi dưới dạng String” hoặc “mọi số luôn gửi dưới dạng JSON number”. Quyết định dựa trên ngữ nghĩa, phạm vi giá trị, độ chính xác và khả năng của bên gửi/bên nhận. Với tiền hoặc số thập phân đòi độ chính xác tuyệt đối, một số API chọn decimal string kèm currency; API khác dùng integer số đơn vị nhỏ nhất (ví dụ cents) và ghi rõ đơn vị. Cả hai đều hợp lệ khi **hợp đồng chính xác và không mơ hồ**.

## 5. BigDecimal và toPlainString cho dữ liệu thập phân

`java.math.BigDecimal` lưu số thập phân dưới dạng giá trị có độ chính xác do số chữ số và scale quyết định, rất hữu ích cho tiền tệ, định lượng và dữ liệu cần decimal chính xác.

Khởi tạo từ chuỗi decimal đã được xác thực:

```java
import java.math.BigDecimal;

BigDecimal value = new BigDecimal("12345.6789");
String wire = value.toPlainString();
System.out.println(wire);
```

Đây là đoạn minh họa trong phương thức. Stdout:

```text
12345.6789
```

`toPlainString()` biểu diễn số theo dạng thông thường không dùng ký pháp mũ, với dấu thập phân ASCII `.`, không thêm grouping theo locale. Nó phù hợp làm **một phần** của hợp đồng trao đổi decimal dạng chuỗi nếu phía nhận chấp nhận đúng ngữ pháp và các giới hạn được công bố.

Lưu ý:

1. `toPlainString()` **không tự kiểm tra** giới hạn độ dài, số chữ số, thang đo hay dải số của ứng dụng.
2. Các số có scale khác nhau nhưng giá trị toán học bằng nhau có thể có chuỗi khác, ví dụ `"1.0"` và `"1.00"`. Hãy quyết định việc bảo toàn scale theo nghiệp vụ.
3. `BigDecimal.toString()` cũng là biểu diễn có định nghĩa rõ, nhưng có thể dùng ký pháp mũ; `toPlainString()` là lựa chọn khi schema không muốn dùng mũ.
4. Một đối tượng `BigDecimal` có thể có scale âm; quá trình chuyển đổi giữa các dạng cần được hiểu đúng, nhất là nếu client coi việc giữ nguyên biểu diễn gốc là bắt buộc.
5. `BigDecimal` không thay thế việc xác định currency, đơn vị và quy tắc rounding.

### Tránh dựng BigDecimal trực tiếp từ double nếu cần chính xác decimal

`double` dùng biểu diễn nhị phân, không thể biểu diễn chính xác nhiều phân số thập phân quen thuộc như `0.1`. So sánh:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = BigDecimal.valueOf(0.1);
BigDecimal c = new BigDecimal(0.1);

System.out.println(a.toPlainString());
System.out.println(b.toPlainString());
System.out.println(c.toPlainString());
```

Trong phương thức có import `BigDecimal`, kết quả:

```text
0.1
0.1
0.1000000000000000055511151231257827021181583404541015625
```

`new BigDecimal("0.1")` bảo toàn chuỗi decimal đã nhập; `BigDecimal.valueOf(0.1)` dùng biểu diễn thập phân qua `Double.toString` của giá trị `double`; còn `new BigDecimal(0.1)` thể hiện giá trị nhị phân double một cách chính xác nên xuất ra phần đuôi dài.

Điều này không có nghĩa mọi nơi bắt buộc phải dùng `BigDecimal`. Với đo đạc/đồ họa/thống kê chấp nhận sai số floating-point, `double` có thể hợp lý. Điều quan trọng là **không dùng chuỗi hiển thị do locale định dạng để bù lại sai số hoặc chọn kiểu số sai nhu cầu**.

### equals, compareTo và scale

Hai đối tượng:

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");
```

thỏa `x.compareTo(y) == 0` nhưng `x.equals(y)` là `false` vì `equals` xét cả giá trị và scale. Khi trao đổi decimal string, phải quyết định có cần giữ thông tin biểu diễn scale hay chỉ cần so sánh giá trị số.

Đừng tự gọi `stripTrailingZeros()` cho mọi khoản tiền nếu số chữ số sau thập phân có ý nghĩa với hợp đồng sản phẩm. Ngược lại, nếu schema yêu cầu canonical representation không giữ trailing zeros, cần ghi rõ bước chuẩn hóa và test nó.

## 6. Ví dụ Java 17+ chạy độc lập: cùng một số, hai lớp biểu diễn

Tạo tệp `NumberDisplayVsWire.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class NumberDisplayVsWire {

    private static DecimalFormat formatter(Locale locale) {
        DecimalFormat format =
                (DecimalFormat) NumberFormat.getNumberInstance(locale);
        format.setGroupingUsed(true);
        format.setMaximumFractionDigits(3);
        format.setRoundingMode(RoundingMode.HALF_UP);
        return format;
    }

    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("12345.6789");

        DecimalFormat german = formatter(Locale.GERMANY);
        DecimalFormat american = formatter(Locale.US);

        String deDisplay = german.format(value);
        String usDisplay = american.format(value);
        String wire = value.toPlainString();

        System.out.println("de display: " + deDisplay);
        System.out.println("us display: " + usDisplay);
        System.out.println("wire: " + wire);

        german.setParseBigDecimal(true);
        ParsePosition position = new ParsePosition(0);
        Number parsed = german.parse(deDisplay, position);

        System.out.println("parsed: " + parsed);
        System.out.println("all consumed: "
                + (parsed != null
                && position.getIndex() == deDisplay.length()));
        System.out.println("original preserved: "
                + (parsed instanceof BigDecimal
                && value.compareTo((BigDecimal) parsed) == 0));

        ParsePosition suffixPos = new ParsePosition(0);
        Number withSuffix = german.parse(deDisplay + "abc", suffixPos);
        System.out.println("suffix rejected as full input: "
                + (withSuffix == null
                || suffixPos.getIndex() != (deDisplay + "abc").length()));

        try {
            new BigDecimal(deDisplay);
            System.out.println("unexpected decimal accepted");
        } catch (NumberFormatException ex) {
            System.out.println("localized string is not wire decimal");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 NumberDisplayVsWire.java
java NumberDisplayVsWire
```

Stdout với các `Locale` và formatter đã nêu:

```text
de display: 12.345,679
us display: 12,345.679
wire: 12345.6789
parsed: 12345.679
all consumed: true
original preserved: false
suffix rejected as full input: true
localized string is not wire decimal
```

Giải thích:

- Hai dòng đầu hiển thị cùng `BigDecimal` theo dấu phân cách của Đức và Hoa Kỳ. Formatter giới hạn 3 chữ số sau thập phân và dùng `HALF_UP` nên `12345.6789` thành `...679`.
- Dòng `wire` dùng `toPlainString()` để giữ đủ phần thập phân mà đối tượng `BigDecimal` đang có.
- `setParseBigDecimal(true)` giúp `DecimalFormat` nhận lại một `BigDecimal` thay vì mặc nhiên trả `Number` kiểu `Long`/`Double` tùy nội dung.
- `all consumed: true` chỉ nói chuỗi hiển thị đã được parser xử lý hết. `original preserved: false` cho thấy **ngay cả parse đủ chuỗi cũng không thể đảo bước làm tròn**.
- Khi thêm `abc` vào cuối, parser có thể parse thành công **phần đầu** nhưng chưa ăn hết input; kiểm tra index phát hiện phần dư.
- `new BigDecimal(deDisplay)` từ chối ký tự phân nhóm và dấu thập phân theo tiếng Đức. `BigDecimal(String)` không phải bộ phân tích chuỗi số hiển thị theo locale.

Ví dụ được cố ý tách biến `deDisplay`, `usDisplay` và `wire`: chúng biểu diễn ba **vai trò** khác nhau của text. Đừng đặt một biến `numberString` rồi dùng nó lẫn lộn cho UI và cho database/API.

## 7. Chuyển ngược từ người dùng nhập: parse phải theo đúng hợp đồng input

Một ứng dụng có thể **cần chấp nhận dữ liệu số người dùng nhập theo locale**. Khi đó việc parse là hợp lý, nhưng đầu vào cần có ngữ cảnh cụ thể.

Ví dụ ô nhập của người dùng chọn `Locale.GERMANY` có thể chấp nhận:

```text
12.345,67
```

trong khi cùng giá trị khi hiển thị theo `Locale.US` có thể là:

```text
12,345.67
```

Đưa cả hai vào `Double.parseDouble(...)` hoặc `new BigDecimal(...)` không phải cách giải quyết giao diện đa ngôn ngữ. Hai API trên không hiểu tùy tiện mọi dấu thập phân/phân nhóm của locale.

Với parser được tạo riêng:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

static BigDecimal parseUserDecimal(String raw, Locale locale) {
    if (raw == null || raw.isEmpty()) {
        throw new IllegalArgumentException("A number is required");
    }

    DecimalFormat format =
            (DecimalFormat) NumberFormat.getNumberInstance(locale);
    format.setParseBigDecimal(true);

    ParsePosition position = new ParsePosition(0);
    Number parsed = format.parse(raw, position);

    if (!(parsed instanceof BigDecimal)
            || position.getIndex() != raw.length()) {
        throw new IllegalArgumentException("Invalid localized number");
    }

    return (BigDecimal) parsed;
}
```

Đây là **phương thức minh họa**, đặt bên trong một lớp Java. Nó kiểm tra đã đọc hết input; đây là bước cần thiết nhưng **chưa đủ để coi input hợp lệ tuyệt đối cho mọi nghiệp vụ**.

### Parser dạng hiển thị có thể chấp nhận cú pháp lỏng

Một điểm dễ bỏ sót: `NumberFormat`/`DecimalFormat` không được thiết kế để thay thế mọi bộ kiểm tra ngữ pháp nghiêm ngặt. Tùy locale, pattern và tùy chọn, parser có thể chấp nhận dấu nhóm không đúng quy cách. Ngay cả khi `ParsePosition.getIndex() == raw.length()`, **định dạng nhập vào vẫn có thể sai yêu cầu riêng của ứng dụng**.

Ví dụ, với formatter Đức quen thuộc, một chuỗi có nhóm chữ số bất thường như `1.23.45,678` có thể vẫn được parser chấp nhận thành một giá trị. Do đó:

1. Xác định input cho phép dấu nhóm hay không.
2. Nếu có, định nghĩa rõ nhóm đúng gồm bao nhiêu chữ số và những loại khoảng trắng nào hợp lệ.
3. Dùng validation theo schema hoặc parser phù hợp để từ chối cú pháp không mong muốn, không chỉ dựa vào việc formatter trả `Number`.
4. Kiểm tra range, scale, đơn vị và tính hợp lệ nghiệp vụ **sau** khi parse.
5. Giữ `Locale` được chọn cho input rõ ràng; đừng đoán locale từ một dấu phẩy vì chuỗi `1,234` có thể mang nhiều nghĩa.

Không nên tự động thay mọi dấu phẩy bằng dấu chấm rồi parse: `1,234` có thể là một nghìn hai trăm ba mươi bốn trong en-US hoặc một phẩy hai ba bốn trong một số quy ước khác. Thao tác thay dấu vô điều kiện có thể khiến người dùng thanh toán sai hàng nghìn lần.

### Phân biệt input của con người và input của máy

Có thể thiết kế hai endpoint/mạch xử lý khác nhau:

- **Form UI:** nhận chuỗi theo locale đã xác định, parse và validate rồi tạo `BigDecimal`.
- **REST/CSV import từ hệ thống khác:** nhận biểu diễn theo schema cố định; parse mà không cần locale, hoặc parse JSON number thành kiểu dữ liệu đã thỏa thuận.

Đừng tái sử dụng parser cho màn hình ở tầng network chỉ vì “nó đã xử lý được dấu phẩy”. Cấu hình locale ở hệ thống gửi có thể thay đổi ngoài dự kiến; format trao đổi nên luôn có quy tắc được ghi tài liệu và kiểm thử liên hệ thống.

## 8. JSON, CSV và cơ sở dữ liệu: ví dụ chọn biểu diễn đúng

### JSON API

Nếu API đòi số thập phân chính xác, một lựa chọn phổ biến:

```json
{
  "amount": "12345.6789",
  "currency": "EUR"
}
```

Trong hợp đồng này, `amount` **là chuỗi decimal theo ngữ pháp đã quy định**, không phải “text bất kỳ để hiển thị”. Bên nhận có thể dựng `new BigDecimal(amount)` sau khi kiểm tra length, ký tự, scale, giới hạn và giá trị. Nếu dùng JSON number thay thế, phải biết serializer/parser của hai bên có bảo toàn precision mong muốn hay không.

Nếu dữ liệu là số lượng nguyên đếm được, `{"quantity": 12345}` dạng JSON number có thể tiện và rõ hơn. Nhưng ngay cả số nguyên cũng cần xét giới hạn kiểu và khả năng chính xác của client, đặc biệt với số lớn vượt phạm vi integer an toàn trong JavaScript.

### CSV

CSV chủ yếu là **định dạng bảng văn bản**, không tự đảm bảo kiểu decimal. Một cột trao đổi chuẩn có thể dùng:

```csv
order_id,amount,currency
A-100,12345.6789,EUR
A-101,-10.25,USD
```

Hãy định nghĩa rõ rằng `amount` dùng chữ số ASCII, dấu `.` cho thập phân, không có dấu grouping; `currency` có mã ISO. Nếu xuất CSV nhằm **mở bằng spreadsheet cho người dùng đọc**, việc hiển thị theo locale hoặc quy tắc import spreadsheet là một bài toán khác. Đừng tuyên bố mọi CSV “đã locale-neutral” nếu không có schema.

Đặc biệt, khi locale dùng dấu phẩy làm thập phân, một chuỗi như `12,34` có thể bị đọc thành **hai cột** trong CSV dùng dấu phẩy phân cách nếu chưa được quote. Ngay cả khi được quote, hệ thống nhập dữ liệu vẫn cần biết `12,34` là một decimal của locale nào. Cách dễ tương tác hơn giữa máy là thống nhất dấu thập phân và delimiter theo hợp đồng.

### SQL / JDBC

Trong database, ưu tiên cột **NUMERIC/DECIMAL** cho số thập phân cần chính xác thay vì lưu văn bản đã định dạng:

```java
BigDecimal price = new BigDecimal("12345.6789");
preparedStatement.setBigDecimal(1, price);
```

Đây là đoạn minh họa trong phương thức có `PreparedStatement preparedStatement` hợp lệ. Cần lựa chọn precision/scale của cột theo nghiệp vụ, xử lý trường hợp số không vừa cột và lưu currency/unit nếu cần.

JDBC hỗ trợ truyền giá trị kiểu `BigDecimal` đến driver; không phải ghép SQL như:

```java
// Không nên:
String sql = "INSERT INTO sales (amount) VALUES ('"
        + numberFormat.format(price) + "')";
```

Đoạn trên chỉ để minh họa **anti-pattern** (giả định có `numberFormat` và `price`). Ngoài lỗi định dạng theo locale và kiểu dữ liệu, nối chuỗi để dựng SQL còn tạo nguy cơ bảo mật nếu lấy thêm input từ bên ngoài. Hãy dùng prepared statement và tham số đúng kiểu.

### Không coi mọi số là tiền

Ngay cả khi schema dùng `BigDecimal`, đơn vị vẫn quan trọng: `0.25` là 25% hay 0.25%? `100` là 100 kg hay 100 g? Một format ổn định không thể tự mang ý nghĩa đơn vị nếu hợp đồng không nói rõ. Hãy đặt tên trường rõ ràng, có đơn vị hoặc metadata cần thiết, rồi mới định dạng cho người dùng.

## 9. Precision, scale, rounding và giá trị đặc biệt

### Kiểm soát làm tròn ở nghiệp vụ, không giao cho UI quyết định

Nếu cần thanh toán đến hai chữ số thập phân, quyết định **khi nào và cách nào** làm tròn thuộc nghiệp vụ, không phải hành vi phụ của một formatter trên màn hình.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal calculated = new BigDecimal("10.005");
BigDecimal charged = calculated.setScale(2, RoundingMode.HALF_UP);
```

Đây là đoạn minh họa trong một phương thức; `charged.toPlainString()` là `10.01`. `RoundingMode.HALF_UP` chỉ là một **quy tắc minh họa**; một sản phẩm có thể yêu cầu quy tắc khác theo pháp luật, loại tiền hoặc hợp đồng.

Đừng định dạng `calculated` thành `10.01` rồi parse trở lại để “làm tròn”. Hãy xử lý số bằng các API số học và quy tắc nghiệp vụ, sau đó mới format để hiển thị.

### double, NaN và Infinity

`double` có thể chứa `NaN`, `Double.POSITIVE_INFINITY` hoặc `Double.NEGATIVE_INFINITY`. Đó không phải các JSON number hợp lệ. Khi tuần tự hóa, serializer phải theo schema (thường từ chối hoặc có quy tắc riêng), không tự nghĩ rằng vì `Double.toString` tạo ra chữ `NaN` thì JSON chấp nhận nó như một số.

Với dữ liệu decimal chính xác, `BigDecimal` không biểu diễn những giá trị đặc biệt này. Khi nhận dữ liệu floating-point, hãy kiểm tra `Double.isFinite(value)` nếu chỉ cho phép số hữu hạn.

### Âm không, số 0 cuối và dạng khoa học

- Với `double`, `-0.0` và `0.0` có hành vi số học/bit khác nhau ở một số ngữ cảnh; chuỗi định dạng có thể làm mất dấu âm.
- Với `BigDecimal`, `1.0` và `1.00` bằng nhau về số nhưng có scale khác nhau; `toPlainString()` thể hiện scale tương ứng.
- `BigDecimal.toString()` có thể dùng ký pháp khoa học khi cần; `toPlainString()` không dùng ký pháp khoa học. Cả hai không tự thay thế hợp đồng phạm vi/độ dài.
- Không nên “canonical hóa” dữ liệu bằng việc xóa dấu, khoảng trắng hoặc số 0 tùy ý trước khi đã xác định ý nghĩa và giới hạn nhận.

Điểm quan trọng là **chính sách nghiệp vụ và schema trao đổi phải được định nghĩa riêng khỏi sở thích hiển thị của locale**.

## 10. Quy trình thiết kế một luồng dữ liệu số đúng

Một sơ đồ tư duy thực tế:

```text
     Người dùng nhập (có Locale)
                 |
       Parse + validate input
                 |
         BigDecimal / Number
                 |
       Nghiệp vụ + rounding
          /               \
         v                 v
  Formatter theo Locale   Serializer theo schema
         |                 |
         v                 v
   Chuỗi hiển thị       Số/decimal chuẩn
     cho người          để lưu/trao đổi
```

Tương tự, dữ liệu nhận từ API phải được parse theo schema **trước khi** đưa vào formatter hiển thị:

```text
API / database -> parse theo schema -> giá trị số -> NumberFormat(locale) -> UI
```

Đừng nối hai mạch trực tiếp bằng `UI String -> lưu DB` hoặc `API decimal -> hiển thị raw` nếu sản phẩm có yêu cầu bản địa hóa.

### Checklist triển khai

1. **Tách biến:** `amount` là `BigDecimal`; `displayText` là String cho UI; `wireAmount` là String theo schema trao đổi.
2. **Truyền locale rõ ràng** cho formatter và parser nhận dữ liệu người dùng.
3. **Không trích số bằng cách bỏ dấu phẩy/dấu chấm** khỏi chuỗi bất kỳ.
4. **Định nghĩa input grammar** cho API/CSV; không dựa vào `Locale.getDefault()`.
5. **Kiểm soát precision/scale/range** của số sau parse; reject thay vì âm thầm làm tròn nếu hợp đồng yêu cầu.
6. **Chọn kiểu serialization phù hợp**: JSON number, decimal string hoặc integer smallest unit, và tài liệu hóa đơn vị.
7. **Dùng prepared statement** truyền giá trị kiểu số cho database.
8. **Định dạng lần cuối** khi sắp hiển thị; không dùng kết quả đã format làm dữ liệu nguồn.
9. **Xử lý NaN/Infinity** nếu dùng floating-point và schema không cho phép.
10. **Test đa locale, đa môi trường** cùng các ca biên (số lớn, số âm, 0, số lẻ, nhóm chữ số, nhập sai, trailing zeros).

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách phù hợp |
| --- | --- | --- |
| Lưu `numberFormat.format(amount)` vào database | Chuỗi phụ thuộc locale và có thể đã được làm tròn | Lưu cột số hoặc decimal chuẩn |
| Dùng `Double.parseDouble("12,34")` | API không hiểu dấu thập phân của mọi locale | Parse input theo locale đã biết hoặc yêu cầu input grammar chuẩn |
| Thay tất cả `,` thành `.` để chuẩn hóa | `1,234` có thể là nhóm hàng nghìn hoặc phần thập phân | Xác định locale/schema trước |
| Xóa mọi dấu `.` và `,` rồi parse | Có thể tăng/giảm giá trị hàng nghìn lần | Dùng parser và validation chính thức |
| Giả định `NumberFormat.parse` đọc hết input | Parser có thể chấp nhận prefix hợp lệ rồi bỏ phần dư | Kiểm tra `ParsePosition.getIndex()` |
| Giả định parse hết input đồng nghĩa cú pháp grouping đúng | Một số parser chấp nhận grouping lỏng | Thêm kiểm tra grammar nghiệp vụ |
| Giả định `parse(format(x)) == x` | Formatter có thể làm tròn và thay scale | Giữ giá trị gốc; format chỉ để hiển thị |
| `new BigDecimal(0.1)` để nhập decimal `0.1` | Lấy đúng giá trị binary64, có phần đuôi | Khởi tạo từ chuỗi đã xác thực hoặc cân nhắc `valueOf` |
| Dùng currency formatter để xác định tiền giao dịch | Locale không quyết định đồng tiền nghiệp vụ | Lưu mã currency riêng |
| Dùng `NumberFormat.getInstance()` không truyền locale trong API | Output có thể thay theo môi trường JVM | Chọn schema cố định, locale chỉ ở UI |
| Coi JSON number luôn giữ mọi chữ số | Client có thể parse về double và mất precision | Xác định kiểu và giới hạn, dùng decimal string khi cần |
| Đưa `NaN`/`Infinity` vào JSON number | Không hợp lệ theo JSON number grammar | Validate finite hoặc định nghĩa biểu diễn riêng |
| Ghép SQL từ chuỗi đã format | Sai dấu phân cách/kiểu và tăng nguy cơ injection | `PreparedStatement#setBigDecimal` |
| Dùng String để tính toán số học | Tính toán và so sánh sai ngữ nghĩa số | Parse vào kiểu số, xử lý số học rồi serialize |

## 12. Bài tập tự kiểm tra

**Bài 1 — hai định dạng hiển thị:** Với giá trị `12345.6789` và yêu cầu tối đa 3 số thập phân, hãy viết hai lệnh `NumberFormat` có locale `US` và `GERMANY`. Vì sao hai chuỗi khác nhau nhưng `BigDecimal` gốc không đổi? Dữ liệu nào bị mất khi format?

**Bài 2 — con số mơ hồ:** Một form gửi `"1,234"`. Hãy nêu ít nhất hai cách hiểu nếu không biết locale và giải thích vì sao thao tác `replace(",", ".")` không an toàn.

**Bài 3 — số chính xác:** Tại sao `new BigDecimal("0.1")` khác `new BigDecimal(0.1)`? Khi nào `BigDecimal.valueOf(0.1)` cho chuỗi ngắn hơn? Điều này nói gì về việc đưa số thập phân qua kiểu `double`?

**Bài 4 — round-trip:** Dùng `DecimalFormat` để hiển thị `new BigDecimal("9.9999")` với hai chữ số thập phân. Nếu parse lại chuỗi, tại sao số gốc không thể khôi phục chắc chắn?

**Bài 5 — API tiền:** Thiết kế schema tối thiểu cho một khoản tiền bằng EUR cần giá trị decimal chính xác. Hãy chọn JSON number hay decimal string, thêm mã currency, và mô tả giới hạn scale/range cùng quy tắc rounding của hợp đồng.

**Bài 6 — parse chặt:** Với `"12.345,678abc"` và `Locale.GERMANY`, vì sao parser có thể trả giá trị và vẫn là đầu vào không hợp lệ? Hãy dùng `ParsePosition` để kiểm tra đã đọc hết chuỗi.

**Bài 7 — lưu trữ:** So sánh cột SQL `VARCHAR("12.345,67")` với `DECIMAL(18,2)` có giá trị số tương ứng. Điều gì xảy ra nếu ứng dụng đổi ngôn ngữ giao diện sang en-US? Vì sao thay đổi locale không nên đổi dữ liệu số đã lưu?

## 13. Kết luận

**Chuỗi hiển thị** là sản phẩm của `Locale` và chính sách trình bày: dễ đọc đối với con người, có thể chứa dấu phân nhóm, ký hiệu tiền tệ hoặc chữ số khác ASCII và có thể đã bị làm tròn. **Biểu diễn để lưu trữ/trao đổi** phải có kiểu số hoặc ngữ pháp văn bản cố định, precision/scale, range và đơn vị được xác định theo schema — không phụ thuộc ngôn ngữ hay locale mặc định.

Trong Java, hãy dùng `NumberFormat`/`DecimalFormat` ở tầng giao diện; dùng `BigDecimal` cho decimal cần chính xác; cân nhắc `toPlainString()` khi cần chuỗi thập phân chuẩn không mũ theo hợp đồng; dùng JDBC tham số đúng kiểu và serializer JSON phù hợp. Khi nhận văn bản từ người dùng, parse theo locale đã biết và kiểm tra nghiêm ngặt; khi nhận từ hệ thống khác, parse theo **schema trao đổi đã thống nhất**.

Nguyên tắc ngắn gọn: **Giữ giá trị số làm nguồn sự thật. Format khi hiển thị, serialize khi trao đổi — không tráo đổi hai nhiệm vụ.**

### Tài liệu API tham khảo

- [`NumberFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [`DecimalFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html)
- [`BigDecimal` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [`ParsePosition` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html)
