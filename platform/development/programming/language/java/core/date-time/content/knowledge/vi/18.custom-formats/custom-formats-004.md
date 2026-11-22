# Giá trị mặc định bằng `parseDefaulting()`

## Bổ sung thông tin thiếu cần một quy ước rõ ràng

Một tệp báo cáo cho phép ghi kỳ báo cáo bằng `2024-02`, nhưng cũng cho phép ghi ngày cụ thể như `2024-02-20`. Ứng dụng muốn đưa cả hai về `LocalDate` và quy định: nếu chỉ có năm–tháng, dùng ngày đầu tháng làm ngày neo.

Chuỗi `2024-02` không có lỗi cú pháp theo hợp đồng này; nó chỉ thiếu trường ngày mà `LocalDate` cần. `DateTimeFormatterBuilder.parseDefaulting()` giúp bổ sung giá trị trường còn thiếu trong quá trình phân tích.

Tuy nhiên, ngày `01` là quy ước của ứng dụng, không phải thông tin nguồn đã gửi. Trước khi dùng mặc định, hãy xác nhận việc bổ sung đó có ý nghĩa nghiệp vụ. Nếu dữ liệu thực sự chỉ là tháng, giữ `YearMonth` có thể chính xác hơn việc biến nó thành một ngày.

## 1. `parseDefaulting(field, value)` làm gì?

Cách gọi có dạng:

```java
builder.parseDefaulting(ChronoField.DAY_OF_MONTH, 1);
```

Nó thêm một chỉ dẫn vào bộ định dạng. Trong lúc phân tích, tại thời điểm gặp chỉ dẫn ấy:

- Nếu trường đã có giá trị, giá trị hiện có được giữ.
- Nếu trường chưa có giá trị, giá trị mặc định được đưa vào kết quả phân tích.
- Giá trị được đưa vào ngay lúc đó, nên các thành phần phân tích chạy sau có thể nhìn thấy nó.

Vì vậy, mặc định thường được đặt **sau các thành phần có khả năng đọc trường ấy**. Trong chiều định dạng từ giá trị ra chuỗi, chỉ dẫn này không có tác dụng. [Tài liệu `parseDefaulting`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html#parseDefaulting(java.time.temporal.TemporalField,long))

Có thể hình dung bộ trường sau khi đọc:

```text
Đầu vào 2024-02:
    YEAR=2024, MONTH_OF_YEAR=2
    ↓ default DAY_OF_MONTH=1
    YEAR=2024, MONTH_OF_YEAR=2, DAY_OF_MONTH=1
    ↓ phân giải và kiểm tra lịch
    LocalDate 2024-02-01

Đầu vào 2024-02-20:
    YEAR=2024, MONTH_OF_YEAR=2, DAY_OF_MONTH=20
    ↓ default thấy trường ngày đã có, giữ nguyên
    LocalDate 2024-02-20
```

Đây là thao tác trên **trường thời gian**, không phải nối chuỗi `"-01"` vào mọi đầu vào.

## 2. Tách hai nhiệm vụ: cho phép thiếu và bổ sung khi thiếu

Để chấp nhận cả `2024-02` lẫn `2024-02-20`, ta cần hai cấu hình:

1. Đoạn `-dd` là tùy chọn trong cú pháp.
2. Nếu đoạn đó không có, bổ sung ngày mặc định.

Hai nhiệm vụ tương ứng với `optionalStart()/optionalEnd()` và `parseDefaulting()`. Chỉ khai báo mặc định không tự biến một đoạn bắt buộc thành tùy chọn.

Cấu trúc chính:

```java
DateTimeFormatter monthOrDate =
        new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM")
                .optionalStart()
                    .appendLiteral('-')
                    .appendPattern("dd")
                .optionalEnd()
                .parseDefaulting(ChronoField.DAY_OF_MONTH, 1)
                .toFormatter(Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
```

Đây là đoạn minh họa, cần các import trong chương trình đầy đủ bên dưới.

Điểm đặt `parseDefaulting` nằm ngoài và sau đoạn tùy chọn. Nhờ vậy, khi đầu vào không có `-dd`, chỉ dẫn bổ sung ngày vẫn được thực hiện.

## 3. Chương trình đầy đủ: đọc phần thiếu, giữ phần có và từ chối dữ liệu sai

Lưu dưới tên `ParseDefaultingDemo.java`. Chương trình dùng Java 17 trở lên:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class ParseDefaultingDemo {
    private static void showDate(
            String label, String text, DateTimeFormatter formatter) {
        try {
            System.out.println(label + "=" + LocalDate.parse(text, formatter));
        } catch (DateTimeException ex) {
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) {
        DateTimeFormatter monthOrDate =
                new DateTimeFormatterBuilder()
                        .appendPattern("uuuu-MM")
                        .optionalStart()
                            .appendLiteral('-')
                            .appendPattern("dd")
                        .optionalEnd()
                        .parseDefaulting(ChronoField.DAY_OF_MONTH, 1)
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        showDate("missingDay", "2024-02", monthOrDate);
        showDate("explicitDay", "2024-02-20", monthOrDate);
        showDate("invalidDate", "2023-02-29", monthOrDate);
        showDate("malformedOptional", "2024-02-xx", monthOrDate);

        DateTimeFormatter requiredDay =
                new DateTimeFormatterBuilder()
                        .appendPattern("uuuu-MM-dd")
                        .parseDefaulting(ChronoField.DAY_OF_MONTH, 1)
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        showDate("defaultDoesNotMakeOptional", "2024-02", requiredDay);

        DateTimeFormatter tooEarly =
                new DateTimeFormatterBuilder()
                        .parseDefaulting(ChronoField.DAY_OF_MONTH, 1)
                        .appendPattern("uuuu-MM-dd")
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        showDate("earlyDefaultConflict", "2024-02-20", tooEarly);

        DateTimeFormatter dayThirtyOne =
                new DateTimeFormatterBuilder()
                        .appendPattern("uuuu-MM")
                        .parseDefaulting(ChronoField.DAY_OF_MONTH, 31)
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        showDate("defaultValidInJanuary", "2024-01", dayThirtyOne);
        showDate("defaultInvalidInFebruary", "2024-02", dayThirtyOne);

        DateTimeFormatter dateOrMinute =
                new DateTimeFormatterBuilder()
                        .appendPattern("uuuu-MM-dd")
                        .optionalStart()
                            .appendLiteral('T')
                            .appendPattern("HH:mm")
                        .optionalEnd()
                        .parseDefaulting(ChronoField.HOUR_OF_DAY, 0)
                        .parseDefaulting(ChronoField.MINUTE_OF_HOUR, 0)
                        .parseDefaulting(ChronoField.SECOND_OF_MINUTE, 0)
                        .parseDefaulting(ChronoField.NANO_OF_SECOND, 0)
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        System.out.println("missingTime="
                + LocalDateTime.parse("2024-06-15", dateOrMinute));
        System.out.println("explicitTime="
                + LocalDateTime.parse("2024-06-15T09:30", dateOrMinute));

        System.out.println("formatYearMonth="
                + monthOrDate.format(YearMonth.of(2024, 2)));
        System.out.println("formatResolvedDate="
                + monthOrDate.format(LocalDate.parse("2024-02", monthOrDate)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ParseDefaultingDemo.java
java ParseDefaultingDemo
```

Stdout:

```text
missingDay=2024-02-01
explicitDay=2024-02-20
invalidDate=REJECTED
malformedOptional=REJECTED
defaultDoesNotMakeOptional=REJECTED
earlyDefaultConflict=REJECTED
defaultValidInJanuary=2024-01-31
defaultInvalidInFebruary=REJECTED
missingTime=2024-06-15T00:00
explicitTime=2024-06-15T09:30
formatYearMonth=2024-02
formatResolvedDate=2024-02-01
```

Các nhãn `REJECTED` do chương trình tự in; không phụ thuộc nội dung thông báo lỗi của một bản JDK.

## 4. Giữ giá trị nguồn thay vì ghi đè

Hai kết quả đầu chứng minh quy tắc quan trọng:

```text
2024-02    → 2024-02-01
2024-02-20 → 2024-02-20
```

Khi ngày `20` đã được đọc trước chỉ dẫn mặc định, mặc định `1` không thay nó. Đây là lý do dùng `parseDefaulting` thường rõ ràng hơn cách “phân tích xong rồi luôn gọi `withDayOfMonth(1)`”.

Đoạn sau chỉ minh họa một phép biến đổi có ý nghĩa khác:

```java
LocalDate date = LocalDate.parse("2024-02-20");
LocalDate firstOfMonth = date.withDayOfMonth(1);
```

Nó chủ động biến ngày 20 thành ngày 1. Nếu yêu cầu chỉ bổ sung khi thiếu, thao tác ấy không tương đương.

Tương tự, mặc định giờ `0` trong chương trình không làm đầu vào có `09:30` trở thành nửa đêm. Các trường giờ/phút đã hiện diện được giữ nguyên.

## 5. Vì sao đặt mặc định quá sớm có thể gây xung đột?

Bộ `tooEarly` trong chương trình thực hiện theo thứ tự:

```text
Chưa đọc gì
    ↓ đưa DAY_OF_MONTH=1 vào kết quả
Đọc uuuu-MM-dd
    ↓ văn bản muốn DAY_OF_MONTH=20
Hai giá trị của cùng trường xung đột
```

Mặc định không đợi đến cuối toàn bộ quá trình rồi mới quyết định thiếu hay đủ. Nó kiểm tra trạng thái **tại chính vị trí đã được thêm vào builder**. Vì thế, một trường xuất hiện ở đoạn văn bản phía sau không thể được coi là “đã đọc” tại vị trí chỉ dẫn phía trước.

Quy tắc thực hành cho ví dụ thông thường là:

```text
các phần đọc trường bắt buộc
    → các phần đọc trường tùy chọn
    → mặc định cho những trường còn thiếu
    → toFormatter
    → cấu hình phân giải
```

Cũng cần tránh đặt mặc định chỉ ở bên trong một đoạn tùy chọn mà toàn bộ đoạn đó có thể bị bỏ qua. Khi đoạn không được đọc, chỉ dẫn trong đoạn không phải một bảo đảm bổ sung trường cho kết quả ngoài đoạn.

Với cấu trúc phức tạp, hãy kiểm tra cả trường hợp có phần tùy chọn, vắng phần tùy chọn và có phần tùy chọn nhưng sai. Đừng chỉ thử đầu vào ngắn nhất.

## 6. Mặc định không cứu cú pháp bắt buộc hay dữ liệu sai

Có ba tình huống phải phân biệt:

| Tình huống | Ví dụ | Xử lý trong bài |
| --- | --- | --- |
| Trường được phép vắng | `2024-02` với đoạn ngày tùy chọn | Bổ sung ngày 1 |
| Trường bắt buộc nhưng không có | `2024-02` với mẫu đầy đủ `uuuu-MM-dd` | Từ chối |
| Đầu vào có phần sai | `2024-02-xx` hoặc `2023-02-29` | Từ chối |

Với `requiredDay`, bộ phân tích vẫn cần đọc `-dd`; thêm mặc định sau mẫu không sửa yêu cầu cú pháp đó.

Với `2024-02-xx`, đoạn tùy chọn không đọc được trọn vẹn và còn ký tự dư; lời gọi phân tích đầy đủ không bỏ qua phần dư để nhận riêng `2024-02`.

Với `2023-02-29`, trường ngày đã có giá trị, nên mặc định không thay nó bằng `1`. Chế độ nghiêm ngặt sau đó từ chối ngày không tồn tại.

Nếu đang cần một chính sách sửa dữ liệu sai, đó là yêu cầu khác và phải được thiết kế riêng. Không nên làm nó ẩn dưới tên “giá trị mặc định”.

## 7. Giá trị mặc định cũng phải hợp lệ trong ngữ cảnh

`DAY_OF_MONTH=31` nằm trong phạm vi chung của trường ngày, nhưng không tồn tại trong mọi tháng. Chương trình cho:

```text
2024-01 + ngày mặc định 31 → 2024-01-31
2024-02 + ngày mặc định 31 → từ chối với STRICT
```

Giá trị được bổ sung vẫn tham gia quá trình phân giải và kiểm tra lịch. Vì vậy, mặc định ngày `1` thường phù hợp hơn cho quy ước ngày đầu tháng, trong khi mặc định ngày `31` không thể dùng để diễn đạt “ngày cuối tháng” cho mọi tháng.

Nếu nghiệp vụ muốn **ngày cuối tháng**, giữ `YearMonth` và gọi:

```java
YearMonth month = YearMonth.parse("2024-02");
LocalDate lastDate = month.atEndOfMonth();
// lastDate = 2024-02-29
```

Đây là đoạn minh họa, dùng `YearMonth` và `LocalDate` từ `java.time`. Nó tính theo tháng cụ thể, không phải một hằng mặc định.

`toFormatter` tạo bộ định dạng với chế độ phân giải mặc định `SMART`. Trong các ví dụ, `withResolverStyle(ResolverStyle.STRICT)` được đặt rõ để không tự điều chỉnh tổ hợp ngày sai. [Tài liệu tạo bộ định dạng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html#toFormatter(java.util.Locale)), [tài liệu `ResolverStyle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html)

## 8. Bổ sung giờ không tự tạo múi giờ hay thời điểm toàn cầu

Trong ví dụ `dateOrMinute`, hợp đồng là:

- Có thể chỉ gửi ngày.
- Có thể gửi ngày và giờ/phút sau chữ `T`.
- Nếu thiếu giờ, ứng dụng hiểu là `00:00`.
- Giây và phần nano không được nhập trong cú pháp này, được mặc định bằng không.

Kết quả vẫn là `LocalDateTime`. `2024-06-15T00:00` chưa nói đó là nửa đêm ở vùng nào. Không được xem việc thêm giờ là đồng thời thêm UTC hay múi giờ máy chủ.

Cũng không cần thêm mặc định cho mọi trường mà một kiểu có thể có. Hãy bổ sung đúng những trường mà hợp đồng cần và hiểu các quy tắc phân giải của kiểu đích. Ví dụ đã ghi tường minh giờ, phút, giây và nano bằng không để làm rõ chính sách, không phải yêu cầu rằng mọi bộ phân tích giờ đều phải lặp nguyên cấu hình ấy.

Nếu nguồn muốn biểu đạt “không biết giờ”, đổi nó thành nửa đêm có thể làm mất ý nghĩa. Khi đó, hãy giữ thông tin thiếu ở mô hình dữ liệu thay vì dùng mặc định chỉ để một phép phân tích luôn trả về giá trị.

## 9. Mặc định không tác động vào chiều định dạng

Hai dòng cuối chương trình cho thấy:

```text
YearMonth 2024-02 → định dạng thành 2024-02
LocalDate 2024-02-01 → định dạng thành 2024-02-01
```

Khi định dạng `YearMonth`, đoạn ngày tùy chọn không có dữ liệu để in. Chỉ dẫn mặc định không tự thêm ngày 1 vào đối tượng để ép in đoạn đó.

Khi đã phân tích chuỗi tháng thành `LocalDate`, kết quả có trường ngày bằng 1. Định dạng kết quả ấy có thể in cả ngày, vì lúc này ngày thực sự có trong đối tượng.

Điều này cũng chỉ ra một giới hạn dữ liệu: sau khi nhận `LocalDate 2024-02-01`, không thể chỉ nhìn giá trị đó để biết nguồn đã gửi `2024-02` hay `2024-02-01`. Nếu độ chi tiết nguồn có ý nghĩa, hãy giữ thêm loại đầu vào hoặc dùng kiểu như `YearMonth` ở chỗ thích hợp.

## 10. Chọn mặc định có thể giải thích và kiểm chứng được

Trước khi thêm một `parseDefaulting`, xác định:

1. Trường nào thực sự được phép thiếu?
2. Giá trị nào được mặc định, vì sao có ý nghĩa?
3. Giá trị nguồn hiện diện có được giữ không?
4. Mặc định có thể tạo tổ hợp lịch không hợp lệ không?
5. Kết quả có làm mất thông tin về độ chi tiết ban đầu không?

Giá trị truyền vào `parseDefaulting(field, value)` là một số được cấu hình khi xây dựng bộ định dạng. Nó không phải hàm được tính lại theo mỗi lần phân tích. Nếu dùng “năm hiện tại” làm giá trị khi khởi tạo một hằng, giá trị đó có thể giữ nguyên sau khi qua năm mới. Với mặc định phụ thuộc ngữ cảnh hoặc thời gian hiện tại, nên thiết kế bước bổ sung rõ ràng với nguồn thời gian có thể kiểm thử, thay vì giấu nó trong một cấu hình tưởng như tĩnh.

Bộ ca tối thiểu có ích cho ví dụ tháng/ngày gồm:

- Thiếu ngày đúng quy định.
- Có ngày cụ thể khác ngày mặc định.
- Ngày không tồn tại.
- Phần tùy chọn hỏng hoặc còn ký tự dư.
- Ngày mặc định không hợp lệ ở một tháng.
- Cấu hình sai thứ tự để chứng minh phép thử có phát hiện xung đột.

## 11. Tự thực hành

1. `parseDefaulting(DAY_OF_MONTH, 1)` có ghi đè ngày `20` đã đọc trước đó không?
2. Vì sao thêm mặc định sau mẫu bắt buộc `uuuu-MM-dd` chưa đủ để nhận `2024-02`?
3. Vì sao đặt mặc định ngày 1 trước đoạn đọc `dd` có thể khiến đầu vào ngày 20 thất bại?
4. Mặc định ngày 31 có phải cách tính ngày cuối tháng không?
5. Chuỗi tháng sau khi đổi thành `LocalDate` còn tự giữ được việc nguồn đã bỏ ngày không?

Gợi ý đáp án:

1. Không; trường đã có giá trị được giữ.
2. Vì quy tắc cú pháp vẫn bắt buộc có đoạn ngày; phải cho phép đoạn đó vắng riêng.
3. Vì giá trị 1 được đưa vào ngay, rồi xung đột với giá trị 20 đọc sau.
4. Không; nhiều tháng không có ngày 31. Dùng `YearMonth.atEndOfMonth()` khi đó là yêu cầu.
5. Không; cần giữ thông tin độ chi tiết riêng nếu nó quan trọng.

Dùng `parseDefaulting` để thực hiện một quy ước bổ sung trường đã được xác định rõ, đặt nó đúng vị trí và vẫn kiểm tra cú pháp, lịch cũng như ý nghĩa nghiệp vụ của kết quả.
