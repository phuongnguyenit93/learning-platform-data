# Gắn ngày, tháng hoặc năm để tạo LocalDate

## 1. Ghép phần còn thiếu để có một ngày đầy đủ

Trong mô hình ngày theo lịch ISO, `LocalDate` biểu diễn đủ **năm, tháng và ngày**. Các kiểu chỉ chứa một phần của ngày có mục đích riêng:

- `Year`: một năm, chẳng hạn 2024.
- `YearMonth`: một năm-tháng, chẳng hạn 2024-02.
- `MonthDay`: một tháng-ngày chưa gắn năm, chẳng hạn 29/2.
- `Month`: một tháng trong năm, chẳng hạn `Month.FEBRUARY`.

Để tạo `LocalDate`, cần bổ sung đúng thông tin còn thiếu. Ví dụ, kỳ báo cáo `2024-02` cần thêm ngày trong tháng; ngày kỷ niệm 29/2 cần thêm năm cụ thể.

Việc bổ sung không phải lúc nào cũng chỉ là nối các số. Ngày 29/2 hợp lệ trong năm 2024 nhưng không hợp lệ trong năm 2023. Vì vậy, cần biết API sẽ **từ chối ngày không tồn tại** hay **điều chỉnh sang ngày hợp lệ**.

`LocalDate` không chứa giờ hay múi giờ. Sau khi ghép thành ngày đầy đủ, ta vẫn chưa có một thời điểm trên trục thời gian. Bài này chỉ xử lý việc ghép các phần của ngày.

## 2. Chọn đường ghép theo dữ liệu đang có

| Dữ liệu đã có | Phần cần bổ sung | Cách ghép | Kiểu kết quả |
| --- | --- | --- | --- |
| `YearMonth` | Ngày trong tháng | `yearMonth.atDay(day)` | `LocalDate` |
| `YearMonth` | Quy tắc chọn cuối tháng | `yearMonth.atEndOfMonth()` | `LocalDate` |
| `MonthDay` | Năm | `monthDay.atYear(year)` | `LocalDate` |
| `Year` | Tháng rồi ngày | `year.atMonth(month).atDay(day)` | `LocalDate` |
| `Year` và `MonthDay` | Không thiếu thành phần nữa | `year.atMonthDay(monthDay)` | `LocalDate` |
| `Year` | Số thứ tự ngày trong năm | `year.atDay(dayOfYear)` | `LocalDate` |
| Ba giá trị năm, tháng, ngày | Không thiếu thành phần nữa | `LocalDate.of(year, month, day)` | `LocalDate` |

Một chuỗi có thể đi qua kiểu trung gian. `year.atMonth(month)` mới cho `YearMonth`, chưa cho `LocalDate`; gọi tiếp `atDay(day)` mới bổ sung ngày trong tháng.

Nếu bắt đầu từ `Month`, có thể kết hợp với ngày bằng `MonthDay.of(month, day)`, rồi gắn năm; hoặc dùng trực tiếp `LocalDate.of(year, month, day)` khi đã có đủ ba phần. Hai đường này cần được lựa chọn theo chính sách xử lý ngày không hợp lệ, như các phần bên dưới.

## 3. YearMonth: bổ sung ngày trong tháng

`YearMonth` đã biết năm và tháng, nên có đủ ngữ cảnh để xác định ngày nào hợp lệ trong tháng đó.

Với `YearMonth.of(2024, 2)`:

- `atDay(1)` cho `2024-02-01`.
- `atDay(29)` cho `2024-02-29`.
- `atDay(30)` báo `DateTimeException`.

`atDay` không âm thầm chuyển ngày 30/2 sang tháng 3 hay lùi về cuối tháng. Ngày phải nằm trong phạm vi hợp lệ của năm-tháng đang xét. Có thể gọi `isValidDay(day)` trước nếu cần trả thông báo lỗi theo giao diện người dùng, hoặc gọi `atDay` rồi xử lý lỗi đúng yêu cầu.

Nếu yêu cầu là “ngày cuối kỳ”, hãy dùng `atEndOfMonth()` thay vì mã hóa cứng ngày 28, 30 hoặc 31:

| Kỳ | Ngày cuối kỳ |
| --- | --- |
| `YearMonth.of(2023, 2)` | `2023-02-28` |
| `YearMonth.of(2024, 2)` | `2024-02-29` |
| `YearMonth.of(2024, 4)` | `2024-04-30` |
| `YearMonth.of(2024, 12)` | `2024-12-31` |

Chọn ngày cuối tháng là một quy tắc rõ ràng, không phải cách xác thực một ngày tùy ý người dùng đã nhập. Nếu người dùng nhập ngày 31 cho tháng 4 mà yêu cầu phải giữ nguyên đầu vào, không được tự thay bằng `atEndOfMonth()` để dữ liệu được chấp nhận.

Các API kết hợp năm-tháng và ngày được mô tả tại [YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html).

## 4. MonthDay: bổ sung năm và xử lý 29/2

`MonthDay` phù hợp với một tháng-ngày lặp lại hằng năm, chưa xác định lần xuất hiện trong năm nào. `MonthDay.of(2, 29)` được phép tồn tại vì 29/2 có thật trong năm nhuận.

Khi gắn năm:

| Biểu thức | Kết quả |
| --- | --- |
| `MonthDay.of(2, 29).atYear(2024)` | `2024-02-29` |
| `MonthDay.of(2, 29).atYear(2023)` | `2023-02-28` |
| `MonthDay.of(12, 25).atYear(2024)` | `2024-12-25` |

Điểm cần nhớ: `atYear` **tự điều chỉnh 29/2 thành 28/2 trong năm thường**. Nó không báo lỗi trong tình huống đó.

Nếu yêu cầu là từ chối một tháng-ngày không tồn tại trong năm đích, kiểm tra trước bằng `Year.of(year).isValidMonthDay(monthDay)`, rồi chỉ ghép khi hợp lệ. Hàm `attachYearStrict` trong chương trình của bài làm đúng quy tắc này.

Một `MonthDay` không chấp nhận mọi cặp số. Chẳng hạn `MonthDay.of(4, 31)` bị từ chối ngay vì tháng 4 không bao giờ có ngày 31. Ngược lại, 29/2 cần thêm năm mới biết có thể giữ nguyên hay không. Hành vi gắn năm được quy định tại [MonthDay](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/MonthDay.html).

Không tự suy ra rằng mọi ngày kỷ niệm 29/2 đều phải chuyển sang 28/2. Đó là hành vi API; nghiệp vụ có thể yêu cầu báo lỗi, bỏ kỳ hoặc chuyển sang ngày khác. Phải chọn rõ chính sách trước khi lưu kết quả.

## 5. Year: bổ sung tháng và ngày theo hai đường khác nhau

### 5.1. Ghép tháng trước, rồi ghép ngày

Với `Year.of(2024)`, có thể gọi:

```java
// Đoạn minh họa bên trong một phương thức.
Year year = Year.of(2024);
YearMonth february = year.atMonth(Month.FEBRUARY);
LocalDate date = february.atDay(29);
```

Có thể viết gọn thành `year.atMonth(Month.FEBRUARY).atDay(29)`. Vì bước cuối là `YearMonth.atDay`, đường này từ chối ngày không hợp lệ. Đổi năm thành 2023 thì `atDay(29)` báo lỗi.

### 5.2. Ghép với MonthDay đã có

Nếu dữ liệu ban đầu là một `Year` và một `MonthDay`, `year.atMonthDay(monthDay)` ghép trực tiếp thành `LocalDate`.

Nhưng phương thức này cũng có quy tắc lùi 29/2 về 28/2 ở năm thường. Với cùng các phần năm 2023, tháng 2, ngày 29:

```text
Year.of(2023).atMonth(2).atDay(29)
→ DateTimeException

Year.of(2023).atMonthDay(MonthDay.of(2, 29))
→ 2023-02-28
```

Như vậy, hai chuỗi có vẻ chỉ khác cách viết lại không có cùng hợp đồng xác thực. Không đổi qua lại chỉ để rút ngắn mã nếu việc đó làm thay đổi chính sách xử lý ngày.

`Year` vẫn được giữ nguyên sau các phép ghép. Các phương thức tạo giá trị kết quả mới, không bổ sung trường trực tiếp vào đối tượng năm ban đầu. Xem các phép ghép tại [Year](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Year.html).

## 6. Year.atDay và YearMonth.atDay nhận hai loại “ngày”

Đây là chỗ dễ đọc nhầm vì tên phương thức giống nhau.

| Phương thức | Ý nghĩa tham số |
| --- | --- |
| `Year.atDay(int dayOfYear)` | Số thứ tự ngày trong cả năm |
| `YearMonth.atDay(int dayOfMonth)` | Số ngày trong tháng đã biết |

Ví dụ:

```text
Year.of(2024).atDay(29)          → 2024-01-29
YearMonth.of(2024, 2).atDay(29)  → 2024-02-29

Year.of(2024).atDay(60)          → 2024-02-29
Year.of(2023).atDay(60)          → 2023-03-01
```

`Year.atDay` không thể biết ta muốn tháng 2 nếu chỉ truyền số 29. Nó đếm từ ngày đầu năm.

Ngày thứ 366 chỉ hợp lệ trong năm nhuận. `Year.of(2023).atDay(366)` báo lỗi, còn năm 2024 cho 31/12. Nếu dữ liệu đã có năm và số thứ tự ngày trong năm, `LocalDate.ofYearDay(year, dayOfYear)` cũng diễn đạt đúng cấu trúc đó.

Tất cả các chỉ số lịch đang dùng bắt đầu từ 1: tháng 1, ngày đầu tháng 1, ngày đầu năm 1. Không đưa số 0 vào vì nhầm với chỉ số mảng.

## 7. Đã có đủ ba phần: dùng LocalDate.of

Khi đầu vào là năm, tháng và ngày cụ thể, `LocalDate.of` tạo trực tiếp một ngày và kiểm tra tính hợp lệ:

- `LocalDate.of(2024, 2, 29)` hợp lệ.
- `LocalDate.of(2023, 2, 29)` báo `DateTimeException`.
- `LocalDate.of(2024, Month.FEBRUARY, 29)` có cùng kết quả với dạng tháng bằng số.

Dạng nhận `Month` giúp mã nêu rõ tháng. Nếu tháng đến từ dữ liệu số, `Month.of(2)` là `Month.FEBRUARY`. Số tháng của `java.time` nằm trong 1..12, không dùng quy ước bắt đầu từ 0. Để lấy số tháng từ enum, dùng `getValue()`, không dùng `ordinal()`; xem [Month](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Month.html).

Không cần tạo một ngày gốc tùy ý rồi lần lượt gọi `withYear`, `withMonth`, `withDayOfMonth` để lắp ba phần. Những ngày trung gian có thể gây điều chỉnh hoặc lỗi không cần thiết. Khi ba phần cùng thuộc một đầu vào, hãy dùng API ghép trực tiếp thể hiện đúng hợp đồng.

## 8. Không tự điền thông tin còn thiếu bằng from()

`LocalDate.from(temporal)` cố lấy một ngày đầy đủ từ dữ liệu đã có; nó không tự thêm ngày 1 cho `YearMonth` hay lấy năm hiện tại cho `MonthDay`.

Vì vậy:

- `LocalDate.from(YearMonth.of(2024, 2))` báo lỗi vì thiếu ngày.
- `LocalDate.from(MonthDay.of(2, 29))` báo lỗi vì thiếu năm.
- `LocalDate.from(Year.of(2024))` báo lỗi vì thiếu tháng và ngày.

Cần đưa phần thiếu vào một cách có chủ đích bằng `atDay`, `atYear`, `atMonth` hoặc `of`. Nếu nghiệp vụ quy định “kỳ tháng được biểu diễn bằng ngày đầu tháng”, hãy viết `yearMonth.atDay(1)` và ghi rõ quy ước ấy. Không coi đó là hành vi mặc định của chuyển đổi.

Chiều ngược lại, trích một phần từ ngày đầy đủ là hợp lý:

- `Year.from(date)` lấy năm.
- `YearMonth.from(date)` lấy năm-tháng.
- `MonthDay.from(date)` lấy tháng-ngày.

Sau khi trích, thông tin bị bỏ không còn nằm trong giá trị mới. Nếu cần ghép lại giống ngày ban đầu, phải giữ hoặc truyền lại phần đó. Hợp đồng tạo và trích ngày được mô tả ở [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

## 9. Chương trình Java 17+ kiểm chứng các đường ghép

Lưu mã sau thành `AssembleLocalDate.java`. Đây là chương trình độc lập không cần thư viện ngoài.

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.Month;
import java.time.MonthDay;
import java.time.Year;
import java.time.YearMonth;
import java.util.Objects;

public class AssembleLocalDate {
    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Runnable action) {
        try {
            action.run();
        } catch (DateTimeException expected) {
            checks++;
            return;
        }
        throw new AssertionError("Expected DateTimeException");
    }

    private static LocalDate attachYearStrict(MonthDay monthDay, int number) {
        Objects.requireNonNull(monthDay, "monthDay");
        Year year = Year.of(number);
        if (!year.isValidMonthDay(monthDay)) {
            throw new DateTimeException("Month-day is invalid in year " + year);
        }
        return year.atMonthDay(monthDay);
    }

    public static void main(String[] args) {
        Year year = Year.of(2024);
        YearMonth period = YearMonth.of(2024, 2);
        MonthDay recurringDay = MonthDay.of(Month.FEBRUARY, 29);
        LocalDate expected = LocalDate.of(2024, 2, 29);

        LocalDate fromYearMonth = period.atDay(29);
        LocalDate fromMonthDay = recurringDay.atYear(2024);
        LocalDate fromYear = year.atMonth(Month.FEBRUARY).atDay(29);
        LocalDate fromParts = LocalDate.of(2024, Month.FEBRUARY, 29);
        eq(fromYearMonth, expected);
        eq(fromMonthDay, expected);
        eq(fromYear, expected);
        eq(fromParts, expected);
        eq(year.atMonthDay(recurringDay), expected);
        eq(attachYearStrict(recurringDay, 2024), expected);

        eq(period.atEndOfMonth(), expected);
        eq(YearMonth.of(2023, 2).atEndOfMonth(), LocalDate.of(2023, 2, 28));
        eq(YearMonth.of(2024, 4).atEndOfMonth(), LocalDate.of(2024, 4, 30));
        eq(period.isValidDay(29), true);
        eq(YearMonth.of(2023, 2).isValidDay(29), false);
        eq(recurringDay.atYear(2023), LocalDate.of(2023, 2, 28));
        eq(Year.of(2023).atMonthDay(recurringDay), LocalDate.of(2023, 2, 28));
        rejects(() -> attachYearStrict(recurringDay, 2023));
        rejects(() -> YearMonth.of(2023, 2).atDay(29));
        rejects(() -> Year.of(2023).atMonth(2).atDay(29));
        rejects(() -> LocalDate.of(2023, 2, 29));
        rejects(() -> MonthDay.of(Month.APRIL, 31));
        rejects(() -> period.atDay(0));
        rejects(() -> YearMonth.of(2024, 13));

        eq(year.atDay(60), expected);
        eq(year.atDay(29), LocalDate.of(2024, 1, 29));
        eq(LocalDate.ofYearDay(2024, 60), expected);
        eq(Year.of(2023).atDay(60), LocalDate.of(2023, 3, 1));
        rejects(() -> Year.of(2023).atDay(366));
        rejects(() -> LocalDate.from(period));
        rejects(() -> LocalDate.from(recurringDay));
        rejects(() -> LocalDate.from(year));

        eq(Year.from(expected), year);
        eq(YearMonth.from(expected), period);
        eq(MonthDay.from(expected), recurringDay);
        eq(year, Year.of(2024));
        eq(period, YearMonth.of(2024, 2));
        eq(recurringDay, MonthDay.of(2, 29));
        eq(Month.of(2), Month.FEBRUARY);

        System.out.println("fromYearMonth=" + fromYearMonth);
        System.out.println("fromMonthDay=" + fromMonthDay);
        System.out.println("fromYear=" + fromYear);
        System.out.println("fromParts=" + fromParts);
        System.out.println("adjustedCommonYear=" + recurringDay.atYear(2023));
        System.out.println("yearAtDay29=" + year.atDay(29));
        System.out.println("yearAtDay60=" + year.atDay(60));
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AssembleLocalDate.java
java AssembleLocalDate
```

Stdout:

```text
fromYearMonth=2024-02-29
fromMonthDay=2024-02-29
fromYear=2024-02-29
fromParts=2024-02-29
adjustedCommonYear=2023-02-28
yearAtDay29=2024-01-29
yearAtDay60=2024-02-29
PASS checks=35
```

Bốn dòng đầu cho thấy các đường ghép đều có thể tạo cùng ngày 29/2/2024 khi đủ phần và ngày hợp lệ. Dòng `adjustedCommonYear` cho thấy quy tắc điều chỉnh riêng của đường gắn năm vào `MonthDay`. Hai dòng sau làm rõ ý nghĩa tham số của `Year.atDay`.

Các hàm kiểm tra chủ động ném `AssertionError` khi sai nên không cần cờ `-ea`. Hàm `rejects` yêu cầu một thao tác ném `DateTimeException`; nếu thao tác âm thầm chấp nhận dữ liệu, chương trình thất bại.

Bộ kiểm tra còn xác nhận các trường hợp không có dòng in riêng: ngày 0, tháng 13, ngày 31/4, ngày 29/2 ở năm thường qua đường ghép nghiêm ngặt, và việc `LocalDate.from` không điền các phần thiếu.

## 10. Chọn cách ghép trong tình huống thực tế

| Tình huống | Cách phù hợp | Điều cần quyết định |
| --- | --- | --- |
| Người dùng chọn ngày cụ thể trong kỳ tháng | `YearMonth.atDay(day)` | Ngày không hợp lệ phải báo lỗi |
| Tính ngày cuối kỳ báo cáo | `YearMonth.atEndOfMonth()` | Đây là quy tắc chọn cuối tháng |
| Lập ngày kỷ niệm trong năm đã chọn | `MonthDay.atYear(year)` hoặc hàm kiểm tra trước | Có cho phép lùi 29/2 không? |
| Nhận đủ ba trường năm/tháng/ngày | `LocalDate.of` | Xác thực chính xác ngày được nhập |
| Nhận số thứ tự ngày trong năm | `Year.atDay` hoặc `LocalDate.ofYearDay` | Không nhầm với ngày trong tháng |
| Chỉ có năm báo cáo, chưa có ngày | Giữ `Year` | Chưa cần tạo `LocalDate` |

Không phải dữ liệu thiếu phần nào cũng phải được ép thành ngày đầy đủ ngay. Nếu chỉ lưu kỳ báo cáo tháng, giữ `YearMonth` có thể diễn đạt chính xác hơn việc tự thêm ngày. Chỉ tạo `LocalDate` khi thao tác kế tiếp thực sự cần một ngày và phần bổ sung đã có nguồn hoặc quy tắc rõ ràng.

## 11. Lỗi thường gặp và thực hành

Các lỗi cần tránh:

- Dùng `Year.atDay(29)` để biểu diễn 29/2: phương thức đang chọn ngày thứ 29 của năm.
- Cho rằng mọi phương thức ghép đều từ chối ngày sai: `MonthDay.atYear` và `Year.atMonthDay` có điều chỉnh ngày nhuận.
- Dùng ngày cuối tháng để che ngày người dùng nhập không hợp lệ.
- Để năm hiện tại hoặc ngày đầu tháng xuất hiện ngầm trong dữ liệu chỉ có một phần của ngày.
- Đổi số tháng từ 1..12 sang 0..11 do mang quy ước của API khác.
- Mong các phần ban đầu biến thành đối tượng nhiều trường hơn sau lời gọi: các kiểu này bất biến, cần giữ giá trị trả về.

Thực hành:

1. **Tạo ngày 15 của kỳ `2025-04`.** Dùng `YearMonth.of(2025, 4).atDay(15)`; kết quả `2025-04-15`.

2. **Tạo ngày cuối kỳ `2025-02`.** Dùng `atEndOfMonth()`; kết quả `2025-02-28`. Không thử ngày 31 rồi trông đợi thư viện tự sửa.

3. **Gắn năm 2100 vào tháng-ngày 29/2.** Đường `atYear` cho `2100-02-28`; hàm `attachYearStrict` phải báo lỗi. Hãy chọn đường đúng với yêu cầu trước khi chạy.

4. **Dự đoán `Year.of(2025).atDay(32)`.** Kết quả `2025-02-01`, vì đây là ngày thứ 32 trong năm.

5. **Có `Month.APRIL`, năm 2025 và ngày 31.** `LocalDate.of` phải từ chối. Việc các phần riêng lẻ đều trông có vẻ đúng không làm tổ hợp của chúng trở thành một ngày hợp lệ.

Trước mỗi phép ghép, hãy chỉ ra dữ liệu đã có, phần còn thiếu và chính sách khi tổ hợp không tồn tại. Ba thông tin đó quyết định phương thức tạo `LocalDate` nên dùng.
