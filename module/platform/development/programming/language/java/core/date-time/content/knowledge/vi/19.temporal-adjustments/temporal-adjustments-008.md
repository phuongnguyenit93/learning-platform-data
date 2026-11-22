# Kiểm tra quy tắc điều chỉnh tại cuối tháng và năm nhuận

## 1. Vì sao ngày cuối tháng cần được kiểm tra riêng?

Trong nhóm thao tác điều chỉnh ngày, tình huống khó xuất hiện khi ngày ban đầu không tồn tại trong tháng hoặc năm đích: ngày 31 chuyển sang tháng 2, ngày 29/2 chuyển sang năm thường, hay ngày cuối tháng 2 chuyển sang tháng 3. Muốn kiểm tra đúng, cần tách ba câu hỏi:

1. Tháng hoặc năm đích là gì?
2. Phương thức Java xử lý ngày không hợp lệ như thế nào?
3. Kết quả đó có đúng quy tắc nghiệp vụ mong muốn không?

Một ngày hợp lệ về lịch chưa chắc là hạn thanh toán đúng. Ví dụ, `2024-02-29.plusMonths(1)` cho ngày 29/3 hợp lệ, nhưng không đáp ứng yêu cầu “luôn chốt vào ngày cuối tháng”.

Bài này dùng `LocalDate`, tức ngày theo lịch ISO, không chứa giờ hay múi giờ. Mục tiêu là dự đoán, kiểm chứng và lựa chọn quy tắc điều chỉnh ngày; chưa chuyển ngày thành thời điểm để lập lịch chạy tác vụ.

## 2. Không phải thao tác nào cũng sửa ngày theo cùng cách

Với `plusMonths` và `plusYears`, hãy hình dung hai bước: tính tháng/năm đích, rồi giữ số ngày nếu nó còn hợp lệ; nếu không, dùng ngày hợp lệ cuối cùng của tháng đích. `withMonth` và `withYear` cũng có hành vi lùi ngày tương ứng khi cần.

Ngược lại, tạo trực tiếp một ngày không tồn tại hoặc đặt một số ngày không hợp lệ sẽ báo lỗi. Không thể suy luận “Java luôn tự sửa ngày” chỉ vì đã thấy `plusMonths` làm như vậy. Xem hợp đồng chính thức của [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

| Yêu cầu | Thao tác | Kết quả |
| --- | --- | --- |
| Sang tháng 2 năm thường | `LocalDate.of(2023, 1, 31).plusMonths(1)` | `2023-02-28` |
| Sang tháng 2 năm nhuận | `LocalDate.of(2024, 1, 31).plusMonths(1)` | `2024-02-29` |
| Lùi từ tháng 3 sang tháng 2 | `LocalDate.of(2024, 3, 31).minusMonths(1)` | `2024-02-29` |
| Đổi tháng, giữ năm | `LocalDate.of(2024, 1, 31).withMonth(2)` | `2024-02-29` |
| Đổi năm của ngày nhuận | `LocalDate.of(2024, 2, 29).withYear(2023)` | `2023-02-28` |
| Cộng một năm từ ngày nhuận | `LocalDate.of(2024, 2, 29).plusYears(1)` | `2025-02-28` |
| Tạo ngày không tồn tại | `LocalDate.of(2023, 2, 29)` | `DateTimeException` |
| Đặt ngày 30 trong tháng 2 | `LocalDate.of(2024, 2, 15).withDayOfMonth(30)` | `DateTimeException` |
| Đặt tháng ngoài phạm vi | `LocalDate.of(2024, 1, 31).withMonth(13)` | `DateTimeException` |

Phải phân biệt “ngày 31 không tồn tại trong tháng đích” với “tháng 13”. Hành vi lùi về ngày cuối tháng không biến mọi đầu vào sai thành đầu vào hợp lệ.

Cũng không thay một tháng bằng 30 ngày: từ 31/1/2024, cộng một tháng được 29/2, nhưng cộng 30 ngày được 1/3. `plusDays` tiến trên lịch theo số ngày, không áp dụng quy tắc giữ số ngày trong tháng.

## 3. Năm nhuận: kiểm tra cả ngoại lệ năm thế kỷ

Theo lịch ISO của các kiểu đang dùng, năm chia hết cho 4 thường là năm nhuận; năm chia hết cho 100 thì không nhuận, trừ khi cũng chia hết cho 400. Vì vậy:

| Năm | Có nhuận? | Ngày cuối tháng 2 |
| --- | --- | --- |
| 1900 | Không | `1900-02-28` |
| 2000 | Có | `2000-02-29` |
| 2023 | Không | `2023-02-28` |
| 2024 | Có | `2024-02-29` |
| 2100 | Không | `2100-02-28` |

Trong mã ứng dụng, dùng `Year.isLeap(year)` hoặc `YearMonth.of(year, month).lengthOfMonth()` để tránh chép lại công thức ở nhiều nơi. Độ dài tháng 2 phải gắn với năm cụ thể, nên chỉ lưu “tháng 2” là chưa đủ để xác định ngày kết thúc.

Với ngày 29/2, hãy kiểm tra cả nhảy trực tiếp lẫn cập nhật từng kỳ. Từ `2024-02-29`, `plusYears(4)` đến `2028-02-29`; nhưng cộng từng năm sẽ mất ngày 29 ngay ở bước sang năm 2025 và những bước sau tiếp tục giữ ngày 28. Nếu nghiệp vụ muốn khôi phục ngày 29 vào năm nhuận tiếp theo, phải giữ quy tắc ban đầu thay vì chỉ giữ ngày đã điều chỉnh.

## 4. “Ngày cuối tháng” là một quy tắc, không phải số ngày cố định

Có hai cách rõ nghĩa để lấy ngày cuối tháng:

- Khi đã có một `LocalDate`: `date.with(TemporalAdjusters.lastDayOfMonth())`.
- Khi đang xử lý kỳ theo tháng: `yearMonth.atEndOfMonth()`.

`lastDayOfMonth()` xét tháng chứa ngày đầu vào, kể cả tháng 2 năm nhuận. Nó không đưa ngày sang tháng tiếp theo. `YearMonth.atEndOfMonth()` phù hợp khi dữ liệu nghiệp vụ là “kỳ 2024-02”, chưa cần chọn một ngày cụ thể. Tham khảo [TemporalAdjusters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAdjusters.html) và [YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html).

Điểm dễ nhầm nằm ở thao tác tiếp theo:

| Biểu thức bắt đầu từ `2024-02-29` | Kết quả | Có giữ cuối tháng? |
| --- | --- | --- |
| `date.plusMonths(1)` | `2024-03-29` | Không |
| `date.plusMonths(1).with(lastDayOfMonth())` | `2024-03-31` | Có |
| `YearMonth.from(date).plusMonths(1).atEndOfMonth()` | `2024-03-31` | Có |

Cộng tháng không lưu thông tin “ngày này từng là cuối tháng”. Nếu yêu cầu là cuối tháng, hãy biểu diễn hoặc áp lại quy tắc đó cho từng kỳ.

Một tính chất hữu ích để kiểm tra `lastDayOfMonth()` là tính lũy đẳng: điều chỉnh một ngày đã ở cuối tháng lần nữa phải giữ nguyên giá trị. Dùng `equals` để so sánh ngày, không dùng `==` để kiểm tra danh tính đối tượng.

## 5. Hai giả định đại số thường sai tại ranh giới tháng

### 5.1. Cộng từng tháng có thể khác cộng nhiều tháng một lần

Từ `2024-01-31`:

```text
Cộng 1 tháng:           2024-02-29
Tiếp tục cộng 1 tháng:  2024-03-29

Cộng thẳng 2 tháng:     2024-03-31
```

Bước đầu tiên đã lùi từ ngày 31 về ngày 29. Nếu lấy ngày vừa nhận làm đầu vào cho bước tiếp theo, thông tin “ngày mong muốn là 31” không còn nằm trong giá trị đó.

Vì vậy, không viết kiểm thử khẳng định `d.plusMonths(a).plusMonths(b)` luôn bằng `d.plusMonths(a + b)`. Tính chất ấy không đúng cho mọi ngày.

### 5.2. Cộng rồi trừ chưa chắc trở lại ngày ban đầu

Cũng từ `2024-01-31`:

```text
2024-01-31 + 1 tháng = 2024-02-29
2024-02-29 - 1 tháng = 2024-01-29
```

Đây là hậu quả của việc thông tin ngày ban đầu bị mất khi điều chỉnh sang tháng ngắn hơn. Nếu cần hoàn tác một thay đổi nghiệp vụ, hãy lưu ngày gốc hoặc dữ liệu quy tắc đủ để dựng lại ngày; không dựa vào phép trừ tháng để suy ra chắc chắn giá trị cũ.

## 6. Chọn chính sách cho lịch lặp theo tháng

Trước khi chọn API, hãy phát biểu chính sách bằng ngôn ngữ nghiệp vụ.

| Chính sách | Cách tính phù hợp | Điểm cần kiểm tra |
| --- | --- | --- |
| Luôn vào ngày cuối tháng | `YearMonth` của từng kỳ rồi `atEndOfMonth()` | Tháng 28, 29, 30, 31 ngày |
| Vào ngày 31; tháng thiếu thì dùng ngày cuối tháng | Giữ số ngày yêu cầu là 31; lấy `min(31, độ dài tháng đích)` | Sau tháng 2 phải trở lại ngày 31 ở tháng 3 |
| Vào ngày 30; tháng thiếu thì dùng ngày cuối tháng | Giữ số ngày yêu cầu là 30; lấy `min(30, độ dài tháng đích)` | Tháng 3 phải là ngày 30, không phải ngày 31 |
| Chỉ chấp nhận đúng ngày được yêu cầu | Kiểm tra `YearMonth.isValidDay`, hoặc để `atDay` báo lỗi và xử lý | Phải có cách thông báo/bỏ kỳ theo yêu cầu rõ ràng |

“Ngày cuối tháng” và “ngày 31, thiếu thì lùi” có thể cho cùng kết quả; “ngày 30, thiếu thì lùi” khác hai chính sách đó. Không tự thay chính sách này bằng chính sách khác chỉ vì chúng trùng nhau trong vài tháng thử nghiệm.

Với lịch lặp, nên giữ hai thông tin: tháng gốc của kỳ và số ngày yêu cầu. Mỗi kỳ được tính từ tháng gốc cộng số thứ tự kỳ, sau đó áp dụng chính sách. Không tăng dần ngày đã bị lùi trong kỳ trước, nếu yêu cầu cần phục hồi số ngày gốc.

Ví dụ chính sách “ngày 31, thiếu thì lùi” cho ba kỳ đầu năm 2024 là 31/1, 29/2, 31/3. Chính sách “ngày 30, thiếu thì lùi” cho tháng 2 và tháng 3 là 29/2, 30/3. Chương trình dưới đây kiểm tra cả hai.

## 7. Chương trình Java 17+ kiểm chứng kết quả và ngoại lệ

Lưu toàn bộ mã sau vào tệp `MonthEndRules.java`. Chương trình dùng kiểm tra chủ động và ném `AssertionError` khi sai; không phụ thuộc JUnit và không cần cờ `-ea`. Hai hàm `eq` và `rejects` lần lượt kiểm tra kết quả và yêu cầu có `DateTimeException`.

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.Year;
import java.time.YearMonth;
import java.util.Objects;
import static java.time.temporal.TemporalAdjusters.lastDayOfMonth;

public class MonthEndRules {
    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static LocalDate d(String value) {
        return LocalDate.parse(value);
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

    // Policy: keep the requested day, or use the target month's last day.
    private static LocalDate dueDate(YearMonth month, int requestedDay) {
        if (requestedDay < 1 || requestedDay > 31) {
            throw new IllegalArgumentException("requestedDay must be 1..31");
        }
        return month.atDay(Math.min(requestedDay, month.lengthOfMonth()));
    }

    public static void main(String[] args) {
        LocalDate anchor = d("2024-01-31");
        eq(d("2023-01-31").plusMonths(1), d("2023-02-28"));
        eq(anchor.plusMonths(1), d("2024-02-29"));
        eq(d("2024-03-31").minusMonths(1), d("2024-02-29"));
        eq(anchor.withMonth(2), d("2024-02-29"));
        eq(d("2024-02-29").withYear(2023), d("2023-02-28"));
        eq(d("2024-02-29").plusYears(1), d("2025-02-28"));
        eq(d("2024-02-29").plusYears(4), d("2028-02-29"));
        eq(anchor.plusDays(30), d("2024-03-01"));
        eq(d("2024-02-28").plusDays(1), d("2024-02-29"));
        eq(d("2023-02-28").plusDays(1), d("2023-03-01"));
        eq(d("2024-12-31").plusDays(1), d("2025-01-01"));

        eq(Year.isLeap(1900), false);
        eq(Year.isLeap(2000), true);
        eq(Year.isLeap(2100), false);
        eq(YearMonth.of(1900, 2).lengthOfMonth(), 28);
        eq(YearMonth.of(2000, 2).lengthOfMonth(), 29);
        eq(YearMonth.of(2100, 2).lengthOfMonth(), 28);

        rejects(() -> LocalDate.of(2023, 2, 29));
        rejects(() -> d("2024-02-15").withDayOfMonth(30));
        rejects(() -> YearMonth.of(2024, 2).atDay(31));
        rejects(() -> anchor.withMonth(13));

        LocalDate chained = anchor.plusMonths(1).plusMonths(1);
        LocalDate direct = anchor.plusMonths(2);
        eq(chained, d("2024-03-29"));
        eq(direct, d("2024-03-31"));
        eq(anchor.plusMonths(1).minusMonths(1), d("2024-01-29"));
        eq(anchor, d("2024-01-31"));

        LocalDate lastFebruary = d("2024-02-10").with(lastDayOfMonth());
        eq(lastFebruary, d("2024-02-29"));
        eq(lastFebruary.plusMonths(1), d("2024-03-29"));
        eq(lastFebruary.plusMonths(1).with(lastDayOfMonth()),
                d("2024-03-31"));
        eq(YearMonth.of(2024, 2).plusMonths(1).atEndOfMonth(),
                d("2024-03-31"));
        eq(dueDate(YearMonth.of(2024, 2), 30), d("2024-02-29"));
        eq(dueDate(YearMonth.of(2024, 3), 30), d("2024-03-30"));
        eq(dueDate(YearMonth.of(2023, 2), 31), d("2023-02-28"));

        // A 400-year Gregorian cycle contains 4,800 months.
        for (int year = 2000; year < 2400; year++) {
            for (int month = 1; month <= 12; month++) {
                YearMonth ym = YearMonth.of(year, month);
                LocalDate end = ym.atEndOfMonth();
                eq(end.getDayOfMonth(), ym.lengthOfMonth());
                eq(end.with(lastDayOfMonth()), end);
                eq(end.plusMonths(1).with(lastDayOfMonth()),
                        ym.plusMonths(1).atEndOfMonth());
            }
        }

        System.out.println("chained=" + chained);
        System.out.println("direct=" + direct);
        for (int i = 0; i < 3; i++) {
            YearMonth month = YearMonth.of(2024, 1).plusMonths(i);
            System.out.println(month + " due31=" + dueDate(month, 31));
        }
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 MonthEndRules.java
java MonthEndRules
```

Stdout:

```text
chained=2024-03-29
direct=2024-03-31
2024-01 due31=2024-01-31
2024-02 due31=2024-02-29
2024-03 due31=2024-03-31
PASS checks=14432
```

Đọc kết quả theo ba nhóm:

1. `chained` và `direct` chứng minh cộng tháng từng bước có thể tạo ngày khác cộng trực tiếp.
2. Các dòng `due31` cho thấy việc giữ số ngày yêu cầu riêng giúp khôi phục ngày 31 sau tháng 2.
3. Dòng `PASS` chỉ xuất hiện sau khi các trường hợp thông thường, ngoại lệ và tính chất của ngày cuối tháng đều vượt qua kiểm tra.

Vòng lặp duyệt 4.800 tháng trong chu kỳ 400 năm, từ năm 2000 đến hết 2399. Với mỗi tháng, nó kiểm tra ba tính chất: số ngày của ngày cuối tháng bằng độ dài tháng; điều chỉnh cuối tháng lần nữa giữ nguyên giá trị; chuyển sang tháng tiếp theo rồi điều chỉnh cuối tháng khớp với kết quả dựng từ `YearMonth`. Có 14.400 lần kiểm tra trong vòng lặp và 32 lần kiểm tra riêng, tổng cộng 14.432.

Các kiểm tra này kiểm chứng hành vi đã chọn trong phạm vi lịch ISO. Chúng không khẳng định mọi quy tắc nghiệp vụ đều đúng, không xử lý lịch nghỉ lễ và không kiểm tra giới hạn cực đại/cực tiểu của toàn bộ miền `LocalDate`.

## 8. Thiết kế bộ ca kiểm tra cho mã thực tế

Hãy chọn dữ liệu có khả năng làm lộ sai sót, thay vì chỉ thử một ngày giữa tháng.

| Nhóm dữ liệu | Ví dụ nên có | Mục tiêu |
| --- | --- | --- |
| Ngày giữa tháng | 15/1 sang 15/2 | Không lùi ngày khi ngày đó còn hợp lệ |
| Tháng 31 sang tháng 30 ngày | 31/3 sang tháng 4 | Không mã hóa cứng tháng 2 là trường hợp duy nhất |
| Tháng 2 năm thường/nhuận | Tháng 2/2023 và 2/2024 | Phân biệt 28 với 29 ngày |
| Năm thế kỷ | 1900, 2000, 2100 | Phát hiện công thức “chia hết cho 4 là đủ” |
| Cả hướng tiến và lùi | 31/1 cộng tháng, 31/3 trừ tháng | Kiểm tra hai hướng điều chỉnh |
| Qua năm | 31/12 cộng một ngày hoặc một tháng | Kiểm tra chuyển năm |
| Thao tác không hợp lệ | 29/2/2023, ngày 30 trong tháng 2 | Kiểm tra đúng loại ngoại lệ |
| Lặp nhiều kỳ | 31/1 → tháng 2 → tháng 3 | Phát hiện mất số ngày yêu cầu |
| Cuối tháng ngắn sang tháng dài | 29/2/2024 → tháng 3 | Phát hiện nhầm “cộng tháng” với “giữ cuối tháng” |

Với mỗi ca, ghi rõ chính sách, ngày đầu vào, phép điều chỉnh và kết quả mong đợi trước khi chạy. Kết quả mong đợi phải xuất phát từ yêu cầu; không dùng chính hàm đang kiểm tra để tính cả kết quả thực tế lẫn kết quả mong đợi.

Các tính chất như “kết quả còn nằm trong tháng đích” hay “kết quả đúng ngày cuối tháng” bổ sung tốt cho những ví dụ ngày cố định. Tuy nhiên, chỉ kiểm tra “không ném lỗi” là chưa đủ: ngày 29/3 vẫn hợp lệ dù hạn chốt đúng phải là 31/3.

## 9. Lỗi thường gặp và cách sửa

- **Bỏ qua giá trị trả về:** `LocalDate` bất biến. Gọi `date.plusMonths(1)` rồi tiếp tục dùng biến cũ không cập nhật được ngày; phải giữ kết quả vào biến hoặc trả nó về.
- **Cho rằng mọi ngày sai đều được lùi:** dùng đúng hợp đồng của từng phương thức. `withDayOfMonth(30)` trong tháng 2 báo lỗi, khác `withMonth(2)` từ ngày 31.
- **Lấy ngày 28 làm cuối tháng 2 cố định:** dùng `YearMonth.lengthOfMonth()` hoặc `atEndOfMonth()`.
- **Cộng 30 ngày để thay một tháng:** viết đúng đơn vị mà yêu cầu nêu; kiểm tra ca 31/1/2024 để thấy khác biệt.
- **Lấy kết quả kỳ trước làm mốc trong khi cần giữ ngày gốc:** lưu ngày yêu cầu và tính từng kỳ từ `YearMonth` gốc.
- **Cho rằng lịch sinh ngày 29/2 phải luôn lùi về 28/2:** Java có hành vi API cụ thể, còn ngày kỷ niệm trong nghiệp vụ có thể được quy định khác. Phải xác định chính sách rồi mới triển khai.
- **Bắt ngoại lệ rồi âm thầm chọn ngày khác:** chỉ đổi sang ngày cuối tháng khi chính sách cho phép; nếu không, trả lỗi hoặc xử lý kỳ không hợp lệ rõ ràng.

## 10. Thực hành có đáp án định hướng

1. **Đổi yêu cầu lịch thu phí sang ngày 30.** Với tháng 2 và tháng 3/2024, hãy dự đoán kết quả trước khi gọi `dueDate`. Kết quả đúng là `2024-02-29` và `2024-03-30`; nếu tháng 3 ra ngày 29, mã đang bị trôi theo kỳ trước; nếu ra ngày 31, mã đang dùng chính sách cuối tháng.

2. **Thêm ca từ 31/3/2024 sang tháng 4.** `plusMonths(1)` cho `2024-04-30`. Sau đó cộng tiếp một tháng cho `2024-05-30`, trong khi cộng trực tiếp hai tháng từ ngày gốc cho `2024-05-31`.

3. **Dự đoán ngày sau bốn lần cộng một năm từ 29/2/2024.** Kết quả cuối là `2028-02-28`. So sánh với một lần `plusYears(4)`, được `2028-02-29`; giải thích thông tin bị mất ở bước nào.

4. **Đổi chính sách thành “tháng nào không có ngày yêu cầu thì báo lỗi”.** Bỏ bước `Math.min` và dùng `month.atDay(requestedDay)`, hoặc kiểm tra `isValidDay` trước. Ca tháng 2/2024 với ngày 31 phải bị từ chối; không được âm thầm lùi ngày.

Khi đọc hoặc viết một phép điều chỉnh ngày, hãy luôn chỉ ra cả quy tắc của API và quy tắc nghiệp vụ mà phép điều chỉnh đang thực hiện. Đó là cơ sở để biết nên chấp nhận ngày đã lùi, yêu cầu ngày cuối tháng, hay báo lỗi.
