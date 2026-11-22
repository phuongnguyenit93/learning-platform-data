# Ghép trường số, văn bản và ký tự cố định

## 1. Xem định dạng như một chuỗi thành phần có ý nghĩa

Giả sử cần trình bày ngày 25/10/2026 thành `Sun | 25 October 2026`. Chuỗi có cả dữ liệu lấy từ ngày và ký tự cố định:

```text
Sun       |       25       October       2026
 |        |        |          |           |
 tên thứ  dấu nối  số ngày    tên tháng   số năm
```

Nếu tự nối bằng `getDayOfMonth()` và các chuỗi tên tháng, bạn phải tự xử lý số 0 phía trước, ngôn ngữ, thứ tự và phép đọc ngược. `DateTimeFormatterBuilder` cho phép mô tả cấu trúc một lần, rồi tạo `DateTimeFormatter` để định dạng và phân tích theo cùng hợp đồng.

Ba thao tác nền tảng là:

| Thao tác | Nội dung được thêm | Ví dụ |
|---|---|---|
| `appendValue(...)` | Giá trị số của một trường thời gian | Ngày `25`, tháng `10`, năm `2026` |
| `appendText(...)` | Tên biểu diễn bằng văn bản của một trường | `Sun`, `October` |
| `appendLiteral(...)` | Ký tự hoặc chuỗi cố định | `" \| "`, `' '`, `'-'` |

Thứ tự gọi chính là thứ tự các thành phần trong đầu ra và đầu vào. Builder không tự sắp xếp chúng theo một mẫu mặc định của quốc gia.

## 2. Trường số: chọn đúng trường và độ rộng

Các trường thường dùng đến từ `ChronoField`, ví dụ `YEAR`, `MONTH_OF_YEAR`, `DAY_OF_MONTH`, `HOUR_OF_DAY`, `MINUTE_OF_HOUR`.

Ví dụ khai báo các thành phần trong builder:

```java
new DateTimeFormatterBuilder()
        .appendValue(ChronoField.DAY_OF_MONTH, 2)
        .appendLiteral('/')
        .appendValue(ChronoField.MONTH_OF_YEAR, 2)
        .appendLiteral('/')
        .appendValue(ChronoField.YEAR, 4);
```

Đây mới là các lệnh xây cấu trúc; cần gọi `toFormatter(...)` để nhận bộ định dạng sử dụng được.

### Độ rộng cố định và số 0 phía trước

`appendValue(field, width)` dùng độ rộng cố định. Khi định dạng, giá trị ngắn hơn được thêm số 0 bên trái: ngày 5 với độ rộng 2 thành `05`. Khi phân tích theo chế độ đọc văn bản nghiêm ngặt mặc định, nó yêu cầu đủ số chữ số đã chọn.

Độ rộng không phải lệnh cắt bớt dữ liệu. Nếu giá trị không vừa, thao tác định dạng báo lỗi thay vì giữ vài chữ số cuối. Biến thể này cũng không in dấu cho giá trị âm; do đó `appendValue(YEAR, 4)` phù hợp với phạm vi năm 0000–9999 của ví dụ, không phải mọi năm mà `LocalDate` biểu diễn được.

Với trường năm rộng hơn hoặc có dấu, cần chọn biến thể phù hợp như `appendValue(field, minWidth, maxWidth, signStyle)`. Không nên dùng độ rộng 4 rồi ngầm cho rằng năm âm hoặc năm có năm chữ số vẫn được xử lý đúng hợp đồng.

`appendValue(field)` không truyền độ rộng tạo dạng số không đệm 0 với độ rộng biến đổi. Hãy chọn dạng cố định hay biến đổi theo dữ liệu muốn nhận và xuất, không chỉ dựa vào việc một ví dụ hiện tại tình cờ có hai chữ số.

### Ghép số không có dấu phân cách

Muốn tạo `20261025`, có thể ghép năm 4 chữ số, tháng 2 chữ số và ngày 2 chữ số. Ranh giới được xác định bởi độ rộng từng phần. Nếu các trường đều có độ rộng thay đổi và đứng sát nhau, đầu vào dễ trở nên mơ hồ; cần thiết kế ranh giới hoặc quy tắc độ rộng rõ ràng.

Trong ví dụ đầy đủ, cả ba trường đều cố định để người đọc dễ kiểm tra cách tách `2026`, `10`, `25`. Builder có cơ chế xử lý các giá trị số liền kề trong một số tổ hợp, nhưng không nên dựa vào việc đoán khi thiết kế hợp đồng mới.

## 3. Trường văn bản: dữ liệu vẫn là trường ngày giờ

`appendText` không chèn một nhãn cố định. Nó lấy giá trị trường rồi tìm biểu diễn văn bản tương ứng theo `Locale` và `TextStyle`.

```java
.appendText(ChronoField.DAY_OF_WEEK, TextStyle.SHORT)
.appendText(ChronoField.MONTH_OF_YEAR, TextStyle.FULL)
```

Với tiếng Anh và ngày trong ví dụ, trường thứ có thể hiển thị `Sun`, còn trường tháng là `October`.

| TextStyle | Ý định | Ví dụ tên tháng tiếng Anh |
|---|---|---|
| `FULL` | Dạng đầy đủ | `January` |
| `SHORT` | Dạng viết tắt | `Jan` |
| `NARROW` | Dạng rất ngắn | `J` |

Dạng rất ngắn không nhất thiết phân biệt được tất cả giá trị: nhiều tháng có thể cùng chữ đầu `J`. Không dùng nó như một mã tháng duy nhất nếu cần đọc ngược không mơ hồ.

Các dạng `*_STANDALONE` phục vụ cách dùng tên độc lập trong những ngôn ngữ có khác biệt ngữ pháp so với tên nằm trong một ngày đầy đủ. Đừng đồng nhất “độc lập” với “tự động viết hoa”.

Chọn `Locale` tường minh ở `toFormatter(Locale.ENGLISH)` hoặc locale cần dùng. Nếu để mặc định, dữ liệu tên thứ/tháng có thể thay đổi theo máy chạy. Việc đổi locale thay tên văn bản; những literal do bạn viết vẫn giữ nguyên và không được dịch tự động.

Khi đọc chuỗi, văn bản phải khớp tập tên và kiểu mà bộ định dạng chấp nhận. Muốn không phân biệt hoa/thường, đặt `parseCaseInsensitive()` trước các phần liên quan. Điều đó không thay thế chính sách kiểm tra ngày và không tự chấp nhận tên của mọi ngôn ngữ.

## 4. Literal: viết gì thì cấu trúc có đúng phần đó

`appendLiteral('-')` thêm một ký tự; `appendLiteral(" | ")` thêm cả chuỗi gồm khoảng trắng, dấu `|` và khoảng trắng.

Literal có hai vai trò:

- Khi định dạng, nó xuất nguyên văn.
- Khi phân tích, bộ phân tích chờ phần tương ứng xuất hiện tại vị trí ấy, theo chính sách khớp văn bản đang áp dụng.

Builder không tự thêm khoảng trắng giữa hai lời gọi. Nếu muốn `25 October`, phải thêm `' '` giữa trường ngày và trường tháng; thiếu nó có thể tạo `25October`.

Cũng cần phân biệt literal với pattern:

```java
.appendLiteral("at")
```

Lệnh này chèn nguyên văn chữ `at`. Trong khi đó, `appendPattern("at")` coi các chữ là ký hiệu mẫu và có thể không hợp lệ; nếu dùng pattern để chèn văn bản, phải dùng cú pháp trích dẫn của pattern như `appendPattern("'at'")`.

Literal chứa một từ như `"tháng"` luôn là từ bạn cung cấp. Nó không đổi sang `month` khi thay `Locale.ENGLISH`. Vì vậy cần chọn giữa phần chữ cố định do thiết kế quy định và phần tên theo ngôn ngữ do `appendText` quản lý.

## 5. Tạo bộ định dạng và bảo đảm đủ dữ liệu

Chuỗi lời gọi kết thúc bằng `toFormatter(...)`, sau đó có thể cấu hình chính sách giải quyết trường:

```java
DateTimeFormatter formatter = new DateTimeFormatterBuilder()
        .appendValue(ChronoField.DAY_OF_MONTH, 2)
        .appendLiteral('-')
        .appendText(ChronoField.MONTH_OF_YEAR, TextStyle.SHORT)
        .appendLiteral('-')
        .appendValue(ChronoField.YEAR, 4)
        .toFormatter(Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);
```

Builder là đối tượng có thể thay đổi, dùng để dựng cấu trúc. `DateTimeFormatter` hoàn chỉnh là bất biến và có thể tái sử dụng đồng thời. Đừng tiếp tục chia sẻ một builder có trạng thái thay đổi giữa nhiều luồng để thay cho việc giữ bộ định dạng đã tạo.

Khi định dạng, đối tượng nguồn cần có các trường được yêu cầu. `LocalDate` có ngày, tháng, năm và thứ; `LocalTime` không có các trường ấy. Khi đọc ngược thành `LocalDate`, đầu vào cũng phải cung cấp đủ thông tin để xác định ngày; chỉ tên tháng và một literal không tự tạo ra ngày hoàn chỉnh.

Thêm trường thứ là thêm dữ liệu có thể kiểm tra, không chỉ thêm đồ trang trí. Nếu chuỗi nói `Mon` nhưng phần ngày-tháng-năm thực tế là Chủ nhật, quá trình giải quyết và đối chiếu trường sẽ báo xung đột. Đừng bỏ qua tên thứ khi dùng cùng bộ định dạng để nhận đầu vào.

## 6. Chương trình chạy đầy đủ

Lưu mã sau vào `ComposedFormatterDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.format.TextStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class ComposedFormatterDemo {
    private static final DateTimeFormatter LABEL =
            new DateTimeFormatterBuilder()
                    .appendText(ChronoField.DAY_OF_WEEK, TextStyle.SHORT)
                    .appendLiteral(" | ")
                    .appendValue(ChronoField.DAY_OF_MONTH, 2)
                    .appendLiteral(' ')
                    .appendText(ChronoField.MONTH_OF_YEAR, TextStyle.FULL)
                    .appendLiteral(' ')
                    .appendValue(ChronoField.YEAR, 4)
                    .toFormatter(Locale.ENGLISH)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static final DateTimeFormatter COMPACT =
            new DateTimeFormatterBuilder()
                    .appendValue(ChronoField.YEAR, 4)
                    .appendValue(ChronoField.MONTH_OF_YEAR, 2)
                    .appendValue(ChronoField.DAY_OF_MONTH, 2)
                    .toFormatter(Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 25);
        String text = LABEL.format(date);
        System.out.println("label=" + text);
        System.out.println("parsed=" + LocalDate.parse(text, LABEL));
        System.out.println("compact=" + COMPACT.format(date));
        System.out.println("compactParsed="
                + LocalDate.parse("20261025", COMPACT));

        inspect("Sun | 25 October 2026");
        inspect("Sun / 25 October 2026");
        inspect("Sun | 5 October 2026");
        inspect("Mon | 25 October 2026");
        inspect("Sun | 31 February 2026");
    }

    private static void inspect(String text) {
        try {
            System.out.println("input=" + text + " -> "
                    + LocalDate.parse(text, LABEL));
        } catch (DateTimeParseException e) {
            System.out.println("input=" + text + " -> ERROR");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac ComposedFormatterDemo.java
java ComposedFormatterDemo
```

Kết quả đã kiểm chứng:

```text
label=Sun | 25 October 2026
parsed=2026-10-25
compact=20261025
compactParsed=2026-10-25
input=Sun | 25 October 2026 -> 2026-10-25
input=Sun / 25 October 2026 -> ERROR
input=Sun | 5 October 2026 -> ERROR
input=Mon | 25 October 2026 -> ERROR
input=Sun | 31 February 2026 -> ERROR
```

Tên thứ/tháng ở đây sử dụng tiếng Anh; kết quả này được kiểm chứng trên Zulu OpenJDK 24.0.2. Dữ liệu ngôn ngữ có thể được cập nhật giữa các bản JDK. Với đầu ra theo một giao thức đòi hỏi giữ nguyên từng ký tự lâu dài, cần xác định rõ hợp đồng văn bản thay vì chỉ dựa vào dữ liệu vùng của máy chạy.

`ERROR` là nhãn của chương trình khi bắt `DateTimeParseException`. Những nguyên nhân được chủ động tách trong ví dụ:

1. `Sun / ...` sai literal `" | "`.
2. `Sun | 5 ...` không đủ độ rộng 2 chữ số của trường ngày.
3. `Mon | 25 October 2026` có thứ mâu thuẫn với ngày cụ thể.
4. `Sun | 31 February 2026` không phải một ngày có thật.

Ví dụ dùng `ResolverStyle.STRICT` để các ngày không tồn tại không bị điều chỉnh. Cấu trúc trường, chính sách nhận văn bản và tính hợp lệ theo lịch là các phần phối hợp, không thay thế cho nhau.

## 7. Những lỗi thiết kế thường gặp

| Lỗi | Cách xử lý |
|---|---|
| Dùng `appendLiteral("October")` cho mọi ngày | Dùng `appendText(MONTH_OF_YEAR, ...)` nếu đó là tên tháng lấy từ giá trị |
| Ghép hai trường rồi chờ tự có khoảng trắng | Thêm literal khoảng trắng tường minh |
| Dùng trường `MONTH_OF_YEAR` nhưng muốn phút | Chọn `MINUTE_OF_HOUR`; builder làm theo trường được truyền |
| Dùng `YEAR_OF_ERA` rồi thiếu kỷ nguyên khi đọc nghiêm ngặt | Với ngày ISO thông thường, chọn `YEAR` hoặc thiết kế đủ dữ liệu kỷ nguyên |
| Dùng số có độ rộng 4 và cho rằng hỗ trợ mọi năm | Xác định phạm vi hoặc dùng biến thể có quy tắc độ rộng/dấu phù hợp |
| Đổi locale và chờ literal được dịch | Chọn lại literal theo ngôn ngữ ở lớp thiết kế, hoặc dùng trường văn bản khi đó là dữ liệu thời gian |
| Tạo được chuỗi nhưng không đọc lại được | Kiểm tra độ rộng, locale, thứ tự, literal và việc đầu vào có đủ trường để tạo kiểu kết quả |

Với một cấu trúc đơn giản, `ofPattern` có thể ngắn hơn. Builder hữu ích khi cần thấy rõ từng loại thành phần, dùng quy tắc số cụ thể hoặc ghép những phần được tạo riêng. Không cần thay mọi pattern bằng builder; hãy dùng cách làm giúp hợp đồng định dạng dễ đọc và kiểm tra.

## 8. Tự thực hành

Đổi ngày trong chương trình thành `LocalDate.of(2026, 1, 5)`. Với bộ định dạng `LABEL`, dự đoán:

```text
Mon | 05 January 2026
```

Giải thích vì sao số ngày có `0` phía trước, tháng dùng từ đầy đủ, còn dấu ` | ` không thay đổi. Tiếp theo, đổi `TextStyle.FULL` của tháng thành `TextStyle.SHORT` và chạy lại để quan sát đúng phần thay đổi.

Cuối cùng, tạo bộ định dạng `dd/MM/uuuu` bằng ba lời gọi `appendValue` và hai literal `/`, rồi kiểm tra cả hai hướng với `05/01/2026`. Thử chuỗi `5/1/2026` để xác nhận độ rộng cố định là một phần của hợp đồng đầu vào.

Tham khảo: [DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html), [TextStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/TextStyle.html) và [ChronoField](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoField.html) trong Java SE 21.
