# Kiểm thử tiền tệ, ngày đầu tuần và múi giờ theo Locale (Java 10+)

## 1. Bài toán thực hành tổng hợp: cùng một giao dịch, nhiều quy ước địa phương

Một ứng dụng có người dùng ở Việt Nam, Hoa Kỳ, Pháp và Nhật Bản. Cùng một thời điểm giao dịch, UI có thể phải hiển thị:

- **Tiền tệ** theo một ngôn ngữ/vùng và **đồng tiền nghiệp vụ** thực sự của giao dịch.
- **Ngày bắt đầu tuần** theo thị trường, ví dụ tuần ở Hoa Kỳ thường bắt đầu Chủ nhật, Pháp bắt đầu Thứ hai.
- **Ngày/giờ** theo vùng địa lý mà người dùng hoặc sự kiện lựa chọn, ví dụ `America/New_York`, `Europe/Paris` hoặc `Asia/Ho_Chi_Minh`.

Ba nhu cầu này có vẻ đều “theo Locale”, nhưng **không phải một thứ**. Nếu dùng `Locale` để suy đoán múi giờ hoặc so chuỗi tiền tệ với literal cố định trên mọi JDK, bộ kiểm thử rất dễ sai.

Đây là bài thực hành tổng hợp trong module **Java 10**. API được dùng trong bài — `Locale.forLanguageTag`, `Currency`, `NumberFormat`, `WeekFields`, `Instant`, `ZoneId`, `DateTimeFormatter` — vẫn được hỗ trợ trên Java hiện hành. Chương trình chính biên dịch được bằng **Java 17+**. Riêng `DateTimeFormatter.localizedBy(Locale)` là tính năng đã xuất hiện từ **Java 10**, được dùng để giải thích trường hợp Locale chứa Unicode extension cho múi giờ.

### Mục tiêu

Học xong, bạn có thể:

1. Chọn `Locale` theo BCP 47, không phụ thuộc default locale của máy chạy test.
2. Dùng `Currency.getInstance(Locale)` lấy mã ISO 4217 và `NumberFormat.getCurrencyInstance(Locale)` để hiển thị tiền; không nhầm **đồng tiền** với **ký hiệu hiển thị**.
3. Dùng `WeekFields.of(Locale)` kiểm tra ngày đầu tuần và số ngày tối thiểu trong tuần thứ nhất; phân biệt với `WeekFields.ISO`.
4. Dùng `ZoneId`/`Instant`/`ZonedDateTime` để tính đúng thời điểm và offset; tách múi giờ khỏi quy ước ngôn ngữ.
5. Biết trường hợp đặc biệt `localizedBy(Locale)` có thể đọc Unicode extension `u-tz-...` và `WeekFields` có thể đọc `u-fw-...`.
6. Viết tests **ổn định ở tầng ý nghĩa** thay vì bắt cứng những chuỗi có thể đổi bởi CLDR, locale provider hoặc phiên bản TZDB.
7. Kiểm tra ranh giới năm/tuần, DST gap/overlap, fraction digits và timezone offset.
8. Nhận biết những khẳng định phụ thuộc dữ liệu JDK cần được **pin environment hoặc review khi cập nhật runtime**.
9. Tạo một chương trình kiểm chứng **có assertions thật**, trả nonzero khi expectation không đúng.

**Quy ước:** số tiền là giá trị nghiệp vụ kiểu `BigDecimal`; Locale là quy ước biểu diễn; Currency là đơn vị thanh toán; ZoneId là quy tắc thời gian của một vùng; Instant là thời điểm tuyệt đối. Đừng gộp bốn đại lượng đó vào một biến “country”.

## 2. Phân biệt rõ ba câu hỏi

| Câu hỏi nghiệp vụ | API chính | Giá trị đầu vào đúng | Giá trị KHÔNG tự suy ra |
| --- | --- | --- | --- |
| “Đơn vị tiền và cách hiển thị?” | `Currency`, `NumberFormat` | Currency code và Locale | Locale không cho biết chắc đồng tiền của giao dịch |
| “Tuần bắt đầu ngày nào?” | `WeekFields.of(locale)` | Locale hoặc quy tắc lịch nghiệp vụ | Không thể đồng nhất với ISO Monday cho mọi quốc gia |
| “Sự kiện diễn ra lúc mấy giờ ở đâu?” | `Instant`, `ZoneId`, `ZonedDateTime` | Instant + ZoneId/IANA region | Locale thường không xác định múi giờ duy nhất |

Ví dụ một người dùng có `Locale.forLanguageTag("fr-FR")` nhưng đang xem sự kiện tổ chức ở New York. Họ có thể muốn:

- tiền thanh toán: `USD` (vì giao dịch được chốt bằng đô-la);
- cách định dạng số và ngày: `fr-FR` (ngôn ngữ Pháp);
- tuần lịch: có thể theo Pháp, ngày đầu `MONDAY`;
- múi giờ sự kiện: `America/New_York` (mặc dù ngôn ngữ của người dùng là Pháp).

Chọn `Europe/Paris` chỉ vì Locale có region `FR` sẽ **đổi sai thời điểm hiển thị của sự kiện**. Một quốc gia cũng có thể có nhiều múi giờ, nên không có phép ánh xạ tổng quát `Locale → ZoneId` chính xác cho mọi người dùng.

### Trục thứ tư: bản ghi nghiệp vụ có thể có quy tắc cố định

Một doanh nghiệp có thể định nghĩa “tuần doanh thu bắt đầu Thứ hai” cho tất cả thị trường, bất kể Locale. Khi đó dùng `WeekFields.ISO` hoặc `WeekFields.of(DayOfWeek.MONDAY, 4)` theo contract nghiệp vụ, **không** vô thức dùng `WeekFields.of(userLocale)`. Chọn đúng chính sách quan trọng hơn máy tính có dữ liệu locale gì.

## 3. Tạo Locale đúng cách trên JDK hiện hành

### 3.1. BCP 47 language tags

Dùng:

```java
Locale us = Locale.forLanguageTag("en-US");
Locale fr = Locale.forLanguageTag("fr-FR");
Locale jp = Locale.forLanguageTag("ja-JP");
Locale vn = Locale.forLanguageTag("vi-VN");
```

Đây là **đoạn minh họa trong phương thức**, thêm `import java.util.Locale;` khi dùng. `Locale.forLanguageTag` hỗ trợ cú pháp IETF BCP 47 và được hỗ trợ trên Java 17+.

Các thành phần chính:

- `en`, `fr`, `ja`, `vi`: **language**.
- `US`, `FR`, `JP`, `VN`: **region**.
- BCP 47 còn có script/variant và Unicode locale extensions (`u-...`).

Đừng dùng `Locale.toString()` làm định danh bền vững trong dữ liệu liên hệ đa hệ thống; để trao đổi nên dùng `toLanguageTag()` và các trường riêng đã xác minh.

### 3.2. Không dùng các constructors đã deprecated cho code mới

Trên JDK hiện đại, constructors như `new Locale("en", "US")` đã được **deprecated từ Java 19**. Mặc dù từng được dùng phổ biến, không nên tiếp tục đề xuất như cách viết mới.

Ưu tiên `Locale.forLanguageTag("en-US")` hoặc `Locale.Builder`. `Locale.of(...)` cũng có trên JDK mới nhưng **được bổ sung sau Java 17**; để ví dụ chạy từ Java 17, bài chọn `forLanguageTag`.

### 3.3. Locale không nhất thiết có region

`Locale.forLanguageTag("en")` chỉ có language, không có country code. `Currency.getInstance(locale)` cần thông tin quốc gia/vùng được xác định hợp lệ và có thể ném `IllegalArgumentException` nếu không có country.

**Không** luôn giả định `Locale.getDefault()` có region hợp lệ để suy đồng tiền. Nếu người dùng chỉ chọn ngôn ngữ `en`, ứng dụng phải lấy country/currency từ hồ sơ, hợp đồng, địa điểm thanh toán hoặc lựa chọn explicit của người dùng.

### 3.4. Default DISPLAY và FORMAT locales

Java phân biệt:

- `Locale.getDefault(Locale.Category.DISPLAY)`: mặc định cho tên/nhãn hiển thị.
- `Locale.getDefault(Locale.Category.FORMAT)`: mặc định cho định dạng ngày/số/tiền.
- `Locale.getDefault()`: default chung của VM.

Các factory methods không truyền Locale có thể dùng `FORMAT` default. Vì vậy một test:

```java
NumberFormat.getCurrencyInstance().format(1234.50)
```

có thể cho output khác trên developer laptop và CI runner.

**Trong kiểm thử, truyền Locale tường minh.** Tránh dùng `Locale.setDefault(...)` trong các unit tests chạy song song: đó là thay đổi **trạng thái toàn cục** có thể ảnh hưởng tests khác. Nếu bắt buộc test default locale, tách process hoặc bảo đảm isolation và restore state đúng.

## 4. Kiểm thử tiền tệ: mã ISO 4217 khác chuỗi hiển thị

### 4.1. Lấy Currency theo region

```java
Locale locale = Locale.forLanguageTag("vi-VN");
Currency currency = Currency.getInstance(locale);
String isoCode = currency.getCurrencyCode(); // VND trong JDK test
```

API `Currency.getInstance(Locale)` gắn đồng tiền với **quốc gia/vùng của Locale**, không lấy language làm khóa chính. JDK có thể cập nhật dữ liệu khi quốc gia đổi đơn vị tiền theo thời gian. Nó cũng có thể trả `null` với vùng không có tiền tệ.

Bảng snapshot đã kiểm thử trên OpenJDK 24.0.2:

| Locale | ISO code | Default fraction digits |
| --- | --- | ---: |
| `en-US` | `USD` | 2 |
| `fr-FR` | `EUR` | 2 |
| `ja-JP` | `JPY` | 0 |
| `vi-VN` | `VND` | 0 |

`getDefaultFractionDigits()` là số chữ số thập phân mặc định theo dữ liệu đồng tiền; nó **không** là quy định toàn bộ nghiệp vụ rounding của từng hệ thống thanh toán. Khi xử lý lượng tiền, định nghĩa đơn vị, scale, rounding, tax, cash rounding và phương thức thanh toán theo contract.

### 4.2. Dùng `BigDecimal` để biểu diễn tiền

```java
BigDecimal amount = new BigDecimal("1234.50");
```

Tạo `BigDecimal` từ chuỗi literal thập phân giúp tránh biểu diễn nhị phân không chính xác của `double` đối với các phép tính tiền tệ. Không truyền `new BigDecimal(0.1)` rồi mong lưu giá trị decimal chính xác bằng `0.1`.

**Cần phân biệt số tiền với currency code.** Một `BigDecimal("100")` không nói đó là 100 VND, 100 EUR hay 100 JPY. Ứng dụng nên lưu **currency code** bên cạnh số tiền (ví dụ mô hình Money domain), tránh dựa vào Locale của user.

### 4.3. Định dạng theo Locale

```java
NumberFormat fmt = NumberFormat.getCurrencyInstance(locale);
String display = fmt.format(amount);
```

Với cùng amount, output có thể khác theo:

- dấu phân cách nghìn/thập phân;
- vị trí ký hiệu tiền;
- ký hiệu `$`/`€`/`¥`/`₫` hoặc mã ISO;
- khoảng trắng thường, NBSP, narrow NBSP;
- số chữ số phần thập phân;
- dữ liệu CLDR và locale provider của runtime.

Các mẫu người đọc có thể gặp (minh họa, **không** dùng làm literal assertion cho mọi JDK):

```text
en-US: $1,234.50
fr-FR: 1 234,50 €
ja-JP: ￥1,234
vi-VN: 1.234 ₫
```

Các ký tự khoảng trắng trong các hệ hiển thị có thể là Unicode NBSP/narrow NBSP; đừng dùng `trim()` hay một phép thay thế tùy tiện rồi giả định kết quả vẫn nguyên ngữ nghĩa.

### 4.4. Viết test chống giòn do Unicode/CLDR

**Nên kiểm tra:**

- `Currency.getInstance(locale).getCurrencyCode()` khớp code business hoặc expected snapshot;
- `fmt.getCurrency()` là Currency mà formatter đang sử dụng;
- chuỗi hiển thị không rỗng;
- dấu/chiều phần thập phân chỉ được kiểm tra theo chính sách nếu cần;
- khi parse lại, phải biết chính xác formatter, locale và rounding policy.

**Tránh:**

```java
// Ví dụ fragile, không phải assertion khuyến nghị.
assert formatted.equals("1 234,50 €");
```

Nó có thể fail vì ``Space` thường khác NBSP/narrow NBSP mà không phải lỗi định dạng của JDK.

### 4.5. `setCurrency` không tự đổi fraction digits

Trường hợp giao dịch bằng CHF nhưng người dùng chọn `en-US`:

```java
NumberFormat fmt = NumberFormat.getCurrencyInstance(
        Locale.forLanguageTag("en-US"));
fmt.setCurrency(Currency.getInstance("CHF"));
```

**Điểm dễ bỏ sót:** theo API `NumberFormat.setCurrency`, việc đổi currency **không tự cập nhật** min/max fraction digits của formatter. Nếu nghiệp vụ cần format theo fraction digits mới, phải cấu hình rõ scale/fraction digits theo chính sách, không mặc định chỉ `setCurrency` là đủ.

Nếu payment amount bằng VND nhưng Locale là Pháp, không được lấy EUR chỉ vì `fr-FR`. Đặt Currency theo **đồng tiền của giao dịch**, giữ Locale theo **quy ước hiển thị**. Đây là hai chiều độc lập.

### 4.6. `NumberFormat` là đối tượng mutable

`NumberFormat`/`DecimalFormat` có các setters và có thể không thread-safe cho concurrent access. Không lưu một instance dùng chung rồi gọi `setCurrency` thay đổi liên tục giữa các requests. Tạo formatter theo request, dùng clone/pool có thread confinement hoặc thiết kế cache không sửa đồng thời.

`Currency`/`Locale` là những đối tượng dữ liệu phù hợp để dùng lại; formatter mutable cần cách quản lý riêng.

### 4.7. Dữ liệu tiền tệ là snapshot theo runtime

`Currency.getInstance(locale)` dùng database của Java runtime; quốc gia có thể thay đổi currency theo thời gian. Nếu bạn bắt cứng “Country X luôn dùng currency Y” trong dữ liệu kế toán đã lưu từ nhiều năm, có thể diễn giải sai lịch sử.

Với giao dịch, **lưu currency ISO code tại thời điểm transaction**. Dùng locale lookup chỉ để lựa chọn/defaults UI, có khả năng override khi contract yêu cầu.

## 5. Kiểm thử ngày đầu tuần bằng `WeekFields.of(Locale)`

### 5.1. Tuần có hai tham số chứ không chỉ một

`WeekFields` mô tả:

1. `getFirstDayOfWeek()` — ngày nào bắt đầu tuần.
2. `getMinimalDaysInFirstWeek()` — tối thiểu có bao nhiêu ngày thuộc năm mới để tính là **tuần số 1**.

Ví dụ snapshot đã kiểm thử:

| Locale | First day | Minimal days in first week |
| --- | --- | ---: |
| `en-US` | `SUNDAY` | 1 |
| `fr-FR` | `MONDAY` | 4 |
| `ja-JP` | `SUNDAY` | 1 |
| `vi-VN` | `MONDAY` | 1 |

**Chú ý:** `vi-VN` bắt đầu tuần vào Thứ hai trong dữ liệu JDK thử nghiệm nhưng có `minimalDays=1`, **khác** `WeekFields.ISO` có Monday và `minimalDays=4`. Vì thế chỉ check ngày bắt đầu chưa đủ nếu phần mềm tính `week-of-year`.

Dữ liệu tuần đến từ locale service provider/CLDR của runtime và có thể cập nhật. Các kỳ vọng chi tiết theo vùng cần được **review** khi nâng JDK/CLDR.

### 5.2. `WeekFields.ISO` là quy tắc riêng

`WeekFields.ISO` định nghĩa:

- ngày đầu tuần: `MONDAY`;
- tối thiểu 4 ngày trong tuần đầu của năm.

`WeekFields.of(Locale.US)` thông thường **khác** ISO. `WeekFields.of(Locale.FRANCE)` trong snapshot bài học **trùng** quy tắc ISO, nhưng không nên lấy đó làm định nghĩa của ISO. ISO là chuẩn, Locale là nguồn dữ liệu văn hóa/vùng.

### 5.3. Ngày 1/1 có thể thuộc week-based-year trước

Ví dụ `LocalDate.of(2021, 1, 1)`:

| Chính sách tuần | Week-based-year | Week number |
| --- | ---: | ---: |
| `WeekFields.of(Locale.US)` | 2021 | 1 |
| `WeekFields.of(Locale.FRANCE)` | 2020 | 53 |
| `WeekFields.ISO` | 2020 | 53 |

Đây là ví dụ quan trọng về **ranh giới năm**: ngày dương lịch 1/1/2021 có thể thuộc **tuần 53 của week-based-year 2020**. Không lấy `date.getYear()` rồi ghép với `weekOfWeekBasedYear()` một cách mù quáng.

### 5.4. Truy vấn đầy đủ các thành phần tuần

```java
WeekFields wf = WeekFields.of(locale);
LocalDate date = LocalDate.of(2021, 1, 1);

int week = date.get(wf.weekOfWeekBasedYear());
int weekYear = date.get(wf.weekBasedYear());
DayOfWeek first = wf.getFirstDayOfWeek();
int minimal = wf.getMinimalDaysInFirstWeek();
```

Đoạn trên minh họa trong một method, chưa khai báo/import đủ khi đứng riêng. Kiểm thử cần so **cặp `weekYear + week`**, không chỉ so tuần.

### 5.5. Khi muốn tìm đầu tuần của một LocalDate

```java
LocalDate startOfWeek = date.with(
        TemporalAdjusters.previousOrSame(wf.getFirstDayOfWeek()));
```

Với một `LocalDate`, đây là cách đặt ngày về đầu tuần theo quy tắc Locale. **Không** cần đổi múi giờ trong phép tính ngày thuần, vì `LocalDate` chưa đại diện cho một thời điểm cụ thể trên timeline.

**Nhưng** khi dữ liệu ban đầu là `Instant`, hãy chuyển `Instant` sang `ZoneId` cần thiết **trước khi** lấy `toLocalDate()`, nếu không ngày có thể khác khi sự kiện gần nửa đêm ở múi giờ khác.

### 5.6. Unicode `fw` extension có thể override ngày đầu tuần

BCP 47 locale:

```java
Locale mondayUS = Locale.forLanguageTag("en-US-u-fw-mon");
DayOfWeek first = WeekFields.of(mondayUS).getFirstDayOfWeek();
```

Trong JDK thử nghiệm, kết quả là `MONDAY` thay vì `SUNDAY` của `en-US` thông thường. Unicode extension này có thể thể hiện preference hoặc policy đã được biểu diễn trong locale identifier.

**Không** mặc định tước bỏ locale extensions khi yêu cầu là “dựa theo preference user” mà không đánh giá ảnh hưởng. Ngược lại, nếu ứng dụng bắt buộc ISO, đừng để một Unicode `fw` extension vô tình thay đổi quy tắc nghiệp vụ; dùng `WeekFields.ISO` explicit.

### 5.7. Pattern `Y` khác `y`

Trong `DateTimeFormatter` pattern:

- `y` là **year-of-era** cho ngày dương lịch theo chronology tương ứng;
- `Y` là **localized week-based-year**;
- `w` là tuần trong week-based-year;
- `W` là tuần trong tháng;
- `E` là tên thứ; `e`/`c` có kiểu localized day-of-week.

Vào ranh giới tháng 12/1, pattern `YYYY-MM-dd` có thể hiển thị **năm theo tuần** khác **năm dương lịch**, gây dữ liệu nhìn sai dù `LocalDate` không đổi. Nếu cần ngày lịch, ưu tiên `uuuu-MM-dd` theo ISO local date; nếu cần tuần, dùng `WeekFields.weekBasedYear()/weekOfWeekBasedYear()` hoặc pattern đã được kiểm thử theo Locale.

## 6. Múi giờ: Locale là cách biểu diễn, `ZoneId` là quy tắc thời gian

### 6.1. Hai người có thể dùng cùng Locale nhưng ở hai múi giờ

Ví dụ những người dùng cùng `Locale.US` có thể sống ở New York, Los Angeles, Honolulu. Ngược lại, một người dùng `Locale.FRANCE` có thể đang đi công tác ở Nhật.

Vì vậy:

```java
Locale locale = Locale.forLanguageTag("fr-FR");
ZoneId zone = ZoneId.of("America/New_York");
```

là tổ hợp hợp lệ. `Locale` kiểm soát cách hiển thị, còn `ZoneId` kiểm soát **cách chuyển một thời điểm thành ngày/giờ địa phương**.

Không dựa vào `Locale.getCountry()` để đoán IANA zone. Những ánh xạ country-to-default-zone là **business preferences** cần hỏi hoặc xác nhận, không là phép suy toàn cục đáng tin.

### 6.2. `Instant`, `ZonedDateTime`, `LocalDateTime` khác nhau

| Kiểu | Có biết thời điểm tuyệt đối? | Có biết zone/rules? | Dùng khi |
| --- | --- | --- | --- |
| `Instant` | **Có** | Là timeline UTC, không gắn region zone | Thời điểm sự kiện, log, giao dịch |
| `ZonedDateTime` | **Có**, với ngày/giờ + zone/offset | **Có** | Lịch/sự kiện theo region và DST |
| `OffsetDateTime` | **Có** | Chỉ biết fixed offset, không biết đầy đủ region rules | API payload có offset |
| `LocalDateTime` | **Chưa** | **Không** | Giờ địa phương chưa gắn zone, cấu hình giờ làm việc |
| `LocalDate` | **Chưa** | **Không** | Ngày lịch không phụ thuộc giờ |

Đừng lưu một `LocalDateTime` như một thời điểm giao dịch mà không lưu **zone/offset** hoặc quy tắc chuyển đổi, vì nó có thể rơi vào một DST gap/overlap.

### 6.3. Dùng region-based IANA ZoneId

Ví dụ:

```java
ZoneId.of("America/New_York");
ZoneId.of("Europe/Paris");
ZoneId.of("Asia/Tokyo");
ZoneId.of("Asia/Ho_Chi_Minh");
```

Đây là những zone IDs rõ ràng và được hỗ trợ trên JDK test. Chúng có **ZoneRules** lịch sử và các quy tắc chuyển giờ. Đừng dùng abbreviations mơ hồ như `CST` cho dữ liệu nghiệp vụ: có nhiều cách hiểu giữa các vùng, và một số short IDs đã bị deprecated/đổi mapping theo bản TZDB.

### 6.4. Không nhầm offset với time zone region

`ZoneOffset.ofHours(1)` là fixed offset `+01:00`, không biết Paris dùng `+02:00` trong mùa hè.

`ZoneId.of("Europe/Paris")` dùng region rules; đầu tháng 1 năm 2024 là `+01:00`, giữa tháng 7 năm 2024 là `+02:00` trong dữ liệu JDK đã thử. Nếu bạn chọn fixed `+01:00` cho tất cả thời điểm Paris, lịch mùa hè sẽ sai.

### 6.5. Cùng một Instant, bốn cách hiển thị thời gian

Bài dùng hai thời điểm cố định:

```text
WINTER = 2024-01-15T12:00:00Z
SUMMER = 2024-07-15T12:00:00Z
```

Kết quả offset đã kiểm thử trên OpenJDK 24.0.2:

| ZoneId | January offset | July offset |
| --- | --- | --- |
| `America/New_York` | `-05:00` | `-04:00` |
| `Europe/Paris` | `+01:00` | `+02:00` |
| `Asia/Tokyo` | `+09:00` | `+09:00` |
| `Asia/Ho_Chi_Minh` | `+07:00` | `+07:00` |

**Đây là dữ liệu vùng và thời điểm, không được suy ra từ Locale.** Các offset lịch sử và tương lai phụ thuộc TZDB; chính phủ có thể sửa quy tắc, và runtime được cập nhật. Với CI muốn tái lập tuyệt đối, **pin JDK/tzdb build** và đánh giá snapshot khi nâng.

### 6.6. DST gap và overlap

Trong `America/New_York`:

- **2024-03-10 02:30** là local time thuộc **gap** khi đồng hồ nhảy qua (không có offset hợp lệ).
- **2024-11-03 01:30** là local time **overlap** khi đồng hồ lùi (có hai offset hợp lệ).

Dùng:

```java
ZoneId ny = ZoneId.of("America/New_York");

int gapOffsets = ny.getRules()
        .getValidOffsets(LocalDateTime.of(2024, 3, 10, 2, 30)).size();

int overlapOffsets = ny.getRules()
        .getValidOffsets(LocalDateTime.of(2024, 11, 3, 1, 30)).size();
```

Snapshot trong JDK test là `gapOffsets=0` và `overlapOffsets=2`. **Đừng** mặc định mọi LocalDateTime luôn tương ứng đúng một Instant.

Khi ứng dụng nhận giờ địa phương từ người dùng, cần thiết kế policy cho gap/overlap: báo lỗi, hỏi chọn offset hoặc xử lý theo quy tắc đã thống nhất. Không tự quy đổi bằng phép cộng giờ thủ công.

## 7. DateTimeFormatter: hiển thị theo Locale và ZoneId explicit

### 7.1. Cách an toàn, rõ nghĩa

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.FULL)
                .withLocale(locale)
                .withZone(zone);

String label = formatter.format(instant);
```

- `ofLocalizedDateTime(FormatStyle.FULL)` chọn style bản địa hóa.
- `withLocale(locale)` chọn ngôn ngữ và mẫu trình bày.
- `withZone(zone)` chọn zone dùng để chuyển từ `Instant` sang local date/time.
- `format(instant)` sử dụng cả hai dữ liệu.

**Không hard-code `label`** trong test cross-JDK: CLDR có thể đổi tên ngày, vị trí dấu phẩy, ký tự Unicode, tên múi giờ hay cụm từ “Giờ mùa hè”.

Thay vào đó, kiểm tra `formatter.getLocale()`/`formatter.getZone()`, label không rỗng và logic Instant-to-zone đúng.

### 7.2. `withLocale` không tự chuyển sang zone của quốc gia

`withLocale(Locale.FRANCE)` chủ yếu thay cách bản địa hóa text/pattern. Một formatter đã có `withZone(ZoneId.of("Europe/Paris"))` vẫn giữ zone Paris nếu thay Locale thành `en-US`.

Trong demo ta kiểm tra cùng **zone Paris** được giữ khi tạo formatter English và French. Đây là minh chứng hai lựa chọn **độc lập**.

### 7.3. Ngoại lệ quan trọng từ Java 10: `localizedBy(Locale)`

`DateTimeFormatter.localizedBy(Locale)` được bổ sung **từ Java 10**. Không giống `withLocale` chỉ đặt locale override, `localizedBy` còn có thể lấy **calendar**, **numbering system**, **region override** và **timezone** từ Unicode extensions:

- `u-ca-...` cho chronology/calendar;
- `u-nu-...` cho numbering system;
- `u-rg-...` cho region override;
- `u-tz-...` cho múi giờ.

Ví dụ đã kiểm chứng trên JDK 24:

```java
Locale special = Locale.forLanguageTag("en-US-u-tz-usnyc");

DateTimeFormatter a = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.FULL)
        .withLocale(special);

DateTimeFormatter b = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.FULL)
        .localizedBy(special);
```

- `a.getZone()` vẫn `null` nếu formatter gốc chưa có zone override.
- `b.getZone()` là `America/New_York` trong dữ liệu locale/tz mappings JDK test.

**Cần biết chi tiết này để không tuyên bố quá mức rằng “Locale không bao giờ ảnh hưởng múi giờ”.** Đúng hơn: **Locale thường chỉ chọn quy ước hiển thị; để nghiệp vụ chắc chắn, hãy truyền ZoneId explicit**. API `localizedBy` có cơ chế riêng để áp Unicode tz extension theo hợp đồng JDK 10+.

### 7.4. Thứ tự gọi `localizedBy` và `withZone` có ý nghĩa

Theo tài liệu API, `localizedBy` có thể override zone đã đặt nếu Locale chứa Unicode `tz`. Do đó thứ tự:

```java
base.withZone(zone).localizedBy(localeWithTzExtension)
```

có thể không tương đương:

```java
base.localizedBy(localeWithTzExtension).withZone(zone)
```

Nếu hệ thống nghiệp vụ yêu cầu một zone explicit ưu tiên mọi user locale extensions, đặt `withZone(zone)` ở cuối hoặc chọn `withLocale(locale)` khi chỉ cần localized text, và thêm test cho thứ tự để tránh regression.

### 7.5. FormatStyle.FULL cần zone khi định dạng thời điểm

Theo API, formatters localized **LONG/FULL** thường cần thông tin múi giờ khi biểu diễn thời gian. Khi input là `Instant`, truyền zone bằng `withZone`; hoặc dùng `ZonedDateTime` chứa zone.

**Không** tưởng rằng `Locale.forLanguageTag("fr-FR")` là đủ để định dạng `Instant` thành ngày giờ Paris. Thiếu zone có thể gây `DateTimeException` hoặc thiếu ngữ cảnh time-zone.

## 8. Bộ dữ liệu kiểm thử: bốn vùng, hai thời điểm, một ranh giới năm

Bộ lab sử dụng:

| Case | Locale tag | Currency kỳ vọng | Week first/min | ZoneId explicit |
| --- | --- | --- | --- | --- |
| US | `en-US` | `USD` | `SUNDAY` / 1 | `America/New_York` |
| France | `fr-FR` | `EUR` | `MONDAY` / 4 | `Europe/Paris` |
| Japan | `ja-JP` | `JPY` | `SUNDAY` / 1 | `Asia/Tokyo` |
| Vietnam | `vi-VN` | `VND` | `MONDAY` / 1 | `Asia/Ho_Chi_Minh` |

**Dữ liệu kỳ vọng là snapshot thực nghiệm trên OpenJDK 24.0.2.** Vì locale/currency/tzdb data có thể thay đổi, đây là **regression matrix**: nếu một JDK cập nhật làm khác kỳ vọng, cần xác định đó là thay đổi dữ liệu hợp lệ hay bug của ứng dụng trước khi sửa test.

Một quy tắc tốt: tách **bất biến API** (ví dụ SHA? Không liên quan; ở đây là `Instant` không phụ thuộc zone, một tuần có 7 ngày, Currency có ISO code) khỏi **snapshot địa phương hóa** (USD/EUR/JPY/VND, first-day, translated labels, tz offsets của thời điểm test).

## 9. Chương trình Java 17+ độc lập, có assertions thật

Chương trình sau là một **test harness chạy được** với JDK chuẩn, không cần JUnit hoặc thư viện ngoài:

- dùng Locale, Currency và NumberFormat;
- kiểm tra first day/minimal days qua WeekFields;
- đo offsets của hai Instants cố định;
- xác nhận tuần 1/1/2021 ở US/France/ISO;
- kiểm tra DST gap/overlap của New York;
- kiểm tra Unicode `fw` và `tz` extensions;
- phân biệt `withLocale`/`localizedBy`;
- tự fail bằng `AssertionError` nếu expectations khác, thay vì chỉ in `false` rồi exit code 0.

**Lưu file `LocaleCurrencyWeekZone428.java`:**

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.DayOfWeek;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.time.temporal.WeekFields;
import java.util.Currency;
import java.util.List;
import java.util.Locale;

public final class LocaleCurrencyWeekZone428 {
    private static final Instant WINTER =
            Instant.parse("2024-01-15T12:00:00Z");
    private static final Instant SUMMER =
            Instant.parse("2024-07-15T12:00:00Z");

    private record Scenario(
            String tag,
            String currencyCode,
            int fractionDigits,
            DayOfWeek firstDay,
            int minimalDays,
            String zoneId,
            String winterOffset,
            String summerOffset) {}

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void verify(Scenario s) {
        Locale locale = Locale.forLanguageTag(s.tag());
        Currency currency = Currency.getInstance(locale);
        WeekFields weeks = WeekFields.of(locale);
        ZoneId zone = ZoneId.of(s.zoneId());

        check(currency != null, "missing currency: " + s.tag());
        check(currency.getCurrencyCode().equals(s.currencyCode()),
                "currency code changed: " + s.tag());
        check(currency.getDefaultFractionDigits() == s.fractionDigits(),
                "fraction digits changed: " + s.tag());
        check(weeks.getFirstDayOfWeek() == s.firstDay(),
                "first day changed: " + s.tag());
        check(weeks.getMinimalDaysInFirstWeek() == s.minimalDays(),
                "minimal days changed: " + s.tag());

        String winterOffset = WINTER.atZone(zone).getOffset().getId();
        String summerOffset = SUMMER.atZone(zone).getOffset().getId();
        check(winterOffset.equals(s.winterOffset()),
                "winter offset changed: " + s.zoneId());
        check(summerOffset.equals(s.summerOffset()),
                "summer offset changed: " + s.zoneId());

        NumberFormat money = NumberFormat.getCurrencyInstance(locale);
        check(currency.equals(money.getCurrency()),
                "formatter currency changed: " + s.tag());
        String formatted = money.format(new BigDecimal("1234.50"));
        check(!formatted.isBlank(), "empty money text: " + s.tag());

        DateTimeFormatter dateTime =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.FULL)
                        .withLocale(locale)
                        .withZone(zone);
        check(!dateTime.format(WINTER).isBlank(),
                "empty localized time text: " + s.tag());
        check(zone.equals(dateTime.getZone()),
                "zone override lost: " + s.tag());

        System.out.printf(Locale.ROOT,
                "locale=%s currency=%s digits=%d first=%s min=%d "
                        + "zone=%s winter=%s summer=%s moneyTextPresent=true%n",
                s.tag(), currency.getCurrencyCode(),
                currency.getDefaultFractionDigits(),
                weeks.getFirstDayOfWeek(),
                weeks.getMinimalDaysInFirstWeek(),
                zone.getId(), winterOffset, summerOffset);
    }

    public static void main(String[] args) {
        List<Scenario> scenarios = List.of(
                new Scenario("en-US", "USD", 2, DayOfWeek.SUNDAY, 1,
                        "America/New_York", "-05:00", "-04:00"),
                new Scenario("fr-FR", "EUR", 2, DayOfWeek.MONDAY, 4,
                        "Europe/Paris", "+01:00", "+02:00"),
                new Scenario("ja-JP", "JPY", 0, DayOfWeek.SUNDAY, 1,
                        "Asia/Tokyo", "+09:00", "+09:00"),
                new Scenario("vi-VN", "VND", 0, DayOfWeek.MONDAY, 1,
                        "Asia/Ho_Chi_Minh", "+07:00", "+07:00")
        );
        scenarios.forEach(LocaleCurrencyWeekZone428::verify);

        LocalDate firstJanuary = LocalDate.of(2021, 1, 1);
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields fr = WeekFields.of(Locale.FRANCE);
        WeekFields iso = WeekFields.ISO;

        int usYear = firstJanuary.get(us.weekBasedYear());
        int usWeek = firstJanuary.get(us.weekOfWeekBasedYear());
        int frYear = firstJanuary.get(fr.weekBasedYear());
        int frWeek = firstJanuary.get(fr.weekOfWeekBasedYear());
        int isoYear = firstJanuary.get(iso.weekBasedYear());
        int isoWeek = firstJanuary.get(iso.weekOfWeekBasedYear());

        check(usYear == 2021 && usWeek == 1, "US year boundary");
        check(frYear == 2020 && frWeek == 53, "FR year boundary");
        check(isoYear == 2020 && isoWeek == 53, "ISO year boundary");
        System.out.println("jan1_2021_US=" + usYear + "-W" + usWeek);
        System.out.println("jan1_2021_FR=" + frYear + "-W" + frWeek);
        System.out.println("jan1_2021_ISO=" + isoYear + "-W" + isoWeek);

        ZoneId newYork = ZoneId.of("America/New_York");
        int gap = newYork.getRules()
                .getValidOffsets(LocalDateTime.of(2024, 3, 10, 2, 30))
                .size();
        int overlap = newYork.getRules()
                .getValidOffsets(LocalDateTime.of(2024, 11, 3, 1, 30))
                .size();
        check(gap == 0 && overlap == 2, "New York DST transition");
        System.out.println("nyGapValidOffsets=" + gap);
        System.out.println("nyOverlapValidOffsets=" + overlap);

        DayOfWeek mondayOverride = WeekFields.of(
                Locale.forLanguageTag("en-US-u-fw-mon"))
                .getFirstDayOfWeek();
        check(mondayOverride == DayOfWeek.MONDAY,
                "Unicode fw extension");
        System.out.println("unicodeFwFirstDay=" + mondayOverride);

        ZoneId paris = ZoneId.of("Europe/Paris");
        DateTimeFormatter base =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.FULL)
                        .withZone(paris);
        DateTimeFormatter english = base.withLocale(Locale.US);
        DateTimeFormatter french = base.withLocale(Locale.FRANCE);
        check(paris.equals(english.getZone())
                        && paris.equals(french.getZone()),
                "withLocale changed explicit zone");
        check(!english.format(WINTER).isBlank()
                        && !french.format(WINTER).isBlank(),
                "localized label is blank");
        System.out.println("withLocaleKeepsExplicitZone=true");

        Locale timeZoneExtension =
                Locale.forLanguageTag("en-US-u-tz-usnyc");
        DateTimeFormatter unlocalized =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.FULL)
                        .withLocale(timeZoneExtension);
        DateTimeFormatter localized =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.FULL)
                        .localizedBy(timeZoneExtension);
        check(unlocalized.getZone() == null, "withLocale zone");
        check(newYork.equals(localized.getZone()),
                "localizedBy Unicode tz extension");
        System.out.println("localizedByTzZone=" + localized.getZone());

        boolean languageOnlyRejected = false;
        try {
            Currency.getInstance(Locale.forLanguageTag("en"));
        } catch (IllegalArgumentException expected) {
            languageOnlyRejected = true;
        }
        check(languageOnlyRejected, "currency needs region");
        System.out.println("languageOnlyCurrencyRejected=true");

        check(WINTER.atZone(paris).toInstant()
                        .equals(WINTER.atZone(newYork).toInstant()),
                "an Instant must be zone independent");
        System.out.println("sameInstantAcrossZones=true");
        System.out.println("allChecksPassed=true");
    }
}
```

### 9.1. Biên dịch

```bash
javac --release 17 -encoding UTF-8 LocaleCurrencyWeekZone428.java
```

`--release 17` yêu cầu API/source/bytecode tương thích Java 17. Program dùng `record` (đã được chuẩn hóa từ JDK 16), các `java.time` APIs và `NumberFormat`; không dùng API Java 19+ để giữ tương thích với Java 17.

### 9.2. Chạy

```bash
java LocaleCurrencyWeekZone428
```

**Stdout chính xác đã kiểm chứng trên OpenJDK 24.0.2 (CLDR/TZDB của bản JDK thử nghiệm):**

```text
locale=en-US currency=USD digits=2 first=SUNDAY min=1 zone=America/New_York winter=-05:00 summer=-04:00 moneyTextPresent=true
locale=fr-FR currency=EUR digits=2 first=MONDAY min=4 zone=Europe/Paris winter=+01:00 summer=+02:00 moneyTextPresent=true
locale=ja-JP currency=JPY digits=0 first=SUNDAY min=1 zone=Asia/Tokyo winter=+09:00 summer=+09:00 moneyTextPresent=true
locale=vi-VN currency=VND digits=0 first=MONDAY min=1 zone=Asia/Ho_Chi_Minh winter=+07:00 summer=+07:00 moneyTextPresent=true
jan1_2021_US=2021-W1
jan1_2021_FR=2020-W53
jan1_2021_ISO=2020-W53
nyGapValidOffsets=0
nyOverlapValidOffsets=2
unicodeFwFirstDay=MONDAY
withLocaleKeepsExplicitZone=true
localizedByTzZone=America/New_York
languageOnlyCurrencyRejected=true
sameInstantAcrossZones=true
allChecksPassed=true
```

**Quan trọng:** đây là stdout đã được kiểm chứng cho **JDK build test**, không phải lời hứa các bảng CLDR/TZDB luôn giữ nguyên sau mọi lần update JDK. Các dòng snapshot về first day/currency/offset sẽ ném `AssertionError` khi môi trường thay đổi — cần xem đó là thay đổi dữ liệu hợp lệ hay regression của ứng dụng.

### 9.3. Chương trình thật sự fail nếu kỳ vọng sai

Hàm `check`:

```java
private static void check(boolean condition, String message) {
    if (!condition) {
        throw new AssertionError(message);
    }
}
```

đảm bảo rằng một bất đồng sẽ làm Java process thoát **nonzero** thay vì chỉ in `false`. Dùng kiểu assertion này làm smoke/CI gate khi không có JUnit. Khi áp dụng JUnit 5 hay framework khác, chuyển các checks thành test cases có tên và report rõ.

### 9.4. Vì sao không in chuỗi tiền/giờ đã localized?

Trong chương trình, `money.format(...)` và `dateTime.format(WINTER)` **đã thực sự được gọi** và được kiểm tra không rỗng. Bài không in các chuỗi Unicode locale-sensitive vào stdout expected vì:

- `fr-FR` có thể dùng narrow no-break space thay regular space;
- dấu tiền, pattern và tên time zone có thể được cập nhật;
- CLDR provider/Unicode version khác nhau;
- locale-specific punctuation và translated names có thể thay;
- một test bằng so chuỗi literal có thể fail dù localization vẫn hợp lệ.

Trong môi trường UI test, dùng screenshot/accessibility review hoặc một test định dạng được xác lập theo **chính phiên bản provider đã pin**, và vẫn có thể cần cập nhật golden snapshot khi nâng JDK.

## 10. Phân biệt test theo API contract và test theo dữ liệu vùng

### 10.1. API contract ổn định hơn translated strings

Bảng thiết kế assertion:

| Điều cần đảm bảo | Test nên viết | Có thể đổi khi dữ liệu cập nhật? |
| --- | --- | --- |
| Locale có region | `!locale.getCountry().isEmpty()` | Không nếu input tag cố định |
| Currency code của giao dịch | So ISO code đã lưu | Data country-to-currency có thể thay |
| NumberFormat sử dụng đúng Currency | `fmt.getCurrency().equals(currency)` | Có nếu provider/config bị thay |
| Ngày đầu tuần theo vùng | `WeekFields.of(locale).getFirstDayOfWeek()` | Có theo CLDR/config |
| Minimal days | `getMinimalDaysInFirstWeek()` | Có theo locale data |
| Một Instant không đổi theo zone | So `zdt.toInstant()` | Bất biến ngữ nghĩa |
| Offset cho 2024 ở vùng cụ thể | So `ZoneRules` tại Instant cố định | Có khi cập nhật TZDB |
| Week-based-year tại ranh giới | `weekBasedYear` + `weekOfWeekBasedYear` | Có nếu quy tắc tuần đổi |
| Chuỗi localized money/time | Tránh literal snapshot trên đa phiên bản | Rất dễ thay |
| `withLocale` giữ override zone | So `getZone()` | API contract |
| `localizedBy` áp Unicode tz extension | So `getZone()` với mapping đã pin | Contract + locale data |

Đừng yêu cầu một test cùng lúc “không phụ thuộc JDK” và “so chính xác mọi biểu tượng Unicode/offset cập nhật theo JDK”: hai mục tiêu xung đột. Tách **unit tests về logic cố định** và **compatibility tests về dữ liệu bản địa hóa**.

### 10.2. Pin runtime và đo thay đổi có chủ đích

Để CI tái lập, ghi:

- `java --version` và vendor/build;
- phiên bản CLDR/locale data nếu cung cấp;
- TZDB version và thời điểm cập nhật rules;
- OS/container locale, JVM startup properties;
- default zone nếu tests còn sử dụng;
- business expectations cho currency/week policy.

Tuy nhiên, **không khuyến nghị giữ mãi JDK/TZDB cũ** để làm tests xanh, vì dữ liệu múi giờ và tiền tệ cần được cập nhật. Khi upgrade, review sự thay đổi so với chính sách nghiệp vụ.

### 10.3. Kiểm tra TZDB hiện hành

`java.time.zone.ZoneRulesProvider.getVersions(zoneId)` có thể cho biết những phiên bản rules mà provider expose cho một region. Có thể dùng trong diagnostics:

```java
var versions = java.time.zone.ZoneRulesProvider
        .getVersions("Europe/Paris")
        .keySet();
```

**Đây là đoạn minh họa**, không phải một assertion JDK luôn có đúng một version hoặc một TZDB label cụ thể. Một provider khác có thể không giống OpenJDK stock; hãy ghi metadata của **runtime đang chạy** và so behavior thực.

### 10.4. Không lưu displayed money strings làm nguồn sự thật

Một số hệ thống đã lưu `"1.234 €"` hoặc `"$1,234.50"` vào database. Điều đó làm parsing và migration khó khăn khi Locale, tỷ giá hoặc đơn vị thay đổi.

**Nên lưu:** amount ở dạng decimal với scale/contract rõ, currency ISO code, time as Instant (hoặc representation thích hợp), và event-zone khi cần giữ quan hệ với địa phương. **Chỉ định dạng tại presentation layer** theo Locale được chọn.

## 11. Các tình huống nghiệp vụ và cách test

### Trường hợp A — 100 USD cho một người dùng tiếng Pháp

Input:

```text
amount = 100.00
currency = USD
userLocale = fr-FR
eventZone = America/New_York
```

Đúng là định dạng số/tiền theo tiếng Pháp **nhưng vẫn giữ currency = USD**. Đừng gọi `Currency.getInstance(fr_FR)` rồi đổi giao dịch sang EUR; điều đó là **thay đổi đơn vị tiền**, không phải formatting.

Test nên có: `Currency.getInstance("USD")` và formatter với `fr-FR` được đặt currency đúng; fraction digits/rounding được cấu hình theo quy tắc nghiệp vụ.

### Trường hợp B — Lịch làm việc luôn bắt đầu Thứ hai

Một phần mềm quản lý lịch công ty có policy `Monday + minimalDays=4` trên toàn thế giới. Khi người dùng ở US, `WeekFields.of(Locale.US)` bắt đầu Chủ nhật; nhưng nghiệp vụ vẫn phải theo policy.

Dùng:

```java
WeekFields businessWeek = WeekFields.ISO;
```

Không dùng `WeekFields.of(userLocale)` chỉ vì UI có Locale US. Ngược lại, nếu xây lịch cá nhân theo chuẩn vùng của người dùng, chọn `WeekFields.of(locale)` có thể đúng.

### Trường hợp C — Báo cáo “tuần 1 năm 2021”

Không đủ khi chỉ có `year=2021` và `week=1`; cần biết:

- sử dụng ISO week hay localized week;
- first day/minimal days;
- event date được tính theo zone nào;
- thời gian cắt báo cáo theo local date hay UTC date.

Trong code, lấy **cặp week-based-year + week** từ cùng `WeekFields` để tránh data mismatch.

### Trường hợp D — Một sự kiện gần nửa đêm

Một `Instant` có thể tương ứng **ngày hôm trước** ở New York và **ngày hôm sau** ở Tokyo. Nếu bạn lấy `LocalDate` theo UTC trước rồi định dạng ở Locale khác, kết quả “ngày giao dịch” có thể sai.

Đúng là chuyển `Instant.atZone(eventZone)` rồi lấy `toLocalDate()`, sau đó mới dùng WeekFields/business calendar.

### Trường hợp E — Đặt lịch ở DST gap

Người dùng chọn `2024-03-10 02:30` tại New York. Thời gian đó không tồn tại ở địa phương. Một test nên phát hiện `getValidOffsets(localDateTime).isEmpty()` và áp dụng chính sách yêu cầu (báo lỗi, hỏi chọn giờ khác...).

**Không** chỉ gọi `LocalDateTime.atZone(...)` rồi giả định người dùng biết nó có thể được điều chỉnh do gap. Cần quy định rõ UX.

### Trường hợp F — Đặt lịch tại DST overlap

Người dùng chọn `2024-11-03 01:30` New York; có thể tương ứng hai Instants khác nhau. Hãy cho phép họ xác nhận lần xảy ra trước/sau hoặc chọn `ZoneOffset` theo policy; test không được giả định chỉ có một.

### Trường hợp G — Test pass trên máy dev, fail trên CI

Nếu code dùng `Locale.getDefault()` và `ZoneId.systemDefault()`, developer ở Việt Nam và runner UTC có thể tính ngày/tuần/tiền khác.

**Khắc phục:** truyền explicit `Locale`, `ZoneId`, `Instant`, pin test fixtures. Không thay VM default globale cho các tests chạy parallel.

### Trường hợp H — Nâng JDK làm đổi khoảng trắng tiền tệ

Một bản JDK/CLDR mới có thể thay space thành NBSP hoặc narrow NBSP trong `fr-FR`. Nếu phép format vẫn phù hợp với chuẩn dữ liệu hiện hành, lỗi so literal có thể là **test quá cứng**.

Cách xử lý: xem Unicode code points, so business invariant, kiểm tra presentation thực và cập nhật golden snapshot có review; không tự strip toàn bộ Unicode trong code production.

## 12. Những lỗi phổ biến

**Lỗi 1 — “Locale cho biết múi giờ người dùng.”**  
Sai trong trường hợp chung. Chọn `ZoneId` explicit; một nước có nhiều vùng và user có thể đang du lịch.

**Lỗi 2 — “Locale xác định đồng tiền của mọi giao dịch.”**  
Sai. Nó có thể gợi ý currency theo region, nhưng giao dịch phải mang currency code thật.

**Lỗi 3 — “Ngôn ngữ `en` là đủ để `Currency.getInstance` suy USD.”**  
Sai. Thiếu region, API không có cơ sở xác định country currency.

**Lỗi 4 — “Số tiền nên lưu dưới dạng chuỗi đã formatted.”**  
Sai. Lưu decimal amount + currency code; định dạng ở UI.

**Lỗi 5 — “`new BigDecimal(0.1)` chính xác bằng 0,1.”**  
Không. Dùng string input hoặc `BigDecimal.valueOf` phù hợp.

**Lỗi 6 — “`setCurrency` tự sửa mọi fraction digits.”**  
Không. `NumberFormat.setCurrency` không cập nhật min/max fraction digits theo hợp đồng.

**Lỗi 7 — “Tất cả quốc gia đều bắt đầu tuần vào Thứ hai.”**  
Sai. `en-US`/`ja-JP` trong snapshot bắt đầu Chủ nhật.

**Lỗi 8 — “First day giống nhau nghĩa week-number giống nhau.”**  
Sai. Minimal days in first week cũng quan trọng: `vi-VN` và ISO có thể đều Monday nhưng khác số ngày tối thiểu.

**Lỗi 9 — “1/1/2021 luôn nằm trong tuần 1 năm 2021.”**  
Sai theo FR/ISO, nó là tuần 53 của week-based-year 2020.

**Lỗi 10 — “`YYYY-MM-dd` luôn là calendar date.”**  
Sai. `Y` là week-based-year, dễ lệch calendar year vào ranh giới năm.

**Lỗi 11 — “`ZoneOffset.ofHours(1)` tương đương Europe/Paris quanh năm.”**  
Sai. Paris có DST, summer offset có thể `+02:00`.

**Lỗi 12 — “`LocalDateTime` tự xác định một Instant.”**  
Sai. Có trường hợp 0/2 offsets hợp lệ trong DST gap/overlap.

**Lỗi 13 — “Đổi Locale bằng `withLocale` tự chuyển thời gian sang zone của Locale.”**  
Sai. `withLocale` chỉ chọn locale override; dùng `withZone` cho time zone explicit.

**Lỗi 14 — “Locale không bao giờ tác động đến time zone.”**  
Khẳng định quá rộng. `localizedBy(Locale)` từ Java 10 có thể dùng Unicode `tz` extension; cần biết API cụ thể.

**Lỗi 15 — “Dùng `localizedBy` và `withZone` thứ tự nào cũng như nhau.”**  
Không chắc. Unicode `tz` extension có thể override zone theo thứ tự gọi.

**Lỗi 16 — “Mỗi lần format tiền đều phải ra cùng bytes Unicode trên mọi JDK.”**  
Sai. CLDR/locale providers cập nhật, có thể đổi text/space/symbol.

**Lỗi 17 — “Một JDK luôn có các currency và DST rules hiện tại mãi mãi.”**  
Sai. Dữ liệu currency/tzdb theo thời gian và bản cập nhật.

**Lỗi 18 — “Dùng `Locale.setDefault` trong test song song không sao.”**  
Không. Default Locale là trạng thái có phạm vi VM, dễ gây race giữa tests.

**Lỗi 19 — “`NumberFormat` bất biến nên chia sẻ và setCurrency cùng lúc an toàn.”**  
Không. Formatter là mutable; quản lý instance/thread-safety rõ ràng.

**Lỗi 20 — “Nếu test chỉ print `false` thì CI tự fail.”**  
Không. Assertion phải ném lỗi/đưa exit code nonzero.

**Lỗi 21 — “Tính đầu tuần bằng LocalDate mà không cần nghĩ tới zone.”**  
Chỉ đúng nếu input **đã là LocalDate theo nghiệp vụ**. Nếu input là Instant, phải chuyển sang event zone trước.

**Lỗi 22 — “Test DST ở future date sẽ bền vững mãi.”**  
Không. Chính phủ có thể thay đổi time-zone rules; tests snapshot cần kiểm soát TZDB.

**Lỗi 23 — “`Locale.of` phải dùng vì đây là bài Java 10.”**  
Không. `Locale.of` xuất hiện sau Java 17; `Locale.forLanguageTag` phù hợp chương trình Java 17+ và code hiện hành.

**Lỗi 24 — “Tiền tệ có 0 fraction digits nên có thể round tự do.”**  
Không. Làm tròn tiền phụ thuộc payment contract; JDK default fraction digits chỉ là metadata đơn vị tiền.

## 13. Bài tập mở rộng có đáp án định hướng

**Bài 1 — Đổi Locale của cùng một Instant:** giữ `ZoneId.of("Europe/Paris")`, thử `en-US`, `fr-FR`, `vi-VN`.  
**Đáp án định hướng:** `getZone()` phải vẫn Paris, còn text bản địa hóa có thể khác.

**Bài 2 — So tháng 1 và tháng 7:** đo offset New York, Paris, Tokyo và Việt Nam tại hai Instants cố định.  
**Đáp án:** US `-05/-04`, France `+01/+02`, Japan `+09/+09`, Vietnam `+07/+07` trên JDK test.

**Bài 3 — Một giao dịch USD với user vi-VN:** format theo `vi-VN` nhưng không đổi currency.  
**Đáp án:** cấu hình `Currency.getInstance("USD")` và fraction digits/rounding theo policy.

**Bài 4 — Tính đầu tuần 1/1/2021:** dùng US, France, ISO.  
**Đáp án:** phải xem cả week-based-year, US `2021-W1`, France/ISO `2020-W53`.

**Bài 5 — Locale Unicode `fw`:** so `en-US` và `en-US-u-fw-mon`.  
**Đáp án:** ngày đầu tuần khác nhau trên JDK test, `SUNDAY` so `MONDAY`.

**Bài 6 — Locale Unicode `tz`:** so `withLocale` và `localizedBy`.  
**Đáp án:** với `en-US-u-tz-usnyc`, JDK test có `localizedBy` tự đưa zone New York, `withLocale` không tự đặt zone khi formatter gốc không có.

**Bài 7 — DST gap:** `2024-03-10T02:30` New York.  
**Đáp án:** `getValidOffsets` trả 0; không tự chấp nhận giờ địa phương này như một Instant duy nhất.

**Bài 8 — DST overlap:** `2024-11-03T01:30` New York.  
**Đáp án:** `getValidOffsets` trả 2; cần chọn offset theo chính sách.

**Bài 9 — CI với locale mặc định khác:** chạy chương trình với JVM properties/default khác.  
**Đáp án:** ví dụ truyền explicit Locale/ZoneId nên assertions không dựa vào defaults; các tests khác gọi default không explicit có thể khác.

**Bài 10 — Phát hiện test so chuỗi giòn:** kiểm tra dấu cách Unicode trong formatted French EUR.  
**Đáp án:** xem codepoints/locale data, tránh literal snapshot không pin JDK/CLDR.

**Bài 11 — Thêm Locale `de-DE`:** lấy Currency, WeekFields, zone `Europe/Berlin`; bổ sung expectation được kiểm thử trên JDK.  
**Đáp án:** Currency thường EUR, first-day Monday, zone phải truyền explicit; không suy Berlin chỉ từ country DE.

**Bài 12 — Chuyển date của Instant sang đầu tuần:** lấy `instant.atZone(zone).toLocalDate()` rồi `previousOrSame(weekFields.getFirstDayOfWeek())`.  
**Đáp án:** đổi zone có thể đổi LocalDate và start-of-week tại ranh giới ngày.

**Bài 13 — Lưu transaction:** thiết kế record `Money(BigDecimal amount, Currency currency)` và event `Instant`/`ZoneId` riêng.  
**Đáp án:** không lưu formatted text thay numeric amount; Locale thuộc presentation/context.

**Bài 14 — Đổi từ Locale hiển thị sang business week policy:** dùng `WeekFields.ISO` thay cho locale-derived rules.  
**Đáp án:** tuần phải được tính theo chính sách yêu cầu, không luôn theo địa phương.

**Bài 15 — Theo dõi thay đổi dữ liệu:** khi nâng Java runtime, so outputs của bốn test cases và đánh dấu thay đổi hợp lệ của CLDR/TZDB trước khi cập nhật baselines.  
**Đáp án:** không downgrade JDK chỉ để test snapshot cũ vẫn xanh.

## 14. Checklist kiểm thử i18n/l10n cho production

- [ ] Locale nhận vào ở dạng BCP 47 hợp lệ; biết language, region và extensions.
- [ ] Không dùng constructors `Locale` deprecated cho code mới.
- [ ] Currency code đến từ **transaction/business domain**, không mặc định từ user UI language.
- [ ] `Currency.getInstance(locale)` chỉ dùng khi region đủ và trường hợp null/invalid được xử lý.
- [ ] Dùng `BigDecimal` với scale/rounding policy explicit cho monetary calculation.
- [ ] Dùng `NumberFormat.getCurrencyInstance(locale)` để hiển thị; biết formatter mutable.
- [ ] Nếu `setCurrency`, kiểm tra fraction-digit settings và UI rounding.
- [ ] Test localized text không phụ thuộc byte-for-byte ngoài golden snapshot đã pin.
- [ ] `WeekFields.of(locale)` dùng khi yêu cầu là tuần theo địa phương; `WeekFields.ISO` khi business policy yêu cầu ISO.
- [ ] Kiểm tra `minimalDaysInFirstWeek` và ranh giới tuần/năm, không chỉ first day.
- [ ] Không dùng `YYYY` để format calendar year nếu cần `uuuu`.
- [ ] Lưu thời điểm dưới dạng `Instant` (hoặc contract tương đương), không biến `LocalDateTime` không có zone thành timestamp duy nhất.
- [ ] Dùng IANA region `ZoneId` explicit; không suy zone duy nhất từ Locale/country.
- [ ] Kiểm tra DST gap/overlap khi nhận local date-time từ user.
- [ ] Hiểu khác biệt `withLocale`/`withZone` và `localizedBy` với Unicode extensions.
- [ ] Dùng fixed Instants/Test Clock để kiểm thử, không dùng `now()` trong assertions deterministic.
- [ ] Ghi JDK/CLDR/TZDB version cho snapshot compatibility tests.
- [ ] CI fail bằng assertions/nonzero exit, không chỉ in kết quả false.
- [ ] Review data changes khi nâng JDK, nhưng tiếp tục dùng runtime được bảo trì.
- [ ] Kiểm tra UI trên thực tế với labels, screen readers, Unicode spaces và timezone names.

## 15. Ghi nhớ

1. **Locale = quy ước bản địa hóa**; **Currency = đơn vị tiền**; **WeekFields = chính sách tuần**; **ZoneId = quy tắc múi giờ**; **Instant = thời điểm tuyệt đối**.
2. `Currency.getInstance(Locale)` chủ yếu suy currency từ region, **không phải currency của mọi giao dịch thực tế**.
3. Định dạng tiền qua `NumberFormat` thay đổi theo CLDR và Unicode; kiểm thử **ngữ nghĩa** thay vì exact strings chưa pin runtime.
4. Dùng `BigDecimal` cho monetary values; `setCurrency` không tự cập nhật min/max fraction digits.
5. `WeekFields.of(Locale)` đưa ra **first day và minimal days**, cả hai có thể ảnh hưởng `week-based-year`.
6. US: `SUNDAY/1`, France: `MONDAY/4`, Japan: `SUNDAY/1`, Vietnam: `MONDAY/1` là **snapshot đã kiểm thử trên OpenJDK 24**.
7. `WeekFields.ISO` có `MONDAY/4`; dùng explicit khi business contract đòi ISO.
8. **Múi giờ không được suy một cách đáng tin từ Locale**; truyền IANA `ZoneId` explicit khi đổi `Instant` thành local date/time.
9. `DateTimeFormatter.withLocale` không tự đổi zone; **`localizedBy` từ Java 10 có thể áp dụng Unicode `tz` extension**.
10. Kiểm thử DST **gap=0 offsets**, **overlap=2 offsets** để tránh làm mất nghĩa thời điểm.
11. JDK/CLDR/TZDB thay đổi theo bản cập nhật; **pin runtime cho snapshots, review khi nâng**.
12. Một test chất lượng phải **thất bại thật** khi kỳ vọng sai, bằng assertion/exit code nonzero.

## Tài liệu tham khảo chính thức, đang áp dụng

- **Oracle Java SE 26 — Locale API**: BCP 47 tags, Unicode extensions, default DISPLAY/FORMAT, constructors deprecated từ Java 19: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html
- **Oracle Java SE 25 — Currency API**: `getInstance(Locale)`, `getCurrencyCode()`, `getDefaultFractionDigits()`, region-to-currency mapping: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Currency.html
- **Oracle Java SE 26 — NumberFormat API**: `getCurrencyInstance(Locale)`, `setCurrency` không cập nhật fraction digits, formatter behaviors: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html
- **Oracle Java SE 26 — WeekFields API**: `of(Locale)`, `ISO`, `weekBasedYear`, `getFirstDayOfWeek` và `getMinimalDaysInFirstWeek`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/WeekFields.html
- **Oracle Java SE 26 — DateTimeFormatter API**: `ofLocalizedDateTime`, `withLocale`, `withZone` và `localizedBy(Locale)` (Since Java 10): https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html
- **Oracle Java SE 26 — ZoneId API**: IANA region IDs, ZoneRules, default time zone và historical/future updates: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html
- **Oracle Java SE 26 — ZoneRules API**: `getValidOffsets`, DST gap/overlap: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html
- **Oracle Java SE 26 — Instant API**: thời điểm UTC độc lập với presentation zone: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html
- **Oracle Java SE 26 — BigDecimal API**: decimal arithmetic, scale/rounding: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html
- **Oracle Java SE 26 — TemporalAdjusters API**: `previousOrSame` khi tính tuần bắt đầu: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalAdjusters.html
