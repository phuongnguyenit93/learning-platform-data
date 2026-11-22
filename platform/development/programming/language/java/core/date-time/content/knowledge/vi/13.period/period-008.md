# So sánh `Period` với `Duration` khi đi qua DST và cuối tháng

Khi một ứng dụng cần “lên lịch cùng giờ vào ngày mai” hoặc “gia hạn thêm một tháng”, việc chọn phép cộng thời gian ảnh hưởng trực tiếp đến kết quả. `Duration` biểu diễn một lượng thời gian cố định theo giây và nano giây; `Period` biểu diễn khoảng theo lịch bằng năm, tháng và ngày. Chúng không thể thay thế cho nhau trong mọi tình huống.

Sự khác biệt hiện rõ khi qua **giờ mùa hè (DST)** hoặc đi từ ngày cuối tháng sang tháng ngắn hơn. Ví dụ, “sau đúng 24 giờ” là một yêu cầu khác “cùng giờ vào ngày mai tại New York”; “thêm một tháng” cũng khác “thêm 30 ngày”. Bài này trình bày cơ chế, ví dụ Java 17+, cách chọn đúng API và các trường hợp biên cần kiểm thử.

## 1. Hai kiểu biểu diễn hai ý nghĩa khác nhau

| Kiểu | Mô tả | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| `Duration` | Lượng thời gian trên trục thời gian, gồm giây và nano giây | `Duration.ofHours(24)` | Chính xác 24 giờ |
| `Period` | Khoảng lịch theo năm, tháng và ngày | `Period.ofDays(1)` | Một ngày lịch |
| `Period.ofMonths(1)` | Một tháng lịch | Tháng tiếp theo | Độ dài phụ thuộc tháng đích |
| `Period.ofYears(1)` | Một năm theo lịch | Cùng ngày năm sau nếu hợp lệ | Có thể cần xử lý 29/02 |

`Duration` không lưu ngày bắt đầu, múi giờ hay quy tắc DST. `Period` cũng không phải thời điểm; nó là lượng lịch cần cộng/trừ vào một ngày hoặc ngày giờ. Khi dùng `Period` với `ZonedDateTime`, quy tắc vùng vẫn được áp dụng để tạo kết quả ngày giờ địa phương hợp lệ.

**Câu hỏi quyết định:** Nghiệp vụ yêu cầu “sau đúng bao lâu?” hay “tới ngày/giờ nào theo lịch”? Nếu là thời lượng thực, dùng `Duration`. Nếu là quy tắc ngày, tháng hoặc năm, dùng phép toán theo lịch như `plusDays`, `plusMonths` hoặc `Period`.

## 2. DST: một ngày lịch có thể dài 23, 24 hoặc 25 giờ

Ở các khu vực có chuyển đổi giờ mùa hè, đồng hồ có thể nhảy tiến hoặc lùi. Vì thế, ngày địa phương có thể có độ dài trên dòng thời gian khác 24 giờ.

Ví dụ tại New York năm 2026, đồng hồ lùi khi kết thúc DST vào ngày 1 tháng 11. Từ 12:00 ngày 31/10 đến 12:00 ngày 01/11, giờ đồng hồ giữ nguyên 12:00 nhưng **25 giờ thực** trôi qua.

~~~java
ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime start = LocalDateTime.of(2026, 10, 31, 12, 0)
        .atZone(zone);

ZonedDateTime calendarTomorrow = start.plusDays(1);
ZonedDateTime after24Hours = start.plusHours(24);

System.out.println("start=" + start);
System.out.println("calendarTomorrow=" + calendarTomorrow);
System.out.println("after24Hours=" + after24Hours);
System.out.println("elapsedToTomorrow=" + Duration.between(
        start.toInstant(), calendarTomorrow.toInstant()).toHours());
~~~

Kết quả tương ứng với dữ liệu múi giờ New York cho ngày ví dụ:

~~~text
start=2026-10-31T12:00-04:00[America/New_York]
calendarTomorrow=2026-11-01T12:00-05:00[America/New_York]
after24Hours=2026-11-01T11:00-05:00[America/New_York]
elapsedToTomorrow=25
~~~

`start.plusDays(1)` di chuyển tới **ngày lịch kế tiếp và giữ 12:00 địa phương**. `start.plusHours(24)` cộng đúng 24 giờ trên dòng thời gian nên hiển thị 11:00 địa phương. Chúng trả hai kết quả khác nhau vì đây là hai yêu cầu khác nhau.

Ở chiều bắt đầu DST, ngày trên lịch có thể chỉ dài 23 giờ. Khi đó, cùng giờ vào ngày mai có thể cách mốc hôm nay 23 giờ thực, trong khi `Duration.ofHours(24)` vẫn là 24 giờ.

## 3. `Period.ofDays(1)` khác `Duration.ofDays(1)`

Hai lời gọi có cùng tên đơn vị nhưng thuộc hai kiểu khác nhau:

~~~java
Period calendarDay = Period.ofDays(1);
Duration fixedDay = Duration.ofDays(1);

System.out.println(calendarDay); // P1D
System.out.println(fixedDay);    // PT24H
~~~

- `Period.ofDays(1)` nghĩa là một đơn vị ngày trong lịch. Khi áp dụng vào `ZonedDateTime`, thao tác giữ logic ngày địa phương và giải quyết lại offset theo vùng.
- `Duration.ofDays(1)` có nghĩa chính xác là 24 giờ, tương đương `Duration.ofHours(24)`.

Nếu chỉ thao tác với `LocalDate`, cả hai không thể trực tiếp được hiểu là “đã trôi bao nhiêu giờ”, vì `LocalDate` không chứa đồng hồ hay múi giờ. Với `ZonedDateTime`, sự khác nhau mới thể hiện qua phép cộng và quy tắc múi giờ.

~~~java
ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime start = LocalDateTime.of(2026, 3, 7, 12, 0)
        .atZone(newYork);

ZonedDateTime periodTomorrow = start.plus(Period.ofDays(1));
ZonedDateTime durationTomorrow = start.plus(Duration.ofDays(1));

System.out.println(periodTomorrow);
System.out.println(durationTomorrow);
System.out.println(Duration.between(
        start.toInstant(), periodTomorrow.toInstant()).toHours());
~~~

Kết quả ở ngày bắt đầu DST của New York:

~~~text
2026-03-08T12:00-04:00[America/New_York]
2026-03-08T13:00-04:00[America/New_York]
23
~~~

Một ngày lịch sau giữ giờ 12:00 nhưng chỉ cách mốc bắt đầu 23 giờ. Cộng 24 giờ cho kết quả 13:00. Đây là ví dụ quan trọng để chọn API theo ý nghĩa nghiệp vụ.

## 4. Cuối tháng: một tháng không phải 30 ngày

Tháng có 28, 29, 30 hoặc 31 ngày. Vì vậy, `Period.ofMonths(1)` không tương đương `Duration.ofDays(30)`:

~~~java
LocalDate jan31 = LocalDate.of(2025, 1, 31);

System.out.println(jan31.plus(Period.ofMonths(1))); // 2025-02-28
System.out.println(jan31.plus(Duration.ofDays(30))); // không hợp lệ với LocalDate
~~~

`LocalDate` không hỗ trợ cộng `Duration` trực tiếp vì nó không có giờ/instant. Nếu muốn so sánh 30 ngày thực, cần bắt đầu từ một instant hoặc kiểu ngày giờ có thời điểm xác định. Với nhu cầu cộng tháng lịch, dùng `LocalDate.plusMonths` hay `Period.ofMonths`.

~~~java
LocalDate jan31 = LocalDate.of(2025, 1, 31);
LocalDate directTwoMonths = jan31.plusMonths(2);
LocalDate chainedTwoMonths = jan31.plusMonths(1).plusMonths(1);

System.out.println(directTwoMonths);  // 2025-03-31
System.out.println(chainedTwoMonths); // 2025-03-28
~~~

Lần cộng đầu chuyển 31/01 thành 28/02, bởi tháng 2/2025 không có ngày 31. Khi cộng tiếp từ 28/02, Java giữ ngày 28. Còn `plusMonths(2)` tính trực tiếp tháng đích từ ngày gốc 31/01 nên cho 31/03.

**Hệ quả cho lịch định kỳ:** Nếu yêu cầu là “ngày cuối tháng”, “ngày 30 mỗi tháng” hoặc “ngày làm việc cuối tháng”, hãy giữ quy tắc gốc và tính từng kỳ theo tháng mục tiêu. Không dùng ngày đã bị điều chỉnh của kỳ trước làm quy tắc cho mọi kỳ sau.

## 5. Cuối tháng khi kết hợp với `ZonedDateTime`

Nếu bài toán vừa yêu cầu ngày lịch vừa có múi giờ, hãy thực hiện theo hai bước có ý nghĩa riêng: tính ngày đích theo lịch, rồi áp dụng quy tắc múi giờ của ngày đó.

Ví dụ muốn tới cùng giờ địa phương vào ngày đầu tháng kế:

~~~java
ZoneId zone = ZoneId.of("Europe/Paris");
ZonedDateTime start = LocalDateTime.of(2026, 1, 31, 9, 0)
        .atZone(zone);

ZonedDateTime nextMonthDate = start.plusMonths(1);
~~~

Java điều chỉnh ngày 31 xuống ngày cuối hợp lệ của tháng đích nếu cần. Nếu chỉ yêu cầu “sau đúng 30 ngày”, cần xác định một instant và cộng `Duration.ofDays(30)`. Hai kết quả có thể trùng nhau ở một số trường hợp nhưng không có bảo đảm chung.

Ngày giờ hợp lệ của vùng còn phụ thuộc quy tắc lịch sử và DST. Nếu giờ đích rơi vào gap hoặc overlap, `ZonedDateTime` áp dụng quy tắc xử lý vùng mặc định; ứng dụng đặt lịch quan trọng nên kiểm tra chính sách và có thể cần `ZoneRules.getValidOffsets` để phát hiện giờ bị bỏ qua hay lặp.

## 6. `Period` có thể giữ thành phần lịch, không giữ một thời lượng cố định

`Period` biểu diễn năm, tháng và ngày thành các thành phần. Ví dụ `Period.of(1, 2, 3)` biểu diễn 1 năm, 2 tháng và 3 ngày. Nó không cung cấp tổng số giây cố định vì khi áp vào lịch, số ngày phụ thuộc ngày bắt đầu và quy tắc lịch.

~~~java
Period p = Period.of(1, 2, 3);
System.out.println(p); // P1Y2M3D
~~~

Ngược lại, `Duration` luôn biểu diễn lượng giây/nano đã chuẩn hóa, không có thành phần “tháng” hoặc “năm”. Một tháng có thể dài 28–31 ngày; một năm theo lịch có thể dài 365 hoặc 366 ngày.

Không so sánh bằng cách giả định một tháng luôn 30 ngày hoặc một năm luôn 365 ngày. Nếu cần biết khoảng cách thực giữa hai ngày giờ, áp dụng quy tắc múi giờ để có các `Instant` rồi dùng `Duration.between`. Nếu cần chênh lệch lịch như “còn 2 tháng và 3 ngày”, dùng phép tính phù hợp trên ngày lịch.

## 7. Khi nào dùng kiểu nào?

| Yêu cầu nghiệp vụ | Cách diễn đạt phù hợp |
| --- | --- |
| OTP hết hạn sau đúng 5 phút | `Instant` deadline = now + `Duration.ofMinutes(5)` |
| Nhắc lại lúc 09:00 ngày mai ở một địa phương | `ZonedDateTime.plusDays(1)` hoặc quy tắc lịch địa phương |
| Tính ngày đáo hạn sau một tháng | `LocalDate.plusMonths(1)` / `Period.ofMonths(1)` |
| Tác vụ chạy lại sau đúng 24 giờ | `Duration.ofHours(24)` trên instant hoặc thời lượng monotonic phù hợp |
| Lịch họp 09:00 hằng tuần ở New York | Quy tắc lặp + `ZoneId`, giải quyết mỗi lần xảy ra |
| Thời gian chạy hàm | Hiệu `System.nanoTime()` hoặc `Duration` từ hiệu đo |
| Tính từ lúc sự kiện bắt đầu đến khi kết thúc | `Duration.between(startInstant, endInstant)` |
| Sinh nhật năm tiếp theo | Ngày lịch và quy tắc cho 29/02, không phải lượng giây cố định |

**Không phải lúc nào nên chọn “một lớp” đơn lẻ.** Một lịch hẹn lặp tại địa phương thường cần `LocalTime`, quy tắc lặp, `ZoneId` và chính sách DST. Một lần hẹn sau khi đã được giải quyết có thể cần `Instant` để phát thông báo chính xác. Phần độ dài giữa hai instant lại dùng `Duration`.

## 8. Ví dụ Java 17+ hoàn chỉnh

Chương trình dùng ngày giờ cố định để minh họa: so sánh cộng một ngày lịch với cộng 24 giờ qua DST; so sánh cộng tháng khi ngày cuối tháng không tồn tại; và tính độ dài thực giữa hai instant. Không gọi đồng hồ hệ thống nên kết quả dễ đối chiếu.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class PeriodVsDurationDemo {
    public static void main(String[] args) {
        ZoneId ny = ZoneId.of("America/New_York");
        ZonedDateTime start = LocalDateTime
                .of(2026, 3, 7, 12, 0).atZone(ny);

        ZonedDateTime plusCalendarDay = start.plus(Period.ofDays(1));
        ZonedDateTime plus24Hours = start.plus(Duration.ofHours(24));

        System.out.println("start=" + start);
        System.out.println("plusCalendarDay=" + plusCalendarDay);
        System.out.println("plus24Hours=" + plus24Hours);
        System.out.println("elapsedHours=" + Duration.between(
                start.toInstant(), plusCalendarDay.toInstant()).toHours());

        LocalDate jan31 = LocalDate.of(2025, 1, 31);
        System.out.println("plusOneMonth=" + jan31.plus(Period.ofMonths(1)));
        System.out.println("plusTwoMonths=" + jan31.plusMonths(2));
        System.out.println("twoSteps=" + jan31.plusMonths(1).plusMonths(1));

        Instant a = Instant.parse("2026-05-01T10:00:00Z");
        Instant b = Instant.parse("2026-05-01T10:03:40Z");
        System.out.println("elapsed=" + Duration.between(a, b));
        System.out.println("period=" + Period.of(1, 2, 3));
    }
}
~~~

Lưu file `PeriodVsDurationDemo.java`, sau đó chạy:

~~~bash
javac PeriodVsDurationDemo.java
java PeriodVsDurationDemo
~~~

Đầu ra chuẩn theo dữ liệu timezone New York cho ngày ví dụ:

~~~text
start=2026-03-07T12:00-05:00[America/New_York]
plusCalendarDay=2026-03-08T12:00-04:00[America/New_York]
plus24Hours=2026-03-08T13:00-04:00[America/New_York]
elapsedHours=23
plusOneMonth=2025-02-28
plusTwoMonths=2025-03-31
twoSteps=2025-03-28
elapsed=PT3M40S
period=P1Y2M3D
~~~

Giải thích:

1. Cộng một ngày lịch giữ 12:00 địa phương và chỉ đi qua 23 giờ thật vì đồng hồ tiến khi bắt đầu DST.
2. Cộng 24 giờ giữ khoảng thời gian, nên giờ địa phương đích là 13:00.
3. Cộng hai tháng trực tiếp từ ngày 31/01 tính theo tháng đích, còn cộng một tháng hai lần kế thừa ngày 28 sau khi tháng 2 đã điều chỉnh.
4. `Duration.between` trả `PT3M40S` (220 giây), trong khi `Period.of(1,2,3)` giữ quy tắc năm/tháng/ngày.

## 9. Lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi `Duration.ofDays(1)` tương đương ngày mai | Có thể lệch giờ khi qua DST | Dùng phép lịch trên `ZonedDateTime` |
| Coi `Period.ofMonths(1)` bằng 30 ngày | Sai với tháng ngắn/dài | Dùng `Period` hoặc `plusMonths` |
| Cộng tháng nhiều lần trên ngày đã bị điều chỉnh mà quên ngày gốc | Lịch định kỳ trôi từ ngày 31 về 28 | Tính từng tháng từ quy tắc gốc |
| Dùng `LocalDate` để đo thời lượng thực | Ngày không có giờ/zone | Chọn hai `Instant` và dùng `Duration.between` |
| So hai `LocalDateTime` ở vùng DST để tính giờ trôi | Bỏ qua offset đổi | Chuyển sang instant theo zone rồi tính Duration |
| Nghĩ `Period` lưu giây/nano | Không thể suy ra thời lượng cố định | Dùng `Duration` nếu đơn vị là thời gian trôi |
| Dùng `Duration` cho lịch tái diễn địa phương | Mốc dần lệch giờ đồng hồ địa phương | Giữ quy tắc lịch và `ZoneId` |
| Không định nghĩa chính sách cuối tháng | Ngày 31 hoặc 29/02 có kết quả không như mong đợi | Quy định rõ kẹp ngày, báo lỗi hay ngày cuối kỳ |
| Tự mặc định DST giống nhau ở mọi zone | Lịch chạy sai vùng | Dùng `ZoneId` khu vực và dữ liệu quy tắc |
| Chỉ kiểm thử ngày thông thường | Bỏ sót DST và cuối tháng | Test ngày đổi DST, năm nhuận, cuối tháng |

## 10. Quy trình quyết định

Trước khi triển khai yêu cầu thời gian, hãy trả lời lần lượt:

1. **Đơn vị là thời gian trôi hay lịch?** “Sau 24 giờ” → Duration; “ngày kế tiếp” → phép toán lịch.
2. **Có múi giờ địa phương không?** Nếu lịch thuộc một vùng, dùng `ZoneId` và các kiểu ngày giờ phù hợp.
3. **Có chuyển DST trong khoảng xét không?** Nếu có, số giờ thực giữa hai giờ đồng hồ có thể khác kỳ vọng.
4. **Có ranh giới cuối tháng/năm nhuận không?** Xác định chính sách cho ngày không tồn tại.
5. **Có cần bảo toàn một instant đã chốt không?** Dùng `Instant`; đừng chỉ lưu giờ địa phương nếu cần một sự kiện tuyệt đối.
6. **Cách test có bao gồm biên không?** Kiểm tra trước/đúng/sau deadline, ngày 28–31, 29/02, gap/overlap và kết quả round-trip.

## 11. Bài tập tự kiểm tra

1. So sánh `Period.ofDays(1)` và `Duration.ofDays(1)`. API nào diễn đạt chính xác “sau 24 giờ”?
2. Với New York ngày 07/03/2026 lúc 12:00, dự đoán kết quả cộng một ngày lịch và 24 giờ. Giải thích chênh lệch.
3. Từ `2025-01-31`, so sánh `plusMonths(2)` với `plusMonths(1).plusMonths(1)`. Tại sao kết quả khác nhau?
4. Viết một hàm tính tháng kế tiếp với chính sách “ngày 30, nếu thiếu thì dùng ngày cuối tháng”; đảm bảo tháng sau trở lại ngày 30.
5. Vì sao không thể lấy `Period.getDays()` làm tổng số ngày giữa hai ngày qua nhiều tháng? Khi cần tổng ngày, hãy tìm API phù hợp.
6. Một timeout cần hết hạn đúng sau 600 giây thực, trong khi một báo cáo cần chạy lúc 09:00 mỗi ngày ở Paris. Hãy thiết kế kiểu dữ liệu và phép toán cho mỗi yêu cầu.
7. Viết test cho ngày bắt đầu/kết thúc DST, ngày cuối tháng, năm nhuận và biên hạn hết hạn.

**Ghi nhớ:** `Duration` mô tả **lượng thời gian cố định** bằng giây/nano giây; `Period` mô tả **khoảng theo lịch**. Qua DST, một ngày lịch có thể dài 23 hoặc 25 giờ; qua cuối tháng, cộng một tháng có thể điều chỉnh ngày. Chọn API theo ý nghĩa “bao lâu” hay “tới ngày/giờ nào”, và test các ranh giới mà lịch thực tế tạo ra.