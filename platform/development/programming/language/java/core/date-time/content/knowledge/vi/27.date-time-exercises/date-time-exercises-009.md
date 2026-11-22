# Lập bảng ca biên cho múi giờ, năm nhuận, độ chính xác và đầu vào sai

## 1. Ca biên phải kiểm tra một hợp đồng cụ thể

Một chương trình chạy đúng với `2025-06-15T10:00` chưa chứng minh nó xử lý đúng cuối tháng, giờ đổi múi, giá trị mất phần lẻ hoặc chuỗi sai. Ca biên là những đầu vào ở nơi quy tắc đổi nhánh hoặc chạm giới hạn.

Trước khi lập bảng, ghi rõ hệ thống cần bảo toàn điều gì: cùng thời điểm hay cùng giờ địa phương, điểm cuối có được tính hay không, parser có tự sửa ngày không, và độ chính xác được lưu đến đơn vị nào. Nếu chưa chốt hợp đồng, bảng chỉ có dữ liệu mà chưa có kết quả mong đợi.

Một hàng kiểm tra nên có **mã ca, điều kiện/quy tắc, đầu vào, kết quả mong đợi, điều cần chứng minh**. Kết quả mong đợi phải được xác định độc lập với hàm đang kiểm tra; không lấy đầu ra hiện tại làm chuẩn chỉ vì chương trình không báo lỗi.

## 2. Chốt phạm vi mẫu

Bài này dùng lịch ISO, JDK 17 trở lên và các hợp đồng minh họa:

- Phân giải giờ địa phương bằng `ZoneId`; giờ thiếu/trùng cần được nhận diện trước khi chọn chính sách.
- Parse ngày `dd/MM/uuuu` nghiêm ngặt.
- Điểm cuối hết hạn loại trừ: đúng mốc cuối đã hết hạn.
- Giữ nano giây trong bộ nhớ; khi giảm độ chính xác phải biết quy tắc rõ ràng.

Đó là phạm vi để tạo ca kiểm tra có thể đối chiếu; sản phẩm có chính sách khác phải thay kết quả mong đợi tương ứng.

## 3. Bảng ca múi giờ

| Mã | Đầu vào và phép kiểm tra | Kết quả mong đợi | Phát hiện điều gì? |
| --- | --- | --- | --- |
| Z01 | Berlin `2025-02-10T10:00`, đếm độ lệch hợp lệ | 1 | Đường đi bình thường |
| Z02 | Berlin `2025-03-30T02:30` | 0 độ lệch | Giờ không tồn tại khi nhảy giờ |
| Z03 | Berlin `2025-10-26T02:30` | 2 độ lệch | Giờ xuất hiện hai lần |
| Z04 | Hai lần của Z03 | `00:30Z` và `01:30Z` | Cùng đồng hồ địa phương nhưng khác thời điểm |
| Z05 | `2025-12-31T18:00Z` hiển thị tại Việt Nam | `2026-01-01T01:00` | Đổi vùng làm đổi cả ngày/năm |
| Z06 | Đổi vùng bằng `withZoneSameInstant` | `toInstant()` không đổi | Không dời sự kiện khi chỉ đổi cách nhìn |
| Z07 | Ngày 30/3/2025 tại Berlin, đầu ngày đến đầu ngày sau | 23 giờ thực trôi | Ngày địa phương không luôn bằng 24 giờ |
| Z08 | Tên vùng không tồn tại | Từ chối bằng lỗi vùng | Không tự fallback sang vùng khác |

Dùng `getValidOffsets(local)` để nhận diện trạng thái, không đoán bằng tháng trong năm. Kết quả vùng phải gắn với dữ liệu quy tắc được dùng trong môi trường chạy. [ZoneRules](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html)

Nếu ứng dụng phải hoạt động ở vùng có độ lệch không tròn giờ hoặc chuyển đổi không dài một giờ, thêm đúng vùng/ngày cần hỗ trợ. Đừng chỉ lấy Berlin làm bằng chứng cho mọi quy tắc trên thế giới.

## 4. Bảng ca lịch và năm nhuận

| Mã | Đầu vào | Kết quả mong đợi | Phát hiện điều gì? |
| --- | --- | --- | --- |
| L01 | `LocalDate.of(2024, 2, 29)` | Hợp lệ | Năm nhuận thông thường |
| L02 | `LocalDate.of(2023, 2, 29)` | `DateTimeException` | Năm thường |
| L03 | `Year.isLeap(2000)` | `true` | Ngoại lệ chia hết cho 400 |
| L04 | `Year.isLeap(2100)` | `false` | Không chỉ kiểm tra chia hết cho 4 |
| L05 | `MonthDay.of(2,29).atYear(2023)` | `2023-02-28` | Hành vi điều chỉnh của API |
| L06 | `2024-01-31.plusMonths(1)` | `2024-02-29` | Ngày cuối tháng đích |
| L07 | Kết quả L06 trừ một tháng | `2024-01-29` | Cộng/trừ tháng không luôn đảo ngược |
| L08 | `LocalDate.MAX.plusDays(1)` | Lỗi vượt miền | Giới hạn biểu diễn |

L05 không chứng minh chính sách sinh nhật 29/2 của sản phẩm là đúng. Nếu yêu cầu bỏ qua năm thường hoặc chuyển sang 1/3, bảng cần ca kiểm tra cho chính sách đó. [Year](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Year.html)

## 5. Bảng ca độ chính xác và ranh giới

| Mã | Đầu vào/phép toán | Kết quả mong đợi |
| --- | --- | --- |
| P01 | `2025-01-01T00:00:00.123456789Z` giữ nguyên trong Instant | 123456789 nano giây |
| P02 | Giá trị P01 `truncatedTo(MILLIS)` | Phần lẻ `.123Z` |
| P03 | Qua `java.util.Date.from(...).toInstant()` | Mất phần nhỏ hơn mili giây |
| P04 | Format rồi parse bằng hợp đồng ISO_INSTANT | Cùng Instant nếu không giảm độ chính xác |
| P05 | `now = end - 1ns`, cuối loại trừ | Còn hiệu lực |
| P06 | `now = end`, cuối loại trừ | Hết hiệu lực |
| P07 | `now = end + 1ns`, cuối loại trừ | Hết hiệu lực |
| P08 | Ghi/đọc timestamp qua DB thật | Khớp quy tắc độ chính xác của schema/driver đã công bố |

`truncatedTo` là cắt xuống theo đơn vị được hỗ trợ, không phải làm tròn đến giá trị gần nhất. P02 là mô hình giảm độ chính xác chủ động; không được giả định mọi DB áp dụng cùng cách cắt. [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html#truncatedTo(java.time.temporal.TemporalUnit))

Với DB/API, ghi rõ đơn vị và quy tắc làm tròn, rồi kiểm tra sau vòng trao đổi thật. Một ca trong bộ nhớ không chứng minh driver giữ phần lẻ hay độ lệch như mong muốn.

## 6. Bảng ca đầu vào sai

| Mã | Đầu vào cho hợp đồng ngày | Kết quả mong đợi |
| --- | --- | --- |
| I01 | `29/02/2024` | Thành công thành `2024-02-29` |
| I02 | `29/02/2023` | Lỗi ngày không tồn tại |
| I03 | `31/04/2024` | Lỗi ngày không tồn tại, không sửa thành 30/4 |
| I04 | `2024-02-29` | Lỗi định dạng |
| I05 | `29/02/2024xyz` | Lỗi ký tự dư |
| I06 | `null` hoặc trống | Lỗi thiếu dữ liệu do lớp đầu vào định nghĩa |
| I07 | `1/2/2024` | Từ chối nếu hợp đồng buộc hai chữ số |
| I08 | `01/01/0000` | Kết quả tùy miền năm ứng dụng; lịch ISO của LocalDate cho phép năm 0 |

Cần tách hình thức, hợp lệ lịch và quy tắc nghiệp vụ. `STRICT` kiểm tra tính hợp lệ khi phân giải các trường; không tự biết ngày sinh phải không ở tương lai hoặc ứng dụng có cấm năm 0 không. [ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html)

## 7. Chương trình chuyển một phần bảng thành kiểm tra tự động

Chương trình dưới đây dùng các điều kiện được viết rõ, không cần bật tùy chọn `-ea`. Nó cố ý chỉ bắt đúng lớp lỗi được yêu cầu; nếu không có lỗi hoặc có loại lỗi khác thì kiểm tra thất bại.

Lưu thành `DateTimeBoundaryChecks.java`:

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.MonthDay;
import java.time.Year;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public class DateTimeBoundaryChecks {
    private static final DateTimeFormatter INPUT =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    static void check(String id, boolean condition) {
        if (!condition) {
            throw new AssertionError("Failed: " + id);
        }
        System.out.println(id + " PASS");
    }

    static void expect(String id, Class<? extends Throwable> type, Runnable action) {
        try {
            action.run();
        } catch (Throwable error) {
            if (!type.isInstance(error)) {
                throw new AssertionError("Wrong exception: " + id, error);
            }
            System.out.println(id + " PASS");
            return;
        }
        throw new AssertionError("Expected exception: " + id);
    }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        check("Z01", berlin.getRules().getValidOffsets(
                LocalDateTime.of(2025, 2, 10, 10, 0)).size() == 1);
        check("Z02", berlin.getRules().getValidOffsets(
                LocalDateTime.of(2025, 3, 30, 2, 30)).isEmpty());
        LocalDateTime overlap = LocalDateTime.of(2025, 10, 26, 2, 30);
        var offsets = berlin.getRules().getValidOffsets(overlap);
        check("Z03", offsets.size() == 2);
        Instant first = ZonedDateTime.ofStrict(overlap, offsets.get(0), berlin).toInstant();
        Instant second = ZonedDateTime.ofStrict(overlap, offsets.get(1), berlin).toInstant();
        check("Z04", first.equals(Instant.parse("2025-10-26T00:30:00Z"))
                && second.equals(Instant.parse("2025-10-26T01:30:00Z")));

        check("L01", LocalDate.of(2024, 2, 29).getDayOfMonth() == 29);
        expect("L02", DateTimeException.class, () -> LocalDate.of(2023, 2, 29));
        check("L03", Year.isLeap(2000));
        check("L04", !Year.isLeap(2100));
        check("L05", MonthDay.of(2, 29).atYear(2023)
                .equals(LocalDate.of(2023, 2, 28)));
        LocalDate monthEnd = LocalDate.of(2024, 1, 31).plusMonths(1);
        check("L06", monthEnd.equals(LocalDate.of(2024, 2, 29)));
        check("L07", monthEnd.minusMonths(1).equals(LocalDate.of(2024, 1, 29)));

        Instant precise = Instant.parse("2025-01-01T00:00:00.123456789Z");
        Instant millis = Instant.parse("2025-01-01T00:00:00.123Z");
        check("P01", precise.getNano() == 123456789);
        check("P02", precise.truncatedTo(ChronoUnit.MILLIS).equals(millis));
        check("P03", Date.from(precise).toInstant().equals(millis));
        Instant end = Instant.parse("2025-01-01T01:00:00Z");
        List<Boolean> expired = List.of(end.minusNanos(1), end, end.plusNanos(1))
                .stream().map(now -> !now.isBefore(end)).toList();
        check("P05-P07", expired.equals(List.of(false, true, true)));

        check("I01", LocalDate.parse("29/02/2024", INPUT)
                .equals(LocalDate.of(2024, 2, 29)));
        expect("I02", DateTimeParseException.class,
                () -> LocalDate.parse("29/02/2023", INPUT));
        expect("I03", DateTimeParseException.class,
                () -> LocalDate.parse("31/04/2024", INPUT));
        expect("I05", DateTimeParseException.class,
                () -> LocalDate.parse("29/02/2024xyz", INPUT));

        LocalDate day = LocalDate.of(2025, 3, 30);
        Duration elapsed = Duration.between(day.atStartOfDay(berlin).toInstant(),
                day.plusDays(1).atStartOfDay(berlin).toInstant());
        check("Z07", elapsed.equals(Duration.ofHours(23)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 DateTimeBoundaryChecks.java
java DateTimeBoundaryChecks
```

Stdout chính xác với dữ liệu múi giờ IANA theo các quy tắc Berlin năm 2025:

```text
Z01 PASS
Z02 PASS
Z03 PASS
Z04 PASS
L01 PASS
L02 PASS
L03 PASS
L04 PASS
L05 PASS
L06 PASS
L07 PASS
P01 PASS
P02 PASS
P03 PASS
P05-P07 PASS
I01 PASS
I02 PASS
I03 PASS
I05 PASS
Z07 PASS
```

Những hàng chưa tự động hóa trong chương trình vẫn cần kiểm tra ở lớp phù hợp. Đặc biệt P08 cần DB/driver/schema thật; I06 và giới hạn năm cần hàm nhập liệu của ứng dụng.

## 8. Thêm các quan hệ bất biến để tăng sức kiểm tra

Ngoài kết quả cụ thể, có thể kiểm tra các quan hệ:

- Đổi vùng để xem cùng sự kiện phải giữ `toInstant()`.
- Format/parse theo hợp đồng không giảm độ chính xác phải giữ giá trị.
- Ghép các đoạn nửa mở liền nhau không làm một điểm biên thuộc hai đoạn.
- Tính thời lượng thực trôi từ hai Instant không phụ thuộc vùng chỉ dùng để hiển thị.

Không áp dụng một quan hệ không có trong hợp đồng. Ví dụ “cộng một tháng rồi trừ một tháng phải về ngày cũ” là sai ở cuối tháng; L07 tồn tại để ngăn chính giả định đó.

## 9. Quản lý môi trường và đọc lỗi kiểm tra

Ghi JDK, dữ liệu múi giờ, locale tường minh và phiên bản DB/driver khi các yếu tố đó ảnh hưởng kết quả. Không để bài kiểm tra dùng ngày hiện tại hoặc vùng mặc định nếu không chủ động kiểm tra sự phụ thuộc ấy.

Khi kiểm tra lỗi, xác nhận đúng loại lỗi hoặc mã lỗi của ứng dụng; không chỉ chấp nhận “bất kỳ ngoại lệ nào”. Khi kiểm tra thành công, xác nhận giá trị và ý nghĩa cần giữ; “không ném lỗi” chưa đủ.

Không nới lỏng kết quả mong đợi chỉ để mọi môi trường đều xanh. Trước hết xác định khác biệt đến từ chính sách, dữ liệu quy tắc, độ chính xác hoặc một lỗi thật.

## 10. Thực hành mở rộng

1. Chuyển bảng thành các ca JUnit của một hàm nghiệp vụ cụ thể.
2. Thêm cặp trước/đúng/sau ranh giới hết hạn với độ chính xác thật của hệ thống.
3. Thêm kiểm tra vùng không tồn tại và thông báo lỗi đầu vào có thể hiểu được.
4. Thêm một vòng ghi/đọc DB thật, kiểm tra Instant, phần lẻ và SQL NULL theo schema đã chọn.

Bảng hoàn chỉnh phải cho phép người khác hiểu lý do của từng ca và tự quyết định đạt/trượt từ hợp đồng, không phải từ suy đoán sau khi nhìn đầu ra.