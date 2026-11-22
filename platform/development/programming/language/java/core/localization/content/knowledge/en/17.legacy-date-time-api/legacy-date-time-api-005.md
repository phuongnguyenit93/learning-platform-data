# setLenient và ParsePosition khi phân tích ngày trong Java

Trong các ứng dụng Java lâu năm, **java.text.DateFormat** và **java.text.SimpleDateFormat** thường được dùng để đổi chuỗi như **28/10/2026** thành **java.util.Date**. Việc gọi **parse(...)** tưởng chừng đơn giản nhưng có ba câu hỏi hoàn toàn khác nhau:

1. **Ngày lịch có hợp lệ không?** Chẳng hạn 31/02/2024 là ngày không tồn tại.
2. **Parser đã đọc hết chuỗi chưa?** Chẳng hạn **28/10/2026XYZ** có thể được hiểu thành ngày hợp lệ dù còn đuôi **XYZ**.
3. **Chuỗi có đúng hợp đồng đầu vào không?** Ví dụ người dùng nhập **1/2/2024** trong khi hệ thống bắt buộc **dd/MM/yyyy** với hai chữ số ngày/tháng.

Hai công cụ quan trọng để trả lời là **DateFormat.setLenient(boolean)** và **java.text.ParsePosition**. **setLenient(false)** giúp ngăn Calendar tự sửa ngày/giờ ngoài miền hợp lệ; **ParsePosition** cho biết parser đã đọc đến vị trí nào và thông tin lỗi. Tuy nhiên, **kết hợp hai công cụ vẫn chưa tự tạo thành validator cú pháp hoàn chỉnh**: tùy yêu cầu, cần kiểm tra định dạng, độ dài, locale, múi giờ và kiểu dữ liệu.

Bài học này tập trung vào API ngày giờ cũ (legacy) trong Java 17+, giải thích hành vi, cách viết một parser có kiểm tra chặt, ví dụ chạy được và hướng chuyển sang **java.time** khi thiết kế mới.

## 1. DateFormat, SimpleDateFormat, Calendar, Date có nhiệm vụ gì?

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| **DateFormat** | Lớp cơ sở định dạng/phân tích ngày giờ có tính locale | Là **abstract class**; cung cấp parse, format, setLenient |
| **SimpleDateFormat** | DateFormat dựa trên chuỗi pattern như **dd/MM/yyyy** | Mutable, không an toàn để chia sẻ đồng thời |
| **Calendar** | Xử lý các trường ngày, tháng, năm, giờ và tính toán lịch | Thuộc tính **lenient** nằm ở Calendar |
| **TimeZone** | Xác định cách diễn giải giờ địa phương thành thời điểm | Tách biệt với Locale |
| **java.util.Date** | Biểu diễn một thời điểm (instant) bằng độ chính xác mili giây | Không chứa pattern, Locale hoặc TimeZone |
| **ParsePosition** | Vị trí bắt đầu, vị trí đã đọc và vị trí lỗi | Chỉ số tính theo vị trí ký tự trong chuỗi Java |
| **ParseException** | Ngoại lệ của overload **parse(String)** khi phân tích thất bại | Không thay thế kiểm tra phần đuôi |
| **Locale** | Ngữ cảnh ngôn ngữ/vùng của formatter | Đặc biệt quan trọng khi pattern có tên tháng/ngày |

Sơ đồ khái niệm:

~~~text
String "31/02/2024"
          |
          v
SimpleDateFormat("dd/MM/yyyy", locale)
          |
          v
      Calendar
          |
    setLenient(?)
          |
          v
   Date hoặc lỗi
          |
          v
      Instant
~~~

Pattern **dd/MM/yyyy** mô tả các trường và dấu phân cách đầu vào; **Calendar** quyết định cách xử lý trường bất thường, còn **TimeZone** quyết định mốc thời gian tương ứng khi ngày/giờ đã được nhận.

**Không nhầm java.util.Date với LocalDate.** Khi chỉ xử lý “ngày sinh 28/10/2026”, một **LocalDate** là mô hình phù hợp hơn vì không có thành phần thời điểm/múi giờ; trong API cũ, Date được tạo ra từ việc phân tích ngày sẽ đại diện cho thời điểm ở đầu ngày theo TimeZone của formatter.

## 2. setLenient là gì?

**DateFormat.setLenient(boolean)** thiết lập khả năng **Calendar nới lỏng việc diễn giải các giá trị trường**. Khi ở chế độ lenient, Calendar có thể tự chuẩn hóa các giá trị ngoài miền, ví dụ “ngày 31 tháng 2” thành một ngày trong tháng 3. Với **setLenient(false)**, Calendar kiểm tra trường và không chấp nhận tổ hợp ngày/giờ không hợp lệ.

Ví dụ:

~~~java
SimpleDateFormat format = new SimpleDateFormat(
        "dd/MM/yyyy", Locale.US);
format.setTimeZone(TimeZone.getTimeZone("UTC"));

format.setLenient(true);
Date rolled = format.parse("31/02/2024");

format.setLenient(false);
// Cùng chuỗi 31/02/2024 sẽ không được chấp nhận như ngày lịch.
~~~

Đây là đoạn **minh họa**, cần import **java.text.SimpleDateFormat**, **java.text.ParseException**, **java.util.Locale**, **java.util.TimeZone**, **java.util.Date** và đặt các lệnh trong phương thức có khai báo hoặc xử lý ParseException.

**Chế độ lenient** trả lời: “Có chấp nhận việc chuẩn hóa giá trị ngày/giờ ngoài miền không?” Nó **không** trả lời: “Mọi ký tự trong chuỗi đã được đọc chưa?” hoặc “Người dùng có viết đúng chính xác hai chữ số cho ngày/tháng chưa?”.

**Nên gọi setLenient(false) tường minh** cho dữ liệu người dùng đòi hỏi ngày hợp lệ. Các Calendar thông thường được tạo theo mặc định nới lỏng, nhưng không nên dựa vào mặc định ngầm của thư viện hoặc cấu hình đã bị code khác sửa.

### 2.1. setLenient là thuộc tính của Calendar

DateFormat lưu một Calendar dùng khi định dạng và phân tích. **DateFormat.setLenient(false)** chuyển tiếp cấu hình đến **Calendar.setLenient(false)** của formatter; **isLenient()** phản ánh thuộc tính này.

~~~java
format.setLenient(false);
boolean strictCalendar = !format.isLenient();
~~~

Nếu một formatter đã được cấu hình rồi lại **setCalendar(...)** bằng Calendar mới, trạng thái lenient có thể thay đổi theo Calendar mới. Thứ tự cài đặt có ý nghĩa: tạo formatter, thiết lập Calendar/TimeZone nếu cần, rồi bảo đảm **setLenient(false)** vẫn đang có hiệu lực trước khi parse.

### 2.2. Ví dụ ngày tràn miền

Năm **2024** là năm nhuận, tháng 2 có **29 ngày**. Ngày **31/02/2024** vượt giới hạn hai ngày:

~~~text
31/02/2024  --lenient-->  02/03/2024
31/02/2024  --strict-->   không hợp lệ
~~~

Đây là một phép **chuẩn hóa lịch** khi lenient, không phải việc đổi cách trình bày. Nếu hệ thống hồ sơ hoặc thanh toán chấp nhận nó như một ngày đúng, dữ liệu nghiệp vụ có thể âm thầm bị đổi mà không ai nhận ra.

Các giá trị như tháng 13, ngày 0, giờ 25 cũng có thể được Calendar nới lỏng thành một thời điểm khác trong các trường hợp thích hợp. Không nên xem cơ chế đó là cách “sửa lỗi người dùng” trừ khi sản phẩm có yêu cầu rõ ràng.

## 3. parse(String) khác parse(String, ParsePosition) như thế nào?

**DateFormat** hỗ trợ hai overload quan trọng:

~~~java
Date a = formatter.parse(text);

ParsePosition position = new ParsePosition(0);
Date b = formatter.parse(text, position);
~~~

Đoạn minh họa cần **DateFormat hoặc SimpleDateFormat formatter**, **String text**, import **java.util.Date**, **java.text.ParsePosition**; overload thứ nhất cần xử lý **ParseException**.

| Đặc điểm | **parse(String)** | **parse(String, ParsePosition)** |
| --- | --- | --- |
| Điểm bắt đầu | Đầu chuỗi | **position.getIndex()** |
| Thành công | Trả Date | Trả Date và cập nhật **position.index** |
| Thất bại | Ném **ParseException** | Thường trả **null** và thiết lập **errorIndex** |
| Biết vị trí cuối | Không trả trực tiếp | **position.getIndex()** |
| Bảo đảm đọc hết chuỗi? | **Không** | **Không**, nhưng caller có thể tự kiểm tra |
| Phù hợp | Trường hợp parse đơn giản | Validator, parser chuỗi phức hợp, xử lý lỗi chi tiết |

Tài liệu API DateFormat cho phép parse chỉ tiêu thụ một **tiền tố** của chuỗi. Vì thế:

~~~text
28/10/2026XYZ
^^^^^^^^^^
10 ký tự cấu thành ngày; "XYZ" có thể còn dư
~~~

Dù **setLenient(false)**, parse có thể trả về Date hợp lệ cho phần **28/10/2026** mà bỏ qua đuôi. Chỉ kiểm tra “không bị ParseException” sẽ không chứng minh người dùng nhập đúng toàn bộ dữ liệu.

## 4. ParsePosition: index và errorIndex

**ParsePosition** chứa:

- **getIndex()**: vị trí bắt đầu trước parse; sau khi thành công, thường trỏ ngay **sau ký tự cuối cùng đã được tiêu thụ**.
- **getErrorIndex()**: vị trí lỗi nếu parser ghi nhận lỗi; giá trị ban đầu thường là **-1**.
- **setIndex(int)** và **setErrorIndex(int)**: thay các vị trí bằng code; tiện khi xây dựng parser nâng cao, nhưng dễ nhầm nếu tái sử dụng object.

Ví dụ:

~~~java
String text = "28/10/2026XYZ";
ParsePosition position = new ParsePosition(0);

Date value = formatter.parse(text, position);

if (value != null && position.getIndex() == text.length()) {
    // Đã parse thành công và tiêu thụ hết chuỗi.
}
~~~

**Lưu ý:** chỉ số trong Java String là offset của **đơn vị UTF-16**, không phải số Unicode code point. Với chuỗi ngày ASCII như ví dụ không có sự khác biệt, nhưng parser tự viết cho chữ bản địa và ký tự ngoài BMP cần nắm rõ điều này.

### 4.1. Không chỉ kiểm tra errorIndex

**errorIndex = -1** không bảo đảm toàn chuỗi hợp lệ: một lần parse thành công có thể không đặt lỗi, nhưng còn phần dư. Điều kiện cơ bản là:

~~~java
value != null
    && position.getErrorIndex() < 0
    && position.getIndex() == text.length()
~~~

Với **ParsePosition** mới cho mỗi lần parse, điều kiện này bảo đảm parser không ghi nhận lỗi và đã đi đến cuối chuỗi theo quy tắc của chính nó. Tuy nhiên, đây vẫn chưa phải kiểm tra độ rộng trường hay chính xác từng ký tự dấu phân cách theo hợp đồng UI.

### 4.2. Parser thất bại

Khi parse với ParsePosition thất bại, chương trình thường nhận **null** và **errorIndex** có thể chỉ vị trí nơi parser không thể tiếp tục. Hãy kiểm tra **null** trước khi gọi **toInstant()**, **getTime()**, hoặc phương thức trên kết quả.

Không nên ghi cứng “errorIndex luôn bằng 0” hay một vị trí cụ thể cho mọi lỗi: chi tiết phụ thuộc pattern, chuỗi và thuật toán parser.

## 5. Ví dụ Java 17+ đầy đủ: lenient, strict và phần đuôi

**File LegacyDateParsingDemo.java**

~~~java
import java.text.ParseException;
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyDateParsingDemo {
    private static SimpleDateFormat newFormatter() {
        SimpleDateFormat format = new SimpleDateFormat(
                "dd/MM/yyyy", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        return format;
    }

    public static void main(String[] args) throws ParseException {
        SimpleDateFormat format = newFormatter();

        format.setLenient(true);
        Date rolled = format.parse("31/02/2024");
        System.out.println(
                "lenient=" + rolled.toInstant());

        format.setLenient(false);
        try {
            format.parse("31/02/2024");
            System.out.println("strict=accepted");
        } catch (ParseException ex) {
            System.out.println("strict=rejected");
        }

        String withTail = "28/10/2026XYZ";
        Date prefix = format.parse(withTail);
        System.out.println(
                "parse(String)=" + prefix.toInstant());

        ParsePosition pos = new ParsePosition(0);
        Date parsed = format.parse(withTail, pos);

        System.out.println("parse(position)="
                + (parsed == null ? "null" : parsed.toInstant())
                + ", index=" + pos.getIndex()
                + ", length=" + withTail.length());

        ParsePosition validPos = new ParsePosition(0);
        String exact = "28/10/2026";
        Date valid = format.parse(exact, validPos);

        System.out.println("complete="
                + (valid != null
                && validPos.getIndex() == exact.length()));
    }
}
~~~

Lưu **LegacyDateParsingDemo.java**, chạy:

~~~bash
javac -encoding UTF-8 LegacyDateParsingDemo.java
java LegacyDateParsingDemo
~~~

**Stdout** cho ví dụ xác định pattern, Locale.US và UTC:

~~~text
lenient=2024-03-02T00:00:00Z
strict=rejected
parse(String)=2026-10-28T00:00:00Z
parse(position)=2026-10-28T00:00:00Z, index=10, length=13
complete=true
~~~

Diễn giải:

1. **lenient=true** cho phép Calendar chuẩn hóa **31/02/2024** thành **02/03/2024**.
2. **lenient=false** từ chối ngày lịch không tồn tại.
3. **parse(String)** với chuỗi có hậu tố **XYZ** vẫn có thể trả về Date, vì nó đọc được tiền tố ngày đúng.
4. **parse(String, ParsePosition)** cho thấy **index=10**, nhỏ hơn **length=13**; ứng dụng có thể phát hiện phần dư.
5. Với chuỗi **28/10/2026**, parse thành công và **index == text.length()**, do đó kiểm tra “tiêu thụ hết” trả **true**.

Việc cấu hình UTC giúp **Date.toInstant()** trong ví dụ có kết quả dự đoán được. Nếu bỏ setTimeZone, cùng ngày lịch nhưng default timezone khác nhau có thể thành Instant khác nhau trên dev và server.

**Đây là ví dụ quan trọng nhất:** **strict Calendar validation không đồng nghĩa strict toàn chuỗi**.

## 6. parse(String) và ParseException không kiểm tra hết input

Overload **parse(String)** ném **ParseException** khi không thể đọc một ngày phù hợp từ đầu chuỗi, nhưng **không mặc nhiên yêu cầu toàn chuỗi chỉ chứa ngày**. Đó là một thiết kế phù hợp với parser có khả năng đọc một phần văn bản, song có thể không phù hợp với trường nhập liệu chính xác.

Ví dụ:

~~~text
"28/10/2026"      -> ngày hợp lệ
"28/10/2026XYZ"   -> tiền tố ngày hợp lệ, còn XYZ
"31/02/2024"      -> lịch không hợp lệ khi setLenient(false)
"1/2/2024"        -> có thể được nhận dù UI yêu cầu 2 chữ số
~~~

Không nên giải quyết các trường hợp bằng một **try/catch(ParseException)** đơn giản. Khi muốn đọc toàn bộ đầu vào, dùng ParsePosition; khi muốn chính xác từng ký tự, bổ sung kiểm tra cú pháp.

**ParseException.getErrorOffset()** là vị trí lỗi tương ứng từ overload ném exception; đó không phải vị trí đã đọc khi parse thành công. Nếu muốn biết chính xác parser đã tiêu thụ bao nhiêu khi thành công, hãy dùng ParsePosition thay vì cố đọc error offset.

## 7. setLenient(false) vẫn không nhất thiết bắt đúng độ rộng dd/MM/yyyy

Trong **SimpleDateFormat**, các ký hiệu như **dd**, **MM**, **yyyy** mô tả định dạng khi xuất và cấu trúc khi phân tích. Không nên nhầm chúng với validator kiểu “bắt buộc chính xác 2 chữ số ngày, 2 chữ số tháng và 4 chữ số năm” trong mọi trường hợp.

Chẳng hạn, một parser có thể đọc **1/2/2024** dù pattern là **dd/MM/yyyy** và Calendar strict. Vì ngày 1 tháng 2 hoàn toàn hợp lệ, **setLenient(false)** không có lý do để bác bỏ chỉ do người dùng không đệm số 0.

Nếu hợp đồng đầu vào bắt buộc dạng:

~~~text
dd/MM/yyyy
01/02/2024   hợp lệ
1/2/2024     không hợp lệ theo độ rộng
01-02-2024   không hợp lệ theo dấu phân cách
29/02/2023   không hợp lệ theo ngày lịch
~~~

thì cần **cả**:

1. Kiểm tra chuỗi có đúng cấu trúc ký tự.
2. Parse theo Calendar strict.
3. Kiểm tra ParsePosition tiêu thụ hết.
4. Nếu cần, format lại và so sánh để loại các biểu diễn khác chuẩn.

Regex hoặc validator cú pháp phải phản ánh chính xác hợp đồng đầu vào. Đối với đầu vào chỉ chấp nhận ASCII, ví dụ regex **[0-9]{2}/[0-9]{2}/[0-9]{4}** thể hiện rõ yêu cầu hơn việc trông chờ độ rộng của SimpleDateFormat.

## 8. Xây dựng một hàm kiểm tra ngày đúng toàn bộ chuỗi

Ví dụ dưới đây kiểm tra dạng **dd/MM/yyyy** ASCII, lịch hợp lệ, không có phần dư và biểu diễn chuẩn hóa. Nó được thiết kế như ví dụ legacy cho hệ thống còn dùng DateFormat; với ứng dụng mới, phần cuối bài giới thiệu **java.time** gọn hơn.

**File StrictLegacyDateInput.java**

~~~java
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.regex.Pattern;

public class StrictLegacyDateInput {
    private static final Pattern SHAPE = Pattern.compile(
            "[0-9]{2}/[0-9]{2}/[0-9]{4}");

    public static boolean isValid(String text) {
        if (text == null || !SHAPE.matcher(text).matches()) {
            return false;
        }

        SimpleDateFormat format = new SimpleDateFormat(
                "dd/MM/yyyy", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        format.setLenient(false);

        ParsePosition position = new ParsePosition(0);
        Date parsed = format.parse(text, position);

        return parsed != null
                && position.getErrorIndex() < 0
                && position.getIndex() == text.length()
                && text.equals(format.format(parsed));
    }

    public static void main(String[] args) {
        System.out.println(isValid("29/02/2024"));
        System.out.println(isValid("29/02/2023"));
        System.out.println(isValid("01/02/2024"));
        System.out.println(isValid("1/2/2024"));
        System.out.println(isValid("01/02/2024XYZ"));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StrictLegacyDateInput.java
java StrictLegacyDateInput
~~~

Stdout:

~~~text
true
false
true
false
false
~~~

Từng bước kiểm tra:

- **SHAPE.matcher(...).matches()** buộc toàn chuỗi khớp đúng mẫu hai chữ số ngày, hai chữ số tháng, bốn chữ số năm và hai dấu **/**.
- **setLenient(false)** chặn ngày 29/02 trong năm không nhuận.
- **position.getIndex() == text.length()** xác nhận parser đã đọc hết chuỗi.
- **text.equals(format.format(parsed))** đảm bảo kết quả format lại giữ đúng biểu diễn đầu vào.
- **TimeZone UTC** làm việc tạo Date từ ngày không phụ thuộc timezone của máy chủ.

**Giới hạn có chủ đích của ví dụ:** regex chỉ chấp nhận chữ số ASCII và năm bốn chữ số; đây là hợp đồng của **mẫu nhập đã chọn**, không phải quy tắc chung cho mọi ngôn ngữ. Nó cũng không tự kiểm tra miền năm nghiệp vụ (ví dụ ngày sinh phải ở quá khứ), không chứng minh thông tin timezone của người dùng, và không thay thế việc kiểm tra quyền/đặc tính dữ liệu khác.

Với ứng dụng đa ngôn ngữ cần nhận chữ số bản địa hoặc tên tháng, không thể bê nguyên regex này cho mọi locale. Phải định nghĩa rõ định dạng nhập và dùng cơ chế parse theo locale phù hợp.

## 9. Vì sao cần ParsePosition mới cho mỗi lượt parse?

Một **ParsePosition** có trạng thái. Nếu tái sử dụng mà không đặt lại **index**, lần parse tiếp theo có thể bắt đầu ở giữa hoặc cuối chuỗi cũ.

~~~java
ParsePosition position = new ParsePosition(0);
Date first = format.parse("28/10/2026", position);

// Index lúc này có thể là 10.
Date second = format.parse("29/10/2026", position);
// Không bắt đầu ở 0 nếu không reset: không đúng ý định.
~~~

Đây là đoạn minh họa cần biến **format** là một SimpleDateFormat đã cấu hình, import **ParsePosition**, **Date**. Cách đơn giản và an toàn nhất là tạo **new ParsePosition(0)** mỗi lần kiểm tra một input độc lập.

Nếu phải dùng lại, cần điều khiển **setIndex(0)** và **setErrorIndex(-1)** theo mục đích, đồng thời đảm bảo code không dùng chung ParsePosition giữa các luồng. Việc tạo một đối tượng ParsePosition mới thường dễ đọc và ít lỗi hơn.

### 9.1. ParsePosition không chỉ dùng để xác minh hết chuỗi

Nó còn hữu ích khi chuỗi chứa nhiều thành phần. Ví dụ:

~~~text
date=28/10/2026;
     ^          ^
     5          15
~~~

Có thể khởi tạo **new ParsePosition(5)** để bắt đầu đọc ngày sau tiền tố **date=**. Sau khi parse, index có thể trở thành **15**, ngay trước dấu chấm phẩy. Phần code ở mức cao hơn sẽ đọc phần còn lại theo cú pháp riêng.

Điều này giải thích vì sao API DateFormat cho phép parse một phần thay vì ép buộc mọi trường hợp phải tiêu thụ cả chuỗi. Trong ứng dụng nhập liệu ngày độc lập, bạn phải tự áp dụng ràng buộc “đọc hết”.

## 10. Phân biệt strict Calendar với strict cú pháp và strict nghiệp vụ

Có ít nhất ba tầng “strict”:

| Tầng | Ví dụ điều kiện | Công cụ |
| --- | --- | --- |
| **Lịch** | 29/02 chỉ hợp lệ trong năm nhuận | **setLenient(false)** |
| **Cú pháp** | Chính xác dd/MM/yyyy, không suffix | Regex/validator + ParsePosition + roundtrip |
| **Nghiệp vụ** | Ngày hẹn không thuộc quá khứ; ngày sinh không ở tương lai | Logic ứng dụng kiểm tra dữ liệu có kiểu |

Một chuỗi **01/02/2024** có thể vượt qua hai tầng đầu nhưng vẫn không hợp lệ nếu hợp đồng nhập dữ liệu yêu cầu “ngày giao hàng phải sau ngày nhận đơn”.

Đừng gọi **setLenient(false)** rồi xem như mọi điều kiện đã được bảo đảm. Nó chỉ thay đổi hành vi của Calendar khi phân tích trường ngày giờ.

### 10.1. Strict vẫn có rủi ro ở vùng đầu vào mơ hồ

**01/02/2024** có nghĩa là 1 tháng 2 theo **dd/MM/yyyy**, nhưng là 2 tháng 1 theo **MM/dd/yyyy**. Cả hai là ngày hợp lệ, nên parser strict không thể phát hiện việc người dùng đang nghĩ theo locale khác.

Giải pháp là hiển thị ví dụ định dạng rõ ràng, thiết lập locale và pattern đúng nguồn dữ liệu, hoặc dùng date picker để giảm nhập nhằng. Không tự đoán locale từ một chuỗi số có dấu phân cách.

## 11. Locale ảnh hưởng việc phân tích tháng và ngày bằng chữ

Với mẫu số như **dd/MM/yyyy**, sự khác nhau về locale thường ít lộ ra. Nhưng với **dd MMMM yyyy** (tên tháng bằng chữ), locale quyết định cách nhận tên tháng và dấu câu.

~~~java
SimpleDateFormat english = new SimpleDateFormat(
        "dd MMMM yyyy", Locale.US);
english.setTimeZone(TimeZone.getTimeZone("UTC"));
english.setLenient(false);

Date parsed = english.parse("28 October 2026");
~~~

Đây là đoạn minh họa cần imports **SimpleDateFormat**, **Locale**, **TimeZone**, **Date** và xử lý **ParseException**. Mẫu chỉ nhận các tên tháng mà formatter theo locale tương ứng biết; không tự hiểu mọi cách viết trong các ngôn ngữ khác nhau.

Nếu dữ liệu đầu vào là tiếng Việt, dùng một Locale tiếng Việt được ứng dụng hỗ trợ; đừng dùng locale mặc định máy chủ. Các tên tháng, tên thứ, dấu chấm trong cách viết tắt và phương thức viết hoa có thể khác giữa các phiên bản JDK/CLDR.

**Lưu ý về số năm hai chữ số:** **SimpleDateFormat** có quy tắc diễn giải đặc biệt khi pattern dùng **yy**; khoảng thế kỷ được tính tương đối với thời điểm tạo formatter, có thể dẫn đến kết quả thay đổi theo thời gian. Với hệ thống cần dữ liệu xác định, đừng dùng **yy** nếu hợp đồng yêu cầu năm đủ bốn chữ số và không có chính sách cửa sổ năm rõ ràng.

## 12. Múi giờ có thể thay đổi Date dù ngày nhập giống nhau

**java.util.Date** đại diện cho một thời điểm. Khi parse **28/10/2026** không có giờ, SimpleDateFormat cần Calendar và TimeZone để tạo Date tương ứng với ngày đó. Đầu ngày ở UTC và đầu ngày ở châu Á có thể là hai Instant khác nhau.

~~~java
SimpleDateFormat utc = new SimpleDateFormat(
        "dd/MM/yyyy", Locale.US);
utc.setTimeZone(TimeZone.getTimeZone("UTC"));
utc.setLenient(false);
~~~

Đây là đoạn minh họa trong phương thức, cần imports phù hợp. Việc chọn UTC làm cho ví dụ tái lập, nhưng không có nghĩa **mọi ngày nghiệp vụ** nên được hiểu là đầu ngày UTC. Với ngày sinh hoặc ngày kỷ niệm, bạn thường muốn lưu **LocalDate** không kèm múi giờ.

Đối với thời gian có giờ phút, **setLenient(false)** còn cần xử lý những giờ địa phương không tồn tại khi chuyển sang giờ mùa hè, hoặc thời điểm mơ hồ trong vùng đổi DST. **DateFormat** và **Calendar** cũ có hành vi và giới hạn riêng; với hệ thống mới nên dùng java.time cùng ZoneId, ZoneRules và chính sách xử lý gap/overlap rõ ràng.

**Locale khác TimeZone.** Locale tiếng Việt không buộc formatter dùng **Asia/Ho_Chi_Minh**. Nếu không đặt TimeZone, default timezone của tiến trình có thể ảnh hưởng Date được tạo.

### 12.1. GregorianCalendar và ngày lịch rất xa

SimpleDateFormat thường làm việc với Calendar như **GregorianCalendar**, có các chi tiết lịch sử và **Gregorian cutover** của lịch kết hợp Julian/Gregorian. Điều này có thể quan trọng với ngày cổ, ngày không nằm trong miền nghiệp vụ thông thường hoặc các hệ lịch khác.

Khi nghiệp vụ thực sự dùng lịch ISO proleptic Gregorian (như **java.time.LocalDate**), không nên giả định mọi kết quả legacy Calendar khớp với java.time cho tất cả thời kỳ lịch sử. Kiểm thử các thời điểm lịch phù hợp miền dữ liệu sản phẩm.

## 13. Lỗi parse String dư ký tự: case study thực tế

Giả sử một API nhận ngày thanh toán theo hợp đồng **dd/MM/yyyy**. Client gửi:

~~~text
28/10/2026#approved
~~~

Một triển khai ban đầu:

~~~java
SimpleDateFormat fmt = new SimpleDateFormat(
        "dd/MM/yyyy", Locale.US);
fmt.setLenient(false);
Date date = fmt.parse(requestDate);
~~~

Đoạn minh họa cần import **SimpleDateFormat**, **Locale**, **Date**, biến **requestDate** và xử lý ParseException. Mặc dù lịch hợp lệ, việc parser đọc ngày ở đầu chuỗi không nhất thiết khiến nó báo lỗi với hậu tố **#approved**.

Hậu quả có thể là:

- Dữ liệu rác bị lưu hoặc được chấp nhận im lặng.
- Client tưởng hậu tố có ý nghĩa nghiệp vụ, server lại bỏ qua.
- Hai dịch vụ dùng parser khác nhau xử lý một request không nhất quán.
- Quá trình kiểm thử chỉ thấy Date đúng và bỏ sót việc đầu vào sai hợp đồng.

Giải pháp: định nghĩa cú pháp, dùng ParsePosition và kiểm tra phần dư, giữ dữ liệu nghiệp vụ có kiểu, không chuyển phần đuôi thành “tùy chọn” nếu hợp đồng không cho phép.

Nếu format được truyền từ bên ngoài hoặc có cấu trúc phức tạp, cần giới hạn/kiểm duyệt pattern và nguồn dữ liệu; đừng nhầm việc parse thành công một ngày với việc chấp nhận toàn bộ payload.

## 14. ParsePosition và nguyên tắc fail-fast

Một parser đầu vào rõ ràng nên trả một trong hai kết quả:

- **Một giá trị đã kiểm chứng đầy đủ** theo hợp đồng cú pháp, lịch và nghiệp vụ.
- **Một lỗi rõ ràng**, không tự sửa ngày hoặc bỏ qua ký tự dư.

Quy trình:

~~~text
String đầu vào
    |
    v
Kiểm tra null / kiểu / độ dài / cú pháp
    |
    v
SimpleDateFormat với Locale + TimeZone rõ ràng
    |
    v
setLenient(false)
    |
    v
ParsePosition(0) -> parse(...)
    |
    +--> null / error -> reject
    |
    v
getIndex() == input.length() ?
    |
    +--> không -> reject
    |
    v
Kiểm tra roundtrip (nếu hợp đồng cần)
    |
    +--> khác -> reject
    |
    v
Kiểm tra miền nghiệp vụ -> chấp nhận
~~~

**Không âm thầm sửa ngày** như “32/01 thành 01/02” nếu hệ thống dùng ngày cho thanh toán, đơn hàng hay pháp lý. Một số tính năng “ngày gần đúng” hoặc công cụ nhập liệu thân thiện có thể cố ý chấp nhận điều chỉnh, nhưng đó phải là **quy tắc nghiệp vụ có thông báo**, không phải tác dụng phụ của leniency mặc định.

## 15. Thread safety: vấn đề đặc biệt của SimpleDateFormat

**SimpleDateFormat** có trạng thái mutable gồm Calendar, TimeZone, NumberFormat, pattern và tùy chọn lenient. Các thao tác **parse** và **format** có thể sửa trạng thái bên trong. Nó **không thread-safe** khi chia sẻ để gọi đồng thời không có bảo vệ phù hợp.

Một anti-pattern trong server:

~~~java
private static final SimpleDateFormat SHARED =
        new SimpleDateFormat("dd/MM/yyyy");
~~~

Đây là đoạn minh họa bên trong class Java; tạo một singleton rồi để nhiều request cùng gọi **SHARED.parse(...)** có thể dẫn đến lỗi cạnh tranh, kết quả sai hoặc ngoại lệ khó tái hiện. Việc **synchronized** mọi truy cập có thể dùng được trong một số cấu trúc, nhưng cần bảo vệ đồng nhất cả các setter và có chi phí/độ phức tạp. Dễ hiểu hơn là **tạo formatter riêng cho mỗi thao tác**, như trong **StrictLegacyDateInput**.

**ParsePosition** cũng có trạng thái và nên tạo mới cho mỗi lần parse. Dữ liệu ngày giờ dạng **LocalDate** và **DateTimeFormatter** của java.time phù hợp hơn cho ứng dụng mới vì formatter modern immutable và thread-safe.

## 16. So sánh với java.time và ResolverStyle.STRICT

Java 8+ giới thiệu **java.time**, và trong Java 17 đây thường là lựa chọn tốt hơn cho code mới. Với ngày lịch, dùng **LocalDate** thay vì Date; với parse pattern, dùng **DateTimeFormatter**; với tính chặt chẽ về lịch, dùng **ResolverStyle.STRICT**.

**Điểm rất quan trọng:** trong DateTimeFormatter, để parse nghiêm ngặt năm lịch ISO, thường dùng pattern **uuuu** thay vì **yyyy**. **yyyy** là year-of-era và có thể cần thêm thông tin era khi giải quyết trường dưới STRICT; **uuuu** là proleptic year. Đây là khác biệt với SimpleDateFormat legacy, nơi **yyyy** dùng theo hệ pattern cũ.

### 16.1. Chương trình Java Time tương đương

**File ModernStrictDateParsing.java**

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ModernStrictDateParsing {
    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter
                    .ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static String parseOrReject(String text) {
        try {
            return LocalDate.parse(text, FORMAT).toString();
        } catch (DateTimeParseException ex) {
            return "rejected";
        }
    }

    public static void main(String[] args) {
        System.out.println(parseOrReject("29/02/2024"));
        System.out.println(parseOrReject("29/02/2023"));
        System.out.println(parseOrReject("28/10/2026XYZ"));
        System.out.println(parseOrReject("28/10/2026"));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ModernStrictDateParsing.java
java ModernStrictDateParsing
~~~

Stdout:

~~~text
2024-02-29
rejected
rejected
2026-10-28
~~~

**Khác biệt chính:**

- **LocalDate** là ngày lịch thuần, không cần TimeZone.
- **ResolverStyle.STRICT** kiểm tra tính hợp lệ của trường ngày/tháng/năm khi giải quyết.
- **LocalDate.parse(CharSequence, DateTimeFormatter)** dùng formatter để parse văn bản thành LocalDate và không chấp nhận phần đuôi không đúng pattern như ví dụ.
- **DateTimeFormatter** immutable và dùng được đồng thời nếu cấu hình được chia sẻ đúng cách.
- **Locale.ROOT** được chọn để làm rõ đầu vào kỹ thuật dùng chữ số/pattern chuẩn, không cần ngôn ngữ giao diện.

Tuy nhiên, **ResolverStyle.STRICT không tự biến mọi pattern thành validator độ rộng ký tự tùy ý**; nếu giao diện có hợp đồng cú pháp cụ thể, hãy kiểm thử các cách nhập mà sản phẩm cho phép. Đặc biệt khi có tháng bằng chữ hoặc chữ số bản địa, cần cấu hình Locale và DecimalStyle phù hợp.

### 16.2. Khi nào vẫn cần legacy API?

Các codebase có thư viện cũ yêu cầu **java.util.Date**, giao diện phụ thuộc **DateFormat**, hoặc giao thức đã tồn tại có thể chưa chuyển đổi ngay. Khi đó:

1. Cô lập parser legacy trong một module/hàm nhỏ.
2. Truyền Locale và TimeZone tường minh.
3. Dùng setLenient(false) cùng ParsePosition/validator cú pháp.
4. Chuyển kết quả sang **Instant** hoặc **LocalDate** theo ý nghĩa dữ liệu, không đổi kiểu tùy tiện.
5. Không để SimpleDateFormat mutable dùng chung giữa nhiều request.
6. Lập test để so sánh hợp đồng cũ và mới trên các dữ liệu trọng yếu.

**Không ép mọi Date thành LocalDate bằng timezone hệ thống.** Một Date biểu diễn Instant; để lấy ngày ở một vùng, phải chọn ZoneId có ý nghĩa. Với ngày thuần từ input legacy, nên cân nhắc parse trực tiếp thành LocalDate trong tầng mới.

## 17. Cạm bẫy khi kiểm thử lenient và ParsePosition

### 17.1. Không assert Date.toString() trong test đa môi trường

**Date.toString()** biểu diễn thời điểm dưới timezone mặc định và có thể cho chuỗi khác giữa CI và máy chủ. Nếu cần kiểm tra Instant, dùng **Date.toInstant()**; hoặc tự format bằng TimeZone được đặt rõ. Với ngày lịch, dùng LocalDate.

### 17.2. Không dùng năm hai chữ số khi yêu cầu tính ổn định

Pattern **yy** có cửa sổ diễn giải năm hai chữ số phụ thuộc thời điểm tạo SimpleDateFormat. Test có thể bị ảnh hưởng theo thời gian hoặc môi trường. Với ngày nhập nghiêm ngặt, yêu cầu năm đủ bốn chữ số và kiểm tra cú pháp.

### 17.3. Kiểm tra nhiều dạng sai chứ không chỉ một ngày 31/02

Một bộ test tối thiểu nên bao phủ:

| Đầu vào | Kết quả mong muốn cho hợp đồng dd/MM/yyyy strict |
| --- | --- |
| **29/02/2024** | Hợp lệ, năm nhuận |
| **29/02/2023** | Không hợp lệ |
| **31/04/2024** | Không hợp lệ |
| **00/01/2024** | Không hợp lệ |
| **01/13/2024** | Không hợp lệ |
| **01/02/2024** | Hợp lệ |
| **1/2/2024** | Không hợp lệ nếu bắt buộc hai chữ số |
| **01/02/2024XYZ** | Không hợp lệ vì phần dư |
| **01-02-2024** | Không hợp lệ theo yêu cầu dấu phân cách |
| **01/02/24** | Không hợp lệ vì thiếu bốn chữ số năm |
| ** 01/02/2024** | Không hợp lệ nếu không cho phép khoảng trắng đầu |
| **01/02/2024** kèm newline | Không hợp lệ nếu không cho phép ký tự cuối |

Nếu sản phẩm cho phép cắt whitespace, cần làm rõ **trim trước validation** có được cho phép không, và sự khác nhau giữa SPACE, NBSP và các ký tự Unicode khác. Không lặng lẽ chuẩn hóa input khi ràng buộc nghiệp vụ yêu cầu giữ nguyên.

### 17.4. Kiểm thử locale và timezone khác nhau

- Chạy parser với **Locale.US** và locale thực tế của người dùng.
- Test với **UTC** và timezone sử dụng trong nghiệp vụ, không chỉ default server.
- Tách test ngày thuần khỏi test thời điểm có giờ và DST.
- Nếu phải thử default JVM khác nhau, chạy các tiến trình riêng; không dùng **Locale.setDefault** hay **TimeZone.setDefault** trong các test song song.
- Kiểm tra parser không trả Date khi ParsePosition mới có errorIndex hoặc chưa tiêu thụ hết chuỗi.
- Kiểm tra kiểu kết quả, đặc biệt khi dùng Calendar lịch sử và năm đặc biệt.

## 18. Các sai lầm thường gặp

### Lỗi 1: Giữ mặc định lenient khi nhận ngày người dùng

**31/02/2024** có thể âm thầm đổi sang tháng 3. Đối với form ngày hẹn, ngày sinh hoặc ngày giao hàng, dùng **setLenient(false)**.

### Lỗi 2: Nghĩ setLenient(false) sẽ bắt lỗi suffix

**28/10/2026XYZ** có tiền tố ngày hợp lệ. Strict Calendar không kiểm tra hết chuỗi. Dùng **ParsePosition** và so sánh index với text.length().

### Lỗi 3: Chỉ kiểm tra Date khác null

Với **parse(String, ParsePosition)**, một Date khác null không chứng minh toàn bộ chuỗi đã được đọc. Phải kiểm tra vị trí kết thúc và các ràng buộc khác.

### Lỗi 4: Chỉ xem errorIndex = -1

Nếu parser dừng thành công trước phần dư, errorIndex vẫn có thể không chỉ báo lỗi. Luôn xem **getIndex()** sau parse.

### Lỗi 5: Dùng dd/MM/yyyy như một regex

SimpleDateFormat là bộ parser theo trường lịch, không phải validator độ rộng ASCII chính xác. Bổ sung validation cú pháp riêng khi bắt buộc.

### Lỗi 6: Nhầm pattern yyyy của API cũ với uuuu của API mới

**SimpleDateFormat** và **DateTimeFormatter** có ý nghĩa pattern không hoàn toàn giống nhau. Với ResolverStyle.STRICT của java.time, dùng **dd/MM/uuuu** khi muốn năm proleptic ISO.

### Lỗi 7: Bỏ qua Locale với tên tháng

Tháng bằng chữ như October cần formatter với Locale thích hợp. Dùng locale server có thể không nhận input đúng ngôn ngữ người dùng.

### Lỗi 8: Không đặt timezone khi tạo Date từ chuỗi ngày

Cùng ngày nhưng Date là instant, nên default timezone khác nhau có thể tạo giá trị epoch khác. Cấu hình timezone rõ ràng hoặc chuyển mô hình sang LocalDate.

### Lỗi 9: Tái sử dụng ParsePosition chưa reset

Index cũ có thể khiến parse bắt đầu sai vị trí. Tạo ParsePosition mới cho từng input.

### Lỗi 10: Dùng SimpleDateFormat singleton nhiều luồng

SimpleDateFormat mutable và không thread-safe. Cách ly formatter, tạo mới hoặc dùng DateTimeFormatter.

### Lỗi 11: Dựa vào parse(String) để kiểm tra input tài chính, pháp lý

Parser có thể chấp nhận tiền tố hợp lệ hoặc tự chuẩn hóa khi lenient. Chuỗi ngày quan trọng cần ràng buộc cú pháp, lịch và nghiệp vụ rõ ràng.

### Lỗi 12: Cố định stdout theo Date.toString()

Date.toString() phụ thuộc timezone mặc định của JVM. Dùng **Date.toInstant()** hoặc format ở timezone đã chỉ định cho test xác định.

## 19. Checklist triển khai parser ngày an toàn

- Xác định ý nghĩa dữ liệu: **ngày thuần**, **giờ địa phương** hay **Instant**.
- Với legacy, khởi tạo **SimpleDateFormat** có pattern và Locale tường minh.
- Đặt **TimeZone** theo nguồn dữ liệu/miền nghiệp vụ trước khi parse, không suy từ locale.
- Gọi **setLenient(false)** khi cần bác bỏ ngày lịch ngoài miền.
- Dùng **new ParsePosition(0)** cho mỗi input, kiểm tra Date khác null.
- Kiểm tra **getErrorIndex()** và **getIndex() == input.length()**.
- Thêm validator cú pháp/roundtrip nếu yêu cầu đúng độ rộng hoặc dấu phân cách.
- Không dùng **yy** nếu không có quy tắc hai chữ số năm rõ ràng.
- Không bỏ qua ngày nhuận, tháng ngắn, ngày 0, tháng 13, input thừa.
- Kiểm tra các ràng buộc nghiệp vụ sau khi đã parse dữ liệu có kiểu.
- Tránh chia sẻ SimpleDateFormat mutable giữa các thread/request.
- Không sử dụng Date.toString() để khẳng định kết quả bằng nhau giữa môi trường.
- Với code mới, ưu tiên **LocalDate** + **DateTimeFormatter** và **ResolverStyle.STRICT**.
- Khi chuyển đổi Date sang java.time, phải xét đúng ZoneId hoặc mô hình dữ liệu.

## 20. Tổng kết

**setLenient(false)** và **ParsePosition** giải quyết **hai vấn đề khác nhau**. Một cái quyết định Calendar có được nới lỏng/sửa ngày ngoài miền hay không; cái kia giúp caller quan sát phần input mà parser đã đọc và vị trí lỗi. Muốn nhận một ngày đúng theo hợp đồng, thường phải kết hợp **strict Calendar + kiểm tra hết chuỗi + kiểm tra cú pháp + kiểm tra nghiệp vụ**.

Với Java 17+, nếu đang bảo trì code dùng **SimpleDateFormat**, hãy truyền Locale và TimeZone tường minh, đặt lenient=false, dùng ParsePosition mới và không chia sẻ formatter mutable. Với chức năng mới chỉ xử lý ngày lịch, ưu tiên **LocalDate** cùng **DateTimeFormatter** cấu hình **ResolverStyle.STRICT**, nhờ kiểu dữ liệu rõ ràng hơn và tránh những phụ thuộc vào TimeZone/Calendar không cần thiết.
