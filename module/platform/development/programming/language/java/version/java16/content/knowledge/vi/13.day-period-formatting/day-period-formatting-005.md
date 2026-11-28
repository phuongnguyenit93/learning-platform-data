# Độ rộng B, BBBB và BBBBB trong văn bản hiển thị

> **Chương:** Định dạng day period  
> **Phạm vi:** Chọn độ rộng văn bản cho pattern day period trong DateTimeFormatter. Java 16 hỗ trợ B ở dạng ngắn, BBBB ở dạng đầy đủ và BBBBB ở dạng hẹp. Các dạng này lấy dữ liệu theo locale, vì vậy không phải giới hạn số ký tự hoặc bản dịch cố định.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt B, BB, BBB, BBBB và BBBBB.
2. Ánh xạ các pattern sang TextStyle.SHORT, FULL và NARROW.
3. Chọn độ rộng phù hợp với màn hình, lịch và thông báo.
4. Hiểu vì sao các độ rộng có thể tạo ra văn bản giống nhau ở một locale.
5. Dùng DateTimeFormatterBuilder để chọn TextStyle bằng mã.
6. Kiểm thử nhiều locale mà không giả định chuỗi phải ngắn dần theo số chữ B.

## 1. Ba độ rộng của day period

Pattern letter B biểu diễn day period theo dữ liệu locale. Số lần lặp B chọn kiểu văn bản:

| Pattern | TextStyle tương đương | Cách gọi | Mục đích |
| --- | --- | --- | --- |
| B | SHORT | Dạng ngắn | Giao diện cần nhãn gọn |
| BB | SHORT | Dạng ngắn | Tương đương B |
| BBB | SHORT | Dạng ngắn | Tương đương B |
| BBBB | FULL | Dạng đầy đủ | Văn bản rõ nghĩa, dễ đọc |
| BBBBB | NARROW | Dạng hẹp | Không gian hiển thị rất hạn chế |

Đây là quy tắc pattern của DateTimeFormatter. Với trường văn bản, một đến ba chữ cái chọn dạng ngắn, bốn chữ chọn dạng đầy đủ và năm chữ chọn dạng hẹp.

Ví dụ, pattern h:mm B và h:mm BBBB dùng cùng giờ, phút và locale; chỉ kiểu văn bản day period thay đổi. Pattern h:mm BBBBB yêu cầu dạng hẹp.

## 2. Độ rộng không phải số ký tự

SHORT, FULL và NARROW là các kiểu trình bày được tra từ dữ liệu locale. Chúng không quy định:

- Số ký tự tối đa của kết quả.
- Một hậu tố cố định như AM hoặc PM.
- Một quy tắc viết tắt chung cho mọi ngôn ngữ.
- Ranh giới thời gian giống nhau giữa các locale.

Ví dụ, dạng SHORT của một locale có thể vẫn là một cụm từ nhiều từ. Dạng NARROW có thể ngắn hơn, nhưng không bảo đảm luôn có ít ký tự hơn FULL. Một locale cũng có thể cung cấp cùng một văn bản cho hai hoặc cả ba kiểu.

Vì vậy, đừng viết kiểm thử như “BBBBB luôn ngắn hơn BBBB” hoặc cắt chuỗi theo một số ký tự cố định. Hãy xem các style là yêu cầu trình bày để thư viện locale chọn nội dung phù hợp.

## 3. Quan sát ba dạng với DateTimeFormatter

Tạo ba formatter cho cùng một locale:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

Locale locale = Locale.US;
LocalTime time = LocalTime.of(15, 30);

DateTimeFormatter shortPeriod =
        DateTimeFormatter.ofPattern("h:mm B", locale);
DateTimeFormatter fullPeriod =
        DateTimeFormatter.ofPattern("h:mm BBBB", locale);
DateTimeFormatter narrowPeriod =
        DateTimeFormatter.ofPattern("h:mm BBBBB", locale);

System.out.println(shortPeriod.format(time));
System.out.println(fullPeriod.format(time));
System.out.println(narrowPeriod.format(time));
```

Ví dụ này cho phép quan sát văn bản được cung cấp bởi JDK và locale đang chạy. Không cố định một đầu ra minh họa làm kết quả bắt buộc trên mọi máy; dữ liệu CLDR và nhà cung cấp JDK có thể khác phiên bản.

### So sánh cả ba độ rộng và AM/PM

Có thể thêm pattern a để thấy day period khác nhãn AM/PM như thế nào:

```java
DateTimeFormatter amPm =
        DateTimeFormatter.ofPattern("h:mm a", locale);

System.out.println(amPm.format(time));
System.out.println(shortPeriod.format(time));
System.out.println(fullPeriod.format(time));
System.out.println(narrowPeriod.format(time));
```

Pattern a biểu diễn hai nửa ngày. Các pattern B biểu diễn day period theo locale và chọn độ rộng văn bản khác nhau.

## 4. Chọn SHORT, FULL hay NARROW?

### SHORT: B, BB hoặc BBB

SHORT thường phù hợp khi:

- Nhãn thời gian xuất hiện trong danh sách nhiều dòng.
- Lịch có nhiều sự kiện trong một ô nhỏ.
- Màn hình cần hiển thị giờ và day period nhưng không có nhiều chỗ.
- Người dùng đã quen với cách diễn đạt ngắn của locale.

Ví dụ pattern:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("h:mm B", Locale.US);
```

Không mặc định SHORT là một chữ viết tắt. Nếu locale dùng cụm từ, formatter vẫn có thể trả về cụm từ.

### FULL: BBBB

FULL phù hợp khi khả năng đọc quan trọng hơn độ gọn:

- Nội dung lịch hẹn hoặc chi tiết sự kiện.
- Thông báo cần câu chữ rõ ràng.
- Giao diện có đủ chiều rộng cho tên day period đầy đủ.
- Nội dung hướng dẫn hoặc văn bản trợ giúp.

Ví dụ:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("h:mm BBBB", Locale.US);
```

FULL không phải câu văn hoàn chỉnh. Nó chỉ là dạng day period đầy đủ được locale cung cấp; cấu trúc xung quanh vẫn do pattern và giao diện quyết định.

### NARROW: BBBBB

NARROW dành cho không gian rất hẹp, nơi ứng dụng vẫn muốn hiển thị thông tin day period:

- Nhãn nhỏ trong lịch dạng lưới.
- Thành phần giao diện có giới hạn chiều ngang.
- Màn hình phụ hoặc chế độ hiển thị cô đọng.

Ví dụ:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("h:mm BBBBB", Locale.US);
```

NARROW có thể khó hiểu hơn khi đứng riêng. Nếu nội dung ảnh hưởng đến quyết định của người dùng, hãy cung cấp ngữ cảnh đầy đủ ở màn hình chi tiết hoặc qua nhãn trợ năng phù hợp. Không chỉ dựa vào ký hiệu hẹp để truyền tải thông tin quan trọng.

## 5. Dùng DateTimeFormatterBuilder và TextStyle

Nếu formatter được dựng bằng mã thay vì pattern string, dùng appendDayPeriodText(TextStyle):

```java
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.TextStyle;
import java.util.Locale;

DateTimeFormatter shortFormatter = new DateTimeFormatterBuilder()
        .appendPattern("h:mm ")
        .appendDayPeriodText(TextStyle.SHORT)
        .toFormatter(Locale.US);

DateTimeFormatter fullFormatter = new DateTimeFormatterBuilder()
        .appendPattern("h:mm ")
        .appendDayPeriodText(TextStyle.FULL)
        .toFormatter(Locale.US);

DateTimeFormatter narrowFormatter = new DateTimeFormatterBuilder()
        .appendPattern("h:mm ")
        .appendDayPeriodText(TextStyle.NARROW)
        .toFormatter(Locale.US);
```

Ánh xạ tương ứng:

| Pattern | Builder |
| --- | --- |
| B, BB, BBB | appendDayPeriodText(TextStyle.SHORT) |
| BBBB | appendDayPeriodText(TextStyle.FULL) |
| BBBBB | appendDayPeriodText(TextStyle.NARROW) |

Phương thức appendDayPeriodText có từ Java 16. Sau khi gọi toFormatter(locale), formatter hoàn chỉnh là immutable và thread-safe, có thể tái sử dụng giữa các luồng.

Chọn ofPattern khi pattern ngắn, cố định và dễ đọc. Chọn builder khi cần ghép nhiều phần, có cấu trúc tùy chọn hoặc style được chọn từ cấu hình.

## 6. Dữ liệu locale quyết định văn bản

Day period và các dạng SHORT/FULL/NARROW được lấy từ dữ liệu locale, thường dựa trên CLDR. Locale có thể quy định:

- Các khoảng như morning, afternoon, evening và night.
- Tên văn bản cho từng khoảng.
- Dạng ngắn, đầy đủ và hẹp.
- Các trường hợp đặc biệt như noon hoặc midnight nếu dữ liệu locale hỗ trợ.

Do đó, cùng một LocalTime có thể tạo văn bản khác nhau khi thay locale. Cùng một locale cũng có thể được cập nhật dữ liệu giữa các phiên bản JDK.

Ví dụ kiểm tra nhiều locale:

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
    DateTimeFormatter shortFormatter =
            DateTimeFormatter.ofPattern("h:mm B", locale);
    DateTimeFormatter fullFormatter =
            DateTimeFormatter.ofPattern("h:mm BBBB", locale);
    DateTimeFormatter narrowFormatter =
            DateTimeFormatter.ofPattern("h:mm BBBBB", locale);

    System.out.println(locale);
    System.out.println(shortFormatter.format(time));
    System.out.println(fullFormatter.format(time));
    System.out.println(narrowFormatter.format(time));
}
```

Đoạn mã dùng cùng thời điểm để cô lập sự khác biệt do locale và độ rộng. Kết quả chính xác cần được quan sát trên JDK mục tiêu; không suy ra bản dịch tiếng Việt từ bản dịch tiếng Anh.

## 7. Không hard-code bản dịch hoặc ranh giới

Không tự tạo các nhãn như Morning, Afternoon, Evening bằng điều kiện giờ cố định rồi coi đó là kết quả của pattern B. CLDR cung cấp quy tắc theo locale; ranh giới có thể không trùng với quy ước nghiệp vụ hoặc trực giác của người viết mã.

Tách hai trách nhiệm:

1. DateTimeFormatter chọn và hiển thị day period cho người dùng.
2. Domain model quyết định ca làm, giờ mở cửa, lịch trực hoặc quy tắc nghiệp vụ bằng khoảng thời gian riêng.

Tương tự, không lưu chuỗi SHORT/FULL/NARROW trong database như dữ liệu thời gian chuẩn. Lưu LocalTime, Instant hoặc kiểu thời gian phù hợp; định dạng thành văn bản khi hiển thị.

## 8. Thiết kế giao diện theo độ rộng

Khi chọn style, hãy đánh giá cả chiều rộng thực tế và khả năng hiểu:

| Thành phần giao diện | Lựa chọn khởi đầu | Điều cần kiểm tra |
| --- | --- | --- |
| Danh sách sự kiện | SHORT | Có bị tràn dòng ở locale dài không? |
| Trang chi tiết | FULL | Văn bản có tự nhiên và dễ đọc không? |
| Lưới lịch nhỏ | NARROW hoặc bỏ day period | Nhãn có đủ rõ và không gây nhầm không? |
| Thông báo đẩy | FULL hoặc SHORT tùy giới hạn | Nội dung có rõ khi bị cắt không? |
| Đồng hồ lớn | SHORT hoặc không cần day period | Người dùng có cần nhãn sáng/chiều không? |

Không đoán chiều rộng dựa trên số chữ B. Hãy render với các locale mà sản phẩm hỗ trợ, dùng font và kích thước thực tế, rồi kiểm tra tràn, xuống dòng và khả năng đọc.

### Hỗ trợ trợ năng

Nếu dùng NARROW trong giao diện nhỏ:

- Cung cấp tên đầy đủ trong ngữ cảnh chi tiết hoặc accessible name.
- Không dùng một ký tự hẹp làm tín hiệu duy nhất cho thông tin quan trọng.
- Đảm bảo nội dung vẫn hiểu được khi người dùng phóng to hoặc dùng trình đọc màn hình.
- Kiểm tra chuỗi đầy đủ trong thông báo hoặc phần mô tả nếu nhãn nhỏ không đủ rõ.

## 9. Kiểm thử đúng hợp đồng, không kiểm thử giả định về độ dài

Test tốt nên xác nhận:

- Mỗi formatter tạo ra văn bản không rỗng.
- Pattern có cùng locale và cùng thời điểm.
- Chuỗi được tạo có thể parse lại nếu pattern chứa đủ giờ và phút.
- Ứng dụng xử lý được các locale cam kết.
- Giao diện không tràn ở kích thước thực tế.

Không nên bắt buộc:

- FULL luôn dài hơn SHORT.
- NARROW luôn ngắn hơn SHORT.
- Ba style luôn khác nhau.
- Mọi locale đều có đủ morning, afternoon, evening và night.

### Ví dụ JUnit

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class DayPeriodWidthTest {
    @Test
    void allWidthsFormatAndParseTheSameTime() {
        Locale locale = Locale.US;
        LocalTime original = LocalTime.of(15, 30);

        DateTimeFormatter[] formatters = {
                DateTimeFormatter.ofPattern("h:mm B", locale),
                DateTimeFormatter.ofPattern("h:mm BBBB", locale),
                DateTimeFormatter.ofPattern("h:mm BBBBB", locale)
        };

        for (DateTimeFormatter formatter : formatters) {
            String text = formatter.format(original);
            assertFalse(text.isBlank());
            assertEquals(original, LocalTime.parse(text, formatter));
        }
    }
}
```

Test này không khẳng định ba chuỗi khác nhau hoặc có độ dài theo thứ tự. Nó xác minh các dạng hiển thị có thể round-trip về cùng giờ trên môi trường locale đã chọn.

### Kiểm thử nhiều locale

Lặp qua locale sản phẩm hỗ trợ và kiểm tra formatter tạo nội dung. Nếu giao diện cần kiểm tra tràn, thực hiện UI test hoặc visual test trên thiết bị/viewport đại diện; unit test Java không đo được chiều rộng pixel của văn bản.

Nếu sản phẩm cam kết chính xác một bản dịch, cố định JDK vendor/version và locale provider trong môi trường test, sau đó quản lý snapshot như một phần của hợp đồng giao diện.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| B, BB và BBB cho cùng kết quả | Cả ba đều chọn SHORT | Đây là hành vi đúng theo pattern |
| BBBB không dài hơn B | Locale có thể dùng cùng văn bản cho SHORT và FULL | Không dựa vào số ký tự; kiểm tra dữ liệu locale |
| BBBBB vẫn là cụm từ dài | Locale không có dạng narrow ngắn hơn hoặc fallback về văn bản sẵn có | Thiết kế giao diện co giãn, không cắt chuỗi |
| Văn bản khác sau khi nâng JDK | Dữ liệu CLDR/provider thay đổi | Kiểm thử lại các locale đã cam kết |
| Nhãn day period không như mong đợi | Dùng locale mặc định khác hoặc locale thiếu dữ liệu phù hợp | Truyền Locale tường minh và kiểm tra JDK mục tiêu |
| Pattern không được hỗ trợ trên runtime cũ | B được bổ sung từ Java 16 | Xác minh runtime Java 16 trở lên |
| Nhãn NARROW gây khó hiểu | Dạng hẹp thiếu ngữ cảnh | Cung cấp accessible name hoặc văn bản đầy đủ |

## 11. Checklist chọn độ rộng

| Câu hỏi | Quyết định |
| --- | --- |
| Cần nhãn day period gọn? | Thử B/BB/BBB |
| Cần văn bản đầy đủ, rõ nghĩa? | Thử BBBB |
| Không gian rất hẹp? | Thử BBBBB và kiểm tra khả năng hiểu |
| Locale nào được hỗ trợ? | Test từng locale được sản phẩm cam kết |
| Có giả định độ dài theo số chữ B? | Loại bỏ giả định đó |
| Có cần chuỗi giống nhau qua các lần nâng JDK? | Chốt JDK/provider và quản lý snapshot |
| Có dùng nhãn cho logic nghiệp vụ? | Tách logic sang quy tắc thời gian riêng |
| Có lưu chuỗi day period làm dữ liệu? | Lưu kiểu thời gian chuẩn thay thế |

## 12. Bài tập thực hành

### Bài 1 — Quan sát ba độ rộng

Định dạng cùng một LocalTime với B, BBBB và BBBBB bằng Locale.US. Ghi lại kết quả thực tế và giải thích vì sao không thể kết luận trước độ dài của từng chuỗi.

### Bài 2 — So sánh nhiều locale

Lặp qua Locale.US, Locale.UK, vi-VN và fr-FR. So sánh ba độ rộng và ghi nhận locale nào dùng cùng văn bản cho nhiều style.

### Bài 3 — Dùng TextStyle

Tạo ba formatter bằng DateTimeFormatterBuilder với SHORT, FULL và NARROW. So sánh với formatter tạo từ pattern B, BBBB và BBBBB.

### Bài 4 — Chọn style cho giao diện

Thiết kế ba vị trí: danh sách sự kiện, trang chi tiết và ô lịch nhỏ. Chọn style cho từng vị trí, kiểm tra trên các locale hỗ trợ và giải thích trade-off giữa độ rõ và chiều rộng.

### Bài 5 — Viết test không phụ thuộc độ dài

Viết JUnit test xác minh mỗi style tạo được văn bản và parse lại cùng LocalTime. Không assertion rằng chuỗi phải khác nhau hoặc có độ dài tăng/giảm.

## Tài liệu chính thức

- [Java SE 16 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatter.html) — quy tắc pattern letter B và số lượng chữ cái.
- [Java SE 16 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) — appendDayPeriodText và TextStyle.
- [Java SE 16 — TextStyle](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/time/format/TextStyle.html) — SHORT, FULL và NARROW.
- [Java SE 25 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html) — xác nhận pattern B tiếp tục được hỗ trợ.
- [Unicode CLDR — Dates, Day Periods](https://www.unicode.org/reports/tr35/tr35-dates.html) — dữ liệu day period và kiểu tên theo locale.

**Nguyên tắc áp dụng:** Dùng B/BB/BBB cho SHORT, BBBB cho FULL và BBBBB cho NARROW. Chọn theo mục tiêu giao diện, kiểm tra trên locale thật và không giả định độ dài hay nội dung chuỗi; văn bản day period là dữ liệu trình bày, không phải dữ liệu nghiệp vụ.
