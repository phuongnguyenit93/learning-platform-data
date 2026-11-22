# Độ rộng, dấu và phần lẻ của giây

## 1. Ba quyết định khác nhau trong một trường số

Khi trao đổi ngày giờ dưới dạng văn bản, “cùng một giá trị” chưa đủ để bảo đảm chuỗi đúng hợp đồng. Ngày 7 có thể phải viết `07`; năm âm cần giữ dấu `-`; phần lẻ `.1` giây phải được hiểu là 100 mili giây chứ không phải 1 nano giây. Chọn sai quy tắc có thể làm chuỗi bị từ chối hoặc làm mất thông tin khi ghi ra rồi đọc lại.

Với `DateTimeFormatterBuilder`, cần phân biệt:

- **Độ rộng:** có bao nhiêu chữ số, có thêm số 0 ở đầu không?
- **Dấu:** có nhận/in `+`, `-` hay chỉ cho phép số không âm?
- **Phần lẻ:** các chữ số biểu diễn tỷ lệ của một giây, với độ chính xác nào?

`appendValue()`, `SignStyle`, `padNext()` và `appendFraction()` giải quyết những khía cạnh khác nhau. Không nên dùng một chuỗi thao tác thêm ký tự bằng tay để thay cho việc mô tả đúng từng quy tắc.

## 2. Độ rộng trường số và phần đệm

### Số chữ số cố định hoặc biến thiên

Những dạng lời gọi thường gặp:

| Lời gọi builder | Ý nghĩa cần nhận biết |
| --- | --- |
| `appendValue(DAY_OF_MONTH)` | Ghi giá trị số theo độ rộng tự nhiên, chẳng hạn `7` |
| `appendValue(DAY_OF_MONTH, 2)` | Dùng hai chữ số và thêm 0 ở đầu, chẳng hạn `07` |
| `appendValue(YEAR, 4, 10, signStyle)` | Điều khiển riêng độ rộng tối thiểu, tối đa và quy tắc dấu |

Trong chế độ đọc cú pháp chặt chẽ mặc định, độ rộng cố định yêu cầu đúng số chữ số; dạng có `minWidth`/`maxWidth` nhận số chữ số trong khoảng đã chọn. Dấu không được tính vào số chữ số: `-0007` có bốn chữ số và một ký tự dấu.

Khi ghi, độ rộng tối thiểu có thể thêm 0 ở đầu, còn vượt độ rộng tối đa có thể gây lỗi; không được hiểu `appendValue(field, 2)` là tự cắt một giá trị ba chữ số xuống còn hai. Độ rộng cũng không thay thế kiểm tra miền giá trị: đọc đủ hai chữ số tháng không chứng minh tháng 13 tồn tại.

### Đệm bằng khoảng trắng khác với thêm số 0

`padNext(3, ' ')` áp dụng cho phần tử được thêm tiếp theo, để phần hiển thị chiếm ba ký tự. Trong chương trình bên dưới, ngày 7 được ghi thành `[  7]`, còn trường số hai chữ số được ghi thành `[07]`. Dấu ngoặc chỉ giúp nhìn thấy khoảng trắng, không thuộc bộ định dạng.

Phần đệm tính trên biểu diễn của phần tử, có thể bao gồm dấu nếu phần tử có in dấu. Ngược lại, độ rộng của `appendValue()` nói đến các chữ số. `padNext()` không tự làm mọi trường còn lại có cùng độ rộng; cần đặt ở đúng vị trí cần đệm.

Với định dạng ghép số không có dấu phân cách, ví dụ năm–tháng–ngày viết liền, phải kiểm soát ranh giới trường. Builder có quy tắc dành chữ số cho các trường số liền kề có độ rộng cố định trong những cấu hình phù hợp; không nên tự giả định rằng mọi tổ hợp trường biến thiên đều phân chia được rõ ràng. Khi hợp đồng dùng cố định bốn chữ số năm, hai tháng và hai ngày, hãy mô tả những độ rộng đó trực tiếp.

## 3. `SignStyle`: dấu là một phần của hợp đồng

[Java SE 21 — SignStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/SignStyle.html) mô tả các cách điều khiển dấu. Bảng sau tập trung vào chiều ghi số; chương trình sẽ kiểm chứng bằng các năm `7`, `-7`, `10000` với độ rộng tối thiểu 4:

| Kiểu dấu | Cách ghi số |
| --- | --- |
| `NORMAL` | Chỉ ghi dấu khi số âm |
| `ALWAYS` | Luôn ghi dấu, số không âm dùng `+` |
| `NEVER` | Không ghi dấu, kể cả đầu vào âm; chỉ ghi trị tuyệt đối |
| `NOT_NEGATIVE` | Không cho phép giá trị âm khi ghi |
| `EXCEEDS_PAD` | Số âm có `-`; số dương có `+` khi số chữ số vượt ngưỡng độ rộng tối thiểu |

Hai lựa chọn dễ nhầm là `NEVER` và `NOT_NEGATIVE`. `NEVER` có thể biến năm `-7` thành chuỗi `0007`, làm mất dấu. `NOT_NEGATIVE` từ chối năm âm thay vì âm thầm bỏ dấu.

Ở chiều đọc cú pháp chặt chẽ, `ALWAYS` yêu cầu có dấu; `NORMAL` cho phép dấu âm nhưng không nhận dấu cộng; `NEVER` và `NOT_NEGATIVE` không nhận dấu. Với `EXCEEDS_PAD`, dấu cộng gắn với quy tắc vượt độ rộng; không thể tự thêm `+` trước mọi số rồi mong mọi formatter đều nhận. Các chế độ đọc cú pháp linh hoạt có thể thay đổi quy tắc chấp nhận dấu, nên phải kiểm tra đúng cấu hình đang dùng.

`SignStyle` ở đây là dấu của một trường số, không phải cấu hình để phân tích độ lệch múi giờ `+07:00`. Độ lệch cần những phần tử thích hợp như `appendOffset()` hoặc `appendOffsetId()`.

## 4. Phần lẻ của giây là tỷ lệ, không phải số nano viết nguyên dạng

Với `NANO_OF_SECOND`, miền phần lẻ nằm từ 0 đến 999.999.999 nano giây. Vị trí thập phân quyết định ý nghĩa của chuỗi:

| Phần lẻ trong chuỗi | Giá trị phần giây | Nano giây |
| --- | --- | ---: |
| `.1` | Một phần mười giây | 100.000.000 |
| `.01` | Một phần trăm giây | 10.000.000 |
| `.001` | Một mili giây | 1.000.000 |
| `.000000001` | Một nano giây | 1 |

Đó là lý do không thay `appendFraction(NANO_OF_SECOND, ...)` bằng `appendValue(NANO_OF_SECOND)` khi hợp đồng yêu cầu phần thập phân của giây. Giá trị nguyên `1` nano giây cần dạng `.000000001`, không phải `.1`.

Lời gọi `appendFraction(NANO_OF_SECOND, minWidth, maxWidth, decimalPoint)` chọn độ rộng phần lẻ và việc quản lý dấu thập phân. `decimalPoint=true` dùng dấu từ `DecimalStyle`; chương trình dùng `DecimalStyle.STANDARD` để quy định dấu `.` rõ ràng. Nếu chọn `false`, phần tử không tự thêm/đọc dấu thập phân, nên hợp đồng phải xử lý dấu ấy ở nơi khác.

Ví dụ dùng `0, 9, true` cho phép không có phần lẻ, tối đa 9 chữ số và bỏ bớt số 0 cuối khi ghi nếu không bị độ rộng tối thiểu yêu cầu giữ lại. Nếu cần đúng ba chữ số, có thể chọn `3, 3, true` hoặc mẫu `SSS` với dấu chấm được đặt phù hợp.

### Bớt chữ số không có nghĩa làm tròn

Mẫu `HH:mm:ss.SSS` xuất giá trị nano `123456789` thành `.123`. Các chữ số thấp hơn bị bỏ khỏi chuỗi; không có bước làm tròn lên `.124`. Đọc lại chuỗi ấy chỉ còn `123000000` nano giây. Đối tượng gốc chưa đổi, nhưng chuỗi trung gian đã mất độ chính xác.

Quy tắc không làm tròn của phần lẻ được nêu trong [Java SE 21 — appendFraction()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html#appendFraction(java.time.temporal.TemporalField,int,int,boolean)). Nếu nghiệp vụ cần làm tròn thời gian, phải định nghĩa và thực hiện phép làm tròn riêng trước bước xuất, bao gồm cách xử lý khi phần giây vượt sang giây tiếp theo.

## 5. Chương trình chạy đầy đủ

Lưu mã sau vào `WidthSignFractionDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài:

```java
import java.time.*;
import java.time.format.*;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class WidthSignFractionDemo {
    private static void checkTime(String text, DateTimeFormatter formatter) {
        try {
            LocalTime time = LocalTime.parse(text, formatter);
            System.out.println(text + " -> nano=" + time.getNano());
        } catch (DateTimeParseException ex) {
            System.out.println(text + " -> DateTimeParseException");
        }
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2025, 6, 7);
        DateTimeFormatter zeroFilled = new DateTimeFormatterBuilder()
                .appendValue(ChronoField.DAY_OF_MONTH, 2)
                .toFormatter(Locale.ROOT);
        DateTimeFormatter spacePadded = new DateTimeFormatterBuilder()
                .padNext(3, ' ')
                .appendValue(ChronoField.DAY_OF_MONTH)
                .toFormatter(Locale.ROOT);
        System.out.println("zero=[" + date.format(zeroFilled) + "]");
        System.out.println("pad =[" + date.format(spacePadded) + "]");

        for (SignStyle style : SignStyle.values()) {
            DateTimeFormatter year = new DateTimeFormatterBuilder()
                    .appendValue(ChronoField.YEAR, 4, 10, style)
                    .toFormatter(Locale.ROOT);
            String negative;
            try {
                negative = year.format(Year.of(-7));
            } catch (DateTimeException ex) {
                negative = "DateTimeException";
            }
            System.out.println(style + " -> " + year.format(Year.of(7))
                    + " | " + negative + " | " + year.format(Year.of(10000)));
        }

        LocalTime sample = LocalTime.of(8, 9, 10, 123_456_789);
        DateTimeFormatter millis = DateTimeFormatter
                .ofPattern("HH:mm:ss.SSS", Locale.ROOT);
        System.out.println("three digits = " + sample.format(millis));
        System.out.println("nano after reparse = "
                + LocalTime.parse(sample.format(millis), millis).getNano());

        DateTimeFormatter fraction = new DateTimeFormatterBuilder()
                .appendPattern("HH:mm:ss")
                .appendFraction(ChronoField.NANO_OF_SECOND, 0, 9, true)
                .toFormatter(Locale.ROOT)
                .withDecimalStyle(DecimalStyle.STANDARD)
                .withResolverStyle(ResolverStyle.STRICT);
        checkTime("08:09:10", fraction);
        checkTime("08:09:10.1", fraction);
        checkTime("08:09:10.", fraction);
        checkTime("08:09:10.123456789", fraction);
        checkTime("08:09:10.1234567890", fraction);
        System.out.println("zero fraction = "
                + LocalTime.of(8, 9, 10).format(fraction));
        System.out.println("trimmed fraction = "
                + LocalTime.of(8, 9, 10, 120_000_000).format(fraction));

        DateTimeFormatter optionalNonEmptyFraction = new DateTimeFormatterBuilder()
                .appendPattern("HH:mm:ss")
                .optionalStart()
                    .appendFraction(ChronoField.NANO_OF_SECOND, 1, 9, true)
                .optionalEnd()
                .toFormatter(Locale.ROOT)
                .withDecimalStyle(DecimalStyle.STANDARD)
                .withResolverStyle(ResolverStyle.STRICT);
        System.out.println("optional non-empty fraction:");
        checkTime("08:09:10", optionalNonEmptyFraction);
        checkTime("08:09:10.1", optionalNonEmptyFraction);
        checkTime("08:09:10.", optionalNonEmptyFraction);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 WidthSignFractionDemo.java
java WidthSignFractionDemo
```

Kết quả:

```text
zero=[07]
pad =[  7]
NORMAL -> 0007 | -0007 | 10000
ALWAYS -> +0007 | -0007 | +10000
NEVER -> 0007 | 0007 | 10000
NOT_NEGATIVE -> 0007 | DateTimeException | 10000
EXCEEDS_PAD -> 0007 | -0007 | +10000
three digits = 08:09:10.123
nano after reparse = 123000000
08:09:10 -> nano=0
08:09:10.1 -> nano=100000000
08:09:10. -> nano=0
08:09:10.123456789 -> nano=123456789
08:09:10.1234567890 -> DateTimeParseException
zero fraction = 08:09:10
trimmed fraction = 08:09:10.12
optional non-empty fraction:
08:09:10 -> nano=0
08:09:10.1 -> nano=100000000
08:09:10. -> DateTimeParseException
```

Mỗi dòng kiểu dấu lần lượt là kết quả cho năm 7, năm -7 và năm 10000. `DateTimeException` được hàm thử nghiệm ghi lại khi kiểu `NOT_NEGATIVE` không cho xuất năm âm. Các dòng lỗi phân tích cũng chỉ in tên ngoại lệ để kết quả dễ đối chiếu, không phải giá trị do thư viện trả về thay cho thời gian.

## 6. Phần lẻ tùy chọn nhưng không được rỗng sau dấu chấm

Kết quả `08:09:10. -> nano=0` cho thấy độ rộng tối thiểu 0 có thể nhận dấu thập phân mà không có chữ số theo sau. Nếu hợp đồng yêu cầu **hoặc không có phần lẻ, hoặc có từ 1 đến 9 chữ số**, hãy dùng nhóm tùy chọn bao quanh `appendFraction(..., 1, 9, true)` như `optionalNonEmptyFraction` trong chương trình.

Cấu trúc này có ba tính chất đã được kiểm chứng:

- Chuỗi không có dấu chấm vẫn được đọc, phần nano bằng 0.
- Có dấu chấm và ít nhất một chữ số thì đọc phần lẻ.
- Chỉ có dấu chấm cuối chuỗi bị từ chối vì nhóm phần lẻ không hoàn thành, còn ký tự dư khiến việc đọc toàn bộ chuỗi thất bại.

Đừng chỉ thay `minWidth` từ 0 thành 1 mà không thêm nhóm tùy chọn nếu vẫn muốn chấp nhận trường hợp hoàn toàn không có phần lẻ. Khi ấy phần lẻ trở thành bắt buộc ở vị trí đó.

## 7. Áp dụng đúng cho chiều đọc và chiều ghi

**Chọn độ chính xác từ hợp đồng dữ liệu.** Nếu đầu ra chỉ được giữ mili giây, hiểu rằng phần nano nhỏ hơn sẽ không còn sau một vòng ghi–đọc. Nếu cần bảo toàn nano, dùng bộ định dạng cho phép đến 9 chữ số và kiểm tra toàn bộ đường truyền dữ liệu.

**Không coi thêm số 0 là tăng độ chính xác của nguồn.** Chuỗi `.1`, `.10`, `.100` có cùng giá trị thời gian. Sau phân tích, `LocalTime` không ghi nhớ nguồn đã có một hay ba chữ số. Nếu số chữ số gốc mang ý nghĩa về độ chính xác đo, cần lưu thông tin đó riêng.

**Đọc cú pháp và phân giải thời gian là hai tầng khác nhau.** Các ví dụ builder dùng chế độ đọc chặt chẽ mặc định; `withResolverStyle(STRICT)` kiểm soát việc phân giải các trường thành thời gian. Nó không phải lệnh duy nhất quyết định độ rộng, dấu hay số chữ số phần lẻ. Nếu trước đó đã bật `parseLenient()`, phải xét lại các quy tắc đọc thay vì chỉ nhìn `ResolverStyle`.

**Đừng dùng cắt chuỗi để xử lý trường vượt rộng.** Cắt năm hoặc dấu có thể đổi giá trị; cắt phần lẻ có thể mất độ chính xác. Bộ định dạng phải mô tả rõ thứ được phép, và ứng dụng phải có quyết định riêng nếu muốn giảm độ chính xác.

Bài tập: với thời gian có `999999999` nano giây, dự đoán mẫu `HH:mm:ss.SSS` sẽ xuất phần lẻ `.999`, không tự tăng giây. Sau đó đổi formatter phần lẻ sang `3, 3, true` và kiểm tra rằng đầu vào có `.1` không đáp ứng đúng ba chữ số trong chế độ đọc chặt chẽ, còn `.100` thì đáp ứng và tạo phần nano `100000000`.
