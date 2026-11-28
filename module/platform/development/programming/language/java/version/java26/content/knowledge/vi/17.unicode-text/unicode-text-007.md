# NumberFormat.setStrict và việc phân tích dấu âm theo locale

## 1. Mục tiêu và trạng thái API

`NumberFormat` hỗ trợ định dạng và phân tích số theo quy ước của `Locale`. Chuỗi số có thể khác nhau giữa các locale về dấu thập phân, dấu phân nhóm, chữ số, tiền tố/hậu tố tiền tệ và dấu âm.

`NumberFormat.setStrict(boolean)` và `isStrict()` điều khiển chế độ phân tích nghiêm ngặt. Hai phương thức này đã có từ Java 23, tiếp tục được hỗ trợ trên JDK 26 và JDK 27. Đây là API Java SE ổn định, không phải preview hoặc incubator.

Bài học tập trung vào ba điểm:

- **Lenient parsing** ưu tiên đọc được giá trị từ chuỗi có thêm nội dung hoặc ký tự tương đương theo quy tắc loose matching.
- **Strict parsing** yêu cầu chuỗi tuân theo quy ước của format và locale, chẳng hạn grouping, prefix/suffix và dấu âm.
- `U+002D HYPHEN-MINUS` và `U+2212 MINUS SIGN` là hai code point khác nhau dù thường trông gần giống nhau. Lenient parsing có thể coi chúng tương đương; strict parsing theo dấu của locale.

## 2. NumberFormat mặc định phân tích lenient

Theo mặc định, `NumberFormat` phân tích theo chế độ lenient. Mục tiêu của chế độ này là lấy được giá trị số khi chuỗi có phần văn bản không liên quan hoặc một số ký tự có thể được so khớp linh hoạt.

Ví dụ với locale Mỹ:

~~~java
NumberFormat currency = NumberFormat.getCurrencyInstance(Locale.US);

Number value = currency.parse("$1,000.00 was paid");
System.out.println(value);
~~~

Một implementation có thể đọc được giá trị 1000 từ chuỗi có thêm phần văn bản. Điều này hữu ích khi trích số từ văn bản tự do, nhưng không phù hợp nếu chuỗi đầu vào phải là một số hợp lệ hoàn chỉnh theo locale.

Lenient parsing cũng cho phép loose matching một số ký tự. Ví dụ được tài liệu Java nêu là implementation có thể chấp nhận dấu U+2212 thay cho dấu U+002D trong negative prefix.

## 3. Bật strict parsing

Có thể cấu hình trực tiếp trên format nhận từ factory:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(Locale.GERMANY);
format.setStrict(true);

Number value = format.parse("1.234,50");
System.out.println(value);
~~~

`setStrict(true)` yêu cầu parser kiểm tra chuỗi theo quy ước của format. `isStrict()` cho biết trạng thái hiện tại:

~~~java
format.setStrict(true);
System.out.println(format.isStrict()); // true

format.setStrict(false);
System.out.println(format.isStrict()); // false
~~~

Strict mode ảnh hưởng đến parsing, không thay đổi cách `format()` tạo chuỗi.

### 3.1. Chú ý implementation của NumberFormat

`NumberFormat` là lớp trừu tượng. Các phương thức `setStrict()` và `isStrict()` là các phương thức tùy chọn: implementation mặc định của lớp cơ sở ném `UnsupportedOperationException`. Subclass cần override nếu hỗ trợ strict parsing.

Các factory method trả về implementation phụ thuộc locale service provider đang cài đặt; không phải lúc nào cũng là `DecimalFormat` hoặc `CompactNumberFormat`. Vì vậy, code dùng provider tùy chỉnh nên kiểm tra khả năng hỗ trợ:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(locale);

try {
    format.setStrict(true);
} catch (UnsupportedOperationException ex) {
    throw new IllegalStateException(
            "Locale provider không hỗ trợ strict parsing", ex
    );
}
~~~

Với JDK mặc định, các implementation chuẩn như `DecimalFormat` hỗ trợ `setStrict`. Không nên giả định mọi provider bên thứ ba đều triển khai phương thức tùy chọn này.

## 4. Strict parsing kiểm tra những gì?

Với `DecimalFormat`, strict parsing kiểm tra chuỗi có khớp cấu trúc format và quy ước locale hay không.

| Thành phần | Hành vi khi strict |
|---|---|
| Prefix | Phải có prefix được format yêu cầu, ví dụ ký hiệu tiền tệ $ |
| Suffix | Phải có suffix được format yêu cầu, ví dụ % |
| Grouping separator | Nếu bật grouping, các nhóm phải theo đúng grouping size |
| Grouping bị tắt | Không chấp nhận grouping separator trong chuỗi |
| Grouping sau decimal separator | Không hợp lệ |
| Ký tự không mong đợi | Không chấp nhận ký tự ngoài symbol/digit được phép trong phần số |
| Dấu âm | Phải tuân theo negative pattern và dấu mà format sử dụng |

Ví dụ với locale Mỹ và number format:

~~~java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
us.setStrict(true);

us.parse("1,234.5");  // Theo quy ước US
us.parse("1.234,5");  // Sai quy ước decimal/grouping của US
~~~

Với `Locale.GERMANY`, dấu chấm thường là dấu phân nhóm và dấu phẩy là dấu thập phân:

~~~java
NumberFormat germany =
        NumberFormat.getNumberInstance(Locale.GERMANY);
germany.setStrict(true);

germany.parse("1.234,5"); // Theo quy ước Germany
germany.parse("1,234.5"); // Sai quy ước Germany
~~~

Nếu bật grouping, nhóm chữ số phải tuân theo grouping size của format. Nếu tắt grouping bằng `setGroupingUsed(false)`, chuỗi có grouping separator sẽ không hợp lệ trong strict mode.

## 5. ParsePosition và yêu cầu tiêu thụ toàn bộ chuỗi

`parse(String, ParsePosition)` được thiết kế để phân tích từ vị trí bắt đầu và trả về vị trí đã đọc. Theo hợp đồng API, parsing thành công không nhất thiết phải tiêu thụ hết chuỗi; phần còn lại có thể được dành cho lần parse tiếp theo.

Nếu ứng dụng cần xác nhận toàn bộ input là một số hợp lệ, hãy kiểm tra `ParsePosition.getIndex()` bằng độ dài chuỗi.

~~~java
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;

static Number parseEntire(NumberFormat format, String text)
        throws ParseException {

    ParsePosition position = new ParsePosition(0);
    Number value = format.parse(text, position);

    if (value == null || position.getIndex() != text.length()) {
        int errorIndex = position.getErrorIndex() >= 0
                ? position.getErrorIndex()
                : position.getIndex();

        throw new ParseException(
                "Chuỗi số không hợp lệ hoặc còn ký tự thừa",
                errorIndex
        );
    }

    return value;
}
~~~

Dùng với strict mode:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(Locale.US);
format.setStrict(true);

Number amount = parseEntire(format, "1,234.50");
~~~

Nếu input là chuỗi có thêm hậu tố, chẳng hạn "1,234.50 USD", helper trên từ chối khi parser không tiêu thụ hết chuỗi. Cách này làm rõ điều kiện xác thực và vị trí lỗi.

## 6. Dấu âm là ký tự Unicode theo locale

### 6.1. Những ký tự thường bị nhầm

| Ký tự | Code point | Tên Unicode | Vai trò |
|---|---|---|---|
| - | U+002D | HYPHEN-MINUS | Dấu gạch nối/dấu trừ ASCII thường dùng trong chuỗi kỹ thuật |
| − | U+2212 | MINUS SIGN | Dấu trừ toán học |
| ‐ | U+2010 | HYPHEN | Dấu nối |
| – | U+2013 | EN DASH | Dấu gạch ngang dài hơn |

U+002D và U+2212 có thể hiển thị gần giống nhau nhưng không bằng nhau khi so sánh chuỗi. U+2010 và U+2013 cũng không phải dấu âm chỉ vì hình dáng giống dấu trừ.

### 6.2. Lấy dấu âm thực tế từ DecimalFormatSymbols

Không hard-code dấu trừ ASCII để đại diện cho mọi locale. Hãy đọc symbol do locale provider cung cấp:

~~~java
NumberFormat numberFormat =
        NumberFormat.getNumberInstance(Locale.US);

if (numberFormat instanceof DecimalFormat decimalFormat) {
    DecimalFormatSymbols symbols =
            decimalFormat.getDecimalFormatSymbols();

    char minusSign = symbols.getMinusSign();

    System.out.printf(
            "Minus sign: %s, code point: U+%04X%n",
            minusSign,
            (int) minusSign
    );
}
~~~

`DecimalFormatSymbols.getMinusSign()` trả về ký tự mà format dùng để biểu diễn dấu âm. Các symbol khác cũng lấy từ cùng đối tượng:

~~~java
char decimalSeparator = symbols.getDecimalSeparator();
char groupingSeparator = symbols.getGroupingSeparator();
char zeroDigit = symbols.getZeroDigit();
~~~

Các symbol này có thể khác theo locale, numbering system và locale provider. Unicode locale extensions như `nu` có thể thay numbering system; khả năng hỗ trợ extension phụ thuộc locale service provider.

### 6.3. Dấu âm trong DecimalFormat pattern

Trong non-localized pattern, dấu U+002D biểu thị vị trí của negative prefix. Khi pattern không khai báo negative subpattern riêng, `DecimalFormat` tạo negative subpattern bằng cách thêm dấu âm vào positive pattern.

Ví dụ:

~~~java
DecimalFormat format = new DecimalFormat("0.00");
~~~

Negative value được định dạng với dấu âm theo `DecimalFormatSymbols` của format. Khi dùng factory theo locale, pattern và symbols được lấy từ locale data.

Có thể định nghĩa negative subpattern riêng, chẳng hạn:

~~~java
DecimalFormat accounting = new DecimalFormat("#,##0.00;(#,##0.00)");
~~~

Trong ví dụ này, số âm được biểu diễn bằng dấu ngoặc thay vì dấu trừ. Strict parsing phải tuân theo negative prefix/suffix đã cấu hình; không nên giả định mọi số âm đều bắt đầu bằng một ký tự minus.

## 7. Lenient và strict khi gặp U+2212/U+002D

Giả sử format của locale đang dùng U+002D. Input từ một tài liệu PDF có thể chứa U+2212. Hai chuỗi nhìn gần giống nhau:

~~~java
String asciiMinus = "-1234.5";        // U+002D
String unicodeMinus = "\u22121234.5"; // U+2212
~~~

Trong lenient mode, `DecimalFormat` dùng loose matching của LDML cho dấu âm trong negative subpattern. Vì vậy, implementation có thể chấp nhận dấu U+2212 như một biến thể của U+002D.

Trong strict mode, parser yêu cầu dấu theo quy ước của format. Nếu locale đang dùng U+002D thì U+2212 không phải cùng ký tự; nếu locale dùng U+2212 thì U+002D không phải cùng ký tự.

Ví dụ kiểm tra dựa trên symbol thực tế:

~~~java
Locale locale = Locale.US;

NumberFormat numberFormat = NumberFormat.getNumberInstance(locale);
if (!(numberFormat instanceof DecimalFormat decimalFormat)) {
    throw new IllegalStateException("Cần DecimalFormat để kiểm tra symbol");
}

DecimalFormatSymbols symbols = decimalFormat.getDecimalFormatSymbols();
decimalFormat.setGroupingUsed(false);

char localeMinus = symbols.getMinusSign();
char decimal = symbols.getDecimalSeparator();

String localeMinusInput =
        "" + localeMinus + "1234" + decimal + "5";

char alternateMinus = localeMinus == '\u2212'
        ? '\u002D'
        : '\u2212';

String alternateInput =
        "" + alternateMinus + "1234" + decimal + "5";

decimalFormat.setStrict(true);
Number strictValue = parseEntire(decimalFormat, localeMinusInput);

// Nếu alternateMinus khác dấu của locale, strict parsing phải từ chối.
try {
    parseEntire(decimalFormat, alternateInput);
    throw new AssertionError("Strict mode đã chấp nhận dấu không theo locale");
} catch (ParseException expected) {
    System.out.println("Dấu âm khác locale bị từ chối");
}

decimalFormat.setStrict(false);
// Lenient mode có thể chấp nhận alternateMinus theo loose matching.
try {
    Number lenientValue = parseEntire(decimalFormat, alternateInput);
    System.out.println("Lenient mode chấp nhận dấu âm thay thế: " + lenientValue);
} catch (ParseException notAcceptedByProvider) {
    System.out.println("Locale provider này không chấp nhận biến thể dấu âm");
}
~~~

Kết quả lenient phụ thuộc loose-matching implementation và locale data. Nếu ứng dụng cần hợp đồng input chặt chẽ, hãy bật strict mode và chỉ nhận ký tự được format quy định.

Không nên thay thế mọi dấu gạch ngang Unicode bằng dấu trừ ASCII. Việc chuẩn hóa mù có thể biến dấu nối trong văn bản thành dấu âm. Nếu nghiệp vụ chấp nhận một tập biến thể cụ thể, hãy xác định rõ code point được phép rồi chuẩn hóa đúng các ký tự đó trước khi parse.

## 8. Strict mode và grouping/decimal separator

Dấu âm không phải khác biệt locale duy nhất. Dấu phân nhóm và dấu thập phân cũng quyết định chuỗi hợp lệ.

| Locale | Ví dụ số theo locale | Dấu thập phân | Dấu phân nhóm |
|---|---|---|---|
| `Locale.US` | 1,234.50 | . | , |
| `Locale.GERMANY` | 1.234,50 | , | . |
| `Locale.FRANCE` | Phụ thuộc locale data của runtime | Lấy từ symbols | Có thể là khoảng trắng Unicode |

Không tự thay dấu phẩy thành dấu chấm bằng thao tác chuỗi. Hãy để locale-specific parser đọc đúng symbol.

Có thể in các code point để chẩn đoán input lấy từ Excel, PDF, trình duyệt hoặc hệ thống khác:

~~~java
static void printSymbols(Locale locale) {
    DecimalFormatSymbols symbols =
            DecimalFormatSymbols.getInstance(locale);

    System.out.printf(
            "%s: minus=U+%04X, decimal=U+%04X, grouping=U+%04X%n",
            locale,
            (int) symbols.getMinusSign(),
            (int) symbols.getDecimalSeparator(),
            (int) symbols.getGroupingSeparator()
    );
}
~~~

Một số locale sử dụng non-breaking space hoặc narrow no-break space làm grouping separator. Hai ký tự khoảng trắng có thể trông giống nhau nhưng có code point khác nhau. Strict parsing giúp phát hiện input không tuân theo symbol và grouping convention mà format đang dùng.

## 9. Currency format và accounting style

Currency format có thể có prefix/suffix khác nhau giữa locale. Một số locale có accounting style: số âm được bao trong dấu ngoặc thay vì có dấu trừ.

Ví dụ:

~~~java
Locale accountingLocale =
        Locale.forLanguageTag("en-US-u-cf-account");

NumberFormat currency =
        NumberFormat.getCurrencyInstance(accountingLocale);

currency.setStrict(true);
~~~

Locale extension `cf-account` yêu cầu accounting currency style nếu locale provider hỗ trợ. Trong trường hợp này, chuỗi âm có thể được định dạng như ($123.45) thay vì -$123.45.

Strict parsing phải khớp prefix/suffix của currency format thực tế. Không tự thêm dấu âm vào đầu chuỗi currency khi format đang dùng accounting pattern.

## 10. Kiểu Number trả về và độ chính xác

Mặc định, `DecimalFormat.parse()` có thể trả về `Long` nếu giá trị nguyên phù hợp; trong các trường hợp khác có thể trả về `Double`. Nếu cần giữ chính xác phần thập phân, có thể bật `setParseBigDecimal(true)` khi format là `DecimalFormat`:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(Locale.GERMANY);

if (format instanceof DecimalFormat decimalFormat) {
    decimalFormat.setStrict(true);
    decimalFormat.setParseBigDecimal(true);

    Number parsed = parseEntire(decimalFormat, "1.234,50");
    BigDecimal amount = (BigDecimal) parsed;
}
~~~

`setParseBigDecimal` là phương thức của `DecimalFormat`, không phải của `NumberFormat`. Kiểm tra kiểu trước khi gọi.

Có một trường hợp đặc biệt cần lưu ý: khi parse negative zero:

- `BigDecimal(0)` được trả về nếu `isParseBigDecimal()` là `true`; dấu âm của zero bị mất.
- `Long(0)` được trả về nếu parse integer only.
- `Double(-0.0)` được trả về nếu parse BigDecimal và parse integer only đều tắt.

Nếu nghiệp vụ cần phân biệt -0.0 với 0.0, không chuyển kết quả sang `BigDecimal` trước khi bảo toàn thông tin dấu âm zero.

## 11. Những cấu hình parsing dễ bị hiểu nhầm

### 11.1. setParseIntegerOnly không phải strict validation

`setParseIntegerOnly(true)` chỉ yêu cầu parser lấy phần nguyên và dừng ở dấu thập phân. Ví dụ 123.45 theo locale Mỹ có thể được parse thành 123.

Nếu nghiệp vụ yêu cầu số nguyên thuần, hãy kết hợp strict parsing và kiểm tra toàn bộ input; đừng dùng `setParseIntegerOnly` như một cách từ chối phần thập phân.

### 11.2. setGroupingUsed(false) ảnh hưởng cả parse

`setGroupingUsed(false)` không chỉ tắt dấu phân nhóm khi format. Nó còn làm parser không mong đợi grouping separator. Trong strict mode, chuỗi vẫn có dấu phân nhóm sẽ bị từ chối.

### 11.3. Strict không thay thế kiểm tra nghiệp vụ

Strict parsing kiểm tra hình thức theo locale, không xác nhận:

- Giá trị có nằm trong miền nghiệp vụ hay không.
- Số tiền có lớn hơn 0 hoặc nằm trong hạn mức hay không.
- Đơn vị tiền tệ có đúng với giao dịch hay không.
- Số chữ số thập phân có phù hợp quy tắc nghiệp vụ hay không.
- Dữ liệu có hợp lệ về quyền truy cập hoặc nguồn gốc hay không.

Sau khi parse, ứng dụng vẫn cần kiểm tra range, scale, sign và các ràng buộc nghiệp vụ.

### 11.4. NumberFormat không thread-safe

`NumberFormat` và `DecimalFormat` nhìn chung không synchronized. Không chia sẻ cùng một instance cho nhiều thread nếu không có đồng bộ hóa bên ngoài. Tốt hơn là tạo instance riêng theo request/thread hoặc dùng cơ chế quản lý formatter an toàn.

## 12. Ví dụ hoàn chỉnh: parse số theo locale và kiểm tra dấu âm

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public class StrictLocaleNumberParsing {
    static Number parseEntire(NumberFormat format, String input)
            throws ParseException {
        ParsePosition position = new ParsePosition(0);
        Number value = format.parse(input, position);

        if (value == null || position.getIndex() != input.length()) {
            int errorIndex = position.getErrorIndex() >= 0
                    ? position.getErrorIndex()
                    : position.getIndex();

            throw new ParseException("Invalid localized number", errorIndex);
        }

        return value;
    }

    static DecimalFormat newStrictDecimalFormat(Locale locale) {
        NumberFormat format = NumberFormat.getNumberInstance(locale);

        if (!(format instanceof DecimalFormat decimalFormat)) {
            throw new IllegalStateException(
                    "Locale provider không trả về DecimalFormat"
            );
        }

        decimalFormat.setStrict(true);
        decimalFormat.setParseBigDecimal(true);
        return decimalFormat;
    }

    public static void main(String[] args) throws Exception {
        Locale locale = Locale.GERMANY;
        DecimalFormat format = newStrictDecimalFormat(locale);

        DecimalFormatSymbols symbols =
                format.getDecimalFormatSymbols();

        char minus = symbols.getMinusSign();
        char decimal = symbols.getDecimalSeparator();

        String valid = "" + minus + "1234" + decimal + "50";
        BigDecimal value = (BigDecimal) parseEntire(format, valid);

        System.out.println("Locale: " + locale);
        System.out.printf("Locale minus: U+%04X%n", (int) minus);
        System.out.println("Parsed value: " + value);

        String invalidGrouping = "12.34,50";

        try {
            parseEntire(format, invalidGrouping);
            throw new AssertionError("Grouping sai đã được chấp nhận");
        } catch (ParseException expected) {
            System.out.println("Grouping sai bị từ chối");
        }

        String trailingText = valid + " EUR";

        try {
            parseEntire(format, trailingText);
            throw new AssertionError("Ký tự thừa đã được chấp nhận");
        } catch (ParseException expected) {
            System.out.println("Ký tự thừa bị từ chối");
        }
    }
}
~~~

Ví dụ dùng `Locale.GERMANY` để parser tự lấy dấu âm và dấu thập phân từ symbols. Không giả định code point của dấu âm hoặc separator giống nhau giữa các runtime.

## 13. Bộ kiểm thử nên có

| Nhóm | Input | Mục đích |
|---|---|---|
| Locale đúng | 1,234.50 với US | Chấp nhận grouping/decimal đúng |
| Locale khác | 1.234,50 với US | Từ chối quy ước của locale khác |
| Grouping sai | 12,34.50 với US | Từ chối grouping size không đúng |
| Grouping bị tắt | Có dấu grouping trong input | Từ chối khi `setGroupingUsed(false)` |
| Dấu âm locale | Dùng `getMinusSign()` | Chấp nhận dấu âm đúng |
| Unicode minus khác locale | Đổi U+002D ↔ U+2212 | Strict từ chối dấu khác locale |
| Lenient minus | Cùng input có dấu thay thế | Kiểm tra loose matching |
| Prefix/suffix | Currency hoặc percent | Bắt buộc có prefix/suffix theo format |
| Literal thừa | 123.45abc | Không bỏ qua hậu tố |
| Negative zero | -0 | Kiểm tra yêu cầu bảo toàn dấu âm |
| Unicode digits | Chữ số thuộc numbering system khác | Xác minh locale/numbering system |
| Provider khác | Locale service provider tùy chỉnh | Kiểm tra hỗ trợ `setStrict` |

Kết quả test locale phụ thuộc JDK build và locale service provider. Nên chạy trên chính runtime production, không hard-code output của một máy phát triển làm chuẩn cho tất cả môi trường.

## 14. Chọn parser theo loại dữ liệu

| Dữ liệu | Cách tiếp cận |
|---|---|
| Người dùng nhập số theo ngôn ngữ/locale giao diện | `NumberFormat` theo locale, strict mode và kiểm tra toàn chuỗi |
| Người dùng nhập tiền tệ có ký hiệu | `getCurrencyInstance(locale)` với strict mode |
| Import CSV có quy ước locale đã biết | Chọn locale rõ ràng, kiểm tra grouping và decimal separator |
| JSON/API/wire format dùng dấu chấm và cú pháp cố định | Dùng parser theo format giao thức, chẳng hạn `BigDecimal(String)` cho decimal canonical |
| Số nguyên ASCII theo giao thức | Dùng `Integer.parseInt` hoặc `Long.parseLong` |
| Văn bản tự do cần trích số | Lenient parsing có kiểm soát và xác minh kết quả theo ngữ cảnh |

Không dùng locale của máy chủ làm mặc định ngầm cho dữ liệu lưu trữ hoặc giao tiếp giữa dịch vụ. Với giao thức máy-máy, định nghĩa format bất biến; với giao diện người dùng, chọn locale theo người dùng hoặc theo cấu hình nghiệp vụ.

## 15. Kết luận

`NumberFormat.setStrict(true)` giúp parser kiểm tra chuỗi số theo quy ước của format và locale. Nó đặc biệt quan trọng khi ứng dụng cần xác thực dữ liệu nhập thay vì chỉ cố trích một giá trị số từ văn bản.

Các điểm cần nhớ:

- `setStrict` và `isStrict` đã có từ Java 23, vẫn dùng được trên JDK 26/27 và là API ổn định.
- Lenient parsing mặc định cho phép một số loose matching, bao gồm biến thể dấu âm U+2212 và U+002D.
- Strict parsing kiểm tra prefix/suffix, grouping, separator, ký tự và dấu âm theo locale.
- Lấy dấu âm từ `DecimalFormatSymbols.getMinusSign()`; không hard-code dấu trừ ASCII cho mọi locale.
- U+2212 MINUS SIGN khác U+002D HYPHEN-MINUS; U+2010 HYPHEN và U+2013 EN DASH cũng không phải cùng ký tự.
- Dùng `ParsePosition` và kiểm tra `getIndex()` để chắc chắn toàn bộ input được tiêu thụ.
- Với dữ liệu thập phân cần chính xác, cân nhắc `DecimalFormat.setParseBigDecimal(true)` và hiểu tác động của negative zero.
- Kiểm tra provider có hỗ trợ strict mode; implementation không hỗ trợ có thể ném `UnsupportedOperationException`.
- Formatter không thread-safe; không chia sẻ instance không đồng bộ giữa các thread.

Strict parsing giúp xác thực hình thức số theo locale. Sau khi parse thành công, ứng dụng vẫn cần kiểm tra miền giá trị, độ chính xác và quy tắc nghiệp vụ.

## Tài liệu tham khảo chính thức

- [NumberFormat — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html)
- [DecimalFormat — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/DecimalFormat.html)
- [DecimalFormatSymbols — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/DecimalFormatSymbols.html)
- [NumberFormat — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/NumberFormat.html)
- [DecimalFormat — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/DecimalFormat.html)
- [New API List — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/new-list.html)
- [Unicode Locale Data Markup Language (LDML), Numbers](https://www.unicode.org/reports/tr35/tr35-78/tr35-numbers.html)

