# Nhận diện `JapaneseDate`, `ThaiBuddhistDate`, `HijrahDate` và `MinguoDate`

## 1. Một ngày, nhiều hệ lịch

`LocalDate` biểu diễn ngày theo lịch ISO. Khi nguồn dữ liệu dùng niên hiệu Nhật, năm Phật lịch Thái, lịch Hijrah hoặc năm Dân Quốc, chỉ đổi ngôn ngữ hiển thị chưa đủ: ý nghĩa các trường năm, tháng, ngày có thể khác.

Bốn lớp trong `java.time.chrono` dùng để biểu diễn ngày theo những hệ lịch đó. Chúng đều là kiểu ngày không chứa giờ hoặc vùng thời gian, bất biến và có thể truy vấn qua `ChronoLocalDate`.

Cần tách ba lựa chọn:

- **Hệ lịch (`Chronology`):** các quy tắc gán năm/tháng/ngày cho một ngày.
- **Ngôn ngữ/vùng hiển thị (`Locale`):** cách viết tên và văn bản.
- **Vùng thời gian (`ZoneId`):** ngữ cảnh chuyển một thời điểm thành ngày–giờ địa phương.

Một người dùng tiếng Nhật không bắt buộc sử dụng niên hiệu Nhật; một `JapaneseDate` cũng không chứa múi giờ Tokyo. Bài này tập trung nhận diện và chuyển biểu diễn của ngày giữa các hệ lịch, không biến chúng thành thời điểm có giờ.

## 2. Nhìn nhanh bốn kiểu

| Kiểu | Hệ lịch và điểm nhận diện | Điều không nên nhầm |
| --- | --- | --- |
| `JapaneseDate` | Lịch Nhật theo niên hiệu; có kỷ nguyên như Heisei, Reiwa và năm trong kỷ nguyên | Không phải lịch âm Nhật cổ |
| `ThaiBuddhistDate` | Phật lịch Thái; năm liên tục lệch +543 so với năm ISO, tháng/ngày tương ứng | Không phải một lịch âm Phật giáo chung cho mọi quốc gia |
| `HijrahDate` | Lịch Hijrah theo một biến thể; tháng âm lịch có 29 hoặc 30 ngày | Không đổi được bằng một hằng số cộng/trừ năm ISO |
| `MinguoDate` | Lịch Dân Quốc; năm 1 tương ứng năm ISO 1912, tháng/ngày tương ứng | Không phải lịch âm dương Trung Hoa |

## 3. `JapaneseDate`: phải biết năm nào đang được đọc

Theo [Java SE 21 — JapaneseDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/JapaneseDate.html), các trường tháng/ngày theo lịch ISO, nhưng cách đánh số năm theo niên hiệu khác. Lớp hỗ trợ ngày từ `1873-01-01`, không mô hình hóa toàn bộ lịch Nhật cổ trước khi áp dụng lịch Gregorian.

Với ngày ISO `2019-05-01`:

- `getEra()` cho niên hiệu Reiwa.
- `ChronoField.YEAR` cho năm liên tục 2019.
- `ChronoField.YEAR_OF_ERA` cho năm 1 trong niên hiệu ấy.

Do đó, `YEAR` và `YEAR_OF_ERA` không thay thế cho nhau. Nếu chỉ lưu “năm 1” mà không lưu niên hiệu, không thể biết ngày nguồn muốn nói tới niên hiệu nào.

Có thể tạo bằng năm liên tục `JapaneseDate.of(2019, 5, 1)` hoặc bằng niên hiệu `JapaneseDate.of(JapaneseEra.REIWA, 1, 5, 1)`. Nhưng `Reiwa 1-01-01` không hợp lệ: niên hiệu này bắt đầu vào `2019-05-01`, nên không thể dùng cả năm lịch 2019 làm năm đầu của niên hiệu mà bỏ qua ngày chuyển tiếp.

Không đặt quy tắc rằng mọi năm trong một niên hiệu luôn bắt đầu từ ngày 1 tháng 1. Khi kiểm tra ngày gần chuyển niên hiệu, phải để API xác nhận tổ hợp niên hiệu/năm/tháng/ngày.

## 4. `ThaiBuddhistDate` và `MinguoDate`: giống tháng/ngày, khác hệ năm

[Java SE 21 — ThaiBuddhistChronology](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/ThaiBuddhistChronology.html) quy định năm liên tục bằng năm ISO cộng 543, còn tháng/ngày và quy luật năm nhuận tương ứng với ISO. Vì vậy, ngày ISO `2019-05-01` được biểu diễn bằng năm Phật lịch 2562, tháng 5, ngày 1.

Các con số khi gọi `ThaiBuddhistDate.of(2562, 5, 1)` thuộc chính hệ lịch Thái. Nếu viết `ThaiBuddhistDate.of(2019, 5, 1)` thì 2019 sẽ được hiểu là năm của hệ lịch Thái, không phải lệnh yêu cầu “đổi năm ISO 2019 sang Phật lịch”.

[Java SE 21 — MinguoChronology](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/MinguoChronology.html) quy định năm liên tục bằng năm ISO trừ 1911. Ví dụ `MinguoDate.of(108, 5, 1)` tương ứng `2019-05-01`. Hệ lịch còn có kỷ nguyên trước Dân Quốc; khi làm việc với ngày trước mốc khởi đầu, vẫn cần phân biệt năm liên tục với năm trong kỷ nguyên.

Quan hệ lệch năm giúp nhận diện hai kiểu này, nhưng mã chuyển đổi nên dùng API thay vì tự cộng/trừ rồi sao chép trường. Làm rõ đầu vào thuộc hệ lịch nào sẽ tránh hiểu nhầm một số năm đã được chuyển đổi từ trước.

## 5. `HijrahDate`: cần biết biến thể và phạm vi dữ liệu

[Java SE 21 — HijrahDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/HijrahDate.html) biểu diễn ngày gắn với một `HijrahChronology` cụ thể. Các phương thức tiện ích như `HijrahDate.from()` và `of()` dùng lịch Umm Al-Qura; mã hệ lịch thường thấy trong runtime là `Hijrah-umalqura`.

Theo [HijrahChronology](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/HijrahChronology.html), lịch Hijrah có nhiều biến thể, tháng dài 29 hoặc 30 ngày, năm thường 354 ngày và năm nhuận 355 ngày. Biến thể có thể dựa trên dữ liệu lịch cấu hình cho một phạm vi năm, nên không được giả định mọi ngày xa trong quá khứ/tương lai đều được hỗ trợ hoặc mọi biến thể cho cùng một kết quả.

Điểm khác biệt với hai kiểu lệch năm ở trên là tháng và ngày Hijrah không giữ nguyên theo ISO. Ngày ISO `2019-05-01` trong dữ liệu Umm Al-Qura dùng ở ví dụ tương ứng năm 1440, tháng 8, ngày 26.

Cộng một tháng Hijrah có nghĩa đi theo tháng của hệ lịch Hijrah; không phải cộng một tháng ISO rồi đổi cách ghi. Khi hợp đồng nguồn ghi “lịch Hồi giáo”, cần xác định biến thể được yêu cầu, thay vì mặc nhiên xem đó là một lịch duy nhất không có cấu hình.

## 6. Chương trình kiểm chứng: cùng ngày, trường khác nhau

Lưu mã vào `CalendarTypesDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài:

```java
import java.time.*;
import java.time.chrono.*;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class CalendarTypesDemo {
    private static void describe(ChronoLocalDate date) {
        System.out.printf(Locale.ROOT,
                "%s | year=%d | yearOfEra=%d | month=%d | day=%d | ISO=%s%n",
                date.getChronology().getId(),
                date.get(ChronoField.YEAR),
                date.get(ChronoField.YEAR_OF_ERA),
                date.get(ChronoField.MONTH_OF_YEAR),
                date.get(ChronoField.DAY_OF_MONTH),
                LocalDate.from(date));
    }

    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2019, 5, 1);
        JapaneseDate japanese = JapaneseDate.from(iso);
        ThaiBuddhistDate buddhist = ThaiBuddhistDate.from(iso);
        HijrahDate hijrah = HijrahDate.from(iso);
        MinguoDate minguo = MinguoDate.from(iso);

        System.out.println("source = " + iso);
        describe(japanese);
        describe(buddhist);
        describe(hijrah);
        describe(minguo);
        System.out.println("Japanese era = " + japanese.getEra());
        System.out.println("same epoch day = "
                + (iso.toEpochDay() == hijrah.toEpochDay()));
        System.out.println("equals across calendars = " + iso.equals(japanese));
        System.out.println("isEqual across calendars = " + iso.isEqual(japanese));

        JapaneseDate byEra = JapaneseDate.of(JapaneseEra.REIWA, 1, 5, 1);
        System.out.println("era constructor -> ISO = " + LocalDate.from(byEra));
        try {
            JapaneseDate.of(JapaneseEra.REIWA, 1, 1, 1);
        } catch (DateTimeException ex) {
            System.out.println("before Reiwa start = DateTimeException");
        }

        DateTimeFormatter japaneseText = DateTimeFormatter
                .ofPattern("G y-MM-dd", Locale.ENGLISH)
                .withChronology(JapaneseChronology.INSTANCE);
        System.out.println("formatted ISO via Japanese = "
                + japaneseText.format(iso));
        System.out.println("Thai year constructor -> ISO = "
                + LocalDate.from(ThaiBuddhistDate.of(2562, 5, 1)));
        System.out.println("Minguo year constructor -> ISO = "
                + LocalDate.from(MinguoDate.of(108, 5, 1)));

        ChronoLocalDate later = hijrah.plus(1, java.time.temporal.ChronoUnit.MONTHS);
        System.out.println("Hijrah plus one month -> ISO = "
                + LocalDate.from(later));
        System.out.println("ISO plus one month = " + iso.plusMonths(1));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CalendarTypesDemo.java
java CalendarTypesDemo
```

Kết quả đã kiểm chứng với dữ liệu lịch của runtime dùng trong bài:

```text
source = 2019-05-01
Japanese | year=2019 | yearOfEra=1 | month=5 | day=1 | ISO=2019-05-01
ThaiBuddhist | year=2562 | yearOfEra=2562 | month=5 | day=1 | ISO=2019-05-01
Hijrah-umalqura | year=1440 | yearOfEra=1440 | month=8 | day=26 | ISO=2019-05-01
Minguo | year=108 | yearOfEra=108 | month=5 | day=1 | ISO=2019-05-01
Japanese era = Reiwa
same epoch day = true
equals across calendars = false
isEqual across calendars = true
era constructor -> ISO = 2019-05-01
before Reiwa start = DateTimeException
formatted ISO via Japanese = Reiwa 1-05-01
Thai year constructor -> ISO = 2019-05-01
Minguo year constructor -> ISO = 2019-05-01
Hijrah plus one month -> ISO = 2019-05-31
ISO plus one month = 2019-06-01
```

Các mốc cố định giúp tránh phụ thuộc ngày chạy. Với Hijrah và văn bản theo ngôn ngữ, đầu ra còn phản ánh biến thể/dữ liệu runtime đang dùng; không mở rộng một lần chạy thành cam kết cho mọi nguồn dữ liệu lịch khác.

## 7. Chuyển ngày khác với sao chép số năm/tháng/ngày

`JapaneseDate.from(iso)`, `ThaiBuddhistDate.from(iso)`, `HijrahDate.from(iso)` và `MinguoDate.from(iso)` biểu diễn cùng ngày nguồn theo hệ lịch đích. Dòng `same epoch day = true` cho thấy ngày ISO và ngày Hijrah có cùng số ngày tính từ mốc ISO `1970-01-01`.

`LocalDate.from(otherCalendarDate)` làm chiều ngược lại: nhận biểu diễn ISO của ngày đó. Nó không lấy nguyên số năm 1440 hoặc 2562 rồi dùng làm năm ISO. Đó là khác biệt giữa **chuyển cùng ngày** và **dựng ngày mới từ các số được diễn giải trong một hệ lịch**.

Quy trình có thể được hình dung:

```text
Ngày ISO 2019-05-01
      ↓ chuyển theo cùng ngày
Japanese / ThaiBuddhist / Hijrah / Minguo
      ↓ LocalDate.from(...)
Ngày ISO 2019-05-01
```

Nếu đầu vào ban đầu là `Instant`, phải chọn vùng để biết ngày địa phương trước khi thực hiện việc chuyển hệ lịch. Bốn kiểu trong bài không tự cung cấp giờ bắt đầu ngày hoặc vùng cho một thời điểm.

## 8. So sánh, phép toán và định dạng cần giữ ngữ nghĩa hệ lịch

### Bằng đối tượng khác với cùng ngày trên lịch tuyến tính

`iso.equals(japanese)` là `false` dù chúng biểu diễn cùng ngày, vì phép bằng còn phân biệt hệ lịch. `iso.isEqual(japanese)` là `true` vì câu hỏi lúc này là có cùng ngày trên trục ngày hay không. Khi so sánh giữa các hệ lịch, chọn phép toán theo đúng câu hỏi, không xem `equals()` thất bại là bằng chứng hai ngày cách nhau.

Trong ví dụ, `ChronoLocalDate` chỉ giúp hàm `describe()` đọc các trường chung và minh họa so sánh. Với mã nghiệp vụ chỉ dùng ngày ISO, chữ ký `LocalDate` thường dễ hiểu hơn việc chuyển mọi biến sang kiểu tổng quát rồi vô tình áp giả định ISO lên dữ liệu hệ khác.

### Cộng tháng theo lịch của đối tượng

Hai dòng cuối cho thấy cộng một tháng Hijrah từ ngày nguồn cho ngày ISO `2019-05-31`, còn cộng một tháng ISO cho `2019-06-01`. Không có lỗi làm tròn ở đây: hai đơn vị “tháng” thuộc hai hệ lịch khác nhau.

Vì thế, khi yêu cầu nói “sau một tháng”, phải xác định tháng theo lịch nào. Nếu chỉ chuyển sang hệ khác để hiển thị, thường nên giữ phép tính nghiệp vụ trên hệ lịch đã thống nhất rồi chuyển ở ranh giới hiển thị. Nếu nghiệp vụ thật sự dựa trên tháng Hijrah hoặc niên hiệu, phải giữ rõ hệ lịch trong phép toán.

### Chọn hệ lịch hiển thị riêng với Locale

Chương trình dùng mẫu `G y-MM-dd` và `withChronology(JapaneseChronology.INSTANCE)` để định dạng ngày ISO thành `Reiwa 1-05-01`. Trong mẫu, `G` là kỷ nguyên, `y` là năm trong kỷ nguyên. `Locale.ENGLISH` chỉ chọn cách viết văn bản; lời gọi `withChronology()` mới làm rõ hệ lịch cần dùng.

Không chỉ đổi sang Locale tiếng Nhật rồi coi mọi formatter đều tự chọn niên hiệu Nhật. Khi phân tích chuỗi năm trong kỷ nguyên, cần có đủ thông tin kỷ nguyên và cấu hình hệ lịch phù hợp; một chuỗi chỉ chứa số năm có thể chưa đủ để biết nó thuộc hệ nào.

## 9. Tự kiểm tra việc nhận diện

Trước khi nhận một ngày không dùng lịch ISO, hãy làm rõ: hệ lịch nào, kỷ nguyên nào nếu có, biến thể nào nếu có, phạm vi ngày được hỗ trợ và chuỗi gốc có cần được bảo toàn không. Một chuỗi `108-05-01` không tự nói rằng nó là năm Dân Quốc 108; nếu bỏ metadata hệ lịch, thông tin có thể trở nên mơ hồ.

Bài tập: chuyển `LocalDate.of(2020, 2, 29)` sang `ThaiBuddhistDate` và `MinguoDate`. Phần năm lần lượt là 2563 và 109, tháng/ngày vẫn là 2/29; khi chuyển ngược bằng `LocalDate.from()`, phải lấy lại `2020-02-29`. Sau đó giải thích vì sao không thể dự đoán trường tháng/ngày của `HijrahDate` bằng cách giữ nguyên `2/29` và chỉ sửa năm.
