# Kiểm tra chuyển đổi đi-về giữa dữ liệu Java, chuỗi và kho lưu trữ

## 1. Đi-về thành công phải giữ điều gì?

Một phép chuyển đổi đi-về (round-trip) thường có dạng:

```text
Giá trị Java → biểu diễn trao đổi → kho lưu trữ
            → biểu diễn đọc lại → giá trị Java
```

Không ném lỗi chưa đủ để kết luận đường đi này đúng. Giá trị đọc lại có thể bị mất nano giây, đổi thời điểm do múi giờ, mất offset hoặc mất tên vùng mà chương trình vẫn chạy bình thường.

Trước khi kiểm tra, cần phát biểu **hợp đồng dữ liệu**:

- Phải giữ cùng ngày lịch?
- Phải giữ cùng bộ ngày giờ địa phương?
- Phải giữ cùng thời điểm trên trục thời gian?
- Có cần giữ offset và tên vùng ban đầu?
- Có cho phép giảm độ chính xác hoặc chuẩn hóa chuỗi không?

Ví dụ `2024-01-15T09:00+07:00` và `2024-01-15T02:00Z` là cùng thời điểm, nhưng không cùng bộ ngày giờ và offset. Một kiểm tra chỉ so `Instant` sẽ bỏ sót việc mất offset nếu yêu cầu phải giữ offset gốc.

Vì vậy, phải chọn tiêu chí bằng nhau trước khi chọn câu lệnh kiểm tra.

## 2. Ba loại hợp đồng đi-về

### 2.1. Giữ nguyên giá trị

Nếu không cho phép mất thông tin, yêu cầu là:

```text
decode(encode(value)) = value
```

Dấu bằng ở đây phải mang nghĩa phù hợp với kiểu, không nhất thiết là so chuỗi hay so tham chiếu đối tượng.

Ví dụ một `LocalDate` 29/2/2024 được định dạng rồi phân tích trở lại phải là đúng ngày ấy. Một `Instant` có phần giây `.123456789` phải giữ cả thời điểm và phần nano giây nếu hợp đồng yêu cầu độ chính xác nano.

### 2.2. Chuẩn hóa biểu diễn nhưng giữ giá trị

Một chuỗi đầu vào có thể có nhiều cách viết tương đương:

```text
2024-01-15T02:00:00.000Z
2024-01-15T02:00:00Z
```

Hai chuỗi này khác ký tự nhưng biểu diễn cùng `Instant`. Nếu đầu ra được quy định là dạng chuẩn, kiểm tra nên xác nhận:

1. Giá trị sau phân tích và định dạng lại vẫn giữ đúng ý nghĩa.
2. Chuỗi đầu ra đúng dạng chuẩn đã công bố.

Không yêu cầu chuỗi đầu vào phải giữ nguyên từng ký tự trừ khi ứng dụng thực sự cần lưu nguyên văn. Nếu cần bảo toàn nguyên văn cho một mục đích riêng, hãy giữ cả chuỗi gốc thay vì hy vọng đối tượng ngày giờ nhớ cách viết ban đầu.

### 2.3. Giảm độ chính xác theo quy tắc rõ ràng

Nếu kho lưu trữ chỉ giữ micro giây và hợp đồng chọn **cắt bỏ phần thấp hơn micro giây**, có thể yêu cầu:

```text
decode(store(encode(value))) = normalize(value)
```

Ví dụ:

```text
Giá trị gốc:       2024-01-15T02:00:00.123456789Z
Sau cắt micro:     2024-01-15T02:00:00.123456Z
```

Phải chỉ rõ cắt hay làm tròn, mức chính xác nào, và áp dụng ở đâu. Không tự thêm “sai lệch dưới một giây thì chấp nhận” để che lỗi. Một sai lệch múi giờ hoặc mất dữ liệu không nên biến thành kiểm tra đạt chỉ vì ngưỡng so sánh quá rộng.

Quy tắc chuẩn hóa cũng nên ổn định: chuẩn hóa lại giá trị đã chuẩn hóa không được tiếp tục làm nó thay đổi.

## 3. Chọn phép so theo kiểu và yêu cầu

| Dữ liệu cần giữ | Cách so điển hình | Điều có thể bị bỏ sót nếu chọn sai |
| --- | --- | --- |
| Ngày lịch `LocalDate` | `expected.equals(actual)` | Không được tự thêm hoặc đổi ngày qua múi giờ |
| Bộ ngày giờ `LocalDateTime` | `equals`, gồm cả nano | So thời điểm đòi hỏi thêm múi giờ chưa có |
| Thời điểm `Instant` | `equals` hoặc so giây epoch và nano | So chuỗi địa phương có thể hiểu nhầm cách hiển thị |
| `OffsetDateTime` cần giữ cả offset | `equals` | Chỉ so `toInstant()` không phát hiện đổi offset |
| Chỉ cần thời điểm từ `OffsetDateTime` | So `toInstant()`, hoặc `isEqual` | Đây không phải kiểm tra bảo toàn toàn bộ đối tượng |
| `ZonedDateTime` cần giữ vùng | Kiểm tra giá trị đầy đủ và `ZoneId` | Chuỗi chỉ còn offset có thể mất tên vùng |
| Kỳ `YearMonth` | `equals` | Không tự gắn một ngày rồi đánh đồng kỳ với ngày |
| Chuỗi chuẩn trao đổi | So chuỗi với mẫu đầu ra mong đợi | So được giá trị chưa chắc đúng quy ước giao thức |

`OffsetDateTime.equals` kiểm tra bộ ngày giờ và offset, còn `isEqual` kiểm tra thời điểm. Sự khác nhau này được quy định ở [OffsetDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html).

Không dùng `==` để kiểm tra bằng nhau theo giá trị của các đối tượng ngày giờ. Hai đối tượng được tạo ở hai thời điểm khác nhau vẫn có thể biểu diễn cùng dữ liệu.

## 4. Kiểm tra từng chặng và cả đường đi hoàn chỉnh

Nên chia bằng chứng thành các chặng có thể xác định lỗi:

1. **Java → chuỗi → Java:** kiểm tra định dạng, phân tích, ý nghĩa và độ chính xác.
2. **Chuỗi → kho → chuỗi:** kiểm tra ghi/đọc thật, mã hóa và thay đổi ngoài ý muốn.
3. **Java → kho → Java:** kiểm tra toàn bộ đường sử dụng thực tế, gồm driver hoặc bộ ánh xạ nếu có.

Chỉ kiểm tra bộ định dạng không chứng minh được cột cơ sở dữ liệu giữ đủ phần giây. Ngược lại, chỉ thấy các byte trong tệp giữ nguyên không chứng minh bộ phân tích đọc đúng ý nghĩa.

Khi một kiểm tra thất bại, nên quan sát đầu ra trung gian:

- Chuỗi thực sự được gửi đi.
- Kiểu và giá trị được ghi.
- Giá trị thô đọc lại.
- Đối tượng Java sau bước giải mã.
- Múi giờ/locale và mức chính xác được dùng tại mỗi nơi.

Một phép đi-về cũng có thể che **hai lỗi bù nhau**. Ví dụ cả bên ghi và bên đọc đều dùng cùng một đơn vị sai so với giao thức công bố. Giá trị Java có thể quay lại như cũ nhưng hệ thống khác đọc sai. Vì thế, cần có cả mẫu dữ liệu mong đợi được xác định độc lập, không chỉ kiểm tra hai hàm do cùng một đoạn mã tạo ra luôn khớp nhau.

## 5. Thiết kế chuỗi trao đổi có thể kiểm tra được

Với giao thức trao đổi, hãy xác định kiểu trước rồi chọn bộ định dạng tương ứng. Ví dụ:

- `LocalDate`: ngày ISO không có giờ.
- `LocalDateTime`: ngày giờ địa phương, chưa có offset.
- `Instant`: thời điểm biểu diễn rõ UTC, chẳng hạn chuỗi có `Z`.
- `OffsetDateTime`: giữ offset nếu hợp đồng yêu cầu.
- `ZonedDateTime`: cần dạng có tên vùng nếu phải giữ `ZoneId`.

Một chuỗi chỉ có offset như `+01:00` không tự lưu quy tắc của `Europe/Paris`. Tại một ngày cụ thể chúng có thể cho cùng thời điểm, nhưng tên vùng cần thiết để áp quy tắc theo các ngày khác.

Nếu dùng mẫu tùy chỉnh, bộ định dạng phải có locale và chế độ giải quyết ngày rõ ràng. Trong chương trình bên dưới, mẫu `uuuu-MM-dd` cùng `ResolverStyle.STRICT` từ chối 29/2 ở năm thường. `uuuu` biểu diễn năm trên trục năm; không tùy ý thay bằng `yyyy`, vốn biểu diễn năm trong kỷ nguyên.

Không chỉ thử dữ liệu đúng. Một đường nhập yêu cầu nghiêm ngặt phải từ chối ngày sai, thay vì tự sửa ngày rồi vẫn được coi là giữ nguyên đầu vào. Các bộ định dạng, quy tắc phân tích và cấu hình được mô tả ở [DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html).

## 6. Chọn dữ liệu có khả năng làm lộ mất thông tin

| Nhóm ca | Dữ liệu gợi ý | Lỗi cần phát hiện |
| --- | --- | --- |
| Ngày nhuận | 29/2/2024 và chuỗi 29/2/2023 | Xác thực hoặc tự điều chỉnh sai |
| Trước epoch | Cuối năm 1969, có nano | Nhầm dấu hoặc cách quy đổi epoch |
| Phần giây dài | `.123456789` | Bị cắt xuống mili/micro ngoài ý muốn |
| Sát cuối ngày | 23:59:59 có nano | Làm tròn hoặc đổi múi giờ làm sang ngày khác |
| Offset khác UTC | Cùng thời điểm ở `+07:00` và `Z` | Nhầm cùng thời điểm với cùng offset |
| Tên vùng | Giá trị có `[Europe/Paris]` | Mất vùng khi chỉ lưu offset |
| Chuỗi tương đương | Có và không có `.000` | Nhầm chuẩn hóa với mất giá trị |
| Chuỗi sai | Rỗng, tháng 13, ngày không tồn tại | Bộ phân tích chấp nhận sai |
| Giá trị thiếu | SQL `NULL` hoặc trường vắng mặt | Tự đổi thành epoch, ngày hiện tại hoặc chuỗi rỗng |

Với dữ liệu thiếu, hợp đồng phải quy định rõ có được thiếu hay không và biểu diễn thế nào. `NULL`, chuỗi rỗng và `1970-01-01T00:00Z` không tự động cùng nghĩa.

Không lấy mọi giá trị cực trị của Java làm mặc định cho mọi kho. Miền biểu diễn của một cột SQL hoặc hệ thống bên ngoài có thể hẹp hơn; hãy kiểm tra ranh giới được hỗ trợ trong hợp đồng thực tế.

## 7. Chương trình Java 17+ kiểm tra chuỗi và tệp thật

Lưu mã sau thành `DateTimeRoundTrip.java`. Chương trình không cần thư viện ngoài. Nó ghi và đọc một tệp tạm bằng UTF-8, rồi xóa đúng tệp đó trong `finally`.

Có hai đường lưu được kiểm tra riêng:

- Giữ nguyên nano giây bằng chuỗi ISO.
- Chủ động cắt xuống micro giây **trong ứng dụng trước khi ghi tệp**.

Đường thứ hai minh họa hợp đồng giảm độ chính xác; nó không giả lập hay khẳng định quy tắc làm tròn của bất kỳ cơ sở dữ liệu nào.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.YearMonth;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoUnit;
import java.util.Locale;
import java.util.Objects;

public class DateTimeRoundTrip {
    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Runnable action) {
        try {
            action.run();
        } catch (DateTimeParseException expected) {
            checks++;
            return;
        }
        throw new AssertionError("Expected DateTimeParseException");
    }

    public static void main(String[] args) throws Exception {
        DateTimeFormatter strictDate = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        for (LocalDate date : new LocalDate[] {
                LocalDate.of(2024, 2, 29),
                LocalDate.of(1969, 12, 31),
                LocalDate.of(2000, 2, 29)}) {
            eq(LocalDate.parse(date.format(strictDate), strictDate), date);
        }
        rejects(() -> LocalDate.parse("2023-02-29", strictDate));
        rejects(() -> LocalDate.parse("2024-13-01", strictDate));
        rejects(() -> LocalDate.parse("", strictDate));

        LocalDateTime local = LocalDateTime.parse("2024-06-30T23:59:59.123456789");
        eq(LocalDateTime.parse(local.toString()), local);
        YearMonth period = YearMonth.of(2024, 2);
        eq(YearMonth.parse(period.toString()), period);

        Instant original = Instant.parse("2024-01-15T02:00:00.123456789Z");
        for (Instant value : new Instant[] {
                Instant.EPOCH,
                Instant.parse("1969-12-31T23:59:59.999999999Z"),
                original}) {
            eq(Instant.parse(value.toString()), value);
        }

        String suppliedText = "2024-01-15T02:00:00.000Z";
        String canonicalText = Instant.parse(suppliedText).toString();
        eq(canonicalText, "2024-01-15T02:00:00Z");
        eq(Instant.parse(canonicalText), Instant.parse(suppliedText));
        eq(canonicalText.equals(suppliedText), false);

        OffsetDateTime suppliedOffset =
                OffsetDateTime.parse("2024-01-15T09:00:00+07:00");
        OffsetDateTime utc = OffsetDateTime.parse("2024-01-15T02:00:00Z");
        eq(suppliedOffset.toInstant(), utc.toInstant());
        eq(suppliedOffset.equals(utc), false);
        eq(OffsetDateTime.parse(suppliedOffset.toString()), suppliedOffset);

        ZonedDateTime zoned =
                ZonedDateTime.parse("2024-01-15T09:00:00+01:00[Europe/Paris]");
        eq(ZonedDateTime.parse(zoned.toString()), zoned);
        ZonedDateTime offsetOnly =
                ZonedDateTime.parse(zoned.toOffsetDateTime().toString());
        eq(offsetOnly.toInstant(), zoned.toInstant());
        eq(offsetOnly.getZone().equals(zoned.getZone()), false);

        Path file = Files.createTempFile("date-time-round-trip-", ".txt");
        boolean fileExact;
        boolean fileNormalized;
        Instant normalized = original.truncatedTo(ChronoUnit.MICROS);
        try {
            Files.writeString(file, original.toString(), StandardCharsets.UTF_8);
            String storedText = Files.readString(file, StandardCharsets.UTF_8);
            eq(storedText, original.toString());
            Instant restored = Instant.parse(storedText);
            eq(restored, original);
            fileExact = restored.equals(original);

            // Explicit application policy: truncate to microseconds.
            Files.writeString(file, normalized.toString(), StandardCharsets.UTF_8);
            Instant restoredMicros =
                    Instant.parse(Files.readString(file, StandardCharsets.UTF_8));
            eq(restoredMicros, normalized);
            eq(restoredMicros.equals(original), false);
            eq(restoredMicros.truncatedTo(ChronoUnit.MICROS), normalized);
            fileNormalized = restoredMicros.equals(normalized);
        } finally {
            Files.deleteIfExists(file);
        }

        System.out.println("canonicalText=" + canonicalText);
        System.out.println("sameInstant=" + suppliedOffset.toInstant().equals(utc.toInstant()));
        System.out.println("sameOffsetDateTime=" + suppliedOffset.equals(utc));
        System.out.println("zoneRetainedByOffsetOnly="
                + offsetOnly.getZone().equals(zoned.getZone()));
        System.out.println("fileExact=" + fileExact);
        System.out.println("normalized=" + normalized);
        System.out.println("fileNormalized=" + fileNormalized);
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 DateTimeRoundTrip.java
java DateTimeRoundTrip
```

Stdout:

```text
canonicalText=2024-01-15T02:00:00Z
sameInstant=true
sameOffsetDateTime=false
zoneRetainedByOffsetOnly=false
fileExact=true
normalized=2024-01-15T02:00:00.123456Z
fileNormalized=true
PASS checks=25
```

Hàm `eq` chủ động ném `AssertionError` khi sai nên không cần cờ `-ea`. Hàm `rejects` xác nhận các chuỗi sai được từ chối bằng `DateTimeParseException`.

Ý nghĩa các dòng:

- `canonicalText` cho thấy biểu diễn có thể được chuẩn hóa mà không đổi giá trị.
- `sameInstant=true` cùng `sameOffsetDateTime=false` chứng minh hai tiêu chí so sánh khác nhau.
- `zoneRetainedByOffsetOnly=false` là kết quả **mong đợi của ca phát hiện mất vùng**, không phải một lần lưu bảo toàn vùng thành công.
- `fileExact` xác nhận đường lưu chuỗi gốc giữ đúng `Instant`.
- `fileNormalized` xác nhận đường cắt micro khớp chính sách đã nêu, đồng thời chương trình xác nhận nó khác giá trị nano gốc.

Các phép thao tác tệp được mô tả ở [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html). Mô hình giây epoch và nano giây của thời điểm được mô tả ở [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html).

## 8. Chạy lại dưới môi trường khác

Vì chương trình dùng biểu diễn và kiểu dữ liệu rõ nghĩa, kết quả nên ổn định khi đổi múi giờ mặc định. Có thể chạy hai lần:

```shell
java "-Duser.timezone=UTC" DateTimeRoundTrip
java "-Duser.timezone=GMT+07:00" DateTimeRoundTrip
```

Đặt đối số cấu hình trong dấu nháy cũng giúp tránh cách phân tích đối số của một số shell. Cả hai lần phải cho cùng stdout ở trên và vượt qua 25 kiểm tra.

Đây là một phép thử phát hiện phụ thuộc môi trường cho chương trình đã cho. Khi đường thực tế có driver, bộ tuần tự hóa hoặc dịch vụ khác, phải chạy lại chính đường đó. Việc ví dụ tệp vượt qua ở hai múi giờ không tự chứng minh toàn hệ thống không có phụ thuộc ngầm.

Nếu giao thức có chữ tên tháng, hãy kiểm tra thêm các locale được hỗ trợ. Với múi giờ vùng có chuyển offset, cần ca khoảng thiếu và khoảng lặp giờ; việc giữ một thời điểm và việc giữ một lịch địa phương có thể đòi hỏi chính sách khác nhau.

## 9. Mở rộng sang kiểm tra cơ sở dữ liệu

Kiểm tra kho SQL cần thật sự ghi và đọc qua driver, không chỉ đổi sang `Timestamp` trong bộ nhớ. Một kiểm tra tích hợp nên có các bước:

1. Tạo dữ liệu và kết quả mong đợi từ hợp đồng đã công bố.
2. Ghi vào đúng kiểu cột bằng đúng đường ứng dụng sử dụng.
3. Hoàn tất các bước ghi cần thiết để phép đọc thực sự thấy dữ liệu.
4. Đọc lại bằng JDBC hoặc bộ ánh xạ thực tế.
5. So theo ngữ nghĩa và mức chính xác đã chọn.
6. Dọn dữ liệu thử hoặc dùng giao dịch cô lập phù hợp.

Nếu dùng ORM, bảo đảm phép đọc không chỉ trả đối tượng đang nằm trong bộ nhớ đệm của phiên làm việc. Cần quan sát việc đọc kho thật để kiểm tra biến đổi do cột và driver.

Một đoạn kiểm tra phần đọc cho dữ liệu địa phương có thể như sau:

```java
// Mã minh họa trong một kiểm tra tích hợp, không phải chương trình độc lập.
// expected đã được tạo từ fixture; rs đã trỏ đến hàng vừa ghi.
// local_value là cột có hợp đồng giữ ngày giờ địa phương.
LocalDateTime actual =
        rs.getObject("local_value", LocalDateTime.class);
if (!Objects.equals(actual, expected)) {
    throw new AssertionError("Local date-time changed during storage");
}
```

Khả năng chuyển từ cột sang kiểu Java có yêu cầu hỗ trợ từ driver; xem [ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html). Với thời điểm, hãy dùng đường ánh xạ giữ thời điểm và so `Instant`, đồng thời công bố cách diễn giải múi giờ của cột.

Đối với cột có độ chính xác thấp hơn Java, không dùng ngay `expected` nano gốc nếu hợp đồng đã chọn giảm độ chính xác. Tính giá trị mong đợi theo quy tắc độc lập, có các mẫu cụ thể phân biệt cắt với làm tròn. Ví dụ giá trị gần ngưỡng sang giây tiếp theo giúp phát hiện việc làm tròn khác cắt.

Bài này không cấu hình một hệ quản trị hoặc driver cụ thể, nên phần chương trình chỉ chứng minh đường chuỗi và tệp đã chạy. Các kiểm tra SQL là việc cần thực hiện trong môi trường lưu trữ thực tế.

## 10. Lỗi thường gặp

- **Chỉ kiểm tra không có ngoại lệ:** thao tác có thể thành công nhưng mất độ chính xác hoặc đổi thời điểm.
- **So chuỗi thay vì so ý nghĩa:** biểu diễn có thể được chuẩn hóa hợp lệ.
- **Chỉ so thời điểm khi yêu cầu giữ offset/vùng:** mất thông tin vẫn vượt qua kiểm tra.
- **Chỉ so ngày giờ địa phương khi yêu cầu giữ thời điểm:** có thể bỏ sót diễn giải sai múi giờ.
- **Dùng chính mã chuyển đổi để tạo mọi kết quả mong đợi:** hai lỗi tương ứng có thể che nhau.
- **Bỏ qua ca âm trước epoch và phần nano:** chỉ thử giá trị tròn giây thường không làm lộ lỗi.
- **Cho phép sai số quá rộng:** che lỗi thay vì xác nhận chính sách độ chính xác.
- **Thay `NULL` bằng một giá trị mặc định không được yêu cầu:** làm mất sự phân biệt giữa thiếu và có dữ liệu.
- **Kiểm tra bộ nhớ nhưng khẳng định kho đã đúng:** cần ghi/đọc thật qua đường tích hợp.

## 11. Thực hành

1. **Thêm mẫu `2024-12-31T23:59:59.999999999Z`.** Đường giữ nguyên nano phải đọc lại chính xác. Nếu chuyển sang chính sách làm tròn xuống độ chính xác khác, nêu rõ kết quả mong đợi, kể cả khả năng sang năm tiếp theo khi làm tròn.

2. **Yêu cầu giữ offset gốc của một `OffsetDateTime`.** Sửa tiêu chí kiểm tra thành bằng nhau toàn bộ giá trị; chỉ so `Instant` không đủ.

3. **Yêu cầu giữ tên vùng.** Dùng đường trao đổi chứa `ZoneId` hoặc lưu trường vùng riêng. Chứng minh ca chỉ lưu offset không vượt qua hợp đồng này.

4. **Chuỗi đầu vào có `.000Z`, đầu ra không có phần lẻ.** Xác nhận cùng `Instant` và đúng dạng chuẩn; không đánh dấu mất giá trị chỉ vì số ký tự giảm.

5. **Cột lưu micro giây nhưng đầu vào có nano giây.** Tạo ít nhất hai mẫu phân biệt cắt và làm tròn, rồi đối chiếu với quy tắc thực tế đã chọn; không lấy kết quả bất kỳ từ kho làm chuẩn mà không đánh giá.

Một kiểm tra chuyển đổi đi-về có giá trị khi nó chứng minh đúng thông tin cần giữ, qua đúng đường dữ liệu thực tế, với các thay đổi được cho phép đã được nêu cụ thể.
