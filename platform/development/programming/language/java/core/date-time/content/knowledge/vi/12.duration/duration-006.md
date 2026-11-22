# Phân biệt tổng số đơn vị với các phần toHoursPart() và toMinutesPart() của Duration

`java.time.Duration` biểu diễn một **khoảng thời gian đã trôi qua**, theo giây và nano giây. Khi đọc thời lượng, Java có hai nhóm phương thức quan trọng:

- **Tổng số đơn vị:** `toHours()`, `toMinutes()`, `toSeconds()`, `toMillis()`. Các phương thức này trả số đơn vị đầy đủ trong toàn bộ duration.
- **Phần thành phần:** `toHoursPart()`, `toMinutesPart()`, `toSecondsPart()`, `toMillisPart()`. Chúng dùng để tách duration thành các phần để hiển thị.

Ví dụ, **52 giờ 5 phút 7,345 giây** tương ứng 2 ngày, 4 giờ, 5 phút, 7 giây và 345 mili giây. Vì thế `toHours()` trả **52**, trong khi `toHoursPart()` trả **4**. Tương tự, `toMinutes()` trả **3125**, còn `toMinutesPart()` trả **5**.

**Total là tổng theo một đơn vị; Part là thành phần dư trong phép phân rã.** Nếu dùng nhầm, báo cáo 52 giờ có thể hiển thị thành 4 giờ, hoặc tổng 125 phút thành 5 phút.

## 1. Duration lưu gì?

`Duration` đo khoảng cách giữa hai thời điểm, phù hợp cho thời gian chờ, thời lượng tác vụ, timeout và SLA. Ví dụ:

~~~java
Duration twoHours = Duration.ofHours(2);
Duration meeting = Duration.ofMinutes(125);
Duration elapsed = Duration.between(start, end);
~~~

Đây là các biểu thức minh họa; cần import `java.time.Duration` và khai báo `start`, `end` nếu dùng `between`. `Duration` là kiểu bất biến: phương thức như `plusMinutes(5)` tạo kết quả mới, không sửa đối tượng ban đầu.

Một ngày của `Duration` được định nghĩa đúng **24 giờ = 86.400 giây**. `Duration.ofDays(1)` là khoảng 24 giờ, không phải đảm bảo mọi ngày lịch địa phương dài 24 giờ. Nếu bài toán hỏi “đầu ngày mai theo vùng”, dùng `LocalDate` và `ZoneId` thay vì đổi ngày lịch thành 24 giờ cố định.

## 2. Total và Part: khác nhau ở đâu?

Xét:

~~~text
52 giờ 5 phút 7,345 giây
= 2 ngày + 4 giờ + 5 phút + 7 giây + 345 mili giây
= 187.507,345 giây
~~~

| Phương thức | Kết quả | Ý nghĩa |
|---|---:|---|
| `toDays()` | 2 | Tổng số ngày tiêu chuẩn 24 giờ đầy đủ. |
| `toHours()` | 52 | Tổng số giờ đầy đủ của cả duration. |
| `toMinutes()` | 3125 | Tổng số phút đầy đủ. |
| `toSeconds()` | 187507 | Tổng số giây đầy đủ. |
| `toMillis()` | 187507345 | Tổng mili giây, nếu không vượt miền `long`. |
| `toDaysPart()` | 2 | Theo API, tương đương `toDays()`. |
| `toHoursPart()` | 4 | Phần giờ sau khi tách ngày. |
| `toMinutesPart()` | 5 | Phần phút sau khi tách giờ. |
| `toSecondsPart()` | 7 | Phần giây sau khi tách phút. |
| `toMillisPart()` | 345 | Phần mili giây trong giây. |
| `toNanosPart()` | 345000000 | Phần nano giây trong giây. |

Đối với duration dương, phép phân rã tương tự:

~~~text
52 giờ    = 2 × 24 giờ + 4 giờ
3125 phút = 52 × 60 phút + 5 phút
187507 giây = 3125 × 60 giây + 7 giây
~~~

`toHoursPart()` không phải phép làm tròn. Nó cho số giờ dư sau khi lấy tổng giờ chia cho 24. `toMinutesPart()` tương tự cho phút dư sau khi chia tổng phút cho 60.

Điểm dễ nhầm là `toDaysPart()` có tên “Part” nhưng không phải ngày dư dưới một đơn vị lớn hơn. Theo định nghĩa API, nó trả số ngày bằng cách chia tổng giây cho 86.400, tức tương đương `toDays()`.

## 3. Ví dụ Java 17+ chạy được

Lưu vào `DurationPartsDemo.java`:

~~~java
import java.time.Duration;

public class DurationPartsDemo {
    public static void main(String[] args) {
        Duration duration = Duration.ofHours(50)
                .plusMinutes(125)
                .plusSeconds(7)
                .plusMillis(345);

        System.out.println("Duration: " + duration);
        System.out.println("Total days: " + duration.toDays());
        System.out.println("Total hours: " + duration.toHours());
        System.out.println("Total minutes: " + duration.toMinutes());
        System.out.println("Total seconds: " + duration.toSeconds());
        System.out.println("Total millis: " + duration.toMillis());

        System.out.println("Days part: " + duration.toDaysPart());
        System.out.println("Hours part: " + duration.toHoursPart());
        System.out.println("Minutes part: " + duration.toMinutesPart());
        System.out.println("Seconds part: " + duration.toSecondsPart());
        System.out.println("Millis part: " + duration.toMillisPart());
        System.out.println("Nanos part: " + duration.toNanosPart());
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac DurationPartsDemo.java
java DurationPartsDemo
~~~

Stdout:

~~~text
Duration: PT52H5M7.345S
Total days: 2
Total hours: 52
Total minutes: 3125
Total seconds: 187507
Total millis: 187507345
Days part: 2
Hours part: 4
Minutes part: 5
Seconds part: 7
Millis part: 345
Nanos part: 345000000
~~~

Cặp kết quả có ý nghĩa như sau:

- **52 giờ tổng vs 4 giờ phần:** 52 = 2 × 24 + 4.
- **3125 phút tổng vs 5 phút phần:** 3125 = 52 × 60 + 5.
- **187507 giây tổng vs 7 giây phần:** 187507 = 3125 × 60 + 7.
- **187507345 mili giây tổng vs 345 mili giây phần:** total chuyển cả duration sang ms; Part chỉ lấy phần ms trong giây.
- **345000000 nano giây phần:** không phải tổng nano giây của thời lượng. `toNanos()` mới chuyển cả duration thành tổng nano giây, nhưng có thể tràn `long` với giá trị rất lớn.

Không cộng `toHours()` với `toMinutes()` để tạo chuỗi phân rã. Cả hai đo toàn bộ duration bằng các đơn vị khác nhau, nên phép cộng không có ý nghĩa.

## 4. Chọn API theo câu hỏi nghiệp vụ

| Câu hỏi | Phương thức phù hợp |
|---|---|
| Tổng thời gian chờ theo giờ? | `toHours()` |
| Sau khi tách ngày còn bao nhiêu giờ? | `toHoursPart()` |
| Tổng số phút một cuộc họp? | `toMinutes()` |
| Phần phút để hiển thị thời lượng? | `toMinutesPart()` |
| Tổng số giây đầy đủ? | `toSeconds()` |
| Phần giây trong định dạng? | `toSecondsPart()` |
| Tổng mili giây cho API? | `toMillis()` |
| Phần mili giây trong giây? | `toMillisPart()` |

### Ví dụ 119 phút

~~~java
Duration duration = Duration.ofMinutes(119);
System.out.println(duration.toHours());
System.out.println(duration.toHoursPart());
System.out.println(duration.toMinutes());
System.out.println(duration.toMinutesPart());
~~~

Đây là mã minh họa, cần import `Duration` và đặt trong phương thức/class. Kết quả:

~~~text
1
1
119
59
~~~

119 phút gồm một giờ và 59 phút. `toHours()` trả một giờ tổng; `toHoursPart()` cũng trả một giờ vì chưa đủ một ngày; `toMinutes()` trả 119 phút tổng và `toMinutesPart()` trả 59 phút dư.

### Hiển thị ngày, giờ, phút, giây

Với duration không âm, các phần có thể giúp xây dựng nhãn:

~~~java
String label = duration.toDaysPart() + "d "
        + String.format("%02dh %02dm %02ds",
                duration.toHoursPart(),
                duration.toMinutesPart(),
                duration.toSecondsPart());
~~~

Đây là mã minh họa cần biến `duration`. Với 52 giờ 5 phút 7 giây, nhãn là `2d 04h 05m 07s`. Cách format này giả định thời lượng không âm và không hiển thị mili/nano; định nghĩa riêng nếu phải hỗ trợ dấu âm hoặc phần lẻ.

## 5. Total không làm tròn

Các phương thức tổng trả số đơn vị đầy đủ, không làm tròn đến đơn vị gần nhất. Với 119 phút, `toHours()` là 1, không phải 2; `toMinutes()` là 119. Với duration 1,9 giây, `toSeconds()` trả 1 giây đầy đủ.

`toMillis()` giữ đến mili giây nhưng loại bỏ phần dưới mili giây. Nó không tự làm tròn tới mili giây gần nhất. Nếu cần làm tròn lên, xuống hoặc tới gần nhất, chọn rõ quy tắc và triển khai riêng.

## 6. Duration âm

`Duration.between(start, end)` có thể trả duration âm nếu end trước start. Ví dụ:

~~~java
Duration duration = Duration.ofMinutes(-125);
System.out.println("Total hours: " + duration.toHours());
System.out.println("Total minutes: " + duration.toMinutes());
System.out.println("Hours part: " + duration.toHoursPart());
System.out.println("Minutes part: " + duration.toMinutesPart());
~~~

Đây là mã minh họa, cần import `Duration` và đặt trong class/phương thức. Kết quả:

~~~text
Total hours: -2
Total minutes: -125
Hours part: -2
Minutes part: -5
~~~

Phép chia số nguyên được dùng để lấy đơn vị đầy đủ, vì vậy tổng giờ của -125 phút là -2 và phần phút là -5. Các Part giờ/phút/giây có thể âm. Khi hiển thị duration âm, cần chính sách dấu riêng; đừng ghép số như thể chúng là các thành phần dương thông thường.

`Duration` lưu giây cùng trường nano giây đã chuẩn hóa trong khoảng 0 đến 999.999.999. Một duration âm một nano giây có thể được biểu diễn tương đương **-1 giây + 999.999.999 nano giây**. Vì vậy `getSeconds()` và `getNano()` không nhất thiết có cùng dấu; `toNanosPart()` không phải tổng nano giây có dấu của toàn duration.

Với duration âm cần hiển thị phần mili/nano, hãy xác định quy ước dấu rõ ràng và kiểm thử. `Duration.toString()` có thể phù hợp nếu dạng ISO-8601 của Java đáp ứng yêu cầu. `abs()` tạo duration không âm nhưng có thể ném `ArithmeticException` ở trường hợp biên. Đừng giả định mọi phương thức Part đều dương.

## 7. Độ chính xác và giới hạn kiểu số

- `toSeconds()` trả tổng giây nguyên, bỏ phần nano lẻ.
- `toMillis()` trả tổng mili giây; có thể ném `ArithmeticException` nếu vượt miền `long`.
- `toNanos()` chuyển toàn bộ duration sang nano giây và có thể tràn `long`.
- `toSecondsPart()` là phần giây trong phút; `toMillisPart()` là phần mili giây trong giây; `toNanosPart()` là phần nano giây trong giây.

Ví dụ 1,5 giây:

~~~text
Duration.ofMillis(1500).toSeconds()     = 1
Duration.ofMillis(1500).toMillis()      = 1500
Duration.ofMillis(1500).toNanosPart()   = 500000000
~~~

`toNanosPart()` không thể thay `toNanos()`: một phương thức trả phần thành phần, phương thức kia chuyển cả duration. Tránh nhân trực tiếp `toHours() * 3600` hoặc `toSeconds() * 1000` mà không xét khả năng tràn.

## 8. Ứng dụng thực tế

**Benchmark và thời gian xử lý:** để báo tổng độ trễ, dùng total theo đơn vị cần báo cáo. `toMillisPart()` không phải tổng thời gian vì chỉ trả phần mili giây còn lại trong giây. Đo elapsed time thường dùng hiệu hai lần đọc `System.nanoTime()`; giá trị nanoTime riêng lẻ không phải epoch.

**SLA:** nếu cần xác định tác vụ đã kéo dài quá 24 giờ, so sánh duration với `Duration.ofHours(24)` hoặc dùng tổng giờ/ngày. `toHoursPart()` có thể là 3 giờ dù tổng thời lượng đã là 27 giờ.

**Countdown:** để hiển thị “2 ngày 04:05:07”, dùng các phần ngày/giờ/phút/giây. Hãy quyết định có hiển thị duration âm, mili giây hoặc nano giây hay không.

**Cộng nhiều phiên:** nếu muốn tổng thời lượng, cộng các `Duration` trước rồi mới phân rã:

~~~java
Duration total = first.plus(second).plus(third);
long totalMinutes = total.toMinutes();
int remainingMinutes = total.toMinutesPart();
~~~

Đây là mã minh họa cần khai báo các biến. Cộng duration trước giúp tránh phải tự xử lý việc cộng 60 phút thành một giờ.

## 9. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| Dùng `toHoursPart()` làm tổng giờ. | 52 giờ thành 4 giờ. | Dùng `toHours()`. |
| Dùng `toMinutesPart()` làm tổng phút. | 125 phút thành 5 phút. | Dùng `toMinutes()`. |
| Cộng `toHours()` và `toMinutes()` để tạo chuỗi. | Đếm lặp một duration theo hai đơn vị. | Chọn total hoặc phân rã Part nhất quán. |
| Nghĩ `toDaysPart()` là ngày dư. | Đọc sai kết quả. | `toDaysPart()` tương đương `toDays()`. |
| Dùng Part để kiểm tra SLA đã vượt ngưỡng. | Bỏ qua ngày/giờ tổng. | So sánh toàn bộ Duration hoặc dùng total. |
| Cho rằng total làm tròn đến gần nhất. | Sai báo cáo. | Total trả đơn vị đầy đủ, không làm tròn. |
| Coi `toNanosPart()` là tổng nano giây. | Mất thông tin toàn duration. | Dùng `toNanos()` khi không tràn. |
| Ghép Part âm như phần dương. | Sai dấu và cách hiển thị. | Định nghĩa format âm rõ ràng. |
| Coi một ngày Duration là ngày lịch của mọi vùng. | Nhầm 24 giờ với ngày địa phương. | Dùng LocalDate/ZoneId cho ngày lịch. |
| Bỏ qua kết quả `d.plusMinutes(5)`. | Duration gốc không đổi. | Nhận hoặc gán đối tượng trả về. |

## 10. Câu hỏi tự kiểm tra

**1.** Với `Duration.ofMinutes(125)`, `toMinutes()` và `toMinutesPart()` trả gì?

**Đáp án:** 125 và 5. Tổng 125 phút gồm hai giờ và năm phút dư.

**2.** Với 52 giờ 5 phút, vì sao `toHoursPart()` trả 4?

**Đáp án:** Hai ngày chứa 48 giờ; còn bốn giờ dư. Tổng giờ vẫn là 52.

**3.** `toHours()` có làm tròn 119 phút thành hai giờ không?

**Đáp án:** Không. Nó trả số giờ đầy đủ là 1, phần còn lại là 59 phút.

**4.** `toDaysPart()` có cùng ý nghĩa phần dư như `toHoursPart()` không?

**Đáp án:** Không. `toDaysPart()` hoạt động như `toDays()`; `toHoursPart()` trả giờ dư sau khi tách ngày.

**5.** Vì sao `toNanosPart()` không thay `toNanos()`?

**Đáp án:** `toNanosPart()` trả phần nano giây trong giây; `toNanos()` chuyển toàn duration thành tổng nano giây và có thể tràn `long`.

**6.** Duration âm có thể định dạng y như duration dương mà không cần quy tắc dấu không?

**Đáp án:** Không nên. Thành phần giờ/phút/giây có thể âm trong khi trường nano nội bộ được chuẩn hóa không âm. Hãy quy định cách đặt dấu và kiểm thử.

## Ghi nhớ

**`toHours()` và `toMinutes()` là tổng số đơn vị; `toHoursPart()` và `toMinutesPart()` là phần dư để phân rã duration.** 52 giờ tương ứng 4 giờ dư sau hai ngày; 3125 phút tương ứng 5 phút dư sau 52 giờ. `toDaysPart()` tương đương `toDays()`. Dùng total để thống kê và so ngưỡng; dùng Part để hiển thị thành phần. Với duration âm, độ chính xác mili/nano và nguy cơ tràn số, hãy định nghĩa quy tắc rõ ràng trước khi chuyển đổi hoặc định dạng.
