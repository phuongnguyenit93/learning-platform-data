# Phân biệt hệ lịch khác với định dạng ngôn ngữ hoặc múi giờ

## Ba yêu cầu khác nhau thường bị gọi chung là “đổi ngày”

Giả sử ứng dụng có một mốc nộp bài. Người dùng có thể muốn:

- Đọc tên tháng bằng tiếng Pháp.
- Xem ngày theo lịch Phật giáo Thái.
- Xem giờ địa phương tại Thành phố Hồ Chí Minh thay vì UTC.

Ba yêu cầu này tác động lên ba khía cạnh khác nhau: **ngôn ngữ/định dạng**, **hệ lịch** và **múi giờ**. Chúng có thể kết hợp trong một lần hiển thị, nhưng không thay thế nhau.

Nếu chọn `Locale.FRANCE` rồi kỳ vọng giờ tự chuyển sang Paris, mã sẽ không thực hiện đúng ý định. Nếu đổi sang lịch Thái rồi nghĩ mốc sự kiện đã được chuyển múi giờ, ta cũng đang nhầm hai phép biến đổi.

## 1. Ba câu hỏi để chọn đúng công cụ

| Câu hỏi | Thành phần phù hợp | Ví dụ |
| --- | --- | --- |
| Dùng quy tắc nào để tổ chức và đánh số ngày? | `Chronology` | ISO, Thai Buddhist, Japanese |
| Viết các thành phần bằng ngôn ngữ/quy ước nào? | `Locale` và `DateTimeFormatter` | `June` hay `juin`, thứ tự ngày/tháng |
| Một thời điểm được nhìn thành ngày giờ địa phương nào? | `ZoneId` | UTC hay `Asia/Ho_Chi_Minh` |

**Hệ lịch (chronology)** quyết định ý nghĩa năm, tháng, ngày, kỷ nguyên và các quy tắc lịch. Cùng một ngày có thể có con số năm khác nhau khi biểu diễn ở hai hệ lịch. [Tài liệu `Chronology`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/Chronology.html)

**Ngôn ngữ/quy ước vùng (locale)** cung cấp ngữ cảnh cho văn bản và các quy ước bản địa hóa. Nó không phải tọa độ hoặc múi giờ hiện tại của người dùng. [Tài liệu `Locale`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)

**Múi giờ** xác định quy tắc liên hệ một `Instant` với ngày giờ địa phương. Mã vùng có thể có quy tắc đổi offset theo thời gian. [Tài liệu `ZoneId`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html)

Ví dụ một người dùng tiếng Việt đang ở Pháp có thể chọn:

```text
ngôn ngữ hiển thị: tiếng Việt
hệ lịch:          ISO
múi giờ:          Europe/Paris
```

Không có yêu cầu rằng cả ba lựa chọn phải trỏ đến cùng một quốc gia.

## 2. Tách các lớp dữ liệu trước khi định dạng

Các kiểu `java.time` giúp giữ khác biệt:

| Kiểu | Thông tin chính |
| --- | --- |
| `Instant` | Một mốc trên dòng thời gian |
| `ZonedDateTime` | Ngày giờ địa phương, vùng và offset đã xác định |
| `LocalDate` | Ngày theo hệ ISO, không giữ giờ/múi giờ |
| `ThaiBuddhistDate`, `JapaneseDate` | Ngày theo hệ lịch cụ thể |
| `String` đã định dạng | Văn bản theo một cấu hình trình bày |

Một chuỗi văn bản không tự giữ mọi thông tin của đối tượng nguồn. Nếu chỉ in ngày và tháng, người đọc không thể từ chuỗi đó khôi phục toàn bộ `Instant`, vùng hoặc hệ lịch nếu thiếu hợp đồng.

Trình tự có ý nghĩa khi hiển thị một sự kiện là:

```text
Instant
   ↓ chọn múi giờ
ngày/giờ địa phương
   ↓ chọn hệ lịch để biểu diễn phần ngày
các trường ngày theo hệ lịch đích
   ↓ chọn ngôn ngữ và cấu trúc định dạng
văn bản cho người dùng
```

Với một ngày sinh chỉ có `LocalDate`, không cần tự tạo `Instant` rồi chuyển vùng chỉ để đổi tên tháng.

## 3. Chương trình hoàn chỉnh: thay từng yếu tố để quan sát

Lưu dưới tên `CalendarLocaleZoneDemo.java`. Chương trình dùng Java 17 trở lên và thư viện chuẩn:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.chrono.IsoChronology;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.chrono.ThaiBuddhistDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class CalendarLocaleZoneDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 6, 15);

        DateTimeFormatter english =
                DateTimeFormatter.ofPattern("dd MMMM uuuu", Locale.ENGLISH)
                        .withChronology(IsoChronology.INSTANCE);
        DateTimeFormatter french = english.withLocale(Locale.FRANCE);

        System.out.println("english=" + english.format(date));
        System.out.println("french=" + french.format(date));
        System.out.println("sourceDate=" + date);
        System.out.println("sourceChronology=" + date.getChronology().getId());
        System.out.println("frenchChronology="
                + french.getChronology().getId());

        DateTimeFormatter numericIso =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                        .withChronology(IsoChronology.INSTANCE)
                        .withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter numericThai =
                numericIso.withChronology(ThaiBuddhistChronology.INSTANCE);

        ThaiBuddhistDate thai = ThaiBuddhistDate.from(date);
        System.out.println("isoCalendar=" + numericIso.format(date));
        System.out.println("thaiCalendar=" + numericThai.format(date));
        System.out.println("calendarConversionSameDay=" + thai.isEqual(date));
        System.out.println("thaiTextBackToIso="
                + numericThai.parse("2567-06-15", LocalDate::from));

        Instant event = Instant.parse("2024-06-15T23:30:00Z");
        ZonedDateTime utc = event.atZone(ZoneOffset.UTC);
        ZonedDateTime hoChiMinh =
                event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("utcLocal=" + utc.toLocalDateTime());
        System.out.println("hoChiMinhLocal=" + hoChiMinh.toLocalDateTime());
        System.out.println("zoneConversionSameInstant="
                + utc.toInstant().equals(hoChiMinh.toInstant()));
        System.out.println("sameLocalDate="
                + utc.toLocalDate().equals(hoChiMinh.toLocalDate()));

        DateTimeFormatter eventView =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm XXX", Locale.ROOT)
                        .withChronology(IsoChronology.INSTANCE);

        System.out.println("utcView="
                + eventView.withZone(ZoneOffset.UTC).format(event));
        System.out.println("hoChiMinhView="
                + eventView.withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                        .format(event));
        System.out.println("thaiHoChiMinhView="
                + eventView.withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                        .withChronology(ThaiBuddhistChronology.INSTANCE)
                        .format(event));

        Locale thaiCalendarPreference =
                Locale.forLanguageTag("en-US-u-ca-buddhist");

        System.out.println("withLocaleOnly="
                + numericIso.withLocale(thaiCalendarPreference)
                        .getChronology().getId());
        System.out.println("localizedBy="
                + numericIso.localizedBy(thaiCalendarPreference)
                        .getChronology().getId());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CalendarLocaleZoneDemo.java
java CalendarLocaleZoneDemo
```

Stdout với dữ liệu ngôn ngữ và múi giờ thông dụng của JDK:

```text
english=15 June 2024
french=15 juin 2024
sourceDate=2024-06-15
sourceChronology=ISO
frenchChronology=ISO
isoCalendar=2024-06-15
thaiCalendar=2567-06-15
calendarConversionSameDay=true
thaiTextBackToIso=2024-06-15
utcLocal=2024-06-15T23:30
hoChiMinhLocal=2024-06-16T06:30
zoneConversionSameInstant=true
sameLocalDate=false
utcView=2024-06-15 23:30 Z
hoChiMinhView=2024-06-16 06:30 +07:00
thaiHoChiMinhView=2567-06-16 06:30 +07:00
withLocaleOnly=ISO
localizedBy=ThaiBuddhist
```

Những phần sau giải thích từng nhóm kết quả.

## 4. Thay ngôn ngữ: chữ hiển thị đổi, ngày nguồn vẫn giữ nguyên

Hai dòng:

```text
15 June 2024
15 juin 2024
```

cùng biểu diễn ngày ISO 15/06/2024. `withLocale(Locale.FRANCE)` làm tên tháng dùng tiếng Pháp; bộ định dạng vẫn được cấu hình với hệ lịch ISO.

Với mẫu tự viết `dd MMMM uuuu`, thứ tự trường là do mẫu quy định. Đổi locale không tự biến mọi mẫu cố định thành cấu trúc ngày thường dùng ở quốc gia ấy. Nếu muốn cấu trúc hiển thị theo phong cách địa phương, có thể chọn các bộ định dạng bản địa hóa phù hợp thay vì cố định toàn bộ thứ tự trường.

Đổi locale cũng không “dịch” các đoạn văn bản literal bạn đã viết trong mẫu. Chẳng hạn, một nhãn riêng bằng tiếng Việt vẫn cần cơ chế dịch của ứng dụng.

Khi kiểm chứng chiều này, hãy giữ cùng giá trị ngày, hệ lịch và vùng nếu có, chỉ thay locale. Như vậy sẽ biết sự thay đổi nào thuộc về phần trình bày.

## 5. Thay hệ lịch: các trường ngày đổi, ngày được đại diện vẫn giữ

Trong chương trình:

```text
ISO:            2024-06-15
Thai Buddhist:  2567-06-15
```

là hai cách biểu diễn cùng một ngày. Phép kiểm tra `thai.isEqual(date)` cho true.

Đây không chỉ là dịch từ “June” sang một từ khác. Năm đã có ý nghĩa theo một hệ lịch khác. Vì vậy, chuỗi `2567-06-15` cần được diễn giải với đúng chronology; phân tích nó mặc định như ngày ISO sẽ tạo ngày ISO năm 2567.

`withChronology` trên bộ định dạng cho phép chọn hệ lịch dùng để biểu diễn/phân giải ngày. Nó không sửa đối tượng `LocalDate` nguồn. Trong chương trình, nguồn vẫn là `2024-06-15` theo ISO.

Nếu chỉ cần đổi ngôn ngữ tên tháng, không cần đổi chronology. Nếu cần biểu diễn theo một lịch khác, chỉ đổi tên tháng sẽ không thực hiện phép chuyển đổi cần thiết.

Khi kiểm chứng chiều này, giữ cùng ngày hoặc cùng vị trí ngày, kiểm tra chuyển đổi ngược và xác nhận hệ lịch đích đúng với hợp đồng.

## 6. Thay múi giờ: cùng thời điểm có thể khác cả ngày lịch

Mốc sự kiện trong chương trình là:

```text
2024-06-15T23:30:00Z
```

Tại UTC, đó là 23:30 ngày 15/06. Tại Thành phố Hồ Chí Minh, đó là 06:30 ngày 16/06.

Phép kiểm tra:

```text
zoneConversionSameInstant=true
sameLocalDate=false
```

cho thấy vừa giữ cùng thời điểm, vừa có thể đổi ngày địa phương.

Đây là hiệu ứng của vùng, không phải đổi hệ lịch. Cả `utc.toLocalDate()` và `hoChiMinh.toLocalDate()` đều là `LocalDate` theo ISO; chúng khác ngày vì được lấy từ hai cách nhìn địa phương của cùng sự kiện.

Khi muốn hiển thị cùng sự kiện cho người ở vùng khác, giữ `Instant` và áp dụng vùng đích. Không xóa offset hoặc chuyển về `LocalDateTime` rồi gắn lại vùng khác mà không xét ý nghĩa: thao tác ấy có thể diễn giải lại giờ và đổi thời điểm.

Tên ngôn ngữ không đủ để suy ra vùng. Tiếng Anh có thể được dùng ở nhiều múi giờ; mã quốc gia cũng không nhất thiết xác định một vùng duy nhất. Vùng của báo cáo hoặc sở thích vùng của người dùng cần được chọn độc lập.

## 7. Kết hợp ba yếu tố có chủ đích

Dòng:

```text
thaiHoChiMinhView=2567-06-16 06:30 +07:00
```

kết hợp:

- Cùng `Instant` như các dòng trước.
- Vùng `Asia/Ho_Chi_Minh`, nên giờ địa phương là 06:30 ngày 16/06.
- Hệ lịch Thai Buddhist, nên năm hiển thị là 2567.
- Mẫu số và locale đã chọn rõ ràng.

Không có điều gì buộc lịch Thai Buddhist chỉ được dùng khi vùng là Thái Lan, hoặc tiếng Pháp chỉ được dùng khi vùng là Paris. Sản phẩm có thể giới hạn lựa chọn theo nhu cầu, nhưng đó là quyết định của sản phẩm.

`DateTimeFormatter` có các cấu hình riêng `withLocale`, `withChronology` và `withZone`; khi định dạng `Instant`, vùng cung cấp cách nhìn ngày giờ địa phương, còn chronology cung cấp hệ lịch cho phần ngày. [Tài liệu cấu hình bộ định dạng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

Các cấu hình này có yêu cầu về thông tin sẵn có của kiểu nguồn. Đừng suy rộng rằng gắn một vùng vào bộ định dạng có thể tự tạo giờ còn thiếu cho một `LocalDate`. Một ngày sinh không có giờ vẫn không tự trở thành một mốc sự kiện đầy đủ.

## 8. Chi tiết cần biết: locale có thể mang sở thích lịch hoặc vùng

Phân biệt ba khái niệm không có nghĩa API không bao giờ kết hợp chúng.

Locale có thể chứa các phần mở rộng Unicode, ví dụ:

```text
en-US-u-ca-buddhist
        └────────── sở thích dùng lịch Buddhist
```

Trong chương trình:

- `numericIso.withLocale(preference)` giữ chronology ISO đã cấu hình.
- `numericIso.localizedBy(preference)` áp dụng sở thích lịch từ phần mở rộng và cho chronology Thai Buddhist.

`localizedBy` còn có thể áp dụng các sở thích liên quan đến kiểu chữ số hoặc vùng khi phần mở rộng phù hợp hiện diện. Thứ tự kết hợp nó với các lời gọi cấu hình khác có thể ảnh hưởng kết quả. [Tài liệu `localizedBy`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#localizedBy(java.util.Locale))

Vì vậy, câu “locale chỉ là ngôn ngữ và không bao giờ liên quan hệ lịch” quá tuyệt đối. Cách hiểu đúng là:

- Hệ lịch, ngôn ngữ và vùng là các khái niệm riêng.
- Một API cụ thể có thể lấy nhiều sở thích từ cùng cấu hình.
- Phải kiểm tra hành vi của phương thức được dùng, thay vì suy ra chỉ từ tên biến `locale`.

Với hợp đồng máy–máy yêu cầu ISO, nên khai báo các lựa chọn quan trọng rõ ràng và kiểm tra cấu hình cuối, không vô tình nhận một sở thích trình bày thành quy tắc diễn giải dữ liệu.

## 9. Thiết kế dữ liệu và tìm lỗi theo đúng trục

Nếu bản ghi là một sự kiện đã diễn ra, mô hình có thể giữ mốc `Instant` cùng những thông tin vùng nguồn cần thiết. Cách hiển thị được tạo theo cấu hình người xem.

Nếu dữ liệu là một ngày không có giờ, giữ `LocalDate` hoặc kiểu ngày nguồn có ý nghĩa. Không tự chuyển vùng một dữ liệu vốn không có thời điểm.

Nếu người dùng nhập theo lịch khác, hợp đồng phải nêu hệ lịch, các trường/kỷ nguyên và quy tắc phân tích. Lưu ISO có thể bảo toàn ngày sau chuyển đổi; nếu cần truy vết cách người dùng nhập, còn phải giữ thông tin nguồn thích hợp.

Khi thấy hiển thị sai, chẩn đoán theo dấu hiệu:

| Hiện tượng | Điều cần kiểm tra trước |
| --- | --- |
| Tên tháng hoặc thứ sai ngôn ngữ | Locale, kiểu văn bản, dữ liệu ngôn ngữ |
| Năm bị hiểu theo lịch khác | Chronology và hợp đồng phân tích |
| Giờ lệch vài tiếng hoặc đổi ngày gần nửa đêm | ZoneId, offset, kiểu nguồn |
| Cùng giá trị ở hai máy hiển thị khác | Các mặc định locale/zone và cấu hình bộ định dạng |
| Một thay đổi sở thích gây nhiều hiệu ứng cùng lúc | Phần mở rộng locale, `localizedBy`, thứ tự cấu hình |

Không sửa một lỗi vùng bằng cách cộng tay bảy giờ; không sửa lỗi hệ lịch bằng cách thay chữ tháng; không sửa lỗi ngôn ngữ bằng cách đổi ngày nguồn.

## 10. Kiểm chứng bằng cách thay từng yếu tố

Một bộ kiểm chứng rõ ràng nên:

1. Giữ ngày và hệ lịch cố định, đổi locale; xác nhận ngày không đổi.
2. Giữ vị trí ngày cố định, đổi chronology; xác nhận chuyển đổi ngược cho ngày ban đầu.
3. Giữ `Instant` cố định, đổi vùng; xác nhận `toInstant()` không đổi nhưng ngày/giờ địa phương có thể đổi.
4. Dùng mốc gần nửa đêm để phát hiện đổi ngày qua vùng.
5. Kết hợp các cấu hình một cách tường minh rồi kiểm tra kết quả cuối.
6. Nếu dùng locale mở rộng, kiểm tra `withLocale` và `localizedBy` theo đúng API được chọn.

Tên tháng, dấu câu hoặc dữ liệu vùng có thể phụ thuộc dữ liệu đi kèm JDK. Với kiểm tra nghiệp vụ, ưu tiên xác nhận cả giá trị có kiểu và cấu hình, không chỉ chụp một chuỗi hiển thị rồi suy ra toàn bộ ý nghĩa thời gian.

## 11. Tự thực hành

1. Muốn đổi `June` thành `juin`, có cần chuyển `Instant` sang Paris không?
2. Vì sao cùng sự kiện có thể là ngày 15 ở UTC và ngày 16 ở Việt Nam?
3. Một ngày Thai Buddhist năm 2567 có nên được phân tích như ISO năm 2567 không?
4. Locale tiếng Việt có tự nói người dùng hiện ở múi giờ nào không?
5. Vì sao phải đọc riêng hành vi `localizedBy` dù đã hiểu `withLocale`?

Gợi ý đáp án:

1. Không; đây là yêu cầu ngôn ngữ trình bày.
2. Múi giờ làm thay đổi cách nhìn ngày giờ địa phương của cùng thời điểm.
3. Không; phải dùng đúng hệ lịch nguồn rồi chuyển đổi khi cần.
4. Không.
5. Vì nó có thể áp dụng thêm sở thích lịch, chữ số hoặc vùng từ phần mở rộng locale.

Hãy gọi tên đúng điều muốn đổi: ngôn ngữ trình bày, cách tổ chức ngày theo hệ lịch hay cách nhìn thời điểm qua múi giờ. Sau đó chọn và kiểm chứng cấu hình tương ứng.
