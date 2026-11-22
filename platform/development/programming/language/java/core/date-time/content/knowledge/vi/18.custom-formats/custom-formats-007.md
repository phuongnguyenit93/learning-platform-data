# Tách giai đoạn đọc trường và giải quyết trường ngày giờ

## “Đọc được con số” khác với “tạo được ngày”

Chuỗi `2023-02-29` có cấu trúc năm–tháng–ngày rất rõ: ta đọc được năm 2023, tháng 2 và ngày 29. Nhưng tổ hợp ấy không tạo được một ngày hợp lệ, vì năm 2023 không có ngày 29/02.

Ngược lại, chuỗi `2024-2-29` mô tả một ngày tồn tại, nhưng có thể không khớp bộ phân tích yêu cầu tháng đủ hai chữ số.

Hai tình huống này giúp phân biệt:

1. **Đọc trường từ văn bản:** nhận ra chữ số, dấu phân cách và đưa chúng vào các trường thời gian.
2. **Phân giải trường ngày giờ (resolving):** kết hợp các trường theo quy tắc của hệ lịch, kiểm tra và tạo giá trị có ý nghĩa.

Hiểu hai giai đoạn giúp sửa đúng cấu hình khi phân tích thất bại, thay vì đổi độ rộng, thêm mặc định hoặc nới lỏng chế độ một cách ngẫu nhiên.

## 1. Bức tranh xử lý từ chuỗi đến kiểu đích

```text
"2024-02-29"
      │
      │ đọc theo cấu trúc của bộ định dạng
      ▼
YEAR=2024
MONTH_OF_YEAR=2
DAY_OF_MONTH=29
      │
      │ phân giải theo hệ lịch và ResolverStyle
      ▼
Ngày ISO hợp lệ 2024-02-29
      │
      │ lấy đúng kiểu mà nơi gọi yêu cầu
      ▼
LocalDate
```

Đây là mô hình khái niệm. API mức cao như `LocalDate.parse(text, formatter)` thực hiện chuỗi công việc ấy trong một lời gọi; bạn không cần tự tách ra khi viết mã nhập ngày thông thường.

`DateTimeFormatter` mô tả phân tích chuỗi bằng hai giai đoạn: đọc văn bản thành trường/giá trị, rồi phân giải chúng thành ngày hoặc giờ. Các truy vấn kiểu như `LocalDate` cần kết quả đủ thông tin phù hợp. [Tài liệu phân giải của `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

## 2. Giai đoạn đọc trường quan tâm đến điều gì?

Bộ phân tích đi theo các thành phần đã khai báo:

- Đọc trường số theo độ rộng và quy tắc dấu.
- Đọc tên tháng, thứ hoặc ký hiệu khác theo ngôn ngữ/cấu hình.
- Đối chiếu các ký tự cố định như `-`, `:` hoặc `T`.
- Xử lý đoạn bắt buộc, đoạn tùy chọn.
- Ghi các trường đọc được, chẳng hạn `YEAR`, `MONTH_OF_YEAR`, `HOUR_OF_DAY`.
- Theo dõi vị trí đã đọc và vị trí lỗi cú pháp khi dùng API có vị trí.

Ví dụ với mẫu `uuuu-MM-dd`, chuỗi `2023-02-29` có thể cung cấp đầy đủ ba trường:

```text
YEAR = 2023
MONTH_OF_YEAR = 2
DAY_OF_MONTH = 29
```

Việc có đủ ba giá trị chưa chứng minh tổ hợp ngày tồn tại. Trong khi đó, tháng chỉ có một chữ số của `2024-2-29` có thể khiến bộ phân tích văn bản nghiêm ngặt thất bại trước khi có tập trường hoàn chỉnh.

Một số xung đột khi cùng trường được đọc nhiều lần cũng có thể được phát hiện ngay trong quá trình đọc. Không nên hiểu mô hình hai giai đoạn như cam kết rằng mọi loại kiểm tra đều bị hoãn đến cuối.

## 3. Giai đoạn phân giải làm gì thêm?

Phân giải không chỉ chuyển các con số sang một đối tượng. Với ngày giờ ISO thông thường, nó còn cần:

- Xác định hệ lịch áp dụng.
- Chuyển những trường liên quan thành năm, tháng, ngày cụ thể nếu đủ dữ liệu.
- Kiểm tra phạm vi và cách kết hợp trường theo `ResolverStyle`.
- Kết hợp các trường giờ, phút, giây và phần lẻ khi đủ thông tin.
- Đối chiếu trường dư với ngày giờ đã tìm được, chẳng hạn ngày trong năm phải khớp ngày/tháng.
- Kết hợp thông tin thời điểm hoặc múi giờ khi kiểu dữ liệu và các trường liên quan cho phép.

Đây là các trách nhiệm giúp hình dung, không phải bản sao đầy đủ thứ tự xử lý nội bộ. Quy tắc ngày ISO được quy định trong [`IsoChronology.resolveDate`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/IsoChronology.html#resolveDate(java.util.Map,java.time.format.ResolverStyle)).

Ví dụ `YEAR=2023`, `MONTH=2`, `DAY=29` sẽ được xử lý khác nhau theo chế độ:

| Chế độ phân giải | Kết quả cho 2023-02-29 trong ví dụ |
| --- | --- |
| `STRICT` | Từ chối ngày không tồn tại |
| `SMART` | Điều chỉnh về ngày cuối tháng: 2023-02-28 |
| `LENIENT` | Tính phần ngày vượt sang tháng tiếp theo: 2023-03-01 |

Các chế độ có quy tắc riêng theo trường và hệ lịch; không nên diễn giải `SMART` thành “luôn an toàn cho mọi đầu vào”. [Tài liệu `ResolverStyle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html)

## 4. Hai kiểu “nghiêm ngặt” không đồng nghĩa

Tên gọi dễ gây nhầm:

| Cấu hình | Phần việc chính |
| --- | --- |
| `DateTimeFormatterBuilder.parseStrict()` | Quy tắc khớp văn bản, như độ rộng và dấu |
| `DateTimeFormatterBuilder.parseLenient()` | Nới quy tắc khớp văn bản từ vị trí cấu hình |
| `formatter.withResolverStyle(STRICT)` | Phân giải trường thành ngày giờ nghiêm ngặt |
| `formatter.withResolverStyle(LENIENT)` | Phân giải với quy tắc cho phép giá trị tràn phù hợp |

Builder mặc định đọc văn bản theo chế độ nghiêm ngặt. Trong khi đó, bộ định dạng do `toFormatter` hoặc `ofPattern` tạo có chế độ phân giải mặc định `SMART`. Vì thế, “đã gọi `parseStrict()`” chưa có nghĩa “ngày không tồn tại chắc chắn bị từ chối”. [Tài liệu `DateTimeFormatterBuilder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html)

Ngược lại, có thể cho phép tháng/ngày một chữ số ở giai đoạn đọc, nhưng vẫn yêu cầu tổ hợp tạo thành ngày tồn tại ở giai đoạn phân giải. Cấu hình có ý nghĩa khi phản ánh hợp đồng dữ liệu, không phải càng nhiều chữ `STRICT` càng đúng.

## 5. Chương trình hoàn chỉnh để quan sát hai giai đoạn

Lưu dưới tên `ParsingPhasesDemo.java`. Chương trình dùng Java 17 trở lên và thư viện chuẩn:

```java
import java.text.ParsePosition;
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;

public class ParsingPhasesDemo {
    private static void inspectRaw(
            String label, String text, DateTimeFormatter formatter) {
        ParsePosition position = new ParsePosition(0);
        TemporalAccessor raw = formatter.parseUnresolved(text, position);
        System.out.println(label + "=" + (raw == null ? "FAILED" : "READ")
                + ",index=" + position.getIndex());
    }

    private static void showDate(
            String label, String text, DateTimeFormatter formatter) {
        try {
            System.out.println(label + "=" + LocalDate.parse(text, formatter));
        } catch (DateTimeException ex) {
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) {
        DateTimeFormatter strict =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        inspectRaw("rawInvalidCalendar", "2023-02-29", strict);
        inspectRaw("rawWrongWidth", "2024-2-29", strict);
        inspectRaw("rawTrailing", "2024-02-29extra", strict);

        ParsePosition position = new ParsePosition(0);
        TemporalAccessor raw = strict.parseUnresolved("2023-02-29", position);
        System.out.println("rawDay=" + raw.getLong(ChronoField.DAY_OF_MONTH));

        showDate("strictValid", "2024-02-29", strict);
        showDate("strictInvalid", "2023-02-29", strict);
        showDate("smartInvalid", "2023-02-29",
                strict.withResolverStyle(ResolverStyle.SMART));
        showDate("lenientInvalid", "2023-02-29",
                strict.withResolverStyle(ResolverStyle.LENIENT));
        showDate("fullTrailing", "2024-02-29extra", strict);

        DateTimeFormatter textStrict =
                new DateTimeFormatterBuilder()
                        .parseStrict()
                        .appendPattern("uuuu-MM-dd")
                        .toFormatter(Locale.ROOT);

        showDate("textStrictButSmart", "2023-02-29", textStrict);

        DateTimeFormatter flexibleWidth =
                new DateTimeFormatterBuilder()
                        .parseLenient()
                        .appendPattern("uuuu-MM-dd")
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        showDate("flexibleWidthValid", "2024-2-9", flexibleWidth);
        showDate("flexibleWidthInvalid", "2023-2-29", flexibleWidth);

        DateTimeFormatter redundant =
                DateTimeFormatter.ofPattern("uuuu-MM-dd-DDD", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        inspectRaw("rawConflictingFields", "2024-02-29-061", redundant);
        showDate("resolvedConflictingFields", "2024-02-29-061", redundant);

        DateTimeFormatter monthOnly =
                DateTimeFormatter.ofPattern("uuuu-MM", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        TemporalAccessor monthFields = monthOnly.parse("2024-02");
        System.out.println("yearMonth=" + YearMonth.from(monthFields));

        try {
            LocalDate.from(monthFields);
            System.out.println("localDateFromMonth=CREATED");
        } catch (DateTimeException ex) {
            System.out.println("localDateFromMonth=REJECTED");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ParsingPhasesDemo.java
java ParsingPhasesDemo
```

Stdout:

```text
rawInvalidCalendar=READ,index=10
rawWrongWidth=FAILED,index=0
rawTrailing=READ,index=10
rawDay=29
strictValid=2024-02-29
strictInvalid=REJECTED
smartInvalid=2023-02-28
lenientInvalid=2023-03-01
fullTrailing=REJECTED
textStrictButSmart=2023-02-28
flexibleWidthValid=2024-02-09
flexibleWidthInvalid=REJECTED
rawConflictingFields=READ,index=14
resolvedConflictingFields=REJECTED
yearMonth=2024-02
localDateFromMonth=REJECTED
```

Các nhãn `READ`, `FAILED` và `REJECTED` là cách chương trình mô tả kết quả, không phải thông báo nguyên văn từ JDK.

## 6. Đọc kết quả: những bằng chứng riêng biệt

### Đọc hết các trường không đồng nghĩa ngày hợp lệ

`rawInvalidCalendar=READ,index=10` và `rawDay=29` cho thấy `parseUnresolved` đã đọc được con số 29 từ đầu vào không có ngày thực tế tương ứng.

Cùng chuỗi đó, `LocalDate.parse` với `STRICT` từ chối; với `SMART` và `LENIENT` cho hai kết quả điều chỉnh khác nhau. Sự khác biệt thuộc giai đoạn phân giải, không phải do ba bộ đọc ra ba con số ngày khác nhau.

### Cú pháp có thể thất bại trước khi kiểm tra lịch

`rawWrongWidth=FAILED,index=0` xuất hiện vì cấu trúc tháng một chữ số không khớp quy tắc đọc đang dùng. Vị trí hiện tại của `ParsePosition` trong trường hợp thất bại không phải lúc nào cũng là vị trí nguyên nhân; khi cần chẩn đoán, xem thêm `getErrorIndex()`.

Bộ `flexibleWidth` chứng minh có thể đọc tháng/ngày ngắn rồi vẫn từ chối ngày không tồn tại. Nó không biến `STRICT` của bước phân giải thành bước bắt buộc tháng đủ hai chữ số.

### Đọc được một tiền tố chưa phải kiểm tra toàn bộ chuỗi

`rawTrailing=READ,index=10` chỉ nói đã đọc phần ngày ở đầu `2024-02-29extra`. `parseUnresolved` có vị trí không tự yêu cầu hết đầu vào.

`fullTrailing=REJECTED` cho thấy lời gọi phân tích đầy đủ từ chối phần dư. Cần phân biệt “đọc được các trường” với “toàn bộ trường đầu vào đã được kiểm tra”.

## 7. Phân giải còn phát hiện những trường không nhất quán

Mẫu:

```text
uuuu-MM-dd-DDD
```

chứa cả ngày/tháng và ngày thứ mấy trong năm. Trong năm nhuận 2024, ngày 29/02 là ngày thứ `060`, không phải `061`.

Chuỗi:

```text
2024-02-29-061
```

đọc được đầy đủ các số theo cấu trúc, nhưng hai cách xác định ngày không nhất quán. Bộ phân giải từ chối thay vì tùy tiện chọn một phía.

Đó là lý do không nên xem phân giải chỉ là kiểm tra từng trường độc lập trong phạm vi hợp lệ. `DAY_OF_MONTH=29` và `DAY_OF_YEAR=61` đều là các số có thể hợp lệ riêng lẻ; quan hệ giữa chúng mới gây lỗi.

Nếu dữ liệu cố ý cung cấp thông tin dư để đối chiếu, hãy giữ việc đối chiếu đó. Không loại bỏ một trường khỏi quá trình phân giải chỉ để đầu vào mâu thuẫn “đọc được”.

## 8. Phân giải thành công có thể vẫn chưa đủ cho kiểu đích

`monthOnly.parse("2024-02")` trong chương trình đọc toàn bộ chuỗi và giữ thông tin năm–tháng. `YearMonth.from` lấy được kết quả `2024-02`.

Nhưng `LocalDate.from` không tạo được một ngày vì chưa có ngày trong tháng. Đây là vấn đề **thiếu thông tin cho kiểu đích**, không phải tháng 02/2024 không hợp lệ.

Tương tự:

- Chỉ có ngày chưa đủ tạo `LocalDateTime` nếu không có quy tắc bổ sung giờ.
- Chỉ có ngày giờ địa phương chưa đủ xác định duy nhất `Instant` nếu không có offset/vùng thích hợp.
- Năm trong kỷ nguyên có thể cần thêm thông tin kỷ nguyên trước khi tạo ngày trong cấu hình nghiêm ngặt.

Khi gặp lỗi, xác định dữ liệu thực sự nên giữ kiểu nào. Chỉ bổ sung trường mặc định khi hợp đồng cho phép và giải thích được ý nghĩa của giá trị mặc định ấy.

## 9. Dùng API nào cho từng mục đích?

| Mục đích | API thường phù hợp |
| --- | --- |
| Nhập một ngày hoàn chỉnh để dùng ngay | `LocalDate.parse(text, formatter)` |
| Nhập một năm–tháng | `YearMonth.parse(text, formatter)` |
| Đọc đầy đủ và dùng truy vấn kiểu cụ thể | `formatter.parse(text, LocalDate::from)` |
| Chẩn đoán các trường trước phân giải | `formatter.parseUnresolved(text, position)` |
| Đọc một đoạn trong cấu trúc lớn hơn | API có `ParsePosition`, kèm kiểm tra phần còn lại |

`parseUnresolved` là API mức thấp. Nó không phân giải ngày, có thể chỉ đọc một phần chuỗi và có thể trả về null khi đọc thất bại. Không dùng một điều kiện “kết quả khác null” làm bộ xác nhận ngày hợp lệ. [Tài liệu `parseUnresolved`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parseUnresolved(java.lang.CharSequence,java.text.ParsePosition))

Cũng không nên giả định `LocalDate.from` sẽ tự chạy lại toàn bộ quy trình của bộ định dạng trên một kết quả chưa phân giải. Khi cần kết quả ngày ở mã sản phẩm, để API phân tích đầy đủ tạo ngày theo cấu hình đã chọn thường đơn giản hơn.

Với mã chẩn đoán, kiểm tra các trường cụ thể bằng `isSupported`/`getLong` thay vì phụ thuộc thứ tự hoặc hình thức chuỗi `toString()` của đối tượng trung gian.

## 10. Một quy trình tìm lỗi có thể áp dụng

Khi chuỗi không tạo được kiểu mong muốn:

1. Xác nhận mẫu và dữ liệu thực tế: thứ tự trường, dấu phân cách, độ rộng, chữ hoa/thường và ngôn ngữ.
2. Nếu chưa rõ lỗi ở đâu, dùng một phép đọc chưa phân giải trong mã chẩn đoán để xem có đọc được các trường và đến vị trí nào.
3. Kiểm tra đã đọc hết đầu vào chưa; thành công ở một tiền tố chưa đủ.
4. Xác định các trường cần cho kiểu đích có hiện diện không.
5. Kiểm tra quy tắc phân giải, hệ lịch và quan hệ giữa các trường.
6. Sau khi có giá trị có kiểu, áp dụng giới hạn nghiệp vụ như phạm vi năm hoặc ngày được đăng ký.

Bước chẩn đoán không phải yêu cầu thêm một tầng phân tích chưa phân giải vào mọi hàm sản phẩm. Sau khi tìm ra nguyên nhân, giữ đường xử lý chính đơn giản và kiểm chứng đúng hợp đồng.

Một bộ kiểm tra có ích nên bao gồm riêng: sai cú pháp, ngày không tồn tại, thiếu trường, trường mâu thuẫn, phần dư và giá trị hợp lệ. Nếu tất cả chỉ được gộp thành “chuỗi sai”, rất khó biết lần sửa sau có vô tình nới lỏng một loại đầu vào khác hay không.

## 11. Tự kiểm tra

1. Vì sao `parseUnresolved` có thể đọc thành công `2023-02-29`?
2. Gọi `parseStrict()` đã bảo đảm ngày 29/02/2023 bị từ chối chưa?
3. Vì sao `2024-02-29-061` có thể vượt bước đọc nhưng thất bại khi phân giải?
4. Một chuỗi năm–tháng hợp lệ có nhất thiết tạo được `LocalDate` không?
5. Nếu bước đọc chỉ đến vị trí 10 trong chuỗi dài 15 ký tự, nên kết luận gì?

Gợi ý đáp án:

1. Vì nó có thể đọc ba trường mà chưa kiểm tra chúng tạo thành ngày tồn tại.
2. Chưa; cần chọn quy tắc phân giải phù hợp, chẳng hạn `ResolverStyle.STRICT`.
3. Các trường có cấu trúc đúng nhưng chỉ đến hai ngày khác nhau.
4. Không; `LocalDate` còn cần ngày trong tháng, trong khi `YearMonth` phù hợp với thông tin đã có.
5. Mới đọc một tiền tố; phải xử lý phần còn lại theo hợp đồng, không coi đó là thành công cho toàn bộ trường.

Hãy tách câu hỏi “đọc ra trường nào?” khỏi “các trường có tạo được giá trị cần dùng không?”. Sự phân biệt này giúp chọn đúng cấu hình và giải thích đúng nguyên nhân lỗi phân tích ngày giờ.
