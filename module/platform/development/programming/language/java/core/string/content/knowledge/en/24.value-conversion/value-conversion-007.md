# NumberFormat khi phân tích số theo Locale trong Java

## 1. Vì sao không thể phân tích mọi số bằng một kiểu dấu cố định?

Cách viết số phụ thuộc vào **quy ước vùng/ngôn ngữ (locale)**. Cùng một giá trị một nghìn hai trăm ba mươi bốn phẩy năm có thể xuất hiện dưới các dạng khác nhau:

| Locale | Văn bản thường thấy | Ý nghĩa |
|---|---|---|
| `Locale.US` | `1,234.50` | Dấu phẩy phân nhóm nghìn, dấu chấm thập phân |
| `Locale.GERMANY` | `1.234,50` | Dấu chấm phân nhóm nghìn, dấu phẩy thập phân |

Nếu chương trình cố định dấu chấm là dấu thập phân và xóa mọi dấu phẩy trước khi gọi `Double.parseDouble()`, nó có thể hiểu sai dữ liệu nhập từ Đức. Ngược lại, thay toàn bộ dấu chấm bằng dấu phẩy cũng không giải quyết được mọi trường hợp: nhiều locale dùng khoảng trắng, khoảng trắng không ngắt, các ký hiệu chữ số và quy tắc phân nhóm khác nhau.

Java cung cấp `java.text.NumberFormat` để **định dạng** giá trị số thành văn bản và **phân tích (parse)** văn bản số theo locale. Bài này tập trung vào chiều phân tích với `NumberFormat.parse()`, đồng thời giải thích các giới hạn về độ chính xác, kiểm tra tính hợp lệ và lựa chọn kiểu kết quả.

Ví dụ mở đầu:

~~~java
import java.text.NumberFormat;
import java.text.ParseException;
import java.util.Locale;

public class FirstParse {
    public static void main(String[] args) throws ParseException {
        NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

        Number a = us.parse("1,234.50");
        Number b = de.parse("1.234,50");

        System.out.println(a.doubleValue()); // 1234.5
        System.out.println(b.doubleValue()); // 1234.5
    }
}
~~~

Hai chuỗi đầu vào khác nhau nhưng được phân tích thành giá trị số giống nhau khi sử dụng đúng locale.

## 2. Các lớp và phương thức cần biết

Các thành phần chính trong thư viện chuẩn:

- `java.util.Locale` mô tả quy ước địa phương hóa. `Locale.US` và `Locale.GERMANY` là hai hằng tiện dụng; `Locale.forLanguageTag("vi-VN")` tạo locale theo thẻ ngôn ngữ.
- `java.text.NumberFormat` là API định dạng/phân tích số tổng quát. Nó trừu tượng hóa ký hiệu thập phân, phân nhóm và một số quy tắc tùy locale.
- `java.text.DecimalFormat` là triển khai thông dụng của `NumberFormat` cho các mẫu số thập phân; cho phép chỉ định pattern và bật `setParseBigDecimal(true)`.
- `java.text.DecimalFormatSymbols` lưu các ký hiệu dùng trong mẫu như dấu thập phân và dấu phân nhóm.
- `java.text.ParsePosition` lưu vị trí bắt đầu, vị trí đã phân tích xong và vị trí lỗi; hữu ích để kiểm tra toàn bộ chuỗi.
- `java.text.ParseException` xuất hiện ở overload `parse(String)` nếu phương thức không thể phân tích một số từ vị trí bắt đầu.

Hai overload tiêu biểu:

~~~java
Number parse(String source) throws ParseException
Number parse(String source, ParsePosition position)
~~~

Khác biệt quan trọng: overload nhận `ParsePosition` trả về `null` nếu không thể phân tích bắt đầu từ vị trí chỉ định, thay vì ném `ParseException` cho trường hợp parse thất bại thông thường.

Các factory phương thức thường dùng:

~~~java
NumberFormat number = NumberFormat.getNumberInstance(Locale.US);
NumberFormat integer = NumberFormat.getIntegerInstance(Locale.US);
NumberFormat percent = NumberFormat.getPercentInstance(Locale.US);
NumberFormat currency = NumberFormat.getCurrencyInstance(Locale.US);
~~~

Chọn đúng factory cho **loại văn bản đầu vào**. Ví dụ dấu phần trăm và ký hiệu tiền không phải chỉ là dấu trang trí: kiểu formatter tương ứng có thể áp dụng quy tắc phân tích và tỷ lệ khác nhau. Với một số thập phân thông thường, hãy bắt đầu bằng `getNumberInstance(locale)`.

`NumberFormat.getInstance(locale)` cũng thường được dùng để lấy formatter số tổng quát; `getNumberInstance(locale)` nêu rõ ý định hơn trong bài toán này.

## 3. Quy trình parse một số theo locale

Một luồng dữ liệu thường có các bước:

1. Xác định **locale của chính dữ liệu nhập**, không tự suy ra chỉ từ vị trí máy chủ.
2. Chọn formatter tương ứng, ví dụ `getNumberInstance(Locale.GERMANY)` cho văn bản kiểu Đức.
3. Gọi `parse(text)` để thu được một đối tượng `Number`.
4. Kiểm tra xem toàn bộ input có được tiêu thụ hay không nếu đầu vào cần hợp lệ tuyệt đối.
5. Chọn kiểu số thích hợp (`long`, `double`, `BigDecimal`) dựa trên yêu cầu độ chính xác, khoảng giá trị và phép tính tiếp theo.

Ví dụ:

~~~java
String input = "1.234,50";
Locale locale = Locale.GERMANY;

NumberFormat parser = NumberFormat.getNumberInstance(locale);
Number parsed = parser.parse(input);

double value = parsed.doubleValue(); // 1234.5
~~~

Đừng dùng kết quả hiển thị mặc định của đối tượng `Number` để đoán locale của dữ liệu gốc. Dữ liệu đã parse trở thành giá trị số; quy tắc hiển thị lại là quyết định riêng của chương trình.

### Locale của người nhập và locale của môi trường

Nếu biểu mẫu yêu cầu nhập số theo chuẩn Đức, cấu hình máy chủ đang chạy ở US **không làm cho chuỗi `1.234,50` tự trở thành số US**. Nên lưu hoặc truyền locale đi kèm nguồn dữ liệu, hay quy định rõ định dạng đầu vào trong hợp đồng API.

Để kiểm thử ổn định:

~~~java
NumberFormat parser = NumberFormat.getNumberInstance(Locale.US);
~~~

Cách trên đáng tin cậy hơn việc gọi `NumberFormat.getNumberInstance()` không có tham số rồi kỳ vọng cùng kết quả trên mọi máy. Phiên bản không tham số sử dụng locale mặc định phù hợp với mục đích định dạng.

## 4. Kết quả của parse() là Number, không cố định Double

`NumberFormat.parse(...)` trả về kiểu trừu tượng `Number`. Triển khai có thể trả đối tượng số nguyên hoặc số thực tùy giá trị và cấu hình. Không nên mặc định rằng kiểu kết quả luôn là `Double`:

~~~java
NumberFormat parser = NumberFormat.getNumberInstance(Locale.US);

Number whole = parser.parse("1234");
Number fraction = parser.parse("1234.50");

// Không nên làm:
// Double d = (Double) whole;
~~~

Nếu cần một giá trị `double`, dùng phương thức chung:

~~~java
double x = fraction.doubleValue();
~~~

Nếu cần số nguyên:

~~~java
long n = whole.longValue();
~~~

Tuy nhiên, **`longValue()` không phải trình kiểm tra số nguyên hợp lệ**: nó có thể cắt phần thập phân khi giá trị vốn là số thực, và chuyển kiểu có thể làm mất thông tin khi giá trị vượt phạm vi hoặc không biểu diễn chính xác. Phải kiểm tra yêu cầu nghiệp vụ trước khi chuyển kiểu, đặc biệt với tiền, số lượng, định danh hoặc các giá trị đòi hỏi độ chính xác tuyệt đối.

Đối với đầu vào thập phân chính xác, xem phần `DecimalFormat` và `BigDecimal` bên dưới.

## 5. Điểm dễ bỏ sót: parse(String) có thể chỉ đọc tiền tố hợp lệ

`NumberFormat.parse(String)` **không bảo đảm đã sử dụng toàn bộ chuỗi**. Nếu parser tìm được một tiền tố có dạng số, phần còn lại có thể bị bỏ qua.

Trên formatter `Locale.US` thông dụng:

~~~java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);

System.out.println(us.parse("1,234.50kg"));
// 1234.5
~~~

Đây là kết quả hợp lý của **quá trình phân tích tiền tố**; nhưng nếu một ô nhập liệu bắt buộc chỉ chứa số, việc chấp nhận `kg` ở cuối là lỗi kiểm tra dữ liệu.

Tình huống nguy hiểm hơn:

~~~java
String input = "1,234.50andMore";
Number parsed = us.parse(input);
// Có thể đọc thành giá trị của tiền tố 1,234.50,
// trong khi phần "andMore" chưa được tiêu thụ.
~~~

Không nên chỉ dựa vào việc `parse(String)` không ném `ParseException` để kết luận văn bản hoàn toàn hợp lệ.

## 6. Dùng ParsePosition để kiểm tra toàn bộ chuỗi

`ParsePosition` cung cấp:

- `getIndex()`: chỉ số đầu tiên sau đoạn đã phân tích thành công.
- `getErrorIndex()`: vị trí lỗi được ghi nhận, hoặc thường là `-1` khi không có lỗi parse tại điểm bắt đầu.
- `setIndex(...)`: thiết lập vị trí bắt đầu parse nếu thực sự muốn đọc từ giữa một chuỗi.

Mẫu kiểm tra toàn bộ đầu vào:

~~~java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class StrictConsumption {
    static Number parseEntire(String input, Locale locale) {
        if (input == null || input.isEmpty()) {
            throw new IllegalArgumentException("Input must not be empty");
        }

        NumberFormat parser = NumberFormat.getNumberInstance(locale);
        ParsePosition position = new ParsePosition(0);
        Number result = parser.parse(input, position);

        if (result == null || position.getIndex() != input.length()) {
            throw new IllegalArgumentException(
                    "Invalid number at index " + position.getIndex()
                            + ": " + input);
        }

        return result;
    }

    public static void main(String[] args) {
        System.out.println(
                parseEntire("1,234.50", Locale.US).doubleValue());
        // 1234.5

        try {
            parseEntire("1,234.50kg", Locale.US);
        } catch (IllegalArgumentException e) {
            System.out.println("Rejected trailing text");
        }
        // Rejected trailing text
    }
}
~~~

Tại đây, `"1,234.50kg"` có độ dài 10 ký tự, trong khi parser chỉ tiến đến chỉ số 8 sau khi đọc phần số; điều kiện `position.getIndex() != input.length()` phát hiện phần dư.

**Giới hạn quan trọng:** tiêu thụ toàn bộ chuỗi **không tương đương với kiểm tra ngữ pháp số nghiêm ngặt**. Nhiều triển khai `NumberFormat` chấp nhận các dạng phân nhóm hoặc dấu ít chặt chẽ hơn yêu cầu nghiệp vụ. Chẳng hạn, một chuỗi nhóm chữ số sai chuẩn có thể vẫn được parser đọc thành một số. Nếu giao diện yêu cầu chính xác mẫu phân nhóm, số chữ số thập phân, chỉ cho phép số dương hoặc không cho phép ký tự đặc biệt, cần **kiểm tra bổ sung theo quy tắc nghiệp vụ** trước/sau parse.

Không nên gọi cách kiểm tra bằng `ParsePosition` là “strict parser tuyệt đối”; nó chỉ bảo đảm parser đã tiến qua toàn bộ input.

### Có nên trim() trước khi parse?

Điều này tùy hợp đồng đầu vào:

~~~java
String normalized = input.trim();
~~~

`trim()` có thể phù hợp nếu người dùng được phép nhập khoảng trắng ngoài cùng; nhưng với dữ liệu máy hoặc những định dạng cần bảo toàn từng ký tự, hành động đó có thể che giấu lỗi. `String.strip()` cũng có quy tắc Unicode riêng; không phải mọi khoảng trắng không ngắt dùng để phân nhóm đều được xử lý giống nhau.

Xác định trước: khoảng trắng đầu/cuối có hợp lệ không, ký hiệu phân nhóm nào được phép, số âm và phần thập phân có hợp lệ không. Sau đó thực hiện đúng chính sách, không tùy tiện xóa mọi dấu hoặc mọi khoảng trắng.

## 7. DecimalFormat: nhận BigDecimal khi cần độ chính xác thập phân

Với các phép tính tài chính hay lượng tiền, việc chuyển chuỗi thập phân qua `double` có thể gây sai số nhị phân. `DecimalFormat` cho phép yêu cầu kết quả parse là `BigDecimal` bằng `setParseBigDecimal(true)`.

Ví dụ:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.util.Locale;

public class BigDecimalParse {
    public static void main(String[] args) throws ParseException {
        DecimalFormat parser = new DecimalFormat(
                "#,##0.###",
                DecimalFormatSymbols.getInstance(Locale.US)
        );
        parser.setParseBigDecimal(true);

        BigDecimal amount = (BigDecimal) parser.parse("1,234.50");
        System.out.println(amount); // 1234.50
        System.out.println(amount.add(new BigDecimal("0.10")));
        // 1234.60
    }
}
~~~

Trong ví dụ này:

1. `DecimalFormatSymbols.getInstance(Locale.US)` cung cấp dấu thập phân và phân nhóm của US.
2. Pattern `#,##0.###` nói rõ hình thức số cơ bản và có tối đa ba chữ số thập phân khi **format** theo mẫu đó.
3. `setParseBigDecimal(true)` giúp giữ giá trị thập phân dưới dạng `BigDecimal` thay vì buộc qua `double`.
4. `new BigDecimal("0.10")` biểu diễn chính xác số thập phân 0.10, phù hợp hơn `new BigDecimal(0.10)` cho loại bài toán này.

**Không hiểu lầm pattern là validator chặt:** số dấu `#` sau dấu thập phân trong pattern chủ yếu điều khiển cách **định dạng**; parser có thể nhận số chữ số thập phân khác. Phải kiểm tra scale và các điều kiện đầu vào nếu yêu cầu chính xác tối đa 2 hoặc 3 chữ số.

Một hàm parse đầy đủ với `BigDecimal`:

~~~java
static BigDecimal parseDecimalEntire(String text, Locale locale) {
    if (text == null || text.isEmpty()) {
        throw new IllegalArgumentException("Empty decimal input");
    }

    DecimalFormat format = new DecimalFormat(
            "#,##0.################",
            DecimalFormatSymbols.getInstance(locale)
    );
    format.setParseBigDecimal(true);

    ParsePosition pos = new ParsePosition(0);
    Number parsed = format.parse(text, pos);

    if (!(parsed instanceof BigDecimal)
            || pos.getIndex() != text.length()) {
        throw new IllegalArgumentException("Invalid decimal: " + text);
    }
    return (BigDecimal) parsed;
}
~~~

Các yêu cầu tính tiền thường cần thêm `setScale(scale, roundingMode)` hoặc phép kiểm tra scale trước khi tính; đó là quy tắc nghiệp vụ độc lập với việc hiểu dấu chấm/dấu phẩy của locale.

Lưu ý: các giá trị đặc biệt như `NaN` hoặc vô cực có cách xử lý riêng tùy formatter; chúng không có biểu diễn `BigDecimal` thông thường. Với bài toán yêu cầu **số thập phân hữu hạn**, cần loại trừ giá trị đặc biệt và kiểm tra kết quả thực tế.

## 8. Định dạng và phân tích là hai chiều khác nhau

`format(number)`: giá trị số → văn bản theo locale.

`parse(text)`: văn bản → giá trị số theo locale.

Ví dụ:

~~~java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
us.setMinimumFractionDigits(2);
us.setMaximumFractionDigits(2);

String rendered = us.format(1234.5);
System.out.println(rendered); // 1,234.50

Number parsed = us.parse(rendered);
System.out.println(parsed.doubleValue()); // 1234.5
~~~

Các tùy chọn `setMinimumFractionDigits`/`setMaximumFractionDigits` làm thay đổi **cách render**. Chúng **không phải cam kết** rằng parse chỉ chấp nhận văn bản có đúng hai chữ số sau dấu thập phân.

Vì vậy, ý tưởng “format theo locale rồi parse lại phải khôi phục nguyên số” chỉ đúng trong những điều kiện cụ thể: formatter có thể làm tròn, rút bớt chữ số hoặc áp dụng kiểu biểu diễn khác. Ví dụ nếu formatter hiển thị tối đa hai chữ số thập phân, số `1.23456` có thể được in thành `1.23` rồi parse lại thành `1.23`, làm mất thông tin ban đầu.

Nếu số được lưu và trao đổi giữa các hệ thống, đừng chọn định dạng giao diện có dấu phân nhóm để làm biểu diễn máy mặc định. Hãy dùng định dạng máy ổn định đã được hợp đồng dữ liệu quy định (ví dụ kiểu số JSON hợp lệ hoặc chuỗi thập phân có quy tắc rõ ràng), và chỉ sử dụng `NumberFormat` khi cần giao tiếp với người dùng theo locale.

## 9. NumberFormat khác Integer.parseInt và Double.parseDouble thế nào?

| Khía cạnh | `NumberFormat.parse(text)` | `Integer.parseInt(text)` / `Double.parseDouble(text)` |
|---|---|---|
| Mục đích | Phân tích số theo quy ước locale | Chuyển chuỗi theo cú pháp số Java quy định |
| Dấu phân nhóm | Có thể hiểu theo locale | Không chấp nhận nhóm hàng nghìn theo locale |
| Dấu thập phân | Phụ thuộc locale | `Double.parseDouble` dùng cú pháp dấu chấm thập phân |
| Kiểu trả về | `Number` (đa hình) | `int` hoặc `double` |
| Lỗi khi đầu vào sai | `ParseException` hoặc kết quả `null` tùy overload, có thể parse tiền tố | `NumberFormatException` |
| Kiểm soát tiêu thụ toàn chuỗi | Cần `ParsePosition` nếu yêu cầu | Các parser nguyên thủy không chấp nhận văn bản thừa ngoài cú pháp hợp lệ |
| Độ chính xác tiền tệ | Có thể dùng `DecimalFormat` + `BigDecimal` | `Double.parseDouble` cho số nhị phân dấu chấm động |

Ví dụ:

~~~java
double machineValue = Double.parseDouble("1234.50"); // 1234.5

NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);
double userValue = de.parse("1.234,50").doubleValue(); // 1234.5
~~~

Dùng `parseInt`/`parseDouble` khi chuỗi đến từ nguồn **đã có cú pháp máy được định nghĩa rõ**, không phải số do người dùng ở các locale khác nhau nhập theo thói quen.

## 10. Các trường hợp đầu vào cần chủ động quyết định

### 10.1. Khoảng trắng và ký tự phân nhóm

Một số locale dùng khoảng trắng hoặc các biến thể Unicode của dấu cách làm dấu phân nhóm. `"1 234,50"`, `"1 234,50"` (dấu cách không ngắt) và `"1 234,50"` (dấu cách không ngắt hẹp) **không nhất thiết tương đương** đối với mọi parser.

Đừng tự xóa toàn bộ whitespace nếu bạn chưa quy định dạng nào hợp lệ. Việc đó có thể biến chuỗi chứa khoảng trắng sai vị trí thành một số tưởng như đúng. Nếu phải chấp nhận nhiều định dạng đầu vào, hãy xác định quy tắc chuyển đổi và kiểm tra chúng bằng tập dữ liệu thực.

### 10.2. Số âm, dấu cộng và ngoặc

Một số định dạng biểu diễn âm bằng dấu trừ, một số pattern tài chính dùng ngoặc. `NumberFormat.getNumberInstance(locale)` không hứa chấp nhận mọi kiểu ký hiệu âm. Với dữ liệu kiểu kế toán, phải dùng formatter/pattern tương thích với định dạng đó và thêm kiểm tra.

### 10.3. Phần trăm

`NumberFormat.getPercentInstance(locale)` có thể chuyển một văn bản phần trăm sang **giá trị tỷ lệ**. Ví dụ khái niệm `50%` thường tương ứng `0.5`, không phải `50`. Không dùng percent formatter như bộ đọc số nguyên chung; hãy xác định dữ liệu đầu vào thể hiện “50 phần trăm” hay “50 đơn vị” trước.

### 10.4. Tiền tệ

`NumberFormat.getCurrencyInstance(locale)` hỗ trợ biểu diễn tiền theo locale nhưng bản thân kết quả `Number` **không mang theo đơn vị tiền tệ**. Nếu ứng dụng có USD, EUR, VND cùng tồn tại, cần lưu mã tiền riêng, kiểm tra đơn vị được nhập và có thể phải dùng hệ thống parse tiền tệ chuyên biệt. Đừng đoán đơn vị chỉ từ độ lớn của giá trị.

### 10.5. Ký hiệu khoa học

Không mặc định mọi pattern của `NumberFormat` đều nhận mọi dạng `1.2e3` giống `Double.parseDouble()`. Với dữ liệu khoa học, chọn parser và pattern hỗ trợ đầu vào đó rồi kiểm chứng trên các phiên bản JDK cần hỗ trợ. Nếu giao thức quy định dạng máy có chữ `e`, một parser máy cố định có thể thích hợp hơn.

### 10.6. Dữ liệu âm thầm sai vì phân nhóm lỏng

Việc dùng `ParsePosition` chỉ đảm bảo parser không bỏ lại ký tự. Nó không đủ để xác nhận đúng vị trí dấu phân nhóm trong mọi trường hợp. Nếu chính sách chỉ nhận dạng US với nhóm ba chữ số, có thể kết hợp một bước kiểm tra hình thức cụ thể trước khi parse, chẳng hạn:

~~~java
boolean validUsForm = text.matches(
        "[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\\.[0-9]+)?"
);
~~~

Regex này **chỉ minh họa chính sách ASCII/US được định nghĩa hẹp**: cho phép số nguyên có hoặc không có nhóm ba chữ số, phần thập phân tùy chọn, không cho khoảng trắng, số khoa học hoặc số bắt đầu bằng dấu chấm. Nó không phải validator cho mọi locale. Sau bước kiểm tra hình thức, vẫn cần parse và kiểm tra giới hạn giá trị theo nghiệp vụ.

## 11. Ví dụ Java 17+ hoàn chỉnh và có kiểm tra đầu vào

Tạo tệp **`LocaleNumberParsingDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleNumberParsingDemo {
    static Number parseEntire(String input, Locale locale) {
        if (input == null || input.isEmpty()) {
            throw new IllegalArgumentException("Empty input");
        }

        NumberFormat format = NumberFormat.getNumberInstance(locale);
        ParsePosition position = new ParsePosition(0);
        Number value = format.parse(input, position);

        if (value == null || position.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid input: " + input);
        }
        return value;
    }

    static BigDecimal parseBigDecimalEntire(
            String input, Locale locale) {
        if (input == null || input.isEmpty()) {
            throw new IllegalArgumentException("Empty input");
        }

        DecimalFormat format = new DecimalFormat(
                "#,##0.################",
                DecimalFormatSymbols.getInstance(locale)
        );
        format.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number value = format.parse(input, position);
        if (!(value instanceof BigDecimal)
                || position.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid input: " + input);
        }
        return (BigDecimal) value;
    }

    public static void main(String[] args) {
        Number us = parseEntire("1,234.50", Locale.US);
        Number de = parseEntire("1.234,50", Locale.GERMANY);

        System.out.println("US: " + us.doubleValue());
        System.out.println("DE: " + de.doubleValue());

        try {
            parseEntire("1,234.50kg", Locale.US);
        } catch (IllegalArgumentException e) {
            System.out.println("Trailing text rejected");
        }

        BigDecimal amount = parseBigDecimalEntire(
                "1,234.50", Locale.US);
        BigDecimal fee = new BigDecimal("0.10");

        System.out.println("Decimal: " + amount);
        System.out.println("Sum: " + amount.add(fee));

        NumberFormat display = NumberFormat.getNumberInstance(Locale.US);
        display.setMinimumFractionDigits(2);
        display.setMaximumFractionDigits(2);
        System.out.println("Formatted: " + display.format(1234.5));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LocaleNumberParsingDemo.java
java LocaleNumberParsingDemo
~~~

Đầu ra mong đợi trên JDK chuẩn với các locale được chỉ định:

~~~text
US: 1234.5
DE: 1234.5
Trailing text rejected
Decimal: 1234.50
Sum: 1234.60
Formatted: 1,234.50
~~~

Giải thích:

1. `parseEntire(...)` nhận chuỗi theo đúng locale và dùng `ParsePosition` kiểm tra không còn đuôi chưa được đọc.
2. Hai chuỗi `1,234.50` và `1.234,50` cho cùng giá trị sau khi áp dụng lần lượt US và Germany.
3. Chuỗi chứa `kg` bị từ chối dù phần tiền tố giống một số hợp lệ.
4. `parseBigDecimalEntire(...)` cấu hình `DecimalFormat` trả `BigDecimal`, giữ biểu diễn thập phân `1234.50` thay vì làm tròn thành một biểu diễn `double`.
5. Phép cộng với `new BigDecimal("0.10")` cho `1234.60` chính xác ở mức thập phân.
6. `display.format(...)` chuyển số về văn bản dành cho giao diện US, có dấu phẩy phân nhóm và hai chữ số thập phân. Đây là bước hiển thị, không phải phép kiểm tra đầu vào.

Ví dụ chủ động tạo instance formatter trong mỗi lời gọi hàm. Điều này cũng tránh vấn đề chia sẻ formatter mutable giữa nhiều luồng.

## 12. Thread-safety và chi phí tạo formatter

Các triển khai `NumberFormat` như `DecimalFormat` có trạng thái thay đổi được (`setGroupingUsed`, `setMinimumFractionDigits`, `setParseBigDecimal` và nhiều cấu hình khác). **Không giả định một instance được chia sẻ có thể bị nhiều luồng cùng parse/format an toàn.** Tài liệu Java khuyến nghị tạo instance riêng theo luồng hoặc có đồng bộ phù hợp.

Ví dụ an toàn, đơn giản:

~~~java
static Number parseUs(String input) throws java.text.ParseException {
    NumberFormat parser = NumberFormat.getNumberInstance(Locale.US);
    return parser.parse(input);
}
~~~

Với ứng dụng hiệu năng cao, có thể cân nhắc chiến lược tái sử dụng theo luồng hoặc thư viện chuyên dụng tùy yêu cầu, nhưng phải kiểm soát cấu hình và tránh để thay đổi trạng thái rò rỉ giữa các request. Chỉ tối ưu sau khi đo nhu cầu thực tế.

Dữ liệu locale có thể phát triển theo JDK và nhà cung cấp dữ liệu địa phương hóa (ví dụ CLDR). Với các locale có dấu phân nhóm đặc biệt hoặc thay đổi quy ước, nên viết test trên phiên bản JDK thực tế được hỗ trợ và dữ liệu tương ứng. Không suy diễn tất cả locale đều dùng chính xác ký hiệu của US/Germany.

## 13. Những lỗi phổ biến

**Lỗi 1 — Dùng `Double.parseDouble("1.234,50")` cho dữ liệu Đức.** Cú pháp số máy của `Double.parseDouble` không phải cú pháp số theo locale Đức. **Cách làm:** dùng `NumberFormat.getNumberInstance(Locale.GERMANY)`.

**Lỗi 2 — Xóa mọi dấu chấm/dấu phẩy rồi parse.** Dễ chuyển sai `1.234,50` thành một giá trị khác. **Cách làm:** biết trước locale; dùng parser phù hợp và xác minh đầu vào.

**Lỗi 3 — Thấy `parse(String)` thành công thì cho rằng toàn chuỗi hợp lệ.** Parser có thể chấp nhận tiền tố số, bỏ lại chữ ở cuối. **Cách làm:** dùng `ParsePosition` và kiểm tra `getIndex() == input.length()`.

**Lỗi 4 — Tin rằng ParsePosition tự thực hiện kiểm tra định dạng nghiêm ngặt.** Nó chỉ báo parser đã tiêu thụ đến đâu, không bảo đảm mọi vị trí dấu phân nhóm hợp lệ theo chính sách. **Cách làm:** nếu cần, kiểm tra thêm mẫu dữ liệu cụ thể và ràng buộc nghiệp vụ.

**Lỗi 5 — Ép kết quả parse trực tiếp sang Double.** `NumberFormat.parse` trả `Number`; kiểu triển khai không cố định. **Cách làm:** dùng API `Number` hoặc cấu hình `DecimalFormat` trả `BigDecimal` khi phù hợp.

**Lỗi 6 — Dùng double để lưu tiền rồi nghĩ format hai số lẻ khắc phục sai số.** Định dạng chỉ ảnh hưởng cách in. **Cách làm:** dùng kiểu giá trị thập phân phù hợp như `BigDecimal` và quy tắc làm tròn rõ ràng.

**Lỗi 7 — Dùng `setMaximumFractionDigits(2)` để giới hạn đầu vào hai số lẻ.** Thuộc tính này chủ yếu quản lý format. **Cách làm:** kiểm tra số chữ số thập phân, scale và chính sách trước/sau parse.

**Lỗi 8 — Dùng một NumberFormat mutable toàn cục cho nhiều luồng.** Có thể gây dữ liệu sai khi đồng thời thay đổi hoặc sử dụng formatter. **Cách làm:** tạo instance riêng hoặc đồng bộ theo thiết kế.

**Lỗi 9 — Nhầm số định dạng theo locale với giao thức trao đổi dữ liệu.** Chuỗi hiển thị cho người dùng có thể không được parser của hệ thống khác hiểu đúng. **Cách làm:** định nghĩa biểu diễn máy riêng và rõ ràng.

## 14. Checklist tự kiểm tra

Trước khi dùng `NumberFormat` trong chương trình thực tế, hãy trả lời:

1. **Input đến từ locale nào?** Có được xác định từ cấu hình người dùng, trường nhập hay hợp đồng dữ liệu không?
2. **Giá trị cần là loại số nào?** Số nguyên, thực xấp xỉ hay `BigDecimal` chính xác?
3. **Có chấp nhận tiền tố hợp lệ và hậu tố ký tự không?** Nếu không, dùng `ParsePosition` để kiểm tra toàn bộ input.
4. **Cần đúng định dạng phân nhóm hay chỉ cần hiểu được số?** Với quy định chặt, cần bước kiểm tra ngữ pháp riêng.
5. **Có giới hạn min/max, số chữ số thập phân, số âm hoặc ký hiệu tiền tệ không?** Đừng giao hết cho parser.
6. **Có nhiều luồng cùng dùng formatter không?** Tránh chia sẻ instance mutable thiếu đồng bộ.
7. **Kết quả format có được dùng để lưu/trao đổi máy không?** Nếu có, dùng một hợp đồng biểu diễn dữ liệu độc lập với locale hiển thị.

## 15. Ghi nhớ

`NumberFormat` giúp Java đọc **văn bản số theo locale**, xử lý sự khác biệt giữa dấu thập phân và phân nhóm một cách có ngữ cảnh. Bắt đầu với `getNumberInstance(locale)` và `parse(...)` khi cần chuyển dữ liệu người dùng thành `Number`. Nếu yêu cầu **toàn bộ văn bản phải hợp lệ**, dùng `ParsePosition` để phát hiện phần đuôi chưa được phân tích và thêm kiểm tra quy tắc nghiệp vụ. Nếu cần giữ **độ chính xác thập phân**, dùng `DecimalFormat` với `setParseBigDecimal(true)` hoặc parser số thập phân phù hợp. Phân biệt rõ **parse để hiểu dữ liệu**, **validate để chấp nhận dữ liệu**, và **format để trình bày dữ liệu**: ba trách nhiệm liên quan nhưng không thay thế nhau.
