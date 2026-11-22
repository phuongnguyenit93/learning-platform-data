# Dấu phân nhóm, khoảng trắng và chữ số Unicode khi phân tích đầu vào

## 1. Vì sao một số “nhìn đúng” vẫn có thể bị đọc sai?

Trong một ứng dụng Java đa ngôn ngữ, dữ liệu nhập từ biểu mẫu không chỉ gồm các chữ số ASCII `0–9` và dấu chấm. Người dùng có thể nhập số như:

| Chuỗi người dùng nhìn thấy | Locale/ngữ cảnh minh họa | Những ký tự đáng chú ý |
| --- | --- | --- |
| `1,234.50` | `en-US` | Dấu phẩy `,` nhóm nghìn, dấu chấm `.` thập phân |
| `1.234,50` | `de-DE` | Dấu chấm nhóm nghìn, dấu phẩy thập phân |
| `1 234,50` | `fr-FR`, dữ liệu CLDR thông dụng | Dấu phân nhóm **NNBSP** `U+202F`, không phải ASCII space |
| `1 234,50` | Một số dữ liệu/cách nhập sử dụng NBSP | Dấu phân nhóm **NBSP** `U+00A0` |
| `١٬٢٣٤٫٥٠` | Dữ liệu số chữ Ả Rập | Chữ số Ả Rập `U+0660–U+0669`, dấu nhóm `U+066C`, dấu thập phân `U+066B` |
| `１２３４．５０` | Chữ số fullwidth | Không thể tùy ý suy ra mọi parser đều chấp nhận cả dấu câu fullwidth |

Hai chuỗi nhìn tương tự có thể chứa **các Unicode code point khác nhau**. Khi phân tích số (*parsing*), parser không chỉ nhìn hình dạng ký tự: nó có quy tắc dấu nhóm, dấu thập phân, chữ số và quy ước từ `Locale`/`DecimalFormatSymbols`. Một sự thay đổi nhỏ, ví dụ thay dấu nhóm NNBSP bằng dấu cách thường, có thể làm parser dừng giữa chừng.

**Mục tiêu của bài:** đọc số bản địa hóa bằng Java 17+ đúng ngữ cảnh, phân biệt các loại khoảng trắng và chữ số Unicode, kiểm tra kết quả phân tích **đã tiêu thụ toàn bộ input**, đồng thời không nhầm việc parse thành công với xác thực cấu trúc dữ liệu nghiêm ngặt.

## 2. Phân biệt giá trị số với chuỗi biểu diễn

Giá trị `1234.50` là một số thập phân; `"1,234.50"` và `"1.234,50"` là hai cách **viết** có thể biểu đạt giá trị đó. Nếu ứng dụng nhận chuỗi `"1.234,50"` rồi gọi:

~~~java
new BigDecimal("1.234,50")
~~~

thì mã sẽ thất bại vì `BigDecimal(String)` **không phải parser số theo locale**. Constructor này nhận dạng số thập phân theo cú pháp chuẩn của nó, không nhận dấu nhóm/chấm phẩy bản địa hóa.

Đối với dữ liệu người dùng đã bản địa hóa, thông thường nên dùng:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(locale);
Number parsed = format.parse(input);
~~~

Đây là **mảnh mã trong một phương thức**, cần import `java.text.NumberFormat` và `java.util.Locale`, có biến `locale`/`input` và xử lý `ParseException`. Tuy nhiên, cách gọi đơn giản này chưa đủ để kiểm tra **toàn bộ** chuỗi nhập đã hợp lệ.

### Ba bước không nên trộn vào nhau

1. **Xác định quy ước nguồn:** người dùng đang nhập theo locale nào, ví dụ `de-DE` hay `en-US`?
2. **Chuyển đổi văn bản thành số:** bộ phân tích hiểu dấu nhóm, dấu thập phân, ký hiệu và chữ số nào?
3. **Xác thực nghiệp vụ:** cú pháp nhóm có nghiêm ngặt không, có ký tự dư không, giá trị có trong phạm vi cho phép không, precision/scale có hợp lệ không?

Một bộ phân tích thành công ở bước 2 **không có nghĩa** bạn có thể bỏ qua bước 3.

## 3. `Locale` và `DecimalFormatSymbols` quyết định điều gì?

`java.text.NumberFormat.getNumberInstance(locale)` trả về một formatter/parser với quy ước số tương ứng. Trong các JDK thông dụng, đó thường là `DecimalFormat`. `DecimalFormatSymbols` lưu các ký hiệu cụ thể cho một định dạng:

| API | Vai trò |
| --- | --- |
| `DecimalFormatSymbols.getInstance(locale)` | Lấy các ký hiệu số của locale |
| `getGroupingSeparator()` | Ký tự được dùng làm dấu phân nhóm nghìn |
| `getDecimalSeparator()` | Ký tự thập phân |
| `getZeroDigit()` | Ký tự chữ số zero mặc định của hệ chữ số |
| `getMinusSign()` | Ký hiệu dấu âm |
| `NumberFormat.getNumberInstance(locale)` | Bộ định dạng/phân tích số theo locale |
| `NumberFormat.parse(...)` | Phân tích chuỗi thành `Number` |
| `DecimalFormat.setParseBigDecimal(true)` | Yêu cầu parser `DecimalFormat` trả `BigDecimal` khi phù hợp thay vì `Double` thông thường |

Ví dụ tường minh:

~~~java
Locale locale = Locale.FRANCE;
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(locale);

char grouping = symbols.getGroupingSeparator();
char decimal = symbols.getDecimalSeparator();
~~~

Đây là **mảnh mã trong phương thức**, cần import `java.util.Locale` và `java.text.DecimalFormatSymbols`.

Với dữ liệu CLDR phổ biến trong JDK hiện đại, `fr-FR` thường có dấu nhóm `U+202F` và dấu thập phân `,`. Nhưng JDK/provider và dữ liệu locale có thể thay đổi. **Không suy từ tên locale rằng ký tự luôn cố định**, khi cần biết chính xác, hãy xem `DecimalFormatSymbols` thực tế và kiểm thử trong môi trường deploy.

### Nhìn vào code point, đừng chỉ nhìn giao diện

Khi debug, thay vì in một dấu cách mơ hồ, in dạng `U+XXXX`:

~~~java
System.out.printf(
        Locale.ROOT,
        "Grouping = U+%04X%n",
        (int) symbols.getGroupingSeparator()
);
~~~

Đoạn trên là **mảnh mã trong phương thức**, có biến `symbols` và import `java.util.Locale`. Nếu in `U+202F` thì đó là NNBSP chứ không phải ASCII space `U+0020`.

## 4. ASCII space, NBSP và NNBSP không tương đương

Ba ký tự dưới đây thường trông như “khoảng trắng”, nhưng có mã Unicode và tính chất khác nhau:

| Tên | Code point | Tên tiếng Anh | Tình huống |
| --- | --- | --- | --- |
| Space thông thường | `U+0020` | SPACE | Gõ từ phím Space |
| Khoảng trắng không ngắt | `U+00A0` | NO-BREAK SPACE (NBSP) | Văn bản không muốn tách dòng, số/tài nguyên bản địa hóa |
| Khoảng trắng hẹp không ngắt | `U+202F` | NARROW NO-BREAK SPACE (NNBSP) | Dấu nhóm nghìn trong một số locale, điển hình `fr-FR` với CLDR hiện đại |

Điều này quan trọng khi người dùng **copy/paste** một con số từ trang web, PDF, bảng tính hoặc email. Ví dụ, `1 234,50` và `1 234,50` có thể chỉ khác ký tự ở giữa `1` và `2` nhưng parser sẽ xử lý khác nhau.

### Đừng nghĩ `trim()`/`strip()` loại hết mọi khoảng trắng Unicode

Trong Java 17:

- `String.trim()` loại một tập ký tự đầu/cuối dựa trên giá trị mã ký tự truyền thống.
- `String.strip()` dùng `Character.isWhitespace`.
- `Character.isWhitespace` **không coi NBSP `U+00A0` hoặc NNBSP `U+202F` là whitespace**.
- `Character.isSpaceChar` **có** nhận diện hai ký tự NBSP và NNBSP này.

Ví dụ chạy độc lập, lưu `SpaceCodePointDemo.java`:

~~~java
public class SpaceCodePointDemo {
    public static void main(String[] args) {
        int space = 0x0020;
        int nbsp = 0x00A0;
        int narrowNbsp = 0x202F;

        System.out.println("SPACE whitespace: "
                + Character.isWhitespace(space));
        System.out.println("NBSP whitespace: "
                + Character.isWhitespace(nbsp));
        System.out.println("NBSP space-char: "
                + Character.isSpaceChar(nbsp));
        System.out.println("NNBSP whitespace: "
                + Character.isWhitespace(narrowNbsp));
        System.out.println("NNBSP space-char: "
                + Character.isSpaceChar(narrowNbsp));

        String wrapped = "\u00A0123\u202F";
        System.out.println("Original length: " + wrapped.length());
        System.out.println("After strip length: "
                + wrapped.strip().length());
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 SpaceCodePointDemo.java
java SpaceCodePointDemo
~~~

Kết quả:

~~~text
SPACE whitespace: true
NBSP whitespace: false
NBSP space-char: true
NNBSP whitespace: false
NNBSP space-char: true
Original length: 5
After strip length: 5
~~~

Do đó, thao tác `strip()` **không loại bỏ** NBSP/NNBSP ở đầu/cuối. Tuy nhiên, điều này không có nghĩa nên xóa **mọi** `Character.isSpaceChar` vô điều kiện: trong một con số, NBSP/NNBSP có thể chính là **dấu nhóm hợp lệ**. Xóa nó trước khi parse có thể làm mất thông tin về cấu trúc nhập.

**Cách đúng:** xác định liệu những ký tự đó là dấu nhóm ở bên trong số, khoảng trắng thừa ở hai đầu, hay dữ liệu không hợp lệ. Thiết kế quy tắc xử lý cụ thể cho từng vị trí.

## 5. Ví dụ đầy đủ: `fr-FR` và dấu phân nhóm Unicode

Tạo `FrenchGroupingDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class FrenchGroupingDemo {
    public static void main(String[] args) {
        Locale locale = Locale.FRANCE;

        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);
        System.out.printf(
                Locale.ROOT,
                "Grouping separator: U+%04X%n",
                (int) symbols.getGroupingSeparator()
        );
        System.out.printf(
                Locale.ROOT,
                "Decimal separator: U+%04X%n",
                (int) symbols.getDecimalSeparator()
        );

        DecimalFormat format =
                (DecimalFormat) NumberFormat.getNumberInstance(locale);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        format.setParseBigDecimal(true);

        BigDecimal original = new BigDecimal("1234.50");
        String formatted = format.format(original);

        System.out.println("Formatted: " + formatted);
        System.out.print("Code points: ");
        formatted.codePoints().forEach(cp ->
                System.out.printf(Locale.ROOT, "U+%04X ", cp)
        );
        System.out.println();

        ParsePosition end = new ParsePosition(0);
        Number parsed = format.parse(formatted, end);

        System.out.println("Parsed: " + parsed);
        System.out.println("Fully consumed: "
                + (parsed != null && end.getIndex() == formatted.length()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FrenchGroupingDemo.java
java FrenchGroupingDemo
~~~

Trên JDK dùng dữ liệu CLDR với dấu nhóm `U+202F`, kết quả minh họa là:

~~~text
Grouping separator: U+202F
Decimal separator: U+002C
Formatted: 1 234,50
Code points: U+0031 U+202F U+0032 U+0033 U+0034 U+002C U+0035 U+0030
Parsed: 1234.50
Fully consumed: true
~~~

Nếu provider dùng một ký tự nhóm khác, dòng `Grouping separator`, `Formatted` và `Code points` có thể khác. Dù vậy, chương trình lấy ký hiệu **từ cùng locale/provider**, format và parse bằng chính formatter, nên ví dụ giúp kiểm chứng được cách làm phù hợp môi trường chạy.

**Điểm học tập:** `DecimalFormatSymbols.getGroupingSeparator()` cho biết ký tự thực tế được cấu hình, thay vì suy luận chỉ từ ký hiệu giống dấu cách trên màn hình.

### Tại sao không đơn giản viết `replace(" ", "")`?

Đối với `"1 234,50"`, ký tự nhóm là NNBSP, **không phải** `" "`. `replace(" ", "")` không xử lý ký tự đó. Ngược lại, một phép xóa tất cả khoảng trắng Unicode có thể khiến đầu vào có dấu nhóm **đặt sai vị trí** trở thành dãy số trông hợp lệ, làm mất dấu hiệu cần xác thực.

Nếu sản phẩm có chính sách chấp nhận nhiều dạng khoảng trắng khi nhập số, việc **chuẩn hóa** phải được giới hạn vào những vị trí hợp lệ và sau đó kiểm tra cấu trúc theo locale, thay vì “xóa hết để parser chạy”.

## 6. `NumberFormat.parse` có thể chỉ đọc tiền tố

Một rủi ro lớn là `NumberFormat.parse(String)` hoặc `parse(String, ParsePosition)` **không có nghĩa kiểm tra cú pháp toàn chuỗi theo yêu cầu biểu mẫu**. Một parser có thể chấp nhận phần đầu rồi dừng.

Ví dụ với locale Mỹ:

~~~java
NumberFormat parser =
        NumberFormat.getNumberInstance(Locale.US);
Number number = parser.parse("1,234.50abc");
~~~

Đây là **mảnh mã trong phương thức**, cần import `java.text.NumberFormat` và `java.util.Locale`. Một số implementation có thể trả số `1234.5` dù còn chuỗi `abc`. Nếu chỉ kiểm tra `number != null`, hệ thống có thể chấp nhận input không hợp lệ.

### Kiểm tra vị trí kết thúc bằng ParsePosition

Tạo `PrefixParsingDemo.java`:

~~~java
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class PrefixParsingDemo {
    public static void main(String[] args) {
        String input = "1,234.50abc";

        DecimalFormat parser =
                (DecimalFormat) NumberFormat.getNumberInstance(Locale.US);
        parser.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = parser.parse(input, position);

        System.out.println("Parsed: " + parsed);
        System.out.println("Consumed: " + position.getIndex());
        System.out.println("Input length: " + input.length());
        System.out.println("Valid full input: "
                + (parsed != null
                   && position.getIndex() == input.length()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 PrefixParsingDemo.java
java PrefixParsingDemo
~~~

Với JDK thông dụng, kết quả:

~~~text
Parsed: 1234.50
Consumed: 8
Input length: 11
Valid full input: false
~~~

Giải thích: phần `"1,234.50"` dài 8 ký tự đã được phân tích; `"abc"` không được tiêu thụ. `ParsePosition.getIndex()` cho biết vị trí kết thúc (theo chỉ số ký tự UTF-16), còn `getErrorIndex()` có thể cung cấp vị trí lỗi khi phân tích thất bại.

Mẫu kiểm tra đáng dùng cho form:

~~~java
ParsePosition position = new ParsePosition(0);
Number result = parser.parse(input, position);

if (result == null || position.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid localized number");
}
~~~

Đây là **mảnh mã** với các biến `parser` và `input` có sẵn. Trong ứng dụng thật, cũng nên giới hạn độ dài input và có chính sách đối với các dấu âm, số không, phạm vi và độ chính xác.

**Quan trọng:** kiểm tra tiêu thụ toàn bộ chỉ phát hiện ký tự dư. Nó **không** chứng minh dấu nhóm được đặt đúng chuẩn hay input tuân thủ toàn bộ luật nghiệp vụ.

## 7. Parser có thể chấp nhận dấu phân nhóm đặt sai chỗ

`DecimalFormat` được thiết kế để phân tích số theo nhiều cách nhập, và nhiều implementation không xác thực chặt cách đặt dấu nhóm theo nhóm ba chữ số. Một số input không chuẩn vẫn có thể được parse ra số.

Ví dụ dưới đây minh họa sự khác biệt giữa **parsing** và **validation** trong JDK thông dụng:

~~~text
Input:       12,34,567.89
Meaning:     dấu nhóm không theo kiểu en-US chuẩn
Parsed:      1234567.89
Full input:  true
Strict UI:   phải từ chối nếu sản phẩm yêu cầu nhóm ba chữ số
~~~

Tạo `GroupingValidationDemo.java`:

~~~java
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class GroupingValidationDemo {
    public static void main(String[] args) {
        String input = "12,34,567.89";

        DecimalFormat parser =
                (DecimalFormat) NumberFormat.getNumberInstance(Locale.US);
        parser.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = parser.parse(input, position);

        System.out.println("Parsed: " + parsed);
        System.out.println("Entire input consumed: "
                + (parsed != null
                   && position.getIndex() == input.length()));

        boolean strictEnUS = input.matches(
                "(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)"
              + "(?:\\.[0-9]{1,2})?"
        );
        System.out.println("Strict en-US shape: " + strictEnUS);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GroupingValidationDemo.java
java GroupingValidationDemo
~~~

Kết quả với parser JDK thường gặp:

~~~text
Parsed: 1234567.89
Entire input consumed: true
Strict en-US shape: false
~~~

**Tại sao regex này không dùng cho mọi locale?**

- Nó được viết **riêng cho yêu cầu biểu mẫu en-US**: số không âm, chỉ ASCII `0–9`, dấu `,` nhóm ba chữ số, `.` làm dấu thập phân, tối đa hai chữ số lẻ, không có exponent.
- Nó chấp nhận cả dạng không nhóm `1234567.89` và dạng nhóm chuẩn `1,234,567.89`.
- Nó cố ý từ chối `12,34,567.89` dù parser có thể đọc thành số.
- Nó **không** phải regex chung của `Locale`: các vùng có quy tắc nhóm khác nhau, dấu Unicode, phần âm, chữ số ngoài ASCII, hoặc yêu cầu cho phép nhiều hơn hai chữ số lẻ.
- Không nên chuẩn hóa bừa `12,34,567.89` thành `1234567.89` mà không cảnh báo người nhập nếu sản phẩm yêu cầu dấu nhóm nghiêm ngặt.

Trong nghiệp vụ nhạy cảm (tài chính, thuế, kế toán), nên xác định một **hợp đồng đầu vào** rõ ràng, xác thực cấu trúc trước hoặc cùng quá trình parse, kiểm tra range/scale và ghi log lỗi theo chính sách riêng tư. Không xem `setGroupingUsed(true)` là chế độ “strict grouping”; nó chỉ liên quan đến việc dùng dấu phân nhóm, **không tự đảm bảo mọi vị trí nhóm được kiểm tra nghiêm ngặt**.

## 8. Chữ số Unicode: không chỉ có `0–9`

Trong Java, một chữ số có thể thuộc nhiều hệ chữ viết:

| Hệ chữ số | Minh họa | Unicode thường gặp |
| --- | --- | --- |
| Latin/ASCII | `0123456789` | `U+0030–U+0039` |
| Arabic-Indic | `٠١٢٣٤٥٦٧٨٩` | `U+0660–U+0669` |
| Extended Arabic-Indic | `۰۱۲۳۴۵۶۷۸۹` | `U+06F0–U+06F9` |
| Devanagari | `०१२३४५६७८९` | `U+0966–U+096F` |
| Fullwidth | `０１２３４５６７８９` | `U+FF10–U+FF19` |

`Character.digit(int codePoint, int radix)` có thể xác định **giá trị số** của nhiều ký tự chữ số Unicode. Ví dụ:

~~~java
System.out.println(Character.digit('3', 10));  // 3
System.out.println(Character.digit('٣', 10));  // 3
System.out.println(Character.digit('३', 10));  // 3
System.out.println(Character.digit('３', 10)); // 3
~~~

Đây là **mảnh mã trong method**. `Character.digit` ở đây minh họa *giá trị số học* của một ký tự; nó **không** chứng minh `NumberFormat` của **mọi locale** sẽ chấp nhận mọi loại chữ số, dấu thập phân hoặc dấu nhóm đi kèm.

Một locale như `ar-EG` có thể dùng chữ số Arabic-Indic và các dấu phân cách dành riêng cho hệ chữ số đó, trong khi parser `en-US` có thể không chấp nhận chính những ký tự này. Quy tắc đọc của parser còn phụ thuộc `DecimalFormatSymbols`, provider và cú pháp input.

### Không nhầm số “trông giống nhau” với byte/chuỗi giống nhau

Hai chuỗi `"123"` và `"١٢٣"` mang các code point khác nhau. Dù cùng biểu đạt giá trị một trăm hai mươi ba trong một ngữ cảnh, so sánh `String.equals` giữa chúng cho kết quả `false`.

Hơn nữa, chuỗi có thể trộn nhiều hệ chữ số, dấu nhóm của một locale với dấu thập phân của locale khác, hoặc ký tự confusable. Nếu hệ thống xác thực mã tài khoản, mã định danh, khóa truy cập hay trường dữ liệu giao thức, **không nên tự động cho phép mọi chữ số Unicode chỉ vì chúng có giá trị 0–9**. Những trường đó thường cần cú pháp ASCII cụ thể, không phải parser số cho UI.

## 9. Ví dụ chạy được: chữ số Arabic-Indic với `ar-EG`

Tạo `ArabicDigitsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class ArabicDigitsDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("ar-EG");

        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);
        System.out.printf(Locale.ROOT,
                "Zero digit: U+%04X%n", (int) symbols.getZeroDigit());
        System.out.printf(Locale.ROOT,
                "Grouping: U+%04X%n",
                (int) symbols.getGroupingSeparator());
        System.out.printf(Locale.ROOT,
                "Decimal: U+%04X%n",
                (int) symbols.getDecimalSeparator());

        DecimalFormat format =
                (DecimalFormat) NumberFormat.getNumberInstance(locale);
        format.setParseBigDecimal(true);

        BigDecimal source = new BigDecimal("1234.5");
        String shown = format.format(source);
        System.out.println("Formatted: " + shown);

        ParsePosition position = new ParsePosition(0);
        Number read = format.parse(shown, position);
        System.out.println("Parsed: " + read);
        System.out.println("Full input: "
                + (read != null
                  && position.getIndex() == shown.length()));
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 ArabicDigitsDemo.java
java ArabicDigitsDemo
~~~

Với provider CLDR dùng hệ chữ số Arabic-Indic cho `ar-EG`, đầu ra minh họa:

~~~text
Zero digit: U+0660
Grouping: U+066C
Decimal: U+066B
Formatted: ١٬٢٣٤٫٥
Parsed: 1234.5
Full input: true
~~~

Đây là kết quả phụ thuộc dữ liệu locale; các bộ dữ liệu khác có thể lựa chọn hệ chữ số khác hoặc cho phép cấu hình Unicode locale extension như `u-nu-latn`. Mục đích là thấy **formatter và parser phải dùng một chính sách locale/hệ chữ số nhất quán**, thay vì tự đổi ký tự theo mắt nhìn.

### Khi nào cần Unicode locale extension?

Một thẻ như `ar-EG-u-nu-latn` thể hiện mong muốn sử dụng chữ số Latin trong ngữ cảnh tiếng Ả Rập tại Ai Cập. `Locale` có thể lưu keyword `nu`, nhưng API/provider cụ thể phải hỗ trợ nó để tác động đến định dạng số. Nếu ứng dụng bắt buộc dùng Latin digits, hãy kiểm thử `NumberFormat` thực tế hoặc thiết lập chính sách hiển thị riêng; **không** giả định mọi thư viện đều tôn trọng mọi extension.

## 10. Chiến lược chuẩn hóa đầu vào Unicode an toàn

Một số người dùng copy chuỗi từ tài liệu có NBSP/NNBSP; một số gõ ASCII space thay cho dấu nhóm theo locale. Ứng dụng có thể chọn **strict input** hoặc **lenient input**, nhưng phải nói rõ quy tắc.

### Phương án A — Strict locale input

- Xác định locale người nhập.
- Lấy đúng dấu nhóm/dấu thập phân của locale.
- Chấp nhận một dạng nhóm đã tài liệu hóa và một tập chữ số được phép.
- Xác thực toàn bộ chuỗi, vị trí dấu âm và nhóm, số chữ số thập phân.
- Parse và xác minh miền giá trị, precision/scale.
- Hiển thị lỗi rõ nếu nhập ký tự giống nhưng không đúng quy định.

Phù hợp với trường hợp số tiền hoặc dữ liệu pháp lý cần kiểm soát.

### Phương án B — Lenient input có chuẩn hóa kiểm soát

Một sản phẩm có thể cho phép người dùng nhập dấu space thường thay cho NNBSP, nhưng phải giới hạn:

1. Chỉ thay **ký tự được cho phép** ở vị trí **dấu nhóm**, không thay tất cả khoảng trắng.
2. Trước hoặc sau thay thế, kiểm tra kích cỡ nhóm theo locale và có quy tắc cho giá trị âm/decimal.
3. Không thay dấu thập phân chỉ bằng cách “đoán” nếu một ký tự có thể vừa là dấu nhóm ở locale này vừa là dấu thập phân ở locale khác.
4. Phân tích bằng locale đã xác định và xác nhận toàn bộ input đã được tiêu thụ.
5. Nếu dữ liệu cần audit, cân nhắc giữ bản input thô có kiểm soát quyền riêng tư để giải thích nguồn lỗi.

**Không nên làm điều sau cho mọi locale:**

~~~java
String guessed = input
        .replace(" ", "")
        .replace(",", ".");
~~~

Đây là **mảnh mã có biến `input`**, minh họa cách làm dễ sai. Với `de-DE`, `"1.234,50"` nếu chỉ đổi dấu phẩy thành dấu chấm sẽ thành `"1.234.50"`, không hợp lệ theo cú pháp số chuẩn. Với `en-US`, `"1,234.50"` khi đổi phẩy thành chấm cũng bị sai. Với `fr-FR`, xóa ASCII space không loại được NNBSP.

### Tại sao phải thận trọng với Unicode normalization?

`java.text.Normalizer` có thể áp dụng NFC/NFKC, nhưng **không nên gọi `Normalizer.normalize(input, Form.NFKC)` lên mọi giá trị số và mặc định nó đã sạch**. NFKC có thể đổi một số ký tự tương thích (ví dụ chữ số fullwidth), **không** đồng nghĩa với việc xử lý đúng mọi dấu nhóm, dấu thập phân và quy tắc an toàn theo locale.

Nếu chọn chuẩn hóa NFKC trong sản phẩm, hãy nêu rõ lý do, danh mục ký tự được cho phép trước/sau chuẩn hóa, cách tránh mơ hồ và test các trường hợp trộn hệ chữ số. Không dùng normalization để thay cho validation.

## 11. Parse đúng nhưng vẫn cần kiểm tra miền giá trị và độ chính xác

Một giá trị số hợp cú pháp có thể **không hợp nghiệp vụ**, chẳng hạn tiền âm ở biểu mẫu chỉ cho phép dương hoặc giá trị có quá nhiều chữ số thập phân.

Dùng `BigDecimal` khi cần giá trị thập phân chính xác:

~~~java
DecimalFormat parser =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.US);
parser.setParseBigDecimal(true);

ParsePosition position = new ParsePosition(0);
Number number = parser.parse(input, position);

if (number == null || position.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid number");
}
BigDecimal amount = (BigDecimal) number;

if (amount.signum() < 0) {
    throw new IllegalArgumentException("Negative amount not allowed");
}
if (amount.scale() > 2) {
    throw new IllegalArgumentException("Too many decimal places");
}
~~~

Đây là **mảnh mã trong method**, cần import `java.math.BigDecimal`, `java.text.DecimalFormat`, `java.text.NumberFormat`, `java.text.ParsePosition` và `java.util.Locale`. Biến `input` là chuỗi cần parse. Kiểm tra `scale()` là một lựa chọn chính sách minh họa; nếu muốn chấp nhận số như `1.230` ở trường tối đa hai chữ số phần lẻ, hãy quyết định xử lý các số 0 thừa trước khi áp dụng giới hạn. `scale` không phải chỉ tiêu duy nhất để xác thực tiền.

**Không suy rằng `setParseBigDecimal(true)` tự tạo parser strict.** Nó chủ yếu tác động kiểu số trả về/độ chính xác. Luật nhập liệu vẫn phải kiểm soát separately.

### Parsing và formatting không nhất thiết là phép đảo tuyệt đối

Nếu formatter làm tròn số từ `1234.567` thành `1,234.57`, parse ngược sẽ nhận `1234.57`, **không** phải `1234.567`. Nếu biến đổi Unicode hoặc chấp nhận nhiều cách đặt dấu nhóm, nhiều chuỗi khác nhau cũng có thể chuyển thành cùng một giá trị.

Vì thế, không dùng chuỗi đã format làm dữ liệu lưu trữ chính. Hãy lưu số ở dạng có kiểu (ví dụ `BigDecimal`), còn chuỗi bản địa hóa dành cho hiển thị và nhận input.

## 12. Trường hợp không nên dùng parser số theo Locale

**Số phục vụ giao tiếp giữa các dịch vụ** (JSON number, cấu hình chuẩn, dữ liệu máy) thường cần cú pháp xác định, **không** phụ thuộc người đang xem. Ví dụ JSON number dùng dấu chấm làm dấu thập phân và không dùng dấu nhóm theo locale.

**Mã định danh** như số tài khoản, mã bưu chính, số điện thoại, mã đơn hàng có thể chứa chữ số và dấu nhưng **không phải đại lượng số học**. Không đưa chúng vào `NumberFormat`: có thể mất số 0 đầu, làm thay đổi cấu trúc ký tự hoặc chấp nhận input không đúng hợp đồng.

Nếu thông tin là mã ID hoặc dữ liệu bảo mật, thường cần **chuỗi với validation riêng**, có thể giới hạn ASCII `[0-9]` một cách có chủ đích; không đồng nhất nó với dữ liệu định dạng số địa phương.

## 13. Bảng so sánh lỗi thường gặp

| Sai lầm | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Nghĩ `" "`, NBSP, NNBSP là cùng một ký tự | Không nhận được số copy từ web/PDF | Kiểm tra code point, dùng `DecimalFormatSymbols` |
| Cho rằng `strip()` loại mọi khoảng trắng | NBSP/NNBSP vẫn tồn tại | Xử lý loại ký tự cụ thể theo chính sách |
| Xóa mọi khoảng trắng trước khi parse | Có thể hợp thức hóa dấu nhóm đặt sai | Xác thực vị trí nhóm trước khi chuẩn hóa |
| Gọi `new BigDecimal("1.234,50")` | Thất bại vì constructor không hiểu locale | Dùng parser theo locale rồi kiểm tra |
| Chỉ kiểm tra `parse(...) != null` | Có thể nhận tiền tố của chuỗi lỗi | Dùng `ParsePosition`, yêu cầu tiêu thụ toàn bộ |
| Nghĩ full consumption đồng nghĩa nhóm hợp lệ | Có thể chấp nhận `12,34,567.89` | Thêm validation nghiêm ngặt theo hợp đồng |
| Dùng cùng một regex ASCII cho mọi locale | Từ chối dữ liệu hợp lệ ở locale khác | Thiết kế validation cho locale thực sự được hỗ trợ |
| Giả định `Character.digit` có nghĩa mọi parser chấp nhận mọi chữ số | Parser từ chối chữ số hoặc dấu khác hệ | Kiểm thử `NumberFormat` theo locale/provider |
| Tự thay `,` bằng `.` trên input đa locale | Có thể đảo nghĩa dấu nhóm/thập phân | Xác định nguồn locale và parse đúng quy tắc |
| Không kiểm tra precision/range sau parse | Nhận số tiền quá lớn, quá nhiều phần lẻ | Dùng `BigDecimal` và kiểm tra nghiệp vụ |
| Dùng `NumberFormat` cho mã ID có số 0 đầu | Mất cấu trúc của định danh | Giữ chuỗi gốc và validation theo schema |
| Chia sẻ `DecimalFormat` giữa nhiều request không đồng bộ | Có thể rò trạng thái/cấu hình giữa luồng | Tạo parser theo request hoặc đồng bộ/copy phù hợp |

`NumberFormat` và `DecimalFormat` **không có bảo đảm thread-safe khi dùng chung không đồng bộ**. `Locale` bất biến, nhưng formatter/parser có trạng thái và có thể được cấu hình lại. Trong ứng dụng đa người dùng, truyền `Locale` từ ngữ cảnh request và tạo parser phù hợp.

## 14. Checklist kiểm thử và bài tập

### Checklist QA

1. Với mỗi locale được hỗ trợ, kiểm tra dấu nhóm, dấu thập phân và chữ số thực tế bằng `DecimalFormatSymbols`.
2. Test các chuỗi có SPACE `U+0020`, NBSP `U+00A0`, NNBSP `U+202F`; lưu ý chúng khác nhau.
3. Test chữ số ASCII, Arabic-Indic và trường hợp trộn hệ chữ số theo chính sách sản phẩm.
4. Test chuỗi được parse toàn bộ so với chỉ parse tiền tố, ví dụ `"1,234.50abc"`.
5. Test nhóm không chuẩn như `"12,34,567.89"`; đừng phụ thuộc mặc định lenient cho validation nghiệp vụ.
6. Test số âm, số không, giá trị rất lớn, nhiều chữ số phần thập phân và input quá dài.
7. Test đúng JDK và locale provider ở production; dấu nhóm `fr-FR` và quy tắc Unicode có thể biến đổi theo dữ liệu locale.
8. Test độ chính xác với `BigDecimal`; không cho format rồi parse đè giá trị nguồn khi có làm tròn.
9. Kiểm thử parser đa luồng hoặc phạm vi sống của parser để không dùng chung instance mutable sai cách.

### Bài tập tự kiểm tra

1. Viết chương trình in `DecimalFormatSymbols.getGroupingSeparator()` cho `Locale.US`, `Locale.GERMANY` và `Locale.FRANCE` theo dạng `U+XXXX`; tại sao nhìn bằng mắt chưa đủ?
2. Cho chuỗi có NNBSP `"1 234,50"`. Vì sao `replace(" ", "")` không xóa được dấu nhóm? Vì sao vẫn không nên xóa mọi khoảng trắng Unicode?
3. Dùng `ParsePosition` parse `"1,234.50abc"` theo `en-US`. Phân tích `getIndex()` và giải thích vì sao không thể chấp nhận toàn bộ input.
4. Dùng `GroupingValidationDemo` thử `"12,34,567.89"`, `"1,234,567.89"` và `"1234567.89"`. Loại nào hợp lệ theo regex của bài, loại nào được parser lenient chấp nhận?
5. Với locale `ar-EG`, kiểm tra chữ số zero, dấu nhóm, dấu thập phân và format số `1234.5`. Vì sao không thể tự động suy rằng parser `en-US` chấp nhận cùng input?
6. Giải thích khác nhau giữa `Character.isWhitespace(0x202F)` và `Character.isSpaceChar(0x202F)`. `String.strip()` có loại ký tự này ở hai đầu không?
7. Thiết kế parser cho biểu mẫu số tiền theo locale có tối đa hai chữ số lẻ. Hãy phân biệt validation cú pháp, `BigDecimal`, phạm vi hợp lệ và currency của giao dịch.
8. Tại sao không nên định dạng/phân tích mã đơn hàng `"001234"` bằng `NumberFormat`?

**Ghi nhớ:** dấu phân nhóm không đơn giản là phẩy hoặc khoảng trắng; nó có thể là **NBSP `U+00A0`**, **NNBSP `U+202F`**, hoặc ký tự đặc thù hệ chữ số. Chữ số Unicode có thể có giá trị số tương đương ASCII nhưng không cùng mã ký tự và không được mọi parser chấp nhận như nhau. Hãy **xác định locale nguồn, đọc đúng `DecimalFormatSymbols`, kiểm tra parse hết chuỗi và xác thực cú pháp/nghiệp vụ riêng**. Trong dữ liệu trao đổi máy hoặc mã định danh, dùng schema có cú pháp tường minh thay vì phụ thuộc định dạng số của người dùng.

### Tài liệu tham khảo

- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) — cách định dạng và phân tích số theo locale.
- [Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) — phân nhóm, parsing, pattern và `setParseBigDecimal`.
- [Java SE 17 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html) — dấu nhóm, dấu thập phân, chữ số zero.
- [Java SE 17 — ParsePosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html) — vị trí đọc được và lỗi phân tích.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html) — `digit`, `isWhitespace`, `isSpaceChar` và Unicode.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html) — `strip` và thao tác chuỗi Unicode.