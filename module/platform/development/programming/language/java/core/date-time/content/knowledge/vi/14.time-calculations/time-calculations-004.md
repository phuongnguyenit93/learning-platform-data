# Thứ tự cộng năm, tháng và ngày có thể làm đổi kết quả trong Java

Trong Java, các phép toán lịch **plusYears**, **plusMonths** và **plusDays** không phải lúc nào cũng có thể đổi thứ tự mà vẫn giữ nguyên kết quả. Nguyên nhân chính là tháng có độ dài khác nhau và ngày đích có thể không tồn tại. Khi cộng năm hoặc tháng, Java điều chỉnh ngày không hợp lệ về **ngày cuối cùng hợp lệ của tháng đích**. Phép toán tiếp theo sử dụng ngày đã điều chỉnh đó, vì vậy kết quả có thể phụ thuộc vào thứ tự.

Ví dụ, từ **2024-01-30**, cộng một tháng rồi một ngày cho **2024-03-01**; cộng một ngày rồi một tháng cho **2024-02-29**. Cả hai đều đúng với chuỗi phép toán đã viết, nhưng chúng diễn đạt các quy tắc nghiệp vụ khác nhau.

Bài này dùng Java 17+ để giải thích điều chỉnh cuối tháng, ngày nhuận, phép cộng dồn, khác biệt giữa Period gộp và các lời gọi tuần tự, cùng cách thiết kế và kiểm thử quy tắc gia hạn.

## 1. Cơ chế điều chỉnh ngày cuối tháng

Một LocalDate chứa năm, tháng và ngày. Khi gọi plusMonths hoặc plusYears, Java xác định tháng/năm đích rồi kiểm tra ngày có hợp lệ hay không. Nếu ngày hiện tại vượt quá số ngày của tháng đích, ngày được điều chỉnh về ngày cuối tháng.

~~~java
LocalDate date = LocalDate.of(2024, 1, 30);
LocalDate february = date.plusMonths(1);
System.out.println(february);
~~~

Đoạn minh họa sẽ in:

~~~text
2024-02-29
~~~

Năm 2024 là năm nhuận nên tháng 02 có 29 ngày. Ngày 30/02 không tồn tại; Java điều chỉnh xuống 29/02. Tương tự, 31/01 cộng một tháng cũng trở thành 29/02/2024.

Phép toán không giữ một “ngày mong muốn” ẩn bên trong đối tượng. Sau khi điều chỉnh, LocalDate thực sự mang ngày mới; các phép toán tiếp theo bắt đầu từ giá trị đó.

## 2. Đổi thứ tự cộng tháng và ngày

Xét hai biểu thức:

~~~java
LocalDate d = LocalDate.of(2024, 1, 30);

LocalDate monthThenDay = d.plusMonths(1).plusDays(1);
LocalDate dayThenMonth = d.plusDays(1).plusMonths(1);
~~~

| Bước | Cộng tháng rồi ngày | Cộng ngày rồi tháng |
|---|---|---|
| Ban đầu | 2024-01-30 | 2024-01-30 |
| Phép thứ nhất | +1 tháng → 2024-02-29 | +1 ngày → 2024-01-31 |
| Phép thứ hai | +1 ngày → 2024-03-01 | +1 tháng → 2024-02-29 |

Kết quả:

~~~text
monthThenDay=2024-03-01
dayThenMonth=2024-02-29
~~~

Sự khác biệt đến từ bước điều chỉnh cuối tháng ở cột thứ hai: ngày 31/01 cộng một tháng trở thành 29/02. Nếu yêu cầu là “sau một tháng rồi thêm một ngày”, phải giữ thứ tự thứ nhất; nếu nghiệp vụ nói “sau một ngày rồi cộng một tháng”, dùng thứ tự thứ hai.

## 3. Đổi thứ tự cộng năm và tháng khi có ngày nhuận

Ngày **29/02/2024** là trường hợp dễ thấy:

~~~java
LocalDate leapDay = LocalDate.of(2024, 2, 29);

LocalDate yearThenMonth =
        leapDay.plusYears(1).plusMonths(1);
LocalDate monthThenYear =
        leapDay.plusMonths(1).plusYears(1);
~~~

Khi cộng năm trước, ngày 29/02/2024 được điều chỉnh thành 28/02/2025 vì năm 2025 không nhuận. Cộng tháng sau sẽ cho 28/03/2025.

Khi cộng tháng trước, ngày thành 29/03/2024; cộng năm sau thành 29/03/2025.

~~~text
yearThenMonth=2025-03-28
monthThenYear=2025-03-29
~~~

Không thay plusYears bằng cộng cố định 365 ngày nếu ý nghĩa nghiệp vụ là “thêm một năm lịch”. Năm nhuận và độ dài các tháng làm hai cách diễn đạt khác nhau.

## 4. Chương trình Java 17+ chạy được

Tạo tệp **DateAdditionOrderDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Period;

public class DateAdditionOrderDemo {
    public static void main(String[] args) {
        LocalDate d = LocalDate.of(2024, 1, 30);

        System.out.println("monthThenDay=" +
                d.plusMonths(1).plusDays(1));
        System.out.println("dayThenMonth=" +
                d.plusDays(1).plusMonths(1));

        LocalDate leap = LocalDate.of(2024, 2, 29);
        System.out.println("yearThenMonth=" +
                leap.plusYears(1).plusMonths(1));
        System.out.println("monthThenYear=" +
                leap.plusMonths(1).plusYears(1));

        System.out.println("period13Months=" +
                leap.plus(Period.of(1, 1, 0)));
        System.out.println("periodSeparate=" +
                leap.plus(Period.ofYears(1)).plus(Period.ofMonths(1)));

        System.out.println("periodYearMonthDay=" +
                leap.plus(Period.of(1, 1, 1)));
        System.out.println("sequentialYearMonthDay=" +
                leap.plusYears(1).plusMonths(1).plusDays(1));

        LocalDateTime dt = leap.atTime(10, 30);
        System.out.println("dateTimePeriod=" +
                dt.plus(Period.of(1, 1, 0)));
        System.out.println("dateTimeSequential=" +
                dt.plusYears(1).plusMonths(1));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DateAdditionOrderDemo.java
java DateAdditionOrderDemo
~~~

Stdout chính xác:

~~~text
monthThenDay=2024-03-01
dayThenMonth=2024-02-29
yearThenMonth=2025-03-28
monthThenYear=2025-03-29
period13Months=2025-03-29
periodSeparate=2025-03-28
periodYearMonthDay=2025-03-30
sequentialYearMonthDay=2025-03-29
dateTimePeriod=2025-03-29T10:30
dateTimeSequential=2025-03-28T10:30
~~~

Các kết quả được tính theo quy tắc của API java.time. Phần tiếp theo giải thích tại sao Period gộp và gọi phương thức tuần tự có thể khác nhau.

## 5. Period gộp không luôn giống các phép cộng tuần tự

**Period.of(years, months, days)** biểu diễn lượng thời gian lịch gồm năm, tháng, ngày. Khi được cộng vào LocalDate hoặc LocalDateTime, thành phần năm và tháng được kết hợp thành tổng số tháng trước khi thành phần ngày được áp dụng.

Với ngày 29/02/2024:

~~~java
LocalDate leap = LocalDate.of(2024, 2, 29);

LocalDate combined = leap.plus(Period.of(1, 1, 0));
LocalDate sequential = leap.plusYears(1).plusMonths(1);
~~~

Kết quả là:

~~~text
combined=2025-03-29
sequential=2025-03-28
~~~

Lý do:

- **Period.of(1, 1, 0)** biểu diễn tổng cộng 13 tháng. Tính trực tiếp 13 tháng từ 29/02/2024 đến 29/03/2025, vì ngày 29 tồn tại trong tháng 03/2025.
- **plusYears(1)** trước tiên chuyển 29/02/2024 thành 28/02/2025.
- **plusMonths(1)** sau đó bắt đầu từ 28/02/2025 nên cho 28/03/2025.

Nếu Period có cả ngày, thứ tự tương đương là xử lý số tháng tổng rồi cộng ngày:

~~~java
LocalDate combined = leap.plus(Period.of(1, 1, 1));
LocalDate sequential =
        leap.plusYears(1).plusMonths(1).plusDays(1);
~~~

Kết quả tương ứng:

~~~text
combined=2025-03-30
sequential=2025-03-29
~~~

Không nên tự thay một Period gộp bằng một chuỗi plusYears/plusMonths/plusDays để rút ngắn hoặc tái cấu trúc code nếu chưa xác minh kết quả. Đó có thể là thay đổi ngữ nghĩa, đặc biệt đối với hạn hợp đồng hoặc ngày thanh toán.

## 6. Cộng nhiều tháng liên tiếp khác cộng một lần nhiều tháng

Một lỗi dễ gặp trong gia hạn định kỳ xuất hiện ở ngày 31:

~~~java
LocalDate start = LocalDate.of(2024, 1, 31);

LocalDate twoSteps = start.plusMonths(1).plusMonths(1);
LocalDate oneStep = start.plusMonths(2);
~~~

Kết quả:

~~~text
twoSteps=2024-03-29
oneStep=2024-03-31
~~~

Cách cộng hai bước diễn tiến:

1. 31/01 cộng một tháng → 29/02/2024.
2. 29/02 cộng một tháng → 29/03/2024.

Cách cộng trực tiếp hai tháng tính từ 31/01. Tháng 03/2024 có ngày 31, vì vậy kết quả là 31/03.

Điều này cho thấy chuỗi cộng dồn có thể làm **ngày gia hạn trôi khỏi ngày gốc**. Nếu hệ thống muốn mỗi kỳ tính từ ngày hợp đồng ban đầu, hãy lưu ngày neo (anchor) và tính mỗi kỳ từ ngày gốc thay vì luôn cộng tháng lên kết quả kỳ trước.

## 7. Xác định chính sách cuối tháng trước khi viết code

Các cụm từ nghiệp vụ có thể mang ý nghĩa khác nhau:

- **Cộng một tháng từ ngày hiện tại:** gọi plusMonths(1) trên ngày hiện tại; Java điều chỉnh nếu ngày không tồn tại trong tháng đích.
- **Giữ ngày gốc nếu tháng đích có ngày đó:** tính kỳ N từ ngày neo ban đầu, ví dụ anchor.plusMonths(N).
- **Ngày cuối tháng tiếp theo:** dùng YearMonth để diễn đạt rõ chính sách cuối tháng.
- **Mỗi kỳ cộng dồn từ kỳ gần nhất:** cộng trên kết quả đã điều chỉnh của kỳ trước; ngày có thể trôi dần.

Ví dụ lấy ngày cuối tháng tiếp theo:

~~~java
import java.time.LocalDate;
import java.time.YearMonth;

LocalDate endOfJanuary = LocalDate.of(2024, 1, 31);
LocalDate nextMonthEnd =
        YearMonth.from(endOfJanuary).plusMonths(1).atEndOfMonth();
~~~

Kết quả là **2024-02-29**. Đây là quy tắc **ngày cuối tháng**, khác với giữ một ngày số cụ thể và điều chỉnh khi cần.

Đối với hợp đồng, nên định nghĩa rõ những trường hợp như: “gia hạn vào cùng số ngày; nếu tháng không có ngày đó thì dùng ngày cuối tháng”, hoặc “gia hạn vào ngày cuối tháng của từng kỳ”. Không có một quy tắc mặc định phù hợp mọi nghiệp vụ.

## 8. LocalDateTime cũng chịu tác động của thứ tự

LocalDateTime dùng cùng quy tắc lịch để điều chỉnh ngày, đồng thời giữ giờ/phút/giây/nano giây:

~~~java
LocalDateTime meeting =
        LocalDate.of(2024, 2, 29).atTime(10, 30);

LocalDateTime first = meeting.plusYears(1).plusMonths(1);
LocalDateTime second = meeting.plusMonths(1).plusYears(1);
~~~

Kết quả:

~~~text
first=2025-03-28T10:30
second=2025-03-29T10:30
~~~

Giờ 10:30 vẫn được giữ nguyên, nhưng ngày thay đổi vì phép cộng năm đầu tiên đã điều chỉnh 29/02 thành 28/02. Điều này quan trọng với lịch hẹn, thời hạn thanh toán hay ngày nhắc việc.

LocalDateTime không có ZoneId. Nó không tự xác định giờ đó có tồn tại tại một vùng DST hay không. Nếu nghiệp vụ cần một thời điểm thực tế, phải bổ sung ZoneId/offset và áp dụng chính sách cho giờ gap hoặc overlap.

## 9. Phân biệt phép toán lịch, Duration và Period

| Nhu cầu | Phù hợp | Lưu ý |
|---|---|---|
| Thêm một tháng lịch | LocalDate.plusMonths(1) hoặc Period | Ngày cuối tháng có thể được điều chỉnh |
| Thêm một năm lịch | LocalDate.plusYears(1) | 29/02 có thể thành 28/02 trong năm không nhuận |
| Thêm 48 giờ thực sự | Instant.plus(Duration.ofHours(48)) | Là 48 giờ theo trục thời gian |
| Cùng giờ ngày kế tiếp tại vùng có DST | Phép toán lịch với ZonedDateTime | Không luôn bằng cộng 24 giờ |
| Lấy ngày cuối tháng sau | YearMonth.plusMonths(1).atEndOfMonth() | Diễn đạt chính sách cuối tháng |
| Cộng 1 năm, 1 tháng, 1 ngày như một khoảng lịch gộp | Period.of(1, 1, 1) | Có thể khác chuỗi phép cộng tuần tự |

**Duration** đo lượng thời gian theo giây/nano giây; **Period** biểu diễn năm/tháng/ngày lịch. Không thay Period bằng Duration 30 ngày chỉ để tránh vấn đề điều chỉnh ngày: hai cách có ngữ nghĩa khác nhau.

## 10. Cách tổ chức hàm nghiệp vụ và kiểm thử

Đối với quy tắc lịch quan trọng, tránh rải các chuỗi cộng nhiều bước ở nhiều nơi. Hãy đưa quy tắc vào một hàm có tên rõ ràng, ví dụ **nextMonthlyDueDate** hoặc **endOfNextMonth**. Tên hàm nên thể hiện chính sách mà nghiệp vụ mong muốn.

Các test cần bao gồm:

1. Ngày bình thường ở giữa tháng.
2. Ngày 28, 29, 30 và 31.
3. Ngày 29/02 trong năm nhuận.
4. Cộng năm rồi tháng so với tháng rồi năm.
5. Cộng tháng rồi ngày so với ngày rồi tháng.
6. Cộng hai tháng một lần so với cộng mỗi tháng một lần.
7. Period gộp so với các lời gọi tuần tự.
8. Chuyển cuối năm và chuyển sang tháng 02.
9. LocalDateTime có giờ/phút/giây/nano.
10. Nếu dùng ZoneId: DST gap/overlap và chính sách được chọn.

Không chỉ kiểm thử ngày giữa tháng vì những ngày đó thường không kích hoạt việc điều chỉnh cuối tháng. Hãy viết kết quả mong đợi dựa theo **quy tắc nghiệp vụ**, không dựa vào việc giữ nguyên hành vi tình cờ của implementation cũ.

## 11. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Đổi thứ tự cộng tháng/ngày mà không kiểm thử | Kết quả khác quanh cuối tháng | Diễn đạt đúng thứ tự của yêu cầu |
| Cộng năm vào 29/02 rồi giả định vẫn giữ ngày 29 | Ngày không tồn tại trong năm thường | Chọn chính sách ngày nhuận |
| Cộng tháng lặp lại từ ngày đã được điều chỉnh | Ngày gia hạn trôi khỏi mốc gốc | Tính từ anchor hoặc dùng quy tắc cuối tháng |
| Thay plusYears rồi plusMonths bằng Period gộp | Có thể đổi kết quả | Kiểm tra các giá trị biên trước khi thay |
| Xem một tháng bằng 30 ngày | Lệch hạn theo lịch | Dùng phương thức lịch/Period |
| Dùng 24 giờ thay cho ngày địa phương ở DST | Giờ địa phương có thể lệch | Phân biệt Duration với phép toán lịch |
| Kiểm thử chỉ giữa tháng | Không phát hiện ngày cuối tháng hoặc ngày nhuận | Thêm test ngày 28–31 và 29/02 |
| Tự cộng ngày cuối tháng bằng nhiều nhánh rải rác | Chính sách không nhất quán | Tạo hàm nghiệp vụ dùng chung |
| Dùng LocalDateTime để tính thời gian thực ở vùng DST | Thiếu thông tin vùng/offset | Quy đổi hai mốc sang Instant khi cần đo thời lượng thực |
| Dùng == để so sánh LocalDate | So sánh tham chiếu thay vì giá trị | Dùng equals() |

## 12. Câu hỏi tự kiểm tra

**1. 2024-01-30 cộng một tháng rồi một ngày cho kết quả nào?**  
2024-03-01.

**2. 2024-01-30 cộng một ngày rồi một tháng?**  
2024-02-29.

**3. Vì sao cộng năm rồi tháng từ 29/02/2024 khác với tháng rồi năm?**  
Cộng năm trước buộc ngày thành 28/02/2025; phép cộng tháng tiếp theo bắt đầu từ ngày 28. Đảo thứ tự thì cộng tháng đầu tiên tạo 29/03/2024.

**4. Vì sao cộng một tháng hai lần từ 31/01 khác cộng hai tháng một lần?**  
Phép cộng lần đầu điều chỉnh 31/01 thành 29/02; lần hai dùng ngày 29 làm đầu vào. Cộng hai tháng một lần tính trực tiếp từ ngày 31 ban đầu.

**5. Period.of(1, 1, 0) có luôn giống plusYears(1).plusMonths(1) không?**  
Không. Period gộp năm và tháng thành tổng số tháng trước khi cộng; phép tuần tự có bước điều chỉnh ngày giữa hai lần gọi.

**6. Nên dùng gì cho yêu cầu “sau đúng 48 giờ”?**  
Duration 48 giờ cộng vào một Instant phù hợp. Với “cùng giờ ngày mai tại vùng có DST”, cần phép toán lịch cùng ZoneId.

**Ghi nhớ:** Thứ tự cộng năm, tháng và ngày có thể làm thay đổi ngày trung gian; khi ngày đích không tồn tại, Java điều chỉnh về cuối tháng. Những điều chỉnh này ảnh hưởng các bước tiếp theo và có thể khiến Period gộp khác phép cộng tuần tự. Hãy diễn đạt chính xác quy tắc nghiệp vụ, kiểm thử ngày cuối tháng/ngày nhuận và chọn chiến lược tính kỳ từ ngày gốc hay từ kỳ trước một cách tường minh.
