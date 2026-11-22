# ofLocalizedDate, ofLocalizedTime và ofLocalizedDateTime

Khi hiển thị ngày, giờ hoặc cả ngày-giờ cho người dùng nhiều quốc gia, Java cung cấp ba factory quan trọng của `java.time.format.DateTimeFormatter`:

- `DateTimeFormatter.ofLocalizedDate(FormatStyle)` — tạo formatter **chỉ hiển thị ngày** theo locale.
- `DateTimeFormatter.ofLocalizedTime(FormatStyle)` — tạo formatter **chỉ hiển thị giờ** theo locale.
- `DateTimeFormatter.ofLocalizedDateTime(FormatStyle)` và `ofLocalizedDateTime(FormatStyle, FormatStyle)` — tạo formatter **hiển thị cả ngày lẫn giờ**.

Các factory này sử dụng các **mẫu định dạng được bản địa hóa** mà JDK/locale provider biết, thay vì bắt lập trình viên tự viết một chuỗi mẫu cố định như `"dd/MM/yyyy"` cho mọi người. Chúng thường được kết hợp với `withLocale(locale)` để xác định ngôn ngữ và quy ước hiển thị.

Tuy nhiên, **locale không phải múi giờ**. Việc chọn style và loại giá trị `LocalDate`, `LocalTime`, `LocalDateTime`, `ZonedDateTime`, hay `Instant` quyết định formatter có đủ dữ liệu để chạy hay không. Đặc biệt, một số style `LONG` và `FULL` có phần giờ mang tên vùng giờ hoặc offset, nên chúng không luôn format được `LocalTime` hay `LocalDateTime` thiếu múi giờ.

## 1. Nhìn tổng quan các API

| Factory | Cái được hiển thị | Ví dụ đối tượng phù hợp | Điều cần chú ý |
| --- | --- | --- | --- |
| `ofLocalizedDate(style)` | Ngày, tháng, năm; có thể có thứ trong tuần | `LocalDate` | Chỉ dựa trên các trường ngày; không yêu cầu giờ |
| `ofLocalizedTime(style)` | Giờ, phút, có thể có giây và vùng giờ | `LocalTime` với một số style; `ZonedDateTime` với style cần zone | `LONG`/`FULL` thường yêu cầu thông tin zone |
| `ofLocalizedDateTime(style)` | Ngày và giờ cùng một độ chi tiết | `LocalDateTime` với `SHORT`/`MEDIUM`; `ZonedDateTime` với style cần zone | Có thể thất bại nếu thiếu trường ngày/giờ/zone |
| `ofLocalizedDateTime(dateStyle, timeStyle)` | Ngày và giờ với hai style độc lập | `LocalDateTime` hoặc `ZonedDateTime` phù hợp | Ví dụ ngày `LONG`, giờ `SHORT` |

Các lời gọi này trả về `DateTimeFormatter` **immutable** và **thread-safe**. Bản thân factory không format ngay; nó tạo một đối tượng formatter, rồi ứng dụng gọi `formatter.format(temporal)` hoặc `temporal.format(formatter)` khi cần.

Các import thông dụng:

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.LocalDateTime;
import java.time.ZonedDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
~~~

Cả ba factory đều thuộc **Java Time API** (`java.time`), không phải `java.text.DateFormat` hoặc `SimpleDateFormat` của API ngày giờ cũ.

## 2. `FormatStyle` là gì?

`FormatStyle` có bốn giá trị:

| Style | Mục tiêu thể hiện | Đặc điểm thường gặp |
| --- | --- | --- |
| `FULL` | Đầy đủ cho người đọc | Ngày có thể ghi thứ; giờ có thể kèm tên vùng giờ |
| `LONG` | Dài nhưng không nhất thiết đầy đủ như FULL | Tháng có thể được viết bằng chữ; giờ có thể kèm vùng giờ |
| `MEDIUM` | Độ dài trung bình | Có thể gồm tháng dạng chữ và giây, tùy locale |
| `SHORT` | Ngắn gọn | Thường dùng số cho ngày/tháng/năm; giờ có thể không có giây |

**Đây không phải bốn chuỗi pattern cố định.** `FormatStyle.SHORT` là **yêu cầu về mức độ trình bày**, còn JDK chọn pattern cụ thể theo locale/provider và loại dữ liệu. Ví dụ cùng `SHORT` có thể đưa ra `5/6/24` ở `en-US` và `06.05.24` ở `de-DE`.

Không nên đồng nhất:
- `SHORT` = chắc chắn `dd/MM/yy`;
- `MEDIUM` = chắc chắn có giây;
- `LONG` = chắc chắn có tên đầy đủ của tháng với mọi locale;
- `FULL` = luôn format được bất kỳ `LocalDateTime` nào.

Đó chỉ là các trường hợp phổ biến trong dữ liệu locale cụ thể, không phải hợp đồng chuỗi đầu ra bất biến trên mọi JDK.

## 3. `ofLocalizedDate`: hiển thị ngày theo locale

Giả sử ứng dụng có một ngày lịch thuần túy: `LocalDate.of(2024, 5, 6)`. Nó biểu diễn **ngày 6 tháng 5 năm 2024**; không chứa giờ hay múi giờ.

Tạo tệp **`LocalizedDateDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedDateDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 5, 6);

        DateTimeFormatter usShort =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .withLocale(Locale.US);

        DateTimeFormatter deShort =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .withLocale(Locale.GERMANY);

        System.out.println(usShort.getLocale().toLanguageTag());
        System.out.println(deShort.getLocale().toLanguageTag());
        System.out.println(usShort.format(date));
        System.out.println(deShort.format(date));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac LocalizedDateDemo.java
java LocalizedDateDemo
~~~

Ví dụ đầu ra với JDK/locale data thông dụng:

~~~text
en-US
de-DE
5/6/24
06.05.24
~~~

Hai dòng đầu (`en-US`, `de-DE`) phản ánh locale được đặt **tường minh**. Hai dòng sau cho thấy **cùng một `LocalDate`** được hiển thị theo hai quy ước ngày khác nhau. Không có phép chuyển đổi múi giờ nào ở đây: dữ liệu là một ngày thuần túy.

Với `FormatStyle.FULL`, formatter có thể thêm tên thứ trong tuần. Ví dụ tiếng Anh Mỹ cho ngày trên thường là “Monday, May 6, 2024”. Không nên kiểm thử mọi locale bằng cách tìm cố định chuỗi “Monday”; tên ngày được bản địa hóa.

### Khi nào dùng?

- Ngày sinh, ngày phát hành, hạn nộp theo lịch.
- Ngày đăng ký hoặc ngày sự kiện được lưu thành `LocalDate`.
- Ngày không mang thời điểm cụ thể trên trục thời gian.

Nếu dữ liệu thực chất là **một timestamp**, cần quyết định múi giờ trước khi trích xuất ngày hiển thị cho người dùng; chỉ đổi locale không thể tự xác định ngày lịch ở nơi người đó sống.

## 4. `ofLocalizedTime`: hiển thị giờ theo locale

`LocalTime` biểu diễn giờ trong ngày mà **không chứa ngày và không chứa múi giờ**, ví dụ `15:04:05`. Khi dùng các style không yêu cầu zone, nó có thể được format trực tiếp.

Tạo tệp **`LocalizedTimeDemo.java`**:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedTimeDemo {
    public static void main(String[] args) {
        LocalTime time = LocalTime.of(15, 4, 5);

        DateTimeFormatter shortTime =
                DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)
                        .withLocale(Locale.US);

        DateTimeFormatter mediumTime =
                DateTimeFormatter.ofLocalizedTime(FormatStyle.MEDIUM)
                        .withLocale(Locale.US);

        System.out.println(shortTime.getLocale().toLanguageTag());
        System.out.println(time.equals(LocalTime.of(15, 4, 5)));
        System.out.println(shortTime.format(time));
        System.out.println(mediumTime.format(time));
    }
}
~~~

~~~bash
javac LocalizedTimeDemo.java
java LocalizedTimeDemo
~~~

Ví dụ đầu ra với locale data tiếng Anh Mỹ thông dụng:

~~~text
en-US
true
3:04 PM
3:04:05 PM
~~~

Trong hai dòng giờ, ký tự khoảng trắng trước “PM” **có thể là một dấu cách Unicode không ngắt**, không nhất thiết là dấu cách ASCII thông thường. Tên AM/PM, dấu phân cách, việc có giây hay không và biểu diễn 12/24 giờ đều chịu ảnh hưởng của locale/provider.

Không bắt buộc kết quả `SHORT` luôn bao gồm giây. Với `LocalTime.of(15, 4, 5)`, `SHORT` của một số locale bỏ phần `05`, trong khi `MEDIUM` thường giữ phần giây.

### Điều dễ nhầm: LONG/FULL và múi giờ

Dạng thời gian `LONG` và `FULL` **thường yêu cầu thông tin múi giờ**, ví dụ tên zone hoặc offset. `LocalTime` không mang thông tin đó, nên:

~~~java
DateTimeFormatter f =
        DateTimeFormatter.ofLocalizedTime(FormatStyle.FULL)
                .withLocale(Locale.US);

String text = f.format(LocalTime.of(15, 4, 5));
~~~

Đây là **snippet minh họa lỗi**, cần import thích hợp. Trên JDK dùng mẫu FULL có trường zone cho `Locale.US`, lời gọi cuối ném `DateTimeException` vì temporal không cung cấp dữ liệu cần thiết. Đừng diễn giải lỗi này là “locale Mỹ không hỗ trợ FULL”: vấn đề là **kiểu dữ liệu không có vùng giờ**.

Cách khắc phục thích hợp là cung cấp `ZonedDateTime` (hoặc temporal có zone/offset phù hợp), hay chủ động dùng style không đòi zone.

## 5. `ofLocalizedDateTime`: gộp ngày và giờ theo locale

`LocalDateTime` chứa cả ngày và giờ nhưng **vẫn không chứa múi giờ**. Vì vậy với các style thông dụng như `SHORT` hay `MEDIUM`, nó có thể đáp ứng dữ liệu cần thiết. Với style giờ yêu cầu zone, nó có thể không đủ.

Tạo **`LocalizedDateTimeDemo.java`**:

~~~java
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedDateTimeDemo {
    public static void main(String[] args) {
        LocalDateTime dateTime =
                LocalDateTime.of(2024, 5, 6, 15, 4, 5);

        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                        .withLocale(Locale.US);

        System.out.println(formatter.getLocale().toLanguageTag());
        System.out.println(formatter.format(dateTime));
    }
}
~~~

~~~bash
javac LocalizedDateTimeDemo.java
java LocalizedDateTimeDemo
~~~

Ví dụ đầu ra trên JDK dùng mẫu địa phương hóa phổ biến:

~~~text
en-US
5/6/24, 3:04 PM
~~~

`ofLocalizedDateTime(FormatStyle.SHORT)` chọn một tổ hợp kiểu ngày ngắn và giờ ngắn theo locale. Đây không nhất thiết là phép nối cứng `ofLocalizedDate(SHORT) + " " + ofLocalizedTime(SHORT)`: ký tự nối, dấu câu và thứ tự thành phần do dữ liệu định dạng của locale quyết định.

### Các loại `DateTimeFormatter` không tự bổ sung trường thiếu

- `ofLocalizedDate(SHORT)` chỉ cần trường ngày, nên `LocalDate` đủ.
- `ofLocalizedTime(SHORT)` thường cần giờ/phút, nên `LocalTime` đủ.
- `ofLocalizedDateTime(SHORT)` cần cả trường ngày và giờ, nên chỉ `LocalDate` hoặc chỉ `LocalTime` **không đủ**.
- Với `LONG`/`FULL` có tên/offset vùng giờ, `LocalDateTime` thiếu zone có thể thất bại.

Formatter không tự bịa ngày hiện tại khi đưa một `LocalTime` vào formatter ngày-giờ, và không tự bịa múi giờ mặc định cho mọi temporal thiếu zone.

## 6. Overload hai style: ngày dài, giờ ngắn

`ofLocalizedDateTime` có **hai overload** quan trọng:

~~~java
DateTimeFormatter a =
        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT);

DateTimeFormatter b =
        DateTimeFormatter.ofLocalizedDateTime(
                FormatStyle.LONG, FormatStyle.SHORT);
~~~

Đây là snippet cần import `DateTimeFormatter` và `FormatStyle`. Với overload thứ hai:

- Tham số **thứ nhất** `FormatStyle.LONG` là style của **ngày**.
- Tham số **thứ hai** `FormatStyle.SHORT` là style của **giờ**.
- Mẫu kết hợp cuối cùng vẫn tuân theo locale; không phải phép nối thủ công hai chuỗi.

Ví dụ runnable **`MixedStylesDemo.java`**:

~~~java
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class MixedStylesDemo {
    public static void main(String[] args) {
        LocalDateTime value =
                LocalDateTime.of(2024, 5, 6, 15, 4, 5);

        DateTimeFormatter fmt =
                DateTimeFormatter.ofLocalizedDateTime(
                        FormatStyle.LONG, FormatStyle.SHORT)
                        .withLocale(Locale.US);

        System.out.println(fmt.getLocale().toLanguageTag());
        System.out.println(fmt.format(value));
    }
}
~~~

~~~bash
javac MixedStylesDemo.java
java MixedStylesDemo
~~~

Ví dụ đầu ra theo mẫu locale Mỹ phổ biến:

~~~text
en-US
May 6, 2024, 3:04 PM
~~~

Lưu ý `LONG` ở đây áp dụng cho **phần ngày**, còn `SHORT` áp dụng cho phần giờ; với dữ liệu locale Mỹ phổ biến, phần giờ không yêu cầu tên zone. Đừng nghĩ cứ thấy chữ `LONG` là bắt buộc có `ZonedDateTime`: yêu cầu zone phụ thuộc **style của phần giờ và pattern kết quả**.

Nếu cần hai thành phần khác độ chi tiết, overload này rõ ràng và dễ bảo trì hơn việc tự dựng pattern nối ngày-giờ.

## 7. Chọn đúng kiểu dữ liệu thời gian

Một số lớp trong `java.time` có ý nghĩa khác nhau:

| Loại temporal | Mang ngày? | Mang giờ? | Mang zone/offset? | Khi nào dùng |
| --- | --- | --- | --- | --- |
| `LocalDate` | Có | Không | Không | Ngày lịch thuần túy |
| `LocalTime` | Không | Có | Không | Giờ trong ngày không gắn vị trí |
| `LocalDateTime` | Có | Có | Không | Giờ địa phương chưa gắn zone |
| `OffsetDateTime` | Có | Có | Có offset | Ngày-giờ có độ lệch UTC |
| `ZonedDateTime` | Có | Có | Có `ZoneId` và offset | Thời gian gắn vùng múi giờ |
| `Instant` | Thời điểm trên trục UTC | Thời điểm trên trục UTC | Không mang các trường ngày/giờ địa phương trực tiếp | Dấu thời gian tuyệt đối |

Cột “ngày/giờ” của `Instant` cần hiểu là **có thể suy ra ngày và giờ khi biết zone**, chứ không phải nó trực tiếp cung cấp đủ các trường lịch cho mọi localized formatter.

Một hệ thống xử lý thời điểm thực tế nên xác định:
1. Timestamp nguồn là gì (thường `Instant`).
2. Múi giờ hiển thị là gì (`ZoneId`).
3. Locale người đọc là gì (`Locale`).
4. Style mong muốn là gì (`FormatStyle`).

Sau đó mới tạo formatter và định dạng.

**Ví dụ điển hình:** hai người xem cùng một sự kiện xảy ra tại `Instant.parse("2024-05-06T23:00:00Z")` có thể thấy **hai ngày lịch khác nhau** vì zone khác nhau. Nhưng nếu họ chỉ khác locale mà cùng zone, ngày lịch sẽ giống nhau, chỉ cách trình bày thay đổi.

## 8. LONG/FULL của phần giờ: dùng `ZonedDateTime` khi cần

Tạo **`ZonedLocalizedDemo.java`**:

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class ZonedLocalizedDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime value = ZonedDateTime.of(
                2024, 5, 6, 15, 4, 5, 0, zone);

        DateTimeFormatter time =
                DateTimeFormatter.ofLocalizedTime(FormatStyle.FULL)
                        .withLocale(Locale.US);

        DateTimeFormatter dateTime =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.LONG)
                        .withLocale(Locale.US);

        System.out.println(value.getZone().getId());
        System.out.println(time.getLocale().toLanguageTag());
        System.out.println(time.format(value));
        System.out.println(dateTime.format(value));
    }
}
~~~

~~~bash
javac ZonedLocalizedDemo.java
java ZonedLocalizedDemo
~~~

Hai dòng đầu **ổn định theo mã tường minh**:

~~~text
Asia/Ho_Chi_Minh
en-US
~~~

Hai dòng sau chứa giờ và có thể chứa tên vùng giờ theo dữ liệu của JDK. Chẳng hạn `FULL` tiếng Anh Mỹ có thể hiển thị tên tương đương “Indochina Time”, còn `LONG` có thể hiển thị offset như `GMT+07:00`. **Không đưa ra một stdout cứng cho hai dòng localized này**, vì tên vùng giờ và khoảng trắng có thể thay đổi theo phiên bản runtime/CLDR.

### Vì sao `LocalDateTime` có thể không đủ?

`LocalDateTime.of(2024, 5, 6, 15, 4)` **không biết** giờ đó thuộc Hà Nội, Tokyo, Berlin hay New York. Không thể suy ra tên zone từ các trường ngày và giờ.

Do đó, với định dạng `FULL` có tên zone, JDK có thể báo lỗi `DateTimeException` vì thiếu dữ kiện, thay vì tự ý chọn `ZoneId.systemDefault()`. Ứng dụng cần gắn đúng zone có ý nghĩa nghiệp vụ.

Nếu đang làm việc với `Instant`, có thể đổi sang `ZonedDateTime` bằng `instant.atZone(zone)` trước khi format, hoặc cấp zone vào formatter bằng `withZone(zone)` khi temporal và kiểu định dạng hỗ trợ.

## 9. `Locale` khác với `ZoneId`

**Locale:** quyết định cách trình bày cho người đọc, ví dụ thứ tự ngày/tháng, chữ viết tên tháng, kiểu giờ 12/24, tên vùng giờ bằng ngôn ngữ nào.

**ZoneId:** quyết định cách một thời điểm UTC chuyển sang giờ địa phương, bao gồm lịch sử thay đổi offset và daylight saving time ở những vùng áp dụng.

| Cấu hình | Tác động | Không tự làm |
| --- | --- | --- |
| `withLocale(Locale.US)` | Dùng quy ước bản địa hóa tiếng Anh Mỹ | Không chuyển `Instant` sang giờ Mỹ |
| `withLocale(Locale.GERMANY)` | Dùng mẫu/ngôn ngữ hiển thị kiểu Đức | Không tự chọn múi giờ Berlin |
| `withZone(ZoneId.of("Asia/Tokyo"))` | Gắn zone override để format/parse khi thích hợp | Không tự đổi ngôn ngữ sang tiếng Nhật |
| `Locale.forLanguageTag("vi-VN")` | Đại diện tiếng Việt trong ngữ cảnh Việt Nam | Không đồng nghĩa `ZoneId.of("Asia/Ho_Chi_Minh")` |

Đặt `Locale.US` cùng `ZoneId.of("Asia/Ho_Chi_Minh")` là **hoàn toàn hợp lệ**: ví dụ hệ thống hiển thị thời gian ở Việt Nam cho người dùng đọc tiếng Anh Mỹ.

Không được suy ra zone bằng cách nối mã quốc gia thành một ID. Một quốc gia có thể có nhiều múi giờ, có thời gian mùa hè hoặc quy tắc lịch sử khác nhau. Hãy lưu/chọn `ZoneId` rõ ràng.

## 10. Ví dụ: format một `Instant` với zone và locale riêng

Tạo **`InstantPresentationDemo.java`**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class InstantPresentationDemo {
    public static void main(String[] args) {
        Instant event = Instant.parse("2024-05-06T08:04:05Z");

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                        .withLocale(Locale.US)
                        .withZone(zone);

        System.out.println(formatter.getLocale().toLanguageTag());
        System.out.println(formatter.getZone().getId());
        System.out.println(event.atZone(zone).getHour());
        System.out.println(formatter.format(event));
    }
}
~~~

~~~bash
javac InstantPresentationDemo.java
java InstantPresentationDemo
~~~

Ba dòng đầu có kết quả xác định:

~~~text
en-US
Asia/Ho_Chi_Minh
15
~~~

Dòng cuối là chuỗi ngày-giờ `SHORT` theo dữ liệu locale Mỹ (thường tương đương `5/6/24, 3:04 PM`, với khoảng trắng AM/PM có thể khác). Phần **15 giờ** đến từ việc chuyển thời điểm UTC vào `Asia/Ho_Chi_Minh`, không đến từ `Locale.US`.

`withZone` tạo **formatter mới**, không đổi formatter gốc. `withLocale` cũng tạo formatter mới. Điều này cho phép xây chuỗi cấu hình rõ ràng mà không sửa state chung:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                .withLocale(userLocale)
                .withZone(userZone);
~~~

Đây là **snippet**: `userLocale` và `userZone` cần được xác thực/khai báo từ ngữ cảnh người dùng, không phải biến có sẵn của JDK.

## 11. `withLocale` và mặc định lúc tạo formatter

Nếu không gọi `withLocale(...)`, factory localized lấy locale mặc định về định dạng từ môi trường tại thời điểm tạo. Đối với dịch vụ đa người dùng, phụ thuộc này dễ gây lỗi:

~~~java
DateTimeFormatter shared =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT);
~~~

Nếu `shared` được tạo khi mặc định là `en-US`, nó không tự biến thành formatter `vi-VN` khi một request khác cần tiếng Việt. `DateTimeFormatter` immutable; đã giữ cấu hình locale từ lúc tạo.

Thiết kế rõ ràng hơn:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(requestLocale);
~~~

Lựa chọn locale nên đến từ người dùng, cấu hình sản phẩm hoặc quy tắc fallback. Không gọi `Locale.setDefault(...)` cho từng request: đó là trạng thái chung của JVM, có thể gây lỗi khi nhiều luồng chạy đồng thời.

### Ví dụ kiểm tra locale được gắn, không phụ thuộc output text

Tạo **`FormatterLocaleDemo.java`**:

~~~java
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class FormatterLocaleDemo {
    public static void main(String[] args) {
        DateTimeFormatter original =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .withLocale(Locale.US);
        DateTimeFormatter german =
                original.withLocale(Locale.GERMANY);

        System.out.println(original.getLocale().toLanguageTag());
        System.out.println(german.getLocale().toLanguageTag());
        System.out.println(original == german);
    }
}
~~~

~~~bash
javac FormatterLocaleDemo.java
java FormatterLocaleDemo
~~~

Kết quả chính xác:

~~~text
en-US
de-DE
false
~~~

`withLocale` trả formatter được cấu hình mới, không sửa `original`. Vì vậy có thể cache formatter immutable theo locale/style/zone nếu hệ thống thật sự cần tối ưu hiệu năng.

## 12. Cách parse ngày giờ đã được bản địa hóa

`DateTimeFormatter` có thể làm chiều ngược lại: đưa **chuỗi theo format tương ứng** vào `LocalDate.parse(...)`, `LocalTime.parse(...)` hoặc `LocalDateTime.parse(...)`.

Để parse đáng tin, phải có **cùng locale, style và loại dữ liệu** tương thích. Ví dụ dùng `SHORT` tại `Locale.US`, đầu vào kiểu Đức có thể bị hiểu nhầm hoặc báo lỗi; ứng dụng không nên tự suy ra format từ một chuỗi không rõ nguồn.

Tạo **`LocalizedParsingDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedParsingDemo {
    public static void main(String[] args) {
        Locale locale = Locale.US;

        LocalDate date = LocalDate.of(2024, 5, 6);
        LocalTime time = LocalTime.of(15, 4, 5);
        LocalDateTime dateTime =
                LocalDateTime.of(2024, 5, 6, 15, 4);

        DateTimeFormatter dateFmt =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .withLocale(locale);
        DateTimeFormatter timeFmt =
                DateTimeFormatter.ofLocalizedTime(FormatStyle.MEDIUM)
                        .withLocale(locale);
        DateTimeFormatter dateTimeFmt =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                        .withLocale(locale);

        LocalDate parsedDate =
                LocalDate.parse(dateFmt.format(date), dateFmt);
        LocalTime parsedTime =
                LocalTime.parse(timeFmt.format(time), timeFmt);
        LocalDateTime parsedDateTime =
                LocalDateTime.parse(
                        dateTimeFmt.format(dateTime), dateTimeFmt);

        System.out.println(date.equals(parsedDate));
        System.out.println(time.equals(parsedTime));
        System.out.println(dateTime.equals(parsedDateTime));
    }
}
~~~

~~~bash
javac LocalizedParsingDemo.java
java LocalizedParsingDemo
~~~

Kết quả trên bộ mẫu locale Mỹ thông dụng:

~~~text
true
true
true
~~~

Ở đây:
- `dateFmt` giữ đủ các thành phần của ngày.
- `timeFmt` dùng `MEDIUM` để giữ đến giây cho `15:04:05`.
- `dateTimeFmt` dùng `SHORT` và dữ liệu nguồn có giây = 0 để tránh mất thông tin khi biểu diễn.

**Không phải mọi phép format → parse đều là round-trip đầy đủ**. Nếu style bỏ giây/nano hoặc vùng giờ, thông tin đã bị lược bỏ trong chuỗi. Ví dụ format `LocalTime.of(15,4,5)` bằng `SHORT` có thể bỏ phần `05`, nên parse lại không thể khôi phục chính xác thời điểm tới giây.

### Lỗi parse cần xử lý

`DateTimeParseException` có thể xảy ra khi chuỗi không đúng pattern/style/locale, hoặc dữ liệu ngày không hợp lệ theo quy tắc resolver. Với đầu vào từ người dùng, hãy bắt lỗi để báo nội dung rõ ràng thay vì để exception lan ra giao diện.

Không nên nhận diện locale chỉ bằng cách nhìn ký tự phân cách `/` hay `.`. Nhiều vùng có dạng giống nhau nhưng ý nghĩa thứ tự ngày/tháng khác nhau. Nếu người dùng nhập ngày thủ công, có thể công bố một định dạng đầu vào cố định hoặc dùng bộ chọn ngày có dữ liệu cấu trúc, rồi chỉ dùng localized formatter để **hiển thị**.

## 13. So sánh localized formatter với pattern tự viết

Hai cách tạo formatter:

~~~java
DateTimeFormatter localized =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(Locale.US);

DateTimeFormatter explicit =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.US);
~~~

Đây là snippet có import `DateTimeFormatter`, `FormatStyle`, `Locale`.

- `localized` xin mẫu phù hợp với mức `SHORT` của locale Mỹ: có thể chọn tháng trước ngày, dùng năm hai chữ số.
- `explicit` ép thứ tự ngày/tháng/năm và độ rộng tương ứng theo chính pattern `dd/MM/uuuu`, dù locale Mỹ thường không dùng thứ tự này.

`ofPattern` phù hợp khi **đặc tả nghiệp vụ yêu cầu một bố cục cụ thể**, ví dụ một biểu mẫu có quy định thống nhất. `ofLocalizedDate` phù hợp khi mục tiêu là **theo thói quen của người dùng/locale**.

### Đừng dùng localized formatter làm chuẩn giao tiếp máy

Với API, log máy, CSV tích hợp hoặc định dạng dữ liệu ổn định, nên dùng các formatter ISO hoặc một schema rõ ràng:

~~~java
String iso = LocalDate.of(2024, 5, 6).toString();
System.out.println(iso);
~~~

Kết quả:

~~~text
2024-05-06
~~~

`LocalDate.toString()` dùng ISO-8601, không thay đổi chỉ vì người dùng có locale khác. Còn localized format thích hợp cho màn hình báo cáo, thông báo hoặc tài liệu hướng tới con người.

## 14. Locale provider, dữ liệu mẫu và tính ổn định của output

Các hàm `ofLocalized...` dựa trên dữ liệu locale mà runtime/provider cung cấp. Tên tháng, thứ, mẫu AM/PM, khoảng trắng, cấu trúc ngày-giờ và tên múi giờ có thể đổi theo:

- Phiên bản JDK/CLDR hoặc locale service provider.
- Locale cụ thể và các Unicode locale extensions liên quan.
- Cấu hình formatter được gắn (zone, chronology, decimal style trong những trường hợp thích hợp).
- Dữ liệu time zone của runtime khi có chuyển đổi thời điểm.

Vì vậy một snapshot test so sánh chuỗi localized từng ký tự trên mọi hệ thống có thể dễ hỏng. Ví dụ:
- Dấu cách thường `U+0020`,
- khoảng trắng không ngắt `U+00A0`,
- khoảng trắng hẹp không ngắt `U+202F`,

trông gần giống nhau nhưng khác mã Unicode. Khoảng trắng trước “PM” là tình huống thường gặp.

Nếu sản phẩm yêu cầu output cực kỳ ổn định, hãy cố định môi trường triển khai/JDK/provider khi kiểm thử, hoặc dùng pattern/khuôn dữ liệu tự định nghĩa khi phù hợp. Nếu mục tiêu là hiển thị theo văn hóa địa phương, đừng hardcode ký tự chỉ vì một phiên bản JDK hiện tại tạo chuỗi ấy.

**Lưu ý:** `getLocale()` cho biết formatter đang dùng locale nào; nó không bảo đảm toàn bộ dữ liệu locale được sao chép vào đối tượng khi khởi tạo. Runtime có thể cache/tra cứu chi tiết theo cơ chế triển khai, nhưng một formatter đã chọn locale không tự theo default mới ở mỗi lần format.

## 15. Khi nào dùng từng factory?

Một số tình huống:

| Nhu cầu | Factory gợi ý | Temporal phù hợp |
| --- | --- | --- |
| “Hạn nộp: ngày 6/5” theo locale người đọc | `ofLocalizedDate(SHORT)` | `LocalDate` |
| “Ngày sinh” dạng đầy đủ | `ofLocalizedDate(FULL)` | `LocalDate` |
| “Giờ mở cửa: 15:30” theo locale | `ofLocalizedTime(SHORT)` | `LocalTime` |
| “Bắt đầu lúc 15:04:05” và cần giây | `ofLocalizedTime(MEDIUM)` (kiểm thử locale) | `LocalTime` |
| Lịch hẹn gồm ngày và giờ ngắn | `ofLocalizedDateTime(SHORT)` | `LocalDateTime` hoặc `ZonedDateTime` |
| Báo cáo ngày dài, giờ ngắn | `ofLocalizedDateTime(LONG, SHORT)` | `LocalDateTime` |
| Sự kiện có ngày/giờ và tên vùng giờ | `ofLocalizedDateTime(FULL)` | `ZonedDateTime` |
| Timestamp UTC hiển thị theo người dùng | `ofLocalizedDateTime(style).withLocale(...).withZone(...)` | `Instant` và `ZoneId` |

Nếu chỉ có `LocalTime` nhưng yêu cầu hiển thị **zone đầy đủ**, phải làm rõ nguồn zone và có thể cả ngày cụ thể; offset của một vùng có thể phụ thuộc ngày do lịch sử hoặc quy tắc DST. Đừng bịa một ngày/zone khi dữ liệu chưa cung cấp.

## 16. Thread safety, cache và ứng dụng nhiều người dùng

`DateTimeFormatter` immutable và thread-safe, nên có thể chia sẻ **một instance đã cấu hình đầy đủ** giữa các luồng. Nhưng một formatter duy nhất có locale `en-US` không trở thành formatter đa locale chỉ vì nó thread-safe.

Ví dụ nếu cache theo locale và style:

~~~java
record FormatterKey(Locale locale, FormatStyle style) {}

Map<FormatterKey, DateTimeFormatter> cache =
        new ConcurrentHashMap<>();

DateTimeFormatter formatter = cache.computeIfAbsent(
        new FormatterKey(locale, FormatStyle.SHORT),
        key -> DateTimeFormatter.ofLocalizedDate(key.style())
                .withLocale(key.locale()));
~~~

Đây là **snippet trong một method**, không phải chương trình độc lập. Cần import `java.util.Locale`, `java.util.Map`, `java.util.concurrent.ConcurrentHashMap`, `java.time.format.FormatStyle` và `java.time.format.DateTimeFormatter`; biến `locale` là locale đã xác thực.

Key này đủ cho trường hợp **chỉ cache formatter ngày** theo style và locale. Nếu cache cả ngày-giờ kèm zone, cần bổ sung zone vào key khi zone được gắn vào formatter, cũng như các tùy chọn khác ảnh hưởng cấu hình.

Không dùng `Locale.setDefault(...)` ở từng request. Locale mặc định là trạng thái chia sẻ toàn JVM; việc thay đổi nó có thể tạo race khi nhiều luồng đồng thời tạo formatter. Tốt hơn là lưu locale hiệu lực theo request và truyền `withLocale(...)` rõ ràng.

Với tác vụ async/thread pool, nếu framework có request locale context thì phải hiểu cách truyền ngữ cảnh qua luồng; không giả định nó tự đi theo nhiệm vụ trong mọi cơ chế thực thi.

## 17. Ví dụ service thực tế: định dạng từ dữ liệu có ngữ cảnh

Tạo tệp **`LocalizedPresentationService.java`**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedPresentationService {
    public static String date(LocalDate value, Locale locale) {
        return DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(locale)
                .format(value);
    }

    public static String event(
            Instant instant, Locale locale, ZoneId zone) {
        return DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                .withLocale(locale)
                .withZone(zone)
                .format(instant);
    }

    public static void main(String[] args) {
        Locale language = Locale.US;
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDate date = LocalDate.of(2024, 5, 6);
        Instant event = Instant.parse("2024-05-06T08:04:05Z");

        String localizedDate = date(date, language);
        String localizedEvent = event(event, language, zone);

        System.out.println(localizedDate.isBlank());
        System.out.println(localizedEvent.isBlank());
        System.out.println(event.atZone(zone).getHour());
    }
}
~~~

~~~bash
javac LocalizedPresentationService.java
java LocalizedPresentationService
~~~

Kết quả chính xác và không phụ thuộc cách viết tên tháng:

~~~text
false
false
15
~~~

Ví dụ cố ý không cố định chuỗi localized trong stdout; điều cần kiểm chứng là cả hai formatter tạo được chuỗi không rỗng và sự kiện được chuyển đúng sang 15 giờ tại zone chỉ định.

**Hợp đồng của service:**
- `date(...)` chỉ nhận `LocalDate` nên không liên quan múi giờ.
- `event(...)` nhận `Instant` và `ZoneId` rõ ràng; việc format ngày-giờ đã có ngữ cảnh.
- `Locale` đến từ người dùng/cấu hình sản phẩm, không đoán từ zone.
- Trong ứng dụng thực tế cần kiểm tra null, locale được hỗ trợ và lỗi cấu hình trước khi đưa vào helper.

## 18. Lỗi phổ biến và cách khắc phục

1. **Dùng `ofLocalizedDate` để định dạng cả giờ.** Factory chỉ dành cho phần ngày. Nếu cần cả hai, dùng `ofLocalizedDateTime`.
2. **Dùng `ofLocalizedTime` cho `LocalDate`.** `LocalDate` không có các trường giờ/phút mà time formatter cần.
3. **Dùng `ofLocalizedDateTime(SHORT)` với `LocalTime`.** Không có ngày; formatter không tự bịa phần còn thiếu.
4. **Dùng `FULL` hoặc `LONG` time với `LocalTime` rồi gặp `DateTimeException`.** Style có thể yêu cầu vùng giờ; cung cấp temporal và zone phù hợp hoặc chọn style khác.
5. **Coi `LocalDateTime` đã có time zone.** Nó chứa ngày và giờ địa phương nhưng không có `ZoneId` hoặc offset.
6. **Nghĩ `Locale.US` đồng nghĩa múi giờ Mỹ.** Locale quyết định cách hiển thị, không xác định nơi xảy ra sự kiện.
7. **Cố định “SHORT = dd/MM/yyyy”.** Mẫu `SHORT` do locale/provider chọn, có thể khác hoàn toàn.
8. **Dùng `ofPattern("dd/MM/yyyy")` rồi nghĩ nó tự đổi thứ tự ngày/tháng khi `withLocale`.** Pattern tùy chỉnh đã cố định thứ tự trường; locale chủ yếu ảnh hưởng văn bản/ký hiệu bản địa hóa.
9. **Parse chuỗi địa phương hóa bằng formatter locale khác.** Có thể sai nghĩa hoặc lỗi; dùng đúng locale và style.
10. **Mong round-trip giữ giây khi dùng `SHORT`.** Nếu formatter không in giây thì dữ liệu đã mất trong chuỗi.
11. **Dùng localized formatter cho giao tiếp máy giữa các dịch vụ.** Nên dùng ISO-8601 hoặc schema thống nhất thay vì dựa vào locale người dùng.
12. **Đổi `Locale.setDefault` cho mỗi request.** Trạng thái chung của JVM có thể gây nhiễm locale giữa người dùng.
13. **Hardcode khoảng trắng AM/PM trong test.** Một số locale/provider dùng narrow no-break space.
14. **Dùng chung formatter `en-US` cho mọi user vì nó thread-safe.** Chia sẻ an toàn không đồng nghĩa locale đã đúng.

## 19. Kiểm thử đúng cách

Hãy xây các bài kiểm thử theo từng lớp thông tin:

| Kiểm thử | Điều cần xác nhận |
| --- | --- |
| `ofLocalizedDate` với `LocalDate` | Format thành công; không yêu cầu giờ/zone |
| `ofLocalizedTime(SHORT)` với `LocalTime` | Format thành công theo locale/provider hỗ trợ |
| `ofLocalizedDateTime(SHORT)` với `LocalDateTime` | Có đủ trường ngày và giờ |
| `ofLocalizedDateTime(LONG, SHORT)` | Ngày dài + giờ ngắn theo mẫu locale |
| `FULL` time với `ZonedDateTime` | Có zone để diễn đạt tên/offset theo yêu cầu |
| `FULL` time với `LocalTime` | Xử lý lỗi thiếu zone theo pattern/runtime |
| Đổi `Locale.US` sang `Locale.GERMANY` | Locale formatter thay đổi; đầu ra tương ứng với quy tắc địa phương |
| Dùng `Instant` với `withZone` | Timestamp chuyển thành giờ địa phương chính xác |
| Parse bằng cùng locale/style | Kiểm tra round-trip chỉ với độ chính xác mà style giữ lại |
| Nâng JDK/locale provider | Kiểm tra những chuỗi quan trọng và ký tự Unicode |

Đối với test **mức dữ liệu**, khẳng định `formatter.getLocale()`, `formatter.getZone()`, `LocalDate` hay giờ của `ZonedDateTime` sẽ ổn định hơn so với assert một mẫu chữ dài phụ thuộc CLDR.

Đối với test **đầu ra hiển thị**, vẫn cần một số snapshot có kiểm soát để phát hiện thay đổi không mong muốn, nhưng ghi rõ runtime/provider và xử lý khác biệt Unicode có chủ đích.

## 20. Bài tập có đáp án

**Câu 1.** Muốn hiển thị ngày sinh theo locale, không cần giờ, dùng factory nào?

**Đáp án:** `DateTimeFormatter.ofLocalizedDate(style).withLocale(locale)` với dữ liệu `LocalDate`.

**Câu 2.** Muốn hiển thị giờ mở cửa `15:30` theo ngôn ngữ người đọc, dữ liệu `LocalTime`, nên bắt đầu với gì?

**Đáp án:** `ofLocalizedTime(FormatStyle.SHORT).withLocale(locale)`; không mặc định chọn `FULL` khi không có zone.

**Câu 3.** `ofLocalizedDateTime(FormatStyle.LONG, FormatStyle.SHORT)` có hai tham số để làm gì?

**Đáp án:** Tham số đầu chọn style của **ngày**, tham số sau chọn style của **giờ**.

**Câu 4.** Vì sao `ofLocalizedDateTime(FormatStyle.FULL).format(LocalDateTime.now())` có thể lỗi?

**Đáp án:** Mẫu `FULL` của phần giờ có thể yêu cầu thông tin zone mà `LocalDateTime` không cung cấp.

**Câu 5.** Đổi `withLocale(Locale.JAPAN)` có làm thời điểm UTC chuyển sang giờ Nhật không?

**Đáp án:** Không. Cần zone tương ứng, ví dụ `ZoneId.of("Asia/Tokyo")`, khi chuyển `Instant` thành giờ địa phương.

**Câu 6.** Tại sao dùng `SHORT` format `LocalTime.of(15,4,5)` rồi parse lại có thể không giữ được giây?

**Đáp án:** Một số mẫu `SHORT` chỉ in giờ và phút, nên thông tin về giây không nằm trong chuỗi.

**Câu 7.** Khi nào nên dùng `ISO_LOCAL_DATE` hoặc `LocalDate.toString()` thay vì localized date?

**Đáp án:** Khi cần dữ liệu trao đổi ổn định giữa các chương trình, không phụ thuộc ngôn ngữ của người đọc.

**Câu 8.** `DateTimeFormatter` immutable giúp gì cho server?

**Đáp án:** Có thể dùng chung formatter đã cấu hình đúng giữa các luồng; tuy nhiên vẫn phải chọn locale, zone và style phù hợp cho từng ngữ cảnh người dùng.

## 21. Tổng kết

Có thể ghi nhớ ba factory bằng bảng ngắn:

~~~text
DateTimeFormatter.ofLocalizedDate(style)
    → Ngày

DateTimeFormatter.ofLocalizedTime(style)
    → Giờ

DateTimeFormatter.ofLocalizedDateTime(style)
DateTimeFormatter.ofLocalizedDateTime(dateStyle, timeStyle)
    → Ngày + giờ
~~~

**Quy trình dùng đúng trong một ứng dụng:**

1. Xác định **loại dữ liệu**: ngày, giờ, ngày-giờ địa phương hay timestamp.
2. Chọn **style** cần thiết: `SHORT`, `MEDIUM`, `LONG`, `FULL`.
3. Gắn **locale hiệu lực** bằng `withLocale(locale)`.
4. Nếu format timestamp/giờ có zone, cung cấp **`ZoneId`** qua temporal hoặc `withZone(...)`.
5. Kiểm tra mẫu đã chọn có đủ dữ liệu trường cần thiết hay không, nhất là với `FULL`/`LONG`.
6. Giữ dữ liệu trao đổi ở dạng cấu trúc/ISO; dùng localized formatter cho **giao diện con người**.
7. Kiểm thử tại các locale và JDK/provider được sản phẩm hỗ trợ.

**Ghi nhớ:** `ofLocalizedDate` chỉ cho ngày, `ofLocalizedTime` chỉ cho giờ, `ofLocalizedDateTime` cho cả hai. **Locale quyết định cách diễn đạt; zone quyết định giờ địa phương của timestamp; FormatStyle quyết định mức chi tiết mong muốn.** Ba khái niệm độc lập nhưng phải được phối hợp đúng.

Tài liệu Java SE 17: [DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html), [FormatStyle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/FormatStyle.html), [ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html).