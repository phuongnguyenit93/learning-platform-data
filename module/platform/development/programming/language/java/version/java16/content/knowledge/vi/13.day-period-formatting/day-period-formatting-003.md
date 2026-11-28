# Phân biệt day period B với ký hiệu AM/PM a

> **Chương:** Định dạng day period  
> **Phạm vi:** So sánh hai pattern letter `a` và `B` trong `DateTimeFormatter`: `a` biểu diễn nửa ngày AM/PM, còn `B` biểu diễn khoảng trong ngày theo locale. Tập trung vào lựa chọn đúng cho giao diện, cách parse và những giới hạn cần biết khi nâng JDK.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khác biệt về ý nghĩa giữa `a` và `B`.
2. Chọn pattern phù hợp với đồng hồ 12 tiếng và cách diễn đạt tự nhiên theo locale.
3. So sánh kết quả của hai pattern trên cùng một thời điểm và locale.
4. Hiểu cách parser kết hợp `a` hoặc `B` với trường giờ.
5. Nhận biết khi nào day period phù hợp cho hiển thị và khi nào không phù hợp cho logic nghiệp vụ.
6. Viết test không phụ thuộc cứng vào bản dịch locale không được cam kết.

## 1. Vì sao có cả AM/PM và day period?

Một ngày có thể được diễn đạt theo nhiều cách. Đồng hồ 12 tiếng thường chia ngày thành hai nửa:

- **AM:** nửa đầu ngày, từ nửa đêm đến trước buổi trưa.
- **PM:** nửa sau ngày, từ buổi trưa đến trước nửa đêm.

Đây là cách chia đơn giản, thuận tiện cho đồng hồ 12 tiếng. Tuy nhiên, khi giao tiếp tự nhiên, người dùng có thể muốn phân biệt buổi sáng, buổi chiều, buổi tối hoặc ban đêm. Một nhãn PM không thể hiện riêng các khoảng này.

Java có hai pattern letter phục vụ hai nhu cầu:

- `a`: AM/PM marker — cho biết giờ thuộc nửa ngày nào.
- `B`: day period — diễn đạt khoảng trong ngày theo dữ liệu locale, chẳng hạn morning, afternoon, evening hoặc night.

`a` đã có từ các phiên bản Java trước. `B` được bổ sung vào `DateTimeFormatter` từ Java 16 và vẫn được hỗ trợ trong JDK hiện đại.

## 2. Khác biệt cốt lõi giữa a và B

| Tiêu chí | `a` | `B` |
| --- | --- | --- |
| Ý nghĩa | AM hoặc PM | Day period linh hoạt theo locale |
| Số nhóm thời gian | Hai nửa ngày | Có thể có nhiều khoảng trong ngày |
| Nguồn văn bản | AM/PM text của locale | Tên day period và quy tắc CLDR của locale |
| Phân biệt sáng/chiều/tối/đêm | Không | Có thể, nếu locale cung cấp |
| Pattern điển hình | `h:mm a` | `h:mm B` |
| Phiên bản Java | Có từ các phiên bản Java ban đầu của `java.time` | Có từ Java 16 |
| Mục đích | Hiển thị đồng hồ 12 tiếng | Hiển thị thời gian tự nhiên hơn theo ngôn ngữ |

Điểm quan trọng: `a` cũng là văn bản được bản địa hóa, không nhất thiết luôn hiện đúng hai chữ cái `AM` và `PM` ở mọi locale. Khác biệt nằm ở mô hình thời gian: `a` biểu diễn hai nửa ngày, còn `B` dùng các khoảng day period linh hoạt.

### Minh họa cùng một thời điểm

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalTime time = LocalTime.of(15, 30);

DateTimeFormatter amPm =
        DateTimeFormatter.ofPattern("h:mm a", Locale.US);
DateTimeFormatter dayPeriod =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US);

System.out.println(amPm.format(time));
System.out.println(dayPeriod.format(time));
```

Với dữ liệu locale tiếng Anh Mỹ thường gặp, kết quả có dạng:

```text
3:30 PM
3:30 in the afternoon
```

Hai chuỗi nói về cùng một giờ. Chuỗi thứ nhất chỉ cho biết đó là nửa ngày PM; chuỗi thứ hai cung cấp cách diễn đạt khoảng trong ngày chi tiết hơn.

## 3. Quan sát khác biệt qua nhiều thời điểm

Với một locale cụ thể, có thể định dạng nhiều giờ bằng cả hai pattern:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;

List<LocalTime> times = List.of(
        LocalTime.of(8, 0),
        LocalTime.of(15, 30),
        LocalTime.of(20, 15),
        LocalTime.of(23, 0)
);

DateTimeFormatter amPm =
        DateTimeFormatter.ofPattern("h:mm a", Locale.US);
DateTimeFormatter dayPeriod =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US);

for (LocalTime time : times) {
    System.out.printf(
            "%s | %s%n",
            amPm.format(time),
            dayPeriod.format(time)
    );
}
```

Bảng sau minh họa ý nghĩa, không phải bảng ranh giới cố định cho mọi locale:

| Giờ | Dạng `a` thường gặp | Ý nghĩa `B` có thể diễn đạt |
| --- | --- | --- |
| 08:00 | `8:00 AM` | Buổi sáng |
| 15:30 | `3:30 PM` | Buổi chiều |
| 20:15 | `8:15 PM` | Buổi tối |
| 23:00 | `11:00 PM` | Ban đêm |

`a` vẫn là một nhãn hợp lệ cho tất cả ví dụ trên, nhưng nó không phân biệt 15:30 với 20:15 vì cả hai đều thuộc PM. `B` có thể chọn nhãn khác nhau theo dữ liệu locale.

Không suy ra từ bảng rằng 15:00 luôn là buổi chiều hoặc 20:00 luôn là buổi tối. Ranh giới và tên gọi do locale quyết định.

## 4. Pattern a: khi cần AM/PM

Pattern `a` phù hợp khi:

- Sản phẩm dùng đồng hồ 12 tiếng.
- Người dùng quen với AM/PM.
- Giao diện cần nhãn ngắn gọn để tránh nhầm 03:00 với 15:00.
- Hệ thống cần hiển thị quy ước AM/PM đã được sản phẩm thống nhất.

Ví dụ:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("h:mm a", Locale.US);

System.out.println(formatter.format(LocalTime.of(9, 15)));
System.out.println(formatter.format(LocalTime.of(21, 15)));
```

Với locale US, hai giờ có thể hiển thị tương ứng dạng `9:15 AM` và `9:15 PM`.

### Giới hạn của a

- Không phân biệt riêng buổi sáng và buổi trưa.
- Không phân biệt buổi chiều, buổi tối và ban đêm.
- Không mô tả một khoảng linh hoạt theo ngôn ngữ.
- Không nên được diễn giải thành quy tắc ca làm hoặc lịch nghiệp vụ.

Nếu yêu cầu chỉ là cho người dùng biết giờ thuộc nửa ngày nào, `a` là đủ. Không cần dùng `B` chỉ vì nó mới hơn.

## 5. Pattern B: khi cần cách diễn đạt tự nhiên theo locale

Pattern `B` phù hợp khi giao diện cần cách gọi khoảng trong ngày giàu ngữ cảnh hơn AM/PM:

- Ứng dụng lịch hiển thị giờ hẹn.
- Ứng dụng nhắc việc diễn đạt thời điểm tự nhiên.
- Giao diện người dùng đa ngôn ngữ.
- Văn bản hỗ trợ người dùng phân biệt buổi chiều, tối và đêm.

Ví dụ:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US);

System.out.println(formatter.format(LocalTime.of(8, 0)));
System.out.println(formatter.format(LocalTime.of(15, 30)));
System.out.println(formatter.format(LocalTime.of(20, 15)));
```

`B` sử dụng dữ liệu locale để ánh xạ thời gian sang day period. Một locale có thể có các nhãn morning, afternoon, evening, night; locale khác có thể phân chia hoặc diễn đạt khác.

### Độ rộng của B

| Pattern | TextStyle | Mục đích |
| --- | --- | --- |
| `B` | `SHORT` | Dạng ngắn |
| `BBBB` | `FULL` | Dạng đầy đủ |
| `BBBBB` | `NARROW` | Dạng hẹp |

Chọn dạng phù hợp với không gian giao diện. Không giả định cả ba dạng đều tạo ra chuỗi khác nhau ở mọi locale.

## 6. Locale ảnh hưởng cả a lẫn B, nhưng theo cách khác nhau

Cả hai pattern đều phụ thuộc locale để hiển thị văn bản. Tuy nhiên, dữ liệu mà chúng biểu diễn khác nhau:

- `a` lấy nhãn AM/PM đã bản địa hóa.
- `B` lấy tên và quy tắc phân loại day period theo locale.

Ví dụ chọn locale rõ ràng:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;

List<Locale> locales = List.of(
        Locale.US,
        Locale.UK,
        Locale.forLanguageTag("vi-VN"),
        Locale.forLanguageTag("fr-FR")
);

LocalTime time = LocalTime.of(20, 15);

for (Locale locale : locales) {
    DateTimeFormatter amPm =
            DateTimeFormatter.ofPattern("h:mm a", locale);
    DateTimeFormatter dayPeriod =
            DateTimeFormatter.ofPattern("h:mm B", locale);

    System.out.println(locale + " | "
            + amPm.format(time) + " | "
            + dayPeriod.format(time));
}
```

Đây là ví dụ để quan sát dữ liệu locale thực tế trên JDK đang chạy. Không khẳng định một bản dịch tiếng Việt cụ thể nếu sản phẩm chưa chốt JDK/vendor và nội dung hiển thị.

### Vai trò của CLDR

CLDR cung cấp dữ liệu về:

- Tên AM/PM theo locale.
- Tên day period theo kiểu ngắn, đầy đủ hoặc hẹp.
- Các khoảng day period và ranh giới thời gian.
- Các dạng đặc biệt như noon hoặc midnight nếu locale hỗ trợ.

Java dùng dữ liệu locale để định dạng. Khi nâng JDK hoặc thay đổi locale provider, văn bản hay ranh giới có thể được cập nhật. Đây là lý do test không nên khóa cứng tất cả chuỗi dịch nếu sản phẩm không cam kết chúng.

## 7. Chọn a hay B theo nhu cầu giao diện

| Tình huống | Lựa chọn gợi ý | Vì sao |
| --- | --- | --- |
| Đồng hồ 12 tiếng truyền thống | `h:mm a` | Cần phân biệt AM và PM |
| Giao diện nhỏ, nhãn ngắn | `h:mm a` hoặc `h:mm B` dạng ngắn | Chọn theo khả năng hiểu của người dùng và locale |
| Lịch hẹn muốn diễn đạt tự nhiên | `h:mm B` | Có thể phân biệt chiều, tối, đêm |
| Thông báo bằng ngôn ngữ tự nhiên | `h:mm B` | Day period có ngữ cảnh hơn |
| Giao diện 24 tiếng | `HH:mm` | Không cần AM/PM; có thể thêm `B` nếu có ích |
| Dữ liệu trao đổi giữa hệ thống | ISO-8601 hoặc kiểu thời gian | Không dùng văn bản locale làm dữ liệu chuẩn |

Đôi khi chỉ dùng `HH:mm` là rõ ràng nhất. Không phải mọi giao diện đều cần thêm `a` hoặc `B`.

## 8. Parse: a và B cung cấp thông tin khác nhau

Hai pattern đều có thể tham gia phân tích chuỗi thành giờ, nhưng chúng cung cấp thông tin khác nhau cho resolver.

### Parse với a

Với pattern `h:mm a`, parser kết hợp:

- `h` — giờ trong nửa ngày, từ 1 đến 12.
- `m` — phút.
- `a` — AM hoặc PM.

Ví dụ:

```java
DateTimeFormatter amPmParser =
        DateTimeFormatter.ofPattern("h:mm a", Locale.US);

LocalTime morning = LocalTime.parse("9:15 AM", amPmParser);
LocalTime evening = LocalTime.parse("9:15 PM", amPmParser);

System.out.println(morning);
System.out.println(evening);
```

Kết quả tương ứng là 09:15 và 21:15. `a` phân biệt hai nửa ngày; nó không cần biết đó là buổi chiều hay ban đêm.

### Parse với B

Với pattern `h:mm B`, parser kết hợp giờ trong nửa ngày với khoảng day period đã đọc:

```java
DateTimeFormatter dayPeriodParser =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US);

LocalTime afternoon = LocalTime.parse(
        "3:30 in the afternoon",
        dayPeriodParser
);

System.out.println(afternoon);
```

Day period giúp phân biệt các khoảng chi tiết hơn nếu dữ liệu locale có định nghĩa chúng. Parser sử dụng giờ và có thể sử dụng phút để xác định thời điểm phù hợp với khoảng đó.

### Khi nào chuỗi không nhất quán?

Với pattern `HH:mm B`, nếu giờ 24 tiếng không thuộc day period đã ghi, parser ở chế độ `STRICT` hoặc `SMART` sẽ ném `DateTimeException`. Ở chế độ `LENIENT`, day period xung đột có thể bị bỏ qua.

Điều này quan trọng với dữ liệu nhập từ người dùng. Nếu cần xác thực, chọn resolver style rõ ràng và không dùng `LENIENT` chỉ để làm parser chấp nhận mọi đầu vào.

### Chỉ có nhãn day period

Nếu chuỗi chỉ có `B` và không có trường giờ, phút, giây hoặc nano giây, chế độ `SMART`/`LENIENT` có thể resolve về điểm giữa của khoảng day period. Ví dụ một khoảng night đi qua nửa đêm có thể có midpoint nằm sau 00:00.

Đó là giá trị đại diện do quy tắc resolve tạo ra. Nó không khôi phục giờ thực của một sự kiện và không thể thay thế timestamp.

## 9. Chọn locale và múi giờ một cách tường minh

Locale quyết định văn bản và quy tắc day period. Múi giờ quyết định giờ địa phương mà formatter dùng để chọn khoảng trong ngày. Hai yếu tố này độc lập:

- Locale `vi-VN` không tự động có nghĩa thời điểm phải ở `Asia/Ho_Chi_Minh`.
- Một người dùng tiếng Việt có thể đang xem lịch ở múi giờ khác.
- Cùng một `Instant` có thể là buổi sáng ở một vùng và ban đêm ở vùng khác.

Ví dụ định dạng một thời điểm tuyệt đối:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

Instant eventTime = Instant.parse("2026-11-27T08:30:00Z");
ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");
Locale userLocale = Locale.forLanguageTag("vi-VN");

DateTimeFormatter amPm =
        DateTimeFormatter.ofPattern("h:mm a", userLocale)
                .withZone(userZone);
DateTimeFormatter dayPeriod =
        DateTimeFormatter.ofPattern("h:mm B", userLocale)
                .withZone(userZone);

System.out.println(amPm.format(eventTime));
System.out.println(dayPeriod.format(eventTime));
```

Nếu chỉ cần so sánh hai kiểu văn bản, giữ nguyên cùng một `Instant`, `ZoneId` và `Locale`; chỉ thay pattern. Như vậy, sự khác biệt quan sát được đến từ `a` và `B`, không phải do hai formatter đang dùng múi giờ hoặc locale khác nhau.

## 10. Không dùng a hoặc B làm logic nghiệp vụ

Cả `a` và `B` đều phục vụ định dạng văn bản. Không dùng chuỗi hiển thị để quyết định:

- Ca làm của nhân viên.
- Giờ mở cửa hoặc đóng cửa.
- Thời điểm được phép chạy tác vụ.
- Ngày kế toán hoặc kỳ tính phí.
- Chính sách giao dịch phụ thuộc múi giờ.

Ví dụ, quy tắc “ca sáng từ 06:00 đến 14:00” là quy tắc của domain. Nó cần thời điểm bắt đầu/kết thúc, múi giờ và lịch áp dụng rõ ràng. CLDR day period có thể dùng ranh giới khác và thay đổi theo locale.

Nếu ứng dụng cần cả hai khái niệm:

1. Dùng domain model để xác định ca làm hoặc khung giờ nghiệp vụ.
2. Dùng `DateTimeFormatter` với `a` hoặc `B` để trình bày thời gian cho người dùng.
3. Giữ timestamp/giờ nghiệp vụ ở kiểu dữ liệu thời gian, không lưu chuỗi đã dịch làm dữ liệu chuẩn.

## 11. Kiểm thử so sánh a và B

Test nên xác minh hai pattern cùng định dạng một thời điểm, có thể parse lại bằng formatter tương ứng và không ràng buộc bản dịch ngoài hợp đồng sản phẩm.

Ví dụ JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class AmPmAndDayPeriodTest {
    @Test
    void bothPatternsRepresentTheSameTime() {
        LocalTime original = LocalTime.of(15, 30);

        DateTimeFormatter amPm =
                DateTimeFormatter.ofPattern("h:mm a", Locale.US);
        DateTimeFormatter dayPeriod =
                DateTimeFormatter.ofPattern("h:mm B", Locale.US);

        String amPmText = amPm.format(original);
        String dayPeriodText = dayPeriod.format(original);

        assertFalse(amPmText.isBlank());
        assertFalse(dayPeriodText.isBlank());
        assertEquals(original, LocalTime.parse(amPmText, amPm));
        assertEquals(original, LocalTime.parse(dayPeriodText, dayPeriod));
    }
}
```

### Kiểm thử nhiều thời điểm và locale

Nên bao phủ:

- Một thời điểm buổi sáng.
- Một thời điểm buổi chiều.
- Một thời điểm buổi tối hoặc ban đêm.
- Cùng một thời điểm với nhiều locale sản phẩm hỗ trợ.
- Parse chuỗi do chính formatter tạo ra.
- Đầu vào mâu thuẫn khi ứng dụng có chức năng parse.

Không khẳng định mọi locale đều tạo ra nhãn morning/afternoon/evening/night riêng. Một locale có thể fallback về AM/PM hoặc có cách diễn đạt khác.

## 12. Các lỗi thường gặp khi chọn pattern

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `a` khi giao diện cần phân biệt chiều và tối | Cả hai đều chỉ hiện PM | Chọn `B` nếu locale hỗ trợ day period phù hợp |
| Dùng `B` nhưng kỳ vọng mọi locale có cùng ranh giới | Văn bản có thể khác hoặc không phân biệt như mong đợi | Kiểm tra locale mục tiêu và dữ liệu CLDR |
| Hard-code giờ bắt đầu buổi sáng/chiều | Giao diện không còn đúng với locale khác | Để formatter xử lý day period |
| Dùng chuỗi `B` làm điều kiện ca làm | Logic nghiệp vụ phụ thuộc bản dịch và JDK | Mô hình hóa khung giờ nghiệp vụ riêng |
| So sánh chuỗi `AM`/`PM` để xác định thời gian | Sai khi nhãn được bản địa hóa | Parse về kiểu thời gian hoặc dùng trường thời gian |
| Dùng `Instant` mà không đặt múi giờ hiển thị | Day period được xác định theo zone mặc định ngoài ý muốn | Dùng `withZone()` hoặc `ZonedDateTime` |
| Cho rằng `--release 16` kiểm tra được ký tự B trong chuỗi pattern | Mã có thể biên dịch nhưng runtime cũ vẫn không hiểu pattern | Kiểm thử trên runtime thực tế Java 16 trở lên |

## 13. Checklist lựa chọn

| Câu hỏi | Nếu câu trả lời là có |
| --- | --- |
| Chỉ cần phân biệt hai nửa ngày? | Dùng `a` |
| Muốn diễn đạt buổi sáng, chiều, tối hoặc đêm theo ngôn ngữ? | Cân nhắc `B` |
| Giao diện dùng 24 tiếng và đã rõ ràng? | Có thể chỉ dùng `HH:mm` |
| Cần hiển thị cho nhiều locale? | Truyền locale tường minh và test trên các locale cam kết |
| Dữ liệu là `Instant`? | Chọn `ZoneId` người dùng trước khi định dạng |
| Cần phân loại ca làm hoặc giờ mở cửa? | Dùng quy tắc nghiệp vụ riêng, không dùng `a`/`B` |
| Cần parse chuỗi do người dùng nhập? | Chọn resolver style và kiểm tra dữ liệu mâu thuẫn |
| Runtime có thể thấp hơn Java 16? | Đảm bảo runtime thực tế hỗ trợ pattern `B` trước khi dùng |

## 14. Bài tập thực hành

### Bài 1 — So sánh cùng thời điểm

Tạo formatter `h:mm a` và `h:mm B` với `Locale.US`. Định dạng 08:00, 15:30 và 20:15. Giải thích vì sao hai thời điểm thuộc PM vẫn có thể có day period khác nhau.

### Bài 2 — Thử nhiều locale

Lặp qua `Locale.US`, `Locale.UK`, `vi-VN` và `fr-FR`. Ghi nhận văn bản do `a` và `B` tạo ra trên JDK đang dùng. Giải thích vì sao không thể dùng một bảng dịch hoặc ranh giới giờ cố định cho mọi locale.

### Bài 3 — Parse hai loại nhãn

Parse `9:15 PM` bằng `h:mm a` và chuỗi day period tương ứng bằng `h:mm B`. Xác minh cả hai cho cùng một `LocalTime`.

### Bài 4 — Phân biệt hiển thị và nghiệp vụ

Một hệ thống quy định ca sáng từ 06:00 đến 14:00. Viết quy tắc nghiệp vụ bằng giờ bắt đầu/kết thúc và dùng `B` chỉ để hiển thị. Giải thích vì sao không nên lấy văn bản day period để xác định ca.

### Bài 5 — Kiểm thử múi giờ

Tạo một `Instant`, định dạng với cùng locale nhưng hai `ZoneId` khác nhau. Quan sát khi giờ địa phương chuyển từ ban ngày sang ban đêm và giải thích vai trò của zone.

## Tài liệu chính thức

- [Java SE 16 — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatter.html) — định nghĩa pattern letter `a` và `B`.
- [Java SE 16 — `DateTimeFormatterBuilder`](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) — day period text và quy tắc phân tích.
- [Java SE 25 — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html) — xác nhận pattern `B` vẫn được hỗ trợ trong JDK hiện đại.
- [Unicode CLDR — Dates, Day Periods](https://www.unicode.org/reports/tr35/tr35-dates.html) — dữ liệu AM/PM, tên và quy tắc day period theo locale.
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252) — cơ sở dữ liệu locale CLDR được dùng mặc định từ JDK 9.

**Nguyên tắc áp dụng:** Chọn `a` khi cần nhãn AM/PM cho đồng hồ 12 tiếng; chọn `B` khi muốn diễn đạt khoảng trong ngày theo locale. Dùng cùng locale và múi giờ khi so sánh, giữ logic nghiệp vụ tách biệt với văn bản hiển thị và kiểm tra trên runtime thực tế.
