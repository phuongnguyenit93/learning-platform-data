# LocalDate: Tạo ngày từ năm, tháng, ngày và ngày thứ bao nhiêu trong năm

`LocalDate` trong Java Date-Time API (`java.time`) biểu diễn **một ngày trên lịch ISO-8601**, ví dụ `2024-02-29`. Nó có năm, tháng, ngày nhưng **không chứa giờ, múi giờ hoặc độ lệch UTC**. Khi hệ thống nhận dữ liệu ngày dưới hai dạng khác nhau — bộ **năm/tháng/ngày** hoặc **năm/ngày thứ mấy trong năm** — ta có thể tạo cùng một `LocalDate` bằng các factory method khác nhau.

Sau bài học, bạn có thể:
- Dùng `LocalDate.of(year, month, dayOfMonth)` và biến thể nhận `Month` để tạo ngày lịch.
- Dùng `LocalDate.ofYearDay(year, dayOfYear)` khi đầu vào là số thứ tự ngày trong năm.
- Chuyển đổi giữa hai cách biểu diễn thông qua `getYear()`, `getMonthValue()`, `getDayOfMonth()` và `getDayOfYear()`.
- Xử lý đúng năm nhuận, ngày 29/02 và đầu vào không hợp lệ, tránh nhầm chỉ số ngày với epoch day.

## 1. Hai cách mô tả cùng một ngày

Giả sử có ngày **29/02/2024**. Có thể mô tả ngày đó theo hai cách:

| Cách biểu diễn | Dữ liệu đầu vào | Ý nghĩa |
|---|---|---|
| Năm, tháng, ngày trong tháng | `year=2024`, `month=2`, `dayOfMonth=29` | Ngày 29 của tháng 2 năm 2024 |
| Năm và ngày thứ mấy trong năm | `year=2024`, `dayOfYear=60` | Ngày thứ 60 tính từ 01/01/2024 |

Cả hai là **cùng ngày lịch**: vì 2024 là năm nhuận, tháng 2 có 29 ngày. Tính từ 01/01: 31 ngày tháng 1 + 29 ngày tháng 2 = **ngày thứ 60 là 29/02**.

Số thứ tự `dayOfYear` được **đếm từ 1**, nên 01/01 luôn là ngày thứ 1. Số lớn nhất là **365** trong năm thường hoặc **366** trong năm nhuận. Đây không phải chỉ số mảng bắt đầu từ 0.

## 2. Tạo ngày từ năm, tháng, ngày: `LocalDate.of(...)`

Java cung cấp hai overload chính:

~~~java
LocalDate date1 = LocalDate.of(2024, 2, 29);
LocalDate date2 = LocalDate.of(2024, Month.FEBRUARY, 29);
~~~

Cần import:

~~~java
import java.time.LocalDate;
import java.time.Month;
~~~

**Overload 1 — tháng là số nguyên:**

~~~java
LocalDate.of(int year, int month, int dayOfMonth)
~~~

- `year`: năm theo lịch ISO (ví dụ 2024).
- `month`: **1 đến 12**; `1` là tháng 1, `12` là tháng 12.
- `dayOfMonth`: ngày từ 1 đến số ngày thực có trong **tháng cụ thể của năm cụ thể**. Không phải lúc nào giá trị 1–31 cũng hợp lệ.
- Kết quả: đối tượng `LocalDate`, ví dụ `2024-02-29`.

**Overload 2 — tháng là enum `Month`:**

~~~java
LocalDate.of(int year, Month month, int dayOfMonth)
~~~

- `Month.JANUARY`, `Month.FEBRUARY`, ..., `Month.DECEMBER` mô tả tháng bằng tên có kiểu dữ liệu rõ ràng.
- Dùng khi mã nguồn đã có biến `Month` hoặc muốn code tự mô tả hơn: `LocalDate.of(2024, Month.FEBRUARY, 29)`.
- `Month.FEBRUARY.getValue()` trả `2`; ngược lại `Month.of(2)` trả `Month.FEBRUARY`.
- Cả hai overload tạo cùng một ngày; không nên viết `Month` rồi cộng/trừ 1 như chỉ số mảng.

`LocalDate.of` **kiểm tra tính hợp lệ của ngày**. Các trường hợp `month=0`, `month=13`, `dayOfMonth=0`, `2023-02-29` và `2024-04-31` sẽ bị từ chối bằng `DateTimeException`. Cần hiểu ngày hợp lệ theo **cả tháng và năm**, chứ không chỉ mỗi ngày nằm trong khoảng 1–31.

Đối tượng `LocalDate` bất biến (*immutable*); việc tạo hay tính ngày mới không làm thay đổi ngày đã có.

## 3. Tạo ngày từ năm và số thứ tự ngày trong năm: `ofYearDay(...)`

Khi dữ liệu đầu vào chứa năm và số thứ tự của ngày trong năm, dùng:

~~~java
LocalDate.ofYearDay(int year, int dayOfYear)
~~~

Ví dụ:

~~~java
LocalDate first = LocalDate.ofYearDay(2024, 1);    // 2024-01-01
LocalDate sixtieth = LocalDate.ofYearDay(2024, 60); // 2024-02-29
LocalDate last = LocalDate.ofYearDay(2024, 366);    // 2024-12-31
~~~

Ở năm thường `2023`, cùng `dayOfYear=60` lại là **01/03/2023**. Số thứ tự ngày **phụ thuộc vào năm**, đặc biệt ở các ngày từ tháng 3 trở đi khi so sánh năm nhuận và năm thường.

| `dayOfYear` | Năm 2023 (không nhuận) | Năm 2024 (nhuận) |
|---:|---|---|
| `1` | `2023-01-01` | `2024-01-01` |
| `31` | `2023-01-31` | `2024-01-31` |
| `32` | `2023-02-01` | `2024-02-01` |
| `59` | `2023-02-28` | `2024-02-28` |
| `60` | `2023-03-01` | `2024-02-29` |
| `61` | `2023-03-02` | `2024-03-01` |
| `365` | `2023-12-31` | `2024-12-30` |
| `366` | **Không hợp lệ** | `2024-12-31` |

`LocalDate.ofYearDay(2023, 366)` sẽ ném `DateTimeException`. Tương tự, `dayOfYear=0` hay giá trị âm luôn không hợp lệ.

**Không nhầm `ofYearDay` với `ofEpochDay`.** `LocalDate.ofYearDay(2024, 60)` có nghĩa “ngày thứ 60 của năm 2024”. `LocalDate.ofEpochDay(60)` lại có nghĩa “60 ngày sau 1970-01-01 theo phép đếm epoch day”; đó là hệ tọa độ khác.

## 4. Đọc thông tin để kiểm tra kết quả hoặc chuyển đổi hai chiều

Sau khi tạo `LocalDate`, dùng getter tương ứng:

| Phương thức | Với `2024-02-29` | Ý nghĩa |
|---|---|---|
| `getYear()` | `2024` | Năm |
| `getMonth()` | `Month.FEBRUARY` | Tháng dạng enum |
| `getMonthValue()` | `2` | Tháng dạng số 1–12 |
| `getDayOfMonth()` | `29` | Ngày trong tháng |
| `getDayOfYear()` | `60` | Ngày thứ mấy của năm |

~~~java
LocalDate original = LocalDate.of(2024, 2, 29);

int year = original.getYear();             // 2024
int ordinal = original.getDayOfYear();     // 60
LocalDate restored = LocalDate.ofYearDay(year, ordinal);
// restored.equals(original) == true
~~~

Chiều ngược lại:

~~~java
LocalDate fromOrdinal = LocalDate.ofYearDay(2024, 60);
LocalDate fromParts = LocalDate.of(
        fromOrdinal.getYear(),
        fromOrdinal.getMonthValue(),
        fromOrdinal.getDayOfMonth());
// fromParts.equals(fromOrdinal) == true
~~~

Đây là một tính chất hữu ích khi đọc/ghi CSV hoặc JSON lưu năm + ngày thứ tự: nếu cả năm và số thứ tự ngày hợp lệ, có thể dựng `LocalDate`, rồi truy ngược lại chính xác bộ năm/tháng/ngày.

**Phân biệt ba khái niệm dễ nhầm:**

- `getDayOfMonth()`: ngày thứ bao nhiêu **trong tháng**, ví dụ 29.
- `getDayOfYear()`: ngày thứ bao nhiêu **trong năm**, ví dụ 60.
- `getDayOfWeek()`: **thứ trong tuần**, trả `DayOfWeek` như `THURSDAY` cho 29/02/2024. Đây không phải số ngày đã trôi qua trong năm.

## 5. Năm nhuận: vì sao ảnh hưởng đến `dayOfYear`?

Theo quy tắc lịch ISO/Gregorian mở rộng mà `LocalDate` sử dụng:
- Năm chia hết cho 4 thường là năm nhuận.
- Năm chia hết cho 100 **không** nhuận, trừ khi đồng thời chia hết cho 400.
- Vì vậy, 2024 và 2000 nhuận; 2023 và 1900 không nhuận.

Java đã cung cấp API để xử lý quy tắc này; không cần tự viết phép tính để tạo ngày:

~~~java
boolean leap = Year.isLeap(2024); // true
LocalDate date = LocalDate.of(2024, 2, 29);
boolean dateYearIsLeap = date.isLeapYear(); // true
int daysInYear = date.lengthOfYear();       // 366
int daysInMonth = date.lengthOfMonth();     // 29
~~~

Cần import `java.time.Year` nếu dùng `Year.isLeap(...)`.

Giá trị hợp lệ của `dayOfYear` có thể kiểm tra dựa trên `lengthOfYear()` của một ngày thuộc năm đó, hoặc bằng `Year.of(year).length()`, trả 365 hay 366. `YearMonth.of(year, month).isValidDay(day)` giúp kiểm tra đầu vào năm/tháng/ngày trước khi tạo đối tượng.

**Đừng tự cộng ngày cố định để đổi `dayOfYear` ra ngày tháng**, đặc biệt sau tháng 2. Hãy dùng `LocalDate.ofYearDay`: thư viện xử lý tự động năm nhuận và ranh giới các tháng.

## 6. Chương trình Java 17 chạy độc lập

Tạo tệp **`LocalDateCreationDemo.java`**:

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.Month;
import java.time.Year;
import java.time.YearMonth;

public class LocalDateCreationDemo {
    public static void main(String[] args) {
        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        LocalDate byMonth = LocalDate.of(2024, Month.FEBRUARY, 29);
        LocalDate byDayOfYear = LocalDate.ofYearDay(2024, 60);

        System.out.println("from parts = " + leapDay);
        System.out.println("from Month = " + byMonth);
        System.out.println("from day-of-year = " + byDayOfYear);
        System.out.println("three dates equal = "
                + (leapDay.equals(byMonth) && byMonth.equals(byDayOfYear)));
        System.out.println("2024-02-29 ordinal = " + leapDay.getDayOfYear());
        System.out.println("2024-03-01 ordinal = "
                + LocalDate.of(2024, 3, 1).getDayOfYear());
        System.out.println("2023 ordinal 60 = " + LocalDate.ofYearDay(2023, 60));
        System.out.println("2024 ordinal 366 = " + LocalDate.ofYearDay(2024, 366));
        System.out.println("2024 is leap = " + Year.isLeap(2024));
        System.out.println("2023 is leap = " + Year.isLeap(2023));
        System.out.println("2024 Feb 29 valid = "
                + YearMonth.of(2024, 2).isValidDay(29));
        System.out.println("2023 Feb 29 valid = "
                + YearMonth.of(2023, 2).isValidDay(29));
        System.out.println("2024 length = " + leapDay.lengthOfYear());

        try {
            LocalDate.of(2023, 2, 29);
        } catch (DateTimeException e) {
            System.out.println("invalid calendar date rejected");
        }

        try {
            LocalDate.ofYearDay(2023, 366);
        } catch (DateTimeException e) {
            System.out.println("invalid ordinal day rejected");
        }
    }
}
~~~

Chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

~~~bash
javac LocalDateCreationDemo.java
java LocalDateCreationDemo
~~~

Kết quả được kiểm chứng khi biên dịch với `javac --release 17`:

~~~text
from parts = 2024-02-29
from Month = 2024-02-29
from day-of-year = 2024-02-29
three dates equal = true
2024-02-29 ordinal = 60
2024-03-01 ordinal = 61
2023 ordinal 60 = 2023-03-01
2024 ordinal 366 = 2024-12-31
2024 is leap = true
2023 is leap = false
2024 Feb 29 valid = true
2023 Feb 29 valid = false
2024 length = 366
invalid calendar date rejected
invalid ordinal day rejected
~~~

**Giải thích kết quả:**

1. Ba cách dựng ngày `2024-02-29` cho ra các đối tượng có giá trị bằng nhau.
2. 29/02 là ngày thứ **60** trong năm nhuận 2024; hôm sau (01/03) là ngày thứ **61**.
3. Năm thường 2023 không có 29/02; ngày thứ 60 rơi vào **01/03**.
4. Năm nhuận dài 366 ngày, có ngày thứ 366 là 31/12; năm thường chỉ có 365 ngày.
5. API kiểm tra hợp lệ giúp tránh tạo ngày sai; nếu vẫn đưa dữ liệu không hợp lệ cho factory, `DateTimeException` được ném và chương trình có thể xử lý ở ranh giới nhập liệu.

Việc bắt `DateTimeException` trong ví dụ dùng để minh họa hành vi lỗi. Trong ứng dụng thật, nên giải thích lỗi đầu vào cho người dùng hoặc trả thông báo hợp lệ ở API, thay vì im lặng bỏ qua.

## 7. Áp dụng với dữ liệu đầu vào và lỗi thường gặp

### Trường hợp nhận ba thành phần từ biểu mẫu

Ví dụ biểu mẫu cung cấp `year=2024`, `month=2`, `day=29`. Với dữ liệu đã được chuyển sang số nguyên và kiểm tra ràng buộc đầu vào, có thể dùng:

~~~java
int year = 2024;
int month = 2;
int day = 29;
YearMonth yearMonth = YearMonth.of(year, month);
if (!yearMonth.isValidDay(day)) {
    throw new IllegalArgumentException("Ngày không tồn tại trong tháng và năm");
}
LocalDate result = LocalDate.of(year, month, day);
~~~

*Đoạn này là mã minh họa trong một phương thức* và cần import `LocalDate`, `YearMonth`. Nếu chính `month` hoặc `year` vượt phạm vi hợp lệ, `YearMonth.of(...)` cũng có thể ném `DateTimeException`; cần xử lý ngoại lệ tại ranh giới nhập liệu. `isValidDay(...)` là cách hỏi ngày tháng hợp lệ, nhưng không thay thế hoàn toàn việc xử lý dữ liệu đầu vào sai.

### Trường hợp nhận năm và số thứ tự ngày

Một nguồn dữ liệu có thể lưu hai cột `year=2024` và `ordinalDay=60`, thay vì ba cột năm/tháng/ngày:

~~~java
int year = 2024;
int ordinalDay = 60;
int daysInYear = Year.of(year).length();
if (ordinalDay < 1 || ordinalDay > daysInYear) {
    throw new IllegalArgumentException("Ngày thứ tự ngoài phạm vi của năm");
}
LocalDate result = LocalDate.ofYearDay(year, ordinalDay);
~~~

*Đoạn này cũng là mã minh họa trong một phương thức*, với import `java.time.Year` và `java.time.LocalDate`. `Year.of(year)` có thể ném ngoại lệ nếu năm không nằm trong dải hỗ trợ. Điểm quan trọng là độ dài của năm phải được quyết định bởi **chính năm đang xét**.

### Những lỗi phổ biến

| Lỗi | Điều xảy ra | Cách xử lý |
|---|---|---|
| Dùng tháng `0` cho tháng 1 | Tháng của `LocalDate.of` bắt đầu tại 1; `0` không hợp lệ | Dùng `1` cho tháng 1 |
| Dùng ngày thứ `0` cho 01/01 | `ofYearDay(year, 0)` không hợp lệ | Dùng `1` cho 01/01 |
| Coi 29/02 hợp lệ mọi năm | `LocalDate.of(2023, 2, 29)` ném `DateTimeException` | Xét năm nhuận hoặc dùng `YearMonth.isValidDay` |
| Coi ngày thứ 60 luôn là 01/03 | Sai trong năm nhuận | Gọi `ofYearDay(year, 60)` với năm tương ứng |
| Cho rằng ngày thứ 366 tồn tại mọi năm | Năm thường chỉ có 365 ngày | `Year.of(year).length()` hoặc xử lý ngoại lệ |
| Nhầm `dayOfYear` và `dayOfMonth` | Một cái tính trong năm, một cái tính trong tháng | Dùng `getDayOfYear()` và `getDayOfMonth()` đúng nghĩa |
| Nhầm `ofYearDay` và `ofEpochDay` | Epoch day đếm từ 1970-01-01, không bắt đầu lại mỗi năm | Dùng factory tương ứng với hợp đồng dữ liệu |
| Tự tính số ngày bằng `(month-1)*30+day` | Tháng dài khác nhau và có năm nhuận | Dùng `LocalDate` để chuyển đổi |
| Dùng `LocalDate.now()` để kiểm chứng ví dụ cố định | Kết quả phụ thuộc đồng hồ/múi giờ môi trường | Dùng `of` / `ofYearDay` với dữ liệu cố định khi học và test |
| Nghĩ `LocalDate` chứa giờ UTC | Nó chỉ là ngày lịch, không mang múi giờ | Chỉ gắn `ZoneId` khi cần diễn giải thành thời điểm thực |

**Lưu ý phạm vi:** Ngày lịch khác timestamp. Cả `LocalDate.of(2024, 2, 29)` và `LocalDate.ofYearDay(2024, 60)` đều tạo **ngày**, chưa xác định một thời điểm UTC duy nhất. Muốn chuyển ngày lịch sang thời điểm cụ thể phải có quy tắc về múi giờ và giờ trong ngày, ví dụ `date.atStartOfDay(zone)`. Việc diễn giải như vậy là một bước nghiệp vụ riêng.

## 8. Tự kiểm tra

1. Ngày `2024-01-01` có `getDayOfYear()` bằng bao nhiêu? **1**, không phải 0.
2. `LocalDate.ofYearDay(2024, 60)` tạo ngày nào? **2024-02-29**.
3. `LocalDate.ofYearDay(2023, 60)` tạo ngày nào? **2023-03-01**.
4. Cùng đầu vào `year=2024, month=2, day=29`, hai overload `of(2024,2,29)` và `of(2024, Month.FEBRUARY,29)` có bằng nhau không? **Có**.
5. Tại sao `LocalDate.ofYearDay(2023, 366)` bị lỗi? Vì **2023 không nhuận** và chỉ có **365** ngày.
6. Dùng phương thức nào để lấy số ngày của năm hiện tại từ `LocalDate`? **`lengthOfYear()`**; muốn kiểm tra năm nhuận dùng **`isLeapYear()`**.
7. Nếu đầu vào là `year=2024, ordinalDay=61`, ngày là gì? **2024-03-01**.
8. Có thể thay `LocalDate.ofYearDay(2024, 60)` bằng `LocalDate.ofEpochDay(60)` không? **Không**, vì ý nghĩa hai giá trị `60` khác nhau.

**Ghi nhớ:** Tạo ngày từ **năm–tháng–ngày** bằng `LocalDate.of(...)`; tạo ngày từ **năm–thứ tự ngày trong năm** bằng `LocalDate.ofYearDay(...)`. Dùng `getDayOfYear()` để đọc lại số thứ tự, luôn đếm từ **1**, và luôn xét **năm nhuận** khi làm việc với 29/02 hoặc ngày thứ 366.

### Tài liệu tham khảo

- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html)
- [Java SE 17 — Year](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Year.html)
- [Java SE 17 — YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html)
- [Java SE 17 — Month](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Month.html)
