# DateTimeFormatter.ofLocalizedPattern() và mẫu yêu cầu trường ngày giờ

Khi xây ứng dụng đa ngôn ngữ, ta thường muốn **chỉ định các trường ngày/giờ cần hiển thị** — ví dụ năm, tháng, ngày hoặc giờ/phút — nhưng để từng locale quyết định **thứ tự, dấu phân cách, tên tháng và cách trình bày tự nhiên**.

Từ **Java 19**, `java.time.format.DateTimeFormatter` cung cấp:

~~~java
DateTimeFormatter.ofLocalizedPattern(String requestedTemplate)
~~~

Phương thức nhận một **mẫu yêu cầu trường (requested template)**. Nó không phải pattern trình bày cố định. Java tìm kiểu định dạng bản địa hóa gần nhất cho các trường đã yêu cầu dựa trên quy tắc Unicode LDML và dữ liệu locale sẵn có. Đây là lựa chọn hữu ích khi `FormatStyle.SHORT/MEDIUM/LONG/FULL` không cho đúng *tập trường* mà sản phẩm muốn hiển thị.

**Chú ý phiên bản:** `ofLocalizedPattern(String)` được đưa vào JDK từ **Java 19**, vì thế mã sử dụng phương thức này **không biên dịch với `--release 17` hoặc JDK 17**. Phần mã chạy đầy đủ dưới đây dành cho **Java 19 trở lên**; bài có phương án riêng cho Java 17 ở mục 10.

## 1. Bài toán: yêu cầu trường, không áp đặt cách sắp xếp

Giả sử cần hiển thị ngày 16/06/2020. Hai người dùng có thể muốn cùng ba trường **năm, tháng, ngày**, nhưng cách thể hiện khác nhau:

~~~text
Locale.US: 6/16/2020
Locale.UK: 16/06/2020
~~~

Nếu dùng một pattern cứng `"dd/MM/yyyy"`, người dùng Mỹ vẫn nhận thứ tự ngày/tháng do lập trình viên áp đặt. Nếu dùng `"MM/dd/yyyy"`, người dùng Anh cũng bị áp thứ tự của Mỹ. Ngoài thứ tự, locale còn tác động cách viết tên tháng, từ nối và dấu phân cách.

Với `ofLocalizedPattern("yMd")`, ta đang nói:

- `y`: cần **năm**.
- `M`: cần **tháng**.
- `d`: cần **ngày trong tháng**.
- Thứ tự mong muốn trong template là **thứ tự chuẩn để mô tả trường**, không phải chỉ dẫn in năm trước tháng trước ngày.

Java có thể trình bày thành ngày/tháng/năm, tháng/ngày/năm hoặc dạng khác phù hợp locale. Việc cung cấp template là yêu cầu **tập trường và hình thức gần đúng**; nó không bảo đảm một mẫu byte-for-byte cố định trên mọi JDK/CLDR.

## 2. Ba cách tạo DateTimeFormatter dễ nhầm lẫn

| API | Đầu vào | Mục đích | Ví dụ |
| --- | --- | --- | --- |
| `ofPattern(pattern, locale)` | **Pattern định dạng cố định** | Kiểm soát vị trí ký hiệu, dấu phân cách, literal | `"dd/MM/uuuu"` |
| `ofLocalizedDate(FormatStyle.MEDIUM)` | **Mức kiểu dáng** | Để locale chọn cách hiện đầy đủ một ngày theo mức MEDIUM | `FormatStyle.MEDIUM` |
| `ofLocalizedPattern(requestedTemplate)` | **Mẫu yêu cầu trường** | Chọn trường cần có; để locale chọn mẫu phù hợp gần nhất | `"yMd"`, `"yMMM"`, `"Hm"` |

Cả `ofLocalizedDate(...)` lẫn `ofLocalizedPattern(...)` đều cung cấp cách định dạng phụ thuộc locale. Khác biệt quan trọng là `FormatStyle` quyết định một **cấp độ trình bày chung**, trong khi requested template quyết định các **thành phần muốn hiển thị**.

Ví dụ khi UI chỉ cần **tháng và năm**, không có ngày, `ofLocalizedDate(FormatStyle.MEDIUM)` không phải lựa chọn trực tiếp vì nó là định dạng một ngày đầy đủ. `ofLocalizedPattern("yMMM")` cho phép yêu cầu cụ thể **năm + tên tháng dạng rút gọn**, đồng thời vẫn để locale sắp xếp.

### ofPattern("yMd") không giống ofLocalizedPattern("yMd")

Đây là lỗi dễ gặp nhất. Với `ofPattern("yMd")`, ký hiệu `y`, `M`, `d` được diễn giải như **pattern in theo đúng trình tự chỉ định**, không tự chuyển thành thứ tự ngày/tháng theo locale. Với `ofLocalizedPattern("yMd")`, ba ký hiệu được diễn giải như **requested template** để tra mẫu bản địa hóa.

Cùng các chữ cái không có nghĩa cùng ngữ nghĩa. Quyết định phụ thuộc **phương thức** được gọi.

## 3. Cú pháp requested template: các trường ở thứ tự chuẩn

Theo tài liệu `DateTimeFormatter.ofLocalizedPattern`, template có các nhóm ký hiệu theo thứ tự từ đơn vị lớn đến nhỏ:

~~~text
G{0,5}             era
y*                 year
Q{0,5}             quarter
M{0,5}             month
w*                 week of week-based year
E{0,5}             day of week
d{0,2}             day of month
B{0,5}             period of day
[hHjC]{0,2}        hour / hour cycle
m{0,2}             minute
s{0,2}             second
[vz]{0,4}          zone
~~~

Đây là **mô tả có thứ tự các nhóm cho phép**, không phải Java regex độc lập để copy và chạy. Các nhóm có thể vắng mặt; không phải template nào cũng chứa tất cả trường. Các ký hiệu nằm ngoài tập này, hoặc có thứ tự không hợp lệ, sẽ khiến `ofLocalizedPattern` ném `IllegalArgumentException`.

Một số template nên biết:

| Requested template | Tập trường mong muốn | Trường hợp sử dụng |
| --- | --- | --- |
| `yMd` | Năm, tháng, ngày ở dạng số | Ngày ngắn có đủ ba trường |
| `yMMM` | Năm và tên tháng dạng ngắn | Nhãn tháng/năm trong lịch, báo cáo |
| `yMMMd` | Năm, tên tháng dạng ngắn và ngày | Ngày thân thiện với người đọc |
| `yMMMMd` | Năm, tháng dạng dài được yêu cầu, ngày | Định dạng chú trọng tên tháng; mẫu gần nhất còn tùy dữ liệu |
| `Hm` | Giờ dạng 24 giờ và phút | Bảng lịch với giờ/phút |
| `jm` | Giờ/phút, yêu cầu chọn chu kỳ giờ theo locale | Hiển thị giờ tự nhiên theo thiết lập locale |
| `yMMMdHm` | Năm, tháng, ngày, giờ và phút | Ngày giờ dạng gọn theo locale |

Trong phần template, `j` (và `C`) là ký hiệu đặc biệt liên quan đến chu kỳ giờ theo Unicode LDML; **không** nên giả định có thể dùng mọi ký hiệu pattern thông thường của `DateTimeFormatter.ofPattern` làm template.

### Template phải có thứ tự chuẩn, dù output không buộc theo thứ tự đó

Các ví dụ **không hợp lệ**:

~~~text
dMy              // ngày-tháng-năm: thứ tự sai cho requested template
yyyy-MM-dd       // dấu gạch ngang là literal pattern, không phải ký hiệu template
dd/MM/yyyy       // dấu / và thứ tự đều không phải requested template hợp lệ
uMMdd            // ký hiệu 'u' của pattern thông thường không được hỗ trợ trong template
~~~

Chọn `ofPattern("yyyy-MM-dd")` nếu mục đích là hiển thị hoặc xuất dữ liệu **chính xác** theo pattern có dấu phân cách cố định. Không thay dấu `-` bằng cách bỏ đi rồi dùng `ofLocalizedPattern` nếu hợp đồng yêu cầu output bất biến.

### Số lần lặp ký hiệu nói gì?

Số lần lặp ký hiệu yêu cầu cách thể hiện như số hoặc văn bản (ví dụ `M` so với `MMM`). Tuy nhiên, phương thức lựa chọn **mẫu bản địa hóa gần nhất theo LDML**. Vì vậy không nên hứa rằng template `yMMMMd` sẽ luôn cho tên tháng đầy đủ trong mọi locale và mọi JDK: lựa chọn cuối cùng dựa trên các mẫu có sẵn và thuật toán matching, có thể không trùng hoàn toàn mức độ dài bạn tưởng tượng.

Nếu một đặc tả yêu cầu **đúng thứ tự, đúng ký tự, đúng width và đúng dấu phân cách** thì `ofPattern` hoặc formatter tự xây, có kiểm thử locale, có thể phù hợp hơn requested template.

## 4. Locale quyết định kết quả ở đâu?

Tạo formatter bằng:

~~~java
DateTimeFormatter f = DateTimeFormatter.ofLocalizedPattern("yMd");
~~~

Formatter trả về ban đầu dùng **locale mặc định cho FORMAT** của JVM, không phải mặc nhiên là `Locale.US`. Vì vậy, để ứng dụng có thể dự đoán và kiểm thử kết quả, hãy gắn locale tường minh:

~~~java
DateTimeFormatter us = DateTimeFormatter
        .ofLocalizedPattern("yMd")
        .withLocale(Locale.US);

DateTimeFormatter uk = DateTimeFormatter
        .ofLocalizedPattern("yMd")
        .withLocale(Locale.UK);
~~~

Đây là **các đoạn minh họa** bên trong phương thức đã import `java.time.format.DateTimeFormatter` và `java.util.Locale`. `DateTimeFormatter` là bất biến và an toàn khi chia sẻ giữa các luồng; `withLocale` tạo formatter mới, không sửa object gốc. Ứng dụng có thể cache formatter theo requested template + locale khi hợp lý.

Không dùng `Locale.setDefault` theo từng request để thay đổi kết quả. Đổi default locale là thay đổi trạng thái toàn cục và gây ảnh hưởng giữa các request chạy đồng thời.

### withLocale và localizedBy khác nhau

`withLocale(locale)` đặt locale được dùng cho định dạng văn bản và mẫu bản địa hóa. `localizedBy(locale)` có thể đồng thời áp dụng thông tin từ Unicode locale extensions (như calendar, numbering system, region override, time zone) theo hợp đồng của API; thứ tự kết hợp với các phương thức `with...` khác có thể ảnh hưởng kết quả. Dùng `withLocale` khi mục tiêu là thay locale của formatter và kiểm soát chronology/zone riêng biệt; dùng `localizedBy` khi thực sự muốn nhận những thiết lập bản địa hóa mở rộng.

Khi chọn `Locale.forLanguageTag("th-TH-u-ca-buddhist")`, việc đặt locale vào formatter **không nên được hiểu** là đã chuyển mọi trường lịch một cách tự động: cần xem API được gọi có áp dụng extension chronology hay không và kiểm thử dữ liệu lịch cụ thể.

## 5. Ví dụ Java 19+ độc lập và kết quả kiểm chứng

Ví dụ cố định ngày/giờ để dễ kiểm thử. Nó minh họa cùng template trên hai locale, chỉ lấy tháng-năm, yêu cầu giờ/phút, dùng pattern cố định, và các trường hợp template sai.

Tạo tệp **`LocalizedTemplateDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.UnsupportedTemporalTypeException;
import java.util.Locale;

public class LocalizedTemplateDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2020, 6, 16);
        LocalTime time = LocalTime.of(13, 45);

        DateTimeFormatter numeric =
                DateTimeFormatter.ofLocalizedPattern("yMd");
        DateTimeFormatter us = numeric.withLocale(Locale.US);
        DateTimeFormatter uk = numeric.withLocale(Locale.UK);

        System.out.println("US date: " + date.format(us));
        System.out.println("UK date: " + date.format(uk));

        System.out.println("US year-month: " + date.format(
                DateTimeFormatter.ofLocalizedPattern("yMMM")
                        .withLocale(Locale.US)));

        System.out.println("US time: " + time.format(
                DateTimeFormatter.ofLocalizedPattern("Hm")
                        .withLocale(Locale.US)));

        System.out.println("Fixed pattern: " + date.format(
                DateTimeFormatter.ofPattern(
                        "yyyy-MM-dd", Locale.US)));

        try {
            DateTimeFormatter.ofLocalizedPattern("dMy");
        } catch (IllegalArgumentException ex) {
            System.out.println("Wrong order: rejected");
        }

        try {
            DateTimeFormatter.ofLocalizedPattern("yyyy-MM-dd");
        } catch (IllegalArgumentException ex) {
            System.out.println("Literal separators: rejected");
        }

        try {
            date.format(DateTimeFormatter.ofLocalizedPattern("Hm")
                    .withLocale(Locale.US));
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("Time fields missing: rejected");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 19 trở lên** (đã thử với JDK 24):

~~~bash
javac --release 19 -encoding UTF-8 LocalizedTemplateDemo.java
java LocalizedTemplateDemo
~~~

Stdout quan sát trên JDK 24 với dữ liệu locale của runtime kiểm thử:

~~~text
US date: 6/16/2020
UK date: 16/06/2020
US year-month: Jun 2020
US time: 13:45
Fixed pattern: 2020-06-16
Wrong order: rejected
Literal separators: rejected
Time fields missing: rejected
~~~

**Lưu ý quan trọng:** Những dòng định dạng theo locale (`US date`, `UK date`, `US year-month`, `US time`) là kết quả của **JDK 24 đã kiểm thử**, không phải hợp đồng bất biến trên mọi bản phát hành. Dữ liệu locale/CLDR và provider có thể được cập nhật. Các dòng báo `rejected` chứng minh lỗi input/trường thiếu, không dựa vào biểu diễn tháng/ngày của từng vùng.

### Giải thích các nhánh

1. `numeric` chỉ định `yMd`. Đặt `Locale.US` và `Locale.UK` cho hai formatter giúp thấy rõ thứ tự ngày/tháng được bản địa hóa. **Cả hai cùng yêu cầu ba trường**, nhưng kết quả trình bày khác nhau.
2. `yMMM` chỉ yêu cầu tháng và năm; ngày **không tự xuất hiện** chỉ vì input là `LocalDate`.
3. `Hm` yêu cầu giờ và phút, vì vậy `LocalTime(13,45)` cung cấp đủ trường để định dạng.
4. `ofPattern("yyyy-MM-dd")` giữ pattern cố định, khác với việc yêu cầu template `yMd`.
5. `"dMy"` không có thứ tự chuẩn của template; `"yyyy-MM-dd"` chứa literal không cho phép trong template. Hai trường hợp bị từ chối bằng `IllegalArgumentException`.
6. `LocalDate` không chứa trường giờ/phút, nên `date.format(formatter Hm)` thất bại với `UnsupportedTemporalTypeException`. Lỗi này khác với **template không hợp lệ**.

Ví dụ không cần timezone vì nó định dạng `LocalDate` và `LocalTime` (không chứa offset/zone). Với ngày giờ thực của một thời điểm trên thế giới, phải xác định `ZoneId` và chọn kiểu dữ liệu thời gian thích hợp.

## 6. Requested template có phải luôn sinh đúng các trường như yêu cầu?

Ý tưởng của requested template là để Java lựa chọn mẫu bản địa hóa đáp ứng tập trường mong muốn. Tuy nhiên, kết quả dựa trên **các mẫu locale có sẵn và phép ánh xạ gần nhất** theo LDML. Không nên đánh đồng “yêu cầu” với một cam kết bất biến rằng mọi ký hiệu, độ dài, dấu phân cách hoặc trường sẽ luôn giữ nguyên theo đúng cách nhập.

Một tình huống đặc biệt: tại một số bộ dữ liệu locale, `yMMMMd` có thể được giải quyết về một định dạng dùng tên tháng rút gọn, dù template đã yêu cầu nhiều `M`. Vì vậy ứng dụng cần kiểm thử **output thực tế của các locale được hỗ trợ** trước khi chốt thiết kế UI, đặc biệt khi cột hẹp hoặc bản in có quy chuẩn.

Khi nào dùng requested template:

- Cần tháng/năm trong bộ chọn kỳ báo cáo mà không cần ngày.
- Cần ngày với đúng trường năm-tháng-ngày, nhưng không muốn áp đặt thứ tự của một quốc gia cho toàn bộ hệ thống.
- Cần giờ/phút trong giao diện lịch hẹn, có thể chấp nhận cách trình bày tự nhiên theo locale.
- Cần cùng tập trường trong nhiều thị trường nhưng cách in nên do dữ liệu bản địa hóa quyết định.

Khi nào **không** nên dùng:

- Chuẩn kết nối giữa hai hệ thống yêu cầu chính xác `2020-06-16` hoặc ISO 8601.
- Một CSV/hợp đồng đối soát yêu cầu pattern cố định và không được thay theo JDK.
- Dữ liệu cần mọi chữ số, dấu phân cách hoặc thứ tự chính xác để so sánh máy.
- Một ngôn ngữ/vùng cụ thể chưa có mẫu đáp ứng yêu cầu; cần policy, test và giải pháp thay thế có chủ đích.

Đối với dữ liệu trao đổi máy, dùng các formatter ISO sẵn có hoặc chuẩn giao thức, không dùng localized template như một định dạng serialization.

## 7. Chọn temporal type phù hợp với trường yêu cầu

Một formatter chỉ xuất được trường mà đối tượng thời gian hỗ trợ (hoặc có thể suy ra theo cơ chế format). Bảng lựa chọn thường gặp:

| Dữ liệu | Kiểu java.time đề xuất | Requested template phù hợp |
| --- | --- | --- |
| Ngày theo lịch, không chứa giờ | `LocalDate` | `yMd`, `yMMM`, `yMMMd` |
| Giờ trong ngày, không chứa ngày | `LocalTime` | `Hm`, `jm` |
| Ngày và giờ địa phương, chưa có timezone | `LocalDateTime` | `yMMMdHm` |
| Ngày giờ đã gắn timezone | `ZonedDateTime` | `yMMMdHm` hoặc mẫu có yêu cầu vùng `z` |
| Thời điểm tuyệt đối cần hiển thị theo vùng | `Instant` + `atZone(zoneId)` | Formatter gắn locale, dùng `ZonedDateTime` |

Không đưa trực tiếp `LocalDate` vào formatter yêu cầu `H`, `m` hoặc `z` rồi mong Java tự dùng giờ hiện tại. Tương tự, `LocalDateTime` không có ZoneId, nên một template yêu cầu tên múi giờ không thể tự biết người dùng đang ở vùng nào.

Ví dụ khi dữ liệu là `Instant` và người dùng chọn một timezone:

~~~java
Instant instant = Instant.parse("2020-06-16T06:45:00Z");
ZonedDateTime userTime =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedPattern("yMMMdHm")
        .withLocale(Locale.forLanguageTag("vi-VN"));

String display = formatter.format(userTime);
~~~

Đây là **đoạn minh họa**, cần import `java.time.Instant`, `java.time.ZonedDateTime`, `java.time.ZoneId`, `java.time.format.DateTimeFormatter`, `java.util.Locale`. Không chốt output văn bản cụ thể vì dữ liệu locale có thể khác theo runtime.

**Timezone khác locale:** `Locale.forLanguageTag("vi-VN")` mô tả cách hiển thị ngôn ngữ/vùng, không tự quyết định `ZoneId.of("Asia/Ho_Chi_Minh")` là múi giờ đúng cho mọi người nói tiếng Việt.

## 8. Quy tắc giờ 12/24, day period và time zone

Với giờ/phút, template có thể yêu cầu rõ giờ 24h bằng `H`, hoặc giờ theo thiết lập bản địa thông qua `j` (và `C` trong các bối cảnh LDML phù hợp). Ví dụ:

~~~java
DateTimeFormatter twentyFour = DateTimeFormatter
        .ofLocalizedPattern("Hm")
        .withLocale(Locale.US);

DateTimeFormatter localHourCycle = DateTimeFormatter
        .ofLocalizedPattern("jm")
        .withLocale(Locale.US);
~~~

Đây là đoạn minh họa Java 19+, cần import `DateTimeFormatter` và `Locale`. Định dạng giờ dùng hour cycle theo locale có thể hiển thị AM/PM và các ký tự khoảng trắng đặc biệt tùy dữ liệu. Đừng viết parser dựa trên một chuỗi `"PM"` cố định khi cần hỗ trợ nhiều ngôn ngữ.

Yêu cầu vùng giờ qua `z` hoặc `v` không tự sinh timezone từ locale. Nếu input là `Instant`, phải gắn ZoneId hoặc dùng formatter `withZone` thích hợp. Với tên múi giờ dạng text, việc hiển thị phụ thuộc locale và dữ liệu timezone của JDK.

`DateTimeFormatter.ofLocalizedPattern` tạo formatter ISO chronology; nếu nghiệp vụ cần lịch Nhật, Phật lịch hoặc hệ lịch khác, cần đánh giá rõ chronology và phiên bản API. Không giả định chỉ đổi ngôn ngữ là đổi hệ lịch.

## 9. Parsing: cùng formatter có thể parse nhưng phải đủ trường

`DateTimeFormatter` dùng cho cả **format** và **parse**, nhưng có vài giới hạn:

- `yMd` yêu cầu một ngày có năm/tháng/ngày và có thể dùng để parse thành `LocalDate` khi chuỗi phù hợp pattern đã được giải quyết.
- `yMMM` không chứa ngày trong tháng. Nếu dùng `LocalDate.parse(text, formatter yMMM)`, parser có thể thiếu trường `day-of-month` để xây dựng ngày đầy đủ. Dùng `YearMonth.parse(...)` khi mục đích là tháng/năm và pattern thích hợp.
- Pattern text được bản địa hóa, ví dụ tên tháng, phụ thuộc locale. Parse chuỗi được hiển thị bằng locale khác có thể thất bại.
- Chế độ giải quyết mặc định của formatter là `ResolverStyle.SMART` theo hợp đồng API. Với input cần xác minh nghiêm ngặt, đánh giá `withResolverStyle(ResolverStyle.STRICT)` cùng việc lựa chọn trường năm/kỷ nguyên và yêu cầu nghiệp vụ.
- Localized pattern có thể thay đổi giữa phiên bản dữ liệu locale; vì vậy không nên dùng nó làm khuôn nhập liệu hoặc biểu diễn dữ liệu lâu dài mà các hệ thống khác phải parse không đổi.

Đoạn minh họa:

~~~java
DateTimeFormatter f = DateTimeFormatter
        .ofLocalizedPattern("yMd")
        .withLocale(Locale.US);

LocalDate date = LocalDate.parse("6/16/2020", f);
~~~

Trong ứng dụng thực tế, cần xử lý `DateTimeParseException` và thử với dữ liệu locale của JDK mà ứng dụng triển khai. Dấu `/` chỉ là ví dụ kết quả của một runtime, không phải ký hiệu bắt buộc của requested template.

Đừng dùng định dạng bản địa hóa làm khóa cơ sở dữ liệu; lưu `LocalDate`, `Instant`, `OffsetDateTime` hoặc giá trị chuẩn tương ứng, rồi định dạng ở rìa giao diện.

## 10. Nếu sản phẩm còn chạy Java 17 thì sao?

Đây là điểm cần kiểm tra **trước khi chọn kiến trúc**. `ofLocalizedPattern` **không có trong Java SE 17**. Một mã nguồn chứa lời gọi phương thức này sẽ **không biên dịch được** nếu target Java 17, dù bạn đã cài JDK mới trên máy phát triển nhưng dùng `javac --release 17`.

Các giải pháp có thể sử dụng trong Java 17:

### A. Dùng định dạng theo FormatStyle nếu đủ yêu cầu

~~~java
DateTimeFormatter fullDate = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.MEDIUM)
        .withLocale(Locale.forLanguageTag("vi-VN"));
~~~

Đây là đoạn minh họa dùng `DateTimeFormatter`, `FormatStyle`, `Locale` có sẵn từ trước Java 19. Giải pháp phù hợp khi chỉ cần style cho ngày/giờ, **không cần yêu cầu tập trường tùy ý**.

### B. Dùng ofPattern nếu thứ tự và dấu phân cách được quyết định rõ

~~~java
DateTimeFormatter fixed = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.forLanguageTag("vi-VN"));
~~~

Đây là pattern cụ thể, dễ kiểm soát; **không** phải thay thế tương đương với `ofLocalizedPattern("yMd")` đa locale. Nếu dùng `ofPattern` cho từng thị trường, phải quản lý pattern cho từng locale và kiểm thử với người bản ngữ.

### C. Sử dụng thư viện quốc tế hóa có hỗ trợ skeleton/template

Nếu Java 17 phải hiển thị **các tập trường linh hoạt theo nhiều locale**, một thư viện sử dụng dữ liệu Unicode CLDR/LDML có API skeleton phù hợp (ví dụ hệ sinh thái ICU4J) có thể là hướng giải quyết. Thư viện ngoài không nằm trong Java Core; phải chọn phiên bản tương thích, kiểm tra license và API, đồng thời **không** xem skeleton của thư viện là tự động giống hoàn toàn `ofLocalizedPattern` của JDK mới.

### D. Nâng runtime tối thiểu lên Java 19+ khi có thể

Nếu sản phẩm có thể nâng Java, `ofLocalizedPattern` là một API trực tiếp cho requested template. Vẫn phải thử nghiệm trên JDK thực tế, bởi thuật toán và dữ liệu mẫu locale có thể được cập nhật theo bản phát hành.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi `ofLocalizedPattern` trên Java 17 | Lỗi biên dịch do không tồn tại API | Yêu cầu Java 19+ hoặc dùng phương án tương thích |
| Truyền `"dd/MM/yyyy"` vào `ofLocalizedPattern` | `IllegalArgumentException` | Dùng `ofPattern` khi cần dấu phân cách cố định |
| Truyền `"dMy"` thay vì `"yMd"` | Sai thứ tự canonical template | Sắp ký hiệu theo thứ tự chuẩn |
| Cho rằng requested template là output pattern | Kỳ vọng sai thứ tự, độ dài hoặc separator | Xem template là yêu cầu trường, kiểm thử output theo locale |
| Không truyền locale tường minh | Kết quả phụ thuộc FORMAT locale mặc định máy chủ | Dùng `withLocale(locale)` |
| Mong `yMMM` tạo đủ ngày/tháng/năm | Thiếu day-of-month | Thêm trường `d` nếu cần ngày |
| Format `LocalDate` bằng `Hm` | Không có dữ liệu giờ/phút | Dùng `LocalTime`/`LocalDateTime` |
| Format timezone từ `LocalDateTime` mà không có zone | Không có timezone để hiển thị | Chuyển thành `ZonedDateTime` đúng vùng |
| Dùng localized text làm dữ liệu trao đổi máy | Kết quả biến theo locale/CLDR | Dùng ISO hoặc hợp đồng machine-readable |
| Trộn `Locale` với `ZoneId` | Ngày/giờ thực tế sai vùng | Chọn múi giờ riêng |
| Dựa vào một bản output của JDK để kết luận mọi runtime | Regression khi nâng dữ liệu locale | Có test nhiều locale, kiểm tra nâng cấp |
| Cho rằng `withLocale` và `localizedBy` luôn đồng nghĩa | Có thể bỏ qua calendar/numbering extensions | Chọn đúng API theo nhu cầu |

## 12. Ma trận kiểm thử thực tế

Để triển khai sản phẩm, không chỉ thử `Locale.US`. Hãy tạo test theo:

| Trục kiểm thử | Kịch bản |
| --- | --- |
| Runtime | Java 19+, JDK đang triển khai, provider/dữ liệu locale thực tế |
| Locale | `en-US`, `en-GB`, `vi-VN`, `fr-FR`, các locale hỗ trợ thật |
| Template | `yMd`, `yMMM`, `yMMMd`, `Hm`, `jm`, mẫu có zone nếu cần |
| Temporal type | `LocalDate`, `LocalTime`, `LocalDateTime`, `ZonedDateTime` |
| Dữ liệu biên | Ngày cuối tháng, năm nhuận, nửa đêm, 12:00, timezone/DST |
| Dữ liệu lỗi | Template sai thứ tự, literal không được phép, thiếu trường thời gian |
| Khả năng tương thích | `javac --release 19`, so với `--release 17` |
| UI | Chuỗi dài/ngắn, khoảng trắng đặc biệt, tên tháng và thứ tự trường |
| Serialization | Không dùng localized text thay kiểu dữ liệu ngày chuẩn |

Khi viết assertion, phân biệt **bất biến nghiệp vụ** (cần có những trường nào, lỗi gì phải xảy ra) và **kết quả trình bày do CLDR quyết định** (có thể đổi khi nâng JDK). Snapshot test trên các chuỗi địa phương hóa có ích, nhưng khi JDK/CLDR thay đổi phải được xem xét như thay đổi dữ liệu ngôn ngữ, không tự động sửa snapshot rồi coi là luôn đúng.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Cần hiển thị tháng/năm không có ngày, để mỗi locale quyết định cách sắp xếp. Nên chọn API và template nào nếu runtime là Java 21?

**Đáp án:** `DateTimeFormatter.ofLocalizedPattern("yMMM").withLocale(locale)` là lựa chọn thích hợp; dữ liệu ngày đưa vào có thể là `LocalDate` hoặc `YearMonth` nếu formatter cần đủ trường được yêu cầu. Vẫn nên kiểm thử output thực tế.

**Câu 2.** Vì sao `ofLocalizedPattern("yMd")` không đồng nghĩa `ofPattern("yMd")`?

**Đáp án:** `ofPattern` xem các ký hiệu là một **chuỗi pattern in theo thứ tự đã viết**; `ofLocalizedPattern` dùng chúng làm **requested template** để tra kiểu định dạng gần nhất theo locale.

**Câu 3.** Có dùng `ofLocalizedPattern("yyyy-MM-dd")` để xuất ngày theo ISO cố định được không?

**Đáp án:** Không. Dấu `-` không hợp lệ trong template. Hãy dùng `DateTimeFormatter.ISO_LOCAL_DATE` (hoặc pattern cố định nếu giao thức đặc biệt yêu cầu).

**Câu 4.** Vì sao `ofLocalizedPattern("yMMMd")` có thể tạo thứ tự tháng/ngày khác nhau giữa `Locale.US` và `Locale.UK`?

**Đáp án:** Requested template mô tả trường cần có, trong khi locale quyết định mẫu gần nhất gồm thứ tự, tên tháng và dấu phân cách. Thứ tự trong template phải canonical để parser chấp nhận, nhưng không buộc thứ tự hiển thị.

**Câu 5.** Nếu một formatter yêu cầu giờ `Hm` nhưng input là `LocalDate`, lỗi là do locale hay do input?

**Đáp án:** Do input không chứa trường giờ/phút. Cần cung cấp `LocalTime`, `LocalDateTime` hoặc `ZonedDateTime` phù hợp.

**Bài tập thực hành:** Tạo ba formatter cho `yMMM`, `yMMMd` và `jm`, áp dụng cho `en-US`, `en-GB`, `vi-VN`. So sánh tập trường mong muốn, thứ tự hiển thị, dấu phân cách, chu kỳ 12/24 giờ và độ dài chuỗi. Thử các trường hợp lỗi `"dMy"`, `"yyyy-MM-dd"`, và format thời gian bằng `LocalDate`. Cuối cùng, viết một test kiểm tra mã nguồn không phụ thuộc API Java 19 khi target của dự án vẫn là Java 17.

## 14. Tài liệu chính thức

- [DateTimeFormatter — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/time/format/DateTimeFormatter.html): `ofLocalizedPattern(String)`, requested template, cú pháp, `withLocale`, `ofPattern` và ghi chú **Since: 19**.
- [DateTimeFormatterBuilder — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html): `appendLocalized(String)` và các lựa chọn cấu trúc formatter.
- [DateTimeFormatter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): các API có sẵn cho runtime 17 như `ofPattern` và `ofLocalizedDate`.
- [Unicode LDML Dates](https://unicode.org/reports/tr35/tr35-dates.html): nền tảng các mẫu và skeleton ngày giờ theo locale.

**Ghi nhớ:** `ofLocalizedPattern("yMd")` nghĩa là “hãy hiển thị **năm, tháng, ngày** theo cách tự nhiên của locale”, không phải “in đúng các ký tự `yMd`”. Hãy chọn temporal type đủ trường, truyền locale tường minh, kiểm thử với dữ liệu locale của runtime và nhớ rằng API này **chỉ có từ Java 19**.
