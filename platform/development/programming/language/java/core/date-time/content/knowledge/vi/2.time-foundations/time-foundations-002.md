# Năm nhuận, số ngày trong tháng và ngày không hợp lệ

Một ngày lịch chỉ hợp lệ khi **năm, tháng và ngày phù hợp với nhau**. Chẳng hạn, tháng 2 không luôn có 29 ngày; ngày 31 không tồn tại trong một số tháng; và tháng 13 không tồn tại. Java cung cấp bộ API `java.time` để kiểm tra các quy tắc này trực tiếp, tránh phải duy trì một bảng điều kiện thủ công.

Bài học thuộc nền tảng thời gian của **Java core – date-time**, tập trung vào lịch ISO/Gregorian, cách xác định năm nhuận, số ngày trong tháng, ngày sai và cách xử lý bằng Java 17+.

## 1. Quy tắc năm nhuận

Theo **lịch Gregorian**, một năm là năm nhuận khi:

1. Năm đó **chia hết cho 400**; hoặc
2. Năm đó **chia hết cho 4 nhưng không chia hết cho 100**.

Diễn đạt bằng biểu thức Boolean:

```java
boolean leap = year % 400 == 0
        || (year % 4 == 0 && year % 100 != 0);
```

Một năm thường có **365 ngày**; năm nhuận có **366 ngày** nhờ thêm ngày **29/02**. Chỉ dùng `year % 4 == 0` sẽ sai với các năm tròn thế kỷ không chia hết cho 400.

| Năm | Chia hết cho 4? | Chia hết cho 100? | Chia hết cho 400? | Kết quả |
| --- | --- | --- | --- | --- |
| 1896 | Có | Không | Không | Nhuận |
| 1900 | Có | Có | Không | Không nhuận |
| 2000 | Có | Có | Có | Nhuận |
| 2024 | Có | Không | Không | Nhuận |
| 2025 | Không | Không | Không | Không nhuận |
| 2100 | Có | Có | Không | Không nhuận |

Java có sẵn API để xác định năm nhuận; với các bài toán thực tế, hãy ưu tiên chúng:

```java
System.out.println(Year.isLeap(1900));          // false
System.out.println(Year.isLeap(2000));          // true
System.out.println(Year.of(2024).isLeap());     // true
System.out.println(YearMonth.of(2024, 2).isLeapYear()); // true
```

Các dòng trên là **đoạn minh họa**, cần đặt trong phương thức Java và import `java.time.Year`, `java.time.YearMonth`. `Year.isLeap(long)` và `YearMonth.isLeapYear()` dùng quy tắc ISO với lịch Gregorian *proleptic*, tức áp dụng quy tắc Gregorian nhất quán ngay cả khi xét năm trước thời kỳ lịch này được áp dụng trong lịch sử. Điều đó hữu ích để tính toán bằng máy; đừng nhầm với việc mô phỏng mọi lịch địa phương trong quá khứ.

## 2. Một tháng có bao nhiêu ngày?

| Tháng | Số ngày |
| --- | --- |
| 1 – Tháng Một | 31 |
| 2 – Tháng Hai | 28 nếu năm thường; **29 nếu năm nhuận** |
| 3 – Tháng Ba | 31 |
| 4 – Tháng Tư | 30 |
| 5 – Tháng Năm | 31 |
| 6 – Tháng Sáu | 30 |
| 7 – Tháng Bảy | 31 |
| 8 – Tháng Tám | 31 |
| 9 – Tháng Chín | 30 |
| 10 – Tháng Mười | 31 |
| 11 – Tháng Mười Một | 30 |
| 12 – Tháng Mười Hai | 31 |

Vì tháng 2 phụ thuộc năm, **năm và tháng phải được xét cùng nhau**. Lớp `YearMonth` thể hiện đúng ý nghĩa này:

```java
YearMonth feb2023 = YearMonth.of(2023, 2);
YearMonth feb2024 = YearMonth.of(2024, 2);

System.out.println(feb2023.lengthOfMonth()); // 28
System.out.println(feb2024.lengthOfMonth()); // 29
System.out.println(feb2024.atEndOfMonth());  // 2024-02-29

LocalDate april = LocalDate.of(2024, 4, 15);
System.out.println(april.lengthOfMonth());   // 30
```

Đây là đoạn minh họa cần import `YearMonth` và `LocalDate`. `lengthOfMonth()` lấy số ngày trong đúng tháng/năm. `atEndOfMonth()` trả về ngày cuối cùng của tháng dưới dạng `LocalDate`; nó rất phù hợp với nghiệp vụ chốt kỳ, hạn thanh toán hoặc lập báo cáo cuối tháng.

`Month.FEBRUARY.length(true)` trả 29 và `Month.FEBRUARY.length(false)` trả 28, nhưng gọi API này đòi hỏi bạn **tự tính đúng cờ năm nhuận**. Với đầu vào năm–tháng cụ thể, `YearMonth.of(year, month).lengthOfMonth()` dễ sử dụng và ít lỗi hơn.

## 3. Ngày hợp lệ và ngày không hợp lệ

Với lịch ISO, bộ ba số nguyên `(year, month, day)` tạo thành một ngày hợp lệ nếu:

- `year` thuộc phạm vi được `LocalDate` hỗ trợ: từ **−999.999.999** đến **+999.999.999**.
- `month` thuộc **1 đến 12**.
- `day` thuộc **1 đến số ngày của tháng đó trong năm đó**, tức `YearMonth.of(year, month).lengthOfMonth()`.

Không thể chỉ kiểm tra `1 <= day && day <= 31`: tháng 2 không có ngày 30/31, tháng 4 không có ngày 31, và ngày 29/02 chỉ xuất hiện ở năm nhuận.

| Ngày ISO | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `2024-02-29` | Có | 2024 là năm nhuận |
| `2023-02-29` | Không | Tháng 2/2023 chỉ có 28 ngày |
| `1900-02-29` | Không | 1900 chia hết cho 100, không chia hết cho 400 |
| `2000-02-29` | Có | 2000 chia hết cho 400 |
| `2024-04-30` | Có | Tháng 4 có 30 ngày |
| `2024-04-31` | Không | Tháng 4 không có ngày 31 |
| `2024-00-10` | Không | Không có tháng 0 |
| `2024-13-01` | Không | Không có tháng 13 |
| `2024-01-00` | Không | Không có ngày 0 |
| `2024-12-31` | Có | Ngày cuối tháng 12 |

### Dùng `LocalDate.of` để Java kiểm tra

```java
LocalDate valid = LocalDate.of(2024, 2, 29); // thành công
LocalDate invalid = LocalDate.of(2023, 2, 29); // DateTimeException
```

Dòng thứ hai cố ý biểu diễn một lỗi; nó sẽ ném `java.time.DateTimeException` và phải được xử lý nếu muốn chương trình tiếp tục chạy. `LocalDate.of` không tự chuyển ngày sai thành ngày khác. Vì thế, tạo `LocalDate` là cách rõ ràng để kiểm tra sự tồn tại của ngày mà không viết lại thuật toán lịch.

Nếu hợp đồng API cần kết quả `boolean`, có thể gói phép tạo ngày:

```java
public static boolean isValidDate(int year, int month, int day) {
    try {
        LocalDate.of(year, month, day);
        return true;
    } catch (DateTimeException ex) {
        return false;
    }
}
```

Đây là **phương thức đặt trong một class Java**, cần import `java.time.LocalDate` và `java.time.DateTimeException`. Nó trả `false` với cả năm, tháng hoặc ngày nằm ngoài phạm vi cho phép. Nếu ứng dụng cần thông báo cụ thể như “tháng không hợp lệ” hay “tháng 2 năm này chỉ có 28 ngày”, hãy phân loại lỗi theo hợp đồng nghiệp vụ sau khi đã kiểm tra đầu vào; tránh tạo cơ chế chấp nhận ngày khác với `java.time`.

## 4. Ví dụ Java 17+ biên dịch và chạy được

Tạo tệp **`DateValidityDemo.java`** với nội dung:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.Year;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.ResolverStyle;

public class DateValidityDemo {
    public static void main(String[] args) {
        for (int year : new int[] {1900, 2000, 2024, 2025}) {
            System.out.printf("%d | leap=%s | February=%d%n",
                    year, Year.isLeap(year), YearMonth.of(year, 2).lengthOfMonth());
        }

        checkDate(2024, 2, 29);
        checkDate(2023, 2, 29);
        checkDate(2024, 4, 31);
        checkDate(2024, 0, 10);

        DateTimeFormatter strict = new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM-dd")
                .toFormatter()
                .withResolverStyle(ResolverStyle.STRICT);

        checkIso("2024-02-29", strict);
        checkIso("2023-02-29", strict);
    }

    private static void checkDate(int year, int month, int day) {
        try {
            LocalDate date = LocalDate.of(year, month, day);
            System.out.printf("%04d-%02d-%02d: VALID (%s)%n",
                    year, month, day, date);
        } catch (DateTimeException ex) {
            System.out.printf("%04d-%02d-%02d: INVALID%n",
                    year, month, day);
        }
    }

    private static void checkIso(String text, DateTimeFormatter formatter) {
        try {
            LocalDate date = LocalDate.parse(text, formatter);
            System.out.printf("%s (STRICT parse): VALID (%s)%n", text, date);
        } catch (DateTimeException ex) {
            System.out.printf("%s (STRICT parse): INVALID%n", text);
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac DateValidityDemo.java
java DateValidityDemo
```

**stdout dự kiến:**

```text
1900 | leap=false | February=28
2000 | leap=true | February=29
2024 | leap=true | February=29
2025 | leap=false | February=28
2024-02-29: VALID (2024-02-29)
2023-02-29: INVALID
2024-04-31: INVALID
2024-00-10: INVALID
2024-02-29 (STRICT parse): VALID (2024-02-29)
2023-02-29 (STRICT parse): INVALID
```

**Giải thích luồng xử lý:**

1. `Year.isLeap(year)` xác định năm nhuận và `YearMonth.of(year, 2).lengthOfMonth()` lấy số ngày tháng 2.
2. `checkDate` cố tạo một `LocalDate` từ ba số; giá trị hợp lệ được in ra, giá trị sai chuyển vào `catch (DateTimeException)`.
3. `checkIso` parse một chuỗi theo formatter `STRICT`; ngày không tồn tại bị từ chối.
4. Chương trình in nhãn `INVALID` thay vì in thông điệp exception, vì nội dung thông báo lỗi của JDK không phải giao diện ổn định cần so khớp trong ví dụ.

## 5. Parse chuỗi: đúng hình thức chưa đủ

Một chuỗi như `"2023-02-29"` có đúng cấu trúc **năm-tháng-ngày** nhưng vẫn **không tồn tại** trong lịch. Đầu vào từ form, JSON, CSV hoặc API cần được kiểm tra cả cú pháp và ý nghĩa.

Với chuỗi ISO đơn giản:

```java
LocalDate.parse("2024-02-29"); // trả LocalDate của 2024-02-29
LocalDate.parse("2023-02-29"); // DateTimeParseException
```

`LocalDate.parse(text)` mặc định dùng bộ định dạng ISO local date với cách phân giải nghiêm ngặt. `DateTimeParseException` là lớp con của `DateTimeException`.

Khi ứng dụng cần formatter theo mẫu riêng, hãy chỉ rõ `ResolverStyle.STRICT` nếu việc **từ chối** ngày không tồn tại là yêu cầu:

```java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd")
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate.parse("2024-02-29", strict); // thành công
LocalDate.parse("2023-02-29", strict); // DateTimeParseException
```

Các chế độ phân giải có ý nghĩa khác nhau:

| Chế độ | Hành vi điển hình |
| --- | --- |
| `STRICT` | Yêu cầu trường ngày tạo thành ngày hợp lệ; từ chối 29/02/2023 |
| `SMART` | Có thể điều chỉnh ngày vượt cuối tháng, ví dụ 29/02/2023 thành 28/02/2023 |
| `LENIENT` | Có thể cho phép ngày/tháng tràn để tính sang ngày, tháng khác |

`DateTimeFormatter.ofPattern(...)` mặc định có resolver style **`SMART`**, nên không được xem formatter tự tạo là `STRICT` nếu chưa cấu hình.

Cần phân biệt ký hiệu pattern:

- **`uuuu`**: proleptic year, phù hợp khi parse ngày ISO `LocalDate` bằng `STRICT` mà không yêu cầu chỉ định kỷ nguyên.
- **`yyyy`**: year-of-era. Khi dùng `STRICT` mà chuỗi không cung cấp era, có thể thiếu dữ liệu để resolve thành `LocalDate`. Với ngày ISO thuần, nên chọn `uuuu-MM-dd`.
- **`MM`** là tháng, **`mm`** là phút. **`YYYY`** là năm dựa theo tuần (*week-based-year*), không phải năm lịch thông thường.
- Nếu muốn từ chối cả chuỗi khác mẫu (ví dụ `"2024/02/29"` với mẫu `uuuu-MM-dd`), dùng đúng formatter đã chọn và xử lý `DateTimeParseException`.

## 6. Tạo ngày sai khác với cộng/trừ ngày tháng

`LocalDate.of(2025, 2, 29)` là **ngày không hợp lệ**. Tuy nhiên, `LocalDate.plusYears` và `plusMonths` có quy tắc điều chỉnh khi ngày cũ không tồn tại trong tháng/năm đích:

```java
System.out.println(LocalDate.of(2024, 2, 29).plusYears(1));  // 2025-02-28
System.out.println(LocalDate.of(2024, 1, 31).plusMonths(1)); // 2024-02-29
```

Việc điều chỉnh ấy phục vụ **phép tính ngày tháng**, không chứng minh rằng đầu vào `2025-02-29` hợp lệ. Ví dụ, chính sách sinh nhật 29/02 trong năm thường (28/02 hay 01/03) hoặc hạn thanh toán cuối tháng phải do nghiệp vụ quyết định rõ ràng.

Khi cần ngày cuối tháng, chọn `YearMonth.atEndOfMonth()` hoặc `TemporalAdjusters.lastDayOfMonth()` thay vì cộng cứng 30 hoặc 31 ngày.

## 7. Lỗi phổ biến và cách tránh

1. **Chỉ kiểm tra chia hết cho 4**: kết luận sai đối với 1900 hoặc 2100. Dùng `Year.isLeap`.
2. **Gán cố định tháng 2 là 28 ngày**: sẽ bác bỏ 29/02 ở năm nhuận. Dùng `YearMonth.lengthOfMonth`.
3. **Cho phép mọi ngày 1–31**: bỏ sót tháng 4/6/9/11 và tháng 2. Tạo `LocalDate` để kiểm tra toàn bộ.
4. **Dùng tháng bắt đầu từ 0**: `LocalDate.of` và `YearMonth.of` nhận số tháng **1–12**, khác với API cũ có thể dùng chỉ số 0.
5. **Để formatter tự sửa ngày**: `SMART`/`LENIENT` có thể trả ngày khác ngày đầu vào. Chọn `STRICT` nếu mục tiêu là xác thực.
6. **Nhầm `yyyy`, `uuuu`, `YYYY` hoặc `MM`, `mm`**: các ký hiệu có ý nghĩa khác nhau, nhất là khi parse chặt.
7. **Dùng `SimpleDateFormat` mà quên tính lenient**: một số thao tác parse kiểu cũ mặc định có thể điều chỉnh ngày sai; với mã mới, ưu tiên `java.time`.
8. **Cộng mili giây để suy ra tháng/năm**: các tháng dài khác nhau và thời lượng ngày địa phương có thể chịu ảnh hưởng DST. Dùng API ngày lịch.

`LocalDate` biểu diễn **ngày lịch**, không có giờ hoặc múi giờ. Tính hợp lệ của `2024-02-29` không phụ thuộc múi giờ; múi giờ chỉ cần thiết khi chuyển một **thời điểm** (ví dụ `Instant`) thành ngày địa phương, vì cùng một thời điểm có thể thuộc hai ngày khác nhau ở hai vùng.

## 8. Kiểm thử theo các ranh giới quan trọng

| Ca kiểm thử | Đầu vào | Mong đợi |
| --- | --- | --- |
| Năm nhuận bình thường | `2024-02-29` | Hợp lệ |
| Năm thường | `2023-02-29` | Bị từ chối |
| Thế kỷ không nhuận | `1900-02-29`; `2100-02-29` | Bị từ chối |
| Thế kỷ nhuận | `2000-02-29` | Hợp lệ |
| Tháng 30 ngày | `2024-04-30`; `2024-04-31` | Hợp lệ; bị từ chối |
| Giới hạn số tháng | `2024-12-31`; `2024-13-01` | Hợp lệ; bị từ chối |
| Giới hạn số ngày | `2024-01-01`; `2024-01-00` | Hợp lệ; bị từ chối |
| Parse theo mẫu nghiêm ngặt | `2024-02-29`; `2024/02/29` | Hợp lệ; bị từ chối |
| Cộng một năm từ ngày nhuận | `2024-02-29` cộng 1 năm | `2025-02-28` |

Ở JUnit, có thể dùng `assertThrows(DateTimeException.class, () -> LocalDate.of(2023, 2, 29))` cho thao tác tạo ngày và `assertThrows(DateTimeParseException.class, () -> LocalDate.parse("2023-02-29"))` cho chuỗi ngày sai; với ca hợp lệ, so sánh trực tiếp giá trị `LocalDate`.

## 9. Chọn API theo công việc

| Yêu cầu | API nên dùng |
| --- | --- |
| Năm có nhuận không? | `Year.isLeap(year)` |
| Một tháng trong năm có bao nhiêu ngày? | `YearMonth.of(year, month).lengthOfMonth()` |
| Ngày cuối tháng là ngày nào? | `YearMonth.of(year, month).atEndOfMonth()` |
| Ba số năm, tháng, ngày có tạo thành ngày thật không? | `LocalDate.of(year, month, day)`; xử lý `DateTimeException` |
| Chuỗi ISO ngày hợp lệ không? | `LocalDate.parse(text)` |
| Parse ngày theo mẫu riêng mà không điều chỉnh ngày sai | `DateTimeFormatter` với `ResolverStyle.STRICT` |
| Cộng ngày/tháng/năm | `LocalDate.plusDays/plusMonths/plusYears` và chính sách nghiệp vụ rõ ràng |

**Nguyên tắc cần nhớ:** xác định năm nhuận theo đầy đủ quy tắc 4/100/400; tính số ngày bằng **năm và tháng cụ thể**; dùng `LocalDate` và strict parsing để **từ chối ngày không tồn tại**. Đừng nhầm hành vi điều chỉnh hợp lệ của phép cộng ngày tháng với việc chấp nhận một đầu vào ngày sai.
