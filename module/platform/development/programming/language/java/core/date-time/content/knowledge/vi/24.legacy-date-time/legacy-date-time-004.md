# Chỉ số tháng của `Calendar` và lỗi lệch tháng thường gặp

## 1. Tháng 1 được biểu diễn bằng số 0

Trong `GregorianCalendar`, giá trị của trường `Calendar.MONTH` bắt đầu từ 0: tháng 1 là 0, tháng 2 là 1, ..., tháng 12 là 11. Đây là quy ước dễ gây lỗi khi dữ liệu đầu vào hoặc API hiện đại dùng số tháng 1–12.

Ví dụ, lệnh `calendar.set(2025, 1, 15)` tạo ngày 15 tháng **2**, không phải ngày 15 tháng 1. Số 1 là một chỉ số tháng hợp lệ, nên ngay cả chế độ chặt chẽ cũng không biết người viết thật ra muốn tháng 1.

[Java SE 21 — Calendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html) mô tả trường tháng và các hằng như `JANUARY`. Với mã phải dùng `Calendar`, ưu tiên những hằng có tên hoặc chuyển quy ước thật rõ ở ranh giới dữ liệu.

| Tháng theo cách ghi thông thường | Giá trị `Calendar.MONTH` trong Gregorian | Hằng có tên |
| --- | ---: | --- |
| 1 | 0 | `Calendar.JANUARY` |
| 2 | 1 | `Calendar.FEBRUARY` |
| 6 | 5 | `Calendar.JUNE` |
| 12 | 11 | `Calendar.DECEMBER` |

Bài dùng `GregorianCalendar` tường minh. `Calendar` là lớp trừu tượng hỗ trợ các hệ lịch; không suy ra rằng mọi hệ lịch tùy biến đều chỉ có 12 tháng. Hằng `UNDECIMBER` tồn tại để mô tả tháng thứ 13 trong hệ lịch phù hợp, nhưng không tạo thêm một tháng hợp lệ cho năm Gregorian thông thường.

## 2. Phân biệt tên trường với giá trị của trường

Hai loại hằng cùng xuất hiện trong `Calendar` nhưng có vai trò khác nhau:

| Hằng | Vai trò | Ví dụ sử dụng |
| --- | --- | --- |
| `Calendar.MONTH` | Chọn trường tháng cần đọc/đặt/cộng | `get(Calendar.MONTH)` |
| `Calendar.JUNE` | Giá trị tháng 6 trong quy ước Calendar | `set(Calendar.MONTH, Calendar.JUNE)` |

Với overload `set(year, month, day)`, tham số thứ hai là **giá trị tháng**, không phải mã trường. Vì vậy, viết `set(2025, Calendar.MONTH, 10)` là nhầm vai trò hằng, không phải cách chọn “đặt tháng” cho overload này.

Hai cách đúng thường gặp:

```java
// Minh họa trong một phương thức; cal là Calendar đã được chuẩn bị.
cal.set(2025, Calendar.JUNE, 10);
cal.set(Calendar.MONTH, Calendar.JUNE);
```

Lệnh đầu đặt bộ năm/tháng/ngày. Lệnh sau chỉ đặt trường tháng trên đối tượng hiện có, nên các trường còn lại vẫn cần được xem xét. `Calendar` có thể thay đổi trạng thái; đừng xem các lời gọi `set()` là tạo giá trị bất biến mới như `LocalDate`.

## 3. Chuyển giữa quy ước bên ngoài và Calendar đúng một lần

Nếu biểu mẫu hoặc JSON quy định tháng 1–12, chuyển vào GregorianCalendar bằng `month - 1`. Khi xuất một giá trị tháng thô từ GregorianCalendar ra giao diện dùng 1–12, chuyển bằng `get(MONTH) + 1`.

```text
Dữ liệu hợp đồng 1..12  ── trừ 1 ──>  Calendar 0..11
Calendar 0..11         ── cộng 1 ──> Dữ liệu hợp đồng 1..12
```

Điều kiện là bạn đã biết quy ước của nguồn. Không cộng/trừ ở nhiều tầng “để chắc chắn”, vì có thể chuyển hai lần. Một biến như `calendarMonthIndex` và một biến như `monthNumber` nên có ý nghĩa riêng rõ ràng.

Không trừ 1 từ hằng `Calendar.JUNE`: nó đã là giá trị đúng cho Calendar. Ngược lại, `Month.JUNE.getValue()` thuộc quy ước 1–12 của API hiện đại, nên không đưa nguyên số ấy vào tham số tháng của `Calendar.set(year, month, day)`.

Với đầu vào tháng theo hợp đồng 1–12, kiểm tra phạm vi tại ranh giới nhập liệu trước khi chuyển. Điều đó giúp từ chối tháng 0 hoặc 13 theo ý nghĩa đầu vào, thay vì để chế độ linh hoạt giải thích thành ngày của năm khác.

## 4. Chương trình kiểm chứng đầy đủ

Lưu mã sau vào `CalendarMonthIndexDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài:

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;

public class CalendarMonthIndexDemo {
    private static GregorianCalendar calendar(boolean lenient) {
        GregorianCalendar value = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.ROOT);
        value.clear();
        value.setLenient(lenient);
        return value;
    }

    private static String isoDate(Calendar value) {
        return value.toInstant().atZone(ZoneOffset.UTC)
                .toLocalDate().toString();
    }

    public static void main(String[] args) {
        GregorianCalendar correct = calendar(false);
        correct.set(2025, Calendar.JANUARY, 15);
        System.out.println("January raw = " + correct.get(Calendar.MONTH));
        System.out.println("January display = "
                + (correct.get(Calendar.MONTH) + 1));
        System.out.println("correct date = " + isoDate(correct));

        GregorianCalendar wrong = calendar(false);
        wrong.set(2025, 1, 15);
        System.out.println("set month 1 = " + isoDate(wrong));

        int userMonth = 6;
        GregorianCalendar fromInput = calendar(false);
        fromInput.set(2025, userMonth - 1, 10);
        System.out.println("human month 6 = " + isoDate(fromInput));
        System.out.println("Calendar.JUNE = " + Calendar.JUNE);
        System.out.println("Month.JUNE value = " + Month.JUNE.getValue());

        GregorianCalendar normalized = calendar(true);
        normalized.set(2025, 12, 15);
        System.out.println("lenient month 12 = " + isoDate(normalized));

        GregorianCalendar rejected = calendar(false);
        rejected.set(2025, 12, 15);
        System.out.println("strict set returned");
        try {
            rejected.getTimeInMillis();
        } catch (IllegalArgumentException ex) {
            System.out.println("strict read = IllegalArgumentException");
        }

        GregorianCalendar leap = calendar(false);
        leap.set(2024, Calendar.FEBRUARY, 29);
        System.out.println("leap date = " + isoDate(leap));

        LocalDate modern = LocalDate.of(2025, 6, 10);
        GregorianCalendar converted = GregorianCalendar.from(
                modern.atStartOfDay(ZoneOffset.UTC));
        System.out.println("conversion raw month = "
                + converted.get(Calendar.MONTH));
        System.out.println("modern month = " + modern.getMonthValue());
        System.out.println("round trip = "
                + converted.toZonedDateTime().toLocalDate());

        DateTimeFormatter output = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT);
        System.out.println("formatted modern = " + modern.format(output));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CalendarMonthIndexDemo.java
java CalendarMonthIndexDemo
```

Kết quả:

```text
January raw = 0
January display = 1
correct date = 2025-01-15
set month 1 = 2025-02-15
human month 6 = 2025-06-10
Calendar.JUNE = 5
Month.JUNE value = 6
lenient month 12 = 2026-01-15
strict set returned
strict read = IllegalArgumentException
leap date = 2024-02-29
conversion raw month = 5
modern month = 6
round trip = 2025-06-10
formatted modern = 2025-06-10
```

## 5. Vì sao ví dụ gọi `clear()` và chọn UTC?

Một Calendar mới thường có các trường thời gian đã được khởi tạo. Nếu chỉ đặt năm/tháng/ngày trên đối tượng ấy, giờ/phút/giây hoặc mili giây cũ có thể vẫn còn. `clear()` trong hàm tạo của bài xóa các trường đã được thiết lập trước khi dựng mốc cần kiểm chứng, giúp ví dụ không giữ lại thành phần từ lúc chạy chương trình.

UTC được chọn tường minh cho `GregorianCalendar` và cho bước chuyển thành ngày hiển thị. Như vậy stdout không phụ thuộc vùng mặc định của máy. Hàm `isoDate()` chỉ dành cho các giá trị UTC đã chuẩn bị trong bài; với dữ liệu thật ở vùng khác, phải chọn vùng hiển thị theo hợp đồng thay vì mặc nhiên đổi sang UTC rồi mong ngày lịch luôn giữ nguyên.

Các lựa chọn này cô lập lỗi chỉ số tháng khỏi lỗi do dữ liệu thừa hoặc vùng thời gian. Khi điều tra ngày bị lệch, cần kiểm tra chúng riêng: cộng/trừ chỉ số tháng không sửa được một ngày lệch vì chuyển vùng.

## 6. Chế độ linh hoạt có thể che lỗi, chế độ chặt chẽ vẫn có giới hạn

Trong `GregorianCalendar` linh hoạt, giá trị tháng 12 được hiểu như đi qua 12 tháng từ tháng 0 của năm, nên `set(2025, 12, 15)` trở thành `2026-01-15`. Nếu người viết nghĩ số 12 là tháng 12, lỗi không chỉ lệch một tháng mà còn làm đổi năm.

`setLenient(false)` yêu cầu các trường hợp lệ khi Calendar tính thời điểm hoặc tính lại các trường. Chương trình cho thấy `set()` có thể trả về trước, rồi `getTimeInMillis()` mới ném `IllegalArgumentException`. Vì vậy không kết luận dữ liệu đã được xác nhận chỉ vì lời gọi đặt trường chưa ném lỗi.

Nhưng số 1 vẫn là tháng 2 hợp lệ. Chế độ chặt chẽ không thể biết bạn muốn tháng 1, nên lỗi lệch quy ước này không bị bắt. Cần kiểm tra giá trị ngày kết quả với kỳ vọng nghiệp vụ, không chỉ kiểm tra có ngoại lệ hay không.

Tương tự, chỉ trừ 1 để đúng tháng chưa bảo đảm bộ ngày tồn tại: tháng 2 năm 2025 không có ngày 29. Trường hợp `2024-02-29` trong bài hợp lệ vì là năm nhuận; kiểm tra tính hợp lệ phải xét cả năm, tháng và ngày.

## 7. Sang `java.time`: số tháng là 1–12

[Java SE 21 — Month](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Month.html) dùng giá trị 1 cho tháng 1 tới 12 cho tháng 12 và khuyến nghị dùng `getValue()` thay cho `ordinal()` để lấy số tháng.

Các cách tạo hiện đại dễ đọc hơn:

```java
LocalDate numeric = LocalDate.of(2025, 6, 10);
LocalDate named = LocalDate.of(2025, Month.JUNE, 10);
```

Cả hai đều tạo ngày `2025-06-10`. Không áp dụng thói quen trừ 1 của Calendar vào tham số tháng của `LocalDate.of()`: số 5 ở đó là tháng 5.

Khi buộc phải nối với mã cũ, có thể chuyển bằng API thay vì sao chép từng trường. Trong chương trình, `GregorianCalendar.from(modern.atStartOfDay(UTC))` tạo đối tượng Calendar tương ứng, rồi `toZonedDateTime().toLocalDate()` lấy lại ngày hiện đại.

`LocalDate` không chứa giờ hoặc vùng, nên việc gọi `atStartOfDay(UTC)` là quyết định chọn mốc để đưa sang kiểu Calendar có thời điểm/vùng. Nếu ứng dụng cần vùng khác hoặc giờ khác, phải chọn theo yêu cầu đó. Không xem lựa chọn UTC trong ví dụ là một giá trị mặc định bắt buộc cho mọi chuyển đổi.

Nếu chỉ cần xuất chuỗi ngày, dùng formatter với kiểu hiện đại hoặc formatter phù hợp cho dữ liệu cũ, thay vì tự ghép `year + "-" + rawMonth + "-" + day`. Bộ định dạng hiểu quy ước trường; chuỗi tự ghép có thể vừa sai tháng vừa thiếu số 0 ở đầu.

## 8. Các lỗi thường gặp cần tách riêng

| Đoạn mã/ý tưởng | Lỗi hoặc ý nghĩa |
| --- | --- |
| `set(2025, 6, 10)` với ý định tháng 6 | Calendar hiểu tháng 7 |
| `get(Calendar.MONTH)` rồi hiển thị trực tiếp | Giao diện 1–12 có thể hiển thị 0–11 |
| `set(2025, Calendar.JUNE - 1, 10)` | Hằng Calendar đã đúng quy ước, bị trừ thêm một lần |
| `LocalDate.of(2025, Calendar.JUNE, 10)` | Số 5 của Calendar bị hiểu thành tháng 5 trong LocalDate |
| `add(Calendar.MONTH, 1)` | Cộng một tháng, không cần trừ 1 ở số lượng cộng |

Dòng `add()` cuối giúp phân biệt **giá trị vị trí tháng** với **số lượng tháng cần cộng**. Lỗi chỉ số bắt đầu từ 0 không có nghĩa mọi tham số liên quan tháng đều phải giảm một đơn vị.

Không dùng `Month.ordinal()` để nối API chỉ vì nó tình cờ bắt đầu từ 0. Dùng `getValue()` theo hợp đồng của `Month`, rồi chuyển sang chỉ số Calendar ở đúng ranh giới nếu thật sự cần. Cách đó thể hiện ý nghĩa tốt hơn và tránh trộn vị trí enum với giá trị nghiệp vụ.

Bài tập: tạo ngày `2025-12-31` bằng `GregorianCalendar` chặt chẽ với `Calendar.DECEMBER`, rồi chuyển về `LocalDate`. Kiểm tra tháng thô là 11 nhưng chuỗi ngày phải là `2025-12-31`. Tiếp theo, thay hằng tháng bằng số 12 để thấy dữ liệu bị từ chối khi tính thời điểm; bật linh hoạt sẽ chuyển sang tháng 1 năm 2026, không giữ tháng 12 như ý định ban đầu.
