# Chronology và các hệ lịch được Java hỗ trợ

## 1. Vì sao ứng dụng đa ngôn ngữ cần hiểu hệ lịch?

Cùng một ngày trong thực tế có thể được viết bằng những **hệ lịch** khác nhau. Ví dụ ngày ISO **2026-10-28** có thể được trình bày với năm **2569** trong Phật lịch Thái, năm **115** trong lịch Dân Quốc (Minguo), hoặc **năm thứ 8 của niên hiệu Reiwa** trong lịch Nhật Bản. Không phải ngày thực tế đã thay đổi: **quy tắc xác định năm, niên hiệu và trường lịch của mỗi hệ lịch khác nhau**.

Java `java.time` lấy **ISO-8601** (hệ lịch Gregorian kéo dài theo quy tắc ISO) làm cơ sở phổ biến, nhưng còn cung cấp gói `java.time.chrono` cho một số hệ lịch khác. Đầu mối chung là interface `Chronology`.

Khi thực hiện localization, phải phân biệt ba quyết định:

1. **Ngày hoặc thời điểm nghiệp vụ nào?** `LocalDate`, `Instant` và các kiểu temporal mô tả dữ liệu thật.
2. **Dùng hệ lịch gì để biểu diễn ngày đó?** `IsoChronology`, `JapaneseChronology`, `ThaiBuddhistChronology`, v.v.
3. **Diễn đạt bằng ngôn ngữ và mẫu định dạng nào?** `Locale`, `DateTimeFormatter`, `FormatStyle`, tên tháng và tên niên hiệu.

Nếu chỉ thay `Locale.JAPAN` mà không thay chronology, không nên mặc định Java sẽ tự chuyển từ năm ISO 2026 thành năm Reiwa 8. Nếu chỉ thay chronology mà không chọn locale phù hợp, các từ như tên niên hiệu vẫn có thể xuất hiện bằng ngôn ngữ không mong muốn.

### Mục tiêu của bài

Bạn sẽ biết những chronology có sẵn trong Java 17, cách chọn chúng qua API hoặc Unicode locale extension, chuyển một ngày giữa các chronology không làm thay đổi ngày trên dòng thời gian, phân biệt `YEAR` và `YEAR_OF_ERA`, dùng `DateTimeFormatter.withChronology`, parse theo lịch phù hợp và tránh trộn lẫn lịch với múi giờ hoặc quy tắc nghiệp vụ.

## 2. Chronology là gì?

`Chronology` trong `java.time.chrono` đại diện cho **bộ quy tắc của một hệ lịch**, gồm cách đánh số năm, chia tháng, ngày, niên hiệu (era), năm nhuận và cách tạo ngày hợp lệ. Nó còn đóng vai trò **factory** sinh ra các đối tượng ngày của chronology tương ứng.

| Khái niệm | API/kiểu Java | Vai trò |
| --- | --- | --- |
| Hệ lịch | `Chronology` | Nhận diện và triển khai quy tắc của calendar |
| Lịch ISO | `IsoChronology` | Nền tảng mặc định của `LocalDate` và phần lớn `java.time` |
| Ngày thuộc một hệ lịch | `ChronoLocalDate` | Giao diện chung cho ngày ISO và non-ISO |
| Niên hiệu | `Era` | Giai đoạn đánh số năm như Reiwa, Heisei |
| Ngày/giờ theo một hệ lịch | `ChronoLocalDateTime` | Ngày non-ISO kết hợp thời gian địa phương |
| Ngày/giờ có múi giờ | `ChronoZonedDateTime` | Biểu diễn non-ISO có zone |
| Formatter | `DateTimeFormatter` | Chuyển ngày thành chuỗi hoặc parse chuỗi |
| Ngôn ngữ/quy ước địa phương | `Locale` | Tên tháng, tên era, localized pattern |
| Vùng thời gian | `ZoneId` | Quy tắc biến một instant thành ngày/giờ địa phương |

`Chronology` **không** phải bộ từ điển dịch, không phải `ZoneId` và không phải tỷ lệ quy đổi thời gian. Nó quyết định ý nghĩa các trường **ngày/tháng/năm** của calendar.

Một cùng ngày có thể có nhiều `ChronoLocalDate` khác nhau nhưng cùng giá trị `EPOCH_DAY` — số ngày tính từ mốc ISO `1970-01-01`. Đây là cơ sở quan trọng để chuyển đổi và so sánh ngày xuyên các hệ lịch. `Chronology.dateEpochDay(long)` dựng ngày theo calendar được chọn từ epoch-day.

**Lời khuyên của Java API:** Đối với phần lớn logic ứng dụng, ưu tiên `LocalDate` theo ISO làm dạng lưu trữ/tính toán đơn giản và chỉ dùng chronology khác khi yêu cầu bản địa hóa hoặc nghiệp vụ thực sự cần. Không thay toàn bộ mô hình thời gian bằng `ChronoLocalDate` chỉ để hiển thị một tên niên hiệu.

## 3. Các hệ lịch tích hợp trong Java 17

Java 17 có năm chronology hệ thống nổi bật sau; ngoài ra ứng dụng có thể cung cấp chronology tùy chỉnh qua `ServiceLoader`.

| Chronology | Class | ID điển hình | Calendar type | Đặc điểm chính |
| --- | --- | --- | --- | --- |
| ISO | `IsoChronology` | `ISO` | `iso8601` | Năm/tháng/ngày ISO; `LocalDate` là kiểu quen thuộc |
| Nhật Bản | `JapaneseChronology` | `Japanese` | `japanese` | Gregorian về tháng/ngày nhưng đếm năm theo niên hiệu Nhật |
| Dân Quốc | `MinguoChronology` | `Minguo` | `roc` | Năm Dân Quốc tính từ mốc 1912; tháng/ngày tương ứng ISO |
| Phật lịch Thái | `ThaiBuddhistChronology` | `ThaiBuddhist` | `buddhist` | Năm Phật lịch Thái hiện hành bằng năm ISO cộng 543 |
| Hijrah | `HijrahChronology` | `Hijrah-umalqura` | `islamic-umalqura` | Lịch âm Hồi giáo, tháng và ngày dựa trên dữ liệu biến thể lịch được cung cấp |

Các tên ID và calendar type dùng ở trên là thông tin của các chronology tích hợp trong JDK 17; chronology bổ sung có thể xuất hiện nếu ứng dụng đăng ký provider khác. `Chronology.getAvailableChronologies()` trả về tập hệ lịch có sẵn **trên runtime hiện tại**, vì thế đừng suy rằng tập này mãi mãi chỉ có đúng năm phần tử trong mọi ứng dụng.

### 3.1. ISO — nền tảng phổ biến

`IsoChronology.INSTANCE` là chronology mặc định cho `LocalDate`. Ví dụ `LocalDate.of(2026, 10, 28)` là một ngày ISO. Phần lớn giao thức máy, API và truy vấn DB ứng dụng kinh doanh dùng ngày ISO hoặc biểu diễn liên quan ISO-8601.

### 3.2. Japanese — lịch theo niên hiệu

`JapaneseChronology.INSTANCE` dùng hệ lịch Nhật Bản. Nó tương ứng với ngày/tháng của lịch Gregorian trong phạm vi được hỗ trợ, nhưng năm thường thể hiện dưới dạng niên hiệu và năm trong niên hiệu. Ví dụ **2026-10-28 ISO** thuộc **Reiwa 8**.

`JapaneseEra` có các giá trị như `MEIJI`, `TAISHO`, `SHOWA`, `HEISEI`, `REIWA`. Một niên hiệu có mốc bắt đầu và kết thúc: **Reiwa bắt đầu ngày 2019-05-01**. Do đó, chỉ có số năm “8” mà không có era là **không đủ** để xác định một năm Nhật cụ thể. Cần lưu/parse era khi dùng `YEAR_OF_ERA`.

Lịch Nhật trong Java không hỗ trợ tùy ý mọi mốc lịch sử: `JapaneseChronology` hỗ trợ từ **Meiji 6, ngày 1873-01-01 ISO** trở về sau. Không dùng để kỳ vọng thao tác ngày trước phạm vi này.

### 3.3. Minguo — lịch Dân Quốc

`MinguoChronology.INSTANCE` có mốc năm 1 vào **1912 ISO**. Với ngày ISO năm 2026, số năm Dân Quốc hiện hành là **115**. Hệ này có era cho năm Dân Quốc và thời kỳ trước Dân Quốc. Đừng lầm “115” thành năm ISO 115 khi xuất API.

### 3.4. Thai Buddhist — Phật lịch Thái

`ThaiBuddhistChronology.INSTANCE` sử dụng thứ tự tháng/ngày tương ứng ISO; trong giai đoạn hiện hành, năm Phật lịch Thái bằng **năm ISO + 543**. Vì thế **2026 → 2569**.

**Đây là phép đối chiếu của hệ lịch, không phải đổi múi giờ hoặc cộng 543 năm vào `LocalDate` nghiệp vụ.** Nếu thực sự gọi `isoDate.plusYears(543)`, bạn đã chuyển thành một ngày khác trên dòng thời gian — khác hoàn toàn với tạo `ThaiBuddhistDate` cho cùng epoch-day.

### 3.5. Hijrah — hệ lịch âm Hồi giáo

`HijrahChronology.INSTANCE` đại diện cho biến thể Hijrah tích hợp, thông dụng là **Umm al-Qura**. Đây là lịch âm: số ngày trong tháng, năm và quy tắc năm nhuận không giống ISO hoặc các chronology chỉ đổi mốc năm.

Do đó **không** thể đổi lịch Hijrah sang ISO bằng công thức “năm cộng/trừ một số cố định”. Thời gian bắt đầu tháng, phạm vi ngày hợp lệ và kết quả có thể phụ thuộc biến thể cũng như dữ liệu lịch đi kèm JDK. Với dữ liệu có ý nghĩa pháp lý/tôn giáo, phải xác định chính xác **calendar variant, nguồn dữ liệu và quy tắc** được sản phẩm chấp nhận.

## 4. Truy cập các Chronology bằng Java API

Các cách lấy một chronology:

```java
Chronology iso = IsoChronology.INSTANCE;
Chronology japanese = JapaneseChronology.INSTANCE;
Chronology minguo = MinguoChronology.INSTANCE;
Chronology thai = ThaiBuddhistChronology.INSTANCE;
Chronology hijrah = HijrahChronology.INSTANCE;
```

Đoạn này là mã minh họa trong một method, cần import `java.time.chrono.*`. Vì các lớp tích hợp có singleton `INSTANCE`, không cần tự khởi tạo chúng.

Có thể dùng lookup:

```java
Chronology jp = Chronology.of("Japanese");
Chronology buddhist = Chronology.of("buddhist");
Chronology thaiById = Chronology.of("ThaiBuddhist");
```

`Chronology.of(String)` tìm theo **ID** hoặc **calendar type**. Nếu ID/type không tồn tại, ném `DateTimeException`. Không coi mọi chuỗi ngẫu nhiên là calendar name hợp lệ.

Để quan sát runtime có gì:

```java
for (Chronology chronology : Chronology.getAvailableChronologies()) {
    System.out.println(chronology.getId() + " / "
            + chronology.getCalendarType());
}
```

Tập trả về **không bảo đảm thứ tự ổn định**. Khi cần kết quả có thứ tự để hiển thị hoặc test, hãy sắp xếp bằng comparator rõ ràng. Đừng làm snapshot thứ tự của một `Set` và xem đó là contract.

## 5. Chương trình Java 17: một ngày, nhiều hệ lịch, không đổi EPOCH_DAY

Ví dụ chính sử dụng **ngày cố định**, không gọi `dateNow()`, để đầu ra không phụ thuộc đồng hồ hoặc múi giờ hệ thống.

Tạo tệp `ChronologyDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.ChronoLocalDate;
import java.time.chrono.JapaneseChronology;
import java.time.chrono.JapaneseEra;
import java.time.chrono.MinguoChronology;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.temporal.ChronoField;

public class ChronologyDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2026, 10, 28);

        ChronoLocalDate thai =
                ThaiBuddhistChronology.INSTANCE.date(iso);
        ChronoLocalDate minguo =
                MinguoChronology.INSTANCE.date(iso);
        ChronoLocalDate japanese =
                JapaneseChronology.INSTANCE.date(iso);

        System.out.println("ISO=" + iso);
        System.out.println("Thai-year=" +
                thai.get(ChronoField.YEAR));
        System.out.println("Minguo-year=" +
                minguo.get(ChronoField.YEAR_OF_ERA));
        System.out.println("Japanese-Reiwa=" +
                japanese.getEra().equals(JapaneseEra.REIWA));
        System.out.println("Japanese-year-of-era=" +
                japanese.get(ChronoField.YEAR_OF_ERA));

        System.out.println("same-day=" +
                (iso.toEpochDay() == thai.toEpochDay()
                && iso.toEpochDay() == minguo.toEpochDay()
                && iso.toEpochDay() == japanese.toEpochDay()));

        System.out.println("back-to-ISO=" +
                LocalDate.from(thai));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 ChronologyDemo.java
java ChronologyDemo
```

Stdout xác định:

```text
ISO=2026-10-28
Thai-year=2569
Minguo-year=115
Japanese-Reiwa=true
Japanese-year-of-era=8
same-day=true
back-to-ISO=2026-10-28
```

**Diễn giải kết quả:**

- `Thai-year=2569`: năm trong chronology Thái.
- `Minguo-year=115`: năm Dân Quốc tương ứng.
- `Japanese-Reiwa=true` và `Japanese-year-of-era=8`: cùng ngày trong niên hiệu Nhật.
- `same-day=true`: các đối tượng trỏ tới **cùng một epoch-day**, không có phép dịch ngày thực tế.
- `back-to-ISO=2026-10-28`: `LocalDate.from(ChronoLocalDate)` chuyển biểu diễn về ISO, vẫn giữ nguyên ngày.

Nếu ứng dụng dùng lịch khác để **hiển thị** số năm, không sửa cột ngày ISO trong DB thành 2569 hay 115. Cần giữ dữ liệu chuẩn và chỉ đổi chronology ở ranh giới presentation, trừ khi nghiệp vụ thật sự đòi hỏi lưu lịch gốc của người dùng.

## 6. YEAR, YEAR_OF_ERA và ERA: ba trường không đồng nghĩa

Các trường trong `java.time.temporal.ChronoField` đặc biệt quan trọng:

| Trường | Ý nghĩa |
| --- | --- |
| `YEAR` | Năm theo trục proleptic của chronology hiện tại |
| `YEAR_OF_ERA` | Năm **tính trong một era**, thường bắt đầu lại từ 1 khi era mới bắt đầu |
| `ERA` | Mã của era tương ứng |
| `MONTH_OF_YEAR` | Tháng trong calendar hiện tại |
| `DAY_OF_MONTH` | Ngày trong tháng của calendar hiện tại |
| `EPOCH_DAY` | Số ngày trên trục chung, dùng chuyển giữa chronology |

Trong lịch Nhật, năm Reiwa 8 phải đi kèm thông tin **Reiwa** để biểu đạt đầy đủ. Nếu pattern chỉ có `"y/MM/dd"` mà thiếu era `G`, kết quả nhìn được nhưng thiếu thông tin xác định niên hiệu. Tương tự, pattern không nên giả định năm `YEAR_OF_ERA` lúc nào cũng bằng năm ISO.

Ví dụ một formatter mô tả cấu trúc era và năm:

```java
DateTimeFormatter japaneseDisplay =
        DateTimeFormatter.ofPattern("G y/MM/dd", Locale.JAPAN)
                .withChronology(JapaneseChronology.INSTANCE);
```

Đoạn mã trên dùng trong method với import `java.time.format.DateTimeFormatter`, `java.time.chrono.JapaneseChronology` và `java.util.Locale`. Khi format ngày ISO 2026-10-28, pattern bao gồm **tên/ký hiệu era Nhật, năm trong era, tháng, ngày**. Nguyên văn tên era có thể phụ thuộc locale data của JDK, vì vậy không đưa ra một stdout cố định cho chữ Nhật.

**Chú ý pattern letter:** trong `DateTimeFormatter`, `G` là era, `y` là năm trong era, còn `u` là proleptic year. Pattern `"uuuu-MM-dd"` và `"G y-MM-dd"` không mang cùng ý nghĩa. `Y` là **week-based-year**, không dùng thay `u` hoặc `y` để xuất một ngày lịch thông thường.

## 7. DateTimeFormatter.withChronology: đổi calendar để format/parse

`DateTimeFormatter.withChronology(chrono)` trả **formatter mới** có chronology override. Khi format một đối tượng có ngày, formatter chuyển biểu diễn ngày sang chronology được yêu cầu trước khi tạo chuỗi, **không làm đổi epoch-day của ngày nguồn**.

Ví dụ muốn một ngày ISO được hiển thị theo lịch Thái:

```java
LocalDate date = LocalDate.of(2026, 10, 28);

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withChronology(ThaiBuddhistChronology.INSTANCE);

String text = formatter.format(date); // "2569-10-28"
```

Đây là đoạn mã trong method, cần import `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.chrono.ThaiBuddhistChronology` và `java.util.Locale`. Phần số năm phản ánh **chronology**, không đơn thuần do `Locale` chọn.

Nếu muốn theo **mẫu ngày được bản địa hóa** cho từng locale, có thể dùng:

```java
DateTimeFormatter thaiLocalized =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(Locale.forLanguageTag("th-TH"))
                .withChronology(ThaiBuddhistChronology.INSTANCE);
```

Dạng này cho phép Java chọn pattern theo locale/`FormatStyle` và áp dụng chronology Thái. Tên tháng, tên era và cách hiển thị phụ thuộc locale/JDK/CLDR. `DateTimeFormatter.ofLocalizedDate` tự nó được tạo với chronology ISO; **cần override chronology rõ ràng** nếu sản phẩm muốn hệ lịch khác.

### 7.1. withLocale khác withChronology

| Thao tác | Thay đổi điều gì? | Không tự thay gì? |
| --- | --- | --- |
| `withLocale(Locale.JAPAN)` | Locale cho localized pattern/text | Không buộc chronology đổi sang Japanese |
| `withChronology(JapaneseChronology.INSTANCE)` | Calendar để diễn giải trường ngày | Không tự đổi ngôn ngữ sang tiếng Nhật |
| `withZone(ZoneId.of("Asia/Tokyo"))` | Zone của instant hoặc temporal có thông tin thời gian phù hợp | Không tự chọn calendar Nhật |
| `withDecimalStyle(DecimalStyle.of(locale))` | Ký hiệu số theo decimal style | Không tự suy chronology |
| `localizedBy(locale)` | Có thể đọc thêm Unicode locale extensions, trong đó có calendar `ca` | Không phải đồng nghĩa giản lược với `withLocale` |

Một bộ lựa chọn UI thực tế có thể gồm `languageLocale`, `calendarChronology` và `zoneId` độc lập. Đừng giả định người dùng Nhật luôn dùng Japanese imperial calendar hoặc người dùng Thái luôn muốn Phật lịch.

### 7.2. Ví dụ độc lập về formatter chronology

Tệp `ChronologyFormatDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.IsoChronology;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ChronologyFormatDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter base =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd", Locale.ROOT);

        DateTimeFormatter thai =
                base.withChronology(ThaiBuddhistChronology.INSTANCE);
        DateTimeFormatter iso =
                base.withChronology(IsoChronology.INSTANCE);

        System.out.println("source=" + date);
        System.out.println("iso=" + iso.format(date));
        System.out.println("thai=" + thai.format(date));
        System.out.println("source-after=" + date);
    }
}
```

```bash
javac -encoding UTF-8 ChronologyFormatDemo.java
java ChronologyFormatDemo
```

Stdout:

```text
source=2026-10-28
iso=2026-10-28
thai=2569-10-28
source-after=2026-10-28
```

`base` là formatter immutable. `withChronology` trả về instance mới, vì vậy việc định dạng theo lịch Thái **không sửa `LocalDate` gốc hay formatter ISO**.

## 8. Chọn chronology theo Locale và Unicode extension ca

`Locale` có thể mang Unicode locale extension `u-ca-...`, trong đó `ca` chỉ calendar. Java hỗ trợ:

```java
Chronology selected = Chronology.ofLocale(locale);
```

**Bẫy quan trọng:** `Chronology.ofLocale(Locale.forLanguageTag("th-TH"))` **không tự trả ThaiBuddhist** chỉ vì vùng là Thái Lan. Nếu locale không chỉ rõ calendar, API thường trả `IsoChronology`. Muốn chọn lịch Thái một cách tường minh, dùng `th-TH-u-ca-buddhist`.

Tương tự:

| Locale | Ý nghĩa |
| --- | --- |
| `en-US` | Tiếng Anh tại Hoa Kỳ, không yêu cầu calendar khác ISO |
| `th-TH` | Tiếng Thái tại Thái Lan, **không tự chỉ định Buddhist calendar** cho `Chronology.ofLocale` |
| `th-TH-u-ca-buddhist` | Tiếng Thái tại Thái Lan, yêu cầu calendar Buddhist |
| `ja-JP-u-ca-japanese` | Tiếng Nhật tại Nhật Bản, yêu cầu Japanese calendar |
| `en-US-u-ca-roc` | Tiếng Anh tại Hoa Kỳ, yêu cầu calendar Minguo/Dân Quốc |

Ví dụ Java 17:

Tệp `ChronologyLocaleDemo.java`:

```java
import java.time.chrono.Chronology;
import java.util.Locale;

public class ChronologyLocaleDemo {
    public static void main(String[] args) {
        Locale plain = Locale.forLanguageTag("th-TH");
        Locale explicit = Locale.forLanguageTag(
                "th-TH-u-ca-buddhist");
        Locale japan = Locale.forLanguageTag(
                "ja-JP-u-ca-japanese");

        System.out.println("plain=" +
                Chronology.ofLocale(plain).getId());
        System.out.println("buddhist=" +
                Chronology.ofLocale(explicit).getId());
        System.out.println("japanese=" +
                Chronology.ofLocale(japan).getId());
    }
}
```

```bash
javac -encoding UTF-8 ChronologyLocaleDemo.java
java ChronologyLocaleDemo
```

Stdout trên JDK 17 tiêu chuẩn:

```text
plain=ISO
buddhist=ThaiBuddhist
japanese=Japanese
```

`Chronology.ofLocale` có thể ném `DateTimeException` nếu `ca` yêu cầu một chronology không được runtime hỗ trợ. Cần áp dụng chính sách supported calendars và thông báo lỗi/fallback của sản phẩm; không chấp nhận mọi calendar tag mà không kiểm tra.

### 8.1. withLocale không phải localizedBy

`DateTimeFormatter.withLocale(...)` cập nhật locale dùng để chọn các phần cần dịch/định dạng, nhưng không tự động gán chronology từ `u-ca`. `DateTimeFormatter.localizedBy(locale)` là API khác (Java 10+) có thể áp dụng calendar từ extension `ca`, cùng những extension được hỗ trợ khác như numbering system `nu` và timezone `tz`.

Với ứng dụng yêu cầu calendar cụ thể, có hai cách rõ nghĩa:

- Chọn `Chronology.ofLocale(locale)` rồi gán `formatter.withChronology(chronology)`.
- Dùng `formatter.localizedBy(locale)` khi muốn tôn trọng các Unicode locale extensions được hỗ trợ và hiểu rõ thứ tự override.

Trong hệ thống cần kiểm soát tuyệt đối lịch sử và logic lưu trữ, lựa chọn chronology **tường minh bằng cấu hình nghiệp vụ** thường rõ ràng hơn việc dựa hoàn toàn vào locale tag của user.

## 9. Parse ngày non-ISO: dữ liệu và pattern phải cùng hệ lịch

Khi parse một ngày mang năm Buddhist `2569`, không được dùng `LocalDate.parse("2569-10-28")` theo ISO rồi mong kết quả là 2026. Parser ISO hiểu **năm ISO 2569**, tức một ngày khác.

Để đọc một ngày theo calendar khác, tạo formatter với chronology tương ứng:

Tệp `ChronologyParsingDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.ChronoLocalDate;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ChronologyParsingDemo {
    public static void main(String[] args) {
        DateTimeFormatter thaiParser =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd", Locale.ROOT)
                        .withChronology(ThaiBuddhistChronology.INSTANCE)
                        .withResolverStyle(ResolverStyle.STRICT);

        ChronoLocalDate thaiDate =
                ThaiBuddhistChronology.INSTANCE.date(
                        thaiParser.parse("2569-10-28"));

        LocalDate sameDayInIso = LocalDate.from(thaiDate);

        System.out.println("thaiYear=" +
                thaiDate.get(java.time.temporal.ChronoField.YEAR));
        System.out.println("iso=" + sameDayInIso);
        System.out.println("roundTrip=" +
                thaiParser.format(thaiDate));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ChronologyParsingDemo.java
java ChronologyParsingDemo
```

Stdout:

```text
thaiYear=2569
iso=2026-10-28
roundTrip=2569-10-28
```

Khi parser có chronology override, các trường ngày được resolve theo chronology đó. `ResolverStyle.STRICT` từ chối những ngày không hợp lệ theo hệ lịch yêu cầu. Dùng pattern `uuuu` cho năm proleptic khi kiểm thử strict; `yyyy` là năm trong era và có thể cần thêm `G` hoặc quy tắc era rõ.

**Đây là điểm ngữ nghĩa:** `2569-10-28` có thể là một ngày ISO ở tương lai hoặc ngày Thai Buddhist tương ứng ISO 2026. Chuỗi số **không có metadata calendar** là không đủ xác định ý nghĩa. Với giao thức máy, lưu calendar ID nếu không phải ISO, hoặc chuẩn hóa thành ngày ISO có contract rõ.

### 9.1. Parse Japanese era

Với lịch Nhật, chuỗi như `"Reiwa 8/10/28"` (ví dụ minh họa bằng chữ tiếng Anh) chứa **era**, **year-of-era** và tháng/ngày. Để parse chắc chắn cần formatter có chronology Nhật, locale tương ứng với tên era, pattern như `"G y/M/d"` và resolver phù hợp; không parse năm 8 như năm ISO 0008. Tên era có thể khác theo locale/JDK, nên kiểm thử bằng formatter thật hoặc dùng mã era chuẩn ở contract thay vì tự viết string.

### 9.2. Parse Hijrah

Với lịch Hijrah, một tháng có thể có độ dài khác ISO và nguồn lịch có thể bị giới hạn phạm vi. Không parse theo ISO rồi tự áp một công thức bù năm. Dùng `HijrahChronology` của biến thể đã chọn, kiểm tra `DateTimeException`/`DateTimeParseException` và dữ liệu lịch được triển khai.

## 10. Chronology, Locale và ZoneId không thay thế nhau

Xét một timestamp:

```text
Instant: 2026-10-28T07:30:00Z
```

Ứng dụng có thể hiển thị thời điểm này ở `Asia/Ho_Chi_Minh` hoặc `Asia/Tokyo`. Chọn `ZoneId` làm **ngày/giờ đồng hồ địa phương** thay đổi. Chọn `Chronology` làm **tên era và số năm/tháng/ngày theo calendar** thay đổi. Chọn `Locale` làm **ngôn ngữ và quy ước viết chuỗi** thay đổi.

Một cách hình dung:

```text
                   Instant gốc (UTC)
                           |
                    +------v------+
                    |   ZoneId    |  Chọn ngày/giờ địa phương
                    +------v------+
                           |
                      LocalDate
                           |
                    +------v------+
                    | Chronology  |  Chọn hệ lịch cho ngày này
                    +------v------+
                           |
                   ChronoLocalDate
                           |
                    +------v------+
                    | Locale +    |  Tên era/tháng, mẫu hiển thị
                    | Formatter   |
                    +------v------+
                           |
                 Văn bản cho người dùng
```

Với các hệ lịch có ngày bắt đầu khác nhau hoặc quyết định ngày theo quy ước tôn giáo, việc hiển thị/ngữ nghĩa có thể phức tạp hơn sơ đồ giản lược này. Trong mọi trường hợp, **không suy ZoneId từ Chronology** và không suy Chronology từ locale language-region khi user chưa chọn calendar.

## 11. Lưu trữ và API: nên chọn dạng canonical nào?

Các hệ thống cần so sánh ngày, tìm khoảng thời gian và giao tiếp giữa các dịch vụ thường dễ bảo trì hơn khi lưu:

- Ngày thuần (ngày sinh, hạn trả theo lịch ISO): `LocalDate` hoặc ngày ISO-8601 chuẩn như `2026-10-28`.
- Thời điểm tuyệt đối: `Instant`/timestamp có offset rõ trong API.
- Sự kiện theo giờ địa phương: ngày/giờ địa phương và `ZoneId` khi nghiệp vụ yêu cầu.

Calendar của người dùng là **thông tin về cách diễn giải và trình bày**; có thể lưu nó trong profile hoặc một trường riêng, ví dụ `calendarType=buddhist`. Nếu đầu vào lịch Hijrah là dữ liệu gốc nghiệp vụ có ý nghĩa riêng, cần lưu **calendar ID/variant, các trường ngày, và quy tắc chuyển đổi/phiên bản dữ liệu** theo yêu cầu truy vết; không tự xóa thông tin nguồn chỉ vì đã quy về ISO.

Ví dụ contract minh họa:

```json
{
  "canonicalDate": "2026-10-28",
  "displayCalendar": "buddhist",
  "displayLocale": "th-TH",
  "displayZone": "Asia/Bangkok"
}
```

Đây là **ví dụ về thiết kế dữ liệu**, không phải JSON mặc định mà `java.time` tự serial hóa. Phải tách ngày canonical khỏi cấu hình calendar và vùng. `displayCalendar=buddhist` không có nghĩa giá trị `canonicalDate` đang là năm 2569; nó bảo ứng dụng **trình bày** ngày gốc theo chronology Thái.

### So sánh và sắp xếp ngày thuộc nhiều chronology

Nếu có hai `ChronoLocalDate` từ **hai hệ lịch khác nhau**, muốn so sánh xem ngày nào xảy ra trước, có thể dùng `ChronoLocalDate.timeLineOrder()` hoặc chuyển sang `EPOCH_DAY`/`LocalDate`. `compareTo` của `ChronoLocalDate` có thêm chronology để cho thứ tự ổn định trong các cấu trúc hỗn hợp; do đó không xem `compareTo==0` là điều kiện duy nhất cho “cùng epoch-day” giữa các loại lịch.

Ví dụ:

```java
boolean samePhysicalDay =
        iso.toEpochDay() == thai.toEpochDay();

int chronologicalOrder =
        ChronoLocalDate.timeLineOrder().compare(iso, thai);
```

Đoạn mã minh họa nằm trong method với `iso` kiểu `LocalDate` và `thai` kiểu `ChronoLocalDate`. Khi cùng epoch-day, `chronologicalOrder` bằng 0 dù chronology khác.

### Tính toán ngày và kỳ hạn

Không giả định `ChronoPeriod`, `Period`, cộng tháng hoặc tính “một năm” luôn tương đương giữa các calendar. Với Hijrah, số ngày của tháng có thể khác ISO; với Japanese chronology, chuyển era giữa năm có quy tắc riêng. Nếu một hợp đồng dùng **ngày ISO + N ngày**, hãy tính trên `LocalDate`/`ChronoUnit.DAYS` theo contract. Nếu nghiệp vụ nói “tháng tiếp theo theo lịch Hijrah”, cần dùng chronology và quy tắc tháng của lịch đó. **Không đưa logic kinh doanh vào formatter.**

## 12. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Cho rằng `Locale.JAPAN` tự chọn lịch niên hiệu Nhật | Locale language/region không buộc chronology | Chọn `JapaneseChronology` hoặc `u-ca-japanese` rõ ràng |
| Cho rằng `th-TH` tự trả `ThaiBuddhistChronology` | `Chronology.ofLocale` mặc định ISO nếu không có `ca` | Dùng `th-TH-u-ca-buddhist` khi thực sự cần |
| Lưu `2569-10-28` nhưng API hiểu là ISO | Năm khác ngữ nghĩa | Ghi calendar metadata hoặc canonical ISO |
| Cộng `543` năm vào `LocalDate` để “chuyển” sang lịch Thái | Di chuyển ngày thực tế | Dùng `ThaiBuddhistChronology.INSTANCE.date(iso)` |
| Parse Reiwa 8 như ISO year 8 | Mất niên hiệu | Dùng `G`, `y` và chronology Nhật |
| Lầm `y` và `u` | Năm trong era khác năm proleptic | Chọn pattern đúng ý nghĩa |
| Lầm `Y` là năm lịch | `Y` là week-based-year | Dùng `u`/`y` tùy yêu cầu |
| Lấy lịch Hijrah bằng công thức bù năm | Lịch âm không giống ISO | Dùng `HijrahChronology` và variant được chỉ định |
| Gọi `dateNow()` trong test cần output cố định | Phụ thuộc thời điểm/múi giờ | Dùng ngày cố định hoặc `Clock` |
| Kết luận hai `ChronoLocalDate` khác chronology là hai ngày khác nhau | Có thể cùng `EPOCH_DAY` | So sánh epoch-day hoặc `timeLineOrder` |
| Dùng `withLocale` và nghĩ đã đổi chronology | `withLocale` chỉ gán locale | Dùng `withChronology` hoặc `localizedBy` có `ca` |
| Xem mọi chronology có 12 tháng giống ISO | Không phải mọi lịch có cấu trúc bằng nhau | Dựa vào Chronology và temporal fields thực tế |
| Thay chronology mà không kiểm tra phạm vi ngày | Japanese/Hijrah có giới hạn hỗ trợ | Bắt lỗi và validation |
| Hard-code tên era/hiển thị tháng | Dữ liệu locale và mốc era có thể đổi | Dùng formatter, dữ liệu locale và test |

## 13. Kiểm thử đúng chức năng

### 13.1. Kiểm tra đồng nhất ngày

Dùng `LocalDate.of(2026, 10, 28)`, tạo `JapaneseDate`, `MinguoDate`, `ThaiBuddhistDate` rồi xác nhận mọi ngày có cùng `EPOCH_DAY`. Đây là kiểm thử **ngữ nghĩa**, đáng tin cậy hơn việc so sánh chuỗi `toString()` giữa các calendar.

### 13.2. Kiểm tra era và biên giới

Kiểm tra những thời điểm giao niên hiệu Nhật, ví dụ ngày **2019-04-30** là cuối Heisei và **2019-05-01** là đầu Reiwa. Khi parse `YEAR_OF_ERA`, phải gắn đúng era; không ép tên era hoặc số năm vào một cột năm ISO.

### 13.3. Kiểm tra các calendar trong runtime

Chạy `Chronology.getAvailableChronologies()` trong môi trường deploy. Sắp xếp theo `getId()` để log ổn định nếu cần. Với locale extension `u-ca` không hỗ trợ, xử lý lỗi rõ ràng thay vì rơi vào một chronology khác mà không thông báo.

### 13.4. Kiểm tra bản địa hóa

Tạo formatter `ofLocalizedDate(FormatStyle.LONG)` với `Locale.JAPAN` và chronology Nhật, đối chiếu với `IsoChronology`. Không so sánh exact text của mọi locale trên các JDK khác nhau trừ khi đã pin data provider; tên era, dấu cách hoặc mô hình chữ số có thể thay đổi.

### 13.5. Kiểm tra parse nghiêm ngặt

Parse một ngày Thai Buddhist bằng formatter có `withChronology(ThaiBuddhistChronology.INSTANCE)` và `ResolverStyle.STRICT`; đổi ngược sang ISO bằng `LocalDate.from(...)`, xác nhận cùng epoch-day. Thử ngày không tồn tại theo calendar, thiếu era Nhật, calendar ID không được hỗ trợ, hoặc ngày ngoài phạm vi.

### 13.6. Kiểm tra dữ liệu nghiệp vụ

Nếu chỉ là UI localization, xác minh **đổi calendar không thay đổi đơn hàng, hạn thanh toán hoặc ngày sinh canonical**. Nếu nghiệp vụ thực sự dùng lịch âm/niên hiệu làm hợp đồng, ghi rõ calendar variant, quy tắc tính kỳ và xử lý thay đổi dữ liệu lịch; kiểm tra với chuyên gia miền nghiệp vụ khi cần.

## 14. Bài tập tự luyện và đáp án

**Bài 1.** Cùng một `LocalDate.of(2026, 10, 28)`, hệ Thai Buddhist cho năm bao nhiêu? Có thể dùng `plusYears(543)` để “đổi lịch” không?

**Đáp án:** Năm 2569. Không dùng `plusYears(543)` vì đó là phép dời ngày thực tế; hãy dùng `ThaiBuddhistChronology.INSTANCE.date(iso)` để biểu diễn **cùng epoch-day**.

**Bài 2.** `Chronology.ofLocale(Locale.forLanguageTag("th-TH"))` trả chronology nào theo JDK 17? Muốn Buddhist thì viết locale nào?

**Đáp án:** Mặc định ISO; dùng `th-TH-u-ca-buddhist` để yêu cầu Thai Buddhist calendar một cách tường minh.

**Bài 3.** Vì sao `JapaneseDate` của năm Reiwa 8 cần thông tin era khi parse?

**Đáp án:** Số 8 là năm trong niên hiệu, không phải năm ISO. Nhiều era có thể có năm 8; thiếu era thì không xác định đủ một ngày theo lịch Nhật.

**Bài 4.** Cùng ngày ISO 2026-10-28, lịch Minguo cho năm nào?

**Đáp án:** Năm Dân Quốc 115, vì năm đầu Dân Quốc tương ứng ISO 1912.

**Bài 5.** `withLocale(Locale.JAPAN)` có tự đổi chronology ISO thành Japanese không?

**Đáp án:** Không. Dùng `withChronology(JapaneseChronology.INSTANCE)` hoặc chronology được chọn tường minh từ locale có extension `u-ca-japanese`.

**Bài 6.** Cần so sánh hai `ChronoLocalDate` từ hai hệ lịch xem có chỉ cùng ngày thực tế không. Nên so sánh gì?

**Đáp án:** So sánh `toEpochDay()` hoặc dùng `ChronoLocalDate.timeLineOrder()`; không chỉ so sánh số YEAR, tháng, ngày.

**Bài 7.** Tại sao không thể đổi ngày Hijrah sang ISO bằng phép trừ một con số cố định từ năm?

**Đáp án:** Vì Hijrah là lịch âm, quy tắc tháng và năm khác ISO; cần chronology/variant và dữ liệu ngày hợp lệ.

**Bài 8.** `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withLocale(Locale.JAPAN)` có tự bảo đảm ngày được hiển thị theo niên hiệu Nhật không?

**Đáp án:** Không, localized formatter theo mặc định dùng ISO chronology. Để diễn đạt niên hiệu Nhật, gán chronology Nhật và dùng mẫu hiển thị phù hợp thể hiện era.

## 15. Tổng kết

- **`Chronology` mô hình hóa hệ lịch**, còn `Locale` mô tả ngôn ngữ/khu vực và `ZoneId` mô tả vùng thời gian.
- Java 17 tích hợp **ISO, Japanese, Minguo, ThaiBuddhist và Hijrah**; runtime có thể được mở rộng thêm.
- **Cùng một ngày, các năm khác nhau:** ISO 2026 tương ứng Thai Buddhist 2569, Minguo 115, Japanese Reiwa 8 trong ví dụ 28/10/2026.
- **Không tự cộng/trừ năm để đổi calendar**; dùng `Chronology.date(isoDate)`, `dateEpochDay` hoặc formatter `withChronology`.
- Chọn lịch tường minh bằng `Chronology.of(...)`, `INSTANCE` hoặc `Chronology.ofLocale(locale có `u-ca-...`)`. Language-region đơn thuần không có nghĩa lựa chọn calendar non-ISO.
- **Era và year-of-era là dữ liệu có ý nghĩa**, nhất là với Japanese chronology; cần pattern `G y` khi muốn biểu diễn năm theo niên hiệu.
- Đối với ứng dụng đa phần chỉ cần ISO, lưu/tính toán bằng `LocalDate`/`Instant` và **đổi chronology ở ranh giới UI**. Nghiệp vụ lịch âm thật sự cần quản lý calendar variant và quy tắc riêng.
- Khi parse non-ISO, dùng chronology chính xác và kiểm tra STRICT; so sánh ngày xuyên lịch bằng `EPOCH_DAY`.

### Tài liệu tham khảo Java 17 chính thức

- [java.time.chrono — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/chrono/package-summary.html)
- [Chronology — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/chrono/Chronology.html)
- [ChronoLocalDate — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/chrono/ChronoLocalDate.html)
- [DateTimeFormatter — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
