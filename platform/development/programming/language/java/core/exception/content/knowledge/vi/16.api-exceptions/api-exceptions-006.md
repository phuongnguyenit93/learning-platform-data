# ParseException, DateTimeParseException và ngữ cảnh phân tích dữ liệu trong Java

Dữ liệu đi vào chương trình Java thường là **văn bản chưa được xác thực**: ngày sinh từ biểu mẫu, ngày giao hàng trong CSV, thời gian trong URL, số có dấu phân nhóm theo locale hoặc thông tin từ hệ thống cũ. Việc chuyển văn bản thành đối tượng có kiểu được gọi là **parsing**. Khi chuỗi không khớp định dạng hoặc không tạo ra được giá trị hợp lệ, API parser báo lỗi. Hai tên ngoại lệ rất dễ nhầm là **java.text.ParseException** và **java.time.format.DateTimeParseException**.

Điều cốt lõi:

- **ParseException** thuộc **java.text**, là **checked exception** (kế thừa trực tiếp Exception). Nhiều API cũ như **SimpleDateFormat.parse(String)** và **NumberFormat.parse(String)** công bố nó trong chữ ký **throws ParseException**.
- **DateTimeParseException** thuộc **java.time.format**, là **unchecked exception** (kế thừa DateTimeException → RuntimeException). Các API hiện đại như **LocalDate.parse** và **DateTimeFormatter.parse** có thể ném nó khi không đọc hoặc không giải quyết được dữ liệu thời gian.
- Cả hai có thể gắn thông tin về **vị trí lỗi**, nhưng **ParseException.getErrorOffset()** và **DateTimeParseException.getErrorIndex()** không phải những “mã lỗi nghiệp vụ” giống nhau. DateTimeParseException còn giữ chuỗi được parse qua **getParsedString()**.
- **Đúng mẫu ký tự chưa đủ** để bảo đảm ngày tồn tại, toàn bộ chuỗi được tiêu thụ, giá trị đúng múi giờ hoặc đáp ứng yêu cầu của một trường đầu vào.
- Khi API chuyển đổi có chính sách checked/unchecked khác nhau, tầng xử lý cần bắt đúng ngoại lệ, thêm **ngữ cảnh trường dữ liệu**, giữ **cause** nếu bọc lỗi và không làm lộ văn bản nhạy cảm trong thông báo người dùng.

Bài viết dành cho **Java 17+**, trình bày cơ chế, lựa chọn API, strict/smart/lenient, vị trí lỗi, ParsePosition, thời gian và locale, cùng những ví dụ độc lập có lệnh biên dịch và kết quả stdout.

## 1. Hệ phân cấp và khác biệt checked/unchecked

Sơ đồ:

~~~text
java.lang.Throwable
  └── java.lang.Exception
       ├── java.text.ParseException                  [checked]
       └── java.lang.RuntimeException
            └── java.time.DateTimeException
                 └── java.time.format.DateTimeParseException [unchecked]
~~~

Hai ngoại lệ không phải quan hệ cha–con trực tiếp và không thể thay thế bằng một nhánh catch cụ thể duy nhất.

| Tiêu chí | ParseException | DateTimeParseException |
| --- | --- | --- |
| Package | java.text | java.time.format |
| Checked hay unchecked? | Checked | Unchecked |
| Lớp cha trực tiếp | Exception | DateTimeException |
| API tiêu biểu | SimpleDateFormat.parse(String), NumberFormat.parse(String) | LocalDate.parse, LocalDateTime.parse, DateTimeFormatter.parse |
| Thông tin vị trí | getErrorOffset() | getErrorIndex() |
| Giữ văn bản đầu vào nguyên dạng? | Không có getter chuyên biệt để lấy toàn chuỗi | getParsedString() |
| Cách xử lý tại nơi gọi | Bắt hoặc khai báo throws ParseException | Không bắt buộc theo compiler nhưng nên xử lý ở ranh giới input |
| Đối tượng kết quả thường gặp | java.util.Date, Number | LocalDate, LocalDateTime, OffsetDateTime, ZonedDateTime, TemporalAccessor |

**Không đồng nhất ngoại lệ của tất cả parser.** Integer.parseInt("bad") ném **NumberFormatException**, cũng là unchecked, chứ không ném ParseException. Các thư viện JSON, XML hoặc CSV có thể có ngoại lệ riêng. Phải xem **chữ ký phương thức thực tế** thay vì suy đoán từ việc API “đang parse chuỗi”.

### Tại sao sự phân biệt này quan trọng?

Với một phương thức dùng API java.text:

~~~java
static java.util.Date readLegacy(String text)
        throws java.text.ParseException {
    java.text.SimpleDateFormat format =
            new java.text.SimpleDateFormat("dd/MM/yyyy");
    return format.parse(text);
}
~~~

Đây là phương thức minh họa, không phải chương trình có main. Vì ParseException checked, caller phải bắt hoặc khai báo phù hợp.

Với java.time:

~~~java
static java.time.LocalDate readModern(String text) {
    return java.time.LocalDate.parse(text);
}
~~~

Phương thức này không cần khai báo throws DateTimeParseException. Tuy nhiên, nếu đọc text từ người dùng, ứng dụng vẫn phải quyết định cách trả về lỗi đầu vào thay vì để unchecked exception làm hỏng request không được xử lý.

## 2. ParseException trong java.text biểu diễn điều gì?

Chữ ký khởi tạo của java.text.ParseException:

~~~java
public ParseException(String message, int errorOffset)
~~~

Thông tin hữu ích:

- **getMessage()**: chuỗi mô tả do parser hoặc bên tạo ngoại lệ cung cấp; không có cấu trúc mã lỗi thống nhất giữa mọi parser.
- **getErrorOffset()**: vị trí báo lỗi do bên phát hiện xác định. Không nên giả định mọi parser luôn cung cấp chỉ số chính xác tuyệt đối cho nguyên nhân sâu xa.
- **getCause()**: cơ chế Throwable thông thường nếu có liên kết nguyên nhân; constructor ParseException không có overload (String, Throwable) chuyên dụng, nhưng có thể dùng **initCause** khi thật sự cần liên kết một cause và cause chưa khởi tạo.

Ví dụ một trình phân tích nội bộ tự tạo ParseException:

~~~java
throw new java.text.ParseException("Invalid token", 4);
~~~

Đây là đoạn mã có thể nằm trong phương thức khai báo throws ParseException. Khi được bắt, **getErrorOffset()** trả 4 vì chính chương trình đã thiết lập offset này.

Đừng mặc định **getErrorOffset()** là số dòng trong file hoặc số cột trong giao diện. Nó là vị trí do parser cung cấp trong ngữ cảnh văn bản của nó. Khi dữ liệu là CSV nhiều dòng, ứng dụng cần tự theo dõi **số dòng**, **tên cột**, **giá trị gốc** và quy tắc chuyển từ vị trí ký tự sang vị trí người dùng có thể hiểu.

## 3. Chương trình Java 17+: bắt checked ParseException

Lưu thành **LegacyParseDemo.java**:

~~~java
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class LegacyParseDemo {
    static Date parseLegacy(String text) throws ParseException {
        SimpleDateFormat format =
                new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
        format.setLenient(false);
        return format.parse(text);
    }

    public static void main(String[] args) {
        try {
            Date date = parseLegacy("19/10/2026");
            SimpleDateFormat output =
                    new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
            output.setLenient(false);
            System.out.println("valid=" + output.format(date));
        } catch (ParseException ex) {
            System.out.println("unexpected parse failure");
        }

        try {
            parseLegacy("31/02/2026");
        } catch (ParseException ex) {
            System.out.println("invalid="
                    + ex.getClass().getSimpleName());
            System.out.println("offsetNonNegative="
                    + (ex.getErrorOffset() >= 0));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LegacyParseDemo.java
java LegacyParseDemo
~~~

Kết quả trong môi trường Java 17+ thông thường:

~~~text
valid=19/10/2026
invalid=ParseException
offsetNonNegative=true
~~~

Điểm cần hiểu:

1. **setLenient(false)** giúp SimpleDateFormat từ chối ngày không tồn tại như ngày 31 tháng 2. Chỉ khớp số chữ số với pattern không thể biến ngày ấy thành giá trị lịch hợp lệ.
2. **parseLegacy** khai báo **throws ParseException**. Chương trình main bắt lỗi checked này.
3. Khi lỗi xảy ra, đoạn mã chỉ in việc offset là không âm, tránh phụ thuộc một giá trị index cụ thể của parser cho dữ liệu sai khác nhau.
4. Để kết quả ngày dễ kiểm chứng, chương trình format lại Date về cùng pattern, không in Date.toString() vốn chịu ảnh hưởng múi giờ khi hiển thị.

**Giới hạn lớn:** setLenient(false) kiểm soát việc giải thích các trường ngày, nhưng **không tự bảo đảm** mọi ký tự của đầu vào đã được sử dụng.

## 4. Bẫy parse tiền tố ở API cũ

Các parser trong java.text thường cho phép parse **một phần đầu hợp lệ** của chuỗi. Ví dụ, **SimpleDateFormat.parse(String)** có thể chấp nhận chuỗi ngày ở đầu và bỏ lại hậu tố không thuộc pattern. Tương tự, NumberFormat.parse(String) có thể tạo một Number từ một tiền tố hợp lệ.

Để kiểm soát mức tiêu thụ đầu vào, dùng **java.text.ParsePosition**:

~~~java
ParsePosition position = new ParsePosition(0);
Date date = format.parse(raw, position);

boolean full = date != null
        && position.getIndex() == raw.length();
~~~

Đoạn minh họa trên nằm trong một phương thức với **format** và **raw** hợp lệ. Khác với **parse(String)** ném checked ParseException, overload **parse(String, ParsePosition)** của SimpleDateFormat báo lỗi bằng giá trị **null** và thông tin vị trí.

### Chương trình Java 17+: phát hiện hậu tố thừa

Lưu thành **LegacyPositionDemo.java**:

~~~java
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class LegacyPositionDemo {
    static SimpleDateFormat formatter() {
        SimpleDateFormat result =
                new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
        result.setLenient(false);
        return result;
    }

    public static void main(String[] args) {
        SimpleDateFormat format = formatter();
        String raw = "19/10/2026tail";

        ParsePosition position = new ParsePosition(0);
        Date parsed = format.parse(raw, position);

        System.out.println("parsed=" + (parsed != null));
        System.out.println("consumed=" + position.getIndex());
        System.out.println("whole="
                + (parsed != null
                   && position.getIndex() == raw.length()));

        ParsePosition invalidPosition = new ParsePosition(0);
        Date invalid = format.parse("31/02/2026", invalidPosition);
        System.out.println("invalid=" + (invalid == null));
        System.out.println("hasErrorIndex="
                + (invalidPosition.getErrorIndex() >= 0));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LegacyPositionDemo.java
java LegacyPositionDemo
~~~

Kết quả:

~~~text
parsed=true
consumed=10
whole=false
invalid=true
hasErrorIndex=true
~~~

Chuỗi **19/10/2026tail** có mười ký tự tạo ngày ở đầu. Parser nhận được một Date, nhưng **position.getIndex() == 10**, nhỏ hơn độ dài toàn chuỗi. Vì thế trường đầu vào theo hợp đồng **phải khớp toàn chuỗi** nên bị từ chối.

ParsePosition có hai trường trạng thái cần phân biệt:

- **getIndex()**: vị trí sau ký tự cuối cùng được parse thành công.
- **getErrorIndex()**: vị trí parser báo lỗi khi thất bại, thường là -1 nếu chưa có lỗi được ghi nhận.

Đừng dùng kiểm tra **parsed != null** như bằng chứng toàn bộ đầu vào hợp lệ. Không nên tự coi chỉ số ParsePosition là số dòng hay số cột; nếu file nguồn có nhiều dòng, ứng dụng cần bổ sung tọa độ dữ liệu.

## 5. DateTimeParseException trong java.time

JDK hiện đại cung cấp thư viện **java.time**, với các loại dữ liệu tách biệt rõ:

- **LocalDate**: ngày theo lịch ISO, không có giờ và múi giờ.
- **LocalTime**: giờ trong ngày, không có ngày/múi giờ.
- **LocalDateTime**: ngày + giờ địa phương, chưa xác định offset/múi giờ.
- **OffsetDateTime**: ngày-giờ với offset cụ thể.
- **ZonedDateTime**: ngày-giờ gắn với vùng múi giờ theo ZoneId.
- **Instant**: một thời điểm trên trục thời gian.

**DateTimeParseException** được ném khi một thao tác parse ngày-giờ không xử lý được chuỗi đầu vào theo formatter và kiểu kết quả yêu cầu. Ngoại lệ này kế thừa DateTimeException nên thuộc nhóm unchecked.

API đọc thông tin chẩn đoán:

~~~java
String originalText = ex.getParsedString();
int errorAt = ex.getErrorIndex();
String description = ex.getMessage();
~~~

Đây là các biểu thức minh họa khi **ex** có kiểu DateTimeParseException. **getParsedString()** có thể chứa nguyên văn dữ liệu đầu vào; khi chuỗi có giá trị nhạy cảm, không ghi toàn bộ vào log công khai. **getErrorIndex()** hỗ trợ xác định vị trí nhưng không phải một mã nghiệp vụ hoặc một cam kết về ký tự gây lỗi sâu xa trong mọi giai đoạn phân tích.

### Chương trình Java 17+: kết quả DateTimeParseException

Lưu thành **ModernDateParseDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

public class ModernDateParseDemo {
    static void inspect(String raw) {
        try {
            LocalDate date = LocalDate.parse(raw);
            System.out.println("ok=" + date);
        } catch (DateTimeParseException ex) {
            System.out.println("bad=" + ex.getParsedString());
            System.out.println("type="
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        inspect("2026-10-19");
        inspect("2026-02-30");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ModernDateParseDemo.java
java ModernDateParseDemo
~~~

Kết quả:

~~~text
ok=2026-10-19
bad=2026-02-30
type=DateTimeParseException
~~~

**2026-02-30** có các thành phần ký tự giống định dạng ISO yyyy-MM-dd, nhưng ngày 30 tháng 2 không tồn tại. **DateTimeFormatter.ISO_LOCAL_DATE** dùng kiểu giải quyết nghiêm ngặt; việc không tạo được LocalDate hợp lệ dẫn tới DateTimeParseException.

Không nên in trước giá trị giả định của **getErrorIndex()** cho lỗi lịch không hợp lệ: index ở giai đoạn xử lý trường ngày có thể khác index của lỗi ký tự thuần túy. Ở đây in lại parsedString để kiểm chứng mối liên hệ với đầu vào; trong môi trường sản xuất chỉ log giá trị này khi chính sách dữ liệu cho phép.

## 6. Lỗi cú pháp và lỗi giải quyết ngày là hai giai đoạn khác nhau

DateTimeFormatter mô tả quy trình parse thành hai bước lớn:

1. **Text parsing**: đọc ký tự theo pattern/formatter để thu các giá trị trường như YEAR, MONTH_OF_YEAR và DAY_OF_MONTH.
2. **Resolving**: kết hợp những giá trị trường thành ngày/giờ có ý nghĩa, kiểm tra tính nhất quán và các quy tắc lịch.

Vì vậy:

| Chuỗi / lỗi | Vấn đề |
| --- | --- |
| "2026/10/19" với ISO_LOCAL_DATE | Sai ký tự phân tách ở giai đoạn đọc text |
| "2026-13-19" | Tháng nằm ngoài phạm vi cho phép |
| "2026-02-30" | Cú pháp trông hợp lệ nhưng ngày không tồn tại |
| "2026-10-19extra" | Tiền tố hợp lệ nhưng dư hậu tố; phương thức parse toàn chuỗi từ chối |
| "2026-10-19" | Ngày ISO hợp lệ |
| "2024-02-29" | Ngày nhuận hợp lệ |

Thông điệp lỗi của DateTimeParseException thường phân biệt “could not be parsed at index...” với “could not be parsed: ...”, nhưng **ứng dụng không nên parse ngược chuỗi message** để quyết định lỗi nào. Hãy quyết định chính sách hợp lệ bằng formatter, kiểu đích và validation riêng.

### Chương trình Java 17+: kiểm tra vị trí ký tự dư

Lưu thành **TrailingTextDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

public class TrailingTextDemo {
    public static void main(String[] args) {
        String raw = "2026-10-19extra";

        try {
            LocalDate.parse(raw);
        } catch (DateTimeParseException ex) {
            System.out.println("sameText="
                    + raw.equals(ex.getParsedString()));
            System.out.println("errorAt="
                    + ex.getErrorIndex());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 TrailingTextDemo.java
java TrailingTextDemo
~~~

Kết quả:

~~~text
sameText=true
errorAt=10
~~~

Với mười ký tự tạo ngày ISO ở đầu, ký tự đầu tiên không được tiêu thụ là chỉ số 10 theo vị trí chuỗi Java bắt đầu từ 0. Đây là trường hợp lỗi cú pháp cụ thể với kết quả xác định; không suy rộng rằng lỗi ngày không nhuận hoặc lỗi resolver cũng luôn có cùng chỉ số.

Các parser mặc định như **LocalDate.parse(text)** mong đợi **toàn bộ text** phù hợp định dạng. Nếu muốn chủ ý phân tích một phân đoạn văn bản lớn, java.time có overload với ParsePosition dành cho xử lý nâng cao, nhưng cần quản lý vị trí và ranh giới riêng.

## 7. ResolverStyle: STRICT, SMART, LENIENT

**java.time.format.ResolverStyle** quyết định cách xử lý những trường ngày/giờ đã đọc:

| Kiểu | Ý nghĩa | Với ngày không tồn tại |
| --- | --- | --- |
| STRICT | Yêu cầu các trường hợp lệ theo lịch/kiểu dữ liệu | Từ chối |
| SMART | Điều chỉnh một số giá trị có thể suy diễn hợp lý | Có thể điều chỉnh ngày cuối tháng |
| LENIENT | Cho phép giải quyết linh hoạt, có thể vượt tháng/ngày | Có thể cuộn sang tháng/ngày khác |

**DateTimeFormatter.ofPattern(...)** mặc định dùng **ResolverStyle.SMART**, trong khi các formatter ISO định sẵn như **ISO_LOCAL_DATE** sử dụng quy tắc chặt chẽ phù hợp. Nếu dữ liệu phải tuân thủ lịch tuyệt đối, hãy **chọn STRICT tường minh**.

Một điểm dễ nhầm là ký hiệu năm:

- **u / uuuu**: proleptic year; phù hợp khi parse LocalDate nghiêm ngặt trong lịch ISO.
- **y / yyyy**: year-of-era. Trong strict parsing, chỉ có year-of-era mà không có era có thể không đủ để tạo LocalDate.

Vì vậy khi tự định nghĩa formatter strict cho **dd/MM/yyyy** theo ý nghĩa năm lịch ISO thông thường, sử dụng **dd/MM/uuuu** thường rõ ràng hơn.

### Chương trình Java 17+: SMART có thể điều chỉnh ngày, STRICT từ chối

Lưu thành **ResolverStyleDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ResolverStyleDemo {
    public static void main(String[] args) {
        DateTimeFormatter smart =
                DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT);
        DateTimeFormatter strict =
                smart.withResolverStyle(ResolverStyle.STRICT);

        System.out.println("smart="
                + LocalDate.parse("29/02/2023", smart));
        System.out.println("leap="
                + LocalDate.parse("29/02/2024", strict));

        try {
            LocalDate.parse("29/02/2023", strict);
        } catch (DateTimeParseException ex) {
            System.out.println("strict=invalid-date");
        }

        DateTimeFormatter strictYearOfEra =
                DateTimeFormatter.ofPattern("dd/MM/yyyy", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);
        try {
            LocalDate.parse("19/10/2026", strictYearOfEra);
        } catch (DateTimeParseException ex) {
            System.out.println("year-of-era=unresolved");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ResolverStyleDemo.java
java ResolverStyleDemo
~~~

Kết quả:

~~~text
smart=2023-02-28
leap=2024-02-29
strict=invalid-date
year-of-era=unresolved
~~~

Điểm quan trọng: với formatter SMART, **29/02/2023** có thể được giải quyết thành **2023-02-28**. Nếu ứng dụng nhận ngày sinh, hạn thanh toán hoặc mốc kiểm toán, việc điều chỉnh âm thầm như vậy có thể không phù hợp. Chọn **ResolverStyle.STRICT** và kiểm thử các ngày cuối tháng, năm nhuận.

Không nên lầm tưởng đổi từ SimpleDateFormat sang DateTimeFormatter có nghĩa **mọi formatter java.time luôn strict**. Phải đọc resolver style thực tế của formatter.

## 8. So sánh lenient của API cũ và resolver style của API mới

**SimpleDateFormat** có **setLenient(boolean)**, điều khiển Calendar được dùng để giải quyết các trường ngày. Mặc định cơ chế cũ thường lenient: một giá trị không tồn tại có thể được chuẩn hóa sang ngày khác. Khi cần ngày hợp lệ, hãy gọi **setLenient(false)**.

**DateTimeFormatter** là immutable và cấu hình bằng **withResolverStyle(ResolverStyle.STRICT)** để tạo formatter mới, không sửa formatter cũ. Với lịch ISO, STRICT bảo đảm các trường không tạo ra ngày không tồn tại; SMART có thể điều chỉnh ngày cuối tháng.

Nhưng hai khái niệm **không đồng nhất hoàn toàn**. Cú pháp pattern, cách phân tích số, hỗ trợ locale và xử lý thời gian ở hai API khác nhau. Không nên chuyển máy móc một pattern từ SimpleDateFormat sang DateTimeFormatter rồi kỳ vọng mọi ký tự pattern có cùng ý nghĩa.

Ví dụ khác biệt đặc biệt quan trọng:

| Nội dung | java.text.SimpleDateFormat | java.time.DateTimeFormatter |
| --- | --- | --- |
| Cấu hình nghiêm ngặt | setLenient(false) | withResolverStyle(STRICT) |
| Tính mutability | Mutable | Immutable |
| Dùng chung giữa thread | Không nên chia sẻ một instance mutable nếu không đồng bộ | Formatter được thiết kế immutable và thread-safe |
| Kiểu kết quả | java.util.Date | Thường LocalDate/LocalDateTime/TemporalAccessor |
| Lỗi parse(String) thông thường | Checked ParseException | Unchecked DateTimeParseException |
| Toàn bộ chuỗi | parse(String) có thể chấp nhận tiền tố | LocalDate.parse/DateTimeFormatter.parse thông thường yêu cầu khớp toàn chuỗi |
| Vị trí parse nâng cao | ParsePosition, thường trả null khi lỗi | API ParsePosition có hành vi lỗi riêng tùy overload |

Khi bảo trì hệ thống cũ, có thể giữ SimpleDateFormat ở ranh giới tương thích; với API mới, java.time thường dễ mô hình hóa ngày/giờ hơn và tránh chia sẻ đối tượng mutable không an toàn giữa các thread.

## 9. Locale và ký hiệu tháng bằng chữ

Định dạng ngày theo từ viết tắt của tháng phụ thuộc Locale. Với DateTimeFormatter, việc chỉ định Locale tường minh tránh phụ thuộc ngôn ngữ mặc định trên máy chạy.

Lưu thành **LocaleDateDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class LocaleDateDemo {
    public static void main(String[] args) {
        DateTimeFormatter english =
                DateTimeFormatter.ofPattern("dd MMM uuuu", Locale.ENGLISH)
                        .withResolverStyle(ResolverStyle.STRICT);

        LocalDate date = LocalDate.parse("19 Oct 2026", english);
        System.out.println("date=" + date);

        try {
            LocalDate.parse("19 Foo 2026", english);
        } catch (DateTimeParseException ex) {
            System.out.println("unknown-month=invalid");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocaleDateDemo.java
java LocaleDateDemo
~~~

Kết quả:

~~~text
date=2026-10-19
unknown-month=invalid
~~~

Với dữ liệu chuẩn trao đổi giữa hệ thống, định dạng ISO như **2026-10-19** thường thuận tiện hơn chuỗi tháng bằng chữ phụ thuộc locale. Nếu yêu cầu UI theo ngôn ngữ người dùng, dùng Locale đã xác định và test với những biểu diễn địa phương thực tế.

Cũng cần phân biệt **Locale** với **ZoneId**. Locale chủ yếu tác động tới quy ước ngôn ngữ/định dạng; nó **không tự gắn múi giờ** cho LocalDate hoặc LocalDateTime. Nếu chuỗi có offset hoặc múi giờ, dùng kiểu đích phù hợp.

## 10. Chọn đúng kiểu đích: ngày, giờ địa phương hay thời điểm

Một chuỗi **2026-10-19** chỉ mô tả ngày, không cho biết thời gian trong ngày hoặc múi giờ. Vì vậy **LocalDate.parse** thích hợp.

Ngược lại:

- **2026-10-19T14:30:00** có ngày và giờ, không có offset: thường là **LocalDateTime**.
- **2026-10-19T14:30:00+07:00** có offset: thường là **OffsetDateTime**.
- **2026-10-19T07:30:00Z** biểu diễn thời điểm UTC và có thể được phân tích bằng **Instant.parse**.
- Chuỗi có vùng múi giờ như **[Asia/Ho_Chi_Minh]** cần formatter và kiểu hỗ trợ zone nếu định dạng có phần đó.

Không nên lấy LocalDateTime rồi coi nó là một **Instant** nếu chưa có thông tin offset/zone đúng theo nghiệp vụ. Việc thiếu bối cảnh thời gian có thể dẫn tới **ngày giờ đúng cú pháp nhưng sai thời điểm thực tế**, dù không xuất hiện DateTimeParseException.

### Chương trình Java 17+: cùng thời điểm, hai cách biểu diễn

Lưu thành **TemporalTypeDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;

public class TemporalTypeDemo {
    public static void main(String[] args) {
        System.out.println("date="
                + LocalDate.parse("2026-10-19"));
        System.out.println("local="
                + LocalDateTime.parse("2026-10-19T14:30:00"));
        System.out.println("offset="
                + OffsetDateTime.parse(
                        "2026-10-19T14:30:00+07:00").toInstant());
        System.out.println("instant="
                + Instant.parse("2026-10-19T07:30:00Z"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 TemporalTypeDemo.java
java TemporalTypeDemo
~~~

Kết quả:

~~~text
date=2026-10-19
local=2026-10-19T14:30
offset=2026-10-19T07:30:00Z
instant=2026-10-19T07:30:00Z
~~~

LocalDateTime.toString() thường bỏ phần giây khi bằng 0 trong trường hợp ví dụ, nên **local=2026-10-19T14:30**. Hai dòng cuối diễn tả cùng Instant: offset +07:00 tại 14:30 tương ứng 07:30 UTC. Không biến **LocalDateTime** thành thời điểm toàn cục mà thiếu thông tin zone.

## 11. NumberFormat.parse(String) cũng dùng checked ParseException

ParseException không chỉ xuất hiện khi đọc ngày. Các parser số có hỗ trợ locale như **NumberFormat.parse(String)** cũng khai báo checked ParseException. Đây là khác biệt đáng nhớ với **Integer.parseInt(String)** ném unchecked NumberFormatException.

Ví dụ dùng Locale.GERMANY để đọc chuỗi **1.234,5** theo quy ước dấu phân nhóm và dấu thập phân:

Lưu thành **LegacyNumberParseDemo.java**:

~~~java
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public class LegacyNumberParseDemo {
    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.GERMANY);

        try {
            Number value = formatter.parse("1.234,5");
            System.out.println("number=" + value.doubleValue());
        } catch (ParseException ex) {
            System.out.println("unexpected-invalid");
        }

        try {
            formatter.parse("not-a-number");
        } catch (ParseException ex) {
            System.out.println("invalid=ParseException");
        }

        String partial = "1.234,5tail";
        ParsePosition position = new ParsePosition(0);
        Number parsed = formatter.parse(partial, position);
        System.out.println("hasNumber=" + (parsed != null));
        System.out.println("consumed=" + position.getIndex());
        System.out.println("whole="
                + (parsed != null
                   && position.getIndex() == partial.length()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LegacyNumberParseDemo.java
java LegacyNumberParseDemo
~~~

Kết quả với dữ liệu locale tiêu chuẩn:

~~~text
number=1234.5
invalid=ParseException
hasNumber=true
consumed=7
whole=false
~~~

**NumberFormat.parse(String)** có thể nhận một tiền tố hợp lệ, vì vậy muốn kiểm tra toàn chuỗi thì dùng ParsePosition hoặc một lớp xác thực chặt hơn. Với dữ liệu tiền cần chính xác decimal, cân nhắc DecimalFormat cấu hình **setParseBigDecimal(true)** và chính sách scale phù hợp thay vì mặc định chuyển về double.

**Sự khác nhau không phải do checked exception “nghiêm ngặt hơn” theo nghĩa nghiệp vụ.** Checked/unchecked là chính sách ngôn ngữ tại vị trí gọi; một parser vẫn có thể dễ dãi với tiền tố hoặc giá trị kể cả khi nó khai báo checked exception.

## 12. ParsePosition giữa java.text và java.time không hoàn toàn giống nhau

**java.text.Format** có nhiều overload parse với ParsePosition. Chẳng hạn **SimpleDateFormat.parse(String, ParsePosition)** thường trả **null** khi parser không đọc được và cập nhật **getErrorIndex()**. Caller cần tự kiểm tra null và vị trí tiêu thụ.

Ở **DateTimeFormatter.parse(CharSequence, ParsePosition)**, tài liệu JDK mô tả **DateTimeParseException** có thể được ném khi có lỗi parse, thay vì mọi lỗi đều được mã hóa dưới dạng null như một số java.text formatter. Có thêm phương thức **parseUnresolved(...)** dành cho xử lý giai đoạn phân tích trường chưa giải quyết, với cách sử dụng và kiểm tra lỗi riêng.

Vì vậy không nên khái quát:

~~~java
// KHÔNG ÁP DỤNG MÙ QUÁNG CHO MỌI PARSER:
Object result = parser.parse(text, position);
if (result == null) {
    // assume all parsing errors arrive here
}
~~~

Đây chỉ là **mã giả minh họa**. Hãy đọc hợp đồng của overload cụ thể: kiểu trả về, checked/unchecked exception, cập nhật ParsePosition và có cần kiểm tra toàn chuỗi hay không.

Với phần lớn ứng dụng cần LocalDate đầy đủ, nên dùng **LocalDate.parse(text, formatter)** và xác thực đầu vào trước/sau parse thay vì tự thao tác parseUnresolved.

## 13. Chuyển ngoại lệ sang lỗi có ngữ cảnh tại ranh giới API

Một lớp API không nên lộ nguyên message của parser cho người dùng nếu đầu vào có thể chứa token, dữ liệu cá nhân, nội dung rất dài hoặc biểu diễn không phù hợp. Tầng ứng dụng biết **tên trường**, **định dạng yêu cầu** và **mã lỗi**. Nó có thể chuyển ngoại lệ thư viện sang ngoại lệ/đối tượng lỗi của miền ứng dụng.

Ví dụ một quy trình nhập hóa đơn muốn trường **invoiceDate** theo ISO. Dùng kiểu lỗi riêng không checked để báo validation, nhưng **giữ cause** để logger kỹ thuật vẫn truy được DateTimeParseException.

Lưu thành **InputContextDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

public class InputContextDemo {
    static class InvalidFieldException extends IllegalArgumentException {
        private final String field;

        InvalidFieldException(
                String field, String message, Throwable cause) {
            super(message, cause);
            this.field = field;
        }

        String field() {
            return field;
        }
    }

    static LocalDate invoiceDate(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new InvalidFieldException(
                    "invoiceDate", "date is required", null);
        }

        try {
            return LocalDate.parse(raw);
        } catch (DateTimeParseException ex) {
            throw new InvalidFieldException(
                    "invoiceDate", "date must be yyyy-MM-dd", ex);
        }
    }

    public static void main(String[] args) {
        System.out.println("valid="
                + invoiceDate("2026-10-19"));

        try {
            invoiceDate("19/10/2026");
        } catch (InvalidFieldException ex) {
            System.out.println("field=" + ex.field());
            System.out.println("message=" + ex.getMessage());
            System.out.println("causeType="
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 InputContextDemo.java
java InputContextDemo
~~~

Kết quả:

~~~text
valid=2026-10-19
field=invoiceDate
message=date must be yyyy-MM-dd
causeType=DateTimeParseException
~~~

Trong ví dụ, **LocalDate.parse** được giữ trong một vùng try nhỏ: một DateTimeParseException khác từ logic không liên quan ở ngoài sẽ không bị gán nhầm thành lỗi trường invoiceDate. Wrapper có thể mang thuộc tính **field** có kiểu rõ ràng; frontend không cần parse message để xác định trường sai.

Nếu sử dụng ParseException checked ở tầng legacy, có thể bọc thành một ngoại lệ checked domain riêng **extends Exception**, hoặc chuyển tại API boundary khi đó là chính sách hợp đồng của module. Không nên bọc mọi checked exception thành RuntimeException mà không phân biệt khả năng phục hồi.

## 14. Checked ParseException và cách giữ cause khi chuyển sang domain exception

Một lớp ngoại lệ nghiệp vụ có thể là checked:

~~~java
class ImportDateException extends Exception {
    ImportDateException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là khai báo lớp hợp lệ không có main. Nếu một bước import legacy ném ParseException:

~~~java
try {
    return legacyFormatter.parse(raw);
} catch (java.text.ParseException ex) {
    throw new ImportDateException(
            "Invalid import date in column invoiceDate", ex);
}
~~~

Đây là đoạn minh họa trong một phương thức có trả về **java.util.Date**, khai báo **throws ImportDateException**, với **legacyFormatter** và **raw** đã định nghĩa.

Thông tin còn lại sau chuyển đổi:

- **ImportDateException.getMessage()** biểu diễn ngữ cảnh của bước import.
- **getCause()** giữ chính đối tượng ParseException cũ; có thể kiểm tra **getErrorOffset()** sau khi ép kiểu cause phù hợp.
- Trace của cause vẫn giúp tìm nơi parser legacy phát hiện lỗi.
- Wrapper có stack trace riêng ở điểm chuyển đổi; không cần gọi **setStackTrace()** để “ghép” các frame.

**Không chỉ viết** một ngoại lệ mới với message của lỗi gốc. Thao tác đó cắt chuỗi nguyên nhân và khó chẩn đoán. Đồng thời, không được giả định **getCause()** luôn khác null trong tất cả tình huống; hãy kiểm tra trước khi truy cập nếu wrapper có thể được tạo mà không có cause.

## 15. Nhập nhiều bản ghi: lưu trạng thái lỗi theo từng dòng

Một file CSV gồm nhiều ngày có thể yêu cầu phản hồi mọi dòng sai thay vì dừng ở lỗi đầu tiên. Khi từng dòng độc lập, có thể chuyển ngoại lệ parse thành một đối tượng kết quả có mã và ngữ cảnh.

Lưu thành **DateBatchDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.List;

public class DateBatchDemo {
    record RowResult(int row, LocalDate value, String error) {
        boolean valid() {
            return error == null;
        }
    }

    static RowResult parseRow(int row, String raw) {
        try {
            return new RowResult(row, LocalDate.parse(raw), null);
        } catch (DateTimeParseException ex) {
            return new RowResult(row, null, "INVALID_DATE");
        }
    }

    public static void main(String[] args) {
        List<String> inputs = List.of(
                "2026-10-19", "2026-02-30", "2024-02-29");

        for (int i = 0; i < inputs.size(); i++) {
            RowResult result = parseRow(i + 1, inputs.get(i));
            if (result.valid()) {
                System.out.println("ok=" + result.row()
                        + ":" + result.value());
            } else {
                System.out.println("error=" + result.row()
                        + ":" + result.error());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DateBatchDemo.java
java DateBatchDemo
~~~

Kết quả:

~~~text
ok=1:2026-10-19
error=2:INVALID_DATE
ok=3:2024-02-29
~~~

Record là tính năng chuẩn của Java 17. Ví dụ chỉ lưu mã lỗi vì mục tiêu là thông báo theo dòng. Một thiết kế production có thể lưu **error index** (khi có ý nghĩa), tên cột và đối tượng cause trong kết quả nội bộ nếu cần truy vết, đồng thời tránh đưa toàn bộ chuỗi thô vào log công khai.

Đừng tự động chọn chính sách “tiếp tục” cho một giao dịch phải nguyên tử: nếu tất cả dòng cần nhập thành công hoặc cùng rollback, dừng/tổng hợp lỗi phải tuân thủ hợp đồng đó.

## 16. Những lỗi không thuộc ParseException hoặc DateTimeParseException

Những API xử lý văn bản có thể ném loại khác:

| Tình huống | Ngoại lệ hoặc cách báo lỗi điển hình |
| --- | --- |
| Integer.parseInt("bad") | NumberFormatException (unchecked) |
| LocalDate.parse("not-date") | DateTimeParseException (unchecked) |
| SimpleDateFormat.parse("bad") | ParseException (checked) |
| NumberFormat.parse("bad") | ParseException (checked) |
| DateTimeFormatter.ofPattern("pattern invalid") | IllegalArgumentException khi pattern không hợp lệ |
| Gọi một số API parse với đối số null | Có thể NullPointerException, tùy API |
| Đọc file trước khi parse | IOException hoặc ngoại lệ I/O tương ứng |
| Chọn ngày hợp lệ nhưng vượt giới hạn nghiệp vụ | Lỗi validation do ứng dụng định nghĩa |
| Chuyển số lớn xuống kiểu hẹp không chính xác | ArithmeticException nếu dùng toIntExact/intValueExact |
| Parse dữ liệu JSON/XML bằng thư viện khác | Ngoại lệ riêng theo thư viện, không mặc định là hai loại trong bài |

Không có một **ParseException chung cho mọi parser Java**. Đừng đặt một **catch(ParseException)** rồi kỳ vọng nó bắt luôn DateTimeParseException hoặc NumberFormatException. Nếu cần quy ước lỗi thống nhất ở tầng application, xây một mô hình **error code / field / message / cause** và map từng loại parser tại ranh giới tương ứng.

## 17. Các bẫy dữ liệu và bảo mật

1. **Giá trị gốc trong exception:** DateTimeParseException.getParsedString có thể chứa toàn bộ văn bản bị từ chối. Không log nguyên văn khi có token, thông tin người dùng hoặc chuỗi rất dài.
2. **Thông điệp của parser:** getMessage có thể gắn giá trị input và các chi tiết triển khai. Đừng gửi toàn bộ cho client như một hợp đồng API.
3. **Vị trí lỗi:** error index là chỉ số phục vụ chẩn đoán, không nhất thiết là số cột trong UI. Java dùng chỉ số trên chuỗi; các ký tự Unicode đặc biệt có thể khiến cách đếm “ký tự nhìn thấy” khác cách đếm offset.
4. **Khoảng trắng:** LocalDate.parse theo ISO không mặc định cho phép ký tự thừa; nếu giao diện cho phép khoảng trắng đầu/cuối, chỉ dùng strip/trim khi đó là chính sách được công bố.
5. **Độ dài đầu vào:** giới hạn số ký tự và số bản ghi trước khi thực hiện các phân tích phức tạp, nhất là khi nhận dữ liệu từ nguồn không tin cậy.
6. **Múi giờ:** parse LocalDateTime thành công không xác định được Instant nếu thiếu zone/offset. Không được biến việc parse không lỗi thành bằng chứng dữ liệu thời điểm chính xác.
7. **Mặc định hệ thống:** SimpleDateFormat có trạng thái timezone/locale, DateTimeFormatter.ofPattern không chỉ rõ locale có thể phụ thuộc cài đặt. Hãy đặt cấu hình tường minh tại ranh giới dữ liệu.
8. **Thread safety:** không chia sẻ cùng SimpleDateFormat mutable qua nhiều thread mà không kiểm soát. DateTimeFormatter immutable và có thể tái sử dụng an toàn hơn.
9. **Dữ liệu không tồn tại theo lịch:** strict resolver giúp ngăn chỉnh ngày âm thầm; kiểm tra ngày nhuận và ngày cuối tháng.
10. **Không parse text message của ngoại lệ:** để quyết định code/loại lỗi, hãy dùng loại exception, vị trí và cấu trúc dữ liệu của ứng dụng, không dùng nội dung getMessage thay cho contract.

## 18. Sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Nghĩ ParseException và DateTimeParseException đều checked | Chữ ký xử lý lỗi sai | Nhớ java.text checked, java.time unchecked |
| Catch ParseException để bắt lỗi LocalDate.parse | Không bắt được DateTimeParseException | Bắt DateTimeParseException khi thích hợp |
| Catch DateTimeParseException để xử lý SimpleDateFormat.parse | Không giải quyết checked ParseException | Bắt/khai báo ParseException |
| setLenient(false) rồi mặc định parser đọc hết chuỗi | Có thể bỏ hậu tố sai | Dùng ParsePosition kiểm tra getIndex == text.length |
| Dùng ofPattern("dd/MM/yyyy") + STRICT và nghĩ giống uuuu | Year-of-era có thể không resolve khi thiếu era | Dùng uuuu cho ISO proleptic year |
| Mặc định ofPattern luôn STRICT | ofPattern mặc định SMART | Đặt withResolverStyle(STRICT) khi cần |
| Chấp nhận ngày 29/02/2023 vì pattern đúng | Ngày không tồn tại | Resolver strict và kiểm tra lịch |
| In java.util.Date.toString rồi so với chuỗi ngày | Hiển thị phụ thuộc múi giờ | Format có timezone/locale rõ hoặc dùng LocalDate |
| Log ex.getParsedString cho mọi trường | Có thể lộ dữ liệu | Chỉ ghi dữ liệu được phép, ưu tiên field/code |
| Tin error index luôn chỉ đúng ký tự lỗi nghiệp vụ | Parser có hai giai đoạn; chỉ số có ngữ cảnh | Dùng index hỗ trợ chẩn đoán, không dùng làm truth duy nhất |
| Parse LocalDateTime rồi suy ra UTC | Thiếu zone/offset | Dùng OffsetDateTime, ZonedDateTime hoặc Instant đúng dữ liệu |
| Dùng chung SimpleDateFormat mutable giữa thread | Có nguy cơ sai kết quả/data race | Tạo instance riêng hoặc dùng DateTimeFormatter |
| Parse String ngày theo tên tháng mà không chỉ định Locale | Tùy máy, có thể lỗi | Khai báo Locale |
| Catch Exception quá rộng rồi trả null | Che lỗi không liên quan và mất nguyên nhân | Bắt đúng loại và giữ cause |
| Chuyển parser error chỉ thành chuỗi | Mất stack trace, lỗi gốc | Wrapper (message, cause) hoặc Result có mã rõ |
| Không kiểm tra null/rỗng | Có thể phát sinh lỗi kỹ thuật thay vì validation | Kiểm tra trước và báo lỗi trường |

## 19. Checklist triển khai parser đáng tin

Trước khi viết hoặc review một đoạn parse dữ liệu:

1. **Xác định kiểu dữ liệu đích:** Date, LocalDate, LocalDateTime, OffsetDateTime hay Instant? Có cần timezone không?
2. **Xác định format:** ISO chuẩn, dd/MM/uuuu, tháng bằng chữ hay định dạng theo locale?
3. **Đặt resolver style:** STRICT nếu ngày phải tồn tại chính xác, không chỉnh sửa ngầm.
4. **Quyết định chính sách whitespace:** có bỏ đầu/cuối không; có chấp nhận hậu tố không?
5. **Đọc hợp đồng ngoại lệ:** checked ParseException, unchecked DateTimeParseException, NumberFormatException hay loại khác?
6. **Kiểm tra toàn chuỗi:** nhất là với java.text.ParsePosition.
7. **Xử lý giá trị thiếu:** null/rỗng có thông báo riêng hay không?
8. **Giữ ngữ cảnh:** tên trường, dòng CSV, format yêu cầu, mã lỗi.
9. **Bảo toàn cause:** nếu chuyển sang domain exception, dùng constructor nhận cause.
10. **Bảo vệ thông tin:** tránh log parsedString/message nguyên văn nếu nhạy cảm.
11. **Xem thread-safety:** formatter mutable hay immutable; có bị dùng chung nhiều thread?
12. **Viết test:** năm nhuận, cuối tháng, sai separator, chuỗi dư, locale, offset/zone, null, input quá dài.
13. **Tầng xử lý:** nếu có thể sửa ở ranh giới input thì phản hồi validation; nếu không, để exception được ghi nhận và lan truyền đúng hợp đồng.
14. **Không đồng nhất exception với validation:** parser thành công vẫn có thể không thỏa mãn quy tắc nghiệp vụ.

## 20. Câu hỏi tự kiểm tra

**1.** ParseException và DateTimeParseException có cùng tính checked không?  
**Không.** ParseException checked; DateTimeParseException unchecked.

**2.** SimpleDateFormat.parse(String) với dữ liệu không hợp lệ thường công bố loại lỗi nào?  
**ParseException**, nên caller cần catch hoặc throws theo hợp đồng checked.

**3.** LocalDate.parse("2026-02-30") có tạo được ngày không?  
**Không.** ISO strict từ chối ngày không tồn tại bằng DateTimeParseException.

**4.** SimpleDateFormat.setLenient(false) có bảo đảm parser đọc toàn bộ chuỗi không?  
**Không.** Cần kiểm tra ParsePosition hoặc một cơ chế tương đương.

**5.** DateTimeParseException có những getter riêng nào hữu ích?  
**getParsedString()** và **getErrorIndex()**.

**6.** ParseException có getter chuyên dụng lấy lại toàn bộ chuỗi đầu vào không?  
**Không.** Có **getErrorOffset()**; ứng dụng phải tự giữ ngữ cảnh đầu vào nếu cần.

**7.** DateTimeFormatter.ofPattern("dd/MM/uuuu") mặc định resolver style nào?  
**SMART**. Dùng **withResolverStyle(STRICT)** nếu muốn ngày hợp lệ tuyệt đối.

**8.** Vì sao dd/MM/yyyy + STRICT có thể không resolve thành LocalDate?  
Vì yyyy là **year-of-era**; thiếu era có thể không đủ để xác định proleptic year. Dùng **uuuu** khi phù hợp lịch ISO.

**9.** NumberFormat.parse(String) ném ParseException hay NumberFormatException trong API tiêu chuẩn?  
**ParseException checked**; khác với Integer.parseInt.

**10.** Locale và ZoneId có tương đương không?  
**Không.** Locale phục vụ ngôn ngữ/định dạng; ZoneId định nghĩa vùng múi giờ.

**11.** Bọc lỗi bằng new InvalidFieldException("date", message, cause) giúp gì?  
Giữ **thông điệp có ngữ cảnh**, **tên trường** và **cause** của lỗi parse ban đầu.

**12.** DateTimeParseException.getErrorIndex() có thể dùng làm số cột CSV trực tiếp không?  
**Không nên.** Đó là vị trí parser báo trong chuỗi được parse; cần chuyển sang tọa độ record/field.

**13.** DateTimeFormatter.parse với ParsePosition có luôn giống hành vi null-khi-sai của java.text không?  
**Không.** Cần đọc hợp đồng overload; DateTimeFormatter có thể ném DateTimeParseException.

**14.** Parse ngày hợp lệ theo pattern đã đủ để tạo đúng Instant chưa?  
**Chưa.** Nếu thiếu offset hoặc zone, thời điểm toàn cục chưa được xác định.

## Tài liệu tham khảo chuẩn

- [Java SE 21 — java.text.ParseException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ParseException.html).
- [Java SE 21 — java.text.ParsePosition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ParsePosition.html).
- [Java SE 21 — java.text.SimpleDateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html).
- [Java SE 21 — java.text.NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html).
- [Java SE 21 — java.time.format.DateTimeParseException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeParseException.html).
- [Java SE 21 — java.time.format.DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html).
- [Java SE 21 — java.time.format.ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html).
- [Java SE 21 — java.time.LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html).
- [JLS 21 — §11.1.1 Checked và unchecked exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.1).

**Ghi nhớ:** ParseException là checked exception điển hình của **java.text**, còn DateTimeParseException là unchecked exception của **java.time**. Để parse đáng tin, hãy chọn đúng kiểu đích, formatter, locale và resolver style, kiểm tra **toàn chuỗi** khi cần, bảo toàn nguyên nhân lỗi và luôn bổ sung ngữ cảnh dữ liệu đầu vào thay vì để message/offset của parser làm hợp đồng nghiệp vụ.
