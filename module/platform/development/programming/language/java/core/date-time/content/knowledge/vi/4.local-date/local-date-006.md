# Thay một thành phần ngày và xử lý ngày cuối tháng với `LocalDate`

Giả sử hệ thống lập hóa đơn vào ngày **31/01** và cần xác định ngày thanh toán của tháng sau. Nếu chỉ đổi tháng từ 1 sang 2, ngày 31/02 sẽ không tồn tại. Ứng dụng nên làm gì: báo lỗi, lấy ngày cuối cùng của tháng 2, hay chuyển lịch sang ngày khác? Câu trả lời phụ thuộc **phương thức Java** được dùng và **quy tắc nghiệp vụ**.

`LocalDate` trong `java.time` (Java 8+, các ví dụ dùng Java 17+) biểu diễn ngày theo lịch ISO-8601, chỉ có **năm, tháng, ngày**, không chứa giờ hoặc múi giờ. Ta có thể thay từng thành phần bằng các phương thức `with...()`, cộng/trừ theo lịch với `plus...()`, hoặc tìm mốc như cuối tháng qua `YearMonth` và `TemporalAdjusters`.

Trong bài này, cần phân biệt ba hành vi:
- **Thay một giá trị ngày một cách nghiêm ngặt:** nếu giá trị không hợp lệ với tháng/năm hiện tại, Java báo lỗi.
- **Thay tháng hoặc năm:** Java tự điều chỉnh **ngày trong tháng** về ngày hợp lệ cuối cùng nếu cần.
- **Dịch chuyển tháng/năm:** Java giữ ngày trong tháng khi có thể, nếu không thì điều chỉnh về ngày cuối tháng đích; nhiều lần dịch chuyển có thể tạo kết quả khác một lần dịch chuyển trực tiếp.

## 1. `LocalDate` là bất biến: thay ngày tạo đối tượng mới

Một `LocalDate` có ba thành phần chính: `getYear()`, `getMonthValue()` và `getDayOfMonth()`. Các phương thức `with...()` trả về một giá trị `LocalDate`; chúng **không chỉnh sửa đối tượng gốc**.

~~~java
LocalDate original = LocalDate.of(2026, 1, 20);
LocalDate changed = original.withDayOfMonth(31);

// original = 2026-01-20
// changed  = 2026-01-31
~~~

Các đoạn mã nhỏ trong bài là **minh họa**, có thể cần `import java.time.LocalDate;` cùng các import liên quan. Phần ví dụ hoàn chỉnh phía dưới có đầy đủ import, tên lớp, lệnh biên dịch và kết quả chạy.

Nếu viết `original.withDayOfMonth(31);` nhưng không nhận giá trị trả về, biến `original` vẫn giữ ngày ban đầu. Đây là lỗi phổ biến khi mới làm quen API bất biến.

## 2. Thay riêng ngày, tháng, năm bằng `with...()`

### 2.1. `withDayOfMonth(int dayOfMonth)`: kiểm tra chặt chẽ ngày hợp lệ

Phương thức này thay **ngày trong tháng**, giữ nguyên tháng/năm:

~~~java
LocalDate date = LocalDate.of(2026, 5, 20);
LocalDate firstDay = date.withDayOfMonth(1);  // 2026-05-01
LocalDate lastDay = date.withDayOfMonth(31);  // 2026-05-31
~~~

Ngày cần thay phải tồn tại trong tháng/năm đang có. Với tháng 2/2025 chỉ có 28 ngày:

~~~java
LocalDate feb = LocalDate.of(2025, 2, 10);
LocalDate invalid = feb.withDayOfMonth(31); // ném DateTimeException
~~~

`withDayOfMonth(31)` **không** âm thầm đổi thành 28/02. Nếu giá trị là 0, âm, lớn hơn 31 hoặc vượt quá số ngày của tháng, phương thức ném `DateTimeException`. Nếu đang xử lý ngày do người dùng nhập, cần kiểm tra/tổ chức xử lý ngoại lệ thay vì mặc định Java sẽ tự sửa.

### 2.2. `withMonth(int month)`: giữ ngày nếu có thể, điều chỉnh nếu thiếu ngày

`withMonth` thay tháng, giữ năm. Nếu **ngày của tháng cũ vượt quá ngày cuối của tháng đích**, Java tự giảm xuống ngày cuối hợp lệ:

~~~java
LocalDate jan31 = LocalDate.of(2025, 1, 31);

LocalDate feb = jan31.withMonth(2); // 2025-02-28
LocalDate apr = jan31.withMonth(4); // 2025-04-30
LocalDate may = jan31.withMonth(5); // 2025-05-31
~~~

Năm nhuận ảnh hưởng kết quả:

~~~java
LocalDate mar31LeapYear = LocalDate.of(2024, 3, 31);
LocalDate feb2024 = mar31LeapYear.withMonth(2); // 2024-02-29
~~~

**Điểm phân biệt:** `withDayOfMonth(31)` trên tháng 2 báo lỗi; `withMonth(2)` từ ngày 31/01 có thể cho ngày 28/02 hoặc 29/02. `withMonth` chỉ chấp nhận tháng 1–12; tháng 0 hoặc 13 vẫn gây `DateTimeException`.

### 2.3. `withYear(int year)`: chú ý ngày 29/02

Tương tự thay tháng, khi thay năm mà ngày gốc không tồn tại trong năm mới, Java điều chỉnh ngày về mốc hợp lệ:

~~~java
LocalDate leapDay = LocalDate.of(2024, 2, 29);

LocalDate newYear = leapDay.withYear(2025); // 2025-02-28
LocalDate stillLeap = leapDay.withYear(2028); // 2028-02-29
~~~

Ví dụ trên cho thấy thay **năm** không luôn giữ nguyên số ngày. Khi đang quản lý sinh nhật 29/02, ngày kỷ niệm hay kỳ thanh toán, ứng dụng cần **chọn chính sách năm không nhuận** (28/02, 01/03 hoặc một quy tắc khác), không mặc định `withYear` là chính sách đúng cho mọi nghiệp vụ.

### 2.4. `withDayOfYear(int dayOfYear)`: thay ngày thứ mấy trong năm

Đây là phép thay **ngày thứ tự trong năm** chứ không phải ngày trong tháng:

~~~java
LocalDate first2024 = LocalDate.of(2024, 1, 1);
LocalDate day60 = first2024.withDayOfYear(60); // 2024-02-29

LocalDate first2025 = LocalDate.of(2025, 1, 1);
LocalDate day60Next = first2025.withDayOfYear(60); // 2025-03-01
~~~

Năm nhuận có 366 ngày, năm thường có 365 ngày. `withDayOfYear(366)` ở năm không nhuận ném `DateTimeException`. Dùng phương thức này khi đầu vào thực sự là **thứ tự ngày trong năm**, không thay cho `withDayOfMonth`.

### 2.5. `with(TemporalField, long)` và `with(TemporalAdjuster)`

Ngoài các phương thức chuyên biệt, `LocalDate` có `with(TemporalField, long)` để thay trường và `with(TemporalAdjuster)` để áp dụng quy tắc điều chỉnh:

~~~java
LocalDate date = LocalDate.of(2025, 1, 31);

LocalDate anotherFebruary =
        date.with(ChronoField.MONTH_OF_YEAR, 2); // 2025-02-28
LocalDate firstOfMonth =
        date.with(ChronoField.DAY_OF_MONTH, 1); // 2025-01-01
LocalDate lastOfMonth =
        date.with(TemporalAdjusters.lastDayOfMonth()); // 2025-01-31
~~~

Đoạn minh họa này cần import `java.time.temporal.ChronoField` và `java.time.temporal.TemporalAdjusters`. Thay `MONTH_OF_YEAR` có hành vi tương tự `withMonth`; thay `DAY_OF_MONTH` có hành vi tương tự `withDayOfMonth`. Dùng phương thức chuyên biệt khi đã biết trường cần đổi; dùng `TemporalAdjusters` cho các quy tắc như “ngày cuối tháng”.

## 3. Ngày cuối tháng là gì và cách xác định chính xác

Các tháng có 28, 29, 30 hoặc 31 ngày. Tháng 2 có 29 ngày trong **năm nhuận** theo lịch ISO (chia hết cho 4, trừ các năm thế kỷ không chia hết cho 400).

Thay vì tự viết bảng số ngày cho từng tháng, `LocalDate` cung cấp các hàm:

| API | Kết quả | Ví dụ |
| --- | --- | --- |
| `date.lengthOfMonth()` | Số ngày trong tháng của chính date | Tháng 2/2024 → 29 |
| `date.lengthOfYear()` | 365 hoặc 366 | Năm 2024 → 366 |
| `date.isLeapYear()` | Năm của date có nhuận hay không | Năm 2025 → false |
| `date.getDayOfMonth()` | Ngày hiện tại trong tháng | 28 ở ngày 28/02 |
| `date.withDayOfMonth(date.lengthOfMonth())` | Ngày cuối cùng của tháng hiện tại | 2025-02-28 |
| `date.with(TemporalAdjusters.lastDayOfMonth())` | Ngày cuối tháng theo bộ điều chỉnh | 2024-02-29 |
| `YearMonth.from(date).atEndOfMonth()` | Ngày cuối tháng từ một `YearMonth` | 2026-04-30 |

Ví dụ:

~~~java
LocalDate someDay = LocalDate.of(2024, 2, 10);

LocalDate lastDay1 =
        someDay.withDayOfMonth(someDay.lengthOfMonth());
LocalDate lastDay2 =
        someDay.with(TemporalAdjusters.lastDayOfMonth());

// lastDay1 = lastDay2 = 2024-02-29
~~~

Kiểm tra một ngày có phải cuối tháng hay không:

~~~java
boolean isMonthEnd =
        someDay.getDayOfMonth() == someDay.lengthOfMonth();
~~~

Đây là phép so sánh chính xác; không nên đoán “ngày 30 hoặc 31 luôn là cuối tháng”, vì cuối tháng 2 có thể là ngày 28 hoặc 29.

## 4. `YearMonth`: biểu diễn một tháng trước khi chọn ngày

Nếu nghiệp vụ xử lý **kỳ hóa đơn, kỳ lương, ngày cuối tháng hoặc lịch lặp theo tháng**, `YearMonth` là công cụ phù hợp. Nó giữ **năm và tháng** mà chưa gắn một ngày cụ thể:

~~~java
YearMonth feb2025 = YearMonth.of(2025, 2);

int length = feb2025.lengthOfMonth(); // 28
LocalDate firstDay = feb2025.atDay(1); // 2025-02-01
LocalDate endDay = feb2025.atEndOfMonth(); // 2025-02-28
~~~

`YearMonth.atDay(int)` kiểm tra ngày tồn tại: `YearMonth.of(2025, 2).atDay(31)` ném `DateTimeException`. Ngược lại, `atEndOfMonth()` tự xác định ngày hợp lệ cuối cùng. Có thể lấy `YearMonth.from(localDate)`, rồi gọi `plusMonths(n)` để chọn **tháng đích trước, ngày sau**.

Đây là lựa chọn thường rõ nghĩa hơn cách tạo một ngày giả định ngày 31 rồi liên tục thay tháng khi bài toán thực chất là “tháng nào và ngày cuối tháng đó”.

## 5. `plusMonths()` và `withMonth()`: cùng có thể điều chỉnh ngày, nhưng ý nghĩa khác

`withMonth(m)` đặt **tháng trong cùng năm** thành số `m`. `plusMonths(n)` đi **n tháng về trước/sau**, có thể sang năm khác. Cả hai đều áp dụng quy tắc điều chỉnh về ngày cuối tháng đích khi ngày gốc không tồn tại.

Ví dụ từ `2025-12-31`:

~~~java
LocalDate dec31 = LocalDate.of(2025, 12, 31);

LocalDate changeToJanuary = dec31.withMonth(1); // 2025-01-31
LocalDate moveOneMonth = dec31.plusMonths(1);   // 2026-01-31
~~~

Hai phép này khác nhau ở **năm**: `withMonth` không biểu diễn “tháng kế tiếp”. Nếu muốn dịch chuyển tháng thực sự, dùng `plusMonths` hoặc `minusMonths`.

Ví dụ từ `2025-01-31`:

~~~java
LocalDate jan31 = LocalDate.of(2025, 1, 31);

LocalDate nextMonth = jan31.plusMonths(1); // 2025-02-28
LocalDate twoMonthsDirect = jan31.plusMonths(2); // 2025-03-31
LocalDate twoSteps = jan31.plusMonths(1).plusMonths(1); // 2025-03-28
~~~

Kết quả khác nhau vì lần cộng đầu đã chuyển 31 thành 28; lần thứ hai cộng tiếp từ ngày 28, không còn thông tin ngày mong muốn ban đầu là 31.

**Kết luận thiết kế:** Không xây lịch lặp bằng cách lấy ngày đã điều chỉnh của kỳ trước làm “ngày gốc” nếu phải giữ **quy tắc ngày cố định/cuối tháng**. Hãy giữ ngày quy ước hoặc tháng gốc, rồi tính trực tiếp từng kỳ.

Điều tương tự có thể xảy ra với `plusYears()`: từ `2024-02-29` cộng 1 năm được `2025-02-28`; sau đó cộng 3 năm từ kết quả sẽ là `2028-02-28`, trong khi cộng trực tiếp 4 năm từ mốc gốc cho `2028-02-29`. Vì thế lịch kỷ niệm mỗi năm cần giữ quy tắc ban đầu nếu muốn ngày 29/02 quay lại trong năm nhuận.

## 6. Ba chính sách khác nhau cho “ngày cuối tháng”

Không có một chính sách phù hợp cho mọi bài toán. Hãy viết rõ quy tắc trước khi triển khai:

### Chính sách A: Ngày cuối cùng **bất kể ngày ban đầu**

Ví dụ “chốt sao kê **vào ngày cuối mọi tháng**”. Ta lấy từng `YearMonth` rồi gọi `atEndOfMonth()`:

~~~java
YearMonth start = YearMonth.of(2025, 1);

LocalDate jan = start.atEndOfMonth();              // 2025-01-31
LocalDate feb = start.plusMonths(1).atEndOfMonth(); // 2025-02-28
LocalDate mar = start.plusMonths(2).atEndOfMonth(); // 2025-03-31
LocalDate apr = start.plusMonths(3).atEndOfMonth(); // 2025-04-30
~~~

Cách này luôn duy trì **cuối tháng**, kể cả sau tháng 2. Dùng khi nghiệp vụ là “cuối kỳ tháng”.

### Chính sách B: Cố định ngày trong tháng, tháng nào thiếu thì lấy ngày cuối

Ví dụ “thanh toán ngày **30** hằng tháng; tháng 2 dùng ngày cuối tháng”. Giữ `desiredDay=30`, tính theo **tháng đích**:

~~~java
int desiredDay = 30;
YearMonth target = YearMonth.of(2025, 2);

int actualDay = Math.min(desiredDay, target.lengthOfMonth());
LocalDate payment = target.atDay(actualDay); // 2025-02-28
~~~

Tháng 3 thì tính lại từ `desiredDay=30`, kết quả là **30/03**, không bị kẹt ở ngày 28 do kế thừa giá trị tháng 2. Mức ngày cố định là phần riêng của quy tắc nghiệp vụ, không nên lấy từ đối tượng ngày đã được “kẹp” của kỳ trước.

### Chính sách C: Không có ngày yêu cầu thì báo lỗi/chọn quy tắc khác

Nếu người dùng chọn “31/02” cho một sự kiện chỉ được phép xảy ra đúng ngày họ nhập, tự dịch sang ngày 28 sẽ che giấu sai sót. Khi đó giữ kiểm tra nghiêm ngặt của `LocalDate.of(year, month, day)` hoặc `YearMonth.atDay(day)` và đưa thông báo sửa ngày. Một số miền như hợp đồng hoặc quy định pháp lý có thể cần quy tắc riêng thay vì tự kẹp.

Nếu yêu cầu là **ngày làm việc cuối tháng**, `atEndOfMonth()` chưa đủ: phải xét cuối tuần, lịch nghỉ lễ và địa phương. Chẳng hạn cuối tháng rơi vào Chủ nhật có thể cần chọn thứ Sáu trước đó hoặc ngày làm việc tiếp theo theo hợp đồng. Không tự đồng nhất “cuối tháng” với “ngày làm việc cuối tháng”.

## 7. Ví dụ Java 17+ chạy độc lập, kết quả xác định

Chương trình sau minh họa các phép thay thành phần, điều chỉnh ngày 31 sang tháng 2, năm nhuận, tính cuối tháng từ `YearMonth`, tính kỳ tiếp theo **giữ quy tắc cuối tháng**, và lỗi khi yêu cầu ngày không tồn tại.

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.temporal.TemporalAdjusters;

public class LocalDateMonthEndDemo {
    public static void main(String[] args) {
        LocalDate original = LocalDate.of(2025, 1, 31);

        System.out.println("Ban dau: " + original);
        System.out.println("Thay ngay: " + original.withDayOfMonth(15));
        System.out.println("Thay thang 2: " + original.withMonth(2));
        System.out.println("Cong 1 thang: " + original.plusMonths(1));
        System.out.println("Cong 2 thang: " + original.plusMonths(2));
        System.out.println("Cong 1 hai lan: "
                + original.plusMonths(1).plusMonths(1));

        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        System.out.println("Thay nam: " + leapDay.withYear(2025));
        System.out.println("Cuoi thang 2/2024: "
                + leapDay.with(TemporalAdjusters.lastDayOfMonth()));

        YearMonth base = YearMonth.from(original);
        for (int i = 0; i < 4; i++) {
            System.out.println("Ky +" + i + ": "
                    + base.plusMonths(i).atEndOfMonth());
        }

        try {
            LocalDate.of(2025, 2, 1).withDayOfMonth(31);
            System.out.println("31/02 hop le");
        } catch (DateTimeException e) {
            System.out.println("31/02 khong hop le");
        }

        System.out.println("Ban dau van la: " + original);
    }
}
~~~

Lưu với tên `LocalDateMonthEndDemo.java`, rồi chạy:

~~~bash
javac LocalDateMonthEndDemo.java
java LocalDateMonthEndDemo
~~~

Đầu ra chính xác:

~~~text
Ban dau: 2025-01-31
Thay ngay: 2025-01-15
Thay thang 2: 2025-02-28
Cong 1 thang: 2025-02-28
Cong 2 thang: 2025-03-31
Cong 1 hai lan: 2025-03-28
Thay nam: 2025-02-28
Cuoi thang 2/2024: 2024-02-29
Ky +0: 2025-01-31
Ky +1: 2025-02-28
Ky +2: 2025-03-31
Ky +3: 2025-04-30
31/02 khong hop le
Ban dau van la: 2025-01-31
~~~

Từng dòng đối chiếu với quy tắc:

1. `withDayOfMonth(15)` thay ngày từ 31 thành 15 trong chính tháng 1.
2. `withMonth(2)` và `plusMonths(1)` từ 31/01/2025 cùng ra 28/02/2025; kết quả trùng nhau **chỉ trong tình huống này**, không phải hai API luôn tương đương.
3. `plusMonths(2)` tính trực tiếp từ 31/01 cho 31/03; gọi `plusMonths(1)` hai lần mất ngày 31 sau khi đi qua tháng 2 nên cho 28/03.
4. `withYear(2025)` từ 29/02/2024 điều chỉnh về 28/02/2025.
5. `TemporalAdjusters.lastDayOfMonth()` và `YearMonth.atEndOfMonth()` tìm ngày cuối tháng dựa vào năm nhuận.
6. `YearMonth.from(original).plusMonths(i).atEndOfMonth()` tạo chuỗi ngày cuối tháng 31/01, 28/02, 31/03, 30/04 theo từng tháng đích, không kế thừa ngày 28.
7. `withDayOfMonth(31)` trên tháng 2 ném `DateTimeException` và được bắt lại.
8. Giá trị `original` không đổi vì `LocalDate` bất biến.

## 8. Cẩn thận khi thao tác nhiều thành phần liên tiếp

Thứ tự thao tác có thể ảnh hưởng kết quả, hoặc thậm chí tạo ngoại lệ:

~~~java
LocalDate jan31 = LocalDate.of(2025, 1, 31);

LocalDate a = jan31.withMonth(2).withDayOfMonth(20);
// 2025-02-20

LocalDate b = jan31.withDayOfMonth(20).withMonth(2);
// 2025-02-20
~~~

Ở ví dụ này hai đường đi trùng nhau vì ngày 20 hợp lệ trong cả hai tháng. Nhưng nếu đặt ngày 31 sau khi đã đổi sang tháng 2:

~~~java
LocalDate feb28 = jan31.withMonth(2);
LocalDate invalid = feb28.withDayOfMonth(31);
// DateTimeException: tháng 2/2025 không có ngày 31.
~~~

Muốn tạo ngày yêu cầu một cách rõ ràng, hãy xác định **năm/tháng mục tiêu**, kiểm tra số ngày tháng đó, sau đó tạo ngày theo chính sách:

~~~java
int targetYear = 2025;
int targetMonth = 2;
int requestedDay = 31;
YearMonth ym = YearMonth.of(targetYear, targetMonth);

LocalDate clamped = ym.atDay(
        Math.min(requestedDay, ym.lengthOfMonth())
); // 2025-02-28
~~~

Đoạn này giả định `requestedDay` đã được kiểm tra là số dương (1–31); `Math.min` không có nhiệm vụ kiểm tra đầu vào âm hoặc 0. Nếu “31/02” phải bị từ chối thì dùng `ym.atDay(requestedDay)` trực tiếp và xử lý `DateTimeException`, không thực hiện phép kẹp.

## 9. Một số trường hợp biên đáng kiểm thử

| Đầu vào | Thao tác | Kết quả đáng chú ý |
| --- | --- | --- |
| `2025-01-31` | `withMonth(2)` | `2025-02-28` |
| `2024-01-31` | `withMonth(2)` | `2024-02-29` |
| `2025-03-31` | `withMonth(4)` | `2025-04-30` |
| `2024-02-29` | `withYear(2025)` | `2025-02-28` |
| `2024-02-29` | `plusYears(4)` | `2028-02-29` |
| `2025-12-31` | `plusMonths(1)` | `2026-01-31` |
| `2025-12-31` | `withMonth(1)` | `2025-01-31` |
| `2025-02-01` | `withDayOfMonth(29)` | Ném `DateTimeException` |
| `2025-02-01` | `withDayOfYear(366)` | Ném `DateTimeException` |
| `2024-02-10` | `with(lastDayOfMonth())` | `2024-02-29` |
| `2025-01-31` | `plusMonths(1).plusMonths(1)` | `2025-03-28` |
| `2025-01-31` | `plusMonths(2)` | `2025-03-31` |

Nên kiểm tra thêm **quy tắc nghiệp vụ**: tháng sau khi thiếu ngày sẽ kẹp, báo lỗi, hay dời sang tháng tiếp; lịch có phải luôn ở cuối tháng; ngày làm việc tính theo lịch nghỉ nào; có được thay đổi ngày kỷ niệm 29/02 trong năm thường hay không.

## 10. Những hiểu lầm thường gặp

**“`withDayOfMonth(31)` sẽ tự chọn ngày cuối tháng.”** Sai: nó ném ngoại lệ nếu tháng có ít hơn 31 ngày. Dùng `with(TemporalAdjusters.lastDayOfMonth())` hoặc `YearMonth.atEndOfMonth()` khi chủ đích là cuối tháng.

**“`withMonth(2)` tương tự `plusMonths(1)`.”** Sai: `withMonth(2)` luôn chuyển sang **tháng 2 của cùng năm**, còn `plusMonths(1)` cộng thêm một tháng kể từ ngày ban đầu.

**“`plusMonths(1)` hai lần tương đương `plusMonths(2)`.”** Không luôn đúng do ngày có thể bị điều chỉnh khi qua tháng ngắn, làm mất ngày dự kiến ban đầu.

**“Một lần bị kẹp về ngày 28 thì lịch định kỳ phải tiếp tục ngày 28.”** Chỉ đúng nếu nghiệp vụ thật sự muốn như vậy. Với lịch cố định ngày 30, ngày 31 hay ngày cuối tháng, phải lưu **quy tắc gốc** và tính từng tháng mục tiêu.

**“`LocalDate` biết ngày ở múi giờ nào.”** Không. `LocalDate` chỉ giữ ngày theo lịch. Việc chuyển một ngày thành thời điểm đầu ngày của khu vực, nếu cần, là thao tác riêng với `ZoneId`; một số khu vực có lịch sử thay đổi giờ khiến đầu ngày không nhất thiết là 00:00.

**“Tháng có 30 ngày thì đó cũng là ngày làm việc cuối tháng.”** Không. `LocalDate` không tự biết cuối tuần, ngày lễ quốc gia hay lịch kinh doanh riêng.

## 11. Bài tập thực hành

1. Cho `LocalDate.of(2026, 1, 31)`. Dự đoán `withMonth(2)`, `plusMonths(1)`, `plusMonths(2)` và `plusMonths(1).plusMonths(1)`; giải thích vì sao hai phép cộng sau có thể cho ngày khác nhau.
2. Viết hàm `lastDayOfMonth(int year, int month)` trả về `LocalDate` bằng `YearMonth`; thử tháng 2/2024, 2/2025, 4/2026.
3. Viết hàm trả ngày thanh toán theo quy tắc “ngày 30 hằng tháng, tháng nào thiếu thì lấy ngày cuối”. Dùng `YearMonth` và thử tháng 2, tháng 3 trong hai năm nhuận/không nhuận. Đảm bảo sau tháng 2 lịch trở lại ngày 30.
4. Từ ngày `2024-02-29`, gọi `withYear(2025)` rồi `withYear(2028)`; so sánh với `LocalDate.of(2024,2,29).withYear(2028)`. Từ đó rút ra vì sao cần giữ mốc gốc cho lịch năm.
5. Một ứng dụng chỉ cho phép chọn ngày hợp lệ, không tự kẹp ngày. Hãy thử gọi `YearMonth.of(2025,2).atDay(31)` và xử lý lỗi hiển thị cho người nhập.
6. Viết hàm xác định **ngày làm việc cuối tháng** trong giả định đơn giản nghỉ thứ Bảy, Chủ nhật. Lấy `YearMonth.atEndOfMonth()` rồi lùi từng ngày khi rơi vào cuối tuần; giải thích vì sao bài toán thực tế còn phải xét ngày lễ.

**Ghi nhớ:** Với `LocalDate`, thay **ngày trong tháng** là kiểm tra nghiêm ngặt; thay **tháng/năm** hoặc cộng tháng/năm có thể tự điều chỉnh ngày. Khi cần “cuối tháng”, dùng `YearMonth.atEndOfMonth()` hay `TemporalAdjusters.lastDayOfMonth()`; khi cần lịch lặp, hãy giữ **quy tắc nghiệp vụ ban đầu** và tính từng kỳ từ năm/tháng mục tiêu.