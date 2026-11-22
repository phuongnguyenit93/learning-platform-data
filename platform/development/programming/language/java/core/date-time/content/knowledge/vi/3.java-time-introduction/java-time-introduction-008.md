# Truyền ZoneId, Locale và Clock tường minh thay cho phụ thuộc môi trường

Trong Java, kết quả xử lý ngày giờ có thể vô tình phụ thuộc vào máy đang chạy: máy cá nhân và máy chủ có múi giờ khác nhau; ngôn ngữ mặc định của JVM có thể khác; đồng hồ thực chạy liên tục nên kiểm thử khó lặp lại. Cách thiết kế đáng tin cậy là **truyền tường minh `ZoneId`, `Locale` và `Clock`** vào nơi cần chúng, thay vì để logic nghiệp vụ tự lấy các giá trị mặc định của môi trường.

Ba đối tượng giải quyết **ba câu hỏi khác nhau**:

| Đối tượng | Câu hỏi mà nó trả lời | Vai trò chính |
| --- | --- | --- |
| `Clock` | “Hiện tại là thời điểm nào?” | Cấp nguồn thời gian, cho phép kiểm thử bằng thời gian cố định |
| `ZoneId` | “Thời điểm đó ứng với giờ/ngày lịch nào tại một vùng?” | Ánh xạ `Instant` sang giờ địa phương bằng quy tắc vùng |
| `Locale` | “Hiển thị hoặc đọc ngày bằng ngôn ngữ và quy ước nào?” | Chọn tên tháng, thứ, cách trình bày/diễn giải văn bản |

**`Locale` không tự chọn múi giờ; `ZoneId` không tự chọn ngôn ngữ; `Clock` không thay thế quy tắc hiển thị.** Một ứng dụng thường cần cả ba, nhưng các giá trị có thể đến từ những nguồn cấu hình khác nhau.

## 1. Vì sao phụ thuộc mặc định của môi trường dễ gây lỗi?

Những lời gọi sau trông đơn giản nhưng mang các quyết định ngầm:

```java
LocalDate today = LocalDate.now();                 // dùng múi giờ mặc định JVM
ZonedDateTime now = ZonedDateTime.now();           // dùng đồng hồ và múi giờ mặc định
ZoneId zone = ZoneId.systemDefault();              // phụ thuộc cấu hình máy/JVM
Locale locale = Locale.getDefault();               // phụ thuộc locale mặc định JVM
String label = DateTimeFormatter.ofLocalizedDate(
        FormatStyle.LONG).format(today);            // dùng locale mặc định của formatter
```

Đoạn này minh họa API, cần các import `java.time.*`, `java.time.format.*`, `java.util.Locale`.

Ví dụ, ở cùng một thời điểm `2024-02-29T23:30:00Z`:

- Tại `Asia/Ho_Chi_Minh` (UTC+07 vào thời điểm đó), ngày địa phương là **01/03/2024**.
- Tại `America/New_York` (UTC−05 vào thời điểm đó), ngày địa phương là **29/02/2024**.

Nếu luật nghiệp vụ là “khóa đơn thuộc ngày nào theo giờ Việt Nam”, một tiến trình chạy trong vùng UTC hay New York không được phép làm thay đổi kết quả. Tương tự, việc một máy dùng tiếng Anh và máy khác dùng tiếng Việt không nên làm đổi ngôn ngữ của thông báo đã được người dùng lựa chọn.

Thiết lập mặc định có thể chịu ảnh hưởng cấu hình khởi chạy hoặc thay đổi toàn JVM trong quá trình chạy. Gọi `TimeZone.setDefault(...)` hoặc `Locale.setDefault(...)` để “chữa” một phép tính riêng lẻ cũng tác động đến mã khác trong tiến trình, không phù hợp với ứng dụng phục vụ nhiều người dùng hoặc kiểm thử chạy song song.

## 2. Hiểu đúng `Instant`, `ZoneId` và ngày địa phương

`Instant` mô tả một **thời điểm trên trục thời gian**, độc lập với múi giờ hiển thị. `ZonedDateTime` gắn thời điểm đó với một `ZoneId` để xác định ngày, giờ và offset địa phương. `LocalDate` chỉ có ngày lịch, không chứa giờ hoặc múi giờ.

```java
Instant instant = Instant.parse("2024-02-29T23:30:00Z");
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId newYork = ZoneId.of("America/New_York");

LocalDate dateInVietnam = instant.atZone(vietnam).toLocalDate(); // 2024-03-01
LocalDate dateInNewYork = instant.atZone(newYork).toLocalDate(); // 2024-02-29
```

Đây là đoạn minh họa cần import `java.time.*`. **Cùng `Instant`, khác `ZoneId`, có thể khác `LocalDate`.** Vì thế, nếu hệ thống nhận một “thời điểm giao dịch” rồi quyết định ngày kế toán, hãy chỉ rõ **vùng nghiệp vụ** trước khi lấy ngày.

Dùng ID vùng dạng IANA, ví dụ `Asia/Ho_Chi_Minh`, `America/New_York`, `Europe/Paris`. ID vùng có quy tắc offset lịch sử và thay đổi giờ mùa hè (DST). Một `ZoneOffset` cố định như `+07:00` chỉ chứa offset, **không mô hình hóa toàn bộ quy tắc một vùng**. Các chữ viết tắt mơ hồ như “CST” không phù hợp để định danh vùng trong cấu hình nghiệp vụ.

### `ZoneId` không giống `Locale`

`ZoneId.of("Asia/Ho_Chi_Minh")` nói cách chuyển thời điểm thành giờ tại Việt Nam, nhưng **không bắt buộc** nội dung hiển thị phải bằng tiếng Việt. Bạn hoàn toàn có thể hiển thị giờ Việt Nam bằng tiếng Anh cho một người dùng nói tiếng Anh:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Locale displayLocale = Locale.US;

Instant eventTime = Instant.parse("2024-02-29T23:30:00Z");
String dayName = DateTimeFormatter.ofPattern("EEEE", displayLocale)
        .format(eventTime.atZone(zone));
// dayName là "Friday"
```

Đoạn minh họa cần import `java.time.*`, `java.time.format.DateTimeFormatter`, `java.util.Locale`. `ZoneId` quyết định **ngày thứ Sáu tại Việt Nam**; `Locale.US` quyết định viết thứ ấy là “Friday”.

## 3. `Clock`: nguồn “bây giờ” có thể thay thế được

Gọi `Instant.now()` hoặc `LocalDate.now()` trực tiếp bên trong logic nghiệp vụ làm thời gian trở thành một phụ thuộc ẩn. `Clock` cho phép chuyển phụ thuộc đó thành tham số:

```java
Clock productionClock = Clock.systemUTC(); // lấy thời gian hệ thống; zone của Clock là UTC

Clock testClock = Clock.fixed(
        Instant.parse("2024-02-29T23:30:00Z"),
        ZoneOffset.UTC);                  // mọi lần đọc đều trả cùng thời điểm

Instant eventTime = Instant.now(testClock);
// 2024-02-29T23:30:00Z
```

Các đoạn trên cần import `java.time.*`. Những kiểu `Clock` thông dụng:

| Cách tạo | Công dụng |
| --- | --- |
| `Clock.systemUTC()` | Nguồn thời gian thực với zone UTC; thường dùng làm dependency mặc định lúc cấu hình ứng dụng |
| `Clock.system(zone)` | Nguồn thời gian thực có `clock.getZone() == zone` |
| `Clock.fixed(instant, zone)` | Luôn trả cùng `Instant`; lý tưởng cho kiểm thử các ranh giới ngày/giờ |
| `Clock.offset(baseClock, duration)` | Đồng hồ dịch so với đồng hồ cơ sở, phù hợp một số kịch bản giả lập |
| `clock.withZone(zone)` | Đồng hồ dùng cùng nguồn thời gian nhưng mang `ZoneId` khác cho API đọc ngày/giờ cục bộ |

**Lưu ý:** `Clock` có một `ZoneId` riêng, nhưng đó là vùng dùng khi API hỏi ngày giờ theo đồng hồ. Nó **không nhất thiết là vùng nghiệp vụ**. Nếu có `Clock.systemUTC()` mà nghiệp vụ yêu cầu giờ Việt Nam, lấy `Instant` từ `Clock` rồi chuyển theo `ZoneId` của nghiệp vụ:

```java
Instant now = clock.instant();
LocalDate businessDate = now.atZone(businessZone).toLocalDate();
```

Hai dòng này là đoạn **bên trong phương thức** có biến `clock` và `businessZone` đã được truyền vào. Một cách tương đương khi chỉ cần ngày là `LocalDate.now(clock.withZone(businessZone))`. Khi cùng một yêu cầu cần nhiều giá trị đồng bộ (ngày, giờ, hạn, log), nên **đọc đồng hồ một lần**, giữ một `Instant` rồi chuyển đổi từ cùng thời điểm đó; điều này loại bỏ việc hai lần `now()` nằm ở hai phía ranh giới ngày.

## 4. `Locale`: quy tắc trình bày/đọc ngày theo ngôn ngữ

`Locale` là định danh ngôn ngữ/vùng phục vụ dữ liệu địa phương hóa. Có thể chọn các giá trị rõ ràng:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale englishUS = Locale.US;
Locale german = Locale.GERMAN;
```

Đoạn minh họa cần import `java.util.Locale`. Một `DateTimeFormatter` với `Locale` được chỉ định tường minh tránh việc cùng một đối tượng ngày bị in bằng ngôn ngữ khác khi deploy:

```java
LocalDate date = LocalDate.of(2024, 3, 1);

DateTimeFormatter english = DateTimeFormatter.ofPattern(
        "EEEE, d MMMM uuuu", Locale.US);
DateTimeFormatter german = DateTimeFormatter.ofPattern(
        "EEEE, d MMMM uuuu", Locale.GERMAN);

System.out.println(english.format(date));
System.out.println(german.format(date));
```

Đoạn minh họa cần import `java.time.LocalDate`, `java.time.format.DateTimeFormatter` và `java.util.Locale`. Dòng tiếng Anh và tiếng Đức cho tên thứ/tháng được địa phương hóa. **Không nên dựa vào toàn bộ câu chữ hiển thị để kiểm thử cố định giữa mọi phiên bản Java**, vì dữ liệu ngôn ngữ/CLDR có thể được cập nhật. Nếu cần trao đổi dữ liệu giữa các hệ thống, hãy dùng dạng ISO có hợp đồng rõ ràng; còn formatter địa phương hóa phục vụ hiển thị cho người dùng.

Có thể chọn formatter mức độ hiển thị như `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withLocale(locale)`. Với pattern nhập có chữ tháng, hãy truyền cùng `Locale` để parse tên tháng phù hợp; nếu cần bác bỏ ngày không tồn tại, cấu hình thêm `ResolverStyle.STRICT` và chọn pattern năm phù hợp (thường là `uuuu`).

**Đừng suy ra `ZoneId` từ `Locale`.** Một người chọn ngôn ngữ tiếng Việt vẫn có thể ở New York; một người làm việc tại Việt Nam vẫn có thể chọn tiếng Anh. Hệ thống nên lưu/lấy chúng theo các thuộc tính độc lập.

## 5. Chương trình Java 17+ hoàn chỉnh: ba tham số, một kết quả tái lập được

Tạo tệp **`ExplicitDateTimeDemo.java`**:

```java
import java.time.*;
import java.time.format.*;
import java.util.Locale;

public class ExplicitDateTimeDemo {
    private static String format(Instant now, ZoneId zone, Locale locale) {
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", locale);
        return formatter.format(now.atZone(zone));
    }

    private static String weekday(Instant now, ZoneId zone, Locale locale) {
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern(
                "EEEE", locale);
        return formatter.format(now.atZone(zone));
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2024-02-29T23:30:00Z"), ZoneOffset.UTC);
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");

        Instant now = Instant.now(clock);
        System.out.println("Instant: " + now);
        System.out.println("VN date: " + now.atZone(vietnam).toLocalDate());
        System.out.println("NY date: " + now.atZone(newYork).toLocalDate());
        System.out.println("VN time: " + format(now, vietnam, Locale.US));
        System.out.println("NY time: " + format(now, newYork, Locale.US));
        System.out.println("Weekday US: " + weekday(now, vietnam, Locale.US));
        System.out.println("Weekday DE: " + weekday(now, vietnam, Locale.GERMAN));
    }
}
```

Trong thư mục chứa tệp:

```bash
javac ExplicitDateTimeDemo.java
java ExplicitDateTimeDemo
```

**stdout** (đã kiểm tra bằng Java, biên dịch với `javac --release 17`):

```text
Instant: 2024-02-29T23:30:00Z
VN date: 2024-03-01
NY date: 2024-02-29
VN time: 2024-03-01 06:30 +07:00
NY time: 2024-02-29 18:30 -05:00
Weekday US: Friday
Weekday DE: Freitag
```

Cơ chế:

1. `Clock.fixed` làm giá trị `now` ổn định dù chạy tại máy nào hay lúc nào.
2. `vietnam` và `newYork` chuyển **cùng một thời điểm** thành hai ngày/giờ địa phương khác nhau.
3. `format` nhận tường minh zone và locale; ở pattern dạng số, `Locale.US` không làm đổi chữ số, nhưng biến này đã sẵn sàng cho pattern có tên tháng/thứ.
4. `weekday` minh họa locale: **cùng ngày tại Việt Nam** được viết “Friday” hoặc “Freitag” tùy tham số.
5. Chương trình không gọi `ZoneId.systemDefault()`, `Locale.getDefault()` hay `LocalDate.now()` không tham số.

Hai vùng được chọn có offset như stdout vào **29/02/2024**. Offset của `America/New_York` thay đổi theo mùa, nên không thể thay mã vùng bằng `-05:00` cho mọi ngày trong năm.

## 6. Thiết kế ứng dụng: đưa phụ thuộc vào constructor

Mã nhận ngày giờ từ môi trường bên trong phương thức khó kiểm thử:

```java
public LocalDate businessToday() {
    return LocalDate.now(); // ngày theo vùng mặc định của máy chạy
}
```

Thay bằng một service được cấp đầy đủ nguồn thời gian và quy tắc hiển thị:

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.Objects;

public final class BusinessDateService {
    private final Clock clock;
    private final ZoneId businessZone;
    private final Locale displayLocale;

    public BusinessDateService(
            Clock clock, ZoneId businessZone, Locale displayLocale) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.businessZone = Objects.requireNonNull(businessZone, "businessZone");
        this.displayLocale = Objects.requireNonNull(displayLocale, "displayLocale");
    }

    public LocalDate today() {
        Instant instant = clock.instant();
        return instant.atZone(businessZone).toLocalDate();
    }

    public String formattedToday() {
        LocalDate date = today();
        DateTimeFormatter formatter = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(displayLocale);
        return formatter.format(date);
    }
}
```

Đây là **một class có thể biên dịch** khi lưu thành `BusinessDateService.java`; nó không khai báo `main` nên không phải chương trình độc lập để chạy bằng lệnh `java BusinessDateService`. Ví dụ tạo instance:

```java
Clock clock = Clock.systemUTC();
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Locale locale = Locale.forLanguageTag("vi-VN");
BusinessDateService service = new BusinessDateService(clock, zone, locale);
LocalDate businessDay = service.today();
```

Đoạn khởi tạo nằm trong mã ứng dụng và cần các import của các kiểu được sử dụng. Ở ứng dụng thực tế, `Clock` thường được cấu hình một lần qua dependency injection. `ZoneId` có thể là vùng cố định của doanh nghiệp hoặc vùng lấy từ hồ sơ người dùng; `Locale` thường đến từ lựa chọn ngôn ngữ. Truyền chúng qua tham số hoặc constructor tùy phạm vi: **không dùng một biến static thay đổi được cho mọi người dùng**.

Nếu trong một giao dịch cần đồng thời sinh `createdAt`, `businessDate` và `dueDate`, lấy `Instant createdAt = clock.instant()` **một lần**; sau đó derive các giá trị từ `createdAt` và `businessZone`, tránh kết quả tự mâu thuẫn khi yêu cầu bắt đầu trước nửa đêm và kết thúc sau nửa đêm.

### Điểm quyết định cấu hình

- **Nguồn hiện tại**: application composition root cung cấp `Clock.systemUTC()`; bài test cung cấp `Clock.fixed(...)`.
- **Vùng tính toán**: lấy từ cấu hình nghiệp vụ hoặc lựa chọn rõ ràng của người dùng, ví dụ `ZoneId.of(configuredZoneId)`.
- **Ngôn ngữ hiển thị**: lấy từ tùy chọn người dùng/hợp đồng request, ví dụ `Locale.forLanguageTag(configuredLanguageTag)`.

`ZoneId.of` từ chối ID không hợp lệ (có thể ném `DateTimeException`, cụ thể `ZoneRulesException`). `Locale.forLanguageTag` có thể chuẩn hóa hoặc bỏ qua các phần thẻ ngôn ngữ sai; nếu ứng dụng chỉ hỗ trợ một tập ngôn ngữ, cần **kiểm tra lựa chọn đó** theo danh sách được hỗ trợ. Header HTTP `Accept-Language` có trọng số ưu tiên, không nên coi toàn bộ giá trị header là một language tag đơn lẻ.

## 7. Kiểm thử thời gian với `Clock.fixed`

Một bài test không nên đợi đúng nửa đêm, sửa múi giờ hệ điều hành hoặc dùng `Thread.sleep` để thử ranh giới ngày. Chỉ việc truyền đồng hồ cố định đã đủ điều khiển tình huống:

```java
Clock frozen = Clock.fixed(
        Instant.parse("2024-02-29T23:30:00Z"),
        ZoneOffset.UTC);

BusinessDateService vietnamService = new BusinessDateService(
        frozen, ZoneId.of("Asia/Ho_Chi_Minh"), Locale.US);
BusinessDateService nyService = new BusinessDateService(
        frozen, ZoneId.of("America/New_York"), Locale.US);

// vietnamService.today() -> 2024-03-01
// nyService.today()      -> 2024-02-29
```

Đoạn này sử dụng class `BusinessDateService` ở mục 6, cần các import `java.time.*` và `java.util.Locale`. Trong JUnit 5, có thể khẳng định:

```java
assertEquals(LocalDate.of(2024, 3, 1), vietnamService.today());
assertEquals(LocalDate.of(2024, 2, 29), nyService.today());
```

Hai lời gọi `assertEquals` thuộc **phương thức test JUnit 5**, với static import `org.junit.jupiter.api.Assertions.assertEquals`; chúng không phải toàn bộ lớp test độc lập. Test cần quan sát một thời điểm sát ranh giới ngày vì đó là nơi phụ thuộc zone dễ lộ ra. Nên bổ sung các trường hợp chuyển cuối tháng, cuối năm, năm nhuận và đổi giờ mùa hè nếu miền nghiệp vụ có vùng áp dụng DST.

Nếu muốn kiểm thử thời gian trôi theo bước, có thể xây một `Clock` giả có thể điều khiển hoặc dùng `Clock.offset` tùy bài toán. `Clock.fixed` đủ và đơn giản nhất cho những phép kiểm tra không cần thời gian thực sự tiến lên. Tránh test dùng `Instant.now()` của máy để kỳ vọng một chuỗi thời điểm cố định.

## 8. DST, chênh lệch giờ và tính hợp lệ của giờ địa phương

Một `ZoneId` vùng mang dữ liệu quy tắc giờ mùa hè và lịch sử offset. Tại một số thời điểm chuyển DST, một `LocalDateTime` có thể:

- **Không tồn tại** trong vùng (*gap*, đồng hồ nhảy tới).
- **Xuất hiện hai lần** với hai offset khác nhau (*overlap*, đồng hồ lùi).
- **Tồn tại duy nhất** với một offset.

Ví dụ ở New York năm 2024, giờ `02:30` ngày 10/03 rơi vào khoảng bị bỏ qua khi bắt đầu DST:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime nonexistent = LocalDateTime.of(2024, 3, 10, 2, 30);

ZonedDateTime adjusted = nonexistent.atZone(ny);
// 2024-03-10T03:30-04:00[America/New_York]
```

Đây là đoạn minh họa cần import `java.time.*`. `LocalDateTime.atZone` mặc định điều chỉnh thời gian nằm trong gap; nếu nghiệp vụ yêu cầu **từ chối** giờ địa phương không tồn tại, hãy kiểm tra quy tắc vùng trước khi chuyển:

```java
int validOffsetCount = ny.getRules().getValidOffsets(nonexistent).size();
// 0: gap; 1: giờ bình thường; 2: overlap (giờ mơ hồ)
```

Nếu là overlap, nghiệp vụ phải quyết định dùng offset nào (có thể chọn `withEarlierOffsetAtOverlap()` hoặc `withLaterOffsetAtOverlap()`). Đây là lý do lưu `LocalDateTime` đơn lẻ chưa đủ để mô tả một **thời điểm duy nhất** trong mọi múi giờ.

Lưu ý giờ mùa hè khác với quy tắc **ngày có hợp lệ hay không**: ngày `2024-03-10` có thật, nhưng không phải mọi giờ địa phương trong ngày ấy đều tồn tại ở New York. Cần chọn API thích hợp với dữ liệu đang mô tả.

## 9. Từ xử lý thời gian đến lưu trữ và API

Một chiến lược rõ ràng thường là:

1. Tại biên ứng dụng, xác định vùng nghiệp vụ hoặc vùng của người dùng (`ZoneId`) và ngôn ngữ (`Locale`).
2. Khi sự kiện xảy ra, lấy một `Instant` từ `Clock`.
3. Dùng `Instant` để biểu diễn **thời điểm** khi lưu log/sự kiện hoặc trao đổi dữ liệu cần mốc thời gian chính xác.
4. Khi cần ngày kế toán, hạn theo ngày hoặc giờ địa phương, chuyển `Instant` bằng **`ZoneId` được chỉ định** rồi trích `LocalDate` hoặc `ZonedDateTime`.
5. Khi hiển thị nội dung, định dạng bằng `DateTimeFormatter` với **`Locale` được chỉ định**. Đừng dùng chuỗi hiển thị làm dữ liệu chuẩn để lưu trữ hay so sánh.

Ví dụ, một deadline “17:00 ngày 1/3 tại Hà Nội” phải được định nghĩa bằng **ngày/giờ địa phương + vùng**, sau đó mới chuyển sang `Instant` để so sánh chính xác thời điểm. Nếu chỉ giữ `2024-03-01T17:00` mà không có zone, chưa biết deadline đó tương ứng thời điểm UTC nào.

Khi cần định dạng một `Instant` trực tiếp, có thể truyền zone vào formatter:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm z", Locale.US)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

String text = formatter.format(Instant.parse("2024-02-29T23:30:00Z"));
```

Đoạn này cần import `java.time.*`, `java.time.format.DateTimeFormatter` và `java.util.Locale`. `withZone` cung cấp thông tin vùng để formatter biến `Instant` thành trường ngày/giờ; `Locale.US` quyết định ngôn ngữ khi pattern có thành phần phụ thuộc locale. Với payload máy–máy, ưu tiên chuẩn ISO theo hợp đồng API hơn tên tháng/thứ địa phương hóa.

## 10. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `LocalDate.now()` trong nghiệp vụ | Ngày thay đổi tùy múi giờ JVM | Lấy `Instant` từ `Clock` và chuyển theo `ZoneId` nghiệp vụ |
| `ZonedDateTime.now()` bên trong service | Khó kiểm thử và có vùng ẩn | Truyền `Clock`, `ZoneId` |
| `Locale.getDefault()` trong formatter của người dùng | Ngôn ngữ thay đổi theo máy chủ | Truyền `Locale` từ lựa chọn người dùng |
| Lấy `ZoneId` từ ngôn ngữ | Người dùng nói tiếng Việt ở nước khác nhận giờ sai | Quản lý language và time zone độc lập |
| Luôn dùng offset cố định cho một thành phố có DST | Sai ở một số thời điểm của năm | Dùng vùng IANA như `America/New_York` |
| Dùng `Clock.systemUTC()` rồi gọi `LocalDate.now(clock)` để suy ngày Việt Nam | Đang lấy **ngày UTC**, không phải ngày Việt Nam | `Instant.now(clock).atZone(vietnam).toLocalDate()` |
| Gọi `now()` nhiều lần trong cùng quyết định nghiệp vụ | Các kết quả có thể thuộc hai ngày khi qua nửa đêm | Chụp một `Instant` rồi tái sử dụng |
| Đổi default timezone/locale JVM trong test | Ảnh hưởng test khác và mã cùng tiến trình | Inject `Clock.fixed`, `ZoneId`, `Locale` |
| Kiểm thử bằng chuỗi tên tháng chính xác trên mọi JDK | Dữ liệu locale có thể thay đổi | So sánh giá trị thời gian; chỉ kiểm thử quy ước locale thật sự được yêu cầu |

## 11. Checklist khi viết chức năng mới

- **Nguồn thời gian:** service có nhận `Clock` hoặc `Instant` từ người gọi không?
- **Vùng:** quy tắc nghiệp vụ nói rõ giờ/địa phương nào, hay đang dựa vào zone của máy chủ?
- **Ngôn ngữ:** formatter/parser có dùng `Locale` đã chọn rõ ràng không?
- **Một thời điểm:** các kết quả liên quan có cùng xuất phát từ một `Instant` không?
- **Ranh giới:** có test sát nửa đêm, cuối tháng/năm, ngày nhuận, chuyển DST khi cần không?
- **Lưu trữ:** có phân biệt thời điểm tuyệt đối với ngày/giờ địa phương và dữ liệu chỉ để hiển thị không?

**Ghi nhớ:** `Clock` trả lời **khi nào**, `ZoneId` quyết định **ngày/giờ địa phương ở đâu**, `Locale` quyết định **hiển thị bằng quy ước nào**. Truyền cả ba tường minh làm nghiệp vụ không đổi theo môi trường triển khai, đồng thời giúp kiểm thử ngày giờ trở nên tái lập và dễ giải thích.
