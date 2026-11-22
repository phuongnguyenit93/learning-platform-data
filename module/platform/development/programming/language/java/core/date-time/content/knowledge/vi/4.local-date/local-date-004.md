# Kiểm tra năm nhuận, độ dài tháng và độ dài năm bằng LocalDate trong Java

## 1. Mục tiêu và phạm vi

Trong ứng dụng quản lý đơn hàng, hợp đồng, báo cáo hoặc lịch hẹn, số ngày của **tháng** và **năm** quyết định một ngày có hợp lệ hay không, ngày cuối kỳ là ngày nào, và phép cộng ngày phải xử lý những trường hợp như 29/02 ra sao. Java cung cấp các API rõ nghĩa trong **java.time** thay vì buộc lập trình viên tự lập bảng số ngày và áp dụng công thức năm nhuận ở nhiều nơi.

Sau bài học, bạn có thể:

- Giải thích quy tắc **năm nhuận trong lịch ISO/Gregorian**, kể cả năm tròn thế kỷ.
- Dùng **LocalDate.isLeapYear()**, **LocalDate.lengthOfMonth()**, **LocalDate.lengthOfYear()**.
- Chọn **Year**, **YearMonth**, **Month** khi mới biết năm, năm-tháng hoặc chỉ tháng.
- Kiểm tra ngày 29/02, ngày 30/31 của các tháng, và xử lý **DateTimeException**.
- Tính ngày cuối tháng, ngày cuối năm, vị trí ngày trong năm và số ngày giữa hai ngày.
- Phân biệt **độ dài năm theo lịch** với **thời lượng thực theo giây**, tránh nhầm lẫn trong nghiệp vụ.

Phạm vi bài này là **LocalDate** và lịch ISO chuẩn dùng trong Java Core. Khi cần một giờ hoặc một thời điểm cụ thể, phải bổ sung kiểu tương ứng; bản thân ngày trong lịch không chứa múi giờ hay thời điểm UTC.

## 2. Năm nhuận là gì?

Trong lịch Gregorian (dạng kéo dài về quá khứ theo quy ước **proleptic Gregorian** của java.time), một năm thông thường có **365 ngày**; một năm nhuận có **366 ngày** vì tháng Hai có thêm ngày **29/02**.

Quy tắc xác định năm nhuận:

1. Năm **chia hết cho 400**: là năm nhuận.
2. Nếu không chia hết cho 400 mà **chia hết cho 100**: không nhuận.
3. Nếu không thuộc hai trường hợp trên nhưng **chia hết cho 4**: là năm nhuận.
4. Các năm còn lại: không nhuận.

Có thể viết biểu thức logic tương đương:

~~~java
boolean leap = (year % 4 == 0)
        && (year % 100 != 0 || year % 400 == 0);
~~~

Đây là **biểu thức minh họa** cần đặt trong phương thức với biến **year** đã khai báo. Trong code ứng dụng, nên dùng **Year.isLeap(year)** hoặc phương thức của đối tượng ngày năm tương ứng để diễn đạt ý nghĩa nghiệp vụ và tránh lặp công thức.

| Năm | Chia hết cho 4 | Chia hết cho 100 | Chia hết cho 400 | Kết luận |
| --- | --- | --- | --- | --- |
| 2024 | Có | Không | Không | Nhuận, 366 ngày |
| 2025 | Không | Không | Không | Không nhuận, 365 ngày |
| 2028 | Có | Không | Không | Nhuận, 366 ngày |
| 1900 | Có | Có | Không | **Không nhuận**, 365 ngày |
| 2000 | Có | Có | Có | **Nhuận**, 366 ngày |
| 2100 | Có | Có | Không | **Không nhuận**, 365 ngày |
| 2400 | Có | Có | Có | **Nhuận**, 366 ngày |

Điểm quan trọng là **“chia hết cho 4” chưa đủ**: năm 1900 và 2100 là những phản ví dụ. Các ví dụ này theo quy tắc ISO proleptic Gregorian của Java; không dùng nguyên quy tắc đó để phán đoán cách các quốc gia đã thực sự đánh số ngày trong mọi giai đoạn lịch sử.

## 3. Ba phương thức trung tâm của LocalDate

**java.time.LocalDate** mô tả **ngày**, gồm năm, tháng, ngày trong tháng theo lịch ISO. Đối tượng không có giờ, offset, ZoneId hoặc Instant, và là **immutable**.

~~~java
LocalDate date = LocalDate.of(2024, 2, 10);
boolean leap = date.isLeapYear();   // true
int daysInMonth = date.lengthOfMonth(); // 29
int daysInYear = date.lengthOfYear();   // 366
~~~

Đây là đoạn trích, cần import **java.time.LocalDate** và đặt trong phương thức nếu muốn biên dịch riêng.

### LocalDate.isLeapYear()

Trả về **boolean** theo **năm** của đối tượng LocalDate; ngày và tháng đang đứng không làm thay đổi kết quả. Chẳng hạn:

- **LocalDate.of(2024, 1, 1).isLeapYear()** trả **true**.
- **LocalDate.of(2024, 12, 31).isLeapYear()** cũng trả **true**.
- **LocalDate.of(2025, 2, 1).isLeapYear()** trả **false**.

Phương thức không tạo hoặc đổi ngày; nó chỉ truy vấn thông tin của năm. LocalDate đã luôn chứa ngày hợp lệ nên không cần dùng phương thức này như bước xác minh đối tượng có hợp lệ hay không.

### LocalDate.lengthOfMonth()

Trả về số ngày của **tháng chứa ngày đó**: một trong 28, 29, 30 hoặc 31.

~~~java
LocalDate feb2024 = LocalDate.of(2024, 2, 1);
LocalDate feb2025 = LocalDate.of(2025, 2, 1);

System.out.println(feb2024.lengthOfMonth()); // 29
System.out.println(feb2025.lengthOfMonth()); // 28
~~~

Đây là đoạn trích dùng bên trong phương thức; cần import LocalDate. Vì năm nhuận chỉ tác động đến tháng Hai theo lịch ISO, **lengthOfMonth()** đặc biệt hữu ích khi xây lịch tháng, chọn ngày giao dịch hợp lệ hoặc xác định ngày cuối tháng.

Không nhầm **lengthOfMonth()** với số ngày **còn lại** từ ngày hiện tại tới cuối tháng. Ví dụ 10/02/2024 có lengthOfMonth() = 29 nhưng số ngày sau ngày 10/02 đến 29/02 là **19**; nếu tính cả ngày 10/02 thì có **20** ngày. Hãy xác định quy tắc tính bao gồm/không bao gồm ngày đầu và cuối.

### LocalDate.lengthOfYear()

Trả về **365** nếu năm thường, **366** nếu năm nhuận.

~~~java
LocalDate firstDay2024 = LocalDate.of(2024, 1, 1);
System.out.println(firstDay2024.lengthOfYear()); // 366
~~~

Số ngày trong năm không phụ thuộc bạn gọi trên 01/01 hay 31/12 của cùng năm. **lengthOfYear()** là độ dài **năm lịch**, không phải cách đo thời lượng thực giữa hai Instant qua múi giờ.

## 4. Chọn Year, YearMonth hay Month khi dữ liệu chưa có ngày

Không cần phải “chế” ra ngày 01/01 hoặc 01 của tháng nếu yêu cầu chỉ cung cấp năm hoặc năm-tháng.

| Đã biết | Kiểu Java | API phù hợp | Ví dụ |
| --- | --- | --- | --- |
| Chỉ có năm | **Year** | **Year.isLeap(long)**, **Year.of(y).isLeap()**, **Year.of(y).length()** | Kiểm tra 2100 có nhuận không |
| Có năm và tháng | **YearMonth** | **isLeapYear()**, **lengthOfMonth()**, **lengthOfYear()**, **isValidDay(d)** | Số ngày tháng 2/2024 |
| Chỉ có tháng, chưa biết năm | **Month** | **length(boolean leapYear)**, **minLength()**, **maxLength()** | Tháng 2 có thể 28/29 ngày |
| Có năm-tháng-ngày | **LocalDate** | **isLeapYear()**, **lengthOfMonth()**, **lengthOfYear()** | Truy vấn từ ngày trên hóa đơn |

Ví dụ:

~~~java
Year year = Year.of(2100);
boolean leap = year.isLeap();                 // false
int daysInYear = year.length();               // 365

YearMonth february = YearMonth.of(2024, 2);
int monthDays = february.lengthOfMonth();      // 29
boolean valid29 = february.isValidDay(29);     // true
LocalDate monthEnd = february.atEndOfMonth();  // 2024-02-29

int febNormal = Month.FEBRUARY.length(false);  // 28
int febLeap = Month.FEBRUARY.length(true);     // 29
~~~

Các biểu thức là đoạn trích cần import java.time.*, đặt trong một phương thức. **Month.length(boolean)** yêu cầu truyền thông tin năm nhuận vào khi xét tháng Hai, vì một Month riêng lẻ không biết năm nào. Với đối tượng YearMonth, Java tự suy ra năm nhuận nên đây là lựa chọn tốt khi xây lịch cho một tháng cụ thể.

**Year.isLeap(long)** là hàm static kiểm tra quy tắc theo năm, không cần tạo LocalDate. Nếu chỉ muốn trả lời “năm 2028 có nhuận không?”, đây là API đúng mức trừu tượng.

## 5. Độ dài từng tháng theo lịch ISO

| Tháng | Số ngày năm thường | Số ngày năm nhuận |
| --- | ---: | ---: |
| Tháng 1 | 31 | 31 |
| **Tháng 2** | **28** | **29** |
| Tháng 3 | 31 | 31 |
| Tháng 4 | 30 | 30 |
| Tháng 5 | 31 | 31 |
| Tháng 6 | 30 | 30 |
| Tháng 7 | 31 | 31 |
| Tháng 8 | 31 | 31 |
| Tháng 9 | 30 | 30 |
| Tháng 10 | 31 | 31 |
| Tháng 11 | 30 | 30 |
| Tháng 12 | 31 | 31 |
| **Tổng** | **365** | **366** |

Mọi tháng khác tháng Hai có số ngày cố định theo quy tắc này; riêng tháng Hai cần biết năm.

Đừng nhầm quy tắc **“tháng chẵn 30 ngày, tháng lẻ 31 ngày”**: tháng 7 và tháng 8 đều có 31 ngày; tháng 12 cũng có 31. Khi viết ứng dụng, dùng API thay cho quy tắc nhớ thủ công.

Có thể lấy ngày cuối cùng của tháng mà không tự tính:

~~~java
YearMonth month = YearMonth.of(2026, 4);
LocalDate last = month.atEndOfMonth(); // 2026-04-30

LocalDate date = LocalDate.of(2024, 2, 10);
LocalDate end = date.withDayOfMonth(date.lengthOfMonth());
// 2024-02-29
~~~

Với LocalDate, cũng có thể dùng **date.with(TemporalAdjusters.lastDayOfMonth())**, sau khi import **java.time.temporal.TemporalAdjusters**. Ưu điểm là diễn đạt trực tiếp chính sách “ngày cuối cùng trong tháng” và xử lý tháng Hai tự động.

## 6. Ví dụ Java 17+ hoàn chỉnh và đầu ra xác định

Tạo tệp **LeapYearAndMonthLength.java**:

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.Month;
import java.time.Year;
import java.time.YearMonth;
import java.time.temporal.ChronoUnit;

public class LeapYearAndMonthLength {
    public static void main(String[] args) {
        System.out.println("2024 nhuận: " + Year.isLeap(2024));
        System.out.println("1900 nhuận: " + Year.isLeap(1900));
        System.out.println("2000 nhuận: " + Year.isLeap(2000));
        System.out.println("2100 nhuận: " + Year.isLeap(2100));

        LocalDate inLeapYear = LocalDate.of(2024, 2, 10);
        LocalDate inNormalYear = LocalDate.of(2025, 2, 10);
        System.out.println("Tháng 2/2024: " + inLeapYear.lengthOfMonth());
        System.out.println("Tháng 2/2025: " + inNormalYear.lengthOfMonth());
        System.out.println("Năm 2024: " + inLeapYear.lengthOfYear());
        System.out.println("Năm 2025: " + inNormalYear.lengthOfYear());

        YearMonth february = YearMonth.of(2024, Month.FEBRUARY);
        YearMonth april = YearMonth.of(2026, Month.APRIL);
        System.out.println("29/02/2024 hợp lệ: " + february.isValidDay(29));
        System.out.println("Cuối tháng 2/2024: " + february.atEndOfMonth());
        System.out.println("Cuối tháng 4/2026: " + april.atEndOfMonth());

        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        System.out.println("29/02 cộng 1 năm: " + leapDay.plusYears(1));
        System.out.println("Ngày thứ mấy trong năm: " +
                LocalDate.of(2024, 12, 31).getDayOfYear());
        long daysIn2024 = ChronoUnit.DAYS.between(
                LocalDate.of(2024, 1, 1),
                LocalDate.of(2025, 1, 1));
        System.out.println("Khoảng năm 2024 (ngày): " + daysIn2024);

        try {
            LocalDate.of(2025, 2, 29);
        } catch (DateTimeException exception) {
            System.out.println("29/02/2025: ngày không hợp lệ");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LeapYearAndMonthLength.java
java LeapYearAndMonthLength
~~~

**Stdout chính xác**:

~~~text
2024 nhuận: true
1900 nhuận: false
2000 nhuận: true
2100 nhuận: false
Tháng 2/2024: 29
Tháng 2/2025: 28
Năm 2024: 366
Năm 2025: 365
29/02/2024 hợp lệ: true
Cuối tháng 2/2024: 2024-02-29
Cuối tháng 4/2026: 2026-04-30
29/02 cộng 1 năm: 2025-02-28
Ngày thứ mấy trong năm: 366
Khoảng năm 2024 (ngày): 366
29/02/2025: ngày không hợp lệ
~~~

Giải thích:

- **1900** là năm tròn thế kỷ không chia hết cho 400 nên không nhuận; **2000** chia hết cho 400 nên nhuận.
- **YearMonth.isValidDay(29)** kiểm tra ngày 29 có hợp lệ trong tháng 2/2024.
- **plusYears(1)** trên 29/02/2024 đưa đến **28/02/2025** vì năm đích không có ngày 29/02. Đây là hành vi chuẩn của LocalDate, nhưng ứng dụng ngày kỷ niệm cần quyết định chính sách riêng nếu muốn chuyển sang 01/03.
- **getDayOfYear()** cho biết thứ tự 1–365 hoặc 1–366; 31/12/2024 là ngày thứ 366.
- **ChronoUnit.DAYS.between(start, end)** với đầu **01/01/2024** và cuối **01/01/2025** trả 366 theo khoảng đầu gồm, cuối loại.
- Gọi **LocalDate.of(2025, 2, 29)** ném DateTimeException vì ngày không tồn tại; đoạn try/catch chỉ in thông báo ổn định, không phụ thuộc nội dung chi tiết của thông điệp lỗi do JDK tạo ra.

Ví dụ dùng toàn bộ ngày tháng cố định, không phụ thuộc đồng hồ, múi giờ hay thời điểm chạy.

## 7. Kiểm tra ngày hợp lệ: đừng chỉ nhìn số ngày nằm trong 1–31

Một cặp năm-tháng-ngày hợp lệ cần đồng thời đúng:

- Năm nằm trong miền mà kiểu dữ liệu hỗ trợ.
- Tháng nằm trong 1–12.
- Ngày nằm trong 1 đến **số ngày thật của tháng trong năm đó**.

Ví dụ:

| Dữ liệu đầu vào | Hợp lệ? | Lý do |
| --- | --- | --- |
| 29/02/2024 | Có | 2024 là năm nhuận |
| 29/02/2025 | Không | 2025 có 28 ngày tháng Hai |
| 31/04/2026 | Không | Tháng Tư có 30 ngày |
| 30/04/2026 | Có | Ngày cuối tháng Tư |
| 31/12/2026 | Có | Tháng Mười Hai có 31 ngày |
| 00/01/2026 | Không | Ngày trong tháng bắt đầu từ 1 |
| 01/13/2026 | Không | Không có tháng 13 |

**Cách A: tạo LocalDate và bắt ngoại lệ.** Đây là phương án đơn giản khi muốn chuyển đầu vào thành đối tượng ngày hợp lệ:

~~~java
try {
    LocalDate parsed = LocalDate.of(year, month, day);
    // parsed chỉ tồn tại nếu năm-tháng-ngày hợp lệ
} catch (DateTimeException invalidDate) {
    // Trả lỗi xác thực cho người dùng
}
~~~

Đây là đoạn trích; khai báo các biến year, month, day phù hợp và import java.time.*. Cách này kiểm tra cả tháng lẫn ngày và miền năm.

**Cách B: dùng YearMonth.isValidDay(day).** Thích hợp khi năm và tháng đã được tạo hợp lệ:

~~~java
YearMonth ym = YearMonth.of(2025, 2);
boolean possible = ym.isValidDay(29); // false
~~~

Nếu tháng đầu vào không hợp lệ, **YearMonth.of(year, month)** cũng ném DateTimeException. Vì thế không thể coi isValidDay là công cụ nhận mọi loại đầu vào chưa được kiểm tra.

**Cách C: parse với formatter nghiêm ngặt.** Khi nhận chuỗi định dạng **dd/MM/uuuu**, tránh tự tách và ghép một ngày mặc định không đúng:

~~~java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu")
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed = LocalDate.parse("29/02/2024", formatter);
// LocalDate.parse("29/02/2025", formatter) ném DateTimeParseException.
~~~

Đây là đoạn trích; cần import **java.time.LocalDate**, **java.time.format.DateTimeFormatter** và **java.time.format.ResolverStyle**. Với **ResolverStyle.STRICT**, chuỗi tạo thành ngày không tồn tại bị từ chối; dùng ký hiệu **uuuu** để biểu diễn năm ISO proleptic. **yyyy** là year-of-era, nên cần chú ý các trường era trong parse STRICT.

Không nuốt ngoại lệ rồi thay đầu vào ngày không hợp lệ bằng ngày hiện tại; việc đó làm sai dữ liệu nghiệp vụ. Nếu API cần báo lỗi, hãy giữ nguyên thông tin đầu vào và trả thông điệp dễ hiểu về ngày/tháng/năm.

## 8. Ngày cuối tháng và quy tắc cộng tháng, cộng năm

Các phương thức như **plusDays**, **plusMonths**, **plusYears**, **minusDays**, **withYear** trả đối tượng LocalDate mới; chúng không sửa đối tượng cũ.

~~~java
LocalDate base = LocalDate.of(2024, 2, 29);
LocalDate nextYear = base.plusYears(1);       // 2025-02-28
LocalDate afterFourYears = base.plusYears(4); // 2028-02-29
LocalDate nextDay = base.plusDays(1);         // 2024-03-01
~~~

Với cộng tháng, Java cố giữ ngày trong tháng; nếu ngày đó không tồn tại ở tháng đích, kết quả được điều chỉnh về **ngày hợp lệ cuối tháng đích**:

~~~java
LocalDate january31 = LocalDate.of(2025, 1, 31);
LocalDate nextMonth = january31.plusMonths(1);
// 2025-02-28

LocalDate leapJanuary31 = LocalDate.of(2024, 1, 31);
LocalDate leapFebruary = leapJanuary31.plusMonths(1);
// 2024-02-29
~~~

**Lưu ý nghiệp vụ:** “Mỗi tháng vào ngày 31” không hoàn toàn giống “lấy ngày trước rồi cộng một tháng” lặp đi lặp lại. Ví dụ:

- 31/01/2025 + 1 tháng = 28/02/2025.
- 28/02/2025 + 1 tháng = 28/03/2025.
- Nhưng nếu chính sách là **ngày cuối mỗi tháng**, kỳ tháng Ba phải rơi vào **31/03/2025**.

Vì vậy, với lịch định kỳ “cuối tháng”, nên lưu **quy tắc cuối tháng** rồi tính bằng **YearMonth.atEndOfMonth()** cho từng tháng; không cộng nối tiếp từ một ngày đã bị điều chỉnh xuống 28. Với chính sách kỷ niệm 29/02 trong năm không nhuận, cần định nghĩa rõ dùng 28/02 hay 01/03; Java không tự chọn quy tắc pháp lý/kinh doanh của tổ chức.

## 9. Độ dài năm, vị trí ngày trong năm và đếm khoảng ngày

Một năm nhuận có 366 ngày, nhưng **day-of-year** là thứ tự của ngày cụ thể từ 1. Một vài ví dụ:

| LocalDate | getDayOfYear() |
| --- | ---: |
| 2024-01-01 | 1 |
| 2024-02-28 | 59 |
| 2024-02-29 | 60 |
| 2024-03-01 | 61 |
| 2025-03-01 | 60 |
| 2024-12-31 | 366 |
| 2025-12-31 | 365 |

Khi chuyển từ số thứ tự ngày trong năm thành ngày, dùng **LocalDate.ofYearDay(year, dayOfYear)**. Chẳng hạn:

~~~java
LocalDate sixtieth2024 = LocalDate.ofYearDay(2024, 60);
// 2024-02-29

LocalDate sixtieth2025 = LocalDate.ofYearDay(2025, 60);
// 2025-03-01
~~~

Truyền 366 cho **LocalDate.ofYearDay(2025, 366)** sẽ ném DateTimeException vì năm thường chỉ có 365 ngày.

**Đếm số ngày giữa hai LocalDate:** dùng **ChronoUnit.DAYS.between(startInclusive, endExclusive)** hoặc **start.until(end, ChronoUnit.DAYS)**. Nếu bài toán cần đếm cả ngày bắt đầu và ngày kết thúc (ví dụ số ngày của một chuyến đi theo lịch), hãy nêu rõ quy tắc bao gồm rồi tính tương ứng. Không phải bài toán nào cũng cộng thêm một ngày.

**Một năm lịch khác 365 × 24 giờ.** LocalDate.lengthOfYear() trả 365/366 ngày theo lịch ISO. Khi xét một năm địa phương trong vùng có chuyển giờ mùa hè, số giờ trôi qua phụ thuộc các lần đổi offset; ở những vùng đặc biệt, thậm chí một ngày địa phương có thể không dài 24 giờ. Nếu cần đo số giây thực giữa hai mốc, tạo Instant theo vùng phù hợp rồi dùng Duration. Đừng lấy số ngày lịch nhân với 86.400 để kết luận chính xác số giây của một khoảng trong mọi múi giờ.

## 10. Ứng dụng: tạo lịch tháng, xác định ngày kết thúc kỳ

### In tất cả ngày trong một tháng

Khi cần tạo các lựa chọn ngày của tháng 2 năm 2024, **YearMonth.lengthOfMonth()** là cách tự nhiên:

~~~java
YearMonth ym = YearMonth.of(2024, 2);
for (int day = 1; day <= ym.lengthOfMonth(); day++) {
    LocalDate calendarDate = ym.atDay(day);
    // Dùng calendarDate để tạo mục lịch hoặc hiển thị ngày.
}
~~~

Đây là đoạn trích; import java.time.* và đặt trong phương thức. Cách làm tự bao gồm 29/02/2024, nhưng không vô tình tạo 29/02/2025. Khi làm lịch nhiều năm, tránh cache cứng số ngày tháng Hai.

### Lấy khoảng ngày của một kỳ tháng

Một kỳ báo cáo từ tháng 2/2024 có thể được biểu diễn bằng khoảng **[2024-02-01, 2024-03-01)**:

~~~java
YearMonth period = YearMonth.of(2024, 2);
LocalDate startInclusive = period.atDay(1);
LocalDate endExclusive = period.plusMonths(1).atDay(1);
// startInclusive = 2024-02-01
// endExclusive   = 2024-03-01
~~~

Mọi LocalDate thỏa **!date.isBefore(startInclusive) && date.isBefore(endExclusive)** nằm trong kỳ. Khoảng **đầu gồm, cuối loại** giúp ghép các kỳ tháng liên tiếp mà không trùng ngày ranh giới.

Nếu truy vấn **timestamp** theo tháng của một địa phương, phải chuyển các ranh giới LocalDate sang Instant bằng ZoneId nghiệp vụ trước; chỉ riêng lengthOfMonth() không đủ để khẳng định bao nhiêu giây trôi qua trong tháng ở mọi vùng.

### Ngày sinh và tuổi

Ngày sinh nên là **LocalDate**. Để tính tuổi tại một ngày tham chiếu, dùng **Period.between(dateOfBirth, referenceDate).getYears()** nếu chính sách tuổi sử dụng cách đếm đủ năm dựa trên lịch ISO; riêng người sinh 29/02 có thể chịu quy định pháp lý hoặc chính sách tổ chức khác ở năm không nhuận. **getYear()** không phải tuổi; nó trả năm tuyệt đối của LocalDate.

### Hạn dùng và ngày thanh toán

Nếu hóa đơn đáo hạn “ngày cuối tháng”, tính theo **YearMonth.atEndOfMonth()**. Nếu hợp đồng yêu cầu “sau đúng 365 ngày”, dùng phép cộng số ngày rõ ràng **date.plusDays(365)**; nếu yêu cầu “sau một năm lịch”, dùng **date.plusYears(1)**. Với ngày 29/02, hai cách có thể ra kết quả khác nhau, vì vậy cần dịch đúng câu chữ hợp đồng thành chính sách tính ngày.

## 11. Các giới hạn và trường hợp biên

- **Không có ngày 0 hoặc tháng 0** trong LocalDate ISO. Ngày nằm trong 1 đến lengthOfMonth(); tháng trong 1 đến 12.
- **Java hỗ trợ cả năm 0 và năm âm** theo hệ số năm proleptic của ISO, cùng miền năm LocalDate từ **-999999999 đến +999999999**. Năm 0 không đồng nhất cách gọi năm trong tài liệu lịch sử (BC/AD); khi hiển thị dữ liệu lịch sử cần xác định quy ước.
- **Year.isLeap(0)** trả **true** theo quy tắc ISO proleptic Gregorian. Năm âm cũng được áp dụng theo cùng quy tắc số học. Đây là quy ước lập trình, không khẳng định mọi xã hội trong lịch sử đều dùng lịch Gregorian.
- Một số hệ lịch khác ISO có cách xác định năm nhuận và độ dài tháng khác. **LocalDate** là kiểu ISO; nếu cần lịch Nhật Bản, Hijrah hoặc hệ khác, hãy tìm hiểu **java.time.chrono** và dùng kiểu/phương thức phù hợp, tránh tự áp công thức ISO cho mọi Chronology.
- **YearMonth.of(...)**, **LocalDate.of(...)**, **LocalDate.ofYearDay(...)** đều có thể ném **DateTimeException** khi trường đầu vào ngoài phạm vi hoặc ngày không hợp lệ.
- Dùng **LocalDate.now()** để lấy “ngày hôm nay” phụ thuộc giờ và múi giờ hệ thống. Khi kiểm tra năm nhuận của một năm do người dùng nhập, nên xây ngày/năm từ dữ liệu đó, không cần đồng hồ máy. Trong bài toán có “hôm nay”, nên dùng **Clock** hoặc ZoneId rõ ràng để test ổn định.
- **LocalDate.isLeapYear()** hoạt động trên năm của chính đối tượng; gọi trên **LocalDate.of(2024, 6, 1)** vẫn là phép kiểm tra năm 2024, không phải kiểm tra liệu tháng Sáu có ngày nhuận.

## 12. Sai lầm phổ biến và cách sửa

| Cách làm sai hoặc dễ gây lỗi | Hệ quả | Cách đúng |
| --- | --- | --- |
| Chỉ dùng **year % 4 == 0** | Xác định sai 1900/2100 | Dùng **Year.isLeap(year)** |
| Giả định **tháng 2 luôn có 28 ngày** | Bỏ mất 29/02 năm nhuận | Dùng **YearMonth.lengthOfMonth()** |
| Giả định mọi năm có **365 ngày** | Đếm sai ngày và day-of-year | Dùng **LocalDate.lengthOfYear()** |
| Cho phép ngày từ **1..31** mọi tháng | Tạo 31/04, 30/02 không tồn tại | Dùng **LocalDate.of(...)** hoặc **YearMonth.isValidDay(...)** |
| Tự thêm 86.400 giây để “sang ngày mai” ở mọi vùng | Có thể lệch tại giờ đổi DST | Dùng ngày lịch **plusDays(1)** và zone khi cần Instant |
| Dùng **plusMonths(1)** liên tiếp cho lịch “cuối tháng” | Sau tháng 2 có thể mất mốc ngày 31 | Lưu chính sách cuối tháng, dùng **atEndOfMonth()** |
| Gán kết quả **date.plusDays(1)** nhưng chờ date tự thay đổi | Không thấy thay đổi vì LocalDate immutable | Dùng giá trị mới trả về |
| Bắt mọi Exception và coi ngày sai là ngày hiện tại | Che lỗi nhập liệu | Bắt **DateTimeException**, báo lý do xác thực |
| Áp quy tắc Gregorian cho mọi lịch sử và hệ lịch | Sai ngữ nghĩa lịch | Nêu rõ **ISO proleptic Gregorian**, chọn Chronology phù hợp |
| So sánh chuỗi “dd/MM/yyyy” thay vì ngày thực | Sai thứ tự ngày tháng | Parse thành **LocalDate**, rồi dùng **isBefore/isAfter** |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Năm 2100 có 366 ngày không?

Không. 2100 chia hết cho 100 nhưng không chia hết cho 400, vì thế là năm thường có **365 ngày**; tháng 2 có 28 ngày.

**Câu 2.** LocalDate.of(2028, 2, 1).lengthOfMonth() trả gì?

**29** vì năm 2028 chia hết cho 4, không chia hết cho 100 và là năm nhuận.

**Câu 3.** LocalDate.of(2025, 2, 28).plusDays(1) trả ngày nào?

**2025-03-01**, vì năm 2025 không nhuận.

**Câu 4.** Ngày 31/01/2024 cộng một tháng và ngày cuối tháng 2/2024 có trùng nhau không?

Có. **LocalDate.of(2024, 1, 31).plusMonths(1)** cho **2024-02-29**; **YearMonth.of(2024, 2).atEndOfMonth()** cũng cho **2024-02-29**. Tuy vậy, cộng tháng nối tiếp không luôn bảo toàn chính sách “cuối tháng”, như đã giải thích tại mục 8.

**Câu 5.** Nếu có 2024 và 02 nhưng chưa có ngày, nên dùng kiểu nào?

**YearMonth**, vì nó thể hiện đúng dữ liệu đầu vào; dùng **lengthOfMonth()** hoặc **isValidDay(29)** mà không cần dựng một LocalDate giả.

**Câu 6.** Ngày thứ 60 trong năm 2024 và năm 2025 có giống nhau?

Không. Năm 2024, đó là **29/02**; năm 2025, đó là **01/03**.

**Câu 7.** Có thể lấy lengthOfYear() nhân 86.400 để tìm số giây chính xác của cả năm ở mọi múi giờ không?

Không. **lengthOfYear()** trả số ngày lịch, còn ranh giới một năm theo múi giờ và quy tắc đổi offset quyết định khoảng thời gian thực giữa hai Instant.

## 14. Ghi nhớ khi triển khai

- **Muốn biết năm nhuận:** **Year.isLeap(year)** hoặc **LocalDate.isLeapYear()**.
- **Muốn biết tháng có bao nhiêu ngày:** **YearMonth.lengthOfMonth()** hoặc **LocalDate.lengthOfMonth()**.
- **Muốn biết năm có bao nhiêu ngày:** **Year.of(year).length()**, **YearMonth.lengthOfYear()** hoặc **LocalDate.lengthOfYear()**.
- **Muốn kiểm tra một ngày trong năm-tháng:** **YearMonth.isValidDay(day)**; muốn dựng cả ngày hợp lệ, dùng **LocalDate.of(year, month, day)**.
- **Muốn xác định ngày cuối tháng:** **YearMonth.atEndOfMonth()** hoặc **TemporalAdjusters.lastDayOfMonth()**.
- **Muốn biết thứ tự ngày trong năm:** **LocalDate.getDayOfYear()**; muốn tạo theo thứ tự đó dùng **LocalDate.ofYearDay(year, day)**.
- **Muốn đo số ngày giữa hai ngày:** **ChronoUnit.DAYS.between(start, end)** và quyết định rõ biên có được tính hay không.

## Tài liệu tham khảo chính thức

- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): isLeapYear, lengthOfMonth, lengthOfYear, getDayOfYear và thao tác ngày.
- [Java SE 17 — Year](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Year.html): quy tắc nhuận, Year.isLeap và Year.length.
- [Java SE 17 — YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html): isValidDay, atEndOfMonth, lengthOfMonth và lengthOfYear.
- [Java SE 17 — Month](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Month.html): độ dài tháng theo năm nhuận.
- [Java SE 17 — ChronoUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoUnit.html): đếm số ngày theo đơn vị thời gian lịch.
