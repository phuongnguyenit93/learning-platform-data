# Year và kiểm tra tính hợp lệ của năm nhuận

## 1. Year biểu diễn năm, không phải một ngày đầy đủ

Trong nhóm các kiểu biểu diễn từng phần của ngày, `java.time.Year` dùng khi dữ liệu chỉ cần **một năm theo lịch ISO**, chẳng hạn năm báo cáo, năm tốt nghiệp hoặc năm cần kiểm tra nhuận. Nó không chứa tháng, ngày, giờ hay múi giờ.

Dùng `Year.of(2024)` diễn đạt rõ “năm 2024”. Không cần tạo một ngày giả như 1/1/2024 chỉ để mang theo phần năm, nếu nghiệp vụ không có ngày đó.

Có ba câu hỏi khác nhau cần tách biệt:

| Câu hỏi | Ví dụ | API phù hợp |
| --- | --- | --- |
| Số năm có nằm trong miền biểu diễn của `Year` không? | 2024 nằm trong miền; 1.000.000.000 thì không | `Year.of(number)` kiểm tra khi tạo |
| Năm đó có nhuận không? | 2024 nhuận, 2023 không nhuận | `year.isLeap()` hoặc `Year.isLeap(number)` |
| Một tháng-ngày có tồn tại trong năm đó không? | 29/2 hợp lệ trong 2024 nhưng không trong 2023 | `year.isValidMonthDay(monthDay)` |

Một năm **không nhuận vẫn là năm hợp lệ**. Kết quả `false` từ `isLeap` không có nghĩa dữ liệu năm bị sai. Ngược lại, một số thỏa quy tắc chia hết để xét nhuận chưa chắc nằm trong miền tạo được đối tượng `Year`.

Bài này tập trung vào cách tạo `Year`, xác định nhuận và kiểm tra ngày phụ thuộc năm. Các quy tắc lịch sử của từng quốc gia hoặc lịch âm không thuộc mô hình này.

## 2. Tạo và đọc một Year

| Cách gọi | Ý nghĩa |
| --- | --- |
| `Year.of(2024)` | Tạo năm từ số nguyên, có kiểm tra miền |
| `Year.parse("2024")` | Đọc năm từ chuỗi theo định dạng mặc định |
| `Year.from(localDate)` | Trích năm từ một ngày ISO đã có |
| `year.getValue()` | Lấy số năm kiểu `int` |
| `year.plusYears(1)` | Tạo năm kế tiếp |
| `year.minusYears(1)` | Tạo năm trước |

`Year` bất biến. Nếu `year` là 2024, gọi `year.plusYears(1)` trả về giá trị 2025; biến và đối tượng năm ban đầu vẫn giữ giá trị 2024 nếu không gán lại.

Miền được hỗ trợ là `Year.MIN_VALUE` đến `Year.MAX_VALUE`, tức từ -999.999.999 đến +999.999.999. `Year.of` từ chối giá trị ngoài miền bằng `DateTimeException`. Với dữ liệu nhập dạng chuỗi, lỗi phân tích cú pháp là `DateTimeParseException`; không nhầm lỗi chuỗi với kết quả “không phải năm nhuận”.

Ngoài miền kỹ thuật của Java, ứng dụng có thể có miền nghiệp vụ hẹp hơn, chẳng hạn chỉ nhận năm của một giai đoạn cụ thể. Ràng buộc đó cần được xác định riêng; `Year.of` không tự biết giới hạn năm của biểu mẫu.

`Year.now()` lấy năm hiện tại theo đồng hồ và múi giờ mặc định. Vì thời gian thực thay đổi, các ví dụ kiểm tra bên dưới dùng năm cố định để kết quả không phụ thuộc ngày chạy. Khi kiểm thử chức năng “năm hiện tại”, có thể truyền một `Clock` xác định vào `Year.now(clock)`; bản thân kết quả `Year` vẫn không lưu múi giờ.

## 3. Quy tắc năm nhuận và hai cách gọi isLeap

Quy tắc của lịch ISO/Gregorian áp dụng trong bài:

1. Năm chia hết cho 400 là năm nhuận.
2. Nếu không thuộc trường hợp trên, năm chia hết cho 100 không nhuận.
3. Nếu không bị loại bởi trường hợp thế kỷ, năm chia hết cho 4 là năm nhuận.
4. Các năm còn lại không nhuận.

Có thể biểu diễn bằng điều kiện:

```text
chia hết cho 4 VÀ (không chia hết cho 100 HOẶC chia hết cho 400)
```

Trong mã ứng dụng, ưu tiên `Year.isLeap` thay vì chép lại công thức ở nhiều nơi. Công thức giúp giải thích và chọn ca kiểm tra, không phải lý do để tự xây một thư viện lịch khác.

| Năm | Chia hết cho 4? | Chia hết cho 100? | Chia hết cho 400? | Kết luận |
| --- | --- | --- | --- | --- |
| 2023 | Không | Không | Không | Không nhuận |
| 2024 | Có | Không | Không | Nhuận |
| 1900 | Có | Có | Không | Không nhuận |
| 2000 | Có | Có | Có | Nhuận |
| 2100 | Có | Có | Không | Không nhuận |
| 2400 | Có | Có | Có | Nhuận |

Chỉ thử 2023 và 2024 chưa đủ để phát hiện lỗi “chia hết cho 4 là nhuận”. Ca 1900 hoặc 2100 phát hiện thiếu ngoại lệ năm thế kỷ; ca 2000 phát hiện việc loại nhầm mọi năm chia hết cho 100.

Hai dạng gọi thông dụng:

- Đã có đối tượng: `Year.of(2024).isLeap()`.
- Chỉ cần kết luận từ một số năm: `Year.isLeap(2024)`.

Dạng tĩnh nhận tham số `long`. Nó xét quy tắc nhuận, không đóng vai trò tạo và kiểm tra miền của đối tượng `Year`. Ví dụ `Year.isLeap(1_000_000_000L)` trả `true`, nhưng `Year.of(1_000_000_000)` báo ngoài miền. Nếu đầu vào cần trở thành `Year`, hãy xác thực qua bước tạo đối tượng chứ đừng dùng kết quả `isLeap` thay thế.

`Year.length()` trả 366 ở năm nhuận và 365 ở năm thường. Đây là **số ngày lịch**, không phải cam kết về số giây của năm ở một múi giờ cụ thể. Các khả năng của lớp được mô tả trong [Year](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Year.html).

## 4. Kiểm tra ngày 29/2 bằng Year và MonthDay

`MonthDay` biểu diễn tháng và ngày chưa gắn năm. `MonthDay.of(2, 29)` là giá trị hợp lệ vì ngày 29/2 tồn tại trong một số năm. Tuy nhiên, nó chưa phải một ngày hoàn chỉnh.

Khi đã biết năm, `year.isValidMonthDay(monthDay)` kiểm tra hai thành phần đó có kết hợp thành ngày thật hay không:

| Năm | Tháng-ngày | Kết quả |
| --- | --- | --- |
| 2024 | 29/2 | `true` |
| 2023 | 29/2 | `false` |
| 1900 | 29/2 | `false` |
| 2000 | 29/2 | `true` |
| 2023 | 28/2 | `true` |
| 2024 | 31/12 | `true` |

Không thể tạo `MonthDay.of(4, 31)` rồi mới hỏi năm nào chấp nhận nó: ngày 31/4 không tồn tại trong bất kỳ năm nào, nên bước tạo `MonthDay` đã báo lỗi.

Điều đó tạo ra hai lớp kiểm tra:

1. **Tháng-ngày có khả năng tồn tại không?** `MonthDay` kiểm tra cấu trúc này.
2. **Nó có tồn tại trong năm đang xét không?** `Year.isValidMonthDay` bổ sung ngữ cảnh năm.

Chỉ biết `year.isLeap() == true` chưa đủ để kết luận mọi ngày trong năm đều hợp lệ. Năm 2024 nhuận nhưng vẫn không có 30/2 hoặc 31/4. Xem cách biểu diễn tháng-ngày tại [MonthDay](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/MonthDay.html).

## 5. Kiểm tra khác với tự điều chỉnh

Đây là điểm quan trọng nhất khi dùng kết quả để xác thực dữ liệu.

`Year.atMonthDay` tạo một ngày từ năm và tháng-ngày. Nếu tháng-ngày là 29/2 nhưng năm không nhuận, phương thức **tự lùi về 28/2**. Tương tự, `MonthDay.of(2, 29).atYear(2023)` cho 28/2/2023.

| Biểu thức | Kết quả |
| --- | --- |
| `Year.of(2023).isValidMonthDay(MonthDay.of(2, 29))` | `false` |
| `Year.of(2023).atMonthDay(MonthDay.of(2, 29))` | `2023-02-28` |
| `MonthDay.of(2, 29).atYear(2023)` | `2023-02-28` |
| `Year.of(2023).atMonth(2).atDay(29)` | `DateTimeException` |
| `LocalDate.of(2023, 2, 29)` | `DateTimeException` |

Vì thế, “tạo ngày thành công” không đồng nghĩa “ngày gốc được nhập là hợp lệ”, nếu đang dùng một API có điều chỉnh.

Lựa chọn phụ thuộc yêu cầu:

- **Muốn từ chối 29/2 trong năm thường:** kiểm tra `isValidMonthDay` rồi từ chối nếu sai, hoặc dùng cách tạo ngày nghiêm ngặt như `LocalDate.of`.
- **Muốn ngày kỷ niệm lùi về 28/2:** có thể dùng `atMonthDay` nếu đó là chính sách đã được xác định.
- **Muốn chuyển sang 1/3:** phải triển khai quy tắc riêng; không suy ra hành vi đó từ `atMonthDay`.

Trong ví dụ dưới đây, hàm `strictDate` chủ động kiểm tra trước khi ghép. Khi đầu vào là 29/2 của năm thường, hàm báo lỗi thay vì âm thầm đổi sang 28/2.

## 6. Từ Year sang các phần khác của ngày

`Year` có thể làm điểm bắt đầu để bổ sung thông tin theo đúng mức dữ liệu:

| Cách ghép | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `year.atMonth(Month.FEBRUARY)` | `YearMonth` | Năm-tháng, chưa có ngày |
| `year.atMonth(2).atDay(29)` | `LocalDate` nếu hợp lệ | Chọn một ngày cụ thể trong tháng 2 |
| `year.atMonthDay(monthDay)` | `LocalDate` | Ghép tháng-ngày, có quy tắc lùi 29/2 |
| `year.atDay(dayOfYear)` | `LocalDate` | Ghép số thứ tự ngày trong năm |

Nếu chỉ cần kiểm tra một số ngày trong tháng cụ thể, `year.atMonth(2).isValidDay(29)` là cách kiểm tra không tạo ngày đầy đủ. `YearMonth` có đủ năm-tháng để xét độ dài tháng và tính hợp lệ của ngày; xem [YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html).

Cẩn thận với tên tham số của `atDay`: ở `Year.atDay`, đó là **ngày thứ bao nhiêu trong năm**, không phải ngày trong tháng.

| Biểu thức | Kết quả |
| --- | --- |
| `Year.of(2024).atDay(60)` | `2024-02-29` |
| `Year.of(2023).atDay(60)` | `2023-03-01` |
| `Year.of(2024).atDay(366)` | `2024-12-31` |
| `Year.of(2023).atDay(366)` | `DateTimeException` |

Thêm một ngày nhuận làm dịch chuyển số thứ tự của các ngày sau tháng 2. Nếu dữ liệu là ngày cố định theo tháng, đừng tự biến nó thành số thứ tự ngày rồi áp cùng số đó cho mọi năm.

## 7. Chương trình Java 17+ kiểm chứng đầy đủ

Lưu toàn bộ mã sau vào `YearLeapValidation.java`. Chương trình không cần thư viện ngoài và không phụ thuộc năm hiện tại.

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.Month;
import java.time.MonthDay;
import java.time.Year;
import java.util.Objects;

public class YearLeapValidation {
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

    private static LocalDate strictDate(Year year, MonthDay monthDay) {
        Objects.requireNonNull(year, "year");
        Objects.requireNonNull(monthDay, "monthDay");
        if (!year.isValidMonthDay(monthDay)) {
            throw new DateTimeException("Invalid month-day for year " + year);
        }
        return year.atMonthDay(monthDay);
    }

    public static void main(String[] args) {
        Year leap = Year.of(2024);
        Year common = Year.of(2023);
        MonthDay feb29 = MonthDay.of(2, 29);
        eq(Year.parse("2024"), leap);
        eq(Year.from(LocalDate.of(2024, 12, 31)), leap);
        eq(leap.getValue(), 2024);
        eq(leap.isLeap(), true);
        eq(common.isLeap(), false);
        eq(Year.isLeap(1900), false);
        eq(Year.isLeap(2000), true);
        eq(Year.isLeap(2100), false);
        eq(Year.isLeap(2400), true);
        eq(leap.length(), 366);
        eq(common.length(), 365);
        eq(leap.isValidMonthDay(feb29), true);
        eq(common.isValidMonthDay(feb29), false);
        eq(common.isValidMonthDay(MonthDay.of(2, 28)), true);
        eq(strictDate(leap, feb29), LocalDate.of(2024, 2, 29));
        rejects(() -> strictDate(common, feb29));
        eq(common.atMonthDay(feb29), LocalDate.of(2023, 2, 28));
        eq(feb29.atYear(2023), LocalDate.of(2023, 2, 28));
        rejects(() -> common.atMonth(Month.FEBRUARY).atDay(29));
        rejects(() -> LocalDate.of(2023, 2, 29));
        rejects(() -> MonthDay.of(4, 31));

        eq(leap.atDay(60), LocalDate.of(2024, 2, 29));
        eq(common.atDay(60), LocalDate.of(2023, 3, 1));
        eq(leap.atDay(366), LocalDate.of(2024, 12, 31));
        rejects(() -> common.atDay(366));
        eq(leap.plusYears(1), Year.of(2025));
        eq(leap, Year.of(2024));
        eq(Year.isLeap(0), true);
        eq(Year.isLeap(-4), true);
        eq(Year.of(Year.MIN_VALUE).getValue(), Year.MIN_VALUE);
        eq(Year.of(Year.MAX_VALUE).getValue(), Year.MAX_VALUE);
        rejects(() -> Year.of(Year.MAX_VALUE + 1));
        rejects(() -> Year.of(Year.MIN_VALUE - 1));
        eq(Year.isLeap(1_000_000_000L), true);
        rejects(() -> Year.of(1_000_000_000));

        int leapCount = 0;
        for (int number = 2000; number < 2400; number++) {
            Year year = Year.of(number);
            boolean hasFeb29 = year.atMonth(Month.FEBRUARY).isValidDay(29);
            eq(year.isLeap(), hasFeb29);
            eq(year.length(), year.isLeap() ? 366 : 365);
            if (year.isLeap()) {
                leapCount++;
            }
        }
        eq(leapCount, 97);

        for (int number : new int[] {1900, 2000, 2023, 2024, 2100}) {
            Year year = Year.of(number);
            System.out.println("year=" + year + " leap=" + year.isLeap()
                    + " days=" + year.length()
                    + " feb29=" + year.isValidMonthDay(feb29));
        }
        System.out.println("adjusted=" + common.atMonthDay(feb29));
        System.out.println("day60Leap=" + leap.atDay(60));
        System.out.println("day60Common=" + common.atDay(60));
        System.out.println("leapYearsIn400Years=" + leapCount);
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 YearLeapValidation.java
java YearLeapValidation
```

Stdout:

```text
year=1900 leap=false days=365 feb29=false
year=2000 leap=true days=366 feb29=true
year=2023 leap=false days=365 feb29=false
year=2024 leap=true days=366 feb29=true
year=2100 leap=false days=365 feb29=false
adjusted=2023-02-28
day60Leap=2024-02-29
day60Common=2023-03-01
leapYearsIn400Years=97
PASS checks=836
```

Hàm `eq` chủ động ném `AssertionError` khi kết quả sai; không cần cờ `-ea`. Hàm `rejects` xác nhận các thao tác phải báo `DateTimeException`; nếu một thao tác âm thầm chấp nhận đầu vào, chương trình sẽ thất bại.

Vòng lặp từ năm 2000 đến hết 2399 kiểm tra tính nhất quán giữa kết luận nhuận, độ dài năm và việc tháng 2 có ngày 29 hay không. Trong chu kỳ 400 năm có 97 năm nhuận: các bội của 4 được chọn, các bội của 100 bị loại, rồi bội của 400 được nhận lại. Ca tổng số 97 bổ sung cho các ca đơn lẻ và cho thấy vì sao không thể thay quy tắc bằng “mỗi bốn năm luôn có đúng một năm nhuận” cho mọi đoạn lịch.

Các ca ngày cụ thể như 1900, 2000 và 2100 vẫn cần thiết: chỉ kiểm tra các API cùng thư viện khớp nhau chưa thay thế việc đối chiếu kết quả mong đợi của từng nhóm quy tắc.

## 8. Năm 0, năm âm và giới hạn lịch sử

`Year` dùng hệ đánh số năm mở rộng của ISO: có năm 0 trước năm 1, rồi đến năm -1. Quy tắc nhuận được áp dụng nhất quán trên trục năm đó. Trong chương trình, năm 0 và năm -4 đều cho kết quả nhuận.

Điều này không có nghĩa mọi quốc gia trong lịch sử đã dùng đúng cách đánh số và quy tắc ấy ở từng thời điểm. Đó là mô hình lịch ISO mở rộng về quá khứ, thường gọi là lịch Gregorian mở rộng (proleptic Gregorian).

Nếu ứng dụng xử lý hồ sơ lịch sử trước thời điểm một địa phương chuyển lịch, cần xác định hệ lịch thực tế của dữ liệu. Không dùng kết quả `Year.isLeap` để khẳng định ngày lịch sử của mọi quốc gia mà không có ngữ cảnh. Đối với dữ liệu năm hiện đại theo lịch ISO, các API đang dùng cung cấp mô hình phù hợp.

Không cần tự cấm năm 0 hoặc năm âm chỉ vì chúng trông khác năm hiện đại, trừ khi ràng buộc nghiệp vụ đã quy định như vậy.

## 9. Lỗi thường gặp

- **Dùng `year % 4 == 0` làm toàn bộ quy tắc:** bỏ sót ngoại lệ năm thế kỷ. Dùng `Year.isLeap` và có ca 1900/2000/2100.
- **Cho rằng không nhuận là năm sai:** 2023 hoàn toàn hợp lệ, chỉ không có ngày 29/2.
- **Dùng `Year.isLeap` để xác nhận miền của `Year`:** dạng tĩnh nhận `long` và không thay bước tạo `Year`.
- **Dùng `atMonthDay` để xác thực đầu vào:** phương thức có thể lùi 29/2 về 28/2. Chọn API kiểm tra hoặc tạo ngày nghiêm ngặt nếu cần từ chối.
- **Cho rằng có `MonthDay.of(2, 29)` là đủ:** cần thêm năm để xác định ngày đầy đủ.
- **Nhầm `Year.atDay(29)` là ngày 29/2:** phương thức đó chọn ngày thứ 29 của năm, tức 29/1.
- **Lấy độ dài năm bằng 365 cố định:** dùng `year.length()` khi đang đếm ngày của một năm cụ thể.
- **Bỏ kết quả của `plusYears`:** `Year` bất biến; giữ hoặc trả lại giá trị mới.
- **Tự thay đổi ngày sai để dữ liệu được chấp nhận:** chỉ điều chỉnh ngày khi đúng chính sách nghiệp vụ; xác thực và điều chỉnh là hai việc khác nhau.

## 10. Thực hành có đáp án định hướng

1. **Kiểm tra năm 2200 và 2400.** 2200 không nhuận vì chia hết cho 100 nhưng không chia hết cho 400; 2400 nhuận. Cả hai đều tạo được đối tượng `Year`.

2. **Biểu mẫu nhận ngày 29/2 và năm 2100.** Nếu yêu cầu từ chối ngày không tồn tại, `isValidMonthDay` phải trả `false` và biểu mẫu cần báo dữ liệu sai. Không gọi `atMonthDay` rồi lưu 28/2 như thể người dùng đã nhập ngày đó.

3. **So sánh ngày thứ 60 của năm 2023 và 2024.** Kết quả là 1/3/2023 và 29/2/2024. Giải thích vì sao một số thứ tự ngày không bảo đảm cùng tháng-ngày giữa các năm.

4. **Dữ liệu chỉ có năm báo cáo 2025.** Biểu diễn bằng `Year.of(2025)` nếu chưa có tháng/ngày; không cần tạo `LocalDate.of(2025, 1, 1)` để thay cho thông tin chưa được cung cấp.

5. **Kiểm tra số năm 1.000.000.000.** Kết quả nhuận từ dạng tĩnh là `true`, nhưng tạo `Year` phải bị từ chối do ngoài miền. Nêu rõ hai câu hỏi mà hai API đang trả lời.

Khi xác thực ngày phụ thuộc năm, hãy đi đúng thứ tự: xác định miền năm, xác định quy tắc nhuận khi cần, rồi kiểm tra tháng-ngày cụ thể. Sau đó mới chọn từ chối đầu vào hay điều chỉnh theo chính sách đã được xác định.
