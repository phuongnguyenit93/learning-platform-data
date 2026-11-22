# Cộng trừ Period và thứ tự áp dụng lên ngày trong Java

## 1. Period mô tả thay đổi lịch, không phải số ngày cố định

`java.time.Period` biểu diễn một khoảng thời gian theo **năm, tháng và ngày theo lịch**. Nó phù hợp với các yêu cầu như “cộng một tháng vào ngày thanh toán”, “thêm hai năm”, “lùi ba ngày” hoặc “tính khoảng cách lịch giữa hai ngày”.

Khác với `Duration`, thường diễn đạt thời lượng theo giây và nano giây, `Period` không quy mọi thứ về một số giây hay số ngày cố định. Một tháng có thể dài 28, 29, 30 hoặc 31 ngày; một năm có thể có 365 hoặc 366 ngày. Vì thế, cộng một tháng vào ngày 31 có thể làm ngày kết quả được điều chỉnh về cuối tháng.

Ví dụ quan trọng:

~~~java
LocalDate start = LocalDate.of(2023, 1, 31);

System.out.println(start.plusMonths(1));
System.out.println(start.plus(Period.ofMonths(1)));
System.out.println(start.plus(Period.ofMonths(2)));
System.out.println(start.plusMonths(1).plusMonths(1));
~~~

Stdout:

~~~text
2023-02-28
2023-02-28
2023-03-31
2023-03-28
~~~

Hai cách đầu tương đương trong ví dụ này: cộng **một tháng lịch** từ ngày 31/01 thì ngày 31/02 không tồn tại, nên kết quả được điều chỉnh thành ngày cuối tháng 2, tức 28/02/2023. Nhưng “cộng hai tháng cùng lúc” và “cộng một tháng hai lần” có thể khác nhau, bởi lần cộng đầu tiên làm thay đổi ngày dùng cho phép tính tiếp theo.

Đây là chủ đề cốt lõi: `Period` là một bộ thành phần năm/tháng/ngày; nó **không lưu một chuỗi các thao tác ngày tháng đã được thực hiện**. Khi cần thứ tự cụ thể, hãy nhìn vào từng lời gọi đang áp dụng lên ngày nào.

## 2. Tạo và đọc Period

Các factory thông dụng:

~~~java
Period days = Period.ofDays(10);
Period months = Period.ofMonths(2);
Period years = Period.ofYears(1);
Period mixed = Period.of(1, 2, 3);
Period parsed = Period.parse("P1Y2M3D");
~~~

Dữ liệu `Period.of(years, months, days)` gồm ba trường nguyên:

| Cách tạo | Giá trị lịch | `toString()` |
|---|---|---|
| `Period.ofDays(10)` | 10 ngày | `P10D` |
| `Period.ofMonths(2)` | 2 tháng | `P2M` |
| `Period.ofYears(1)` | 1 năm | `P1Y` |
| `Period.of(1, 2, 3)` | 1 năm, 2 tháng, 3 ngày | `P1Y2M3D` |
| `Period.ZERO` | Không thay đổi năm/tháng/ngày | `P0D` |

Chuỗi theo ISO-8601 sử dụng `P` mở đầu cho period; `Y` là năm, `M` trong phần năm-tháng là tháng, `D` là ngày. Ví dụ `Period.parse("P1Y2M3D")` tạo một Period gồm 1 năm, 2 tháng và 3 ngày.

Các phương thức đọc gồm:

- `getYears()`: số năm.
- `getMonths()`: số tháng trong **thành phần tháng**, không phải tổng tháng gộp với năm.
- `getDays()`: số ngày trong **thành phần ngày**.
- `isZero()`: có phải period bằng 0 hay không.
- `isNegative()`: có ít nhất một thành phần âm không.
- `toTotalMonths()`: chuyển năm và tháng thành tổng số tháng; **không** bao gồm ngày vì một ngày không có quy đổi số tháng cố định.

Lưu ý rằng `Period.of(1, 14, 3)` vẫn có thể giữ trường tháng là 14. `Period` không tự chuẩn hóa mọi giá trị vào dạng “0–11 tháng” lúc tạo; gọi `normalized()` nếu muốn gộp mỗi 12 tháng thành một năm.

## 3. Cách áp dụng Period lên LocalDate

`LocalDate.plus(Period)` áp dụng thành phần **năm và tháng trước**, sau đó áp dụng **ngày**. Có thể hiểu việc cộng một period tương đương với quy trình lịch:

1. Cộng số năm và số tháng trên ngày ban đầu như một tổng số tháng.
2. Nếu ngày trong tháng ban đầu không tồn tại trong tháng kết quả, điều chỉnh về ngày cuối hợp lệ của tháng đó.
3. Cộng số ngày trong period vào kết quả vừa tạo.

Ví dụ:

~~~java
LocalDate jan31 = LocalDate.of(2023, 1, 31);
Period oneMonthMinusOneDay = Period.ofMonths(1).minusDays(1);

System.out.println(jan31.plus(oneMonthMinusOneDay));
System.out.println(jan31.plusMonths(1).minusDays(1));
~~~

Stdout:

~~~text
2023-02-27
2023-02-27
~~~

Lý do: bước cộng tháng đưa 31/01/2023 đến 28/02/2023, vì tháng 2 năm 2023 chỉ có 28 ngày. Sau đó trừ một ngày thành 27/02/2023.

### 3.1. Cộng Period là áp dụng thành phần, không lặp thao tác

Không được đọc `Period.ofMonths(2)` là “hãy gọi plusMonths(1) hai lần”. Nó có nghĩa **cộng hai tháng trong cùng một phép tính lịch**:

~~~java
LocalDate start = LocalDate.of(2023, 1, 31);

LocalDate twoMonthsAtOnce = start.plus(Period.ofMonths(2));
LocalDate oneMonthTwice =
        start.plusMonths(1).plusMonths(1);

System.out.println(twoMonthsAtOnce);
System.out.println(oneMonthTwice);
~~~

Stdout:

~~~text
2023-03-31
2023-03-28
~~~

Giải thích:

- Cộng hai tháng trực tiếp: 31/01 + 2 tháng = 31/03; ngày 31 tồn tại trong tháng 3.
- Cộng một tháng lần đầu: 31/01 → 28/02 (ngày 31 không tồn tại).
- Cộng thêm một tháng từ kết quả 28/02: 28/02 → 28/03.

**Ngày sau lần cộng đầu tiên trở thành đầu vào cho lần cộng thứ hai.** Thông tin rằng ngày gốc là 31 đã không còn trong giá trị 28/02, nên lần thứ hai không thể “khôi phục” ngày 31.

Sự khác biệt này ảnh hưởng tới lịch thanh toán hàng tháng, ngày đáo hạn, lịch lặp theo ngày trong tháng và các phép tính tháng cuối năm. Nếu muốn “ngày cuối mỗi tháng”, đừng cộng tháng lặp lại từ một ngày đã bị điều chỉnh rồi mặc định luôn nhận cuối tháng; dùng chính sách cuối tháng tường minh, chẳng hạn `YearMonth.atEndOfMonth()`.

## 4. Thứ tự cộng và trừ là quan trọng

Phép tính ngày tháng thường **không giao hoán**. Nghĩa là đổi thứ tự hai thao tác có thể tạo kết quả khác nhau:

~~~java
LocalDate start = LocalDate.of(2023, 1, 31);

LocalDate a = start.plusMonths(1).minusDays(1);
LocalDate b = start.minusDays(1).plusMonths(1);

System.out.println(a);
System.out.println(b);
~~~

Stdout:

~~~text
2023-02-27
2023-02-28
~~~

Chi tiết:

- `a`: 31/01 + 1 tháng → 28/02; trừ 1 ngày → 27/02.
- `b`: 31/01 − 1 ngày → 30/01; cộng 1 tháng → 28/02.

Hai biểu thức dùng cùng hai đơn vị tháng và ngày nhưng kết quả khác nhau do ngày được điều chỉnh ở các thời điểm khác nhau.

### 4.1. Period kết hợp không ghi lại thứ tự thao tác

Xét:

~~~java
Period p = Period.ofMonths(1).minusDays(1);
LocalDate combined = LocalDate.of(2023, 1, 31).plus(p);
~~~

`combined` là `2023-02-27` vì period chứa các trường `months = 1` và `days = -1`; khi áp dụng, Java cộng tháng trước rồi cộng ngày sau.

Không có một lịch sử nào được lưu để nói người tạo period đã gọi “trừ ngày trước, cộng tháng sau”. Hai cách sau:

~~~java
Period p1 = Period.ofMonths(1).minusDays(1);
Period p2 = Period.ofDays(-1).plusMonths(1);

System.out.println(p1);
System.out.println(p2);
~~~

Đều biểu diễn `P1M-1D`. Cộng hai đối tượng đó vào một LocalDate sẽ tuân theo cùng quy tắc áp dụng thành phần của Period. Nếu nghiệp vụ bắt buộc thứ tự “trừ một ngày trước rồi mới cộng một tháng”, hãy giữ hai phép gọi riêng trên LocalDate:

~~~java
LocalDate ordered = start.minusDays(1).plusMonths(1);
~~~

Không gộp chúng thành một Period với kỳ vọng ghi lại thứ tự.

## 5. Thứ tự bên trong một Period có cả năm, tháng và ngày

Với `Period.of(1, 2, 3)`, Java áp dụng năm/tháng như tổng số tháng rồi cộng số ngày. Ví dụ:

~~~java
LocalDate start = LocalDate.of(2020, 2, 29);
Period p = Period.of(1, 1, 1);

System.out.println(start.plus(p));
~~~

Stdout:

~~~text
2021-03-30
~~~

Diễn giải:

1. Cộng một năm và một tháng: 29/02/2020 + 13 tháng → 29/03/2021. Ngày 29 có tồn tại trong tháng 3.
2. Cộng thêm một ngày → 30/03/2021.

Đối với những ngày không tồn tại ở tháng đích, phần năm/tháng cũng điều chỉnh ngày về cuối tháng trước khi cộng phần ngày. Ví dụ:

~~~java
LocalDate start = LocalDate.of(2020, 2, 29);
System.out.println(start.plus(Period.ofYears(1)));
System.out.println(start.plus(Period.ofYears(1).plusDays(1)));
~~~

Stdout:

~~~text
2021-02-28
2021-03-01
~~~

Cộng một năm từ 29/02/2020 → 28/02/2021, rồi cộng một ngày → 01/03/2021. Điều này **khác** với suy luận “một năm luôn bằng 365 ngày”; Period đang thao tác theo quy tắc lịch.

## 6. Trừ Period: dấu âm và hai cách viết tương đương

Có thể trừ period bằng `minus(Period)`:

~~~java
LocalDate date = LocalDate.of(2024, 3, 31);

System.out.println(date.minus(Period.ofMonths(1)));
System.out.println(date.plus(Period.ofMonths(-1)));
System.out.println(date.minusMonths(1));
~~~

Ba kết quả đều là `2024-02-29`. Lý do tháng 2 năm nhuận 2024 có 29 ngày, nên ngày 31/03 trừ một tháng được điều chỉnh thành ngày cuối tháng 2.

`Period.negated()` đổi dấu các thành phần; `Period.multipliedBy(-1)` cũng tạo period đổi dấu. Ví dụ:

~~~java
Period p = Period.of(1, 2, 3);
System.out.println(p.negated());
System.out.println(p.multipliedBy(-1));
~~~

Cả hai in `P-1Y-2M-3D`.

Chú ý: một Period có thể có các trường **trái dấu nhau**, ví dụ `P1M-1D`. `isNegative()` trả về true nếu **bất kỳ thành phần nào âm**, kể cả khi các thành phần dương khác làm ta có cảm giác period “tổng thể” vẫn dương. Với mixed period, không có một tổng số ngày cố định để đánh giá độ dài; phải áp dụng lên ngày cụ thể mới biết kết quả.

## 7. Period.between(): khoảng lịch phụ thuộc hai ngày

`Period.between(start, end)` trả về period từ ngày bắt đầu đến ngày kết thúc; dấu sẽ phụ thuộc thứ tự hai ngày. Ví dụ:

~~~java
LocalDate start = LocalDate.of(2023, 1, 15);
LocalDate end = LocalDate.of(2023, 6, 1);

System.out.println(Period.between(start, end));
System.out.println(Period.between(end, start));
~~~

Stdout:

~~~text
P4M17D
P-4M-17D
~~~

Với 31/01/2023 đến 28/02/2023:

~~~java
System.out.println(Period.between(
        LocalDate.of(2023, 1, 31),
        LocalDate.of(2023, 2, 28)));
~~~

Kết quả:

~~~text
P28D
~~~

`Period.between` không phải phép chia tổng số ngày thành “mỗi tháng đúng 30 ngày”. Kết quả tùy hai ngày đầu/cuối và quy tắc lịch. Nếu chỉ cần số ngày tuyệt đối giữa hai ngày ISO, dùng:

~~~java
long days = ChronoUnit.DAYS.between(start, end);
~~~

Đối với hai giá trị `LocalDate`, `ChronoUnit.DAYS.between` cho tổng số ngày giữa chúng. Period thích hợp khi cần biểu diễn độ lệch lịch năm/tháng/ngày để đọc và áp dụng lại.

Một lưu ý nghiệp vụ: `Period.between(a, b)` không đảm bảo `a.plus(Period.between(a, b)).equals(b)` cho mọi tổ hợp? Với `LocalDate`, Period được sinh ra để biểu diễn khoảng lịch theo thuật toán `until` và cộng lại thường khôi phục ngày đích; nhưng không nên dùng một Period đã làm tròn hoặc tự sửa các thành phần như thể nó là duration cố định. Hãy kiểm tra round-trip trong miền dữ liệu thật nếu ngày cuối tháng, năm nhuận hoặc period âm có ý nghĩa nghiệp vụ.

## 8. normalized(): chuẩn hóa tháng thành năm

`Period.normalized()` chuyển phần tháng thành số năm và tháng còn lại, sao cho tháng nằm trong khoảng -11 đến 11 với dấu phù hợp của phép chuẩn hóa năm/tháng:

~~~java
Period original = Period.of(1, 14, 3);
System.out.println(original);
System.out.println(original.normalized());
~~~

Stdout:

~~~text
P1Y14M3D
P2Y2M3D
~~~

`normalized()` **không** chuyển ngày thành tháng hoặc năm; nó chỉ chuẩn hóa quan hệ 12 tháng = 1 năm. Một tháng có độ dài ngày khác nhau nên không thể chuẩn hóa `P1M30D` thành một dạng tương đương lịch duy nhất dựa trên số ngày.

~~~java
System.out.println(Period.ofMonths(1).plusDays(30));
~~~

Stdout:

~~~text
P1M30D
~~~

`P1M30D` không có nghĩa luôn bằng hai tháng. Trên ngày 01/01 nó có thể thành 02/03 hoặc 03/02 tùy năm/tháng, trong khi cộng trực tiếp hai tháng cho một ngày cụ thể có quy tắc khác. Không dùng `toTotalMonths()` để đổi toàn bộ period có ngày thành số tháng; phương thức đó chỉ tính `years * 12 + months` và bỏ phần ngày.

### 8.1. Không phải mọi Period mixed-sign đều “chuẩn hóa thành dương/âm đồng nhất”

Một Period được phép có thành phần năm/tháng/ngày khác dấu. Ví dụ `P1M-40D`. `normalized()` không giải quyết độ dài ngày thực tế để làm mọi trường cùng dấu, bởi phải biết ngày bắt đầu mới tính được độ dài tháng.

Đừng viết logic như:

~~~java
if (period.toTotalMonths() > 0) {
    // Cho rằng toàn bộ period là dương
}
~~~

nếu period có phần ngày âm. `toTotalMonths()` có thể dương trong khi `getDays()` âm. Hãy kiểm tra từng thành phần, hoặc áp dụng lên ngày cụ thể và so sánh ngày kết quả nếu đó là điều nghiệp vụ cần biết.

## 9. Phân biệt Period và Duration

| Đặc điểm | `Period` | `Duration` |
|---|---|---|
| Đơn vị chính | Năm, tháng, ngày lịch | Giây và nano giây |
| Dùng với | `LocalDate`, ngày tháng lịch | `Instant`, `Duration.between`; các kiểu thời gian tương thích |
| Tháng | Là thành phần lịch, không cố định số ngày | Không có đơn vị tháng |
| Ngày | Một ngày lịch | 24 giờ theo duration khi được biểu diễn là `Duration.ofDays(1)` |
| Cộng lên ZonedDateTime | Cộng ngày lịch theo quy tắc ngày/zone | Cộng thời lượng theo thời gian trôi qua |
| Có thể cộng lại nhiều lần ra kết quả khác so với cộng một lần? | Có, do cuối tháng | Thường là cộng số giây/nano tổng, nhưng cách nhìn local có thể đổi qua DST |

Ví dụ quan trọng cho lịch có múi giờ:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, zone);

System.out.println(start.plus(Period.ofDays(1)));
System.out.println(start.plus(Duration.ofDays(1)));
~~~

Trong thời điểm New York bắt đầu DST, ngày lịch tiếp theo có thể chỉ cách instant ban đầu 23 giờ. Cộng `Period.ofDays(1)` giữ ý nghĩa **cùng giờ địa phương ngày kế tiếp**, còn `Duration.ofDays(1)` cộng đúng 24 giờ trôi qua và có thể cho giờ địa phương muộn hơn một giờ.

Dùng Period khi yêu cầu là **ngày lịch** (“ngày mai”, “thêm một tháng”, “hạn thanh toán”), Duration khi yêu cầu là **thời lượng** (“sau đúng 24 giờ”, “timeout 30 giây”). Đừng chuyển ngầm giữa hai ý nghĩa.

## 10. Chương trình Java chạy độc lập: thứ tự áp dụng

Lưu trong tệp **`PeriodOrderDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.Period;
import java.time.temporal.ChronoUnit;

public class PeriodOrderDemo {
    public static void main(String[] args) {
        LocalDate jan31 = LocalDate.of(2023, 1, 31);

        LocalDate oneMonthTwice =
                jan31.plusMonths(1).plusMonths(1);
        LocalDate twoMonthsOnce =
                jan31.plus(Period.ofMonths(2));

        LocalDate monthThenMinusDay =
                jan31.plusMonths(1).minusDays(1);
        LocalDate dayThenMonth =
                jan31.minusDays(1).plusMonths(1);

        System.out.println("One month twice: " + oneMonthTwice);
        System.out.println("Two months at once: " + twoMonthsOnce);
        System.out.println("Month then minus day: " + monthThenMinusDay);
        System.out.println("Minus day then month: " + dayThenMonth);
        System.out.println("Period between: " + Period.between(
                jan31, LocalDate.of(2023, 2, 28)));
        System.out.println("Days between: " + ChronoUnit.DAYS.between(
                jan31, LocalDate.of(2023, 2, 28)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PeriodOrderDemo.java
java PeriodOrderDemo
~~~

Stdout:

~~~text
One month twice: 2023-03-28
Two months at once: 2023-03-31
Month then minus day: 2023-02-27
Minus day then month: 2023-02-28
Period between: P28D
Days between: 28
~~~

Kết quả cho thấy **thứ tự và điểm bắt đầu** quyết định hành vi điều chỉnh cuối tháng. Khi đọc code chứa chuỗi phương thức, hãy diễn giải từ trái sang phải bằng ngày trung gian cụ thể; không thay chuỗi các phép toán bằng một Period tổng hợp nếu chưa chứng minh hai cách tương đương.

## 11. Lỗi thường gặp và cách tránh

1. **Coi tháng là 30 ngày:** không đúng. Tháng có thể 28–31 ngày; năm còn có thể nhuận.
2. **Coi `Period.ofMonths(2)` bằng hai lần `plusMonths(1)`:** ngày cuối tháng có thể bị điều chỉnh ở lần đầu và thay đổi kết quả lần sau.
3. **Gộp các phép cộng/trừ rồi tưởng giữ nguyên thứ tự:** Period lưu thành phần, không lưu lịch sử lời gọi. Giữ các lời gọi riêng nếu thứ tự nghiệp vụ quan trọng.
4. **Giả định mọi ngày kết quả giữ số ngày trong tháng:** 31/01 + 1 tháng là 28/02 hoặc 29/02 tùy năm.
5. **Dùng Period như một duration tính timeout:** Period mang thành phần lịch; dùng Duration hoặc Instant cho lượng thời gian tuyệt đối.
6. **Dùng `toTotalMonths()` cho period có thành phần ngày:** nó bỏ ngày, không phải tổng tháng thực tế.
7. **Nghĩ `normalized()` chuẩn hóa mọi thành phần:** nó chỉ gộp tháng vào năm, không đổi ngày thành tháng.
8. **Không xét mixed-sign Period:** `P1M-40D` có trường tháng dương, ngày âm; không thể kết luận dấu “tổng thể” bằng riêng tổng tháng.
9. **Hiểu nhầm `Period.between` là số ngày cố định chia thành tháng:** kết quả theo quy tắc lịch; dùng `ChronoUnit.DAYS.between` nếu cần tổng ngày.
10. **Dùng chuỗi `P1M-1D` để biểu diễn trình tự “trừ ngày rồi cộng tháng”:** nó không lưu thứ tự. Viết các phép thao tác trên ngày lần lượt.
11. **Cộng một ngày vào ZonedDateTime rồi mặc định đúng 24 giờ đã trôi qua:** DST có thể làm ngày lịch dài 23/25 giờ.
12. **Bỏ qua năm nhuận:** 29/02 + 1 năm có thể là 28/02 năm tiếp theo; cộng ngày sau đó tiếp tục từ ngày đã điều chỉnh.
13. **Không kiểm tra miền dữ liệu âm:** subtract và Period âm có thể tạo kết quả khác với phép cộng dương đảo lại vì điều chỉnh cuối tháng.
14. **Dùng Period như chính sách cuối tháng lặp:** lịch cuối tháng nên được tính lại từ YearMonth hoặc quy tắc “end of month”, không chỉ dựa vào ngày sau lần cộng trước.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Kết quả của `LocalDate.of(2023,1,31).plus(Period.ofMonths(2))` là gì? Vì sao khác hai lần cộng một tháng?

**Đáp án:** `2023-03-31`. Hai tháng được cộng trong một phép tính. Hai lần cộng một tháng đưa 31/01 → 28/02 → 28/03 vì lần đầu đã điều chỉnh ngày cuối tháng.

**Câu 2.** So sánh `start.plusMonths(1).minusDays(1)` với `start.minusDays(1).plusMonths(1)` cho start = 31/01/2023.

**Đáp án:** Kết quả lần lượt là `2023-02-27` và `2023-02-28`; thứ tự thao tác không giao hoán.

**Câu 3.** `Period.of(1,14,3).normalized()` cho gì?

**Đáp án:** `P2Y2M3D`, vì 14 tháng được đổi thành 1 năm 2 tháng; thành phần ngày giữ nguyên.

**Câu 4.** `Period.ofMonths(1).plusDays(30).normalized()` có thể đổi thành hai tháng không?

**Đáp án:** Không có quy đổi lịch tổng quát như vậy. `normalized()` chỉ chuẩn hóa tháng/năm; tháng không có một số ngày cố định.

**Câu 5.** Tại sao `Period.between(2023-01-31, 2023-02-28)` là `P28D`?

**Đáp án:** Theo thuật toán khoảng lịch của LocalDate, khoảng từ ngày 31/01 đến 28/02 năm đó được biểu diễn thành 28 ngày. Period không ép mọi tháng thành một độ dài cố định.

**Câu 6.** Khi nào dùng Period, khi nào dùng Duration?

**Đáp án:** Period cho thay đổi ngày lịch theo năm/tháng/ngày; Duration cho thời lượng giây/nano. Timeout 24 giờ dùng Duration; hạn vào ngày tháng sau dùng Period hoặc phép lịch tương ứng.

**Câu 7.** `P1M-1D` lưu thông tin rằng ngày phải bị trừ trước khi cộng tháng không?

**Đáp án:** Không. Nó lưu trường 1 tháng và -1 ngày. Khi áp dụng lên LocalDate, phần tháng được áp dụng trước phần ngày.

**Câu 8.** Vì sao phải cẩn thận khi cộng một Period nhiều lần?

**Đáp án:** Vì ngày trung gian sau mỗi lần cộng có thể đã bị điều chỉnh đến cuối tháng. Phép cộng tiếp theo dùng ngày trung gian đó làm đầu vào, nên có thể cho kết quả khác phép cộng tổng số tháng một lần.

## 13. Quy tắc thực hành

- Đọc `Period` như **ba thành phần lịch**, không như một số ngày cố định.
- Khi áp dụng lên `LocalDate`, nhớ năm/tháng được xử lý trước ngày; ngày không tồn tại ở tháng đích sẽ được điều chỉnh về cuối tháng.
- Nếu nghiệp vụ quy định nhiều bước có thứ tự, giữ nguyên các bước trên ngày; đừng gộp thành một Period và kỳ vọng lưu thứ tự.
- Khi muốn cộng hai tháng từ ngày gốc, dùng một phép cộng hai tháng. Khi muốn quy tắc lặp hằng tháng, xác định rõ ngày gốc/điều chỉnh cuối tháng để kết quả mỗi kỳ ổn định.
- Chọn `Period` cho thay đổi lịch và `Duration` cho thời lượng. Với `ZonedDateTime`, ngày lịch và 24 giờ đã trôi qua có thể cho kết quả khác nhau quanh DST.
- Kiểm thử ít nhất ngày 29/30/31, tháng 2, năm nhuận, Period âm/mixed-sign và các chuỗi cộng/trừ nhiều bước.

Khi tính toán ngày tháng trong Java, **thứ tự áp dụng là một phần của ý nghĩa nghiệp vụ**. Hiểu cách `Period` lưu thành phần và cách `LocalDate` điều chỉnh ngày cuối tháng giúp tránh sai hạn thanh toán, lịch lặp và phép tính ngày giữa các kỳ.
