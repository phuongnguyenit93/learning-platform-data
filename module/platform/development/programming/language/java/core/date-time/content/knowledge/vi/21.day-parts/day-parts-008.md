# Lựa chọn kiểu thành phần thay cho số nguyên hoặc chuỗi tùy ý

## 1. Kiểu dữ liệu nên nói rõ dữ liệu có nghĩa gì

Một số nguyên `2` có thể là tháng 2, ngày thứ 2 trong tháng, số lượng bài học hoặc mã trạng thái. Một chuỗi `"2024-02"` có thể là kỳ báo cáo, nhưng kiểu `String` vẫn chấp nhận `"tháng sau"`, `"2024-13"` và chuỗi rỗng.

Khi dữ liệu mang ý nghĩa lịch rõ ràng, các kiểu thành phần của `java.time` giúp đưa ý nghĩa đó vào mô hình:

- `Year`: một năm.
- `YearMonth`: một năm-tháng.
- `MonthDay`: một tháng-ngày chưa gắn năm.
- `Month`: một tháng trong năm.
- `DayOfWeek`: một thứ trong tuần.

Mục tiêu không phải thay mọi số và chuỗi bằng đối tượng. Mục tiêu là dùng kiểu có cấu trúc tương ứng với điều nghiệp vụ thực sự biết. Nếu dữ liệu chỉ là số lượng bài học, `int` có thể phù hợp; nếu dữ liệu là kỳ học tập tháng 2/2024, `YearMonth` biểu đạt chính xác hơn một số hay chuỗi chưa xác thực.

Các kiểu của `java.time` sử dụng trong bài là các giá trị bất biến theo lịch ISO. Chúng cung cấp phép tạo, phân tích, so sánh và thao tác theo ý nghĩa lịch, thay vì để từng nơi tự xử lý ký tự hoặc số. Tổng quan mô hình có ở [java.time](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html).

## 2. Chọn kiểu theo phần thông tin thực sự có

| Dữ liệu nghiệp vụ | Kiểu phù hợp | Vì sao |
| --- | --- | --- |
| Năm tốt nghiệp hoặc năm báo cáo | `Year` | Chưa có tháng/ngày cụ thể |
| Kỳ báo cáo tháng 2/2024 | `YearMonth` | Cần cả năm và tháng, chưa cần ngày |
| Ngày kỷ niệm lặp lại vào 25/12 | `MonthDay` | Cần tháng-ngày, chưa chỉ định lần xuất hiện ở năm nào |
| Tháng bắt đầu một mùa, chẳng hạn tháng 6 | `Month` | Là tháng trong năm, không phải một kỳ cụ thể |
| Thứ học hằng tuần, chẳng hạn thứ Hai | `DayOfWeek` | Là thứ trong tuần, chưa có ngày lịch |
| Ngày sinh đầy đủ để tính tuổi | `LocalDate` | Cần giữ cả năm sinh, tháng và ngày |

Hai phân biệt quan trọng:

- `Month.FEBRUARY` không thay cho `YearMonth.of(2024, 2)`: giá trị tháng không chứa năm.
- `MonthDay.of(12, 25)` không thay cho ngày sinh đầy đủ: bỏ năm sinh thì không còn đủ dữ liệu để tính tuổi.

Không tự thêm ngày 1 vào kỳ tháng chỉ để dùng `LocalDate`, nếu nghiệp vụ không có ngày đó. Tương tự, không tự thêm năm hiện tại vào một ngày kỷ niệm chỉ để làm dữ liệu trông đầy đủ. Khi cần tạo một ngày cụ thể, phần bổ sung phải xuất phát từ yêu cầu rõ ràng.

## 3. Số nguyên và chuỗi tùy ý làm phát sinh lỗi gì?

### 3.1. Các tham số cùng kiểu rất dễ đổi vị trí

Một hàm nhận riêng `int year` và `int month` không giúp trình biên dịch phân biệt hai vai trò đó. Đổi vị trí đối số vẫn có thể biên dịch, dù tháng 2024 vô nghĩa.

Hàm nhận một `YearMonth period` gom hai phần thành một giá trị đã được tạo hợp lệ. Bên gọi phải đưa vào đúng loại đối tượng; một số lượng bài học không thể vô tình được truyền vào chỗ kỳ tháng.

Điều này không loại bỏ mọi lỗi: hai tham số đều là `YearMonth`, chẳng hạn kỳ đầu và kỳ cuối, vẫn có thể bị đảo. Quan hệ “kỳ đầu không sau kỳ cuối” cần kiểm tra riêng.

### 3.2. Chuỗi có nhiều cách viết và nhiều trạng thái sai

Một kỳ tháng có thể bị viết thành `"2024-02"`, `"2024-2"`, `"02/2024"` hoặc `"Feb 2024"`. Nếu toàn bộ lớp nghiệp vụ nhận `String`, mỗi nơi lại phải quyết định định dạng, cách phân tích và xử lý lỗi.

Phân tích một lần ở nơi nhận dữ liệu, rồi dùng `YearMonth` bên trong giúp thống nhất cách hiểu. Ví dụ bài này chọn `"2024-02"` cho định dạng trao đổi của kỳ tháng. Chuỗi `"2024-2"` bị từ chối bởi phép phân tích mặc định, dù người đọc có thể đoán ý nghĩa.

Chọn định dạng nhập rộng hơn là một quyết định riêng. Nếu biểu mẫu cho phép `"02/2024"`, hãy phân tích bằng bộ định dạng đã xác định, rồi vẫn chuyển sang kiểu lịch trước khi tính toán; không phát tán nhiều quy ước chuỗi vào mọi hàm.

### 3.3. Tự tính bằng số dễ bỏ sót quy tắc lịch

Với một kỳ tháng, tăng số tháng bằng 1 phải xử lý chuyển tháng 12 sang tháng 1 và tăng năm. `YearMonth.plusMonths(1)` diễn đạt trực tiếp việc sang kỳ kế tiếp.

Với một năm, kiểm tra nhuận cần xử lý cả ngoại lệ năm thế kỷ. `Year.isLeap` giúp tránh việc mỗi nơi tự viết một phiên bản “chia hết cho 4”.

Lợi ích nằm ở việc thao tác theo mô hình lịch chuẩn; không chỉ ở chỗ dữ liệu được bọc trong một lớp.

## 4. Các kiểu bảo vệ được gì?

### 4.1. Year và YearMonth

`Year.of(number)` kiểm tra miền năm được Java hỗ trợ. `YearMonth.of(year, month)` kiểm tra cả năm và tháng; tháng 13 bị từ chối.

`YearMonth` giữ một kỳ năm-tháng như một giá trị duy nhất. Có thể:

- So sánh hai kỳ bằng `isBefore`, `isAfter` hoặc `compareTo`.
- Chuyển kỳ bằng `plusMonths`, `minusMonths`.
- Tìm số ngày của tháng bằng `lengthOfMonth`.
- Tạo ngày cụ thể bằng `atDay` hoặc ngày cuối kỳ bằng `atEndOfMonth`.

Một kỳ tháng hợp lệ chưa phải một ngày đầy đủ, và không có lý do phải luôn chọn ngày đầu hay cuối kỳ. Xem định nghĩa của [Year](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Year.html) và [YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html).

### 4.2. Month và DayOfWeek

`Month.of(2)` cho `Month.FEBRUARY`; `DayOfWeek.of(1)` cho `DayOfWeek.MONDAY`. Hai enum loại trừ số ngoài phạm vi, đồng thời làm chữ ký hàm rõ nghĩa hơn.

Số tháng chuẩn là 1..12. Số thứ ISO là 1..7, với thứ Hai là 1. Không mang quy ước bắt đầu từ 0 hoặc quy ước Chủ nhật là 1 của API khác vào đây.

Khi cần số để trao đổi, dùng `getValue()`, không dùng `ordinal()`. `ordinal()` là vị trí khai báo enum, không phải quy ước số lịch dành cho dữ liệu bên ngoài. Xem [Month](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Month.html) và [DayOfWeek](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/DayOfWeek.html).

### 4.3. MonthDay

`MonthDay.of(4, 31)` bị từ chối vì không có ngày 31/4. Nhưng `MonthDay.of(2, 29)` được chấp nhận vì ngày đó tồn tại trong năm nhuận.

Điều này không phải lỗ hổng xác thực: kiểu đang biểu diễn tháng-ngày **chưa có năm**, nên chưa thể kết luận 29/2 có tồn tại trong năm đích nào.

Khi gắn năm, cần chọn chính sách. `MonthDay.atYear` lùi 29/2 về 28/2 nếu năm không nhuận. Nếu nghiệp vụ muốn từ chối, kiểm tra `Year.isValidMonthDay` trước khi tạo ngày. Kiểu biểu diễn được phần cấu trúc, còn chính sách phải rõ ràng; xem [MonthDay](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/MonthDay.html).

## 5. Các kiểu không tự bảo vệ mọi quy tắc nghiệp vụ

Một đối tượng `YearMonth` hợp lệ không tự trả lời:

- Kỳ đó có nằm trong giai đoạn cho phép của hệ thống không?
- Kỳ đầu có trước hoặc bằng kỳ cuối không?
- Báo cáo có cho phép số bài hoàn thành âm không?
- Trường này có được phép thiếu không?
- Ngày kỷ niệm 29/2 được xử lý ra sao trong năm thường?

Vì vậy, cần phân biệt ba lớp:

| Lớp kiểm tra | Ví dụ |
| --- | --- |
| Cú pháp dữ liệu bên ngoài | Chuỗi kỳ có đúng định dạng đã công bố không? |
| Cấu trúc lịch | Năm-tháng có hợp lệ, tháng có nằm trong 1..12 không? |
| Quy tắc nghiệp vụ | Kỳ đầu có sau kỳ cuối, số lượng có âm, trường có bắt buộc không? |

`record` có thể gom dữ liệu với các kiểm tra nghiệp vụ trong hàm dựng. Chỉ khai báo `record` chưa tự loại bỏ `null` hoặc đảm bảo thứ tự kỳ; phải viết các kiểm tra cần thiết.

Nếu hai khái niệm cùng dùng một kiểu lịch nhưng có ràng buộc riêng rõ ràng, có thể tạo kiểu miền bao ngoài. Ví dụ “năm học” có thể trải qua hai năm dương lịch nên không nhất thiết đồng nghĩa với một `Year`. Không đổi tên một năm dương lịch rồi cho rằng đã mô hình hóa đầy đủ năm học.

## 6. Đọc ở đầu vào, giữ kiểu lịch trong phần tính toán

Một luồng xử lý dễ kiểm soát là:

```text
Dữ liệu ngoài: chuỗi hoặc số có quy ước rõ
        ↓ phân tích và kiểm tra
Giá trị có kiểu: Year / YearMonth / MonthDay / Month / DayOfWeek
        ↓ kiểm tra nghiệp vụ
Tính toán, so sánh, lưu trong mô hình
        ↓ định dạng theo hợp đồng đầu ra
Dữ liệu trao đổi hoặc nội dung hiển thị
```

Một số dạng mặc định dùng trong bài:

| Kiểu | Dữ liệu đầu vào minh họa | Cách tạo |
| --- | --- | --- |
| `Year` | `"2024"` | `Year.parse(text)` |
| `YearMonth` | `"2024-02"` | `YearMonth.parse(text)` |
| `MonthDay` | `"--02-29"` | `MonthDay.parse(text)` |
| `Month` | Số 2 theo ISO | `Month.of(number)` |
| `DayOfWeek` | Số 1 theo ISO | `DayOfWeek.of(number)` |

Dấu `--` trong biểu diễn mặc định của `MonthDay` cho thấy phần năm bị bỏ. Đây không phải chuỗi ngày đầy đủ.

Tên enum tiếng Anh như `FEBRUARY` và nhãn hiển thị như “tháng 2” phục vụ những mục đích khác nhau. Không lấy nhãn đã bản địa hóa làm dữ liệu lưu cố định nếu chưa có hợp đồng phân tích tương ứng.

Khi xuất JSON hoặc lưu cơ sở dữ liệu, hãy xác định định dạng và cách chuyển đổi rõ ràng. Không mặc định mọi thư viện tự ánh xạ các kiểu thành phần giống nhau. Dù nơi lưu dùng chuỗi hay số, phần tính toán vẫn có thể giữ kiểu lịch và chuyển đổi ở nơi vào/ra.

Nếu dữ liệu được phép thiếu, thể hiện trạng thái thiếu có chủ đích theo mô hình của ứng dụng. Không dùng tháng 0, năm -1 hay chuỗi rỗng làm giá trị thay thế mà các hàm phía sau tưởng là dữ liệu thật. Năm -1 còn là một năm hợp lệ trong mô hình ISO của `Year`, nên càng không phải dấu hiệu thiếu có sẵn.

## 7. Chương trình Java 17+ với mô hình báo cáo theo tháng

Lưu mã sau thành `ComponentTypeChoices.java`. Chương trình dùng `record` để đặt tên ý nghĩa và kiểm tra quan hệ nghiệp vụ; không yêu cầu thư viện ngoài.

`MonthlyReport` lưu kỳ bằng `YearMonth` và giữ số bài hoàn thành bằng `int`. `ReportWindow` chứa hai kỳ, kiểm tra thứ tự của chúng. Hàm `readReport` phân tích chuỗi một lần trước khi tạo báo cáo.

```java
import java.time.DateTimeException;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.Month;
import java.time.MonthDay;
import java.time.Year;
import java.time.YearMonth;
import java.time.format.DateTimeParseException;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ComponentTypeChoices {
    public record MonthlyReport(YearMonth period, int completedLessons) {
        public MonthlyReport {
            Objects.requireNonNull(period, "period");
            if (completedLessons < 0) {
                throw new IllegalArgumentException("completedLessons must be non-negative");
            }
        }
    }

    public record ReportWindow(YearMonth first, YearMonth last) {
        public ReportWindow {
            Objects.requireNonNull(first, "first");
            Objects.requireNonNull(last, "last");
            if (first.isAfter(last)) {
                throw new IllegalArgumentException("first must not be after last");
            }
        }
    }

    private static int checks;

    private static MonthlyReport readReport(String rawPeriod, int completedLessons) {
        return new MonthlyReport(YearMonth.parse(rawPeriod), completedLessons);
    }

    private static LocalDate strictOccurrence(Year year, MonthDay day) {
        Objects.requireNonNull(year, "year");
        Objects.requireNonNull(day, "day");
        if (!year.isValidMonthDay(day)) {
            throw new DateTimeException("Month-day does not exist in year " + year);
        }
        return year.atMonthDay(day);
    }

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Class<? extends RuntimeException> type,
                                Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw new AssertionError("Unexpected exception", ex);
            }
            checks++;
            return;
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        MonthlyReport report = readReport("2024-02", 12);
        eq(report.period(), YearMonth.of(2024, 2));
        eq(report.completedLessons(), 12);
        eq(report.period().plusMonths(1), YearMonth.of(2024, 3));
        eq(report.period().atEndOfMonth(), LocalDate.of(2024, 2, 29));
        eq(Year.parse("2024"), Year.of(2024));
        eq(MonthDay.parse("--02-29"), MonthDay.of(2, 29));
        eq(Month.of(2), Month.FEBRUARY);
        eq(Month.FEBRUARY.getValue(), 2);
        eq(DayOfWeek.of(1), DayOfWeek.MONDAY);
        eq(YearMonth.parse(report.period().toString()), report.period());

        Map<YearMonth, Integer> counts = new HashMap<>();
        counts.put(report.period(), report.completedLessons());
        eq(counts.get(YearMonth.parse("2024-02")), Integer.valueOf(12));

        ReportWindow window = new ReportWindow(YearMonth.of(2024, 1),
                YearMonth.of(2024, 3));
        eq(window.first().isBefore(window.last()), true);
        rejects(IllegalArgumentException.class,
                () -> new ReportWindow(window.last(), window.first()));
        rejects(IllegalArgumentException.class,
                () -> new MonthlyReport(report.period(), -1));
        rejects(NullPointerException.class, () -> new MonthlyReport(null, 1));
        rejects(DateTimeParseException.class, () -> readReport("2024-13", 1));
        rejects(DateTimeParseException.class, () -> readReport("202402", 1));
        rejects(DateTimeParseException.class, () -> readReport("2024-2", 1));
        rejects(DateTimeException.class, () -> Month.of(0));
        rejects(DateTimeException.class, () -> DayOfWeek.of(0));
        rejects(DateTimeException.class, () -> MonthDay.of(4, 31));

        MonthDay anniversary = MonthDay.of(2, 29);
        eq(strictOccurrence(Year.of(2024), anniversary), LocalDate.of(2024, 2, 29));
        rejects(DateTimeException.class,
                () -> strictOccurrence(Year.of(2023), anniversary));
        eq(anniversary.atYear(2023), LocalDate.of(2023, 2, 28));

        System.out.println("period=" + report.period());
        System.out.println("nextPeriod=" + report.period().plusMonths(1));
        System.out.println("periodEnd=" + report.period().atEndOfMonth());
        System.out.println("samePeriodCount=" + counts.get(YearMonth.of(2024, 2)));
        System.out.println("strictOccurrence=" + strictOccurrence(Year.of(2024), anniversary));
        System.out.println("adjustedOccurrence=" + anniversary.atYear(2023));
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ComponentTypeChoices.java
java ComponentTypeChoices
```

Stdout:

```text
period=2024-02
nextPeriod=2024-03
periodEnd=2024-02-29
samePeriodCount=12
strictOccurrence=2024-02-29
adjustedOccurrence=2023-02-28
PASS checks=24
```

Dòng `samePeriodCount` cho thấy hai đối tượng `YearMonth` được tạo riêng nhưng cùng giá trị có thể dùng như cùng một khóa trong `Map`. Các kiểu thành phần chuẩn bất biến và có phép bằng nhau theo giá trị; không cần so sánh bằng `==`.

Hai dòng về ngày kỷ niệm cho thấy lựa chọn kiểu không thay thế lựa chọn chính sách. Hàm `strictOccurrence` yêu cầu tháng-ngày tồn tại trong năm đích, còn lời gọi trực tiếp `atYear` có hành vi điều chỉnh đã nêu.

Hàm `eq` chủ động ném `AssertionError` khi sai nên không cần bật `-ea`. Hàm `rejects` xác nhận đúng loại ngoại lệ, không âm thầm chấp nhận mọi lỗi. Bộ kiểm tra phân biệt chuỗi sai định dạng, cấu trúc lịch sai, thiếu trường bắt buộc và quan hệ kỳ bị đảo.

## 8. Chuyển một mô hình đang dùng số/chuỗi sang kiểu phù hợp

Có thể chuyển từng phần theo một trình tự cụ thể:

1. **Ghi rõ ý nghĩa hiện tại.** Trường `month` là tháng trong năm hay một kỳ tháng thuộc năm cụ thể? Chuỗi `birthday` có chứa năm sinh không?
2. **Chọn kiểu giữ đủ thông tin.** Dùng `YearMonth` cho kỳ, `Month` cho tháng chung, `LocalDate` cho ngày đầy đủ.
3. **Xác định quy ước đầu vào.** Công bố định dạng chuỗi hoặc quy ước số; không để nhiều nơi tự đoán.
4. **Chuyển đổi ở nơi nhận dữ liệu.** Sau khi phân tích thành công, các hàm tính toán nhận kiểu lịch.
5. **Giữ các ràng buộc nghiệp vụ.** Không xóa kiểm tra kỳ được phép, thứ tự khoảng hoặc số lượng chỉ vì đã dùng kiểu mới.
6. **Kiểm tra dữ liệu cũ trước khi chuyển.** Những chuỗi sai hoặc giá trị đánh dấu thiếu cần được xử lý rõ; không tự đổi sang một ngày/kỳ gần nhất.
7. **Định dạng khi xuất.** Đừng chuyển thành chuỗi giữa chừng rồi lại tách chuỗi để tính kỳ tiếp theo.

Việc chuyển đổi có ích nhất khi nó giảm số nơi phải nhớ các quy ước lịch và giúp chữ ký hàm nói rõ dữ liệu cần nhận. Không cần tạo nhiều lớp bao nếu chưa có khác biệt về ý nghĩa hoặc ràng buộc.

## 9. Lỗi phổ biến và bài tập lựa chọn

Các lỗi cần tránh:

- Chọn `Month` cho kỳ tháng có năm, làm mất thông tin năm.
- Chọn `MonthDay` cho ngày sinh dùng tính tuổi, làm mất năm sinh.
- Chọn `LocalDate` cho năm-tháng rồi quên rằng ngày 1 là dữ liệu tự thêm.
- Giữ `String` trong mọi tầng và lặp lại việc tách, ghép, so sánh chuỗi.
- Cho rằng kiểu hợp lệ đồng nghĩa hợp lệ về nghiệp vụ.
- Dùng `ordinal()` làm số tháng/thứ trao đổi.
- Tự điều chỉnh dữ liệu sai để qua được bước chuyển đổi.
- Coi việc dùng `record` tự động loại bỏ `null` và kiểm tra quan hệ giữa các trường.

Thực hành:

1. **“Tháng phát hành: 3” nhưng không có năm.** Nếu đây là tháng lặp lại trong lịch, dùng `Month.MARCH`; nếu là kỳ phát hành tháng 3/2025, cần `YearMonth.of(2025, 3)`.

2. **“Ngày sinh: 2000-02-29”, cần tính tuổi.** Giữ `LocalDate`. Có thể trích `MonthDay` để tạo lời nhắc, nhưng không dùng kết quả trích thay thế ngày sinh gốc.

3. **“Kỳ bắt đầu 2024-05, kỳ kết thúc 2024-02”.** Cả hai kỳ đều hợp lệ về lịch, nhưng khoảng bị đảo; mô hình nghiệp vụ phải từ chối.

4. **“Lời nhắc 29/2 trong năm 2023”.** `MonthDay` vẫn là giá trị phù hợp để mô tả mẫu ngày lặp; việc tạo lần xuất hiện cụ thể cần chính sách báo lỗi hoặc điều chỉnh.

5. **“Năm tốt nghiệp 2026”.** `Year.of(2026)` giữ đúng mức thông tin. Nếu trường bắt buộc và có giới hạn năm theo chương trình đào tạo, kiểm tra các điều kiện đó riêng.

Hãy chọn kiểu dựa trên ý nghĩa và mức thông tin, rồi xác định quy ước vào/ra cùng các điều kiện nghiệp vụ. Một kiểu lịch tốt giúp giảm trạng thái sai có thể biểu diễn, nhưng không thay việc hiểu dữ liệu đang dùng để làm gì.
