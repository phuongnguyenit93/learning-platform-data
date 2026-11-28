# Ranh giới nửa đêm, buổi trưa và các khoảng ngày theo dữ liệu locale

Java 16 bổ sung ký hiệu mẫu `B` cho `DateTimeFormatter` để định dạng *day period* linh hoạt theo locale. Day period là cách ngôn ngữ chia thời gian trong ngày thành các khoảng như buổi sáng, buổi chiều, buổi tối hoặc ban đêm; một số locale còn có nhãn riêng cho đúng thời điểm nửa đêm hoặc buổi trưa.

`B` khác với `a`. `a` chỉ biểu diễn nửa ngày AM/PM, còn `B` dùng dữ liệu locale để chọn nhãn phù hợp với giờ địa phương. Ranh giới giữa các khoảng không phải một bộ giờ cố định áp dụng cho mọi ngôn ngữ. Vì vậy, hãy để locale quyết định văn bản hiển thị và kiểm tra các thời điểm sát ranh giới trên những locale mà ứng dụng hỗ trợ.

## 1. Day period là gì?

Một ngày có thể được diễn đạt thành nhiều khoảng thời gian bằng ngôn ngữ tự nhiên. Ví dụ, giao diện có thể hiển thị "buổi sáng", "buổi chiều", "buổi tối" hoặc "ban đêm". Một số ngôn ngữ có cách gọi riêng cho đúng 12 giờ trưa hoặc 12 giờ đêm.

Các khoảng này không chỉ là phép chia ngày thành hai nửa:

- AM/PM chia ngày thành hai phần theo quy ước đồng hồ 12 giờ.
- Day period có thể chia ngày thành nhiều khoảng có tên riêng.
- Tên gọi và ranh giới các khoảng phụ thuộc dữ liệu locale.
- Một số locale có nhãn riêng cho thời điểm cụ thể như noon hoặc midnight; locale khác có thể dùng nhãn của khoảng rộng hơn.

Ví dụ, cùng một thời điểm có thể được diễn đạt là buổi sáng trong một locale và có cách diễn đạt khác trong locale khác. Ứng dụng không nên tự giả định rằng "morning" luôn bắt đầu lúc 06:00 hoặc "evening" luôn bắt đầu lúc 18:00.

## 2. Phân biệt a và B trong DateTimeFormatter

Hai ký hiệu có mục đích khác nhau:

| Ký hiệu | Ý nghĩa | Ví dụ về dạng hiển thị |
|---|---|---|
| `a` | Nửa ngày AM/PM | AM, PM hoặc bản địa hóa tương ứng |
| `B` | Day period linh hoạt theo locale | Buổi sáng, buổi chiều, buổi tối, ban đêm, noon hoặc midnight nếu dữ liệu locale có nhãn đó |

Ví dụ định dạng cùng một thời điểm theo hai cách:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalTime time = LocalTime.of(13, 30);

DateTimeFormatter amPmFormatter =
    DateTimeFormatter.ofPattern("h:mm a", Locale.US);

DateTimeFormatter dayPeriodFormatter =
    DateTimeFormatter.ofPattern("h:mm B", Locale.US);

System.out.println(amPmFormatter.format(time));
System.out.println(dayPeriodFormatter.format(time));
```

Formatter thứ nhất hiển thị giờ theo đồng hồ 12 giờ cùng AM/PM. Formatter thứ hai dùng day period phù hợp với dữ liệu locale. Văn bản cụ thể do locale provider cung cấp, không nên hardcode kết quả tiếng Anh hoặc tiếng Việt vào logic nghiệp vụ.

Có thể dùng `B` độc lập nếu chỉ cần nhãn khoảng ngày:

```java
DateTimeFormatter periodOnly =
    DateTimeFormatter.ofPattern("B", Locale.forLanguageTag("vi-VN"));

String label = periodOnly.format(LocalTime.of(15, 0));
```

## 3. B là ký hiệu mẫu được hỗ trợ từ Java 16

Ký hiệu `B` được bổ sung trong Java 16 cho mẫu ngày giờ của `DateTimeFormatter`. Đây là API định dạng ngày giờ tiêu chuẩn, không phải tính năng preview.

Có thể sử dụng với `DateTimeFormatter.ofPattern`:

```java
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter formatter =
    DateTimeFormatter.ofPattern("h:mm B", Locale.forLanguageTag("vi-VN"));
```

Hoặc đặt mẫu trong `DateTimeFormatterBuilder`:

```java
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.util.Locale;

DateTimeFormatter formatter = new DateTimeFormatterBuilder()
    .appendPattern("h:mm B")
    .toFormatter(Locale.forLanguageTag("vi-VN"));
```

`DateTimeFormatter` là immutable và thread-safe, nên có thể tạo formatter dùng chung cho nhiều lần định dạng. Locale được gắn vào formatter để kết quả không phụ thuộc ngầm vào locale mặc định của máy chạy.

Nếu ứng dụng hỗ trợ JDK 16 trở lên, có thể dùng `B` trực tiếp. Nếu cần chạy trên JDK cũ hơn Java 16, mẫu chứa `B` không được hỗ trợ; cần chọn mẫu tương thích với phiên bản runtime mục tiêu.

## 4. Locale quyết định nhãn day period

Day period là dữ liệu ngôn ngữ và văn hóa. Cùng một giờ có thể có cách gọi khác nhau giữa các locale. Dữ liệu locale cũng quyết định cách diễn đạt và những khoảng nào được phân biệt.

Nên truyền locale rõ ràng:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;

List<Locale> locales = List.of(
    Locale.US,
    Locale.UK,
    Locale.forLanguageTag("vi-VN")
);

List<LocalTime> samples = List.of(
    LocalTime.of(7, 0),
    LocalTime.NOON,
    LocalTime.of(15, 0),
    LocalTime.of(20, 0),
    LocalTime.MIDNIGHT
);

for (Locale locale : locales) {
    DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("h:mm B", locale);

    System.out.println("Locale: " + locale.toLanguageTag());

    for (LocalTime time : samples) {
        System.out.printf("%s -> %s%n", time, formatter.format(time));
    }
}
```

Đoạn mã in cách mỗi locale diễn đạt cùng các thời điểm. Hãy chạy trên JDK mục tiêu để xem dữ liệu locale thực tế của runtime đó.

Không nên giả định locale `vi-VN` luôn trả về đúng một chuỗi cụ thể giữa mọi bản JDK. Dữ liệu CLDR và locale provider có thể được cập nhật theo phiên bản JDK. Nếu đầu ra là nội dung giao diện, hãy kiểm tra lại khi nâng cấp runtime.

## 5. Ranh giới nửa đêm và buổi trưa

Nửa đêm và buổi trưa là các thời điểm dễ gây nhầm lẫn khi định dạng giờ:

- `LocalTime.MIDNIGHT` là 00:00, thời điểm bắt đầu ngày theo đồng hồ địa phương.
- `LocalTime.NOON` là 12:00, thời điểm giữa ngày theo đồng hồ địa phương.
- 23:59 thuộc ngày trước đó; 00:00 đã sang ngày tiếp theo.
- 11:59 là trước buổi trưa; 12:00 là đúng buổi trưa; 12:01 là sau buổi trưa.

Mẫu `B` có thể hiển thị nhãn riêng cho đúng nửa đêm hoặc buổi trưa nếu dữ liệu locale có quy tắc tương ứng. Không phải locale nào cũng phải có nhãn riêng, vì vậy kết quả có thể là tên khoảng ngày rộng hơn.

Ví dụ kiểm tra các thời điểm ngay trước, đúng lúc và ngay sau hai mốc:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;

DateTimeFormatter formatter =
    DateTimeFormatter.ofPattern("HH:mm | h:mm B", Locale.US);

List<LocalTime> boundaryTimes = List.of(
    LocalTime.of(23, 59),
    LocalTime.MIDNIGHT,
    LocalTime.of(0, 1),
    LocalTime.of(11, 59),
    LocalTime.NOON,
    LocalTime.of(12, 1)
);

for (LocalTime time : boundaryTimes) {
    System.out.println(formatter.format(time));
}
```

Các thời điểm trên là những điểm cần kiểm tra, không phải tuyên bố rằng mọi locale đổi nhãn đúng tại các giờ đó. Đặc biệt, đừng lấy quy tắc của một locale rồi áp dụng cho toàn bộ người dùng.

## 6. Ranh giới của các khoảng buổi sáng, chiều, tối và đêm

Ngoài hai mốc nửa đêm và buổi trưa, locale có thể chia ngày thành các khoảng nhỏ hơn. Ví dụ thường gặp là morning, afternoon, evening và night. Một số locale phân biệt thêm các khoảng như sáng sớm hoặc cuối buổi chiều.

Không có một bảng giờ phổ quát để ánh xạ:

- Morning = 06:00–11:59.
- Afternoon = 12:00–17:59.
- Evening = 18:00–21:59.
- Night = 22:00–05:59.

Đây chỉ có thể là quy ước riêng của một ứng dụng nếu nghiệp vụ tự định nghĩa; không phải hợp đồng chung của `DateTimeFormatter`. Khi dùng `B`, ranh giới được lấy từ dữ liệu locale của formatter.

Nếu ứng dụng cần xác định một sự kiện thuộc ca làm việc, ca trực hoặc khoảng nghiệp vụ cụ thể, hãy định nghĩa các khoảng đó bằng quy tắc nghiệp vụ riêng. Không dùng văn bản day period để thay thế logic phân loại.

## 7. Quan sát các nhãn mà locale thực sự sử dụng

Có thể định dạng từng phút trong ngày với mẫu chỉ chứa `B` để quan sát những lúc nhãn hiển thị thay đổi:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Objects;

Locale locale = Locale.forLanguageTag("vi-VN");
DateTimeFormatter periodFormatter =
    DateTimeFormatter.ofPattern("B", locale);

String previousLabel = null;

for (int minute = 0; minute < 24 * 60; minute++) {
    LocalTime time = LocalTime.of(minute / 60, minute % 60);
    String label = periodFormatter.format(time);

    if (!Objects.equals(previousLabel, label)) {
        System.out.printf("%s -> %s%n", time, label);
        previousLabel = label;
    }
}
```

Đoạn mã quét theo độ phân giải một phút và in khi nhãn hiển thị thay đổi. Đây là cách khảo sát hành vi formatter của một locale trên JDK hiện tại.

Kết quả chỉ cho thấy những thời điểm mà chuỗi định dạng thay đổi ở độ phân giải đã chọn. Nó không phải API truy vấn chính thức toàn bộ quy tắc CLDR, cũng không chứng minh ranh giới nội bộ nếu hai khoảng có cùng nhãn hiển thị. Nếu nghiệp vụ cần ranh giới chính xác, hãy định nghĩa chúng trong mô hình nghiệp vụ thay vì suy ra từ chuỗi định dạng.

Có thể lặp lại với các locale khác để so sánh:

```java
for (Locale locale : List.of(
        Locale.US,
        Locale.UK,
        Locale.forLanguageTag("vi-VN"))) {
    DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("B", locale);

    System.out.println("Locale: " + locale.toLanguageTag());

    String previous = null;

    for (int minute = 0; minute < 24 * 60; minute++) {
        LocalTime time = LocalTime.of(minute / 60, minute % 60);
        String current = formatter.format(time);

        if (!Objects.equals(previous, current)) {
            System.out.printf("%s -> %s%n", time, current);
            previous = current;
        }
    }
}
```

Đoạn mã thứ hai tái sử dụng import `java.util.List`, `java.util.Locale`, `java.time.LocalTime`, `java.time.format.DateTimeFormatter` và `java.util.Objects` từ ví dụ trước.

## 8. Phân biệt thời gian địa phương với Instant và múi giờ

Day period được chọn dựa trên giờ địa phương mà formatter nhìn thấy. Một `Instant` chỉ là một thời điểm trên timeline UTC; nó không tự chứa múi giờ hoặc giờ địa phương.

Khi định dạng sự kiện từ `Instant`, hãy chuyển sang múi giờ đích trước:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

Instant event = Instant.parse("2026-11-27T17:30:00Z");

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime localEvent = event.atZone(zone);

DateTimeFormatter formatter = DateTimeFormatter
    .ofPattern("EEE, d MMM uuuu, h:mm B", Locale.forLanguageTag("vi-VN"));

System.out.println(formatter.format(localEvent));
```

Cùng một Instant có thể thuộc day period khác nhau ở hai múi giờ vì giờ trên đồng hồ địa phương khác nhau. Ví dụ, thời điểm buổi sáng ở một khu vực có thể vẫn là đêm ở khu vực khác.

Vì vậy:

- Chọn đúng `ZoneId` theo người xem hoặc địa điểm của sự kiện.
- Chuyển `Instant` thành `ZonedDateTime` trước khi định dạng.
- Dùng locale phù hợp với ngôn ngữ hiển thị.
- Không dùng giờ hệ thống mặc định nếu ứng dụng có múi giờ nghiệp vụ rõ ràng.

`LocalTime` chỉ chứa giờ và phút/giây, không có ngày hay múi giờ. Nó phù hợp để định dạng một giờ địa phương đã được xác định; nó không đủ thông tin để xác định một thời điểm toàn cầu.

## 9. Dùng B trong mẫu ngày giờ hoàn chỉnh

Có thể kết hợp `B` với các thành phần ngày, giờ và múi giờ khác:

```java
import java.time.ZonedDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

ZonedDateTime appointment = ZonedDateTime.of(
    2026, 11, 27,
    15, 30, 0, 0,
    ZoneId.of("Asia/Ho_Chi_Minh")
);

DateTimeFormatter formatter = DateTimeFormatter.ofPattern(
    "EEEE, d MMMM uuuu 'lúc' h:mm B",
    Locale.forLanguageTag("vi-VN")
);

String displayText = formatter.format(appointment);
```

Mẫu này kết hợp:

- `EEEE`: tên đầy đủ của thứ theo locale.
- `d MMMM uuuu`: ngày, tên tháng và năm.
- `'lúc'`: văn bản literal được đặt trong dấu nháy đơn.
- `h:mm`: giờ theo đồng hồ 12 giờ và phút.
- `B`: day period theo locale.

Có thể dùng `HH:mm` nếu giao diện cần giờ 24 giờ. Khi đó `B` có thể bổ sung ngữ cảnh ngôn ngữ, nhưng việc hiển thị cả giờ 24 giờ và day period có thể dư thừa tùy thiết kế.

## 10. B không thay thế dữ liệu giờ số

`B` tạo văn bản trình bày, không thay đổi thời điểm và không phải một kiểu dữ liệu để lưu trữ.

Ví dụ:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalTime appointmentTime = LocalTime.of(15, 30);

DateTimeFormatter numericFormatter =
    DateTimeFormatter.ofPattern("HH:mm", Locale.ROOT);

DateTimeFormatter displayFormatter =
    DateTimeFormatter.ofPattern("h:mm B", Locale.forLanguageTag("vi-VN"));

String canonicalTime = numericFormatter.format(appointmentTime);
String displayTime = displayFormatter.format(appointmentTime);
```

`canonicalTime` là dạng giờ số có thể dùng trong một giao thức hoặc định dạng trao đổi nếu hợp đồng dữ liệu quy định như vậy. `displayTime` dành cho giao diện người dùng.

Không lưu chuỗi như "in the afternoon" hoặc "buổi chiều" làm đại diện cho thời điểm chính xác. Một day period bao phủ một khoảng thời gian, không xác định duy nhất giờ và phút.

## 11. Parsing và round-trip

Định dạng và phân tích ngược là hai nhu cầu khác nhau. Chuỗi day period phụ thuộc locale và có thể biểu diễn một khoảng thay vì một thời điểm duy nhất.

Nếu cần nhận giờ chính xác từ người dùng, nên yêu cầu thành phần giờ số và dùng formatter có locale rõ ràng. Ví dụ, mẫu `h:mm a` chứa giờ, phút và AM/PM:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

Locale locale = Locale.US;

DateTimeFormatter inputFormatter = DateTimeFormatter
    .ofPattern("h:mm a", locale)
    .withResolverStyle(ResolverStyle.STRICT);

LocalTime parsedTime = LocalTime.parse("3:30 PM", inputFormatter);
```

`B` có thể tham gia parsing theo dữ liệu locale của JDK, nhưng không nên giả định mọi nhãn day period có thể khôi phục duy nhất một `LocalTime`. Nếu ứng dụng nhận chuỗi có `B`, hãy kiểm tra các trường hợp parse thực tế trên từng locale và JDK hỗ trợ, bao gồm đúng nửa đêm, buổi trưa và các khoảng ngày.

Đối với dữ liệu lưu trữ hoặc API, hãy ưu tiên định dạng số có hợp đồng rõ ràng như giờ 24 giờ, ngày giờ ISO hoặc timestamp có múi giờ. Dùng day period cho phần trình bày đã bản địa hóa.

## 12. Kiểm thử ranh giới theo locale

Không nên chỉ kiểm thử một thời điểm giữa buổi. Hãy kiểm tra các thời điểm sát ranh giới và các locale thực sự được ứng dụng hỗ trợ.

Một bộ thời điểm kiểm tra cơ bản:

```java
import java.time.LocalTime;
import java.util.List;

List<LocalTime> boundaryCases = List.of(
    LocalTime.of(0, 0),
    LocalTime.of(0, 1),
    LocalTime.of(5, 59),
    LocalTime.of(6, 0),
    LocalTime.of(11, 59),
    LocalTime.of(12, 0),
    LocalTime.of(12, 1),
    LocalTime.of(17, 59),
    LocalTime.of(18, 0),
    LocalTime.of(23, 59)
);
```

Các thời điểm 06:00 và 18:00 ở đây là điểm lấy mẫu để khảo sát, không phải ranh giới chuẩn của mọi locale.

Trong test:

1. Tạo formatter bằng locale cụ thể.
2. Định dạng tất cả thời điểm trong bộ kiểm tra.
3. Quan sát nhãn tại hai phía của nửa đêm và buổi trưa.
4. Kiểm tra các khoảng khác theo locale mà sản phẩm hỗ trợ.
5. Chạy lại sau khi nâng cấp JDK vì dữ liệu locale có thể được cập nhật.

Tránh kiểm thử bằng cách khẳng định một chuỗi tiếng Anh cố định cho tất cả locale. Nếu kiểm thử snapshot giao diện, hãy gắn snapshot với locale và môi trường JDK đã xác định. Nếu mục tiêu là kiểm tra logic nghiệp vụ, kiểm tra dữ liệu thời gian số và quy tắc miền riêng thay vì phụ thuộc vào nhãn bản địa hóa.

## 13. Những lỗi thường gặp

**Dùng `a` khi cần day period linh hoạt.** `a` chỉ biểu diễn AM/PM. Dùng `B` khi muốn nhãn khoảng ngày theo locale.

**Cho rằng mọi locale có cùng ranh giới buổi sáng và buổi chiều.** Các khoảng được lấy từ dữ liệu locale; không hardcode giờ bắt đầu/kết thúc chung cho mọi ngôn ngữ.

**Giả định 12:00 luôn được hiển thị bằng nhãn noon.** Locale có thể có nhãn riêng hoặc dùng tên khoảng rộng hơn. Kiểm tra output trên locale mục tiêu.

**Giả định 00:00 luôn được hiển thị bằng nhãn midnight.** Tương tự buổi trưa, nhãn riêng phụ thuộc dữ liệu locale.

**Dùng chuỗi day period để phân loại ca làm việc.** Nhãn hiển thị là dữ liệu trình bày. Hãy dùng quy tắc nghiệp vụ riêng cho ca làm, giờ mở cửa hoặc SLA.

**Định dạng Instant mà không chọn múi giờ.** Day period cần giờ địa phương. Chuyển Instant sang ZoneId phù hợp trước khi định dạng.

**Dùng locale mặc định ngầm định.** Kết quả có thể đổi theo môi trường máy. Truyền Locale rõ ràng cho formatter.

**Lưu nhãn day period làm dữ liệu thời gian chuẩn.** Nhãn không biểu diễn một thời điểm duy nhất và có thể đổi theo locale hoặc phiên bản dữ liệu.

**Giả định định dạng rồi parse lại luôn khôi phục chính xác thời gian.** Day period có thể biểu diễn một khoảng; dùng giờ số khi cần round-trip chính xác.

**Chỉ kiểm thử giữa khoảng.** Lỗi thường xuất hiện sát nửa đêm, buổi trưa hoặc lúc chuyển nhãn. Hãy kiểm tra thời điểm ngay trước, tại và sau mốc cần quan tâm.

## 14. Ghi nhớ

- `B` là ký hiệu day period linh hoạt được bổ sung trong Java 16.
- `a` biểu diễn AM/PM; `B` biểu diễn nhãn khoảng ngày theo locale.
- Locale provider quyết định văn bản và các khoảng ngày được thể hiện.
- Ranh giới buổi sáng, chiều, tối và đêm không phải một bộ giờ phổ quát.
- Nửa đêm là `LocalTime.MIDNIGHT`; buổi trưa là `LocalTime.NOON`, nhưng nhãn riêng phụ thuộc locale.
- Dùng `DateTimeFormatter.ofPattern("h:mm B", locale)` để định dạng day period.
- Chuyển `Instant` sang múi giờ địa phương trước khi định dạng.
- Không dùng nhãn `B` làm dữ liệu chuẩn hoặc logic phân loại nghiệp vụ.
- Khi cần parse chính xác, giữ thành phần giờ số và kiểm tra round-trip theo locale.
- Kiểm thử các thời điểm sát ranh giới và chạy lại sau khi nâng cấp JDK.

`DateTimeFormatter` với ký hiệu `B` giúp giao diện diễn đạt thời gian tự nhiên hơn theo locale. Khi hiểu rằng ranh giới và nhãn day period đến từ dữ liệu ngôn ngữ, ứng dụng có thể xử lý đúng nửa đêm, buổi trưa và các khoảng trong ngày mà không áp đặt một lịch chia giờ duy nhất cho mọi người dùng.

