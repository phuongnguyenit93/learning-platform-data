# DateFormat và các factory theo Locale trong Java

## 1. Tổng quan: định dạng ngày giờ theo ngôn ngữ người dùng

`java.text.DateFormat` là API định dạng và phân tích ngày giờ thuộc **Java core, nhóm API ngày giờ cũ (`java.text`/`java.util`)**. Trước khi `java.time` xuất hiện, ứng dụng Java thường kết hợp `java.util.Date`, `Calendar`, `TimeZone` và `DateFormat` để hiển thị ngày giờ theo từng ngôn ngữ, lãnh thổ.

Cùng một thời điểm có thể được hiển thị khác nhau:

- Theo tiếng Anh (Hoa Kỳ): `January 2, 2024` hoặc `1/2/24`.
- Theo tiếng Pháp (Pháp): `2 janvier 2024`.
- Với cùng một locale nhưng chọn **style** khác, chuỗi ngày có thể ngắn, dài, có tên thứ hoặc không.
- Với cùng locale và style nhưng **múi giờ khác**, một timestamp gần nửa đêm có thể thuộc hai ngày lịch khác nhau.

`DateFormat` cung cấp **factory methods** để chọn dạng định dạng theo `Locale` mà **không phải tự viết pattern ngày tháng cụ thể cho từng ngôn ngữ**. Thay vì cố định `"dd/MM/yyyy"` hay `"MM/dd/yyyy"`, bạn yêu cầu Java tạo formatter theo mục đích: date, time hoặc date+time.

**Mục tiêu bài học:** nắm đủ các factory của `DateFormat`, các style `FULL/LONG/MEDIUM/SHORT`, cách truyền `Locale` và `TimeZone`, cách định dạng/parse an toàn, nhận diện giới hạn legacy API, và cách chọn `java.time` cho code mới.

## 2. DateFormat là lớp nào?

`DateFormat` là **lớp trừu tượng** kế thừa `java.text.Format`:

- `format(Date)` chuyển giá trị ngày giờ thành chuỗi để hiển thị.
- `parse(String)` hoặc `parse(String, ParsePosition)` đọc một chuỗi thành `java.util.Date`.
- `setTimeZone(TimeZone)` cấu hình múi giờ cho formatter.
- `setLenient(boolean)` điều chỉnh việc parser/calendar có cho phép xử lý mềm dẻo những ngày không hợp lệ hay không.
- `getCalendar()` và `setCalendar(Calendar)` truy cập/cấu hình lịch do formatter dùng.
- `getNumberFormat()` và `setNumberFormat(NumberFormat)` dùng cấu hình số ở việc định dạng các thành phần.

Đối tượng được trả về bởi một factory có **kiểu khai báo là `DateFormat`**. Trong nhiều môi trường, implementation là `SimpleDateFormat`; nhưng không nên luôn ép kiểu sang `SimpleDateFormat` nếu bạn chỉ cần dùng các API chung, bởi implementation có thể phụ thuộc locale provider và môi trường JDK.

Một `Date` đại diện thời điểm (epoch milliseconds) **không tự mang cách hiển thị theo ngôn ngữ hay tên múi giờ**. `DateFormat` chịu trách nhiệm trình bày các trường lịch theo `Locale` và zone đã cấu hình. Khi parse, nó dùng những quy tắc đó để tạo `Date`. Không vì thấy chuỗi `"02/01/2024"` mà có thể suy ra chắc chắn nó thuộc ngày 2 tháng 1 hay 1 tháng 2 nếu chưa biết locale/pattern.

## 3. Các factory chính và cách chọn

Các factory là phương thức static của `DateFormat`:

| API | Mục đích | Những tham số quan trọng |
| --- | --- | --- |
| `DateFormat.getDateInstance()` | Chỉ ngày, style mặc định. | Dùng `DEFAULT` và locale mặc định cho định dạng. |
| `DateFormat.getDateInstance(int style)` | Chỉ ngày theo style. | `FULL/LONG/MEDIUM/SHORT`. |
| `DateFormat.getDateInstance(int style, Locale locale)` | Chỉ ngày, chọn style và locale tường minh. | Phù hợp khi ứng dụng phục vụ nhiều ngôn ngữ. |
| `DateFormat.getTimeInstance()` | Chỉ giờ, style mặc định. | Không chỉ định locale. |
| `DateFormat.getTimeInstance(int style)` | Chỉ giờ theo style. | Không chỉ định locale. |
| `DateFormat.getTimeInstance(int style, Locale locale)` | Chỉ giờ theo style và locale. | Có thể chọn bố cục 12h/24h theo quy ước locale. |
| `DateFormat.getDateTimeInstance()` | Gồm ngày và giờ, style mặc định. | Hai phần đều dùng `DEFAULT`. |
| `DateFormat.getDateTimeInstance(int dateStyle, int timeStyle)` | Ngày và giờ với hai style riêng. | Thứ tự đối số là **dateStyle trước, timeStyle sau**. |
| `DateFormat.getDateTimeInstance(int dateStyle, int timeStyle, Locale locale)` | Ngày, giờ và locale đều được xác định. | Cách tường minh nhất khi dùng legacy API. |
| `DateFormat.getInstance()` | Factory tiện dụng ngày+giờ ngắn. | Tương đương dùng `SHORT` cho ngày và giờ. |

Các phiên bản không có tham số `Locale` dựa vào locale mặc định của JVM phục vụ định dạng (liên quan `Locale.Category.FORMAT`). Trong môi trường máy chủ có nhiều người dùng, **không nên thay `Locale.setDefault(...)` theo từng request**. Hãy truyền locale của người dùng vào factory có tham số `Locale` để tránh tác động thread khác.

### Ba nhóm factory tương ứng ba nhu cầu

```java
Locale locale = Locale.US;

DateFormat dateOnly =
        DateFormat.getDateInstance(DateFormat.LONG, locale);

DateFormat timeOnly =
        DateFormat.getTimeInstance(DateFormat.SHORT, locale);

DateFormat dateAndTime =
        DateFormat.getDateTimeInstance(
                DateFormat.MEDIUM, DateFormat.SHORT, locale);
```

Đây là các câu lệnh minh họa đặt trong một phương thức Java, cần import `java.text.DateFormat` và `java.util.Locale`. Trong phần sau có chương trình hoàn chỉnh chạy bằng Java 17+.

Không dùng `getTimeInstance(...)` nếu cần hiển thị ngày; không dùng `getDateInstance(...)` khi UI cần cả giờ. Với `getDateTimeInstance(...)`, **dateStyle** và **timeStyle** được chọn riêng: ví dụ `MEDIUM` cho ngày, `SHORT` cho giờ.

### Không tự đoán pattern của factory

Factory có thể tạo pattern giống một `SimpleDateFormat` cụ thể, nhưng **hợp đồng của API là cung cấp dạng định dạng phù hợp với locale và style**, không hứa mọi JDK luôn dùng cùng pattern/chuỗi. Dữ liệu CLDR và nhà cung cấp locale có thể thay đổi theo phiên bản JDK, cấu hình `java.locale.providers` hoặc môi trường.

Do đó, với bài toán UI, nên xem kết quả theo style là **bản địa hóa để hiển thị**, không phải một protocol string để truyền vào API hay so sánh cứng từng byte giữa mọi phiên bản JDK.

## 4. Bốn mức style và ý nghĩa thực tế

`DateFormat` định nghĩa các hằng:

| Hằng | Giá trị hằng trong API | Vai trò thường gặp |
| --- | ---: | --- |
| `DateFormat.FULL` | `0` | Biểu diễn đầy đủ, thường có thứ và tên tháng (với date). |
| `DateFormat.LONG` | `1` | Ngày giờ dạng dài, thường có tên tháng hoặc thông tin zone ở time. |
| `DateFormat.MEDIUM` | `2` | Độ dài trung bình; `DEFAULT` tương đương `MEDIUM`. |
| `DateFormat.SHORT` | `3` | Biểu diễn ngắn, thường dùng chữ số và thành phần tối giản. |

**Style không phải bộ ký tự cố định.** Ví dụ `FULL` với `Locale.US` có thể là `Tuesday, January 2, 2024`; với locale khác, thứ và tháng có thể ở vị trí khác, dùng từ bản địa hoặc hệ chữ số khác. `SHORT` có thể không chứa năm đủ bốn chữ số; khi parse cần cẩn thận với năm hai chữ số và tính mơ hồ.

Với cùng ngày 2/1/2024, một cấu hình Java 17 phổ biến cho `Locale.US` cho:

| Factory date-only | Ví dụ đầu ra |
| --- | --- |
| `getDateInstance(FULL, Locale.US)` | `Tuesday, January 2, 2024` |
| `getDateInstance(LONG, Locale.US)` | `January 2, 2024` |
| `getDateInstance(MEDIUM, Locale.US)` | `Jan 2, 2024` |
| `getDateInstance(SHORT, Locale.US)` | `1/2/24` |

Ví dụ chỉ nhằm giúp đọc style; **đừng viết code nghiệp vụ giả định cố định các dấu câu, từ viết tắt hoặc độ rộng số của mọi locale/JDK**.

Đối với giờ, `DateFormat.getTimeInstance(SHORT, Locale.US)` có thể thể hiện `3:04 PM`, còn ở locale ưu tiên 24 giờ thường có kiểu khác. `LONG/FULL` có thể thể hiện thêm time zone hoặc tên zone, phụ thuộc implementation và locale. Không đồng nhất `Locale.US` với múi giờ Hoa Kỳ; locale và zone là hai cấu hình độc lập.

### DEFAULT và MEDIUM

`DateFormat.DEFAULT` có cùng giá trị với `DateFormat.MEDIUM`. Do đó `getDateInstance()` là dạng thông dụng tương ứng với `getDateInstance(DEFAULT)` và locale mặc định; `getDateTimeInstance()` dùng style mặc định cho cả hai thành phần. Việc “mặc định” này **không cố định ngôn ngữ**, vì default locale JVM có thể khác giữa máy developer và máy chạy CI.

## 5. Locale: ngôn ngữ, vùng và dữ liệu định dạng

`Locale` lưu danh tính ngôn ngữ/vùng/biến thể, ví dụ:

```java
Locale us = Locale.US;
Locale france = Locale.FRANCE;
Locale vietnam = Locale.forLanguageTag("vi-VN");

DateFormat usDate =
        DateFormat.getDateInstance(DateFormat.LONG, us);
DateFormat frDate =
        DateFormat.getDateInstance(DateFormat.LONG, france);
DateFormat viDate =
        DateFormat.getDateInstance(DateFormat.LONG, vietnam);
```

Với cùng `Date` và cùng `TimeZone`, ba formatter có thể tạo ba cách viết ngày khác nhau. Locale ảnh hưởng trật tự, từ vựng, tên tháng/thứ, cách viết giờ và các quy tắc có liên quan. Nó **không tự chuyển** từ đơn vị thời gian UTC sang TP.HCM, cũng không thay `Date` thành một thời điểm khác.

### Vì sao nên truyền locale tường minh?

- Người dùng A muốn giao diện tiếng Việt, người dùng B muốn tiếng Anh; cùng một JVM phục vụ cả hai.
- CI hoặc Docker container có thể đặt `Locale.getDefault()` khác máy lập trình.
- Test trở nên ổn định hơn khi có tham số locale rõ ràng, không phụ thuộc thứ tự chạy các test khác.
- Bạn không cần sửa global state bằng `Locale.setDefault(...)`; đây là thao tác có thể gây race trong ứng dụng đa luồng.

### Locale mặc định cho FORMAT

Java có `Locale.Category.DISPLAY` và `Locale.Category.FORMAT`. Những factory định dạng không có tham số locale sử dụng mặc định dành cho formatting; mặc định này có thể khác locale dùng để hiển thị tên ngôn ngữ.

Ví dụ về nguy cơ (chỉ minh họa, **không khuyến nghị chạy trong web request**):

```java
Locale.setDefault(Locale.Category.FORMAT, Locale.FRANCE);
DateFormat df = DateFormat.getDateInstance(DateFormat.LONG);
```

Điều này tác động đến cấu hình chung của JVM. Khi buộc phải thử thay đổi default locale trong unit test, cần chụp và khôi phục đầy đủ các mặc định liên quan trong `try/finally`, đồng thời tránh test song song không được điều phối. Thông thường, dùng `getDateInstance(style, locale)` là giải pháp tốt hơn.

### Những locale nào được hỗ trợ?

`DateFormat.getAvailableLocales()` trả tập locale mà các factory có thể hỗ trợ theo môi trường Java. Tập locale/data không phải lời cam kết về mọi bản dịch/tên tháng hiển thị giống hệt qua các phiên bản JDK. Với tính năng sản phẩm quan trọng, kiểm thử các locale chính mà ứng dụng cho phép; đừng tự suy từ tên quốc gia rằng mọi ngày giờ sẽ được biểu diễn đúng như người dùng mong muốn.

## 6. TimeZone: phần bắt buộc để kiểm soát thời điểm

`DateFormat` tạo ra đối tượng có `Calendar`/`TimeZone`; nếu bạn không chỉ định zone, nó có thể sử dụng múi giờ mặc định của JVM tại thời điểm cấu hình. Cùng một timestamp, ngày/giờ địa phương có thể khác nhau theo zone.

Ví dụ:

```java
Date event = Date.from(
        Instant.parse("2024-01-02T00:30:00Z"));

DateFormat clock = DateFormat.getDateTimeInstance(
        DateFormat.SHORT, DateFormat.SHORT, Locale.US);
clock.setTimeZone(TimeZone.getTimeZone("UTC"));
String inUtc = clock.format(event);

clock.setTimeZone(
        TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));
String inVietnam = clock.format(event);
```

Đoạn này đặt trong phương thức Java và cần import `Date`, `Instant`, `DateFormat`, `TimeZone` và `Locale`. Hai chuỗi có thể khác giờ hiển thị vì cùng mốc `00:30Z` là `07:30` tại TP.HCM. **Bạn không sửa `Date event`, chỉ đổi formatter.**

**Một nguyên tắc đặc biệt:** `Locale` quyết định cách viết ngày giờ; `TimeZone` quyết định các trường giờ/ngày địa phương của một thời điểm. Đừng lấy locale của người dùng rồi đoán timezone bằng cách ghép mã country; một quốc gia có thể có nhiều múi giờ, và một người có thể muốn hiển thị giờ ở khu vực khác.

### TimeZone, DST và ranh giới ngày

Với múi giờ có daylight saving time, độ lệch UTC có thể thay đổi theo ngày. Không cộng trừ giờ bằng tay. Khi cần hiển thị hoặc phân tích timestamp, dùng `TimeZone` có region ID rõ ràng; với dự án mới, ưu tiên `ZoneId` và `ZonedDateTime` của `java.time`.

Dùng một timestamp cố định trong test là chưa đủ nếu logic có lịch hẹn; nên kiểm tra thêm thời điểm gần nửa đêm và các DST transition ở vùng phù hợp.

### Lưu ý về mã zone sai

`TimeZone.getTimeZone(String)` có thể trả về `GMT` khi ID không nhận diện được, thay vì báo lỗi như kỳ vọng. Với dữ liệu múi giờ từ người dùng, không được coi kết quả này là bằng chứng zone ID hợp lệ. Dùng danh sách ID được hỗ trợ hoặc API `ZoneId.of(...)` (có lỗi rõ hơn cho ID sai) cùng quy tắc validation ở ranh giới input.

## 7. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`DateFormatFactoriesDemo.java`**. Chương trình tạo các formatter độc lập bằng factory, truyền `Locale` rõ ràng, đặt zone `UTC` và tắt lenient khi kiểm tra parse. Với output giờ theo `Locale.US`, hàm `view(...)` quy hai dạng khoảng trắng không ngắt thường gặp thành khoảng trắng thông thường để dễ đọc log; nó **không biến mọi format của mọi JDK thành một chuỗi bất biến**.

```java
import java.text.DateFormat;
import java.text.ParsePosition;
import java.time.Instant;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class DateFormatFactoriesDemo {

    private static DateFormat utc(DateFormat format) {
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        format.setLenient(false);
        return format;
    }

    private static String view(DateFormat format, Date date) {
        // Chuẩn hóa khoảng trắng của đầu ra demo:
        // narrow no-break space và no-break space.
        return format.format(date)
                .replace('\u202F', ' ')
                .replace('\u00A0', ' ');
    }

    private static void tryParse(DateFormat format, String input) {
        ParsePosition position = new ParsePosition(0);
        Date parsed = format.parse(input, position);

        boolean complete = parsed != null
                && position.getIndex() == input.length();

        System.out.println("parse(" + input + ")="
                + (complete ? "OK" : "REJECTED")
                + "; consumed=" + position.getIndex()
                + "/" + input.length());
    }

    public static void main(String[] args) {
        Date fixed = Date.from(
                Instant.parse("2024-01-02T15:04:05Z"));

        Locale us = Locale.US;
        Locale fr = Locale.FRANCE;

        System.out.println("us.full=" + view(utc(
                DateFormat.getDateInstance(DateFormat.FULL, us)),
                fixed));
        System.out.println("us.long=" + view(utc(
                DateFormat.getDateInstance(DateFormat.LONG, us)),
                fixed));
        System.out.println("us.medium=" + view(utc(
                DateFormat.getDateInstance(DateFormat.MEDIUM, us)),
                fixed));
        System.out.println("us.short=" + view(utc(
                DateFormat.getDateInstance(DateFormat.SHORT, us)),
                fixed));

        System.out.println("us.time=" + view(utc(
                DateFormat.getTimeInstance(DateFormat.SHORT, us)),
                fixed));
        System.out.println("us.both=" + view(utc(
                DateFormat.getDateTimeInstance(
                        DateFormat.MEDIUM,
                        DateFormat.SHORT, us)),
                fixed));

        System.out.println("fr.long=" + view(utc(
                DateFormat.getDateInstance(DateFormat.LONG, fr)),
                fixed));

        DateFormat parser = utc(
                DateFormat.getDateInstance(DateFormat.LONG, us));

        tryParse(parser, "January 2, 2024");
        tryParse(parser, "January 2, 2024junk");
        tryParse(parser, "February 30, 2024");
    }
}
```

Biên dịch và chạy bằng JDK 17+ trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 DateFormatFactoriesDemo.java
java DateFormatFactoriesDemo
```

**Stdout đã kiểm tra trên một môi trường Java 17 với dữ liệu locale tương ứng:**

```text
us.full=Tuesday, January 2, 2024
us.long=January 2, 2024
us.medium=Jan 2, 2024
us.short=1/2/24
us.time=3:04 PM
us.both=Jan 2, 2024, 3:04 PM
fr.long=2 janvier 2024
parse(January 2, 2024)=OK; consumed=15/15
parse(January 2, 2024junk)=REJECTED; consumed=15/19
parse(February 30, 2024)=REJECTED; consumed=0/17
```

**Ghi chú về tính tái lập:** các chuỗi chữ ngày giờ như thứ/tên tháng, dấu câu, style `SHORT` và chữ viết tắt có thể khác giữa các cấu hình locale provider/JDK. Ví dụ dùng một runtime Java và dữ liệu mẫu cố định để có đầu ra trên; trong dự án thật, nếu muốn khẳng định chính xác từng ký tự ở mọi bản JDK, đừng dựa vào factory locale với style mặc định làm hợp đồng dữ liệu. Hãy kiểm thử theo phiên bản triển khai, hoặc dùng formatter/pattern xác định rõ khi cần chuỗi máy–máy cố định.

### Giải thích kết quả

1. `us.full`, `us.long`, `us.medium`, `us.short` cho thấy bốn cách trình bày cùng ngày theo các style.
2. `us.time` chỉ lấy phần giờ; `us.both` kết hợp ngày ở `MEDIUM` với giờ ở `SHORT`. Khoảng trắng không ngắt trong một số locale/JDK được chuẩn hóa để dễ đọc demo.
3. `fr.long` minh họa **cùng một timestamp và zone** nhưng locale khác nên dùng tên tháng tiếng Pháp và trật tự ngày khác.
4. `parse(...)=OK` cho chuỗi hợp pattern và được đọc **hết 15 ký tự**.
5. `January 2, 2024junk` được parser đọc ra một ngày ở phần đầu nhưng còn bốn ký tự `junk`, nên hàm validation của demo từ chối dù `parsed != null`.
6. `February 30, 2024` không tồn tại trong lịch; vì đã `setLenient(false)`, parser không sửa ngày thành tháng 3 mà từ chối.

Chương trình không thay đổi locale/timezone mặc định của JVM. Mỗi factory được tạo cho một mục đích riêng; không chia sẻ formatter mutable sang thread khác.

## 8. Parse là thao tác khác format

`DateFormat.format(...)` nhận `Date` và tạo **chuỗi hiển thị**. `DateFormat.parse(...)` thử đọc **chuỗi đầu vào** và trả `Date`. Hai chiều này không nhất thiết đối xứng tuyệt đối:

- `SHORT` có thể bỏ thế kỷ hoặc giây, nên chuỗi không giữ mọi chi tiết của timestamp nguồn.
- `getDateInstance(...)` chỉ thể hiện ngày, không thể bảo toàn giờ/phút/giây khi format rồi parse ngược.
- Khi parse date-only thành `Date`, time trong ngày được resolver/calendar xác lập theo quy tắc và zone; không nên coi đây là timestamp của sự kiện gốc.
- Chuỗi nhập không có time zone sẽ được diễn giải bằng zone của formatter, điều này có thể khác timezone người nhập tưởng tượng.
- Parser có thể chấp nhận một tiền tố hợp lệ của chuỗi và bỏ phần đuôi nếu không kiểm tra vị trí cuối.

### parse(String) và ParseException

`DateFormat.parse(String)` có thể ném `java.text.ParseException` khi không đọc được chuỗi. Nếu ứng dụng cần phát hiện **chuỗi đuôi bị bỏ qua**, thường nên dùng `parse(String, ParsePosition)` rồi xác nhận:

```java
ParsePosition pos = new ParsePosition(0);
Date parsed = formatter.parse(input, pos);

boolean valid = parsed != null
        && pos.getIndex() == input.length();
```

Đây là đoạn minh họa đặt trong phương thức Java (với `formatter`, `input` đã có và import `ParsePosition`/`Date`); ví dụ độc lập đã trình bày ở mục 7.

Với parse sai, `parse(String, ParsePosition)` có thể trả `null`, cập nhật `errorIndex`. Nhưng **đọc hết chuỗi mới chỉ chứng minh parser chấp nhận cấu trúc nó hiểu**, chưa chứng minh ngày nằm trong miền nghiệp vụ hoặc input đúng định dạng mà form yêu cầu.

### setLenient(false): không tự sửa ngày không tồn tại

`DateFormat` sử dụng một `Calendar` trong cơ chế parse. Nếu parser có tính lenient, nó có thể điều chỉnh `31/02` thành một ngày khác thay vì báo sai. Khi muốn người dùng nhập một ngày lịch thực sự hợp lệ, đặt:

```java
DateFormat formatter =
        DateFormat.getDateInstance(DateFormat.SHORT, Locale.US);
formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
formatter.setLenient(false);
```

Đoạn này đặt trong phương thức Java với import phù hợp. Sau đó, **vẫn cần** kiểm tra parse tiêu thụ hết chuỗi và validation domain. Chọn `SHORT` để input có thể mang năm hai chữ số, nên trong ứng dụng mới nên dùng một pattern yêu cầu năm đầy đủ rõ ràng hơn nếu dữ liệu quan trọng.

### Năm hai chữ số và tính mơ hồ

Các factory `SHORT` có thể dùng năm `24` thay vì `2024`. Khi parse, một số implementation có quy tắc cửa sổ năm hai chữ số; kết quả có thể phụ thuộc thời điểm tạo formatter, cấu hình provider và implementation. Tránh lưu ngày sinh, ngày hạn hợp đồng hoặc lịch tài chính dưới dạng năm hai chữ số. Với input của người dùng, xác định format năm đầy đủ và ưu tiên `java.time.DateTimeFormatter` có resolver strict.

## 9. Những hạn chế của API ngày giờ cũ

### 9.1. Date và Calendar khác mục đích

`java.util.Date` mô tả một mốc thời gian, còn `Calendar` quản lý các trường lịch theo timezone/locale và có thể bị thay đổi. `DateFormat` kết hợp chúng trong quá trình trình bày/parse. Điều này dễ dẫn tới nhầm lẫn: thấy `DateFormat` in ngày khác không có nghĩa `Date` nguồn đã bị sửa.

`DateFormat.setCalendar(Calendar)` là thao tác cấu hình sâu; khi đổi calendar, nên xác minh lại timezone, chế độ lenient và ngữ nghĩa chronology đang dùng. Không dùng `Calendar` như kiểu dữ liệu bất biến cho mọi nghiệp vụ.

### 9.2. Factory không bảo đảm luôn trả SimpleDateFormat

Đừng viết:

```java
SimpleDateFormat df = (SimpleDateFormat)
        DateFormat.getDateInstance(DateFormat.SHORT, locale);
```

nếu không có yêu cầu và bảo đảm về implementation. Đoạn code này là **minh họa cách ép kiểu dễ gây rủi ro**, không phải lời khuyên. Đối với API chung, giữ kiểu `DateFormat`. Nếu thực sự cần một pattern cụ thể và đang làm việc với legacy library, có thể chủ động tạo `new SimpleDateFormat(pattern, locale)`, nhưng nhớ kiểm soát calendar, timezone, lenient và thread safety.

### 9.3. DateFormat mutable, không thread-safe

`DateFormat` và `SimpleDateFormat` là **mutable** và không được bảo đảm thread-safe khi nhiều thread dùng cùng một instance mà không đồng bộ. `setTimeZone`, `setLenient`, `setCalendar` và các thao tác định dạng/parse có thể phụ thuộc trạng thái nội bộ.

Các lựa chọn phù hợp:

1. Tạo instance formatter mới trong phương thức hoặc phạm vi request.
2. Clone một formatter mẫu khi cần cấu hình chung và bảo đảm các bản sao riêng biệt.
3. Đồng bộ hóa toàn bộ truy cập nếu buộc phải chia sẻ, nhưng cần hiểu chi phí contention và tránh bỏ sót điểm truy cập.

**Không nên tạo một `static DateFormat` rồi đổi locale/timezone theo mỗi request.** Với dự án mới, `java.time.format.DateTimeFormatter` immutable và thread-safe giúp giải quyết nhiều vấn đề này.

### 9.4. Lệ thuộc locale mặc định và TZDB

Một formatter được tạo bằng factory không có `Locale` và không gán zone có thể cho output khác khi chạy trên máy có cấu hình JVM/OS khác. Các tên zone, kiểu chữ và quy tắc địa phương cũng chịu ảnh hưởng dữ liệu locale và cơ sở dữ liệu múi giờ của môi trường Java. Trong test, truyền locale và zone rõ ràng, sử dụng timestamp cố định; không lấy ngày giờ hiện tại làm điểm chuẩn nếu muốn stdout kiểm thử ổn định.

## 10. Khi nào dùng factory và khi nào cần pattern cụ thể?

| Yêu cầu | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Hiển thị ngày cho người dùng theo locale | `DateFormat.getDateInstance(style, locale)` | Có format bản địa mà không cần tự viết mẫu của mỗi ngôn ngữ. |
| Hiển thị giờ cho người dùng | `DateFormat.getTimeInstance(style, locale)` | Theo quy tắc trình bày giờ của locale. |
| Hiển thị ngày+giờ cùng nhau | `DateFormat.getDateTimeInstance(dateStyle, timeStyle, locale)` | Cho phép style ngày và giờ khác nhau. |
| Format dùng trong log giao tiếp máy–máy | `DateTimeFormatter.ISO_INSTANT`/ISO formatter phù hợp | Không phụ thuộc cách viết chữ theo locale UI. |
| Ngày sinh, lịch hẹn thuần ngày | `LocalDate` + `DateTimeFormatter` | Không ép ngày thuần túy thành một timestamp tùy múi giờ. |
| Timestamp tuyệt đối để lưu/trao đổi | `Instant` hoặc kiểu thời gian có offset phù hợp | Định nghĩa rõ điểm trên timeline. |
| Nhập ngày có pattern được sản phẩm quy định | `DateTimeFormatter` + `ResolverStyle.STRICT` | Bắt lỗi ngày không có thật và tránh nhiều bất định của legacy parse. |
| Bảo trì API legacy nhận/trả `Date` | `DateFormat` + locale/zone/lenient rõ ràng | Giữ tương thích nhưng quản lý rủi ro. |
| Formatter dùng chung nhiều thread | `DateTimeFormatter` | Immutable, phù hợp code Java hiện đại. |

Các factory `DateFormat` là lựa chọn hữu ích khi **bảo trì hệ thống cũ** hoặc tích hợp với thư viện chỉ dùng `Date`/`Calendar`. Trong code mới, ưu tiên `java.time` không có nghĩa phải loại bỏ mọi factory lập tức, mà là chọn API rõ nghĩa cho domain và tránh thêm phụ thuộc vào trạng thái mutable.

### Tương tác Date với Instant

Khi code legacy nhận `Date` nhưng domain mới dùng `Instant`:

```java
Instant instant = Instant.parse("2024-01-02T15:04:05Z");
Date date = Date.from(instant);
Instant back = date.toInstant();
```

Đoạn này có thể chạy trong một phương thức Java với import `Instant`, `Date`. Việc chuyển đổi này giữ ý nghĩa thời điểm ở độ chính xác milliseconds của `Date`; nó **không thêm timezone hay Locale vào Instant**. Với timestamp có nano giây, cần xem xét giới hạn chính xác khi đi qua `Date`.

## 11. Các lỗi phổ biến và cách khắc phục

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dùng `getDateInstance()` cho mọi người dùng | Kết quả phụ thuộc mặc định JVM, không theo locale từng người. | Truyền `Locale` tường minh. |
| Dùng `getDateInstance(...)` khi cần giờ | Format chỉ có ngày. | Dùng `getDateTimeInstance(...)`. |
| Đảo `dateStyle` và `timeStyle` | Ngày và giờ nhận style không như dự định. | Luôn đọc đúng thứ tự tham số. |
| Nghĩ `SHORT` luôn là `dd/MM/yyyy` | Locale có thể đảo ngày/tháng và rút năm. | Để factory quyết định UI; dùng input pattern rõ khi cần. |
| Nghĩ locale tự quyết định zone | Người dùng ở cùng ngôn ngữ có thể thuộc nhiều vùng giờ. | Chọn `TimeZone`/`ZoneId` theo ngữ cảnh. |
| Dùng `TimeZone.getTimeZone` với ID không xác minh | ID sai có thể fallback về GMT. | Validate zone ID; xem xét `ZoneId.of`. |
| Mặc định parse thành công nghĩa input sạch | Parser có thể bỏ ký tự đuôi. | Dùng `ParsePosition` và kiểm tra đã đọc hết. |
| Không gọi `setLenient(false)` với ngày nhập | Ngày không có thật có thể bị tự điều chỉnh. | Tắt lenient và thêm domain validation. |
| Đưa ngày `MM/dd/yy` vào cơ sở dữ liệu | Năm hai chữ số và cách viết ngày mơ hồ. | Dùng kiểu ngày/chuẩn ISO có schema rõ ràng. |
| Ép mọi kết quả factory sang `SimpleDateFormat` | Phụ thuộc implementation. | Giữ kiểu `DateFormat` hoặc tạo mẫu riêng có chủ đích. |
| Dùng static `DateFormat` trong web server | Race và trạng thái chéo giữa nhiều request. | Tạo mới/clone/đồng bộ, hoặc migrate `DateTimeFormatter`. |
| So sánh output FULL giữa mọi JDK bằng exact text | Dữ liệu CLDR và provider có thể khác. | Test chức năng, cố định môi trường khi cần snapshot test. |

## 12. Bộ test nên có

Để tự tin rằng localization bằng `DateFormat` vận hành đúng, tối thiểu cần kiểm thử:

- **Date/time/dateTime:** mỗi factory chỉ hiển thị thành phần đúng nhu cầu, hai style riêng của `getDateTimeInstance` được áp dụng đúng.
- **Locale khác nhau:** cùng timestamp và timezone được biểu diễn bằng ngôn ngữ/định dạng khác nhau mà không làm thay đổi giá trị nguồn.
- **FULL/LONG/MEDIUM/SHORT:** kiểm tra theo locale được hỗ trợ; không dựa vào một pattern cứng dùng cho mọi JDK.
- **TimeZone:** test UTC và region zone khác, nhất là thời điểm gần ranh giới ngày.
- **Parse thành công:** input đúng cấu trúc và được đọc hết; sau parse, thời điểm có ý nghĩa chính xác.
- **Parse có đuôi:** từ chối chuỗi như `January 2, 2024junk` nếu form yêu cầu toàn bộ input hợp lệ.
- **Ngày không tồn tại:** `February 30, 2024` phải bị từ chối khi `setLenient(false)`.
- **Năm hai chữ số:** xác định policy, không âm thầm chấp nhận ngày gây mơ hồ.
- **DST gap/overlap:** nếu domain có thời gian hẹn ở vùng có DST, kiểm tra quyết định nghiệp vụ riêng, không chỉ so chuỗi hiển thị.
- **Concurrency:** không chia sẻ formatter mutable không có đồng bộ giữa test/thread.
- **Dữ liệu bất thường:** null, chuỗi rỗng, giới hạn độ dài, dữ liệu có Unicode whitespace hoặc ký hiệu ngày theo locale khác.

Đối với code parse input từ người dùng, ngoài việc đọc hết chuỗi, còn cần validation miền dữ liệu: ngày sinh không ở tương lai nếu sản phẩm yêu cầu, ngày đến hạn trong khoảng cho phép, giờ hẹn hợp lệ ở timezone người dùng. **DateFormat không phải bộ kiểm tra toàn bộ quy tắc nghiệp vụ.**

## 13. Bài tập thực hành

**Bài 1 — Ba factory:** cùng `Date.from(Instant.parse("2024-01-02T15:04:05Z"))`, thử `getDateInstance`, `getTimeInstance` và `getDateTimeInstance` ở `Locale.US`. Đặt `UTC` cho tất cả formatter. Giải thích khác biệt giữa ngày, giờ và cả ngày+giờ.

**Bài 2 — Bốn style:** với `FULL`, `LONG`, `MEDIUM`, `SHORT` cho ngày, thử `Locale.US` và `Locale.FRANCE`. Ghi lại cách viết ngày thay đổi; không đoán pattern dựa trên chữ viết tắt tiếng Anh.

**Bài 3 — Cấu hình zone:** format `2024-01-02T00:30:00Z` theo `UTC` và `Asia/Ho_Chi_Minh` với cùng locale/style. Xác nhận `Date` không đổi, chỉ giờ hiển thị thay đổi. Thử một zone có DST ở ngày chuyển mùa và giải thích vì sao không cộng offset cố định.

**Bài 4 — Parse và kiểm tra chuỗi thừa:** parse `January 2, 2024`, `January 2, 2024junk` và `February 30, 2024` với `getDateInstance(LONG, Locale.US)`, `UTC`, `setLenient(false)`. In kết quả, `ParsePosition.getIndex()` và `getErrorIndex()`; phân biệt thành công kỹ thuật với input hợp lệ theo policy.

**Bài 5 — Default locale:** chạy test với mặc định FORMAT khác nhau (có cô lập và restore theo `try/finally`), so sánh factory không có locale và factory có `Locale.US` tường minh. Vì sao ứng dụng nhiều người dùng không nên đổi default locale trong mỗi request?

**Bài 6 — Di chuyển sang java.time:** viết cùng tính năng bằng `Instant`/`ZoneId`/`DateTimeFormatter.ofLocalizedDateTime(...)`. So sánh API bất biến với `DateFormat` mutable; xác định cách xử lý các chuỗi ngày giờ lưu trong database so với chuỗi hiển thị cho người dùng.

## 14. Checklist kiến thức

- [ ] Phân biệt `DateFormat` với `Date`, `Calendar`, `TimeZone` và `Locale`.
- [ ] Sử dụng đúng `getDateInstance`, `getTimeInstance`, `getDateTimeInstance` và `getInstance`.
- [ ] Biết ý nghĩa `FULL`, `LONG`, `MEDIUM`, `SHORT`; `DEFAULT` tương ứng `MEDIUM`.
- [ ] Chọn và truyền `Locale` tường minh, tránh phụ thuộc default `FORMAT` trong hệ thống nhiều người dùng.
- [ ] Cấu hình `TimeZone` rõ ràng khi cần kết quả tái lập; không tự cộng trừ giờ.
- [ ] Nhận biết `parse` có thể chấp nhận tiền tố, dùng `ParsePosition` kiểm tra tiêu thụ hết.
- [ ] Dùng `setLenient(false)` khi cần từ chối ngày không có thật và kiểm tra nghiệp vụ bổ sung.
- [ ] Hiểu vì sao factory locale không phải hợp đồng serialization có chuỗi cố định.
- [ ] Không chia sẻ `DateFormat` mutable giữa các thread một cách thiếu kiểm soát.
- [ ] Biết khi nào nên dùng `java.time`/`DateTimeFormatter` thay cho legacy API.

**Kết luận:** các factory của `DateFormat` là công cụ tạo formatter ngày giờ theo **mục đích (date/time/dateTime)**, **độ chi tiết (style)** và **ngữ cảnh ngôn ngữ (Locale)**. Khi dùng, hãy tách biệt time zone, parse và validation; chỉ chọn API cũ khi cần tương thích, còn code mới nên ưu tiên `java.time` với mô hình thời gian rõ ràng.
