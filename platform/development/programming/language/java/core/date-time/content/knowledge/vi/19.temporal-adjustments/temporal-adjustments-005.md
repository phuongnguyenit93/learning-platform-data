# Tìm một thứ cụ thể trong tháng

## Từ quy tắc lịch sang ngày cụ thể

“Thứ Hai thứ hai của tháng” là một quy tắc khác với “Thứ Hai sắp tới”. Quy tắc thứ nhất lấy **tháng** làm phạm vi; quy tắc thứ hai lấy **ngày hiện tại** làm mốc di chuyển.

Ví dụ, với ngày nguồn `2024-02-18`:

- Thứ Hai đầu tiên của tháng là `2024-02-05`.
- Thứ Hai lần thứ hai của tháng là `2024-02-12`.
- Thứ Hai kế tiếp sau ngày nguồn là `2024-02-19`.

`TemporalAdjusters` giúp diễn đạt trực tiếp các quy tắc như lần đầu, lần cuối hoặc lần thứ n của một thứ trong tháng. Bài này dùng `LocalDate` theo lịch ISO và tuần bảy ngày.

## 1. Chọn bộ điều chỉnh theo yêu cầu

| Yêu cầu | Cách viết với ngày nguồn `date` |
| --- | --- |
| Thứ Hai đầu tiên trong tháng | `date.with(TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY))` |
| Thứ Sáu cuối cùng trong tháng | `date.with(TemporalAdjusters.lastInMonth(DayOfWeek.FRIDAY))` |
| Thứ Hai lần thứ hai trong tháng | `date.with(TemporalAdjusters.dayOfWeekInMonth(2, DayOfWeek.MONDAY))` |
| Thứ Hai cuối cùng trong tháng | `date.with(TemporalAdjusters.dayOfWeekInMonth(-1, DayOfWeek.MONDAY))` |
| Thứ Hai áp chót trong tháng | `date.with(TemporalAdjusters.dayOfWeekInMonth(-2, DayOfWeek.MONDAY))` |

`firstInMonth` và `lastInMonth` trả về ngày khớp trong tháng chứa ngày nguồn. Với `dayOfWeekInMonth`, số thứ tự dương đếm từ đầu tháng, số âm đếm từ cuối tháng. Cần lưu ý riêng khả năng kết quả vượt biên tháng. [Tài liệu `TemporalAdjusters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAdjusters.html)

`DayOfWeek` có bảy hằng:

```java
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY
```

Đoạn trên liệt kê tên hằng, không phải một chương trình độc lập. Trong mã, dùng `DayOfWeek.MONDAY` thường rõ hơn một con số. Theo ISO, `getValue()` của `DayOfWeek` là 1 cho Thứ Hai đến 7 cho Chủ nhật; không dùng `ordinal()` để lấy số thứ theo lịch. [Tài liệu `DayOfWeek`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/DayOfWeek.html)

## 2. Hình dung cách đếm lần xuất hiện

Tháng 02/2024 có các Thứ Hai:

```text
05/02       12/02       19/02       26/02
lần 1       lần 2       lần 3       lần 4
đầu tiên                           cuối cùng
                       áp chót
```

Đếm từ đầu:

```text
ordinal = 1 → 05/02
ordinal = 2 → 12/02
ordinal = 3 → 19/02
ordinal = 4 → 26/02
```

Đếm từ cuối:

```text
ordinal = -1 → 26/02
ordinal = -2 → 19/02
ordinal = -3 → 12/02
ordinal = -4 → 05/02
```

Ngày nguồn có thể là bất kỳ ngày nào trong tháng. Nó không bắt buộc nằm trước ngày kết quả. Vì vậy, lấy Thứ Hai đầu tiên từ ngày 18/02 có thể đưa kết quả về trước ngày nguồn.

## 3. Chương trình hoàn chỉnh

Lưu dưới tên `WeekdayInMonthDemo.java`. Chương trình dùng Java 17 trở lên:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class WeekdayInMonthDemo {
    static Optional<LocalDate> nthWeekdayInMonth(
            YearMonth month, int occurrence, DayOfWeek weekday) {
        if (occurrence < 1 || occurrence > 5) {
            throw new IllegalArgumentException("Lan xuat hien phai trong 1..5");
        }

        LocalDate candidate = month.atDay(1).with(
                TemporalAdjusters.dayOfWeekInMonth(occurrence, weekday));

        if (!YearMonth.from(candidate).equals(month)) {
            return Optional.empty();
        }
        return Optional.of(candidate);
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 18);
        YearMonth month = YearMonth.from(date);

        LocalDate firstMonday =
                date.with(TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY));
        LocalDate secondMonday =
                date.with(TemporalAdjusters.dayOfWeekInMonth(2, DayOfWeek.MONDAY));
        LocalDate lastFriday =
                date.with(TemporalAdjusters.lastInMonth(DayOfWeek.FRIDAY));
        LocalDate lastMonday =
                date.with(TemporalAdjusters.dayOfWeekInMonth(-1, DayOfWeek.MONDAY));
        LocalDate secondLastMonday =
                date.with(TemporalAdjusters.dayOfWeekInMonth(-2, DayOfWeek.MONDAY));

        System.out.println("original=" + date);
        System.out.println("firstMonday=" + firstMonday);
        System.out.println("secondMonday=" + secondMonday);
        System.out.println("lastFriday=" + lastFriday);
        System.out.println("lastMonday=" + lastMonday);
        System.out.println("secondLastMonday=" + secondLastMonday);

        LocalDate fifthMonday =
                date.with(TemporalAdjusters.dayOfWeekInMonth(5, DayOfWeek.MONDAY));
        LocalDate zeroMonday =
                date.with(TemporalAdjusters.dayOfWeekInMonth(0, DayOfWeek.MONDAY));

        System.out.println("rawFifthMonday=" + fifthMonday);
        System.out.println("zeroMonday=" + zeroMonday);

        System.out.println("checkedFifthMonday="
                + nthWeekdayInMonth(month, 5, DayOfWeek.MONDAY)
                        .map(LocalDate::toString)
                        .orElse("NONE"));
        System.out.println("checkedFifthThursday="
                + nthWeekdayInMonth(month, 5, DayOfWeek.THURSDAY)
                        .map(LocalDate::toString)
                        .orElse("NONE"));

        System.out.println("nextMondayFromOriginal="
                + date.with(TemporalAdjusters.next(DayOfWeek.MONDAY)));

        List<LocalDate> mondays = new ArrayList<>();
        for (LocalDate current = firstMonday;
             YearMonth.from(current).equals(month);
             current = current.plusWeeks(1)) {
            mondays.add(current);
        }
        System.out.println("allMondays=" + mondays);

        System.out.println("addingOneMonth=" + secondMonday.plusMonths(1));
        LocalDate nextSecondMonday = month.plusMonths(1).atDay(1).with(
                TemporalAdjusters.dayOfWeekInMonth(2, DayOfWeek.MONDAY));
        System.out.println("recomputedNextMonth=" + nextSecondMonday);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 WeekdayInMonthDemo.java
java WeekdayInMonthDemo
```

Stdout:

```text
original=2024-02-18
firstMonday=2024-02-05
secondMonday=2024-02-12
lastFriday=2024-02-23
lastMonday=2024-02-26
secondLastMonday=2024-02-19
rawFifthMonday=2024-03-04
zeroMonday=2024-01-29
checkedFifthMonday=NONE
checkedFifthThursday=2024-02-29
nextMondayFromOriginal=2024-02-19
allMondays=[2024-02-05, 2024-02-12, 2024-02-19, 2024-02-26]
addingOneMonth=2024-03-12
recomputedNextMonth=2024-03-11
```

## 4. Điểm quan trọng: `dayOfWeekInMonth` có thể đi ra ngoài tháng

Tên phương thức dễ khiến người đọc nghĩ nó luôn trả về một ngày trong tháng. Nhưng thuật toán đếm có thể đi tiếp sang tháng khác.

Trong tháng 02/2024 chỉ có bốn Thứ Hai. Yêu cầu lần thứ năm tiếp tục tiến một tuần từ lần thứ tư, cho `2024-03-04`, không tự ném lỗi vì “tháng này thiếu lần thứ năm”.

Tương tự, số thứ tự `0` có ý nghĩa được API định nghĩa: lần khớp cuối cùng của tháng trước. Trong ví dụ, kết quả là `2024-01-29`. Những số âm có độ lớn vượt số lần xuất hiện trong tháng cũng có thể đưa kết quả về tháng trước.

`dayOfWeekInMonth` không giới hạn tham số số thứ tự vào tập 1..5; nó diễn giải số thứ tự theo thuật toán đếm tuần. [Tài liệu `dayOfWeekInMonth`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAdjusters.html#dayOfWeekInMonth(int,java.time.DayOfWeek))

Vì vậy, với yêu cầu nghiệp vụ **phải tồn tại trong chính tháng được chọn**, cần kiểm tra lại kết quả.

Hàm `nthWeekdayInMonth` trong chương trình áp dụng một hợp đồng riêng:

- Chỉ nhận lần xuất hiện dương từ 1 đến 5.
- Tính ứng viên bằng thư viện.
- So sánh cả năm và tháng của ứng viên với tháng yêu cầu.
- Trả `Optional.empty()` nếu lần xuất hiện đó không có trong tháng.

Giới hạn 1..5 là lựa chọn của hàm ứng dụng, không phải mô tả giới hạn tham số của API Java.

So sánh `YearMonth` giúp kiểm tra cả năm khi kết quả đi qua ranh giới 31/12. Không nên chỉ so sánh tên tháng hoặc số tháng nếu mục đích là xác nhận đúng kỳ năm–tháng.

## 5. “Lần cuối” không đồng nghĩa “lần thứ năm”

Một thứ có thể xuất hiện bốn hoặc năm lần trong tháng. Do đó:

```java
date.with(TemporalAdjusters.lastInMonth(DayOfWeek.FRIDAY));
```

không tương đương:

```java
date.with(TemporalAdjusters.dayOfWeekInMonth(5, DayOfWeek.FRIDAY));
```

Đây là hai đoạn minh họa với `date` đã có. Trong tháng 02/2024, Thứ Sáu cuối là 23/02, trong khi lần thứ năm sẽ đi sang tháng 03.

Nếu yêu cầu là “Thứ Sáu cuối cùng”, dùng `lastInMonth` hoặc số thứ tự `-1`. Chỉ dùng lần thứ năm khi nghiệp vụ thực sự yêu cầu lần thứ năm và đã có chính sách cho tháng không có lần đó.

Các chính sách có thể là không tạo lịch tháng đó, báo không có kết quả hoặc yêu cầu chọn quy tắc khác. Không tự đổi “lần thứ năm” thành “lần cuối” nếu người dùng chưa chọn quy tắc này.

## 6. Cơ chế đếm từ biên tháng

Với lần xuất hiện dương:

1. Tìm ngày đầu tháng.
2. Tìm lần xuất hiện đầu tiên của thứ cần tìm.
3. Cộng `occurrence - 1` tuần.

Ví dụ tháng 02/2024 bắt đầu vào Thứ Năm. Thứ Hai đầu tiên cách đó bốn ngày, là 05/02. Thứ Hai lần thứ hai là 05/02 cộng một tuần, thành 12/02.

Đoạn minh họa cách diễn đạt tương đương cho lần thứ hai:

```java
LocalDate firstMonday =
        month.atDay(1).with(TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY));
LocalDate secondMonday = firstMonday.plusWeeks(1);
```

Với lần xuất hiện âm, xuất phát từ lần khớp cuối tháng rồi lùi từng tuần.

Hiểu cơ chế giúp giải thích trường hợp vượt biên, nhưng trong mã thông thường nên ưu tiên phương thức có tên phù hợp. Không cần tự viết lại phép tính ngày trong tuần nếu thư viện đã diễn đạt đúng yêu cầu.

Nếu tự tính độ lệch bằng số thứ ISO, hãy dùng `getValue()` và phép chia dư không âm thích hợp, tránh nhầm số âm khi quay từ cuối tuần sang đầu tuần. Dùng enum và bộ điều chỉnh thường giúp loại bỏ loại lỗi này.

## 7. Phân biệt với `next`, `nextOrSame` và “đổi thứ trong tuần”

`firstInMonth(MONDAY)` dùng tháng làm phạm vi. `next(MONDAY)` tìm sau ngày nguồn. Hai phép này không thay thế nhau.

Từ ngày 18/02/2024:

```text
firstInMonth(MONDAY) → 05/02/2024
next(MONDAY)         → 19/02/2024
```

Nếu bắt đầu từ chính một ngày Thứ Hai, `next(MONDAY)` đi thêm một tuần; `nextOrSame(MONDAY)` có thể giữ cùng ngày. Sự khác biệt này quan trọng khi tự xây dựng quy tắc bắt đầu từ ngày đầu tháng.

Cũng không nên dùng:

```java
date.with(DayOfWeek.MONDAY);
```

rồi cho rằng đã lấy Thứ Hai đầu tiên của tháng. Đó là điều chỉnh trường ngày trong tuần quanh tuần của ngày nguồn, không phải quy tắc lần xuất hiện trong tháng.

Hãy đọc yêu cầu theo hai phần: **thứ cần tìm** và **mốc/phạm vi để tìm**. Nếu phạm vi là một tháng, thể hiện tháng đó rõ ràng.

## 8. Tạo lịch lặp theo tháng phải tính lại quy tắc

Chương trình có:

```text
Thứ Hai lần thứ hai tháng 02: 2024-02-12
Cộng một tháng:              2024-03-12
Tính lại quy tắc tháng 03:   2024-03-11
```

Ngày 12/03 không còn là Thứ Hai lần thứ hai của tháng 03. `plusMonths(1)` điều chỉnh theo số tháng, không bảo toàn một quy tắc “thứ và số lần xuất hiện”.

Nếu lịch học tổ chức vào Thứ Hai lần thứ hai mỗi tháng:

```java
YearMonth nextMonth = month.plusMonths(1);
LocalDate nextMeeting = nextMonth.atDay(1).with(
        TemporalAdjusters.dayOfWeekInMonth(2, DayOfWeek.MONDAY));
```

Đây là đoạn minh họa, dùng các import trong chương trình hoàn chỉnh. Mỗi tháng nên được tính từ kỳ `YearMonth` tương ứng và cùng quy tắc, thay vì cộng tháng vào ngày họp trước.

Nếu quy tắc là lần thứ năm, dùng chính sách kiểm tra tồn tại như hàm trong bài cho từng tháng.

## 9. Khi cần tất cả các ngày có cùng thứ trong tháng

Chương trình tìm Thứ Hai đầu tiên rồi cộng từng tuần cho đến khi ra khỏi tháng. Danh sách thu được là:

```text
2024-02-05
2024-02-12
2024-02-19
2024-02-26
```

Điểm dừng kiểm tra `YearMonth.from(current).equals(month)` bảo đảm không đưa 04/03 vào lịch tháng 02.

Cách này phù hợp khi giao diện cần hiển thị toàn bộ ngày học theo một thứ. Nếu chỉ cần lần đầu, lần cuối hoặc lần thứ n, lời gọi bộ điều chỉnh trực tiếp thường rõ hơn việc tạo cả danh sách rồi chọn phần tử.

## 10. Lưu ý khi áp dụng vào nghiệp vụ

- `LocalDate` bất biến; phải giữ giá trị trả về từ `with`.
- Một Thứ Sáu trong tháng không tự là ngày làm việc nếu trùng lịch nghỉ riêng.
- Kết quả là ngày, chưa có giờ hoặc múi giờ để xác định một thời điểm toàn cầu.
- Nếu yêu cầu là lịch của một tháng cụ thể, `YearMonth` diễn đạt đầu vào rõ hơn một ngày tùy ý.
- “Lần thứ hai của Thứ Hai” không có nghĩa “tuần số 2” theo mọi quy tắc đánh số tuần; ở đây chỉ đếm các lần xuất hiện của cùng thứ trong tháng.

Trước khi dùng kết quả, kiểm chứng các điều kiện có ý nghĩa: thứ có đúng không, năm–tháng có đúng không, số lần xuất hiện có đúng không và chính sách thiếu lần thứ năm có được thực hiện không.

Các ca thử hữu ích gồm tháng bắt đầu ngay đúng thứ cần tìm, tháng chỉ có bốn lần, tháng có năm lần, tháng 02 nhuận/không nhuận và tháng 12 khi ứng viên vượt sang năm sau. Không chỉ kiểm tra một tháng mà thứ cần tìm luôn xuất hiện năm lần.

## 11. Tự thực hành

1. Từ một ngày bất kỳ trong tháng, lấy Thứ Tư cuối tháng bằng phương thức nào?
2. Vì sao Thứ Hai lần thứ năm tháng 02/2024 có thể cho ngày 04/03?
3. Muốn chắc kết quả thuộc đúng kỳ tháng, cần đối chiếu gì?
4. Cộng một tháng vào Thứ Hai lần thứ hai có bảo toàn quy tắc đó không?
5. Số thứ tự `0` trong `dayOfWeekInMonth` có tự bị từ chối không?

Gợi ý đáp án:

1. `date.with(TemporalAdjusters.lastInMonth(DayOfWeek.WEDNESDAY))`.
2. Thuật toán tiếp tục đếm tuần; API không tự coi thiếu lần thứ năm là lỗi.
3. Đối chiếu cả năm và tháng, chẳng hạn bằng `YearMonth`.
4. Không; cần tính lại từ tháng đích.
5. Không; nó có nghĩa lần khớp cuối của tháng trước.

Chọn bộ điều chỉnh theo đúng quy tắc lịch, kiểm tra biên tháng khi đếm lần xuất hiện và tính lại quy tắc cho từng kỳ khi tạo lịch lặp.
