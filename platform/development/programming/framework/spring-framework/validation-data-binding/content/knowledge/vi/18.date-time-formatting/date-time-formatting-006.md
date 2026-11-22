# Phân biệt múi giờ, độ lệch UTC và Locale trong Spring Framework

## 1. Mục tiêu và tình huống thực tế

Một ứng dụng Spring nhận yêu cầu đặt lịch: **9 giờ sáng ngày 01/07/2026**. Câu hỏi quan trọng không chỉ là chuỗi ngày giờ có đúng định dạng hay không, mà còn là **9 giờ sáng ở đâu** và **người dùng muốn nhìn thấy nó theo cách nào**.

Có ba khái niệm độc lập:

1. **Múi giờ (time zone)**: quy tắc chuyển đổi giữa một thời điểm thực và giờ địa phương theo một vùng, thường thể hiện qua `ZoneId` như `Asia/Ho_Chi_Minh`, `America/New_York`.
2. **Độ lệch UTC (UTC offset)**: lượng thời gian cộng/trừ so với UTC tại một thời điểm, thể hiện qua `ZoneOffset` như `+07:00`, `-04:00`.
3. **Locale**: quy ước ngôn ngữ/vùng dùng để trình bày hoặc đọc chuỗi, thể hiện qua `Locale` như `vi-VN`, `en-US`, `fr-FR`.

Chúng trả lời ba câu hỏi khác nhau:

- **ZoneId:** quy tắc thời gian của địa điểm nào được áp dụng?
- **ZoneOffset:** tại thời điểm này, giờ ở vùng đó chênh UTC bao nhiêu?
- **Locale:** ngày, tháng, tên thứ, chữ số và thông báo được hiển thị/diễn giải theo quy ước nào?

Ví dụ cùng một thời điểm `2026-07-01T12:00:00Z` (UTC):

| Bối cảnh | Giờ địa phương tại thời điểm đó | Độ lệch UTC |
| --- | --- | --- |
| `Asia/Ho_Chi_Minh` | 19:00 ngày 01/07/2026 | `+07:00` |
| `America/New_York` | 08:00 ngày 01/07/2026 | `-04:00` |
| UTC | 12:00 ngày 01/07/2026 | `+00:00` |

Đổi `Locale.US` thành `Locale.FRANCE` **không đổi** thời điểm hay độ lệch UTC của New York; nó chỉ có thể đổi biểu diễn văn bản. Ngược lại, thay `ZoneId` từ Việt Nam sang New York **thay đổi giờ trên mặt đồng hồ** được hiển thị cho cùng một `Instant`, nhưng không thay đổi bản thân thời điểm đó.

## 2. UTC, ZoneOffset, ZoneId và Locale: bảng phân biệt

| Thuật ngữ | Kiểu Java liên quan | Chứa gì? | Không chứa gì? | Ví dụ |
| --- | --- | --- | --- | --- |
| UTC | Mốc tham chiếu thời gian | Thang tham chiếu có độ lệch bằng 0 | Ngôn ngữ, cách trình bày | `2026-07-01T12:00:00Z` |
| UTC offset | `ZoneOffset` | Độ lệch cố định so với UTC | Lịch sử/luật đổi giờ của một khu vực | `+07:00`, `-05:00` |
| Time zone vùng | `ZoneId` | ID vùng và bộ quy tắc lịch sử/tương lai từ tzdb | Locale của người dùng | `Europe/Paris` |
| Locale | `java.util.Locale` | Ngôn ngữ, vùng, quy tắc văn bản/số/ngày | Múi giờ hoặc UTC offset | `vi-VN`, `en-US` |
| Instant | `java.time.Instant` | Một điểm trên dòng thời gian | Múi giờ hay locale gốc của người nhập | `2026-07-01T12:00:00Z` |

**UTC không đồng nghĩa với Locale và cũng không phải một địa điểm.** Chữ `Z` trong chuỗi thời gian ISO-8601 thể hiện offset bằng 0 (`Zulu`/UTC); dấu `+07:00` biểu thị giờ địa phương đi trước UTC bảy giờ, còn `-04:00` đi sau UTC bốn giờ. `+07:00` là một offset, không tự nói đó là Việt Nam.

**`ZoneOffset` là một dạng `ZoneId` cố định** trong API `java.time`, nhưng bản thân nó không mang các quy tắc giờ mùa hè (DST). `ZoneId.of("Asia/Ho_Chi_Minh")` là ID vùng; `ZoneOffset.of("+07:00")` chỉ là độ lệch. Chúng có thể cho cùng giờ ở một thời điểm hiện đại nhưng khác nhau về dữ liệu biểu diễn và khả năng xử lý các biến động lịch sử.

**Locale không suy ra timezone.** Người dùng chọn tiếng Việt (`vi-VN`) có thể đang sống ở New York; một người dùng `en-US` có thể đang ở Thành phố Hồ Chí Minh. Không suy diễn `Locale` → `ZoneId` nếu không có chính sách nghiệp vụ rõ ràng và dữ liệu vị trí do người dùng cung cấp.

## 3. Múi giờ là tập hợp quy tắc; offset là kết quả tại một thời điểm

Vùng `America/New_York` có thể có hai offset khác nhau trong năm 2026:

- Tháng 01/2026: UTC`-05:00` (giờ chuẩn).
- Tháng 07/2026: UTC`-04:00` (thời gian áp dụng DST).

Bởi vậy, không nên nói **“múi giờ New York luôn là UTC-5”**. Đúng hơn: “offset của New York tại một `Instant` cụ thể được tính từ quy tắc của `ZoneId`”.

Trong Java:

```java
ZoneId zone = ZoneId.of("America/New_York");
Instant instant = Instant.parse("2026-07-01T12:00:00Z");
ZoneOffset offset = zone.getRules().getOffset(instant); // -04:00
```

Đây là đoạn minh họa API, không phải chương trình độc lập; cần import các lớp từ `java.time`. Phương thức `getOffset(instant)` có đầu vào là thời điểm đã xác định, do đó cho **một** kết quả. Với giờ địa phương chưa có offset, câu trả lời có thể có 0, 1 hoặc 2 kết quả ở ngày đổi giờ mùa hè.

Hệ thống sử dụng dữ liệu quy tắc múi giờ (tzdb/IANA), có thể được cập nhật khi luật của các quốc gia thay đổi. Không hard-code mọi vùng dưới dạng offset cố định, đặc biệt với lịch trong tương lai.

### 3.1. Giờ không tồn tại và giờ bị lặp khi DST

Tại New York trong năm 2026, theo quy tắc múi giờ hiện hành:

- **Gap:** `2026-03-08 02:30` là giờ địa phương không tồn tại vì đồng hồ chuyển từ khoảng 02:00 sang 03:00. `getValidOffsets(local)` trả danh sách rỗng.
- **Overlap:** `2026-11-01 01:30` xuất hiện hai lần khi đồng hồ lùi; giờ đó có hai offset hợp lệ: `-04:00` và `-05:00`.
- Thời gian thông thường có đúng một offset hợp lệ.

Để kiểm tra:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime requested = LocalDateTime.of(2026, 11, 1, 1, 30);
List<ZoneOffset> offsets = ny.getRules().getValidOffsets(requested);
System.out.println(offsets); // [-04:00, -05:00] với tzdb hiện hành
```

Đoạn này cần import `java.time.*` và `java.util.List`.

**`LocalDateTime.atZone(zone)` không phải bộ xác thực “giờ địa phương chắc chắn tồn tại”.** API mặc định có cơ chế xử lý gap bằng cách đẩy giờ sang phía sau khoảng trống và xử lý overlap bằng một offset ưu tiên. Với nghiệp vụ đặt vé, chuyển khoản hẹn giờ hay giao dịch nhạy cảm về thời điểm, không nên âm thầm chấp nhận cách tự điều chỉnh đó.

Chính sách rõ ràng hơn:

1. Không có offset hợp lệ → yêu cầu nhập lại giờ.
2. Một offset hợp lệ → chuyển thành `Instant`.
3. Hai offset hợp lệ → yêu cầu chọn offset/lần xuất hiện, hoặc áp dụng quy tắc nghiệp vụ được công bố trước.

Khi offset đã được chọn, có thể dùng `ZonedDateTime.ofStrict(localDateTime, chosenOffset, zone)` để bảo đảm offset thực sự hợp lệ với vùng và giờ địa phương. Nếu cần phân biệt hai lần `01:30`, một chuỗi chỉ chứa `LocalDateTime` là không đủ.

## 4. Chọn đúng kiểu `java.time` trước khi định dạng hoặc binding

| Kiểu | Mang thông tin gì? | Dùng khi nào? |
| --- | --- | --- |
| `LocalDate` | Ngày lịch, không có giờ/zone | Ngày sinh, ngày hiệu lực không phụ thuộc địa điểm |
| `LocalTime` | Giờ trên đồng hồ, không có ngày/zone | Giờ mở cửa 09:00 theo địa phương |
| `LocalDateTime` | Ngày và giờ địa phương, chưa có offset/zone | Dữ liệu người dùng nhập cho lịch hẹn, trước khi xác định vùng |
| `Instant` | Điểm thời gian duy nhất trên timeline | Thời điểm đã chốt, log, timestamp giao dịch |
| `OffsetDateTime` | Ngày giờ cùng một offset cụ thể | API gửi thời điểm với offset, không cần quy tắc vùng |
| `ZonedDateTime` | Ngày giờ, offset đã xác định và `ZoneId` | Giữ cả thời điểm và ngữ cảnh vùng |
| `ZoneId` | ID vùng/các quy tắc offset | Lịch hẹn lặp theo giờ địa phương |
| `ZoneOffset` | Chênh lệch cố định so với UTC | Ghi offset thực tế được chọn tại một thời điểm |

Hai biểu diễn có thể chỉ cùng một `Instant`:

```text
2026-07-01T12:00:00Z
2026-07-01T19:00:00+07:00
2026-07-01T08:00:00-04:00
```

Trong khi đó `2026-07-01T19:00:00` **không có offset hoặc vùng**, nên chưa xác định được `Instant`.

Để hiểu rõ khi chuyển vùng:

- `withZoneSameInstant(otherZone)`: giữ nguyên thời điểm, đổi giờ địa phương hiển thị.
- `withZoneSameLocal(otherZone)`: cố giữ ngày/giờ trên đồng hồ, nên thường **đổi thời điểm thực**; còn phải xử lý quy tắc gap/overlap của vùng đích.

Ví dụ lịch họp đã chốt dùng `sameInstant` để người tham dự ở nơi khác nhìn thấy đúng thời điểm. Lịch khai trương lúc 09:00 giờ địa phương của một địa điểm khác là bài toán `sameLocal`, đòi hỏi quy tắc nghiệp vụ rõ.

Với lịch hẹn **lặp mỗi ngày lúc 09:00 theo giờ Paris**, lưu `LocalTime`/quy tắc lặp và `Europe/Paris`. Chỉ lưu một offset cố định `+01:00` sẽ làm lịch lệch một giờ khi Paris chuyển sang `+02:00`. Với sự kiện đơn đã chốt, lưu `Instant` và nếu cần tái hiện lý do chọn giờ, lưu thêm `ZoneId` và thông tin lựa chọn offset.

## 5. Locale chỉ điều khiển cách hiển thị/đọc biểu diễn

Một `Locale` thường chứa ngôn ngữ, vùng và một số quy ước văn hóa; ví dụ:

- `Locale.forLanguageTag("vi-VN")`: tiếng Việt dùng cho Việt Nam.
- `Locale.US`: tiếng Anh dùng cho Mỹ.
- `Locale.FRANCE`: tiếng Pháp dùng cho Pháp.

Locale ảnh hưởng đến tên tháng, tên thứ, thứ tự ngày/tháng/năm trong kiểu format theo vùng, ngôn ngữ thông báo, định dạng số hoặc tiền tệ. Nó **không biến `Instant` thành giờ Hà Nội/Paris** nếu bạn chưa chọn `ZoneId`.

Trong `java.time.format.DateTimeFormatter`, hai cấu hình tách biệt:

```java
Instant instant = Instant.parse("2026-07-01T12:00:00Z");
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd MMM uuuu HH:mm XXX", Locale.ENGLISH)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
String display = formatter.format(instant);
```

`withZone(...)` chọn cách nhìn `Instant` trong một vùng; `Locale.ENGLISH` quyết định dạng tên tháng `MMM`. Nếu đổi locale nhưng vẫn giữ zone, giờ địa phương và offset không thay đổi.

Các token cần nhớ:

| Pattern | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `uuuu` | Năm theo lịch ISO/proleptic year | Thường phù hợp hơn `YYYY` cho năm lịch |
| `MM` / `mm` | Tháng / phút | Phân biệt chữ hoa với chữ thường |
| `dd` / `HH` | Ngày trong tháng / giờ 0–23 | Cần đủ ngày/giờ tương ứng |
| `XXX` | Offset dạng ISO như `+07:00` | Chỉ có offset, không chứa ID vùng |
| `VV` | `ZoneId` | Có thể in `Asia/Ho_Chi_Minh` |
| `z` | Tên múi giờ theo locale | Tên viết tắt như EST/CST có thể mơ hồ |
| `MMM` / `EEEE` | Tên tháng viết tắt / thứ trong tuần | Phụ thuộc locale, dữ liệu JDK |

Không tạo ISO UTC bằng cách nối chữ `Z` vào chuỗi giờ địa phương. Chỉ dùng `Z` khi giá trị thực sự được biểu diễn theo UTC/offset 0. Với API trao đổi dữ liệu giữa hệ thống, ưu tiên ISO-8601/RFC 3339 có offset rõ ràng hoặc định dạng `Instant` UTC; dữ liệu giao diện có thể được địa phương hóa riêng.

Việc dùng `DateTimeFormatter.ofLocalizedDate(...)` tiện lợi cho UI, nhưng chuỗi chính xác có thể thay đổi theo JDK/locale data. Nếu hợp đồng API yêu cầu format bất biến, chỉ rõ pattern hoặc dùng bộ formatter ISO thay vì dựa vào `FormatStyle.SHORT` của từng môi trường.

## 6. Ví dụ chạy độc lập với Java 17+: cùng Instant, nhiều vùng và Locale

Đây là chương trình Java đầy đủ, không cần Spring để hiểu phần cốt lõi. Kết quả dưới đây đã được kiểm tra với bộ quy tắc múi giờ hiện hành; dữ liệu tzdb trong JDK khác có thể thay đổi đối với những vùng/năm bị sửa luật.

Tạo tệp **`TimeZoneLocaleDemo.java`**:

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class TimeZoneLocaleDemo {
    static String displayDate(LocalDate value, Locale locale) {
        String pattern = locale.equals(Locale.FRANCE)
                ? "dd/MM/uuuu" : "MM/dd/uuuu";
        return value.format(DateTimeFormatter.ofPattern(pattern, locale));
    }

    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-07-01T12:00:00Z");
        ZoneId vietNam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");

        ZonedDateTime vnTime = instant.atZone(vietNam);
        ZonedDateTime nyTime = instant.atZone(newYork);
        System.out.println("instant=" + instant);
        System.out.println("vietnam=" + vnTime);
        System.out.println("nySummer=" + nyTime);
        System.out.println("nyWinter="
                + Instant.parse("2026-01-01T12:00:00Z").atZone(newYork));
        System.out.println("zoneId=" + vnTime.getZone());
        System.out.println("offset=" + vnTime.getOffset());
        System.out.println("offsetOnly=" + vnTime.toOffsetDateTime());
        System.out.println("sameInstant=" + vnTime.withZoneSameInstant(newYork));
        System.out.println("sameLocal=" + vnTime.withZoneSameLocal(newYork));
        LocalDate date = LocalDate.of(2026, 12, 31);
        System.out.println("localeUS=" + displayDate(date, Locale.US));
        System.out.println("localeFR=" + displayDate(date, Locale.FRANCE));
        LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
        System.out.println("gapValidOffsets="
                + newYork.getRules().getValidOffsets(gap).size());
        System.out.println("overlapValidOffsets="
                + newYork.getRules().getValidOffsets(overlap).size());
    }
}
```

Chạy từ thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 TimeZoneLocaleDemo.java
java TimeZoneLocaleDemo
```

Kết quả stdout:

```text
instant=2026-07-01T12:00:00Z
vietnam=2026-07-01T19:00+07:00[Asia/Ho_Chi_Minh]
nySummer=2026-07-01T08:00-04:00[America/New_York]
nyWinter=2026-01-01T07:00-05:00[America/New_York]
zoneId=Asia/Ho_Chi_Minh
offset=+07:00
offsetOnly=2026-07-01T19:00+07:00
sameInstant=2026-07-01T08:00-04:00[America/New_York]
sameLocal=2026-07-01T19:00-04:00[America/New_York]
localeUS=12/31/2026
localeFR=31/12/2026
gapValidOffsets=0
overlapValidOffsets=2
```

Diễn giải kết quả:

- `vietnam` và `nySummer` chỉ hai cách nhìn cùng `instant`.
- `nyWinter` và `nySummer` có offset khác nhau dù cùng `ZoneId` New York.
- `offsetOnly` giữ `+07:00` nhưng không giữ ID `Asia/Ho_Chi_Minh`.
- `sameInstant` giữ `12:00Z`, còn `sameLocal` giữ chữ số 19:00 và chuyển sang một thời điểm khác.
- `localeUS` và `localeFR` biểu diễn cùng một `LocalDate` bằng hai thứ tự khác nhau. Ví dụ chủ động chọn pattern dựa vào locale để stdout ổn định; nó không khẳng định mọi hệ thống Pháp/Mỹ đều luôn dùng đúng các pattern này.
- `gapValidOffsets=0` và `overlapValidOffsets=2` minh họa lý do phải xác định DST khi nhận lịch hẹn theo giờ địa phương.

## 7. Liên hệ với Spring MVC: data binding, formatter và ngữ cảnh request

Ở tầng web, Spring thường nhận chuỗi từ form, query parameter hoặc path variable rồi chuyển thành kiểu thuộc tính của `@ModelAttribute`/tham số controller qua `WebDataBinder`, `ConversionService` và cơ chế `Formatter`. Các mục này có trách nhiệm khác nhau:

1. **Binding:** ánh xạ tham số `localStart=2026-07-01T19:00:00` vào `LocalDateTime`.
2. **Parsing/formatting:** đọc hoặc in chuỗi theo `@DateTimeFormat`/`Formatter` và `Locale` đã được thiết lập.
3. **Xác định thời điểm:** kết hợp `LocalDateTime` với một `ZoneId` do ứng dụng biết và quy tắc offset hợp lệ.
4. **Validation nghiệp vụ:** phát hiện thời gian không tồn tại/bị lặp, lịch nằm quá khứ hoặc ngoài giờ làm việc.
5. **Lưu trữ/hiển thị:** lưu `Instant` hoặc mô hình lịch thích hợp, khi hiển thị dùng zone + locale của người xem.

**`@DateTimeFormat` không tự suy ra time zone từ `Locale`.** Nếu dữ liệu chỉ có `LocalDateTime`, formatter có thể đọc thành ngày giờ địa phương nhưng vẫn thiếu thông tin để tạo `Instant`.

Ví dụ form model cho một buổi họp:

```java
import java.time.LocalDateTime;
import org.springframework.format.annotation.DateTimeFormat;

public class ScheduleForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
    private LocalDateTime localStart;
    private String zoneId;

    public LocalDateTime getLocalStart() { return localStart; }
    public void setLocalStart(LocalDateTime localStart) {
        this.localStart = localStart;
    }

    public String getZoneId() { return zoneId; }
    public void setZoneId(String zoneId) { this.zoneId = zoneId; }
}
```

Giá trị form mẫu:

```text
localStart=2026-07-01T19:00:00
zoneId=Asia/Ho_Chi_Minh
```

Nếu chưa có `zoneId`, chỉ có chuỗi `localStart` thì backend **không đủ dữ kiện** để khẳng định buổi họp diễn ra lúc `12:00Z`.

### 7.1. Cách xử lý local date-time an toàn khi tạo lịch

Đoạn dưới là **mã tích hợp trong một dự án Spring MVC/Spring Boot có Web MVC**; sử dụng class `ScheduleForm` ở trên. Đây không phải chương trình standalone chạy bằng lệnh `java` của mục 6.

```java
import java.time.*;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;

@RestController
public class ScheduleController {
    @PostMapping("/schedules")
    public ResponseEntity<String> create(
            @ModelAttribute ScheduleForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()
                || form.getLocalStart() == null
                || form.getZoneId() == null) {
            return ResponseEntity.badRequest().body("Invalid form data");
        }

        final ZoneId zone;
        try {
            zone = ZoneId.of(form.getZoneId());
        } catch (DateTimeException ex) {
            return ResponseEntity.badRequest().body("Invalid zone ID");
        }

        LocalDateTime local = form.getLocalStart();
        List<ZoneOffset> validOffsets = zone.getRules().getValidOffsets(local);

        if (validOffsets.size() != 1) {
            return ResponseEntity.badRequest()
                    .body("Local time is missing or ambiguous in this zone");
        }

        Instant confirmed = ZonedDateTime
                .ofStrict(local, validOffsets.get(0), zone)
                .toInstant();

        return ResponseEntity.ok(confirmed.toString());
    }
}
```

Với form mẫu ở trên, phản hồi sẽ mang chuỗi `2026-07-01T12:00:00Z`. Controller cố ý từ chối gap/overlap để người nhập xác nhận lại; một ứng dụng có thể hỗ trợ lựa chọn offset riêng cho giờ bị lặp. Trong sản phẩm thực tế, cần thêm kiểm tra quyền tạo lịch, quy tắc nghiệp vụ và xử lý lỗi theo hợp đồng API.

Điểm quan trọng: `BindingResult` nằm ngay sau tham số `@ModelAttribute` để Spring MVC báo lỗi chuyển đổi field trước khi controller ra quyết định nghiệp vụ. `ZoneId.of(...)` xác thực ID vùng (không dựa vào `TimeZone.getTimeZone(...)` vì API legacy này có thể trả GMT khi ID không hợp lệ).

### 7.2. Spring lấy Locale và timezone của request từ đâu?

Trong Spring MVC (Servlet stack), `LocaleResolver` phục vụ việc xác định `Locale` của request. Một `LocaleContextResolver` có thể cung cấp thêm thông tin `TimeZone`. Các nơi thường gặp:

- Header `Accept-Language` có thể gợi ý `Locale`, **không xác định timezone của trình duyệt**.
- Cookie/session/profile/thiết lập UI có thể chứa một locale hoặc timezone đã được người dùng chọn, tùy chiến lược ứng dụng.
- `LocaleContextHolder` giữ ngữ cảnh locale theo thread trong xử lý request đồng bộ; ví dụ `LocaleContextHolder.getLocale()` và `LocaleContextHolder.getTimeZone()`. Giá trị timezone có thể là mặc định khi resolver không cung cấp timezone riêng.

Mã minh họa cách đọc ngữ cảnh:

```java
import java.time.ZoneId;
import java.util.Locale;
import java.util.TimeZone;
import org.springframework.context.i18n.LocaleContextHolder;

Locale locale = LocaleContextHolder.getLocale();
TimeZone timeZone = LocaleContextHolder.getTimeZone();
ZoneId presentationZone = timeZone.toZoneId();
```

Đoạn này dành cho code chạy trong ngữ cảnh Spring có locale/timezone phù hợp. Nó không chứng minh `presentationZone` chính là timezone do người dùng chọn. Đối với nghiệp vụ đặt lịch có yêu cầu vùng chính xác, nên đọc và kiểm tra `ZoneId` từ profile/tham số hợp lệ, không âm thầm dựa vào timezone mặc định của máy chủ.

Với luồng bất đồng bộ, queue, scheduler hoặc thread riêng, đừng mặc định `LocaleContextHolder` sẽ được mang theo. Truyền `Locale`/`ZoneId` như dữ liệu nghiệp vụ hoặc cấu hình công việc; tránh dựa vào thread-local xuyên ranh giới thread.

### 7.3. Tách biệt form binding và JSON body

- `@ModelAttribute`, form/query field và `@DateTimeFormat`/Spring `FormattingConversionService` thuộc đường binding/formatting thích hợp trong MVC.
- `@RequestBody` JSON được xử lý bởi `HttpMessageConverter`, thường thông qua Jackson. Các annotation `@DateTimeFormat` không tự động thay thế cấu hình Java Time serializer/deserializer của JSON.
- `@JsonFormat` (Jackson) và `@DateTimeFormat` (Spring) giải quyết hai đường xử lý khác nhau; dùng theo đúng giao thức đầu vào.
- Một API nhận `"2026-07-01T19:00:00+07:00"` có offset đủ để xác định thời điểm, nhưng vẫn không có quy tắc múi giờ vùng cho một cuộc hẹn lặp trong tương lai.

Với ISO-8601, việc nhận `OffsetDateTime` hoặc `Instant` giúp tránh nhiều mơ hồ khi API cần truyền **một thời điểm đã biết**. Khi người dùng nhập **giờ hẹn tại một địa điểm**, cần `LocalDateTime` + `ZoneId` và xử lý DST rõ ràng.

### 7.4. Các điểm cần cẩn thận với Date và timezone mặc định

Với các kiểu legacy như `java.util.Date`, timezone áp dụng trong formatting có thể phụ thuộc annotation (ISO/style/pattern) và cấu hình Spring/JVM. Không suy ra hành vi của `@DateTimeFormat` trên `Date` rồi gán y hệt sang `LocalDateTime` hay `Instant`. Tránh dùng `Locale.setDefault(...)`, `TimeZone.setDefault(...)` hoặc sửa timezone toàn JVM trong handler của một request: chúng có thể ảnh hưởng tới request khác.

Nếu chỉ cần hiển thị `Instant` cho người dùng, cách tường minh là:

```java
DateTimeFormatter output = DateTimeFormatter
        .ofPattern("dd/MM/uuuu HH:mm XXX", locale)
        .withZone(presentationZone);
String text = output.format(confirmedInstant);
```

Ở đây `confirmedInstant` là thời điểm đã chốt, `presentationZone` là vùng hiển thị đã xác định, và `locale` là quy ước ngôn ngữ/hiển thị. Mặc dù pattern số đã cố định, `locale` vẫn được truyền để có thể thay đổi template chứa tên tháng/thứ sau này.

## 8. Tình huống thực tế: thiết kế dữ liệu và hợp đồng API

**Tình huống A — log giao dịch:** lưu `Instant` ở UTC và hiện cho người xem theo zone của họ. Một log tạo ở Việt Nam và xem ở California vẫn cùng một thời điểm. Nếu cần truy vấn theo “ngày làm việc” địa phương, tính ranh giới ngày dựa trên `ZoneId` phù hợp trước khi chuyển về `Instant`.

**Tình huống B — lịch họp được chốt một lần:** người tạo nhập ngày giờ địa phương và vùng IANA; backend xác định đúng offset (xử lý DST) rồi lưu `Instant`. Giữ thêm `ZoneId` để có thể hiển thị bối cảnh lịch hẹn hoặc cập nhật chính sách theo nhu cầu.

**Tình huống C — lịch lặp lúc 09:00 ở New York:** lưu quy tắc lặp, `LocalTime` và `America/New_York`; tính `Instant` cho từng ngày theo quy tắc thời gian của ngày đó. Không dùng offset `-05:00` cố định cho cả năm.

**Tình huống D — sinh nhật:** lưu `LocalDate`. Sinh nhật không tự nhiên biến thành một `Instant`; chỉ khi hệ thống cần gửi lời chúc “đúng 08:00 tại timezone của người dùng” mới xác định giờ/vùng cụ thể.

**Tình huống E — giao diện đa ngôn ngữ:** một người dùng ở New York xem giao diện tiếng Việt. Chọn `Locale=vi-VN` và `ZoneId=America/New_York`; thứ/tên tháng theo tiếng Việt còn giờ hiển thị vẫn đúng theo New York.

| Dữ liệu | Nên gửi/lưu | Vì sao |
| --- | --- | --- |
| Thời điểm tuyệt đối của sự kiện | `Instant` hoặc ISO UTC có `Z` | Tái hiện một điểm timeline |
| Thời điểm với offset phía client | `OffsetDateTime` | Giữ offset client cung cấp, xác định được instant |
| Lịch hẹn theo địa phương | `LocalDateTime` + `ZoneId` + chính sách DST | Không mơ hồ về vùng và quy tắc giờ |
| Lịch lặp theo giờ địa phương | `LocalTime`/`LocalDate` + `ZoneId` + recurrence rule | Bám giờ địa phương khi DST đổi |
| Tùy chọn văn hóa/UI | `Locale` (ví dụ BCP 47 tag `vi-VN`) | Phục vụ ngôn ngữ và format |
| Chênh lệch thực tại một thời điểm | `ZoneOffset` | Cung cấp ngữ cảnh khi chuyển đổi, không thay thế vùng |

## 9. Lỗi phổ biến và hướng sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dựa `vi-VN` để tự gán `Asia/Ho_Chi_Minh` | Sai với người Việt ở nước ngoài | Lưu locale và zone như hai lựa chọn độc lập |
| Lưu `UTC-5` thay cho `America/New_York` | Lệch lịch khi DST | Lưu `ZoneId` vùng cho quy tắc lịch tương lai |
| Dùng `LocalDateTime.now()` không chỉ định zone để lưu audit | Kết quả phụ thuộc máy chạy và không có instant rõ ràng | Dùng `Instant.now(clock)` hoặc `OffsetDateTime.now(ZoneOffset.UTC)` theo hợp đồng |
| Parse `2026-07-01T19:00:00` rồi gán `Z` | Giả định sai đó là 19:00 UTC | Chỉ chuyển sang UTC sau khi đã xác định zone/offset |
| Dùng `withZoneSameLocal` khi hiển thị cho người ở vùng khác | Đổi thời điểm cuộc họp | Dùng `withZoneSameInstant` |
| Bỏ qua gap/overlap DST | Lịch bị chỉnh giờ hoặc gặp hai thời điểm khả dĩ | Kiểm tra `getValidOffsets` và xử lý theo chính sách |
| Dùng `TimeZone.getTimeZone("typo")` để validate | ID sai có thể trở thành GMT mà không báo lỗi | Dùng `ZoneId.of(...)` và bắt `DateTimeException` |
| Coi `Accept-Language` là timezone | Gán sai địa điểm theo ngôn ngữ | Đọc timezone riêng từ cấu hình/người dùng |
| Áp `@DateTimeFormat` cho JSON rồi nghĩ đã thay Jackson | JSON vẫn theo cấu hình serialization khác | Tách cấu hình Spring formatting và JSON |
| Dùng pattern `YYYY-MM-dd` cho năm dương lịch | Có thể in sai năm gần giao thừa do `YYYY` là week-based-year | Dùng `uuuu-MM-dd`/ISO phù hợp |
| Chia sẻ `SimpleDateFormat` mutable xuyên thread | Format/parsing không an toàn | Dùng `DateTimeFormatter` immutable hoặc mỗi lần tạo formatter |
| Giữ `LocaleContextHolder` khi qua thread async | Locale/timezone mất hoặc rơi về default | Truyền giá trị cần thiết theo request/job |

Các kiểm thử đáng có:

1. Cùng `Instant` ở nhiều zone; assert các `Instant` sau chuyển đổi vẫn bằng nhau.
2. Một `ZoneId` ở mùa đông và mùa hè; assert offset có thể khác nhau.
3. `LocalDateTime` rơi vào gap và overlap DST; assert chính sách chấp nhận/từ chối minh bạch.
4. Locale khác nhau nhưng cùng zone; assert cách trình bày khác, thời điểm không đổi.
5. Zone ID không hợp lệ, field rỗng, format sai; kiểm tra `BindingResult` và HTTP 400.
6. Chuyển đổi qua JSON/form và qua các JDK/locale khác nhau nếu sản phẩm có hợp đồng định dạng chặt chẽ.
7. Lịch lặp qua ngày đổi DST; assert vẫn đúng giờ địa phương mong muốn.

## 10. Quy tắc ghi nhớ

- **`ZoneId` cho biết quy tắc thời gian của một vùng; `ZoneOffset` cho biết chênh lệch UTC tại một thời điểm; `Locale` cho biết quy ước ngôn ngữ/định dạng.**
- `Instant` đại diện thời điểm thực, `LocalDateTime` chưa đại diện thời điểm thực nếu thiếu zone/offset.
- Timezone và offset quyết định **giờ nào** tại địa phương; locale quyết định **viết ngày/giờ đó ra sao**.
- Trong Spring, `@DateTimeFormat` hỗ trợ parse/print field, còn xác định zone, giải quyết DST và chọn mô hình lưu trữ là quyết định nghiệp vụ.
- Chọn vùng IANA (ví dụ `America/New_York`) cho lịch địa phương cần quy tắc DST; giữ UTC/`Instant` cho một thời điểm đã chốt; chuyển đổi khi trình bày.
- Đừng đoán timezone từ locale hoặc từ server default: yêu cầu thông tin vùng rõ ràng khi nghiệp vụ cần chính xác.

### Tài liệu tham khảo

- Java 17 `ZonedDateTime` và xử lý gap/overlap: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html
- Java `ZoneId`, `ZoneOffset`, `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html
- Spring Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring MVC — Locale và Time Zone: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html
- Spring MVC — Type Conversion: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html
- Spring MVC — `@ModelAttribute` và binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
