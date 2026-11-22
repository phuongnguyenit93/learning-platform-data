# Ký tự cố định, dấu nháy và thành phần tùy chọn trong DateTimeFormatter

Với `java.time.format.DateTimeFormatter`, chuỗi mẫu (pattern) không chỉ chứa các ký hiệu ngày giờ như `uuuu`, `MM`, `dd`, `HH`, `mm`. Một mẫu còn có thể chứa **văn bản cố định**, **dấu nháy để đánh dấu văn bản theo nghĩa đen**, và **thành phần tùy chọn** có thể xuất hiện hoặc không xuất hiện trong kết quả.

Ví dụ:

- Mẫu `uuuu-MM-dd 'at' HH:mm` tạo chuỗi `2026-04-05 at 09:07`.
- Mẫu `'Date:' uuuu-MM-dd` tạo chuỗi `Date: 2026-04-05`.
- Mẫu `HH:mm[':'ss]` có thể cho ra `09:07` hoặc `09:07:03`, tùy giá trị thời gian được định dạng.
- Mẫu `'it''s' uuuu-MM-dd` tạo phần chữ cố định `it's`; hai dấu nháy đơn liên tiếp bên trong vùng literal đại diện cho một dấu nháy đơn trong kết quả.

Bài này dùng API `DateTimeFormatter.ofPattern(...)` của Java 17+ để làm rõ ngữ nghĩa của pattern, quy tắc dấu nháy và ngoặc vuông, cách dùng khi format và parse, cùng các lỗi phổ biến.

## 1. Pattern của DateTimeFormatter gồm những gì?

Pattern là chuỗi hướng dẫn bộ định dạng cách đọc hoặc ghi từng thành phần ngày giờ. Các nhóm ký tự chính:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Chữ mẫu ngày/giờ | `uuuu`, `MM`, `dd`, `HH`, `mm`, `ss` | Năm, tháng, ngày, giờ, phút, giây |
| Ký tự phân cách | `-`, `:`, `/`, dấu cách | Thường được in ra nguyên văn |
| Literal được trích dẫn | `'at'`, `'Date:'` | Văn bản cố định, không phải ký hiệu thời gian |
| Escape dấu nháy đơn | `''` | In ra một dấu nháy đơn |
| Thành phần tùy chọn | `[ ... ]` | Thành phần bên trong có thể vắng mặt khi parse/format theo khả năng của temporal |
| Offset/vùng | `XXX`, `VV`, `z` | Offset hoặc thông tin múi giờ, khi giá trị đầu vào có dữ liệu phù hợp |

Mẫu được xử lý theo quy tắc, không phải chuỗi định dạng tự do. Một ký tự chữ cái thường là ký hiệu trường ngày/giờ; nếu muốn chính chữ ấy xuất hiện trong kết quả, cần kiểm tra nó có phải ký hiệu hợp lệ hay không và thường phải đặt trong dấu nháy đơn.

## 2. Ký tự cố định: dấu gạch, dấu hai chấm và văn bản

Các ký tự phân cách phổ biến không cần trích dẫn:

```java
DateTimeFormatter f = DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss");
```

Với ngày giờ 05/04/2026 lúc 09:07:03, mẫu sẽ tạo `2026-04-05 09:07:03`. Dấu gạch, dấu cách và dấu hai chấm được in ra như chúng xuất hiện trong pattern.

Để chèn chữ rõ ràng, hãy đặt literal trong dấu nháy đơn:

```java
DateTimeFormatter f = DateTimeFormatter.ofPattern("uuuu-MM-dd 'at' HH:mm");
```

Với cùng giá trị, đầu ra là:

```text
2026-04-05 at 09:07
```

Trong `'at'`, các chữ `a` và `t` là văn bản cố định chứ không phải ký hiệu AM/PM hay trường ngày giờ. Có thể dùng một literal dài hơn:

```java
DateTimeFormatter f = DateTimeFormatter.ofPattern("'Date:' uuuu-MM-dd");
```

Kết quả:

```text
Date: 2026-04-05
```

Các dấu nháy đơn ở biên pattern dùng để mở/đóng vùng literal; bản thân dấu nháy không được in ra, trừ khi dùng quy tắc escape.

## 3. Quy tắc dấu nháy đơn và cách ghi dấu nháy trong kết quả

Trong pattern DateTimeFormatter:

- Một dấu nháy đơn mở vùng literal, và dấu nháy đơn tiếp theo đóng vùng đó.
- Hai dấu nháy đơn liên tiếp `''` biểu diễn **một dấu nháy đơn literal**.
- Muốn kết quả có dấu nháy đơn ở giữa từ, dùng hai dấu nháy trong vùng literal.

Ví dụ:

```java
DateTimeFormatter f =
        DateTimeFormatter.ofPattern("'it''s' uuuu-MM-dd", Locale.US);
System.out.println(f.format(LocalDate.of(2026, 4, 5)));
```

Kết quả:

```text
it's 2026-04-05
```

Giải thích từng phần của pattern:

- Dấu `'` đầu tiên bắt đầu literal.
- `it` là chữ cố định.
- `''` tạo dấu nháy đơn `'` trong đầu ra.
- `s` tiếp tục là chữ cố định trong cùng literal.
- Dấu nháy kế tiếp kết thúc literal.
- `uuuu-MM-dd` trở lại là mẫu năm, tháng, ngày.

Nếu cần cả hai dấu nháy hiển thị quanh chữ, hãy để chúng thành literal bằng cách dùng dấu nháy kép đơn đúng quy tắc, ví dụ `'It''s' uuuu` tạo `It's 2026`, không tạo chuỗi `'It's' 2026` có cặp dấu nháy ngoài.

Literal rất hữu ích khi tạo nhãn như `Date: 2026-04-05`, `Week of 2026-04-06` hoặc định dạng xuất dữ liệu mà hợp đồng giao tiếp quy định văn bản cố định. Chữ cố định không phụ thuộc ngôn ngữ người dùng; nếu cần bản dịch, hãy dùng tài nguyên locale/i18n thay vì khóa cứng các từ trong pattern.

## 4. Các ký tự chữ cái đặc biệt cần được trích dẫn

Nhiều chữ cái có ý nghĩa riêng trong pattern. Ví dụ `M` là tháng, `m` là phút; `H` là giờ 0–23, `h` là giờ 1–12; `y` là năm theo era, `u` là năm proleptic; `a` là AM/PM. Một chữ cái không được pattern hỗ trợ có thể khiến `ofPattern` ném `IllegalArgumentException`.

Nếu muốn hiển thị đúng chữ cái vốn trùng ký hiệu, hãy trích dẫn bằng dấu nháy đơn:

```java
DateTimeFormatter f = DateTimeFormatter.ofPattern("HH 'hours' mm 'minutes'");
```

Với 09:07, kết quả là `09 hours 07 minutes`. Nếu viết `HH hours mm minutes` không trích dẫn, các chữ cái trong `hours`/ `minutes` có thể bị diễn giải như pattern letter hoặc gây lỗi; đừng dựa vào việc một chữ nào đó tình cờ được bỏ qua.

Các ký tự đặc biệt như `[` và `]` mang ý nghĩa cấu trúc của optional section, còn `{` và `}` không phải cú pháp literal thông thường trong pattern. Khi muốn những ký tự này xuất hiện theo nghĩa đen, đặt chúng trong literal đã trích dẫn, ví dụ `"'['" ` như một đoạn pattern literal. Luôn kiểm tra pattern theo tài liệu Java thay vì suy luận từ cú pháp định dạng của ngôn ngữ khác.

## 5. Thành phần tùy chọn với ngoặc vuông

Trong pattern DateTimeFormatter, cặp ngoặc vuông `[ ... ]` đánh dấu một **optional section**. Nó hay được dùng khi một phần dữ liệu phụ có thể tồn tại hoặc vắng mặt, chẳng hạn giây hoặc phần thập phân của giây.

Ví dụ mẫu:

```java
DateTimeFormatter f = DateTimeFormatter.ofPattern("HH:mm[':'ss]");
```

Đối với `LocalTime` có giây bằng 03, output là `09:07:03`. Đối với `LocalTime` không có giây (giây bằng 0), khi format theo pattern này, optional section có thể không được xuất ra và kết quả là `09:07`.

Có thể lồng các optional section để mô tả dữ liệu có độ chính xác tăng dần:

```java
DateTimeFormatter f = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd'T'HH:mm[:ss[.SSS]]");
```

Mẫu này biểu diễn ngày và giờ, với giây tùy chọn; nếu giây có mặt, nhóm mili giây cũng được mô tả như một thành phần tùy chọn lồng bên trong. Với dữ liệu xuất JSON hoặc ISO, cần thống nhất biểu diễn ở cấp API; đừng giả định mọi parser sẽ có cùng chính sách về mức độ chính xác nếu không cùng dùng cùng formatter.

Lưu ý quan trọng:

- Ngoặc vuông là cú pháp của pattern formatter, không phải ký tự sẽ in ra.
- Optional section không có nghĩa là “mọi lỗi trong đoạn này đều bị bỏ qua”. Khi parse, các giá trị nếu xuất hiện vẫn phải hợp lệ với pattern và kiểu temporal đích.
- Khi format một temporal không có trường cần thiết, các quy tắc optional có thể cho phép phần đó vắng mặt; phần bắt buộc còn lại vẫn cần được cung cấp bởi kiểu dữ liệu.
- Đừng đặt một field bắt buộc duy nhất của đầu ra vào optional chỉ để né lỗi thiếu dữ liệu; điều đó có thể che giấu lỗi dữ liệu ở tầng domain.

## 6. Chương trình Java đầy đủ: literal, quote và optional section

Tạo tệp **`PatternLiteralDemo.java`**:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class PatternLiteralDemo {
    public static void main(String[] args) {
        LocalDateTime dateTime = LocalDateTime.of(2026, 4, 5, 9, 7, 3);

        DateTimeFormatter literal = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd 'at' HH:mm", Locale.US);
        DateTimeFormatter quotedQuote = DateTimeFormatter.ofPattern(
                "'it''s' uuuu-MM-dd", Locale.US);
        DateTimeFormatter optionalSeconds = DateTimeFormatter.ofPattern(
                "HH:mm[':'ss]", Locale.US);

        System.out.println(literal.format(dateTime));
        System.out.println(quotedQuote.format(dateTime));
        System.out.println(optionalSeconds.format(dateTime.toLocalTime()));
        System.out.println(optionalSeconds.format(LocalTime.of(9, 7)));
    }
}
```

Biên dịch và chạy:

```bash
javac PatternLiteralDemo.java
java PatternLiteralDemo
```

Đầu ra:

```text
2026-04-05 at 09:07
it's 2026-04-05
09:07:03
09:07
```

Chương trình minh họa ba ý:

1. `'at'` được in nguyên văn.
2. `''` trong literal tạo dấu nháy đơn thật trong chuỗi.
3. Phần `[':'ss]` chỉ hiển thị khi có giây khác 0 trong giá trị `LocalTime` được định dạng bằng mẫu này.

Nếu ứng dụng cần luôn in `09:07:00`, hãy dùng pattern bắt buộc `HH:mm:ss` thay vì làm giây optional.

## 7. Pattern khi parse: optional không thay thế validation

Một `DateTimeFormatter` có thể dùng cả để format (đối tượng ngày giờ thành chuỗi) và parse (chuỗi thành temporal). Với literal, chuỗi parse phải có đúng văn bản cố định nếu literal là bắt buộc. Với optional section, thành phần có thể hiện diện hoặc vắng mặt theo cấu trúc mẫu.

Ví dụ chương trình **`PatternParseDemo.java`**:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public class PatternParseDemo {
    public static void main(String[] args) {
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern(
                "HH:mm[':'ss]", Locale.US);

        System.out.println(LocalTime.parse("09:07", formatter));
        System.out.println(LocalTime.parse("09:07:03", formatter));

        try {
            LocalTime.parse("09:07:xx", formatter);
        } catch (DateTimeParseException e) {
            System.out.println("Invalid input");
        }
    }
}
```

```bash
javac PatternParseDemo.java
java PatternParseDemo
```

Kết quả:

```text
09:07
09:07:03
Invalid input
```

Việc phần giây là optional chỉ cho phép chuỗi không có giây. Nếu chuỗi có phần giây, phần đó vẫn phải parse hợp lệ; `09:07:xx` không trở thành hợp lệ chỉ vì giây nằm trong optional section. Với đầu vào từ người dùng hoặc hệ thống bên ngoài, hãy xử lý `DateTimeParseException` và đưa thông báo validation rõ ràng.

## 8. Giữ rõ ý nghĩa của năm, tháng, giờ khi kết hợp literal

Pattern letter phân biệt chữ hoa và chữ thường. Một số ký hiệu thường nhầm:

| Pattern | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `u` / `uuuu` | Năm proleptic | Thường phù hợp cho ngày ISO và xử lý số học |
| `y` / `yyyy` | Năm theo era | Trong một số lịch/era, semantics khác `u` |
| `M` / `MM` | Tháng trong năm | `MM` thường có padding 2 chữ số |
| `m` / `mm` | Phút trong giờ | Chữ thường |
| `H` / `HH` | Giờ 0–23 | Phù hợp đồng hồ 24 giờ |
| `h` / `hh` | Giờ 1–12 | Thường kết hợp `a` (AM/PM) |
| `s` / `ss` | Giây trong phút | Không phải ký hiệu tùy chọn nếu nằm ngoài ngoặc vuông |
| `S` | Phần thập phân của giây | Số chữ `S` quyết định số chữ số phần thập phân được in |
| `X` / `XXX` | Offset theo cách biểu diễn ISO | Cần temporal chứa offset/zone phù hợp |
| `VV` | ID vùng như `Europe/Paris` | Thường cần đối tượng có ZoneId |

Ví dụ `HH 'h' mm` tạo `09 h 07`; chữ `h` được trích dẫn nên là hậu tố văn bản, không phải pattern giờ 12 tiếng. Nếu dùng `hh a`, cùng một giờ có thể được in theo hệ 12 giờ cùng AM/PM. Pattern letter không phân biệt hoa/thường một cách tùy ý; luôn chọn đúng ký hiệu tương ứng.

## 9. Locale và văn bản cố định

Literal như `'at'`, `'Date:'`, `'hours'` là chữ cố định, do tác giả pattern đặt vào; nó không tự dịch theo `Locale`. Trong khi đó, các trường tên tháng/ngày như `MMMM` hoặc `EEEE` có thể dùng locale để lấy tên tháng hoặc ngày trong tuần bằng ngôn ngữ phù hợp.

Ví dụ:

```java
DateTimeFormatter f = DateTimeFormatter.ofPattern(
        "d MMMM uuuu", Locale.forLanguageTag("vi-VN"));
```

Mẫu này định dạng ngày cùng tên tháng theo locale tiếng Việt. Nếu chuỗi cần dùng trên giao diện đa ngôn ngữ, hãy tách nhãn dịch được khỏi pattern hoặc tạo formatter theo locale tương ứng; không khóa cứng từ tiếng Anh bằng literal rồi kỳ vọng `Locale` chuyển nó sang tiếng Việt.

Ngoài ra, không nên dùng mẫu hiển thị thân thiện làm định dạng trao đổi dữ liệu nếu hợp đồng yêu cầu cấu trúc cố định. Với giao tiếp liên dịch vụ, ưu tiên ISO-8601 chuẩn hoặc schema rõ ràng; các literal phục vụ giao diện phải được xem là quy tắc hiển thị.

## 10. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Viết chữ như `at` không trích dẫn | Ký tự bị hiểu là pattern letter hoặc gây lỗi pattern | Dùng `'at'` |
| Muốn output có dấu nháy đơn nhưng chỉ đặt một cặp nháy bao quanh | Nháy bao quanh là cú pháp, không được in ra | Dùng `''` để in một nháy đơn |
| Nghĩ mọi phần trong `[...]` tự động bỏ qua mọi lỗi | Parse vẫn báo lỗi nếu phần xuất hiện không hợp lệ | Dùng optional đúng cấu trúc và validate đầu vào |
| Để `ss` ngoài optional nhưng muốn bỏ giây khi không có | Mẫu yêu cầu giây trong mọi trường hợp | Dùng `HH:mm[':'ss]` nếu giây thật sự optional |
| Dùng `MM` khi muốn phút | In tháng thay vì phút | Dùng `mm` |
| Dùng `hh` mà quên AM/PM | Giờ 12 tiếng mơ hồ | Thêm `a` hoặc chuyển sang `HH` |
| Nghĩ literal tự dịch theo locale | Chữ như `at` vẫn cố định | Dùng tài nguyên i18n cho literal dịch được |
| Dùng pattern format người đọc làm giao thức dữ liệu | Thay đổi chữ cố định có thể phá parse của phía nhận | Giữ schema/ISO ổn định cho API |
| Dùng `yyyy` và `uuuu` như thể luôn đồng nghĩa | Có thể khác khi xử lý era | Chọn năm đúng nghĩa nghiệp vụ |

## Checklist trước khi đưa pattern vào ứng dụng

1. Xác định trường bắt buộc và trường thực sự optional.
2. Đặt chữ cố định trong dấu nháy đơn; dùng `''` để in một dấu nháy đơn.
3. Kiểm tra chữ hoa/chữ thường của pattern letter, nhất là `M/m`, `H/h`, `y/u`.
4. Dùng locale phù hợp cho tên tháng/ngày; đừng kỳ vọng locale dịch literal.
5. Kiểm thử cả format lẫn parse với trường hợp có/không có phần optional, và với đầu vào không hợp lệ.
6. Nếu mẫu dùng `X`, `XXX`, `VV` hoặc trường múi giờ khác, bảo đảm temporal đầu vào có đúng thông tin cần thiết.
7. Giữ mẫu trao đổi dữ liệu ổn định và tách khỏi mẫu hiển thị cho người dùng khi hai mục tiêu khác nhau.

### Ghi nhớ

Trong `DateTimeFormatter`, ký tự cố định được in nguyên văn, chữ cần giữ nguyên như literal được trích dẫn bằng dấu nháy đơn, `''` in một dấu nháy đơn, còn `[ ... ]` bao bọc một thành phần tùy chọn. Chọn pattern đúng ngữ nghĩa, kiểm tra độ hợp lệ khi parse và kiểm thử cả trường hợp có/không có phần optional trước khi dùng trong giao tiếp thực tế.
