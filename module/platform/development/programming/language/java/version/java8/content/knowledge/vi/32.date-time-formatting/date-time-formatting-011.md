# Kiểm thử chuỗi ngày giờ: hợp lệ, sai định dạng và sai ngày thực tế (Java 8+)

## 1. Vì sao một chuỗi trông giống ngày chưa chắc là ngày hợp lệ?

Giả sử hệ thống nhận ngày sinh, ngày giao hàng hoặc ngày hẹn theo mẫu **dd/MM/uuuu**. Những chuỗi dưới đây trông khá giống nhau nhưng có ý nghĩa khác nhau:

- **29/02/2024**: đúng mẫu, là ngày có thật vì 2024 nhuận.
- **29/02/2025**: đúng mẫu ký tự nhưng **không phải ngày có thật**, vì 2025 không nhuận.
- **31/04/2025**: đúng mẫu ký tự nhưng tháng 4 chỉ có 30 ngày.
- **1/03/2025**: có thể là một ngày có thật khi hiểu là 01/03, nhưng **sai quy ước hai chữ số của dd**.
- **01-03-2025**: có thể hiểu được nhưng dùng dấu phân cách không đúng contract.
- **01/03/2025 extra**: có tiền tố đúng mẫu nhưng có dữ liệu dư ngoài định dạng.
- **15/13/2025**: đúng dạng số/dấu phân cách, nhưng tháng 13 không thuộc lịch ISO.
- **01/01/0000**: Java **LocalDate** chấp nhận năm 0 trong lịch ISO proleptic; nếu trường dữ liệu là ngày sinh dân sự, ứng dụng có thể phải từ chối theo chính sách.

Vì vậy, **kiểm thử chuỗi ngày giờ phải tách ba lớp**: hình thức nhập, tính hợp lệ của ngày/giờ theo lịch, và quy tắc miền dữ liệu. Một biểu thức chính quy chỉ kiểm tra mẫu ký tự **không thể** chứng minh 31/04 là ngày có thật.

Bài này sử dụng **java.time.LocalDate**, **DateTimeFormatter**, **ResolverStyle**, **DateTimeParseException**, **YearMonth**, **MonthDay** và các kiểu hiện hành trong Java SE. Chúng có từ Java 8 và vẫn còn phù hợp. Các chương trình độc lập được kiểm thử bằng Java 17, thêm ví dụ Java 8 để làm rõ tương thích.

**Kết quả mong muốn:** phân biệt được các trường hợp VALID, WRONG_FORMAT và INVALID_CALENDAR_DATE, không tự sửa dữ liệu đầu vào sai, có bộ ca kiểm thử tái lập được và biết khi nào cần kiểm tra múi giờ.

## 2. Ba tầng xác thực cần có một contract rõ

| Tầng | Câu hỏi | Công cụ phù hợp | Ví dụ bị từ chối |
| --- | --- | --- | --- |
| **1. Hình thức** | Chuỗi có đúng số chữ số và dấu phân cách không? | Kiểm tra cấu trúc hoặc formatter nghiêm ngặt | 1/03/2025, 01-03-2025 |
| **2. Ngày thực tế** | Ngày/tháng/năm có tạo được LocalDate ISO không? | LocalDate.parse và ResolverStyle.STRICT | 31/04/2025, 29/02/2025 |
| **3. Nghiệp vụ** | Ngày hợp lệ theo Java có được phép trong hệ thống không? | Kiểm tra trên LocalDate sau khi parse | Ngày sinh ở tương lai, năm 0000 nếu hệ thống chỉ cho năm dương |

Ví dụ, **01/01/0000** có thể vượt qua tầng 1 và tầng 2 nếu format dùng **uuuu**, nhưng có thể bị tầng 3 từ chối với hợp đồng "ngày sinh phải nằm trong một khoảng thời gian cho phép".

**Đừng gộp ba loại lỗi vào một thông báo mơ hồ** nếu người dùng cần biết cách sửa: sai mẫu cần hướng dẫn sửa cú pháp, sai ngày cần nhắc kiểm tra lịch, vi phạm nghiệp vụ cần thông báo giới hạn cụ thể.

Tuy nhiên, mã lỗi trả cho client không nhất thiết phải lộ toàn bộ nội dung ngoại lệ hệ thống. Trong log, dữ liệu ngày sinh là dữ liệu cá nhân, cần quy tắc riêng về việc ghi lại giá trị đã nhập.

## 3. Parse trong java.time diễn ra theo hai bước

**DateTimeFormatter** mô hình hóa việc chuyển chuỗi thành các trường ngày giờ, rồi **resolve** các trường thành đối tượng như LocalDate.

1. **Text parsing:** đọc chữ số, dấu phân cách, tên tháng, offset hoặc các trường theo pattern.
2. **Field resolving:** kiểm tra các trường đã đọc có tạo ra một giá trị hợp lệ hay không. Chính bước này dùng **ResolverStyle**.

Khi gọi:

~~~java
LocalDate date = LocalDate.parse(text, formatter);
~~~

kết quả chỉ được xem là thành công nếu formatter đọc được input **và** tạo ra một LocalDate phù hợp. Không nên chỉ kiểm tra rằng chuỗi khớp một pattern regex rồi coi đã có ngày hợp lệ.

**DateTimeFormatter là immutable và thread-safe**, có thể tạo một lần và dùng lại để parse ở nhiều thread. Không cần tạo formatter mới cho từng lời gọi nếu mẫu và locale đã cố định.

**LocalDate cũng immutable**. Khi parse thành công, một LocalDate là dữ liệu ngày đã được chuẩn hóa về cấu trúc, phù hợp để dùng trong logic, thay vì liên tục xử lý chuỗi thô.

## 4. Tạo formatter nghiêm ngặt với dd/MM/uuuu

Với hợp đồng ngày dạng **hai chữ số ngày / hai chữ số tháng / bốn chữ số năm**, có thể tạo formatter:

~~~java
DateTimeFormatter strictDmy =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed = LocalDate.parse("29/02/2024", strictDmy);
// 2024-02-29
~~~

Đoạn này cần import **java.time.LocalDate**, **java.time.format.DateTimeFormatter**, **java.time.format.ResolverStyle**, **java.util.Locale**.

**ResolverStyle.STRICT** đảm bảo khi tạo ngày ISO, tháng/ngày phải hợp lệ. Vì vậy 29/02/2025 và 31/04/2025 không được âm thầm sửa thành ngày khác.

**uuuu** biểu diễn **proleptic year** (năm theo trục ISO bao gồm năm 0); **yyyy** biểu diễn **year-of-era**. Khi parse nghiêm ngặt chỉ có năm–tháng–ngày mà không có thông tin era, dùng **uuuu** giúp các trường đủ để tạo LocalDate theo ISO.

**Locale.ROOT** làm rõ lựa chọn locale đối với pattern số; nếu pattern chứa tên tháng hoặc thứ, cần chọn một locale khớp với ngôn ngữ input. Không dựa vô thức vào locale mặc định của server.

### Thận trọng: kiểm tra chiều dài và chữ số

Pattern giúp đọc trường nhưng **nếu giao thức đòi hình thức tuyệt đối** như chỉ chữ số ASCII và chính xác dd/MM/uuuu, nên thêm bước xác nhận cấu trúc ở phía trước. Ví dụ mẫu của bài dùng một regex neo toàn chuỗi để bảo đảm chính xác 2/2/4 chữ số. Không nên mặc nhiên cho rằng mọi lựa chọn pattern, cấu hình parser và locale đều thực thi một chính sách ký tự Unicode/độ dài giống nhau.

## 5. Phân biệt STRICT, SMART và LENIENT

**ResolverStyle** có ba chế độ:

| Chế độ | Cách giải quyết trường ngày | Ý nghĩa khi kiểm thử |
| --- | --- | --- |
| **STRICT** | Từ chối ngày không tồn tại trong tháng/năm ISO | Phù hợp xác thực input cần đúng tuyệt đối |
| **SMART** | Có thể điều chỉnh ngày vượt cuối tháng về ngày cuối hợp lệ | Dễ vô tình biến input sai thành ngày khác |
| **LENIENT** | Có thể cho thành phần ngày/tháng tràn rồi cộng theo lịch | Không phù hợp khi input phải chính xác |

**DateTimeFormatter.ofPattern(...) mặc định dùng SMART**. Đây là điểm dễ bị bỏ qua khi viết validation.

Với pattern **uuuu-MM-dd**:

~~~java
DateTimeFormatter base =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);

DateTimeFormatter strict =
        base.withResolverStyle(ResolverStyle.STRICT);
DateTimeFormatter smart =
        base.withResolverStyle(ResolverStyle.SMART);
DateTimeFormatter lenient =
        base.withResolverStyle(ResolverStyle.LENIENT);
~~~

Các kết quả thực nghiệm:

~~~text
strict rejects 2025-02-29: true
smart adjusts 2025-02-29: 2025-02-28
lenient rolls 2025-02-29: 2025-03-01
lenient accepts month 13: 2026-01-03
~~~

**Phân biệt quan trọng:** các chế độ resolver quyết định **cách hợp nhất các trường thành ngày giờ**, không phải cam kết bỏ qua mọi lỗi định dạng. Chuỗi dùng dấu '-' vẫn không tự khớp với một formatter đã định nghĩa dấu '/' chỉ vì đặt LENIENT.

Nếu đang xác nhận ngày sinh, ngày đáo hạn, ngày xuất hóa đơn hoặc dữ liệu pháp lý, **không nên âm thầm chuyển 29/02/2025 thành 28/02 hay 01/03** trừ khi đó là chính sách nghiệp vụ được đặc tả rõ ràng.

## 6. Bẫy yyyy, uuuu và YYYY trong pattern

Các chữ hoa/thường trong DateTimeFormatter có ý nghĩa riêng:

- **u / uuuu**: proleptic year.
- **y / yyyy**: year-of-era.
- **Y / YYYY**: week-based-year, phụ thuộc hệ thống tuần/locale, **không** phải năm lịch thông thường.

Đối với parse nghiêm ngặt của một LocalDate theo mẫu ngày/tháng/năm không có era, nên dùng **uuuu**.

~~~java
DateTimeFormatter strictUuuu =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

DateTimeFormatter strictYyyy =
        DateTimeFormatter.ofPattern("dd/MM/yyyy", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
~~~

Với input **01/05/2025**, formatter **strictUuuu** tạo được LocalDate. Formatter **strictYyyy** chỉ có YEAR_OF_ERA mà không có ERA; khi resolve nghiêm ngặt thành LocalDate, phép parse có thể bị từ chối. Chương trình Java 8 ở phần 12 xác nhận trường hợp này.

**Không dùng YYYY thay cho uuuu chỉ vì cả hai trông giống bốn chữ số năm.** Gần cuối/đầu năm, năm tính theo tuần có thể khác năm lịch. Một sai sót pattern có thể khiến chuỗi ngày hẹn bị đưa sang năm khác mà không nhận ra qua test ở giữa năm.

**Khuyến nghị:** dùng các formatter ISO có sẵn khi giao thức dùng ISO, hoặc pattern rõ ràng **dd/MM/uuuu** kèm STRICT khi hệ thống đòi ngày/tháng/năm.

## 7. ISO_LOCAL_DATE và LocalDate.parse mặc định

Khi input theo chuẩn ISO **uuuu-MM-dd**, Java cung cấp parser có sẵn:

~~~java
LocalDate leap = LocalDate.parse("2024-02-29");
// 2024-02-29

LocalDate other = LocalDate.parse(
        "2025-05-01", DateTimeFormatter.ISO_LOCAL_DATE);
// 2025-05-01
~~~

**DateTimeFormatter.ISO_LOCAL_DATE** là formatter ISO ngày cục bộ, có chế độ kiểm tra ngày nghiêm ngặt. **LocalDate.parse(text)** sử dụng ISO_LOCAL_DATE.

Do đó:

~~~java
// Không thành công:
// LocalDate.parse("2025-02-29");
~~~

Sẽ phát sinh **DateTimeParseException**, thay vì coi 2025-02-29 là một ngày hợp lệ. Tương tự, input **01/05/2025** không phải định dạng ISO mặc định; muốn dùng dd/MM/uuuu phải truyền formatter đúng.

**Không tự thay '-' bằng '/' trước khi parse** như một giải pháp chung. Một API cần xác định chính xác hình thức mà nó nhận. Nếu chấp nhận nhiều format, hãy công bố chúng, xử lý từng format theo thứ tự được chỉ định và kiểm thử tính không mơ hồ.

## 8. Bảng ca kiểm thử: đúng ngày, sai mẫu, sai lịch

Bộ kiểm thử dưới đây dùng hợp đồng **dd/MM/uuuu**, đúng hai chữ số ngày và tháng, đúng bốn chữ số năm ISO và ký tự '/'.

| Input | Kết quả mong muốn | Giải thích |
| --- | --- | --- |
| 29/02/2024 | VALID | Năm 2024 nhuận |
| 01/03/2025 | VALID | Ngày có thật |
| 31/12/1999 | VALID | Ngày có thật |
| 29/02/2000 | VALID | Năm 2000 nhuận |
| 01/01/0000 | VALID về java.time | Proleptic ISO cho phép năm 0; nghiệp vụ có thể cấm |
| 29/02/2025 | INVALID_CALENDAR_DATE | 2025 không nhuận |
| 31/04/2025 | INVALID_CALENDAR_DATE | Tháng 4 có 30 ngày |
| 15/13/2025 | INVALID_CALENDAR_DATE | Tháng 13 không hợp lệ |
| 00/01/2025 | INVALID_CALENDAR_DATE | Không có ngày 0 |
| 32/01/2025 | INVALID_CALENDAR_DATE | Không có ngày 32 |
| 29/02/1900 | INVALID_CALENDAR_DATE | Năm 1900 không nhuận |
| 1/03/2025 | WRONG_FORMAT | Thiếu chữ số 0 ở ngày |
| 01-03-2025 | WRONG_FORMAT | Sai dấu phân cách |
| 01/03/25 | WRONG_FORMAT | Năm chỉ hai chữ số |
| 01/03/2025x | WRONG_FORMAT | Có dữ liệu dư cuối |
| Đầu chuỗi có khoảng trắng | WRONG_FORMAT | Không khớp toàn chuỗi |
| Chuỗi rỗng | WRONG_FORMAT | Thiếu dữ liệu |
| null | WRONG_FORMAT | Không có chuỗi để parse |

**Năm nhuận:** thường chia hết cho 4, nhưng năm thế kỷ chỉ nhuận nếu chia hết cho 400. **2000 là năm nhuận**, **1900 không phải năm nhuận**. Đó là lý do phải có test cho cả hai; chỉ kiểm tra year % 4 == 0 là thiếu.

**Tính hợp lệ về java.time chưa đồng nghĩa tính hợp lệ của người dùng:** ngày sinh năm 0, ngày ở tương lai hay ngày ngoài khoảng dữ liệu hệ thống có thể phải bị từ chối ở tầng domain.

## 9. Phân loại lỗi bằng kiểm tra hình thức và parser nghiêm ngặt

Đôi khi ứng dụng cần trả về hai mã lỗi riêng:

- **WRONG_FORMAT:** thiếu chữ số, sai dấu, ký tự lạ, khoảng trắng không được phép, null.
- **INVALID_CALENDAR_DATE:** đúng đúng hình thức nhưng tổ hợp năm/tháng/ngày không tồn tại trong LocalDate ISO.

Có thể chia làm hai bước:

~~~java
private static final Pattern SHAPE =
        Pattern.compile("[0-9]{2}/[0-9]{2}/[0-9]{4}");

private static final DateTimeFormatter FORMATTER =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

static String classify(String input) {
    if (input == null || !SHAPE.matcher(input).matches()) {
        return "WRONG_FORMAT";
    }
    try {
        return "VALID:" + LocalDate.parse(input, FORMATTER);
    } catch (DateTimeParseException ex) {
        return "INVALID_CALENDAR_DATE";
    }
}
~~~

Đây là **đoạn mã thuộc một class** cần import java.util.regex.Pattern, java.time.LocalDate, java.time.format.* và java.util.Locale; chương trình đầy đủ ở phần 10.

**Regex chỉ là bước cấu trúc.** Nó vẫn cho **29/02/2025**, **31/04/2025** và **15/13/2025** qua được. Chính LocalDate.parse với STRICT mới xác nhận ngày có thật. Không dùng riêng regex làm validator ngày.

**Regex này cố ý giới hạn chữ số ASCII [0-9]**, không dùng một ký hiệu số bất kỳ. Với quốc tế hóa chữ số (Arabic-Indic, v.v.), ứng dụng phải thiết kế hợp đồng khác và kiểm thử DecimalStyle/locale tương ứng.

**Không lấy getErrorIndex() làm bộ phân loại duy nhất.** DateTimeParseException có thông tin lỗi khi parse, nhưng vị trí lỗi không nói chắc đó là lỗi hình thức hay sai lịch trong mọi formatter. Muốn mã lỗi tách bạch, cần một contract input rõ và bộ kiểm tra theo các bước có nghĩa.

## 10. Chương trình Java 17 độc lập: 18 test có đối chiếu kỳ vọng

Tạo tệp **StrictDateInputDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

public class StrictDateInputDemo {
    private static final Pattern SHAPE =
            Pattern.compile("[0-9]{2}/[0-9]{2}/[0-9]{4}");
    private static final DateTimeFormatter FORMATTER =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    record Case(String input, String expected) {}

    static String classify(String input) {
        if (input == null || !SHAPE.matcher(input).matches()) {
            return "WRONG_FORMAT";
        }
        try {
            return "VALID:" + LocalDate.parse(input, FORMATTER);
        } catch (DateTimeParseException ex) {
            return "INVALID_CALENDAR_DATE";
        }
    }

    public static void main(String[] args) {
        List<Case> cases = List.of(
            new Case("29/02/2024", "VALID:2024-02-29"),
            new Case("01/03/2025", "VALID:2025-03-01"),
            new Case("31/12/1999", "VALID:1999-12-31"),
            new Case("29/02/2000", "VALID:2000-02-29"),
            new Case("01/01/0000", "VALID:0000-01-01"),
            new Case("29/02/2025", "INVALID_CALENDAR_DATE"),
            new Case("31/04/2025", "INVALID_CALENDAR_DATE"),
            new Case("15/13/2025", "INVALID_CALENDAR_DATE"),
            new Case("00/01/2025", "INVALID_CALENDAR_DATE"),
            new Case("32/01/2025", "INVALID_CALENDAR_DATE"),
            new Case("29/02/1900", "INVALID_CALENDAR_DATE"),
            new Case("1/03/2025", "WRONG_FORMAT"),
            new Case("01-03-2025", "WRONG_FORMAT"),
            new Case("01/03/25", "WRONG_FORMAT"),
            new Case("01/03/2025x", "WRONG_FORMAT"),
            new Case(" 01/03/2025", "WRONG_FORMAT"),
            new Case("", "WRONG_FORMAT"),
            new Case(null, "WRONG_FORMAT")
        );

        int passed = 0;
        for (Case test : cases) {
            String actual = classify(test.input());
            if (!test.expected().equals(actual)) {
                throw new AssertionError("input=" + test.input()
                        + " expected=" + test.expected()
                        + " actual=" + actual);
            }
            passed++;
            System.out.println(String.valueOf(test.input())
                    + " -> " + actual);
        }
        System.out.println("PASS: " + passed + "/" + cases.size());
    }
}
~~~

Biên dịch/chạy bằng JDK 17 hoặc cao hơn:

~~~bash
javac StrictDateInputDemo.java
java StrictDateInputDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
29/02/2024 -> VALID:2024-02-29
01/03/2025 -> VALID:2025-03-01
31/12/1999 -> VALID:1999-12-31
29/02/2000 -> VALID:2000-02-29
01/01/0000 -> VALID:0000-01-01
29/02/2025 -> INVALID_CALENDAR_DATE
31/04/2025 -> INVALID_CALENDAR_DATE
15/13/2025 -> INVALID_CALENDAR_DATE
00/01/2025 -> INVALID_CALENDAR_DATE
32/01/2025 -> INVALID_CALENDAR_DATE
29/02/1900 -> INVALID_CALENDAR_DATE
1/03/2025 -> WRONG_FORMAT
01-03-2025 -> WRONG_FORMAT
01/03/25 -> WRONG_FORMAT
01/03/2025x -> WRONG_FORMAT
 01/03/2025 -> WRONG_FORMAT
 -> WRONG_FORMAT
null -> WRONG_FORMAT
PASS: 18/18
~~~

**Cơ chế test:** mỗi ca khai báo **input và kết quả dự kiến**. Vòng lặp so bằng **String.equals** và ném **AssertionError** nếu khác; vì vậy chương trình không phụ thuộc JVM có bật tùy chọn **-ea** hay không. Chạy thành công chỉ khi cả 18 ca trả đúng. Đây là bộ test đơn giản không cần thư viện bên ngoài.

**Tại sao dùng record?** **record Case(...)** là cú pháp chính thức từ Java 16, nên chương trình độc lập này chạy trên Java 17+. Các API LocalDate, DateTimeFormatter và ResolverStyle đều đã có từ Java 8. Phần 12 có chương trình thuần Java 8 để kiểm tra một số quy tắc quan trọng.

## 11. Ví dụ runnable thứ hai: ba resolver và các kiểu dữ liệu ngày khác nhau

Chương trình này tách rõ việc kiểm tra **định dạng và giá trị ngày**, đồng thời minh họa một chuỗi LocalDateTime có thể đúng hình thức nhưng không phải giờ thực tại một zone đang chuyển DST.

Tạo tệp **DateResolverSemanticsDemo.java**:

~~~java
import java.time.*;
import java.time.format.*;
import java.util.Locale;

public class DateResolverSemanticsDemo {
    private static boolean rejected(String text, DateTimeFormatter fmt) {
        try {
            LocalDate.parse(text, fmt);
            return false;
        } catch (DateTimeParseException ex) {
            return true;
        }
    }

    public static void main(String[] args) {
        DateTimeFormatter base =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);
        DateTimeFormatter strict =
                base.withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter smart =
                base.withResolverStyle(ResolverStyle.SMART);
        DateTimeFormatter lenient =
                base.withResolverStyle(ResolverStyle.LENIENT);

        System.out.println("strict rejects 2025-02-29: "
                + rejected("2025-02-29", strict));
        System.out.println("smart adjusts 2025-02-29: "
                + LocalDate.parse("2025-02-29", smart));
        System.out.println("lenient rolls 2025-02-29: "
                + LocalDate.parse("2025-02-29", lenient));
        System.out.println("lenient accepts month 13: "
                + LocalDate.parse("2025-13-03", lenient));

        DateTimeFormatter strictYearOfEra =
                DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);
        System.out.println("strict yyyy rejects without era: "
                + rejected("2025-05-01", strictYearOfEra));
        System.out.println("strict uuuu succeeds: "
                + LocalDate.parse("2025-05-01", strict));
        System.out.println("ISO leap valid: "
                + LocalDate.parse("2024-02-29"));
        System.out.println("ISO invalid rejected: "
                + rejected("2025-02-29",
                           DateTimeFormatter.ISO_LOCAL_DATE));

        System.out.println("year-month: " + YearMonth.parse("2025-02"));
        System.out.println("month-day: " + MonthDay.parse("--02-29"));

        ZoneId zone = ZoneId.of("Europe/Paris");
        LocalDateTime gap =
                LocalDateTime.parse("2025-03-30T02:30");
        LocalDateTime overlap =
                LocalDateTime.parse("2025-10-26T02:30");
        System.out.println("gap syntactically valid: " + gap);
        System.out.println("gap valid offsets: "
                + zone.getRules().getValidOffsets(gap).size());
        System.out.println("overlap valid offsets: "
                + zone.getRules().getValidOffsets(overlap).size());
    }
}
~~~

Lệnh:

~~~bash
javac DateResolverSemanticsDemo.java
java DateResolverSemanticsDemo
~~~

**Stdout đúng đã kiểm chứng:**

~~~text
strict rejects 2025-02-29: true
smart adjusts 2025-02-29: 2025-02-28
lenient rolls 2025-02-29: 2025-03-01
lenient accepts month 13: 2026-01-03
strict yyyy rejects without era: true
strict uuuu succeeds: 2025-05-01
ISO leap valid: 2024-02-29
ISO invalid rejected: true
year-month: 2025-02
month-day: --02-29
gap syntactically valid: 2025-03-30T02:30
gap valid offsets: 0
overlap valid offsets: 2
~~~

**Tính đúng:** chương trình chạy với dữ liệu ngày cố định, không lấy ngày hiện tại. Hai trường hợp Europe/Paris kiểm tra **ZoneRules** của JDK. Đối với lịch tương lai, các quy tắc múi giờ có thể được cập nhật theo dữ liệu tzdb, vì vậy cần kiểm thử phiên bản tzdb triển khai.

## 12. Chương trình tương thích Java 8: uuuu và yyyy

Khi phải hỗ trợ runtime Java 8, vẫn có **java.time** và **ResolverStyle.STRICT**. Không cần chuyển sang API parse ngày giờ cũ.

Tạo **YearPatternJava8Demo.java**:

~~~java
import java.time.*;
import java.time.format.*;
import java.util.Locale;

public class YearPatternJava8Demo {
    static boolean invalid(String text, DateTimeFormatter fmt) {
        try {
            LocalDate.parse(text, fmt);
            return false;
        } catch (DateTimeParseException e) {
            return true;
        }
    }

    public static void main(String[] args) {
        DateTimeFormatter strictUuuu =
                DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter strictYyyy =
                DateTimeFormatter.ofPattern("dd/MM/yyyy", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        System.out.println("strict uuuu: "
                + LocalDate.parse("01/05/2025", strictUuuu));
        System.out.println("strict yyyy no era: "
                + invalid("01/05/2025", strictYyyy));
        System.out.println("bad calendar: "
                + invalid("31/04/2025", strictUuuu));
    }
}
~~~

Lệnh chạy (mã đã được biên dịch với mục tiêu Java 8):

~~~bash
javac YearPatternJava8Demo.java
java YearPatternJava8Demo
~~~

Stdout:

~~~text
strict uuuu: 2025-05-01
strict yyyy no era: true
bad calendar: true
~~~

**Phân biệt phiên bản:** chương trình này chỉ dùng API và cú pháp có từ Java 8. Chương trình 18 ca ở phần 10 dùng **record** nên cần Java 17+.

## 13. Sai định dạng khác sai ngày thực tế như thế nào?

Một validator nên diễn đạt rõ các trường hợp:

**Sai định dạng (lexical/shape):**

~~~text
1/03/2025
01-03-2025
01/03/25
01/03/2025 extra
~~~

Những chuỗi đó có thể mang ý nghĩa ngày trong cách đọc của con người, nhưng không đúng contract **dd/MM/uuuu** với dấu '/' và độ dài cố định.

**Sai ngày thực tế (calendar invalid):**

~~~text
29/02/2025
31/04/2025
00/01/2025
15/13/2025
29/02/1900
~~~

Các chuỗi này đều khớp biểu thức **[0-9]{2}/[0-9]{2}/[0-9]{4}**, nhưng LocalDate ISO không thể tạo ngày tương ứng.

**Hợp lệ về mặt Java nhưng sai nghiệp vụ:**

~~~text
01/01/0000
31/12/2999
~~~

LocalDate hỗ trợ khoảng năm rộng theo lịch proleptic. Một ngày sinh năm 0000 hoặc 2999 có thể không có ý nghĩa trong ứng dụng. Cần một quy tắc domain bổ sung, ví dụ ngày sinh nằm trong khoảng cho phép và không sau ngày tham chiếu. Không đưa các quy tắc như "phải từ 1900" vào validator chung nếu sản phẩm chưa yêu cầu.

## 14. Kiểm tra năm nhuận đúng cách

Trong lịch Gregorian mà LocalDate ISO sử dụng:

- Năm chia hết cho 4 thường là năm nhuận.
- Nếu chia hết cho 100 thì **không** nhuận, trừ khi còn chia hết cho 400.
- Vì vậy năm 2000 nhuận, năm 1900 không nhuận; năm 2024 nhuận, 2025 không nhuận.

~~~java
System.out.println(Year.isLeap(2024)); // true
System.out.println(Year.isLeap(2025)); // false
System.out.println(Year.isLeap(1900)); // false
System.out.println(Year.isLeap(2000)); // true
~~~

Đây là mã minh họa bên trong một method có import java.time.Year.

**Không cần tự triển khai thuật toán năm nhuận chỉ để xác thực một LocalDate.** DateTimeFormatter ở STRICT và LocalDate.parse đã kiểm tra xem 29/02 có hợp lệ theo năm/tháng tương ứng hay không. Year.isLeap có ích nếu UI hoặc nghiệp vụ cần chủ động tính số ngày trong tháng.

Các test nên chứa **29/02/2024**, **29/02/2025**, **29/02/1900** và **29/02/2000** để phát hiện code tự viết đơn giản quá mức.

## 15. Xác thực ngày không đồng nghĩa xác thực giờ hoặc múi giờ

**LocalDate** chỉ có ngày. Nếu client gửi ngày cùng giờ, cần chọn kiểu đúng:

| Dữ liệu được gửi | Mô hình thường phù hợp |
| --- | --- |
| 2025-05-01 | LocalDate |
| 15:30 | LocalTime |
| 2025-05-01T15:30 | LocalDateTime |
| 2025-05-01T08:30:00Z | Instant |
| 2025-05-01T15:30+07:00 | OffsetDateTime |
| Ngày giờ có quy tắc Europe/Paris | ZonedDateTime/ZoneId |

**Đừng cố parse timestamp có dấu Z bằng LocalDate.parse** rồi tự cắt 10 ký tự đầu. Nếu mục tiêu là ngày trong một vùng nhất định, trước tiên parse timestamp như Instant/OffsetDateTime, sau đó chuyển sang ZoneId nghiệp vụ để lấy ngày.

Ví dụ:

~~~java
Instant instant = Instant.parse("2025-05-01T18:00:00Z");

LocalDate inVietnam = instant
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toLocalDate();

// 2025-05-02, khác ngày UTC của instant.
~~~

Ở đây 18:00 UTC + 7 giờ là 01:00 ngày tiếp theo tại Việt Nam. Đó là lý do không thể chỉ lấy phần ngày của chuỗi UTC để tính ngày theo cửa hàng ở vùng khác.

**Nếu input là ngày sinh hoặc hạn hợp đồng theo lịch, giữ LocalDate; đừng tự thêm một offset UTC giả.**

## 16. Giờ local qua DST có thể parse đúng nhưng không tồn tại tại zone

Ví dụ **LocalDateTime.parse("2025-03-30T02:30")** tạo được một ngày giờ cục bộ hợp lệ về trường (30/03, 02:30). Nhưng tại **Europe/Paris**, ngày 30/03/2025 đồng hồ nhảy từ 02:00 sang 03:00: **02:30 không tồn tại**.

~~~java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime gap = LocalDateTime.parse(
        "2025-03-30T02:30");

int offsets = paris.getRules().getValidOffsets(gap).size();
// 0: không có offset hợp lệ.
~~~

Với giờ lặp lại trong đêm đổi giờ mùa thu:

~~~java
LocalDateTime overlap = LocalDateTime.parse(
        "2025-10-26T02:30");

int offsets = paris.getRules().getValidOffsets(overlap).size();
// 2: có hai offset hợp lệ.
~~~

**Vậy "chuỗi ngày giờ hợp lệ" có ít nhất hai nghĩa:**

1. Các trường LocalDateTime tạo được một giá trị local.
2. LocalDateTime đó xác định được thời điểm thật ở một **ZoneId** hay chưa.

Nếu sản phẩm đặt lịch theo zone cụ thể, phải xác định quy tắc **gap/overlap**: từ chối giờ không tồn tại, dịch giờ đến thời điểm hợp lệ hoặc cho người dùng chọn offset khi trùng giờ. Không nên âm thầm áp một mặc định mà khách hàng không biết.

**ZoneRules.getValidOffsets** giúp phân biệt 0/1/2 offset trong đa số trường hợp; dữ liệu timezone có thể được cập nhật theo thay đổi của quốc gia.

## 17. Tránh parse mơ hồ và chuẩn hóa âm thầm

**Chuỗi như 01/02/2025 có thể mang nghĩa ngày 1 tháng 2 hoặc tháng 1 ngày 2** nếu client và server không thống nhất định dạng. Vì thế giao diện/API nên xác định một định dạng trao đổi duy nhất như ISO **uuuu-MM-dd**, còn UI có thể hiển thị **dd/MM/uuuu** theo locale.

Đừng tạo validator chấp nhận bất kỳ chuỗi có dấu '/', '-', '.', chữ tháng hoặc dấu cách rồi thử nhiều formatter không theo thứ tự. Cách thử hết các format có thể vô tình diễn giải **03/04/2025** sai ý nghĩa nếu cả dd/MM và MM/dd đều được cho phép.

Nếu phải hỗ trợ nhiều định dạng cũ:

1. Tài liệu hóa **danh sách format được phép**.
2. Quy định **thứ tự ưu tiên** và xử lý input mơ hồ bằng cách từ chối hoặc yêu cầu nguồn cung cấp format rõ.
3. Dùng **STRICT** cho từng định dạng có ngày thực tế.
4. Sau parse, chuyển về **LocalDate** để xử lý, không lưu chuỗi lẫn lộn.
5. Đoạn API mới nên hướng tới một định dạng trao đổi nhất quán, không mở rộng chấp nhận thiếu kiểm soát.

### Khoảng trắng và chữ hoa/thường

Nếu contract yêu cầu chính xác, **" 01/03/2025"** khác **"01/03/2025"**. Gọi trim() trước khi xác thực là một quyết định chuẩn hóa input cần được công bố; không mặc nhiên là đúng. Với các trường text gồm tên tháng (Jan/February hoặc ngôn ngữ khác), cần Locale và chính sách case-sensitivity rõ.

**DateTimeFormatterBuilder.parseCaseInsensitive()** có thể hỗ trợ khi thật sự cần parser không phân biệt hoa/thường, nhưng không giải quyết ngày không tồn tại. Không nên biến việc "thoải mái về chữ hoa" thành cho phép điều chỉnh sai ngày lịch.

## 18. Thực hành với DateTimeParseException

Khi parse sai định dạng hoặc sai lịch, **LocalDate.parse** có thể ném **DateTimeParseException** (một subclass của **DateTimeException**).

~~~java
try {
    LocalDate date = LocalDate.parse(
            "31/04/2025", strictDmy);
    System.out.println(date);
} catch (DateTimeParseException ex) {
    System.out.println("Ngày không hợp lệ");
}
~~~

Đây là mã minh họa trong một method có biến formatter **strictDmy** và import phù hợp.

Exception cung cấp:

- **getParsedString()**: chuỗi được thử parse.
- **getErrorIndex()**: vị trí lỗi do parser báo.
- **getMessage()**: thông tin kỹ thuật để chẩn đoán.

**Không suy từ getErrorIndex() rằng mọi lỗi cùng một loại.** Một lỗi resolving ngày thực tế có thể được báo khác với lỗi lexical. Tùy formatter, thông tin vị trí không nhất thiết mô tả nguyên nhân theo ý nghĩa nghiệp vụ.

**Không gửi nguyên getMessage hoặc getParsedString ra client hoặc log đại trà** với dữ liệu nhạy cảm như ngày sinh. Nên trả mã lỗi có ý nghĩa, ví dụ WRONG_FORMAT, INVALID_CALENDAR_DATE, OUT_OF_ALLOWED_RANGE; log có kiểm soát theo chính sách bảo vệ dữ liệu.

**Phân biệt ngoại lệ từ factory:** LocalDate.of(year,month,day) có thể ném DateTimeException khi giá trị ngoài phạm vi; đây không phải lời gọi parse một chuỗi. Khi xây validator, catch đúng ngoại lệ bạn mong đợi và không che lỗi lập trình không liên quan.

## 19. Kiểm thử format so với kiểm thử parser

Một số hệ thống nhầm **định dạng đầu ra** với **xác thực đầu vào**.

~~~java
DateTimeFormatter fmt =
        DateTimeFormatter.ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate date = LocalDate.of(2025, 3, 1);
String formatted = date.format(fmt);
// 01/03/2025
~~~

**format(...)** có ngày LocalDate đã hợp lệ nên không kiểm thử liệu một chuỗi input sai ngày có bị từ chối hay không. Muốn kiểm thử parser phải gọi parse trên nhiều chuỗi hợp lệ và không hợp lệ.

### Test round-trip

~~~java
LocalDate original = LocalDate.of(2024, 2, 29);
String text = original.format(fmt);
LocalDate after = LocalDate.parse(text, fmt);

boolean same = original.equals(after); // true
~~~

Round-trip cho biết formatter có thể tái tạo một giá trị nhất định, nhưng **không chứng minh** nó từ chối mọi input không hợp lệ. Cần cả ca từ chối 29/02/2025, 31/04/2025, sai dấu và đầu vào dư.

## 20. Mở rộng thành unit test trong dự án

Bộ **table-driven test** ở phần 10 đã thực thi 18 ca mà không cần dependency. Trong dự án dùng **JUnit Jupiter** hiện hành, có thể chuyển các ca này thành **parameterized tests** và nhóm theo mong đợi:

- Ca hợp lệ: assertEquals với LocalDate dự kiến, không chỉ assertDoesNotThrow.
- Ca sai hình thức: assert mã WRONG_FORMAT hoặc kiểm tra parser từ chối, theo contract.
- Ca đúng hình thức nhưng ngày không tồn tại: assertThrows(DateTimeParseException.class) với parser STRICT.
- Ca năm 0 hoặc ngày ngoài phạm vi cho phép: parse thành LocalDate thành công, sau đó assert điều kiện domain từ chối.
- Ca ngày giờ có ZoneId: kiểm tra gap/overlap nếu tính một mốc Instant thực.

Ví dụ về cách kiểm tra chính xác ngày đầu ra (đoạn minh họa trong lớp test JUnit có dependency phù hợp):

~~~java
@Test
void leapDateShouldParse() {
    LocalDate actual = LocalDate.parse(
            "29/02/2024", STRICT_DMY);
    assertEquals(LocalDate.of(2024, 2, 29), actual);
}

@Test
void invalidLeapDayShouldFail() {
    assertThrows(DateTimeParseException.class,
        () -> LocalDate.parse("29/02/2025", STRICT_DMY));
}
~~~

Đoạn này cần **JUnit Jupiter** và biến **STRICT_DMY** được khai báo trong class test; đây **không** phải chương trình chạy độc lập. Khi triển khai, dùng dependency JUnit Jupiter được tổ chức phê duyệt, không đặt giả định một phiên bản library cụ thể trong logic parse.

**Không cần dùng framework test để chứng minh một API có đúng hay không**; nhưng với CI/production, kiểm thử tự động sau mỗi thay đổi formatter, contract hoặc phiên bản JDK rất quan trọng.

## 21. Chính sách domain sau khi parse

Một ngày **đúng lịch** có thể vẫn không được chấp nhận trong sản phẩm:

- Ngày sinh ở tương lai.
- Ngày hợp đồng quá xa quá khứ.
- Ngày giao hàng nằm ngoài cửa sổ vận hành.
- Ngày hẹn rơi vào ngày nghỉ hoặc giờ không làm việc.
- Ngày 29/02 với yêu cầu kỷ niệm trong một năm không nhuận.
- Năm 0000 mà dữ liệu nghiệp vụ chỉ cho các năm dân sự dương.

Ví dụ riêng cho ngày sinh, với **ngày tham chiếu được truyền vào**:

~~~java
static boolean allowedBirthDate(
        LocalDate dob, LocalDate referenceDay) {
    LocalDate earliest = LocalDate.of(1900, 1, 1);
    return dob != null
            && !dob.isBefore(earliest)
            && !dob.isAfter(referenceDay);
}
~~~

Đây là **quy tắc ví dụ**: năm 1900 không phải giới hạn mặc định của Java hoặc quy định bắt buộc. Ứng dụng phải định nghĩa giới hạn theo yêu cầu thực tế.

**Ngày tham chiếu nên được truyền vào hoặc lấy từ Clock/ZoneId nghiệp vụ**, thay vì âm thầm dùng giờ server. Với input là ngày trong lịch, đừng biến nó thành Instant ở 00:00 UTC rồi so vì việc đổi zone có thể dịch ngày.

## 22. Checklist kiểm thử cho hệ thống thực tế

| Nhóm | Ca tối thiểu |
| --- | --- |
| Hợp lệ | Một ngày thường, cuối tháng, cuối năm, 29/02 năm nhuận |
| Sai hình thức | Thiếu số 0, sai dấu, sai số chữ số năm, chữ lẫn số |
| Thiếu/dư | Chuỗi rỗng, null, khoảng trắng đầu/cuối, hậu tố dư |
| Sai lịch | 31/04, 31/06, 29/02 năm thường, tháng 0, tháng 13, ngày 0, ngày 32 |
| Năm nhuận đặc biệt | 1900 không nhuận, 2000 nhuận, 2024 nhuận, 2025 không nhuận |
| Resolver | STRICT reject, SMART điều chỉnh, LENIENT có thể tràn |
| Pattern | uuuu vs yyyy, cảnh giác YYYY |
| Locale | Input tháng dạng text phải có Locale cố định |
| Timezone | LocalDateTime hợp lệ nhưng gap/overlap khi đặt ở ZoneId |
| Domain | Năm 0, ngày sinh tương lai, giới hạn hệ thống |
| Contract | dd/MM/uuuu và ISO uuuu-MM-dd không bị trộn tùy tiện |
| Bảo mật | Không log giá trị nhạy cảm hoặc đưa lỗi nội bộ cho client |
| Regression | Lặp test trong CI sau thay đổi formatter, JDK, locale hoặc tzdb |

Một bộ kiểm thử tốt cần đảm bảo **cùng input, cùng formatter và cùng policy thì cho cùng kết quả**. Không phụ thuộc Locale.getDefault hoặc ZoneId.systemDefault nếu nghiệp vụ không cho phép.

### Đảm bảo không tự sửa input sai

Khi người dùng nhập 31/04/2025, hệ thống có thể quyết định trả lỗi rõ thay vì biến thành 30/04/2025. Nếu một quy trình nghiệp vụ muốn "điều chỉnh ngày cuối tháng", đó nên là một thao tác riêng **sau khi đã xác nhận ý định**, không phải tác dụng phụ ẩn của việc parse ở SMART.

## 23. Những sai lầm thường gặp

1. **Chỉ dùng regex:** 29/02/2025 có hình thức đúng nhưng ngày không tồn tại.
2. **Dùng ofPattern mà không đặt STRICT:** mặc định SMART có thể điều chỉnh ngày cuối tháng.
3. **Dùng yyyy thay uuuu trong STRICT rồi thiếu ERA:** năm-of-era không tự trở thành proleptic-year khi resolve.
4. **Dùng YYYY cho năm lịch:** đây là week-based-year, có thể khác năm dương lịch ở đầu/cuối năm.
5. **Bỏ qua năm 1900 và 2000:** thiếu quy tắc năm nhuận thế kỷ.
6. **Tự chuẩn hóa bằng trim hoặc thay dấu:** làm đầu vào sai contract trở thành hợp lệ mà không được công bố.
7. **Dùng LocalDate.parse cho timestamp:** mất giờ, offset và ngữ nghĩa thời điểm.
8. **Coi LocalDateTime có nghĩa Instant:** thiếu ZoneId; gap/overlap có thể tạo 0 hoặc 2 offset.
9. **Chỉ test chuỗi đúng, không test chuỗi sai:** không chứng minh parser nghiêm ngặt.
10. **Chỉ test format(date), không test parse(text):** format và parse là hai hướng có mục tiêu khác nhau.
11. **Coi parse thành công là hợp lệ nghiệp vụ:** năm 0 hoặc ngày quá xa tương lai vẫn có thể được LocalDate chấp nhận.
12. **Dựa vào default locale:** parser đổi hành vi theo môi trường.
13. **Hiển thị nguyên exception cho người dùng:** thông điệp kỹ thuật và dữ liệu thô có thể không phù hợp hoặc nhạy cảm.
14. **Dùng đối tượng formatter mutable kiểu cũ:** DateTimeFormatter của java.time có thể tái sử dụng an toàn; không cần sử dụng các API ngày giờ cũ làm giải pháp chính.

## 24. Bài tập kèm đáp án

**Bài 1.** Chuỗi "29/02/2024" với dd/MM/uuuu + STRICT có hợp lệ không?

**Đáp án:** Có; LocalDate là **2024-02-29** vì 2024 nhuận.

**Bài 2.** "29/02/2025" sai ở đâu?

**Đáp án:** Đúng hình thức 2/2/4, nhưng **không có ngày 29/02/2025**. Mã lỗi theo contract mẫu: INVALID_CALENDAR_DATE.

**Bài 3.** "01-03-2025" có thể đọc ra ngày không?

**Đáp án:** Có thể nếu contract khác dùng dấu '-', nhưng theo dd/MM/uuuu phải trả WRONG_FORMAT, không tự đổi dấu.

**Bài 4.** SMART xử lý "2025-02-29" như thế nào với pattern uuuu-MM-dd?

**Đáp án:** Tạo LocalDate **2025-02-28**. Đây là lý do không dùng SMART để kiểm tra dữ liệu phải chính xác.

**Bài 5.** LENIENT xử lý "2025-13-03" thế nào?

**Đáp án:** Chuyển thành **2026-01-03**. Cơ chế tràn tháng có thể hữu ích trong phép tính lịch, nhưng không nên làm validation đầu vào mặc định.

**Bài 6.** Cách xác nhận chuỗi đúng hình thức nhưng ngày không tồn tại?

**Đáp án:** Bước một kiểm tra hình thức; bước hai parse **LocalDate** bằng formatter STRICT và bắt DateTimeParseException. Không chỉ dùng regex.

**Bài 7.** Vì sao uuuu khác yyyy?

**Đáp án:** uuuu là proleptic-year; yyyy là year-of-era, có thể thiếu thông tin era trong resolver nghiêm ngặt. Còn YYYY là week-based-year.

**Bài 8.** "01/01/0000" có hợp lệ không?

**Đáp án:** LocalDate theo ISO proleptic hỗ trợ năm 0, nên có thể parse được với uuuu. Nếu đây là ngày sinh dân sự, tầng domain có thể từ chối.

**Bài 9.** LocalDateTime "2025-03-30T02:30" có hợp lệ không?

**Đáp án:** Hợp lệ về trường local; nhưng **Europe/Paris** có DST gap tại giờ này, nên không có offset hợp lệ trong zone đó.

**Bài 10.** Đối với dữ liệu giờ có offset, có nên cắt 10 ký tự đầu để kiểm tra LocalDate?

**Đáp án:** Không nếu nghiệp vụ muốn ngày địa phương của một vùng. Hãy parse Instant hoặc OffsetDateTime, rồi chuyển về ZoneId được yêu cầu mới lấy LocalDate.

**Bài 11.** Chỉ format một LocalDate hợp lệ rồi parse lại có đủ kiểm tra validator không?

**Đáp án:** Không. Round-trip không bao phủ dữ liệu nhập sai, ngày không có thật, sai dấu, null hoặc chuỗi dư.

**Bài 12.** Khi validator trả lỗi, có nên log toàn bộ chuỗi ngày sinh và getMessage của exception không?

**Đáp án:** Không mặc định. Chọn mã lỗi và logging đã xét bảo vệ dữ liệu, quyền truy cập, thông tin kỹ thuật cần thiết.

## 25. Tổng kết và tài liệu chính thức

**Những quy tắc quan trọng nhất:**

1. **Đúng hình thức không đồng nghĩa đúng ngày lịch.** Regex chỉ kiểm tra cấu trúc; LocalDate.parse + STRICT xác nhận ngày tồn tại.
2. **DateTimeFormatter.ofPattern mặc định SMART.** Dùng withResolverStyle(STRICT) khi input phải được xác thực chính xác.
3. **uuuu là proleptic-year**, **yyyy là year-of-era**, **YYYY là week-based-year**.
4. **LocalDate.parse(text)** dùng ISO_LOCAL_DATE, thích hợp cho dữ liệu ISO ngày.
5. **Năm nhuận cần test 1900/2000** ngoài 2024/2025; không tự suy ngày 29/02 luôn hợp lệ.
6. **DateTimeParseException** có thông tin kỹ thuật nhưng không tự quyết định mã lỗi nghiệp vụ.
7. **Ngày hợp lệ về java.time vẫn có thể sai domain**, như năm 0 hoặc ngày sinh tương lai.
8. **LocalDateTime không mang zone**: dữ liệu giờ có thể rơi vào DST gap/overlap khi gắn ZoneId.
9. **DateTimeFormatter immutable/thread-safe**, có thể dùng lại.
10. **Test cần cả ca chấp nhận và từ chối**, so giá trị LocalDate thực, không chỉ kiểm tra không ném exception.

**Tài liệu chính thức Java SE hiện hành:**

- **DateTimeFormatter** — pattern, parse, resolver style, locale: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html
- **ResolverStyle** — STRICT, SMART, LENIENT: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/ResolverStyle.html
- **LocalDate** — parse, lịch ISO và phạm vi giá trị: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html
- **DateTimeParseException** — lỗi parse và error index: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeParseException.html
- **DateTimeFormatterBuilder** — parseCaseInsensitive và thiết kế parser: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html
- **ZoneRules** — valid offsets, DST gap/overlap: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/zone/ZoneRules.html
- **Year** — kiểm tra năm nhuận: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Year.html

**Phiên bản:** toàn bộ API java.time chính có từ Java 8 và vẫn áp dụng. Chương trình 18 ca dùng cú pháp record/collection factory của Java 17, còn chương trình YearPatternJava8Demo đã được biên dịch theo Java 8. Không cần dựa vào các API parser ngày giờ legacy cho bài này.
