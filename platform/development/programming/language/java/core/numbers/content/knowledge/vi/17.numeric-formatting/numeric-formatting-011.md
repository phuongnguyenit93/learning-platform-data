# ParsePosition và kiểm tra toàn bộ chuỗi khi parse theo locale trong Java

## 1. Mục tiêu: parse được một tiền tố chưa chắc dữ liệu hợp lệ

Khi nhận một chuỗi số theo quy ước vùng miền (locale), `NumberFormat` hoặc `DecimalFormat` có thể **đọc thành công một phần đầu chuỗi rồi dừng lại**. Một kết quả kiểu `Number` khác `null` **không đảm bảo toàn bộ chuỗi đầu vào đã được tiêu thụ**.

Ví dụ với quy ước Đức, dấu chấm phân cách hàng nghìn và dấu phẩy là dấu thập phân:

~~~text
Đầu vào:   "1.234,56 kg"
            └──────┘└─┘
              Số     Phần còn dư

Kết quả số: 1234.56
Đã đọc:      8 ký tự trên tổng 11 ký tự
~~~

Nếu phần mềm nhận trường dữ liệu “chỉ được chứa một số”, việc chấp nhận `1234.56` và lờ `" kg"` là lỗi validation. Công cụ cốt lõi để phát hiện trường hợp này là `java.text.ParsePosition`.

Sau bài học, bạn sẽ biết cách:

- Dùng `NumberFormat.parse(String, ParsePosition)` và `DecimalFormat` để parse theo `Locale`.
- Phân biệt kết quả parse thành công một **prefix** với việc tiêu thụ **toàn bộ chuỗi**.
- Hiểu đúng `getIndex()`, `getErrorIndex()`, `null`, điểm bắt đầu và trạng thái của `ParsePosition`.
- Tạo hàm parse chặt chẽ bằng Java 17: xác nhận kiểu số, toàn chuỗi và miền nghiệp vụ.
- Phân biệt giới hạn của kiểm tra toàn chuỗi với kiểm tra cú pháp grouping, ký tự khoảng trắng, `NaN`/`Infinity`, độ chính xác và các giá trị ngoài miền.

## 2. Locale thay đổi ý nghĩa dấu phân cách số

Java cung cấp các cách biểu diễn số khác nhau theo `Locale`. Ví dụ phổ biến:

| Locale | Chuỗi biểu diễn một nghìn hai trăm ba mươi tư phẩy năm sáu |
| --- | --- |
| `Locale.US` | `"1,234.56"` |
| `Locale.GERMANY` | `"1.234,56"` |

Cùng một ký tự `,` hoặc `.` có thể được hiểu là dấu thập phân, dấu nhóm hoặc không phù hợp với cách biểu diễn dự kiến. Vì vậy không được dựa vào locale mặc định của hệ điều hành khi định dạng dữ liệu trao đổi có hợp đồng cố định.

~~~java
NumberFormat german = NumberFormat.getNumberInstance(Locale.GERMANY);
NumberFormat american = NumberFormat.getNumberInstance(Locale.US);
~~~

Đoạn này giả định đã import `java.text.NumberFormat` và `java.util.Locale`, và được đặt trong một phương thức.

Các yếu tố cần phân biệt:

- **Locale của dữ liệu:** cách chuỗi được tạo hoặc người dùng nhập, ví dụ tiếng Đức hay tiếng Mỹ.
- **Locale mặc định của tiến trình:** có thể thay đổi theo máy, môi trường triển khai hoặc mã khác.
- **Hợp đồng định dạng:** ngoài locale, ứng dụng còn phải quy định có cho phép grouping, khoảng trắng, dấu âm, số mũ hoặc hậu tố đơn vị hay không.

`NumberFormat.getNumberInstance(Locale.GERMANY)` giúp đọc số theo locale Đức; nó **không** tự biến parser thành bộ xác thực chặt chẽ của tất cả quy tắc nghiệp vụ.

## 3. NumberFormat.parse(String) và parse(String, ParsePosition)

`NumberFormat` có hai cách dùng quan trọng.

**Cách tiện lợi:**

~~~java
NumberFormat format = NumberFormat.getNumberInstance(Locale.GERMANY);
Number value = format.parse("1.234,56 kg"); // Có thể nhận một số từ tiền tố.
~~~

Đây là đoạn minh họa bên trong phương thức có khai báo `throws ParseException` hoặc `try/catch`. Overload `parse(String)` có thể ném `ParseException` khi không parse được từ vị trí bắt đầu, nhưng **không có hợp đồng bắt buộc phải tiêu thụ hết chuỗi**. Đừng xem việc lời gọi không ném exception là “whole-input validation”.

**Cách quan sát vị trí:**

~~~java
NumberFormat format = NumberFormat.getNumberInstance(Locale.GERMANY);
ParsePosition pos = new ParsePosition(0);
Number value = format.parse("1.234,56 kg", pos);

System.out.println(value);          // 1234.56
System.out.println(pos.getIndex()); // 8
~~~

Ở overload có `ParsePosition`:

- Giá trị trả về là một `Number` nếu parse được phần bắt đầu được phép.
- Có thể trả `null` khi không nhận diện được số.
- `pos.getIndex()` phản ánh vị trí tiếp theo sau phần đã parse thành công.
- `pos.getErrorIndex()` có thể cho thông tin lỗi khi parse thất bại; **không** thay thế phép kiểm tra đã tiêu thụ hết đầu vào.

Với một form chỉ chứa số, logic cơ bản phải đồng thời kiểm tra **`value != null`** và **`pos.getIndex() == input.length()`**.

## 4. ParsePosition lưu những gì?

`java.text.ParsePosition` là một đối tượng trạng thái có thể thay đổi, với hai thông tin chính:

| API | Ý nghĩa |
| --- | --- |
| `new ParsePosition(startIndex)` | Bắt đầu parse tại chỉ số UTF-16 được chỉ định |
| `getIndex()` | Chỉ số bắt đầu/hiện tại; khi parse thành công, là vị trí tiếp theo sau phần đã tiêu thụ |
| `setIndex(index)` | Chọn vị trí bắt đầu mới |
| `getErrorIndex()` | Vị trí báo lỗi khi parser cung cấp; có thể là −1 nếu không có thông tin lỗi |
| `setErrorIndex(index)` | Cho phép thay đổi trạng thái chỉ số lỗi |

`ParsePosition` không giữ chuỗi nguồn và cũng không xác định sẵn locale; locale được cấu hình ở `NumberFormat`/`DecimalFormat`.

### Quy ước chỉ số của Java String

Các chỉ số vị trí dùng theo đơn vị **UTF-16 code unit**, cùng hệ chỉ số với `String.length()`. Do đó, điều kiện so sánh cuối chuỗi là:

~~~java
pos.getIndex() == input.length()
~~~

Không dùng số lượng code point Unicode (`codePointCount`) hoặc số byte UTF-8 để so với `ParsePosition`. Nếu đầu vào có ký tự bổ sung ngoài BMP, số UTF-16 code unit và số code point có thể khác nhau; `String.length()` vẫn là đơn vị phù hợp cho chỉ số của parser.

### ParsePosition không phải là Boolean success

Một ví dụ có thể parse được tiền tố nhưng vẫn có ký tự không hợp lệ về sau:

~~~java
String text = "1.234,56 kg";
ParsePosition pos = new ParsePosition(0);
Number parsed = NumberFormat.getNumberInstance(Locale.GERMANY).parse(text, pos);

boolean hasNumber = parsed != null;               // true
boolean consumedAll = pos.getIndex() == text.length(); // false
~~~

Nếu chỉ dựa vào `hasNumber`, chương trình nhận sai dữ liệu. Nếu chỉ kiểm tra `getErrorIndex() == -1`, chương trình cũng có nguy cơ nhận sai: không có lỗi được ghi nhận khi parser **chủ động dừng sau một tiền tố hợp lệ** không có nghĩa phần còn lại đã được xác thực.

## 5. Công thức kiểm tra toàn bộ chuỗi

Với dữ liệu phải bắt đầu từ ký tự đầu tiên và không cho phép phần dư, mẫu cơ bản:

~~~java
static Number parseEntire(String text, Locale locale) {
    if (text == null || text.isEmpty()) {
        throw new IllegalArgumentException("Missing numeric text");
    }

    NumberFormat parser = NumberFormat.getNumberInstance(locale);
    ParsePosition pos = new ParsePosition(0);
    Number number = parser.parse(text, pos);

    if (number == null || pos.getIndex() != text.length()) {
        throw new IllegalArgumentException("Invalid or trailing characters");
    }
    return number;
}
~~~

Đây là **phương thức minh họa** đặt trong lớp Java, cần import `NumberFormat`, `ParsePosition` và `Locale`.

Điều kiện gồm hai phần bắt buộc:

1. `number != null` — một giá trị đã được parse.
2. `pos.getIndex() == text.length()` — parser đã đọc tới đúng cuối chuỗi.

Không cần tự tăng chỉ số. Không tự cắt phần hậu tố trước khi so sánh, vì như thế đã làm mất bằng chứng rằng chuỗi đầu vào chứa dữ liệu dư.

**Định nghĩa “toàn chuỗi” phải được quyết định trước.** Nếu ứng dụng cho phép khoảng trắng ngoài số, có thể dùng `trim()` theo hợp đồng trước khi parse rồi so sánh với **độ dài chuỗi đã chuẩn hóa**. Nếu không cho phép khoảng trắng, giữ nguyên `text` và yêu cầu tất cả ký tự đều được tiêu thụ.

## 6. Phân biệt parse thất bại, prefix success và whole-input success

Với bộ parse số Đức:

| Text | Kết quả dự kiến về prefix | Toàn chuỗi được đọc? | Kết luận khi field chỉ cho phép số |
| --- | --- | --- | --- |
| `"1.234,56"` | 1234.56 | Có | Chấp nhận nếu đáp ứng nghiệp vụ |
| `"1.234,56 kg"` | 1234.56 | Không | Từ chối phần dư |
| `"12,5abc"` | 12.5 | Không | Từ chối phần dư |
| `"abc"` | Không parse được từ đầu | Không | Từ chối |
| `""` | Không có số | Không | Từ chối |
| `"-5"` | −5 | Có | Còn phải kiểm tra miền giá trị |
| `"1.234,56"` theo locale US | Có thể bị hiểu khác hoặc dừng sớm | Không suy ra được ý định | Dùng locale đúng hợp đồng |

Bảng cố ý không biến “parse được một số” thành “hợp lệ”. Một chuỗi có thể được tiêu thụ hết nhưng vẫn **không đúng miền giá trị**, hoặc bị parser chấp nhận theo quy tắc grouping tương đối linh hoạt.

## 7. NumberFormat trả Number: lưu ý kiểu và độ chính xác

`NumberFormat.parse` trả kiểu trừu tượng `Number`. Tùy định dạng và giá trị, kết quả có thể được biểu diễn bằng wrapper số nguyên hoặc dấu phẩy động. Đừng giả định mọi kết quả luôn là `Double` và ép kiểu:

~~~java
Number value = NumberFormat.getNumberInstance(Locale.GERMANY)
        .parse("123", new ParsePosition(0));
double asDouble = value.doubleValue(); // lấy giá trị theo kiểu double
~~~

Ví dụ trên minh họa lấy giá trị; bản thân nó **chưa kiểm tra toàn chuỗi**. Mặt khác, `doubleValue()` có thể làm mất độ chính xác đối với một số nguyên lớn hoặc giá trị thập phân có nhiều chữ số.

Với tiền hoặc dữ liệu decimal cần giữ chữ số, trong JDK chuẩn, `NumberFormat.getNumberInstance(Locale.GERMANY)` trả một `DecimalFormat`. Có thể cấu hình:

~~~java
DecimalFormat parser =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.GERMANY);
parser.setParseBigDecimal(true);
~~~

Khi parse số thập phân thông thường, `DecimalFormat` có thể trả `BigDecimal`, giúp tránh bước chuyển qua binary64 trước khi kiểm tra và sử dụng kết quả decimal. Tuy nhiên **không được ép mù mọi kết quả về `BigDecimal`**: các giá trị đặc biệt như NaN/Infinity có thể được biểu diễn bằng kiểu khác theo hợp đồng `DecimalFormat`. Kiểm tra `instanceof BigDecimal` trước khi sử dụng.

Chỉ sử dụng ép kiểu `(DecimalFormat)` khi bạn biết implementation đang cung cấp `DecimalFormat` (các locale số phổ biến của JDK chuẩn). Trong môi trường tích hợp provider tùy biến, có thể kiểm tra `instanceof` và từ chối kiểu formatter không được hỗ trợ để tránh `ClassCastException`.

## 8. Ví dụ parser decimal đầy đủ: toàn chuỗi, miền số và kiểu kết quả

Giả sử ứng dụng nhận số lượng decimal theo quy ước Đức, cho phép:

- Giá trị từ **0 đến 10.000**, gồm hai biên.
- Grouping và dấu phẩy thập phân của locale Đức.
- Không nhận ký tự dư hay đơn vị ở cuối.
- Không chấp nhận NaN/Infinity.
- Giữ biểu diễn bằng `BigDecimal` để kiểm tra decimal và tránh làm tròn binary64 trước khi validation.

Hàm áp dụng:

~~~java
static BigDecimal parseGermanAmount(String input) {
    if (input == null || input.isEmpty()) {
        throw new IllegalArgumentException("Missing number");
    }

    NumberFormat base = NumberFormat.getNumberInstance(Locale.GERMANY);
    if (!(base instanceof DecimalFormat parser)) {
        throw new IllegalStateException("DecimalFormat is required");
    }
    parser.setParseBigDecimal(true);

    ParsePosition pos = new ParsePosition(0);
    Number result = parser.parse(input, pos);

    if (!(result instanceof BigDecimal value)
            || pos.getIndex() != input.length()) {
        throw new IllegalArgumentException("Invalid number or trailing text");
    }

    if (value.signum() < 0
            || value.compareTo(new BigDecimal("10000")) > 0) {
        throw new IllegalArgumentException("Out of allowed range");
    }
    return value;
}
~~~

Đây là **phương thức thành viên** để đặt trong lớp Java 17+, cần import `BigDecimal`, `DecimalFormat`, `NumberFormat`, `ParsePosition` và `Locale`.

Các điểm quan trọng:

1. Tham số `input` không được null hoặc rỗng.
2. Tạo parser **theo locale xác định**, không phụ thuộc locale mặc định.
3. Bật `setParseBigDecimal(true)` trước khi parse.
4. Bắt đầu từ index **0**.
5. Yêu cầu trả về `BigDecimal` và vị trí cuối bằng `input.length()`.
6. Chỉ sau đó mới kiểm tra miền decimal `[0, 10000]`, bằng `signum` và `compareTo`.

`value.compareTo(new BigDecimal("10000"))` so sánh giá trị số học, không dựa vào scale của `BigDecimal`. `new BigDecimal("10000")` nhận chính xác số decimal 10000 theo chuỗi.

Việc tạo `NumberFormat` mới mỗi lời gọi tránh chia sẻ một `DecimalFormat` có thể thay đổi trạng thái giữa nhiều luồng. `NumberFormat` không nên được chia sẻ giữa các thread nếu không có cơ chế đồng bộ riêng theo hướng dẫn của Java API.

## 9. Chương trình Java 17+ hoàn chỉnh

Lưu thành tệp `LocaleParsePositionDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleParsePositionDemo {
    static BigDecimal parseGermanAmount(String input) {
        if (input == null || input.isEmpty()) {
            throw new IllegalArgumentException("Missing number");
        }

        NumberFormat base = NumberFormat.getNumberInstance(Locale.GERMANY);
        if (!(base instanceof DecimalFormat parser)) {
            throw new IllegalStateException("DecimalFormat is required");
        }
        parser.setParseBigDecimal(true);

        ParsePosition pos = new ParsePosition(0);
        Number result = parser.parse(input, pos);

        if (!(result instanceof BigDecimal value)
                || pos.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid or trailing text");
        }
        if (value.signum() < 0
                || value.compareTo(new BigDecimal("10000")) > 0) {
            throw new IllegalArgumentException("Outside [0, 10000]");
        }
        return value;
    }

    public static void main(String[] args) {
        NumberFormat german = NumberFormat.getNumberInstance(Locale.GERMANY);
        String withSuffix = "1.234,56 kg";
        ParsePosition pos = new ParsePosition(0);
        Number prefix = german.parse(withSuffix, pos);

        System.out.println("prefix=" + prefix);
        System.out.println("consumed=" + pos.getIndex() + "/" + withSuffix.length());
        System.out.println("full=" + (pos.getIndex() == withSuffix.length()));

        System.out.println("strict=" + parseGermanAmount("1.234,56"));
        System.out.println("plain=" + parseGermanAmount("1234,56"));
        System.out.println("zero=" + parseGermanAmount("0"));

        String[] invalid = {
            "1.234,56 kg", "12,5abc", "abc", "", "-5", "20.000,00"
        };
        for (String text : invalid) {
            try {
                parseGermanAmount(text);
                System.out.println("accepted=" + text);
            } catch (IllegalArgumentException ex) {
                System.out.println("rejected=" + text);
            }
        }

        ParsePosition badPos = new ParsePosition(0);
        Number bad = german.parse("abc", badPos);
        System.out.println("failed=" + (bad == null));
        System.out.println("errorIndex=" + badPos.getErrorIndex());
    }
}
~~~

Biên dịch/chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 LocaleParsePositionDemo.java
java LocaleParsePositionDemo
~~~

Stdout dự kiến trên nhà cung cấp dữ liệu locale tiêu chuẩn của JDK 17+:

~~~text
prefix=1234.56
consumed=8/11
full=false
strict=1234.56
plain=1234.56
zero=0
rejected=1.234,56 kg
rejected=12,5abc
rejected=abc
rejected=
rejected=-5
rejected=20.000,00
failed=true
errorIndex=0
~~~

Giải thích:

- `NumberFormat.parse(withSuffix, pos)` nhận một số từ phần đầu `"1.234,56"` và dừng tại index 8, trước `" kg"`.
- `parseGermanAmount` dùng `setParseBigDecimal(true)` và bắt buộc parser tiêu thụ **toàn bộ chuỗi**, nên từ chối hậu tố, đơn vị và ký tự thừa.
- `"abc"` không tạo giá trị từ vị trí 0; `getErrorIndex()` được hiển thị để quan sát, nhưng không thay cho `value != null` và so sánh vị trí.
- Giá trị âm `"-5"` và `"20.000,00"` được parse thành số nhưng ngoài miền nghiệp vụ `[0, 10000]`, nên bị từ chối.
- Chuỗi rỗng bị loại trước khi parse.

Nếu JVM sử dụng nhà cung cấp locale được tùy biến, các biểu diễn/thuộc tính locale có thể khác bộ dữ liệu tiêu chuẩn; hệ thống cần cố định môi trường và kiểm thử quy tắc locale thực tế khi yêu cầu tương thích chặt chẽ.

## 10. getErrorIndex() dùng khi nào?

`ParsePosition.getErrorIndex()` có giá trị khi parser **không thể nhận diện một số** và muốn chỉ ra vị trí nghi ngờ gây lỗi. Ví dụ parser số Đức gặp `"abc"` ở index 0 thì kết quả có thể `null` và error index được đặt 0.

Nhưng hãy phân biệt:

- **Không parse được từ đầu:** `value == null`. Index thành công có thể giữ nguyên, và `getErrorIndex()` có thể chỉ ra nơi lỗi.
- **Parse được một tiền tố:** `value != null`, `index < length`. Parser không nhất thiết coi phần còn lại là lỗi; `errorIndex` có thể vẫn bằng −1.
- **Đã parse hết:** `value != null` và `index == length`. Đây mới là yêu cầu cơ bản của validation “whole input”.

Không nên viết:

~~~java
// Không đủ để đảm bảo toàn chuỗi hợp lệ:
boolean valid = pos.getErrorIndex() == -1;
~~~

Không nên kiểm tra `getErrorIndex() >= 0` thay cho `pos.getIndex() != text.length()`. `getErrorIndex()` không phải thông báo lỗi lexical toàn cục hoặc bộ kiểm tra quy tắc nghiệp vụ.

Nếu muốn báo lỗi vị trí phần dư, với parse prefix thành công hãy dùng:

~~~java
int firstUnconsumed = pos.getIndex();
if (firstUnconsumed < input.length()) {
    // Có thể báo: ký tự không được chấp nhận bắt đầu tại firstUnconsumed.
}
~~~

Đây là đoạn minh họa sau khi đã parse, chưa phải một chương trình độc lập. Cần phân biệt rõ index UTF-16 với index hiển thị trong giao diện người dùng có thể dùng code point/grapheme cluster.

## 11. Bắt đầu ở index khác 0, tái sử dụng ParsePosition và kiểm tra kết thúc

`ParsePosition` cho phép parse một con số bắt đầu **giữa** chuỗi. Điều đó hữu ích khi ứng dụng có giao thức gồm phần tiền tố cố định:

~~~java
String text = "qty=1.234,56";
ParsePosition pos = new ParsePosition(4);

Number n = NumberFormat.getNumberInstance(Locale.GERMANY).parse(text, pos);
System.out.println(n);              // 1234.56
System.out.println(pos.getIndex()); // 12
~~~

Trong trường hợp này, bạn đã **chủ động cho phép bỏ qua bốn ký tự đầu** `"qty="`. Việc `pos.getIndex() == text.length()` chỉ chứng minh đã tiêu thụ từ vị trí bắt đầu tới hết chuỗi; nó không xác nhận tiền tố đúng. Cần kiểm tra riêng `text.startsWith("qty=")` (hoặc grammar của giao thức) và chọn index 4 một cách có chủ đích.

Với một field đơn thuần chỉ chứa số, **luôn bắt đầu từ index 0**; không nên chọn index khác rồi gọi đó là “parse toàn chuỗi”.

### ParsePosition là đối tượng trạng thái

Nếu dùng lại cùng một instance `ParsePosition`, lần parse sau có thể **bắt đầu từ index cũ**. Một số trạng thái lỗi cũng có thể còn tồn tại hoặc thay đổi tùy kết quả parser. Mẫu dễ kiểm soát nhất là tạo một `new ParsePosition(0)` cho **mỗi chuỗi đầu vào**.

~~~java
ParsePosition first = new ParsePosition(0);
ParsePosition second = new ParsePosition(0);
~~~

Không chia sẻ cùng một `ParsePosition` có thể thay đổi giữa các thread nếu không tự kiểm soát đồng bộ.

## 12. Kiểm tra toàn chuỗi vẫn chưa phải validation cú pháp thật chặt

`NumberFormat`/`DecimalFormat` được thiết kế để xử lý định dạng số theo locale; trong nhiều cấu hình, parser có thể **linh hoạt** với grouping hoặc những cách viết mà ứng dụng không muốn nhận. Điều kiện `index == length` chỉ đảm bảo parser tiêu thụ hết ký tự theo **ngữ pháp mà parser đang chấp nhận**.

Ví dụ yêu cầu dữ liệu tiền tệ có đúng mẫu “1.234,56”, không chấp nhận mọi vị trí grouping, có thể cần thêm một bước kiểm tra định dạng.

Các lựa chọn:

1. **Hợp đồng số theo locale tương đối linh hoạt:** parse với `NumberFormat`, kiểm tra whole-input, type và range. Cách này phù hợp khi chấp nhận các biến thể hợp lệ theo parser.
2. **Không cho phép dấu grouping:** tạo `DecimalFormat`, đặt `setGroupingUsed(false)` và kiểm tra whole-input; vẫn nên kiểm thử các dạng đặc biệt được chấp nhận.
3. **Yêu cầu grouping đúng vị trí và cú pháp chính xác:** xác thực grammar bằng quy tắc riêng đã được kiểm thử theo locale; `DecimalFormat` parse sau đó chỉ là bước chuyển giá trị. Đừng trông chờ `index == length` một mình bảo đảm cấu trúc nhóm hàng nghìn.
4. **Dữ liệu trao đổi giữa máy móc:** tốt hơn dùng một format **bất biến theo locale**, như decimal ASCII với dấu `.` và quy tắc rõ ràng, thay vì tùy thuộc ngôn ngữ hiển thị của người dùng.

### Vì sao không chỉ round-trip format rồi so với input?

Một ý tưởng là parse rồi `format(value)` và so chuỗi đầu vào. Phương pháp này có thể **từ chối cả chuỗi hợp lệ** vì formatter quyết định số chữ số thập phân, grouping, zero đầu, dấu cộng và rounding theo pattern. Nếu muốn định dạng đúng tuyệt đối, phải xác định rõ **một dạng canonical duy nhất** và xây bộ kiểm tra phù hợp; không thể mặc định mọi chuỗi người dùng cần giống output formatter.

## 13. Phân biệt NumberFormat với Double.parseDouble

| Khía cạnh | `NumberFormat` theo `Locale` | `Double.parseDouble` |
| --- | --- | --- |
| Dấu thập phân | Tùy locale, ví dụ Đức dùng `,` | Cú pháp Java dùng `.` |
| Dấu nhóm | Có thể xử lý theo locale | Không hỗ trợ grouping kiểu `1,234.56` |
| Hậu tố không hợp lệ | Có thể parse một tiền tố rồi dừng | Thường ném `NumberFormatException` nếu chuỗi không đúng grammar |
| Cơ chế kiểm tra toàn chuỗi | `ParsePosition` và `getIndex()` | Parser xác thực cú pháp toàn chuỗi theo grammar Java |
| Giá trị trả về | `Number`; có thể cấu hình `DecimalFormat` dùng `BigDecimal` | Primitive `double` |
| NaN/Infinity | Có thể xử lý theo ký hiệu locale và implementation | `"NaN"`, `"Infinity"` theo cú pháp Java |
| Chính xác decimal | Dùng `setParseBigDecimal(true)` với `DecimalFormat` | Theo binary64, có làm tròn |

Chọn API dựa trên **định dạng nguồn**. Nếu người dùng nhập số theo locale, `NumberFormat` là công cụ phù hợp nhưng cần validation đầy đủ. Nếu hệ thống nhận protocol decimal với dấu chấm thống nhất, `Double.parseDouble` hoặc `BigDecimal(String)` có thể đơn giản hơn; tuy nhiên vẫn phải kiểm tra dữ liệu nghiệp vụ (miền giá trị, NaN/Infinity, độ chính xác).

## 14. Lưu ý về số đặc biệt, số âm và BigDecimal

`DecimalFormat.setParseBigDecimal(true)` không đồng nghĩa **mọi** kết quả đều là `BigDecimal`. Các giá trị không phải số bình thường, đặc biệt NaN/Infinity theo locale, có thể được trả dưới dạng `Double`. Bởi vậy đoạn:

~~~java
if (!(result instanceof BigDecimal amount)) {
    throw new IllegalArgumentException("Expected a finite decimal value");
}
~~~

là kiểm tra có chủ đích nếu hợp đồng chỉ cho phép decimal hữu hạn. Nó cũng tránh lỗi ép kiểu `ClassCastException`.

Mặt khác, `BigDecimal` hỗ trợ số âm, zero và những số decimal rất nhỏ; việc chọn miền (chẳng hạn ≥0) là **một bước kiểm tra khác**. Các yêu cầu như “hai chữ số thập phân đúng”, “không quá ba chữ số phần lẻ”, “không được số âm” hoặc “phải thuộc `[0, 10000]`” không tự xuất hiện từ cấu hình locale.

Với tiền hoặc tỷ lệ cần độ chính xác decimal, lưu `BigDecimal` và sử dụng `compareTo` để so miền. Không chuyển sang `double` chỉ để kiểm tra rồi lại chuyển về `BigDecimal`: quá trình đó có thể làm mất chữ số.

## 15. Trimming, whitespace và ký tự Unicode

Một form cho người dùng có thể gửi `" 1.234,56 "`. Có ít nhất hai thiết kế hợp lý:

- **Strict raw input:** không chấp nhận khoảng trắng đầu/cuối; giữ nguyên text và buộc parser tiêu thụ hết.
- **Normalize rồi strict:** nếu hợp đồng cho phép whitespace biên, chuẩn hóa đầu vào trước (ví dụ `strip()` hoặc `trim()` tùy quy tắc ký tự) rồi parse đầy đủ chuỗi **đã chuẩn hóa**.

Không tự gọi `trim()` chỉ vì tiện: với giao thức, chữ ký số hoặc dữ liệu lưu trữ, thay đổi đầu vào có thể không được phép. `String.strip()` và `String.trim()` không xử lý mọi loại dấu cách Unicode theo cùng một cách; dấu cách không ngắt được dùng làm grouping trong một số locale có thể cần xử lý đặc biệt.

Cũng cần phân biệt:

- **Khoảng trắng biên:** phần trước/sau toàn bộ số.
- **Grouping separator:** ký tự phân cách nhóm chữ số hợp lệ của locale, có thể trông giống dấu cách.
- **Đơn vị ở cuối:** ví dụ `" kg"`, không nên bỏ qua trong field chỉ nhận số.
- **Ký tự Unicode giống chữ số:** không tự chuẩn hóa thành ASCII nếu hệ thống chưa quy định.

Với validation toàn chuỗi, chuỗi sau bước chuẩn hóa (nếu có) là chuỗi dùng để tính `length()`; không lấy độ dài văn bản gốc đem so với vị trí trên chuỗi đã sửa.

## 16. Hiệu năng, tính luồng và bảo mật dữ liệu đầu vào

`NumberFormat`/`DecimalFormat` là các đối tượng có trạng thái cấu hình (pattern, symbol, grouping, parseBigDecimal). Khi chạy song song:

- Không chia sẻ một formatter mutable cho nhiều luồng mà không có biện pháp đồng bộ phù hợp.
- Có thể tạo formatter **mới** cho mỗi request, hoặc dùng cơ chế cung cấp formatter riêng theo thread nếu đo đạc cho thấy cần tối ưu.
- `ParsePosition` cũng mutable; tạo mới cho mỗi lần parse sẽ tránh index và error index bị dùng lại ngoài ý muốn.

Đối với dữ liệu bên ngoài:

- Đặt giới hạn độ dài chuỗi đầu vào hợp lý để tránh chi phí parse quá mức.
- Không chấp nhận dữ liệu dài bất thường chỉ vì parser trả được prefix ở đầu.
- Định nghĩa rõ locale, dấu phân cách, cho phép dấu âm và miền giá trị.
- Nếu thông báo lỗi chứa text của người dùng, escape/ghi log theo quy định để tránh log injection và lộ dữ liệu nhạy cảm.
- Với tài chính và dữ liệu cần precision, không ép thành `double` nếu không cần.

## 17. Các lỗi thường gặp

| Lỗi | Hậu quả | Sửa đúng |
| --- | --- | --- |
| Chỉ dùng `NumberFormat.parse(text)` | Có thể bỏ qua hậu tố | `parse(text, new ParsePosition(0))` rồi kiểm tra index |
| Chỉ kiểm tra `number != null` | Prefix hợp lệ vẫn lọt | Cần thêm `index == text.length()` |
| Chỉ kiểm tra `getErrorIndex() == -1` | Không phát hiện mọi ký tự còn dư | Kiểm tra vị trí tiêu thụ |
| Dùng `new ParsePosition(4)` cho field chỉ chứa số | Có thể bỏ qua 4 ký tự đầu | Bắt đầu từ index 0 |
| Dùng `parsePosition` cũ mà không reset | Lần sau bắt đầu sai vị trí | Tạo mới cho mỗi lần parse |
| So với `String.codePointCount` hoặc byte length | Sai hệ chỉ số | Dùng `String.length()` |
| Parse theo locale mặc định của server | Máy khác hiểu dấu khác | Chỉ định `Locale` rõ ràng |
| Ép mọi `Number` thành `Double` | Có thể `ClassCastException` | Dùng `Number`/`instanceof` và chuyển có kiểm soát |
| Ép mọi kết quả `DecimalFormat` thành `BigDecimal` | NaN/Infinity có thể dùng kiểu khác | Kiểm tra `instanceof BigDecimal` |
| Nghĩ full consumption chứng minh grouping đúng | Parser có thể chấp nhận dạng nhóm linh hoạt | Thêm validation lexical/pattern |
| Nghĩ parse được là đúng miền | Âm, quá lớn vẫn parse được | Kiểm tra miền nghiệp vụ |
| Dùng `doubleValue()` cho tiền decimal | Có thể mất độ chính xác | Dùng `BigDecimal` trực tiếp |
| Formatter dùng chung giữa thread | Trạng thái mutable, dễ lỗi | Tạo riêng hoặc bảo vệ đúng |
| Tự động `trim()` rồi không đổi độ dài so sánh | So sánh sai text và index | So với length của chuỗi thực sự parse |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `parse("1.234,56 kg")` có thể thành công theo locale Đức nhưng dữ liệu chưa hợp lệ?

**Đáp án:** Parser đọc được tiền tố `"1.234,56"` thành số 1234.56, nhưng không nhất thiết tiêu thụ `" kg"`. Một field chỉ chứa số phải kiểm tra `ParsePosition.getIndex() == text.length()`.

**Câu 2.** Nếu `getErrorIndex() == -1`, có chắc chuỗi đã parse hết không?

**Đáp án:** Không. Khi parse được tiền tố, parser có thể dừng mà không ghi lỗi; cần kiểm tra `getIndex()`.

**Câu 3.** `NumberFormat.parse(String, ParsePosition)` trả `null`, có thể chấp nhận nếu index bằng length không?

**Đáp án:** Không. Điều kiện nhận là **cả** `result != null` và `index == length`. Nếu `null`, không có số hợp lệ.

**Câu 4.** ParsePosition được tạo bằng `new ParsePosition(4)` có phù hợp để kiểm tra toàn chuỗi của field số không?

**Đáp án:** Không. Nó bỏ qua phần đầu. Chỉ dùng vị trí khác 0 khi prefix được grammar của ứng dụng kiểm tra riêng.

**Câu 5.** Tại sao `DecimalFormat.setParseBigDecimal(true)` vẫn cần kiểm tra `instanceof BigDecimal`?

**Đáp án:** Giá trị đặc biệt như NaN hoặc Infinity có thể không tạo `BigDecimal`. Nếu hợp đồng chỉ nhận số decimal hữu hạn, phải từ chối chúng và tránh ép kiểu sai.

**Câu 6.** Tại sao whole-input parse không tự bảo đảm phân nhóm hàng nghìn “đẹp và đúng chuẩn”?

**Đáp án:** `NumberFormat` có thể chấp nhận một số hình thức grouping linh hoạt. `index == length` chỉ chứng minh đã tiêu thụ toàn bộ theo parser, không chứng minh chuỗi tuân thủ một mẫu nhập liệu chặt chẽ do ứng dụng tự đặt.

**Câu 7.** Nếu chuẩn hóa chuỗi trước khi parse, phải dùng độ dài nào để so với `getIndex()`?

**Đáp án:** `length()` của **chính chuỗi được đưa vào parser**, không dùng độ dài chuỗi thô ban đầu.

## 19. Tóm tắt và tài liệu tham khảo

Điểm cần nhớ:

- `NumberFormat` theo locale được thiết kế để đọc chuỗi số **theo quy ước vùng miền**, nhưng việc parse một số không đảm bảo toàn bộ input hợp lệ.
- **Bộ đôi kiểm tra bắt buộc** cho field chỉ chứa số: `result != null` và `pos.getIndex() == text.length()`, với `new ParsePosition(0)`.
- `getErrorIndex()` giúp tìm lỗi parse, **không** thay thế việc kiểm tra vị trí kết thúc.
- Kiểm tra toàn chuỗi chỉ là **một lớp validation**; còn cần kiểm tra kiểu, miền giá trị, độ chính xác và những ràng buộc định dạng khác.
- Dữ liệu decimal cần chính xác có thể dùng `DecimalFormat.setParseBigDecimal(true)` và kiểm tra `instanceof BigDecimal`.
- Hãy quy định locale, grouping, whitespace và tính hợp lệ của dấu phân cách theo hợp đồng đầu vào, thay vì phó mặc cho locale mặc định.

Nguồn tra cứu chính thức (Java 17):

- [NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): `parse(String)`, `parse(String, ParsePosition)`, formatter theo `Locale` và lưu ý về thread safety.
- [DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): `setParseBigDecimal`, pattern, grouping và decimal symbols.
- [ParsePosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html): `getIndex()`, `setIndex()`, `getErrorIndex()`.
- [Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): mô hình locale trong API Java.
- [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): số decimal chính xác và `compareTo()`.
