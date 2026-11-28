# Day period và nhu cầu diễn đạt các khoảng trong ngày theo locale

> **Chương:** Định dạng day period  
> **Phạm vi:** Tìm hiểu cách Java 16 bổ sung ký hiệu `B` trong `DateTimeFormatter` để diễn đạt thời điểm bằng các khoảng trong ngày như buổi sáng, buổi chiều, buổi tối hoặc ban đêm. Nội dung tập trung vào dữ liệu locale, cách định dạng và phân tích chuỗi, cùng những giới hạn cần hiểu khi dùng trong ứng dụng hiện đại.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích day period là gì và vì sao AM/PM chưa đủ cho mọi ngôn ngữ.
2. Phân biệt ký hiệu `a` (AM/PM) với `B` (day period linh hoạt).
3. Dùng `DateTimeFormatter` để định dạng giờ theo locale.
4. Hiểu vì sao ranh giới buổi sáng, chiều, tối và đêm phụ thuộc locale.
5. Phân tích chuỗi có day period và nhận biết giới hạn khi chỉ có tên khoảng thời gian.
6. Thiết kế test ổn định mà không phụ thuộc cứng vào một bản dịch hoặc một bộ dữ liệu locale.

## 1. Day period là gì?

Day period là cách gọi một khoảng trong ngày bằng ngôn ngữ tự nhiên. Thay vì chỉ nói thời điểm thuộc AM hay PM, giao diện có thể diễn đạt:

- Buổi sáng.
- Buổi chiều.
- Buổi tối.
- Ban đêm.
- Những cách gọi đặc biệt như giữa trưa hoặc nửa đêm nếu locale hỗ trợ.

Hai thời điểm 09:00 và 15:00 đều có thể được phân loại bằng các khoảng trong ngày khác nhau. Cách gọi cụ thể phụ thuộc ngôn ngữ và quy ước của locale.

AM/PM chỉ chia ngày thành hai nửa theo mốc 12 giờ:

- AM: từ 00:00 đến trước 12:00.
- PM: từ 12:00 đến trước 24:00.

Hai nhãn này hữu ích với đồng hồ 12 giờ, nhưng không thể hiện sự khác biệt giữa buổi sáng, buổi chiều, buổi tối và ban đêm. Nhiều ngôn ngữ dùng các cách diễn đạt chi tiết hơn khi nói về một giờ cụ thể.

Ví dụ, một ứng dụng lịch có thể muốn hiển thị giờ họp theo cách tự nhiên với người dùng. Câu “3:30 PM” có thể phù hợp trong một số giao diện tiếng Anh, trong khi cách diễn đạt “3:30 in the afternoon” cung cấp ngữ cảnh rõ hơn. Với ngôn ngữ khác, cách chia khoảng và từ ngữ có thể khác.

## 2. Java 16 bổ sung day period trong `DateTimeFormatter`

Từ Java 16, `java.time.format.DateTimeFormatter` hỗ trợ ký hiệu mẫu **`B`** để định dạng day period. Đây là tính năng chính thức, không phải preview hoặc incubator.

Các ký hiệu liên quan:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `a` | AM/PM của ngày | `AM`, `PM` |
| `B` | Day period theo locale | `in the morning`, `in the afternoon` |
| `h` | Giờ theo đồng hồ 12 giờ, từ 1 đến 12 | `3` |
| `H` | Giờ trong ngày, từ 0 đến 23 | `15` |
| `m` | Phút trong giờ | `30` |

Khác biệt quan trọng:

- `a` luôn diễn đạt nửa ngày AM hoặc PM.
- `B` tra dữ liệu locale để chọn cách gọi khoảng thời gian phù hợp với giờ địa phương.
- `h` hoặc `H` biểu diễn con số giờ; `B` cung cấp nhãn bằng ngôn ngữ tự nhiên.

`B` được hỗ trợ trong `DateTimeFormatter` và `DateTimeFormatterBuilder`. Tài liệu Java SE 16 đã liệt kê `B` là pattern letter có ý nghĩa `period-of-day`; tài liệu JDK hiện đại vẫn giữ hỗ trợ này.

## 3. Nhu cầu diễn đạt khoảng trong ngày theo locale

Day period không phải một bảng giờ cố định dùng chung cho mọi ngôn ngữ. Bộ dữ liệu locale có thể xác định những khoảng như morning, afternoon, evening và night, cùng tên bản dịch tương ứng.

Ví dụ minh họa về ý nghĩa:

| Thời điểm | Cách diễn đạt có thể gặp |
| --- | --- |
| 08:00 | Buổi sáng / in the morning |
| 15:00 | Buổi chiều / in the afternoon |
| 19:00 | Buổi tối / in the evening |
| 23:00 | Ban đêm / at night |

Các hàng trên chỉ minh họa ý nghĩa. Không suy ra rằng 08:00 luôn là giờ bắt đầu buổi sáng, 15:00 luôn thuộc buổi chiều hoặc mọi locale đều có đủ bốn nhãn này.

### Vì sao không tự chia giờ bằng các điều kiện cố định?

Một cách làm đơn giản nhưng thiếu tính quốc tế hóa là:

```java
if (hour < 12) {
    return "Morning";
} else if (hour < 18) {
    return "Afternoon";
} else {
    return "Evening";
}
```

Logic này tự áp đặt ranh giới thời gian và ngôn ngữ. Khi đổi locale, các nhãn có thể không còn phù hợp; khi nghiệp vụ hoặc dữ liệu ngôn ngữ thay đổi, mã phải được sửa và kiểm thử lại.

Nếu mục tiêu là hiển thị giờ theo ngôn ngữ người dùng, hãy để `DateTimeFormatter` sử dụng dữ liệu locale. Nếu mục tiêu là phân loại ca làm việc, giờ mở cửa, lịch trực hoặc quy tắc nghiệp vụ, hãy định nghĩa các khoảng nghiệp vụ riêng; không dùng chuỗi day period để quyết định logic.

### Vai trò của CLDR

Java sử dụng dữ liệu locale để tra cách viết và quy tắc định dạng. CLDR (Common Locale Data Repository) của Unicode mô tả:

- Tên day period theo ngôn ngữ và kiểu trình bày.
- Các quy tắc xác định một giờ thuộc day period nào.
- Các khoảng linh hoạt như morning, afternoon, evening và night.
- Trường hợp locale không có dữ liệu day period linh hoạt thì có thể quay về cách phân chia AM/PM.

Vì dữ liệu được tổ chức theo locale, cùng một `LocalTime` có thể được diễn đạt khác nhau khi đổi locale. Bản dịch và ranh giới cũng có thể thay đổi khi JDK cập nhật dữ liệu locale.

## 4. Định dạng day period với `DateTimeFormatter`

Tạo formatter với pattern `B` và locale mong muốn:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class DayPeriodExample {
    public static void main(String[] args) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("h:mm B", Locale.US);

        System.out.println(formatter.format(LocalTime.of(9, 0)));
        System.out.println(formatter.format(LocalTime.of(15, 30)));
        System.out.println(formatter.format(LocalTime.of(20, 15)));
    }
}
```

Với locale tiếng Anh Mỹ, kết quả có thể được diễn đạt theo dạng:

```text
9:00 in the morning
3:30 in the afternoon
8:15 in the evening
```

Văn bản chính xác phụ thuộc dữ liệu locale của JDK đang chạy. Khi cần một chuỗi cố định trong tài liệu hoặc test snapshot, hãy ghi rõ JDK/vendor và dữ liệu locale được dùng.

### Chọn locale tường minh

Có thể sử dụng locale theo ngôn ngữ và khu vực:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale englishUS = Locale.US;

DateTimeFormatter viFormatter =
        DateTimeFormatter.ofPattern("h:mm B", vietnamese);
DateTimeFormatter enFormatter =
        DateTimeFormatter.ofPattern("h:mm B", englishUS);

LocalTime time = LocalTime.of(15, 30);

System.out.println(viFormatter.format(time));
System.out.println(enFormatter.format(time));
```

Đối với giao diện có tùy chọn ngôn ngữ, truyền locale người dùng đã chọn vào formatter. Không nên phụ thuộc ngầm vào locale mặc định của máy chủ vì locale của máy chủ có thể khác người dùng.

Ví dụ trên minh họa cách gọi API; không giả định chuỗi tiếng Việt cụ thể giống nhau giữa mọi bản dựng JDK. Hãy chạy trên JDK mục tiêu để xác nhận bản dịch thực tế.

## 5. Kết hợp `B` với các pattern letter khác

Day period thường được đặt cạnh giờ và phút:

| Pattern | Nội dung |
| --- | --- |
| `B` | Chỉ nhãn day period |
| `h B` | Giờ 12 tiếng và day period |
| `h:mm B` | Giờ, phút và day period |
| `HH:mm B` | Giờ 24 tiếng, phút và day period |
| `EEEE h:mm B` | Thứ, giờ, phút và day period |

Ví dụ:

```java
DateTimeFormatter timeFormatter =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US);

DateTimeFormatter detailedFormatter =
        DateTimeFormatter.ofPattern("EEEE, h:mm B", Locale.US);

LocalTime meetingTime = LocalTime.of(15, 30);
System.out.println(timeFormatter.format(meetingTime));
```

Pattern `h:mm B` thường tự nhiên khi muốn dùng đồng hồ 12 giờ cùng nhãn khoảng trong ngày. Pattern `HH:mm B` có thể hữu ích nếu sản phẩm muốn giữ giờ 24 tiếng nhưng vẫn thêm cách diễn đạt day period. Chọn kiểu hiển thị theo thiết kế giao diện và quy ước locale.

### Độ rộng văn bản

Với các trường văn bản, số lượng pattern letter quyết định kiểu trình bày:

| Pattern | Kiểu trình bày |
| --- | --- |
| `B`, `BB`, `BBB` | Dạng ngắn |
| `BBBB` | Dạng đầy đủ |
| `BBBBB` | Dạng hẹp |

Ví dụ:

```java
DateTimeFormatter shortPeriod =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US);
DateTimeFormatter fullPeriod =
        DateTimeFormatter.ofPattern("h:mm BBBB", Locale.US);
DateTimeFormatter narrowPeriod =
        DateTimeFormatter.ofPattern("h:mm BBBBB", Locale.US);
```

Không phải locale nào cũng có ba cách viết khác nhau rõ rệt. Dạng ngắn và đầy đủ có thể giống nhau; dạng hẹp có thể dùng ký hiệu ngắn. Kiểm tra kết quả thực tế với locale mục tiêu trước khi quyết định chiều rộng giao diện.

## 6. Định dạng từ `LocalTime`, `LocalDateTime` và `ZonedDateTime`

Day period được xác định từ giờ địa phương. Các kiểu thời gian trong `java.time` cung cấp ngữ cảnh khác nhau:

| Kiểu | Có giờ địa phương? | Dùng với `B` |
| --- | --- | --- |
| `LocalTime` | Có giờ và phút, không có ngày/múi giờ | Phù hợp khi đã có giờ địa phương |
| `LocalDateTime` | Có ngày và giờ địa phương, không có múi giờ | Phù hợp khi thời gian đã ở múi giờ nghiệp vụ |
| `ZonedDateTime` | Có ngày, giờ và `ZoneId` | Phù hợp khi thời điểm gắn với múi giờ cụ thể |
| `Instant` | Chỉ biểu diễn một thời điểm trên trục UTC | Cần chuyển sang múi giờ trước khi lấy day period |

Ví dụ với một cuộc hẹn ở Thành phố Hồ Chí Minh:

```java
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime appointment =
        ZonedDateTime.of(2026, 11, 27, 15, 30, 0, 0, zone);

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("EEEE, h:mm B", Locale.forLanguageTag("vi-VN"));

System.out.println(formatter.format(appointment));
```

Nếu dữ liệu đầu vào là `Instant`, đặt múi giờ rõ ràng cho formatter:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

Instant eventTime = Instant.parse("2026-11-27T08:30:00Z");

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US)
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(formatter.format(eventTime));
```

Không định dạng `Instant` như thể nó đã có giờ địa phương. Day period phải được tính sau khi thời điểm được chuyển sang múi giờ hiển thị. Cùng một `Instant` có thể thuộc day period khác nhau tại hai khu vực khác nhau.

## 7. Phân tích chuỗi có day period

`DateTimeFormatter` không chỉ định dạng; nó còn có thể phân tích văn bản day period thành thời gian nếu chuỗi cung cấp đủ thông tin.

Ví dụ với pattern `h:mm B`:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter parser =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US)
                .withResolverStyle(ResolverStyle.STRICT);

LocalTime time = LocalTime.parse("3:30 in the afternoon", parser);
System.out.println(time);
```

Day period được phân tích thành một loại khoảng thời gian theo locale. Khi có giờ 12 tiếng, parser kết hợp giờ đó với day period để xác định giờ trong ngày. Khi có giờ 24 tiếng, parser kiểm tra giờ có nằm trong day period đã đọc hay không.

### Quy tắc khi chỉ có day period

Nếu chuỗi chỉ có tên khoảng, chẳng hạn chỉ có `in the afternoon` mà không có giờ/phút, parser không thể khôi phục một thời điểm chính xác. Theo quy tắc của `DateTimeFormatterBuilder`, trong chế độ `SMART` hoặc `LENIENT`, thời điểm giữa của khoảng có thể được dùng làm giá trị `LocalTime`.

Ví dụ, nếu dữ liệu locale định nghĩa một khoảng night từ 21:00 đến 06:00, điểm giữa của khoảng đi qua nửa đêm có thể là 01:30. Đây là giá trị đại diện để giải quyết parse, không phải giờ gốc của một sự kiện.

Vì vậy:

- Dùng `B` cùng giờ/phút khi cần phân tích một thời điểm cụ thể.
- Không dùng chuỗi chỉ có “buổi chiều” hoặc “ban đêm” để tái tạo timestamp chính xác.
- Nếu nghiệp vụ cần một khoảng thời gian, mô hình hóa nó thành khoảng bắt đầu/kết thúc riêng thay vì coi day period là một thời điểm.

### Kiểm tra tính nhất quán

Khi chuỗi có cả giờ và day period, hai phần phải phù hợp theo quy tắc locale. Ví dụ một giờ 03:30 kết hợp với nhãn afternoon có thể không hợp lệ; trong chế độ `STRICT` hoặc `SMART`, xung đột có thể gây `DateTimeException`. Chế độ `LENIENT` có thể bỏ qua day period khi có xung đột, vì vậy không nên dùng chế độ này nếu tính nhất quán là yêu cầu nghiệp vụ.

## 8. Dùng `DateTimeFormatterBuilder`

Khi cần dựng formatter theo từng phần hoặc muốn chỉ định kiểu văn bản rõ ràng, có thể dùng `DateTimeFormatterBuilder.appendDayPeriodText(TextStyle)`.

Ví dụ:

```java
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.TextStyle;
import java.util.Locale;

DateTimeFormatter formatter = new DateTimeFormatterBuilder()
        .appendPattern("h:mm ")
        .appendDayPeriodText(TextStyle.FULL)
        .toFormatter(Locale.US);
```

`appendDayPeriodText` bổ sung phần định dạng/phân tích văn bản day period. Khi định dạng, builder lấy `HOUR_OF_DAY` và có thể dùng thêm `MINUTE_OF_HOUR`, sau đó ánh xạ sang loại day period theo dữ liệu locale và tìm bản dịch tương ứng.

Khi phân tích, văn bản được chuyển thành day period type rồi kết hợp với các trường giờ/phút để tạo `LocalTime`. Vì vậy, các quy tắc về xung đột và midpoint ở phần trước cũng áp dụng cho formatter được dựng bằng builder.

Chọn `DateTimeFormatter.ofPattern()` cho pattern ngắn, dễ đọc. Dùng builder khi cấu trúc định dạng có nhiều phần tùy chọn hoặc cần kết hợp các thành phần động.

## 9. Kiểm thử day period ổn định

Test nên kiểm tra hợp đồng của ứng dụng, không khóa cứng mọi bản dịch locale nếu bản dịch không phải yêu cầu sản phẩm cố định.

### Kiểm thử định dạng và parse round-trip

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class DayPeriodFormatterTest {
    @Test
    void formatsAndParsesTimeWithDayPeriod() {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("h:mm B", Locale.US);
        LocalTime original = LocalTime.of(15, 30);

        String text = formatter.format(original);
        LocalTime parsed = LocalTime.parse(text, formatter);

        assertFalse(text.isBlank());
        assertEquals(original, parsed);
    }

    @Test
    void formatterCanUseVietnameseLocale() {
        Locale locale = Locale.forLanguageTag("vi-VN");
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("h:mm B", locale);

        String text = formatter.format(LocalTime.of(15, 30));

        assertFalse(text.isBlank());
    }
}
```

Round-trip kiểm tra rằng văn bản do formatter tạo ra có thể được phân tích lại thành giờ tương ứng trong cùng locale và bộ dữ liệu. Test với `vi-VN` chỉ kiểm tra formatter tạo được nội dung; không giả định mọi JDK/vendor phải trả về đúng một chuỗi tiếng Việt giống nhau.

### Khi nào có thể kiểm tra chuỗi chính xác?

Nếu sản phẩm có yêu cầu giao diện cụ thể, có thể kiểm tra chuỗi kỳ vọng nhưng phải kiểm soát môi trường:

- Chốt JDK vendor và phiên bản cập nhật.
- Chốt locale và locale provider được sử dụng.
- Ghi rõ chuỗi được mong đợi là một phần của hợp đồng sản phẩm.
- Chủ động xem lại snapshot khi nâng JDK hoặc cập nhật dữ liệu locale.

Nếu chỉ kiểm tra chức năng chung, ưu tiên xác minh formatter không rỗng, có thể parse lại và cho ra giờ mong đợi thay vì khẳng định một bản dịch bất biến theo thời gian.

## 10. Những điểm cần lưu ý khi đưa vào ứng dụng

### Day period phụ thuộc locale, không phải quy tắc nghiệp vụ

`B` phục vụ cách diễn đạt cho người dùng. Không dùng chuỗi được định dạng để quyết định:

- Một nhân viên đang ở ca sáng hay ca chiều.
- Một cửa hàng đã mở cửa hay chưa.
- Một giao dịch thuộc ngày kế toán nào.
- Một tác vụ có được phép chạy trong khung giờ nào.

Các quy tắc trên cần mô hình hóa bằng giờ bắt đầu/kết thúc, múi giờ và lịch nghiệp vụ rõ ràng. Day period có thể thay đổi theo locale hoặc dữ liệu ngôn ngữ; logic nghiệp vụ không nên thay đổi theo bản dịch.

### Không tự giả định ranh giới

Không viết logic kiểu `hour < 12` là buổi sáng, `hour < 18` là buổi chiều hoặc phần còn lại là buổi tối rồi dùng kết quả làm bản dịch. Cách phân loại này có thể khác với dữ liệu locale.

Nếu sản phẩm cần một khái niệm riêng như “ca sáng từ 06:00 đến 14:00”, định nghĩa nó trong domain model và đặt tên riêng. Không gọi nó là CLDR day period nếu nó không theo quy tắc locale.

### Dữ liệu locale có thể thay đổi

JDK có thể cập nhật dữ liệu CLDR theo bản phát hành hoặc bản cập nhật. Vì thế:

- Chuỗi hiển thị có thể đổi dù mã nguồn không đổi.
- Ranh giới day period của một locale có thể được hiệu chỉnh.
- Một locale có thể dùng nhãn khác hoặc quay về AM/PM nếu không có dữ liệu linh hoạt phù hợp.

Đây là hành vi bình thường của quốc tế hóa. Nếu sản phẩm yêu cầu chuỗi pháp lý hoặc thương hiệu bất biến, quản lý nội dung đó như bản dịch sản phẩm riêng thay vì kỳ vọng dữ liệu locale luôn trả về một câu cố định.

### Locale mặc định và locale người dùng

Máy chủ thường chạy với locale hệ thống khác với locale của người dùng. Vì vậy:

- Lấy locale từ tùy chọn hồ sơ, request hoặc cấu hình giao diện.
- Truyền locale tường minh vào `DateTimeFormatter`.
- Tránh thay đổi locale mặc định toàn JVM để định dạng cho một người dùng.
- Nếu ứng dụng hỗ trợ nhiều ngôn ngữ, kiểm thử ít nhất các locale chính thức mà sản phẩm cam kết.

`DateTimeFormatter` là immutable và thread-safe, nên có thể tái sử dụng formatter đã cấu hình cho một locale cố định. Nếu locale thay đổi theo người dùng, hãy chọn formatter tương ứng với locale đó thay vì dùng chung một formatter gắn với locale mặc định không rõ ràng.

### Múi giờ và thời điểm

Day period được xác định theo giờ địa phương sau khi áp dụng múi giờ. Một `Instant` duy nhất có thể là buổi sáng ở khu vực này và ban đêm ở khu vực khác. Với lịch họp, thông báo hoặc lịch sự kiện:

1. Xác định `Instant` hoặc `ZonedDateTime` đúng với nghiệp vụ.
2. Chọn `ZoneId` hiển thị của người dùng.
3. Chuyển thời điểm sang múi giờ đó.
4. Dùng formatter có locale người dùng và pattern chứa `B`.

Không dùng timezone mặc định của server để đại diện cho timezone của người dùng.

## 11. So sánh `a` và `B` trong tình huống thực tế

| Nhu cầu | Pattern phù hợp | Lý do |
| --- | --- | --- |
| Hiển thị kiểu AM/PM quen thuộc | `h:mm a` | Chỉ cần phân biệt nửa ngày |
| Hiển thị lời gọi tự nhiên theo locale | `h:mm B` | Dùng day period linh hoạt |
| Giao diện dùng giờ 24 tiếng nhưng muốn thêm nhãn khoảng | `HH:mm B` | Giữ số giờ 24 tiếng và thêm cách diễn đạt |
| Dữ liệu máy hoặc API trao đổi | ISO-8601, ví dụ `HH:mm:ss` hoặc định dạng chuẩn có offset | Không dùng nhãn ngôn ngữ tự nhiên làm định dạng trao đổi |
| Phân loại ca làm việc hoặc giờ mở cửa | Quy tắc thời gian nghiệp vụ riêng | Không phụ thuộc bản dịch locale |

Không thay thế định dạng trao đổi máy bằng chuỗi có `B`. Tên day period là văn bản hiển thị cho con người, có thể khác theo locale và dữ liệu locale; dữ liệu hệ thống nên giữ kiểu thời gian hoặc định dạng chuẩn có múi giờ phù hợp.

## 12. Checklist trước khi phát hành

| Hạng mục | Câu hỏi cần xác nhận |
| --- | --- |
| Phiên bản Java | Build/runtime có hỗ trợ pattern `B` (Java 16 trở lên) không? |
| Locale | Locale lấy từ người dùng hay từ cấu hình máy chủ? |
| Múi giờ | `Instant` đã được chuyển sang `ZoneId` hiển thị chưa? |
| Kiểu hiển thị | Sản phẩm cần `a`, `B`, `h:mm B` hay `HH:mm B`? |
| Dữ liệu locale | Có kiểm tra kết quả trên JDK/vendor mục tiêu không? |
| Parse | Chuỗi có đủ giờ/phút để khôi phục thời điểm chính xác không? |
| Resolver style | Có cần `STRICT` để từ chối giờ và day period mâu thuẫn không? |
| Kiểm thử | Có test round-trip, locale chính và trường hợp ranh giới không? |
| Nghiệp vụ | Logic ca làm/giờ mở cửa có được tách khỏi chuỗi day period không? |
| Dữ liệu trao đổi | API lưu timestamp hoặc ISO-8601 thay vì chuỗi dịch theo locale không? |

## 13. Bài tập thực hành

### Bài 1 — So sánh AM/PM và day period

Tạo hai formatter `h:mm a` và `h:mm B` với cùng locale. Định dạng các giờ 08:00, 15:30 và 21:00. Ghi lại sự khác biệt về thông tin người dùng nhận được.

### Bài 2 — Đổi locale

Định dạng cùng một `LocalTime` với `Locale.US` và `Locale.forLanguageTag("vi-VN")`. Quan sát cách diễn đạt và giải thích vì sao không nên hard-code ranh giới buổi sáng/chiều.

### Bài 3 — Định dạng một Instant

Tạo một `Instant`, định dạng với `ZoneId.of("Asia/Ho_Chi_Minh")` và một múi giờ khác. Giải thích vì sao cùng thời điểm có thể tạo day period khác nhau.

### Bài 4 — Parse và kiểm tra xung đột

Dùng pattern `h:mm B` để parse một chuỗi có giờ và day period. Thử một chuỗi mà giờ và day period mâu thuẫn, sau đó so sánh hành vi của `STRICT`, `SMART` và `LENIENT`.

### Bài 5 — Parse chỉ có day period

Thử parse chuỗi chỉ có nhãn day period. Quan sát thời điểm được giải quyết và giải thích vì sao kết quả đó chỉ là điểm đại diện, không phải giờ chính xác của sự kiện.

### Bài 6 — Viết test đa locale

Viết test xác minh formatter không trả chuỗi rỗng và có thể parse lại thời gian đã định dạng. Không khóa cứng bản dịch của tất cả locale nếu sản phẩm không cam kết văn bản cụ thể.

## Tài liệu chính thức

- [Java SE 16 — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatter.html) — bảng pattern letter, trong đó `B` là period-of-day.
- [Java SE 16 — `DateTimeFormatterBuilder.appendDayPeriodText`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) — cách ánh xạ giờ sang day period và quy tắc phân tích văn bản.
- [Java SE 25 — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html) — xác nhận pattern `B` tiếp tục được hỗ trợ trong JDK hiện đại.
- [Unicode CLDR — Dates, Day Periods](https://www.unicode.org/reports/tr35/tr35-dates.html) — dữ liệu tên, độ rộng văn bản và quy tắc day period theo locale.
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252) — cơ sở dữ liệu locale CLDR được dùng mặc định từ JDK 9.

**Nguyên tắc áp dụng:** Dùng `B` khi cần diễn đạt giờ theo day period tự nhiên của locale. Chọn locale và múi giờ tường minh, hiểu quy tắc parse và không dùng tên khoảng trong ngày làm logic nghiệp vụ hoặc định dạng trao đổi máy.
