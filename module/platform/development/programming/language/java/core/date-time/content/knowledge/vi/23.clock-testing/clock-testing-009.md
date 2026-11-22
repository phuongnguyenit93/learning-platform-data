# Kiểm thử cuối tháng, năm nhuận, nửa đêm và chuyển DST

## Các lỗi thời gian thường xuất hiện ở ranh giới

Một hàm lấy ngày hôm nay có thể chạy đúng suốt buổi trưa nhưng sai gần nửa đêm nếu dùng nhầm múi giờ. Lịch lặp ngày 31 có thể hoạt động trong tháng 1 nhưng hỏng ở tháng 2. Một cuộc hẹn lúc 02:30 có thể không tồn tại hoặc xuất hiện hai lần vào ngày chuyển giờ mùa hè.

Kiểm thử thời gian hiệu quả cần **chủ động đặt đầu vào tại ranh giới**, thay vì đợi đúng ngày thật. Với Java, `Clock.fixed` giúp kiểm soát “bây giờ”; các giá trị ngày giờ cố định giúp kiểm tra phép tính lịch và quy tắc múi giờ.

Bài này dùng ngày theo lịch ISO và ví dụ DST của `Europe/Paris` trong năm 2024. Mục tiêu là kiểm chứng quy tắc mà ứng dụng đã chọn, không mặc định mọi sản phẩm phải chọn cùng một cách xử lý ngày không tồn tại hay giờ bị lặp.

## 1. Viết quy tắc mong đợi trước khi viết ca kiểm tra

Một phép thử chỉ có giá trị khi biết kết quả nào là đúng.

Ví dụ các quy tắc minh họa trong bài:

| Tình huống | Quy tắc được chọn |
| --- | --- |
| Chọn ngày 31 ở tháng không có ngày 31 | Dùng ngày cuối hợp lệ của tháng đó |
| “Hôm nay” của dịch vụ | Tính theo vùng của Clock được truyền vào |
| Thời điểm hiện tại bằng hạn cuối | Đã hết hạn; cận cuối không bao gồm |
| Giờ địa phương rơi vào khoảng DST bị bỏ qua | Nếu yêu cầu giữ nguyên giờ/offset, từ chối tổ hợp không hợp lệ |
| Giờ lặp lại do DST | Offset được cung cấp phân biệt hai lần xuất hiện |

Một quy tắc khác có thể hợp lệ, chẳng hạn bỏ qua tháng không có ngày 31. Nếu nghiệp vụ chọn như vậy, ca kiểm tra phải phản ánh quy tắc ấy, không chép kết quả từ bài này.

Cũng cần phân biệt **hành vi của API** với **chính sách của ứng dụng**. `atZone` có cách mặc định xử lý giờ không tồn tại, nhưng ứng dụng có thể yêu cầu từ chối thay vì tự dịch giờ.

## 2. Ma trận ca biên nên có

| Nhóm | Các trường hợp cần chủ động chọn |
| --- | --- |
| Cuối tháng | Tháng 28, 29, 30, 31 ngày; chuyển tháng 12 sang năm sau nếu phép tính có bước ấy |
| Năm nhuận | Năm thường; năm chia hết 4; năm tròn thế kỷ không nhuận; năm tròn 400 năm có nhuận |
| Nửa đêm | Ngay trước, đúng và ngay sau nửa đêm của vùng nghiệp vụ |
| DST tiến giờ | Trước khoảng bị bỏ qua, trong khoảng không tồn tại, sau khoảng |
| DST lùi giờ | Hai offset hợp lệ của cùng giờ địa phương; so sánh cả `Instant` |
| Cận thời điểm | Trước hạn, đúng hạn, sau hạn |

Không nhất thiết ghép mọi ca với mọi ca thành một bộ tích Descartes lớn. Chọn các trường hợp có thể làm lộ sai giả định của logic đang kiểm tra.

Một ngày giữa tháng hoặc mốc giữa trưa có thể là ca đối chứng, nhưng không thay thế các ranh giới trên.

## 3. Kiểm soát “bây giờ” bằng Clock được truyền vào

Đoạn mã nghiệp vụ phụ thuộc trực tiếp vào `LocalDate.now()` sẽ lấy thời gian/vùng mặc định của môi trường. Thay vào đó, nhận một Clock và đọc:

```java
LocalDate today = LocalDate.now(clock);
```

Trong kiểm thử:

```java
Clock clock = Clock.fixed(
        Instant.parse("2024-06-30T17:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

Đây là các đoạn minh họa, cần import các lớp tương ứng trong `java.time`.

Mốc 17:00Z này là đúng 00:00 ngày 01/07 tại vùng Việt Nam dùng trong ví dụ. Đặt Clock ở UTC sẽ không kiểm tra cùng câu hỏi “hôm nay theo Việt Nam”.

Clock cố định luôn trả mốc đã chọn. Không cần `sleep`, đổi giờ máy hoặc chạy kiểm thử vào đúng ngày cuối tháng. [Tài liệu `Clock.fixed`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html#fixed(java.time.Instant,java.time.ZoneId))

## 4. Chương trình kiểm tra hoàn chỉnh, không cần thư viện ngoài

Lưu dưới tên `TimeBoundaryChecks.java`. Chương trình chạy với Java 17 trở lên. Nếu một điều kiện sai, nó ném `AssertionError`; các điều kiện không phụ thuộc tùy chọn bật/tắt từ khóa `assert`.

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Year;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.Objects;

public class TimeBoundaryChecks {
    private static int checks;

    private static void expect(
            String label, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void expectDateTimeFailure(
            String label, Runnable action) {
        try {
            action.run();
        } catch (DateTimeException ex) {
            checks++;
            return;
        }
        throw new AssertionError(label + ": expected DateTimeException");
    }

    // Quy tắc ứng dụng: ngày mong muốn 1..31;
    // nếu tháng ngắn hơn thì dùng ngày cuối tháng.
    static LocalDate scheduledDate(YearMonth month, int requestedDay) {
        if (requestedDay < 1 || requestedDay > 31) {
            throw new IllegalArgumentException("Ngay mong muon phai trong 1..31");
        }
        return month.atDay(Math.min(requestedDay, month.lengthOfMonth()));
    }

    static LocalDate businessToday(Clock clock) {
        return LocalDate.now(clock);
    }

    static boolean isExpired(Clock clock, Instant endExclusive) {
        return !clock.instant().isBefore(endExclusive);
    }

    public static void main(String[] args) {
        expect("normal February", LocalDate.of(2023, 2, 28),
                YearMonth.of(2023, 2).atEndOfMonth());
        expect("leap February", LocalDate.of(2024, 2, 29),
                YearMonth.of(2024, 2).atEndOfMonth());
        expect("April", LocalDate.of(2024, 4, 30),
                YearMonth.of(2024, 4).atEndOfMonth());
        expect("requested 31 in February", LocalDate.of(2024, 2, 29),
                scheduledDate(YearMonth.of(2024, 2), 31));
        expect("requested 31 in March", LocalDate.of(2024, 3, 31),
                scheduledDate(YearMonth.of(2024, 3), 31));
        System.out.println("monthChecks=PASS");

        expect("1900", false, Year.isLeap(1900));
        expect("2000", true, Year.isLeap(2000));
        expect("2100", false, Year.isLeap(2100));
        expect("leap day plus year", LocalDate.of(2025, 2, 28),
                LocalDate.of(2024, 2, 29).plusYears(1));
        System.out.println("leapYearChecks=PASS");

        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        Instant midnight = Instant.parse("2024-06-30T17:00:00Z");

        Clock before = Clock.fixed(midnight.minusNanos(1), vietnam);
        Clock at = Clock.fixed(midnight, vietnam);
        Clock after = Clock.fixed(midnight.plusNanos(1), vietnam);

        expect("before midnight", LocalDate.of(2024, 6, 30),
                businessToday(before));
        expect("at midnight", LocalDate.of(2024, 7, 1),
                businessToday(at));
        expect("after midnight", LocalDate.of(2024, 7, 1),
                businessToday(after));
        expect("same instant in UTC", LocalDate.of(2024, 6, 30),
                businessToday(at.withZone(ZoneOffset.UTC)));

        expect("before expiry", false, isExpired(before, midnight));
        expect("at expiry", true, isExpired(at, midnight));
        expect("after expiry", true, isExpired(after, midnight));
        System.out.println("midnightChecks=PASS");

        ZoneId paris = ZoneId.of("Europe/Paris");
        LocalDateTime gap = LocalDateTime.of(2024, 3, 31, 2, 30);

        expect("gap has no valid offset", 0,
                paris.getRules().getValidOffsets(gap).size());
        expect("default gap adjustment", LocalDateTime.of(2024, 3, 31, 3, 30),
                gap.atZone(paris).toLocalDateTime());
        expectDateTimeFailure("strict gap rejection",
                () -> ZonedDateTime.ofStrict(
                        gap, ZoneOffset.ofHours(1), paris));

        LocalDateTime overlap = LocalDateTime.of(2024, 10, 27, 2, 30);
        expect("overlap has two offsets", 2,
                paris.getRules().getValidOffsets(overlap).size());

        ZonedDateTime first = ZonedDateTime.ofStrict(
                overlap, ZoneOffset.ofHours(2), paris);
        ZonedDateTime second = ZonedDateTime.ofStrict(
                overlap, ZoneOffset.ofHours(1), paris);

        expect("first overlap instant", Instant.parse("2024-10-27T00:30:00Z"),
                first.toInstant());
        expect("second overlap instant", Instant.parse("2024-10-27T01:30:00Z"),
                second.toInstant());
        expect("overlap minutes apart", 60L,
                Duration.between(first.toInstant(), second.toInstant()).toMinutes());

        ZonedDateTime noonBefore =
                LocalDateTime.of(2024, 3, 30, 12, 0).atZone(paris);
        expect("one calendar day elapsed hours", 23L,
                Duration.between(
                        noonBefore.toInstant(),
                        noonBefore.plusDays(1).toInstant()).toHours());
        expect("24 hours gives local 13", 13,
                noonBefore.plus(Duration.ofHours(24)).getHour());

        System.out.println("dstChecks=PASS");
        System.out.println("totalChecks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 TimeBoundaryChecks.java
java TimeBoundaryChecks
```

Stdout khi toàn bộ kiểm tra đạt, với quy tắc Paris năm 2024 như trong ví dụ:

```text
monthChecks=PASS
leapYearChecks=PASS
midnightChecks=PASS
dstChecks=PASS
totalChecks=25
```

Trong dự án có JUnit, có thể chuyển các nhóm thành phương thức kiểm thử và dùng assertion tương ứng. Tên ca nên nêu quy tắc/ranh giới được kiểm tra, không chỉ đánh số.

## 5. Cuối tháng: kiểm tra chính sách, không chỉ gọi được API

Hàm `scheduledDate` giữ **ngày mong muốn** tách khỏi ngày kết quả. Với yêu cầu ngày 31:

```text
tháng 02/2024 → ngày thực hiện 29/02
tháng 03/2024 → ngày thực hiện 31/03
```

Nếu thay bằng cách lấy kết quả tháng 2 rồi cộng một tháng, ngày 29 có thể tiếp tục sang tháng 3, mất ý định ngày 31.

Một kiểm tra chỉ xác nhận “tháng 2 trả ra ngày hợp lệ” chưa phát hiện lỗi lịch lặp này. Cần thêm ca tháng kế tiếp khôi phục đúng ngày mong muốn.

`YearMonth.atEndOfMonth()` tính cuối tháng theo năm và tháng cụ thể. [Tài liệu `YearMonth`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/YearMonth.html#atEndOfMonth())

Đối với phép cộng tháng/năm của `LocalDate`, ngày có thể được điều chỉnh về ngày cuối hợp lệ của tháng đích. Ví dụ chương trình kiểm tra 29/02/2024 cộng một năm thành 28/02/2025. Hành vi API này chưa tự quyết định toàn bộ chính sách ngày kỷ niệm của ứng dụng. [Tài liệu phép cộng năm](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#plusYears(long))

Nếu nghiệp vụ muốn ngày 01/03 cho một trường hợp không có 29/02, phải viết quy tắc ấy riêng và kiểm chứng đúng kỳ vọng.

## 6. Năm nhuận: dùng các ca có thể phá công thức đơn giản

Các ca 1900, 2000 và 2100 có giá trị vì kiểm tra chỉ “chia hết cho 4” sẽ trả sai ở năm tròn thế kỷ không nhuận.

Không cần tự viết lại thuật toán năm nhuận nếu thư viện đã có. Trong logic ứng dụng, điều cần kiểm chứng là kết quả như hạn ngày, lịch lặp hoặc phạm vi báo cáo đã dùng đúng năm đích.

Ví dụ một bộ dữ liệu có thể gồm:

| Đầu vào | Kết quả lịch mong đợi |
| --- | --- |
| 28/02/2023 cộng một ngày | 01/03/2023 |
| 28/02/2024 cộng một ngày | 29/02/2024 |
| 29/02/2024 cộng một ngày | 01/03/2024 |
| Cuối tháng 02/1900 | 28/02/1900 |
| Cuối tháng 02/2000 | 29/02/2000 |

Những kết quả mong đợi được nêu rõ bằng dữ kiện lịch, thay vì trong kiểm thử lại tính expected bằng chính công thức đang được kiểm tra.

## 7. Nửa đêm: đặt mốc theo vùng nghiệp vụ

Chương trình đặt ba Clock quanh:

```text
2024-07-01 00:00 Asia/Ho_Chi_Minh
= 2024-06-30 17:00Z
```

Nếu hàm `businessToday` bỏ qua Clock được truyền vào và gọi ngày theo UTC, các ca tại/sau nửa đêm sẽ phát hiện sai khác.

Ba ca trước–đúng–sau cũng kiểm tra cận hết hạn:

```text
now < endExclusive  → chưa hết hạn
now = endExclusive  → đã hết hạn
now > endExclusive  → đã hết hạn
```

Khoảng nano trong ví dụ là độ gần điểm biên của dữ liệu kiểm thử, không phải cam kết đồng hồ hệ thống hoặc cơ sở dữ liệu có độ chính xác nano.

Nếu tầng lưu trữ chỉ giữ mili giây, cần có kiểm tra tích hợp cho việc làm tròn/cắt phần lẻ ở tầng đó. Đừng suy từ phép thử `Instant` trong bộ nhớ rằng tất cả tầng dữ liệu giữ nguyên độ chính xác.

Ngoài ra, nếu một thao tác tạo nhiều giá trị phải nhất quán, nên chụp một mốc rồi suy ra ngày/giờ từ cùng mốc ấy. Hai lần đọc nguồn thật độc lập có thể nằm ở hai phía nửa đêm.

## 8. DST tiến giờ: một giờ địa phương có thể không tồn tại

Tại Paris ngày 31/03/2024, `02:30` rơi vào khoảng giờ bị bỏ qua. `getValidOffsets` trả danh sách rỗng.

Chương trình kiểm tra đồng thời hai hành vi có chủ đích:

- `gap.atZone(paris)` áp dụng chính sách mặc định và điều chỉnh thành `03:30`.
- `ZonedDateTime.ofStrict` từ chối tổ hợp giờ địa phương/offset không hợp lệ.

Hai kết quả không đối lập về độ đúng; chúng là hai hợp đồng khác nhau. Ứng dụng hẹn giờ cần chọn có chấp nhận tự dịch giờ hay báo người dùng chọn lại.

Khi kiểm thử đầu vào hẹn giờ, đừng chỉ xác nhận lời gọi không ném lỗi. Nếu tự dịch giờ được phép, xác nhận cả giờ địa phương, offset và `Instant` sau dịch. Nếu không được phép, xác nhận đúng loại từ chối. [Tài liệu xử lý khoảng giờ của `ZonedDateTime`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html)

## 9. DST lùi giờ: một giờ địa phương có thể chỉ hai thời điểm

Tại Paris ngày 27/10/2024, `02:30` có hai offset hợp lệ:

```text
02:30 +02:00 → 00:30Z
02:30 +01:00 → 01:30Z
```

Nếu chỉ so sánh `LocalDateTime`, hai lần xuất hiện nhìn như bằng nhau. So sánh `Instant` cho thấy chúng cách nhau một giờ.

Một ca kiểm thử DST lùi giờ cần biết nguồn chọn lần nào. Có thể bắt người dùng cung cấp offset hoặc áp dụng chính sách lần sớm/lần muộn đã công khai. Không bỏ offset khỏi expected rồi coi cả hai kết quả như tương đương.

`ZoneRules.getValidOffsets(localDateTime)` giúp nhận diện ba trạng thái: không có offset, một offset hoặc hai offset. [Tài liệu `getValidOffsets`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html#getValidOffsets(java.time.LocalDateTime))

Giờ mùa hè không xuất hiện ở mọi vùng và độ chuyển không được mặc định luôn là một giờ trong mọi quy tắc lịch sử. Ca Paris một giờ là dữ liệu cụ thể, không phải thuật toán thay thế cơ sở dữ liệu múi giờ.

## 10. Một ngày lịch khác một thời lượng 24 giờ

Từ 12:00 ngày 30/03/2024 tại Paris:

- `plusDays(1)` tìm ngày lịch kế tiếp với giờ địa phương tương ứng; trong ví dụ chỉ trôi 23 giờ.
- `plus(Duration.ofHours(24))` thêm đúng thời lượng 24 giờ; kết quả giờ địa phương là 13:00 ngày sau.

Nếu lịch học yêu cầu “mỗi ngày lúc 12:00”, phép thử cần kiểm tra giờ địa phương qua chuyển DST. Nếu yêu cầu “sau 24 giờ”, cần kiểm tra thời lượng giữa hai `Instant`.

Không chỉ kiểm tra ngày đích vì cả hai có thể rơi vào cùng ngày nhưng khác giờ. Tương tự, ở chuyển DST lùi giờ, một ngày lịch có thể tương ứng 25 giờ trong ca chuyển một giờ.

Các phép thử nên làm rõ đại lượng mà nghiệp vụ bảo toàn: giờ trên đồng hồ, ngày lịch hay thời lượng.

## 11. Giữ bộ kiểm tra ổn định và có ích

- Truyền Clock hoặc mốc thời gian vào nơi cần “bây giờ”; tránh lời gọi mặc định ẩn trong logic.
- Dùng ngày giờ cố định và vùng rõ ràng.
- Không thay múi giờ toàn cục của JVM để kiểm thử một hàm nếu có thể truyền vùng/Clock trực tiếp.
- Không dùng chờ thật làm cách kiểm tra lịch hoặc hết hạn.
- Ghi phiên bản JDK/dữ liệu múi giờ khi điều tra một ca DST khác expected.
- Với quy tắc tương lai, hiểu rằng dữ liệu vùng có thể cập nhật; phân biệt thay đổi môi trường với lỗi thuật toán.
- Khi chuyển sang kiểm thử dự án, kiểm tra lớp nghiệp vụ thực sự, không chỉ lặp lại ví dụ API thư viện.

Có thể thêm các tính chất cho thuật toán phù hợp, chẳng hạn ngày chọn không vượt tháng đích hoặc phép lấy cuối tháng lặp lại vẫn cho cùng giá trị. Nhưng không áp đặt tính chất sai như “cộng một tháng rồi trừ một tháng luôn trở về ngày ban đầu”; điều chỉnh cuối tháng có thể làm mất ngày gốc.

## 12. Tự thực hành

1. Vì sao chỉ kiểm tra ngày 15 hàng tháng chưa đủ cho lịch ngày 31?
2. Tại sao một Clock cố định có mốc UTC đúng nhưng vùng sai vẫn có thể làm kiểm thử “hôm nay” sai ý nghĩa?
3. Cần kiểm tra gì ngoài `LocalDateTime` khi giờ xuất hiện hai lần do DST?
4. `plusDays(1)` có luôn bằng thêm 24 giờ thực tế không?
5. Nếu đúng thời điểm hết hạn đã là quá hạn, phép so sánh `isAfter` có đủ không?

Gợi ý đáp án:

1. Vì không chạm trường hợp tháng thiếu ngày và mất ngày mong muốn qua kỳ tiếp theo.
2. Ngày địa phương phụ thuộc cả mốc và vùng.
3. Kiểm tra offset và `Instant` của lần xuất hiện được chọn.
4. Không; chuyển offset có thể làm khác thời lượng.
5. Không; cần tính cả trường hợp bằng hạn, chẳng hạn `!now.isBefore(endExclusive)`.

Hãy đưa thời gian đến ranh giới bằng dữ liệu kiểm thử, xác định rõ điều được bảo toàn và kiểm tra cả giá trị ngày giờ lẫn ý nghĩa nghiệp vụ của kết quả.
