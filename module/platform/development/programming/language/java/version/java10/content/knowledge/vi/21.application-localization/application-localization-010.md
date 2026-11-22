# Java 10 — Không đồng nhất `Locale` với múi giờ mặc định của tiến trình

## 1. Mục tiêu bài học

Trong ứng dụng đa ngôn ngữ, hai cấu hình thường xuất hiện cạnh nhau là **`Locale`** và **múi giờ**. Chúng có thể cùng được suy ra từ thiết lập hệ điều hành lúc khởi động JVM, nhưng **không phải một khái niệm** và **không có quan hệ tự động đồng bộ**.

Ví dụ: một người đọc tiếng Việt ở New York có thể chọn:

- `Locale.forLanguageTag("vi-VN")` để xem tên tháng, số và thông báo theo quy ước tiếng Việt;
- `ZoneId.of("America/New_York")` để xem sự kiện theo giờ địa phương New York;
- Trong khi máy chủ của ứng dụng chạy với `ZoneId.systemDefault()` là `UTC`.

Không có mâu thuẫn: ngôn ngữ/cách trình bày và vùng thời gian của sự kiện là những **trục cấu hình riêng**. Thay `Locale` không đồng nghĩa đổi timezone của JVM; thay timezone của JVM không có nghĩa đổi ngôn ngữ người dùng.

Sau bài này, bạn sẽ:

1. Phân biệt `Locale`, `Locale.Category.FORMAT`/`DISPLAY`, `ZoneId`, `TimeZone` và `Instant`.
2. Hiểu cách `Locale.getDefault(...)` khác `ZoneId.systemDefault()` và `TimeZone.getDefault()`.
3. Trình bày một `Instant` tại nhiều múi giờ mà **không sửa thời điểm gốc**.
4. Dùng `DateTimeFormatter` với **`Locale` và `ZoneId` tường minh**.
5. Tránh sửa cấu hình JVM toàn cục bằng `Locale.setDefault`/`TimeZone.setDefault` trong xử lý request nhiều người dùng.
6. Hiểu tình huống đặc biệt Java 10: Unicode locale key `tz` và `DateTimeFormatter.localizedBy(Locale)`, nhưng không nhầm nó với việc đổi timezone toàn tiến trình.
7. Xử lý giờ mùa hè (DST), thời điểm không tồn tại và thời điểm trùng trong `LocalDateTime`.
8. Kiểm thử độc lập với timezone/locale của máy phát triển hay CI.

**Giới hạn kiến thức:** sử dụng các API còn phù hợp trên Java hiện đại, ưu tiên `java.time` cho thời gian. `java.util.TimeZone` được nhắc đến vì nó vẫn là cầu nối chính thức của **múi giờ mặc định JVM** và tương tác với `ZoneId.systemDefault()`, không vì cổ vũ thiết kế ứng dụng mới dựa trên lịch sử `Date`/`Calendar`.

## 2. Bảng phân biệt nhanh

| Khái niệm/API | Đại diện cho điều gì? | Ví dụ | Có tự đổi timezone của JVM không? |
|---|---|---|---|
| `Locale` | Ngôn ngữ và quy ước quốc tế hóa khi hiển thị/parse | `vi-VN`, `en-US`, `fr-FR` | **Không** |
| `Locale.Category.FORMAT` | Locale mặc định cho định dạng ngày, số, tiền tệ... ở API sử dụng category này | `Locale.FRANCE` | **Không** |
| `Locale.Category.DISPLAY` | Locale mặc định cho tên hiển thị/ngôn ngữ của thông tin locale ở API phù hợp | `Locale.JAPAN` | **Không** |
| `ZoneId` | Danh tính múi giờ và quy tắc chuyển offset theo thời điểm | `Asia/Tokyo`, `Europe/Paris` | **Không**, khi chỉ tạo bằng `ZoneId.of` |
| `ZoneOffset` | Một độ lệch UTC cố định | `+07:00` | **Không** |
| `TimeZone` | API timezone trong `java.util`, có thể lấy/đặt default của JVM | `TimeZone.getDefault()` | Chỉ `setDefault(...)` mới thay default |
| `ZoneId.systemDefault()` | Truy vấn timezone mặc định JVM **tại thời điểm gọi** | `UTC` trên một server được cấu hình UTC | Là phép đọc, **không** sửa |
| `Instant` | Một thời điểm tuyệt đối trên timeline UTC | `2024-01-15T12:00:00Z` | Không chứa Locale/timezone |
| `LocalDateTime` | Ngày + giờ “trên đồng hồ”, **chưa có zone/offset** | `2024-01-15T21:00` | Không đủ để xác định một `Instant` duy nhất |
| `ZonedDateTime` | Ngày/giờ với `ZoneId` và quy tắc offset | `2024-01-15T21:00+09:00[Asia/Tokyo]` | Không tự sửa default |
| `DateTimeFormatter` | Quy tắc biến đổi dữ liệu thời gian thành văn bản và ngược lại | `ofPattern(...).withLocale(...).withZone(...)` | Không tự sửa default |

**Quy tắc một câu:** `Locale` quyết định **trình bày như thế nào**; `ZoneId` quyết định **mốc giờ địa phương là bao nhiêu** tại một thời điểm; `Instant` quyết định **đó là thời điểm nào**.

### 2.1. Cùng vùng quốc gia không có nghĩa cùng timezone

`Locale.US` không tự chỉ ra `America/New_York` hay `America/Los_Angeles`. Hoa Kỳ có nhiều múi giờ; nhiều vùng khác cũng vậy. Ngược lại, `Locale.forLanguageTag("vi-VN")` không bắt buộc bạn phải hiển thị mọi sự kiện bằng múi giờ Việt Nam.

**Không ánh xạ `locale.getCountry()` trực tiếp sang một `ZoneId` duy nhất** trừ khi nghiệp vụ có dữ liệu cấu hình vùng–múi giờ thật sự rõ ràng và xử lý được các nước có nhiều zone. Khi người dùng chọn timezone, lưu ID IANA/region riêng.

## 3. Hai loại “mặc định” hoàn toàn khác nhau

### 3.1. `Locale.getDefault()` và các category

`java.util.Locale` cung cấp:

```java
Locale current = Locale.getDefault();
Locale formatLocale =
        Locale.getDefault(Locale.Category.FORMAT);
Locale displayLocale =
        Locale.getDefault(Locale.Category.DISPLAY);
```

Đây là **mảnh code trong một phương thức**, cần import `java.util.Locale`.

- `Locale.getDefault()` lấy default locale chung của JVM.
- `Locale.Category.FORMAT` dùng khi các API chọn locale để định dạng theo giá trị địa phương (số, ngày, tiền...).
- `Locale.Category.DISPLAY` dành cho một số tên/nhãn hiển thị.
- Các category này **có thể khác nhau**.
- Việc chọn locale mặc định nào còn tùy API và cách nó sử dụng category.

Các locale mặc định có thể được thiết lập từ môi trường/thuộc tính hệ thống lúc khởi động. Không suy ra timezone chỉ vì biết `Locale.getDefault()`.

### 3.2. `TimeZone.getDefault()` và `ZoneId.systemDefault()`

`java.util.TimeZone` có:

```java
TimeZone legacyDefault = TimeZone.getDefault();
ZoneId modernDefault = ZoneId.systemDefault();
```

Đây là mảnh code cần import `java.util.TimeZone` và `java.time.ZoneId`. Tên biến `legacyDefault` chỉ để phân biệt kiểu API; `TimeZone` vẫn được JDK hỗ trợ.

Theo Javadoc, `ZoneId.systemDefault()` tra default qua `TimeZone.getDefault()` rồi chuyển thành `ZoneId`. Vì thế:

- Đổi **default TimeZone** bằng `TimeZone.setDefault(...)` có thể làm kết quả **những lần gọi sau** của `ZoneId.systemDefault()` thay đổi.
- Đổi **default Locale** bằng `Locale.setDefault(...)` **không** khiến `ZoneId.systemDefault()` chọn múi giờ mới.
- Gọi `ZoneId.of("Europe/Paris")` chỉ tạo đối tượng zone, **không** thay default.
- Biến `ZoneId captured = ZoneId.systemDefault()` là một **giá trị đã được lấy**. Nếu default đổi sau đó, biến `captured` không phải “liên kết sống” tự cập nhật.
- Vì timezone default là trạng thái **toàn JVM**, thao tác sửa default là một thay đổi có phạm vi rất rộng.

### 3.3. Hai mặc định có thể cùng xuất phát từ hệ điều hành, nhưng không bị ràng buộc

Một máy làm việc có thể được cấu hình tiếng Việt và timezone `Asia/Ho_Chi_Minh`. Khi JVM khởi chạy, cả `Locale` và `TimeZone` có thể được nhận diện từ môi trường đó. Nhưng ứng dụng, container, process flags hoặc code khác có thể cấu hình **một bên mà không đụng bên kia**.

Ví dụ một JVM được khởi động với:

```bash
java -Duser.language=fr -Duser.country=FR -Duser.timezone=UTC Main
```

Đây là cú pháp minh họa cấu hình khởi động, với `Main` là class đã được biên dịch. Locale có thể là `fr-FR`, trong khi timezone mặc định là `UTC`. Các properties khởi động này được JDK hỗ trợ nhưng cấu hình thực tế còn tùy môi trường và các locale category; đối với xử lý nghiệp vụ, **truyền đối tượng Locale và ZoneId tường minh** thường đáng tin cậy hơn.

## 4. Ví dụ chạy độc lập 1 — thay Locale không đổi timezone

Tệp **`LocaleZoneSeparationDemo.java`**:

```java
import java.time.ZoneId;
import java.util.Locale;
import java.util.TimeZone;

public class LocaleZoneSeparationDemo {
    public static void main(String[] args) {
        Locale oldFormat =
                Locale.getDefault(Locale.Category.FORMAT);
        Locale oldDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);
        TimeZone oldZone = TimeZone.getDefault();

        try {
            TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
            Locale.setDefault(Locale.Category.FORMAT, Locale.FRANCE);
            Locale.setDefault(Locale.Category.DISPLAY, Locale.JAPAN);

            System.out.println("formatLocale="
                    + Locale.getDefault(
                        Locale.Category.FORMAT).toLanguageTag());
            System.out.println("displayLocale="
                    + Locale.getDefault(
                        Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("zoneAfterLocale="
                    + ZoneId.systemDefault().getId());

            Locale.setDefault(Locale.Category.FORMAT, Locale.US);
            System.out.println("zoneAfterFormatChange="
                    + ZoneId.systemDefault().getId());

            TimeZone.setDefault(
                    TimeZone.getTimeZone("Asia/Tokyo"));
            System.out.println("zoneAfterTimeZoneChange="
                    + ZoneId.systemDefault().getId());
            System.out.println("formatAfterZoneChange="
                    + Locale.getDefault(
                        Locale.Category.FORMAT).toLanguageTag());
        } finally {
            TimeZone.setDefault(oldZone);
            Locale.setDefault(Locale.Category.FORMAT, oldFormat);
            Locale.setDefault(Locale.Category.DISPLAY, oldDisplay);
        }
    }
}
```

Chạy trong **process thử nghiệm riêng** bằng JDK hỗ trợ `--release 10`:

```bash
javac --release 10 LocaleZoneSeparationDemo.java
java LocaleZoneSeparationDemo
```

**Stdout đã chạy kiểm chứng:**

```text
formatLocale=fr-FR
displayLocale=ja-JP
zoneAfterLocale=UTC
zoneAfterFormatChange=UTC
zoneAfterTimeZoneChange=Asia/Tokyo
formatAfterZoneChange=en-US
```

### 4.1. Diễn giải

1. `FORMAT=fr-FR` và `DISPLAY=ja-JP` cùng tồn tại; không cần bằng nhau.
2. Sau khi đặt Locale FORMAT/DISPLAY, `ZoneId.systemDefault()` vẫn là `UTC`.
3. Đổi FORMAT Locale từ Pháp sang Mỹ vẫn giữ default zone `UTC`.
4. Khi **cố ý** gọi `TimeZone.setDefault(Asia/Tokyo)`, lần truy vấn tiếp theo bằng `ZoneId.systemDefault()` cho `Asia/Tokyo`.
5. Locale FORMAT vẫn là `en-US` sau khi đổi timezone.

**Cảnh báo quan trọng:** `Locale.setDefault(...)` và `TimeZone.setDefault(...)` là thao tác **global mutation**. Chương trình trên chỉ dành cho **một process kiểm thử độc lập**, dùng `try/finally` để khôi phục giá trị cũ. Không sao chép chiến lược này để đổi ngôn ngữ/múi giờ theo từng HTTP request trong một dịch vụ nhiều người dùng; khôi phục trong `finally` **không** giúp loại bỏ race condition khi nhiều thread cùng xử lý.

## 5. Những kiểu thời gian nên hiểu rõ

### 5.1. `Instant` — thời điểm tuyệt đối

`Instant.parse("2024-01-15T12:00:00Z")` biểu diễn một thời điểm trên timeline UTC. Nó không chứa Locale hay thông tin “người dùng đang ở đâu”.

```java
Instant event = Instant.parse("2024-01-15T12:00:00Z");
```

Đây là mảnh code cần import `java.time.Instant`. Cùng một `Instant` có thể hiển thị:
- `12:00` tại `UTC`;
- `21:00` tại `Asia/Tokyo` vào ngày này;
- `13:00` tại `Europe/Paris` vào ngày này, vì Paris dùng UTC+01:00 trong tháng 1 năm 2024.

**Không có ba sự kiện khác nhau**. Đây là **ba cách nhìn cùng một thời điểm**.

### 5.2. `ZoneId` — quy tắc theo vùng và lịch sử

`ZoneId.of("America/New_York")` đại diện một danh tính múi giờ với lịch sử và quy tắc đổi offset, gồm các chuyển tiếp daylight-saving time (DST) nếu vùng có. `ZoneId.of("Asia/Tokyo")` có quy tắc khác.

Không nên thay các vùng có quy tắc DST bằng một offset cố định như `ZoneOffset.of("-05:00")` cho mọi thời điểm. New York có thời gian dùng UTC−05 và thời gian dùng UTC−04. Một offset cố định sẽ sai ở những giai đoạn còn lại.

### 5.3. `LocalDateTime` — không đủ để biết thời điểm nào

`LocalDateTime.of(2024, 11, 3, 1, 30)` mô tả mặt đồng hồ là 01:30, **chưa có múi giờ**. Ở New York ngày đó có chuyển đổi DST nên 01:30 xảy ra **hai lần** với hai offset khác nhau.

Đối với lịch họp hoặc lịch làm việc, cần biết zone và chính sách xử lý giờ trùng/gap. Đối với timestamp của sự kiện đã xảy ra, dùng `Instant` hoặc một biểu diễn có offset/zone phù hợp.

### 5.4. `ZonedDateTime` — kết hợp local date-time và zone

`instant.atZone(ZoneId.of("Asia/Tokyo"))` tạo một `ZonedDateTime` biểu thị cùng `Instant` tại Tokyo. Gọi `toInstant()` trả lại chính thời điểm ban đầu.

Những phép chuyển đổi này **không** cần `Locale.setDefault(...)` hoặc `TimeZone.setDefault(...)`; chúng sử dụng zone được truyền vào.

## 6. Cách đúng để render một thời điểm cho từng người dùng

Giả sử một hệ thống nhận:

- Event timestamp ở dạng `Instant`;
- Ngôn ngữ/ngữ cảnh trình bày của người xem ở dạng `Locale`;
- Múi giờ người xem chọn ở dạng `ZoneId`.

Đường đi tốt:

```text
Instant gốc
    |
    +---- ZoneId của người xem ----> giờ/ngày địa phương
    |
    +---- Locale của người xem ----> tên tháng, kiểu ngày, chữ số
    |
    +---- DateTimeFormatter ------------> chuỗi hiển thị
```

Ví dụ mảnh code trong một method:

```java
static String renderForUser(
        Instant occurredAt,
        Locale locale,
        ZoneId viewerZone) {

    DateTimeFormatter formatter =
            DateTimeFormatter.ofLocalizedDateTime(
                    FormatStyle.MEDIUM)
            .withLocale(locale)
            .withZone(viewerZone);

    return formatter.format(occurredAt);
}
```

Mảnh này cần import `Instant`, `Locale`, `ZoneId`, `DateTimeFormatter` và `FormatStyle`. Phương thức không gọi `systemDefault()`, không sửa state toàn JVM; cùng một lúc có thể render cho nhiều người xem khác nhau.

**Ghi chú:** các pattern định dạng localized từ CLDR có thể thay đổi giữa JDK/locale provider, nên **không hard-code stdout chuỗi tháng/ngày** cho ví dụ dùng localized pattern nếu không cố định runtime. Lệnh `withZone(viewerZone)` xác định timezone mà formatter dùng khi render một `Instant`.

### 6.1. Phân biệt `withLocale` và `withZone`

`DateTimeFormatter.withLocale(locale)` tạo formatter mới có locale để tra cứu văn bản/pattern theo vùng, nhưng **không tự động đặt timezone từ country của locale**.

`DateTimeFormatter.withZone(zone)` tạo formatter mới có zone override; nếu format một `Instant`, nó chuyển mốc thời gian sang giờ địa phương tương ứng.

Để nhìn rõ hai trục, có thể tách bước:

```java
DateTimeFormatter base =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm");
DateTimeFormatter userFormatter =
        base.withLocale(Locale.FRANCE)
            .withZone(ZoneId.of("Asia/Tokyo"));
```

Đây là mảnh code cần các import `java.time.format.DateTimeFormatter`, `java.util.Locale`, `java.time.ZoneId`.

Không có điều gì sai khi **Locale.FRANCE** đi cùng **Asia/Tokyo**: một người sử dụng tiếng Pháp vẫn có thể ở Tokyo hoặc xem một sự kiện diễn ra tại Tokyo.

## 7. Chương trình chạy độc lập 2 — một `Instant`, nhiều giờ hiển thị

Tệp **`InstantRenderingDemo.java`**:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class InstantRenderingDemo {
    public static void main(String[] args) {
        Instant fixed = Instant.parse("2024-01-15T12:00:00Z");
        ZoneId utc = ZoneId.of("UTC");
        ZoneId tokyo = ZoneId.of("Asia/Tokyo");

        var pattern =
                DateTimeFormatter.ofPattern(
                    "uuuu-MM-dd HH:mm", Locale.US);

        System.out.println("utcClock="
                + pattern.withZone(utc).format(fixed));
        System.out.println("tokyoClock="
                + pattern.withZone(tokyo).format(fixed));
        System.out.println("sameInstant="
                + fixed.equals(fixed.atZone(tokyo).toInstant()));

        var french = pattern.withLocale(Locale.FRANCE)
                .withZone(tokyo);

        System.out.println("frenchLocale="
                + french.getLocale().toLanguageTag());
        System.out.println("frenchZone="
                + french.getZone().getId());
        System.out.println("numericClockSame="
                + french.format(fixed).equals(
                    pattern.withZone(tokyo).format(fixed)));

        ZoneId ny = ZoneId.of("America/New_York");
        LocalDateTime springGap =
                LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime autumnOverlap =
                LocalDateTime.of(2024, 11, 3, 1, 30);

        System.out.println("springValidOffsets="
                + ny.getRules().getValidOffsets(springGap).size());
        System.out.println("springResolved="
                + springGap.atZone(ny).toLocalDateTime());
        System.out.println("autumnValidOffsets="
                + ny.getRules().getValidOffsets(
                    autumnOverlap).size());
    }
}
```

Lệnh:

```bash
javac --release 10 InstantRenderingDemo.java
java InstantRenderingDemo
```

**Stdout đã kiểm chứng với dữ liệu múi giờ IANA cho các mốc năm 2024:**

```text
utcClock=2024-01-15 12:00
tokyoClock=2024-01-15 21:00
sameInstant=true
frenchLocale=fr-FR
frenchZone=Asia/Tokyo
numericClockSame=true
springValidOffsets=0
springResolved=2024-03-10T03:30
autumnValidOffsets=2
```

### 7.1. Vì sao `numericClockSame=true`?

`french` là formatter cho `Locale.FRANCE` nhưng **ZoneId Asia/Tokyo**. Bởi pattern trong demo chỉ chứa các con số thuộc lịch ISO, đổi Locale.US sang Locale.FRANCE không thay giá trị giờ/ngày của cùng một `Instant` tại Tokyo. Nếu pattern có **tên tháng/ngày trong tuần bằng chữ**, Locale có thể tạo chuỗi khác.

Không được suy rằng `Locale` luôn “không có tác động” đến mọi formatter. Ý nghĩa đúng là **Locale không thay thế ZoneId**, và đối với pattern numeric đã chọn, cùng zone nên kết quả chuỗi giống nhau.

### 7.2. Vì sao cùng thời điểm mà `utcClock` và `tokyoClock` khác?

`Instant` cố định ở 12:00Z; `withZone(UTC)` render 12:00, `withZone(Asia/Tokyo)` render 21:00 vào ngày đó. `sameInstant=true` chứng minh dữ liệu thời điểm tuyệt đối không thay đổi sau chuyển đổi vùng.

Đây là kỹ thuật đúng khi một hệ thống cần hiện thời gian của cùng sự kiện trên trang người dùng ở nhiều vùng.

### 7.3. Những dòng DST mang ý nghĩa gì?

- `springValidOffsets=0`: ở New York, `2024-03-10 02:30` **không tồn tại** theo đồng hồ địa phương vì bước chuyển sang DST.
- `springResolved=2024-03-10T03:30`: `LocalDateTime.atZone(...)` mặc định đẩy giờ trong gap tới thời điểm hợp lệ sau gap theo độ dài chuyển tiếp.
- `autumnValidOffsets=2`: ở New York, `2024-11-03 01:30` xảy ra **hai lần**, tương ứng hai UTC offsets.

DST là vấn đề của **ZoneRules/ZoneId**, **không** của `Locale.US` hay `Locale.FRANCE`.

## 8. Phân biệt `ZoneId` và `ZoneOffset`

### 8.1. `ZoneOffset` là offset cố định

`ZoneOffset.of("+07:00")` mô tả một độ lệch UTC cố định. Nó không chứa tên vùng hay lịch sử thay đổi giờ.

### 8.2. `ZoneId` có thể mang quy tắc vùng

`ZoneId.of("Europe/Paris")` có những quy tắc offset theo lịch sử và ngày trong năm. Vào một thời điểm có thể là `+01:00`, thời điểm khác là `+02:00`.

Đoạn minh họa trong method:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
Instant winter =
        Instant.parse("2024-01-15T12:00:00Z");
Instant summer =
        Instant.parse("2024-07-15T12:00:00Z");

System.out.println(
        paris.getRules().getOffset(winter)); // +01:00
System.out.println(
        paris.getRules().getOffset(summer)); // +02:00
```

Mảnh code cần import `ZoneId` và `Instant`. Dữ liệu IANA áp dụng trong năm 2024 cho Paris cho kết quả như chú thích.

**Không dùng offset đã lấy tại một thời điểm để dự đoán offset của một thời điểm khác** ở vùng có DST. Nếu hệ thống lập lịch tương lai, hãy lưu ID zone và dùng tzdb; các quy tắc pháp lý tương lai có thể thay đổi theo cập nhật tzdb.

### 8.3. Mã quốc gia không xác định một offset duy nhất

`Locale.getCountry()` chỉ cho biết region cơ sở của Locale, **không** cho một `ZoneOffset`. Nhiều nước có nhiều múi giờ, và một vùng đơn lẻ cũng có offset thay đổi theo DST. Thiết kế kiểu:

```java
// Không phải cách ánh xạ tổng quát hợp lệ:
String country = locale.getCountry();
// ZoneId zone = guessZoneFromCountry(country);
```

là dấu hiệu cần xem lại yêu cầu. Nếu cần timezone người dùng, lưu `ZoneId` độc lập, cho người dùng chọn hoặc lấy từ nguồn tin cậy có ngữ cảnh địa lý đủ chính xác.

## 9. Java 10 có khóa Unicode `tz`, nhưng `tz` không phải timezone mặc định của JVM

Java 10 giới thiệu **JEP 314 — Additional Unicode Language-Tag Extensions**, mở rộng các locale-sensitive APIs để hiểu thêm các Unicode extension keys:

- `cu`: currency;
- `fw`: first day of week;
- `rg`: region override;
- `tz`: timezone preference.

**Điểm rất dễ gây nhầm:** một `Locale` chứa `tz` **vẫn không tự động thay `TimeZone.getDefault()` hoặc `ZoneId.systemDefault()`**. Thẻ `tz` là một **preference bên trong Locale**; chỉ một số API có hỗ trợ mới đọc nó.

Ví dụ:

```java
Locale locale =
        Locale.forLanguageTag("en-US-u-tz-jptyo");
```

Ở đây `jptyo` là Unicode BCP 47 timezone type được ánh xạ đến `Asia/Tokyo` trong dữ liệu locale tương ứng. Nó **không** phải chuỗi IANA ID `"Asia/Tokyo"` được đặt trực tiếp sau `-tz-`. Cú pháp và các ánh xạ của Unicode time zone type được định nghĩa bởi Unicode/CLDR.

### 9.1. `DateTimeFormatter.localizedBy(Locale)` có từ Java 10

Theo Javadoc, `DateTimeFormatter.localizedBy(locale)` (Since: **10**) tạo formatter mới với các thiết lập localized phù hợp, có thể tính đến Unicode extensions như `ca`, `nu`, `rg` và **`tz`**. Trong trường hợp `tz` được hỗ trợ, **formatter** có thể nhận zone tương ứng.

Đây là khác biệt quan trọng với:

- `formatter.withLocale(locale)`: đổi Locale sử dụng cho văn bản/pattern; **không** tự biến Unicode timezone preference thành `formatter.getZone()`.
- `formatter.localizedBy(locale)`: có thể áp dụng zone từ Unicode `tz` trong Locale, **chỉ lên formatter mới**.
- `formatter.withZone(zoneId)`: đặt zone tường minh, thường rõ nhất khi ứng dụng đã biết chính xác `ZoneId` của người dùng hoặc sự kiện.

Không được suy từ việc `localizedBy(...)` tạo formatter có zone rằng **múi giờ mặc định JVM cũng bị đổi**. Đây chỉ là cấu hình của **một formatter**.

### 9.2. `rg` không phải `tz`

`en-US-u-rg-gbzzzz` yêu cầu dùng dữ liệu khu vực của GB cho những mặc định phù hợp, như quy tắc tuần và tiền tệ. Nó **không** đồng nghĩa chọn `Europe/London` làm timezone mặc định toàn process.

`en-US-u-tz-jptyo` yêu cầu timezone preference trong các API hỗ trợ `tz`. Nó **không** đổi `Locale.getCountry()` sang JP, cũng không thay `ZoneId.systemDefault()`.

Trong hệ thống dữ liệu quan trọng, nên truyền **ZoneId tường minh** thay vì suy ra giờ địa phương từ một extension bên trong Locale vốn có thể không được các thành phần thư viện xử lý đồng nhất.

## 10. Chương trình chạy độc lập 3 — `localizedBy` khác `withLocale`

Tệp **`LocaleTzExtensionDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class LocaleTzExtensionDemo {
    public static void main(String[] args) {
        ZoneId defaultBefore = ZoneId.systemDefault();

        Locale locale =
                Locale.forLanguageTag("en-US-u-tz-jptyo");
        var base = DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm");
        var withLocale = base.withLocale(locale);
        var localized = base.localizedBy(locale);
        Instant value =
                Instant.parse("2024-01-15T12:00:00Z");

        System.out.println("tzKeyword="
                + locale.getUnicodeLocaleType("tz"));
        System.out.println("baseZoneNull="
                + (base.getZone() == null));
        System.out.println("withLocaleZoneNull="
                + (withLocale.getZone() == null));
        System.out.println("localizedZone="
                + localized.getZone().getId());
        System.out.println("localizedClock="
                + localized.format(value));
        System.out.println("systemDefaultUnchanged="
                + defaultBefore.equals(ZoneId.systemDefault()));
    }
}
```

```bash
javac --release 10 LocaleTzExtensionDemo.java
java LocaleTzExtensionDemo
```

**Stdout đã kiểm chứng với OpenJDK có ánh xạ Unicode `jptyo` → `Asia/Tokyo`:**

```text
tzKeyword=jptyo
baseZoneNull=true
withLocaleZoneNull=true
localizedZone=Asia/Tokyo
localizedClock=2024-01-15 21:00
systemDefaultUnchanged=true
```

### 10.1. Vì sao `localizedZone=Asia/Tokyo`?

`DateTimeFormatter.localizedBy(Locale)` đọc Unicode timezone preference từ `locale` và tạo **một formatter mới** có zone phù hợp. Khi format `Instant` 12:00Z, giờ địa phương là 21:00 tại Tokyo.

### 10.2. Tại sao `withLocaleZoneNull=true`?

`withLocale(locale)` chỉ thay locale được formatter sử dụng cho text/pattern; nó **không tự áp dụng zone từ Unicode `tz`** theo cùng cách `localizedBy`. Vì formatter cơ sở chưa được gán zone, `getZone()` vẫn là `null`.

Điểm này có thể kiểm thử ổn định về cấu trúc API; riêng ánh xạ `jptyo` cần runtime có dữ liệu locale tương ứng.

### 10.3. Tại sao default JVM không đổi?

`localizedBy` không gọi `TimeZone.setDefault(...)`. Nó không thay thông số chung cho các request khác, cũng không thay `ZoneId.systemDefault()`.

**Thực hành khuyến nghị:** khi nghiệp vụ đã lưu `ZoneId.of("Asia/Tokyo")`, dùng `formatter.withZone(zone)` trực tiếp. `tz` vẫn hữu ích để hiểu dữ liệu BCP 47, nhưng không nên để nó thay thế trường múi giờ chuyên biệt nếu hệ thống cần tính chính xác hoặc kiểm soát version của timezone rules.

## 11. Vấn đề thường gặp khi dùng API phụ thuộc default

### 11.1. `LocalDateTime.now()` không phải mốc thời gian tuyệt đối

`LocalDateTime.now()` lấy ngày/giờ từ system clock và **múi giờ mặc định**, nhưng kết quả là một `LocalDateTime` **không lưu ZoneId**. Đem kết quả đó lưu làm timestamp sự kiện có thể khiến bên đọc không biết nó thuộc timezone nào.

Đối với timestamp của sự kiện đã xảy ra, thường hợp lý hơn:

```java
Instant occurredAt = Instant.now();
```

Sau đó, khi cần render:

```java
String display = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm")
        .withZone(viewerZone)
        .format(occurredAt);
```

Đây là mảnh code giả định `viewerZone` là `ZoneId` được cung cấp riêng. `Instant.now()` lấy thời điểm từ clock, không tự sinh ra một “giờ New York” hay “giờ Việt Nam”.

Trong code cần test determinism, tiêm `Clock` vào service thay vì gọi `Instant.now()` trực tiếp, ví dụ dùng `Clock.fixed(...)` cho unit tests.

### 11.2. `ZonedDateTime.now()` mặc định dùng zone JVM

`ZonedDateTime.now()` khi không truyền zone sẽ sử dụng system default. Điều này là API hợp lệ, không bị deprecated. Tuy nhiên trong server đa người dùng, nó có thể không đúng zone của người đang xem.

Nên dùng:

```java
ZonedDateTime viewerNow =
        ZonedDateTime.now(viewerZone);
```

Mảnh code cần import `ZonedDateTime` và biến `viewerZone`. Ở service có `Clock` được inject, có thể dùng `ZonedDateTime.now(clock)`, trong đó clock đã định nghĩa zone phù hợp.

### 11.3. `DateTimeFormatter` có thể dùng FORMAT locale mặc định

Một số factory như `DateTimeFormatter.ofLocalizedDate(...)` sử dụng `Locale.getDefault(Locale.Category.FORMAT)` khi tạo formatter. Do đó, nếu dự án cần output cho mỗi người dùng, đừng dựa vào locale của server.

Nên truyền:

```java
DateTimeFormatter formatter =
        DateTimeFormatter
            .ofLocalizedDateTime(FormatStyle.MEDIUM)
            .withLocale(viewerLocale)
            .withZone(viewerZone);
```

Mảnh code cần `viewerLocale` kiểu `Locale`, `viewerZone` kiểu `ZoneId`, cùng import `DateTimeFormatter` và `FormatStyle`. Lúc này formatter thể hiện hai lựa chọn **độc lập**.

## 12. Global defaults trong ứng dụng nhiều thread

Hai lời gọi có thể thay đổi cấu hình **ở phạm vi JVM**:

```java
Locale.setDefault(Locale.Category.FORMAT, Locale.FRANCE);
TimeZone.setDefault(TimeZone.getTimeZone("Europe/Paris"));
```

Chúng có chỗ dùng trong tool thử nghiệm độc lập, chương trình nhỏ hoặc thiết lập có chủ đích từ rất sớm lúc khởi tạo process. Nhưng nếu sử dụng để phục vụ **từng request**, chúng gây rủi ro:

1. Request A đặt locale tiếng Pháp và zone Paris.
2. Request B đặt locale tiếng Nhật và zone Tokyo.
3. Request A tiếp tục format sau khi B đã đổi global defaults.
4. Request A có thể vô tình sử dụng thiết lập của B.

Ngay cả code dạng:

```java
Locale old = Locale.getDefault();
try {
    Locale.setDefault(Locale.FRANCE);
    // xử lý yêu cầu...
} finally {
    Locale.setDefault(old);
}
```

là **chống mẫu trong server song song**. `finally` chỉ khôi phục global state ở cuối đường đi của một request, không ngăn request khác can thiệp giữa chừng. Tương tự với `TimeZone.setDefault(...)`.

**Mẫu an toàn hơn:**
- Nhận `Locale` từ user preferences, HTTP `Accept-Language` (sau khi validate), hoặc cài đặt UI;
- Nhận `ZoneId` từ cài đặt riêng, hoặc nguồn tin cậy có đủ thông tin;
- Lưu chúng trong request context/đối tượng tham số, không ghi vào global JVM;
- Tạo formatter immutable bằng `withLocale(...)` và `withZone(...)`;
- Dùng `Instant` cho timestamp cần biểu diễn nhất quán;
- Nếu phải ghi thông tin timezone vào dữ liệu, lưu ZoneId cùng timestamp theo yêu cầu (cần phân biệt giờ người dùng nhập với sự kiện thực tế).

### 12.1. Không hard-code một timezone cho mọi user

Một container có thể chạy UTC; điều đó **có lợi** cho timestamp máy chủ. Nhưng nếu luôn gọi `ZoneId.systemDefault()` để render lịch người dùng, mọi người sẽ thấy giờ theo UTC chứ không theo zone họ chọn.

Quy ước thực tế thường là:
- **Server clock / event timestamp:** `Instant`;
- **Lưu lịch theo múi giờ người dùng:** `LocalDateTime` + `ZoneId` + chính sách DST rõ;
- **Hiển thị:** `Instant` + `ZoneId` + `Locale`;
- **Trao đổi máy:** ISO 8601 và timezone/offset đúng contract, không dùng format localized tự động làm schema.

## 13. DST: sự khác biệt không thể giải quyết chỉ bằng Locale

### 13.1. Giờ “không tồn tại” (gap)

Tại một số vùng, khi bắt đầu daylight-saving time, đồng hồ được chỉnh tiến. Ví dụ New York ngày 10/03/2024:

```text
01:59:59 -> 03:00:00
            ^
02:30 không tồn tại
```

`LocalDateTime.of(2024, 3, 10, 2, 30)` tự nó vẫn là một giá trị Java hợp lệ vì không chứa zone. Nhưng khi gắn `America/New_York`, `ZoneRules.getValidOffsets` cho **0 offset hợp lệ** tại local time này.

`LocalDateTime.atZone(zone)` có quy tắc mặc định giúp điều chỉnh vào giờ hợp lệ sau gap. Với một lịch đặt hẹn nghiêm ngặt, việc tự động đẩy 02:30 thành 03:30 có thể **không đúng ý định người dùng**. Hãy xác định policy: từ chối, hỏi lại, hoặc chủ động điều chỉnh và thông báo.

### 13.2. Giờ “xuất hiện hai lần” (overlap)

Khi kết thúc DST, một khoảng giờ địa phương được lặp. New York ngày 03/11/2024 lúc 01:30 có **hai offset hợp lệ**.

Cần xác định lịch hẹn là **lần 01:30 đầu** hay **lần 01:30 sau**. Nếu không, chỉ `LocalDateTime` + `Locale.US` là thiếu thông tin; ngay cả thêm `ZoneId` mà không chọn policy overlap vẫn cần làm rõ nếu có hai khả năng.

Có thể kiểm tra:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime ambiguous =
        LocalDateTime.of(2024, 11, 3, 1, 30);
int candidates =
        ny.getRules().getValidOffsets(ambiguous).size();
// candidates = 2
```

Đây là mảnh code trong method, cần `ZoneId` và `LocalDateTime`. Có thể chọn offset cụ thể từ danh sách được trả về theo quy tắc sản phẩm, rồi dùng API như `ZonedDateTime.ofLocal(...)` nếu cần xác lập cách giải quyết rõ ràng.

### 13.3. Vì sao không dùng `ZoneOffset.of("-05:00")` để tránh DST?

Offset cố định không biết lúc nào New York chuyển sang `-04:00`. Dùng offset để thay IANA zone khiến lịch tương lai bị sai khi offset thực tế thay đổi. Chỉ dùng offset cố định khi đó đúng là contract nguồn dữ liệu (ví dụ một timestamp đã có offset rõ ràng).

**Locale không chứa ZoneRules.** Vì thế không có thao tác nào kiểu `Locale.setDefault(Locale.US)` giúp quyết định đúng thời gian trong DST gap/overlap.

## 14. `TimeZone` vẫn được hỗ trợ nhưng nên biết sự khác biệt với `ZoneId`

`java.util.TimeZone` là API còn tồn tại để tương tác với Java truyền thống và default timezone JVM. `ZoneId` là API hiện đại trong `java.time`, thường phù hợp hơn cho code ngày/giờ mới.

Bridge:

```java
TimeZone oldApi = TimeZone.getTimeZone(
        ZoneId.of("Europe/Paris"));

ZoneId newApiZone = oldApi.toZoneId();
```

Mảnh code trong method cần `TimeZone` và `ZoneId`. Đây là chuyển đổi giữa hai mô hình API cho cùng vùng.

### 14.1. Tránh nhận diện timezone không hợp lệ bằng `TimeZone.getTimeZone(String)`

Một bẫy của API `TimeZone.getTimeZone(String)` là có trường hợp chuỗi ID không nhận diện được sẽ **fallback về GMT**. Trong code mới cần validate một tên IANA do người dùng nhập, nên dùng:

```java
ZoneId selectedZone = ZoneId.of(inputZoneId);
```

Mảnh code giả định `inputZoneId` là `String`, và caller xử lý `DateTimeException`/`ZoneRulesException` phù hợp. `ZoneId.of` xác minh ID hợp lệ và có quy tắc dùng được, thay vì âm thầm chọn một timezone khác.

**Không dùng các viết tắt mơ hồ** như `"CST"` hay `"PST"` làm định danh timezone khi có thể dùng ID IANA rõ ràng `America/Chicago`, `America/Los_Angeles`. Các viết tắt có thể chỉ nhiều vùng khác nhau và quy tắc DST khác nhau.

### 14.2. `ZoneId.systemDefault()` không phải cài đặt per-request

Việc `ZoneId.systemDefault()` phản ánh default timezone JVM không có nghĩa nó là zone thực của người dùng cuối. Trên server/container, giá trị ấy có thể là UTC hoặc timezone của máy chủ, không liên quan tới người dùng.

Đừng đặt:

```java
ZoneId zoneForEveryUser = ZoneId.systemDefault();
```

nếu yêu cầu là “hiển thị theo múi giờ mỗi người dùng”. Hãy nhận `ZoneId` của từng người dùng từ dữ liệu ứng dụng. `systemDefault()` vẫn hoàn toàn hữu ích trong chương trình desktop hoặc tác vụ thực sự muốn dùng timezone của máy đang chạy.

## 15. Kiểm thử độc lập môi trường và khuyến nghị production

### 15.1. Dùng dữ liệu cố định thay vì đồng hồ thực

Đối với unit test của formatter, chọn:

```java
Instant fixed =
        Instant.parse("2024-01-15T12:00:00Z");
ZoneId viewerZone = ZoneId.of("Asia/Tokyo");
Locale viewerLocale = Locale.US;
```

Mảnh code trong method. `fixed` và `viewerZone` không thay đổi theo giờ chạy test hay múi giờ máy CI.

### 15.2. Assert time conversion, không assert locale mặc định của máy

Một test ổn định:

```java
String actual = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm", Locale.US)
        .withZone(ZoneId.of("Asia/Tokyo"))
        .format(Instant.parse("2024-01-15T12:00:00Z"));

if (!"2024-01-15 21:00".equals(actual)) {
    throw new AssertionError("wrong Tokyo time");
}
```

Đây là mảnh code trong method, cần `DateTimeFormatter`, `Locale`, `ZoneId`, `Instant`. Kiểm tra rõ hành vi chuyển đổi; không dựa trên `ZoneId.systemDefault()`.

### 15.3. Khi nào nên test localized text?

Nếu test tên tháng/ngày, định dạng tiền tệ hay chuỗi `DateTimeFormatter.ofLocalizedDateTime` theo một locale, cần lưu ý dữ liệu CLDR và provider có thể thay đổi giữa các JDK. Với yêu cầu format ổn định đến từng ký tự:
- Cố định môi trường JDK/CLDR hoặc pattern của sản phẩm;
- Không coi một ký hiệu tiền cụ thể là contract nếu API không bảo đảm;
- Tách test **time-zone arithmetic** khỏi test **ngôn ngữ trình bày**.

Ví dụ trong ba chương trình trên chủ yếu in các ID, boolean và giờ dạng số để giảm phụ thuộc dữ liệu CLDR. Riêng ánh xạ Unicode `tz-jptyo` phụ thuộc provider có hỗ trợ theo JEP 314, vì thế phải bảo đảm runtime có dữ liệu tương ứng.

### 15.4. Test global defaults chỉ trong process riêng

Nếu thực sự phải test `Locale.setDefault` và `TimeZone.setDefault`, hãy chạy trong JVM test riêng, khôi phục state và **không** chia sẻ execution với test song song khác.

Không thay đổi hai mặc định rồi để nguyên sau test. Nó dễ làm hỏng những test unrelated, nhất là các test format ngày/số hoặc code dùng `LocalDate.now()`.

### 15.5. Chú ý cập nhật IANA tzdb

Zone rules có thể thay đổi theo quyết định pháp lý của các quốc gia. Java dùng timezone database của runtime. Với các hệ thống lập lịch tương lai nhiều năm, hãy cập nhật JDK/tzdb và xác định chiến lược khi quy tắc giờ địa phương tương lai thay đổi.

**Không giả định mọi năm có cùng DST transition** hoặc mọi offset của một vùng là cố định.

## 16. Các sai lầm phổ biến

| Sai lầm | Cách hiểu đúng |
|---|---|
| “`Locale.US` nghĩa là `America/New_York`.” | Locale không chỉ ra một timezone duy nhất; Mỹ có nhiều múi giờ. |
| “Đổi `Locale.setDefault(Locale.FRANCE)` sẽ đổi `ZoneId.systemDefault()` sang Paris.” | Không. Locale default và TimeZone default là trạng thái riêng. |
| “Đổi `TimeZone.setDefault(Asia/Tokyo)` sẽ đổi ngôn ngữ sang tiếng Nhật.” | Không. Locale FORMAT/DISPLAY không bị đổi chỉ bởi thao tác đó. |
| “`ZoneId.of("Asia/Tokyo")` tự thay timezone JVM.” | Không. Chỉ tạo đối tượng ZoneId. |
| “`Locale.Category.FORMAT` chính là timezone mặc định.” | Không. Category này nói về locale dùng cho formatting. |
| “`Instant` luôn là giờ UTC nên không thể hiển thị giờ Tokyo.” | Instant là mốc tuyệt đối, có thể render tại bất kỳ ZoneId hợp lệ. |
| “`LocalDateTime` đủ để phân biệt 01:30 xảy ra hai lần tại DST.” | Không. Cần zone và quy tắc xử lý overlap/offset. |
| “`ZoneOffset=-05:00` là New York mọi thời điểm.” | Không. Vùng này có DST. |
| “`withLocale` đồng nghĩa `withZone`.” | Không. Cần truyền riêng nếu muốn cả hai. |
| “Thẻ `u-tz-jptyo` tự đổi JVM default timezone.” | Không. Một số API như `localizedBy` đọc extension, nhưng không sửa default. |
| “`localizedBy(locale)` và `withLocale(locale)` xử lý Unicode `tz` giống nhau.” | Không. `localizedBy` có thể áp dụng zone lên formatter khi extension được hỗ trợ. |
| “`rg-gbzzzz` tự cho timezone Europe/London.” | Không. `rg` chủ yếu chọn giá trị mặc định theo vùng, không phải đặt default timezone. |
| “Bắt lỗi timezone bằng `TimeZone.getTimeZone(invalid)` sẽ luôn báo ngoại lệ.” | Có thể fallback GMT. Với input cần validate, dùng `ZoneId.of`. |
| “Đổi global defaults trong `try/finally` là thread-safe.” | Không. Nhiều request vẫn có race condition. |
| “`ZonedDateTime.now()` lấy múi giờ của từng user.” | Không nếu không truyền zone; nó dùng default JVM. |
| “Default timezone của server luôn cùng với Locale mặc định.” | Không được cam kết; có thể cấu hình độc lập. |
| “Định dạng ngày từ CLDR luôn giống nhau giữa mọi JDK.” | Không. Dữ liệu locale có thể cập nhật. |

## 17. Checklist code review

- [ ] Có phân biệt `Locale` và `ZoneId` thành hai tham số/dữ liệu cấu hình khác nhau?
- [ ] Có chỗ nào suy timezone từ `locale.getCountry()` không?
- [ ] Code xử lý request có gọi `Locale.setDefault` hoặc `TimeZone.setDefault` không?
- [ ] Khi format `Instant`, đã truyền `ZoneId` xác định rõ chưa?
- [ ] Khi cần ngôn ngữ, đã truyền `Locale` cho formatter hoặc renderer?
- [ ] Có dùng `ZonedDateTime.now()` không tham số trong môi trường nhiều người dùng?
- [ ] Có dùng `LocalDateTime` làm timestamp sự kiện mà không lưu zone/offset không?
- [ ] Dữ liệu người dùng nhập rơi vào DST gap/overlap có chính sách rõ không?
- [ ] Có xử lý UTC offset khác nhau theo mùa cho vùng có DST?
- [ ] Nếu dùng `DateTimeFormatter.localizedBy(locale)`, có cố ý áp dụng Unicode `tz` không?
- [ ] Có nhầm `withLocale`, `localizedBy` và `withZone`?
- [ ] Có chọn timezone ID IANA rõ ràng và validate qua `ZoneId.of`?
- [ ] Unit test có dùng `Instant` cố định, `Locale`/`ZoneId` tường minh và không phụ thuộc máy CI?
- [ ] Localized text có được kiểm tra phù hợp biến động CLDR/locale provider?
- [ ] Nếu hệ thống cần xuất timestamp giữa các máy, có dùng ISO 8601/offset theo contract không?

Một nhận xét review có cơ sở:

> “Phần hiển thị hiện lấy `ZoneId.systemDefault()`. Đây là timezone của server chứ không phải timezone người xem. Hãy truyền `ZoneId` từ tùy chọn của người dùng; tiếp tục dùng `Locale` riêng cho kiểu trình bày.”

Một nhận xét cần tránh:

> “Người dùng chọn tiếng Pháp thì gọi `TimeZone.setDefault(Europe/Paris)` trước mỗi request.”

Ngôn ngữ không xác định timezone, và sửa global state gây xung đột giữa request.

## 18. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `Locale.FRANCE` có tự suy ra timezone Paris không?

**Đáp án:** Không. Locale chỉ nói về ngôn ngữ và quy ước vùng. Đặt `ZoneId.of("Europe/Paris")` nếu cần múi giờ Paris.

**Câu 2.** `Locale.setDefault(Locale.JAPAN)` có đổi `ZoneId.systemDefault()` sang Tokyo không?

**Đáp án:** Không. Đây là hai mặc định khác nhau.

**Câu 3.** `TimeZone.setDefault(TimeZone.getTimeZone("UTC"))` có đổi `Locale.Category.FORMAT` không?

**Đáp án:** Không. TimeZone default không thay Locale default.

**Câu 4.** `ZoneId.systemDefault()` lấy timezone từ đâu?

**Đáp án:** Nó truy vấn timezone mặc định JVM thông qua `TimeZone.getDefault()` rồi chuyển sang `ZoneId`.

**Câu 5.** `Locale.getDefault(Locale.Category.DISPLAY)` và `Locale.getDefault(Locale.Category.FORMAT)` bắt buộc bằng nhau không?

**Đáp án:** Không. Hai category có thể khác nhau.

**Câu 6.** `Instant.parse("2024-01-15T12:00:00Z")` hiển thị lúc mấy giờ ở Tokyo vào ngày đó?

**Đáp án:** 21:00 theo `Asia/Tokyo`, tức cùng một `Instant` được render theo UTC+09:00.

**Câu 7.** Vì sao `ZoneOffset.of("-05:00")` không thể thay thế `America/New_York` mọi ngày?

**Đáp án:** New York có quy tắc DST, có thời điểm offset `-04:00`.

**Câu 8.** `LocalDateTime` có lưu offset hoặc timezone không?

**Đáp án:** Không. Nó chỉ chứa ngày/giờ địa phương.

**Câu 9.** Tại sao ngày 10/03/2024 lúc 02:30 ở New York không có offset hợp lệ?

**Đáp án:** Đây là gap khi bắt đầu DST; đồng hồ nhảy qua khoảng 02:00–02:59.

**Câu 10.** Vì sao ngày 03/11/2024 lúc 01:30 có hai offset hợp lệ ở New York?

**Đáp án:** Đây là overlap khi kết thúc DST, một khoảng giờ địa phương xảy ra hai lần.

**Câu 11.** `DateTimeFormatter.withLocale(locale)` có mặc nhiên đặt zone từ `locale.getCountry()` không?

**Đáp án:** Không. Muốn đặt zone tường minh, dùng `withZone(zone)`.

**Câu 12.** `DateTimeFormatter.localizedBy(locale)` mới có từ Java nào, và có gì đặc biệt?

**Đáp án:** Java 10. Nó có thể áp dụng các Unicode locale extensions, trong đó có `tz`, lên formatter mới.

**Câu 13.** `en-US-u-tz-jptyo` có làm thay timezone mặc định JVM sang Tokyo không?

**Đáp án:** Không. Nó là locale preference mà API hỗ trợ có thể sử dụng; ví dụ `localizedBy`.

**Câu 14.** Vì sao nên dùng `ZoneId.of(userInput)` thay cho `TimeZone.getTimeZone(userInput)` nếu cần kiểm tra timezone ID sai?

**Đáp án:** `ZoneId.of` kiểm tra ID và có thể ném ngoại lệ khi ID không hợp lệ; `TimeZone.getTimeZone` có trường hợp fallback GMT âm thầm.

**Câu 15.** Tại sao không nên đặt locale/timezone mặc định JVM riêng trong từng HTTP request?

**Đáp án:** Chúng là global state; các request song song có thể can thiệp và làm sai kết quả của nhau.

**Câu 16.** Nếu server ở UTC còn người dùng ở New York, nên lưu sự kiện dưới dạng gì?

**Đáp án:** Thường lưu `Instant` cho sự kiện đã xảy ra, render bằng `ZoneId.of("America/New_York")` và `Locale` người dùng. Với lịch hẹn theo giờ địa phương trong tương lai, cần giữ `LocalDateTime` + `ZoneId` và chính sách DST.

## 19. Tài liệu chính thức

- [Oracle Java SE 21 — `Locale`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `getDefault()`, `setDefault()`, các category `FORMAT`/`DISPLAY` và Unicode locale extensions.
- [Oracle Java SE 21 — `TimeZone`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TimeZone.html): `getDefault()`/`setDefault()`, kết nối với `ZoneId` và hành vi fallback.
- [Oracle Java SE 21 — `ZoneId`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html): `systemDefault()`, `of(String)`, zone IDs và time-zone rules.
- [Oracle Java SE 21 — `Instant`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html): biểu diễn thời điểm tuyệt đối.
- [Oracle Java SE 21 — `ZonedDateTime`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html): ngày/giờ với zone, xử lý gap/overlap khi tạo từ local time.
- [Oracle Java SE 21 — `LocalDateTime`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html): giá trị ngày/giờ không có timezone/offset.
- [Oracle Java SE 21 — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): `withLocale`, `withZone`, `localizedBy` và các định dạng ISO.
- [OpenJDK JEP 314 — Additional Unicode Language-Tag Extensions](https://openjdk.org/jeps/314): Java 10 hỗ trợ `cu`/`fw`/`rg`/`tz` và `DateTimeFormatter.localizedBy(Locale)`.
- [Unicode CLDR — Language and Locale Identifiers](https://www.unicode.org/reports/tr35/): Unicode locale keys và việc ánh xạ các timezone types.
- [IANA Time Zone Database](https://www.iana.org/time-zones): quy tắc timezone vùng dùng để tính offset và DST.

**Ghi nhớ:** **`Locale` không phải timezone**. Thay `Locale.setDefault(...)` không đổi `ZoneId.systemDefault()`; thay `TimeZone.setDefault(...)` không đổi `Locale`. Trong ứng dụng hiện đại, giữ `Instant` làm mốc thời gian, dùng `ZoneId` để biết giờ địa phương và dùng `Locale` để trình bày văn bản. Kể cả Unicode `tz` và `DateTimeFormatter.localizedBy(...)` của Java 10 cũng **không** thay timezone mặc định toàn JVM.